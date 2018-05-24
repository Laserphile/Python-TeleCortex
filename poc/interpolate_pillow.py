#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Demonstrate basic image interpolation using pillow."""

import itertools
import logging
import os
import tkinter as tk
from datetime import datetime
from math import ceil, floor
from time import time as time_now

import serial
from serial.tools import list_ports

import coloredlogs
import numpy as np
from context import telecortex
from PIL import Image, ImageColor, ImageTk
from PIL.ImageDraw import ImageDraw
from telecortex.session import (PANEL_LENGTHS, PANELS, DEFAULT_BAUD,
                                TEENSY_VID, find_serial_dev, TelecortexSession)
from telecortex.util import pix_array2text
from telecortex.mapping import MAPS_DOME
from telecortex.config import TeleCortexConfig


# STREAM_LOG_LEVEL = logging.INFO
STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.DEBUG
# STREAM_LOG_LEVEL = logging.ERROR

IMG_SIZE = 64
MAX_HUE = 360

LOG_FILE = ".interpolate.log"
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


def fill_rainbows(image, angle=0):
    draw_api = ImageDraw(image)
    for col in range(IMG_SIZE):
        hue = (col * MAX_HUE / IMG_SIZE + angle) % MAX_HUE
        colour_string = "hsl(%d, 100%%, 50%%)" % (hue)
        # logging.warning("colour_string: %s" % colour_string)
        rgb = ImageColor.getrgb(colour_string)
        # logging.warning("rgb: %s" % (rgb,))
        draw_api.line([(col, 0), (col, IMG_SIZE)], fill=rgb)


def draw_map(test_img, pix_map_normlized, outline=None):
    if outline is None:
        outline = (0, 0, 0)
    draw_api = ImageDraw(test_img)
    for pixel in pix_map_normlized:
        coordinate_from = (
            int(pixel[0] * IMG_SIZE) - DOT_RADIUS,
            int(pixel[1] * IMG_SIZE) - DOT_RADIUS
        )
        coordinate_to = (
            int(pixel[0] * IMG_SIZE) + DOT_RADIUS,
            int(pixel[1] * IMG_SIZE) + DOT_RADIUS
        )
        draw_api.ellipse([coordinate_from, coordinate_to], outline=outline)


def blend_pixel(pixel_a, pixel_b, coefficient):
    return (
        int(np.interp(coefficient, [0, 1], [pixel_a[0], pixel_b[0]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[1], pixel_b[1]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[2], pixel_b[2]])),
    )


def interpolate_pixel(image, coordinates, interp_type=None):
    if interp_type is None:
        interp_type = 'nearest'

    assert \
        interp_type in ['nearest', 'bilinear'], \
        "unsupported interpolation type: %s" % interp_type

    if interp_type == 'nearest':
        return image.getpixel((
            int(round(coordinates[0])),
            int(round(coordinates[1]))
        ))

    coordinate_floor = (
        int(np.clip(floor(coordinates[0]), 0, image.size[0] - 1)),
        int(np.clip(floor(coordinates[1]), 0, image.size[1] - 1))
    )
    coordinate_ceil = (
        int(np.clip(ceil(coordinates[0]), 0, image.size[0] - 1)),
        int(np.clip(ceil(coordinates[1]), 0, image.size[1] - 1))
    )

    pixel_0 = image.getpixel((
        coordinate_floor[0], coordinate_floor[1]
    ))
    pixel_1 = image.getpixel((
        coordinate_ceil[0], coordinate_floor[1]
    ))
    pixel_2 = image.getpixel((
        coordinate_floor[0], coordinate_ceil[1]
    ))
    pixel_3 = image.getpixel((
        coordinate_ceil[0], coordinate_ceil[1]
    ))
    pix_coefficients = (
        coordinates[0] - coordinate_floor[0],
        coordinates[1] - coordinate_floor[1]
    )
    pixel_4 = blend_pixel(pixel_0, pixel_1, pix_coefficients[0])
    pixel_5 = blend_pixel(pixel_2, pixel_3, pix_coefficients[0])
    return blend_pixel(pixel_4, pixel_5, pix_coefficients[1])


def interpolate_pixel_map(image, pix_map_normalized, interp_type=None):
    """
    Generate a pixel list from an image and a pixel map.

    Given a numpy array image and a normalized pixel map showing the position
    of each pixel, return a list of channel values for each pixel in the map,
    so that it can be encoded and send to the server.
    """
    pixel_list = []
    for pix in pix_map_normalized:
        pix_coordinate = (
            np.clip(image.size[0] * pix[0], 0, image.size[0] - 1),
            np.clip(image.size[1] * pix[1], 0, image.size[1] - 1)
        )
        pixel_value = interpolate_pixel(image, pix_coordinate)
        pixel_list.append(pixel_value)
    # logging.debug("pixel_list: %s" % pformat(pixel_list))
    pixel_list = list(itertools.chain(*pixel_list))
    # logging.debug("pixel_list returned: %s ... " % (pixel_list[:10]))
    return pixel_list


def main():
    """
    Main.

    Enumerate serial ports
    Select board by pid/vid
    Rend some perpendicular rainbowz
    Respond to microcontroller
    """

    conf = TeleCortexConfig(
        name="rainbowz",
        description="send rainbows to a single telecortex controller as fast as possible",
        default_config='single'
    )
    conf.parser.add_argument('--serial-dev',)

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    target_device = conf.args.serial_dev
    if target_device is None:
        target_device = find_serial_dev(TEENSY_VID)
    if not target_device:
        raise UserWarning("target device not found")
    else:
        logging.debug("target_device: %s" % target_device)
        logging.debug("baud: %s" % DEFAULT_BAUD)

    pix_map_normlized_smol = MAPS_DOME['smol']
    pix_map_normlized_big = MAPS_DOME['big']

    test_img = Image.new('RGB', (IMG_SIZE, IMG_SIZE))

    if ENABLE_PREVIEW:
        tk_root = tk.Tk()
        tk_img = ImageTk.PhotoImage(test_img)
        tk_panel = tk.Label(tk_root, image=tk_img)
        tk_panel.pack(side="bottom", fill="both", expand="yes")

    start_time = time_now()
    with serial.Serial(
            port=target_device, baudrate=DEFAULT_BAUD, timeout=1
    ) as ser:
        sesh = TelecortexSession(ser)
        sesh.reset_board()

        while sesh:
            frameno = ((time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED) % 360
            fill_rainbows(test_img, frameno)

            pixel_list_smol = interpolate_pixel_map(
                test_img, pix_map_normlized_smol, INTERPOLATION_TYPE
            )
            pixel_list_big = interpolate_pixel_map(
                test_img, pix_map_normlized_big, INTERPOLATION_TYPE
            )
            pixel_str_smol = pix_array2text(*pixel_list_smol)
            pixel_str_big = pix_array2text(*pixel_list_big)
            for panel in range(PANELS):
                if PANEL_LENGTHS[panel] == max(PANEL_LENGTHS):
                    sesh.chunk_payload_with_linenum("M2600", {"Q": panel}, pixel_str_big)
                if PANEL_LENGTHS[panel] == min(PANEL_LENGTHS):
                    sesh.chunk_payload_with_linenum("M2600", {"Q": panel}, pixel_str_smol)
            sesh.send_cmd_with_linenum("M2610")

            if ENABLE_PREVIEW:
                draw_map(test_img, pix_map_normlized_smol)
                draw_map(test_img, pix_map_normlized_big, outline=(255, 255, 255))
                tk_img = ImageTk.PhotoImage(test_img)
                tk_panel.configure(image=tk_img)
                tk_panel.image = tk_img
                tk_root.update()

            frameno = (frameno + 5) % MAX_HUE


if __name__ == '__main__':
    main()
