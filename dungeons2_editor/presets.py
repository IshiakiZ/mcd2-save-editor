"""Ready-made changes ("presets") for a hero, from what's known about the game.

The game keeps its real number tables (loot odds, XP curve, item stats) in
encrypted files, so nothing here is calculated from them. The numbers come from
community datamines of build 1.1.1.0 (MetaBot, Maxroll) and from the game's
readable script files, as collected in mcd2-research/README.md.

A preset can set stats, upgrade the gear you own, and add items. It only adds
items whose IDs the game has already saved on this PC (see hero.build_catalog);
anything else is listed with where to find it in the game.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hero import CatalogItem, Hero, attribute_label, format_amount, item_group, template_for
from .icons import ALIASES, normalize

MAXROLL_TALISMANS = "https://maxroll.gg/minecraft-dungeons-2/guides/talisman-guide-and-the-best-talismans-in-minecraft-dungeons-2"
MAXROLL_SECRETS = "https://maxroll.gg/minecraft-dungeons-2/guides/secret-talisman-locations-in-minecraft-dungeons-2"
MAXROLL_ENDGAME = "https://maxroll.gg/minecraft-dungeons-2/guides/endgame-farming-guide-for-minecraft-dungeons-2"
METABOT_UNIQUES = "https://metabot.gg/en/minecraft-dungeons-2/guides/unique-items-farming"
METABOT_BEGINNER = "https://metabot.gg/en/minecraft-dungeons-2/guides/beginners-guide"
METABOT_PROGRESSION = "https://metabot.gg/en/minecraft-dungeons-2/progression"


@dataclass(frozen=True)
class KitItem:
    name: str  # in-game name
    kind: str
    why: str
    where: str = ""
    rarity: str | None = None  # None keeps the rarity of the copy the game saved


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


# Items the presets mention, with what they do and where they are.
LUCKY_CLOVER = KitItem(
    "Lucky Clover", "Talisman", "+2 / 4 / 7% extra loot drops (by talisman level).",
    "Frozen Highlands: from the Frozen Fortress waypoint, go into Library Towers, climb the stairs, leave through the gap in the railing and take the hidden jump pad to the chest.",
)
LOOTERS_CHARM = KitItem("Looter's Charm", "Talisman", "+1 / 2 / 4% more loot from enemies.")
EMERALD_OF_GOOD_FORTUNE = KitItem(
    "Emerald of Good Fortune", "Talisman", "+10 / 20 / 25% extra emeralds.",
    "Lullaby Hills: the pipe jumping puzzle near the Lullaby Hilltop checkpoint.",
)
EYE_OF_EXPERIENCE = KitItem("The Eye of Experience", "Talisman", "+4 / 6 / 10% XP.")
THRIFTY_PENDANT = KitItem(
    "Thrifty Pendant", "Talisman", "+25 / 40 / 50% damage while you carry 7,000 / 8,000 / 9,000 emeralds.",
    "Rainy Plains: the sinking-platform jumping puzzle over the water north of the White Tower, near a dungeon entrance.",
)
EMERALD_HAMMER = KitItem(
    "Emerald Hammer", "Melee", "Unique weapon with 5% higher rarity chance on loot.",
    "Guaranteed reward from the quest The Final Souldown.", rarity="Unique",
)
ORACLE_SANDALS = KitItem(
    "Oracle Sandals", "Boots", "Unique boots with 5% higher rarity chance on loot.",
    "Part of the full Oracle set from the quest A Dip in Ichor Springs.", rarity="Unique",
)
AMETHYST_LENS = KitItem(
    "Amethyst Lens", "Talisman", "One of the 8 secret talismans.",
    "Howling Woods: from the Hidden Grove waypoint, go down to the waterfall and climb the blocks above it to a hidden cave chest.",
)
SOUL_CHIP = KitItem(
    "Soul Chip", "Talisman", "One of the 8 secret talismans.",
    "Sift dungeons: jump pads lead to a raised green platform; the chest appears when you get close.",
)
MEDALLION_OF_MOMENTUM = KitItem(
    "Medallion of Momentum", "Talisman", "One of the 8 secret talismans.",
    "Humbler Huskland: walk into the cliffside near the Echo Den entrance, then platform across the skeletal structures.",
)
GLOWSTONE_FLASK = KitItem(
    "Glowstone Flask", "Talisman", "One of the 8 secret talismans.",
    "Overworld dungeons: a room with 4 lit braziers. Put all four out and a floor tile opens.",
)
OCELOTS_PAW = KitItem(
    "Ocelot's Paw", "Talisman", "One of the 8 secret talismans.",
    "Overworld rifts: an interactable wall in a narrow canyon with high walls.",
)

PRESETS = (
    Preset(
        "Most money",
        "Fill your wallet and make every pickup pay more.",
        "Sets emeralds and Echo Shards to the game's caps (9,999 and 100; anything above a cap is lost). "
        "The Emerald of Good Fortune adds up to 25% to emerald pickups. In the game, salvaging gear is the main "
        "source of emeralds, and bigger, rarer items pay more.",
        stats={"Emeralds": 9_999, "SpringStone": 100},
        items=(EMERALD_OF_GOOD_FORTUNE,),
        sources=(MAXROLL_TALISMANS, METABOT_BEGINNER),
    ),
    Preset(
        "Most XP",
        "Level up as fast as the game allows.",
        "The Eye of Experience adds up to 10% XP. The fastest XP in the game is re-killing bosses (the final campaign "
        "boss gives about a level per kill), and higher difficulty pays more XP per kill. Your equipped talismans level "
        "from the same XP.",
        items=(EYE_OF_EXPERIENCE,),
        sources=(MAXROLL_TALISMANS, MAXROLL_ENDGAME, METABOT_UNIQUES),
    ),
    Preset(
        "Best loot",
        "More drops and better rarity while you farm.",
        "Lucky Clover and Looter's Charm add loot drops, and the Emerald Hammer and Oracle Sandals each add 5% "
        "rarity chance. Never farm on Easy: it can't drop Special or Unique items. After the campaign, the Soul Storm "
        "reward chest is the best source of Uniques (about 20%).",
        items=(LUCKY_CLOVER, LOOTERS_CHARM, EMERALD_HAMMER, ORACLE_SANDALS),
        sources=(MAXROLL_TALISMANS, METABOT_UNIQUES, MAXROLL_ENDGAME),
    ),
    Preset(
        "Most powerful",
        "Turn everything you own into top-rarity gear at the power you pick.",
        "Makes every weapon and armor piece in your inventory Unique and every artifact Special (artifacts and "
        "talismans can't be Unique), at the power you choose. It also fills your emeralds for the Thrifty Pendant, "
        "which adds up to 50% damage while you carry 9,000+ emeralds. The editor can't add a Unique's signature "
        "effect; Uniques found in the game come with one.",
        stats={"Emeralds": 9_999},
        items=(THRIFTY_PENDANT,),
        upgrade_gear=True,
        sources=(MAXROLL_TALISMANS, METABOT_UNIQUES),
    ),
    Preset(
        "Fully upgraded town",
        "Max out the Village Merchant, Enchantsmith and Blacksmith.",
        "Sets all three vendors to level 3 and fills your Echo Shards. In the game the first vendor upgrade needs "
        "level 15, 300 emeralds, 50 Echo Shards and 4 enchantment books, and the next Blacksmith and Enchantsmith "
        "levels cost 20 / 40 and 30 / 60 Echo Shards.",
        stats={"VillageMerchantUpgradeLevel": 3, "EnchantsmithUpgradeLevel": 3, "OldBlacksmithUpgradeLevel": 3, "SpringStone": 100},
        sources=(METABOT_PROGRESSION, MAXROLL_ENDGAME),
    ),
    Preset(
        "Secret talisman hunt",
        "Where to find all 8 secret talismans.",
        "Finding all 8 opens the Mosstrosity door in Hidden Grove: an ambush, a boss you can farm, 4 chests and "
        "Wonderful Wheat. Any you've already found (or that another hero has) can be added straight away.",
        items=(AMETHYST_LENS, THRIFTY_PENDANT, LUCKY_CLOVER, SOUL_CHIP, MEDALLION_OF_MOMENTUM, EMERALD_OF_GOOD_FORTUNE, GLOWSTONE_FLASK, OCELOTS_PAW),
        sources=(MAXROLL_SECRETS,),
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


def find_item(name: str, catalog: list[CatalogItem]) -> CatalogItem | None:
    """The catalog entry for an in-game item name, allowing for known renames and a leading 'The'."""
    wanted = {normalize(name), normalize(re.sub(r"^The\s+", "", name))}
    for entry in catalog:
        internal = entry.tag.rsplit(".", 1)[-1]
        if normalize(entry.name) in wanted or normalize(ALIASES.get(internal, "")) in wanted:
            return entry
    return None


@dataclass
class Plan:
    """What applying a preset to one hero would do."""

    power: int = 1  # for upgraded gear, and added items the game hasn't saved a copy of
    stats: dict[str, int] = field(default_factory=dict)
    add: list[tuple[KitItem, CatalogItem]] = field(default_factory=list)
    have: list[KitItem] = field(default_factory=list)
    find: list[KitItem] = field(default_factory=list)
    upgrades: list[tuple[int, str, int]] = field(default_factory=list)  # (item index, rarity, power)

    @property
    def changes_anything(self) -> bool:
        return bool(self.stats or self.add or self.upgrades)


def plan(preset: Preset, hero: Hero, catalog: list[CatalogItem], power: int) -> Plan:
    result = Plan(power=power)
    for name, value in preset.stats.items():
        if name in {a["AttributeName"] for a in hero.attributes()} and hero.attribute(name) != value:
            result.stats[name] = value
    owned = {normalize(item.name) for item in hero.items() if not item.stock_slot}
    owned |= {normalize(ALIASES.get(item.tag.rsplit(".", 1)[-1], "")) for item in hero.items() if not item.stock_slot}
    for kit_item in preset.items:
        wanted = {normalize(kit_item.name), normalize(re.sub(r"^The\s+", "", kit_item.name))}
        found = find_item(kit_item.name, catalog)
        if owned & wanted:
            result.have.append(kit_item)
        elif found is not None:
            result.add.append((kit_item, found))
        else:
            result.find.append(kit_item)
    if preset.upgrade_gear:
        for item in hero.items():
            if item.is_cosmetic or item.stock_slot or item.power is None:
                continue
            group = item_group(item.tag)
            if group == "Gear":
                rarity = "Unique"
            elif group == "Artifact":
                rarity = "Special"
            else:
                continue  # talismans and the rest level up instead
            if item.rarity != rarity or item.power != power:
                result.upgrades.append((item.index, rarity, power))
    return result


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
    for kit_item, found in preset_plan.add:
        lines.append(f"Add {kit_item.name}: {kit_item.why}")
    for kit_item in preset_plan.have:
        lines.append(f"Already have {kit_item.name}")
    return lines


def apply(preset_plan: Plan, hero: Hero, catalog: list[CatalogItem], game_caps: bool = True) -> None:
    """Make the planned changes to ``hero``. Nothing changes if a stat is refused."""
    if preset_plan.stats:
        hero.set_attributes(dict(preset_plan.stats), game_caps=game_caps)
    for index, rarity, power in preset_plan.upgrades:
        hero.update_item(index, rarity=rarity, power=power)
    for kit_item, found in preset_plan.add:
        template = template_for(found.tag, catalog)
        exact = template is not None and template.get("ItemData", {}).get("TypeTag") == found.tag
        # A saved copy of the item already has the right rarity and power; otherwise use the preset's.
        hero.add_item(found.tag, template, rarity=kit_item.rarity, power=None if exact else preset_plan.power)
