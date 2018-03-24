
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
from telecortex.session import (DEFAULT_BAUDRATE, DEFAULT_TIMEOUT,
                                PANEL_LENGTHS, TelecortexSession, SERVERS)
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import (PIXEL_MAP_BIG, PIXEL_MAP_SMOL, PANELS,
                                normalize_pix_map, rotate_mapping, scale_mapping, rotate_vector,
                                transpose_mapping, draw_map)
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
        'file': '/dev/cu.usbmodem3176951',
        'baud': 57600,
        'timeout': 1
    }),
    (1, {
        'file': '/dev/cu.usbmodem4057531',
        'baud': 57600,
        'timeout': 1
    }),
    (2, {
        'file': '/dev/cu.usbmodem4057541',
        'baud': 57600,
        'timeout': 1
    }),
    (3, {
        'file': '/dev/cu.usbmodem4058601',
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
        # (0, 'big'),
        (1, 'smol'),
        # (2, 'smol'),
        # (3, 'smol')
    ])
])

def controller_thread(serial_conf, pipe):
    # setup serial device
    ser = serial.Serial(
        port=serial_conf['file'],
        baudrate=serial_conf['baud'],
        timeout=serial_conf['timeout']
    )
    logging.debug("setting up serial sesh: %s" % ser)
    sesh = TelecortexSession(ser)
    sesh.reset_board()
    # listen for commands
    while sesh:
        cmd, args, payload = pipe.recv()
        logging.debug("received: %s" % str((cmd, args, payload)))
        sesh.chunk_payload_with_linenum(cmd, args, payload)

class TelecortexThreadManager(object):
    # TODO: this
    def __init__(self, servers):
        self.servers = servers
        self.threads = OrderedDict()
        self.refresh_connections()

    def refresh_connections(self):
        ctx = mp.get_context('spawn')

        for server_id, serial_conf in SERVERS.items():
            parent_conn, child_conn = ctx.Pipe()

            proc = ctx.Process(
                target=controller_thread,
                args=(serial_conf, child_conn),
                name="controller_%s" % server_id
            )
            proc.start()
            self.threads[server_id] = (parent_conn, proc)

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
        cv2.imshow(MAIN_WINDOW, img)

    start_time = time_now()

    while manager:
        frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % MAX_ANGLE
        fill_rainbows(img, frameno)

        pixel_list_smol = interpolate_pixel_map(
            img, pix_map_normlized_smol, INTERPOLATION_TYPE
        )
        pixel_list_big = interpolate_pixel_map(
            img, pix_map_normlized_big, INTERPOLATION_TYPE
        )
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

                manager.threads[server_id][0].send(("M2600", {"Q":panel_number}, pixel_str))

        for server_id, (pipe, proc) in manager.threads.items():
            pipe.send(("M2610", None, None))

        frameno = (frameno + 1) % 255

if __name__ == '__main__':
    main()
