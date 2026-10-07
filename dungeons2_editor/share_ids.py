"""Sharing item IDs: the IDs in your saves that the editor doesn't know yet, ready to post on GitHub.

Only item IDs (like SW.Item.MysticHelmet) go into the report, and what the game saved with those items: what
a talisman does when the editor can't add it with its effect yet, and the effects and enchantments on weapons,
armor and artifacts that the editor's list doesn't have, which it can't add until it has seen them. That
includes the effect a Unique comes with, for each Unique the editor hasn't seen it on. And an item saved with
a mark or a field the editor has never met on one (however the game tags a Soul Storm piece, say) goes in as
the save holds it. Nothing else from the save.
"""

from __future__ import annotations

import json
import re
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import ttk

from .hero import (
    NOT_ADDABLE_GROUPS, UNSEEN_TAG, Hero, Item, effect_book, game_item, game_items, is_unique_version, item_group, item_kind, local_name,
    own_effect,
)
from .game_style import match_title_bar
from .layout import fit_to_contents, text_width

ISSUE_URL = "https://github.com/IshiakiZ/mcd2-save-editor/issues/new"
ISSUE_TEMPLATE = "item-ids.yml"
MAX_LINK = 6000  # characters; GitHub turns away a link much longer than this, so a longer list is pasted in instead
PASTE_HERE = "(paste the list here: it's on your clipboard, so press Ctrl+V)"
MAX_GEAR_LINES = 60  # lines of gear effects in one report, so it fits in a GitHub issue
MAX_MARK_LINES = 8  # lines for items saved with a mark or a field the editor doesn't know: each holds a whole item

# Every field the editor has seen an inventory entry saved with, by where it sits in the entry. They are the
# same on every one of thousands of entries in real saves, so a field that isn't here is one the game writes
# only for something the editor has never met. The same goes for a mark besides the one for an item you
# haven't looked at.
_EFFECT_FIELDS = {"TypeTag", "Intensity", "Quality", "EnchantmentPointsInvested", "GeneratorData"}
_EFFECT_SOURCE_FIELDS = {"GeneratorParentTemplate", "Locked"}
KNOWN_FIELDS = {
    "": {"ItemData", "StackCount", "EquippedSlot", "MerchantItemSold", "MerchantDiscount"},
    "ItemData": {
        "TypeTag", "RarityTag", "Effects", "ItemProgression", "GeneratorData", "DynamicPropertyTags", "TargetSlotOverride", "PickupTimestamp",
        "EffectRerolls",
    },
    "ItemData.Effects[]": {"TypeTag", "EffectsInThisBatch"},
    "ItemData.Effects[].EffectsInThisBatch[]": _EFFECT_FIELDS,
    "ItemData.Effects[].EffectsInThisBatch[].GeneratorData": _EFFECT_SOURCE_FIELDS,
    "ItemData.GeneratorData": {"GenesisRandomSeed", "PowerGeneratorValues"},
    "ItemData.GeneratorData.PowerGeneratorValues": {
        "PlayerLevel", "AreaThreatLevel", "RecommendedThreatLevel", "ThreatSliderOffset", "ItemPowerMin", "ItemPowerMax", "RNGRoll", "ItemPower",
        "ItemPowerOriginal",
    },
    "ItemData.ItemProgression": {"CurrentLevel", "CurrentXP", "ItemLevels"},
    "ItemData.ItemProgression.ItemLevels[]": {"LevelEffects", "LevelTags"},
    "ItemData.ItemProgression.ItemLevels[].LevelEffects[]": _EFFECT_FIELDS,
    "ItemData.ItemProgression.ItemLevels[].LevelEffects[].GeneratorData": _EFFECT_SOURCE_FIELDS,
}
# What a whole item goes into the report without: neither says anything about how an item is saved.
_LEFT_OUT = {("ItemData", "PickupTimestamp"), ("ItemData.GeneratorData", "GenesisRandomSeed")}
_TAG_LIKE = re.compile(r"[A-Za-z0-9_.]{1,80}")  # the game's own names: SW.Item.Property.Dynamic.Unseen, ItemPower


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
    """(effect, template) for every tier of an effect or enchantment that the editor's own list has seen saved,
    and for every Unique's own effect it has."""
    book = effect_book()
    rolled = {(choice.effect, choice.template) for choice in book.effects + book.enchantments if choice.seen}
    return rolled | {(item.unique_own.effect, item.unique_own.template) for item in game_items() if item.unique_own is not None}


def _own_is_news(item: Item) -> bool:
    """Whether an item holds an effect saved some way that would teach the editor something: a Unique's own
    effect that isn't the one the editor would give that Unique (it has none for it, or a different one), a
    kind of batch it doesn't know, or an effect that's locked, which the editor never writes.

    A Unique's own effect that matches the editor's is never news, even where the editor only has it from
    another Unique that does the same thing: the editor writes exactly that on a Unique it adds or makes, so
    finding it in a save proves nothing (issue 22 listed several such, on items made Unique with the editor)."""
    saved = [(effect.tag, effect.strength, effect.template) for effect in item.effects if effect.is_own]
    known = own_effect(item.tag)
    if saved and saved != ([(known.effect, known.strength, known.template)] if known is not None else None):
        return True
    return any(not effect.is_own for effect in item.own_effects) or any(effect.locked for effect in item.effects)


def _telling_items(heroes: list[Hero]) -> list[tuple[Item, set[tuple[str, str]], bool]]:
    """(item, the effects on it that are new to the editor, whether it has an effect saved some way that's news:
    see _own_is_news) for each weapon, armor piece and artifact in these saves that would teach the editor
    something, Uniques first. An item the game hasn't shown you yet is left out: the editor may have just made
    it, or changed its effects, and then they aren't the game's word for anything."""
    known = _known_pairs()
    found = []
    for hero in heroes:
        for item in hero.items():
            marks = item.data.get("DynamicPropertyTags")
            looked_at = item.stock_slot or (isinstance(marks, list) and UNSEEN_TAG not in marks)
            if item.is_cosmetic or item.is_talisman or not looked_at or item_group(item.tag) in NOT_ADDABLE_GROUPS:
                continue
            pairs = _effect_pairs(item) - known
            own = _own_is_news(item)
            if pairs or own:
                found.append((not is_unique_version(item.tag), not own, -len(pairs), item.tag, item, pairs, own))
    found.sort(key=lambda entry: entry[:4])
    return [entry[4:] for entry in found]


def gear_effects(heroes: list[Hero]) -> list[tuple[str, str]]:
    """(item ID, the effects a save holds for one) for weapons, armor and artifacts in these saves whose effects
    the editor's list doesn't have, exactly as saved. The editor can't add an effect it has never seen, so this
    is how it learns them.

    One line for each item that shows an effect or enchantment the editor doesn't know and the lines before
    it don't show, and one for each kind of item with an effect saved some way that's news (a Unique's own
    effect the editor hasn't seen on that Unique, say), up to MAX_GEAR_LINES."""
    covered: set[tuple[str, str]] = set()
    listed: set[str] = set()
    chosen: list[Item] = []
    for item, pairs, own in _telling_items(heroes):
        if len(chosen) >= MAX_GEAR_LINES:
            break
        if not pairs <= covered or (own and item.tag not in listed):
            chosen.append(item)
            covered |= pairs
            listed.add(item.tag)
    return [(item.tag, f"effects on a {item.rarity} one: {_compact(item.data.get('Effects'))}") for item in chosen]


def _plain(value: object, depth: int = 0) -> object:
    """What a field the editor doesn't know holds, as it may go into the report: a number, a yes or no, or one
    of the game's own names goes in as it is. Any other text is left out, since the editor can't tell what it
    is, and nothing but item data is ever meant to leave a save."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if _TAG_LIKE.fullmatch(value) else "(text)"
    if depth >= 3:
        return "(more)"
    if isinstance(value, list):
        return [_plain(inner, depth + 1) for inner in value[:12]]
    if isinstance(value, dict):
        return {_plain(str(key)): _plain(inner, depth + 1) for key, inner in list(value.items())[:12]}
    return "(other)"


def _unknown_fields(value: object, where: str = "") -> dict[str, object]:
    """{where it sits: what it holds} for each field of an inventory entry that the editor has never seen an
    entry saved with."""
    found: dict[str, object] = {}
    if isinstance(value, dict):
        known = KNOWN_FIELDS.get(where)
        for key, inner in value.items():
            inside = f"{where}.{key}" if where else str(key)
            if known is not None and key not in known:
                found[inside if _TAG_LIKE.fullmatch(str(key)) else f"{where}.(text)".lstrip(".")] = _plain(inner)
            else:
                found.update(_unknown_fields(inner, inside))
    elif isinstance(value, list):
        for inner in value:
            found.update(_unknown_fields(inner, where + "[]"))
    return found


def _unknown_marks(item: Item) -> list[str]:
    """The marks on an item besides the one for an item you haven't looked at, the only one the editor knows."""
    marks = item.data.get("DynamicPropertyTags")
    return [str(_plain(mark)) for mark in marks if mark != UNSEEN_TAG] if isinstance(marks, list) else []


def _as_saved(item: Item) -> dict:
    """An item's whole inventory entry as the save holds it, less when it was picked up and its random seed,
    and with whatever sits in a field the editor doesn't know cut down to what may be shared (_plain)."""

    def copy_of(value: object, where: str = "") -> object:
        if isinstance(value, dict):
            known = KNOWN_FIELDS.get(where)
            return {
                key: _plain(inner) if known is not None and key not in known else copy_of(inner, f"{where}.{key}" if where else str(key))
                for key, inner in value.items()
                if (where, key) not in _LEFT_OUT
            }
        if isinstance(value, list):
            return [copy_of(inner, where + "[]") for inner in value]
        return value

    saved = copy_of(item.entry)
    marks = item.data.get("DynamicPropertyTags")
    if isinstance(marks, list) and isinstance(saved.get("ItemData"), dict):
        saved["ItemData"]["DynamicPropertyTags"] = [_plain(mark) for mark in marks]
    return saved


def _marked_items(heroes: list[Hero]) -> list[tuple[Item, list[str]]]:
    """(item, what's new on it) for each item in these saves that is saved with something the editor has never
    seen on one: a mark, or a field. Cosmetics, quest items and currencies are left out, like everywhere here.

    Whether the game has shown you the item doesn't matter for this. The editor never writes a mark or a field
    it doesn't know (an item it adds gets neither, and a copy it makes only repeats the game's own), so however
    one is saved is the game's way of saving it."""
    found = []
    for hero in heroes:
        for item in hero.items():
            if item.is_cosmetic or item_group(item.tag) in NOT_ADDABLE_GROUPS:
                continue
            news = [f"mark {mark}" for mark in _unknown_marks(item)] + [f"field {where}" for where in _unknown_fields(item.entry)]
            if news:
                found.append((item, news))
    return found


def marked_items(heroes: list[Hero]) -> list[tuple[str, str]]:
    """(item ID, the whole item as saved) for items the game saved with a mark or a field the editor has never
    seen on one. The mark for an item you haven't looked at is the only one any save sent so far holds, so
    another one is how the editor learns it: what the game tags a Soul Storm piece with, for one. The line asks
    what the game shows on the item, since a save only has the game's own name for the mark.

    One line for each item that shows something the lines before it don't, up to MAX_MARK_LINES."""
    covered: set[str] = set()
    lines = []
    for item, news in _marked_items(heroes):
        if len(lines) >= MAX_MARK_LINES:
            break
        if set(news) <= covered:
            continue
        covered |= set(news)
        what = "a talisman" if item.is_talisman else "an enchantment book" if item.is_book else f"a {item.rarity} one"
        lines.append((
            item.tag,
            f"{what} saved with something new to the editor ({', '.join(news)}), as saved: {_compact(_as_saved(item))}; "
            "what does the game show on this item that it doesn't on others?",
        ))
    return lines


def finding_keys(heroes: list[Hero]) -> set[str]:
    """A key for each thing the report would tell. The editor remembers the ones you've been shown, so it can
    tell when your saves hold something that wasn't there before."""
    keys = {tag for tag, _note in unknown_ids(heroes)} | {f"{tag} effect" for tag, _text in talisman_effects(heroes)}
    for item, pairs, own in _telling_items(heroes):
        keys |= {f"{effect} {template}".strip() for effect, template in pairs}
        if own:
            keys.add(f"{item.tag} own effects")
    for _item, news in _marked_items(heroes):
        keys |= set(news)
    return keys


def report_text(heroes: list[Hero], version: str) -> str:
    lines = [f"{tag} - {note}" for tag, note in unknown_ids(heroes) + talisman_effects(heroes) + gear_effects(heroes) + marked_items(heroes)]
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
            "Your saves hold things the editor's list doesn't have yet: item IDs, what the game calls an item, "
            "effects and enchantments on your gear, or an item the game marks some way the editor hasn't seen. It can only "
            "write those once it has seen them. Add what the game calls an item after its dash if you know it, then open a "
            "GitHub issue (you need a free GitHub account) or copy the list. Only item IDs and what the game saved with "
            "those items are shared: nothing else from your saves."
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
