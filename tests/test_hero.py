import copy
import json
import tempfile
import unittest
from pathlib import Path

from dungeons2_editor import hero as heroes
from dungeons2_editor import my_items
from dungeons2_editor.hero import Hero

from .helpers import enchanted, enchantment_effect, hero_item, hero_save, rolled, rolled_effect, talisman_item

# What the game saved, key for key, for a Special Bow it dropped and for a Unique helmet enchanted at the Enchantsmith
# (the developer's own save, 2026-10-05). The editor has to write the same.
GAME_BOW_EFFECTS = (
    '[{"TypeTag": "SW.Item.Effect.Rerollable", "EffectsInThisBatch": [{"TypeTag": "SW.Effect.Knockback", "Intensity": 0.15, '
    '"Quality": 0, "EnchantmentPointsInvested": 0, "GeneratorData": {"GeneratorParentTemplate": "SW.EffectTemplate.Knockback.I", '
    '"Locked": false}}, {"TypeTag": "SW.Effect.CriticalEdge", "Intensity": 0.2, "Quality": 0, "EnchantmentPointsInvested": 0, '
    '"GeneratorData": {"GeneratorParentTemplate": "SW.EffectTemplate.CriticalEdge.II", "Locked": false}}]}]'
)
GAME_HELMET_EFFECTS = (
    '[{"TypeTag": "SW.Item.Effect.Enchantment", "EffectsInThisBatch": [{"TypeTag": "SW.Enchantment.SoulInfusedPotion", '
    '"Intensity": 0.6, "Quality": 0, "EnchantmentPointsInvested": 8, "GeneratorData": {"GeneratorParentTemplate": '
    '"SW.Enchantment.SoulInfusedPotion.II", "Locked": false}}]}]'
)
UNSEEN = "SW.Item.Property.Dynamic.Unseen"


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
        self.assertEqual(heroes.display_name("SW.Item.Artifact.FireworkQuiver"), "Firework Arrow")
        self.assertEqual(heroes.display_name("SW.Item.SomethingNew"), "Something New")
        # What a save calls an item often isn't what players see.
        self.assertEqual(heroes.display_name("SW.Item.CurvedLongsword"), "Riftslasher")
        self.assertEqual(heroes.display_name("SW.Item.CaveCrawlerHelmet"), "Sculk Digger Hood")
        self.assertEqual(heroes.display_name("SW.Item.Talisman.RangedBuff"), "Amethyst Lens")
        self.assertEqual(heroes.display_name("SW.Item.Artifact.Satchel.Fire"), "Pouch of Ember")
        self.assertEqual(heroes.display_name("SW.Item.EnchantmentBook.MultiRoll"), "Somersault")
        self.assertEqual(heroes.tag_kind("SW.Item.EnchantmentBook.MultiRoll"), heroes.BOOK_KIND)

    def test_a_unique_has_an_id_of_its_own(self):
        # Seen in real saves: weapons end in _Unique1, armor in _Unique.
        self.assertEqual(heroes.display_name("SW.Item.Sword_Unique1"), "The Burning Blade")
        self.assertEqual(heroes.display_name("SW.Item.MysticLeggings_Unique"), "Oracle Tights")
        self.assertEqual((heroes.tag_kind("SW.Item.Trickbow_Unique1"), heroes.armor_piece("SW.Item.UndauntedHelmet_Unique")), ("Ranged", "Helmet"))
        self.assertEqual(heroes.display_name("SW.Item.Sword"), "Sword")  # the base item, whatever its rarity
        # A Unique's ID that hasn't been seen still reads as that Unique, but isn't written until it has been.
        self.assertEqual(heroes.display_name("SW.Item.Mace_Unique1"), "Carapace Mace")
        self.assertEqual(heroes.unique_tag("SW.Item.Sword"), "SW.Item.Sword_Unique1")
        self.assertIsNone(heroes.unique_tag("SW.Item.Mace"))
        self.assertEqual(heroes.unique_tag("SW.Item.Mace", {"SW.Item.Mace_Unique1", "SW.Item.Sword"}), "SW.Item.Mace_Unique1")
        self.assertIsNone(heroes.unique_tag("SW.Item.Artifact.Grindstone"))  # artifacts have no Unique
        self.assertEqual(heroes.base_tag("SW.Item.Sword_Unique1"), "SW.Item.Sword")
        self.assertEqual(heroes.base_tag("SW.Item.NotInTheList_Unique1"), "SW.Item.NotInTheList_Unique1")
        self.assertFalse(heroes.is_unique_version("SW.Item.Sword"))

    def test_making_an_item_unique_gives_it_the_uniques_id_when_thats_known(self):
        sword = self.item_index("SW.Item.Sword")
        self.hero.update_item(sword, rarity="Unique")
        self.assertEqual((self.hero.item(sword).tag, self.hero.item(sword).name), ("SW.Item.Sword_Unique1", "The Burning Blade"))
        self.assertEqual(self.hero.item(sword).equipped_slot, "SW.ItemSlot.Equipment.MeleeWeapon")  # it stays on
        self.hero.update_item(sword, rarity="Rare")
        self.assertEqual((self.hero.item(sword).tag, self.hero.item(sword).name), ("SW.Item.Sword", "Sword"))
        helmet = self.item_index("SW.Item.MysticHelmet")
        self.hero.update_item(helmet, rarity="Unique")  # the Oracle Crown's own ID hasn't been seen in a save
        self.assertEqual((self.hero.item(helmet).tag, self.hero.item(helmet).rarity, self.hero.item(helmet).name), ("SW.Item.MysticHelmet", "Unique", "Mystic Circlet"))
        longbow = self.item_index("SW.Item.Longbow")
        self.hero.update_item(longbow, tag="SW.Item.Mace_Unique1")  # an ID that's typed in is kept exactly
        self.assertEqual((self.hero.item(longbow).tag, self.hero.item(longbow).rarity), ("SW.Item.Mace_Unique1", "Rare"))

    def test_an_item_added_at_unique_rarity_is_the_unique(self):
        catalog = {entry.tag: entry for entry in heroes.build_catalog([self.hero])}
        sword, mace = catalog["SW.Item.Sword"], catalog["SW.Item.Mace"]
        self.assertEqual((sword.tag_at("Unique"), sword.confirmed_at("Unique"), sword.name_at("Unique")), ("SW.Item.Sword_Unique1", True, "The Burning Blade"))
        self.assertEqual((sword.tag_at("Rare"), sword.name_at("Rare")), ("SW.Item.Sword", "Sword"))
        # The Carapace Mace's own ID hasn't been seen, but it follows the pattern every seen one does: it can be added.
        self.assertEqual((mace.tag_at("Unique"), mace.id_known_at("Unique"), mace.by_pattern_at("Unique")), ("SW.Item.Mace_Unique1", False, True))
        self.assertEqual((mace.confirmed_at("Unique"), mace.doubt("Unique"), mace.confirmed_at("Rare")), (True, "", True))
        self.assertEqual((sword.by_pattern_at("Unique"), mace.by_pattern_at("Rare")), (False, False))  # seen; not a Unique
        # The Battlestaff's own ID is a guess, so its Unique's is a guess twice over.
        staff = catalog["SW.Item.Battlestaff"]
        self.assertEqual((staff.unique, staff.by_pattern_at("Unique"), staff.confirmed_at("Unique")), ("Elemental Staff", False, False))
        self.assertIn("best guess", staff.doubt("Unique"))
        self.assertEqual(catalog["SW.Item.MysticHelmet"].tag_at("Unique"), "SW.Item.MysticHelmet_Unique")  # armor: no 1
        grindstone = catalog["SW.Item.Artifact.Grindstone"]
        self.assertEqual((grindstone.tag_at("Unique"), grindstone.confirmed_at("Unique")), ("SW.Item.Artifact.Grindstone", True))
        index = self.hero.add_item("SW.Item.Sword", sword.template, rarity="Unique", power=5)  # even from the base ID
        self.assertEqual((self.hero.item(index).tag, self.hero.item(index).name), ("SW.Item.Sword_Unique1", "The Burning Blade"))
        self.assertIn("SW.Item.Sword_Unique1", self.document["CharacterSaveV1"]["LootProgression"]["DiscoveredLoot"])

    def test_a_unique_found_in_the_game_is_its_base_items_unique(self):
        self.document["CharacterSaveV1"]["Inventory"]["Entries"].append(hero_item("SW.Item.Mace_Unique1", rarity="Unique", seed=77, unseen=False))
        catalog = {entry.tag: entry for entry in heroes.build_catalog([self.hero])}
        self.assertNotIn("SW.Item.Mace_Unique1", catalog)  # not an item of its own
        mace = catalog["SW.Item.Mace"]
        self.assertEqual((mace.unique_tag, mace.id_known_at("Unique"), mace.by_pattern_at("Unique")), ("SW.Item.Mace_Unique1", True, False))
        self.assertEqual(heroes.template_for("SW.Item.Sword_Unique1", list(catalog.values())), catalog["SW.Item.Sword"].template)

    def test_only_what_the_game_vouches_for_counts_as_seen(self):
        vouched = self.hero.item_types_from_the_game()
        self.assertEqual(vouched["SW.Item.Axe"], "collected")  # in the game's collections, which the editor never writes
        self.assertEqual(vouched["SW.Item.Sword"], "collected")
        self.assertEqual(vouched["SW.Item.CurvedGreatsword"], "merchant")  # the Village Merchant's stock is the game's
        self.assertEqual(vouched["SW.Item.Cosmetic.Cape.Hero"], "kept")  # on an item the game has shown you
        self.assertNotIn("SW.Item.Bow", vouched)  # only in the discovered loot, which the editor adds to itself
        self.assertNotIn("SW.Item.Longbow", vouched)  # on an item nobody has looked at yet
        self.assertIn("SW.Item.Bow", self.hero.seen_item_types())  # everything in the save, vouched for or not

    def test_an_id_the_editor_wrote_is_not_evidence_until_the_game_keeps_it(self):
        def staff():
            return next(entry for entry in heroes.build_catalog([self.hero]) if entry.tag == "SW.Item.Battlestaff")

        self.assertFalse(staff().confirmed)  # a best guess from its name
        index = self.hero.add_item("SW.Item.Battlestaff", staff().template)
        # It's in the inventory and the discovered loot now, but only because the editor put it there.
        self.assertIn("SW.Item.Battlestaff", self.body["LootProgression"]["DiscoveredLoot"])
        self.assertNotIn("SW.Item.Battlestaff", self.hero.item_types_from_the_game())
        self.assertFalse(staff().confirmed)
        # The game loads the hero, keeps the item and shows it to you: it would have dropped an ID it doesn't know.
        self.hero.item(index).data["DynamicPropertyTags"].remove("SW.Item.Property.Dynamic.Unseen")
        self.assertEqual(self.hero.item_types_from_the_game()["SW.Item.Battlestaff"], "kept")
        self.assertTrue(staff().confirmed)
        # Turned into something else, it's a new item again, and vouches for nothing until the game has had it.
        self.hero.update_item(index, tag="SW.Item.SomethingElse")
        self.assertIn("SW.Item.Property.Dynamic.Unseen", self.hero.item(index).data["DynamicPropertyTags"])
        self.assertNotIn("SW.Item.SomethingElse", self.hero.item_types_from_the_game())
        self.assertFalse(staff().confirmed)
        # The merchant's stock is evidence because the game makes it, so what's in it can't be changed.
        stock = self.item_index("SW.Item.CurvedGreatsword")
        with self.assertRaisesRegex(ValueError, "Village Merchant's stock"):
            self.hero.update_item(stock, tag="SW.Item.Battlestaff")
        self.hero.update_item(stock, rarity="Rare", power=9)  # its rarity and power still can

    def choice(self, name, tier="I"):
        gear, enchantments = heroes.effect_choices([self.hero])
        return next(choice for choice in gear + enchantments if choice.name == name and choice.tier == tier)

    def test_effects_are_read_the_way_a_save_holds_them(self):
        sword = self.hero.item(self.item_index("SW.Item.Sword"))
        self.assertEqual((sword.effects, sword.effect_lines()), ([], []))
        thorns = rolled_effect("Thorns", 12)
        thorns.update(Quality=2)
        thorns["GeneratorData"]["Locked"] = True
        sword.data["Effects"] = [
            rolled(rolled_effect("CriticalEdge", 0.2, "II"), thorns, "not an effect"),
            enchanted(enchantment_effect("Radiance", 0.3)),
            {"TypeTag": "SW.Item.Effect.Other"},  # a batch laid out some other way is left out, not guessed at
            "not a batch",
        ]
        first, second, third = sword.effects
        self.assertEqual((first.name, first.tier, first.tag, first.strength, first.template, first.group),
                         ("Critical Edge", "II", "SW.Effect.CriticalEdge", 0.2, "SW.EffectTemplate.CriticalEdge.II", "SW.Item.Effect.Rerollable"))
        self.assertEqual((second.name, second.quality, second.locked), ("Thorns", 2, True))  # not in the list: named from its ID
        self.assertEqual((third.name, third.tier, third.points, third.is_enchantment), ("Healing Smite", "I", 3, True))
        # The game's own number for a tier when the list has it, else the strength as saved. An enchantment's
        # strength isn't a number the game shows.
        self.assertEqual(sword.effect_lines(), ["Critical Edge II 20%", "Thorns I 12, quality 2, locked", "Enchanted: Healing Smite I, 3 enchantment points"])
        self.assertEqual(([effect.title for effect in sword.rolled_effects], sword.enchantment.title, sword.own_effects),
                         (["Critical Edge II", "Thorns I"], "Healing Smite I", []))
        self.assertEqual(heroes.sort_items(self.hero.items(), "Most effects")[0].tag, "SW.Item.Sword")
        # A rolled effect goes by its template, as in the game: SW.Effect.RollCooldown from the Acrobat template is
        # Acrobat, and from another template it's another thing.
        sword.data["Effects"] = [rolled(rolled_effect("RollCooldown", 0.1, template="Acrobat"), rolled_effect("RollCooldown", 0.2, template="RollingCooldown"))]
        self.assertEqual(sword.effect_lines(), ["Acrobat I 10%", "Rolling Cooldown I 0.2"])
        # A talisman also says which level it's at, how far along it is, and what's to come.
        self.body["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", level=1, seed=61))
        sigil = self.hero.item(self.item_index("SW.Item.Talisman.HealthBoost"))
        self.assertEqual(sigil.effect_lines(), ["Health Boost 1.25", "Level 2 of 3. At the next level: 1.35."])
        sigil.progression["CurrentLevel"] = 2
        self.assertEqual(sigil.effect_lines()[-1], "Level 3 of 3.")
        sigil.progression.update(CurrentLevel=0, CurrentXP=14396)
        self.assertEqual(sigil.effect_lines()[-1], "Level 1 of 3 (14,396 of 18,480 XP). At the next levels: 1.25, then 1.35.")

    def test_a_copy_changed_into_another_item_keeps_its_effects(self):
        sword = self.item_index("SW.Item.Sword")
        effects = [rolled(rolled_effect("CriticalEdge", 0.1))]
        self.hero.item(sword).data["Effects"] = effects
        copy_index = self.hero.duplicate_item(sword)
        self.hero.update_item(copy_index, tag="SW.Item.Axe", rarity="Rare", power=20)
        axe = self.hero.item(copy_index)
        self.assertEqual((axe.name, axe.rarity, axe.power, axe.equipped_slot), ("Axe", "Rare", 20, None))
        self.assertEqual(axe.data["Effects"], effects)
        self.assertIsNot(axe.data["Effects"], self.hero.item(sword).data["Effects"])  # its own copy of them
        self.assertEqual(axe.effect_lines(), ["Critical Edge I 10%"])

    def test_effects_are_written_the_way_the_game_saves_them(self):
        sword = self.item_index("SW.Item.Sword")
        item = self.hero.item(sword)
        self.assertNotIn(UNSEEN, item.data["DynamicPropertyTags"])
        self.hero.set_effects(sword, [self.choice("Knockback"), self.choice("Critical Edge", "II")])
        self.assertEqual(json.dumps(item.data["Effects"]), GAME_BOW_EFFECTS)  # the same keys, in the same order
        # What the editor wrote isn't the game's word for anything until the game has shown you the item.
        self.assertIn(UNSEEN, item.data["DynamicPropertyTags"])
        # An effect the item keeps is left exactly as it is; the rest are made new.
        knockback = item.data["Effects"][0]["EffectsInThisBatch"][0]
        knockback["Quality"] = 7  # something the editor doesn't set
        self.hero.set_effects(sword, [self.choice("Looter"), self.choice("Knockback")])
        self.assertEqual([effect.text for effect in item.rolled_effects], ["Looter I 20%", "Knockback I 15%, quality 7"])
        self.assertIs(item.data["Effects"][0]["EffectsInThisBatch"][1], knockback)
        # The same effect at another tier takes its place.
        self.hero.set_effects(sword, [self.choice("Looter"), self.choice("Knockback", "III")])
        self.assertEqual(item.effect_lines(), ["Looter I 20%", "Knockback III 30%"])
        # No effects at all is saved the way the game saves a Common item: no batch.
        self.hero.set_effects(sword, [])
        self.assertEqual(item.data["Effects"], [])

    def test_what_effects_an_item_can_have(self):
        sword = self.item_index("SW.Item.Sword")
        most = heroes.effect_book().max_effects
        self.assertEqual(most, 4)
        five = [self.choice(name) for name in ("Knockback", "Looter", "Luck", "Vanguard", "Acrobat")]
        with self.assertRaisesRegex(ValueError, "caps an item at 4 effects"):
            self.hero.set_effects(sword, five)
        self.hero.set_effects(sword, five[:4])
        with self.assertRaisesRegex(ValueError, "same effect twice"):
            self.hero.set_effects(sword, [self.choice("Knockback"), self.choice("Knockback", "II")])
        with self.assertRaisesRegex(ValueError, "isn't one of the effects the game rolls"):
            self.hero.set_effects(sword, [self.choice("Healing Smite")])
        self.assertEqual(len(self.hero.item(sword).rolled_effects), 4)  # a refused change changes nothing
        # An effect saved some other way (the one a Unique comes with) is left alone, and counts towards the four.
        own = {"TypeTag": "SW.Item.Effect.Fixed", "EffectsInThisBatch": [rolled_effect("Burning", 1, "Unique")]}
        self.hero.item(sword).data["Effects"].insert(0, own)
        with self.assertRaisesRegex(ValueError, "caps an item at 4 effects, and the Sword has 1 of its own"):
            self.hero.set_effects(sword, five[:4])
        self.hero.set_effects(sword, five[:3])
        self.assertIs(self.hero.item(sword).data["Effects"][0], own)
        self.assertEqual([effect.name for effect in self.hero.item(sword).own_effects], ["Burning"])
        # Only weapons, armor and artifacts; and the merchant's stock is the game's doing.
        self.body["Inventory"]["Entries"] += [
            talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", seed=61),
            hero_item("SW.Item.Artifact.RallyingHorn", seed=62),
        ]
        with self.assertRaisesRegex(ValueError, "the game rolls them on weapons, armor and artifacts"):
            self.hero.set_effects(self.item_index("SW.Item.Talisman.HealthBoost"), five[:1])
        with self.assertRaisesRegex(ValueError, "Cosmetics"):
            self.hero.set_effects(self.item_index("SW.Item.Cosmetic.Cape.Hero"), five[:1])
        with self.assertRaisesRegex(ValueError, "Village Merchant's stock"):
            self.hero.set_effects(self.item_index("SW.Item.CurvedGreatsword"), five[:1])
        self.hero.set_effects(self.item_index("SW.Item.Artifact.RallyingHorn"), five[:1])  # an artifact can
        self.hero.item(sword).data["Effects"] = {"not": "a list"}
        with self.assertRaisesRegex(ValueError, "saved in a way the editor doesn't know"):
            self.hero.set_effects(sword, five[:1])

    def test_an_enchantment_is_written_the_way_the_enchantsmith_saves_it(self):
        helmet = self.item_index("SW.Item.MysticHelmet")
        item = self.hero.item(helmet)
        item.data["RarityTag"] = "SW.Rarity.Unique"
        item.data["DynamicPropertyTags"] = []
        self.hero.set_enchantment(helmet, self.choice("Ancient Alchemy", "II"))
        self.assertEqual(json.dumps(item.data["Effects"]), GAME_HELMET_EFFECTS)  # 8 points: tiers I and II on a Unique
        self.assertIn(UNSEEN, item.data["DynamicPropertyTags"])
        self.assertEqual((item.enchantment.title, item.effect_lines()), ("Ancient Alchemy II", ["Enchanted: Ancient Alchemy II, 8 enchantment points"]))
        same = item.data["Effects"][0]["EffectsInThisBatch"][0]
        self.hero.set_enchantment(helmet, self.choice("Ancient Alchemy", "II"))
        self.assertIs(item.data["Effects"][0]["EffectsInThisBatch"][0], same)  # it has it already: nothing to do
        # One enchantment an item: another takes its place. The points the game counts depend on the item's rarity.
        for rarity, points in (("Common", 1), ("Rare", 1), ("Special", 2), ("Unique", 3)):
            item.data["RarityTag"] = f"SW.Rarity.{rarity}"
            self.hero.set_enchantment(helmet, None)
            self.hero.set_enchantment(helmet, self.choice("Ancient Alchemy"))
            self.assertEqual([(effect.title, effect.points) for effect in item.effects], [("Ancient Alchemy I", points)], rarity)
        # The effects the game rolled go before it, as they would on an item enchanted after it dropped.
        self.hero.set_effects(helmet, [self.choice("Luck")])
        self.assertEqual([batch["TypeTag"] for batch in item.data["Effects"]], ["SW.Item.Effect.Rerollable", "SW.Item.Effect.Enchantment"])
        self.hero.set_enchantment(helmet, None)
        self.assertEqual(item.effect_lines(), ["Luck I 10%"])
        # An enchantment only goes where the game puts it.
        sword = self.item_index("SW.Item.Sword")
        with self.assertRaisesRegex(ValueError, "Piercing goes on ranged weapons, and the Sword isn't one"):
            self.hero.set_enchantment(sword, self.choice("Piercing"))
        with self.assertRaisesRegex(ValueError, "Ancient Alchemy goes on armor"):
            self.hero.set_enchantment(sword, self.choice("Ancient Alchemy"))
        self.hero.set_enchantment(sword, self.choice("Healing Smite"))  # weapons, melee or ranged
        self.hero.set_enchantment(self.item_index("SW.Item.Longbow"), self.choice("Piercing"))
        with self.assertRaisesRegex(ValueError, "Critical Edge isn't an enchantment"):
            self.hero.set_enchantment(sword, self.choice("Critical Edge"))
        self.body["Inventory"]["Entries"].append(hero_item("SW.Item.Artifact.RallyingHorn", seed=62))
        with self.assertRaisesRegex(ValueError, "can't be enchanted: enchantments go on weapons and armor"):
            self.hero.set_enchantment(self.item_index("SW.Item.Artifact.RallyingHorn"), self.choice("Healing Smite"))

    def test_effects_on_your_own_items_can_be_put_on_others(self):
        gear, enchantments = heroes.effect_choices([])
        listed = len(gear), len(enchantments)
        self.assertEqual([choice.title for choice in enchantments], ["Ancient Alchemy I", "Ancient Alchemy II", "Healing Smite I", "Piercing I"])
        knock = next(choice for choice in gear if choice.title == "Knockback III")
        self.assertEqual((knock.seen, knock.number, knock.strength, knock.rolls_on), (False, "30%", 0.3, "Any weapon"))  # from the game files' table
        self.assertEqual(knock.what, "Attacks do 30% more knockback.")  # in the game's own words
        self.assertEqual(next(choice for choice in gear if choice.title == "Spiritual I").strength, 1.25)  # 25% more
        self.assertEqual(next(choice for choice in gear if choice.title == "Lightning Focus I").maybe, "Electromancer")
        self.assertEqual(self.choice("Healing Smite").slots, ("Melee", "Ranged"))
        # An effect or enchantment the list doesn't have, on an item in a save, can be copied exactly as it is there.
        sword = self.hero.item(self.item_index("SW.Item.Sword"))
        sword.data["Effects"] = [
            rolled(rolled_effect("Thorns", 0.3, "II"), rolled_effect("Vanguard", 0.5, "III"), rolled_effect("Knockback", 0.25, "II")),
            enchanted(enchantment_effect("FireAspect", 0.9, "III", points=15)),
        ]
        gear, enchantments = heroes.effect_choices([self.hero])
        self.assertEqual((len(gear), len(enchantments)), (listed[0] + 1, listed[1] + 1))
        thorns, fire = self.choice("Thorns", "II"), self.choice("Fire Aspect", "III")
        self.assertEqual((thorns.yours, thorns.strength, thorns.template), (True, 0.3, "SW.EffectTemplate.Thorns.II"))
        self.assertEqual((fire.yours, fire.is_enchantment, fire.slots), (True, True, ("Melee",)))  # all that's known: it was on a melee weapon
        # A save showing a tier the list only had from the table makes it seen; and the save's number wins.
        self.assertTrue(self.choice("Vanguard", "III").seen)
        knockback = self.choice("Knockback", "II")
        self.assertEqual((knockback.seen, knockback.strength, knockback.number), (True, 0.25, "0.25"))
        # Put on another item, they're saved as they were found.
        bow = self.item_index("SW.Item.Longbow")
        self.hero.set_effects(bow, [thorns, knockback])
        self.assertEqual(self.hero.item(bow).data["Effects"], [rolled(rolled_effect("Thorns", 0.3, "II"), rolled_effect("Knockback", 0.25, "II"))])
        with self.assertRaisesRegex(ValueError, "Fire Aspect goes on melee weapons"):
            self.hero.set_enchantment(bow, fire)
        self.assertEqual([effect.as_choice() for effect in sword.rolled_effects][0], thorns)

    def test_a_talismans_xp_and_its_next_level(self):
        self.assertEqual(heroes.effect_book().talisman_xp, (18480, 73920))
        self.body["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", xp=90, seed=61))
        index = self.item_index("SW.Item.Talisman.HealthBoost")
        sigil = self.hero.item(index)
        self.assertEqual((sigil.level, sigil.xp, sigil.next_level_xp), (0, 90, 18480))
        # One XP short of the next level: the game does the levelling up itself, the next time it earns XP.
        self.assertEqual(self.hero.ready_talisman(index), 18479)
        self.assertEqual((sigil.xp, sigil.level, type(sigil.xp)), (18479, 0, int))
        self.hero.set_item_xp(index, 500.5)
        self.assertEqual(sigil.xp, 500.5)
        for bad in (-1, heroes.MAX_ITEM_XP + 1, "lots", True):
            with self.assertRaises(ValueError):
                self.hero.set_item_xp(index, bad)
        # At level 2, whichever way the save counts its XP, this is enough for the next XP earned to reach level 3.
        sigil.progression["CurrentLevel"] = 1
        self.assertEqual((sigil.next_level_xp, self.hero.ready_talisman(index)), (73920, 92399))
        sigil.progression["CurrentLevel"] = 2
        self.assertIsNone(sigil.next_level_xp)
        with self.assertRaisesRegex(ValueError, "last level"):
            self.hero.ready_talisman(index)
        sword = self.item_index("SW.Item.Sword")
        self.assertIsNone(self.hero.item(sword).next_level_xp)
        with self.assertRaisesRegex(ValueError, "only talismans do"):
            self.hero.set_item_xp(sword, 5)
        # A talisman with no levels saved has nothing to level into.
        bare = self.hero.add_item("SW.Item.Talisman.SomethingNew", self.entry("SW.Item.Sword"))
        with self.assertRaisesRegex(ValueError, "doesn't know what"):
            self.hero.ready_talisman(bare)

    def test_the_town_vendors_a_hero_has_opened(self):
        # Nothing says this hero has been to a vendor. The Village Merchant's stock doesn't: a hero has that from
        # the start, before the Merchant has been found.
        self.assertEqual(self.hero.vendors_opened(), {"Village Merchant": False, "Blacksmith": False, "Enchantsmith": False})
        # The game files a hint the first time you open each vendor's window.
        self.body["CollectionsStats"]["ShownHints"] = [
            {"Tag": "SW.UI.Onboarding.ActionList.Movement", "Count": 16},
            {"Tag": "SW.UI.Onboarding.Panel.Enchantsmith.Overview", "Count": 1},
        ]
        self.assertEqual(self.hero.vendors_opened(), {"Village Merchant": False, "Blacksmith": False, "Enchantsmith": True})
        self.body["CollectionsStats"]["ShownHints"].append({"Tag": "SW.UI.Onboarding.Panel.Blacksmith.Overview", "Count": 1})
        self.assertEqual(self.hero.vendors_opened()["Blacksmith"], True)
        # So do the counts it keeps of what a vendor did. What the editor writes doesn't count: an enchantment it
        # put on, or a vendor level it set.
        self.body["CollectionsStats"]["ShownHints"] = []
        self.hero.set_enchantment(self.item_index("SW.Item.Sword"), self.choice("Healing Smite"))
        self.hero.set_attributes({"VillageMerchantUpgradeLevel": 3})
        self.assertEqual(self.hero.vendors_opened(), {"Village Merchant": False, "Blacksmith": False, "Enchantsmith": False})
        self.body["Achievements"] = {
            "BoolAchievements": {
                "SW.Achievements.ReforgeASpecialPieceOfGear": {"bCompleted": True},
                "SW.Achievements.PurchaseASpecialGearPieceFromTheVillageMerchant": {"bCompleted": False},
            },
            "CountAchievements": {"SW.Achievements.UpgradeAnEnchantmentToLevel3": {"Count": 2}},
        }
        self.assertEqual(self.hero.vendors_opened(), {"Village Merchant": False, "Blacksmith": True, "Enchantsmith": True})
        self.body["Achievements"]["BoolAchievements"]["SW.Achievements.PurchaseASpecialGearPieceFromTheVillageMerchant"]["bCompleted"] = True
        self.assertEqual(self.hero.vendors_opened(), {"Village Merchant": True, "Blacksmith": True, "Enchantsmith": True})

    def test_changed_effects_are_described(self):
        self.body["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", xp=90, seed=61))
        before = copy.deepcopy(self.document)
        sword = self.item_index("SW.Item.Sword")
        self.hero.set_effects(sword, [self.choice("Knockback"), self.choice("Critical Edge", "II")])
        self.hero.set_enchantment(sword, self.choice("Healing Smite"))
        self.hero.ready_talisman(self.item_index("SW.Item.Talisman.HealthBoost"))
        self.assertEqual(heroes.describe_changes(before, self.document), [
            "Sword: effects: Knockback I 15%, Critical Edge II 20%, enchanted with Healing Smite I",
            "Sigil of Beeswax: XP 90 → 18,479",
        ])
        after = copy.deepcopy(self.document)
        self.hero.set_effects(sword, [])
        self.hero.set_enchantment(sword, None)
        self.assertEqual(heroes.describe_changes(after, self.document), ["Sword: effects: none, enchantment taken off"])

    def test_the_save_format_the_editor_was_checked_against(self):
        self.assertEqual((self.hero.save_format, self.hero.format_is_tested), (("FCharacterSaveV1", 5), True))
        self.document["SerializeMeta"]["SoftVersion"] = 6  # a game update changed how heroes are saved
        self.assertEqual((self.hero.save_format, self.hero.format_is_tested), (("FCharacterSaveV1", 6), False))

    def test_a_talisman_is_added_the_way_the_game_saves_one(self):
        catalog = {entry.tag: entry for entry in heroes.build_catalog([self.hero])}
        sigil = catalog["SW.Item.Talisman.HealthBoost"]  # the Sigil of Beeswax: its effect has been seen in a real save
        self.assertTrue(sigil.confirmed)
        index = self.hero.add_item(sigil.tag, sigil.template, rarity="Unique", power=40)  # a talisman has neither
        item = self.hero.item(index)
        self.assertEqual((item.rarity, item.power, item.data["RarityTag"]), ("None", -1, "SW.Rarity.None"))
        (batch,) = item.data["Effects"]
        (effect,) = batch["EffectsInThisBatch"]
        self.assertEqual(batch["TypeTag"], "SW.Item.Effect.Upgradable")
        self.assertEqual(
            effect,
            {
                "TypeTag": "SW.Effect.HealthBoost", "Intensity": 1.2, "Quality": 0, "EnchantmentPointsInvested": 0,
                "GeneratorData": {"GeneratorParentTemplate": "SW.EffectTemplate.HealthBoost.I", "Locked": False},
            },
        )
        levels = item.data["ItemProgression"]["ItemLevels"]
        self.assertEqual([level["LevelEffects"][0]["Intensity"] for level in levels], [1.2, 1.25, 1.35])
        self.assertEqual(levels[2]["LevelEffects"][0]["GeneratorData"]["GeneratorParentTemplate"], "SW.EffectTemplate.HealthBoost.III")
        self.assertEqual(levels[0]["LevelEffects"][0], effect)
        power = item.data["GeneratorData"]["PowerGeneratorValues"]
        self.assertEqual({key: power[key] for key in ("PlayerLevel", "ItemPowerMin", "ItemPowerMax", "RNGRoll", "ItemPower", "ItemPowerOriginal")},
                         {"PlayerLevel": 1, "ItemPowerMin": 1, "ItemPowerMax": 11, "RNGRoll": 0, "ItemPower": -1, "ItemPowerOriginal": 0})
        for change in ({"rarity": "Rare"}, {"power": 5}):
            with self.assertRaises(ValueError):
                self.hero.update_item(index, **change)
        self.hero.update_item(index, rarity="None", power=-1, count=1)  # nothing changes, so nothing is refused

    def test_a_talisman_whose_effect_isnt_known_is_a_guess_unless_the_hero_has_one(self):
        tag = "SW.Item.Talisman.AmmoCapacity"  # the Twig of Dark Oak: its ID has been seen in a save, its effect hasn't
        twig = next(entry for entry in heroes.build_catalog([self.hero]) if entry.tag == tag)
        self.assertEqual((twig.confirmed, twig.no_effect, twig.confirmed_at()), (True, True, False))
        self.assertIn("added without one and may do nothing", twig.doubt())
        bare = self.hero.item(self.hero.add_item(tag, twig.template)).data
        self.assertEqual((bare["RarityTag"], bare["Effects"], bare["ItemProgression"]["ItemLevels"]), ("SW.Rarity.None", [], []))
        # One the game handed over carries its effect, and a new one is laid out like it, not like the bare one.
        real = talisman_item(tag, "AmmoCapacity", (1.2, 1.4, 1.6), level=2, xp=500, seed=90)
        self.body["Inventory"]["Entries"].append(real)
        twig = next(entry for entry in heroes.build_catalog([self.hero]) if entry.tag == tag)
        self.assertEqual((twig.no_effect, twig.confirmed_at(), twig.doubt()), (False, True, ""))
        self.assertIs(twig.template, real)
        new = self.hero.item(self.hero.add_item(tag, twig.template)).data
        levels = real["ItemData"]["ItemProgression"]["ItemLevels"]
        self.assertEqual((new["ItemProgression"]["CurrentLevel"], new["ItemProgression"]["CurrentXP"]), (0, 0))  # a new one starts at level 1
        self.assertEqual(new["ItemProgression"]["ItemLevels"], levels)
        self.assertEqual(new["Effects"], [{"TypeTag": "SW.Item.Effect.Upgradable", "EffectsInThisBatch": levels[0]["LevelEffects"]}])
        # The one you had is untouched.
        self.assertEqual((real["ItemData"]["ItemProgression"]["CurrentLevel"], real["ItemData"]["Effects"][0]["EffectsInThisBatch"]), (2, levels[2]["LevelEffects"]))
        # A talisman whose ID is a guess as well is doubtful twice over.
        clover = next(entry for entry in heroes.build_catalog([self.hero]) if entry.tag == "SW.Item.Talisman.LuckyClover")
        self.assertEqual((clover.confirmed, clover.no_effect, clover.confirmed_at()), (False, True, False))
        self.assertIn("best guess", clover.doubt())

    def test_changing_an_item_into_a_talisman_lays_it_out_as_one(self):
        catalog = {entry.tag: entry for entry in heroes.build_catalog([self.hero])}
        before = copy.deepcopy(self.document)
        index = self.hero.add_item("SW.Item.Battlestaff", catalog["SW.Item.Battlestaff"].template, rarity="Rare", power=12)
        self.hero.update_item(index, tag="SW.Item.Talisman.HealthBoost")
        item = self.hero.item(index)
        self.assertEqual((item.name, item.is_talisman, item.rarity, item.power), ("Sigil of Beeswax", True, "None", -1))
        self.assertEqual([level["LevelEffects"][0]["Intensity"] for level in item.progression["ItemLevels"]], [1.2, 1.25, 1.35])
        self.assertEqual(item.data["Effects"][0]["EffectsInThisBatch"], item.progression["ItemLevels"][0]["LevelEffects"])
        self.assertEqual(heroes.describe_changes(before, self.document), ["Added Sigil of Beeswax"])  # no rarity or power to tell
        # Into a talisman whose effect isn't known: laid out as one, without an effect.
        self.hero.update_item(index, tag="SW.Item.Talisman.AmmoCapacity")
        item = self.hero.item(index)
        self.assertEqual((item.name, item.rarity, item.data["Effects"], item.progression["ItemLevels"]), ("Twig of Dark Oak", "None", [], []))
        # And back into gear: it can have a rarity and a power again.
        self.hero.update_item(index, tag="SW.Item.Battlestaff")
        self.hero.update_item(index, rarity="Rare", power=12)
        item = self.hero.item(index)
        self.assertEqual((item.is_talisman, item.rarity, item.power), (False, "Rare", 12))

    def test_enchantment_books_are_only_offered_when_the_hero_has_one(self):
        book = "SW.Item.EnchantmentBook.MultiRoll"
        self.assertNotIn(book, {entry.tag for entry in heroes.build_catalog([self.hero])})
        self.document["CharacterSaveV1"]["Inventory"]["Entries"].append(hero_item(book, seed=78))
        entry = next(entry for entry in heroes.build_catalog([self.hero]) if entry.tag == book)
        self.assertEqual((entry.name, entry.kind, entry.template["ItemData"]["TypeTag"]), ("Somersault", heroes.BOOK_KIND, book))

    def test_books_in_the_collections_are_not_on_offer_without_one_to_copy(self):
        # The game files every book you've found in its collections. That used to put each of them in Add items,
        # nameless ones included, to be laid out like whatever gear came to hand.
        listed, unlisted = "SW.Item.EnchantmentBook.Shockwave", "SW.Item.EnchantmentBook.NotInTheList"
        self.body["CollectionsStats"]["CollectedEnchantmentBooksOffensive"] = [listed, unlisted]
        self.assertTrue({listed, unlisted} <= set(self.hero.item_types_from_the_game()))
        self.assertFalse({listed, unlisted} & {entry.tag for entry in heroes.build_catalog([self.hero])})
        self.body["Inventory"]["Entries"].append(hero_item(unlisted, seed=79, unseen=False))
        entry = next(entry for entry in heroes.build_catalog([self.hero]) if entry.tag == unlisted)
        self.assertEqual((entry.name, entry.template["ItemData"]["TypeTag"]), ("Not In The List", unlisted))

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
        self.assertTrue(catalog["SW.Item.CaveCrawlerChest"].confirmed)  # reported from a real save
        self.assertFalse(catalog["SW.Item.Battlestaff"].confirmed)  # a best guess from its name
        self.assertEqual(catalog["SW.Item.Hammer"].unique, "Emerald Hammer")  # the Battle Hammer
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


class UniqueOwnEffectTests(unittest.TestCase):
    """A Unique comes with an effect of its own, saved apart from the ones the game rolls. The editor writes the
    ones it has seen in a real save, and says when a Unique is without its own."""

    BLADE = {  # The Burning Blade's, as a real save holds it (issue 20)
        "TypeTag": "SW.Item.Effect.Static",
        "EffectsInThisBatch": [{
            "TypeTag": "SW.Effect.FireFocus", "Intensity": 0.2, "Quality": 0, "EnchantmentPointsInvested": 0,
            "GeneratorData": {"GeneratorParentTemplate": "SW.EffectTemplate.FireFocus.Unique", "Locked": False},
        }],
    }

    def unique(self, *batches, tag="SW.Item.Sword_Unique1", rarity="Unique"):
        save = hero_save()
        entry = hero_item(tag, rarity=rarity)
        entry["ItemData"]["Effects"] = list(batches)
        save["CharacterSaveV1"]["Inventory"]["Entries"] = [entry]
        return Hero(save).item(0)

    def hero_and_sword(self):
        hero = Hero(hero_save())
        return hero, next(item for item in hero.items() if item.tag == "SW.Item.Sword")

    def test_the_list_knows_what_a_unique_comes_with(self):
        blade = heroes.own_effect("SW.Item.Sword_Unique1")
        self.assertEqual((blade.effect, blade.strength, blade.template, blade.seen), ("SW.Effect.FireFocus", 0.2, "SW.EffectTemplate.FireFocus.Unique", True))
        # Under an ID nobody has seen yet, the Unique is still the one the pattern says, and its effect was seen.
        self.assertEqual(heroes.own_effect("SW.Item.MysticHelmet_Unique").template, "SW.EffectTemplate.LightningFocus.Unique")
        # The Slaymore's hasn't been seen: it's the one saved for the Humbler Greaves, which do the same thing.
        slaymore = heroes.own_effect("SW.Item.Claymore_Unique1")
        self.assertEqual((slaymore.seen, slaymore.like, slaymore.effect), (False, "Humbler Greaves", "SW.Effect.SweepingEdge"))
        for tag in ("SW.Item.Sword", "SW.Item.Bow_Unique1", "SW.Item.Talisman.HealthBoost", "SW.Item.Nonsense_Unique1"):
            self.assertIsNone(heroes.own_effect(tag), tag)  # not a Unique, or one whose own effect hasn't been seen

    def test_a_unique_is_added_with_its_own_effect(self):
        hero, sword = self.hero_and_sword()
        blade = hero.item(hero.add_item("SW.Item.Sword", sword.entry, rarity="Unique"))
        self.assertEqual((blade.tag, blade.data["Effects"]), ("SW.Item.Sword_Unique1", [self.BLADE]))
        self.assertEqual(json.dumps(blade.data["Effects"]), json.dumps([self.BLADE]))  # in the game's order of keys
        self.assertFalse(blade.own_effect_missing or blade.own_effect_note)
        self.assertEqual(blade.effect_lines(), ["Its own: Fire Focus"])
        self.assertEqual([(effect.is_own, effect.is_rolled, effect.tier) for effect in blade.effects], [(True, False, "")])
        # Any other rarity is the plain Sword, with nothing of its own; so is a Unique the editor hasn't seen one for.
        self.assertEqual(hero.item(hero.add_item("SW.Item.Sword", sword.entry, rarity="Special")).data["Effects"], [])
        promise = hero.item(hero.add_item("SW.Item.Bow_Unique1", sword.entry, rarity="Unique"))  # the Ranger's Promise
        self.assertEqual((promise.data["Effects"], promise.own_effect_missing, promise.can_get_own_effect), ([], True, False))
        self.assertEqual(promise.own_effect_note, "Without its own effect: the editor can't add that one yet.")

    def test_its_own_effect_goes_with_what_the_item_is(self):
        hero, worn = self.hero_and_sword()
        sword = hero.item(hero.add_item("SW.Item.Sword", worn.entry))  # one in the backpack: what's equipped can't change into another item
        sword.data["Effects"] = [rolled(rolled_effect("CriticalEdge", 0.2, "II")), enchanted(enchantment_effect("Radiance", 0.3))]
        kept = copy.deepcopy(sword.data["Effects"])
        hero.update_item(sword.index, rarity="Unique")  # The Burning Blade's ID has been seen, so the Sword becomes it
        blade = hero.item(sword.index)
        self.assertEqual((blade.tag, blade.data["Effects"]), ("SW.Item.Sword_Unique1", [self.BLADE] + kept))  # its own comes first
        hero.update_item(sword.index, tag="SW.Item.Claymore_Unique1")  # changed into another Unique: the Slaymore
        slaymore = hero.item(sword.index)
        self.assertEqual((slaymore.tag, slaymore.data["Effects"][0]["EffectsInThisBatch"][0]["TypeTag"], slaymore.data["Effects"][1:]),
                         ("SW.Item.Claymore_Unique1", "SW.Effect.SweepingEdge", kept))
        hero.update_item(sword.index, rarity="Rare")  # no longer a Unique: nothing of its own is left on it
        self.assertEqual((hero.item(sword.index).tag, hero.item(sword.index).data["Effects"]), ("SW.Item.Claymore", kept))
        hero.update_item(sword.index, tag="SW.Item.Bow_Unique1", rarity="Unique")  # a Unique the editor hasn't seen one for
        self.assertEqual(hero.item(sword.index).data["Effects"], kept)
        self.assertTrue(hero.item(sword.index).own_effect_missing)

    def test_changing_the_other_effects_leaves_its_own_alone(self):
        hero, sword = self.hero_and_sword()
        index = hero.add_item("SW.Item.Sword", sword.entry, rarity="Unique")
        gear, enchantments = heroes.effect_choices([])
        edge = next(choice for choice in gear if choice.title == "Critical Edge II")
        smite = next(choice for choice in enchantments if choice.title == "Healing Smite I")
        hero.set_enchantment(index, smite)
        hero.set_effects(index, [edge])
        kinds = [batch["TypeTag"].rsplit(".", 1)[1] for batch in hero.item(index).data["Effects"]]
        self.assertEqual(kinds, ["Static", "Rerollable", "Enchantment"])  # the order a real save keeps them in
        self.assertEqual(hero.item(index).data["Effects"][0], self.BLADE)
        self.assertEqual(hero.item(index).effect_lines(), ["Its own: Fire Focus", "Critical Edge II 20%", "Enchanted: Healing Smite I, 3 enchantment points"])
        # Its own counts towards the four the game allows, so three more is the most.
        three = [choice for choice in gear if choice.tier == "I"][:3]
        hero.set_effects(index, three)
        with self.assertRaisesRegex(ValueError, "caps an item at 4 effects, and the The Burning Blade has 1 of its own"):
            hero.set_effects(index, [choice for choice in gear if choice.tier == "I"][:4])
        hero.set_effects(index, [])
        hero.set_enchantment(index, None)
        self.assertEqual(hero.item(index).data["Effects"], [self.BLADE])
        # A copy is the same Unique, effect and all.
        self.assertEqual(hero.item(hero.duplicate_item(index)).data["Effects"], [self.BLADE])

    def test_a_unique_without_its_own_effect_can_be_given_it(self):
        # As an older version of the editor made one: no effects, or only the ones it could write then.
        for batches in ((), (rolled(rolled_effect("CriticalEdge", 0.2, "II")), enchanted(enchantment_effect("Radiance", 0.3)))):
            save = hero_save()
            entry = hero_item("SW.Item.Sword_Unique1", rarity="Unique", unseen=False)
            entry["ItemData"]["Effects"] = list(batches)
            save["CharacterSaveV1"]["Inventory"]["Entries"] = [entry]
            hero = Hero(save)
            item = hero.item(0)
            self.assertEqual((item.own_effect_missing, item.can_get_own_effect, item.own_effect_note), (True, True, "Without its own effect."))
            before = copy.deepcopy(save)
            hero.give_own_effect(0)
            self.assertEqual(hero.item(0).data["Effects"], [self.BLADE] + list(batches))
            self.assertFalse(hero.item(0).own_effect_missing)
            self.assertIn(heroes.UNSEEN_TAG, hero.item(0).data["DynamicPropertyTags"])  # the editor's doing until the game shows it
            self.assertEqual(heroes.describe_changes(before, save), ["The Burning Blade: given its own effect"])
            with self.assertRaisesRegex(ValueError, "has its own effect already"):
                hero.give_own_effect(0)

    def test_what_cant_be_given_one_says_why(self):
        hero, sword = self.hero_and_sword()
        self.assertEqual((heroes.the("Sword"), heroes.the("Sword", start=True), heroes.the("The Burning Blade")), ("the Sword", "The Sword", "The Burning Blade"))
        with self.assertRaisesRegex(ValueError, "The Sword isn't a Unique"):
            hero.give_own_effect(sword.index)
        promise = hero.add_item("SW.Item.Bow_Unique1", sword.entry, rarity="Unique")
        with self.assertRaisesRegex(ValueError, "hasn't seen how the game saves the Ranger's Promise's own effect yet"):
            hero.give_own_effect(promise)
        # With four effects on it already, its own would be a fifth.
        blade = hero.add_item("SW.Item.Sword", sword.entry, rarity="Unique")
        hero.item(blade).data["Effects"] = [rolled(*[rolled_effect(f"Effect{number}", number) for number in range(1, 5)])]
        with self.assertRaisesRegex(ValueError, "caps an item at 4 effects, and The Burning Blade has 4. Take one off first."):
            hero.give_own_effect(blade)

    def test_an_item_can_hold_the_effect_it_comes_with_a_second_time(self):
        # The game does this itself: a Pride of the Plains (Duelist of its own) has been seen with Duelist rolled on
        # it, and a Redstone Wrecker (Fire Aspect built in) enchanted with Fire Aspect. So the editor allows it.
        hero, sword = self.hero_and_sword()
        crown = hero.add_item("SW.Item.MysticHelmet_Unique", sword.entry, rarity="Unique")  # the Oracle Crown: lightning damage
        gear, _enchantments = heroes.effect_choices([])
        lightning = next(choice for choice in gear if choice.effect == "SW.Effect.LightningFocus")
        hero.set_effects(crown, [lightning])
        self.assertEqual([(effect.tag, effect.is_own) for effect in hero.item(crown).effects],
                         [("SW.Effect.LightningFocus", True), ("SW.Effect.LightningFocus", False)])
        save = hero_save()
        entry = hero_item("SW.Item.Greatbow_Unique1", rarity="Unique")
        entry["ItemData"]["Effects"] = [{"TypeTag": "SW.Item.Effect.Static", "EffectsInThisBatch": [enchantment_effect("Radiance", 10)]}]
        save["CharacterSaveV1"]["Inventory"]["Entries"] = [entry]
        bow = Hero(save)
        smite = next(choice for choice in heroes.effect_choices([])[1] if choice.title == "Healing Smite I")
        bow.set_enchantment(0, smite)
        self.assertEqual([batch["TypeTag"].rsplit(".", 1)[1] for batch in bow.item(0).data["Effects"]], ["Static", "Enchantment"])
        self.assertEqual(bow.item(0).enchantment.title, "Healing Smite I")

    def test_an_effect_saved_some_other_way_counts_as_its_own(self):
        item = self.unique({"TypeTag": "SW.Item.Effect.Fixed", "EffectsInThisBatch": [rolled_effect("Burning", 1, "Unique")]})
        self.assertFalse(item.own_effect_missing or item.own_effect_note)  # the editor leaves what it doesn't know alone

    def test_only_a_unique_has_one(self):
        for tag, rarity in (("SW.Item.Sword", "Common"), ("SW.Item.MysticHelmet", "Unique"), ("SW.Item.Talisman.HealthBoost", "Common")):
            item = self.unique(tag=tag, rarity=rarity)  # a base item at Unique rarity isn't its Unique
            self.assertFalse(item.own_effect_missing or item.can_get_own_effect or item.own_effect_note, tag)

    def test_an_enchantment_under_another_name_is_written_as_saved(self):
        # The Prime Enchanter's Gauntlets' waves of lightning and ice, the effect issue 19 asked for: an enchantment
        # with no tier on its template, which no pattern would have given.
        hero, sword = self.hero_and_sword()
        gauntlets = hero.item(hero.add_item("SW.Item.Gauntlet_Unique1", sword.entry, rarity="Unique"))
        self.assertEqual(gauntlets.data["Effects"], [{
            "TypeTag": "SW.Item.Effect.Static",
            "EffectsInThisBatch": [{
                "TypeTag": "SW.Enchantment.MaulerDive", "Intensity": 1, "Quality": 0, "EnchantmentPointsInvested": 0,
                "GeneratorData": {"GeneratorParentTemplate": "SW.Enchantment.MaulerDive", "Locked": False},
            }],
        }])
        self.assertEqual(gauntlets.effect_lines(), ["Its own: Mauler Dive"])
        self.assertIsNone(gauntlets.enchantment)  # it isn't the Enchantsmith's: the item can still be enchanted


class LocalNameTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(heroes.use_local_names, {})

    def test_your_names_fill_in_for_names_made_from_ids(self):
        self.assertEqual(heroes.display_name("SW.Item.Artifact.HasteMushroom"), "Haste Mushroom")
        self.assertFalse(heroes.name_is_known("SW.Item.Artifact.HasteMushroom"))
        heroes.use_local_names({"SW.Item.Artifact.HasteMushroom": "Tempo Truffle", "SW.Item.Sword": "Not a sword"})
        self.assertEqual(heroes.display_name("SW.Item.Artifact.HasteMushroom"), "Tempo Truffle")
        self.assertTrue(heroes.name_is_known("SW.Item.Artifact.HasteMushroom"))
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
