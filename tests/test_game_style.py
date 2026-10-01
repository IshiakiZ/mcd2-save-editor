import gc
import tkinter as tk
import unittest
from tkinter import ttk

from dungeons2_editor import game_art, game_style
from dungeons2_editor.game_art import ICONS, RARITY_TILE, Art, mix, tile_fill


def _tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    root.withdraw()
    return root


class PatternTests(unittest.TestCase):
    def test_icons_are_twelve_by_twelve(self):
        for name, rows in ICONS.items():
            self.assertEqual((len(rows), {len(row) for row in rows}), (12, {12}), name)
            self.assertTrue(set("".join(rows)) <= set("#+-o."), name)

    def test_every_kind_and_piece_has_an_icon(self):
        for kind in ("Melee", "Ranged", "Armor", "Artifact", "Talisman", "Helmet", "Chestplate", "Leggings", "Boots"):
            self.assertIn(game_art.KIND_ICONS[kind], ICONS)
        self.assertEqual(game_art.icon_for("Armor", "Boots"), "boots")
        self.assertEqual(game_art.icon_for("Armor", None), "chestplate")

    def test_colours(self):
        self.assertEqual(mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(mix("#123456", "#ffffff", 0), "#123456")
        self.assertEqual(tile_fill("Unique", "Melee"), RARITY_TILE["Unique"])
        self.assertEqual(tile_fill("Unique", "Talisman"), game_art.TALISMAN_TILE)  # the game shows talismans dark
        self.assertEqual(tile_fill("Mythic", "Melee"), game_art.UNKNOWN_TILE)


class DrawingTests(unittest.TestCase):
    def setUp(self):
        self.root = _tk_root()
        if self.root is None:
            self.skipTest("needs a display")
        self.addCleanup(gc.collect)
        self.addCleanup(self.root.destroy)

    def test_pictures_are_made_once_at_the_right_size(self):
        art = Art(1.5)
        icon = art.icon("sword", "#52d2ff", 2)
        self.assertEqual((icon.width(), icon.height()), (36, 36))  # 12 cells of 3 pixels at 150%
        self.assertIs(art.icon("sword", "#52d2ff", 2), icon)
        tile = art.tile(RARITY_TILE["Rare"], 64)
        self.assertEqual((tile.width(), tile.height()), (64, 64))
        self.assertEqual(art.px(10), 15)
        self.assertEqual(Art(0.5).px(10), 10)  # never smaller than at 96 DPI

    def test_tiles_glow_in_the_middle(self):
        tile = Art().tile(RARITY_TILE["Unique"], 64)
        middle, edge = tile.get(32, 32), tile.get(6, 32)
        self.assertGreater(sum(middle), sum(edge))
        self.assertLess(sum(tile.get(0, 0)), 80)  # a dark outline

    def test_theme_switches_with_the_mode(self):
        style = ttk.Style(self.root)
        light = style.theme_use()
        game_style.install(style, game_style.GameFonts(self.root), 24, 30)
        game_style.install(style, game_style.GameFonts(self.root), 24, 30)  # only once
        game_style.use(self.root, simple=True, light_theme=light)
        self.assertTrue(game_style.is_active(self.root))
        self.assertEqual(str(tk.Text(self.root).cget("background")), game_style.FIELD)  # plain Tk widgets follow too
        self.assertEqual(style.lookup("Card.TFrame", "background"), game_style.CARD)
        game_style.use(self.root, simple=False, light_theme=light)
        self.assertEqual(style.theme_use(), light)
        self.assertNotEqual(str(tk.Text(self.root).cget("background")), game_style.FIELD)


if __name__ == "__main__":
    unittest.main()
