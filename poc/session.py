#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Demonstrate basic session capabilities."""

import itertools
import logging
import os
import sys
from collections import OrderedDict
from datetime import datetime
from time import time as time_now

import serial
from serial.tools import list_ports

import coloredlogs
import numpy as np
from context import telecortex
from telecortex.mapping import PIXEL_MAP_BIG, PIXEL_MAP_SMOL, normalize_pix_map
from telecortex.session import (PANEL_LENGTHS, PANELS, TELECORTEX_BAUD,
                                TELECORTEX_VID, TelecortexSession,
                                TelecortexSessionManager, find_serial_dev)
from telecortex.util import pix_array2text

STREAM_LOG_LEVEL = logging.INFO
# STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.ERROR

IMG_SIZE = 64
MAX_HUE = 360

LOG_FILE = ".sesssion.log"
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

TELECORTEX_DEV = "/dev/tty.usbmodem35"
TARGET_FRAMERATE = 20
ANIM_SPEED = 3

# Pixel mapping from pixel_map_helper.py in touch_dome

INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 0

SERVERS = OrderedDict([
    (0, {'vid': 0x16C0, 'pid': 0x0483, 'ser':'4057530', 'baud':57600}),
    (1, {'vid': 0x16C0, 'pid': 0x0483, 'ser':'4058600', 'baud':57600})
])

def main():
    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())
    manager = TelecortexSessionManager(SERVERS)
    for session in manager.sessions.values():
        for panel in range(len(PANEL_LENGTHS)):
            session.send_cmd_sync("M2602 Q%d V////" % panel)
        session.send_cmd_sync("M2610")


if __name__ == '__main__':
    main()
