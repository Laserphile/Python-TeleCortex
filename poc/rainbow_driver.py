import cv2
import colorsys
import itertools
import logging
import math
from pprint import pformat


class PanelDriver(object):

    def __init__(self, pix_map_normlized_smol, pix_map_normlized_big, img_size, max_hue, max_angle):
        self.pix_map_normlized_smol = pix_map_normlized_smol
        self.pix_map_normlized_big = pix_map_normlized_big
        self.img_size = img_size
        self.max_hue = max_hue
        self.max_angle = max_angle

    def direct_rainbows(self, angle=0.):

        pixel_list_smol = []
        pixel_list_big = []
        for coordinate in self.pix_map_normlized_smol:
            self.calc_direct_rainbows(angle, coordinate, pixel_list_smol)
        for coordinate in self.pix_map_normlized_big:
            self.calc_direct_rainbows(angle, coordinate, pixel_list_big)

        logging.debug("pixel_list: %s" % pformat(pixel_list_smol))
        logging.debug("pixel_list: %s" % pformat(pixel_list_big))
        pixel_list_smol = list(itertools.chain(*pixel_list_smol))
        pixel_list_big = list(itertools.chain(*pixel_list_big))
        logging.debug("pixel_list returned: %s ... " % (pixel_list_smol[:10]))
        logging.debug("pixel_list returned: %s ... " % (pixel_list_big[:10]))
        return pixel_list_smol, pixel_list_big

    def calc_direct_rainbows(self, angle, coordinate, pixel_list):
        magnitude = math.sqrt(
            (0.5 - coordinate[0]) ** 2 +
            (0.5 - coordinate[1]) ** 2
        )
        hue = (magnitude * self.max_hue + angle * self.max_hue / self.max_angle) % self.max_hue
        rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue, 0.5, 1))
        logging.debug("rgb: %s" % (rgb,))
        pixel_list.append(rgb)

    def fill_rainbows(self, image, angle=0.):
        for col in range(self.img_size):
            hue = (col * self.max_hue / self.img_size + angle * self.max_hue / self.max_angle) % self.max_hue
            rgb = tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue, 0.5, 1))
            # logging.debug("rgb: %s" % (rgb,))
            cv2.line(image, (col, 0), (col, self.img_size), color=rgb, thickness=1)
        return image
