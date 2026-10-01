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
is worked out from its name, following the patterns seen in real saves:

    weapons     SW.Item.<Name>               (Sword, Bow, Longbow)
    armor       SW.Item.<Set><Slot>          (MysticHelmet is the Mystic Circlet)
    artifacts   SW.Item.Artifact.<Name>
    talismans   SW.Item.Talisman.<Name>

IDs seen in real saves are marked "confirmed". The rest are best guesses, and plenty will be
wrong: the game's internal names don't always match the names players see (the Firework Arrow
is saved as FireworkQuiver, the Beekeeper set as Honey).

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

# IDs seen in real saves, and the in-game names they belong to where those differ from the ID.
CONFIRMED_IDS = {
    "SW.Item.Sword",
    "SW.Item.Bow",
    "SW.Item.Longbow",
    "SW.Item.CurvedGreatsword",
    "SW.Item.MysticHelmet",
    "SW.Item.HoneyLeggings",
    "SW.Item.HoneyBoots",
    "SW.Item.Artifact.FireworkQuiver",
}
KNOWN_IDS = {"Firework Arrow": "SW.Item.Artifact.FireworkQuiver"}
# Armor sets named differently in saves: the save's HoneyLeggings and HoneyBoots are the Beekeeper pieces.
SET_NAMES = {"Beekeeper": "Honey"}
# Armor slots as MetaBot names them, as the editor names them, and as armor IDs spell them
# (Helmet, Leggings and Boots as in the confirmed MysticHelmet, HoneyLeggings and HoneyBoots; Chest is a guess).
SLOTS = {"Helmet": "Helmet", "Chest": "Chestplate", "Leggings": "Leggings", "Boots": "Boots"}
SLOT_WORDS = {"Helmet": "Helmet", "Chestplate": "Chest", "Leggings": "Leggings", "Boots": "Boots"}
RANGED_TYPES = {"Bow", "Crossbow"}
ENCHANT_SLOTS = {"Melee": "Melee", "Ranged": "Ranged", "Armor": "Armor", "Chest": "Chestplate"}
# In saves, but under a name MetaBot doesn't list.
EXTRA = [{"name": "Curved Greatsword", "kind": "Melee", "id": "SW.Item.CurvedGreatsword"}]


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


def entry(name: str, kind: str, item_id: str, **extra: str) -> dict:
    item_id = KNOWN_IDS.get(name, item_id)
    return {"name": name, "kind": kind, "id": item_id, "confirmed": item_id in CONFIRMED_IDS, **{k: v for k, v in extra.items() if v}}


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
            item_id = f"SW.Item.{pascal(SET_NAMES.get(armor_set, armor_set))}{SLOT_WORDS[slot]}"
            items[base] = entry(base, "Armor", item_id, slot=slot, set=armor_set, unique=unique, unique_effect=effect)
        else:
            weapon = "Ranged" if kind in RANGED_TYPES else "Melee"
            items[base] = entry(base, weapon, f"SW.Item.{pascal(base)}", unique=unique, unique_effect=effect)
    for row in rows(pages["artifacts"], "ARTIFACT", "TYPE"):
        name = row["ARTIFACT"]
        items.setdefault(name, entry(name, "Artifact", f"SW.Item.Artifact.{pascal(name)}"))
    for row in rows(pages["talismans"], "TALISMAN", "EFFECT AT LEVEL 3"):
        name, effect = row["TALISMAN"], row["EFFECT AT LEVEL 3"]
        items.setdefault(name, entry(name, "Talisman", f"SW.Item.Talisman.{pascal(name)}", effect="" if effect == "—" else effect))
    for extra in EXTRA:
        items.setdefault(extra["name"], entry(extra["name"], extra["kind"], extra["id"]))

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

    catalog = sorted(items.values(), key=lambda e: (e["kind"], e["name"].lower()))
    by_id: dict[str, list[str]] = {}
    for item in catalog:
        by_id.setdefault(item["id"], []).append(item["name"])
    for item_id, same in by_id.items():
        if len(same) > 1:
            print(f"warning: {' and '.join(same)} would share the ID {item_id}; the editor offers only the first")
    sources = [BASE_URL + page for page in PAGES]
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "items.json").write_text(json.dumps({"sources": sources[:3], "items": catalog}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA / "enchantments.json").write_text(
        json.dumps({"sources": sources[3:], "enchantments": sorted(enchantments, key=lambda e: e["name"])}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    counts = {kind: sum(item["kind"] == kind for item in catalog) for kind in sorted({item["kind"] for item in catalog})}
    print(f"{len(catalog)} items ({sum(item['confirmed'] for item in catalog)} confirmed IDs, {sum('unique' in item for item in catalog)} with a Unique), "
          f"{len(enchantments)} enchantments -> {DATA}\n{counts}")


if __name__ == "__main__":
    main()
