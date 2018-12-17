"""
Serial stuff.
"""
import logging
from serial.tools import list_ports
from collections import OrderedDict


def find_serial_dev(vid=None, pid=None, ser=None):
    """
    Given a Vendor ID and (optional) Product ID, enumerate the serial ports
    until a matching device is found.
    """
    logging.debug(
        "Checking for: VID: %s, PID: %s, SER: %s",
        repr(vid), repr(pid), repr(ser)
    )
    for port_info in list_ports.comports():
        logging.debug(
            "found a device: \ninfo: %s\nvars: %s",
            port_info.usb_info(),
            vars(port_info)
        )
        if vid is not None and port_info.vid != vid:
            logging.debug("vid not match %s | %s", vid, port_info.vid)
            continue
        if pid is not None and port_info.pid != pid:
            logging.debug("pid not match %s | %s", pid, port_info.pid)
            continue
        if ser is not None and port_info.serial_number != str(ser):
            logging.debug(
                "ser not match %s | %s", ser, port_info.serial_number)
            continue
        logging.info("found target device: %s" % port_info.device)
        target_device = port_info.device
        return target_device


def query_serial_dev(vid=None, pid=None, ser=None, dev=None):
    """
    Given a Vendor ID and (optional) Product ID, return the serial ports which
    match these parameters
    """
    logging.debug(
        "Querying for: VID: %s, PID: %s, SER: %s, DEV: %s",
        repr(vid), repr(pid), repr(ser), repr(dev)
    )
    matching_devs = []
    for port_info in list_ports.comports():
        logging.debug(
            "found a device: \ninfo: %s\nvars: %s",
            port_info.usb_info(),
            vars(port_info)
        )
        if vid is not None and port_info.vid != vid:
            logging.debug("vid not match %s | %s", vid, port_info.vid)
            continue
        if pid is not None and port_info.pid != pid:
            logging.debug("pid not match %s | %s", pid, port_info.pid)
            continue
        if ser is not None and port_info.serial_number != str(ser):
            logging.debug(
                "ser not match %s | %s", ser, port_info.serial_number)
            continue
        if dev is not None and port_info.device != dev:
            logging.debug(
                "dev not match %s | %s", ser, port_info.serial_number)
            continue
        logging.info("found target device: %s" % port_info.device)
        target_device = port_info.device
        matching_devs.append(target_device)
    return matching_devs

# to get these values:
# pip install pyserial
# python -m serial.tools.list_ports --verbose

DEFAULT_BAUD = 1000000
DEFAULT_TIMEOUT = 1

# Fix for this issue:
IGNORE_SERIAL_NO = True
IGNORE_VID_PID = False

TEENSY_VID = 0x16C0

"""
Servers is a list of objects containing information about a server's
configuration.
"""

SERVERS_DOME = OrderedDict([
    (0, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser': '4057530',
         'baud': DEFAULT_BAUD, 'cid': 1}),
    (1, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser': '4058600',
         'baud': DEFAULT_BAUD, 'cid': 2}),
    (2, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser': '3176950',
         'baud': DEFAULT_BAUD, 'cid': 3}),
    (3, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser': '4057540',
         'baud': DEFAULT_BAUD, 'cid': 4}),
    (4, {'vid': TEENSY_VID, 'pid': 0x0483, 'ser': '4058621',
         'baud': DEFAULT_BAUD, 'cid': 5})
])

# SERVERS = OrderedDict([
#    (0, {'vid': TEENSY_VID, 'pid': 0x0483})
# ])

# SERVERS_DOME = OrderedDict([
#     (0, {
#         'file': '/dev/cu.usbmodem4057531',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (1, {
#         'file': '/dev/cu.usbmodem4058621',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (2, {
#         'file': '/dev/cu.usbmodem3176951',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (3, {
#         'file': '/dev/cu.usbmodem4057541',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
#     (4, {
#         'file': '/dev/cu.usbmodem4058601',
#         'baud': DEFAULT_BAUD,
#         'timeout': DEFAULT_TIMEOUT
#     }),
# ])

SERVERS_SINGLE = OrderedDict([
    # (0, {
    #     'vid': TEENSY_VID,
    #     'pid': 0x0483,
    #     'baud': DEFAULT_BAUD,
    #     'timeout': DEFAULT_TIMEOUT
    # })
    (0, {
        'file': '/dev/tty.usbmodem3176940',
        'baud': DEFAULT_BAUD,
        'timeout': DEFAULT_TIMEOUT
    }),
])

SERVERS_BLANK = OrderedDict([

])
