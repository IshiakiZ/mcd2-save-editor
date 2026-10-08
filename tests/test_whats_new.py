import re
import tempfile
import unittest
from pathlib import Path

from dungeons2_editor import __version__, whats_new

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
MOST_NOTES = 10  # changes listed for one version in the notes that ship
LONGEST_NOTE = 200  # letters in one of them, as the window shows it

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
