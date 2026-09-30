"""Builds dungeons2_editor/data/items.json: every Minecraft Dungeons II item on the Minecraft Wiki.

The game's own item list is in encrypted files, so each item's save ID is derived from its
in-game name, following the patterns seen in real saves:

    weapons     SW.Item.<Name>               (Sword, Bow, Longbow)
    armor       SW.Item.<Set><Slot>          (MysticHelmet is the Mystic Circlet)
    artifacts   SW.Item.Artifact.<Name>
    talismans   SW.Item.Talisman.<Name>

IDs seen in real saves are marked "confirmed"; the rest are best guesses. A Unique is its
base item at Unique rarity (the Oracle set is the Mystic set, the Emerald Hammer is a
Battle Hammer), so Uniques are listed on their base item.

Run from the repository root:  python tools/build_item_catalog.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://minecraft.wiki/api.php"
HEADERS = {"User-Agent": "Dungeons2SaveEditor/1.1 (item catalog builder)"}
OUT = Path(__file__).resolve().parent.parent / "dungeons2_editor" / "data" / "items.json"
CATEGORIES = {
    "Minecraft Dungeons II melee weapons": "Melee",
    "Minecraft Dungeons II ranged weapons": "Ranged",
    "Minecraft Dungeons II armor": "Armor",
    "Minecraft Dungeons II artifacts": "Artifact",
    "Minecraft Dungeons II talismans": "Talisman",
}
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
# Slot words as the game's own slot tags spell them (SW.ItemSlot.Equipment.Armor.Chest).
SLOT_WORDS = {"Helmet": "Helmet", "Chestplate": "Chest", "Leggings": "Leggings", "Boots": "Boots"}
SLOT_FIELDS = {"helmet": "Helmet", "chestplate": "Chestplate", "leggings": "Leggings", "boots": "Boots"}
# In saves but not on the wiki (yet).
EXTRA = [{"name": "Curved Greatsword", "kind": "Melee", "id": "SW.Item.CurvedGreatsword"}]


def api(**params) -> dict:
    params.update(format="json")
    request = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers=HEADERS)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except OSError:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"minecraft.wiki didn't answer: {params}")


def category_pages(category: str) -> list[str]:
    titles, extra = [], {}
    while True:
        data = api(action="query", list="categorymembers", cmtitle=f"Category:{category}", cmlimit="500", **extra)
        titles += [m["title"] for m in data["query"]["categorymembers"] if m["title"].startswith("Dungeons II:")]
        if "continue" not in data:
            return titles
        extra = {"cmcontinue": data["continue"]["cmcontinue"]}


def page_texts(titles: list[str]) -> dict[str, str]:
    texts = {}
    for start in range(0, len(titles), 50):
        data = api(action="query", prop="revisions", rvprop="content", rvslots="main", titles="|".join(titles[start:start + 50]))
        for page in data["query"]["pages"].values():
            if "revisions" in page:
                texts[page["title"]] = page["revisions"][0]["slots"]["main"]["*"]
        time.sleep(0.2)
    return texts


def infobox(text: str) -> dict[str, str]:
    start = text.find("{{Infobox Dungeons II item")
    if start < 0:
        return {}
    fields = {}
    for line in text[start:].splitlines()[1:]:
        match = re.match(r"\s*\|\s*([\w-]+)\s*=\s*(.*)", line)
        if match:
            fields[match.group(1).lower()] = re.sub(r"\}\}\s*$", "", match.group(2)).strip()
        if line.strip().endswith("}}") and not line.strip().startswith("|"):
            break
        if line.rstrip().endswith("}}") and match:
            break
    return fields


def pascal(name: str) -> str:
    return "".join(word[0].upper() + word[1:] for word in re.findall(r"[A-Za-z0-9]+", name.replace("'", "")))


def main() -> None:
    kinds, texts = {}, {}
    for category, kind in CATEGORIES.items():
        for title in category_pages(category):
            kinds.setdefault(title, kind)
    texts = page_texts(sorted(kinds))
    boxes = {title.removeprefix("Dungeons II:"): infobox(text) for title, text in texts.items()}

    items: dict[str, dict] = {}
    unique_of: dict[str, str] = {}  # base item name -> its Unique's name

    def add(name: str, kind: str, item_id: str, slot: str | None = None) -> None:
        item_id = KNOWN_IDS.get(name, item_id)
        entry = {"name": name, "kind": kind, "id": item_id, "confirmed": item_id in CONFIRMED_IDS}
        if slot:
            entry["slot"] = slot
        items.setdefault(name, entry)

    for name, box in boxes.items():
        kind = kinds["Dungeons II:" + name]
        item_type = box.get("type", "")
        unique = box.get("rarity", "").lower() == "unique"
        if item_type in ("Melee Weapon", "Ranged Weapon"):
            if unique:
                if box.get("variant"):
                    unique_of[box["variant"]] = name
            else:
                add(name, "Melee" if item_type == "Melee Weapon" else "Ranged", f"SW.Item.{pascal(name)}")
        elif item_type == "Armor" and box.get("slot") in SLOT_WORDS and box.get("set"):
            if unique:
                if box.get("variant"):
                    unique_of[box["variant"]] = name
            else:
                armor_set = SET_NAMES.get(box["set"], box["set"])
                add(name, "Armor", f"SW.Item.{pascal(armor_set)}{SLOT_WORDS[box['slot']]}", box["slot"])
        elif item_type == "Artifact":
            add(name, "Artifact", f"SW.Item.Artifact.{pascal(name)}")
        elif item_type == "Talisman":
            add(name, "Talisman", f"SW.Item.Talisman.{pascal(name)}")

    # Armor set pages fill in pieces without their own page, and pair each slot with its Unique.
    for name, box in boxes.items():
        if box.get("type") != "Armor Set" or box.get("rarity", "").lower() == "unique":
            continue
        armor_set = name.removesuffix(" Armor")
        unique_set = boxes.get(box.get("variant", ""), {})
        for field, slot in SLOT_FIELDS.items():
            piece = box.get(field)
            if not piece:
                continue
            add(piece, "Armor", f"SW.Item.{pascal(SET_NAMES.get(armor_set, armor_set))}{SLOT_WORDS[slot]}", slot)
            if unique_set.get(field):
                unique_of.setdefault(piece, unique_set[field])

    for entry in EXTRA:
        items.setdefault(entry["name"], {**entry, "confirmed": entry["id"] in CONFIRMED_IDS})
    for name, entry in items.items():
        if name in unique_of:
            entry["unique"] = unique_of[name]

    catalog = sorted(items.values(), key=lambda entry: (entry["kind"], entry["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = {kind: sum(entry["kind"] == kind for entry in catalog) for kind in sorted({e["kind"] for e in catalog})}
    print(f"{len(catalog)} items ({sum(e['confirmed'] for e in catalog)} confirmed IDs, "
          f"{sum('unique' in e for e in catalog)} with a Unique) -> {OUT}\n{counts}")


if __name__ == "__main__":
    main()
