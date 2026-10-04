"""A dialog for picking an item to add (or to change an item into), with search and pictures."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from . import document as doc
from .hero import MAX_ITEM_POWER, MAX_STACK, RARITIES, CatalogItem, GearSlot, slots_for
from .icons import IconLibrary
from .game_style import match_title_bar
from .layout import fit_to_contents, text_width

LIST_ICON_SIZE = 24
PREVIEW_SIZE = 80
ALL = "All kinds"
SIZE = (880, 600)


def slot_open(slot: GearSlot, level: int | None) -> bool:
    """Whether a hero of ``level`` has the slot (None: don't check)."""
    return not isinstance(level, int) or level >= slot.level


def slot_choice(slot: GearSlot, occupant: str | None, level: int | None) -> str:
    """How a slot reads in a list: 'Artifact 2: Firework Arrow', 'Helmet: empty', 'Artifact 3: opens at level 10'."""
    if not slot_open(slot, level):
        return f"{slot.label}: opens at level {slot.level}"
    return f"{slot.label}: {occupant or 'empty'}"


def default_slot(slots: list[GearSlot], equipped: dict[str, str], level: int | None) -> GearSlot | None:
    """The first open, empty slot, else the first open one."""
    open_slots = [slot for slot in slots if slot_open(slot, level)]
    return next((slot for slot in open_slots if slot.tag not in equipped), None) or next(iter(open_slots), None)


class ItemPicker(tk.Toplevel):
    """Pick an item from ``catalog``.

    In "add" mode, the right-hand panel sets rarity, power, count and (optionally) the slot to
    equip it in, and calls ``on_add(tag, rarity, power, count, slot)`` (which raises ValueError to
    reject); the dialog stays open so several items can be added. ``equipped()`` says what's in
    each slot now (slot tag -> item name). In "choose" mode the dialog closes and leaves the
    picked item ID in ``result``.
    """

    def __init__(
        self,
        parent: tk.Misc,
        catalog: list[CatalogItem],
        icons: IconLibrary,
        *,
        mode: str = "add",
        advanced: bool = False,
        best_power: int = 1,
        slots: list[GearSlot] | None = None,
        equipped: Callable[[], dict[str, str]] | None = None,
        hero_level: int | None = None,
        on_add: Callable[[str, str, int, int, GearSlot | None], None] | None = None,
        for_slot: GearSlot | None = None,
    ):
        super().__init__(parent)
        self.catalog = catalog
        self.icons = icons
        self.mode = mode
        self.advanced = advanced
        self.slots = slots or []
        self.equipped = equipped or (lambda: {})
        self.hero_level = hero_level
        self.on_add = on_add
        self.for_slot = for_slot  # only items for this slot, equipped there
        self.result: str | None = None
        self._by_iid: dict[str, CatalogItem] = {}
        self._slot_by_choice: dict[str, GearSlot] = {}
        self._chosen_slot_tag: str | None = for_slot.tag if for_slot else None
        self._unconfirmed_ok = False
        self._guessed_slot_ok = False
        self.title(f"Add items: {for_slot.label}" if for_slot else "Add items" if mode == "add" else "Change item")
        self.transient(parent)
        match_title_bar(self)
        self.geometry("{}x{}".format(*SIZE))
        self._build(best_power)
        self._fill()
        fit_to_contents(self, *SIZE)
        self.search_entry.focus_set()
        self.bind("<Escape>", lambda _event: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not shown yet (e.g. while the main window is minimised); still usable

    def _build(self, best_power: int) -> None:
        wrap = text_width(self, 38)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(top, text="Find").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._fill())
        self.search_entry = ttk.Entry(top, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(6, 12))
        self.kind_var = tk.StringVar(value=ALL)
        kinds = [ALL] + sorted({item.kind for item in self.catalog})
        kind_box = ttk.Combobox(top, textvariable=self.kind_var, values=kinds, state="readonly", width=16)
        kind_box.pack(side="left")
        if self.for_slot is not None:
            self.kind_var.set(self.for_slot.kind)
            kind_box.state(["disabled"])
        kind_box.bind("<<ComboboxSelected>>", lambda _event: self._fill())
        self.confirmed_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Only confirmed", variable=self.confirmed_only, command=self._fill).pack(side="left", padx=(12, 0))

        listing = ttk.Frame(frame)
        listing.grid(row=1, column=0, sticky="nsew")
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(listing, columns=("kind", "status"), selectmode="browse", style="Items.Treeview")
        self.tree.heading("#0", text="Item")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("kind", width=90, stretch=False)
        self.tree.column("status", width=100, stretch=False)
        self.tree.tag_configure("unconfirmed", foreground=ttk.Style(self).lookup("Muted.TLabel", "foreground"))
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())
        self.tree.bind("<Double-1>", lambda _event: self._confirm())
        self.tree.bind("<Return>", lambda _event: self._confirm())

        panel = ttk.Frame(frame, padding=(14, 0, 0, 0))
        panel.grid(row=1, column=1, sticky="nsew")
        head = ttk.Frame(panel)
        head.pack(anchor="w", fill="x")
        self.preview = ttk.Label(head)
        self.preview.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        self.name_var = tk.StringVar(value="Pick an item on the left.")
        name_wrap = max(wrap - PREVIEW_SIZE - 10, wrap // 2)
        ttk.Label(head, textvariable=self.name_var, style="Heading.TLabel", wraplength=name_wrap, justify="left").grid(row=0, column=1, sticky="sw")
        self.kind_text = tk.StringVar()
        ttk.Label(head, textvariable=self.kind_text, style="Muted.TLabel", wraplength=name_wrap, justify="left").grid(row=1, column=1, sticky="nw")
        head.rowconfigure(0, weight=1)
        head.rowconfigure(1, weight=1)
        self.status_text = tk.StringVar()
        self.status_label = ttk.Label(panel, textvariable=self.status_text, style="Muted.TLabel", wraplength=wrap, justify="left")
        self.status_label.pack(anchor="w", pady=(6, 0))

        self.rarity_var = tk.StringVar(value="Common")
        self.power_var = tk.StringVar(value=str(best_power))
        self.count_var = tk.StringVar(value="1")
        self.unique_text = tk.StringVar()
        self.equip_var = tk.BooleanVar(value=self.for_slot is not None)
        self.slot_var = tk.StringVar()
        self.slot_note = tk.StringVar()
        if self.mode == "add":
            ttk.Label(panel, text="Rarity").pack(anchor="w", pady=(10, 2))
            rarities = ttk.Frame(panel)
            rarities.pack(anchor="w")
            for position, rarity in enumerate(RARITIES):
                ttk.Radiobutton(
                    rarities,
                    text=rarity,
                    value=rarity,
                    variable=self.rarity_var,
                    image=self.icons.rarity_badge(rarity, 16),
                    compound="left",
                    command=self._show_selected,
                ).grid(row=position // 2, column=position % 2, sticky="w", padx=(0, 18))
            ttk.Label(panel, textvariable=self.unique_text, style="Muted.TLabel", wraplength=wrap, justify="left").pack(anchor="w")
            numbers = ttk.Frame(panel)
            numbers.pack(anchor="w", pady=(10, 0))
            ttk.Label(numbers, text="Power").grid(row=0, column=0, sticky="w", padx=(0, 8))
            ttk.Spinbox(numbers, textvariable=self.power_var, from_=0, to=MAX_ITEM_POWER, increment=1, width=9).grid(row=0, column=1, pady=2)
            ttk.Label(numbers, text="How many").grid(row=1, column=0, sticky="w", padx=(0, 8))
            ttk.Spinbox(numbers, textvariable=self.count_var, from_=1, to=MAX_STACK, increment=1, width=9).grid(row=1, column=1, pady=2)
            ttk.Label(
                panel, text=f"Your strongest item has power {best_power}. Much higher may be removed by the game.", style="Muted.TLabel", wraplength=wrap
            ).pack(anchor="w", pady=(2, 0))

            equip_row = ttk.Frame(panel)
            equip_row.pack(anchor="w", pady=(10, 0))
            self.equip_check = ttk.Checkbutton(equip_row, text="Equip it", variable=self.equip_var, command=self._show_slot)
            self.equip_check.pack(side="left")
            self.slot_box = ttk.Combobox(equip_row, textvariable=self.slot_var, state="readonly", width=28)
            self.slot_box.pack(side="left", padx=(8, 0))
            self.slot_box.bind("<<ComboboxSelected>>", lambda _event: self._pick_slot())
            ttk.Label(panel, textvariable=self.slot_note, style="Muted.TLabel", wraplength=wrap, justify="left").pack(anchor="w")
        self.confirm_button = ttk.Button(
            panel, text="Add to inventory" if self.mode == "add" else "Use this item", style="Accent.TButton", command=self._confirm
        )
        self.confirm_button.pack(anchor="w", pady=(12, 0))
        self.message_var = tk.StringVar()
        self.message = ttk.Label(panel, textvariable=self.message_var, style="Muted.TLabel", wraplength=wrap, justify="left")
        self.message.pack(anchor="w", pady=(6, 0))

        hint = (
            "Every item in the game is listed. Confirmed items have been seen in real saves, so the game knows them. "
            "For the others the editor has to guess the game's name for the item; if it guesses wrong, the game may "
            "drop the item. Items you find in the game become confirmed automatically."
        )
        ttk.Label(frame, text=hint, style="Muted.TLabel", wraplength=text_width(self, 110), justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        if self.advanced:
            raw = ttk.Frame(frame)
            raw.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
            ttk.Label(raw, text="Item ID").pack(side="left")
            self.raw_var = tk.StringVar(value="SW.Item.")
            ttk.Entry(raw, textvariable=self.raw_var, width=40).pack(side="left", padx=6)
            ttk.Button(raw, text="Use this ID", command=self._use_raw).pack(side="left")
            ttk.Label(raw, text="IDs the game doesn't know may make it drop the item.", style="Muted.TLabel").pack(side="left", padx=(10, 0))

        bottom = ttk.Frame(frame)
        bottom.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(bottom, text="Close" if self.mode == "add" else "Cancel", command=self.destroy).pack(side="right")

    def _fill(self) -> None:
        query = self.search_var.get().strip().lower()
        kind = self.kind_var.get()
        self.tree.delete(*self.tree.get_children())
        self._by_iid.clear()
        for item in self.catalog:
            if kind != ALL and item.kind != kind:
                continue
            if self.for_slot is not None and not slots_for(item.kind, item.piece, [self.for_slot]):
                continue
            if self.confirmed_only.get() and not item.confirmed:
                continue
            words = f"{item.name} {item.unique or ''} {item.tag}".lower()
            if query and query not in words:
                continue
            iid = self.tree.insert(
                "",
                "end",
                text=" " + item.name,
                image=self.icons.item_image(item.tag, "", LIST_ICON_SIZE, item.name),
                values=(item.kind, "Confirmed" if item.confirmed else "Unconfirmed"),
                tags=() if item.confirmed else ("unconfirmed",),
            )
            self._by_iid[iid] = item
        if not self._by_iid:
            self.name_var.set("Nothing matches. Try another search." if self.catalog else "No items found in your saves yet.")
            self._show_selected()
        first = next(iter(self._by_iid), None)
        if first is not None:
            self.tree.selection_set(first)
            self.tree.see(first)

    def selected_item(self) -> CatalogItem | None:
        selection = self.tree.selection()
        return self._by_iid.get(selection[0]) if selection else None

    def _show_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            self.preview.configure(image="")
            for var in (self.kind_text, self.status_text, self.unique_text):
                var.set("")
            self._show_slot()
            return
        rarity = self._rarity()
        as_unique = rarity == "Unique" and bool(item.unique)
        shown_name = item.name_at(rarity)
        self.preview.configure(image=self.icons.item_image(item.tag, "", PREVIEW_SIZE, shown_name))
        self.name_var.set(shown_name)
        kind = item.kind + (f"  ·  {item.piece.lower()}" if item.piece else "")
        self.kind_text.set(kind + (f"  ·  {item.tag_at(rarity)}" if self.advanced else ""))
        if item.confirmed_at(rarity):
            self.status_text.set("Confirmed: seen in real saves, so the game knows it.")
            self.status_label.configure(style="Success.TLabel")
        else:
            self.status_text.set("Unconfirmed: the game's name for this item is a best guess.")
            self.status_label.configure(style="Warn.TLabel")
        if as_unique:
            effect = f" {item.unique_effect}" if item.unique_effect else ""
            self.unique_text.set(f"At Unique rarity this is the {item.unique} (a Unique {item.name}).{effect}")
        elif item.unique and self.mode == "add":
            self.unique_text.set(f"Pick Unique to get the {item.unique}.")
        else:
            self.unique_text.set("")
        self._show_slot()
        if self.winfo_ismapped():
            fit_to_contents(self)  # longer text can need more room

    # ------------------------------------------------------------ equipping

    def _fitting_slots(self) -> list[GearSlot]:
        item = self.selected_item()
        return slots_for(item.kind, item.piece, self.slots) if item is not None else []

    def _chosen_slot(self) -> GearSlot | None:
        return self._slot_by_choice.get(self.slot_var.get())

    def _pick_slot(self) -> None:
        slot = self._chosen_slot()
        self._chosen_slot_tag = slot.tag if slot else None
        self._show_slot()

    def _show_slot(self) -> None:
        """Fill the slot list for the selected item and say what equipping it would do."""
        if self.mode != "add":
            return
        slots = self._fitting_slots()
        equipped = self.equipped()
        self._slot_by_choice = {slot_choice(slot, equipped.get(slot.tag), self.hero_level): slot for slot in slots}
        self.slot_box["values"] = list(self._slot_by_choice)
        chosen = next((slot for slot in slots if slot.tag == self._chosen_slot_tag), None) or default_slot(slots, equipped, self.hero_level)
        self.slot_var.set(next((choice for choice, slot in self._slot_by_choice.items() if slot == chosen), ""))
        if not slots:
            self.equip_check.state(["disabled"])
            self.slot_box.state(["disabled"])
            self.slot_note.set("The editor doesn't know which slot this goes in." if self.selected_item() and self.slots else "")
        else:
            self.equip_check.state(["!disabled"])
            self.slot_box.state(["!disabled"] if self.equip_var.get() else ["disabled"])
            self.slot_note.set(self._slot_note(chosen, equipped) if self.equip_var.get() else "")
        equipping = self.equip_var.get() and chosen is not None
        self.confirm_button.configure(text="Add and equip" if equipping else "Add to inventory")

    def _slot_note(self, slot: GearSlot | None, equipped: dict[str, str]) -> str:
        if slot is None:
            return "No slot for this is open yet."
        notes = []
        if not slot_open(slot, self.hero_level):
            notes.append(f"This slot opens at level {slot.level}.")
        elif slot.tag in equipped:
            notes.append(f"Your {equipped[slot.tag]} goes back to your inventory.")
        if not slot.confirmed:
            notes.append("The game's name for this slot is a best guess.")
        return " ".join(notes)

    # ---------------------------------------------------------------- adding

    def _say(self, text: str, error: bool = False) -> None:
        self.message_var.set(text)
        self.message.configure(style="Error.TLabel" if error else "Success.TLabel")

    def _confirm(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        slot = self._chosen_slot() if self.mode == "add" and self.equip_var.get() else None
        rarity = self._rarity()
        if not self._accept_guesses(item, slot, rarity):
            return
        self._finish(item.tag_at(rarity), item.name_at(rarity), slot)

    def _rarity(self) -> str | None:
        """The rarity being added at. A Unique has an ID of its own, so the rarity decides which item this is."""
        return self.rarity_var.get() if self.mode == "add" else None

    def _accept_guesses(self, item: CatalogItem, slot: GearSlot | None, rarity: str | None = None) -> bool:
        """Ask once per window before using an item, or a slot, whose name in the game is a best guess."""
        guessed_item = not item.confirmed_at(rarity) and not self._unconfirmed_ok
        guessed_slot = slot is not None and not slot.confirmed and not self._guessed_slot_ok
        if not guessed_item and not guessed_slot:
            return True
        if guessed_item and guessed_slot:
            what = f"this item and for the {slot.label.lower()} slot haven't"
        elif guessed_item:
            what = "this item hasn't"
        else:
            what = f"the {slot.label.lower()} slot hasn't"
        lines = [
            f"The game's name for {what} been seen in a real save yet, so the editor is making a best guess.",
            "If a guess is wrong, the game removes the item when it loads your hero (it did in testing) and keeps "
            "the rest. Restore… undoes the change (a backup is made every time you save).",
        ]
        if guessed_slot:
            lines.append(f"Equip any {slot.kind.lower()} in the game once and the editor learns the slot's real name.")
        lines.append("Add it anyway?")
        if not messagebox.askyesno("Unconfirmed item" if guessed_item else "Unconfirmed slot", "\n\n".join(lines), parent=self):
            return False
        self._unconfirmed_ok |= guessed_item
        self._guessed_slot_ok |= guessed_slot
        return True

    def _use_raw(self) -> None:
        tag = self.raw_var.get().strip()
        if tag:
            self._finish(tag, tag, None)

    def _finish(self, tag: str, name: str, slot: GearSlot | None) -> None:
        if self.mode == "choose":
            self.result = tag
            self.destroy()
            return
        try:
            power = doc.parse_input(self.power_var.get(), 0)
            count = doc.parse_input(self.count_var.get(), 0)
            self.on_add(tag, self.rarity_var.get(), power, count, slot)
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        equipped = f" and equipped it ({slot.label.lower()})" if slot is not None else ""
        self._say(f"Added {name}{equipped}. Add more, or close this window.")
        self._show_slot()  # what's in the slots has changed
