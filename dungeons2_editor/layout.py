"""Sizing helpers that keep windows readable at any display scaling."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

SCREEN_MARGIN = (40, 80)  # room left for the window frame and the taskbar, on a display at 100%


def text_width(widget: tk.Misc, characters: int) -> int:
    """Pixels for about ``characters`` characters of the default font, for wrapping text."""
    return tkfont.nametofont("TkDefaultFont", root=widget).measure("0") * characters


def display_scale(widget: tk.Misc) -> float:
    """How much Windows scales this display up: 1.0 at 100%, 1.5 at 150%. Never below 1."""
    return max(1.0, widget.winfo_fpixels("1i") / 96)


def screen_room(widget: tk.Misc) -> tuple[int, int]:
    """The biggest a window should be here: the screen, less room for the window's frame and the taskbar,
    which grow with the display's scaling too."""
    scale = display_scale(widget)
    return widget.winfo_screenwidth() - int(SCREEN_MARGIN[0] * scale), widget.winfo_screenheight() - int(SCREEN_MARGIN[1] * scale)


def scaled_size(widget: tk.Misc, width: int, height: int) -> tuple[int, int]:
    """A window size given in pixels for a display at 100%, as it should be on this one: text and buttons
    are bigger on a scaled-up display, so the window has to be too. Never more than the screen has room for."""
    scale = display_scale(widget)
    most_width, most_height = screen_room(widget)
    return min(int(width * scale), most_width), min(int(height * scale), most_height)


def fit_to_contents(window: tk.Wm, width: int = 0, height: int = 0) -> None:
    """Make ``window`` at least ``width`` x ``height`` and big enough to show everything in it (within
    the screen), and stop it from being made smaller than that, so nothing gets cut off."""
    window.update_idletasks()
    need_width, need_height = window.winfo_reqwidth(), window.winfo_reqheight()
    shown = window.winfo_ismapped()
    current_width, current_height = (window.winfo_width(), window.winfo_height()) if shown else (0, 0)
    most_width, most_height = screen_room(window)
    new_width = min(max(width, need_width, current_width), most_width)
    new_height = min(max(height, need_height, current_height), most_height)
    if (new_width, new_height) != (current_width, current_height):
        window.geometry(f"{new_width}x{new_height}")
    window.minsize(min(need_width, most_width), min(need_height, most_height))
