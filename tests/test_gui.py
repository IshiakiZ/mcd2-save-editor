import copy
import dataclasses
import gc
import json
import sys
import tempfile
import time
import tkinter as tk
import unittest
import urllib.parse
from pathlib import Path
from tkinter import ttk
from unittest import mock

from dungeons2_editor import __version__, game_style, gui, layout, recorder, saves, share_ids, updater, wgs, whats_new, world_dialog
from dungeons2_editor.effects_dialog import EffectsDialog
from dungeons2_editor.hero import BOOK_KIND, Hero, effect_choices, use_local_names
from dungeons2_editor.item_picker import ItemPicker
from dungeons2_editor.restore_dialog import RestoreDialog

from .helpers import (
    SETTINGS_TEXT, enchanted, enchantment_effect, hero_item, hero_save, hero_save_text, hero_with_a_world, make_profile, recordings_of_a_world, rolled,
    rolled_effect, shift_encode, talisman_item,
)

HERO = "Character00000000-0000-1000-8000-000000000002"
OTHER_HERO = "Character00000000-0000-1000-8000-000000000003"


def snapshot_of(folder: Path) -> dict:
    """Every file under a folder with what's in it: to see that looking changed nothing."""
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(Path(folder).rglob("*")) if path.is_file()}


def _tk_available() -> bool:
    # On a Mac, Tk never runs out of things to do once the editor's window is up: update(), which these tests call
    # to let the window settle, doesn't come back there. The window itself is alive (its timers keep their time,
    # and nothing in the editor's own code is spinning), so until someone with a Mac finds what keeps Tk busy,
    # the window tests run on Windows and Linux only.
    if sys.platform == "darwin":
        return False
    try:
        tk.Tk().destroy()
    except tk.TclError:
        return False
    return True


def _display_scaling() -> float | None:
    """The display's own scaling (Tk's pixels per point), read before any test changes it. Tk keeps the
    scaling for the whole process, not for one window: a test that sets it would otherwise pass it on to
    every test after it."""
    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    try:
        return float(root.tk.call("tk", "scaling"))
    finally:
        root.destroy()


DISPLAY_SCALING = _display_scaling()


class WindowTestCase(unittest.TestCase):
    """Opens the editor on a temporary save folder, in Simple or Advanced mode."""

    containers: dict = {}
    advanced = False
    scaling: float | None = None  # Tk's pixels per point: 1.3333 on a display at 100%, 2.0 at 150%
    look: str | None = None  # Simple mode's look, as the settings file names it; None: nothing chosen yet (the original)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.profile_path = make_profile(self.dir / "saves", self.containers)
        self.settings_file = self.dir / "settings.json"
        self.settings_file.write_text(json.dumps({"advanced": self.advanced, **({"look": self.look} if self.look else {})}), encoding="utf-8")
        patcher = mock.patch.object(saves, "running_game_processes", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        # The play recorder's recordings are looked for here, never in the folder of whoever runs the tests.
        patcher = mock.patch.object(recorder, "DEFAULT_OUT", self.dir / "recordings")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.tk.call("tk", "scaling", self.scaling or DISPLAY_SCALING)
        self.addCleanup(gc.collect)  # frees Tk objects on the main thread, after the window is destroyed
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.root.tk.call, "tk", "scaling", DISPLAY_SCALING)  # before the window goes: back to the display's own
        self.make_icons()
        self.names_file = self.dir / "item-names.json"
        self.addCleanup(use_local_names, {})  # names given in a test don't leak into the next
        with mock.patch.object(saves, "find_profiles", return_value=[]):
            self.app = gui.EditorApp(self.root, self.profile_path, self.dir / "backups", self.dir / "icons", self.settings_file, self.names_file)
        self.root.update()

    def make_icons(self):
        pass

    def container_names(self):
        return [c.name for c in self.app._containers_by_iid.values()]

    def show_on_screen(self, dialog):
        """Windows are hidden in these tests; this one needs its real layout."""
        self.root.deiconify()
        dialog.deiconify()
        dialog.update()
        if not dialog.winfo_viewable():
            self.skipTest("windows can't be shown here")

    def needs_room_for(self, window):
        """Skip a check of what happens when a window that fits is made smaller, on a screen that can't show the
        window whole to begin with (GitHub's Windows machines sometimes come with an 800x600 one)."""
        room = layout.screen_room(window)
        if room[0] < window.winfo_reqwidth() or room[1] < window.winfo_reqheight():
            self.skipTest(f"this screen ({window.winfo_screenwidth()}x{window.winfo_screenheight()}) is too small to show the window whole")

    def assert_in_view(self, button, dialog):
        self.assertTrue(button.winfo_ismapped())
        self.assertGreater(button.winfo_height(), 5)
        self.assertGreaterEqual(button.winfo_rooty(), dialog.winfo_rooty())
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), dialog.winfo_rooty() + dialog.winfo_height())
        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), dialog.winfo_rootx() + dialog.winfo_width())


@unittest.skipUnless(_tk_available(), "needs a display")
class AdvancedSettingsTests(WindowTestCase):
    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), "auth_dynamic_entjwtbin": b"\x01\x02secret"}
    advanced = True

    def find_row(self, path):
        for depth in range(1, len(path)):
            self.app._expand(next(i for i, p in self.app.node_paths.items() if p == path[:depth]))
        return next(iid for iid, node_path in self.app.node_paths.items() if node_path == path)

    def select(self, path):
        iid = self.find_row(path)
        self.app.tree.selection_set(iid)
        self.root.update()
        return iid

    def test_opens_the_settings_save_in_advanced_mode(self):
        self.assertEqual(self.app.container.name, "GlobalSaveDataDefault")
        self.assertEqual(sorted(self.container_names()), ["GlobalSaveDataDefault", "auth_dynamic_entjwtbin"])
        self.assertEqual(self.app.notebook.tab(self.app.hero_tab, "state"), "hidden")
        self.assertEqual(self.app.notebook.tab(self.app.edit_tab, "state"), "normal")

    def test_edit_and_save(self):
        iid = self.select(("blobs", 0, "masterVolume"))
        self.assertEqual(self.app.value_var.get(), "60")
        self.app.value_var.set("85")
        self.app.apply_value()
        self.assertEqual(self.app.change_count, 1)
        self.assertIn("changed", self.app.tree.item(iid, "tags"))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask, mock.patch("tkinter.messagebox.showinfo"):
            self.app.save_to_game()
        self.assertIn("masterVolume: 60 → 85", ask.call_args.args[1])
        saved = saves.SaveProfile(self.profile_path).get("GlobalSaveDataDefault").decoded.document
        self.assertEqual(saved["blobs"][0]["masterVolume"], 85)

    def test_bool_values_use_a_true_false_picker(self):
        self.select(("blobs", 0, "backgroundAudio"))
        self.assertTrue(self.app.value_bool.grid_info())
        self.app.value_var.set("false")
        self.app.apply_value()
        self.assertIs(self.app.document["blobs"][0]["backgroundAudio"], False)

    def test_search_shows_matching_fields(self):
        self.app.search_var.set("deadzone")
        self.app._run_search()
        shown = {self.app.tree.item(iid, "text") for iid in self.app.node_paths}
        self.assertEqual(shown, {"blobs", "Audio", "leftDeadzone"})

    def test_invalid_raw_json_is_rejected(self):
        self.app.notebook.select(self.app.raw_tab)
        self.root.update()
        self.app.raw_text.insert("1.0", "oops")
        with mock.patch("tkinter.messagebox.showerror") as showerror:
            self.app.apply_raw()
        showerror.assert_called_once()
        self.assertEqual(self.app.change_count, 0)

    def test_protected_container_shows_a_message_not_its_contents(self):
        iid = next(i for i, c in self.app._containers_by_iid.items() if c.name == "auth_dynamic_entjwtbin")
        self.app.container_list.selection_set(iid)
        self.root.update()
        self.assertIsNone(self.app.document)
        self.assertIn("sign-in token", self.app.message_var.get())

    def test_advanced_mode_keeps_the_windows_look(self):
        self.assertEqual(ttk.Style(self.root).theme_use(), self.app.light_theme)
        self.assertTrue(self.app.advanced_screen.winfo_manager())
        self.assertFalse(self.app.simple_screen.winfo_manager())

    def test_switching_to_simple_mode_hides_the_technical_parts(self):
        self.app.advanced_var.set(False)
        self.app._on_advanced_toggled()
        self.assertEqual(self.container_names(), [])
        self.assertEqual(self.app.notebook.tab(self.app.edit_tab, "state"), "hidden")
        self.assertEqual(self.app.title_var.get(), "No offline heroes yet")
        self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8")), {"advanced": False})
        self.assertEqual(ttk.Style(self.root).theme_use(), game_style.THEME)
        self.assertTrue(self.app.simple_screen.winfo_manager())
        self.assertTrue(self.app.inventory.empty.winfo_manager())  # no hero to show: says how to get one
        self.assertIn("Reload", self.app.empty_text_var.get())


    def test_the_help_pages_buttons_all_fit(self):
        tools = self.app.help_tools
        self.assertEqual([button.cget("text") for button in tools.winfo_children()], ["World map…", "Play recorder…", "What's new…", "Connect an AI…"])
        # Their line asks for no more room than the line above it, which the page is wide enough for. (That much can
        # be checked on any screen; the rest needs one that shows the window whole.)
        self.root.update_idletasks()
        self.assertLessEqual(tools.winfo_reqwidth(), self.app.help_tab.winfo_children()[0].winfo_reqwidth())
        self.app.notebook.select(self.app.help_tab)
        self.show_on_screen(self.root)
        self.needs_room_for(self.root)
        # Each line of buttons has the room it asks for: none of them runs off the side of the page.
        for row in self.app.help_tab.winfo_children()[:2]:
            self.assertLessEqual(row.winfo_reqwidth(), row.winfo_width(), [child.cget("text") for child in row.winfo_children()])
        last = tools.winfo_children()[-1]
        self.assertLessEqual(last.winfo_rootx() + last.winfo_width(), self.app.help_tab.winfo_rootx() + self.app.help_tab.winfo_width())


@unittest.skipUnless(_tk_available(), "needs a display")
class HeroTabTests(WindowTestCase):
    """The Hero tab, which Advanced mode shows."""

    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), HERO: hero_save_text().encode()}
    advanced = True

    def make_icons(self):
        icons = self.dir / "icons" / "wiki"
        icons.mkdir(parents=True)
        picture = tk.PhotoImage(width=32, height=32)
        picture.put("#00aa00", to=(0, 0, 32, 32))
        picture.write(str(icons / "Mystic Circlet.png"), format="png")

    @property
    def tab(self):
        return self.app.hero_tab

    def rows(self):
        return [self.tab.tree.item(iid, "text").strip() for iid in self.tab.tree.get_children()]

    def select_item(self, name):
        iid = next(i for i in self.tab.tree.get_children() if self.tab.tree.item(i, "text").strip() == name)
        self.tab.tree.selection_set(iid)
        self.root.update()

    def saved_hero(self):
        return saves.SaveProfile(self.profile_path).get(HERO).hero

    def save(self):
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask, mock.patch("tkinter.messagebox.showinfo"):
            self.app.save_to_game()
        return ask.call_args.args[1] if ask.called else None

    def test_opens_the_hero_on_the_hero_tab(self):
        self.assertEqual(self.app.container.name, HERO)
        self.assertEqual(sorted(self.container_names()), sorted([HERO, "GlobalSaveDataDefault"]))
        self.assertEqual(self.app.notebook.select(), str(self.tab))
        for tab in (self.app.edit_tab, self.app.raw_tab):
            self.assertEqual(self.app.notebook.tab(tab, "state"), "normal")
        self.assertTrue(self.tab.raw_row.winfo_manager())
        self.assertTrue(self.app.meta_var.get().startswith(HERO))

    def test_lists_items_most_powerful_first_with_pictures(self):
        self.assertEqual(self.rows(), ["Longbow", "Mystic Circlet", "Cookiecutter", "Sword"])
        images = {self.tab.tree.item(i, "text").strip(): self.tab.tree.item(i, "image") for i in self.tab.tree.get_children()}
        self.assertTrue(all(images.values()))
        self.select_item("Mystic Circlet")
        self.assertEqual(self.tab.preview_source_var.get(), "Picture: minecraft.wiki")

    def test_an_items_effects_show_in_the_list_and_under_its_name(self):
        sword = next(item for item in self.tab.hero.items() if item.tag == "SW.Item.Sword")
        sword.data["Effects"] = [rolled(rolled_effect("CriticalEdge", 0.2, "II")), enchanted(enchantment_effect("Radiance", 0.3))]
        self.tab._fill_items()
        self.select_item("Sword")
        row = self.tab.tree.selection()[0]
        self.assertEqual(str(self.tab.tree.set(row, "enchants")), "2")
        self.assertEqual(self.tab.tree.heading("enchants", "text").strip(" ▲▼"), "Effects")
        self.assertIn("\nEffects: Critical Edge II 20%  ·  Enchanted: Healing Smite I, 3 enchantment points", self.tab.item_subtitle_var.get())
        self.select_item("Longbow")
        self.assertNotIn("Effects", self.tab.item_subtitle_var.get())

    def test_effects_are_changed_in_their_own_window(self):
        self.select_item("Sword")
        button = self.tab.effects_button
        self.assertEqual((str(button.cget("text")), button.instate(["!disabled"])), ("Change effects…", True))

        def choose(dialog):
            self.assertIsInstance(dialog, EffectsDialog)
            self.assertTrue(dialog.select("Critical Edge", "II"))
            dialog.add()
            self.assertTrue(dialog.select("Healing Smite"))
            dialog.add()
            dialog.apply()

        with mock.patch.object(self.tab, "wait_window", side_effect=choose):
            button.invoke()
        sword = next(item for item in self.tab.hero.items() if item.tag == "SW.Item.Sword")
        self.assertEqual(sword.effect_lines(), ["Critical Edge II 20%", "Enchanted: Healing Smite I, 1 enchantment point"])
        self.assertIn("Effects changed.", self.tab.item_message_var.get())
        self.assertIn("Effects: Critical Edge II 20%", self.tab.item_subtitle_var.get())
        # Closing the window without Apply leaves the item as it was.
        with mock.patch.object(self.tab, "wait_window", side_effect=lambda dialog: (dialog.remove_all(), dialog.destroy())):
            button.invoke()
        self.assertEqual(len(sword.effects), 2)
        self.assertIn("Sword: effects: Critical Edge II 20%, enchanted with Healing Smite I", self.save())
        self.assertEqual(next(item for item in self.saved_hero().items() if item.tag == "SW.Item.Sword").effect_lines(), sword.effect_lines())
        # Not for what the merchant stocks, or for a cosmetic.
        self.select_item("Cookiecutter")
        self.assertTrue(button.instate(["disabled"]))
        self.tab.show_cosmetics.set(True)
        self.tab._fill_items()
        self.select_item("Hero")
        self.assertTrue(button.instate(["disabled"]))

    def test_a_talisman_is_levelled_up(self):
        self.tab.hero.body["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", xp=90, seed=61))
        self.tab._fill_items()
        self.select_item("Sigil of Beeswax")
        button = self.tab.effects_button
        self.assertEqual((str(button.cget("text")), button.instate(["!disabled"])), ("Level up", True))
        self.assertIn("Level 1 of 3 (90 of 18,480 XP)", self.tab.item_subtitle_var.get())
        button.invoke()
        self.assertIn("The Sigil of Beeswax is level 2 now, saved the way the game saves a level-up.", self.tab.item_message_var.get())
        self.assertIn("Level 2 of 3", self.tab.item_subtitle_var.get())
        button.invoke()
        self.assertIn("is level 3 now, saved the way the game saves a level-up. That's its top level.", self.tab.item_message_var.get())
        self.assertEqual((str(button.cget("text")), button.instate(["!disabled"])), ("Level up", False))
        self.save()
        saved = next(item for item in self.saved_hero().items() if item.is_talisman)
        self.assertEqual((saved.level, saved.xp, saved.effects[0].strength, saved.effects[0].template), (2, 92400, 1.35, "SW.EffectTemplate.HealthBoost.III"))

    def test_a_companions_talisman_is_made_ready_to_level_up(self):
        # It levels up by tags, not by an effect, which nobody has seen saved yet: the game does that one itself.
        wolf = talisman_item("SW.Item.Talisman.Wolf", "Wolf", xp=90, seed=62)
        wolf["ItemData"]["Effects"] = []
        wolf["ItemData"]["ItemProgression"]["ItemLevels"] = [{"LevelEffects": [], "LevelTags": [f"SW.Talisman.Wolf.Level.{level}"]} for level in (1, 2, 3)]
        self.tab.hero.body["Inventory"]["Entries"].append(wolf)
        self.tab._fill_items()
        self.select_item("Tasty Bone")
        button = self.tab.effects_button
        self.assertEqual((str(button.cget("text")), button.instate(["!disabled"])), ("Ready to level up", True))
        button.invoke()
        self.assertIn("XP set to 18,479, one short of level 2", self.tab.item_message_var.get())
        self.save()
        saved = next(item for item in self.saved_hero().items() if item.is_talisman)
        self.assertEqual((saved.level, saved.xp), (0, 18479))

    def test_the_town_vendors_the_hero_has_unlocked(self):
        self.assertTrue(self.tab.vendors_var.get().startswith("This hero hasn't opened a town vendor in the game yet."))
        hints = self.tab.hero.body["CollectionsStats"]["ShownHints"] = [{"Tag": "SW.UI.Onboarding.Panel.VillageMerchant.Overview", "Count": 1}]
        self.tab.refresh()
        self.assertTrue(self.tab.vendors_var.get().startswith("Unlocked in the game: the Village Merchant. Not opened yet: the Blacksmith and the Enchantsmith."))
        hints += [{"Tag": f"SW.UI.Onboarding.Panel.{vendor}.Overview", "Count": 1} for vendor in ("Blacksmith", "Enchantsmith")]
        self.tab.refresh()
        self.assertEqual(self.tab.vendors_var.get(), "This hero has unlocked all three town vendors: the Village Merchant, the Blacksmith and the Enchantsmith.")

    def test_sorting_and_filters(self):
        self.tab.sort_var.set("Name")
        self.tab._fill_items()
        self.assertEqual(self.rows(), ["Cookiecutter", "Longbow", "Mystic Circlet", "Sword"])
        self.tab._sort_by_heading("rarity")
        self.assertEqual(self.rows()[0], "Longbow")
        self.assertTrue(self.tab.tree.heading("rarity", "text").endswith("▼"))
        self.tab.show_merchant.set(False)
        self.tab.show_cosmetics.set(True)
        self.tab._fill_items()
        self.assertEqual(sorted(self.rows()), ["Hero", "Longbow", "Mystic Circlet", "Sword"])

    def test_stats_apply_as_you_go_and_save_with_a_plain_summary(self):
        self.tab.stat_vars["Emeralds"].set("5000")
        self.assertTrue(self.tab._apply_stat("Emeralds"))
        self.assertEqual(self.app.change_count, 1)
        summary = self.save()
        self.assertIn("Emeralds: 55 → 5,000", summary)
        self.assertNotIn("CharacterSaveV1", summary)
        self.assertEqual(self.saved_hero().attribute("Emeralds"), 5000)

    def test_typed_value_is_kept_even_without_leaving_the_field(self):
        self.tab.stat_vars["Emeralds"].set("123")  # typed, then straight to Save to game
        self.save()
        self.assertEqual(self.saved_hero().attribute("Emeralds"), 123)

    def test_mistakes_show_inline_instead_of_pop_ups(self):
        self.tab.stat_vars["Emeralds"].set("lots")
        with mock.patch("tkinter.messagebox.showerror") as showerror:
            self.assertFalse(self.tab._apply_stat("Emeralds"))
        showerror.assert_not_called()
        self.assertEqual(str(self.tab.stats_message.cget("style")), "Error.TLabel")
        self.assertIn("Emeralds", self.tab.stats_message_var.get())
        self.assertEqual(self.tab.stat_vars["Emeralds"].get(), "55")
        self.assertEqual(self.app.change_count, 0)

    def test_item_power_rarity_copy_and_delete(self):
        self.select_item("Mystic Circlet")
        self.tab.power_var.set("50")
        self.assertTrue(self.tab._apply_numbers())
        self.tab.rarity_var.set("Unique")
        self.tab._apply_item(rarity="Unique")
        self.select_item("Longbow")
        self.tab.copy_item()
        self.select_item("Cookiecutter")
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            self.tab.delete_item()
        summary = self.save()
        self.assertIn("Mystic Circlet: Common → Unique, power 1 → 50", summary)
        self.assertIn("Added Longbow (Rare, power 2)", summary)
        self.assertIn("Removed Cookiecutter", summary)
        hero = self.saved_hero()
        tags = [item.tag for item in hero.items()]
        self.assertEqual(tags.count("SW.Item.Longbow"), 2)
        self.assertNotIn("SW.Item.CurvedGreatsword", tags)

    def test_bad_item_value_stays_on_that_item(self):
        self.select_item("Mystic Circlet")
        self.tab.power_var.set("-5")
        self.select_item("Longbow")  # clicking away with a bad value
        self.assertEqual(self.tab.item_title_var.get(), "Mystic Circlet")
        self.assertEqual(str(self.tab.item_message.cget("style")), "Error.TLabel")

    def test_equipped_items_cannot_be_deleted(self):
        self.select_item("Sword")
        self.assertTrue(self.tab.delete_button.instate(["disabled"]))
        self.assertTrue(self.tab.change_button.instate(["disabled"]))

    def test_equip_and_unequip_on_the_hero_tab(self):
        self.select_item("Sword")
        self.assertEqual(self.tab.equip_button.cget("text"), "Unequip")
        self.tab.equip_item()
        self.assertFalse(self.tab.delete_button.instate(["disabled"]))
        self.assertEqual(self.tab.equip_button.cget("text"), "Equip")
        self.select_item("Mystic Circlet")
        with mock.patch("tkinter.messagebox.askyesno") as ask:
            self.tab.equip_item()  # the game's files name every gear slot, so there's nothing to ask
        ask.assert_not_called()
        self.assertIn("Equipped (helmet)", self.tab.item_message_var.get())
        self.select_item("Cookiecutter")  # merchant stock
        self.assertTrue(self.tab.equip_button.instate(["disabled"]))
        summary = self.save()
        self.assertIn("Sword: unequipped", summary)
        self.assertIn("Mystic Circlet: equipped (helmet)", summary)
        self.assertEqual(self.saved_hero().equipped("SW.ItemSlot.Equipment.Armor.Helmet").name, "Mystic Circlet")

    def show_equipped(self):
        self.tab.item_views.select(self.tab.gear)
        self.root.update()

    def slot_row(self, label):
        """(equipped column, rarity and power) for the slot with this label in the Equipped view."""
        iid = next(i for i in self.tab.gear_tree.get_children() if self.tab.gear_tree.item(i, "text").strip() == label)
        return iid, tuple(self.tab.gear_tree.item(iid, "values"))

    def test_equipped_view_shows_every_slot(self):
        self.show_equipped()
        self.assertEqual(len(self.tab.gear_tree.get_children()), 12)
        self.assertEqual(self.slot_row("Melee weapon")[1], ("Sword", "Common, power 1"))
        self.assertEqual(self.slot_row("Helmet")[1][0], "empty")
        later, values = self.slot_row("Artifact 2")
        self.assertEqual(values[0], "empty")  # Advanced mode doesn't wait for the level that opens it
        self.tab.gear_tree.selection_set(later)
        self.root.update()
        self.assertTrue(self.tab.slot_add_button.instate(["!disabled"]))
        melee, _values = self.slot_row("Melee weapon")
        self.tab.gear_tree.selection_set(melee)
        self.root.update()
        self.assertEqual(self.tab.item_title_var.get(), "Sword")  # picking a slot shows its item below
        self.tab.slot_off_button.invoke()
        self.assertEqual(self.slot_row("Melee weapon")[1][0], "empty")
        self.assertIn("Unequipped", self.tab.item_message_var.get())

    def test_add_straight_into_a_slot(self):
        self.show_equipped()
        helmet, _values = self.slot_row("Helmet")
        self.tab.gear_tree.selection_set(helmet)
        self.root.update()
        self.tab.slot_add_button.invoke()
        self.root.update()
        picker = next(w for w in self.tab.winfo_children() if isinstance(w, ItemPicker))
        names = [picker.tree.item(i, "text").strip() for i in picker.tree.get_children()]
        self.assertIn("Mystic Circlet", names)
        self.assertNotIn("Sword", names)
        self.assertNotIn("Beekeeper Boots", names)  # armor, but not a helmet
        self.assertTrue(picker.equip_var.get())
        row = next(i for i in picker.tree.get_children() if picker.tree.item(i, "text").strip() == "Mystic Circlet")
        picker.tree.selection_set(row)
        self.root.update()
        self.assertEqual(picker.slot_var.get(), "Helmet: empty")
        with mock.patch("tkinter.messagebox.askyesno") as ask:
            picker._confirm()
        ask.assert_not_called()  # a confirmed item, in a slot the game's own files name
        picker.destroy()
        self.assertEqual(self.slot_row("Helmet")[1][0], "Mystic Circlet")

    def test_add_and_equip_from_the_picker(self):
        picker, _row = self.open_picker_on("Axe")
        picker.equip_var.set(True)
        picker._show_slot()
        self.assertEqual(picker.slot_var.get(), "Melee weapon: Sword")
        self.assertIn("Your Sword goes back to your inventory.", picker.slot_note.get())
        self.assertEqual(picker.confirm_button.cget("text"), "Add and equip")
        with mock.patch("tkinter.messagebox.askyesno") as ask:
            picker._confirm()  # the melee slot's name is confirmed: no question
        ask.assert_not_called()
        self.assertIn("equipped it (melee weapon)", picker.message_var.get())
        self.assertEqual(picker.slot_var.get(), "Melee weapon: Axe")
        picker.destroy()
        summary = self.save()
        self.assertIn("Added Axe (Common, power 2), equipped (melee weapon)", summary)  # power starts at your best item's
        self.assertIn("Sword: unequipped", summary)

    def test_add_items_from_the_picker(self):
        self.tab.open_add_items()
        self.root.update()
        picker = next(w for w in self.tab.winfo_children() if isinstance(w, ItemPicker))
        names = [picker.tree.item(i, "text").strip() for i in picker.tree.get_children()]
        self.assertIn("Axe", names)  # from the collections
        self.assertNotIn("Hero", names)  # cosmetics can't be added
        picker.search_var.set("axe")
        self.root.update()
        results = {picker.tree.item(i, "text").strip(): i for i in picker.tree.get_children()}
        self.assertIn("Greataxe", results)  # from the game's item list, not just the saves
        self.assertEqual(picker.tree.item(results["Axe"], "values")[1], "Confirmed")  # seen in this save's collections
        picker.tree.selection_set(results["Axe"])
        self.root.update()
        picker.rarity_var.set("Unique")
        picker.power_var.set("40")
        picker.count_var.set("2")
        picker._confirm()
        self.assertIn("Added Hunter's Hatchet", picker.message_var.get())  # the Axe's Unique
        picker.destroy()
        summary = self.save()
        self.assertIn("Added Hunter's Hatchet (Unique, power 40)", summary)
        axe = next(item for item in self.saved_hero().items() if item.tag == "SW.Item.Axe_Unique1")  # the Unique's own ID
        self.assertEqual((axe.name, axe.rarity, axe.power, axe.count, axe.where), ("Hunter's Hatchet", "Unique", 40, 2, "Inventory"))

    def test_an_enchantment_book_in_the_list(self):
        entry = next(entry for entry in self.tab._catalog() if entry.tag == "SW.Item.EnchantmentBook.Piercing")
        self.tab.hero.add_item(entry.tag, entry.template)
        self.tab._fill_items()
        self.select_item("Piercing")
        values = self.tab.tree.item(self.tab.tree.selection()[0], "values")
        self.assertEqual(tuple(values[:3]), ("Enchantment Book", "", ""))  # kind, and no rarity or power
        self.assertEqual(
            self.tab.item_subtitle_var.get(),
            "Enchantment book  ·  Inventory\nThe book of an enchantment for ranged weapons. Projectiles pierce enemies: "
            "1 / 3 / 5 enemies at tiers I, II and III.",
        )
        tab = self.tab
        for widget in (tab.power_entry, tab.count_entry, tab.type_box, tab.change_button, tab.copy_button, tab.equip_button,
                       tab.effects_button, *tab.rarity_buttons):
            self.assertTrue(widget.instate(["disabled"]), widget)
        self.assertTrue(tab.delete_button.instate(["!disabled"]))
        self.assertIn("An enchantment book has no rarity or power. A hero has one of each enchantment book", tab.item_message_var.get())
        self.assertFalse(tab.has_pending_input())
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            tab.delete_button.invoke()
        self.assertNotIn("Piercing", self.rows())

    def test_a_book_by_its_id_and_every_book_at_once(self):
        # Advanced mode takes an ID typed by hand: a book's is laid out as a book, whatever the boxes say.
        self.tab.open_add_items()
        self.root.update()
        picker = next(w for w in self.tab.winfo_children() if isinstance(w, ItemPicker))
        self.assertFalse(picker.books_button.winfo_manager())  # the list is on all kinds
        picker.rarity_var.set("Unique")
        picker.count_var.set("4")
        picker.raw_var.set("SW.Item.EnchantmentBook.NotInTheList")
        picker._use_raw()
        self.assertIn("Added the SW.Item.EnchantmentBook.NotInTheList book", picker.message_var.get())
        made = next(item for item in self.tab.hero.items() if item.tag == "SW.Item.EnchantmentBook.NotInTheList")
        self.assertEqual((made.rarity, made.power, made.count, made.name), ("None", -1, 1, "Not In The List"))
        picker._use_raw()
        self.assertIn("already has the Not In The List book", picker.message_var.get())
        picker.kind_var.set(BOOK_KIND)
        picker._fill()
        self.root.update()
        self.assertTrue(picker.books_button.winfo_manager())
        picker.books_button.invoke()
        self.assertEqual(picker.message_var.get(), "Added 9 enchantment books, saved the way the game saves one. Add more, or close this window.")
        self.assertFalse(picker.books_button.winfo_manager())
        self.assertEqual({picker.tree.item(row, "values")[1] for row in picker.tree.get_children()}, {"You have it"})
        self.assertTrue(picker.confirm_button.instate(["disabled"]))
        picker.destroy()
        self.assertEqual(len(self.tab.hero.books()), 10)
        self.assertEqual(self.tab.item_message_var.get(), "Added 9 enchantment books, saved the way the game saves one. Press Save to game when you're done.")
        summary = self.save()
        self.assertIn("Added Somersault (enchantment book)", summary)
        self.assertEqual(len(self.saved_hero().books()), 10)

    def test_an_item_is_not_changed_into_a_book(self):
        picker = ItemPicker(self.tab, self.tab._catalog(), self.tab.icons, mode="choose", advanced=True)
        self.root.update()
        names = [picker.tree.item(row, "text").strip() for row in picker.tree.get_children()]
        self.assertIn("Longbow", names)
        self.assertFalse({"Piercing", "Somersault", "Shockwave"} & set(names))
        picker.destroy()
        self.select_item("Longbow")
        self.tab.type_var.set("SW.Item.EnchantmentBook.Piercing")
        self.tab._apply_type()
        self.assertIn("can't be changed into an enchantment book. Add the Piercing book with Add items", self.tab.item_message_var.get())
        self.assertIn("Longbow", self.rows())

    def open_picker_on(self, name):
        self.tab.open_add_items()
        self.root.update()
        picker = next(w for w in self.tab.winfo_children() if isinstance(w, ItemPicker))
        picker.search_var.set(name)
        self.root.update()
        row = next(i for i in picker.tree.get_children() if picker.tree.item(i, "text").strip() == name)
        picker.tree.selection_set(row)
        self.root.update()
        return picker, row

    def test_unconfirmed_items_warn_once_before_adding(self):
        picker, row = self.open_picker_on("Battlestaff")
        self.assertEqual(picker.tree.item(row, "values")[1], "Unconfirmed")
        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            picker._confirm()
        ask.assert_called_once()
        self.assertEqual(self.app.change_count, 0)
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            picker._confirm()
            picker._confirm()  # asked only once per window
        ask.assert_called_once()
        picker.destroy()
        staffs = [item for item in self.app.hero_tab.hero.items() if item.tag == "SW.Item.Battlestaff"]
        self.assertEqual(len(staffs), 2)

    def test_a_talisman_without_a_known_effect_warns_before_adding(self):
        picker, row = self.open_picker_on("Twig of Dark Oak")  # its ID has been seen in a save, its effect hasn't
        self.assertEqual(picker.tree.item(row, "values")[1], "Unconfirmed")
        self.assertIn("hasn't seen this talisman's effect", picker.status_text.get())
        self.assertNotIn("best guess", picker.status_text.get())
        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            picker._confirm()
        self.assertIn("adds the talisman without one", ask.call_args.args[1])
        self.assertNotIn("best guess", ask.call_args.args[1])
        self.assertEqual(self.app.change_count, 0)
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            picker._confirm()
            picker._confirm()  # asked only once per window
        ask.assert_called_once()
        picker.destroy()
        # In the list a talisman shows no rarity or power, and its controls are off.
        self.select_item("Twig of Dark Oak")
        row = self.tab.tree.selection()[0]
        self.assertEqual(self.tab.tree.item(row, "values")[:3], ("Talisman", "", ""))
        self.assertTrue(self.tab.item_subtitle_var.get().startswith("Talisman  ·  Inventory"))
        self.assertEqual(self.tab.power_var.get(), "")
        self.assertTrue(self.tab.power_entry.instate(["disabled"]))
        self.assertTrue(all(button.instate(["disabled"]) for button in self.tab.rarity_buttons))
        self.assertFalse(self.tab.has_pending_input())
        self.assertTrue(self.tab.commit_pending())
        self.assertIn("This one has no effect saved", self.tab.item_message_var.get())
        self.assertNotIn("Delete it and add it again", self.tab.item_message_var.get())  # a new one would be the same
        # The Sigil of Beeswax's effect is known, so it's added without a question.
        picker, row = self.open_picker_on("Sigil of Beeswax")
        self.assertEqual(picker.tree.item(row, "values")[1], "Confirmed")
        with mock.patch("tkinter.messagebox.askyesno") as ask:
            picker._confirm()
        ask.assert_not_called()
        picker.destroy()
        summary = self.save()
        self.assertIn("Added Sigil of Beeswax", summary)
        self.assertNotIn("Added Sigil of Beeswax (", summary)  # no rarity or power to tell

    def test_the_add_button_keeps_its_room_in_a_window_too_short_for_everything(self):
        picker, _row = self.open_picker_on("Battle Hammer")
        self.show_on_screen(picker)
        self.assert_in_view(picker.confirm_button, picker)
        self.needs_room_for(picker)
        picker.minsize(1, 1)
        picker.geometry(f"{picker.winfo_width()}x{picker.winfo_height() // 2}")  # as on a screen that's too small for it
        picker.update()
        self.assert_in_view(picker.confirm_button, picker)
        picker.destroy()

    def test_the_connect_an_ai_windows_buttons_keep_their_room(self):
        from dungeons2_editor.ai_dialog import ConnectAiDialog

        self.app._connect_ai()
        self.root.update()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, ConnectAiDialog))
        self.show_on_screen(dialog)
        buttons = [w for w in dialog.winfo_children()[0].winfo_children() if isinstance(w, ttk.Button)]
        close = next(w for frame in dialog.winfo_children()[0].winfo_children() if isinstance(frame, ttk.Frame) for w in frame.winfo_children() if isinstance(w, ttk.Button))
        self.needs_room_for(dialog)
        dialog.minsize(1, 1)
        dialog.geometry(f"{dialog.winfo_width()}x{dialog.winfo_height() - 3 * close.winfo_height()}")  # the boxes of text can give that much
        dialog.update()
        for button in [*buttons, close]:  # the three Copy buttons and Close
            self.assert_in_view(button, dialog)
        self.assertEqual(len(buttons), 3)
        dialog.destroy()

    def test_a_unique_is_added_under_its_own_id(self):
        picker, _row = self.open_picker_on("Battle Hammer")
        self.assertTrue(picker.status_text.get().startswith("Confirmed"))  # SW.Item.Hammer, reported from a real save
        picker.rarity_var.set("Unique")
        picker._show_selected()
        self.assertEqual(picker.name_var.get(), "Emerald Hammer")
        self.assertIn("Unique Battle Hammer", picker.unique_text.get())
        # It comes with the effect of its own, which the editor has seen saved: nothing to warn about.
        note = picker.unique_note_label
        self.assertTrue(picker.unique_text.get().endswith("(a Unique Battle Hammer). Grants a 5% chance of higher rarity loot drops."))
        self.assertFalse(note.winfo_manager())
        self.assertIn("SW.Item.Hammer_Unique1", picker.kind_text.get())
        # The Emerald Hammer's own ID hasn't been seen, but it follows the pattern every seen one does: no question asked.
        self.assertTrue(picker.status_text.get().startswith("By its pattern"))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            picker._confirm()
        ask.assert_not_called()
        self.assertIn("Added. Press Save", self.tab.item_message_var.get())
        picker.destroy()
        self.assertIn("Added Emerald Hammer (Unique", self.save())
        hammer = next(item for item in self.saved_hero().items() if item.tag == "SW.Item.Hammer_Unique1")
        self.assertEqual((hammer.rarity, hammer.name), ("Unique", "Emerald Hammer"))
        self.assertEqual([(effect.is_own, effect.tag, effect.strength) for effect in hammer.effects], [(True, "SW.Effect.Opulence", 0.05)])

    def test_add_items_says_which_uniques_come_without_their_own_effect(self):
        # The Ranger's Promise: no save has shown the effect it comes with, so the editor can't add it.
        picker, _row = self.open_picker_on("Bow")
        note = picker.unique_note_label
        self.assertFalse(note.winfo_manager())  # at Common rarity it's a Bow
        picker.rarity_var.set("Unique")
        picker._show_selected()
        self.assertEqual(picker.name_var.get(), "Ranger's Promise")
        self.assertIn("). In the game: Increases chance of critical hits from ranged attacks by 25%.", picker.unique_text.get())
        self.assertTrue(note.winfo_manager())
        self.assertEqual(str(note.cget("text")), "The editor adds this Unique without its own effect: it hasn't seen how the game saves that one yet.")
        picker.rarity_var.set("Special")
        picker._show_selected()
        self.assertFalse(note.winfo_manager())  # only a Unique has one to be without
        picker.rarity_var.set("Unique")
        picker._show_selected()
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            picker._confirm()
        self.assertIn("Added. Without its own effect: the editor can't add that one yet. ", self.tab.item_message_var.get())
        picker.destroy()
        # The Slaymore's hasn't been seen either, but the Humbler Greaves do the same thing and theirs has.
        picker, _row = self.open_picker_on("Claymore")
        picker.rarity_var.set("Unique")
        picker._show_selected()
        self.assertTrue(picker.unique_text.get().endswith(
            "Melee attacks deal 50% more damage to secondary targets. That effect is saved the way the game saves it for the "
            "Humbler Greaves, which does the same."
        ))
        self.assertFalse(picker.unique_note_label.winfo_manager())
        picker.destroy()

    def test_making_an_item_unique_renames_it_only_when_the_uniques_id_is_known(self):
        self.select_item("Sword")
        self.tab._apply_item(rarity="Unique")
        self.assertIn("The Burning Blade", self.rows())  # SW.Item.Sword_Unique1 has been seen in real saves
        self.assertIn("It's The Burning Blade now. ", self.tab.item_message_var.get())
        self.assertIn("\nEffects: Its own: Fire Focus", self.tab.item_subtitle_var.get())  # it came with the effect of its own
        self.assertNotIn("Without its own effect", self.tab.item_subtitle_var.get())
        self.select_item("Mystic Circlet")
        self.tab._apply_item(rarity="Unique")
        self.assertNotIn("Oracle Crown", self.rows())  # its own ID hasn't: guessing wrong would cost the item
        self.assertIn("a Unique-rarity Mystic Circlet, not the Oracle Crown", self.tab.item_message_var.get())
        hero = self.tab.hero
        self.assertEqual(sorted(item.tag for item in hero.items() if item.rarity == "Unique"), ["SW.Item.MysticHelmet", "SW.Item.Sword_Unique1"])

    def test_picker_reports_bad_input_inline(self):
        self.tab.open_add_items()
        self.root.update()
        picker = next(w for w in self.tab.winfo_children() if isinstance(w, ItemPicker))
        picker.power_var.set("lots")
        picker._confirm()
        self.assertEqual(str(picker.message.cget("style")), "Error.TLabel")
        picker.destroy()
        self.assertEqual(self.app.change_count, 0)

    def test_change_item_into_another(self):
        self.select_item("Mystic Circlet")
        with mock.patch.object(self.tab, "wait_window"):
            with mock.patch("dungeons2_editor.hero_editing.ItemPicker") as picker_class:
                picker_class.return_value.result = "SW.Item.Axe"
                self.tab.change_item()
        self.assertIn("Axe", self.rows())

    def test_advanced_mode_shows_raw_ids_and_other_saves(self):
        self.assertIn("GlobalSaveDataDefault", self.container_names())
        self.assertEqual(self.app.notebook.tab(self.app.edit_tab, "state"), "normal")
        self.assertTrue(self.tab.raw_row.winfo_manager())
        self.select_item("Mystic Circlet")
        self.assertEqual(self.tab.type_var.get(), "SW.Item.MysticHelmet")

    def test_edits_in_the_tree_show_up_on_the_hero_tab(self):
        self.app.notebook.select(self.app.edit_tab)
        self.root.update()
        attributes = self.app.document["CharacterSaveV1"]["Ability"]["Attributes"]
        path = ("CharacterSaveV1", "Ability", "Attributes", next(i for i, a in enumerate(attributes) if a["AttributeName"] == "Emeralds"), "CurrentValue")
        for depth in range(1, len(path)):
            self.app._expand(next(i for i, p in self.app.node_paths.items() if p == path[:depth]))
        self.app.tree.selection_set(next(i for i, p in self.app.node_paths.items() if p == path))
        self.root.update()
        self.app.value_var.set("777")
        self.app.apply_value()
        self.app.notebook.select(self.tab)
        self.root.update()
        self.assertEqual(self.tab.stat_vars["Emeralds"].get(), "777")

    def test_presets_window_previews_and_applies(self):
        from dungeons2_editor.presets_dialog import PresetsDialog

        self.tab.open_presets()
        self.root.update()
        dialog = next(w for w in self.tab.winfo_children() if isinstance(w, PresetsDialog))
        text = dialog.text.get("1.0", "end")
        self.assertIn("Emeralds: 55 → 99,999", text)
        self.assertIn("Unconfirmed items", text)
        self.assertFalse(dialog.rarity_row.winfo_manager())  # Most money doesn't ask for a rarity
        dialog._apply()
        self.assertTrue(dialog.message_var.get().startswith("Applied Most money"))
        dialog.destroy()
        self.assertEqual(self.tab.stat_vars["Emeralds"].get(), "99999")
        self.assertIn("Emeralds: 55 → 99,999", self.save())

    def test_kit_preset_adds_and_equips_a_loadout(self):
        from dungeons2_editor import presets
        from dungeons2_editor.presets_dialog import PresetsDialog

        self.tab.open_presets()
        self.root.update()
        dialog = next(w for w in self.tab.winfo_children() if isinstance(w, PresetsDialog))
        number = next(i for i, p in enumerate(presets.PRESETS) if p.title == "Melee damage")
        dialog.listing.selection_set(str(number))
        dialog.include_unconfirmed.set(True)
        dialog.power_var.set("40")
        self.root.update()
        dialog._refresh()
        # Advanced mode doesn't wait for the levels that open artifact slots 2 and 3.
        self.assertIn("\tArtifacts\tWarrior Drums, Death Cap Mushroom, Grindstone\n", dialog.text.get("1.0", "end"))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            dialog._apply()
        dialog.destroy()
        self.assertEqual(self.tab.hero.equipped("SW.ItemSlot.Equipment.Artifact.Slot3").name, "Grindstone")
        self.assertIn("Pride of the Plains", self.rows())

    def test_talisman_preset_leaves_out_talismans_it_cant_give_an_effect(self):
        from dungeons2_editor import presets
        from dungeons2_editor.presets_dialog import PresetsDialog

        self.tab.open_presets()
        self.root.update()
        dialog = next(w for w in self.tab.winfo_children() if isinstance(w, PresetsDialog))
        dialog.listing.selection_set(str(next(i for i, p in enumerate(presets.PRESETS) if p.title == "Best talismans")))
        self.root.update()
        text = dialog.text.get("1.0", "end")
        self.assertIn("•  Talismans, ", text)  # no "Unique gear at power 1": they have neither
        self.assertIn("\tTalismans\tFist of Iron, Ocelot's Paw, Sigil of Beeswax\n", text)
        self.assertIn("A grey talisman can be one whose effect the editor hasn't seen", text)
        self.assertEqual([a.kit.name for a in dialog.plan.add], ["Sigil of Beeswax"])
        dialog.include_unconfirmed.set(True)
        dialog._refresh()
        self.assertIn("2 of these talismans are added without their effect", dialog.text.get("1.0", "end"))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            dialog._apply()
        question = ask.call_args.args[1]
        self.assertIn("1 of the items is unconfirmed", question)  # Ocelot's Paw's ID is a guess; Fist of Iron's isn't
        self.assertIn("2 of the talismans are added without their effect", question)
        dialog.destroy()
        added = {item.name: item for item in self.tab.hero.items() if item.is_talisman}
        self.assertEqual(sorted(added), ["Fist of Iron", "Ocelot's Paw", "Sigil of Beeswax"])
        self.assertEqual([len(added[name].progression["ItemLevels"]) for name in sorted(added)], [0, 0, 3])
        self.assertEqual({item.rarity for item in added.values()}, {"None"})

    def test_group_rows_pick_their_first_preset(self):
        from dungeons2_editor.presets_dialog import PresetsDialog

        self.tab.open_presets()
        self.root.update()
        dialog = next(w for w in self.tab.winfo_children() if isinstance(w, PresetsDialog))
        dialog.listing.selection_set("group:Kits")
        self.root.update()
        self.assertEqual(dialog.title_var.get(), "Melee damage")
        dialog.destroy()

    def game_saves(self, change):
        """The game saves the hero while the editor has it open (a play session, or the Xbox app syncing)."""
        game = saves.SaveProfile(self.profile_path)
        document = copy.deepcopy(game.get(HERO).decoded.document)
        change(Hero(document))
        game.save(HERO, document, self.dir / "game-backups", check_game=lambda: [])
        self.app.game_running = []

    def test_reloads_when_the_game_saves_and_nothing_is_unsaved(self):
        self.game_saves(lambda hero: hero.set_attributes({"XP": 3000}))
        self.app._check_disk()
        self.assertEqual(self.tab.stat_vars["XP"].get(), "3000")
        self.assertIn("loaded the new version", self.app.status_var.get())

    def test_saving_after_the_game_saved_reapplies_your_changes(self):
        self.tab.stat_vars["Emeralds"].set("5000")
        self.assertTrue(self.tab._apply_stat("Emeralds"))
        self.game_saves(lambda hero: hero.set_attributes({"XP": 3000}))
        self.app._check_disk()
        self.assertIn("re-applied", self.app.status_var.get())
        self.assertEqual(self.tab.stat_vars["Emeralds"].get(), "5000")  # your change is kept
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask, mock.patch("tkinter.messagebox.showinfo"):
            self.app.save_to_game()
        self.assertEqual([call.args[0] for call in ask.call_args_list], ["Save to game", "Newer save found", "Save to game"])
        self.assertIn("Emeralds: 55 → 5,000", ask.call_args_list[2].args[1])
        hero = self.saved_hero()
        self.assertEqual((hero.attribute("Emeralds"), hero.attribute("XP")), (5000, 3000))  # yours and the game's

    def wait_until(self, done):
        """Let the window's background work finish (it reports back through Tk's event loop)."""
        for _ in range(400):
            self.root.update()
            if done():
                return
            time.sleep(0.01)
        self.fail("the background work didn't finish")

    @staticmethod
    def release(version):
        page = f"https://github.com/IshiakiZ/mcd2-save-editor/releases/tag/v{version}"
        return updater.Release(version, page, f"{updater.DOWNLOADS}v{version}/{updater.ASSET_NAME}", 19_000_000, "0" * 64)

    def test_update_button_appears_when_a_newer_version_is_out(self):
        self.assertFalse(self.app.update_button_advanced.winfo_manager())
        release = self.release("99.0.0")
        with mock.patch.object(updater, "latest_release", return_value=release):
            self.app.check_for_updates()
            self.wait_until(lambda: self.app.update is not None)
        self.assertEqual(self.app.update_button_advanced.cget("text"), "Update to 99.0.0")
        self.assertEqual(self.app.update_button.cget("text"), "UPDATE TO 99.0.0")
        self.assertTrue(self.app.update_button_advanced.winfo_manager())
        self.assertIn("Version 99.0.0 is out", self.app.status_var.get())
        with mock.patch("webbrowser.open") as browser:  # run from source there's no packaged editor to replace
            self.app.update_app()
        browser.assert_called_once_with(release.page)

    def test_the_offline_edition_asks_nobody(self):
        from dungeons2_editor import edition

        offline = (mock.patch.object(edition, "ONLINE", False), mock.patch.object(edition, "NAME", "Nexus Mods"))
        with offline[0], offline[1], mock.patch.object(updater, "latest_release", side_effect=AssertionError("it asked GitHub")) as asked, \
                mock.patch.object(gui.wiki, "list_pictures", side_effect=AssertionError("it asked the wiki")) as listed:
            self.app.check_for_updates()  # at start-up: nothing happens, and nothing is said
            with mock.patch("tkinter.messagebox.showinfo") as info:
                self.app.check_for_updates(announce=True)  # Check for updates in the menu
            self.assertIn("from Nexus Mods, never goes online, so it doesn't look for updates", info.call_args.args[1])
            self.assertIn(f"New versions are on Nexus Mods. You have {__version__}.", info.call_args.args[1])
            with mock.patch("tkinter.messagebox.showinfo") as info:
                self.app._get_pictures()
            self.assertIn("never goes online, so it doesn't download pictures", info.call_args.args[1])
            self.assertIn("Windows+Shift+S", info.call_args.args[1])  # and how to get pictures all the same
            for _ in range(20):
                self.root.update()
                time.sleep(0.01)
        asked.assert_not_called()
        listed.assert_not_called()
        self.assertIsNone(self.app.update)

    def test_no_update_button_without_a_newer_version(self):
        for found in (self.release(__version__), self.release("0.9.0"), None):
            with mock.patch.object(updater, "latest_release", return_value=found), mock.patch("tkinter.messagebox.showinfo") as info:
                self.app.check_for_updates(announce=True)
                self.wait_until(lambda: info.called)
            self.assertIn("latest version", info.call_args.args[1])
        with mock.patch.object(updater, "latest_release", side_effect=OSError("offline")), mock.patch("tkinter.messagebox.showinfo") as info:
            self.app.check_for_updates(announce=True)
            self.wait_until(lambda: info.called)
        self.assertIn("couldn't be reached", info.call_args.args[1])
        self.assertIsNone(self.app.update)
        self.assertFalse(self.app.update_button_advanced.winfo_manager())
        with mock.patch.object(updater, "latest_release", side_effect=OSError("offline")), mock.patch("tkinter.messagebox.showinfo") as info:
            self.app.check_for_updates()  # the check at start-up says nothing when it finds nothing
            for _ in range(40):
                self.root.update()
                time.sleep(0.01)
        info.assert_not_called()

    def test_update_downloads_the_new_copy_and_hands_over_to_it(self):
        release = self.release("99.0.0")
        self.app._show_update(release)
        target, staged = self.dir / "MCD2SaveEditor", self.dir / "update" / "MCD2SaveEditor"
        with mock.patch.object(updater, "app_dir", return_value=target), mock.patch.object(updater, "stage", return_value=staged) as stage, \
                mock.patch.object(updater, "start_swap") as swap, mock.patch.object(self.root, "destroy") as closed, \
                mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            self.app.update_app()  # asked, and the answer was no
            self.assertIn("Update to version 99.0.0?", ask.call_args.args[1])
            stage.assert_not_called()
            ask.return_value = True
            self.app.update_app()
            self.wait_until(lambda: closed.called)
        self.assertEqual(stage.call_args.args[0], release)
        swap.assert_called_once_with(staged, target)  # the new copy replaces the folder once this window has closed

    def test_a_failed_update_offers_the_download_page(self):
        release = self.release("99.0.0")
        self.app._show_update(release)
        with mock.patch.object(updater, "app_dir", return_value=self.dir / "MCD2SaveEditor"), \
                mock.patch.object(updater, "stage", side_effect=updater.UpdateError("The download doesn't match")), \
                mock.patch.object(updater, "start_swap") as swap, mock.patch("webbrowser.open") as browser, \
                mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            self.app.update_app()
            self.wait_until(lambda: browser.called)
        swap.assert_not_called()
        self.assertIn("The download doesn't match", ask.call_args.args[1])
        browser.assert_called_once_with(release.page)
        self.assertIn("wasn't installed", self.app.status_var.get())

    def test_share_item_ids_window(self):
        from dungeons2_editor.share_ids import ShareIdsDialog

        with mock.patch("webbrowser.open") as browser:
            # Something the game has filed in its collections that the editor has never heard of.
            self.app.profile.get(HERO).decoded.document["CharacterSaveV1"]["CollectionsStats"]["CollectedWeaponsCommon"].append("SW.Item.SomethingNew")
            self.app._share_ids()
            self.root.update()
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, ShareIdsDialog))
            self.assertIn("SW.Item.SomethingNew", dialog.report())
            self.assertNotIn("SW.Item.CurvedGreatsword", dialog.report())  # known: the Cookiecutter
            dialog.open_issue()
            self.assertIn("template=item-ids.yml", browser.call_args.args[0])
            self.assertIn("SW.Item.SomethingNew", urllib.parse.unquote_plus(browser.call_args.args[0]))
            # A list too long for a link goes on the clipboard, and the page opens ready for it to be pasted in.
            dialog.text.insert("end", "\n" + "\n".join(f"SW.Item.Thing{number} - a line that makes the list long" for number in range(200)))
            dialog.open_issue()
            link = browser.call_args.args[0]
            self.assertLess(len(link), share_ids.MAX_LINK)
            self.assertIn("paste the list here", urllib.parse.unquote_plus(link))
            self.assertIn("SW.Item.Thing199", self.root.clipboard_get())
            self.assertIn("paste the list", dialog.message.get())
        dialog.destroy()

    def test_advanced_mode_lets_stats_pass_the_game_caps(self):
        self.tab.stat_vars["Emeralds"].set("500000")
        self.assertTrue(self.tab._apply_stat("Emeralds"))
        self.assertIn("above the game's cap", self.tab.stats_message_var.get())

    def test_hero_rows_show_level_and_emeralds(self):
        details = [self.app.container_list.item(iid, "values")[0] for iid, c in self.app._containers_by_iid.items() if c.name == HERO]
        self.assertEqual(details, ["Lv 1 · 55 emeralds"])


@unittest.skipUnless(_tk_available(), "needs a display")
class SimpleModeTests(WindowTestCase):
    """Simple mode: the hero laid out like the game's inventory screen."""

    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), HERO: hero_save_text().encode()}

    @property
    def screen(self):
        return self.app.inventory

    def index_of(self, tag):
        return next(item.index for item in self.screen.hero.items() if item.tag == tag)

    def shown(self):
        return [item.name for item in self.screen._inventory_items()]

    def show(self, kind):
        self.screen.filter_var.set(kind)
        self.screen._draw_inventory()

    def saved_hero(self):
        return saves.SaveProfile(self.profile_path).get(HERO).hero

    def save(self):
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask, mock.patch("tkinter.messagebox.showinfo"):
            self.app.save_to_game()
        return ask.call_args.args[1] if ask.called else None

    def test_the_look_is_switched_from_the_menu_and_remembered(self):
        app, screen = self.app, self.screen
        style = ttk.Style(self.root)
        top, _bar, _under, _bottom = app._bars

        def room(widget):
            return [int(str(side)) for side in widget.cget("padding")]

        # The original look to begin with: square tiles and panels, and bars from edge to edge, as it always was.
        self.assertEqual((app.look, style.theme_use(), screen.glass, app.art.rounded), ("classic", game_style.THEME, False, False))
        self.assertNotIn(game_style.GLASS_THEME, style.theme_names())  # nothing of Liquid Glass is drawn until it's asked for
        self.assertEqual((room(top), room(screen.card_border), room(screen.well)), ([0], [1], [0]))
        self.assertEqual([app.look_menu.entrycget(index, "label") for index in range(2)], ["Original", "Liquid Glass"])
        self.assertEqual(app.app_menu.entrycget("Look", "menu"), str(app.look_menu))
        screen.pick_item(self.index_of("SW.Item.Longbow"))
        self.assertEqual(self.screen.inventory_canvas.type("selection"), "rectangle")

        # Liquid Glass: rounded tiles, panels with room for their corners and shadows, bars clear of the edges.
        app.look_menu.invoke(1)
        self.assertEqual((app.look, app.look_var.get(), style.theme_use(), screen.glass, app.art.rounded), ("glass", "glass", game_style.GLASS_THEME, True, True))
        self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8")), {"advanced": False, "look": "glass"})
        self.assertEqual(len(room(top)), 4)
        glass_card, glass_well = room(screen.card_border), room(screen.well)
        self.assertEqual((len(glass_card), glass_card[3] > glass_card[1] > 1, glass_well[0] > 1), (4, True, True))
        self.assertEqual(screen.selected, self.index_of("SW.Item.Longbow"))  # what was picked stays picked
        self.assertEqual(self.screen.inventory_canvas.type("selection"), "image")  # a rounded frame round the picked tile
        self.assertEqual(app.changes_var.get(), "")  # a look changes nothing in a save

        # The next time the editor opens (after an update, say), it's in the look that was chosen.
        with mock.patch.object(saves, "find_profiles", return_value=[]):
            again = gui.EditorApp(tk.Toplevel(self.root), self.profile_path, self.dir / "backups", self.dir / "icons", self.settings_file, self.names_file)
        self.assertEqual((again.look, again.look_var.get(), again.art.rounded, again.inventory.glass), ("glass", "glass", True, True))
        again.root.destroy()

        # Advanced mode keeps the Windows look whichever is chosen, and Simple mode comes back in the chosen one.
        app.advanced_var.set(True)
        app._on_advanced_toggled()
        light = style.theme_use()
        self.assertNotIn(light, (game_style.THEME, game_style.GLASS_THEME))
        app.look_var.set("classic")
        app._on_look_changed()
        self.assertEqual(style.theme_use(), light)
        app.advanced_var.set(False)
        app._on_advanced_toggled()
        self.assertEqual((style.theme_use(), room(top), room(screen.card_border), room(screen.well)), (game_style.THEME, [0], [1], [0]))
        self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8"))["look"], "classic")

    def test_a_look_can_be_asked_for_just_this_once(self):
        # The command line's --look: the window opens in that look, and the settings keep what they said.
        before = self.settings_file.read_text(encoding="utf-8")
        with mock.patch.object(saves, "find_profiles", return_value=[]):
            again = gui.EditorApp(tk.Toplevel(self.root), self.profile_path, self.dir / "backups", self.dir / "icons", self.settings_file, self.names_file, look="glass")
        self.assertEqual((again.look, again.look_var.get(), again.art.rounded, again.inventory.glass), ("glass", "glass", True, True))
        self.assertTrue(game_style.is_glass(again.root))
        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), before)
        again.root.destroy()
        # The pictures belong to the app's own window, so they outlive the window that first asked for the look.
        self.assertTrue(hasattr(self.root, "_mcd2_looks"))
        self.root.update()
        with mock.patch.object(saves, "find_profiles", return_value=[]):
            unknown = gui.EditorApp(tk.Toplevel(self.root), self.profile_path, self.dir / "backups", self.dir / "icons", self.settings_file, self.names_file, look="neon")
        self.assertEqual(unknown.look, "classic")
        unknown.root.destroy()

    def test_a_look_the_editor_doesnt_know_is_the_original(self):
        self.settings_file.write_text(json.dumps({"advanced": False, "look": "neon"}), encoding="utf-8")
        with mock.patch.object(saves, "find_profiles", return_value=[]):
            again = gui.EditorApp(tk.Toplevel(self.root), self.profile_path, self.dir / "backups", self.dir / "icons", self.settings_file, self.names_file)
        self.assertEqual((again.look, again.look_var.get()), ("classic", "classic"))
        again.root.destroy()

    def test_shows_the_game_style_screen(self):
        self.assertEqual(ttk.Style(self.root).theme_use(), game_style.GLASS_THEME if self.look == "glass" else game_style.THEME)
        self.assertTrue(self.app.simple_screen.winfo_manager())
        self.assertFalse(self.app.advanced_screen.winfo_manager())
        self.assertEqual(self.app.container.name, HERO)
        self.assertEqual(self.container_names(), [HERO])  # only heroes in Simple mode
        self.assertEqual(self.app.hero_choice_var.get(), "RANGER DELUXE  ·  LV 1")
        self.assertTrue(self.app.meta_var.get().startswith("Last saved"))
        self.assertEqual(self.screen.gear_power_var.get(), "1")  # only the Sword (power 1) is worn
        self.assertEqual(self.screen.power_part_vars["Melee"].get(), "1")
        self.assertEqual(self.screen._fixed_vars["Emeralds"].get(), "55")
        self.assertEqual(self.screen._fixed_vars["SpringStone"].get(), "")  # this hero has no echo shards yet
        self.assertEqual(self.screen.banner_text, "YOUR HERO")

    def test_gear_is_laid_out_like_the_game(self):
        labels = [slot.label for _box, slot in self.screen._gear_hits]
        self.assertEqual(labels, [
            "Melee weapon", "Ranged weapon", "Helmet", "Chestplate", "Leggings", "Boots",
            "Artifact 1", "Artifact 2", "Artifact 3", "Talisman 1", "Talisman 2", "Talisman 3",
        ])
        self.screen.pick_slot("SW.ItemSlot.Equipment.MeleeWeapon")
        self.assertEqual((self.screen.banner_text, self.screen.card_name_var.get()), ("EQUIPPED", "SWORD"))
        self.assertEqual(self.screen.equip_button.cget("text"), "UNEQUIP")
        self.assertTrue(self.screen.delete_button.instate(["disabled"]))
        self.screen.pick_slot("SW.ItemSlot.Equipment.Armor.Helmet")
        self.assertEqual(self.screen.banner_text, "EMPTY SLOT")
        self.assertTrue(self.screen.slot_add_button.instate(["!disabled"]))
        self.screen.pick_slot("SW.ItemSlot.Equipment.Artifact.Slot2")  # opens at level 5; this hero is level 1
        self.assertEqual(self.screen.banner_text, "LOCKED SLOT")
        self.assertTrue(self.screen.slot_add_button.instate(["disabled"]))

    def test_inventory_shows_what_isnt_worn(self):
        self.assertEqual(self.shown(), ["Longbow", "Mystic Circlet"])  # not the worn Sword, the merchant's stock or cosmetics
        self.assertEqual(len(self.screen._item_hits), 2)
        self.show("Merchant")
        self.assertEqual(self.shown(), ["Cookiecutter"])
        self.show("Armor")
        self.assertEqual(self.shown(), ["Mystic Circlet"])
        self.assertEqual(self.screen.count_text.get(), "1 ITEM")
        self.show("Talisman")
        self.assertEqual((self.shown(), self.screen._item_hits), ([], []))

    def test_change_rarity_and_power_on_the_card(self):
        self.screen.pick_item(self.index_of("SW.Item.MysticHelmet"))
        self.assertEqual((self.screen.banner_text, self.screen.card_name_var.get()), ("INVENTORY", "MYSTIC CIRCLET"))
        self.assertIn("Its Unique is the Oracle Crown.", self.screen.card_text_var.get())
        unique = next(button for button in self.screen.rarity_buttons if str(button.cget("value")) == "Unique")
        unique.invoke()
        # The Oracle Crown has an ID of its own that hasn't been seen in a save, so this stays a Mystic Circlet.
        self.assertEqual(self.screen.card_name_var.get(), "MYSTIC CIRCLET")
        self.assertIn("not the Oracle Crown", self.screen.item_message_var.get())
        self.assertEqual(self.screen.hero.item(self.index_of("SW.Item.MysticHelmet")).rarity, "Unique")
        self.screen.power_var.set("50")
        self.assertTrue(self.screen._apply_numbers())
        self.assertEqual(self.screen.card_power_var.get(), "50")
        self.assertIn("Mystic Circlet: Common → Unique, power 1 → 50", self.save())

    def test_bad_power_stays_on_that_item(self):
        self.screen.pick_item(self.index_of("SW.Item.MysticHelmet"))
        self.screen.power_var.set("-5")
        self.screen.pick_item(self.index_of("SW.Item.Longbow"))  # clicking away with a bad value
        self.assertEqual(self.screen.card_name_var.get(), "MYSTIC CIRCLET")
        self.assertEqual(str(self.screen.item_message.cget("style")), "CardError.TLabel")

    def test_equip_and_unequip_from_the_card(self):
        self.screen.pick_item(self.index_of("SW.Item.MysticHelmet"))
        with mock.patch("tkinter.messagebox.askyesno") as ask:
            self.screen.equip_button.invoke()
        ask.assert_not_called()
        self.assertEqual(self.screen.banner_text, "EQUIPPED")
        self.assertNotIn("Mystic Circlet", self.shown())
        self.assertEqual(self.screen.power_part_vars["Armor"].get(), "1")
        self.screen.equip_button.invoke()
        self.assertEqual(self.screen.banner_text, "INVENTORY")
        self.assertIn("Unequipped", self.screen.item_message_var.get())

    def test_a_talisman_shows_no_rarity_or_power_to_change(self):
        entry = next(entry for entry in self.screen._catalog() if entry.tag == "SW.Item.Talisman.HealthBoost")
        index = self.screen.hero.add_item(entry.tag, entry.template, rarity="Rare", power=30)
        self.screen.refresh()
        self.screen.pick_item(index)
        self.assertEqual((self.screen.card_name_var.get(), self.screen.card_power_var.get()), ("SIGIL OF BEESWAX", ""))
        self.assertTrue(self.screen.power_entry.instate(["disabled"]))
        self.assertTrue(all(button.instate(["disabled"]) for button in self.screen.rarity_buttons))
        self.assertIn("no rarity or power", self.screen.power_hint.get())
        self.assertNotIn("no effect saved", self.screen.power_hint.get())
        self.assertEqual(self.screen.power_var.get(), "")
        self.assertFalse(self.screen.has_pending_input())
        self.assertTrue(self.screen.equip_button.instate(["!disabled"]))
        # One an older version added (Common, with a power and no effect) is told apart, and can be replaced.
        self.screen.hero.item(index).data.update(RarityTag="SW.Rarity.Common", Effects=[])
        self.screen.hero.item(index).progression["ItemLevels"] = []
        self.screen.refresh()
        self.screen.pick_item(index)
        self.assertIn("This one has no effect saved, so it may do nothing in the game. Delete it and add it again", self.screen.power_hint.get())
        self.screen.pick_item(self.index_of("SW.Item.Longbow"))  # other items get their rarity and power back
        self.assertTrue(self.screen.power_entry.instate(["!disabled"]))

    def test_a_unique_comes_with_its_own_effect_and_an_older_one_can_be_given_it(self):
        entry = next(entry for entry in self.screen._catalog() if entry.tag == "SW.Item.Sword")
        button = self.screen.effects_button
        blade = self.screen.hero.add_item("SW.Item.Sword_Unique1", entry.template, rarity="Unique")
        self.screen.refresh()
        self.screen.pick_item(blade)
        self.assertEqual((self.screen.enchant_title.get(), self.screen.enchant_text.get()), ("EFFECTS", "Its own: Fire Focus"))
        self.assertEqual(self.screen.card_text_var.get(), "Fire attacks deal 20% more damage.")
        self.assertEqual(str(button.cget("text")), "CHANGE EFFECTS…")
        # One made by a version that couldn't write that effect: the card says so, and the button puts it right.
        self.screen.hero.item(blade).data["Effects"] = [rolled(rolled_effect("CriticalEdge", 0.2, "II"))]
        self.screen.refresh()
        self.screen.pick_item(blade)
        self.assertEqual(self.screen.enchant_text.get().splitlines(), ["Without its own effect.", "Critical Edge II 20%"])
        self.assertEqual(self.screen.card_text_var.get(), "In the game: Fire attacks deal 20% more damage.")
        self.assertEqual((str(button.cget("text")), button.instate(["!disabled"])), ("ADD ITS OWN EFFECT", True))
        button.invoke()
        self.assertEqual(self.screen.enchant_text.get().splitlines(), ["Its own: Fire Focus", "Critical Edge II 20%"])
        self.assertIn("The Burning Blade has its own effect now, saved the way the game saves it.", self.screen.item_message_var.get())
        self.assertEqual(str(button.cget("text")), "CHANGE EFFECTS…")
        self.assertEqual(self.screen.hero.item(blade).data["Effects"][0]["TypeTag"], "SW.Item.Effect.Static")
        # With nothing on it at all, the card says what the button does.
        self.screen.hero.item(blade).data["Effects"] = []
        self.screen.refresh()
        self.screen.pick_item(blade)
        self.assertEqual((self.screen.enchant_title.get(), self.screen.enchant_text.get()),
                         ("NO EFFECTS", "Without its own effect. The button adds it, saved the way the game saves it."))
        # A Unique whose own effect the editor hasn't seen: it says so, and the button changes the other effects.
        promise = self.screen.hero.add_item("SW.Item.Bow_Unique1", entry.template, rarity="Unique")
        self.screen.refresh()
        self.screen.pick_item(promise)
        self.assertEqual(
            self.screen.enchant_text.get(),
            "Without its own effect: the editor can't add that one yet. Give it any other you like, and an enchantment.",
        )
        self.assertTrue(self.screen.card_text_var.get().startswith("In the game: "))
        self.assertEqual(str(button.cget("text")), "CHANGE EFFECTS…")
        # An item that isn't a Unique never gets the note.
        self.screen.pick_item(self.index_of("SW.Item.Sword"))
        self.assertIn("The game rolls a Rare item one effect and a Special item two.", self.screen.enchant_text.get())

    def test_an_items_effects_are_listed_on_its_card(self):
        sword = self.index_of("SW.Item.Sword")
        button = self.screen.effects_button
        self.screen.pick_item(sword)
        self.assertEqual(self.screen.enchant_title.get(), "NO EFFECTS")  # a weapon with nothing on it yet
        self.assertIn("Give this one any you like, and an enchantment.", self.screen.enchant_text.get())
        self.assertEqual((str(button.cget("text")), button.instate(["!disabled"])), ("CHANGE EFFECTS…", True))
        self.screen.hero.item(sword).data["Effects"] = [
            rolled(*[rolled_effect(f"Effect{number}", number) for number in range(1, 5)]), enchanted(enchantment_effect("Radiance", 0.3)),
            {"TypeTag": "SW.Item.Effect.Fixed", "EffectsInThisBatch": [rolled_effect("Burning", 1, "Unique")]},
        ]
        self.screen.refresh()
        self.screen.pick_item(sword)
        self.assertEqual(self.screen.enchant_title.get(), "EFFECTS")
        self.assertEqual(self.screen.enchant_text.get().splitlines(), ["Effect1 I 1", "Effect2 I 2", "Effect3 I 3", "Effect4 I 4", "and 2 more"])
        self.assertTrue(self.screen.enchant_box.winfo_manager())
        # A talisman's effect comes with its level, and the button gets it ready for the next one.
        entry = next(entry for entry in self.screen._catalog() if entry.tag == "SW.Item.Talisman.HealthBoost")
        sigil = self.screen.hero.add_item(entry.tag, entry.template)
        self.screen.refresh()
        self.screen.pick_item(sigil)
        self.assertEqual(self.screen.enchant_title.get(), "EFFECT")
        self.assertEqual(self.screen.enchant_text.get().splitlines(), ["Health Boost 1.2", "Level 1 of 3 (0 of 18,480 XP). At the next levels: 1.25, then 1.35."])
        self.assertEqual((str(button.cget("text")), button.instate(["!disabled"])), ("LEVEL UP", True))
        button.invoke()
        self.assertEqual((self.screen.hero.item(sigil).level, self.screen.hero.item(sigil).xp), (1, 18480))
        self.assertIn("The Sigil of Beeswax is level 2 now, saved the way the game saves a level-up.", self.screen.item_message_var.get())
        self.assertEqual(self.screen.enchant_text.get().splitlines(), ["Health Boost 1.25", "Level 2 of 3. At the next level: 1.35."])
        # An artifact gets effects but no enchantment; the merchant's stock is left alone; a cosmetic has nothing to show.
        horn = self.screen.hero.add_item("SW.Item.Artifact.RallyingHorn", entry.template)
        self.screen.refresh()
        self.screen.pick_item(horn)
        self.assertEqual(self.screen.enchant_title.get(), "NO EFFECTS")
        self.assertNotIn("enchantment", self.screen.enchant_text.get())
        self.assertTrue(button.instate(["!disabled"]))
        self.screen.pick_item(self.index_of("SW.Item.CurvedGreatsword"))
        self.assertTrue(button.instate(["disabled"]))
        self.screen.pick_item(self.index_of("SW.Item.Cosmetic.Cape.Hero"))
        self.assertFalse(self.screen.enchant_box.winfo_manager())

    def test_the_card_scrolls_when_its_too_short_for_what_it_shows(self):
        # On a small screen, or a display Windows scales up, the card used to cut off its lower buttons.
        screen = self.screen
        screen.pick_item(self.index_of("SW.Item.Longbow"))
        self.root.minsize(1, 1)
        self.root.geometry("1280x520")
        self.root.deiconify()
        self.root.update()
        if not self.root.winfo_viewable():
            self.skipTest("windows can't be shown here")
        needed = screen.card_content.winfo_reqheight()
        self.assertLess(screen.card_view.winfo_height(), needed)
        self.assertTrue(screen.card_scroll.winfo_ismapped())
        screen.card_view.yview_moveto(1)
        self.root.update()
        self.assert_in_view(screen.name_button, screen.card)  # the last button can be reached
        # What's said about a change stays in view, below whatever scrolls.
        screen._say_item("Changed. Press Save to game when you're done.")
        self.root.update()
        self.assert_in_view(screen.item_message, screen.card)
        screen.pick_item(self.index_of("SW.Item.MysticHelmet"))
        self.root.update()
        self.assertEqual((screen.card_view.yview()[0], screen.item_message.winfo_manager()), (0.0, ""))  # another item: from the top, nothing said yet
        # With room for everything, nothing scrolls.
        self.root.geometry(f"1280x{self.root.winfo_height() + needed}")
        self.root.update()
        if screen.card_view.winfo_height() >= screen.card_content.winfo_reqheight():
            self.assertFalse(screen.card_scroll.winfo_ismapped())

    def test_no_get_pictures_button_in_the_edition_that_never_goes_online(self):
        from dungeons2_editor import edition

        self.screen._draw_inventory()
        self.assertTrue(self.screen.pictures_button.winfo_manager())  # no pictures yet, so the button offers to get them
        with mock.patch.object(edition, "ONLINE", False):
            self.screen._draw_inventory()
            self.assertFalse(self.screen.pictures_button.winfo_manager())

    def test_effects_are_changed_from_the_card(self):
        sword = self.index_of("SW.Item.Sword")
        self.screen.pick_item(sword)

        def choose(dialog):
            self.assertIsInstance(dialog, EffectsDialog)
            self.assertFalse(dialog.enchantsmith_opened)  # nothing in this save says the hero has been to the Enchantsmith
            self.assertTrue(dialog.select("Looter"))
            dialog.add()
            self.assertTrue(dialog.select("Healing Smite"))
            dialog.add()
            dialog.apply()

        with mock.patch.object(self.screen, "wait_window", side_effect=choose):
            self.screen.effects_button.invoke()
        self.assertEqual(self.screen.enchant_text.get().splitlines(), ["Looter I 20%", "Enchanted: Healing Smite I, 1 enchantment point"])
        self.assertIn("Effects changed.", self.screen.item_message_var.get())
        self.assertIn("Sword: effects: Looter I 20%, enchanted with Healing Smite I", self.save())
        self.assertEqual(self.saved_hero().item(sword).effect_lines(), ["Looter I 20%", "Enchanted: Healing Smite I, 1 enchantment point"])

    def test_merchant_stock_can_be_copied_but_not_worn(self):
        self.show("Merchant")
        self.screen.pick_item(self.index_of("SW.Item.CurvedGreatsword"))
        self.assertEqual(self.screen.banner_text, "MERCHANT STOCK")
        self.assertTrue(self.screen.equip_button.instate(["disabled"]))
        self.assertTrue(self.screen.change_button.instate(["disabled"]))  # the game stocks the merchant; a copy can be changed
        self.assertTrue(self.screen.power_entry.instate(["!disabled"]))
        self.screen.copy_button.invoke()
        self.assertIn("Copied", self.screen.item_message_var.get())
        self.assertEqual(self.screen.banner_text, "INVENTORY")  # the copy is yours
        self.show("All")
        self.assertIn("Cookiecutter", self.shown())

    def test_delete_from_the_card(self):
        self.screen.pick_item(self.index_of("SW.Item.Longbow"))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            self.screen.delete_button.invoke()
        self.assertEqual(self.shown(), ["Mystic Circlet"])
        self.assertEqual(self.screen.banner_text, "YOUR HERO")
        self.assertIn("Removed Longbow", self.save())

    def test_stats_stop_at_the_game_caps(self):
        emeralds = self.screen.stat_vars["Emeralds"]
        emeralds.set("500000")
        self.assertFalse(self.screen._apply_stat("Emeralds"))
        self.assertIn("cap", self.screen.stats_message_var.get())
        self.assertEqual(str(self.screen.stats_message.cget("style")), "MessageError.TLabel")
        self.assertEqual(emeralds.get(), "55")
        emeralds.set("99998")
        self.assertTrue(self.screen._apply_stat("Emeralds"))
        self.assertEqual(self.screen._nudge_stat("Emeralds", 5), "break")  # arrow keys stop at the cap
        self.assertEqual(emeralds.get(), "99999")
        self.app.advanced_var.set(True)
        self.app._on_advanced_toggled()
        self.assertEqual(self.app.hero_tab.stat_vars["Emeralds"].get(), "99999")  # the Hero tab sees the change
        self.app.hero_tab.stat_vars["Emeralds"].set("500000")
        self.assertTrue(self.app.hero_tab._apply_stat("Emeralds"))  # Advanced mode may go past the caps
        self.app.advanced_var.set(False)
        self.app._on_advanced_toggled()
        self.assertEqual(self.screen.stat_vars["Emeralds"].get(), "500000")

    def test_level_opens_gear_slots(self):
        self.screen.stat_vars["Level"].set("5")
        self.assertTrue(self.screen._apply_stat("Level"))
        self.assertEqual(self.app.hero_choice_var.get(), "RANGER DELUXE  ·  LV 5")
        self.screen.pick_slot("SW.ItemSlot.Equipment.Artifact.Slot2")
        self.assertEqual(self.screen.banner_text, "EMPTY SLOT")
        self.screen.pick_slot("SW.ItemSlot.Equipment.Artifact.Slot3")
        self.assertEqual(self.screen.banner_text, "LOCKED SLOT")

    def test_stats_card_lists_every_stat(self):
        self.screen.show_stats()
        self.assertEqual(self.screen.card_name_var.get(), "STATS & TOWN")
        entries = [w for w in self.screen.stats_box.winfo_children() if isinstance(w, ttk.Entry)]
        self.assertEqual(len(entries), len(self.screen.hero.attributes()))
        notes = [str(w.cget("text")) for w in self.screen.stats_box.winfo_children() if isinstance(w, ttk.Label)]
        self.assertIn("This hero hasn't opened a town vendor in the game yet. The game notes the first time you open each one's window.", notes)
        self.assertIs(self.screen.stat_vars["Emeralds"], self.screen._fixed_vars["Emeralds"])  # the same as the top bar's
        self.screen._close_stats()
        self.assertEqual(self.screen.banner_text, "YOUR HERO")

    def test_typed_values_are_kept_when_saving(self):
        self.screen.stat_vars["XP"].set("900")  # typed, then straight to Save to game
        self.screen.pick_item(self.index_of("SW.Item.Longbow"))
        self.screen.power_var.set("9")
        summary = self.save()
        self.assertIn("XP: 845.5 → 900", summary)
        self.assertIn("Longbow: power 2 → 9", summary)

    def test_save_button_and_shortcut(self):
        self.assertTrue(self.app.simple_save_button.instate(["disabled"]))
        self.screen.stat_vars["Emeralds"].set("123")
        self.assertTrue(self.screen._apply_stat("Emeralds"))
        self.assertEqual(self.app.changes_var.get(), "1 unsaved change")
        self.assertTrue(self.app.simple_save_button.instate(["!disabled"]))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True), mock.patch("tkinter.messagebox.showinfo"):
            self.app._save_shortcut()
        self.assertEqual(self.saved_hero().attribute("Emeralds"), 123)

    def test_launch_game_starts_the_copy_the_saves_belong_to(self):
        app = self.app
        launch_buttons = (app.simple_launch_button, app.launch_button)
        self.assertEqual(app.app_menu.entrycget(0, "label"), "Launch Minecraft Dungeons II")
        with mock.patch.object(gui.game_launch, "target", return_value="somewhere to open"):
            app._update_buttons()
            self.assertTrue(all(button.instate(["!disabled"]) for button in launch_buttons))
            with mock.patch.object(gui.game_launch, "launch") as launch:
                app.simple_launch_button.invoke()
            launch.assert_called_once_with("xbox")  # these saves are the Xbox app's
            self.assertEqual(app.status_var.get(), "Starting Minecraft Dungeons II…")
            # While the game runs there's nothing to start.
            app.game_running = ["Dungeons.exe"]
            app._update_buttons()
            self.assertTrue(all(button.instate(["disabled"]) for button in launch_buttons))
            with mock.patch.object(gui.game_launch, "launch") as launch:
                app.launch_game()  # from the menu, say
            launch.assert_not_called()
            self.assertEqual(app.status_var.get(), "Minecraft Dungeons II is already running.")
            app.game_running = []
            # When it can't be started, the editor says where to start it instead.
            with mock.patch.object(gui.game_launch, "launch", side_effect=gui.game_launch.LaunchError("Start it from the Xbox app.")), \
                    mock.patch("tkinter.messagebox.showinfo") as told:
                app.launch_game()
            self.assertEqual(told.call_args.args[1], "Start it from the Xbox app.")
        # Where the editor can't start the game at all (a Mac, say), the button is there but switched off.
        with mock.patch.object(gui.game_launch, "target", return_value=None):
            app._update_buttons()
            self.assertTrue(all(button.instate(["disabled"]) for button in launch_buttons))

    def test_launching_with_unsaved_changes_asks_first(self):
        app = self.app
        self.screen.stat_vars["Emeralds"].set("123")
        self.assertTrue(self.screen._apply_stat("Emeralds"))
        with mock.patch.object(gui.game_launch, "target", return_value="somewhere to open"), mock.patch.object(gui.game_launch, "launch") as launch:
            with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
                app.launch_game()
            launch.assert_not_called()  # No: save first
            self.assertIn("You have 1 unsaved change, and the editor can't save while the game is running.", ask.call_args.args[1])
            self.assertEqual(ask.call_args.kwargs["default"], "no")
            with mock.patch("tkinter.messagebox.askyesno", return_value=True):
                app.launch_game()
            launch.assert_called_once_with("xbox")
        self.assertEqual(app.changes_var.get(), "1 unsaved change")  # still here, for when the game is closed again

    def test_the_play_recorder_writes_down_what_the_game_saves(self):
        out = self.dir / "recordings"
        with mock.patch.object(recorder, "DEFAULT_OUT", out):
            self.app.app_menu.invoke(self.app.app_menu.index("Play recorder…"))
        (dialog,) = [child for child in self.root.winfo_children() if isinstance(child, gui.RecorderDialog)]
        self.assertEqual((dialog.out, dialog.profile, dialog.start_button.cget("text")), (out, self.profile_path, "Start recording"))
        self.assertTrue(dialog.note_button.instate(["disabled"]))  # nothing to add a note to yet
        self.assertFalse(out.exists())  # opening the window writes nothing
        dialog.start_button.invoke()
        self.assertEqual(dialog.start_button.cget("text"), "Stop recording")
        (session,) = list(out.iterdir())
        self.assertIn("level 1, 5 items", dialog.shown_text())  # what's there to begin with

        # The game saves: the recorder reads the saves again and says what changed.
        profile = saves.SaveProfile(self.profile_path)
        document = copy.deepcopy(profile.get(HERO).decoded.document)
        for attribute in document["CharacterSaveV1"]["Ability"]["Attributes"]:
            if attribute["AttributeName"] == "Emeralds":
                attribute["CurrentValue"] = 300
        profile.save(HERO, document, self.dir / "backups", check_game=lambda: [])
        self.assertNotEqual(saves.profile_stamp(self.profile_path), dialog._stamp)  # which is how it notices
        dialog._tick()  # the folder changed: it waits a moment for the game to finish writing, then reads
        dialog._look()
        self.assertIn("Emeralds: 55 -> 300", dialog.shown_text())
        dialog.note_var.set("  bought a sword  ")
        dialog.note_button.invoke()
        self.assertEqual(dialog.note_var.get(), "")
        self.assertIn("note: bought a sword", dialog.shown_text())

        with mock.patch("tkinter.messagebox.askyesnocancel") as ask:
            dialog.start_button.invoke()  # Stop recording
        ask.assert_not_called()  # nothing here for the Soul Storm check to ask about
        self.assertEqual(dialog.start_button.cget("text"), "Start recording")
        summary = (session / "summary.txt").read_text(encoding="utf-8")
        self.assertIn("Emeralds: 55 -> 300 in 1 step(s)", summary)
        self.assertIn("bought a sword", summary)
        self.assertIn("World progress:", dialog.shown_text())
        self.assertEqual(len(list((session / "snapshots").iterdir())), 3)  # the hero twice, the settings once
        dialog.map_button.invoke()
        self.assertTrue((out / "world_progress_atlas.json").exists() and (out / "world_map.txt").exists())
        self.assertIn("hero saves read.", dialog.shown_text())
        dialog.close()
        self.assertFalse(dialog.winfo_exists())
        # If the editor closes while it's recording, the recording's file is closed with it and nothing is left waiting.
        with mock.patch.object(recorder, "DEFAULT_OUT", out):
            left_open = self.app.open_recorder()
        left_open.start()
        events = left_open.recorder.events_file
        left_open.destroy()
        self.assertTrue(events.closed and left_open.recorder is None and left_open._timer is None)
        # With no saves open there's nothing to record.
        self.app.profile = None
        with mock.patch("tkinter.messagebox.showinfo") as told:
            self.assertIsNone(self.app.open_recorder())
        self.assertIn("no saves open to record", told.call_args.args[1])

    def test_whats_new_is_shown_the_first_time_a_version_opens_and_from_the_menu(self):
        app = self.app
        notes = whats_new.parse(
            f"## What's new in {__version__}\n\n- **A new thing.** With `code`.\n  - A point under it.\n\n"
            "## What's new in 0.9.1\n\n- A fix.\n\n## What's new in 0.9.0\n\n- The first.\n"
        )

        def dialogs():
            return [child for child in self.root.winfo_children() if isinstance(child, whats_new.WhatsNewDialog)]

        self.assertEqual(dialogs(), [])  # opening the editor in a test, or to check a build, shows nothing
        with mock.patch.object(gui.whats_new, "load", return_value=notes):
            # The first time this version opens here: its own notes, once.
            self.assertTrue(app.greet_new_version())
            (dialog,) = dialogs()
            self.assertEqual(dialog.shown_text(), "•  A new thing. With code.\n–  A point under it.")
            self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8"))["seen_version"], __version__)
            dialog.close_button.invoke()
            self.assertEqual(dialogs(), [])
            self.assertFalse(app.greet_new_version())
            self.assertEqual(dialogs(), [])
            # After an update: everything since the version that was here before.
            app.settings["seen_version"] = "0.9.0"
            self.assertTrue(app.greet_new_version())
            (dialog,) = dialogs()
            self.assertEqual(dialog.shown_text().splitlines()[0], f"Version {__version__}")
            self.assertIn("Version 0.9.1\n•  A fix.", dialog.shown_text())
            self.assertNotIn("The first.", dialog.shown_text())
            dialog.destroy()
            # The menu shows the newest few whenever you ask.
            app.app_menu.invoke(app.app_menu.index("What's new…"))
            (dialog,) = dialogs()
            self.assertIn("The first.", dialog.shown_text())
            dialog.destroy()
        # Nothing to show (the notes didn't come with this copy): the version is remembered all the same.
        app.settings.pop("seen_version")
        with mock.patch.object(gui.whats_new, "load", return_value=[]):
            self.assertFalse(app.greet_new_version())
        self.assertEqual((dialogs(), app.settings["seen_version"]), ([], __version__))

    def test_enchantment_books_have_a_tab_of_their_own(self):
        button, bar = self.screen.books_button, self.screen.books_bar
        self.assertFalse(bar.winfo_manager())  # only on the Books tab
        self.show(BOOK_KIND)
        self.assertEqual((self.shown(), self.screen.count_text.get()), ([], "0 BOOKS"))
        self.assertIn("No enchantment books in your inventory. ADD EVERY BOOK gives your hero all the ones the editor knows", self.screen._nothing_here())
        self.assertTrue(bar.winfo_manager())
        self.assertEqual(self.screen.books_text.get(), "9 missing")
        button.invoke()
        self.assertEqual((len(self.shown()), self.screen.count_text.get()), (9, "9 BOOKS"))
        self.assertFalse(bar.winfo_manager())  # none left to add
        self.assertEqual(self.screen.item_message_var.get(), "Added 9 enchantment books, saved the way the game saves one. Press Save to game when you're done.")
        self.assertEqual(self.app.changes_var.get(), "18 unsaved changes")  # each book, and its line in the loot you've discovered
        # A book's card: what its enchantment does, and nothing to set but whether it's there.
        screen = self.screen
        screen.pick_item(self.index_of("SW.Item.EnchantmentBook.MultiRoll"))
        self.assertEqual((screen.card_name_var.get(), screen.card_kind_var.get(), screen.card_power_var.get()), ("SOMERSAULT", "Enchantment book", ""))
        self.assertEqual(screen.card_text_var.get(), "The book of an enchantment for armor. Extra rolls: +1 / +2 / +3 rolls at tiers I, II and III.")
        self.assertFalse(screen.badge.winfo_manager())  # no rarity to show
        for widget in (screen.power_entry, screen.count_entry, screen.copy_button, screen.change_button, screen.equip_button, *screen.rarity_buttons):
            self.assertTrue(widget.instate(["disabled"]), widget)
        self.assertTrue(screen.delete_button.instate(["!disabled"]))
        self.assertFalse(screen.enchant_box.winfo_manager())  # a book has no effects of its own
        self.assertEqual(
            screen.power_hint.get(),
            "An enchantment book has no rarity or power. A hero has one of each enchantment book, and the Enchantsmith works "
            "from the ones in your inventory.",
        )
        self.assertFalse(screen.has_pending_input())
        box, _tile, _index = next(hit for hit in screen._item_hits if hit[2] == screen.selected)
        tip = screen._inventory_tip(mock.Mock(x=box[0] + 2, y=box[1] + 2))
        self.assertEqual(tip, "Somersault\nEnchantment book")
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            screen.delete_button.invoke()
        self.assertEqual((len(self.shown()), screen.count_text.get()), (8, "8 BOOKS"))
        self.assertEqual((bool(bar.winfo_manager()), self.screen.books_text.get()), (True, "1 missing"))
        self.show("All")
        self.assertFalse(bar.winfo_manager())
        self.assertEqual(len([name for name in self.shown() if name in ("Piercing", "Ricochet", "Shockwave")]), 3)  # books are items too
        summary = self.save()
        self.assertIn("Added Ricochet (enchantment book)", summary)
        self.assertNotIn("Somersault", summary)  # added and deleted again
        saved = self.saved_hero().books()
        self.assertEqual((len(saved), {item.rarity for item in saved}, {item.power for item in saved}, {item.count for item in saved}), (8, {"None"}, {-1}, {1}))

    def test_add_items_starts_on_the_kind_being_shown(self):
        self.show(BOOK_KIND)
        self.screen.add_items()
        self.root.update()
        picker = next(w for w in self.screen.winfo_children() if isinstance(w, ItemPicker))
        self.assertEqual(picker.kind_var.get(), BOOK_KIND)
        rows = picker.tree.get_children()
        self.assertEqual(len(rows), 9)
        self.assertEqual({picker.tree.item(row, "values") for row in rows}, {("Enchantment Book", "Confirmed")})
        first = rows[0]
        self.assertEqual((picker.tree.selection(), picker.tree.item(first, "text").strip()), ((first,), "Ancient Alchemy"))
        # Rarity, power and count are for gear.
        self.assertTrue(all(widget.instate(["disabled"]) for widget in picker.grade_inputs))
        self.assertEqual(
            picker.unique_text.get(),
            "An enchantment book has no rarity or power. A hero has one of each enchantment book. The book of an enchantment "
            "for armor. Potions grant souls: 30 / 45 / 60 souls at tiers I, II and III.",
        )
        self.assertEqual((picker.slot_note.get(), picker.equip_check.instate(["disabled"])), ("", True))
        self.assertTrue(picker.books_button.winfo_manager())
        picker.count_var.set("5")  # left over from a stack of something else
        picker.rarity_var.set("Unique")
        with mock.patch("tkinter.messagebox.askyesno") as ask:
            picker._confirm()
        ask.assert_not_called()
        self.assertEqual(picker.message_var.get(), "Added the Ancient Alchemy book. Add more, or close this window.")
        self.assertEqual(picker.tree.item(first, "values")[1], "You have it")
        self.assertTrue(picker.confirm_button.instate(["disabled"]))  # one of each
        picker.tree.selection_set(rows[1])
        self.root.update()
        self.assertTrue(picker.confirm_button.instate(["!disabled"]))
        made = next(item for item in self.screen.hero.books())
        self.assertEqual((made.name, made.rarity, made.power, made.count), ("Ancient Alchemy", "None", -1, 1))
        self.assertEqual(self.screen.item_message_var.get(), "Added the Ancient Alchemy book, saved the way the game saves one. Press Save to game when you're done.")
        # Back on gear, the boxes work again and there's nothing about books.
        picker.kind_var.set("Melee")
        picker._fill()
        self.root.update()
        self.assertTrue(all(widget.instate(["!disabled"]) for widget in picker.grade_inputs))
        self.assertFalse(picker.books_button.winfo_manager())
        self.assertTrue(picker.confirm_button.instate(["!disabled"]))
        picker.destroy()
        # From any other tab the list starts where it always did, or on that tab's kind.
        for shown, kind in (("All", "All kinds"), ("Merchant", "All kinds"), ("Artifact", "Artifact")):
            self.show(shown)
            self.screen.add_items()
            self.root.update()
            picker = next(w for w in self.screen.winfo_children() if isinstance(w, ItemPicker))
            self.assertEqual(picker.kind_var.get(), kind)
            picker.destroy()

    def test_put_an_item_in_an_empty_slot(self):
        self.screen.pick_slot("SW.ItemSlot.Equipment.Armor.Helmet")
        self.screen.slot_add_button.invoke()
        self.root.update()
        picker = next(w for w in self.screen.winfo_children() if isinstance(w, ItemPicker))
        names = [picker.tree.item(i, "text").strip() for i in picker.tree.get_children()]
        self.assertIn("Mystic Circlet", names)
        self.assertNotIn("Sword", names)
        row = next(i for i in picker.tree.get_children() if picker.tree.item(i, "text").strip() == "Mystic Circlet")
        picker.tree.selection_set(row)
        self.root.update()
        with mock.patch("tkinter.messagebox.askyesno") as ask:
            picker._confirm()
        ask.assert_not_called()  # a confirmed item, in a slot the game's own files name
        picker.destroy()
        self.assertEqual(self.screen.hero.equipped("SW.ItemSlot.Equipment.Armor.Helmet").name, "Mystic Circlet")
        self.assertEqual(self.screen.banner_text, "EQUIPPED")  # the card shows what was added

    def test_slots_that_open_later_are_offered_but_locked(self):
        self.screen.open_add_items()
        self.root.update()
        picker = next(w for w in self.screen.winfo_children() if isinstance(w, ItemPicker))
        picker.search_var.set("Firework Arrow")
        self.root.update()
        row = next(i for i in picker.tree.get_children() if picker.tree.item(i, "text").strip() == "Firework Arrow")
        picker.tree.selection_set(row)
        self.root.update()
        picker.equip_var.set(True)
        picker._show_slot()
        self.assertEqual(list(picker.slot_box["values"]), ["Artifact 1: empty", "Artifact 2: opens at level 5", "Artifact 3: opens at level 10"])
        picker.slot_var.set("Artifact 3: opens at level 10")
        picker._pick_slot()
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            picker._confirm()
        ask.assert_not_called()  # a confirmed item in a slot the game's files name
        self.assertEqual(str(picker.message.cget("style")), "Error.TLabel")
        self.assertIn("opens at level 10", picker.message_var.get())
        picker.destroy()
        self.assertEqual(self.app.change_count, 0)

    def test_kit_preset_adds_and_equips_a_loadout(self):
        from dungeons2_editor import presets
        from dungeons2_editor.presets_dialog import PresetsDialog

        self.screen.open_presets()
        self.root.update()
        dialog = next(w for w in self.screen.winfo_children() if isinstance(w, PresetsDialog))
        number = next(i for i, p in enumerate(presets.PRESETS) if p.title == "Melee damage")
        dialog.listing.selection_set(str(number))
        self.root.update()
        self.assertEqual(dialog.title_var.get(), "Melee damage")
        self.assertTrue(dialog.rarity_row.winfo_manager())
        self.assertTrue(dialog.equip_var.get())
        self.assertFalse(dialog.include_unconfirmed.get())  # the game removed them in testing
        self.assertIn("the game removed every unconfirmed item a kit added", dialog.text.get("1.0", "end"))
        dialog.include_unconfirmed.set(True)
        dialog._refresh()
        text = dialog.text.get("1.0", "end")
        self.assertIn("Enchantments to pick in the game", text)
        self.assertIn("Melee weapon\tLightning Surge (book: Any area)", text)
        dialog.power_var.set("40")
        dialog._refresh()
        text = dialog.text.get("1.0", "end")
        self.assertIn("Unique gear at power 40, equipped:", text)
        self.assertIn("\tMelee weapon\tPride of the Plains\n", text)
        # Most of the kit's Uniques come with the effect of their own; the editor names the ones that can't yet.
        self.assertIn("A Unique's own effect comes on top, as the game saves it.", text)
        self.assertIn("of these Uniques", text)
        self.assertIn("own effect (", text)
        # This hero is level 1, and artifact slots 2 and 3 open at levels 5 and 10.
        self.assertIn("\tArtifacts\tWarrior Drums, Death Cap Mushroom (inventory), Grindstone (inventory)\n", text)
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            dialog._apply()
        ask.assert_called_once()  # most of the kit's item IDs are best guesses
        self.assertTrue(dialog.message_var.get().startswith("Applied Melee damage"))
        dialog.destroy()
        hero = self.screen.hero
        self.assertEqual(hero.equipped("SW.ItemSlot.Equipment.MeleeWeapon").name, "Pride of the Plains")
        self.assertEqual(hero.equipped("SW.ItemSlot.Equipment.Armor.Helmet").name, "Twisted Warden Blindfold")
        self.assertIsNone(hero.equipped("SW.ItemSlot.Equipment.Artifact.Slot2"))  # this hero is level 1
        self.assertEqual(self.screen.gear_power_var.get(), "40")
        self.assertIn("Preset applied", self.screen.stats_message_var.get())

    def test_reloads_when_the_game_saves_and_nothing_is_unsaved(self):
        game = saves.SaveProfile(self.profile_path)
        document = copy.deepcopy(game.get(HERO).decoded.document)
        Hero(document).set_attributes({"XP": 3000})
        game.save(HERO, document, self.dir / "game-backups", check_game=lambda: [])
        self.app.game_running = []
        self.app._check_disk()
        self.assertEqual(self.screen.stat_vars["XP"].get(), "3000")

    def test_help_page(self):
        self.app.page_var.set("help")
        self.app._show_page()
        self.assertTrue(self.app.simple_help.winfo_manager())
        self.assertFalse(self.screen.winfo_manager())
        self.assertIn("EDITING YOUR HERO", self.app.simple_help_text.get("1.0", "end"))
        self.app.page_var.set("inventory")
        self.app._show_page()
        self.assertTrue(self.screen.winfo_manager())

    def test_menu_has_the_tools(self):
        menu = self.app.app_menu
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]
        for label in ("Reload", "Back up now", "Restore a backup…", "Get item pictures…", "Open the pictures folder", "Share item IDs…",
                      "Connect an AI (MCP)…", "Save profile"):
            self.assertIn(label, labels)
        self.assertIn("Lemma: a free creative studio for Minecraft ↗", labels)
        self.assertIn("Batchly: free browser games, tools and experiments ↗", labels)

    def test_help_links_to_the_developers_sites(self):
        for text in (self.app.simple_help_text, self.app.help_text):
            self.assertIn("https://lemma.ishiakiz.com", text.get("1.0", "end"))
            self.assertIn("https://batch-ly.com", text.get("1.0", "end"))
            self.assertTrue(text.tag_ranges("link:https://batch-ly.com"))  # a link you can click
        with mock.patch("webbrowser.open") as browser:
            self.app.app_menu.invoke("Batchly: free browser games, tools and experiments ↗")
        browser.assert_called_once_with("https://batch-ly.com")

    def test_connect_an_ai_window(self):
        from dungeons2_editor.ai_dialog import ConnectAiDialog

        self.app._connect_ai()
        self.root.update()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, ConnectAiDialog))
        config = json.loads(dialog.sections["desktop"])
        self.assertEqual(config["mcpServers"]["mcd2-save-editor"]["args"][-1], "mcp")
        self.assertIn("claude mcp add mcd2-save-editor --", dialog.sections["code"])
        dialog.copy("code")
        self.assertEqual(self.root.clipboard_get(), dialog.sections["code"])
        dialog.destroy()

    def test_paste_a_picture_from_the_game(self):
        from tests.test_icons import Image, game_tile

        if Image is None:
            self.skipTest("needs Pillow")
        self.screen.pick_item(self.index_of("SW.Item.MysticHelmet"))
        with mock.patch("PIL.ImageGrab.grabclipboard", return_value=None):
            self.screen.picture_button.invoke()
        self.assertIn("Windows+Shift+S", self.screen.item_message_var.get())
        with mock.patch("PIL.ImageGrab.grabclipboard", return_value=game_tile()):
            self.screen.picture_button.invoke()
        kept = self.dir / "icons" / "captured" / "Mystic Circlet.png"
        self.assertTrue(kept.is_file())
        with Image.open(kept) as picture:
            self.assertEqual(picture.size, (46, 46))  # just the item, cut out of the tile
        self.assertIn("kept on this PC", self.screen.item_message_var.get())
        self.assertEqual(self.app.icons.find("SW.Item.MysticHelmet"), kept)

    def test_name_an_item_the_editor_doesnt_know(self):
        self.screen.pick_item(self.index_of("SW.Item.MysticHelmet"))
        self.assertTrue(self.screen.name_button.instate(["disabled"]))  # the game's list names it
        # The Longbow turns into an artifact that's been seen in saves, but that nobody has named yet.
        longbow = self.index_of("SW.Item.Longbow")
        self.screen.hero.update_item(longbow, tag="SW.Item.Artifact.HasteMushroom")
        self.screen.hero.item(longbow).data["DynamicPropertyTags"].clear()  # and the game has shown it to you since
        self.screen.refresh()
        self.screen.pick_item(longbow)
        self.assertIn("name made from its save ID", self.screen.card_kind_var.get())
        self.assertTrue(self.screen.name_button.instate(["!disabled"]))
        with mock.patch.object(self.screen, "_ask_text", return_value="Tempo Truffle"):
            self.screen.name_button.invoke()
        self.assertEqual(self.screen.card_name_var.get(), "TEMPO TRUFFLE")
        self.assertEqual(json.loads(self.names_file.read_text(encoding="utf-8")), {"SW.Item.Artifact.HasteMushroom": "Tempo Truffle"})
        self.assertIn("SW.Item.Artifact.HasteMushroom - Tempo Truffle [kept by the game]", share_ids.report_text([self.screen.hero], "9"))


def size_of(window):
    """(width, height) a window has been given."""
    return tuple(int(side) for side in window.geometry().split("+")[0].split("x"))


@unittest.skipUnless(_tk_available(), "needs a display")
class RestoreTests(WindowTestCase):
    """Restore a backup…: the way back from any change."""

    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), HERO: hero_save_text().encode()}

    def save_with_emeralds(self, emeralds):
        screen = self.app.inventory
        screen.stat_vars["Emeralds"].set(str(emeralds))
        self.assertTrue(screen.commit_pending())
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask, mock.patch("tkinter.messagebox.showinfo"):
            self.app.save_to_game()
        self.assertNotIn("checked against", ask.call_args.args[1])  # a save format the editor knows: no caution
        self.assertEqual(self.emeralds_saved(), emeralds)

    def emeralds_saved(self):
        return saves.SaveProfile(self.profile_path).get(HERO).hero.attribute("Emeralds")

    def open_restore(self):
        self.app._restore_dialog()
        self.root.update()
        return next(w for w in self.root.winfo_children() if isinstance(w, RestoreDialog))

    def test_restore_puts_back_the_save_from_before(self):
        self.assertEqual([bool(self.app.share_button.winfo_manager()), bool(self.app.share_button_advanced.winfo_manager())], [False, False])  # nothing new in these saves
        self.save_with_emeralds(777)
        dialog = self.open_restore()
        self.assertEqual(dialog.selected().reason, "Before saving Offline hero (Ranger Deluxe)")  # the newest is picked
        with mock.patch("tkinter.messagebox.askyesno", return_value=False):
            dialog.restore_button.invoke()
        self.assertTrue(dialog.winfo_exists())  # said no: nothing happens
        self.assertEqual(self.emeralds_saved(), 777)
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask, mock.patch("tkinter.messagebox.showinfo") as told:
            dialog.restore_button.invoke()
        self.assertIn("Put back the save data from", ask.call_args.args[1])
        self.assertEqual(told.call_args.args[1], "Restored: Offline hero (Ranger Deluxe)")
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(self.emeralds_saved(), 55)
        self.assertEqual(self.app.inventory.stat_vars["Emeralds"].get(), "55")
        self.assertEqual(self.app.status_var.get(), "Restored Offline hero (Ranger Deluxe)")
        # Restoring backs up first, so it can be undone the same way.
        self.assertTrue(saves.list_backups(self.dir / "backups")[0].reason.startswith("Before restoring backup from"))

    def test_double_clicking_a_backup_restores_it(self):
        self.save_with_emeralds(777)
        dialog = self.open_restore()
        self.show_on_screen(dialog)
        row = dialog.listing.get_children()[0]
        left, top, _width, height = dialog.listing.bbox(row)

        def double_click(y):
            for event in ("<ButtonPress-1>", "<ButtonRelease-1>") * 2:
                dialog.listing.event_generate(event, x=left + 5, y=y)
            dialog.update()

        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            double_click(1)  # on the headings: not a backup
            ask.assert_not_called()
            double_click(top + height // 2)
            ask.assert_called_once()
        with mock.patch("tkinter.messagebox.askyesno", return_value=True), mock.patch("tkinter.messagebox.showinfo"):
            dialog.listing.focus_force()  # a key goes to whatever has the keyboard, and a test's window may not
            dialog.update()
            dialog.listing.event_generate("<Return>")
            dialog.update()
        self.assertEqual(self.emeralds_saved(), 55)

    def test_the_buttons_keep_their_room_in_a_window_too_small_for_the_list(self):
        for _ in range(3):
            saves.make_backup(self.profile_path, self.dir / "backups")
        dialog = self.open_restore()
        self.show_on_screen(dialog)
        self.assert_in_view(dialog.restore_button, dialog)
        dialog.minsize(1, 1)
        dialog.geometry(f"{dialog.winfo_width()}x{dialog.restore_button.winfo_height() * 4}")  # far less than the list asks for
        dialog.update()
        self.assert_in_view(dialog.restore_button, dialog)

    def test_says_so_when_theres_nothing_to_put_back(self):
        with mock.patch("tkinter.messagebox.showinfo") as told:
            self.app._restore_dialog()
        self.assertEqual(told.call_args.args[1], "There are no backups of this save profile yet.")
        saves.make_backup(self.profile_path, self.dir / "backups")
        dialog = self.open_restore()
        with mock.patch("tkinter.messagebox.askyesno", return_value=True), mock.patch("tkinter.messagebox.showinfo") as told:
            dialog.restore()
        self.assertEqual(told.call_args.args[1], "Nothing to restore: that backup matches your current save data.")
        self.assertFalse(dialog.winfo_exists())

    def test_says_which_save_couldnt_be_put_back(self):
        self.save_with_emeralds(777)
        index = wgs.read_index(self.profile_path)  # then the hero is deleted in the game
        entries = [dataclasses.replace(entry, sync_state=wgs.DELETED) if entry.name == HERO else entry for entry in index.entries]
        (self.profile_path / wgs.INDEX_FILE).write_bytes(wgs.serialize_index(dataclasses.replace(index, entries=entries)))
        dialog = self.open_restore()
        with mock.patch("tkinter.messagebox.askyesno", return_value=True), mock.patch("tkinter.messagebox.showwarning") as warned:
            dialog.restore()
        message = warned.call_args.args[1]
        self.assertIn("Nothing was put back.", message)
        self.assertIn("• Offline hero (Ranger Deluxe) has been deleted in the game.", message)
        self.assertIn("can only put a save back over one that's still in your save folder", message)

    def test_the_game_has_to_be_closed(self):
        self.save_with_emeralds(777)
        dialog = self.open_restore()
        with mock.patch.object(saves, "running_game_processes", return_value=["Dungeons.exe"]), mock.patch(
            "tkinter.messagebox.askyesno", return_value=True
        ), mock.patch("tkinter.messagebox.showwarning") as warned:
            dialog.restore()
        self.assertIn("Minecraft Dungeons II is running", warned.call_args.args[1])
        self.assertTrue(dialog.winfo_exists())  # still there, to try again once the game is closed
        self.assertEqual(self.emeralds_saved(), 777)


@unittest.skipUnless(_tk_available(), "needs a display")
class ScaledDisplayTests(RestoreTests):
    """The same on a display that Windows scales up to 150%, where text and buttons are half as big again.
    The Restore window used to open at a fixed size there, with no room left for its Restore button."""

    scaling = 2.0

    def test_windows_are_as_big_as_the_scaling_needs(self):
        self.assertEqual(size_of(self.root), layout.scaled_size(self.root, *gui.START_SIZE))
        least = layout.scaled_size(self.root, *gui.MIN_SIZE)  # Simple mode may need more than that
        self.assertTrue(all(got >= wanted for got, wanted in zip(self.root.minsize(), least)), (self.root.minsize(), least))
        saves.make_backup(self.profile_path, self.dir / "backups")
        dialog = self.open_restore()
        self.show_on_screen(dialog)
        needed = (dialog.winfo_reqwidth(), dialog.winfo_reqheight())
        room = layout.screen_room(dialog)
        self.assertEqual((dialog.winfo_width(), dialog.winfo_height()), (min(needed[0], room[0]), min(needed[1], room[1])))
        self.assertGreater(needed[1], 380)  # the height the window used to have, whatever the scaling


def geared_hero_save():
    """A hero with a Special bow the game rolled two effects for, an enchanted helmet, and a horn."""
    document = hero_save()
    bow = hero_item("SW.Item.Bow", power=17, rarity="Special", seed=71, unseen=False)
    bow["ItemData"]["Effects"] = [rolled(rolled_effect("Knockback", 0.15), rolled_effect("CriticalEdge", 0.2, "II"))]
    helmet = hero_item("SW.Item.HoneyHelmet", power=14, rarity="Unique", seed=72, unseen=False)
    helmet["ItemData"]["Effects"] = [
        {"TypeTag": "SW.Item.Effect.Fixed", "EffectsInThisBatch": [rolled_effect("Burning", 1, "Unique")]},
        enchanted(enchantment_effect("SoulInfusedPotion", 0.6, "II", points=8)),
    ]
    document["CharacterSaveV1"]["Inventory"]["Entries"] += [bow, helmet, hero_item("SW.Item.Artifact.RallyingHorn", seed=73, unseen=False)]
    return json.dumps(document, separators=(",", ":")).encode()


@unittest.skipUnless(_tk_available(), "needs a display")
class EffectsWindowTests(WindowTestCase):
    """The window that changes an item's effects and its enchantment."""

    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), HERO: geared_hero_save()}

    def open(self, tag, **more):
        hero = self.app.inventory.hero
        item = next(item for item in hero.items() if item.tag == tag)
        dialog = EffectsDialog(self.root, item, *effect_choices([hero]), **more)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        self.root.update()
        return dialog

    def on_item(self, dialog):
        return [(dialog.current.item(iid, "text"), dialog.current.set(iid, "kind")) for iid in dialog.current.get_children()]

    def listed(self, dialog):
        return [dialog.listing.item(iid, "text") for iid in dialog.listing.get_children()]

    def test_effects_are_added_changed_and_removed(self):
        dialog = self.open("SW.Item.Bow")
        self.assertEqual(self.on_item(dialog), [("Knockback I", "Effect"), ("Critical Edge II", "Effect")])
        self.assertEqual(dialog.count_var.get(), "2 of 4 effects")
        self.assertTrue(dialog.apply_button.instate(["disabled"]))  # nothing to apply yet
        self.assertIn("Lightning Focus (Electromancer?)", self.listed(dialog))  # a name made from the ID, and the likely one
        # One it has already: the tier it has is the one picked, and there's nothing to add.
        self.assertTrue(dialog.select("Critical Edge"))
        self.assertEqual((dialog.tier_var.get(), str(dialog.add_button.cget("text")), dialog.add_button.instate(["disabled"])), ("II", "On the item", True))
        # Another tier of it takes its place.
        dialog.tier_var.set("I")
        dialog._show_choice()
        self.assertEqual(str(dialog.add_button.cget("text")), "Change to tier I")
        dialog.add()
        self.assertEqual(self.on_item(dialog), [("Knockback I", "Effect"), ("Critical Edge I", "Effect")])
        self.assertTrue(dialog.apply_button.instate(["!disabled"]))
        # A new one starts at the best tier a save has shown, and is added at the end.
        self.assertTrue(dialog.select("Looter"))
        self.assertEqual((dialog.tier_var.get(), str(dialog.add_button.cget("text"))), ("I", "Add this effect"))
        self.assertEqual(dialog.note_var.get(), "Looter I: Grants a 20% chance to get additional loot drops.")
        dialog.add()
        self.assertTrue(dialog.select("Luck"))
        dialog.add()
        self.assertEqual(dialog.count_var.get(), "4 of 4 effects")
        # Full: a fifth has to wait until one is removed.
        self.assertTrue(dialog.select("Vanguard"))
        self.assertTrue(dialog.add_button.instate(["disabled"]))
        self.assertIn("The game caps an item at 4 effects, so remove one first.", dialog.note_var.get())
        dialog.add()
        self.assertEqual(len(dialog.effects), 4)
        dialog.current.selection_set("effect 0")
        self.root.update()
        dialog.remove()
        self.assertEqual([choice.title for choice in dialog.effects], ["Critical Edge I", "Looter I", "Luck I"])
        self.assertTrue(dialog.add_button.instate(["!disabled"]))
        # Searching narrows the list.
        dialog.search_var.set("any weapon")
        self.assertEqual(self.listed(dialog), ["Critical Edge", "Critical Hit", "Knockback"])
        dialog.search_var.set("nothing like this")
        self.assertEqual((self.listed(dialog), dialog.note_var.get()), ([], "Nothing matches. Try another search."))
        dialog.search_var.set("")
        dialog.apply()
        self.assertEqual(([choice.title for choice in dialog.result[0]], dialog.result[1]), (["Critical Edge I", "Looter I", "Luck I"], None))
        self.assertFalse(dialog.winfo_exists())

    def test_a_tier_no_save_has_shown_is_asked_about_once(self):
        dialog = self.open("SW.Item.Bow")
        self.assertFalse(dialog.select("Critical Edge", "III"))  # not on offer: the game files' two numbers for it disagree
        self.assertTrue(dialog.select("Vanguard", "III"))
        self.assertIn("Deal 50% more damage to enemies who are at full health. This tier hasn't been seen in a real save yet", dialog.note_var.get())
        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            dialog.add()
        self.assertEqual((ask.call_count, [choice.title for choice in dialog.effects]), (1, ["Knockback I", "Critical Edge II"]))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            dialog.add()
            dialog.select("Knockback", "III")
            dialog.add()
        self.assertEqual((ask.call_count, [choice.title for choice in dialog.effects]), (1, ["Knockback III", "Critical Edge II", "Vanguard III"]))

    def test_an_enchantment_goes_only_where_the_game_puts_it(self):
        dialog = self.open("SW.Item.Bow", enchantsmith_opened=False)
        dialog.kind_var.set("Enchantments")
        dialog._fill_choices()
        self.assertEqual(self.listed(dialog), ["Healing Smite", "Piercing"])  # the ones for a ranged weapon
        self.assertTrue(dialog.select("Piercing"))
        self.assertEqual(str(dialog.add_button.cget("text")), "Enchant with it")
        self.assertEqual(
            dialog.note_var.get(),
            "Projectiles pierce enemies. Tiers I, II and III: 1 / 3 / 5 enemies. This hero hasn't opened the Enchantsmith in the game yet.",
        )
        dialog.add()
        self.assertEqual(self.on_item(dialog)[-1], ("Piercing I", "Enchantment"))
        dialog.select("Healing Smite")
        self.assertEqual(str(dialog.add_button.cget("text")), "Change to Healing Smite I")  # one enchantment an item
        dialog.add()
        self.assertEqual((dialog.enchantment.title, len(dialog.effects)), ("Healing Smite I", 2))
        dialog.current.selection_set("enchantment")
        self.root.update()
        dialog.remove()
        self.assertIsNone(dialog.enchantment)
        dialog.remove_all()
        self.assertEqual((self.on_item(dialog), dialog.clear_button.instate(["disabled"])), ([], True))
        dialog.destroy()
        self.assertIsNone(dialog.result)
        # An artifact takes effects and no enchantment.
        horn = self.open("SW.Item.Artifact.RallyingHorn")
        self.assertTrue(horn.kind_buttons["Enchantments"].instate(["disabled"]))
        self.assertEqual(horn.choices["Enchantments"], [])

    def test_an_effect_of_the_items_own_is_left_alone(self):
        dialog = self.open("SW.Item.HoneyHelmet")
        self.assertEqual(self.on_item(dialog), [("Ancient Alchemy II", "Enchantment"), ("Burning", "Its own")])
        self.assertEqual(dialog.count_var.get(), "0 of 3 effects")  # its own one counts towards the game's four
        dialog.current.selection_set("own 0")
        self.root.update()
        self.assertTrue(dialog.remove_button.instate(["disabled"]))
        dialog.remove()
        self.assertEqual(len(self.on_item(dialog)), 2)
        self.assertEqual(dialog.kind_var.get(), "Effects")
        dialog.kind_var.set("Enchantments")
        dialog._fill_choices()
        self.assertEqual(self.listed(dialog), ["Ancient Alchemy"])  # the one enchantment known for armor
        self.assertEqual((dialog.tier_var.get(), str(dialog.add_button.cget("text"))), ("II", "On the item"))

    def test_best_for_puts_the_editors_picks_on_the_item(self):
        dialog = self.open("SW.Item.Bow")
        self.assertEqual(list(dialog.goal_box.cget("values")), ["Damage", "Survival", "Mobility", "Loot", "Artifacts and souls", "Companions", "XP"])
        self.assertIn("out of the ones the game can roll on this very item", dialog.best_var.get())
        # The picks go first, each at the best tier a save has shown, and what the item had stays while it fits.
        self.assertTrue(dialog.best_for("Loot"))
        self.assertEqual([choice.title for choice in dialog.effects], ["Looter I", "Luck I", "Knockback I", "Critical Edge II"])
        self.assertEqual((dialog.goal_var.get(), dialog.count_var.get()), ("Loot", "4 of 4 effects"))
        self.assertTrue(
            dialog.best_var.get().startswith(
                "Best for loot on the Bow (a ranged weapon with no archetype): Looter I and Luck I. Kept Knockback I and "
                "Critical Edge II. In the editor's order: more drops first"
            ),
            dialog.best_var.get(),
        )
        self.assertTrue(dialog.apply_button.instate(["!disabled"]))
        # Another goal's picks go ahead of those. Critical Edge was on it already, and what no longer fits comes off.
        self.assertTrue(dialog.best_for("Damage"))
        self.assertEqual([choice.title for choice in dialog.effects], ["Critical Hit I", "Critical Edge II", "Looter I", "Luck I"])
        self.assertIn("Critical Hit I and Critical Edge II. Kept Looter I and Luck I. Took off Knockback I.", dialog.best_var.get())
        # What the game doesn't roll on this item isn't picked: the window says where it does roll it.
        before = list(dialog.effects)
        self.assertFalse(dialog.best_for("Mobility"))
        self.assertEqual(
            dialog.best_var.get(),
            "The game rolls no effect for mobility on the Bow (a ranged weapon with no archetype). It rolls them on Trickster gear. "
            "You can still add one from the list by hand.",
        )
        self.assertFalse(dialog.best_for("XP"))
        self.assertIn("No effect on gear gives XP. The Eye of Experience talisman does", dialog.best_var.get())
        self.assertFalse(dialog.best_for("Fishing"))
        self.assertEqual(dialog.effects, before)
        # One picked by hand that the game wouldn't roll here can still be added, and the window says which it is.
        self.assertTrue(dialog.select("Vanguard"))
        self.assertIn("In the game it rolls on fighter gear, which the Bow isn't.", dialog.note_var.get())
        self.assertTrue(dialog.select("Looter"))
        self.assertNotIn("In the game it rolls on", dialog.note_var.get())
        # Choosing a goal in the list does the same as the call.
        dialog.remove_all()
        dialog.goal_box.set("Loot")
        dialog.goal_box.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual([choice.title for choice in dialog.effects], ["Looter I", "Luck I"])
        dialog.apply()
        self.assertEqual(([choice.title for choice in dialog.result[0]], dialog.result[1]), (["Looter I", "Luck I"], None))

    def test_best_for_knows_the_item_and_leaves_its_own_effect_alone(self):
        dialog = self.open("SW.Item.HoneyHelmet", elements={"Fire", ""})
        self.assertEqual(dialog.elements, {"Fire"})  # the elements of the artifacts the hero has equipped
        self.assertTrue(dialog.best_for("Loot"))
        self.assertEqual(
            self.on_item(dialog), [("Looter I", "Effect"), ("Luck I", "Effect"), ("Ancient Alchemy II", "Enchantment"), ("Burning", "Its own")]
        )
        self.assertEqual(dialog.count_var.get(), "2 of 3 effects")
        self.assertIn("on the Beekeeper Veil (Support gear)", dialog.best_var.get())
        self.assertFalse(dialog.best_for("Damage"))  # nothing in the list for damage rolls on Support gear
        horn = self.open("SW.Item.Artifact.RallyingHorn")
        self.assertTrue(horn.best_for("Artifacts and souls"))
        self.assertEqual([choice.title for choice in horn.effects], ["Cooldown II", "Spiritual I"])
        self.assertIn("(Summoner, Support and Tank gear)", horn.best_var.get())

    def test_the_buttons_keep_their_room(self):
        dialog = self.open("SW.Item.Bow")
        self.show_on_screen(dialog)
        for button in (dialog.apply_button, dialog.add_button, dialog.remove_button, dialog.goal_box):
            self.assert_in_view(button, dialog)
        dialog.select("Vanguard", "III")  # the longest note there is
        dialog.best_for("Damage")  # and the most "Best for" has to say
        dialog.update()
        for button in (dialog.apply_button, dialog.add_button, dialog.goal_box):
            self.assert_in_view(button, dialog)


class EffectsWindowAt150Tests(EffectsWindowTests):
    """The same on a display scaled up to 150%."""

    scaling = 2.0


class EffectsWindowAt200Tests(EffectsWindowTests):
    scaling = 2.6667


class EffectsWindowInLiquidGlassTests(EffectsWindowAt200Tests):
    """And in the other look, whose buttons and boxes are pictures drawn for the display's scaling."""

    look = "glass"


@unittest.skipUnless(_tk_available(), "needs a display")
class LiquidGlassTests(SimpleModeTests):
    """Simple mode in the Liquid Glass look: everything the original look does, it does the same."""

    look = "glass"
    test_the_look_is_switched_from_the_menu_and_remembered = None  # these three start from a hero whose look is unset
    test_a_look_the_editor_doesnt_know_is_the_original = None
    test_a_look_can_be_asked_for_just_this_once = None

    def test_it_opens_in_the_look_that_was_chosen(self):
        self.assertEqual((self.app.look, self.app.look_var.get(), self.screen.glass, self.app.art.rounded), ("glass", "glass", True, True))
        self.assertTrue(game_style.is_glass(self.root))
        self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8")), {"advanced": False, "look": "glass"})  # opening changes no setting


def newer_hero_save():
    """A hero as a later version of the game might save it, who has found a Unique the editor's list hasn't seen."""
    document = hero_save()
    document["SerializeMeta"]["SoftVersion"] = 6
    document["CharacterSaveV1"]["CollectionsStats"]["CollectedWeaponsUnique"] = ["SW.Item.Mace_Unique1"]
    return json.dumps(document, separators=(",", ":")).encode()


@unittest.skipUnless(_tk_available(), "needs a display")
class WorldMapTests(WindowTestCase):
    """Menu > World map: the ground a hero has explored, drawn from its save, and how far it has got."""

    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), HERO: json.dumps(hero_with_a_world(), separators=(",", ":")).encode()}

    def open_map(self, atlas=None):
        with mock.patch.object(recorder, "fresh_atlas", return_value=atlas) as fresh, mock.patch.object(recorder, "DEFAULT_OUT", self.dir / "recordings"):
            self.app.app_menu.invoke(self.app.app_menu.index("World map…"))
        fresh.assert_called_once_with(self.dir / "recordings")  # what the recordings have shown, up to the newest
        return self.app.world_map

    def test_draws_the_ground_explored_with_what_was_found_on_it(self):
        before = snapshot_of(self.profile_path)
        dialog = self.open_map(recordings_of_a_world())
        self.assertEqual(dialog.title(), "World map: Ranger Deluxe")
        self.assertEqual(list(dialog.region_box.cget("values")), ["Camp", "Meadow.R1"])  # the biggest region first
        self.assertEqual(dialog.heading_var.get(), "Camp: 4 of 12 squares explored. One square is 32 metres across.")
        # Four squares the fog has lifted from, the six unseen ones next to them, two doors, and from the
        # recordings a station and the chests opened where it turned up.
        self.assertEqual([dialog.shown(kind) for kind in ("explored", "edge", "door", "found", "chest", "name")], [4, 6, 2, 1, 1, 0])
        colours = {dialog.canvas.itemcget(item, "fill") for item in dialog.canvas.find_withtag("explored")}
        self.assertIn(recorder.clarity_colour(255), colours)
        self.assertEqual(len(colours), 4)  # the clearer the fog, the greener
        # The docks' door is on the square that's all clear: the third along the middle line.
        size = dialog._size
        (clear,) = [item for item in dialog.canvas.find_withtag("explored") if dialog.canvas.itemcget(item, "fill") == recorder.clarity_colour(255)]
        left, top, right, bottom = dialog.canvas.coords(clear)
        self.assertEqual((left, top), (2 * size, 1 * size))
        docks = dialog.canvas.find_withtag("door")[0]
        x0, y0, x1, y1 = dialog.canvas.coords(docks)
        self.assertTrue(left < (x0 + x1) / 2 < right and top < (y0 + y1) / 2 < bottom)
        # The station and the chests turned up at one spot: side by side, not one on top of the other.
        found, chest = dialog.canvas.coords(dialog.canvas.find_withtag("found")[0]), dialog.canvas.coords(dialog.canvas.find_withtag("chest")[0])
        self.assertGreaterEqual(chest[0], found[2])
        # Names on: each dot gets its name, in the game's words where they're known.
        dialog.names_box.invoke()
        named = {dialog.canvas.itemcget(item, "text") for item in dialog.canvas.find_withtag("name")}
        self.assertEqual(named, {"Camp.Docks", "ForestA1.Dungeon.1", "Little Howl Hamlet", "2 chests"})
        dialog.names_box.invoke()
        self.assertEqual(dialog.shown("name"), 0)
        # Closer in and back out, never smaller than the whole region.
        self.assertTrue(dialog.out_button.instate(["disabled"]))
        dialog.in_button.invoke()
        self.assertGreater(dialog._size, size)
        self.assertTrue(dialog.out_button.instate(["!disabled"]))
        dialog.zoom_by(100)
        self.assertTrue(dialog.in_button.instate(["disabled"]))
        dialog.zoom_by(0.001)
        self.assertEqual((dialog.zoom, dialog._size), (1.0, size))
        # The wheel zooms when the pointer is over the map, and not when it's over the list beside it.
        over_map = (dialog.canvas.winfo_rootx() + 40, dialog.canvas.winfo_rooty() + 40)
        with mock.patch.object(dialog, "winfo_pointerx", return_value=over_map[0]), mock.patch.object(dialog, "winfo_pointery", return_value=over_map[1]):
            dialog._wheel(world_dialog.ZOOM_STEP)
        self.assertGreater(dialog.zoom, 1.0)
        with mock.patch.object(dialog, "winfo_pointerx", return_value=over_map[0] - 5000), mock.patch.object(dialog, "winfo_pointery", return_value=over_map[1]):
            dialog._wheel(1 / world_dialog.ZOOM_STEP)
        self.assertGreater(dialog.zoom, 1.0)
        dialog.zoom_by(0.001)
        # Another region.
        dialog.region_var.set("Meadow.R1")
        dialog.region_box.event_generate("<<ComboboxSelected>>")
        self.assertEqual(dialog.heading_var.get(), "Meadow.R1: 1 of 4 squares explored. One square is 32 metres across.")
        self.assertEqual([dialog.shown(kind) for kind in ("explored", "edge", "door", "found", "chest")], [1, 2, 1, 0, 0])
        # The list beside it, and a copy of it for the clipboard.
        shown = dialog.shown_text()
        for line in ("Area: Howling Woods", "Story quests done: 1 of 3", "Carapace Side Quest", "Howling Woods: 1 of its 12 dungeon spots found",
                     "CA04 (The Missing Note Blocks): active, 1 of 2 steps done", "Little Howl Hamlet  (ForestA1.Outpost)", "Howling Woods: 2", "3 saves of this hero read"):
            self.assertIn(line, shown)
        dialog.copy_button.invoke()
        copied = self.root.clipboard_get()
        self.assertTrue(copied.startswith("Where the hero is\n  Area: Howling Woods\n"))
        self.assertIn("\n\nThe story, by the game's achievements for it\n  ✓  Arrive In Brave Haven\n", copied)
        self.assertIn("Copied", dialog.hover_var.get())
        # Looking changes nothing: not the hero on screen, not the save folder.
        self.assertEqual((self.app.change_count, snapshot_of(self.profile_path)), (0, before))
        # One map at a time: opening it again draws it afresh.
        again = self.open_map()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual([again.shown(kind) for kind in ("door", "found", "chest")], [2, 0, 0])  # no recordings: the save's own doors
        self.assertIn("Nothing yet for this hero.", again.shown_text())
        again.destroy()
        self.assertIsNone(again._redraw)

    def test_sharing_tells_of_the_world_unless_you_untick_it(self):
        from dungeons2_editor import world

        # Everything this hero has found that the editor's list of the world lacks counts as news, like an item ID.
        self.assertEqual(self.app.share_button.cget("text"), "SHARE ITEM IDS · 13 NEW")
        places = {"chests": [{"opened": 2, "count": 4, "area": "SW.Area.Forest.A1", "near": [48, 48], "region": "SW.Region.Camp"}], "locations": [], "found_at": {}}
        with mock.patch.object(recorder, "fresh_atlas", return_value=places) as fresh:
            self.app.share_button.invoke()
        fresh.assert_called_once_with(self.dir / "recordings")
        self.root.update()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, share_ids.ShareIdsDialog))
        told = dialog.report().splitlines()
        self.assertEqual(told[:2], [world.SAVES_HEADER, "quest CA04 - Active; steps: E01+, E02~"])
        self.assertEqual(told[-3:], [world.PLACES_HEADER, "chest - 2 opened in SW.Area.Forest.A1, around 48, 48 in SW.Region.Camp", "chests - 2 opened in SW.Area.Forest.A1"])
        self.assertTrue(dialog.world_box.winfo_manager() and dialog.world_var.get())
        self.assertTrue(dialog.issue_button.instate(["!disabled"]))
        # Unticked, the world's part goes, and with nothing else to tell there's nothing to send.
        dialog.world_box.invoke()
        self.assertEqual(dialog.report(), "")
        self.assertTrue(dialog.issue_button.instate(["disabled"]) and dialog.copy_button.instate(["disabled"]))
        # Ticked again it's back, under whatever was typed above it meanwhile.
        dialog.text.insert("1.0", "SW.Item.Mine - a line I typed")
        dialog.world_box.invoke()
        self.assertEqual(dialog.report().splitlines()[:3], ["SW.Item.Mine - a line I typed", "", world.SAVES_HEADER])
        self.assertEqual(dialog.report().splitlines()[2:], told)
        dialog.world_box.invoke()
        self.assertEqual(dialog.report(), "SW.Item.Mine - a line I typed")
        dialog.world_box.invoke()
        with mock.patch("webbrowser.open") as browser:
            dialog.open_issue()
        self.assertIn("door SW.Doorway.ForestA1.Dungeon.1 - at 16, 16, 0; marker 8", urllib.parse.unquote_plus(browser.call_args.args[0]))
        dialog.destroy()
        # Shown once, it isn't news the next time, and the button goes away.
        self.assertFalse(self.app.share_button.winfo_manager())
        self.assertIn("world quest CA04", json.loads(self.settings_file.read_text(encoding="utf-8"))["shared"])
        # A hero whose saves hold nothing new has no box to untick; recordings that can't be read don't stop the list.
        self.app.profile.get(HERO).decoded.document.update(hero_save())
        with mock.patch.object(recorder, "fresh_atlas", side_effect=OSError("no such folder")):
            self.app._share_ids()
        plain = [w for w in self.root.winfo_children() if isinstance(w, share_ids.ShareIdsDialog)][-1]
        self.assertEqual((plain.report(), plain.world_box.winfo_manager(), self.root.cget("cursor")), ("", "", ""))
        plain.destroy()

    def test_the_recorders_window_shows_it_and_a_save_with_no_map_says_so(self):
        out = self.dir / "recordings"
        with mock.patch.object(recorder, "DEFAULT_OUT", out):
            window = self.app.open_recorder()
            self.assertEqual(window.map_button.cget("text"), "Show the map")
            window.map_button.invoke()  # reads the recordings (there are none yet), writes the atlas, opens the map
        self.assertTrue(self.app.world_map.winfo_exists())
        self.assertEqual(self.app.world_map.shown("door"), 2)
        window.close()
        self.app.world_map.destroy()
        # A hero that has been nowhere: no picture to draw, and the list all the same.
        nowhere = gui.WorldDialog(self.root, hero_save())
        self.assertEqual((nowhere.region_var.get(), nowhere.heading_var.get(), nowhere.shown("explored")), ("", "", 0))
        self.assertEqual(nowhere.canvas.itemcget(nowhere.canvas.find_all()[0], "text"), "This save has no map yet: the game draws one as the hero explores.")
        self.assertIn("Area: Brave Haven", nowhere.shown_text())
        nowhere.zoom_by(2)  # nothing to zoom
        nowhere.destroy()
        # Recordings that can't be read don't stop the map: it's the save's own.
        with mock.patch.object(recorder, "fresh_atlas", side_effect=ValueError("a recording nobody can read")):
            self.assertEqual(self.app.open_world_map().shown("door"), 2)
        self.assertEqual(self.root.cget("cursor"), "")
        # With something other than a hero on screen there's no map to draw.
        self.app.original = None
        with mock.patch("tkinter.messagebox.showinfo") as told:
            self.assertIsNone(self.app.open_world_map())
        self.assertIn("Pick a hero first", told.call_args.args[1])


class WorldMapInLiquidGlassTests(WorldMapTests):
    look = "glass"


@unittest.skipUnless(_tk_available(), "needs a display")
class NewsFromTheSavesTests(WindowTestCase):
    """What the editor points out about a save: something to share, and a save format it hasn't been checked against."""

    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), HERO: newer_hero_save()}

    def shown(self):
        return [bool(button.winfo_manager()) for button in (self.app.share_button, self.app.share_button_advanced)]

    def test_a_note_when_the_saves_hold_something_to_share(self):
        self.assertEqual(self.shown(), [True, True])
        self.assertEqual((self.app.share_button.cget("text"), self.app.share_button_advanced.cget("text")),
                         ("SHARE ITEM IDS · 1 NEW", "Share item IDs (1 new)…"))
        self.app.share_button.invoke()
        self.root.update()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, share_ids.ShareIdsDialog))
        self.assertIn("SW.Item.Mace_Unique1 - Carapace Mace (the Unique Mace): confirms the editor's guess [in the collections]", dialog.report())
        dialog.destroy()
        # You've been shown it, so the note goes away, and stays away the next time the saves are opened.
        self.assertEqual(self.shown(), [False, False])
        self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8"))["shared"], ["SW.Item.Mace_Unique1"])
        self.app.reload()
        self.root.update()
        self.assertEqual(self.shown(), [False, False])
        # Until the saves hold something else.
        self.app.profile.get(HERO).decoded.document["CharacterSaveV1"]["CollectionsStats"]["CollectedWeaponsCommon"].append("SW.Item.SomethingNew")
        self.app._update_share_note()
        self.assertEqual((self.shown(), self.app.share_button.cget("text")), ([True, True], "SHARE ITEM IDS · 1 NEW"))

    def test_a_caution_before_saving_a_format_the_editor_wasnt_checked_against(self):
        self.app.inventory.stat_vars["Emeralds"].set("60")
        self.assertTrue(self.app.inventory.commit_pending())
        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            self.app.save_to_game()
        question = ask.call_args.args[1]
        self.assertIn("Emeralds: 55 → 60", question)
        self.assertIn("a format the editor hasn't been checked against (FCharacterSaveV1, version 6)", question)


@unittest.skipUnless(_tk_available(), "needs a display")
class HeroChoiceTests(WindowTestCase):
    containers = {HERO: hero_save_text().encode(), OTHER_HERO: hero_save_text(emeralds=999, level=7).encode()}

    def test_pick_another_hero_in_the_top_bar(self):
        menu = self.app.hero_menu
        heroes = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "radiobutton"]
        self.assertEqual(len(heroes), 2)
        other = next(c for c in self.app._containers_by_iid.values() if c.name != self.app.container.name)
        self.app.inventory.stat_vars["Emeralds"].set("123")
        self.assertTrue(self.app.inventory._apply_stat("Emeralds"))
        with mock.patch("tkinter.messagebox.askyesno", return_value=False):
            self.app._choose_hero(other)  # keep the unsaved change
        self.assertNotEqual(self.app.container.name, other.name)
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            self.app._choose_hero(other)
        self.assertEqual(self.app.container.name, other.name)
        self.assertEqual(self.app.hero_menu_var.get(), other.name)
        self.assertTrue(self.app.hero_choice_var.get().endswith(f"LV {other.hero.level}"))


@unittest.skipUnless(_tk_available(), "needs a display")
class OnlineHeroTests(WindowTestCase):
    containers = {HERO: hero_save_text(online=True).encode()}

    def test_online_heroes_say_why_they_cant_be_changed(self):
        self.assertIsNone(self.app.container)
        self.assertEqual(self.app.title_var.get(), "No offline heroes yet")
        self.assertTrue(self.app.inventory.empty.winfo_manager())
        online = next(iter(self.app._containers_by_iid.values()))
        self.app._choose_hero(online)
        self.assertIn("servers", self.app.empty_text_var.get())
        self.assertTrue(self.app.inventory.empty.winfo_manager())


if __name__ == "__main__":
    unittest.main()
