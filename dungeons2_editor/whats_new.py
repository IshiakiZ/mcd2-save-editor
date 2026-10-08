"""What's new: the changes in each version, shown in the editor the first time a new version opens.

The notes are the ones on each release's page (``dungeons2_editor/data/release-notes.md``, which ships with
the editor): a ``## What's new in 1.15.0`` heading for each version, newest first, and the changes under it as a
list. This reads them, picks the versions someone hasn't seen yet, and shows them in a window. Nothing is
fetched: an edition that never goes online shows the same notes.

They are short on purpose, the main things in a line each, for the newest version and the two before it.
Every version, with the detail, is in ``CHANGELOG.md``.
"""

from __future__ import annotations

import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from . import paths
from .game_style import match_title_bar
from .layout import fit_to_contents, scaled_size

NOTES_FILE = paths.resource("dungeons2_editor/data/release-notes.md")
MOST_VERSIONS = 3  # versions the notes hold, and so the most shown at once; someone who skipped more gets the newest
_HEADING = re.compile(r"^## What's new in (\d+(?:\.\d+)*)\b(.*)$")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^()\s]|\([^()\s]*\))+\)")  # [text](address): the text is kept
_MARKED = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


@dataclass(frozen=True)
class Note:
    """One change: a paragraph, or an entry in a list (``depth`` 1 for an entry under another entry)."""

    text: str
    bullet: bool = True
    depth: int = 0


@dataclass(frozen=True)
class Version:
    version: str
    title: str  # the heading as written: "What's new in 1.2.3: important fix, please update"
    notes: tuple[Note, ...]


def _order(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def parse(text: str) -> list[Version]:
    """The versions in the notes, in the order they're written (newest first). Anything under another kind of
    heading (how to download, say) isn't a version's notes and is left out."""
    versions: list[Version] = []
    notes: list[Note] | None = None
    open_note: list[str] | None = None  # the lines of the note being read
    shape = (True, 0)

    def close() -> None:
        nonlocal open_note
        if open_note and notes is not None:
            notes.append(Note(" ".join(open_note), *shape))
        open_note = None

    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading or line.startswith("#"):
            close()
            notes = None
            if heading:
                notes = []
                versions.append(Version(heading.group(1), line[3:].strip(), ()))
                versions[-1] = (versions[-1], notes)  # type: ignore[assignment]
            continue
        if notes is None:
            continue
        stripped = line.strip()
        if not stripped:
            close()
        elif stripped.startswith("- "):
            close()
            shape = (True, min(1, (len(line) - len(line.lstrip())) // 2))
            open_note = [stripped[2:].strip()]
        elif open_note is not None and (line.startswith(" ") or not shape[0]):
            open_note.append(stripped)  # a list entry goes on, indented, and a paragraph goes on until a blank line
        else:
            close()
            shape = (False, 0)
            open_note = [stripped]
    close()
    return [Version(version.version, version.title, tuple(found)) for version, found in versions]  # type: ignore[misc]


def load(path: Path = NOTES_FILE) -> list[Version]:
    """The notes that came with this copy of the editor; none if the file isn't there."""
    try:
        return parse(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return []


def unseen(versions: list[Version], seen: str | None, current: str, most: int = MOST_VERSIONS) -> list[Version]:
    """The notes to show someone who last opened version ``seen`` and now has ``current``, newest first: every
    version in between, the newest ``most`` of them at the outside. Someone opening the editor for the first
    time (``seen`` is None) gets the notes of the version they have, and nobody gets notes for a version newer
    than the one they're running."""
    try:
        now = _order(current)
        reached = [version for version in versions if _order(version.version) <= now]
        if seen is None:
            return reached[:1]
        return [version for version in reached if _order(version.version) > _order(seen)][:most]
    except ValueError:  # a version that isn't numbers, in the settings or the notes: show the newest notes there are
        return versions[:1]


def runs(text: str) -> list[tuple[str, str]]:
    """A note's text as (text, how it's shown) pieces: "" for plain, "bold" for **this** and "code" for `this`.
    A link is shown by its words alone."""
    text = _LINK.sub(lambda match: match.group(1), text)
    pieces = []
    for part in _MARKED.split(text):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            pieces.append((part[2:-2].replace("`", ""), "bold"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            pieces.append((part[1:-1], "code"))
        elif part:
            pieces.append((part, ""))
    return pieces


def heading_for(versions: list[Version]) -> str:
    if not versions:
        return "What's new"
    if len(versions) == 1:
        return f"What's new in {versions[0].version}"
    return f"What's new in {versions[0].version}, and back to {versions[-1].version}"


class WhatsNewDialog(tk.Toplevel):
    """The notes of one version or a few, to read and close. It doesn't stop you using the editor meanwhile."""

    def __init__(self, parent: tk.Misc, versions: list[Version]):
        super().__init__(parent)
        self.title("What's new")
        self.transient(parent)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        base = tkfont.nametofont("TkDefaultFont", root=self)
        size = abs(int(base.cget("size"))) or 9
        self.fonts = {
            "title": tkfont.Font(self, family=base.cget("family"), size=size + 5, weight="bold"),
            "version": tkfont.Font(self, family=base.cget("family"), size=size + 2, weight="bold"),
            "bold": tkfont.Font(self, family=base.cget("family"), size=size, weight="bold"),
            "code": tkfont.Font(self, family=tkfont.nametofont("TkFixedFont", root=self).cget("family"), size=size),
        }
        ttk.Label(frame, text=heading_for(versions), font=self.fonts["title"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.text = tk.Text(
            frame, wrap="word", width=92, height=22, relief="flat", borderwidth=0, highlightthickness=0, padx=12, pady=8, cursor="arrow", takefocus=False,
            font=base,  # a Text widget writes in a typewriter's letters unless told otherwise
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self._write(versions)
        self.text.configure(state="disabled")
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.close_button = ttk.Button(buttons, text="Close", style="Accent.TButton", command=self.destroy)
        self.close_button.pack(side="right")
        fit_to_contents(self, *scaled_size(self, 760, 520))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self.destroy())
        self.close_button.focus_set()

    def _write(self, versions: list[Version]) -> None:
        text, gap = self.text, self.fonts["bold"].metrics("linespace")
        hang = self.fonts["bold"].measure("•  ")
        text.tag_configure("version", font=self.fonts["version"], spacing1=gap, spacing3=gap // 3)
        text.tag_configure("first", spacing1=0)
        text.tag_configure("bold", font=self.fonts["bold"])
        text.tag_configure("code", font=self.fonts["code"])
        text.tag_configure("para", spacing3=gap // 3)
        for depth in (0, 1):
            text.tag_configure(f"bullet{depth}", lmargin1=hang * depth * 2, lmargin2=hang * (depth * 2 + 1), spacing3=gap // 3)
        if not versions:
            text.insert("end", "The notes that come with the editor weren't found.", ("para",))
        for number, version in enumerate(versions):
            if len(versions) > 1:  # a single version is named by the window's own heading
                text.insert("end", f"Version {version.version}\n", ("version",) + (("first",) if number == 0 else ()))
            for note in version.notes:
                shape = f"bullet{note.depth}" if note.bullet else "para"
                if note.bullet:
                    text.insert("end", "•  " if note.depth == 0 else "–  ", (shape,))
                for piece, how in runs(note.text):
                    text.insert("end", piece, (shape, how) if how else (shape,))
                text.insert("end", "\n", (shape,))

    def shown_text(self) -> str:
        return self.text.get("1.0", "end").strip()
