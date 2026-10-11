"""Item pictures from the editor's picture pack on Batchly (batch-ly.com), the developer's own site.

The pack is a folder there holding the pictures and a list of them, ``index.json``::

    {"version": 1, "pictures": [{"name": "Mystic Circlet", "file": "Mystic Circlet.png", "size": 12345, "sha256": "…"}]}

``list_pictures`` reads the list. ``download_pictures`` saves the pictures into the icons folder as
``<item name>.png`` and checks every one against the size and SHA-256 the list gives for it, so what lands on the
PC is what the list promised: a PNG picture, and nothing else. ``tools/make_picture_pack.py`` makes the folder to
put on the site.

With no pack on the site, asking for it finds nothing (``NoPack``) and Get item pictures… gets the Minecraft
Wiki's pictures as it used to: ``best_source`` chooses.

The editor also gets the pack by itself when it opens (``missing`` says what a PC hasn't got yet), unless that
has been turned off in its menu. It never gets the Minecraft Wiki's pictures unasked.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import __version__, edition, wiki
from .icons import PACK_FOLDER, WIKI_FOLDER, normalize

PACK_URL = "https://batch-ly.com/mcd2/pictures/"  # index.json and the pictures are in this folder
PACK_HOST = "batch-ly.com"
INDEX_FILE = "index.json"
USER_AGENT = f"Dungeons2SaveEditor/{__version__} (+https://github.com/IshiakiZ/mcd2-save-editor)"
MAX_PICTURES = 2000
MAX_PICTURE_BYTES = 2_000_000
MAX_INDEX_BYTES = 2_000_000
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class NoPack(OSError):
    """The site has no picture pack (yet)."""


@dataclass(frozen=True)
class PackPicture:
    name: str  # the item's in-game name, e.g. "Mystic Circlet"
    file: str  # its file in the pack's folder
    size: int
    sha256: str


def _get(url: str, most: int, timeout: float = 30) -> bytes:
    edition.require_online("download pictures")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not (host == PACK_HOST or host.endswith("." + PACK_HOST)):
        raise ValueError(f"refusing to download from {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(most + 1)
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            raise NoPack(f"{PACK_HOST} has no picture pack yet") from error
        raise
    if len(data) > most:
        raise ValueError(f"{url} is bigger than a picture pack's files may be")
    return data


def pictures_from_index(data: Any) -> list[PackPicture]:
    """The pictures an index lists, one per item. Anything in it that isn't a plain PNG file in the pack's own
    folder, with a size and a SHA-256, makes the whole index unusable: a list the editor can't trust isn't used."""
    listed = data.get("pictures") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(listed, list) or len(listed) > MAX_PICTURES:
        raise ValueError("the picture pack's list isn't one this version of the editor can read")
    chosen: dict[str, PackPicture] = {}
    for entry in listed:
        name, file, size, digest = (entry.get(key) for key in ("name", "file", "size", "sha256")) if isinstance(entry, dict) else (None,) * 4
        if (
            not isinstance(name, str) or not name.strip() or not isinstance(file, str)
            or _UNSAFE.search(file) or file.startswith(".") or not file.lower().endswith(".png")
            or isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_PICTURE_BYTES
            or not isinstance(digest, str) or not _SHA256.fullmatch(digest)
        ):
            raise ValueError(f"the picture pack's list has an entry the editor can't use: {str(entry)[:120]}")
        chosen.setdefault(normalize(name), PackPicture(name.strip(), file, size, digest))
    return sorted(chosen.values(), key=lambda picture: picture.name.lower())


def list_pictures() -> list[PackPicture]:
    """What the pack on the site holds. ``NoPack`` when there is none."""
    return pictures_from_index(json.loads(_get(PACK_URL + INDEX_FILE, MAX_INDEX_BYTES).decode("utf-8")))


def file_name(picture: PackPicture) -> str:
    return _UNSAFE.sub("", picture.name) + ".png"


def _same(path: Path, picture: PackPicture) -> bool:
    try:
        return path.stat().st_size == picture.size and hashlib.sha256(path.read_bytes()).hexdigest() == picture.sha256
    except OSError:
        return False


def missing(pictures: list[PackPicture], folder: Path) -> list[PackPicture]:
    """The pictures of the pack that ``folder`` hasn't got, or has in another size than the list gives: what
    there is to download. (The download itself checks every picture against its SHA-256.)"""
    wanted = []
    for picture in pictures:
        try:
            here = (Path(folder) / file_name(picture)).stat().st_size == picture.size
        except OSError:
            here = False
        if not here:
            wanted.append(picture)
    return wanted


def download_pictures(
    pictures: list[PackPicture],
    folder: Path,
    progress: Callable[[int, int, str], None] | None = None,
    pause: float = 0.05,
) -> tuple[int, int]:
    """Save ``pictures`` into ``folder``, skipping ones already there. Returns (downloaded, skipped). A picture
    that isn't the one the list describes stops the download: nothing of it is kept."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = 0
    for number, picture in enumerate(pictures, 1):
        target = folder / file_name(picture)
        if _same(target, picture):
            skipped += 1
        else:
            data = _get(PACK_URL + urllib.parse.quote(picture.file), MAX_PICTURE_BYTES)
            if len(data) != picture.size or hashlib.sha256(data).hexdigest() != picture.sha256:
                raise ValueError(f"the pack's picture of {picture.name} isn't the one its list describes")
            if not data.startswith(PNG_MAGIC):
                raise ValueError(f"the pack's picture of {picture.name} is not a PNG image")
            temp = target.with_name(target.name + ".part")
            temp.write_bytes(data)
            temp.replace(target)
            downloaded += 1
            time.sleep(pause)
        if progress is not None:
            progress(number, len(pictures), picture.name)
    return downloaded, skipped


@dataclass(frozen=True)
class Source:
    """Somewhere the editor gets item pictures from, with what it has."""

    site: str  # as it's named to the player: batch-ly.com, minecraft.wiki
    folder: str  # where its pictures go, under the icons folder
    pictures: list
    file_name: Callable[[Any], str]
    download: Callable[..., tuple[int, int]]


def best_source() -> Source:
    """The picture pack when the site has one with pictures in it that the editor can read, else the Minecraft
    Wiki: with no pack up yet, an empty one, the site out of reach or a list it can't use, the player still gets
    pictures. (The edition that never goes online asks neither, and says so.)"""
    try:
        packed = list_pictures()
    except edition.OfflineEdition:
        raise
    except (OSError, ValueError):
        packed = []
    if packed:
        return Source(PACK_HOST, PACK_FOLDER, packed, file_name, download_pictures)
    return Source(wiki.WIKI_HOST, WIKI_FOLDER, wiki.list_pictures(), wiki.file_name, wiki.download_pictures)
