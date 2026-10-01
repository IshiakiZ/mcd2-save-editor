import copy
import gc
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import gui, saves
from dungeons2_editor.hero import Hero
from dungeons2_editor.item_picker import ItemPicker

from .helpers import SETTINGS_TEXT, hero_save_text, make_profile, shift_encode

HERO = "Character00000000-0000-1000-8000-000000000002"


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
        with mock.patch.object(saves, "find_profiles", return_value=[]):
            self.app = gui.EditorApp(self.root, self.profile_path, self.dir / "backups", self.dir / "icons", self.settings_file)
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

    def test_switching_to_simple_mode_hides_the_technical_parts(self):
        self.app.advanced_var.set(False)
        self.app._on_advanced_toggled()
        self.assertEqual(self.container_names(), [])
        self.assertEqual(self.app.notebook.tab(self.app.edit_tab, "state"), "hidden")
        self.assertEqual(self.app.title_var.get(), "No offline heroes yet")
        self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8")), {"advanced": False})


@unittest.skipUnless(_tk_available(), "needs a display")
class HeroTabTests(WindowTestCase):
    containers = {"GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT), HERO: hero_save_text().encode()}

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

    def test_simple_mode_shows_only_heroes_and_the_hero_tab(self):
        self.assertEqual(self.app.container.name, HERO)
        self.assertEqual(self.container_names(), [HERO])
        self.assertEqual(self.app.notebook.select(), str(self.tab))
        for tab in (self.app.edit_tab, self.app.raw_tab):
            self.assertEqual(self.app.notebook.tab(tab, "state"), "hidden")
        self.assertFalse(self.tab.raw_row.winfo_manager())
        self.assertTrue(self.app.meta_var.get().startswith("Last saved"))

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
        locked, values = self.slot_row("Artifact 2")
        self.assertEqual(values[0], "opens at level 5")
        self.tab.gear_tree.selection_set(locked)
        self.root.update()
        self.assertTrue(self.tab.slot_add_button.instate(["disabled"]))
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

    def test_slots_that_open_later_are_offered_but_locked(self):
        picker, _row = self.open_picker_on("Firework Arrow")
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
            with mock.patch("dungeons2_editor.hero_tab.ItemPicker") as picker_class:
                picker_class.return_value.result = "SW.Item.Axe"
                self.tab.change_item()
        self.assertIn("Axe", self.rows())

    def test_advanced_mode_shows_raw_ids_and_other_saves(self):
        self.app.advanced_var.set(True)
        self.app._on_advanced_toggled()
        self.assertIn("GlobalSaveDataDefault", self.container_names())
        self.assertEqual(self.app.notebook.tab(self.app.edit_tab, "state"), "normal")
        self.assertTrue(self.tab.raw_row.winfo_manager())
        self.select_item("Mystic Circlet")
        self.assertEqual(self.tab.type_var.get(), "SW.Item.MysticHelmet")

    def test_edits_in_the_tree_show_up_on_the_hero_tab(self):
        self.app.advanced_var.set(True)
        self.app._on_advanced_toggled()
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
        hero = self.tab.hero
        self.assertEqual(hero.equipped("SW.ItemSlot.Equipment.MeleeWeapon").name, "Pride of the Plains")
        self.assertEqual(hero.equipped("SW.ItemSlot.Equipment.Armor.Helmet").name, "Twisted Warden Blindfold")
        self.assertIsNone(hero.equipped("SW.ItemSlot.Equipment.Artifact.Slot2"))  # this hero is level 1
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

    def test_simple_mode_stops_stats_at_the_game_cap(self):
        self.tab.stat_vars["Emeralds"].set("50000")
        self.assertFalse(self.tab._apply_stat("Emeralds"))
        self.assertIn("cap", self.tab.stats_message_var.get())
        self.app.advanced_var.set(True)
        self.app._on_advanced_toggled()
        self.tab.stat_vars["Emeralds"].set("50000")
        self.assertTrue(self.tab._apply_stat("Emeralds"))
        self.assertIn("above the game's cap", self.tab.stats_message_var.get())

    def test_hero_rows_show_level_and_emeralds(self):
        details = [self.app.container_list.item(iid, "values")[0] for iid, c in self.app._containers_by_iid.items() if c.name == HERO]
        self.assertEqual(details, ["Lv 1 · 55 emeralds"])


if __name__ == "__main__":
    unittest.main()
