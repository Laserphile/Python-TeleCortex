
import colorsys
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
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import (PANELS, PANELS_PER_CONTROLLER, PIXEL_MAP_BIG, PIXEL_MAP_SMOL, PIXEL_MAP_OUTER, PIXEL_MAP_OUTER_FLIP,
                                draw_map, normalize_pix_map, rotate_mapping,
                                rotate_vector, scale_mapping,
                                transpose_mapping)
from telecortex.session import (DEFAULT_BAUD, DEFAULT_TIMEOUT,
                                PANEL_LENGTHS, TelecortexSession,
                                TelecortexSessionManager,
                                TelecortexThreadManager)
from telecortex.session import SERVERS_DOME as SERVERS
from telecortex.util import pix_array2text
from telecortex.mapping import MAPS_DOME, transform_panel_map
from telecortex.config import TeleCortexConfig

ENABLE_PREVIEW = True

IMG_SIZE = 128
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 2
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 1
INTERLEAVE = False
VIDEO_FILE = "/Users/derwent/Movies/dome animations/BOKK (loop).mov"

def main():

    conf = TeleCortexConfig(
        name="parallel_video",
        description="draw a video file spanning several telecortex controllers in parallel",
        default_config='dome_overhead'
    )

    conf.parse_args()

    manager = TelecortexThreadManager(conf.servers)

    cap = cv2.VideoCapture(VIDEO_FILE)
    ret, img = cap.read()

    if ENABLE_PREVIEW:
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

        cv2.imshow(MAIN_WINDOW, np.array(img))

        for server_id, server_panel_info in PANELS.items():
            if not manager.session_active(server_id):
                continue
            for panel_number, size, scale, angle, offset in server_panel_info:
                if (server_id, panel_number) not in pixel_map_cache.keys():
                    if size not in MAPS_DOME:
                        raise UserWarning('Panel size %s not in known mappings: %s' %(
                            size, MAPS_DOME.keys()
                        ))
                    panel_map = MAPS_DOME[size]
                    panel_map = transform_panel_map(panel_map, size, scale, angle, offset)

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
                    "M2600", {"Q":panel_number}, pixel_str
                )

        if INTERLEAVE:
            for panel_number in range(PANELS_PER_CONTROLLER):
                for server_id in PANELS.keys():
                    panel_map = pixel_map_cache.get((server_id, panel_number))
                    if not panel_map:
                        continue

                    pixel_list = interpolate_pixel_map(
                        img, panel_map, INTERPOLATION_TYPE
                    )
                    pixel_str = pix_array2text(*pixel_list)

                    manager.chunk_payload_with_linenum(
                        server_id,
                        "M2600", {"Q":panel_number}, pixel_str
                    )

        while not manager.all_idle:
            logging.debug("waiting on queue")

        for server_id in manager.threads.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)


        if ENABLE_PREVIEW:
            for panel_map in pixel_map_cache.values():
                draw_map(img, panel_map, DOT_RADIUS + 1, outline=(255, 255, 255))
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

        ret, img = cap.read()


if __name__ == '__main__':
    main()
