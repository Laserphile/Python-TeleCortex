"""Asynchronous implementation of session management."""

import asyncio
import functools
import itertools
import logging
import os
import re
import sys
from asyncio import AbstractEventLoop
from collections import OrderedDict, deque
from datetime import datetime
from time import time as time_now

import coloredlogs
import serial
from kitchen.text import converters

import serial_asyncio
import six
# from serial import aio as serial_aio
from context import telecortex
from telecortex.config import TeleCortexManagerConfig
from telecortex.session import TeleCortexBaseManager, TelecortexBaseSession
from telecortex.util import pix_array2text

assert sys.version_info > (3, 7), (
    "must be running Python 3.7 or later to use asyncio")


# I'm not really sure what's up with this, seems super high level
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
        self.transport.serial.write(bytes_)
        return len(bytes_)

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
            await asyncio.sleep(0.1)
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

class TelecortexAsyncManager(TeleCortexBaseManager):
    """
    Manages TelecortexSerialProtocol objects in an async loop.
    """
    protocol_class = TelecortexSerialProtocol

    def __init__(self, conf, graphics, **kwargs):
        self.queue_len = kwargs.pop('queue_len', 10)
        self.conf = conf
        self.graphics = graphics
        super(TelecortexAsyncManager, self).__init__(conf.servers, **kwargs)
        # asyncio.Queues for sending commands to each server.
        self.cmd_queues = OrderedDict()
        # asyncio coroutines controlling each serial device
        self.sesh_coroutines = OrderedDict()
        # asyncio coroutines sending graphics to each serial coroutine
        self.gfx_coroutines = OrderedDict()
        # A tuple of (queue, sesh, gfx) for each server_id
        self.workers = OrderedDict()
        self.loop = asyncio.get_event_loop()
        self.loop.set_debug(True)
        self.refresh_connections()

    @classmethod
    def open_sesh(cls, serial_kwargs, session_kwargs):
        """
        @overrides TeleCortexBaseManager.open_sesh.
        """
        return

    def refresh_connections(self, server_ids=None):
        if server_ids is None:
            server_ids = self.servers.keys()
        else:
            raise UserWarning("individual server refresh not supported")

        assert sys.version_info > (3, 7), (
            "async only works properly on python 3.7")

        for server_id, server_info in self.servers.items():
            if server_id not in self.cmd_queues:
                self.cmd_queues[server_id] = asyncio.Queue(self.queue_len)

            if server_id in self.sesh_coroutines:
                self.sesh_coroutines[server_id].cancel()
            serial_kwargs = self.get_serial_conf(server_info)
            serial_url = serial_kwargs.pop('port')
            coro = serial_asyncio.create_serial_connection(
                self.loop,
                functools.partial(
                    self.protocol_class,
                    self.cmd_queues[server_id],
                    **self.session_kwargs
                ),
                serial_url,
                **serial_kwargs
            )
            self.sesh_coroutines[server_id] = coro

            if server_id not in self.gfx_coroutines:
                self.gfx_coroutines[server_id] = graphics(
                    self.conf, server_id, self.cmd_queues[server_id])

        self.loop.run_until_complete(asyncio.gather(*itertools.chain(
            self.sesh_coroutines.values(),
            self.gfx_coroutines.values()
        )))


class TeleCortexAsyncManagerConfig(TeleCortexManagerConfig):
    """
    Config for multiple asynchronous sessions.
    """
    real_manager_class = TelecortexAsyncManager

    def __init__(self, graphics, *args, **kwargs):
        self.graphics = graphics
        super().__init__(*args, **kwargs)

    def setup_manager(self):
        return self.manager_class(
            self,
            self.graphics,
            **self.session_kwargs
        )

    # def setup_loop(self, graphics):
    #     """
    #     Gather several asyncio coroutines into a loop.
    #
    #     Sorry Jon, this is probably going to make very little sense :(
    #     """
    #     coroutines = []
    #     for server_id in self.servers.keys():
    #         cmd_queue = asyncio.Queue(10)
    #         coroutines.append(serial_asyncio.create_serial_connection(
    #             self.loop,
    #             functools.partial(
    #                 TelecortexSerialProtocol,
    #                 cmd_queue,
    #                 max_ack_queue=self.args.max_ack_queue,
    #                 do_crc=self.args.do_crc,
    #                 ignore_acks=self.args.ignore_acks,
    #                 chunk_size=self.args.chunk_size,
    #                 ser_buf_size=self.args.ser_buf_size
    #             ),
    #             self.servers[server_id]['file'],
    #             baudrate=self.servers[server_id]['baud']
    #         ))
    #         coroutines.append(
    #             graphics(self, server_id, cmd_queue))
    #
    #     self.loop.run_until_complete(*coroutines)
    #     self.loop.run_forever()
    #     self.loop.close()

async def graphics(conf, server_id, cmd_queue):
    # Frame number used for animations
    frameno = 0
    while True:
        for panel in range(4):
            logging.debug("putting M2603")
            pixel_str = pix_array2text(
                frameno, 255, 127
            )
            await cmd_queue.put(
                ("M2603", {"Q": panel}, pixel_str)
            )
        await cmd_queue.put(
            ("M2610", None, None)
        )
        await asyncio.sleep(0.01)

        # increment frame number
        frameno = (frameno + 1) % 255


def main():
    logging.getLogger('asyncio').setLevel(logging.DEBUG)

    conf = TeleCortexAsyncManagerConfig(
        name="async",
        description=(
            "Asynchronous Management of Telecortex Controllers"),
        default_config='dome_overhead',
        graphics=graphics
    )

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    start_time = time_now()

    manager = conf.setup_manager()

    manager.loop.run_forever()
    manager.loop.close()


if __name__ == '__main__':
    main()
