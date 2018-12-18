"""Various utilities for graphics tasks."""

import colorsys
import math
import itertools
from time import time as time_now
from context import telecortex
from telecortex.mapping import denormalize_coordinate

import cv2
import numpy as np

IMG_SIZE = 64
MAX_HUE = 1.0
MAX_ANGLE = 360
TARGET_FRAMERATE = 20
ANIM_SPEED = 5
MAIN_WINDOW = 'image_window'
DOT_RADIUS = 3


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


def cv2_draw_map(img, pix_map_normlized, radius=1, outline=None):
    """Given an image and a normalized pixel map, draw the map on the image."""
    if outline is None:
        outline = (0, 0, 0)
    for pixel in pix_map_normlized:
        pix_coordinate = denormalize_coordinate(img.shape, pixel)
        pix_coordinate = (
            int(pix_coordinate[0]),
            int(pix_coordinate[1])
        )
        cv2.circle(img, pix_coordinate, radius, outline, 1)
    return img

def cv2_setup_main_window(img):
    """
    Create the main window using the background image provided.
    """
    window_flags = 0
    window_flags |= cv2.WINDOW_NORMAL
    # window_flags |= cv2.WINDOW_AUTOSIZE
    # window_flags |= cv2.WINDOW_FREERATIO
    window_flags |= cv2.WINDOW_KEEPRATIO

    cv2.namedWindow(MAIN_WINDOW, flags=window_flags)
    cv2.moveWindow(MAIN_WINDOW, 900, 0)
    cv2.resizeWindow(MAIN_WINDOW, 700, 700)
    cv2.imshow(MAIN_WINDOW, img)


def cv2_show_preview(img, maps):
    """
    Draw the maps on img, wait to detect keypresses.
    """
    for panel_map in maps.values():
        cv2_draw_map(img, panel_map, DOT_RADIUS + 1, outline=(255, 255, 255))
    for panel_map in maps.values():
        cv2_draw_map(img, panel_map, DOT_RADIUS)
    cv2.imshow(MAIN_WINDOW, img)
    if int(time_now() * TARGET_FRAMERATE / 2) % 2 == 0:
        key = cv2.waitKey(2) & 0xFF
        if key == 27:
            cv2.destroyAllWindows()
            return True
        elif key == ord('d'):
            import pudb
            pudb.set_trace()
    return False
