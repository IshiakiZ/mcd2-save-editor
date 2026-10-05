"""The tests run against pinned copies of the item list and the effects list (tests/data), so that the editor
learning more item IDs and effects doesn't change which ones they see as confirmed, guessed or unnamed.
tests/test_catalog.py checks the real lists."""

from pathlib import Path

from dungeons2_editor import hero

REAL_ITEMS_FILE = hero.GAME_ITEMS_FILE
REAL_EFFECTS_FILE = hero.EFFECTS_FILE
PINNED_ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"
PINNED_EFFECTS_FILE = PINNED_ITEMS_FILE.with_name("effects.json")


def use_item_list(path: Path) -> None:
    hero.GAME_ITEMS_FILE = path
    for cached in (hero.game_items, hero._game_items_by_id, hero._uniques_by_id):
        cached.cache_clear()


def use_effect_list(path: Path) -> None:
    hero.EFFECTS_FILE = path
    hero.effect_book.cache_clear()


use_item_list(PINNED_ITEMS_FILE)
use_effect_list(PINNED_EFFECTS_FILE)
