"""A dialog for picking an item to add (or to change an item into), with search and pictures."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import document as doc
from .hero import MAX_ITEM_POWER, MAX_STACK, RARITIES, CatalogItem
from .icons import IconLibrary

LIST_ICON_SIZE = 24
PREVIEW_SIZE = 96
ALL = "All kinds"


class ItemPicker(tk.Toplevel):
    """Pick an item from ``catalog``.

    In "add" mode, the right-hand panel sets rarity, power and count and calls
    ``on_add(tag, rarity, power, count)`` (which raises ValueError to reject);
    the dialog stays open so several items can be added. In "choose" mode the
    dialog closes and leaves the picked item ID in ``result``.
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
        on_add: Callable[[str, str, int, int], None] | None = None,
    ):
        super().__init__(parent)
        self.catalog = catalog
        self.icons = icons
        self.mode = mode
        self.advanced = advanced
        self.on_add = on_add
        self.result: str | None = None
        self._by_iid: dict[str, CatalogItem] = {}
        self.title("Add items" if mode == "add" else "Change item")
        self.transient(parent)
        self.geometry("860x580")
        self.minsize(680, 440)
        self._build(best_power)
        self._fill()
        self.search_entry.focus_set()
        self.bind("<Escape>", lambda _event: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not shown yet (e.g. while the main window is minimised); still usable

    def _build(self, best_power: int) -> None:
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
        kind_box.bind("<<ComboboxSelected>>", lambda _event: self._fill())

        listing = ttk.Frame(frame)
        listing.grid(row=1, column=0, sticky="nsew")
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(listing, columns=("kind",), selectmode="browse", style="Items.Treeview")
        self.tree.heading("#0", text="Item")
        self.tree.heading("kind", text="Kind")
        self.tree.column("#0", width=300, stretch=True)
        self.tree.column("kind", width=110, stretch=False)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())
        self.tree.bind("<Double-1>", lambda _event: self._confirm())
        self.tree.bind("<Return>", lambda _event: self._confirm())

        panel = ttk.Frame(frame, padding=(14, 0, 0, 0), width=280)
        panel.grid(row=1, column=1, sticky="nsew")
        self.preview = ttk.Label(panel)
        self.preview.pack(anchor="w")
        self.name_var = tk.StringVar(value="Pick an item on the left.")
        ttk.Label(panel, textvariable=self.name_var, style="Heading.TLabel", wraplength=260).pack(anchor="w", pady=(8, 0))
        self.kind_text = tk.StringVar()
        ttk.Label(panel, textvariable=self.kind_text, style="Muted.TLabel").pack(anchor="w")

        self.rarity_var = tk.StringVar(value="Common")
        self.power_var = tk.StringVar(value=str(best_power))
        self.count_var = tk.StringVar(value="1")
        if self.mode == "add":
            ttk.Label(panel, text="Rarity").pack(anchor="w", pady=(14, 2))
            for rarity in RARITIES:
                ttk.Radiobutton(
                    panel, text=rarity, value=rarity, variable=self.rarity_var, image=self.icons.rarity_badge(rarity, 16), compound="left"
                ).pack(anchor="w")
            numbers = ttk.Frame(panel)
            numbers.pack(anchor="w", pady=(12, 0))
            ttk.Label(numbers, text="Power").grid(row=0, column=0, sticky="w", padx=(0, 8))
            ttk.Spinbox(numbers, textvariable=self.power_var, from_=0, to=MAX_ITEM_POWER, increment=1, width=10).grid(row=0, column=1, pady=2)
            ttk.Label(numbers, text="How many").grid(row=1, column=0, sticky="w", padx=(0, 8))
            ttk.Spinbox(numbers, textvariable=self.count_var, from_=1, to=MAX_STACK, increment=1, width=10).grid(row=1, column=1, pady=2)
            ttk.Label(panel, text=f"Your strongest item has power {best_power}.", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.confirm_button = ttk.Button(
            panel, text="Add to inventory" if self.mode == "add" else "Use this item", style="Accent.TButton", command=self._confirm
        )
        self.confirm_button.pack(anchor="w", pady=(14, 0))
        self.message_var = tk.StringVar()
        self.message = ttk.Label(panel, textvariable=self.message_var, style="Muted.TLabel", wraplength=260, justify="left")
        self.message.pack(anchor="w", pady=(8, 0))

        hint = (
            "These are the items the game has saved on this PC (in your inventory, loot you've found and your "
            "collections). Find more items in the game and they'll show up here too."
        )
        ttk.Label(frame, text=hint, style="Muted.TLabel", wraplength=780, justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

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
            if query and query not in item.name.lower() and query not in item.tag.lower():
                continue
            image = self.icons.image(item.tag, LIST_ICON_SIZE) or self.icons.rarity_badge("", LIST_ICON_SIZE)
            iid = self.tree.insert("", "end", text=" " + item.name, image=image, values=(item.kind,))
            self._by_iid[iid] = item
        if not self._by_iid:
            self.name_var.set("Nothing matches. Try another search." if self.catalog else "No items found in your saves yet.")
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
            self.kind_text.set("")
            return
        self.preview.configure(image=self.icons.image(item.tag, PREVIEW_SIZE) or self.icons.rarity_badge("", PREVIEW_SIZE))
        self.name_var.set(item.name)
        self.kind_text.set(item.kind + (f"  ·  {item.tag}" if self.advanced else ""))

    def _say(self, text: str, error: bool = False) -> None:
        self.message_var.set(text)
        self.message.configure(style="Error.TLabel" if error else "Success.TLabel")

    def _confirm(self) -> None:
        item = self.selected_item()
        if item is not None:
            self._finish(item.tag, item.name)

    def _use_raw(self) -> None:
        tag = self.raw_var.get().strip()
        if tag:
            self._finish(tag, tag)

    def _finish(self, tag: str, name: str) -> None:
        if self.mode == "choose":
            self.result = tag
            self.destroy()
            return
        try:
            power = doc.parse_input(self.power_var.get(), 0)
            count = doc.parse_input(self.count_var.get(), 0)
            self.on_add(tag, self.rarity_var.get(), power, count)
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        self._say(f"Added {name}. Add more, or close this window.")
