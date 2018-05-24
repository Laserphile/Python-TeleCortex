
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

# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.ERROR

LOG_FILE = ".parallel.log"
ENABLE_LOG_FILE = True

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
LOGGER.addHandler(STREAM_HANDLER)

IMG_SIZE = 256
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0

SERVERS_DOME = OrderedDict([
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

SERVERS_DERWENT = OrderedDict([
    (0, {
        'file': '/dev/cu.usbmodem3176931',
        'baud': 57600,
        'timeout': 1
    }),
])

MAPS_DOME = OrderedDict([
    ('smol', normalize_pix_map(PIXEL_MAP_DOME_SMOL)),
    ('big', normalize_pix_map(PIXEL_MAP_DOME_BIG))
])

PIXEL_MAP_GOGGLE = PIXEL_MAP_SMOL = np.array(
    [
        [-1, -1]
    ] * 16 + [
        [1, 1]
    ] * 16
)

MAPS_DERWENT = OrderedDict([
    ('goggle', normalize_pix_map(PIXEL_MAP_GOGGLE))
])

PANELS_DOME = OrderedDict([
    (0, [
        (0, 'big'),
        (1, 'smol'),
        (2, 'smol'),
        (3, 'smol')
    ]),
    (1, [
        (0, 'big'),
        (1, 'smol'),
        (2, 'smol'),
        (3, 'smol')
    ]),
    (2, [
        (0, 'big'),
        (1, 'smol'),
        (2, 'smol'),
        (3, 'smol')
    ]),
    (3, [
        (0, 'big'),
        (1, 'smol'),
        (2, 'smol'),
        (3, 'smol')
    ]),
    (4, [
        (0, 'big'),
        (1, 'smol'),
        (2, 'smol'),
        (3, 'smol')
    ])
])

PANELS_DERWENT = OrderedDict([
    (0, [
        (0, 'goggle'),
        # (1, 'goggle'),
        # (2, 'goggle'),
        # (3, 'goggle'),
    ])
])


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

    parser = argparse.ArgumentParser(
        description="send rainbows to several telecortex controllers in parallel",
    )
    parser.add_argument('--verbose', '-v', action='count', default=1)
    parser.add_argument('--verbosity', action='store', dest='verbose', type=int)
    parser.add_argument('--quiet', '-q', action='store_const', const=0, dest='verbose')
    parser.add_argument('--enable-log', default=ENABLE_LOG_FILE)
    parser.add_argument('--disable-log', action='store_false', dest='enable_log')
    parser.add_argument('--config', choices=['derwent'] )


    args = parser.parse_args()

    log_level = 50 - 10 * args.verbose

    STREAM_HANDLER.setLevel(log_level)

    if args.enable_log:
        LOGGER.addHandler(FILE_HANDLER)

    server_config = {
        'derwent': SERVERS_DERWENT
    }.get(args.config, SERVERS_DOME)

    map_config = {
        'derwent': MAPS_DERWENT
    }.get(args.config, MAPS_DOME)

    panel_config = {
        'derwent': PANELS_DERWENT
    }.get(args.config, PANELS_DOME)

    logging.debug("server_config:\n%s" % pformat(server_config))
    logging.debug("map_config:\n%s" % pformat(map_config))
    logging.debug("panel_config:\n%s" % pformat(panel_config))

    manager = TelecortexThreadManager(server_config)

    start_time = time_now()

    while manager:
        frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % MAX_ANGLE

        pixel_strs = OrderedDict()

        for size, pix_map_normlized in map_config.items():
            pixel_list = direct_rainbows(pix_map_normlized, frameno)
            pixel_strs[size] = pix_array2text(*pixel_list)

        for server_id, server_panel_info in panel_config.items():
            if not manager.threads.get(server_id):
                logging.debug("server id %s not found in manager threads: %s" % (
                    server_id, manager.threads.keys(),
                ))
                continue
            for panel_number, size in server_panel_info:
                assert size in pixel_strs, \
                    "Your panel configuration specifies a size %s but your map configuration does not contain a matching entry, only %s" % (
                        size, map_config.keys()
                    )
                pixel_str = pixel_strs.get(size)
                if not pixel_str:
                    logging.warning("empty pixel_str generated: %s" % pixel_str)
                else:
                    logging.debug("pixel_str: %s" % pformat(pixel_str))

                manager.chunk_payload_with_linenum(
                    server_id,
                    "M2600", {"Q":panel_number}, pixel_str
                )

        while not manager.all_idle:
            logging.debug("waiting on queue")
            time.sleep(0.1)

        for server_id in manager.threads.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)

        frameno = (frameno + 1) % 255

if __name__ == '__main__':
    main()
