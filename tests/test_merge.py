import copy
import unittest

from dungeons2_editor import merge
from dungeons2_editor.hero import Hero, gear_slots

from .helpers import hero_item, hero_save


def by_tag(document, tag):
    return next(item for item in Hero(document).items() if item.tag == tag)


class ReapplyTests(unittest.TestCase):
    """The editor changed ``edited`` from ``original``; meanwhile the game saved ``newer``."""

    def setUp(self):
        self.original = hero_save()
        self.edited = copy.deepcopy(self.original)
        self.newer = copy.deepcopy(self.original)
        self.slots = {slot.label: slot for slot in gear_slots([])}

    def play(self):
        """What a play session does to the save: more XP, and a new item picked up at the front."""
        Hero(self.newer).set_attributes({"XP": 2000})
        self.newer["CharacterSaveV1"]["Inventory"]["Entries"].insert(0, hero_item("SW.Item.Bow", power=7, seed=777))

    def test_stats_and_items_are_reapplied_by_name_and_seed(self):
        hero = Hero(self.edited)
        hero.set_attributes({"Emeralds": 9_999})
        helmet = by_tag(self.edited, "SW.Item.MysticHelmet").index
        hero.update_item(helmet, rarity="Unique", power=50)
        self.play()
        merged, problems = merge.reapply(self.original, self.edited, self.newer)
        self.assertEqual(problems, [])
        result = Hero(merged)
        self.assertEqual((result.attribute("Emeralds"), result.attribute("XP")), (9_999, 2000))  # yours and the game's
        circlet = by_tag(merged, "SW.Item.MysticHelmet")
        self.assertEqual((circlet.rarity, circlet.power), ("Unique", 50))
        self.assertEqual(by_tag(merged, "SW.Item.Bow").power, 7)  # the game's new item is still there

    def test_added_and_deleted_items(self):
        hero = Hero(self.edited)
        hero.add_item("SW.Item.Axe", by_tag(self.edited, "SW.Item.Sword").entry, rarity="Rare", power=9)
        hero.remove_item(by_tag(self.edited, "SW.Item.Longbow").index)
        self.play()
        merged, problems = merge.reapply(self.original, self.edited, self.newer)
        self.assertEqual(problems, [])
        tags = [item.tag for item in Hero(merged).items()]
        self.assertIn("SW.Item.Axe", tags)
        self.assertNotIn("SW.Item.Longbow", tags)
        self.assertEqual(tags[0], "SW.Item.Bow")
        self.assertIn("SW.Item.Axe", merged["CharacterSaveV1"]["LootProgression"]["DiscoveredLoot"])

    def test_items_the_game_got_rid_of_or_equipped_are_reported(self):
        hero = Hero(self.edited)
        hero.update_item(by_tag(self.edited, "SW.Item.MysticHelmet").index, power=40)
        hero.remove_item(by_tag(self.edited, "SW.Item.Longbow").index)
        newer = Hero(self.newer)
        newer.remove_item(by_tag(self.newer, "SW.Item.MysticHelmet").index)  # salvaged in the game
        newer.equip(by_tag(self.newer, "SW.Item.Longbow").index, self.slots["Ranged weapon"])
        merged, problems = merge.reapply(self.original, self.edited, self.newer)
        self.assertEqual(len(problems), 2)
        self.assertIn("Mystic Circlet isn't in the newer save", problems[0])
        self.assertIn("Longbow is equipped in the newer save", problems[1])
        self.assertIn("SW.Item.Longbow", [item.tag for item in Hero(merged).items()])

    def test_your_equipped_item_wins_its_slot(self):
        Hero(self.edited).equip(by_tag(self.edited, "SW.Item.MysticHelmet").index, self.slots["Helmet"])
        newer = Hero(self.newer)
        index = newer.add_item("SW.Item.HoneyHelmet", by_tag(self.newer, "SW.Item.MysticHelmet").entry, slot=self.slots["Helmet"])
        self.assertEqual(newer.item(index).where, "Equipped (helmet)")
        merged, problems = merge.reapply(self.original, self.edited, self.newer)
        result = Hero(merged)
        self.assertEqual(result.equipped("SW.ItemSlot.Equipment.Armor.Helmet").tag, "SW.Item.MysticHelmet")
        self.assertEqual(by_tag(merged, "SW.Item.HoneyHelmet").where, "Inventory")
        self.assertEqual(problems, ["Unequipped Beekeeper Veil to make room for your Mystic Circlet."])

    def test_nothing_to_reapply(self):
        self.play()
        merged, problems = merge.reapply(self.original, self.edited, self.newer)
        self.assertEqual((merged, problems), (self.newer, []))
        self.assertIsNot(merged, self.newer)

    def test_other_saves_by_path(self):
        original = {"blobs": [{"name": "Audio", "masterVolume": 60}, {"name": "General", "tutorials": ["a"]}]}
        edited = copy.deepcopy(original)
        edited["blobs"][0]["masterVolume"] = 80
        edited["blobs"][1]["tutorials"][0] = "b"
        newer = copy.deepcopy(original)
        newer["blobs"][1]["tutorials"][0] = "c"  # the game changed the same list item
        merged, problems = merge.reapply(original, edited, newer)
        self.assertEqual(merged["blobs"][0]["masterVolume"], 80)
        self.assertEqual(merged["blobs"][1]["tutorials"], ["c"])
        self.assertEqual(len(problems), 1)


if __name__ == "__main__":
    unittest.main()
