"""Makes the editor's picture pack from a folder of item pictures: the folder to put on batch-ly.com.

    python tools/make_picture_pack.py <pictures> <pack>

``<pictures>`` holds one picture per item, named after the item as the game names it ("Mystic Circlet.png", "The
Burning Blade.webp"; any folders inside are looked through too), and one for a stat under its save name
("Emeralds.png"). ``<pack>`` gets each picture as a PNG named
after its item, no bigger than it needs to be, and ``index.json``, the list the editor reads: every picture's
item, file, size and SHA-256 (dungeons2_editor/picture_pack.py checks each download against it).

Put the contents of ``<pack>`` on the site so that ``index.json`` answers at the address in picture_pack.PACK_URL.
The pictures are named in what it prints: which items got one, which items are still without, and which files
matched no item (rename those after their item and run it again).

Needs Pillow. The pictures stay out of this repository: they are the game's artwork, and only the pack on the
site holds them.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dungeons2_editor import picture_pack  # noqa: E402
from dungeons2_editor.hero import game_items  # noqa: E402
from dungeons2_editor.icons import ALIASES, normalize  # noqa: E402

PICTURES = {".png", ".webp", ".jpg", ".jpeg", ".gif", ".bmp"}
MOST = 256  # pixels along the longer side: plenty for a tile, and small to download
STATS = ("Emeralds", "SpringStone", "EnchantmentPoints", "Level", "XP")  # the stats the editor shows a picture beside, by their save names


def item_names() -> dict[str, str]:
    """Every name a picture can be filed under, by its normalised form: each item, each Unique, the names the
    editor already knows a save's own name by (icons.ALIASES), and the stats that are shown with a picture."""
    names: dict[str, str] = {}
    for item in game_items():
        for name in (item.name, item.unique):
            if name:
                names.setdefault(normalize(name), name)
    for picture in ALIASES.values():
        names.setdefault(normalize(picture), picture)
    for stat in STATS:
        names.setdefault(normalize(stat), stat)
    return names


def as_png(path: Path) -> bytes:
    """The picture as a PNG with its transparency, shrunk to MOST pixels if it's bigger, and nothing else in it."""
    from PIL import Image

    with Image.open(path) as picture:
        picture = picture.convert("RGBA")
        picture.thumbnail((MOST, MOST), Image.LANCZOS)
        out = io.BytesIO()
        picture.save(out, format="PNG", optimize=True)
    return out.getvalue()


def make(source: Path, pack: Path) -> tuple[list[str], list[str], list[str]]:
    """Fill ``pack`` from ``source``. Returns (items that got a picture, items without one, files that matched
    no item)."""
    names = item_names()
    pack.mkdir(parents=True, exist_ok=True)
    listed: dict[str, dict] = {}
    strays: list[str] = []
    for path in sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in PICTURES):
        name = names.get(normalize(path.stem))
        if name is None:
            strays.append(str(path.relative_to(source)))
            continue
        if name in listed:
            continue  # the first picture of an item wins
        data = as_png(path)
        if len(data) > picture_pack.MAX_PICTURE_BYTES:
            raise SystemExit(f"{path.name} is still {len(data):,} bytes as a {MOST}-pixel PNG: too big for the pack")
        entry = picture_pack.PackPicture(name, "", len(data), hashlib.sha256(data).hexdigest())
        file = picture_pack.file_name(entry)
        (pack / file).write_bytes(data)
        listed[name] = {"name": name, "file": file, "size": len(data), "sha256": entry.sha256}
    index = {"version": 1, "pictures": [listed[name] for name in sorted(listed, key=str.lower)]}
    picture_pack.pictures_from_index(index)  # the editor must be able to read what this writes
    (pack / picture_pack.INDEX_FILE).write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    without = sorted((name for name in names.values() if name not in listed), key=str.lower)
    return sorted(listed, key=str.lower), without, strays


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    source, pack = Path(argv[0]), Path(argv[1])
    if not source.is_dir():
        print(f"{source} isn't a folder")
        return 2
    made, without, strays = make(source, pack)
    size = sum(path.stat().st_size for path in pack.glob("*.png"))
    print(f"{len(made)} pictures, {size / 1e6:.1f} MB, and {picture_pack.INDEX_FILE} -> {pack}")
    print(f"Put what's in that folder at {picture_pack.PACK_URL}")
    if without:
        print(f"\n{len(without)} items are still without a picture:\n  " + ", ".join(without))
    if strays:
        print(f"\n{len(strays)} files matched no item (rename them after their item):\n  " + "\n  ".join(strays))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
