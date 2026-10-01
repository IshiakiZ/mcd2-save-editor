"""Ready-made changes ("presets") for a hero, from what's known about the game.

The game keeps its real number tables (loot odds, XP curve, item stats) in
encrypted files, so nothing here is calculated from them. The numbers, the gear
rankings and the kits come from MetaBot.GG's database and guides, which are built
from the game files (build 1.1.1.0) and may be reused with a link to the page the
data came from; every preset links its pages.

A preset can set stats, upgrade the gear you own, add items and equip them.
Items whose save ID is only a best guess are added only when asked to (see
hero.build_catalog). Enchantments can't be added yet, so presets suggest the
ones to pick at the Enchantsmith instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hero import (
    GEAR_SLOTS,
    CatalogItem,
    Enchantment,
    GearSlot,
    Hero,
    Item,
    attribute_label,
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
# Where the secret talismans are hidden: a link only, since Maxroll's terms don't allow reusing its guides in software.
MAXROLL_SECRETS = "https://maxroll.gg/minecraft-dungeons-2/guides/secret-talisman-locations-in-minecraft-dungeons-2"

GOALS, BEST_GEAR, KITS = "Goals", "Most powerful gear", "Kits"
GROUPS = (GOALS, BEST_GEAR, KITS)
TALISMAN_RARITY = "Common"  # the wiki lists every talisman as common
TOP_ARTIFACT_RARITY = "Special"  # artifacts don't come in Unique


@dataclass(frozen=True)
class KitItem:
    name: str  # in-game name (a base item; at Unique rarity it becomes its Unique)
    kind: str
    why: str
    where: str = ""
    rarity: str | None = None  # always this rarity; None: the rarity picked in the window
    enchants: tuple[str, ...] = ()  # enchantments to pick for it in the game, best first


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
        "Sets emeralds and Echo Shards to the game's caps (9,999 and 100; anything above a cap is lost). "
        "The Emerald of Good Fortune adds up to a 25% chance of extra emeralds. In the game, salvaging gear is the "
        "main source of emeralds, and bigger, rarer items pay more.",
        stats={"Emeralds": 9_999, "SpringStone": 100},
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
        "talismans can't be Unique), at the power you choose. It also fills your emeralds for the Thrifty Pendant, "
        "which adds more damage the more emeralds you carry. The editor can't add a Unique's signature effect; "
        "Uniques found in the game come with one.",
        stats={"Emeralds": 9_999},
        items=(THRIFTY_PENDANT,),
        upgrade_gear=True,
        sources=(METABOT_TALISMANS, METABOT_UNIQUES),
    ),
    Preset(
        "Fully upgraded town",
        "Max out the Village Merchant, Enchantsmith and Blacksmith.",
        "Sets all three vendors to level 3 and fills your Echo Shards. In the game the first vendor upgrade needs "
        "level 15, 300 emeralds, 50 Echo Shards and 4 enchantment books, and the next Blacksmith and Enchantsmith "
        "levels cost 20 / 40 and 30 / 60 Echo Shards.",
        stats={"VillageMerchantUpgradeLevel": 3, "EnchantsmithUpgradeLevel": 3, "OldBlacksmithUpgradeLevel": 3, "SpringStone": 100},
        sources=(METABOT_PROGRESSION,),
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
    Preset(
        "Max level",
        "Jump straight to level 100 with all your enchantment points.",
        "Sets your level to 100 and enchantment points to 99 (one per level-up). The editor doesn't know how the "
        "game ties XP to level, so XP is left alone and the game may adjust it. Try it on a hero you don't mind "
        "restoring from a backup.",
        stats={"Level": 100, "EnchantmentPoints": 99},
        experimental=True,
        sources=(METABOT_PROGRESSION,),
    ),
)


def _piece(name: str, kind: str, why: str, *enchants: str) -> KitItem:
    return KitItem(name, kind, why, enchants=enchants)


def _set(*pieces: tuple[str, str], enchants: tuple[str, str, str, str]) -> tuple[KitItem, ...]:
    """Four armor pieces (helmet, chestplate, leggings, boots) with an enchantment each."""
    return tuple(_piece(name, "Armor", why, enchant) for (name, why), enchant in zip(pieces, enchants))


def _kit(*, melee: KitItem, ranged: KitItem | None, armor: tuple[KitItem, ...], artifacts: dict[str, str], talismans: dict[str, str]) -> tuple[KitItem, ...]:
    """A loadout: weapons, the four armor pieces, three artifacts and three talismans (name: what it does here)."""
    weapons = (melee,) if ranged is None else (melee, ranged)
    return (
        weapons
        + armor
        + tuple(KitItem(name, "Artifact", why) for name, why in artifacts.items())
        + tuple(KitItem(name, "Talisman", why) for name, why in talismans.items())
    )


# The pieces of MetaBot's builds. Weapons and armor are base items: at Unique rarity they're the Unique named.
RIFTSLASHER = _piece("Riftslasher", "Melee", "At Unique it's Pride of the Plains: +40% damage to the enemy you target.", "Lightning Surge")
GREATBOW = _piece("Greatbow", "Ranged", "At Unique it's the Humbler Heartstring: arrows pierce up to 10 enemies.", "Chain Reaction")
HEAVY_CROSSBOW = _piece("Heavy Crossbow", "Ranged", "At Unique it's The Close Ranger: double damage up close.", "Chain Reaction")
AXE = _piece("Axe", "Melee", "At Unique it's the Hunter's Hatchet: arrows come back 35% faster.", "Lightning Surge")
TWISTED_WARDEN = _set(
    ("Sculk Digger Hood", "At Unique it's the Twisted Warden Blindfold: +45% melee critical damage."),
    ("Sculk Digger Robe", "At Unique it's the Twisted Warden Vest: 20% chance to dodge melee damage."),
    ("Sculk Digger Leggings", "At Unique they're the Twisted Warden Tights: Shadowcloaking lasts 45% longer."),
    ("Sculk Digger Boots", "At Unique they're the Twisted Warden Sneakers: +25% melee critical chance."),
    enchants=("Dynamo", "Power Amplifier", "Dynamo", "Power Amplifier"),
)
SHARPSHOOTER = _set(
    ("Ranger Cap", "At Unique it's the Sharpshooter Fedora: 60% chance of extra arrows."),
    ("Ranger Jacket", "At Unique it's the Sharpshooter Duster: +30% ranged damage."),
    ("Ranger Leggings", "At Unique they're the Sharpshooter Chaps: arrows come back 35% faster."),
    ("Ranger Boots", "At Unique they're the Sharpshooter Spurs: carry 45% more arrows."),
    enchants=("Ender Quiver", "Critical Quiver", "Ender Quiver", "Critical Quiver"),
)
SCOUNDREL = _set(
    ("Scamp Hood", "At Unique it's the Scoundrel Cowl: a chance to stay in Shadowcloak when you attack."),
    ("Scamp Jacket", "At Unique it's the Scoundrel Blazer: double ranged damage up close."),
    ("Scamp Leggings", "At Unique they're the Scoundrel Chaps: 40% less time between shots."),
    ("Scamp Sneakers", "At Unique they're the Scoundrel Sneakers: faster while Shadowcloaking."),
    enchants=("Tumbleshot", "Tumbleshot", "Critical Quiver", "Ender Quiver"),
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
GEAR_SOURCES = (METABOT_BUILDS, METABOT_TIERS, METABOT_ENCHANTING)

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
        items=tuple(KitItem(name, "Artifact", why) for name, why in MELEE_ARTIFACTS.items()),
        group=BEST_GEAR,
        choose_rarity=True,
        equip=True,
        sources=GEAR_SOURCES,
    ),
    Preset(
        "Best talismans",
        "More melee damage, and the health to use it.",
        "Fist of Iron and Ocelot's Paw each add up to 35% melee damage (Ocelot's Paw on jump attacks) and the Sigil "
        "of Beeswax up to 35% max health. Talismans level up from the XP you earn while they're equipped, and only "
        "come in Common. For ranged builds, see the Greatbow kit.",
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
        items=_kit(melee=RIFTSLASHER, ranged=HEAVY_CROSSBOW, armor=TWISTED_WARDEN, artifacts=MELEE_ARTIFACTS, talismans=MELEE_TALISMANS),
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
            melee=_piece("War Hammer", "Melee", "At Unique it's the Heartbreaker: hits explode.", "Shockwave"),
            ranged=None,
            armor=_set(
                ("Protector Helmet", "At Unique it's the Humbler Antenna: take 25% less damage."),
                ("Protector Chestplate", "At Unique it's the Humbler Carapace: 40% more healing."),
                ("Protector Shinguards", "At Unique they're the Humbler Greaves: +50% melee damage to enemies around your target."),
                ("Protector Boots", "At Unique they're the Humbler Tarsi: 20% chance to dodge melee damage."),
                enchants=("Health Synergy", "Bottomless Brew", "Health Synergy", "Health Synergy"),
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
            melee=_piece("Scythe", "Melee", "At Unique it's the Soul Reaper: +60% souls.", "Soul Blast"),
            ranged=None,
            armor=_set(
                ("Sorcerer Hat", "At Unique it's the Alchemist Top Hat: your buffs cover a 55% bigger area."),
                ("Sorcerer Robe", "At Unique it's the Alchemist Overcoat: artifacts deal 25% more damage."),
                ("Sorcerer Leggings", "At Unique they're the Alchemist Trousers: heal 6% when you use an artifact."),
                ("Sorcerer Boots", "At Unique they're the Alchemist Loafers: hold 50% more souls."),
                enchants=("Artifact Amplifier", "Power Amplifier", "Artifact Amplifier", "Power Amplifier"),
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
            melee=_piece("Wolf Claws", "Melee", "At Unique they're the Sculker Claws: a chance to vanish into Shadowcloak.", "Healing Smite"),
            ranged=_piece("Scatter Crossbow", "Ranged", "At Unique it's the Harp Crossbow: 60% chance of extra bolts.", "Healing Smite"),
            armor=_set(
                ("Mushroom Cap", "At Unique it's the Fly Agaric Cap: poison attacks deal 20% more damage."),
                ("Mushroom Robe", "At Unique it's the Fly Agaric Coat: heals you out of combat."),
                ("Mushroom Leggings", "At Unique they're the Fly Agaric Trousers: companions deal 40% more damage."),
                ("Mushroom Boots", "At Unique they're the Fly Agaric Galoshes: companions take 20% less damage."),
                enchants=("Buddy Brew", "Buddy Brew", "Buddy Brew", "Buddy Brew"),
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
    Common for talismans, else ``chosen`` (artifacts top out at Special). None keeps the rarity of the
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

    @property
    def name(self) -> str:
        """Its in-game name: a base item at Unique rarity goes by its Unique's name."""
        return self.found.unique if self.rarity == "Unique" and self.found.unique else self.kit.name


@dataclass
class Owned:
    """An item a preset wants that the hero already has."""

    kit: KitItem
    index: int
    slot: GearSlot | None = None  # where to equip it; None leaves it where it is


@dataclass
class Plan:
    """What applying a preset to one hero would do."""

    power: int = 1  # for upgraded gear, and added items the game hasn't saved a copy of
    rarity: str | None = None  # picked in the window, for presets that ask
    stats: dict[str, int] = field(default_factory=dict)
    add: list[Addition] = field(default_factory=list)
    unconfirmed: list[tuple[KitItem, CatalogItem]] = field(default_factory=list)  # addable, but with a best-guess ID
    have: list[Owned] = field(default_factory=list)
    find: list[KitItem] = field(default_factory=list)
    upgrades: list[tuple[int, str, int]] = field(default_factory=list)  # (item index, rarity, power)

    @property
    def changes_anything(self) -> bool:
        return bool(self.stats or self.add or self.upgrades or any(owned.slot for owned in self.have))


def _names(item: Item) -> set[str]:
    return {normalize(item.name), normalize(ALIASES.get(item.tag.rsplit(".", 1)[-1], ""))}


def _owned_copy(hero: Hero, kit_item: KitItem, found: CatalogItem | None, result: Plan) -> Item | None:
    """The hero's own copy of a kit item, if it has one that's good enough.

    For presets that pick a rarity, a copy counts only at that rarity and at least the chosen power.
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
            if item.tag == found.tag and (rarity is None or item.rarity == rarity) and (item.power or 0) >= result.power
        ]
    return max(matches, key=lambda item: (item.equipped_slot is not None, item.power or 0), default=None)


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
) -> Plan:
    """What ``preset`` would do. Items with best-guess IDs are only added with ``include_unconfirmed``.

    ``rarity`` is used by presets that ask for one. With ``equip`` the items it adds (or the hero
    already has) are equipped, in the preset's order, in slots the hero has opened (unless
    ``check_level`` is off).
    """
    result = Plan(power=power, rarity=rarity if preset.choose_rarity else None)
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
        elif found.confirmed or include_unconfirmed:
            result.add.append(Addition(kit_item, found, rarity_for(kit_item, found, result.rarity)))
        else:
            result.unconfirmed.append((kit_item, found))
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
        if preset_plan.rarity is not None:
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
        lines.append(f"{line}: {why}" + ("" if addition.found.confirmed else " (unconfirmed)"))
    for owned in preset_plan.have:
        item = hero.item(owned.index)
        if owned.slot is not None:
            lines.append(f"Equip your {item.name} ({owned.slot.label.lower()})")
        else:
            lines.append(f"Already have {item.name}" + (" (equipped)" if item.equipped_slot else ""))
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
        by_kit[id(addition.kit)] = LoadoutRow(place, addition.name, "add", addition.slot is not None, addition.found.confirmed)
    for owned in preset_plan.have:
        item = hero.item(owned.index)
        by_kit[id(owned.kit)] = LoadoutRow(place_of(item.kind, item.piece), item.name, "yours", owned.slot is not None or bool(item.equipped_slot))
    for kit_item, found in preset_plan.unconfirmed:
        unique = rarity_for(kit_item, found, preset_plan.rarity) == "Unique" and found.unique
        by_kit[id(kit_item)] = LoadoutRow(place_of(found.kind, found.piece), found.unique if unique else kit_item.name, "left out", False, False)
    for kit_item in preset_plan.find:
        by_kit[id(kit_item)] = LoadoutRow(_PLACES.get(kit_item.kind, kit_item.kind), kit_item.name, "unknown", False, False)
    return [by_kit[id(kit_item)] for kit_item in preset.items if id(kit_item) in by_kit]


def enchant_suggestions(preset: Preset) -> list[tuple[KitItem, list[Enchantment | str]]]:
    """For each item in the preset with suggested enchantments: (item, its enchantments, best first).
    Enchantments missing from the game data come back as plain names."""
    known = enchantments()
    return [(kit_item, [known.get(name, name) for name in kit_item.enchants]) for kit_item in preset.items if kit_item.enchants]


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
        hero.add_item(
            addition.found.tag,
            template,
            rarity=addition.rarity,
            power=None if keep_power else preset_plan.power,
            slot=addition.slot,
            check_level=check_level,
        )
