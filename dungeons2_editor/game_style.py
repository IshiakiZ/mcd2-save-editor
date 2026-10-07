"""Simple mode's looks: the colours and lettering of Minecraft Dungeons II's inventory screen, in two styles.

Simple mode uses its own ttk themes, built on "clam" so everything can be set, and Advanced mode keeps the
Windows look. Switching modes switches the theme, so the windows Simple mode opens (Add items, Presets, ...)
look the same. There are two of them, one for each look. Original, the one the editor opens in, is flat and
square, drawn by ttk itself. Liquid Glass, which Menu > Look switches to, has Apple's shapes (capsule buttons,
rounded panels with a bright rim, one tinted button for the main action, bars that float): pictures the editor
draws for itself the first time the look is asked for (``glass.py``), fitted to each widget by ttk. The colours,
the lettering and the item tiles' pictures are the game's in both.
"""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import glass
from .game_art import RARITY_TILE, mix

THEME = "mcd2"  # the original look
GLASS_THEME = "mcd2glass"  # Liquid Glass
# The looks Simple mode comes in: what the settings file calls each, and what the menu does. The original one
# is what the editor opens in until Menu > Look says otherwise.
LOOKS = {"classic": "Original", "glass": "Liquid Glass"}
DEFAULT_LOOK = "classic"

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

# Sizes of the glass, in pixels on a display at 100% (they grow with the display's scaling). The screens that lay
# things out on a panel use the same numbers.
BANNER_HEIGHT = 28  # the title strip along the top of the item card
CARD_RADIUS = 14
CARD_PAD = 5  # how far inside the card's rounded edge its contents start
CARD_DROP = 4  # room under the card for its shadow
WELL_RADIUS = 12
WELL_PAD = 6
BOX_RADIUS = 10
BAR_RADIUS = 18
BAR_DROP = 3
TILE_RADIUS = 10

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
    """Create the theme of Simple mode's original look (once), and keep what Liquid Glass's is made from. That
    one's pictures take a moment to draw, longer the more a display is scaled up, so it is made when the look is
    first asked for (``use``): a window that stays in the original look never waits for it."""
    if THEME not in style.theme_names():
        style.theme_create(THEME, parent="clam", settings=_classic_settings(fonts, row_height, item_row_height))
    home = style.master.nametowidget(".")
    if not hasattr(home, "_mcd2_glass"):
        home._mcd2_glass = (fonts, row_height, item_row_height)


def _install_glass(style: ttk.Style) -> None:
    """Create Liquid Glass's theme (once): its pictures are drawn first, and then the styles that use them."""
    if GLASS_THEME in style.theme_names():
        return
    root = style.master.nametowidget(".")  # the app's own window: it lives as long as the theme does
    fonts, row_height, item_row_height = root._mcd2_glass
    looks = Looks(root, fonts)
    root._mcd2_looks = looks  # Tk drops a picture nobody holds
    before = style.theme_use()
    style.theme_create(GLASS_THEME, parent="clam")
    style.theme_use(GLASS_THEME)  # an element is created in the theme in use
    try:
        for name, pictures, options in looks.elements:
            style.element_create(name, "image", *pictures, **options)
        style.theme_settings(GLASS_THEME, _glass_settings(fonts, row_height, item_row_height))
    finally:
        style.theme_use(before)


class Looks:
    """Simple mode's glass: the pictures its buttons, tabs, panels and fields are made of, drawn for this
    display's scaling. ``elements`` lists what to make of them: (element name, its pictures by state, options)."""

    def __init__(self, root: tk.Misc, fonts: GameFonts):
        self.root = root
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        self.line = fonts.heading.metrics("linespace")
        # ttk fills a widget by laying the middle of its picture side by side, piece by piece, and each piece is
        # blended in on its own: a picture with a middle two pixels wide makes a large panel take seconds to draw.
        # So every picture gets a middle about as big as the widget it's for (a wide one costs no more to make).
        self.wide, self.tall = self.px(160), self.px(256)
        self.pictures: dict[tuple, tk.PhotoImage] = {}
        self.elements: list[tuple[str, list, dict]] = []
        self._buttons()
        self._fields()
        self._marks()
        self._scrollbars()
        self._panels()

    def px(self, size: float) -> int:
        return max(1, int(round(size * self.scale)))

    def picture(self, width: int, height: int, *parts) -> tk.PhotoImage:
        key = (width, height, parts)
        if key not in self.pictures:
            self.pictures[key] = tk.PhotoImage(master=self.root, data=glass.picture(width, height, *parts))
        return self.pictures[key]

    def element(self, name: str, size: tuple[int, int], default: tuple, states: tuple = (), **options) -> None:
        """An element that shows ``default`` (the parts of a picture), and other parts in other states:
        ``states`` is ((state, ...), parts) pairs, the first that fits winning."""
        pictures: list = [self.picture(*size, *default)]
        pictures += [(*state, self.picture(*size, *parts)) for state, parts in states]
        self.elements.append((name, pictures, options))

    def _capsule(self, name: str, pad_x: float, pad_y: float, drop: float, default: dict, states: tuple, like: str = "") -> None:
        """A capsule as tall as a line of the buttons' lettering plus ``pad_y`` above and below, which ttk
        stretches sideways. ``default`` and each state give the Shape's settings; with ``like``, the pictures of
        that capsule are used again with another padding."""
        pad, fall = self.px(pad_y), self.px(drop) if drop else 0
        body = self.line + 2 * pad
        body += 1 - body % 2  # an odd height leaves one row in the middle to stretch
        radius = body // 2
        size = (2 * radius + self.wide, body + fall)
        top = (body - self.line) // 2

        def shape(settings: dict) -> tuple:
            return (glass.Shape(radius=body / 2, drop=fall, **settings),)

        self.element(
            name, size, shape(default), tuple((state, shape(settings)) for state, settings in states),
            border=(radius, radius, radius, radius + fall), sticky="nsew", width=2 * radius + 2, height=body + fall,
            padding=(self.px(pad_x), top, self.px(pad_x), body - self.line - top + fall),
        )

    def _buttons(self) -> None:
        clear = {"alpha": 0.0}
        lit = {"glow": 0.07, "shade": 0.10, "rim": 0.42, "edge_alpha": 0.34, "shadow": 0.30}
        regular = (
            (("disabled",), {"alpha": 0.07, "rim": 0.10, "edge_alpha": 0.18}),
            (("pressed",), {"alpha": 0.13, "rim": 0.18, "edge_alpha": 0.40, "shade": 0.10}),
            (("active",), {"alpha": 0.31, **lit}),
            (("focus",), {"alpha": 0.24, **lit, "edge": "#ffffff", "edge_alpha": 0.30}),
        )
        for name, pad_x, pad_y in (("glassbtn", 15, 7), ("glassbtn.card", 8, 5)):  # the card's buttons are a little lower
            self._capsule(name, pad_x, pad_y, 2, {"alpha": 0.22, **lit}, regular)
        tint = {"glow": 0.22, "shade": 0.14, "rim": 0.55, "edge": "#3d1a04", "edge_alpha": 0.60, "shadow": 0.34}
        self._capsule(
            "glassaccent", 17, 7, 2, {"fill": ACCENT, **tint},
            (
                (("disabled",), {"fill": ACCENT, "alpha": 0.26, "rim": 0.12}),
                (("pressed",), {"fill": ACCENT_PRESSED, **tint, "rim": 0.22, "glow": 0.08}),
                (("active",), {"fill": ACCENT_HOVER, **tint}),
            ),
        )
        # A tab: clear until it's pointed at, and a lifted pill when it's the one picked.
        self._capsule(
            "glasschip", 8, 5, 1, clear,
            (
                (("selected",), {"alpha": 0.20, "glow": 0.06, "shade": 0.08, "rim": 0.42, "edge_alpha": 0.30, "shadow": 0.26}),
                (("active",), {"alpha": 0.10}),
            ),
        )
        # A button on a bar: its lettering alone, with a pill behind it under the pointer.
        self._capsule("glassbar", 12, 6, 0, clear, ((("disabled",), clear), (("pressed",), {"alpha": 0.08}), (("active",), {"alpha": 0.14, "rim": 0.25})))
        self._capsule(
            "glasstab", 14, 6, 0, clear,
            ((("selected",), {"alpha": 0.16, "glow": 0.05, "rim": 0.40, "edge_alpha": 0.25}), (("active",), {"alpha": 0.09})),
        )
        for rarity, color in RARITY_TILE.items():
            self._capsule(
                f"glassrarity.{rarity.lower()}", 9, 3, 1, {"alpha": 0.0, "edge": color, "edge_alpha": 0.55},
                (
                    (("disabled",), {"alpha": 0.0, "edge": MUTED, "edge_alpha": 0.30}),
                    (("selected",), {"fill": color, "glow": 0.20, "shade": 0.12, "rim": 0.50, "edge_alpha": 0.30, "shadow": 0.30}),
                    (("active",), {"fill": color, "alpha": 0.24, "edge": color, "edge_alpha": 0.85}),
                ),
            )

    def _fields(self) -> None:
        """A text box: set into the surface, with a rounded edge that turns orange when it's typed into."""
        radius, lip = self.px(7), self.px(3)
        size = (2 * radius + self.wide, 2 * radius + self.px(16))

        def field(fill: str, edge: str, edge_alpha: float = 1.0) -> tuple:
            return (glass.Shape(fill=fill, radius=radius, inset=0.45, zone=lip, edge=edge, edge_alpha=edge_alpha),)

        self.element(
            "glassfield", size, field(FIELD, EDGE),
            ((("disabled",), field(mix(FIELD, BG, 0.5), EDGE, 0.5)), (("focus",), field(FIELD, ACCENT))),
            border=radius, sticky="nsew", width=2 * radius + 2, height=2 * radius + 2, padding=(self.px(8), lip, self.px(5), lip),
        )
        # The little arrows in a number box and at the end of a list box.
        wide, tall, thick = self.px(13), self.px(8), max(1.4, 1.5 * self.scale)
        up = ((wide * 0.24, tall * 0.72), (wide * 0.5, tall * 0.30), (wide * 0.76, tall * 0.72))
        down = tuple((x, tall - y) for x, y in up)
        for name, points in (("glass.uparrow", up), ("glass.downarrow", down)):
            self.element(
                name, (wide, tall), (glass.Stroke(points, thick, SOFT),),
                ((("disabled",), (glass.Stroke(points, thick, MUTED, 0.6),)), (("pressed",), (glass.Stroke(points, thick, ACCENT),)), (("active",), (glass.Stroke(points, thick, TEXT),))),
                sticky="",
            )
        big, high = self.px(16), self.px(14)
        chevron = ((big * 0.26, high * 0.38), (big * 0.5, high * 0.64), (big * 0.74, high * 0.38))
        self.element(
            "glasschevron", (big, high), (glass.Stroke(chevron, thick, SOFT),),
            ((("disabled",), (glass.Stroke(chevron, thick, MUTED, 0.6),)), (("active",), (glass.Stroke(chevron, thick, TEXT),))), sticky="",
        )

    def _marks(self) -> None:
        """A tick box, a round one, and the switch on the top bar."""
        box, gap = self.px(16), self.px(7)
        size = (box + gap, box)
        square, round_ = (0, 0, box, box), box / 2
        off = glass.Shape(fill=FIELD, radius=self.px(4), inset=0.4, zone=self.px(3), edge=EDGE, edge_alpha=1.0)
        on = glass.Shape(fill=ACCENT, radius=self.px(4), glow=0.2, rim=0.45, edge="#3d1a04", edge_alpha=0.6)
        tick = glass.Stroke(((box * 0.24, box * 0.52), (box * 0.43, box * 0.71), (box * 0.76, box * 0.31)), max(1.6, 1.9 * self.scale), ON_COLOR)
        dim = glass.Shape(fill=mix(FIELD, BG, 0.5), radius=self.px(4), edge=EDGE, edge_alpha=0.5)
        self.element(
            "glasscheck", size, ((off, square),),
            ((("disabled", "selected"), ((dim, square), glass.Stroke(tick.points, tick.width, MUTED))), (("disabled",), ((dim, square),)), (("selected",), ((on, square), tick))),
            sticky="",
        )
        dot_box = (box * 0.31, box * 0.31, box * 0.69, box * 0.69)
        dot = glass.Shape(fill=ON_COLOR, radius=round_)
        self.element(
            "glassradio", size, ((glass.Shape(fill=FIELD, radius=round_, inset=0.4, zone=self.px(3), edge=EDGE, edge_alpha=1.0), square),),
            (
                (("disabled",), ((glass.Shape(fill=mix(FIELD, BG, 0.5), radius=round_, edge=EDGE, edge_alpha=0.5), square),)),
                (("selected",), ((glass.Shape(fill=ACCENT, radius=round_, glow=0.2, rim=0.45, edge="#3d1a04", edge_alpha=0.6), square), (dot, dot_box))),
            ),
            sticky="",
        )
        wide, tall, gap = self.px(32), self.px(18), self.px(9)
        knob = glass.Shape(fill="#f2f6f7", radius=tall, rim=0.8, edge_alpha=0.25, shadow=0.45, drop=1)
        inset = max(2, self.px(2))
        left, right = (inset, inset, tall - inset, tall - inset + 1), (wide - tall + inset, inset, wide - inset, tall - inset + 1)
        track = (0, 0, wide, tall)
        self.element(
            "glassswitch", (wide + gap, tall),
            ((glass.Shape(alpha=0.14, radius=tall, inset=0.3, zone=self.px(5), edge_alpha=0.45), track), (knob, left)),
            ((("selected",), ((glass.Shape(fill=ACCENT, radius=tall, glow=0.18, rim=0.35, edge="#3d1a04", edge_alpha=0.6), track), (knob, right))),),
            sticky="",
        )

    def _scrollbars(self) -> None:
        """A slim rounded thumb with clear space either side of it, and nothing else: no arrows, and a trough
        the colour of whatever it runs along."""
        thick, margin = self.px(6), self.px(3)
        across, long, least = thick + 2 * margin, self.px(72), self.px(28)
        ends = thick // 2 + 1

        def thumb(alpha: float, upright: bool) -> tuple:
            shape = glass.Shape(alpha=alpha, radius=thick / 2)
            return ((shape, (margin, 0, margin + thick, long) if upright else (0, margin, long, margin + thick)),)

        for name, upright in (("glassv.thumb", True), ("glassh.thumb", False)):
            states = ((("pressed",), thumb(0.50, upright)), (("active",), thumb(0.42, upright)))
            if upright:
                self.element(name, (across, long), thumb(0.26, True), states, border=(0, ends, 0, ends), sticky="nsew", width=across, height=least)
            else:
                self.element(name, (long, across), thumb(0.26, False), states, border=(ends, 0, ends, 0), sticky="nsew", width=least, height=across)

    def _panels(self) -> None:
        """The surfaces: the item card with its title strip, the well the inventory sits in, the boxes on the
        card, and the bars along the top and bottom, which float clear of the window's edges."""
        radius, pad, drop = self.px(CARD_RADIUS), self.px(CARD_PAD), self.px(CARD_DROP)
        band = pad + self.px(BANNER_HEIGHT)
        self.element(
            "glasscard", (2 * radius + self.tall, band + self.tall + radius + drop),
            (glass.Shape(fill=CARD, radius=radius, band=band, band_fill=BANNER, glow=0.16, zone=band * 0.7, rim=0.50, edge="#31505c", edge_alpha=0.9, shadow=0.42, drop=drop),),
            border=(radius, band + 1, radius, radius + drop), sticky="nsew", width=2 * radius + 2, height=band + radius + drop + 2,
            padding=(pad, pad, pad, pad + drop),
        )
        radius, pad = self.px(WELL_RADIUS), self.px(WELL_PAD)
        self.element(
            "glasswell", (2 * radius + self.tall, 2 * radius + self.tall),
            (glass.Shape(fill=WELL, radius=radius, inset=0.55, zone=pad, edge="#051820", edge_alpha=1.0),),
            border=radius, sticky="nsew", width=2 * radius + 2, height=2 * radius + 2, padding=pad,
        )
        radius = self.px(BOX_RADIUS)
        self.element(
            "glassbox", (2 * radius + self.tall, 2 * radius + self.wide),
            (glass.Shape(fill=CARD_BOX, radius=radius, rim=0.26, edge_alpha=0.40),),
            border=radius, sticky="nsew", width=2 * radius + 2, height=2 * radius + 2, padding=(self.px(10), self.px(8)),
        )
        radius, drop = self.px(BAR_RADIUS), self.px(BAR_DROP)
        self.element(
            "glassbarpanel", (2 * radius + 2 * self.tall, 2 * radius + self.px(12) + drop),
            (glass.Shape(fill=BAR, radius=radius, glow=0.05, rim=0.30, edge="#4b423b", edge_alpha=0.9, shadow=0.45, drop=drop),),
            border=(radius, radius, radius, radius + drop), sticky="nsew", width=2 * radius + 2, height=2 * radius + 2 + drop,
            padding=(self.px(12), self.px(3), self.px(12), self.px(3) + drop),
        )


def look_of(value: object) -> str:
    """A look the editor has, from what the settings file says: anything it doesn't know is the default."""
    return value if value in LOOKS else DEFAULT_LOOK


def use(root: tk.Tk, simple: bool, light_theme: str, look: str = DEFAULT_LOOK) -> None:
    """Switch the whole app between Simple mode's theme, in the look asked for, and the normal (light) one."""
    style = ttk.Style(root)
    if simple and look == "glass":
        _install_glass(style)
    style.theme_use((GLASS_THEME if look == "glass" else THEME) if simple else light_theme)
    root.option_clear()
    if simple:
        for pattern, value in _DARK_OPTIONS.items():
            root.option_add(pattern, value)
    set_dark_title_bar(root, simple)


def is_active(widget: tk.Misc) -> bool:
    """Whether one of Simple mode's themes is in use."""
    return ttk.Style(widget).theme_use() in (THEME, GLASS_THEME)


def is_glass(widget: tk.Misc) -> bool:
    """Whether Simple mode is showing in the Liquid Glass look."""
    return ttk.Style(widget).theme_use() == GLASS_THEME


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


def _glass_settings(fonts: GameFonts, row_height: int, item_row_height: int) -> dict:
    """Liquid Glass: the same style names as the original look, drawn with the pictures ``Looks`` makes."""
    # A glass shape is a picture with see-through corners, so what shows there is the style's own background:
    # every style that uses one says which surface it sits on (the teal, the card, a bar...), in every state.
    def on(surface: str) -> list:
        return [("disabled", surface), ("pressed", surface), ("active", surface), ("focus", surface)]

    def button(surface: str, element: str = "glassbtn", foreground: str = TEXT, faded: str | None = None) -> dict:
        return {
            "layout": [(element, {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})],
            "configure": {"background": surface, "foreground": foreground, "font": fonts.heading, "anchor": "center"},
            "map": {"background": on(surface), "foreground": [("disabled", faded or mix(foreground, surface, 0.62))]},
        }

    def menu_button(surface: str, element: str, foreground: str) -> dict:
        return {
            "layout": [(element, {"sticky": "nsew", "children": [
                ("glasschevron", {"side": "right", "sticky": ""}),
                ("Menubutton.label", {"side": "left", "sticky": ""}),
            ]})],
            "configure": {"background": surface, "foreground": foreground, "font": fonts.heading},
            "map": {"background": on(surface), "foreground": [("disabled", mix(foreground, surface, 0.62))]},
        }

    def tab(surface: str, element: str, picked: str = TEXT, **more) -> dict:
        return {
            "layout": [(element, {"sticky": "nsew", "children": [("Toolbutton.label", {"sticky": "nsew"})]})],
            "configure": {"background": surface, "foreground": MUTED, "font": fonts.heading, "anchor": "center", **more},
            "map": {"background": on(surface) + [("selected", surface)], "foreground": [("disabled", mix(MUTED, surface, 0.5)), ("selected", picked), ("active", SOFT)]},
        }

    def label(background: str, foreground: str, font: tkfont.Font | None = None) -> dict:
        return {"configure": {"background": background, "foreground": foreground, **({"font": font} if font else {})}}

    def field(kind: str, surface: str) -> dict:
        """A text box (Entry), a number box (Spinbox) or a list box (Combobox) on ``surface``."""
        text = (f"{kind}.textarea", {"sticky": "nswe"})
        if kind == "Spinbox":
            inside = [("null", {"side": "right", "sticky": "", "children": [
                ("glass.uparrow", {"side": "top", "sticky": "e"}), ("glass.downarrow", {"side": "bottom", "sticky": "e"}),
            ]}), text]
        elif kind == "Combobox":
            inside = [("glasschevron", {"side": "right", "sticky": ""}), text]
        else:
            inside = [text]
        return {
            "layout": [("glassfield", {"sticky": "nswe", "children": inside})],
            "configure": {
                "fieldbackground": FIELD, "foreground": TEXT, "background": surface, "insertcolor": TEXT,
                "selectbackground": SELECT, "selectforeground": TEXT, "arrowcolor": SOFT,
            },
            "map": {
                "background": on(surface) + [("readonly", surface)],
                "fieldbackground": [("disabled", mix(FIELD, BG, 0.5)), ("readonly", FIELD)],
                "foreground": [("disabled", MUTED)],
            },
        }

    def plain_field(surface: str, foreground: str, focus: str, **more) -> dict:
        """A number that's typed over in place, with no box round it until it's being changed."""
        return {
            "layout": [("Entry.field", {"sticky": "nswe", "border": "1", "children": [("Entry.padding", {"sticky": "nswe", "children": [("Entry.textarea", {"sticky": "nswe"})]})]})],
            "configure": {
                "fieldbackground": surface, "background": surface, "foreground": foreground, "insertcolor": foreground,
                "bordercolor": surface, "lightcolor": surface, "darkcolor": surface, "selectbackground": SELECT, **more,
            },
            "map": {"bordercolor": [("focus", focus)], "fieldbackground": [("disabled", surface)], "foreground": [("disabled", MUTED)], "lightcolor": [("focus", surface)]},
        }

    def mark(surface: str, element: str, kind: str, foreground: str = TEXT, **more) -> dict:
        """A tick box, a round box or a switch, with its words beside it."""
        return {
            "layout": [(f"{kind}.padding", {"sticky": "nswe", "children": [(element, {"side": "left", "sticky": ""}), (f"{kind}.label", {"side": "left", "sticky": "w"})]})],
            "configure": {"background": surface, "foreground": foreground, **more},
            "map": {"background": on(surface) + [("selected", surface)], "foreground": [("disabled", MUTED), ("active", TEXT)]},
        }

    def scrollbar(surface: str, way: str) -> dict:
        trough = ("Vertical.Scrollbar.trough", "ns") if way == "v" else ("Horizontal.Scrollbar.trough", "we")
        return {
            "layout": [(trough[0], {"sticky": trough[1], "children": [(f"glass{way}.thumb", {"sticky": "nswe"})]})],
            "configure": {**_flat(surface), "troughcolor": surface},
            "map": {"background": on(surface)},
        }

    def panel(element: str, around: str) -> dict:
        """A rounded surface: ``around`` is what shows past its corners."""
        return {"layout": [(element, {"sticky": "nsew"})], "configure": {"background": around}}

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
        "TButton": button(BG),
        "Accent.TButton": button(BG, "glassaccent", ON_COLOR, "#d9b79b"),
        "TMenubutton": menu_button(BG, "glassbtn", TEXT),
        "TEntry": field("Entry", BG),
        "TSpinbox": field("Spinbox", BG),
        "TCombobox": field("Combobox", BG),
        "TCheckbutton": mark(BG, "glasscheck", "Checkbutton"),
        "TRadiobutton": mark(BG, "glassradio", "Radiobutton"),
        "Vertical.TScrollbar": scrollbar(BG, "v"),
        "Horizontal.TScrollbar": scrollbar(BG, "h"),
        "Well.Vertical.TScrollbar": scrollbar(WELL, "v"),
        "Card.Vertical.TScrollbar": scrollbar(CARD, "v"),
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
        # The bars along the top and bottom of the window: dark glass, floating clear of the window's edges.
        "BarPanel.TFrame": panel("glassbarpanel", BG),
        "Bar.TFrame": {"configure": {"background": BAR}},
        "Bar.TLabel": label(BAR, SOFT),
        "BarMuted.TLabel": label(BAR, MUTED, fonts.small),
        "BarRunning.TLabel": label(BAR, ERROR, fonts.heading),
        "BarClosed.TLabel": label(BAR, SUCCESS, fonts.heading),
        "BarChanges.TLabel": label(BAR, ACCENT, fonts.heading),
        "Bar.TButton": button(BAR, "glassbar", SOFT),
        "BarAccent.TButton": button(BAR, "glassaccent", ON_COLOR, "#d9b79b"),
        "Bar.TMenubutton": menu_button(BAR, "glassbar", TEXT),
        "Bar.TCheckbutton": mark(BAR, "glassswitch", "Checkbutton", SOFT, font=fonts.heading, padding=(6, 6)),
        "BarTab.Toolbutton": tab(BAR, "glasstab", "#f6e9da"),
        "Underline.TFrame": {"configure": {"background": ACCENT}},
        "BarLine.TFrame": {"configure": {"background": BAR}},
        "Currency.TEntry": plain_field(BAR, TEXT, ACCENT, padding=(2, 0)),
        # The hero screen.
        "Game.TFrame": {"configure": {"background": BG}},
        "Well.TFrame": {"configure": {"background": WELL}},
        "WellPanel.TFrame": panel("glasswell", BG),
        "Caption.TLabel": label(BG, HEADING, fonts.heading),
        "GearPower.TLabel": label(BG, POWER, fonts.huge),
        "GearPart.TLabel": label(BG, POWER_PART, fonts.heading),
        "Message.TLabel": label(BG, SOFT, fonts.small),
        "MessageError.TLabel": label(BG, ERROR, fonts.small),
        "MessageGood.TLabel": label(BG, SUCCESS, fonts.small),
        "Big.TLabel": label(BG, TEXT, fonts.title),
        "Body.TLabel": label(BG, SOFT, fonts.body),
        "Level.TEntry": plain_field(BG, LEVEL, LEVEL, selectbackground="#4f2463", padding=(0, 0)),
        "Stat.TEntry": field("Entry", BG),
        "Chip.Toolbutton": tab(BG, "glasschip"),
        # The item card.
        "CardPanel.TFrame": panel("glasscard", BG),
        "Card.TFrame": {"configure": {"background": CARD}},
        "Card.TLabel": label(CARD, SOFT, fonts.body),
        "CardMuted.TLabel": label(CARD, MUTED, fonts.small),
        "CardTitle.TLabel": label(CARD, TEXT, fonts.title),
        "CardPower.TLabel": label(CARD, TEXT, fonts.big),
        "CardHeading.TLabel": label(CARD, HEADING, fonts.heading),
        "CardError.TLabel": label(CARD, ERROR, fonts.small),
        "CardGood.TLabel": label(CARD, SUCCESS, fonts.small),
        "CardWarn.TLabel": label(CARD, WARN, fonts.small),
        "Box.TFrame": panel("glassbox", CARD),
        "Box.TLabel": label(CARD_BOX, SOFT, fonts.small),
        "BoxTitle.TLabel": label(CARD_BOX, TEXT, fonts.heading),
        "Box.TButton": button(CARD_BOX, "glassbtn.card"),
        "Card.TButton": button(CARD, "glassbtn.card"),
        "CardAccent.TButton": button(CARD, "glassaccent", ON_COLOR, "#d9b79b"),
        "Card.TSpinbox": field("Spinbox", CARD),
        "Card.TEntry": field("Entry", CARD),
    }
    for rarity, color in RARITY_TILE.items():
        settings[f"{rarity}.Rarity.Toolbutton"] = {
            "layout": [(f"glassrarity.{rarity.lower()}", {"sticky": "nsew", "children": [("Toolbutton.label", {"sticky": "nsew"})]})],
            "configure": {"background": CARD, "foreground": color, "font": fonts.heading, "anchor": "center"},
            "map": {"background": on(CARD) + [("selected", CARD)], "foreground": [("disabled", MUTED), ("selected", ON_COLOR)]},
        }
    return settings


def _classic_settings(fonts: GameFonts, row_height: int, item_row_height: int) -> dict:
    """The original look: flat colours and square corners, every widget drawn by ttk itself."""
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
    settings.update({
        # Styles that came with the glass look, as the original look draws them: the same flat surfaces as before.
        "BarPanel.TFrame": {"configure": {"background": BAR}},
        "WellPanel.TFrame": {"configure": {"background": WELL}},
        "CardPanel.TFrame": {"configure": {"background": "#2a3d46"}},
        "Box.TButton": button(BUTTON, BUTTON_HOVER, BUTTON_PRESSED, TEXT, padding=(10, 5)),
        "BarAccent.TButton": button(ACCENT, ACCENT_HOVER, ACCENT_PRESSED, ON_COLOR, padding=(16, 6)),
        "CardAccent.TButton": button(ACCENT, ACCENT_HOVER, ACCENT_PRESSED, ON_COLOR, padding=(16, 6)),
    })
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
