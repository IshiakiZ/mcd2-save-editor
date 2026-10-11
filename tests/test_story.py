import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import tests
from dungeons2_editor import story, world
from dungeons2_editor.hero import describe_changes

from .helpers import hero_save, hero_with_a_world

# What the editor's list of the world says in these tests: three quests with their steps, the number saved with two
# finished steps, and the two quests a recording saw the game open as it finished CA04.
LIST = {
    "quests": {
        "CA04": ["CA04_E01", "CA04_E02"], "CA05": ["CA05_E01", "CA05_K01", "CA05_Sequence01"], "CA04_BR": ["CA04_BR_AS01", "CA04_BR_Sequence01"],
        "PLa2_S15_A": ["PLa2_S15_A_I01"], "CT_S01_A": ["CT_S01_A_MT01"], "Empty": [],
    },
    "counts": {"CA04_E02": 3, "CA05_K01": 5},
    "follows": {"CA04": ["CA05", "CA04_BR", "FOa1_S10_A", "Unseen"]},
    "areas": ["SW.Area.Town", "SW.Area.Forest.A1"],
    "regions": {"SW.Area.Plains.A2.BossTower": {"corner": [0, 0], "size": [2, 2]}},
}
# A quest as the game saved it just before it finished it, just after, and the quest it listed with that, from one of
# the developer's play recordings, written the way a shared list writes a quest (+ done, ~ active, a number after it
# for a step that counts).
BEFORE = "quest CA01_B - Active; steps: I01+1, E02+, AS01+, I02+1, Standard01+, Standard02+, SM01+, I03+1, Standard03+, SM02+, I04+1, Standard04+, SM03+, I05+1, Standard05+, SM04+, I06+1, E03+, I07+1, E04+, E05+, I08~, Sequence01~"
AFTER = "quest CA01_B - Completed; steps: I01+1, E02+, AS01+, I02+1, Standard01+, Standard02+, SM01+, I03+1, Standard03+, SM02+, I04+1, Standard04+, SM03+, I05+1, Standard05+, SM04+, I06+1, E03+, I07+1, E04+, E05+, I08+1, Sequence01+"
CAME = "quest CA02 - Available; steps: E08, I09, I08, E02, I01, E03, AS01, PC01, E04, Sequence03, E05, I03, PC02, AS02, E06, AS03, I04, PC03, I05, PC04, I07, Sequence01"


def as_saved(line: str) -> dict:
    """A quest as a save holds it, from a shared list's line about it."""
    head, steps = line.split("; steps: ")
    name, state = re.fullmatch(r"quest (\S+) - (\w+)", head).groups()
    tasks = []
    for token in steps.split(", "):
        step, mark, count = re.fullmatch(r"([A-Za-z0-9]+)([+~]?)(\d*)", token).groups()
        tasks.append({"TaskName": f"{name}_{step}", "State": {"+": "Completed", "~": "Active", "": "NotSet"}[mark], "PartialProgress": int(count or 0)})
    return {"QuestName": name, "State": state, "TaskData": tasks}


class StoryTests(unittest.TestCase):
    """A hero's quests, and the few changes the editor makes to them."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        path = Path(cls.folder.name) / "world.json"
        path.write_text(json.dumps(LIST), encoding="utf-8")
        tests.use_world_list(path)

    @classmethod
    def tearDownClass(cls):
        tests.use_world_list(tests.PINNED_WORLD_FILE)
        cls.folder.cleanup()

    def setUp(self):
        self.document = hero_with_a_world()  # CA01 finished, CA04 active and tracked, FOa1_S10_A available
        self.quests = self.document["CharacterSaveV1"]["quest"]

    def quest(self, name):
        return next(quest for quest in story.quests(self.document) if quest.name == name)

    def test_reads_a_heros_quests_as_the_save_has_them(self):
        self.quests["Quests"][1]["TaskData"][1]["PartialProgress"] = 2
        found = story.quests(self.document)
        self.assertEqual([(quest.name, quest.state, quest.done, len(quest.steps), quest.tracked) for quest in found],
                         [("CA01", "Completed", 1, 1, False), ("CA04", "Active", 1, 2, True), ("FOa1_S10_A", "Available", 0, 1, False)])
        self.assertEqual([(step.short, step.state, step.count) for step in found[1].steps], [("E01", "Completed", 0), ("E02", "Active", 2)])
        self.assertEqual((found[1].label, found[0].standing, found[1].standing, found[2].standing), ("The Missing Note Blocks (CA04)", "finished", "active", "available"))
        self.assertEqual(story.tracked(self.document), "CA04")
        # A save with no quests in it has none, and nothing to change.
        self.assertEqual((story.quests(hero_save()), story.quests({}), story.tracked(hero_save())), ([], [], ""))
        for change in (story.finish, story.start_over, story.add, story.track):
            with self.assertRaisesRegex(ValueError, "keeps no quests yet"):
                change(hero_save(), "CA04")

    def test_a_quest_and_a_step_say_what_they_are(self):
        self.assertEqual([story.group_of(name) for name in ("CA04", "CA10_BR_B", "PLa1_S04_A", "FOa1_S10_A", "PLa2_S15_A", "DEa1_S13_A", "MEa2_S03_A", "CAa1_S02_A", "TOa1_S01_A", "CT_S01_A")], [
            "Main story", "Main story", "Side quests: Honeycomb Fields", "Side quests: Howling Woods", "Side quests: Rainy Plains", "Side quests: Frozen Highlands",
            "Side quests: Meadow A2", "Side quests: Carapace A1", "Side quests: Brave Haven", "Other quests",
        ])
        self.assertEqual((story.label("CA04"), story.label("CA02_C")), ("The Missing Note Blocks (CA04)", "CA02_C"))
        kinds = {name: story.Step(f"CA09_{name}", "NotSet", 0, "CA09").kind for name in ("E02B", "I16", "K04", "SM09", "PC01", "MT02", "A04", "Arena03Gateless", "Follow01", "Sequence06", "Standard07", "Selection04", "AS05", "F01", "false04")}
        self.assertEqual(kinds, {
            "E02B": "reach a place", "I16": "interact with something", "K04": "defeat enemies", "SM09": "enemies appear", "PC01": "a cutscene", "MT02": "someone walks somewhere",
            "A04": "an arena fight", "Arena03Gateless": "an arena fight", "Follow01": "follow someone", "Sequence06": "a group of steps, one after the other",
            "Standard07": "a group of steps, in any order", "Selection04": "a choice between steps", "AS05": "", "F01": "", "false04": "",
        })
        self.assertEqual((story.Step("CA09_Sequence06", "NotSet", 0, "CA09").is_group, story.Step("CA09_K04", "NotSet", 0, "CA09").is_group), (True, False))
        self.assertEqual(story.Step("Elsewhere_K04", "NotSet", 0, "CA09").short, "Elsewhere_K04")  # a step not named for its quest keeps its whole name

    def test_finishes_a_quest_the_way_a_save_holds_a_finished_one(self):
        untouched = copy.deepcopy({key: value for key, value in self.document["CharacterSaveV1"].items() if key != "quest"})
        added = story.finish(self.document, "CA04")
        quest = self.quest("CA04")
        self.assertEqual((quest.state, quest.tracked, story.tracked(self.document)), ("Completed", False, ""))
        # Every step done, and the one that counts with the number the game saved with it once it was done.
        self.assertEqual([(step.short, step.state, step.count) for step in quest.steps], [("E01", "Completed", 0), ("E02", "Completed", 3)])
        # The quests a recording saw the game open with it are there now: the ones the hero hadn't met, and whose
        # steps the editor knows. The one the hero had already is as it was.
        self.assertEqual(added, ["CA05", "CA04_BR"])
        self.assertEqual([quest.name for quest in story.quests(self.document)], ["CA01", "CA04", "FOa1_S10_A", "CA05", "CA04_BR"])
        self.assertEqual(self.quests["Quests"][3], {"QuestName": "CA05", "State": "Available", "TaskData": [
            {"TaskName": "CA05_E01", "State": "NotSet", "PartialProgress": 0}, {"TaskName": "CA05_K01", "State": "NotSet", "PartialProgress": 0},
            {"TaskName": "CA05_Sequence01", "State": "NotSet", "PartialProgress": 0},
        ]})
        # Nothing else in the save: no achievement, no item, no XP. Those are the game's to give.
        self.assertEqual({key: value for key, value in self.document["CharacterSaveV1"].items() if key != "quest"}, untouched)
        with self.assertRaisesRegex(ValueError, r"The Missing Note Blocks \(CA04\) is finished already"):
            story.finish(self.document, "CA04")
        with self.assertRaisesRegex(ValueError, "hasn't met the quest CA09"):
            story.finish(self.document, "CA09")

    def test_finishing_keeps_a_count_that_is_further_than_the_one_it_knows_and_another_quests_tracking(self):
        self.quests["Quests"][1]["TaskData"][1]["PartialProgress"] = 4
        self.quests["FocusedQuestId"] = "CA04"
        self.assertEqual(story.finish(self.document, "FOa1_S10_A"), [])  # nothing is known to follow it
        self.assertEqual((self.quest("FOa1_S10_A").state, story.tracked(self.document)), ("Completed", "CA04"))
        story.finish(self.document, "CA04")
        self.assertEqual(self.quest("CA04").steps[1].count, 4)

    def test_finishes_a_quest_as_the_game_itself_did(self):
        # The save before the game finished CA01_B, the save after, and the editor's own work on the first, with
        # the real list of what follows what: the same quest, the same quest opened with it, nothing tracked.
        tests.use_world_list(tests.REAL_WORLD_FILE)
        try:
            document = hero_with_a_world()
            quests = document["CharacterSaveV1"]["quest"]
            quests["Quests"], quests["FocusedQuestId"] = [as_saved(BEFORE)], "CA01_B"
            self.assertEqual(story.finish(document, "CA01_B"), ["CA02"])
            self.assertEqual(quests, {"FocusedQuestId": "", "Quests": [as_saved(AFTER), as_saved(CAME)]})
        finally:
            tests.use_world_list(Path(self.folder.name) / "world.json")

    def test_starts_a_quest_over(self):
        self.quests["Quests"][1]["TaskData"][1]["PartialProgress"] = 2
        story.start_over(self.document, "CA04")
        quest = self.quest("CA04")
        self.assertEqual((quest.state, story.tracked(self.document)), ("Available", ""))
        self.assertEqual([(step.state, step.count) for step in quest.steps], [("NotSet", 0), ("NotSet", 0)])
        story.start_over(self.document, "CA01")  # a finished one too
        self.assertEqual((self.quest("CA01").state, self.quest("CA01").done), ("Available", 0))
        with self.assertRaisesRegex(ValueError, "hasn't been begun"):
            story.start_over(self.document, "FOa1_S10_A")
        with self.assertRaisesRegex(ValueError, "hasn't met the quest CA05"):
            story.start_over(self.document, "CA05")

    def test_adds_a_quest_the_hero_has_not_met(self):
        self.assertEqual([(quest.name, quest.state, len(quest.steps)) for quest in story.unmet(self.document)],
                         [("CA04_BR", None, 2), ("CA05", None, 3), ("CT_S01_A", None, 1), ("PLa2_S15_A", None, 1)])  # not the one with no steps known
        story.add(self.document, "PLa2_S15_A")
        self.assertEqual(self.quests["Quests"][-1], {"QuestName": "PLa2_S15_A", "State": "Available", "TaskData": [{"TaskName": "PLa2_S15_A_I01", "State": "NotSet", "PartialProgress": 0}]})
        self.assertNotIn("PLa2_S15_A", [quest.name for quest in story.unmet(self.document)])
        with self.assertRaisesRegex(ValueError, "has met PLa2_S15_A already"):
            story.add(self.document, "PLa2_S15_A")
        for unknown in ("CA09", "Empty"):
            with self.assertRaisesRegex(ValueError, "doesn't know its steps"):
                story.add(self.document, unknown)

    def test_lists_every_quest_by_the_part_of_the_game_it_belongs_to(self):
        listed = [(quest.group, quest.name, quest.standing) for quest in story.every(self.document)]
        self.assertEqual(listed, [
            ("Main story", "CA01", "finished"), ("Main story", "CA04", "active"), ("Main story", "CA04_BR", "not met yet"), ("Main story", "CA05", "not met yet"),
            ("Side quests: Howling Woods", "FOa1_S10_A", "available"), ("Side quests: Rainy Plains", "PLa2_S15_A", "not met yet"), ("Other quests", "CT_S01_A", "not met yet"),
        ])

    def test_picks_the_quest_the_game_tracks(self):
        self.quests["Quests"][2]["State"] = "Active"
        story.track(self.document, "FOa1_S10_A")
        self.assertEqual((story.tracked(self.document), self.quest("FOa1_S10_A").tracked, self.quest("CA04").tracked), ("FOa1_S10_A", True, False))
        story.track(self.document, "")
        self.assertEqual(story.tracked(self.document), "")
        with self.assertRaisesRegex(ValueError, "Only an active quest"):
            story.track(self.document, "CA01")

    def test_has_a_hero_start_at_a_station_it_has_found(self):
        self.assertEqual(story.start_points(self.document), ["SW.MinecartStation.Town.Fountain", "SW.MinecartStation.Town", "SW.MinecartStation.ForestA1.Outpost"])
        self.assertEqual((story.last_station(self.document), story.area(self.document)), ("SW.MinecartStation.ForestA1.Outpost", "SW.Area.Forest.A1"))
        untouched = copy.deepcopy(self.document["CharacterSaveV1"]["WorldExploration"]["DiscoveredMinecartStationTags"])
        story.start_at(self.document, "SW.MinecartStation.Town")
        self.assertEqual((story.last_station(self.document), story.area(self.document)), ("SW.MinecartStation.Town", "SW.Area.Town"))
        story.start_at(self.document, "SW.MinecartStation.Town.Fountain")  # where a hero starts out: no save lists it as found
        self.assertEqual((story.last_station(self.document), story.area(self.document)), ("SW.MinecartStation.Town.Fountain", "SW.Area.Town"))
        self.assertEqual(self.document["CharacterSaveV1"]["WorldExploration"]["DiscoveredMinecartStationTags"], untouched)
        with self.assertRaisesRegex(ValueError, "hasn't found Monsoon Banks"):
            story.start_at(self.document, "SW.MinecartStation.PlainsA2.Central")
        # An area no save has named stays out of the save: the station changes, and the area is left as it was.
        self.document["CharacterSaveV1"]["WorldExploration"]["DiscoveredMinecartStationTags"].append("SW.MinecartStation.DesertA1.Cliffs")
        story.start_at(self.document, "SW.MinecartStation.DesertA1.Cliffs")
        self.assertEqual((story.last_station(self.document), story.area(self.document)), ("SW.MinecartStation.DesertA1.Cliffs", "SW.Area.Town"))
        # A save that doesn't say where its hero was last has nowhere to change.
        self.assertEqual(story.start_points(hero_save()), [])
        with self.assertRaisesRegex(ValueError, "doesn't say where the hero was last"):
            story.start_at(hero_save(), "SW.MinecartStation.Town")

    def test_a_stations_area_is_one_a_save_has_named(self):
        self.assertEqual([story.area_of(f"SW.MinecartStation.{tag}") for tag in ("Town", "Town.Fountain", "ForestA1.Outpost", "Forest.A1.DangerZone", "PlainsA2.Central", "DesertA1.Cliffs", "Odd")],
                         ["SW.Area.Town", "SW.Area.Town", "SW.Area.Forest.A1", "SW.Area.Forest.A1", "SW.Area.Plains.A2", None, None])

    def test_says_what_changed(self):
        before = copy.deepcopy(self.document)
        self.assertEqual(story.changes(before, self.document), [])
        story.finish(self.document, "CA04")
        story.start_over(self.document, "CA01")
        story.add(self.document, "PLa2_S15_A")
        self.quests["Quests"][2]["State"] = "Active"
        story.track(self.document, "FOa1_S10_A")
        story.start_at(self.document, "SW.MinecartStation.Town")
        lines = [
            "Quest The Illagers from the Rift (CA01): started over", "Quest The Missing Note Blocks (CA04): finished", "Quest The Cleric's Apprentice (FOa1_S10_A): available → active",
            "Quest Hiking Frozen Highlands (CA05): added, available", "Quest CA04_BR: added, available", "Quest PLa2_S15_A: added, available",
            "Quest tracked: The Cleric's Apprentice (FOa1_S10_A)", "Starts at: Haven Station, in Brave Haven",
        ]
        self.assertEqual(story.changes(before, self.document), lines)
        self.assertEqual(describe_changes(before, self.document), lines)  # and so does the list shown before saving
        # A step that moved with its quest standing as it did, and a quest that's gone.
        after = copy.deepcopy(before)
        after["CharacterSaveV1"]["quest"]["Quests"][1]["TaskData"][1]["State"] = "Completed"
        del after["CharacterSaveV1"]["quest"]["Quests"][2]
        after["CharacterSaveV1"]["quest"]["FocusedQuestId"] = ""
        self.assertEqual(story.changes(before, after), [
            "Quest The Missing Note Blocks (CA04): 2 of 2 steps done (it was 1)", "Quest The Cleric's Apprentice (FOa1_S10_A): taken out", "Quest tracked: none",
        ])


class RealListStoryTests(unittest.TestCase):
    """What the editor's real list of the world knows about how quests follow each other."""

    @classmethod
    def setUpClass(cls):
        tests.use_world_list(tests.REAL_WORLD_FILE)
        cls.world = copy.deepcopy(world.known())

    @classmethod
    def tearDownClass(cls):
        tests.use_world_list(tests.PINNED_WORLD_FILE)

    def test_what_follows_a_quest_is_quests_it_knows(self):
        quests = self.world["quests"]
        self.assertGreaterEqual(len(self.world["follows"]), 6)
        for name, came in self.world["follows"].items():
            self.assertIn(name, quests)
            self.assertTrue(came and len(set(came)) == len(came) and name not in came, name)
            for quest in came:
                self.assertTrue(quests.get(quest), f"{name} is followed by {quest}, whose steps aren't known")
        self.assertEqual(self.world["follows"]["CA03"], ["CA04", "CA03_BR"])

    def test_a_count_is_of_a_step_it_knows(self):
        steps = {step for listed in self.world["quests"].values() for step in listed}
        self.assertGreaterEqual(len(self.world["counts"]), 150)
        for step, count in self.world["counts"].items():
            self.assertIn(step, steps)
            self.assertTrue(isinstance(count, int) and not isinstance(count, bool) and 0 < count < 1000, step)
        self.assertEqual((self.world["counts"]["CA00_K01"], self.world["counts"]["CA01_K02"]), (5, 5))

    def test_every_quest_has_a_place_in_the_list_and_every_station_an_area(self):
        groups = {story.group_of(name) for name in self.world["quests"]}
        self.assertEqual(sorted(groups, key=story.group_order)[0], "Main story")
        self.assertTrue(all(group == "Main story" or group == "Other quests" or group.startswith("Side quests: ") for group in groups), groups)
        for tag in self.world["stations"] + [story.TOWN_FOUNTAIN]:
            self.assertRegex(story.area_of(tag) or "", r"^SW\.Area\.[A-Za-z]+(\.A\d)?$", tag)


if __name__ == "__main__":
    unittest.main()
