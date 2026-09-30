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
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

GAME_ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"  # made by tools/build_item_catalog.py

ITEM_PREFIX = "SW.Item."
COSMETIC_PREFIX = "SW.Item.Cosmetic."
RARITY_PREFIX = "SW.Rarity."
RARITIES = ("Common", "Rare", "Special", "Unique")
UNSEEN_TAG = "SW.Item.Property.Dynamic.Unseen"
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
STAT_CAPS = {
    "Emeralds": 9_999,
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


@lru_cache(maxsize=1)
def game_items() -> tuple[GameItem, ...]:
    try:
        entries = json.loads(GAME_ITEMS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(
        GameItem(e["name"], e["kind"], e["id"], bool(e.get("confirmed")), e.get("unique"), e.get("slot"))
        for e in entries
        if isinstance(e, dict) and e.get("name") and e.get("id")
    )


@lru_cache(maxsize=1)
def _game_items_by_id() -> dict[str, GameItem]:
    found: dict[str, GameItem] = {}
    for game_item in game_items():
        found.setdefault(game_item.id, game_item)
    return found


def display_name(tag: str, rarity: str = "") -> str:
    """The in-game name: 'SW.Item.MysticHelmet' is the Mystic Circlet, or the Oracle Crown at Unique rarity."""
    known = _game_items_by_id().get(tag)
    if known is None:
        return item_name(tag)
    return known.unique if rarity == "Unique" and known.unique else known.name


def item_group(tag: str) -> str:
    """'Gear' for weapons and armor (SW.Item.<Name>), else the group named in the tag (Artifact, Talisman, ...)."""
    parts = tag.split(".")
    return parts[2] if len(parts) > 3 else "Gear"


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
        return display_name(self.tag, self.rarity)

    @property
    def kind(self) -> str:
        known = _game_items_by_id().get(self.tag)
        return known.kind if known else item_kind(self.tag)

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
        can't re-roll it to something else.
        """
        item = self._gear(index)
        if tag is not None:
            tag = tag.strip()
            if tag != item.tag:
                _check_addable_tag(tag)
                if item.equipped_slot:
                    raise ValueError(f"Unequip the {item.name} in the game before changing what it is.")
        if rarity is not None and rarity != item.rarity and rarity not in RARITIES:
            raise ValueError(f"Rarity must be one of {', '.join(RARITIES)}.")
        if power is not None:
            _check_number(power, 0, MAX_ITEM_POWER, "Power", whole=True)
            if "ItemPower" not in item.power_values:
                raise ValueError(f"The {item.name} has no power value.")
        if count is not None:
            _check_number(count, 1, MAX_STACK, "Count", whole=True)

        if tag is not None and tag != item.tag:
            item.data["TypeTag"] = tag
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

    def add_item(self, tag: str, template: dict, *, rarity: str | None = "Common", power: int | None = 1, count: int = 1) -> int:
        """Add a brand-new item, laid out like ``template`` (an existing inventory entry). Returns its index.

        ``rarity`` or ``power`` of None keeps the template's.
        """
        tag = tag.strip()
        _check_addable_tag(tag)
        if rarity is not None and rarity not in RARITIES:
            raise ValueError(f"Rarity must be one of {', '.join(RARITIES)}.")
        if power is not None:
            _check_number(power, 0, MAX_ITEM_POWER, "Power", whole=True)
        _check_number(count, 1, MAX_STACK, "Count", whole=True)

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
        return index

    def best_power(self) -> int:
        """Power of the hero's strongest item (at least 1)."""
        powers = [item.power for item in self.items() if not item.is_cosmetic and isinstance(item.power, (int, float))]
        return max([1] + [int(power) for power in powers])

    def remove_item(self, index: int) -> None:
        item = self._gear(index)
        if item.equipped_slot:
            raise ValueError(f"Unequip the {item.name} in the game before removing it.")
        del self._entries()[index]

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

    @property
    def name(self) -> str:
        return self.title or item_name(self.tag)

    @property
    def kind(self) -> str:
        return self.kind_name or item_kind(self.tag)


def build_catalog(heroes: list[Hero]) -> list[CatalogItem]:
    """Items that can be added: every item in the game's item list, plus any other item ID
    the game has saved for these heroes. Cosmetics, quest items and currencies are left out.

    IDs seen in saves are confirmed; the game list's other IDs are best guesses from the
    items' names (see tools/build_item_catalog.py). Each item borrows the layout of a saved
    inventory entry: the same item, the same group, or any gear.
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
        catalog[game_item.id] = CatalogItem(
            game_item.id,
            template(game_item.id),
            confirmed=game_item.confirmed or game_item.id in seen,
            title=game_item.name,
            unique=game_item.unique,
            kind_name=game_item.kind,
        )
    for tag in seen:
        if tag not in catalog and item_group(tag) not in NOT_ADDABLE_GROUPS and template(tag) is not None:
            catalog[tag] = CatalogItem(tag, template(tag))
    return sorted(catalog.values(), key=lambda entry: (entry.kind, entry.name.lower()))


def template_for(tag: str, catalog: list[CatalogItem]) -> dict | None:
    """An entry to lay a typed-in item ID out like: same item, same group, or any gear."""
    for match in (lambda c: c.tag == tag, lambda c: item_group(c.tag) == item_group(tag), lambda c: True):
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
    old_items, new_items = _items_by_identity(old), _items_by_identity(new)
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
        if parts:
            lines.append(f"{item.name}: {', '.join(parts)}")
    for key, item in new_items.items():
        if key not in old_items:
            lines.append(f"Added {item.name} ({item.rarity}, power {format_amount(item.power)})")
    return lines


def _items_by_identity(hero: Hero) -> dict[tuple, Item]:
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
