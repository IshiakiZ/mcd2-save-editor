"""Walking, describing, editing and comparing decoded save documents.

A path is a tuple of dict keys (str) and list indices (int) from the root.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Iterator


class _Missing:
    def __repr__(self) -> str:
        return "(none)"


MISSING: Any = _Missing()

# Fields whose value names a list item better than its position does.
_LABEL_FIELDS = ("name", "tagName", "displayName", "AttributeName", "QuestName", "TaskName", "TypeTag")


def children(value: Any) -> Iterator[tuple[str | int, Any]]:
    if isinstance(value, dict):
        yield from value.items()
    elif isinstance(value, list):
        yield from enumerate(value)


def walk(value: Any, path: tuple = ()) -> Iterator[tuple[tuple, str | int, Any]]:
    """Yield (path, key, value) for every node below ``value``, depth first."""
    for key, child in children(value):
        child_path = path + (key,)
        yield child_path, key, child
        yield from walk(child, child_path)


def get_at(document: Any, path: tuple) -> Any:
    for key in path:
        document = document[key]
    return document


def set_at(document: Any, path: tuple, value: Any) -> None:
    if not path:
        raise ValueError("cannot replace the whole document")
    get_at(document, path[:-1])[path[-1]] = value


def label(key: str | int, value: Any) -> str:
    if isinstance(key, int):
        if isinstance(value, dict):
            named = value.get("ItemData") if isinstance(value.get("ItemData"), dict) else value
            for field in _LABEL_FIELDS:
                if isinstance(named.get(field), str) and named[field]:
                    return named[field]
        return f"#{key + 1}"
    return str(key)


def describe_path(document: Any, path: tuple) -> str:
    parts = []
    node = document
    for key in path:
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            node = MISSING
        parts.append(label(key, node))
    return " › ".join(parts) or "(whole file)"


def format_value(value: Any) -> str:
    if value is MISSING:
        return "(none)"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, dict):
        return f"{{{len(value)} fields}}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return str(value)


def type_name(value: Any) -> str:
    if isinstance(value, dict):
        return "group"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def parse_input(text: str, original: Any) -> Any:
    """Turn what the user typed into a value of the same kind as ``original``."""
    if isinstance(original, bool):
        lowered = text.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError("Enter true or false.")
    if isinstance(original, (int, float)):
        cleaned = text.strip()
        if re.fullmatch(r"[+-]?\d+", cleaned):
            return int(cleaned)
        try:
            number = float(cleaned)
        except ValueError:
            raise ValueError(f"{text!r} is not a number.") from None
        if not math.isfinite(number):
            raise ValueError("Enter a finite number.")
        return number
    if original is None:
        cleaned = text.strip()
        if cleaned in ("", "null"):
            return None
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return text
    return text


def _same(old: Any, new: Any) -> bool:
    if isinstance(old, bool) or isinstance(new, bool):
        return type(old) is type(new) and old == new
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return old == new
    return type(old) is type(new) and old == new


def diff(old: Any, new: Any, path: tuple = ()) -> list[tuple[tuple, Any, Any]]:
    """List (path, old value, new value) for every value that differs."""
    if isinstance(old, dict) and isinstance(new, dict):
        keys = list(old) + [key for key in new if key not in old]
        changes = []
        for key in keys:
            changes += diff(old.get(key, MISSING), new.get(key, MISSING), path + (key,))
        return changes
    if isinstance(old, list) and isinstance(new, list):
        changes = []
        for position in range(max(len(old), len(new))):
            before = old[position] if position < len(old) else MISSING
            after = new[position] if position < len(new) else MISSING
            changes += diff(before, after, path + (position,))
        return changes
    return [] if _same(old, new) else [(path, old, new)]
