from __future__ import unicode_literals

import base64
import itertools
import logging
import os
import re
import time
from collections import OrderedDict
from datetime import datetime
from pprint import pformat, pprint
from copy import deepcopy

import serial
from serial.tools import list_ports

import coloredlogs
import six
from kitchen.text import converters

# TODO: soft reset when linenum approach long int so it can run forever

# to get these values:
# pip install pyserial
# python -m serial.tools.list_ports --verbose

DEFAULT_BAUDRATE = 57600
DEFAULT_TIMEOUT = 1

# Fix for this issue:
IGNORE_SERIAL_NO = True

TELECORTEX_VID = 0x16C0
TELECORTEX_BAUD = 57600
PANEL_LENGTHS = [
    316, 260, 260, 260
]
PANELS = len(PANEL_LENGTHS)

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

def query_serial_dev(vid=None, pid=None, ser=None):
    """
    Given a Vendor ID and (optional) Product ID, return the serial ports which
    match these parameters
    """
    logging.debug(
        "Querying for: VID: %s, PID: %s, SER: %s",
        repr(vid), repr(pid), repr(ser)
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

    chunk_size = 256
    ser_buff_size = 1 * chunk_size
    max_ack_queue = 5

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
    # re_loo_timing = (
    #     r"%s"
    #     r"TIME:\s+(?P<time>\d+),?\s*"
    # ) % re_loo
    # re_loo_get_stats = (
    #     r"%s"
    #     r"GET_CMD:\s+(?P<get_cmd>\d+),?\s*"
    #     r"ENQD:\s+(?P<enqd>\d+),?\s*"
    # ) % re_loo
    # re_loo_proc_stats = (
    #     r"%s"
    #     r"CMD:\s+(?P<cmd>[A-Z] \d+),?\s*"
    #     r"PIXLS:\s+(?P<pixls>\d+),?\s*"
    #     r"PROC_CMD:\s+(?P<proc_cmd>\d+),?\s*"
    #     r"PARSE_CMD:\s+(?P<parse_cmd>\d+),?\s*"
    #     r"PR_PA_CMD:\s+(?P<pr_pa_cmd>\d+),?\s*"
    # ) % re_loo
    # re_loo_get_cmd_time = r"%sget_cmd: (?P<time>[\d\.]+)" % re_loo
    # re_loo_process_cmd_time = r"%sprocess_cmd: (?P<time>[\d\.]+)" % re_loo
    # re_enq = r"^;ENQ: "
    # re_gco = r"^;GCO: "
    # re_gco_encoded = r"%s-> payload: " % re_gco
    # re_gco_decoded = r"%s-> decoded payload: " % re_gco
    do_crc = True

    def __init__(self, ser, linecount=0):
        super(TelecortexSession, self).__init__()
        self.ser = ser
        self.linecount = linecount
        # commands which expect acknowledgement
        self.ack_queue = OrderedDict()
        self.responses = OrderedDict()
        self.cid = 0

    @classmethod
    def from_serial_conf(cls, serial_conf, linenum=0):
        ser = serial.Serial(
            port=serial_conf.get('port'),
            baudrate=serial_conf.get('baud', DEFAULT_BAUDRATE),
            timeout=serial_conf.get('timeout', DEFAULT_TIMEOUT)
        )
        return TelecortexSession.from_serial_obj(ser)

    def fmt_cmd(self, linenum=None, cmd=None, args=None):
        raise DeprecationWarning("create cmd object and format instead")

    def add_checksum(self, full_cmd):
        raise DeprecationWarning("create cmd object add instead")

    def send_cmd_obj(self, cmd_obj):
        full_cmd = cmd_obj.fmt(checksum=self.do_crc)
        while self.ser.in_waiting or self.bytes_left < len(full_cmd):
            self.parse_responses()
        cmd_obj.bytes_occupied = self.write_line(full_cmd)
        self.last_cmd = cmd_obj

    def send_cmd_with_linenum(self, cmd, args=None):
        """
        Send a command, expecting an eventual acknowledgement of that command later.
        """
        cmd_obj = TelecortexLineCommand(self, self.linecount, cmd, args)
        self.send_cmd_obj(cmd_obj)
        self.ack_queue[self.linecount] = cmd_obj
        logging.debug("sending cmd with lineno, %s" % repr(cmd_obj.fmt()))
        self.linecount += 1

    def send_cmd_without_linenum(self, cmd, args=None):
        cmd_obj = TelecortexCommand(cmd, args)
        self.send_cmd_obj(cmd_obj)
        logging.debug("sending cmd without lineno %s" % repr(cmd_obj.fmt()))

    def reset_board(self):

        self.ser.reset_output_buffer()
        self.ser.flush()
        self.send_cmd_without_linenum("M9999")

        # wiggle DTR and CTS (only works with AVR boards)
        self.ser.dtr = not self.ser.dtr
        self.ser.rts = not self.ser.rts
        time.sleep(0.1)
        self.ser.dtr = not self.ser.dtr
        self.ser.rts = not self.ser.rts
        time.sleep(0.5)

        while self.ser.in_waiting:
            self.get_line()

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

    def chunk_payload_with_linenum(self, cmd, static_args, payload):
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
            pixels_left = int((self.chunk_size - len(skeleton_cmd) - len(' ****\r\n'))/4)

            assert \
                pixels_left > 0, \
                "not enough bytes left to chunk cmd, skeleton: %s, chunk_size: %s" % (
                    skeleton_cmd,
                    self.chunk_size
                )
            chunk_args['V'] = "".join(payload[:(pixels_left*4)])

            self.send_cmd_with_linenum(
                cmd,
                chunk_args
            )

            payload = payload[(pixels_left*4):]
            offset += pixels_left

    def chunk_payload_without_linenum(self, cmd, static_args, payload):
        offset = 0
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
            pixels_left = int((self.chunk_size - len(skeleton_cmd) - len(' ****\r\n'))/4)
            assert \
                pixels_left > 0, \
                "not enough bytes left to chunk cmd, skeleton: %s, chunk_size: %s" % (
                    skeleton_cmd,
                    self.chunk_size
                )
            chunk_args['V'] = "".join(payload[:(pixels_left*4)])

            self.send_cmd_without_linenum(
                cmd,
                chunk_args
            )

            payload = payload[(pixels_left*4):]
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

    def handle_error(self, errnum, err, linenum=None):
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

    def handle_error_match(self, matchdict):
        try:
            linenum = int(matchdict.get('linenum', None))
        except (ValueError, TypeError):
            linenum = None
        try:
            errnum = int(matchdict.get('errnum', None))
        except (ValueError, TypeError):
            errnum = None

        self.handle_error(errnum, matchdict.get('err', None), linenum)

    def handle_line_response_match(self, matchdict):
        try:
            linenum = int(matchdict.get('linenum', None))
        except (ValueError, TypeError):
            linenum = None
        # TODO: finish this
        self.responses[linenum] = matchdict.get('response', '')

    def handle_resend(self, linenum):
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
                self.send_cmd_with_linenum(*resend_command)

    def handle_resend_match(self, matchdict):
        try:
            linenum = int(matchdict.get('linenum', None))
        except (ValueError, TypeError):
            linenum = None

        self.handle_resend(linenum)

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
        self.ser.write(byte_array)
        return len(byte_array)

    def get_line(self):
        line = self.ser.readline()
        line = converters.to_unicode(line)
        line = re.split(r"[\r\n]+", line)[0]
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
                self.handle_error_match(match)
            elif re.match(self.re_line_response, line):
                match = re.search(self.re_line_response, line).groupdict()
                self.handle_line_response_match(match)
        elif line.startswith("E"):
            self.action_idle = False
            if re.match(self.re_error, line):
                match = re.search(self.re_error, line).groupdict()
                self.handle_error_match(match)
        elif line.startswith("RS"):
            self.action_idle = False
            if re.match(self.re_resend, line):
                match = re.search(self.re_resend, line).groupdict()
                self.handle_resend_match(match)
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
            self.parse_response(line)
            if not self.ser.in_waiting:
                break
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
        for linenum, ack_cmd in self.ack_queue.items():
            if ack_cmd.cmd == "M110":
                return 0
            ser_buff_len += ack_cmd.bytes_occupied
            if ser_buff_len > self.ser_buff_size:
                return 0
        return self.ser_buff_size - ser_buff_len

    @property
    def ready(self):
        if len(self.ack_queue) > self.max_ack_queue:
            return False
        ser_buff_len = 0
        for linenum, ack_cmd in self.ack_queue.items():
            if ack_cmd[0] == "M110":
                return False
            ser_buff_len += len(self.fmt_cmd(linenum, *ack_cmd))
            if ser_buff_len > self.ser_buff_size:
                return False
        return True

    def __nonzero__(self):
        return bool(self.ser)

    def close(self):
        self.ser.close()

"""
servers is a list of objects containing information about a server's configuration.
"""

class TelecortexSessionManager(object):
    # TODO: This
    def __init__(self, servers):
        self.servers = servers
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
            dev_kwargs = {}
            for key in ['vid', 'pid', 'ser']:
                if key in server_info:
                    dev_kwargs[key] = server_info[key]

            if IGNORE_SERIAL_NO:
                if 'ser' in dev_kwargs:
                    del dev_kwargs['ser']

            ports = query_serial_dev(**dev_kwargs)
            if not ports:
                raise UserWarning("target device not found for server: %s" % server_info)

            for port in ports:
                ser = serial.Serial(
                    port=port,
                    baudrate=server_info.get('baud', DEFAULT_BAUDRATE),
                    timeout=server_info.get('timeout', DEFAULT_TIMEOUT)
                )
                sesh = TelecortexSession(ser)
                sesh.reset_board()
                if server_info.get('cid') is not None:
                    cid = int(sesh.get_cid());
                    if cid != server_info.get('cid'):
                        ser.close()
                        continue
                # if doesn't match controller id then close port and skip
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


SERVERS = OrderedDict([
    (0, {'vid': 0x16C0, 'pid': 0x0483, 'ser':'4057530', 'baud':57600, 'cid':1}),
    (1, {'vid': 0x16C0, 'pid': 0x0483, 'ser':'4058601', 'baud':57600, 'cid':2}),
    (2, {'vid': 0x16C0, 'pid': 0x0483, 'ser':'3176950', 'baud':57600, 'cid':3}),
    (3, {'vid': 0x16C0, 'pid': 0x0483, 'ser':'4057540', 'baud':57600, 'cid':4}),
    (4, {'vid': 0x16C0, 'pid': 0x0483, 'ser':'4058621', 'baud':57600, 'cid':5})
])

SERVERS = OrderedDict([
    (0, {'vid': 0x16C0, 'pid': 0x0483})
])

def main():
    manager = TelecortexSessionManager(SERVERS)
    while manager:
        for sesh in manager.sessions.values():
            for panel_number, _ in enumerate(PANEL_LENGTHS):
                sesh.send_cmd_with_linenum(
                    "M2602",
                    {"Q": panel_number, "V": "////"}
                )
            sesh.send_cmd_with_linenum("M2610")


if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    main()
