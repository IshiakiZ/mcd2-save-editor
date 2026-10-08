"""The tests run against pinned copies of the item list, the effects list and the list of the world (tests/data),
so that the editor learning more item IDs, effects and places doesn't change which ones they see as confirmed,
guessed, unnamed or new. tests/test_catalog.py and tests/test_world.py check the real lists."""

from pathlib import Path

from dungeons2_editor import hero, world

REAL_ITEMS_FILE = hero.GAME_ITEMS_FILE
REAL_EFFECTS_FILE = hero.EFFECTS_FILE
REAL_WORLD_FILE = world.WORLD_FILE
PINNED_ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"
PINNED_EFFECTS_FILE = PINNED_ITEMS_FILE.with_name("effects.json")
PINNED_WORLD_FILE = PINNED_ITEMS_FILE.with_name("world.json")


def use_item_list(path: Path) -> None:
    hero.GAME_ITEMS_FILE = path
    for cached in (hero.game_items, hero._game_items_by_id, hero._uniques_by_id):
        cached.cache_clear()


def use_effect_list(path: Path) -> None:
    hero.EFFECTS_FILE = path
    hero.effect_book.cache_clear()


def use_world_list(path: Path) -> None:
    world.WORLD_FILE = path
    world.known.cache_clear()


use_item_list(PINNED_ITEMS_FILE)
use_effect_list(PINNED_EFFECTS_FILE)
use_world_list(PINNED_WORLD_FILE)
