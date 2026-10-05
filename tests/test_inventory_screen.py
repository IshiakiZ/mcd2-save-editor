import unittest

from dungeons2_editor.hero import GEAR_SLOTS, Hero, game_item, gear_power
from dungeons2_editor.inventory_screen import describe, fit_lines, slot_noun

from .helpers import hero_item, hero_save, rolled, rolled_effect

SLOT = {slot.label: slot.tag for slot in GEAR_SLOTS}


def hero_wearing(*worn):
    """A hero wearing (slot label, item ID, power) for each of ``worn``."""
    save = hero_save()
    save["CharacterSaveV1"]["Inventory"]["Entries"] = [
        hero_item(tag, power=power, equipped=SLOT[label], seed=100 + number) for number, (label, tag, power) in enumerate(worn)
    ] + [hero_item("SW.Item.Claymore", power=500, seed=99)]  # in the inventory: doesn't count
    return Hero(save)


class GearPowerTests(unittest.TestCase):
    def test_matches_the_games_inventory_screen(self):
        # The game's own screen: weapons 45 and 44, armor 157 in all, artifacts 108 in all, gear power 39.
        hero = hero_wearing(
            ("Melee weapon", "SW.Item.Sword", 45),
            ("Ranged weapon", "SW.Item.Bow", 44),
            ("Helmet", "SW.Item.MysticHelmet", 38),
            ("Chestplate", "SW.Item.MysticChest", 40),
            ("Leggings", "SW.Item.HoneyLeggings", 38),
            ("Boots", "SW.Item.HoneyBoots", 41),
            ("Artifact 1", "SW.Item.Artifact.FireworkQuiver", 42),
            ("Artifact 2", "SW.Item.Artifact.RallyingHorn", 30),
            ("Artifact 3", "SW.Item.Artifact.Grindstone", 36),
            ("Talisman 1", "SW.Item.Talisman.LuckyClover", 300),  # talismans don't count
        )
        self.assertEqual(gear_power(hero, list(GEAR_SLOTS)), (39, {"Melee": 45, "Ranged": 44, "Armor": 157, "Artifact": 108}))

    def test_averages_only_what_is_worn_rounding_down(self):
        # A real hero wearing gear at power 10, 1, 2 and 2 was saved by the game with power level 3.
        hero = hero_wearing(
            ("Melee weapon", "SW.Item.Sword", 10),
            ("Ranged weapon", "SW.Item.Bow", 1),
            ("Boots", "SW.Item.MysticBoots", 2),
            ("Artifact 1", "SW.Item.Artifact.RallyingHorn", 2),
        )
        self.assertEqual(gear_power(hero, list(GEAR_SLOTS))[0], 3)

    def test_nothing_worn(self):
        self.assertEqual(gear_power(hero_wearing(), list(GEAR_SLOTS)), (None, {"Melee": 0, "Ranged": 0, "Armor": 0, "Artifact": 0}))


class CardTextTests(unittest.TestCase):
    def item(self, tag, rarity):
        save = hero_save()
        save["CharacterSaveV1"]["Inventory"]["Entries"] = [hero_item(tag, rarity=rarity)]
        return Hero(save).item(0)

    def test_says_what_the_item_does(self):
        unique = self.item("SW.Item.MysticHelmet_Unique", "Unique")  # the Oracle Crown has an ID of its own
        # Made by the editor, it holds no effects, so it's without the Crown's own: the card says what that does in the game.
        self.assertEqual(describe(unique, game_item(unique.tag)), "In the game: Lightning attacks deal 25% more damage.")
        unique.data["Effects"] = [rolled(rolled_effect("CriticalEdge", 0.2, "II"))]  # could be the editor's doing or the game's
        self.assertEqual(describe(unique, game_item(unique.tag)), "In the game: Lightning attacks deal 25% more damage.")
        unique.data["Effects"] = [{"TypeTag": "SW.Item.Effect.Fixed", "EffectsInThisBatch": [rolled_effect("Burning", 1, "Unique")]}]
        self.assertEqual(describe(unique, game_item(unique.tag)), "Lightning attacks deal 25% more damage.")  # saved a way the editor doesn't write
        for rarity in ("Common", "Unique"):  # the Mystic Circlet stays a Mystic Circlet, whatever its rarity
            base = self.item("SW.Item.MysticHelmet", rarity)
            self.assertEqual(describe(base, game_item(base.tag)), "Its Unique is the Oracle Crown. Lightning attacks deal 25% more damage.")
        talisman = self.item("SW.Item.Talisman.LuckyClover", "Common")
        self.assertTrue(describe(talisman, game_item(talisman.tag)).startswith("At level 3: "))
        unknown = self.item("SW.Item.SomethingNew", "Rare")
        self.assertEqual(describe(unknown, game_item(unknown.tag)), "")

    def test_slot_nouns(self):
        nouns = {slot.label: slot_noun(slot) for slot in GEAR_SLOTS}
        self.assertEqual((nouns["Melee weapon"], nouns["Chestplate"], nouns["Artifact 2"]), ("melee weapon", "chestplate", "artifact"))


class FitLinesTests(unittest.TestCase):
    class Font:
        @staticmethod
        def measure(text):
            return 7 * len(text)

    def test_wraps_and_cuts_names_to_fit_under_a_tile(self):
        font = self.Font()
        self.assertEqual(fit_lines("Bow", font, 70), "Bow")
        self.assertEqual(fit_lines("The Close Ranger", font, 70), "The Close\nRanger")
        self.assertEqual(fit_lines("Twisted Warden Blindfold of Doom", font, 70), "Twisted\nWarden…")
        self.assertEqual(fit_lines("Cacaphonous Cleaver", font, 56), "Cacapho…\nCleaver")


if __name__ == "__main__":
    unittest.main()
