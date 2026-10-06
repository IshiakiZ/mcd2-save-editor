"""Small pixel-art pictures for Simple mode: gear tiles in their rarity's colour and little icons.

Everything here is drawn by the editor (no game files), in the style of Minecraft Dungeons II's
inventory: square tiles with a bevelled frame and a glow in the rarity's colour, and blocky icons.
Pictures are made once and cached, so ask for them freely. Create an ``Art`` after the Tk root exists.
"""

from __future__ import annotations

import math
import tkinter as tk

# Tile colours, sampled from the game's inventory screen (MetaBot's beginner's guide confirms Common
# drops look grey and Rare ones green; Uniques are orange, so Special is the blue).
RARITY_TILE = {"Common": "#a8917c", "Rare": "#5ec85a", "Special": "#2394ec", "Unique": "#ec7330"}
TALISMAN_TILE = "#17191c"  # the game shows talismans on dark tiles
EMPTY_TILE = "#0b2531"
UNKNOWN_TILE = "#7d8a90"

# Patterns: "#" the colour, "+" lighter, "-" darker, "o" an outline, "." nothing. All the same size.
ICONS: dict[str, tuple[str, ...]] = {
    "sword": (
        "..........##",
        ".........#+#",
        "........#+#.",
        ".......#+#..",
        "......#+#...",
        ".....#+#....",
        ".#..#+#.....",
        "..##+#......",
        "...##.......",
        "..-.##......",
        ".-....#.....",
        "-...........",
    ),
    "bow": (
        "...##.......",
        "...-.##.....",
        "...-...#....",
        "...-....#...",
        "...-....#.#.",
        "+++++++++###",
        "...-....#.#.",
        "...-....#...",
        "...-...#....",
        "...-.##.....",
        "...##.......",
        "............",
    ),
    "helmet": (
        "............",
        "...oooooo...",
        "..o++++++o..",
        ".o+######-o.",
        ".o+######-o.",
        ".o+#oooo#-o.",
        ".o+#o..o#-o.",
        ".o+-o..o--o.",
        ".o-o....o-o.",
        "..o......o..",
        "............",
        "............",
    ),
    "chestplate": (
        ".ooo....ooo.",
        "o++#o..o#--o",
        "o+##oooo##-o",
        "o+########-o",
        ".o+######-o.",
        "..o+####-o..",
        "..o+####-o..",
        "..o+####-o..",
        "..o+####-o..",
        "..o+####-o..",
        "..o------o..",
        "...oooooo...",
    ),
    "leggings": (
        "............",
        ".oooooooooo.",
        ".o++++++++o.",
        ".o+######-o.",
        ".o+##oo##-o.",
        ".o+#o..o#-o.",
        ".o+#o..o#-o.",
        ".o+#o..o#-o.",
        ".o+#o..o#-o.",
        ".o--o..o--o.",
        ".oooo..oooo.",
        "............",
    ),
    "boots": (
        "............",
        "............",
        "..oooo..oooo",
        "..o+#o..o+#o",
        "..o+#o..o+#o",
        "..o+#o..o+#o",
        "ooo+#oooo+#o",
        "o++##oo++##o",
        "o----oo----o",
        "oooooooooooo",
        "............",
        "............",
    ),
    "artifact": (
        "....oooo....",
        "...o+##-o...",
        "..oooooooo..",
        ".o++++++++o.",
        ".o+######-o.",
        ".o+#o++o#-o.",
        ".o+#o+#o#-o.",
        ".o+#oooo#-o.",
        ".o+######-o.",
        ".o--------o.",
        "..oooooooo..",
        "............",
    ),
    "talisman": (
        "..o......o..",
        "...o....o...",
        "....o..o....",
        ".....oo.....",
        "....o++o....",
        "...o+##-o...",
        "..o+#++#-o..",
        "..o#+##+-o..",
        "...o#--#o...",
        "....o--o....",
        ".....oo.....",
        "............",
    ),
    "emerald": (
        "....oooo....",
        "...o++#-o...",
        "..o++##--o..",
        "..o+####-o..",
        "..o+####-o..",
        "..o+####-o..",
        "..o+####-o..",
        "..o+####-o..",
        "..o#####-o..",
        "...o#---o...",
        "....oooo....",
        "............",
    ),
    "enchant": (
        "..oooooooo..",
        ".o++++++++o.",
        "o+oooooooo#o",
        "o+o++++++o#o",
        "o+o+oooo+o#o",
        "o+o+o##o+o#o",
        "o+o+o#oo+o#o",
        "o+o+ooo++o#o",
        "o+o+++++oo#o",
        "o+ooooooo##o",
        ".o--------o.",
        "..oooooooo..",
    ),
    "echo": (
        ".....oo.....",
        ".....o+o....",
        "....o++#o...",
        "...o+###-o..",
        "oooo+####-oo",
        "o++++##----o",
        "oo#####--ooo",
        "..o-##--o...",
        "...o-#-o....",
        "....o-o.....",
        ".....oo.....",
        "............",
    ),
    "xp": (
        "............",
        "....oooo....",
        "...o++++o...",
        "..o++##+#o..",
        ".o++####-#o.",
        ".o+######-o.",
        ".o+######-o.",
        ".o#+####--o.",
        "..o#----#o..",
        "...o####o...",
        "....oooo....",
        "............",
    ),
    "lock": (
        "....oooo....",
        "...o----o...",
        "..o-o..o-o..",
        "..o-o..o-o..",
        ".oooooooooo.",
        ".o++++++++o.",
        ".o+##oo##-o.",
        ".o+##oo##-o.",
        ".o+###o##-o.",
        ".o+######-o.",
        ".o--------o.",
        ".oooooooooo.",
    ),
    "plus": (
        "............",
        "............",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        "..########..",
        "..########..",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        "............",
        "............",
    ),
    "menu": (
        "............",
        "............",
        ".##########.",
        ".##########.",
        "............",
        ".##########.",
        ".##########.",
        "............",
        ".##########.",
        ".##########.",
        "............",
        "............",
    ),
    "power": (
        "............",
        "....####....",
        "....####....",
        "....####....",
        "....####....",
        ".##########.",
        "..########..",
        "...######...",
        "....####....",
        ".....##.....",
        "............",
        "............",
    ),
}

# The icon for each kind of item and each armor piece.
KIND_ICONS = {
    "Melee": "sword",
    "Ranged": "bow",
    "Armor": "chestplate",
    "Helmet": "helmet",
    "Chestplate": "chestplate",
    "Leggings": "leggings",
    "Boots": "boots",
    "Artifact": "artifact",
    "Talisman": "talisman",
}


def mix(color: str, other: str, amount: float) -> str:
    """``color`` moved ``amount`` (0 to 1) of the way towards ``other``."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def icon_for(kind: str, piece: str | None = None) -> str:
    return KIND_ICONS.get(piece or "", KIND_ICONS.get(kind, "artifact"))


def tile_fill(rarity: str, kind: str = "") -> str:
    """The colour of a tile for an item of this rarity and kind."""
    if kind == "Talisman":
        return TALISMAN_TILE
    return RARITY_TILE.get(rarity, UNKNOWN_TILE)


class Art:
    """Makes and keeps the editor's own pictures. ``scale`` is the screen's size factor (1 at 96 DPI)."""

    def __init__(self, scale: float = 1.0):
        self.scale = max(1.0, scale)
        self._cache: dict[tuple, tk.PhotoImage] = {}

    def px(self, size: float) -> int:
        """A size in pixels, grown for high-DPI screens."""
        return int(round(size * self.scale))

    def icon(self, name: str, color: str, pixel: int = 2) -> tk.PhotoImage:
        """The icon ``name`` in ``color``, each pattern cell ``pixel`` screen pixels across (before scaling)."""
        pixel = max(1, int(round(pixel * self.scale)))
        key = ("icon", name, color, pixel)
        if key not in self._cache:
            pattern = ICONS[name]
            width = max(len(row) for row in pattern)
            image = tk.PhotoImage(width=width * pixel, height=len(pattern) * pixel)
            shades = {"#": color, "+": mix(color, "#ffffff", 0.4), "-": mix(color, "#000000", 0.35), "o": mix(color, "#000000", 0.75)}
            for y, row in enumerate(pattern):
                for x, cell in enumerate(row):
                    if cell in shades:
                        image.put(shades[cell], to=(x * pixel, y * pixel, (x + 1) * pixel, (y + 1) * pixel))
            self._cache[key] = image
        return self._cache[key]

    def tile(self, fill: str, size: int, empty: bool = False) -> tk.PhotoImage:
        """A square gear tile: a bevelled frame around a body that glows in ``fill`` (darker at the edges).
        An ``empty`` tile has a faint frame, for a gear slot with nothing in it."""
        key = ("tile", fill, size, empty)
        if key not in self._cache:
            self._cache[key] = self._make_tile(fill, size, empty)
        return self._cache[key]

    def _make_tile(self, fill: str, size: int, empty: bool) -> tk.PhotoImage:
        if empty:
            frame = ["#081a22", "#1f3f4b", "#1f3f4b", "#16313b", "#0a1d25"]
            center, edge = mix(fill, "#ffffff", 0.03), mix(fill, "#000000", 0.15)
        else:
            frame = ["#121110", "#7a766f", "#5c5955", "#3f3d3a", "#1b1a19"]
            center, edge = mix(fill, "#ffffff", 0.22), mix(fill, "#000000", 0.16)
        border = max(4, self.px(4))
        half = (size - 1) / 2
        reach = half * math.sqrt(2)
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                ring = min(x, y, size - 1 - x, size - 1 - y)
                if ring == 0:
                    color = frame[0]
                elif ring < border - 1:
                    # Bevel: light along the top and left, dark along the bottom and right.
                    color = frame[1] if x + y < size - 1 else frame[3]
                    if ring == border - 2:
                        color = frame[2]
                elif ring == border - 1:
                    color = frame[4]
                else:
                    distance = math.hypot(x - half, y - half) / reach
                    color = mix(center, edge, min(1.0, distance * 1.15))
                row.append(color)
            rows.append("{" + " ".join(row) + "}")
        image = tk.PhotoImage(width=size, height=size)
        image.put(" ".join(rows))
        return image

    def diamond(self, size: int, fill: str, outline: str) -> tk.PhotoImage:
        """The game's empty enchantment socket: a diamond with a plus in it."""
        key = ("diamond", size, fill, outline)
        if key not in self._cache:
            image = tk.PhotoImage(width=size, height=size)
            half = (size - 1) / 2
            arm = max(2, size // 6)
            for y in range(size):
                for x in range(size):
                    distance = abs(x - half) + abs(y - half)
                    if distance <= half:
                        color = outline if distance > half - max(1, self.px(1.5)) else fill
                        in_plus = (abs(x - half) < 1 and abs(y - half) <= arm) or (abs(y - half) < 1 and abs(x - half) <= arm)
                        image.put(outline if in_plus else color, to=(x, y))
            self._cache[key] = image
        return self._cache[key]
