import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import codec, saves, wgs

from .helpers import HERO_TEXT, SETTINGS_TEXT, hero_save_text, make_profile, shift_encode, snapshot

NOT_RUNNING = lambda: []  # noqa: E731


class SaveProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.backups = root / "backups"
        self.profile_path = make_profile(
            root / "saves",
            {
                "GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT),
                "auth_dynamic_entjwtbin": os.urandom(300),
                "OnlineDataTables": os.urandom(300),
                "Mystery": os.urandom(64),
                "OfflineHero": shift_encode(HERO_TEXT),
            },
        )

    def edited_settings(self, profile):
        document = copy.deepcopy(profile.get("GlobalSaveDataDefault").decoded.document)
        document["blobs"][0]["masterVolume"] = 85
        return document

    def test_containers_are_classified(self):
        profile = saves.SaveProfile(self.profile_path)
        kinds = {container.name: container.kind for container in profile.containers}
        self.assertEqual(
            kinds,
            {
                "GlobalSaveDataDefault": saves.Kind.EDITABLE,
                "auth_dynamic_entjwtbin": saves.Kind.PROTECTED,
                "OnlineDataTables": saves.Kind.PROTECTED,
                "Mystery": saves.Kind.UNSUPPORTED,
                "OfflineHero": saves.Kind.EDITABLE,
            },
        )
        self.assertEqual(profile.get("OfflineHero").decoded.document["blobs"][0]["emeralds"], 120)

    def test_protected_containers_are_never_read(self):
        with mock.patch.object(wgs, "read_blobs", wraps=wgs.read_blobs) as read_blobs:
            profile = saves.SaveProfile(self.profile_path)
        read_names = {call.args[1].name for call in read_blobs.call_args_list}
        self.assertNotIn("auth_dynamic_entjwtbin", read_names)
        self.assertNotIn("OnlineDataTables", read_names)
        self.assertEqual(profile.get("auth_dynamic_entjwtbin").blobs, {})

    def test_save_backs_up_then_writes_only_that_container(self):
        profile = saves.SaveProfile(self.profile_path)
        before = snapshot(self.profile_path)
        document = self.edited_settings(profile)

        backup = profile.save("GlobalSaveDataDefault", document, self.backups, check_game=NOT_RUNNING)

        reloaded = saves.SaveProfile(self.profile_path)
        self.assertEqual(reloaded.get("GlobalSaveDataDefault").decoded.document, document)
        self.assertEqual(reloaded.get("GlobalSaveDataDefault").entry.sync_state, wgs.MODIFIED)
        for name in ("auth_dynamic_entjwtbin", "OnlineDataTables", "Mystery", "OfflineHero"):
            self.assertEqual(reloaded.index.find(name), profile.index.find(name))
        self.assertEqual(snapshot(backup / self.profile_path.name), before)
        self.assertEqual([b.path for b in saves.list_backups(self.backups)], [backup])

        raw = wgs.read_blobs(self.profile_path, reloaded.index.find("GlobalSaveDataDefault"))["Data"]
        self.assertEqual(codec.decode_bytes(raw).decode(), SETTINGS_TEXT.replace('"masterVolume":60', '"masterVolume":85'))

    def test_the_same_profile_can_save_twice(self):
        profile = saves.SaveProfile(self.profile_path)
        profile.save("GlobalSaveDataDefault", self.edited_settings(profile), self.backups, check_game=NOT_RUNNING)
        document = self.edited_settings(profile)
        document["blobs"][0]["masterVolume"] = 90
        profile.save("GlobalSaveDataDefault", document, self.backups, check_game=NOT_RUNNING)
        saved = saves.SaveProfile(self.profile_path).get("GlobalSaveDataDefault").decoded.document
        self.assertEqual(saved["blobs"][0]["masterVolume"], 90)
        self.assertEqual(len(saves.list_backups(self.backups)), 2)

    def test_save_refuses_while_the_game_runs(self):
        profile = saves.SaveProfile(self.profile_path)
        before = snapshot(self.profile_path)
        with self.assertRaises(saves.GameRunningError):
            profile.save("GlobalSaveDataDefault", self.edited_settings(profile), self.backups, check_game=lambda: ["Dungeons-WinGDK-Shipping.exe"])
        self.assertEqual(snapshot(self.profile_path), before)
        self.assertFalse(self.backups.exists())

    def test_default_game_check_is_used(self):
        profile = saves.SaveProfile(self.profile_path)
        with mock.patch.object(saves, "running_game_processes", return_value=["Dungeons.exe"]):
            with self.assertRaises(saves.GameRunningError):
                profile.save("GlobalSaveDataDefault", self.edited_settings(profile), self.backups)

    def test_save_refuses_if_the_game_saved_in_the_meantime(self):
        profile = saves.SaveProfile(self.profile_path)
        game = saves.SaveProfile(self.profile_path)
        game.save("GlobalSaveDataDefault", self.edited_settings(game), self.backups, check_game=NOT_RUNNING)
        with self.assertRaises(saves.StaleSaveError):
            profile.save("GlobalSaveDataDefault", self.edited_settings(profile), self.backups, check_game=NOT_RUNNING)

    def test_only_editable_containers_can_be_saved(self):
        profile = saves.SaveProfile(self.profile_path)
        for name in ("auth_dynamic_entjwtbin", "Mystery", "Nope"):
            with self.assertRaises(ValueError):
                profile.save(name, {}, self.backups, check_game=NOT_RUNNING)

    def test_failure_after_writing_rolls_the_folder_back(self):
        profile = saves.SaveProfile(self.profile_path)
        before = snapshot(self.profile_path)
        real_write = wgs.write_container

        def write_then_fail(*args, **kwargs):
            real_write(*args, **kwargs)
            raise RuntimeError("simulated crash")

        with mock.patch.object(wgs, "write_container", side_effect=write_then_fail):
            with self.assertRaises(saves.SaveFailedError) as caught:
                profile.save("GlobalSaveDataDefault", self.edited_settings(profile), self.backups, check_game=NOT_RUNNING)
        self.assertTrue(caught.exception.rolled_back)
        self.assertEqual(snapshot(self.profile_path), before)

    def test_restore_writes_the_old_data_as_a_new_revision(self):
        profile = saves.SaveProfile(self.profile_path)
        original = profile.get("GlobalSaveDataDefault")
        profile.save("GlobalSaveDataDefault", self.edited_settings(profile), self.backups, check_game=NOT_RUNNING)
        backup = saves.list_backups(self.backups)[0]

        restored = saves.SaveProfile(self.profile_path).restore(backup, self.backups, check_game=NOT_RUNNING)

        self.assertEqual(restored, ["GlobalSaveDataDefault"])
        now = saves.SaveProfile(self.profile_path).get("GlobalSaveDataDefault")
        self.assertEqual(now.blobs, original.blobs)
        self.assertEqual(now.entry.revision, original.entry.revision + 2)
        self.assertEqual(now.entry.sync_state, wgs.MODIFIED)
        self.assertEqual(len(saves.list_backups(self.backups)), 2)  # plus the safety copy made before restoring

    def test_restore_does_nothing_when_data_matches(self):
        profile = saves.SaveProfile(self.profile_path)
        saves.make_backup(self.profile_path, self.backups)
        before = snapshot(self.profile_path)
        self.assertEqual(profile.restore(saves.list_backups(self.backups)[0], self.backups, check_game=NOT_RUNNING), [])
        self.assertEqual(snapshot(self.profile_path), before)


class SteamSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile_path = self.root / saves.STEAM_SAVE_DIR
        self.profile_path.mkdir(parents=True)
        self.save_path = self.profile_path / "Character00000000-0000-1000-8000-000000000002.sav"
        self.original = hero_save_text().encode("utf-8")
        self.save_path.write_bytes(self.original)
        self.backups = self.root / "backups"

    def test_finds_steam_profile_from_local_appdata(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}):
            self.assertEqual(saves.find_profiles(), [self.profile_path])

    def test_steam_auth_and_device_files_are_never_decoded(self):
        protected_path = self.root / "protected"
        protected_path.mkdir()
        names = ("auth_dynamic_ent.jwt.bin", "entitlements.jwt.bin", "Guid.bin")
        for name in names:
            (protected_path / f"{name}.sav").write_bytes(b"private platform data")

        with mock.patch.object(codec, "decode_blob", side_effect=AssertionError("protected data was read")):
            profile = saves.SaveProfile(protected_path)

        self.assertTrue(all(container.kind is saves.Kind.PROTECTED for container in profile.containers))
        self.assertTrue(all(container.blobs == {} for container in profile.containers))

    def test_loads_and_saves_standalone_hero_file_with_backup(self):
        profile = saves.SaveProfile(self.profile_path)
        container = profile.containers[0]
        self.assertTrue(profile.is_steam)
        self.assertEqual(container.kind, saves.Kind.EDITABLE)
        self.assertEqual(container.hero.level, 1)

        document = copy.deepcopy(container.decoded.document)
        document["CharacterSaveV1"]["Ability"]["Attributes"][1]["CurrentValue"] = 777
        backup = profile.save(container.name, document, self.backups, check_game=NOT_RUNNING)

        saved = saves.SaveProfile(self.profile_path).get(container.name)
        self.assertEqual(saved.decoded.document, document)
        self.assertEqual(codec.decode_blob(self.save_path.read_bytes()).document, document)
        self.assertEqual((backup / self.profile_path.name / self.save_path.name).read_bytes(), self.original)
        self.assertEqual(len(list(self.profile_path.glob("*.sav"))), 1)

    def test_lists_and_restores_steam_backup(self):
        profile = saves.SaveProfile(self.profile_path)
        document = copy.deepcopy(profile.containers[0].decoded.document)
        document["CharacterSaveV1"]["MetaData"]["Level"] = 9
        profile.save(profile.containers[0].name, document, self.backups, check_game=NOT_RUNNING)

        backup = saves.list_backups(self.backups)[0]
        restored = saves.SaveProfile(self.profile_path).restore(backup, self.backups, check_game=NOT_RUNNING)

        self.assertEqual(restored, [profile.containers[0].name])
        self.assertEqual(self.save_path.read_bytes(), self.original)


class HeroContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.backups = root / "backups"
        self.profile_path = make_profile(
            root / "saves",
            {
                "Character00000000-0000-1000-8000-000000000002": hero_save_text().encode(),
                "Character00000000-0000-1000-8000-000000000003": hero_save_text(online=True).encode(),
                "GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT),
            },
        )

    def test_offline_heroes_are_editable_and_online_ones_are_not(self):
        profile = saves.SaveProfile(self.profile_path)
        offline, online = (profile.get(f"Character00000000-0000-1000-8000-00000000000{n}") for n in (2, 3))
        self.assertEqual((offline.kind, offline.label), (saves.Kind.EDITABLE, "Offline hero (Ranger Deluxe)"))
        self.assertEqual((online.kind, online.label), (saves.Kind.PROTECTED, "Online hero (Ranger Deluxe)"))
        self.assertIsNone(profile.get("GlobalSaveDataDefault").hero)
        with self.assertRaises(ValueError):
            profile.save(online.name, online.decoded.document, self.backups, check_game=NOT_RUNNING)

    def test_saving_a_hero_keeps_it_plain_json(self):
        profile = saves.SaveProfile(self.profile_path)
        name = "Character00000000-0000-1000-8000-000000000002"
        document = copy.deepcopy(profile.get(name).decoded.document)
        hero = profile.get(name).hero.__class__(document)
        hero.set_attributes({"Emeralds": 5000})
        profile.save(name, document, self.backups, check_game=NOT_RUNNING)
        raw = wgs.read_blobs(self.profile_path, wgs.read_index(self.profile_path).find(name))["Data"]
        self.assertEqual(raw, hero_save_text(emeralds=5000).encode())


class FindProfilesTests(unittest.TestCase):
    def test_finds_dungeons_ii_save_folders_only(self):
        with tempfile.TemporaryDirectory() as temp:
            wgs_dir = Path(temp, "Packages", "Microsoft.MinecraftDungeons2_8wekyb3d8bbwe", "SystemAppData", "wgs")
            profile = make_profile(wgs_dir, {"A": b"x"})
            make_profile(Path(temp, "Packages", "Microsoft.Lovika_8wekyb3d8bbwe", "SystemAppData", "wgs"), {"A": b"x"})
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": temp}):
                self.assertEqual(saves.find_profiles(), [profile])


if __name__ == "__main__":
    unittest.main()
