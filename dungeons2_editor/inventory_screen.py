"""Simple mode's hero screen, laid out like Minecraft Dungeons II's own inventory.

The gear the hero has on sits on the left (weapons, armor, artifacts and talismans), the rest of the
inventory fills the middle, and the card on the right shows whatever is picked: its power, rarity and
what it does, with buttons to change it, like the game's item card. Level, XP and gear power run along
the top, and the currencies go in the window's top bar (``make_currency_strip``).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from . import document as doc
from . import game_style as gs
from .game_art import EMPTY_TILE, RARITY_TILE, Art, icon_for, mix, tile_fill
from .game_style import GameFonts
from .hero import (
    ITEM_SORTS,
    MAX_ITEM_POWER,
    MAX_STACK,
    MAX_STAT,
    RARITIES,
    STAT_CAPS,
    STAT_MINIMUMS,
    GameItem,
    GearSlot,
    Hero,
    Item,
    attribute_label,
    format_amount,
    game_item,
    gear_power,
    local_name,
    name_is_known,
    slots_for,
    sort_items,
    use_local_names,
)
from .hero_editing import SAVE_REMINDER, HeroEditing, number_text
from .icons import IconLibrary
from .item_picker import slot_open
from .layout import fit_to_contents
from .my_items import NAMES_FILE, load_names, save_names

TILE = 64  # a gear tile, in pixels at 96 DPI
GAP = 10
CARD_WIDTH = 330

# The gear on the left, top to bottom, as in the game.
SECTIONS = (
    ("WEAPONS", "sword", ("Melee", "Ranged")),
    ("ARMOR", "chestplate", ("Armor",)),
    ("ARTIFACTS", "artifact", ("Artifact",)),
    ("TALISMANS", "talisman", ("Talisman",)),
)
# What gear power is made of, with the game's icons.
POWER_PARTS = (
    ("Melee", "sword", "Melee weapon"),
    ("Ranged", "bow", "Ranged weapon"),
    ("Armor", "chestplate", "All four armor pieces added up"),
    ("Artifact", "artifact", "All three artifacts added up"),
)
# The currencies in the top bar, in the game's order and colours.
CURRENCIES = (  # name, icon, colour, digits shown
    ("EnchantmentPoints", "enchant", "#8fd3ff", 3),
    ("Emeralds", "emerald", "#3fcf52", 5),
    ("SpringStone", "echo", "#b86cf0", 3),
)
STAT_ICONS = {
    "EnchantmentPoints": ("enchant", "#8fd3ff"),
    "Emeralds": ("emerald", "#3fcf52"),
    "SpringStone": ("echo", "#b86cf0"),
    "Level": ("power", gs.LEVEL),
    "XP": ("xp", "#a6e05a"),
}
FILTERS = (
    ("All", "ALL"),
    ("Melee", "MELEE"),
    ("Ranged", "RANGED"),
    ("Armor", "ARMOR"),
    ("Artifact", "ARTIFACTS"),
    ("Talisman", "TALISMANS"),
    ("Merchant", "MERCHANT"),
)
KIND_NAMES = {"Melee": "Melee weapon", "Ranged": "Ranged weapon", "Armor": "Armor", "Artifact": "Artifact", "Talisman": "Talisman"}
ENCHANTABLE = ("Melee", "Ranged", "Armor")  # artifacts and talismans can't be enchanted


def describe(item: Item, known: GameItem | None) -> str:
    """What the item does, for its card: a Unique's effect, a talisman's, or what Unique rarity would give."""
    if known is None:
        return ""
    if item.kind == "Talisman" and known.effect:
        return f"At level 3: {known.effect}"
    if item.rarity == "Unique" and known.unique_effect:
        return known.unique_effect
    if known.unique:
        return f"Make it Unique to get the {known.unique}." + (f" {known.unique_effect}" if known.unique_effect else "")
    return ""


def slot_noun(slot: GearSlot) -> str:
    """'melee weapon', 'helmet', 'artifact': what goes in a slot."""
    if slot.piece:
        return slot.piece.lower()
    return KIND_NAMES.get(slot.kind, slot.kind).lower()


def fit_lines(text: str, font: Any, width: int, lines: int = 2) -> str:
    """``text`` wrapped to ``width`` pixels of ``font``, at most ``lines`` lines, cut short with "…"."""

    def cut(line: str) -> str:
        if font.measure(line) <= width:
            return line
        while line and font.measure(line + "…") > width:
            line = line[:-1]
        return line.rstrip() + "…"

    wrapped: list[str] = []
    for word in text.split():
        if wrapped and font.measure(f"{wrapped[-1]} {word}") <= width:
            wrapped[-1] += f" {word}"
        else:
            wrapped.append(word)
    if len(wrapped) > lines:
        wrapped = wrapped[:lines]
        wrapped[-1] += "…"
    return "\n".join(cut(line) for line in wrapped)


class _Tip:
    """A small dark box with a hint, shown when the pointer rests on (part of) a widget."""

    def __init__(self, widget: tk.Misc, text_at: Callable[[tk.Event], str | None], font: Any):
        self.widget = widget
        self.text_at = text_at
        self.font = font
        self.window: tk.Toplevel | None = None
        self.job: str | None = None
        self.text: str | None = None
        widget.bind("<Motion>", self._moved, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _moved(self, event: tk.Event) -> None:
        text = self.text_at(event)
        if text == self.text:
            return
        self._hide()
        self.text = text
        if text:
            self.job = self.widget.after(500, self._show)

    def _show(self) -> None:
        self.job = None
        if not self.text or not self.widget.winfo_exists():
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(
            window, text=self.text, justify="left", background=gs.CARD, foreground=gs.TEXT, font=self.font,
            padx=8, pady=5, highlightthickness=1, highlightbackground=gs.EDGE, wraplength=320,
        ).pack()
        window.geometry(f"+{self.widget.winfo_pointerx() + 14}+{self.widget.winfo_pointery() + 18}")
        self.window = window

    def _hide(self, _event: tk.Event | None = None) -> None:
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window is not None:
            self.window.destroy()
            self.window = None
        self.text = None


class InventoryScreen(HeroEditing, ttk.Frame):
    """The hero, as the game's inventory screen shows it. Works like the Hero tab (same changes, same
    checks), but in Simple mode only: the game's caps apply and gear slots open with level."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None],
        app_title: str,
        icons: IconLibrary,
        fonts: GameFonts,
        art: Art,
        get_pictures: Callable[[], None],
        catalog_heroes: Callable[[], list[Hero]],
        empty_title: tk.StringVar,
        empty_text: tk.StringVar,
        names_file: Path = NAMES_FILE,
    ):
        super().__init__(master, style="Game.TFrame")
        self.on_change = on_change
        self.app_title = app_title
        self.icons = icons
        self.fonts = fonts
        self.art = art
        self.get_pictures = get_pictures
        self.catalog_heroes = catalog_heroes
        self.names_file = Path(names_file)  # names you gave items the editor doesn't know
        self.advanced = False  # Simple mode: the game's caps and level checks apply
        self.hero: Hero | None = None
        self.active = False  # on screen; while it isn't, changes are drawn when it next is
        self.selected: int | None = None  # the inventory entry on the card
        self._shown: int | None = None  # the entry whose values are in the card's fields
        self.picked_slot: GearSlot | None = None  # an empty gear slot on the card
        self.card_mode = "hero"  # what the card shows: "hero", "item", "slot" or "stats"
        self.banner_text = ""
        self.stat_vars: dict[str, tk.StringVar] = {}
        self._fixed_vars = {name: tk.StringVar() for name in ("Level", "XP", "EnchantmentPoints", "Emeralds", "SpringStone")}
        self._stat_entries: dict[str, list[ttk.Entry]] = {}
        self.power_var = tk.StringVar()
        self.count_var = tk.StringVar()
        self.rarity_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="All")
        self.sort_var = tk.StringVar(value="Most powerful")
        self._guessed_slot_ok = False
        self._slot_list: list[GearSlot] = []
        self._gear_hits: list[tuple[tuple, GearSlot]] = []  # (tile box, slot)
        self._item_hits: list[tuple[tuple, tuple, int]] = []  # (box with caption, tile box, inventory index)
        self._inventory_width = 0
        self._redraw_job: str | None = None
        self.tile = art.px(TILE)
        self._build(empty_title, empty_text)

    # ------------------------------------------------------------------ layout

    def _build(self, empty_title: tk.StringVar, empty_text: tk.StringVar) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_header()
        self.stats_message_var = tk.StringVar()
        self.stats_message = ttk.Label(self, textvariable=self.stats_message_var, style="Message.TLabel", padding=(22, 0, 22, 2))
        self.stats_message.grid(row=1, column=0, sticky="ew")
        self.body = ttk.Frame(self, style="Game.TFrame")
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.columnconfigure(1, weight=1)
        self.body.rowconfigure(0, weight=1)
        self._build_gear()
        self._build_inventory()
        self._build_card()

        self.empty = ttk.Frame(self, style="Game.TFrame", padding=(40, 40))
        ttk.Label(self.empty, textvariable=empty_title, style="Big.TLabel").pack(anchor="w")
        ttk.Label(self.empty, textvariable=empty_text, style="Body.TLabel", wraplength=self.art.px(640), justify="left").pack(anchor="w", pady=(10, 0))

    def _build_header(self) -> None:
        self.header = header = ttk.Frame(self, style="Game.TFrame", padding=(22, 12, 22, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)

        level = ttk.Frame(header, style="Game.TFrame")
        level.grid(row=0, column=0, sticky="nw")
        ttk.Label(level, text="LEVEL", style="Caption.TLabel").grid(row=0, column=0, sticky="w")
        self.level_entry = ttk.Entry(level, textvariable=self._fixed_vars["Level"], style="Level.TEntry", font=self.fonts.huge, width=3)
        self.level_entry.grid(row=1, column=0, sticky="w")
        xp = ttk.Frame(level, style="Game.TFrame")
        xp.grid(row=2, column=0, sticky="w")
        ttk.Label(xp, text="XP", style="Caption.TLabel", image=self.art.icon("xp", "#a6e05a", 1), compound="left").pack(side="left")
        self.xp_entry = ttk.Entry(xp, textvariable=self._fixed_vars["XP"], style="Stat.TEntry", font=self.fonts.body, width=9)
        self.xp_entry.pack(side="left", padx=(6, 0))
        self._bind_stat(self.level_entry, "Level", "Your hero's level. In testing, level 10 stuck but level 100 was put back to 1.")
        self._bind_stat(self.xp_entry, "XP", "Experience towards the next level.")

        power = ttk.Frame(header, style="Game.TFrame")
        power.grid(row=0, column=1, sticky="nw", padx=(self.art.px(56), 0))
        ttk.Label(power, text="GEAR POWER", style="Caption.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(power, image=self.art.icon("power", gs.POWER, 2)).grid(row=1, column=0, sticky="w", padx=(0, 6))
        self.gear_power_var = tk.StringVar(value="–")
        number = ttk.Label(power, textvariable=self.gear_power_var, style="GearPower.TLabel")
        number.grid(row=1, column=1, sticky="w")
        _Tip(number, lambda _event: "The average power of the weapons, armor and artifacts your hero has on, as the game "
             "works it out. Talismans don't count.", self.fonts.small)
        ttk.Label(power, text="▸", style="GearPart.TLabel").grid(row=1, column=2, padx=(8, 6))
        parts = ttk.Frame(power, style="Game.TFrame")
        parts.grid(row=1, column=3, sticky="w")
        self.power_part_vars: dict[str, tk.StringVar] = {}
        for column, (kind, icon, hint) in enumerate(POWER_PARTS):
            picture = ttk.Label(parts, image=self.art.icon(icon, gs.POWER_PART, 2))
            picture.grid(row=0, column=column, padx=self.art.px(9))
            var = self.power_part_vars[kind] = tk.StringVar(value="0")
            value = ttk.Label(parts, textvariable=var, style="GearPart.TLabel")
            value.grid(row=1, column=column)
            for widget in (picture, value):
                _Tip(widget, lambda _event, hint=hint: hint, self.fonts.small)

        buttons = ttk.Frame(header, style="Game.TFrame")
        buttons.grid(row=0, column=3, sticky="ne")
        ttk.Button(buttons, text="STATS & TOWN", command=self.show_stats).pack(side="left")
        ttk.Button(buttons, text="PRESETS…", command=self.open_presets).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="+ ADD ITEMS…", style="Accent.TButton", command=self.open_add_items).pack(side="left", padx=(8, 0))

    def make_currency_strip(self, parent: tk.Misc) -> ttk.Frame:
        """The currencies (enchantment points, emeralds, echo shards), to put in the window's top bar."""
        strip = ttk.Frame(parent, style="Bar.TFrame")
        self._currency_icons: list[tuple[ttk.Label, str, str, str]] = []
        for name, icon, color, digits in CURRENCIES:
            picture = ttk.Label(strip, style="Bar.TLabel")
            picture.pack(side="left", padx=(16, 4))
            self._currency_icons.append((picture, name, icon, color))
            entry = ttk.Entry(strip, textvariable=self._fixed_vars[name], style="Currency.TEntry", font=self.fonts.number, width=digits)
            entry.pack(side="left")
            cap = STAT_CAPS.get(name)
            if name == "SpringStone" and cap:
                ttk.Label(strip, text=f"/{cap}", style="BarMuted.TLabel").pack(side="left")
            hint = f"{attribute_label(name)}. Click to change" + (f"; the game's cap is {format_amount(cap)}." if cap else ".")
            self._bind_stat(entry, name, hint)
        self._show_currency_icons()
        return strip

    def _show_currency_icons(self) -> None:
        for picture, name, icon, color in getattr(self, "_currency_icons", []):
            # A picture in the icons folder (Emeralds.png, ...) wins over the editor's own.
            picture.configure(image=self.icons.image(name, self.art.px(20)) or self.art.icon(icon, color, 2))

    def _bind_stat(self, entry: ttk.Entry, name: str, hint: str) -> None:
        self._stat_entries.setdefault(name, []).append(entry)
        entry.bind("<Return>", lambda _event: self._apply_stat(name))
        entry.bind("<FocusOut>", lambda _event: self._apply_stat(name))
        entry.bind("<Up>", lambda _event: self._nudge_stat(name, 1))
        entry.bind("<Down>", lambda _event: self._nudge_stat(name, -1))
        entry.bind("<MouseWheel>", lambda event: self._nudge_stat(name, 1 if event.delta > 0 else -1) if self.focus_get() is entry else None)
        _Tip(entry, lambda _event: hint, self.fonts.small)

    def _build_gear(self) -> None:
        panel = ttk.Frame(self.body, style="Game.TFrame", padding=(22, 6, 12, 14))
        panel.grid(row=0, column=0, sticky="nw")
        tile, gap = self.tile, self.art.px(GAP)
        self._heading = self.art.px(26)
        width = 4 * tile + 3 * gap + 8
        height = len(SECTIONS) * (self._heading + tile + gap) + 8
        self.gear_canvas = tk.Canvas(panel, width=width, height=height, background=gs.BG, highlightthickness=0)
        self.gear_canvas.pack(anchor="nw")
        self.gear_canvas.bind("<Button-1>", self._on_gear_click)
        self.gear_canvas.bind("<Double-1>", self._on_gear_double)
        self.gear_canvas.bind("<Button-3>", lambda event: self._context_menu(event, self._gear_slot_at(event)))
        self.gear_canvas.bind("<Motion>", lambda event: self._hover(self.gear_canvas, [box for box, _slot in self._gear_hits], event), add="+")
        self.gear_canvas.bind("<Leave>", lambda _event: self._hover(self.gear_canvas, [], None), add="+")
        _Tip(self.gear_canvas, self._gear_tip, self.fonts.small)

    def _build_inventory(self) -> None:
        panel = ttk.Frame(self.body, style="Game.TFrame", padding=(8, 6, 8, 14))
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        top = ttk.Frame(panel, style="Game.TFrame")
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text="INVENTORY", style="Caption.TLabel").pack(side="left")
        self.count_text = tk.StringVar()
        ttk.Label(top, textvariable=self.count_text, style="Message.TLabel").pack(side="left", padx=(8, 0))
        self.sort_button = ttk.Menubutton(top, text="", style="TMenubutton")
        sort_menu = tk.Menu(self.sort_button, tearoff=False)
        for name in ITEM_SORTS:
            sort_menu.add_radiobutton(label=name, value=name, variable=self.sort_var, command=self._resort)
        self.sort_button["menu"] = sort_menu
        self.sort_button.pack(side="right")
        self.pictures_button = ttk.Button(top, text="GET PICTURES…", command=self.get_pictures)
        self._resort(draw=False)

        chips = ttk.Frame(panel, style="Game.TFrame")
        chips.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 6))
        for key, text in FILTERS:
            ttk.Radiobutton(chips, text=text, value=key, variable=self.filter_var, style="Chip.Toolbutton", command=self._draw_inventory).pack(side="left", padx=(0, 4))

        cell = self.tile + self.art.px(18)
        self.inventory_canvas = tk.Canvas(
            panel, width=4 * cell + self.art.px(24), height=self.art.px(200), background=gs.WELL, highlightthickness=0,
            yscrollincrement=self.art.px(30),
        )
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.inventory_canvas.yview)
        self.inventory_canvas.configure(yscrollcommand=scroll.set)
        self.inventory_canvas.grid(row=2, column=0, sticky="nsew")
        scroll.grid(row=2, column=1, sticky="ns")
        canvas = self.inventory_canvas
        canvas.bind("<Configure>", self._on_inventory_resize)
        canvas.bind("<Button-1>", self._on_inventory_click)
        canvas.bind("<Double-1>", self._on_inventory_double)
        canvas.bind("<Button-3>", lambda event: self._context_menu(event, self._inventory_index_at(event)))
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-2 if event.delta > 0 else 2, "units"))
        canvas.bind("<Delete>", lambda _event: self.delete_item())
        canvas.bind("<Motion>", lambda event: self._hover(canvas, [tile for _box, tile, _index in self._item_hits], event), add="+")
        canvas.bind("<Leave>", lambda _event: self._hover(canvas, [], None), add="+")
        _Tip(canvas, self._inventory_tip, self.fonts.small)

    def _build_card(self) -> None:
        width = self.art.px(CARD_WIDTH)
        self._card_width = width
        wrap = width - 34
        outer = ttk.Frame(self.body, style="Game.TFrame", padding=(10, 6, 22, 14))
        outer.grid(row=0, column=2, sticky="nsew")
        border = ttk.Frame(outer, style="CardBorder.TFrame", padding=1)
        border.pack(fill="both", expand=True)
        self.card = ttk.Frame(border, style="Card.TFrame")
        self.card.pack(fill="both", expand=True)
        self.banner = tk.Canvas(self.card, width=width, height=self.art.px(28), background=gs.CARD, highlightthickness=0)
        self.banner.pack(fill="x")
        content = ttk.Frame(self.card, style="Card.TFrame", padding=(16, 12, 16, 14))
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)

        head = ttk.Frame(content, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        top = ttk.Frame(head, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="nw")
        self.card_power_var = tk.StringVar()
        ttk.Label(top, textvariable=self.card_power_var, style="CardPower.TLabel").pack(side="left")
        self.badge = tk.Label(top, font=self.fonts.heading, padx=8, pady=1, borderwidth=0)
        picture_size = self.art.px(72)
        self.card_name_var = tk.StringVar()
        ttk.Label(head, textvariable=self.card_name_var, style="CardTitle.TLabel", wraplength=wrap - picture_size, justify="left").grid(
            row=1, column=0, sticky="nw", pady=(2, 0)
        )
        self.card_kind_var = tk.StringVar()
        ttk.Label(head, textvariable=self.card_kind_var, style="CardMuted.TLabel", wraplength=wrap - picture_size, justify="left").grid(
            row=2, column=0, sticky="nw"
        )
        self.card_picture = ttk.Label(head, style="Card.TLabel", anchor="center")
        self.card_picture.grid(row=0, column=1, rowspan=3, sticky="ne", padx=(8, 0))
        self.card_text_var = tk.StringVar()
        self.card_text = ttk.Label(content, textvariable=self.card_text_var, style="Card.TLabel", wraplength=wrap, justify="left")
        self.card_text.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.item_box = ttk.Frame(content, style="Card.TFrame")
        self.item_box.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.item_box.columnconfigure(0, weight=1)
        ttk.Label(self.item_box, text="RARITY", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
        rarities = ttk.Frame(self.item_box, style="Card.TFrame")
        rarities.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.rarity_buttons = []
        for rarity in RARITIES:
            button = ttk.Radiobutton(
                rarities, text=rarity.upper(), value=rarity, variable=self.rarity_var, style=f"{rarity}.Rarity.Toolbutton",
                command=lambda: self._apply_item(rarity=self.rarity_var.get()),
            )
            button.pack(side="left", padx=(0, 4))
            self.rarity_buttons.append(button)
        numbers = ttk.Frame(self.item_box, style="Card.TFrame")
        numbers.grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(numbers, text="POWER", style="CardHeading.TLabel").pack(side="left")
        self.power_entry = ttk.Spinbox(
            numbers, textvariable=self.power_var, from_=0, to=MAX_ITEM_POWER, increment=1, width=7, style="Card.TSpinbox",
            command=self._apply_numbers, font=self.fonts.body,
        )
        self.power_entry.pack(side="left", padx=(8, 16))
        ttk.Label(numbers, text="COUNT", style="CardHeading.TLabel").pack(side="left")
        self.count_entry = ttk.Spinbox(
            numbers, textvariable=self.count_var, from_=1, to=MAX_STACK, increment=1, width=4, style="Card.TSpinbox",
            command=self._apply_numbers, font=self.fonts.body,
        )
        self.count_entry.pack(side="left", padx=(8, 0))
        for widget in (self.power_entry, self.count_entry):
            widget.bind("<Return>", lambda _event: self._apply_numbers())
            widget.bind("<FocusOut>", lambda _event: self._apply_numbers())
        self.power_hint = tk.StringVar()
        ttk.Label(self.item_box, textvariable=self.power_hint, style="CardMuted.TLabel", wraplength=wrap, justify="left").grid(
            row=3, column=0, sticky="w", pady=(3, 0)
        )

        self.enchant_box = ttk.Frame(self.item_box, style="Box.TFrame", padding=(10, 8))
        self.enchant_box.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.enchant_box.columnconfigure(1, weight=1)
        diamond = self.art.px(34)
        ttk.Label(self.enchant_box, image=self.art.diamond(diamond, gs.CARD_BOX, "#5d6a71"), style="Box.TLabel").grid(
            row=0, column=0, rowspan=2, sticky="w", padx=(0, 10)
        )
        self.enchant_title = tk.StringVar()
        ttk.Label(self.enchant_box, textvariable=self.enchant_title, style="BoxTitle.TLabel").grid(row=0, column=1, sticky="w")
        self.enchant_text = tk.StringVar()
        ttk.Label(self.enchant_box, textvariable=self.enchant_text, style="Box.TLabel", wraplength=wrap - diamond - 40, justify="left").grid(
            row=1, column=1, sticky="w"
        )

        actions = ttk.Frame(self.item_box, style="Card.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        actions.columnconfigure((0, 1), weight=1, uniform="actions")
        self.equip_button = ttk.Button(actions, text="EQUIP", style="Card.TButton", command=self.equip_item)
        self.equip_button.grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=(0, 6))
        self.copy_button = ttk.Button(actions, text="MAKE A COPY", style="Card.TButton", command=self.copy_item)
        self.copy_button.grid(row=0, column=1, sticky="ew", padx=(3, 0), pady=(0, 6))
        self.change_button = ttk.Button(actions, text="CHANGE ITEM…", style="Card.TButton", command=self.change_item)
        self.change_button.grid(row=1, column=0, sticky="ew", padx=(0, 3))
        self.delete_button = ttk.Button(actions, text="DELETE", style="Card.TButton", command=self.delete_item)
        self.delete_button.grid(row=1, column=1, sticky="ew", padx=(3, 0))
        self.picture_button = ttk.Button(actions, text="PASTE PICTURE", style="Card.TButton", command=self.paste_picture)
        self.picture_button.grid(row=2, column=0, sticky="ew", padx=(0, 3), pady=(6, 0))
        self.name_button = ttk.Button(actions, text="NAME IT…", style="Card.TButton", command=self.name_item)
        self.name_button.grid(row=2, column=1, sticky="ew", padx=(3, 0), pady=(6, 0))

        self.slot_box = ttk.Frame(content, style="Card.TFrame")
        self.slot_box.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.slot_add_button = ttk.Button(self.slot_box, text="PUT AN ITEM HERE…", style="Accent.TButton", command=self._add_to_picked_slot)
        self.slot_add_button.pack(anchor="w")

        self.stats_box = ttk.Frame(content, style="Card.TFrame")
        self.stats_box.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.stats_box.columnconfigure(1, weight=1)

        self.item_message_var = tk.StringVar()
        self.item_message = ttk.Label(content, textvariable=self.item_message_var, style="CardMuted.TLabel", wraplength=wrap, justify="left")
        self.item_message.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self._show_parts()

    # ----------------------------------------------------------------- loading

    def load(self, hero: Hero | None) -> None:
        """Show ``hero`` (a Hero wrapping the document being edited)."""
        self.hero = hero
        self.selected = self._shown = None
        self.picked_slot = None
        self.card_mode = "hero"
        self._say_stats(f"Changes are kept as you go. {SAVE_REMINDER}" if hero is not None else "")
        self._say_item("")
        self.refresh()

    def set_active(self, active: bool) -> None:
        """Simple mode shows this screen; switching to it draws it again from the document."""
        self.active = active
        if active:
            self.refresh()

    def refresh(self) -> None:
        """Re-read everything from the document, e.g. after it was edited elsewhere."""
        if not self.active:
            return
        hero = self.hero
        if hero is not None and self.selected is not None and self.selected >= len(hero.items()):
            self.selected = None
        self._shown = None
        self._load_stats()
        self._show_currency_icons()
        if hero is None:
            self.header.grid_remove()
            self.stats_message.grid_remove()
            self.body.grid_remove()
            self.empty.grid(row=0, column=0, rowspan=3, sticky="nsew")
            return
        self.empty.grid_remove()
        self.header.grid()
        self.stats_message.grid()
        self.body.grid()
        self._fill_items()

    def _load_stats(self) -> None:
        self.stat_vars = {}
        if self.hero is not None:
            for attribute in self.hero.attributes():
                name = attribute["AttributeName"]
                var = self._fixed_vars.get(name) or tk.StringVar()
                var.set(number_text(attribute.get("CurrentValue")))
                self.stat_vars[name] = var
        for name, var in self._fixed_vars.items():
            if name not in self.stat_vars:
                var.set("")
            for entry in self._stat_entries.get(name, []):
                entry.state(["!disabled"] if name in self.stat_vars else ["disabled"])

    def _update_summary(self) -> None:
        if self.active and self.hero is not None:
            self._draw_gear()  # the hero's level opens gear slots
            if self.card_mode in ("hero", "slot"):
                self._show_card()

    def _say_stats(self, text: str, error: bool = False) -> None:
        self.stats_message_var.set(text)
        self.stats_message.configure(style="MessageError.TLabel" if error else "Message.TLabel")

    def _say_item(self, text: str, error: bool = False) -> None:
        self.item_message_var.set(text)
        self.item_message.configure(style="CardError.TLabel" if error else "CardMuted.TLabel")

    # ------------------------------------------------------------------- stats

    def _nudge_stat(self, name: str, step: int) -> str:
        """Arrow keys and the mouse wheel change a stat by one."""
        if self.hero is None or name not in self.stat_vars:
            return "break"
        var = self.stat_vars[name]
        current = self.hero.attribute(name)
        current = current if isinstance(current, (int, float)) and not isinstance(current, bool) else 0
        try:
            value = doc.parse_input(var.get(), current)
        except ValueError:
            value = current
        high = MAX_STAT if self.advanced else STAT_CAPS.get(name, MAX_STAT)
        var.set(number_text(min(max(value + step, STAT_MINIMUMS.get(name, 0)), high)))
        self._apply_stat(name)
        return "break"

    def show_stats(self) -> None:
        """Every stat on the card, with the town upgrades (like the game's Effects & Stats)."""
        if self.hero is None or not self._apply_numbers():
            return
        self.selected = self._shown = None
        self.picked_slot = None
        self.card_mode = "stats"
        self._say_item("")
        self._show_card()

    def _close_stats(self) -> None:
        self.card_mode = "hero"
        self._show_card()

    # ------------------------------------------------------------------- drawing

    def _fill_items(self) -> None:
        """Draw the gear, the inventory, gear power and the card again (keeping what's picked)."""
        if not self.active or self.hero is None:
            return
        if self.selected is not None and self.selected >= len(self.hero.items()):
            self.selected = None
        self._slot_list = self._slots()
        self._draw_gear()
        self._draw_inventory()
        self._update_power()
        self._show_card()

    def _update_power(self) -> None:
        power, parts = gear_power(self.hero, self._slot_list)
        self.gear_power_var.set("–" if power is None else str(power))
        for kind, var in self.power_part_vars.items():
            var.set(str(parts[kind]))

    def _draw_item_tile(self, canvas: tk.Canvas, x: int, y: int, item: Item) -> None:
        size = self.tile
        fill = tile_fill(item.rarity, item.kind)
        canvas.create_image(x, y, image=self.art.tile(fill, size), anchor="nw")
        picture = self.icons.item_art((item.name, item.tag), size - self.art.px(16))
        if picture is None:
            shade = mix(fill, "#ffffff", 0.35) if item.kind == "Talisman" else mix(fill, "#000000", 0.5)
            picture = self.art.icon(icon_for(item.kind, item.piece), shade, 3)
        canvas.create_image(x + size // 2, y + size // 2, image=picture)
        inset = max(4, self.art.px(4)) + self.art.px(3)
        if item.power is not None:
            self._shadow_text(canvas, x + size - inset, y + size - inset + 2, number_text(item.power), "se")
        if item.count > 1:
            self._shadow_text(canvas, x + inset, y + inset - 1, f"×{item.count}", "nw")

    def _shadow_text(self, canvas: tk.Canvas, x: int, y: int, text: str, anchor: str) -> None:
        canvas.create_text(x + 1, y + 1, text=text, anchor=anchor, fill="#101010", font=self.fonts.tile)
        canvas.create_text(x, y, text=text, anchor=anchor, fill="#ffffff", font=self.fonts.tile)

    def _draw_gear(self) -> None:
        canvas = self.gear_canvas
        canvas.delete("all")
        self._gear_hits = []
        if self.hero is None:
            return
        size, gap, heading = self.tile, self.art.px(GAP), self._heading
        worn = {item.equipped_slot: item for item in self.hero.items() if item.equipped_slot}
        level = self._hero_level()
        y = 4
        for title, icon, kinds in SECTIONS:
            middle = y + heading // 2 - 2
            canvas.create_image(4, middle, image=self.art.icon(icon, gs.HEADING, 1), anchor="w")
            canvas.create_text(4 + self.art.px(18), middle, text=title, anchor="w", fill=gs.HEADING, font=self.fonts.heading)
            y += heading
            for column, slot in enumerate(slot for slot in self._slot_list if slot.kind in kinds):
                x = 4 + column * (size + gap)
                item = worn.get(slot.tag)
                if item is not None and not item.is_cosmetic:
                    self._draw_item_tile(canvas, x, y, item)
                else:
                    self._draw_empty_slot(canvas, x, y, slot, slot_open(slot, level))
                self._gear_hits.append(((x, y, x + size, y + size), slot))
            y += size + gap
        self._mark_selection()

    def _draw_empty_slot(self, canvas: tk.Canvas, x: int, y: int, slot: GearSlot, is_open: bool) -> None:
        size = self.tile
        canvas.create_image(x, y, image=self.art.tile(EMPTY_TILE, size, empty=True), anchor="nw")
        middle = x + size // 2
        if is_open:
            canvas.create_image(middle, y + size // 2 - self.art.px(5), image=self.art.icon(icon_for(slot.kind, slot.piece), "#1f4858", 3))
            label = {"Melee": "MELEE", "Ranged": "RANGED"}.get(slot.kind, slot.label.upper())
            canvas.create_text(middle, y + size - self.art.px(9), text=label, fill="#5a8494", font=self.fonts.tiny)
        else:
            canvas.create_image(middle, y + size // 2 - self.art.px(5), image=self.art.icon("lock", "#3f6b7b", 2))
            canvas.create_text(middle, y + size - self.art.px(10), text=f"LV {slot.level}", fill="#6f97a6", font=self.fonts.tiny)

    def _inventory_items(self) -> list[Item]:
        """The items in the inventory (not worn, not cosmetics) that the filter shows, sorted."""
        items = [item for item in self.hero.items() if not item.is_cosmetic and not item.equipped_slot]
        key = self.filter_var.get()
        if key == "Merchant":
            items = [item for item in items if item.stock_slot]
        else:
            items = [item for item in items if not item.stock_slot and (key == "All" or item.kind == key)]
        return sort_items(items, self.sort_var.get())

    def _draw_inventory(self) -> None:
        canvas = self.inventory_canvas
        canvas.delete("all")
        self._item_hits = []
        if self.hero is None:
            return
        items = self._inventory_items()
        size = self.tile
        pad = self.art.px(12)
        cell_width = size + self.art.px(18)
        caption = self.art.px(30)
        cell_height = size + caption + self.art.px(8)
        width = max(canvas.winfo_width(), int(canvas.cget("width")) if canvas.winfo_width() <= 1 else 0)
        columns = max(1, (width - 2 * pad) // cell_width)
        for number, item in enumerate(items):
            row, column = divmod(number, columns)
            x = pad + column * cell_width + (cell_width - size) // 2
            y = pad + row * cell_height
            self._draw_item_tile(canvas, x, y, item)
            name = fit_lines(item.name, self.fonts.small, cell_width - 4)
            canvas.create_text(x + size // 2, y + size + self.art.px(3), text=name, anchor="n", justify="center", fill=gs.SOFT, font=self.fonts.small)
            self._item_hits.append(((x, y, x + size, y + size + caption), (x, y, x + size, y + size), item.index))
        if not items:
            canvas.create_text(pad, pad, anchor="nw", text=self._nothing_here(), fill=gs.MUTED, font=self.fonts.body, width=max(width - 2 * pad, 100))
        rows = -(-len(items) // columns)
        canvas.configure(scrollregion=(0, 0, width, max(pad * 2 + rows * cell_height, 1)))
        key = self.filter_var.get()
        self.count_text.set(f"{len(items)} {'IN STOCK' if key == 'Merchant' else 'ITEM' if len(items) == 1 else 'ITEMS'}")
        if self.icons.has_pictures():
            self.pictures_button.pack_forget()
        elif not self.pictures_button.winfo_manager():
            self.pictures_button.pack(side="right", padx=(0, 8))
        self._mark_selection()

    def _nothing_here(self) -> str:
        key = self.filter_var.get()
        if key == "Merchant":
            return "The Village Merchant has nothing in stock."
        if key == "All":
            return "Your inventory is empty. Press + ADD ITEMS to put something in it."
        return f"No {dict(FILTERS)[key].lower()} in your inventory. + ADD ITEMS adds some."

    def _on_inventory_resize(self, event: tk.Event) -> None:
        if event.width != self._inventory_width:
            self._inventory_width = event.width
            if self._redraw_job is not None:
                self.after_cancel(self._redraw_job)
            self._redraw_job = self.after_idle(self._redraw_inventory)

    def _redraw_inventory(self) -> None:
        self._redraw_job = None
        if self.active:
            self._draw_inventory()

    def _resort(self, draw: bool = True) -> None:
        self.sort_button.configure(text=f"SORT: {self.sort_var.get().upper()}")
        if draw:
            self._draw_inventory()

    def _mark_selection(self) -> None:
        """A white frame around the picked tile, as in the game."""
        for canvas in (self.gear_canvas, self.inventory_canvas):
            canvas.delete("selection")
        box, canvas = None, None
        if self.card_mode == "item" and self.selected is not None and self.hero is not None:
            item = self.hero.item(self.selected)
            if item.equipped_slot:
                box = next((tile for tile, slot in self._gear_hits if slot.tag == item.equipped_slot), None)
                canvas = self.gear_canvas
            else:
                box = next((tile for _box, tile, index in self._item_hits if index == self.selected), None)
                canvas = self.inventory_canvas
        elif self.card_mode == "slot" and self.picked_slot is not None:
            box = next((tile for tile, slot in self._gear_hits if slot.tag == self.picked_slot.tag), None)
            canvas = self.gear_canvas
        if box is not None:
            x0, y0, x1, y1 = box
            canvas.create_rectangle(x0 - 3, y0 - 3, x1 + 2, y1 + 2, outline="#ffffff", width=2, tags="selection")

    def _hover(self, canvas: tk.Canvas, boxes: list[tuple], event: tk.Event | None) -> None:
        canvas.delete("hover")
        found = None
        if event is not None:
            x, y = canvas.canvasx(event.x), canvas.canvasy(event.y)
            found = next((box for box in boxes if box[0] <= x <= box[2] and box[1] <= y <= box[3]), None)
        if found is not None:
            x0, y0, x1, y1 = found
            canvas.create_rectangle(x0 - 2, y0 - 2, x1 + 1, y1 + 1, outline="#9fb6c0", width=1, tags="hover")
            canvas.tag_raise("selection")
        canvas.configure(cursor="hand2" if found is not None else "")

    # ------------------------------------------------------------------ picking

    def _gear_slot_at(self, event: tk.Event) -> GearSlot | None:
        return next((slot for (x0, y0, x1, y1), slot in self._gear_hits if x0 <= event.x <= x1 and y0 <= event.y <= y1), None)

    def _inventory_index_at(self, event: tk.Event) -> int | None:
        x, y = self.inventory_canvas.canvasx(event.x), self.inventory_canvas.canvasy(event.y)
        return next((index for (x0, y0, x1, y1), _tile, index in self._item_hits if x0 <= x <= x1 and y0 <= y <= y1), None)

    def _on_gear_click(self, event: tk.Event) -> None:
        self.gear_canvas.focus_set()
        slot = self._gear_slot_at(event)
        if slot is not None:
            self.pick_slot(slot.tag)

    def _on_gear_double(self, event: tk.Event) -> None:
        slot = self._gear_slot_at(event)
        if slot is not None and self.hero is not None and self.hero.equipped(slot.tag) is None and slot_open(slot, self._hero_level()):
            self.open_add_items(for_slot=slot)

    def _on_inventory_click(self, event: tk.Event) -> None:
        self.inventory_canvas.focus_set()
        index = self._inventory_index_at(event)
        if index is not None:
            self.pick_item(index)

    def _on_inventory_double(self, event: tk.Event) -> None:
        """Double-clicking an item puts it on, like picking it in the game."""
        index = self._inventory_index_at(event)
        if index is not None and self.selected == index and self.equip_button.instate(["!disabled"]):
            self.equip_item()

    def pick_slot(self, slot_tag: str) -> None:
        """Show a gear slot on the card: the item in it, or what can go there."""
        slot = next((slot for slot in self._slot_list if slot.tag == slot_tag), None)
        if slot is None or self.hero is None:
            return
        item = self.hero.equipped(slot.tag)
        if item is not None:
            self.pick_item(item.index)
            return
        if not self._apply_numbers():  # something typed for the item on the card is wrong: stay on it
            return
        self.selected = self._shown = None
        self.picked_slot = slot
        self.card_mode = "slot"
        self._say_item("")
        self._show_card()

    def pick_item(self, index: int) -> None:
        """Show an item on the card."""
        if index == self.selected and self.card_mode == "item":
            return
        previous = self.selected
        self.selected = index
        if not self._apply_numbers():  # something typed for the previous item is wrong: stay on it
            self.selected = previous
            return
        self.picked_slot = None
        self.card_mode = "item"
        self._show_item(index)
        self._mark_selection()

    def _add_to_picked_slot(self) -> None:
        slot = self.picked_slot
        if slot is not None and slot_open(slot, self._hero_level()):
            self.open_add_items(for_slot=slot)

    def _context_menu(self, event: tk.Event, picked: GearSlot | int | None) -> None:
        """Right-click a tile for its actions (the game's More Actions)."""
        if picked is None or self.hero is None:
            return
        if isinstance(picked, GearSlot):
            self.pick_slot(picked.tag)
        else:
            self.pick_item(picked)
        menu = tk.Menu(self, tearoff=False)
        if self.card_mode == "slot":
            menu.add_command(label="Put an item here…", command=self._add_to_picked_slot, state="normal" if self.slot_add_button.instate(["!disabled"]) else "disabled")
        elif self.card_mode == "item":
            for button in (self.equip_button, self.copy_button, self.change_button, self.delete_button, self.picture_button, self.name_button):
                text = str(button.cget("text"))
                menu.add_command(label=text[0] + text[1:].lower(), command=button.invoke, state="normal" if button.instate(["!disabled"]) else "disabled")
        menu.tk_popup(event.x_root, event.y_root)

    # --------------------------------------------------------------------- card

    def _show_card(self) -> None:
        if self.hero is None:
            return
        if self.card_mode == "stats":
            self._show_stats_card()
        elif self.selected is not None:
            self._show_item(self.selected)
        elif self.card_mode == "slot" and self.picked_slot is not None:
            self._show_slot_card(self.picked_slot)
        else:
            self._show_hero_card()
        self._mark_selection()

    def _show_parts(self, *shown: ttk.Frame) -> None:
        for part in (self.item_box, self.slot_box, self.stats_box):
            if part in shown:
                part.grid()
            else:
                part.grid_remove()

    def _set_banner(self, text: str) -> None:
        self.banner_text = text
        canvas = self.banner
        canvas.delete("all")
        width, height = self._card_width, self.art.px(28)
        canvas.create_rectangle(0, 0, width, height, fill=gs.BANNER, outline="")
        canvas.create_rectangle(0, height - 2, width, height, fill=mix(gs.BANNER, "#000000", 0.3), outline="")
        canvas.create_text(width // 2, height // 2, text=text, fill=gs.TEXT, font=self.fonts.heading)
        half = self.fonts.heading.measure(text) // 2 + self.art.px(12)
        dot = self.art.px(3)
        for x in (width // 2 - half - dot, width // 2 + half):
            canvas.create_rectangle(x, height // 2 - dot // 2, x + dot, height // 2 + dot - dot // 2, fill=mix(gs.BANNER, "#ffffff", 0.5), outline="")

    def _set_badge(self, rarity: str | None) -> None:
        if rarity in RARITY_TILE:
            self.badge.configure(text=rarity.upper(), background=RARITY_TILE[rarity], foreground=gs.ON_COLOR)
            self.badge.pack(side="left", padx=(10, 0), pady=(4, 0))
        else:
            self.badge.pack_forget()

    def _card_head(self, banner: str, name: str, kind: str, picture: Any, text: str = "", power: str = "", rarity: str | None = None) -> None:
        self._set_banner(banner)
        self.card_power_var.set(power)
        self._set_badge(rarity)
        self.card_name_var.set(name)
        self.card_kind_var.set(kind)
        self.card_picture.configure(image=picture or "")
        self.card_text_var.set(text)

    def _show_hero_card(self) -> None:
        self.card_mode = "hero"
        self._shown = None
        hero = self.hero
        picture = self.icons.image(hero.skin, self.art.px(72)) if hero.skin else None
        self._card_head(
            "YOUR HERO",
            (hero.skin or "Your hero").upper(),
            f"{'Online' if hero.is_online else 'Offline'} hero · level {hero.level}",
            picture or self.art.icon("helmet", "#3b6d7e", 5),
            "Pick a gear slot on the left or an item in your inventory to see it here and change it. "
            "+ ADD ITEMS puts any item from the game in your inventory, and PRESETS sets your hero up in one go.",
        )
        self._show_parts()

    def _show_slot_card(self, slot: GearSlot) -> None:
        self._shown = None
        is_open = slot_open(slot, self._hero_level())
        if is_open:
            text = f"Nothing is equipped here. Put an item here to add any {slot_noun(slot)} from the game straight onto your hero."
        else:
            text = f"This slot opens at level {slot.level}, and your hero is level {self.hero.level}. Raise your level under LEVEL to open it."
        self._card_head(
            "EMPTY SLOT" if is_open else "LOCKED SLOT",
            slot.label.upper(),
            "Gear slot",
            self.art.icon(icon_for(slot.kind, slot.piece), "#2f6576", 5),
            text,
        )
        self.slot_add_button.state(["!disabled"] if is_open else ["disabled"])
        self._show_parts(self.slot_box)

    def _show_item(self, index: int | None) -> None:
        if index != self._shown:
            self._say_item("")
        self._shown = index
        if self.hero is None:
            return
        if index is None:
            self._show_hero_card()
            return
        self.card_mode = "item"
        item = self.hero.item(index)
        known = game_item(item.tag)
        details = [item.piece or KIND_NAMES.get(item.kind, item.kind)]
        if not name_is_known(item.tag):
            details.append("name made from its save ID")
        if known is not None and known.set:
            details.append(f"{known.set} set")
        if item.level:
            details.append(f"item level {item.level}")
        picture = self.icons.item_art((item.name, item.tag), self.art.px(72))
        if picture is None:
            color = gs.SOFT if item.kind == "Talisman" else RARITY_TILE.get(item.rarity, gs.HEADING)
            picture = self.art.icon(icon_for(item.kind, item.piece), color, 5)
        banner = "EQUIPPED" if item.equipped_slot else "MERCHANT STOCK" if item.stock_slot else "INVENTORY"
        self._card_head(banner, item.name.upper(), " · ".join(details), picture, describe(item, known), number_text(item.power), item.rarity)
        self.rarity_var.set(item.rarity)
        self.power_var.set(number_text(item.power))
        self.count_var.set(str(item.count))
        self.power_hint.set(f"Your strongest item has power {self.hero.best_power()}. Much higher may be removed by the game.")
        if item.kind in ENCHANTABLE:
            if item.enchantments:
                self.enchant_title.set("ENCHANTED")
                plural = "s" if item.enchantments != 1 else ""
                self.enchant_text.set(f"{item.enchantments} enchantment{plural}, picked in the game. The editor leaves them as they are.")
            else:
                self.enchant_title.set("NOT ENCHANTED")
                self.enchant_text.set("Find the Enchantsmith in town to enchant this item. The editor can't add enchantments yet.")
            self.enchant_box.grid()
        else:
            self.enchant_box.grid_remove()
        for widget in (self.power_entry, self.count_entry, *self.rarity_buttons, self.equip_button, self.change_button, self.copy_button,
                       self.delete_button, self.picture_button):
            widget.state(["!disabled"])
        # Only items the game's list doesn't name can be named here (and renamed, if you named them).
        self.name_button.state(["!disabled"] if not name_is_known(item.tag) or local_name(item.tag) else ["disabled"])
        self.equip_button.configure(text="UNEQUIP" if item.equipped_slot else "EQUIP")
        if item.equipped_slot:
            self.change_button.state(["disabled"])
            self.delete_button.state(["disabled"])
            if not self.item_message_var.get():
                self._say_item("You have this equipped. Unequip it to delete it or change it into another item.")
        elif item.stock_slot:
            self.equip_button.state(["disabled"])
            if not self.item_message_var.get():
                self._say_item("This is in the Village Merchant's stock, not your inventory. Make a copy to get one for yourself.")
        elif not slots_for(item.kind, item.piece, self._slot_list or self._slots()):
            self.equip_button.state(["disabled"])
        self._show_parts(self.item_box)

    def _show_stats_card(self) -> None:
        self._shown = None
        caps = "Simple mode stops at the game's caps, because anything above them is lost in the game."
        self._card_head("YOUR HERO", "STATS & TOWN", f"Changes are kept as you go. {SAVE_REMINDER}", None, caps)
        for child in self.stats_box.winfo_children():
            child.destroy()
        for row, attribute in enumerate(self.hero.attributes()):
            name = attribute["AttributeName"]
            icon = STAT_ICONS.get(name)
            ttk.Label(
                self.stats_box, text=attribute_label(name), style="Card.TLabel",
                image=self.art.icon(icon[0], icon[1], 1) if icon else "", compound="left",
            ).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(self.stats_box, textvariable=self.stat_vars[name], style="Card.TEntry", width=10, font=self.fonts.body)
            entry.grid(row=row, column=1, sticky="w", padx=(10, 8), pady=2)
            cap = STAT_CAPS.get(name)
            ttk.Label(self.stats_box, text=f"up to {format_amount(cap)}" if cap else "", style="CardMuted.TLabel").grid(row=row, column=2, sticky="w")
            entry.bind("<Return>", lambda _event, name=name: self._apply_stat(name))
            entry.bind("<FocusOut>", lambda _event, name=name: self._apply_stat(name))
            entry.bind("<Up>", lambda _event, name=name: self._nudge_stat(name, 1))
            entry.bind("<Down>", lambda _event, name=name: self._nudge_stat(name, -1))
        ttk.Button(self.stats_box, text="DONE", style="Card.TButton", command=self._close_stats).grid(
            row=len(self.hero.attributes()), column=0, sticky="w", pady=(10, 0)
        )
        self._show_parts(self.stats_box)

    # ---------------------------------------------- your own pictures and names

    def paste_picture(self) -> None:
        """Use the picture on the clipboard for the item on the card. Snip an item's tile in the game
        (Windows+Shift+S) first: the editor cuts the item out and keeps it on this PC."""
        if self.hero is None or self._shown is None:
            return
        item = self.hero.item(self._shown)
        try:
            from PIL import Image, ImageGrab
        except ImportError:
            self._say_item("Pasting pictures needs Pillow (the .exe includes it; from source: py -m pip install pillow).", error=True)
            return
        try:
            picture = ImageGrab.grabclipboard()
            if isinstance(picture, list):  # files copied in Explorer
                picture = next((Image.open(path) for path in picture if Path(path).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")), None)
        except OSError:
            picture = None
        if picture is None:
            self._say_item(
                "Copy a picture first: in the game, press Windows+Shift+S and drag around the item's tile, "
                "then pick the item here and press PASTE PICTURE.",
                error=True,
            )
            return
        try:
            self.icons.save_captured(picture, item.name)
        except OSError as exc:
            self._say_item(f"Couldn't keep the picture: {exc}", error=True)
            return
        self._fill_items()
        self._say_item(f"Got it: that's the {item.name}'s picture now. It's kept on this PC, in the icons folder.")

    def name_item(self) -> None:
        """Give an item the editor doesn't know the name the game uses for it."""
        if self.hero is None or self._shown is None:
            return
        item = self.hero.item(self._shown)
        name = self._ask_text(
            "Name this item",
            f"What does the game call this item? Its save ID is {item.tag}.\n\n"
            "The name stays on this PC. Share item IDs (on the Help page) puts it in the list you can send, "
            "so the editor can learn it for everyone.",
            local_name(item.tag) or "",
        )
        if not name:
            return
        names = load_names(self.names_file)
        names[item.tag] = name
        try:
            save_names(names, self.names_file)
        except OSError as exc:
            self._say_item(f"Couldn't keep the name: {exc}", error=True)
            return
        use_local_names(names)
        self._fill_items()
        self._say_item(f"Named it the {name}. Share item IDs can send the name on.")

    def _ask_text(self, title: str, prompt: str, initial: str) -> str | None:
        """A small window asking for a line of text, in the editor's own look. None if cancelled."""
        window = tk.Toplevel(self)
        window.title(title)
        window.transient(self.winfo_toplevel())
        gs.match_title_bar(window)
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=prompt, wraplength=self.art.px(380), justify="left").pack(anchor="w")
        value = tk.StringVar(value=initial)
        entry = ttk.Entry(frame, textvariable=value, width=40)
        entry.pack(anchor="w", fill="x", pady=(10, 0))
        answer: list[str] = []

        def done(keep: bool) -> None:
            if keep and value.get().strip():
                answer.append(value.get().strip())
            window.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=lambda: done(False)).pack(side="right")
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=lambda: done(True)).pack(side="right", padx=(0, 8))
        entry.bind("<Return>", lambda _event: done(True))
        window.bind("<Escape>", lambda _event: done(False))
        fit_to_contents(window)
        entry.focus_set()
        entry.select_range(0, "end")
        try:
            window.grab_set()
        except tk.TclError:
            pass
        self.wait_window(window)
        return answer[0] if answer else None

    # ------------------------------------------------------------------- hints

    def _gear_tip(self, event: tk.Event) -> str | None:
        slot = self._gear_slot_at(event)
        if slot is None or self.hero is None:
            return None
        item = self.hero.equipped(slot.tag)
        if item is not None:
            return f"{item.name}\n{item.rarity} · power {number_text(item.power)}"
        if not slot_open(slot, self._hero_level()):
            return f"{slot.label}: opens at level {slot.level}"
        return f"{slot.label}: empty. Double-click to put an item here."

    def _inventory_tip(self, event: tk.Event) -> str | None:
        index = self._inventory_index_at(event)
        if index is None or self.hero is None:
            return None
        item = self.hero.item(index)
        return f"{item.name}\n{item.rarity} {(item.piece or KIND_NAMES.get(item.kind, item.kind)).lower()} · power {number_text(item.power)}"
