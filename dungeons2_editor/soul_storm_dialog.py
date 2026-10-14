"""Menu > World > Soul Storms: the storm that's on now, and when each area gets its next one, on the PC's clock.

It needs no save: the timetable is the game's own, and the same for every player (see soul_storms).
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
from typing import Callable

from . import soul_storms
from .game_style import match_title_bar
from .layout import fit_to_contents, text_width

REFRESH_MS = 20_000  # the minutes left are told to the minute, so a look a few times a minute keeps them right


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SoulStormDialog(tk.Toplevel):
    """The storm now and the next one in each area. ``clock`` gives the time (in UTC); the tests give a fixed one."""

    def __init__(self, parent: tk.Misc, table: soul_storms.Timetable, clock: Callable[[], datetime] | None = None, zone=None):
        super().__init__(parent)
        self.table = table
        self.clock = clock or _now
        self.zone = zone  # None: the PC's own
        self.title("Soul Storms")
        self.transient(parent)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        wrap = text_width(self, 70)
        self.now_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.now_var, style="Heading.TLabel", wraplength=wrap, justify="left").grid(row=0, column=0, sticky="w")
        self.zone_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.zone_var, wraplength=wrap, justify="left").grid(row=1, column=0, sticky="w", pady=(10, 4))
        self.listing = ttk.Treeview(frame, columns=("starts", "ends", "wait"), selectmode="none", height=len(table.areas))
        self.listing.heading("#0", text="Area", anchor="w")
        self.listing.heading("starts", text="Starts", anchor="w")
        self.listing.heading("ends", text="Ends", anchor="w")
        self.listing.heading("wait", text="", anchor="w")
        self.listing.column("#0", width=text_width(self, 22), stretch=True)
        self.listing.column("starts", width=text_width(self, 11), stretch=False)
        self.listing.column("ends", width=text_width(self, 11), stretch=False)
        self.listing.column("wait", width=text_width(self, 22), stretch=False)
        self.listing.tag_configure("on", font=ttk.Style(self).lookup("Heading.TLabel", "font") or None)
        self.listing.grid(row=2, column=0, sticky="nsew")
        ttk.Label(frame, text=soul_storms.WHERE_FROM, style="Muted.TLabel", wraplength=wrap, justify="left").grid(row=3, column=0, sticky="w", pady=(10, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.close_button = ttk.Button(buttons, text="Close", command=self.destroy)
        self.close_button.pack(side="right")
        self._after: str | None = None
        self.refresh()
        fit_to_contents(self)
        self.bind("<Escape>", lambda _event: self.destroy())

    def rows(self, now: datetime | None = None) -> list[tuple[str, str, str, str]]:
        """What the list shows: each area's next storm (the one on now first), as area, start, end and how long."""
        now = now or self.clock()
        rows = []
        for storm in soul_storms.coming(self.table, now):
            if storm.is_on(now):
                wait = f"on now, {soul_storms.wait_text((storm.ends - now).total_seconds())} left"
            else:
                wait = f"in {soul_storms.wait_text((storm.starts - now).total_seconds())}"
            rows.append((storm.name, soul_storms.clock_text(storm.starts, now, self.zone), soul_storms.clock_text(storm.ends, now, self.zone), wait))
        return rows

    def refresh(self) -> None:
        self._stop_timer()  # one timer at a time, however often this is called
        now = self.clock()
        self.now_var.set(soul_storms.now_text(self.table, now, self.zone))
        zone = self.zone.tzname(now) if self.zone is not None else soul_storms.zone_name(now)
        self.zone_var.set(f"The next storm in each area, on this PC's clock ({zone}):")
        self.listing.delete(*self.listing.get_children())
        for name, starts, ends, wait in self.rows(now):
            self.listing.insert("", "end", text=name, values=(starts, ends, wait), tags=("on",) if wait.startswith("on now") else ())
        self._after = self.after(REFRESH_MS, self.refresh)

    def _stop_timer(self) -> None:
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def destroy(self) -> None:
        self._stop_timer()
        super().destroy()
