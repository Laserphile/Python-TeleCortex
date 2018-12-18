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
from telecortex.graphics import (MAIN_WINDOW, cv2_draw_map,
                                 cv2_setup_main_window, cv2_show_preview,
                                 fill_rainbows, get_frameno, get_square_canvas)
from telecortex.interpolation import interpolate_pixel_map
from telecortex.manage import TelecortexSessionManager
from telecortex.util import pix_array2text

# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'

def graphics(manager, conf):
    pixel_map_cache = OrderedDict()
    pixel_str_cache = OrderedDict()

    img = get_square_canvas()

    if conf.args.enable_preview:
        cv2_setup_main_window(img)

    while manager.any_alive:
        frameno = get_frameno()
        fill_rainbows(img, frameno)

        for server_id, server_panel_info in conf.panels.items():
            if server_id not in manager.sessions:
                continue
            for panel_number, map_name in server_panel_info:
                if (server_id, panel_number) not in pixel_map_cache.keys():
                    if map_name not in conf.maps:
                        raise UserWarning(
                            'Panel map_name %s not in known mappings: %s' % (
                                map_name, conf.maps.keys()
                            )
                        )
                    panel_map = conf.maps[map_name]

                    pixel_map_cache[(server_id, panel_number)] = panel_map

                panel_map = pixel_map_cache.get((server_id, panel_number))

                pixel_list = interpolate_pixel_map(
                    img, panel_map, INTERPOLATION_TYPE
                )
                pixel_str_cache[(server_id, panel_number)] = \
                    pix_array2text(*pixel_list)

        manager.wait_for_workers_idle()

        for (server_id, panel_number), pixel_str in pixel_str_cache.items():
            manager.chunk_payload_with_linenum(
                server_id,
                "M2600", {"Q": panel_number}, pixel_str
            )
        for server_id, server_panel_info in conf.panels.items():
            if server_id not in manager.sessions:
                continue
            manager.chunk_payload_with_linenum(server_id, 'M2610', None, None)

        if conf.args.enable_preview:
            if cv2_show_preview(img, conf.maps):
                break


def main():

    telecortex.graphics.IMG_SIZE = 128
    telecortex.graphics.DOT_RADIUS = 0

    conf = TeleCortexManagerConfig(
        name="linalg",
        description=(
            "draw a single rainbow spanning several telecortex controllers"),
        default_config='dome_overhead'
    )
    conf.parser.add_argument('--enable-preview', default=False,
                             action='store_true')

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    manager = conf.setup_manager()

    graphics(manager, conf)


if __name__ == '__main__':
    main()
