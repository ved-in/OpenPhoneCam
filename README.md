# OpenPhoneCam

FOSS program that turns your phone into a high quality webcam for your computer!

# Disclaimer

This is a work-in-progress app that is right now ~~using scrcpy~~ custom app acitivty to fetch the video from your android device. No App Downloads!

Scrcpy is abandoned, didnt work out. We are making a custom app activity but will monitor Google's upcoming developer verification policies, if they require activites as well to be verified like normal apps...

This project is NOT COMPLETE. Attempting to run it will give you... a broken mess.

# Requirements

After a functional release, we will update this part.

If for some reason you have balls of steel and want to mess with this, if your system can merely boot, it's good enough.
for the yolo vision tracking however, do ensure you have an a cpu that came out within the last 4 years or a CUDA-compatible GPU. AMD maybe works...?

Also ensure your phoen supports Android 11 or higher (Camera2API stuff) and that you have USB Debugging enabled.

# Notes for future

What’s Done:

main_tab has majority of its options linked. the few left are the ones which would require a bit of "thinking"
Added proper liscencing

Currently Pending:

better logging and error handling
about and settings tab ui
few options in main and cammy tab currently do not have functionality and needs to be done.
add V4L2 options in case the user may be using a different V4L2 setup than the one the program accepts

Discovered about toml files which we can use to setup the dependencies and all. Need to check it out and replace the current dependencies.txtw

# License 

Copyright (C) 2026 Rudraksh Tiku, Vedant Jain
This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
See the LICENSE file for details.

# Third-Party Disclosure

This project incorporates Ultralytics YOLO (AGPL-3.0).
Ultralytics YOLO source: https://github.com/ultralytics/ultralytics