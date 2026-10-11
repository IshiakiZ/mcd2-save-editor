"""The editor's picture pack on batch-ly.com (picture_pack.py) and the tool that makes it."""

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from dungeons2_editor import edition, picture_pack, wiki
from dungeons2_editor.icons import PACK_FOLDER, WIKI_FOLDER, IconLibrary

PNG = picture_pack.PNG_MAGIC + b"a picture"
TOOL = Path(__file__).resolve().parent.parent / "tools" / "make_picture_pack.py"


def entry(name="Mystic Circlet", data=PNG, **changes):
    return {"name": name, "file": f"{name}.png", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), **changes}


def index(*entries):
    return {"version": 1, "pictures": list(entries)}


class IndexTests(unittest.TestCase):
    def test_a_list_gives_one_picture_per_item(self):
        pictures = picture_pack.pictures_from_index(index(entry("Sword"), entry("Mystic Circlet"), entry("mystic  circlet", file="other.png")))
        self.assertEqual([(picture.name, picture.file, picture.size) for picture in pictures], [("Mystic Circlet", "Mystic Circlet.png", len(PNG)), ("Sword", "Sword.png", len(PNG))])
        self.assertEqual(picture_pack.file_name(pictures[0]), "Mystic Circlet.png")
        self.assertEqual(picture_pack.pictures_from_index(index()), [])

    def test_a_list_the_editor_cant_trust_isnt_used(self):
        bad = [
            None, [], {"pictures": []}, {"version": 2, "pictures": []}, {"version": 1, "pictures": "all of them"},
            index("Sword.png"),
            index(entry(file="../Mystic Circlet.png")), index(entry(file="pictures/Mystic Circlet.png")), index(entry(file="C:\\\\x.png")),
            index(entry(file=".hidden.png")), index(entry(file="Mystic Circlet.exe")), index(entry(file="Mystic Circlet.png.exe")),
            index(entry(name="")), index(entry(name=7)),
            index(entry(size=0)), index(entry(size=picture_pack.MAX_PICTURE_BYTES + 1)), index(entry(size=True)), index(entry(size="12")),
            index(entry(sha256="abc")), index(entry(sha256="G" * 64)), index(entry(sha256=None)),
            index(*[entry(f"Item {number}") for number in range(picture_pack.MAX_PICTURES + 1)]),
        ]
        for data in bad:
            with self.subTest(str(data)[:70]), self.assertRaises(ValueError):
                picture_pack.pictures_from_index(data)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "icons" / PACK_FOLDER
        self.files = {"Mystic Circlet.png": PNG, "The Burning Blade.png": PNG + b" of a blade"}
        self.asked: list[str] = []

    def serve(self, url, most, timeout=30):
        self.asked.append(url)
        if url == picture_pack.PACK_URL + picture_pack.INDEX_FILE:
            return json.dumps(index(*[entry(name[:-4], data) for name, data in self.files.items()])).encode()
        name = url[len(picture_pack.PACK_URL):].replace("%20", " ")
        return self.files[name]

    def test_pictures_are_saved_and_checked_against_the_list(self):
        steps = []
        with mock.patch.object(picture_pack, "_get", self.serve):
            pictures = picture_pack.list_pictures()
            self.assertEqual(picture_pack.download_pictures(pictures, self.folder, lambda *step: steps.append(step), pause=0), (2, 0))
            self.assertEqual({path.name: path.read_bytes() for path in self.folder.iterdir()}, self.files)
            self.assertEqual(steps, [(1, 2, "Mystic Circlet"), (2, 2, "The Burning Blade")])
            self.assertIn(picture_pack.PACK_URL + "The%20Burning%20Blade.png", self.asked)
            # A second run downloads nothing, and a picture that was changed on the PC is fetched again.
            self.asked.clear()
            self.assertEqual(picture_pack.download_pictures(pictures, self.folder, pause=0), (0, 2))
            self.assertEqual(self.asked, [])
            (self.folder / "Mystic Circlet.png").write_bytes(PNG[:-1] + b"X")
            self.assertEqual(picture_pack.download_pictures(pictures, self.folder, pause=0), (1, 1))
            self.assertEqual((self.folder / "Mystic Circlet.png").read_bytes(), PNG)

    def test_what_a_folder_hasnt_got_yet_is_what_there_is_to_download(self):
        pictures = picture_pack.pictures_from_index(index(*(entry(name[:-4], data) for name, data in self.files.items())))
        self.assertEqual([picture.name for picture in picture_pack.missing(pictures, self.folder)], ["Mystic Circlet", "The Burning Blade"])  # no folder yet
        self.folder.mkdir(parents=True)
        (self.folder / "Mystic Circlet.png").write_bytes(PNG)
        (self.folder / "The Burning Blade.png").write_bytes(PNG)  # an older picture of it: another size
        self.assertEqual([picture.name for picture in picture_pack.missing(pictures, self.folder)], ["The Burning Blade"])
        (self.folder / "The Burning Blade.png").write_bytes(self.files["The Burning Blade.png"])
        self.assertEqual(picture_pack.missing(pictures, self.folder), [])

    def test_a_picture_that_isnt_the_listed_one_is_not_kept(self):
        with mock.patch.object(picture_pack, "_get", self.serve):
            pictures = picture_pack.list_pictures()
            self.files["Mystic Circlet.png"] = PNG[:-1] + b"!"  # the same size, another picture
            with self.assertRaisesRegex(ValueError, "isn't the one its list describes"):
                picture_pack.download_pictures(pictures, self.folder, pause=0)
            self.assertEqual(list(self.folder.iterdir()), [])
        # Something that isn't a PNG, even with the list on its side.
        program = b"MZ this is a program"
        self.files = {"Mystic Circlet.png": program}
        with mock.patch.object(picture_pack, "_get", self.serve):
            with self.assertRaisesRegex(ValueError, "is not a PNG image"):
                picture_pack.download_pictures(picture_pack.list_pictures(), self.folder, pause=0)
            self.assertEqual(list(self.folder.iterdir()), [])

    def test_only_the_packs_own_site_is_asked_and_only_over_https(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("it opened a connection")):
            for url in ("http://batch-ly.com/mcd2/pictures/index.json", "https://example.com/index.json", "https://batch-ly.com.example.com/x", "file:///C:/x.png"):
                with self.subTest(url), self.assertRaisesRegex(ValueError, "refusing to download"):
                    picture_pack._get(url, 100)
            with mock.patch.object(edition, "ONLINE", False), self.assertRaises(edition.OfflineEdition):
                picture_pack.list_pictures()

    def test_no_pack_on_the_site_is_told_apart_from_other_trouble(self):
        missing = urllib.error.HTTPError(picture_pack.PACK_URL, 404, "Not Found", None, None)
        broken = urllib.error.HTTPError(picture_pack.PACK_URL, 500, "Server Error", None, None)
        with mock.patch("urllib.request.urlopen", side_effect=missing), self.assertRaises(picture_pack.NoPack):
            picture_pack.list_pictures()
        with mock.patch("urllib.request.urlopen", side_effect=broken), self.assertRaises(urllib.error.HTTPError) as raised:
            picture_pack.list_pictures()
        self.assertNotIsInstance(raised.exception, picture_pack.NoPack)
        answer = mock.MagicMock()
        answer.__enter__.return_value.read.return_value = b"x" * 101
        with mock.patch("urllib.request.urlopen", return_value=answer), self.assertRaisesRegex(ValueError, "bigger than"):
            picture_pack._get(picture_pack.PACK_URL + "Sword.png", 100)


class SourceTests(unittest.TestCase):
    def test_the_pack_when_there_is_one_else_the_wiki(self):
        packed = [picture_pack.PackPicture("Sword", "Sword.png", 9, "0" * 64)]
        from_wiki = [wiki.WikiPicture("Sword", "https://minecraft.wiki/images/MCD2_Sword_gear_icon.png", 7)]
        with mock.patch.object(wiki, "list_pictures", return_value=from_wiki):
            with mock.patch.object(picture_pack, "list_pictures", return_value=packed):
                source = picture_pack.best_source()
                self.assertEqual((source.site, source.folder, source.pictures, source.file_name(packed[0])), ("batch-ly.com", PACK_FOLDER, packed, "Sword.png"))
                self.assertIs(source.download, picture_pack.download_pictures)
            # No pack yet, the site out of reach, or a list the editor can't use: the wiki's pictures, as before.
            for trouble in (picture_pack.NoPack("none yet"), urllib.error.URLError("no route"), TimeoutError(), ValueError("a list it can't read")):
                with self.subTest(repr(trouble)), mock.patch.object(picture_pack, "list_pictures", side_effect=trouble):
                    source = picture_pack.best_source()
                    self.assertEqual((source.site, source.folder, source.pictures), ("minecraft.wiki", WIKI_FOLDER, from_wiki))
                    self.assertIs(source.download, wiki.download_pictures)
            # A pack with nothing in it yet is no better than none.
            with mock.patch.object(picture_pack, "list_pictures", return_value=[]):
                self.assertEqual(picture_pack.best_source().site, "minecraft.wiki")
        # The edition that never goes online asks neither.
        with mock.patch.object(edition, "ONLINE", False), mock.patch("urllib.request.urlopen", side_effect=AssertionError("it opened a connection")):
            with self.assertRaises(edition.OfflineEdition):
                picture_pack.best_source()

    def test_your_own_picture_comes_first_then_the_packs_then_the_wikis(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for where in (WIKI_FOLDER, PACK_FOLDER, ""):
                (folder / where).mkdir(exist_ok=True)
                (folder / where / "Sword.png").write_bytes(PNG)
            (folder / WIKI_FOLDER / "Bow.png").write_bytes(PNG)
            library = IconLibrary(folder)
            self.assertEqual((library.find("Sword"), library.downloaded_from("Sword")), (folder / "Sword.png", ""))
            (folder / "Sword.png").unlink()
            library.reload()
            self.assertEqual(library.find("Sword"), folder / PACK_FOLDER / "Sword.png")
            self.assertFalse(library.is_from_wiki("Sword"))
            self.assertEqual((library.downloaded_from("Sword"), library.downloaded_from("Bow"), library.downloaded_from("Axe")), (PACK_FOLDER, WIKI_FOLDER, ""))
            (folder / PACK_FOLDER / "Sword.png").unlink()
            library.reload()
            self.assertEqual(library.find("Sword"), folder / WIKI_FOLDER / "Sword.png")
            self.assertTrue(library.is_from_wiki("Sword") and library.is_from_wiki("Bow"))


def _pillow() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(_pillow(), "needs Pillow")
class PackToolTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("make_picture_pack", TOOL)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source, self.pack = Path(self.temp.name) / "pictures", Path(self.temp.name) / "pack"
        (self.source / "armor").mkdir(parents=True)

    def picture(self, path: Path, size=(40, 30), kind="PNG"):
        from PIL import Image

        Image.new("RGBA" if kind != "JPEG" else "RGB", size, (200, 80, 40, 255)[: 4 if kind != "JPEG" else 3]).save(path, format=kind)

    def test_a_folder_of_pictures_becomes_a_pack_the_editor_can_download(self):
        from PIL import Image

        self.picture(self.source / "sword.png")
        self.picture(self.source / "armor" / "Mystic  Circlet.webp", kind="WEBP")
        self.picture(self.source / "The Burning Blade.jpg", size=(1024, 512), kind="JPEG")
        self.picture(self.source / "screenshot of my desk.png")
        self.picture(self.source / "Emeralds.png")  # a stat has a picture too, under its save name
        (self.source / "notes.txt").write_text("not a picture", encoding="utf-8")
        made, without, strays = self.tool.make(self.source, self.pack)
        self.assertEqual((made, strays), (["Emeralds", "Mystic Circlet", "Sword", "The Burning Blade"], ["screenshot of my desk.png"]))
        self.assertIn("Bow", without)
        self.assertNotIn("Sword", without)
        self.assertEqual(sorted(path.name for path in self.pack.iterdir()), ["Emeralds.png", "Mystic Circlet.png", "Sword.png", "The Burning Blade.png", "index.json"])
        with Image.open(self.pack / "The Burning Blade.png") as blade:
            self.assertEqual((blade.format, blade.size, blade.mode), ("PNG", (256, 128), "RGBA"))  # shrunk, as a PNG
        # The editor reads the list and gets exactly these files.
        listed = json.loads((self.pack / "index.json").read_text(encoding="utf-8"))
        pictures = picture_pack.pictures_from_index(listed)
        self.assertEqual([picture.name for picture in pictures], made)

        def serve(url, most, timeout=30):
            return (self.pack / url[len(picture_pack.PACK_URL):].replace("%20", " ")).read_bytes()

        target = Path(self.temp.name) / "icons" / PACK_FOLDER
        with mock.patch.object(picture_pack, "_get", serve):
            self.assertEqual(picture_pack.download_pictures(picture_pack.list_pictures(), target, pause=0), (4, 0))
        self.assertEqual({path.name: path.read_bytes() for path in target.iterdir()}, {path.name: path.read_bytes() for path in self.pack.glob("*.png")})
        self.assertEqual(IconLibrary(target.parent).find("The Burning Blade"), target / "The Burning Blade.png")

    def test_it_says_how_to_use_it(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertEqual(self.tool.main([]), 2)
            self.assertEqual(self.tool.main([str(self.source / "nowhere"), str(self.pack)]), 2)
        self.assertIn("python tools/make_picture_pack.py <pictures> <pack>", out.getvalue())
        self.assertIn("isn't a folder", out.getvalue())


if __name__ == "__main__":
    unittest.main()
