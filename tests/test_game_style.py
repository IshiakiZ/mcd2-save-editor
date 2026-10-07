import base64
import gc
import struct
import tkinter as tk
import unittest
import zlib
from tkinter import ttk

from dungeons2_editor import game_art, game_style, glass
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


class GlassTests(unittest.TestCase):
    """The shapes Liquid Glass is made of: drawn pixel by pixel, with nothing but the standard library."""

    def test_a_shape_is_solid_in_the_middle_and_clear_past_its_corners(self):
        rows = glass.render(40, 30, glass.Shape(fill="#204060", radius=10))
        self.assertEqual((len(rows), {len(row) for row in rows}), (30, {40}))
        self.assertEqual(rows[15][20], (0x20, 0x40, 0x60, 255))
        for x, y in ((0, 0), (39, 0), (0, 29), (39, 29)):
            self.assertEqual(rows[y][x][3], 0, (x, y))  # the corners are cut off
        self.assertEqual(rows[0][20][3], 255)  # the straight edges aren't
        self.assertTrue(any(0 < rows[y][x][3] < 255 for y in range(10) for x in range(10)))  # and the curve is smooth, not stepped

    def test_glass_lets_what_is_behind_it_through(self):
        clear = glass.render(20, 20, glass.Shape(alpha=0.25, radius=4))
        self.assertEqual(clear[10][10], (255, 255, 255, 64))
        self.assertEqual(glass.render(8, 8, glass.Shape(alpha=0.0))[4][4][3], 0)

    def test_light_falls_from_above(self):
        lit = glass.render(30, 40, glass.Shape(fill="#406080", radius=6, glow=0.3, shade=0.3, zone=12, rim=0.8, edge="#000000", edge_alpha=0.5))
        top, middle, bottom = lit[4][15], lit[20][15], lit[36][15]
        self.assertGreater(sum(top[:3]), sum(middle[:3]))
        self.assertGreater(sum(middle[:3]), sum(bottom[:3]))
        self.assertEqual(middle, (0x40, 0x60, 0x80, 255))  # the middle is the plain fill, so it can be stretched
        self.assertGreater(sum(lit[0][15][:3]), sum(lit[39][15][:3]))  # a bright rim along the top, a dark edge below

    def test_a_shadow_falls_under_a_shape_that_leaves_room_for_it(self):
        rows = glass.render(30, 24, glass.Shape(fill="#ffffff", radius=6, shadow=0.5, drop=4))
        self.assertEqual(rows[10][15], (255, 255, 255, 255))
        under = rows[21][15]
        self.assertEqual(under[:3], (0, 0, 0))
        self.assertTrue(0 < under[3] < 255)
        self.assertEqual(glass.render(30, 24, glass.Shape(radius=6, drop=4))[22][15][3], 0)  # no shadow asked for: clear

    def test_a_title_strip_runs_along_the_top_of_a_panel(self):
        rows = glass.render(40, 60, glass.Shape(fill="#102030", radius=8, band=20, band_fill="#507080"))
        self.assertEqual(rows[10][20][:3], (0x50, 0x70, 0x80))
        self.assertEqual(rows[30][20][:3], (0x10, 0x20, 0x30))
        self.assertLess(sum(rows[19][20][:3]), sum(rows[10][20][:3]))  # a darker line along the bottom of the strip

    def test_a_wide_picture_is_the_same_as_one_drawn_pixel_by_pixel(self):
        # A lone shape is drawn the quick way (its ends, and one pixel for everything between them), so that a
        # picture with a big middle costs no more: that's what keeps a large panel quick for ttk to lay down.
        shape = glass.Shape(fill="#5ec85a", radius=10, glow=0.26, shade=0.3, zone=20, rim=0.65, edge_alpha=0.55, shadow=0.3, drop=3, inset=0.2)
        for width, height in ((64, 64), (23, 33), (300, 40), (5, 5), (9, 40)):
            with self.subTest(width=width, height=height):
                self.assertEqual(glass.render(width, height, shape), glass.render(width, height, (shape, (0, 0, width, height))))

    def test_parts_are_laid_one_over_the_other(self):
        track, knob = glass.Shape(fill="#ee7a2b", radius=9), glass.Shape(fill="#ffffff", radius=9)
        rows = glass.render(32, 18, (track, (0, 0, 32, 18)), (knob, (16, 2, 30, 16)))
        self.assertEqual((rows[9][6][:3], rows[9][23][:3]), ((0xEE, 0x7A, 0x2B), (255, 255, 255)))
        tick = glass.render(16, 16, glass.Stroke(((3, 8), (7, 12), (13, 4)), 2, "#101010"))
        self.assertEqual(tick[10][5][:3], (16, 16, 16))  # on the line
        self.assertEqual(tick[2][2][3], 0)  # off it

    def test_a_picture_is_a_png_tk_can_read(self):
        data = base64.b64decode(glass.picture(12, 7, glass.Shape(fill="#123456", radius=3)))
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (12, 7))
        self.assertEqual(data[24:26], b"\x08\x06")  # eight bits a channel, with alpha
        idat = data.index(b"IDAT")
        length = struct.unpack(">I", data[idat - 4:idat])[0]
        raw = zlib.decompress(data[idat + 4:idat + 4 + length])
        self.assertEqual(len(raw), 7 * (1 + 12 * 4))  # a filter byte and four bytes a pixel on every row


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

    def test_the_original_looks_tiles_glow_in_the_middle(self):
        tile = Art(rounded=False).tile(RARITY_TILE["Unique"], 64)
        middle, edge = tile.get(32, 32), tile.get(6, 32)
        self.assertGreater(sum(middle), sum(edge))
        self.assertLess(sum(tile.get(0, 0)), 80)  # a dark outline
        self.assertFalse(tile.transparency_get(0, 0))  # square: it fills its corners

    def test_liquid_glass_tiles_are_rounded_and_lit_from_above(self):
        self.assertFalse(Art().rounded)  # square unless asked: the original look
        art = Art(rounded=True)
        tile = art.tile(RARITY_TILE["Unique"], 64)
        self.assertTrue(all(tile.transparency_get(x, y) for x, y in ((0, 0), (63, 0), (0, 63), (63, 63))))
        self.assertFalse(tile.transparency_get(32, 32))
        self.assertGreater(sum(tile.get(32, 6)), sum(tile.get(32, 32)))
        self.assertGreater(sum(tile.get(32, 32)), sum(tile.get(32, 58)))
        # Each look keeps its own picture of the same tile, and the frame round a picked tile fits the glass one.
        self.assertIsNot(Art(rounded=False).tile(RARITY_TILE["Unique"], 64), tile)
        art.rounded = False
        self.assertFalse(art.tile(RARITY_TILE["Unique"], 64).transparency_get(0, 0))
        art.rounded = True
        self.assertIs(art.tile(RARITY_TILE["Unique"], 64), tile)
        ring = art.ring(64, "#ffffff")
        self.assertEqual((ring.width(), ring.height()), (70, 70))
        self.assertTrue(ring.transparency_get(35, 35) and ring.transparency_get(0, 0))  # only the outline is drawn
        self.assertFalse(ring.transparency_get(35, 0))

    def test_theme_switches_with_the_mode(self):
        style = ttk.Style(self.root)
        light = style.theme_use()
        game_style.install(style, game_style.GameFonts(self.root), 24, 30)
        game_style.install(style, game_style.GameFonts(self.root), 24, 30)  # only once
        self.assertEqual(style.theme_use(), light)  # making the themes doesn't switch to one
        game_style.use(self.root, simple=True, light_theme=light)
        self.assertTrue(game_style.is_active(self.root))
        self.assertEqual(str(tk.Text(self.root).cget("background")), game_style.FIELD)  # plain Tk widgets follow too
        self.assertEqual(style.lookup("Card.TFrame", "background"), game_style.CARD)
        game_style.use(self.root, simple=False, light_theme=light)
        self.assertEqual(style.theme_use(), light)
        self.assertNotEqual(str(tk.Text(self.root).cget("background")), game_style.FIELD)

    def test_simple_mode_comes_in_two_looks(self):
        style = ttk.Style(self.root)
        light = style.theme_use()
        game_style.install(style, game_style.GameFonts(self.root), 24, 30)
        # Only the original look is made to begin with: Liquid Glass's pictures wait until the look is asked for.
        self.assertEqual((game_style.THEME in style.theme_names(), game_style.GLASS_THEME in style.theme_names()), (True, False))
        self.assertFalse(hasattr(self.root, "_mcd2_looks"))
        self.assertEqual((game_style.DEFAULT_LOOK, list(game_style.LOOKS.items())), ("classic", [("classic", "Original"), ("glass", "Liquid Glass")]))
        self.assertEqual([game_style.look_of(value) for value in ("glass", "classic", "neon", None, 3)], ["glass", "classic", "classic", "classic", "classic"])
        game_style.use(self.root, simple=True, light_theme=light)  # the original look unless told otherwise
        self.assertEqual((style.theme_use(), game_style.is_active(self.root), game_style.is_glass(self.root)), (game_style.THEME, True, False))
        self.assertEqual(style.layout("TButton")[0][0], "Button.border")  # drawn by ttk, as it always was
        self.assertNotIn("glasscard", style.element_names())
        self.assertNotIn(game_style.GLASS_THEME, style.theme_names())  # using the original look doesn't make the other
        game_style.use(self.root, simple=True, light_theme=light, look="glass")
        self.assertEqual((style.theme_use(), game_style.is_active(self.root), game_style.is_glass(self.root)), (game_style.GLASS_THEME, True, True))
        drawn = self.root._mcd2_looks
        game_style.use(self.root, simple=True, light_theme=light)
        game_style.use(self.root, simple=True, light_theme=light, look="glass")
        self.assertIs(self.root._mcd2_looks, drawn)  # drawn once, however often the look is switched
        self.assertEqual(style.layout("TButton")[0][0], "glassbtn")  # a picture the editor drew, fitted to the button
        self.assertIn("glasscard", style.element_names())
        # Every style the screens ask for by name is in both looks, on the same surfaces.
        for look in game_style.LOOKS:
            game_style.use(self.root, simple=True, light_theme=light, look=look)
            for name, surface in (
                ("BarPanel.TFrame", None), ("WellPanel.TFrame", None), ("CardPanel.TFrame", None), ("Box.TFrame", None),
                ("Bar.TButton", game_style.BAR), ("Card.TLabel", game_style.CARD), ("Box.TLabel", game_style.CARD_BOX),
                ("Bar.TLabel", game_style.BAR), ("Caption.TLabel", game_style.BG), ("Chip.Toolbutton", game_style.BG),
            ):
                with self.subTest(look=look, style=name):
                    self.assertTrue(style.layout(name))
                    if surface is not None:
                        self.assertEqual(style.lookup(name, "background"), surface)
            for name in ("Box.TButton", "BarAccent.TButton", "CardAccent.TButton", "Card.TButton", "Unique.Rarity.Toolbutton", "Card.TSpinbox", "Stat.TEntry",
                         "Well.Vertical.TScrollbar", "Card.Vertical.TScrollbar", "Bar.TCheckbutton", "Bar.TMenubutton", "BarTab.Toolbutton"):
                with self.subTest(look=look, style=name):
                    self.assertTrue(style.layout(name))
        # In Liquid Glass what shows past a shape's corners is the surface it sits on, whatever state it's in.
        game_style.use(self.root, simple=True, light_theme=light, look="glass")
        for name, surface in (("TButton", game_style.BG), ("Card.TButton", game_style.CARD), ("Box.TButton", game_style.CARD_BOX),
                              ("BarAccent.TButton", game_style.BAR), ("Card.TSpinbox", game_style.CARD), ("Bar.TCheckbutton", game_style.BAR)):
            for state in ((), ("disabled",), ("active",), ("pressed",), ("focus",)):
                with self.subTest(style=name, state=state):
                    self.assertEqual(style.lookup(name, "background", state), surface)

    def test_the_glass_is_drawn_for_the_display(self):
        looks = game_style.Looks(self.root, game_style.GameFonts(self.root))
        names = [name for name, _pictures, _options in looks.elements]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"glassbtn", "glassaccent", "glasschip", "glassfield", "glasscard", "glasswell", "glassbarpanel", "glassswitch", "glassv.thumb"} <= set(names))
        for name, pictures, options in looks.elements:
            first = pictures[0]
            with self.subTest(name):
                self.assertGreater(first.width(), 0)
                # ttk lays the middle of a picture side by side to fill a widget, each piece blended in on its own:
                # a picture that stretches has a middle big enough that a whole panel takes a handful of pieces.
                border = options.get("border")
                if border is None:
                    continue
                left, top, right, bottom = (border,) * 4 if isinstance(border, int) else border
                stretches_across = "glassv" not in name
                if stretches_across:
                    self.assertGreaterEqual(first.width() - left - right, 60, name)
                if name in ("glasscard", "glasswell") or "glassv" in name:
                    self.assertGreaterEqual(first.height() - top - bottom, 40, name)
                # And it asks for no more room than its corners take, so a small button stays small.
                self.assertLess(options["width"], first.width() if stretches_across else first.width() + 1, name)


if __name__ == "__main__":
    unittest.main()
