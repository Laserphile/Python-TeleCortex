"""Image Interpolation Functions."""

import itertools
import logging
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
    # logging.debug(
    #     "interpolating pixel %s using %s on image:\n%s" % (
    #         coordinates, interp_type, image
    #     )
    # )
    # import pudb; pudb.set_trace()
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
        int(np.clip(floor(coordinates[1]), 0, image.shape[1] - 1)),
        int(np.clip(floor(coordinates[0]), 0, image.shape[0] - 1))
    )
    # Otherwise bilinear
    coordinate_ceiling = (
        int(np.clip(ceil(coordinates[1]), 0, image.shape[1] - 1)),
        int(np.clip(ceil(coordinates[0]), 0, image.shape[0] - 1))
    )
    coordinate_fractional = (
        coordinates[1] - coordinate_floor[1],
        coordinates[0] - coordinate_floor[0]
    )
    pixel_tl = image[
        coordinate_floor[0],
        coordinate_floor[1]
    ]
    pixel_bl = image[
        coordinate_floor[0],
        coordinate_ceiling[1]
    ]
    pixel_tr = image[
        coordinate_ceiling[0],
        coordinate_floor[1]
    ]
    pixel_br = image[
        coordinate_ceiling[0],
        coordinate_ceiling[1],
    ]
    pixel_l = blend_pixel(pixel_tl, pixel_bl, coordinate_fractional[1])
    pixel_r = blend_pixel(pixel_tr, pixel_br, coordinate_fractional[1])
    return blend_pixel(pixel_l, pixel_r, coordinate_fractional[0])

def denormalize_coordinate(shape, coordinate):
    min_dimension = min(shape[0], shape[1])
    max_dimension = max(shape[0], shape[1])
    delta_dimension = max_dimension - min_dimension
    if shape[1] > shape[0]:
        return tuple([
            np.clip(min_dimension * coordinate[0], 0, shape[0] - 1),
            np.clip(min_dimension * coordinate[1] + delta_dimension / 2, 0, shape[1] - 1)
        ])
    else:
        return tuple([
            np.clip(min_dimension * coordinate[0] + delta_dimension / 2, 0, shape[0] - 1),
            np.clip(min_dimension * coordinate[1], 0, shape[1] - 1)
        ])

def interpolate_pixel_map(image, pix_map_normalized, interp_type=None):
    """
    Generate a pixel list from an image and a pixel map.

    Given a numpy array image and a normalized pixel map showing the position
    of each pixel, return a list of channel values for each pixel in the map,
    so that it can be encoded and send to the server.

    `pix_map_normalized` is a list of coordinates of pixels, normalized means
    instead of them being coordinates on the frame like (420, 69), they are
    values from 0.0 to 1.0.

    `itertools.chain` takes a list of lists, and basically flattens that list
    https://docs.python.org/2/library/itertools.html#itertools.chain .

    This could be optimized by calculating the denormalized coordinates first.
    """
    pixel_list = []
    for pix in pix_map_normalized:
        pix_coordinate = denormalize_coordinate(image.shape, pix)
        pixel_value = interpolate_pixel(image, pix_coordinate, interp_type)
        if len(pixel_value) > 3:
            # BGRA fix
            pixel_value = tuple(pixel_value[:3])
        pixel_list.append(pixel_value)
    # logging.debug("pixel_list: %s" % pformat(pixel_list))
    pixel_list = list(itertools.chain(*pixel_list))
    assert len(pixel_list) % 4 == 0
    # logging.debug("pixel_list returned: %s ... " % (pixel_list[:10]))
    return pixel_list
