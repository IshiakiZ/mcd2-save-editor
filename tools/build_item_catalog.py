"""Builds the editor's item and enchantment lists from MetaBot's Minecraft Dungeons II database.

MetaBot (https://metabot.gg/en/minecraft-dungeons-2) lists every item in the game files
(build 1.1.1.0). Its terms allow reusing the data with a link to the page it came from; the
links are in each file this writes and in the README:

    uniques       every Unique, its slot and its base item: so every weapon, and every
                  armor piece with its set and slot
    artifacts     every artifact
    talismans     every talisman and what it does at level 3
    enchantments  every enchantment, the gear it goes on and where its book drops

The game's own item IDs aren't published anywhere the editor can use, so each item's save ID
comes from real saves where players have reported it, and is otherwise worked out from its
name, following the patterns seen in those saves:

    weapons     SW.Item.<Name>               (Sword, Bow, Longbow)
    armor       SW.Item.<Set><Slot>          (MysticHelmet is the Mystic Circlet)
    artifacts   SW.Item.Artifact.<Name>
    talismans   SW.Item.Talisman.<Name>
    Uniques     the base item's ID with _Unique1 (weapons) or _Unique (armor) on the end
    books       SW.Item.EnchantmentBook.<Name>

IDs seen in real saves are marked "confirmed". The rest are best guesses, and plenty will be
wrong: the game's internal names often aren't the names players see (the Riftslasher is saved
as CurvedLongsword, the Sculk Digger set as CaveCrawler, the Amethyst Lens as
Talisman.RangedBuff). A Unique's own ID is only listed once it has been seen.

Run from the repository root:  python tools/build_item_catalog.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://metabot.gg/en/minecraft-dungeons-2/"
PAGES = ("uniques", "artifacts", "talismans", "enchantments")
HEADERS = {"User-Agent": "Dungeons2SaveEditor/1.2 (item catalog builder; +https://github.com/IshiakiZ/mcd2-save-editor)"}
DATA = Path(__file__).resolve().parent.parent / "dungeons2_editor" / "data"
PREFIX = "SW.Item."
BOOK = "Enchantment Book"

# IDs seen in real saves, without the SW.Item. in front: the developer's own, and the ones players sent in
# https://github.com/IshiakiZ/mcd2-save-editor/issues/2, /issues/7 and /issues/9.
CONFIRMED_IDS = {
    PREFIX + name
    for name in """
    Sword Bow Longbow HeavyCrossbow
    Axe Claws Claymore Cleaver Crossbow CurvedGreatsword CurvedLongsword Dagger Daggers DualCrossbow
    Gauntlet GiantClub Glaive GreatAxe Greatbow Greatsword Hammer Mace MoonSword Pickaxe Pike Powerbow
    RapidCrossbow Rapier Sabre ScatterCrossbow Scythe ShortSpear Shortbow Shovel Sickles StraightSword
    Trickbow WarHammer Battlestaff

    CaveCrawlerBoots CaveCrawlerChest CaveCrawlerHelmet CaveCrawlerLeggings DiscipleBoots DiscipleChest
    DiscipleHelmet DiscipleLeggings EvocationBoots EvocationHelmet FrostRimeChest FrostRimeLeggings
    HewnBarkBoots HoneyBoots HoneyLeggings MushroomBoots MushroomChest MushroomHelmet MushroomLeggings
    MysticBoots MysticChest MysticHelmet MysticLeggings PhantomBoots PhantomChest PhantomHelmet
    PhantomLeggings RealmreacherBoots RealmreacherChest RealmreacherHelmet RealmreacherLeggings
    RedstoneBoots RedstoneChest RedstoneHelmet RedstoneLeggings ScampBoots ScampChest ScavengerLeggings
    StalwartBoots StalwartChest StalwartHelmet StalwartLeggings TimewornBoots TimewornChest
    UndauntedChest UndauntedHelmet VoyagerBoots VoyagerHelmet VoyagerLeggings WellspringBoots
    WellspringHelmet WolfclutchBoots WolfclutchChest WolfclutchLeggings
    HewnBarkChest HewnBarkHelmet HewnBarkLeggings HoneyChest HoneyHelmet ScampHelmet ScampLeggings
    ScavengerBoots ScavengerHelmet UndauntedBoots UndauntedLeggings VoyagerChest WellspringLeggings
    WolfclutchHelmet EvocationLeggings TimewornHelmet

    Artifact.BlizzardStaff Artifact.CarapaceOcarina Artifact.ConductiveBracelet Artifact.CorruptedSeeds
    Artifact.CreeperCandle Artifact.FightersFife Artifact.FireBracelet Artifact.FireworkQuiver
    Artifact.FlameQuiver Artifact.FlameSceptre Artifact.Grindstone Artifact.HasteMushroom
    Artifact.Honeypot Artifact.IronHideLute Artifact.LightningRod Artifact.MaimingMushroom
    Artifact.PoisonBracelet Artifact.PoisonQuiver Artifact.Powershaker Artifact.RallyingHorn
    Artifact.RedstoneMines Artifact.Satchel.Conductive Artifact.Satchel.Fire Artifact.Satchel.Freezing
    Artifact.Satchel.Poison Artifact.SmokeBomb Artifact.SoulHarvester Artifact.TotemOfCasting
    Artifact.TotemOfRegeneration Artifact.TotemOfShielding Artifact.WarBanner Artifact.WardingChimes
    Artifact.WarriorsDrums Artifact.WitchesBrew Artifact.CorruptedBeacon Artifact.FrostQuiver
    Artifact.DeathcapMushroom Artifact.LightningQuiver

    Talisman.AmmoCapacity Talisman.Brawling Talisman.HealthBoost Talisman.PotionCooldown
    Talisman.RangedBuff Talisman.SoulGather Talisman.Wolf
    """.split()
}
# Uniques' own IDs seen in real saves. Each is its base item's ID with _Unique1 (weapons) or _Unique (armor).
UNIQUE_IDS = {
    PREFIX + name
    for name in """
    Axe_Unique1 Claws_Unique1 Pickaxe_Unique1 Sabre_Unique1 Sword_Unique1 Trickbow_Unique1
    Bow_Unique1 Greatsword_Unique1 Mace_Unique1 Powerbow_Unique1 Rapier_Unique1 Sickles_Unique1
    Daggers_Unique1 HeavyCrossbow_Unique1
    CaveCrawlerChest_Unique CaveCrawlerHelmet_Unique StalwartBoots_Unique StalwartChest_Unique VoyagerLeggings_Unique
    HoneyBoots_Unique HoneyChest_Unique HoneyHelmet_Unique HoneyLeggings_Unique
    MysticBoots_Unique MysticChest_Unique MysticHelmet_Unique MysticLeggings_Unique
    RealmreacherBoots_Unique RealmreacherChest_Unique RealmreacherHelmet_Unique RealmreacherLeggings_Unique
    UndauntedBoots_Unique UndauntedChest_Unique UndauntedHelmet_Unique UndauntedLeggings_Unique
    """.split()
}
# What a save calls an item, where that isn't the name players see with the spaces taken out.
KNOWN_IDS = {
    "Battle Hammer": "Hammer",
    "Clobberer": "GiantClub",
    "Cookiecutter": "CurvedGreatsword",
    "Double Daggers": "Daggers",
    "Double Sickles": "Sickles",
    "Gauntlets": "Gauntlet",
    "Greataxe": "GreatAxe",
    "Longsword": "StraightSword",
    "Meat Cleaver": "Cleaver",
    "Riftslasher": "CurvedLongsword",
    "Tidal Sickle": "MoonSword",
    "Twilight Dagger": "Dagger",
    "Wolf Claws": "Claws",  # its Unique, the Sculker Claws, is saved as Claws_Unique1
    "Dual Crossbows": "DualCrossbow",
    "Battle Banner": "Artifact.WarBanner",
    "Blaze Bangle": "Artifact.FireBracelet",
    "Blight Bangle": "Artifact.PoisonBracelet",
    "Cinder Scepter": "Artifact.FlameSceptre",
    "Conductive Quiver": "Artifact.LightningQuiver",  # by its name, like the Freezing Quiver: it's the one quiver left
    "Death Cap Mushroom": "Artifact.DeathcapMushroom",
    "Echo Ocarina": "Artifact.CarapaceOcarina",
    "Electric Bangle": "Artifact.ConductiveBracelet",
    "Ender Fog": "Artifact.SmokeBomb",
    "Fighter's Flute": "Artifact.FightersFife",
    "Fighting Fungus": "Artifact.MaimingMushroom",
    "Firework Arrow": "Artifact.FireworkQuiver",
    "Flaming Quiver": "Artifact.FlameQuiver",
    "Freezing Quiver": "Artifact.FrostQuiver",  # by its name: the report that had it didn't say what the game calls it
    "Honey Dipper": "Artifact.Honeypot",
    "Humbling Horn": "Artifact.RallyingHorn",
    "Pouch of Ember": "Artifact.Satchel.Fire",
    "Pouch of Frost": "Artifact.Satchel.Freezing",
    "Pouch of Poison": "Artifact.Satchel.Poison",
    "Pouch of Thunder": "Artifact.Satchel.Conductive",
    "Redstone Mine Launcher": "Artifact.RedstoneMines",
    "Turtle Master's Mandolin": "Artifact.IronHideLute",
    "Venomous Quiver": "Artifact.PoisonQuiver",
    "Warrior Drums": "Artifact.WarriorsDrums",
    "Winter Staff": "Artifact.BlizzardStaff",
    "Witch Brew": "Artifact.WitchesBrew",
    # Talismans are saved by what they do, so the ones not seen yet are almost certainly guessed wrong.
    "Amethyst Lens": "Talisman.RangedBuff",
    "Fist of Iron": "Talisman.Brawling",
    "Glowstone Flask": "Talisman.PotionCooldown",
    "Sigil of Beeswax": "Talisman.HealthBoost",
    "Tasty Bone": "Talisman.Wolf",
    "Twig of Dark Oak": "Talisman.AmmoCapacity",
    "Twisted Tooth": "Talisman.SoulGather",
}
# Armor sets named differently in saves. Two come from their Uniques' IDs rather than from a report of the set
# itself: RealmreacherChest_Unique is the Sharpshooter Duster, the Unique Ranger Jacket, and UndauntedHelmet_Unique
# is the Dauntless Horns, the Unique Bounty Hunter Helmet. The set players see as Realmreacher is saved as Timeworn.
# Treehugger is by elimination: HewnBark is the one set name in saves left over, and Treehugger the one set.
SET_NAMES = {
    "Beekeeper": "Honey",
    "Bounty Hunter": "Undaunted",
    "Nomad": "Voyager",
    "Protector": "Stalwart",
    "Ranger": "Realmreacher",
    "Realmreacher": "Timeworn",
    "Sculk Digger": "CaveCrawler",
    "Sculker": "Scavenger",
    "Sifter": "Wellspring",
    "Sorcerer": "Evocation",
    "Steel Wool": "FrostRime",
    "Treehugger": "HewnBark",
    "Wolfpack": "Wolfclutch",
}
# Enchantment books seen in real saves, by the enchantment's name. They're listed so the editor can name them;
# it only offers to add one a hero already has.
BOOK_IDS = {
    "Ancient Alchemy": "SoulInfusedPotion",
    "Buddy Brew": "PotionSharing",
    "Dynamo": "Dynamo",
    "Ender Quiver": "ExpandedQuiver",
    "Fire Aspect": "FireAspect",
    "Frost Crescent": "FrostCrescent",
    "Piercing": "Piercing",
    "Poison Fog": "PoisonFog",
    "Ricochet": "Ricochet",
    "Shockwave": "Shockwave",
    "Somersault": "MultiRoll",
    "Springload": "SpringLoaded",
    "Tempo Theft": "TempoTheft",
    "Thundering": "Thundering",
}
# What a talisman does at each of its three levels, as a real save stores it: the effect is SW.Effect.<name>, its
# level templates are SW.EffectTemplate.<name>.I to .III, and these are the strengths. A talisman that isn't here
# can only be added without its effect, so the editor treats it as a guess even when its ID is known.
TALISMAN_LEVELS = {
    "Talisman.HealthBoost": ("HealthBoost", (1.2, 1.25, 1.35)),  # Sigil of Beeswax: +20 / 25 / 35% max health
}
# Armor slots as MetaBot names them, as the editor names them, and as armor IDs spell them.
SLOTS = {"Helmet": "Helmet", "Chest": "Chestplate", "Leggings": "Leggings", "Boots": "Boots"}
SLOT_WORDS = {"Helmet": "Helmet", "Chestplate": "Chest", "Leggings": "Leggings", "Boots": "Boots"}
RANGED_TYPES = {"Bow", "Crossbow"}
ENCHANT_SLOTS = {"Melee": "Melee", "Ranged": "Ranged", "Armor": "Armor", "Chest": "Chestplate"}
# In saves, but nobody has said what the game calls them (the names below come from the IDs).
EXTRA = [
    {"name": "Haste Mushroom", "kind": "Artifact", "id": PREFIX + "Artifact.HasteMushroom"},
]


class Tables(HTMLParser):
    """Collects the text of every table on a page: tables -> rows -> cells."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif self._cell is not None and tag in ("div", "p", "li", "br", "a"):
            self._cell.append(" ")  # keep "Melee" and "Ranged" in separate boxes apart

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row and self.tables:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def fetch_tables(page: str) -> list[list[list[str]]]:
    request = urllib.request.Request(BASE_URL + page, headers=HEADERS)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                parser = Tables()
                parser.feed(response.read().decode("utf-8"))
                return parser.tables
        except OSError:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"metabot.gg didn't answer for {page}")


def rows(tables: list[list[list[str]]], *headers: str) -> list[dict[str, str]]:
    """The rows of the first table whose header row starts with ``headers``, keyed by header."""
    for table in tables:
        names = [cell.upper() for cell in table[0]] if table else []
        if names[: len(headers)] == list(headers):
            return [dict(zip(names, row)) for row in table[1:] if len(row) == len(names)]
    raise RuntimeError(f"no table headed {headers}")


def pascal(name: str) -> str:
    return "".join(word[0].upper() + word[1:] for word in re.findall(r"[A-Za-z0-9]+", name.replace("'", "")))


def entry(name: str, kind: str, item_id: str, unique_suffix: str = "", **extra: str) -> dict:
    if name in KNOWN_IDS:
        item_id = PREFIX + KNOWN_IDS[name]
    made = {"name": name, "kind": kind, "id": item_id, "confirmed": item_id in CONFIRMED_IDS, **{k: v for k, v in extra.items() if v}}
    if unique_suffix and item_id + unique_suffix in UNIQUE_IDS:
        made["unique_id"] = item_id + unique_suffix
    if item_id[len(PREFIX):] in TALISMAN_LEVELS:
        effect, strengths = TALISMAN_LEVELS[item_id[len(PREFIX):]]
        made["levels"] = [
            {"effect": f"SW.Effect.{effect}", "intensity": strength, "template": f"SW.EffectTemplate.{effect}.{numeral}"}
            for numeral, strength in zip(("I", "II", "III"), strengths)
        ]
    return made


def main() -> None:
    pages = {}
    for page in PAGES:
        pages[page] = fetch_tables(page)
        time.sleep(1)  # be gentle

    items: dict[str, dict] = {}
    for row in rows(pages["uniques"], "ITEM", "TYPE", "BASE ITEM", "EFFECT"):
        unique, kind, base, effect = row["ITEM"], row["TYPE"], row["BASE ITEM"], row["EFFECT"]
        if kind in SLOTS:
            slot = SLOTS[kind]
            armor_set = base.rsplit(" ", 1)[0]  # "Sculk Digger Hood" is in the Sculk Digger set
            item_id = f"{PREFIX}{pascal(SET_NAMES.get(armor_set, armor_set))}{SLOT_WORDS[slot]}"
            items[base] = entry(base, "Armor", item_id, "_Unique", slot=slot, set=armor_set, unique=unique, unique_effect=effect)
        else:
            weapon = "Ranged" if kind in RANGED_TYPES else "Melee"
            items[base] = entry(base, weapon, PREFIX + pascal(base), "_Unique1", unique=unique, unique_effect=effect)
    for row in rows(pages["artifacts"], "ARTIFACT", "TYPE"):
        name = row["ARTIFACT"]
        items.setdefault(name, entry(name, "Artifact", f"{PREFIX}Artifact.{pascal(name)}"))
    for row in rows(pages["talismans"], "TALISMAN", "EFFECT AT LEVEL 3"):
        name, effect = row["TALISMAN"], row["EFFECT AT LEVEL 3"]
        items.setdefault(name, entry(name, "Talisman", f"{PREFIX}Talisman.{pascal(name)}", effect="" if effect == "—" else effect))
    for extra in EXTRA:
        items.setdefault(extra["name"], entry(extra["name"], extra["kind"], extra["id"], slot=extra.get("slot", ""), name_from_id=True))

    enchantments = [
        {
            "name": row["ENCHANTMENT"],
            "slots": [ENCHANT_SLOTS[word] for word in re.findall("|".join(ENCHANT_SLOTS), row["SLOT"])],  # "MeleeRanged"
            "category": row["CATEGORY"],
            "triggers": row["TRIGGERS ON"],
            "book": row.get("BOOK DROPS IN", ""),
            "tier3": row["AT TIER III"],
        }
        for row in rows(pages["enchantments"], "ENCHANTMENT", "SLOT", "CATEGORY")
    ]
    books = [
        {"name": name, "kind": BOOK, "id": f"{PREFIX}EnchantmentBook.{BOOK_IDS[name]}", "confirmed": True}
        for name in sorted(BOOK_IDS)
    ]
    for book in books:
        if book["name"] not in {enchantment["name"] for enchantment in enchantments}:
            print(f"warning: {book['name']} has a book in saves but isn't one of MetaBot's enchantments")

    catalog = sorted(items.values(), key=lambda e: (e["kind"], e["name"].lower())) + books
    by_id: dict[str, list[str]] = {}
    for item in catalog:
        by_id.setdefault(item["id"], []).append(item["name"])
    for item_id, same in by_id.items():
        if len(same) > 1:
            print(f"warning: {' and '.join(same)} would share the ID {item_id}; the editor offers only the first")
    for item_id in sorted(PREFIX + name for name in TALISMAN_LEVELS):
        if not any(item["id"] == item_id and "levels" in item for item in catalog):
            print(f"warning: {item_id} has its levels listed, but no talisman in the list has that ID")
    for item_id in sorted(CONFIRMED_IDS - set(by_id)):
        print(f"warning: {item_id} was seen in a save, but no item in the list has it")
    for item_id in sorted(UNIQUE_IDS - {item.get("unique_id") for item in catalog}):
        print(f"warning: {item_id} was seen in a save, but no item in the list has a Unique with that ID")
    sources = [BASE_URL + page for page in PAGES]
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "items.json").write_text(json.dumps({"sources": sources[:3], "items": catalog}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA / "enchantments.json").write_text(
        json.dumps({"sources": sources[3:], "enchantments": sorted(enchantments, key=lambda e: e["name"])}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    counts = {kind: sum(item["kind"] == kind for item in catalog) for kind in sorted({item["kind"] for item in catalog})}
    print(f"{len(catalog)} items ({sum(item['confirmed'] for item in catalog)} confirmed IDs, {sum('unique' in item for item in catalog)} with a Unique, "
          f"{sum('unique_id' in item for item in catalog)} of those with the Unique's own ID), {len(enchantments)} enchantments -> {DATA}\n{counts}")


if __name__ == "__main__":
    main()
