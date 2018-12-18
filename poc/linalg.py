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
from telecortex.graphics import (cv2_draw_map, fill_rainbows, get_frameno,
                                 get_square_canvas)
from telecortex.interpolation import interpolate_pixel_map
from telecortex.manage import TelecortexSessionManager
from telecortex.mapping import GENERATOR_DOME_OVERHEAD as PANELS
from telecortex.util import pix_array2text

# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0


def main():

    telecortex.graphics.IMG_SIZE = 128
    telecortex.graphics.DOT_RADIUS = 1

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

    img = get_square_canvas()

    if conf.args.enable_preview:
        cv2_setup_main_window(img)

    manager = conf.setup_manager()

    while manager.any_alive:
        frameno = get_frameno()
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

        if conf.args.enable_preview:
            if cv2_show_preview(img, conf.maps):
                break


if __name__ == '__main__':
    main()
