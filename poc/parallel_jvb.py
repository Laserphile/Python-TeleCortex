import logging
import os
from collections import OrderedDict
from time import time as time_now
import coloredlogs
from cortex_drivers import PanelDriver
from context import telecortex
from telecortex.session import (TelecortexThreadManager)
from telecortex.mapping import (PIXEL_MAP_BIG, PIXEL_MAP_SMOL, normalize_pix_map)
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
DOT_RADIUS = 0

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

PANELS = OrderedDict([
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


def main():
    manager = TelecortexThreadManager(SERVERS)

    pix_map_normlized_smol = normalize_pix_map(PIXEL_MAP_SMOL)
    pix_map_normlized_big = normalize_pix_map(PIXEL_MAP_BIG)

    start_time = time_now()

    while manager:
        frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % MAX_ANGLE

        driver = PanelDriver(pix_map_normlized_smol, pix_map_normlized_big, IMG_SIZE, MAX_HUE, MAX_ANGLE)

        pixel_list_smol, pixel_list_big = driver.direct_rainbows(frameno)

        pixel_str_smol = pix_array2text(*pixel_list_smol)
        pixel_str_big = pix_array2text(*pixel_list_big)
        for server_id, server_panel_info in PANELS.items():
            if not manager.threads.get(server_id):
                continue
            for panel_number, size in server_panel_info:
                if size == 'big':
                    pixel_str = pixel_str_big
                elif size == 'smol':
                    pixel_str = pixel_str_smol
                else:
                    raise UserWarning('panel size unknown')

                manager.threads[server_id][0].send(("M2600", {"Q": panel_number}, pixel_str))

        for server_id, (pipe, proc) in manager.threads.items():
            pipe.send(("M2610", None, None))


if __name__ == '__main__':
    main()
