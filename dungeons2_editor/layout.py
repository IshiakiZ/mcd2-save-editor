"""Sizing helpers that keep windows readable at any display scaling."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

SCREEN_MARGIN = (40, 80)  # room left for the window frame and the taskbar


def text_width(widget: tk.Misc, characters: int) -> int:
    """Pixels for about ``characters`` characters of the default font, for wrapping text."""
    return tkfont.nametofont("TkDefaultFont", root=widget).measure("0") * characters


def fit_to_contents(window: tk.Wm, width: int = 0, height: int = 0) -> None:
    """Make ``window`` at least ``width`` x ``height`` and big enough to show everything in it (within
    the screen), and stop it from being made smaller than that, so nothing gets cut off."""
    window.update_idletasks()
    need_width, need_height = window.winfo_reqwidth(), window.winfo_reqheight()
    shown = window.winfo_ismapped()
    current_width, current_height = (window.winfo_width(), window.winfo_height()) if shown else (0, 0)
    most_width = window.winfo_screenwidth() - SCREEN_MARGIN[0]
    most_height = window.winfo_screenheight() - SCREEN_MARGIN[1]
    new_width = min(max(width, need_width, current_width), most_width)
    new_height = min(max(height, need_height, current_height), most_height)
    if (new_width, new_height) != (current_width, current_height):
        window.geometry(f"{new_width}x{new_height}")
    window.minsize(min(need_width, most_width), min(need_height, most_height))
