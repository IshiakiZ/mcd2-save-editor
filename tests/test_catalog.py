"""Checks on the real item list (dungeons2_editor/data/items.json), which tools/build_item_catalog.py makes.

The other tests use a pinned copy, so these are the ones that notice a list that came out wrong.
"""

import unittest

from dungeons2_editor import hero as heroes
from dungeons2_editor import presets
from dungeons2_editor.hero import Hero, build_catalog

from . import PINNED_ITEMS_FILE, REAL_ITEMS_FILE, use_item_list
from .helpers import hero_save


class RealItemListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_item_list(REAL_ITEMS_FILE)
        cls.addClassCleanup(use_item_list, PINNED_ITEMS_FILE)
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
