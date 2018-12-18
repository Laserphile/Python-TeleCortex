#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Demonstrate basic session capabilities."""

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
from telecortex.graphics import (cv2_draw_map, cv2_setup_main_window,
                                 cv2_show_preview, fill_rainbows, get_frameno,
                                 get_square_canvas)
from telecortex.interpolation import interpolate_pixel_map
from telecortex.manage import TelecortexSessionManager
from telecortex.mapping import (PIXEL_MAP_BIG, PIXEL_MAP_SMOL,
                                normalize_pix_map, rotate_mapping,
                                rotate_vector, scale_mapping,
                                transpose_mapping)
from telecortex.util import pix_array2text

MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0

def main():
    telecortex.graphics.IMG_SIZE = 100
    telecortex.graphics.DOT_RADIUS = 1

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

    pixel_map_cache = OrderedDict()

    pixel_map_cache['smol'] = normalize_pix_map(PIXEL_MAP_SMOL)
    pixel_map_cache['big'] = normalize_pix_map(PIXEL_MAP_BIG)

    img = get_square_canvas()

    if conf.args.enable_preview:
        cv2_setup_main_window(img)

    manager = conf.setup_manager()

    while manager:
        frameno = get_frameno()
        fill_rainbows(img, frameno)

        pixel_list_smol = interpolate_pixel_map(
            img, pixel_map_cache['smol'], INTERPOLATION_TYPE
        )
        pixel_list_big = interpolate_pixel_map(
            img, pixel_map_cache['big'], INTERPOLATION_TYPE
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
            if cv2_show_preview(img, pixel_map_cache):
                break


if __name__ == '__main__':
    main()
