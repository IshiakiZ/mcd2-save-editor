import json
import tempfile
import unittest
from pathlib import Path

import tests
from dungeons2_editor import story, world_dialog

from . import helpers
from .helpers import hero_save, hero_with_a_world, recordings_of_a_world


class WorldMapListTests(unittest.TestCase):
    """What the World map window lists about a hero and puts on its map, worked out without a window."""

    def test_lists_how_far_a_hero_has_got_in_the_games_own_names(self):
        listed = dict(world_dialog.sections(hero_with_a_world(), recordings_of_a_world()))
        self.assertEqual(list(listed), [
            "Where the hero is", "So far", "The story, by the game's achievements for it", "What you may have missed, as far as the save shows",
            "Ground explored", "Quests, as the save names them", "Minecart stations found", "Doors found", "Chests your recordings saw opened, by area",
            "Other achievements, as the save counts them", "From your recordings",
        ])
        self.assertEqual(listed["Where the hero is"], ["Area: Howling Woods", "Quest in focus: CA04 (The Missing Note Blocks)", "Last minecart station: Little Howl Hamlet"])
        self.assertEqual(listed["So far"], [
            "Story quests done: 1 of 3", "Quests met: 1 completed, 1 active, 1 available", "Quest steps done: 2 of 4", "Minecart stations found: 2 of at least 19",
            "Doors found: 3", "Cutscenes seen: 1", "Chests opened: 5, by the game's own count",
        ])
        # A story quest is named by the game's achievement for finishing it.
        self.assertEqual(listed["The story, by the game's achievements for it"], ["✓  Arrive In Brave Haven", "·  Wobble Run", "·  Carapace Side Quest"])
        missed = listed["What you may have missed, as far as the save shows"]
        self.assertEqual(missed[:3], [
            "Howling Woods: 1 of its 12 dungeon spots found",
            "(The game opens only a few of an area's dungeon and rift spots at a time, so one you haven't found may not be open yet.)",
            "Minecart stations: 2 found of at least 19",
        ])
        self.assertEqual(missed[4:], [
            "Quest CA04 (The Missing Note Blocks): 1 of 2 steps left", "Quest FOa1_S10_A (The Cleric's Apprentice): not started",
            "Camp: 6 unexplored squares right next to the 4 you've explored", "Meadow.R1: 2 unexplored squares right next to the 1 you've explored",
        ])
        self.assertEqual(listed["Ground explored"], ["Camp: 4 of 12 squares", "Meadow.R1: 1 of 4 squares"])
        self.assertEqual(listed["Quests, as the save names them"], [
            "CA01 (The Illagers from the Rift): completed, 1 of 1 steps done", "CA04 (The Missing Note Blocks): active, 1 of 2 steps done",
            "FOa1_S10_A (The Cleric's Apprentice): available, 0 of 1 steps done",
        ])
        self.assertEqual(listed["Minecart stations found"], ["Haven Station  (Town)", "Little Howl Hamlet  (ForestA1.Outpost)"])
        self.assertEqual(listed["Doors found"], ["Camp.Docks", "ForestA1.Dungeon.1", "MeadowR1.ForestA1"])
        self.assertEqual(listed["Chests your recordings saw opened, by area"], ["Howling Woods: 2", "While nothing was recording: 1"])
        self.assertEqual(listed["Other achievements, as the save counts them"], ["Equip A Unique Item: done", "Discover All Minecart Stations: 2 collected", "Open 100 Chests: 5"])
        self.assertEqual(listed["From your recordings"], ["3 saves of this hero read"])

    def test_says_how_many_shortcuts_and_key_gates_are_open_and_asks_before_opening_them(self):
        with tempfile.TemporaryDirectory() as folder:
            listed = Path(folder) / "world.json"
            listed.write_text(json.dumps({"pieces": helpers.PIECES}), encoding="utf-8")
            tests.use_world_list(listed)
            self.addCleanup(tests.use_world_list, tests.PINNED_WORLD_FILE)
            hero = hero_with_a_world()
            hero["CharacterSaveV1"]["WorldExploration"]["SavedActorStates"] = [helpers.as_saved(helpers.ROCK_OPENED)]
            so_far = dict(world_dialog.sections(hero))["So far"]
            self.assertEqual(so_far[5:8], ["Cutscenes seen: 1", "Shortcuts open: 1 of the 3 the editor knows", "Key gates open: 0 of the 2 the editor knows"])
        # With the list the tests are pinned to, which knows none, the two lines aren't there.
        tests.use_world_list(tests.PINNED_WORLD_FILE)
        self.assertFalse(any("the editor knows" in line for line in dict(world_dialog.sections(hero_with_a_world()))["So far"]))
        # Discovering the whole map costs the recorder its way of telling where things happen, and the question says so.
        self.assertIn("With the whole map discovered it can only tell the area.", world_dialog.discover_question(15, []))
        question = world_dialog.open_question(story.SHORTCUTS, 2, 3)
        self.assertTrue(question.startswith("Open the shortcuts?\n\nThe editor knows 3 shortcuts: rocks that move out of the way once you've come round to their far side, and a bridge. "), question)
        self.assertIn("2 of them aren't open for this hero yet, and they will be marked open, the way a save holds one that is.", question)
        self.assertTrue(question.endswith("nothing reaches the game until Save to game, and Discard changes takes it back."))
        question = world_dialog.open_question(story.GATES, 2, 2)
        self.assertIn("The editor knows 2 gates that a key opens. None of them is open for this hero yet, and they will be marked open, the way a save holds a gate once its key is in: "
                      "the gate open, the key in its lock, and the key taken, for each lock and key the editor can tell to be a gate's own.", question)
        # Every gate open, and locks and keys still as before a key went in: the question says what's left to do.
        left = world_dialog.open_question(story.GATES, 0, 2, 3)
        self.assertIn("Every key gate the editor knows is open for this hero, but 3 of their locks and keys are as before a key was put in: the gate stands open with its keyhole still there. "
                      "They will be marked the way a save holds them once the key is in: the key in its lock, and the key taken.", left)
        self.assertIn("1 of their locks and keys is as before", world_dialog.open_question(story.GATES, 0, 2, 1))
        self.assertIn("One of them isn't open for this hero yet, and it will be marked open", world_dialog.open_question(story.GATES, 1, 4))
        self.assertIn("The editor knows 1 gate that a key opens. It isn't open for this hero yet, and it will be marked open", world_dialog.open_question(story.GATES, 1, 1))

    def test_a_hero_with_no_recordings_and_one_that_has_been_nowhere(self):
        listed = dict(world_dialog.sections(hero_with_a_world()))
        self.assertNotIn("Chests your recordings saw opened, by area", listed)
        self.assertEqual(listed["From your recordings"], [world_dialog.NO_RECORDINGS])
        # Another hero's recordings are not this one's.
        theirs = recordings_of_a_world()
        theirs["heroes"] = {"someone-else": theirs["heroes"].popitem()[1]}
        self.assertEqual(dict(world_dialog.sections(hero_with_a_world(), theirs))["From your recordings"], [world_dialog.NO_RECORDINGS])
        # A save that says nothing about the world still has a list to show, and no map.
        listed = dict(world_dialog.sections(hero_save()))
        self.assertEqual(listed["Where the hero is"], ["Area: Brave Haven"])
        self.assertEqual(listed["So far"], ["Minecart stations found: 0 of at least 19", "Doors found: 0", "Cutscenes seen: 0"])
        self.assertNotIn("Ground explored", listed)

    def test_puts_doors_exactly_and_what_the_recordings_saw_around_where_it_turned_up(self):
        from dungeons2_editor import recorder

        document, mine = hero_with_a_world(), recordings_of_a_world()["heroes"]["00000000-0000-1000-8000-000000000002"]
        regions, doors = recorder.map_regions(document), recorder.door_places(document)
        camp = world_dialog.things("SW.Region.Camp", regions, doors, mine)
        self.assertEqual([(kind, name, x, y) for kind, name, x, y, _what in camp], [
            ("door", "Camp.Docks", 48.0, 80.0), ("door", "ForestA1.Dungeon.1", 16.0, 16.0), ("found", "Little Howl Hamlet", 48, 48), ("chest", "2 chests", 48, 48)])
        self.assertEqual(camp[0][4], "Door Camp.Docks, at 48, 80")
        self.assertTrue(camp[2][4].startswith("Minecart station Little Howl Hamlet. The save that showed it also showed new ground explored here"))
        self.assertTrue(camp[3][4].startswith("2 chests opened in Howling Woods. "))
        # On the camp's picture (four squares across, three down, the top line the far side in X) the docks' door is
        # in the middle line, on the square that's all clear.
        self.assertEqual(recorder.square_of(regions["SW.Region.Camp"], 48, 80), (2.5, 1.5))
        self.assertEqual(regions["SW.Region.Camp"]["cells"][1 * 4 + 2], 255)
        self.assertEqual([(kind, name) for kind, name, *_rest in world_dialog.things("SW.Area.Meadow.R1", regions, doors, mine)], [("door", "MeadowR1.ForestA1")])
        self.assertEqual(world_dialog.things("SW.Region.Camp", regions, doors, {})[2:], [])  # no recordings: the doors only
        # A quest that started or ended there isn't put on the map; a cutscene seen there is.
        mine["found_at"]["quest CA04"] = mine["found_at"]["cutscene SW.UI.Cutscene.Cutscenes.CS02"] = dict(mine["found_at"]["minecart station SW.MinecartStation.ForestA1.Outpost"])
        self.assertEqual([name for kind, name, *_rest in world_dialog.things("SW.Region.Camp", regions, doors, mine) if kind == "found"], ["Little Howl Hamlet", "Cutscenes.CS02"])

    def test_puts_a_rock_a_key_and_a_gate_where_a_recording_saw_them_change(self):
        from dungeons2_editor import world

        with tempfile.TemporaryDirectory() as folder:
            listed = Path(folder) / "world.json"
            # The editor's list knows where a recording saw the bridge and a lock change; this PC's recordings saw the gate.
            listed.write_text(json.dumps({"pieces": helpers.PIECES, "found": {
                f"piece {world.piece_id(helpers.BRIDGE)}": [{"region": "SW.Region.Camp", "at": [20, 60]}],
                f"piece {world.piece_id(helpers.KEY_LOCK)}": [{"region": "SW.Area.Meadow.R1", "at": [1010, 1010]}],
                f"piece {world.piece_id(helpers.LIFT_BUTTON)}": [{"region": "SW.Region.Camp", "at": [5, 5]}],
            }}), encoding="utf-8")
            tests.use_world_list(listed)
            self.addCleanup(tests.use_world_list, tests.PINNED_WORLD_FILE)
            hero = hero_with_a_world()
            hero["CharacterSaveV1"]["WorldExploration"]["SavedActorStates"] = [helpers.as_saved(helpers.KEY_GATE)]
            # A recording's name for a thing is the end of the save's, which can be cut short in front.
            seen = {"found_at": {
                "actor " + helpers.KEY_GATE.rsplit("/", 1)[-1][-90:]: {"near": [40, 70], "region": "SW.Region.Camp"},
                "actor " + helpers.ROCK.rsplit("/", 1)[-1][-90:]: {"near": None, "region": None},  # saw it change, with no ground newly explored: no place
                "minecart station SW.MinecartStation.Town": {"near": [1, 1], "region": "SW.Region.Camp"},
            }}
            camp = world_dialog.pieces_placed("SW.Region.Camp", hero, seen)
            self.assertEqual([(kind, name, x, y) for kind, name, x, y, _what in camp], [("piece", "Gold Key Gate Door", 40, 70), ("piece", "Farm Bridge", 20, 60)])
            self.assertTrue(camp[0][4].startswith("Gold Key Gate Door, a gate a key opens: open for this hero. The save that showed it"), camp[0][4])
            self.assertTrue(camp[1][4].startswith("Farm Bridge, a shortcut: not open yet for this hero. "), camp[1][4])
            (lock,) = world_dialog.pieces_placed("SW.Area.Meadow.R1", hero, None)
            self.assertEqual((lock[1], lock[4].split(". ")[0]), ("Key Golem Lock", "Key Golem Lock, a lock for a key: no key in it yet for this hero"))
            self.assertEqual(world.piece_id("d:PersistentLevel.BP_MeadowRoadblockActorStateGimmick_C_UAID_B025_1138"), "BP_MeadowRoadblockActorStateGimmick UAID_B025_1138")
            self.assertEqual((world.piece_id(helpers.CAMP_GATE), world.piece_id("SW.Doorway.Camp.Docks")), ("BP_MA2_KeyGate UAID_AA05_5", ""))
            # And the list takes such a place from a recording's atlas, to tell and to read back.
            told = world.of_recordings({"found_at": seen["found_at"]})["found"]
            self.assertEqual(told, {"minecart station SW.MinecartStation.Town": [{"region": "SW.Region.Camp", "at": [1, 1]}],
                                    f"piece {world.piece_id(helpers.KEY_GATE)}": [{"region": "SW.Region.Camp", "at": [40, 70]}]})
            line = "found piece BP_GoldKeyGateDoorActorStateGimmick UAID_AA04_4 - around 40, 70 in SW.Region.Camp"
            self.assertEqual(world.read_list(line)["found"], {f"piece {world.piece_id(helpers.KEY_GATE)}": [{"region": "SW.Region.Camp", "at": [40, 70]}]})

    def test_puts_what_the_list_knows_and_the_hero_has_not_found_on_the_map_too(self):
        from dungeons2_editor import recorder

        with tempfile.TemporaryDirectory() as folder:
            listed = Path(folder) / "world.json"
            listed.write_text(json.dumps({
                "doors": {"SW.Doorway.Camp.Docks": {"at": [48.0, 80.0, 0.0], "marker": 7}, "SW.Doorway.Camp.Cellar": {"at": [16.0, 48.0, 0.0], "marker": 8},
                          "SW.Doorway.Far.Away": {"at": [90000.0, 90000.0, 0.0], "marker": 8}},
                "found": {"minecart station SW.MinecartStation.PlainsA1.Barn": [{"region": "SW.Region.Camp", "at": [40, 40]}],
                          "minecart station SW.MinecartStation.Town": [{"region": "SW.Region.Camp", "at": [8, 8]}],
                          "minecart station SW.MinecartStation.ForestA1.Outpost": [{"region": "SW.Region.Camp", "at": [9, 9]}],
                          "piece BP_FarmBridgeActorStateGimmick UAID_AA03_3": [{"region": "SW.Region.Camp", "at": [20, 60]}]},
                "chests": [{"area": "SW.Area.Town", "region": "SW.Region.Camp", "at": [30, 30], "opened": 2},
                           {"area": "SW.Area.Forest.A1", "region": "SW.Region.Camp", "at": [48, 48], "opened": 2}],
            }), encoding="utf-8")
            tests.use_world_list(listed)
            self.addCleanup(tests.use_world_list, tests.PINNED_WORLD_FILE)
            document, mine = hero_with_a_world(), recordings_of_a_world()["heroes"]["00000000-0000-1000-8000-000000000002"]
            regions, doors = recorder.map_regions(document), recorder.door_places(document)
            more = world_dialog.things_not_found("SW.Region.Camp", regions, doors, mine, document)
            self.assertEqual([(kind, name, x, y) for kind, name, x, y, _what in more], [
                ("door?", "Camp.Cellar", 16.0, 48.0),  # a door the hero hasn't found, exactly where other saves have it; the docks' it has, and the far one is in no region of its map
                ("found?", "Honeycomb Farm", 40, 40),  # a station the hero hasn't found
                ("found", "Haven Station", 8, 8),  # one it has found, which its own recordings have no place for
                ("chest?", "2 chests", 30, 30),  # a spot its own recordings don't have; the one they do isn't drawn twice
            ])
            self.assertEqual(more[0][4], "Door Camp.Cellar, at 16, 48. This hero hasn't found it yet: other players' saves have it here.")
            self.assertTrue(more[1][4].endswith(", which this hero has not found yet. Another player's recording saw it turn up around here."), more[1][4])
            self.assertEqual(more[2][4], "Minecart station Haven Station. Another player's recording saw it turn up around here.")
            self.assertEqual(more[3][4], "A recording saw 2 chests opened around here, in Brave Haven.")
        tests.use_world_list(tests.PINNED_WORLD_FILE)

    def test_names_made_from_the_games_ids(self):
        self.assertEqual([world_dialog.spaced(name) for name in ("Open100Chests", "Kill10MobsWithATNT", "DefeatACopperMonstrosity", "ReachLevel50")],
                         ["Open 100 Chests", "Kill 10 Mobs With A TNT", "Defeat A Copper Monstrosity", "Reach Level 50"])
        self.assertEqual(world_dialog.story_name("SW.Achievements.CompleteDefeatTheSupremeEvokerAndSoulConstructQuest"), "Defeat The Supreme Evoker And Soul Construct")
        self.assertEqual([world_dialog.short(name) for name in ("SW.Doorway.TownA1.Docks", "SW.Region.Overworld", "SW.UI.Cutscene.Cutscenes.CS02", "Something.Else")],
                         ["TownA1.Docks", "Overworld", "Cutscenes.CS02", "Something.Else"])


if __name__ == "__main__":
    unittest.main()
