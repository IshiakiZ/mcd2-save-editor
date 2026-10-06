"""Saves of the Steam version: plain ``.sav`` files in one folder.

The Steam build keeps each save as its own file in ``Dungeons2\\Saved\\SaveGames``, named after the container
the Xbox build would use (``Character<id>.sav`` for a hero)::

    Windows   %LOCALAPPDATA%\\Dungeons2\\Saved\\SaveGames
    Linux     <steam>/steamapps/compatdata/1912410/pfx/drive_c/users/steamuser/AppData/Local/Dungeons2/Saved/SaveGames
              (Proton; the folder inside the game's Wine prefix)

``Dungeons\\Saved\\SaveGames`` (no 2) has been reported as well, so that folder is looked in too.

There is no ``containers.index`` and no revision numbering: a file's content is the same JSON the Xbox build
keeps in a blob (see ``codec.py``), and a file is replaced in place. This module gives those files the same
shape ``wgs.py`` gives Xbox containers (an entry per save, and a single blob called ``Data``), so ``saves.py``
can treat both layouts alike.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import wgs

STEAM_APP_ID = "1912410"
SAVE_SUFFIX = ".sav"
BLOB_NAME = "Data"
_TEMP_SUFFIX = ".mcd2tmp"

_SAVE_GAMES = Path("Dungeons2", "Saved", "SaveGames")
# Also reported for the Steam build. The first Minecraft Dungeons is an Unreal project called "Dungeons" too and
# may have left this folder behind, so here only a folder with a hero save in it counts.
_OTHER_SAVE_GAMES = Path("Dungeons", "Saved", "SaveGames")
_HERO_PREFIX = "character"
_PREFIX_USERS = Path("steamapps", "compatdata", STEAM_APP_ID, "pfx", "drive_c", "users")
_LIBRARY_PATH = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')

# Where Steam keeps its files on Linux: the normal install, the older symlink, Flatpak (which has its own home
# folder, with the same three names in it and a data folder besides) and Snap. Most of these are links to one
# another on a given PC; find_folders counts a folder once however it was reached.
_LINUX_STEAM_ROOTS = (
    ".local/share/Steam",
    ".steam/steam",
    ".steam/root",
    ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ".var/app/com.valvesoftware.Steam/data/Steam",
    ".var/app/com.valvesoftware.Steam/.steam/steam",
    ".var/app/com.valvesoftware.Steam/.steam/root",
    "snap/steam/common/.local/share/Steam",
)


@dataclass
class LooseEntry:
    """One ``.sav`` file, with the fields of ``wgs.IndexEntry`` that the rest of the editor reads."""

    name: str  # file name without .sav
    revision: int  # modification time in nanoseconds: changes whenever the file is rewritten
    mtime: int  # FILETIME, like wgs.IndexEntry.mtime
    size: int
    sync_state: int = wgs.SYNCED  # not used: Steam Cloud syncs these files by itself
    local_file: bool = True

    @property
    def file_name(self) -> str:
        return self.name + SAVE_SUFFIX


def is_steam_folder(folder: Path) -> bool:
    """True for a folder of ``.sav`` files (and not an Xbox container folder)."""
    folder = Path(folder)
    if (folder / wgs.INDEX_FILE).is_file():
        return False
    try:
        return any(path.is_file() and path.suffix.lower() == SAVE_SUFFIX for path in folder.iterdir())
    except OSError:
        return False


def _entry(path: Path) -> LooseEntry:
    stat = path.stat()
    return LooseEntry(
        name=path.name[: -len(SAVE_SUFFIX)],
        revision=stat.st_mtime_ns,
        mtime=stat.st_mtime_ns // 100 + wgs._FILETIME_UNIX_EPOCH,
        size=stat.st_size,
    )


def read_entries(folder: Path) -> list[LooseEntry]:
    """Every ``.sav`` file in ``folder``, in name order."""
    paths = [p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() == SAVE_SUFFIX]
    return [_entry(path) for path in sorted(paths, key=lambda p: p.name.lower())]


def find_entry(folder: Path, name: str) -> LooseEntry | None:
    path = Path(folder) / (name + SAVE_SUFFIX)
    try:
        return _entry(path) if path.is_file() else None
    except OSError:
        return None


def read_blobs(folder: Path, entry: LooseEntry) -> dict[str, bytes]:
    return {BLOB_NAME: (Path(folder) / entry.file_name).read_bytes()}


def write_file(folder: Path, name: str, blobs: dict[str, bytes]) -> LooseEntry:
    """Replace ``<name>.sav`` with the new data.

    The data goes into a temporary file next to it first and then takes the place of the old one in one step, so
    the game never sees a half-written save.
    """
    folder = Path(folder)
    target = folder / (name + SAVE_SUFFIX)
    temp = folder / f"{name}.{uuid.uuid4().hex[:8]}{_TEMP_SUFFIX}"
    try:
        with open(temp, "wb") as handle:
            handle.write(blobs[BLOB_NAME])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return _entry(target)


def stamp(folder: Path) -> tuple | None:
    """A value that changes whenever any save in ``folder`` is written, added or removed."""
    try:
        return tuple((e.name, e.revision, e.size) for e in read_entries(folder))
    except OSError:
        return None


# ------------------------------------------------------------------ finding the folders


def _library_roots(steam_root: Path) -> list[Path]:
    """Steam's install folder, plus every other library folder it lists (games can live on another drive)."""
    roots = [steam_root]
    try:
        text = (steam_root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return roots
    for match in _LIBRARY_PATH.finditer(text):
        library = Path(match.group(1).replace("\\\\", "\\"))
        if library not in roots:
            roots.append(library)
    return roots


def _candidate_folders() -> list[Path]:
    app_data: list[Path] = []  # every "AppData\Local" the game could be saving under
    local = os.environ.get("LOCALAPPDATA")
    if local:
        app_data.append(Path(local))
    home = Path.home()
    for relative in _LINUX_STEAM_ROOTS:
        steam_root = home / relative
        for library in _library_roots(steam_root):
            users = library / _PREFIX_USERS
            try:
                prefix_users = sorted(users.iterdir()) if users.is_dir() else []
            except OSError:
                continue
            app_data.extend(user / "AppData" / "Local" for user in prefix_users)
    return [folder / save_games for folder in app_data for save_games in (_SAVE_GAMES, _OTHER_SAVE_GAMES)]


def folder_label(folder: Path) -> str:
    """What to call a folder ``find_folders`` found: "Steam", plus what sets it apart when it isn't the usual one."""
    folder = Path(folder)
    if folder.name != _SAVE_GAMES.name:
        return f"Steam ({folder.name})"  # a folder per Steam account
    game = folder.parent.parent.name
    return "Steam" if game == _SAVE_GAMES.parts[0] else f"Steam ({game} folder)"


def _has_hero_save(folder: Path) -> bool:
    try:
        return any(entry.name.lower().startswith(_HERO_PREFIX) for entry in read_entries(folder))
    except OSError:
        return False


def find_folders() -> list[Path]:
    """Save folders of the Steam version on this PC, most recently saved first.

    A folder counts when it holds ``.sav`` files itself or in a folder one level down (some Steam builds keep a
    folder per Steam account).
    """
    found: dict[Path, float] = {}
    for candidate in _candidate_folders():
        ours_for_sure = candidate.parts[-len(_SAVE_GAMES.parts) :] == _SAVE_GAMES.parts
        try:
            if not candidate.is_dir():
                continue
            folders = [candidate] + [child for child in candidate.iterdir() if child.is_dir()]
        except OSError:
            continue
        for folder in folders:
            if not is_steam_folder(folder) or not (ours_for_sure or _has_hero_save(folder)):
                continue
            try:
                newest = max(entry.revision for entry in read_entries(folder))
            except (OSError, ValueError):
                continue
            found.setdefault(folder.resolve(), newest)
    return sorted(found, key=found.get, reverse=True)
