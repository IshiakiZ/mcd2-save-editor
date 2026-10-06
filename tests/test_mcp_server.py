import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dungeons2_editor import saves
from dungeons2_editor.hero import Hero
from dungeons2_editor.mcp_server import PROTOCOL_VERSIONS, EditorServer, serve_streams

from .helpers import SETTINGS_TEXT, enchanted, enchantment_effect, hero_item, hero_save, make_profile, rolled, rolled_effect, shift_encode, talisman_item

ROOT = Path(__file__).resolve().parent.parent
HERO = "Character00000000-0000-1000-8000-000000000002"
ONLINE = "Character00000000-0000-1000-8000-000000000009"


def online_hero_text():
    save = hero_save(online=True)
    save["CharacterSaveV1"]["MetaData"]["CharacterId"] = "99999999-0000-1000-8000-000000000009"
    return json.dumps(save, separators=(",", ":"))


class ServerTestCase(unittest.TestCase):
    """An MCP server on a temporary save folder: an offline hero, an online one, settings and a sign-in token."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.profile = make_profile(
            self.dir / "saves",
            {
                HERO: json.dumps(hero_save(), separators=(",", ":")).encode(),
                ONLINE: online_hero_text().encode(),
                "GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT),
                "auth_dynamic_entjwtbin": b"\x01\x02secret",
            },
        )
        patcher = mock.patch.object(saves, "running_game_processes", return_value=[])
        self.running = patcher.start()
        self.addCleanup(patcher.stop)
        self.server = EditorServer(self.profile, self.dir / "backups")
        self.next_id = 0

    def request(self, method, params=None):
        self.next_id += 1
        reply = self.server.handle({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        self.assertEqual(reply["id"], self.next_id)
        return reply

    def call(self, tool, **arguments):
        """A tool's result, or its error message."""
        result = self.request("tools/call", {"name": tool, "arguments": arguments})["result"]
        text = result["content"][0]["text"]
        return text if result["isError"] else json.loads(text)

    def saved_hero(self):
        return saves.SaveProfile(self.profile).get(HERO).hero

    def ref_of(self, name):
        hero = self.call("get_hero", hero="00000000")
        items = hero["inventory"] + hero["merchant_stock"] + [slot["item"] for slot in hero["gear"] if slot["item"]]
        return next(item["ref"] for item in items if item["name"] == name)


class ProtocolTests(ServerTestCase):
    def test_initialize_agrees_a_protocol_version(self):
        for asked, agreed in (("2025-06-18", "2025-06-18"), ("2024-11-05", "2024-11-05"), ("2099-01-01", PROTOCOL_VERSIONS[0])):
            result = self.request("initialize", {"protocolVersion": asked, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})["result"]
            self.assertEqual(result["protocolVersion"], agreed)
        self.assertEqual(result["serverInfo"]["name"], "mcd2-save-editor")
        self.assertIn("tools", result["capabilities"])
        self.assertIn("save_changes", result["instructions"])

    def test_lists_the_tools(self):
        tools = {tool["name"]: tool for tool in self.request("tools/list")["result"]["tools"]}
        self.assertEqual(set(tools), {
            "list_heroes", "get_hero", "find_items", "list_presets", "set_stats", "add_item", "change_item", "equip_item",
            "unequip_item", "copy_item", "delete_item", "apply_preset", "preview_changes", "save_changes", "discard_changes",
            "list_effects", "set_item_effects", "add_unique_effect", "ready_talisman",
        })
        self.assertTrue(tools["get_hero"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["save_changes"]["annotations"]["destructiveHint"])
        self.assertEqual(tools["add_item"]["inputSchema"]["required"], ["hero", "item"])

    def test_notifications_and_mistakes(self):
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.request("ping")["result"], {})
        self.assertEqual(self.request("resources/list")["error"]["code"], -32601)
        self.assertEqual(self.request("tools/call", {"name": "nope"})["error"]["code"], -32602)
        self.assertEqual(self.server.handle({"id": 1, "method": "ping"})["error"]["code"], -32600)  # not JSON-RPC 2.0
        self.assertIn("doesn't take", self.call("list_heroes", sneaky=True))
        self.assertIn("needs hero", self.call("get_hero"))

    def test_structured_results_from_2025_06_18(self):
        self.request("initialize", {"protocolVersion": "2025-06-18"})
        result = self.request("tools/call", {"name": "list_presets", "arguments": {}})["result"]
        self.assertIn("presets", result["structuredContent"])
        self.request("initialize", {"protocolVersion": "2024-11-05"})
        result = self.request("tools/call", {"name": "list_presets", "arguments": {}})["result"]
        self.assertNotIn("structuredContent", result)

    def test_answers_over_stdio(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_heroes", "arguments": {}}},
        ]
        reader = io.BytesIO(b"\n".join(json.dumps(line).encode() for line in lines) + b"\n\nnot json\n")
        writer = io.BytesIO()
        serve_streams(self.server, reader, writer)
        replies = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual([reply.get("id") for reply in replies], [1, 2, None])
        self.assertEqual(replies[2]["error"]["code"], -32700)


class ReadingTests(ServerTestCase):
    def test_lists_heroes_but_never_the_sign_in_token(self):
        result = self.call("list_heroes")
        heroes = {hero["hero"]: hero for hero in result["heroes"]}
        self.assertEqual(set(heroes), {"00000000", "99999999"})
        self.assertTrue(heroes["00000000"]["editable"])
        self.assertEqual(heroes["00000000"]["emeralds"], 55)
        self.assertFalse(heroes["99999999"]["editable"])
        self.assertFalse(result["game_running"])
        self.assertNotIn("auth", json.dumps(result))
        self.assertNotIn(str(self.profile.name), json.dumps(result))  # the profile folder (an Xbox user ID) stays private

    def test_get_hero(self):
        hero = self.call("get_hero", hero="Ranger Deluxe")  # by name, too: the offline hero, not the online one
        self.assertEqual((hero["hero"], hero["level"], hero["gear_power"]), ("00000000", 1, 1))
        emeralds = next(stat for stat in hero["stats"] if stat["stat"] == "Emeralds")
        self.assertEqual((emeralds["value"], emeralds["cap"]), (55, 99999))
        gear = {slot["slot"]: slot for slot in hero["gear"]}
        self.assertEqual(len(gear), 12)
        self.assertEqual(gear["Melee weapon"]["item"]["name"], "Sword")
        self.assertFalse(gear["Artifact 2"]["open"])  # opens at level 5
        self.assertEqual([item["name"] for item in hero["inventory"]], ["Mystic Circlet", "Longbow"])
        self.assertEqual([item["name"] for item in hero["merchant_stock"]], ["Cookiecutter"])
        self.assertEqual(hero["inventory"][0]["at_unique"], "Oracle Crown")
        self.assertTrue(all(item["ref"] for item in hero["inventory"]))
        self.assertEqual(hero["unsaved_changes"], [])

    def test_find_items_and_presets(self):
        found = self.call("find_items", query="oracle crown")
        self.assertEqual([item["name"] for item in found["items"]], ["Mystic Circlet"])
        self.assertEqual(found["items"][0]["unique"], "Oracle Crown")
        talismans = self.call("find_items", kind="Talisman", limit=3)
        self.assertEqual(len(talismans["items"]), 3)
        self.assertGreater(talismans["matches"], 3)
        self.assertTrue(all(item["confirmed"] for item in self.call("find_items", confirmed_only=True, limit=200)["items"]))
        titles = [preset["preset"] for preset in self.call("list_presets")["presets"]]
        self.assertIn("Most money", titles)
        self.assertIn("Melee damage", titles)


class EditingTests(ServerTestCase):
    def test_changes_wait_in_a_draft_until_saved(self):
        result = self.call("set_stats", hero="00000000", stats={"Emeralds": 5000, "level": 3})
        self.assertEqual(result["unsaved_changes"], ["Emeralds: 55 → 5,000", "Level: 1 → 3"])
        self.assertEqual(self.saved_hero().attribute("Emeralds"), 55)  # nothing written yet
        self.assertEqual(self.call("get_hero", hero="00000000")["level"], 3)  # but the draft shows it
        self.assertEqual(self.call("list_heroes")["heroes"][0]["unsaved_changes"], 2)
        self.assertEqual(self.call("preview_changes", hero="00000000")["unsaved_changes"], ["Emeralds: 55 → 5,000", "Level: 1 → 3"])
        saved = self.call("save_changes", hero="00000000")
        self.assertEqual(saved["saved_changes"], ["Emeralds: 55 → 5,000", "Level: 1 → 3"])
        self.assertTrue((self.dir / "backups" / saved["backup"]).is_dir())  # backed up first
        self.assertEqual((self.saved_hero().attribute("Emeralds"), self.saved_hero().level), (5000, 3))
        self.assertEqual(self.call("save_changes", hero="00000000")["done"], "There's nothing to save.")

    def test_stats_stop_at_the_game_caps(self):
        self.assertIn("ignore_caps", self.call("set_stats", hero="00000000", stats={"Emeralds": 500000}))
        self.assertEqual(self.call("set_stats", hero="00000000", stats={"Emeralds": 500000}, ignore_caps=True)["done"], "Set Emeralds 500,000.")
        self.assertIn("no stat", self.call("set_stats", hero="00000000", stats={"Echo shards": 50}))  # this hero has none yet

    def test_add_a_unique_by_its_name_and_equip_it(self):
        result = self.call("add_item", hero="00000000", item="Oracle Tights", power=3, equip=True)
        self.assertEqual(result["done"], "Added the Oracle Tights (Unique, power 3) and equipped it (leggings).")
        gear = {slot["slot"]: slot["item"] for slot in self.call("get_hero", hero="00000000")["gear"]}
        # A Unique has a save ID of its own; this one has been seen in a real save.
        self.assertEqual((gear["Leggings"]["name"], gear["Leggings"]["id"]), ("Oracle Tights", "SW.Item.MysticLeggings_Unique"))
        # It comes with the effect of its own, saved the way the game saves it, so there's nothing to warn about.
        self.assertEqual(gear["Leggings"]["unique_effect"], "Reduces artifact cooldown time by 30%.")
        self.assertEqual([(effect["name"], effect["strength"]) for effect in gear["Leggings"]["effects"]], [("Cooldown", -0.3)])
        self.assertNotIn("unique_effect_note", gear["Leggings"])
        # The Oracle Crown's hasn't, but it follows the pattern every seen one does, so it can be added too.
        found = self.call("find_items", query="Mystic Circlet")["items"][0]
        self.assertEqual((found["unique"], found["unique_confirmed"], found["unique_by_pattern"]), ("Oracle Crown", False, True))
        self.assertNotIn("unique_effect_note", found)
        # The Ranger's Promise is one whose own effect the editor hasn't seen: the assistant is told before and after.
        bow = next(item for item in self.call("find_items", query="Bow")["items"] if item["name"] == "Bow")
        self.assertEqual(bow["unique_effect_note"], "The editor adds this Unique without its own effect: it hasn't seen how the game saves that one yet.")
        promise = self.call("add_item", hero="00000000", item="Ranger's Promise", allow_unconfirmed=True)["item"]
        self.assertEqual(promise["unique_effect_note"], "Without its own effect: the editor can't add that one yet.")
        self.assertIn("hasn't seen how the game saves the Ranger's Promise's own effect yet", self.call("add_unique_effect", hero="00000000", item=promise["ref"]))
        crown = self.call("add_item", hero="00000000", item="Mystic Circlet", rarity="Unique")["item"]
        self.assertEqual((crown["name"], crown["id"], crown["unique_effect"]), ("Oracle Crown", "SW.Item.MysticHelmet_Unique", "Lightning attacks deal 25% more damage."))
        self.assertEqual(self.call("add_item", hero="00000000", item="Longbow")["item"]["power"], 3)  # power defaults to the best item's
        self.assertIn("Did you mean", self.call("add_item", hero="00000000", item="mystic"))

    def test_talismans_have_no_rarity_or_power_and_need_their_effect(self):
        result = self.call("add_item", hero="00000000", item="Sigil of Beeswax", rarity="Unique", power=40, equip=True)
        self.assertEqual(result["done"], "Added the Sigil of Beeswax and equipped it (talisman 1).")
        self.assertEqual((result["item"]["kind"], "rarity" in result["item"], "power" in result["item"], "note" in result["item"]), ("Talisman", False, False, False))
        self.assertEqual(result["unsaved_changes"], ["Added Sigil of Beeswax, equipped (talisman 1)"])
        self.assertIn("is a talisman: it has no rarity or power", self.call("change_item", hero="00000000", item=result["item"]["ref"], rarity="Rare"))
        # The Twig of Dark Oak's save ID is known, but not what the game saves as its effect.
        found = {item["name"]: item for item in self.call("find_items", query="", kind="Talisman", limit=50)["items"]}
        self.assertEqual((found["Twig of Dark Oak"]["confirmed"], found["Twig of Dark Oak"]["effect_known"]), (True, False))
        self.assertNotIn("effect_known", found["Sigil of Beeswax"])
        sure = [item["name"] for item in self.call("find_items", kind="Talisman", confirmed_only=True, limit=50)["items"]]
        self.assertEqual(sure, ["Sigil of Beeswax"])
        refused = self.call("add_item", hero="00000000", item="Twig of Dark Oak")
        self.assertIn("hasn't seen the Twig of Dark Oak's effect", refused)
        self.assertNotIn("best guess", refused)  # its ID isn't one
        twig = self.call("add_item", hero="00000000", item="Twig of Dark Oak", allow_unconfirmed=True)
        self.assertEqual(twig["done"], "Added the Twig of Dark Oak.")
        self.assertIn("No effect is saved", twig["item"]["note"])
        kit = self.call("apply_preset", hero="00000000", preset="Best talismans")
        self.assertIn("Fist of Iron (effect not known yet)", kit["left_out"])
        self.assertIn("Ocelot's Paw (best-guess save ID)", kit["left_out"])

    def test_an_owned_item_is_not_risked_on_a_uniques_pattern(self):
        # Adding the Oracle Crown under its pattern ID risks nothing but the new item. Turning the hero's own
        # Longbow into it would risk the Longbow, so that needs the ID to have been seen, or a yes.
        refused = self.call("change_item", hero="00000000", item=self.ref_of("Longbow"), change_into="Oracle Crown")
        self.assertIn("SW.Item.MysticHelmet_Unique) is a best guess", refused)
        changed = self.call("change_item", hero="00000000", item=self.ref_of("Longbow"), change_into="Oracle Crown", allow_unconfirmed=True)
        self.assertEqual((changed["item"]["name"], changed["item"]["id"]), ("Oracle Crown", "SW.Item.MysticHelmet_Unique"))

    def test_effects_are_shown_as_the_game_saved_them(self):
        document = json.loads(json.dumps(hero_save()))
        sword = next(e for e in document["CharacterSaveV1"]["Inventory"]["Entries"] if e["ItemData"]["TypeTag"] == "SW.Item.Sword")
        sword["ItemData"]["Effects"] = [rolled(rolled_effect("CriticalEdge", 0.2, "II")), enchanted(enchantment_effect("Radiance", 0.3))]
        document["CharacterSaveV1"]["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", xp=90, seed=61))
        document["CharacterSaveV1"]["CollectionsStats"]["ShownHints"] = [{"Tag": "SW.UI.Onboarding.Panel.Enchantsmith.Overview", "Count": 1}]
        self.profile = make_profile(
            self.dir / "saves2", {HERO: json.dumps(document, separators=(",", ":")).encode(), "GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT)}
        )
        self.server = EditorServer(self.profile, self.dir / "backups")
        hero = self.call("get_hero", hero="00000000")
        gear = {slot["slot"]: slot["item"] for slot in hero["gear"]}
        self.assertEqual(gear["Melee weapon"]["effects"], [
            {"name": "Critical Edge", "id": "SW.Effect.CriticalEdge", "strength": 0.2, "tier": "II"},
            {"name": "Healing Smite", "id": "SW.Enchantment.Radiance", "strength": 0.3, "tier": "I", "enchantment": True, "enchantment_points": 3},
        ])
        sigil = next(item for item in hero["inventory"] if item["name"] == "Sigil of Beeswax")
        self.assertEqual((sigil["talisman_level"], sigil["xp"], sigil["xp_for_next_level"]), (1, 90, 18480))
        # Which town vendors the hero has unlocked, by the game's own records.
        self.assertEqual(hero["vendors"], {"Village Merchant": False, "Blacksmith": False, "Enchantsmith": True})

    def test_effects_and_an_enchantment_are_set_from_the_ones_the_editor_has_seen(self):
        listed = self.call("list_effects")
        self.assertEqual(listed["most_effects_on_an_item"], 4)
        edge = next(entry for entry in listed["effects"] if entry["name"] == "Critical Edge")
        self.assertEqual((edge["id"], edge["rolls_on"]), ("SW.Effect.CriticalEdge", "Any weapon"))
        self.assertEqual(edge["tiers"], [{"tier": "I", "strength": "10%"}, {"tier": "II", "strength": "20%"}])
        knock = next(entry for entry in listed["effects"] if entry["name"] == "Knockback")
        self.assertEqual(knock["tiers"][1:], [{"tier": "II", "strength": "20%", "seen": False}, {"tier": "III", "strength": "30%", "seen": False}])
        self.assertEqual(next(entry for entry in listed["effects"] if entry["name"] == "Lightning Focus")["probably_called"], "Electromancer")
        smite = next(entry for entry in listed["enchantments"] if entry["name"] == "Healing Smite")
        self.assertEqual((smite["goes_on"], smite["tiers"]), (["Melee", "Ranged"], [{"tier": "I"}]))
        self.assertIn("Kills can create a Regenerating well (tiers I, II and III: 20% / 35% / 50% chance)", smite["does"])
        self.assertEqual([entry["name"] for entry in self.call("list_effects", query="smite")["enchantments"]], ["Healing Smite"])
        sword = self.ref_of("Sword")
        # A name without a tier gets the best tier a save has shown; one no save has shown needs a yes.
        done = self.call("set_item_effects", hero="00000000", item=sword, effects=["critical edge", "Looter I"], enchantment="Healing Smite")
        self.assertEqual(done["done"], "The Sword: effects: Critical Edge II, Looter I; enchanted with Healing Smite I.")
        self.assertEqual([effect["name"] + " " + effect["tier"] for effect in done["item"]["effects"]], ["Critical Edge II", "Looter I", "Healing Smite I"])
        self.assertIn("hasn't opened the Enchantsmith", done["heads_up"])
        self.assertEqual(done["unsaved_changes"], ["Sword: effects: Critical Edge II 20%, Looter I 20%, enchanted with Healing Smite I"])
        self.assertIn("hasn't been seen in a real save yet", self.call("set_item_effects", hero="00000000", item=sword, effects=["Knockback III"]))
        self.assertIn("Knockback III", self.call("set_item_effects", hero="00000000", item=sword, effects=["Knockback III"], allow_unseen=True)["done"])
        self.assertIn("known at tier I, II, not III", self.call("set_item_effects", hero="00000000", item=sword, effects=["Critical Edge III"]))
        # What can't be done says why, and leaves the draft as it was.
        for arguments, why in (
            ({"effects": ["Sharpness"]}, "can't write 'Sharpness' yet"),
            ({"effects": ["Looter IV"]}, "can't write 'Looter IV' yet"),
            ({"effects": ["Acrobat", "Knockback", "Looter", "Luck", "Vanguard"]}, "caps an item at 4 effects"),
            ({"effects": "Looter"}, "effects is a list of names"),
            ({"enchantment": "Piercing"}, "Piercing goes on ranged weapons"),
            ({"enchantment": "Critical Edge"}, "can't write 'Critical Edge' yet"),
            ({}, "Say what to set"),
        ):
            self.assertIn(why, self.call("set_item_effects", hero="00000000", item=sword, **arguments))
        self.assertIn("Knockback III", json.dumps(self.call("preview_changes", hero="00000000")["unsaved_changes"]))
        # Leaving one out keeps it; an empty list and "none" take them off.
        # best_for: the editor's own picks for a goal, out of what the game rolls on this item, ahead of what it has.
        self.call("set_item_effects", hero="00000000", item=sword, effects=["Knockback I", "Looter I"])
        best = self.call("set_item_effects", hero="00000000", item=sword, best_for="damage")
        self.assertEqual([effect["name"] for effect in best["item"]["effects"] if not effect.get("enchantment")], ["Critical Hit", "Critical Edge", "Vanguard", "Knockback"])
        self.assertIn(
            "Best for damage on the Sword (Fighter gear): Critical Hit I, Critical Edge II and Vanguard I. Kept Knockback I. Took off Looter I.",
            best["done"],
        )
        self.assertIn("The game rolls no effect for mobility on the Sword (Fighter gear)", self.call("set_item_effects", hero="00000000", item=sword, best_for="Mobility"))
        self.assertIn("No effect on gear gives XP. The Eye of Experience talisman does", self.call("set_item_effects", hero="00000000", item=sword, best_for="XP"))
        self.assertIn("best_for is one of: Damage, Survival, Mobility, Loot, Artifacts and souls, Companions.", self.call("set_item_effects", hero="00000000", item=sword, best_for="Fishing"))
        self.assertIn("Give effects or best_for, not both", self.call("set_item_effects", hero="00000000", item=sword, effects=["Looter"], best_for="Loot"))
        cleared = self.call("set_item_effects", hero="00000000", item=sword, effects=[])
        self.assertEqual([effect["name"] for effect in cleared["item"]["effects"]], ["Healing Smite"])
        gone = self.call("set_item_effects", hero="00000000", item=sword, enchantment="none")
        self.assertNotIn("effects", gone["item"])
        self.assertEqual(gone["unsaved_changes"], [])
        self.call("set_item_effects", hero="00000000", item=sword, effects=["Looter"])
        self.call("save_changes", hero="00000000")
        self.assertEqual(next(item for item in self.saved_hero().items() if item.tag == "SW.Item.Sword").effect_lines(), ["Looter I 20%"])

    def test_a_unique_from_an_older_version_is_given_its_own_effect(self):
        self.assertIn("isn't a Unique", self.call("add_unique_effect", hero="00000000", item=self.ref_of("Sword")))
        document = json.loads(json.dumps(hero_save()))
        document["CharacterSaveV1"]["Inventory"]["Entries"].append(hero_item("SW.Item.Sword_Unique1", rarity="Unique", seed=61, unseen=False))
        self.profile = make_profile(self.dir / "saves4", {HERO: json.dumps(document, separators=(",", ":")).encode()})
        self.server = EditorServer(self.profile, self.dir / "backups")
        blade = next(item for item in self.call("get_hero", hero="00000000")["inventory"] if item["name"] == "The Burning Blade")
        self.assertEqual(blade["unique_effect_note"], "Without its own effect.")
        done = self.call("add_unique_effect", hero="00000000", item=blade["ref"])
        self.assertEqual(done["done"], "The Burning Blade has its own effect now, saved the way the game saves it.")
        self.assertEqual((done["item"]["effects"][0]["name"], "unique_effect_note" in done["item"]), ("Fire Focus", False))
        self.assertEqual(done["unsaved_changes"], ["The Burning Blade: given its own effect"])
        self.assertIn("has its own effect already", self.call("add_unique_effect", hero="00000000", item=blade["ref"]))

    def test_a_talisman_is_made_ready_to_level_up(self):
        self.assertIn("only talismans do", self.call("ready_talisman", hero="00000000", item=self.ref_of("Sword")))
        document = json.loads(json.dumps(hero_save()))
        document["CharacterSaveV1"]["Inventory"]["Entries"].append(talisman_item("SW.Item.Talisman.HealthBoost", "HealthBoost", xp=90, seed=61))
        self.profile = make_profile(self.dir / "saves3", {HERO: json.dumps(document, separators=(",", ":")).encode()})
        self.server = EditorServer(self.profile, self.dir / "backups")
        done = self.call("ready_talisman", hero="00000000", item=self.ref_of("Sigil of Beeswax"))
        self.assertIn("XP is 18,479, one short of level 2", done["done"])
        self.assertEqual((done["item"]["xp"], done["unsaved_changes"]), (18479, ["Sigil of Beeswax: XP 90 → 18,479"]))

    def test_guessed_ids_and_locked_slots_need_permission(self):
        self.assertIn("best guess", self.call("add_item", hero="00000000", item="Battlestaff"))
        self.assertNotIn("best guess", json.dumps(self.call("add_item", hero="00000000", item="Battlestaff", allow_unconfirmed=True)))
        self.assertNotIn("best guess", json.dumps(self.call("add_item", hero="00000000", item="Riftslasher")))  # reported from a real save
        self.assertIn("opens at level 10", self.call("add_item", hero="00000000", item="Firework Arrow", equip="Artifact 3"))
        result = self.call("add_item", hero="00000000", item="Firework Arrow", equip="artifact3", ignore_slot_levels=True)
        self.assertIn("equipped it (artifact 3)", result["done"])

    def test_a_refused_change_leaves_the_draft_alone(self):
        self.call("set_stats", hero="00000000", stats={"Emeralds": 100})
        self.assertIn("between", self.call("change_item", hero="00000000", item=self.ref_of("Longbow"), power=-1))
        self.assertIn("isn't equipped", self.call("unequip_item", hero="00000000", item=self.ref_of("Longbow")))
        self.assertEqual(self.call("preview_changes", hero="00000000")["unsaved_changes"], ["Emeralds: 55 → 100"])

    def test_item_actions(self):
        longbow, circlet, sword = self.ref_of("Longbow"), self.ref_of("Mystic Circlet"), self.ref_of("Sword")
        self.call("change_item", hero="00000000", item=circlet, rarity="Unique", power=20)
        self.assertIn("Equipped the Longbow (ranged weapon)", self.call("equip_item", hero="00000000", item=longbow)["done"])
        self.assertIn("Unequip the Sword", self.call("change_item", hero="00000000", item=sword, change_into="Axe"))
        self.call("unequip_item", hero="00000000", item=sword)
        self.call("change_item", hero="00000000", item=sword, change_into="Axe")
        copy_ref = self.call("copy_item", hero="00000000", item=self.ref_of("Cookiecutter"))["item"]["ref"]
        self.call("delete_item", hero="00000000", item=copy_ref)
        self.assertIn("no item with ref", self.call("delete_item", hero="00000000", item=copy_ref))
        changes = self.call("preview_changes", hero="00000000")["unsaved_changes"]
        self.assertIn("Mystic Circlet: Common → Unique, power 1 → 20", changes)
        self.assertIn("Longbow: equipped (ranged weapon)", changes)
        self.assertIn("Sword: changed into Axe, unequipped", changes)
        self.assertEqual(self.call("discard_changes", hero="00000000")["done"], "Threw the unsaved changes away.")
        self.assertEqual(self.call("preview_changes", hero="00000000")["unsaved_changes"], [])

    def test_a_caution_with_a_save_format_the_editor_wasnt_checked_against(self):
        saved = self.call("set_stats", hero="00000000", stats={"Emeralds": 60}) and self.call("save_changes", hero="00000000")
        self.assertNotIn("caution", saved)
        document = hero_save()
        document["SerializeMeta"]["SoftVersion"] = 6  # as a later version of the game might save it
        self.profile = make_profile(
            self.dir / "newer", {HERO: json.dumps(document, separators=(",", ":")).encode(), "GlobalSaveDataDefault": shift_encode(SETTINGS_TEXT)}
        )
        self.server = EditorServer(self.profile, self.dir / "backups")
        self.call("set_stats", hero="00000000", stats={"Emeralds": 61})
        saved = self.call("save_changes", hero="00000000")
        self.assertEqual(saved["done"], "Saved. Start the game to see the changes.")
        self.assertIn("hasn't been checked against (FCharacterSaveV1, version 6)", saved["caution"])

    def test_presets(self):
        self.assertEqual(self.call("apply_preset", hero="00000000", preset="most money")["preset_did"], ["Emeralds: 55 → 99,999"])
        kit = self.call("apply_preset", hero="00000000", preset="Melee damage", power=12)
        self.assertTrue(kit["left_out"])  # best-guess items stay out unless asked for
        self.assertIn("no preset", self.call("apply_preset", hero="00000000", preset="Max everything"))

    def test_online_heroes_and_other_containers_cant_be_changed(self):
        self.assertIn("online hero", self.call("set_stats", hero="99999999", stats={"Emeralds": 1}))
        self.assertIn("There's no hero", self.call("set_stats", hero="auth_dynamic_entjwtbin", stats={"Emeralds": 1}))
        self.assertIn("There's no hero", self.call("get_hero", hero="GlobalSaveDataDefault"))

    def test_no_saving_while_the_game_runs(self):
        self.call("set_stats", hero="00000000", stats={"Emeralds": 100})
        self.running.return_value = ["Dungeons-WinGDK-Shipping.exe"]
        self.assertIn("running", self.call("save_changes", hero="00000000").lower())
        self.assertEqual(self.saved_hero().attribute("Emeralds"), 55)
        self.running.return_value = []
        self.call("save_changes", hero="00000000")  # the draft was kept
        self.assertEqual(self.saved_hero().attribute("Emeralds"), 100)

    def test_keeps_the_games_progress_when_it_saved_in_between(self):
        self.call("set_stats", hero="00000000", stats={"Emeralds": 100})
        game = saves.SaveProfile(self.profile)  # the game saves the hero (a play session)
        document = copy.deepcopy(game.get(HERO).decoded.document)
        Hero(document).set_attributes({"XP": 3000})
        game.save(HERO, document, self.dir / "game-backups", check_game=lambda: [])
        self.assertIn("re-apply", self.call("preview_changes", hero="00000000")["note"])
        self.call("save_changes", hero="00000000")
        hero = self.saved_hero()
        self.assertEqual((hero.attribute("Emeralds"), hero.attribute("XP")), (100, 3000))  # yours and the game's


class CommandLineTests(unittest.TestCase):
    def test_runs_over_stdin_and_stdout(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = make_profile(Path(temp) / "saves", {HERO: json.dumps(hero_save()).encode()})
            messages = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_hero", "arguments": {"hero": "00000000"}}},
            ]
            for command in self._commands():
                with self.subTest(command=command[0]):
                    run = subprocess.run(
                        command + ["mcp", "--profile", str(profile), "--backups", str(Path(temp) / "backups")],
                        input="".join(json.dumps(m) + "\n" for m in messages).encode(),
                        capture_output=True,
                        cwd=ROOT,
                        timeout=60,
                    )
                    replies = [json.loads(line) for line in run.stdout.splitlines()]
                    self.assertEqual([reply["id"] for reply in replies], [1, 2], run.stderr.decode(errors="replace"))
                    hero = json.loads(replies[1]["result"]["content"][0]["text"])
                    self.assertEqual(hero["name"], "Ranger Deluxe")

    @staticmethod
    def _commands():
        commands = [[sys.executable, "-m", "dungeons2_editor"]]
        # The .exe is a windowed app; pythonw.exe runs the same entry script the same way.
        windowed = Path(sys.executable).with_name("pythonw.exe")
        if os.name == "nt" and windowed.is_file():
            commands.append([str(windowed), str(ROOT / "mcd2_save_editor.py")])
        return commands


if __name__ == "__main__":
    unittest.main()
