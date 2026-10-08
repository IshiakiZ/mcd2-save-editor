@echo off
rem Starts the play recorder in a console: it writes down what Minecraft Dungeons II saves while you play.
rem It only reads your saves, and what it writes stays in the recordings folder on this PC.
rem The same recorder is in the editor: Menu, Play recorder.
cd /d "%~dp0"
title MCD2 play recorder
python -c "import sys" >nul 2>nul && (python -m dungeons2_editor record %* & goto done)
py -3 -c "import sys" >nul 2>nul && (py -3 -m dungeons2_editor record %* & goto done)
echo Could not find Python 3. Install it from https://www.python.org/downloads/ and run this again.
:done
pause
