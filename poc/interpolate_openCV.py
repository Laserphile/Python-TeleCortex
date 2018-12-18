#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime
from pprint import pformat, pprint
from time import time as time_now

import serial
from serial.tools import list_ports

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from telecortex.config import TeleCortexSessionConfig
from telecortex.graphics import (MAIN_WINDOW, cv2_draw_map,
                                 cv2_setup_main_window, cv2_show_preview,
                                 fill_rainbows, get_frameno, get_square_canvas)
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import MAPS_DOME, MAPS_GOGGLE
from telecortex.session import (DEFAULT_BAUD, TEENSY_VID, TelecortexSession,
                                find_serial_dev)
from telecortex.util import pix_array2text

TARGET_FRAMERATE = 20
ANIM_SPEED = 10
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0


def main():
    """
    Main.

    Enumerate serial ports
    Select board by pid/vid
    Rend some perpendicular rainbowz
    Respond to microcontroller
    """

    telecortex.graphics.IMG_SIZE = 64
    telecortex.graphics.DOT_RADIUS = 1

    conf = TeleCortexSessionConfig(
        name="interpolate_opencv",
        description="draw interpolated maps using opencv",
        default_config='dome_overhead'
    )

    conf.parser.add_argument('--serial-dev',)
    conf.parser.add_argument('--serial-baud', default=DEFAULT_BAUD)
    conf.parser.add_argument('--enable-preview', default=False,
                             action='store_true')

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

    # img = cv2.imread(
    #     '/Users/derwent/Documents/GitHub/touch_dome/Images/test_image.jpg',
    #     cv2.IMREAD_COLOR)
    img = get_square_canvas()

    if conf.args.enable_preview:
        cv2_setup_main_window(img)

    with serial.Serial(
        port=target_device, baudrate=DEFAULT_BAUD, timeout=1
    ) as ser:
        sesh = conf.setup_session(ser)

        while sesh:
            frameno = get_frameno()
            fill_rainbows(img, frameno)

            if conf.args.config == 'goggles':
                pixel_list_goggle = interpolate_pixel_map(
                    img, MAPS_GOGGLE['goggle'], INTERPOLATION_TYPE
                )
                pixel_str_goggle = pix_array2text(*pixel_list_goggle)
            else:
                pixel_list_smol = interpolate_pixel_map(
                    img, MAPS_DOME['smol'], INTERPOLATION_TYPE
                )
                pixel_list_big = interpolate_pixel_map(
                    img, MAPS_DOME['big'], INTERPOLATION_TYPE
                )

                pixel_str_smol = pix_array2text(*pixel_list_smol)
                pixel_str_big = pix_array2text(*pixel_list_big)
            for panel, map_name in conf.panels[0]:
                if map_name.startswith('big'):
                    pixel_str = pixel_str_big
                elif map_name.startswith('smol'):
                    pixel_str = pixel_str_smol
                elif map_name.startswith('goggle'):
                    pixel_str = pixel_str_goggle
                sesh.chunk_payload_with_linenum(
                    "M2600", {"Q": panel}, pixel_str)
            sesh.send_cmd_with_linenum("M2610")

            if conf.args.enable_preview:
                if cv2_show_preview(img, MAPS_DOME):
                    break



if __name__ == '__main__':
    main()
