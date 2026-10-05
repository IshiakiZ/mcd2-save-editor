"""Turns the source into another edition of the editor before it's built.

    python tools/make_edition.py nexus     the edition for Nexus Mods, which never goes online
    python tools/make_edition.py github    back to the edition on GitHub

Nexus Mods doesn't host programs that go online, an updater included, so the release workflow builds the
editor a second time with dungeons2_editor/edition.py rewritten by this. Run from the repository root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

EDITION_FILE = Path(__file__).resolve().parent.parent / "dungeons2_editor" / "edition.py"
EDITIONS = {"github": (True, "GitHub"), "nexus": (False, "Nexus Mods")}


def as_edition(source: str, edition: str) -> str:
    """``source`` (the text of edition.py) with ONLINE and NAME set for ``edition``."""
    online, name = EDITIONS[edition]
    changed, first = re.subn(r"(?m)^ONLINE = (True|False)\b", f"ONLINE = {online}", source)
    changed, second = re.subn(r'(?m)^NAME = "[^"]*"', f'NAME = "{name}"', changed)
    if (first, second) != (1, 1):
        raise ValueError("edition.py doesn't set ONLINE and NAME once each any more")
    return changed


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in EDITIONS:
        print(__doc__)
        return 2
    EDITION_FILE.write_text(as_edition(EDITION_FILE.read_text(encoding="utf-8"), argv[0]), encoding="utf-8", newline="\n")
    online, name = EDITIONS[argv[0]]
    print(f"{EDITION_FILE.name}: the {name} edition ({'goes online for updates and pictures' if online else 'never goes online'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
