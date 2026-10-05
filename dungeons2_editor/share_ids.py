"""Sharing item IDs: the IDs in your saves that the editor doesn't know yet, ready to post on GitHub.

Only item IDs (like SW.Item.MysticHelmet) go into the report, and the effects the game saved with items: what
a talisman does when the editor can't add it with its effect yet, the effects and enchantments on weapons,
armor and artifacts that the editor's list doesn't have, which it can't add until it has seen them, and what
each Unique holds, because the effect a Unique comes with is one the editor can't write yet. Nothing else from
the save.
"""

from __future__ import annotations

import json
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import ttk

from .hero import NOT_ADDABLE_GROUPS, UNSEEN_TAG, Hero, Item, effect_book, game_item, is_unique_version, item_group, item_kind, local_name
from .game_style import match_title_bar
from .layout import fit_to_contents, text_width

ISSUE_URL = "https://github.com/IshiakiZ/mcd2-save-editor/issues/new"
ISSUE_TEMPLATE = "item-ids.yml"
MAX_LINK = 6000  # characters; GitHub turns away a link much longer than this, so a longer list is pasted in instead
PASTE_HERE = "(paste the list here: it's on your clipboard, so press Ctrl+V)"
MAX_GEAR_LINES = 60  # lines of gear effects in one report, so it fits in a GitHub issue
MAX_UNIQUE_LINES = 12  # of those, Uniques listed only to show what a Unique holds
# Said above a report that lists Uniques: only one the game made shows how a Unique's own effect is saved.
UNIQUES_WANTED = (
    "The list shows what your Uniques hold. If the game itself gave you one of them (a drop, a reward or a purchase, "
    "not one added or changed with the editor), write \"from the game\" at the end of its line: it shows how the game "
    "saves a Unique's own effect, which the editor can't add yet."
)


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
                found[item.tag] = f"{item.name}'s effect: {text}{_whole_layout(item, levels)}"
    return sorted(found.items())


def _compact(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def _whole_layout(item: Item, levels: list) -> str:
    """For a talisman the short form can't describe, exactly what the save holds. That's one with no effect at
    some level (a companion's talisman, say), or with tags on its levels: adding one needs the rest too."""
    plain = all(isinstance(level, dict) and level.get("LevelEffects") and not level.get("LevelTags") for level in levels)
    return "" if plain else f"; levels as saved: {_compact(levels)}; effects as saved: {_compact(item.data.get('Effects'))}"


def _effect_pairs(item: Item) -> set[tuple[str, str]]:
    """(effect, template) for each effect on an item, read straight from the save."""
    pairs = set()
    for batch in item.data.get("Effects") or []:
        for effect in (batch.get("EffectsInThisBatch") or []) if isinstance(batch, dict) else []:
            if isinstance(effect, dict):
                generator = effect.get("GeneratorData")
                pairs.add((str(effect.get("TypeTag")), str(generator.get("GeneratorParentTemplate")) if isinstance(generator, dict) else ""))
    return pairs


def _known_pairs() -> set[tuple[str, str]]:
    """(effect, template) for every tier of an effect or enchantment that the editor's own list has seen saved."""
    book = effect_book()
    return {(choice.effect, choice.template) for choice in book.effects + book.enchantments if choice.seen}


def _telling_items(heroes: list[Hero]) -> list[tuple[Item, set[tuple[str, str]], bool, bool]]:
    """(item, the effects on it that are new to the editor, whether it has an effect saved some way the editor
    doesn't write, whether it's a Unique with anything saved on it) for each weapon, armor piece and artifact in
    these saves that would teach the editor something, Uniques first. An item the game hasn't shown you yet is
    left out: the editor may have just made it, or changed its effects, and then they aren't the game's word
    for anything.

    A Unique with effects is always in: the one a Unique comes with hasn't been seen in a save, so nobody knows
    yet what to look for (it could even be saved like any other effect). One the editor made holds nothing, or
    only what you gave it, which is why the report asks which Uniques the game gave you."""
    known = _known_pairs()
    found = []
    for hero in heroes:
        for item in hero.items():
            marks = item.data.get("DynamicPropertyTags")
            looked_at = item.stock_slot or (isinstance(marks, list) and UNSEEN_TAG not in marks)
            if item.is_cosmetic or item.is_talisman or not looked_at or item_group(item.tag) in NOT_ADDABLE_GROUPS:
                continue
            pairs = _effect_pairs(item) - known
            # A Unique's own effect, say: how those are saved isn't known yet. The editor never locks an effect.
            own = bool(item.own_effects) or any(effect.locked for effect in item.effects)
            unique = is_unique_version(item.tag)
            holds = unique and bool(item.data.get("Effects"))
            if pairs or own or holds:
                found.append((not unique, not own, -len(pairs), -len(item.effects), item.tag, item, pairs, own, holds))
    found.sort(key=lambda entry: entry[:5])
    return [entry[5:] for entry in found]


def gear_effects(heroes: list[Hero]) -> list[tuple[str, str]]:
    """(item ID, the effects a save holds for one) for weapons, armor and artifacts in these saves whose effects
    the editor's list doesn't have, exactly as saved. The editor can't add an effect it has never seen, so this
    is how it learns them.

    One line for each item that shows an effect or enchantment the editor doesn't know and the lines before
    it don't show, one for each item with an effect saved some way the editor doesn't write (what a Unique
    comes with, perhaps), and one for each other Unique that holds anything (MAX_UNIQUE_LINES of those at
    most), up to MAX_GEAR_LINES."""
    covered: set[tuple[str, str]] = set()
    listed: set[str] = set()
    chosen: list[Item] = []
    just_uniques = 0
    for item, pairs, own, holds in _telling_items(heroes):
        if len(chosen) >= MAX_GEAR_LINES:
            break
        first = item.tag not in listed
        telling = not pairs <= covered or (own and first)
        if not telling and not (holds and first and just_uniques < MAX_UNIQUE_LINES):
            continue
        just_uniques += not telling
        chosen.append(item)
        covered |= pairs
        listed.add(item.tag)
    return [(item.tag, f"effects on a {item.rarity} one: {_compact(item.data.get('Effects'))}") for item in chosen]


def finding_keys(heroes: list[Hero]) -> set[str]:
    """A key for each thing the report would tell. The editor remembers the ones you've been shown, so it can
    tell when your saves hold something that wasn't there before."""
    keys = {tag for tag, _note in unknown_ids(heroes)} | {f"{tag} effect" for tag, _text in talisman_effects(heroes)}
    for item, pairs, own, _holds in _telling_items(heroes):
        # A Unique that only holds what the editor writes too isn't news: it may be one the editor made.
        keys |= {f"{effect} {template}".strip() for effect, template in pairs}
        if own:
            keys.add(f"{item.tag} own effects")
    return keys


def report_text(heroes: list[Hero], version: str) -> str:
    lines = [f"{tag} - {note}" for tag, note in unknown_ids(heroes) + talisman_effects(heroes) + gear_effects(heroes)]
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
            "Your saves hold things the editor's list doesn't have yet: item IDs, what the game calls an item, or "
            "effects and enchantments on your gear, which the editor can only add once it has seen them. Add what the game calls "
            "an item after its dash if you know it, then open a GitHub issue (you need a free GitHub account) or copy "
            "the list. Only item IDs and the effects saved with items are shared: nothing else from your saves."
            if report
            else "Everything in your saves is already in the editor's list. Thanks for checking!"
        )
        if any(is_unique_version(tag) for tag, _text in gear_effects(heroes)):
            intro += "\n\n" + UNIQUES_WANTED
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
        report = self.report()
        link = issue_url(report, self.version)
        if len(link) <= MAX_LINK:
            webbrowser.open(link)
            self.message.set("Opened in your browser.")
            return
        # Too long to hand over in a link, so it goes on the clipboard and the page opens ready for it.
        self.clipboard_clear()
        self.clipboard_append(report)
        webbrowser.open(issue_url(PASTE_HERE, self.version))
        self.message.set("Copied, and the page is open: paste the list into its first box (Ctrl+V).")
