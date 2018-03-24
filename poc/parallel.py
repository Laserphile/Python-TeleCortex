import itertools
import logging
import multiprocessing as mp
import os
from collections import OrderedDict

import serial

import coloredlogs
from context import telecortex
from telecortex.session import (DEFAULT_BAUDRATE, DEFAULT_TIMEOUT,
                                PANEL_LENGTHS, PANELS, TelecortexSession)
from telecortex.util import pix_array2text

STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.INFO
# STREAM_LOG_LEVEL = logging.WARN
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

class TelecortexParallelSessionManager(object):
    # TODO: this
    pass


SERVERS = OrderedDict([
    (1, {
        'file': '/dev/cu.usbmodem144101',
        'baud': 57600,
        'timeout': 1
    })
])

def main():
    ctx = mp.get_context('spawn')

    controller_threads = OrderedDict()

    for server_id, serial_conf in SERVERS.items():
        parent_conn, child_conn = ctx.Pipe()

        proc = ctx.Process(
            target=controller_thread,
            args=(serial_conf, child_conn),
            name="controller_%s" % server_id
        )
        proc.start()
        controller_threads[server_id] = (parent_conn, proc)

    logging.debug("created connections")

    frameno = 0

    while True:
        for server_id, (pipe, proc) in controller_threads.items():
            for panel in range(PANELS):
                panel_length = PANEL_LENGTHS[panel]
                pixel_list = [
                    [(frameno + pixel) % 256, 255, 127]
                    for pixel in range(panel_length)
                ]
                pixel_str = pix_array2text
                pixel_list = list(itertools.chain(*pixel_list))
                pixel_str = pix_array2text(*pixel_list)
                logging.debug("sending M2601 on panel %s" % panel)
                pipe.send(("M2601", {"Q":panel}, pixel_str))

        for server_id, (pipe, proc) in controller_threads.items():
            pipe.send(("M2610", None, None))

        frameno = (frameno + 1) % 255

if __name__ == '__main__':
    main()
