@echo off
rem Opens the Minecraft Dungeons II Save Editor without a console window.
rem Uses the first Python that starts and has Tkinter (the py launcher's default can be a broken install).
cd /d "%~dp0"
for %%C in ("python" "py -3") do (
    for /f "delims=" %%W in ('%%~C -c "import sys, tkinter; print(sys.executable)" 2^>nul') do (
        if exist "%%~dpWpythonw.exe" (
            start "" "%%~dpWpythonw.exe" -m dungeons2_editor
            exit /b
        )
    )
)
echo Could not find a working Python 3 with Tkinter.
echo Install Python from https://www.python.org/downloads/ and run this again.
pause
