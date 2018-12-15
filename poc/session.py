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
from telecortex.config import TeleCortexManagerConfig
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import (PIXEL_MAP_BIG, PIXEL_MAP_SMOL, draw_map,
                                normalize_pix_map, rotate_mapping,
                                rotate_vector, scale_mapping,
                                transpose_mapping)
from telecortex.session import TelecortexSessionManager
from telecortex.util import pix_array2text

# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.ERROR

LOG_FILE = ".sesssion.log"
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

IMG_SIZE = 64
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0


def fill_rainbows(image, angle=0.0):
    """
    Given an openCV image, fill with ranbows.

    - `angle` is the hue offset
    """
    for col in range(IMG_SIZE):
        hue = (
            col * MAX_HUE / IMG_SIZE + angle * MAX_HUE / MAX_ANGLE
        ) % MAX_HUE
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        cv2.line(image, (col, 0), (col, IMG_SIZE), color=rgb, thickness=1)
    return image


def main():
    conf = TeleCortexManagerConfig(
        name="session",
        description=(
            "draw a single rainbow spanning onto telecortex controllers"),
        default_config='dome_overhead'
    )

    conf.parser.add_argument('--enable-preview', default=False,
                             action='store_true')

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    pix_map_normlized_smol = normalize_pix_map(PIXEL_MAP_SMOL)
    pix_map_normlized_big = normalize_pix_map(PIXEL_MAP_BIG)

    img = np.ndarray(shape=(IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)

    if conf.args.enable_preview:
        window_flags = 0
        window_flags |= cv2.WINDOW_NORMAL
        # window_flags |= cv2.WINDOW_AUTOSIZE
        # window_flags |= cv2.WINDOW_FREERATIO
        window_flags |= cv2.WINDOW_KEEPRATIO

        cv2.namedWindow(MAIN_WINDOW, flags=window_flags)
        cv2.imshow(MAIN_WINDOW, img)

        cv2.moveWindow(MAIN_WINDOW, 500, 0)
        key = cv2.waitKey(2) & 0xFF

    start_time = time_now()

    manager = conf.setup_manager()

    while any([manager.sessions.get(server_id) for server_id in conf.panels]):
        frameno = (
            (time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED
        ) % MAX_ANGLE
        fill_rainbows(img, frameno)

        pixel_list_smol = interpolate_pixel_map(
            img, pix_map_normlized_smol, INTERPOLATION_TYPE
        )
        pixel_list_big = interpolate_pixel_map(
            img, pix_map_normlized_big, INTERPOLATION_TYPE
        )
        pixel_str_smol = pix_array2text(*pixel_list_smol)
        pixel_str_big = pix_array2text(*pixel_list_big)
        for server_id, server_panel_info in conf.panels.items():
            if not manager.sessions.get(server_id):
                continue
            for panel_number, panel_name in server_panel_info:
                if panel_name.startswith('big'):
                    pixel_str = pixel_str_big
                elif panel_name.startswith('smol'):
                    pixel_str = pixel_str_smol

                manager.sessions[server_id].chunk_payload_with_linenum(
                    "M2600", {"Q": panel_number}, pixel_str
                )
            manager.sessions[server_id].send_cmd_with_linenum('M2610')

        if conf.args.enable_preview:
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
