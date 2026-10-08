import copy
import json
import tempfile
import unittest
from pathlib import Path

from dungeons2_editor import recorder as play_recorder
from dungeons2_editor import saves

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
        self.assertIn("The game saved 1 time(s)", text)
        self.assertIn("Item IDs first seen while recording (2):", text)
        self.assertIn("changed  SW.Item.Longbow  ItemData.Effects[0]", text)
        self.assertIn("Emeralds: 55 -> 300 in 1 step(s)", text)
        self.assertEqual(self.recorder.write_summary().read_text(encoding="utf-8"), text)

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

    def test_the_soul_storm_check_says_what_turns_up_and_asks_about_it(self):
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
            body["Inventory"]["Entries"] += [chest, plain]
            body.setdefault("WorldExploration", {})["SoulStormsCompleted"] = 1

        self.game_saves(a_soul_storm)
        self.assertTrue(self.recorder.look())
        (marked,) = self.events("marked_item")
        self.assertEqual((marked["id"], marked["news"], marked["new"], marked["rolled"]),
                         ("SW.Item.Axe", ["mark SW.Item.Property.Dynamic.SoulStorm"], True, ["Sharpness.I", "Looting.I", "CriticalEdge.I"]))
        self.assertNotIn("PickupTimestamp", marked["as_saved"]["ItemData"])  # the whole item as saved, the way Share item IDs gives one
        self.assertEqual([e["id"] for e in self.events("extra_effect")], ["SW.Item.Axe"])  # the Mace has no more than usual
        # Two things in the save mention a storm that didn't before: the counter, and the mark on the Axe.
        storms = {storm["where"]: (storm["old"], storm["new"]) for storm in self.events("storm")}
        self.assertEqual(storms, {
            "CharacterSaveV1.WorldExploration.SoulStormsCompleted": ("(not there)", 1),
            "CharacterSaveV1.Inventory.Entries[].ItemData.DynamicPropertyTags[] SW.Item.Property.Dynamic.SoulStorm": ("(not there)", True),
        })
        self.assertTrue(any("AN ITEM SAVED WITH SOMETHING THE EDITOR HASN'T SEEN: Axe" in line for line in self.said))
        self.assertTrue(any("SOUL STORM IN THE SAVE: CharacterSaveV1.WorldExploration.SoulStormsCompleted" in line for line in self.said))
        self.assertTrue(any("new item: Axe" in line and "3 rolled effects (one more than usual)" in line for line in self.said))

        # At the end it asks about each of them, what arrived while recording first.
        self.assertEqual([about["id"] for _key, about in self.recorder.storm_questions()], ["SW.Item.Axe", "SW.Item.Sword_Unique1"])
        answers = iter(["Y", "n"])
        asked = []

        def ask(question):
            asked.append(question.strip())
            return next(answers)

        given = self.recorder.ask_storm(ask)
        self.assertEqual(sorted(given.values()), ["no", "yes"])
        self.assertEqual(asked[0], "Axe (Special, power 40, effects: Sharpness.I, Looting.I, CriticalEdge.I) =")
        self.assertEqual([(e["id"], e["shows_soulstorm_enhanced"]) for e in self.events("storm_answer")], [("SW.Item.Axe", "yes"), ("SW.Item.Sword_Unique1", "no")])
        self.assertEqual(self.recorder.storm_questions(), [])  # nothing is asked twice
        self.assertEqual(self.recorder.ask_storm(lambda question: self.fail("asked again")), {})

        text = self.recorder.summary()
        self.assertIn("Soul Storm check:", text)
        self.assertIn("Places in the saves that mention a storm now (2):", text)
        self.assertIn("What changed there while recording (2):", text)
        self.assertIn("Items saved with a mark or a field the editor has never seen (1):", text)
        self.assertIn("SW.Item.Axe  Axe, Special: mark SW.Item.Property.Dynamic.SoulStorm  [arrived while recording; Soulstorm Enhanced in the game, you said: yes]", text)
        self.assertIn("Items with one more rolled effect than their rarity usually has (2):", text)
        self.assertIn("SW.Item.Sword_Unique1  The Burning Blade, Unique, power 1: Sharpness.I, Looting.I; marks: none  [Soulstorm Enhanced in the game, you said: no]", text)

        # Salvaged afterwards: what it looked like is kept, and it isn't asked about any more.
        self.game_saves(lambda document: document["CharacterSaveV1"]["Inventory"]["Entries"].__setitem__(
            slice(None), [e for e in document["CharacterSaveV1"]["Inventory"]["Entries"] if e["ItemData"]["TypeTag"] != "SW.Item.Axe"]))
        self.recorder.look()
        self.assertIn("gone again", self.recorder.summary())
        self.assertEqual(len(self.events("storm")), 3)  # the mark went with it, which is a change in what the save says about storms

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
        text = self.recorder.summary()
        self.assertIn("World progress:", text)
        self.assertIn("Now: quests: 1 active, 1 completed; tasks done: 2 of 3; 2 minecart stations, 1 doors, 1 cutscenes", text)
        self.assertIn("Steps while recording (4, and 2 quieter changes in events.jsonl):", text)
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
        # Where things are. A door's place is the save's own, in metres; a square of explored ground is 32 metres,
        # so the station turned up near the middle of the square explored in that save (the top left one).
        self.assertEqual(atlas["doors"], {"SW.Doorway.Camp.Docks": {
            "metres": [48.0, 16.0, 0.0], "region": "SW.Region.Camp", "MarkerType": 7, "Location": {"X": 4800, "Y": 1600, "Z": 3}}})
        found = atlas["found_at"]["minecart station SW.MinecartStation.PlainsA1.Barn"]
        self.assertEqual((found["area"], found["near"], found["region"], found["recording"]), ("SW.Area.Town", [16, 16], "SW.Region.Camp", "play"))
        self.assertEqual(atlas["map"]["regions"]["SW.Region.Camp"]["cells"], [1, 3, 0, 1])  # every square any save shows explored
        station = next(event for event in self.events("progress") if event["what"].startswith("minecart station"))
        self.assertEqual((station["area"], station["near"]), ("SW.Area.Town", {"region": "SW.Region.Camp", "squares": 1, "x": 16, "y": 16}))
        self.assertTrue(any("-> True  [in SW.Area.Town, near 16, 16]" in line for line in self.said))
        drawn = play_recorder.text_map(atlas)
        self.assertIn("SW.Region.Camp  (corner 0, 0; 2 by 2 squares; 3 explored)", drawn)
        self.assertIn("  A  SW.Doorway.Camp.Docks  at 48, 16", drawn)
        self.assertIn("  2  cutscene SW.UI.Cutscene.Cutscenes.CS02  near 16, 16", drawn)
        self.assertEqual(play_recorder.newly_explored({}, {}), None)
        self.assertEqual(play_recorder.region_of(48, 16, atlas["map"]["regions"]), "SW.Region.Camp")
        self.assertEqual(atlas["areas"]["SW.Region.Camp"]["most_explored"], 3)
        self.assertEqual((atlas["cutscenes"], atlas["locations"]), (["SW.UI.Cutscene.Cutscenes.CS02"], ["SW.Area.Town"]))

    def test_values_too_long_for_an_event_are_cut_short(self):
        self.assertEqual(play_recorder.compact([1, 2]), [1, 2])
        long = play_recorder.compact(["x" * 50] * 20)
        self.assertTrue(long.endswith("characters)") and len(long) < play_recorder.LONG + 40)
        self.assertEqual(play_recorder.path_text(("ItemData", "Effects", 0, "Tier")), "ItemData.Effects[0].Tier")


if __name__ == "__main__":
    unittest.main()
