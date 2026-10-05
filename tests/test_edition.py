"""The edition built for Nexus Mods never goes online (dungeons2_editor/edition.py, tools/make_edition.py)."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import cli, edition, updater, wiki

ROOT = Path(__file__).resolve().parent.parent


def make_edition():
    spec = importlib.util.spec_from_file_location("make_edition", ROOT / "tools" / "make_edition.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EditionTests(unittest.TestCase):
    def test_the_source_is_the_github_edition(self):
        self.assertEqual((edition.ONLINE, edition.NAME), (True, "GitHub"))
        edition.require_online("download pictures")  # nothing stops it

    def test_the_build_tool_makes_the_offline_edition_and_back(self):
        tool = make_edition()
        source = tool.EDITION_FILE.read_text(encoding="utf-8")
        nexus = tool.as_edition(source, "nexus")
        made: dict = {}
        exec(compile(nexus, "edition.py", "exec"), made)
        self.assertEqual((made["ONLINE"], made["NAME"]), (False, "Nexus Mods"))
        self.assertEqual(tool.as_edition(nexus, "github"), source)
        with self.assertRaisesRegex(ValueError, "doesn't set ONLINE and NAME"):
            tool.as_edition("nothing to change here", "nexus")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(["somewhere else"]), 2)  # an edition it doesn't know: the file is left alone
        self.assertEqual(tool.EDITION_FILE.read_text(encoding="utf-8"), source)

    def test_the_offline_edition_opens_no_connection(self):
        release = updater.Release("99.0.0", updater.RELEASES_PAGE, f"{updater.DOWNLOADS}v99.0.0/{updater.ASSET_NAME}", 19_000_000, "0" * 64)
        with mock.patch.object(edition, "ONLINE", False), mock.patch.object(edition, "NAME", "Nexus Mods"), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("it went online")) as urlopen, \
                tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(edition.OfflineEdition, "from Nexus Mods, never goes online, so it doesn't look for updates"):
                updater.latest_release()
            self.assertIsNone(updater.check())  # as ever, the check never gets in the way
            with self.assertRaisesRegex(updater.UpdateError, "never goes online"):
                updater.download(release, Path(folder))
            with self.assertRaisesRegex(edition.OfflineEdition, "doesn't download pictures"):
                wiki.list_pictures()
            for command, said in ((["update", "--yes"], "New versions are on Nexus Mods."), (["pictures", "--yes"], "Put your own in the icons folder")):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(cli.main(command), 1)
                self.assertIn("never goes online", out.getvalue())
                self.assertIn(said, out.getvalue())
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
