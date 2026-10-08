"""Saves kept a folder each (dungeons2_editor/folders.py): read, saved and restored like the other layouts, and
only ever opened by hand."""

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import folders, recorder, saves
from dungeons2_editor.mcp_server import EditorServer

from .helpers import SETTINGS_TEXT, hero_save_text, make_profile, shift_encode, snapshot
from .test_steam import make_steam_folder

NOT_RUNNING = lambda: []  # noqa: E731
HERO = "Character0123456789abcdef"
STAMP = b"\x80\x1f\x9c\x0b\x2d\xa7\xdc\x08"  # whatever a LastModifiedTime file holds: the editor never reads it


def make_save_folders(root: Path, saves_in_it: dict[str, bytes] | None = None) -> Path:
    """A SaveGames folder with a folder for each save: its Data, and the other file such a folder has."""
    folder = Path(root) / "SaveGames"
    folder.mkdir(parents=True)
    saves_in_it = saves_in_it or {
        HERO: hero_save_text(emeralds=120, level=5).encode("utf-8"),
        "GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT),
        "auth_dynamic_entjwtbin": b"a sign-in token",
        "Mystery": os.urandom(48),
    }
    for name, data in saves_in_it.items():
        (folder / name).mkdir()
        (folder / name / "Data").write_bytes(data)
        (folder / name / "LastModifiedTime").write_bytes(STAMP)
    (folder / "Empty").mkdir()  # a folder with no Data in it isn't a save
    (folder / "notes.txt").write_bytes(b"not a save")
    return folder


class SaveFoldersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backups = self.root / "backups"
        self.folder = make_save_folders(self.root / "copy")

    def edited(self, profile, emeralds=9000):
        document = copy.deepcopy(profile.get(HERO).decoded.document)
        for attribute in document["CharacterSaveV1"]["Ability"]["Attributes"]:
            if attribute["AttributeName"] == "Emeralds":
                attribute["CurrentValue"] = emeralds
        return document

    def test_the_layout_is_told_from_the_folder(self):
        self.assertEqual(saves.layout_of(self.folder), "folders")
        self.assertTrue(saves.is_save_folder(self.folder) and folders.is_save_folder(self.folder))
        # The other two layouts are still themselves, and none of the three is taken for another.
        xbox = make_profile(self.root / "xbox", {"A": shift_encode(SETTINGS_TEXT)})
        steam_folder = make_steam_folder(self.root / "steam")
        self.assertEqual((saves.layout_of(xbox), saves.layout_of(steam_folder)), ("xbox", "steam"))
        self.assertFalse(folders.is_save_folder(xbox) or folders.is_save_folder(steam_folder))
        (steam_folder / HERO).mkdir()
        (steam_folder / HERO / "Data").write_bytes(b"{}")
        self.assertEqual(saves.layout_of(steam_folder), "steam")  # .sav files in it: that's the Steam version's folder
        # A hero's save has to be there: any folder with a Data file somewhere under it won't do.
        other = self.root / "other"
        (other / "Something").mkdir(parents=True)
        (other / "Something" / "Data").write_bytes(b"x")
        (other / "CharacterWithoutData").mkdir()
        self.assertFalse(saves.is_save_folder(other) or saves.is_save_folder(self.root / "not there"))
        self.assertEqual(saves.layout_of(other), "xbox")  # what a folder is taken for when nothing says otherwise

    def test_saves_are_classified(self):
        profile = saves.SaveProfile(self.folder)
        self.assertTrue(profile.is_loose and not profile.is_steam)
        self.assertEqual(
            {container.name: container.kind for container in profile.containers},
            {
                HERO: saves.Kind.EDITABLE,
                "GlobalSaveDataDefault": saves.Kind.EDITABLE,
                "auth_dynamic_entjwtbin": saves.Kind.PROTECTED,
                "Mystery": saves.Kind.UNSUPPORTED,
            },
        )
        hero = profile.get(HERO)
        self.assertEqual((hero.hero.level, hero.hero.attribute("Emeralds"), hero.blob_name, hero.label), (5, 120, "Data", "Offline hero (Ranger Deluxe)"))
        self.assertEqual(profile.get("auth_dynamic_entjwtbin").blobs, {})  # the sign-in token is never read
        entry = hero.entry
        self.assertEqual((entry.name, entry.size, entry.sync_state, entry.local_file), (HERO, len((self.folder / HERO / "Data").read_bytes()), 1, True))

    def test_save_replaces_only_that_data_file_and_backs_up_first(self):
        profile = saves.SaveProfile(self.folder)
        before = snapshot(self.folder)
        backup = profile.save(HERO, self.edited(profile), self.backups, NOT_RUNNING)
        after = snapshot(self.folder)
        changed = sorted(name for name in after if after[name] != before.get(name))
        self.assertEqual([Path(name).as_posix() for name in changed], [f"{HERO}/Data"])
        self.assertEqual(set(after), set(before))  # nothing added, nothing left behind
        self.assertEqual((self.folder / HERO / "LastModifiedTime").read_bytes(), STAMP)  # not the editor's to write
        self.assertEqual(saves.SaveProfile(self.folder).get(HERO).hero.attribute("Emeralds"), 9000)
        self.assertEqual(snapshot(backup / "SaveGames"), before)  # the whole folder as it was
        # The same profile can save again, and a restore puts the first one back.
        profile.save(HERO, self.edited(profile, 7), self.backups, NOT_RUNNING)
        first = saves.list_backups(self.backups)[-1]
        self.assertEqual(profile.restore(first, self.backups, NOT_RUNNING), [HERO])
        self.assertEqual(snapshot(self.folder), before)

    def test_an_unedited_hero_is_written_back_byte_for_byte(self):
        profile = saves.SaveProfile(self.folder)
        original = (self.folder / HERO / "Data").read_bytes()
        profile.save(HERO, copy.deepcopy(profile.get(HERO).decoded.document), self.backups, NOT_RUNNING)
        self.assertEqual((self.folder / HERO / "Data").read_bytes(), original)

    def test_save_refuses_while_the_game_runs_or_after_it_has_saved(self):
        profile = saves.SaveProfile(self.folder)
        before = snapshot(self.folder)
        with self.assertRaises(saves.GameRunningError):
            profile.save(HERO, self.edited(profile), self.backups, lambda: ["Dungeons-Win64-Shipping.exe"])
        self.assertEqual(snapshot(self.folder), before)
        stamp, revision = saves.profile_stamp(self.folder), saves.current_revision(self.folder, HERO)
        data = self.folder / HERO / "Data"
        data.write_bytes(hero_save_text(emeralds=121, level=5).encode("utf-8"))  # the game saved
        os.utime(data, ns=(revision + 5_000_000_000, revision + 5_000_000_000))
        self.assertNotEqual((saves.profile_stamp(self.folder), saves.current_revision(self.folder, HERO)), (stamp, revision))
        with self.assertRaises(saves.StaleSaveError):
            profile.save(HERO, self.edited(profile), self.backups, NOT_RUNNING)
        self.assertEqual(saves.SaveProfile(self.folder).get(HERO).hero.attribute("Emeralds"), 121)
        self.assertIsNone(saves.current_revision(self.folder, "CharacterGone"))

    def test_a_failed_write_rolls_the_folder_back(self):
        profile = saves.SaveProfile(self.folder)
        before = snapshot(self.folder)

        def broken(folder, name, blobs):
            (folder / name / "Data").write_bytes(b"garbage")
            raise OSError("disk on fire")

        with mock.patch.object(folders, "write_file", broken):
            with self.assertRaises(saves.SaveFailedError) as caught:
                profile.save(HERO, self.edited(profile), self.backups, NOT_RUNNING)
        self.assertTrue(caught.exception.rolled_back)
        self.assertEqual(snapshot(self.folder), before)

    def test_only_a_file_the_game_wrote_is_written_over(self):
        with self.assertRaises(FileNotFoundError):
            folders.write_file(self.folder, "CharacterNew", {"Data": b"{}"})
        self.assertFalse((self.folder / "CharacterNew").exists())
        with self.assertRaises(FileNotFoundError):
            folders.write_file(self.folder, "Empty", {"Data": b"{}"})
        self.assertEqual(list((self.folder / "Empty").iterdir()), [])
        profile = saves.SaveProfile(self.folder)
        with self.assertRaises(ValueError):  # and only a save the editor could read
            profile.save("Mystery", {}, self.backups, NOT_RUNNING)

    def test_a_save_that_is_gone_is_not_put_back_but_named(self):
        saves.make_backup(self.folder, self.backups)
        (backup,) = saves.list_backups(self.backups)
        for path in (self.folder / HERO).iterdir():
            path.unlink()
        (self.folder / HERO).rmdir()  # the hero was deleted in the game
        other = self.folder / "CharacterOther"
        other.mkdir()
        (other / "Data").write_bytes(hero_save_text().encode("utf-8"))
        profile = saves.SaveProfile(self.folder)
        self.assertEqual(profile.restore_problems(backup), ["Offline hero (Ranger Deluxe) isn't in your saves any more."])
        self.assertEqual(profile.restore(backup, self.backups, NOT_RUNNING), [])
        self.assertFalse((self.folder / HERO).exists())

    def test_it_is_opened_by_hand_and_never_looked_for(self):
        # Nothing finds a folder like this by itself: it's picked in Open a save folder…, or given with --profile.
        self.assertFalse(hasattr(folders, "find_folders"))
        home = {"LOCALAPPDATA": str(self.root), "PUBLIC": str(self.root), "HOME": str(self.root), "USERPROFILE": str(self.root)}
        with mock.patch.dict(os.environ, home), mock.patch.object(Path, "home", return_value=self.root):
            self.assertEqual(saves.find_profiles(), [])
        # Once open, the rest of the editor reads it like any other: the recorder says which kind of save it was
        # and nothing of where, and the editor can't start a copy of the game it knows nothing about.
        from dungeons2_editor import game_launch

        self.assertIsNone(game_launch.target("folders"))
        watching = recorder.Recorder(self.folder, self.root / "recording", say=lambda line: None)
        self.addCleanup(watching.events_file.close)
        watching.begin()
        summary = watching.summary()
        self.assertEqual(summary.splitlines()[1], "Saves: a folder for each save")
        self.assertNotIn(str(self.root), summary)

    def test_an_assistant_is_told_the_layout_is_untried_when_it_saves(self):
        server = EditorServer(self.folder, self.backups)

        def call(tool, **arguments):
            reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}})
            return reply["result"]["content"][0]["text"]

        with mock.patch.object(saves, "running_game_processes", return_value=[]):
            self.assertIn("Emeralds", call("set_stats", hero="00000000", stats={"Emeralds": 500}))
            saved = call("save_changes", hero="00000000")
        self.assertIn("Saved.", saved)
        self.assertIn("a way of saving the editor's developer has no copy of to try", saved)
        self.assertEqual(saves.SaveProfile(self.folder).get(HERO).hero.attribute("Emeralds"), 500)


if __name__ == "__main__":
    unittest.main()
