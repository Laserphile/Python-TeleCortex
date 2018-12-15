
import itertools
import json
import logging
import multiprocessing as mp
import os
import re
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
from telecortex.config import TeleCortexThreadManagerConfig
from telecortex.session import DEFAULT_BAUD, DEFAULT_TIMEOUT, PANEL_LENGTHS
from telecortex.session import SERVERS_BLANK as SERVERS
from telecortex.util import pix_array2text

TARGET_FRAMERATE = 20
ANIM_SPEED = 2
MAIN_WINDOW = 'image_window'
# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
DOT_RADIUS = 1
INTERLEAVE = False

# TODO: put this in config
GCODE_FILE = "BOKK.gcode"

RE_GCODE_LINE = "(?P<server_id>\d+): (?P<cmd>\S+), (?P<args>.*), (?P<payload>\S+)"

def main():

    conf = TeleCortexThreadManagerConfig(
        name="parallel_gcode_player",
        description=(
            "play a gcode file to several telecortex controllers in parallel"),
        default_config='dome_overhead'
    )

    conf.parse_args()

    manager = conf.setup_manager()

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
            # TODO: manager.wait_for_workers_idle()

            while not manager.all_idle:
                logging.debug("waiting on queue")


if __name__ == '__main__':
    main()
