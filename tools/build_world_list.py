"""Builds dungeons2_editor/data/world.json: what the editor knows of the game's world.

    python tools/build_world_list.py                        # add what the play recorder's recordings show
    python tools/build_world_list.py list.txt another.txt   # and what players' lists say
    python tools/build_world_list.py --recordings FOLDER    # recordings somewhere else than recordings/
    python tools/build_world_list.py --quest-tables ZIP     # and the game's own quest tables, as a player sent them

The game keeps its quests, doors, minecart stations and regions in its encrypted files, so the editor learns them
from saves, the way it learns items. This adds to the list it has:

    every hero save in the recordings: each quest with its steps, each door with its place, the stations,
    regions, cutscenes, areas, achievements and puzzle pieces it shows
    the recordings themselves: where a minecart station or a cutscene turned up, where chests were opened, and
    which quests the game made available in the save that finished a quest
    each list given: the world's part of a Share item IDs list, as a player posted it (a text file with the
    lines; the item IDs and the headings in it are passed over)
    the game's quest tables (a zip or a folder of the game's quest files as JSON, as a player read them out of
    the game and sent them): the number each step to defeat enemies counts to, which quest waits for which, and
    which quests the game lets a hero do again

Nothing is ever taken out, and nothing a list already has is changed: a door or a region that a save puts
somewhere else than the list does is kept beside it ("also") and named here, to be looked at. No hero's ID or
name goes in, and nothing about when anyone played. What the game calls an area, a minecart station and a quest
isn't in a save: those names are in dungeons2_editor/recorder.py, from MetaBot's map.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dungeons2_editor import recorder, world  # noqa: E402

TARGET = ROOT / "dungeons2_editor" / "data" / "world.json"
ABOUT = (
    "What the editor knows of the game's world, from saves: quests and their steps, doors and where they are (metres), minecart stations, the regions a save "
    "keeps a picture of the fog for, cutscenes, areas, achievements, puzzle pieces, the number saved with a finished step, and from play recordings where "
    "things turned up, where chests were opened and which quests the game made available as it finished one. From the game's own quest tables, as a "
    "player read them out of the game and sent them (github.com/IshiakiZ/mcd2-save-editor/issues/40): the number each step to defeat enemies counts to, "
    "which quest waits for which, and which quests can be done again. "
    "Built by tools/build_world_list.py; added to from players' Share item IDs lists."
)


def quest_tables(path: Path) -> list[dict]:
    """The game's quest files under a folder, or in a zip, each read as JSON. One that can't be read is passed over."""
    texts = []
    if path.is_dir():
        texts = [found.read_bytes() for found in sorted(path.glob("*.json"))]
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            texts = [archive.read(info) for info in archive.infolist() if info.filename.endswith(".json") and info.file_size < 5_000_000]
    tables = []
    for text in texts:
        try:
            table = json.loads(text.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            continue
        if isinstance(table, dict) and isinstance(table.get("Quests"), list):
            tables.append(table)
    return tables


def build(recordings: Path | None, lists: list[Path], start: dict | None = None, tables: Path | None = None) -> tuple[dict, list[str]]:
    """The list, added to from the recordings under a folder, from players' lists and from the game's quest tables,
    and what to say about it."""
    built = world.merge(world.empty(), start or {})
    said = [f"The list had: {world.counts(built)}"]
    if tables is not None:
        shown = world.of_quest_tables(quest_tables(tables))
        # The tables and the saves must tell of the same quests in the same way, or one of them isn't what it seems.
        odd = [name for name, steps in shown["quests"].items() if name in built["quests"] and built["quests"][name] != steps]
        wrong = {step: (count, built["counts"][step]) for step, count in shown["counts"].items() if built["counts"].get(step, count) != count}
        if odd or wrong:
            said.append(f"The quest tables under {tables} don't agree with what saves have shown, and were left out: steps of {odd}; numbers {wrong}")
        else:
            world.merge(built, shown)
            said.append(f"Read {len(shown['quests'])} quests in the game's quest tables under {tables}")
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
    parser.add_argument("--quest-tables", type=Path, default=None, help="the game's quest tables as JSON: a zip of them, or a folder")
    parser.add_argument("--out", type=Path, default=TARGET)
    args = parser.parse_args(argv)
    try:
        start = json.loads(args.out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        start = {}
    built, said = build(args.recordings, args.lists, start, args.quest_tables)
    args.out.write_text(json.dumps({"about": ABOUT, **built}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n".join(said))
    print(f"Written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
