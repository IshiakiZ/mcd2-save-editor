import re
import tempfile
import unittest
from pathlib import Path

from dungeons2_editor import __version__, whats_new

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
MOST_NOTES = 10  # changes listed for one version in the notes that ship
LONGEST_NOTE = 200  # letters in one of them, as the window shows it
BIGGEST_PICTURE = 400_000  # bytes of a picture in them: it rides in every download
WIDEST_PICTURE = 1000  # pixels: more than the window ever shows across

NOTES = """## What's new in 2.1.0

- **A second look.** With a [link](https://example.com/a_(b)) and `code`,
  going on to a second line.
  - A point under it,
    which goes on too.
- Another change.

A paragraph that runs
over two lines.

## What's new in 2.0.1: important fix, please update

- A fix.

## What's new in 2.0.0

- The first.

## Download

Download **the zip** below.

- Not a change.
"""


class WhatsNewTests(unittest.TestCase):
    def test_reads_each_versions_notes(self):
        versions = whats_new.parse(NOTES)
        self.assertEqual([version.version for version in versions], ["2.1.0", "2.0.1", "2.0.0"])  # how to download isn't a version's notes
        newest, fix, first = versions
        self.assertEqual((newest.title, fix.title), ("What's new in 2.1.0", "What's new in 2.0.1: important fix, please update"))
        self.assertEqual(newest.notes, (
            whats_new.Note("**A second look.** With a [link](https://example.com/a_(b)) and `code`, going on to a second line."),
            whats_new.Note("A point under it, which goes on too.", depth=1),
            whats_new.Note("Another change."),
            whats_new.Note("A paragraph that runs over two lines.", bullet=False),
        ))
        self.assertEqual((fix.notes, first.notes), ((whats_new.Note("A fix."),), (whats_new.Note("The first."),)))
        self.assertEqual(whats_new.parse("Nothing here.\n"), [])

    def test_a_picture_under_a_change_is_read_by_its_files_name(self):
        # The address is for a release's page. The window shows the file of that name that came with the editor,
        # so nothing of the address but the name is kept, and a name that isn't a picture's is no picture.
        notes = whats_new.parse(
            "## What's new in 3.0.0\n\n- **Pictures.** A change.\n\n  ![What it shows](https://example.com/any/where/3.0.0-pictures.png)\n"
            "- Another.\n  ![A program](https://example.com/3.0.0-setup.exe)\n  ![Up a folder](../../3.0.0-other.png)\nA paragraph.\n"
        )[0].notes
        self.assertEqual(notes, (
            whats_new.Note("**Pictures.** A change."),
            whats_new.Note("What it shows", False, 0, "3.0.0-pictures.png"),
            whats_new.Note("Another."),
            whats_new.Note("Up a folder", False, 0, "3.0.0-other.png"),
            whats_new.Note("A paragraph.", bullet=False),
        ))
        self.assertEqual(
            whats_new.picture_address("3.0.0", "3.0.0-pictures.png"),
            "https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v3.0.0/dungeons2_editor/data/whats-new/3.0.0-pictures.png",
        )

    def test_the_edition_that_never_goes_online_leaves_out_what_only_the_other_one_does(self):
        # Such a change ends with a mark that a release's page doesn't show. The window doesn't show the mark
        # either, and in the edition that never goes online it shows neither the change nor its picture.
        notes = (
            "## What's new in 3.1.0\n\n- **Fetched.** It downloads them. <!-- online -->\n\n  ![Them](https://example.com/3.1.0-them.png)\n- Both do this.\n\n"
            "## What's new in 3.0.0\n\n- Only this, which it\n  fetches. <!-- online -->\n"
        )
        fetched, picture, both = whats_new.parse(notes)[0].notes
        self.assertEqual((fetched, picture, both), (
            whats_new.Note("**Fetched.** It downloads them.", online=True),
            whats_new.Note("Them", False, 0, "3.1.0-them.png", online=True),
            whats_new.Note("Both do this."),
        ))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "notes.md"
            path.write_text(notes, encoding="utf-8")
            self.assertEqual([(version.version, len(version.notes)) for version in whats_new.load(path, online=True)], [("3.1.0", 3), ("3.0.0", 1)])
            offline = whats_new.load(path, online=False)
            self.assertEqual([(version.version, version.notes) for version in offline], [("3.1.0", (whats_new.Note("Both do this."),))])
        # In the notes that ship, every version has something to say in that edition too, and nothing left in it
        # speaks of getting or downloading.
        shipped = whats_new.load(online=False)
        self.assertEqual([version.version for version in shipped], [version.version for version in whats_new.load(online=True)])
        for version in shipped:
            for note in version.notes:
                self.assertFalse(note.picture and note.online, note)
                self.assertNotRegex(note.text.lower(), r"\bdownload|\bgets? (them|it) by itself|batch-ly", (version.version, note.text))

    def test_the_pictures_the_notes_show_ship_with_the_editor(self):
        # A picture is named after its version, is in the folder that ships, and is written in the notes with the
        # address a release's page finds it at: the file in the repository at that version's tag. Nothing else is
        # in the folder, so a version's pictures go when its notes do.
        text = whats_new.NOTES_FILE.read_text(encoding="utf-8")
        used = []
        for version in whats_new.load(online=True):
            for note in version.notes:
                if not note.picture:
                    continue
                used.append(note.picture)
                self.assertTrue(note.picture.startswith(version.version + "-"), note.picture)
                self.assertIn(f"![{note.text}]({whats_new.picture_address(version.version, note.picture)})", text)
                data = (whats_new.PICTURES_FOLDER / note.picture).read_bytes()
                self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) <= BIGGEST_PICTURE, (note.picture, len(data)))
                self.assertLessEqual(int.from_bytes(data[16:20], "big"), WIDEST_PICTURE, note.picture)
        self.assertEqual(text.count("!["), len(used))  # every picture written in the notes was read as one
        kept = sorted(path.name for path in whats_new.PICTURES_FOLDER.iterdir()) if whats_new.PICTURES_FOLDER.is_dir() else []
        self.assertEqual(kept, sorted(used))

    def test_bold_and_code_are_shown_and_a_link_by_its_words(self):
        self.assertEqual(
            whats_new.runs("**A second look.** With a [link](https://example.com/a_(b)) and `code`, and **`both`** at the end."),
            [("A second look.", "bold"), (" With a link and ", ""), ("code", "code"), (", and ", ""), ("both", "bold"), (" at the end.", "")],
        )
        self.assertEqual(whats_new.runs("Plain."), [("Plain.", "")])

    def test_shows_what_you_havent_seen(self):
        versions = whats_new.parse(NOTES)

        def shown(seen, current, **more):
            return [version.version for version in whats_new.unseen(versions, seen, current, **more)]

        self.assertEqual(shown(None, "2.1.0"), ["2.1.0"])  # the first time the editor opens: the version you have
        self.assertEqual(shown("2.0.0", "2.1.0"), ["2.1.0", "2.0.1"])  # after an update: everything since
        self.assertEqual(shown("2.1.0", "2.1.0"), [])
        self.assertEqual(shown("1.0.0", "2.1.0", most=2), ["2.1.0", "2.0.1"])  # skipped a lot: the newest few
        self.assertEqual(shown("0", "2.1.0"), ["2.1.0", "2.0.1", "2.0.0"])  # Menu > What's new: all the notes hold
        self.assertEqual(shown("1.0.0", "2.0.1"), ["2.0.1", "2.0.0"])  # never notes for a version newer than the one running
        self.assertEqual(shown("2.1.0", "2.0.0"), [])  # an older copy opened after a newer one
        self.assertEqual(shown("not a version", "2.1.0"), ["2.1.0"])
        self.assertEqual((whats_new.heading_for(versions[:1]), whats_new.heading_for(versions), whats_new.heading_for([])),
                         ("What's new in 2.1.0", "What's new in 2.1.0, and back to 2.0.0", "What's new"))

    def test_the_notes_that_ship_with_the_editor_begin_with_this_version(self):
        # The same file is each release's page, so a version can't go out without its notes.
        versions = whats_new.load()
        self.assertEqual(versions[0].version, __version__)
        for version in versions:
            self.assertTrue(version.notes, version.version)
            self.assertTrue(all(note.text for note in version.notes), version.version)
        self.assertEqual([version.version for version in whats_new.unseen(versions, None, __version__)], [__version__])
        orders = [whats_new._order(version.version) for version in versions]
        self.assertEqual(orders, sorted(orders, reverse=True))  # newest first, which is what picking the unseen ones counts on

    def test_the_notes_that_ship_are_short_and_the_changelog_has_the_rest(self):
        # Someone reading a release's page, or the window after an update, is looking for the main things: the
        # newest version and the two before it, a line for each change. The detail, and every earlier version,
        # is in CHANGELOG.md, under a heading for each version, newest first.
        versions = whats_new.load()
        self.assertLessEqual(len(versions), whats_new.MOST_VERSIONS)
        for version in versions:
            self.assertLessEqual(len(version.notes), MOST_NOTES, version.version)
            for note in version.notes:
                shown = "".join(piece for piece, _how in whats_new.runs(note.text))
                self.assertLessEqual(len(shown), LONGEST_NOTE, (version.version, shown))
        in_full = re.findall(r"^## (\d+(?:\.\d+)*)\b", CHANGELOG.read_text(encoding="utf-8"), flags=re.MULTILINE)
        self.assertEqual(in_full[0], __version__)
        self.assertEqual(len(set(in_full)), len(in_full))
        orders = [whats_new._order(version) for version in in_full]
        self.assertEqual(orders, sorted(orders, reverse=True))
        self.assertLessEqual({version.version for version in versions}, set(in_full))

    def test_no_notes_is_no_trouble(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(whats_new.load(Path(temp) / "missing.md"), [])


if __name__ == "__main__":
    unittest.main()
