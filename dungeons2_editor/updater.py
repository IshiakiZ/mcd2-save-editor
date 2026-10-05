"""Finding a newer version on GitHub, and replacing the packaged editor with it.

When the editor's window opens it asks GitHub what the latest release is: one request to the releases API, which
carries nothing about you or your saves. If that release is newer, an Update button appears. Pressing it downloads
the release's MCD2SaveEditor.zip, checks it against the SHA-256 GitHub lists for it, unpacks it into the editor's
data folder and starts the new copy's own ``apply-update`` command. That waits for this window to close, swaps the
editor's folder for the new one and opens the editor again.

A running program can't replace its own files, which is why the new copy does the swap. Run from source there is
nothing to swap, so the button opens the download page instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import __version__, edition, paths

REPOSITORY = "IshiakiZ/mcd2-save-editor"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOADS = f"https://github.com/{REPOSITORY}/releases/download/"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
ASSET_NAME = "MCD2SaveEditor.zip"
APP_FOLDER = "MCD2SaveEditor"  # the folder inside the zip, and the folder the editor runs from
EXE_NAME = "MCD2SaveEditor.exe"
USER_AGENT = f"MCD2SaveEditor/{__version__} (+https://github.com/{REPOSITORY})"
TIMEOUT = 8  # seconds: the check must never hold the editor up
MAX_DOWNLOAD = 300 * 1024 * 1024
OLD_SUFFIX = ".old"


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    version: str  # "1.7.0"
    page: str  # where a person can read about it and download it
    download_url: str
    size: int
    sha256: str | None  # as GitHub lists it; an update isn't installed without one


def parse_version(text: str) -> tuple[int, ...] | None:
    """'v1.7.0' -> (1, 7, 0); None for anything that isn't numbers and dots."""
    parts = text.strip().lstrip("vV").split(".")
    return tuple(int(part) for part in parts) if parts and all(part.isdigit() for part in parts) else None


def is_newer(version: str, than: str = __version__) -> bool:
    new, current = parse_version(version), parse_version(than)
    return new is not None and current is not None and new > current


def _open(url: str, timeout: float = TIMEOUT):
    edition.require_online("look for updates or download them")
    if not url.startswith("https://"):
        raise UpdateError(f"{url} isn't a secure address")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(request, timeout=timeout)


def release_from(data: Any) -> Release | None:
    """The release GitHub's API describes, if it has the editor's zip."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    version = str(data.get("tag_name", "")).lstrip("vV")
    for asset in data.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == ASSET_NAME and parse_version(version) is not None:
            url = str(asset.get("browser_download_url", ""))
            if not url.startswith(DOWNLOADS):
                return None
            digest = str(asset.get("digest") or "")
            sha256 = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None
            return Release(version, str(data.get("html_url") or RELEASES_PAGE), url, int(asset.get("size") or 0), sha256)
    return None


def latest_release(opener: Callable = _open) -> Release | None:
    with opener(LATEST_URL) as response:
        return release_from(json.loads(response.read().decode("utf-8")))


def check(current: str = __version__, opener: Callable = _open) -> Release | None:
    """The latest release if it's newer than ``current``. None when it isn't, or when GitHub can't be reached:
    checking for updates must never get in the way."""
    try:
        release = latest_release(opener)
    except Exception:
        return None
    return release if release is not None and is_newer(release.version, current) else None


# ------------------------------------------------------------------ downloading and unpacking


def staging_dir() -> Path:
    return paths.data_dir() / "update"


def download(release: Release, folder: Path, progress: Callable[[int, int], None] | None = None, opener: Callable = _open) -> Path:
    """Download the release's zip into ``folder`` and check it is the file GitHub lists: same size, same SHA-256."""
    if not release.sha256:
        raise UpdateError("GitHub lists no checksum for this release, so the download can't be checked.")
    if not 0 < release.size <= MAX_DOWNLOAD:
        raise UpdateError("The release's size doesn't look right.")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / (ASSET_NAME + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with opener(release.download_url, 60) as response, open(part, "wb") as out:
            if not str(response.geturl()).startswith("https://"):
                raise UpdateError("The download was sent somewhere that isn't secure.")
            while True:
                block = response.read(256 * 1024)
                if not block:
                    break
                received += len(block)
                if received > release.size:
                    raise UpdateError("The download is bigger than the release GitHub lists.")
                digest.update(block)
                out.write(block)
                if progress is not None:
                    progress(received, release.size)
        if received != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError("The download doesn't match the release GitHub lists, so it wasn't used.")
    except (OSError, UpdateError) as exc:
        part.unlink(missing_ok=True)
        raise exc if isinstance(exc, UpdateError) else UpdateError(f"The download failed: {exc}") from exc
    target = folder / ASSET_NAME
    os.replace(part, target)
    return target


def unpack(archive: Path, folder: Path) -> Path:
    """Unpack the release's zip into ``folder`` and return the editor's folder inside it. Every file must be
    inside MCD2SaveEditor/, so the zip can't write anywhere else."""
    folder = Path(folder)
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = PurePosixPath(member.filename.replace("\\", "/"))
                if name.is_absolute() or ".." in name.parts or ":" in member.filename or name.parts[:1] != (APP_FOLDER,):
                    raise UpdateError(f"The release has a file where it shouldn't be: {member.filename}")
            bundle.extractall(folder)
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdateError(f"The download couldn't be unpacked: {exc}") from exc
    app = folder / APP_FOLDER
    if not (app / EXE_NAME).is_file():
        raise UpdateError(f"The release doesn't contain {EXE_NAME}.")
    return app


def stage(release: Release, progress: Callable[[int, int], None] | None = None, opener: Callable = _open) -> Path:
    """Download and unpack the release into the editor's data folder. Returns the new copy's folder."""
    folder = staging_dir()
    shutil.rmtree(folder, ignore_errors=True)
    archive = download(release, folder, progress, opener)
    app = unpack(archive, folder)
    archive.unlink(missing_ok=True)
    return app


# ------------------------------------------------------------------ replacing the editor


def app_dir() -> Path | None:
    """The folder the packaged editor runs from; None when it runs from source."""
    if not paths.is_frozen():
        return None
    folder = Path(sys.executable).resolve().parent
    return folder if (folder / EXE_NAME).is_file() else None


def can_replace() -> bool:
    return app_dir() is not None


def _start(command: list[str], cwd: Path) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(command, cwd=str(cwd), close_fds=True, creationflags=flags)


def start_swap(staged: Path, target: Path, restart: bool = True) -> None:
    """Start the new copy's apply-update command. The caller then closes the editor, which lets the swap happen;
    with ``restart`` the editor opens again afterwards."""
    command = [str(Path(staged) / EXE_NAME), "apply-update", "--target", str(target)]
    _start(command if restart else command + ["--no-restart"], staging_dir().parent)


def apply_update(target: Path, staged: Path, wait: float = 60, restart: bool = True) -> None:
    """Swap the editor's folder ``target`` for the new copy in ``staged`` (the folder this runs from).

    The old folder is moved aside first and only deleted once the new one is in place; if anything fails it is
    moved back, so the editor that was there keeps working.
    """
    target, staged = Path(target).resolve(), Path(staged).resolve()
    if not (staged / EXE_NAME).is_file():
        raise UpdateError(f"{staged} doesn't hold the new version.")
    if not target.is_dir() or not (target / EXE_NAME).is_file():
        raise UpdateError(f"{target} isn't the editor's folder.")
    if target == staged or target in staged.parents or staged in target.parents:
        raise UpdateError("The new version can't replace the folder it is in.")
    aside = target.with_name(target.name + OLD_SUFFIX)
    deadline = time.monotonic() + wait
    while True:  # until the old window has closed, its files are in use and the folder can't be moved
        try:
            if aside.exists():
                shutil.rmtree(aside)
            os.replace(target, aside)
            break
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise UpdateError(f"The editor's folder couldn't be replaced ({exc}). Is the editor still open, or is the folder read-only?") from exc
            time.sleep(0.5)
    try:
        shutil.copytree(staged, target)
    except OSError as exc:
        shutil.rmtree(target, ignore_errors=True)
        os.replace(aside, target)
        raise UpdateError(f"The new version couldn't be copied into place ({exc}). The version you had is still there.") from exc
    shutil.rmtree(aside, ignore_errors=True)
    if restart:
        _start([str(target / EXE_NAME)], target.parent)


def clean_up(tries: int = 5, pause: float = 2.0) -> None:
    """Remove what an update leaves behind: the unpacked download, and the old folder if it couldn't be deleted.
    The copy that did the swap may still be closing, so this tries a few times."""
    leftovers = [staging_dir()]
    folder = app_dir()
    if folder is not None:
        leftovers.append(folder.with_name(folder.name + OLD_SUFFIX))
    for attempt in range(tries):
        remaining = [path for path in leftovers if path.exists()]
        if not remaining:
            return
        if attempt:
            time.sleep(pause)
        for path in remaining:
            shutil.rmtree(path, ignore_errors=True)
