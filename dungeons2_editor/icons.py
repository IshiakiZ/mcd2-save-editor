"""Pictures for items, stats and heroes.

The game's own art is inside its encrypted asset archive, so the editor does
not extract it. It shows pictures you put in the icons folder instead, found
by name: ``MysticHelmet.png``, ``Mystic Helmet.png``, ``mystic_helmet.png`` and
``SW.Item.MysticHelmet.png`` all match the Mystic Helmet. Items without a
picture get a small square in their rarity's colour.
"""

from __future__ import annotations

import math
import re
import tkinter as tk
from collections import deque
from pathlib import Path

from .paths import data_dir

DEFAULT_ICON_ROOT = data_dir() / "icons"
WIKI_FOLDER = "wiki"  # pictures downloaded from minecraft.wiki; your own pictures take priority
ALIASES_FILE = "aliases.txt"
EXTENSIONS = (".png", ".gif", ".jpg", ".jpeg", ".webp", ".bmp")
# The game's rarity colours (see game_art.RARITY_TILE): Common is grey-brown, Rare green, Special blue, Unique orange.
RARITY_COLORS = {"Common": "#9a8774", "Rare": "#4cb648", "Special": "#1f8be0", "Unique": "#e8702a"}
_FALLBACK_COLOR = "#b0b0b0"

# Save names of items whose picture is filed under a different in-game name.
ALIASES = {
    "MysticHelmet": "Mystic Circlet",
    "HoneyLeggings": "Beekeeper Leggings",
    "HoneyBoots": "Beekeeper Boots",
    "FireworkQuiver": "Firework Arrow",
}

FOLDER_README = """Pictures for the Minecraft Dungeons II Save Editor

Put a picture here named after the item, stat or hero skin it shows, then press
Reload in the editor. Any of these names work for the Mystic Helmet:

    MysticHelmet.png
    Mystic Helmet.png
    mystic_helmet.png
    SW.Item.MysticHelmet.png

Stats use their save name (Emeralds.png, SpringStone.png, EnchantmentPoints.png)
and heroes use their skin (RangerDeluxe.png).

Pictures in the "wiki" folder come from minecraft.wiki (the editor's "Get
pictures" button or `python -m dungeons2_editor pictures`). Pictures you put
directly in this folder win over those.

If an item's save name differs from the picture's name, add a line to
aliases.txt in this folder:

    CurvedGreatsword = Claymore

PNG and GIF always work. JPG, WEBP and BMP work when Pillow is installed.
"""


def normalize(name: str) -> str:
    """'SW.Item.MysticHelmet', 'Mystic Helmet' and 'mystic_helmet' all become 'mystichelmet'."""
    if name.startswith("SW."):
        name = name.rsplit(".", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _load(path: Path, size: int) -> tk.PhotoImage | None:
    """Load a picture scaled to fit a size x size square, or None if it can't be read."""
    try:
        from PIL import Image, ImageTk
    except ImportError:
        Image = ImageTk = None
    try:
        if Image is not None:
            with Image.open(path) as picture:
                picture = picture.convert("RGBA")
                picture.thumbnail((size, size), Image.LANCZOS)
                canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                canvas.paste(picture, ((size - picture.width) // 2, (size - picture.height) // 2), picture)
                try:
                    return ImageTk.PhotoImage(canvas)
                except ImportError:
                    pass  # Pillow without its Tk part: Tk reads PNG and GIF itself
        if path.suffix.lower() not in (".png", ".gif"):
            return None
        image = tk.PhotoImage(file=str(path))
        factor = max(1, math.ceil(max(image.width(), image.height()) / size))
        return image.subsample(factor, factor) if factor > 1 else image
    except (OSError, ValueError, tk.TclError):
        return None


CUT_OUT_SIDE = 160  # pictures are shrunk to about this before cutting the item out, to keep it quick


def cut_out(picture):
    """Just the item from a picture, for drawing on the editor's own tiles (a Pillow image, or None).

    minecraft.wiki's pictures are mostly screenshots of the game's item tiles: a dark square with a
    frame, a rarity arrow in the top-left corner and the power number in the bottom-right. This clears
    the dark background (flooding in from near the edges), drops the frame, the arrow, the number and
    its upgrade arrow, and crops to what's left. A picture with a transparent background is already
    just the item. None when the picture isn't a plain tile, or nothing sensible is left.
    """
    from PIL import Image

    image = picture.convert("RGBA")
    if max(image.size) > CUT_OUT_SIDE:
        image.thumbnail((CUT_OUT_SIDE, CUT_OUT_SIDE), Image.LANCZOS)
    width, height = image.size
    pixels = image.load()
    alpha = [pixels[x, y][3] for y in range(height) for x in range(width)]
    if sum(value < 20 for value in alpha) > 0.1 * len(alpha):
        box = image.getbbox()
        return _square(image.crop(box)) if box else None

    def dark(color) -> bool:
        return max(color[:3]) < 72

    inset = max(3, round(min(width, height) * 0.06))
    clear = [[False] * width for _ in range(height)]
    queue: deque = deque()
    dark_seeds = total_seeds = 0
    # Seed from a few rings just inside the edge: the frame is a few pixels wide, sometimes white.
    for ring in (inset, inset + max(2, round(width * 0.03)), inset + max(4, round(width * 0.06))):
        for x, y in _ring(ring, width, height):
            total_seeds += 1
            if dark(pixels[x, y]):
                dark_seeds += 1
                if not clear[y][x]:
                    clear[y][x] = True
                    queue.append((x, y))
    if dark_seeds < 0.5 * total_seeds:
        return None  # not a dark game tile
    while queue:
        x, y = queue.popleft()
        here = pixels[x, y]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if inset <= nx < width - inset and inset <= ny < height - inset and not clear[ny][nx]:
                there = pixels[nx, ny]
                # The tile is dark with a soft glow, so follow small colour steps through dim pixels.
                if max(there[:3]) < 90 and sum(abs(a - b) for a, b in zip(here[:3], there[:3])) < 40:
                    clear[ny][nx] = True
                    queue.append((nx, ny))

    kept = []
    seen = [[False] * width for _ in range(height)]
    for y in range(inset, height - inset):
        for x in range(inset, width - inset):
            if clear[y][x] or seen[y][x]:
                continue
            seen[y][x] = True
            part = [(x, y)]
            queue = deque(part)
            while queue:
                cx, cy = queue.popleft()
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if inset <= nx < width - inset and inset <= ny < height - inset and not clear[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            part.append((nx, ny))
                            queue.append((nx, ny))
            if not _is_tile_mark(part, pixels, width, height):
                kept.append(part)
    if sum(len(part) for part in kept) < 0.02 * width * height:
        return None
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    out = result.load()
    for part in kept:
        for x, y in part:
            out[x, y] = pixels[x, y]
    return _square(result.crop(result.getbbox()))


def _ring(inset: int, width: int, height: int):
    for x in range(inset, width - inset):
        yield x, inset
        yield x, height - 1 - inset
    for y in range(inset, height - inset):
        yield inset, y
        yield width - 1 - inset, y


def _is_tile_mark(part: list, pixels, width: int, height: int) -> bool:
    """Whether a piece left after clearing the background belongs to the tile rather than the item: a speck,
    the frame, the rarity arrow and glow in the top-left corner, the corner brackets of Unique tiles, a
    controller button or talisman level at the top, or the power number and its upgrade arrow."""
    area = width * height
    size = len(part) / area
    if size < 0.002:
        return True
    xs = [x for x, _y in part]
    ys = [y for _x, y in part]
    x0, x1, y0, y1 = min(xs) / width, max(xs) / width, min(ys) / height, max(ys) / height
    red, green, blue = (sum(pixels[x, y][i] for x, y in part) // len(part) for i in range(3))
    grey = max(red, green, blue) - min(red, green, blue) < 40
    if x0 < 0.16 and y0 < 0.16 and x1 > 0.84 and y1 > 0.84 and len(part) < 0.3 * (x1 - x0) * (y1 - y0) * area:
        return True  # a frame all the way round
    if (x1 - x0 < 0.06 or y1 - y0 < 0.06) and (x0 < 0.1 or x1 > 0.9 or y0 < 0.1 or y1 > 0.9):
        return True  # what's left of the frame along one edge
    if x0 < 0.12 and y0 < 0.12:
        in_corner = sum(1 for x, y in part if x / width + y / height < 0.8) / len(part)
        if y1 < 0.36 or (not grey and in_corner > 0.85):
            return True  # the rarity arrow, with its glow
    near_corner = (x0 < 0.15 or x1 > 0.85) and (y0 < 0.15 or y1 > 0.85)
    if near_corner and size < 0.012 and (x1 - x0) < 0.15 and (y1 - y0) < 0.15:
        return True  # a Unique tile's corner bracket
    if y0 < 0.12 and y1 < 0.24 and size < 0.03 and (grey or x1 < 0.3):
        return True  # a controller button (Y, B, RB) or a talisman's level (I, II, III)
    if y0 > 0.6 and x0 > 0.26 and y1 > 0.8 and size < 0.08:
        # The number is white (or grey on small tiles) and its upgrade arrow green; they can touch.
        def marked(color) -> bool:
            r, g, b = color[:3]
            white = min(r, g, b) > 110 and max(r, g, b) - min(r, g, b) < 45
            upgrade = g > 120 and g - r > 45 and g - b > 25
            return white or upgrade

        return sum(marked(pixels[x, y]) for x, y in part) > 0.55 * len(part)
    return False


def _square(image):
    from PIL import Image

    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return square


class IconLibrary:
    """Finds and caches pictures in one folder. Create it after the Tk root exists."""

    def __init__(self, folder: Path = DEFAULT_ICON_ROOT):
        self.folder = Path(folder)
        self._files: dict[str, Path] | None = None
        self._aliases: dict[str, str] | None = None
        self._images: dict[tuple, tk.PhotoImage | None] = {}
        # Badges are drawn, not loaded, so reload() keeps them: widgets that show one would go blank if Tk deleted it.
        self._badges: dict[tuple, tk.PhotoImage] = {}
        self._cut_outs: dict[tuple, object] = {}  # (path, modified) -> just the item (a Pillow image), or None

    def reload(self) -> None:
        self._files = None
        self._aliases = None
        self._images.clear()

    def _index(self) -> dict[str, Path]:
        if self._files is None:
            downloaded: dict[str, Path] = {}
            own: dict[str, Path] = {}
            if self.folder.is_dir():
                for path in sorted(self.folder.rglob("*")):
                    if path.suffix.lower() in EXTENSIONS:
                        from_wiki = path.relative_to(self.folder).parts[0] == WIKI_FOLDER
                        (downloaded if from_wiki else own).setdefault(normalize(path.stem), path)
            self._files = {**downloaded, **own}
        return self._files

    def aliases(self) -> dict[str, str]:
        """Built-in renames plus the lines of aliases.txt (``SaveName = Picture name``)."""
        if self._aliases is None:
            pairs = dict(ALIASES)
            try:
                lines = (self.folder / ALIASES_FILE).read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            for line in lines:
                name, separator, picture = line.partition("=")
                if separator and not name.strip().startswith("#") and name.strip() and picture.strip():
                    pairs[name.strip()] = picture.strip()
            self._aliases = {normalize(name): picture for name, picture in pairs.items()}
        return self._aliases

    def find(self, name: str) -> Path | None:
        if not name:
            return None
        files = self._index()
        key = normalize(name)
        if key in files:
            return files[key]
        alias = self.aliases().get(key)
        return files.get(normalize(alias)) if alias else None

    def has_pictures(self) -> bool:
        """Whether the icons folder has any pictures at all."""
        return bool(self._index())

    def is_from_wiki(self, *names: str) -> bool:
        path = next((found for found in (self.find(name) for name in names if name) if found), None)
        return path is not None and path.relative_to(self.folder).parts[0] == WIKI_FOLDER

    def image_for(self, names: tuple[str, ...], size: int) -> tk.PhotoImage | None:
        """The picture for the first of ``names`` that has one (e.g. an in-game name, then an item ID)."""
        return next((image for image in (self.image(name, size) for name in names if name) if image), None)

    def image(self, name: str, size: int) -> tk.PhotoImage | None:
        """The picture for ``name`` scaled to ``size`` pixels, or None if there isn't one."""
        key = ("picture", normalize(name), size)
        if key not in self._images:
            path = self.find(name)
            self._images[key] = _load(path, size) if path else None
        return self._images[key]

    def item_art(self, names: tuple[str, ...], size: int) -> tk.PhotoImage | None:
        """Just the item, ``size`` pixels square, from the first of ``names`` with a picture: for drawing on
        Simple mode's rarity tiles. Screenshots of the game's tiles (as minecraft.wiki's pictures are) are cut
        down to the item; your own pictures that aren't are shown as they are. None if there's no usable
        picture (or Pillow, which cutting out needs, isn't installed)."""
        path = next((found for found in (self.find(name) for name in names if name) if found), None)
        if path is None:
            return None
        key = ("art", str(path), size)
        if key not in self._images:
            self._images[key] = self._make_art(path, size)
        return self._images[key]

    def _make_art(self, path: Path, size: int) -> tk.PhotoImage | None:
        from_wiki = path.relative_to(self.folder).parts[0] == WIKI_FOLDER
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return None if from_wiki else _load(path, size)
        try:
            stamp = (str(path), path.stat().st_mtime_ns)
            if stamp not in self._cut_outs:
                with Image.open(path) as picture:
                    self._cut_outs[stamp] = cut_out(picture)
            art = self._cut_outs[stamp]
        except (OSError, ValueError):
            return None
        if art is None:
            return None if from_wiki else _load(path, size)
        try:
            return ImageTk.PhotoImage(art.resize((size, size), Image.LANCZOS))
        except (ImportError, tk.TclError, ValueError):
            return None  # Pillow without its Tk part

    def rarity_badge(self, rarity: str, size: int) -> tk.PhotoImage:
        """A square in the rarity's colour, for items without a picture."""
        key = (rarity, size)
        if key not in self._badges:
            color = RARITY_COLORS.get(rarity, _FALLBACK_COLOR)
            badge = tk.PhotoImage(width=size, height=size)
            inset = max(2, size // 6)
            badge.put(_darker(color), to=(inset, inset, size - inset, size - inset))
            badge.put(color, to=(inset + 1, inset + 1, size - inset - 1, size - inset - 1))
            self._badges[key] = badge
        return self._badges[key]

    def item_image(self, tag: str, rarity: str, size: int, name: str = "") -> tk.PhotoImage:
        """The item's picture, found by its in-game name or ID, or else its rarity badge."""
        return self.image_for((name, tag), size) or self.rarity_badge(rarity, size)

    def ensure_folder(self) -> Path:
        """Create the icons folder (with a note on how to name pictures) and return it."""
        self.folder.mkdir(parents=True, exist_ok=True)
        readme = self.folder / "README.txt"
        if not readme.exists():
            readme.write_text(FOLDER_README, encoding="utf-8")
        return self.folder


def _darker(color: str) -> str:
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (red * 3 // 4, green * 3 // 4, blue * 3 // 4)
