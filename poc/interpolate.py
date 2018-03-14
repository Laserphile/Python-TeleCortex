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

IMG_SIZE = 512
MAX_HUE = 360

LOG_FILE = ".interpolate.log"
ENABLE_LOG_FILE = True
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
TELECORTEX_VID = 0x16C0
TELECORTEX_BAUD = 57600
PANELS = 4
PANEL_LENGTHS = [
    316, 260, 260, 260
]

# Pixel mapping from pixel_map_helper.py in touch_dome

PIXEL_MAP = np.array([
    [963, 45], [965, 106], [1032, 171], [966, 171], [901, 171], [904, 237],
    [967, 237], [1030, 237], [1094, 302], [1029, 302], [964, 302], [899, 301],
    [834, 301], [773, 364], [838, 364], [902, 364], [967, 364], [1032, 365],
    [1096, 365], [1161, 365], [1224, 429], [1159, 429], [1095, 429],
    [1030, 429], [966, 429], [901, 429], [836, 429], [772, 429], [707, 429],
    [706, 494], [771, 494], [836, 494], [900, 494], [965, 494], [1030, 494],
    [1094, 494], [1159, 494], [1224, 494], [1287, 559], [1222, 559],
    [1158, 559], [1093, 559], [1028, 559], [964, 559], [899, 559], [834, 559],
    [769, 559], [705, 559], [640, 559], [579, 623], [643, 623], [708, 623],
    [772, 624], [836, 624], [901, 624], [965, 624], [1029, 624], [1094, 624],
    [1158, 624], [1222, 625], [1287, 625], [1351, 625], [1353, 690],
    [1288, 690], [1224, 690], [1159, 690], [1095, 690], [1030, 690], [966, 690],
    [901, 689], [836, 689], [772, 689], [707, 689], [643, 689], [578, 689],
    [514, 753], [578, 753], [643, 753], [707, 754], [772, 754], [836, 754],
    [901, 754], [965, 754], [1029, 755], [1094, 755], [1158, 755], [1223, 755],
    [1287, 756], [1352, 756], [1416, 756], [1483, 818], [1418, 818],
    [1354, 818], [1289, 817], [1224, 817], [1160, 817], [1095, 816],
    [1031, 816], [966, 816], [901, 816], [837, 816], [772, 815],
    [708, 815], [643, 815], [578, 814], [514, 814], [449, 814],
    [449, 881], [514, 881], [578, 881], [643, 881], [708, 881],
    [772, 881], [837, 881], [901, 881], [966, 881], [1031, 881],
    [1095, 881], [1160, 881], [1224, 881], [1289, 881], [1354, 881],
    [1418, 881], [1483, 881], [1546, 949], [1482, 949], [1417, 949],
    [1352, 949], [1288, 949], [1224, 949], [1159, 949], [1094, 949],
    [1030, 949], [966, 948], [901, 948], [836, 948], [772, 948],
    [708, 948], [643, 948], [578, 948], [514, 948], [450, 948],
    [385, 948], [323, 1009], [387, 1009], [452, 1009], [516, 1009],
    [580, 1010], [645, 1010], [709, 1010], [773, 1010], [838, 1010],
    [902, 1010], [966, 1010], [1031, 1011], [1095, 1011], [1160, 1011],
    [1224, 1011], [1288, 1011], [1353, 1011], [1417, 1012], [1481, 1012],
    [1546, 1012], [1610, 1012], [1613, 1079], [1548, 1079], [1484, 1078],
    [1419, 1078], [1354, 1078], [1290, 1078], [1225, 1078], [1160, 1077],
    [1095, 1077], [1031, 1077], [966, 1076], [901, 1076], [837, 1076],
    [772, 1076], [707, 1076], [642, 1075], [578, 1075], [513, 1075],
    [448, 1074], [384, 1074], [319, 1074], [256, 1139], [320, 1139],
    [385, 1139], [450, 1139], [514, 1138], [578, 1138], [643, 1138],
    [708, 1138], [772, 1138], [836, 1138], [901, 1138], [966, 1138],
    [1030, 1137], [1094, 1137], [1159, 1137], [1224, 1137], [1288, 1137],
    [1352, 1137], [1417, 1137], [1482, 1136], [1546, 1136], [1610, 1136],
    [1675, 1136], [1739, 1202], [1675, 1202], [1610, 1202], [1546, 1202],
    [1481, 1202], [1417, 1202], [1352, 1202], [1288, 1202], [1223, 1202],
    [1159, 1202], [1094, 1202], [1030, 1202], [966, 1202], [901, 1203],
    [837, 1203], [772, 1203], [708, 1203], [643, 1203], [579, 1203],
    [514, 1203], [450, 1203], [385, 1203], [321, 1203], [256, 1203],
    [192, 1203], [128, 1267], [192, 1267], [257, 1267], [321, 1267],
    [386, 1267], [450, 1267], [515, 1267], [579, 1267], [643, 1267],
    [708, 1267], [772, 1267], [837, 1267], [901, 1267], [966, 1266],
    [1030, 1266], [1094, 1266], [1159, 1266], [1223, 1266], [1288, 1266],
    [1352, 1266], [1416, 1266], [1481, 1266], [1545, 1266], [1610, 1266],
    [1674, 1266], [1739, 1266], [1803, 1266]
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

    if ENABLE_PREVIEW:
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

            if ENABLE_PREVIEW:
                draw_map(test_img, pix_map_normlized)
                tk_img = ImageTk.PhotoImage(test_img)
                tk_panel.configure(image=tk_img)
                tk_panel.image = tk_img
                tk_root.update()

            frameno = (frameno + 5) % MAX_HUE


if __name__ == '__main__':
    main()
