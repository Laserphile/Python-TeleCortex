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

import coloredlogs
import serial

import serial_asyncio
import six
# from serial import aio as serial_aio
from context import telecortex
from telecortex.config import TeleCortexAsyncManagerConfig
from telecortex.manage import TeleCortexBaseManager
from telecortex.session import TelecortexSerialProtocol
from telecortex.util import pix_array2text

assert sys.version_info > (3, 7), (
    "must be running Python 3.7 or later to use asyncio")


async def graphics(conf, server_id, cmd_queue):
    # Frame number used for animations
    frameno = 0
    while True:
        for panel in range(4):
            logging.debug("putting M2603")
            pixel_str = pix_array2text(
                frameno, 255, 127
            )
            await cmd_queue.put(
                ("M2603", {"Q": panel}, pixel_str)
            )
        await cmd_queue.put(
            ("M2610", None, None)
        )
        await asyncio.sleep(0.01)

        # increment frame number
        frameno = (frameno + 1) % 255


def main():
    logging.getLogger('asyncio').setLevel(logging.DEBUG)

    conf = TeleCortexAsyncManagerConfig(
        name="async",
        description=(
            "Asynchronous Management of Telecortex Controllers"),
        default_config='dome_overhead',
        graphics=graphics
    )

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    start_time = time_now()

    manager = conf.setup_manager()

    manager.loop.run_forever()
    manager.loop.close()


if __name__ == '__main__':
    main()
