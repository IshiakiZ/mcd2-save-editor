"""Finding, classifying, backing up and saving Minecraft Dungeons II save data."""

from __future__ import annotations

import csv
import enum
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import codec, paths, steam, wgs
from .hero import Hero, is_hero_document

PACKAGE_PATTERN = "Microsoft.MinecraftDungeons2_*"
GAME_EXECUTABLES = ("Dungeons-WinGDK-Shipping.exe", "Dungeons-Win64-Shipping.exe", "Dungeons.exe")
# The Steam build's executable name isn't known for certain, so any Dungeons "...-Shipping.exe" counts too.
_GAME_PROCESS = re.compile(r"^dungeons[\w.-]*shipping\.exe$", re.IGNORECASE)
DEFAULT_BACKUP_ROOT = paths.data_dir() / "backups"
BACKUP_INFO_FILE = "backup-info.json"

# Containers the editor never reads or writes. The first two hold sign-in and
# purchase tokens issued by the game's servers; the others are encrypted.
PROTECTED_CONTAINERS = {
    "auth_dynamic_entjwtbin": "Online sign-in token. Never read or changed.",
    "entitlementsjwtbin": "Record of owned editions and DLC. Never read or changed.",
    "Guidbin": "Device ID, encrypted by Windows. Never read or changed.",
    "OnlineDataTables": "Encrypted cache of online game data. Never read or changed.",
}

FRIENDLY_NAMES = {
    "GlobalSaveDataDefault": "Settings & profile",
    "auth_dynamic_entjwtbin": "Sign-in token",
    "entitlementsjwtbin": "Entitlements",
    "Guidbin": "Device ID",
    "OnlineDataTables": "Online data cache",
}

ONLINE_HERO_NOTE = "Online hero. Its real data lives on the game's servers, so this copy is never changed."


def _plain(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


_PROTECTED_BY_PLAIN_NAME = {_plain(name): name for name in PROTECTED_CONTAINERS}


def protected_name(name: str) -> str | None:
    """The protected container that ``name`` is, or None. The Steam build spells these names with dots
    (``auth_dynamic_ent.jwt.bin.sav``) where the Xbox build has none (``auth_dynamic_entjwtbin``)."""
    return _PROTECTED_BY_PLAIN_NAME.get(_plain(name))


class Kind(enum.Enum):
    EDITABLE = "Editable"
    PROTECTED = "Protected"
    UNSUPPORTED = "Read-only"


class GameRunningError(RuntimeError):
    pass


class StaleSaveError(RuntimeError):
    pass


class SaveFailedError(RuntimeError):
    def __init__(self, message: str, backup: Path, rolled_back: bool):
        super().__init__(message)
        self.backup = backup
        self.rolled_back = rolled_back


def _is_game_process(name: str) -> bool:
    return name.lower() in {exe.lower() for exe in GAME_EXECUTABLES} or bool(_GAME_PROCESS.match(name))


def _linux_process_names() -> set[str]:
    """Executable names of every running process. Under Proton the game is a Wine process, so the name that
    matters is the .exe in the command line (``Z:\\...\\Dungeons-Win64-Shipping.exe``), not the process name."""
    names: set[str] = set()
    proc = Path("/proc")
    try:
        entries = [entry for entry in proc.iterdir() if entry.name.isdigit()]
    except OSError:
        return names
    for entry in entries:
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        for argument in raw.split(b"\0")[:3]:
            text = argument.decode("utf-8", errors="replace")
            if text.lower().endswith(".exe"):
                names.add(re.split(r"[\\/]", text)[-1])
    return names


_EXE_IN_COMMAND = re.compile(r"(?:^|[\\/\s])([^\\/]*?\.exe)(?=\s|$)", re.IGNORECASE)


def _ps_process_names() -> set[str]:
    """The same on a Mac, which has no /proc: the game runs under Wine there too (in CrossOver, Whisky and the
    like), so its .exe is in a command line, and ps prints the command lines."""
    try:
        result = subprocess.run(["ps", "-Ao", "args="], capture_output=True, text=True, errors="replace", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return set()
    return {match.group(1).strip() for line in result.stdout.splitlines() for match in _EXE_IN_COMMAND.finditer(line)}


def running_game_processes() -> list[str]:
    """Names of Minecraft Dungeons II processes that are currently running."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return []
        names = {row[0] for row in csv.reader(result.stdout.splitlines()) if row}
    elif sys.platform == "darwin":
        names = _ps_process_names()
    else:
        names = _linux_process_names()
    return sorted(name for name in names if _is_game_process(name))


def layout_of(path: Path) -> str:
    """``"steam"`` for a folder of ``.sav`` files, ``"xbox"`` for a folder with ``containers.index``."""
    return "steam" if steam.is_steam_folder(Path(path)) else "xbox"


def find_profiles() -> list[Path]:
    """Save folders of the installed game (Xbox app: one per Xbox user; Steam: the SaveGames folder), most
    recently used first."""
    found: list[tuple[float, Path]] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        indexes = Path(local, "Packages").glob(f"{PACKAGE_PATTERN}/SystemAppData/wgs/*/{wgs.INDEX_FILE}")
        found += [(index.stat().st_mtime, index.parent) for index in indexes]
    for folder in steam.find_folders():
        try:
            newest = max(entry.revision for entry in steam.read_entries(folder)) / 1e9
        except (OSError, ValueError):
            continue
        found.append((newest, folder))
    return [path for _, path in sorted(found, key=lambda pair: pair[0], reverse=True)]


def profile_stamp(path: Path) -> tuple | None:
    """A value that changes when the game (or anything) writes to the save folder; None if unreadable."""
    path = Path(path)
    if layout_of(path) == "steam":
        return steam.stamp(path)
    try:
        stat = (path / wgs.INDEX_FILE).stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def current_revision(path: Path, name: str) -> int | None:
    """The revision of container ``name`` on disk now, or None if it's gone. May raise OSError or
    ``wgs.WgsFormatError`` when the folder is caught mid-write."""
    path = Path(path)
    if layout_of(path) == "steam":
        entry = steam.find_entry(path, name)
    else:
        entry = wgs.read_index(path).find(name)
    return None if entry is None else entry.revision


@dataclass
class Container:
    entry: wgs.IndexEntry | steam.LooseEntry
    kind: Kind
    note: str
    blobs: dict[str, bytes]  # raw blob bytes as loaded; empty for protected containers
    blob_name: str | None = None  # blob holding the JSON document
    decoded: codec.DecodedBlob | None = None

    @property
    def name(self) -> str:
        return self.entry.name

    @property
    def hero(self) -> Hero | None:
        """The saved hero, if this container holds one (as loaded, not as edited)."""
        if self.decoded is not None and is_hero_document(self.decoded.document):
            return Hero(self.decoded.document)
        return None

    @property
    def label(self) -> str:
        hero = self.hero
        if hero is None:
            return FRIENDLY_NAMES.get(protected_name(self.name) or self.name, self.name)
        kind = "Online hero" if hero.is_online else "Offline hero"
        return f"{kind} ({hero.skin})" if hero.skin else f"{kind} {hero.character_id[:8]}"


@dataclass
class Backup:
    path: Path
    profile_copy: Path
    created: datetime
    reason: str
    source: str


class SaveProfile:
    """The containers of one set of Minecraft Dungeons II saves: one Xbox user's containers, or the Steam
    version's folder of .sav files. ``layout`` says which."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.layout = layout_of(self.path)
        self.reload()

    @property
    def is_steam(self) -> bool:
        return self.layout == "steam"

    def reload(self) -> None:
        if self.is_steam:
            self.index = None
            entries = steam.read_entries(self.path)
        else:
            self.index = wgs.read_index(self.path)
            entries = self.index.entries
        self.containers = [self._load(entry) for entry in entries]

    def _read_blobs(self, entry) -> dict[str, bytes]:
        return steam.read_blobs(self.path, entry) if self.is_steam else wgs.read_blobs(self.path, entry)

    def _write_blobs(self, name: str, blobs: dict[str, bytes]) -> None:
        if self.is_steam:
            steam.write_file(self.path, name, blobs)
        else:
            wgs.write_container(self.path, name, blobs)

    def _load(self, entry) -> Container:
        protected = protected_name(entry.name)
        if protected is not None:
            return Container(entry, Kind.PROTECTED, PROTECTED_CONTAINERS[protected], blobs={})
        if entry.sync_state == wgs.DELETED:
            return Container(entry, Kind.UNSUPPORTED, "Marked as deleted.", blobs={})
        try:
            blobs = self._read_blobs(entry)
        except (OSError, wgs.WgsFormatError) as exc:
            return Container(entry, Kind.UNSUPPORTED, f"Could not be read: {exc}", blobs={})
        for blob_name, raw in blobs.items():
            try:
                decoded = codec.decode_blob(raw)
            except codec.NotASaveDocument:
                continue
            if is_hero_document(decoded.document) and Hero(decoded.document).is_online:
                return Container(entry, Kind.PROTECTED, ONLINE_HERO_NOTE, blobs, blob_name, decoded)
            return Container(entry, Kind.EDITABLE, "Save data", blobs, blob_name, decoded)
        if any(raw.startswith(b"GVAS") for raw in blobs.values()):
            return Container(entry, Kind.UNSUPPORTED, "Unreal Engine binary save (GVAS). This format isn't supported yet.", blobs)
        return Container(entry, Kind.UNSUPPORTED, "Encrypted or unknown format. Not shown.", blobs)

    def get(self, name: str) -> Container | None:
        return next((container for container in self.containers if container.name == name), None)

    def save(
        self,
        name: str,
        document: Any,
        backup_root: Path = DEFAULT_BACKUP_ROOT,
        check_game: Callable[[], list[str]] | None = None,
    ) -> Path:
        """Write ``document`` into container ``name``. Returns the backup made first.

        Refuses if the game is running or the container changed on disk since
        this profile was loaded. If writing or the read-back check fails, the
        profile folder is put back exactly as it was.
        """
        container = self.get(name)
        if container is None or container.kind is not Kind.EDITABLE or container.decoded is None:
            raise ValueError(f"{name} is not editable")
        self._ensure_game_closed(check_game)
        self._ensure_unchanged(container)

        raw = codec.encode_blob(document, container.decoded.style)
        if codec.decode_blob(raw).document != document:
            raise ValueError("the edited data could not be encoded faithfully")

        backup = make_backup(self.path, backup_root, f"Before saving {container.label}")

        def write() -> None:
            self._write_blobs(name, {**container.blobs, container.blob_name: raw})
            written = SaveProfile(self.path).get(name)
            if written is None or written.decoded is None or written.decoded.document != document:
                raise RuntimeError("the saved data did not read back correctly")

        _write_or_roll_back(write, self.path, backup)
        self.reload()
        return backup

    def restore(
        self,
        backup: Backup,
        backup_root: Path = DEFAULT_BACKUP_ROOT,
        check_game: Callable[[], list[str]] | None = None,
    ) -> list[str]:
        """Write the editable containers stored in ``backup`` back as new revisions.

        On the Xbox layout, writing them as new revisions (instead of copying the
        old files back) makes Gaming Services upload them rather than
        re-download the cloud copy. On Steam the files are simply replaced. Returns the names of the containers that were restored.
        Only a save that is still in the folder is put back; ``restore_problems`` says which ones aren't.
        """
        self._ensure_game_closed(check_game)
        to_restore, _problems = self._restore_plan(backup)
        if not to_restore:
            return []

        safety = make_backup(self.path, backup_root, f"Before restoring backup from {backup.created:%Y-%m-%d %H:%M:%S}")

        def write() -> None:
            for container in to_restore:
                self._write_blobs(container.name, container.blobs)
            written = SaveProfile(self.path)
            for container in to_restore:
                if written.get(container.name).blobs != container.blobs:
                    raise RuntimeError(f"{container.label} did not read back correctly")

        _write_or_roll_back(write, self.path, safety)
        self.reload()
        return [container.name for container in to_restore]

    def restore_problems(self, backup: Backup) -> list[str]:
        """A sentence for each save in ``backup`` that ``restore`` can't put back, as things are now."""
        return self._restore_plan(backup)[1]

    def _restore_plan(self, backup: Backup) -> tuple[list[Container], list[str]]:
        """The containers of ``backup`` that differ from what's saved now and can be written back, and why
        each of the others can't. A save is only ever written over one that's still there: making a
        container the game has removed would be a guess at how it tells the Xbox cloud about it."""
        current = SaveProfile(self.path)
        to_restore, problems = [], []
        for old_container in SaveProfile(backup.profile_copy).containers:
            if old_container.kind is not Kind.EDITABLE:
                continue
            now = current.get(old_container.name)
            if now is None:
                problems.append(f"{old_container.label} isn't in your saves any more.")
            elif now.entry.sync_state == wgs.DELETED:
                problems.append(f"{old_container.label} has been deleted in the game.")
            elif now.kind is not Kind.EDITABLE:
                problems.append(f"{old_container.label} can't be changed as it is now: {now.note}")
            elif set(now.blobs) != set(old_container.blobs):
                problems.append(f"{old_container.label} is stored in a different way now.")
            elif now.blobs != old_container.blobs:
                to_restore.append(old_container)
        return to_restore, problems

    def _ensure_game_closed(self, check_game: Callable[[], list[str]] | None) -> None:
        running = (check_game or running_game_processes)()
        if running:
            raise GameRunningError(
                f"Minecraft Dungeons II is running ({', '.join(running)}). Close the game, wait a few seconds, then try again."
            )

    def _ensure_unchanged(self, container: Container) -> None:
        if self.is_steam:
            entry = steam.find_entry(self.path, container.name)
        else:
            entry = wgs.read_index(self.path).find(container.name)
        if entry is None or entry.revision != container.entry.revision or self._read_blobs(entry) != container.blobs:
            raise StaleSaveError(
                f"{container.label} changed on disk after it was loaded (the game probably saved). Reload and make your edits again."
            )


def make_backup(profile: Path, backup_root: Path = DEFAULT_BACKUP_ROOT, reason: str = "Manual backup") -> Path:
    """Copy the whole profile folder into a new timestamped backup folder."""
    profile = Path(profile)
    backup_root = Path(backup_root)
    now = datetime.now()
    target = backup_root / now.strftime("%Y-%m-%d_%H-%M-%S")
    suffix = 1
    while target.exists():
        suffix += 1
        target = backup_root / f"{now:%Y-%m-%d_%H-%M-%S}_{suffix}"
    shutil.copytree(profile, target / profile.name)
    info = {"created": now.isoformat(timespec="seconds"), "reason": reason, "source": str(profile)}
    (target / BACKUP_INFO_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")
    return target


def list_backups(backup_root: Path = DEFAULT_BACKUP_ROOT) -> list[Backup]:
    """Backups in ``backup_root``, newest first."""
    backups = []
    root = Path(backup_root)
    if not root.is_dir():
        return backups
    for folder in root.iterdir():
        try:
            info = json.loads((folder / BACKUP_INFO_FILE).read_text(encoding="utf-8"))
            copy = next(child for child in folder.iterdir() if child.is_dir() and ((child / wgs.INDEX_FILE).is_file() or steam.is_steam_folder(child)))
            created = datetime.fromisoformat(info["created"])
        except (OSError, ValueError, KeyError, StopIteration):
            continue
        backups.append(Backup(folder, copy, created, info.get("reason", ""), info.get("source", "")))
    return sorted(backups, key=lambda backup: (backup.created, backup.path.name), reverse=True)


def _write_or_roll_back(write: Callable[[], None], profile: Path, backup: Path) -> None:
    """Run ``write``; if it fails, put the profile folder back as stored in ``backup``."""
    try:
        write()
    except Exception as exc:
        try:
            _copy_folder_over(backup / profile.name, profile)
        except Exception as rollback_exc:
            raise SaveFailedError(
                f"Saving failed ({exc}) and putting the old files back failed too ({rollback_exc}). "
                f"A full copy of your saves from just before is in: {backup}",
                backup,
                rolled_back=False,
            ) from exc
        raise SaveFailedError(f"Saving failed: {exc}. Your saves were put back exactly as they were.", backup, rolled_back=True) from exc


def _copy_folder_over(source: Path, target: Path) -> None:
    """Make ``target`` hold exactly the files in ``source``."""
    for path in sorted(target.rglob("*"), reverse=True):
        relative = path.relative_to(target)
        if not (source / relative).exists():
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()
    shutil.copytree(source, target, dirs_exist_ok=True)
