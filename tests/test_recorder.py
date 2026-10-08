import copy
import json
import os
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from dungeons2_editor import __version__
from dungeons2_editor import recorder as play_recorder
from dungeons2_editor import recorder_dialog, saves, share_ids

from .helpers import SETTINGS_TEXT, hero_item, hero_save_text, make_profile, rolled, rolled_effect, shift_encode, snapshot

HERO = "Character00000000-0000-1000-8000-000000000002"
NOT_RUNNING = lambda: []  # noqa: E731



class PlayRecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.profile = make_profile(
            self.dir / "saves",
            {HERO: hero_save_text().encode(), "GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), "auth_dynamic_entjwtbin": b"a sign-in token"},
        )
        self.said: list[str] = []
        self.now = 1_800_000_000.0
        self.recorder = play_recorder.Recorder(self.profile, self.dir / "play", say=self.said.append, clock=lambda: self.now)
        self.addCleanup(lambda: self.recorder.events_file.closed or self.recorder.events_file.close())

    def game_saves(self, change, name=HERO):
        """What the game does when it saves: a new revision of the container, with the changed document."""
        profile = saves.SaveProfile(self.profile)
        document = copy.deepcopy(profile.get(name).decoded.document)
        change(document)
        profile.save(name, document, self.dir / "backups", check_game=NOT_RUNNING)
        self.now += 60

    def kinds(self):
        return [record["kind"] for record in self.recorder.log]

    def events(self, kind):
        return [record for record in self.recorder.log if record["kind"] == kind]

    def test_first_look_writes_down_what_is_there_and_only_reads(self):
        before = snapshot(self.profile)
        self.recorder.begin("1.1.1.0")
        self.assertEqual(snapshot(self.profile), before)  # the save folder is never written to
        self.assertEqual(self.kinds(), ["session_start", "baseline", "progress_baseline", "baseline"])
        start, hero = self.recorder.log[0], self.recorder.log[1]
        self.assertEqual((start["game_version"], start["layout"]), ("1.1.1.0", "xbox"))
        self.assertEqual((hero["what"], hero["stats"]["Emeralds"], len(hero["items"])), ("hero", 55, 5))
        self.assertEqual(hero["serialize_meta"]["FormatHash"], 1764133460)
        self.assertEqual(hero["ids"]["SW.Item.Sword"], "confirmed")
        files = sorted(path.name for path in (self.dir / "play" / "snapshots").iterdir())
        self.assertEqual(len(files), 2)  # the hero and the settings: never the sign-in token
        self.assertFalse([name for name in files if "auth" in name])
        self.assertNotIn("auth_dynamic_entjwtbin", self.recorder.last)
        saved = json.loads((self.dir / "play" / "snapshots" / files[0]).read_text(encoding="utf-8"))
        self.assertIn("CharacterSaveV1", saved)
        self.assertEqual(len((self.dir / "play" / "events.jsonl").read_text(encoding="utf-8").splitlines()), 4)

    def test_nothing_new_nothing_written(self):
        self.recorder.begin()
        self.assertTrue(self.recorder.look())
        self.assertEqual(self.kinds(), ["session_start", "baseline", "progress_baseline", "baseline"])

    def test_writes_down_what_a_save_changed(self):
        self.recorder.begin()

        def play(document):
            body = document["CharacterSaveV1"]
            entries = body["Inventory"]["Entries"]
            entries.append(hero_item("SW.Item.Talisman.BrandNew", seed=501))  # picked up something the editor has never heard of
            longbow = next(e for e in entries if e["ItemData"]["TypeTag"] == "SW.Item.Longbow")
            longbow["ItemData"]["Effects"].append({"EffectTag": "SW.Effect.FireAspect", "Tier": 1})  # enchanted
            longbow["ItemData"]["EffectRerolls"] = 2
            entries[:] = [e for e in entries if e["ItemData"]["TypeTag"] != "SW.Item.MysticHelmet"]  # salvaged
            for attribute in body["Ability"]["Attributes"]:
                if attribute["AttributeName"] == "Emeralds":
                    attribute["CurrentValue"] = 300
            body["LootProgression"]["DiscoveredLoot"].append("SW.Item.Mace_Unique1")
            body["Ability"]["ProgressionTags"].append("SW.Progression.Something")

        self.game_saves(play)
        self.assertTrue(self.recorder.look())
        self.assertEqual(self.events("save_written")[0]["what"], "hero")
        self.assertEqual([(e["stat"], e["old"], e["new"]) for e in self.events("stat")], [("Emeralds", 55, 300)])
        (added,) = self.events("item_added")
        self.assertEqual((added["id"], added["entry"]["ItemData"]["GeneratorData"]["GenesisRandomSeed"]), ("SW.Item.Talisman.BrandNew", 501))
        (changed,) = self.events("item_changed")
        paths = {change["path"]: change for change in changed["changes"]}
        self.assertEqual(changed["id"], "SW.Item.Longbow")
        self.assertEqual(paths["ItemData.Effects[0]"]["new"], {"EffectTag": "SW.Effect.FireAspect", "Tier": 1})
        self.assertEqual(paths["ItemData.Effects[0]"]["old"], "(not there)")
        self.assertEqual((paths["ItemData.EffectRerolls"]["old"], paths["ItemData.EffectRerolls"]["new"]), (0, 2))
        self.assertEqual([e["id"] for e in self.events("item_removed")], ["SW.Item.MysticHelmet"])
        new = {e["id"]: e["editor"] for e in self.events("new_id")}
        self.assertEqual(new, {"SW.Item.Talisman.BrandNew": "unknown", "SW.Item.Mace_Unique1": "guess"})
        self.assertEqual({e["section"] for e in self.events("section_changed")}, {"Ability", "LootProgression"})
        self.assertTrue(any("NEW ITEM ID: SW.Item.Talisman.BrandNew" in line for line in self.said))

        text = self.recorder.summary()
        # A summary is the part of a recording that gets passed on, so it says which kind of save it was and
        # nothing of where: the folder's path holds the Windows account's name and the Xbox user's ID.
        self.assertEqual(text.splitlines()[1], "Saves: the Xbox app")
        self.assertFalse([part for part in (str(self.profile), self.profile.name, str(self.dir)) if part in text])
        self.assertIn("The game saved 1 time(s)", text)
        self.assertIn("Item IDs first seen while recording (2):", text)
        self.assertIn("changed  SW.Item.Longbow  ItemData.Effects[0]", text)
        self.assertIn("Emeralds: 55 -> 300 in 1 step(s)", text)
        self.assertEqual(self.recorder.write_summary().read_text(encoding="utf-8"), text)

    def test_the_copy_for_sending_says_what_happened_and_nothing_of_when_or_where(self):
        self.recorder.begin("1.1.1.0")

        def play(document):
            for attribute in document["CharacterSaveV1"]["Ability"]["Attributes"]:
                if attribute["AttributeName"] == "Emeralds":
                    attribute["CurrentValue"] = 300
            longbow = next(e for e in document["CharacterSaveV1"]["Inventory"]["Entries"] if e["ItemData"]["TypeTag"] == "SW.Item.Longbow")
            longbow["ItemData"]["EffectRerolls"] = 2

        self.game_saves(play)  # a minute goes by
        self.recorder.look()
        self.recorder.note("rerolled the bow")
        # Something an item's entry says of when you played, should the game ever change one in place.
        self.recorder.event("item_changed", id="SW.Item.Longbow", changes=[{"path": "ItemData.PickupTimestamp", "old": 1790802481, "new": 1790809999}])
        summary, shared = self.recorder.summary(), self.recorder.summary(sharing=True)

        self.assertEqual(shared.splitlines()[:3], [
            f"Play recording, 1 minute(s) long. Saves: the Xbox app. Editor {__version__}, game 1.1.1.0.",
            "Times are minutes and seconds into the recording.",
            "",
        ])
        # The same things, told by how far into the recording they happened.
        self.assertIn("  +01:00  changed  SW.Item.Longbow  ItemData.EffectRerolls: 0 -> 2", shared)
        self.assertIn("Emeralds: 55 -> 300 in 1 step(s)", shared)
        self.assertIn("  +01:00  rerolled the bow", shared)
        self.assertIn("Soul Storm check:", shared)
        # No date, no time of day, nothing of where the saves or the recording are, no pickup time.
        started = play_recorder.datetime.fromtimestamp(self.recorder.started)
        self.assertRegex(summary, r"\d\d:\d\d:\d\d  changed  SW\.Item\.Longbow")
        self.assertIn(f"{started:%Y-%m-%d}", summary)
        self.assertNotRegex(shared, r"\d\d:\d\d:\d\d")
        self.assertNotIn(f"{started:%Y-%m-%d}", shared)
        self.assertFalse([part for part in (str(self.profile), self.profile.name, str(self.dir), HERO) if part in shared])
        self.assertIn("ItemData.PickupTimestamp", summary)
        self.assertNotIn("PickupTimestamp", shared)

        # Both are written together, and the newest recording that has the copy is the one to send.
        target = self.recorder.write_summary()
        self.assertEqual((target.name, (target.parent / "to_share.txt").read_text(encoding="utf-8")), ("summary.txt", shared))
        self.assertEqual(play_recorder.to_share(self.dir), target.parent / "to_share.txt")
        self.assertIsNone(play_recorder.to_share(self.dir / "saves"))  # nothing there was made by the recorder
        self.assertIsNone(play_recorder.to_share(self.dir / "not there"))
        older = self.dir / "0001-01-01_00-00-00"  # a recording from a version that wrote only a summary
        older.mkdir()
        (older / "summary.txt").write_text("Play recording\nSave folder: somewhere\n", encoding="utf-8")
        (self.dir / "play" / "to_share.txt").unlink()
        self.assertIsNone(play_recorder.to_share(self.dir))

    def test_the_copy_for_sending_fits_in_an_issue(self):
        self.recorder.begin()
        for number in range(play_recorder.MOST_SHARED + 40):
            self.recorder.event("item_removed", id=f"SW.Item.Thing{number}", rarity="Common", power=1)
        shared = self.recorder.summary(sharing=True)
        self.assertIn("  (40 earlier lines were left out to keep this short enough to post)", shared)
        self.assertNotIn("SW.Item.Thing39 ", shared)  # the latest are the ones kept
        self.assertIn(f"SW.Item.Thing{play_recorder.MOST_SHARED + 39} ", shared)
        self.assertEqual(self.recorder.summary().count("  removed  "), play_recorder.MOST_SHARED + 40)  # your own copy has them all
        # However long the rest runs, it stays within what a GitHub issue holds.
        for number in range(400):
            self.recorder.note(f"note {number}: " + "x" * 300)
        shared = self.recorder.summary(sharing=True)
        self.assertLessEqual(len(shared), share_ids.MAX_REPORT)
        self.assertRegex(shared.splitlines()[-1], r"^\(\d+ more lines were left out to keep this short enough to post\)$")

    def test_the_issue_form_has_the_boxes_the_window_fills_in(self):
        link = urllib.parse.urlsplit(recorder_dialog.issue_url("what it found", "9.9.9"))
        self.assertEqual(f"{link.scheme}://{link.netloc}{link.path}", share_ids.ISSUE_URL)
        self.assertEqual(
            urllib.parse.parse_qs(link.query),
            {"template": ["play-recording.yml"], "title": ["A play recording"], "recording": ["what it found"], "version": ["9.9.9"]},
        )
        form = (Path(__file__).resolve().parent.parent / ".github" / "ISSUE_TEMPLATE" / recorder_dialog.ISSUE_TEMPLATE).read_text(encoding="utf-8")
        for box in ("recording", "version"):
            self.assertIn(f"    id: {box}\n", form)
        self.assertIn('title: "A play recording"', form)

    def test_a_save_format_change_stands_out(self):
        self.recorder.begin()
        self.game_saves(lambda document: document["SerializeMeta"].update(SoftVersion=6, FormatHash=42))
        self.recorder.look()
        (event,) = self.events("format_changed")
        self.assertEqual({change["path"] for change in event["changes"]}, {"SoftVersion", "FormatHash"})
        self.assertTrue(any("SAVE FORMAT CHANGED" in line for line in self.said))

    def test_settings_changes_are_written_down_too(self):
        self.recorder.begin()
        self.game_saves(lambda document: document["blobs"][0].update(masterVolume=85), name="GlobalSaveDataDefault")
        self.recorder.look()
        (event,) = self.events("settings_changed")
        self.assertEqual(event["changes"], [{"path": "blobs[0].masterVolume", "old": 60, "new": 85}])

    def test_a_save_caught_half_written_is_read_again(self):
        self.recorder.begin()
        index = self.profile / "containers.index"
        data = index.read_bytes()
        index.write_bytes(data[:20])
        self.assertFalse(self.recorder.look())
        self.assertTrue(self.recorder.retry)
        index.write_bytes(data)
        self.assertTrue(self.recorder.look())
        self.assertFalse(self.recorder.retry)

    def test_notes_and_the_game_starting_and_closing(self):
        self.recorder.begin()
        self.recorder.note("enchanted the bow")
        self.assertFalse(self.recorder.check_game([]))
        self.assertFalse(self.recorder.check_game(["Dungeons-WinGDK-Shipping.exe"]))
        self.assertFalse(self.recorder.check_game(["Dungeons-WinGDK-Shipping.exe"]))  # still running: nothing to say
        self.assertTrue(self.recorder.check_game([]))  # it just closed
        self.assertEqual([e["running"] for e in self.events("game")], [[], ["Dungeons-WinGDK-Shipping.exe"], []])
        self.assertIn("enchanted the bow", self.recorder.summary())

    def test_asks_what_unnamed_items_are_called_and_keeps_the_answers(self):
        self.recorder.begin()
        self.game_saves(lambda document: document["CharacterSaveV1"]["Inventory"]["Entries"].extend(
            [hero_item("SW.Item.Talisman.BrandNew", seed=501), hero_item("SW.Item.Artifact.HasteMushroom", seed=502), hero_item("SW.Item.AnotherNewThing", seed=503)]
        ))
        self.recorder.look()
        self.assertEqual(self.recorder.nameless(), ["SW.Item.AnotherNewThing", "SW.Item.Artifact.HasteMushroom", "SW.Item.Talisman.BrandNew"])
        names_file = self.dir / "item-names.json"
        names_file.write_text(json.dumps({"SW.Item.AnotherNewThing": "Already Named"}), encoding="utf-8")
        answers = iter(["Tempo Truffle", "   "])
        asked = []

        def ask(question):
            asked.append(question.strip())
            return next(answers)

        self.assertEqual(self.recorder.ask_names(ask, names_file), {"SW.Item.Artifact.HasteMushroom": "Tempo Truffle"})
        self.assertEqual(asked, ["SW.Item.Artifact.HasteMushroom =", "SW.Item.Talisman.BrandNew ="])  # not the one already named
        self.assertEqual(
            json.loads(names_file.read_text(encoding="utf-8")),
            {"SW.Item.AnotherNewThing": "Already Named", "SW.Item.Artifact.HasteMushroom": "Tempo Truffle"},
        )
        self.assertEqual(self.recorder.ask_names(lambda question: None, names_file), {})  # nobody there: stop asking

    def test_finds_whatever_a_save_says_about_a_storm(self):
        save = {
            "CharacterSaveV1": {
                "WorldExploration": {"SoulStormsCompleted": 2, "Areas": ["SW.Area.Forest", "SW.Area.Soulstorm.Plains"]},
                "Achievements": {"Counts": [{"Tag": "SW.Achievements.Defeat10Storminators", "Count": 4}, {"Tag": "SW.Achievements.Open100Chests", "Count": 9}]},
                "Inventory": {"Entries": [{"ItemData": {"TypeTag": "SW.Item.Sword", "DynamicPropertyTags": ["SW.Item.Property.Dynamic.SoulStorm"]}}]},
            }
        }
        self.assertEqual(play_recorder.storm_mentions(save), {
            "CharacterSaveV1.WorldExploration.SoulStormsCompleted": 2,  # a field named after one: what it holds
            "CharacterSaveV1.WorldExploration.Areas[] SW.Area.Soulstorm.Plains": True,  # a name in a list
            "CharacterSaveV1.Achievements.Counts[] {Tag: SW.Achievements.Defeat10Storminators}": {"Tag": "SW.Achievements.Defeat10Storminators", "Count": 4},
            "CharacterSaveV1.Inventory.Entries[].ItemData.DynamicPropertyTags[] SW.Item.Property.Dynamic.SoulStorm": True,
        })
        self.assertEqual(play_recorder.storm_mentions({"CharacterSaveV1": {"Inventory": {"Entries": []}}}), {})

    def test_the_soul_storm_check_says_what_turns_up(self):
        def before_recording(document):  # a Unique the hero already has, with a rolled effect more than usual
            old = hero_item("SW.Item.Sword_Unique1", rarity="Unique", seed=700, unseen=False)
            old["ItemData"]["Effects"] = [rolled(rolled_effect("Sharpness", 0.1, "I"), rolled_effect("Looting", 0.2, "I"))]
            document["CharacterSaveV1"]["Inventory"]["Entries"].append(old)

        self.game_saves(before_recording)
        self.recorder.begin()
        self.assertEqual((self.events("storm_baseline"), self.events("marked_item"), self.events("extra_effect")), ([], [], []))
        self.assertEqual([(about["id"], about["new"]) for about in self.recorder.extra.values()], [("SW.Item.Sword_Unique1", False)])

        def a_soul_storm(document):
            body = document["CharacterSaveV1"]
            chest = hero_item("SW.Item.Axe", rarity="Special", power=40, seed=701)  # from the reward chest: three effects, and a tag
            chest["ItemData"]["Effects"] = [rolled(rolled_effect("Sharpness", 0.1, "I"), rolled_effect("Looting", 0.2, "I"), rolled_effect("CriticalEdge", 0.1, "I"))]
            chest["ItemData"]["DynamicPropertyTags"].append("SW.Item.Property.Dynamic.SoulStorm")
            plain = hero_item("SW.Item.Mace", rarity="Special", seed=702)  # an ordinary drop
            plain["ItemData"]["Effects"] = [rolled(rolled_effect("Sharpness", 0.1, "I"))]
            reward = hero_item("SW.Item.GiantClub", rarity="Special", power=118, seed=703, unseen=False)  # as a real save holds one
            reward["ItemData"]["Effects"] = [rolled(rolled_effect("CriticalEdge", 0.1, "I"), rolled_effect("SweepingEdge", 0.2, "I"), rolled_effect("Knockback", 0.3, "III"))]
            reward["ItemData"]["DynamicPropertyTags"] = ["SW.Item.Property.StorminatorReward"]
            body["Inventory"]["Entries"] += [chest, plain, reward]
            body.setdefault("WorldExploration", {})["SoulStormsCompleted"] = 1

        self.game_saves(a_soul_storm)
        self.assertTrue(self.recorder.look())
        (marked,) = self.events("marked_item")
        self.assertEqual((marked["id"], marked["news"], marked["new"], marked["rolled"]),
                         ("SW.Item.Axe", ["mark SW.Item.Property.Dynamic.SoulStorm"], True, ["Sharpness.I", "Looting.I", "CriticalEdge.I"]))
        self.assertNotIn("PickupTimestamp", marked["as_saved"]["ItemData"])  # the whole item as saved, the way Share item IDs gives one
        self.assertEqual([e["id"] for e in self.events("extra_effect")], ["SW.Item.Axe", "SW.Item.GiantClub"])  # the Mace has no more than usual
        # Three things in the save mention a storm that didn't before: the counter, and the marks on the two items.
        storms = {storm["where"]: (storm["old"], storm["new"]) for storm in self.events("storm")}
        self.assertEqual(storms, {
            "CharacterSaveV1.WorldExploration.SoulStormsCompleted": ("(not there)", 1),
            "CharacterSaveV1.Inventory.Entries[].ItemData.DynamicPropertyTags[] SW.Item.Property.Dynamic.SoulStorm": ("(not there)", True),
            "CharacterSaveV1.Inventory.Entries[].ItemData.DynamicPropertyTags[] SW.Item.Property.StorminatorReward": ("(not there)", True),
        })
        self.assertTrue(any("AN ITEM SAVED WITH SOMETHING THE EDITOR HASN'T SEEN: Axe" in line for line in self.said))
        self.assertTrue(any("SOUL STORM IN THE SAVE: CharacterSaveV1.WorldExploration.SoulStormsCompleted" in line for line in self.said))
        self.assertTrue(any("new item: Axe" in line and "3 rolled effects (one more than usual)" in line for line in self.said))

        # The game's own mark for a Soul Storm reward is one the editor knows, so that item isn't news: it's listed
        # as Soulstorm Enhanced, and said so as it arrives.
        (reward,) = self.events("soulstorm_item")
        self.assertEqual((reward["id"], reward["marks"], reward["new"]), ("SW.Item.GiantClub", ["SW.Item.Property.StorminatorReward"], True))
        self.assertTrue(any("SOULSTORM ENHANCED: Clobberer" in line for line in self.said))
        self.assertTrue(any("new item: Clobberer" in line and "3 rolled effects (one more than usual), Soulstorm Enhanced" in line for line in self.said))

        # Nothing is asked: what the game shows as Soulstorm Enhanced is that mark, and the save has it or hasn't.
        self.assertFalse(hasattr(self.recorder, "ask_storm"))
        text = self.recorder.summary()
        self.assertIn("Soul Storm check:", text)
        self.assertIn("Places in the saves that mention a storm now (3):", text)
        self.assertIn("What changed there while recording (3):", text)
        self.assertIn("Items saved with a mark or a field the editor has never seen (1):", text)
        self.assertIn("SW.Item.Axe  Axe, Special: mark SW.Item.Property.Dynamic.SoulStorm  [arrived while recording]", text)
        self.assertIn("Soulstorm Enhanced items, by the game's mark for a Soul Storm reward (1):", text)
        self.assertIn("SW.Item.GiantClub  Clobberer, Special, power 118: CriticalEdge.I, SweepingEdge.I, Knockback.III  [arrived while recording]", text)
        self.assertIn("Items with one more rolled effect than their rarity usually has (3):", text)
        self.assertIn("SW.Item.Sword_Unique1  The Burning Blade, Unique, power 1: Sharpness.I, Looting.I; marks: none", text)
        self.assertNotIn("you said", text)

        # Salvaged afterwards: what it looked like is kept, and it isn't asked about any more.
        self.game_saves(lambda document: document["CharacterSaveV1"]["Inventory"]["Entries"].__setitem__(
            slice(None), [e for e in document["CharacterSaveV1"]["Inventory"]["Entries"] if e["ItemData"]["TypeTag"] != "SW.Item.Axe"]))
        self.recorder.look()
        self.assertIn("gone again", self.recorder.summary())
        self.assertEqual(len(self.events("storm")), 4)  # the mark went with it, which is a change in what the save says about storms

    def test_tracks_world_progress_step_by_step(self):
        def a_hero_partway(document):
            body = document["CharacterSaveV1"]
            body["MetaData"]["CurrentLocation"] = "SW.Area.Town"
            body["quest"] = {"FocusedQuestId": "CA01", "Quests": [
                {"QuestName": "CA00", "State": "Completed", "TaskData": [{"TaskName": "CA00_E01", "State": "Completed", "PartialProgress": 0}]},
                {"QuestName": "CA01", "State": "Active", "TaskData": [
                    {"TaskName": "CA01_E01", "State": "Active", "PartialProgress": 0}, {"TaskName": "CA01_E02", "State": "NotSet", "PartialProgress": 0}]},
            ]}
            body["WorldExploration"] = {
                "DiscoveredMinecartStationTags": ["SW.MinecartStation.Town"], "LastMinecartStation": "SW.MinecartStation.Town", "SavedCutsceneTags": [],
                "DiscoveredDungeonDoors": [{"DoorId": "SW.Doorway.Camp.Docks", "MarkerType": 7, "Location": {"X": 4800, "Y": 1600, "Z": 3}}],
                "SavedFogOfWarExploration": {"Items": [{"Tag": "SW.Region.Camp", "Data": [0, 3, 0, 1], "WorldPosition": {"X": 0, "Y": 0}, "Size": {"X": 2, "Y": 2}}]},
            }
            body["Achievements"] = {"QuestAchievements": {"SW.Achievements.CompleteCA01": {"bCompleted": False}},
                                    "CountAchievements": {"SW.Achievements.Open100Chests": {"Count": 3}}}

        self.game_saves(a_hero_partway)
        self.recorder.begin()
        (baseline,) = self.events("progress_baseline")
        progress = baseline["progress"]
        self.assertEqual((progress["quest CA00"], progress["quest CA01"], progress["task CA01_E01"], progress["quest in focus"]), ("Completed", "Active", "Active", "CA01"))
        self.assertEqual((progress["minecart station SW.MinecartStation.Town"], progress["door SW.Doorway.Camp.Docks"], progress["explored SW.Region.Camp"]), (True, "marker 7", "2 of 4"))
        self.assertEqual((progress["achievement CompleteCA01"], progress["achievement Open100Chests"]), (False, 3))
        self.assertTrue(any("World progress: quests: 1 active, 1 completed; tasks done: 1 of 3; 1 minecart stations, 1 doors, 0 cutscenes" in line for line in self.said))

        def a_step(document):
            body = document["CharacterSaveV1"]
            tasks = body["quest"]["Quests"][1]["TaskData"]
            tasks[0].update(State="Completed", PartialProgress=1)
            tasks[1]["State"] = "Active"
            world = body["WorldExploration"]
            world["DiscoveredMinecartStationTags"].append("SW.MinecartStation.PlainsA1.Barn")
            world["SavedCutsceneTags"].append("SW.UI.Cutscene.Cutscenes.CS02")
            world["SavedFogOfWarExploration"]["Items"][0]["Data"][0] = 1
            body["Achievements"]["CountAchievements"]["SW.Achievements.Open100Chests"]["Count"] = 4

        self.game_saves(a_step)
        self.recorder.look()
        steps = {event["what"]: (event["old"], event["new"]) for event in self.events("progress")}
        self.assertEqual(steps, {
            "task CA01_E01": ("Active", "Completed (1)"), "task CA01_E02": ("NotSet", "Active"),
            "minecart station SW.MinecartStation.PlainsA1.Barn": ("(not there)", True), "cutscene SW.UI.Cutscene.Cutscenes.CS02": ("(not there)", True),
            "explored SW.Region.Camp": ("2 of 4", "3 of 4"), "achievement Open100Chests": (3, 4),
        })
        # The steps that say how far the hero has got are said out loud; counters and explored ground only go in the file.
        self.assertTrue(any("PROGRESS: task CA01_E01: Active -> Completed (1)" in line for line in self.said))
        self.assertTrue(any("PROGRESS: minecart station SW.MinecartStation.PlainsA1.Barn: (not there) -> True" in line for line in self.said))
        self.assertFalse(any("Open100Chests" in line or "explored" in line for line in self.said if "PROGRESS" in line))
        # A chest, though: the game's own count of chests opened went up, which is all a save says about one.
        (chest,) = self.events("chest")
        self.assertEqual((chest["opened"], chest["count"], chest["area"], chest["near"]["x"]), (1, 4, "SW.Area.Town", 48))
        self.assertTrue(any("CHEST OPENED: 1 more, 4 by the game's count  [in SW.Area.Town, near 48, 16]" in line for line in self.said))
        text = self.recorder.summary()
        self.assertIn("World progress:", text)
        self.assertIn("Now: quests: 1 active, 1 completed; tasks done: 2 of 3; 2 minecart stations, 1 doors, 1 cutscenes", text)
        self.assertIn("Steps while recording (4, and 2 quieter changes in events.jsonl):", text)
        self.assertIn("Chests opened while recording: 1 (1 in SW.Area.Town)", text)
        self.assertIn("task CA01_E01: \"Active\" -> \"Completed (1)\"", text)

        # The atlas: everything every recording has shown, with a quest's tasks in the save's order and the order
        # they were completed in.
        atlas = play_recorder.build_atlas(self.dir)  # the recorder writes into self.dir / "play"
        self.assertEqual(atlas["snapshots"], 2)
        self.assertEqual(atlas["quests"]["CA01"], {
            "states": ["Active"], "tasks": ["CA01_E01", "CA01_E02"], "completed_in_order": ["CA01_E01"],
            "task_states": {"CA01_E01": ["Active", "Completed (1)"], "CA01_E02": ["NotSet", "Active"]},
        })
        self.assertEqual(atlas["minecart_stations"], ["SW.MinecartStation.Town", "SW.MinecartStation.PlainsA1.Barn"])
        # Where things are. A door's place is the save's own, in metres; a square of a region's picture is 32 metres,
        # so the station turned up near the middle of the square that cleared in that save: the first of the top
        # line, which is the far side in X and the near side in Y.
        self.assertEqual(atlas["doors"], {"SW.Doorway.Camp.Docks": {
            "metres": [48.0, 16.0, 0.0], "region": "SW.Region.Camp", "MarkerType": 7, "Location": {"X": 4800, "Y": 1600, "Z": 3}}})
        found = atlas["found_at"]["minecart station SW.MinecartStation.PlainsA1.Barn"]
        self.assertEqual((found["area"], found["near"], found["region"], found["recording"]), ("SW.Area.Town", [48, 16], "SW.Region.Camp", "play"))
        self.assertEqual(atlas["map"]["regions"]["SW.Region.Camp"]["cells"], [1, 3, 0, 1])  # every square any save shows explored
        station = next(event for event in self.events("progress") if event["what"].startswith("minecart station"))
        self.assertEqual((station["area"], station["near"]), ("SW.Area.Town", {"region": "SW.Region.Camp", "squares": 1, "x": 48, "y": 16}))
        self.assertTrue(any("-> True  [in SW.Area.Town, near 48, 16]" in line for line in self.said))
        drawn = play_recorder.text_map(atlas)
        self.assertIn("SW.Region.Camp  (2 squares across, 2 down; 3 explored)", drawn)
        self.assertIn("  A  SW.Doorway.Camp.Docks  at 48, 16", drawn)
        self.assertIn("  2  cutscene SW.UI.Cutscene.Cutscenes.CS02  near 48, 16", drawn)
        self.assertEqual([(chest["opened"], chest["count"], chest["area"], chest["near"]) for chest in atlas["chests"]], [(1, 4, "SW.Area.Town", [48, 16])])
        self.assertIn("  $  a chest opened (1 in this region with a spot to show)", drawn)
        self.assertIn("Chests opened, by the area you were in:\n  SW.Area.Town: 1", drawn)
        # The same, for this hero alone, is what its map in the editor takes: what has a spot, and the chests.
        mine = atlas["heroes"]["00000000-0000-1000-8000-000000000002"]
        self.assertEqual((mine["saves"], sorted(mine["found_at"]), mine["chests"]), (
            2, ["cutscene SW.UI.Cutscene.Cutscenes.CS02", "minecart station SW.MinecartStation.PlainsA1.Barn"], atlas["chests"]))
        self.assertEqual(play_recorder.newly_explored({}, {}), None)
        self.assertEqual(play_recorder.region_of(48, 16, atlas["map"]["regions"]), "SW.Region.Camp")
        self.assertEqual(atlas["areas"]["SW.Region.Camp"]["most_explored"], 3)
        self.assertEqual((atlas["cutscenes"], atlas["locations"]), (["SW.UI.Cutscene.Cutscenes.CS02"], ["SW.Area.Town"]))

    def test_values_too_long_for_an_event_are_cut_short(self):
        self.assertEqual(play_recorder.compact([1, 2]), [1, 2])
        long = play_recorder.compact(["x" * 50] * 20)
        self.assertTrue(long.endswith("characters)") and len(long) < play_recorder.LONG + 40)
        self.assertEqual(play_recorder.path_text(("ItemData", "Effects", 0, "Tier")), "ItemData.Effects[0].Tier")


def a_save(hero="hero-1", where="SW.Area.Town", chests=None, regions=(), doors=(), quests=(), stations=()):
    """A hero save with only what the map and world progress read. A region is (tag, corner X, corner Y, squares
    across, squares down, the squares); a door (name, X, Y) in metres; a quest (name, state, [(step, state)])."""
    body = {
        "MetaData": {"CharacterId": hero, "CurrentLocation": where},
        "quest": {"Quests": [{"QuestName": name, "State": state, "TaskData": [{"TaskName": step, "State": how, "PartialProgress": 0} for step, how in steps]} for name, state, steps in quests]},
        "WorldExploration": {
            "DiscoveredMinecartStationTags": list(stations),
            "DiscoveredDungeonDoors": [{"DoorId": name, "MarkerType": 8, "Location": {"X": x * 100, "Y": y * 100, "Z": 0}} for name, x, y in doors],
            "SavedFogOfWarExploration": {"Items": [{"Tag": tag, "WorldPosition": {"X": x, "Y": y}, "Size": {"X": across, "Y": down}, "Data": list(data)} for tag, x, y, across, down, data in regions]},
        },
    }
    if chests is not None:
        body["Achievements"] = {"CountAchievements": {"SW.Achievements.Open100Chests": {"Count": chests}}}
    return {"CharacterSaveV1": body}


class MapTests(unittest.TestCase):
    """How a save's pictures of the fog lie on the world, and what the recordings' atlas makes of them."""

    MEADOW = "SW.Area.Meadow.R9"

    def meadow(self, *squares):
        return a_save(regions=[(self.MEADOW, 320, 640, 3, 2, squares)])

    def test_a_regions_picture_lies_the_way_the_games_own_map_does(self):
        # Three squares to a line, two lines. The first line is the far side in X, and a line runs with Y.
        regions = play_recorder.map_regions(self.meadow(0, 0, 200, 9, 0, 0))
        region = regions[self.MEADOW]
        self.assertEqual((region["across"], region["down"], region["shift"]), (3, 2, [0, 0]))
        self.assertEqual(play_recorder.spot_of(region, 2.5, 0.5), (368, 720))  # the clear square: far in X, far in Y
        self.assertEqual(play_recorder.square_of(region, 368, 720), (2.5, 0.5))
        self.assertEqual(play_recorder.spot_of(region, 0, 2), (320, 640))  # the bottom left is the corner the save gives
        self.assertEqual(play_recorder.region_of(368, 720, regions), self.MEADOW)
        self.assertIsNone(play_recorder.region_of(390, 720, regions))  # past the top line
        self.assertEqual(play_recorder.frontier(region), [0, 1, 4, 5])  # never seen, right next to what has been
        self.assertEqual(play_recorder.frontier({**region, "cells": [0] * 6}), [])
        # A picture is as many squares as its size says, whatever the save holds for it: none missing, none over.
        odd = play_recorder.map_regions(a_save(regions=[("short", 0, 0, 2, 2, [5, 6]), ("long", 0, 0, 1, 2, [5, 6, 7]), ("none", 0, 0, 0, -3, [1])]))
        self.assertEqual([(region["across"], region["down"], region["cells"]) for region in odd.values()], [(2, 2, [5, 6, 0, 0]), (1, 2, [5, 6]), (0, 0, [])])
        self.assertEqual((play_recorder.frontier(odd["short"]), play_recorder.frontier(odd["none"])), ([2, 3], []))
        # The overworld's picture lies three squares lower and half a square to the right of where its corner says.
        overworld = play_recorder.map_regions(a_save(regions=[("SW.Region.Overworld", -608, -192, 52, 52, [0] * 2704)]))["SW.Region.Overworld"]
        self.assertEqual(play_recorder.square_of(overworld, 960, -176), (0, 0))
        self.assertEqual(play_recorder.spot_of(overworld, 0, 0), (960, -176))
        # A region inside another: a spot in both is in the smaller.
        both = {**regions, "SW.Region.Overworld": overworld}
        self.assertEqual((play_recorder.region_of(368, 720, both), play_recorder.region_of(100, 100, both)), (self.MEADOW, "SW.Region.Overworld"))
        # The colour of a square: the clearer its fog the greener, and an unseen one next to a seen one stands out.
        self.assertEqual([play_recorder.clarity_colour(0), play_recorder.clarity_colour(0, True), play_recorder.clarity_colour(255)], ["#16303f", "#3c5f78", "#5d8a66"])
        self.assertNotIn(play_recorder.clarity_colour(40), ("#16303f", "#5d8a66"))

    def test_where_the_hero_went_is_the_middle_of_the_fog_that_cleared(self):
        before = play_recorder.map_regions(self.meadow(0, 0, 200, 9, 0, 0))
        self.assertIsNone(play_recorder.newly_explored(before, before))
        after = play_recorder.map_regions(self.meadow(0, 100, 200, 9, 0, 0))
        self.assertEqual(play_recorder.newly_explored(before, after), {"region": self.MEADOW, "squares": 1, "x": 368, "y": 688})
        # Two squares cleared, one more than the other: nearer the one that cleared more.
        after = play_recorder.map_regions(self.meadow(0, 100, 255, 9, 0, 0))
        self.assertEqual(play_recorder.newly_explored(before, after), {"region": self.MEADOW, "squares": 2, "x": 368, "y": 699})
        # Fog that got no clearer says nothing, and a region the save before didn't have counts from nothing.
        self.assertEqual(play_recorder.newly_explored({}, before)["squares"], 2)
        # Stepping into a region inside the overworld clears a patch of both pictures: the hero is in the smaller.
        outside = ("SW.Region.Overworld", -608, -192, 52, 52, [0] * 2704)
        was = play_recorder.map_regions(a_save(regions=[outside, (self.MEADOW, 320, 640, 3, 2, [0] * 6)]))
        now = play_recorder.map_regions(a_save(regions=[outside[:5] + ([0] * 100 + [210] + [0] * 2603,), (self.MEADOW, 320, 640, 3, 2, [0, 0, 200, 0, 0, 0])]))
        self.assertEqual(play_recorder.newly_explored(was, now)["region"], self.MEADOW)
        now = play_recorder.map_regions(a_save(regions=[outside[:5] + ([0] * 100 + [210, 250] + [0] * 2602,), (self.MEADOW, 320, 640, 3, 2, [0, 0, 200, 0, 0, 0])]))
        self.assertEqual(play_recorder.newly_explored(was, now)["region"], "SW.Region.Overworld")  # far more cleared out there

    def test_what_may_have_been_missed_is_said_in_the_games_own_names(self):
        document = a_save(
            quests=[("CA02", "Completed", [("CA02_E01", "Completed")]), ("CA02_B", "Active", [("CA02_B_E01", "Completed"), ("CA02_B_E02", "Active")]),
                    ("CA02_B_BR", "Available", [("CA02_B_BR_E01", "NotSet")]), ("CA04", "Active", [("CA04_E01", "NotSet")])],
            stations=["SW.MinecartStation.Town", "SW.MinecartStation.ForestA1.Outpost"],
            doors=[("SW.Doorway.ForestA1.Dungeon.1", 0, 0), ("SW.Doorway.ForestA1.Dungeon.7", 0, 0), ("SW.Doorway.PlainsA1.Rift.2", 0, 0),
                   ("SW.Doorway.SwampB2.Rift.1", 0, 0), ("SW.Doorway.TownA1.Docks", 0, 0)],
            regions=[(self.MEADOW, 320, 640, 3, 2, [0, 0, 200, 9, 0, 0])],
        )
        progress = play_recorder.world_progress(document)
        # A step is its quest's alone: CA02_B's steps start the way CA02's do, and CA02_B_BR's the way CA02_B's do.
        self.assertEqual(play_recorder.quest_tasks(progress), {"CA02": ["Completed"], "CA02_B": ["Completed", "Active"], "CA02_B_BR": ["NotSet"], "CA04": ["NotSet"]})
        lines = play_recorder.might_be_missing(progress, play_recorder.map_regions(document))
        self.assertEqual(lines[:5], [
            "Howling Woods: 2 of its 12 dungeon spots found", "Honeycomb Fields: 1 of its 8 rift spots found", "SwampB2: 1 rift spot found",
            "(The game opens only a few of an area's dungeon and rift spots at a time, so one you haven't found may not be open yet.)",
            "Minecart stations: 2 found of at least 19",
        ])
        # The Town Fountain isn't among them: a hero starts there, and no save lists it as a station found.
        self.assertTrue(lines[5].startswith(
            "Stations not found yet: Honeycomb Farm, Honeybrook Bridge (Honeycomb Fields); "
            "Deep Dark Entrance, Hidden Grove, Woodcutter's Outpost (Howling Woods); Monsoon Banks,"))
        self.assertNotIn("Town Fountain", lines[5])
        # A station by the game's name where MetaBot's map has it, however the game spells its tag, and otherwise
        # by what a save calls it, set out to be read.
        self.assertEqual(
            [play_recorder.station_name("SW.MinecartStation." + key) for key in ("PlainsA1.Barn", "Forest.A1.DangerZone", "Town.Fountain", "DesertA1.TaigaBeach", "CarapaceA1.North", "Somewhere")],
            ["Honeycomb Farm", "Woodcutter's Outpost", "Town Fountain", "Taiga Beach (Frozen Highlands)", "North (Carapace A1)", "Somewhere"],
        )
        self.assertEqual(lines[6:], [
            "Quest CA02_B (Corruption in the Woods): 1 of 2 steps left", "Quest CA02_B_BR: not started", "Quest CA04 (The Missing Note Blocks): 1 of 1 steps left",
            f"{self.MEADOW}: 4 unexplored squares right next to the 2 you've explored (marked on the map)",
        ])
        self.assertEqual([play_recorder.area_name(tag) for tag in ("SW.Area.Town", "SW.Area.Plains.A1", "SW.Area.Forest.A1.SpiderCaves.3", "SW.Area.Meadow.R1")],
                         ["Brave Haven", "Honeycomb Fields", "Howling Woods: SpiderCaves.3", "Meadow.R1"])
        self.assertEqual((play_recorder.station_name("SW.MinecartStation.ForestA1.Outpost"), play_recorder.station_name("SW.MinecartStation.Moon.Base")), ("Little Howl Hamlet", "Base (Moon)"))
        self.assertEqual((play_recorder.quest_name("CA04"), play_recorder.quest_name("XX09")), ("CA04 (The Missing Note Blocks)", "XX09"))
        self.assertEqual(play_recorder.hero_id(document), "hero-1")

    def test_the_atlas_keeps_each_heros_finds_apart_and_gives_no_place_across_a_gap(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        out = Path(temp.name)

        def recorded(recording, name, document):
            folder = out / recording / "snapshots"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(json.dumps(document), encoding="utf-8")

        self.assertIsNone(play_recorder.fresh_atlas(out))  # no recordings: nothing to say, and nothing written
        self.assertEqual(list(out.iterdir()), [])
        town, station = "SW.MinecartStation.Town", "SW.MinecartStation.ForestA1.Outpost"
        recorded("2026-10-01_10-00-00", "0001_A.json", a_save("A", chests=3, regions=[(self.MEADOW, 320, 640, 3, 2, [0] * 6)]))
        recorded("2026-10-01_10-00-00", "0002_B.json", a_save("B", chests=0, regions=[(self.MEADOW, 320, 640, 3, 2, [0] * 6)]))
        recorded("2026-10-01_10-00-00", "0003_A.json", a_save("A", chests=4, stations=[town], regions=[(self.MEADOW, 320, 640, 3, 2, [0, 200, 0, 0, 0, 0])]))
        recorded("2026-10-01_10-00-00", "0004_B.json", a_save("B", chests=1, where="SW.Area.Forest.A1", regions=[(self.MEADOW, 320, 640, 3, 2, [0] * 6)]))
        # The next day the count has gone up by two and a station is there that wasn't: found while nothing recorded.
        recorded("2026-10-02_10-00-00", "0001_A.json", a_save("A", chests=6, stations=[town, station], regions=[(self.MEADOW, 320, 640, 3, 2, [9, 200, 0, 0, 0, 0])]))
        recorded("2026-10-02_10-00-00", "0002_A.json", a_save("A", chests=7, stations=[town, station], regions=[(self.MEADOW, 320, 640, 3, 2, [9, 200, 0, 0, 0, 50])]))
        atlas = play_recorder.fresh_atlas(out)
        self.assertEqual((atlas["format"], atlas["snapshots"], sorted(atlas["heroes"])), (play_recorder.ATLAS_FORMAT, 6, ["A", "B"]))
        mine, other = atlas["heroes"]["A"], atlas["heroes"]["B"]
        self.assertEqual((mine["saves"], other["saves"]), (4, 2))
        self.assertEqual([(chest["opened"], chest["count"], chest["area"], chest["near"], chest["region"]) for chest in mine["chests"]], [
            (1, 4, "SW.Area.Town", [368, 688], self.MEADOW), (2, 6, None, None, None), (1, 7, "SW.Area.Town", [336, 720], self.MEADOW)])
        self.assertEqual([(chest["opened"], chest["area"], chest["near"]) for chest in other["chests"]], [(1, "SW.Area.Forest.A1", None)])  # no fog cleared: no spot
        self.assertEqual(len(atlas["chests"]), 4)  # everyone's, for the map of all the recordings
        self.assertEqual(play_recorder.chests_by_area(mine["chests"]), {"SW.Area.Town": 2, play_recorder.BETWEEN: 2})
        # The station found with the recorder on has a spot; the one found between two recordings has none.
        self.assertEqual(list(mine["found_at"]), [f"minecart station {town}"])
        self.assertEqual((mine["found_at"][f"minecart station {town}"]["near"], atlas["found_at"][f"minecart station {station}"]["near"]), ([368, 688], None))
        self.assertEqual(atlas["map"]["regions"][self.MEADOW]["cells"], [9, 200, 0, 0, 0, 50])  # each square as clear as any save has it
        self.assertIn("  while nothing was recording: 2", play_recorder.text_map(atlas))

        # It's written down, and read again only when a recording is newer than what was written, or was written the old way.
        written = out / "world_progress_atlas.json"
        self.assertEqual(json.loads(written.read_text(encoding="utf-8"))["heroes"], atlas["heroes"])
        with mock.patch.object(play_recorder, "write_atlas", wraps=play_recorder.write_atlas) as write:
            self.assertEqual(play_recorder.fresh_atlas(out)["snapshots"], 6)
            write.assert_not_called()
            recorded("2026-10-02_10-00-00", "0003_A.json", a_save("A", chests=7, regions=[(self.MEADOW, 320, 640, 3, 2, [9, 200, 0, 0, 0, 50])]))
            later = written.stat().st_mtime + 30
            os.utime(out / "2026-10-02_10-00-00" / "snapshots", (later, later))
            self.assertEqual(play_recorder.fresh_atlas(out)["snapshots"], 7)
            self.assertEqual(write.call_count, 1)
            os.utime(written, (later + 30, later + 30))
            written.write_text(json.dumps({"format": 2, "snapshots": 7}), encoding="utf-8")
            os.utime(written, (later + 30, later + 30))
            self.assertIn("heroes", play_recorder.fresh_atlas(out))
            self.assertEqual(write.call_count, 2)
        self.assertEqual(play_recorder.load_atlas(out / "nowhere"), None)


if __name__ == "__main__":
    unittest.main()
