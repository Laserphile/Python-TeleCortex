"""Simple Rainbow test script with no mapping required."""

from __future__ import unicode_literals

import logging
from datetime import datetime

import serial
import time

from context import telecortex
from six import b
from telecortex.config import TeleCortexSessionConfig
from telecortex.session import DEFAULT_BAUD, TEENSY_VID, find_serial_dev


def main():
    """Main."""
    conf = TeleCortexSessionConfig(
        name="serialtest",
        description="Test serial buffer capacity",
    )
    conf.parser.add_argument('--serial-dev',)
    conf.parser.add_argument('--serial-baud', default=DEFAULT_BAUD)

    conf.parse_args()

    logging.debug("\n\n\nnew session at %s" % datetime.now().isoformat())

    target_device = conf.args.serial_dev
    if target_device is None:
        target_device = find_serial_dev(TEENSY_VID)
    if not target_device:
        raise UserWarning("target device not found")
    else:
        logging.debug("target_device: %s" % target_device)
        logging.debug("baud: %s" % conf.args.serial_baud)
    # Connect to serial
    with serial.Serial(
        port=target_device, baudrate=conf.args.serial_baud, timeout=1
    ) as ser:
        # logging.debug("settings: %s" % pformat(ser.get_settings()))
        for i in range(1000):
            out = b'%02X' % i + b'||' + b''.join([
                b'%02X' % x for x in range(i)
            ]) + b'\r\n'
            logging.info("sending: %s" % out)
            ser.write(out)
            time.sleep(0.01)
            data = ser.read_all()
            if data:
                logging.info("received: %s" % data)


if __name__ == '__main__':
    main()
