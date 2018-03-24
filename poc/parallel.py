import logging
import multiprocessing as mp
import os
from collections import OrderedDict

import coloredlogs
from context import telecortex
from telecortex.session import TelecortexSession

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


def controller_thread(serial_conf, pipe):
    # setup serial device
    sesh = TelecortexSession.from_serial_conf(serial_conf)
    # listen for commands


CONTROLLERS = OrderedDict([
    (1, {
        'file': '/dev/cu.usbmodem144101',
        'baud': 57600,
        'timeout': 1
    })
])

def main():
    ctx = mp.get_context('spawn')

    controller_threads = []

    for controller_id, serial_conf in CONTROLLERS:
        parent_conn, child_conn = ctx.Pipe()
        proc = ctx.Process(
            target=controller_thread,
            args=(serial_conf, child_conn)
        )
        controller_threads.append((parent_conn, proc))


if __name__ == '__main__':
    main()
