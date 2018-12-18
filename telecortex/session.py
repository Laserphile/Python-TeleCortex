from __future__ import unicode_literals

import asyncio
import base64
import itertools
import json
import logging
import os
import queue
import re
import sys
import time
import numpy
from builtins import super
from collections import OrderedDict, deque
from copy import deepcopy
from datetime import datetime
from pprint import pformat, pprint
from time import time as time_now

import coloredlogs
import serial
from kitchen.text import converters

import serial_asyncio
import six
from context import telecortex
from telecortex.ser import (DEFAULT_BAUD, DEFAULT_TIMEOUT, IGNORE_SERIAL_NO,
                            IGNORE_VID_PID, TEENSY_VID, find_serial_dev,
                            query_serial_dev)

# TODO: soft reset when linenum approach long int so it can run forever

PANEL_LENGTHS = [
    316, 260, 260, 260
]


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
        for char in cmd:
            checksum ^= ord(char)
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
    def __init__(self, linenum, cmd, args=None):
        super(TelecortexLineCommand, self).__init__(cmd, args)
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


class TelecortexBaseSession(object):
    """
    Abstract interface for a session with a Telecortex device.

    When commands are sent that require acknowledgement (with linenum),
    they are queued in ack_queue until the acknowledgement or error for that
    command is received.
    """
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

    def __init__(self, linecount=0, **kwargs):
        # Current linecount used as sequence number for error detection
        self.linecount = linecount
        # Lines which have been recieved but are yet to be processed
        self.line_queue = deque()
        # Command objects which are yet to be acknowledged
        self.ack_queue = OrderedDict()
        # Responses attached to a line number which are not "OK" or "ERROR"
        self.responses = OrderedDict()
        # Controller ID as reported by controller
        self.cid = None
        # Partially complete received lines
        self.line_buffer = ""
        # Last line which was receieved
        self.last_line = None
        # Limits the number of commands which have yet to be acknoqledged
        self.max_ack_queue = kwargs.get('max_ack_queue', 5)
        assert isinstance(self.max_ack_queue, six.integer_types)
        # Determins if Cyclic Redundancy Check is added to commands
        self.do_crc = kwargs.get('do_crc', True)
        # Determines if acknowledgments are processed.
        self.ignore_acks = kwargs.get('ignore_acks', False)
        # Maximum length of command, larger commands are chunked to fit.
        self.chunk_size = kwargs.get('chunk_size', 2000)
        # Maximum bytes allowed to sit in Serial.out_waiting
        self.ser_buf_size = kwargs.get('ser_buf_size', 10000)

    def get_line(self):
        """
        Retrieve a single line which has been received from the controller.
        """
        raise NotImplementedError()

    def set_linenum(self, linenum):
        """
        Set the line number used by the controller and this manager.
        """
        raise NotImplementedError()

    def send_cmd_obj(self, cmd):
        """
        Send a command object to the controller.
        """
        raise NotImplementedError()

    def get_cid(self):
        """
        Populate this instance's controller id by asking the controller
        """
        raise NotImplementedError()

    def reset_board(self):
        """
        Software reset the controller
        """
        raise NotImplementedError()

    def close(self):
        """
        Close the connection to the controller
        """
        raise NotImplementedError()

    def send_cmd_with_linenum(self, cmd, args=None):
        """
        Send a command, expect an eventual acknowledgement.
        """
        cmd_obj = TelecortexLineCommand(self.linecount, cmd, args)
        self.send_cmd_obj(cmd_obj)
        if not self.ignore_acks:
            self.ack_queue[self.linecount] = cmd_obj
        logging.debug("sending cmd with lineno, %s, ack_queue: %s" % (
            repr(cmd_obj.fmt(checksum=self.do_crc)), self.ack_queue.keys()))
        self.linecount += 1

    def send_cmd_without_linenum(self, cmd, args=None):
        cmd_obj = TelecortexCommand(cmd, args)
        self.send_cmd_obj(cmd_obj)
        logging.debug("sending cmd without lineno %s" % (
            repr(cmd_obj.fmt(checksum=self.do_crc))))

    def parse_response(self, line):
        if line.startswith("IDLE"):
            self.idles_recvd += 1
        elif line.startswith(";"):
            if re.match(self.re_loo_rates, line):
                self.last_loo_rate = time_now()
                match = re.search(self.re_loo_rates, line).groupdict()
                pix_rate = int(match.get('pix_rate'))
                cmd_rate = int(match.get('cmd_rate'))
                fps = int(match.get('fps'))
                queue_occ = int(match.get('queue_occ'))
                queue_max = int(match.get('queue_max'))
                logging.warning(
                    (
                        "CID: %2s FPS: %3s, CMD_RATE: %5d, PIX_RATE: %7d, "
                        "QUEUE: %s") % (
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
        """
        Parse all of the lines in the incoming line queue in order.

        Assume that controller may send many commands at the same time.
        """
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
            self.last_idle = time_now()
            self.clear_ack_queue()
        # else:
        #     logging.debug("did not recieve IDLE")

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
            pixels_left = int(
                (self.chunk_size - len(skeleton_cmd) - len(' ****\r\n')) / 4)

            assert \
                pixels_left > 0, \
                (
                    "not enough bytes left to chunk cmd, skeleton: %s, "
                    "chunk_size: %s"
                ) % (
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
            pixels_left = int(
                (self.chunk_size - len(skeleton_cmd) - len(' ****\r\n')) / 4)
            assert \
                pixels_left > 0, \
                (
                    "not enough bytes left to chunk cmd, skeleton: %s, "
                    "chunk_size: %s"
                ) % (
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
        self.responses[linenum] = kwargs.get('response', '')

    def handle_resend(self, **kwargs):
        try:
            linenum = int(kwargs.get('linenum', None))
        except (ValueError, TypeError):
            linenum = None

        if linenum not in self.ack_queue:
            error = "CID: %s could not resend unknown linenum: %d" % (
                self.cid, linenum)
            logging.error(error)
            # raise UserWarning(error)
        warning = "CID: %s resending %s" % (
            self.cid,
            ", ".join([
                "N%s" % line
                for line in self.ack_queue.keys() if line >= linenum
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

    @property
    def ready(self):
        return True

# TODO: rename to TelecortexSerialSession or something


class TelecortexSession(TelecortexBaseSession):
    """
    Manages a serial session with a Telecortex device.
    """

    serial_class = serial.Serial

    def __init__(self, ser, **kwargs):
        super(TelecortexSession, self).__init__(**kwargs)
        self.ser = ser

    @property
    def lines_avail(self):
        return self.ser.in_waiting

    def relinquish(self):
        """
        Potentially relinquish control to other threads.
        """
        pass

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
        """
        @overrides TelecortexBaseSession.send_cmd_obj
        """
        full_cmd = cmd_obj.fmt(checksum=self.do_crc)
        while any([
            self.lines_avail,
            self.bytes_left < len(full_cmd),
            # self.last_idle - time_now() > 1,
            # self.last_loo_rate - time_now() > 1
        ]):
            self.parse_responses()
        cmd_obj.bytes_occupied = self.write_line(full_cmd)
        self.last_cmd = cmd_obj

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
        """
        @overrides TelecortexBaseSession.reset_board
        """
        self.last_idle = time_now()
        self.last_loo_rate = time_now()
        self.ser.reset_output_buffer()
        self.send_cmd_without_linenum("M9999")
        self.flush_in()
        self.set_linenum(0)

    def get_cid(self):
        """
        @overrides TelecortexBaseSession.get_cid
        """
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

    def set_linenum(self, linenum):
        """
        @overrides TelecortexBaseSession.set_linenum
        """
        self.send_cmd_with_linenum(
            "M110",
            {"N": linenum}
        )
        self.linecount = linenum + 1

        while self.ack_queue:
            self.parse_responses()

    def write_line(self, text):
        # byte_array = serial.to_bytes(text)
        if not text[-1] == '\n':
            text = text + '\n'
        # assert isinstance(text, six.text_type), "text should be text_type"
        # if six.PY3:
        #     byte_array = six.binary_type(text, 'latin-1')
        # if six.PY2:
        #     byte_array = six.binary_type(text)

        bytes_ = converters.to_bytes(text)
        bytes_len = len(bytes_)

        while bytes_:
            buf_left = self.ser_buf_size - self.ser.out_waiting
            buf_left = numpy.clip(buf_left, 0, len(bytes_))
            logging.debug("writing partial: %s" % (repr(bytes_[:buf_left]),))
            self.ser.write(bytes_[:buf_left])
            bytes_ = bytes_[buf_left:]
            if bytes_:
                logging.debug("waiting on write out: %d = %d - %d" % (
                    buf_left,
                    self.ser_buf_size,
                    self.ser.out_waiting
                ))
                self.relinquish()

        # while len(bytes_) > (self.ser_buf_size - self.ser.out_waiting):
        #     logging.debug("waiting on write out: %d > (%d - %d)" % (
        #         len(bytes_),
        #         self.chunk_size,
        #         self.ser.out_waiting
        #     ))
        #     self.relinquish()
        # self.ser.write(bytes_)
        return bytes_len

    def get_line(self):
        """
        @overrides TelecortexBaseSession.get_line
        """
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

    @property
    def bytes_left(self):
        ser_buf_len = self.ser.out_waiting
        if not self.ignore_acks and len(self.ack_queue) > self.max_ack_queue:
            return 0
        if self.ignore_acks:
            for linenum, ack_cmd in self.ack_queue.items():
                if ack_cmd.cmd == "M110":
                    return 0
                ser_buf_len += ack_cmd.bytes_occupied
                if ser_buf_len > self.ser_buf_size:
                    return 0
        return self.ser_buf_size - ser_buf_len

    @property
    def ready(self):
        if self.ser.out_waiting >= self.ser_buf_size:
            return False
        if not self.ignore_acks and len(self.ack_queue) >= self.max_ack_queue:
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


class ThreadedTelecortexSession(TelecortexSession):
    def relinquish(self):
        """
        Relinquish control to other threads.
        """
        # TODO: actually relinquish
        time.sleep(0.01)


class TelecortexSerialProtocol(asyncio.Protocol, TelecortexBaseSession):
    """
    A serial protocol, which uses a `serial_asyncio.SerialTransport`, is
    generally responsible for telling the transport what to write, and for
    interpreting the data coming from the transport.

    See: https://tinkering.xyz/async-serial/

    TODO:

    Generate an asyncio.StreamReader/asyncio.StreamWriter pair.
    """
    def __init__(self, queue_, linecount=0, *args, **kwargs):
        asyncio.Protocol.__init__(self)
        TelecortexBaseSession.__init__(self, *args, **kwargs)
        # Asyncio queue containing commands to be run
        self.cmd_queue = queue_
        # Since serial writes are parallelized, must have a mutex.
        self.serial_lock = asyncio.Lock()

    def connection_made(self, transport):
        """
        Provide Asyncio with Callback for when serial is connected.
        """
        assert isinstance(transport, serial_asyncio.SerialTransport), \
            "expected `serial_asyncio.SerialTransport` transport"
        self.transport = transport
        logging.debug('port opened: %s' % transport)
        # You can manipulate Serial object via transport
        # transport.serial.rts = False
        # Write serial data via transport
        # transport.write(b'Hello, World!\n')

        self.reset_board()

        self.get_cid()

        asyncio.create_task(self.cmd_queue_loop())

    async def cmd_queue_loop(self):
        while True:
            try:
                cmd, args, payload = await self.cmd_queue.get()
                self.chunk_payload_with_linenum(cmd, args, payload)
            except Exception as exc:
                logging.error(exc)

    def data_received(self, data):
        """
        Provide Asyncio with Callback for when data is received.
        """
        logging.debug('data received %s' % repr(data))
        self.line_buffer += converters.to_unicode(data)

        if '\n' in self.line_buffer:
            lines = re.split(r"[\r\n]+", self.line_buffer)
            self.line_queue.extend(lines[:-1])
            self.line_buffer = lines[-1]

        self.parse_responses()

    def get_line(self):
        """
        @overrides TelecortexBaseSession.get_line
        """
        if self.line_queue:
            line = self.line_queue.popleft()
            logging.debug("received line: %s" % line)
            self.last_line = line
            return line

    def connection_lost(self, exc):
        """
        Provide Asyncio with Callback for when serial is disconnected.
        """
        logging.warning('port closed')
        self.transport.loop.stop()

    # def pause_writing(self):
    #     logging.debug('pause writing')
    #     logging.debug(self.transport.get_write_buffer_size())
    #
    # def resume_writing(self):
    #     logging.debug(self.transport.get_write_buffer_size())
    #     logging.debug('resume writing')

    async def relinquish_async(self):
        await asyncio.sleep(0.005)

    async def write_line_async(self, text):
        """
        Async here because Serial.write blocks?
        """
        logging.debug("sending text: %s" % repr(text))
        if not text[-1] == '\n':
            text = text + '\n'
        # bytes_ = six.binary_type(text, 'latin-1')
        # bytes_ = text.encode('utf8')
        bytes_ = converters.to_bytes(text)
        bytes_len = len(bytes_)

        async with self.serial_lock:
            while bytes_:
                buf_left = self.ser_buf_size - self.transport.serial.out_waiting
                buf_left = numpy.clip(buf_left, 0, len(bytes_))
                logging.debug("writing partial: %s" % (repr(bytes_[:buf_left]),))
                self.transport.serial.write(bytes_[:buf_left])
                bytes_ = bytes_[buf_left:]

                if bytes_:
                    logging.debug("waiting on write out: %d = %d - %d" % (
                        buf_left,
                        self.ser_buf_size,
                        self.transport.serial.out_waiting
                    ))
                    # await self.relinquish_async()
        return bytes_len

    # def write_line(self, text):
    #     """
    #     """
    #     asyncio.create_task(

    def send_cmd_obj(self, cmd_obj):
        """
        @overrides TelecortexBaseSession.send_cmd_obj
        """
        full_cmd = cmd_obj.fmt(checksum=self.do_crc)
        cmd_obj.bytes_occupied = asyncio.create_task(
            self.write_line_async(full_cmd))
        self.last_cmd = cmd_obj

    def set_linenum(self, linenum):
        """
        @overrides TelecortexBaseSession.set_linenum
        """
        self.send_cmd_with_linenum(
            "M110",
            {"N": linenum}
        )
        self.linecount = linenum + 1

    def reset_board(self):
        """
        @overrides TelecortexBaseSession.reset_board
        """
        self.send_cmd_without_linenum("M9999")
        self.set_linenum(0)

    async def get_cid_async(self):
        """
        Async here because has to wait for response from controller
        """
        linenum = self.linecount
        self.send_cmd_with_linenum("P2205")
        while linenum not in self.responses:
            logging.debug(
                '%d not in responses: %s' % (linenum, self.responses,))
            await self.relinquish_async()
        response = self.responses.get(linenum)

        assert \
            response.startswith('S'), \
            "Expected P2205 response to have S value, instead N%d: %s" % (
                linenum, response)
        self.cid = response[1:]

        logging.debug("set CID to %s" % self.cid)

    def get_cid(self):
        """
        @overrides TelecortexBaseSession.get_cid
        """
        asyncio.create_task(self.get_cid_async())


if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    main()
