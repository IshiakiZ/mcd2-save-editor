"""Ready-made changes ("presets") for a hero, from what's known about the game.

The game keeps its real number tables (loot odds, XP curve, item stats) in
encrypted files, so nothing here is calculated from them. The numbers, the gear
rankings and the kits come from MetaBot.GG's database and guides, which are built
from the game files (build 1.1.1.0) and may be reused with a link to the page the
data came from; every preset links its pages.

A preset can set stats, upgrade the gear you own, add items and equip them.
Items whose save ID is only a best guess are added only when asked to (see
hero.build_catalog). A kit's weapons and armor also get an enchantment each,
once the hero has opened the Enchantsmith in the game, and the gear it adds
gets the effects the game would roll for it. The editor can only write an
enchantment or an effect it has seen in a real save (hero.effect_choices),
so a kit names its picks best first and takes the first one that can be
written. Where it can't write any of them (or the build names none for that
piece), the piece gets the editor's own pick for its kind of gear instead,
and the kit adds the books of the enchantments the build names, so the
Enchantsmith offers those in the game.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hero import (
    BOOK_KIND,
    GEAR_SLOTS,
    NO_RARITY,
    STAT_CAPS,
    TIERS,
    CatalogItem,
    EffectChoice,
    Enchantment,
    GearSlot,
    Hero,
    Item,
    archetypes,
    attribute_label,
    effect_choices,
    enchantments,
    format_amount,
    item_group,
    slots_for,
    template_for,
)
from .icons import ALIASES, normalize

METABOT = "https://metabot.gg/en/minecraft-dungeons-2/"
METABOT_TALISMANS = METABOT + "talismans"
METABOT_UNIQUES = METABOT + "guides/unique-items-farming"
METABOT_BEGINNER = METABOT + "guides/beginners-guide"
METABOT_PROGRESSION = METABOT + "progression"
METABOT_TIERS = METABOT + "tier-list"
METABOT_BUILDS = METABOT + "guides/best-builds"
METABOT_ENCHANTING = METABOT + "guides/enchanting-guide"
METABOT_ENCHANTMENTS = METABOT + "enchantments"
METABOT_EFFECTS = METABOT + "effects"
METABOT_MERCHANTS = METABOT + "merchants"
# Where the secret talismans are hidden: a link only, since Maxroll's terms don't allow reusing its guides in software.
MAXROLL_SECRETS = "https://maxroll.gg/minecraft-dungeons-2/guides/secret-talisman-locations-in-minecraft-dungeons-2"

GOALS, BEST_GEAR, KITS = "Goals", "Most powerful gear", "Kits"
GROUPS = (GOALS, BEST_GEAR, KITS)
TALISMAN_RARITY = NO_RARITY  # a talisman has no rarity (the game saves SW.Rarity.None) and no power
TOP_ARTIFACT_RARITY = "Special"  # artifacts don't come in Unique
# Effects the game rolls on an item it drops, by rarity (a Unique gets one, next to the effect of its own).
ROLLED_EFFECTS = {"Rare": 1, "Special": 2, "Unique": 1}


@dataclass(frozen=True)
class KitItem:
    name: str  # in-game name (a base item; at Unique rarity it becomes its Unique)
    kind: str
    why: str
    where: str = ""
    rarity: str | None = None  # always this rarity; None: the rarity picked in the window
    enchants: tuple[str, ...] = ()  # enchantments for it, best first: the first the editor can write goes on
    effects: tuple[str, ...] = ()  # gear effects for it, best first: as many go on as the game rolls at its rarity


@dataclass(frozen=True)
class Preset:
    title: str
    goal: str
    details: str
    stats: dict[str, int] = field(default_factory=dict)
    items: tuple[KitItem, ...] = ()
    upgrade_gear: bool = False  # weapons and armor to Unique, artifacts to Special, at the chosen power
    experimental: bool = False
    sources: tuple[str, ...] = ()
    group: str = GOALS
    choose_rarity: bool = False  # the window asks what rarity to add the gear at
    equip: bool = False  # "Equip them" starts ticked


# Talismans and Uniques the goal presets mention (effects by talisman level, from MetaBot's talisman pages).
LUCKY_CLOVER = KitItem("Lucky Clover", "Talisman", "+2 / 4 / 7% chance of extra loot drops (by talisman level).")
LOOTERS_CHARM = KitItem("Looter's Charm", "Talisman", "Up to a 4% better chance for enemies to drop loot.")
EMERALD_OF_GOOD_FORTUNE = KitItem("Emerald of Good Fortune", "Talisman", "Up to a 25% chance of extra emeralds.")
EYE_OF_EXPERIENCE = KitItem("The Eye of Experience", "Talisman", "Up to +10% XP.")
THRIFTY_PENDANT = KitItem("Thrifty Pendant", "Talisman", "More damage the more emeralds you carry.")
EMERALD_HAMMER = KitItem(
    "Emerald Hammer", "Melee", "Unique weapon with a 5% chance of higher-rarity loot.",
    "A reward from the quest The Final Souldown.", rarity="Unique",
)
ORACLE_SANDALS = KitItem(
    "Oracle Sandals", "Boots", "Unique boots with a 5% chance of higher-rarity loot.",
    "Part of the full Oracle set from the quest A Dip in Ichor Springs.", rarity="Unique",
)
SECRET = "One of the 8 Mosstrosity secret-quest talismans."
SECRET_TALISMANS = tuple(
    KitItem(name, "Talisman", SECRET)
    for name in ("Amethyst Lens", "Thrifty Pendant", "Lucky Clover", "Soul Chip", "Medallion of Momentum",
                 "Emerald of Good Fortune", "Glowstone Flask", "Ocelot's Paw")
)

PRESETS: tuple[Preset, ...] = (
    Preset(
        "Most money",
        "Fill your wallet and make every pickup pay more.",
        f"Sets emeralds and Echo Shards to the game's caps ({STAT_CAPS['Emeralds']:,} and {STAT_CAPS['SpringStone']}; "
        "anything above a cap is lost). "
        "The Emerald of Good Fortune adds up to a 25% chance of extra emeralds. In the game, salvaging gear is the "
        "main source of emeralds, and bigger, rarer items pay more.",
        stats={"Emeralds": STAT_CAPS["Emeralds"], "SpringStone": STAT_CAPS["SpringStone"]},
        items=(EMERALD_OF_GOOD_FORTUNE,),
        sources=(METABOT_TALISMANS, METABOT_BEGINNER),
    ),
    Preset(
        "Most XP",
        "Level up faster.",
        "The Eye of Experience adds up to 10% XP. Your equipped talismans level up from the same XP, so wear the "
        "ones you want to level.",
        items=(EYE_OF_EXPERIENCE,),
        sources=(METABOT_TALISMANS,),
    ),
    Preset(
        "Best loot",
        "More drops and better rarity while you farm.",
        "Lucky Clover and Looter's Charm add loot drops, and the Emerald Hammer and Oracle Sandals each add a 5% "
        "chance of higher-rarity loot. Never farm on Easy: it can't drop Special or Unique items. Soul Storm reward "
        "chests are the best source of Uniques (about 20%), then bosses (16.7%).",
        items=(LUCKY_CLOVER, LOOTERS_CHARM, EMERALD_HAMMER, ORACLE_SANDALS),
        sources=(METABOT_TALISMANS, METABOT_UNIQUES),
    ),
    Preset(
        "Upgrade my gear",
        "Turn everything you own into top-rarity gear at the power you pick.",
        "Makes every weapon and armor piece in your inventory Unique and every artifact Special (artifacts and "
        "talismans can't be Unique), at the power you choose. An item whose Unique has been seen in a real save "
        "becomes that Unique (a Sword becomes The Burning Blade); the others keep their name and get Unique rarity. "
        "It also fills your emeralds for the Thrifty Pendant, which adds more damage the more emeralds you carry. "
        "Keep the power close to your level: in a test, the game removed items at power 135.",
        stats={"Emeralds": STAT_CAPS["Emeralds"]},
        items=(THRIFTY_PENDANT,),
        upgrade_gear=True,
        sources=(METABOT_TALISMANS, METABOT_UNIQUES),
    ),
    Preset(
        "Fully upgraded town",
        "Max out the Village Merchant, Enchantsmith and Blacksmith.",
        "Sets all three vendors to level 3 and fills your Echo Shards. At level 3 the Merchant sells Special items, "
        "the Blacksmith re-rolls the effects on Unique items, and the Enchantsmith raises enchantments to tier III. "
        "In the game the first upgrade comes at level 15, for 300 emeralds, 50 Echo Shards and 4 enchantment books, "
        "and takes the Merchant and the Enchantsmith to level 2; the rest are paid for in Echo Shards. A vendor you "
        "haven't unlocked yet keeps the level set here for when you do.",
        stats={"VillageMerchantUpgradeLevel": 3, "EnchantsmithUpgradeLevel": 3, "OldBlacksmithUpgradeLevel": 3, "SpringStone": 100},
        sources=(METABOT_PROGRESSION, METABOT_MERCHANTS),
    ),
    Preset(
        "Secret talisman hunt",
        "The 8 secret talismans.",
        "The game ties 8 talismans to the Mosstrosity secret quest, whose reward is Wonderful Wheat (a llama "
        "companion). Any you've already found, or that another hero has, can be added straight away. Maxroll's "
        "secret talisman guide shows where each one is hidden: " + MAXROLL_SECRETS,
        items=SECRET_TALISMANS,
        sources=(METABOT_TALISMANS,),
    ),
)


def _piece(name: str, kind: str, why: str, *enchants: str, effects: tuple[str, ...] = ()) -> KitItem:
    return KitItem(name, kind, why, enchants=enchants, effects=effects)


def _set(*pieces: tuple[str, str], enchants: tuple[tuple[str, ...], tuple[str, ...]], effects: tuple[str, ...] = ()) -> tuple[KitItem, ...]:
    """Four armor pieces (helmet, chestplate, leggings, boots). The helmet and the chestplate take the
    enchantments, as in MetaBot's build planner, which enchants one weapon, the helmet and the chestplate."""
    return tuple(
        _piece(name, "Armor", why, *enchant, effects=effects) for (name, why), enchant in zip(pieces, (*enchants, (), ()))
    )


def _kit(*, melee: KitItem, ranged: KitItem | None, armor: tuple[KitItem, ...], artifacts: dict[str, str], talismans: dict[str, str]) -> tuple[KitItem, ...]:
    """A loadout: weapons, the four armor pieces, three artifacts and three talismans (name: what it does here)."""
    weapons = (melee,) if ranged is None else (melee, ranged)
    return (
        weapons
        + armor
        + tuple(KitItem(name, "Artifact", why, effects=ARTIFACT_EFFECTS) for name, why in artifacts.items())
        + tuple(KitItem(name, "Talisman", why) for name, why in talismans.items())
    )


# Effects for the gear a kit adds. MetaBot's guides name no gear effects, so these are the editor's own picks,
# best first, from the ones the game rolls on that kind of gear (MetaBot's effects page lists each effect's
# pools): the first the editor has seen saved go on, as many as the game rolls at the item's rarity.
MELEE_EFFECTS = ("Critical Edge", "Critical Hit", "Knockback")  # any weapon: harder and likelier critical hits
RANGED_EFFECTS = ("Marksman", "Critical Edge", "Critical Hit")  # ranger and trickster gear, then any weapon
HEAVY_EFFECTS = ("Knockback", "Critical Edge", "Critical Hit")
ARTIFACT_EFFECTS = ("Cooldown", "Spiritual")  # any artifact: shorter cooldowns, and more souls to pay for them
TRICKSTER_ARMOR = ("Acrobat", "Luck")  # rolls recharge sooner
STURDY_ARMOR = ("Projectile Protection", "Luck")  # fighter, ranger and tank gear: less damage from ranged attacks
MAGE_ARMOR = ("Spiritual", "Cooldown", "Luck")
ANY_ARMOR = ("Luck",)
# Enchantments for a weapon or armor piece when the build names none for it, or none the editor can write yet: the
# editor's own picks, best first, for any kit. Each piece of a kit takes the first one that the editor can write,
# that goes on that piece and that no other piece of the kit carries, so a kit ends up with one of each. Damage
# first on weapons; on armor, healing and artifact power before the rest.
ENCHANT_FALLBACKS = {
    "Melee": ("Fire Aspect", "Thundering", "Swirling", "Poison Fog", "Healing Smite"),
    "Ranged": ("Chain Reaction", "Thundering", "Piercing", "Swirling", "Healing Smite"),
    "Armor": ("Health Synergy", "Artifact Amplifier", "Somersault", "Barrier Brew", "Springload", "Ancient Alchemy", "Ender Quiver", "Gravity Pulse", "Cow Stampede"),
}

# The pieces of MetaBot's builds. Weapons and armor are base items: at Unique rarity they're the Unique named. The
# enchantments are the ones its build planner puts on each piece, then the alternatives its guide names.
RIFTSLASHER = _piece(
    "Riftslasher", "Melee", "At Unique it's Pride of the Plains: +40% damage to the enemy you target.", "Lightning Surge", "Fire Aspect",
    effects=MELEE_EFFECTS,
)
GREATBOW = _piece(
    "Greatbow", "Ranged", "At Unique it's the Humbler Heartstring: arrows pierce up to 10 enemies.", "Chain Reaction", "Piercing",
    effects=RANGED_EFFECTS,
)
HEAVY_CROSSBOW = _piece(
    "Heavy Crossbow", "Ranged", "At Unique it's The Close Ranger: double damage up close.", "Chain Reaction", "Piercing", effects=RANGED_EFFECTS
)
# In the melee build the crossbow is the back-up weapon, and MetaBot's planner leaves it without an enchantment.
SPARE_CROSSBOW = _piece("Heavy Crossbow", "Ranged", "At Unique it's The Close Ranger: double damage up close.", effects=RANGED_EFFECTS)
AXE = _piece("Axe", "Melee", "At Unique it's the Hunter's Hatchet: arrows come back 35% faster.", effects=MELEE_EFFECTS)
TWISTED_WARDEN = _set(
    ("Sculk Digger Hood", "At Unique it's the Twisted Warden Blindfold: +45% melee critical damage."),
    ("Sculk Digger Robe", "At Unique it's the Twisted Warden Vest: 20% chance to dodge melee damage."),
    ("Sculk Digger Leggings", "At Unique they're the Twisted Warden Tights: Shadowcloaking lasts 45% longer."),
    ("Sculk Digger Boots", "At Unique they're the Twisted Warden Sneakers: +25% melee critical chance."),
    enchants=(("Dynamo",), ("Power Amplifier",)),
    effects=TRICKSTER_ARMOR,
)
SHARPSHOOTER = _set(
    ("Ranger Cap", "At Unique it's the Sharpshooter Fedora: 60% chance of extra arrows."),
    ("Ranger Jacket", "At Unique it's the Sharpshooter Duster: +30% ranged damage."),
    ("Ranger Leggings", "At Unique they're the Sharpshooter Chaps: arrows come back 35% faster."),
    ("Ranger Boots", "At Unique they're the Sharpshooter Spurs: carry 45% more arrows."),
    enchants=(("Ender Quiver",), ("Critical Quiver",)),
    effects=STURDY_ARMOR,
)
SCOUNDREL = _set(
    ("Scamp Hood", "At Unique it's the Scoundrel Cowl: a chance to stay in Shadowcloak when you attack."),
    ("Scamp Jacket", "At Unique it's the Scoundrel Blazer: double ranged damage up close."),
    ("Scamp Leggings", "At Unique they're the Scoundrel Chaps: 40% less time between shots."),
    ("Scamp Sneakers", "At Unique they're the Scoundrel Sneakers: faster while Shadowcloaking."),
    enchants=(("Tumbleshot", "Ender Quiver"), ("Critical Quiver",)),  # the editor's picks: MetaBot names none for this variant
    effects=TRICKSTER_ARMOR,
)
MELEE_ARTIFACTS = {
    "Warrior Drums": "Doubles critical hit damage while it plays.",
    "Death Cap Mushroom": "Faster attacks and movement on a 4-second cooldown.",
    "Grindstone": "Sharpens your weapon for extra damage.",
}
MELEE_TALISMANS = {
    "Fist of Iron": "+10 / 20 / 35% melee damage (by talisman level).",
    "Ocelot's Paw": "+10 / 20 / 35% damage on jump attacks.",
    "Sigil of Beeswax": "+20-35% max health.",
}
RANGED_ARTIFACTS = {
    "Flaming Quiver": "Fire arrows.",
    "Firework Arrow": "Explosive arrows.",
    "Tempo Truffle": "Speed for getting into position.",
}
RANGED_TALISMANS = {
    "Amethyst Lens": "+10 / 15 / 25% ranged damage.",
    "Twig of Dark Oak": "+20 / 40 / 60% ammo.",
    "Armadillo Amulet": "Rolls recharge 20-45% faster.",
}
GEAR_SOURCES = (METABOT_BUILDS, METABOT_TIERS, METABOT_ENCHANTING, METABOT_EFFECTS)

PRESETS += (
    Preset(
        "Best melee weapon",
        "The strongest melee weapon for single targets.",
        "MetaBot measures every weapon's damage per second from the game files. The Riftslasher is near the top, and "
        "its Unique, Pride of the Plains, also deals 40% more damage to the enemy you target, which makes it the "
        "strongest single-target melee weapon. Also at the top of their classes: the Twilight Dagger (Unique: "
        "Sculker's Bane) and the War Hammer (Unique: Heartbreaker, whose hits explode); add those with + Add items.",
        items=(RIFTSLASHER,),
        group=BEST_GEAR,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Best ranged weapon",
        "The ranged weapon with the most damage.",
        "The Greatbow has the highest burst damage in the game, though its 10 arrows run out in about 4 seconds. Its "
        "Unique, the Humbler Heartstring, pierces up to 10 enemies. The Heavy Crossbow (Unique: The Close Ranger) "
        "hits slower but keeps firing for longer.",
        items=(GREATBOW,),
        group=BEST_GEAR,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Best armor",
        "The best damage armor: the Twisted Warden set.",
        "Pick Unique rarity to get the Twisted Warden set (the Unique Sculk Digger set), MetaBot's cleanest set for "
        "critical hits: more critical chance and critical damage, and a chance to dodge melee hits. For other "
        "playstyles, see the kits.",
        items=TWISTED_WARDEN,
        group=BEST_GEAR,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Best artifacts",
        "Critical hits and speed on short cooldowns.",
        "Warrior Drums double critical hit damage, the Death Cap Mushroom speeds up your attacks and the Grindstone "
        "sharpens your weapon, all on 4-5 second cooldowns. Artifacts don't come in Unique, so Unique adds them as "
        "Special. Artifact slots 2 and 3 open at levels 5 and 10.",
        items=tuple(KitItem(name, "Artifact", why, effects=ARTIFACT_EFFECTS) for name, why in MELEE_ARTIFACTS.items()),
        group=BEST_GEAR,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Best talismans",
        "More melee damage, and the health to use it.",
        "Fist of Iron and Ocelot's Paw each add up to 35% melee damage (Ocelot's Paw on jump attacks) and the Sigil "
        "of Beeswax up to 35% max health. Talismans level up from the XP you earn while they're equipped, and have "
        "no rarity or power. For ranged builds, see the Greatbow kit.",
        items=tuple(KitItem(name, "Talisman", why) for name, why in MELEE_TALISMANS.items()),
        group=BEST_GEAR,
        choose_rarity=True,
        equip=True,
        sources=(METABOT_BUILDS, METABOT_TALISMANS),
    ),
    # The five builds (and the crossbow variant) from MetaBot's best builds guide.
    Preset(
        "Melee damage",
        "Melt bosses: critical hits, jump attacks and raw melee damage.",
        "The Twisted Warden set adds critical chance and critical damage, and Warrior Drums double critical damage "
        "while they play, so the two multiply each other. Open every fight with a jump attack for Ocelot's Paw.",
        items=_kit(melee=RIFTSLASHER, ranged=SPARE_CROSSBOW, armor=TWISTED_WARDEN, artifacts=MELEE_ARTIFACTS, talismans=MELEE_TALISMANS),
        group=KITS,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Greatbow sharpshooter",
        "The biggest damage numbers in the game, from a safe distance.",
        "The Sharpshooter set (the Unique Ranger set) adds ranged damage, extra arrows and faster arrow recovery, "
        "and the Twig of Dark Oak and the Hunter's Hatchet keep the Greatbow's 10-arrow quiver going.",
        items=_kit(melee=AXE, ranged=GREATBOW, armor=SHARPSHOOTER, artifacts=RANGED_ARTIFACTS, talismans=RANGED_TALISMANS),
        group=KITS,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Close-range crossbow",
        "Crossbow bolts point-blank, rolling between shots.",
        "The Close Ranger (the Unique Heavy Crossbow) and the Scoundrel set (the Unique Scamp set) both deal double "
        "ranged damage up close, and Tumbleshot fires a volley every time you roll.",
        items=_kit(melee=AXE, ranged=HEAVY_CROSSBOW, armor=SCOUNDREL, artifacts=RANGED_ARTIFACTS, talismans=RANGED_TALISMANS),
        group=KITS,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Humbler tank",
        "Stand in the middle of a Soul Storm.",
        "The Humbler set (the Unique Protector set) takes 25% less damage, heals 40% more and can dodge melee hits, "
        "and Health Synergy turns each of the three defensive artifacts into a heal. The full set is the first-clear "
        "reward of The Final Souldown. MetaBot's build doesn't name a ranged weapon, so yours stays.",
        items=_kit(
            melee=_piece("War Hammer", "Melee", "At Unique it's the Heartbreaker: hits explode.", "Shockwave", effects=HEAVY_EFFECTS),
            ranged=None,
            armor=_set(
                ("Protector Helmet", "At Unique it's the Humbler Antenna: take 25% less damage."),
                ("Protector Chestplate", "At Unique it's the Humbler Carapace: 40% more healing."),
                ("Protector Shinguards", "At Unique they're the Humbler Greaves: +50% melee damage to enemies around your target."),
                ("Protector Boots", "At Unique they're the Humbler Tarsi: 20% chance to dodge melee damage."),
                enchants=(("Health Synergy",), ("Bottomless Brew",)),
                effects=STURDY_ARMOR,
            ),
            artifacts={
                "Warding Chimes": "5 seconds of invulnerability.",
                "Echo Ocarina": "Protection from ranged attacks.",
                "Totem of Shielding": "Blocks projectiles for everyone inside it.",
            },
            talismans={
                "Sigil of Beeswax": "+20-35% max health.",
                "Healing Heart": "Heals you out of combat.",
                "Glowstone Flask": "Potions recharge 10 / 15 / 25% faster.",
            },
        ),
        group=KITS,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Soul caster",
        "Area damage from artifacts that are always ready.",
        "The Alchemist set (the Unique Sorcerer set) holds 50% more souls and adds 25% artifact damage, and the "
        "Soul Reaper, Twisted Tooth and Soul Chip keep the souls coming, so an artifact is always ready. MetaBot's "
        "build doesn't name a ranged weapon, so yours stays.",
        items=_kit(
            melee=_piece("Scythe", "Melee", "At Unique it's the Soul Reaper: +60% souls.", "Soul Blast", effects=MELEE_EFFECTS),
            ranged=None,
            armor=_set(
                ("Sorcerer Hat", "At Unique it's the Alchemist Top Hat: your buffs cover a 55% bigger area."),
                ("Sorcerer Robe", "At Unique it's the Alchemist Overcoat: artifacts deal 25% more damage."),
                ("Sorcerer Leggings", "At Unique they're the Alchemist Trousers: heal 6% when you use an artifact."),
                ("Sorcerer Boots", "At Unique they're the Alchemist Loafers: hold 50% more souls."),
                enchants=(("Artifact Amplifier",), ("Power Amplifier",)),
                effects=MAGE_ARMOR,
            ),
            artifacts={
                "Soul Harvester": "Charges into a burst of soul damage.",
                "Cinder Scepter": "Charged soul fire.",
                "Corrupted Beacon": "A soul beam for as long as your souls last.",
            },
            talismans={
                "Twisted Tooth": "+40 / 80 / 140% souls.",
                "Soul Chip": "Hold 15 / 25 / 35% more souls.",
                "Essence of Efficiency": "Artifacts recharge 4-14% faster.",
            },
        ),
        group=KITS,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Companion support",
        "Let three companions fight while you buff and heal the party.",
        "Golem Kit, Tasty Bone and Prickle's Mark each bring a companion, and the Fly Agaric set (the Unique Mushroom "
        "set) makes them deal 40% more damage and take 20% less. Companions draw enemies away from you, which makes "
        "this forgiving in co-op.",
        items=_kit(
            melee=_piece(
                "Wolf Claws", "Melee", "At Unique they're the Sculker Claws: a chance to vanish into Shadowcloak.", "Healing Smite", effects=MELEE_EFFECTS
            ),
            ranged=_piece(
                "Scatter Crossbow", "Ranged", "At Unique it's the Harp Crossbow: 60% chance of extra bolts.", "Healing Smite", effects=RANGED_EFFECTS
            ),
            armor=_set(
                ("Mushroom Cap", "At Unique it's the Fly Agaric Cap: poison attacks deal 20% more damage."),
                ("Mushroom Robe", "At Unique it's the Fly Agaric Coat: heals you out of combat."),
                ("Mushroom Leggings", "At Unique they're the Fly Agaric Trousers: companions deal 40% more damage."),
                ("Mushroom Boots", "At Unique they're the Fly Agaric Galoshes: companions take 20% less damage."),
                enchants=(("Buddy Brew",), ()),
                effects=ANY_ARMOR,
            ),
            artifacts={
                "Honey Dipper": "Traps enemies and brings bees into the fight.",
                "Battle Banner": "Strength for you and your allies.",
                "Totem of Regeneration": "Heals everyone near it.",
            },
            talismans={
                "Golem Kit": "An Iron Golem companion.",
                "Tasty Bone": "A wolf companion.",
                "Prickle's Mark": "A Prickle companion.",
            },
        ),
        group=KITS,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
)


def _wanted(name: str) -> set[str]:
    return {normalize(name), normalize(re.sub(r"^The\s+", "", name))}


def find_item(name: str, catalog: list[CatalogItem]) -> CatalogItem | None:
    """The catalog entry for an in-game item name, allowing for known renames, a leading 'The' and
    Unique names (the Emerald Hammer is a Unique Battle Hammer). Confirmed entries win."""
    wanted = _wanted(name)
    matches = []
    for entry in catalog:
        internal = entry.tag.rsplit(".", 1)[-1]
        names = {normalize(entry.name), normalize(ALIASES.get(internal, "")), normalize(entry.unique or "")}
        if names & wanted:
            matches.append(entry)
    return min(matches, key=lambda entry: not entry.confirmed) if matches else None


def _is_unique_name(kit_item: KitItem, found: CatalogItem) -> bool:
    return bool(found.unique) and bool(_wanted(found.unique) & _wanted(kit_item.name))


def rarity_for(kit_item: KitItem, found: CatalogItem, chosen: str | None) -> str | None:
    """The rarity to add a kit item at: the kit's own, Unique for an item named by its Unique name,
    none for talismans, else ``chosen`` (artifacts top out at Special). None keeps the rarity of the
    saved item it's laid out like."""
    if kit_item.rarity:
        return kit_item.rarity
    if _is_unique_name(kit_item, found):
        return "Unique"
    if found.kind == "Talisman":
        return TALISMAN_RARITY
    if chosen == "Unique" and found.kind == "Artifact":
        return TOP_ARTIFACT_RARITY
    return chosen


@dataclass
class Addition:
    """An item a preset adds."""

    kit: KitItem
    found: CatalogItem
    rarity: str | None  # None keeps the rarity of the saved item it's laid out like
    slot: GearSlot | None = None  # where to equip it
    enchantment: EffectChoice | None = None  # the enchantment it's given
    effects: list[EffectChoice] = field(default_factory=list)  # the effects it's given

    @property
    def name(self) -> str:
        """Its in-game name: at Unique rarity it's the item's Unique."""
        return self.found.unique if self.rarity == "Unique" and self.found.unique else self.kit.name

    @property
    def tag(self) -> str:
        """The ID it's added under: a Unique has an ID of its own."""
        return self.found.tag_at(self.rarity)

    @property
    def confirmed(self) -> bool:
        return self.found.confirmed_at(self.rarity)


@dataclass
class Owned:
    """An item a preset wants that the hero already has."""

    kit: KitItem
    index: int
    slot: GearSlot | None = None  # where to equip it; None leaves it where it is
    enchantment: EffectChoice | None = None  # the enchantment your copy is given, when it has none


@dataclass
class Plan:
    """What applying a preset to one hero would do."""

    power: int = 1  # for upgraded gear, and added items the game hasn't saved a copy of
    rarity: str | None = None  # picked in the window, for presets that ask
    stats: dict[str, int] = field(default_factory=dict)
    add: list[Addition] = field(default_factory=list)
    unconfirmed: list[tuple[KitItem, CatalogItem]] = field(default_factory=list)  # addable, but as a best guess
    have: list[Owned] = field(default_factory=list)
    find: list[KitItem] = field(default_factory=list)
    upgrades: list[tuple[int, str, int]] = field(default_factory=list)  # (item index, rarity, power)
    enchant: bool = False  # the hero has opened the Enchantsmith in the game, so the kit's items get enchanted
    books: list[CatalogItem] = field(default_factory=list)  # enchantment books it adds: the build's own picks, and what it puts on

    @property
    def changes_anything(self) -> bool:
        return bool(self.stats or self.add or self.upgrades or self.books or any(owned.slot or owned.enchantment for owned in self.have))


def _names(item: Item) -> set[str]:
    return {normalize(item.name), normalize(ALIASES.get(item.tag.rsplit(".", 1)[-1], ""))}


def _owned_copy(hero: Hero, kit_item: KitItem, found: CatalogItem | None, result: Plan) -> Item | None:
    """The hero's own copy of a kit item, if it has one that's good enough.

    For presets that pick a rarity, a copy counts only at that rarity and at least the chosen power.
    A talisman has neither: a copy counts unless it has no effect saved and a new one would get one.
    """
    mine = [item for item in hero.items() if not item.stock_slot and not item.is_cosmetic]
    if result.rarity is None:
        wanted = _wanted(kit_item.name)
        matches = [item for item in mine if _names(item) & wanted]
    elif found is None:
        return None
    else:
        rarity = rarity_for(kit_item, found, result.rarity)
        matches = [
            item for item in mine
            if item.tag == found.tag_at(rarity)
            and (
                (found.no_effect or bool(item.progression.get("ItemLevels")))
                if found.kind == "Talisman"
                else (rarity is None or item.rarity == rarity) and (item.power or 0) >= result.power
            )
        ]
    return max(matches, key=lambda item: (item.equipped_slot is not None, item.power or 0), default=None)


def _best(matches: list[EffectChoice]) -> EffectChoice | None:
    """The highest tier of an effect that a real save has shown."""
    order = {tier: position for position, tier in enumerate(TIERS)}
    usable = [choice for choice in matches if choice.seen or choice.yours]
    return max(usable, key=lambda choice: order.get(choice.tier, -1), default=None)


def pick_enchantment(
    names: tuple[str, ...], kind: str, piece: str | None, known: list[EffectChoice], own: str = "", taken: set[str] | frozenset[str] = frozenset()
) -> EffectChoice | None:
    """The first of ``names`` (enchantments, best first) that the editor can write on an item of this kind, at
    the highest tier a real save has shown. None when it can't write any of them yet. ``own`` is the effect the
    item comes with, if it's a Unique: a kit doesn't spend an enchantment on that one again (the Humbler
    Heartstring comes with Piercing for ten enemies; the game would allow it, but nobody knows that it adds
    anything). ``taken`` are the enchantments other pieces of the kit carry: nobody knows that two of one add up
    either, so each piece gets a different one."""
    for name in names:
        found = _best([
            choice for choice in known
            if choice.name == name and choice.is_enchantment and choice.fits(kind, piece) and choice.effect != own and choice.effect not in taken
        ])
        if found is not None:
            return found
    return None


def _enchant(preset: Preset, hero: Hero, result: Plan, known: list[EffectChoice]) -> None:
    """Give every weapon and armor piece of the preset an enchantment, in the preset's order: first the ones
    the build names for a piece, where the editor can write one, then the editor's own pick for the pieces still
    without (ENCHANT_FALLBACKS). A piece of the hero's own keeps the enchantment it has."""
    entries: dict[int, Addition | Owned] = {id(entry.kit): entry for entry in [*result.add, *result.have]}
    wanting = []  # (the plan's entry, kind, piece, the effect it comes with)
    taken: set[str] = set()
    for kit_item in preset.items:
        entry = entries.get(id(kit_item))
        if isinstance(entry, Addition):
            comes_with = entry.found.own_effect_at(entry.rarity)
            if entry.found.kind in ENCHANT_FALLBACKS:
                wanting.append((entry, entry.found.kind, entry.found.piece, comes_with.effect if comes_with is not None else ""))
        elif isinstance(entry, Owned):
            item = hero.item(entry.index)
            if item.enchantment is not None:
                taken.add(item.enchantment.tag)
            elif item.can_be_enchanted and item.kind in ENCHANT_FALLBACKS:
                wanting.append((entry, item.kind, item.piece, next((effect.tag for effect in item.own_effects), "")))
    for names_of in (lambda kit_item, kind: kit_item.enchants, lambda kit_item, kind: ENCHANT_FALLBACKS[kind]):
        for entry, kind, piece, own in wanting:
            if entry.enchantment is None:
                entry.enchantment = pick_enchantment(names_of(entry.kit, kind), kind, piece, known, own, taken)
                if entry.enchantment is not None:
                    taken.add(entry.enchantment.effect)


def _books(preset: Preset, hero: Hero, result: Plan, catalog: list[CatalogItem]) -> list[CatalogItem]:
    """The enchantment books a kit brings: the ones for the enchantments its build names, so the Enchantsmith
    offers those even where the editor can't write them yet, and the ones for what the kit puts on, so they can
    be put on again or raised there. Only books the editor knows, and that the hero is without."""
    wanted = {name for kit_item in preset.items for name in kit_item.enchants}
    wanted |= {entry.enchantment.name for entry in [*result.add, *result.have] if entry.enchantment is not None}
    return [book for book in hero.missing_books(catalog) if book.name in wanted]


def pick_effects(
    names: tuple[str, ...], count: int, known: list[EffectChoice], own: str = "", kind: str = "", tags: tuple[str, ...] = ()
) -> list[EffectChoice]:
    """The first ``count`` of ``names`` (gear effects, best first) that the editor can write, each at the
    highest tier a real save has shown. A kit leaves out the effect the item comes with (``own``): the game
    can roll it as well, but nobody knows that the two add up. Given the item's ``kind`` (and its archetypes,
    ``tags``), it also leaves out an effect the game doesn't roll on such an item: Marksman rolls on Ranger and
    Trickster gear, so a Heavy Crossbow, which is Fighter and Tank gear, gets the next on the list."""
    picked: list[EffectChoice] = []
    for name in names:
        found = _best(
            [
                choice for choice in known
                if choice.name == name and not choice.is_enchantment and choice.effect != own and (not kind or choice.rolls_on_item(kind, tags))
            ]
        )
        if found is not None and len(picked) < count and found.effect not in {choice.effect for choice in picked}:
            picked.append(found)
    return picked


def plan(
    preset: Preset,
    hero: Hero,
    catalog: list[CatalogItem],
    power: int,
    include_unconfirmed: bool = False,
    *,
    rarity: str | None = None,
    equip: bool = False,
    slots: list[GearSlot] | tuple[GearSlot, ...] = GEAR_SLOTS,
    check_level: bool = True,
    enchant: bool | None = None,
    effects: tuple[list[EffectChoice], list[EffectChoice]] | None = None,
) -> Plan:
    """What ``preset`` would do. Best guesses (an item whose ID is one, a talisman the editor can't give its
    effect) are only added with ``include_unconfirmed``.

    ``rarity`` is used by presets that ask for one. With ``equip`` the items it adds (or the hero
    already has) are equipped, in the preset's order, in slots the hero has opened (unless
    ``check_level`` is off). Its weapons and armor are enchanted when ``enchant`` is on, which by default
    is when the hero has opened the Enchantsmith in the game; an item of the hero's own keeps the
    enchantment it has. ``effects`` are the gear effects and enchantments that can be written
    (``hero.effect_choices``; by default the editor's list and what this hero's items show).
    """
    result = Plan(power=power, rarity=rarity if preset.choose_rarity else None)
    result.enchant = hero.vendors_opened()["Enchantsmith"] if enchant is None else enchant
    gear_effects, known_enchantments = effects if effects is not None else effect_choices([hero])
    for name, value in preset.stats.items():
        if name in {a["AttributeName"] for a in hero.attributes()} and hero.attribute(name) != value:
            result.stats[name] = value
    for kit_item in preset.items:
        found = find_item(kit_item.name, catalog)
        mine = _owned_copy(hero, kit_item, found, result)
        if mine is not None:
            result.have.append(Owned(kit_item, mine.index))
        elif found is None:
            result.find.append(kit_item)
        elif found.confirmed_at(rarity_for(kit_item, found, result.rarity)) or include_unconfirmed:
            result.add.append(Addition(kit_item, found, rarity_for(kit_item, found, result.rarity)))
        else:
            result.unconfirmed.append((kit_item, found))
    for addition in result.add:
        kit_item, found = addition.kit, addition.found
        comes_with = found.own_effect_at(addition.rarity)
        own = comes_with.effect if comes_with is not None else ""
        addition.effects = pick_effects(
            kit_item.effects, ROLLED_EFFECTS.get(addition.rarity or "", 0), gear_effects, own, found.kind, archetypes(addition.tag)
        )
    if result.enchant:
        _enchant(preset, hero, result, known_enchantments)
        result.books = _books(preset, hero, result, catalog)
    if equip:
        _choose_slots(preset, hero, result, slots, check_level)
    if preset.upgrade_gear:
        for item in hero.items():
            if item.is_cosmetic or item.stock_slot or item.power is None:
                continue
            group = item_group(item.tag)
            if group == "Gear":
                rarity_wanted = "Unique"
            elif group == "Artifact":
                rarity_wanted = TOP_ARTIFACT_RARITY
            else:
                continue  # talismans and the rest level up instead
            if item.rarity != rarity_wanted or item.power != power:
                result.upgrades.append((item.index, rarity_wanted, power))
    return result


def _choose_slots(preset: Preset, hero: Hero, result: Plan, slots, check_level: bool) -> None:
    """Give each item the plan adds or finds a slot, in the preset's order. Items already
    equipped where they fit stay put, and items left without a free slot stay in the inventory."""
    level = hero.level if check_level and isinstance(hero.level, int) else None
    usable = [slot for slot in slots if level is None or level >= slot.level]
    taken: set[str] = set()
    staying: set[int] = set()
    for owned in result.have:
        item = hero.item(owned.index)
        if item.equipped_slot in {slot.tag for slot in slots_for(item.kind, item.piece, slots)}:
            taken.add(item.equipped_slot)
            staying.add(owned.index)
    entries = {id(entry.kit): entry for entry in [*result.add, *result.have]}
    for kit_item in preset.items:
        entry = entries.get(id(kit_item))
        if entry is None or (isinstance(entry, Owned) and entry.index in staying):
            continue
        if isinstance(entry, Owned):
            item = hero.item(entry.index)
            kind, piece = item.kind, item.piece
        else:
            kind, piece = entry.found.kind, entry.found.piece
        free = [slot for slot in slots_for(kind, piece, usable) if slot.tag not in taken]
        if free:
            entry.slot = free[0]
            taken.add(free[0].tag)


_UNIQUE_INTRO = re.compile(r"^At Unique (it's|they're) (the )?[^:]+: ")


def describe(preset_plan: Plan, hero: Hero) -> list[str]:
    """What the plan will do, in plain English."""
    lines = []
    for name, value in preset_plan.stats.items():
        lines.append(f"{attribute_label(name)}: {format_amount(hero.attribute(name))} → {format_amount(value)}")
    for index, rarity, power in preset_plan.upgrades:
        item = hero.item(index)
        parts = [f"{item.rarity} → {rarity}"] if item.rarity != rarity else []
        if item.power != power:
            parts.append(f"power {format_amount(item.power)} → {format_amount(power)}")
        lines.append(f"{item.name}: {', '.join(parts)}")
    for addition in preset_plan.add:
        line = f"Add {addition.name}"
        if preset_plan.rarity is not None and addition.found.kind != "Talisman":
            what = addition.rarity or "same rarity as your copy"
            if addition.name != addition.found.name:
                what += f" {addition.found.name}"  # "Heartbreaker (Unique War Hammer, ...)"
            line += f" ({what}, power {format_amount(preset_plan.power)})"
        if addition.slot is not None:
            line += f" and equip it ({addition.slot.label.lower()})"
        why = addition.kit.why
        if addition.name != addition.kit.name:
            why = _UNIQUE_INTRO.sub("", why)  # "At Unique it's the Heartbreaker: hits explode." -> "hits explode."
            why = why[:1].upper() + why[1:]
        note = "" if addition.confirmed else " (unconfirmed: without its effect)" if addition.found.no_effect else " (unconfirmed)"
        extras = [choice.title for choice in addition.effects]
        if addition.enchantment is not None:
            extras.append(f"enchanted with {addition.enchantment.title}")
        lines.append(f"{line}: {why}{note}" + (f" With {', '.join(extras)}." if extras else ""))
    for owned in preset_plan.have:
        item = hero.item(owned.index)
        enchanted = f", enchanted with {owned.enchantment.title}" if owned.enchantment is not None else ""
        if owned.slot is not None:
            lines.append(f"Equip your {item.name} ({owned.slot.label.lower()}){enchanted}")
        elif enchanted:
            lines.append(f"Your {item.name}: {enchanted[2:]}")
        else:
            lines.append(f"Already have {item.name}" + (" (equipped)" if item.equipped_slot else ""))
    if preset_plan.books:
        names = [book.name for book in preset_plan.books]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        lines.append(f"Add the enchantment book{'s' if len(names) != 1 else ''} for {listed}, so the Enchantsmith offers {'them' if len(names) != 1 else 'it'}")
    return lines


_PLACES = {"Melee": "Melee weapon", "Ranged": "Ranged weapon", "Artifact": "Artifacts", "Talisman": "Talismans"}


@dataclass(frozen=True)
class LoadoutRow:
    """One item of a kit, the short way: where it goes and what it is."""

    place: str  # Melee weapon, Ranged weapon, Helmet, Chestplate, Leggings, Boots, Artifacts or Talismans
    name: str  # the in-game name it will have
    state: str  # "add", "yours" (the hero's own copy), "left out" (unconfirmed) or "unknown"
    equipped: bool  # goes into a slot rather than the inventory
    confirmed: bool = True


def place_of(kind: str, piece: str | None) -> str:
    return piece if kind == "Armor" and piece else _PLACES.get(kind, kind)


def loadout(preset: Preset, preset_plan: Plan, hero: Hero, catalog: list[CatalogItem]) -> list[LoadoutRow]:
    """The preset's items in its own order, one row each, for a short summary."""
    by_kit: dict[int, LoadoutRow] = {}
    for addition in preset_plan.add:
        place = place_of(addition.found.kind, addition.found.piece)
        by_kit[id(addition.kit)] = LoadoutRow(place, addition.name, "add", addition.slot is not None, addition.confirmed)
    for owned in preset_plan.have:
        item = hero.item(owned.index)
        by_kit[id(owned.kit)] = LoadoutRow(place_of(item.kind, item.piece), item.name, "yours", owned.slot is not None or bool(item.equipped_slot))
    for kit_item, found in preset_plan.unconfirmed:
        unique = rarity_for(kit_item, found, preset_plan.rarity) == "Unique" and found.unique
        by_kit[id(kit_item)] = LoadoutRow(place_of(found.kind, found.piece), found.unique if unique else kit_item.name, "left out", False, False)
    for kit_item in preset_plan.find:
        by_kit[id(kit_item)] = LoadoutRow(_PLACES.get(kit_item.kind, kit_item.kind), kit_item.name, "unknown", False, False)
    return [by_kit[id(kit_item)] for kit_item in preset.items if id(kit_item) in by_kit]


def enchant_suggestions(preset: Preset, preset_plan: Plan | None = None) -> list[tuple[KitItem, list[Enchantment | str]]]:
    """For each item in the preset with suggested enchantments: (item, its enchantments, best first).
    Enchantments missing from the game data come back as plain names. Given the plan, the pieces it enchants
    with a pick of the editor's own are listed too, the ones the build names nothing for with no suggestions."""
    known = enchantments()
    given = enchanted_by(preset_plan) if preset_plan is not None else {}
    return [
        (kit_item, [known.get(name, name) for name in kit_item.enchants]) for kit_item in preset.items if kit_item.enchants or id(kit_item) in given
    ]


def enchanted_by(preset_plan: Plan) -> dict[int, EffectChoice]:
    """The enchantment the plan puts on each of the preset's items that gets one, by ``id`` of the kit item."""
    return {id(entry.kit): entry.enchantment for entry in [*preset_plan.add, *preset_plan.have] if entry.enchantment is not None}


def apply(preset_plan: Plan, hero: Hero, catalog: list[CatalogItem], game_caps: bool = True, check_level: bool = True) -> None:
    """Make the planned changes to ``hero``. Nothing changes if a stat is refused."""
    if preset_plan.stats:
        hero.set_attributes(dict(preset_plan.stats), game_caps=game_caps)
    for index, rarity, power in preset_plan.upgrades:
        hero.update_item(index, rarity=rarity, power=power)
    for owned in preset_plan.have:
        if owned.slot is not None:
            hero.equip(owned.index, owned.slot, check_level)
    for addition in preset_plan.add:
        template = template_for(addition.found.tag, catalog)
        exact = template is not None and template.get("ItemData", {}).get("TypeTag") == addition.found.tag
        # Without a picked rarity, a saved copy of the item already has the right power; otherwise use the preset's.
        keep_power = exact and preset_plan.rarity is None
        index = hero.add_item(
            addition.tag,
            template,
            rarity=addition.rarity,
            power=None if keep_power else preset_plan.power,
            slot=addition.slot,
            check_level=check_level,
        )
        if addition.effects:
            hero.set_effects(index, addition.effects)
        if addition.enchantment is not None:
            hero.set_enchantment(index, addition.enchantment)
    for owned in preset_plan.have:
        if owned.enchantment is not None:
            hero.set_enchantment(owned.index, owned.enchantment)
    for book in preset_plan.books:
        if not hero.has_book(book.tag):
            hero.add_item(book.tag, template_for(book.tag, catalog))
