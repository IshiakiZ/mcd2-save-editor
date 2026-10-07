import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import cli, gui, paths


class PathTests(unittest.TestCase):
    def test_from_source_files_live_next_to_the_code(self):
        self.assertEqual(paths.data_dir(), paths.SOURCE_ROOT)
        self.assertEqual(paths.resource("assets/app.ico"), paths.SOURCE_ROOT / "assets" / "app.ico")
        self.assertTrue(paths.resource("assets/app.ico").is_file())

    def test_the_exe_keeps_files_in_local_app_data(self):
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\someone\AppData\Local"}):
            self.assertEqual(paths.data_dir(), Path(r"C:\Users\someone\AppData\Local") / "MCD2 Save Editor")
        with mock.patch.object(sys, "_MEIPASS", r"C:\Temp\_MEI123", create=True):
            self.assertEqual(paths.resource("assets/app.ico"), Path(r"C:\Temp\_MEI123") / "assets" / "app.ico")

    def test_settings_folder_is_created_when_needed(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "MCD2 Save Editor" / "editor-settings.json"
            gui._save_settings(target, {"advanced": True})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"advanced": True})

    def test_gui_close_after_is_passed_through(self):
        with mock.patch.object(gui, "run", return_value=0) as run:
            self.assertEqual(cli.main(["gui", "--close-after", "2.5"]), 0)
        self.assertEqual((run.call_args.args[3], run.call_args.kwargs), (2.5, {"look": None}))

    def test_gui_can_be_opened_in_a_look(self):
        with mock.patch.object(gui, "run", return_value=0) as run:
            self.assertEqual(cli.main(["gui", "--look", "glass", "--close-after", "1"]), 0)
        self.assertEqual(run.call_args.kwargs, {"look": "glass"})
        with mock.patch.object(gui, "run", return_value=0) as run, mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            cli.main(["gui", "--look", "neon"])
        run.assert_not_called()

    def test_folder_options_work_before_or_after_the_command(self):
        from .helpers import SETTINGS_TEXT, make_profile, shift_encode

        with tempfile.TemporaryDirectory() as temp:
            profile = make_profile(Path(temp), {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT)})
            # No auto-detected saves, so the test can't pass by finding real ones on this PC.
            with mock.patch("sys.stdout"), mock.patch("dungeons2_editor.saves.find_profiles", return_value=[]):
                self.assertEqual(cli.main(["verify", "--profile", str(profile)]), 0)
                self.assertEqual(cli.main(["--profile", str(profile), "verify"]), 0)
            with mock.patch.object(gui, "run", return_value=0) as run:
                cli.main(["gui", "--profile", str(profile), "--close-after", "1"])
            self.assertEqual(run.call_args.args[0], profile)


if __name__ == "__main__":
    unittest.main()
