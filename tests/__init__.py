"""The tests run against a pinned copy of the item list (tests/data/items.json), so that the editor learning more
item IDs doesn't change which items they see as confirmed, guessed or unnamed. tests/test_catalog.py checks the
real list."""

from pathlib import Path

from dungeons2_editor import hero

REAL_ITEMS_FILE = hero.GAME_ITEMS_FILE
PINNED_ITEMS_FILE = Path(__file__).resolve().parent / "data" / "items.json"


def use_item_list(path: Path) -> None:
    hero.GAME_ITEMS_FILE = path
    for cached in (hero.game_items, hero._game_items_by_id, hero._uniques_by_id):
        cached.cache_clear()


use_item_list(PINNED_ITEMS_FILE)
