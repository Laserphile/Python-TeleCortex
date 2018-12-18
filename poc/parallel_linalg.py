
import itertools
import logging
import multiprocessing as mp
import os
import sys
from collections import OrderedDict
from datetime import datetime
from time import time as time_now

import serial

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from mss import mss
from telecortex.config import TeleCortexThreadManagerConfig
from telecortex.graphics import (MAIN_WINDOW, cv2_draw_map,
                                 cv2_setup_main_window, cv2_show_preview,
                                 fill_rainbows, get_frameno, get_square_canvas)
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import PANELS_PER_CONTROLLER
from telecortex.util import pix_array2text

# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
INTERLEAVE = False


def main():
    telecortex.graphics.IMG_SIZE = 128
    telecortex.graphics.DOT_RADIUS = 1

    conf = TeleCortexThreadManagerConfig(
        name="parallel_linalg",
        description=(
            "draw a single rainbow spanning several telecortex controllers "
            "in parallel"),
        default_config='dome_overhead'
    )
    conf.parser.add_argument('--enable-preview', default=False,
                             action='store_true')

    conf.parse_args()

    manager = conf.setup_manager()

    img = get_square_canvas()

    if conf.args.enable_preview:
        cv2_setup_main_window(img)

    pixel_map_cache = OrderedDict()

    while manager.any_alive:
        frameno = get_frameno()
        fill_rainbows(img, frameno)

        for server_id, server_panel_info in conf.panels.items():
            if not manager.threads.get(server_id):
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

                if INTERLEAVE:
                    continue
                panel_map = pixel_map_cache.get((server_id, panel_number))

                pixel_list = interpolate_pixel_map(
                    img, panel_map, INTERPOLATION_TYPE
                )
                pixel_str = pix_array2text(*pixel_list)
                manager.chunk_payload_with_linenum(
                    server_id,
                    "M2600", {"Q": panel_number}, pixel_str
                )

        if INTERLEAVE:
            for panel_number in range(PANELS_PER_CONTROLLER):
                for server_id in conf.panels.keys():
                    panel_map = pixel_map_cache.get((server_id, panel_number))
                    if not panel_map:
                        continue

                    pixel_list = interpolate_pixel_map(
                        img, panel_map, INTERPOLATION_TYPE
                    )
                    pixel_str = pix_array2text(*pixel_list)

                    manager.chunk_payload_with_linenum(
                        server_id,
                        "M2600", {"Q": panel_number}, pixel_str
                    )

        manager.wait_for_workers_idle()

        for server_id in manager.threads.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)

        if conf.args.enable_preview:
            if cv2_show_preview(img, pixel_map_cache):
                break


if __name__ == '__main__':
    main()
