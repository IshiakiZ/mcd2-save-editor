#!/bin/sh
# Opens the Minecraft Dungeons II Save Editor on a Mac (double-click it in Finder).
# Needs Python 3.10 or newer with Tkinter: the installer from python.org has both.
cd "$(dirname "$0")" || exit 1
exec python3 -m dungeons2_editor "$@"
