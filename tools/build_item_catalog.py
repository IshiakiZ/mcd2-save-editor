"""Builds the editor's item and enchantment lists from MetaBot's Minecraft Dungeons II database.

MetaBot (https://metabot.gg/en/minecraft-dungeons-2) lists every item in the game files
(build 1.1.1.0). Its terms allow reusing the data with a link to the page it came from; the
links are in each file this writes and in the README:

    uniques       every Unique, its slot and its base item: so every weapon, and every
                  armor piece with its set and slot
    artifacts     every artifact
    talismans     every talisman and what it does at level 3, and the XP a talisman level takes
    enchantments  every enchantment, the gear it goes on and where its book drops
    effects       every gear effect and its strength at each tier, and on each effect's own
                  page (effects/acrobat) the game's wording for each tier
    guides/enchanting-guide   what each enchantment does at each level, and what a level costs
    weapons, armor            the archetypes of every melee weapon and armor piece (Fighter, Ranger...)
    builds/fighter and the other six archetypes' pages   the archetypes of every ranged weapon

An item's archetypes decide which effects the game can roll on it: MetaBot's builds page says an item
rolls from its slot's pool (any weapon, any artifact, all gear) and from one pool per archetype it
carries, and the effects table says which pools each effect is in. The effects on the items in
players' lists bear that out, so the editor's "Best for" picks only offer an item what it can roll.

The game's own item IDs aren't published anywhere the editor can use, so each item's save ID
comes from real saves where players have reported it, and is otherwise worked out from its
name, following the patterns seen in those saves:

    weapons     SW.Item.<Name>               (Sword, Bow, Longbow)
    armor       SW.Item.<Set><Slot>          (MysticHelmet is the Mystic Circlet)
    artifacts   SW.Item.Artifact.<Name>
    talismans   SW.Item.Talisman.<Name>
    Uniques     the base item's ID with _Unique1 (weapons) or _Unique (armor) on the end
    books       SW.Item.EnchantmentBook.<Name>

IDs seen in real saves are marked "confirmed". The rest are best guesses, and plenty will be
wrong: the game's internal names often aren't the names players see (the Riftslasher is saved
as CurvedLongsword, the Sculk Digger set as CaveCrawler, the Amethyst Lens as
Talisman.RangedBuff). A Unique's own ID is only listed once it has been seen.

The same goes for effects and enchantments (dungeons2_editor/data/effects.json): the editor can
only write one the way a real save holds it, so GEAR_EFFECTS and ENCHANTMENT_TIERS list what
saves have shown, and MetaBot's tables give the names and the numbers the game shows. And for
the effect a Unique comes with (UNIQUE_EFFECTS): each is listed as a save holds it, with its
Unique in the item list.

Run from the repository root:  python tools/build_item_catalog.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://metabot.gg/en/minecraft-dungeons-2/"
PAGES = ("uniques", "artifacts", "talismans", "enchantments", "effects", "guides/enchanting-guide", "weapons", "armor")
ARCHETYPES = ("Fighter", "Mage", "Ranger", "Summoner", "Support", "Tank", "Trickster")
ELEMENTS = ("Fire", "Frost", "Lightning", "Poison", "Soul")  # an artifact has one of these at most
BUILD_PAGES = {archetype: f"builds/{archetype.lower()}" for archetype in ARCHETYPES}
HEADERS = {"User-Agent": "Dungeons2SaveEditor/1.2 (item catalog builder; +https://github.com/IshiakiZ/mcd2-save-editor)"}
DATA = Path(__file__).resolve().parent.parent / "dungeons2_editor" / "data"
PREFIX = "SW.Item."
BOOK = "Enchantment Book"

# IDs seen in real saves, without the SW.Item. in front: the developer's own, and the ones players sent in
# https://github.com/IshiakiZ/mcd2-save-editor/issues/2, /issues/7, /issues/9, /issues/11, /issues/12, /issues/15,
# /issues/17, /issues/20, /issues/21, /issues/22 and /issues/23. From /issues/11 on, a report only lists IDs the
# game itself vouches for.
CONFIRMED_IDS = {
    PREFIX + name
    for name in """
    Sword Bow Longbow HeavyCrossbow
    Axe Claws Claymore Cleaver Crossbow CurvedGreatsword CurvedLongsword Dagger Daggers DualCrossbow
    Gauntlet GiantClub Glaive GreatAxe Greatbow Greatsword Hammer Mace MoonSword Pickaxe Pike Powerbow
    RapidCrossbow Rapier Sabre ScatterCrossbow Scythe ShortSpear Shortbow Shovel Sickles StraightSword
    Trickbow WarHammer Battlestaff

    CaveCrawlerBoots CaveCrawlerChest CaveCrawlerHelmet CaveCrawlerLeggings DiscipleBoots DiscipleChest
    DiscipleHelmet DiscipleLeggings EvocationBoots EvocationHelmet FrostRimeChest FrostRimeLeggings
    HewnBarkBoots HoneyBoots HoneyLeggings MushroomBoots MushroomChest MushroomHelmet MushroomLeggings
    MysticBoots MysticChest MysticHelmet MysticLeggings PhantomBoots PhantomChest PhantomHelmet
    PhantomLeggings RealmreacherBoots RealmreacherChest RealmreacherHelmet RealmreacherLeggings
    RedstoneBoots RedstoneChest RedstoneHelmet RedstoneLeggings ScampBoots ScampChest ScavengerLeggings
    StalwartBoots StalwartChest StalwartHelmet StalwartLeggings TimewornBoots TimewornChest
    UndauntedChest UndauntedHelmet VoyagerBoots VoyagerHelmet VoyagerLeggings WellspringBoots
    WellspringHelmet WolfclutchBoots WolfclutchChest WolfclutchLeggings
    HewnBarkChest HewnBarkHelmet HewnBarkLeggings HoneyChest HoneyHelmet ScampHelmet ScampLeggings
    ScavengerBoots ScavengerHelmet UndauntedBoots UndauntedLeggings VoyagerChest WellspringLeggings
    WolfclutchHelmet EvocationLeggings TimewornHelmet
    EvocationChest FrostRimeBoots FrostRimeHelmet ScavengerChest TimewornLeggings WellspringChest
    GiantMallet

    Artifact.BlizzardStaff Artifact.CarapaceOcarina Artifact.ConductiveBracelet Artifact.CorruptedSeeds
    Artifact.CreeperCandle Artifact.FightersFife Artifact.FireBracelet Artifact.FireworkQuiver
    Artifact.FlameQuiver Artifact.FlameSceptre Artifact.Grindstone Artifact.HasteMushroom
    Artifact.Honeypot Artifact.IronHideLute Artifact.LightningRod Artifact.MaimingMushroom
    Artifact.PoisonBracelet Artifact.PoisonQuiver Artifact.Powershaker Artifact.RallyingHorn
    Artifact.RedstoneMines Artifact.Satchel.Conductive Artifact.Satchel.Fire Artifact.Satchel.Freezing
    Artifact.Satchel.Poison Artifact.SmokeBomb Artifact.SoulHarvester Artifact.TotemOfCasting
    Artifact.TotemOfRegeneration Artifact.TotemOfShielding Artifact.WarBanner Artifact.WardingChimes
    Artifact.WarriorsDrums Artifact.WitchesBrew Artifact.CorruptedBeacon Artifact.FrostQuiver
    Artifact.DeathcapMushroom Artifact.LightningQuiver Artifact.FrostBracelet Artifact.PicnicBlanket

    Talisman.AmmoCapacity Talisman.Brawling Talisman.HealthBoost Talisman.PotionCooldown
    Talisman.RangedBuff Talisman.SoulGather Talisman.Wolf
    Talisman.ArtifactCooldown Talisman.DropChance Talisman.EmeraldIncrease Talisman.ExperienceIncrease
    Talisman.FiringEmeralds Talisman.Healing Talisman.HealthyStrike Talisman.IronGolem Talisman.Prickle
    Talisman.RollingCooldown Talisman.SoulCapacity Talisman.StatusBuff Talisman.Wobble
    Talisman.DoubleDrop Talisman.Plummeting Talisman.SpeedIncrement
    """.split()
} | {"sw.Item.Talisman.Llama"}
# Uniques' own IDs seen in real saves. Each is its base item's ID with _Unique1 (weapons) or _Unique (armor).
UNIQUE_IDS = {
    PREFIX + name
    for name in """
    Axe_Unique1 Claws_Unique1 Pickaxe_Unique1 Sabre_Unique1 Sword_Unique1 Trickbow_Unique1
    Bow_Unique1 Greatsword_Unique1 Mace_Unique1 Powerbow_Unique1 Rapier_Unique1 Sickles_Unique1
    Daggers_Unique1 HeavyCrossbow_Unique1
    CaveCrawlerChest_Unique CaveCrawlerHelmet_Unique StalwartBoots_Unique StalwartChest_Unique VoyagerLeggings_Unique
    HoneyBoots_Unique HoneyChest_Unique HoneyHelmet_Unique HoneyLeggings_Unique
    MysticBoots_Unique MysticChest_Unique MysticHelmet_Unique MysticLeggings_Unique
    RealmreacherBoots_Unique RealmreacherChest_Unique RealmreacherHelmet_Unique RealmreacherLeggings_Unique
    UndauntedBoots_Unique UndauntedChest_Unique UndauntedHelmet_Unique UndauntedLeggings_Unique
    Battlestaff_Unique1 Claymore_Unique1 Cleaver_Unique1 Crossbow_Unique1 CurvedGreatsword_Unique1
    CurvedLongsword_Unique1 Dagger_Unique1 DualCrossbow_Unique1 Gauntlet_Unique1 GiantClub_Unique1
    Glaive_Unique1 GreatAxe_Unique1 Greatbow_Unique1 Hammer_Unique1 Longbow_Unique1 MoonSword_Unique1
    Pike_Unique1 RapidCrossbow_Unique1 ScatterCrossbow_Unique1 Scythe_Unique1 ShortSpear_Unique1
    Shortbow_Unique1 Shovel_Unique1 StraightSword_Unique1 WarHammer_Unique1
    CaveCrawlerBoots_Unique CaveCrawlerLeggings_Unique EvocationChest_Unique EvocationLeggings_Unique
    FrostRimeChest_Unique FrostRimeLeggings_Unique HewnBarkChest_Unique HewnBarkLeggings_Unique
    MushroomBoots_Unique MushroomChest_Unique MushroomHelmet_Unique MushroomLeggings_Unique
    PhantomBoots_Unique PhantomHelmet_Unique PhantomLeggings_Unique RedstoneBoots_Unique
    RedstoneChest_Unique RedstoneHelmet_Unique RedstoneLeggings_Unique ScampBoots_Unique ScampChest_Unique
    ScampHelmet_Unique ScampLeggings_Unique ScavengerChest_Unique ScavengerHelmet_Unique
    ScavengerLeggings_Unique StalwartHelmet_Unique StalwartLeggings_Unique TimewornBoots_Unique
    TimewornChest_Unique TimewornHelmet_Unique TimewornLeggings_Unique VoyagerChest_Unique
    WellspringBoots_Unique WolfclutchBoots_Unique
    DiscipleBoots_Unique DiscipleChest_Unique DiscipleHelmet_Unique HewnBarkBoots_Unique ScavengerBoots_Unique
    VoyagerBoots_Unique
    FrostRimeBoots_Unique FrostRimeHelmet_Unique WellspringChest_Unique WellspringHelmet_Unique
    DiscipleLeggings_Unique EvocationBoots_Unique EvocationHelmet_Unique GiantMallet_Unique1 HewnBarkHelmet_Unique
    PhantomChest_Unique VoyagerHelmet_Unique WellspringLeggings_Unique WolfclutchChest_Unique WolfclutchLeggings_Unique
    """.split()
}
# What a save calls an item, where that isn't the name players see with the spaces taken out.
KNOWN_IDS = {
    "Battle Hammer": "Hammer",
    "Clobberer": "GiantClub",
    "Cookiecutter": "CurvedGreatsword",
    "Double Daggers": "Daggers",
    "Double Sickles": "Sickles",
    "Gauntlets": "Gauntlet",
    "Greataxe": "GreatAxe",
    "Longsword": "StraightSword",
    "Meat Cleaver": "Cleaver",
    "Mob Mallet": "GiantMallet",
    "Riftslasher": "CurvedLongsword",
    "Tidal Sickle": "MoonSword",
    "Twilight Dagger": "Dagger",
    "Wolf Claws": "Claws",  # its Unique, the Sculker Claws, is saved as Claws_Unique1
    "Dual Crossbows": "DualCrossbow",
    "Battle Banner": "Artifact.WarBanner",
    "Blaze Bangle": "Artifact.FireBracelet",
    "Blight Bangle": "Artifact.PoisonBracelet",
    "Blizzard Bangle": "Artifact.FrostBracelet",  # by its name, like the other three bangles
    "Cinder Scepter": "Artifact.FlameSceptre",
    "Conductive Quiver": "Artifact.LightningQuiver",  # the player who reported the ID said so
    "Death Cap Mushroom": "Artifact.DeathcapMushroom",
    "Echo Ocarina": "Artifact.CarapaceOcarina",
    "Electric Bangle": "Artifact.ConductiveBracelet",
    "Ender Fog": "Artifact.SmokeBomb",
    "Fighter's Flute": "Artifact.FightersFife",
    "Fighting Fungus": "Artifact.MaimingMushroom",
    "Firework Arrow": "Artifact.FireworkQuiver",
    "Flaming Quiver": "Artifact.FlameQuiver",
    "Freezing Quiver": "Artifact.FrostQuiver",  # by its name: the report that had it didn't say what the game calls it
    "Honey Dipper": "Artifact.Honeypot",
    "Humbling Horn": "Artifact.RallyingHorn",
    "Picnic Basket": "Artifact.PicnicBlanket",
    "Pouch of Ember": "Artifact.Satchel.Fire",
    "Pouch of Frost": "Artifact.Satchel.Freezing",
    "Pouch of Poison": "Artifact.Satchel.Poison",
    "Pouch of Thunder": "Artifact.Satchel.Conductive",
    "Redstone Mine Launcher": "Artifact.RedstoneMines",
    # By elimination, and by its name: the one artifact ID in saves, and the one artifact name, left without the other.
    "Tempo Truffle": "Artifact.HasteMushroom",
    "Turtle Master's Mandolin": "Artifact.IronHideLute",
    "Venomous Quiver": "Artifact.PoisonQuiver",
    "Warrior Drums": "Artifact.WarriorsDrums",
    "Winter Staff": "Artifact.BlizzardStaff",
    "Witch Brew": "Artifact.WitchesBrew",
    # Talismans are saved by what they do, so the ones not seen yet are almost certainly guessed wrong.
    "Amethyst Lens": "Talisman.RangedBuff",
    "Fist of Iron": "Talisman.Brawling",
    "Glowstone Flask": "Talisman.PotionCooldown",
    "Sigil of Beeswax": "Talisman.HealthBoost",
    "Tasty Bone": "Talisman.Wolf",
    "Twig of Dark Oak": "Talisman.AmmoCapacity",
    "Twisted Tooth": "Talisman.SoulGather",
    # Matched by what they do: the strength a save gives each one at level 3 (TALISMAN_LEVELS) is the number in
    # MetaBot's description of the talisman ("Reduces rolling cooldown time by 45%" is RollCooldown 0.45).
    "Armadillo Amulet": "Talisman.RollingCooldown",
    "Emerald of Good Fortune": "Talisman.EmeraldIncrease",
    "Essence of Efficiency": "Talisman.ArtifactCooldown",
    "Healing Heart": "Talisman.Healing",
    "Looter's Charm": "Talisman.DropChance",
    "Lucky Clover": "Talisman.DoubleDrop",  # "a 7% chance to get additional loot drops" is Looting 0.07
    "Sculk Badge": "Talisman.StatusBuff",
    "Soul Chip": "Talisman.SoulCapacity",
    "Tendrils of the Sprout": "Talisman.HealthyStrike",  # and a player who has one said so
    "The Eye of Experience": "Talisman.ExperienceIncrease",
    "Thrifty Pendant": "Talisman.FiringEmeralds",
    "Ocelot's Paw": "Talisman.Plummeting",  # "Jumping melee attacks deal 35% more damage" is Plummeting 1.35
    # By what's left: the one talisman about moving fast, saved with 1, 2 and 3 for its 30% after 3 seconds.
    "Medallion of Momentum": "Talisman.SpeedIncrement",
    # By their names: none of these has an effect with a number, in a save or on MetaBot.
    "Golem Kit": "Talisman.IronGolem",
    "Prickle's Mark": "Talisman.Prickle",
    "Wobblestone": "Talisman.Wobble",
}
# An ID a save spells its own way. The Wonderful Wheat is the companion talisman left over once the other three
# were named (a llama's, to go by the save), and the game writes its ID with a small "sw": the one ID seen that
# doesn't begin SW.Item. The editor writes it the same way.
EXACT_IDS = {
    "Wonderful Wheat": "sw.Item.Talisman.Llama",
}
# Armor sets named differently in saves. Two come from their Uniques' IDs rather than from a report of the set
# itself: RealmreacherChest_Unique is the Sharpshooter Duster, the Unique Ranger Jacket, and UndauntedHelmet_Unique
# is the Dauntless Horns, the Unique Bounty Hunter Helmet. The set players see as Realmreacher is saved as Timeworn.
# Treehugger is by elimination: HewnBark is the one set name in saves left over, and Treehugger the one set.
SET_NAMES = {
    "Beekeeper": "Honey",
    "Bounty Hunter": "Undaunted",
    "Nomad": "Voyager",
    "Protector": "Stalwart",
    "Ranger": "Realmreacher",
    "Realmreacher": "Timeworn",
    "Sculk Digger": "CaveCrawler",
    "Sculker": "Scavenger",
    "Sifter": "Wellspring",
    "Sorcerer": "Evocation",
    "Steel Wool": "FrostRime",
    "Treehugger": "HewnBark",
    "Wolfpack": "Wolfclutch",
}
# Enchantment books seen in real saves, by the enchantment's name. They're listed so the editor can name them;
# it only offers to add one a hero already has.
BOOK_IDS = {
    "Ancient Alchemy": "SoulInfusedPotion",
    # PotionBarrier by what a save holds for it: 6 at tier III, on a helmet. Barrier Brew is the armor enchantment
    # whose potion makes a Fortifying well for 2, 4 and 6 seconds (the other brew with those numbers, Buddy Brew,
    # is PotionSharing).
    "Barrier Brew": "PotionBarrier",
    "Buddy Brew": "PotionSharing",
    "Chain Reaction": "ChainReaction",
    "Critical Quiver": "CriticalQuiver",
    "Dynamo": "Dynamo",
    "Ender Quiver": "ExpandedQuiver",
    "Fire Aspect": "FireAspect",
    "Frost Crescent": "FrostCrescent",
    "Gravity Pulse": "GravityPulse",
    # Radiance by the quest that hands it out: Training with the Enchantsmith rewards Piercing, Healing Smite and
    # Ancient Alchemy (MetaBot's enchanting guide), and a save got Piercing, Radiance and SoulInfusedPotion from it.
    "Healing Smite": "Radiance",
    "Health Synergy": "HealthSynergy",
    "Piercing": "Piercing",
    "Poison Fog": "PoisonFog",
    "Ricochet": "Ricochet",
    "Shockwave": "Shockwave",
    "Somersault": "MultiRoll",
    "Springload": "SpringLoaded",
    "Swirling": "Swirling",
    "Tempo Theft": "TempoTheft",
    "Thundering": "Thundering",
}
# What a talisman does at each of its three levels, as real saves store it: (effect, template, strengths). The
# effect is SW.Effect.<effect>, its level templates are SW.EffectTemplate.<template>.I to .III, and the strengths are
# the effect's Intensity at each level. A talisman that isn't here can only be added without its effect, so the
# editor treats it as a guess even when its ID is known.
TALISMAN_LEVELS = {
    "Talisman.AmmoCapacity": ("AmmoCapacity", "AmmoCapacity", (1.2, 1.4, 1.6)),  # Twig of Dark Oak: 60% more ammo
    "Talisman.ArtifactCooldown": ("Cooldown", "ArtifactCooldown", (-0.04, -0.08, -0.14)),  # Essence of Efficiency
    "Talisman.Brawling": ("Sharpness", "Brawling", (0.1, 0.2, 0.35)),  # Fist of Iron: 35% more melee damage
    "Talisman.DoubleDrop": ("Looting", "DoubleDrop", (0.02, 0.04, 0.07)),  # Lucky Clover: 7% chance of more loot
    "Talisman.DropChance": ("DropChance", "DropChance", (0.01, 0.02, 0.04)),  # Looter's Charm
    "Talisman.EmeraldIncrease": ("EmeraldsIncrease", "EmeraldIncrease", (0.1, 0.2, 0.25)),  # Emerald of Good Fortune
    "Talisman.ExperienceIncrease": ("ExperienceIncrease", "ExperienceIncrease", (1.04, 1.06, 1.1)),  # The Eye of Experience
    "Talisman.FiringEmeralds": ("FiringEmerald", "FiringEmerald", (1, 1.75, 2)),  # Thrifty Pendant: up to 200% damage
    "Talisman.Healing": ("Regeneration", "Healing", (0.01, 0.03, 0.05)),  # Healing Heart: 5% health a second
    "Talisman.HealthBoost": ("HealthBoost", "HealthBoost", (1.2, 1.25, 1.35)),  # Sigil of Beeswax: +20 / 25 / 35% max health
    "Talisman.HealthyStrike": ("HealthyStrike", "HealthyStrike", (1, 2, 3)),  # Tendrils of the Sprout: 300% damage
    "Talisman.Plummeting": ("Plummeting", "Plummeting", (1.1, 1.2, 1.35)),  # Ocelot's Paw: 35% more jump-attack damage
    "Talisman.PotionCooldown": ("PotionCooldown", "PotionCooldown", (-0.1, -0.15, -0.25)),  # Glowstone Flask
    "Talisman.RangedBuff": ("Power", "RangedBuff", (0.1, 0.15, 0.25)),  # Amethyst Lens: 25% more ranged damage
    "Talisman.RollingCooldown": ("RollCooldown", "RollingCooldown", (0.2, 0.25, 0.45)),  # Armadillo Amulet
    "Talisman.SoulCapacity": ("SoulMax", "SoulCapacity", (1.15, 1.2, 1.35)),  # Soul Chip: 35% more Soul capacity
    "Talisman.SoulGather": ("SoulGather", "SoulGather", (0.4, 0.8, 1.4)),  # Twisted Tooth: 140% more souls
    "Talisman.SpeedIncrement": ("SpeedIncrement", "SpeedIncrement", (1, 2, 3)),  # Medallion of Momentum
    "Talisman.StatusBuff": ("StatusBuff", "StatusBuff", (1.1, 1.15, 1.25)),  # Sculk Badge: statuses last 25% longer
}
# A companion's talisman has no effect of its own: each level carries a tag instead (SW.Talisman.Wolf.Level.1 to
# .3), and the game does the rest. The Tasty Bone has been seen whole in a real save, and /issues/20, /issues/21
# and /issues/23 list the other four with their tags.
TALISMAN_LEVEL_TAGS = {
    "Talisman.IronGolem": "SW.Talisman.IronGolem.Level",  # Golem Kit
    "Talisman.Llama": "SW.Talisman.Llama.Level",  # Wonderful Wheat
    "Talisman.Prickle": "SW.Talisman.Prickle.Level",  # Prickle's Mark
    "Talisman.Wobble": "SW.Talisman.Wobble.Level",  # Wobblestone
    "Talisman.Wolf": "SW.Talisman.Wolf.Level",  # Tasty Bone
}
# Gear effects (the bonuses the game rolls on weapons, armor and artifacts) as real saves store them: effect ->
# (template, strength at each tier seen). The effect is SW.Effect.<effect>, a tier's template is
# SW.EffectTemplate.<template>.<tier> and the strength is the save's Intensity. Everything here was written by
# the game: the developer's own play, and players' Share item IDs reports.
GEAR_EFFECTS = {
    "ArrowBurst": ("ArrowBurst", {"I": 0.2, "II": 0.25, "III": 0.3}),
    "BeastBoss": ("BeastBoss", {"II": 0.25}),
    "Committed": ("Committed", {"I": 0.2, "II": 0.25, "III": 0.3}),
    "Constitution": ("Constitution", {"I": 0.1, "II": 0.2}),
    "Cooldown": ("Cooldown", {"I": -0.1, "II": -0.15}),
    "CriticalEdge": ("CriticalEdge", {"I": 0.1, "II": 0.2, "III": 0.3}),
    "CriticalHit": ("CriticalHit", {"I": 0.05, "II": 0.1, "III": 0.15}),
    "Deflect": ("Deflect", {"III": 0.2}),
    "Desperation": ("Desperation", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "Duelist": ("Duelist", {"II": 0.25, "III": 0.3}),
    "EagleEye": ("EagleEye", {"II": 0.15}),
    "ElementalProtection": ("ElementalProtection", {"II": -0.15}),
    "EmeraldsIncrease": ("Prospector", {"I": 0.05, "III": 0.15}),
    "Expand": ("Expand", {"I": 0.2}),
    "Finesse": ("Finesse", {"II": 0.25, "III": 0.35}),
    "FireFocus": ("FireFocus", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "FriendsForever": ("FriendsForever", {"I": -0.05, "II": -0.1, "III": -0.15}),
    "Friendship": ("Friendship", {"II": -0.1}),
    "FrostFocus": ("FrostFocus", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "Gambler": ("Gambler", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "HealingFocus": ("HealingFocus", {"I": 0.25, "II": 0.35}),
    "Knockback": ("Knockback", {"I": 0.15, "II": 0.2, "III": 0.3}),
    "LightningFocus": ("LightningFocus", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "Looting": ("Looting", {"I": 0.2, "II": 0.4, "III": 0.6}),
    "Lucky": ("Lucky", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "MasterMarksman": ("MasterMarksman", {"I": 0.15, "II": 0.2, "III": 0.25}),
    "MasterStrike": ("MasterStrike", {"II": 0.2, "III": 0.25}),
    "MultiShot": ("MultiShot", {"I": 0.2}),
    "Opportunist": ("Opportunist", {"I": 0.25, "II": 0.35, "III": 0.5}),
    "Opulence": ("Opulence", {"I": 0.01, "II": 0.02, "III": 0.03}),
    "PoisonFocus": ("PoisonFocus", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "PotionCooldown": ("PotionMaster", {"I": -0.05, "II": -0.1, "III": -0.2}),
    "Power": ("Power", {"I": 0.1, "II": 0.2, "III": 0.3}),
    "Precision": ("Precision", {"I": 0.1}),
    "ProjectileProtection": ("ProjectileProtection", {"I": -0.1, "II": -0.15, "III": -0.2}),
    "Protection": ("Protection", {"I": -0.1, "II": -0.15, "III": -0.2}),
    "RapidStrike": ("RapidStrike", {"III": 0.2}),
    "Reconstruction": ("Reconstruction", {"II": -0.2, "III": -0.25}),
    "Reeling": ("Reeling", {"I": 0.2}),
    "Regeneration": ("Regeneration", {"I": 0.05, "II": 0.075, "III": 0.1}),
    "Resilience": ("Resilience", {"I": -0.2, "II": -0.25, "III": -0.3}),
    "RollCooldown": ("Acrobat", {"I": 0.1, "II": 0.15}),
    "Saboteur": ("Saboteur", {"II": 0.6, "III": 0.8}),
    "ShadowWalk": ("ShadowWalk", {"I": 0.2, "II": 0.25, "III": 0.35}),
    "Sharpness": ("Sharpness", {"I": 0.1, "II": 0.2, "III": 0.3}),
    "Sidestep": ("Sidestep", {"I": 0.1, "III": 0.2}),
    "Sniper": ("Sniper", {"II": 0.5}),
    "SoulFocus": ("SoulFocus", {"I": 0.1, "II": 0.15, "III": 0.2}),
    "SoulGatherMultiply": ("SoulSiphon", {"II": 0.35, "III": 0.45}),
    "SoulMax": ("BagOfSouls", {"I": 1.25, "II": 1.3, "III": 1.35}),
    "SpeedBoost": ("SpeedBoost", {"II": 0.1, "III": 0.15}),
    "Supercharge": ("Supercharge", {"I": 0.3, "II": 0.35, "III": 0.4}),
    "SweepingEdge": ("SweepingEdge", {"II": 0.3}),
    "SwiftSneak": ("SwiftSneak", {"I": 0.15, "II": 0.2}),
    "Thorns": ("Thorns", {"II": 0.65}),
    "Vanguard": ("Vanguard", {"I": 0.2}),
    "Vestige": ("Vestige", {"I": 0.1, "II": 0.15}),
    "Vivify": ("Vivify", {"I": 0.15, "III": 0.5}),
}
# What the game calls an effect, by its template, where there's no doubt: the template is named as MetaBot names
# the effect (or all but), and every strength a save has shown is MetaBot's number for that tier. For these the
# tiers nobody has sent yet are filled in from MetaBot's table, marked as not seen.
# Spiritual is here by another route: MetaBot lists the Soul Chip talisman under it, a save holds the Soul Chip's
# effect as SW.Effect.SoulMax, and SoulMax is the effect the BagOfSouls template gives gear, at Spiritual's 25%.
# Most of the rest are tied by a Unique: MetaBot says which effect each Unique carries, and a save holds that
# Unique's own effect under the same template the game rolls (UNIQUE_EFFECTS: the Sage Tunic carries Bounty
# Hunter, saved as Committed.Unique). A name alone isn't enough: the effect a save calls Constitution is MetaBot's
# Recovery, not its Constitution. Sharpness and Potion Maker are tied by a talisman instead (the Fist of Iron and
# the Glowstone Flask are saved with the same effects). Reaper, Prickly and Sharpshooter are the only effects with
# the numbers saves show for SoulSiphon (35% and 45%), Thorns (65%) and Supercharge (30%, 35% and 40%), and
# Resilience has its own name and all its numbers. Bowyer and Speed are the last effects left for the numbers of
# ArrowBurst (20%, 25%, 30%) and SpeedBoost (10%, 15%) once every other effect with those numbers was tied.
EFFECT_NAMES = {
    "Acrobat": "Acrobat",
    "ArrowBurst": "Bowyer",
    "BagOfSouls": "Spiritual",
    "BeastBoss": "Pack Leader",
    "Committed": "Bounty Hunter",
    "Constitution": "Recovery",
    "Cooldown": "Cooldown",
    "CriticalEdge": "Critical Edge",
    "CriticalHit": "Critical Hit",
    "Deflect": "Deflection",
    "Desperation": "Persistence",
    "Duelist": "Duelist",
    "EagleEye": "Aim",
    "ElementalProtection": "Elemental Protection",
    "Expand": "Totem Radius",
    "Finesse": "Finesse",
    "FireFocus": "Pyromancer",
    "FriendsForever": "Veterinarian",
    "Friendship": "Shepherd",
    "FrostFocus": "Cryomancer",
    "Gambler": "Assassin",
    "HealingFocus": "Healer",
    "Knockback": "Knockback",
    "LightningFocus": "Electromancer",
    "Looting": "Looter",
    "Lucky": "Luck",
    "MasterMarksman": "Marksman",
    "MasterStrike": "Strength",
    "MultiShot": "Ranger",
    "Opportunist": "Bully",
    "Opulence": "Raider",
    "PoisonFocus": "Venomancer",
    "PotionMaster": "Potion Maker",
    "Power": "Impact",
    "Precision": "Precision",
    "ProjectileProtection": "Projectile Protection",
    "Prospector": "Prospector",
    "Protection": "Protection",
    "RapidStrike": "Swiftness",
    "Reconstruction": "Fletcher",
    "Reeling": "Momentum",
    "Regeneration": "Regeneration",
    "Resilience": "Resilience",
    "Saboteur": "Tainted",
    "ShadowWalk": "Stealth",
    "Sharpness": "Sharpness",
    "Sidestep": "Evasion",
    "Sniper": "Sniper",
    "SoulFocus": "Soulmancer",
    "SoulSiphon": "Reaper",
    "SpeedBoost": "Speed",
    "Supercharge": "Sharpshooter",
    "SweepingEdge": "Brawler",
    "SwiftSneak": "Prowler",
    "Thorns": "Prickly",
    "Vanguard": "Vanguard",
    "Vestige": "Sorcerer",
    "Vivify": "Ally",
}
# What the game probably calls these: the meaning and the one strength seen fit, but the names don't match and no
# Unique ties them, so it's shown as a maybe and no tier is filled in from it.
EFFECT_GUESSES: dict[str, str] = {}
# Enchantments as real saves store them: enchantment -> strength at each tier seen. The effect is
# SW.Enchantment.<name>, named like its book (BOOK_IDS), and a tier's template is SW.Enchantment.<name>.<tier>. The
# strength isn't the number the game shows (Ancient Alchemy I is 0.5 and gives 30 souls), so a tier can't be
# worked out: each one has to be seen. ENCHANTMENT_TEMPLATES holds a template a save spells differently from its
# effect: Springload is SW.Enchantment.SpringLoaded, from the template SW.Enchantment.Springloaded.III.
ENCHANTMENT_TEMPLATES = {"SpringLoaded": "Springloaded"}
ENCHANTMENT_TIERS = {
    "Arcane": {"III": 9},
    "Blowback": {"III": 0.5},
    "Borealis": {"III": 0.287547},
    "ExpandedQuiver": {"III": 4},
    "FireAspect": {"III": 1},
    "GravityPulse": {"III": 0},
    "Piercing": {"I": 1, "III": 5},
    "PotionBarrier": {"III": 6},
    "Radiance": {"I": 0.3, "III": 0.5},
    "SoulInfusedPotion": {"I": 0.5, "II": 0.6, "III": 0.85},
    "SpringLoaded": {"III": 6},
    "Swirling": {"III": 1},
    "Unstoppable": {"III": 0.3},
}
# Enchantment points a save has shown for an enchantment on a Unique item (EnchantmentPointsInvested), to check
# MetaBot's cost table against.
SEEN_ENCHANT_POINTS = {("Unique", "I"): 3, ("Unique", "II"): 8, ("Unique", "III"): 15}
# The effect a Unique comes with, as real saves store it: the Unique's ID -> (effect, strength, template), each as
# saved, without the SW. in front. A save holds it as the one effect in a batch of the kind SW.Item.Effect.Static,
# ahead of the effects the game rolls. Most are a gear effect at a tier of its own (SW.EffectTemplate.<name>.Unique)
# with the number the Unique's description gives, the way round that effect's rolled tiers go. A few are
# enchantments under another name, and their numbers follow no rule (the Sculker Claws' 15% chance is saved as
# 0.08), and one has no tier on its template at all (the Lullaby Blade's SoulCurse), so every one is taken from a
# save and none is worked out. From /issues/20, sixty Uniques the game made on a first playthrough, and /issues/21,
# thirty-one more, which showed nine new ones and the same effect for every Unique both lists hold. Both lists were
# made by versions that couldn't write this kind of batch, so every one of them is the game's. A list made with
# 1.10.0 or later can hold the editor's own (/issues/22 does: items its sender had made Unique), so from such a list
# only an effect that version didn't have counts: the Humbler Heartstring's from /issues/22, and twenty-seven from
# /issues/23, which leaves one Unique nobody has sent (the Packleader Paws). Two of those are saved with a template
# spelled SW.Effecttemplate, small t: Protection's Unique tier, on the Monster Masher and the Humbler Antenna.
# /issues/23 also holds three Uniques whose ID its version (1.10.1) hadn't seen, so the editor can't have made them:
# the Alchemist Top Hat, the Woodsprite Crown and the Dreamruler Cover, each with the very effect own_effects() had
# given it from a Unique described in the same words. That rule has now been right every time a save could check it.
UNIQUE_EFFECTS = {
    "Battlestaff_Unique1": ("Effect.ElementalHit", 1, "EffectTemplate.ElementalHit.Unique"),  # Elemental Staff
    "Bow_Unique1": ("Effect.EagleEye", 0.25, "EffectTemplate.EagleEye.Unique"),  # Ranger's Promise
    "CaveCrawlerChest_Unique": ("Effect.Sidestep", 0.2, "EffectTemplate.Sidestep.Unique"),  # Twisted Warden Vest
    "CaveCrawlerLeggings_Unique": ("Effect.ShadowWalk", 0.45, "EffectTemplate.ShadowWalk.Unique"),  # Twisted Warden Tights
    "Claws_Unique1": ("Enchantment.ClawingShadow.Unique", 0.08, "Enchantment.ClawingShadow.Unique"),  # Sculker Claws
    "Cleaver_Unique1": ("Effect.AnimaConduit", 0.07, "EffectTemplate.AnimaConduit.Unique"),  # Cacaphonous Cleaver
    "Crossbow_Unique1": ("Effect.Chains", 0.3, "EffectTemplate.Chains.Unique"),  # The Shackler
    "CurvedGreatsword_Unique1": ("Effect.SoulCurse", 1, "EffectTemplate.SoulCurse"),  # Lullaby Blade
    "CurvedLongsword_Unique1": ("Effect.Duelist", 0.4, "EffectTemplate.Duelist.Unique"),  # Pride of the Plains
    "Dagger_Unique1": ("Effect.SoulFocus", 0.2, "EffectTemplate.SoulFocus.Unique"),  # Sculker's Bane
    "Daggers_Unique1": ("Effect.PoisonFocus", 0.2, "EffectTemplate.PoisonFocus.Unique"),  # Venomous Fangs
    "DiscipleBoots_Unique": ("Effect.RapidStrike", 0.3, "EffectTemplate.RapidStrike.Unique"),  # Sage Wraps
    "DiscipleChest_Unique": ("Effect.Committed", 0.4, "EffectTemplate.Committed.Unique"),  # Sage Tunic
    "DiscipleHelmet_Unique": ("Effect.ProjectileProtection", -0.25, "EffectTemplate.ProjectileProtection.Unique"),  # Sage Headband
    "DiscipleLeggings_Unique": ("Effect.RollCooldown", 0.4, "EffectTemplate.Acrobat.Unique"),  # Sage Belt
    "DualCrossbow_Unique1": ("Enchantment.Dynamo", 0.5, "Enchantment.Dynamo.Unique"),  # Double Crossers
    "EvocationBoots_Unique": ("Effect.SoulMax", 1.5, "EffectTemplate.BagOfSouls.Unique"),  # Alchemist Loafers
    "EvocationChest_Unique": ("Effect.Vestige", 0.25, "EffectTemplate.Vestige.Unique"),  # Alchemist Overcoat
    "EvocationHelmet_Unique": ("Effect.Expand", 0.55, "EffectTemplate.Expand.Unique"),  # Alchemist Top Hat
    "EvocationLeggings_Unique": ("Effect.ArtifactHealing", 0.06, "EffectTemplate.ArtifactHealing.Unique"),  # Alchemist Trousers
    "FrostRimeBoots_Unique": ("Effect.Saboteur", 1, "EffectTemplate.Saboteur.Unique"),  # Rimefrost Plodders
    "FrostRimeHelmet_Unique": ("Effect.FrostFocus", 0.3, "EffectTemplate.FrostFocus.Unique"),  # Rimefrost Icecap
    "FrostRimeLeggings_Unique": ("Effect.SweepingEdge", 0.5, "EffectTemplate.SweepingEdge.Unique"),  # Rimefrost Longjohns
    "Gauntlet_Unique1": ("Enchantment.MaulerDive", 1, "Enchantment.MaulerDive"),  # Prime Enchanter's Gauntlets
    "GiantClub_Unique1": ("Enchantment.FireAspect", 1, "Enchantment.FlameBelch.Unique"),  # Redstone Wrecker
    "GiantMallet_Unique1": ("Effect.Protection", -0.25, "Effecttemplate.Protection.Unique"),  # Monster Masher
    "Glaive_Unique1": ("Effect.Vanguard", 0.6, "EffectTemplate.Vanguard.Unique"),  # Golden Glaive
    "GreatAxe_Unique1": ("Effect.StatusOnHit.Strength", 0.06, "EffectTemplate.StrenghteningStrike.Unique"),  # Awesomeaxe
    "Greatbow_Unique1": ("Enchantment.Piercing", 10, "Enchantment.Piercing.Unique"),  # Humbler Heartstring
    "Greatsword_Unique1": ("Enchantment.GravityPulse", 0, "Enchantment.GravityPulse.Unique"),  # The Darkshard
    "Hammer_Unique1": ("Effect.Opulence", 0.05, "EffectTemplate.Opulence.Unique"),  # Emerald Hammer
    "HeavyCrossbow_Unique1": ("Effect.PointBlank", 1, "EffectTemplate.PointBlank.Unique"),  # The Close Ranger
    "HewnBarkBoots_Unique": ("Effect.Reconstruction", -0.35, "EffectTemplate.Reconstruction.Unique"),  # Woodsprite Root Boots
    "HewnBarkChest_Unique": ("Effect.HealthBoost", 1.3, "EffectTemplate.HealthBoost.Unique"),  # Woodsprite Barkpiece
    "HewnBarkHelmet_Unique": ("Effect.Friendship", -0.2, "EffectTemplate.Friendship.Unique"),  # Woodsprite Crown
    "HewnBarkLeggings_Unique": ("Effect.Thorns", 1, "EffectTemplate.Thorns.Unique"),  # Woodsprite Trunks
    "HoneyChest_Unique": ("Effect.HealingFocus", 0.5, "EffectTemplate.HealingFocus.Unique"),  # Hivemind Thorax
    "HoneyHelmet_Unique": ("Effect.Vivify", 0.7, "EffectTemplate.Vivify.Unique"),  # Hivemind Hardhat
    "HoneyLeggings_Unique": ("Effect.Resilience", -0.5, "EffectTemplate.Resilience.Unique"),  # Hivemind Trousers
    "Longbow_Unique1": ("Effect.Sniper", 1, "EffectTemplate.Sniper.Unique"),  # Creaking's Reach
    "Mace_Unique1": ("Effect.Finesse", 0.35, "EffectTemplate.Finesse.Unique"),  # Carapace Mace
    "MoonSword_Unique1": ("Effect.Reeling", 0.6, "EffectTemplate.Reeling.Unique"),  # Lunar Sickle
    "MushroomBoots_Unique": ("Effect.Friendship", -0.2, "EffectTemplate.Friendship.Unique"),  # Fly Agaric Galoshes
    "MushroomChest_Unique": ("Effect.Regeneration", 0.15, "EffectTemplate.Regeneration.Unique"),  # Fly Agaric Coat
    "MushroomLeggings_Unique": ("Effect.BeastBoss", 0.4, "EffectTemplate.BeastBoss.Unique"),  # Fly Agaric Trousers
    "MysticChest_Unique": ("Effect.Saboteur", 1, "EffectTemplate.Saboteur.Unique"),  # Oracle Mantle
    "MysticHelmet_Unique": ("Effect.LightningFocus", 0.25, "EffectTemplate.LightningFocus.Unique"),  # Oracle Crown
    "MysticLeggings_Unique": ("Effect.Cooldown", -0.3, "EffectTemplate.Cooldown.Unique"),  # Oracle Tights
    "PhantomChest_Unique": ("Effect.Duelist", 0.4, "EffectTemplate.Duelist.Unique"),  # Dreamruler Cover
    "PhantomHelmet_Unique": ("Effect.SoulGatherMultiply", 0.6, "EffectTemplate.SoulSiphon.Unique"),  # Dreamruler Crown
    "PhantomLeggings_Unique": ("Effect.SwiftSneak", 0.4, "EffectTemplate.SwiftSneak.Unique"),  # Dreamruler Pyjamas
    "Pickaxe_Unique1": ("Effect.EmeraldsIncrease", 0.2, "EffectTemplate.Prospector.Unique"),  # The Prospector's Pick
    "Pike_Unique1": ("Effect.LightningFocus", 0.25, "EffectTemplate.LightningFocus.Unique"),  # Stormcaller
    "Powerbow_Unique1": ("Effect.Power", 0.3, "EffectTemplate.Power.Unique"),  # Paragon
    "RapidCrossbow_Unique1": ("Effect.Hairtrigger", 0.4, "EffectTemplate.Hairtrigger.Unique"),  # The Cross Pollinator
    "Rapier_Unique1": ("Effect.RapidStrike", 0.3, "EffectTemplate.RapidStrike.Unique"),  # The Thousand Cuts
    "RealmreacherBoots_Unique": ("Effect.AmmoCapacity", 1.45, "EffectTemplate.AmmoCapacity.Unique"),  # Sharpshooter Spurs
    "RealmreacherChest_Unique": ("Effect.Power", 0.3, "EffectTemplate.Power.Unique"),  # Sharpshooter Duster
    "RedstoneBoots_Unique": ("Effect.MasterStrike", 0.45, "EffectTemplate.MasterStrike.Unique"),  # Monstrosity Stompers
    "RedstoneChest_Unique": ("Effect.ArtifactHealing", 0.06, "EffectTemplate.ArtifactHealing.Unique"),  # Monstrosity Armor
    "RedstoneLeggings_Unique": ("Effect.ElementalProtection", -0.25, "EffectTemplate.ElementalProtection.Unique"),  # Monstrosity Greaves
    "Sabre_Unique1": ("Effect.RollCooldown", 0.4, "EffectTemplate.Acrobat.Unique"),  # Rascal's Razor
    "ScampHelmet_Unique": ("Effect.Gambler", 0.25, "EffectTemplate.Gambler.Unique"),  # Scoundrel Cowl
    "ScampLeggings_Unique": ("Effect.Hairtrigger", 0.4, "EffectTemplate.Hairtrigger.Unique"),  # Scoundrel Chaps
    "ScatterCrossbow_Unique1": ("Effect.MultiShot", 0.6, "EffectTemplate.MultiShot.Unique"),  # Harp Crossbow
    "ScavengerBoots_Unique": ("Effect.Opportunist", 0.5, "EffectTemplate.Opportunist.Unique"),  # Monarch Talons
    "ScavengerChest_Unique": ("Effect.Resilience", -0.5, "EffectTemplate.Resilience.Unique"),  # Monarch Mantle
    "ScavengerHelmet_Unique": ("Effect.Looting", 0.8, "EffectTemplate.Looting.Unique"),  # Monarch Crown
    "ScavengerLeggings_Unique": ("Effect.SoulMax", 1.5, "EffectTemplate.BagOfSouls.Unique"),  # Monarch Sash
    "Scythe_Unique1": ("Effect.SoulGatherMultiply", 0.6, "EffectTemplate.SoulSiphon.Unique"),  # Soul Reaper
    "ShortSpear_Unique1": ("Enchantment.PhantomLance", 1, "Enchantment.PhantomLance"),  # Spectral Spear
    "Shortbow_Unique1": ("Effect.Sidestep", 0.2, "EffectTemplate.Sidestep.Unique"),  # Shooting Star
    "Shovel_Unique1": ("Enchantment.Shockwave", 1, "Enchantment.Shockwave.Unique"),  # Diamond Shovel
    "Sickles_Unique1": ("Effect.HealingFocus", 0.5, "EffectTemplate.HealingFocus.Unique"),  # Sift Sickles
    "StalwartBoots_Unique": ("Effect.Sidestep", 0.2, "EffectTemplate.Sidestep.Unique"),  # Humbler Tarsi
    "StalwartChest_Unique": ("Effect.Constitution", 0.4, "EffectTemplate.Constitution.Unique"),  # Humbler Carapace
    "StalwartHelmet_Unique": ("Effect.Protection", -0.25, "Effecttemplate.Protection.Unique"),  # Humbler Antenna
    "StalwartLeggings_Unique": ("Effect.SweepingEdge", 0.5, "EffectTemplate.SweepingEdge.Unique"),  # Humbler Greaves
    "Sword_Unique1": ("Effect.FireFocus", 0.2, "EffectTemplate.FireFocus.Unique"),  # The Burning Blade
    "TimewornBoots_Unique": ("Effect.EagleEye", 0.25, "EffectTemplate.EagleEye.Unique"),  # Soul Corruptor Sandals
    "TimewornChest_Unique": ("Effect.Expand", 0.55, "EffectTemplate.Expand.Unique"),  # Soul Corruptor Duster
    "TimewornHelmet_Unique": ("Effect.Supercharge", 0.6, "EffectTemplate.Supercharge.Unique"),  # Soul Corruptor Mask
    "TimewornLeggings_Unique": ("Effect.MasterMarksman", 0.45, "EffectTemplate.MasterMarksman.Unique"),  # Soul Corruptor Sash
    "Trickbow_Unique1": ("Effect.Jumpshot", 0.06, "EffectTemplate.Jumpshot.Unique"),  # Phantom Wing
    "UndauntedHelmet_Unique": ("Effect.Knockback", 0.4, "EffectTemplate.Knockback.Unique"),  # Dauntless Horns
    "UndauntedLeggings_Unique": ("Effect.Vanguard", 0.6, "EffectTemplate.Vanguard.Unique"),  # Dauntless Greaves
    "VoyagerBoots_Unique": ("Effect.Desperation", 0.25, "EffectTemplate.Desperation.Unique"),  # Rover Sabatons
    "VoyagerChest_Unique": ("Effect.Deflect", 0.25, "EffectTemplate.Deflect.Unique"),  # Rover Pauldrons
    "VoyagerHelmet_Unique": ("Effect.Precision", 0.25, "EffectTemplate.Precision.Unique"),  # Rover Visor
    "VoyagerLeggings_Unique": ("Effect.Reeling", 0.6, "EffectTemplate.Reeling.Unique"),  # Rover Gaiters
    "WarHammer_Unique1": ("Effect.ExplosiveStrike", 1, "EffectTemplate.ExplosiveStrike.Unique"),  # Heartbreaker
    "WellspringChest_Unique": ("Effect.Vestige", 0.25, "EffectTemplate.Vestige.Unique"),  # Mad Sifter Vest
    "WellspringHelmet_Unique": ("Effect.Saboteur", 1, "EffectTemplate.Saboteur.Unique"),  # Mad Sifter Mask
    "WellspringLeggings_Unique": ("Effect.StatusBuff", 1.2, "EffectTemplate.StatusBuff.Unique"),  # Mad Sifter Slacks
    "WolfclutchChest_Unique": ("Effect.BeastBoss", 0.4, "EffectTemplate.BeastBoss.Unique"),  # Packleader Hide
    "WolfclutchLeggings_Unique": ("Effect.FriendsForever", -0.2, "EffectTemplate.FriendsForever.Unique"),  # Packleader Fur Chaps
}
TIERS = ("I", "II", "III")
POOLS = re.compile(r"All gear|Any (?:weapon|armor|artifact)|[A-Z][a-z]+ gear|Fixed only")  # where an effect rolls
# Armor slots as MetaBot names them, as the editor names them, and as armor IDs spell them.
SLOTS = {"Helmet": "Helmet", "Chest": "Chestplate", "Leggings": "Leggings", "Boots": "Boots"}
SLOT_WORDS = {"Helmet": "Helmet", "Chestplate": "Chest", "Leggings": "Leggings", "Boots": "Boots"}
RANGED_TYPES = {"Bow", "Crossbow"}
ENCHANT_SLOTS = {"Melee": "Melee", "Ranged": "Ranged", "Armor": "Armor", "Chest": "Chestplate"}
# In saves, but nobody has said what the game calls them (a name here would come from the ID).
EXTRA: list[dict] = []


class Tables(HTMLParser):
    """Collects the text of every table on a page: tables -> rows -> cells."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif self._cell is not None and tag in ("div", "p", "li", "br", "a"):
            self._cell.append(" ")  # keep "Melee" and "Ranged" in separate boxes apart

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row and self.tables:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def fetch(page: str) -> str:
    request = urllib.request.Request(BASE_URL + page, headers=HEADERS)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8")
        except OSError:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"metabot.gg didn't answer for {page}")


def fetch_tables(page: str) -> list[list[list[str]]]:
    return tables_in(fetch(page))


def tables_in(page_html: str) -> list[list[list[str]]]:
    parser = Tables()
    parser.feed(page_html)
    return parser.tables


def rows(tables: list[list[list[str]]], *headers: str) -> list[dict[str, str]]:
    """The rows of the first table whose header row starts with ``headers``, keyed by header."""
    for table in tables:
        names = [cell.upper() for cell in table[0]] if table else []
        if names[: len(headers)] == list(headers):
            return [dict(zip(names, row)) for row in table[1:] if len(row) == len(names)]
    raise RuntimeError(f"no table headed {headers}")


def all_rows(tables: list[list[list[str]]], *headers: str) -> list[dict[str, str]]:
    """The rows of every table whose header row starts with ``headers``."""
    found = []
    for table in tables:
        names = [cell.upper() for cell in table[0]] if table else []
        if names[: len(headers)] == list(headers):
            found += [dict(zip(names, row)) for row in table[1:] if len(row) == len(names)]
    return found


def spaced(name: str) -> str:
    """'BagOfSouls' -> 'Bag Of Souls': a name for an effect nobody has named, from its ID."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def percent(cell: str) -> float | None:
    """'7.5%' -> 7.5; None for a tier the effect doesn't have ('—')."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)%", cell.strip())
    return float(match.group(1)) if match else None


def strength_like(seen: float, shown: float) -> str:
    """How a save's strength relates to the number the game shows: 0.2 for 20% ("plain"), -0.1 for 10% less
    ("less"), or 1.25 for 25% more ("times")."""
    for way, value in (("plain", shown / 100), ("less", -shown / 100), ("times", 1 + shown / 100)):
        if abs(seen - value) < 1e-9:
            return way
    return ""


def as_strength(way: str, shown: float) -> float:
    return round({"plain": shown / 100, "less": -shown / 100, "times": 1 + shown / 100}[way], 6)


def slug(name: str) -> str:
    """'Critical Edge' -> 'critical-edge', as in the address of the effect's own page."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def gear_effects(table: list[dict[str, str]], wording: dict[str, dict[str, str]]) -> list[dict]:
    """GEAR_EFFECTS as the editor's list: each effect with its tiers. A named effect also gets the tiers nobody
    has seen yet, from MetaBot's numbers, as long as every tier that has been seen agrees with them, and the
    game's own wording for each tier (``wording``: effect name -> tier -> sentence)."""
    by_name = {row["EFFECT"]: row for row in table}
    made = []
    for effect, (template, seen) in sorted(GEAR_EFFECTS.items()):
        name = EFFECT_NAMES.get(template)
        entry = {"effect": f"SW.Effect.{effect}", "template": f"SW.EffectTemplate.{template}", "name": name or spaced(template)}
        tiers = [{"tier": tier, "strength": seen[tier], "seen": True} for tier in TIERS if tier in seen]
        if name is None:
            entry["name_from_id"] = True
            if template in EFFECT_GUESSES:
                entry["maybe"] = EFFECT_GUESSES[template]
        elif name not in by_name:
            raise SystemExit(f"{name} isn't in MetaBot's effects table any more")
        else:
            row = by_name[name]
            ways = {strength_like(strength, percent(row[tier]) or 0) for tier, strength in seen.items()}
            if len(ways) != 1 or "" in ways:
                raise SystemExit(f"{effect}: saves hold {seen}, which doesn't fit MetaBot's {[row[tier] for tier in TIERS]}")
            way = ways.pop()
            tiers = []
            for tier in TIERS:
                shown = percent(row[tier])
                if shown is None:
                    continue
                sentence = wording.get(name, {}).get(tier, "")
                # MetaBot gives a tier's number twice: in its table, and in the game's wording for the tier. A tier
                # nobody has seen saved is only taken when the two agree (Critical Edge III: 30% and "40% more").
                agrees = bool(re.search(rf"(?<![\d.]){re.escape(f'{shown:g}')}(?![\d.])", sentence))
                if tier not in seen and not agrees:
                    print(f"warning: {name} {tier} is {row[tier]} in MetaBot's table, but its wording is {sentence!r}; left out until a save shows it")
                    continue
                tiers.append({"tier": tier, "strength": as_strength(way, shown), "shown": row[tier], "seen": tier in seen, **({"text": sentence} if agrees else {})})
            entry["category"] = row["CATEGORY"]
            entry["rolls_on"] = ", ".join(POOLS.findall(row["ROLLS ON"]))
            entry["page"] = f"{BASE_URL}effects/{slug(name)}"
        entry["tiers"] = tiers
        made.append(entry)
    return made


def tagged(cell: str) -> list[str]:
    """'RangerSummoner' -> ['Ranger', 'Summoner']: the archetypes in one of MetaBot's cells, in the editor's order."""
    return [archetype for archetype in ARCHETYPES if archetype in cell]


def archetypes(pages: dict[str, list], builds: dict[str, list], effects: list[dict[str, str]]) -> dict[str, list[str]]:
    """Every weapon's, armor piece's and artifact's archetypes, by the item's name (a Unique has its own).

    Three of MetaBot's tables give them outright. A ranged weapon's are only on the archetypes' own pages, which
    list every item with that tag; those pages also repeat the melee weapons, the artifacts and each archetype's
    pool of effects, so everything they repeat is checked against the tables it came from."""
    found: dict[str, list[str]] = {}
    for row in rows(pages["armor"], "ARMOR PIECE", "SLOT", "WEIGHT", "ARCHETYPE"):
        found[row["ARMOR PIECE"]] = tagged(row["ARCHETYPE"])
    for row in rows(pages["weapons"], "WEAPON", "WEIGHT", "ARCHETYPE"):
        found[row["WEAPON"]] = tagged(row["ARCHETYPE"])
    for row in rows(pages["artifacts"], "ARTIFACT", "TYPE"):
        found[row["ARTIFACT"]] = tagged(row["ARCHETYPE"])
    listed: dict[str, list[str]] = {}
    ranged: dict[str, list[str]] = {}
    for archetype, tables in builds.items():
        for row in all_rows(tables, "WEAPON", "CLASS", "DPS"):
            listed.setdefault(row["WEAPON"], []).append(archetype)
        for row in all_rows(tables, "ARTIFACT", "COOLDOWN"):  # the Ranger page has no artifacts
            listed.setdefault(row["ARTIFACT"], []).append(archetype)
        for row in all_rows(tables, "WEAPON", "TYPE", "BURST DPS"):
            ranged.setdefault(row["WEAPON"], []).append(archetype)
        pool = sorted(row["EFFECT"] for row in rows(tables, "EFFECT", "CATEGORY", "I", "II", "III"))
        table = sorted(row["EFFECT"] for row in effects if f"{archetype} gear" in row["ROLLS ON"])
        if pool != table:
            raise SystemExit(f"MetaBot's {archetype} page lists the effects {pool}, but its effects table puts {table} on {archetype} gear")
    for name, tags in listed.items():
        if found.get(name) != tags:
            raise SystemExit(f"MetaBot's build pages tag the {name} {tags}, but its own table says {found.get(name)}")
    for name, tags in ranged.items():
        if name in found:
            raise SystemExit(f"{name} is in MetaBot's tables as a ranged weapon and as something else")
        found[name] = tags
    return found


def own_effects(items: dict[str, dict]) -> None:
    """Check the Uniques' own effects against MetaBot's words for them, and give a Unique nobody has seen the
    effect of one that does the same thing.

    MetaBot describes several Uniques in the very same words (the Slaymore and the Humbler Greaves: "Melee
    attacks deal 50% more damage to secondary targets."), and wherever saves have shown two such Uniques, a
    weapon and an armor piece as often as not, they hold the very same effect. So a Unique that hasn't been
    seen takes the effect of a seen one with the same words, marked as not seen itself."""
    uniques = [item for item in items.values() if item.get("unique")]
    listed = {(item["id"] + ("_Unique" if item["kind"] == "Armor" else "_Unique1"))[len(PREFIX):] for item in uniques}
    for name in sorted(set(UNIQUE_EFFECTS) - listed):
        print(f"warning: {name} has its own effect listed, but no item in the list has a Unique with that ID")
    for name in sorted(set(UNIQUE_EFFECTS) - {unique[len(PREFIX):] for unique in UNIQUE_IDS}):
        raise SystemExit(f"{name} has its own effect listed, so it was seen in a save: add it to UNIQUE_IDS")
    by_words: dict[str, dict] = {}
    for item in uniques:
        own, words = item.get("unique_own"), item.get("unique_effect", "")
        if own is None:
            continue
        other = by_words.setdefault(words, item)
        if other["unique_own"] != own:
            raise SystemExit(f"{item['unique']} and {other['unique']} are described the same ({words!r}) but saved differently")
        # A gear effect's number is the one in the description: 0.2 for 20%, -0.3 for "30% less", 1.5 for "50% more".
        numbers = re.findall(r"(\d+(?:\.\d+)?)%", words)
        if own["effect"].startswith("SW.Effect.") and len(numbers) == 1 and not strength_like(own["strength"], float(numbers[0])):
            print(f"warning: {item['unique']} is saved with {own['strength']}, and described as {words!r}")
    for item in uniques:
        twin = by_words.get(item.get("unique_effect", ""))
        if "unique_own" not in item and twin is not None:
            item["unique_own"] = {**twin["unique_own"], "seen": False, "like": twin["unique"]}


def pascal(name: str) -> str:
    return "".join(word[0].upper() + word[1:] for word in re.findall(r"[A-Za-z0-9]+", name.replace("'", "")))


def entry(name: str, kind: str, item_id: str, unique_suffix: str = "", **extra: str) -> dict:
    if name in KNOWN_IDS:
        item_id = PREFIX + KNOWN_IDS[name]
    item_id = EXACT_IDS.get(name, item_id)
    made = {"name": name, "kind": kind, "id": item_id, "confirmed": item_id in CONFIRMED_IDS, **{k: v for k, v in extra.items() if v}}
    if unique_suffix and item_id + unique_suffix in UNIQUE_IDS:
        made["unique_id"] = item_id + unique_suffix
    own = UNIQUE_EFFECTS.get((item_id + unique_suffix)[len(PREFIX):]) if unique_suffix else None
    if own is not None:
        made["unique_own"] = {"effect": f"SW.{own[0]}", "strength": own[1], "template": f"SW.{own[2]}", "seen": True}
    if item_id[len(PREFIX):] in TALISMAN_LEVELS:
        effect, template, strengths = TALISMAN_LEVELS[item_id[len(PREFIX):]]
        made["levels"] = [
            {"effect": f"SW.Effect.{effect}", "intensity": strength, "template": f"SW.EffectTemplate.{template}.{numeral}"}
            for numeral, strength in zip(TIERS, strengths)
        ]
    if item_id[len(PREFIX):] in TALISMAN_LEVEL_TAGS:
        made["levels"] = [{"tags": [f"{TALISMAN_LEVEL_TAGS[item_id[len(PREFIX):]]}.{level}"]} for level in (1, 2, 3)]
    return made


def main() -> None:
    pages, texts = {}, {}
    for page in PAGES:
        texts[page] = fetch(page)
        pages[page] = tables_in(texts[page])
        time.sleep(1)  # be gentle
    builds = {}
    for archetype, page in BUILD_PAGES.items():
        builds[archetype] = fetch_tables(page)
        time.sleep(1)

    items: dict[str, dict] = {}
    for row in rows(pages["uniques"], "ITEM", "TYPE", "BASE ITEM", "EFFECT"):
        unique, kind, base, effect = row["ITEM"], row["TYPE"], row["BASE ITEM"], row["EFFECT"]
        if kind in SLOTS:
            slot = SLOTS[kind]
            armor_set = base.rsplit(" ", 1)[0]  # "Sculk Digger Hood" is in the Sculk Digger set
            item_id = f"{PREFIX}{pascal(SET_NAMES.get(armor_set, armor_set))}{SLOT_WORDS[slot]}"
            items[base] = entry(base, "Armor", item_id, "_Unique", slot=slot, set=armor_set, unique=unique, unique_effect=effect)
        else:
            weapon = "Ranged" if kind in RANGED_TYPES else "Melee"
            items[base] = entry(base, weapon, PREFIX + pascal(base), "_Unique1", unique=unique, unique_effect=effect)
    for row in rows(pages["artifacts"], "ARTIFACT", "TYPE"):
        name = row["ARTIFACT"]
        items.setdefault(name, entry(name, "Artifact", f"{PREFIX}Artifact.{pascal(name)}", element=row["ELEMENT"] if row["ELEMENT"] in ELEMENTS else ""))
    for row in rows(pages["talismans"], "TALISMAN", "EFFECT AT LEVEL 3"):
        name, effect = row["TALISMAN"], row["EFFECT AT LEVEL 3"]
        items.setdefault(name, entry(name, "Talisman", f"{PREFIX}Talisman.{pascal(name)}", effect="" if effect == "—" else effect))
    for extra in EXTRA:
        items.setdefault(extra["name"], entry(extra["name"], extra["kind"], extra["id"], slot=extra.get("slot", ""), name_from_id=True))
    own_effects(items)
    tags = archetypes(pages, builds, rows(pages["effects"], "EFFECT", "CATEGORY", "ROLLS ON", "I", "II", "III"))
    for item in items.values():
        if item["kind"] not in ("Melee", "Ranged", "Armor", "Artifact"):
            continue
        for key, name in (("tags", item["name"]), ("unique_tags", item.get("unique"))):
            if name and tags.get(name):
                item[key] = tags[name]
            elif name and name not in tags and item["kind"] != "Artifact":  # MetaBot gives a few artifacts no archetype
                print(f"warning: MetaBot gives the {name} no archetype, so only the effects any {item['kind'].lower()} item rolls are known for it")

    guide = pages["guides/enchanting-guide"]
    by_level = {row["ENCHANTMENT"]: row for row in all_rows(guide, "ENCHANTMENT", "EFFECT", "I / II / III")}
    enchantments = [
        {
            "name": row["ENCHANTMENT"],
            "slots": [ENCHANT_SLOTS[word] for word in re.findall("|".join(ENCHANT_SLOTS), row["SLOT"])],  # "MeleeRanged"
            "category": row["CATEGORY"],
            "triggers": row["TRIGGERS ON"],
            "book": row.get("BOOK DROPS IN", ""),
            "tier3": row["AT TIER III"],
            **({"what": by_level[row["ENCHANTMENT"]]["EFFECT"], "levels": by_level[row["ENCHANTMENT"]]["I / II / III"]} if row["ENCHANTMENT"] in by_level else {}),
        }
        for row in rows(pages["enchantments"], "ENCHANTMENT", "SLOT", "CATEGORY")
    ]
    for name in sorted(set(by_level) - {enchantment["name"] for enchantment in enchantments}):
        print(f"warning: MetaBot's enchanting guide lists {name}, but its enchantments page doesn't")

    # Effects and enchantments the editor can write: only as real saves hold them.
    names_by_book = {book_id: name for name, book_id in BOOK_IDS.items()}
    enchantment_tiers = [
        {
            "effect": f"SW.Enchantment.{enchantment}",
            **({"template": f"SW.Enchantment.{ENCHANTMENT_TEMPLATES[enchantment]}"} if enchantment in ENCHANTMENT_TEMPLATES else {}),
            "name": names_by_book.get(enchantment, spaced(enchantment)),
            **({} if enchantment in names_by_book else {"name_from_id": True}),
            "tiers": [{"tier": tier, "strength": seen[tier], "seen": True} for tier in TIERS if tier in seen],
        }
        for enchantment, seen in sorted(ENCHANTMENT_TIERS.items())
    ]
    costs = {
        row["ITEM RARITY"]: [int(row[column]) for column in ("LEVEL I", "LEVEL II (TOTAL)", "LEVEL III (TOTAL)")]
        for row in rows(guide, "ITEM RARITY", "LEVEL I", "LEVEL II (TOTAL)", "LEVEL III (TOTAL)")
    }
    for (rarity, tier), points in SEEN_ENCHANT_POINTS.items():
        if costs[rarity][TIERS.index(tier)] != points:
            raise SystemExit(f"a save holds {points} points for a tier {tier} enchantment on a {rarity} item; MetaBot's table says {costs[rarity]}")
    talisman_xp = [int(row["XP TO NEXT LEVEL"].replace(",", "")) for row in rows(pages["talismans"], "LEVEL", "XP TO NEXT LEVEL")[:2]]
    cap = re.search(r"caps an item at (\d+) effects", texts["effects"])
    if cap is None:
        raise SystemExit("MetaBot's effects page no longer says how many effects an item can have")
    wording = {}
    for name in sorted(set(EFFECT_NAMES.values())):  # each named effect's own page has the game's wording for its tiers
        wording[name] = {row["TIER"]: row["EFFECT"] for row in rows(fetch_tables(f"effects/{slug(name)}"), "TIER", "VALUE", "EFFECT")}
        time.sleep(1)
    effects = gear_effects(rows(pages["effects"], "EFFECT", "CATEGORY", "ROLLS ON", "I", "II", "III"), wording)
    books = [
        {"name": name, "kind": BOOK, "id": f"{PREFIX}EnchantmentBook.{BOOK_IDS[name]}", "confirmed": True}
        for name in sorted(BOOK_IDS)
    ]
    for book in books:
        if book["name"] not in {enchantment["name"] for enchantment in enchantments}:
            print(f"warning: {book['name']} has a book in saves but isn't one of MetaBot's enchantments")

    catalog = sorted(items.values(), key=lambda e: (e["kind"], e["name"].lower())) + books
    by_id: dict[str, list[str]] = {}
    for item in catalog:
        by_id.setdefault(item["id"], []).append(item["name"])
    for item_id, same in by_id.items():
        if len(same) > 1:
            print(f"warning: {' and '.join(same)} would share the ID {item_id}; the editor offers only the first")
    for item_id in sorted(PREFIX + name for name in TALISMAN_LEVELS):
        if not any(item["id"] == item_id and "levels" in item for item in catalog):
            print(f"warning: {item_id} has its levels listed, but no talisman in the list has that ID")
    for item_id in sorted(CONFIRMED_IDS - set(by_id)):
        print(f"warning: {item_id} was seen in a save, but no item in the list has it")
    for item_id in sorted(UNIQUE_IDS - {item.get("unique_id") for item in catalog}):
        print(f"warning: {item_id} was seen in a save, but no item in the list has a Unique with that ID")
    sources = {page: BASE_URL + page for page in PAGES}
    DATA.mkdir(parents=True, exist_ok=True)
    item_sources = [sources[page] for page in ("uniques", "artifacts", "talismans", "weapons", "armor")] + [BASE_URL + "builds"]
    (DATA / "items.json").write_text(json.dumps({"sources": item_sources, "items": catalog}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA / "enchantments.json").write_text(
        json.dumps(
            {"sources": [sources["enchantments"], sources["guides/enchanting-guide"]], "enchantments": sorted(enchantments, key=lambda e: e["name"])},
            indent=1, ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    (DATA / "effects.json").write_text(
        json.dumps(
            {
                "sources": [sources["effects"], sources["guides/enchanting-guide"], sources["talismans"]],
                "max_effects": int(cap.group(1)),  # "The game caps an item at 4 effects."
                "enchant_points": costs,  # enchantment points in an enchantment, by the item's rarity, at tiers I to III
                "talisman_xp": talisman_xp,  # XP a talisman needs for level 2, then for level 3
                "effects": effects,
                "enchantments": enchantment_tiers,
            },
            indent=1, ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    counts = {kind: sum(item["kind"] == kind for item in catalog) for kind in sorted({item["kind"] for item in catalog})}
    print(f"{len(catalog)} items ({sum(item['confirmed'] for item in catalog)} confirmed IDs, {sum('unique' in item for item in catalog)} with a Unique, "
          f"{sum('unique_id' in item for item in catalog)} of those with the Unique's own ID), {len(enchantments)} enchantments -> {DATA}\n{counts}")
    owned = [item["unique_own"] for item in catalog if "unique_own" in item]
    print(f"{len(owned)} Uniques with the effect of their own ({sum(own['seen'] for own in owned)} seen in saves, the rest like one that was)")
    print(f"{len(effects)} gear effects ({sum(len(effect['tiers']) for effect in effects)} tiers, "
          f"{sum(tier['seen'] for effect in effects for tier in effect['tiers'])} of them seen in saves) and "
          f"{len(enchantment_tiers)} enchantments ({sum(len(e['tiers']) for e in enchantment_tiers)} tiers) the editor can write")


if __name__ == "__main__":
    main()
