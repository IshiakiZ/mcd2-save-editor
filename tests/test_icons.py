import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from dungeons2_editor import icons
from dungeons2_editor.icons import IconLibrary, cut_out, normalize

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None

ITEM = (200, 60, 60)


def game_tile():
    """Like minecraft.wiki's pictures: the game's dark item tile, with a frame, the rarity arrow in the
    top-left corner and the power number (here 11) in the bottom-right, around a square red item."""
    image = Image.new("RGB", (120, 120), (22, 22, 22))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 119, 119), outline=(70, 140, 80), width=3)
    draw.polygon([(10, 10), (26, 10), (10, 26)], fill=(80, 160, 80))
    draw.rectangle((35, 30, 80, 75), fill=ITEM, outline=(5, 5, 5), width=2)
    for x in (78, 94):
        draw.rectangle((x, 88, x + 9, 110), fill=(240, 240, 240), outline=(0, 0, 0), width=2)
    return image


def _tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    root.withdraw()
    return root


class NameTests(unittest.TestCase):
    def test_names_match_however_they_are_written(self):
        for name in ("SW.Item.MysticHelmet", "Mystic Helmet", "mystic_helmet", "MysticHelmet", "SW.Item.Armor.MysticHelmet"):
            self.assertEqual(normalize(name), "mystichelmet")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "icons"
        (self.folder / "wiki").mkdir(parents=True)
        for name in ("wiki/Mystic Circlet.png", "wiki/Sword.png", "wiki/Claymore.png", "Sword.png", "notes.txt"):
            (self.folder / name).write_bytes(b"x")
        self.library = IconLibrary(self.folder)

    def test_known_renames_find_the_wiki_picture(self):
        self.assertEqual(self.library.find("SW.Item.MysticHelmet"), self.folder / "wiki" / "Mystic Circlet.png")
        self.assertTrue(self.library.is_from_wiki("SW.Item.MysticHelmet"))

    def test_your_own_pictures_win_over_wiki_ones(self):
        self.assertEqual(self.library.find("SW.Item.Sword"), self.folder / "Sword.png")
        self.assertFalse(self.library.is_from_wiki("SW.Item.Sword"))

    def test_aliases_file_adds_renames(self):
        self.assertIsNone(self.library.find("SW.Item.CurvedGreatsword"))
        (self.folder / icons.ALIASES_FILE).write_text("# comment\nCurvedGreatsword = Claymore\nbroken line\n", encoding="utf-8")
        self.library.reload()
        self.assertEqual(self.library.find("SW.Item.CurvedGreatsword"), self.folder / "wiki" / "Claymore.png")

    def test_missing_folder_and_names(self):
        empty = IconLibrary(Path(self.temp.name) / "nowhere")
        self.assertIsNone(empty.find("SW.Item.Sword"))
        self.assertIsNone(self.library.find(""))
        self.assertIsNone(self.library.find("notes"))

    def test_ensure_folder_writes_instructions(self):
        folder = IconLibrary(Path(self.temp.name) / "fresh").ensure_folder()
        self.assertIn("MysticHelmet.png", (folder / "README.txt").read_text(encoding="utf-8"))


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.root = _tk_root()
        if self.root is None:
            self.skipTest("needs a display")
        self.addCleanup(gc.collect)  # frees Tk objects on the main thread, after the window is destroyed
        self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        picture = tk.PhotoImage(width=64, height=48)
        picture.put("#ff0000", to=(0, 0, 64, 48))
        picture.write(str(self.folder / "Longbow.png"), format="png")
        (self.folder / "Broken.png").write_bytes(b"not a picture")
        self.library = IconLibrary(self.folder)

    def test_pictures_are_scaled_to_fit(self):
        image = self.library.image("SW.Item.Longbow", 20)
        self.assertIsNotNone(image)
        self.assertLessEqual(max(image.width(), image.height()), 20)
        self.assertIs(self.library.image("SW.Item.Longbow", 20), image)  # cached

    def test_unreadable_or_missing_pictures_fall_back_to_a_rarity_badge(self):
        self.assertIsNone(self.library.image("Broken", 20))
        badge = self.library.item_image("SW.Item.Nothing", "Unique", 20)
        self.assertEqual((badge.width(), badge.height()), (20, 20))
        self.assertIs(self.library.item_image("SW.Item.Other", "Unique", 20), badge)



@unittest.skipIf(Image is None, "needs Pillow")
class CutOutTests(unittest.TestCase):
    def test_keeps_only_the_item_from_a_game_tile(self):
        art = cut_out(game_tile())
        self.assertEqual(art.size, (46, 46))  # the item, keeping its dark outline
        colours = {art.getpixel((x, y)) for x in range(art.width) for y in range(art.height)}
        self.assertEqual(colours, {ITEM + (255,), (5, 5, 5, 255)})  # no frame, arrow or number left

    def test_a_picture_with_a_transparent_background_is_already_just_the_item(self):
        picture = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
        ImageDraw.Draw(picture).rectangle((20, 10, 59, 69), fill=(10, 200, 30, 255))
        art = cut_out(picture)
        self.assertEqual(art.size, (60, 60))  # squared up around the item
        self.assertEqual(art.getpixel((30, 30)), (10, 200, 30, 255))
        self.assertEqual(art.getpixel((0, 0))[3], 0)

    def test_other_pictures_are_left_alone(self):
        self.assertIsNone(cut_out(Image.new("RGB", (100, 100), (200, 200, 200))))  # not a dark game tile
        self.assertIsNone(cut_out(Image.new("RGB", (100, 100), (22, 22, 22))))  # nothing on it


@unittest.skipIf(Image is None, "needs Pillow")
class ItemArtTests(unittest.TestCase):
    def setUp(self):
        self.root = _tk_root()
        if self.root is None:
            self.skipTest("needs a display")
        self.addCleanup(gc.collect)
        self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / "wiki").mkdir()
        game_tile().save(self.folder / "wiki" / "Mystic Circlet.png")
        Image.new("RGB", (60, 60), (200, 200, 200)).save(self.folder / "wiki" / "Sword.png")
        Image.new("RGB", (60, 60), (200, 200, 200)).save(self.folder / "Bow.png")
        self.library = IconLibrary(self.folder)

    def test_wiki_tiles_are_cut_down_to_the_item(self):
        art = self.library.item_art(("Mystic Circlet", "SW.Item.MysticHelmet"), 40)
        self.assertEqual((art.width(), art.height()), (40, 40))
        self.assertIs(self.library.item_art(("Mystic Circlet",), 40), art)  # cached

    def test_pictures_pasted_from_the_game_are_kept_as_yours(self):
        kept = self.library.save_captured(game_tile(), "Mystic Boots")
        self.assertEqual(kept, self.folder / "captured" / "Mystic Boots.png")
        with Image.open(kept) as picture:
            self.assertEqual(picture.size, (46, 46))
        self.assertEqual(self.library.find("SW.Item.MysticBoots"), kept)
        self.assertFalse(self.library.is_from_wiki("Mystic Boots"))
        odd = self.library.save_captured(Image.new("RGB", (400, 300), (200, 200, 200)), 'What: "is" this?')
        with Image.open(odd) as picture:
            self.assertEqual((odd.name, max(picture.size)), ("What is this.png", 256))  # not a game tile: kept, smaller

    def test_pictures_that_cant_be_cut_out(self):
        self.assertIsNone(self.library.item_art(("Sword",), 40))  # a wiki picture that isn't a game tile
        own = self.library.item_art(("Bow",), 40)  # your own picture is shown as it is
        self.assertLessEqual(max(own.width(), own.height()), 40)
        self.assertIsNone(self.library.item_art(("Nothing",), 40))


if __name__ == "__main__":
    unittest.main()
