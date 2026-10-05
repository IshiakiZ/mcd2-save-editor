"""What the two ways of editing a hero share: the Hero tab (Advanced mode) and the inventory screen
(Simple mode) apply typed stats and item values the same way, and their item actions (add, equip,
change, copy, delete, presets) do the same thing.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
from typing import Any

from . import document as doc
from .hero import (
    MAX_STAT, STAT_CAPS, GearSlot, Hero, Item, attribute_label, build_catalog, format_amount, game_item, gear_slots,
    is_unique_version, slots_for, talisman_levels, template_for,
)
from .item_picker import ItemPicker, slot_choice, slot_open
from .presets_dialog import PresetsDialog

SAVE_REMINDER = "Press Save to game when you're done."


def number_text(value: Any) -> str:
    return "" if value is None else doc.format_value(value)


def power_text(item: Item) -> str:
    """What an item's power box shows: nothing for a talisman, which has no power."""
    return "" if item.is_talisman else number_text(item.power)


def talisman_hint(item: Item) -> str:
    """What to say about a talisman where other items show their rarity and power."""
    hint = "A talisman has no rarity or power. It levels up from the XP you earn while you wear it."
    if item.progression.get("ItemLevels"):
        return hint
    fix = " Delete it and add it again to get one with its effect." if talisman_levels(item.tag) else ""
    return f"{hint} This one has no effect saved, so it may do nothing in the game.{fix}"


class HeroEditing:
    """Mixed into a Tk widget that shows a hero.

    The widget has ``hero``, ``advanced``, ``stat_vars`` (stat name -> StringVar), ``power_var``,
    ``count_var``, ``selected`` and ``_shown`` (the inventory entry picked, and the one whose values
    are in the fields), ``icons``, ``catalog_heroes``, ``on_change``, ``app_title``, ``equip_button``
    and ``_guessed_slot_ok``. It shows messages with ``_say_stats`` and ``_say_item``, and redraws with
    ``_fill_items`` (everything about items, keeping the picked one), ``_show_item`` and
    ``_update_summary``.
    """

    # ------------------------------------------------------------- typed values

    def has_pending_input(self) -> bool:
        """Whether something has been typed into a field but not applied yet."""
        if self.hero is None:
            return False
        if any(var.get().strip() != number_text(self.hero.attribute(name)) for name, var in self.stat_vars.items()):
            return True
        if self._shown is None or self._shown >= len(self.hero.items()):
            return False
        item = self.hero.item(self._shown)
        return not item.is_cosmetic and (
            self.power_var.get().strip() != power_text(item) or self.count_var.get().strip() != str(item.count)
        )

    def commit_pending(self) -> bool:
        """Apply anything typed but not applied yet. False if something typed is invalid."""
        ok = all([self._apply_stat(name) for name in list(self.stat_vars)])
        return self._apply_numbers() and ok

    def _apply_stat(self, name: str) -> bool:
        if self.hero is None or name not in self.stat_vars:
            return True
        var = self.stat_vars[name]
        current = self.hero.attribute(name)
        if var.get().strip() == number_text(current):
            return True
        like = current if isinstance(current, (int, float)) and not isinstance(current, bool) else 0
        try:
            value = doc.parse_input(var.get(), like)
            self.hero.set_attributes({name: value}, game_caps=not self.advanced)
        except (ValueError, KeyError) as exc:
            var.set(number_text(current))
            message = f"{attribute_label(name)}: {exc}"
            if name in STAT_CAPS and not self.advanced:
                message += " That's the game's cap; anything above it is lost in the game."
            self._say_stats(message, error=True)
            return False
        var.set(number_text(self.hero.attribute(name)))
        message = f"{attribute_label(name)} is now {format_amount(value)}. {SAVE_REMINDER}"
        if name == "Level":
            message += " In testing, level 10 stuck but level 100 was put back to 1, so change it in small steps."
        if value > STAT_CAPS.get(name, MAX_STAT):
            message = f"{attribute_label(name)} is now {format_amount(value)}, above the game's cap of {format_amount(STAT_CAPS[name])}, so the game may lower it."
        self._say_stats(message)
        self._update_summary()
        self.on_change()
        return True

    def _apply_item(self, **changes: Any) -> bool:
        if self.hero is None or self._shown is None:
            return True
        index = self._shown
        try:
            self.hero.update_item(index, **changes)
        except ValueError as exc:
            self._show_item(index)
            self._say_item(str(exc), error=True)
            return False
        self._fill_items()  # keeps whichever item is selected
        self._say_item(f"Changed. {self._unique_note(index, changes)}{SAVE_REMINDER}")
        self.on_change()
        return True

    def _unique_note(self, index: int, changes: dict) -> str:
        """What making an item Unique did: a Unique has an ID of its own, and the editor only uses one it knows."""
        if changes.get("rarity") != "Unique":
            return ""
        item = self.hero.item(index)
        known = game_item(item.tag)
        if known is None or not known.unique:
            return ""
        if is_unique_version(item.tag):
            return f"It's {'' if item.name.startswith('The ') else 'the '}{item.name} now. "
        return (
            f"It's a Unique-rarity {item.name}, not the {known.unique}: the editor hasn't seen that Unique's own ID in a "
            "save yet, and won't risk an item you own on it. Add items can add one. "
        )

    def _apply_numbers(self) -> bool:
        if self.hero is None or self._shown is None:
            return True
        item = self.hero.item(self._shown)
        if item.is_cosmetic:
            return True
        changes = {}
        try:
            if self.power_var.get().strip() != power_text(item):
                changes["power"] = doc.parse_input(self.power_var.get(), item.power if item.power is not None else 0)
            if self.count_var.get().strip() != str(item.count):
                changes["count"] = doc.parse_input(self.count_var.get(), item.count)
        except ValueError as exc:
            self._show_item(self._shown)
            self._say_item(str(exc), error=True)
            return False
        return self._apply_item(**changes) if changes else True

    # ----------------------------------------------------------- what's known

    def _heroes(self) -> list[Hero]:
        heroes = [self.hero] if self.hero is not None else []
        return heroes + [hero for hero in self.catalog_heroes() if hero is not None]

    def _catalog(self):
        return build_catalog(self._heroes())

    def _slots(self) -> list[GearSlot]:
        return gear_slots(self._heroes())

    def _equipped_names(self) -> dict[str, str]:
        return {item.equipped_slot: item.name for item in self.hero.items() if item.equipped_slot} if self.hero else {}

    def _hero_level(self) -> int | None:
        """The level that opens gear slots, or None in Advanced mode, which doesn't check."""
        return None if self.advanced or self.hero is None else self.hero.level

    # ----------------------------------------------------------------- actions

    def open_add_items(self, for_slot: GearSlot | None = None) -> None:
        """Add items; with ``for_slot``, only items for that slot, equipped there."""
        if self.hero is None:
            return
        catalog = self._catalog()

        def add(tag: str, rarity: str, power: int, count: int, slot: GearSlot | None) -> None:
            template = template_for(tag, catalog)
            if template is None:
                raise ValueError("There's no item in your saves to copy the layout from yet.")
            self.selected = self.hero.add_item(
                tag, template, rarity=rarity, power=power, count=count, slot=slot, check_level=not self.advanced
            )
            self._fill_items()
            self._say_item(f"Added. {SAVE_REMINDER}")
            self.on_change()

        ItemPicker(
            self,
            catalog,
            self.icons,
            mode="add",
            advanced=self.advanced,
            best_power=self.hero.best_power(),
            slots=self._slots(),
            equipped=self._equipped_names,
            hero_level=self._hero_level(),
            on_add=add,
            for_slot=for_slot,
        )

    def equip_item(self) -> None:
        """Equip the selected item (asking which slot when there's a choice), or unequip it."""
        if self.hero is None or self._shown is None:
            return
        item = self.hero.item(self._shown)
        if item.equipped_slot:
            self._take_off(self._shown)
            return
        slots = slots_for(item.kind, item.piece, self._slots())
        if len(slots) == 1:
            self._equip(slots[0])
            return
        menu = tk.Menu(self, tearoff=False)
        equipped = self._equipped_names()
        level = self._hero_level()
        for slot in slots:
            menu.add_command(
                label=slot_choice(slot, equipped.get(slot.tag), level),
                state="normal" if slot_open(slot, level) else "disabled",
                command=lambda slot=slot: self._equip(slot),
            )
        menu.tk_popup(self.equip_button.winfo_rootx(), self.equip_button.winfo_rooty() + self.equip_button.winfo_height())

    def _equip(self, slot: GearSlot) -> None:
        if self.hero is None or self._shown is None or not self._accept_guessed_slot(slot):
            return
        try:
            replaced = self.hero.equip(self._shown, slot, check_level=not self.advanced)
        except ValueError as exc:
            self._say_item(str(exc), error=True)
            return
        text = f"Equipped ({slot.label.lower()})."
        if replaced is not None:
            text += f" Your {replaced.name} went back to your inventory."
        self._fill_items()
        self._say_item(f"{text} {SAVE_REMINDER}")
        self.on_change()

    def _take_off(self, index: int | None) -> None:
        if self.hero is None or index is None:
            return
        self.hero.unequip(index)
        self._fill_items()
        self._say_item(f"Unequipped. It's in your inventory. {SAVE_REMINDER}")
        self.on_change()

    def _accept_guessed_slot(self, slot: GearSlot) -> bool:
        """Ask once before using a slot whose name in the game is a best guess."""
        if slot.confirmed or self._guessed_slot_ok:
            return True
        self._guessed_slot_ok = messagebox.askyesno(
            "Unconfirmed slot",
            f"The game's name for the {slot.label.lower()} slot hasn't been seen in a real save yet, so the editor "
            "is making a best guess.\n\nIf the guess is wrong, the game may leave the item unequipped, or may not "
            "load this hero until you undo the change with Restore… (a backup is made every time you save).\n\n"
            f"Equip any {slot.kind.lower()} in the game once and the editor learns the slot's real name.\n\nEquip it anyway?",
            parent=self,
        )
        return self._guessed_slot_ok

    def open_presets(self) -> None:
        if self.hero is None or not self.commit_pending():
            return
        PresetsDialog(
            self,
            hero=self.hero,
            catalog=self._catalog(),
            advanced=self.advanced,
            on_applied=self._after_preset,
            text_font=tkfont.nametofont("TkDefaultFont"),
            slots=self._slots(),
            icons=self.icons,
        )

    def _after_preset(self) -> None:
        self.refresh()
        self._say_stats(f"Preset applied. {SAVE_REMINDER}")
        self.on_change()

    def change_item(self) -> None:
        if self.hero is None or self._shown is None:
            return
        picker = ItemPicker(self, self._catalog(), self.icons, mode="choose", advanced=self.advanced)
        self.wait_window(picker)
        if picker.result:
            self._apply_item(tag=picker.result)

    def copy_item(self) -> None:
        if self.hero is None or self._shown is None:
            return
        try:
            self.selected = self.hero.duplicate_item(self._shown)
        except ValueError as exc:
            self._say_item(str(exc), error=True)
            return
        self._fill_items()
        self._say_item(f"Copied into your inventory. {SAVE_REMINDER}")
        self.on_change()

    def delete_item(self) -> None:
        if self.hero is None or self._shown is None:
            return
        item = self.hero.item(self._shown)
        if item.is_cosmetic or item.equipped_slot:
            return
        if not messagebox.askyesno(self.app_title, f"Delete the {item.name}?", parent=self):
            return
        try:
            self.hero.remove_item(self._shown)
        except ValueError as exc:
            self._say_item(str(exc), error=True)
            return
        self.selected = self._shown = None
        self._fill_items()
        self._say_item(f"Deleted. {SAVE_REMINDER}")
        self.on_change()
