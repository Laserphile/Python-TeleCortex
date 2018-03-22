#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
from collections import OrderedDict
from datetime import datetime
from time import time as time_now
from pprint import pformat

import coloredlogs
import cv2
import numpy as np
from mss import mss
from context import telecortex
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import (PIXEL_MAP_BIG, PIXEL_MAP_SMOL, PANELS,
                                normalize_pix_map, rotate_mapping, scale_mapping, rotate_vector,
                                transpose_mapping, draw_map)
from telecortex.session import SERVERS, TelecortexSessionManager
from telecortex.util import pix_array2text


# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.ERROR

IMG_SIZE = 64
MAX_HUE = 1.0
MAX_ANGLE = 360

LOG_FILE = ".interpolate.log"
ENABLE_LOG_FILE = False
ENABLE_PREVIEW = True

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
TARGET_FRAMERATE = 20
ANIM_SPEED = 10
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 3

MON = {'top': 200, 'left': 200, 'width': 400, 'height': 400}

def main():
    """
    Main.

    Enumerate serial ports
    Select board by pid/vid
    Rend some perpendicular rainbowz
    Respond to microcontroller
    """
    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    manager = TelecortexSessionManager(SERVERS)

    pix_map_normlized_smol = normalize_pix_map(PIXEL_MAP_SMOL)
    pix_map_normlized_big = normalize_pix_map(PIXEL_MAP_BIG)

    # test_img = cv2.imread('/Users/derwent/Documents/GitHub/touch_dome/Images/test_image.jpg', cv2.IMREAD_COLOR)
    # cap = cv2.VideoCapture("/Users/derwent/Desktop/Steamed Hams.mp4")
    # cap = cv2.VideoCapture("/Users/derwent/Desktop/SampleVideo_1280x720_1mb.mp4")
    # test_img = np.ndarray(shape=(IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)

    sct = mss()

    img = np.array(sct.grab(MON))

    if ENABLE_PREVIEW:
        window_flags = 0
        window_flags |= cv2.WINDOW_NORMAL
        # window_flags |= cv2.WINDOW_AUTOSIZE
        # window_flags |= cv2.WINDOW_FREERATIO
        window_flags |= cv2.WINDOW_KEEPRATIO

        cv2.namedWindow(MAIN_WINDOW, flags=window_flags)
        cv2.moveWindow(MAIN_WINDOW, 500, 0)
        cv2.imshow(MAIN_WINDOW, img)
        key = cv2.waitKey(2) & 0xFF

    pixel_map_cache = OrderedDict()

    start_time = time_now()

    while manager:

        img = np.array(sct.grab(MON))

        cv2.imshow(MAIN_WINDOW, np.array(img))

        for server_id, server_panel_info in PANELS.items():
            for panel_number, size, scale, angle, offset in server_panel_info:
                if (server_id, panel_number) not in pixel_map_cache.keys():
                    if size == 'big':
                        map = pix_map_normlized_big
                    elif size == 'smol':
                        map = pix_map_normlized_smol
                    map = transpose_mapping(map, (-0.5, -0.5))
                    map = scale_mapping(map, scale)
                    map = rotate_mapping(map, angle)
                    map = transpose_mapping(map, (+0.5, +0.5))
                    map = transpose_mapping(map, offset)
                    pixel_map_cache[(server_id, panel_number)] = map
                else:
                    map = pixel_map_cache[(server_id, panel_number)]

                pixel_list = interpolate_pixel_map(
                    img, map, INTERPOLATION_TYPE
                )
                pixel_str = pix_array2text(*pixel_list)

                manager.sessions[server_id].chunk_payload(
                    "M2600", "Q%d" % panel_number, pixel_str
                )
            manager.sessions[server_id].send_cmd_sync('M2610')

        if ENABLE_PREVIEW:
            for map in pixel_map_cache.values():
                draw_map(img, map, DOT_RADIUS+1, outline=(255, 255, 255))
            for map in pixel_map_cache.values():
                draw_map(img, map, DOT_RADIUS)
            cv2.imshow(MAIN_WINDOW, img)
            if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 0:
                key = cv2.waitKey(2) & 0xFF
                if key == 27:
                    cv2.destroyAllWindows()
                    break
                elif key == ord('d'):
                    import pudb; pudb.set_trace()

if __name__ == '__main__':
    main()
