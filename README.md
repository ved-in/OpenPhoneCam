# OpenPhoneCam

FOSS program that turns your phone into a high quality webcam for your computer!

# Disclaimer

This is a work-in-progress app that is right now ~~using scrcpy~~ custom app acitivty to fetch the video from your android device. No App Downloads!

Currently using scrcpy but will need a custom activity as V4L2 sink doesnt exist in Windows and MacOS. Will be supported in first release.

This project is NOT COMPLETE. Attempting to run it will give you... a broken mess.

# Requirements

After a functional release, we will update this part.

If for some reason you have balls of steel and want to mess with this, if your system can merely boot, it's good enough.
for the yolo vision tracking however, do ensure you have an a cpu that came out within the last 4 years or a CUDA-compatible GPU. AMD maybe works...?

Also ensure your phoen supports Android 11 or higher (Camera2API stuff) and that you have USB Debugging enabled.

THis project only works on linux, and requires that you have a virtual V4L2 sink at /dev/video0. Keep in mind OBS Virtual Camera also uses that directory so you may not use both OBS Virtual Cam and our program at the same time  F O R  N O W.

To switch the input camera device, open tab_cammy and riiiiiiight at the tippity top edit "device_index" variable. DONT. TOUCH. ANYTHING. ELSE.

# Notes for future

What’s Done:

main_tab has majority of its options linked.
Added proper liscencing.
Experimental Centre Stage feature added, its not toggleable but it will be in the release.

Currently Pending:

Most GUI buttons and elements dont work and havent been coded yet.
better logging and error handling.
about and settings tab ui.
few options in main and cammy tab currently do not have functionality and needs to be done.
add V4L2 options in case the user may be using a different V4L2 setup than the one the program accepts.
Discovered about toml files which we can use to setup the dependencies and all. Need to check it out and replace the current dependencies.txtw

# License 

Copyright (C) 2026 Rudraksh Tiku, Vedant Jain
This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
See the LICENSE file for details.

# Third-Party Disclosure

This project incorporates Ultralytics YOLO (AGPL-3.0).
Ultralytics YOLO source: https://github.com/ultralytics/ultralytics