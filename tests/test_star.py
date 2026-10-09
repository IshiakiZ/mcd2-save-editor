import unittest

from dungeons2_editor import __version__, star, updater


class StarTests(unittest.TestCase):
    def test_it_asks_in_this_version_and_in_no_other(self):
        # The editor asks for a star in one version only. This fails on purpose when the version number moves
        # on: the version after goes out without the question. Take out star.py, welcome's and
        # ask_for_a_star's lines in gui.py, and the tests of them.
        self.assertEqual(star.ASK_IN, __version__)

    def test_who_is_asked(self):
        self.assertTrue(star.should_ask({}, star.ASK_IN, online=True))
        self.assertFalse(star.should_ask({star.SETTING: True}, star.ASK_IN, online=True))  # once
        self.assertFalse(star.should_ask({}, star.ASK_IN, online=False))  # the edition that never goes online: nobody
        self.assertFalse(star.should_ask({}, star.ASK_IN, online=True, used_before=False))  # not before they've used it
        self.assertFalse(star.should_ask({}, "0.0.1", online=True))  # no other version
        self.assertEqual(star.PAGE, f"https://github.com/{updater.REPOSITORY}")  # the project's own page, and nowhere else


if __name__ == "__main__":
    unittest.main()
