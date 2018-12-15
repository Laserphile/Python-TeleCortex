import asyncio
import logging
import os
import re
from collections import OrderedDict, deque

import serial

import coloredlogs
import serial_asyncio
# from serial import aio as serial_aio
from context import telecortex
from kitchen.text import converters
from telecortex.session import TelecortexSession, telecortexCommand

import sys
assert sys.version_info > (3, 5), "must be running Python 3.5 or later to use asyncio"

STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
# STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.ERROR

LOG_FILE = ".parallel.log"
ENABLE_LOG_FILE = False

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)
FILE_HANDLER = logging.FileHandler(LOG_FILE)
FILE_HANDLER.setLevel(logging.DEBUG)
STREAM_HANDLER = logging.StreamHandler()
STREAM_HANDLER.setLevel(STREAM_LOG_LEVEL)
if os.name != 'nt':
    STREAM_HANDLER.setFormatter(coloredlogs.ColoredFormatter())
STREAM_HANDLER.addFilter(coloredlogs.HostNameFilter())
STREAM_HANDLER.addFilter(coloredlogs.ProgramNameFilter())
if ENABLE_LOG_FILE:
    LOGGER.addHandler(FILE_HANDLER)
LOGGER.addHandler(STREAM_HANDLER)

TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0

CONTROLLERS = OrderedDict([
    (1, {
        'file': '/dev/cu.usbmodem144101',
        'baud': 57600,
    })
])

class TelecortexCommandAsync(telecortexCommand):
    """

    """
    pass

class TelecortexSessionAsync(TelecortexSession):
    """

    """

    def __init__(self, ser, main_loop, linecount=0):
        super(TelecortexSessionAsync, self).__init__(ser, linecount)
        self.main_loop = main_loop

    def write_line(self, text):
        logging.warning("Should never call write_line synchronously")
        return super(TelecortexSessionAsync, self).write_line(text)

    async def write_line_async(self, text):
        pass

    def get_line(self):
        logging.warning("Should never call get_line synchronously")
        return super(TelecortexSessionAsync, self).get_line()

    async def get_line_async(self):
        try:
            return await asyncio.wait_for(self.ser.readline(), timeout=.2)
        except Exception as e:
            pass


# I'm not really sure what's up with this, seems super high level
class SerialProtocol(asyncio.Protocol):
    def __init__(self, *args, **kwargs):
        super(SerialProtocol, self).__init__(*args, **kwargs)
        self.line_queue = deque()
        self.line_buffer = ""

    def connection_made(self, transport):
        self.transport = transport
        logging.debug('port opened: %s' % transport)
        transport.serial.rts = False  # You can manipulate Serial object via transport
        # transport.write(b'Hello, World!\n')  # Write serial data via transport

    def data_received(self, data):
        logging.debug('data received %s' % repr(data))
        self.line_buffer += converters.to_unicode(data)

        if self.line_buffer:
            lines = re.split(r"[\r\n]+", self.line_buffer)
            self.line_queue.extend(lines[:-1])
            self.line_buffer = lines[-1]

        # if b'\n' in data:
        #     self.transport.close()

    def connection_lost(self, exc):
        logging.debug('port closed')
        self.transport.loop.stop()

    def pause_writing(self):
        logging.debug('pause writing')
        logging.debug(self.transport.get_write_buffer_size())

    def resume_writing(self):
        logging.debug(self.transport.get_write_buffer_size())
        logging.debug('resume writing')

def main():
    loop = asyncio.get_event_loop()
    # coro = serial_aio.create_serial_connection(
    coro = serial_asyncio.create_serial_connection(
        loop,
        SerialProtocol,
        CONTROLLERS[1]['file'],
        baudrate=CONTROLLERS[1]['baud']
    )
    loop.run_until_complete(coro)
    loop.run_forever()
    loop.close()

if __name__ == '__main__':
    main()
