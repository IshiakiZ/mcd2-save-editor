import copy
import json
import unittest
import urllib.parse
from unittest import mock

from dungeons2_editor import share_ids
from dungeons2_editor.hero import Hero, effect_choices

from .helpers import enchanted, enchantment_effect, hero_item, hero_save, rolled, rolled_effect, talisman_item


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

    def test_a_talisman_the_short_form_cant_describe_is_shared_whole(self):
        save = hero_save()
        golem = talisman_item("SW.Item.Talisman.IronGolem", "Unused", seed=55, unseen=False)
        for level in golem["ItemData"]["ItemProgression"]["ItemLevels"]:
            level["LevelEffects"] = []  # a companion's talisman: three levels, and no effect at any of them
        golem["ItemData"]["Effects"] = [{"TypeTag": "SW.Item.Effect.Upgradable", "EffectsInThisBatch": []}]
        save["CharacterSaveV1"]["Inventory"]["Entries"].append(golem)
        ((tag, text),) = share_ids.talisman_effects([Hero(save)])
        self.assertEqual(tag, "SW.Item.Talisman.IronGolem")
        self.assertTrue(text.startswith("Iron Golem's effect: nothing / nothing / nothing; levels as saved: [{"), text)
        self.assertIn('"LevelTags":[]', text)
        self.assertTrue(text.endswith('; effects as saved: [{"TypeTag":"SW.Item.Effect.Upgradable","EffectsInThisBatch":[]}]'), text)

    def test_effects_the_editor_doesnt_know_are_shared_as_saved(self):
        def gear(tag, *batches, **more):
            entry = hero_item(tag, unseen=False, **more)
            entry["ItemData"]["Effects"] = list(batches)
            return entry

        own = {"TypeTag": "SW.Item.Effect.Fixed", "EffectsInThisBatch": [rolled_effect("Burning", 1, "Unique")]}  # what a Unique comes with
        save = hero_save()
        save["CharacterSaveV1"]["Inventory"]["Entries"] += [
            gear("SW.Item.Axe", rolled(rolled_effect("Thorns", 0.5)), seed=61),
            gear("SW.Item.Glaive", rolled(rolled_effect("Thorns", 0.5)), seed=62),  # nothing the Axe doesn't show
            gear("SW.Item.Mace", rolled(rolled_effect("Thorns", 0.7, "II"), rolled_effect("CriticalEdge", 0.1)),
                 enchanted(enchantment_effect("FireAspect", 0.9, "III", points=9)), rarity="Rare", seed=63),
            gear("SW.Item.Sword_Unique1", own, rarity="Unique", seed=64),
            gear("SW.Item.Bow_Unique1", own, rarity="Unique", seed=65),  # another Unique with the same effect still gets its line
            gear("SW.Item.Pike", seed=66),  # no effects
            gear("SW.Item.Claymore", rolled(rolled_effect("CriticalEdge", 0.2, "II"), rolled_effect("Vanguard", 0.2)),
                 enchanted(enchantment_effect("Radiance", 0.3)), rarity="Special", seed=67),  # all of it in the editor's list already
            gear("SW.Item.Shortbow", rolled(rolled_effect("Vanguard", 0.5, "III")), rarity="Rare", seed=68),  # a tier the list has only from the table
            gear("SW.Item.Talisman.HealthBoost", {"TypeTag": "SW.Item.Effect.Upgradable", "EffectsInThisBatch": [rolled_effect("HealthBoost", 1.2)]}, seed=69),
        ]
        unseen = gear("SW.Item.Scythe", rolled(rolled_effect("SoulBlast", 0.75)), seed=70)
        unseen["ItemData"]["DynamicPropertyTags"] = ["SW.Item.Property.Dynamic.Unseen"]  # the editor may have just made it
        save["CharacterSaveV1"]["Inventory"]["Entries"].append(unseen)
        hero = Hero(save)
        found = share_ids.gear_effects([hero])
        # Uniques first, then whatever shows the most that's new.
        self.assertEqual([tag for tag, _text in found], ["SW.Item.Bow_Unique1", "SW.Item.Sword_Unique1", "SW.Item.Mace", "SW.Item.Axe", "SW.Item.Shortbow"])
        mace = dict(found)["SW.Item.Mace"]
        self.assertTrue(mace.startswith('effects on a Rare one: [{"TypeTag":"SW.Item.Effect.Rerollable","EffectsInThisBatch":[{"TypeTag":"SW.Effect.Thorns","Intensity":0.7,'), mace)
        self.assertEqual(json.loads(mace.split(": ", 1)[1]), save["CharacterSaveV1"]["Inventory"]["Entries"][7]["ItemData"]["Effects"])  # exactly as saved
        report = share_ids.report_text([hero], "9.9.9").splitlines()
        self.assertTrue(all(line.startswith("SW.Item.") for line in report))
        self.assertIn("SW.Item.Axe - effects on a Common one: ", "\n".join(report))
        self.assertNotIn("SW.Item.Claymore", "\n".join(report))
        self.assertEqual(share_ids.finding_keys([hero]) - {tag for tag, _note in share_ids.unknown_ids([hero])}, {
            "SW.Effect.Thorns SW.EffectTemplate.Thorns.I",
            "SW.Effect.Thorns SW.EffectTemplate.Thorns.II",
            "SW.Enchantment.FireAspect SW.Enchantment.FireAspect.III",
            "SW.Effect.Vanguard SW.EffectTemplate.Vanguard.III",
            "SW.Effect.Burning SW.EffectTemplate.Burning.Unique",
            "SW.Item.Sword_Unique1 own effects",
            "SW.Item.Bow_Unique1 own effects",
        })
        # A long list of them stops at what fits in a GitHub issue.
        with mock.patch.object(share_ids, "MAX_GEAR_LINES", 2):
            self.assertEqual([tag for tag, _text in share_ids.gear_effects([hero])], ["SW.Item.Bow_Unique1", "SW.Item.Sword_Unique1"])
        # A Unique's own effect is news where the editor hasn't seen it on that very Unique. The rest of what a
        # Unique holds is news like anyone's: only if the editor's list doesn't have it.
        def static(effect, strength, template):
            entry = rolled_effect("Any", strength)
            entry["TypeTag"] = f"SW.{effect}"
            entry["GeneratorData"]["GeneratorParentTemplate"] = f"SW.{template}"
            return {"TypeTag": "SW.Item.Effect.Static", "EffectsInThisBatch": [entry]}

        blade = static("Effect.FireFocus", 0.2, "EffectTemplate.FireFocus.Unique")  # The Burning Blade's, as the list has it
        held = hero_save()
        held["CharacterSaveV1"]["Inventory"]["Entries"] += [
            gear("SW.Item.Sword_Unique1", blade, rolled(rolled_effect("CriticalEdge", 0.2, "II")), rarity="Unique", seed=71),  # nothing new
            gear("SW.Item.Mace_Unique1", enchanted(enchantment_effect("Radiance", 0.3)), rarity="Unique", seed=72),  # without its own: nothing to learn
            gear("SW.Item.Claymore", rolled(rolled_effect("CriticalEdge", 0.2, "II")), rarity="Rare", seed=73),
        ]
        self.assertEqual((share_ids.gear_effects([Hero(held)]), share_ids.finding_keys([Hero(held)]) - {tag for tag, _note in share_ids.unknown_ids([Hero(held)])}), ([], set()))
        held["CharacterSaveV1"]["Inventory"]["Entries"] += [
            # The Ranger's Promise: the editor has no effect of its own for it.
            gear("SW.Item.Bow_Unique1", static("Effect.Aim", 0.25, "EffectTemplate.Aim.Unique"), rarity="Unique", seed=74),
            gear("SW.Item.Bow_Unique1", static("Effect.Aim", 0.25, "EffectTemplate.Aim.Unique"), rarity="Unique", seed=75),  # once is enough
            # The Slaymore: the editor has its effect from the Humbler Greaves, which do the same, and writes it on a
            # Slaymore it makes. So finding exactly that on one proves nothing: it may be the editor's own work.
            gear("SW.Item.Claymore_Unique1", static("Effect.SweepingEdge", 0.5, "EffectTemplate.SweepingEdge.Unique"), rarity="Unique", seed=76),
            # A Burning Blade saved another way than the editor would save it: that can only be the game's.
            gear("SW.Item.Sword_Unique1", static("Effect.FireFocus", 0.3, "EffectTemplate.FireFocus.Unique"), rarity="Unique", seed=77),
        ]
        plain = Hero(held)
        listed = share_ids.gear_effects([plain])
        self.assertEqual([tag for tag, _text in listed], ["SW.Item.Bow_Unique1", "SW.Item.Sword_Unique1"])
        self.assertTrue(listed[0][1].startswith('effects on a Unique one: [{"TypeTag":"SW.Item.Effect.Static","EffectsInThisBatch":[{"TypeTag":"SW.Effect.Aim","Intensity":0.25,'), listed[0][1])
        self.assertIn('"Intensity":0.3,', listed[1][1])
        self.assertEqual(share_ids.finding_keys([plain]) - {tag for tag, _note in share_ids.unknown_ids([plain])}, {
            "SW.Effect.Aim SW.EffectTemplate.Aim.Unique", "SW.Item.Bow_Unique1 own effects", "SW.Item.Sword_Unique1 own effects",
        })
        # An effect that's locked is saved a way the editor never writes, so it's news, on a Unique or not.
        locked = rolled_effect("CriticalEdge", 0.2, "II")
        locked["GeneratorData"]["Locked"] = True
        held["CharacterSaveV1"]["Inventory"]["Entries"] += [gear("SW.Item.Pike", rolled(locked), rarity="Rare", seed=78)]
        plain = Hero(held)
        self.assertEqual([tag for tag, _text in share_ids.gear_effects([plain])][-1], "SW.Item.Pike")
        self.assertIn("SW.Item.Pike own effects", share_ids.finding_keys([plain]))
        # Effects the editor put on an item aren't the game's word until the game has shown you the item.
        fresh = Hero(hero_save())
        index = next(item.index for item in fresh.items() if item.tag == "SW.Item.Sword")
        fresh.item(index).data["Effects"] = [rolled(rolled_effect("Thorns", 0.5))]
        self.assertEqual(len(share_ids.gear_effects([fresh])), 1)
        edge = next(choice for choice in effect_choices([])[0] if choice.title == "Vanguard III")
        fresh.set_effects(index, [edge])
        self.assertEqual((share_ids.gear_effects([fresh]), share_ids.finding_keys([fresh])), ([], set()))

    def test_an_item_the_game_marks_some_way_the_editor_hasnt_seen_is_shared_whole(self):
        # However the game tags a Soul Storm piece, say: no save sent so far holds one, so the list has to show it.
        save = hero_save()
        plain = Hero(copy.deepcopy(save))
        self.assertEqual(share_ids.marked_items([plain]), [])  # every item here is saved the way the editor knows
        self.assertFalse([key for key in share_ids.finding_keys([plain]) if key.startswith(("mark ", "field "))])

        marked = hero_item("SW.Item.Longbow", rarity="Special", seed=41, unseen=False)
        marked["ItemData"]["DynamicPropertyTags"] = ["SW.Item.Property.Dynamic.SoulStorm"]
        twin = hero_item("SW.Item.Sword", seed=42)  # the same mark again, on an item the game hasn't shown you yet
        twin["ItemData"]["DynamicPropertyTags"].append("SW.Item.Property.Dynamic.SoulStorm")
        odd = hero_item("SW.Item.Axe", seed=43, unseen=False)  # fields no entry the editor has seen was saved with
        odd["SoulStormGear"] = True
        odd["ItemData"]["GeneratorData"]["PowerGeneratorValues"]["StormTier"] = "SW.SoulStorm.Tier.Hard"
        odd["ItemData"]["Owner"] = "Somebody's name, typed in"
        cape = hero_item("SW.Item.Cosmetic.Cape.Other", seed=44, unseen=False)
        cape["ItemData"]["DynamicPropertyTags"] = ["SW.Item.Property.Dynamic.Worn"]
        save["CharacterSaveV1"]["Inventory"]["Entries"] += [marked, twin, odd, cape]
        hero = Hero(save)
        lines = share_ids.marked_items([hero])
        # One line for each new thing, on the first item that shows it. Cosmetics are left out, as everywhere.
        self.assertEqual([tag for tag, _text in lines], ["SW.Item.Longbow", "SW.Item.Axe"])

        first = lines[0][1]
        self.assertTrue(first.startswith("a Special one saved with something new to the editor (mark SW.Item.Property.Dynamic.SoulStorm), as saved: {"))
        self.assertTrue(first.endswith("; what does the game show on this item that it doesn't on others?"))
        whole = copy.deepcopy(marked)
        del whole["ItemData"]["PickupTimestamp"], whole["ItemData"]["GeneratorData"]["GenesisRandomSeed"]
        self.assertEqual(json.loads(first.split("as saved: ", 1)[1].rsplit(";", 1)[0]), whole)  # the whole item, less its pickup time and seed

        second = lines[1][1]
        self.assertIn("(field ItemData.GeneratorData.PowerGeneratorValues.StormTier, field ItemData.Owner, field SoulStormGear)", second)
        saved = json.loads(second.split("as saved: ", 1)[1].rsplit(";", 1)[0])
        # A yes or no and one of the game's own names are passed on; other text in a field the editor doesn't know isn't.
        self.assertEqual((saved["SoulStormGear"], saved["ItemData"]["GeneratorData"]["PowerGeneratorValues"]["StormTier"], saved["ItemData"]["Owner"]),
                         (True, "SW.SoulStorm.Tier.Hard", "(text)"))
        report = share_ids.report_text([hero], "9.9.9")
        self.assertNotIn("Somebody", report)
        self.assertTrue(all(line.startswith("SW.Item.") for line in report.splitlines()))
        self.assertEqual(report.count("SW.Item.Property.Dynamic.Worn"), 0)
        # Each of them counts as news, so the Share item IDs button shows up for it.
        self.assertTrue({
            "mark SW.Item.Property.Dynamic.SoulStorm", "field SoulStormGear", "field ItemData.Owner",
            "field ItemData.GeneratorData.PowerGeneratorValues.StormTier",
        } <= share_ids.finding_keys([hero]))

    def test_marked_items_stop_at_a_few_lines(self):
        save = hero_save()
        for number in range(share_ids.MAX_MARK_LINES + 3):
            entry = hero_item("SW.Item.Sword", seed=60 + number, unseen=False)
            entry["ItemData"]["DynamicPropertyTags"] = [f"SW.Item.Property.Dynamic.Mark{number}"]
            save["CharacterSaveV1"]["Inventory"]["Entries"].append(entry)
        hero = Hero(save)
        self.assertEqual(len(share_ids.marked_items([hero])), share_ids.MAX_MARK_LINES)
        self.assertEqual(len([key for key in share_ids.finding_keys([hero]) if key.startswith("mark ")]), share_ids.MAX_MARK_LINES + 3)

    def test_the_fields_the_editor_knows_are_the_ones_a_real_entry_has(self):
        # The list of known fields is what real saves hold, entry for entry; a talisman's levels and an
        # enchanted Unique's effects are part of it.
        save = hero_save()
        sword = hero_item("SW.Item.Sword_Unique1", rarity="Unique", seed=52, unseen=False)
        sword["ItemData"]["Effects"] = [rolled(rolled_effect("Sharpness", 0.1, "I")), enchanted(enchantment_effect("Piercing", 1, "I", 3))]
        save["CharacterSaveV1"]["Inventory"]["Entries"] += [talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", seed=51), sword]
        hero = Hero(save)
        self.assertEqual([share_ids._unknown_fields(item.entry) for item in hero.items() if share_ids._unknown_fields(item.entry)], [])
        entry = hero_item("SW.Item.Sword")
        self.assertEqual(set(entry), share_ids.KNOWN_FIELDS[""])
        self.assertEqual(set(entry["ItemData"]), share_ids.KNOWN_FIELDS["ItemData"])
        self.assertEqual(set(entry["ItemData"]["GeneratorData"]["PowerGeneratorValues"]), share_ids.KNOWN_FIELDS["ItemData.GeneratorData.PowerGeneratorValues"])

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
