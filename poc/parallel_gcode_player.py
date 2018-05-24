
import colorsys
import itertools
import logging
import multiprocessing as mp
import os
import sys
from collections import OrderedDict
from datetime import datetime
from time import time as time_now
import re
import json

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
                                PANEL_LENGTHS, TelecortexSession,
                                TelecortexSessionManager,
                                TelecortexThreadManager)
from telecortex.session import SERVERS_BLANK as SERVERS
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
GCODE_FILE = "BOKK.gcode"

RE_GCODE_LINE = "(?P<server_id>\d+): (?P<cmd>\S+), (?P<args>.*), (?P<payload>\S+)"

def main():

    manager = TelecortexThreadManager(SERVERS)

    with open(GCODE_FILE) as gcode_file:
        while manager.any_alive:
            line = gcode_file.readline()
            try:
                matchdict = re.search(RE_GCODE_LINE, line).groupdict()
            except Exception as exc:
                logging.error("lines does not match: %s" % line)
                raise exc

            server_id = int(matchdict.get('server_id'))
            cmd = matchdict.get('cmd')
            str_args = matchdict.get('args')
            payload = matchdict.get('payload')
            args = json.loads(str_args)

            manager.chunk_payload_with_linenum(
                server_id,
                cmd, args, payload
            )

            while not manager.all_idle:
                logging.debug("waiting on queue")


if __name__ == '__main__':
    main()
