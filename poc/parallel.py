
import argparse
import colorsys
import itertools
import logging
import multiprocessing as mp
import os
import time
from collections import OrderedDict
from pprint import pformat

import serial

import coloredlogs
import cv2
import numpy as np
from context import telecortex
from telecortex.config import TeleCortexThreadManagerConfig
from telecortex.graphics import direct_rainbows, get_frameno
from telecortex.util import pix_array2text


def graphics(manager, conf):
    while manager.any_alive:
        frameno = get_frameno()

        pixel_strs = OrderedDict()

        for size, pix_map_normlized in conf.maps.items():
            pixel_list = direct_rainbows(pix_map_normlized, frameno)
            pixel_strs[size] = pix_array2text(*pixel_list)

        manager.wait_for_workers_idle()

        for server_id, server_panel_info in conf.panels.items():
            if not manager.sessions.get(server_id):
                logging.debug(
                    "server id %s not found in manager sessions: %s" % (
                        server_id, manager.sessions.keys(),
                    )
                )
                continue
            for panel_number, size in server_panel_info:
                if conf.args.do_single:
                    pixel_str = pix_array2text(
                        frameno, 255, 127
                    )
                    manager.chunk_payload_with_linenum(
                        server_id,
                        "M2603", {"Q": panel_number}, pixel_str
                    )
                else:
                    assert size in pixel_strs, \
                        (
                            "Your panel configuration specifies a size %s but "
                            "your map configuration does not contain a "
                            "matching entry, only %s"
                        ) % (
                            size, conf.maps.keys()
                        )
                    pixel_str = pixel_strs.get(size)
                    if not pixel_str:
                        logging.warning(
                            "empty pixel_str generated: %s" % pixel_str)
                    # else:
                    #     logging.debug("pixel_str: %s" % pformat(pixel_str))

                    manager.chunk_payload_with_linenum(
                        server_id,
                        "M2600", {"Q": panel_number}, pixel_str
                    )

        for server_id in manager.sessions.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)

def main():

    conf = TeleCortexThreadManagerConfig(
        name="parallel",
        description=(
            "send rainbows to several telecortex controllers in parallel"),
        default_config='dome_simplified'
    )

    conf.parser.add_argument(
        '--do-single', default=False, action='store_true',
        help=(
            "if true, send a single colour to the board, "
            "otherwise send a rainbow string"
        )
    )

    conf.parse_args()

    conf.parser.print_help()

    manager = conf.setup_manager()

    graphics(manager, conf)

if __name__ == '__main__':
    main()
