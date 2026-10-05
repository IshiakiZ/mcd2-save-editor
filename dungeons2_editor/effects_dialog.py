"""The window that changes the effects and the enchantment on one item.

The game rolls a weapon, armor piece or artifact its effects when it drops, and the Enchantsmith adds one
enchantment to a weapon or armor piece. The editor writes both exactly as a real save holds them, so it only
offers the ones it has seen: the tiers in its own list (dungeons2_editor/data/effects.json) and anything on an
item in your own saves.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from .game_style import match_title_bar
from .hero import TIERS, EffectChoice, Item, _base_of
from .layout import fit_to_contents, text_width

EFFECTS, ENCHANTMENTS = "Effects", "Enchantments"
ROWS = 8  # choices in view before the list scrolls
NOT_SEEN = (
    "This tier hasn't been seen in a real save yet. Its number is from the game files' table, and the way the "
    "game saves it is worked out from the tiers that have been seen."
)


def group_key(choice: EffectChoice) -> tuple[str, str]:
    """What makes two choices tiers of the same effect."""
    return choice.effect, _base_of(choice.template)


class EffectsDialog(tk.Toplevel):
    """Pick the effects and the enchantment for ``item`` from ``gear`` and ``enchantments`` (hero.effect_choices).

    ``result`` stays None when the window is closed without applying. Apply leaves ``(effects, enchantment)``
    there: the effects the item should have, in order, and its enchantment or None.
    """

    def __init__(
        self,
        parent: tk.Misc,
        item: Item,
        gear: list[EffectChoice],
        enchantments: list[EffectChoice],
        *,
        most: int = 4,
        enchantsmith_opened: bool = True,
    ):
        super().__init__(parent)
        self.item = item
        self.own = item.own_effects
        self.most = max(most - len(self.own), 0)
        self.enchantsmith_opened = enchantsmith_opened
        self.choices = {
            EFFECTS: list(gear) if item.can_have_effects else [],
            ENCHANTMENTS: [choice for choice in enchantments if choice.fits(item.kind, item.piece)] if item.can_be_enchanted else [],
        }
        self.effects: list[EffectChoice] = [effect.as_choice() for effect in item.rolled_effects]
        enchanted = item.enchantment
        self.enchantment: EffectChoice | None = enchanted.as_choice() if enchanted is not None else None
        self._start = (list(self.effects), self.enchantment)
        self.result: tuple[list[EffectChoice], EffectChoice | None] | None = None
        self._groups: dict[str, list[EffectChoice]] = {}
        self._row: str | None = None  # the row of the list whose tiers are on offer
        self._unseen_ok = False
        self.title(f"Effects: {item.name}")
        self.transient(parent)
        match_title_bar(self)
        self._build()
        self._fill_current()
        self._fill_choices()
        fit_to_contents(self)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.search_entry.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not shown yet (e.g. while the main window is minimised); still usable

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        item = self.item
        digit = tkfont.Font(root=self, font=ttk.Style(self).lookup("Treeview", "font") or "TkDefaultFont").measure("0")
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)  # the lists take the room that's left over; the buttons always get theirs

        intro = (
            "The game rolls an item's effects when it drops: none on a Common item, one on a Rare one, two on a "
            f"Special one, and never more than {self.most + len(self.own)}. Here you choose them. The editor writes an "
            "effect or an enchantment exactly as a real save holds it, so it offers the ones it has seen so far. Share "
            "item IDs sends it the ones on your gear, which is how the lists grow."
        )
        if item.rarity == "Unique":
            intro += (
                " In the game a Unique also comes with an effect of its own. The editor hasn't seen one saved yet, so "
                "a Unique it added may be missing that one."
            )
        ttk.Label(frame, text=intro, style="Muted.TLabel", wraplength=text_width(self, 118), justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        # Left: what the item has.
        left = ttk.Frame(frame)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        grade = "" if item.is_talisman else f"{item.rarity} {item.kind.lower()}, power {item.power}"
        ttk.Label(left, text=f"On your {item.name}" + (f"  ({grade})" if grade else ""), style="Heading.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.current = ttk.Treeview(left, columns=("number", "kind"), selectmode="browse", height=ROWS - 2)
        self.current.heading("#0", text="Effect")
        self.current.heading("number", text="Strength")
        self.current.heading("kind", text="Kind")
        self.current.column("#0", width=digit * 24, stretch=True)
        self.current.column("number", width=digit * 10, stretch=False)
        self.current.column("kind", width=digit * 14, stretch=False)
        self.current.tag_configure("own", foreground=ttk.Style(self).lookup("Muted.TLabel", "foreground"))
        self.current.grid(row=1, column=0, sticky="nsew")
        current_scroll = ttk.Scrollbar(left, orient="vertical", command=self.current.yview)
        current_scroll.grid(row=1, column=1, sticky="ns")
        self.current.configure(yscrollcommand=current_scroll.set)
        self.current.bind("<<TreeviewSelect>>", lambda _event: self._show_buttons())
        self.current.bind("<Delete>", lambda _event: self.remove())
        under = ttk.Frame(left)
        under.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.remove_button = ttk.Button(under, text="Remove", command=self.remove)
        self.remove_button.pack(side="left")
        self.clear_button = ttk.Button(under, text="Remove all", command=self.remove_all)
        self.clear_button.pack(side="left", padx=6)
        self.count_var = tk.StringVar()
        ttk.Label(under, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

        # Right: what can be added.
        right = ttk.Frame(frame)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        switch = ttk.Frame(right)
        switch.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.kind_var = tk.StringVar(value=EFFECTS if item.can_have_effects or not item.can_be_enchanted else ENCHANTMENTS)
        self.kind_buttons = {}
        for kind in (EFFECTS, ENCHANTMENTS):
            button = ttk.Radiobutton(switch, text=kind, value=kind, variable=self.kind_var, command=self._fill_choices)
            button.pack(side="left", padx=(0, 12))
            self.kind_buttons[kind] = button
        if not item.can_have_effects:
            self.kind_buttons[EFFECTS].state(["disabled"])
        if not item.can_be_enchanted:
            self.kind_buttons[ENCHANTMENTS].state(["disabled"])
        find = ttk.Frame(right)
        find.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(find, text="Find").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._fill_choices())
        self.search_entry = ttk.Entry(find, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.listing = ttk.Treeview(right, columns=("tiers", "where"), selectmode="browse", height=ROWS)
        self.listing.heading("#0", text="Name")
        self.listing.heading("tiers", text="Tiers")
        self.listing.heading("where", text="In the game")
        self.listing.column("#0", width=digit * 30, stretch=True)
        self.listing.column("tiers", width=digit * 10, stretch=False)
        self.listing.column("where", width=digit * 34, stretch=True)
        self.listing.grid(row=2, column=0, sticky="nsew")
        listing_scroll = ttk.Scrollbar(right, orient="vertical", command=self.listing.yview)
        listing_scroll.grid(row=2, column=1, sticky="ns")
        self.listing.configure(yscrollcommand=listing_scroll.set)
        self.listing.bind("<<TreeviewSelect>>", lambda _event: self._on_row())
        self.listing.bind("<Double-1>", self._on_double_click)
        self.listing.bind("<Return>", lambda _event: self.add())
        tiers = ttk.Frame(right)
        tiers.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(tiers, text="Tier").pack(side="left", padx=(0, 8))
        self.tier_var = tk.StringVar()
        self.tier_buttons = {}
        for tier in TIERS:
            button = ttk.Radiobutton(tiers, text=tier, value=tier, variable=self.tier_var, command=self._show_choice)
            button.pack(side="left", padx=(0, 12))
            self.tier_buttons[tier] = button
        self.add_button = ttk.Button(tiers, text="Add", style="Accent.TButton", command=self.add)
        self.add_button.pack(side="right")
        self.note_var = tk.StringVar()
        self.note = ttk.Label(right, textvariable=self.note_var, style="Muted.TLabel", wraplength=text_width(self, 62), justify="left")
        self.note.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        bottom = ttk.Frame(frame)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.message_var = tk.StringVar()
        self.message = ttk.Label(bottom, textvariable=self.message_var, style="Muted.TLabel")
        self.message.pack(side="left")
        self.apply_button = ttk.Button(bottom, text="Apply", style="Accent.TButton", command=self.apply)
        self.apply_button.pack(side="right")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right", padx=8)

    # ------------------------------------------------------- what the item has

    def _fill_current(self, select: str | None = None) -> None:
        self.current.delete(*self.current.get_children())
        for position, choice in enumerate(self.effects):
            self.current.insert("", "end", iid=f"effect {position}", text=choice.title, values=(choice.number, "Effect"))
        if self.enchantment is not None:
            self.current.insert("", "end", iid="enchantment", text=self.enchantment.title, values=("", "Enchantment"))
        for position, effect in enumerate(self.own):
            self.current.insert("", "end", iid=f"own {position}", text=effect.title, values=("", "Its own"), tags=("own",))
        if select is not None and self.current.exists(select):
            self.current.selection_set(select)
            self.current.see(select)
        self.count_var.set(f"{len(self.effects)} of {self.most} effects" if self.item.can_have_effects else "")
        self._show_buttons()

    def _show_buttons(self) -> None:
        picked = self._picked_current()
        self.remove_button.state(["!disabled"] if picked is not None and not picked.startswith("own") else ["disabled"])
        self.clear_button.state(["!disabled"] if self.effects or self.enchantment is not None else ["disabled"])
        changed = (self.effects, self.enchantment) != self._start
        self.apply_button.state(["!disabled"] if changed else ["disabled"])
        self._show_choice()

    def _picked_current(self) -> str | None:
        selection = self.current.selection()
        return selection[0] if selection else None

    def remove(self) -> None:
        """Take the picked effect, or the enchantment, off the item."""
        picked = self._picked_current()
        if picked is None or picked.startswith("own"):
            return
        if picked == "enchantment":
            self.enchantment = None
        else:
            del self.effects[int(picked.split()[1])]
        self._say("")
        self._fill_current()

    def remove_all(self) -> None:
        self.effects, self.enchantment = [], None
        self._say("")
        self._fill_current()

    # ------------------------------------------------------- what can be added

    def _fill_choices(self) -> None:
        kind = self.kind_var.get()
        query = self.search_var.get().strip().lower()
        self.listing.delete(*self.listing.get_children())
        self._groups.clear()
        grouped: dict[tuple[str, str], list[EffectChoice]] = {}
        for choice in self.choices[kind]:
            grouped.setdefault(group_key(choice), []).append(choice)
        for tiers in grouped.values():
            first = tiers[0]
            name = first.name + (f" ({first.maybe}?)" if first.maybe else "")
            where = first.what if kind == ENCHANTMENTS else (f"rolls on {first.rolls_on.lower()}" if first.rolls_on else "")
            if query and query not in f"{name} {where} {first.effect}".lower():
                continue
            listed = " ".join(choice.tier or "as saved" for choice in tiers)
            iid = self.listing.insert("", "end", text=name, values=(listed, where))
            self._groups[iid] = tiers
        self._row = next(iter(self._groups), None)
        if self._row is not None:
            self.listing.selection_set(self._row)
            self.listing.see(self._row)
        self._show_choice(pick_tier=True)

    def _on_row(self) -> None:
        """Another effect was picked in the list: offer its tiers, starting from the best one seen."""
        selection = self.listing.selection()
        row = selection[0] if selection else None
        if row != self._row:
            self._row = row
            self._show_choice(pick_tier=True)

    def _group(self) -> list[EffectChoice]:
        selection = self.listing.selection()
        return self._groups.get(selection[0], []) if selection else []

    def selected_choice(self) -> EffectChoice | None:
        """The tier picked of the effect picked in the list."""
        group = self._group()
        return next((choice for choice in group if choice.tier == self.tier_var.get()), None) or (group[0] if len(group) == 1 else None)

    def _show_choice(self, pick_tier: bool = False) -> None:
        """Offer the picked effect's tiers, and say what adding the picked tier would do."""
        group = self._group()
        kind = self.kind_var.get()
        have = {choice.tier for choice in group}
        if pick_tier or self.tier_var.get() not in have:
            best = [choice for choice in group if choice.seen] or group
            self.tier_var.set(best[-1].tier if best else "")
        for tier, button in self.tier_buttons.items():
            button.state(["!disabled"] if tier in have else ["disabled"])
        choice = self.selected_choice()
        if choice is None:
            self.add_button.configure(text="Add")
            self.add_button.state(["disabled"])
            self.note.configure(style="Muted.TLabel")
            self.note_var.set(self._nothing_to_offer(kind) if not self._groups else "")
            return
        parts = []
        if kind == ENCHANTMENTS:
            if choice.what:
                parts.append(f"{choice.what}." + (f" Tiers I, II and III: {choice.levels}." if choice.levels else ""))
            if not self.enchantsmith_opened:
                parts.append("This hero hasn't opened the Enchantsmith in the game yet.")
        else:
            parts.append(f"{choice.title}: {choice.what or choice.number + '.'}")
        if choice.yours:
            parts.append("Copied from an item in your saves.")
        elif not choice.seen:
            parts.append(NOT_SEEN)
        replaced = self._replaces(choice)
        full = kind == EFFECTS and replaced is None and len(self.effects) >= self.most
        same = replaced is not None and replaced.template == choice.template
        if full:
            parts.append(f"The game caps an item at {self.most + len(self.own)} effects, so remove one first.")
        self.add_button.state(["disabled"] if full or same else ["!disabled"])
        if kind == ENCHANTMENTS:
            self.add_button.configure(text="On the item" if same else "Enchant with it" if replaced is None else f"Change to {choice.title}")
        else:
            self.add_button.configure(text="On the item" if same else "Add this effect" if replaced is None else f"Change to tier {choice.tier}")
        self.note.configure(style="Warn.TLabel" if full or (not choice.seen and not choice.yours) else "Muted.TLabel")
        self.note_var.set(" ".join(parts))

    def _nothing_to_offer(self, kind: str) -> str:
        if self.search_var.get().strip():
            return "Nothing matches. Try another search."
        if kind == ENCHANTMENTS and not self.item.can_be_enchanted:
            return f"The {self.item.name} can't be enchanted: enchantments go on weapons and armor."
        if kind == ENCHANTMENTS:
            return (
                "The editor hasn't seen an enchantment for this kind of item saved yet. Enchant any item like it "
                "in the game and the editor can copy that enchantment from your save."
            )
        return f"The {self.item.name} can't have effects like these: the game rolls them on weapons, armor and artifacts."

    def _replaces(self, choice: EffectChoice) -> EffectChoice | None:
        """What adding ``choice`` would take the place of: the same effect at another tier, or the enchantment."""
        if choice.is_enchantment:
            return self.enchantment
        return next((other for other in self.effects if other.effect == choice.effect), None)

    def select(self, name: str, tier: str = "") -> bool:
        """Pick an effect or enchantment in the list by name, and a tier. False if it isn't listed."""
        for kind in (EFFECTS, ENCHANTMENTS):
            if any(choice.name == name for choice in self.choices[kind]) and self.kind_var.get() != kind:
                self.kind_var.set(kind)
                self._fill_choices()
        for iid, group in self._groups.items():
            if group[0].name == name and (not tier or any(choice.tier == tier for choice in group)):
                self._row = iid
                self.listing.selection_set(iid)
                self.listing.see(iid)
                self._show_choice(pick_tier=True)
                if tier:
                    self.tier_var.set(tier)
                    self._show_choice()
                return True
        return False

    def _on_double_click(self, event: tk.Event) -> None:
        if self.listing.identify_row(event.y):
            self.add()

    def add(self) -> None:
        """Put the picked tier on the item, in place of the same effect at another tier (or of the enchantment)."""
        choice = self.selected_choice()
        if choice is None or self.add_button.instate(["disabled"]) or not self._accept_unseen(choice):
            return
        if choice.is_enchantment:
            self.enchantment = choice
            picked = "enchantment"
        else:
            replaced = self._replaces(choice)
            if replaced is not None:
                self.effects[self.effects.index(replaced)] = choice
            else:
                self.effects.append(choice)
            picked = f"effect {self.effects.index(choice)}"
        self._say("")
        self._fill_current(select=picked)

    def _accept_unseen(self, choice: EffectChoice) -> bool:
        """Ask once per window before adding a tier no save has shown."""
        if choice.seen or choice.yours or self._unseen_ok:
            return True
        self._unseen_ok = messagebox.askyesno(
            "Tier not seen yet",
            f"{NOT_SEEN}\n\nIf the game doesn't know it the way the editor writes it, the game may drop the effect, or "
            "the item. Restore… undoes the change (a backup is made every time you save).\n\nAdd it anyway?",
            parent=self,
        )
        return self._unseen_ok

    def _say(self, text: str) -> None:
        self.message_var.set(text)

    def apply(self) -> None:
        self.result = (list(self.effects), self.enchantment)
        self.destroy()
