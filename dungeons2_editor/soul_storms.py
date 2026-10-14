"""Soul Storms: which area has one now, and when the next ones come.

The game runs its Soul Storms to a timetable of its own, the same for every player and worked out from the clock:
one area at a time, going round seven in a fixed order, a storm every 40 minutes that lasts 20. The timetable is
the game's own: icicle1133 sent it with the game's other tables (issue 41), and the times it gives were checked in
the game. The game gets it from its servers, so it can change without an update to the game, and until the
editor's copy (data/soul_storms.json) is changed too, the times here would then be wrong. Nothing here goes online.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths, recorder

TABLE_FILE = paths.resource("dungeons2_editor/data/soul_storms.json")
WHERE_FROM = (
    "The times come from the game's own timetable: a storm every 40 minutes that lasts 20, in each area in turn. "
    "The game gets it from its servers, so it can change. If the game shows a storm somewhere else, the editor's copy is out of date."
)


@dataclass(frozen=True)
class Timetable:
    starts: datetime  # when the first storm began (in UTC); the rest follow from it
    every: timedelta  # from the start of one storm to the start of the next
    lasts: timedelta  # how long a storm lasts
    areas: tuple[str, ...]  # the areas' tags (SW.Area.Forest.A1), in the order the storms go round them


@dataclass(frozen=True)
class Storm:
    number: int  # how many storms came before it, counting from the first
    area: str  # the area's tag
    starts: datetime  # in UTC
    ends: datetime

    @property
    def name(self) -> str:
        """The area by the game's name for it: Howling Woods."""
        return recorder.area_name(self.area)

    def is_on(self, when: datetime) -> bool:
        return self.starts <= when < self.ends


def load(path: Path = TABLE_FILE) -> Timetable:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    starts = datetime.fromisoformat(data["starts"].replace("Z", "+00:00"))
    if starts.tzinfo is None:
        raise ValueError("the timetable's start needs its time zone")
    if not data["areas"] or data["every_seconds"] <= 0 or not 0 < data["lasts_seconds"] <= data["every_seconds"]:
        raise ValueError("the timetable needs its areas, and storms that end before the next begins")
    return Timetable(starts, timedelta(seconds=data["every_seconds"]), timedelta(seconds=data["lasts_seconds"]), tuple(data["areas"]))


def storm(table: Timetable, number: int) -> Storm:
    """The storm that many after the first (a negative number is one from before the timetable's start, which the
    game would have had on the same turn)."""
    starts = table.starts + number * table.every
    return Storm(number, table.areas[number % len(table.areas)], starts, starts + table.lasts)


def coming(table: Timetable, when: datetime, count: int | None = None) -> list[Storm]:
    """The storm that's on at that moment, if one is, and the ones after it: ``count`` in all, one round of the
    areas unless told otherwise, so that each area's next storm is in it."""
    when = _utc(when)
    number = (when - table.starts) // table.every
    if not storm(table, number).is_on(when):
        number += 1  # between two storms: the next one is the first to come
    return [storm(table, number + offset) for offset in range(len(table.areas) if count is None else count)]


def next_in(table: Timetable, area: str, when: datetime) -> Storm:
    """An area's next storm, or the one on there now."""
    for found in coming(table, when):
        if found.area == area:
            return found
    raise ValueError(f"{area} has no Soul Storms in the timetable")


def wait_text(seconds: float) -> str:
    """How long until something, the way a person would say it: 'under a minute', '25 minutes', '2 hours 5 minutes'."""
    minutes = int(seconds // 60)
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    parts = ([f"{hours} hour{'s' if hours != 1 else ''}"] if hours else []) + ([f"{minutes} minute{'s' if minutes != 1 else ''}"] if minutes else [])
    return " ".join(parts)


def clock_text(moment: datetime, now: datetime, zone: timezone | None = None) -> str:
    """A moment on the PC's clock (or in ``zone``): 15:40 if it's today there, else with the day: Wed 00:20."""
    local, today = _utc(moment).astimezone(zone), _utc(now).astimezone(zone)
    return f"{local:%H:%M}" if local.date() == today.date() else f"{local:%a %H:%M}"


def now_text(table: Timetable, now: datetime, zone: timezone | None = None) -> str:
    """A sentence on the storm that's on, or the next one if none is."""
    first = coming(table, now, 1)[0]
    if first.is_on(_utc(now)):
        return f"A Soul Storm is on in {first.name} until {clock_text(first.ends, now, zone)} ({wait_text((first.ends - _utc(now)).total_seconds())} left)."
    return f"No Soul Storm is on now. The next is in {first.name} at {clock_text(first.starts, now, zone)}, in {wait_text((first.starts - _utc(now)).total_seconds())}."


def zone_name(now: datetime) -> str:
    """The PC's time zone, by the name the system gives it (Mountain Daylight Time), or as an offset from UTC."""
    local = _utc(now).astimezone()
    name = local.tzname() or ""
    if name and not name.startswith(("+", "-")):
        return name
    offset = int((local.utcoffset() or timedelta()).total_seconds() // 60)
    hours, minutes = divmod(abs(offset), 60)
    return f"UTC{'-' if offset < 0 else '+'}{hours}" + (f":{minutes:02d}" if minutes else "")


def _utc(moment: datetime) -> datetime:
    """A moment in UTC; one without a time zone is taken as the PC's own clock."""
    return (moment if moment.tzinfo else moment.astimezone()).astimezone(timezone.utc)
