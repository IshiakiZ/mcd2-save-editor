import tempfile
import unittest
from pathlib import Path

from dungeons2_editor import hero as heroes
from dungeons2_editor import my_items
from dungeons2_editor.hero import Hero

from .helpers import hero_save


class HeroTests(unittest.TestCase):
    def setUp(self):
        self.document = hero_save()
        self.hero = Hero(self.document)
        self.body = self.document["CharacterSaveV1"]

    def entry(self, tag):
        return next(e for e in self.body["Inventory"]["Entries"] if e["ItemData"]["TypeTag"] == tag)

    def item_index(self, tag):
        return next(item.index for item in self.hero.items() if item.tag == tag)

    def test_recognises_hero_saves_only(self):
        self.assertTrue(heroes.is_hero_document(self.document))
        self.assertFalse(heroes.is_hero_document({"blobs": []}))
        with self.assertRaises(ValueError):
            Hero({"blobs": []})

    def test_summary(self):
        self.assertEqual((self.hero.level, self.hero.power_level, self.hero.is_online), (1, 1, False))
        self.assertEqual(self.hero.skin, "Ranger Deluxe")

    def test_stats_are_listed_in_a_friendly_order(self):
        names = [a["AttributeName"] for a in self.hero.attributes()]
        self.assertEqual(names, ["Emeralds", "Level", "XP", "VillageMerchantUpgradeLevel", "MysteryStat"])
        self.assertEqual(heroes.attribute_label("VillageMerchantUpgradeLevel"), "Village merchant level")
        self.assertEqual(heroes.attribute_label("MysteryStat"), "Mystery Stat")

    def test_level_changes_both_places_it_is_stored(self):
        self.hero.set_attributes({"Level": 20, "Emeralds": 9999})
        self.assertEqual(self.hero.attribute("Level"), 20)
        self.assertEqual(self.body["MetaData"]["Level"], 20)
        self.assertEqual(self.hero.attribute("Emeralds"), 9999)

    def test_bad_stats_change_nothing(self):
        for values in ({"Emeralds": 100, "Level": -5}, {"Emeralds": 1.5}, {"Emeralds": 2**31}, {"Nope": 1}, {"Emeralds": True}):
            with self.assertRaises((ValueError, KeyError)):
                self.hero.set_attributes(values)
        self.assertEqual(self.hero.attribute("Emeralds"), 55)
        self.hero.set_attributes({"XP": 900.75, "MysteryStat": 0.25})  # not whole numbers, and that's fine
        self.assertEqual((self.hero.attribute("XP"), self.hero.attribute("MysteryStat")), (900.75, 0.25))

    def test_items_are_described(self):
        rows = {item.tag: (item.name, item.kind, item.rarity, item.where) for item in self.hero.items()}
        self.assertEqual(rows["SW.Item.MysticHelmet"], ("Mystic Circlet", "Armor", "Common", "Inventory"))
        self.assertEqual(rows["SW.Item.CurvedGreatsword"][1:], ("Melee", "Common", "Merchant stock"))
        self.assertEqual(rows["SW.Item.Longbow"][1:3], ("Ranged", "Rare"))
        self.assertEqual(rows["SW.Item.Sword"][3], "Equipped (melee weapon)")
        self.assertEqual(rows["SW.Item.Cosmetic.Cape.Hero"][:2], ("Hero", "Cape"))

    def test_power_change_sets_the_whole_roll_range(self):
        self.hero.update_item(self.item_index("SW.Item.MysticHelmet"), power=50, rarity="Unique")
        data = self.entry("SW.Item.MysticHelmet")["ItemData"]
        values = data["GeneratorData"]["PowerGeneratorValues"]
        self.assertEqual([values[k] for k in ("ItemPower", "ItemPowerOriginal", "ItemPowerMin", "ItemPowerMax")], [50] * 4)
        self.assertEqual(data["RarityTag"], "SW.Rarity.Unique")

    def test_unchanged_power_leaves_the_roll_range_alone(self):
        index = self.item_index("SW.Item.MysticHelmet")
        self.hero.update_item(index, power=1, rarity="Rare", count=1)
        values = self.entry("SW.Item.MysticHelmet")["ItemData"]["GeneratorData"]["PowerGeneratorValues"]
        self.assertEqual((values["ItemPowerMin"], values["ItemPowerMax"]), (1, 3))

    def test_bad_item_edits_change_nothing(self):
        before = hero_save()
        helmet = self.item_index("SW.Item.MysticHelmet")
        sword = self.item_index("SW.Item.Sword")
        cape = self.item_index("SW.Item.Cosmetic.Cape.Hero")
        bad_edits = [
            (helmet, {"power": 50, "rarity": "Legendary"}),
            (helmet, {"power": -1}),
            (helmet, {"power": 2.5}),
            (helmet, {"count": 0}),
            (helmet, {"tag": "SW.Item.Cosmetic.Cape.Mojang"}),
            (helmet, {"tag": "not an item"}),
            (sword, {"tag": "SW.Item.Axe"}),
            (cape, {"power": 5}),
        ]
        for index, changes in bad_edits:
            with self.assertRaises(ValueError, msg=changes):
                self.hero.update_item(index, **changes)
        self.assertEqual(self.document, before)

    def test_type_change_on_unequipped_item(self):
        index = self.item_index("SW.Item.MysticHelmet")
        self.hero.update_item(index, tag="SW.Item.Axe")
        self.assertEqual(self.hero.item(index).tag, "SW.Item.Axe")

    def test_duplicate_makes_an_unequipped_inventory_copy(self):
        original = self.entry("SW.Item.CurvedGreatsword")
        seed = original["ItemData"]["GeneratorData"]["GenesisRandomSeed"]
        index = self.hero.duplicate_item(self.item_index("SW.Item.CurvedGreatsword"))
        copy = self.hero.item(index)
        self.assertEqual(copy.tag, "SW.Item.CurvedGreatsword")
        self.assertIsNone(copy.equipped_slot)
        self.assertIsNone(copy.stock_slot)
        self.assertEqual(copy.where, "Inventory")
        self.assertNotEqual(copy.data["GeneratorData"]["GenesisRandomSeed"], seed)
        self.assertIn(heroes.UNSEEN_TAG, copy.data["DynamicPropertyTags"])
        self.assertEqual(original["ItemData"]["TargetSlotOverride"], "SW.ItemSlot.Inventory.VillageMerchant.Tier0")
        self.assertEqual(len(self.hero.items()), 6)

    def test_cosmetics_cannot_be_copied_or_removed(self):
        cape = self.item_index("SW.Item.Cosmetic.Cape.Hero")
        with self.assertRaises(ValueError):
            self.hero.duplicate_item(cape)
        with self.assertRaises(ValueError):
            self.hero.remove_item(cape)

    def test_remove(self):
        with self.assertRaises(ValueError):
            self.hero.remove_item(self.item_index("SW.Item.Sword"))  # equipped
        self.hero.remove_item(self.item_index("SW.Item.Longbow"))
        self.assertNotIn("SW.Item.Longbow", [item.tag for item in self.hero.items()])

    def test_known_item_types_skip_cosmetics(self):
        types = self.hero.known_item_types()
        self.assertIn("SW.Item.Axe", types)
        self.assertIn("SW.Item.Bow", types)
        self.assertFalse([tag for tag in types if "Cosmetic" in tag])

    def test_item_sorting(self):
        def order(sort):
            return [item.tag.rsplit(".", 1)[-1] for item in heroes.sort_items(self.hero.items(), sort)]

        self.assertEqual(order("Most powerful")[0], "Longbow")
        self.assertEqual(order("Most powerful")[-1], "Hero")  # cosmetics have power -1
        self.assertEqual(order("Name"), ["CurvedGreatsword", "Hero", "Longbow", "MysticHelmet", "Sword"])
        self.assertEqual(order("Rarest")[0], "Longbow")
        self.assertEqual(order("Newest")[0], "Longbow")
        self.assertEqual(order("Save order"), ["MysticHelmet", "CurvedGreatsword", "Longbow", "Sword", "Hero"])
        for sort in heroes.ITEM_SORTS:
            self.assertEqual(len(order(sort)), 5)

    def test_in_game_names(self):
        self.assertEqual(heroes.display_name("SW.Item.MysticHelmet"), "Mystic Circlet")
        self.assertEqual(heroes.display_name("SW.Item.MysticHelmet", "Unique"), "Oracle Crown")
        self.assertEqual(heroes.display_name("SW.Item.Artifact.FireworkQuiver"), "Firework Arrow")
        self.assertEqual(heroes.display_name("SW.Item.SomethingNew"), "Something New")

    def test_the_game_item_list(self):
        items = heroes.game_items()
        self.assertGreater(len(items), 150)
        self.assertTrue(all(heroes._ITEM_TAG.fullmatch(item.id) for item in items))
        self.assertFalse([item for item in items if heroes.item_group(item.id) in heroes.NOT_ADDABLE_GROUPS])
        self.assertTrue({"SW.Item.Sword", "SW.Item.MysticHelmet"} <= {item.id for item in items if item.confirmed})

    def test_catalog_has_every_game_item_and_marks_confirmed_ones(self):
        catalog = {entry.tag: entry for entry in heroes.build_catalog([self.hero])}
        self.assertGreater(len(catalog), 150)
        self.assertTrue(catalog["SW.Item.Axe"].confirmed)  # in this save's collections
        self.assertTrue(catalog["SW.Item.MysticHelmet"].confirmed)
        self.assertFalse(catalog["SW.Item.Claymore"].confirmed)  # a best guess from its name
        self.assertEqual(catalog["SW.Item.BattleHammer"].unique, "Emerald Hammer")
        self.assertNotIn("SW.Item.Cosmetic.Cape.Hero", catalog)
        talisman = catalog["SW.Item.Talisman.LuckyClover"]
        self.assertEqual(talisman.template["ItemData"]["TypeTag"], "SW.Item.MysticHelmet")  # borrows a gear layout

    def test_equip_swaps_what_is_in_the_slot(self):
        slots = {slot.label: slot for slot in heroes.GEAR_SLOTS}
        sword, axe = self.item_index("SW.Item.Sword"), self.hero.duplicate_item(self.item_index("SW.Item.Sword"))
        self.hero.update_item(axe, tag="SW.Item.Axe")
        replaced = self.hero.equip(axe, slots["Melee weapon"])
        self.assertEqual(replaced.index, sword)
        self.assertEqual(self.hero.item(axe).where, "Equipped (melee weapon)")
        self.assertEqual(self.hero.item(sword).entry["EquippedSlot"], "None")
        self.assertEqual(self.hero.equipped("SW.ItemSlot.Equipment.MeleeWeapon").index, axe)
        self.assertIsNone(self.hero.equip(axe, slots["Melee weapon"]))  # already there

    def test_equip_checks_the_slot(self):
        slots = {slot.label: slot for slot in heroes.GEAR_SLOTS}
        before = hero_save()
        helmet = self.item_index("SW.Item.MysticHelmet")
        bad = [
            (helmet, slots["Boots"]),  # wrong piece
            (helmet, slots["Melee weapon"]),
            (self.item_index("SW.Item.CurvedGreatsword"), slots["Melee weapon"]),  # merchant stock
            (self.item_index("SW.Item.Cosmetic.Cape.Hero"), slots["Melee weapon"]),
        ]
        for index, slot in bad:
            with self.assertRaises(ValueError, msg=slot.label):
                self.hero.equip(index, slot)
        self.assertEqual(self.document, before)
        self.hero.equip(helmet, slots["Helmet"])
        self.assertEqual(self.hero.item(helmet).where, "Equipped (helmet)")

    def test_locked_slots_need_the_level_unless_told_otherwise(self):
        slots = {slot.label: slot for slot in heroes.GEAR_SLOTS}
        template = self.entry("SW.Item.MysticHelmet")
        with self.assertRaises(ValueError):
            self.hero.add_item("SW.Item.Artifact.FireworkQuiver", template, slot=slots["Artifact 3"])  # opens at level 10
        self.assertEqual(len(self.hero.items()), 5)
        index = self.hero.add_item("SW.Item.Artifact.FireworkQuiver", template, slot=slots["Artifact 3"], check_level=False)
        self.assertEqual(self.hero.item(index).where, "Equipped (artifact 3)")
        self.hero.set_attributes({"Level": 10})
        self.hero.equip(index, slots["Artifact 2"])
        self.assertIsNone(self.hero.equipped(slots["Artifact 3"].tag))

    def test_unequip_then_delete(self):
        sword = self.item_index("SW.Item.Sword")
        self.hero.unequip(sword)
        self.assertEqual(self.hero.item(sword).where, "Inventory")
        self.hero.remove_item(sword)
        self.assertNotIn("SW.Item.Sword", [item.tag for item in self.hero.items()])

    def test_armor_pieces(self):
        self.assertEqual(heroes.armor_piece("SW.Item.MysticHelmet"), "Helmet")
        self.assertEqual(heroes.armor_piece("SW.Item.HoneyChest"), "Chestplate")
        self.assertEqual(heroes.armor_piece("SW.Item.SomethingBoots"), "Boots")  # not in the game list: from the ID
        self.assertIsNone(heroes.armor_piece("SW.Item.Sword"))
        self.assertEqual([slot.label for slot in heroes.slots_for("Armor", "Leggings", heroes.GEAR_SLOTS)], ["Leggings"])
        self.assertEqual(len(heroes.slots_for("Talisman", None, heroes.GEAR_SLOTS)), 3)

    def test_slot_names_are_learned_from_saves(self):
        default = {slot.label: slot for slot in heroes.gear_slots([self.hero])}
        self.assertTrue(all(slot.confirmed for slot in default.values()))  # named in the game's own script cache
        self.assertEqual(default["Helmet"].tag, "SW.ItemSlot.Equipment.Armor.Helmet")
        self.entry("SW.Item.MysticHelmet")["EquippedSlot"] = "SW.ItemSlot.Equipment.Head"
        other = Hero(hero_save())
        other.body["Inventory"]["Entries"].append(dict(self.entry("SW.Item.Longbow"), EquippedSlot="SW.ItemSlot.Equipment.Artifact2"))
        other.body["Inventory"]["Entries"][-1]["ItemData"] = dict(other.body["Inventory"]["Entries"][-1]["ItemData"], TypeTag="SW.Item.Artifact.FireworkQuiver")
        learned = {slot.label: slot for slot in heroes.gear_slots([self.hero, other])}
        self.assertEqual((learned["Helmet"].tag, learned["Helmet"].confirmed), ("SW.ItemSlot.Equipment.Head", True))
        self.assertEqual((learned["Artifact 2"].tag, learned["Artifact 2"].confirmed), ("SW.ItemSlot.Equipment.Artifact2", True))
        self.assertEqual((learned["Artifact 3"].tag, learned["Artifact 3"].confirmed), ("SW.ItemSlot.Equipment.Artifact3", False))
        self.assertEqual(learned["Boots"], default["Boots"])

    def test_hero_sorting(self):
        rich, poor = Hero(hero_save(emeralds=900, level=2)), Hero(hero_save(emeralds=10, level=30))
        by = lambda sort: sorted([rich, poor], key=heroes.HERO_SORTS[sort], reverse=True)  # noqa: E731
        self.assertEqual(by("Most emeralds"), [rich, poor])
        self.assertEqual(by("Highest level"), [poor, rich])


class LocalNameTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(heroes.use_local_names, {})

    def test_your_names_fill_in_for_names_made_from_ids(self):
        self.assertEqual(heroes.display_name("SW.Item.UndauntedHelmet"), "Undaunted Helmet")
        self.assertFalse(heroes.name_is_known("SW.Item.UndauntedHelmet"))
        heroes.use_local_names({"SW.Item.UndauntedHelmet": "Bounty Hunter Helmet", "SW.Item.Sword": "Not a sword"})
        self.assertEqual(heroes.display_name("SW.Item.UndauntedHelmet"), "Bounty Hunter Helmet")
        self.assertTrue(heroes.name_is_known("SW.Item.UndauntedHelmet"))
        self.assertEqual(heroes.display_name("SW.Item.Sword"), "Sword")  # the game's list wins
        self.assertEqual(heroes.display_name("SW.Item.BrandNew"), "Brand New")


class ItemNamesFileTests(unittest.TestCase):
    def test_saves_and_loads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "deeper" / "item-names.json"
            self.assertEqual(my_items.load_names(path), {})
            my_items.save_names({"SW.Item.B": "Bee", "SW.Item.A": "Ay"}, path)
            self.assertEqual(my_items.load_names(path), {"SW.Item.A": "Ay", "SW.Item.B": "Bee"})
            path.write_text("[1, 2]", encoding="utf-8")
            self.assertEqual(my_items.load_names(path), {})


if __name__ == "__main__":
    unittest.main()
