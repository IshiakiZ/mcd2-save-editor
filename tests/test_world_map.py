import unittest

from dungeons2_editor import world_dialog

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
            "Story quests done: 1 of 3", "Quests met: 1 completed, 1 active, 1 available", "Quest steps done: 2 of 4", "Minecart stations found: 2 of 19",
            "Doors found: 3", "Cutscenes seen: 1", "Chests opened: 5, by the game's own count",
        ])
        # A story quest is named by the game's achievement for finishing it.
        self.assertEqual(listed["The story, by the game's achievements for it"], ["✓  Arrive In Brave Haven", "·  Wobble Run", "·  Carapace Side Quest"])
        missed = listed["What you may have missed, as far as the save shows"]
        self.assertEqual(missed[:3], [
            "Howling Woods: 1 of its 12 dungeon spots found",
            "(The game opens only a few of an area's dungeon and rift spots at a time, so one you haven't found may not be open yet.)",
            "Minecart stations: 2 found of 19",
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
        self.assertEqual(listed["So far"], ["Minecart stations found: 0 of 19", "Doors found: 0", "Cutscenes seen: 0"])
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

    def test_names_made_from_the_games_ids(self):
        self.assertEqual([world_dialog.spaced(name) for name in ("Open100Chests", "Kill10MobsWithATNT", "DefeatACopperMonstrosity", "ReachLevel50")],
                         ["Open 100 Chests", "Kill 10 Mobs With A TNT", "Defeat A Copper Monstrosity", "Reach Level 50"])
        self.assertEqual(world_dialog.story_name("SW.Achievements.CompleteDefeatTheSupremeEvokerAndSoulConstructQuest"), "Defeat The Supreme Evoker And Soul Construct")
        self.assertEqual([world_dialog.short(name) for name in ("SW.Doorway.TownA1.Docks", "SW.Region.Overworld", "SW.UI.Cutscene.Cutscenes.CS02", "Something.Else")],
                         ["TownA1.Docks", "Overworld", "Cutscenes.CS02", "Something.Else"])


if __name__ == "__main__":
    unittest.main()
