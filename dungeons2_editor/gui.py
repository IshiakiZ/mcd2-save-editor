"""Tkinter window for browsing and editing Minecraft Dungeons II saves."""

from __future__ import annotations

import copy
import ctypes
import json
import os
import queue
import re
import threading
import tkinter as tk
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any

from . import __version__, codec, edition, game_style, merge, paths, saves, share_ids, updater, wgs, wiki
from . import document as doc
from .ai_dialog import ConnectAiDialog
from .game_art import Art
from .game_style import GameFonts
from .hero import HERO_SORTS, Hero, describe_changes, format_amount, format_caution, is_hero_document, use_local_names
from .hero_tab import HeroTab
from .icons import DEFAULT_ICON_ROOT, WIKI_FOLDER, IconLibrary
from .inventory_screen import InventoryScreen
from .layout import scaled_size, screen_room
from .my_items import NAMES_FILE, load_names
from .restore_dialog import RestoreDialog

APP_TITLE = "Minecraft Dungeons II Save Editor"
SEARCH_LIMIT = 2000
START_SIZE = (1280, 880)  # on a display at 100%; see layout.scaled_size
MIN_SIZE = (960, 640)
GAME_CHECK_SECONDS = 3
CHANGED_COLOR = "#b35900"
MUTED_COLOR = "#6b7075"
# More from the same developer, linked from the menu, both Help pages and the README.
MORE_FROM_DEVELOPER = (
    ("Lemma", "a free creative studio for Minecraft", "https://lemma.ishiakiz.com"),
    ("Batchly", "free browser games, tools and experiments", "https://batch-ly.com"),
)
MORE_TEXT = "\n".join(f"• {name}, {what}: {url}" for name, what, url in MORE_FROM_DEVELOPER)

_SAFE_TEXT = (
    "• Close Minecraft Dungeons II before saving. The editor will not save while the game is running.\n"
    "• Every save first copies your whole save folder into the backups folder. {restore} puts one back.\n"
    "• If the game saves your hero while the editor is open (say you played to check a change), the editor loads "
    "the new version. If you have unsaved changes, it re-applies them to the new version when you save.\n"
    "• Xbox app: changes are written the way the game writes them and marked for upload, so the Xbox cloud "
    "keeps the edited version. Steam: the .sav file is replaced in place; if Steam Cloud is on, Steam uploads "
    "it the next time the game closes.\n"
    "• If the game, the Xbox app or Steam asks which save to keep, the cloud's or this PC's, keep this PC's: "
    "that's the one with your changes.\n"
    "• The sign-in, entitlement and device-ID containers are never read or changed.\n"
    "• Backups contain your sign-in token, so don't share them.\n"
) + (
    "• When the editor opens, it asks GitHub whether a newer version is out, and shows an Update button if one "
    "is. That request says nothing about you or your saves. Update downloads the new version, checks it and "
    "replaces the editor; your saves, backups, pictures and settings aren't touched."
    if edition.ONLINE
    else f"• This edition of the editor, from {edition.NAME}, never goes online: it doesn't look for updates and it "
    f"doesn't download anything. New versions are on {edition.NAME}. Links open in your own browser."
)
# What the edition that never goes online says where the other one downloads the Minecraft Wiki's pictures.
_NO_PICTURES = (
    edition.offline_note("download pictures")
    + " In the game, press Windows+Shift+S and drag around an item's tile, then pick the item here and paste the "
    "picture; or put pictures in the icons folder yourself, named after the item (MysticHelmet.png)."
)
_DATA_TEXT = (
    "Item names, armor sets, Uniques and enchantments: MetaBot.GG's Minecraft Dungeons II database, which is built "
    "from the game files (https://metabot.gg/en/minecraft-dungeons-2/uniques, /artifacts, /talismans and "
    "/enchantments). What the game calls a gear effect and its number at each tier, what an enchantment does and "
    "costs, and the XP a talisman level takes: its /effects, /guides/enchanting-guide and /talismans pages. How "
    "effects and enchantments are saved comes from real saves only. Best gear and kits: MetaBot.GG's best builds "
    "guide and tier list; each preset links its pages. Item pictures: the Minecraft Wiki."
)
_FILES_TEXT = (
    "Saves (Xbox app): %LOCALAPPDATA%\\Packages\\Microsoft.MinecraftDungeons2_8wekyb3d8bbwe\\SystemAppData\\wgs\n"
    "Saves (Steam): %LOCALAPPDATA%\\Dungeons2\\Saved\\SaveGames (on Linux, inside the game's Proton prefix)\n"
    "Backups: {backups}"
)

# Simple mode's Help page.
SIMPLE_HELP_SECTIONS = [
    (
        "Editing your hero",
        "This screen is laid out like the game's inventory.\n"
        "• Your gear is on the left: weapons, armor, artifacts and talismans. Click a tile to see it on the card on "
        "the right. Double-click an empty slot to put an item in it.\n"
        "• The rest of your inventory is in the middle. Pick a filter to see one kind of item, or MERCHANT for the "
        "Village Merchant's stock. Double-click an item to put it on, and right-click any tile for its actions.\n"
        "• The card shows the item's power and rarity. Click a rarity or type a power to change it, and use the "
        "buttons to equip it, copy it, change it into another item or delete it.\n"
        "• The card lists the item's effects. CHANGE EFFECTS… gives a weapon, armor piece or artifact the effects "
        "you pick (the game rolls a Rare item one and a Special item two, and never more than four) and a weapon or "
        "armor piece an enchantment. The editor writes these exactly as a real save holds them, so it offers the ones "
        "it has seen so far and anything on an item in your own saves; Share item IDs sends it the ones on your gear. "
        "A Unique comes with an effect of its own, the one its card describes. The editor adds it with the Unique, saved "
        "the way the game saves it, for the Uniques it has seen it on; for the rest it says the Unique is added "
        "without. A Unique from an older version of the editor is without it too: its card says so, and ADD ITS OWN "
        "EFFECT puts it right. "
        "On a talisman the button is READY TO LEVEL UP: it puts the talisman one XP short of its next level, and the "
        "game levels it up the next time you earn XP with it on.\n"
        "• Level, XP and gear power are along the top, and enchantment points, emeralds and echo shards are in the "
        "top bar. Click a number to change it (the arrow keys change it by one). STATS & TOWN lists every stat, "
        "with the town upgrades, and says which of the three town vendors this hero has unlocked.\n"
        "• + ADD ITEMS adds any weapon, armor piece, artifact or talisman in the game at the rarity and power you "
        "pick. Pick Unique to get an item's Unique version. PRESETS sets your hero up in one go: goals like Most "
        "money, the most powerful gear, or complete kits from top builds. A kit's gear comes with effects, and with "
        "enchantments once your hero has unlocked the Enchantsmith in the game.\n"
        "Then press SAVE TO GAME. Try a small change first and check it in the game.\n\n"
        "Simple mode keeps numbers within the game's caps (for example 99,999 emeralds; anything above is lost in "
        "the game) and opens gear slots with your level, as the game does. Online heroes are stored on the game's "
        "servers, so no save editor can change them. Cosmetics from your game edition can't be changed.",
    ),
    (
        "Advanced mode",
        "Tick ADVANCED MODE in the top bar for the technical side: every item in a sortable list, every value in the "
        "save as a tree, the raw JSON, the settings save, item IDs (and typing any item ID), and stats past the "
        "game's caps.",
    ),
    (
        "Let an AI do it",
        "Connect an AI (in MENU, or the button above) shows how to let an AI assistant such as Claude use the editor "
        "over MCP. It can look at your heroes and change them for you, and its changes are only written when you "
        "agree, with the game closed and a backup made first.",
    ),
    (
        "Pictures",
        "Items show their picture when the icons folder has one, and an icon in their rarity's colour when it "
        "doesn't. "
        + (
            "Get item pictures… in MENU downloads the Minecraft Wiki's item pictures (run it again now and then "
            "for new ones). For an item it doesn't have, take your own: "
            if edition.ONLINE
            else "This edition never goes online, so it doesn't download pictures. Take your own: "
        )
        + "in the game, press Windows+Shift+S and drag around "
        "the item's tile, then pick the item here and press PASTE PICTURE. The editor cuts the item out and keeps it "
        "on this PC. You can also put pictures in the icons folder yourself, named after the item, stat or hero skin "
        "(MysticHelmet.png, Emeralds.png, RangerDeluxe.png).",
    ),
    (
        "Item names",
        "Names come from the game's item list, so new items you pick up show their names. When the editor doesn't "
        "know what the game calls an item, its card says its name is made from its save ID: press NAME IT… and type "
        "the name the game shows. It's kept on this PC, and Share item IDs (above) can send it on so the editor learns "
        "it for everyone. When your saves hold item IDs, effects or enchantments the editor's list doesn't have, a "
        "SHARE ITEM IDS button with the count appears in the top bar. Nothing is sent unless you send it.",
    ),
    ("Staying safe", _SAFE_TEXT.replace("{restore}", "Restore a backup… (in MENU)")),
    ("Where the data comes from", _DATA_TEXT),
    ("Where the files are", _FILES_TEXT),
    ("More from the developer", MORE_TEXT),
]

# Advanced mode's Help tab.
HELP_SECTIONS = [
    (
        "Editing a hero",
        "Pick your offline hero on the left. On the Hero tab:\n"
        "• Stats: type a new number or use the arrows. Changes are kept as you go.\n"
        "• Items: sort by power, level, XP, rarity and more (click a column heading or use Sort by). Pick an item "
        "to change its rarity, power or count, equip or unequip it, turn it into another item, make a copy or delete it. "
        "Its effects are listed under its name. Change effects… gives a weapon, armor piece or artifact the effects "
        "you pick (up to the game's four) and a weapon or armor piece an enchantment, from the ones the editor has "
        "seen in real saves and anything on an item in your own. Best for, in that window, puts the editor's picks "
        "for a goal on the item (damage, survival, mobility, loot, artifacts and souls, companions), out of the effects "
        "the game can roll on that very item; which of those is best is the editor's own judgement. "
        "For a talisman the button is Ready to level up: it "
        "puts the talisman one XP short of its next level, and the game does the rest. "
        "The Equipped view lists all 12 gear slots: pick one to put an item in it or take one off. Under the stats, "
        "the editor says which of the three town vendors this hero has unlocked.\n"
        "• + Add items: pick any weapon, armor piece, artifact or talisman in the game and choose rarity, power and "
        "how many, and tick Equip it to put it straight on your hero. Pick Unique rarity to get an item's Unique "
        "version. Confirmed items are known to work; for Unconfirmed ones the editor has to guess the game's name "
        "for the item, and a wrong guess may make the game drop it. Talismans have no rarity or power, and one is "
        "Unconfirmed until the editor has seen its effect in a save: until then it's added without one.\n"
        "• Presets: goals (Most money, Most XP, Best loot and more), the most powerful weapon, armor, artifacts and "
        "talismans, and complete kits from top builds. Pick the item power and rarity, and the editor adds and equips "
        "everything. A kit's gear gets effects, and once your hero has unlocked the Enchantsmith in the game, the "
        "enchantments the editor can write; the rest it lists for you to pick at the Enchantsmith.\n"
        "Then press Save to game. Try a small change first and check it in the game.\n\n"
        "Simple mode keeps numbers within the game's caps (for example 99,999 emeralds; anything above is lost in "
        "the game). Online heroes are stored on the game's servers, so no save editor can change them. Cosmetics "
        "from your game edition are shown but can't be changed or copied.",
    ),
    (
        "Advanced mode",
        "Advanced mode shows the technical side: the Edit tab shows every value in the save as a tree, Raw JSON "
        "shows the whole file, the settings save appears on the left, items show their IDs (and you can type any "
        "item ID), and stats may go past the game's caps. Untick Advanced mode at the top for Simple mode, which "
        "looks like the game's own inventory screen.",
    ),
    (
        "Pictures",
        "Items show their picture when the icons folder has one, and a square in their rarity's colour when it "
        "doesn't. "
        + (
            "Get pictures… (on the Hero tab) downloads the Minecraft Wiki's item pictures. You can also add your "
            if edition.ONLINE
            else "This edition never goes online, so it doesn't download pictures. Add your "
        )
        + "own, named after the item, stat or hero skin (MysticHelmet.png, Emeralds.png, RangerDeluxe.png). "
        "The README in the icons folder explains the names.",
    ),
    ("Staying safe", _SAFE_TEXT.replace("{restore}", "Restore…")),
    ("Where the data comes from", _DATA_TEXT),
    ("Where the files are", _FILES_TEXT),
    ("More from the developer", MORE_TEXT),
]


def _insert_linked(text: tk.Text, body: str) -> None:
    """Add ``body`` to a Help page, with the developer's sites as links that open in the browser."""
    urls = [url for _name, _what, url in MORE_FROM_DEVELOPER]
    for part in re.split("(" + "|".join(re.escape(url) for url in urls) + ")", body):
        if part in urls:
            tag = f"link:{part}"
            text.insert("end", part, ("body", "link", tag))
            text.tag_bind(tag, "<Button-1>", lambda _event, url=part: webbrowser.open(url))
        elif part:
            text.insert("end", part, "body")


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
        names_file: Path = NAMES_FILE,
    ):
        self.root = root
        self.backup_root = Path(backup_root)
        self.icons = IconLibrary(icon_root)
        self.settings_file = Path(settings_file)
        self.settings = _load_settings(self.settings_file)
        self.names_file = Path(names_file)
        use_local_names(load_names(self.names_file))  # names you gave items the editor doesn't know
        self._pictures_busy = False
        self.update: updater.Release | None = None  # a newer version on GitHub, once the check has found one
        self._update_busy = False
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
        width, height = scaled_size(self.root, *START_SIZE)
        if (width, height) == START_SIZE:
            self.root.geometry(f"{width}x{height}")
        else:
            # Grown for a scaled-up display, or cut down to a small screen: put it where all of it shows.
            room = screen_room(self.root)
            self.root.geometry(f"{width}x{height}+{max(0, (self.root.winfo_screenwidth() - width) // 2)}+{max(0, (room[1] - height) // 2)}")
        self.root.minsize(*scaled_size(self.root, *MIN_SIZE))
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        self.light_theme = style.theme_use()  # Advanced mode's look; Simple mode switches to game_style.THEME
        self.light_background = self.root.cget("background")
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
        style.configure("Link.TLabel", foreground="#0b6f80")
        self.game_fonts = GameFonts(self.root)
        self.art = Art(self.root.winfo_fpixels("1i") / 96)
        row_height = int(base.metrics("linespace") * 1.55)
        game_style.install(style, self.game_fonts, row_height, max(30, int(base.metrics("linespace") * 1.9)))

    def _build(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        # Shared by both screens.
        self.title_var = tk.StringVar(value="No save loaded")
        self.meta_var = tk.StringVar()
        self.empty_text_var = tk.StringVar()  # Simple mode, with no hero to show: why, and what to do
        self.changes_var = tk.StringVar()
        self.game_var = tk.StringVar(value="Checking whether the game is running…")
        self.status_var = tk.StringVar()
        self.advanced_var = tk.BooleanVar(value=bool(self.settings.get("advanced", False)))
        self.hero_sort_var = tk.StringVar(value="Most powerful")

        self.advanced_screen = ttk.Frame(root)
        self.advanced_screen.grid(row=0, column=0, sticky="nsew")
        self._build_advanced_screen(self.advanced_screen)
        self.simple_screen = ttk.Frame(root, style="Game.TFrame")
        self.simple_screen.grid(row=0, column=0, sticky="nsew")
        self._build_simple_screen(self.simple_screen)
        root.bind("<Control-s>", lambda _event: self._save_shortcut())

        self._update_buttons()
        self._apply_mode()

    def _build_advanced_screen(self, screen: ttk.Frame) -> None:
        """Advanced mode: the save files' containers on the left, and tabs for the hero, every value and the raw JSON."""
        screen.columnconfigure(0, weight=1)
        screen.rowconfigure(1, weight=1)

        bar = ttk.Frame(screen, padding=(12, 10, 12, 6))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Save profile").pack(side="left")
        self.profile_box = ttk.Combobox(bar, state="readonly", width=44)
        self.profile_box.pack(side="left", padx=(6, 6))
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_selected)
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="left", padx=2)
        ttk.Button(bar, text="Open folder…", command=self._open_folder).pack(side="left", padx=2)
        ttk.Checkbutton(bar, text="Advanced mode", variable=self.advanced_var, command=self._on_advanced_toggled).pack(side="left", padx=(14, 2))
        self.update_button_advanced = ttk.Button(bar, style="Accent.TButton", command=self.update_app)  # shown once there's an update
        self.share_button_advanced = ttk.Button(bar, command=self._share_ids)  # shown when there's something new to share
        ttk.Button(bar, text="Backups folder", command=self._open_backups_folder).pack(side="right", padx=2)
        ttk.Button(bar, text="Restore…", command=self._restore_dialog).pack(side="right", padx=2)
        ttk.Button(bar, text="Back up now", command=self._backup_now).pack(side="right", padx=2)

        panes = ttk.PanedWindow(screen, orient="horizontal")
        panes.grid(row=1, column=0, sticky="nsew", padx=12)

        left = ttk.Frame(panes, padding=(0, 0, 10, 0))
        heading = ttk.Frame(left)
        heading.pack(fill="x", pady=(0, 4))
        ttk.Label(heading, text="Save data", font=self.bold_font).pack(side="left")
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
        ttk.Label(actions, textvariable=self.changes_var, style="Changes.TLabel").pack(side="left")
        self.save_button = ttk.Button(actions, text="Save to game", style="Accent.TButton", command=self.save_to_game)
        self.save_button.pack(side="right")
        self.discard_button = ttk.Button(actions, text="Discard changes", command=self.discard_changes)
        self.discard_button.pack(side="right", padx=8)

        status = ttk.Frame(screen, padding=(12, 6, 12, 8))
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(1, weight=1)
        self.game_label = ttk.Label(status, textvariable=self.game_var, style="Muted.TLabel")
        self.game_label.grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel", anchor="e").grid(row=0, column=1, sticky="ew", padx=(16, 0))

    def _build_simple_screen(self, screen: ttk.Frame) -> None:
        """Simple mode: the hero as the game's inventory screen shows it, between dark bars like the game's."""
        screen.columnconfigure(0, weight=1)
        screen.rowconfigure(1, weight=1)
        bar = ttk.Frame(screen, style="Bar.TFrame", padding=(8, 0, 12, 0))
        bar.grid(row=0, column=0, sticky="ew")

        menu_button = ttk.Menubutton(bar, text="MENU", image=self.art.icon("menu", game_style.SOFT, 1), compound="left", style="Bar.TMenubutton")
        menu_button.pack(side="left")
        self.app_menu = menu = tk.Menu(menu_button, tearoff=False)
        menu.add_command(label="Reload", command=self.reload)
        menu.add_command(label="Open a save folder…", command=self._open_folder)
        self.profile_menu = tk.Menu(menu, tearoff=False)
        self.profile_menu_var = tk.StringVar()
        menu.add_cascade(label="Save profile", menu=self.profile_menu)
        menu.add_separator()
        menu.add_command(label="Back up now", command=self._backup_now)
        menu.add_command(label="Restore a backup…", command=self._restore_dialog)
        menu.add_command(label="Open the backups folder", command=self._open_backups_folder)
        menu.add_separator()
        menu.add_command(label="Get item pictures…", command=self._get_pictures)
        menu.add_command(label="Open the pictures folder", command=self._open_icons_folder)
        menu.add_command(label="Share item IDs…", command=self._share_ids)
        menu.add_command(label="Connect an AI (MCP)…", command=self._connect_ai)
        menu.add_command(label="Check for updates", command=lambda: self.check_for_updates(announce=True))
        menu.add_separator()
        for name, what, url in MORE_FROM_DEVELOPER:
            menu.add_command(label=f"{name}: {what} ↗", command=lambda url=url: webbrowser.open(url))
        menu_button["menu"] = menu

        self.hero_choice_var = tk.StringVar(value="NO HERO")
        self.hero_menu_var = tk.StringVar()
        hero_button = ttk.Menubutton(bar, textvariable=self.hero_choice_var, style="Bar.TMenubutton")
        hero_button.pack(side="left", padx=(2, 12))
        self.hero_menu = tk.Menu(hero_button, tearoff=False)
        hero_button["menu"] = self.hero_menu

        tabs = ttk.Frame(bar, style="Bar.TFrame")
        tabs.pack(side="left")
        self.page_var = tk.StringVar(value="inventory")
        self._tab_lines: dict[str, ttk.Frame] = {}
        for column, (key, text) in enumerate((("inventory", "INVENTORY"), ("help", "HELP"))):
            ttk.Radiobutton(tabs, text=text, value=key, variable=self.page_var, style="BarTab.Toolbutton", command=self._show_page).grid(row=0, column=column)
            line = ttk.Frame(tabs, style="BarLine.TFrame", height=3)
            line.grid(row=1, column=column, sticky="ew", padx=6)
            self._tab_lines[key] = line

        ttk.Checkbutton(bar, text="ADVANCED MODE", variable=self.advanced_var, command=self._on_advanced_toggled, style="Bar.TCheckbutton").pack(
            side="right", padx=(20, 0)
        )
        self.update_button = ttk.Button(bar, style="Accent.TButton", command=self.update_app)  # shown once there's an update
        self.share_button = ttk.Button(bar, style="Bar.TButton", command=self._share_ids)  # shown when there's something new to share

        body = ttk.Frame(screen, style="Game.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.inventory = InventoryScreen(
            body,
            on_change=self._on_hero_changed,
            app_title=APP_TITLE,
            icons=self.icons,
            fonts=self.game_fonts,
            art=self.art,
            get_pictures=self._get_pictures,
            catalog_heroes=self._other_saved_heroes,
            empty_title=self.title_var,
            empty_text=self.empty_text_var,
            names_file=self.names_file,
        )
        self.inventory.grid(row=0, column=0, sticky="nsew")
        self.inventory.make_currency_strip(bar).pack(side="right")
        self.simple_help = self._build_simple_help(body)

        bottom = ttk.Frame(screen, style="Bar.TFrame", padding=(16, 8, 16, 8))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(2, weight=1)
        self.simple_game_label = ttk.Label(bottom, textvariable=self.game_var, style="BarMuted.TLabel")
        self.simple_game_label.grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, textvariable=self.meta_var, style="BarMuted.TLabel").grid(row=0, column=1, sticky="w", padx=(18, 0))
        ttk.Label(bottom, textvariable=self.status_var, style="BarMuted.TLabel", width=1).grid(row=0, column=2, sticky="ew", padx=(18, 12))
        ttk.Label(bottom, textvariable=self.changes_var, style="BarChanges.TLabel").grid(row=0, column=3, sticky="e", padx=(0, 12))
        self.simple_discard_button = ttk.Button(bottom, text="DISCARD CHANGES", style="Bar.TButton", command=self.discard_changes)
        self.simple_discard_button.grid(row=0, column=4, padx=(0, 8))
        self.simple_save_button = ttk.Button(bottom, text="SAVE TO GAME", style="Accent.TButton", command=self.save_to_game)
        self.simple_save_button.grid(row=0, column=5)
        self._show_page()

    def _build_simple_help(self, parent: ttk.Frame) -> ttk.Frame:
        page = ttk.Frame(parent, style="Game.TFrame", padding=(28, 16, 20, 12))
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        share = ttk.Frame(page, style="Game.TFrame")
        share.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(share, text="Help the editor learn more items: send the item IDs in your saves that it doesn't know yet.", style="Body.TLabel").pack(side="left")
        ttk.Button(share, text="SHARE ITEM IDS…", command=self._share_ids).pack(side="left", padx=12)
        ttk.Button(share, text="CONNECT AN AI…", command=self._connect_ai).pack(side="left")
        text = tk.Text(
            page, wrap="word", font=self.game_fonts.body, relief="flat", borderwidth=0, highlightthickness=0, padx=4, pady=4,
            background=game_style.BG, foreground=game_style.SOFT, cursor="arrow",
        )
        text.tag_configure("heading", font=self.game_fonts.heading, foreground=game_style.TEXT, spacing1=14, spacing3=4)
        text.tag_configure("body", lmargin1=2, lmargin2=2, spacing2=3)
        text.tag_configure("link", foreground=game_style.LINK, underline=True)
        text.tag_bind("link", "<Enter>", lambda _event: text.configure(cursor="hand2"))
        text.tag_bind("link", "<Leave>", lambda _event: text.configure(cursor="arrow"))
        for heading, body in SIMPLE_HELP_SECTIONS:
            text.insert("end", heading.upper() + "\n", "heading")
            _insert_linked(text, body.format(backups=self.backup_root) if "{backups}" in body else body)
            text.insert("end", "\n", "body")
        text.configure(state="disabled")
        text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(page, orient="vertical", command=text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        self.simple_help_text = text
        return page

    def _show_page(self) -> None:
        """Simple mode's top-bar tabs: the inventory or the help."""
        page = self.page_var.get()
        for key, line in self._tab_lines.items():
            line.configure(style="Underline.TFrame" if key == page else "BarLine.TFrame")
        if page == "help":
            self.inventory.grid_remove()
            self.simple_help.grid(row=0, column=0, sticky="nsew")
        else:
            self.simple_help.grid_remove()
            self.inventory.grid()

    def _save_shortcut(self) -> None:
        if self.change_count and not self.game_running:
            self.save_to_game()

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
        share = ttk.Frame(self.help_tab)
        share.pack(fill="x", padx=6, pady=(4, 6))
        ttk.Label(share, text="Help the editor learn more items: send the item IDs in your saves that it doesn't know yet.").pack(side="left")
        ttk.Button(share, text="Share item IDs…", command=self._share_ids).pack(side="left", padx=10)
        ttk.Button(share, text="Connect an AI…", command=self._connect_ai).pack(side="left")
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
        text.tag_configure("link", foreground="#0b6f80", underline=True)
        text.tag_bind("link", "<Enter>", lambda _event: text.configure(cursor="hand2"))
        text.tag_bind("link", "<Leave>", lambda _event: text.configure(cursor=""))
        for heading, body in HELP_SECTIONS:
            text.insert("end", heading + "\n", "heading")
            _insert_linked(text, body.format(backups=self.backup_root) if "{backups}" in body else body)
            text.insert("end", "\n", "body")
        text.configure(state="disabled")
        self.help_text = text
        text.pack(fill="both", expand=True)

    def _saved_heroes(self) -> list[Hero]:
        return [c.hero for c in self.profile.containers if c.hero is not None] if self.profile is not None else []

    def _share_ids(self) -> None:
        heroes = self._saved_heroes()
        share_ids.ShareIdsDialog(self.root, heroes, __version__)
        # You've been shown what there is to share now. The note comes back when your saves hold something else.
        shown = set(self._shared_already()) | share_ids.finding_keys(heroes)
        self.settings["shared"] = sorted(shown)
        _save_settings(self.settings_file, self.settings)
        self._update_share_note()

    def _shared_already(self) -> list[str]:
        shared = self.settings.get("shared")
        return [key for key in shared if isinstance(key, str)] if isinstance(shared, list) else []

    def _update_share_note(self) -> None:
        """Show a button when your saves hold item IDs or talisman effects that the editor's list doesn't have
        and that you haven't been shown yet. Nothing is sent anywhere unless you share it yourself."""
        new = len(share_ids.finding_keys(self._saved_heroes()) - set(self._shared_already()))
        if new:
            self.share_button.configure(text=f"SHARE ITEM IDS · {new} NEW")
            self.share_button_advanced.configure(text=f"Share item IDs ({new} new)…")
            self.share_button.pack(side="right", padx=(20, 0))
            self.share_button_advanced.pack(side="left", padx=(14, 2))
        else:
            self.share_button.pack_forget()
            self.share_button_advanced.pack_forget()

    def _connect_ai(self) -> None:
        ConnectAiDialog(self.root)

    def _open_icons_folder(self) -> None:
        paths.open_in_file_manager(self.icons.ensure_folder())

    # ---------------------------------------------------------------- profiles

    def _load_profiles(self, select: Path | None = None) -> None:
        found = saves.find_profiles()
        self._auto_profiles = set(found)
        paths = list(found)
        if select is not None and Path(select) not in paths:
            paths.insert(0, Path(select))
        self._profile_paths = paths
        self.profile_box["values"] = [self._profile_label(path) for path in paths]
        self.profile_menu.delete(0, "end")
        for path in paths:
            self.profile_menu.add_radiobutton(
                label=self._profile_label(path), value=str(path), variable=self.profile_menu_var, command=lambda path=path: self._switch_profile(path)
            )
        if not paths:
            self.profile_menu.add_command(label="No saves found", state="disabled")
        if not paths:
            self.profile = None
            self._fill_container_list()
            self._show_container(None)
            self.title_var.set("No Minecraft Dungeons II saves found")
            self.meta_var.set("Play the game once on this PC, or use Open folder… to pick a save folder.")
            return
        target = Path(select) if select is not None else paths[0]
        self.profile_box.current(paths.index(target))
        self.profile_menu_var.set(str(target))
        self._open_profile(target)

    def _profile_label(self, path: Path) -> str:
        if path in self._auto_profiles:
            if saves.layout_of(path) == "steam":
                return saves.steam.folder_label(path)
            return f"Xbox user {path.name.split('_', 1)[0]}"
        return str(path)

    def _open_profile(self, path: Path, keep: str | None = None, profile: saves.SaveProfile | None = None) -> None:
        stamp = self._read_index_stamp(path)
        try:
            profile = profile or saves.SaveProfile(path)
        except (OSError, wgs.WgsFormatError) as exc:
            messagebox.showerror(APP_TITLE, f"Could not read the saves in\n{path}\n\n{exc}", parent=self.root)
            self._show_profile_choice()
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
        self._update_share_note()
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
        """Simple mode shows the game-style screen in the game's colours; Advanced mode, the technical one."""
        advanced = self.advanced_var.get()
        game_style.use(self.root, simple=not advanced, light_theme=self.light_theme)
        self.root.configure(background=self.light_background if advanced else game_style.BG)
        if advanced:
            self.simple_screen.grid_remove()
            self.advanced_screen.grid()
        else:
            self.advanced_screen.grid_remove()
            self.simple_screen.grid()
        if not advanced and self.notebook.select() in (str(self.edit_tab), str(self.raw_tab)):
            hero_shown = self.notebook.tab(self.hero_tab, "state") == "normal"
            self.notebook.select(self.hero_tab if hero_shown else self.help_tab)
        for tab in (self.edit_tab, self.raw_tab):
            self.notebook.tab(tab, state="normal" if advanced else "hidden")
        self.hero_tab.set_advanced(advanced)
        if advanced:
            self.hero_tab.refresh()  # Simple mode may have changed the hero
        self.inventory.set_active(not advanced)
        self._fit_window()

    def _fit_window(self) -> None:
        """Simple mode's screen doesn't shrink well (the gear and the card have fixed sizes), so keep the
        window big enough for it, within the screen. Advanced mode keeps its usual minimum."""
        least_width, least_height = scaled_size(self.root, *MIN_SIZE)
        if self.advanced_var.get():
            self.root.minsize(least_width, least_height)
            return
        self.root.update_idletasks()
        most_width, most_height = screen_room(self.root)
        need_width = min(max(least_width, self.simple_screen.winfo_reqwidth()), most_width)
        need_height = min(max(least_height, self.simple_screen.winfo_reqheight()), most_height)
        self.root.minsize(need_width, need_height)
        width, height = self.root.winfo_width(), self.root.winfo_height()
        if self.root.winfo_ismapped() and (width < need_width or height < need_height):
            self.root.geometry(f"{max(width, need_width)}x{max(height, need_height)}")

    def _fill_container_list(self) -> None:
        self.container_list.delete(*self.container_list.get_children())
        self._containers_by_iid.clear()
        if self.profile is None:
            self._fill_hero_menu([])
            return
        heroes = [c for c in self.profile.containers if c.hero is not None]
        others = [c for c in self.profile.containers if c.hero is None]
        sort_key = HERO_SORTS[self.hero_sort_var.get()]
        heroes.sort(key=lambda c: sort_key(c.hero), reverse=True)

        self._fill_hero_menu(heroes)
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

    def _fill_hero_menu(self, heroes: list[saves.Container]) -> None:
        """Simple mode's hero list, in the top bar."""
        menu = self.hero_menu
        menu.delete(0, "end")
        for container in heroes:
            hero = container.hero
            name = hero.skin or f"Hero {hero.character_id[:8]}"
            if container.kind is saves.Kind.EDITABLE:
                label = f"{name}  ·  level {hero.level}  ·  {format_amount(hero.attribute('Emeralds') or 0)} emeralds"
            else:
                label = f"{name}  ·  online, can't be changed"
            menu.add_radiobutton(label=label, value=container.name, variable=self.hero_menu_var, command=lambda c=container: self._choose_hero(c))
        if not heroes:
            menu.add_command(label="No offline heroes yet", state="disabled")
        sorts = tk.Menu(menu, tearoff=False)
        for sort in HERO_SORTS:
            sorts.add_radiobutton(label=sort, value=sort, variable=self.hero_sort_var, command=self._resort_heroes)
        menu.add_separator()
        menu.add_cascade(label="Sort heroes by", menu=sorts)

    def _choose_hero(self, container: saves.Container) -> None:
        if container is not self.container and self._confirm_discard():
            self._show_container(container)
            self._select_in_list(container)
        self._show_hero_choice()

    def _show_hero_choice(self) -> None:
        """The hero button in Simple mode's top bar: the hero on screen, with their level."""
        container = self.container
        self.hero_menu_var.set(container.name if container is not None else "")
        hero = Hero(self.document) if self.document is not None and is_hero_document(self.document) else container.hero if container else None
        if hero is None:
            self.hero_choice_var.set("NO HERO" if container is None else container.label.upper())
            return
        name = (hero.skin or f"Hero {hero.character_id[:8]}").upper()
        self.hero_choice_var.set(f"{name}  ·  LV {hero.level}")

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
        self._show_hero_choice()
        for iid, candidate in self._containers_by_iid.items():
            if candidate is container:
                self.container_list.selection_set(iid)
                self.container_list.see(iid)
                return

    def _on_profile_selected(self, _event: tk.Event) -> None:
        self._switch_profile(self._profile_paths[self.profile_box.current()])

    def _switch_profile(self, path: Path) -> None:
        if self.profile is not None and path == self.profile.path:
            return
        if not self._confirm_discard():
            self._show_profile_choice()
            return
        self._open_profile(path)
        self._show_profile_choice()

    def _show_profile_choice(self) -> None:
        """Point the profile list (Advanced mode) and the Save profile menu (Simple mode) at the open profile."""
        if self.profile is not None and self.profile.path in self._profile_paths:
            self.profile_box.current(self._profile_paths.index(self.profile.path))
            self.profile_menu_var.set(str(self.profile.path))

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
        chosen = filedialog.askdirectory(
            title="Choose a save folder (Xbox: has containers.index; Steam: has Character….sav files)", parent=self.root
        )
        if not chosen:
            return
        path = Path(chosen)
        if not (path / wgs.INDEX_FILE).is_file() and not saves.steam.is_steam_folder(path):
            messagebox.showerror(
                APP_TITLE, f"{path} has no {wgs.INDEX_FILE} file and no .sav files, so it isn't a Minecraft Dungeons II save folder.", parent=self.root
            )
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
        self.empty_text_var.set("")
        if container is None:
            if self.profile is not None and not self.advanced_var.get():
                self.title_var.set("No offline heroes yet")
                self.meta_var.set("Create an offline hero in the game, play until it saves, close the game, then press Reload.")
                self.empty_text_var.set(
                    "Create an offline hero in the game, play until it saves and close the game. Then pick Reload in MENU."
                )
            else:
                self.title_var.set("No save loaded")
                self.meta_var.set("")
                self.empty_text_var.set("Play Minecraft Dungeons II once on this PC, or pick Open a save folder… in MENU.")
            return
        if container.hero is not None and container.kind is not saves.Kind.EDITABLE:
            self.empty_text_var.set(f"{container.note} Pick an offline hero in the top bar.")
        entry = container.entry
        when = datetime.fromtimestamp(wgs.filetime_to_unix(entry.mtime))
        self.title_var.set(container.label)
        if self.advanced_var.get():
            if self.profile is not None and self.profile.is_steam:
                meta = f"{container.name}.sav · {entry.size:,} bytes · written {when:%Y-%m-%d %H:%M}"
            else:
                sync = wgs.SYNC_STATE_NAMES.get(entry.sync_state, f"sync state {entry.sync_state}")
                meta = f"{container.name} · revision {entry.revision} · {entry.size:,} bytes · written {when:%Y-%m-%d %H:%M} · {sync}"
            if container.decoded is not None and not container.decoded.exact:
                meta += " · formatting will be tidied when saved"
        else:
            meta = f"Last saved {when:%d %B %Y at %H:%M}"
            if not (self.profile is not None and self.profile.is_steam) and entry.sync_state != wgs.SYNCED:
                meta += " · waiting to upload to the Xbox cloud (it will next time you play)"
        self.meta_var.set(meta)

    def _load_hero_tab(self, select: bool = False) -> None:
        """Point the Hero tab (and Simple mode's screen) at the document being edited; hide the tab unless
        that's a hero."""
        hero = Hero(self.document) if self.document is not None and is_hero_document(self.document) else None
        self.hero_tab.load(hero)
        self.inventory.load(hero)
        self._show_hero_choice()
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
        self._show_hero_choice()  # the level may have changed

    def _hero_editor(self) -> HeroTab | InventoryScreen:
        """Whichever shows the hero in this mode."""
        return self.hero_tab if self.advanced_var.get() else self.inventory

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
        for button in (self.save_button, self.simple_save_button):
            button.state(["!disabled"] if dirty and not self.game_running else ["disabled"])
        for button in (self.discard_button, self.simple_discard_button):
            button.state(["!disabled"] if dirty else ["disabled"])

    def _confirm_discard(self) -> bool:
        self._hero_editor().commit_pending()
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
        if not self._hero_editor().commit_pending():
            return  # the hero screen shows what's wrong
        changes = doc.diff(self.original, self.document)
        if not changes:
            return
        lines = self._change_lines(changes)
        if len(lines) > 14:
            lines = lines[:13] + [f"… and {len(lines) - 13} more"]
        question = f"Save these changes to {self.container.label}?\n\n" + "\n".join(lines) + "\n\nYour current saves are backed up first."
        caution = format_caution(Hero(self.document)) if is_hero_document(self.document) else ""
        if caution:
            question += f"\n\n{caution}"
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
            "Saved! Start the game to see your changes. If you're asked which save to keep, the cloud's or this "
            "PC's, keep this PC's.\n\n"
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
        paths.open_in_file_manager(self.backup_root)

    def _restore_dialog(self) -> None:
        if self.profile is None:
            return
        backups = [b for b in saves.list_backups(self.backup_root) if b.profile_copy.name == self.profile.path.name]
        if not backups:
            messagebox.showinfo(APP_TITLE, "There are no backups of this save profile yet.", parent=self.root)
            return
        RestoreDialog(self.root, backups, self._restore_backup)

    def _restore_backup(self, backup: saves.Backup, dialog: tk.Toplevel) -> None:
        """Put ``backup`` back, once you've said yes, and say what was restored and what couldn't be."""
        if not self._confirm_discard():
            return
        if not messagebox.askyesno(
            "Restore", f"Put back the save data from {backup.created:%Y-%m-%d %H:%M:%S}?\n({backup.reason})", parent=dialog
        ):
            return
        try:
            problems = self.profile.restore_problems(backup)
            restored = self.profile.restore(backup, self.backup_root)
        except saves.GameRunningError as exc:
            messagebox.showwarning(APP_TITLE, str(exc), parent=dialog)
            return
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=dialog)
            return
        dialog.destroy()
        not_restored = "\n".join(f"• {problem}" for problem in problems)
        if not restored:
            if problems:
                messagebox.showwarning(
                    APP_TITLE,
                    f"Nothing was put back.\n\n{not_restored}\n\nThe editor can only put a save back over one that's still in your save folder.",
                    parent=self.root,
                )
            else:
                messagebox.showinfo(APP_TITLE, "Nothing to restore: that backup matches your current save data.", parent=self.root)
            return
        self.change_count = 0
        self._open_profile(self.profile.path, keep=self.container.name if self.container else None)
        containers = {name: self.profile.get(name) for name in restored}
        labels = ", ".join(container.label if container else name for name, container in containers.items())
        self.status_var.set(f"Restored {labels}")
        messagebox.showinfo(APP_TITLE, f"Restored: {labels}" + (f"\n\nNot put back:\n{not_restored}" if problems else ""), parent=self.root)

    # ---------------------------------------------------------------- pictures

    def _in_background(self, work: Any, done: Any, progress: queue.Queue | None = None, say: Any = None) -> None:
        """Run ``work()`` on a thread, then call ``done(ok, result)`` on the UI thread. What the work puts in
        ``progress`` is shown in the status line as ``say(*item)`` says it."""
        results: queue.Queue = queue.Queue()
        say = say or (lambda number, total, name: f"Downloading pictures {number}/{total}: {name}")

        def run() -> None:
            try:
                results.put((True, work()))
            except Exception as exc:  # reported to the user by done()
                results.put((False, exc))

        def poll() -> None:
            while progress is not None and not progress.empty():
                self.status_var.set(say(*progress.get_nowait()))
            if results.empty():
                self.root.after(150, poll)
            else:
                done(*results.get_nowait())

        threading.Thread(target=run, name="background", daemon=True).start()
        poll()

    # ----------------------------------------------------------------- updates

    def check_for_updates(self, announce: bool = False) -> None:
        """Ask GitHub, off the UI thread, whether a newer version is out. The Update button appears if one is;
        ``announce`` also says so when there isn't, or when GitHub can't be reached. The edition that never
        goes online asks nobody."""
        if not edition.ONLINE:
            if announce:
                messagebox.showinfo(
                    APP_TITLE, f"{edition.offline_note('look for updates')}\n\nNew versions are on {edition.NAME}. You have {__version__}.", parent=self.root
                )
            return

        def done(ok: bool, release: Any) -> None:
            newer = ok and release is not None and updater.is_newer(release.version)
            if newer:
                self._show_update(release)
            if not announce:
                return
            if not ok:
                messagebox.showinfo(APP_TITLE, f"GitHub couldn't be reached to look for a newer version.\n\n{release}", parent=self.root)
            elif not newer:
                messagebox.showinfo(APP_TITLE, f"You have the latest version ({__version__}).", parent=self.root)

        self._in_background(updater.latest_release, done)

    def _show_update(self, release: updater.Release) -> None:
        self.update = release
        self.update_button.configure(text=f"UPDATE TO {release.version}")
        self.update_button_advanced.configure(text=f"Update to {release.version}")
        self.update_button.pack(side="right", padx=(20, 0))
        self.update_button_advanced.pack(side="left", padx=(14, 2))
        self.status_var.set(f"Version {release.version} is out. Press Update to get it.")
        self._fit_window()

    def update_app(self) -> None:
        """The Update button: replace the packaged editor with the newer version. Run from source there is no
        packaged editor to replace, so it opens the download page."""
        release = self.update
        if release is None or self._update_busy:
            return
        target = updater.app_dir()
        if target is None:
            webbrowser.open(release.page)
            self.status_var.set("Opened the download page. Run from source, the editor can't replace itself.")
            return
        if not self._confirm_discard():
            return
        question = (
            f"Update to version {release.version}?\n\nThe editor downloads it from GitHub ({release.size / 1e6:.0f} MB), checks the "
            "download, replaces its own folder and opens again. Your saves, backups, pictures and settings aren't touched."
        )
        if not messagebox.askyesno(APP_TITLE, question, parent=self.root):
            return
        self._update_busy = True
        self.status_var.set(f"Downloading version {release.version}…")
        progress: queue.Queue = queue.Queue()

        def done(ok: bool, result: Any) -> None:
            self._update_busy = False
            if ok:
                try:
                    updater.start_swap(result, target)
                except OSError as exc:
                    ok, result = False, exc
            if not ok:
                self.status_var.set("The update wasn't installed.")
                if messagebox.askyesno(APP_TITLE, f"The update couldn't be installed.\n\n{result}\n\nOpen the download page instead?", parent=self.root):
                    webbrowser.open(release.page)
                return
            self.root.destroy()  # the new copy swaps the folder once this window has closed, then opens the editor

        self._in_background(
            lambda: updater.stage(release, lambda got, total: progress.put((got, total))),
            done,
            progress,
            lambda got, total: f"Downloading version {release.version}: {got / 1e6:.0f} of {total / 1e6:.0f} MB",
        )

    # ---------------------------------------------------------------- pictures

    def _get_pictures(self) -> None:
        """Download item pictures from minecraft.wiki, after asking."""
        if not edition.ONLINE:
            messagebox.showinfo(APP_TITLE, _NO_PICTURES, parent=self.root)
            return
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
        self.inventory.refresh()
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
                self.simple_game_label.configure(style="BarRunning.TLabel")
            else:
                self.game_var.set("●  Game is closed. Saving is allowed.")
                self.game_label.configure(style="Closed.TLabel")
                self.simple_game_label.configure(style="BarClosed.TLabel")
            self._update_buttons()
        self._polls += 1
        if self._polls % 4 == 0:  # every 2 seconds
            self._check_disk()
        self._poll_job = self.root.after(500, self._poll_game_results)

    @staticmethod
    def _read_index_stamp(path: Path) -> tuple | None:
        return saves.profile_stamp(path)

    def _check_disk(self) -> None:
        """Notice when the game saved the container on screen after it was loaded. With nothing
        unsaved, load the new version; otherwise say so (saving then re-applies the edits)."""
        if self.profile is None or self.container is None or self.game_running is None or self.game_running:
            return  # while the game runs it keeps saving; look again once it's closed
        stamp = self._read_index_stamp(self.profile.path)
        if stamp is None or stamp == self._index_stamp:
            return
        try:
            revision = saves.current_revision(self.profile.path, self.container.name)
        except (OSError, wgs.WgsFormatError):
            return  # caught in the middle of a write; look again next time
        self._index_stamp = stamp
        if revision is None or revision == self.container.entry.revision:
            return  # only the upload state changed
        if self.change_count == 0 and not self._hero_editor().has_pending_input():
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
        app = EditorApp(root, profile, backup_root, icon_root)
        if close_after is None and edition.ONLINE:  # a build check stays offline, and so does the offline edition
            app.check_for_updates()
            threading.Thread(target=updater.clean_up, name="update clean-up", daemon=True).start()
    except Exception:
        if close_after is None:
            messagebox.showerror(APP_TITLE, traceback.format_exc(), parent=root)
        root.destroy()
        return 1
    if close_after is not None:
        root.after(int(close_after * 1000), root.destroy)
    root.mainloop()
    return 1 if failures else 0
