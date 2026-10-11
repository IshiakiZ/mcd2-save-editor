"""The Story progress window: a hero's quests and how far each has got, with the few changes the editor makes to
them (story.py): finish a quest, start one over, add one the hero hasn't met, pick the quest the game tracks, and
say which minecart station the hero was last at.

Like every other change, these go into the hero's unsaved changes: nothing reaches the game until Save to game.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Callable

from . import story
from .game_style import match_title_bar
from .layout import fit_to_contents, scaled_size, text_width

SIZE = (980, 640)  # on a display at 100%
GROUP_PREFIX, QUEST_PREFIX = "group:", "quest:"
SAVE_REMINDER = "Press Save to game when you're done."
INTRO = (
    "How far this hero has got, quest by quest. Finish a quest, start one over, or add one the hero hasn't met yet. "
    "Nothing reaches the game until you press Save to game, which backs up your saves first."
)
STEPS_NOTE = "What a step is about is read off its name (E is a place to reach, K enemies to defeat); the game keeps the words in its own files."
REWARDS = "What the game gives for a quest (items, XP, an achievement) isn't added: the game gives those when it finishes one itself."
START_NOTE = (
    "A save keeps no position for a hero, only the minecart station it was last at and the area it's in. This sets both, to a "
    "station the hero has found."
)
MARKS = {story.DONE: "✓", story.ACTIVE: "▶", story.NOT_SET: "·"}


station_label = story.station_label


def what_it_does(quest: story.Quest, document: Any) -> str:
    """What the buttons do for the quest picked, in a few plain sentences."""
    if not quest.met:
        return "Add it lists this quest as available with every step unset, the way the game lists a quest it has just opened. Its steps are as another hero's save listed them."
    if quest.state == story.DONE:
        return "Start it over makes this quest available again with every step unset, as it was before it was begun."
    told = ["Finish it marks this quest and every one of its steps as done, the way a save holds a finished quest."]
    came = story.follows(quest.name)
    if came:
        have = {other.name for other in story.quests(document)}
        new = [story.label(name) for name in came if name not in have]
        told.append(
            f"In a play recording the game opened {_listed(new)} as it finished this quest, so the editor lists {'that one' if len(new) == 1 else 'those'} too."
            if new else "The quests the game opened after this one are in this hero's list already."
        )
    else:
        told.append("The editor hasn't seen which quests the game opens after this one. If the game doesn't open them by itself, add the next one here.")
    told.append(REWARDS)
    if quest.state == story.ACTIVE:
        told.append("Start it over makes it available again with every step unset. Track it makes it the quest the game shows on screen.")
    return " ".join(told)


def _listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def step_line(step: story.Step) -> tuple[str, str, str]:
    """(mark, name, what to say) for a step in the list of a quest's steps."""
    said = step.kind
    if step.count:
        said += f"{'  ' if said else ''}({step.count}{'' if step.state == story.DONE else ' so far'})"
    return MARKS.get(step.state, "?"), step.short, said


class StoryDialog(tk.Toplevel):
    """A hero's story, to read and to change. ``document`` is the hero's save as the editor is changing it;
    ``on_change`` is called after each change to it."""

    def __init__(self, parent: tk.Misc, document: dict, on_change: Callable[[], None], hero: str = ""):
        super().__init__(parent)
        self.document = document
        self.on_change = on_change
        self.title(f"Story progress: {hero}" if hero else "Story progress")
        self.transient(parent)
        match_title_bar(self)
        base = tkfont.nametofont("TkDefaultFont", root=self)
        size = abs(int(base.cget("size"))) or 9
        self.fonts = {"bold": tkfont.Font(self, family=base.cget("family"), size=size, weight="bold")}
        self._build(base)
        self._fill()
        fit_to_contents(self, *scaled_size(self, *SIZE))
        self._pick_first()  # once the list has its size, so that the quest picked is shown among the ones around it
        self.bind("<Escape>", lambda _event: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ building

    def _build(self, base: tkfont.Font) -> None:
        wrap = text_width(self, 60)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=INTRO, style="Muted.TLabel", wraplength=text_width(self, 138), justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        listing = ttk.Frame(frame)
        listing.grid(row=1, column=0, sticky="ns", padx=(0, 14))
        listing.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(listing, columns=("stands", "steps"), selectmode="browse", height=18)
        self.tree.heading("#0", text="Quest", anchor="w")
        self.tree.heading("stands", text="Stands", anchor="w")
        self.tree.heading("steps", text="Steps done", anchor="w")
        self.tree.column("#0", width=text_width(self, 42), stretch=True)
        self.tree.column("stands", width=text_width(self, 12), stretch=False)
        self.tree.column("steps", width=text_width(self, 13), stretch=False)
        self.tree.tag_configure("group", font=self.fonts["bold"])
        self.tree.tag_configure("unmet", foreground=ttk.Style(self).lookup("Muted.TLabel", "foreground") or "#808080")
        self.tree.grid(row=0, column=0, sticky="ns")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._on_pick())

        panel = ttk.Frame(frame)
        panel.grid(row=1, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(5, weight=1)
        self.title_var, self.stands_var, self.note_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(panel, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, textvariable=self.stands_var, style="Muted.TLabel", wraplength=wrap, justify="left").grid(row=1, column=0, sticky="w")
        buttons = ttk.Frame(panel)
        buttons.grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.finish_button = ttk.Button(buttons, text="Finish it", style="Accent.TButton", command=self.finish)
        self.over_button = ttk.Button(buttons, text="Start it over", command=self.start_over)
        self.add_button = ttk.Button(buttons, text="Add it", command=self.add)
        self.track_button = ttk.Button(buttons, text="Track it", command=self.track)
        for column, button in enumerate((self.finish_button, self.over_button, self.add_button, self.track_button)):
            button.grid(row=0, column=column, padx=(0, 8))
        ttk.Label(panel, textvariable=self.note_var, style="Muted.TLabel", wraplength=wrap, justify="left").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Label(panel, text=STEPS_NOTE, style="Muted.TLabel", wraplength=wrap, justify="left").grid(row=4, column=0, sticky="w", pady=(12, 4))
        steps = ttk.Frame(panel)
        steps.grid(row=5, column=0, sticky="nsew")
        steps.columnconfigure(0, weight=1)
        steps.rowconfigure(0, weight=1)
        self.text = tk.Text(steps, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, font=base, padx=2, pady=4, height=12, width=54, cursor="arrow", takefocus=False)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(steps, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set, background=self.cget("background"))
        self.text.tag_configure("step", tabs=(text_width(self, 4), text_width(self, 22)), lmargin2=text_width(self, 22))
        self.text.tag_configure("group", font=self.fonts["bold"])
        self.text.tag_configure("muted", foreground=ttk.Style(self).lookup("Muted.TLabel", "foreground") or "#808080")

        start = ttk.Frame(frame)
        start.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(start, text="Where the hero starts", font=self.fonts["bold"]).grid(row=0, column=0, sticky="w")
        self.station_var = tk.StringVar()
        self.station_box = ttk.Combobox(start, textvariable=self.station_var, state="readonly", width=40)
        self.station_box.grid(row=0, column=1, padx=(10, 8))
        self.station_box.bind("<<ComboboxSelected>>", lambda _event: self._update_start())
        self.start_button = ttk.Button(start, text="Start there", command=self.start_there)
        self.start_button.grid(row=0, column=2)
        self.now_var = tk.StringVar()
        ttk.Label(start, textvariable=self.now_var, style="Muted.TLabel").grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Label(start, text=START_NOTE, style="Muted.TLabel", wraplength=text_width(self, 138), justify="left").grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))

        bottom = ttk.Frame(frame)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)
        self.message_var = tk.StringVar()
        self.message = ttk.Label(bottom, textvariable=self.message_var, style="Muted.TLabel", wraplength=text_width(self, 130), justify="left")
        self.message.grid(row=0, column=0, sticky="w")
        self.close_button = ttk.Button(bottom, text="Close", command=self.destroy)
        self.close_button.grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------ the list of quests

    def _fill(self, keep: str | None = None) -> None:
        """Write the list of quests again, as the save has them now, and pick ``keep`` if it's there."""
        tree = self.tree
        tree.delete(*tree.get_children())
        self.quests = {quest.name: quest for quest in story.every(self.document)}
        for quest in self.quests.values():
            group = GROUP_PREFIX + quest.group
            if not tree.exists(group):
                tree.insert("", "end", iid=group, text=quest.group, open=True, tags=("group",))
            steps = f"{quest.done} of {len(quest.steps)}" if quest.met else f"{len(quest.steps)} step{'' if len(quest.steps) == 1 else 's'}"
            name = (quest.title + f"  ({quest.name})" if quest.title else quest.name) + ("  ◀ tracked" if quest.tracked else "")
            tree.insert(group, "end", iid=QUEST_PREFIX + quest.name, text=name, values=(quest.standing, steps), tags=() if quest.met else ("unmet",))
        if keep and tree.exists(QUEST_PREFIX + keep):
            tree.selection_set(QUEST_PREFIX + keep)
            tree.see(QUEST_PREFIX + keep)  # it was in view before: this moves the list only if it has to
        self._fill_start()
        self._show()

    def _pick_first(self) -> None:
        """Start on the quest the game tracks, or the first one that's active, or the first one."""
        names = list(self.quests)
        first = next((name for name in names if self.quests[name].tracked), None) or next((name for name in names if self.quests[name].state == story.ACTIVE), None) or (names[0] if names else None)
        if first:
            self.tree.selection_set(QUEST_PREFIX + first)
            # From the top if that shows it, and otherwise with it in the middle of the list, among its neighbours.
            rows = [row for group in self.tree.get_children() for row in (group, *self.tree.get_children(group))]
            place, room = rows.index(QUEST_PREFIX + first), int(self.tree.cget("height"))
            self.tree.yview_moveto(0 if place < room else (place - room // 2) / len(rows))
        self._show()

    def _on_pick(self) -> None:
        selection = self.tree.selection()
        if selection and selection[0].startswith(GROUP_PREFIX):
            children = self.tree.get_children(selection[0])
            if children:
                self.tree.selection_set(children[0])  # fires this again
                return
        self._say("")
        self._show()

    @property
    def quest(self) -> story.Quest | None:
        """The quest picked in the list."""
        selection = self.tree.selection()
        return self.quests.get(selection[0][len(QUEST_PREFIX):]) if selection and selection[0].startswith(QUEST_PREFIX) else None

    def pick(self, name: str) -> None:
        self.tree.selection_set(QUEST_PREFIX + name)
        self._on_pick()

    def _show(self) -> None:
        """The quest picked, beside the list: how it stands, what can be done with it, and its steps."""
        quest = self.quest
        can = {
            self.finish_button: quest is not None and quest.met and quest.state != story.DONE,
            self.over_button: quest is not None and quest.state in (story.ACTIVE, story.DONE),
            self.add_button: quest is not None and not quest.met,
            self.track_button: quest is not None and quest.state == story.ACTIVE and not quest.tracked,
        }
        for button, enabled in can.items():
            button.state(["!disabled"] if enabled else ["disabled"])
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        if quest is None:
            self.title_var.set("No quests")
            self.stands_var.set("This hero's save keeps no quests yet, and the editor's list has none either.")
            self.note_var.set("")
            text.configure(state="disabled")
            return
        self.title_var.set(quest.label)
        where = {story.MAIN: "in the main story", story.OTHER: "among the other quests"}.get(quest.group) or "a side quest of " + quest.group.split(": ", 1)[-1]
        stands = f"{quest.standing.capitalize()}, {where}"
        if quest.met:
            stands += f". {quest.done} of {len(quest.steps)} steps done"
        self.stands_var.set(stands + (". The game tracks this one on screen." if quest.tracked else "."))
        self.note_var.set(what_it_does(quest, self.document))
        for step in quest.steps:
            mark, name, said = step_line(step)
            text.insert("end", f"{mark}\t{name}\t{said}\n", ("step", "group") if step.is_group else ("step",) if step.state != story.NOT_SET else ("step", "muted"))
        text.configure(state="disabled")

    def steps_text(self) -> str:
        return self.text.get("1.0", "end").strip()

    # ------------------------------------------------------------------ changing a quest

    def _say(self, text: str, error: bool = False) -> None:
        self.message_var.set(text)
        self.message.configure(style="Error.TLabel" if error else "Success.TLabel" if text.endswith(SAVE_REMINDER) else "Muted.TLabel")

    def _change(self, change: Callable[[story.Quest], str]) -> None:
        """Make a change to the quest picked, show the list as it is now, and say what was done."""
        quest = self.quest
        if quest is None:
            return
        try:
            done = change(quest)
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        self.on_change()
        self._fill(keep=quest.name)
        self._say(f"{done} {SAVE_REMINDER}")

    def finish(self) -> None:
        def change(quest: story.Quest) -> str:
            added = story.finish(self.document, quest.name)
            return f"Finished {quest.label}." + (f" Added what the game opens after it: {_listed([story.label(name) for name in added])}." if added else "")

        self._change(change)

    def start_over(self) -> None:
        def change(quest: story.Quest) -> str:
            story.start_over(self.document, quest.name)
            return f"{quest.label} is available again, with every step unset."

        self._change(change)

    def add(self) -> None:
        def change(quest: story.Quest) -> str:
            story.add(self.document, quest.name)
            return f"Added {quest.label}: it's available."

        self._change(change)

    def track(self) -> None:
        def change(quest: story.Quest) -> str:
            story.track(self.document, quest.name)
            return f"The game will track {quest.label}."

        self._change(change)

    # ------------------------------------------------------------------ where the hero starts

    def _fill_start(self) -> None:
        self.stations = {station_label(tag): tag for tag in story.start_points(self.document)}
        self.station_box.configure(values=list(self.stations))
        now = story.last_station(self.document)
        if not self.stations:
            self.station_var.set("")
            self.station_box.state(["disabled"])
            self.now_var.set("This save doesn't say where the hero was last.")
        else:
            self.station_box.state(["!disabled"])
            if self.station_var.get() not in self.stations:
                self.station_var.set(next((label for label, tag in self.stations.items() if tag == now), next(iter(self.stations))))
            self.now_var.set(f"Now: {station_label(now)}" if now else "")
        self._update_start()

    def _update_start(self) -> None:
        tag = self.stations.get(self.station_var.get())
        self.start_button.state(["!disabled"] if tag and tag != story.last_station(self.document) else ["disabled"])

    def start_there(self) -> None:
        tag = self.stations.get(self.station_var.get())
        if not tag:
            return
        try:
            story.start_at(self.document, tag)
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        self.on_change()
        self._fill_start()
        self._say(f"The save now says the hero was last at {station_label(tag)}. {SAVE_REMINDER}")
