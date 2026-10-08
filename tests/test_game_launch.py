import unittest
from unittest import mock

from dungeons2_editor import game_launch

XBOX = "shell:AppsFolder\\Microsoft.MinecraftDungeons2_8wekyb3d8bbwe!AppMinecraftDungeonsIIShipping"
STEAM = "steam://rungameid/1912410"


class GameLaunchTests(unittest.TestCase):
    def test_starts_the_copy_the_saves_belong_to(self):
        self.assertEqual(game_launch.target("xbox", "win32"), XBOX)  # the game's entry in Windows' list of apps
        self.assertEqual((game_launch.target("steam", "win32"), game_launch.target("steam", "linux")), (STEAM, STEAM))
        # Where the editor can't: no saves open, the Xbox app's copy off Windows, and a Mac, where the game runs
        # inside a Windows layer.
        for layout, platform in ((None, "win32"), ("xbox", "linux"), ("xbox", "darwin"), ("steam", "darwin"), ("other", "win32")):
            self.assertIsNone(game_launch.target(layout, platform), (layout, platform))

    def test_asks_windows_or_steam_and_runs_nothing_itself(self):
        with mock.patch.object(game_launch.os, "startfile", create=True) as startfile, mock.patch.object(game_launch.subprocess, "Popen") as popen:
            game_launch.launch("xbox", "win32")
            game_launch.launch("steam", "win32")
        self.assertEqual([call.args for call in startfile.call_args_list], [(XBOX,), (STEAM,)])
        popen.assert_not_called()
        with mock.patch.object(game_launch.os, "startfile", create=True) as startfile, mock.patch.object(game_launch.subprocess, "Popen") as popen:
            game_launch.launch("steam", "linux")
        startfile.assert_not_called()
        self.assertEqual(popen.call_args.args[0], ["xdg-open", STEAM])

    def test_says_where_to_start_the_game_when_it_cant(self):
        with self.assertRaisesRegex(game_launch.LaunchError, "can't start the game from here. Start it from Steam."):
            game_launch.launch("steam", "darwin")
        with self.assertRaisesRegex(game_launch.LaunchError, "Start it from the place you got it from."):
            game_launch.launch(None, "win32")
        with mock.patch.object(game_launch.os, "startfile", create=True, side_effect=FileNotFoundError(2, "not found")):
            with self.assertRaisesRegex(game_launch.LaunchError, "Windows has no Minecraft Dungeons II from the Xbox app in its list of apps"):
                game_launch.launch("xbox", "win32")
        with mock.patch.object(game_launch.subprocess, "Popen", side_effect=FileNotFoundError(2, "no xdg-open")):
            with self.assertRaisesRegex(game_launch.LaunchError, "Steam doesn't seem to be installed.*Start it from Steam."):
                game_launch.launch("steam", "linux")
        with mock.patch.object(game_launch.os, "startfile", create=True, side_effect=OSError("access denied")):
            with self.assertRaisesRegex(game_launch.LaunchError, r"The game didn't start \(access denied\). Start it from the Xbox app."):
                game_launch.launch("xbox", "win32")


if __name__ == "__main__":
    unittest.main()
