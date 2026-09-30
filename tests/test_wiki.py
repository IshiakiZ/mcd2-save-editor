import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import wiki

PNG = wiki.PNG_MAGIC + b"rest of a png"


def image(name, size=100):
    return {"name": name, "url": f"https://minecraft.wiki/images/{name}", "size": size}


class ListingTests(unittest.TestCase):
    def test_one_picture_per_item_preferring_gear_icons(self):
        pictures = wiki.pictures_from_listing(
            [
                image("MCD2_Mystic_Circlet_gear_icon.png"),
                image("MCD2_Longbow_inventory_render.png"),
                image("MCD2_Longbow_gear_icon.png"),
                image("MCD2_Firework_Arrow_inventory_render.png"),
                image("MCD2_Hivemind_Hardhat_gear_icon.png"),
                image("MCD2_Hivemind_hardhat_gear_icon.png"),
                image("MCD2_Bee_screenshot.png"),
                image("Dungeons2Sprite_bow.png"),
            ]
        )
        self.assertEqual([p.name for p in pictures], ["Firework Arrow", "Hivemind Hardhat", "Longbow", "Mystic Circlet"])
        self.assertTrue(next(p for p in pictures if p.name == "Longbow").url.endswith("gear_icon.png"))

    def test_listing_follows_continuation(self):
        pages = [
            {"query": {"allimages": [image("MCD2_Sword_gear_icon.png")]}, "continue": {"aicontinue": "next"}},
            {"query": {"allimages": [image("MCD2_Bow_gear_icon.png")]}},
        ]
        with mock.patch.object(wiki, "_get", side_effect=[json.dumps(page).encode() for page in pages]) as get:
            names = [p.name for p in wiki.list_pictures()]
        self.assertEqual(names, ["Bow", "Sword"])
        self.assertIn("aicontinue=next", get.call_args_list[1].args[0])

    def test_only_the_wiki_is_contacted(self):
        for url in ("http://minecraft.wiki/x.png", "https://example.com/x.png", "https://minecraft.wiki.evil.com/x.png", "file:///C:/x"):
            with self.assertRaises(ValueError):
                wiki._get(url)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "wiki"

    def test_downloads_new_pictures_and_skips_ones_already_there(self):
        pictures = [wiki.WikiPicture("Sword", "https://minecraft.wiki/images/a.png", len(PNG)), wiki.WikiPicture("Bow", "https://minecraft.wiki/images/b.png", len(PNG))]
        self.folder.mkdir()
        (self.folder / "Bow.png").write_bytes(PNG)
        steps = []
        with mock.patch.object(wiki, "_get", return_value=PNG) as get:
            result = wiki.download_pictures(pictures, self.folder, lambda *step: steps.append(step), pause=0)
        self.assertEqual(result, (1, 1))
        self.assertEqual(get.call_count, 1)
        self.assertEqual((self.folder / "Sword.png").read_bytes(), PNG)
        self.assertEqual(steps[-1], (2, 2, "Bow"))

    def test_rejects_things_that_are_not_pngs(self):
        pictures = [wiki.WikiPicture("Sword", "https://minecraft.wiki/images/a.png", 10)]
        with mock.patch.object(wiki, "_get", return_value=b"<html>error</html>"):
            with self.assertRaises(ValueError):
                wiki.download_pictures(pictures, self.folder, pause=0)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_file_names_are_safe(self):
        self.assertEqual(wiki.file_name(wiki.WikiPicture("Fighter's Flute", "", 0)), "Fighter's Flute.png")
        self.assertEqual(wiki.file_name(wiki.WikiPicture('A/B:C"?', "", 0)), "ABC.png")


if __name__ == "__main__":
    unittest.main()
