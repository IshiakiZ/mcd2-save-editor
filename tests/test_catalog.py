"""Checks on the real item list (dungeons2_editor/data/items.json), which tools/build_item_catalog.py makes.

The other tests use a pinned copy, so these are the ones that notice a list that came out wrong.
"""

import copy
import json
import unittest

from dungeons2_editor import hero as heroes
from dungeons2_editor import presets, recommend
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
        # Every item goes by the game's name, but for five books whose IDs players' collections showed and nobody
        # has put a name to: they go by their IDs.
        self.assertEqual(
            [item.name for item in self.items if item.name_from_id],
            ["Burst Bowstring", "Guarding Strike", "Multi Potion", "Shadow Strike", "Soul Aspect"],
        )
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
        # The Lucky Clover is saved as DoubleDrop: its 7% chance of more loot is Looting 0.07 at level 3 (issue 20).
        clover = ids["Lucky Clover"]
        self.assertEqual((clover.id, clover.confirmed, [level["intensity"] for level in clover.levels]), ("SW.Item.Talisman.DoubleDrop", True, [0.02, 0.04, 0.07]))
        self.assertTrue(all(level["effect"] == "SW.Effect.Looting" for level in clover.levels))
        # A companion's talisman carries a tag at each level and no effect: all four have been reported with theirs.
        for name, tag in (("Golem Kit", "IronGolem"), ("Prickle's Mark", "Prickle"), ("Wobblestone", "Wobble"), ("Tasty Bone", "Wolf")):
            self.assertEqual((ids[name].id, ids[name].confirmed), (f"SW.Item.Talisman.{tag}", True))
            self.assertEqual(list(ids[name].levels), [{"tags": [f"SW.Talisman.{tag}.Level.{level}"]} for level in (1, 2, 3)])
        # The last three came in one list (issue 23). The Ocelot's Paw by its number, the Medallion of Momentum as the
        # one talisman about moving fast, and the Wonderful Wheat as the companion talisman left over: a llama's.
        paw, medallion, wheat = ids["Ocelot's Paw"], ids["Medallion of Momentum"], ids["Wonderful Wheat"]
        self.assertEqual((paw.id, [level["intensity"] for level in paw.levels]), ("SW.Item.Talisman.Plummeting", [1.1, 1.2, 1.35]))
        self.assertIn("35% more damage", paw.effect)
        self.assertEqual((medallion.id, [level["intensity"] for level in medallion.levels]), ("SW.Item.Talisman.SpeedIncrement", [1, 2, 3]))
        # The game spells this one ID with a small "sw", and the editor keeps it as saved.
        self.assertEqual((wheat.id, list(wheat.levels)), ("sw.Item.Talisman.Llama", [{"tags": [f"SW.Talisman.Llama.Level.{level}"]} for level in (1, 2, 3)]))
        self.assertEqual((heroes.display_name("sw.Item.Talisman.Llama"), heroes.tag_kind("sw.Item.Talisman.Llama")), ("Wonderful Wheat", "Talisman"))
        # So every talisman comes with what it does, and every item's ID has been seen in a real save.
        self.assertFalse([item.name for item in self.items if item.kind == "Talisman" and not item.levels])
        self.assertFalse([item.name for item in self.items if not item.confirmed])

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
        self.assertEqual(book.enchant_points["Unique"], [3, 8, 15])  # all three have been seen in a save
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
            self.assertEqual(choice.template.lower(), f"{choice.effect}.{choice.tier}".lower())
            if choice.name in names:
                self.assertEqual(choice.slots, names[choice.name].slots)
            else:  # in a save, but nobody knows what the game calls it: it goes by its ID, and on whatever takes one
                self.assertEqual((choice.name, choice.slots), (heroes.words(choice.effect.rsplit(".", 1)[1]), ()), choice.title)
        saved_enchantments = {(choice.title, choice.strength) for choice in book.enchantments}
        self.assertTrue({("Ancient Alchemy I", 0.5), ("Ancient Alchemy II", 0.6), ("Healing Smite I", 0.3), ("Piercing I", 1)} <= saved_enchantments)
        # From a player's Uniques (issue 20). An enchantment's saved strength follows no rule: Ancient Alchemy's 30,
        # 45 and 60 souls are 0.5, 0.6 and 0.85, while Barrier Brew's 6 seconds and Swirling's 100% are 6 and 1.
        self.assertTrue({("Ancient Alchemy III", 0.85), ("Barrier Brew III", 6), ("Swirling III", 1), ("Crash Landing III", 0.5)} <= saved_enchantments)
        self.assertEqual(heroes.display_name("SW.Item.EnchantmentBook.PotionBarrier"), "Barrier Brew")
        # A save spells Springload's template with a small l, unlike its effect: written as saved.
        springload = next(choice for choice in book.enchantments if choice.title == "Springload III")
        self.assertEqual((springload.effect, springload.template, springload.strength), ("SW.Enchantment.SpringLoaded", "SW.Enchantment.Springloaded.III", 6))
        self.assertEqual(heroes.display_name("SW.Item.EnchantmentBook.Radiance"), "Healing Smite")  # the book the save calls Radiance
        # MetaBot's table says Critical Edge III is 30% and the game's wording for it says 40%. A save settled it: 0.3
        # (the 40% is the tier a Unique carries). Recovery had the same clash, and its tier III was left out until a
        # save showed it: 0.3 as well, the table's number again (issue 28). The wording that disagrees isn't shown.
        self.assertEqual([(choice.tier, choice.strength, choice.seen) for choice in book.effects if choice.name == "Critical Edge"],
                         [("I", 0.1, True), ("II", 0.2, True), ("III", 0.3, True)])
        self.assertEqual([(choice.tier, choice.strength, choice.seen, choice.shown) for choice in book.effects if choice.name == "Recovery"],
                         [("I", 0.1, True, "10%"), ("II", 0.2, True, "20%"), ("III", 0.3, True, "30%")])
        self.assertNotIn("40", next(choice for choice in book.effects if choice.title == "Recovery III").what)
        # Tiers the list offered on the table's word that a save has since shown (issue 28, made with a version that
        # didn't offer them), and two on that list it leaves as they were: that version could write those itself.
        seen = {choice.title: choice.seen for choice in book.effects}
        self.assertEqual(
            [seen[title] for title in ("Pack Leader III", "Totem Radius III", "Momentum III", "Evasion II", "Brawler III", "Prowler III", "Prickly III")],
            [True] * 7,
        )
        self.assertEqual((seen["Cooldown III"], seen["Vanguard III"]), (False, False))
        # Two enchantments a save calls Channeling and SoulFireAspect, and Health Synergy's top tier, from the same
        # list. The developer put them on items and read the game's names for them off those.
        self.assertTrue({("Lightning Surge III", 3), ("Soul Blast III", 3), ("Health Synergy III", 0.35), ("Health Synergy I", 0.15)} <= saved_enchantments)
        # The same tier of one enchantment has been saved with two numbers (0.244871 and 0.5): the first one seen stays.
        self.assertIn(("Power Amplifier III", 0.244871), saved_enchantments)
        # Poison Fog's first tier, from lists made with a version that had none of it to write (issues 29 and 30), and
        # Somersault's third, which no version has offered (issue 31). Poison Fog goes on melee weapons, as its book says.
        self.assertTrue({("Poison Fog III", 1), ("Somersault II", 2), ("Somersault III", 3)} <= saved_enchantments)
        self.assertEqual(next(choice for choice in book.enchantments if choice.title == "Poison Fog III").slots, ("Melee",))
        self.assertEqual((len({choice.effect for choice in book.enchantments}), len(book.enchantments)), (22, 29))
        # What a save calls an effect isn't always MetaBot's name for it, even when MetaBot has that name too.
        self.assertEqual({choice.effect for choice in book.effects if choice.name == "Recovery"}, {"SW.Effect.Constitution"})
        self.assertEqual(next(choice for choice in book.effects if choice.title == "Acrobat I").what, "Reduces rolling cooldown time by 10%.")
        self.assertTrue(all(enchantment.what for enchantment in names.values()))
        # Two do the same at every tier, so there are no numbers to give for them.
        self.assertEqual(sorted(name for name, enchantment in names.items() if not enchantment.levels), ["Cow Stampede", "Tumbleshot"])

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
        # Each gets the highest tier of its effect that a save has shown.
        # The Humbler Heartstring comes with Piercing of its own (ten enemies), so the kit doesn't spend its
        # enchantment on Piercing as well: it gets Chain Reaction, the guide's first choice for it.
        self.assertEqual(made["Humbler Heartstring"], ("Chain Reaction III", ["Marksman III"]))
        heartstring = hero.item(hero.add_item("SW.Item.Greatbow", build_catalog([hero])[0].template, rarity="Unique", power=30))
        self.assertEqual(heartstring.effect_lines(), ["Its own: Piercing"])
        # You can still do it by hand: the game lets an item be enchanted with what it has built in.
        piercing = next(choice for choice in heroes.effect_choices([])[1] if choice.title == "Piercing III")
        hero.set_enchantment(heartstring.index, piercing)
        self.assertEqual(hero.item(heartstring.index).effect_lines(), ["Its own: Piercing", "Enchanted: Piercing III, 15 enchantment points"])
        # The build names nothing for the Hunter's Hatchet, and Critical Quiver (its pick for the Duster) hasn't been
        # seen saved yet: those get the editor's own pick for their kind of gear, and so do the leggings and boots.
        self.assertEqual(made["Hunter's Hatchet"], ("Fire Aspect III", ["Critical Edge III"]))
        self.assertEqual(made["Sharpshooter Fedora"], ("Ender Quiver III", ["Projectile Protection III"]))
        self.assertEqual(made["Sharpshooter Duster"], ("Health Synergy III", ["Projectile Protection III"]))
        self.assertEqual(made["Flaming Quiver"], (None, ["Cooldown II", "Spiritual III"]))  # an artifact tops out at Special: two effects
        # Every weapon and armor piece of every kit gets an enchantment, and no two pieces of a kit the same one.
        for kit in (preset for preset in presets.PRESETS if preset.group == presets.KITS):
            fresh = Hero(copy.deepcopy(save))
            planned = presets.plan(kit, fresh, build_catalog([fresh]), power=30, rarity="Unique")
            gear = [addition for addition in planned.add if addition.found.kind in presets.ENCHANT_FALLBACKS]
            given = [addition.enchantment.title for addition in gear if addition.enchantment is not None]
            self.assertEqual((len(given), len(set(given))), (len(gear), len(gear)), f"{kit.title}: {given}")
            # It brings the books of what the build names and of what it put on, where the editor knows the book.
            wanted = {name for item in kit.items for name in item.enchants} | {addition.enchantment.name for addition in gear}
            self.assertEqual({book.name for book in planned.books}, wanted & {book.name for book in fresh.missing_books(build_catalog([fresh]))}, kit.title)
            self.assertTrue(planned.books, kit.title)

    def test_uniques_come_with_the_effect_saves_show(self):
        uniques = [item for item in self.items if item.unique]
        owned = [item for item in uniques if item.unique_own is not None]
        self.assertGreaterEqual(sum(item.unique_own.seen for item in owned), 97)
        self.assertEqual((len(uniques), len(owned)), (116, 116))
        for item in owned:
            own = item.unique_own
            self.assertRegex(own.effect, r"^SW\.(Effect|Enchantment)\.[A-Za-z.]+$", item.unique)
            self.assertRegex(own.template, r"^SW\.(Effect[Tt]emplate|Enchantment)\.[A-Za-z.]+$", item.unique)
            self.assertIsInstance(own.strength, (int, float))
            if own.seen:  # seen on this very Unique, so its ID has been seen too
                self.assertTrue(item.unique_id and not own.like, item.unique)
            else:  # taken from a Unique that has been seen, and that MetaBot describes in the very same words
                twin = next(other for other in owned if other.unique == own.like)
                self.assertTrue(twin.unique_own.seen, item.unique)
                self.assertEqual((twin.unique_effect, twin.unique_own.effect, twin.unique_own.strength, twin.unique_own.template),
                                 (item.unique_effect, own.effect, own.strength, own.template), item.unique)
        own = {item.unique: (item.unique_own.effect, item.unique_own.strength, item.unique_own.template) for item in owned}
        # Most are a gear effect at a tier of its own, with the number its description gives ("less" is below zero).
        self.assertEqual(own["Pride of the Plains"], ("SW.Effect.Duelist", 0.4, "SW.EffectTemplate.Duelist.Unique"))
        self.assertEqual(own["Oracle Tights"], ("SW.Effect.Cooldown", -0.3, "SW.EffectTemplate.Cooldown.Unique"))
        self.assertEqual(own["The Prospector's Pick"], ("SW.Effect.EmeraldsIncrease", 0.2, "SW.EffectTemplate.Prospector.Unique"))  # two names
        # A few are enchantments under another name, and follow no pattern: the one issue 19 asked about is one.
        self.assertEqual(own["Prime Enchanter's Gauntlets"], ("SW.Enchantment.MaulerDive", 1, "SW.Enchantment.MaulerDive"))
        self.assertEqual(own["Sculker Claws"], ("SW.Enchantment.ClawingShadow.Unique", 0.08, "SW.Enchantment.ClawingShadow.Unique"))
        self.assertEqual(own["Redstone Wrecker"], ("SW.Enchantment.FireAspect", 1, "SW.Enchantment.FlameBelch.Unique"))
        # The Slaymore hasn't been seen; two Uniques that deal the same 50% to secondary targets have.
        slaymore = next(item for item in owned if item.unique == "Slaymore").unique_own
        self.assertEqual((slaymore.seen, slaymore.template), (False, "SW.EffectTemplate.SweepingEdge.Unique"))
        self.assertIn(slaymore.like, ("Humbler Greaves", "Rimefrost Longjohns"))
        # An effect with no tiers has no tier on its template: the Lullaby Blade's Soulsick on hit.
        self.assertEqual(own["Lullaby Blade"], ("SW.Effect.SoulCurse", 1, "SW.EffectTemplate.SoulCurse"))
        # Three Uniques that say the same thing, each seen: saved alike.
        self.assertEqual({own[name] for name in ("Rimefrost Plodders", "Oracle Mantle", "Mad Sifter Mask")}, {("SW.Effect.Saboteur", 1, "SW.EffectTemplate.Saboteur.Unique")})
        # Nothing is worked out for a Unique that says something no seen Unique says. The one that left, the
        # Packleader Paws, came with /issues/32, made with a version that had no own effect to write for it: Bowyer
        # at a tier of its own, past the 0.3 of tier III.
        self.assertEqual(own["Packleader Paws"], ("SW.Effect.ArrowBurst", 0.5, "SW.EffectTemplate.ArrowBurst.Unique"))
        self.assertTrue(next(item for item in owned if item.unique == "Packleader Paws").unique_own.seen)
        self.assertEqual([item.unique for item in uniques if item.unique_own is None], [])
        # Two are saved with a template the game spells with a small t. Written as saved.
        self.assertEqual({own[name] for name in ("Humbler Antenna", "Monster Masher")}, {("SW.Effect.Protection", -0.25, "SW.Effecttemplate.Protection.Unique")})
        # "50% more" can be saved as 1.5: the way round follows the effect's rolled tiers (Spiritual I is 1.25).
        self.assertEqual(own["Alchemist Loafers"], ("SW.Effect.SoulMax", 1.5, "SW.EffectTemplate.BagOfSouls.Unique"))
        self.assertEqual(own["The Shackler"], ("SW.Effect.Chains", 0.3, "SW.EffectTemplate.Chains.Unique"))
        # The Humbler Heartstring's is Piercing itself, at a tier the Enchantsmith doesn't sell: ten enemies.
        self.assertEqual(own["Humbler Heartstring"], ("SW.Enchantment.Piercing", 10, "SW.Enchantment.Piercing.Unique"))

    def test_a_unique_is_made_the_way_the_game_saved_one(self):
        # Two of the sixty Uniques in issue 20, exactly as the game saved their effects: its own first, then what it
        # rolled (a Unique can roll two), then the Enchantsmith's work.
        game = {
            "SW.Item.HeavyCrossbow_Unique1": json.loads(
                '[{"TypeTag":"SW.Item.Effect.Static","EffectsInThisBatch":[{"TypeTag":"SW.Effect.PointBlank","Intensity":1,"Quality":0,'
                '"EnchantmentPointsInvested":0,"GeneratorData":{"GeneratorParentTemplate":"SW.EffectTemplate.PointBlank.Unique","Locked":false}}]},'
                '{"TypeTag":"SW.Item.Effect.Rerollable","EffectsInThisBatch":[{"TypeTag":"SW.Effect.Committed","Intensity":0.25,"Quality":0,'
                '"EnchantmentPointsInvested":0,"GeneratorData":{"GeneratorParentTemplate":"SW.EffectTemplate.Committed.II","Locked":false}}]},'
                '{"TypeTag":"SW.Item.Effect.Enchantment","EffectsInThisBatch":[{"TypeTag":"SW.Enchantment.Swirling","Intensity":1,"Quality":0,'
                '"EnchantmentPointsInvested":15,"GeneratorData":{"GeneratorParentTemplate":"SW.Enchantment.Swirling.III","Locked":false}}]}]'
            ),
            "SW.Item.Longbow_Unique1": json.loads(
                '[{"TypeTag":"SW.Item.Effect.Static","EffectsInThisBatch":[{"TypeTag":"SW.Effect.Sniper","Intensity":1,"Quality":0,'
                '"EnchantmentPointsInvested":0,"GeneratorData":{"GeneratorParentTemplate":"SW.EffectTemplate.Sniper.Unique","Locked":false}}]},'
                '{"TypeTag":"SW.Item.Effect.Rerollable","EffectsInThisBatch":[{"TypeTag":"SW.Effect.Knockback","Intensity":0.3,"Quality":0,'
                '"EnchantmentPointsInvested":0,"GeneratorData":{"GeneratorParentTemplate":"SW.EffectTemplate.Knockback.III","Locked":false}},'
                '{"TypeTag":"SW.Effect.Opulence","Intensity":0.02,"Quality":0,"EnchantmentPointsInvested":0,'
                '"GeneratorData":{"GeneratorParentTemplate":"SW.EffectTemplate.Opulence.II","Locked":false}}]}]'
            ),
        }
        gear, enchantments = heroes.effect_choices([])
        pick = {choice.title: choice for choice in gear + enchantments}
        hero = Hero(hero_save())
        catalog = {entry.tag: entry for entry in build_catalog([hero])}
        for tag, rolled, enchantment in (
            ("SW.Item.HeavyCrossbow_Unique1", ["Bounty Hunter II"], "Swirling III"),
            ("SW.Item.Longbow_Unique1", ["Knockback III", "Raider II"], None),
        ):
            base = heroes.base_tag(tag)
            index = hero.add_item(base, catalog[base].template, rarity="Unique", power=20)
            # The effect of its own is there from the start, saved the way the game saves it.
            self.assertEqual(hero.item(index).data["Effects"], game[tag][:1])
            hero.set_effects(index, [pick[title] for title in rolled])
            if enchantment:
                hero.set_enchantment(index, pick[enchantment])
            self.assertEqual(json.dumps(hero.item(index).data["Effects"]), json.dumps(game[tag]), tag)  # key for key, in order
            # Taking the rolled effects and the enchantment off again leaves what makes it that Unique.
            hero.set_effects(index, [])
            hero.set_enchantment(index, None)
            self.assertEqual(hero.item(index).data["Effects"], game[tag][:1])

    def test_the_wonderful_wheat_is_added_under_the_id_the_game_writes(self):
        hero = Hero(hero_save())
        hero.document["CharacterSaveV1"]["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", seed=61))
        entry = next(entry for entry in build_catalog([hero]) if entry.name == "Wonderful Wheat")
        self.assertEqual((entry.tag, entry.kind, entry.confirmed_at(), entry.no_effect), ("sw.Item.Talisman.Llama", "Talisman", True, False))
        wheat = hero.item(hero.add_item(entry.tag, entry.template))
        self.assertEqual((wheat.tag, wheat.name, wheat.is_talisman, wheat.data["Effects"]), ("sw.Item.Talisman.Llama", "Wonderful Wheat", True, []))
        self.assertEqual([level["LevelTags"] for level in wheat.progression["ItemLevels"]], [[f"SW.Talisman.Llama.Level.{level}"] for level in (1, 2, 3)])
        # One the game gave is recognised the same way, and isn't reported as an ID the editor doesn't know.
        self.assertIn("sw.Item.Talisman.Llama", hero.seen_item_types() | {wheat.tag})
        with self.assertRaisesRegex(ValueError, "isn't an item ID"):
            hero.add_item("Sw.Item.Talisman.Llama", entry.template)  # only the two spellings saves have shown

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
        self.assertEqual((len(books), len([book for book in books if book.name_from_id])), (32, 5))
        # That is every book there is: MetaBot's enchantments, less the two that are built into a Unique. And as
        # many enchantments are without a book here as books are without a name.
        bookless = set(heroes.enchantments()) - {book.name for book in books}
        self.assertEqual(len(books), len(heroes.enchantments()) - 2)
        self.assertEqual(bookless - {"Ichor Blast", "Primed Enchantment"}, {"Bottomless Brew", "Shadowcloak", "Shielding Smite", "Soul Blast", "Tumbleshot"})
        # Four books the developer named by putting their enchantments on items and reading the game's word for each.
        # An enchantment is saved under its book's ID, so the book takes the name.
        self.assertEqual(
            [heroes.display_name(f"SW.Item.EnchantmentBook.{book}") for book in ("Blowback", "Borealis", "Channeling", "LingeringPower", "Thundering")],
            ["Crash Landing", "Ender Mines", "Lightning Surge", "Power Amplifier", "Thundering"],
        )
        self.assertEqual(heroes.book_enchantment("SW.Item.EnchantmentBook.Channeling").slots, ("Melee",))
        # The fifth, Soul Blast, is saved as SoulFireAspect, which no book is called: the enchantment has its name,
        # and the book most likely to be its own (SoulAspect) keeps its ID until a save ties the two.
        by_effect = {choice.effect: choice for choice in heroes.effect_choices()[1]}
        self.assertEqual((by_effect["SW.Enchantment.SoulFireAspect"].title, by_effect["SW.Enchantment.SoulFireAspect"].slots), ("Soul Blast III", ("Melee",)))
        self.assertEqual((heroes.display_name("SW.Item.EnchantmentBook.SoulAspect"), heroes.book_enchantment("SW.Item.EnchantmentBook.SoulAspect")), ("Soul Aspect", None))
        for book in books:
            self.assertTrue(book.id.startswith("SW.Item.EnchantmentBook.") and book.confirmed, book.id)
            if book.name_from_id:  # seen in a save's collections, but nobody has said what the game calls it
                self.assertEqual(book.name, heroes.words(book.id.rsplit(".", 1)[1]))
                self.assertNotIn(book.name, heroes.enchantments(), book.id)  # a name the game uses would be a claim
                self.assertIsNone(heroes.book_enchantment(book.id))
                self.assertFalse(heroes.name_is_known(book.id))
            else:
                self.assertIn(book.name, heroes.enchantments(), book.id)
        self.assertEqual(heroes.book_text("SW.Item.EnchantmentBook.GuardingStrike"), "An enchantment book. The editor doesn't know what the game calls its enchantment yet.")
        # A hero with none of them is offered all thirty-two, and gets them in one go.
        hero = Hero(hero_save())
        catalog = build_catalog([hero])
        self.assertEqual(len(hero.missing_books(catalog)), 32)
        self.assertEqual(len(hero.add_books(catalog)), 32)
        self.assertEqual({item.rarity for item in hero.books()}, {"None"})
        # Two that players' saves and words tied to their names: they go on armor, as the game has them.
        named = {choice.effect: choice for choice in heroes.effect_choices()[1]}
        amplifier, stampede = named["SW.Enchantment.Arcane"], named["SW.Enchantment.Unstoppable"]
        self.assertEqual((amplifier.title, amplifier.strength, amplifier.slots, amplifier.levels), ("Artifact Amplifier III", 9, ("Armor",), "6 / 7.5 / 9 seconds"))
        self.assertEqual((stampede.title, stampede.slots, stampede.levels), ("Cow Stampede III", ("Armor",), ""))
        self.assertEqual(stampede.what, "Rolling into enemies damages and knocks them back")
        self.assertTrue(stampede.fits("Armor", "Helmet") and not stampede.fits("Melee"))

    def test_what_a_players_list_added_that_the_editor_could_not_have_written(self):
        # /issues/26, made with 1.12.0, which had neither of these effects and none of these enchantment tiers.
        gear, enchantments = heroes.effect_choices()
        seen = {(choice.name, choice.tier): (choice.effect, choice.strength, choice.seen) for choice in gear + enchantments}
        self.assertEqual(seen[("Shackler", "III")], ("SW.Effect.Chains", 0.25, True))
        self.assertEqual(seen[("Point Blank", "I")], ("SW.Effect.PointBlank", 0.25, True))
        self.assertEqual((seen[("Shackler", "I")][2], seen[("Point Blank", "III")][2]), (False, False))  # from the game files' table
        self.assertEqual(seen[("Chain Reaction", "III")], ("SW.Enchantment.ChainReaction", 5, True))
        self.assertEqual(seen[("Somersault", "II")], ("SW.Enchantment.MultiRoll", 2, True))
        self.assertEqual(seen[("Health Synergy", "I")], ("SW.Enchantment.HealthSynergy", 0.15, True))
        self.assertNotEqual(seen[("Thundering", "III")][1], 0.264703)  # this list's number for it: see /issues/32's, below
        self.assertEqual(seen[("Power Amplifier", "III")], ("SW.Enchantment.LingeringPower", 0.244871, True))  # what a save calls LingeringPower
        self.assertEqual((seen[("Ender Quiver", "II")], seen[("Ender Quiver", "III")]), (("SW.Enchantment.ExpandedQuiver", 3, True), ("SW.Enchantment.ExpandedQuiver", 4, True)))
        # They roll where the game rolled them: Shackler on a Support's crossbow, Point Blank on a Tank's.
        by_name = {choice.name: choice for choice in gear}
        self.assertTrue(by_name["Shackler"].rolls_on_item("Ranged", heroes.archetypes("SW.Item.ScatterCrossbow_Unique1")))
        self.assertTrue(by_name["Point Blank"].rolls_on_item("Ranged", heroes.archetypes("SW.Item.HeavyCrossbow")))

    def test_what_a_list_made_with_1_14_2_added(self):
        # /issues/32. 1.14.2 had no Dynamo to write, so the one on this list's Redstone boots is the game's, and it
        # is the game's own number for the tier (MetaBot: 20% / 30% / 40%).
        _gear, enchantments = heroes.effect_choices()
        seen = {(choice.name, choice.tier): choice for choice in enchantments}
        dynamo = seen[("Dynamo", "III")]
        self.assertEqual((dynamo.effect, dynamo.strength, dynamo.seen, dynamo.slots), ("SW.Enchantment.Dynamo", 0.4, True, ("Armor",)))
        self.assertEqual((dynamo.what, dynamo.levels), ("Rolling amplifies your next attack", "20% / 30% / 40%"))
        # The same list has Thundering at tier III as 0.5, where /issues/26 has 0.264703 and 1.14.2 would have
        # written that. Both are in saves. 0.5 is also the game's own number for the tier (a 50% chance for 50% of
        # the damage), so it's the one the editor writes.
        thundering = seen[("Thundering", "III")]
        self.assertEqual((thundering.effect, thundering.strength, thundering.seen), ("SW.Enchantment.Thundering", 0.5, True))
        # A kit whose build names Dynamo can put it on now: MetaBot's planner has it on the Twisted Warden's hood.
        fresh = Hero(hero_save())
        kit = next(preset for preset in presets.PRESETS if preset.title == "Melee damage")
        planned = presets.plan(kit, fresh, build_catalog([fresh]), power=30, rarity="Unique", enchant=True)
        made = {addition.name: addition.enchantment.title for addition in planned.add if addition.enchantment is not None}
        self.assertEqual(made["Twisted Warden Blindfold"], "Dynamo III")

    def test_every_item_that_rolls_effects_has_its_archetypes(self):
        gear = [item for item in self.items if item.kind in heroes.EFFECT_KINDS]
        # MetaBot gives these no archetype: all they roll comes from their slot's pool.
        self.assertEqual(
            sorted(item.name for item in gear if not item.tags),
            ["Bow", "Conductive Quiver", "Firework Arrow", "Flaming Quiver", "Freezing Quiver", "Venomous Quiver"],
        )
        self.assertEqual(sorted(item.unique for item in gear if item.unique and not item.unique_tags), ["Ranger's Promise"])
        known = {"Fighter", "Mage", "Ranger", "Summoner", "Support", "Tank", "Trickster"}
        for item in gear:
            self.assertTrue(set(item.tags) | set(item.unique_tags) <= known, item.name)
        # A Unique has archetypes of its own, and an artifact may have an element.
        self.assertEqual(heroes.archetypes("SW.Item.Greatbow"), ("Fighter", "Ranger"))
        self.assertEqual(heroes.archetypes("SW.Item.Greatbow_Unique1"), ("Fighter", "Ranger", "Tank"))
        self.assertEqual(heroes.archetypes("SW.Item.NoSuchThing"), ())
        elements = {item.name: item.element for item in self.items if item.element}
        self.assertEqual(set(elements.values()), {"Fire", "Frost", "Lightning", "Poison", "Soul"})
        self.assertEqual((elements["Blaze Bangle"], elements["Soul Harvester"]), ("Fire", "Soul"))
        self.assertTrue(all(item.kind == "Artifact" for item in self.items if item.element))
        bangle = next(item for item in self.items if item.name == "Blaze Bangle")
        self.assertEqual((heroes.element(bangle.id), heroes.element("SW.Item.Sword")), ("Fire", ""))

    def test_the_pools_fit_what_the_game_rolled_on_players_items(self):
        # Items the game itself made, from players' lists, with the effects it rolled on them. Counted over all
        # of those lists, 338 of 342 rolled effects are in the pools of the item they're on; the other four are
        # on items in /issues/22, whose sender had changed items with the editor.
        rolled = {
            "SW.Item.Longbow_Unique1": [("SW.Effect.Knockback", "SW.EffectTemplate.Knockback.III"), ("SW.Effect.Opulence", "SW.EffectTemplate.Opulence.II")],  # Creaking's Reach, /issues/20
            "SW.Item.MushroomBoots_Unique": [("SW.Effect.ElementalProtection", "SW.EffectTemplate.ElementalProtection.II"), ("SW.Effect.FrostFocus", "SW.EffectTemplate.FrostFocus.III")],  # Fly Agaric Galoshes, /issues/20
            "SW.Item.HewnBarkChest_Unique": [("SW.Effect.Vivify", "SW.EffectTemplate.Vivify.II"), ("SW.Effect.Expand", "SW.EffectTemplate.Expand.II")],  # Woodsprite Barkpiece, /issues/23
            "SW.Item.HewnBarkLeggings_Unique": [("SW.Effect.Saboteur", "SW.EffectTemplate.Saboteur.III"), ("SW.Effect.Vivify", "SW.EffectTemplate.Vivify.II")],  # Woodsprite Trunks, /issues/23
            "SW.Item.HoneyLeggings_Unique": [("SW.Effect.HealingFocus", "SW.EffectTemplate.HealingFocus.III"), ("SW.Effect.Expand", "SW.EffectTemplate.Expand.II")],  # Hivemind Trousers, /issues/23
            "SW.Item.Crossbow_Unique1": [("SW.Effect.Knockback", "SW.EffectTemplate.Knockback.II"), ("SW.Effect.Vanguard", "SW.EffectTemplate.Vanguard.II")],  # The Shackler, /issues/23
            "SW.Item.GiantMallet_Unique1": [("SW.Effect.CriticalEdge", "SW.EffectTemplate.CriticalEdge.II"), ("SW.Effect.SweepingEdge", "SW.EffectTemplate.SweepingEdge.III")],  # Monster Masher, /issues/23
            "SW.Item.Glaive_Unique1": [("SW.Effect.Knockback", "SW.EffectTemplate.Knockback.III"), ("SW.Effect.SweepingEdge", "SW.EffectTemplate.SweepingEdge.III")],  # Golden Glaive, /issues/23
            "SW.Item.Sabre_Unique1": [("SW.Effect.Vanguard", "SW.EffectTemplate.Vanguard.II"), ("SW.Effect.Finesse", "SW.EffectTemplate.Finesse.II")],  # Rascal's Razor, /issues/23
            "SW.Item.Greatbow_Unique1": [("SW.Effect.Sniper", "SW.EffectTemplate.Sniper.II"), ("SW.Effect.CriticalEdge", "SW.EffectTemplate.CriticalEdge.II")],  # Humbler Heartstring, /issues/23
        }
        for tag, effects in rolled.items():
            kind, tags = heroes.tag_kind(tag), heroes.archetypes(tag)
            self.assertTrue(tags, tag)
            for effect, template in effects:
                choice = heroes._named(effect, template)
                self.assertIsNotNone(choice, (tag, effect))
                self.assertTrue(choice.rolls_on_item(kind, tags), f"{choice.name} ({choice.rolls_on}) on {heroes.display_name(tag)} {tags}")
        # And what the game wouldn't roll: a Fighter's effect on a bow that is only a Ranger's.
        vanguard = next(choice for choice in heroes.effect_book().effects if choice.name == "Vanguard")
        self.assertEqual((vanguard.pools, vanguard.rolls_on_item("Ranged", heroes.archetypes("SW.Item.Longbow_Unique1"))), (("Fighter gear",), False))
        self.assertTrue(vanguard.rolls_on_item("Ranged", heroes.archetypes("SW.Item.Crossbow_Unique1")))

    def test_every_goal_ranks_effects_the_list_knows(self):
        book = heroes.effect_book()
        names = {choice.name for choice in book.effects}
        for goal in recommend.GOALS:
            self.assertTrue(set(goal.order) <= names, f"{goal.name}: {sorted(set(goal.order) - names)}")
        self.assertTrue(set(sum(recommend.ABOUT.values(), ())) | set(recommend.ELEMENT_EFFECTS.values()) <= names)
        self.assertTrue(all(choice.pools for choice in book.effects))  # every effect in the list says where it rolls
        gear = list(book.effects)

        def picks(goal, tag, **more):
            found = recommend.candidates(recommend.goal(goal), heroes.tag_kind(tag), heroes.archetypes(tag), gear, **more)
            return [choice.title for choice in found[:4]]

        self.assertEqual(picks("Damage", "SW.Item.Sword"), ["Sharpness III", "Duelist III", "Swiftness III", "Critical Hit III"])
        self.assertEqual(picks("Damage", "SW.Item.Greatbow_Unique1"), ["Impact III", "Ranger I", "Sharpshooter III", "Critical Hit III"])
        self.assertEqual(picks("Damage", "SW.Item.Bow"), ["Impact III", "Critical Hit III", "Critical Edge III", "Persistence III"])  # no archetype
        self.assertEqual(picks("Loot", "SW.Item.Bow"), ["Looter III", "Raider III", "Luck III", "Prospector III"])
        self.assertEqual(picks("Mobility", "SW.Item.Greatbow_Unique1"), ["Speed III"])
        self.assertEqual(picks("Mobility", "SW.Item.Sword"), [])
        self.assertEqual(picks("Damage", "SW.Item.MysticHelmet"), ["Sorcerer II"])
        self.assertEqual(picks("Damage", "SW.Item.MysticHelmet", elements={"Soul"}), ["Sorcerer II", "Soulmancer III"])
        self.assertEqual(picks("Artifacts and souls", "SW.Item.MysticHelmet"), ["Cooldown II", "Spiritual III", "Reaper III", "Sorcerer II"])
        self.assertEqual(picks("Companions", "SW.Item.WolfclutchChest"), ["Pack Leader III", "Shepherd II", "Veterinarian III"])
        self.assertEqual(picks("XP", "SW.Item.Sword"), [])

    def test_a_kit_only_gives_an_item_effects_the_game_rolls_on_it(self):
        hero = Hero(hero_save())
        catalog = build_catalog([hero])
        given = {}
        for preset in presets.PRESETS:
            for rarity in ("Unique", "Special"):
                for addition in presets.plan(preset, hero, catalog, power=30, rarity=rarity).add:
                    kind, tags = addition.found.kind, heroes.archetypes(addition.tag)
                    for choice in addition.effects:
                        self.assertTrue(choice.rolls_on_item(kind, tags), f"{preset.title}: {choice.title} on {addition.name} {tags}")
                    given[addition.name] = [choice.title for choice in addition.effects]
        # Marksman rolls on Ranger and Trickster gear: the Humbler Heartstring is a Ranger's, The Close Ranger isn't.
        self.assertEqual((given["Humbler Heartstring"], given["The Close Ranger"]), (["Marksman III"], ["Critical Edge III"]))

    def test_every_preset_item_is_in_the_list(self):
        catalog = build_catalog([Hero(hero_save())])
        for preset in presets.PRESETS:
            for kit_item in preset.items:
                found = presets.find_item(kit_item.name, catalog)
                self.assertIsNotNone(found, f"{preset.title}: {kit_item.name}")


if __name__ == "__main__":
    unittest.main()
