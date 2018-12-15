"""Various utilities for graphics tasks."""

import colorsys

import cv2

IMG_SIZE = 64
MAX_HUE = 1.0
MAX_ANGLE = 360

def fill_rainbows(image, angle=0.0):
    """
    Given an openCV image, fill with ranbows.

    - `angle` is the hue offset
    """
    for col in range(IMG_SIZE):
        hue = (
            col * MAX_HUE / IMG_SIZE + angle * MAX_HUE / MAX_ANGLE
        ) % MAX_HUE
        rgb = tuple(c * 255 for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        # logging.debug("rgb: %s" % (rgb,))
        cv2.line(image, (col, 0), (col, IMG_SIZE), color=rgb, thickness=1)
    return image
