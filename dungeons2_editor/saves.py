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
    """Save folders (one per Xbox user) of the installed game, most recently used first."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    indexes = Path(local, "Packages").glob(f"{PACKAGE_PATTERN}/SystemAppData/wgs/*/{wgs.INDEX_FILE}")
    return [index.parent for index in sorted(indexes, key=lambda p: p.stat().st_mtime, reverse=True)]


@dataclass
class Container:
    entry: wgs.IndexEntry
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
    """The containers of one Xbox user's Minecraft Dungeons II saves."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.reload()

    def reload(self) -> None:
        self.index = wgs.read_index(self.path)
        self.containers = [self._load(entry) for entry in self.index.entries]

    def _load(self, entry: wgs.IndexEntry) -> Container:
        if entry.name in PROTECTED_CONTAINERS:
            return Container(entry, Kind.PROTECTED, PROTECTED_CONTAINERS[entry.name], blobs={})
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

        backup = make_backup(self.path, backup_root, f"Before saving {container.label}")

        def write() -> None:
            wgs.write_container(self.path, name, {**container.blobs, container.blob_name: raw})
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
                wgs.write_container(self.path, container.name, container.blobs)
            written = SaveProfile(self.path)
            for container in to_restore:
                if written.get(container.name).blobs != container.blobs:
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
        entry = wgs.read_index(self.path).find(container.name)
        if entry is None or entry.revision != container.entry.revision or wgs.read_blobs(self.path, entry) != container.blobs:
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
            copy = next(child for child in folder.iterdir() if (child / wgs.INDEX_FILE).is_file())
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
