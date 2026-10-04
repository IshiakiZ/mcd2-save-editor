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
from typing import Any, Iterable

GAME_ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"  # made by tools/build_item_catalog.py
ENCHANTMENTS_FILE = GAME_ITEMS_FILE.with_name("enchantments.json")

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
_ITEM_TAG = re.compile(r"SW\.Item\.[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*")
_UNIQUE_SUFFIX = re.compile(r"_Unique\d*$")  # on a Unique's own ID: SW.Item.Sword_Unique1, SW.Item.MysticHelmet_Unique
BOOK_KIND = "Enchantment Book"  # SW.Item.EnchantmentBook.<Name>; only offered to a hero that has one to copy

_RANGED = re.compile(r"bow|sling|blowgun|launcher", re.IGNORECASE)  # Longbow, Crossbow, ...
_ARMOR = re.compile(r"Helmet|Helm|Hood|Hat|Mask|Chest|Armor|Armour|Mail|Robe|Tunic|Vest|Leggings|Pants|Greaves|Boots|Shoes|Gauntlets|Gloves")


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


@dataclass(frozen=True)
class Enchantment:
    """An enchantment (dungeons2_editor/data/enchantments.json)."""

    name: str
    slots: tuple[str, ...]  # Melee, Ranged, Armor (any piece) or Chestplate
    book: str  # where its book drops
    tier3: str  # what it does at tier III


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
        )
        for e in _load(GAME_ITEMS_FILE, "items")
        if e.get("id") and e.get("kind")
    )


@lru_cache(maxsize=1)
def enchantments() -> dict[str, Enchantment]:
    """Every enchantment by name."""
    return {
        e["name"]: Enchantment(e["name"], tuple(e.get("slots") or ()), e.get("book", ""), e.get("tier3", ""))
        for e in _load(ENCHANTMENTS_FILE, "enchantments")
    }


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
    def enchantments(self) -> int:
        return len(self.data.get("Effects") or [])

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
    "Most enchantments": (lambda item: item.enchantments, True),
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
        A ``tag`` that's given is otherwise kept exactly.
        """
        item = self._gear(index)
        if tag is not None:
            tag = tag.strip()
            if tag != item.tag:
                _check_addable_tag(tag)
                if item.equipped_slot:
                    raise ValueError(f"Unequip the {item.name} before changing what it is.")
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
            wanted = unique_tag(wanted, self.seen_item_types()) or wanted
        elif rarity is not None and tag is None:
            wanted = base_tag(wanted)
        if wanted != item.tag:
            item.data["TypeTag"] = wanted
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
        clone = copy.deepcopy(self._gear(index).entry)
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
        At Unique rarity the item gets its Unique's own ID, when that ID is known to be real.
        """
        tag = tag.strip()
        _check_addable_tag(tag)
        if rarity == "Unique":
            tag = unique_tag(tag, self.seen_item_types()) or tag
        if rarity is not None and rarity not in RARITIES:
            raise ValueError(f"Rarity must be one of {', '.join(RARITIES)}.")
        if power is not None:
            _check_number(power, 0, MAX_ITEM_POWER, "Power", whole=True)
        _check_number(count, 1, MAX_STACK, "Count", whole=True)
        if slot is not None:
            self._check_slot(display_name(tag), tag_kind(tag), armor_piece(tag), slot, check_level)

        entry = copy.deepcopy(template)
        data = entry.setdefault("ItemData", {})
        data["TypeTag"] = tag
        if rarity is not None:
            data["RarityTag"] = RARITY_PREFIX + rarity
        if "Effects" in data:
            data["Effects"] = []
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
        entry["StackCount"] = int(count)
        self._make_new(entry)
        index = self._add_entry(entry)
        loot = (self.body.get("LootProgression") or {}).get("DiscoveredLoot")
        if isinstance(loot, list) and tag not in loot:
            loot.append(tag)
        if slot is not None:
            self.equip(index, slot, check_level)
        return index

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

    def seen_item_types(self) -> set[str]:
        """Every item ID in this save: inventory, discovered loot and collections."""
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
    confirmed: bool = True  # the ID has been seen in real saves, so the game knows it
    title: str | None = None  # in-game name, when known
    unique: str | None = None  # name of the item at Unique rarity
    kind_name: str | None = None
    unique_effect: str | None = None  # what the Unique does
    unique_tag: str | None = None  # the Unique's own ID, when it's known to be real

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

    def confirmed_at(self, rarity: str | None) -> bool:
        """Whether the game is known to have the ID it's added under at this rarity."""
        return self.unique_tag is not None if rarity == "Unique" and self.unique else self.confirmed

    def name_at(self, rarity: str | None) -> str:
        return self.unique if rarity == "Unique" and self.unique else self.name


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
    the game has saved for these heroes. Cosmetics, quest items and currencies are left out,
    and so is an enchantment book unless a hero has that book to copy.

    IDs seen in saves are confirmed; the game list's other IDs are best guesses from the
    items' names (see tools/build_item_catalog.py). Each item borrows the layout of a saved
    inventory entry: the same item, the same group, or any gear. A Unique isn't an entry of
    its own: its base item's entry carries the Unique's ID, once that has been seen.
    """
    seen: set[str] = set()
    by_tag: dict[str, dict] = {}
    by_group: dict[str, dict] = {}
    for hero in heroes:
        seen |= hero.seen_item_types()
        for item in hero.items():
            if not item.is_cosmetic:
                by_tag.setdefault(item.tag, item.entry)
                by_group.setdefault(item_group(item.tag), item.entry)
    fallback = by_group.get("Gear") or next(iter(by_group.values()), None)

    def template(tag: str) -> dict | None:
        return by_tag.get(tag) or by_group.get(item_group(tag)) or fallback

    catalog: dict[str, CatalogItem] = {}
    for game_item in game_items():
        if game_item.id in catalog or item_group(game_item.id) in NOT_ADDABLE_GROUPS or template(game_item.id) is None:
            continue
        if game_item.kind == BOOK_KIND and game_item.id not in by_tag:
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
        )
    for tag in seen:
        if tag in catalog or is_unique_version(tag) or item_group(tag) in NOT_ADDABLE_GROUPS or template(tag) is None:
            continue
        catalog[tag] = CatalogItem(tag, template(tag))
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
            lines.append(f"Removed {item.name}")
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
        if other.equipped_slot != item.equipped_slot:
            parts.append(other.where[0].lower() + other.where[1:] if other.equipped_slot else "unequipped")
        if parts:
            lines.append(f"{item.name}: {', '.join(parts)}")
    for key, item in new_items.items():
        if key not in old_items:
            equipped = f", {item.where[0].lower() + item.where[1:]}" if item.equipped_slot else ""
            lines.append(f"Added {item.name} ({item.rarity}, power {format_amount(item.power)}){equipped}")
    return lines


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
