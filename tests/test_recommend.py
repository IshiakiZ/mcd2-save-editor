"""The editor's picks of effects for a goal (recommend.py)."""

import unittest

from dungeons2_editor import presets, recommend
from dungeons2_editor.hero import EffectChoice


def effect(name, pools, seen=("I", "II", "III")):
    """A made-up gear effect at tiers I to III, rolled from ``pools``, with the tiers a save has shown."""
    short = name.replace(" ", "")
    return [
        EffectChoice(f"SW.Effect.{short}", f"SW.EffectTemplate.{short}.{tier}", 0.1, name, tier, seen=tier in seen, rolls_on=pools)
        for tier in ("I", "II", "III")
    ]


class PickTests(unittest.TestCase):
    def picks(self, goal, kind, tags, choices, **more):
        return [choice.title for choice in recommend.candidates(recommend.goal(goal), kind, tags, choices, **more)]

    def test_a_pick_is_an_effect_the_game_rolls_on_that_item(self):
        gear = effect("Sharpness", "Any weapon") + effect("Duelist", "Fighter gear") + effect("Sorcerer", "Any artifact, Mage gear") + effect("Looter", "All gear")
        self.assertEqual(self.picks("Damage", "Melee", ("Fighter",), gear), ["Sharpness III", "Duelist III"])
        self.assertEqual(self.picks("Damage", "Melee", ("Tank",), gear), ["Sharpness III"])  # Duelist rolls on Fighter gear only
        self.assertEqual(self.picks("Damage", "Armor", ("Fighter", "Tank"), gear), ["Duelist III"])  # Sharpness rolls on weapons
        self.assertEqual(self.picks("Damage", "Artifact", (), gear), ["Sorcerer III"])
        self.assertEqual(self.picks("Damage", "Armor", ("Mage",), gear), ["Sorcerer III"])
        self.assertEqual(self.picks("Damage", "Armor", ("Summoner",), gear), [])
        self.assertEqual(self.picks("Loot", "Armor", (), gear), ["Looter III"])  # all gear rolls it
        self.assertEqual(self.picks("Mobility", "Melee", ("Fighter",), gear), [])
        # One found only on an item in your saves isn't in any pool the editor knows, and an enchantment isn't an effect.
        yours = [EffectChoice("SW.Effect.Sharpness", "SW.EffectTemplate.Sharpness.III", 0.3, "Sharpness", "III", yours=True)]
        enchantment = [EffectChoice("SW.Enchantment.Sharpness", "SW.Enchantment.Sharpness.III", 1, "Sharpness", "III", rolls_on="Any weapon")]
        self.assertEqual(self.picks("Damage", "Melee", (), yours + enchantment), [])

    def test_a_weapon_gets_the_other_kind_of_weapons_effects_last(self):
        gear = effect("Sharpness", "Any weapon") + effect("Impact", "Any weapon") + effect("Critical Hit", "Any weapon")
        self.assertEqual(self.picks("Damage", "Melee", (), gear), ["Sharpness III", "Critical Hit III", "Impact III"])
        self.assertEqual(self.picks("Damage", "Ranged", (), gear), ["Impact III", "Critical Hit III", "Sharpness III"])
        # An artifact gets what speaks of artifacts first; armor takes the order as it stands.
        gear = effect("Duelist", "Fighter gear") + effect("Sorcerer", "Any artifact, Mage gear") + effect("Cooldown", "Any artifact, Mage gear")
        self.assertEqual(self.picks("Damage", "Artifact", ("Fighter",), gear), ["Sorcerer III", "Duelist III"])
        self.assertEqual(self.picks("Damage", "Armor", ("Fighter", "Mage"), gear), ["Duelist III", "Sorcerer III"])
        self.assertEqual(self.picks("Artifacts and souls", "Artifact", (), gear), ["Cooldown III", "Sorcerer III"])  # only damage is sorted so

    def test_each_pick_is_at_the_best_tier_a_save_has_shown(self):
        gear = effect("Sharpness", "Any weapon", seen=("I", "II")) + effect("Impact", "Any weapon", seen=())
        self.assertEqual(self.picks("Damage", "Ranged", (), gear), ["Impact III", "Sharpness II"])  # no tier of Impact seen: the best there is

    def test_an_elements_effect_needs_that_element_in_play(self):
        gear = effect("Sorcerer", "Any artifact, Mage gear") + effect("Pyromancer", "Any artifact, Mage gear") + effect("Cryomancer", "Any artifact, Mage gear")
        self.assertEqual(self.picks("Damage", "Armor", ("Mage",), gear), ["Sorcerer III"])
        self.assertEqual(self.picks("Damage", "Armor", ("Mage",), gear, elements={"Fire"}), ["Sorcerer III", "Pyromancer III"])
        self.assertEqual(self.picks("Damage", "Artifact", (), gear, elements={"Frost", "Fire", "Wind"}), ["Sorcerer III", "Pyromancer III", "Cryomancer III"])

    def test_what_the_item_comes_with_is_left_out(self):
        gear = effect("Sharpness", "Any weapon") + effect("Duelist", "Fighter gear") + effect("Swiftness", "Fighter gear")
        self.assertEqual(self.picks("Damage", "Melee", ("Fighter",), gear), ["Sharpness III", "Duelist III", "Swiftness III"])
        # The Pride of the Plains comes with Duelist: the place goes to the next pick.
        self.assertEqual(self.picks("Damage", "Melee", ("Fighter",), gear, own={"SW.Effect.Duelist"}), ["Sharpness III", "Swiftness III"])
        self.assertEqual(
            [choice.title for choice in recommend.best(recommend.goal("Damage"), "Melee", ("Fighter",), gear, 1, own={"SW.Effect.Sharpness"})],
            ["Duelist III"],
        )

    def test_the_picks_go_first_and_what_was_there_stays_while_it_fits(self):
        sharpness, impact, looter, luck = (effect(name, "All gear") for name in ("Sharpness", "Impact", "Looter", "Luck"))
        had = [looter[0], sharpness[0], luck[1]]
        # Sharpness I gives way to the pick of the same effect; the others keep their order behind the picks.
        self.assertEqual(recommend.keep([sharpness[2], impact[2]], had, 4), [sharpness[2], impact[2], looter[0], luck[1]])
        self.assertEqual(recommend.keep([sharpness[2], impact[2]], had, 3), [sharpness[2], impact[2], looter[0]])
        self.assertEqual(recommend.keep([sharpness[2], impact[2]], had, 2), [sharpness[2], impact[2]])
        self.assertEqual(recommend.best(recommend.goal("Loot"), "Armor", (), looter + luck, 1), [looter[2]])
        self.assertEqual(recommend.best(recommend.goal("Loot"), "Armor", (), looter + luck, 0), [])

    def test_it_says_what_it_did_and_how_it_chose(self):
        sharpness, looter, luck = (effect(name, "All gear") for name in ("Sharpness", "Looter", "Luck"))
        damage = recommend.goal("Damage")
        self.assertEqual(
            recommend.explain(damage, "Sword", "Melee", ("Fighter",), [sharpness[2]], kept=[looter[0]], dropped=[luck[1]]),
            "Best for damage on the Sword (Fighter gear): Sharpness III. Kept Looter I. Took off Luck II. In the editor's order: "
            "bonuses that always apply first, then critical hits and charged shots, then ones that need the right enemy or moment.",
        )
        said = recommend.explain(recommend.goal("Loot"), "The Burning Blade", "Melee", (), [looter[2], luck[2]], kept=[], dropped=[])
        self.assertTrue(said.startswith("Best for loot on The Burning Blade (a melee weapon with no archetype): Looter III and Luck III. In the editor's order: "), said)
        self.assertEqual(recommend.gear_words("Armor", ("Fighter", "Ranger", "Tank")), "Fighter, Ranger and Tank gear")
        self.assertEqual(recommend.gear_words("Artifact", ()), "an artifact with no archetype")

    def test_it_says_where_the_game_rolls_what_this_item_cant_get(self):
        gear = effect("Speed", "Ranger gear") + effect("Acrobat", "Trickster gear") + effect("Cooldown", "Any artifact, Mage gear")
        self.assertEqual(
            recommend.nothing(recommend.goal("Mobility"), "Sword", "Melee", ("Fighter",), gear),
            "The game rolls no effect for mobility on the Sword (Fighter gear). It rolls them on Ranger and Trickster gear. "
            "You can still add one from the list by hand.",
        )
        self.assertIn("It rolls them on any artifact and Mage gear.", recommend.nothing(recommend.goal("Artifacts and souls"), "Sword", "Melee", (), gear))
        # Nothing known that serves it: nothing more to say.
        self.assertEqual(
            recommend.nothing(recommend.goal("Companions"), "Sword", "Melee", (), gear),
            "The game rolls no effect for companions on the Sword (a melee weapon with no archetype).",
        )

    def test_xp_points_to_the_talisman_that_gives_it(self):
        xp = recommend.goal("XP")
        self.assertEqual(xp.order, ())
        self.assertEqual(recommend.nothing(xp, "Sword", "Melee", (), []), xp.instead)
        most_xp = next(preset for preset in presets.PRESETS if preset.title == "Most XP")  # the preset it names
        self.assertEqual((most_xp.group, [kit_item.name for kit_item in most_xp.items]), (presets.GOALS, ["The Eye of Experience"]))
        self.assertIn("The Eye of Experience talisman", xp.instead)
        self.assertIn("under Goals, as Most XP", xp.instead)

    def test_the_goals(self):
        self.assertEqual([goal.name for goal in recommend.GOALS], ["Damage", "Survival", "Mobility", "Loot", "Artifacts and souls", "Companions", "XP"])
        self.assertIsNone(recommend.goal("Fishing"))
        for goal in recommend.GOALS:
            self.assertEqual(len(set(goal.order)), len(goal.order), goal.name)
            self.assertTrue(bool(goal.order) != bool(goal.instead), goal.name)
            self.assertTrue(goal.instead or goal.how.endswith("."), goal.name)


if __name__ == "__main__":
    unittest.main()
