"""Simple Rainbow test script with no mapping required. """

from __future__ import unicode_literals

import itertools
import logging
import os
from datetime import datetime
import time

import serial
from serial.tools import list_ports
from pprint import pformat

import coloredlogs
from context import telecortex
from telecortex.session import (PANEL_LENGTHS, DEFAULT_BAUD,
                                TEENSY_VID, find_serial_dev, TelecortexSession)
from telecortex.util import pix_array2text
from telecortex.config import TeleCortexSessionConfig

def main():
    """
    Main.

    Enumerate serial ports
    Select board by pid/vid
    Rend some HSV rainbowz
    Respond to microcontroller
    """

    conf = TeleCortexSessionConfig(
        name="rainbowz",
        description="send rainbows to a single telecortex controller as fast as possible",
        default_config='single'
    )
    conf.parser.add_argument(
        '--do-single', default=False, action='store_true',
        help="if true, send a single colour to the board, otherwise send a rainbow string"
    )
    # conv.parser.add_argument(
    #     '--virtual', default=False, action='store_true',
    #     help="use virtual sessions (when debugging without access to device)"
    # )
    conf.parser.add_argument('--serial-dev',)
    conf.parser.add_argument('--serial-baud', default=DEFAULT_BAUD)

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    target_device = conf.args.serial_dev
    if target_device is None:
        target_device = find_serial_dev(TEENSY_VID)
    if not target_device:
        raise UserWarning("target device not found")
    else:
        logging.debug("target_device: %s" % target_device)
        logging.debug("baud: %s" % conf.args.serial_baud)
    # Connect to serial
    frameno = 0
    with serial.Serial(
        port=target_device, baudrate=conf.args.serial_baud, timeout=1
    ) as ser:
        # logging.debug("settings: %s" % pformat(ser.get_settings()))
        sesh = conf.setup_session(ser)
        while sesh:

            # H = frameno, S = 255 (0xff), V = 127 (0x7f)
            logging.debug("Drawing frame %s" % frameno)
            for panel, map_name in conf.panels[0]:
                if conf.args.do_single:
                    pixel_str = pix_array2text(
                        frameno, 255, 127
                    )
                    sesh.send_cmd_with_linenum("M2603", {"Q":panel, "V":pixel_str})
                else:
                    panel_length = len(conf.maps[map_name])
                    logging.debug(
                        "panel: %s; panel_length: %s" % (panel, panel_length)
                    )
                    pixel_list = [
                        [(frameno + pixel) % 256, 255, 127]
                        for pixel in range(panel_length)
                    ]
                    logging.debug("pixel_list: %s" % pformat(pixel_list))
                    pixel_list = list(itertools.chain(*pixel_list))
                    pixel_str = pix_array2text(*pixel_list)
                    sesh.chunk_payload_with_linenum("M2601", {"Q":panel}, pixel_str)

                while not sesh.ready:
                    logging.debug("waiting on queue")
            sesh.send_cmd_with_linenum("M2610")
            frameno = (frameno + 1) % 255



if __name__ == '__main__':
    main()
