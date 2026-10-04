import unittest

from dungeons2_editor import hero as heroes
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
            self.assertIn(preset.group, presets.GROUPS)
        self.assertEqual(len({p.title for p in presets.PRESETS}), len(presets.PRESETS))

    def test_every_preset_item_and_enchantment_is_known(self):
        known = heroes.enchantments()
        for preset in presets.PRESETS:
            for kit_item in preset.items:
                found = presets.find_item(kit_item.name, self.catalog)
                self.assertIsNotNone(found, f"{preset.title}: {kit_item.name}")
                for name in kit_item.enchants:
                    slots = known[name].slots
                    fits = found.kind in slots or (found.kind == "Armor" and ("Armor" in slots or (found.piece == "Chestplate" and "Chestplate" in slots)))
                    self.assertTrue(fits, f"{preset.title}: {name} on {kit_item.name}")

    def test_kits_are_complete_loadouts(self):
        kits = [p for p in presets.PRESETS if p.group == presets.KITS]
        self.assertGreaterEqual(len(kits), 5)
        for kit in kits:
            found = [presets.find_item(item.name, self.catalog) for item in kit.items]
            kinds = sorted(f.kind for f in found if f.kind != "Ranged")
            self.assertEqual(kinds, sorted(["Melee"] + ["Armor"] * 4 + ["Artifact"] * 3 + ["Talisman"] * 3), kit.title)
            self.assertLessEqual(sum(f.kind == "Ranged" for f in found), 1, kit.title)  # some builds keep your bow
            self.assertEqual(sorted(f.piece for f in found if f.kind == "Armor"), ["Boots", "Chestplate", "Helmet", "Leggings"], kit.title)
            self.assertTrue(kit.choose_rarity and kit.equip)
            self.assertTrue(all(item.enchants for item in kit.items if item.kind in ("Melee", "Ranged", "Armor")), kit.title)

    def test_finds_items_by_their_in_game_names(self):
        self.assertEqual(presets.find_item("The Eye of Experience", self.catalog).tag, "SW.Item.Talisman.EyeOfExperience")
        self.assertEqual(presets.find_item("Lucky Clover", self.catalog).tag, "SW.Item.Talisman.LuckyClover")
        self.assertEqual(presets.find_item("Mystic Circlet", self.catalog).tag, "SW.Item.MysticHelmet")  # known rename
        self.assertFalse(presets.find_item("Emerald of Good Fortune", self.catalog).confirmed)  # only a best-guess ID
        self.assertIsNone(presets.find_item("Not An Item", self.catalog))

    def test_most_money_fills_to_the_cap(self):
        plan = presets.plan(by_title("Most money"), self.hero, self.catalog, power=1)
        self.assertEqual(plan.stats, {"Emeralds": 99_999})  # this hero has no Echo Shards stat
        self.assertEqual([k.name for k, _ in plan.unconfirmed], ["Emerald of Good Fortune"])
        presets.apply(plan, self.hero, self.catalog)
        self.assertEqual(self.hero.attribute("Emeralds"), 99_999)

    def test_items_another_hero_found_can_be_added(self):
        plan = presets.plan(by_title("Most XP"), self.hero, self.catalog, power=1)
        self.assertEqual([addition.kit.name for addition in plan.add], ["The Eye of Experience"])
        presets.apply(plan, self.hero, self.catalog)
        added = next(item for item in self.hero.items() if item.tag == "SW.Item.Talisman.EyeOfExperience")
        self.assertEqual((added.power, added.where), (-1, "Inventory"))  # laid out like the saved copy
        again = presets.plan(by_title("Most XP"), self.hero, self.catalog, power=1)
        self.assertEqual([owned.kit.name for owned in again.have], ["The Eye of Experience"])
        self.assertFalse(again.changes_anything)

    def test_upgrade_my_gear_upgrades_owned_gear_only(self):
        body = self.document["CharacterSaveV1"]
        body["Inventory"]["Entries"].append(hero_item("SW.Item.Artifact.FireworkQuiver", power=2, seed=13))
        plan = presets.plan(by_title("Upgrade my gear"), self.hero, self.catalog, power=60)
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

    def test_unique_names_and_unconfirmed_items(self):
        self.assertEqual(presets.find_item("Emerald Hammer", self.catalog).tag, "SW.Item.BattleHammer")
        careful = presets.plan(by_title("Best loot"), self.hero, self.catalog, power=30)
        self.assertIn("Emerald Hammer", [kit.name for kit, _ in careful.unconfirmed])
        self.assertNotIn("Emerald Hammer", [addition.kit.name for addition in careful.add])
        bold = presets.plan(by_title("Best loot"), self.hero, self.catalog, power=30, include_unconfirmed=True)
        self.assertIn("Emerald Hammer", [addition.kit.name for addition in bold.add])
        self.assertTrue(any(line.endswith("(unconfirmed)") for line in presets.describe(bold, self.hero)))
        presets.apply(bold, self.hero, self.catalog)
        hammer = next(item for item in self.hero.items() if item.tag == "SW.Item.BattleHammer")
        self.assertEqual((hammer.name, hammer.rarity, hammer.power), ("Emerald Hammer", "Unique", 30))

    def test_best_gear_at_the_picked_rarity_and_power_equipped(self):
        plan = presets.plan(by_title("Best melee weapon"), self.hero, self.catalog, power=45, include_unconfirmed=True, rarity="Rare", equip=True)
        (addition,) = plan.add
        self.assertEqual((addition.name, addition.rarity, addition.slot.label), ("Riftslasher", "Rare", "Melee weapon"))
        self.assertIn("Add Riftslasher (Rare, power 45) and equip it (melee weapon)", presets.describe(plan, self.hero)[0])
        presets.apply(plan, self.hero, self.catalog)
        blade = self.hero.equipped("SW.ItemSlot.Equipment.MeleeWeapon")
        self.assertEqual((blade.tag, blade.rarity, blade.power), ("SW.Item.Riftslasher", "Rare", 45))
        sword = next(item for item in self.hero.items() if item.tag == "SW.Item.Sword")
        self.assertEqual(sword.where, "Inventory")

    def test_unique_rarity_names_the_unique_and_caps_artifacts_and_talismans(self):
        weapon = presets.plan(by_title("Best melee weapon"), self.hero, self.catalog, power=10, include_unconfirmed=True, rarity="Unique")
        line = presets.describe(weapon, self.hero)[0]
        self.assertTrue(line.startswith("Add Pride of the Plains (Unique Riftslasher, power 10): +40% damage"), line)
        kit = presets.plan(by_title("Humbler tank"), self.hero, self.catalog, power=10, include_unconfirmed=True, rarity="Unique")
        self.assertIn("Add Heartbreaker (Unique War Hammer, power 10): Hits explode.", presets.describe(kit, self.hero)[0])
        artifacts = presets.plan(by_title("Best artifacts"), self.hero, self.catalog, power=10, include_unconfirmed=True, rarity="Unique")
        self.assertEqual({a.rarity for a in artifacts.add}, {"Special"})
        talismans = presets.plan(by_title("Best talismans"), self.hero, self.catalog, power=10, include_unconfirmed=True, rarity="Unique")
        self.assertEqual({a.rarity for a in talismans.add}, {"Common"})

    def test_kit_fills_each_slot_once_within_the_heros_level(self):
        kit = by_title("Greatbow sharpshooter")
        plan = presets.plan(kit, self.hero, self.catalog, power=50, include_unconfirmed=True, rarity="Unique", equip=True)
        slots = [a.slot.label for a in plan.add if a.slot is not None]
        self.assertEqual(len(slots), len(set(slots)))
        self.assertNotIn("Artifact 2", slots)  # this hero is level 1: artifact slots 2 and 3 open at levels 5 and 10
        self.assertIn("Artifact 1", slots)
        self.hero.set_attributes({"Level": 10})
        plan = presets.plan(kit, self.hero, self.catalog, power=50, include_unconfirmed=True, rarity="Unique", equip=True)
        self.assertEqual(len([a for a in plan.add if a.slot is not None]), 12)
        presets.apply(plan, self.hero, self.catalog)
        equipped = [item for item in self.hero.items() if item.equipped_slot]
        self.assertEqual(len(equipped), 12)
        self.assertEqual(self.hero.equipped("SW.ItemSlot.Equipment.RangedWeapon").name, "Humbler Heartstring")

    def test_a_good_enough_copy_you_own_is_equipped_instead(self):
        body = self.document["CharacterSaveV1"]
        body["Inventory"]["Entries"].append(hero_item("SW.Item.Riftslasher", power=80, rarity="Unique", seed=21))
        plan = presets.plan(by_title("Best melee weapon"), self.hero, self.catalog, power=50, include_unconfirmed=True, rarity="Unique", equip=True)
        self.assertFalse(plan.add)
        self.assertEqual(plan.have[0].slot.label, "Melee weapon")
        self.assertIn("Equip your Pride of the Plains (melee weapon)", presets.describe(plan, self.hero))
        presets.apply(plan, self.hero, self.catalog)
        self.assertEqual(self.hero.equipped("SW.ItemSlot.Equipment.MeleeWeapon").power, 80)

    def test_enchantment_suggestions_come_with_what_they_do(self):
        suggestions = dict((kit.name, picks) for kit, picks in presets.enchant_suggestions(by_title("Best melee weapon")))
        lightning = suggestions["Riftslasher"][0]
        self.assertEqual(lightning.name, "Lightning Surge")
        self.assertIn("Melee", lightning.slots)
        self.assertTrue(lightning.tier3 and lightning.book)

    def test_game_caps(self):
        with self.assertRaises(ValueError):
            self.hero.set_attributes({"Emeralds": 100_000}, game_caps=True)
        with self.assertRaises(ValueError):
            self.hero.set_attributes({"Level": 0})
        self.hero.set_attributes({"Emeralds": 100_000})  # Advanced mode may go past a cap
        self.assertEqual(self.hero.attribute("Emeralds"), 100_000)


if __name__ == "__main__":
    unittest.main()
