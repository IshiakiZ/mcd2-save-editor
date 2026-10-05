import unittest
import urllib.parse

from dungeons2_editor import share_ids
from dungeons2_editor.hero import Hero

from .helpers import hero_item, hero_save, talisman_item


class ShareIdsTests(unittest.TestCase):
    def test_lists_ids_the_editor_does_not_know(self):
        save = hero_save()
        save["CharacterSaveV1"]["Inventory"]["Entries"] += [
            hero_item("SW.Item.SomethingNew", seed=31, unseen=False),  # not in the editor's list
            hero_item("SW.Item.Battlestaff", seed=32, unseen=False),  # in the list as a guess
            hero_item("SW.Item.Cosmetic.Cape.Other", seed=33, unseen=False),  # cosmetics are left out
            hero_item("SW.Item.Artifact.HasteMushroom", seed=34, unseen=False),  # in the list, but its name comes from its ID
            hero_item("SW.Item.Mace_Unique1", rarity="Unique", seed=35, unseen=False),  # a Unique's own ID that hasn't been seen before
            hero_item("SW.Item.Sword_Unique1", rarity="Unique", seed=36, unseen=False),  # one the list already has
        ]
        found = dict(share_ids.unknown_ids([Hero(save)]))
        self.assertEqual(found["SW.Item.SomethingNew"], "new to the editor (melee), what's it called in the game? [kept by the game]")
        self.assertEqual(found["SW.Item.Battlestaff"], "Battlestaff: confirms the editor's guess [kept by the game]")
        self.assertIn("what's it called in the game?", found["SW.Item.Artifact.HasteMushroom"])
        self.assertEqual(found["SW.Item.Mace_Unique1"], "Carapace Mace (the Unique Mace): confirms the editor's guess [kept by the game]")
        for known in ("SW.Item.Sword", "SW.Item.Sword_Unique1", "SW.Item.CurvedGreatsword"):  # confirmed, with their names
            self.assertNotIn(known, found)
        self.assertFalse([tag for tag in found if "Cosmetic" in tag])

    def test_an_id_only_the_editor_wrote_is_not_reported(self):
        # Adding an item under a guessed ID puts that ID in the save. That's the editor's guess, not the game's word.
        save = hero_save()
        hero = Hero(save)
        template = save["CharacterSaveV1"]["Inventory"]["Entries"][0]
        hero.add_item("SW.Item.Battlestaff", template)
        hero.add_item("SW.Item.Mace_Unique1", template, rarity="Unique")  # the Carapace Mace, under the ID its pattern gives
        self.assertTrue({"SW.Item.Battlestaff", "SW.Item.Mace_Unique1"} <= hero.seen_item_types())
        self.assertEqual(share_ids.unknown_ids([hero]), [])
        # Found in the game instead, they are: the collections are the game's own list, and so is the merchant's stock.
        save["CharacterSaveV1"]["CollectionsStats"]["CollectedWeaponsUnique"] = ["SW.Item.Mace_Unique1"]
        save["CharacterSaveV1"]["Inventory"]["Entries"].append(hero_item("SW.Item.Battlestaff", slot="SW.ItemSlot.Inventory.VillageMerchant.Tier0", seed=37))
        self.assertEqual(
            share_ids.unknown_ids([hero]),
            [
                ("SW.Item.Battlestaff", "Battlestaff: confirms the editor's guess [in the merchant's stock]"),
                ("SW.Item.Mace_Unique1", "Carapace Mace (the Unique Mace): confirms the editor's guess [in the collections]"),
            ],
        )

    def test_a_talismans_effect_is_shared_until_the_editor_knows_it(self):
        save = hero_save()
        save["CharacterSaveV1"]["Inventory"]["Entries"] += [
            talisman_item("SW.Item.Talisman.AmmoCapacity", "AmmoCapacity", (1.1, 1.2, 1.4), level=1, xp=300, seed=51),  # effect not in the list
            talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", seed=52),  # the list has this one's effect
            hero_item("SW.Item.Talisman.Brawling", power=4, seed=53),  # added by an older editor: no effect to share
            talisman_item("SW.Item.Talisman.BrandNew", "BrandNew", (2, 3, 4), seed=54, unseen=False),  # not in the list at all
        ]
        hero = Hero(save)
        self.assertEqual(
            share_ids.talisman_effects([hero]),
            [
                ("SW.Item.Talisman.AmmoCapacity", "Twig of Dark Oak's effect: AmmoCapacity 1.1 (AmmoCapacity.I) / AmmoCapacity 1.2 (AmmoCapacity.II) / AmmoCapacity 1.4 (AmmoCapacity.III)"),
                ("SW.Item.Talisman.BrandNew", "Brand New's effect: BrandNew 2 (BrandNew.I) / BrandNew 3 (BrandNew.II) / BrandNew 4 (BrandNew.III)"),
            ],
        )
        report = share_ids.report_text([hero], "9.9.9").splitlines()
        self.assertIn("SW.Item.Talisman.BrandNew - new to the editor (talisman), what's it called in the game? [kept by the game]", report)
        self.assertEqual(sum(line.startswith("SW.Item.Talisman.AmmoCapacity - ") for line in report), 1)  # its ID was known already
        self.assertFalse([line for line in report if "HealthBoost" in line or "Brawling" in line])
        self.assertNotIn("300", "\n".join(report))  # how far you've levelled yours stays out
        # Levels laid out some other way aren't guessed at.
        self.assertEqual(share_ids.effect_text([{"LevelEffects": "?"}]), "")
        self.assertEqual(share_ids.effect_text([{"LevelEffects": []}, {"LevelEffects": [{"TypeTag": "Other.Thing", "Intensity": 0.5, "Quality": 2}]}]), "nothing / Other.Thing 0.5 quality 2 (?)")

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
