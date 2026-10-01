"""Sharing item IDs: the IDs in your saves that the editor doesn't know yet, ready to post on GitHub.

Only item IDs (like SW.Item.MysticHelmet) go into the report: nothing else from the save.
"""

from __future__ import annotations

import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import ttk

from .hero import NOT_ADDABLE_GROUPS, Hero, game_items, item_group, item_kind
from .layout import fit_to_contents, text_width

ISSUE_URL = "https://github.com/IshiakiZ/mcd2-save-editor/issues/new"
ISSUE_TEMPLATE = "item-ids.yml"


def unknown_ids(heroes: list[Hero]) -> list[tuple[str, str]]:
    """(item ID, note) for each ID in these saves that the editor's item list doesn't confirm, or confirms
    without knowing the item's name in the game. Cosmetics, quest items and currencies are left out."""
    known = {item.id: item for item in game_items()}
    seen = set()
    for hero in heroes:
        seen |= hero.seen_item_types()
    found = []
    for tag in sorted(seen):
        if item_group(tag) in NOT_ADDABLE_GROUPS:
            continue
        item = known.get(tag)
        if item is None:
            found.append((tag, f"new to the editor ({item_kind(tag).lower()}), what's it called in the game?"))
        elif not item.confirmed:
            found.append((tag, f"{item.name}: confirms the editor's guess"))
        elif item.name_from_id:
            found.append((tag, f"the editor calls it {item.name}; what's it called in the game?"))
    return found


def report_text(heroes: list[Hero], version: str) -> str:
    lines = [f"{tag} - {note}" for tag, note in unknown_ids(heroes)]
    return "\n".join(lines)


def issue_url(ids_text: str, version: str) -> str:
    query = {"template": ISSUE_TEMPLATE, "title": "Item IDs from my saves", "ids": ids_text, "version": version}
    return ISSUE_URL + "?" + urllib.parse.urlencode(query)


class ShareIdsDialog(tk.Toplevel):
    """Shows the report, lets you add names, and copies it or opens a pre-filled GitHub issue."""

    def __init__(self, parent: tk.Misc, heroes: list[Hero], version: str):
        super().__init__(parent)
        self.version = version
        self.title("Share item IDs")
        self.transient(parent)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        wrap = text_width(self, 80)
        report = report_text(heroes, version)
        intro = (
            "These item IDs from your saves aren't in the editor's list yet, or are there without their in-game name. "
            "Add what the game calls each one after the dash if you know it, then open a GitHub issue (you need a "
            "free GitHub account) or copy the list. Only item IDs are shared, nothing else from your saves."
            if report
            else "Every item ID in your saves is already in the editor's list, with its name. Thanks for checking!"
        )
        ttk.Label(frame, text=intro, wraplength=wrap, justify="left").grid(row=0, column=0, sticky="w")
        self.text = tk.Text(frame, height=10, width=80, wrap="none", font=("Consolas", 10))
        self.text.insert("1.0", report)
        self.text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.message = tk.StringVar()
        ttk.Label(buttons, textvariable=self.message, style="Success.TLabel").pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.copy_button = ttk.Button(buttons, text="Copy", command=self.copy)
        self.copy_button.pack(side="right", padx=6)
        self.issue_button = ttk.Button(buttons, text="Open a GitHub issue…", style="Accent.TButton", command=self.open_issue)
        self.issue_button.pack(side="right")
        if not report:
            self.copy_button.state(["disabled"])
            self.issue_button.state(["disabled"])
        fit_to_contents(self, 720, 380)
        self.bind("<Escape>", lambda _event: self.destroy())

    def report(self) -> str:
        return self.text.get("1.0", "end").strip()

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.report())
        self.message.set("Copied.")

    def open_issue(self) -> None:
        webbrowser.open(issue_url(self.report(), self.version))
        self.message.set("Opened in your browser.")
