
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
from telecortex.session import (DEFAULT_BAUDRATE, DEFAULT_TIMEOUT,
                                PANEL_LENGTHS, SERVERS, TelecortexSession,
                                TelecortexSessionManager,
                                TelecortexThreadManager)
from telecortex.util import pix_array2text

# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.ERROR

LOG_FILE = ".parallel.log"
ENABLE_LOG_FILE = False
ENABLE_PREVIEW = True

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)
FILE_HANDLER = logging.FileHandler(LOG_FILE)
FILE_HANDLER.setLevel(logging.DEBUG)
STREAM_HANDLER = logging.StreamHandler()
STREAM_HANDLER.setLevel(STREAM_LOG_LEVEL)
if os.name != 'nt':
    STREAM_HANDLER.setFormatter(coloredlogs.ColoredFormatter())
STREAM_HANDLER.addFilter(coloredlogs.HostNameFilter())
STREAM_HANDLER.addFilter(coloredlogs.ProgramNameFilter())
if ENABLE_LOG_FILE:
    LOGGER.addHandler(FILE_HANDLER)
LOGGER.addHandler(STREAM_HANDLER)

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

SERVERS = OrderedDict([
    (0, {
        'file': '/dev/cu.usbmodem4057531',
        'baud': 57600,
        'timeout': 1
    }),
    (1, {
        'file': '/dev/cu.usbmodem4058621',
        'baud': 57600,
        'timeout': 1
    }),
    (2, {
        'file': '/dev/cu.usbmodem3176951',
        'baud': 57600,
        'timeout': 1
    }),
    (3, {
        'file': '/dev/cu.usbmodem4057541',
        'baud': 57600,
        'timeout': 1
    }),
    (4, {
        'file': '/dev/cu.usbmodem4058601',
        'baud': 57600,
        'timeout': 1
    }),
])

def main():

    manager = TelecortexThreadManager(SERVERS)

    pix_map_normlized_smol = normalize_pix_map(PIXEL_MAP_SMOL)
    pix_map_normlized_big = normalize_pix_map(PIXEL_MAP_BIG)
    pix_map_normlized_outer = normalize_pix_map(PIXEL_MAP_OUTER)
    pix_map_normlized_outer_flip = normalize_pix_map(PIXEL_MAP_OUTER_FLIP)

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

    while any([manager.threads.get(server_id)[1] for server_id in PANELS]):

        cv2.imshow(MAIN_WINDOW, np.array(img))

        for server_id, server_panel_info in PANELS.items():
            if not manager.threads.get(server_id):
                continue
            for panel_number, size, scale, angle, offset in server_panel_info:
                if (server_id, panel_number) not in pixel_map_cache.keys():
                    if size == 'big':
                        panel_map = pix_map_normlized_big
                    elif size == 'smol':
                        panel_map = pix_map_normlized_smol
                    elif size == 'outer':
                        panel_map = pix_map_normlized_outer
                    elif size == 'outer_flip':
                        panel_map = pix_map_normlized_outer_flip
                    else:
                        raise UserWarning('Panel not a know dimension')
                    panel_map = transpose_mapping(panel_map, (-0.5, -0.5))
                    panel_map = scale_mapping(panel_map, scale)
                    panel_map = rotate_mapping(panel_map, angle)
                    panel_map = transpose_mapping(panel_map, (+0.5, +0.5))
                    panel_map = transpose_mapping(panel_map, offset)
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
