
import argparse
import colorsys
import itertools
import logging
import math
import multiprocessing as mp
import os
import time
from collections import OrderedDict
from pprint import pformat
from time import time as time_now

import serial

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import PIXEL_MAP_BIG as PIXEL_MAP_DOME_BIG
from telecortex.mapping import PIXEL_MAP_SMOL as PIXEL_MAP_DOME_SMOL
from telecortex.mapping import (draw_map, normalize_pix_map, rotate_mapping,
                                rotate_vector, scale_mapping,
                                transpose_mapping)
from telecortex.session import TelecortexSession, TelecortexThreadManager
from telecortex.util import pix_array2text
from telecortex.config import TeleCortexThreadManagerConfig

MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 1
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0

def direct_rainbows(pix_map, angle=0.):
    pixel_list = []
    for coordinate in pix_map:
        magnitude = math.sqrt(
            (0.5 - coordinate[0]) ** 2 +
            (0.5 - coordinate[1]) ** 2
        )
        hue = (magnitude * MAX_HUE + angle * MAX_HUE / MAX_ANGLE ) % MAX_HUE
        rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        pixel_list.append(rgb)

    # logging.debug("pixel_list: %s" % pformat(pixel_list))
    pixel_list = list(itertools.chain(*pixel_list))
    # logging.debug("pixel_list returned: %s ... " % (pixel_list[:10]))
    return pixel_list

def main():

    conf = TeleCortexThreadManagerConfig(
        name="parallel",
        description=(
            "send rainbows to several telecortex controllers in parallel"),
        default_config='dome_simplified'
    )

    conf.parse_args()

    conf.parser.print_help()

    manager = conf.setup_manager()

    start_time = time_now()

    while manager.any_alive:
        frameno = (
            (time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED
        ) % MAX_ANGLE

        pixel_strs = OrderedDict()

        for size, pix_map_normlized in conf.maps.items():
            pixel_list = direct_rainbows(pix_map_normlized, frameno)
            pixel_strs[size] = pix_array2text(*pixel_list)

        for server_id, server_panel_info in conf.panels.items():
            if not manager.threads.get(server_id):
                logging.debug(
                    "server id %s not found in manager threads: %s" % (
                        server_id, manager.threads.keys(),
                    )
                )
                continue
            for panel_number, size in server_panel_info:
                assert size in pixel_strs, \
                    (
                        "Your panel configuration specifies a size %s but your"
                        " map configuration does not contain a matching "
                        "entry, only %s"
                    ) % (
                        size, conf.maps.keys()
                    )
                pixel_str = pixel_strs.get(size)
                if not pixel_str:
                    logging.warning(
                        "empty pixel_str generated: %s" % pixel_str)
                # else:
                #     logging.debug("pixel_str: %s" % pformat(pixel_str))

                manager.chunk_payload_with_linenum(
                    server_id,
                    "M2600", {"Q": panel_number}, pixel_str
                )

        manager.wait_for_workers()

        for server_id in manager.threads.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)

        frameno = (frameno + 1) % 255

if __name__ == '__main__':
    main()
