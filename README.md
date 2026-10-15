# Minecraft Dungeons II Save Editor

An unofficial save editor for **Minecraft Dungeons II** on PC: the **Xbox app / PC Game Pass** version and the
**Steam** version, on Windows, on Linux (Steam through Proton) and on a Mac (through CrossOver or Whisky). Change your offline hero's stats and gear, add and
equip items, and apply ready-made presets and complete kits from top builds, without having to know anything about
save files. It looks like the game's own inventory screen, so you already know your way around. Advanced mode shows
the full save for people who want it.

![Simple mode, laid out like the game's inventory](docs/screenshots/inventory.png)

> **Also from the same developer:** [**Lemma**](https://lemma.ishiakiz.com), a free creative studio for Minecraft, and
> [**Batchly**](https://batch-ly.com), free browser games, tools and experiments.

**Questions, ideas and builds** go in [Discussions](https://github.com/IshiakiZ/mcd2-save-editor/discussions); bugs, and the
lists of item IDs the editor makes for you, in [Issues](https://github.com/IshiakiZ/mcd2-save-editor/issues).

## Features

- **Looks like the game:** your gear, your inventory and the item's card, laid out like the game's own inventory
  screen, in two looks: **Original** and **Liquid Glass**.
- **Stats:** emeralds, Echo Shards, level, XP, enchantment points, and the town's Merchant, Enchantsmith and
  Blacksmith levels.
- **Items:** add any of the game's 180 items and all 116 Uniques, with pictures and search. Change rarity, power
  and count, equip, copy or delete.
- **Effects and enchantments:** pick them yourself, or let **Best for** pick for damage, survival, mobility, loot,
  artifacts and souls, or companions. A piece can be made **Soulstorm Enhanced** too.
- **Talismans and enchantment books:** level a talisman up, and add any of the game's 32 books, so the Enchantsmith
  offers their enchantments.
- **Presets and kits:** most money, most XP, best loot, every minecart station, the most powerful gear, or one of
  six complete builds, in one click.
- **World map and play recorder:** see the ground your hero has explored and what it hasn't found yet, discover
  the whole map, open the shortcuts and the key gates, and write down what the game saves while you play.
- **Story progress:** every quest and its steps, in the game's own words. Move a quest on by one step, finish it, a whole group or the
  whole game, start a quest over or add one, and start your hero at any minecart station it has found.
- **Soul Storms:** which area has a storm now, and when each area gets its next one, on your PC's clock.
- **Let an AI do it:** connect Claude or another AI assistant [over MCP](#let-an-ai-customise-your-hero-mcp) and
  ask for what you want.
- **Safe saving:** a backup before every save, one-click restore, and no saving while the game runs.
- **And more:** Simple and Advanced modes, sorting and filters, item pictures, a **Launch game** button, an
  **Update** button when a newer version is out, and **Suggest something…** for your ideas.

Every feature, in detail: **[Features](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Features)** in the wiki.

| Add items | Kits |
|---|---|
| ![Add items](docs/screenshots/add-items.png) | ![A kit preset](docs/screenshots/presets-kit.png) |

| The Liquid Glass look (Menu → Look) | Advanced mode |
|---|---|
| ![Simple mode in the Liquid Glass look](docs/screenshots/inventory-glass.png) | ![Advanced mode](docs/screenshots/advanced-mode.png) |

| The world map (Menu → World → World map…) | The play recorder (Menu → World → Play recorder…) |
|---|---|
| ![The world map: the ground a hero has explored, its doors, and how far it has got](docs/screenshots/world-map.png) | ![The play recorder writing down what the game saved](docs/screenshots/play-recorder.png) |

| Story progress (Menu → World → Story progress…) | Soul Storms (Menu → World → Soul Storms…) |
|---|---|
| ![Story progress: a hero's quests and steps, with the buttons that change them](docs/screenshots/story-progress.png) | ![Soul Storms: the storm on now, and the next one in each area](docs/screenshots/soul-storms.png) |

## Download

**[⬇ Download MCD2SaveEditor.zip](https://github.com/IshiakiZ/mcd2-save-editor/releases/latest)** from the latest
release. There's nothing to install, and it finds your saves automatically.

1. Unzip it (right-click → **Extract All…**) and open the **MCD2SaveEditor** folder.
2. **Close the game.**
3. Open **MCD2SaveEditor.exe**. Leave it in its folder: it needs the `_internal` folder next to it.
4. Your hero opens (pick another at the top left), make your changes, and press **Save to game**.

Good to know:

- **"Windows protected your PC"?** The .exe isn't code-signed. Click **More info → Run anyway**.
- **Try a small change first** (a few emeralds, say) and check it in the game. Every save makes a backup first, and
  **Menu → Restore a backup…** puts one back.
- **Steam:** the editor finds your saves by itself, as it does the Xbox app's. On **Linux** and on a **Mac** it runs
  from its source: see [Linux and Mac](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Linux-and-Mac).
- **Rather not run an .exe?**
  [Run it from source](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Running-from-source) with Python 3.10 or
  newer.

More help: [Getting started](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Getting-started) ·
[Troubleshooting](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Troubleshooting)

### Antivirus warnings, and checking the download

Antivirus tools sometimes flag programs packaged the way this one is (with PyInstaller), and releases are not
code-signed. You don't have to take anyone's word for the download: GitHub Actions builds every release from this
repository's source, and `gh attestation verify MCD2SaveEditor.zip --repo IshiakiZ/mcd2-save-editor` confirms that
your zip is that build. The details are in
[Safety and privacy](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Safety-and-privacy).

### Privacy

The editor never sends your saves, your hero's data or anything about you anywhere. It goes online for these things
only. When it opens, it asks GitHub whether a newer version is out, and it gets the game's item pictures from
batch-ly.com, the developer's own site, if this PC hasn't got them yet (**Menu → Pictures → Don't get item
pictures automatically** turns that off). **Update** downloads the new version. **Get item pictures…** fetches
pictures when you ask: from batch-ly.com, or from minecraft.wiki if they aren't there.
[More](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Safety-and-privacy#privacy).

## Let an AI customise your hero (MCP)

The editor can run as an [MCP](https://modelcontextprotocol.io) server, so AI assistants that support MCP (Claude
Desktop, Claude Code and others) can look at your heroes and change them for you. **Menu → Connect an AI (MCP)…** shows
the exact setup for your PC, with Copy buttons. In short:

- **Claude Desktop:** Settings → Developer → Edit Config, add this, save, and restart Claude Desktop:

  ```json
  {
    "mcpServers": {
      "mcd2-save-editor": { "command": "C:\\path\\to\\MCD2SaveEditor\\MCD2SaveEditor.exe", "args": ["mcp"] }
    }
  }
  ```

- **Claude Code:** `claude mcp add mcd2-save-editor -- "C:\path\to\MCD2SaveEditor\MCD2SaveEditor.exe" mcp`

The assistant gets tools to list your heroes, show a hero's stats, gear and inventory, search every item in the game,
set stats, add, change, equip, copy and delete items, add enchantment books, give an item effects and an
enchantment, set a talisman's level, apply presets, list and change quests, discover the map, and open shortcuts and key gates. Its changes collect in a draft, like unsaved
changes in the editor window: nothing is written until it calls **save_changes**, which needs the game to be closed
and backs up your saves first, exactly like **Save to game**. It plays by Simple mode's rules (offline heroes only, the
game's caps, slots that open with your level, and best-guess item IDs only if it asks for them), and it never sees
your sign-in, account or device data.

## What it can't do

- **Online heroes.** The game keeps them on its servers; the editor changes **offline** heroes only.
- **Only what real saves have shown:** every item, Unique and enchantment book, 30 of the 32 enchantments and 179 of
  the 180 effect tiers. A tier nobody has sent is marked, and the editor asks before adding it.
- **No rewards.** A quest finished or moved on here gives no items, XP or achievement, and an added book doesn't
  count in the game's collections.
- **Doors and chests** stay as the game saved them.
- **Very high power or level** may be undone by the game: stay close to what it gives at your level.
- **Asked which save to keep** after an edit? Keep this PC's: it has your changes.
- **Steam and Mac support are new:** try a small change first.

Everything else, and why: **[Known limits](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Known-limits)** in the wiki.

## How it works

**Steam version:** each save is its own file, `Character<id>.sav` for a hero, in the game's `SaveGames` folder
(`%LOCALAPPDATA%\Dungeons2\Saved\SaveGames` on Windows). The
content is the same plain JSON the Xbox build keeps in a blob, so the same codec reads it. The editor replaces the
file in one step (write a temporary file, then swap it in), and numbers the game writes in an unusual form are
written back exactly as they were, so an unedited save comes out byte for byte identical.

**Xbox app version:** the game stores saves in the Xbox app's standard layout under
`%LOCALAPPDATA%\Packages\Microsoft.MinecraftDungeons2_8wekyb3d8bbwe\SystemAppData\wgs\`: `containers.index`
lists named containers, each container folder has a `container.<N>` file naming its data blob, and the blobs hold
the data.

- **Heroes** (`Character<id>`) are plain, compact JSON. Stats are in `Ability.Attributes`, items in
  `Inventory.Entries`.
- An item's effects are saved in batches, one for each kind, in this order: the one a Unique comes with
  (`SW.Item.Effect.Static`), the ones the game rolled for it (`SW.Item.Effect.Rerollable`) and its enchantment
  (`SW.Item.Effect.Enchantment`); a talisman has its own instead (`SW.Item.Effect.Upgradable`). Each effect holds
  what it is (`SW.Effect.CriticalEdge`), its strength, and the template it was made from, which says the tier
  (`SW.EffectTemplate.CriticalEdge.II`, or `SW.EffectTemplate.Duelist.Unique` for the Pride of the Plains' own).
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
python -m dungeons2_editor pictures                             # download item pictures (from batch-ly.com)
python -m dungeons2_editor items                                # every item the editor can add, with its ID
python -m dungeons2_editor ids                                  # item IDs in your saves the editor doesn't know yet
python -m dungeons2_editor record                               # the play recorder in a console (--atlas: write the map files)
python -m dungeons2_editor mcp                                  # run as an MCP server for an AI assistant (stdin/stdout)
python -m dungeons2_editor update                               # look for a newer version on GitHub and install it
python -m dungeons2_editor gui --look glass                     # open the window in Liquid Glass this once (classic: Original)
```

Add `--profile <folder>` to point at a save folder somewhere else (the Xbox folder with `containers.index`, or the
Steam `SaveGames` folder).

## Research: the fastest way to gear, XP and emeralds

[**mcd2-research**](mcd2-research/README.md) is a separate write-up of what the game's readable files and
community datamines say about loot odds, the route to level 42, secret talisman locations, currency caps, Soul
Storms and the fastest progression. The editor's presets are built from it.

## Development

```
python -m unittest discover -s tests -t .
```

The tests run on every push and pull request, on Windows, on Linux and on a Mac (`.github/workflows/tests.yml`).

| Path | What's in it |
|---|---|
| `dungeons2_editor/wgs.py` | Xbox save containers: reading, and writing new revisions |
| `dungeons2_editor/steam.py` | Steam saves (loose `.sav` files): finding the folders, reading, writing |
| `dungeons2_editor/codec.py` | The two JSON formats, reproduced exactly |
| `dungeons2_editor/saves.py` | Finding saves (both layouts), backups, restore, safe saving |
| `dungeons2_editor/hero.py` | Hero stats and items, the add-item catalog, change summaries |
| `dungeons2_editor/presets.py` | The presets, kits and the facts behind them |
| `dungeons2_editor/data/` | The item, enchantment and effect lists (`tools/build_item_catalog.py` rebuilds them) |
| `dungeons2_editor/gui.py`, `item_picker.py`, `presets_dialog.py`, `restore_dialog.py`, `layout.py` | The window, its dialogs, and sizing them for the display's scaling |
| `dungeons2_editor/inventory_screen.py`, `game_style.py`, `game_art.py` | Simple mode's game-style screen, its colours and theme, and its pixel art |
| `dungeons2_editor/hero_tab.py`, `hero_editing.py` | Advanced mode's Hero tab, and the editing both modes share |
| `dungeons2_editor/icons.py`, `picture_pack.py`, `wiki.py`, `my_items.py` | Pictures (and cutting items out of them), the downloaders for the picture pack and the Minecraft Wiki, and the names you give items |
| `dungeons2_editor/mcp_server.py`, `ai_dialog.py` | The MCP server for AI assistants, and the window that shows how to connect one |
| `dungeons2_editor/updater.py` | Finding a newer version on GitHub, and replacing the packaged editor with it |
| `dungeons2_editor/edition.py` | Which edition this is: the one on GitHub, or the one for Nexus Mods that never goes online (`tools/make_edition.py` switches) |
| `dungeons2_editor/effects_dialog.py` | The window that changes an item's effects and enchantment |
| `dungeons2_editor/recommend.py` | "Best for": the editor's picks of effects for a goal, out of the ones the game can roll on an item |
| `dungeons2_editor/recorder.py`, `recorder_dialog.py`, `world_dialog.py` | The play recorder: what the game saves while you play, world progress and where things are, and its window; the World map window |
| `dungeons2_editor/world.py`, `data/world.json` | What the editor knows of the game's world (quests, doors, stations, regions, chest spots), and what a save shows of it that's new, for Share item IDs (`tools/build_world_list.py` adds recordings and players' lists to it) |
| `dungeons2_editor/game_launch.py`, `whats_new.py` | Starting the game, and the What's new window (the notes are `data/release-notes.md`, their pictures `data/whats-new/`) |
| `tools/` | The item catalog builder, the picture pack maker, and the release build's helpers and checks |

## Credits and disclaimer

A fan project, **not affiliated with or endorsed by Mojang Studios or Microsoft**. Minecraft is a trademark of Mojang
Synergies AB. Use it at your own risk, and keep your backups.

- **Players' saves** taught the editor its item IDs, effects, enchantments and world. Thank you to everyone who sent a
  list or a find: [icicle1133](https://github.com/icicle1133), [MEGASLAVMAN](https://github.com/MEGASLAVMAN),
  [WyattDrako](https://github.com/WyattDrako), [Blake5256](https://github.com/Blake5256),
  [mauricioggizi](https://github.com/mauricioggizi), [darklynkttv](https://github.com/darklynkttv),
  [dtreddy30-source](https://github.com/dtreddy30-source),
  [gabrielgm0803-ctrl](https://github.com/gabrielgm0803-ctrl), [Frikduf](https://github.com/Frikduf),
  [blasterguy24](https://github.com/blasterguy24), [Armagedon13](https://github.com/Armagedon13),
  [berwulf](https://github.com/berwulf), [regnirok](https://github.com/regnirok),
  [gchristol](https://github.com/gchristol), [XcenZ](https://github.com/XcenZ),
  [itamarnyg8-del](https://github.com/itamarnyg8-del), [hayden-xyz](https://github.com/hayden-xyz) and
  [Pandzio21](https://github.com/Pandzio21).
- **Steam support:** icicle1133 ([#1](https://github.com/IshiakiZ/mcd2-save-editor/pull/1)) and
  [douglas-93](https://github.com/douglas-93) ([#5](https://github.com/IshiakiZ/mcd2-save-editor/pull/5)). **The
  game's quest tables and quest text,** used for their facts only: icicle1133
  ([#40](https://github.com/IshiakiZ/mcd2-save-editor/issues/40),
  [#41](https://github.com/IshiakiZ/mcd2-save-editor/issues/41)).
- **[MetaBot.GG](https://metabot.gg/en/minecraft-dungeons-2)**, built from the game files: item names, sets, Uniques,
  enchantments, effects and their numbers, archetypes, the map's names and the presets' builds, from its
  [uniques](https://metabot.gg/en/minecraft-dungeons-2/uniques),
  [artifacts](https://metabot.gg/en/minecraft-dungeons-2/artifacts),
  [talismans](https://metabot.gg/en/minecraft-dungeons-2/talismans),
  [enchantments](https://metabot.gg/en/minecraft-dungeons-2/enchantments),
  [effects](https://metabot.gg/en/minecraft-dungeons-2/effects), [enchanting
  guide](https://metabot.gg/en/minecraft-dungeons-2/guides/enchanting-guide),
  [weapons](https://metabot.gg/en/minecraft-dungeons-2/weapons),
  [armor](https://metabot.gg/en/minecraft-dungeons-2/armor),
  [builds](https://metabot.gg/en/minecraft-dungeons-2/builds), [map](https://metabot.gg/en/minecraft-dungeons-2/map),
  [best builds](https://metabot.gg/en/minecraft-dungeons-2/guides/best-builds) and [tier
  list](https://metabot.gg/en/minecraft-dungeons-2/tier-list) pages.
- **Item pictures** are Mojang's artwork, downloaded to your PC from batch-ly.com (or from the [Minecraft
  Wiki](https://minecraft.wiki) with **Get item pictures…**); none are in this repository or the download.
- **Ideas from** [MCDSaveEdit](https://github.com/CutFlame/MCDSaveEdit) (Simple mode's inventory), Apple's Liquid
  Glass (the look of that name) and [libNOM.io](https://github.com/zencq/libNOM.io) (the Xbox save layout).

Who sent what, in full: **[Credits](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Credits)** in the wiki. Released
under the [MIT License](LICENSE): do what you like with it, as long as the copyright notice stays with it.
