"""What you've told the editor about items it doesn't know: the names you gave them.

They're kept on this PC (item-names.json, next to the backups) and only leave it if you use Share item IDs,
which puts them in the report for you to post. Pictures you paste go in the icons folder (icons.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import data_dir

NAMES_FILE = data_dir() / "item-names.json"


def load_names(path: Path = NAMES_FILE) -> dict[str, str]:
    """Item ID -> the name you gave it. Empty if there's no file or it can't be read."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(tag): str(name).strip() for tag, name in data.items() if isinstance(name, str) and name.strip()}


def save_names(names: dict[str, str], path: Path = NAMES_FILE) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(names.items())), indent=2, ensure_ascii=False), encoding="utf-8")
