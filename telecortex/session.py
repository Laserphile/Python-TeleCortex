from __future__ import unicode_literals

import base64
import itertools
import logging
import os
import sys
import re
import time
from collections import OrderedDict, deque
from datetime import datetime
from pprint import pformat, pprint
from copy import deepcopy
import queue
from builtins import super
import json

import serial
from serial.tools import list_ports

import coloredlogs
import six
from kitchen.text import converters
import multiprocessing as mp

# TODO: soft reset when linenum approach long int so it can run forever

# to get these values:
# pip install pyserial
# python -m serial.tools.list_ports --verbose

DEFAULT_BAUD = 57600
DEFAULT_TIMEOUT = 1

# Fix for this issue:
IGNORE_SERIAL_NO = True
IGNORE_VID_PID = False

TEENSY_VID = 0x16C0
PANEL_LENGTHS = [
    316, 260, 260, 260
]

def find_serial_dev(vid=None, pid=None, ser=None):
    """
    Given a Vendor ID and (optional) Product ID, enumerate the serial ports
    until a matching device is found.
    """
    logging.debug(
        "Checking for: VID: %s, PID: %s, SER: %s",
        repr(vid), repr(pid), repr(ser)
    )
    for port_info in list_ports.comports():
        logging.debug(
            "found a device: \ninfo: %s\nvars: %s",
            port_info.usb_info(),
            vars(port_info)
        )
        if vid is not None and port_info.vid != vid:
            logging.debug("vid not match %s | %s", vid, port_info.vid)
            continue
        if pid is not None and port_info.pid != pid:
            logging.debug("pid not match %s | %s", pid, port_info.pid)
            continue
        if ser is not None and port_info.serial_number != str(ser):
            logging.debug("ser not match %s | %s", ser, port_info.serial_number)
            continue
        logging.info("found target device: %s" % port_info.device)
        target_device = port_info.device
        return target_device


def query_serial_dev(vid=None, pid=None, ser=None, dev=None):
    """
    Given a Vendor ID and (optional) Product ID, return the serial ports which
    match these parameters
    """
    logging.debug(
        "Querying for: VID: %s, PID: %s, SER: %s, DEV: %s",
        repr(vid), repr(pid), repr(ser), repr(dev)
    )
    matching_devs = []
    for port_info in list_ports.comports():
        logging.debug(
            "found a device: \ninfo: %s\nvars: %s",
            port_info.usb_info(),
            vars(port_info)
        )
        if vid is not None and port_info.vid != vid:
            logging.debug("vid not match %s | %s", vid, port_info.vid)
            continue
        if pid is not None and port_info.pid != pid:
            logging.debug("pid not match %s | %s", pid, port_info.pid)
            continue
        if ser is not None and port_info.serial_number != str(ser):
            logging.debug("ser not match %s | %s", ser, port_info.serial_number)
            continue
        if dev is not None and port_info.device != dev:
            logging.debug("dev not match %s | %s", ser, port_info.serial_number)
            continue
        logging.info("found target device: %s" % port_info.device)
        target_device = port_info.device
        matching_devs.append(target_device)
    return matching_devs

class TelecortexCommand(object):
    """
    Base Telecortex Command.
    """
    def __init__(self, cmd, args=None):
        self.cmd = cmd
        self.args = args
        self.bytes_occupied = None

    @classmethod
    def fmt_cmd_args(cls, cmd, args):
        if args:
            return " ".join(
                [cmd] + [
                    "%s%s" % (key, value) for key, value in args.items()
                ]
            )
        return cmd

    def add_checksum(self, cmd):
        checksum = 0
        if cmd[-1] != ' ':
            cmd += ' '
        for c in cmd:
            checksum ^= ord(c)
        return cmd + "*%d" % checksum

    def fmt(self, checksum=False):
        cmd = self.fmt_cmd_args(self.cmd, self.args)
        if checksum:
            cmd = self.add_checksum(cmd)
        return cmd

class TelecortexLineCommand(TelecortexCommand):
    """
    Telecortex Command which has a linenumber
    """
    def __init__(self, owner, linenum, cmd, args=None):
        super(TelecortexLineCommand, self).__init__(cmd, args)
        self.owner = owner
        self.linenum = linenum

    @classmethod
    def fmt_line_cmd_args(cls, line, cmd, args):
        return "N%d %s" % (
            line,
            cls.fmt_cmd_args(cmd, args)
        )

    def fmt(self, checksum=False):
        cmd = self.fmt_line_cmd_args(self.linenum, self.cmd, self.args)
        if checksum:
            cmd = self.add_checksum(cmd)
        return cmd


class TelecortexSession(object):
    """
    Manages a serial session with a Telecortex device.

    When commands are sent that require acknowledgement (with linenum),
    they are queued in ack_queue until the acknowledgement or error for that
    command is received.
    When
    """

    # TODO: group idle debug prints

    chunk_size = 261
    ser_buff_size = int(1.2 * chunk_size)
    serial_class = serial.Serial

    re_error = r"^E(?P<errnum>\d+):\s*(?P<err>.*)"
    re_line = r"^N(?P<linenum>\d+)"
    re_line_ok = r"%s:\s*OK" % re_line
    re_line_error = r"%s\s*" % re_line + re_error[1:]
    re_line_response = r"%s:\s*(?P<response>\S+)" % re_line
    re_resend = r"^RS\s+(?P<linenum>\d+)"
    re_set = r"^;SET: "
    re_loo = r"^;LOO: "
    re_loo_rates = (
        r"%s"
        r"FPS:\s+(?P<fps>[\d\.]+),?\s*"
        r"CMD_RATE:\s+(?P<cmd_rate>[\d\.]+)\s*cps,?\s*"
        r"PIX_RATE:\s+(?P<pix_rate>[\d\.]+)\s*pps,?\s*"
        r"QUEUE:\s+(?P<queue_occ>\d+)\s*/\s*(?P<queue_max>\d+)"
    ) % re_loo

    def __init__(self, ser, linecount=0, **kwargs):
        super(TelecortexSession, self).__init__()
        self.ser = ser
        self.linecount = linecount
        # commands which expect acknowledgement
        self.ack_queue = OrderedDict()
        self.responses = OrderedDict()
        self.cid = 0
        self.line_buffer = ""
        self.line_queue = deque()
        self.max_ack_queue = kwargs.get('max_ack_queue', 5)
        assert isinstance(self.max_ack_queue, six.integer_types)
        self.do_crc = kwargs.get('do_crc', True)
        self.ignore_acks = kwargs.get('ignore_acks', False)

    @property
    def lines_avail(self):
        # TODO: something seems to crash this all the time:
        """
        Traceback (most recent call last):
          File "poc/rainbows.py", line 69, in main
            sesh.send_cmd_without_linenum("M2603", {"Q":panel, "V":pixel_str})
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 246, in send_cmd_without_linenum
            self.send_cmd_obj(cmd_obj)
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 229, in send_cmd_obj
            self.parse_responses()
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 553, in parse_responses
            self.parse_response(line)
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 537, in parse_response
            self.handle_resend(**match)
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 442, in handle_resend
            resend_command.args
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 238, in send_cmd_with_linenum
            self.send_cmd_obj(cmd_obj)
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 228, in send_cmd_obj
            while self.lines_avail or self.bytes_left < len(full_cmd):
          File "/Users/derwent/Documents/GitHub/Python-TeleCortex/telecortex/session.py", line 208, in lines_avail
            return self.ser.in_waiting
          File "/Users/derwent/.pyenv/versions/3.6.2/lib/python3.6/site-packages/serial/serialpos[watchdog] outside of io loop, proc.returncode is -15 - -15 (SIGTERM)
        """

        return self.ser.in_waiting

    @classmethod
    def from_serial_conf(cls, serial_conf, linenum=0):
        # TODO: I don't think this works because of garbage collection?
        ser = cls.serial_class(
            port=serial_conf.get('port'),
            baudrate=serial_conf.get('baud', DEFAULT_BAUD),
            timeout=serial_conf.get('timeout', DEFAULT_TIMEOUT)
        )
        return cls(ser, linenum)

    def fmt_cmd(self, linenum=None, cmd=None, args=None):
        raise DeprecationWarning("create cmd object and format instead")

    def add_checksum(self, full_cmd):
        raise DeprecationWarning("create cmd object add instead")

    def send_cmd_obj(self, cmd_obj):
        full_cmd = cmd_obj.fmt(checksum=self.do_crc)
        while self.lines_avail or self.bytes_left < len(full_cmd):
            self.parse_responses()
        cmd_obj.bytes_occupied = self.write_line(full_cmd)
        self.last_cmd = cmd_obj

    def send_cmd_with_linenum(self, cmd, args=None):
        """
        Send a command, expecting an eventual acknowledgement of that command later.
        """
        cmd_obj = TelecortexLineCommand(self, self.linecount, cmd, args)
        self.send_cmd_obj(cmd_obj)
        if not self.ignore_acks:
            self.ack_queue[self.linecount] = cmd_obj
        logging.debug("sending cmd with lineno, %s, ack_queue: %s" % (repr(cmd_obj.fmt(checksum=self.do_crc)), self.ack_queue.keys()))
        self.linecount += 1

    def send_cmd_without_linenum(self, cmd, args=None):
        cmd_obj = TelecortexCommand(cmd, args)
        self.send_cmd_obj(cmd_obj)
        logging.debug("sending cmd without lineno %s" % repr(cmd_obj.fmt()))

    def flush_in(self):
        # wiggle DTR and CTS (only works with AVR boards)
        # self.ser.dtr = not self.ser.dtr
        # self.ser.rts = not self.ser.rts
        # time.sleep(0.1)
        # self.ser.dtr = not self.ser.dtr
        # self.ser.rts = not self.ser.rts
        # time.sleep(0.5)

        while self.lines_avail:
            self.get_line()

    def reset_board(self):

        self.ser.reset_output_buffer()
        self.send_cmd_without_linenum("M9999")
        self.flush_in()
        self.set_linenum(0)

    def get_cid(self):
        linenum = self.linecount
        self.send_cmd_with_linenum("P2205")
        while linenum not in self.responses:
            self.parse_responses()
        response = self.responses.get(linenum)
        assert \
            response.startswith('S'), \
            "unknown response format for N%d: %s" % (linenum, response)
        self.cid = response[1:]
        return self.cid

    def chunk_payload_with_linenum(self, cmd, static_args, payload=None):
        if payload is None:
            self.send_cmd_with_linenum(cmd, static_args)
        offset = 0
        while payload:
            chunk_args = deepcopy(static_args)
            if offset > 0:
                chunk_args['S'] = offset
            chunk_args['V'] = ''
            skeleton_cmd = TelecortexLineCommand.fmt_line_cmd_args(
                self.linecount,
                cmd,
                chunk_args
            )
            # 4 bytes per pixel because base64 encoded 24bit RGB
            pixels_left = int((self.chunk_size - len(skeleton_cmd) - len(' ****\r\n')) / 4)

            assert \
                pixels_left > 0, \
                "not enough bytes left to chunk cmd, skeleton: %s, chunk_size: %s" % (
                    skeleton_cmd,
                    self.chunk_size
                )
            chunk_args['V'] = "".join(payload[:(pixels_left * 4)])

            self.send_cmd_with_linenum(
                cmd,
                chunk_args
            )

            payload = payload[(pixels_left * 4):]
            offset += pixels_left

    def chunk_payload_without_linenum(self, cmd, static_args, payload):
        import pudb; pudb.set_trace()
        offset = 0
        if not static_args:
            static_args = {}
        if not payload:
            self.send_cmd_without_linenum(cmd, static_args)
        while payload:
            chunk_args = deepcopy(static_args)
            if offset > 0:
                chunk_args['S'] = offset
            chunk_args['V'] = ''
            skeleton_cmd = TelecortexCommand.fmt_cmd_args(
                cmd,
                chunk_args
            )
            # 4 bytes per pixel because base64 encoded 24bit RGB
            pixels_left = int((self.chunk_size - len(skeleton_cmd) - len(' ****\r\n')) / 4)
            assert \
                pixels_left > 0, \
                "not enough bytes left to chunk cmd, skeleton: %s, chunk_size: %s" % (
                    skeleton_cmd,
                    self.chunk_size
                )
            chunk_args['V'] = "".join(payload[:(pixels_left * 4)])

            self.send_cmd_without_linenum(
                cmd,
                chunk_args
            )

            payload = payload[(pixels_left * 4):]
            offset += pixels_left

    def clear_ack_queue(self):
        logging.info("clearing ack queue: %s" % self.ack_queue.keys())
        self.ack_queue = OrderedDict()

    def handle_line_ok_match(self, match):
        try:
            linenum = int(match.get('linenum'))
        except ValueError:
            linenum = None
        if linenum is not None:
            deletable_linenums = []
            for ack_linenum in self.ack_queue.keys():
                if ack_linenum <= linenum:
                    deletable_linenums.append(ack_linenum)
            for ack_linenum in deletable_linenums:
                del self.ack_queue[ack_linenum]
        else:
            logging.warn((
                "received an acknowledgement "
                "for an unknown command: %s"
                "known linenums: %s"
            ) % (
                self.last_line,
                self.ack_queue.keys()
            ))

    def handle_error(self, **kwargs):
        try:
            linenum = int(kwargs.get('linenum', None))
        except (ValueError, TypeError):
            linenum = None
        try:
            errnum = int(kwargs.get('errnum', None))
        except (ValueError, TypeError):
            errnum = None

        err = kwargs.get('err', None)

        warning = "error %s: %s" % (
            errnum,
            err
        )
        if linenum is not None:
            warning = "line %d, %s\nOriginal Command: %s" % (
                linenum,
                warning,
                self.ack_queue.get(linenum, "???")
            )
        warning = "CID: %s %s" % (self.cid, warning)
        logging.error(warning)
        if errnum in [10, 19]:
            pass
            # resend request will come later
        elif errnum in [11]:
            pass
            # can't resend after receive acknowledgement
        elif errnum in [14]:
            # base64 panel payload should be a multiple of 4 bytes
            # happens a lot, just skip
            pass
        else:
            raise UserWarning(warning)

    def handle_line_response(self, **kwargs):
        try:
            linenum = int(kwargs.get('linenum', None))
        except (ValueError, TypeError):
            linenum = None
        # TODO: finish this
        self.responses[linenum] = kwargs.get('response', '')

    def handle_resend(self, **kwargs):
        try:
            linenum = int(kwargs.get('linenum', None))
        except (ValueError, TypeError):
            linenum = None

        if linenum not in self.ack_queue:
            error = "CID: %s could not resend unknown linenum: %d" % (self.cid, linenum)
            logging.error(error)
            # raise UserWarning(error)
        warning = "CID: %s resending %s" % (
            self.cid,
            ", ".join([
                "N%s" % line for line in self.ack_queue.keys() if line >= linenum
            ])
        )
        logging.warning(warning)
        old_queue = deepcopy(self.ack_queue)
        self.clear_ack_queue()
        self.linecount = linenum
        for resend_linenum, resend_command in old_queue.items():
            if resend_linenum >= self.linecount:
                self.send_cmd_with_linenum(
                    resend_command.cmd,
                    resend_command.args
                )

    def set_linenum(self, linenum):
        self.send_cmd_with_linenum(
            "M110",
            {"N": linenum}
        )
        self.linecount = linenum + 1

        while self.ack_queue:
            self.parse_responses()

    def write_line(self, text):
        # byte_array = [six.byte2int(j) for j in text]
        # byte_array = six.binary_type(text, 'latin-1')

        if not text[-1] == '\n':
            text = text + '\n'
        assert isinstance(text, six.text_type), "text should be text_type"
        if six.PY3:
            byte_array = six.binary_type(text, 'latin-1')
        if six.PY2:
            byte_array = six.binary_type(text)
        # logging.debug(
        #     "before write | CTS %s, DSR: %s, RTS %s, DTR %s, RI: %s, CD: %s" % (
        #         self.ser.cts, self.ser.dsr, self.ser.rts, self.ser.dtr, self.ser.ri, self.ser.cd
        #     )
        # )
        while len(byte_array) > (self.ser_buff_size - self.ser.out_waiting):
            logging.debug("waiting on write out: %d > (%d - %d)" % (
                len(byte_array),
                self.chunk_size,
                self.ser.out_waiting
            ))
        self.ser.write(byte_array)
        # logging.debug(
        #     "after write | CTS %s, DSR: %s, RTS %s, DTR %s, RI: %s, CD: %s" % (
        #         self.ser.cts, self.ser.dsr, self.ser.rts, self.ser.dtr, self.ser.ri, self.ser.cd
        #     )
        # )
        return len(byte_array)

    def get_line(self):
        while self.ser.in_waiting:
            data = self.ser.read_all()
            self.line_buffer += converters.to_unicode(data)

        if self.line_buffer:
            lines = re.split(r"[\r\n]+", self.line_buffer)
            self.line_queue.extend(lines[:-1])
            self.line_buffer = lines[-1]

        if self.line_queue:
            line = self.line_queue.popleft()
            logging.debug("received line: %s" % line)
            self.last_line = line
            return line

    def parse_response(self, line):
        if line.startswith("IDLE"):
            self.idles_recvd += 1
        elif line.startswith(";"):
            if re.match(self.re_loo_rates, line):
                match = re.search(self.re_loo_rates, line).groupdict()
                pix_rate = int(match.get('pix_rate'))
                cmd_rate = int(match.get('cmd_rate'))
                fps = int(match.get('fps'))
                queue_occ = int(match.get('queue_occ'))
                queue_max = int(match.get('queue_max'))
                logging.warning(
                    "CID: %2s FPS: %3s, CMD_RATE: %5d, PIX_RATE: %7d, QUEUE: %s" % (
                        self.cid, fps, cmd_rate, pix_rate,
                        "%s / %s" % (queue_occ, queue_max)
                    )
                )
            elif re.match(self.re_set, line):
                logging.info(line)
        elif line.startswith("N"):
            self.action_idle = False
            # either "N\d+: OK" or N\d+: E\d+:
            if re.match(self.re_line_ok, line):
                match = re.search(self.re_line_ok, line).groupdict()
                self.handle_line_ok_match(match)
            elif re.match(self.re_line_error, line):
                match = re.search(self.re_line_error, line).groupdict()
                self.handle_error(**match)
            elif re.match(self.re_line_response, line):
                match = re.search(self.re_line_response, line).groupdict()
                self.handle_line_response(**match)
        elif line.startswith("E"):
            self.action_idle = False
            if re.match(self.re_error, line):
                match = re.search(self.re_error, line).groupdict()
                self.handle_error(**match)
        elif line.startswith("RS"):
            self.action_idle = False
            if re.match(self.re_resend, line):
                match = re.search(self.re_resend, line).groupdict()
                self.handle_resend(**match)
        else:
            logging.warn(
                "CID: %s line not recognised:\n%s\n" % (
                    self.cid,
                    repr(line.encode('ascii', errors='backslashreplace'))
                )
            )

    def parse_responses(self):
        line = self.get_line()
        self.idles_recvd = 0
        self.action_idle = True
        while True:
            if not line:
                break
            self.parse_response(line)
            line = self.get_line()
        if self.idles_recvd > 0:
            logging.info('Idle received x %s' % self.idles_recvd)
        if self.action_idle and self.idles_recvd:
            self.clear_ack_queue()
        # else:
        #     logging.debug("did not recieve IDLE")

    @property
    def bytes_left(self):
        ser_buff_len = 0
        if len(self.ack_queue) > self.max_ack_queue:
            return 0
        for linenum, ack_cmd in self.ack_queue.items():
            if ack_cmd.cmd == "M110":
                return 0
            ser_buff_len += ack_cmd.bytes_occupied
            if ser_buff_len > self.ser_buff_size:
                return 0
        return self.ser_buff_size - ser_buff_len

    @property
    def ready(self):
        if self.ignore_acks:
            return True
        if len(self.ack_queue) > self.max_ack_queue:
            return False

        return True

    def __nonzero__(self):
        return bool(self.ser)

    def close(self):
        self.ser.close()

class VirtualTelecortexSession(TelecortexSession):
    serial_class = dict

    def __init__(self, *args, **kwargs):
        kwargs['ignore_acks'] = True
        super().__init__(*args, **kwargs)

    @property
    def lines_avail(self):
        pass

    def write_line(self, text):
        pass

    def get_line(self):
        pass

    @property
    def bytes_left(self):
        return self.chunk_size * 2

    def parse_responses(self):
        time.sleep(0.01)
        if self.ack_queue:
            self.clear_ack_queue()

    @property
    def ready(self):
        self.parse_responses()
        return True

    def __nonzero__(self):
        return True

    def close(self):
        pass


"""
servers is a list of objects containing information about a server's configuration.
"""

class TeleCortexBaseManager(object):
    serial_class = serial.Serial
    session_class = TelecortexSession

    def __init__(self, servers, **kwargs):
        self.servers = servers
        self.known_cids = OrderedDict()
        self.session_kwargs = kwargs

    def get_serial_conf(self, server_info):

        if 'file' in server_info:
            return {
                'file': server_info.get('file'),
                'baud': server_info.get('baud', DEFAULT_BAUD),
                'timeout': server_info.get('timeout', DEFAULT_TIMEOUT)
            }

        dev_kwargs = {}
        for key in ['vid', 'pid', 'ser', 'dev']:
            if key in server_info:
                dev_kwargs[key] = server_info[key]

        if IGNORE_SERIAL_NO:
            if 'ser' in dev_kwargs:
                del dev_kwargs['ser']
        if IGNORE_VID_PID:
            if 'vid' in dev_kwargs:
                del dev_kwargs['vid']
            if 'pid' in dev_kwargs:
                del dev_kwargs['pid']


        ports = query_serial_dev(**dev_kwargs)


        if 'cid' in server_info:
            ports_matching_cid = []

            for port in ports:
                cid = None
                if port in self.known_cids:
                    cid = self.known_cids[port]
                    if cid != server_info.get('cid'):
                        continue
                else:
                    ser = self.serial_class(
                        port=port,
                        baudrate=server_info.get('baud', DEFAULT_BAUD),
                        timeout=server_info.get('timeout', DEFAULT_TIMEOUT)
                    )
                    sesh = self.session_class(ser)
                    sesh.reset_board()
                    if server_info.get('cid') is not None:
                        cid = int(sesh.get_cid())
                        self.known_cids[port] = cid
                        if cid != server_info.get('cid'):
                            ser.close()
                            continue
                ports_matching_cid.append(port)
            ports = ports_matching_cid

        if len(ports) > 1:
            logging.warning("ambiguous server info matches multiple ports: %s | %s" % (
                server_info, ports
            ))

        response = {
            'baud': server_info.get('baud', DEFAULT_BAUD),
            'timeout': server_info.get('timeout', DEFAULT_TIMEOUT)
        }

        if not ports:
            logging.critical("target device not found for server: %s" % server_info)
            return {}
        else:
            response['file'] = ports[0]

        return response

    def all_idle(self):
        raise NotImplementedError()

    def chunk_payload_with_linenum(self, server_id, cmd, args, payload):
        raise NotImplementedError()

class TelecortexSessionManager(TeleCortexBaseManager):

    def __init__(self, servers, **kwargs):
        super(TelecortexSessionManager, self).__init__(servers)
        self.sessions = OrderedDict()
        self.refresh_connections()

    def refresh_connections(self):
        """
        Use information from `self.servers` to ensure all sessions are connected.
        """
        for server_id, server_info in self.servers.items():
            logging.info(
                "looking for server_id %d with info: %s" %
                (server_id, server_info)
            )
            if server_id in self.sessions:
                if self.sessions[server_id]:
                    # we're fine
                    continue
                if not self.sessions[server_id]:
                    # session is dead, kill it
                    self.sessions[server_id].close()
                    del self.sessions[server_id]

            if self.sessions.get(server_id) is not None:
                continue

            # if session does not exist, create a new one
            serial_conf = self.get_serial_conf(server_info)

            if serial_conf:
                ser = self.serial_class(
                    port=serial_conf['file'],
                    baudrate=serial_conf['baud'],
                    timeout=serial_conf['timeout'],
                )
                sesh = self.session_class(ser, **self.session_kwargs)
                sesh.reset_board()
                logging.warning("added session for server: %s" % server_info)
                self.sessions[server_id] = sesh


    def close(self):
        for server_id, session in self.sessions.items():
            session.close()
        self.sessions = OrderedDict()

    def __enter__(self, *args, **kwargs):
        # TODO: this
        pass

    def __exit__(self, *args, **kwargs):
        self.close()

class TelecortexVirtualManagerMixin(object):
    """
    Don't actually create any connections
    """
    serial_class = dict
    session_class = VirtualTelecortexSession

    def get_serial_conf(self, server_info):
        return {
            'file': server_info.get('file', "VIRTUAL"),
            'baud': server_info.get('baud', DEFAULT_BAUD),
            'timeout': server_info.get('timeout', DEFAULT_TIMEOUT)
        }


class TelecortexVirtualManager(TelecortexSessionManager, TelecortexVirtualManagerMixin):
    serial_class = TelecortexVirtualManagerMixin.serial_class
    session_class =  TelecortexVirtualManagerMixin.session_class
    get_serial_conf = TelecortexVirtualManagerMixin.get_serial_conf

class TelecortexThreadManager(TeleCortexBaseManager):

    def __init__(self, servers, **kwargs):
        super(TelecortexThreadManager, self).__init__(servers, **kwargs)
        self.threads = OrderedDict()
        self.refresh_connections()

    @classmethod
    def controller_thread(cls, serial_conf, queue):
        # setup serial device
        ser = cls.serial_class(
            port=serial_conf['file'],
            baudrate=serial_conf['baud'],
            timeout=serial_conf['timeout'],
            xonxoff=False,
            # rtscts=True,
            # dsrdtr=True
        )
        logging.debug("setting up serial sesh: %s" % ser)
        sesh = cls.session_class(ser)
        sesh.reset_board()
        sesh.get_cid()
        # listen for commands
        while sesh:
            try:
                cmd, args, payload = queue.get(timeout=0.01)
            except Exception as exc:
                # logging.error(exc)
                continue
            # logging.debug("received: %s" % str((cmd, args, payload)))
            sesh.chunk_payload_with_linenum(cmd, args, payload)

    def refresh_connections(self, server_ids=None):
        if server_ids is None:
            server_ids = self.servers.keys()

        assert sys.version_info > (3, 0), "multiprocessing only works properly on python 3"
        ctx = mp.get_context('fork')

        for server_id in server_ids:
            server_info = self.threads.get(server_id, (None, None))
            if server_info[1]:
                server_info[1].terminate()

            server_info = self.servers.get(server_id, {})
            serial_conf = self.get_serial_conf(server_info)

            if serial_conf:
                queue = mp.Queue(10)

                proc = ctx.Process(
                    target=self.controller_thread,
                    args=(serial_conf, queue),
                    name="controller_%s" % server_id
                )
                proc.start()
                self.threads[server_id] = (queue, proc)

    @property
    def any_alive(self):
        return any([self.threads.get(server_id, (None, None))[1] for server_id in self.servers.keys()])

    def session_active(self, server_id):
        return self.threads.get(server_id)

    @property
    def all_idle(self):
        return all([queue.empty() for (queue, proc) in self.threads.values()])

    def chunk_payload_with_linenum(self, server_id, cmd, args, payload):
        loops = 0

        while True:
            loops += 1
            if loops > 1000:
                raise UserWarning("too many retries: %s, %s" % (loops,map(str, [server_id, cmd, args, payload])) )
            try:
                self.threads[server_id][0].put((cmd, args, payload), timeout=0.01)
            except queue.Full:
                continue
            except OSError as exc:
                logging.error("OSError: %s" % exc)
                self.refresh_connections([server_id])
                time.sleep(0.1)
                continue
            except Exception as exc:
                raise UserWarning("unhandled exception: %s" % str(exc))
            break

class TeleCortexVirtualThreadManager(TelecortexThreadManager, TelecortexVirtualManagerMixin):
    serial_class = TelecortexVirtualManagerMixin.serial_class
    session_class =  TelecortexVirtualManagerMixin.session_class
    get_serial_conf = TelecortexVirtualManagerMixin.get_serial_conf

class TeleCortexCacheManager(TeleCortexBaseManager):
    def __init__(self, servers, cache_file):
        super(TeleCortexCacheManager, self).__init__(servers)
        self.cache_file = cache_file
        with open(self.cache_file, 'w') as cache:
            cache.write('')

    def chunk_payload_with_linenum(self, server_id, cmd, args, payload):
        with open(self.cache_file, 'a') as cache:
            pass
            # TODO: fix this
            # print(
            #     "%s: %s" % (
            #         server_id,
            #         ", ".join(map(str, [
            #             cmd, json.dumps(args), payload
            #         ]))
            #     ), file=cache
            # )

    def any_alive(self):
        return True

    def all_idle(self):
        return True

    def session_active(self, server_id):
        return True

SERVERS_DOME = OrderedDict([
    (0, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser':'4057530', 'baud':DEFAULT_BAUD, 'cid':1}),
    (1, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser':'4058600', 'baud':DEFAULT_BAUD, 'cid':2}),
    (2, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser':'3176950', 'baud':DEFAULT_BAUD, 'cid':3}),
    (3, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser':'4057540', 'baud':DEFAULT_BAUD, 'cid':4}),
    (4, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser':'4058621', 'baud':DEFAULT_BAUD, 'cid':5})
])

# SERVERS = OrderedDict([
#    (0, {'vid': TEENSY_VID, 'pid': 0x0483})
# ])

# SERVERS_DOME = OrderedDict([
#     (0, {
#         'file': '/dev/cu.usbmodem4057531',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (1, {
#         'file': '/dev/cu.usbmodem4058621',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (2, {
#         'file': '/dev/cu.usbmodem3176951',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (3, {
#         'file': '/dev/cu.usbmodem4057541',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (4, {
#         'file': '/dev/cu.usbmodem4058601',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
# ])

SERVERS_SINGLE = OrderedDict([
    (0, {'vid': TEENSY_VID, 'pid': 0x0483, 'baud': DEFAULT_BAUD, 'timeout': DEFAULT_TIMEOUT})
    # (0, {
    #     'file': '/dev/cu.usbmodem3176931',
    #     'baud': DEFAULT_BAUD,
    #     'timeout': DEFAULT_TIMEOUT
    # }),
])

SERVERS_BLANK = OrderedDict([

])


if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    main()
