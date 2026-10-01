import unittest
import urllib.parse

from dungeons2_editor import share_ids
from dungeons2_editor.hero import Hero

from .helpers import hero_item, hero_save


class ShareIdsTests(unittest.TestCase):
    def test_lists_ids_the_editor_does_not_know(self):
        save = hero_save()
        save["CharacterSaveV1"]["Inventory"]["Entries"] += [
            hero_item("SW.Item.SomethingNew", seed=31),  # not in the editor's list
            hero_item("SW.Item.Claymore", seed=32),  # in the list as a guess
            hero_item("SW.Item.Cosmetic.Cape.Other", seed=33),  # cosmetics are left out
        ]
        found = dict(share_ids.unknown_ids([Hero(save)]))
        self.assertIn("new to the editor", found["SW.Item.SomethingNew"])
        self.assertEqual(found["SW.Item.Claymore"], "Claymore: confirms the editor's guess")
        self.assertIn("what's it called in the game?", found["SW.Item.CurvedGreatsword"])  # its name comes from its ID
        self.assertNotIn("SW.Item.Sword", found)  # confirmed, with its name
        self.assertFalse([tag for tag in found if "Cosmetic" in tag])

    def test_report_holds_only_item_ids(self):
        report = share_ids.report_text([Hero(hero_save())], "9.9.9")
        self.assertTrue(all(line.startswith("SW.Item.") for line in report.splitlines()))
        self.assertNotIn("00000000-0000-1000-8000-000000000002", report)  # the character ID stays out

    def test_issue_link_fills_in_the_form(self):
        url = share_ids.issue_url("SW.Item.X - Thing", "9.9.9")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertTrue(url.startswith(share_ids.ISSUE_URL + "?"))
        self.assertEqual((query["template"], query["ids"], query["version"]), (["item-ids.yml"], ["SW.Item.X - Thing"], ["9.9.9"]))


if __name__ == "__main__":
    unittest.main()
