import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import tests
from dungeons2_editor import story, world
from dungeons2_editor.hero import describe_changes

from . import helpers
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
    "regions": {
        "SW.Region.Camp": {"corner": [0, 0], "size": [4, 3]},  # the hero has this one
        "SW.Area.Plains.A2.BossTower": {"corner": [-256, 128], "size": [2, 2]},
        # Two saves put this one in two places, so nothing says which is right: it isn't one to add.
        "SW.Region.Twice": {"corner": [0, 0], "size": [2, 2], "also": [{"corner": [64, 64], "size": [2, 2]}]},
    },
    "pieces": helpers.PIECES,
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

    def quest_with(self, name, state, *steps):
        """Give the hero a quest whose steps are (name, how it stands, its number)."""
        self.quests["Quests"].append({"QuestName": name, "State": state, "TaskData": [{"TaskName": f"{name}_{step}", "State": how, "PartialProgress": count} for step, how, count in steps]})

    def test_a_finished_step_carries_the_number_a_save_holds_with_it(self):
        # What a save holds with a finished step: 1 for one to interact with something (all but two of those the game
        # has saved), the number a save has shown for a step to defeat enemies, and none for the rest.
        self.quest_with("CA05", "Active", ("I01", "Completed", 1), ("I02", "Active", 0), ("K01", "Active", 2), ("K02", "NotSet", 0), ("E01", "NotSet", 0), ("Sequence01", "Active", 0))
        self.quest_with("CA07", "Active", ("I12", "NotSet", 0), ("I13", "NotSet", 0))
        story.finish(self.document, "CA05")
        story.finish(self.document, "CA07")
        self.assertEqual([(step.short, step.count) for step in self.quest("CA05").steps], [("I01", 1), ("I02", 1), ("K01", 5), ("K02", 0), ("E01", 0), ("Sequence01", 0)])
        self.assertEqual([step.number_when_done for step in self.quest("CA05").steps], [1, 1, 5, None, 0, 0])  # nobody has sent K02 finished
        # CA07_I12 is one of the two the game finishes with no number: two heroes' lists have it so.
        self.assertEqual([(step.short, step.count) for step in self.quest("CA07").steps], [("I12", 0), ("I13", 1)])
        self.assertEqual((self.quest("CA05").unnumbered, self.quest("CA07").unnumbered, self.quest("CA05").to_finish), (0, 0, False))

    def test_a_quest_finished_without_its_numbers_is_finished_again(self):
        # As version 1.16.0 left a quest nobody had sent finished: done, its interact steps at nothing.
        self.quest_with("FOa1_S08_A", "Completed", ("E01", "Completed", 0), ("I01", "Completed", 0), ("I02", "Completed", 0), ("K01", "Completed", 0))
        self.quests["FocusedQuestId"] = "CA04"
        before = copy.deepcopy(self.document)
        quest = self.quest("FOa1_S08_A")
        self.assertEqual((quest.state, quest.unnumbered, quest.to_finish, [step.lacks_its_number for step in quest.steps]), ("Completed", 2, True, [False, True, True, False]))
        self.assertIn("FOa1_S08_A", [found.name for found in story.to_finish(self.document)])
        self.assertEqual(story.finish(self.document, "FOa1_S08_A"), [])  # nothing opens: it was finished already
        quest = self.quest("FOa1_S08_A")
        self.assertEqual(([step.count for step in quest.steps], quest.unnumbered, quest.to_finish, story.tracked(self.document)), ([0, 1, 1, 0], 0, False, "CA04"))
        self.assertEqual(story.changes(before, self.document), ["Quest FOa1_S08_A: 2 finished steps given their numbers"])
        with self.assertRaisesRegex(ValueError, "FOa1_S08_A is finished already"):
            story.finish(self.document, "FOa1_S08_A")

    def test_finishes_all_of_a_part_of_the_game_or_the_whole_of_it(self):
        self.assertEqual([quest.name for quest in story.to_finish(self.document, "Main story")], ["CA04", "CA04_BR", "CA05"])
        self.assertEqual([quest.name for quest in story.to_finish(self.document)], ["CA04", "CA04_BR", "CA05", "FOa1_S10_A", "PLa2_S15_A", "CT_S01_A"])
        self.assertEqual(story.to_finish(self.document, "Side quests: Nowhere"), [])
        done = story.finish_all(self.document, [quest.name for quest in story.to_finish(self.document, "Main story")])
        # CA04's finishing opens CA05 and CA04_BR, which are then finished in their turn; neither had been met.
        self.assertEqual((done.finished, done.added, done.opened), (("CA04", "CA04_BR", "CA05"), ("CA04_BR", "CA05"), ()))
        self.assertEqual([(quest.name, quest.state) for quest in story.quests(self.document)],
                         [("CA01", "Completed"), ("CA04", "Completed"), ("FOa1_S10_A", "Available"), ("CA05", "Completed"), ("CA04_BR", "Completed")])
        self.assertEqual((story.to_finish(self.document, "Main story"), story.tracked(self.document)), ([], ""))
        # The whole game: what's left, with the ones the hero hasn't met added first. A finished quest is passed over.
        done = story.finish_all(self.document, ["CA01"] + [quest.name for quest in story.to_finish(self.document)])
        self.assertEqual((done.finished, done.added), (("FOa1_S10_A", "PLa2_S15_A", "CT_S01_A"), ("PLa2_S15_A", "CT_S01_A")))
        self.assertTrue(all(quest.state == "Completed" for quest in story.every(self.document)))
        self.assertEqual(story.finish_all(self.document, [quest.name for quest in story.every(self.document)]), story.Finished((), (), ()))

    def test_finishing_several_is_all_or_nothing(self):
        before = copy.deepcopy(self.document)
        with self.assertRaisesRegex(ValueError, "doesn't know its steps"):
            story.finish_all(self.document, ["CA04", "PLa2_S15_A", "CA09"])  # the last is one the editor has never seen
        self.assertEqual(self.document, before)
        with self.assertRaisesRegex(ValueError, "keeps no quests yet"):
            story.finish_all(hero_save(), ["CA04"])
        # One that opens a quest outside the ones asked for leaves that one available, as the game would.
        done = story.finish_all(self.document, ["CA04"])
        self.assertEqual((done.finished, done.added, done.opened), (("CA04",), (), ("CA05", "CA04_BR")))

    def test_discovers_the_whole_map(self):
        fog = self.document["CharacterSaveV1"]["WorldExploration"]["SavedFogOfWarExploration"]["Items"]
        self.assertEqual(story.map_explored(self.document), (5, 16, 2))  # five squares seen at all, of the camp's twelve and the meadow's four
        self.assertEqual(story.map_to_discover(self.document), (15, ["SW.Area.Plains.A2.BossTower"]))  # one square is all clear already
        before = copy.deepcopy(self.document)
        untouched = copy.deepcopy({key: value for key, value in self.document["CharacterSaveV1"]["WorldExploration"].items() if key != "SavedFogOfWarExploration"})
        self.assertEqual(story.discover_map(self.document), (15, ["SW.Area.Plains.A2.BossTower"]))
        self.assertEqual([(item["Tag"], item["Data"]) for item in fog[:2]], [("SW.Region.Camp", [255] * 12), ("SW.Area.Meadow.R1", [255] * 4)])
        # A region the hero hasn't been in, as another hero's save holds it: its tag, its squares, its corner, its size.
        self.assertEqual(fog[2:], [{"Tag": "SW.Area.Plains.A2.BossTower", "Data": [255] * 4, "WorldPosition": {"X": -256, "Y": 128}, "Size": {"X": 2, "Y": 2}}])
        self.assertEqual(list(fog[2]), ["Tag", "Data", "WorldPosition", "Size"])
        self.assertEqual((story.map_explored(self.document), story.map_to_discover(self.document)), ((20, 20, 3), (0, [])))
        # Nothing else of the world: no door, no station, no chest is found by it.
        self.assertEqual({key: value for key, value in self.document["CharacterSaveV1"]["WorldExploration"].items() if key != "SavedFogOfWarExploration"}, untouched)
        line = "Map: 20 of 20 squares explored in 3 regions (it was 5 of 16 in 2)"
        self.assertEqual((story.changes(before, self.document), describe_changes(before, self.document)), ([line], [line]))
        # A picture that isn't laid out the way a save's are is left alone, and a save with no map has none to discover.
        odd = hero_with_a_world()
        odd["CharacterSaveV1"]["WorldExploration"]["SavedFogOfWarExploration"]["Items"][1]["Size"] = {"X": "two", "Y": 2}
        story.discover_map(odd)
        self.assertEqual(odd["CharacterSaveV1"]["WorldExploration"]["SavedFogOfWarExploration"]["Items"][1]["Data"], [0, 7, 0, 0])
        self.assertEqual(story.map_explored(hero_save()), (0, 0, 0))
        for change in (story.discover_map, story.map_to_discover):
            with self.assertRaisesRegex(ValueError, "keeps no map yet"):
                change(hero_save())

    def test_opens_the_shortcuts_and_the_key_gates(self):
        place = self.document["CharacterSaveV1"]["WorldExploration"]
        # The hero has moved one rock out of the way and put a key in its lock: the lock is not the editor's to touch.
        place["SavedActorStates"] = [helpers.as_saved(helpers.ROCK_OPENED), helpers.as_saved(helpers.KEY_LOCK, 2, 1)]
        self.assertEqual([(piece.kind, piece.name, piece.open) for piece in story.pieces(self.document)], [
            ("shortcut", "Farm Bridge", False), ("shortcut", "Forest Roadblock", False), ("shortcut", "Meadow Roadblock", True),
            ("key gate", "Gold Key Gate Door", False), ("key gate", "MA2 Key Gate", False),
        ])  # no lock, no key, nothing inside a dungeon, nothing saves have shown held two ways, nothing the editor has no word for
        self.assertEqual((story.pieces_open(self.document, story.SHORTCUTS), story.pieces_open(self.document, story.GATES)), ((1, 3), (0, 2)))
        before = copy.deepcopy(self.document)
        untouched = copy.deepcopy({key: value for key, value in place.items() if key != "SavedActorStates"})
        self.assertEqual(story.open_pieces(self.document, story.SHORTCUTS), 2)
        # Each as a save holds an open one, after the ones the save had: its name, the state it was in, the state it's in, a version.
        self.assertEqual(place["SavedActorStates"], [
            helpers.as_saved(helpers.ROCK_OPENED), helpers.as_saved(helpers.KEY_LOCK, 2, 1), helpers.as_saved(helpers.BRIDGE), helpers.as_saved(helpers.ROCK),
        ])
        self.assertEqual(list(place["SavedActorStates"][2]), ["SoftObjectPath", "PreviousState", "CurrentState", "Version"])
        self.assertEqual((story.pieces_open(self.document, story.SHORTCUTS), story.pieces_open(self.document, story.GATES)), ((3, 3), (0, 2)))
        self.assertEqual((story.open_pieces(self.document, story.SHORTCUTS), len(place["SavedActorStates"])), (0, 4))  # nothing left to open
        line = "Shortcuts: 3 of the 3 the editor knows open (it was 1)"
        self.assertEqual((story.changes(before, self.document), describe_changes(before, self.document)), ([line], [line]))
        # With the gates go the lock that stands by one of them and the key that was put there with that lock: the lock
        # has its key already, so it's the key that's left to mark as taken (the furthest state a save has shown it in).
        self.assertEqual([(piece.kind, piece.name, piece.opened, piece.open) for piece in story.gate_parts(self.document)],
                         [("key lock", "Key Golem Lock", (2, 1), True), ("key", "Key Golem Spawner", (1, 2), False)])
        self.assertEqual(story.open_pieces(self.document, story.GATES), 3)
        self.assertEqual(place["SavedActorStates"][4:], [helpers.as_saved(helpers.KEY_GATE), helpers.as_saved(helpers.CAMP_GATE), helpers.as_saved(helpers.THE_KEY, 1, 2)])
        self.assertEqual(story.changes(before, self.document), [
            line, "Key gates: 2 of the 2 the editor knows open (it was 0)", "Locks and keys of those gates: 2 of 2 as they are once a key is in (it was 1)"])
        self.assertEqual((story.gate_parts_to_use(self.document), story.open_pieces(self.document, story.GATES)), ([], 0))
        # A gate that stands open with its keyhole still there, as version 1.16.1's first try left one: the lock and the key are still to mark.
        left = hero_with_a_world()
        left["CharacterSaveV1"]["WorldExploration"]["SavedActorStates"] = [helpers.as_saved(helpers.KEY_GATE), helpers.as_saved(helpers.CAMP_GATE)]
        self.assertEqual((story.pieces_to_open(left, story.GATES), len(story.gate_parts_to_use(left)), story.open_pieces(left, story.GATES)), ([], 2, 2))
        self.assertEqual(left["CharacterSaveV1"]["WorldExploration"]["SavedActorStates"][2:], [helpers.as_saved(helpers.KEY_LOCK, 2, 1), helpers.as_saved(helpers.THE_KEY, 1, 2)])
        # A lock that stands by no gate the editor knows, and a key put there with no such lock, are nobody's to mark.
        self.assertFalse(any(piece.path in (helpers.CAVE_GATE, helpers.LIFT_BUTTON, helpers.ROCK_TWO_WAYS) for piece in story.gate_parts(left)))
        # The key in its lock is as it was, and so is everything else of the world.
        self.assertEqual(place["SavedActorStates"][1], helpers.as_saved(helpers.KEY_LOCK, 2, 1))
        self.assertEqual({key: value for key, value in place.items() if key != "SavedActorStates"}, untouched)
        # One the save holds some other way is set to the open one, where it stands in the save.
        odd = hero_with_a_world()
        odd["CharacterSaveV1"]["WorldExploration"]["SavedActorStates"] = [helpers.as_saved(helpers.ROCK, 1, 0)]
        self.assertEqual(story.open_pieces(odd, story.SHORTCUTS), 3)
        self.assertEqual(odd["CharacterSaveV1"]["WorldExploration"]["SavedActorStates"][0], helpers.as_saved(helpers.ROCK))
        # A save that keeps no such list has none open, and none can be added to it.
        self.assertEqual(story.pieces_open(hero_save(), story.SHORTCUTS), (0, 3))
        with self.assertRaisesRegex(ValueError, "keeps no list of the world's rocks and gates yet"):
            story.open_pieces(hero_save(), story.SHORTCUTS)

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


class StepByStepTests(unittest.TestCase):
    """Moving a quest on one step at a time, the way the game does."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        path = Path(cls.folder.name) / "world.json"
        path.write_text(json.dumps(helpers.STEPPING), encoding="utf-8")
        tests.use_world_list(path)

    @classmethod
    def tearDownClass(cls):
        tests.use_world_list(tests.PINNED_WORLD_FILE)
        cls.folder.cleanup()

    def hero(self, *quests, focus=""):
        document = hero_with_a_world()
        document["CharacterSaveV1"]["quest"] = {"FocusedQuestId": focus, "Quests": list(quests)}
        return document

    def stands(self, document, name):
        quest = next(quest for quest in story.quests(document) if quest.name == name)
        marks = {story.DONE: "+", story.ACTIVE: "~", story.NOT_SET: ""}
        return quest.state, " ".join(step.short + marks[step.state] + (str(step.count) if step.count else "") for step in quest.steps)

    def test_begins_a_quest_and_finishes_it_step_by_step(self):
        document = self.hero(helpers.a_quest("QA"), focus="QA")
        self.assertEqual((story.why_no_step(document, "QA"), story.steps_it_is_on(document, "QA")), ("", []))
        # Begun: the quest is active, with its own group and the first member of it.
        done = story.step(document, "QA")
        self.assertEqual(done, story.Stepped("QA", True, "", ("QA_E01",), False, ()))
        self.assertEqual(self.stands(document, "QA"), ("Active", "E01~ Standard01 I01 K01 Sequence02 E02 E03 I02 Sequence01~"))
        # The place reached: the turn of the group whose members go all at once, both of them.
        done = story.step(document, "QA")
        self.assertEqual((done.begun, done.step, done.now_on, done.ended), (False, "QA_E01", ("QA_I01", "QA_K01"), False))
        self.assertEqual(self.stands(document, "QA"), ("Active", "E01+ Standard01~ I01~ K01~ Sequence02 E02 E03 I02 Sequence01~"))
        # Either of the two can be finished first; a step to defeat enemies gets the number a save holds with it once it's done.
        with self.assertRaisesRegex(ValueError, "isn't on the step QA_E02"):
            story.step(document, "QA", "QA_E02")
        self.assertEqual(story.step(document, "QA", "QA_K01").now_on, ("QA_I01",))
        self.assertEqual(self.stands(document, "QA"), ("Active", "E01+ Standard01~ I01~ K01+3 Sequence02 E02 E03 I02 Sequence01~"))
        # The other one: the group is done, and the next group's turn comes, on its first member. An interact step gets its 1.
        self.assertEqual(story.step(document, "QA").now_on, ("QA_E02",))
        self.assertEqual(self.stands(document, "QA"), ("Active", "E01+ Standard01+ I01+1 K01+3 Sequence02~ E02~ E03 I02 Sequence01~"))
        self.assertEqual(story.step(document, "QA").now_on, ("QA_E03",))
        self.assertEqual(story.step(document, "QA").now_on, ("QA_I02",))
        self.assertEqual(self.stands(document, "QA"), ("Active", "E01+ Standard01+ I01+1 K01+3 Sequence02+ E02+ E03+ I02~ Sequence01~"))
        before = copy.deepcopy(document)
        # The last step: the quest is finished the way Finish it leaves one, with what follows it listed and nothing tracked.
        done = story.step(document, "QA")
        self.assertEqual(done, story.Stepped("QA", False, "QA_I02", (), True, ("QC",)))
        self.assertEqual(self.stands(document, "QA"), ("Completed", "E01+ Standard01+ I01+1 K01+3 Sequence02+ E02+ E03+ I02+1 Sequence01+"))
        self.assertEqual((self.stands(document, "QC"), story.tracked(document)), (("Available", "E01 Sequence01"), ""))
        self.assertEqual(story.changes(before, document), ["Quest QA: finished", "Quest QC: added, available", "Quest tracked: none"])
        with self.assertRaisesRegex(ValueError, "QA is finished: a step can be finished in a quest that's active, and a quest that's available can be begun"):
            story.step(document, "QA")
        # Finishing it whole from the start comes to the very same save.
        whole = self.hero(helpers.a_quest("QA"), focus="QA")
        story.step(whole, "QA")
        story.finish(whole, "QA")
        self.assertEqual(whole["CharacterSaveV1"]["quest"], document["CharacterSaveV1"]["quest"])

    def test_leaves_a_quest_alone_where_the_rules_do_not_reach(self):
        # A choice between steps comes next: no save has shown one under way, so nothing is changed and the editor says so.
        document = self.hero(helpers.a_quest("QB", "Active", E01="Active", Sequence01="Active"), helpers.a_quest("QD"))
        before = copy.deepcopy(document)
        with self.assertRaisesRegex(ValueError, "The next step of QB is a choice between steps, and the editor hasn't seen how the game saves a choice that's under way"):
            story.step(document, "QB")
        self.assertEqual(document, before)
        self.assertEqual(story.why_no_step(document, "QB"), "")  # it has a step to finish: only finishing it shows what comes next
        # A quest whose groups the list doesn't have, one the hero hasn't met, and one with no step under way.
        self.assertIn("The editor doesn't know how the steps of QD hang together", story.why_no_step(document, "QD"))
        with self.assertRaisesRegex(ValueError, "doesn't know how the steps of QD hang together, so it can't move it on by one. Finish it whole instead."):
            story.step(document, "QD")
        with self.assertRaisesRegex(ValueError, "hasn't met the quest QA"):
            story.step(document, "QA")
        stuck = self.hero(helpers.a_quest("QA", "Active", Sequence01="Active"))
        self.assertEqual(story.why_no_step(stuck, "QA"), "No step of QA is active, so there's none to finish. Finish it whole instead.")
        begun = self.hero(helpers.a_quest("QA"))
        with self.assertRaisesRegex(ValueError, "QA isn't begun yet: it has no step to finish"):
            story.step(begun, "QA", "QA_E01")
        self.assertEqual(document, before)


class TheGamesWordsTests(unittest.TestCase):
    """A quest by the game's name for it and a step by the game's words, where the editor's list has them from the
    game's quest text; MetaBot's name where it hasn't."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "world.json"
        path.write_text(json.dumps({**helpers.STEPPING, "names": {"QA": "The Made-up Quest", "CA04": "Another Name"}, "labels": {"QA_K01": "Defeat the monsters"}}), encoding="utf-8")
        tests.use_world_list(path)
        self.addCleanup(tests.use_world_list, tests.PINNED_WORLD_FILE)

    def test_names_quests_and_steps_the_way_the_game_does(self):
        from dungeons2_editor import recorder

        self.assertEqual((story.label("QA"), story.label("QB"), story.label("CA04"), story.label("CA01")),
                         ("The Made-up Quest (QA)", "QB", "Another Name (CA04)", "The Illagers from the Rift (CA01)"))
        self.assertEqual((recorder.quest_name("QA"), recorder.quest_name("QB")), ("QA (The Made-up Quest)", "QB"))
        document = hero_with_a_world()
        document["CharacterSaveV1"]["quest"] = {"FocusedQuestId": "", "Quests": [helpers.a_quest("QA")]}
        quest = next(quest for quest in story.quests(document) if quest.name == "QA")
        self.assertEqual((quest.title, {step.short: step.words for step in quest.steps if step.words}), ("The Made-up Quest", {"K01": "Defeat the monsters"}))


class StepsAsTheGameTookThemTests(unittest.TestCase):
    """The same rules, with the editor's real list, replayed against what the game did: each line of the fixture is a
    quest as one save of a play recording held it, and follows from the line before."""

    @classmethod
    def setUpClass(cls):
        tests.use_world_list(tests.REAL_WORLD_FILE)

    @classmethod
    def tearDownClass(cls):
        tests.use_world_list(tests.PINNED_WORLD_FILE)

    def test_every_move_the_game_made_is_the_one_the_rules_make(self):
        lines = [line for line in (Path(__file__).resolve().parent / "data" / "quest-steps.txt").read_text(encoding="utf-8").splitlines() if line.startswith("quest ")]
        groups = world.known()["groups"]
        moves = {"begun": 0, "moved on": 0, "finished": 0}
        for earlier, later in zip(lines, lines[1:]):
            before, after = as_saved(earlier), as_saved(later)
            name = before["QuestName"]
            if after["QuestName"] != name:
                continue  # the next quest's first line
            document, stood = hero_with_a_world(), before["State"]
            document["CharacterSaveV1"]["quest"] = {"FocusedQuestId": "", "Quests": [before]}
            if stood == "Available":
                self.assertTrue(story.step(document, name).begun)
                moves["begun"] += 1
            todo = [task["TaskName"] for task, old in zip(after["TaskData"], before["TaskData"]) if task["State"] == "Completed" and old["State"] != "Completed" and task["TaskName"] not in groups]
            while todo:
                on = [step.name for step in story.steps_it_is_on(document, name)]
                ready = [step for step in todo if step in on]
                self.assertTrue(ready, (later, todo, on))
                story.step(document, name, ready[0])
                todo.remove(ready[0])
            mine = document["CharacterSaveV1"]["quest"]["Quests"][0]
            self.assertEqual(mine["State"], after["State"], later)
            self.assertEqual([(task["TaskName"], task["State"]) for task in mine["TaskData"]], [(task["TaskName"], task["State"]) for task in after["TaskData"]], later)
            # A finished step holds the number the game saved with it; one still under way counts as the game counted.
            for task, theirs in zip(mine["TaskData"], after["TaskData"]):
                if theirs["State"] == "Completed":
                    self.assertEqual(task["PartialProgress"], theirs["PartialProgress"], (task["TaskName"], later))
            if stood != "Available":
                moves["finished" if after["State"] == "Completed" else "moved on"] += 1
        # Three quests begun, forty-five moves along the way, and the two of them that the game went on to finish.
        self.assertEqual((len(lines), moves), (53, {"begun": 3, "moved on": 45, "finished": 2}))

    def test_the_list_knows_how_every_quest_hangs_together(self):
        known = world.known()
        for name, steps in known["quests"].items():
            entry = {"QuestName": name, "State": "Available", "TaskData": [{"TaskName": step, "State": "NotSet", "PartialProgress": 0} for step in steps]}
            self.assertIsNotNone(story._tree(entry), name)
            # Begun, every quest is on at least one step that isn't a group.
            document = hero_with_a_world()
            document["CharacterSaveV1"]["quest"] = {"FocusedQuestId": "", "Quests": [entry]}
            self.assertTrue(story.step(document, name).now_on, name)
        self.assertEqual({group["kind"] for group in known["groups"].values()}, {"Sequence", "Standard", "Selection"})
        self.assertEqual(sorted(name for name, group in known["groups"].items() if group["kind"] == "Selection"),
                         ["MEa1_S06_A_Selection01", "MEa1_S06_A_Selection02", "MEa1_S06_A_Selection03", "MEa1_S06_A_Selection04"])


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

    def test_the_quests_the_game_offers_again_are_quests_it_knows(self):
        from dungeons2_editor import story_dialog

        # By the game's own quest tables: one golem to rescue, and the eight boss fights. Each is a quest the list knows.
        again = self.world["again"]
        self.assertEqual(sorted(again), ["CA02_B_BR", "CA03_BR", "CA04_BR", "CA05_BR", "CA07_BR", "CA09_BR", "CA10_BR", "CA10_BR_B", "CT_S01_A"])
        self.assertEqual({rule for rule in again.values()}, {"TimeBased", "WorldReset"})
        self.assertTrue(all(name in self.world["quests"] for name in again))
        self.assertEqual([story.comes_back(name) for name in ("CT_S01_A", "CA03_BR", "CT_S02_A", "CT_S03_A", "CT_S04_A", "CA03", "Unheard of")], [True, True, False, False, False, False, False])
        golem = story.Quest("CT_S01_A", story.DONE, tuple(story.Step(step, story.DONE, 1, "CT_S01_A") for step in self.world["quests"]["CT_S01_A"]), False)
        other = story.Quest("CT_S02_A", story.DONE, tuple(story.Step(step, story.DONE, 1, "CT_S02_A") for step in self.world["quests"]["CT_S02_A"]), False)
        fight = story.Quest("CA03_BR", None, tuple(story.Step(step, story.NOT_SET, 0, "CA03_BR") for step in self.world["quests"]["CA03_BR"]), False)
        self.assertTrue(story_dialog.what_it_does(golem, {}).endswith("The game lets a hero do this quest again: once it's finished the game offers it once more, and "
                                                                     "it comes back on the game's map as a new side quest."))
        self.assertIn("comes back on the game's map", story_dialog.what_it_does(fight, {}))  # said before the quest is met, too
        self.assertNotIn("comes back", story_dialog.what_it_does(other, {}))  # the other three golems are rescued once

    def test_every_defeat_step_has_its_number_and_every_quest_what_follows_it(self):
        # The fourteen numbers no save had shown came with the game's quest tables, which agree with all the saves did show.
        defeat = [step for steps in self.world["quests"].values() for step in steps if re.search(r"_K\d+$", step)]
        self.assertEqual((len(defeat), [step for step in defeat if step not in self.world["counts"]]), (32, []))
        self.assertEqual({step: self.world["counts"][step] for step in ("PLa1_S04_A_K01", "PLa2_S17_A_K02", "CA00_K01", "DEa1_S13_A_K01")}, {
            "PLa1_S04_A_K01": 3, "PLa2_S17_A_K02": 9, "CA00_K01": 5, "DEa1_S13_A_K01": 10})
        quest = story.Quest("PLa2_S17_A", story.DONE, tuple(story.Step(step, story.DONE, 0, "PLa2_S17_A") for step in self.world["quests"]["PLa2_S17_A"]), False)
        self.assertEqual([step.number_when_done for step in quest.steps if step.short.startswith("K")], [7, 9])
        # Every quest but the first waits for one other, so sixteen quests have something that follows them; one that
        # starts out unavailable (the merchant's) is opened some other way and follows nothing.
        follows = self.world["follows"]
        self.assertEqual(len(follows), 16)
        self.assertEqual((follows["CA04"], follows["CA00"], follows["MEa2_S02_A"]), (["CT_S01_A", "CT_S03_A", "CA07", "CA04_BR"], ["CA01"], ["MEa2_S03_A"]))
        after = [name for came in follows.values() for name in came]
        self.assertEqual((len(after), len(set(after)), "TOa1_S01_A" in after, "CA00" in after), (42, 42, False, False))

    def test_the_real_list_has_shortcuts_and_key_gates_to_open(self):
        from dungeons2_editor import recorder

        shortcuts, gates = story.pieces(hero_with_a_world(), story.SHORTCUTS), story.pieces(hero_with_a_world(), story.GATES)
        self.assertGreaterEqual(len(shortcuts), 13)
        self.assertGreaterEqual(len(gates), 11)
        for piece in shortcuts + gates:
            # Each is of the overworld, named the way a save names one, and held one way in every save that showed it.
            self.assertRegex(piece.path, r"^/Game/Spicewood/Maps/Overworld/Overworld/_Generated_/\w+\.Overworld:PersistentLevel\.BP_\w+_C_UAID_\w+$")
            self.assertEqual((piece.opened, piece.state, recorder.piece_kind(piece.path)), ((0, 1), None, piece.kind))
        self.assertEqual({piece.name for piece in gates}, {"Gold Key Gate Door", "Silver Key Gate Door", "Illager Concrete Gate7 Wide", "MA2 Key Gate"})
        self.assertTrue(all("Roadblock" in piece.name or "Bridge" in piece.name for piece in shortcuts))
        # The keys and their locks are in the list, and the ones the editor can tell to be those gates' own go with them:
        # a lock with its key in (2 then 1), a key taken (1 then 2).
        kinds = [recorder.piece_kind(piece["path"]) for piece in self.world["pieces"].values()]
        self.assertTrue(kinds.count(recorder.LOCK) >= 10 and kinds.count(recorder.KEY) >= 7)
        parts = story.gate_parts(hero_with_a_world())
        self.assertEqual(sorted({(piece.kind, piece.opened) for piece in parts}), [("key", (1, 2)), ("key lock", (2, 1))])
        self.assertTrue(sum(piece.kind == recorder.LOCK for piece in parts) >= 10 and sum(piece.kind == recorder.KEY for piece in parts) >= 7)
        self.assertTrue(all(story.OVERWORLD in piece.path and piece.state is None for piece in parts))
        from dungeons2_editor import world as the_world
        for lock, gate in story.SEEN_TOGETHER.items():  # the pair a recording saw change together is of the list's own pieces
            names = {the_world.piece_id(piece["path"]) for piece in self.world["pieces"].values()}
            self.assertTrue(lock in names and gate in names, lock)

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
