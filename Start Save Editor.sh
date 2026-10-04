#!/bin/sh
# Opens the Minecraft Dungeons II Save Editor on Linux (for the Steam version, which runs through Proton).
# Needs Python 3.10 or newer with Tkinter: on Debian/Ubuntu, sudo apt install python3-tk
cd "$(dirname "$0")" || exit 1
exec python3 -m dungeons2_editor "$@"
