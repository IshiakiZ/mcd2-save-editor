"""The play recorder's window: start it, play, and read what the game wrote.

The recording itself is ``recorder.Recorder``; this watches the save folder for it from the window's own
timer, shows what it says as it happens, takes your notes, and at the end asks the Soul Storm check's
questions. It reads your saves and writes only to the recordings folder.
"""

from __future__ import annotations

import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from . import paths, recorder, saves
from .game_style import match_title_bar
from .layout import fit_to_contents, scaled_size, text_width

INTRO = (
    "Leave this open while you play. Every time the game saves, the recorder reads your hero and settings saves again and "
    "writes down what changed: items, stats, quests, stations, doors, the ground you explored. It only reads your saves, and "
    "everything it writes stays in the recordings folder on this PC. A recording holds your whole hero save, so treat it like "
    "a backup: it isn't for posting anywhere whole."
)
LAST_SAVE_WAIT = 8.0  # seconds after the game closes before the wrap-up: its last save lands a moment after its window goes


class RecorderDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        profile: Path,
        out: Path | None = None,
        running: Callable[[], list[str]] = saves.running_game_processes,
        show_map: Callable[[], object] | None = None,
    ):
        super().__init__(parent)
        self.profile = Path(profile)
        self.out = Path(out) if out is not None else recorder.DEFAULT_OUT
        self.running = running
        self.show_map = show_map  # opens the editor's world map window, once the map has been made
        self.recorder: recorder.Recorder | None = None
        self._stamp: tuple | None = None
        self._next_game_check = 0.0
        self._timer: str | None = None
        self.title("Play recorder")
        self.transient(parent)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=INTRO, wraplength=text_width(self, 96), justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        self.text = tk.Text(frame, height=18, width=100, wrap="word", state="disabled", font=("Consolas", 10))
        self.text.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        scroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))
        self.text.configure(yscrollcommand=scroll.set)

        notes = ttk.Frame(frame)
        notes.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        notes.columnconfigure(1, weight=1)
        ttk.Label(notes, text="Note").grid(row=0, column=0, padx=(0, 8))
        self.note_var = tk.StringVar()
        self.note_entry = ttk.Entry(notes, textvariable=self.note_var)
        self.note_entry.grid(row=0, column=1, sticky="ew")
        self.note_entry.bind("<Return>", lambda _event: self.add_note())
        self.note_button = ttk.Button(notes, text="Add note", command=self.add_note)
        self.note_button.grid(row=0, column=2, padx=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.start_button = ttk.Button(buttons, text="Start recording", style="Accent.TButton", command=self.toggle)
        self.start_button.pack(side="left")
        self.map_button = ttk.Button(buttons, text="Show the map", command=self.make_map)
        self.map_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="Open the recordings folder", command=self.open_folder).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.close).pack(side="right")
        self._show_state()
        self._say(recorder.WORTH_DOING.replace("Type a note and press Enter", "Add a note"))
        fit_to_contents(self, *scaled_size(self, 860, 560))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())

    # ------------------------------------------------------------------ what it shows

    def _say(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.configure(state="disabled")
        self.text.see("end")

    def shown_text(self) -> str:
        return self.text.get("1.0", "end").strip()

    def _show_state(self) -> None:
        recording = self.recorder is not None
        self.start_button.configure(text="Stop recording" if recording else "Start recording")
        for widget in (self.note_entry, self.note_button):
            widget.state(["!disabled"] if recording else ["disabled"])

    # ------------------------------------------------------------------ recording

    def toggle(self) -> None:
        self.stop() if self.recorder is not None else self.start()

    def start(self) -> None:
        """Begin a recording: write down what's there now, then watch for the game's saves."""
        if self.recorder is not None:
            return
        session = self.out / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        try:
            self.recorder = recorder.Recorder(self.profile, session, say=self._say)
            self._say(f"Recording to {session}")
            self.recorder.begin(recorder.game_version())
        except OSError as exc:
            self.recorder = None
            messagebox.showerror("Play recorder", f"The recording couldn't be started:\n{exc}", parent=self)
            return
        self._stamp = saves.profile_stamp(self.profile)
        self._next_game_check = 0.0
        self._show_state()
        self._wait(recorder.POLL, self._tick)

    def _wait(self, seconds: float | None, then: Callable[[], None] | None = None) -> None:
        """Do ``then`` after ``seconds``, in place of whatever was waiting to be done. With None, wait for nothing."""
        if self._timer is not None:
            self.after_cancel(self._timer)
        self._timer = self.after(int(seconds * 1000), then) if seconds is not None and then is not None else None

    def _tick(self) -> None:
        """One look at the clock: read the saves again if the folder changed, and check on the game now and then."""
        if self.recorder is None:
            self._wait(None)
            return
        if saves.profile_stamp(self.profile) != self._stamp or self.recorder.retry:
            self._wait(recorder.SETTLE, self._look)  # let the game finish writing
            return
        if time.monotonic() >= self._next_game_check:
            self._next_game_check = time.monotonic() + recorder.GAME_CHECK
            if self.recorder.check_game(self.running()):
                self._wait(LAST_SAVE_WAIT, self._game_closed)
                return
        self._wait(recorder.POLL, self._tick)

    def _look(self) -> None:
        if self.recorder is not None:
            self._stamp = saves.profile_stamp(self.profile)
            self.recorder.look()
            self._wait(recorder.POLL, self._tick)

    def _game_closed(self) -> None:
        if self.recorder is not None:
            self._wrap_up()
            self._say("\nStill recording: start the game again to carry on, or press Stop recording.")
            self._wait(recorder.POLL, self._tick)

    def _wrap_up(self) -> None:
        """Read the saves once more, write the summary, and ask what only you can say: whether the game shows
        Soulstorm Enhanced on the items the Soul Storm check picked out."""
        assert self.recorder is not None
        self.recorder.look()
        self._say("\n" + self.recorder.summary())
        self._say(f"Summary written to {self.recorder.write_summary()}")

        def ask(question: str) -> str | None:
            answer = messagebox.askyesnocancel(
                "Play recorder", f"Does the game show Soulstorm Enhanced on this item?\n\n{question.strip(' =')}\n\nCancel skips the rest.", parent=self
            )
            return None if answer is None else "y" if answer else "n"

        if self.recorder.storm_questions() and self.recorder.ask_storm(ask):
            self._say(f"Summary written again with your answers: {self.recorder.write_summary()}")

    def stop(self) -> None:
        if self.recorder is None:
            return
        self._wait(None)
        self._wrap_up()
        self.recorder.close()
        self.recorder = None
        self._say("Stopped.")
        self._show_state()

    def add_note(self) -> None:
        note = self.note_var.get().strip()
        if note and self.recorder is not None:
            self.recorder.note(note)
            self.note_var.set("")

    # ------------------------------------------------------------------ afterwards

    def make_map(self) -> None:
        """Put everything every recording has shown on the map, and say where the files are."""
        try:
            for line in recorder.write_atlas(self.out):
                self._say(line)
        except OSError as exc:
            messagebox.showerror("Play recorder", f"The map couldn't be written:\n{exc}", parent=self)
            return
        if self.show_map is not None:
            self.show_map()

    def open_folder(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        paths.open_in_file_manager(self.out)

    def close(self) -> None:
        if self.recorder is not None:
            if not messagebox.askyesno("Play recorder", "Stop recording and close?", parent=self):
                return
            self.stop()
        self.destroy()

    def destroy(self) -> None:
        """Going away some other way (the editor itself closing): stop watching and close the recording's file.
        What was recorded up to the last save is kept."""
        self._wait(None)
        if self.recorder is not None:
            self.recorder.close()
            self.recorder = None
        super().destroy()
