"""Sharing item IDs: the IDs in your saves that the editor doesn't know yet, ready to post on GitHub.

Only item IDs (like SW.Item.MysticHelmet) go into the report, and what the game saved as the effect of a
talisman the editor can't add with its effect yet: nothing else from the save.
"""

from __future__ import annotations

import json
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import ttk

from .hero import NOT_ADDABLE_GROUPS, Hero, game_item, is_unique_version, item_group, item_kind, local_name
from .game_style import match_title_bar
from .layout import fit_to_contents, text_width

ISSUE_URL = "https://github.com/IshiakiZ/mcd2-save-editor/issues/new"
ISSUE_TEMPLATE = "item-ids.yml"


# How the game vouches for an ID (Hero.item_types_from_the_game), as the report puts it.
SEEN_AS = {"collected": "in the collections", "merchant": "in the merchant's stock", "kept": "kept by the game"}


def unknown_ids(heroes: list[Hero]) -> list[tuple[str, str]]:
    """(item ID, note) for each ID in these saves that the editor's item list doesn't confirm, or confirms
    without knowing the item's name in the game. A name you gave the item (NAME IT…) is the note. Cosmetics, quest
    items and currencies are left out. A Unique has an ID of its own, which counts as known once the list has it.

    Only IDs the game itself vouches for are listed, with how in square brackets: an item the editor added
    under a guessed ID isn't evidence for that ID until the game has kept it."""
    seen: dict[str, str] = {}
    for hero in heroes:
        for tag, how in hero.item_types_from_the_game().items():
            seen.setdefault(tag, how)
    found = []
    for tag in sorted(seen):
        if item_group(tag) in NOT_ADDABLE_GROUPS:
            continue
        item = game_item(tag)
        unique = item is not None and is_unique_version(tag)
        confirmed = item is not None and (item.unique_id == tag if unique else item.confirmed)
        mine = local_name(tag)
        if mine and (item is None or item.name_from_id or not confirmed):
            note = mine
        elif item is None:
            note = f"new to the editor ({item_kind(tag).lower()}), what's it called in the game?"
        elif unique and not confirmed:
            note = f"{item.unique} (the Unique {item.name}): confirms the editor's guess"
        elif not confirmed:
            note = f"{item.name}: confirms the editor's guess"
        elif item.name_from_id:
            note = f"the editor calls it {item.name}; what's it called in the game?"
        else:
            continue
        found.append((tag, f"{note} [{SEEN_AS[seen[tag]]}]"))
    return found


def _last_part(name: object, prefix: str) -> str:
    name = str(name or "?")
    return name[len(prefix):] if name.startswith(prefix) else name


def effect_text(levels: list) -> str:
    """A talisman's saved levels the short way: 'HealthBoost 1.2 (HealthBoost.I) / HealthBoost 1.25
    (HealthBoost.II) / ...'. Each level's effects are named without their SW.Effect. and SW.EffectTemplate.
    prefixes. Empty if the levels aren't laid out the way the editor knows."""
    described = []
    for level in levels:
        effects = level.get("LevelEffects") if isinstance(level, dict) else None
        if not isinstance(effects, list) or not all(isinstance(effect, dict) for effect in effects):
            return ""
        parts = []
        for effect in effects:
            template = (effect.get("GeneratorData") or {}).get("GeneratorParentTemplate")
            part = f"{_last_part(effect.get('TypeTag'), 'SW.Effect.')} {json.dumps(effect.get('Intensity'))}"
            if effect.get("Quality"):
                part += f" quality {json.dumps(effect['Quality'])}"
            parts.append(f"{part} ({_last_part(template, 'SW.EffectTemplate.')})")
        described.append(" + ".join(parts) or "nothing")
    return " / ".join(described)


def talisman_effects(heroes: list[Hero]) -> list[tuple[str, str]]:
    """(talisman ID, its effect at each level) for each talisman in these saves whose effect the editor's item
    list doesn't have. A talisman the game handed over carries its effect, and that's what the editor needs
    to add that talisman so it works."""
    found: dict[str, str] = {}
    for hero in heroes:
        for item in hero.items():
            known = game_item(item.tag)
            if not item.is_talisman or item.tag in found or (known is not None and known.levels):
                continue
            levels = item.progression.get("ItemLevels")
            text = effect_text(levels) if isinstance(levels, list) and levels else ""
            if text:
                found[item.tag] = f"{item.name}'s effect: {text}"
    return sorted(found.items())


def finding_keys(heroes: list[Hero]) -> set[str]:
    """A key for each line the report would have. The editor remembers the ones you've been shown, so it can
    tell when your saves hold something that wasn't there before."""
    return {tag for tag, _note in unknown_ids(heroes)} | {f"{tag} effect" for tag, _text in talisman_effects(heroes)}


def report_text(heroes: list[Hero], version: str) -> str:
    lines = [f"{tag} - {note}" for tag, note in unknown_ids(heroes) + talisman_effects(heroes)]
    return "\n".join(lines)


def issue_url(ids_text: str, version: str) -> str:
    query = {"template": ISSUE_TEMPLATE, "title": "Item IDs from my saves", "ids": ids_text, "version": version}
    return ISSUE_URL + "?" + urllib.parse.urlencode(query)


class ShareIdsDialog(tk.Toplevel):
    """Shows the report, lets you add names, and copies it or opens a pre-filled GitHub issue."""

    def __init__(self, parent: tk.Misc, heroes: list[Hero], version: str):
        super().__init__(parent)
        self.version = version
        self.title("Share item IDs")
        self.transient(parent)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        wrap = text_width(self, 80)
        report = report_text(heroes, version)
        intro = (
            "These item IDs from your saves aren't in the editor's list yet, or are there without their in-game name. "
            "Add what the game calls each one after the dash if you know it, then open a GitHub issue (you need a "
            "free GitHub account) or copy the list. Only item IDs are shared, and what your talismans do (so the "
            "editor can add them with their effect): nothing else from your saves."
            if report
            else "Everything in your saves is already in the editor's list. Thanks for checking!"
        )
        ttk.Label(frame, text=intro, wraplength=wrap, justify="left").grid(row=0, column=0, sticky="w")
        self.text = tk.Text(frame, height=10, width=80, wrap="none", font=("Consolas", 10))
        self.text.insert("1.0", report)
        self.text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.message = tk.StringVar()
        ttk.Label(buttons, textvariable=self.message, style="Success.TLabel").pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.copy_button = ttk.Button(buttons, text="Copy", command=self.copy)
        self.copy_button.pack(side="right", padx=6)
        self.issue_button = ttk.Button(buttons, text="Open a GitHub issue…", style="Accent.TButton", command=self.open_issue)
        self.issue_button.pack(side="right")
        if not report:
            self.copy_button.state(["disabled"])
            self.issue_button.state(["disabled"])
        fit_to_contents(self, 720, 380)
        self.bind("<Escape>", lambda _event: self.destroy())

    def report(self) -> str:
        return self.text.get("1.0", "end").strip()

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.report())
        self.message.set("Copied.")

    def open_issue(self) -> None:
        webbrowser.open(issue_url(self.report(), self.version))
        self.message.set("Opened in your browser.")
