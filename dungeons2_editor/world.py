"""What the editor knows of the game's world, and what a save shows of it that the editor doesn't know yet.

The game keeps its quests, doors, minecart stations and regions in its encrypted files, so the editor learns them
the way it learns items: from saves. data/world.json is what it has so far: every quest with its steps, every door
with its place, the stations, regions, cutscenes, areas and puzzle pieces that any save sent to it has shown, and,
from play recordings, where chests were opened and where stations and cutscenes turned up.

Share item IDs… adds what your saves show that this list doesn't have (``lines``), and tools/build_world_list.py
puts a list someone sent into it (``read_list``, ``merge``). Only the game's own names and numbers go into a list:
no hero's ID or name, nothing from your inventory, and nothing about when you played.
"""

from __future__ import annotations

import base64
import functools
import json
import re
from typing import Any

from . import paths, recorder

WORLD_FILE = paths.resource("dungeons2_editor/data/world.json")
MAX_CHARS = 30_000  # the world's part of one list at most, so that the whole of it can be posted
MAX_PICTURE = 3000  # squares in a region's picture of the fog at most, for it to go into a list with a region that's new
SAVES_HEADER = "The world, as your saves show it (what the editor's list doesn't have yet):"
PLACES_HEADER = "Where your recordings saw things turn up:"
LEFT_OUT = "more lines were left out to keep this short enough to post: share again after the editor's next update)"
# What a list holds, in the order a shared list tells it.
SIMPLE = ("stations", "cutscenes", "gimmicks", "areas")  # plain lists of the game's own tags
WORD = {"stations": "station", "cutscenes": "cutscene", "gimmicks": "gimmick", "areas": "area"}
_STEP = re.compile(r"^(=)?([A-Za-z0-9_.\-]+)(?:[+~][0-9.]*|\?[A-Za-z]+)?$")
_DOOR = re.compile(r"at (-?[\d.]+), (-?[\d.]+), (-?[\d.]+); marker (-?\d+)")
_REGION = re.compile(r"corner (-?[\d.]+), (-?[\d.]+); (\d+) across, (\d+) down(?:; fog (\S+))?")
_AROUND = re.compile(r"around (-?\d+), (-?\d+) in (\S+)$")
_OPENED = re.compile(r"^(\d+) opened in ([^,\s]+)(?:, around (-?\d+), (-?\d+) in (\S+))?$")
_PIECE = re.compile(r"([^/.:]+):PersistentLevel\.(.+?)_C_(UAID_[0-9A-Za-z_]+)$")
_TAG = re.compile(r"[A-Za-z0-9_.\-]{1,120}")  # one of the game's own names


def empty() -> dict[str, Any]:
    return {
        "quests": {},  # a quest, as a save names it: its steps, in the order of the save that first showed it
        "stations": [], "cutscenes": [], "gimmicks": [], "areas": [],
        "doors": {},  # a door: {"at": [x, y, z] in metres, "marker": the kind of marker the map gives it}
        "regions": {},  # a region with a picture of its fog: {"corner": [x, y] in metres, "size": [squares across, down]}
        "achievements": {},  # an achievement: the group a save keeps it in
        "progression": {},  # a list under a save's Ability, by its name: the tags seen in it
        "pieces": {},  # a puzzle piece (a roadblock, a bridge, a key golem's lock): {"path": as saved, "states": [[before, now]]}
        "found": {},  # from recordings: "minecart station <tag>" or "cutscene <tag>": [{"region", "at": [x, y]}] where it turned up
        "chests": [],  # from recordings: {"area", "region", "at": [x, y], "opened"} each time chests were opened with a spot to give
        "chest_counts": {},  # from recordings: an area: the most chests one player's recordings saw opened there
    }


@functools.lru_cache(maxsize=1)
def known() -> dict[str, Any]:
    """The editor's own list of the world. Empty if the file isn't there or can't be read."""
    try:
        loaded = json.loads(WORLD_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    return merge(empty(), loaded if isinstance(loaded, dict) else {})


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _tag(value: object) -> str | None:
    """One of the game's own names, or nothing: whatever else a save may hold where a name belongs stays out."""
    return value if isinstance(value, str) and _TAG.fullmatch(value) else None


def piece_key(path: str) -> str:
    """A puzzle piece by what stays the same wherever its level is put: the level, what it is, and its own ID."""
    match = _PIECE.search(path)
    return " ".join(match.groups()) if match else path.rsplit("/", 1)[-1][-100:]


def of_save(document: Any) -> dict[str, Any]:
    """What one hero save shows of the world, laid out like the editor's list. Two things more ride along for a
    shared list to tell, which no list keeps: how each quest and step stands ("states") and each region's picture
    of the fog ("pictures")."""
    shown = empty()
    shown["states"], shown["pictures"] = {}, {}
    body = _dict(document).get("CharacterSaveV1")
    if not isinstance(body, dict):
        return shown
    area = _tag(_dict(body.get("MetaData")).get("CurrentLocation"))
    if area:
        shown["areas"].append(area)
    for quest in _list(_dict(body.get("quest")).get("Quests")):
        name = _tag(quest.get("QuestName")) if isinstance(quest, dict) else None
        if not name:
            continue
        steps = shown["quests"].setdefault(name, [])
        shown["states"][name] = _tag(quest.get("State")) or "?"
        for task in _list(quest.get("TaskData")):
            step = _tag(task.get("TaskName")) if isinstance(task, dict) else None
            if step and step not in steps:
                steps.append(step)
                partial = task.get("PartialProgress")
                count = json.dumps(partial) if isinstance(partial, (int, float)) and not isinstance(partial, bool) and partial else ""
                state = task.get("State")
                shown["states"][f"{name} {step}"] = "+" + count if state == "Completed" else "~" + count if state == "Active" else "" if state == "NotSet" else f"?{_tag(state) or 'Other'}"
    world = _dict(body.get("WorldExploration"))
    for kind, field in (("stations", "DiscoveredMinecartStationTags"), ("cutscenes", "SavedCutsceneTags"), ("gimmicks", "ActivatedGimmickTags")):
        shown[kind] += [tag for tag in map(_tag, _list(world.get(field))) if tag and tag not in shown[kind]]
    for door in _list(world.get("DiscoveredDungeonDoors")):
        name, place = (_tag(door.get("DoorId")), door.get("Location")) if isinstance(door, dict) else (None, None)
        if name and isinstance(place, dict) and all(isinstance(place.get(axis), (int, float)) and not isinstance(place.get(axis), bool) for axis in "XYZ"):
            marker = door.get("MarkerType")
            shown["doors"][name] = {"at": [round(place[axis] / 100, 1) for axis in "XYZ"], "marker": marker if isinstance(marker, int) else -1}
    for tag, region in recorder.map_regions(document).items():
        if _tag(tag) and all(isinstance(region[side], (int, float)) for side in ("x", "y")):
            shown["regions"][tag] = {"corner": [region["x"], region["y"]], "size": [region["across"], region["down"]]}
            shown["pictures"][tag] = region["cells"]
    for actor in _list(world.get("SavedActorStates")):
        path = actor.get("SoftObjectPath") if isinstance(actor, dict) else None
        if isinstance(path, str) and path.startswith("/Game/") and len(path) < 400 and "\n" not in path:
            states = [actor.get("PreviousState"), actor.get("CurrentState")]
            if all(isinstance(state, int) for state in states):
                piece = shown["pieces"].setdefault(piece_key(path), {"path": path, "states": []})
                if states not in piece["states"]:
                    piece["states"].append(states)
    for group, entries in _dict(body.get("Achievements")).items():
        for name in entries if isinstance(entries, dict) and _tag(group) else []:
            if _tag(name):
                shown["achievements"][name] = group
    for key, value in _dict(body.get("Ability")).items():
        if key != "Attributes" and _tag(key) and isinstance(value, list):
            tags = [tag for tag in map(_tag, value) if tag]
            if tags:
                shown["progression"][key] = tags
    return shown


def _spot(value: object) -> list | None:
    """A place as an atlas keeps it, two numbers, or nothing."""
    return value if isinstance(value, list) and len(value) == 2 and all(isinstance(part, (int, float)) and not isinstance(part, bool) for part in value) else None


def of_recordings(atlas: dict[str, Any] | None) -> dict[str, Any]:
    """What the play recorder's recordings add (recorder.fresh_atlas), laid out like the editor's list: the areas
    the hero was saved in, where a minecart station or a cutscene turned up, and the chests opened."""
    shown = empty()
    if not isinstance(atlas, dict):
        return shown
    shown["areas"] = [tag for tag in map(_tag, _list(atlas.get("locations"))) if tag]
    for label, place in _dict(atlas.get("found_at")).items():
        near = _spot(place.get("near")) if isinstance(place, dict) else None
        if label.startswith(("minecart station ", "cutscene ")) and _tag(label.rsplit(" ", 1)[-1]) and near and _tag(place.get("region")):
            shown["found"].setdefault(label, []).append({"region": place["region"], "at": [round(near[0]), round(near[1])]})
    for chest in _list(atlas.get("chests")):
        area, opened = (_tag(chest.get("area")), chest.get("opened")) if isinstance(chest, dict) else (None, None)
        if not area or not isinstance(opened, int) or isinstance(opened, bool) or opened < 1:
            continue  # between two recordings: nothing says where
        near = _spot(chest.get("near"))
        if near and _tag(chest.get("region")):
            shown["chests"].append({"area": area, "region": chest["region"], "at": [round(near[0]), round(near[1])], "opened": opened})
        shown["chest_counts"][area] = shown["chest_counts"].get(area, 0) + opened
    return shown


def merge(into: dict[str, Any], more: dict[str, Any]) -> dict[str, Any]:
    """Add to a list what another has and it doesn't. A quest keeps the order of its steps and gets new ones at
    the end; a door or a region keeps the place it has, and a different place for it is kept beside that
    ("also"), since one of them needs looking at. Returns the list added to."""
    for name, steps in (more.get("quests") or {}).items():
        mine = into["quests"].setdefault(name, [])
        mine += [step for step in steps if step not in mine]
    for kind in SIMPLE:
        into[kind] += [tag for tag in more.get(kind) or [] if tag not in into[kind]]
    for kind in ("doors", "regions"):
        for name, entry in (more.get(kind) or {}).items():
            mine = into[kind].setdefault(name, dict(entry))
            if not same_place(kind, mine, entry) and not any(same_place(kind, other, entry) for other in mine.get("also", [])):
                mine.setdefault("also", []).append({key: value for key, value in entry.items() if key != "also"})
    for name, group in (more.get("achievements") or {}).items():
        into["achievements"].setdefault(name, group)
    for key, tags in (more.get("progression") or {}).items():
        mine = into["progression"].setdefault(key, [])
        mine += [tag for tag in tags if tag not in mine]
    for key, piece in (more.get("pieces") or {}).items():
        mine = into["pieces"].setdefault(key, {"path": piece.get("path", ""), "states": []})
        mine["states"] += [states for states in piece.get("states") or [] if states not in mine["states"]]
    for label, places in (more.get("found") or {}).items():
        mine = into["found"].setdefault(label, [])
        mine += [place for place in places if place not in mine]
    into["chests"] += [chest for chest in more.get("chests") or [] if chest not in into["chests"]]
    for area, count in (more.get("chest_counts") or {}).items():
        into["chest_counts"][area] = max(into["chest_counts"].get(area, 0), count)
    return into


def same_place(kind: str, one: dict, other: dict) -> bool:
    """Whether two entries for a door put it within a metre of the same spot, or two for a region give its picture
    the same corner and size."""
    if kind == "doors":
        return all(abs(a - b) <= 1 for a, b in zip(one.get("at") or [], other.get("at") or [])) and len(one.get("at") or []) == len(other.get("at") or [])
    return one.get("corner") == other.get("corner") and one.get("size") == other.get("size")


def news(shown: dict[str, Any], have: dict[str, Any] | None = None) -> dict[str, Any]:
    """The part of what saves or recordings show that a list (the editor's own, if none is given) doesn't have,
    laid out the same way. A quest with steps the list lacks comes whole, so its order can be seen."""
    have = known() if have is None else have
    new = empty()
    for name, steps in shown["quests"].items():
        if name not in have["quests"] or any(step not in have["quests"][name] for step in steps):
            new["quests"][name] = list(steps)
    for kind in SIMPLE:
        new[kind] = [tag for tag in shown[kind] if tag not in have[kind]]
    for kind in ("doors", "regions"):
        for name, entry in shown[kind].items():
            mine = have[kind].get(name)
            if mine is None or not (same_place(kind, mine, entry) or any(same_place(kind, other, entry) for other in mine.get("also", []))):
                new[kind][name] = entry
    new["achievements"] = {name: group for name, group in shown["achievements"].items() if name not in have["achievements"]}
    for key, tags in shown["progression"].items():
        fresh = [tag for tag in tags if tag not in have["progression"].get(key, [])]
        if fresh:
            new["progression"][key] = fresh
    for key, piece in shown["pieces"].items():
        fresh = [states for states in piece["states"] if states not in (have["pieces"].get(key) or {}).get("states", [])]
        if fresh:
            new["pieces"][key] = {"path": piece["path"], "states": fresh}
    for label, places in shown["found"].items():
        fresh = [place for place in places if place not in have["found"].get(label, [])]
        if fresh:
            new["found"][label] = fresh
    new["chests"] = [chest for chest in shown["chests"] if chest not in have["chests"]]
    new["chest_counts"] = {area: count for area, count in shown["chest_counts"].items() if count > have["chest_counts"].get(area, 0)}
    return new


def of_saves(documents: list[Any]) -> dict[str, Any]:
    """What several hero saves show between them."""
    shown = empty()
    shown["states"], shown["pictures"] = {}, {}
    for document in documents:
        one = of_save(document)
        merge(shown, one)
        for extra in ("states", "pictures"):
            for key, value in one[extra].items():
                shown[extra].setdefault(key, value)
    return shown


def keys(documents: list[Any]) -> set[str]:
    """A key for each thing these saves show of the world that the editor's list doesn't have: what the editor
    remembers having shown you, so that it can tell when your saves hold something more."""
    new = news(of_saves(documents))
    found = {f"world quest {name}" for name in new["quests"]}
    for kind in SIMPLE + ("doors", "regions", "achievements"):
        found |= {f"world {WORD.get(kind, kind[:-1])} {name}" for name in new[kind]}
    found |= {f"world progression {key} {tag}" for key, tags in new["progression"].items() for tag in tags}
    found |= {f"world piece {key} {before}>{now}" for key, piece in new["pieces"].items() for before, now in piece["states"]}
    return found


def _step(quest: str, step: str, states: dict[str, str]) -> str:
    """A step the short way: without its quest's name in front (=whole name, if it doesn't start with it), and
    with how it stands after it."""
    short = step[len(quest) + 1:] if step.startswith(quest + "_") and len(step) > len(quest) + 1 else "=" + step
    return short + states.get(f"{quest} {step}", "")


def _number(value: float) -> str:
    return json.dumps(int(value) if float(value).is_integer() else value)


def lines_of(new: dict[str, Any], states: dict[str, str] | None = None, pictures: dict[str, list[int]] | None = None, have: dict[str, Any] | None = None) -> list[str]:
    """What a list holds, a line to a thing, as ``read_list`` reads it back. ``states`` and ``pictures`` are what
    a save adds for a shared list (``of_save``); ``have`` is the list it's compared with, for saying what differs."""
    have = known() if have is None else have
    states, pictures, told = states or {}, pictures or {}, []
    for name, steps in new["quests"].items():
        note = "more steps than the editor's list has; " if name in have["quests"] else ""
        how = f"{states[name]}; " if name in states else ""
        told.append(f"quest {name} - {how}{note}steps: {', '.join(_step(name, step, states) for step in steps)}")
    for name, door in new["doors"].items():
        there = have["doors"].get(name)
        note = f"; the editor's list has it at {', '.join(_number(value) for value in there['at'])}" if there else ""
        told.append(f"door {name} - at {', '.join(_number(value) for value in door['at'])}; marker {door['marker']}{note}")
    for tag in new["stations"]:
        name = recorder.station_name(tag)
        told.append(f"station {tag}" + (f" - {name}" if name != tag.removeprefix("SW.MinecartStation.") else ""))
    for tag, region in new["regions"].items():
        cells = pictures.get(tag) or []
        fog = "; fog " + base64.b64encode(bytes(min(max(cell, 0), 255) for cell in cells)).decode("ascii") if 0 < len(cells) <= MAX_PICTURE and any(cells) else ""
        note = "; the editor's list has it elsewhere" if tag in have["regions"] else ""
        told.append(f"region {tag} - corner {_number(region['corner'][0])}, {_number(region['corner'][1])}; {region['size'][0]} across, {region['size'][1]} down{fog}{note}")
    told += [f"cutscene {tag}" for tag in new["cutscenes"]] + [f"gimmick {tag}" for tag in new["gimmicks"]]
    for tag in new["areas"]:
        name = recorder.area_name(tag)
        told.append(f"area {tag}" + (f" - {name}" if name != tag.removeprefix("SW.Area.") else ""))
    told += [f"achievement {name} - {group}" for name, group in new["achievements"].items()]
    told += [f"progression {key} {tag}" for key, tags in new["progression"].items() for tag in tags]
    for key, piece in new["pieces"].items():
        told.append(f"piece {key} - {'; '.join(f'{before} then {now}' for before, now in piece['states'])}; as saved: {piece['path']}")
    for label, places in new["found"].items():
        told += [f"found {label} - around {place['at'][0]}, {place['at'][1]} in {place['region']}" for place in places]
    told += [f"chest - {chest['opened']} opened in {chest['area']}, around {chest['at'][0]}, {chest['at'][1]} in {chest['region']}" for chest in new["chests"]]
    told += [f"chests - {count} opened in {area}" for area, count in new["chest_counts"].items()]
    return told


def lines(documents: list[Any], atlas: dict[str, Any] | None = None, most: int = MAX_CHARS) -> list[str]:
    """The world's part of a Share item IDs list: under a heading each, what these saves show that the editor's
    list doesn't have, and what the recordings saw turn up where. Empty when there's nothing to tell. No more
    than ``most`` characters: what doesn't fit is left for the next time, and the last line says how much."""
    shown = of_saves(documents)
    from_saves = lines_of(news(shown), shown["states"], shown["pictures"])
    seen = merge(empty(), shown)  # an area the saves already tell of isn't told again from the recordings
    from_recordings = lines_of(news(news(of_recordings(atlas), seen)))
    told, room, left = [], most, 0
    for heading, part in ((SAVES_HEADER, from_saves), (PLACES_HEADER, from_recordings)):
        kept = []
        for line in part:
            if len(line) + 1 <= room:
                kept.append(line)
                room -= len(line) + 1
            else:
                left += 1
        if kept:
            told += ([""] if told else []) + [heading] + kept
    return told + ([f"({left} {LEFT_OUT}"] if left else [])


def read_list(text: str) -> dict[str, Any]:
    """A shared list's world lines, as a list like the editor's own (the reverse of ``lines_of``). Lines that
    aren't about the world (the item IDs above them, the headings) are passed over. The pictures of the fog that
    came with regions are under "pictures", for working out how such a picture lies; no list keeps them."""
    found = empty()
    found["pictures"] = {}
    for line in text.splitlines():
        head, _dash, rest = line.strip().partition(" - ")
        word, _space, name = head.partition(" ")
        if word == "quest" and "steps: " in rest:
            steps = found["quests"].setdefault(name, [])
            for token in rest.rsplit("steps: ", 1)[1].split(", "):
                match = _STEP.match(token.strip())
                if match:
                    step = match.group(2) if match.group(1) else f"{name}_{match.group(2)}"
                    if step not in steps:
                        steps.append(step)
        elif word == "door" and _DOOR.search(rest):
            x, y, z, marker = _DOOR.search(rest).groups()
            found["doors"][name] = {"at": [float(x), float(y), float(z)], "marker": int(marker)}
        elif word == "region" and _REGION.search(rest):
            x, y, across, down, fog = _REGION.search(rest).groups()
            found["regions"][name] = {"corner": [float(x) if "." in x else int(x), float(y) if "." in y else int(y)], "size": [int(across), int(down)]}
            if fog:
                try:
                    found["pictures"][name] = list(base64.b64decode(fog, validate=True))
                except ValueError:
                    pass
        elif word in ("station", "cutscene", "gimmick", "area") and _tag(name):
            kind = word + "s"
            if name not in found[kind]:
                found[kind].append(name)
        elif word == "achievement" and _tag(name) and _tag(rest):
            found["achievements"][name] = rest
        elif word == "progression" and len(name.split(" ")) == 2:
            key, tag = name.split(" ")
            found["progression"].setdefault(key, []).append(tag)
        elif word == "piece" and "; as saved: " in rest:
            states, path = rest.rsplit("; as saved: ", 1)
            pairs = [[int(a), int(b)] for a, b in re.findall(r"(-?\d+) then (-?\d+)", states)]
            found["pieces"][name] = {"path": path, "states": pairs}
        elif word == "found" and _AROUND.search(rest):
            x, y, region = _AROUND.search(rest).groups()
            found["found"].setdefault(name, []).append({"region": region, "at": [int(x), int(y)]})
        elif word in ("chest", "chests") and not name and _OPENED.match(rest):
            opened, area, x, y, region = _OPENED.match(rest).groups()
            if region:
                found["chests"].append({"area": area, "region": region, "at": [int(x), int(y)], "opened": int(opened)})
            else:
                found["chest_counts"][area] = max(found["chest_counts"].get(area, 0), int(opened))
    return found


def counts(world: dict[str, Any]) -> str:
    """A list in a line: how many of each thing it holds."""
    steps = sum(len(steps) for steps in world["quests"].values())
    return (
        f"{len(world['quests'])} quests ({steps} steps), {len(world['doors'])} doors, {len(world['stations'])} minecart stations, {len(world['regions'])} regions, "
        f"{len(world['cutscenes'])} cutscenes, {len(world['areas'])} areas, {len(world['achievements'])} achievements, {len(world['pieces'])} puzzle pieces, "
        f"{sum(len(places) for places in world['found'].values())} places things turned up, {len(world['chests'])} chest spots"
    )
