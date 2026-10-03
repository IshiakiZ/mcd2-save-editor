"""Where the editor keeps its files, whether it runs from source or as the packaged .exe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MCD2 Save Editor"
SOURCE_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """True inside the packaged .exe."""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    """Backups, pictures and settings.

    From source they live next to the code. The .exe unpacks itself into a temporary
    folder that's deleted when it closes, so it uses %LOCALAPPDATA%\\MCD2 Save Editor.
    """
    if is_frozen():
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
    return SOURCE_ROOT


def open_in_file_manager(folder: Path) -> None:
    """Show a folder in Explorer (Windows), Finder (macOS) or the desktop's file manager (Linux)."""
    import subprocess

    folder = Path(folder)
    if os.name == "nt":
        os.startfile(folder)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])


def resource(relative: str) -> Path:
    """A file that ships with the editor (bundled inside the .exe, or in the source tree)."""
    return Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)) / relative
