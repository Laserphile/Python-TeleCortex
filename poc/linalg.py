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
                                normalize_pix_map, rotate_mapping, scale_mapping, rotate_vector,
                                transpose_mapping, draw_map)
from telecortex.mapping import GENERATOR_DOME_OVERHEAD as PANELS
from telecortex.mapping import transform_panel_map
from telecortex.session import TelecortexSessionManager
from telecortex.util import pix_array2text
from telecortex.config import TeleCortexManagerConfig

ENABLE_PREVIEW = True

IMG_SIZE = 256
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0

def fill_rainbows(image, angle=0.0):
    for col in range(IMG_SIZE):
        hue = (col * MAX_HUE / IMG_SIZE + angle * MAX_HUE / MAX_ANGLE ) % MAX_HUE
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        cv2.line(image, (col, 0), (col, IMG_SIZE), color=rgb, thickness=1)
    return image

def main():
    conf = TeleCortexManagerConfig(
        name="linalg",
        description="draw a single rainbow spanning several telecortex controllers",
        default_config='dome_overhead'
    )

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    conf.parse_args()

    img = np.ndarray(shape=(IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)

    if ENABLE_PREVIEW:
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

    while any([manager.sessions.get(server_id) for server_id in conf.servers]):
        frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % MAX_ANGLE
        fill_rainbows(img, frameno)

        for server_id, server_panel_info in conf.panels.items():
            if not manager.sessions.get(server_id):
                continue
            for panel_number, map_name in server_panel_info:
                panel_map = conf.maps[map_name]

                pixel_list = interpolate_pixel_map(
                    img, panel_map, INTERPOLATION_TYPE
                )
                pixel_str = pix_array2text(*pixel_list)

                manager.sessions[server_id].chunk_payload_with_linenum(
                    "M2600", {"Q": panel_number}, pixel_str
                )
            # import pudb; pudb.set_trace()
            manager.sessions[server_id].send_cmd_with_linenum('M2610')

        if ENABLE_PREVIEW:
            for map_name, mapping in conf.maps.items():
                draw_map(img, mapping, DOT_RADIUS+1, outline=(255, 255, 255))
            for map_name, mapping in conf.maps.items():
                draw_map(img, mapping, DOT_RADIUS)
            cv2.imshow(MAIN_WINDOW, img)
            if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 0:
                key = cv2.waitKey(2) & 0xFF
                if key == 27:
                    cv2.destroyAllWindows()
                    break


if __name__ == '__main__':
    main()
