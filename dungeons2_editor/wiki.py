"""Item pictures from the Minecraft Wiki (minecraft.wiki).

The wiki hosts a gear icon for most Minecraft Dungeons II items
(``MCD2 Mystic Circlet gear icon.png``) and inventory renders for some others.
``list_pictures`` asks the wiki's API which exist; ``download_pictures`` saves
them into the icons folder as ``<item name>.png``.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import edition
from .icons import normalize

API_URL = "https://minecraft.wiki/api.php"
WIKI_HOST = "minecraft.wiki"
USER_AGENT = "Dungeons2SaveEditor/1.0 (personal save editor)"
GEAR_SUFFIX = "_gear_icon.png"
RENDER_SUFFIX = "_inventory_render.png"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class WikiPicture:
    name: str  # the item's in-game name, e.g. "Mystic Circlet"
    url: str
    size: int


def _get(url: str, timeout: float = 30) -> bytes:
    edition.require_online("download pictures")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not (host == WIKI_HOST or host.endswith("." + WIKI_HOST)):
        raise ValueError(f"refusing to download from {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _all_images(prefix: str) -> list[dict]:
    images: list[dict] = []
    params = {"action": "query", "format": "json", "list": "allimages", "aiprefix": prefix, "ailimit": "500", "aiprop": "size|url"}
    while True:
        data = json.loads(_get(API_URL + "?" + urllib.parse.urlencode(params)))
        images += data["query"]["allimages"]
        if "continue" not in data:
            return images
        params["aicontinue"] = data["continue"]["aicontinue"]


def pictures_from_listing(images: list[dict]) -> list[WikiPicture]:
    """Pick one picture per item: its gear icon, or else its inventory render."""
    chosen: dict[str, WikiPicture] = {}
    for suffix in (GEAR_SUFFIX, RENDER_SUFFIX):
        for image in images:
            name = image.get("name", "")
            if not (name.startswith("MCD2_") and name.endswith(suffix)):
                continue
            item = name[len("MCD2_"):-len(suffix)].replace("_", " ")
            chosen.setdefault(normalize(item), WikiPicture(item, image["url"], int(image.get("size", 0))))
    return sorted(chosen.values(), key=lambda picture: picture.name.lower())


def list_pictures() -> list[WikiPicture]:
    return pictures_from_listing(_all_images("MCD2 "))


def file_name(picture: WikiPicture) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", picture.name) + ".png"


def download_pictures(
    pictures: list[WikiPicture],
    folder: Path,
    progress: Callable[[int, int, str], None] | None = None,
    pause: float = 0.1,
) -> tuple[int, int]:
    """Save ``pictures`` into ``folder``, skipping ones already there. Returns (downloaded, skipped)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = 0
    for number, picture in enumerate(pictures, 1):
        target = folder / file_name(picture)
        if target.exists() and target.stat().st_size == picture.size:
            skipped += 1
        else:
            data = _get(picture.url)
            if not data.startswith(PNG_MAGIC):
                raise ValueError(f"the wiki's picture of {picture.name} is not a PNG image")
            temp = target.with_name(target.name + ".part")
            temp.write_bytes(data)
            temp.replace(target)
            downloaded += 1
            time.sleep(pause)
        if progress is not None:
            progress(number, len(pictures), picture.name)
    return downloaded, skipped
