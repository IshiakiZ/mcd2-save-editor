"""Finding, classifying, backing up and saving Minecraft Dungeons II save data."""

from __future__ import annotations

import csv
import enum
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import codec, paths, wgs
from .hero import Hero, is_hero_document

PACKAGE_PATTERN = "Microsoft.MinecraftDungeons2_*"
GAME_EXECUTABLES = ("Dungeons-WinGDK-Shipping.exe", "Dungeons.exe")
DEFAULT_BACKUP_ROOT = paths.data_dir() / "backups"
BACKUP_INFO_FILE = "backup-info.json"
STEAM_SAVE_DIR = Path("Dungeons") / "Saved" / "SaveGames"
_FILETIME_UNIX_EPOCH = 116_444_736_000_000_000

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


def _protected_note(name: str) -> str | None:
    normalized = "".join(character.casefold() for character in name if character.isalnum())
    return next(
        (
            note
            for protected_name, note in PROTECTED_CONTAINERS.items()
            if "".join(character.casefold() for character in protected_name if character.isalnum()) == normalized
        ),
        None,
    )


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


def running_game_processes() -> list[str]:
    """Names of Minecraft Dungeons II processes that are currently running."""
    if os.name != "nt":
        return []
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
    running = {row[0].lower() for row in csv.reader(result.stdout.splitlines()) if row}
    return [exe for exe in GAME_EXECUTABLES if exe.lower() in running]


def find_profiles() -> list[Path]:
    """Save folders for installed versions of the game, most recently used first."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    indexes = Path(local, "Packages").glob(f"{PACKAGE_PATTERN}/SystemAppData/wgs/*/{wgs.INDEX_FILE}")
    profiles = {index.parent for index in indexes}
    steam = Path(local) / STEAM_SAVE_DIR
    if any(steam.glob("*.sav")):
        profiles.add(steam)
    return sorted(profiles, key=_profile_mtime, reverse=True)


def _profile_mtime(path: Path) -> float:
    try:
        if (path / wgs.INDEX_FILE).is_file():
            return (path / wgs.INDEX_FILE).stat().st_mtime
        return max((save.stat().st_mtime for save in path.glob("*.sav")), default=0)
    except OSError:
        return 0


def profile_stamp(path: Path) -> tuple:
    """Return a lightweight disk stamp for WGS indexes or standalone save files."""
    path = Path(path)
    try:
        index = path / wgs.INDEX_FILE
        if index.is_file():
            stat = index.stat()
            return stat.st_mtime_ns, stat.st_size
        return tuple((save.name, save.stat().st_mtime_ns, save.stat().st_size) for save in sorted(path.glob("*.sav")))
    except OSError:
        return ()


@dataclass
class DirectSaveEntry:
    """Metadata for a standalone Steam save file, shaped for the shared UI."""

    name: str
    revision: int
    sync_state: int
    mtime: int
    size: int


@dataclass
class Container:
    entry: wgs.IndexEntry | DirectSaveEntry
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
            return FRIENDLY_NAMES.get(self.name, self.name)
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
    """The save data for one local Xbox or Steam user."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.reload()

    def reload(self) -> None:
        self.is_steam = not (self.path / wgs.INDEX_FILE).is_file()
        if self.is_steam:
            self.index = None
            self.containers = [self._load_steam_file(path) for path in sorted(self.path.glob("*.sav"))]
        else:
            self.index = wgs.read_index(self.path)
            self.containers = [self._load(entry) for entry in self.index.entries]

    def _load_steam_file(self, path: Path) -> Container:
        name = path.stem
        protected = _protected_note(name)
        if protected is not None:
            entry = _steam_entry(path, name)
            return Container(entry, Kind.PROTECTED, protected, blobs={})
        relative = path.relative_to(self.path).as_posix()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return Container(_steam_entry(path, name), Kind.UNSUPPORTED, f"Could not be read: {exc}", blobs={})
        try:
            decoded = codec.decode_blob(raw)
        except codec.NotASaveDocument:
            return Container(_steam_entry(path, name), Kind.UNSUPPORTED, "Encrypted or unknown format. Not shown.", blobs={relative: raw})
        if is_hero_document(decoded.document) and Hero(decoded.document).is_online:
            return Container(_steam_entry(path, name), Kind.PROTECTED, ONLINE_HERO_NOTE, {relative: raw}, relative, decoded)
        return Container(_steam_entry(path, name), Kind.EDITABLE, "Save data", {relative: raw}, relative, decoded)

    def _load(self, entry: wgs.IndexEntry) -> Container:
        protected = _protected_note(entry.name)
        if protected is not None:
            return Container(entry, Kind.PROTECTED, protected, blobs={})
        if entry.sync_state == wgs.DELETED:
            return Container(entry, Kind.UNSUPPORTED, "Marked as deleted.", blobs={})
        try:
            blobs = wgs.read_blobs(self.path, entry)
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
        blob_name = container.blob_name
        if blob_name is None:
            raise ValueError(f"{name} has no editable save file")

        backup = make_backup(self.path, backup_root, f"Before saving {container.label}")

        def write() -> None:
            if self.is_steam:
                _write_steam_file(self.path, blob_name, raw)
            else:
                wgs.write_container(self.path, name, {**container.blobs, blob_name: raw})
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

        Writing them as new revisions (instead of copying the old files back)
        makes Gaming Services upload them rather than re-download the cloud
        copy. Returns the names of the containers that were restored.
        """
        self._ensure_game_closed(check_game)
        current = SaveProfile(self.path)
        old = SaveProfile(backup.profile_copy)
        to_restore = []
        for old_container in old.containers:
            now = current.get(old_container.name)
            if (
                old_container.kind is Kind.EDITABLE
                and now is not None
                and now.kind is Kind.EDITABLE
                and set(now.blobs) == set(old_container.blobs)
                and now.blobs != old_container.blobs
            ):
                to_restore.append(old_container)
        if not to_restore:
            return []

        safety = make_backup(self.path, backup_root, f"Before restoring backup from {backup.created:%Y-%m-%d %H:%M:%S}")

        def write() -> None:
            for container in to_restore:
                blob_name = container.blob_name
                if blob_name is None:
                    raise RuntimeError(f"{container.label} has no save file")
                if current.is_steam:
                    _write_steam_file(self.path, blob_name, container.blobs[blob_name])
                else:
                    wgs.write_container(self.path, container.name, container.blobs)
            written = SaveProfile(self.path)
            for container in to_restore:
                saved = written.get(container.name)
                if saved is None or saved.blobs != container.blobs:
                    raise RuntimeError(f"{container.label} did not read back correctly")

        _write_or_roll_back(write, self.path, safety)
        self.reload()
        return [container.name for container in to_restore]

    def _ensure_game_closed(self, check_game: Callable[[], list[str]] | None) -> None:
        running = (check_game or running_game_processes)()
        if running:
            raise GameRunningError(
                f"Minecraft Dungeons II is running ({', '.join(running)}). Close the game, wait a few seconds, then try again."
            )

    def _ensure_unchanged(self, container: Container) -> None:
        if self.is_steam:
            blob_name = container.blob_name
            if blob_name is None:
                raise StaleSaveError(f"{container.label} no longer has a save file")
            path = self.path / blob_name
            try:
                unchanged = path.read_bytes() == container.blobs[blob_name]
            except OSError:
                unchanged = False
            if not unchanged:
                raise StaleSaveError(
                    f"{container.label} changed on disk after it was loaded (the game probably saved). Reload and make your edits again."
                )
            return
        entry = wgs.read_index(self.path).find(container.name)
        if entry is None or entry.revision != container.entry.revision or wgs.read_blobs(self.path, entry) != container.blobs:
            raise StaleSaveError(
                f"{container.label} changed on disk after it was loaded (the game probably saved). Reload and make your edits again."
            )


def _steam_entry(path: Path, name: str) -> DirectSaveEntry:
    stat = path.stat()
    return DirectSaveEntry(
        name=name,
        revision=stat.st_mtime_ns,
        sync_state=wgs.SYNCED,
        mtime=int(stat.st_mtime * 10_000_000) + _FILETIME_UNIX_EPOCH,
        size=stat.st_size,
    )


def _write_steam_file(profile: Path, relative: str, data: bytes) -> None:
    path = Path(profile) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


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
    info = {"created": now.isoformat(timespec="seconds"), "reason": reason, "source": str(profile), "profile": profile.name}
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
            copy = folder / info.get("profile", Path(info["source"]).name)
            if not copy.is_dir() or not ((copy / wgs.INDEX_FILE).is_file() or any(copy.glob("*.sav"))):
                copy = next(
                    child
                    for child in folder.iterdir()
                    if child.is_dir() and ((child / wgs.INDEX_FILE).is_file() or any(child.glob("*.sav")))
                )
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
