"""The Presets window: pick a ready-made set of changes, see exactly what it will do, apply it."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Callable

from . import document as doc
from . import presets
from .hero import MAX_ITEM_POWER, CatalogItem, Hero


class PresetsDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        hero: Hero,
        catalog: list[CatalogItem],
        advanced: bool,
        on_applied: Callable[[], None],
        text_font: object,
    ):
        super().__init__(parent)
        self.hero = hero
        self.catalog = catalog
        self.advanced = advanced
        self.on_applied = on_applied
        self.plan: presets.Plan | None = None
        self.title("Presets")
        self.transient(parent)
        self.geometry("900x620")
        self.minsize(720, 480)
        self._build(text_font)
        first = self.listing.get_children()[0]
        self.listing.selection_set(first)
        self.listing.focus(first)
        self.bind("<Escape>", lambda _event: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass

    @property
    def preset(self) -> presets.Preset:
        selection = self.listing.selection()
        return presets.PRESETS[int(selection[0])] if selection else presets.PRESETS[0]

    def _build(self, text_font: object) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self.listing = ttk.Treeview(frame, show="tree", selectmode="browse", height=10)
        self.listing.column("#0", width=210)
        for number, preset in enumerate(presets.PRESETS):
            label = preset.title + ("  (experimental)" if preset.experimental else "")
            self.listing.insert("", "end", iid=str(number), text=label)
        self.listing.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        self.listing.bind("<<TreeviewSelect>>", lambda _event: (self._say(""), self._refresh()))

        panel = ttk.Frame(frame)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)
        self.title_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.goal_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.goal_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w")

        self.power_row = ttk.Frame(panel)
        self.power_row.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(self.power_row, text="Power for your gear").grid(row=0, column=0, sticky="w")
        self.power_var = tk.StringVar(value=str(self.hero.best_power()))
        power = ttk.Spinbox(self.power_row, textvariable=self.power_var, from_=1, to=MAX_ITEM_POWER, increment=1, width=8, command=self._refresh)
        power.grid(row=0, column=1, sticky="w", padx=8)
        power.bind("<Return>", lambda _event: self._refresh())
        power.bind("<FocusOut>", lambda _event: self._refresh())
        ttk.Label(
            self.power_row,
            text=f"Your strongest item has power {self.hero.best_power()}. Well above your level's usual power, the game may lower it.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w")
        self.include_unconfirmed = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.power_row,
            text="Also add unconfirmed items (the game's name for them is a best guess)",
            variable=self.include_unconfirmed,
            command=self._refresh,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        text_frame = ttk.Frame(panel)
        text_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.text = tk.Text(text_frame, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, font=text_font, padx=2, pady=6)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)
        self.text.configure(background=self.cget("background"))
        muted = ttk.Style(self).lookup("Muted.TLabel", "foreground")
        self.text.tag_configure("heading", font=(text_font.actual("family"), text_font.actual("size"), "bold"), spacing1=10, spacing3=2)
        self.text.tag_configure("muted", foreground=muted)
        self.text.tag_configure("warn", foreground="#b35900")
        self.text.tag_configure("link", foreground="#0b6f80", underline=True)
        self.text.tag_bind("link", "<Enter>", lambda _event: self.text.configure(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _event: self.text.configure(cursor=""))

        bottom = ttk.Frame(frame)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.message_var = tk.StringVar()
        self.message = ttk.Label(bottom, textvariable=self.message_var, style="Muted.TLabel")
        self.message.pack(side="left")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")
        self.apply_button = ttk.Button(bottom, text="Apply to this hero", style="Accent.TButton", command=self._apply)
        self.apply_button.pack(side="right", padx=8)

    def _power(self) -> int | None:
        try:
            power = doc.parse_input(self.power_var.get(), 0)
        except ValueError:
            return None
        return power if isinstance(power, int) and 1 <= power <= MAX_ITEM_POWER else None

    def _refresh(self) -> None:
        preset = self.preset
        self.title_var.set(preset.title)
        self.goal_var.set(preset.goal)
        if preset.upgrade_gear or preset.items:
            self.power_row.grid()
        else:
            self.power_row.grid_remove()
        power = self._power()
        self.plan = presets.plan(preset, self.hero, self.catalog, power or self.hero.best_power(), self.include_unconfirmed.get())

        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        if preset.experimental:
            text.insert("end", "Experimental. Back up first; you can undo with Restore….\n", "warn")
        text.insert("end", preset.details + "\n")
        text.insert("end", "What it will do\n", "heading")
        lines = presets.describe(self.plan, self.hero)
        if lines:
            for line in lines:
                text.insert("end", f"•  {line}\n")
        else:
            text.insert("end", "Nothing to change: this hero already matches.\n", "muted")
        if self.plan.unconfirmed:
            text.insert("end", "Unconfirmed items\n", "heading")
            text.insert(
                "end",
                "These can be added, but the game's name for them hasn't been seen in a real save yet. If the editor's "
                "guess is wrong, the game may drop them. Tick \"Also add unconfirmed items\" above to include them, "
                "or find one in the game first.\n",
                "muted",
            )
            for kit_item, _found in self.plan.unconfirmed:
                text.insert("end", f"•  {kit_item.name} ({kit_item.kind.lower()}): {kit_item.why}\n")
                if kit_item.where:
                    text.insert("end", f"   {kit_item.where}\n", "muted")
        if self.plan.find:
            text.insert("end", "Find these in the game first\n", "heading")
            text.insert(
                "end",
                "The game hasn't saved these on this PC yet, so the editor can't add them. Once you pick one up, "
                "come back and the preset can add more.\n",
                "muted",
            )
            for kit_item in self.plan.find:
                text.insert("end", f"•  {kit_item.name} ({kit_item.kind.lower()}): {kit_item.why}\n")
                text.insert("end", f"   {kit_item.where or 'Where to find it is not known yet.'}\n", "muted")
        if preset.sources:
            text.insert("end", "Where this comes from\n", "heading")
            text.insert("end", "Community datamines of the game (build 1.1.1.0):\n", "muted")
            for number, url in enumerate(preset.sources):
                tag = f"source{number}"
                text.insert("end", f"{url}\n", ("link", tag))
                text.tag_bind(tag, "<Button-1>", lambda _event, url=url: webbrowser.open(url))
        text.configure(state="disabled")

        if power is None and (preset.upgrade_gear or preset.items):
            self._say("Power must be a whole number of at least 1.", error=True)
            self.apply_button.state(["disabled"])
        else:
            self.apply_button.state(["!disabled"] if self.plan.changes_anything else ["disabled"])
            if not self.message_var.get().startswith("Applied"):
                self._say("")

    def _say(self, text: str, error: bool = False) -> None:
        self.message_var.set(text)
        self.message.configure(style="Error.TLabel" if error else "Success.TLabel" if text.startswith("Applied") else "Muted.TLabel")

    def _apply(self) -> None:
        if self.plan is None or not self.plan.changes_anything:
            return
        try:
            presets.apply(self.plan, self.hero, self.catalog, game_caps=not self.advanced)
        except (ValueError, KeyError) as exc:
            self._say(str(exc), error=True)
            return
        self.on_applied()
        self._say(f"Applied {self.preset.title}. Press Save to game when you're done.")
        self._refresh()
