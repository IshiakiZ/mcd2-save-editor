# Minecraft Dungeons II Save Editor

An unofficial save editor for **Minecraft Dungeons II** on Windows (Xbox app / PC Game Pass). Change your offline
hero's stats and gear, add items, apply ready-made presets, and sort everything by power, XP and more, without
having to know anything about save files. Advanced mode shows the full save for people who want it.

![The Hero tab](docs/screenshots/hero-tab.png)

## Features

- **Stats:** emeralds, Echo Shards, level, XP, enchantment points, and the Merchant, Enchantsmith and Blacksmith
  levels. Changes apply as you type, and mistakes show up in red next to the field.
- **Items:** change rarity, power and count, turn an item into another one, make copies or delete them.
- **Add items:** pick from every item the game has saved on your PC, with pictures, search and a category filter.
- **Presets:** Most money, Most XP, Best loot, Most powerful, Fully upgraded town, Secret talisman hunt and Max
  level. Each shows exactly what it will change, why, and where to find items you haven't picked up yet.
- **Sorting:** items by most powerful, highest item level, most item XP, rarest, most enchantments, newest, name,
  kind or location; heroes by power, level, XP or emeralds.
- **Pictures:** item pictures from the Minecraft Wiki, downloaded on request, or your own.
- **Simple and Advanced modes:** Simple keeps numbers within the game's caps and hides the technical parts.
  Advanced adds a tree of every value in the save, the raw JSON, the settings save and raw item IDs.
- **Safe saving:** a backup before every save, one-click restore, no saving while the game runs, a read-back check
  after writing, and an automatic rollback if anything fails.

| Add items | Presets |
|---|---|
| ![Add items](docs/screenshots/add-items.png) | ![Presets](docs/screenshots/presets-most-powerful.png) |

| Before saving | Advanced mode |
|---|---|
| ![Save summary](docs/screenshots/save-summary.png) | ![Advanced mode](docs/screenshots/advanced-mode.png) |

## Download

**[⬇ Download MCD2SaveEditor.exe](https://github.com/IshiakiZ/mcd2-save-editor/releases/latest)** from the latest
release and double-click it. There's nothing to install, and it finds your saves automatically.

1. **Close the game.**
2. Open **MCD2SaveEditor.exe**.
3. Pick your hero on the left, make your changes, and press **Save to game**.

Windows may say **"Windows protected your PC"** because the .exe isn't code-signed. Click **More info → Run
anyway**. The .exe is built by GitHub Actions straight from this repository's source
([the workflow](.github/workflows/release.yml)). The .exe keeps backups, pictures and settings in
`%LOCALAPPDATA%\MCD2 Save Editor`.

**Running from source instead:** install [Python 3.10 or newer](https://www.python.org/downloads/) (its standard
installer includes the Tkinter this uses), download this repository (**Code → Download ZIP**), unzip it and
double-click **Start Save Editor.bat**. Run that way, backups, pictures and settings stay in the unzipped folder.

**Try a small change first** (a few emeralds, say), start the game and check it before making big ones. Every
save first copies your whole save folder into `backups\`, and **Restore…** puts any of those back. Backups contain
your sign-in token, so don't share them.

## What it can't do

- **Online heroes** are stored on the game's servers, so no save editor can change them. When you create a hero,
  the game makes you pick online or offline for good; this editor works with **offline** heroes.
- **Adding items** only works for items whose IDs the game has saved on your PC (your inventory, loot you've found,
  your collections, and your other heroes). The game's full item list is in encrypted files, so the editor never
  guesses IDs. Advanced mode lets you type one if you know it.
- **Enchantments and Unique signature effects** can't be added yet.
- Only the **Xbox app / PC Game Pass** version is supported; the Steam version keeps its saves differently.
- Level, XP, item power caps and some other numbers come from community datamines, not from the game's own tables.
  The **Max level** preset is experimental.

## How it works

The game stores saves in the Xbox app's standard layout under
`%LOCALAPPDATA%\Packages\Microsoft.MinecraftDungeons2_8wekyb3d8bbwe\SystemAppData\wgs\`: `containers.index`
lists named containers, each container folder has a `container.<N>` file naming its data blob, and the blobs hold
the data.

- **Heroes** (`Character<id>`) are plain, compact JSON. Stats are in `Ability.Attributes`, items in
  `Inventory.Entries`.
- **Settings** (`GlobalSaveDataDefault`) are JSON with every byte stored minus one (`{"blobs"` becomes `z!aknar!`).
- The editor writes both formats byte-for-byte the way the game does, so an unedited save comes out identical.
- Saves are written the way the game writes them: the new data gets a new file name, the revision goes up
  (`container.<N+1>`), and the container is marked modified so Gaming Services uploads it to the Xbox cloud. Only
  then is the old revision deleted.
- Sign-in, entitlement and device-ID containers are never read or changed.

## Command line

```
python -m dungeons2_editor list                                 # show containers
python -m dungeons2_editor export GlobalSaveDataDefault out.json
python -m dungeons2_editor import GlobalSaveDataDefault out.json # asks first, backs up first
python -m dungeons2_editor backup
python -m dungeons2_editor restore "backups\2026-09-30_14-35-12"
python -m dungeons2_editor verify                               # checks saves re-encode exactly; writes nothing
python -m dungeons2_editor pictures                             # download item pictures from minecraft.wiki
```

Add `--profile <folder>` to point at a save folder somewhere else.

## Research: the fastest way to gear, XP and emeralds

[**mcd2-research**](mcd2-research/README.md) is a separate write-up of what the game's readable files and
community datamines say about loot odds, the route to level 42, secret talisman locations, currency caps, Soul
Storms and the fastest progression. The editor's presets are built from it.

## Development

```
python -m unittest discover -s tests -t .
```

| Path | What's in it |
|---|---|
| `dungeons2_editor/wgs.py` | Xbox save containers: reading, and writing new revisions |
| `dungeons2_editor/codec.py` | The two JSON formats, reproduced exactly |
| `dungeons2_editor/saves.py` | Finding saves, backups, restore, safe saving |
| `dungeons2_editor/hero.py` | Hero stats and items, the add-item catalog, change summaries |
| `dungeons2_editor/presets.py` | The presets and the facts behind them |
| `dungeons2_editor/gui.py`, `hero_tab.py`, `item_picker.py`, `presets_dialog.py` | The window |
| `dungeons2_editor/icons.py`, `wiki.py` | Pictures and the Minecraft Wiki downloader |

## Credits and disclaimer

This is a fan project. It is **not affiliated with or endorsed by Mojang Studios or Microsoft**. Minecraft is a
trademark of Mojang Synergies AB. Use it at your own risk and keep your backups.

- Item pictures come from the [Minecraft Wiki](https://minecraft.wiki) and are downloaded on your PC when you ask;
  none are included here. The screenshots use a made-up demo save.
- The Xbox save container layout follows [libNOM.io](https://github.com/zencq/libNOM.io), which writes No Man's Sky
  saves the same way.
- Game facts come from community datamines by [MetaBot](https://metabot.gg/en/minecraft-dungeons-2) and
  [Maxroll](https://maxroll.gg/minecraft-dungeons-2); see [mcd2-research](mcd2-research/README.md).

Released under the [MIT License](LICENSE).
