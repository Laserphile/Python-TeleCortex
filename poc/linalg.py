#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Demonstrate basic session capabilities."""

import colorsys
import itertools
import logging
import os
import sys
from collections import OrderedDict
from datetime import datetime
from time import time as time_now

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import (PIXEL_MAP_BIG, PIXEL_MAP_SMOL,
                                normalize_pix_map, rotate_mapping, scale_mapping,
                                transpose_mapping)
from telecortex.session import SERVERS, TelecortexSessionManager
from telecortex.util import pix_array2text

# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.ERROR

LOG_FILE = ".sesssion.log"
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

IMG_SIZE = 64
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0

PANELS = OrderedDict([
    (0, [
        # (0, 'big'),
        (1, 'smol', 0.5, (1 * 360 / 5)),
        # (2, 'smol'),
        # (3, 'smol')
    ]),
    (1, [
        # (0, 'big'),
        (1, 'smol', 0.5, (2 * 360 / 5)),
        # (2, 'smol'),
        # (3, 'smol')
    ]),
    (2, [
        # (0, 'big'),
        (1, 'smol', 0.5, (3 * 360 / 5)),
        # (2, 'smol'),
        # (3, 'smol')
    ]),
    (3, [
        # (0, 'big'),
        (1, 'smol', 0.5, (4 * 360 / 5)),
        # (2, 'smol'),
        # (3, 'smol')
    ]),
    (4, [
        # (0, 'big'),
        (1, 'smol', 0.5, (0 * 360 / 5)),
        # (2, 'smol'),
        # (3, 'smol')
    ])
])

def fill_rainbows(image, angle=0.0):
    for col in range(IMG_SIZE):
        hue = (col * MAX_HUE / IMG_SIZE + angle * MAX_HUE / MAX_ANGLE ) % MAX_HUE
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        cv2.line(image, (col, 0), (col, IMG_SIZE), color=rgb, thickness=1)
    return image

def draw_map(image, pix_map_normlized, radius=1, outline=None):
    """Given an image and a normalized pixel map, draw the map on the image."""
    if outline is None:
        outline = (0, 0, 0)
    for pixel in pix_map_normlized:
        pix_coordinate = (
            int(image.shape[0] * pixel[0]),
            int(image.shape[1] * pixel[1])
        )
        cv2.circle(image, pix_coordinate, radius, outline, 1)
    return image

def main():
    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    manager = TelecortexSessionManager(SERVERS)

    pix_map_normlized_smol = normalize_pix_map(PIXEL_MAP_SMOL)
    pix_map_normlized_big = normalize_pix_map(PIXEL_MAP_BIG)

    test_img = np.ndarray(shape=(IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)

    if ENABLE_PREVIEW:
        window_flags = 0
        window_flags |= cv2.WINDOW_NORMAL
        # window_flags |= cv2.WINDOW_AUTOSIZE
        # window_flags |= cv2.WINDOW_FREERATIO
        window_flags |= cv2.WINDOW_KEEPRATIO

        cv2.namedWindow(MAIN_WINDOW, flags=window_flags)
        cv2.imshow(MAIN_WINDOW, test_img)

    # pixel_list_smol = interpolate_pixel_map(
    #     test_img, pix_map_normlized_smol, INTERPOLATION_TYPE
    # )
    # pixel_list_big = interpolate_pixel_map(
    #     test_img, pix_map_normlized_big, INTERPOLATION_TYPE
    # )
    # pixel_str_smol = pix_array2text(*pixel_list_smol)
    # pixel_str_big = pix_array2text(*pixel_list_big)

    pixel_map_cache = OrderedDict()

    start_time = time_now()

    while manager:
        frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % MAX_ANGLE
        fill_rainbows(test_img, frameno)

        for server_id, server_panel_info in PANELS.items():
            for panel_number, size, scale, angle in server_panel_info:
                if (server_id, panel_number) not in pixel_map_cache.keys():
                    if size == 'big':
                        map = pix_map_normlized_big
                    elif size == 'smol':
                        map = pix_map_normlized_smol
                    map = transpose_mapping(map, (-0.5, -0.5))
                    map = scale_mapping(map, scale)
                    map = rotate_mapping(map, angle)
                    map = transpose_mapping(map, (+0.5, +0.5))
                    pixel_map_cache[(server_id, panel_number)] = map
                else:
                    map = pixel_map_cache[(server_id, panel_number)]

                pixel_list = interpolate_pixel_map(
                    test_img, map, INTERPOLATION_TYPE
                )
                pixel_str = pix_array2text(*pixel_list)

                manager.sessions[server_id].chunk_payload(
                    "M2600", "Q%d" % panel_number, pixel_str
                )
            # import pudb; pudb.set_trace()
            manager.sessions[server_id].send_cmd_sync('M2610')

        if ENABLE_PREVIEW:
            for map in pixel_map_cache.values():
                draw_map(test_img, map, DOT_RADIUS)
                draw_map(test_img, map, DOT_RADIUS+1, outline=(255, 255, 255))
            cv2.imshow(MAIN_WINDOW, test_img)
            if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 0:
                key = cv2.waitKey(2) & 0xFF
                if key == 27:
                    cv2.destroyAllWindows()
                    break


if __name__ == '__main__':
    main()
