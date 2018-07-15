# Python-TeleCortex

A Python Client for the [TeleCortex Protocol](https://github.com/Laserphile/TeleCortex)

# The library

- __session__ used to keep track of connections to individual controllers
- __mapping__ used to create a list of pixel locations within a given image
- __interpolation__ is used to extract pixel data from an image using a pixel map.

# Proof of Concept Scripts

These are a bunch of helpful examples to get you started. See the full list of PoCs at `poc/__init__.py`

## Configuration

Since each script is a proof of concept that was written as the library was developing,
there are slight variances in the way they are all configured.
Most will have a SERVERS global variable that can be configured with details used to
identify the devices that the script will talk to.

To get the serial port information for your device, use `python -m serial.tools.list_ports --verbose`

e.g.
```bash
#              / This is the file
/dev/cu.usbmodem3176931
    desc: USB Serial                  #  / and this is the serial number
    hwid: USB VID:PID=16C0:0483 SER=3176930 LOCATION=20-1
     #  This is the VID/     \ This is the PID
```

### Note for Teensy 3.2

on the teensys we used, the serial number obtained by serial.tools is not reliable,
and can sometimes bet set to `None` inexplicably.
The file name can randomly disappear while the device is being used,
and then reappear under a different name which was a nightmare to debug.
This is why in our implementation, we used an EEPROM coded device ID to get around this.
We also suggest using `watchdog.py` to run the scripts so that your script can be restarted automatically

## Debugging

Each proof of concept script has its own `LOG_FILE` which can be enabled with `ENABLE_LOG_FILE`.
By default the scripts will log everything to the log file, and only log messages above `STREAM_LOG_LEVEL` to the console.

Some scripts will also allow you to preview the output in an opencv window with `ENABLE_PREVIEW`.
This is disabled by default because of its performance impact.

## More info
[Blog posts](http://blog.laserphile.com/search/label/Cortex)
