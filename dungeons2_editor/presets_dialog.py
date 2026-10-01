"""The Presets window: pick a ready-made set of changes, see exactly what it will do, apply it."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Callable

from . import document as doc
from . import presets
from .hero import MAX_ITEM_POWER, RARITIES, CatalogItem, Enchantment, GearSlot, Hero, attribute_label, format_amount
from .icons import IconLibrary
from .layout import fit_to_contents, text_width

GROUP_PREFIX = "group:"
SIZE = (1000, 680)
ENCHANTING_HELP = (
    "The editor can't add enchantments yet, so put these on at the Enchantsmith. Each weapon and armor piece takes "
    "one enchantment, and a book works on any number of items. Enchanting costs enchantment points (set them on the "
    "Hero tab) and Echo Shards."
)


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
        slots: list[GearSlot] | None = None,
        icons: IconLibrary | None = None,
    ):
        super().__init__(parent)
        self.hero = hero
        self.catalog = catalog
        self.advanced = advanced
        self.on_applied = on_applied
        self.slots = slots
        self.icons = icons
        self.plan: presets.Plan | None = None
        self._shown_preset: presets.Preset | None = None
        self.title("Presets")
        self.transient(parent)
        self.geometry("{}x{}".format(*SIZE))
        self._build(text_font)
        first = self.listing.get_children(self.listing.get_children()[0])[0]
        self.listing.selection_set(first)
        self.listing.focus(first)
        self._refresh()
        fit_to_contents(self, *SIZE)
        self.bind("<Escape>", lambda _event: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass

    @property
    def preset(self) -> presets.Preset:
        selection = self.listing.selection()
        iid = selection[0] if selection else "0"
        if iid.startswith(GROUP_PREFIX):
            iid = self.listing.get_children(iid)[0]
        return presets.PRESETS[int(iid)]

    def _build(self, text_font: object) -> None:
        wrap = text_width(self, 90)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        self.listing = ttk.Treeview(frame, show="tree", selectmode="browse")
        self.listing.column("#0", width=text_width(self, 36))
        for group in presets.GROUPS:
            group_iid = GROUP_PREFIX + group
            self.listing.insert("", "end", iid=group_iid, text=group, open=True, tags=("group",))
            for number, preset in enumerate(presets.PRESETS):
                if preset.group == group:
                    label = preset.title + ("  (experimental)" if preset.experimental else "")
                    self.listing.insert(group_iid, "end", iid=str(number), text=label)
        self.listing.tag_configure("group", font=(text_font.actual("family"), text_font.actual("size"), "bold"))
        self.listing.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        self.listing.bind("<<TreeviewSelect>>", lambda _event: self._on_pick())

        panel = ttk.Frame(frame)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)
        self.title_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.goal_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.goal_var, style="Muted.TLabel", wraplength=wrap).grid(row=1, column=0, sticky="w")

        options = ttk.Frame(panel)
        options.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.power_row = ttk.Frame(options)
        self.power_row.grid(row=0, column=0, sticky="w")
        ttk.Label(self.power_row, text="Item power").pack(side="left")
        self.power_var = tk.StringVar(value=str(self.hero.best_power()))
        power = ttk.Spinbox(self.power_row, textvariable=self.power_var, from_=1, to=MAX_ITEM_POWER, increment=1, width=8, command=self._refresh)
        power.pack(side="left", padx=8)
        power.bind("<Return>", lambda _event: self._refresh())
        power.bind("<FocusOut>", lambda _event: self._refresh())
        ttk.Label(
            self.power_row,
            text=f"Your strongest item has power {self.hero.best_power()}. Far above your level's usual power, the game may lower it.",
            style="Muted.TLabel",
        ).pack(side="left")

        self.rarity_row = ttk.Frame(options)
        self.rarity_row.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(self.rarity_row, text="Rarity").pack(side="left", padx=(0, 8))
        self.rarity_var = tk.StringVar(value="Unique")
        for rarity in RARITIES:
            badge = self.icons.rarity_badge(rarity, 16) if self.icons else ""
            ttk.Radiobutton(
                self.rarity_row, text=rarity, value=rarity, variable=self.rarity_var, image=badge, compound="left", command=self._refresh
            ).pack(side="left", padx=(0, 12))
        ttk.Label(self.rarity_row, text="(artifacts top out at Special, talismans are Common)", style="Muted.TLabel").pack(side="left")

        self.equip_var = tk.BooleanVar(value=False)
        self.equip_check = ttk.Checkbutton(
            options, text="Equip them (whatever is in those slots now goes back to your inventory)", variable=self.equip_var, command=self._refresh
        )
        self.equip_check.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.include_unconfirmed = tk.BooleanVar(value=False)
        self.unconfirmed_check = ttk.Checkbutton(
            options,
            text="Also add unconfirmed items (the game's name for them is a best guess)",
            variable=self.include_unconfirmed,
            command=self._refresh,
        )
        self.unconfirmed_check.grid(row=3, column=0, sticky="w", pady=(4, 0))

        text_frame = ttk.Frame(panel)
        text_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.text = tk.Text(text_frame, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, font=text_font, padx=2, pady=6, height=18)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)
        self.text.configure(background=self.cget("background"))
        muted = ttk.Style(self).lookup("Muted.TLabel", "foreground")
        family, size = text_font.actual("family"), text_font.actual("size")
        self.text.tag_configure("heading", font=(family, size, "bold"), spacing1=10, spacing3=2)
        self.text.tag_configure("bold", font=(family, size, "bold"))
        self.text.tag_configure("muted", foreground=muted)
        self.text.tag_configure("warn", foreground="#b35900")
        self.text.tag_configure("link", foreground="#0b6f80", underline=True)
        indent, column = text_width(self, 3), text_width(self, 19)
        self.text.tag_configure("row", tabs=(indent, column), lmargin2=column)
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

    def _on_pick(self) -> None:
        selection = self.listing.selection()
        if selection and selection[0].startswith(GROUP_PREFIX):
            self.listing.selection_set(self.listing.get_children(selection[0])[0])  # fires this again
            return
        self._say("")
        self._refresh()

    def _power(self) -> int | None:
        try:
            power = doc.parse_input(self.power_var.get(), 0)
        except ValueError:
            return None
        return power if isinstance(power, int) and 1 <= power <= MAX_ITEM_POWER else None

    def _show_options(self, preset: presets.Preset) -> None:
        adds_items = bool(preset.items)
        for row, shown in ((self.power_row, preset.upgrade_gear or adds_items), (self.rarity_row, preset.choose_rarity)):
            if shown:
                row.grid()
            else:
                row.grid_remove()
        for check in (self.equip_check, self.unconfirmed_check):
            if adds_items:
                check.grid()
            else:
                check.grid_remove()
        if preset is not self._shown_preset:
            self._shown_preset = preset
            self.equip_var.set(preset.equip)

    def _refresh(self) -> None:
        preset = self.preset
        self.title_var.set(preset.title)
        self.goal_var.set(preset.goal)
        self._show_options(preset)
        power = self._power()
        self.plan = presets.plan(
            preset,
            self.hero,
            self.catalog,
            power or self.hero.best_power(),
            self.include_unconfirmed.get(),
            rarity=self.rarity_var.get(),
            equip=self.equip_var.get() and bool(preset.items),
            slots=self.slots or presets.GEAR_SLOTS,
            check_level=not self.advanced,
        )
        self._write(preset)
        if self.winfo_ismapped():
            fit_to_contents(self)  # some presets show more options
        if power is None and (preset.upgrade_gear or preset.items):
            self._say("Item power must be a whole number of at least 1.", error=True)
            self.apply_button.state(["disabled"])
        else:
            self.apply_button.state(["!disabled"] if self.plan.changes_anything else ["disabled"])
            if not self.message_var.get().startswith("Applied"):
                self._say("")

    def _write(self, preset: presets.Preset) -> None:
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        if preset.experimental:
            text.insert("end", "Experimental. Back up first; you can undo with Restore….\n", "warn")
        text.insert("end", preset.details + "\n")
        text.insert("end", "What it will do\n", "heading")
        if preset.choose_rarity:
            self._write_loadout(preset)
        else:
            self._write_changes()
        suggestions = presets.enchant_suggestions(preset)
        if suggestions:
            self._write_enchantments(suggestions)
        sources = list(preset.sources)
        if suggestions and presets.METABOT_ENCHANTMENTS not in sources:
            sources.append(presets.METABOT_ENCHANTMENTS)
        if sources:
            text.insert("end", "Where this comes from\n", "heading")
            text.insert("end", "Community datamines and tests of the game (build 1.1.1.0):\n", "muted")
            for number, url in enumerate(sources):
                tag = f"source{number}"
                text.insert("end", f"{url}\n", ("link", tag))
                text.tag_bind(tag, "<Button-1>", lambda _event, url=url: webbrowser.open(url))
        text.configure(state="disabled")

    def _write_changes(self) -> None:
        """Goal presets: a line per change."""
        text, plan = self.text, self.plan
        lines = presets.describe(plan, self.hero)
        for line in lines:
            text.insert("end", f"•  {line}\n")
        if not lines:
            text.insert("end", "Nothing to change: this hero already matches.\n", "muted")
        if plan.unconfirmed:
            text.insert("end", "Unconfirmed items\n", "heading")
            text.insert(
                "end",
                "These can be added, but the game's name for them hasn't been seen in a real save yet. If the editor's "
                "guess is wrong, the game may drop them. Tick \"Also add unconfirmed items\" above to include them, "
                "or find one in the game first.\n",
                "muted",
            )
            for kit_item, found in plan.unconfirmed:
                text.insert("end", f"•  {kit_item.name} ({found.kind.lower()})" + (f": {kit_item.why}" if kit_item.why else "") + "\n")
                if kit_item.where:
                    text.insert("end", f"   {kit_item.where}\n", "muted")
        if plan.find:
            text.insert("end", "Find these in the game first\n", "heading")
            text.insert("end", "The editor doesn't know these items yet, so it can't add them.\n", "muted")
            for kit_item in plan.find:
                text.insert("end", f"•  {kit_item.name} ({kit_item.kind.lower()})" + (f": {kit_item.why}" if kit_item.why else "") + "\n")
                text.insert("end", f"   {kit_item.where or 'Where to find it is not known yet.'}\n", "muted")

    def _write_loadout(self, preset: presets.Preset) -> None:
        """Kits and best gear: the stats, then one short line per slot."""
        text, plan = self.text, self.plan
        equip = self.equip_var.get()
        for name, value in plan.stats.items():
            text.insert("end", f"•  {attribute_label(name)}: {format_amount(self.hero.attribute(name))} → {format_amount(value)}\n")
        rows = presets.loadout(preset, plan, self.hero, self.catalog)
        text.insert("end", f"•  {plan.rarity} gear at power {format_amount(plan.power)}, " + ("equipped:" if equip else "into your inventory:") + "\n")
        places: dict[str, list[presets.LoadoutRow]] = {}
        for row in rows:
            places.setdefault(row.place, []).append(row)
        for place, group in places.items():
            text.insert("end", f"\t{place}\t", "row")
            for position, row in enumerate(group):
                if position:
                    text.insert("end", ", ", "row")
                left_out = row.state in ("left out", "unknown")
                text.insert("end", row.name, ("row", "muted") if left_out else ("row",))
                note = {"yours": " (yours)", "unknown": " (unknown item)"}.get(row.state, "")
                if equip and not left_out and not row.equipped:
                    note += " (inventory)"
                if note:
                    text.insert("end", note, ("row", "muted"))
            text.insert("end", "\n", "row")
        notes = []
        if any(row.state == "left out" for row in rows):
            notes.append(
                "Grey items are unconfirmed (the editor has to guess the game's name for them), so they're left out: "
                "in a test, the game removed every unconfirmed item a kit added. Tick \"Also add unconfirmed items\" "
                "to try them anyway."
            )
        guesses = []
        guessed = sum(row.state == "add" and not row.confirmed for row in rows)
        if guessed:
            guesses.append(f"{guessed} of these items" if guessed < len(rows) else "these items")
        if any(not entry.slot.confirmed for entry in [*plan.add, *plan.have] if entry.slot is not None):
            guesses.append("the armor, artifact and talisman slots")
        if guesses:
            notes.append(f"Best guesses: the game's names for {' and '.join(guesses)} haven't been seen in a real save yet.")
        if equip and any(row.state in ("add", "yours") and not row.equipped for row in rows):
            notes.append("(inventory): that slot opens at a higher level, so it goes to your inventory.")
        for note in notes:
            text.insert("end", note + "\n", "muted")

    def _write_enchantments(self, suggestions: list[tuple[presets.KitItem, list[Enchantment | str]]]) -> None:
        """One line per item, then what each enchantment does, once."""
        text = self.text
        text.insert("end", "Enchantments to pick in the game\n", "heading")
        text.insert("end", ENCHANTING_HELP + "\n", "muted")
        described: dict[str, Enchantment] = {}
        for kit_item, picks in suggestions:
            found = presets.find_item(kit_item.name, self.catalog)
            place = presets.place_of(found.kind, found.piece) if found else kit_item.kind
            text.insert("end", f"\t{place}\t", "row")
            for position, pick in enumerate(picks):
                name = pick.name if isinstance(pick, Enchantment) else pick
                text.insert("end", ("" if position == 0 else " or ") + name, ("row", "bold"))
                if isinstance(pick, Enchantment):
                    described.setdefault(pick.name, pick)
                    if pick.book:
                        text.insert("end", f" (book: {pick.book})", ("row", "muted"))
            text.insert("end", "\n", "row")
        for enchantment in described.values():
            text.insert("end", f"{enchantment.name}: {enchantment.tier3}\n", "muted")

    def _accept_guesses(self) -> bool:
        """Ask before adding items, or using slots, whose names in the game are best guesses."""
        items = sum(not addition.found.confirmed for addition in self.plan.add)
        slots = sorted({entry.slot.label.lower() for entry in [*self.plan.add, *self.plan.have] if entry.slot and not entry.slot.confirmed})
        if not items and not slots:
            return True
        lines = []
        if items:
            lines.append(
                f"{items} of the items {'is' if items == 1 else 'are'} unconfirmed: the game's name for "
                f"{'it' if items == 1 else 'them'} is a best guess, and if a guess is wrong the game may drop the item."
            )
        if slots:
            lines.append(f"These slot names are best guesses too: {', '.join(slots)}. If one is wrong, the game may leave that item unequipped.")
        lines.append("If the game won't load this hero afterwards, undo it with Restore… (a backup is made every time you save).")
        lines.append("Apply anyway?")
        return messagebox.askyesno("Best guesses", "\n\n".join(lines), parent=self)

    def _say(self, text: str, error: bool = False) -> None:
        self.message_var.set(text)
        self.message.configure(style="Error.TLabel" if error else "Success.TLabel" if text.startswith("Applied") else "Muted.TLabel")

    def _apply(self) -> None:
        if self.plan is None or not self.plan.changes_anything:
            return
        if not self._accept_guesses():
            return
        try:
            presets.apply(self.plan, self.hero, self.catalog, game_caps=not self.advanced, check_level=not self.advanced)
        except (ValueError, KeyError) as exc:
            self._say(str(exc), error=True)
            return
        self.on_applied()
        self._say(f"Applied {self.preset.title}. Press Save to game when you're done.")
        self._refresh()
