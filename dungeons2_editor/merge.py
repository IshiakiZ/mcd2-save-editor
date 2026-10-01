"""Re-applying the editor's changes to a newer copy of a save.

If the game saves a hero while the editor has it open (you played, or the Xbox
app synced), saving the editor's copy would throw away the game's progress. So
the editor takes the newer save and re-applies its own changes on top: stats by
name, items by their random seed (which never changes), everything else by path.
Whatever can't be re-applied safely is reported instead of guessed.
"""

from __future__ import annotations

import copy
from typing import Any

from . import document as doc
from .hero import EMPTY_SLOT, Hero, is_hero_document, items_by_identity

MISSING = doc.MISSING


def reapply(original: Any, edited: Any, newer: Any) -> tuple[Any, list[str]]:
    """``newer`` with the changes from ``original`` to ``edited`` applied, and what couldn't be."""
    if is_hero_document(original) and is_hero_document(edited) and is_hero_document(newer):
        return _reapply_hero(original, edited, newer)
    merged = copy.deepcopy(newer)
    return merged, _reapply_paths(original, edited, merged)


def _lookup(document: Any, path: tuple) -> Any:
    node = document
    for key in path:
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return MISSING
    return node


def _put(document: Any, path: tuple, value: Any) -> bool:
    """Set (or, for MISSING, delete) the value at ``path``. False if that can't be done safely."""
    parent = _lookup(document, path[:-1])
    key = path[-1]
    if isinstance(parent, dict):
        if value is MISSING:
            parent.pop(key, None)
        else:
            parent[key] = value
        return True
    if isinstance(parent, list) and isinstance(key, int) and value is not MISSING:
        if key < len(parent):
            parent[key] = value
            return True
        if key == len(parent):
            parent.append(value)
            return True
    return False


def _reapply_paths(original: Any, edited: Any, merged: Any, skip: tuple[tuple, ...] = (), where: str = "") -> list[str]:
    """Apply each changed value to ``merged``. A value reached only through dictionary keys is the same
    value in any copy, so the editor's value wins; one inside a list is only changed where the game
    left it alone, since the game may have moved things around."""
    problems = []
    for path, old, new in doc.diff(original, edited):
        if any(path[: len(prefix)] == prefix for prefix in skip):
            continue
        current = _lookup(merged, path)
        if doc._same(current, new):
            continue
        through_list = any(isinstance(key, int) for key in path)
        if (through_list and not doc._same(current, old)) or not _put(merged, path, new):
            problems.append(f"{where}{doc.describe_path(edited, path)}: the game changed this too, so the game's value was kept.")
    return problems


def _body_key(document: dict) -> str:
    key = str(document["SerializeMeta"].get("HardFormat", ""))[1:]
    return key if key in document else next((k for k in document if k != "SerializeMeta"), "")


def _reapply_hero(original: dict, edited: dict, newer: dict) -> tuple[dict, list[str]]:
    merged = copy.deepcopy(newer)
    old, new, out = Hero(original), Hero(edited), Hero(merged)
    problems: list[str] = []

    # Stats, by name. The editor's value wins: that's the change you asked for.
    before = {a["AttributeName"]: a.get("CurrentValue") for a in old.attributes()}
    changed = {a["AttributeName"]: a.get("CurrentValue") for a in new.attributes() if before.get(a["AttributeName"], MISSING) != a.get("CurrentValue")}
    present = {a["AttributeName"]: a for a in out.attributes()}
    for name, value in changed.items():
        if name in present:
            present[name]["CurrentValue"] = value
            if name == "Level" and "Level" in out.metadata:
                out.metadata["Level"] = int(value)
        else:
            problems.append(f"The newer save has no {name} stat, so that change was skipped.")

    # Items, by their random seed.
    old_items, new_items = items_by_identity(old), items_by_identity(new)
    out_items = items_by_identity(out)
    entries = out._entries()
    ours: set[int] = set()  # id() of entries whose equipped slot the editor set
    for key, edited_item in new_items.items():
        if key not in old_items:
            entry = copy.deepcopy(edited_item.entry)
            entries.append(entry)
            if edited_item.equipped_slot:
                ours.add(id(entry))
            continue
        original_item = old_items[key]
        if original_item.entry == edited_item.entry:
            continue
        target = out_items.get(key)
        if target is None:
            problems.append(f"{edited_item.name} isn't in the newer save any more, so your change to it was skipped.")
            continue
        problems += _reapply_paths(original_item.entry, edited_item.entry, target.entry, where=f"{edited_item.name}, ")
        if original_item.equipped_slot != edited_item.equipped_slot and edited_item.equipped_slot:
            ours.add(id(target.entry))
    removed = []
    for key, original_item in old_items.items():
        if key in new_items or key not in out_items:
            continue
        target = out_items[key]
        if target.equipped_slot:
            problems.append(f"{target.name} is equipped in the newer save, so it wasn't deleted.")
        else:
            removed.append(target.entry)
    entries[:] = [entry for entry in entries if not any(entry is gone for gone in removed)]

    # One item per gear slot: an item the editor equipped beats one the game put there since.
    for item in out.items():
        if item.equipped_slot and id(item.entry) not in ours:
            rival = next((other for other in out.items() if id(other.entry) in ours and other.equipped_slot == item.equipped_slot), None)
            if rival is not None:
                item.entry["EquippedSlot"] = EMPTY_SLOT
                problems.append(f"Unequipped {item.name} to make room for your {rival.name}.")

    # Item types the editor marked as discovered.
    body = _body_key(merged)
    old_loot = set((old.body.get("LootProgression") or {}).get("DiscoveredLoot") or [])
    loot = (out.body.get("LootProgression") or {}).get("DiscoveredLoot")
    if isinstance(loot, list):
        for tag in (new.body.get("LootProgression") or {}).get("DiscoveredLoot") or []:
            if tag not in old_loot and tag not in loot:
                loot.append(tag)

    # Anything else (Advanced mode edits).
    skip = ((body, "Ability", "Attributes"), (body, "Inventory", "Entries"), (body, "LootProgression", "DiscoveredLoot"), (body, "MetaData", "Level"))
    problems += _reapply_paths(original, edited, merged, skip=skip)
    return merged, problems
