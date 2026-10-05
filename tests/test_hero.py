import copy
import tempfile
import unittest
from pathlib import Path

from dungeons2_editor import hero as heroes
from dungeons2_editor import my_items
from dungeons2_editor.hero import Hero

from .helpers import hero_item, hero_save, talisman_item


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

    def test_effects_are_read_the_way_a_save_holds_them(self):
        sword = self.hero.item(self.item_index("SW.Item.Sword"))
        self.assertEqual((sword.effects, sword.effect_lines()), ([], []))
        sword.data["Effects"] = [
            {"TypeTag": "SW.Item.Effect.Enchantment", "EffectsInThisBatch": [
                {"TypeTag": "SW.Effect.FireAspect", "Intensity": 0.5, "Quality": 2, "EnchantmentPointsInvested": 3,
                 "GeneratorData": {"GeneratorParentTemplate": "SW.EffectTemplate.FireAspect.II", "Locked": True}},
                {"TypeTag": "SW.Effect.Sharpness", "Intensity": 12},
                "not an effect",
            ]},
            {"TypeTag": "SW.Item.Effect.Other"},  # a batch laid out some other way is left out, not guessed at
            "not a batch",
        ]
        first, second = sword.effects
        self.assertEqual((first.name, first.tag, first.strength, first.quality, first.points, first.locked, first.group),
                         ("Fire Aspect", "SW.Effect.FireAspect", 0.5, 2, 3, True, "SW.Item.Effect.Enchantment"))
        self.assertEqual(sword.effect_lines(), ["Fire Aspect 0.5, quality 2, 3 enchantment points, locked", "Sharpness 12"])
        self.assertEqual(heroes.sort_items(self.hero.items(), "Most effects")[0].tag, "SW.Item.Sword")
        # A talisman also says which level it's at, and what's to come.
        self.body["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", level=1, seed=61))
        sigil = self.hero.item(self.item_index("SW.Item.Talisman.HealthBoost"))
        self.assertEqual(sigil.effect_lines(), ["Health Boost 1.25", "Level 2 of 3. At the next level: 1.35."])
        sigil.progression["CurrentLevel"] = 2
        self.assertEqual(sigil.effect_lines()[-1], "Level 3 of 3.")

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
