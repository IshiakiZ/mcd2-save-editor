"""An MCP server, so an AI assistant (Claude Desktop, Claude Code, ...) can customise your heroes for you.

Run ``MCD2SaveEditor.exe mcp`` (or ``python -m dungeons2_editor mcp``). The assistant's app starts it and talks
to it over stdin and stdout with JSON-RPC, as the Model Context Protocol says (https://modelcontextprotocol.io).

Changes collect in a draft for each hero, like the editor window's unsaved changes, and nothing is written until
``save_changes``, which refuses while the game runs and backs up your saves first. The rules are the editor's
own: offline heroes only, the game's caps and the levels that open gear slots unless the assistant asks to skip
them, and items whose save ID is a best guess only when it says so. The sign-in, entitlement and device-ID
containers are never read.
"""

from __future__ import annotations

import copy
import io
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Callable

from . import __version__, merge, presets, recommend, saves, wgs
from .hero import (
    ATTRIBUTE_LABELS,
    BOOK_KIND,
    MAX_ITEM_POWER,
    MAX_STACK,
    SOULSTORM,
    NO_OWN_EFFECT,
    RARITIES,
    STAT_CAPS,
    TIERS,
    CatalogItem,
    Effect,
    EffectChoice,
    GearSlot,
    Hero,
    Item,
    book_text,
    build_catalog,
    describe_changes,
    effect_book,
    effect_choices,
    format_amount,
    format_caution,
    game_item,
    gear_power,
    gear_slots,
    is_unique_version,
    items_by_identity,
    slots_for,
    template_for,
    the,
)

SERVER_NAME = "mcd2-save-editor"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first
NOT_WRITTEN = "Nothing is written to the game until save_changes."

INSTRUCTIONS = (
    "Edits Minecraft Dungeons II heroes saved on this PC (the Xbox app / PC Game Pass or the Steam version). Start with "
    "list_heroes and get_hero. set_stats, add_item, add_enchantment_books, change_item, equip_item, unequip_item, "
    "copy_item, delete_item and apply_preset collect changes in a draft, like unsaved changes in the editor window: "
    "nothing reaches the game until save_changes, which needs Minecraft Dungeons II to be closed and backs up the whole "
    "save folder first. Show the user preview_changes and get their OK before save_changes. Stay near the gear power "
    "the game gives at the hero's level: a hero set to level 100 has kept it, but in an earlier test the game removed "
    "items at power 135 (most had best-guess IDs). Items with "
    "confirmed: false have a best-guess save ID, and the game may remove them. Talismans have no rarity or power, "
    "and one with effect_known: false can only be added without its effect. Enchantment books (kind Enchantment Book "
    "in find_items) have none either, and a hero has one of each: add_item adds one, add_enchantment_books every one "
    "that's missing, saved the way the game saves a book. The Enchantsmith offers the enchantments of the books in the "
    "inventory, the ones the editor added included (checked in the game). Online heroes are stored on the "
    "game's servers, so they can't be changed. set_item_effects gives a weapon, armor piece or artifact its "
    "effects and a weapon or armor piece its enchantment, from list_effects: the editor writes them exactly as a "
    "real save holds them, so it only has the ones it has seen so far. With best_for (a goal: Damage, Survival, "
    "Mobility, Loot, Artifacts and souls, Companions) it picks the effects itself, out of the ones the game can roll "
    "on that item; that choice is the editor's judgement, so say so if asked. A Unique comes with an effect of its own "
    "(unique_effect): the editor adds it with the Unique where it has seen how the game saves it, and "
    "add_unique_effect gives it to a Unique that's without it (unique_effect_note says when one is). set_talisman_level "
    "puts a talisman at a level outright, as the game saves a level-up; for a companion's talisman ready_talisman "
    "puts a talisman one XP short of its next level. get_hero's vendors says which town vendors the hero has unlocked; kits from "
    "apply_preset add enchantments once the Enchantsmith is one of them."
)

_SLOT_WORDS = {"melee": "Melee weapon", "ranged": "Ranged weapon", "chest": "Chestplate", "legs": "Leggings", "helm": "Helmet"}


class ToolError(Exception):
    """Something the assistant asked for that can't be done; it gets the message as the tool's result."""


@dataclass
class Tool:
    name: str
    title: str
    description: str
    properties: dict
    run: Callable[[dict], dict]
    required: tuple[str, ...] = ()
    read_only: bool = False
    destructive: bool = False

    def listing(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": {"type": "object", "properties": self.properties, "required": list(self.required), "additionalProperties": False},
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "idempotentHint": self.read_only,
                "openWorldHint": False,
            },
        }


@dataclass
class Draft:
    """A hero's unsaved changes: the save as it was when the first change was made, and as edited."""

    name: str  # the container's name
    original: dict
    document: dict
    notes: list[str] = field(default_factory=list)  # what each change did, in order

    @property
    def hero(self) -> Hero:
        return Hero(self.document)


def _string(description: str, **more) -> dict:
    return {"type": "string", "description": description, **more}


def _flag(description: str) -> dict:
    return {"type": "boolean", "description": description, "default": False}


HERO = _string("The hero's id from list_heroes (or its name, if only one hero has that name).")
ITEM = _string("The item's ref from get_hero.")
RARITY = _string("Common, Rare, Special or Unique.", enum=list(RARITIES))
POWER = {"type": "integer", "minimum": 0, "maximum": MAX_ITEM_POWER, "description": "Item power. Stay near the hero's own gear."}
COUNT = {"type": "integer", "minimum": 1, "maximum": MAX_STACK, "description": "How many (a stack)."}
SLOT = _string("A gear slot: Melee weapon, Ranged weapon, Helmet, Chestplate, Leggings, Boots, Artifact 1-3 or Talisman 1-3.")
UNCONFIRMED = _flag(
    "Allow an item whose save ID is a best guess (confirmed: false), which the game may remove, or a talisman "
    "whose effect isn't known (effect_known: false), which may do nothing."
)
LOCKED = _flag("Allow artifact slots the hero's level hasn't opened yet (2 opens at level 5, 3 at level 10).")


class EditorServer:
    """The MCP server's state and tools. ``handle`` takes one JSON-RPC message and returns the reply (or None)."""

    def __init__(self, profile: Path | None = None, backup_root: Path = saves.DEFAULT_BACKUP_ROOT):
        self.profile_path = Path(profile) if profile is not None else None
        self.backup_root = Path(backup_root)
        self.protocol = PROTOCOL_VERSIONS[0]
        self.drafts: dict[str, Draft] = {}
        self.tools = {tool.name: tool for tool in self._tools()}

    # ---------------------------------------------------------------- protocol

    def handle(self, message: Any) -> Any:
        if isinstance(message, list):  # a batch (2025-03-26)
            replies = [reply for reply in (self.handle(part) for part in message) if reply is not None]
            return replies or None
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid request")
        method, params, request_id = message["method"], message.get("params") or {}, message.get("id")
        if "id" not in message:
            return None  # a notification (initialized, cancelled, ...): nothing to answer
        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [tool.listing() for tool in self.tools.values()]}
            elif method == "tools/call":
                result = self._call(params)
            else:
                return _error(request_id, -32601, f"Method not found: {method}")
        except _ProtocolError as exc:
            return _error(request_id, exc.code, str(exc))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _initialize(self, params: dict) -> dict:
        asked = params.get("protocolVersion")
        self.protocol = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {
            "protocolVersion": self.protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "Minecraft Dungeons II Save Editor", "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    def _call(self, params: dict) -> dict:
        tool = self.tools.get(params.get("name"))
        if tool is None:
            raise _ProtocolError(-32602, f"Unknown tool: {params.get('name')}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise _ProtocolError(-32602, "arguments must be an object")
        try:
            unknown = sorted(set(arguments) - set(tool.properties))
            if unknown:
                raise ToolError(f"{tool.name} doesn't take {', '.join(unknown)}.")
            missing = [name for name in tool.required if arguments.get(name) in (None, "")]
            if missing:
                raise ToolError(f"{tool.name} needs {', '.join(missing)}.")
            result = tool.run(arguments)
        except (ToolError, ValueError, KeyError) as exc:
            message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            return {"content": [{"type": "text", "text": str(message)}], "isError": True}
        except saves.GameRunningError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except Exception as exc:  # report it and keep serving
            traceback.print_exc(file=sys.stderr)
            return {"content": [{"type": "text", "text": f"The editor hit an unexpected error: {exc}"}], "isError": True}
        reply = {"content": [{"type": "text", "text": json.dumps(result, indent=1, ensure_ascii=False)}], "isError": False}
        if self.protocol >= "2025-06-18":
            reply["structuredContent"] = result
        return reply

    # ----------------------------------------------------------------- loading

    def _profile(self) -> saves.SaveProfile:
        path = self.profile_path
        if path is None:
            found = saves.find_profiles()
            if not found:
                raise ToolError("No Minecraft Dungeons II saves were found on this PC. Play the game once (Xbox app or Steam version), then try again.")
            path = found[0]
        try:
            return saves.SaveProfile(path)
        except (OSError, wgs.WgsFormatError) as exc:
            raise ToolError(f"Couldn't read the saves: {exc}") from exc

    @staticmethod
    def _hero_ids(profile: saves.SaveProfile) -> dict[str, str]:
        """A short id for each hero, by container name: the start of its character ID (all of it, in the
        unlikely case that two heroes' IDs start the same way)."""
        heroes = [c for c in profile.containers if c.hero is not None]
        short = {c.name: c.hero.character_id[:8] or c.name for c in heroes}
        taken = [value for value in short.values()]
        return {c.name: short[c.name] if taken.count(short[c.name]) == 1 else (c.hero.character_id or c.name) for c in heroes}

    def _container(self, profile: saves.SaveProfile, wanted: str) -> saves.Container:
        """The hero's container, by id (from list_heroes), container name, or name. Only heroes are ever matched."""
        heroes = [c for c in profile.containers if c.hero is not None]
        ids = self._hero_ids(profile)
        key = str(wanted).strip().lower()
        match = [c for c in heroes if key in (c.name.lower(), ids[c.name].lower(), c.hero.character_id.lower())]
        if not match:  # by name: offline heroes first, since online ones can't be changed anyway
            named = [c for c in heroes if key in ((c.hero.skin or "").lower(), c.label.lower())]
            match = [c for c in named if c.kind is saves.Kind.EDITABLE and not c.hero.is_online] or named
        if not match:
            raise ToolError(f"There's no hero {wanted!r}. list_heroes shows the heroes and their ids.")
        if len(match) > 1:
            raise ToolError(f"More than one hero is called {wanted!r}; use the id from list_heroes.")
        container = match[0]
        if container.kind is not saves.Kind.EDITABLE or container.decoded is None or container.hero.is_online:
            raise ToolError("That's an online hero: online heroes are stored on the game's servers, so no save editor can change them.")
        return container

    def _hero_now(self, wanted: str) -> tuple[saves.SaveProfile, saves.Container, Hero, Draft | None]:
        """The hero as it is now: the draft if there's one, else the saved hero."""
        profile = self._profile()
        container = self._container(profile, wanted)
        draft = self.drafts.get(container.name)
        return profile, container, (draft.hero if draft else container.hero), draft

    def _heroes_for_catalog(self, hero: Hero, profile: saves.SaveProfile, name: str) -> list[Hero]:
        return [hero] + [c.hero for c in profile.containers if c.hero is not None and c.name != name]

    def _catalog(self, hero: Hero, profile: saves.SaveProfile, name: str) -> list[CatalogItem]:
        return build_catalog(self._heroes_for_catalog(hero, profile, name))

    def _slots(self, hero: Hero, profile: saves.SaveProfile, name: str) -> list[GearSlot]:
        return gear_slots(self._heroes_for_catalog(hero, profile, name))

    # ----------------------------------------------------------------- reading

    def list_heroes(self, _args: dict) -> dict:
        profile = self._profile()
        ids = self._hero_ids(profile)
        heroes = []
        for container in profile.containers:
            hero = container.hero
            if hero is None:
                continue
            entry = {"hero": ids[container.name], "name": hero.skin or "Hero", "level": hero.level}
            if container.kind is saves.Kind.EDITABLE and not hero.is_online:
                when = datetime.fromtimestamp(wgs.filetime_to_unix(container.entry.mtime))
                draft = self.drafts.get(container.name)
                entry.update(
                    editable=True,
                    power_level=hero.power_level,
                    emeralds=hero.attribute("Emeralds"),
                    last_saved_by_game=f"{when:%Y-%m-%d %H:%M}",
                    unsaved_changes=len(describe_changes(draft.original, draft.document)) if draft else 0,
                )
            else:
                entry.update(editable=False, why="Online hero: stored on the game's servers, so it can't be changed.")
            heroes.append(entry)
        return {"heroes": heroes, "game_running": bool(saves.running_game_processes())}

    def get_hero(self, args: dict) -> dict:
        profile, container, hero, draft = self._hero_now(args["hero"])
        slots = self._slots(hero, profile, container.name)
        refs = _refs(hero)
        catalog = {entry.tag: entry for entry in self._catalog(hero, profile, container.name)}
        level = hero.level if isinstance(hero.level, int) else 1
        worn = {item.equipped_slot: item for item in hero.items() if item.equipped_slot}
        gear = []
        for slot in slots:
            item = worn.get(slot.tag)
            gear.append({
                "slot": slot.label,
                "opens_at_level": slot.level,
                "open": level >= slot.level,
                "item": _item_info(item, refs, catalog) if item is not None else None,
            })
        stats = [
            {"stat": a["AttributeName"], "label": ATTRIBUTE_LABELS.get(a["AttributeName"], a["AttributeName"]), "value": a.get("CurrentValue"),
             "cap": STAT_CAPS.get(a["AttributeName"])}
            for a in hero.attributes()
        ]
        everything = [item for item in hero.items() if not item.is_cosmetic]
        result = {
            "hero": self._hero_ids(profile)[container.name],
            "name": hero.skin or "Hero",
            "level": hero.level,
            "gear_power": gear_power(hero, slots)[0],
            "best_item_power": hero.best_power(),
            "stats": stats,
            "gear": gear,
            "inventory": [_item_info(item, refs, catalog) for item in everything if not item.equipped_slot and not item.stock_slot],
            "merchant_stock": [_item_info(item, refs, catalog) for item in everything if item.stock_slot],
            # By the game's own records: it notes the first time each vendor's window is opened.
            "vendors": hero.vendors_opened(),
            "unsaved_changes": describe_changes(draft.original, draft.document) if draft else [],
        }
        return result

    def list_effects(self, args: dict) -> dict:
        profile = self._profile()
        gear, enchantments = effect_choices([c.hero for c in profile.containers if c.hero is not None])
        query = str(args.get("query") or "").strip().lower()

        def listing(choices: list[EffectChoice]) -> list[dict]:
            grouped: dict[tuple[str, str], list[EffectChoice]] = {}
            for choice in choices:
                grouped.setdefault((choice.effect, choice.template.rsplit(".", 1)[0] if choice.tier else choice.template), []).append(choice)
            found = []
            for tiers in grouped.values():
                first = tiers[0]
                entry: dict[str, Any] = {"name": first.name, "id": first.effect}
                if first.maybe:
                    entry["probably_called"] = first.maybe
                if first.rolls_on:
                    entry["rolls_on"] = first.rolls_on
                if first.is_enchantment:
                    entry["goes_on"] = list(first.slots)
                    if first.what:
                        entry["does"] = first.what + (f" (tiers I, II and III: {first.levels})" if first.levels else "")
                entry["tiers"] = [
                    {"tier": choice.tier or "as saved", **({} if choice.is_enchantment else {"strength": choice.number}),
                     **({} if choice.seen else {"seen": False}), **({"from_your_saves": True} if choice.yours else {})}
                    for choice in tiers
                ]
                if not query or query in f"{entry['name']} {first.maybe} {first.effect} {first.rolls_on} {first.what}".lower():
                    found.append(entry)
            return found

        return {
            "effects": listing(gear),
            "enchantments": listing(enchantments),
            "most_effects_on_an_item": effect_book().max_effects,
            "note": "The game rolls none on a Common item, one on a Rare one and two on a Special one. seen: false marks a tier "
                    "no save has shown yet: its number is from the game files' table, and set_item_effects needs allow_unseen for it. "
                    "Anything on an item in these saves can be copied to another, which is how more become available.",
        }

    def find_items(self, args: dict) -> dict:
        profile = self._profile()
        container = next((c for c in profile.containers if c.hero is not None and c.kind is saves.Kind.EDITABLE), None)
        heroes = [c.hero for c in profile.containers if c.hero is not None]
        catalog = build_catalog(heroes) if heroes else []
        query = str(args.get("query") or "").strip().lower()
        kind = str(args.get("kind") or "").strip().lower()
        limit = _number(args, "limit", 25, 1, 200)
        found = []
        for entry in catalog:
            words = f"{entry.name} {entry.unique or ''} {entry.tag}".lower()
            if (query and query not in words) or (kind and entry.kind.lower() != kind):
                continue
            if args.get("confirmed_only") and not entry.confirmed_at():
                continue
            found.append(_catalog_info(entry))
        note = "" if container is not None else "There's no offline hero to copy an item's layout from yet, so items can't be added."
        return {"items": found[:limit], "matches": len(found), "note": note}

    def list_presets(self, _args: dict) -> dict:
        return {
            "presets": [
                {
                    "preset": preset.title,
                    "group": preset.group,
                    "goal": preset.goal,
                    "asks_for_rarity": preset.choose_rarity,
                    "adds_items": bool(preset.items or preset.upgrade_gear),
                    "sets_stats": dict(preset.stats),
                }
                for preset in presets.PRESETS
            ]
        }

    def preview_changes(self, args: dict) -> dict:
        profile = self._profile()
        container = self._container(profile, args["hero"])
        draft = self.drafts.get(container.name)
        if draft is None:
            return {"unsaved_changes": [], "note": "No changes yet."}
        changes = describe_changes(draft.original, draft.document)
        result = {"unsaved_changes": changes, "note": NOT_WRITTEN}
        if container.decoded.document != draft.original:
            result["note"] = "The game saved this hero since the first change; save_changes will re-apply the changes to the newer save."
        return result

    # ----------------------------------------------------------------- editing

    def _edit(self, wanted: str, change: Callable[[Hero, saves.SaveProfile, saves.Container], tuple[str, dict]]) -> dict:
        """Make one change to a copy of the hero's draft, and keep it only if it worked: a refused change
        leaves the draft as it was."""
        profile = self._profile()
        container = self._container(profile, wanted)
        draft = self.drafts.get(container.name)
        document = copy.deepcopy(draft.document if draft else container.decoded.document)
        text, more = change(Hero(document), profile, container)
        if draft is None:
            draft = self.drafts[container.name] = Draft(container.name, container.decoded.document, document)
        else:
            draft.document = document
        draft.notes.append(text)
        return {"done": text, **more, "unsaved_changes": describe_changes(draft.original, draft.document), "note": NOT_WRITTEN}

    def set_stats(self, args: dict) -> dict:
        values = args["stats"]
        if not isinstance(values, dict) or not values:
            raise ToolError('stats must be an object like {"Emeralds": 9999}.')

        def change(hero: Hero, _profile: saves.SaveProfile, _container: saves.Container) -> tuple[str, dict]:
            names = {a["AttributeName"] for a in hero.attributes()}
            wanted = {}
            for key, value in values.items():
                name = _stat_name(key, names)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ToolError(f"{key} must be a number.")
                wanted[name] = int(value) if float(value).is_integer() and name != "XP" else value
            try:
                hero.set_attributes(wanted, game_caps=not args.get("ignore_caps"))
            except ValueError as exc:
                hint = " Pass ignore_caps to go past the game's caps (anything above them is lost in the game)." if "between" in str(exc) else ""
                raise ToolError(f"{exc}{hint}") from exc
            done = ", ".join(f"{ATTRIBUTE_LABELS.get(name, name)} {format_amount(value)}" for name, value in wanted.items())
            return f"Set {done}.", {}

        return self._edit(args["hero"], change)

    def add_item(self, args: dict) -> dict:
        def change(hero: Hero, profile: saves.SaveProfile, container: saves.Container) -> tuple[str, dict]:
            catalog = self._catalog(hero, profile, container.name)
            entry, unique_name = _catalog_item(args["item"], catalog)
            rarity = args.get("rarity") or ("Unique" if unique_name else "Common")
            if not entry.confirmed_at(rarity) and not args.get("allow_unconfirmed"):
                raise ToolError(f"{_doubt(entry, rarity)} Pass allow_unconfirmed to add it anyway, or pick a confirmed item.")
            power = _number(args, "power", hero.best_power(), 0, MAX_ITEM_POWER)
            count = _number(args, "count", 1, 1, MAX_STACK)
            slot = None
            if args.get("equip"):
                slots = slots_for(entry.kind, entry.piece, self._slots(hero, profile, container.name))
                if not slots:
                    raise ToolError(f"The {entry.name} doesn't go in a gear slot the editor knows.")
                equip = args["equip"]
                slot = _pick_slot(slots, equip if isinstance(equip, str) else None, hero, args.get("ignore_slot_levels"))
            template = template_for(entry.tag, catalog)
            if template is None:
                raise ToolError("There's no item in your saves to copy the layout from yet. Pick up any item in the game first.")
            index = hero.add_item(
                entry.tag_at(rarity), template, rarity=rarity, power=power, count=count, slot=slot, check_level=not args.get("ignore_slot_levels")
            )
            item = hero.item(index)
            text = f"Added the {item.name}" + (" book" if item.is_book else "" if item.ungraded else f" ({item.rarity}, power {format_amount(item.power)})")
            if slot is not None:
                text += f" and equipped it ({slot.label.lower()})"
            return text + ".", {"item": _item_info(item, _refs(hero), {entry.tag: entry})}

        return self._edit(args["hero"], change)

    def add_enchantment_books(self, args: dict) -> dict:
        def change(hero: Hero, profile: saves.SaveProfile, container: saves.Container) -> tuple[str, dict]:
            added = [hero.item(index) for index in hero.add_books(self._catalog(hero, profile, container.name))]
            if not added:
                raise ToolError("This hero has every enchantment book the editor knows.")
            books = "book" if len(added) == 1 else "books"
            refs = _refs(hero)
            return f"Added {len(added)} enchantment {books}: {', '.join(item.name for item in added)}.", {
                "items": [_item_info(item, refs, {}) for item in added],
            }

        return self._edit(args["hero"], change)

    def change_item(self, args: dict) -> dict:
        def change(hero: Hero, profile: saves.SaveProfile, container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            changes: dict[str, Any] = {}
            if args.get("change_into"):
                entry, unique_name = _catalog_item(args["change_into"], self._catalog(hero, profile, container.name))
                rarity = args.get("rarity") or ("Unique" if unique_name else hero.item(index).rarity)
                if not (entry.id_known_at(rarity) and not entry.no_effect) and not args.get("allow_unconfirmed"):
                    raise ToolError(f"{_doubt(entry, rarity, owned=True)} Pass allow_unconfirmed to use it anyway.")
                changes["tag"] = entry.tag_at(rarity)
                if unique_name and not args.get("rarity"):
                    changes["rarity"] = "Unique"
            if args.get("rarity"):
                changes["rarity"] = args["rarity"]
            if args.get("power") is not None:
                changes["power"] = _number(args, "power", 0, 0, MAX_ITEM_POWER)
            if args.get("count") is not None:
                changes["count"] = _number(args, "count", 1, 1, MAX_STACK)
            if not changes:
                raise ToolError("Say what to change: rarity, power, count or change_into.")
            before = hero.item(index).name
            hero.update_item(index, **changes)
            item = hero.item(index)
            text = f"Changed the {before}: now the {item.name}" + ("." if item.ungraded else f", {item.rarity}, power {format_amount(item.power)}.")
            return text, {"item": _item_info(item, _refs(hero), {})}

        return self._edit(args["hero"], change)

    def set_item_effects(self, args: dict) -> dict:
        def change(hero: Hero, profile: saves.SaveProfile, container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            gear, enchantments = effect_choices(self._heroes_for_catalog(hero, profile, container.name))
            allow = bool(args.get("allow_unseen"))
            did = []
            if args.get("effects") is not None:
                wanted = args["effects"]
                if not isinstance(wanted, list) or not all(isinstance(name, str) for name in wanted):
                    raise ToolError("effects is a list of names from list_effects, e.g. [\"Critical Edge II\", \"Looter\"]. An empty list removes them.")
                if args.get("best_for") is not None:
                    raise ToolError("Give effects or best_for, not both: best_for chooses the effects itself.")
                hero.set_effects(index, [_effect_choice(name, gear, allow) for name in wanted])
                did.append("effects: " + (", ".join(effect.title for effect in hero.item(index).rolled_effects) or "none"))
            if args.get("best_for") is not None:
                did.append(_best_for(hero, index, str(args["best_for"]), gear))
            if args.get("enchantment") is not None:
                wanted = str(args["enchantment"]).strip()
                if wanted.lower() in ("", "none", "remove"):
                    hero.set_enchantment(index, None)
                    did.append("enchantment taken off")
                else:
                    hero.set_enchantment(index, _effect_choice(wanted, enchantments, allow))
                    did.append(f"enchanted with {hero.item(index).enchantment.title}")
            if args.get("soulstorm_enhanced") is not None:
                if not isinstance(args["soulstorm_enhanced"], bool):
                    raise ToolError("soulstorm_enhanced is true or false.")
                hero.set_soulstorm(index, args["soulstorm_enhanced"])
                did.append(f"made {SOULSTORM}" if args["soulstorm_enhanced"] else f"no longer {SOULSTORM}")
            if not did:
                raise ToolError(
                    "Say what to set: effects (a list of names from list_effects), best_for (a goal, for the editor's own picks), "
                    "enchantment (a name, or \"none\") or soulstorm_enhanced (true or false)."
                )
            item = hero.item(index)
            more = {"item": _item_info(item, _refs(hero), {})}
            if hero.item(index).enchantment is not None and not hero.vendors_opened()["Enchantsmith"]:
                more["heads_up"] = "This hero hasn't opened the Enchantsmith in the game yet."
            return f"The {item.name}: {'; '.join(did)}.", more

        return self._edit(args["hero"], change)

    def add_unique_effect(self, args: dict) -> dict:
        def change(hero: Hero, _profile: saves.SaveProfile, _container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            item = hero.item(index)
            hero.give_own_effect(index)
            return f"{the(item.name, start=True)} has its own effect now, saved the way the game saves it.", {"item": _item_info(hero.item(index), _refs(hero), {})}

        return self._edit(args["hero"], change)

    def set_talisman_level(self, args: dict) -> dict:
        def change(hero: Hero, _profile: saves.SaveProfile, _container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            level = args.get("level")
            if isinstance(level, float) and level.is_integer():
                level = int(level)
            try:
                hero.set_talisman_level(index, level)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
            item = hero.item(index)
            return f"{the(item.name, start=True)} is level {item.level + 1} now.", {"item": _item_info(item, _refs(hero), {})}

        return self._edit(args["hero"], change)

    def ready_talisman(self, args: dict) -> dict:
        def change(hero: Hero, _profile: saves.SaveProfile, _container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            item = hero.item(index)
            xp = hero.ready_talisman(index)
            text = (f"The {item.name}'s XP is {format_amount(xp)}, one short of level {item.level + 2}: the next XP earned in the "
                    "game with it equipped levels it up.")
            return text, {"item": _item_info(hero.item(index), _refs(hero), {})}

        return self._edit(args["hero"], change)

    def equip_item(self, args: dict) -> dict:
        def change(hero: Hero, profile: saves.SaveProfile, container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            item = hero.item(index)
            slots = slots_for(item.kind, item.piece, self._slots(hero, profile, container.name))
            if not slots:
                raise ToolError(f"The {item.name} doesn't go in a gear slot the editor knows.")
            slot = _pick_slot(slots, args.get("slot"), hero, args.get("ignore_slot_levels"))
            replaced = hero.equip(index, slot, check_level=not args.get("ignore_slot_levels"))
            text = f"Equipped the {item.name} ({slot.label.lower()})."
            if replaced is not None:
                text += f" The {replaced.name} went back to the inventory."
            return text, {}

        return self._edit(args["hero"], change)

    def unequip_item(self, args: dict) -> dict:
        def change(hero: Hero, _profile: saves.SaveProfile, _container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            item = hero.item(index)
            if not item.equipped_slot:
                raise ToolError(f"The {item.name} isn't equipped.")
            hero.unequip(index)
            return f"Unequipped the {item.name}; it's in the inventory.", {}

        return self._edit(args["hero"], change)

    def copy_item(self, args: dict) -> dict:
        def change(hero: Hero, _profile: saves.SaveProfile, _container: saves.Container) -> tuple[str, dict]:
            item = hero.item(hero.duplicate_item(_index_of(hero, args["item"])))
            return f"Copied the {item.name} into the inventory.", {"item": _item_info(item, _refs(hero), {})}

        return self._edit(args["hero"], change)

    def delete_item(self, args: dict) -> dict:
        def change(hero: Hero, _profile: saves.SaveProfile, _container: saves.Container) -> tuple[str, dict]:
            index = _index_of(hero, args["item"])
            name = hero.item(index).name
            hero.remove_item(index)
            return f"Deleted the {name}.", {}

        return self._edit(args["hero"], change)

    def apply_preset(self, args: dict) -> dict:
        preset = next((p for p in presets.PRESETS if p.title.lower() == str(args["preset"]).strip().lower()), None)
        if preset is None:
            raise ToolError(f"There's no preset {args['preset']!r}. list_presets shows them.")

        def change(hero: Hero, profile: saves.SaveProfile, container: saves.Container) -> tuple[str, dict]:
            catalog = self._catalog(hero, profile, container.name)
            check_level = not args.get("ignore_slot_levels")
            equip = args.get("equip")
            plan = presets.plan(
                preset,
                hero,
                catalog,
                _number(args, "power", hero.best_power(), 0, MAX_ITEM_POWER),
                bool(args.get("include_unconfirmed")),
                rarity=args.get("rarity") or "Unique",
                equip=preset.equip if equip is None else bool(equip),
                slots=self._slots(hero, profile, container.name),
                check_level=check_level,
            )
            lines = presets.describe(plan, hero)
            if not lines:
                raise ToolError(f"{preset.title} has nothing to change for this hero.")
            presets.apply(plan, hero, catalog, game_caps=True, check_level=check_level)
            more: dict[str, Any] = {"preset_did": lines}
            left_out = [
                f"{kit.name} ({'effect not known yet' if found.id_trusted_at(presets.rarity_for(kit, found, plan.rarity)) else 'best-guess save ID'})"
                for kit, found in plan.unconfirmed
            ]
            if left_out:
                more["left_out"] = left_out + [
                    "Pass include_unconfirmed to add these anyway; the game may remove a best-guess item, and a talisman "
                    "without its effect may do nothing."
                ]
            return f"Applied {preset.title}.", more

        return self._edit(args["hero"], change)

    def discard_changes(self, args: dict) -> dict:
        container = self._container(self._profile(), args["hero"])
        draft = self.drafts.pop(container.name, None)
        return {"done": "Threw the unsaved changes away." if draft else "There were no unsaved changes."}

    def save_changes(self, args: dict) -> dict:
        profile = self._profile()
        container = self._container(profile, args["hero"])
        draft = self.drafts.get(container.name)
        if draft is None or draft.document == draft.original:
            return {"done": "There's nothing to save."}
        document, problems = draft.document, []
        current = container.decoded.document
        if current != draft.original:  # the game saved the hero since the first change: keep both
            document, problems = merge.reapply(draft.original, draft.document, current)
        changes = describe_changes(current, document)
        if not changes:
            self.drafts.pop(container.name, None)
            return {"done": "The saved hero already has all of these changes.", "problems": problems}
        try:
            backup = profile.save(container.name, document, self.backup_root)
        except saves.StaleSaveError as exc:
            raise ToolError("The game saved the hero at the same moment; run save_changes again.") from exc
        except saves.SaveFailedError as exc:
            raise ToolError(f"{exc} Your saves were put back as they were.") from exc
        self.drafts.pop(container.name, None)
        result = {
            "done": "Saved. Start the game to see the changes.",
            "saved_changes": changes,
            "backup": backup.name,
            "undo": "The editor's Restore a backup… puts the save from before this back.",
        }
        if problems:
            result["problems"] = problems
        if format_caution(Hero(document)):
            result["caution"] = format_caution(Hero(document))
        return result

    # ------------------------------------------------------------------- tools

    def _tools(self) -> list[Tool]:
        return [
            Tool("list_heroes", "List heroes", "The heroes saved on this PC, with their ids, level and emeralds, and whether the game is running.",
                 {}, self.list_heroes, read_only=True),
            Tool("get_hero", "Show a hero", "A hero's stats (with the game's caps), the gear in each of the 12 slots, the inventory and the Village "
                 "Merchant's stock. Each item has a ref to use in the other tools. Shows unsaved changes too.",
                 {"hero": HERO}, self.get_hero, ("hero",), read_only=True),
            Tool("find_items", "Find items", "Search every weapon, armor piece, artifact, talisman and enchantment book the editor knows "
                 "by name (Uniques included). "
                 "confirmed: false means the save ID is a best guess; unique_confirmed says whether the Unique's own ID has "
                 "been seen (unique_by_pattern: it hasn't, but it follows the pattern every seen one does, and can be added). "
                 "effect_known: false marks a talisman the editor can only add without its effect. A book's enchantment says "
                 "what its enchantment does and what it goes on.",
                 {"query": _string("Part of a name, e.g. 'mystic' or 'Oracle Crown'."),
                  "kind": _string("Melee, Ranged, Armor, Artifact, Talisman or Enchantment Book.",
                                  enum=["Melee", "Ranged", "Armor", "Artifact", "Talisman", BOOK_KIND]),
                  "confirmed_only": _flag("Only items known to work: the save ID has been seen in a real save, and for a talisman its effect too."),
                  "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 25}},
                 self.find_items, read_only=True),
            Tool("list_presets", "List presets", "Ready-made goals (Most money, Most XP, ...), the most powerful gear, and complete kits from top builds.",
                 {}, self.list_presets, read_only=True),
            Tool("list_effects", "List effects", "The gear effects and enchantments the editor can put on an item, with their tiers: the ones seen "
                 "in real saves so far, and anything on an item in these saves.",
                 {"query": _string("Part of a name, e.g. 'critical' or 'smite'.")}, self.list_effects, read_only=True),
            Tool("set_stats", "Set stats", "Change stats: Emeralds, Echo shards (SpringStone), Enchantment points, Level, XP and the town upgrade "
                 "levels. Stops at the game's caps unless ignore_caps.",
                 {"hero": HERO, "stats": {"type": "object", "description": "Stat name to value, e.g. {\"Emeralds\": 9999, \"Level\": 12}.",
                                          "additionalProperties": {"type": "number"}},
                  "ignore_caps": _flag("Go past the game's caps (anything above them is lost in the game).")},
                 self.set_stats, ("hero", "stats")),
            Tool("add_item", "Add an item", "Add any item from find_items to the inventory, optionally equipped. A Unique's own name (e.g. Oracle "
                 "Crown), or its base item at Unique rarity, adds the Unique, which has a save ID of its own, with the effect "
                 "it comes with in the game (unique_effect). Where the editor hasn't seen how the game saves that effect, the "
                 "item says so in unique_effect_note: tell the user. Power defaults to the hero's strongest item.",
                 {"hero": HERO, "item": _string("The item's name or save ID from find_items."), "rarity": RARITY, "power": POWER,
                  "count": COUNT, "equip": {"type": ["boolean", "string"], "description": "true to equip it in the first free slot, or a slot name."},
                  "allow_unconfirmed": UNCONFIRMED, "ignore_slot_levels": LOCKED},
                 self.add_item, ("hero", "item")),
            Tool("add_enchantment_books", "Add every enchantment book", "Give a hero every enchantment book the editor knows that it's "
                 "without (add_item adds a single one), each saved the way the game saves a book. With a book in the "
                 "inventory the Enchantsmith offers its enchantment for the gear it goes on (checked in the game with books the "
                 "editor added).",
                 {"hero": HERO}, self.add_enchantment_books, ("hero",)),
            Tool("change_item", "Change an item", "Change an item's rarity, power or count, or turn it into another item (not while equipped). "
                 "A talisman has no rarity or power to change, and an enchantment book can't be changed at all: delete it, or add another.",
                 {"hero": HERO, "item": ITEM, "rarity": RARITY, "power": POWER, "count": COUNT,
                  "change_into": _string("Another item's name or save ID."), "allow_unconfirmed": UNCONFIRMED},
                 self.change_item, ("hero", "item")),
            Tool("set_item_effects", "Set an item's effects", "Give a weapon, armor piece or artifact its effects (in place of the ones the game "
                 "rolled), and a weapon or armor piece its enchantment, from list_effects. Leave either out to keep what the item "
                 "has. A name without a tier gets the highest tier a save has shown. Or give best_for and the editor picks: "
                 "the best effects for that goal out of the ones the game can roll on this very item (it rolls from the pool of "
                 "the item's slot and of each archetype the item carries), ahead of the effects it has. Which is best is the "
                 "editor's judgement, not a measurement. soulstorm_enhanced puts on, or takes off, the mark the game shows as "
                 "Soulstorm Enhanced: gear from a Soul Storm's reward chest has it, along with one more effect than its rarity "
                 "usually gets, which is yours to add with effects.",
                 {"hero": HERO, "item": ITEM,
                  "best_for": {"type": "string", "enum": [goal.name for goal in recommend.GOALS if goal.order],
                               "description": "A goal, instead of effects. The answer says what was picked, kept and taken off."},
                  "effects": {"type": "array", "items": {"type": "string"},
                              "description": "Names from list_effects, with a tier if you like: [\"Critical Edge II\", \"Looter\"]. At most 4; [] removes them."},
                  "enchantment": _string("An enchantment from list_effects, with a tier if you like (\"Healing Smite I\"), or \"none\" to take it off."),
                  "soulstorm_enhanced": {"type": "boolean", "description": "true makes the item Soulstorm Enhanced, false takes that off. Left out, it stays as it is."},
                  "allow_unseen": _flag("Allow a tier no save has shown yet (seen: false). If the game doesn't know it as written, it may drop the effect or the item.")},
                 self.set_item_effects, ("hero", "item")),
            Tool("add_unique_effect", "Give a Unique its own effect", "Give a Unique that's without it (unique_effect_note) the effect it comes with "
                 "in the game, saved the way the game saves it. For a Unique an older version of the editor made. It can't be done "
                 "for a Unique whose own effect the editor hasn't seen in a save.",
                 {"hero": HERO, "item": ITEM}, self.add_unique_effect, ("hero", "item")),
            Tool("set_talisman_level", "Set a talisman's level", "Put a talisman at level 1, 2 or 3, saved the way the game "
                 "saves a level-up: its level, its effect at that level, and enough XP for it. For a companion's talisman, "
                 "which levels up another way, use ready_talisman instead.",
                 {"hero": HERO, "item": ITEM, "level": {"type": "integer", "minimum": 1, "maximum": 3, "description": "1 is the level a talisman starts at."}},
                 self.set_talisman_level, ("hero", "item", "level")),
            Tool("ready_talisman", "Ready a talisman to level up", "Put a talisman one XP short of its next level: the game levels it up the next time it "
                 "earns XP while equipped. A talisman's effect follows its level, which only the game changes.",
                 {"hero": HERO, "item": ITEM}, self.ready_talisman, ("hero", "item")),
            Tool("equip_item", "Equip an item", "Put an item on. Whatever was in the slot goes back to the inventory.",
                 {"hero": HERO, "item": ITEM, "slot": SLOT, "ignore_slot_levels": LOCKED}, self.equip_item, ("hero", "item")),
            Tool("unequip_item", "Unequip an item", "Take an item off; it stays in the inventory.",
                 {"hero": HERO, "item": ITEM}, self.unequip_item, ("hero", "item")),
            Tool("copy_item", "Copy an item", "Add a copy of an item (or of an item in the merchant's stock) to the inventory.",
                 {"hero": HERO, "item": ITEM}, self.copy_item, ("hero", "item")),
            Tool("delete_item", "Delete an item", "Delete an item from the inventory (unequip it first).",
                 {"hero": HERO, "item": ITEM}, self.delete_item, ("hero", "item")),
            Tool("apply_preset", "Apply a preset", "Apply a preset from list_presets: set stats, and add and equip its gear at the power and rarity given. "
                 "Items with best-guess save IDs, and talismans whose effect isn't known, are left out unless include_unconfirmed. "
                 "A kit's gear gets the effects the game would roll for it, and once the hero has unlocked the Enchantsmith, an "
                 "enchantment on every weapon and armor piece (the build's pick where the editor can write it, else its own pick, a "
                 "different one on each piece) and the books of the enchantments the build names.",
                 {"hero": HERO, "preset": _string("The preset's name from list_presets."), "power": POWER,
                  "rarity": RARITY, "equip": {"type": "boolean", "description": "Equip the gear it adds (kits and gear presets do by default)."},
                  "include_unconfirmed": _flag("Also add items whose save ID is a best guess (the game may remove them) and "
                                               "talismans without their effect (they may do nothing)."),
                  "ignore_slot_levels": LOCKED},
                 self.apply_preset, ("hero", "preset")),
            Tool("preview_changes", "Preview changes", "The hero's unsaved changes in plain English. Show these to the user before save_changes.",
                 {"hero": HERO}, self.preview_changes, ("hero",), read_only=True),
            Tool("save_changes", "Save to the game", "Write the hero's unsaved changes to the game's save. Minecraft Dungeons II must be closed. "
                 "The whole save folder is backed up first. Get the user's OK first.",
                 {"hero": HERO}, self.save_changes, ("hero",), destructive=True),
            Tool("discard_changes", "Discard changes", "Throw away the hero's unsaved changes.",
                 {"hero": HERO}, self.discard_changes, ("hero",)),
        ]


class _ProtocolError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _number(args: dict, name: str, default: int, low: int, high: int) -> int:
    value = args.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer():
        raise ToolError(f"{name} must be a whole number.")
    if not low <= value <= high:
        raise ToolError(f"{name} must be between {low:,} and {high:,}.")
    return int(value)


def _stat_name(key: str, names: set[str]) -> str:
    """'Echo shards', 'echo_shards' and 'SpringStone' all mean SpringStone."""
    def squash(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    wanted = squash(str(key))
    for name in names:
        if wanted in (squash(name), squash(ATTRIBUTE_LABELS.get(name, ""))):
            return name
    raise ToolError(f"This hero has no stat {key!r}. It has: {', '.join(ATTRIBUTE_LABELS.get(n, n) for n in sorted(names))}.")


def _refs(hero: Hero) -> dict[int, str]:
    """A ref for each item that stays the same while other items are added or deleted (from its random seed)."""
    refs = {}
    for (seed, occurrence), item in items_by_identity(hero).items():
        if isinstance(seed, tuple):
            ref = f"i{item.index}"
        else:
            ref = str(seed) if occurrence == 0 else f"{seed}.{occurrence}"
        refs[item.index] = ref
    return refs


def _index_of(hero: Hero, ref: Any) -> int:
    ref = str(ref).strip()
    for index, candidate in _refs(hero).items():
        if candidate == ref:
            item = hero.item(index)
            if item.is_cosmetic:
                raise ToolError("Cosmetics come from your game edition and can't be changed.")
            return index
    raise ToolError(f"There's no item with ref {ref!r}. get_hero shows the refs.")


def _item_info(item: Item, refs: dict[int, str], catalog: dict[str, CatalogItem]) -> dict:
    known = game_item(item.tag)
    entry = catalog.get(item.tag)
    info = {
        "ref": refs.get(item.index),
        "name": item.name,
        "id": item.tag,
        "kind": item.kind,
        "rarity": item.rarity,
        "power": item.power,
        "count": item.count,
        "where": item.where,
    }
    if item.ungraded:  # a talisman or a book has neither: the game saves SW.Rarity.None and power -1
        del info["rarity"], info["power"]
    if item.is_book:
        info["enchantment"] = book_text(item.tag)
    if item.is_talisman:
        info["talisman_level"] = item.level + 1 if isinstance(item.level, int) else item.level
        info["xp"] = item.xp
        if item.next_level_xp is not None and item.level == 0:
            info["xp_for_next_level"] = item.next_level_xp
        if not item.progression.get("ItemLevels"):
            info["note"] = "No effect is saved with this talisman, so it may do nothing in the game."
    if item.piece:
        info["piece"] = item.piece
    if item.level:
        info["item_level"] = item.level
    if item.effects:  # as the game saved them; set_item_effects changes the rolled ones and the enchantment
        info["effects"] = [_effect_info(effect) for effect in item.effects]
    if item.is_soulstorm:
        info["soulstorm_enhanced"] = True
    if known is not None and is_unique_version(item.tag):
        if known.unique_effect:
            info["unique_effect"] = known.unique_effect  # what the Unique does in the game
        if item.own_effect_note:
            info["unique_effect_note"] = item.own_effect_note
    elif known is not None and known.unique:
        info["at_unique"] = known.unique
    if entry is not None and not entry.confirmed:
        info["confirmed"] = False
    return info


def _best_for(hero: Hero, index: int, name: str, gear: list[EffectChoice]) -> str:
    """Put the editor's picks for a goal on an item, ahead of the effects it has, and say what was done: what
    "Best for" does in the effects window."""
    goal = next((found for found in recommend.GOALS if found.name.lower() == name.strip().lower()), None)
    if goal is None:
        raise ToolError(f"best_for is one of: {', '.join(found.name for found in recommend.GOALS if found.order)}.")
    item = hero.item(index)
    if not item.can_have_effects:
        raise ToolError(f"{the(item.name, start=True)} can't have effects: the game rolls them on weapons, armor and artifacts.")
    elements = hero.elements_in_play() | ({item.element} if item.element else set())
    room = max(effect_book().max_effects - len(item.own_effects), 0)
    picked = recommend.best(goal, item.kind, item.archetypes, gear, room, elements, own={effect.tag for effect in item.own_effects})
    if not picked:
        raise ToolError(recommend.nothing(goal, item.name, item.kind, item.archetypes, gear))
    had = [effect.as_choice() for effect in item.rolled_effects]
    wanted = recommend.keep(picked, had, room)
    hero.set_effects(index, wanted)
    on_it = {choice.effect for choice in wanted}
    return recommend.explain(
        goal, item.name, item.kind, item.archetypes, picked, kept=wanted[len(picked):], dropped=[choice for choice in had if choice.effect not in on_it]
    )


def _effect_choice(wanted: str, choices: list[EffectChoice], allow_unseen: bool) -> EffectChoice:
    """The effect or enchantment an assistant named: 'Critical Edge II', or 'looter' for its best tier seen."""
    words = wanted.strip().split()
    tier = words[-1].upper() if len(words) > 1 and words[-1].upper() in TIERS else ""
    name = " ".join(words[:-1] if tier else words).lower()
    same = [choice for choice in choices if name in (choice.name.lower(), choice.maybe.lower(), choice.effect.rsplit(".", 1)[-1].lower())]
    if not same:
        raise ToolError(f"The editor can't write {wanted!r} yet: it hasn't seen it in a real save. list_effects shows what it can.")
    if not tier:
        found = presets._best(same) or same[0]
    else:
        found = next((choice for choice in same if choice.tier == tier), None)
        if found is None:
            raise ToolError(f"{same[0].name} is known at tier {', '.join(choice.tier for choice in same)}, not {tier}.")
    if not found.seen and not found.yours and not allow_unseen:
        raise ToolError(
            f"{found.title} hasn't been seen in a real save yet: its number is from the game files' table. If the game doesn't "
            "know it as written, it may drop the effect or the item. Pass allow_unseen to use it anyway."
        )
    return found


def _effect_info(effect: Effect) -> dict:
    info = {"name": effect.name, "id": effect.tag, "strength": effect.strength}
    if effect.tier:
        info["tier"] = effect.tier
    if effect.is_enchantment:
        info["enchantment"] = True
    if effect.is_own:
        info["unique_own"] = True  # the effect a Unique comes with; set_item_effects leaves it alone
    if effect.quality:
        info["quality"] = effect.quality
    if effect.points:
        info["enchantment_points"] = effect.points
    if effect.locked:
        info["locked"] = True
    return info


def _doubt(entry: CatalogItem, rarity: str | None, owned: bool = False) -> str:
    """Why adding this item is a best guess, for the assistant. For an item the hero ``owned`` already, a
    Unique's ID has to have been seen: its pattern isn't enough to risk the item on."""
    parts = []
    if not (entry.id_known_at(rarity) if owned else entry.id_trusted_at(rarity)):
        parts.append(
            f"The game's save ID for the {entry.name_at(rarity)} ({entry.tag_at(rarity)}) is a best guess, and in testing "
            "the game removed items whose guess was wrong."
        )
    if entry.no_effect:
        parts.append(
            f"The editor hasn't seen the {entry.name}'s effect in a real save yet, so it can only add this talisman "
            "without one, and it may do nothing in the game."
        )
    return " ".join(parts)


def _catalog_info(entry: CatalogItem) -> dict:
    info = {"name": entry.name, "id": entry.tag, "kind": entry.kind, "confirmed": entry.confirmed}
    if entry.no_effect:
        info["effect_known"] = False
    if entry.piece:
        info["piece"] = entry.piece
    if entry.unique:
        info["unique"] = entry.unique
        info["unique_confirmed"] = entry.unique_tag is not None
        if entry.by_pattern_at("Unique"):
            info["unique_by_pattern"] = True
    if entry.unique_effect:
        info["unique_effect"] = entry.unique_effect
        if entry.bare_unique_at("Unique"):
            info["unique_effect_note"] = NO_OWN_EFFECT
    known = game_item(entry.tag)
    if known is not None and known.effect:
        info["effect_at_level_3"] = known.effect
    if entry.kind == BOOK_KIND:
        info["enchantment"] = book_text(entry.tag)
    return info


def _catalog_item(wanted: Any, catalog: list[CatalogItem]) -> tuple[CatalogItem, bool]:
    """The catalog item for a name, a Unique's name or a save ID, and whether the Unique's name was used."""
    key = str(wanted).strip().lower()
    for entry in catalog:
        if entry.tag.lower() == key or entry.name.lower() == key:
            return entry, False
    for entry in catalog:
        if entry.unique and entry.unique.lower() == key:
            return entry, True
    close = [entry.name for entry in catalog if key and (key in entry.name.lower() or key in (entry.unique or "").lower())]
    hint = f" Did you mean: {', '.join(close[:8])}?" if close else " find_items searches the list."
    raise ToolError(f"There's no item called {wanted!r}.{hint}")


def _pick_slot(slots: list[GearSlot], wanted: str | None, hero: Hero, ignore_levels: bool) -> GearSlot:
    level = hero.level if isinstance(hero.level, int) else 1
    if wanted:
        key = "".join(ch for ch in str(wanted).lower() if ch.isalnum() or ch == " ").strip()
        key = _SLOT_WORDS.get(key, key).lower()
        match = next((slot for slot in slots if key in (slot.label.lower(), slot.label.lower().replace(" ", ""), slot.tag.lower().replace(".", ""))), None)
        if match is None:
            raise ToolError(f"That doesn't go in {wanted!r}. It fits: {', '.join(slot.label for slot in slots)}.")
        return match
    open_slots = [slot for slot in slots if ignore_levels or level >= slot.level]
    if not open_slots:
        raise ToolError(f"No slot for it is open yet at level {level}.")
    worn = {item.equipped_slot for item in hero.items() if item.equipped_slot}
    return next((slot for slot in open_slots if slot.tag not in worn), open_slots[0])


# --------------------------------------------------------------------- stdio


def _std_streams() -> tuple[BinaryIO, BinaryIO]:
    """stdin and stdout as bytes. The windowed .exe may have no Python streams even when the assistant's app
    connected pipes to it, so on Windows fall back to the process's own standard handles."""
    reader = getattr(sys.stdin, "buffer", None)
    writer = getattr(sys.stdout, "buffer", None)
    stdout_is_null = getattr(sys.stdout, "name", "") == os.devnull
    if os.name == "nt" and (reader is None or writer is None or stdout_is_null):
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = ctypes.c_void_p

        def stream(which: int, flags: int, mode: str):
            handle = kernel32.GetStdHandle(which)
            if handle in (None, 0, ctypes.c_void_p(-1).value):
                raise OSError("no standard input or output to talk over")
            raw = os.fdopen(msvcrt.open_osfhandle(handle, flags), mode, buffering=0)
            return io.BufferedReader(raw) if "r" in mode else raw

        reader = stream(-10, os.O_RDONLY | os.O_BINARY, "rb")  # STD_INPUT_HANDLE
        writer = stream(-11, os.O_WRONLY | os.O_BINARY, "wb")  # STD_OUTPUT_HANDLE
    if reader is None or writer is None:
        raise OSError("no standard input or output to talk over")
    return reader, writer


def serve_streams(server: EditorServer, reader: BinaryIO, writer: BinaryIO) -> None:
    """Answer newline-delimited JSON-RPC messages until the input ends."""
    while True:
        line = reader.readline()
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            reply = _error(None, -32700, "Parse error")
        else:
            reply = server.handle(message)
        if reply is not None:
            writer.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            writer.flush()


def serve(profile: Path | None = None, backup_root: Path = saves.DEFAULT_BACKUP_ROOT) -> int:
    """Run the MCP server on stdin and stdout until the assistant's app closes it."""
    try:
        reader, writer = _std_streams()
    except OSError as exc:
        print(f"The MCP server talks over stdin and stdout, and there are none: {exc}", file=sys.stderr)
        return 1
    serve_streams(EditorServer(profile, backup_root), reader, writer)
    return 0
