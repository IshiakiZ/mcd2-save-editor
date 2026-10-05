"""Checks on the real item list (dungeons2_editor/data/items.json), which tools/build_item_catalog.py makes.

The other tests use a pinned copy, so these are the ones that notice a list that came out wrong.
"""

import unittest

from dungeons2_editor import hero as heroes
from dungeons2_editor import presets
from dungeons2_editor.hero import Hero, build_catalog

from . import PINNED_EFFECTS_FILE, PINNED_ITEMS_FILE, REAL_EFFECTS_FILE, REAL_ITEMS_FILE, use_effect_list, use_item_list
from .helpers import hero_save, talisman_item


class RealItemListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_item_list(REAL_ITEMS_FILE)
        cls.addClassCleanup(use_item_list, PINNED_ITEMS_FILE)
        use_effect_list(REAL_EFFECTS_FILE)
        cls.addClassCleanup(use_effect_list, PINNED_EFFECTS_FILE)
        cls.items = heroes.game_items()

    def test_every_id_is_an_item_id_used_once(self):
        ids = [item.id for item in self.items] + [item.unique_id for item in self.items if item.unique_id]
        self.assertGreater(len(self.items), 180)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(heroes._ITEM_TAG.fullmatch(tag) for tag in ids))
        self.assertFalse([item for item in self.items if heroes.item_group(item.id) in heroes.NOT_ADDABLE_GROUPS])
        self.assertEqual({item.kind for item in self.items}, {"Melee", "Ranged", "Armor", "Artifact", "Talisman", heroes.BOOK_KIND})

    def test_ids_checked_in_the_game_are_confirmed(self):
        confirmed = {item.id for item in self.items if item.confirmed}
        self.assertTrue({"SW.Item.Sword", "SW.Item.MysticHelmet", "SW.Item.HeavyCrossbow", "SW.Item.Artifact.FireworkQuiver"} <= confirmed)
        self.assertEqual(heroes.unique_tag("SW.Item.Sword"), "SW.Item.Sword_Unique1")  # the developer made one and the game kept it
        self.assertEqual(heroes.display_name("SW.Item.Sword_Unique1"), "The Burning Blade")

    def test_ids_players_reported_replace_the_guesses(self):
        ids = {item.name: (item.id, item.confirmed) for item in self.items}
        # Reported from real saves (issue 9): neither is the in-game name with the spaces taken out.
        self.assertEqual(ids["Death Cap Mushroom"], ("SW.Item.Artifact.DeathcapMushroom", True))
        self.assertEqual(ids["Conductive Quiver"], ("SW.Item.Artifact.LightningQuiver", True))
        self.assertEqual(heroes.unique_tag("SW.Item.HeavyCrossbow"), "SW.Item.HeavyCrossbow_Unique1")
        self.assertEqual(heroes.display_name("SW.Item.StalwartChest_Unique"), "Humbler Carapace")
        self.assertEqual(heroes.display_name("SW.Item.EnchantmentBook.FireAspect"), "Fire Aspect")

    def test_names_matched_to_ids_by_what_the_items_do(self):
        ids = {item.name: item for item in self.items}
        # Three artifacts whose save ID isn't their name: by a player's word, by the other bangles, and by elimination.
        self.assertEqual([ids[name].id for name in ("Picnic Basket", "Blizzard Bangle", "Tempo Truffle")],
                         ["SW.Item.Artifact.PicnicBlanket", "SW.Item.Artifact.FrostBracelet", "SW.Item.Artifact.HasteMushroom"])
        self.assertEqual((ids["Mob Mallet"].id, ids["Mob Mallet"].confirmed), ("SW.Item.GiantMallet", True))
        self.assertFalse([item.name for item in self.items if item.name_from_id])
        # A talisman is saved by what it does, and its effect can go by another name than its level templates.
        fist = ids["Fist of Iron"]
        self.assertEqual((fist.id, [(level["effect"], level["intensity"], level["template"]) for level in fist.levels]),
                         ("SW.Item.Talisman.Brawling", [("SW.Effect.Sharpness", 0.1, "SW.EffectTemplate.Brawling.I"),
                                                        ("SW.Effect.Sharpness", 0.2, "SW.EffectTemplate.Brawling.II"),
                                                        ("SW.Effect.Sharpness", 0.35, "SW.EffectTemplate.Brawling.III")]))
        # Each of these was matched to its name by the number in MetaBot's description of what it does at level 3.
        for name, tag, strength, words in (
            ("Armadillo Amulet", "RollingCooldown", 0.45, "by 45%"),
            ("Essence of Efficiency", "ArtifactCooldown", -0.14, "by 14%"),
            ("Looter's Charm", "DropChance", 0.04, "4%"),
            ("The Eye of Experience", "ExperienceIncrease", 1.1, "by 10%"),
            ("Thrifty Pendant", "FiringEmeralds", 2, "200%"),
            ("Soul Chip", "SoulCapacity", 1.35, "by 35%"),
        ):
            item = ids[name]
            self.assertEqual((item.id, item.confirmed, item.levels[2]["intensity"]), (f"SW.Item.Talisman.{tag}", True, strength), name)
            self.assertIn(words, item.effect, name)
        # Seen in saves with three levels and no effect at any of them: how to add one isn't known yet.
        golem = ids["Golem Kit"]
        self.assertEqual((golem.id, golem.confirmed, golem.levels), ("SW.Item.Talisman.IronGolem", True, ()))
        self.assertGreaterEqual(sum(bool(item.levels) for item in self.items), 16)

    def test_every_unique_seen_follows_the_pattern_the_guesses_use(self):
        # CatalogItem.tag_at guesses an unseen Unique's ID this way, so a Unique that breaks it should be noticed.
        seen = [item for item in self.items if item.unique_id]
        self.assertGreaterEqual(len(seen), 12)
        for item in seen:
            self.assertTrue(item.unique, item.id)
            self.assertEqual(item.unique_id, item.id + ("_Unique" if item.kind == "Armor" else "_Unique1"), item.name)
            self.assertTrue(item.confirmed, f"{item.name}: its Unique has been seen, so the item itself should be confirmed")

    def test_only_weapons_and_armor_have_uniques(self):
        self.assertEqual({item.kind for item in self.items if item.unique}, {"Melee", "Ranged", "Armor"})
        self.assertEqual(len([item for item in self.items if item.unique]), 116)

    def test_armor_ids_are_a_set_name_and_a_slot(self):
        for item in self.items:
            if item.kind == "Armor":
                self.assertEqual(heroes.armor_piece(item.id), item.slot, item.id)
                self.assertRegex(item.id, r"^SW\.Item\.[A-Za-z]+(Helmet|Chest|Leggings|Boots)$")

    def test_the_effects_list_holds_what_saves_have_shown(self):
        book = heroes.effect_book()
        self.assertEqual((book.max_effects, book.talisman_xp), (4, (18480, 73920)))
        self.assertEqual(book.enchant_points["Unique"], [3, 8, 15])  # tiers I and II have been seen in a save
        self.assertEqual(set(book.enchant_points), set(heroes.RARITIES))
        self.assertGreaterEqual(len({choice.effect for choice in book.effects}), 18)
        by_effect: dict = {}
        for choice in book.effects:
            by_effect.setdefault((choice.effect, choice.template.rsplit(".", 1)[0]), []).append(choice)
            self.assertRegex(choice.effect, r"^SW\.Effect\.[A-Za-z]+$")
            self.assertRegex(choice.template, r"^SW\.EffectTemplate\.[A-Za-z]+\.(I|II|III)$")
            self.assertEqual(choice.template.rsplit(".", 1)[1], choice.tier)
            self.assertFalse(choice.is_enchantment or choice.yours)
            if not choice.seen:  # only where the game files' table gives the number, for an effect it names
                self.assertTrue(choice.shown.endswith("%") and not choice.maybe, choice.title)
                self.assertIn(choice.shown.rstrip("%"), choice.what, choice.title)  # and the game's wording agrees
        for tiers in by_effect.values():
            self.assertTrue(any(choice.seen for choice in tiers), tiers[0].name)  # nothing is listed on the table's word alone
            self.assertEqual(len({choice.tier for choice in tiers}), len(tiers), tiers[0].name)
        # Checked against the developer's own save: what the game wrote for these tiers.
        saved = {(choice.title, choice.strength, choice.effect.rsplit(".", 1)[1], choice.template.split(".")[2]) for choice in book.effects if choice.seen}
        self.assertTrue({
            ("Critical Edge II", 0.2, "CriticalEdge", "CriticalEdge"),
            ("Cooldown II", -0.15, "Cooldown", "Cooldown"),
            ("Acrobat I", 0.1, "RollCooldown", "Acrobat"),  # the effect and its template don't share a name
            ("Spiritual I", 1.25, "SoulMax", "BagOfSouls"),
            ("Looter I", 0.2, "Looting", "Looting"),
        } <= saved)
        names = heroes.enchantments()
        for choice in book.enchantments:
            self.assertTrue(choice.seen and choice.is_enchantment, choice.title)  # an enchantment's number can't be worked out
            self.assertEqual(choice.template, f"{choice.effect}.{choice.tier}")
            self.assertIn(choice.name, names)
            self.assertEqual(choice.slots, names[choice.name].slots)
        self.assertEqual({(choice.title, choice.strength) for choice in book.enchantments},
                         {("Ancient Alchemy I", 0.5), ("Ancient Alchemy II", 0.6), ("Healing Smite I", 0.3), ("Piercing I", 1)} | {
                             (choice.title, choice.strength) for choice in book.enchantments
                         })
        self.assertEqual(heroes.display_name("SW.Item.EnchantmentBook.Radiance"), "Healing Smite")  # the book the save calls Radiance
        # MetaBot's table says Critical Edge III is 30% and the game's wording for it says 40%: left out until a save shows it.
        self.assertEqual([choice.tier for choice in book.effects if choice.name == "Critical Edge"], ["I", "II"])
        self.assertEqual(next(choice for choice in book.effects if choice.title == "Acrobat I").what, "Reduces rolling cooldown time by 10%.")
        self.assertTrue(all(enchantment.levels and enchantment.what for enchantment in names.values()))

    def test_the_kits_name_effects_and_enchantments_the_lists_know(self):
        book = heroes.effect_book()
        effects = {choice.name for choice in book.effects}
        enchantments = heroes.enchantments()
        for preset in presets.PRESETS:
            for kit_item in preset.items:
                self.assertTrue(set(kit_item.effects) <= effects, f"{preset.title}: {kit_item.name}: {kit_item.effects}")
                self.assertTrue(set(kit_item.enchants) <= set(enchantments), f"{preset.title}: {kit_item.name}: {kit_item.enchants}")
        # With the Enchantsmith unlocked, a kit puts on what the editor can write so far: Piercing on the Greatbow.
        save = hero_save()
        save["CharacterSaveV1"]["CollectionsStats"]["ShownHints"] = [{"Tag": "SW.UI.Onboarding.Panel.Enchantsmith.Overview", "Count": 1}]
        hero = Hero(save)
        kit = next(preset for preset in presets.PRESETS if preset.title == "Greatbow sharpshooter")
        plan = presets.plan(kit, hero, build_catalog([hero]), power=30, rarity="Unique")
        made = {addition.name: (addition.enchantment.title if addition.enchantment else None, [choice.title for choice in addition.effects]) for addition in plan.add}
        self.assertEqual(made["Humbler Heartstring"], ("Piercing I", ["Marksman I"]))
        self.assertEqual(made["Hunter's Hatchet"], (None, ["Critical Edge II"]))
        self.assertEqual(made["Sharpshooter Fedora"], (None, ["Projectile Protection I"]))  # Ender Quiver hasn't been seen saved yet
        self.assertEqual(made["Flaming Quiver"], (None, ["Cooldown II", "Spiritual I"]))  # an artifact tops out at Special: two effects

    def test_a_companions_talisman_is_added_the_way_the_game_saves_one(self):
        # What the game saved for a Tasty Bone it handed over (the developer's own save, 2026-10-05).
        game = {
            "Effects": [],
            "ItemProgression": {"CurrentLevel": 0, "CurrentXP": 0, "ItemLevels": [
                {"LevelEffects": [], "LevelTags": ["SW.Talisman.Wolf.Level.1"]},
                {"LevelEffects": [], "LevelTags": ["SW.Talisman.Wolf.Level.2"]},
                {"LevelEffects": [], "LevelTags": ["SW.Talisman.Wolf.Level.3"]},
            ]},
        }
        save = hero_save()
        save["CharacterSaveV1"]["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", seed=61))
        hero = Hero(save)
        entry = next(entry for entry in build_catalog([hero]) if entry.tag == "SW.Item.Talisman.Wolf")
        self.assertEqual((entry.name, entry.confirmed_at(), entry.no_effect), ("Tasty Bone", True, False))
        bone = hero.item(hero.add_item(entry.tag, entry.template))
        self.assertEqual({key: bone.data[key] for key in game}, game)
        self.assertEqual((bone.rarity, bone.power, bone.effect_lines()), ("None", -1, ["Level 1 of 3 (0 of 18,480 XP)."]))

    def test_a_talismans_levels_are_its_effect_as_a_save_holds_it(self):
        sigil = heroes.game_item("SW.Item.Talisman.HealthBoost")  # seen in the developer's own save
        self.assertEqual((sigil.name, sigil.confirmed), ("Sigil of Beeswax", True))
        self.assertEqual(
            [(level["effect"], level["intensity"], level["template"]) for level in sigil.levels],
            [
                ("SW.Effect.HealthBoost", 1.2, "SW.EffectTemplate.HealthBoost.I"),
                ("SW.Effect.HealthBoost", 1.25, "SW.EffectTemplate.HealthBoost.II"),
                ("SW.Effect.HealthBoost", 1.35, "SW.EffectTemplate.HealthBoost.III"),
            ],
        )
        for item in self.items:
            if not item.levels:
                continue
            self.assertEqual((item.kind, item.confirmed, len(item.levels)), ("Talisman", True, 3), item.name)
            for level in item.levels:
                if "tags" in level:  # a companion's talisman: a tag at each level, and no effect of its own
                    self.assertTrue(all(tag.startswith("SW.Talisman.") for tag in level["tags"]) and "effect" not in level, item.name)
                    continue
                self.assertTrue(level["effect"].startswith("SW.Effect.") and level["template"].startswith("SW.EffectTemplate."), item.name)
                self.assertIsInstance(level["intensity"], (int, float))
        catalog = {entry.tag: entry for entry in build_catalog([Hero(hero_save())])}
        self.assertTrue(catalog["SW.Item.Talisman.HealthBoost"].confirmed_at())
        self.assertTrue(all(entry.no_effect == (not heroes.game_item(entry.tag).levels) for entry in catalog.values() if entry.kind == "Talisman"))

    def test_books_are_named_after_enchantments(self):
        books = [item for item in self.items if item.kind == heroes.BOOK_KIND]
        self.assertTrue(books)
        for book in books:
            self.assertIn(book.name, heroes.enchantments(), book.id)
            self.assertTrue(book.id.startswith("SW.Item.EnchantmentBook.") and book.confirmed, book.id)

    def test_every_preset_item_is_in_the_list(self):
        catalog = build_catalog([Hero(hero_save())])
        for preset in presets.PRESETS:
            for kit_item in preset.items:
                found = presets.find_item(kit_item.name, catalog)
                self.assertIsNotNone(found, f"{preset.title}: {kit_item.name}")


if __name__ == "__main__":
    unittest.main()
