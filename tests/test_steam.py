import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import saves, steam, wgs

from .helpers import SETTINGS_TEXT, hero_save_text, make_profile, shift_encode, snapshot

NOT_RUNNING = lambda: []  # noqa: E731
HERO_FILE = "Character0123456789abcdef.sav"
PROTON_SAVES = Path("steamapps/compatdata/1912410/pfx/drive_c/users/steamuser/AppData/Local/Dungeons2/Saved/SaveGames")


def make_steam_folder(root: Path, files: dict[str, bytes] | None = None) -> Path:
    folder = Path(root) / "SaveGames"
    folder.mkdir(parents=True)
    files = files or {
        HERO_FILE: hero_save_text(emeralds=120, level=5).encode("utf-8"),
        "GlobalSaveDataDefault.sav": shift_encode(SETTINGS_TEXT),
        "Character_gvas.sav": b"GVAS\x02\x00\x00\x00" + os.urandom(64),
        "Mystery.sav": os.urandom(48),
        "notes.txt": b"not a save",
    }
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return folder


class SteamProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backups = self.root / "backups"
        self.folder = make_steam_folder(self.root / "steam")

    def edited(self, profile, emeralds=9000):
        document = copy.deepcopy(profile.get("Character0123456789abcdef").decoded.document)
        for attribute in document["CharacterSaveV1"]["Ability"]["Attributes"]:
            if attribute["AttributeName"] == "Emeralds":
                attribute["CurrentValue"] = emeralds
        return document

    def test_layout_is_detected_from_the_folder(self):
        self.assertEqual(saves.layout_of(self.folder), "steam")
        xbox = make_profile(self.root / "xbox", {"A": shift_encode(SETTINGS_TEXT)})
        self.assertEqual(saves.layout_of(xbox), "xbox")
        self.assertFalse(saves.SaveProfile(xbox).is_steam)

    def test_sav_files_are_classified(self):
        profile = saves.SaveProfile(self.folder)
        self.assertTrue(profile.is_steam)
        kinds = {c.name: c.kind for c in profile.containers}
        self.assertEqual(
            kinds,
            {
                "Character0123456789abcdef": saves.Kind.EDITABLE,
                "Character_gvas": saves.Kind.UNSUPPORTED,
                "GlobalSaveDataDefault": saves.Kind.EDITABLE,
                "Mystery": saves.Kind.UNSUPPORTED,
            },
        )
        self.assertIn("GVAS", profile.get("Character_gvas").note)
        hero = profile.get("Character0123456789abcdef").hero
        self.assertIsNotNone(hero)
        self.assertEqual(hero.attribute("Emeralds"), 120)

    def test_save_replaces_only_that_file_and_backs_up_first(self):
        profile = saves.SaveProfile(self.folder)
        before = snapshot(self.folder)
        backup = profile.save("Character0123456789abcdef", self.edited(profile), self.backups, NOT_RUNNING)
        after = snapshot(self.folder)
        self.assertEqual(set(after), set(before), "no stray temporary files")
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual(changed, {HERO_FILE})
        self.assertEqual(snapshot(backup / "SaveGames"), before)
        reread = saves.SaveProfile(self.folder).get("Character0123456789abcdef")
        self.assertEqual(reread.hero.attribute("Emeralds"), 9000)
        self.assertTrue(reread.decoded.exact)

    def test_unedited_hero_is_written_back_byte_for_byte(self):
        profile = saves.SaveProfile(self.folder)
        before = (self.folder / HERO_FILE).read_bytes()
        profile.save("Character0123456789abcdef", profile.get("Character0123456789abcdef").decoded.document, self.backups, NOT_RUNNING)
        self.assertEqual((self.folder / HERO_FILE).read_bytes(), before)

    def test_the_same_profile_can_save_twice(self):
        profile = saves.SaveProfile(self.folder)
        profile.save("Character0123456789abcdef", self.edited(profile, 100), self.backups, NOT_RUNNING)
        profile.save("Character0123456789abcdef", self.edited(profile, 200), self.backups, NOT_RUNNING)
        self.assertEqual(saves.SaveProfile(self.folder).get("Character0123456789abcdef").hero.attribute("Emeralds"), 200)

    def test_save_refuses_while_the_game_runs(self):
        profile = saves.SaveProfile(self.folder)
        before = snapshot(self.folder)
        with self.assertRaises(saves.GameRunningError):
            profile.save("Character0123456789abcdef", self.edited(profile), self.backups, lambda: ["Dungeons-Win64-Shipping.exe"])
        self.assertEqual(snapshot(self.folder), before)

    def test_save_refuses_if_the_game_saved_in_the_meantime(self):
        profile = saves.SaveProfile(self.folder)
        other = hero_save_text(emeralds=7, level=5).encode("utf-8")
        (self.folder / HERO_FILE).write_bytes(other)
        with self.assertRaises(saves.StaleSaveError):
            profile.save("Character0123456789abcdef", self.edited(profile), self.backups, NOT_RUNNING)
        self.assertEqual((self.folder / HERO_FILE).read_bytes(), other)

    def test_unsupported_files_cannot_be_saved(self):
        profile = saves.SaveProfile(self.folder)
        with self.assertRaises(ValueError):
            profile.save("Mystery", {}, self.backups, NOT_RUNNING)

    def test_failed_write_rolls_the_folder_back(self):
        profile = saves.SaveProfile(self.folder)
        before = snapshot(self.folder)

        def broken(folder, name, blobs):
            (folder / (name + ".sav")).write_bytes(b"garbage")
            raise OSError("disk on fire")

        with mock.patch.object(steam, "write_file", broken):
            with self.assertRaises(saves.SaveFailedError) as caught:
                profile.save("Character0123456789abcdef", self.edited(profile), self.backups, NOT_RUNNING)
        self.assertTrue(caught.exception.rolled_back)
        self.assertEqual(snapshot(self.folder), before)

    def test_restore_puts_back_the_old_data(self):
        profile = saves.SaveProfile(self.folder)
        original = (self.folder / HERO_FILE).read_bytes()
        profile.save("Character0123456789abcdef", self.edited(profile), self.backups, NOT_RUNNING)
        self.assertNotEqual((self.folder / HERO_FILE).read_bytes(), original)
        backups = saves.list_backups(self.backups)
        self.assertEqual(len(backups), 1)
        restored = profile.restore(backups[0], self.backups, NOT_RUNNING)
        self.assertEqual(restored, ["Character0123456789abcdef"])
        self.assertEqual((self.folder / HERO_FILE).read_bytes(), original)

    def test_stamp_and_revision_notice_the_game_saving(self):
        stamp = saves.profile_stamp(self.folder)
        revision = saves.current_revision(self.folder, "Character0123456789abcdef")
        self.assertIsNotNone(stamp)
        self.assertIsNone(saves.current_revision(self.folder, "NoSuchHero"))
        path = self.folder / HERO_FILE
        path.write_bytes(hero_save_text(emeralds=1).encode("utf-8"))
        os.utime(path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        self.assertNotEqual(saves.profile_stamp(self.folder), stamp)
        self.assertNotEqual(saves.current_revision(self.folder, "Character0123456789abcdef"), revision)

    def test_entries_look_like_xbox_ones_to_the_rest_of_the_editor(self):
        entry = saves.SaveProfile(self.folder).get("Character0123456789abcdef").entry
        self.assertGreater(wgs.filetime_to_unix(entry.mtime), 1_600_000_000)
        self.assertEqual(entry.sync_state, wgs.SYNCED)
        self.assertEqual(entry.size, (self.folder / HERO_FILE).stat().st_size)


class SteamDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        env = mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("LOCALAPPDATA", None)
        patcher = mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)

    def proton_folder(self, steam_root: Path) -> Path:
        folder = steam_root / PROTON_SAVES
        folder.mkdir(parents=True)
        (folder / HERO_FILE).write_bytes(hero_save_text().encode("utf-8"))
        return folder

    def test_finds_the_default_linux_steam_folder(self):
        folder = self.proton_folder(self.home / ".local/share/Steam")
        self.assertEqual(steam.find_folders(), [folder.resolve()])
        self.assertEqual(saves.find_profiles(), [folder.resolve()])

    def test_finds_flatpak_steam(self):
        folder = self.proton_folder(self.home / ".var/app/com.valvesoftware.Steam/.local/share/Steam")
        self.assertEqual(steam.find_folders(), [folder.resolve()])

    def test_finds_a_game_on_another_steam_library(self):
        main = self.home / ".local/share/Steam"
        (main / "steamapps").mkdir(parents=True)
        library = Path(self.temp.name) / "games-drive" / "SteamLibrary"
        folder = self.proton_folder(library)
        (main / "steamapps" / "libraryfolders.vdf").write_text(
            f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{main}"\n\t}}\n\t"1"\n\t{{\n\t\t"path"\t\t"{library}"\n\t}}\n}}\n',
            encoding="utf-8",
        )
        self.assertEqual(steam.find_folders(), [folder.resolve()])

    def test_finds_the_windows_steam_folder(self):
        local = Path(self.temp.name) / "AppData" / "Local"
        folder = local / "Dungeons2" / "Saved" / "SaveGames"
        folder.mkdir(parents=True)
        (folder / HERO_FILE).write_bytes(hero_save_text().encode("utf-8"))
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            self.assertEqual(steam.find_folders(), [folder.resolve()])

    def test_finds_a_per_account_subfolder(self):
        base = self.home / ".local/share/Steam" / PROTON_SAVES
        account = base / "76561198000000000"
        account.mkdir(parents=True)
        (account / HERO_FILE).write_bytes(hero_save_text().encode("utf-8"))
        self.assertEqual(steam.find_folders(), [account.resolve()])

    def test_ignores_empty_and_non_save_folders(self):
        folder = self.home / ".local/share/Steam" / PROTON_SAVES
        folder.mkdir(parents=True)
        (folder / "readme.txt").write_text("x")
        self.assertEqual(steam.find_folders(), [])
        self.assertEqual(saves.find_profiles(), [])

    def test_nothing_installed_finds_nothing(self):
        self.assertEqual(saves.find_profiles(), [])


class GameProcessTests(unittest.TestCase):
    def test_steam_executables_are_recognised(self):
        for name in ("Dungeons-Win64-Shipping.exe", "dungeons-win64-shipping.exe", "Dungeons-WinGDK-Shipping.exe", "Dungeons2-Win64-Shipping.exe"):
            self.assertTrue(saves._is_game_process(name), name)
        for name in ("steam.exe", "Dungeons.txt", "notdungeons-shipping.exe", "explorer.exe"):
            self.assertFalse(saves._is_game_process(name), name)

    def test_proton_process_is_found_from_its_command_line(self):
        with mock.patch.object(os, "name", "posix"), mock.patch.object(
            saves, "_linux_process_names", return_value={"Dungeons-Win64-Shipping.exe", "wineserver.exe", "steam.exe"}
        ):
            self.assertEqual(saves.running_game_processes(), ["Dungeons-Win64-Shipping.exe"])

    def test_linux_scan_reads_wine_style_command_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            (proc / "4242").mkdir()
            (proc / "4242" / "cmdline").write_bytes(b"Z:\\home\\me\\Steam\\Dungeons-Win64-Shipping.exe\0-steam\0")
            (proc / "9").mkdir()
            (proc / "9" / "cmdline").write_bytes(b"/usr/bin/bash\0")
            (proc / "self").mkdir()
            real_path = saves.Path
            with mock.patch.object(saves, "Path", lambda p="": proc if p == "/proc" else real_path(p)):
                self.assertEqual(saves._linux_process_names(), {"Dungeons-Win64-Shipping.exe"})


if __name__ == "__main__":
    unittest.main()
