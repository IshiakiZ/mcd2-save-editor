"""A hero's story: its quests, how each of them stands, and the few changes the editor makes to them.

How a save keeps the story, in every hero save the editor has been shown: quest.Quests lists each quest the hero
has met, with how it stands (State: Unavailable, Available, Active or Completed) and its steps (TaskData), each
with how it stands (NotSet, Active or Completed) and a number (PartialProgress: how many of a thing are done, for
a step that counts). quest.FocusedQuestId is the quest the game tracks on screen. A quest the hero hasn't met
isn't listed at all.

Three things hold in every one of those saves, and they are all the editor writes:

    a finished quest has every one of its steps finished (26 finished quests of five heroes, not a step left over)
    a quest that's available and not begun has every step unset
    when the game finishes a quest it stops tracking it, and lists the quests it opens next as available

So the editor finishes a quest (every step done, with the number the game saved with a step where a save has shown
it), starts one over (available again, every step unset), adds one the hero hasn't met (available, every step
unset, its steps as another hero's save listed them) and picks the quest the game tracks. It doesn't move a quest
on by a single step: steps come in groups that run in order, side by side or by choice, a save lists them flat,
and which step follows which is in the game's own files.

What the game gives for a quest (items, XP, an achievement) it gives when it finishes the quest itself. The editor
writes none of that.

Checked in the game (1.1.2.0, October 2026): with The Missing Note Blocks finished this way, the game loaded the
hero, opened the four quests that follow it by itself (the next main quest active, three more available), gave no
item, XP or achievement for the quest, and played on from there.

Where a hero starts: a save keeps no position, only the minecart station the hero was last at
(WorldExploration.LastMinecartStation) and the area it was in (MetaData.CurrentLocation). ``start_at`` writes the
two the way a save has them for a hero standing at that station. Checked in the game the same day: a hero saved
in Howling Woods and set to the Frozen Fortress station was standing in Frozen Highlands when the game loaded it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import recorder, world

UNAVAILABLE, AVAILABLE, ACTIVE, DONE = "Unavailable", "Available", "Active", "Completed"
NOT_SET = "NotSet"
STATE_WORDS = {UNAVAILABLE: "not open yet", AVAILABLE: "available", ACTIVE: "active", DONE: "finished"}
TOWN_FOUNTAIN = "SW.MinecartStation.Town.Fountain"  # where a hero starts out: a save names it, and never among the stations found
MAIN, OTHER = "Main story", "Other quests"
NO_QUESTS = "This hero's save keeps no quests yet. Play until the game has given you the first one."
NO_STATION = "This hero's save doesn't say where the hero was last. Play until the game has saved it once."
STEP_NOTE = "What a step is about is read off its name (E is a place to reach, K enemies to defeat): the editor's reading, not the game's words."
# What a step's name says it's about: the letters after its quest's name, as the game's own goals are called
# (ExploreGoal, InteractGoal, KillGoal and so on, in its readable scripts). The editor's reading, not the game's words.
STEP_KINDS = {
    "E": "reach a place", "I": "interact with something", "K": "defeat enemies", "SM": "enemies appear", "PC": "a cutscene",
    "MT": "someone walks somewhere", "A": "an arena fight", "Arena": "an arena fight", "Follow": "follow someone",
    "Sequence": "a group of steps, one after the other", "Standard": "a group of steps, in any order", "Selection": "a choice between steps",
}
_MAIN = re.compile(r"CA\d\d(_|$)")  # CA04, CA02_B, CA10_BR_B
_SIDE = re.compile(r"([A-Z]{2})a(\d)_S\d")  # PLa1_S04_A: a side quest of the first plains
_AREAS = {"PL": "Plains", "FO": "Forest", "DE": "Desert", "ME": "Meadow", "CA": "Carapace"}
_STEP = re.compile(r"([A-Za-z]+?)(\d.*)?$")
_AREA_CODE = re.compile(r"([A-Za-z]+?)(A\d+)$")  # ForestA1, as a station's tag has it


@dataclass(frozen=True)
class Step:
    name: str  # as the save names it: CA01_K02
    state: str
    count: int  # how many of the thing it counts are done
    quest: str

    @property
    def short(self) -> str:
        """Its name without its quest's in front: K02."""
        return self.name[len(self.quest) + 1:] if self.name.startswith(self.quest + "_") and len(self.name) > len(self.quest) + 1 else self.name

    @property
    def kind(self) -> str:
        """What its name says it's about, where the editor can read that. Otherwise nothing."""
        match = _STEP.match(self.short)
        return STEP_KINDS.get(match.group(1), "") if match else ""

    @property
    def is_group(self) -> bool:
        return self.kind.startswith(("a group", "a choice"))


@dataclass(frozen=True)
class Quest:
    name: str  # as the save names it: CA04
    state: str | None  # None for a quest the hero hasn't met, which the editor knows from other heroes' saves
    steps: tuple[Step, ...]
    tracked: bool = False

    @property
    def met(self) -> bool:
        return self.state is not None

    @property
    def title(self) -> str:
        """What the game calls it, where that's known."""
        return recorder.QUESTS.get(self.name, "")

    @property
    def label(self) -> str:
        return label(self.name)

    @property
    def group(self) -> str:
        return group_of(self.name)

    @property
    def done(self) -> int:
        return sum(1 for step in self.steps if step.state == DONE)

    @property
    def standing(self) -> str:
        """How it stands, in a word or two."""
        return "not met yet" if self.state is None else STATE_WORDS.get(self.state, self.state)


def label(name: str) -> str:
    """A quest to read: what the game calls it, where that's known, with the save's name for it."""
    title = recorder.QUESTS.get(name, "")
    return f"{title} ({name})" if title else name


def group_of(name: str) -> str:
    """The part of the game a quest belongs to, read off its name: the main story (CA04), an area's side quests
    (PLa1_S04_A is one of Honeycomb Fields'), or the rest."""
    if _MAIN.match(name):
        return MAIN
    side = _SIDE.match(name)
    if side and side.group(1) in _AREAS:
        code = f"{_AREAS[side.group(1)]}A{side.group(2)}"
        return f"Side quests: {recorder.AREAS.get(code) or recorder._words(code)}"
    if side and side.group(1) == "TO":
        return f"Side quests: {recorder.AREAS['Town']}"
    return OTHER


def group_order(name: str) -> tuple:
    """Where a group goes in a list of them: the main story, the side quests by area, then the rest."""
    return (0 if name == MAIN else 2 if name == OTHER else 1, name)


def _natural(name: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _body(document: Any) -> dict:
    body = document.get("CharacterSaveV1") if isinstance(document, dict) else None
    return body if isinstance(body, dict) else {}


def _section(document: Any) -> dict:
    """The part of a save that keeps the quests. An error if this one keeps none."""
    section = _body(document).get("quest")
    if not isinstance(section, dict) or not isinstance(section.get("Quests"), list):
        raise ValueError(NO_QUESTS)
    return section


def _entry(section: dict, name: str) -> dict:
    for entry in section["Quests"]:
        if isinstance(entry, dict) and entry.get("QuestName") == name:
            if not isinstance(entry.get("TaskData"), list) or not all(isinstance(task, dict) for task in entry["TaskData"]):
                raise ValueError(f"The save keeps {name} in a way the editor hasn't seen, so it leaves it alone.")
            return entry
    raise ValueError(f"This hero hasn't met the quest {name}.")


def _quest(entry: dict, tracked: str | None) -> Quest:
    name = str(entry.get("QuestName"))
    steps = []
    for task in entry.get("TaskData") or []:
        if isinstance(task, dict):
            count = task.get("PartialProgress")
            steps.append(Step(str(task.get("TaskName")), str(task.get("State")), count if isinstance(count, int) and not isinstance(count, bool) else 0, name))
    return Quest(name, str(entry.get("State")), tuple(steps), tracked == name)


def quests(document: Any) -> list[Quest]:
    """The quests a hero has met, in the save's own order. None of them for a save that keeps no quests."""
    section = _body(document).get("quest")
    listed = section.get("Quests") if isinstance(section, dict) else None
    tracked = section.get("FocusedQuestId") if isinstance(section, dict) else None
    return [_quest(entry, tracked) for entry in listed if isinstance(entry, dict) and isinstance(entry.get("QuestName"), str)] if isinstance(listed, list) else []


def unmet(document: Any) -> list[Quest]:
    """The quests the editor knows from other heroes' saves that this hero hasn't met, by name."""
    have = {quest.name for quest in quests(document)}
    known = world.known()["quests"]
    return [Quest(name, None, tuple(Step(step, NOT_SET, 0, name) for step in known[name])) for name in sorted(known, key=_natural) if name not in have and known[name]]


def every(document: Any) -> list[Quest]:
    """A hero's quests and the ones it hasn't met, group by group (group_order) and by name within one."""
    return sorted(quests(document) + unmet(document), key=lambda quest: (group_order(quest.group), _natural(quest.name)))


def tracked(document: Any) -> str:
    """The quest the game tracks on screen for this hero, as the save names it. Nothing if it tracks none."""
    section = _body(document).get("quest")
    name = section.get("FocusedQuestId") if isinstance(section, dict) else None
    return name if isinstance(name, str) else ""


def follows(name: str) -> list[str]:
    """The quests the game made available as it finished this one, where a play recording has shown that."""
    return list(world.known()["follows"].get(name, []))


def finish(document: Any, name: str) -> list[str]:
    """Finish a quest the hero has met, the way a save holds a finished one: the quest and every one of its steps
    Completed, a step that counts with the number the game saved with it where a save has shown that, and the
    quest no longer the one tracked. Where a recording has shown which quests the game makes available as it
    finishes this one, the ones the hero hasn't met are added too. Returns the quests added."""
    section = _section(document)
    entry = _entry(section, name)
    if entry.get("State") == DONE:
        raise ValueError(f"{label(name)} is finished already.")
    counts = world.known()["counts"]
    for task in entry["TaskData"]:
        task["State"] = DONE
        count, had = counts.get(task.get("TaskName")), task.get("PartialProgress")
        if count and not (isinstance(had, int) and not isinstance(had, bool) and had >= count):
            task["PartialProgress"] = count
    entry["State"] = DONE
    if section.get("FocusedQuestId") == name:
        section["FocusedQuestId"] = ""
    have = {quest.name for quest in quests(document)}
    added = [quest for quest in follows(name) if quest not in have and world.known()["quests"].get(quest)]
    for quest in added:
        add(document, quest)
    return added


def start_over(document: Any, name: str) -> None:
    """Put a quest the hero has begun or finished back to where the game has one that's open and not begun:
    Available, every step NotSet and counting from nothing, and not the quest tracked."""
    section = _section(document)
    entry = _entry(section, name)
    if entry.get("State") not in (ACTIVE, DONE):
        raise ValueError(f"{label(name)} hasn't been begun, so there's nothing to start over.")
    for task in entry["TaskData"]:
        task["State"] = NOT_SET
        task["PartialProgress"] = 0
    entry["State"] = AVAILABLE
    if section.get("FocusedQuestId") == name:
        section["FocusedQuestId"] = ""


def add(document: Any, name: str) -> None:
    """Add a quest the hero hasn't met, the way the game lists one it has just opened: Available, with every step
    NotSet. The steps are the ones another hero's save listed for it, in that save's order."""
    section = _section(document)
    steps = world.known()["quests"].get(name)
    if not steps:
        raise ValueError(f"The editor hasn't seen the quest {name} in a save, so it doesn't know its steps.")
    if any(isinstance(entry, dict) and entry.get("QuestName") == name for entry in section["Quests"]):
        raise ValueError(f"This hero has met {label(name)} already.")
    section["Quests"].append({"QuestName": name, "State": AVAILABLE, "TaskData": [{"TaskName": step, "State": NOT_SET, "PartialProgress": 0} for step in steps]})


def track(document: Any, name: str) -> None:
    """Make an active quest the one the game tracks on screen, or with no name, track none."""
    section = _section(document)
    if name and _entry(section, name).get("State") != ACTIVE:
        raise ValueError("Only an active quest can be the one the game tracks.")
    section["FocusedQuestId"] = name


# ------------------------------------------------------------------ where the hero starts

def area_of(station: str) -> str | None:
    """The area a minecart station is in, as a save names areas: SW.MinecartStation.ForestA1.Outpost is in
    SW.Area.Forest.A1. Only an area a save has named, itself or a place inside it; otherwise nothing."""
    code = recorder.station_key(station).split(".")[0]
    code = "Town" if code == "TownFountain" else code
    match = _AREA_CODE.match(code)
    tag = "SW.Area.Town" if code == "Town" else f"SW.Area.{match.group(1)}.{match.group(2)}" if match else None
    seen = list(world.known()["areas"]) + list(world.known()["regions"])
    return tag if tag and any(known == tag or known.startswith(tag + ".") for known in seen) else None


def station_label(tag: str) -> str:
    """A station to pick from a list: what the game calls it, and its area."""
    name, there = recorder.station_name(tag), area_of(tag)
    return name if "(" in name or not there else f"{name} ({recorder.area_name(there)})"


def last_station(document: Any) -> str:
    """The minecart station the save says the hero was last at. Nothing if it doesn't say."""
    place = _body(document).get("WorldExploration")
    tag = place.get("LastMinecartStation") if isinstance(place, dict) else None
    return tag if isinstance(tag, str) else ""


def area(document: Any) -> str:
    """The area the save says the hero is in. Nothing if it doesn't say."""
    meta = _body(document).get("MetaData")
    tag = meta.get("CurrentLocation") if isinstance(meta, dict) else None
    return tag if isinstance(tag, str) else ""


def start_points(document: Any) -> list[str]:
    """Where the editor can have a hero start: the town's fountain, and every minecart station the hero has found."""
    place = _body(document).get("WorldExploration")
    found = place.get("DiscoveredMinecartStationTags") if isinstance(place, dict) else None
    if not isinstance(place, dict) or not isinstance(place.get("LastMinecartStation"), str):
        return []
    return [TOWN_FOUNTAIN] + [tag for tag in found or [] if isinstance(tag, str) and tag != TOWN_FOUNTAIN]


def start_at(document: Any, station: str) -> None:
    """Have the save say the hero was last at a minecart station it has found (or the town's fountain), in that
    station's area: the two things a save keeps about where a hero is."""
    if station not in start_points(document):
        raise ValueError(NO_STATION if not start_points(document) else f"This hero hasn't found {recorder.station_name(station)}. Find it in the game, or add it with the Every minecart station preset.")
    body = _body(document)
    body["WorldExploration"]["LastMinecartStation"] = station
    there, meta = area_of(station), body.get("MetaData")
    if there and isinstance(meta, dict) and isinstance(meta.get("CurrentLocation"), str):
        meta["CurrentLocation"] = there


# ------------------------------------------------------------------ what changed

def changes(before: Any, after: Any) -> list[str]:
    """What differs between two versions of a hero's save in its story and where it starts, a line each."""
    old, lines = {quest.name: quest for quest in quests(before)}, []
    for quest in quests(after):
        was = old.pop(quest.name, None)
        if was is None:
            lines.append(f"Quest {quest.label}: added, {quest.standing}")
        elif (was.state, was.steps) != (quest.state, quest.steps):
            if quest.state == DONE and was.state != DONE:
                how = "finished"
            elif quest.state == AVAILABLE and was.state in (ACTIVE, DONE):
                how = "started over"
            elif was.state != quest.state:
                how = f"{was.standing} → {quest.standing}"
            else:
                how = f"{quest.done} of {len(quest.steps)} steps done (it was {was.done})"
            lines.append(f"Quest {quest.label}: {how}")
    lines += [f"Quest {quest.label}: taken out" for quest in old.values()]
    if tracked(before) != tracked(after):
        lines.append(f"Quest tracked: {label(tracked(after)) if tracked(after) else 'none'}")
    if (last_station(before), area(before)) != (last_station(after), area(after)):
        lines.append(f"Starts at: {recorder.station_name(last_station(after))}, in {recorder.area_name(area(after))}")
    return lines
