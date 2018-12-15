#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import tkinter as tk
from datetime import datetime
from pprint import pformat, pprint
from time import time as time_now

import serial
from serial.tools import list_ports

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from PIL import Image, ImageColor, ImageTk
from PIL.ImageDraw import ImageDraw
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import MAPS_DOME, MAPS_GOGGLE
from telecortex.session import (DEFAULT_BAUD, TEENSY_VID, TelecortexSession,
                                find_serial_dev)
from telecortex.util import pix_array2text
from telecortex.config import TeleCortexSessionConfig


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

    # test_img = cv2.imread(
    #     '/Users/derwent/Documents/GitHub/touch_dome/Images/test_image.jpg',
    #     cv2.IMREAD_COLOR)
    test_img = np.ndarray(
        shape=(telecortex.graphics.IMG_SIZE, telecortex.graphics.IMG_SIZE, 3),
        dtype=np.uint8)

    if conf.args.enable_preview:
        window_flags = 0
        window_flags |= cv2.WINDOW_NORMAL
        # window_flags |= cv2.WINDOW_AUTOSIZE
        # window_flags |= cv2.WINDOW_FREERATIO
        window_flags |= cv2.WINDOW_KEEPRATIO

        cv2.namedWindow(MAIN_WINDOW, flags=window_flags)
        cv2.imshow(MAIN_WINDOW, test_img)

    start_time = time_now()
    with serial.Serial(
        port=target_device, baudrate=DEFAULT_BAUD, timeout=1
    ) as ser:
        sesh = conf.setup_session(ser)

        while sesh:
            frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % MAX_ANGLE
            fill_rainbows(test_img, frameno)

            if conf.args.config == 'goggles':
                pixel_list_goggle = interpolate_pixel_map(
                    test_img, MAPS_GOGGLE['goggle'], INTERPOLATION_TYPE
                )
                pixel_str_goggle = pix_array2text(*pixel_list_goggle)
            else:
                pixel_list_smol = interpolate_pixel_map(
                    test_img, MAPS_DOME['smol'], INTERPOLATION_TYPE
                )
                pixel_list_big = interpolate_pixel_map(
                    test_img, MAPS_DOME['big'], INTERPOLATION_TYPE
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
                sesh.chunk_payload_with_linenum("M2600", {"Q": panel}, pixel_str)
            sesh.send_cmd_with_linenum("M2610")

            if conf.args.enable_preview:
                draw_map(test_img, MAPS_DOME['smol'])
                draw_map(test_img, MAPS_DOME['big'], outline=(255, 255, 255))
                cv2.imshow(MAIN_WINDOW, test_img)
            if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 0:
                key = cv2.waitKey(2) & 0xFF
                if key == 27:
                    cv2.destroyAllWindows()
                    break



if __name__ == '__main__':
    main()
