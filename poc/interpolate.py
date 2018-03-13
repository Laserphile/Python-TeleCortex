#!/usr/bin/env python
# -*- coding: utf-8 -*-

import itertools
import logging
import os
from datetime import datetime
from pprint import pformat, pprint
from math import floor
import numpy as np

import serial
from serial.tools import list_ports

import coloredlogs
from PIL import Image, ImageColor
from PIL.ImageDraw import ImageDraw
from telecortex_session import TelecortexSession
from telecortex_utils import pix_array2text

STREAM_LOG_LEVEL = logging.WARN
STREAM_LOG_LEVEL = logging.DEBUG

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
    [1912,  137],
    [1913,  284],
    [1778,  422],
    [1910,  420],
    [2042,  419],
    [1774,  566],
    [1906,  566],
    [2038,  567],
    [1648,  697],
    [1778,  698],
    [1907,  698],
    [2036,  699],
    [2166,  700],
    [1653,  824],
    [1781,  827],
    [1910,  830],
    [2038,  832],
    [2166,  835],
    [1527,  955],
    [1652,  956],
    [1777,  957],
    [1902,  958],
    [2028,  958],
    [2153,  959],
    [2278,  960],
    [1529, 1081],
    [1653, 1082],
    [1778, 1083],
    [1902, 1084],
    [2026, 1086],
    [2151, 1087],
    [2275, 1088],
    [1406, 1207],
    [1530, 1207],
    [1653, 1208],
    [1776, 1208],
    [1900, 1208],
    [2024, 1209],
    [2147, 1209],
    [2270, 1210],
    [2394, 1210],
    [1288, 1327],
    [1410, 1327],
    [1533, 1328],
    [1656, 1328],
    [1778, 1329],
    [1900, 1329],
    [2023, 1329],
    [2146, 1330],
    [2268, 1330],
    [2390, 1331],
    [2513, 1331],
    [1290, 1444],
    [1411, 1445],
    [1532, 1445],
    [1654, 1446],
    [1775, 1446],
    [1896, 1447],
    [2017, 1448],
    [2138, 1448],
    [2260, 1449],
    [2381, 1449],
    [2502, 1450],
    [1175, 1568],
    [1295, 1568],
    [1415, 1568],
    [1534, 1568],
    [1654, 1567],
    [1774, 1567],
    [1894, 1567],
    [2014, 1567],
    [2134, 1567],
    [2254, 1566],
    [2373, 1566],
    [2493, 1566],
    [2613, 1566]
])


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

def blend_pixel(pixel_a, pixel_b, coefficient):
    return (
        int(np.interp(coefficient, [0, 1], [pixel_a[0], pixel_b[0]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[1], pixel_b[1]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[2], pixel_b[2]])),
    )


def interpolate_pixel(image, coordinates):
    coordinate_floor = tuple(map(floor, coordinates))

    pixel_0 = image.getpixel((
        coordinate_floor[0], coordinate_floor[1]
    ))
    pixel_1 = image.getpixel((
        coordinate_floor[0] + 1, coordinate_floor[1]
    ))
    pixel_2 = image.getpixel((
        coordinate_floor[0], coordinate_floor[1] + 1
    ))
    pixel_3 = image.getpixel((
        coordinate_floor[0] + 1, coordinate_floor[1] + 1
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
            image.size[0] * pix[0],
            image.size[1] * pix[1]
        )
        pixel_value = interpolate_pixel(image, pix_coordinate)
        pixel_list.append(pixel_value)
    # logging.debug("pixel_list: %s" % pformat(pixel_list))
    return list(itertools.chain(*pixel_list))


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
            frameno = (frameno + 1) % MAX_HUE

if __name__ == '__main__':
    main()
