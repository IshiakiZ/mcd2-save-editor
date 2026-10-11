import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from dungeons2_editor import edition, share_ids, suggest

FORM = Path(__file__).resolve().parent.parent / ".github" / "ISSUE_TEMPLATE" / suggest.ISSUE_TEMPLATE


class SuggestTests(unittest.TestCase):
    """A suggestion on its way to GitHub: its title, the line about the editor, and the form it fills in."""

    def test_the_title_is_the_first_line_cut_at_a_word(self):
        self.assertEqual(suggest.title_of("Sort by power\nso the strongest is on top"), "Suggestion: Sort by power")
        self.assertEqual(suggest.title_of("\n\n   A button for it   \n"), "Suggestion: A button for it")
        long = suggest.title_of("Let me sort my inventory by power, and also remember which sort I picked the last time the editor was open")
        self.assertEqual(long, "Suggestion: Let me sort my inventory by power, and also remember which sort I…")
        self.assertLessEqual(len(long), len("Suggestion: ") + suggest.MOST_TITLE + 1)
        self.assertEqual(suggest.title_of("  \n "), "Suggestion")

    def test_the_line_about_the_editor_says_nothing_of_the_saves_or_the_pc(self):
        with mock.patch("platform.system", return_value="Windows"):
            self.assertEqual(suggest.setup_line("9.9.9", "xbox", False, "classic"), f"Editor 9.9.9 ({edition.NAME} edition), saves from the Xbox app, Simple mode, Original look, Windows")
            self.assertEqual(suggest.setup_line("9.9.9", "steam", False, "glass"), f"Editor 9.9.9 ({edition.NAME} edition), saves from Steam, Simple mode, Liquid Glass look, Windows")
            # Advanced mode has one look; saves that are neither kind, or none open, aren't guessed at.
            self.assertEqual(suggest.setup_line("9.9.9", "folders", True, "glass"), f"Editor 9.9.9 ({edition.NAME} edition), a folder for each save, Advanced mode, Windows")
            self.assertEqual(suggest.setup_line("9.9.9", None, False, "something else"), f"Editor 9.9.9 ({edition.NAME} edition), Simple mode, Windows")
        with mock.patch("platform.system", return_value="Darwin"):
            self.assertTrue(suggest.setup_line("9.9.9").endswith("Simple mode, a Mac"))
        with mock.patch("platform.system", return_value="Plan 9"):
            self.assertTrue(suggest.setup_line("9.9.9").endswith("Simple mode"))  # a system it doesn't know goes unnamed

    def test_the_link_fills_in_the_form(self):
        link = urllib.parse.urlsplit(suggest.issue_url("Sort by power\nplease", "Editor 9.9.9, Simple mode", "9.9.9"))
        self.assertEqual(f"{link.scheme}://{link.netloc}{link.path}", share_ids.ISSUE_URL)
        self.assertEqual(urllib.parse.parse_qs(link.query), {
            "template": ["suggestion.yml"], "title": ["Suggestion: Sort by power"], "suggestion": ["Sort by power\nplease"], "setup": ["Editor 9.9.9, Simple mode"], "version": ["9.9.9"],
        })
        # Without the line about the editor, its box is left for whoever sends it; a title can be given.
        bare = urllib.parse.parse_qs(urllib.parse.urlsplit(suggest.issue_url("(paste it here)", "", "9.9.9", "Suggestion: Sort by power")).query)
        self.assertEqual((bare["title"], "setup" in bare), (["Suggestion: Sort by power"], False))
        # The form has the boxes the link names, and the title the editor's own begin with.
        form = FORM.read_text(encoding="utf-8")
        for box in ("suggestion", "setup", "version"):
            self.assertIn(f"    id: {box}\n", form)
        self.assertIn('title: "Suggestion: "', form)
        self.assertIn('labels: ["suggestion"]', form)

    def test_what_is_copied_has_the_line_about_the_editor_under_it(self):
        self.assertEqual(suggest.to_copy("Sort by power", "Editor 9.9.9, Simple mode"), "Sort by power\n\n(Editor 9.9.9, Simple mode)")
        self.assertEqual(suggest.to_copy("Sort by power", ""), "Sort by power")


if __name__ == "__main__":
    unittest.main()
