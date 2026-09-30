import unittest

from dungeons2_editor import document as doc

SAMPLE = {
    "blobs": [
        {"masterVolume": 60, "name": "Audio"},
        {"unlockedTutorials": [{"tagName": "SW.UI.TutorialLog.Basic.Jump"}], "ids": ["a", "b"], "name": "General"},
    ]
}


class LabelTests(unittest.TestCase):
    def test_list_items_are_named_after_their_name_field(self):
        self.assertEqual(doc.describe_path(SAMPLE, ("blobs", 0, "masterVolume")), "blobs › Audio › masterVolume")
        self.assertEqual(doc.describe_path(SAMPLE, ("blobs", 1, "unlockedTutorials", 0)), "blobs › General › unlockedTutorials › SW.UI.TutorialLog.Basic.Jump")
        self.assertEqual(doc.describe_path(SAMPLE, ("blobs", 1, "ids", 1)), "blobs › General › ids › #2")

    def test_walk_visits_every_node(self):
        paths = [path for path, _, _ in doc.walk(SAMPLE)]
        self.assertIn(("blobs", 1, "unlockedTutorials", 0, "tagName"), paths)
        self.assertEqual(len(paths), len(set(paths)))


class ParseInputTests(unittest.TestCase):
    def test_values_keep_their_kind(self):
        self.assertIs(doc.parse_input("false", True), False)
        self.assertEqual(doc.parse_input(" 85 ", 60), 85)
        self.assertIsInstance(doc.parse_input("85", 0.5), int)
        self.assertEqual(doc.parse_input("0.25", 60), 0.25)
        self.assertEqual(doc.parse_input("85", "text"), "85")
        self.assertEqual(doc.parse_input("12", None), 12)
        self.assertEqual(doc.parse_input("hello", None), "hello")

    def test_bad_input_is_rejected(self):
        for text, original in (("maybe", True), ("lots", 60), ("nan", 1.5), ("inf", 1)):
            with self.assertRaises(ValueError):
                doc.parse_input(text, original)


class DiffTests(unittest.TestCase):
    def test_reports_leaf_changes_additions_and_removals(self):
        new = {"blobs": [{"masterVolume": 85, "name": "Audio"}, {"unlockedTutorials": [], "ids": ["a", "b", "c"], "name": "General"}]}
        changes = doc.diff(SAMPLE, new)
        self.assertEqual(
            changes,
            [
                (("blobs", 0, "masterVolume"), 60, 85),
                (("blobs", 1, "unlockedTutorials", 0), {"tagName": "SW.UI.TutorialLog.Basic.Jump"}, doc.MISSING),
                (("blobs", 1, "ids", 2), doc.MISSING, "c"),
            ],
        )

    def test_equal_numbers_are_not_changes_but_bool_vs_number_is(self):
        self.assertEqual(doc.diff({"a": 60}, {"a": 60.0}), [])
        self.assertEqual(doc.diff({"a": 1}, {"a": True}), [(("a",), 1, True)])


if __name__ == "__main__":
    unittest.main()
