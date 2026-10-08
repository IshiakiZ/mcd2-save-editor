"""The play recorder: writes down what the game saves while you play, so you (and the editor) can learn from it.

    Menu > Play recorder… in the editor, or:   python -m dungeons2_editor record

Leave it running while you play. It only ever reads. Every time the game saves, it reads the hero and settings
saves again (never the sign-in, entitlement or device-ID containers), works out what changed and writes that
down. Nothing leaves this PC. Each run's files go in the recordings folder, next to the backups, in a folder
named after the date and time:

    events.jsonl   one line per thing that happened: an item picked up, an item that changed (an enchantment, a
                   reroll, a power upgrade), a stat that moved, an item ID seen for the first time, a note you typed
    snapshots/     every version of each save the game wrote, as JSON, to look at closely afterwards
    summary.txt    written when the game closes and when you stop: new item IDs, what happened to items, how
                   the stats moved, world progress, and what it found for the Soul Storm check

A recording holds your whole hero save, version by version, so treat the folder like a backup: it's yours, and
not for posting anywhere whole.

While it runs you can type a note ("enchanted the sword with Fire Aspect"); the note goes into the timeline at
that moment. Run from a console, it also asks, when the game closes or you press Ctrl+C, what the game calls each
item the editor has no name for, and keeps the answers for the editor (item-names.json).

The Soul Storm check is for finding out how the game saves the Soulstorm Enhanced tag, which no save has shown
yet. It watches three things and says so at once when one turns up:

    an item saved with a mark or a field the editor has never seen on one (the tag itself, if it's kept on the item)
    anything anywhere in a save that mentions a storm, and every change to it (if it's kept somewhere else)
    an item with one more rolled effect than its rarity usually has, which is what a Soul Storm chest gives

At the end it asks, for each such item, whether the game shows Soulstorm Enhanced on it. An item that does and
one that doesn't, side by side as saved, is what shows where the tag lives.

It also tracks world progress: every quest and each of its tasks, minecart stations, doors, cutscenes, how much of
each area is explored, achievements, and anything else a save keeps about how far the hero has got. Each step
is written down as the game saves it, so the recordings show how the game itself moves a hero along, which is
what the editor would have to write to do the same.

    python -m dungeons2_editor record --atlas      (Make the map, in the window)

reads every recording made so far and writes world_progress_atlas.json next to them: every quest with its tasks
in order, every station, door, cutscene, area and achievement any save has shown.

And it tracks where things are. A save gives a door's exact position, and for each region a grid of the ground
the hero has explored (a square is 32 metres across). So every step is written down with the area the hero was
in and the middle of the ground explored since the save before: that is where a station, a cutscene or a quest
step was found, to within a few squares. --atlas puts all of it on a map: world_map.txt, and world_map.png when
Pillow is installed.

What it can say about things you may have missed is what a save gives away: a numbered door whose number is
skipped (rifts 1, 2 and 4 found means a 3 is out there), how many dungeon and rift entrances an area has in all
(MetaBot's count from the game files), quests you haven't started or finished, and ground you haven't explored
right next to ground you have, which the map marks. It can't see a chest or a secret you haven't touched: the
game writes those to a save only once you have, and where they are is in its encrypted files.
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import __version__, paths, saves, share_ids
from . import document as doc
from .hero import Hero, format_amount, game_item, is_hero_document, is_unique_version, items_by_identity
from .my_items import NAMES_FILE, load_names, save_names

DEFAULT_OUT = paths.data_dir() / "recordings"  # next to the backups, on this PC only
POLL = 1.0  # seconds between looks at the save folder
SETTLE = 0.7  # after the folder changes, wait this long before reading, so the game has finished writing
GAME_CHECK = 10.0  # seconds between checks for the game's process
LONG = 400  # characters of a value kept in an event; snapshots keep everything
MOST = 60  # changes listed per event
MOST_QUESTIONS = 8  # items the Soul Storm check asks about at the end

STORM = re.compile("storm", re.IGNORECASE)  # SoulStorm, Soulstorm, Storminator: however the game spells it
# The most rolled effects an item of each rarity usually has. A Soul Storm chest is said to give one more.
USUAL_MOST = {"Common": 0, "Rare": 1, "Special": 2, "Unique": 1}
# The editor's own check for an item saved with something it has never seen on one (Share item IDs uses it).
MARKED_ITEMS = share_ids._marked_items
AS_SAVED = share_ids._as_saved

WORTH_DOING = """Most useful things to do while this runs (any of them, in any order):
  - enchant an item at the Enchantsmith, and take an enchantment off again
  - pick up or buy items you haven't had before, talismans above all
  - reroll an effect and raise an item's power at the Blacksmith
  - salvage an item, and level up
  - play a Soul Storm, open its reward chests, and look at what you got: does a piece say Soulstorm Enhanced?
Type a note and press Enter whenever something happens that the save alone won't explain."""


def path_text(path: tuple) -> str:
    return "".join(f"[{part}]" if isinstance(part, int) else ("." if position else "") + str(part) for position, part in enumerate(path))


def compact(value: Any) -> Any:
    """A value as it goes into an event: whole if it's small, else cut short with its size."""
    if value is doc.MISSING:
        return "(not there)"
    text = json.dumps(value, ensure_ascii=False)
    return value if len(text) <= LONG else f"{text[:LONG]}... ({len(text)} characters)"


def changes(old: Any, new: Any) -> list[dict]:
    return [{"path": path_text(path), "old": compact(before), "new": compact(after)} for path, before, after in doc.diff(old, new)]


def standing(tag: str) -> str:
    """What the editor's item list knows about an ID: confirmed, a guess, unnamed or unknown."""
    known = game_item(tag)
    if known is None:
        return "unknown"
    if is_unique_version(tag):
        return "confirmed" if known.unique_id == tag else "guess"
    if not known.confirmed:
        return "guess"
    return "unnamed" if known.name_from_id else "confirmed"


def storm_mentions(document: Any) -> dict[str, Any]:
    """Everything in a save that mentions a storm, under a label that stays the same while lists grow and shift:

        a field whose name mentions one               -> "Where.It.Sits.SoulStormThing": what it holds
        an entry with a value that mentions one       -> "Where.It.Sits[] {Tag: SW.SoulStorm.X}": the whole entry
        a plain name in a list that mentions one      -> "Where.It.Sits[] SW.SoulStorm.X": True
    """
    found: dict[str, Any] = {}

    def walk(value: Any, where: str) -> None:
        if isinstance(value, dict):
            named = [key for key, inner in value.items() if isinstance(inner, str) and STORM.search(inner)]
            if named:
                found[f"{where} {{{', '.join(f'{key}: {value[key]}' for key in named)}}}"] = compact(value)
                return
            for key, inner in value.items():
                inside = f"{where}.{key}" if where else str(key)
                if STORM.search(str(key)):
                    found[inside] = compact(inner)
                else:
                    walk(inner, inside)
        elif isinstance(value, list):
            for inner in value:
                if isinstance(inner, str):
                    if STORM.search(inner):
                        found[f"{where}[] {inner}"] = True
                else:
                    walk(inner, where + "[]")

    walk(document, "")
    return found


LOUD_PROGRESS = ("quest ", "task ", "minecart station ", "door ", "cutscene ", "gimmick ", "progression ")  # said out loud as they happen
PLACED = ("quest ", "task ", "minecart station ", "cutscene ", "gimmick ", "actor ")  # what the atlas keeps a place for (doors have their own)
# Metres across one square of the grid a save keeps of explored ground. A region's corner is saved in metres and
# its size in squares, and nothing says how big a square is: at 32 every door in the saves falls inside its
# region, and at 16 or 64 half of them fall outside. The squares run down each column in turn (that order puts
# most doors on explored ground; row by row puts fewer there).
CELL = 32


def map_regions(document: Any) -> dict[str, dict]:
    """The grid of explored ground a save keeps for each region: its corner (metres), its size (squares) and the
    squares themselves, zero for one the hero hasn't been to."""
    body = document.get("CharacterSaveV1") if isinstance(document, dict) else None
    world = (body or {}).get("WorldExploration") or {}
    found = {}
    for area in (world.get("SavedFogOfWarExploration") or {}).get("Items") or []:
        corner, size = area.get("WorldPosition") or {}, area.get("Size") or {}
        found[str(area.get("Tag"))] = {"x": corner.get("X", 0), "y": corner.get("Y", 0), "cols": size.get("X", 0), "rows": size.get("Y", 0), "cells": list(area.get("Data") or [])}
    return found


def door_places(document: Any) -> dict[str, list[float]]:
    """Where each door a save lists is, in metres: the one thing on the map a save gives an exact position for."""
    body = document.get("CharacterSaveV1") if isinstance(document, dict) else None
    world = (body or {}).get("WorldExploration") or {}
    return {
        str(door.get("DoorId")): [round((door.get("Location") or {}).get(axis, 0) / 100, 1) for axis in ("X", "Y", "Z")]
        for door in world.get("DiscoveredDungeonDoors") or []
    }


def newly_explored(before: dict[str, dict], after: dict[str, dict]) -> dict | None:
    """Where the hero went between two saves: the region with the most squares explored since, and the middle of
    those squares in metres. None if no new ground was explored."""
    best = None
    for tag, region in after.items():
        old = (before.get(tag) or {}).get("cells") or []
        rows = region["rows"] or 1
        fresh = [index for index, cell in enumerate(region["cells"]) if cell and not (old[index] if index < len(old) else 0)]
        if fresh and (best is None or len(fresh) > best["squares"]):
            best = {
                "region": tag, "squares": len(fresh),
                "x": round(region["x"] + (sum(index // rows for index in fresh) / len(fresh) + 0.5) * CELL),
                "y": round(region["y"] + (sum(index % rows for index in fresh) / len(fresh) + 0.5) * CELL),
            }
    return best


def region_of(x: float, y: float, regions: dict[str, dict]) -> str | None:
    """The region a spot is in: the smallest one whose grid covers it (the camp and the caves sit inside the overworld's)."""
    inside = [(region["cols"] * region["rows"], tag) for tag, region in regions.items()
              if 0 <= (x - region["x"]) / CELL < region["cols"] and 0 <= (y - region["y"]) / CELL < region["rows"]]
    return min(inside)[1] if inside else None


def world_progress(document: Any) -> dict[str, Any]:
    """How far a hero has got, as its save tells it, flattened to {what: how it stands} so that two saves compare
    line by line: where the hero is, each quest and each of its tasks, every minecart station, door, cutscene and
    area found, each achievement, and whatever else the save keeps about progress."""
    body = document.get("CharacterSaveV1") if isinstance(document, dict) else None
    if not isinstance(body, dict):
        return {}
    found: dict[str, Any] = {}
    meta = body.get("MetaData") or {}
    for key in ("CurrentLocation", "CurrentDifficulty", "ReleaseToggles"):
        if key in meta:
            found[f"where {key}"] = meta[key]
    quests = body.get("quest") or {}
    if "FocusedQuestId" in quests:
        found["quest in focus"] = quests["FocusedQuestId"]
    for quest in quests.get("Quests") or []:
        found[f"quest {quest.get('QuestName')}"] = quest.get("State")
        for task in quest.get("TaskData") or []:
            partial = task.get("PartialProgress")
            found[f"task {task.get('TaskName')}"] = f"{task.get('State')}" + (f" ({partial})" if partial else "")
    world = body.get("WorldExploration") or {}
    for tag in world.get("DiscoveredMinecartStationTags") or []:
        found[f"minecart station {tag}"] = True
    if "LastMinecartStation" in world:
        found["last minecart station"] = world["LastMinecartStation"]
    for door in world.get("DiscoveredDungeonDoors") or []:
        found[f"door {door.get('DoorId')}"] = f"marker {door.get('MarkerType')}"
    for tag in world.get("SavedCutsceneTags") or []:
        found[f"cutscene {tag}"] = True
    for tag in world.get("ActivatedGimmickTags") or []:
        found[f"gimmick {tag}"] = True
    for area in (world.get("SavedFogOfWarExploration") or {}).get("Items") or []:
        cells = area.get("Data") or []
        found[f"explored {area.get('Tag')}"] = f"{sum(1 for cell in cells if cell)} of {len(cells)}"
    for actor in world.get("SavedActorStates") or []:
        path = str(actor.get("SoftObjectPath", "?"))
        found[f"actor {path.rsplit('/', 1)[-1][-90:]}"] = f"{actor.get('PreviousState')} then {actor.get('CurrentState')}"
    for entries in (body.get("Achievements") or {}).values():
        for name, entry in (entries or {}).items() if isinstance(entries, dict) else []:
            if isinstance(entry, dict):
                value = entry["bCompleted"] if "bCompleted" in entry else entry["Count"] if "Count" in entry else f"{len(entry.get('CollectedTags') or [])} collected"
                found[f"achievement {str(name).rsplit('.', 1)[-1]}"] = value
    for key, value in (body.get("Ability") or {}).items():
        if key == "Attributes":
            continue
        if isinstance(value, list) and all(isinstance(tag, str) for tag in value):
            for tag in value:
                found[f"progression {key} {tag}"] = True
        else:
            found[f"progression {key}"] = compact(value)
    for hint in (body.get("CollectionsStats") or {}).get("ShownHints") or []:
        if isinstance(hint, dict):
            found[f"hint {hint.get('Tag')}"] = hint.get("Count")
    return found


def progress_counts(progress: dict[str, Any]) -> str:
    """A hero's progress in a line: quests by how they stand, tasks done, and what's been found."""
    quests: dict[str, int] = {}
    for label, value in progress.items():
        if label.startswith("quest ") and label != "quest in focus":
            quests[str(value)] = quests.get(str(value), 0) + 1
    tasks = [value for label, value in progress.items() if label.startswith("task ")]
    counted = {kind: sum(1 for label in progress if label.startswith(kind + " ")) for kind in ("minecart station", "door", "cutscene")}
    return (
        f"quests: {', '.join(f'{count} {state.lower()}' for state, count in sorted(quests.items())) or 'none'}; "
        f"tasks done: {sum(1 for value in tasks if str(value).startswith('Completed'))} of {len(tasks)}; "
        f"{counted['minecart station']} minecart stations, {counted['door']} doors, {counted['cutscene']} cutscenes"
    )


def build_atlas(play: Path) -> dict[str, Any]:
    """Everything every recording under ``play`` has shown about world progress, in the order it was first seen:
    each quest with its tasks in the save's own order, the states it and they have been in and the order its
    tasks were completed in, and every station, door, cutscene, area, achievement and progression tag."""
    atlas: dict[str, Any] = {
        "snapshots": 0, "quests": {}, "minecart_stations": [], "last_minecart_station_values": [], "doors": {}, "cutscenes": [], "gimmicks": [],
        "areas": {}, "achievements": {}, "progression": {}, "locations": [], "hints": [], "quests_in_focus": [],
        # The map: each region's grid with every square any save shows explored, and where each thing was found,
        # by the ground explored in the save it first appeared in (things there from the first save have no place).
        "map": {"metres_per_square": CELL, "regions": {}}, "found_at": {},
    }
    earlier: tuple[dict[str, Any], dict[str, dict]] | None = None  # the save before: its progress and its grids

    def add(where: list, value: Any) -> None:
        if value is not None and value not in where:
            where.append(value)

    for path in sorted(Path(play).glob("*/snapshots/*.json"), key=lambda found: (found.parent.parent.name, found.name)):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        body = document.get("CharacterSaveV1") if isinstance(document, dict) else None
        if not isinstance(body, dict):
            continue
        atlas["snapshots"] += 1
        progress, regions = world_progress(document), map_regions(document)
        for tag, region in regions.items():
            merged = atlas["map"]["regions"].setdefault(tag, {**region, "cells": [0] * len(region["cells"])})
            if len(merged["cells"]) == len(region["cells"]):
                merged["cells"] = [old | new for old, new in zip(merged["cells"], region["cells"])]
        if earlier is not None:
            near = newly_explored(earlier[1], regions)
            for label in progress:
                first = label not in earlier[0] or (label.startswith(("quest ", "task ")) and str(progress[label]).startswith("Completed") and not str(earlier[0][label]).startswith("Completed"))
                if first and label.startswith(PLACED) and label != "quest in focus":
                    atlas["found_at"].setdefault(label, {"area": progress.get("where CurrentLocation"), "near": [near["x"], near["y"]] if near else None,
                                                         "region": near["region"] if near else None, "recording": path.parent.parent.name, "snapshot": path.name})
        earlier = (progress, regions)
        atlas["might_be_missing"] = might_be_missing(progress, regions)  # as the newest save has it
        add(atlas["locations"], (body.get("MetaData") or {}).get("CurrentLocation"))
        quests = body.get("quest") or {}
        add(atlas["quests_in_focus"], quests.get("FocusedQuestId"))
        for quest in quests.get("Quests") or []:
            entry = atlas["quests"].setdefault(str(quest.get("QuestName")), {"states": [], "tasks": [], "task_states": {}, "completed_in_order": []})
            add(entry["states"], quest.get("State"))
            for task in quest.get("TaskData") or []:
                name = str(task.get("TaskName"))
                add(entry["tasks"], name)
                partial = task.get("PartialProgress")
                add(entry["task_states"].setdefault(name, []), f"{task.get('State')}" + (f" ({partial})" if partial else ""))
                if task.get("State") == "Completed":
                    add(entry["completed_in_order"], name)
        world = body.get("WorldExploration") or {}
        for tag in world.get("DiscoveredMinecartStationTags") or []:
            add(atlas["minecart_stations"], tag)
        add(atlas["last_minecart_station_values"], world.get("LastMinecartStation"))
        for door in world.get("DiscoveredDungeonDoors") or []:
            place = door_places({"CharacterSaveV1": {"WorldExploration": {"DiscoveredDungeonDoors": [door]}}})[str(door.get("DoorId"))]
            atlas["doors"].setdefault(str(door.get("DoorId")), {"metres": place, "region": region_of(place[0], place[1], regions), **{key: value for key, value in door.items() if key != "DoorId"}})
        for tag in world.get("SavedCutsceneTags") or []:
            add(atlas["cutscenes"], tag)
        for tag in world.get("ActivatedGimmickTags") or []:
            add(atlas["gimmicks"], tag)
        for area in (world.get("SavedFogOfWarExploration") or {}).get("Items") or []:
            cells = area.get("Data") or []
            seen = atlas["areas"].setdefault(str(area.get("Tag")), {"cells": len(cells), "most_explored": 0, "WorldPosition": area.get("WorldPosition"), "Size": area.get("Size")})
            seen["most_explored"] = max(seen["most_explored"], sum(1 for cell in cells if cell))
        for group, entries in (body.get("Achievements") or {}).items():
            for name, entry in (entries or {}).items() if isinstance(entries, dict) else []:
                add(atlas["achievements"].setdefault(group, []), name)
        for key, value in (body.get("Ability") or {}).items():
            if key != "Attributes":
                for tag in value if isinstance(value, list) else [value]:
                    add(atlas["progression"].setdefault(key, []), tag if isinstance(tag, (str, int, float, bool)) else json.dumps(tag, sort_keys=True))
        for hint in (body.get("CollectionsStats") or {}).get("ShownHints") or []:
            add(atlas["hints"], hint.get("Tag") if isinstance(hint, dict) else None)
    return atlas


# How many entrances each area has, from MetaBot's Overworld map (https://metabot.gg/en/minecraft-dungeons-2/map,
# read from the game's files, build 1.1.1.0): (the area's name in the game, dungeon entrances, rifts). Only the
# areas whose save names are certain are here: the spider caves are in Howling Woods and in the save's ForestA1,
# and the plains the game starts in are PlainsA1.
AREA_TOTALS = {"PlainsA1": ("Rainy Plains", 9, 10), "ForestA1": ("Howling Woods", 12, 12)}
STATIONS_IN_ALL = 19  # minecart stations on the same map
_NUMBERED = re.compile(r"SW\.Doorway\.(\w+)\.(Dungeon|Rift)\.(\d+)$")


def frontier(region: dict) -> list[int]:
    """The squares of a region the hero hasn't explored that touch one it has: the ground right next to where
    it has been, which is where something walked past would be."""
    cols, rows, cells = region["cols"], region["rows"], region["cells"]
    edge = []
    for index, cell in enumerate(cells):
        if not cell:
            col, row = index // rows, index % rows
            around = [(col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1)]
            if any(0 <= c < cols and 0 <= r < rows and cells[c * rows + r] for c, r in around):
                edge.append(index)
    return edge


def might_be_missing(progress: dict[str, Any], regions: dict[str, dict]) -> list[str]:
    """What a hero may have missed, as far as its save shows: doors whose numbers are skipped or short of the
    area's count, minecart stations, quests not started or not finished, and unexplored ground beside explored."""
    lines = []
    numbered: dict[tuple[str, str], list[int]] = {}
    for label in progress:
        match = _NUMBERED.match(label[5:]) if label.startswith("door ") else None
        if match:
            numbered.setdefault((match.group(1), match.group(2)), []).append(int(match.group(3)))
    for (area, kind), found in sorted(numbered.items()):
        found = sorted(set(found))
        name, dungeons, rifts = AREA_TOTALS.get(area, (area, None, None))
        total = dungeons if kind == "Dungeon" else rifts
        skipped = [number for number in range(1, max(found) + 1) if number not in found]
        line = f"{name}: {len(found)} {kind.lower()} entrance{'s' if len(found) != 1 else ''} found" + (f" of {total}" if total else "")
        if skipped:
            line += f"; not found yet: number{'s' if len(skipped) != 1 else ''} {', '.join(map(str, skipped))}" + (f", and {total - max(found)} more above {max(found)}" if total and total > max(found) else "")
        elif total and total > len(found):
            line += f"; {total - len(found)} more to find"
        lines.append(line)
    stations = sum(1 for label in progress if label.startswith("minecart station "))
    lines.append(f"Minecart stations: {stations} found of {STATIONS_IN_ALL}")
    for label, state in sorted(progress.items()):
        if label.startswith("quest ") and label != "quest in focus" and state in ("Available", "Active"):
            name = label[6:]
            tasks = [value for task, value in progress.items() if task.startswith(f"task {name}_")]
            left = sum(1 for value in tasks if not str(value).startswith("Completed"))
            lines.append(f"Quest {name}: " + ("not started" if state == "Available" else f"{left} of {len(tasks)} steps left"))
    for tag, region in regions.items():
        explored, edge = sum(1 for cell in region["cells"] if cell), len(frontier(region))
        if edge:
            lines.append(f"{tag}: {edge} unexplored square{'s' if edge != 1 else ''} right next to the {explored} you've explored (marked on the map)")
    return lines


def text_map(atlas: dict[str, Any]) -> str:
    """The atlas as a map you can read in a text file: each region's grid, north at the top as the save has it
    (# explored, . not), with a letter on each door's square and a number on each place something else was found."""
    lines = [f"World map from {atlas['snapshots']} saves. One square is {CELL} metres. # explored, ? not explored but right next to it, . not yet.", ""]
    if atlas.get("might_be_missing"):
        lines += ["What you may have missed, as far as a save shows it:"] + [f"  {line}" for line in atlas["might_be_missing"]] + [""]
    marks = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    for tag, region in atlas["map"]["regions"].items():
        cols, rows = region["cols"], region["rows"]
        edge = set(frontier(region))
        grid = [["#" if region["cells"][col * rows + row] else "?" if col * rows + row in edge else "." for col in range(cols)] for row in range(rows)]
        legend = []

        def put(x: float, y: float, mark: str) -> bool:
            col, row = int((x - region["x"]) // CELL), int((y - region["y"]) // CELL)
            if 0 <= col < cols and 0 <= row < rows:
                grid[row][col] = mark
                return True
            return False

        doors = [(name, door) for name, door in atlas["doors"].items() if door.get("region") == tag]
        for number, (name, door) in enumerate(doors):
            mark = marks[number % len(marks)]
            if put(door["metres"][0], door["metres"][1], mark):
                legend.append(f"  {mark}  {name}  at {door['metres'][0]:.0f}, {door['metres'][1]:.0f}")
        found = [(label, place) for label, place in atlas["found_at"].items() if place.get("region") == tag and place.get("near") and not label.startswith(("task ", "actor "))]
        for number, (label, place) in enumerate(found, start=1):
            mark = str(number % 10)
            if put(place["near"][0], place["near"][1], mark):
                legend.append(f"  {mark}  {label}  near {place['near'][0]}, {place['near'][1]}")
        explored = sum(1 for cell in region["cells"] if cell)
        lines += [f"{tag}  (corner {region['x']}, {region['y']}; {cols} by {rows} squares; {explored} explored)"] + ["  " + "".join(row) for row in grid] + legend + [""]
    return "\n".join(lines)


def picture_map(atlas: dict[str, Any], target: Path) -> bool:
    """The same map as a picture, if Pillow is installed: explored ground lighter, doors as orange dots with their
    names, and a blue dot where anything else was found. False when it can't be drawn."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    regions = atlas["map"]["regions"]
    if not regions:
        return False
    scale, gap, top = 14, 40, 26  # pixels to a square, between regions, and above each for its name
    order = sorted(regions.items(), key=lambda pair: -pair[1]["cols"] * pair[1]["rows"])
    width = max(region["cols"] for _tag, region in order) * scale + 2 * gap + 360
    height = sum(max(region["rows"] * scale, 40 * 13) + gap + top for _tag, region in order) + gap  # room for the names beside a small grid
    image = Image.new("RGB", (width, height), "#0d1a24")
    draw = ImageDraw.Draw(image)
    y0 = gap
    for tag, region in order:
        cols, rows = region["cols"], region["rows"]
        draw.text((gap, y0), f"{tag}   {sum(1 for cell in region['cells'] if cell)} of {cols * rows} squares explored", fill="#d7e3ea")
        y0 += top
        edge = set(frontier(region))
        for col in range(cols):
            for row in range(rows):
                shade = "#5d8a66" if region["cells"][col * rows + row] else "#3c5f78" if col * rows + row in edge else "#16303f"
                draw.rectangle([gap + col * scale, y0 + row * scale, gap + (col + 1) * scale - 2, y0 + (row + 1) * scale - 2], fill=shade)

        def spot(x: float, y: float) -> tuple[float, float] | None:
            col, row = (x - region["x"]) / CELL, (y - region["y"]) / CELL
            return (gap + col * scale, y0 + row * scale) if 0 <= col < cols and 0 <= row < rows else None

        labels = []
        for name, door in atlas["doors"].items():
            at = spot(door["metres"][0], door["metres"][1]) if door.get("region") == tag else None
            if at:
                draw.ellipse([at[0] - 4, at[1] - 4, at[0] + 4, at[1] + 4], fill="#ff9b3d", outline="#1a0f05")
                labels.append((at, name.replace("SW.Doorway.", ""), "#ffc58f"))
        for label, place in atlas["found_at"].items():
            if place.get("region") == tag and place.get("near") and not label.startswith(("task ", "actor ")):
                at = spot(place["near"][0], place["near"][1])
                if at:
                    draw.ellipse([at[0] - 4, at[1] - 4, at[0] + 4, at[1] + 4], fill="#4cc3ff", outline="#04141d")
                    labels.append((at, label.replace("SW.MinecartStation.", "").replace("SW.UI.Cutscene.", ""), "#a8e1ff"))
        side = gap + cols * scale + 24  # names go in a column beside the grid, each joined to its dot
        for number, (at, name, colour) in enumerate(sorted(labels, key=lambda entry: entry[0][1])):
            line_y = y0 + number * 13
            if line_y < y0 + max(rows * scale, len(labels) * 13):
                draw.line([at, (side - 4, line_y + 6)], fill="#33505f")
                draw.text((side, line_y), name[:52], fill=colour)
        y0 += max(rows * scale, len(labels) * 13) + gap
    image.crop((0, 0, width, min(height, y0 + gap))).save(target)
    return True


def rolled_effects(item: Any) -> list[str]:
    """The effects the game rolled on an item, by their templates without the SW.EffectTemplate. in front."""
    found = []
    for batch in item.data.get("Effects") or []:
        if isinstance(batch, dict) and str(batch.get("TypeTag", "")).endswith(".Rerollable"):
            for effect in batch.get("EffectsInThisBatch") or []:
                template = str(((effect or {}).get("GeneratorData") or {}).get("GeneratorParentTemplate", "?"))
                found.append(template.split(".", 2)[2] if template.count(".") > 1 else template)
    return found


def one_more_than_usual(item: Any) -> bool:
    """Whether an item has more rolled effects than its rarity usually gets: what a Soul Storm chest is said to give."""
    return not item.is_cosmetic and item.rarity in USUAL_MOST and len(rolled_effects(item)) > USUAL_MOST[item.rarity]


def game_version() -> str | None:
    """The installed game's version, where Windows keeps it: the Xbox app's copy is a package, and the name
    Windows files it under carries the version (Microsoft.MinecraftDungeons2_1.1.1.0_x64__...). None for
    Steam's copy, and anywhere but Windows."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        packages = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, packages) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                name = winreg.EnumKey(key, index)
                if name.startswith("Microsoft.MinecraftDungeons2_"):
                    return name.split("_")[1]
    except OSError:
        pass
    return None


class Recorder:
    """Watches one save folder and writes down what changes in it. It never writes to that folder."""

    def __init__(self, profile: Path, out: Path, say: Callable[[str], None] = print, clock: Callable[[], float] = time.time):
        self.profile = Path(profile)
        self.out = Path(out)
        self.say = say
        self.clock = clock
        self.started = clock()
        (self.out / "snapshots").mkdir(parents=True, exist_ok=True)
        self.events_file = open(self.out / "events.jsonl", "a", encoding="utf-8")
        self.log: list[dict] = []
        self.last: dict[str, tuple[bytes, Any]] = {}  # container -> its bytes and document as last read
        self.ids: dict[str, str] = {}  # every item ID seen -> what the editor knew about it when first seen
        self.at_start: set[str] = set()
        self.retry = False  # a save couldn't be read (caught mid-write): look again even if nothing else changes
        self.snapshots = 0
        self.game: list[str] | None = None
        # The Soul Storm check: what each save says about storms, and the items worth asking about, by (container,
        # the item's identity).
        self.storms: dict[str, dict[str, Any]] = {}
        self.marked: dict[tuple, dict] = {}  # items saved with a mark or a field the editor doesn't know
        self.extra: dict[tuple, dict] = {}  # items with one more rolled effect than their rarity usually has
        self.storm_answers: dict[tuple, str] = {}  # whether the game shows Soulstorm Enhanced on one, as you said
        self.progress: dict[str, dict[str, Any]] = {}  # each hero's world progress as last read
        self.regions: dict[str, dict[str, dict]] = {}  # and its grids of explored ground

    # ------------------------------------------------------------------ writing things down

    def event(self, kind: str, line: str | None = None, **details: Any) -> None:
        record = {"time": datetime.fromtimestamp(self.clock()).isoformat(timespec="seconds"), "after": round(self.clock() - self.started, 1), "kind": kind, **details}
        self.events_file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self.events_file.flush()
        self.log.append(record)
        if line:
            self.say(f"{record['time'][11:]}  {line}")

    def note(self, text: str) -> None:
        self.event("note", f"note: {text}", text=text)

    def _snapshot(self, container: saves.Container) -> str:
        self.snapshots += 1
        name = f"{self.snapshots:04d}_{container.name[:18]}_rev{container.entry.revision}.json"
        (self.out / "snapshots" / name).write_text(json.dumps(container.decoded.document, ensure_ascii=False), encoding="utf-8")
        return name

    # ------------------------------------------------------------------ looking

    def begin(self, version: str | None = None) -> None:
        self.event(
            "session_start",
            f"Recording {self.profile}",
            editor=__version__,
            game_version=version,
            layout=saves.layout_of(self.profile),
            folder=str(self.profile),
        )
        self.look()
        self.at_start = set(self.ids)

    def look(self) -> bool:
        """Read the saves again and write down what changed. False if one couldn't be read (try again soon)."""
        try:
            profile = saves.SaveProfile(self.profile)
        except Exception as exc:  # the game is in the middle of writing
            self.retry = True
            self.event("unreadable", why=str(exc))
            return False
        self.retry = False
        for container in profile.containers:
            if container.kind is saves.Kind.UNSUPPORTED and container.note.startswith("Could not be read"):
                self.retry = True
                continue
            if container.decoded is None or container.blob_name is None:
                continue  # sign-in and device containers, and anything that isn't a save document
            raw = container.blobs[container.blob_name]
            before = self.last.get(container.name)
            if before is not None and before[0] == raw:
                continue
            file = self._snapshot(container)
            document = container.decoded.document
            what = "hero" if is_hero_document(document) else "settings"
            if before is None:
                self._first_look(container, what, file)
            else:
                self.event("save_written", f"the game saved {container.label} (revision {container.entry.revision})", container=container.name, what=what, revision=container.entry.revision, size=container.entry.size, snapshot=file)
                (self._hero_changed if what == "hero" else self._other_changed)(container.name, before[1], document)
            self.last[container.name] = (raw, document)
        return not self.retry

    def _first_look(self, container: saves.Container, what: str, file: str) -> None:
        document = container.decoded.document
        details: dict[str, Any] = {"container": container.name, "what": what, "revision": container.entry.revision, "size": container.entry.size, "snapshot": file}
        line = f"{container.label}: revision {container.entry.revision}"
        if what == "hero":
            hero = Hero(document)
            details.update(
                serialize_meta=document.get("SerializeMeta"),
                metadata=hero.metadata,
                stats={a["AttributeName"]: a.get("CurrentValue") for a in hero.attributes()},
                items=[{"id": item.tag, "rarity": item.rarity, "power": item.power, "where": item.where, "effects": len(item.data.get("Effects") or [])} for item in hero.items()],
            )
            line += f", level {hero.level}, {len(hero.items())} items"
            self._ids(hero, quiet=True)
            details["ids"] = dict(sorted(self.ids.items()))
        self.event("baseline", line, **details)
        if what == "hero":
            self._storm_items(container.name, Hero(document), new=set())
            self._world_progress(container.name, document)
        self._storm_mentions(container.name, document)

    def _ids(self, hero: Hero, quiet: bool = False) -> None:
        for tag in sorted(hero.seen_item_types()):
            if tag not in self.ids:
                self.ids[tag] = standing(tag)
                if not quiet:
                    known = game_item(tag)
                    name = (known.unique if is_unique_version(tag) else known.name) if known is not None else None
                    self.event("new_id", f"NEW ITEM ID: {tag}  ({self.ids[tag]}{', ' + name if name else ''})", id=tag, editor=self.ids[tag], name=name)

    def _hero_changed(self, container: str, old: dict, new: dict) -> None:
        before, after = Hero(old), Hero(new)
        for section in ("SerializeMeta",):
            found = changes(old.get(section), new.get(section))
            if found:
                self.event("format_changed", "THE SAVE FORMAT CHANGED: the game was probably updated", container=container, changes=found)
        found = changes(before.metadata, after.metadata)
        if found:
            self.event("metadata", container=container, changes=found)
        old_stats = {a["AttributeName"]: a.get("CurrentValue") for a in before.attributes()}
        for attribute in after.attributes():
            name, value = attribute["AttributeName"], attribute.get("CurrentValue")
            if old_stats.get(name, doc.MISSING) != value:
                was = old_stats.get(name)
                self.event("stat", f"{name}: {format_amount(was)} -> {format_amount(value)}", container=container, stat=name, old=was, new=value)
        old_items, new_items = items_by_identity(before), items_by_identity(after)
        for key, item in new_items.items():
            earlier = old_items.get(key)
            if earlier is None:
                more = f", {len(rolled_effects(item))} rolled effects (one more than usual)" if one_more_than_usual(item) else ""
                self.event("item_added", f"new item: {item.name}  [{item.tag}]  {item.rarity}, power {format_amount(item.power)}{more}", container=container, id=item.tag, name=item.name, rarity=item.rarity, power=item.power, where=item.where, entry=item.entry)
                continue
            found = changes(earlier.entry, item.entry)
            if found:
                paths = ", ".join(sorted({change["path"].split("[")[0] for change in found}))
                self.event("item_changed", f"{item.name} changed: {paths}", container=container, id=item.tag, name=item.name, changes=found[:MOST], count=len(found))
        for key, item in old_items.items():
            if key not in new_items:
                self.event("item_removed", f"item gone: {item.name}  [{item.tag}]", container=container, id=item.tag, name=item.name, rarity=item.rarity, power=item.power)
        self._ids(after)
        self._storm_items(container, after, new=set(new_items) - set(old_items))
        self._storm_mentions(container, new)
        self._world_progress(container, new)
        handled = {"MetaData", "Inventory"}
        for section in after.body:
            if section in handled:
                continue
            old_part, new_part = before.body.get(section, doc.MISSING), after.body.get(section, doc.MISSING)
            if section == "Ability":  # its attributes are the stats above
                old_part = {k: v for k, v in old_part.items() if k != "Attributes"} if isinstance(old_part, dict) else old_part
                new_part = {k: v for k, v in new_part.items() if k != "Attributes"} if isinstance(new_part, dict) else new_part
            found = changes(old_part, new_part)
            if found:
                self.event("section_changed", container=container, section=section, changes=found[:MOST], count=len(found))

    def _other_changed(self, container: str, old: Any, new: Any) -> None:
        found = changes(old, new)
        if found:
            self.event("settings_changed", container=container, changes=found[:MOST], count=len(found))
        self._storm_mentions(container, new)

    # ------------------------------------------------------------------ world progress

    def _world_progress(self, container: str, document: Any) -> None:
        """Write down where a hero stands the first time its save is read, and every step it takes after that:
        a quest or a task changing state, a station, door or cutscene found, and the quieter things too (areas
        explored, counters, where the hero is), which go in the file without a line on the screen."""
        now, regions = world_progress(document), map_regions(document)
        before, grids = self.progress.get(container), self.regions.get(container, {})
        self.progress[container], self.regions[container] = now, regions
        if before is None:
            self.event("progress_baseline", f"World progress: {progress_counts(now)}", container=container, progress=now, doors=door_places(document))
            return
        # Where it happened: the area the hero is in, and the middle of the ground explored since the last save.
        # A door has its own position in the save, to the metre.
        area, near, doors = now.get("where CurrentLocation"), newly_explored(grids, regions), door_places(document)
        for label in sorted(set(before) | set(now)):
            old, new = before.get(label, doc.MISSING), now.get(label, doc.MISSING)
            if old != new:
                was = "(not there)" if old is doc.MISSING else old
                at = doors.get(label[5:]) if label.startswith("door ") else None
                where = f"at {at[0]:.0f}, {at[1]:.0f}" if at else f"in {area}" + (f", near {near['x']}, {near['y']}" if near else "")
                line = f"PROGRESS: {label}: {was} -> {'(gone)' if new is doc.MISSING else new}  [{where}]" if label.startswith(LOUD_PROGRESS) else None
                self.event("progress", line, container=container, what=label, old=compact(old), new=compact(new), area=area, near=near, at=at)

    # ------------------------------------------------------------------ the Soul Storm check

    def _storm_mentions(self, container: str, document: Any) -> None:
        """Write down what a save says about storms the first time it's read, and every change after that."""
        now = storm_mentions(document)
        before = self.storms.get(container)
        self.storms[container] = now
        if before is None:
            if now:
                self.event("storm_baseline", f"Soul Storm check: {len(now)} place(s) in this save mention a storm", container=container, mentions=now)
            return
        for label in sorted(set(before) | set(now)):
            old, new = before.get(label, doc.MISSING), now.get(label, doc.MISSING)
            if old != new:
                self.event("storm", f"SOUL STORM IN THE SAVE: {label}: {json.dumps(compact(old), ensure_ascii=False)} -> {json.dumps(compact(new), ensure_ascii=False)}", container=container, where=label, old=compact(old), new=compact(new))

    def _storm_items(self, container: str, hero: Hero, new: set) -> None:
        """Keep track of the items a Soul Storm might have to do with: one saved with something the editor has
        never seen on an item, and one with a rolled effect more than usual. ``new`` holds the identities of the
        items that have just arrived."""
        items = items_by_identity(hero)
        by_entry = {id(item.entry): key for key, item in items.items()}
        here = {(container, key) for key in items}
        for known in (self.marked, self.extra):
            for key in [key for key in known if key[0] == container and key not in here]:
                known[key]["gone"] = True  # salvaged, sold or dropped since; what it looked like is kept
        for item, news in MARKED_ITEMS([hero]) if MARKED_ITEMS is not None else []:
            key = (container, by_entry.get(id(item.entry)))
            if self.marked.get(key, {}).get("news") != news:
                self.marked[key] = self._about(item, key[1] in new, news=news)
                self.event("marked_item", f"AN ITEM SAVED WITH SOMETHING THE EDITOR HASN'T SEEN: {item.name}  [{item.tag}]: {', '.join(news)}", container=container, **self.marked[key])
        for identity, item in items.items():
            key = (container, identity)
            if one_more_than_usual(item) and key not in self.extra:
                self.extra[key] = self._about(item, identity in new)
                if identity in new:
                    self.event("extra_effect", container=container, **self.extra[key])

    @staticmethod
    def _about(item: Any, new: bool, **more: Any) -> dict:
        return {
            "id": item.tag, "name": item.name, "rarity": item.rarity, "power": item.power, "rolled": rolled_effects(item),
            "marks": list(item.data.get("DynamicPropertyTags") or []), "new": new, "as_saved": AS_SAVED(item) if AS_SAVED is not None else item.entry, **more,
        }

    def storm_questions(self) -> list[tuple[tuple, dict]]:
        """The items to ask about at the end, the ones that arrived while recording first: does the game show
        Soulstorm Enhanced on it? One that's gone, or already answered, isn't asked about."""
        both = {**self.extra, **self.marked}
        open_ones = [(key, about) for key, about in both.items() if key not in self.storm_answers and not about.get("gone")]
        return sorted(open_ones, key=lambda pair: not pair[1]["new"])[:MOST_QUESTIONS]

    def ask_storm(self, ask: Callable[[str], str | None]) -> dict[tuple, str]:
        """Ask whether the game shows Soulstorm Enhanced on each item a Soul Storm might have to do with, and
        write the answers down next to how the item is saved."""
        asking = self.storm_questions()
        given: dict[tuple, str] = {}
        if asking:
            self.say(
                f"\nSoul Storm check: {len(asking)} item(s) here are saved with something new, or have one more effect than usual. "
                "Does the game show Soulstorm Enhanced on them? Type y or n for each, or just press Enter to skip."
            )
        for key, about in asking:
            answer = ask(f"  {about['name']} ({about['rarity']}, power {format_amount(about['power'])}, effects: {', '.join(about['rolled']) or 'none'}) = ")
            if answer is None:
                break
            said = answer.strip().lower()
            if said:
                given[key] = "yes" if said in ("y", "yes") else "no" if said in ("n", "no") else answer.strip()
                self.storm_answers[key] = given[key]
                self.event("storm_answer", container=key[0], shows_soulstorm_enhanced=given[key], **about)
        return given

    def check_game(self, running: list[str]) -> bool:
        """Note the game starting or closing. True when it has just closed."""
        closed = bool(self.game) and not running
        if self.game is None or bool(self.game) != bool(running):
            self.event("game", "the game is running" if running else ("the game closed" if self.game else "the game isn't running yet"), running=running)
        self.game = running
        return closed

    # ------------------------------------------------------------------ afterwards

    def nameless(self) -> list[str]:
        """Item IDs in the saves that the editor has no name for."""
        return sorted(tag for tag, known in self.ids.items() if known in ("unknown", "unnamed") and ".Cosmetic." not in tag)

    def summary(self) -> str:
        lines = [f"Play recording, {datetime.fromtimestamp(self.started):%Y-%m-%d %H:%M} to {datetime.fromtimestamp(self.clock()):%H:%M}", f"Save folder: {self.profile}", ""]
        written = [e for e in self.log if e["kind"] == "save_written"]
        lines.append(f"The game saved {len(written)} time(s); {self.snapshots} snapshot(s) kept.")
        new = sorted(tag for tag in self.ids if tag not in self.at_start)
        lines += ["", f"Item IDs first seen while recording ({len(new)}):"] + [f"  {tag}  ({self.ids[tag]})" for tag in new]
        nameless = [tag for tag in self.nameless()]
        lines += ["", f"Item IDs the editor has no name for ({len(nameless)}):"] + [f"  {tag}" for tag in nameless]
        guesses = sorted(tag for tag, known in self.ids.items() if known == "guess")
        lines += ["", f"Item IDs that confirm one of the editor's guesses ({len(guesses)}):"] + [f"  {tag}" for tag in guesses]
        lines += ["", "What happened to items:"]
        for record in self.log:
            if record["kind"] == "item_added":
                effects = len((record["entry"].get("ItemData") or {}).get("Effects") or [])
                lines.append(f"  {record['time'][11:]}  added    {record['id']}  {record['rarity']}, power {record['power']}, {effects} effect(s)")
            elif record["kind"] == "item_removed":
                lines.append(f"  {record['time'][11:]}  removed  {record['id']}  {record['rarity']}, power {record['power']}")
            elif record["kind"] == "item_changed":
                for change in record["changes"]:
                    lines.append(f"  {record['time'][11:]}  changed  {record['id']}  {change['path']}: {json.dumps(change['old'], ensure_ascii=False)} -> {json.dumps(change['new'], ensure_ascii=False)}")
        lines += ["", "How the stats moved:"]
        moves: dict[str, list] = {}
        for record in self.log:
            if record["kind"] == "stat":
                moves.setdefault(record["stat"], [record["old"]]).append(record["new"])
        for stat, values in sorted(moves.items()):
            numbers = [v for v in values if isinstance(v, (int, float))]
            lines.append(f"  {stat}: {format_amount(values[0])} -> {format_amount(values[-1])} in {len(values) - 1} step(s)" + (f", between {format_amount(min(numbers))} and {format_amount(max(numbers))}" if numbers else ""))
        levels = [(r["new"], r["after"]) for r in self.log if r["kind"] == "stat" and r["stat"] == "Level"]
        if levels:
            lines += ["", "Level-ups: " + ", ".join(f"level {format_amount(level)} after {after / 60:.0f} min" for level, after in levels)]
        lines += ["", "World progress:"]
        for progress in self.progress.values():
            lines.append(f"  Now: {progress_counts(progress)}")
            if "where CurrentLocation" in progress:
                lines.append(f"  Where: {progress['where CurrentLocation']}; quest in focus: {progress.get('quest in focus')}; last minecart station: {progress.get('last minecart station')}")
        for container, progress in self.progress.items():
            missing = might_be_missing(progress, self.regions.get(container, {}))
            lines += ["  What you may have missed, as far as the save shows it:"] + [f"    {line}" for line in missing]
        steps = [r for r in self.log if r["kind"] == "progress"]
        loud = [r for r in steps if r["what"].startswith(LOUD_PROGRESS)]
        lines.append(f"  Steps while recording ({len(loud)}, and {len(steps) - len(loud)} quieter changes in events.jsonl):")
        for r in loud[: MOST * 3]:
            where = f"at {r['at'][0]:.0f}, {r['at'][1]:.0f}" if r.get("at") else f"in {r.get('area')}" + (f", near {r['near']['x']}, {r['near']['y']}" if r.get("near") else "")
            lines.append(f"    {r['time'][11:]}  {r['what']}: {json.dumps(r['old'], ensure_ascii=False)} -> {json.dumps(r['new'], ensure_ascii=False)}  [{where}]")
        lines += ["", "Soul Storm check:"]
        mentions = {label: value for found in self.storms.values() for label, value in found.items()}
        lines.append(f"  Places in the saves that mention a storm now ({len(mentions)}):")
        lines += [f"    {label}: {json.dumps(value, ensure_ascii=False)}" for label, value in sorted(mentions.items())[:MOST]]
        moved = [r for r in self.log if r["kind"] == "storm"]
        lines.append(f"  What changed there while recording ({len(moved)}):")
        lines += [f"    {r['time'][11:]}  {r['where']}: {json.dumps(r['old'], ensure_ascii=False)} -> {json.dumps(r['new'], ensure_ascii=False)}" for r in moved[:MOST]]
        if MARKED_ITEMS is None:
            lines.append("  This copy of the editor can't tell an item saved with something new: that part was left out.")
        lines.append(f"  Items saved with a mark or a field the editor has never seen ({len(self.marked)}):")
        for key, about in self.marked.items():
            lines.append(f"    {about['id']}  {about['name']}, {about['rarity']}: {', '.join(about['news'])}{self._storm_notes(key, about)}")
            lines.append(f"      as saved: {json.dumps(about['as_saved'], ensure_ascii=False)}")
        lines.append(f"  Items with one more rolled effect than their rarity usually has ({len(self.extra)}):")
        for key, about in self.extra.items():
            lines.append(f"    {about['id']}  {about['name']}, {about['rarity']}, power {format_amount(about['power'])}: {', '.join(about['rolled'])}; marks: {about['marks'] or 'none'}{self._storm_notes(key, about)}")
        other = [r for r in self.log if r["kind"] in ("section_changed", "format_changed", "metadata")]
        if other:
            lines += ["", "Other parts of the save that changed (see events.jsonl):"]
            seen: dict[str, int] = {}
            for record in other:
                key = record.get("section") or record["kind"]
                seen[key] = seen.get(key, 0) + record.get("count", len(record.get("changes", [])))
            lines += [f"  {key}: {count} value(s)" for key, count in sorted(seen.items())]
        notes = [r for r in self.log if r["kind"] == "note"]
        if notes:
            lines += ["", "Your notes:"] + [f"  {r['time'][11:]}  {r['text']}" for r in notes]
        return "\n".join(lines) + "\n"

    def _storm_notes(self, key: tuple, about: dict) -> str:
        notes = (["arrived while recording"] if about["new"] else []) + (["gone again"] if about.get("gone") else [])
        if key in self.storm_answers:
            notes.append(f"Soulstorm Enhanced in the game, you said: {self.storm_answers[key]}")
        return f"  [{'; '.join(notes)}]" if notes else ""

    def write_summary(self) -> Path:
        target = self.out / "summary.txt"
        target.write_text(self.summary(), encoding="utf-8")
        return target

    def ask_names(self, ask: Callable[[str], str | None], names_file: Path = NAMES_FILE) -> dict[str, str]:
        """Ask what the game calls each item the editor can't name; keep the answers where the editor reads them."""
        names = load_names(names_file)
        asked = [tag for tag in self.nameless() if tag not in names]
        given: dict[str, str] = {}
        if asked:
            self.say(f"\nThe editor has no name for {len(asked)} item(s) in your saves. Type what the game calls each one, or just press Enter to skip.")
        for tag in asked:
            answer = ask(f"  {tag} = ")
            if answer is None:
                break
            if answer.strip():
                given[tag] = answer.strip()
        if given:
            save_names({**names, **given}, names_file)
            self.event("names", names=given)
            self.say(f"Kept {len(given)} name(s) for the editor. Share item IDs (on its Help page) can send them on.")
        return given

    def close(self) -> None:
        self.event("session_end", saves=len([e for e in self.log if e["kind"] == "save_written"]), snapshots=self.snapshots)
        self.events_file.close()


def run(profile: Path, out: Path, once: bool = False, questions: bool = True) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace", line_buffering=True)  # a console that can't show a character shouldn't stop the recording
    session = out / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    recorder = Recorder(profile, session)
    print(f"Play recorder for Minecraft Dungeons II (editor {__version__}). Reads only; nothing leaves this PC.")
    print(f"Writing to {session}\n")
    recorder.begin(game_version())
    if once:
        print(recorder.summary())
        recorder.write_summary()
        recorder.close()
        return 0
    print("\n" + WORTH_DOING + "\n\nPress Ctrl+C to stop.\n")

    typed: queue.Queue[str | None] = queue.Queue()

    def read_lines() -> None:
        for line in sys.stdin:
            typed.put(line.rstrip("\n"))
        typed.put(None)

    interactive = questions and sys.stdin is not None and sys.stdin.isatty()
    if interactive:
        threading.Thread(target=read_lines, name="notes", daemon=True).start()

    reading = [interactive]  # whether the notes thread is still reading what's typed

    def ask(question: str) -> str | None:
        print(question, end="", flush=True)
        if reading[0]:
            try:
                line = typed.get(timeout=600)
            except queue.Empty:
                return None
            if line is not None:
                return line
            reading[0] = False  # Ctrl+C ends that thread's reading on Windows, so ask directly from here on
        try:
            return input()
        except (EOFError, KeyboardInterrupt):
            return None

    def wrap_up() -> None:
        recorder.look()
        print("\n" + recorder.summary())
        print(f"Summary written to {recorder.write_summary()}")
        if interactive:
            recorder.ask_names(ask)
            if recorder.ask_storm(ask):
                print(f"Summary written again with your answers: {recorder.write_summary()}")

    stamp = saves.profile_stamp(profile)
    next_game_check = 0.0
    try:
        while True:
            time.sleep(POLL)
            while interactive and not typed.empty():
                line = typed.get_nowait()
                if line and line.strip():
                    recorder.note(line.strip())
            latest = saves.profile_stamp(profile)
            if latest != stamp or recorder.retry:
                stamp = latest
                time.sleep(SETTLE)
                recorder.look()
            if time.monotonic() >= next_game_check:
                next_game_check = time.monotonic() + GAME_CHECK
                if recorder.check_game(saves.running_game_processes()):
                    time.sleep(8)  # the game's last save lands a moment after its window goes
                    wrap_up()
                    print("\nStill recording: start the game again to carry on, or press Ctrl+C to stop.")
    except KeyboardInterrupt:
        print("\nStopping.")
        wrap_up()
    recorder.close()
    return 0


def write_atlas(out: Path = DEFAULT_OUT) -> list[str]:
    """Read every recording under ``out`` and write what they show next to them: world_progress_atlas.json,
    world_map.txt and, when Pillow is there, world_map.png. Returns what to tell whoever asked."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    atlas = build_atlas(out)
    target = out / "world_progress_atlas.json"
    target.write_text(json.dumps(atlas, indent=1, ensure_ascii=False), encoding="utf-8")
    tasks = sum(len(quest["tasks"]) for quest in atlas["quests"].values())
    said = [
        f"{atlas['snapshots']} hero saves read. {len(atlas['quests'])} quests ({tasks} tasks), {len(atlas['minecart_stations'])} minecart stations, "
        f"{len(atlas['doors'])} doors, {len(atlas['cutscenes'])} cutscenes, {len(atlas['areas'])} areas, "
        f"{sum(len(names) for names in atlas['achievements'].values())} achievements.",
        f"Written to {target}",
    ]
    (out / "world_map.txt").write_text(text_map(atlas), encoding="utf-8")
    drawn = picture_map(atlas, out / "world_map.png")
    said.append(f"The map: {out / 'world_map.txt'}" + (f" and {out / 'world_map.png'}" if drawn else " (install Pillow for a picture of it)"))
    return said
