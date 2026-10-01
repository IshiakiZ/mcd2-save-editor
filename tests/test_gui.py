import copy
import gc
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest import mock

from dungeons2_editor import game_style, gui, saves, share_ids
from dungeons2_editor.hero import Hero, use_local_names
from dungeons2_editor.item_picker import ItemPicker

from .helpers import SETTINGS_TEXT, hero_save_text, make_profile, shift_encode

HERO = "Character00000000-0000-1000-8000-000000000002"
OTHER_HERO = "Character00000000-0000-1000-8000-000000000003"


def _tk_available() -> bool:
    try:
        tk.Tk().destroy()
    except tk.TclError:
        return False
    return True


class WindowTestCase(unittest.TestCase):
    """Opens the editor on a temporary save folder, in Simple or Advanced mode."""

    containers: dict = {}
    advanced = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.profile_path = make_profile(self.dir / "saves", self.containers)
        self.settings_file = self.dir / "settings.json"
        self.settings_file.write_text(json.dumps({"advanced": self.advanced}), encoding="utf-8")
        patcher = mock.patch.object(saves, "running_game_processes", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(gc.collect)  # frees Tk objects on the main thread, after the window is destroyed
        self.addCleanup(self.root.destroy)
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
        self.assertEqual(self.rows(), ["Longbow", "Mystic Circlet", "Curved Greatsword", "Sword"])
        images = {self.tab.tree.item(i, "text").strip(): self.tab.tree.item(i, "image") for i in self.tab.tree.get_children()}
        self.assertTrue(all(images.values()))
        self.select_item("Mystic Circlet")
        self.assertEqual(self.tab.preview_source_var.get(), "Picture: minecraft.wiki")

    def test_sorting_and_filters(self):
        self.tab.sort_var.set("Name")
        self.tab._fill_items()
        self.assertEqual(self.rows(), ["Curved Greatsword", "Longbow", "Mystic Circlet", "Sword"])
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
        self.select_item("Curved Greatsword")
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            self.tab.delete_item()
        summary = self.save()
        self.assertIn("Mystic Circlet: Common → Unique, power 1 → 50", summary)
        self.assertIn("Added Longbow (Rare, power 2)", summary)
        self.assertIn("Removed Curved Greatsword", summary)
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
        self.select_item("Curved Greatsword")  # merchant stock
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
        axe = next(item for item in self.saved_hero().items() if item.tag == "SW.Item.Axe")
        self.assertEqual((axe.rarity, axe.power, axe.count, axe.where), ("Unique", 40, 2, "Inventory"))

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
        picker, row = self.open_picker_on("Claymore")
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
        claymores = [item for item in self.app.hero_tab.hero.items() if item.tag == "SW.Item.Claymore"]
        self.assertEqual(len(claymores), 2)

    def test_uniques_are_their_base_item_at_unique_rarity(self):
        picker, _row = self.open_picker_on("Battle Hammer")
        picker.rarity_var.set("Unique")
        picker._show_selected()
        self.assertEqual(picker.name_var.get(), "Emerald Hammer")
        self.assertIn("Unique Battle Hammer", picker.unique_text.get())
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            picker._confirm()
        picker.destroy()
        self.assertIn("Added Emerald Hammer (Unique", self.save())
        hammer = next(item for item in self.saved_hero().items() if item.tag == "SW.Item.BattleHammer")
        self.assertEqual((hammer.rarity, hammer.name), ("Unique", "Emerald Hammer"))

    def test_rarity_unique_shows_the_unique_name_in_the_list(self):
        self.select_item("Mystic Circlet")
        self.tab._apply_item(rarity="Unique")
        self.assertIn("Oracle Crown", self.rows())

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
        self.assertIn("Emeralds: 55 → 9,999", text)
        self.assertIn("Unconfirmed items", text)
        self.assertFalse(dialog.rarity_row.winfo_manager())  # Most money doesn't ask for a rarity
        dialog._apply()
        self.assertTrue(dialog.message_var.get().startswith("Applied Most money"))
        dialog.destroy()
        self.assertEqual(self.tab.stat_vars["Emeralds"].get(), "9999")
        self.assertIn("Emeralds: 55 → 9,999", self.save())

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

    def test_share_item_ids_window(self):
        from dungeons2_editor.share_ids import ShareIdsDialog

        with mock.patch("webbrowser.open") as browser:
            self.app._share_ids()
            self.root.update()
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, ShareIdsDialog))
            self.assertIn("SW.Item.CurvedGreatsword", dialog.report())
            dialog.open_issue()
        self.assertIn("template=item-ids.yml", browser.call_args.args[0])
        dialog.destroy()

    def test_advanced_mode_lets_stats_pass_the_game_caps(self):
        self.tab.stat_vars["Emeralds"].set("50000")
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

    def test_shows_the_game_style_screen(self):
        self.assertEqual(ttk.Style(self.root).theme_use(), game_style.THEME)
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
        self.assertEqual(self.shown(), ["Curved Greatsword"])
        self.show("Armor")
        self.assertEqual(self.shown(), ["Mystic Circlet"])
        self.assertEqual(self.screen.count_text.get(), "1 ITEM")
        self.show("Talisman")
        self.assertEqual((self.shown(), self.screen._item_hits), ([], []))

    def test_change_rarity_and_power_on_the_card(self):
        self.screen.pick_item(self.index_of("SW.Item.MysticHelmet"))
        self.assertEqual((self.screen.banner_text, self.screen.card_name_var.get()), ("INVENTORY", "MYSTIC CIRCLET"))
        self.assertIn("Make it Unique to get the Oracle Crown.", self.screen.card_text_var.get())
        unique = next(button for button in self.screen.rarity_buttons if str(button.cget("value")) == "Unique")
        unique.invoke()
        self.assertEqual(self.screen.card_name_var.get(), "ORACLE CROWN")
        self.assertEqual(self.screen.card_text_var.get(), "Lightning attacks deal 25% more damage.")
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

    def test_merchant_stock_can_be_copied_but_not_worn(self):
        self.show("Merchant")
        self.screen.pick_item(self.index_of("SW.Item.CurvedGreatsword"))
        self.assertEqual(self.screen.banner_text, "MERCHANT STOCK")
        self.assertTrue(self.screen.equip_button.instate(["disabled"]))
        self.screen.copy_button.invoke()
        self.assertIn("Copied", self.screen.item_message_var.get())
        self.assertEqual(self.screen.banner_text, "INVENTORY")  # the copy is yours
        self.show("All")
        self.assertIn("Curved Greatsword", self.shown())

    def test_delete_from_the_card(self):
        self.screen.pick_item(self.index_of("SW.Item.Longbow"))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            self.screen.delete_button.invoke()
        self.assertEqual(self.shown(), ["Mystic Circlet"])
        self.assertEqual(self.screen.banner_text, "YOUR HERO")
        self.assertIn("Removed Longbow", self.save())

    def test_stats_stop_at_the_game_caps(self):
        emeralds = self.screen.stat_vars["Emeralds"]
        emeralds.set("50000")
        self.assertFalse(self.screen._apply_stat("Emeralds"))
        self.assertIn("cap", self.screen.stats_message_var.get())
        self.assertEqual(str(self.screen.stats_message.cget("style")), "MessageError.TLabel")
        self.assertEqual(emeralds.get(), "55")
        emeralds.set("9998")
        self.assertTrue(self.screen._apply_stat("Emeralds"))
        self.assertEqual(self.screen._nudge_stat("Emeralds", 5), "break")  # arrow keys stop at the cap
        self.assertEqual(emeralds.get(), "9999")
        self.app.advanced_var.set(True)
        self.app._on_advanced_toggled()
        self.assertEqual(self.app.hero_tab.stat_vars["Emeralds"].get(), "9999")  # the Hero tab sees the change
        self.app.hero_tab.stat_vars["Emeralds"].set("50000")
        self.assertTrue(self.app.hero_tab._apply_stat("Emeralds"))  # Advanced mode may go past the caps
        self.app.advanced_var.set(False)
        self.app._on_advanced_toggled()
        self.assertEqual(self.screen.stat_vars["Emeralds"].get(), "50000")

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
        self.show("Merchant")
        self.screen.pick_item(self.index_of("SW.Item.CurvedGreatsword"))
        self.assertIn("name made from its save ID", self.screen.card_kind_var.get())
        self.assertTrue(self.screen.name_button.instate(["!disabled"]))
        with mock.patch.object(self.screen, "_ask_text", return_value="Cookiecutter"):
            self.screen.name_button.invoke()
        self.assertEqual(self.screen.card_name_var.get(), "COOKIECUTTER")
        self.assertEqual(json.loads(self.names_file.read_text(encoding="utf-8")), {"SW.Item.CurvedGreatsword": "Cookiecutter"})
        self.assertIn("SW.Item.CurvedGreatsword - Cookiecutter", share_ids.report_text([self.screen.hero], "9"))


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
