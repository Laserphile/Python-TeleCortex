#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
from collections import OrderedDict
from datetime import datetime
from time import time as time_now
from pprint import pformat

import coloredlogs
import cv2
import numpy as np
from mss import mss
# noinspection PyUnresolvedReferences
from context import telecortex
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import (PIXEL_MAP_BIG, PIXEL_MAP_SMOL, PANELS,
                                normalize_pix_map, rotate_mapping, scale_mapping, rotate_vector,
                                transpose_mapping, draw_map)
from telecortex.mapping import MAPS_DOME, transform_panel_map
from telecortex.session import SERVERS, TelecortexSessionManager
from telecortex.util import pix_array2text
from telecortex.config import TeleCortexConfig

IMG_SIZE = 64
MAX_HUE = 1.0
MAX_ANGLE = 360

ENABLE_PREVIEW = True

TELECORTEX_DEV = "/dev/tty.usbmodem35"
TARGET_FRAMERATE = 20
ANIM_SPEED = 10
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 3

# viewport definition
MON = {'top': 200, 'left': 200, 'width': 400, 'height': 400}

def main():
    """
    Main.

    Enumerate serial ports
    Select board by pid/vid
    Rend some perpendicular rainbowz
    Respond to microcontroller
    """

    conf = TeleCortexConfig(
        name="hams",
        description="take the output of the screen and draw on several telecortex controllers",
        default_config='dome_overhead'
    )

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    manager = TelecortexSessionManager(SERVERS)

    sct = mss()

    img = np.array(sct.grab(MON))

    if ENABLE_PREVIEW:
        window_flags = 0
        window_flags |= cv2.WINDOW_NORMAL
        # window_flags |= cv2.WINDOW_AUTOSIZE
        # window_flags |= cv2.WINDOW_FREERATIO
        window_flags |= cv2.WINDOW_KEEPRATIO

        cv2.namedWindow(MAIN_WINDOW, flags=window_flags)
        cv2.moveWindow(MAIN_WINDOW, 500, 0)
        cv2.imshow(MAIN_WINDOW, img)
        key = cv2.waitKey(2) & 0xFF

    pixel_map_cache = OrderedDict()

    start_time = time_now()

    while any([manager.sessions.get(server_id) for server_id in PANELS]):

        img = np.array(sct.grab(MON))

        cv2.imshow(MAIN_WINDOW, np.array(img))

        for server_id, server_panel_info in PANELS.items():
            if not manager.sessions.get(server_id):
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
                else:
                    panel_map = pixel_map_cache[(server_id, panel_number)]

                pixel_list = interpolate_pixel_map(
                    img, panel_map, INTERPOLATION_TYPE
                )
                pixel_str = pix_array2text(*pixel_list)

                manager.sessions[server_id].chunk_payload_with_linenum(
                    "M2600", {"Q": panel_number}, pixel_str
                )
            manager.sessions[server_id].send_cmd_with_linenum('M2610')

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


if __name__ == '__main__':
    main()
