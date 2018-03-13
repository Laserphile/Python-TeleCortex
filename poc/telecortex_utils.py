from __future__ import unicode_literals

import base64
import itertools
import logging
import os
import re
import time
from collections import OrderedDict
from datetime import datetime
from pprint import pformat, pprint

import serial
from serial.tools import list_ports

import coloredlogs
import six
from kitchen.text import converters
from telecortex_session import TelecortexSession

def pix_array2text(*pixels):
    """Convert an array of pixels to a base64 encoded unicode string."""
    # logging.debug("pixels: %s" % repr(["%02x" % pixel for pixel in pixels]))
    # logging.debug(
    #     "bytes: %s" % repr([six.int2byte(pixel) for pixel in pixels])
    # )
    pix_bytestring = b''.join([
        six.int2byte(pixel % 256)
        for pixel in pixels
    ])
    # logging.debug("bytestring: %s" % repr(pix_bytestring))

    response = base64.b64encode(pix_bytestring)
    response = six.text_type(response, 'ascii')
    # response = ''.join(map(six.unichr, pixels))
    # response = six.binary_type(base64.b64encode(
    #     bytes(pixels)
    # ))
    # logging.debug("pix_text: %s" % repr(response))
    return response
