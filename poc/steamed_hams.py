#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
from collections import OrderedDict
from datetime import datetime
from time import time as time_now

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from mss import mss
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import PIXEL_MAP_BIG, PIXEL_MAP_SMOL, normalize_pix_map
from telecortex.session import SERVERS, TelecortexSessionManager
from telecortex.util import pix_array2text

# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
# STREAM_LOG_LEVEL = logging.WARN
STREAM_LOG_LEVEL = logging.ERROR

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
INTERPOLATION_TYPE = 'bilinear'
# INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 3

def draw_map(image, pix_map_normlized, outline=None):
    """Given an image and a normalized pixel map, draw the map on the image."""
    if outline is None:
        outline = (0, 0, 0)
    for pixel in pix_map_normlized:
        pix_coordinate = (
            int(image.shape[0] * pixel[0]),
            int(image.shape[1] * pixel[1])
        )
        cv2.circle(image, pix_coordinate, DOT_RADIUS, outline, 1)
    return image

MON = {'top': 100, 'left': 0, 'width': 200, 'height': 200}

PANELS = OrderedDict([
    (2, [
        (1, 'smol'),
        (2, 'smol')
    ]),
    (3, [
        (1, 'smol'),
        (2, 'smol'),
        (3, 'smol')
    ])
])

# PANELS = [
#     # (0, 0, 'big'),
#     (2, 1, 'smol'),
#     (2, 2, 'smol'),
#     # (2, 3, 'smol'),
#     (3, 1, 'smol'),
#     (3, 2, 'smol'),
#     (3, 3, 'smol')
# ]

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


    if ENABLE_PREVIEW:
        window_flags = 0
        window_flags |= cv2.WINDOW_NORMAL
        # window_flags |= cv2.WINDOW_AUTOSIZE
        # window_flags |= cv2.WINDOW_FREERATIO
        window_flags |= cv2.WINDOW_KEEPRATIO

        cv2.namedWindow(MAIN_WINDOW, flags=window_flags)

    start_time = time_now()

    while manager:

        img = np.array(sct.grab(MON))

        cv2.imshow(MAIN_WINDOW, np.array(img))

        pixel_list_smol = interpolate_pixel_map(
            img, pix_map_normlized_smol, INTERPOLATION_TYPE
        )
        pixel_list_big = interpolate_pixel_map(
            img, pix_map_normlized_big, INTERPOLATION_TYPE
        )
        pixel_str_smol = pix_array2text(*pixel_list_smol)
        pixel_str_big = pix_array2text(*pixel_list_big)
        for server_id, server_panel_info in PANELS.items():
            for panel_number, size in server_panel_info:
                if size == 'big':
                    pixel_str = pixel_str_big
                elif size == 'smol':
                    pixel_str = pixel_str_smol

                manager.sessions[server_id].chunk_payload(
                    "M2600", "Q%d" % panel_number, pixel_str
                )
            manager.sessions[server_id].send_cmd_sync('M2610')

        if ENABLE_PREVIEW:
            draw_map(img, pix_map_normlized_smol)
            draw_map(img, pix_map_normlized_big, outline=(255, 255, 255))
            cv2.imshow(MAIN_WINDOW, img)
        if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 0:
            key = cv2.waitKey(2) & 0xFF
            if key == 27:
                cv2.destroyAllWindows()
                break



if __name__ == '__main__':
    main()
