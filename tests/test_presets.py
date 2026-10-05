import unittest

from dungeons2_editor import hero as heroes
from dungeons2_editor import presets
from dungeons2_editor.hero import Hero, build_catalog

from .helpers import enchanted, enchantment_effect, hero_item, hero_save, talisman_item


def by_title(title):
    return next(p for p in presets.PRESETS if p.title == title)


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.document = hero_save()
        self.hero = Hero(self.document)
        # A second hero who has already found a Lucky Clover and The Eye of Experience.
        other = hero_save()
        other["CharacterSaveV1"]["Inventory"]["Entries"] += [
            talisman_item("SW.Item.Talisman.LuckyClover", "LuckyClover", seed=11, unseen=False),
            talisman_item("SW.Item.Talisman.EyeOfExperience", "EyeOfExperience", seed=12, unseen=False),
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
            # Enchantments as MetaBot's build planner places them: on a weapon and the helmet, and mostly the chestplate.
            pieces = {entry.piece or entry.kind: item for item, entry in zip(kit.items, found)}
            self.assertTrue(any(pieces[kind].enchants for kind in ("Melee", "Ranged") if kind in pieces) and pieces["Helmet"].enchants, kit.title)
            self.assertFalse(pieces["Leggings"].enchants or pieces["Boots"].enchants, kit.title)
            # Every weapon, armor piece and artifact names effects to roll; a talisman's effect is its own.
            self.assertTrue(all(bool(item.effects) == (entry.kind != "Talisman") for item, entry in zip(kit.items, found)), kit.title)
        self.assertGreaterEqual(sum(bool(pieces["Chestplate"].enchants) for pieces in (
            {entry.piece: item for item, entry in zip(kit.items, [presets.find_item(i.name, self.catalog) for i in kit.items]) if entry.piece}
            for kit in kits
        )), 5)

    def test_a_kit_enchants_once_the_hero_has_opened_the_enchantsmith(self):
        kit = presets.Preset("Test kit", "A goal.", "Details.", sources=("https://example.com",), group=presets.KITS, choose_rarity=True, items=(
            presets.KitItem("Sword", "Melee", "Hits things.", enchants=("Lightning Surge", "Healing Smite"),
                            effects=("Sharpness", "Critical Edge", "Looter", "Luck")),
            presets.KitItem("Longbow", "Ranged", "Shoots things.", enchants=("Chain Reaction", "Ricochet")),
            presets.KitItem("Mystic Circlet", "Armor", "Looks wise.", enchants=("Ancient Alchemy",)),
        ))

        def added(plan):
            return {addition.kit.name: (addition.enchantment.title if addition.enchantment else None, [choice.title for choice in addition.effects])
                    for addition in plan.add}

        # Nothing in the save says this hero has been to the Enchantsmith: no enchantments. The gear the kit adds
        # still gets the effects the game would roll for it: two on a Special item, from the ones the editor can
        # write (it hasn't seen Sharpness saved), each at the best tier a save has shown.
        plan = presets.plan(kit, self.hero, self.catalog, power=20, rarity="Special")
        self.assertFalse(plan.enchant)
        self.assertEqual(added(plan), {"Sword": (None, ["Critical Edge II", "Looter I"]), "Longbow": (None, []), "Mystic Circlet": (None, [])})
        # Once it has, each item gets the first of its enchantments that the editor can write and that fits it.
        self.hero.body["CollectionsStats"]["ShownHints"] = [{"Tag": "SW.UI.Onboarding.Panel.Enchantsmith.Overview", "Count": 1}]
        plan = presets.plan(kit, self.hero, self.catalog, power=20, rarity="Special")
        self.assertTrue(plan.enchant)
        self.assertEqual(added(plan), {
            "Sword": ("Healing Smite I", ["Critical Edge II", "Looter I"]),  # Lightning Surge hasn't been seen saved yet
            "Longbow": (None, []),  # nor has Chain Reaction
            "Mystic Circlet": ("Ancient Alchemy II", []),
        })
        self.assertEqual(presets.enchanted_by(plan)[id(kit.items[0])].title, "Healing Smite I")
        self.assertIn("Add Sword (Special, power 20): Hits things. With Critical Edge II, Looter I, enchanted with Healing Smite I.", presets.describe(plan, self.hero))
        self.assertEqual(added(presets.plan(kit, self.hero, self.catalog, power=20, rarity="Special", enchant=False))["Sword"][0], None)
        self.assertEqual(added(presets.plan(kit, self.hero, self.catalog, power=20, rarity="Unique"))["Sword"][1], ["Critical Edge II"])  # one on a Unique
        self.assertEqual(added(presets.plan(kit, self.hero, self.catalog, power=20, rarity="Common"))["Sword"][1], [])
        presets.apply(plan, self.hero, self.catalog)
        sword = max((item for item in self.hero.items() if item.tag == "SW.Item.Sword"), key=lambda item: item.power)
        self.assertEqual(sword.effect_lines(), ["Critical Edge II 20%", "Looter I 20%", "Enchanted: Healing Smite I, 2 enchantment points"])
        circlet = max((item for item in self.hero.items() if item.tag == "SW.Item.MysticHelmet"), key=lambda item: item.power)
        self.assertEqual(circlet.effect_lines(), ["Enchanted: Ancient Alchemy II, 6 enchantment points"])
        # An enchantment found on an item in the saves can be written too. Its book says what it's called and what
        # it goes on (the book saved as Ricochet is Ricochet, for ranged weapons); without a named book, all the
        # editor knows is the kind of item it was on.
        bow = next(item for item in self.hero.items() if item.tag == "SW.Item.Longbow" and item.rarity == "Rare")
        bow.data["Effects"] = [enchanted(enchantment_effect("Ricochet", 3, "III", points=9))]
        sword.data["Effects"] = [enchanted(enchantment_effect("ChainLightning", 0.4, "II", points=6))]
        learned = heroes.effect_choices([self.hero])
        self.assertEqual([(choice.title, choice.slots) for choice in learned[1] if choice.yours],
                         [("Chain Lightning II", ("Melee",)), ("Ricochet III", ("Ranged",))])
        again = presets.plan(kit, self.hero, self.catalog, power=30, rarity="Special", effects=learned)
        self.assertEqual(added(again)["Longbow"], ("Ricochet III", []))

    def test_a_kit_enchants_your_own_copy_only_when_it_has_no_enchantment(self):
        kit = presets.Preset("Test kit", "A goal.", "Details.", sources=("https://example.com",), items=(
            presets.KitItem("Sword", "Melee", "Hits things.", enchants=("Healing Smite",), effects=("Looter",)),
        ))
        self.assertFalse(presets.plan(kit, self.hero, self.catalog, power=1).changes_anything)  # it has the Sword already
        self.hero.body["CollectionsStats"]["ShownHints"] = [{"Tag": "SW.UI.Onboarding.Panel.Enchantsmith.Overview", "Count": 1}]
        plan = presets.plan(kit, self.hero, self.catalog, power=1)
        self.assertEqual(([owned.enchantment.title for owned in plan.have], plan.changes_anything), (["Healing Smite I"], True))
        self.assertEqual(presets.describe(plan, self.hero), ["Your Sword: enchanted with Healing Smite I"])
        presets.apply(plan, self.hero, self.catalog)
        sword = next(item for item in self.hero.items() if item.tag == "SW.Item.Sword")
        self.assertEqual(sword.effect_lines(), ["Enchanted: Healing Smite I, 1 enchantment point"])  # the effects the game rolled for it stay as they are
        again = presets.plan(kit, self.hero, self.catalog, power=1)
        self.assertEqual(([owned.enchantment for owned in again.have], again.changes_anything), ([None], False))  # the one it has is kept

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
        self.assertEqual(added.data["Effects"][0]["EffectsInThisBatch"][0]["TypeTag"], "SW.Effect.EyeOfExperience")  # with its effect
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
        )  # not the merchant's Cookiecutter, not the cape
        self.assertIn("Sword: Common → Unique, power 1 → 60", presets.describe(plan, self.hero))
        presets.apply(plan, self.hero, self.catalog)
        # The Sword's Unique has an ID of its own that has been seen in a save, so the Sword becomes that item.
        sword = self.hero.equipped("SW.ItemSlot.Equipment.MeleeWeapon")
        self.assertEqual((sword.tag, sword.name, sword.rarity, sword.power), ("SW.Item.Sword_Unique1", "The Burning Blade", "Unique", 60))
        # The Oracle Crown's hasn't, so the Mystic Circlet only changes rarity: a wrong guess would cost the item.
        helmet = next(item for item in self.hero.items() if item.tag == "SW.Item.MysticHelmet")
        self.assertEqual((helmet.name, helmet.rarity, helmet.power), ("Mystic Circlet", "Unique", 60))

    def test_unique_names_and_unconfirmed_items(self):
        found = presets.find_item("Emerald Hammer", self.catalog)
        # The Battle Hammer's ID is known. Its Unique's own ID hasn't been seen, but follows the pattern every seen one does.
        self.assertEqual((found.tag, found.confirmed, found.tag_at("Unique"), found.id_known_at("Unique"), found.confirmed_at("Unique")),
                         ("SW.Item.Hammer", True, "SW.Item.Hammer_Unique1", False, True))
        careful = presets.plan(by_title("Best loot"), self.hero, self.catalog, power=30)
        self.assertIn("Emerald Hammer", [addition.kit.name for addition in careful.add])  # so a kit adds it without being asked to
        self.assertEqual([kit.name for kit, _ in careful.unconfirmed], ["Looter's Charm"])  # its ID is a guess, and its effect unknown
        bold = presets.plan(by_title("Best loot"), self.hero, self.catalog, power=30, include_unconfirmed=True)
        self.assertIn("Looter's Charm", [addition.kit.name for addition in bold.add])
        self.assertTrue(any(line.endswith("(unconfirmed: without its effect)") for line in presets.describe(bold, self.hero)))
        # A kit with gear whose own ID is a guess still leaves that out.
        kit = presets.plan(by_title("Melee damage"), self.hero, self.catalog, power=30, rarity="Unique")
        self.assertTrue(kit.unconfirmed)
        self.assertTrue(all(not found.id_trusted_at(presets.rarity_for(item, found, "Unique")) or found.no_effect for item, found in kit.unconfirmed))
        presets.apply(bold, self.hero, self.catalog)
        hammer = next(item for item in self.hero.items() if item.tag == "SW.Item.Hammer_Unique1")
        self.assertEqual((hammer.name, hammer.rarity, hammer.power), ("Emerald Hammer", "Unique", 30))

    def test_best_gear_at_the_picked_rarity_and_power_equipped(self):
        plan = presets.plan(by_title("Best melee weapon"), self.hero, self.catalog, power=45, include_unconfirmed=True, rarity="Rare", equip=True)
        (addition,) = plan.add
        self.assertEqual((addition.name, addition.rarity, addition.slot.label), ("Riftslasher", "Rare", "Melee weapon"))
        self.assertIn("Add Riftslasher (Rare, power 45) and equip it (melee weapon)", presets.describe(plan, self.hero)[0])
        presets.apply(plan, self.hero, self.catalog)
        blade = self.hero.equipped("SW.ItemSlot.Equipment.MeleeWeapon")
        self.assertEqual((blade.tag, blade.rarity, blade.power), ("SW.Item.CurvedLongsword", "Rare", 45))
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
        self.assertEqual({a.rarity for a in talismans.add}, {"None"})  # a talisman has no rarity
        self.assertTrue(all("power" not in line for line in presets.describe(talismans, self.hero)))  # and no power

    def test_talismans_are_only_added_when_their_effect_is_known(self):
        # The Sigil of Beeswax's effect has been seen in a real save. Fist of Iron's ID has, but not what it saves.
        careful = presets.plan(by_title("Best talismans"), self.hero, self.catalog, power=30, rarity="Unique")
        self.assertEqual([a.kit.name for a in careful.add], ["Sigil of Beeswax"])
        self.assertEqual(sorted(kit.name for kit, _found in careful.unconfirmed), ["Fist of Iron", "Ocelot's Paw"])
        presets.apply(careful, self.hero, self.catalog)
        sigil = next(item for item in self.hero.items() if item.tag == "SW.Item.Talisman.HealthBoost")
        self.assertEqual((sigil.rarity, sigil.power, len(sigil.data["Effects"]), len(sigil.data["ItemProgression"]["ItemLevels"])), ("None", -1, 1, 3))
        again = presets.plan(by_title("Best talismans"), self.hero, self.catalog, power=30, rarity="Unique")
        self.assertEqual([owned.kit.name for owned in again.have], ["Sigil of Beeswax"])  # the one it has counts, whatever power was picked
        bold = presets.plan(by_title("Best talismans"), self.hero, self.catalog, power=30, include_unconfirmed=True, rarity="Unique")
        notes = {a.kit.name: presets.describe(bold, self.hero)[n].rsplit("(", 1)[-1] for n, a in enumerate(bold.add)}
        self.assertEqual(notes["Fist of Iron"], "unconfirmed: without its effect)")

    def test_a_talisman_an_older_version_added_without_its_effect_isnt_good_enough(self):
        # Before 1.7.1 the editor added talismans as Common items with a power and no effect.
        self.document["CharacterSaveV1"]["Inventory"]["Entries"].append(hero_item("SW.Item.Talisman.HealthBoost", power=5, seed=41))
        plan = presets.plan(by_title("Best talismans"), self.hero, self.catalog, power=30, rarity="Unique")
        self.assertEqual(([a.kit.name for a in plan.add], plan.have), (["Sigil of Beeswax"], []))

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
        body["Inventory"]["Entries"].append(hero_item("SW.Item.CurvedLongsword_Unique1", power=80, rarity="Unique", seed=21))
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
