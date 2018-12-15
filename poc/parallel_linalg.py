
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
from telecortex.graphics import MAX_ANGLE, fill_rainbows
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import PANELS_PER_CONTROLLER, draw_map
from telecortex.util import pix_array2text

TARGET_FRAMERATE = 20
ANIM_SPEED = 2
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 1
INTERLEAVE = False


def main():
    telecortex.graphics.IMG_SIZE = 128

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

    img = np.ndarray(
        shape=(telecortex.graphics.IMG_SIZE, telecortex.graphics.IMG_SIZE, 3),
        dtype=np.uint8)

    if conf.args.enable_preview:
        window_flags = 0
        window_flags |= cv2.WINDOW_NORMAL
        # window_flags |= cv2.WINDOW_AUTOSIZE
        # window_flags |= cv2.WINDOW_FREERATIO
        window_flags |= cv2.WINDOW_KEEPRATIO

        cv2.namedWindow(MAIN_WINDOW, flags=window_flags)
        cv2.moveWindow(MAIN_WINDOW, 900, 0)
        cv2.resizeWindow(MAIN_WINDOW, 700, 700)
        cv2.imshow(MAIN_WINDOW, img)

    pixel_map_cache = OrderedDict()

    start_time = time_now()

    while manager.any_alive:
        frameno = (
            (time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED
        ) % MAX_ANGLE
        fill_rainbows(img, frameno)

        cv2.imshow(MAIN_WINDOW, np.array(img))

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

        while not manager.all_idle:
            logging.debug("waiting on queue")

        for server_id in manager.threads.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)

        if conf.args.enable_preview:
            for panel_map in pixel_map_cache.values():
                draw_map(
                    img, panel_map, DOT_RADIUS + 1, outline=(255, 255, 255))
            for panel_map in pixel_map_cache.values():
                draw_map(img, panel_map, DOT_RADIUS)
            cv2.imshow(MAIN_WINDOW, img)
            if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 0:
                key = cv2.waitKey(2) & 0xFF
                if key == 27:
                    cv2.destroyAllWindows()
                    break
                elif key == ord('d'):
                    import pudb
                    pudb.set_trace()


if __name__ == '__main__':
    main()
