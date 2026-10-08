import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import tests
from dungeons2_editor import world

from .helpers import hero_save, hero_with_a_world

HERO_ID = "00000000-0000-1000-8000-000000000002"
TOLD = [
    "quest CA04 - Active; steps: E01+, E02~",
    "quest FOa1_S10_A - Available; steps: E01",
    "door SW.Doorway.ForestA1.Dungeon.1 - at 16, 16, 0; marker 8",
    "door SW.Doorway.MeadowR1.ForestA1 - at 1040, 1040, 0; marker 7",
    "station SW.MinecartStation.ForestA1.Outpost - Little Howl Hamlet",
    "region SW.Area.Meadow.R1 - corner 1000, 1000; 2 across, 2 down; fog AAcAAA==",
    "cutscene SW.UI.Cutscene.Cutscenes.CS01",
    "area SW.Area.Forest.A1 - Howling Woods",
    "achievement SW.Achievements.CompleteWobbleRunQuest - QuestAchievements",
    "achievement SW.Achievements.CompleteCarapaceSideQuest - QuestAchievements",
    "achievement SW.Achievements.EquipAUniqueItem - BoolAchievements",
    "achievement SW.Achievements.DiscoverAllMinecartStations - CollectionAchievements",
    "achievement SW.Achievements.Open100Chests - CountAchievements",
]


def recordings():
    """What a play recorder's atlas holds that a shared list tells: the areas the hero was saved in, where a station
    turned up, and the chests opened (two with a spot, one between two recordings, three in a cave with no spot)."""
    spot = {"area": "SW.Area.Forest.A1", "near": [48.4, 47.6], "region": "SW.Region.Camp", "recording": "2026-10-01_10-00-00", "snapshot": "0002_Character.json"}
    return {
        "locations": ["SW.Area.Town", "SW.Area.Forest.A1", "SW.Area.DeepDark.A1"],
        "found_at": {
            "minecart station SW.MinecartStation.ForestA1.Outpost": spot, "task CA01_E01": spot, "quest CA04": spot,
            "cutscene SW.UI.Cutscene.Cutscenes.CS01": {**spot, "near": None, "region": None},
        },
        "chests": [
            {"opened": 2, "count": 4, **spot}, {"opened": 1, "count": 5, "area": None, "near": None, "region": None},
            {"opened": 3, "count": 8, "area": "SW.Area.DeepDark.A1", "near": None, "region": None},
        ],
        "heroes": {HERO_ID: {"saves": 3}},
    }


class WorldListTests(unittest.TestCase):
    """What a save shows of the game's world that the editor's list of it doesn't have, as a shared list tells it."""

    def test_tells_what_a_save_shows_that_the_list_lacks(self):
        self.assertEqual(world.lines([hero_save()]), [])  # a hero in town who has met nobody: nothing the list lacks
        self.assertEqual(world.keys([hero_save()]), set())
        told = world.lines([hero_with_a_world()])
        self.assertEqual(told, [world.SAVES_HEADER] + TOLD)
        # The quest, the station, the door and the region the list has aren't told again.
        self.assertFalse([line for line in told if "CA01" in line or "MinecartStation.Town" in line or "Camp" in line])
        # A key for each, which is how the editor counts what's new in your saves.
        self.assertEqual(world.keys([hero_with_a_world()]), {
            "world quest CA04", "world quest FOa1_S10_A", "world door SW.Doorway.ForestA1.Dungeon.1", "world door SW.Doorway.MeadowR1.ForestA1",
            "world station SW.MinecartStation.ForestA1.Outpost", "world region SW.Area.Meadow.R1", "world cutscene SW.UI.Cutscene.Cutscenes.CS01",
            "world area SW.Area.Forest.A1", "world achievement SW.Achievements.CompleteWobbleRunQuest", "world achievement SW.Achievements.CompleteCarapaceSideQuest",
            "world achievement SW.Achievements.EquipAUniqueItem", "world achievement SW.Achievements.DiscoverAllMinecartStations",
            "world achievement SW.Achievements.Open100Chests",
        })
        # Two heroes: what either shows, once.
        self.assertEqual(world.lines([hero_with_a_world(), hero_save(), hero_with_a_world()]), told)

    def test_tells_how_a_quest_stands_and_what_differs_from_the_list(self):
        document = hero_with_a_world()
        body = document["CharacterSaveV1"]
        steps = body["quest"]["Quests"][0]["TaskData"]  # CA01, which the list has with one step
        steps[0]["PartialProgress"] = 3
        steps += [{"TaskName": "CA01_E02", "State": "Failed", "PartialProgress": 0}, {"TaskName": "Elsewhere_K01", "State": "Active", "PartialProgress": 2}]
        body["WorldExploration"]["DiscoveredDungeonDoors"][0]["Location"] = {"X": 4800, "Y": 9950, "Z": 0}  # the docks, 19.5 metres from where the list has them
        body["WorldExploration"]["SavedFogOfWarExploration"]["Items"][0]["Size"] = {"X": 5, "Y": 3}
        body["WorldExploration"]["SavedActorStates"] = [
            {"SoftObjectPath": "/Game/Maps/Overworld/_Generated_/ABC123.Overworld:PersistentLevel.BP_FarmBridgeActorStateGimmick_C_UAID_08BF_2059", "PreviousState": 0, "CurrentState": 1},
            {"SoftObjectPath": "/Game/Maps/Caves/Cave-1677000-500.Cave:PersistentLevel.BP_KeyGolemLock_C_UAID_B025_1144", "PreviousState": 2, "CurrentState": 1},
            {"SoftObjectPath": "/Game/Maps/Caves/Cave-1668200-500.Cave:PersistentLevel.BP_KeyGolemLock_C_UAID_B025_1144", "PreviousState": 1, "CurrentState": 2},
        ]
        body["Ability"]["ProgressionTags"] = ["SW.Progression.MetTheMerchant"]
        told = world.lines([document])
        # A quest the list has, with steps it lacks: whole, in the save's order, each step with how it stands (+ done,
        # ~ the one in hand, with its count so far; a step that isn't named for its quest goes whole, after an =).
        self.assertIn("quest CA01 - Completed; more steps than the editor's list has; steps: E01+3, E02?Failed, =Elsewhere_K01~2", told)
        self.assertIn("door SW.Doorway.Camp.Docks - at 48, 99.5, 0; marker 7; the editor's list has it at 48, 80, 0", told)
        self.assertIn("region SW.Region.Camp - corner 0, 0; 5 across, 3 down; fog AAAAAABa/ygAAHgAAAAA; the editor's list has it elsewhere", told)
        self.assertIn("progression ProgressionTags SW.Progression.MetTheMerchant", told)
        # A puzzle piece is the same piece wherever its level was put, and is told once with every way it has stood.
        self.assertIn("piece Overworld BP_FarmBridgeActorStateGimmick UAID_08BF_2059 - 0 then 1; as saved: /Game/Maps/Overworld/_Generated_/ABC123.Overworld:PersistentLevel.BP_FarmBridgeActorStateGimmick_C_UAID_08BF_2059", told)
        self.assertIn("piece Cave BP_KeyGolemLock UAID_B025_1144 - 2 then 1; 1 then 2; as saved: /Game/Maps/Caves/Cave-1677000-500.Cave:PersistentLevel.BP_KeyGolemLock_C_UAID_B025_1144", told)
        self.assertTrue({"world quest CA01", "world door SW.Doorway.Camp.Docks", "world region SW.Region.Camp", "world progression ProgressionTags SW.Progression.MetTheMerchant",
                         "world piece Cave BP_KeyGolemLock UAID_B025_1144 2>1", "world piece Cave BP_KeyGolemLock UAID_B025_1144 1>2"} <= world.keys([document]))

    def test_recordings_add_where_things_turned_up(self):
        told = world.lines([hero_with_a_world()], recordings())
        self.assertEqual(told[: len(TOLD) + 1], [world.SAVES_HEADER] + TOLD)
        self.assertEqual(told[len(TOLD) + 1:], [
            "", world.PLACES_HEADER,
            "area SW.Area.DeepDark.A1",  # the saves tell of the town and the woods already
            "found minecart station SW.MinecartStation.ForestA1.Outpost - around 48, 48 in SW.Region.Camp",  # a quest or a step isn't a place
            "chest - 2 opened in SW.Area.Forest.A1, around 48, 48 in SW.Region.Camp",
            "chests - 2 opened in SW.Area.Forest.A1", "chests - 3 opened in SW.Area.DeepDark.A1",  # none for the one between two recordings
        ])
        # Recordings alone are worth telling, and are no news of the saves: they have no key.
        self.assertEqual(world.lines([hero_save()], recordings())[0], world.PLACES_HEADER)
        self.assertEqual(world.keys([hero_save()]), set())
        self.assertEqual(world.lines([hero_save()], {"heroes": {}}), [])
        # What the editor's list already has from recordings isn't told again: a spot it has, a count no higher than its own.
        have = world.merge(copy.deepcopy(world.known()), world.read_list("\n".join(told)))
        again = world.lines_of(world.news(world.of_recordings(recordings()), have), have=have)
        self.assertEqual(again, [])
        more = recordings()
        more["chests"][2]["opened"] = 5
        self.assertEqual(world.lines_of(world.news(world.of_recordings(more), have), have=have), ["chests - 5 opened in SW.Area.DeepDark.A1"])

    def test_a_list_told_reads_back_as_it_was(self):
        shown = world.of_saves([hero_with_a_world()])
        new = world.news(world.merge(shown, world.of_recordings(recordings())))
        read = world.read_list("SW.Item.Sword - a line about an item\n\n" + "\n".join(world.lines([hero_with_a_world()], recordings())))
        self.assertEqual(read.pop("pictures"), {"SW.Area.Meadow.R1": [0, 7, 0, 0]})
        self.assertEqual(read["chest_counts"], {"SW.Area.Forest.A1": 2, "SW.Area.DeepDark.A1": 3})
        for kind in ("quests", "stations", "doors", "regions", "cutscenes", "gimmicks", "achievements", "progression", "pieces", "found", "chests"):
            self.assertEqual(read[kind], new[kind], kind)
        self.assertEqual(read["areas"], ["SW.Area.Forest.A1", "SW.Area.DeepDark.A1"])
        # Steps, with how they stand taken off again; a door at a fraction of a metre; a piece with two ways of standing.
        read = world.read_list(
            "quest CA01 - Completed; more steps than the editor's list has; steps: E01+3, E02?Failed, =Elsewhere_K01~2, E03\n"
            "door SW.Doorway.Camp.Docks - at 48, 99.5, -3.25; marker 7; the editor's list has it at 48, 80, 0\n"
            "piece Cave BP_KeyGolemLock UAID_B025_1144 - 2 then 1; 1 then 2; as saved: /Game/Maps/Caves/Cave-1.Cave:PersistentLevel.BP_KeyGolemLock_C_UAID_B025_1144\n"
            "progression ProgressionTags SW.Progression.MetTheMerchant\nregion SW.Region.X - corner -608.5, 32; 2 across, 1 down; fog not-a-picture!\n"
            "a line about nothing\nquest - nothing\ndoor SW.Doorway.Nowhere - somewhere"
        )
        self.assertEqual(read["quests"], {"CA01": ["CA01_E01", "CA01_E02", "Elsewhere_K01", "CA01_E03"]})
        self.assertEqual(read["doors"], {"SW.Doorway.Camp.Docks": {"at": [48.0, 99.5, -3.25], "marker": 7}})
        self.assertEqual(read["pieces"]["Cave BP_KeyGolemLock UAID_B025_1144"]["states"], [[2, 1], [1, 2]])
        self.assertEqual((read["progression"], read["regions"], read["pictures"]), (
            {"ProgressionTags": ["SW.Progression.MetTheMerchant"]}, {"SW.Region.X": {"corner": [-608.5, 32], "size": [2, 1]}}, {}))

    def test_adding_to_a_list_changes_nothing_it_has(self):
        have = world.merge(world.empty(), {"quests": {"CA01": ["CA01_B", "CA01_A"]}, "doors": {"D": {"at": [1.0, 2.0, 3.0], "marker": 8}}, "chest_counts": {"X": 4},
                                           "chests": [{"area": "X", "region": "R", "at": [1, 2], "opened": 1}], "stations": ["S1"]})
        more = {"quests": {"CA01": ["CA01_A", "CA01_C"], "CA02": ["CA02_A"]}, "stations": ["S1", "S2"], "chest_counts": {"X": 3, "Y": 1},
                "doors": {"D": {"at": [1.4, 2.0, 3.9], "marker": 8}, "E": {"at": [0.0, 0.0, 0.0], "marker": 9}},
                "chests": [{"area": "X", "region": "R", "at": [1, 2], "opened": 1}, {"area": "X", "region": "R", "at": [5, 6], "opened": 2}]}
        world.merge(have, more)
        self.assertEqual(have["quests"], {"CA01": ["CA01_B", "CA01_A", "CA01_C"], "CA02": ["CA02_A"]})  # the order it had, new steps after
        self.assertEqual((have["stations"], have["chest_counts"], len(have["chests"])), (["S1", "S2"], {"X": 4, "Y": 1}, 2))
        self.assertEqual(have["doors"]["D"], {"at": [1.0, 2.0, 3.0], "marker": 8})  # within a metre: the same place
        # A door a save puts somewhere else keeps its place, and the other is kept beside it to be looked at, once.
        elsewhere = {"doors": {"D": {"at": [40.0, 2.0, 3.0], "marker": 8}}}
        world.merge(world.merge(have, elsewhere), elsewhere)
        self.assertEqual(have["doors"]["D"], {"at": [1.0, 2.0, 3.0], "marker": 8, "also": [{"at": [40.0, 2.0, 3.0], "marker": 8}]})
        self.assertEqual(world.news({**world.empty(), **elsewhere}, have)["doors"], {})  # and isn't news a second time
        self.assertEqual(copy.deepcopy(have), world.merge(have, have))

    def test_only_the_games_own_names_go_into_a_list(self):
        document = hero_with_a_world()
        body = document["CharacterSaveV1"]
        body["quest"]["Quests"].append({"QuestName": "Someone's own words, with a path C:\\Users\\me", "State": "Active", "TaskData": []})
        body["quest"]["Quests"].append({"QuestName": "CA09", "State": "Active", "TaskData": [{"TaskName": "not a name!", "State": "Active"}, "nonsense"]})
        body["WorldExploration"]["DiscoveredMinecartStationTags"] += ["a station with spaces", 12, None]
        body["WorldExploration"]["DiscoveredDungeonDoors"] += [{"DoorId": "SW.Doorway.NoPlace"}, {"DoorId": "SW.Doorway.Odd", "Location": {"X": "east"}}, "nonsense"]
        body["WorldExploration"]["SavedActorStates"] = [{"SoftObjectPath": "C:/Users/me/Documents/thing", "PreviousState": 0, "CurrentState": 1}, {"SoftObjectPath": 7}]
        body["MetaData"]["CurrentLocation"] = "an area with spaces"
        told = "\n".join(world.lines([document], recordings()))
        for kept_out in ("Someone", "Users", "spaces", "not a name", "NoPlace", "Odd", HERO_ID, "2026-10-01", "0002_Character", "Ranger"):
            self.assertNotIn(kept_out, told)
        self.assertIn("quest CA09 - Active; steps: ", told)
        self.assertEqual(world.lines([{"CharacterSaveV1": "not a save"}, None, {}]), [])
        # A save that holds the world some way nobody has seen tells nothing, and trips nothing up.
        odd = {"CharacterSaveV1": {
            "MetaData": ["a list"], "quest": "words", "Achievements": 5, "Ability": None,
            "WorldExploration": {"DiscoveredMinecartStationTags": {"a": 1}, "DiscoveredDungeonDoors": "none", "SavedActorStates": 3,
                                 "SavedFogOfWarExploration": {"Items": ["text", {"Tag": "SW.Region.Odd", "WorldPosition": "here", "Size": {"X": True, "Y": "2"}, "Data": "0102"},
                                                                        {"Tag": "SW.Region.Half", "WorldPosition": {"X": None, "Y": 32}, "Size": {"X": 2, "Y": 1}, "Data": [9, "x", 4]}]}},
        }}
        self.assertEqual(world.lines([odd]), [world.SAVES_HEADER, "region SW.Region.Odd - corner 0, 0; 0 across, 0 down", "region SW.Region.Half - corner 0, 32; 2 across, 1 down; fog CQA="])
        self.assertEqual(world.lines([{"CharacterSaveV1": {"WorldExploration": ["a list"], "quest": {"Quests": "many"}}}]), [])
        self.assertEqual(world.lines([hero_save()], {"locations": "everywhere", "found_at": ["a list"], "chests": [{"area": "SW.Area.Town", "opened": True, "near": "here"},
                                                                                                   {"area": "SW.Area.Town", "opened": 2, "near": [1], "region": "SW.Region.Camp"}]}),
                         [world.PLACES_HEADER, "chests - 2 opened in SW.Area.Town"])

    def test_no_more_than_fits(self):
        whole = world.lines([hero_with_a_world()], recordings())
        cut = world.lines([hero_with_a_world()], recordings(), most=320)
        self.assertEqual(cut[:5], whole[:5])
        self.assertLessEqual(sum(len(line) + 1 for line in cut[1:-1]), 320)
        kept = len([line for line in cut[:-1] if line and line not in (world.SAVES_HEADER, world.PLACES_HEADER)])
        told = len([line for line in whole if line and line not in (world.SAVES_HEADER, world.PLACES_HEADER)])
        self.assertEqual(cut[-1], f"({told - kept} more lines were left out to keep this short enough to post: share again after the editor's next update)")
        self.assertGreater(told - kept, 0)
        self.assertLess(sum(len(line) + 1 for line in world.lines([hero_with_a_world()], recordings())), world.MAX_CHARS)


class RealWorldListTests(unittest.TestCase):
    """The list that ships with the editor."""

    @classmethod
    def setUpClass(cls):
        tests.use_world_list(tests.REAL_WORLD_FILE)
        cls.world = copy.deepcopy(world.known())

    @classmethod
    def tearDownClass(cls):
        tests.use_world_list(tests.PINNED_WORLD_FILE)

    def test_holds_the_world_as_saves_have_shown_it(self):
        have = self.world
        self.assertGreaterEqual(len(have["quests"]), 15)
        self.assertIn("CA04", have["quests"])
        for name, steps in have["quests"].items():
            self.assertTrue(steps and len(set(steps)) == len(steps), name)
        for name, door in have["doors"].items():
            self.assertTrue(name.startswith("SW.Doorway.") and len(door["at"]) == 3 and isinstance(door["marker"], int), name)
        for tag, region in have["regions"].items():
            self.assertTrue(len(region["corner"]) == 2 and all(isinstance(side, int) and side > 0 for side in region["size"]), tag)
        self.assertTrue(all(tag.startswith("SW.MinecartStation.") for tag in have["stations"]))
        self.assertTrue(all(tag.startswith("SW.Area.") for tag in have["areas"] + list(have["chest_counts"])))
        for chest in have["chests"]:
            self.assertTrue(set(chest) == {"area", "region", "at", "opened"} and chest["region"] in have["regions"], chest)
        for label, places in have["found"].items():
            self.assertTrue(label.startswith(("minecart station ", "cutscene ")) and all(place["region"] in have["regions"] for place in places), label)
        # Nothing of anyone's: no hero's ID, no date, no recording's name anywhere in the file.
        text = tests.REAL_WORLD_FILE.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        self.assertNotRegex(text, r"20\d\d-\d\d-\d\d|Character|snapshot|Users")

    def test_tells_and_reads_back_whole(self):
        told = world.lines_of(self.world, have=world.empty())
        read = world.read_list("\n".join(told))
        read.pop("pictures")
        self.assertEqual(world.merge(world.empty(), read), {key: value for key, value in self.world.items()})
        self.assertEqual(world.counts(read), world.counts(self.world))

    def test_the_tool_adds_recordings_and_players_lists_to_it(self):
        spec = importlib.util.spec_from_file_location("build_world_list", Path(__file__).resolve().parent.parent / "tools" / "build_world_list.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder = Path(temp.name)
        snapshots = folder / "recordings" / "2026-10-01_10-00-00" / "snapshots"
        snapshots.mkdir(parents=True)
        (snapshots / "0001_Character.json").write_text(json.dumps(hero_save()), encoding="utf-8")
        (snapshots / "0002_Character.json").write_text(json.dumps(hero_with_a_world()), encoding="utf-8")
        (snapshots / "0003_GlobalSaveData.json").write_text(json.dumps({"settings": 1}), encoding="utf-8")
        sent = folder / "issue-99.txt"
        sent.write_text("SW.Item.Sword - an item\n\n" + world.SAVES_HEADER + "\nquest CA09 - Active; steps: E01~\ndoor SW.Doorway.Camp.Docks - at 480, 80, 0; marker 7\n", encoding="utf-8")
        out = folder / "world.json"
        out.write_text(json.dumps({"quests": {"CA01": ["CA01_E01", "CA01_E00"]}}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(tool.main([str(sent), "--recordings", str(folder / "recordings"), "--out", str(out)]), 0)
        self.assertIn("The list has: 4 quests (6 steps), 3 doors, 2 minecart stations, 2 regions", printed.getvalue())
        built = json.loads(out.read_text(encoding="utf-8"))
        self.assertIn("tools/build_world_list.py", built.pop("about"))
        self.assertEqual(list(built["quests"]), ["CA01", "CA04", "FOa1_S10_A", "CA09"])
        self.assertEqual(built["quests"]["CA01"], ["CA01_E01", "CA01_E00"])  # what the list had stays as it was
        self.assertEqual((built["areas"], built["stations"]), (["SW.Area.Town", "SW.Area.Forest.A1"], ["SW.MinecartStation.Town", "SW.MinecartStation.ForestA1.Outpost"]))
        self.assertEqual(built["doors"]["SW.Doorway.Camp.Docks"], {"at": [48.0, 80.0, 0.0], "marker": 7, "also": [{"at": [480.0, 80.0, 0.0], "marker": 7}]})
        _built, said = tool.build(folder / "recordings", [sent], built)
        self.assertTrue(any(line.startswith("LOOK AT: door SW.Doorway.Camp.Docks is in two places") for line in said))
        self.assertIn("Read 2 hero saves in the recordings", "\n".join(said))


if __name__ == "__main__":
    unittest.main()
