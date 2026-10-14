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

A finished step carries a number where it counts something. In the saves the editor could not have written a
quest into (players' lists made before 1.16.0, and the developer's recordings up to then): a step to defeat
enemies carries how many (1 to 10), a step to interact with something carries 1 (153 of them; two carry none,
NO_NUMBER), and every other kind carries none (476 of them). 1.16.0 wrote a number only where a save had shown it
for that very step, and so left interact steps of quests nobody had sent finished without theirs. Since 1.16.1 a
finished interact step gets its 1, and a quest finished without can be finished again to be given it. Nothing has
shown the game to mind the difference: the number is written because that is how a save holds a finished step.

So the editor finishes a quest (every step done, with the number a save holds with a finished step), starts one
over (available again, every step unset), adds one the hero hasn't met (available, every step
unset, its steps as another hero's save listed them) and picks the quest the game tracks.

It also moves a quest on by one step (``step``). Steps come in groups, and a save lists them flat: which step
follows which is in the game's own quest tables, which a player read out of the game and sent, and the editor's
list has it from them (a group's members one after the other, all at once, or as a choice). The rules: a quest
that's begun has its own group active, and what that group starts with; a group whose members come one after the
other has one of them active at a time; one whose members go all at once has them all active, and is finished
when they all are; a finished group moves its own group on; the quest is finished when its own group is. Replayed
against the developer's play recordings, the rules give the very save the game wrote all 118 times a quest moved
on between two saves, and all 7 times the game began one. A choice between steps is in one quest only, and no
save has shown one under way: there the editor stops, and says so.

What the game gives for a quest (items, XP, an achievement) it gives when it finishes the quest itself. The editor
writes none of that.

Checked in the game (1.1.2.0, October 2026): with The Missing Note Blocks finished this way, the game loaded the
hero, opened the four quests that follow it by itself (the next main quest active, three more available), gave no
item, XP or achievement for the quest, and played on from there. And with every quest the editor knows finished
(44) and the whole map discovered, the game loaded the hero, changed nothing in its quests, kept every picture of
the fog (the nineteen added ones too) and showed the whole map. Four side quests stayed marked on that map as new
ones to take: quests the game lets a hero do again (comes_back), which it offers once more after they're finished.

The map: for each region a hero has been in, a save keeps a picture of the fog over it
(WorldExploration.SavedFogOfWarExploration.Items: the region's tag, where its corner is, how many squares it is
across and down, and a number from 0 to 255 for each square, 255 where the fog is all gone). ``discover_map`` sets
every square of every one of them to 255, and adds the regions the hero hasn't been in that another hero's save
has shown, each with its corner and size as that save had them and every square at 255.

Where a hero starts: a save keeps no position, only the minecart station the hero was last at
(WorldExploration.LastMinecartStation) and the area it was in (MetaData.CurrentLocation). ``start_at`` writes the
two the way a save has them for a hero standing at that station. Checked in the game the same day: a hero saved
in Howling Woods and set to the Frozen Fortress station was standing in Frozen Highlands when the game loaded it.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Iterable

from . import recorder, world

UNAVAILABLE, AVAILABLE, ACTIVE, DONE = "Unavailable", "Available", "Active", "Completed"
NOT_SET = "NotSet"
STATE_WORDS = {UNAVAILABLE: "not open yet", AVAILABLE: "available", ACTIVE: "active", DONE: "finished"}
TOWN_FOUNTAIN = "SW.MinecartStation.Town.Fountain"  # where a hero starts out: a save names it, and never among the stations found
MAIN, OTHER = "Main story", "Other quests"
NO_QUESTS = "This hero's save keeps no quests yet. Play until the game has given you the first one."
NO_STATION = "This hero's save doesn't say where the hero was last. Play until the game has saved it once."
NO_MAP = "This hero's save keeps no map yet. Play until the game has drawn one."
CLEAR = 255  # a square the fog is all gone from, as a save has it
# Interact steps the game has saved as finished with no number: CA07_I12 in two heroes' lists (issues 33 and 34) and
# CA09_I17 in one (issue 33). Every other finished interact step in the saves the editor couldn't have written has 1.
NO_NUMBER = frozenset({"CA07_I12", "CA09_I17"})
MOST_SQUARES = 20_000  # more than any region has: a size beyond this isn't one to write
STEP_NOTE = (
    "A step's words are the game's own, where the editor has them. What a step is about is read off its name (E is a place to reach, "
    "K enemies to defeat): the editor's reading, not the game's words."
)
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
    def words(self) -> str:
        """What the game shows for it on screen, under its quest's name (Defeat the monsters), where the editor's
        world list has the game's own words for it. Otherwise nothing."""
        return world.known()["labels"].get(self.name, "")

    @property
    def kind(self) -> str:
        """What its name says it's about, where the editor can read that. Otherwise nothing."""
        match = _STEP.match(self.short)
        return STEP_KINDS.get(match.group(1), "") if match else ""

    @property
    def is_group(self) -> bool:
        return self.kind.startswith(("a group", "a choice"))

    @property
    def number_when_done(self) -> int | None:
        """The number a save holds with this step once it's finished: the one a save has shown for this very
        step, or 1 for a step to interact with something, as all but two of those have had. None when it isn't
        known (a step to defeat enemies that no save has shown finished), and nothing counted for the rest."""
        seen = world.known()["counts"].get(self.name)
        if seen:
            return seen
        letters = _STEP.match(self.short)
        if letters and letters.group(1) == "I":
            return 0 if self.name in NO_NUMBER else 1
        return None if letters and letters.group(1) == "K" else 0

    @property
    def lacks_its_number(self) -> bool:
        """Finished, and without the number a save holds with it once it is."""
        return self.state == DONE and bool(self.number_when_done) and self.count < self.number_when_done


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
        return recorder.quest_title(self.name)

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

    @property
    def unnumbered(self) -> int:
        """How many of a finished quest's steps are without the number a save holds with them: a quest finished
        by version 1.16.0. Finishing it again gives them theirs."""
        return sum(1 for step in self.steps if step.lacks_its_number) if self.state == DONE else 0

    @property
    def to_finish(self) -> bool:
        """Whether there's anything for Finish it to do: it isn't finished, or it is and steps lack their number."""
        return self.state != DONE or bool(self.unnumbered)


def label(name: str) -> str:
    """A quest to read: what the game calls it, where that's known, with the save's name for it."""
    title = recorder.quest_title(name)
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


def comes_back(name: str) -> bool:
    """Whether the game lets a hero do this quest again once it's finished: it then offers it once more, and the
    quest comes back on the game's map as a new side quest to take. The game's own quest tables say which (the
    list's ``again``): a golem to rescue in Howling Woods (The Trembling Golem) and eight boss fights. Seen in the
    game (1.1.2.0) on a hero with every quest finished: four such marks on its map, one of them a stand that
    offered The Trembling Golem. Nothing in a save tells such a quest from one that's finished for good."""
    return name in world.known()["again"]


def follows(name: str) -> list[str]:
    """The quests the game makes available as it finishes this one: the ones that wait for it, by the game's own
    quest tables, which is what play recordings saw it do for the six quests they caught."""
    return list(world.known()["follows"].get(name, []))


def finish(document: Any, name: str) -> list[str]:
    """Finish a quest the hero has met, the way a save holds a finished one: the quest and every one of its steps
    Completed, a step that counts with the number the game saved with it where a save has shown that, and the
    quest no longer the one tracked. Where a recording has shown which quests the game makes available as it
    finishes this one, the ones the hero hasn't met are added too. Returns the quests added.

    A quest that's finished already, with steps that lack the number a save holds with them (version 1.16.0
    finished quests that way), is given those numbers and nothing else."""
    section = _section(document)
    entry = _entry(section, name)
    if entry.get("State") == DONE and not _quest(entry, None).unnumbered:
        raise ValueError(f"{label(name)} is finished already.")
    for task in entry["TaskData"]:
        task["State"] = DONE
        had = task.get("PartialProgress")
        count = Step(str(task.get("TaskName")), DONE, 0, name).number_when_done
        if count and not (isinstance(had, int) and not isinstance(had, bool) and had >= count):
            task["PartialProgress"] = count
    if entry.get("State") == DONE:
        return []
    entry["State"] = DONE
    if section.get("FocusedQuestId") == name:
        section["FocusedQuestId"] = ""
    have = {quest.name for quest in quests(document)}
    added = [quest for quest in follows(name) if quest not in have and world.known()["quests"].get(quest)]
    for quest in added:
        add(document, quest)
    return added


# ------------------------------------------------------------------ one step at a time

NOT_UNDER_WAY = "{label} is {standing}: a step can be finished in a quest that's active, and a quest that's available can be begun."
NO_TREE = "The editor doesn't know how the steps of {label} hang together, so it can't move it on by one. Finish it whole instead."
A_CHOICE = (
    "The next step of {label} is a choice between steps, and the editor hasn't seen how the game saves a choice that's under way. "
    "Finish the quest whole instead."
)


class _Choice(Exception):
    """The rules have come to a group of the kind the editor has never seen under way in a save (a Selection)."""


@dataclass(frozen=True)
class Stepped:
    """What moving a quest on did: it was begun, or one of its steps was finished."""

    quest: str
    begun: bool  # it was available, and is under way now
    step: str  # the step that was finished, as the save names it ("" when the quest was begun)
    now_on: tuple[str, ...]  # the steps it is on now: the ones active that aren't groups
    ended: bool  # that was its last step: the quest is finished
    opened: tuple[str, ...]  # with that, the quests listed as available after it


def _tree(entry: dict) -> tuple[dict[str, dict], dict[str, str]] | None:
    """How a quest's steps hang together, by the editor's list: its groups (a step with members: their kind and
    their members) and each member's group. None unless the list knows the quest's own group, the last step a save
    lists, and every other step is in a group: a tree of all of them, and nothing else."""
    known = world.known()["groups"]
    names = [str(task.get("TaskName")) for task in entry["TaskData"]]
    groups = {name: known[name] for name in names if name in known}
    parents = {member: name for name, group in groups.items() for member in group["of"]}
    whole = bool(names) and names[-1] in groups and set(parents) == set(names[:-1]) and len(set(names)) == len(names)
    return (groups, parents) if whole else None


def _activate(name: str, tasks: dict[str, dict], groups: dict[str, dict]) -> None:
    """A step's turn has come: it's active, and if it's a group so is what it starts with (its first member, or
    every member of a group whose members go all at once)."""
    tasks[name]["State"] = ACTIVE
    group = groups.get(name)
    if group is None:
        return
    if group["kind"] == "Sequence":
        _activate(group["of"][0], tasks, groups)
    elif group["kind"] == "Standard":
        for member in group["of"]:
            _activate(member, tasks, groups)
    else:
        raise _Choice(name)


def _moved_on(name: str, tasks: dict[str, dict], groups: dict[str, dict], parents: dict[str, str]) -> bool:
    """A step has just been finished: its group moves on. In a group whose members come one after the other the
    next one's turn comes; a group is finished when its last member is, or all of them; and so on up. True when it
    is the quest's own group that has finished."""
    parent = parents.get(name)
    if parent is None:
        return True
    group = groups[parent]
    if group["kind"] == "Sequence":
        place = group["of"].index(name)
        if place + 1 < len(group["of"]):
            _activate(group["of"][place + 1], tasks, groups)
            return False
    elif group["kind"] == "Standard":
        if any(tasks[member].get("State") != DONE for member in group["of"]):
            return False
    else:
        raise _Choice(parent)
    tasks[parent]["State"] = DONE
    return _moved_on(parent, tasks, groups, parents)


def steps_it_is_on(document: Any, name: str) -> list[Step]:
    """The steps a quest under way is on: the active ones that aren't groups, in the save's order. A group's
    members that go all at once are all there."""
    entry = _entry(_section(document), name)
    groups = world.known()["groups"]
    return [step for step in _quest(entry, None).steps if step.state == ACTIVE and step.name not in groups] if entry.get("State") == ACTIVE else []


def why_no_step(document: Any, name: str) -> str:
    """Why this quest can't be moved on by a step, in a sentence; nothing if it can."""
    entry = _entry(_section(document), name)
    if entry.get("State") not in (AVAILABLE, ACTIVE):
        return NOT_UNDER_WAY.format(label=label(name), standing=STATE_WORDS.get(str(entry.get("State")), str(entry.get("State"))))
    if _tree(entry) is None:
        return NO_TREE.format(label=label(name))
    if entry.get("State") == ACTIVE and not steps_it_is_on(document, name):
        return f"No step of {label(name)} is active, so there's none to finish. Finish it whole instead."
    return ""


def step(document: Any, name: str, which: str | None = None) -> Stepped:
    """Move a quest on the way the game does. One that's available is begun: it is active, and so is what it starts
    with. In one that's active, a step it is on is finished (``which`` of them, or the first as the save lists
    them), with the number a save holds with a finished step, and its group moves on: the next step's turn comes,
    and when the quest's own group is finished the quest is, as ``finish`` leaves one. All of it or none: a quest
    the rules can't move on (a choice between steps comes next) is left as it was, with an error that says why."""
    section = _section(document)
    entry = _entry(section, name)
    reason = why_no_step(document, name)
    if reason:
        raise ValueError(reason)
    groups, parents = _tree(entry)
    trial = copy.deepcopy(entry["TaskData"])
    tasks = {str(task.get("TaskName")): task for task in trial}
    root = str(trial[-1].get("TaskName"))
    finished, ended = "", False
    try:
        if entry.get("State") == AVAILABLE:
            if which is not None:
                raise ValueError(f"{label(name)} isn't begun yet: it has no step to finish.")
            _activate(root, tasks, groups)
        else:
            on = [found.name for found in steps_it_is_on(document, name)]
            finished = on[0] if which is None else which
            if finished not in on:
                raise ValueError(f"{label(name)} isn't on the step {which}.")
            task = tasks[finished]
            task["State"] = DONE
            had, count = task.get("PartialProgress"), Step(finished, DONE, 0, name).number_when_done
            if count and not (isinstance(had, int) and not isinstance(had, bool) and had >= count):
                task["PartialProgress"] = count
            ended = _moved_on(finished, tasks, groups, parents)
    except _Choice:
        raise ValueError(A_CHOICE.format(label=label(name))) from None
    entry["TaskData"][:] = trial
    opened: list[str] = []
    if ended:
        opened = finish(document, name)  # every step is done by now: this finishes the quest itself, and lists what follows
    else:
        entry["State"] = ACTIVE
    now_on = tuple(found.name for found in steps_it_is_on(document, name))
    return Stepped(name, not finished, finished, now_on, ended, tuple(opened))


@dataclass(frozen=True)
class Finished:
    """What finishing several quests at once did."""

    finished: tuple[str, ...]  # the quests finished, in the order they were
    added: tuple[str, ...]  # the ones among them that the hero hadn't met, and that were added to be finished
    opened: tuple[str, ...]  # quests left available that the hero hadn't met: what the game opens after one of those finished


def to_finish(document: Any, part: str | None = None) -> list[Quest]:
    """The quests that finishing all of a part of the game would finish: the ones in it that aren't finished,
    the hero's own and the ones it hasn't met, and the finished ones whose steps lack their number, in the order
    ``every`` lists them. With no part, the whole game: every quest the editor knows."""
    return [quest for quest in every(document) if quest.to_finish and (part is None or quest.group == part)]


def finish_all(document: Any, names: Iterable[str]) -> Finished:
    """Finish several quests at once, each the way ``finish`` does it; one the hero hasn't met is added first.
    Quests that are finished already are passed over. All of it or none: if any one of them can't be finished,
    the save is left as it was."""
    section = _section(document)
    before = {quest.name for quest in quests(document)}
    # On a copy of the quests, which is all that finishing touches, and put in place only once every one has worked.
    trial = {"CharacterSaveV1": {"quest": copy.deepcopy(section)}}
    finished = []
    for name in names:
        standing = {quest.name: quest for quest in quests(trial)}
        if name in standing and not standing[name].to_finish:
            continue
        if name not in standing:
            add(trial, name)
        finish(trial, name)
        finished.append(name)
    added = [name for name in finished if name not in before]  # met for the first time here, by being added or by following one
    done = trial["CharacterSaveV1"]["quest"]
    section["Quests"][:] = done["Quests"]
    if "FocusedQuestId" in done:
        section["FocusedQuestId"] = done["FocusedQuestId"]
    opened = [quest.name for quest in quests(document) if quest.name not in before and quest.state != DONE]
    return Finished(tuple(finished), tuple(added), tuple(opened))


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


# ------------------------------------------------------------------ the map

def _maps(document: Any) -> list:
    """The pictures of the fog a save keeps, one to a region. An error if it keeps none."""
    place = _body(document).get("WorldExploration")
    fog = place.get("SavedFogOfWarExploration") if isinstance(place, dict) else None
    items = fog.get("Items") if isinstance(fog, dict) else None
    if not isinstance(items, list):
        raise ValueError(NO_MAP)
    return items


def _squares(item: Any) -> int:
    """How many squares a region's picture has, by the size saved with it. None for one that isn't laid out as a save's are."""
    size = item.get("Size") if isinstance(item, dict) else None
    across, down = (size.get("X"), size.get("Y")) if isinstance(size, dict) else (None, None)
    whole = all(isinstance(side, int) and not isinstance(side, bool) and side > 0 for side in (across, down))
    return across * down if whole and across * down <= MOST_SQUARES and isinstance(item.get("Data"), list) else 0


def map_explored(document: Any) -> tuple[int, int, int]:
    """How much of the map a hero has seen: (squares the fog has lifted from at all, squares in all, regions),
    over the regions its save keeps a picture for. Nothing of each for a save that keeps none."""
    try:
        items = _maps(document)
    except ValueError:
        return 0, 0, 0
    seen = sum(1 for item in items if _squares(item) for cell in item["Data"][: _squares(item)] if isinstance(cell, int) and cell > 0)
    return seen, sum(_squares(item) for item in items), sum(1 for item in items if _squares(item))


def _regions_to_add(document: Any) -> dict[str, dict]:
    """The regions the editor knows from other heroes' saves that this hero's save has no picture for: each with
    one corner and one size in every save that showed it."""
    have = {item.get("Tag") for item in _maps(document) if isinstance(item, dict)}
    found = {}
    for tag, region in world.known()["regions"].items():
        corner, size = region.get("corner"), region.get("size")
        exact = (
            isinstance(corner, list) and len(corner) == 2 and all(isinstance(part, (int, float)) and not isinstance(part, bool) for part in corner)
            and isinstance(size, list) and len(size) == 2 and all(isinstance(side, int) and not isinstance(side, bool) and side > 0 for side in size)
        )
        if tag not in have and exact and not region.get("also") and size[0] * size[1] <= MOST_SQUARES:
            found[tag] = region
    return found


def map_to_discover(document: Any) -> tuple[int, list[str]]:
    """What discovering the whole map would change: how many squares of the save's own pictures aren't all clear
    yet, and the regions it would add. An error if the save keeps no map."""
    left = sum(1 for item in _maps(document) for cell in (item["Data"][: _squares(item)] + [0] * max(0, _squares(item) - len(item["Data"])) if _squares(item) else []) if cell != CLEAR)
    return left, list(_regions_to_add(document))


def discover_map(document: Any) -> tuple[int, list[str]]:
    """Lift the fog from the whole map: every square of every region's picture all clear, and a picture, all
    clear too, for each region the hero hasn't been in that another hero's save has shown. Returns what
    ``map_to_discover`` said it would change."""
    left, more = map_to_discover(document)
    items = _maps(document)
    for item in items:
        if _squares(item):
            item["Data"] = [CLEAR] * _squares(item)
    for tag, region in _regions_to_add(document).items():
        (x, y), (across, down) = region["corner"], region["size"]
        items.append({"Tag": tag, "Data": [CLEAR] * (across * down), "WorldPosition": {"X": x, "Y": y}, "Size": {"X": across, "Y": down}})
    return left, more


# ------------------------------------------------------------------ shortcuts and key gates

SHORTCUTS, GATES = recorder.SHORTCUT, recorder.GATE
OVERWORLD = "/Maps/Overworld/"  # the one world every hero walks: what stands in it is named the same in every save
# Which lock is a gate's, and which key is a lock's, is in the game's own files. What a save shows of it: a lock
# stands in the same part of the map as its gate (its name has the same piece of the map in it: nine of the ten
# locks the editor knows), and a key was put there with its lock (its ID starts the same: all seven). The tenth
# lock is across the line from its gate, and one of the developer's recordings saw the two change in one save, as
# a key was put in (Meadow A2, 2026-10-11): that pair is written here.
SEEN_TOGETHER = {"BP_KeyGolemLockActorStateGimmick UAID_D45D640431825D9802_1554914530": "BP_MA2_KeyGate UAID_D45D6404305656A302_1326242774"}
_PART_OF_MAP = re.compile(r"/_Generated_/([^./]+)\.")
_PUT_WITH = re.compile(r"_C_UAID_([0-9A-Za-z]+)_\d+$")
NO_PIECES = "This hero's save keeps no list of the world's rocks and gates yet. Play until the game has saved it once."


@dataclass(frozen=True)
class Piece:
    """A thing in the overworld that stays as the hero left it and that the editor can open: a rock that moves out
    of the way or a bridge (a shortcut), or a gate that a key opens."""

    path: str  # as a save names it
    kind: str  # SHORTCUTS or GATES; recorder.LOCK or recorder.KEY for what goes with a gate (gate_parts)
    name: str  # what the game's files call it, in words: Forest Roadblock
    opened: tuple[int, int]  # the two numbers a save holds with it once it's open: the state it was in, the state it's in
    state: tuple[int, int] | None  # the two this hero's save holds with it; None when the save doesn't list it, which is how one stands that nobody has touched

    @property
    def open(self) -> bool:
        return self.state is not None and self.state[1] == self.opened[1]


def _actors(document: Any) -> list | None:
    """The list a save keeps of the things in the world that have changed, or None where it keeps none."""
    place = _body(document).get("WorldExploration")
    actors = place.get("SavedActorStates") if isinstance(place, dict) else None
    return actors if isinstance(actors, list) else None


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def pieces(document: Any, kind: str | None = None) -> list[Piece]:
    """The shortcuts and the key gates of the overworld that the editor knows from other heroes' saves (of one kind,
    or both), each with how it stands for this hero. Only the ones every save that showed them held the same way:
    one state before, one state now. A key and its lock aren't among them: the editor leaves those alone."""
    mine = {}
    for actor in _actors(document) or []:
        if isinstance(actor, dict) and _whole(actor.get("PreviousState")) and _whole(actor.get("CurrentState")):
            mine[actor.get("SoftObjectPath")] = (actor["PreviousState"], actor["CurrentState"])
    found = []
    for piece in world.known()["pieces"].values():
        path, states = (piece.get("path"), piece.get("states")) if isinstance(piece, dict) else (None, None)
        what = recorder.piece_kind(path) if isinstance(path, str) else ""
        one = isinstance(states, list) and len(states) == 1 and isinstance(states[0], list) and len(states[0]) == 2 and all(map(_whole, states[0]))
        if what in (SHORTCUTS, GATES) and kind in (None, what) and OVERWORLD in path and one:
            found.append(Piece(path, what, recorder.piece_name(path), (states[0][0], states[0][1]), mine.get(path)))
    return sorted(found, key=lambda piece: (piece.kind != SHORTCUTS, piece.name, piece.path))


def _found(pattern: re.Pattern, path: str) -> str:
    match = pattern.search(path)
    return match.group(1) if match else ""


def gate_parts(document: Any) -> list[Piece]:
    """The locks and the keys that go with the key gates the editor knows, each with how it stands for this hero
    and the two states a save holds with it once the gate has been opened by playing: the key in its lock (2 then
    1), the key taken (1 then 2). Only a lock the editor can tell to be one of those gates' own, and a key it can
    tell to be one of those locks': anything else it leaves alone, since a lock marked as used beside a gate that
    isn't open would leave that gate shut for good."""
    mine = {}
    for actor in _actors(document) or []:
        if isinstance(actor, dict) and _whole(actor.get("PreviousState")) and _whole(actor.get("CurrentState")):
            mine[actor.get("SoftObjectPath")] = (actor["PreviousState"], actor["CurrentState"])
    gates = [piece.path for piece in pieces(document, GATES)]
    by_the_gates, gate_names = {_found(_PART_OF_MAP, path) for path in gates} - {""}, {world.piece_id(path) for path in gates}
    listed = []
    for piece in world.known()["pieces"].values():
        path, states = (piece.get("path"), piece.get("states")) if isinstance(piece, dict) else (None, None)
        if isinstance(path, str) and OVERWORLD in path and isinstance(states, list) and states and all(isinstance(pair, list) and len(pair) == 2 and all(map(_whole, pair)) for pair in states):
            listed.append((path, recorder.piece_kind(path), max(states, key=lambda pair: pair[1])))  # the furthest a save has shown it
    locks = [
        (path, used) for path, kind, used in listed
        if kind == recorder.LOCK and (_found(_PART_OF_MAP, path) in by_the_gates or SEEN_TOGETHER.get(world.piece_id(path)) in gate_names)
    ]
    put_with = {_found(_PUT_WITH, path) for path, _used in locks} - {""}
    by_the_locks = by_the_gates | ({_found(_PART_OF_MAP, path) for path, _used in locks} - {""})
    keys = [
        (path, used) for path, kind, used in listed
        if kind == recorder.KEY and (_found(_PUT_WITH, path) in put_with or _found(_PART_OF_MAP, path) in by_the_locks)
    ]
    found = [Piece(path, kind, recorder.piece_name(path), (used[0], used[1]), mine.get(path)) for kind, group in ((recorder.LOCK, locks), (recorder.KEY, keys)) for path, used in group]
    return sorted(found, key=lambda piece: (piece.kind != recorder.LOCK, piece.path))


def gate_parts_to_use(document: Any) -> list[Piece]:
    """The locks and keys of the key gates that aren't yet as a save holds them once the gate is open."""
    return [piece for piece in gate_parts(document) if not piece.open]


def pieces_open(document: Any, kind: str) -> tuple[int, int]:
    """How many of the shortcuts, or of the key gates, the editor knows are open for this hero, and how many it knows."""
    known = pieces(document, kind)
    return sum(1 for piece in known if piece.open), len(known)


def pieces_to_open(document: Any, kind: str) -> list[Piece]:
    """The shortcuts, or the key gates, that opening them all would open: the ones this hero hasn't opened."""
    return [piece for piece in pieces(document, kind) if not piece.open]


def open_pieces(document: Any, kind: str) -> int:
    """Open every shortcut, or every key gate, the editor knows: each is listed with the two states a save holds
    with it once it's open, where the game lists one (after the ones the save has). With the key gates go their
    locks and keys (gate_parts), each as a save holds it once the key is in. Returns how many things it changed.
    An error if the save keeps no such list."""
    actors = _actors(document)
    if actors is None:
        raise ValueError(NO_PIECES)
    todo = pieces_to_open(document, kind) + (gate_parts_to_use(document) if kind == GATES else [])
    for piece in todo:
        mine = next((actor for actor in actors if isinstance(actor, dict) and actor.get("SoftObjectPath") == piece.path), None)
        if mine is None:
            actors.append({"SoftObjectPath": piece.path, "PreviousState": piece.opened[0], "CurrentState": piece.opened[1], "Version": 0})
        else:
            mine["PreviousState"], mine["CurrentState"] = piece.opened
    return len(todo)


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
            elif quest.state == DONE and was.unnumbered > quest.unnumbered:
                given = was.unnumbered - quest.unnumbered
                how = f"{given} finished step{'' if given == 1 else 's'} given {'its number' if given == 1 else 'their numbers'}"
            else:
                how = f"{quest.done} of {len(quest.steps)} steps done (it was {was.done})"
            lines.append(f"Quest {quest.label}: {how}")
    lines += [f"Quest {quest.label}: taken out" for quest in old.values()]
    if tracked(before) != tracked(after):
        lines.append(f"Quest tracked: {label(tracked(after)) if tracked(after) else 'none'}")
    if (last_station(before), area(before)) != (last_station(after), area(after)):
        lines.append(f"Starts at: {recorder.station_name(last_station(after))}, in {recorder.area_name(area(after))}")
    was, now = map_explored(before), map_explored(after)
    if was != now:
        lines.append(f"Map: {now[0]:,} of {now[1]:,} squares explored in {now[2]} region{'' if now[2] == 1 else 's'} (it was {was[0]:,} of {was[1]:,} in {was[2]})")
    for kind, words in ((SHORTCUTS, "Shortcuts"), (GATES, "Key gates")):
        was, now = pieces_open(before, kind), pieces_open(after, kind)
        if was != now:
            lines.append(f"{words}: {now[0]} of the {now[1]} the editor knows open (it was {was[0]})")
    was, now = [sum(1 for piece in gate_parts(version) if piece.open) for version in (before, after)]
    if was != now:
        lines.append(f"Locks and keys of those gates: {now} of {len(gate_parts(after))} as they are once a key is in (it was {was})")
    return lines
