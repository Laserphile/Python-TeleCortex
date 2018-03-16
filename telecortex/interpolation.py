"""Image Interpolation Functions."""

import itertools
from math import ceil, floor

import numpy as np


def blend_pixel(pixel_a, pixel_b, coefficient):
    """Find a colour between two colours using a coefficient."""
    return (
        int(np.interp(coefficient, [0, 1], [pixel_a[0], pixel_b[0]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[1], pixel_b[1]])),
        int(np.interp(coefficient, [0, 1], [pixel_a[2], pixel_b[2]])),
    )


def interpolate_pixel(image, coordinates, interp_type=None):
    """Get the colour of a pixel from its coordinates within an image."""
    if interp_type is None:
        interp_type = 'nearest'

    assert \
        interp_type in ['nearest', 'bilinear'], \
        "unsupported interpolation type: %s" % interp_type

    if interp_type == 'nearest':
        return image[
            int(round(coordinates[0])),
            int(round(coordinates[1]))
        ]

    coordinate_floor = (
        int(np.clip(floor(coordinates[0]), 0, image.shape[0] - 1)),
        int(np.clip(floor(coordinates[1]), 0, image.shape[1] - 1))
    )
    # Otherwise bilinear
    coordinate_floor = (
        int(np.clip(floor(coordinates[0]), 0, image.shape[0] - 1)),
        int(np.clip(floor(coordinates[1]), 0, image.shape[1] - 1))
    )
    coordinate_ceiling = (
        int(np.clip(ceil(coordinates[0]), 0, image.shape[0] - 1)),
        int(np.clip(ceil(coordinates[1]), 0, image.shape[1] - 1))
    )
    coordinate_fractional = (
        coordinates[0] - coordinate_floor[0],
        coordinates[1] - coordinate_floor[1]
    )
    pixel_tl = image[
        coordinate_floor[0], coordinate_floor[1]
    ]
    pixel_bl = image[
        coordinate_ceiling[0], coordinate_floor[1]
    ]
    pixel_tr = image[
        coordinate_floor[0], coordinate_ceiling[1]
    ]
    pixel_br = image[
        coordinate_ceiling[0], coordinate_ceiling[1]
    ]
    pixel_l = blend_pixel(pixel_tl, pixel_bl, coordinate_fractional[1])
    pixel_r = blend_pixel(pixel_tr, pixel_br, coordinate_fractional[1])
    return blend_pixel(pixel_l, pixel_r, coordinate_fractional[0])

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
            np.clip(image.shape[0] * pix[0], 0, image.shape[0] - 1),
            np.clip(image.shape[1] * pix[1], 0, image.shape[1] - 1)
        )
        pixel_value = interpolate_pixel(image, pix_coordinate, interp_type)
        pixel_list.append(pixel_value)
    # logging.debug("pixel_list: %s" % pformat(pixel_list))
    pixel_list = list(itertools.chain(*pixel_list))
    # logging.debug("pixel_list returned: %s ... " % (pixel_list[:10]))
    return pixel_list
