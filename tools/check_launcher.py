"""Release check: PyInstaller's launcher (its "bootloader") was compiled in this build, not taken ready-made.

The ready-made launcher is the same file in every PyInstaller app, malware included, so antivirus engines flag
whatever carries it. The release build compiles its own (PYINSTALLER_COMPILE_BOOTLOADER), and this compares the
installed launcher with the one in PyInstaller's ready-made package to make sure that really happened.

    python -m pip download --no-deps --only-binary=:all: --dest build/stock pyinstaller==<installed version>
    python tools/check_launcher.py build/stock
"""

import hashlib
import sys
import zipfile
from pathlib import Path

LAUNCHER = "PyInstaller/bootloader/Windows-64bit-intel/runw.exe"  # the windowed launcher the editor uses


def main(stock_folder: str) -> int:
    import PyInstaller

    installed = Path(PyInstaller.__file__).resolve().parent.parent / LAUNCHER
    wheels = sorted(Path(stock_folder).glob("pyinstaller-*.whl"))
    if not wheels or not installed.is_file():
        print(f"Nothing to compare: wheels {[wheel.name for wheel in wheels]}, installed launcher {installed}")
        return 1
    with zipfile.ZipFile(wheels[-1]) as wheel:
        stock = hashlib.sha256(wheel.read(LAUNCHER)).hexdigest()
    ours = hashlib.sha256(installed.read_bytes()).hexdigest()
    if ours == stock:
        print(f"The installed launcher is PyInstaller's ready-made one ({ours}); it was not compiled here.")
        return 1
    print(f"OK: the launcher was compiled here ({ours}); the ready-made one is {stock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
