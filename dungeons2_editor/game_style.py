"""Simple mode's look: the colours and lettering of Minecraft Dungeons II's inventory screen.

Simple mode uses its own ttk theme, built on "clam" so every colour can be set, and Advanced mode
keeps the Windows look. Switching modes switches the theme, so the windows Simple mode opens (Add
items, Presets, ...) are dark too.
"""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .game_art import RARITY_TILE, mix

THEME = "mcd2"

# Colours sampled from the game's inventory screen.
BAR = "#181411"  # the tab bar along the top
BAR_HOVER = "#2b241f"
BG = "#0d3140"  # the teal behind the gear
WELL = "#0a2833"  # behind the inventory tiles
CARD = "#0b1a22"  # the item card
CARD_BOX = "#1c2a31"  # boxes on the card, like "Not enchanted"
BANNER = "#51818f"  # the card's title strip
FIELD = "#07171f"  # text boxes
EDGE = "#2a4a57"
TEXT = "#eef3f4"
SOFT = "#b4c2c8"  # body text
MUTED = "#7d929b"
HEADING = "#8ea5af"  # WEAPONS, ARMOR, ...
LEVEL = "#c75bf5"  # the level number
POWER = "#52d2ff"  # gear power
POWER_PART = "#3fb3db"
ACCENT = "#ee7a2b"  # the game's orange: the open tab, Uniques
ACCENT_HOVER = "#ff8f40"
ACCENT_PRESSED = "#cf6420"
ON_COLOR = "#1a0f06"  # text on orange and on rarity colours
BUTTON = "#56686f"
BUTTON_HOVER = "#6a7e86"
BUTTON_PRESSED = "#46565c"
BUTTON_EDGE = "#1b2427"
SELECT = "#2c6c82"
ERROR = "#ff8070"
WARN = "#ffb763"
SUCCESS = "#7fdc89"
LINK = "#66c8ff"

# Tk widgets that aren't ttk (text boxes, menus, lists in drop-downs) take their colours from here.
_DARK_OPTIONS = {
    "*Toplevel.background": BG,
    "*Text.background": FIELD,
    "*Text.foreground": TEXT,
    "*Text.insertBackground": TEXT,
    "*Text.selectBackground": SELECT,
    "*Text.selectForeground": TEXT,
    "*Text.highlightBackground": BG,
    "*Text.highlightColor": EDGE,
    "*Listbox.background": FIELD,
    "*Listbox.foreground": TEXT,
    "*Listbox.selectBackground": SELECT,
    "*Listbox.selectForeground": TEXT,
    "*Menu.background": CARD,
    "*Menu.foreground": TEXT,
    "*Menu.activeBackground": SELECT,
    "*Menu.activeForeground": TEXT,
    "*Menu.disabledForeground": MUTED,
    "*Menu.selectColor": ACCENT,
    "*Canvas.background": BG,
}


def _first_family(root: tk.Misc, *names: str) -> str | None:
    available = set(tkfont.families(root))
    return next((name for name in names if name in available), None)


class GameFonts:
    """The game's blocky capitals, as near as Windows gets (Bahnschrift), plus Segoe UI for reading."""

    def __init__(self, root: tk.Misc):
        display = _first_family(root, "Bahnschrift SemiBold", "Segoe UI Semibold", "Segoe UI")
        weight = "normal" if display == "Bahnschrift SemiBold" else "bold"
        body = _first_family(root, "Segoe UI") or tkfont.nametofont("TkDefaultFont", root=root).actual("family")
        display = display or body

        def make(family: str, size: int, weight: str = "normal") -> tkfont.Font:
            return tkfont.Font(root=root, family=family, size=size, weight=weight)

        self.huge = make(display, 30, weight)  # LEVEL and GEAR POWER
        self.title = make(display, 16, weight)  # an item's name on its card
        self.big = make(display, 20, weight)  # an item's power on its card
        self.number = make(display, 12, weight)  # currencies
        self.heading = make(display, 10, weight)  # WEAPONS, buttons, tabs
        self.tile = make(display, 9, weight)  # power on a tile
        self.tiny = make(display, 7, weight)  # a slot's name on an empty tile
        self.body = make(body, 10)
        self.small = make(body, 9)


def install(style: ttk.Style, fonts: GameFonts, row_height: int, item_row_height: int) -> None:
    """Create the Simple-mode theme (once)."""
    if THEME not in style.theme_names():
        style.theme_create(THEME, parent="clam", settings=_settings(fonts, row_height, item_row_height))


def use(root: tk.Tk, simple: bool, light_theme: str) -> None:
    """Switch the whole app between Simple mode's theme and the normal (light) one."""
    style = ttk.Style(root)
    style.theme_use(THEME if simple else light_theme)
    root.option_clear()
    if simple:
        for pattern, value in _DARK_OPTIONS.items():
            root.option_add(pattern, value)
    set_dark_title_bar(root, simple)


def is_active(widget: tk.Misc) -> bool:
    """Whether Simple mode's theme is in use."""
    return ttk.Style(widget).theme_use() == THEME


def match_title_bar(window: tk.Toplevel) -> None:
    """Give a new window a dark title bar in Simple mode."""
    if is_active(window):
        set_dark_title_bar(window, True)


def set_dark_title_bar(window: tk.Wm, dark: bool) -> None:
    """Ask Windows 10 and 11 to draw the window's title bar dark (or light again). Elsewhere, nothing.
    A window that isn't on screen yet gets it when it first appears."""
    if os.name != "nt":
        return
    window._dark_title_bar = dark  # what the next <Map> applies
    if not getattr(window, "_dark_title_bar_bound", False):
        window._dark_title_bar_bound = True
        window.bind("<Map>", lambda event: event.widget is window and _apply_title_bar(window, window._dark_title_bar), add="+")
    if window.winfo_ismapped():
        _apply_title_bar(window, dark)


def _apply_title_bar(window: tk.Wm, dark: bool) -> None:
    try:
        from ctypes import wintypes

        user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        hwnd = user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT: the frame with the title bar
        value = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, and its number before Windows 10 20H1
            if dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        # Redraw the frame now rather than the next time the window is activated.
        user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except (AttributeError, OSError, tk.TclError):
        pass


def _flat(background: str, **more) -> dict:
    """A borderless element on ``background``."""
    return {"background": background, "bordercolor": background, "lightcolor": background, "darkcolor": background, **more}


def _settings(fonts: GameFonts, row_height: int, item_row_height: int) -> dict:
    def button(background: str, hover: str, pressed: str, foreground: str, **more) -> dict:
        configure = {
            "background": background,
            "foreground": foreground,
            "bordercolor": BUTTON_EDGE,
            "lightcolor": mix(background, "#ffffff", 0.12),
            "darkcolor": mix(background, "#000000", 0.2),
            "font": fonts.heading,
            "padding": (12, 5),
            "anchor": "center",
            "focuscolor": mix(background, "#ffffff", 0.35),
            "focusthickness": 1,
            **more,
        }
        return {
            "configure": configure,
            "map": {
                "background": [("disabled", mix(background, BG, 0.6)), ("pressed", pressed), ("active", hover)],
                "lightcolor": [("pressed", pressed), ("active", mix(hover, "#ffffff", 0.12))],
                "foreground": [("disabled", mix(foreground, BG, 0.55))],
            },
        }

    def label(background: str, foreground: str, font: tkfont.Font | None = None) -> dict:
        return {"configure": {"background": background, "foreground": foreground, **({"font": font} if font else {})}}

    def field(background: str, foreground: str, border: str, focus: str) -> dict:
        return {
            "configure": {
                "fieldbackground": background,
                "foreground": foreground,
                "background": background,
                "insertcolor": foreground,
                "bordercolor": border,
                "lightcolor": background,
                "darkcolor": background,
                "selectbackground": SELECT,
                "selectforeground": TEXT,
                "arrowcolor": SOFT,
                "padding": (4, 2),
            },
            "map": {
                "bordercolor": [("focus", focus)],
                "fieldbackground": [("disabled", mix(background, BG, 0.5)), ("readonly", background)],
                "foreground": [("disabled", MUTED)],
                "lightcolor": [("focus", background)],
            },
        }

    settings = {
        ".": {
            "configure": {
                "background": BG,
                "foreground": TEXT,
                "troughcolor": WELL,
                "fieldbackground": FIELD,
                "bordercolor": EDGE,
                "lightcolor": BG,
                "darkcolor": BG,
                "selectbackground": SELECT,
                "selectforeground": TEXT,
                "insertcolor": TEXT,
                "arrowcolor": SOFT,
                "focuscolor": EDGE,
                "font": fonts.body,
            },
            "map": {"foreground": [("disabled", MUTED)]},
        },
        "TFrame": {"configure": {"background": BG}},
        "TLabel": label(BG, TEXT),
        "TButton": button(BUTTON, BUTTON_HOVER, BUTTON_PRESSED, TEXT),
        "Accent.TButton": button(ACCENT, ACCENT_HOVER, ACCENT_PRESSED, ON_COLOR, padding=(16, 6)),
        "TMenubutton": button(BUTTON, BUTTON_HOVER, BUTTON_PRESSED, TEXT, arrowcolor=TEXT),
        "TEntry": field(FIELD, TEXT, EDGE, ACCENT),
        "TSpinbox": field(FIELD, TEXT, EDGE, ACCENT),
        "TCombobox": field(FIELD, TEXT, EDGE, ACCENT),
        "TCheckbutton": {
            "configure": {
                "background": BG,
                "foreground": TEXT,
                "indicatorbackground": FIELD,
                "indicatorforeground": ACCENT,
                "upperbordercolor": EDGE,
                "lowerbordercolor": EDGE,
                "indicatormargin": (0, 1, 6, 1),
            },
            "map": {"indicatorbackground": [("pressed", SELECT), ("disabled", BG)], "background": [("active", BG)]},
        },
        "TRadiobutton": {
            "configure": {
                "background": BG,
                "foreground": TEXT,
                "indicatorbackground": FIELD,
                "indicatorforeground": ACCENT,
                "upperbordercolor": EDGE,
                "lowerbordercolor": EDGE,
                "indicatormargin": (0, 1, 6, 1),
            },
            "map": {"indicatorbackground": [("pressed", SELECT), ("disabled", BG)], "background": [("active", BG)]},
        },
        "Treeview": {
            "configure": {
                "background": FIELD,
                "fieldbackground": FIELD,
                "foreground": TEXT,
                "bordercolor": EDGE,
                "lightcolor": FIELD,
                "darkcolor": FIELD,
                "rowheight": row_height,
            },
            "map": {"background": [("selected", SELECT)], "foreground": [("selected", TEXT)]},
        },
        "Items.Treeview": {"configure": {"rowheight": item_row_height}},
        "Treeview.Heading": {
            "configure": {
                "background": "#163846",
                "foreground": HEADING,
                "bordercolor": EDGE,
                "lightcolor": "#1d4554",
                "darkcolor": "#112d38",
                "font": fonts.heading,
                "padding": (6, 3),
            },
            "map": {"background": [("active", "#1d4554")]},
        },
        "TScrollbar": {
            "configure": {
                "background": "#2f4f5c",
                "troughcolor": WELL,
                "bordercolor": WELL,
                "lightcolor": "#3d6270",
                "darkcolor": "#26414c",
                "arrowcolor": SOFT,
                "gripcount": 0,
            },
            "map": {"background": [("active", "#3e6676")]},
        },
        "TNotebook": {"configure": {"background": BG, "bordercolor": EDGE, "lightcolor": BG, "darkcolor": BG, "tabmargins": (0, 4, 0, 0)}},
        "TNotebook.Tab": {
            "configure": {"background": WELL, "foreground": MUTED, "bordercolor": EDGE, "lightcolor": WELL, "padding": (12, 4), "font": fonts.heading},
            "map": {"background": [("selected", BG)], "foreground": [("selected", TEXT)], "lightcolor": [("selected", BG)]},
        },
        "TLabelframe": {"configure": {"background": BG, "bordercolor": EDGE, "lightcolor": BG, "darkcolor": BG}},
        "TLabelframe.Label": label(BG, HEADING, fonts.heading),
        "TPanedwindow": {"configure": {"background": BG}},
        "Sash": {"configure": {"background": EDGE, "bordercolor": EDGE, "lightcolor": EDGE, "darkcolor": EDGE}},
        # The same style names the rest of the editor uses, in colours that work on the dark background.
        "Muted.TLabel": label(BG, MUTED),
        "Title.TLabel": label(BG, TEXT, fonts.title),
        "Heading.TLabel": label(BG, TEXT, fonts.heading),
        "Error.TLabel": label(BG, ERROR),
        "Warn.TLabel": label(BG, WARN),
        "Success.TLabel": label(BG, SUCCESS),
        "Link.TLabel": label(BG, LINK),
        "Changes.TLabel": label(BG, ACCENT, fonts.heading),
        "Running.TLabel": label(BG, ERROR, fonts.heading),
        "Closed.TLabel": label(BG, SUCCESS),
        # The bars along the top and bottom of the window.
        "Bar.TFrame": {"configure": {"background": BAR}},
        "Bar.TLabel": label(BAR, SOFT),
        "BarMuted.TLabel": label(BAR, MUTED, fonts.small),
        "BarRunning.TLabel": label(BAR, ERROR, fonts.heading),
        "BarClosed.TLabel": label(BAR, SUCCESS, fonts.heading),
        "BarChanges.TLabel": label(BAR, ACCENT, fonts.heading),
        "Bar.TButton": {
            "configure": {**_flat(BAR), "foreground": SOFT, "font": fonts.heading, "padding": (10, 6), "focuscolor": BAR_HOVER},
            "map": {
                "background": [("pressed", BAR_HOVER), ("active", BAR_HOVER)],
                "lightcolor": [("active", BAR_HOVER)],
                "darkcolor": [("active", BAR_HOVER)],
                "bordercolor": [("active", BAR_HOVER)],
                "foreground": [("disabled", mix(SOFT, BAR, 0.6)), ("active", TEXT)],
            },
        },
        "Bar.TMenubutton": {
            "configure": {**_flat(BAR), "foreground": TEXT, "arrowcolor": SOFT, "font": fonts.heading, "padding": (10, 8)},
            "map": {
                "background": [("pressed", BAR_HOVER), ("active", BAR_HOVER)],
                "lightcolor": [("active", BAR_HOVER)],
                "darkcolor": [("active", BAR_HOVER)],
                "bordercolor": [("active", BAR_HOVER)],
            },
        },
        "Bar.TCheckbutton": {
            "configure": {
                "background": BAR,
                "foreground": SOFT,
                "font": fonts.heading,
                "indicatorbackground": "#0f0c0a",
                "indicatorforeground": ACCENT,
                "upperbordercolor": "#4a3f37",
                "lowerbordercolor": "#4a3f37",
                "indicatormargin": (0, 1, 6, 1),
                "padding": (6, 6),
            },
            "map": {"background": [("active", BAR_HOVER)], "foreground": [("active", TEXT)]},
        },
        "BarTab.Toolbutton": {
            "configure": {**_flat(BAR), "foreground": MUTED, "font": fonts.heading, "padding": (14, 9, 14, 7), "anchor": "center"},
            "map": {
                "foreground": [("selected", "#f6e9da"), ("active", TEXT)],
                "background": [("active", BAR_HOVER)],
                "lightcolor": [("active", BAR_HOVER)],
                "darkcolor": [("active", BAR_HOVER)],
                "bordercolor": [("active", BAR_HOVER)],
            },
        },
        "Underline.TFrame": {"configure": {"background": ACCENT}},
        "BarLine.TFrame": {"configure": {"background": BAR}},
        "Currency.TEntry": {
            "configure": {
                "fieldbackground": BAR,
                "background": BAR,
                "foreground": TEXT,
                "insertcolor": TEXT,
                "bordercolor": BAR,
                "lightcolor": BAR,
                "darkcolor": BAR,
                "selectbackground": SELECT,
                "padding": (2, 0),
            },
            "map": {"bordercolor": [("focus", ACCENT)], "fieldbackground": [("disabled", BAR)], "foreground": [("disabled", MUTED)]},
        },
        # The hero screen.
        "Game.TFrame": {"configure": {"background": BG}},
        "Well.TFrame": {"configure": {"background": WELL}},
        "Caption.TLabel": label(BG, HEADING, fonts.heading),
        "GearPower.TLabel": label(BG, POWER, fonts.huge),
        "GearPart.TLabel": label(BG, POWER_PART, fonts.heading),
        "Message.TLabel": label(BG, SOFT, fonts.small),
        "MessageError.TLabel": label(BG, ERROR, fonts.small),
        "MessageGood.TLabel": label(BG, SUCCESS, fonts.small),
        "Big.TLabel": label(BG, TEXT, fonts.title),
        "Body.TLabel": label(BG, SOFT, fonts.body),
        "Level.TEntry": {
            "configure": {
                "fieldbackground": BG,
                "background": BG,
                "foreground": LEVEL,
                "insertcolor": LEVEL,
                "bordercolor": BG,
                "lightcolor": BG,
                "darkcolor": BG,
                "selectbackground": "#4f2463",
                "padding": (0, 0),
            },
            "map": {"bordercolor": [("focus", LEVEL)]},
        },
        "Stat.TEntry": field(FIELD, TEXT, EDGE, ACCENT),
        "Chip.Toolbutton": {
            "configure": {**_flat(BG), "foreground": MUTED, "font": fonts.heading, "padding": (6, 4), "anchor": "center"},
            "map": {
                "background": [("selected", "#1b4b5c"), ("active", "#123d4c")],
                "lightcolor": [("selected", "#1b4b5c"), ("active", "#123d4c")],
                "darkcolor": [("selected", "#1b4b5c"), ("active", "#123d4c")],
                "bordercolor": [("selected", "#2e6a7e"), ("active", "#123d4c")],
                "foreground": [("selected", TEXT), ("active", SOFT)],
            },
        },
        # The item card.
        "Card.TFrame": {"configure": {"background": CARD}},
        "CardBorder.TFrame": {"configure": {"background": "#2a3d46"}},
        "Card.TLabel": label(CARD, SOFT, fonts.body),
        "CardMuted.TLabel": label(CARD, MUTED, fonts.small),
        "CardTitle.TLabel": label(CARD, TEXT, fonts.title),
        "CardPower.TLabel": label(CARD, TEXT, fonts.big),
        "CardHeading.TLabel": label(CARD, HEADING, fonts.heading),
        "CardError.TLabel": label(CARD, ERROR, fonts.small),
        "CardGood.TLabel": label(CARD, SUCCESS, fonts.small),
        "CardWarn.TLabel": label(CARD, WARN, fonts.small),
        "Box.TFrame": {"configure": {"background": CARD_BOX}},
        "Box.TLabel": label(CARD_BOX, SOFT, fonts.small),
        "BoxTitle.TLabel": label(CARD_BOX, TEXT, fonts.heading),
        "Card.TButton": button(BUTTON, BUTTON_HOVER, BUTTON_PRESSED, TEXT, padding=(10, 5)),
        "Card.TSpinbox": field(FIELD, TEXT, EDGE, ACCENT),
        "Card.TEntry": field(FIELD, TEXT, EDGE, ACCENT),
    }
    for rarity, color in RARITY_TILE.items():
        settings[f"{rarity}.Rarity.Toolbutton"] = {
            "configure": {
                "background": CARD,
                "foreground": color,
                "bordercolor": mix(color, CARD, 0.45),
                "lightcolor": CARD,
                "darkcolor": CARD,
                "font": fonts.heading,
                "padding": (7, 3),
                "anchor": "center",
            },
            "map": {
                "background": [("selected", color), ("active", mix(color, CARD, 0.75))],
                "lightcolor": [("selected", color), ("active", mix(color, CARD, 0.75))],
                "darkcolor": [("selected", color), ("active", mix(color, CARD, 0.75))],
                "bordercolor": [("selected", color)],
                "foreground": [("selected", ON_COLOR), ("disabled", MUTED)],
            },
        }
    return settings
