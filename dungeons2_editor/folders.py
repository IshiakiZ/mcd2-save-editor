"""Saves kept a folder each: one folder for every save, with the save in a file called ``Data``.

Some copies of the game keep their saves this way::

    <a SaveGames folder>
        Character<id>/
            Data
            LastModifiedTime
        GlobalSaveDataDefault/
            Data
            LastModifiedTime

``Data`` holds what the Steam build keeps in a ``.sav`` file and the Xbox build in a blob (see ``codec.py``).
The editor reads and replaces that one file and nothing else in a save's folder: what ``LastModifiedTime`` holds
hasn't been seen, so it is left as it is.

A folder like this is never looked for. It opens when it's picked by hand (Menu > Open a save folder…, or
``--profile``). The developer has no saves kept this way, so how they are read and written rests on a player's
account of them, and the editor says so before it saves into one.

This module gives those folders the same shape ``steam.py`` gives ``.sav`` files (an entry per save, and a single
blob called ``Data``), so ``saves.py`` can treat the two alike.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import steam, wgs

DATA_FILE = "Data"
_HERO_PREFIX = "character"
_TEMP_SUFFIX = ".mcd2tmp"


@dataclass
class FolderEntry:
    """One save's folder, with the fields of ``wgs.IndexEntry`` that the rest of the editor reads."""

    name: str  # the folder's name
    revision: int  # the Data file's modification time in nanoseconds: changes whenever it is rewritten
    mtime: int  # FILETIME, like wgs.IndexEntry.mtime
    size: int
    sync_state: int = wgs.SYNCED  # not used: nothing here says anything of a cloud
    local_file: bool = True


def is_save_folder(folder: Path) -> bool:
    """True for a folder that keeps each save in a folder of its own, a hero's among them. An Xbox container
    folder isn't one, and neither is a folder of ``.sav`` files."""
    folder = Path(folder)
    if (folder / wgs.INDEX_FILE).is_file():
        return False
    try:
        children = list(folder.iterdir())
    except OSError:
        return False
    if any(child.is_file() and child.suffix.lower() == steam.SAVE_SUFFIX for child in children):
        return False
    return any(_holds_a_save(child) and child.name.lower().startswith(_HERO_PREFIX) for child in children)


def _holds_a_save(child: Path) -> bool:
    try:
        return child.is_dir() and (child / DATA_FILE).is_file()
    except OSError:
        return False


def _entry(save: Path) -> FolderEntry:
    stat = (save / DATA_FILE).stat()
    return FolderEntry(
        name=save.name,
        revision=stat.st_mtime_ns,
        mtime=stat.st_mtime_ns // 100 + wgs._FILETIME_UNIX_EPOCH,
        size=stat.st_size,
    )


def read_entries(folder: Path) -> list[FolderEntry]:
    """Every save in ``folder``, in name order."""
    saves = [child for child in Path(folder).iterdir() if _holds_a_save(child)]
    return [_entry(save) for save in sorted(saves, key=lambda save: save.name.lower())]


def find_entry(folder: Path, name: str) -> FolderEntry | None:
    save = Path(folder) / name
    try:
        return _entry(save) if _holds_a_save(save) else None
    except OSError:
        return None


def read_blobs(folder: Path, entry: FolderEntry) -> dict[str, bytes]:
    return {DATA_FILE: (Path(folder) / entry.name / DATA_FILE).read_bytes()}


def write_file(folder: Path, name: str, blobs: dict[str, bytes]) -> FolderEntry:
    """Replace the ``Data`` file of the save called ``name`` with the new data, and touch nothing else of it.

    The data goes into a temporary file next to it first and then takes the place of the old one in one step, so
    the game never sees a half-written save. A save that isn't there isn't made: only a file the game wrote is
    ever written over.
    """
    save = Path(folder) / name
    target = save / DATA_FILE
    if not target.is_file():
        raise FileNotFoundError(f"{name} has no {DATA_FILE} file to replace")
    temp = save / f"{DATA_FILE}.{uuid.uuid4().hex[:8]}{_TEMP_SUFFIX}"
    try:
        with open(temp, "wb") as handle:
            handle.write(blobs[DATA_FILE])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return _entry(save)


def stamp(folder: Path) -> tuple | None:
    """A value that changes whenever any save in ``folder`` is written, added or removed."""
    try:
        return tuple((entry.name, entry.revision, entry.size) for entry in read_entries(folder))
    except OSError:
        return None
