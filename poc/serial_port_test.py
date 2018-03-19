import serial
from serial.tools import list_ports

import cv2

print(vars(serial.tools.list_ports.comports()[-1]))
