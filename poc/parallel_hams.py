
import colorsys
import itertools
import logging
import multiprocessing as mp
import os
from collections import OrderedDict
from time import time as time_now

import serial

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from mss import mss
from telecortex.config import TeleCortexConfig
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import GENERATOR_DOME_OVERHEAD as PANELS
from telecortex.mapping import MAPS_DOME, draw_map, transform_panel_map
from telecortex.session import TelecortexThreadManager
from telecortex.util import pix_array2text

ENABLE_PREVIEW = True

IMG_SIZE = 256
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 3

MON = {'top': 200, 'left': 200, 'width': 400, 'height': 400}

def main():
    conf = TeleCortexConfig(
        name="parallel_hams",
        description="take the output of the screen and draw on several telecortex controllers in parallel",
        default_config='dome_overhead'
    )

    conf.parse_args()

    manager = TelecortexThreadManager(conf.servers)

    sct = mss()

    img = np.array(sct.grab(MON))

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

    while any([manager.threads.get(server_id, (None, None))[1] for server_id in PANELS]):

        img = np.array(sct.grab(MON))

        cv2.imshow(MAIN_WINDOW, np.array(img))

        for server_id, server_panel_info in PANELS.items():
            if not manager.threads.get(server_id):
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

                # logging.debug("sending panel %s pixel str %s" % (panel_number, pixel_str))

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


if __name__ == '__main__':
    main()
