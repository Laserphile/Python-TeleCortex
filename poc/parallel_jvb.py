import colorsys
import itertools
import logging
import math
import os
import random
import time
from collections import OrderedDict
from time import time as time_now
import coloredlogs
from cortex_drivers import PanelDriver
# noinspection PyUnresolvedReferences
from context import telecortex
from telecortex.mapping import (normalize_pix_map, MAPS_DOME_SIMPLIFIED)
from telecortex.util import pix_array2text
from telecortex.config import TeleCortexThreadManagerConfig

IMG_SIZE = 256
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
# ANIM_SPEED = 5
# Note: animation speed is set in cortex_drivers for this script.
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
        hue = (magnitude * MAX_HUE + angle * MAX_HUE / MAX_ANGLE) % MAX_HUE
        rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        pixel_list.append(rgb)

    # logging.debug("pixel_list: %s" % pformat(pixel_list))
    pixel_list = list(itertools.chain(*pixel_list))
    # logging.debug("pixel_list returned: %s ... " % (pixel_list[:10]))
    return pixel_list

def main():
    conf = TeleCortexThreadManagerConfig(
        name="parallel_jvb",
        description="send fucked up rainbow circles to several telecortex controllers in parallel",
        default_config='dome_simplified'
    )

    conf.parse_args()

    conf.parser.print_help()

    pix_map_normlized_smol = MAPS_DOME_SIMPLIFIED['smol']
    pix_map_normlized_big = MAPS_DOME_SIMPLIFIED['big']

    frameno = 0
    seed = random.random() * 50
    start_time = time_now()
    five_minutes = 60 * 5

    manager = conf.setup_manager()

    while manager.any_alive:
        frameno += 1
        if frameno > 2 ** 16 or (start_time - time_now() > five_minutes):
            frameno = 0
            seed = random.random()

        driver = PanelDriver(pix_map_normlized_smol, pix_map_normlized_big, IMG_SIZE, MAX_HUE, MAX_ANGLE)

        pixel_list_smol, pixel_list_big = driver.crazy_rainbows(frameno, seed)
        pixel_str_smol = pix_array2text(*pixel_list_smol)
        pixel_str_big = pix_array2text(*pixel_list_big)
        for server_id, server_panel_info in conf.panels.items():
            if not manager.sessions.get(server_id):
                continue
            for panel_number, map_name in server_panel_info:
                size = map_name.split('-')[0]
                if size == 'big':
                    pixel_str = pixel_str_big
                elif size == 'smol':
                    pixel_str = pixel_str_smol
                else:
                    raise UserWarning('panel size unknown')

                manager.chunk_payload_with_linenum(
                    server_id,
                    "M2600", {"Q": panel_number}, pixel_str
                )

        manager.wait_for_workers_idle()

        for server_id in manager.sessions.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)


if __name__ == '__main__':
    main()
