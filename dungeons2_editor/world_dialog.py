"""The world map: the ground a hero has explored, what it has found there, and how far it has got.

The map is the hero's own, from its save: for each region the game keeps a picture of the fog over it, and every
door with its position. It's drawn the way round the game's own map is. The list beside it is the save's too: the
story quests, every quest and its steps, minecart stations, doors, the game's counts. The play recorder's
recordings add what a save can't place by itself: where a station, a cutscene or a chest turned up, by the
ground whose fog cleared in the save it turned up in.

It's a view, with one thing to press: Discover the whole map lifts the fog from every map (story.discover_map).
That joins the hero's unsaved changes, like any other change, and the window is drawn again from them.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import recorder, story
from .game_style import match_title_bar
from .layout import fit_to_contents, scaled_size

GROUND, INK = "#0d1a24", "#d7e3ea"
DOOR, FOUND, CHEST = "#ff9b3d", "#4cc3ff", "#ffd84a"
LEGEND = (
    (recorder.clarity_colour(255), "explored"), (recorder.clarity_colour(0, True), "not explored, right next to it"),
    (DOOR, "door"), (FOUND, "found around here"), (CHEST, "chest opened around here"),
)
# A save says that a thing was found, not where. A recording has the save it first showed up in, and the ground
# whose fog cleared between that save and the one before: so it was there, or somewhere the hero went into from there.
AROUND = "The save that showed it also showed new ground explored here, so it was around here, or in a place you went into from here."
STATES = ("Completed", "Active", "Available", "Unavailable")  # how a quest stands, furthest along first
MAP_SIDE = 560  # pixels the map starts out at, on a display at 100%; it grows with the window
MARGIN = 10  # pixels kept clear around the picture
MOST_SQUARE = 44  # pixels to a square at most with the whole region in view, so that a small region isn't blown up
MOST_ZOOMED = 72  # and at most when zoomed in
ZOOM_STEP = 1.25
HINT = "Point at a dot to see what it is. Scroll to zoom in and out, and drag to move the map."
NO_MAP = "This save has no map yet: the game draws one as the hero explores."
DISCOVER = "Discover the whole map"
DISCOVERED = "The whole map is discovered. Press Save to game when you're done."
OPEN = {story.SHORTCUTS: "Open the shortcuts", story.GATES: "Open the key gates"}
ALL_OPEN = {story.SHORTCUTS: "Every shortcut the editor knows is open already.", story.GATES: "Every key gate the editor knows is open already."}
NO_RECORDINGS = (
    "Nothing yet for this hero. Play with the play recorder on (Menu > World > Play recorder), and the minecart stations, cutscenes "
    "and chests you find get a place on this map."
)
_PREFIXES = ("SW.Doorway.", "SW.MinecartStation.", "SW.UI.Cutscene.", "SW.Achievements.", "SW.Area.", "SW.Region.", "SW.")
_WORDS = re.compile(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[0-9])(?=[A-Za-z])|(?<=[a-z]A)(?=[A-Z])")


def short(name: str) -> str:
    """A save's name for a thing, without the prefix every one of its kind shares."""
    for prefix in _PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def spaced(name: str) -> str:
    """A name the game runs together, with its words apart: Open100Chests is Open 100 Chests."""
    return _WORDS.sub(" ", name)


def story_name(achievement: str) -> str:
    """A story quest's name, from the game's achievement for finishing it: CompleteWobbleRunQuest is Wobble Run."""
    name = short(achievement).removeprefix("Complete").removesuffix("Quest")
    return spaced(name + "Quest" if name.endswith("Side") else name)  # CompleteCarapaceSideQuest is the Carapace side quest


def things(tag: str, regions: dict[str, dict], doors: dict[str, list[float]], mine: dict[str, Any]) -> list[tuple[str, str, float, float, str]]:
    """(kind, name, x, y, what to say about it) for everything with a place in a region, the place in the world's
    metres: its doors, exactly, then what the hero's recordings saw turn up there and the chests opened there.
    ``mine`` is the hero's part of the recordings' atlas."""
    placed = [("door", short(name), place[0], place[1], f"Door {short(name)}, at {place[0]:.0f}, {place[1]:.0f}")
              for name, place in doors.items() if recorder.region_of(place[0], place[1], regions) == tag]
    for label, place in (mine.get("found_at") or {}).items():
        # A quest starting or ending isn't a place: several do at once, at wherever the hero happened to be.
        if place.get("region") == tag and place.get("near") and not label.startswith("quest "):
            kind = next((kind for kind in ("minecart station", "cutscene", "gimmick") if label.startswith(kind + " ")), "")
            rest = label[len(kind):].strip()
            name = recorder.station_name(rest) if kind == "minecart station" else short(rest)
            what = {"minecart station": "Minecart station", "cutscene": "Cutscene", "gimmick": "Gimmick"}.get(kind, "Found:")
            placed.append(("found", name, place["near"][0], place["near"][1], f"{what} {name}. {AROUND}"))
    for chest in mine.get("chests") or []:
        if chest.get("region") == tag and chest.get("near"):
            count = chest.get("opened", 1)
            words = f"{count} chest{'s' if count != 1 else ''}"
            placed.append(("chest", words, chest["near"][0], chest["near"][1], f"{words} opened in {recorder.area_name(str(chest.get('area')))}. {AROUND}"))
    return placed


def sections(document: Any, atlas: dict[str, Any] | None = None) -> list[tuple[str, list[str]]]:
    """What a hero's save says about how far it has got, as headed lists to read: (heading, lines). ``atlas`` is
    what the play recorder's recordings have shown (recorder.fresh_atlas), for where chests were opened."""
    progress, regions = recorder.world_progress(document), recorder.map_regions(document)
    mine = ((atlas or {}).get("heroes") or {}).get(recorder.hero_id(document)) or {}
    achievements = ((document.get("CharacterSaveV1") if isinstance(document, dict) else None) or {}).get("Achievements") or {}
    found: list[tuple[str, list[str]]] = []

    def labelled(kind: str) -> list[str]:
        return [label[len(kind) + 1:] for label in progress if label.startswith(kind + " ")]

    where = [f"Area: {recorder.area_name(str(progress.get('where CurrentLocation', 'not saved')))}"]
    if progress.get("quest in focus"):
        where.append(f"Quest in focus: {recorder.quest_name(str(progress['quest in focus']))}")
    if progress.get("last minecart station"):
        where.append(f"Last minecart station: {recorder.station_name(str(progress['last minecart station']))}")
    found.append(("Where the hero is", where))

    achieved = [(story_name(name), bool(entry.get("bCompleted"))) for name, entry in (achievements.get("QuestAchievements") or {}).items() if isinstance(entry, dict)]
    steps = recorder.quest_tasks(progress)
    quests = {name: str(progress[f"quest {name}"]) for name in steps}
    states: dict[str, int] = {}
    for state in quests.values():
        states[state] = states.get(state, 0) + 1
    so_far = []
    if achieved:
        so_far.append(f"Story quests done: {sum(1 for _name, done in achieved if done)} of {len(achieved)}")
    if quests:
        every = [value for values in steps.values() for value in values]
        so_far.append("Quests met: " + ", ".join(f"{states[state]} {state.lower()}" for state in sorted(states, key=lambda state: (STATES.index(state) if state in STATES else len(STATES), state))))
        so_far.append(f"Quest steps done: {sum(1 for value in every if value.startswith('Completed'))} of {len(every)}")
    stations = len(labelled("minecart station"))
    so_far.append(f"Minecart stations found: {stations} of at least {recorder.stations_at_least(stations)}")
    so_far.append(f"Doors found: {len(labelled('door'))}")
    so_far.append(f"Cutscenes seen: {len(labelled('cutscene'))}")
    for kind, words in ((story.SHORTCUTS, "Shortcuts open"), (story.GATES, "Key gates open")):
        done, known = story.pieces_open(document, kind)
        if known:
            so_far.append(f"{words}: {done} of the {known} the editor knows")
    if isinstance(progress.get(recorder.CHESTS), int):
        so_far.append(f"Chests opened: {progress[recorder.CHESTS]}, by the game's own count")
    found.append(("So far", so_far))

    found.append(("The story, by the game's achievements for it", [("✓  " if done else "·  ") + name for name, done in achieved]))
    found.append(("What you may have missed, as far as the save shows", [short(line).replace(" (marked on the map)", "") for line in recorder.might_be_missing(progress, regions)]))
    found.append(("Ground explored", [
        f"{short(tag)}: {sum(1 for cell in region['cells'] if cell)} of {len(region['cells'])} squares" for tag, region in regions.items()
    ]))
    found.append(("Quests, as the save names them", [
        f"{recorder.quest_name(name)}: {state.lower()}" + (f", {sum(1 for value in steps[name] if value.startswith('Completed'))} of {len(steps[name])} steps done" if steps[name] else "")
        for name, state in quests.items()
    ]))
    found.append(("Minecart stations found", [f"{recorder.station_name(name)}  ({short(name)})" for name in labelled("minecart station")]))
    found.append(("Doors found", sorted(short(name) for name in labelled("door"))))
    chests = [f"{'While nothing was recording' if area == recorder.BETWEEN else recorder.area_name(area)}: {count}" for area, count in recorder.chests_by_area(mine.get("chests") or []).items()]
    found.append(("Chests your recordings saw opened, by area", chests))
    other = []
    for group, entries in achievements.items():
        for name, entry in (entries or {}).items() if isinstance(entries, dict) and group != "QuestAchievements" else []:
            if isinstance(entry, dict):
                value = ("done" if entry["bCompleted"] else "not yet") if "bCompleted" in entry else entry["Count"] if "Count" in entry else f"{len(entry.get('CollectedTags') or [])} collected"
                other.append(f"{spaced(short(str(name)))}: {value}")
    found.append(("Other achievements, as the save counts them", other))
    found.append(("From your recordings", [f"{mine['saves']} saves of this hero read"] if mine.get("saves") else [NO_RECORDINGS]))
    return [(heading, lines) for heading, lines in found if lines]


def discover_question(left: int, more: list[str]) -> str:
    """What to ask before lifting the fog from the whole map."""
    told = [f"{DISCOVER}?"]
    told.append(
        f"Every square of every map this hero has is marked as explored ({left:,} {'is' if left == 1 else 'are'}n't yet)."
        if left else "Every square of the maps this hero has is explored already."
    )
    if more:
        told.append(
            f"The editor also adds the map{'' if len(more) == 1 else 's'} of {len(more)} place{'' if len(more) == 1 else 's'} this hero hasn't been to yet, "
            "explored too, the way other players' saves hold them."
        )
    # The recorder places what happens by the fog that cleared between two saves (recorder.newly_explored).
    told.append("The play recorder tells where a chest was opened by the fog that lifts as you explore. With the whole map discovered it can only tell the area.")
    told.append("It joins your unsaved changes: nothing reaches the game until Save to game, and Discard changes takes it back.")
    return "\n\n".join(told)


def open_question(kind: str, count: int, known: int) -> str:
    """What to ask before opening the shortcuts, or the key gates."""
    them = "It isn't" if known == 1 else "None of them is" if count == known else "One of them isn't" if count == 1 else f"{count} of them aren't"
    marked = "it will be marked open" if count == 1 else "they will be marked open"
    if kind == story.SHORTCUTS:
        told = [
            f"{OPEN[kind]}?",
            f"The editor knows {known} shortcut{'' if known == 1 else 's'}: rocks that move out of the way once you've come round to their far side, and "
            f"a bridge. {them} open for this hero yet, and {marked}, the way a save holds one that is.",
        ]
    else:
        told = [
            f"{OPEN[kind]}?",
            f"The editor knows {known} gate{'' if known == 1 else 's'} that a key opens. {them} open for this hero yet, and {marked}, the way a save "
            "holds a gate once its key is in. The keys and their locks are left as they are.",
        ]
    told.append("It joins your unsaved changes: nothing reaches the game until Save to game, and Discard changes takes it back.")
    return "\n\n".join(told)


class WorldDialog(tk.Toplevel):
    """A hero's map and its progress, to look at. It doesn't stop you using the editor meanwhile. With
    ``on_discover`` (which lifts the fog in the save it's given and says whether it did), it has a button for
    that, and is drawn again afterwards. With ``on_open`` (which opens the shortcuts or the key gates in the
    save it's given, and says whether it did), it has a button for each of those."""

    def __init__(
        self, parent: tk.Misc, document: Any, atlas: dict[str, Any] | None = None, hero: str = "", on_discover: Callable[[Any], bool] | None = None,
        on_open: Callable[[Any, str], bool] | None = None,
    ):
        super().__init__(parent)
        self.document, self.atlas, self.on_discover, self.on_open = document, atlas, on_discover, on_open
        self.regions = recorder.map_regions(document)
        self.doors = recorder.door_places(document)
        self.mine = ((atlas or {}).get("heroes") or {}).get(recorder.hero_id(document)) or {}
        self.listed = sections(document, atlas)
        self.zoom = 1.0  # how many times bigger than with the whole region in view
        self._size = 0  # pixels to a square as last drawn
        self._most_zoom = 1.0
        self._redraw: str | None = None
        self.title(f"World map: {hero}" if hero else "World map")
        self.transient(parent)
        match_title_bar(self)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        base = tkfont.nametofont("TkDefaultFont", root=self)
        size = abs(int(base.cget("size"))) or 9
        self.fonts = {
            "bold": tkfont.Font(self, family=base.cget("family"), size=size, weight="bold"),
            "small": tkfont.Font(self, family=base.cget("family"), size=max(size - 2, 7)),
        }

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(top, text="Region").pack(side="left")
        # The biggest region first: that's the overworld, and the camp, the meadows and the caves come after it.
        self.tags = sorted(self.regions, key=lambda tag: -self.regions[tag]["across"] * self.regions[tag]["down"])
        self.region_var = tk.StringVar(value=short(self.tags[0]) if self.tags else "")
        self.region_box = ttk.Combobox(top, textvariable=self.region_var, values=[short(tag) for tag in self.tags], state="readonly", width=22)
        self.region_box.pack(side="left", padx=(8, 10))
        self.region_box.bind("<<ComboboxSelected>>", lambda _event: self.show_region())
        self.out_button = ttk.Button(top, text="−", width=3, command=lambda: self.zoom_by(1 / ZOOM_STEP))
        self.out_button.pack(side="left")
        self.in_button = ttk.Button(top, text="+", width=3, command=lambda: self.zoom_by(ZOOM_STEP))
        self.in_button.pack(side="left", padx=(4, 10))
        self.names_var = tk.BooleanVar(value=False)
        self.names_box = ttk.Checkbutton(top, text="Names", variable=self.names_var, command=self.draw)
        self.names_box.pack(side="left", padx=(0, 8))
        for colour, what in LEGEND:
            swatch = tk.Canvas(top, width=11, height=11, highlightthickness=0, background=colour)
            swatch.pack(side="left", padx=(6, 4))
            ttk.Label(top, text=what, style="Muted.TLabel").pack(side="left")

        self.heading_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.heading_var, font=self.fonts["bold"]).grid(row=1, column=0, sticky="w", pady=(0, 6))
        side = scaled_size(self, MAP_SIDE, MAP_SIDE)[1]
        self.canvas = tk.Canvas(frame, width=side, height=side, background=GROUND, highlightthickness=0)
        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._resized)
        # The wheel zooms the map when the pointer is over it, whichever part of the window the turn of it goes to
        # (on Windows that can be the part that last had a click, not the one under the pointer).
        self.bind("<MouseWheel>", lambda event: self._wheel(ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP))
        self.bind("<Button-4>", lambda _event: self._wheel(ZOOM_STEP))  # the wheel, on Linux
        self.bind("<Button-5>", lambda _event: self._wheel(1 / ZOOM_STEP))
        self.canvas.bind("<ButtonPress-1>", lambda event: self.canvas.scan_mark(event.x, event.y))
        self.canvas.bind("<B1-Motion>", lambda event: self.canvas.scan_dragto(event.x, event.y, gain=1))
        data = ttk.Frame(frame)
        data.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=(12, 0))
        data.rowconfigure(0, weight=1)
        self.text = tk.Text(
            data, width=54, height=10, wrap="word", relief="flat", borderwidth=0, highlightthickness=0, padx=10, pady=6, cursor="arrow", takefocus=False,
            font=base,  # a Text widget writes in a typewriter's letters unless told otherwise
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(data, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        bottom = ttk.Frame(frame)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(0, weight=1)
        self.hover_var = tk.StringVar(value=HINT)
        ttk.Label(bottom, textvariable=self.hover_var, style="Muted.TLabel", anchor="w").grid(row=0, column=0, sticky="ew")
        self.discover_button = ttk.Button(bottom, text=DISCOVER, command=self.discover)
        if on_discover is not None:
            self.discover_button.grid(row=0, column=1, padx=(8, 0))
            self._update_discover()
        self.piece_buttons = {kind: ttk.Button(bottom, text=OPEN[kind], command=lambda kind=kind: self.open_pieces(kind)) for kind in (story.SHORTCUTS, story.GATES)}
        if on_open is not None:
            for column, button in enumerate(self.piece_buttons.values(), start=2):
                button.grid(row=0, column=column, padx=(8, 0))
            self._update_pieces()
        self.copy_button = ttk.Button(bottom, text="Copy the list", command=self.copy_list)
        self.copy_button.grid(row=0, column=4, padx=(8, 8))
        self.close_button = ttk.Button(bottom, text="Close", style="Accent.TButton", command=self.destroy)
        self.close_button.grid(row=0, column=5)
        self._write()
        self.draw()
        fit_to_contents(self, *scaled_size(self, 1120, 700))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.close_button.focus_set()

    # ------------------------------------------------------------------ the map

    def region_tag(self) -> str | None:
        return next((tag for tag in self.tags if short(tag) == self.region_var.get()), None)

    def show_region(self) -> None:
        """Another region was picked: all of it, in the middle."""
        self.zoom, self._size = 1.0, 0
        self.draw()

    def _room(self) -> tuple[int, int]:
        """The map's size in pixels: as it is on screen, or as it asked to be before it's there."""
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        return (width, height) if width > 20 and height > 20 else (self.canvas.winfo_reqwidth(), self.canvas.winfo_reqheight())

    def _resized(self, _event: object = None) -> None:
        """The window gave the map a new size: draw it again, once the dragging has stopped for a moment."""
        if self._redraw is not None:
            self.after_cancel(self._redraw)
        self._redraw = self.after(60, self.draw)

    def _wheel(self, factor: float) -> None:
        """A turn of the wheel: zoom about the pointer, if it's over the map."""
        x, y = self.winfo_pointerx() - self.canvas.winfo_rootx(), self.winfo_pointery() - self.canvas.winfo_rooty()
        width, height = self._room()
        if 0 <= x < width and 0 <= y < height:
            self.zoom_by(factor, (x, y))

    def zoom_by(self, factor: float, at: tuple[float, float] | None = None) -> None:
        """Make the map ``factor`` times as big, keeping what's under ``at`` (the middle, if not given) where it is.
        Never smaller than the whole region in view."""
        width, height = self._room()
        at = at or (width / 2, height / 2)
        zoom = min(max(self.zoom * factor, 1.0), self._most_zoom)
        if abs(zoom - self.zoom) < 0.001 or not self._size:
            return
        keep = (self.canvas.canvasx(at[0]) / self._size, self.canvas.canvasy(at[1]) / self._size, at[0], at[1])
        self.zoom = zoom
        self.draw(keep)

    def draw(self, keep: tuple[float, float, float, float] | None = None) -> None:
        """Draw the region picked, the way round the game's own map is. ``keep`` is a spot on the picture (in
        squares) and where in the map's own window it should be (in pixels); without it, what was in the middle
        stays there."""
        if self._redraw is not None:
            self.after_cancel(self._redraw)
            self._redraw = None
        canvas = self.canvas
        width, height = self._room()
        if keep is None and self._size:
            keep = (canvas.canvasx(width / 2) / self._size, canvas.canvasy(height / 2) / self._size, width / 2, height / 2)
        canvas.delete("all")
        self.hover_var.set(HINT)
        tag = self.region_tag()
        if tag is None:
            canvas.configure(scrollregion=(0, 0, width, height))
            canvas.create_text(width // 2, height // 2, text=NO_MAP, fill=INK, width=width - 60)
            self.heading_var.set("")
            self._size = 0
            return
        region = self.regions[tag]
        across, down, cells = max(region["across"], 1), max(region["down"], 1), region["cells"]
        fit = max(3, min((width - 2 * MARGIN) // across, (height - 2 * MARGIN) // down, MOST_SQUARE))
        self._most_zoom = max(1.0, MOST_ZOOMED / fit)
        self.zoom = min(self.zoom, self._most_zoom)
        size = max(3, round(fit * self.zoom))
        wide, high = across * size, down * size
        # What can be scrolled to: the picture and a margin, and never less than the window, which keeps a map
        # smaller than its window in the middle of it.
        beside, above = max(MARGIN, (width - wide) // 2), max(MARGIN, (height - high) // 2)
        around = (-beside, -above, wide + beside, high + above)
        canvas.configure(scrollregion=around)
        canvas.create_rectangle(0, 0, wide, high, fill=recorder.clarity_colour(0), width=0, tags=("ground",))
        gap = 1 if size > 5 else 0
        if gap:
            for place in range(1, across + 1):
                canvas.create_line(place * size - 1, 0, place * size - 1, high, fill=GROUND, tags=("grid",))
            for line in range(1, down + 1):
                canvas.create_line(0, line * size - 1, wide, line * size - 1, fill=GROUND, tags=("grid",))
        edge = set(recorder.frontier(region))
        for index in range(min(len(cells), across * down)):
            if cells[index] or index in edge:
                line, place = divmod(index, across)
                canvas.create_rectangle(place * size, line * size, (place + 1) * size - gap, (line + 1) * size - gap, width=0,
                                        fill=recorder.clarity_colour(cells[index], index in edge), tags=("explored" if cells[index] else "edge",))
        dot = max(3, min(size // 3, 7))
        taken: dict[tuple[float, float], int] = {}
        names: list[tuple[float, float, str, str]] = []
        boxes: list[tuple[float, float, float, float]] = []  # where there's a dot or a name already
        for kind, name, x, y, what in things(tag, self.regions, self.doors, self.mine):
            # Things one save showed are at one spot: side by side, then, not on top of each other.
            beside_it = taken[(x, y)] = taken.get((x, y), -1) + 1
            place, line = recorder.square_of(region, x, y)
            at_x, at_y = place * size + beside_it * (2 * dot + 2), line * size
            box = (at_x - dot, at_y - dot, at_x + dot, at_y + dot)
            colour = {"door": DOOR, "found": FOUND, "chest": CHEST}[kind]
            item = canvas.create_rectangle(*box, fill=colour, outline=GROUND, tags=("thing", kind)) if kind == "chest" else canvas.create_oval(*box, fill=colour, outline=GROUND, tags=("thing", kind))
            canvas.tag_bind(item, "<Enter>", lambda _event, text=what: self.hover_var.set(text))
            canvas.tag_bind(item, "<Leave>", lambda _event: self.hover_var.set(HINT))
            boxes.append(box)
            names.append((at_x, at_y, name, colour))
        sides = (("w", dot + 4, 0), ("e", -dot - 4, 0), ("n", 0, dot + 3), ("s", 0, -dot - 3))
        for at_x, at_y, name, colour in names if self.names_var.get() else []:
            # A name goes beside its dot, on whichever side it covers no other dot or name: right, left, below,
            # above. With nowhere clear, on the right all the same.
            item = None
            for anchor, over, under in sides + sides[:1]:
                if item is not None:
                    canvas.delete(item)
                item = canvas.create_text(at_x + over, at_y + under, anchor=anchor, text=name, fill=colour, font=self.fonts["small"], tags=("name",))
                box = canvas.bbox(item)
                if not any(box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3] for other in boxes):
                    break
            boxes.append(box)
            canvas.create_rectangle(box[0] - 2, box[1], box[2] + 2, box[3], fill=GROUND, width=0, tags=("label",))
        canvas.tag_raise("name")
        canvas.tag_raise("thing")
        self.heading_var.set(f"{short(tag)}: {sum(1 for cell in cells if cell)} of {across * down} squares explored. One square is {recorder.CELL} metres across.")
        self._size = size
        self.out_button.state(["!disabled"] if self.zoom > 1.0 else ["disabled"])
        self.in_button.state(["!disabled"] if self.zoom < self._most_zoom else ["disabled"])
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        if keep is not None:
            canvas.xview_moveto((keep[0] * size - keep[2] - around[0]) / (around[2] - around[0]))
            canvas.yview_moveto((keep[1] * size - keep[3] - around[1]) / (around[3] - around[1]))

    def shown(self, kind: str) -> int:
        """How many of a kind of thing ("explored", "edge", "door", "found", "chest", "name") the map shows just now."""
        return len(self.canvas.find_withtag(kind))

    # ------------------------------------------------------------------ the list beside it

    def _update_discover(self) -> None:
        """The button is there to press while there's fog left to lift, or a map to add."""
        try:
            left, more = story.map_to_discover(self.document)
        except ValueError:
            left, more = 1, []  # no map at all: pressing it says so
        self.discover_button.state(["!disabled"] if left or more else ["disabled"])

    def discover(self) -> None:
        """Lift the fog from the whole map, once the user has said yes, and draw the window again."""
        if self.on_discover is None:
            return
        try:
            left, more = story.map_to_discover(self.document)
        except ValueError as exc:
            self.hover_var.set(str(exc))
            return
        if not left and not more:
            self.hover_var.set("The whole map is discovered already.")
            return
        if not messagebox.askyesno(DISCOVER, discover_question(left, more), default="no", parent=self):
            return
        if not self.on_discover(self.document):
            return
        picked = self.region_tag()
        self.regions = recorder.map_regions(self.document)
        self.listed = sections(self.document, self.atlas)
        self.tags = sorted(self.regions, key=lambda tag: -self.regions[tag]["across"] * self.regions[tag]["down"])
        self.region_box.configure(values=[short(tag) for tag in self.tags])
        self.region_var.set(short(picked if picked in self.regions else self.tags[0]) if self.tags else "")
        self._write()
        self.show_region()
        self._update_discover()
        self.hover_var.set(DISCOVERED)

    def _update_pieces(self) -> None:
        """Each of the two buttons is there to press while the editor knows a shortcut, or a gate, that isn't open."""
        for kind, button in self.piece_buttons.items():
            button.state(["!disabled"] if story.pieces_to_open(self.document, kind) else ["disabled"])

    def open_pieces(self, kind: str) -> None:
        """Open the shortcuts, or the key gates, once the user has said yes, and write the list again."""
        if self.on_open is None:
            return
        todo, known = len(story.pieces_to_open(self.document, kind)), len(story.pieces(self.document, kind))
        if not todo:
            self.hover_var.set(ALL_OPEN[kind] if known else "The editor doesn't know any yet.")
            return
        if not messagebox.askyesno(OPEN[kind], open_question(kind, todo, known), default="no", parent=self):
            return
        if not self.on_open(self.document, kind):
            return
        self.listed = sections(self.document, self.atlas)
        self._write()
        self._update_pieces()
        what = ("shortcut" if kind == story.SHORTCUTS else "key gate") + ("" if todo == 1 else "s")
        self.hover_var.set(f"{todo} {what} opened. Press Save to game when you're done.")

    def _write(self) -> None:
        text, gap = self.text, self.fonts["bold"].metrics("linespace")
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.tag_configure("heading", font=self.fonts["bold"], spacing1=gap * 2 // 3, spacing3=gap // 4)
        text.tag_configure("first", spacing1=0)
        # A line that starts with a tick or a dot has its words start where the others' do.
        text.tag_configure("line", lmargin1=gap // 2, lmargin2=gap * 3 // 2, spacing3=1, tabs=(gap * 3 // 2 + 10,))
        for number, (heading, lines) in enumerate(self.listed):
            text.insert("end", heading + "\n", ("heading", "first") if number == 0 else ("heading",))
            for line in lines:
                mark, _gap, rest = line.partition("  ")
                text.insert("end", (f"{mark}\t{rest}" if mark in ("✓", "·") else line) + "\n", ("line",))
        text.configure(state="disabled")

    def shown_text(self) -> str:
        return self.text.get("1.0", "end").strip()

    def list_text(self) -> str:
        """The list as plain text, for the clipboard: each heading, then its lines."""
        return "\n\n".join("\n".join([heading] + [f"  {line}" for line in lines]) for heading, lines in self.listed)

    def copy_list(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.list_text())
        self.hover_var.set("Copied: the list is on the clipboard.")

    def destroy(self) -> None:
        if self._redraw is not None:
            self.after_cancel(self._redraw)
            self._redraw = None
        super().destroy()
