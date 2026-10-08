"""The play recorder: writes down what the game saves while you play, so you (and the editor) can learn from it.

    Menu > Play recorder… in the editor, or:   python -m dungeons2_editor record

Leave it running while you play. It only ever reads. Every time the game saves, it reads the hero and settings
saves again (never the sign-in, entitlement or device-ID containers), works out what changed and writes that
down. Nothing leaves this PC unless you send it. Each run's files go in the recordings folder, next to the
backups, in a folder named after the date and time:

    events.jsonl   one line per thing that happened: an item picked up, an item that changed (an enchantment, a
                   reroll, a power upgrade), a stat that moved, an item ID seen for the first time, a note you typed
    snapshots/     every version of each save the game wrote, as JSON, to look at closely afterwards
    summary.txt    written when the game closes and when you stop: new item IDs, what happened to items, how
                   the stats moved, world progress, and what it found for the Soul Storm check
    to_share.txt   the summary as it can be sent on: how far into the recording each thing happened in place of
                   the date and the time of day, and nothing of where your saves are

A recording holds your whole hero save, version by version, so treat the folder like a backup: it's yours, and
not for posting anywhere whole. What can be sent is to_share.txt: Share this recording…, in the window, shows
it and opens a GitHub issue with it, if you choose to.

While it runs you can type a note ("enchanted the sword with Fire Aspect"); the note goes into the timeline at
that moment. Run from a console, it also asks, when the game closes or you press Ctrl+C, what the game calls each
item the editor has no name for, and keeps the answers for the editor (item-names.json).

The Soul Storm check is how the Soulstorm Enhanced tag was found: the game saves it as a mark on the item
(hero.SOULSTORM_TAG), and a player's list showed one. It still watches for what a save holds that the editor
hasn't met, and says so at once when one turns up:

    an item saved with a mark or a field the editor has never seen on one
    anything anywhere in a save that mentions a storm, and every change to it
    an item the game marks as a Soul Storm reward, and an item with one more rolled effect than its rarity
    usually has, which is what a Soul Storm's chest gives

It also tracks world progress: every quest and each of its tasks, minecart stations, doors, cutscenes, how much of
each area is explored, achievements, and anything else a save keeps about how far the hero has got. Each step
is written down as the game saves it, so the recordings show how the game itself moves a hero along, which is
what the editor would have to write to do the same.

    python -m dungeons2_editor record --atlas      (Show the map, in the window)

reads every recording made so far and writes world_progress_atlas.json next to them: every quest with its tasks
in order, every station, door, cutscene, area and achievement any save has shown. The editor's World map window
draws a hero's own map from its save, and takes from that file where the hero's recordings saw things turn up.

And it tracks where things are. A save gives a door's exact position, and for each region a picture of the fog
over it, a square of it being 32 metres of ground, laid out the way the game's own map is. So every step is
written down with the area the hero was in and the middle of the ground whose fog cleared since the save before:
that is where a station, a cutscene or a quest step was found, to within a few squares. --atlas puts all of it on
a map: world_map.txt, and world_map.png when Pillow is installed.

What it can say about things you may have missed is what a save gives away: how many of an area's dungeon and
rift spots you've found (MetaBot's counts, from the game's files; the game opens only a few of them at a time, so
a spot you haven't found may not be open yet), the minecart stations you haven't found, by name, quests you
haven't started or finished, and ground you haven't seen right next to ground you have, which the map marks. It
can't see a chest or a secret you haven't touched: the game writes those to a save only once you have, and where
they are is in its encrypted files.

Chests you open, it counts: the game keeps a count of them for its "open 100 chests" achievement, so each time
that goes up the recorder says so, with the area you were in and, out in the open, the spot. A save doesn't say
which chest it was, and whether the count goes on past a hundred isn't known.
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
from .hero import SOULSTORM, Hero, format_amount, game_item, is_hero_document, is_unique_version, items_by_identity
from .my_items import NAMES_FILE, load_names, save_names

DEFAULT_OUT = paths.data_dir() / "recordings"  # next to the backups, on this PC only
POLL = 1.0  # seconds between looks at the save folder
SETTLE = 0.7  # after the folder changes, wait this long before reading, so the game has finished writing
GAME_CHECK = 10.0  # seconds between checks for the game's process
LONG = 400  # characters of a value kept in an event; snapshots keep everything
MOST = 60  # changes listed per event
SUMMARY_FILE = "summary.txt"
SHARE_FILE = "to_share.txt"  # the summary as it can be sent on (Recorder.summary(sharing=True))
MOST_SHARED = 250  # lines about items in the copy for sending, the latest ones, so it fits in a GitHub issue
NOT_SHARED = ("PickupTimestamp", "GenesisRandomSeed")  # what an item's entry says of when you played: left out there

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
  - play a Soul Storm and open its reward chests
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
ATLAS_FORMAT = 3  # goes up when the atlas is laid out differently, so that one written down the old way is read again
CHESTS = "achievement Open100Chests"  # the game's own count of chests opened, the one thing a save says about chests
# A save keeps, for each region, a picture of the fog over it: Size.X values to a line and Size.Y lines, each value
# from 0 (never seen) to 255 (clear), a square of the picture being 32 metres of ground. The picture lies the way
# the game's own map does: its lines run from the far side in the world's X down to the near side, and the values
# in a line run with the world's Y. Read any other way, the doors a save lists land off the ground it shows
# cleared; read this way all of them land on it, and MetaBot's map (https://metabot.gg/en/minecraft-dungeons-2/map,
# from the game's files) has the same dungeon and rift spots the same way round.
CELL = 32
CLEAR = 128  # from here up a square counts as clear; under it the fog has only begun to lift (the edge of what was seen)
# How far a region's picture lies from where the corner saved with it says, in squares: (down, to the right).
# Nothing in a save says, so it's measured, and good to about a third of a square. With no entry a picture's
# bottom left is the saved corner, which fits the camp and the meadows. The overworld's picture is three squares
# lower and half a square to the right: that is where all 32 of its doors in the developer's saves sit on cleared
# ground (less the few metres a hero stands in front of a door), and where the round patch cleared on stepping
# into a region inside the overworld, which both pictures get, is in the same place in both.
SHIFTS = {"SW.Region.Overworld": (3.0, 0.5), "SW.Area.Forest.A1.Underwell": (1.3, -0.4)}


def map_regions(document: Any) -> dict[str, dict]:
    """The picture of the fog a save keeps for each region: the corner saved with it (metres), how many squares
    it is across and down, the squares themselves line by line from the top (0 for one the hero has never seen,
    up to 255 for one all clear), and how far the picture lies from that corner (SHIFTS)."""
    def held(value: object, kind: type) -> Any:
        return value if isinstance(value, kind) else kind()

    def number(value: object) -> float:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0

    body = held(document, dict).get("CharacterSaveV1")
    fog = held(held(held(body, dict).get("WorldExploration"), dict).get("SavedFogOfWarExploration"), dict)
    found = {}
    for area in held(fog.get("Items"), list):
        if not isinstance(area, dict):
            continue
        corner, size, tag = held(area.get("WorldPosition"), dict), held(area.get("Size"), dict), str(area.get("Tag"))
        across, down = (side if isinstance(side, int) and not isinstance(side, bool) and side > 0 else 0 for side in (size.get("X"), size.get("Y")))
        # As many squares as the picture's size says, whatever the save holds: one short of them counts as never seen.
        cells = [cell if isinstance(cell, int) and not isinstance(cell, bool) else 0 for cell in held(area.get("Data"), list)[: across * down]]
        found[tag] = {"x": number(corner.get("X")), "y": number(corner.get("Y")), "across": across, "down": down,
                      "cells": cells + [0] * (across * down - len(cells)), "shift": list(SHIFTS.get(tag, (0, 0)))}
    return found


def door_places(document: Any) -> dict[str, list[float]]:
    """Where each door a save lists is, in metres: the one thing on the map a save gives an exact position for."""
    body = document.get("CharacterSaveV1") if isinstance(document, dict) else None
    world = (body or {}).get("WorldExploration") or {}
    return {
        str(door.get("DoorId")): [round((door.get("Location") or {}).get(axis, 0) / 100, 1) for axis in ("X", "Y", "Z")]
        for door in world.get("DiscoveredDungeonDoors") or []
    }


def square_of(region: dict, x: float, y: float) -> tuple[float, float]:
    """Where a spot in the world (metres) is on a region's picture: squares across from its left edge, and squares
    down from its top."""
    lower, right = region.get("shift") or (0, 0)
    return (y - region["y"]) / CELL - right, region["down"] - lower - (x - region["x"]) / CELL


def spot_of(region: dict, across: float, down: float) -> tuple[float, float]:
    """The other way: the spot in the world (metres) at a place on a region's picture."""
    lower, right = region.get("shift") or (0, 0)
    return region["x"] + (region["down"] - lower - down) * CELL, region["y"] + (across + right) * CELL


def newly_explored(before: dict[str, dict], after: dict[str, dict]) -> dict | None:
    """Where the hero went between two saves: the region whose fog cleared the most, and the middle of what
    cleared, in the world's metres. None if none did. When a smaller region cleared about as much as the one that
    cleared most, it's the smaller: stepping into a region inside the overworld clears a patch of both pictures."""
    cleared = []
    for tag, region in after.items():
        old = (before.get(tag) or {}).get("cells") or []
        gains = [(index, cell - (old[index] if index < len(old) else 0)) for index, cell in enumerate(region["cells"][: region["across"] * region["down"]])]
        gains = [(index, gain) for index, gain in gains if gain > 0]
        if gains:
            cleared.append((sum(gain for _index, gain in gains), tag, gains))
    if not cleared:
        return None
    most = max(total for total, _tag, _gains in cleared)
    total, tag, gains = min((entry for entry in cleared if entry[0] >= 0.9 * most), key=lambda entry: (len(after[entry[1]]["cells"]), entry[1]))
    region = after[tag]
    across = sum((index % region["across"] + 0.5) * gain for index, gain in gains) / total
    down = sum((index // region["across"] + 0.5) * gain for index, gain in gains) / total
    x, y = spot_of(region, across, down)
    return {"region": tag, "squares": len(gains), "x": round(x), "y": round(y)}


def region_of(x: float, y: float, regions: dict[str, dict]) -> str | None:
    """The region a spot is in: the smallest one whose picture has it (the caves and the meadows lie inside the overworld's)."""
    inside = []
    for tag, region in regions.items():
        across, down = square_of(region, x, y)
        if 0 <= across < region["across"] and 0 <= down < region["down"]:
            inside.append((region["across"] * region["down"], tag))
    return min(inside)[1] if inside else None


def clarity_colour(value: int, edge: bool = False) -> str:
    """The colour of a square on a map: the clearer its fog, the greener; a square never seen is dark, and one never
    seen right next to one that has been stands out from the rest."""
    if not value:
        return "#3c5f78" if edge else "#16303f"
    share = 0.3 + 0.7 * min(value, 255) / 255
    return "#" + "".join(f"{round(dark + (light - dark) * share):02x}" for dark, light in ((0x16, 0x5D), (0x30, 0x8A), (0x3F, 0x66)))


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


def hero_id(document: Any) -> str:
    """The ID the game gave the hero a save is of."""
    body = document.get("CharacterSaveV1") if isinstance(document, dict) else None
    return str(((body or {}).get("MetaData") or {}).get("CharacterId", ""))


def quest_tasks(progress: dict[str, Any]) -> dict[str, list[str]]:
    """How each step of each quest stands, by quest, in the save's order. A step is named for its quest (CA02_B_E07
    is a step of CA02_B), so it goes to the quest with the longest name it starts with: CA02's steps start the
    same way, and so do CA02_B_BR's."""
    quests = [label[6:] for label in progress if label.startswith("quest ") and label != "quest in focus"]
    steps: dict[str, list[str]] = {name: [] for name in quests}
    for label, value in progress.items():
        if label.startswith("task "):
            owners = [name for name in quests if label[5:].startswith(name + "_")]
            if owners:
                steps[max(owners, key=len)].append(str(value))
    return steps


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
        "format": ATLAS_FORMAT,
        "snapshots": 0, "quests": {}, "minecart_stations": [], "last_minecart_station_values": [], "doors": {}, "cutscenes": [], "gimmicks": [],
        "areas": {}, "achievements": {}, "progression": {}, "locations": [], "hints": [], "quests_in_focus": [],
        # The map: each region's picture with every square as clear as any save shows it, and where each thing was
        # found, by the ground cleared in the save it first appeared in (things there from the first save have no place).
        "map": {"metres_per_square": CELL, "regions": {}}, "found_at": {},
        "chests": [],  # each time the count of chests opened went up: how many, where the hero was, and the spot if new ground was explored
        # The same, hero by hero (by its ID), for a hero's own map: only what its own saves showed, and of what
        # it found only what has a spot. Above, a thing two heroes found is where the first of them found it.
        "heroes": {},
    }
    before: dict[str, tuple[dict[str, Any], dict[str, dict], str]] = {}  # each hero's save before this one: its progress, its grids, its recording

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
                merged["cells"] = [max(old, new) for old, new in zip(merged["cells"], region["cells"])]
        hero, recording = hero_id(document), path.parent.parent.name
        mine = atlas["heroes"].setdefault(hero, {"saves": 0, "found_at": {}, "chests": []})
        mine["saves"] += 1
        earlier = before.get(hero)
        if earlier is not None:
            # Two saves one after the other in a recording are one step of the game's, so what's new in the second
            # happened on the ground explored between them. The last save of one recording and the first of the
            # next are however long apart the hero played unrecorded: what's new then has no place to give.
            together = earlier[2] == recording
            near = newly_explored(earlier[1], regions) if together else None
            where = {"area": progress.get("where CurrentLocation") if together else None, "near": [near["x"], near["y"]] if near else None,
                     "region": near["region"] if near else None, "recording": recording, "snapshot": path.name}
            was, now = earlier[0].get(CHESTS), progress.get(CHESTS)
            if isinstance(was, int) and isinstance(now, int) and now > was:
                chest = {"opened": now - was, "count": now, **where}
                atlas["chests"].append(chest)
                mine["chests"].append(chest)
            for label in progress:
                first = label not in earlier[0] or (label.startswith(("quest ", "task ")) and str(progress[label]).startswith("Completed") and not str(earlier[0][label]).startswith("Completed"))
                if first and label.startswith(PLACED) and label != "quest in focus":
                    atlas["found_at"].setdefault(label, where)
                    if near and not label.startswith(("task ", "actor ")):
                        mine["found_at"].setdefault(label, where)
        before[hero] = (progress, regions, recording)
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


# What the game calls the places a save names by its own tags, and how many of each kind of spot an area has, from
# MetaBot's Overworld map (https://metabot.gg/en/minecraft-dungeons-2/map, read from the game's files, build
# 1.1.1.0). An area is keyed the way a save's doors and minecart stations name it. The first two areas' door names
# are in the developer's saves; Rainy Plains and Frozen Highlands are keyed the way their stations are, and no
# save has shown the editor a door there yet. The game opens only some of an area's dungeon and rift spots at a
# time (four of its dungeons, MetaBot says), so a spot a hero hasn't found may not be there to find just now.
AREAS = {"Town": "Brave Haven", "PlainsA1": "Honeycomb Fields", "ForestA1": "Howling Woods", "PlainsA2": "Rainy Plains", "DesertA1": "Frozen Highlands"}
AREA_TOTALS = {"PlainsA1": (7, 8), "ForestA1": (12, 12), "PlainsA2": (9, 10), "DesertA1": (11, 16)}  # dungeon spots, rift spots
STATIONS = {  # a minecart station, as its tag ends: (what the game calls it, the area it's in)
    "Town": ("Haven Station", "Town"), "TownFountain": ("Town Fountain", "Town"),
    "PlainsA1.Barn": ("Honeycomb Farm", "PlainsA1"), "PlainsA1.Border": ("Honeybrook Bridge", "PlainsA1"),
    "ForestA1.Outpost": ("Little Howl Hamlet", "ForestA1"), "ForestA1.SpiderCaveExit": ("Deep Dark Entrance", "ForestA1"),
    "ForestA1.NWPass": ("Hidden Grove", "ForestA1"), "ForestA1.DangerZone": ("Woodcutter's Outpost", "ForestA1"),
    "PlainsA2.Central": ("Monsoon Banks", "PlainsA2"), "PlainsA2.IllagerCamp": ("Orange Tower", "PlainsA2"), "PlainsA2.VillagerOasis": ("Puddle Pond", "PlainsA2"),
    "PlainsA2.NorthWestBridge": ("Red Tower", "PlainsA2"), "PlainsA2.SouthEastBridge": ("White Tower", "PlainsA2"),
    "DesertA1.MountainPass": ("Archie's Ruins", "DesertA1"), "DesertA1.Fortress": ("Fortress Backgate", "DesertA1"), "DesertA1.Fortress2": ("Frozen Fortress", "DesertA1"),
    "DesertA1.IceShelf": ("Frozen Shipyard", "DesertA1"), "DesertA1.Cliffs": ("Highland Cliffs", "DesertA1"), "DesertA1.IceLagoon": ("Ice Caves", "DesertA1"),
}
# The Town Fountain is where a hero starts out: a save names it as the station last used (SW.MinecartStation.Town.Fountain)
# and no save has ever listed it among the stations found, so it isn't one to find.
NOT_FOUND_BY_RIDING = frozenset({"TownFountain"})
# MetaBot's map marks those nineteen. Saves have since shown stations it doesn't mark (two in the Carapace, four in
# the meadows, and two more in Frozen Highlands, in /issues/33), so nineteen is not how many the game has: see
# stations_at_least().
QUESTS = {  # a quest, as a save names it: what the game calls it (the ones MetaBot's map marks a spot for)
    "CA01": "The Illagers from the Rift", "CA02": "The Silence in Little Howl", "CA02_B": "Corruption in the Woods", "CA04": "The Missing Note Blocks",
    "CA05": "Hiking Frozen Highlands", "CA06": "Returning the Note Blocks", "CA07": "Wading Rainy Plains", "PLa1_S04_A": "Keeper of the Bees",
    "FOa1_S10_A": "The Cleric's Apprentice", "DEa1_S13_A": "The Fight at the End of the Tunnel",
}
_NUMBERED = re.compile(r"SW\.Doorway\.(\w+)\.(Dungeon|Rift)\.(\d+)$")
_STATION = "SW.MinecartStation."


def area_name(tag: str) -> str:
    """An area by the game's name for it, where that's known: SW.Area.Forest.A1 is Howling Woods, and a place inside
    it keeps the rest of its tag (Howling Woods: SpiderCaves.3). Otherwise the tag, less the SW.Area. on every one."""
    plain = tag.removeprefix("SW.Area.")
    parts = plain.split(".")
    for count in range(len(parts), 0, -1):
        name = AREAS.get("".join(parts[:count]))
        if name:
            return name + (": " + ".".join(parts[count:]) if parts[count:] else "")
    return plain


def station_key(tag: str) -> str:
    """A minecart station's tag as STATIONS is keyed: less the part every one has, and with its area written as
    one word, which the game doesn't always do (a save has SW.MinecartStation.Forest.A1.DangerZone)."""
    key = tag.removeprefix(_STATION)
    parts = key.split(".")
    for count in range(2, len(parts) + 1):
        joined = ".".join(["".join(parts[:count]), *parts[count:]])
        if joined in STATIONS:
            return joined
    return key


def station_name(tag: str) -> str:
    """A minecart station by the game's name for it, where that's known. Otherwise by what a save calls it, set
    out to be read: SW.MinecartStation.DesertA1.TaigaBeach is Taiga Beach (Frozen Highlands)."""
    key = station_key(tag)
    if key in STATIONS:
        return STATIONS[key][0]
    area, _, name = key.partition(".")
    return f"{_words(name)} ({AREAS.get(area) or _words(area)})" if name else _words(key)


def _words(name: str) -> str:
    """A name the game runs together, with its words apart: TaigaBeach, MeadowA1, Forest.A1."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name.replace(".", " "))


def stations_at_least(found: int = 0) -> int:
    """How many minecart stations the game has, at the least: the ones MetaBot's map marks, the ones saves have
    shown the editor, or the ones this hero has ``found``, whichever is most. It isn't the game's total, which
    nothing readable gives."""
    from . import world  # which reads this module, so not at the top

    return max(len(STATIONS), len(world.known().get("stations") or ()), found)


def quest_name(name: str) -> str:
    """A quest as a save names it, with what the game calls it where that's known."""
    return f"{name} ({QUESTS[name]})" if name in QUESTS else name


def frontier(region: dict) -> list[int]:
    """The squares of a region's picture the hero has never seen that touch one it has: the ground right next to
    where it has been, which is where something walked past would be."""
    across, down, cells = region["across"], region["down"], region["cells"]
    edge = []
    for index, cell in enumerate(cells[: across * down]):
        if not cell:
            line, place = divmod(index, across)
            around = [(line - 1, place), (line + 1, place), (line, place - 1), (line, place + 1)]
            if any(0 <= l < down and 0 <= p < across and cells[l * across + p] for l, p in around):
                edge.append(index)
    return edge


def might_be_missing(progress: dict[str, Any], regions: dict[str, dict]) -> list[str]:
    """What a hero may have missed, as far as its save shows: how many of each area's dungeon and rift spots it has
    found, the minecart stations it hasn't, quests not started or not finished, and unseen ground beside seen."""
    lines = []
    numbered: dict[tuple[str, str], set[int]] = {}
    for label in progress:
        match = _NUMBERED.match(label[5:]) if label.startswith("door ") else None
        if match:
            numbered.setdefault((match.group(1), match.group(2)), set()).add(int(match.group(3)))
    for (area, kind), found in sorted(numbered.items()):
        dungeons, rifts = AREA_TOTALS.get(area, (None, None))
        total = dungeons if kind == "Dungeon" else rifts
        lines.append(f"{AREAS.get(area, area)}: {len(found)} " + (f"of its {total} {kind.lower()} spots found" if total else f"{kind.lower()} spot{'s' if len(found) != 1 else ''} found"))
    if numbered:
        lines.append("(The game opens only a few of an area's dungeon and rift spots at a time, so one you haven't found may not be open yet.)")
    stations = {station_key(label[len("minecart station "):]) for label in progress if label.startswith("minecart station ")}
    lines.append(f"Minecart stations: {len(stations)} found of at least {stations_at_least(len(stations))}")
    unfound: dict[str, list[str]] = {}
    for key, (name, area) in STATIONS.items():
        if key not in stations and key not in NOT_FOUND_BY_RIDING:
            unfound.setdefault(AREAS.get(area, area), []).append(name)
    if unfound and stations:
        lines.append("Stations not found yet: " + "; ".join(f"{', '.join(names)} ({area})" for area, names in unfound.items()))
    steps = quest_tasks(progress)
    for label, state in sorted(progress.items()):
        if label.startswith("quest ") and label != "quest in focus" and state in ("Available", "Active"):
            name = label[6:]
            tasks = steps[name]
            left = sum(1 for value in tasks if not str(value).startswith("Completed"))
            lines.append(f"Quest {quest_name(name)}: " + ("not started" if state == "Available" else f"{left} of {len(tasks)} steps left"))
    for tag, region in regions.items():
        explored, edge = sum(1 for cell in region["cells"] if cell), len(frontier(region))
        if edge:
            lines.append(f"{tag}: {edge} unexplored square{'s' if edge != 1 else ''} right next to the {explored} you've explored (marked on the map)")
    return lines


def text_map(atlas: dict[str, Any]) -> str:
    """The atlas as a map you can read in a text file: each region's picture, the way round the game's own map is
    (# clear, + the fog only beginning to lift, . never seen), with a letter on each door's square and a number
    on each place something else was found."""
    lines = [f"World map from {atlas['snapshots']} saves, the way round the game's own map is. One square is {CELL} metres. "
             "# clear, + the fog only beginning to lift, ? never seen but right next to ground that has been, . never seen.", ""]
    if atlas.get("might_be_missing"):
        lines += ["What you may have missed, as far as a save shows it:"] + [f"  {line}" for line in atlas["might_be_missing"]] + [""]
    marks = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    for tag, region in atlas["map"]["regions"].items():
        across, down, cells = region["across"], region["down"], region["cells"]
        edge = set(frontier(region))
        grid = [["#" if cells[line * across + place] >= CLEAR else "+" if cells[line * across + place] else "?" if line * across + place in edge else "."
                 for place in range(across)] for line in range(down)]
        legend = []

        def put(x: float, y: float, mark: str) -> bool:
            place, line = square_of(region, x, y)
            if 0 <= place < across and 0 <= line < down:
                grid[int(line)][int(place)] = mark
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
        chests = [chest for chest in atlas.get("chests", []) if chest.get("region") == tag and chest.get("near")]
        if any([put(chest["near"][0], chest["near"][1], "$") for chest in chests]):
            legend.append(f"  $  a chest opened ({sum(chest['opened'] for chest in chests)} in this region with a spot to show)")
        explored = sum(1 for cell in cells if cell)
        lines += [f"{tag}  ({across} squares across, {down} down; {explored} explored)"] + ["  " + "".join(row) for row in grid] + legend + [""]
    opened = chests_by_area(atlas.get("chests", []))
    if opened:
        lines += ["Chests opened, by the area you were in:"] + [f"  {area}: {count}" for area, count in opened.items()] + [""]
    return "\n".join(lines)


BETWEEN = "while nothing was recording"  # where a chest was opened, when the count went up between one recording and the next


def chests_by_area(chests: list[dict]) -> dict[str, int]:
    """How many chests the recordings saw opened in each area, the areas in order of name, and last how many the
    game's count went up by between one recording and the next."""
    opened: dict[str, int] = {}
    for chest in chests:
        area = str(chest["area"]) if chest.get("area") else BETWEEN
        opened[area] = opened.get(area, 0) + chest.get("opened", 1)
    return {area: opened[area] for area in sorted(opened, key=lambda area: (area == BETWEEN, area))}


def picture_map(atlas: dict[str, Any], target: Path) -> bool:
    """The same map as a picture, if Pillow is installed: the clearer the fog over a square the greener, doors as
    orange dots with their names, a blue dot where anything else was found, a yellow one where a chest was
    opened. False when it can't be drawn."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    regions = atlas["map"]["regions"]
    if not regions:
        return False
    scale, gap, top = 14, 40, 26  # pixels to a square, between regions, and above each for its name
    order = sorted(regions.items(), key=lambda pair: -pair[1]["across"] * pair[1]["down"])
    width = max(region["across"] for _tag, region in order) * scale + 2 * gap + 360
    height = sum(max(region["down"] * scale, 40 * 13) + gap + top for _tag, region in order) + gap  # room for the names beside a small picture
    image = Image.new("RGB", (width, height), "#0d1a24")
    draw = ImageDraw.Draw(image)
    y0 = gap
    for tag, region in order:
        across, down, cells = region["across"], region["down"], region["cells"]
        draw.text((gap, y0), f"{tag}   {sum(1 for cell in cells if cell)} of {across * down} squares explored", fill="#d7e3ea")
        y0 += top
        edge = set(frontier(region))
        for index in range(min(len(cells), across * down)):
            line, place = divmod(index, across)
            draw.rectangle([gap + place * scale, y0 + line * scale, gap + (place + 1) * scale - 2, y0 + (line + 1) * scale - 2], fill=clarity_colour(cells[index], index in edge))

        def spot(x: float, y: float) -> tuple[float, float] | None:
            place, line = square_of(region, x, y)
            return (gap + place * scale, y0 + line * scale) if 0 <= place < across and 0 <= line < down else None

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
        for chest in atlas.get("chests", []):
            at = spot(chest["near"][0], chest["near"][1]) if chest.get("region") == tag and chest.get("near") else None
            if at:
                draw.rectangle([at[0] - 4, at[1] - 3, at[0] + 4, at[1] + 3], fill="#ffd84a", outline="#2a2100")
                labels.append((at, f"chest opened ({chest['opened']})", "#ffe98a"))
        side = gap + across * scale + 24  # names go in a column beside the picture, each joined to its dot
        for number, (at, name, colour) in enumerate(sorted(labels, key=lambda entry: entry[0][1])):
            line_y = y0 + number * 13
            if line_y < y0 + max(down * scale, len(labels) * 13):
                draw.line([at, (side - 4, line_y + 6)], fill="#33505f")
                draw.text((side, line_y), name[:52], fill=colour)
        y0 += max(down * scale, len(labels) * 13) + gap
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
        self.game_version: str | None = None
        # The Soul Storm check: what each save says about storms, and the items worth asking about, by (container,
        # the item's identity).
        self.storms: dict[str, dict[str, Any]] = {}
        self.marked: dict[tuple, dict] = {}  # items saved with a mark or a field the editor doesn't know
        self.extra: dict[tuple, dict] = {}  # items with one more rolled effect than their rarity usually has
        self.soulstorm: dict[tuple, dict] = {}  # items the game marks as a Soul Storm reward: Soulstorm Enhanced
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
        self.game_version = version
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
                more += f", {SOULSTORM}" if item.is_soulstorm else ""
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
                if label == CHESTS and isinstance(old, int) and isinstance(new, int) and new > old:
                    more = new - old
                    self.event("chest", f"CHEST OPENED: {more} more, {new} by the game's count  [{where}]", container=container, opened=more, count=new, area=area, near=near)

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
        """Keep track of the items a Soul Storm has to do with, or might: one saved with something the editor has
        never seen on an item, one the game marks as a Soul Storm reward, and one with a rolled effect more than
        usual. ``new`` holds the identities of the items that have just arrived."""
        items = items_by_identity(hero)
        by_entry = {id(item.entry): key for key, item in items.items()}
        here = {(container, key) for key in items}
        for known in (self.marked, self.extra, self.soulstorm):
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
            if item.is_soulstorm and key not in self.soulstorm:
                self.soulstorm[key] = self._about(item, identity in new)
                if identity in new:
                    self.event("soulstorm_item", f"{SOULSTORM.upper()}: {item.name}  [{item.tag}]", container=container, **self.soulstorm[key])

    @staticmethod
    def _about(item: Any, new: bool, **more: Any) -> dict:
        return {
            "id": item.tag, "name": item.name, "rarity": item.rarity, "power": item.power, "rolled": rolled_effects(item),
            "marks": list(item.data.get("DynamicPropertyTags") or []), "new": new, "as_saved": AS_SAVED(item) if AS_SAVED is not None else item.entry, **more,
        }

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

    def summary(self, sharing: bool = False) -> str:
        """What the recording shows. With ``sharing`` it's the copy that can be sent on: the same, with how far
        into the recording each thing happened in place of the date and the time of day, the latest of a long
        run of item lines, and nothing an item's entry says of when it was picked up."""
        # Which kind of save, and not the folder: its path holds the Windows account's name and, for the Xbox app,
        # the Xbox user's ID, and a summary is the part of a recording that gets passed on.
        kind = {"steam": "Steam", "folders": "a folder for each save"}.get(saves.layout_of(self.profile), "the Xbox app")

        def when(record: dict) -> str:
            if not sharing:
                return record["time"][11:]
            minutes, seconds = divmod(int(record.get("after") or 0), 60)
            return f"+{minutes:02d}:{seconds:02d}"

        if sharing:
            lines = [
                f"Play recording, {max(1, round((self.clock() - self.started) / 60))} minute(s) long. Saves: {kind}. Editor {__version__}"
                + (f", game {self.game_version}" if self.game_version else "") + ".",
                "Times are minutes and seconds into the recording.",
                "",
            ]
        else:
            lines = [f"Play recording, {datetime.fromtimestamp(self.started):%Y-%m-%d %H:%M} to {datetime.fromtimestamp(self.clock()):%H:%M}", f"Saves: {kind}", ""]
        written = [e for e in self.log if e["kind"] == "save_written"]
        lines.append(f"The game saved {len(written)} time(s); {self.snapshots} snapshot(s) kept.")
        new = sorted(tag for tag in self.ids if tag not in self.at_start)
        lines += ["", f"Item IDs first seen while recording ({len(new)}):"] + [f"  {tag}  ({self.ids[tag]})" for tag in new]
        nameless = [tag for tag in self.nameless()]
        lines += ["", f"Item IDs the editor has no name for ({len(nameless)}):"] + [f"  {tag}" for tag in nameless]
        guesses = sorted(tag for tag, known in self.ids.items() if known == "guess")
        lines += ["", f"Item IDs that confirm one of the editor's guesses ({len(guesses)}):"] + [f"  {tag}" for tag in guesses]
        lines += ["", "What happened to items:"]
        items: list[str] = []
        for record in self.log:
            if record["kind"] == "item_added":
                effects = len((record["entry"].get("ItemData") or {}).get("Effects") or [])
                items.append(f"  {when(record)}  added    {record['id']}  {record['rarity']}, power {record['power']}, {effects} effect(s)")
            elif record["kind"] == "item_removed":
                items.append(f"  {when(record)}  removed  {record['id']}  {record['rarity']}, power {record['power']}")
            elif record["kind"] == "item_changed":
                for change in record["changes"]:
                    if sharing and any(part in NOT_SHARED for part in re.split(r"[.\[\]]", str(change["path"]))):
                        continue
                    items.append(f"  {when(record)}  changed  {record['id']}  {change['path']}: {json.dumps(change['old'], ensure_ascii=False)} -> {json.dumps(change['new'], ensure_ascii=False)}")
        if sharing and len(items) > MOST_SHARED:
            items = [f"  ({len(items) - MOST_SHARED} earlier lines were left out to keep this short enough to post)"] + items[-MOST_SHARED:]
        lines += items
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
        chests: dict[str, int] = {}
        for r in self.log:
            if r["kind"] == "chest":
                chests[str(r.get("area"))] = chests.get(str(r.get("area")), 0) + r["opened"]
        lines.append(f"  Chests opened while recording: {sum(chests.values())}" + (f" ({', '.join(f'{count} in {area}' for area, count in sorted(chests.items()))})" if chests else ""))
        steps = [r for r in self.log if r["kind"] == "progress"]
        loud = [r for r in steps if r["what"].startswith(LOUD_PROGRESS)]
        lines.append(f"  Steps while recording ({len(loud)}, and {len(steps) - len(loud)} quieter changes in events.jsonl):")
        for r in loud[: MOST * 3]:
            where = f"at {r['at'][0]:.0f}, {r['at'][1]:.0f}" if r.get("at") else f"in {r.get('area')}" + (f", near {r['near']['x']}, {r['near']['y']}" if r.get("near") else "")
            lines.append(f"    {when(r)}  {r['what']}: {json.dumps(r['old'], ensure_ascii=False)} -> {json.dumps(r['new'], ensure_ascii=False)}  [{where}]")
        lines += ["", "Soul Storm check:"]
        mentions = {label: value for found in self.storms.values() for label, value in found.items()}
        lines.append(f"  Places in the saves that mention a storm now ({len(mentions)}):")
        lines += [f"    {label}: {json.dumps(value, ensure_ascii=False)}" for label, value in sorted(mentions.items())[:MOST]]
        moved = [r for r in self.log if r["kind"] == "storm"]
        lines.append(f"  What changed there while recording ({len(moved)}):")
        lines += [f"    {when(r)}  {r['where']}: {json.dumps(r['old'], ensure_ascii=False)} -> {json.dumps(r['new'], ensure_ascii=False)}" for r in moved[:MOST]]
        if MARKED_ITEMS is None:
            lines.append("  This copy of the editor can't tell an item saved with something new: that part was left out.")
        lines.append(f"  Items saved with a mark or a field the editor has never seen ({len(self.marked)}):")
        for number, (key, about) in enumerate(self.marked.items()):
            lines.append(f"    {about['id']}  {about['name']}, {about['rarity']}: {', '.join(about['news'])}{self._storm_notes(key, about)}")
            if not sharing or number < share_ids.MAX_MARK_LINES:  # a whole item each: a few show how it's saved
                lines.append(f"      as saved: {json.dumps(about['as_saved'], ensure_ascii=False)}")
        lines.append(f"  {SOULSTORM} items, by the game's mark for a Soul Storm reward ({len(self.soulstorm)}):")
        for key, about in self.soulstorm.items():
            lines.append(f"    {about['id']}  {about['name']}, {about['rarity']}, power {format_amount(about['power'])}: {', '.join(about['rolled']) or 'no rolled effects'}{self._storm_notes(key, about)}")
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
            lines += ["", "Your notes:"] + [f"  {when(r)}  {r['text']}" for r in notes]
        if sharing:
            lines = _fitting(lines, share_ids.MAX_REPORT)
        return "\n".join(lines) + "\n"

    def _storm_notes(self, key: tuple, about: dict) -> str:
        notes = (["arrived while recording"] if about["new"] else []) + (["gone again"] if about.get("gone") else [])
        return f"  [{'; '.join(notes)}]" if notes else ""

    def write_summary(self) -> Path:
        """Write the summary, and beside it the copy that can be sent on (Share this recording…, in the window)."""
        target = self.out / SUMMARY_FILE
        target.write_text(self.summary(), encoding="utf-8")
        (self.out / SHARE_FILE).write_text(self.summary(sharing=True), encoding="utf-8")
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


def _fitting(lines: list[str], most: int) -> list[str]:
    """The lines that fit in ``most`` characters, with a line saying how many were left out when some were."""
    room, kept = most - 100, 0
    for line in lines:
        if room - len(line) - 1 < 0:
            break
        room -= len(line) + 1
        kept += 1
    return lines if kept == len(lines) else lines[:kept] + [f"({len(lines) - kept} more lines were left out to keep this short enough to post)"]


def to_share(out: Path) -> Path | None:
    """The copy for sending of the newest recording under ``out`` that has one. None when none has: a recording
    made by a version before 1.15.1 has only a summary, and that one names the save folder."""
    try:
        folders = sorted((folder for folder in Path(out).iterdir() if folder.is_dir()), key=lambda folder: folder.name, reverse=True)
    except OSError:
        return None
    return next((folder / SHARE_FILE for folder in folders if (folder / SHARE_FILE).is_file()), None)


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
        print(f"Beside it, {SHARE_FILE} is the copy that can be sent on. In the editor: Menu > Play recorder… > Share this recording…")
        if interactive:
            recorder.ask_names(ask)

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


def load_atlas(out: Path = DEFAULT_OUT) -> dict[str, Any] | None:
    """What the recordings under ``out`` have shown, as it was last written down. None if it never was."""
    try:
        atlas = json.loads((Path(out) / "world_progress_atlas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return atlas if isinstance(atlas, dict) else None


def fresh_atlas(out: Path = DEFAULT_OUT) -> dict[str, Any] | None:
    """What the recordings under ``out`` have shown, up to the newest of them: as last written down if nothing has
    been recorded since, and read again first if something has (about a second for every few hundred saves).
    None if there are no recordings."""
    out = Path(out)
    newest = written = None
    try:
        newest = max((folder.stat().st_mtime for folder in out.glob("*/snapshots")), default=None)
        written = (out / "world_progress_atlas.json").stat().st_mtime
    except OSError:
        pass  # no recordings, or recordings and nothing written down about them yet
    atlas = load_atlas(out)
    if newest is not None and (atlas is None or written is None or newest > written or atlas.get("format") != ATLAS_FORMAT):
        try:
            write_atlas(out)
        except OSError:
            return build_atlas(out)  # it can't be written down here: read it all the same
        atlas = load_atlas(out)
    return atlas


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
