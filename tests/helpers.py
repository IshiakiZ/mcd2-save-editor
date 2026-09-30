"""Builds small fake save folders for tests.

The bytes are packed by hand here, independently of wgs.py, following the
layout of a real Minecraft Dungeons II containers.index.
"""

from __future__ import annotations

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
