"""

# Proof of concept scripts:

- rainbows.py : single-controller, draws the same rainbow on all panels
- session.py : Multiple controller, draws the same rainbow on all panels on all controllers
- linalg.py : Multiple controller, uses multiple mappings to draw different parts of the same rainbow on a panel on each controller
- steamed_hams.py : Multiple controller, uses multiple mappings to draw different parts of a screendump on a panel on each controller

- parallel_X.py : X but communication is implemented in multiple parallel threads.
- parallel_jvb.py : The script we were running at Blazing Swan 2018

## Helpers:

- context.py : provides ability for poc modules to import telecortex module

## Incomplete:

- async.py : An attempt at asychronous which lost out to parallel
- parallel_transcode.py | parallel_gcode_player.py : Given a video file,
    convert to gcode with `transcode` so that it can be played with `gcode_player`
- cortex_drivers.py : Something JVB was working on

"""
