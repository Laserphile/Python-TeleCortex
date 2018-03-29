import cv2
import colorsys
import itertools
import logging
import math
from pprint import pformat


def log_if_correct_level(logging_level, message):
    if logging.getLogger().getEffectiveLevel() == logging_level:
        logging.debug(message)


class PanelDriver(object):

    def __init__(self, pix_map_normlized_smol, pix_map_normlized_big, img_size, max_hue, max_angle):
        self.pix_map_normlized_smol = pix_map_normlized_smol
        self.pix_map_normlized_big = pix_map_normlized_big
        self.img_size = img_size
        self.max_hue = max_hue
        self.max_angle = max_angle

    def direct_rainbows(self, angle=0.):
        pixel_list_smol = self.calc_direct_rainbows(angle, self.pix_map_normlized_smol)
        pixel_list_big = self.calc_direct_rainbows(angle, self.pix_map_normlized_big)

        # log_if_correct_level(logging.DEBUG, "pixel_list returned: %s ... " % (pixel_list_smol[:10]))
        # log_if_correct_level(logging.DEBUG, "pixel_list returned: %s ... " % (pixel_list_big[:10]))
        return pixel_list_smol, pixel_list_big

    def calc_direct_rainbows(self, angle, pix_map_normlized):
        pixel_list = []
        for coordinate in pix_map_normlized:
            magnitude = math.sqrt(
                (0.5 - coordinate[0]) ** 2 +
                (0.5 - coordinate[1]) ** 2
            )
            hue = (magnitude * self.max_hue + angle * self.max_hue / self.max_angle) % self.max_hue
            rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1, 1))
            # log_if_correct_level(logging.DEBUG, "rgb: %s" % (rgb,))
            pixel_list.append(rgb)
        # log_if_correct_level(logging.DEBUG, "pixel_list: %s" % pformat(pixel_list))
        return list(itertools.chain(*pixel_list))
