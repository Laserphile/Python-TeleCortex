"""Asynchronous implementation of session management."""

import asyncio
import functools
import itertools
import logging
import os
import re
import sys
from asyncio import AbstractEventLoop
from collections import OrderedDict, deque
from datetime import datetime
from time import time as time_now

import serial

import coloredlogs
import serial_asyncio
import six
# from serial import aio as serial_aio
from context import telecortex
from telecortex.config import TeleCortexAsyncManagerConfig
from telecortex.graphics import direct_rainbows, get_frameno
from telecortex.manage import TeleCortexBaseManager
from telecortex.session import TelecortexSerialProtocol
from telecortex.util import pix_array2text

assert sys.version_info > (3, 7), (
    "must be running Python 3.7 or later to use asyncio")


async def graphics(manager, conf):
    # TODO: Rewrite this to take manager instead of server id

    # Frame number used for animations
    frameno = 0
    pixel_strs = {}

    while manager.any_alive:
        frameno = get_frameno()

        pixel_strs = OrderedDict()

        if not conf.args.do_single:
            for size, pix_map_normlized in conf.maps.items():
                pixel_list = direct_rainbows(pix_map_normlized, frameno)
                pixel_strs[size] = pix_array2text(*pixel_list)

        for server_id, server_panel_info in conf.panels.items():
            if server_id not in manager.sesh_coroutines:
                logging.debug(
                    "server id %s not found in manager coroutines: %s" % (
                        server_id, manager.sesh_coroutines.keys(),
                    )
                )
                continue
            if server_id not in manager.cmd_queues:
                logging.debug(
                    "server id %s not found in manager command queues: %s" % (
                        server_id, manager.cmd_queues.keys(),
                    )
                )
                continue

            for panel_number, size in server_panel_info:
                if conf.args.do_single:
                    pixel_str = pix_array2text(
                        frameno, 255, 127
                    )
                    await manager.chunk_payload_with_linenum_async(
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

                    await manager.chunk_payload_with_linenum_async(
                        server_id,
                        "M2600", {"Q": panel_number}, pixel_str
                    )

            logging.debug("gfx %s fn %s" % (server_id, frameno))

            await manager.chunk_payload_with_linenum_async(
                server_id, "M2610", None, None
            )

        await manager.wait_for_workers_idle_async()


def main():
    logging.getLogger('asyncio').setLevel(logging.DEBUG)

    conf = TeleCortexAsyncManagerConfig(
        name="async",
        description=(
            "Asynchronous Management of Telecortex Controllers\n"
            "Recommended buffer size: 1024"),
        default_config='dome_overhead',
        graphics=graphics
    )

    conf.parser.add_argument(
        '--do-single', default=False, action='store_true',
        help=(
            "if true, send a single colour to the board, "
            "otherwise send a rainbow string"
        )
    )

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    manager = conf.setup_manager()

    manager.loop.run_forever()
    manager.loop.close()


if __name__ == '__main__':
    main()
