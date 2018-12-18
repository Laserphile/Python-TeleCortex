
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
from linalg import graphics
from mss import mss
from telecortex.config import TeleCortexThreadManagerConfig
from telecortex.graphics import (MAIN_WINDOW, cv2_draw_map,
                                 cv2_setup_main_window, cv2_show_preview,
                                 fill_rainbows, get_frameno, get_square_canvas)
from telecortex.interpolation import interpolate_pixel_map
from telecortex.mapping import PANELS_PER_CONTROLLER
from telecortex.util import pix_array2text

# INTERPOLATION_TYPE = 'bilinear'
INTERPOLATION_TYPE = 'nearest'
INTERLEAVE = False


def main():
    telecortex.graphics.IMG_SIZE = 128
    telecortex.graphics.DOT_RADIUS = 1

    conf = TeleCortexThreadManagerConfig(
        name="parallel_linalg",
        description=(
            "draw a single rainbow spanning several telecortex controllers "
            "in parallel"),
        default_config='dome_overhead'
    )
    conf.parser.add_argument('--enable-preview', default=False,
                             action='store_true')

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    manager = conf.setup_manager()

    graphics(manager, conf)


if __name__ == '__main__':
    main()
