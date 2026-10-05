"""The Hero tab, in Advanced mode: an offline hero's stats, and every item in a sortable list.

Changes apply as soon as you press Enter, click an arrow or leave a field, and
mistakes show up in red next to the field instead of in pop-ups. Advanced mode
adds the raw item ID for people who want it. Simple mode shows the hero the way
the game's inventory screen does instead (inventory_screen.py).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from .hero import (
    ITEM_SORTS,
    MAX_ITEM_POWER,
    MAX_STACK,
    MAX_STAT,
    RARITIES,
    STAT_CAPS,
    GearSlot,
    Hero,
    attribute_label,
    slots_for,
    sort_items,
)
from .hero_editing import SAVE_REMINDER, HeroEditing, number_text, power_text, talisman_hint
from .icons import IconLibrary
from .item_picker import slot_open

_HEADINGS = {
    "#0": "Item",
    "kind": "Kind",
    "rarity": "Rarity",
    "power": "Power",
    "level": "Level",
    "xp": "XP",
    "enchants": "Effects",
    "where": "Where",
}
# Clicking a column heading sorts by it.
_HEADING_SORTS = {
    "#0": "Name",
    "kind": "Kind",
    "rarity": "Rarest",
    "power": "Most powerful",
    "level": "Highest item level",
    "xp": "Most item XP",
    "enchants": "Most effects",
    "where": "Where",
}
_NUMBER_COLUMNS = ("power", "level", "xp", "enchants")
_STATS_PER_ROW = 3
ROW_ICON_SIZE = 24
STAT_ICON_SIZE = 18
PREVIEW_SIZE = 72


class HeroTab(HeroEditing, ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None],
        app_title: str,
        bold_font: Any,
        icons: IconLibrary,
        get_pictures: Callable[[], None],
        catalog_heroes: Callable[[], list[Hero]],
    ):
        super().__init__(master, padding=10)
        self.on_change = on_change
        self.app_title = app_title
        self.bold_font = bold_font
        self.icons = icons
        self.get_pictures = get_pictures
        self.catalog_heroes = catalog_heroes
        self.advanced = False
        self.hero: Hero | None = None
        self.selected: int | None = None  # inventory entry index picked in the list
        self._shown: int | None = None  # entry whose details are in the fields below the list
        self.stat_vars: dict[str, tk.StringVar] = {}
        self.sort_var = tk.StringVar(value="Most powerful")
        self.show_merchant = tk.BooleanVar(value=True)
        self.show_cosmetics = tk.BooleanVar(value=False)
        self._index_by_iid: dict[str, int] = {}
        self._guessed_slot_ok = False  # asked once before using a slot whose name is a best guess
        self._build()

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.summary_var = tk.StringVar()
        ttk.Label(top, textvariable=self.summary_var, style="Muted.TLabel").pack(side="left")
        ttk.Button(top, text="Presets…", style="Accent.TButton", command=self.open_presets).pack(side="right")

        stats = ttk.LabelFrame(self, text="Stats", padding=10)
        stats.grid(row=1, column=0, sticky="ew")
        stats.columnconfigure(0, weight=1)
        self.stats_fields = ttk.Frame(stats)
        self.stats_fields.grid(row=0, column=0, sticky="w")
        self.stats_message_var = tk.StringVar()
        self.stats_message = ttk.Label(stats, textvariable=self.stats_message_var, style="Muted.TLabel")
        self.stats_message.grid(row=1, column=0, sticky="w", pady=(8, 0))

        items = ttk.LabelFrame(self, text="Items", padding=10)
        items.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        items.columnconfigure(0, weight=1)
        items.rowconfigure(1, weight=1)

        controls = ttk.Frame(items)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(controls, text="+ Add items…", style="Accent.TButton", command=self.open_add_items).pack(side="left", padx=(0, 14))
        ttk.Label(controls, text="Sort by").pack(side="left")
        sort_box = ttk.Combobox(controls, textvariable=self.sort_var, values=list(ITEM_SORTS), state="readonly", width=19)
        sort_box.pack(side="left", padx=(6, 14))
        sort_box.bind("<<ComboboxSelected>>", lambda _event: self._fill_items())
        ttk.Checkbutton(controls, text="Merchant stock", variable=self.show_merchant, command=self._fill_items).pack(side="left")
        ttk.Checkbutton(controls, text="Cosmetics", variable=self.show_cosmetics, command=self._fill_items).pack(side="left", padx=(10, 0))
        ttk.Button(controls, text="Get pictures…", command=self.get_pictures).pack(side="right")
        self.shown_var = tk.StringVar()
        ttk.Label(controls, textvariable=self.shown_var, style="Muted.TLabel").pack(side="right", padx=(0, 10))

        # Two views of the items: every item, and the 12 gear slots with what's equipped in each.
        self.item_views = ttk.Notebook(items)
        self.item_views.grid(row=1, column=0, columnspan=2, sticky="nsew")
        inventory = ttk.Frame(self.item_views)
        inventory.columnconfigure(0, weight=1)
        inventory.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(inventory, columns=list(_HEADINGS)[1:], selectmode="browse", height=7, style="Items.Treeview")
        for column, text in _HEADINGS.items():
            self.tree.heading(column, text=text, command=lambda column=column: self._sort_by_heading(column))
        self.tree.column("#0", width=200, stretch=True)
        widths = {"kind": 80, "rarity": 72, "power": 64, "level": 54, "xp": 64, "enchants": 72, "where": 180}
        for column, width in widths.items():
            self.tree.column(column, width=width, stretch=column == "where", anchor="e" if column in _NUMBER_COLUMNS else "w")
        scroll = ttk.Scrollbar(inventory, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.gear = ttk.Frame(self.item_views)
        self.gear.columnconfigure(0, weight=1)
        self.gear.rowconfigure(0, weight=1)
        self.gear_tree = ttk.Treeview(self.gear, columns=("item", "detail"), selectmode="browse", height=7, style="Items.Treeview")
        self.gear_tree.heading("#0", text="Slot")
        self.gear_tree.heading("item", text="Equipped")
        self.gear_tree.heading("detail", text="Rarity and power")
        self.gear_tree.column("#0", width=170, stretch=False)
        self.gear_tree.column("item", width=260, stretch=True)
        self.gear_tree.column("detail", width=200, stretch=False)
        self.gear_tree.tag_configure("empty", foreground=ttk.Style(self).lookup("Muted.TLabel", "foreground"))
        gear_scroll = ttk.Scrollbar(self.gear, orient="vertical", command=self.gear_tree.yview)
        self.gear_tree.configure(yscrollcommand=gear_scroll.set)
        self.gear_tree.grid(row=0, column=0, sticky="nsew")
        gear_scroll.grid(row=0, column=1, sticky="ns")
        self.gear_tree.bind("<<TreeviewSelect>>", lambda _event: self._on_gear_select())
        self.gear_tree.bind("<Double-1>", lambda _event: self._add_to_gear_slot())
        gear_buttons = ttk.Frame(self.gear)
        gear_buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.slot_add_button = ttk.Button(gear_buttons, text="Put an item here…", command=self._add_to_gear_slot)
        self.slot_add_button.pack(side="left", padx=(0, 6))
        self.slot_off_button = ttk.Button(gear_buttons, text="Unequip", command=self._unequip_gear_slot)
        self.slot_off_button.pack(side="left")
        self._gear_slots: dict[str, tuple[GearSlot, int | None]] = {}  # row id (slot tag) -> slot, equipped item index
        self.item_views.add(inventory, text="All items")
        self.item_views.add(self.gear, text="Equipped")
        self.item_views.bind("<<NotebookTabChanged>>", lambda _event: self._fill_gear())
        self.tree.tag_configure("locked", foreground=ttk.Style(self).lookup("Muted.TLabel", "foreground"))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", lambda _event: self.delete_item())

        self._build_details(items)
        self._show_item(None)

    def _build_details(self, items: ttk.Frame) -> None:
        details = ttk.Frame(items)
        details.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        details.columnconfigure(1, weight=1)
        self.preview = ttk.Label(details)
        self.preview.grid(row=0, column=0, rowspan=5, sticky="nw", padx=(0, 14))

        self.item_title_var = tk.StringVar()
        ttk.Label(details, textvariable=self.item_title_var, font=self.bold_font).grid(row=0, column=1, sticky="w")
        self.item_subtitle_var = tk.StringVar()
        ttk.Label(details, textvariable=self.item_subtitle_var, style="Muted.TLabel", wraplength=720, justify="left").grid(row=1, column=1, sticky="w")

        fields = ttk.Frame(details)
        fields.grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(fields, text="Rarity").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.rarity_var = tk.StringVar()
        self.rarity_buttons = []
        for column, rarity in enumerate(RARITIES, start=1):
            button = ttk.Radiobutton(
                fields,
                text=rarity,
                value=rarity,
                variable=self.rarity_var,
                image=self.icons.rarity_badge(rarity, 16),
                compound="left",
                command=lambda: self._apply_item(rarity=self.rarity_var.get()),
            )
            button.grid(row=0, column=column, sticky="w", padx=(0, 10))
            self.rarity_buttons.append(button)
        ttk.Label(fields, text="Power").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        self.power_var = tk.StringVar()
        self.power_entry = ttk.Spinbox(fields, textvariable=self.power_var, from_=0, to=MAX_ITEM_POWER, increment=1, width=9, command=self._apply_numbers)
        self.power_entry.grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(fields, text="Count").grid(row=1, column=2, sticky="e", padx=(0, 8), pady=(6, 0))
        self.count_var = tk.StringVar()
        self.count_entry = ttk.Spinbox(fields, textvariable=self.count_var, from_=1, to=MAX_STACK, increment=1, width=7, command=self._apply_numbers)
        self.count_entry.grid(row=1, column=3, sticky="w", pady=(6, 0))
        for widget in (self.power_entry, self.count_entry):
            widget.bind("<Return>", lambda _event: self._apply_numbers())
            widget.bind("<FocusOut>", lambda _event: self._apply_numbers())

        self.raw_row = ttk.Frame(details)
        self.raw_row.grid(row=3, column=1, sticky="ew", pady=(6, 0))
        ttk.Label(self.raw_row, text="Item ID").pack(side="left", padx=(0, 8))
        self.type_var = tk.StringVar()
        self.type_box = ttk.Combobox(self.raw_row, textvariable=self.type_var, width=42)
        self.type_box.pack(side="left")
        self.type_box.bind("<Return>", lambda _event: self._apply_type())
        self.type_box.bind("<FocusOut>", lambda _event: self._apply_type())
        self.type_box.bind("<<ComboboxSelected>>", lambda _event: self._apply_type())

        buttons = ttk.Frame(details)
        buttons.grid(row=4, column=1, sticky="w", pady=(8, 0))
        self.equip_button = ttk.Button(buttons, text="Equip", width=10, command=self.equip_item)
        self.equip_button.pack(side="left", padx=(0, 6))
        self.change_button = ttk.Button(buttons, text="Change item…", command=self.change_item)
        self.change_button.pack(side="left")
        self.copy_button = ttk.Button(buttons, text="Make a copy", command=self.copy_item)
        self.copy_button.pack(side="left", padx=6)
        self.delete_button = ttk.Button(buttons, text="Delete", command=self.delete_item)
        self.delete_button.pack(side="left")

        self.item_message_var = tk.StringVar()
        self.item_message = ttk.Label(details, textvariable=self.item_message_var, style="Muted.TLabel", wraplength=720, justify="left")
        self.item_message.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.preview_source_var = tk.StringVar()
        ttk.Label(details, textvariable=self.preview_source_var, style="Muted.TLabel").grid(row=6, column=0, columnspan=2, sticky="w")
        self.set_advanced(False)

    def set_advanced(self, advanced: bool) -> None:
        self.advanced = advanced
        if advanced:
            self.raw_row.grid()
        else:
            self.raw_row.grid_remove()
        if self.hero is not None:
            self._build_stats()  # the most each stat may be set to depends on the mode

    # ----------------------------------------------------------------- loading

    def load(self, hero: Hero | None) -> None:
        """Show ``hero`` (a Hero wrapping the document being edited)."""
        self.hero = hero
        self.selected = self._shown = None
        self.icons.reload()
        self._say_stats(f"Changes are kept as you go. {SAVE_REMINDER}")
        self.refresh()

    def refresh(self) -> None:
        """Re-read everything from the document, e.g. after it was edited elsewhere."""
        if self.hero is not None and self.selected is not None and self.selected >= len(self.hero.items()):
            self.selected = self._shown = None
        self._build_stats()
        self._update_summary()
        self._shown = None
        self._fill_items()

    def _update_summary(self) -> None:
        hero = self.hero
        if hero is None:
            self.summary_var.set("")
            return
        parts = ["Online hero" if hero.is_online else "Offline hero"]
        if hero.skin:
            parts.append(hero.skin)
        parts.append(f"level {hero.level}")
        parts.append(f"power level {hero.power_level} (the game works this out from your gear)")
        self.summary_var.set("  ·  ".join(parts))

    def _say(self, label: ttk.Label, var: tk.StringVar, text: str, error: bool = False) -> None:
        var.set(text)
        label.configure(style="Error.TLabel" if error else "Muted.TLabel")

    def _say_stats(self, text: str, error: bool = False) -> None:
        self._say(self.stats_message, self.stats_message_var, text, error)

    def _say_item(self, text: str, error: bool = False) -> None:
        self._say(self.item_message, self.item_message_var, text, error)

    # ------------------------------------------------------------------- stats

    def _build_stats(self) -> None:
        for child in self.stats_fields.winfo_children():
            child.destroy()
        self.stat_vars.clear()
        if self.hero is None:
            return
        for position, attribute in enumerate(self.hero.attributes()):
            name = attribute["AttributeName"]
            row, column = divmod(position, _STATS_PER_ROW)
            icon = self.icons.image(name, STAT_ICON_SIZE)
            label = ttk.Label(self.stats_fields, text=attribute_label(name), image=icon or "", compound="left")
            label.grid(row=row, column=column * 2, sticky="w", padx=(0 if column == 0 else 24, 8), pady=3)
            var = tk.StringVar(value=number_text(attribute.get("CurrentValue")))
            highest = MAX_STAT if self.advanced else STAT_CAPS.get(name, MAX_STAT)
            spin = ttk.Spinbox(
                self.stats_fields, textvariable=var, from_=0, to=highest, increment=1, width=12, command=lambda name=name: self._apply_stat(name)
            )
            spin.grid(row=row, column=column * 2 + 1, sticky="w", pady=3)
            spin.bind("<Return>", lambda _event, name=name: self._apply_stat(name))
            spin.bind("<FocusOut>", lambda _event, name=name: self._apply_stat(name))
            self.stat_vars[name] = var

    # ------------------------------------------------------------------- items

    def _fill_items(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._index_by_iid.clear()
        if self.hero is None:
            self.shown_var.set("")
            self._show_item(None)
            return
        every = self.hero.items()
        shown = [
            item
            for item in every
            if (self.show_merchant.get() or not item.stock_slot) and (self.show_cosmetics.get() or not item.is_cosmetic)
        ]
        for item in sort_items(shown, self.sort_var.get()):
            power = "" if item.is_cosmetic else power_text(item)
            iid = self.tree.insert(
                "",
                "end",
                text=" " + item.name,
                image=self.icons.item_image(item.tag, item.rarity, ROW_ICON_SIZE, item.name),
                values=(item.kind, "" if item.is_talisman else item.rarity, power, item.level, number_text(item.xp), len(item.effects), item.where),
                tags=("locked",) if item.is_cosmetic else (),
            )
            self._index_by_iid[iid] = item.index
        self._mark_sorted_heading()
        self.shown_var.set(f"{len(shown)} of {len(every)} shown")
        if self.selected in self._index_by_iid.values():
            self._select_row(self.selected)
            self._show_item(self.selected)
        else:
            self.selected = None
            self._show_item(None)
        self._fill_gear()

    def _fill_gear(self) -> None:
        """The Equipped view: each gear slot and what's in it. Built only while it's showing;
        switching to it builds it."""
        if self.item_views.select() != str(self.gear):
            return
        chosen = self.gear_tree.selection()
        self.gear_tree.delete(*self.gear_tree.get_children())
        self._gear_slots.clear()
        if self.hero is not None:
            level = self._hero_level()
            worn = {item.equipped_slot: item for item in self.hero.items() if item.equipped_slot}
            for slot in self._slots():
                item = worn.get(slot.tag)
                if item is not None:
                    values = (item.name, "" if item.is_talisman else f"{item.rarity}, power {number_text(item.power)}")
                    image = self.icons.item_image(item.tag, item.rarity, ROW_ICON_SIZE, item.name)
                else:
                    values = ("empty" if slot_open(slot, level) else f"opens at level {slot.level}", "")
                    image = ""
                self.gear_tree.insert("", "end", iid=slot.tag, text=" " + slot.label, image=image, values=values, tags=() if item else ("empty",))
                self._gear_slots[slot.tag] = (slot, item.index if item else None)
        if chosen and chosen[0] in self._gear_slots:
            self.gear_tree.selection_set(chosen[0])
        self._on_gear_select()

    def _selected_gear_slot(self) -> tuple[GearSlot, int | None] | None:
        selection = self.gear_tree.selection()
        return self._gear_slots.get(selection[0]) if selection else None

    def _on_gear_select(self) -> None:
        chosen = self._selected_gear_slot()
        level = self._hero_level()
        can_add = chosen is not None and slot_open(chosen[0], level)
        self.slot_add_button.state(["!disabled"] if can_add else ["disabled"])
        self.slot_off_button.state(["!disabled"] if chosen is not None and chosen[1] is not None else ["disabled"])
        if chosen is not None and chosen[1] is not None:
            self._pick_item(chosen[1])

    def _add_to_gear_slot(self) -> None:
        chosen = self._selected_gear_slot()
        level = self._hero_level()
        if chosen is not None and slot_open(chosen[0], level):
            self.open_add_items(for_slot=chosen[0])

    def _unequip_gear_slot(self) -> None:
        chosen = self._selected_gear_slot()
        if chosen is not None:
            self._take_off(chosen[1])

    def _pick_item(self, index: int) -> None:
        """Show an item (picked in the Equipped view) in the details below."""
        if index == self.selected:
            return
        previous = self.selected
        self.selected = index
        if not self._apply_numbers():  # something typed for the previous item is wrong: stay on it
            self.selected = previous
            return
        self._select_row(index)
        self._show_item(index)

    def _mark_sorted_heading(self) -> None:
        sort = self.sort_var.get()
        for column, text in _HEADINGS.items():
            if _HEADING_SORTS[column] == sort:
                text += " ▼" if ITEM_SORTS[sort][1] else " ▲"
            self.tree.heading(column, text=text)

    def _sort_by_heading(self, column: str) -> None:
        self.sort_var.set(_HEADING_SORTS[column])
        self._fill_items()

    def _on_select(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        index = self._index_by_iid.get(selection[0]) if selection else None
        if index == self.selected:
            return
        previous = self.selected
        self.selected = index
        if not self._apply_numbers():  # something typed for the previous item is wrong: stay on it
            self.selected = previous
            self._select_row(previous)
            return
        self._show_item(index)

    def _select_row(self, index: int | None) -> None:
        for iid, candidate in self._index_by_iid.items():
            if candidate == index:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                return

    def _show_item(self, index: int | None) -> None:
        inputs = [self.power_entry, self.count_entry, self.type_box, *self.rarity_buttons]
        buttons = [self.equip_button, self.change_button, self.copy_button, self.delete_button]
        if index != self._shown:
            self._say_item("")
        self._shown = index
        if self.hero is None or index is None:
            self.item_title_var.set("Pick an item in the list to change it, or add new ones with + Add items.")
            for var in (self.item_subtitle_var, self.type_var, self.rarity_var, self.power_var, self.count_var, self.preview_source_var):
                var.set("")
            for widget in inputs + buttons:
                widget.state(["disabled"])
            self.equip_button.configure(text="Equip")
            self.preview.configure(image="")
            return
        item = self.hero.item(index)
        self.item_title_var.set(item.name)
        subtitle = ("Talisman" if item.is_talisman else f"{item.rarity} {item.kind.lower()}") + f"  ·  {item.where}"
        effects = item.effect_lines()
        if effects:  # shown, not changed: the editor can't edit effects yet
            subtitle += "\nEffects: " + "  ·  ".join(line.rstrip(".") for line in effects)
        self.item_subtitle_var.set(subtitle)
        self.preview.configure(image=self.icons.item_image(item.tag, item.rarity, PREVIEW_SIZE, item.name))
        self.preview_source_var.set("Picture: minecraft.wiki" if self.icons.is_from_wiki(item.name, item.tag) else "")
        if self.advanced:
            self.type_box["values"] = [entry.tag for entry in self._catalog()]
        self.type_var.set(item.tag)
        self.rarity_var.set(item.rarity)
        self.power_var.set(power_text(item))
        self.count_var.set(str(item.count))
        locked = item.is_cosmetic
        for widget in inputs + buttons:
            widget.state(["disabled"] if locked else ["!disabled"])
        self.equip_button.configure(text="Unequip" if item.equipped_slot else "Equip")
        if locked:
            if not self.item_message_var.get():
                self._say_item("Cosmetics come from your game edition, so they can't be changed or copied.")
            return
        if item.is_talisman:  # no rarity or power: it levels up from the XP you earn
            for widget in (self.power_entry, *self.rarity_buttons):
                widget.state(["disabled"])
            # Said unless there's something more pressing to say about a talisman that's fine.
            pressing = (item.equipped_slot or item.stock_slot) and item.progression.get("ItemLevels")
            if not self.item_message_var.get() and not pressing:
                self._say_item(talisman_hint(item))
        if item.equipped_slot:
            self.change_button.state(["disabled"])
            self.delete_button.state(["disabled"])
            self.type_box.state(["disabled"])
            if not self.item_message_var.get():
                self._say_item("You have this equipped. Unequip it to delete it or change it into another item.")
        elif item.stock_slot:
            self.equip_button.state(["disabled"])
            self.change_button.state(["disabled"])  # what the merchant stocks is the game's doing
            self.type_box.state(["disabled"])
            if not self.item_message_var.get():
                self._say_item("This is in the Village Merchant's stock, not your inventory. Make a copy to get one for yourself.")
        elif not slots_for(item.kind, item.piece, self._slots()):
            self.equip_button.state(["disabled"])

    def _apply_type(self) -> None:
        if self.hero is not None and self._shown is not None and self.type_var.get().strip() != self.hero.item(self._shown).tag:
            self._apply_item(tag=self.type_var.get())
