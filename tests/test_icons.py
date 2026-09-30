import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from dungeons2_editor import icons
from dungeons2_editor.icons import IconLibrary, normalize


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


if __name__ == "__main__":
    unittest.main()
