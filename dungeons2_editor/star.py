"""Asking for a star: once, in one version of the editor, whether you'd give it a star on GitHub.

A star on the project's GitHub page is how other players come across the editor. The window asks once and
never again: the editor remembers it has asked with its other settings, whichever button was pressed. Nothing
is opened or sent by asking. Star it on GitHub opens the project's page in your own browser, where the star is
yours to give or not.

It asks in one version only (ASK_IN). In any other version this module does nothing, and the version after
that one is to go out without it: a test says so when the version number moves on.

Who isn't asked: someone opening the editor for the first time, who hasn't used it yet (they're asked the next
time they open it), and anyone with the edition that never goes online, which doesn't point its users at
another site.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from .game_style import match_title_bar
from .layout import fit_to_contents, text_width
from .updater import REPOSITORY

ASK_IN = "1.15.2"  # the one version that asks
SETTING = "asked_for_a_star"  # in the editor's settings: true once the window has been shown
PAGE = f"https://github.com/{REPOSITORY}"
TITLE = "Enjoying the editor?"
HEADING = "If the editor has been useful, give it a star"
WORDS = (
    "The MCD2 Save Editor is free, and a star on its GitHub page is how other players come across it. It takes "
    "one click on that page, and a free GitHub account."
)
ONCE = "This is the only time the editor asks."
STAR_BUTTON = "★  Star it on GitHub"
NO_BUTTON = "No thanks"


def should_ask(settings: dict, version: str, online: bool, used_before: bool = True) -> bool:
    """Whether to ask now: in the one version that asks, in the edition that goes online, of someone who has
    opened the editor before and hasn't been asked."""
    return version == ASK_IN and online and used_before and not settings.get(SETTING)


class StarDialog(tk.Toplevel):
    """The question, over the editor's window until it's answered. ``starred`` says which answer it got."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.starred = False
        self.title(TITLE)
        self.transient(parent)
        self.resizable(False, False)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        wrap = text_width(self, 58)
        ttk.Label(frame, text=HEADING, style="Heading.TLabel", wraplength=wrap, justify="left").pack(anchor="w")
        ttk.Label(frame, text=WORDS, wraplength=wrap, justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, text=ONCE, style="Muted.TLabel", wraplength=wrap, justify="left").pack(anchor="w", pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(16, 0))
        self.no_button = ttk.Button(buttons, text=NO_BUTTON, command=self.destroy)
        self.no_button.pack(side="right")
        self.star_button = ttk.Button(buttons, text=STAR_BUTTON, style="Accent.TButton", command=self.star)
        self.star_button.pack(side="right", padx=8)
        fit_to_contents(self)
        self._centre_on(parent)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.star_button.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not shown yet (the editor's window is minimised, say); still there to answer

    def _centre_on(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        top = parent.winfo_toplevel()
        across = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        down = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(across, 0)}+{max(down, 0)}")

    def star(self) -> None:
        """Open the project's page, where the star is, and close."""
        self.starred = True
        webbrowser.open(PAGE)
        self.destroy()
