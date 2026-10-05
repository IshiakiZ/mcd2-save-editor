"""Which edition of the editor this is.

The download from GitHub goes online for three things: when it opens it asks GitHub whether a newer version
is out, Update downloads that version, and Get item pictures downloads pictures from the Minecraft Wiki.
Nexus Mods doesn't host programs that go online, an updater included, so the edition built for it has
ONLINE off and does none of the three: it never connects to anything, and its new versions are on Nexus
Mods. The release workflow makes that edition by building once more with this file rewritten
(tools/make_edition.py).
"""

ONLINE = True  # False in the edition for Nexus Mods
NAME = "GitHub"  # where this edition is downloaded from, and where its new versions are


class OfflineEdition(OSError):
    """Something that needs the internet was asked of the edition that never goes online."""


def offline_note(what: str) -> str:
    """Why this edition can't do ``what`` ('download pictures', 'look for updates')."""
    return f"This edition of the editor, from {NAME}, never goes online, so it doesn't {what}."


def require_online(what: str) -> None:
    """Stop here in the edition that never goes online. Everything that opens a connection calls this first."""
    if not ONLINE:
        raise OfflineEdition(offline_note(what))
