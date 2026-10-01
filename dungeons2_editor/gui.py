"""Tkinter window for browsing and editing Minecraft Dungeons II saves."""

from __future__ import annotations

import copy
import ctypes
import json
import os
import queue
import threading
import time
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any

from . import __version__, codec, merge, paths, saves, wgs, wiki
from . import document as doc
from .hero import HERO_SORTS, Hero, describe_changes, format_amount, is_hero_document
from .hero_tab import HeroTab
from .icons import DEFAULT_ICON_ROOT, WIKI_FOLDER, IconLibrary

APP_TITLE = "Minecraft Dungeons II Save Editor"
SEARCH_LIMIT = 2000
GAME_CHECK_SECONDS = 3
CHANGED_COLOR = "#b35900"
MUTED_COLOR = "#6b7075"

HELP_SECTIONS = [
    (
        "Editing a hero",
        "Pick your offline hero on the left. On the Hero tab:\n"
        "• Stats: type a new number or use the arrows. Changes are kept as you go.\n"
        "• Items: sort by power, level, XP, rarity and more (click a column heading or use Sort by). Pick an item "
        "to change its rarity, power or count, equip or unequip it, turn it into another item, make a copy or delete it.\n"
        "• + Add items: pick any weapon, armor piece, artifact or talisman in the game and choose rarity, power and "
        "how many, and tick Equip it to put it straight on your hero. Pick Unique rarity to get an item's Unique "
        "version. Confirmed items are known to work; for Unconfirmed ones the editor has to guess the game's name "
        "for the item, and a wrong guess may make the game drop it.\n"
        "• Presets: goals (Most money, Most XP, Best loot and more), the most powerful weapon, armor, artifacts and "
        "talismans, and complete kits from top builds. Pick the item power and rarity, and the editor adds and equips "
        "everything and lists the best enchantments to put on each piece at the Enchantsmith.\n"
        "Then press Save to game. Try a small change first and check it in the game.\n\n"
        "Simple mode keeps numbers within the game's caps (for example 9,999 emeralds; anything above is lost in "
        "the game). Online heroes are stored on the game's servers, so no save editor can change them. Cosmetics "
        "from your game edition are shown but can't be changed or copied.",
    ),
    (
        "Advanced mode",
        "Tick Advanced mode at the top to see the technical side: the Edit tab shows every value in the save as a "
        "tree, Raw JSON shows the whole file, the settings save appears on the left, items show their IDs (and you "
        "can type any item ID), and stats may go past the game's caps.",
    ),
    (
        "Pictures",
        "Items show their picture when the icons folder has one, and a square in their rarity's colour when it "
        "doesn't. Get pictures… (on the Hero tab) downloads the Minecraft Wiki's item pictures. You can also add your "
        "own, named after the item, stat or hero skin (MysticHelmet.png, Emeralds.png, RangerDeluxe.png). "
        "The README in the icons folder explains the names.",
    ),
    (
        "Staying safe",
        "• Close Minecraft Dungeons II before saving. The editor will not save while the game is running.\n"
        "• Every save first copies your whole save folder into the backups folder. Restore… puts one back.\n"
        "• If the game saves your hero while the editor is open (say you played to check a change), the editor loads "
        "the new version. If you have unsaved changes, it re-applies them to the new version when you save.\n"
        "• Changes are written the same way the game writes them and are marked for upload, so the Xbox cloud "
        "keeps the edited version.\n"
        "• The sign-in, entitlement and device-ID containers are never read or changed.\n"
        "• Backups contain your sign-in token, so don't share them.",
    ),
    (
        "Where the data comes from",
        "Item names, armor sets, Uniques and enchantments: MetaBot.GG's Minecraft Dungeons II database, which is built "
        "from the game files (https://metabot.gg/en/minecraft-dungeons-2/uniques, /artifacts, /talismans and "
        "/enchantments). Best gear and kits: MetaBot.GG's best builds guide and tier list; each preset links its "
        "pages. Item pictures: the Minecraft Wiki.",
    ),
    (
        "Where the files are",
        "Saves: %LOCALAPPDATA%\\Packages\\Microsoft.MinecraftDungeons2_8wekyb3d8bbwe\\SystemAppData\\wgs\n"
        "Backups: {backups}",
    ),
]


def _short(value: Any, limit: int = 48) -> str:
    text = doc.format_value(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


SETTINGS_FILE = paths.data_dir() / "editor-settings.json"


def _load_settings(path: Path) -> dict:
    try:
        settings = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def _save_settings(path: Path, settings: dict) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass  # only a convenience; the editor works without it


class EditorApp:
    def __init__(
        self,
        root: tk.Tk,
        profile: Path | None = None,
        backup_root: Path = saves.DEFAULT_BACKUP_ROOT,
        icon_root: Path = DEFAULT_ICON_ROOT,
        settings_file: Path = SETTINGS_FILE,
    ):
        self.root = root
        self.backup_root = Path(backup_root)
        self.icons = IconLibrary(icon_root)
        self.settings_file = Path(settings_file)
        self.settings = _load_settings(self.settings_file)
        self._pictures_busy = False
        self.profile: saves.SaveProfile | None = None
        self.container: saves.Container | None = None
        self.original: Any = None  # document as loaded from disk
        self.document: Any = None  # document being edited
        self.change_count = 0
        self.changed_paths: set[tuple] = set()
        self.node_paths: dict[str, tuple] = {}
        self.selected_path: tuple | None = None
        self.game_running: list[str] | None = None  # None until the first check finishes
        self._profile_paths: list[Path] = []
        self._auto_profiles: set[Path] = set()
        self._containers_by_iid: dict[str, saves.Container] = {}
        self._game_results: queue.Queue[list[str]] = queue.Queue()
        self._index_stamp: tuple | None = None  # containers.index as last loaded, to notice the game saving
        self._newer_on_disk = False  # the game saved the container on screen after it was loaded
        self._polls = 0
        self._search_job: str | None = None
        self._poll_job: str | None = None
        self._raw_stale = True
        self._tree_stale = False  # the Edit tree needs rebuilding (the Hero tab changed the document)
        self._hero_stale = False  # the Hero tab needs refreshing (the tree or raw JSON changed it)

        self._setup_style()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Destroy>", self._on_destroy, add="+")
        self._start_game_watch()
        self._load_profiles(select=profile)

    # ------------------------------------------------------------------ layout

    def _setup_style(self) -> None:
        self.root.title(f"{APP_TITLE} {__version__}")
        icon = paths.resource("assets/app.ico")
        if icon.is_file():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass
        self.root.geometry("1240x880")
        self.root.minsize(960, 640)
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=10)
        tkfont.nametofont("TkTextFont").configure(size=10)
        self.bold_font = base.copy()
        self.bold_font.configure(weight="bold")
        self.title_font = base.copy()
        self.title_font.configure(size=14, weight="bold")
        self.mono_font = tkfont.Font(family="Consolas", size=10)
        style.configure("Treeview", rowheight=int(base.metrics("linespace") * 1.55))
        style.configure("Items.Treeview", rowheight=max(30, int(base.metrics("linespace") * 1.9)))
        style.configure("Title.TLabel", font=self.title_font)
        style.configure("Heading.TLabel", font=self.bold_font)
        style.configure("Muted.TLabel", foreground=MUTED_COLOR)
        style.configure("Error.TLabel", foreground="#b3261e")
        style.configure("Warn.TLabel", foreground=CHANGED_COLOR)
        style.configure("Success.TLabel", foreground="#1e7e34")
        style.configure("Changes.TLabel", foreground=CHANGED_COLOR, font=self.bold_font)
        style.configure("Accent.TButton", font=self.bold_font, padding=(14, 4))
        style.configure("Running.TLabel", foreground="#b3261e", font=self.bold_font)
        style.configure("Closed.TLabel", foreground="#1e7e34")

    def _build(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        bar = ttk.Frame(root, padding=(12, 10, 12, 6))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Save profile").pack(side="left")
        self.profile_box = ttk.Combobox(bar, state="readonly", width=44)
        self.profile_box.pack(side="left", padx=(6, 6))
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_selected)
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="left", padx=2)
        ttk.Button(bar, text="Open folder…", command=self._open_folder).pack(side="left", padx=2)
        self.advanced_var = tk.BooleanVar(value=bool(self.settings.get("advanced", False)))
        ttk.Checkbutton(bar, text="Advanced mode", variable=self.advanced_var, command=self._on_advanced_toggled).pack(side="left", padx=(14, 2))
        ttk.Button(bar, text="Backups folder", command=self._open_backups_folder).pack(side="right", padx=2)
        ttk.Button(bar, text="Restore…", command=self._restore_dialog).pack(side="right", padx=2)
        ttk.Button(bar, text="Back up now", command=self._backup_now).pack(side="right", padx=2)

        panes = ttk.PanedWindow(root, orient="horizontal")
        panes.grid(row=1, column=0, sticky="nsew", padx=12)

        left = ttk.Frame(panes, padding=(0, 0, 10, 0))
        heading = ttk.Frame(left)
        heading.pack(fill="x", pady=(0, 4))
        ttk.Label(heading, text="Save data", font=self.bold_font).pack(side="left")
        self.hero_sort_var = tk.StringVar(value="Most powerful")
        hero_sort = ttk.Combobox(heading, textvariable=self.hero_sort_var, values=list(HERO_SORTS), state="readonly", width=15)
        hero_sort.pack(side="right")
        hero_sort.bind("<<ComboboxSelected>>", lambda _event: self._resort_heroes())
        ttk.Label(heading, text="Heroes by", style="Muted.TLabel").pack(side="right", padx=(0, 6))
        self.container_list = ttk.Treeview(left, columns=("status",), selectmode="browse")
        self.container_list.heading("#0", text="Container")
        self.container_list.heading("status", text="Details")
        self.container_list.column("#0", width=175, stretch=True)
        self.container_list.column("status", width=150, stretch=False)
        self.container_list.tag_configure("locked", foreground=MUTED_COLOR)
        self.container_list.tag_configure("group", font=self.bold_font)
        self.container_list.pack(fill="both", expand=True)
        self.container_list.bind("<<TreeviewSelect>>", self._on_container_selected)
        panes.add(left, weight=1)

        right = ttk.Frame(panes)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        panes.add(right, weight=4)
        self.title_var = tk.StringVar(value="No save loaded")
        self.meta_var = tk.StringVar()
        ttk.Label(right, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(right, textvariable=self.meta_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 6))

        self.notebook = ttk.Notebook(right)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        self.hero_tab = HeroTab(
            self.notebook,
            on_change=self._on_hero_changed,
            app_title=APP_TITLE,
            bold_font=self.bold_font,
            icons=self.icons,
            get_pictures=self._get_pictures,
            catalog_heroes=self._other_saved_heroes,
        )
        self.edit_tab = ttk.Frame(self.notebook, padding=10)
        self.raw_tab = ttk.Frame(self.notebook, padding=10)
        self.help_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.hero_tab, text="Hero", state="hidden")
        self.notebook.add(self.edit_tab, text="Edit (advanced)")
        self.notebook.add(self.raw_tab, text="Raw JSON (advanced)")
        self.notebook.add(self.help_tab, text="Help")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._build_edit_tab()
        self._build_raw_tab()
        self._build_help_tab()

        actions = ttk.Frame(right, padding=(0, 10, 0, 0))
        actions.grid(row=3, column=0, sticky="ew")
        self.changes_var = tk.StringVar()
        ttk.Label(actions, textvariable=self.changes_var, style="Changes.TLabel").pack(side="left")
        self.save_button = ttk.Button(actions, text="Save to game", style="Accent.TButton", command=self.save_to_game)
        self.save_button.pack(side="right")
        self.discard_button = ttk.Button(actions, text="Discard changes", command=self.discard_changes)
        self.discard_button.pack(side="right", padx=8)

        status = ttk.Frame(root, padding=(12, 6, 12, 8))
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(1, weight=1)
        self.game_var = tk.StringVar(value="Checking whether the game is running…")
        self.game_label = ttk.Label(status, textvariable=self.game_var, style="Muted.TLabel")
        self.game_label.grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar()
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel", anchor="e").grid(row=0, column=1, sticky="ew", padx=(16, 0))

        self._update_buttons()
        self._apply_mode()

    def _build_edit_tab(self) -> None:
        tab = self.edit_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        self.search_row = ttk.Frame(tab)
        self.search_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(self.search_row, text="Find").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_search())
        ttk.Entry(self.search_row, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=(6, 6))
        ttk.Button(self.search_row, text="Clear", command=lambda: self.search_var.set("")).pack(side="left")

        self.tree_frame = ttk.Frame(tab)
        self.tree_frame.grid(row=1, column=0, sticky="nsew")
        self.tree_frame.columnconfigure(0, weight=1)
        self.tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(self.tree_frame, columns=("value", "type"), selectmode="browse")
        self.tree.heading("#0", text="Field")
        self.tree.heading("value", text="Value")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", width=300, stretch=True)
        self.tree.column("value", width=330, stretch=True)
        self.tree.column("type", width=90, stretch=False)
        scroll = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("changed", foreground=CHANGED_COLOR, font=self.bold_font)
        self.tree.tag_configure("placeholder", foreground=MUTED_COLOR)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        self.message_var = tk.StringVar()
        self.message = ttk.Label(tab, textvariable=self.message_var, wraplength=620, justify="left", padding=(4, 16))

        editor = ttk.LabelFrame(tab, text="Selected value", padding=10)
        editor.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        editor.columnconfigure(1, weight=1)
        self.editor_frame = editor
        self.path_var = tk.StringVar()
        ttk.Label(editor, textvariable=self.path_var, style="Muted.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(editor, text="Value").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.value_var = tk.StringVar()
        self.value_entry = ttk.Entry(editor, textvariable=self.value_var)
        self.value_entry.bind("<Return>", lambda _event: self.apply_value())
        self.value_bool = ttk.Combobox(editor, textvariable=self.value_var, values=("true", "false"), state="readonly")
        self.value_bool.bind("<<ComboboxSelected>>", lambda _event: self.apply_value())
        self.value_entry.grid(row=1, column=1, sticky="ew")
        self.apply_button = ttk.Button(editor, text="Apply", command=self.apply_value)
        self.apply_button.grid(row=1, column=2, padx=(8, 0))
        self._set_editor(None)

    def _build_raw_tab(self) -> None:
        tab = self.raw_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(
            tab,
            text="The whole container as JSON. Edit it here to add or remove entries, then press Apply JSON.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.raw_text = tk.Text(tab, wrap="none", font=self.mono_font, undo=True, relief="solid", borderwidth=1)
        yscroll = ttk.Scrollbar(tab, orient="vertical", command=self.raw_text.yview)
        xscroll = ttk.Scrollbar(tab, orient="horizontal", command=self.raw_text.xview)
        self.raw_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.raw_text.grid(row=1, column=0, sticky="nsew")
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll.grid(row=2, column=0, sticky="ew")
        self.raw_text.tag_configure("error", background="#fde2e1")
        buttons = ttk.Frame(tab)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.raw_apply_button = ttk.Button(buttons, text="Apply JSON", command=self.apply_raw)
        self.raw_apply_button.pack(side="right")
        ttk.Button(buttons, text="Undo raw edits", command=self._refresh_raw).pack(side="right", padx=8)

    def _build_help_tab(self) -> None:
        text = tk.Text(
            self.help_tab,
            wrap="word",
            font=tkfont.nametofont("TkDefaultFont"),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=6,
            pady=4,
            background=self.root.cget("background"),
        )
        text.tag_configure("heading", font=self.bold_font, spacing1=10, spacing3=4)
        text.tag_configure("body", lmargin1=4, lmargin2=4, spacing2=2)
        for heading, body in HELP_SECTIONS:
            text.insert("end", heading + "\n", "heading")
            text.insert("end", body.format(backups=self.backup_root) + "\n", "body")
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- profiles

    def _load_profiles(self, select: Path | None = None) -> None:
        found = saves.find_profiles()
        self._auto_profiles = set(found)
        paths = list(found)
        if select is not None and Path(select) not in paths:
            paths.insert(0, Path(select))
        self._profile_paths = paths
        self.profile_box["values"] = [self._profile_label(path) for path in paths]
        if not paths:
            self.profile = None
            self._fill_container_list()
            self._show_container(None)
            self.title_var.set("No Minecraft Dungeons II saves found")
            self.meta_var.set("Play the game once on this PC, or use Open folder… to pick a save folder.")
            return
        target = Path(select) if select is not None else paths[0]
        self.profile_box.current(paths.index(target))
        self._open_profile(target)

    def _profile_label(self, path: Path) -> str:
        if path in self._auto_profiles:
            return f"Xbox user {path.name.split('_', 1)[0]}"
        return str(path)

    def _open_profile(self, path: Path, keep: str | None = None, profile: saves.SaveProfile | None = None) -> None:
        stamp = self._read_index_stamp(path)
        try:
            profile = profile or saves.SaveProfile(path)
        except (OSError, wgs.WgsFormatError) as exc:
            messagebox.showerror(APP_TITLE, f"Could not read the saves in\n{path}\n\n{exc}", parent=self.root)
            if self.profile is not None and self.profile.path in self._profile_paths:
                self.profile_box.current(self._profile_paths.index(self.profile.path))
            return
        self.profile = profile
        self._index_stamp = stamp
        self._newer_on_disk = False
        self._fill_container_list()
        containers = profile.containers
        advanced = self.advanced_var.get()
        editable = [c for c in containers if c.kind is saves.Kind.EDITABLE]
        heroes = [c for c in editable if c.hero is not None]
        kept = next((c for c in containers if c.name == keep and (advanced or c.hero is not None)), None)
        if advanced:
            target = kept or next(iter(heroes), None) or next(iter(editable), None) or next(iter(containers), None)
        else:
            target = kept or next(iter(heroes), None)
        self._show_container(target)
        self._select_in_list(target)
        self.status_var.set("Loaded your saves.")

    def _other_saved_heroes(self) -> list[Hero]:
        """Heroes in this profile other than the one being edited, as last saved."""
        if self.profile is None:
            return []
        return [c.hero for c in self.profile.containers if c.hero is not None and c is not self.container]

    def _on_advanced_toggled(self) -> None:
        advanced = self.advanced_var.get()
        if not advanced and self.container is not None and self.container.hero is None:
            # Simple mode only shows heroes, so leave the settings save first.
            if not self._confirm_discard():
                self.advanced_var.set(True)
                return
            self.settings["advanced"] = advanced
            _save_settings(self.settings_file, self.settings)
            self._apply_mode()
            if self.profile is not None:
                self._open_profile(self.profile.path)
            return
        self.settings["advanced"] = advanced
        _save_settings(self.settings_file, self.settings)
        self._apply_mode()
        self._fill_container_list()
        self._select_in_list(self.container)
        self._show_meta()

    def _apply_mode(self) -> None:
        """Show the technical tabs and details only in Advanced mode."""
        advanced = self.advanced_var.get()
        if not advanced and self.notebook.select() in (str(self.edit_tab), str(self.raw_tab)):
            hero_shown = self.notebook.tab(self.hero_tab, "state") == "normal"
            self.notebook.select(self.hero_tab if hero_shown else self.help_tab)
        for tab in (self.edit_tab, self.raw_tab):
            self.notebook.tab(tab, state="normal" if advanced else "hidden")
        self.hero_tab.set_advanced(advanced)

    def _fill_container_list(self) -> None:
        self.container_list.delete(*self.container_list.get_children())
        self._containers_by_iid.clear()
        if self.profile is None:
            return
        heroes = [c for c in self.profile.containers if c.hero is not None]
        others = [c for c in self.profile.containers if c.hero is None]
        sort_key = HERO_SORTS[self.hero_sort_var.get()]
        heroes.sort(key=lambda c: sort_key(c.hero), reverse=True)

        group = self.container_list.insert("", "end", text="Heroes", open=True, tags=("group",))
        for container in heroes:
            hero = container.hero
            if container.kind is saves.Kind.EDITABLE:
                details = f"Lv {hero.level} · {format_amount(hero.attribute('Emeralds') or 0)} emeralds"
            else:
                details = "Online (read-only)"
            self._add_container_row(group, container, details)
        if not heroes:
            self.container_list.insert(group, "end", text="No offline heroes yet", tags=("locked",))
        if self.advanced_var.get():
            group = self.container_list.insert("", "end", text="Game data", open=True, tags=("group",))
            for container in others:
                self._add_container_row(group, container, container.kind.value)

    def _add_container_row(self, parent: str, container: saves.Container, details: str) -> None:
        locked = container.kind is not saves.Kind.EDITABLE
        hero = container.hero
        text = (hero.skin or f"Hero {hero.character_id[:8]}") if hero is not None else container.label
        picture = self.icons.image(hero.skin, 18) if hero is not None and hero.skin else None
        iid = self.container_list.insert(
            parent, "end", text=text, image=picture or "", values=(details,), tags=("locked",) if locked else ()
        )
        self._containers_by_iid[iid] = container

    def _resort_heroes(self) -> None:
        self._fill_container_list()
        self._select_in_list(self.container)

    def _select_in_list(self, container: saves.Container | None) -> None:
        for iid, candidate in self._containers_by_iid.items():
            if candidate is container:
                self.container_list.selection_set(iid)
                self.container_list.see(iid)
                return

    def _on_profile_selected(self, _event: tk.Event) -> None:
        path = self._profile_paths[self.profile_box.current()]
        if self.profile is not None and path == self.profile.path:
            return
        if not self._confirm_discard():
            self.profile_box.current(self._profile_paths.index(self.profile.path))
            return
        self._open_profile(path)

    def _on_container_selected(self, _event: tk.Event) -> None:
        selection = self.container_list.selection()
        if not selection:
            return
        container = self._containers_by_iid.get(selection[0])
        if container is None:  # a group heading or placeholder row
            self._select_in_list(self.container)
            return
        if container is self.container:
            return
        if not self._confirm_discard():
            self._select_in_list(self.container)
            return
        self._show_container(container)

    def reload(self) -> None:
        if not self._confirm_discard():
            return
        self.icons.reload()
        if self.profile is None:
            self._load_profiles()
        else:
            self._open_profile(self.profile.path, keep=self.container.name if self.container else None)

    def _open_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Choose a folder that contains containers.index", parent=self.root)
        if not chosen:
            return
        path = Path(chosen)
        if not (path / wgs.INDEX_FILE).is_file():
            messagebox.showerror(APP_TITLE, f"{path} has no {wgs.INDEX_FILE} file.", parent=self.root)
            return
        if self._confirm_discard():
            self._load_profiles(select=path)

    # -------------------------------------------------------------- containers

    def _show_container(self, container: saves.Container | None) -> None:
        self.container = container
        self.selected_path = None
        editable = container is not None and container.kind is saves.Kind.EDITABLE and container.decoded is not None
        if editable:
            self.original = container.decoded.document
            self.document = copy.deepcopy(self.original)
        else:
            self.original = self.document = None

        self._show_meta()

        if editable:
            self.message.grid_remove()
            self.search_row.grid()
            self.tree_frame.grid()
            self.editor_frame.grid()
        else:
            self.search_row.grid_remove()
            self.tree_frame.grid_remove()
            self.editor_frame.grid_remove()
            self.message_var.set(self._locked_message(container))
            self.message.grid(row=1, column=0, sticky="nw")

        self._set_search_silently("")
        self.status_var.set("")
        self._rebuild_tree()
        self._load_hero_tab(select=True)
        self._update_changes()
        self._raw_stale = True
        if self._raw_tab_visible():
            self._refresh_raw()

    def _show_meta(self) -> None:
        """The title and the line under it: friendly in Simple mode, technical in Advanced mode."""
        container = self.container
        if container is None:
            if self.profile is not None and not self.advanced_var.get():
                self.title_var.set("No offline heroes yet")
                self.meta_var.set("Create an offline hero in the game, play until it saves, close the game, then press Reload.")
            else:
                self.title_var.set("No save loaded")
                self.meta_var.set("")
            return
        entry = container.entry
        when = datetime.fromtimestamp(wgs.filetime_to_unix(entry.mtime))
        self.title_var.set(container.label)
        if self.advanced_var.get():
            sync = wgs.SYNC_STATE_NAMES.get(entry.sync_state, f"sync state {entry.sync_state}")
            meta = f"{container.name} · revision {entry.revision} · {entry.size:,} bytes · written {when:%Y-%m-%d %H:%M} · {sync}"
            if container.decoded is not None and not container.decoded.exact:
                meta += " · formatting will be tidied when saved"
        else:
            meta = f"Last saved {when:%d %B %Y at %H:%M}"
            if entry.sync_state != wgs.SYNCED:
                meta += " · waiting to upload to the Xbox cloud (it will next time you play)"
        self.meta_var.set(meta)

    def _load_hero_tab(self, select: bool = False) -> None:
        """Point the Hero tab at the document being edited; hide it unless that's a hero."""
        hero = Hero(self.document) if self.document is not None and is_hero_document(self.document) else None
        self.hero_tab.load(hero)
        self._hero_stale = False
        if hero is not None:
            self.notebook.tab(self.hero_tab, state="normal")
            if select:
                self.notebook.select(self.hero_tab)
        else:
            if self.notebook.select() == str(self.hero_tab):
                self.notebook.select(self.edit_tab)
            self.notebook.tab(self.hero_tab, state="hidden")

    def _on_hero_changed(self) -> None:
        self._tree_stale = True
        self._raw_stale = True
        self._update_changes()

    def _locked_message(self, container: saves.Container | None) -> str:
        if container is None:
            return "Nothing to show."
        if container.kind is saves.Kind.PROTECTED:
            return f"{container.note}\n\nThis container belongs to the game's online services, so the editor leaves it alone."
        return f"{container.note}\n\nOnly containers the editor can decode are shown and edited."

    # -------------------------------------------------------------------- tree

    def _rebuild_tree(self) -> None:
        self._tree_stale = False
        self.tree.delete(*self.tree.get_children())
        self.node_paths.clear()
        self.selected_path = None
        self._set_editor(None)
        if self.document is None:
            return
        query = self.search_var.get().strip().lower()
        if query:
            self._build_filtered(query)
            return
        self._add_children("", (), self.document)
        top_level = self.tree.get_children("")
        if len(top_level) <= 3:
            for iid in top_level:
                self._expand(iid)

    def _add_children(self, parent: str, path: tuple, value: Any) -> None:
        for key, child in doc.children(value):
            self._add_node(parent, path + (key,), key, child)

    def _add_node(self, parent: str, path: tuple, key: str | int, value: Any, lazy: bool = True) -> str:
        shown = doc.format_value(value)
        if len(shown) > 300:
            shown = shown[:299] + "…"
        iid = self.tree.insert(
            parent,
            "end",
            text=doc.label(key, value),
            values=(shown, doc.type_name(value)),
            tags=("changed",) if path in self.changed_paths else (),
        )
        self.node_paths[iid] = path
        if lazy and isinstance(value, (dict, list)) and value:
            self.tree.insert(iid, "end", text="Loading…", tags=("placeholder",))
        return iid

    def _fill_lazy(self, iid: str) -> None:
        children = self.tree.get_children(iid)
        if len(children) == 1 and "placeholder" in self.tree.item(children[0], "tags"):
            self.tree.delete(children[0])
            path = self.node_paths[iid]
            self._add_children(iid, path, doc.get_at(self.document, path))

    def _expand(self, iid: str) -> None:
        self._fill_lazy(iid)
        self.tree.item(iid, open=True)

    def _on_tree_open(self, _event: tk.Event) -> None:
        iid = self.tree.focus()
        if iid in self.node_paths:
            self._fill_lazy(iid)

    def _build_filtered(self, query: str) -> None:
        visible: set[tuple] = set()
        matches = 0
        for path, key, value in doc.walk(self.document):
            haystack = doc.label(key, value).lower()
            if not isinstance(value, (dict, list)):
                haystack += "\n" + doc.format_value(value).lower()
            if query in haystack:
                matches += 1
                visible.update(path[:depth] for depth in range(1, len(path) + 1))
                if matches >= SEARCH_LIMIT:
                    break
        self._add_filtered("", (), self.document, visible)
        if matches >= SEARCH_LIMIT:
            self.status_var.set(f"Showing the first {SEARCH_LIMIT} matches. Type more to narrow it down.")
        else:
            self.status_var.set(f"{matches} match{'es' if matches != 1 else ''} for “{query}”")

    def _add_filtered(self, parent: str, path: tuple, value: Any, visible: set[tuple]) -> None:
        for key, child in doc.children(value):
            child_path = path + (key,)
            if child_path not in visible:
                continue
            iid = self._add_node(parent, child_path, key, child, lazy=False)
            if isinstance(child, (dict, list)) and child:
                self._add_filtered(iid, child_path, child, visible)
                if self.tree.get_children(iid):
                    self.tree.item(iid, open=True)
                else:
                    self.tree.insert(iid, "end", text="Loading…", tags=("placeholder",))

    def _schedule_search(self) -> None:
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(250, self._run_search)

    def _run_search(self) -> None:
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)  # harmless if this is that job running
            self._search_job = None
        self._rebuild_tree()
        if not self.search_var.get().strip():
            self.status_var.set("")

    def _set_search_silently(self, text: str) -> None:
        self.search_var.set(text)
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
            self._search_job = None

    # ------------------------------------------------------------ value editor

    def _on_tree_select(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        self.selected_path = self.node_paths.get(selection[0]) if selection else None
        self._set_editor(self.selected_path)

    def _on_tree_double_click(self, _event: tk.Event) -> None:
        if self.selected_path is None:
            return
        value = doc.get_at(self.document, self.selected_path)
        if not isinstance(value, (dict, list, bool)):
            self.value_entry.focus_set()
            self.value_entry.select_range(0, "end")

    def _show_value_widget(self, widget: ttk.Widget) -> None:
        other = self.value_bool if widget is self.value_entry else self.value_entry
        other.grid_remove()
        widget.grid(row=1, column=1, sticky="ew")

    def _set_editor(self, path: tuple | None) -> None:
        if path is None or self.document is None:
            self.path_var.set("Select a value in the list above to change it.")
            self.value_var.set("")
            self._show_value_widget(self.value_entry)
            self.value_entry.state(["disabled"])
            self.apply_button.state(["disabled"])
            return
        value = doc.get_at(self.document, path)
        where = doc.describe_path(self.document, path)
        if isinstance(value, (dict, list)):
            self.path_var.set(f"{where}  —  open it and pick a single value, or use Raw JSON to add or remove entries.")
            self.value_var.set(doc.format_value(value))
            self._show_value_widget(self.value_entry)
            self.value_entry.state(["disabled"])
            self.apply_button.state(["disabled"])
            return
        self.path_var.set(f"{where}  ({doc.type_name(value)})")
        self.value_var.set(doc.format_value(value))
        if isinstance(value, bool):
            self._show_value_widget(self.value_bool)
        else:
            self._show_value_widget(self.value_entry)
            self.value_entry.state(["!disabled"])
        self.apply_button.state(["!disabled"])

    def apply_value(self) -> None:
        path = self.selected_path
        if path is None or self.document is None:
            return
        old = doc.get_at(self.document, path)
        if isinstance(old, (dict, list)):
            return
        try:
            new = doc.parse_input(self.value_var.get(), old)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return
        doc.set_at(self.document, path, new)
        self._refresh_row(path)
        self._update_changes()
        self._raw_stale = True
        self._hero_stale = True
        self._set_editor(path)

    def _refresh_row(self, path: tuple) -> None:
        for iid, node_path in self.node_paths.items():
            if node_path == path:
                value = doc.get_at(self.document, path)
                self.tree.item(iid, text=doc.label(path[-1], value), values=(doc.format_value(value), doc.type_name(value)))
            elif node_path == path[:-1] and node_path:
                parent = doc.get_at(self.document, node_path)
                self.tree.item(iid, text=doc.label(node_path[-1], parent))

    # ----------------------------------------------------------------- changes

    def _update_changes(self) -> None:
        changes = doc.diff(self.original, self.document) if self.document is not None else []
        self.change_count = len(changes)
        self.changed_paths = {path[:depth] for path, _, _ in changes for depth in range(len(path) + 1)}
        for iid, path in self.node_paths.items():
            self.tree.item(iid, tags=("changed",) if path in self.changed_paths else ())
        if self.change_count:
            self.changes_var.set(f"{self.change_count} unsaved change{'s' if self.change_count != 1 else ''}")
        else:
            self.changes_var.set("")
        self._update_buttons()

    def _update_buttons(self) -> None:
        dirty = self.change_count > 0
        self.save_button.state(["!disabled"] if dirty and not self.game_running else ["disabled"])
        self.discard_button.state(["!disabled"] if dirty else ["disabled"])

    def _confirm_discard(self) -> bool:
        self.hero_tab.commit_pending()
        if not self.change_count:
            return True
        return messagebox.askyesno(APP_TITLE, "You have unsaved changes. Throw them away?", parent=self.root)

    def discard_changes(self) -> None:
        if not self.change_count or not self._confirm_discard():
            return
        self.document = copy.deepcopy(self.original)
        self._rebuild_tree()
        self._load_hero_tab()
        self._update_changes()
        self._raw_stale = True
        if self._raw_tab_visible():
            self._refresh_raw()

    def _change_lines(self, changes: list) -> list[str]:
        """The changes to list before saving: plain English for heroes, save-file paths otherwise."""
        friendly = describe_changes(self.original, self.document) if is_hero_document(self.document) else []
        if friendly:
            lines = [f"• {line}" for line in friendly]
            if self.advanced_var.get():
                lines.append(f"({len(changes)} value{'s' if len(changes) != 1 else ''} change in the save file.)")
            return lines
        lines = []
        for path, old, new in changes:
            where = doc.describe_path(self.original if new is doc.MISSING else self.document, path)
            lines.append(f"• {where}: {_short(old)} → {_short(new)}")
        return lines

    def save_to_game(self) -> None:
        if self.profile is None or self.container is None or self.document is None:
            return
        if not self.hero_tab.commit_pending():
            return  # the Hero tab shows what's wrong
        changes = doc.diff(self.original, self.document)
        if not changes:
            return
        lines = self._change_lines(changes)
        if len(lines) > 14:
            lines = lines[:13] + [f"… and {len(lines) - 13} more"]
        question = f"Save these changes to {self.container.label}?\n\n" + "\n".join(lines) + "\n\nYour current saves are backed up first."
        if not messagebox.askyesno("Save to game", question, parent=self.root):
            return
        name = self.container.name
        try:
            backup = self.profile.save(name, self.document, self.backup_root)
        except saves.StaleSaveError:
            self._reapply_to_newer_save(name)
            return
        except saves.GameRunningError as exc:
            messagebox.showwarning(APP_TITLE, str(exc), parent=self.root)
            return
        except saves.SaveFailedError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return
        except Exception as exc:  # nothing was written; see SaveProfile.save
            messagebox.showerror(APP_TITLE, f"Could not save: {exc}\n\nYour saves were not changed.", parent=self.root)
            return
        self.change_count = 0
        self._open_profile(self.profile.path, keep=name)
        self.status_var.set(f"Saved. Previous version backed up to {backup}")
        messagebox.showinfo(
            APP_TITLE,
            "Saved! Start the game to see your changes.\n\n"
            "If anything looks wrong, close the game and use Restore… to go back. "
            f"The previous version was backed up to:\n{backup}",
            parent=self.root,
        )

    def _reapply_to_newer_save(self, name: str) -> None:
        """The game saved this container after it was loaded: re-apply the edits to the newer save."""
        label = self.container.label
        if not messagebox.askyesno(
            "Newer save found",
            f"Minecraft Dungeons II saved {label} after the editor loaded it, probably while you were playing.\n\n"
            "The editor will load that newer save and re-apply your changes to it, so you keep both. You'll see the "
            "list of changes again before anything is saved.",
            parent=self.root,
        ):
            return
        try:
            newer = saves.SaveProfile(self.profile.path)
        except (OSError, wgs.WgsFormatError) as exc:
            messagebox.showerror(APP_TITLE, f"Could not read the newer save:\n{exc}", parent=self.root)
            return
        container = newer.get(name)
        if container is None or container.kind is not saves.Kind.EDITABLE or container.decoded is None:
            messagebox.showerror(APP_TITLE, f"{label} can't be edited any more.", parent=self.root)
            return
        merged, problems = merge.reapply(self.original, self.document, container.decoded.document)
        self.change_count = 0  # the edits now live in ``merged``
        self._open_profile(newer.path, keep=name, profile=newer)
        self._set_document(merged)
        if problems:
            shown = problems[:12] + ([f"… and {len(problems) - 12} more"] if len(problems) > 12 else [])
            messagebox.showwarning(
                "Some changes couldn't be re-applied", "\n".join(f"• {problem}" for problem in shown), parent=self.root
            )
        if self.change_count:
            self.save_to_game()
        else:
            messagebox.showinfo(APP_TITLE, "The newer save already has all of your changes. Nothing to save.", parent=self.root)

    def _set_document(self, document: Any) -> None:
        """Show ``document`` as the edited version of the container on screen."""
        self.document = document
        self._rebuild_tree()
        self._load_hero_tab()
        self._update_changes()
        self._raw_stale = True
        if self._raw_tab_visible():
            self._refresh_raw()

    # ---------------------------------------------------------------- raw JSON

    def _raw_tab_visible(self) -> bool:
        return self.notebook.select() == str(self.raw_tab)

    def _on_tab_changed(self, _event: tk.Event) -> None:
        current = self.notebook.select()
        if current == str(self.raw_tab) and self._raw_stale:
            self._refresh_raw()
        elif current == str(self.edit_tab) and self._tree_stale:
            self._rebuild_tree()
        elif current == str(self.hero_tab) and self._hero_stale:
            self._hero_stale = False
            self.hero_tab.refresh()

    def _refresh_raw(self) -> None:
        self.raw_text.configure(state="normal")
        self.raw_text.delete("1.0", "end")
        if self.document is None:
            self.raw_text.insert("1.0", "This container is not shown.")
            self.raw_text.configure(state="disabled")
            self.raw_apply_button.state(["disabled"])
        else:
            self.raw_text.insert("1.0", json.dumps(self.document, indent=2, ensure_ascii=False))
            self.raw_apply_button.state(["!disabled"])
        self.raw_text.edit_reset()
        self._raw_stale = False

    def apply_raw(self) -> None:
        if self.document is None:
            return
        text = self.raw_text.get("1.0", "end-1c")
        self.raw_text.tag_remove("error", "1.0", "end")
        try:
            new_document = json.loads(text)
            codec.dumps(new_document)  # rejects NaN and infinity
        except json.JSONDecodeError as exc:
            self.raw_text.tag_add("error", f"{exc.lineno}.0", f"{exc.lineno}.end")
            self.raw_text.see(f"{exc.lineno}.0")
            messagebox.showerror(APP_TITLE, f"That is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno}).", parent=self.root)
            return
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return
        self.document = new_document
        self._rebuild_tree()
        self._load_hero_tab()
        self._update_changes()
        self.status_var.set("Raw JSON applied. Press Save to game to write it.")

    # ----------------------------------------------------------------- backups

    def _backup_now(self) -> None:
        if self.profile is None:
            return
        try:
            path = saves.make_backup(self.profile.path, self.backup_root, "Manual backup")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Backup failed: {exc}", parent=self.root)
            return
        self.status_var.set(f"Backed up to {path}")

    def _open_backups_folder(self) -> None:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        os.startfile(self.backup_root)

    def _restore_dialog(self) -> None:
        if self.profile is None:
            return
        backups = [b for b in saves.list_backups(self.backup_root) if b.profile_copy.name == self.profile.path.name]
        if not backups:
            messagebox.showinfo(APP_TITLE, "There are no backups of this save profile yet.", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Restore a backup")
        dialog.transient(self.root)
        dialog.geometry("640x380")
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Pick the backup to put back. Your current saves are backed up first.").pack(anchor="w", pady=(0, 8))
        listing = ttk.Treeview(frame, columns=("reason",), selectmode="browse")
        listing.heading("#0", text="Made")
        listing.heading("reason", text="Why")
        listing.column("#0", width=170, stretch=False)
        listing.column("reason", width=400)
        listing.pack(fill="both", expand=True)
        by_iid = {}
        for backup in backups:
            iid = listing.insert("", "end", text=f"{backup.created:%Y-%m-%d %H:%M:%S}", values=(backup.reason,))
            by_iid[iid] = backup
        first = listing.get_children()[0]
        listing.selection_set(first)
        listing.focus(first)

        def restore() -> None:
            selection = listing.selection()
            if not selection:
                return
            backup = by_iid[selection[0]]
            if not self._confirm_discard():
                return
            if not messagebox.askyesno(
                "Restore", f"Put back the save data from {backup.created:%Y-%m-%d %H:%M:%S}?\n({backup.reason})", parent=dialog
            ):
                return
            try:
                restored = self.profile.restore(backup, self.backup_root)
            except saves.GameRunningError as exc:
                messagebox.showwarning(APP_TITLE, str(exc), parent=dialog)
                return
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)
                return
            dialog.destroy()
            if not restored:
                messagebox.showinfo(APP_TITLE, "Nothing to restore: that backup matches your current save data.", parent=self.root)
                return
            self.change_count = 0
            self._open_profile(self.profile.path, keep=self.container.name if self.container else None)
            labels = ", ".join(saves.FRIENDLY_NAMES.get(name, name) for name in restored)
            self.status_var.set(f"Restored {labels}")
            messagebox.showinfo(APP_TITLE, f"Restored: {labels}", parent=self.root)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Restore", style="Accent.TButton", command=restore).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=8)
        dialog.grab_set()

    # ---------------------------------------------------------------- pictures

    def _in_background(self, work: Any, done: Any, progress: queue.Queue | None = None) -> None:
        """Run ``work()`` on a thread, then call ``done(ok, result)`` on the UI thread."""
        results: queue.Queue = queue.Queue()

        def run() -> None:
            try:
                results.put((True, work()))
            except Exception as exc:  # reported to the user by done()
                results.put((False, exc))

        def poll() -> None:
            while progress is not None and not progress.empty():
                number, total, name = progress.get_nowait()
                self.status_var.set(f"Downloading pictures {number}/{total}: {name}")
            if results.empty():
                self.root.after(150, poll)
            else:
                done(*results.get_nowait())

        threading.Thread(target=run, name="background", daemon=True).start()
        poll()

    def _get_pictures(self) -> None:
        """Download item pictures from minecraft.wiki, after asking."""
        if self._pictures_busy:
            return
        self._pictures_busy = True
        self.status_var.set("Asking minecraft.wiki which item pictures it has…")
        self._in_background(wiki.list_pictures, self._on_pictures_listed)

    def _on_pictures_listed(self, ok: bool, result: Any) -> None:
        if not ok:
            self._pictures_busy = False
            self.status_var.set("")
            messagebox.showerror(APP_TITLE, f"Couldn't get the picture list from minecraft.wiki:\n{result}", parent=self.root)
            return
        folder = self.icons.ensure_folder() / WIKI_FOLDER
        missing = []
        for picture in result:
            target = folder / wiki.file_name(picture)
            if not (target.exists() and target.stat().st_size == picture.size):
                missing.append(picture)
        if not missing:
            self._pictures_busy = False
            self.status_var.set("")
            messagebox.showinfo(APP_TITLE, f"You already have all {len(result)} pictures minecraft.wiki has.", parent=self.root)
            return
        size = sum(picture.size for picture in missing) / 1e6
        question = (
            f"Download {len(missing)} item pictures ({size:.1f} MB) from minecraft.wiki into\n{folder}?\n\n"
            "They're Mojang's artwork from the Minecraft Wiki, kept on your PC for your own use."
        )
        if not messagebox.askyesno(APP_TITLE, question, parent=self.root):
            self._pictures_busy = False
            self.status_var.set("")
            return
        progress: queue.Queue = queue.Queue()

        def download() -> tuple[int, int]:
            return wiki.download_pictures(missing, folder, lambda *step: progress.put(step))

        self._in_background(download, self._on_pictures_downloaded, progress)

    def _on_pictures_downloaded(self, ok: bool, result: Any) -> None:
        self._pictures_busy = False
        self.icons.reload()
        self.hero_tab.refresh()
        self._resort_heroes()
        if ok:
            self.status_var.set(f"Downloaded {result[0]} pictures from minecraft.wiki.")
        else:
            self.status_var.set("")
            messagebox.showerror(APP_TITLE, f"Downloading pictures stopped:\n{result}", parent=self.root)

    # -------------------------------------------------------------- game watch

    def _start_game_watch(self) -> None:
        def watch() -> None:
            while not self._closing.is_set():
                self._game_results.put(saves.running_game_processes())
                self._closing.wait(GAME_CHECK_SECONDS)

        self._closing = threading.Event()
        threading.Thread(target=watch, name="game-watch", daemon=True).start()
        self._poll_game_results()

    def _poll_game_results(self) -> None:
        latest = None
        while not self._game_results.empty():
            latest = self._game_results.get_nowait()
        if latest is not None and latest != self.game_running:
            self.game_running = latest
            if latest:
                self.game_var.set("●  Minecraft Dungeons II is running. Close it before saving.")
                self.game_label.configure(style="Running.TLabel")
            else:
                self.game_var.set("●  Game is closed. Saving is allowed.")
                self.game_label.configure(style="Closed.TLabel")
            self._update_buttons()
        self._polls += 1
        if self._polls % 4 == 0:  # every 2 seconds
            self._check_disk()
        self._poll_job = self.root.after(500, self._poll_game_results)

    @staticmethod
    def _read_index_stamp(path: Path) -> tuple | None:
        try:
            stat = (Path(path) / wgs.INDEX_FILE).stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _check_disk(self) -> None:
        """Notice when the game saved the container on screen after it was loaded. With nothing
        unsaved, load the new version; otherwise say so (saving then re-applies the edits)."""
        if self.profile is None or self.container is None or self.game_running is None or self.game_running:
            return  # while the game runs it keeps saving; look again once it's closed
        stamp = self._read_index_stamp(self.profile.path)
        if stamp is None or stamp == self._index_stamp:
            return
        try:
            entry = wgs.read_index(self.profile.path).find(self.container.name)
        except (OSError, wgs.WgsFormatError):
            return  # caught in the middle of a write; look again next time
        self._index_stamp = stamp
        if entry is None or entry.revision == self.container.entry.revision:
            return  # only the upload state changed
        if self.change_count == 0 and not self.hero_tab.has_pending_input():
            self._open_profile(self.profile.path, keep=self.container.name)
            self.status_var.set("The game saved this hero since it was loaded, so the editor loaded the new version.")
        elif not self._newer_on_disk:
            self._newer_on_disk = True
            self.status_var.set("The game saved this hero after you loaded it. When you save, your changes are re-applied to the new version.")

    def _on_close(self) -> None:
        if self._confirm_discard():
            self.root.destroy()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self.root:
            self._closing.set()
            for job in (self._poll_job, self._search_job):
                if job is not None:
                    self.root.after_cancel(job)


def _enable_dpi_awareness() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def run(
    profile: Path | None = None,
    backup_root: Path = saves.DEFAULT_BACKUP_ROOT,
    icon_root: Path = DEFAULT_ICON_ROOT,
    close_after: float | None = None,
) -> int:
    """Open the editor window. ``close_after`` (seconds) closes it again, for checking a build starts."""
    _enable_dpi_awareness()
    root = tk.Tk()
    failures: list[str] = []

    def report(exc_type, exc, tb) -> None:
        failures.append("".join(traceback.format_exception(exc_type, exc, tb)))
        if close_after is None:
            messagebox.showerror(APP_TITLE, failures[-1], parent=root)

    root.report_callback_exception = report
    try:
        EditorApp(root, profile, backup_root, icon_root)
    except Exception:
        if close_after is None:
            messagebox.showerror(APP_TITLE, traceback.format_exc(), parent=root)
        root.destroy()
        return 1
    if close_after is not None:
        root.after(int(close_after * 1000), root.destroy)
    root.mainloop()
    return 1 if failures else 0
