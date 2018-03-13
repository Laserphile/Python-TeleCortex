#!/usr/bin/env python
# -*- coding: utf-8 -*-

import itertools
import logging
import os
import tkinter as tk
from datetime import datetime
from math import floor, ceil
from pprint import pformat, pprint

import serial
from serial.tools import list_ports

import coloredlogs
import numpy as np
from PIL import Image, ImageColor, ImageTk
from PIL.ImageDraw import ImageDraw
from telecortex_session import TelecortexSession
from telecortex_utils import pix_array2text

STREAM_LOG_LEVEL = logging.INFO
# STREAM_LOG_LEVEL = logging.WARN
# STREAM_LOG_LEVEL = logging.DEBUG

ENABLE_LOG_FILE = True

IMG_SIZE = 512
MAX_HUE = 360

LOG_FILE = ".interpolate.log"
ENABLE_LOG_FILE = False

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
TELECORTEX_VID = 0x16C0
TELECORTEX_BAUD = 57600
PANELS = 4
PANEL_LENGTHS = [
    316, 260, 260, 260
]

# Pixel mapping from pixel_map_helper.py in touch_dome

PIXEL_MAP = np.array([
    [ 966,   45],
    [ 965,  109],
    [1031,  174],
    [ 965,  173],
    [ 899,  172],
    [ 903,  239],
    [ 968,  238],
    [1032,  236],
    [1096,  302],
    [1031,  302],
    [ 966,  302],
    [ 900,  301],
    [ 835,  301],
    [ 773,  366],
    [ 838,  366],
    [ 902,  367],
    [ 966,  367],
    [1031,  367],
    [1096,  368],
    [1160,  368],
    [1224,  430],
    [1159,  430],
    [1094,  430],
    [1029,  430],
    [ 964,  430],
    [ 900,  429],
    [ 835,  429],
    [ 770,  429],
    [ 705,  429],
    [ 706,  494],
    [ 771,  494],
    [ 835,  494],
    [ 900,  495],
    [ 964,  495],
    [1029,  495],
    [1094,  496],
    [1158,  496],
    [1223,  496],
    [1289,  559],
    [1224,  559],
    [1160,  558],
    [1095,  558],
    [1031,  558],
    [ 966,  558],
    [ 901,  557],
    [ 837,  557],
    [ 772,  557],
    [ 708,  556],
    [ 643,  556],
    [ 577,  624],
    [ 642,  624],
    [ 707,  624],
    [ 772,  624],
    [ 837,  624],
    [ 902,  624],
    [ 967,  624],
    [1032,  624],
    [1097,  624],
    [1162,  624],
    [1227,  624],
    [1292,  624],
    [1357,  624],
    [1355,  688],
    [1290,  688],
    [1226,  688],
    [1161,  688],
    [1097,  688],
    [1032,  688],
    [ 968,  688],
    [ 903,  689],
    [ 838,  689],
    [ 774,  689],
    [ 709,  689],
    [ 645,  689],
    [ 580,  689],
    [ 517,  758],
    [ 581,  758],
    [ 646,  757],
    [ 710,  757],
    [ 775,  756],
    [ 839,  756],
    [ 904,  755],
    [ 968,  755],
    [1032,  755],
    [1097,  754],
    [1161,  754],
    [1226,  753],
    [1290,  753],
    [1355,  752],
    [1419,  752],
    [1480,  818],
    [1416,  818],
    [1351,  818],
    [1287,  818],
    [1223,  818],
    [1158,  818],
    [1094,  818],
    [1030,  818],
    [ 966,  818],
    [ 901,  817],
    [ 837,  817],
    [ 773,  817],
    [ 708,  817],
    [ 644,  817],
    [ 580,  817],
    [ 515,  817],
    [ 451,  817],
    [ 452,  884],
    [ 516,  884],
    [ 581,  884],
    [ 645,  883],
    [ 709,  883],
    [ 774,  883],
    [ 838,  883],
    [ 902,  883],
    [ 966,  882],
    [1031,  882],
    [1095,  882],
    [1159,  882],
    [1224,  882],
    [1288,  882],
    [1352,  881],
    [1417,  881],
    [1481,  881],
    [1545,  947],
    [1480,  947],
    [1416,  947],
    [1351,  947],
    [1287,  947],
    [1222,  947],
    [1158,  947],
    [1093,  947],
    [1029,  947],
    [ 964,  947],
    [ 899,  947],
    [ 835,  947],
    [ 770,  947],
    [ 706,  947],
    [ 641,  947],
    [ 577,  947],
    [ 512,  947],
    [ 448,  947],
    [ 383,  947],
    [ 320, 1011],
    [ 384, 1011],
    [ 449, 1011],
    [ 513, 1011],
    [ 578, 1011],
    [ 642, 1012],
    [ 707, 1012],
    [ 771, 1012],
    [ 836, 1012],
    [ 900, 1012],
    [ 964, 1012],
    [1029, 1012],
    [1093, 1012],
    [1158, 1012],
    [1222, 1012],
    [1287, 1012],
    [1351, 1013],
    [1416, 1013],
    [1480, 1013],
    [1545, 1013],
    [1609, 1013],
    [1612, 1074],
    [1548, 1074],
    [1483, 1074],
    [1419, 1074],
    [1354, 1074],
    [1290, 1074],
    [1226, 1074],
    [1161, 1074],
    [1097, 1074],
    [1032, 1074],
    [ 968, 1074],
    [ 904, 1075],
    [ 839, 1075],
    [ 775, 1075],
    [ 710, 1075],
    [ 646, 1075],
    [ 582, 1075],
    [ 517, 1075],
    [ 453, 1075],
    [ 388, 1075],
    [ 324, 1075],
])

DOT_RADIUS = 1

def normalize_pix_map(pix_map):
    """
    Return a normalized copy of `pixel map` so that ∀(x, y); x, y ∈ [0,1]
    """

    normalized = pix_map.astype(np.float64)

    pix_min_x = normalized.min(0)[0]
    pix_max_x = normalized.max(0)[0]
    pix_min_y = normalized.min(1)[0]
    pix_max_y = normalized.max(1)[0]
    pix_breadth_x = pix_max_x - pix_min_x
    pix_breadth_y = pix_max_y - pix_min_y
    pix_breadth_max = max(pix_breadth_x, pix_breadth_y)

    logging.debug(
        "mins: (%4d, %4d), maxs: (%4d, %4d), breadth: (%4d, %4d)" % (
            pix_min_x, pix_min_y, pix_max_x, pix_max_y,
            pix_breadth_x, pix_breadth_y
        )
    )

    normalized[..., [0, 1]] -= [pix_min_x, pix_min_y]
    normalized *= (1/pix_breadth_max)

    # TODO: probably need to centre this somehow

    return normalized


def fill_rainbows(image, angle=0):
    draw_api = ImageDraw(image)
    for col in range(IMG_SIZE):
        hue = (col * MAX_HUE / IMG_SIZE + angle) % MAX_HUE
        colour_string = "hsl(%d, 100%%, 50%%)" % (hue)
        # logging.warning("colour_string: %s" % colour_string)
        rgb = ImageColor.getrgb(colour_string)
        # logging.warning("rgb: %s" % (rgb,))
        draw_api.line([(col, 0), (col, IMG_SIZE)], fill=rgb)

def draw_map(test_img, pix_map_normlized):
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
        draw_api.ellipse([coordinate_from, coordinate_to], outline=(0, 0, 0))

def blend_pixel(pixel_a, pixel_b, coefficient):
    return (
        int(np.interp(coefficient, [0, 1], [pixel_a[0], pixel_b[0]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[1], pixel_b[1]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[2], pixel_b[2]])),
    )


def interpolate_pixel(image, coordinates):
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


def interpolate_pixel_map(image, pix_map_normalized):
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
    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    target_device = TELECORTEX_DEV
    for port_info in list_ports.comports():
        if port_info.vid == TELECORTEX_VID:
            logging.info("found target device: %s" % port_info.device)
            target_device = port_info.device
            break
    if not target_device:
        raise UserWarning("target device not found")

    pix_map_normlized = normalize_pix_map(PIXEL_MAP)
    logging.info("pix_map_normlized:\n %s" % pformat(pix_map_normlized))

    test_img = Image.new('RGB', (IMG_SIZE, IMG_SIZE))

    tk_root = tk.Tk()
    tk_img = ImageTk.PhotoImage(test_img)
    tk_panel = tk.Label(tk_root, image=tk_img)
    tk_panel.pack(side="bottom", fill="both", expand="yes")

    frameno = 0
    with serial.Serial(
        port=target_device, baudrate=TELECORTEX_BAUD, timeout=1
    ) as ser:
        sesh = TelecortexSession(ser)
        sesh.reset_board()

        while sesh:
            fill_rainbows(test_img, frameno)

            pixel_list = interpolate_pixel_map(test_img, pix_map_normlized)
            pixel_str = pix_array2text(*pixel_list)
            for panel in range(PANELS):
                sesh.chunk_payload("M2600", "Q%d" % panel, pixel_str)
            sesh.send_cmd_sync("M2610")

            draw_map(test_img, pix_map_normlized)
            tk_img = ImageTk.PhotoImage(test_img)
            tk_panel.configure(image=tk_img)
            tk_panel.image = tk_img
            tk_root.update()

            frameno = (frameno + 5) % MAX_HUE


if __name__ == '__main__':
    main()
