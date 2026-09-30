import unittest

from dungeons2_editor import presets
from dungeons2_editor.hero import Hero, build_catalog

from .helpers import hero_item, hero_save


def by_title(title):
    return next(p for p in presets.PRESETS if p.title == title)


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.document = hero_save()
        self.hero = Hero(self.document)
        # A second hero who has already found a Lucky Clover and The Eye of Experience.
        other = hero_save()
        other["CharacterSaveV1"]["Inventory"]["Entries"] += [
            hero_item("SW.Item.Talisman.LuckyClover", power=-1, rarity="Common", seed=11),
            hero_item("SW.Item.Talisman.EyeOfExperience", power=-1, rarity="Common", seed=12),
        ]
        self.other = Hero(other)
        self.catalog = build_catalog([self.hero, self.other])

    def test_every_preset_explains_itself(self):
        for preset in presets.PRESETS:
            self.assertTrue(preset.title and preset.goal and preset.details)
            self.assertTrue(preset.sources)
            self.assertTrue(preset.stats or preset.items or preset.upgrade_gear)

    def test_finds_items_by_their_in_game_names(self):
        self.assertEqual(presets.find_item("The Eye of Experience", self.catalog).tag, "SW.Item.Talisman.EyeOfExperience")
        self.assertEqual(presets.find_item("Lucky Clover", self.catalog).tag, "SW.Item.Talisman.LuckyClover")
        self.assertEqual(presets.find_item("Mystic Circlet", self.catalog).tag, "SW.Item.MysticHelmet")  # known rename
        self.assertIsNone(presets.find_item("Emerald of Good Fortune", self.catalog))

    def test_most_money_fills_to_the_cap_and_lists_what_to_find(self):
        plan = presets.plan(by_title("Most money"), self.hero, self.catalog, power=1)
        self.assertEqual(plan.stats, {"Emeralds": 9_999})  # this hero has no Echo Shards stat
        self.assertEqual([k.name for k in plan.find], ["Emerald of Good Fortune"])
        self.assertIn("Lullaby Hills", plan.find[0].where)
        presets.apply(plan, self.hero, self.catalog)
        self.assertEqual(self.hero.attribute("Emeralds"), 9_999)

    def test_items_another_hero_found_can_be_added(self):
        plan = presets.plan(by_title("Most XP"), self.hero, self.catalog, power=1)
        self.assertEqual([kit.name for kit, _ in plan.add], ["The Eye of Experience"])
        presets.apply(plan, self.hero, self.catalog)
        added = next(item for item in self.hero.items() if item.tag == "SW.Item.Talisman.EyeOfExperience")
        self.assertEqual((added.power, added.where), (-1, "Inventory"))  # laid out like the saved copy
        again = presets.plan(by_title("Most XP"), self.hero, self.catalog, power=1)
        self.assertEqual([k.name for k in again.have], ["The Eye of Experience"])
        self.assertFalse(again.changes_anything)

    def test_most_powerful_upgrades_owned_gear_only(self):
        body = self.document["CharacterSaveV1"]
        body["Inventory"]["Entries"].append(hero_item("SW.Item.Artifact.FireworkQuiver", power=2, seed=13))
        plan = presets.plan(by_title("Most powerful"), self.hero, self.catalog, power=60)
        upgraded = {self.hero.item(index).tag: (rarity, power) for index, rarity, power in plan.upgrades}
        self.assertEqual(
            upgraded,
            {
                "SW.Item.MysticHelmet": ("Unique", 60),
                "SW.Item.Longbow": ("Unique", 60),
                "SW.Item.Sword": ("Unique", 60),
                "SW.Item.Artifact.FireworkQuiver": ("Special", 60),
            },
        )  # not the merchant's Curved Greatsword, not the cape
        self.assertIn("Sword: Common → Unique, power 1 → 60", presets.describe(plan, self.hero))
        presets.apply(plan, self.hero, self.catalog)
        sword = next(item for item in self.hero.items() if item.tag == "SW.Item.Sword")
        self.assertEqual((sword.rarity, sword.power, sword.equipped_slot), ("Unique", 60, "SW.ItemSlot.Equipment.MeleeWeapon"))

    def test_max_level_keeps_both_levels_in_step(self):
        plan = presets.plan(by_title("Max level"), self.hero, self.catalog, power=1)
        presets.apply(plan, self.hero, self.catalog)
        self.assertEqual((self.hero.attribute("Level"), self.hero.level), (100, 100))

    def test_game_caps(self):
        with self.assertRaises(ValueError):
            self.hero.set_attributes({"Emeralds": 10_000}, game_caps=True)
        with self.assertRaises(ValueError):
            self.hero.set_attributes({"Level": 0})
        self.hero.set_attributes({"Emeralds": 10_000})  # Advanced mode may go past a cap
        self.assertEqual(self.hero.attribute("Emeralds"), 10_000)


if __name__ == "__main__":
    unittest.main()
