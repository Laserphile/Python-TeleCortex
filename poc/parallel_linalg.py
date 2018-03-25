
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
from telecortex.mapping import (PANELS, PIXEL_MAP_BIG, PIXEL_MAP_SMOL,
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
ENABLE_PREVIEW = False

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

IMG_SIZE = 256
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 1

SERVERS = OrderedDict([
    (0, {
        'file': '/dev/cu.usbmodem4057531',
        'baud': 57600,
        'timeout': 1
    }),
    (1, {
        'file': '/dev/cu.usbmodem4058601',
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
        'file': '/dev/cu.usbmodem4058621',
        'baud': 57600,
        'timeout': 1
    }),
])

# Uncomment for Derwent config
# SERVERS = OrderedDict([
#     (1, {
#         'file': '/dev/cu.usbmodem144101',
#         'baud': 57600,
#         'timeout': 1
#     }),
# ])

def fill_rainbows(image, angle=0.0):
    for col in range(IMG_SIZE):
        hue = (col * MAX_HUE / IMG_SIZE + angle * MAX_HUE / MAX_ANGLE ) % MAX_HUE
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        cv2.line(image, (col, 0), (col, IMG_SIZE), color=rgb, thickness=1)
    return image

def main():

    manager = TelecortexThreadManager(SERVERS)

    pix_map_normlized_smol = normalize_pix_map(PIXEL_MAP_SMOL)
    pix_map_normlized_big = normalize_pix_map(PIXEL_MAP_BIG)

    img = np.ndarray(shape=(IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)

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
        frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % MAX_ANGLE
        fill_rainbows(img, frameno)

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
                    else:
                        raise UserWarning('Panel not a know dimension')
                    panel_map = transpose_mapping(panel_map, (-0.5, -0.5))
                    panel_map = scale_mapping(panel_map, scale)
                    panel_map = rotate_mapping(panel_map, angle)
                    panel_map = transpose_mapping(panel_map, (+0.5, +0.5))
                    panel_map = transpose_mapping(panel_map, offset)
                    pixel_map_cache[(server_id, panel_number)] = panel_map
                else:
                    panel_map = pixel_map_cache[(server_id, panel_number)]

                pixel_list = interpolate_pixel_map(
                    img, panel_map, INTERPOLATION_TYPE
                )
                pixel_str = pix_array2text(*pixel_list)

                # logging.debug("sending panel %s pixel str %s" % (panel_number, pixel_str))

                manager.threads[server_id][0].send(("M2600", {"Q":panel_number}, pixel_str))

        if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 1:
            for server_id, (pipe, proc) in manager.threads.items():
                while proc.is_alive() and pipe.poll():
                    logging.debug("waiting on pipe %s" % server_id)
                    pipe.recv()

        for server_id, (pipe, proc) in manager.threads.items():
            pipe.send(("M2610", None, None))

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
