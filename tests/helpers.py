"""Builds small fake save folders for tests.

The bytes are packed by hand here, independently of wgs.py, following the
layout of a real Minecraft Dungeons II containers.index.
"""

from __future__ import annotations

import copy
import json
import struct
import uuid
from pathlib import Path

PROFILE_NAME = "0009ABCDEF012345_000000000000000000000000DEADBEEF"
PACKAGE = "Microsoft.MinecraftDungeons2_8wekyb3d8bbwe!AppMinecraftDungeonsIIShipping"
ACCOUNT = "00000000-0000-4000-8000-000000000000"
BASE_TIME = 0x01DD5117B11327C0

# Shaped like the start of a real GlobalSaveDataDefault blob (made-up ID).
SETTINGS_TEXT = (
    '{"blobs" :[{"masterVolume":60,"leftDeadzone":0.34999999999999998,"ping":24.674900054931641,'
    '"backgroundAudio":true,"audioOutputDevice":"Speakers","name":"Audio","version":0},'
    '{"activeCharacterId":"00000000-0000-1000-8000-000000000001","deletedCharacterIds":[],'
    '"unlockedTutorials":[{"tagName":"SW.UI.TutorialLog.Basic.Movement"}],"name":"General","version":0}]}'
)
HERO_TEXT = '{"blobs" :[{"emeralds":120,"level":7,"heroName":"Zoë","name":"Hero","version":0}]}'


def hero_item(tag, power=1, rarity="Common", equipped="None", slot="None", seed=1, roll=0.218016, unseen=True, picked_up=1790802481):
    """An inventory entry shaped like the ones in a real hero save."""
    return {
        "ItemData": {
            "TypeTag": tag,
            "RarityTag": "SW.Rarity." + rarity,
            "Effects": [],
            "ItemProgression": {"CurrentLevel": 0, "CurrentXP": 0, "ItemLevels": []},
            "GeneratorData": {
                "GenesisRandomSeed": seed,
                "PowerGeneratorValues": {
                    "PlayerLevel": 1,
                    "AreaThreatLevel": 1,
                    "RecommendedThreatLevel": 1,
                    "ThreatSliderOffset": 0,
                    "ItemPowerMin": 1,
                    "ItemPowerMax": 3,
                    "RNGRoll": roll,
                    "ItemPower": power,
                    "ItemPowerOriginal": power,
                },
            },
            "DynamicPropertyTags": ["SW.Item.Property.Dynamic.Unseen"] if unseen else [],
            "TargetSlotOverride": slot,
            "PickupTimestamp": picked_up,
            "EffectRerolls": 0,
        },
        "StackCount": 1,
        "EquippedSlot": equipped,
        "MerchantItemSold": False,
        "MerchantDiscount": 0,
    }


def talisman_item(tag, effect, strengths=(1.2, 1.25, 1.35), level=0, xp=0, **more):
    """A talisman shaped like one the game handed over: no rarity or power, and its effect at each of its levels."""
    entry = hero_item(tag, power=-1, rarity="None", **more)
    levels = [
        {
            "LevelEffects": [
                {
                    "TypeTag": f"SW.Effect.{effect}",
                    "Intensity": strength,
                    "Quality": 0,
                    "EnchantmentPointsInvested": 0,
                    "GeneratorData": {"GeneratorParentTemplate": f"SW.EffectTemplate.{effect}.{numeral}", "Locked": False},
                }
            ],
            "LevelTags": [],
        }
        for numeral, strength in zip(("I", "II", "III"), strengths)
    ]
    data = entry["ItemData"]
    data["Effects"] = [{"TypeTag": "SW.Item.Effect.Upgradable", "EffectsInThisBatch": copy.deepcopy(levels[level]["LevelEffects"])}]
    data["ItemProgression"] = {"CurrentLevel": level, "CurrentXP": xp, "ItemLevels": levels}
    data["GeneratorData"]["PowerGeneratorValues"].update(ItemPowerMax=11, RNGRoll=0, ItemPowerOriginal=0)
    return entry


def book_item(tag, **more):
    """An enchantment book shaped like one the game handed over: no rarity, no power, no effects and no levels."""
    entry = hero_item(tag, power=-1, rarity="None", **more)
    entry["ItemData"]["GeneratorData"]["PowerGeneratorValues"].update(ItemPowerMax=11, RNGRoll=0, ItemPowerOriginal=0)
    return entry


def rolled_effect(name, strength, tier="I", template=None):
    """One of the effects the game rolls on a weapon, armor piece or artifact, as a real save holds it."""
    return {
        "TypeTag": f"SW.Effect.{name}",
        "Intensity": strength,
        "Quality": 0,
        "EnchantmentPointsInvested": 0,
        "GeneratorData": {"GeneratorParentTemplate": f"SW.EffectTemplate.{template or name}.{tier}", "Locked": False},
    }


def enchantment_effect(name, strength, tier="I", points=3):
    """An enchantment as a real save holds one the Enchantsmith put on."""
    return {
        "TypeTag": f"SW.Enchantment.{name}",
        "Intensity": strength,
        "Quality": 0,
        "EnchantmentPointsInvested": points,
        "GeneratorData": {"GeneratorParentTemplate": f"SW.Enchantment.{name}.{tier}", "Locked": False},
    }


def rolled(*effects):
    """The batch an item's rolled effects are saved in."""
    return {"TypeTag": "SW.Item.Effect.Rerollable", "EffectsInThisBatch": list(effects)}


def enchanted(effect):
    """The batch an item's enchantment is saved in."""
    return {"TypeTag": "SW.Item.Effect.Enchantment", "EffectsInThisBatch": [effect]}


def hero_save(online=False, emeralds=55, level=1):
    """A hero save shaped like a real Character<id> container (made-up ID)."""
    return {
        "SerializeMeta": {"InternalVersion": 0, "HardFormat": "FCharacterSaveV1", "SoftVersion": 5, "FormatHash": 1764133460},
        "CharacterSaveV1": {
            "MetaData": {
                "CharacterId": "00000000-0000-1000-8000-000000000002",
                "Created": 0,
                "GameDataUpdated": 639263000000000000,
                "IsOnline": online,
                "IsGuest": False,
                "Level": level,
                "PowerLevel": 1,
                "CurrentLocation": "SW.Area.Town",
                "ReleaseToggles": ["R1", "R2"],
                "CurrentDifficulty": "None",
            },
            "Ability": {
                "Attributes": [
                    {"AttributeName": "VillageMerchantUpgradeLevel", "CurrentValue": 1},
                    {"AttributeName": "Emeralds", "CurrentValue": emeralds},
                    {"AttributeName": "Level", "CurrentValue": level},
                    {"AttributeName": "XP", "CurrentValue": 845.5},
                    {"AttributeName": "MysteryStat", "CurrentValue": 0.5},
                ],
                "ProgressionTags": [],
            },
            "Cosmetics": {"Cosmetics": {"SW.Skin": {"TypeTag": "SW.Skin.RangerDeluxe"}}},
            "Inventory": {
                "Entries": [
                    hero_item("SW.Item.MysticHelmet", power=1, seed=1894972666, picked_up=1790802400),
                    hero_item("SW.Item.CurvedGreatsword", slot="SW.ItemSlot.Inventory.VillageMerchant.Tier0", seed=4023525344, roll=0.700214),
                    hero_item("SW.Item.Longbow", power=2, rarity="Rare", seed=3312656623, picked_up=1790802500),
                    hero_item("SW.Item.Sword", equipped="SW.ItemSlot.Equipment.MeleeWeapon", seed=3506801006, unseen=False),
                    hero_item("SW.Item.Cosmetic.Cape.Hero", power=-1, seed=4269766170, unseen=False),
                ]
            },
            "LootProgression": {"DiscoveredLoot": ["SW.Item.Sword", "SW.Item.Bow", "SW.Item.Cosmetic.Cape.Hero"]},
            "CollectionsStats": {"CollectedWeaponsCommon": ["SW.Item.Sword", "SW.Item.Axe"]},
        },
    }


def hero_with_a_world() -> dict:
    """A hero that has been somewhere: a camp four squares across and three down, a meadow, three doors, two
    minecart stations, quests at every stage and the game's counts."""
    document = hero_save()
    body = document["CharacterSaveV1"]
    body["MetaData"]["CurrentLocation"] = "SW.Area.Forest.A1"

    def quest(name, state, *steps):
        return {"QuestName": name, "State": state, "TaskData": [{"TaskName": f"{name}_E0{number}", "State": step, "PartialProgress": 0} for number, step in enumerate(steps, start=1)]}

    body["quest"] = {"FocusedQuestId": "CA04", "Quests": [quest("CA01", "Completed", "Completed"), quest("CA04", "Active", "Completed", "Active"), quest("FOa1_S10_A", "Available", "NotSet")]}
    body["WorldExploration"] = {
        "DiscoveredMinecartStationTags": ["SW.MinecartStation.Town", "SW.MinecartStation.ForestA1.Outpost"],
        "LastMinecartStation": "SW.MinecartStation.ForestA1.Outpost",
        "SavedCutsceneTags": ["SW.UI.Cutscene.Cutscenes.CS01"],
        "ActivatedGimmickTags": [],
        "DiscoveredDungeonDoors": [
            {"DoorId": "SW.Doorway.Camp.Docks", "MarkerType": 7, "Location": {"X": 4800, "Y": 8000, "Z": 0}},
            {"DoorId": "SW.Doorway.ForestA1.Dungeon.1", "MarkerType": 8, "Location": {"X": 1600, "Y": 1600, "Z": 0}},
            {"DoorId": "SW.Doorway.MeadowR1.ForestA1", "MarkerType": 7, "Location": {"X": 104000, "Y": 104000, "Z": 0}},
        ],
        "SavedFogOfWarExploration": {"Items": [
            # Line by line from the top, which is the far side in X: nothing, then three squares, then one.
            {"Tag": "SW.Region.Camp", "WorldPosition": {"X": 0, "Y": 0}, "Size": {"X": 4, "Y": 3}, "Data": [0, 0, 0, 0, 0, 90, 255, 40, 0, 0, 120, 0]},
            {"Tag": "SW.Area.Meadow.R1", "WorldPosition": {"X": 1000, "Y": 1000}, "Size": {"X": 2, "Y": 2}, "Data": [0, 7, 0, 0]},
        ]},
        "SavedActorStates": [],
    }
    body["Achievements"] = {
        "QuestAchievements": {
            "SW.Achievements.CompleteArriveInBraveHavenQuest": {"bCompleted": True}, "SW.Achievements.CompleteWobbleRunQuest": {"bCompleted": False},
            "SW.Achievements.CompleteCarapaceSideQuest": {"bCompleted": False},
        },
        "BoolAchievements": {"SW.Achievements.EquipAUniqueItem": {"bCompleted": True}},
        "CollectionAchievements": {"SW.Achievements.DiscoverAllMinecartStations": {"CollectedTags": ["SW.MinecartStation.Town", "SW.MinecartStation.ForestA1.Outpost"]}},
        "CountAchievements": {"SW.Achievements.Open100Chests": {"Count": 5}},
    }
    return document


def recordings_of_a_world() -> dict:
    """What the play recorder's recordings showed of that hero, as their atlas has it: where a station turned up,
    two chests opened in one go, and one more while nothing was recording."""
    place = {"area": "SW.Area.Forest.A1", "near": [48, 48], "region": "SW.Region.Camp", "recording": "2026-10-01_10-00-00", "snapshot": "0002.json"}
    return {"format": 3, "heroes": {"00000000-0000-1000-8000-000000000002": {
        "saves": 3,
        "found_at": {"minecart station SW.MinecartStation.ForestA1.Outpost": place},
        "chests": [{"opened": 2, "count": 4, **place}, {"opened": 1, "count": 5, "area": None, "near": None, "region": None, "recording": "2026-10-02_10-00-00", "snapshot": "0001.json"}],
    }}}


def hero_save_text(**kwargs) -> str:
    """Written the way the game writes hero saves: compact, numbers in shortest form."""
    return json.dumps(hero_save(**kwargs), separators=(",", ":"), ensure_ascii=False)


def text_field(value: str) -> bytes:
    return struct.pack("<I", len(value)) + value.encode("utf-16-le")


def shift_encode(text: str) -> bytes:
    return bytes((byte - 1) & 0xFF for byte in text.encode("utf-8"))


def manifest_bytes(blobs: list[tuple[str, uuid.UUID, uuid.UUID]]) -> bytes:
    out = struct.pack("<II", 4, len(blobs))
    for name, cloud, local in blobs:
        out += name.encode("utf-16-le").ljust(128, b"\0") + cloud.bytes_le + local.bytes_le
    return out


def index_bytes(entries: list[dict], sync: int = 3) -> bytes:
    out = struct.pack("<IQ", 14, len(entries)) + text_field(PACKAGE)
    out += struct.pack("<QI", BASE_TIME, sync) + text_field(ACCOUNT) + struct.pack("<Q", 0x10000000)
    for entry in entries:
        out += text_field(entry["name"]) + text_field(entry["name"]) + text_field(entry["etag"])
        out += struct.pack("<BI", entry["revision"], entry["sync"]) + entry["folder"].bytes_le
        out += struct.pack("<QQQ", entry["mtime"], 0, entry["size"])
    return out


def make_profile(root: Path, containers: dict[str, bytes], revisions: dict[str, int] | None = None, sync: dict[str, int] | None = None) -> Path:
    """Create a save folder with one "Data" blob per container."""
    profile = Path(root) / PROFILE_NAME
    profile.mkdir(parents=True)
    entries = []
    for number, (name, data) in enumerate(containers.items()):
        folder = uuid.uuid4()
        blob = uuid.uuid4()
        revision = (revisions or {}).get(name, 4)
        folder_path = profile / folder.hex.upper()
        folder_path.mkdir()
        (folder_path / f"container.{revision}").write_bytes(manifest_bytes([("Data", blob, blob)]))
        (folder_path / blob.hex.upper()).write_bytes(data)
        entries.append(
            {
                "name": name,
                "etag": f'"0x8DE00000000{number:04X}"',
                "revision": revision,
                "sync": (sync or {}).get(name, 1),
                "folder": folder,
                "mtime": BASE_TIME + number,
                "size": len(data),
            }
        )
    (profile / "containers.index").write_bytes(index_bytes(entries))
    return profile


def snapshot(folder: Path) -> dict[str, bytes]:
    """Every file under ``folder`` by relative path."""
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(Path(folder).rglob("*")) if path.is_file()}
