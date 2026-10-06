"""The editor's picks of effects for an item, by what you want from it: "Best for" in Change effects.

Two things go into a pick, and only the first is the game's own rule.

Which effects an item can get. The game rolls an item's effects from pools: its slot's (any weapon, any
artifact, all gear) and one for each archetype it carries (Fighter, Ranger...). MetaBot's tables give every
item's archetypes and every effect's pools (tools/build_item_catalog.py reads them, and the item list links the
pages), and the items in players' lists bear them out: of the 342 rolled effects on those items, 338 are in the
pool this predicts, and the other four are on items their owner had changed with the editor. So a pick is always
an effect the game could have rolled on that very item.

Which of those serve a goal best. That is the editor's judgement, from what the game says each effect does: a
bonus that always applies comes before one that needs a critical hit or a charged shot, and that before one that
needs the right enemy or the right moment. Nobody has measured one effect against another, so the order is a
recommendation, and the window says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .hero import TIERS, EffectChoice, the

MELEE, RANGED, ARTIFACT = "Melee", "Ranged", "Artifact"
# What an elemental artifact's own attacks are boosted by.
ELEMENT_EFFECTS = {"Fire": "Pyromancer", "Frost": "Cryomancer", "Lightning": "Electromancer", "Poison": "Venomancer", "Soul": "Soulmancer"}
# Effects that only speak of one kind of attack. On a weapon, the ones for the other kind of weapon go last; on
# an artifact, the ones for artifacts come first.
ABOUT = {
    MELEE: ("Sharpness", "Duelist", "Swiftness", "Precision", "Strength", "Brawler"),
    RANGED: ("Impact", "Ranger", "Sharpshooter", "Aim", "Marksman", "Sniper", "Point Blank"),
    ARTIFACT: ("Sorcerer", *ELEMENT_EFFECTS.values()),
}


@dataclass(frozen=True)
class Goal:
    """Something to want from an item, and the effects that give it, best first."""

    name: str  # as the list shows it: Damage
    order: tuple[str, ...] = ()  # effects by the game's name for them
    how: str = ""  # how the order was made, to finish "In the editor's order: "
    instead: str = ""  # what to say when no effect on gear gives it at all
    by_kind: bool = False  # the order depends on the item: see ABOUT


GOALS = (
    Goal(
        "Damage",
        (
            # Always on.
            "Sharpness", "Duelist", "Impact", "Sorcerer", *ELEMENT_EFFECTS.values(), "Pack Leader", "Swiftness", "Ranger",
            # Needs a charged shot or a critical hit.
            "Sharpshooter", "Critical Hit", "Critical Edge", "Precision", "Aim", "Strength", "Marksman",
            # Needs the right enemy or the right moment.
            "Brawler", "Bully", "Sniper", "Point Blank", "Vanguard", "Bounty Hunter", "Finesse", "Persistence", "Prickly",
        ),
        "bonuses that always apply first, then critical hits and charged shots, then ones that need the right enemy or moment.",
        by_kind=True,
    ),
    Goal(
        "Survival",
        (
            "Protection", "Evasion", "Projectile Protection", "Deflection", "Elemental Protection",
            "Regeneration", "Recovery", "Healer", "Resilience", "Potion Maker",
        ),
        "taking less damage first, then healing, then shaking off statuses.",
    ),
    Goal("Mobility", ("Speed", "Acrobat", "Prowler"), "moving faster first, then rolling more often."),
    Goal(
        "Loot",
        ("Looter", "Raider", "Luck", "Prospector"),
        "more drops first, then better rarity, duplicates and emeralds.",
    ),
    Goal(
        "Artifacts and souls",
        ("Cooldown", "Spiritual", "Reaper", "Sorcerer"),
        "shorter cooldowns first, then the souls to pay for artifacts, then their damage.",
    ),
    Goal(
        "Companions",
        ("Pack Leader", "Shepherd", "Veterinarian"),
        "their damage first, then keeping them alive, then getting them back sooner.",
    ),
    Goal(
        "XP",
        instead=(
            "No effect on gear gives XP. The Eye of Experience talisman does, up to 10% more: Presets has it "
            "under Goals, as Most XP."
        ),
    ),
)


def goal(name: str) -> Goal | None:
    return next((found for found in GOALS if found.name == name), None)


def _order(found: Goal, kind: str, elements: Iterable[str]) -> list[str]:
    """The goal's effects for an item of this kind, best first. An element's effect only counts for an element
    in play: the item's own, or one of the artifacts the hero has equipped."""
    wanted = {ELEMENT_EFFECTS[element] for element in elements if element in ELEMENT_EFFECTS}
    names = [name for name in found.order if name not in ELEMENT_EFFECTS.values() or name in wanted]
    if not found.by_kind:
        return names
    first = ABOUT[ARTIFACT] if kind == ARTIFACT else ()
    last = ABOUT[RANGED] if kind == MELEE else ABOUT[MELEE] if kind == RANGED else ()
    return sorted(names, key=lambda name: 0 if name in first else 2 if name in last else 1)  # sorted keeps the order within each


def candidates(
    found: Goal, kind: str, tags: Iterable[str], choices: Iterable[EffectChoice], elements: Iterable[str] = (), own: Iterable[str] = ()
) -> list[EffectChoice]:
    """Every effect that serves the goal and that the game can roll on an item of this kind with these
    archetypes, best first, each at the best tier a real save has shown (else the best there is). The effects the
    item comes with (``own``, by their IDs) are left out: the game can roll a Unique its own effect a second time,
    but nobody knows that the two add up, so the place goes to the next pick."""
    tags, own = tuple(tags), set(own)
    by_name: dict[str, list[EffectChoice]] = {}
    for choice in choices:
        if choice.effect in own:
            continue
        if not choice.is_enchantment and not choice.yours and choice.tier in TIERS and choice.rolls_on_item(kind, tags):
            by_name.setdefault(choice.name, []).append(choice)
    made = []
    for name in _order(found, kind, elements):
        tiers = sorted(by_name.get(name, ()), key=lambda choice: TIERS.index(choice.tier))
        seen = [choice for choice in tiers if choice.seen]
        if tiers:
            made.append((seen or tiers)[-1])
    return made


def best(
    found: Goal, kind: str, tags: Iterable[str], choices: Iterable[EffectChoice], room: int, elements: Iterable[str] = (), own: Iterable[str] = ()
) -> list[EffectChoice]:
    """The effects to put on an item for a goal: the best ``room`` of the candidates."""
    return candidates(found, kind, tags, choices, elements, own)[: max(room, 0)]


def keep(picked: list[EffectChoice], had: list[EffectChoice], room: int) -> list[EffectChoice]:
    """The picks, then as many of the effects the item had as still fit. One that a pick replaces (the same effect
    at another tier) goes, and so does whatever no longer fits."""
    taken = {choice.effect for choice in picked}
    return picked + [choice for choice in had if choice.effect not in taken][: max(room - len(picked), 0)]


def _listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def gear_words(kind: str, tags: Iterable[str]) -> str:
    """'Fighter and Tank gear', or 'a ranged weapon with no archetype': what decides an item's effects."""
    tags = list(tags)
    if tags:
        return f"{_listed(tags)} gear"
    what = {MELEE: "a melee weapon", RANGED: "a ranged weapon", ARTIFACT: "an artifact"}.get(kind, "an item")
    return f"{what} with no archetype"


def explain(found: Goal, name: str, kind: str, tags: Iterable[str], picked: list[EffectChoice], kept: list[EffectChoice], dropped: list[EffectChoice]) -> str:
    """What "Best for" just did to the item called ``name``, and how it chose, in the words the window shows."""
    parts = [f"Best for {found.name.lower()} on {the(name)} ({gear_words(kind, tags)}): {_listed([choice.title for choice in picked])}."]
    if kept:
        parts.append(f"Kept {_listed([choice.title for choice in kept])}.")
    if dropped:
        parts.append(f"Took off {_listed([choice.title for choice in dropped])}.")
    parts.append(f"In the editor's order: {found.how}")
    return " ".join(parts)


def nothing(found: Goal, name: str, kind: str, tags: Iterable[str], choices: Iterable[EffectChoice]) -> str:
    """What to say when the game rolls none of a goal's effects on an item: where it does roll them."""
    if found.instead:
        return found.instead
    pools: list[str] = []
    for choice in choices:
        if choice.name in found.order:
            pools += [pool for pool in choice.pools if pool not in pools]
    slots = [pool.lower() for pool in pools if not pool.endswith(" gear")]
    gear = sorted(pool[: -len(" gear")] for pool in pools if pool.endswith(" gear"))
    where = slots + ([f"{_listed(gear)} gear"] if gear else [])
    said = f"The game rolls no effect for {found.name.lower()} on {the(name)} ({gear_words(kind, tags)})."
    return said + (f" It rolls them on {_listed(where)}. You can still add one from the list by hand." if where else "")
