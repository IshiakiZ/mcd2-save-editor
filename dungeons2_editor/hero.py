"""Friendly access to a Minecraft Dungeons II hero save (the ``Character<id>`` containers).

A hero save looks like::

    {"SerializeMeta": {"HardFormat": "FCharacterSaveV1", ...},
     "CharacterSaveV1": {
        "MetaData": {"Level": 1, "PowerLevel": 1, "IsOnline": false, ...},
        "Ability": {"Attributes": [{"AttributeName": "Emeralds", "CurrentValue": 55}, ...]},
        "Inventory": {"Entries": [{"ItemData": {...}, "StackCount": 1, "EquippedSlot": "None", ...}]},
        ...}}

``Hero`` edits that dict in place. Inventory entries include the Village
Merchant's stock (``TargetSlotOverride`` names a merchant slot) and cosmetics
granted by editions and pre-orders; cosmetics are never edited or copied.
"""

from __future__ import annotations

import copy
import json
import math
import random
import re
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

GAME_ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"  # made by tools/build_item_catalog.py
ENCHANTMENTS_FILE = GAME_ITEMS_FILE.with_name("enchantments.json")
EFFECTS_FILE = GAME_ITEMS_FILE.with_name("effects.json")

ITEM_PREFIX = "SW.Item."
COSMETIC_PREFIX = "SW.Item.Cosmetic."
RARITY_PREFIX = "SW.Rarity."
RARITIES = ("Common", "Rare", "Special", "Unique")
UNSEEN_TAG = "SW.Item.Property.Dynamic.Unseen"
EMPTY_SLOT = "None"  # an entry's EquippedSlot when it isn't equipped
MAX_STAT = 2_147_483_647
MAX_ITEM_POWER = 1_000_000
MAX_STACK = 9_999

ATTRIBUTE_LABELS = {
    "Emeralds": "Emeralds",
    "SpringStone": "Echo shards",  # the save calls Echo Shards "SpringStone"
    "EnchantmentPoints": "Enchantment points",
    "Level": "Level",
    "XP": "XP",
    "VillageMerchantUpgradeLevel": "Village merchant level",
    "VillageMerchantRefreshCharges": "Merchant refreshes",
    "EnchantsmithUpgradeLevel": "Enchantsmith level",
    "OldBlacksmithUpgradeLevel": "Blacksmith level",
}
_ATTRIBUTE_ORDER = list(ATTRIBUTE_LABELS)
_WHOLE_NUMBER_ATTRIBUTES = set(ATTRIBUTE_LABELS) - {"XP"}

# The game's caps, from community datamines of build 1.1.1.0 (MetaBot, Maxroll; see
# mcd2-research/README.md). Anything above a cap is lost in the game, so Simple mode stops there.
# Emeralds stopped at 9,999 in that build; the game has let you hold 99,999 since.
STAT_CAPS = {
    "Emeralds": 99_999,
    "SpringStone": 100,
    "Level": 100,
    "EnchantmentPoints": 99,  # one per level-up
    "VillageMerchantUpgradeLevel": 3,
    "EnchantsmithUpgradeLevel": 3,
    "OldBlacksmithUpgradeLevel": 3,
}
STAT_MINIMUMS = {"Level": 1, "VillageMerchantUpgradeLevel": 1, "EnchantsmithUpgradeLevel": 1, "OldBlacksmithUpgradeLevel": 1}

# Item groups (SW.Item.<Group>.<Name>) that can't be added: they come from editions and
# pre-orders, drive quests, or are really currencies.
NOT_ADDABLE_GROUPS = {"Cosmetic", "QuestItem", "Currency"}
# An item ID. The game writes one with a small "sw" (sw.Item.Talisman.Llama, the Wonderful Wheat), so both count.
_ITEM_TAG = re.compile(r"(?:SW|sw)\.Item\.[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*")
_UNIQUE_SUFFIX = re.compile(r"_Unique\d*$")  # on a Unique's own ID: SW.Item.Sword_Unique1, SW.Item.MysticHelmet_Unique
NO_RARITY = "None"  # what a talisman or an enchantment book has: SW.Rarity.None
# Neither has a power. This is what the game saves in its place, for the one and for the other.
_NO_POWER = {
    "PlayerLevel": 1, "AreaThreatLevel": 1, "RecommendedThreatLevel": 1, "ThreatSliderOffset": 0,
    "ItemPowerMin": 1, "ItemPowerMax": 11, "RNGRoll": 0, "ItemPower": -1, "ItemPowerOriginal": 0,
}
# An item's effects are saved in batches, each of a kind:
_UPGRADABLE = "SW.Item.Effect.Upgradable"  # a talisman's own effect, which grows with its level
_REROLLABLE = "SW.Item.Effect.Rerollable"  # the effects the game rolls on a weapon, armor piece or artifact
_ENCHANTMENT = "SW.Item.Effect.Enchantment"  # the enchantment the Enchantsmith put on it
_STATIC = "SW.Item.Effect.Static"  # the effect a Unique comes with: one effect, saved ahead of the rolled ones
EFFECT_KINDS = ("Melee", "Ranged", "Armor", "Artifact")  # what the game rolls effects on
ENCHANTABLE_KINDS = ("Melee", "Ranged", "Armor")  # what the Enchantsmith enchants
TIERS = ("I", "II", "III")
# The pools the game rolls an item's effects from: its slot's, and one for each archetype it carries ("Ranger gear").
ANY_WEAPON, ANY_ARTIFACT, ALL_GEAR = "Any weapon", "Any artifact", "All gear"
# A Unique comes with an effect of its own, the one its card describes. The editor writes it exactly as a real
# save holds it (issue 20 showed 51 of them), so it can only give a Unique the one it has seen. For a Unique whose
# own effect it hasn't seen, it says this wherever it makes one (a player checked in the game: without it, the
# Unique is one in name only, issue 19).
NO_OWN_EFFECT = "The editor adds this Unique without its own effect: it hasn't seen how the game saves that one yet."
MAX_ITEM_XP = 10_000_000
# The town's three vendors, and the hint the game files in a hero's save the first time you open each one's
# window (CollectionsStats.ShownHints). The game's script cache spells all three; two have been seen in a save.
VENDORS = {
    "Village Merchant": "SW.UI.Onboarding.Panel.VillageMerchant.Overview",
    "Blacksmith": "SW.UI.Onboarding.Panel.Blacksmith.Overview",
    "Enchantsmith": "SW.UI.Onboarding.Panel.Enchantsmith.Overview",
}
# SW.Item.EnchantmentBook.<Name>. The Enchantsmith works from the books in the inventory: the game's own script
# names say so (GetAllOwnedEnchantmentBooks hands back inventory entries), and it was checked in the game. With 17
# books the editor had added, the game kept them all and the Enchantsmith offered their enchantments, though the
# game's own collections never listed one of them.
BOOK_KIND = "Enchantment Book"
_BOOK_GROUP = "EnchantmentBook"
ONE_OF_EACH = "A hero has one of each enchantment book"
# How a hero is saved, as (HardFormat, SoftVersion) from the save's SerializeMeta, for the game versions the
# editor has been checked against. A game update that changes the format is expected to change one of them.
TESTED_FORMATS = {("FCharacterSaveV1", 5)}

_RANGED = re.compile(r"bow|sling|blowgun|launcher", re.IGNORECASE)  # Longbow, Crossbow, ...
_ARMOR = re.compile(r"Helmet|Helm|Hood|Hat|Mask|Chest|Armor|Armour|Mail|Robe|Tunic|Vest|Leggings|Pants|Greaves|Boots|Shoes|Gauntlets|Gloves")


def vendors_text(hero: "Hero") -> str:
    """Which town vendors the hero has unlocked, as the game's own records show it, in a sentence or two."""
    opened = hero.vendors_opened()
    yes = [name for name, done in opened.items() if done]
    no = [name for name, done in opened.items() if not done]
    how = "The game notes the first time you open each one's window."
    if not no:
        return f"This hero has unlocked all three town vendors: the {', the '.join(yes[:-1])} and the {yes[-1]}."
    if not yes:
        return f"This hero hasn't opened a town vendor in the game yet. {how}"
    return f"Unlocked in the game: the {' and the '.join(yes)}. Not opened yet: the {' and the '.join(no)}. {how}"


def format_caution(hero: "Hero") -> str:
    """What to say before saving a hero whose save format the editor hasn't been checked against (a game
    update has most likely changed it). Empty when it has been."""
    if hero.format_is_tested:
        return ""
    name, version = hero.save_format
    return (
        f"This hero is saved in a format the editor hasn't been checked against ({name}, version {version}), most "
        "likely since a game update. The editor leaves everything in a save that it doesn't know as it is, and your "
        "saves are backed up first, but check the result in the game."
    )


def is_hero_document(document: Any) -> bool:
    meta = document.get("SerializeMeta") if isinstance(document, dict) else None
    return isinstance(meta, dict) and str(meta.get("HardFormat", "")).startswith("FCharacterSave")


def words(identifier: str) -> str:
    """'FireworkQuiver' -> 'Firework Quiver'."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", identifier)


def attribute_label(name: str) -> str:
    return ATTRIBUTE_LABELS.get(name, words(name))


def item_name(tag: str) -> str:
    return words(tag.rsplit(".", 1)[-1]) if tag else "(unknown item)"


def item_kind(tag: str) -> str:
    parts = tag.split(".")
    if tag.startswith(COSMETIC_PREFIX):
        return words(parts[3]) if len(parts) > 4 else "Cosmetic"
    if len(parts) > 3:
        return words(parts[2])
    if _RANGED.search(parts[-1]):
        return "Ranged"
    if _ARMOR.search(parts[-1]):
        return "Armor"
    return "Melee"


@dataclass(frozen=True)
class GameItem:
    """An item from the game's full item list (dungeons2_editor/data/items.json)."""

    name: str  # in-game name
    kind: str  # Melee, Ranged, Armor, Artifact or Talisman
    id: str  # save ID; a best guess unless confirmed
    confirmed: bool  # the ID has been seen in real saves
    unique: str | None = None  # name of the item at Unique rarity
    slot: str | None = None  # armor slot
    set: str | None = None  # armor set
    unique_effect: str | None = None  # what the Unique does
    effect: str | None = None  # what a talisman does at level 3
    name_from_id: bool = False  # the name is made from the ID; what the game calls it isn't known yet
    unique_id: str | None = None  # the Unique's own save ID, once it has been seen in a real save
    levels: tuple = ()  # a talisman's effect at each of its levels, once seen in a real save
    unique_own: "OwnEffect | None" = None  # the effect its Unique comes with, as a real save holds it
    tags: tuple[str, ...] = ()  # its archetypes (Fighter, Ranger...), which decide the effects the game rolls on it
    unique_tags: tuple[str, ...] = ()  # its Unique's, which aren't always the same
    element: str = ""  # an artifact's element, if it has one: Fire, Frost, Lightning, Poison or Soul


@dataclass(frozen=True)
class OwnEffect:
    """The effect a Unique comes with, as a real save holds it: the one effect in a batch of the kind
    SW.Item.Effect.Static. Its numbers follow no rule the editor can rely on (some are enchantments under
    another name), so each is taken from a save."""

    effect: str  # SW.Effect.Sidestep
    strength: Any  # the save's Intensity
    template: str  # SW.EffectTemplate.Sidestep.Unique
    seen: bool = True  # seen on this very Unique; if not, it's the one seen on a Unique that does the same thing
    like: str = ""  # that other Unique's name


@dataclass(frozen=True)
class Enchantment:
    """An enchantment (dungeons2_editor/data/enchantments.json)."""

    name: str
    slots: tuple[str, ...]  # Melee, Ranged, Armor (any piece) or Chestplate
    book: str  # where its book drops
    tier3: str  # what it does at tier III
    what: str = ""  # what it does, in a few words
    levels: str = ""  # its numbers at tiers I, II and III: "20% / 35% / 50% chance"


@dataclass(frozen=True)
class EffectChoice:
    """One tier of a gear effect or of an enchantment, as a save holds it, ready to put on an item."""

    effect: str  # SW.Effect.CriticalEdge, SW.Enchantment.Radiance
    template: str  # SW.EffectTemplate.CriticalEdge.II, SW.Enchantment.Radiance.I
    strength: Any  # the save's Intensity
    name: str  # what the game calls it, or a name made from its ID
    tier: str = ""  # I, II or III
    seen: bool = True  # this tier has been seen in a real save (else its number is from the game files' table)
    shown: str = ""  # the number the game shows for it: 20%
    maybe: str = ""  # what the game probably calls it, when the name is made from its ID
    rolls_on: str = ""  # the gear the game rolls it on
    slots: tuple[str, ...] = ()  # an enchantment: what it goes on (Melee, Ranged, Armor or Chestplate), when known
    what: str = ""  # what it does: an enchantment in a few words, a gear effect's tier in the game's own
    levels: str = ""  # an enchantment: its numbers at tiers I, II and III
    yours: bool = False  # not in the editor's list: found on an item in your saves

    @property
    def is_enchantment(self) -> bool:
        return self.effect.startswith(ENCHANTMENT_PREFIX)

    @property
    def title(self) -> str:
        """'Critical Edge II'."""
        return f"{self.name} {self.tier}".strip()

    @property
    def number(self) -> str:
        """'20%' when the game's number for it is known, else the strength as saved."""
        return self.shown or format_amount(self.strength)

    def fits(self, kind: str, piece: str | None = None) -> bool:
        """Whether an enchantment goes on an item of this kind (and armor piece). True when that isn't known."""
        if not self.slots:
            return True
        return kind in self.slots or (piece is not None and piece in self.slots)

    @property
    def pools(self) -> tuple[str, ...]:
        """The pools the game rolls a gear effect from: 'Any weapon', 'All gear', 'Ranger gear'. None when that
        isn't known."""
        return tuple(pool.strip() for pool in self.rolls_on.split(",") if pool.strip())

    def rolls_on_item(self, kind: str, tags: Iterable[str] = ()) -> bool:
        """Whether the game can roll this effect on an item of this kind that carries these archetypes: an item
        rolls from its slot's pool and from one pool per archetype. False when the effect's pools aren't known."""
        pools = self.pools
        return (
            ALL_GEAR in pools
            or (ANY_WEAPON in pools and kind in ("Melee", "Ranged"))
            or (ANY_ARTIFACT in pools and kind == "Artifact")
            or any(f"{tag} gear" in pools for tag in tags)
        )


@dataclass(frozen=True)
class EffectBook:
    """What the editor knows about effects (dungeons2_editor/data/effects.json)."""

    effects: tuple[EffectChoice, ...] = ()  # gear effects, a choice for each tier
    enchantments: tuple[EffectChoice, ...] = ()
    max_effects: int = 4  # the most effects the game gives an item
    enchant_points: Any = None  # rarity -> enchantment points in an enchantment at tiers I, II and III
    talisman_xp: tuple[int, ...] = ()  # XP a talisman needs for level 2, then for level 3

    def points_for(self, rarity: str, tier: str) -> int:
        """Enchantment points the game counts as put into an enchantment of this tier on an item of this rarity."""
        costs = (self.enchant_points or {}).get(rarity)
        return int(costs[TIERS.index(tier)]) if costs and tier in TIERS and TIERS.index(tier) < len(costs) else 0


def _load(path: Path, key: str) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get(key, []) if isinstance(data, dict) else data
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("name")]


@lru_cache(maxsize=1)
def game_items() -> tuple[GameItem, ...]:
    return tuple(
        GameItem(
            e["name"], e["kind"], e["id"], bool(e.get("confirmed")), e.get("unique"), e.get("slot"),
            e.get("set"), e.get("unique_effect"), e.get("effect"), bool(e.get("name_from_id")), e.get("unique_id"),
            tuple(e.get("levels") or ()), _own_effect_in(e.get("unique_own")),
            _words_in(e.get("tags")), _words_in(e.get("unique_tags")), str(e.get("element") or ""),
        )
        for e in _load(GAME_ITEMS_FILE, "items")
        if e.get("id") and e.get("kind")
    )


def _words_in(listed: Any) -> tuple[str, ...]:
    """A list of words from the item list, as a tuple; nothing for anything else."""
    return tuple(word for word in listed if isinstance(word, str)) if isinstance(listed, list) else ()


def _own_effect_in(listed: Any) -> OwnEffect | None:
    """An item list entry's ``unique_own``, when it's all there."""
    if not isinstance(listed, dict):
        return None
    effect, template, strength = listed.get("effect"), listed.get("template"), listed.get("strength")
    if not isinstance(effect, str) or not isinstance(template, str) or not _is_number(strength):
        return None
    return OwnEffect(effect, strength, template, bool(listed.get("seen", True)), str(listed.get("like") or ""))


@lru_cache(maxsize=1)
def enchantments() -> dict[str, Enchantment]:
    """Every enchantment by name."""
    return {
        e["name"]: Enchantment(
            e["name"], tuple(e.get("slots") or ()), e.get("book", ""), e.get("tier3", ""), e.get("what", ""), e.get("levels", "")
        )
        for e in _load(ENCHANTMENTS_FILE, "enchantments")
    }


ENCHANTMENT_PREFIX = "SW.Enchantment."


def _tier_of(template: str) -> str:
    """'II' for SW.EffectTemplate.CriticalEdge.II; '' when the template doesn't end in a tier."""
    last = template.rsplit(".", 1)[-1]
    return last if last in TIERS and "." in template else ""


def _base_of(template: str) -> str:
    """A template without its tier: SW.EffectTemplate.CriticalEdge."""
    return template.rsplit(".", 1)[0] if _tier_of(template) else template


@lru_cache(maxsize=1)
def effect_book() -> EffectBook:
    """The effects and enchantments the editor can write, as real saves hold them (made by
    tools/build_item_catalog.py). Empty when the file can't be read."""
    try:
        data = json.loads(EFFECTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return EffectBook()
    if not isinstance(data, dict):
        return EffectBook()
    by_name = enchantments()

    def choices(entries: Any, enchantment: bool) -> tuple[EffectChoice, ...]:
        made = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or not isinstance(entry.get("effect"), str) or not entry.get("name"):
                continue
            # An enchantment's template is its effect's name with the tier, unless a save spells it another way.
            base = (entry.get("template") or entry["effect"]) if enchantment else entry.get("template")
            known = by_name.get(entry["name"]) if enchantment else None
            for tier in entry.get("tiers") or []:
                if not isinstance(base, str) or not isinstance(tier, dict) or tier.get("tier") not in TIERS or not _is_number(tier.get("strength")):
                    continue
                made.append(
                    EffectChoice(
                        entry["effect"], f"{base}.{tier['tier']}", tier["strength"], entry["name"], tier["tier"], bool(tier.get("seen")),
                        str(tier.get("shown") or ""), str(entry.get("maybe") or ""), str(entry.get("rolls_on") or ""),
                        known.slots if known else (), known.what if known else str(tier.get("text") or ""), known.levels if known else "",
                    )
                )
        return tuple(made)

    costs = data.get("enchant_points")
    xp = data.get("talisman_xp")
    most = data.get("max_effects")
    return EffectBook(
        choices(data.get("effects"), False),
        choices(data.get("enchantments"), True),
        most if isinstance(most, int) and not isinstance(most, bool) and most > 0 else 4,
        costs if isinstance(costs, dict) else None,
        tuple(value for value in xp if _is_number(value)) if isinstance(xp, list) else (),
    )


def _named(tag: str, template: str) -> EffectChoice | None:
    """What the editor's list says about an effect on an item: the same effect and template if it has them, else
    another tier of the same effect, for its name."""
    book = effect_book()
    listed = book.enchantments if tag.startswith(ENCHANTMENT_PREFIX) else book.effects
    same = [choice for choice in listed if choice.effect == tag and _base_of(choice.template) == _base_of(template)]
    return next((choice for choice in same if choice.template == template), same[0] if same else None)


def _enchantment_info(tag: str) -> Enchantment | None:
    """What the game calls an enchantment and what it goes on, by way of its book: SW.Enchantment.PotionSharing
    comes from the book SW.Item.EnchantmentBook.PotionSharing, which the item list knows as Buddy Brew. None
    for anything else, and for an enchantment whose book hasn't been named."""
    if not tag.startswith(ENCHANTMENT_PREFIX):
        return None
    book = _game_items_by_id().get(f"{ITEM_PREFIX}{_BOOK_GROUP}.{tag[len(ENCHANTMENT_PREFIX):]}")
    return enchantments().get(book.name) if book is not None and not book.name_from_id else None


def book_enchantment(tag: str) -> Enchantment | None:
    """The enchantment a book is for: SW.Item.EnchantmentBook.PotionSharing is the book of Buddy Brew. None for
    anything else, and for a book the item list hasn't named."""
    known = game_item(tag)
    if known is None or known.kind != BOOK_KIND or known.name_from_id:
        return None
    return enchantments().get(known.name)


def book_text(tag: str) -> str:
    """What an enchantment book is for, in a sentence or two, for its card."""
    found = book_enchantment(tag)
    if found is None:
        return "An enchantment book. The editor doesn't know what the game calls its enchantment yet."
    what = found.what or found.tier3
    text = f"The book of an enchantment for {_slot_words(found.slots)}." if found.slots else "An enchantment book."
    if what:
        text += f" {what.rstrip('.')}" + (f": {found.levels} at tiers I, II and III." if found.levels else ".")
    return text


def effect_choices(heroes: Iterable["Hero"] = ()) -> tuple[list[EffectChoice], list[EffectChoice]]:
    """(gear effects, enchantments) the editor can put on an item: every tier in its own list, and any other it
    finds on an item in these saves, which it can copy exactly as the game saved it. A tier the list only has
    from the game files' table counts as seen once a save shows it, and the save's number wins."""
    book = effect_book()
    found: dict[tuple[str, str], EffectChoice] = {}
    kinds: dict[tuple[str, str], set[str]] = {}
    for hero in heroes:
        for item in hero.items():
            for effect in item.effects:
                if effect.group not in (_REROLLABLE, _ENCHANTMENT) or not effect.template or not _is_number(effect.strength):
                    continue
                if (effect.group == _ENCHANTMENT) != effect.tag.startswith(ENCHANTMENT_PREFIX):
                    continue  # not laid out the way the editor knows
                key = (effect.tag, effect.template)
                kinds.setdefault(key, set()).add(item.kind)
                known = _named(effect.tag, effect.template)
                listed = known is not None and known.template == effect.template
                if listed and known.seen:
                    continue  # the list has this tier from a real save already; a number typed in by hand doesn't replace it
                found.setdefault(
                    key,
                    replace(known, strength=effect.strength, seen=True, shown=known.shown if known.strength == effect.strength else "")
                    if listed
                    else effect.as_choice(),
                )
    lists: tuple[list[EffectChoice], list[EffectChoice]] = ([], [])
    for enchantment, listed in ((False, book.effects), (True, book.enchantments)):
        made = [found.pop((choice.effect, choice.template), choice) for choice in listed]
        for key, choice in list(found.items()):
            if choice.is_enchantment == enchantment:
                if enchantment and not choice.slots:  # all that's known is where it was found
                    choice = replace(choice, slots=tuple(sorted(kinds[key] & set(ENCHANTABLE_KINDS))))
                made.append(choice)
                del found[key]
        order = {tier: position for position, tier in enumerate(TIERS)}
        lists[enchantment].extend(sorted(made, key=lambda choice: (choice.name.lower(), order.get(choice.tier, len(order)), choice.template)))
    return lists


def _effect_entry(choice: EffectChoice, points: int = 0) -> dict:
    """An effect the way a save holds one, in the game's own order of keys."""
    return {
        "TypeTag": choice.effect,
        "Intensity": choice.strength,
        "Quality": 0,
        "EnchantmentPointsInvested": int(points),
        "GeneratorData": {"GeneratorParentTemplate": choice.template, "Locked": False},
    }


def _effect_key(entry: Any) -> tuple[Any, Any]:
    generator = entry.get("GeneratorData") if isinstance(entry, dict) else None
    return (entry.get("TypeTag") if isinstance(entry, dict) else None, generator.get("GeneratorParentTemplate") if isinstance(generator, dict) else None)


@lru_cache(maxsize=1)
def _game_items_by_id() -> dict[str, GameItem]:
    found: dict[str, GameItem] = {}
    for game_item in game_items():
        found.setdefault(game_item.id, game_item)
    return found


@lru_cache(maxsize=1)
def _uniques_by_id() -> dict[str, GameItem]:
    return {game_item.unique_id: game_item for game_item in game_items() if game_item.unique_id}


def _known(tag: str) -> tuple[GameItem | None, bool]:
    """The game's item for an ID, and whether the ID is that item's Unique version. A Unique has an ID of its
    own: its base item's with _Unique1 (weapons) or _Unique (armor) on the end, so SW.Item.Sword_Unique1 is the
    Burning Blade, the Unique Sword."""
    found = _game_items_by_id().get(tag)
    if found is not None:
        return found, False
    found = _uniques_by_id().get(tag)
    if found is None and _UNIQUE_SUFFIX.search(tag):
        found = _game_items_by_id().get(_UNIQUE_SUFFIX.sub("", tag))
    return (found, True) if found is not None and found.unique else (None, False)


def game_item(tag: str) -> GameItem | None:
    """What the game's item list says about an item ID, if it lists it. A Unique's own ID gives its base item."""
    return _known(tag)[0]


def is_unique_version(tag: str) -> bool:
    """Whether the ID is a Unique's own (SW.Item.Sword_Unique1), not a base item's."""
    return _known(tag)[1]


def archetypes(tag: str) -> tuple[str, ...]:
    """The archetypes the game tags an item with (Fighter, Ranger...), by its ID. A Unique has its own, which
    aren't always its base item's. None for an item the list doesn't have, and for the few the game gives none."""
    known, unique = _known(tag)
    if known is None:
        return ()
    return known.unique_tags if unique else known.tags


def element(tag: str) -> str:
    """An artifact's element (Fire, Frost, Lightning, Poison or Soul), by its ID. '' for anything without one."""
    known = _known(tag)[0]
    return known.element if known is not None else ""


def the(name: str, start: bool = False) -> str:
    """'the Sword', and 'The Burning Blade' as it is: a name that brings its own article doesn't get a second.
    With ``start`` it begins a sentence."""
    if name.startswith("The "):
        return name
    return f"{'The' if start else 'the'} {name}"


def own_effect(tag: str) -> OwnEffect | None:
    """The effect the Unique with this ID comes with, when the editor's list has how a save holds it. None for
    any other ID, and for a Unique whose own effect hasn't been seen."""
    known, unique = _known(tag)
    return known.unique_own if known is not None and unique else None


def _own_batch(own: OwnEffect) -> dict:
    """A Unique's own effect the way a save holds it: a batch of its own kind with the one effect, in the game's
    order of keys."""
    return {
        "TypeTag": _STATIC,
        "EffectsInThisBatch": [
            {
                "TypeTag": own.effect,
                "Intensity": own.strength,
                "Quality": 0,
                "EnchantmentPointsInvested": 0,
                "GeneratorData": {"GeneratorParentTemplate": own.template, "Locked": False},
            }
        ],
    }


def base_tag(tag: str) -> str:
    """The base item's ID for a Unique's own ID; any other ID as it is."""
    known, unique = _known(tag)
    return known.id if known is not None and unique else tag


def unique_tag(tag: str, seen: Iterable[str] = ()) -> str | None:
    """The ID of an item's Unique version, when that ID is known to be real: the game's item list has it, or it
    is in ``seen`` (IDs from real saves). None for an item with no Unique, or one whose Unique hasn't been seen:
    its ID could be guessed, but the game removes items whose ID it doesn't know."""
    known, unique = _known(tag)
    if known is None or not known.unique:
        return None
    if unique:
        return tag
    if known.unique_id:
        return known.unique_id
    return next((other for other in sorted(seen) if _known(other) == (known, True)), None)


_LOCAL_NAMES: dict[str, str] = {}  # item ID -> the name you gave it (my_items.py)


def use_local_names(names: dict[str, str]) -> None:
    """Use the names you gave items the editor doesn't know, instead of names made from their IDs."""
    _LOCAL_NAMES.clear()
    _LOCAL_NAMES.update(names)


def local_name(tag: str) -> str | None:
    return _LOCAL_NAMES.get(tag)


def name_is_known(tag: str) -> bool:
    """Whether the editor knows what the game calls this item (from the game's item list, or from you)."""
    known = game_item(tag)
    return tag in _LOCAL_NAMES or (known is not None and not known.name_from_id)


def display_name(tag: str) -> str:
    """The in-game name: 'SW.Item.MysticHelmet' is the Mystic Circlet, and its Unique's own ID,
    'SW.Item.MysticHelmet_Unique', is the Oracle Crown. (A base item's ID is the base item at any rarity.)"""
    known, unique = _known(tag)
    if known is None or known.name_from_id:
        mine = _LOCAL_NAMES.get(tag)
        if mine:
            return mine
    if known is None:
        return item_name(tag)
    return known.unique if unique and known.unique else known.name


def talisman_levels(tag: str) -> list[dict]:
    """A talisman's levels as the game saves them (ItemProgression.ItemLevels): its effect at each one, or for
    a companion's talisman, which has no effect of its own, the tag each level carries. Empty when the item
    list doesn't know what the talisman does."""
    known = game_item(tag)
    return [
        {
            "LevelEffects": [
                {
                    "TypeTag": level["effect"],
                    "Intensity": level["intensity"],
                    "Quality": 0,
                    "EnchantmentPointsInvested": 0,
                    "GeneratorData": {"GeneratorParentTemplate": level["template"], "Locked": False},
                }
            ]
            if "effect" in level
            else [],
            "LevelTags": list(level.get("tags") or []),
        }
        for level in (known.levels if known is not None else ())
        if isinstance(level, dict)
    ]


def _item_levels(entry: dict) -> list:
    """The levels saved with an inventory entry (ItemProgression.ItemLevels). A talisman the game handed over
    has them; one an older version of the editor added doesn't."""
    levels = ((entry.get("ItemData") or {}).get("ItemProgression") or {}).get("ItemLevels")
    return levels if isinstance(levels, list) else []


def item_group(tag: str) -> str:
    """'Gear' for weapons and armor (SW.Item.<Name>), else the group named in the tag (Artifact, Talisman, ...)."""
    parts = tag.split(".")
    return parts[2] if len(parts) > 3 else "Gear"


def tag_kind(tag: str) -> str:
    """Melee, Ranged, Armor, Artifact, Talisman, ...: from the game's item list, else from the ID."""
    known = game_item(tag)
    return known.kind if known else item_kind(tag)


_PIECE_WORDS = {"Helmet": "Helmet", "Chest": "Chestplate", "Chestplate": "Chestplate", "Leggings": "Leggings", "Boots": "Boots"}


def armor_piece(tag: str) -> str | None:
    """Helmet, Chestplate, Leggings or Boots for armor, else None."""
    known = game_item(tag)
    if known is not None:
        return known.slot if known.kind == "Armor" else None
    match = re.search(r"(Helmet|Chestplate|Chest|Leggings|Boots)$", tag)
    return _PIECE_WORDS[match.group(1)] if match and item_kind(tag) == "Armor" else None


@dataclass(frozen=True)
class GearSlot:
    """A place on the hero that gear goes."""

    tag: str  # the save's name for it, as an inventory entry's EquippedSlot
    kind: str  # Melee, Ranged, Armor, Artifact or Talisman
    label: str
    piece: str | None = None  # the armor piece that goes here
    level: int = 1  # the hero level it opens at
    confirmed: bool = False  # the name has been seen in a real save


# The hero's 12 gear slots, named as the game's own script cache lists them
# (Content/Dungeons/Script/PrecompiledScript.Cache spells SW.ItemSlot.Equipment.Armor.Helmet as
# SW_ItemSlot_Equipment_Armor_Helmet, the way it spells the weapon and merchant slots seen in saves).
# Artifact slots 2 and 3 open at levels 5 and 10 (community datamines; mcd2-research/README.md).
GEAR_SLOTS = (
    GearSlot("SW.ItemSlot.Equipment.MeleeWeapon", "Melee", "Melee weapon", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.RangedWeapon", "Ranged", "Ranged weapon", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Armor.Helmet", "Armor", "Helmet", piece="Helmet", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Armor.Chest", "Armor", "Chestplate", piece="Chestplate", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Armor.Leggings", "Armor", "Leggings", piece="Leggings", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Armor.Boots", "Armor", "Boots", piece="Boots", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Artifact.Slot1", "Artifact", "Artifact 1", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Artifact.Slot2", "Artifact", "Artifact 2", level=5, confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Artifact.Slot3", "Artifact", "Artifact 3", level=10, confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Talisman.Slot1", "Talisman", "Talisman 1", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Talisman.Slot2", "Talisman", "Talisman 2", confirmed=True),
    GearSlot("SW.ItemSlot.Equipment.Talisman.Slot3", "Talisman", "Talisman 3", confirmed=True),
)


def _slot_number(tag: str) -> int | None:
    match = re.search(r"(\d+)$", tag)
    return int(match.group(1)) if match else None


def slots_for(kind: str, piece: str | None, slots: list[GearSlot] | tuple[GearSlot, ...]) -> list[GearSlot]:
    """The slots an item of this kind (and armor piece) goes in."""
    return [slot for slot in slots if slot.kind == kind and (slot.piece is None or slot.piece == piece)]


def _slot_words(slots: Sequence[str]) -> str:
    """'melee and ranged weapons', 'armor', 'chestplates': what an enchantment goes on."""
    names = {"Melee": "melee weapons", "Ranged": "ranged weapons", "Armor": "armor", "Chestplate": "chestplates"}
    if set(slots) >= {"Melee", "Ranged"}:
        slots = ["weapons"] + [slot for slot in slots if slot not in ("Melee", "Ranged")]
    listed = [names.get(slot, slot.lower()) for slot in slots]
    return " and ".join(listed) if len(listed) < 3 else ", ".join(listed[:-1]) + " and " + listed[-1]


def format_amount(value: Any) -> str:
    """5000 -> '5,000'; 845.5 -> '845.5'."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int) or value.is_integer():
        return f"{int(value):,}"
    return repr(value)


def _check_addable_tag(tag: str) -> None:
    if not _ITEM_TAG.fullmatch(tag):
        raise ValueError(f"{tag!r} isn't an item ID. Item IDs look like SW.Item.Sword.")
    if item_group(tag) in NOT_ADDABLE_GROUPS:
        raise ValueError(f"{item_name(tag)} is a {words(item_group(tag)).lower()} item, and those can't be added.")


def _check_number(value: Any, low: float, high: float, what: str, whole: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{what} must be a number.")
    if whole and not float(value).is_integer():
        raise ValueError(f"{what} must be a whole number.")
    if not low <= value <= high:
        raise ValueError(f"{what} must be between {low:,} and {high:,}.")


@dataclass(frozen=True)
class Effect:
    """One effect on an item, as a save holds it."""

    tag: str  # SW.Effect.HealthBoost
    strength: Any  # the save's Intensity; what the number means depends on the effect (1.2 is +20% max health)
    quality: Any = 0
    points: Any = 0  # enchantment points put into it
    locked: bool = False
    group: str = ""  # the kind of batch it's saved in: SW.Item.Effect.Upgradable for a talisman's own effect
    template: str = ""  # SW.EffectTemplate.HealthBoost.I: which tier of which effect the game made it from

    @property
    def is_rolled(self) -> bool:
        """One of the effects the game rolls on a weapon, armor piece or artifact."""
        return self.group == _REROLLABLE

    @property
    def is_enchantment(self) -> bool:
        return self.group == _ENCHANTMENT

    @property
    def is_own(self) -> bool:
        """The effect a Unique comes with."""
        return self.group == _STATIC

    @property
    def tier(self) -> str:
        """I, II or III for a rolled effect or an enchantment; a talisman's effect follows its level instead."""
        return _tier_of(self.template) if self.group in (_REROLLABLE, _ENCHANTMENT) else ""

    @property
    def name(self) -> str:
        """What the game calls it when the editor knows ('Acrobat' for SW.Effect.RollCooldown from the Acrobat
        template), else a name made from its ID ('Health Boost' for SW.Effect.HealthBoost)."""
        known = _named(self.tag, self.template) if self.group in (_REROLLABLE, _ENCHANTMENT) else None
        if known is not None:
            return known.name
        if self.is_own:
            return self._own_name()
        book = _enchantment_info(self.tag) if self.is_enchantment else None
        # A rolled effect is named after its template, as the game names it: Acrobat, not Roll Cooldown.
        named = _base_of(self.template) if self.is_rolled and self.template else self.tag
        return book.name if book is not None else words(named.rsplit(".", 1)[-1])

    def _own_name(self) -> str:
        """A Unique's own effect by the name the game gives the same effect when it rolls it ('Evasion' for
        SW.Effect.Sidestep, from the template SW.EffectTemplate.Sidestep.Unique), else by its ID."""
        base = self.template.rsplit(".", 1)[0] if self.template.endswith(".Unique") else self.template
        tag = self.tag.rsplit(".", 1)[0] if self.tag.endswith(".Unique") else self.tag
        if tag.startswith(ENCHANTMENT_PREFIX):
            book = _enchantment_info(tag)
            return book.name if book is not None else words(tag.rsplit(".", 1)[-1])
        rolled = next((choice for choice in effect_book().effects if choice.effect == tag and _base_of(choice.template) == base), None)
        return rolled.name if rolled is not None else words((base or tag).rsplit(".", 1)[-1])

    @property
    def title(self) -> str:
        """'Critical Edge II'."""
        return f"{self.name} {self.tier}".strip()

    def as_choice(self) -> EffectChoice:
        """This effect as something to put on an item again, exactly as it's saved here: the editor's own entry
        for it when it has one, else a copy."""
        known = _named(self.tag, self.template)
        if known is not None and known.template == self.template and known.strength == self.strength:
            return known if known.seen else replace(known, seen=True)  # it's in a save: that's seen
        like = known or _enchantment_info(self.tag)  # another tier of it, or what its book says
        return EffectChoice(
            self.tag, self.template, self.strength, self.name, self.tier, maybe=known.maybe if known else "",
            rolls_on=known.rolls_on if known else "", slots=like.slots if like else (), what=like.what if like else "",
            levels=like.levels if like else "", yours=True,
        )

    @property
    def text(self) -> str:
        """'Health Boost 1.2' or 'Critical Edge II 20%', with its quality and enchantment points when it has
        any. An enchantment's strength isn't a number the game shows, so it's left out."""
        if self.is_own:  # what it does, with its number, is the Unique's own description
            return f"Its own: {self.name}"
        known = _named(self.tag, self.template) if self.tier else None
        if known is not None and known.template == self.template and known.strength == self.strength and known.shown:
            number = known.shown
        else:
            number = format_amount(self.strength) if _is_number(self.strength) else ""
        parts = [f"{self.title} {number}" if number and not self.is_enchantment else self.title]
        if _is_number(self.quality) and self.quality:
            parts.append(f"quality {format_amount(self.quality)}")
        if _is_number(self.points) and self.points:
            parts.append(f"{format_amount(self.points)} enchantment point{'' if self.points == 1 else 's'}")
        if self.locked:
            parts.append("locked")
        return ", ".join(parts)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass
class Item:
    index: int
    entry: dict

    @property
    def data(self) -> dict:
        return self.entry.get("ItemData") or {}

    @property
    def tag(self) -> str:
        return str(self.data.get("TypeTag", ""))

    @property
    def name(self) -> str:
        return display_name(self.tag)

    @property
    def kind(self) -> str:
        return tag_kind(self.tag)

    @property
    def piece(self) -> str | None:
        return armor_piece(self.tag)

    @property
    def is_cosmetic(self) -> bool:
        return self.tag.startswith(COSMETIC_PREFIX)

    @property
    def is_talisman(self) -> bool:
        """A talisman has no rarity or power (the game saves SW.Rarity.None and power -1): it levels up instead."""
        return self.kind == "Talisman"

    @property
    def is_book(self) -> bool:
        """An enchantment book: the Enchantsmith can put its enchantment on gear while it's in the inventory."""
        return self.kind == BOOK_KIND

    @property
    def ungraded(self) -> bool:
        """A talisman or an enchantment book: neither has a rarity or a power (the game saves SW.Rarity.None
        and power -1 for both)."""
        return self.is_talisman or self.is_book

    @property
    def rarity(self) -> str:
        tag = str(self.data.get("RarityTag", ""))
        return tag[len(RARITY_PREFIX):] if tag.startswith(RARITY_PREFIX) else tag

    @property
    def rarity_rank(self) -> int:
        return RARITIES.index(self.rarity) if self.rarity in RARITIES else -1

    @property
    def power_values(self) -> dict:
        return (self.data.get("GeneratorData") or {}).get("PowerGeneratorValues") or {}

    @property
    def power(self) -> float | None:
        return self.power_values.get("ItemPower")

    @property
    def progression(self) -> dict:
        return self.data.get("ItemProgression") or {}

    @property
    def level(self) -> int:
        return self.progression.get("CurrentLevel", 0)

    @property
    def xp(self) -> float:
        return self.progression.get("CurrentXP", 0)

    @property
    def effects(self) -> list[Effect]:
        """The item's effects, in the save's order. A save keeps them in batches (a talisman's own effect is
        one batch, of the kind SW.Item.Effect.Upgradable); anything laid out another way is left out."""
        found = []
        for batch in self.data.get("Effects") or []:
            listed = batch.get("EffectsInThisBatch") if isinstance(batch, dict) else None
            for effect in listed if isinstance(listed, list) else []:
                if not isinstance(effect, dict) or not isinstance(effect.get("TypeTag"), str):
                    continue
                generator = effect.get("GeneratorData")
                template = generator.get("GeneratorParentTemplate") if isinstance(generator, dict) else None
                found.append(
                    Effect(
                        effect["TypeTag"],
                        effect.get("Intensity"),
                        effect.get("Quality", 0),
                        effect.get("EnchantmentPointsInvested", 0),
                        bool(generator.get("Locked")) if isinstance(generator, dict) else False,
                        str(batch.get("TypeTag", "")),
                        template if isinstance(template, str) else "",
                    )
                )
        return found

    @property
    def rolled_effects(self) -> list[Effect]:
        """The effects the game rolled for it (or the editor gave it in their place)."""
        return [effect for effect in self.effects if effect.is_rolled]

    @property
    def enchantment(self) -> Effect | None:
        return next((effect for effect in self.effects if effect.is_enchantment), None)

    @property
    def own_effects(self) -> list[Effect]:
        """Effects saved any other way, such as the one a Unique comes with. The editor leaves these alone."""
        return [effect for effect in self.effects if not effect.is_rolled and not effect.is_enchantment]

    @property
    def own_effect_missing(self) -> bool:
        """Whether this is a Unique without the effect of its own, the one its card describes. The game gives
        every Unique one, saved apart from the effects it rolls; a Unique made by a version of the editor that
        couldn't write it, or one whose own effect the editor hasn't seen, is without."""
        return is_unique_version(self.tag) and not self.own_effects

    @property
    def can_get_own_effect(self) -> bool:
        """Whether the editor can give this Unique the effect of its own that it's missing."""
        return self.own_effect_missing and own_effect(self.tag) is not None

    @property
    def own_effect_note(self) -> str:
        """What to say about a Unique that is without its own effect; nothing for any other item."""
        if not self.own_effect_missing:
            return ""
        return "Without its own effect." if self.can_get_own_effect else "Without its own effect: the editor can't add that one yet."

    @property
    def can_have_effects(self) -> bool:
        return not self.is_cosmetic and self.kind in EFFECT_KINDS

    @property
    def archetypes(self) -> tuple[str, ...]:
        """Its archetypes (Fighter, Ranger...): with its kind, they decide which effects the game rolls on it."""
        return archetypes(self.tag)

    @property
    def element(self) -> str:
        """An artifact's element, if it has one."""
        return element(self.tag)

    @property
    def can_be_enchanted(self) -> bool:
        return not self.is_cosmetic and self.kind in ENCHANTABLE_KINDS

    @property
    def level_effects(self) -> list[list]:
        """A talisman's effect at each of its levels, as the item itself carries them (ItemLevels). Empty for
        anything else, and for a talisman that levels up another way (a companion's has tags, not effects)."""
        levels = self.progression.get("ItemLevels")
        if not self.is_talisman or not isinstance(levels, list) or not levels:
            return []
        effects = [level.get("LevelEffects") if isinstance(level, dict) else None for level in levels]
        return effects if all(isinstance(listed, list) and listed for listed in effects) else []

    @property
    def can_be_leveled(self) -> bool:
        """Whether the editor can put this talisman at another level itself: it has its levels' effects with it,
        and its own effect is saved the way the game saves a talisman's."""
        own = [batch for batch in self.data.get("Effects") or [] if isinstance(batch, dict) and batch.get("TypeTag") == _UPGRADABLE]
        return len(self.level_effects) > 1 and len(own) == 1 and isinstance(self.level, int)

    @property
    def next_level_xp(self) -> int | None:
        """XP a talisman needs for its next level, counted from the level before. None at the last level, for
        anything else, or when the editor doesn't know."""
        needed = effect_book().talisman_xp
        levels = self.progression.get("ItemLevels")
        if not self.is_talisman or not isinstance(levels, list) or not isinstance(self.level, int):
            return None  # one with no levels saved has nothing to level into
        return int(needed[self.level]) if 0 <= self.level < min(len(needed), len(levels) - 1) else None

    def effect_lines(self) -> list[str]:
        """What the item's effects are, a line each. A talisman also says which level it's at and how
        strong its effect gets at the levels to come."""
        lines = [f"Enchanted: {effect.text}" if effect.is_enchantment else effect.text for effect in self.effects]
        levels = self.progression.get("ItemLevels")
        if self.is_talisman and isinstance(levels, list) and levels and isinstance(self.level, int) and 0 <= self.level < len(levels):
            needed = self.next_level_xp
            # Past the first level, whether the XP saved counts from nothing or from the last level-up hasn't been seen.
            progress = f" ({format_amount(self.xp)} of {format_amount(needed)} XP)" if needed is not None and self.level == 0 and _is_number(self.xp) else ""
            line = f"Level {self.level + 1} of {len(levels)}{progress}."
            later = []
            for level in levels[self.level + 1:]:
                listed = level.get("LevelEffects") if isinstance(level, dict) else None
                strength = listed[0].get("Intensity") if isinstance(listed, list) and len(listed) == 1 and isinstance(listed[0], dict) else None
                later.append(format_amount(strength) if _is_number(strength) else None)
            if later and all(later):
                line += f" At the next level{'' if len(later) == 1 else 's'}: {', then '.join(later)}."
            lines.append(line)
        return lines

    @property
    def count(self) -> int:
        return self.entry.get("StackCount", 1)

    @property
    def picked_up(self) -> int:
        return self.data.get("PickupTimestamp", 0)

    @property
    def equipped_slot(self) -> str | None:
        slot = self.entry.get("EquippedSlot")
        return None if slot in (None, "", "None") else str(slot)

    @property
    def stock_slot(self) -> str | None:
        slot = self.data.get("TargetSlotOverride")
        return None if slot in (None, "", "None") else str(slot)

    @property
    def where(self) -> str:
        if self.equipped_slot:
            known = next((slot for slot in GEAR_SLOTS if slot.tag == self.equipped_slot), None)
            if known is not None:
                return f"Equipped ({known.label.lower()})"
            parts = self.equipped_slot.split(".")
            slot = re.fullmatch(r"Slot(\d+)", parts[-1])
            place = f"{parts[-2]} slot {slot.group(1)}" if slot and len(parts) > 1 else words(parts[-1])
            return f"Equipped ({place.lower()})"
        if self.stock_slot:
            return "Merchant stock" if "Merchant" in self.stock_slot else words(self.stock_slot.rsplit(".", 1)[-1])
        return "Inventory"


# Sort choices for the item list: label -> (key, highest first?)
ITEM_SORTS = {
    "Most powerful": (lambda item: item.power if item.power is not None else -math.inf, True),
    "Highest item level": (lambda item: item.level, True),
    "Most item XP": (lambda item: item.xp, True),
    "Rarest": (lambda item: item.rarity_rank, True),
    "Most effects": (lambda item: len(item.effects), True),
    "Newest": (lambda item: item.picked_up, True),
    "Name": (lambda item: item.name.lower(), False),
    "Kind": (lambda item: (item.kind, item.name.lower()), False),
    "Where": (lambda item: (item.where, item.name.lower()), False),
    "Save order": (lambda item: item.index, False),
}


def sort_items(items: list[Item], sort: str) -> list[Item]:
    key, highest_first = ITEM_SORTS[sort]
    return sorted(items, key=key, reverse=highest_first)


class Hero:
    """Reads and edits one hero save document in place."""

    def __init__(self, document: dict):
        if not is_hero_document(document):
            raise ValueError("not a hero save")
        self.document = document
        body_key = str(document["SerializeMeta"].get("HardFormat", ""))[1:]  # FCharacterSaveV1 -> CharacterSaveV1
        if body_key not in document:
            body_key = next((key for key in document if key != "SerializeMeta"), "")
        self.body: dict = document.get(body_key) or {}

    # ------------------------------------------------------------ summary

    @property
    def metadata(self) -> dict:
        return self.body.get("MetaData") or {}

    @property
    def character_id(self) -> str:
        return str(self.metadata.get("CharacterId", ""))

    @property
    def is_online(self) -> bool:
        return bool(self.metadata.get("IsOnline"))

    @property
    def level(self) -> Any:
        return self.metadata.get("Level")

    @property
    def power_level(self) -> Any:
        return self.metadata.get("PowerLevel")

    @property
    def save_format(self) -> tuple[str, Any]:
        """(HardFormat, SoftVersion): how the game says this hero is saved."""
        meta = self.document.get("SerializeMeta") or {}
        return str(meta.get("HardFormat", "")), meta.get("SoftVersion")

    @property
    def format_is_tested(self) -> bool:
        """Whether the editor has been checked against this save format (see TESTED_FORMATS)."""
        return self.save_format in TESTED_FORMATS

    @property
    def skin(self) -> str:
        tag = str(((self.body.get("Cosmetics") or {}).get("Cosmetics") or {}).get("SW.Skin", {}).get("TypeTag", ""))
        return words(tag.rsplit(".", 1)[-1]) if tag else ""

    # --------------------------------------------------------- attributes

    def attributes(self) -> list[dict]:
        """The hero's stats (emeralds, level, XP, ...), in a friendly order."""
        found = [a for a in (self.body.get("Ability") or {}).get("Attributes") or [] if isinstance(a, dict) and "AttributeName" in a]
        order = {name: position for position, name in enumerate(_ATTRIBUTE_ORDER)}
        return sorted(found, key=lambda a: order.get(a["AttributeName"], len(order)))

    def attribute(self, name: str) -> Any:
        return next((a.get("CurrentValue") for a in self.attributes() if a["AttributeName"] == name), None)

    def set_attributes(self, values: dict[str, int | float], game_caps: bool = False) -> None:
        """Change several stats at once. Nothing changes unless every value is valid.

        With ``game_caps`` a value above the game's own cap (STAT_CAPS) is refused too.
        """
        by_name = {a["AttributeName"]: a for a in self.attributes()}
        for name, value in values.items():
            if name not in by_name:
                raise KeyError(name)
            high = STAT_CAPS.get(name, MAX_STAT) if game_caps else MAX_STAT
            _check_number(value, STAT_MINIMUMS.get(name, 0), high, attribute_label(name), whole=name in _WHOLE_NUMBER_ATTRIBUTES)
        for name, value in values.items():
            by_name[name]["CurrentValue"] = value
            if name == "Level" and "Level" in self.metadata:
                self.metadata["Level"] = int(value)

    # -------------------------------------------------------------- items

    def _entries(self) -> list:
        return (self.body.get("Inventory") or {}).get("Entries") or []

    def items(self) -> list[Item]:
        return [Item(index, entry) for index, entry in enumerate(self._entries()) if isinstance(entry, dict)]

    def item(self, index: int) -> Item:
        return Item(index, self._entries()[index])

    def _gear(self, index: int) -> Item:
        item = self.item(index)
        if item.is_cosmetic:
            raise ValueError("Cosmetics come from your game edition and can't be edited here.")
        return item

    def update_item(
        self,
        index: int,
        *,
        tag: str | None = None,
        rarity: str | None = None,
        power: int | None = None,
        count: int | None = None,
    ) -> None:
        """Change an item. Nothing changes unless every given value is valid.

        Setting the power also sets the range it was rolled from, so the game
        can't re-roll it to something else. A Unique has an ID of its own, so
        making an item Unique gives it that ID when it's known to be real, and
        taking an item's Unique rarity away gives it back its base item's ID.
        A ``tag`` that's given is otherwise kept exactly. A talisman has no rarity
        or power to change, and an item changed into one is laid out as one. An
        enchantment book has nothing to change at all, and nothing is changed into
        one: a book is added (``add_item``) or deleted. An
        item that becomes another item is marked as new, the way the game marks
        one you haven't looked at: until the game has shown it to you, nothing
        says the game knows its ID (see ``item_types_from_the_game``).
        """
        item = self._gear(index)
        if item.is_talisman:
            if (rarity is not None and rarity != item.rarity) or (power is not None and power != item.power):
                raise ValueError(f"The {item.name} is a talisman: it has no rarity or power, and levels up from the XP you earn.")
            rarity = power = None  # what it has already
        if item.is_book:
            if tag is not None and tag.strip() != item.tag:
                raise ValueError(f"The {item.name} book can't be changed into another item. Delete it, and add the one you want.")
            if (rarity is not None and rarity != item.rarity) or (power is not None and power != item.power):
                raise ValueError(f"The {item.name} is an enchantment book: it has no rarity or power.")
            if count is not None and count != item.count:
                raise ValueError(f"{ONE_OF_EACH}: the count stays as it is.")
            return
        if tag is not None:
            tag = tag.strip()
            if tag != item.tag:
                _check_addable_tag(tag)
                if tag_kind(tag) == BOOK_KIND:
                    raise ValueError(f"An item can't be changed into an enchantment book. Add the {display_name(tag)} book with Add items.")
                if item.equipped_slot:
                    raise ValueError(f"Unequip the {item.name} before changing what it is.")
                if item.stock_slot:
                    raise ValueError(f"The {item.name} is in the Village Merchant's stock. Make a copy, and change the copy.")
        if rarity is not None and rarity != item.rarity and rarity not in RARITIES:
            raise ValueError(f"Rarity must be one of {', '.join(RARITIES)}.")
        if power is not None:
            _check_number(power, 0, MAX_ITEM_POWER, "Power", whole=True)
            if "ItemPower" not in item.power_values:
                raise ValueError(f"The {item.name} has no power value.")
        if count is not None:
            _check_number(count, 1, MAX_STACK, "Count", whole=True)

        wanted = item.tag if tag is None else tag
        if rarity == "Unique":
            wanted = unique_tag(wanted, self.item_types_from_the_game()) or wanted
        elif rarity is not None and tag is None:
            wanted = base_tag(wanted)
        if wanted != item.tag:
            levels = self._talisman_levels(wanted) if tag_kind(wanted) == "Talisman" else None
            item.data["TypeTag"] = wanted
            self._mark_unseen(item.data)
            if levels is not None:
                self._as_talisman(item.data, levels)
                rarity = power = None
            else:
                self._set_own_effect(item.data)  # a Unique's own effect goes with what the item is
        if rarity is not None and rarity != item.rarity:
            item.data["RarityTag"] = RARITY_PREFIX + rarity
        if power is not None and power != item.power:
            values = item.power_values
            for key in ("ItemPower", "ItemPowerOriginal", "ItemPowerMin", "ItemPowerMax"):
                if key in values:
                    values[key] = int(power)
        if count is not None and count != item.count:
            item.entry["StackCount"] = int(count)

    @staticmethod
    def _mark_unseen(data: dict) -> None:
        """Mark an item as one you haven't looked at, the way the game marks a new one. Until the game has
        shown it to you, what the editor wrote on it isn't the game's word for anything."""
        marks = data.get("DynamicPropertyTags")
        if isinstance(marks, list) and UNSEEN_TAG not in marks:
            marks.append(UNSEEN_TAG)

    @staticmethod
    def _set_own_effect(data: dict) -> bool:
        """Make an item's own effect the one that goes with its ID: a Unique gets the effect it comes with, when
        the editor's list has it, ahead of its other effects, where the game puts it; anything else has none.
        Whether that changed anything."""
        batches = data.get("Effects")
        if not isinstance(batches, list):
            return False
        own = own_effect(str(data.get("TypeTag", "")))
        wanted = [_own_batch(own)] if own is not None else []
        current = [batch for batch in batches if isinstance(batch, dict) and batch.get("TypeTag") == _STATIC]
        if current == wanted:
            return False
        batches[:] = wanted + [batch for batch in batches if not (isinstance(batch, dict) and batch.get("TypeTag") == _STATIC)]
        return True

    def give_own_effect(self, index: int) -> None:
        """Give a Unique that's without it the effect it comes with in the game, saved the way the game saves
        it. For one the editor made before it could write that effect."""
        item, _batches = self._effects_item(index)
        if not is_unique_version(item.tag):
            raise ValueError(f"{the(item.name, start=True)} isn't a Unique: only a Unique comes with an effect of its own.")
        if not item.own_effect_missing:
            raise ValueError(f"{the(item.name, start=True)} has its own effect already.")
        if own_effect(item.tag) is None:
            raise ValueError(f"The editor hasn't seen how the game saves {the(item.name)}'s own effect yet, so it can't add it.")
        most = effect_book().max_effects
        if len(item.rolled_effects) + 1 > most:
            raise ValueError(f"The game caps an item at {most} effects, and {the(item.name)} has {len(item.rolled_effects)}. Take one off first.")
        self._set_own_effect(item.data)
        self._mark_unseen(item.data)

    def _effects_item(self, index: int) -> tuple[Item, list]:
        """An item whose effects can be changed, and its list of effect batches."""
        item = self._gear(index)
        if item.stock_slot:
            raise ValueError(f"The {item.name} is in the Village Merchant's stock. Make a copy, and change the copy.")
        batches = item.data.get("Effects")
        if not isinstance(batches, list) or not all(isinstance(batch, dict) for batch in batches):
            raise ValueError(f"The {item.name}'s effects are saved in a way the editor doesn't know, so it leaves them alone.")
        return item, batches

    def set_effects(self, index: int, choices: Sequence[EffectChoice]) -> None:
        """Give a weapon, armor piece or artifact these effects, in place of the ones the game rolled for it.

        They're saved the way the game saves the effects it rolls (one batch of the kind
        SW.Item.Effect.Rerollable), each exactly as a real save holds that tier. An effect the item keeps is
        left as it is. Any other effect the item has (an enchantment, a Unique's own) isn't touched, and
        counts towards the most the game gives an item. No effects at all removes the batch, which is how
        the game saves a Common item. An effect the item also comes with is fine: the game rolls those too
        (a Pride of the Plains, whose own effect is Duelist, has been seen with Duelist III rolled on it).
        """
        item, batches = self._effects_item(index)
        wanted = list(choices)
        if not item.can_have_effects:
            raise ValueError(f"The {item.name} can't have effects like these: the game rolls them on weapons, armor and artifacts.")
        if any(choice.is_enchantment for choice in wanted):
            raise ValueError("An enchantment isn't one of the effects the game rolls. Set it as the item's enchantment.")
        if len({choice.effect for choice in wanted}) != len(wanted):
            raise ValueError("An item can't have the same effect twice.")
        most = effect_book().max_effects
        own = len(item.own_effects)
        if len(wanted) + own > most:
            also = f", and the {item.name} has {own} of its own" if own else ""
            raise ValueError(f"The game caps an item at {most} effects{also}.")
        batch = next((batch for batch in batches if batch.get("TypeTag") == _REROLLABLE), None)
        kept = batch.get("EffectsInThisBatch") if batch is not None else None
        current = {_effect_key(entry): entry for entry in kept} if isinstance(kept, list) else {}
        made = [current.get((choice.effect, choice.template)) or _effect_entry(choice) for choice in wanted]
        if isinstance(kept, list) and len(made) == len(kept) and all(a is b for a, b in zip(made, kept)):
            return
        if not made:
            if batch is None:
                return
            batches.remove(batch)
        elif batch is not None:
            batch["EffectsInThisBatch"] = made
        else:
            # Before an enchantment: the game rolls an item's effects when it makes it, and enchants it later.
            at = next((position for position, other in enumerate(batches) if other.get("TypeTag") == _ENCHANTMENT), len(batches))
            batches.insert(at, {"TypeTag": _REROLLABLE, "EffectsInThisBatch": made})
        self._mark_unseen(item.data)

    def set_enchantment(self, index: int, choice: EffectChoice | None) -> None:
        """Enchant a weapon or armor piece, or with None take its enchantment off.

        It's saved the way the Enchantsmith's work is: one batch of the kind SW.Item.Effect.Enchantment
        holding the one enchantment, with the enchantment points the game counts for that tier on an item of
        that rarity (it hands them back when you disenchant). The editor doesn't take the points from you.
        """
        item, batches = self._effects_item(index)
        batch = next((batch for batch in batches if batch.get("TypeTag") == _ENCHANTMENT), None)
        if choice is None:
            if batch is not None:
                batches.remove(batch)
                self._mark_unseen(item.data)
            return
        if not choice.is_enchantment:
            raise ValueError(f"{choice.name} isn't an enchantment.")
        if not item.can_be_enchanted:
            raise ValueError(f"The {item.name} can't be enchanted: enchantments go on weapons and armor.")
        if not choice.fits(item.kind, item.piece):
            raise ValueError(f"{choice.name} goes on {_slot_words(choice.slots)}, and the {item.name} isn't one.")
        kept = batch.get("EffectsInThisBatch") if batch is not None else None
        if isinstance(kept, list) and len(kept) == 1 and _effect_key(kept[0]) == (choice.effect, choice.template):
            return  # it has this one already
        made = [_effect_entry(choice, effect_book().points_for(item.rarity, choice.tier))]
        if batch is not None:
            batch["EffectsInThisBatch"] = made
        else:
            batches.append({"TypeTag": _ENCHANTMENT, "EffectsInThisBatch": made})
        self._mark_unseen(item.data)

    def set_item_xp(self, index: int, xp: int | float) -> None:
        """Set the XP a talisman has earned. The game works out the level itself: it levels a talisman up when
        the XP it earns takes it past what the next level needs."""
        item = self._gear(index)
        progression = item.data.get("ItemProgression")
        if not item.is_talisman or not isinstance(progression, dict) or "CurrentXP" not in progression:
            raise ValueError(f"The {item.name} doesn't earn XP: only talismans do.")
        _check_number(xp, 0, MAX_ITEM_XP, "XP")
        progression["CurrentXP"] = int(xp) if float(xp).is_integer() else float(xp)

    def ready_talisman(self, index: int) -> int:
        """Put a talisman one XP short of its next level, so the next XP you earn in the game levels it up.
        Returns the XP it was given."""
        item = self._gear(index)
        if not item.is_talisman:
            raise ValueError(f"The {item.name} doesn't earn XP: only talismans do.")
        needed = item.next_level_xp
        if needed is None:
            raise ValueError(
                f"The {item.name} is at its last level." if item.is_talisman and item.progression.get("ItemLevels")
                else f"The editor doesn't know what the {item.name} needs for its next level."
            )
        # A save counts a talisman's XP from nothing: it isn't set back at a level-up. Whether the second number
        # the game files give (73,920) is the XP at level 3 or the XP from level 2 on hasn't been seen, so past the
        # first level this is the higher of the two: either way the next XP earned is enough.
        target = sum(effect_book().talisman_xp[: item.level + 1]) - 1
        self.set_item_xp(index, max(target, 0))
        return target

    def set_talisman_level(self, index: int, level: int) -> None:
        """Put a talisman at a level (1 is the one it starts at), the way the game saves a level-up. A real save
        showed it: the level goes up by one, the talisman's effect becomes that level's (the item carries every
        level's effect with it), and its XP stays as it was, counted from nothing. So the XP is brought to at
        least what the level takes, and kept under what the next one takes, or the next XP earned would move it."""
        item = self._gear(index)
        if not item.is_talisman:
            raise ValueError(f"{the(item.name, start=True)} has no levels: only talismans do.")
        effects = item.level_effects
        if not item.can_be_leveled:
            raise ValueError(
                f"The editor can't set the level of {the(item.name)}: "
                + ("it hasn't seen how the game saves a level-up of a talisman like this one (a companion's)." if item.progression.get("ItemLevels") else "it doesn't know its levels.")
            )
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= len(effects):
            raise ValueError(f"{the(item.name, start=True)} has levels 1 to {len(effects)}.")
        steps = [int(step) for step in effect_book().talisman_xp]
        if len(steps) < len(effects) - 1:
            raise ValueError(f"The editor doesn't know the XP {the(item.name)} needs for its levels.")
        # What a level takes, counted from nothing. The game files' second number may be the XP at level 3 or the
        # XP from level 2 on: the level's own XP is the higher reading, and the XP to stay under the lower one.
        least = sum(steps[: level - 1])
        most = None if level == len(effects) else max(min(steps[level - 1], sum(steps[:level])), least + 1) - 1
        xp = item.xp if _is_number(item.xp) else 0
        xp = max(xp, least) if most is None else min(max(xp, least), most)
        batch = next(batch for batch in item.data["Effects"] if isinstance(batch, dict) and batch.get("TypeTag") == _UPGRADABLE)
        batch["EffectsInThisBatch"] = copy.deepcopy(effects[level - 1])
        progression = item.data["ItemProgression"]
        progression["CurrentLevel"] = level - 1
        progression["CurrentXP"] = int(xp) if float(xp).is_integer() else xp

    # ------------------------------------------------------------ the town

    def vendors_opened(self) -> dict[str, bool]:
        """Which of the town's three vendors this hero has unlocked and opened, by the game's own records: the
        hint it files the first time you open a vendor's window, and the counts it keeps of what each vendor
        has done for you. The editor writes none of these, so an enchantment or a vendor level set here
        doesn't count. Nor does the Village Merchant's stock: a hero has that before the Merchant is found."""
        stats = self.body.get("CollectionsStats") or {}
        hints = {hint.get("Tag") for hint in stats.get("ShownHints") or [] if isinstance(hint, dict)}
        opened = {name: tag in hints for name, tag in VENDORS.items()}
        achievements = self.body.get("Achievements") or {}

        def done(group: str, name: str, key: str) -> bool:
            entry = (achievements.get(group) or {}).get(f"SW.Achievements.{name}")
            return bool(entry.get(key)) if isinstance(entry, dict) else False

        if done("BoolAchievements", "PurchaseASpecialGearPieceFromTheVillageMerchant", "bCompleted"):
            opened["Village Merchant"] = True
        if done("BoolAchievements", "ReforgeASpecialPieceOfGear", "bCompleted"):
            opened["Blacksmith"] = True
        if done("CountAchievements", "UpgradeAnEnchantmentToLevel3", "Count") or done("CollectionAchievements", "EnchantEveryInventorySlotWithLevel3Enchantments", "CollectedTags"):
            opened["Enchantsmith"] = True
        return opened

    @staticmethod
    def _make_new(entry: dict) -> None:
        """Turn a copied inventory entry into a new, unequipped item in the backpack."""
        data = entry.setdefault("ItemData", {})
        if "EquippedSlot" in entry:
            entry["EquippedSlot"] = "None"
        if "MerchantItemSold" in entry:
            entry["MerchantItemSold"] = False
        if "MerchantDiscount" in entry:
            entry["MerchantDiscount"] = 0
        if "TargetSlotOverride" in data:
            data["TargetSlotOverride"] = "None"
        generator = data.get("GeneratorData")
        if isinstance(generator, dict) and "GenesisRandomSeed" in generator:
            generator["GenesisRandomSeed"] = random.randrange(1, 2**32)
        if "PickupTimestamp" in data:
            data["PickupTimestamp"] = int(time.time())
        tags = data.get("DynamicPropertyTags")
        if isinstance(tags, list) and UNSEEN_TAG not in tags:
            tags.append(UNSEEN_TAG)

    def _add_entry(self, entry: dict) -> int:
        entries = self.body.setdefault("Inventory", {}).setdefault("Entries", [])
        entries.append(entry)
        return len(entries) - 1

    def duplicate_item(self, index: int) -> int:
        """Add an unequipped copy of an item to the inventory. Returns the copy's index."""
        item = self._gear(index)
        if item.is_book:
            raise ValueError(f"{ONE_OF_EACH}, and this one has the {item.name} book.")
        clone = copy.deepcopy(item.entry)
        self._make_new(clone)
        return self._add_entry(clone)

    def add_item(
        self,
        tag: str,
        template: dict,
        *,
        rarity: str | None = "Common",
        power: int | None = 1,
        count: int = 1,
        slot: GearSlot | None = None,
        check_level: bool = True,
    ) -> int:
        """Add a brand-new item, laid out like ``template`` (an existing inventory entry). Returns its index.

        ``rarity`` or ``power`` of None keeps the template's. With ``slot`` the item is equipped there.
        At Unique rarity the item gets its Unique's own ID, when that ID is known to be real. A talisman
        has no rarity or power, so those are left out for one, and it gets its effect instead. Nor has an
        enchantment book, which is laid out the way the game saves one: a hero has one of each.
        """
        tag = tag.strip()
        _check_addable_tag(tag)
        talisman, book = tag_kind(tag) == "Talisman", tag_kind(tag) == BOOK_KIND
        if talisman or book:
            rarity = power = None
        if book:
            if self.has_book(tag):
                raise ValueError(f"This hero already has the {display_name(tag)} book.")
            if count != 1:
                raise ValueError(f"{ONE_OF_EACH}, so the count is 1.")
        if rarity == "Unique":
            tag = unique_tag(tag, self.item_types_from_the_game()) or tag
        if rarity is not None and rarity not in RARITIES:
            raise ValueError(f"Rarity must be one of {', '.join(RARITIES)}.")
        if power is not None:
            _check_number(power, 0, MAX_ITEM_POWER, "Power", whole=True)
        _check_number(count, 1, MAX_STACK, "Count", whole=True)
        if slot is not None:
            self._check_slot(display_name(tag), tag_kind(tag), armor_piece(tag), slot, check_level)

        entry = copy.deepcopy(template)
        data = entry.setdefault("ItemData", {})
        # A copy of this very talisman that the game made carries its levels; a new one is laid out like it.
        own_levels = _item_levels(entry) if talisman and data.get("TypeTag") == tag else []
        data["TypeTag"] = tag
        if rarity is not None:
            data["RarityTag"] = RARITY_PREFIX + rarity
        if "Effects" in data:
            data["Effects"] = []
            self._set_own_effect(data)  # a Unique comes with an effect of its own
        if "EffectRerolls" in data:
            data["EffectRerolls"] = 0
        progression = data.get("ItemProgression")
        if isinstance(progression, dict):
            for key, fresh in (("CurrentLevel", 0), ("CurrentXP", 0), ("ItemLevels", [])):
                if key in progression:
                    progression[key] = fresh
        values = (data.get("GeneratorData") or {}).get("PowerGeneratorValues")
        if isinstance(values, dict):
            if "PlayerLevel" in values and isinstance(self.level, int):
                values["PlayerLevel"] = self.level
            for key in ("ItemPower", "ItemPowerOriginal", "ItemPowerMin", "ItemPowerMax"):
                if key in values and power is not None:
                    values[key] = int(power)
        if talisman:
            self._as_talisman(data, own_levels or self._talisman_levels(tag))
        if book:
            self._as_book(data)
        entry["StackCount"] = int(count)
        self._make_new(entry)
        index = self._add_entry(entry)
        loot = (self.body.get("LootProgression") or {}).get("DiscoveredLoot")
        if isinstance(loot, list) and tag not in loot:
            loot.append(tag)
        if slot is not None:
            self.equip(index, slot, check_level)
        return index

    @staticmethod
    def _as_talisman(data: dict, levels: list) -> None:
        """Lay a new talisman out the way the game saves one it has just handed over: no rarity, no power, and
        its effect at level 1 with every level listed. Without ``levels`` (the editor doesn't know what this
        talisman does) it has no effect at all, and may do nothing in the game."""
        data["RarityTag"] = RARITY_PREFIX + NO_RARITY
        first = levels[0].get("LevelEffects") if levels else None  # a companion's talisman has none
        data["Effects"] = [{"TypeTag": _UPGRADABLE, "EffectsInThisBatch": copy.deepcopy(first)}] if first else []
        progression = data.setdefault("ItemProgression", {})
        progression.update(CurrentLevel=0, CurrentXP=0, ItemLevels=copy.deepcopy(levels))
        values = (data.get("GeneratorData") or {}).get("PowerGeneratorValues")
        if isinstance(values, dict):
            values.update({key: value for key, value in _NO_POWER.items() if key in values})

    @staticmethod
    def _as_book(data: dict) -> None:
        """Lay a new enchantment book out the way the game saves one it has just handed over. Seven of them in a
        real save were alike in everything but the ID, the seed and the time: no rarity, no power, no effects,
        no levels, and no mark but the one for an item you haven't looked at (``_make_new`` puts that on)."""
        data["RarityTag"] = RARITY_PREFIX + NO_RARITY
        data["Effects"] = []
        progression = data.setdefault("ItemProgression", {})
        progression.update(CurrentLevel=0, CurrentXP=0, ItemLevels=[])
        values = (data.get("GeneratorData") or {}).get("PowerGeneratorValues")
        if isinstance(values, dict):
            values.update({key: value for key, value in _NO_POWER.items() if key in values})
        if isinstance(data.get("DynamicPropertyTags"), list):
            data["DynamicPropertyTags"] = []

    def books(self) -> list[Item]:
        """The enchantment books in the inventory."""
        return [item for item in self.items() if item.is_book and not item.stock_slot]

    def has_book(self, tag: str) -> bool:
        return any(item.tag == tag for item in self.books())

    def missing_books(self, catalog: list["CatalogItem"]) -> list["CatalogItem"]:
        """The enchantment books in ``catalog`` that this hero doesn't have, leaving out any whose ID is a guess."""
        have = {item.tag for item in self.books()}
        return [entry for entry in catalog if entry.kind == BOOK_KIND and entry.confirmed and entry.tag not in have]

    def add_books(self, catalog: list["CatalogItem"]) -> list[int]:
        """Add every enchantment book this hero doesn't have yet (``missing_books``). Returns the new entries'
        indexes."""
        return [self.add_item(entry.tag, entry.template) for entry in self.missing_books(catalog)]

    def _talisman_levels(self, tag: str) -> list:
        """What a talisman does at each level: from one the game gave this hero, else from the item list.
        Empty when neither shows it."""
        for item in self.items():
            if item.tag == tag and _item_levels(item.entry):
                return _item_levels(item.entry)
        return talisman_levels(tag)

    def best_power(self) -> int:
        """Power of the hero's strongest item (at least 1)."""
        powers = [item.power for item in self.items() if not item.is_cosmetic and isinstance(item.power, (int, float))]
        return max([1] + [int(power) for power in powers])

    def remove_item(self, index: int) -> None:
        item = self._gear(index)
        if item.equipped_slot:
            raise ValueError(f"Unequip the {item.name} before deleting it.")
        del self._entries()[index]

    # ---------------------------------------------------------- equipment

    def elements_in_play(self) -> set[str]:
        """The elements of the artifacts this hero has equipped (Fire, Soul...): the ones an effect that boosts
        one element's attacks would do anything for."""
        return {item.element for item in self.items() if item.equipped_slot and item.element}

    def equipped(self, slot_tag: str) -> Item | None:
        """The item in a gear slot, if any."""
        return next((item for item in self.items() if item.equipped_slot == slot_tag), None)

    def _check_slot(self, name: str, kind: str, piece: str | None, slot: GearSlot, check_level: bool) -> None:
        if not slots_for(kind, piece, [slot]):
            raise ValueError(f"The {name} doesn't go in the {slot.label.lower()} slot.")
        if check_level and isinstance(self.level, int) and self.level < slot.level:
            raise ValueError(f"The {slot.label.lower()} slot opens at level {slot.level}, and this hero is level {self.level}.")

    def equip(self, index: int, slot: GearSlot, check_level: bool = True) -> Item | None:
        """Put an item on, in ``slot``. Returns the item that was there, which goes back to the inventory.

        With ``check_level`` a slot the hero's level hasn't opened yet is refused.
        """
        item = self._gear(index)
        if item.stock_slot:
            raise ValueError(f"The {item.name} is in the Village Merchant's stock. Make a copy to get one for yourself.")
        self._check_slot(item.name, item.kind, item.piece, slot, check_level)
        current = self.equipped(slot.tag)
        if current is not None and current.index == index:
            return None
        if current is not None:
            current.entry["EquippedSlot"] = EMPTY_SLOT
        item.entry["EquippedSlot"] = slot.tag
        return current

    def unequip(self, index: int) -> None:
        """Take an item off. It stays in the inventory."""
        item = self._gear(index)
        if item.equipped_slot:
            item.entry["EquippedSlot"] = EMPTY_SLOT

    def collected_item_types(self) -> set[str]:
        """Item IDs in the game's own collections (CollectionsStats): it files an item there when you pick
        it up. The editor never writes these lists."""
        tags: set[str] = set()
        for key, values in (self.body.get("CollectionsStats") or {}).items():
            if key.startswith("Collected") and isinstance(values, list):
                tags.update(tag for tag in values if isinstance(tag, str))
        return {tag for tag in tags if _ITEM_TAG.fullmatch(tag)}

    def item_types_from_the_game(self) -> dict[str, str]:
        """Item IDs in this save that the game itself vouches for, and how each one is known:

        - ``"collected"``: it's in the game's collections.
        - ``"merchant"``: it's in the Village Merchant's stock, which the game makes.
        - ``"kept"``: it's on an item the game has shown you. The game drops an item whose ID it doesn't
          know when it loads a hero, so an item it has shown you since is real, even one the editor made.

        An item the editor has just added or changed is still marked as not looked at, so it doesn't count
        yet. Nor does the discovered-loot list, which the editor adds to itself. This is what keeps the
        editor's own guesses from coming back as "seen in a real save".
        """
        found = dict.fromkeys(self.collected_item_types(), "collected")
        for item in self.items():
            if item.tag in found or not _ITEM_TAG.fullmatch(item.tag):
                continue
            marks = item.data.get("DynamicPropertyTags")
            if item.stock_slot:
                found[item.tag] = "merchant"
            elif isinstance(marks, list) and UNSEEN_TAG not in marks:
                found[item.tag] = "kept"
        return found

    def seen_item_types(self) -> set[str]:
        """Every item ID in this save: inventory, discovered loot and collections. Some of these the editor
        may have written itself; ``item_types_from_the_game`` has only the ones the game vouches for."""
        tags = {item.tag for item in self.items()}
        tags.update(tag for tag in (self.body.get("LootProgression") or {}).get("DiscoveredLoot") or [] if isinstance(tag, str))
        for key, values in (self.body.get("CollectionsStats") or {}).items():
            if key.startswith("Collected") and isinstance(values, list):
                tags.update(tag for tag in values if isinstance(tag, str))
        return {tag for tag in tags if _ITEM_TAG.fullmatch(tag)}

    def known_item_types(self) -> list[str]:
        """Item types seen in this save, without cosmetics."""
        return sorted(tag for tag in self.seen_item_types() if not tag.startswith(COSMETIC_PREFIX))


@dataclass
class CatalogItem:
    """An item that can be added, with an existing inventory entry to copy the layout from."""

    tag: str
    template: dict
    confirmed: bool = True  # the ID is one the game has been seen to use, so the game knows it
    title: str | None = None  # in-game name, when known
    unique: str | None = None  # name of the item at Unique rarity
    kind_name: str | None = None
    unique_effect: str | None = None  # what the Unique does
    unique_tag: str | None = None  # the Unique's own ID, when it's known to be real
    no_effect: bool = False  # a talisman the editor can only add without its effect: no save has shown it yet

    @property
    def name(self) -> str:
        return self.title or item_name(self.tag)

    @property
    def kind(self) -> str:
        return self.kind_name or item_kind(self.tag)

    @property
    def piece(self) -> str | None:
        return armor_piece(self.tag) if self.kind == "Armor" else None

    def tag_at(self, rarity: str | None) -> str:
        """The ID to add it under. At Unique rarity that's its Unique's own ID: the one seen in real saves, or
        else a guess after the pattern every Unique seen so far follows."""
        if rarity != "Unique" or not self.unique:
            return self.tag
        return self.unique_tag or self.tag + ("_Unique" if self.kind == "Armor" else "_Unique1")

    def id_known_at(self, rarity: str | None = None) -> bool:
        """Whether the game has been seen to use the ID it's added under at this rarity."""
        return self.unique_tag is not None if rarity == "Unique" and self.unique else self.confirmed

    def by_pattern_at(self, rarity: str | None = None) -> bool:
        """Whether it's added under a Unique's ID that hasn't been seen itself, but follows the pattern of
        every Unique's ID that has: its base item's ID, which is known, with _Unique1 (weapons) or _Unique
        (armor) on the end."""
        return rarity == "Unique" and bool(self.unique) and self.unique_tag is None and self.confirmed

    def id_trusted_at(self, rarity: str | None = None) -> bool:
        """Whether the ID it's added under is good enough to add without asking: seen, or a Unique's by the
        pattern. (Making an item you own Unique is stricter: there a wrong ID would cost you the item.)"""
        return self.id_known_at(rarity) or self.by_pattern_at(rarity)

    def confirmed_at(self, rarity: str | None = None) -> bool:
        """Whether it can be added at this rarity without asking: its ID is trusted, and a talisman gets
        its effect."""
        return self.id_trusted_at(rarity) and not self.no_effect

    def doubt(self, rarity: str | None = None) -> str:
        """Why adding it at this rarity is a guess, as a sentence. Empty when it isn't one."""
        if self.no_effect and not self.id_trusted_at(rarity):
            return (
                "The game's name for this talisman is a best guess, and the editor hasn't seen its effect in a "
                "save yet, so it's added without one."
            )
        if self.no_effect:
            return "The editor hasn't seen this talisman's effect in a save yet, so it's added without one and may do nothing in the game."
        return "" if self.id_trusted_at(rarity) else "The game's name for this item is a best guess."

    def name_at(self, rarity: str | None) -> str:
        return self.unique if rarity == "Unique" and self.unique else self.name

    def own_effect_at(self, rarity: str | None) -> OwnEffect | None:
        """The effect of its own it's added with at this rarity: a Unique's, when the editor has seen it."""
        return own_effect(self.tag_at(rarity)) if rarity == "Unique" and self.unique else None

    def bare_unique_at(self, rarity: str | None) -> bool:
        """Whether it's added as a Unique without the effect that makes it one."""
        return rarity == "Unique" and bool(self.unique) and self.own_effect_at(rarity) is None


def gear_slots(heroes: list[Hero]) -> list[GearSlot]:
    """GEAR_SLOTS, unless these heroes' saves show other names for the slots: real saves win.

    An armor slot takes the name seen for the same piece, and an artifact or talisman slot the
    name seen for the same slot number, or else another slot's name with the number swapped in
    (a guess, so not confirmed).
    """
    seen: dict[str, Item] = {}
    for hero in heroes:
        for item in hero.items():
            if item.equipped_slot and not item.is_cosmetic:
                seen.setdefault(item.equipped_slot, item)
    slots = []
    for slot in GEAR_SLOTS:
        same_kind = [(tag, item) for tag, item in seen.items() if item.kind == slot.kind]
        numbered = [(tag, _slot_number(tag)) for tag, _item in same_kind if _slot_number(tag) is not None]
        if slot.tag in seen:
            slot = replace(slot, confirmed=True)
        elif slot.piece is not None:
            tag = next((tag for tag, item in same_kind if item.piece == slot.piece), None)
            if tag is not None:
                slot = replace(slot, tag=tag, confirmed=True)
        elif numbered and _slot_number(slot.tag) is not None:
            number = _slot_number(slot.tag)
            tag = next((tag for tag, seen_number in numbered if seen_number == number), None)
            if tag is not None:
                slot = replace(slot, tag=tag, confirmed=True)
            else:
                tag = re.sub(r"\d+$", str(number), numbered[0][0])
                if tag != slot.tag:
                    slot = replace(slot, tag=tag, confirmed=False)
        slots.append(slot)
    return slots


WORN_KINDS = ("Melee", "Ranged", "Armor", "Artifact")  # what counts towards gear power


def gear_power(hero: Hero, slots: list[GearSlot]) -> tuple[int | None, dict[str, int]]:
    """Gear power as the game shows it: the average power of the weapons, armor and artifacts the hero
    has on, rounded down (talismans don't count), and the total for each kind. None if nothing counts.

    Checked against the game: power 45, 44, 157 for four armor pieces and 108 for three artifacts show
    as gear power 39, and a hero wearing gear at power 10, 1, 2 and 2 was saved with power level 3.
    """
    kind_of_slot = {slot.tag: slot.kind for slot in slots}
    totals = dict.fromkeys(WORN_KINDS, 0)
    powers = []
    for item in hero.items():
        if not item.equipped_slot or item.is_cosmetic or isinstance(item.power, bool) or not isinstance(item.power, (int, float)):
            continue
        kind = kind_of_slot.get(item.equipped_slot, item.kind)
        if kind in totals:
            totals[kind] += int(item.power)
            powers.append(item.power)
    return (int(sum(powers) // len(powers)) if powers else None), totals


def build_catalog(heroes: list[Hero]) -> list[CatalogItem]:
    """Items that can be added: every item in the game's item list, plus any other item ID
    the game has saved for these heroes. Cosmetics, quest items and currencies are left out.
    An enchantment book needs no copy of itself to be laid out like: ``Hero.add_item`` lays one
    out the way the game does, whatever it borrows the layout from.

    IDs the game vouches for in these saves (``Hero.item_types_from_the_game``) are confirmed;
    the game list's other IDs are best guesses from the items' names (see
    tools/build_item_catalog.py). Each item borrows the layout of a saved
    inventory entry: the same item, the same group, or any gear. A Unique isn't an entry of
    its own: its base item's entry carries the Unique's ID, once that has been seen. A talisman
    also needs its effect: one that neither the item list nor a saved copy shows is ``no_effect``.
    """
    seen: set[str] = set()
    by_tag: dict[str, dict] = {}
    by_group: dict[str, dict] = {}
    for hero in heroes:
        seen |= set(hero.item_types_from_the_game())
        for item in hero.items():
            if not item.is_cosmetic:
                # A talisman the game handed over carries its effect, so it's the better one to lay a new one out like.
                if item.tag not in by_tag or (_item_levels(item.entry) and not _item_levels(by_tag[item.tag])):
                    by_tag[item.tag] = item.entry
                by_group.setdefault(item_group(item.tag), item.entry)
    fallback = by_group.get("Gear") or next(iter(by_group.values()), None)

    def template(tag: str) -> dict | None:
        return by_tag.get(tag) or by_group.get(item_group(tag)) or fallback

    def no_effect(tag: str, levels: tuple = ()) -> bool:
        return tag_kind(tag) == "Talisman" and not levels and not _item_levels(by_tag.get(tag) or {})

    catalog: dict[str, CatalogItem] = {}
    for game_item in game_items():
        if game_item.id in catalog or item_group(game_item.id) in NOT_ADDABLE_GROUPS or template(game_item.id) is None:
            continue
        catalog[game_item.id] = CatalogItem(
            game_item.id,
            template(game_item.id),
            confirmed=game_item.confirmed or game_item.id in seen,
            title=game_item.name,
            unique=game_item.unique,
            kind_name=game_item.kind,
            unique_effect=game_item.unique_effect,
            unique_tag=unique_tag(game_item.id, seen),
            no_effect=no_effect(game_item.id, game_item.levels),
        )
    for tag in seen:
        if tag in catalog or is_unique_version(tag) or item_group(tag) in NOT_ADDABLE_GROUPS or template(tag) is None:
            continue
        catalog[tag] = CatalogItem(tag, template(tag), no_effect=no_effect(tag))
    return sorted(catalog.values(), key=lambda entry: (entry.kind, entry.name.lower()))


def template_for(tag: str, catalog: list[CatalogItem]) -> dict | None:
    """An entry to lay an item ID out like: the same item (its base item, for a Unique), the same group, or
    any gear."""
    base = base_tag(tag)
    for match in (lambda c: c.tag == tag, lambda c: c.tag == base, lambda c: item_group(c.tag) == item_group(tag), lambda c: True):
        found = next((c.template for c in catalog if match(c)), None)
        if found is not None:
            return found
    return None


def describe_changes(before: dict, after: dict) -> list[str]:
    """Plain-English list of stat and item changes between two versions of a hero save."""
    old, new = Hero(before), Hero(after)
    lines = []
    old_stats = {a["AttributeName"]: a.get("CurrentValue") for a in old.attributes()}
    for attribute in new.attributes():
        name, value = attribute["AttributeName"], attribute.get("CurrentValue")
        if name in old_stats and old_stats[name] != value:
            lines.append(f"{attribute_label(name)}: {format_amount(old_stats[name])} → {format_amount(value)}")
    old_items, new_items = items_by_identity(old), items_by_identity(new)
    for key, item in old_items.items():
        other = new_items.get(key)
        if other is None:
            lines.append(f"Removed {_listed(item)}")
            continue
        parts = []
        if other.tag != item.tag:
            parts.append(f"changed into {other.name}")
        if other.rarity != item.rarity:
            parts.append(f"{item.rarity} → {other.rarity}")
        if other.power != item.power:
            parts.append(f"power {format_amount(item.power)} → {format_amount(other.power)}")
        if other.count != item.count:
            parts.append(f"count {item.count} → {other.count}")
        if [effect.text for effect in other.rolled_effects] != [effect.text for effect in item.rolled_effects]:
            parts.append("effects: " + (", ".join(effect.text for effect in other.rolled_effects) or "none"))
        was, now = item.enchantment, other.enchantment
        if (was.title if was else None) != (now.title if now else None):
            parts.append(f"enchanted with {now.title}" if now else "enchantment taken off")
        if other.tag == item.tag and item.own_effect_missing and not other.own_effect_missing:
            parts.append("given its own effect")
        if other.is_talisman and other.level != item.level and isinstance(item.level, int) and isinstance(other.level, int):
            parts.append(f"level {item.level + 1} → {other.level + 1}")
        if other.is_talisman and other.xp != item.xp:
            parts.append(f"XP {format_amount(item.xp)} → {format_amount(other.xp)}")
        if other.equipped_slot != item.equipped_slot:
            parts.append(other.where[0].lower() + other.where[1:] if other.equipped_slot else "unequipped")
        if parts:
            lines.append(f"{item.name}: {', '.join(parts)}")
    for key, item in new_items.items():
        if key not in old_items:
            equipped = f", {item.where[0].lower() + item.where[1:]}" if item.equipped_slot else ""
            grade = "" if item.ungraded else f" ({item.rarity}, power {format_amount(item.power)})"
            lines.append(f"Added {_listed(item)}{grade}{equipped}")
    return lines


def _listed(item: Item) -> str:
    """An item's name in the list of changes. A book goes by its enchantment's name, so the list says it's the book."""
    return f"{item.name} (enchantment book)" if item.is_book else item.name


def items_by_identity(hero: Hero) -> dict[tuple, Item]:
    """Items keyed by their random seed (unique per item), so edits can be matched up."""
    found: dict[tuple, Item] = {}
    for item in hero.items():
        seed = (item.data.get("GeneratorData") or {}).get("GenesisRandomSeed", ("index", item.index))
        occurrence = 0
        while (seed, occurrence) in found:
            occurrence += 1
        found[(seed, occurrence)] = item
    return found


# Sort choices for heroes: label -> key (highest first)
HERO_SORTS = {
    "Most powerful": lambda hero: hero.power_level or 0,
    "Highest level": lambda hero: hero.level or 0,
    "Most XP": lambda hero: hero.attribute("XP") or 0,
    "Most emeralds": lambda hero: hero.attribute("Emeralds") or 0,
}
