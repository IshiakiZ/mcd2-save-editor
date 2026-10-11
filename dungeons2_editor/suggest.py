"""Suggest something: a place to leave an idea for the editor, or to say what it gets wrong.

It works the way Share item IDs does. You write, and the editor hands what you wrote to your own browser as a
GitHub issue that's filled in and waiting for you to send, or puts it on the clipboard to paste somewhere else. The
editor sends nothing itself, so there's nothing here for the edition that never goes online to leave out.

With the suggestion goes a line about the editor it was written in (its version, which kind of saves are open, the
mode and the look), which you can untick. Nothing of your saves is in it.
"""

from __future__ import annotations

import platform
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import font as tkfont
from tkinter import ttk

from . import edition, share_ids
from .game_style import LOOKS, match_title_bar
from .layout import fit_to_contents, scaled_size, text_width

ISSUE_TEMPLATE = "suggestion.yml"
TITLE = "Suggestion"
MOST_TITLE = 70  # characters of a suggestion's first line in the issue's title
MOST_TEXT = 60_000  # characters: a GitHub issue holds 65,536, and the form adds a little of its own
SIZE = (640, 470)  # on a display at 100%
PASTE_HERE = "(paste your suggestion here: it's on your clipboard, so press Ctrl+V)"
INTRO = "Have an idea for the editor, or is something not working the way you'd expect? Write it here, in your own words."
HOW = (
    "Open a GitHub issue… takes it to the editor's page on GitHub in your browser, filled in: press the green button there to "
    "send it (you need a free GitHub account). Copy puts it on the clipboard, to paste anywhere else. The editor sends nothing itself."
)
SAVES = {"steam": "saves from Steam", "folders": "a folder for each save", "xbox": "saves from the Xbox app"}
SYSTEMS = {"Windows": "Windows", "Darwin": "a Mac", "Linux": "Linux"}


def setup_line(version: str, layout: str | None = None, advanced: bool = False, look: str | None = None) -> str:
    """The line about the editor a suggestion was written in: nothing of the saves, and nothing of the PC but which
    system it runs."""
    parts = [f"Editor {version} ({edition.NAME} edition)"]
    if layout in SAVES:
        parts.append(SAVES[layout])
    parts.append("Advanced mode" if advanced else f"Simple mode, {LOOKS[look]} look" if look in LOOKS else "Simple mode")
    system = SYSTEMS.get(platform.system())
    if system:
        parts.append(system)
    return ", ".join(parts)


def title_of(text: str) -> str:
    """An issue's title for a suggestion: its first line, cut at a word if it runs long."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first) > MOST_TITLE:
        first = first[:MOST_TITLE].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
    return f"{TITLE}: {first}" if first else TITLE


def issue_url(text: str, setup: str, version: str, title: str | None = None) -> str:
    """The address that opens the suggestion form on GitHub with this suggestion in it, under a title made from
    its first line unless one is given."""
    query = {"template": ISSUE_TEMPLATE, "title": title or title_of(text), "suggestion": text}
    if setup:
        query["setup"] = setup
    query["version"] = version
    return share_ids.ISSUE_URL + "?" + urllib.parse.urlencode(query)


def to_copy(text: str, setup: str) -> str:
    """A suggestion as it goes on the clipboard: what was written, and under it the line about the editor."""
    return text + (f"\n\n({setup})" if setup else "")


class SuggestDialog(tk.Toplevel):
    """A box to write a suggestion in, and two ways to send it on. ``draft`` is what was written the last time
    the window was open; ``on_close`` is told what's in the box as the window closes, to keep for the next time."""

    def __init__(self, parent: tk.Misc, version: str, setup: str = "", draft: str = "", on_close=None):
        super().__init__(parent)
        self.version = version
        self.setup = setup
        self.on_close = on_close
        self.title("Suggest something")
        self.transient(parent)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        wrap = text_width(self, 84)
        ttk.Label(frame, text=INTRO, wraplength=wrap, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        self.text = tk.Text(
            frame, height=10, width=76, wrap="word", undo=True, padx=6, pady=6,
            font=tkfont.nametofont("TkDefaultFont", root=self),  # a Text widget writes in a typewriter's letters unless told otherwise
        )
        self.text.insert("1.0", draft)
        self.text.edit_reset()  # what was there from the last time isn't something to undo
        self.text.edit_modified(False)
        self.text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        down = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        down.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        self.text.configure(yscrollcommand=down.set)
        # Whichever way the words get there (typed, pasted, cut, undone): the box says when what's in it changes.
        self.text.bind("<<Modified>>", self._changed)
        # The line about the editor is yours to leave out.
        self.setup_var = tk.BooleanVar(value=bool(setup))
        self.setup_box = ttk.Checkbutton(frame, text="Add which editor this is:", variable=self.setup_var)
        if setup:
            self.setup_box.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
            ttk.Label(frame, text=setup, style="Muted.TLabel", wraplength=wrap, justify="left").grid(row=3, column=0, columnspan=2, sticky="w", padx=(text_width(self, 3), 0))
        ttk.Label(frame, text=HOW, style="Muted.TLabel", wraplength=wrap, justify="left").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.message = tk.StringVar()
        ttk.Label(buttons, textvariable=self.message, style="Success.TLabel").pack(side="left")
        self.close_button = ttk.Button(buttons, text="Close", command=self.destroy)
        self.close_button.pack(side="right")
        self.copy_button = ttk.Button(buttons, text="Copy", command=self.copy)
        self.copy_button.pack(side="right", padx=6)
        self.issue_button = ttk.Button(buttons, text="Open a GitHub issue…", style="Accent.TButton", command=self.open_issue)
        self.issue_button.pack(side="right")
        self._update()
        fit_to_contents(self, *scaled_size(self, *SIZE))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.text.focus_set()

    def suggestion(self) -> str:
        """What's written in the box, without the empty lines around it."""
        return self.text.get("1.0", "end").strip()

    def about_editor(self) -> str:
        """The line about the editor, if it's ticked to go along."""
        return self.setup if self.setup_var.get() else ""

    def _changed(self, _event: object = None) -> None:
        if self.text.edit_modified():
            self._update()
            self.text.edit_modified(False)  # so that the next change is told of too

    def _update(self) -> None:
        """The two ways to send it on are there once something is written."""
        state = ["!disabled"] if self.suggestion() else ["disabled"]
        self.copy_button.state(state)
        self.issue_button.state(state)

    def copy(self) -> None:
        text = self.suggestion()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(to_copy(text, self.about_editor()))
        self.message.set("Copied.")

    def open_issue(self) -> None:
        text = self.suggestion()
        if not text:
            return
        if len(text) > MOST_TEXT:
            self.message.set("That's more than a GitHub issue holds. Shorten it a little, or send it in two.")
            return
        link = issue_url(text, self.about_editor(), self.version)
        if len(link) <= share_ids.MAX_LINK:
            webbrowser.open(link)
            self.message.set("Opened in your browser: press the green button there to send it.")
            return
        # Too long to hand over in a link: it goes on the clipboard, and the page opens ready for it.
        self.clipboard_clear()
        self.clipboard_append(text)
        webbrowser.open(issue_url(PASTE_HERE, self.about_editor(), self.version, title_of(text)))
        self.message.set("Copied, and the page is open: paste your suggestion into its first box (Ctrl+V).")

    def destroy(self) -> None:
        if self.on_close is not None:
            try:
                self.on_close(self.suggestion())
            except tk.TclError:
                pass  # the box is gone already: the window is being taken down with the editor's own
            self.on_close = None
        super().destroy()
