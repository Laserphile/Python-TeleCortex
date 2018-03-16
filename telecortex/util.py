"""Utilities for Proofs of Concept."""

from __future__ import unicode_literals

import base64
import six


def pix_array2text(*pixels):
    """Convert an array of pixels to a base64 encoded unicode string."""
    pix_bytestring = b''.join([
        six.int2byte(pixel % 256)
        for pixel in pixels
    ])

    response = base64.b64encode(pix_bytestring)
    response = six.text_type(response, 'ascii')
    return response
