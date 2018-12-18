
import argparse
import colorsys
import itertools
import logging
import multiprocessing as mp
import os
import time
from collections import OrderedDict
from pprint import pformat

import coloredlogs
import cv2
import numpy as np
import serial

from context import telecortex
from telecortex.config import TeleCortexThreadManagerConfig
from telecortex.graphics import direct_rainbows, get_frameno
from telecortex.util import pix_array2text


def main():

    conf = TeleCortexThreadManagerConfig(
        name="parallel",
        description=(
            "send rainbows to several telecortex controllers in parallel"),
        default_config='dome_simplified'
    )

    conf.parse_args()

    conf.parser.print_help()

    manager = conf.setup_manager()

    while manager.any_alive:
        frameno = get_frameno()

        pixel_strs = OrderedDict()

        for size, pix_map_normlized in conf.maps.items():
            pixel_list = direct_rainbows(pix_map_normlized, frameno)
            pixel_strs[size] = pix_array2text(*pixel_list)

        for server_id, server_panel_info in conf.panels.items():
            if not manager.threads.get(server_id):
                logging.debug(
                    "server id %s not found in manager threads: %s" % (
                        server_id, manager.threads.keys(),
                    )
                )
                continue
            for panel_number, size in server_panel_info:
                assert size in pixel_strs, \
                    (
                        "Your panel configuration specifies a size %s but your"
                        " map configuration does not contain a matching "
                        "entry, only %s"
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

        manager.wait_for_workers_idle()

        for server_id in manager.threads.keys():
            manager.chunk_payload_with_linenum(server_id, "M2610", None, None)

if __name__ == '__main__':
    main()
