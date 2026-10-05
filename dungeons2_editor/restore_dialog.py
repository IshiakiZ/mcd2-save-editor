"""The window that lists a save folder's backups and puts one back."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable

from .game_style import match_title_bar
from .layout import fit_to_contents
from .saves import Backup

ROWS = 10  # backups in view before the list scrolls


class RestoreDialog(tk.Toplevel):
    """Pick a backup and press Restore, or double-click it. ``restore(backup, window)`` does the work, and
    closes the window when it's done."""

    def __init__(self, parent: tk.Misc, backups: list[Backup], restore: Callable[[Backup, tk.Toplevel], None]):
        super().__init__(parent)
        self._restore = restore
        self.title("Restore a backup")
        self.transient(parent)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)  # the list takes the room that's left over; the buttons always get theirs
        ttk.Label(frame, text="Pick the backup to put back, then press Restore. Your current saves are backed up first.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        self.listing = ttk.Treeview(frame, columns=("reason",), selectmode="browse", height=ROWS)
        self.listing.heading("#0", text="Made")
        self.listing.heading("reason", text="Why")
        # Sized in characters, not pixels: text is bigger on a display that Windows scales up.
        digit = tkfont.Font(root=self, font=ttk.Style(self).lookup("Treeview", "font") or "TkDefaultFont").measure("0")
        self.listing.column("#0", width=digit * 26, stretch=False)
        self.listing.column("reason", width=digit * 58)
        self.listing.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.listing.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.listing.configure(yscrollcommand=scroll.set)
        self._by_iid: dict[str, Backup] = {}
        for backup in backups:
            iid = self.listing.insert("", "end", text=f"{backup.created:%Y-%m-%d %H:%M:%S}", values=(backup.reason,))
            self._by_iid[iid] = backup
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.restore_button = ttk.Button(buttons, text="Restore", style="Accent.TButton", command=self.restore)
        self.restore_button.pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        first = next(iter(self._by_iid), None)
        if first is not None:
            self.listing.selection_set(first)
            self.listing.focus(first)
        self.listing.bind("<Double-1>", self._on_double_click)
        self.listing.bind("<Return>", lambda _event: self.restore())
        self.bind("<Escape>", lambda _event: self.destroy())
        fit_to_contents(self)
        self.listing.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not shown yet (e.g. while the main window is minimised); still usable

    def selected(self) -> Backup | None:
        selection = self.listing.selection()
        return self._by_iid.get(selection[0]) if selection else None

    def restore(self) -> None:
        backup = self.selected()
        if backup is not None:
            self._restore(backup, self)

    def _on_double_click(self, event: tk.Event) -> None:
        if self.listing.identify_row(event.y):  # on a backup, not on the headings or the empty space below
            self.restore()
