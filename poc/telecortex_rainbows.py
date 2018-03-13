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

import serial
from serial.tools import list_ports

import coloredlogs
import six
from kitchen.text import converters
from telecortex_session import TelecortexSession

STREAM_LOG_LEVEL = logging.INFO
# STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.DEBUG

LOG_FILE = ".rainbowz.log"
PROC_DATA_FILE = "rainbowz_proc.csv"
GET_DATA_FILE = "rainbowz_get.csv"
ENABLE_LOG_FILE = False
ENABLE_PROC_DATA = False
ENABLE_GET_DATA = False

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

TELECORTEX_DEV = "/dev/tty.usbmodem35"
# to get these values:
# pip install pyserial
# python -m serial.tools.list_ports
TELECORTEX_VID = 0x16C0
TELECORTEX_PID = 0x0483
TELECORTEX_BAUD = 57600
ACK_QUEUE_LEN = 3
PANELS = 4
PANEL_LENGTHS = [
    316, 260, 260, 260
]

DO_SINGLE = False

def pix_array2text(*pixels):
    """Convert an array of pixels to a base64 encoded unicode string."""
    # logging.debug("pixels: %s" % repr(["%02x" % pixel for pixel in pixels]))
    # logging.debug(
    #     "bytes: %s" % repr([six.int2byte(pixel) for pixel in pixels])
    # )
    pix_bytestring = b''.join([
        six.int2byte(pixel % 256)
        for pixel in pixels
    ])
    # logging.debug("bytestring: %s" % repr(pix_bytestring))

    response = base64.b64encode(pix_bytestring)
    response = six.text_type(response, 'ascii')
    # response = ''.join(map(six.unichr, pixels))
    # response = six.binary_type(base64.b64encode(
    #     bytes(pixels)
    # ))
    # logging.debug("pix_text: %s" % repr(response))
    return response


def main():
    """
    Main.

    Enumerate serial ports
    Select board by pid/vid
    Rend some HSV rainbowz
    Respond to microcontroller
    """

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    target_device = TELECORTEX_DEV
    for port_info in list_ports.comports():
        # logging.debug(
        #     "found serial device vid: %s, pid: %s" % (
        #         port_info.vid, port_info.pid
        #     )
        # )
        if port_info.vid == TELECORTEX_VID:
            logging.info("found target device: %s" % port_info.device)
            target_device = port_info.device
            break
    if not target_device:
        raise UserWarning("target device not found")
    # Connect to serial
    frameno = 0
    with serial.Serial(
        port=target_device, baudrate=TELECORTEX_BAUD, timeout=1
    ) as ser:
        # logging.debug("settings: %s" % pformat(ser.get_settings()))
        sesh = TelecortexSession(ser)
        sesh.reset_board()

        while sesh:

            # H = frameno, S = 255 (0xff), V = 127 (0x7f)
            logging.debug("Drawing frame %s" % frameno)
            for panel in range(PANELS):
                if DO_SINGLE:
                    pixel_str = pix_array2text(
                        frameno, 255, 127
                    )
                    sesh.send_cmd_sync("M2603", "Q%d V%s" % (panel, pixel_str))
                else:
                    panel_length = PANEL_LENGTHS[panel]
                    # logging.debug(
                    #     "panel: %s; panel_length: %s" % (panel, panel_length)
                    # )
                    pixel_list = [
                        [(frameno + pixel) % 256, 255, 127]
                        for pixel in range(panel_length)
                    ]
                    # logging.info("pixel_list: %s" % pformat(pixel_list))
                    pixel_list = list(itertools.chain(*pixel_list))
                    pixel_str = pix_array2text(*pixel_list)
                    sesh.chunk_payload("M2601", "Q%d" % panel, pixel_str)
            sesh.send_cmd_sync("M2610")
            frameno = (frameno + 1) % 255


if __name__ == '__main__':
    main()
