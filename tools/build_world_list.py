"""Builds dungeons2_editor/data/world.json: what the editor knows of the game's world.

    python tools/build_world_list.py                        # add what the play recorder's recordings show
    python tools/build_world_list.py list.txt another.txt   # and what players' lists say
    python tools/build_world_list.py --recordings FOLDER    # recordings somewhere else than recordings/

The game keeps its quests, doors, minecart stations and regions in its encrypted files, so the editor learns them
from saves, the way it learns items. This adds to the list it has:

    every hero save in the recordings: each quest with its steps, each door with its place, the stations,
    regions, cutscenes, areas, achievements and puzzle pieces it shows
    the recordings themselves: where a minecart station or a cutscene turned up, and where chests were opened
    each list given: the world's part of a Share item IDs list, as a player posted it (a text file with the
    lines; the item IDs and the headings in it are passed over)

Nothing is ever taken out, and nothing a list already has is changed: a door or a region that a save puts
somewhere else than the list does is kept beside it ("also") and named here, to be looked at. No hero's ID or
name goes in, and nothing about when anyone played. What the game calls an area, a minecart station and a quest
isn't in a save: those names are in dungeons2_editor/recorder.py, from MetaBot's map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dungeons2_editor import recorder, world  # noqa: E402

TARGET = ROOT / "dungeons2_editor" / "data" / "world.json"
ABOUT = (
    "What the editor knows of the game's world, from saves: quests and their steps, doors and where they are (metres), minecart stations, the regions a save "
    "keeps a picture of the fog for, cutscenes, areas, achievements, puzzle pieces, and from play recordings where things turned up and chests were opened. "
    "Built by tools/build_world_list.py; added to from players' Share item IDs lists."
)


def build(recordings: Path | None, lists: list[Path], start: dict | None = None) -> tuple[dict, list[str]]:
    """The list, added to from the recordings under a folder and from players' lists, and what to say about it."""
    built = world.merge(world.empty(), start or {})
    said = [f"The list had: {world.counts(built)}"]
    if recordings is not None and recordings.is_dir():
        saves = 0
        for path in sorted(recordings.glob("*/snapshots/*.json"), key=lambda found: (found.parent.parent.name, found.name)):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(document, dict) and "CharacterSaveV1" in document:
                world.merge(built, world.of_save(document))
                saves += 1
        world.merge(built, world.of_recordings(recorder.build_atlas(recordings)))
        said.append(f"Read {saves} hero saves in the recordings under {recordings}")
    for path in lists:
        told = world.read_list(path.read_text(encoding="utf-8"))
        world.merge(built, told)
        said.append(f"Read {path.name}: {world.counts(told)}" + (f"; pictures of the fog for {', '.join(told['pictures'])}" if told["pictures"] else ""))
    for kind in ("doors", "regions"):
        said += [f"LOOK AT: {kind[:-1]} {name} is in two places: {json.dumps(entry)}" for name, entry in built[kind].items() if entry.get("also")]
    said.append(f"The list has: {world.counts(built)}")
    return built, said


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lists", nargs="*", type=Path, help="text files holding the world's part of a Share item IDs list")
    parser.add_argument("--recordings", type=Path, default=ROOT / "recordings", help="the play recorder's recordings (default: recordings/)")
    parser.add_argument("--out", type=Path, default=TARGET)
    args = parser.parse_args(argv)
    try:
        start = json.loads(args.out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        start = {}
    built, said = build(args.recordings, args.lists, start)
    args.out.write_text(json.dumps({"about": ABOUT, **built}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n".join(said))
    print(f"Written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
