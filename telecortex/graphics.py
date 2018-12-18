"""Various utilities for graphics tasks."""

import colorsys
import math
import itertools
from time import time as time_now

import cv2
import numpy as np

IMG_SIZE = 64
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5

start_time = time_now()

def get_frameno():
    return int(
        (time_now() - start_time) * TARGET_FRAMERATE * ANIM_SPEED
    ) % MAX_ANGLE

def fill_rainbows(image, angle=0.0):
    """
    Given an openCV image, fill with ranbows.

    - `angle` is the hue offset
    """
    size = image.shape[0]
    for col in range(size):
        hue = (
            col * MAX_HUE / size + angle * MAX_HUE / MAX_ANGLE
        ) % MAX_HUE
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        cv2.line(image, (col, 0), (col, size), color=rgb, thickness=1)
    return image

def direct_rainbows(pix_map, angle=0.):
    pixel_list = []
    for coordinate in pix_map:
        magnitude = math.sqrt(
            (0.5 - coordinate[0]) ** 2 +
            (0.5 - coordinate[1]) ** 2
        )
        hue = (
            magnitude * MAX_HUE + angle * MAX_HUE / MAX_ANGLE
        ) % MAX_HUE
        rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        pixel_list.append(rgb)

    # logging.debug("pixel_list: %s" % pformat(pixel_list))
    pixel_list = list(itertools.chain(*pixel_list))
    # logging.debug("pixel_list returned: %s ... " % (pixel_list[:10]))
    return pixel_list

def get_square_canvas(size=None):
    if size is None:
        size = IMG_SIZE
    return np.ndarray(shape=(size, size, 3), dtype=np.uint8)
