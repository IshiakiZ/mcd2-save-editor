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
from pathlib import Path

from .paths import data_dir

DEFAULT_ICON_ROOT = data_dir() / "icons"
WIKI_FOLDER = "wiki"  # pictures downloaded from minecraft.wiki; your own pictures take priority
ALIASES_FILE = "aliases.txt"
EXTENSIONS = (".png", ".gif", ".jpg", ".jpeg", ".webp", ".bmp")
RARITY_COLORS = {"Common": "#8d8d8d", "Rare": "#2a9d8f", "Special": "#8e5cc4", "Unique": "#e07b1a"}
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
                return ImageTk.PhotoImage(canvas)
        if path.suffix.lower() not in (".png", ".gif"):
            return None
        image = tk.PhotoImage(file=str(path))
        factor = max(1, math.ceil(max(image.width(), image.height()) / size))
        return image.subsample(factor, factor) if factor > 1 else image
    except (OSError, ValueError, tk.TclError):
        return None


class IconLibrary:
    """Finds and caches pictures in one folder. Create it after the Tk root exists."""

    def __init__(self, folder: Path = DEFAULT_ICON_ROOT):
        self.folder = Path(folder)
        self._files: dict[str, Path] | None = None
        self._aliases: dict[str, str] | None = None
        self._images: dict[tuple, tk.PhotoImage | None] = {}
        # Badges are drawn, not loaded, so reload() keeps them: widgets that show one would go blank if Tk deleted it.
        self._badges: dict[tuple, tk.PhotoImage] = {}

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

    def is_from_wiki(self, name: str) -> bool:
        path = self.find(name)
        return path is not None and path.relative_to(self.folder).parts[0] == WIKI_FOLDER

    def image(self, name: str, size: int) -> tk.PhotoImage | None:
        """The picture for ``name`` scaled to ``size`` pixels, or None if there isn't one."""
        key = ("picture", normalize(name), size)
        if key not in self._images:
            path = self.find(name)
            self._images[key] = _load(path, size) if path else None
        return self._images[key]

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

    def item_image(self, tag: str, rarity: str, size: int) -> tk.PhotoImage:
        return self.image(tag, size) or self.rarity_badge(rarity, size)

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
