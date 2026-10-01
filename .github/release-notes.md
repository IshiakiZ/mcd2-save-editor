## What's new in 1.4.0

- **Let an AI customise your hero.** The editor can run as an MCP server, so Claude Desktop, Claude Code or another
  AI assistant that supports MCP can look at your heroes and change them for you: stats, items, gear and presets.
  **Menu → Connect an AI (MCP)…** shows the setup for your PC. The assistant's changes collect in a draft and are
  written only when it saves, with the game closed and your saves backed up first, the same as Save to game. It
  follows Simple mode's rules: offline heroes only, the game's caps, gear slots that open with your level, and
  best-guess item IDs only if it asks.
- **Pictures for items the wiki doesn't have:** snip an item's tile in the game (Windows+Shift+S), pick the item and
  press **Paste picture** on its card. The editor cuts the item out and keeps the picture on your PC.
- **Name items the editor doesn't know:** **Name it…** on the card. The name stays on your PC, and Share item IDs
  includes it so the editor can learn it for everyone.
- A link to Batchly, free browser games, tools and experiments from the same developer, next to Lemma.

## What's new in 1.3.0

- **Simple mode now looks like the game's inventory screen.** Your gear is on the left as tiles in their rarity's
  colour (weapons, armor, artifacts and talismans; slots your level hasn't opened yet show a lock). The rest of your
  inventory is in the middle, with filters for each kind of item and the Village Merchant's stock. The item card on
  the right shows power, rarity, what the item does and whether it's enchanted, with buttons to change it. Level, XP
  and gear power run along the top, and enchantment points, emeralds and echo shards sit in the top bar; click any
  of them to change it. **Stats & town** has every other stat. The Add items and Presets windows are dark to match.
- **Gear power** is worked out the way the game does (the average power of what your hero wears; talismans don't
  count) and changes as you edit.
- **Item pictures:** the editor cuts the item out of the Minecraft Wiki's pictures so it sits on the tiles the way it
  does in the game; items without a picture get a pixel-art icon. The .exe now includes Pillow for this.
- **Quicker editing:** double-click an empty slot to fill it, double-click an inventory item to put it on,
  right-click a tile for its actions, and press Ctrl+S to save.
- **Advanced mode** stays as it was, with the sortable item list, the Edit tree and the raw JSON. Rarity colours now
  match the game everywhere: Common grey-brown, Rare green, Special blue, Unique orange.
- A link to Lemma, a free creative studio for Minecraft from the same developer, in the menu and on the Help page.

## What's new in 1.2.5

- **More confirmed items**: the Heavy Crossbow (added with the editor and kept by the game), the Mystic Boots, and
  two items the game calls something the editor doesn't know yet. 12 items are now confirmed.
- **Share item IDs…** on the Help tab (or `python -m dungeons2_editor ids`) lists the item IDs in your saves that the
  editor doesn't know yet. Add the in-game names and open a pre-filled GitHub issue with one click. Only item IDs
  are shared, nothing else from your saves.
- **Corrected what 1.2.4 said about the game:** a Unique Sword, a Heavy Crossbow at power 10 and level 10 all
  stuck in the game. Level 100 and twelve items at power 135 didn't, so the warnings now point at very high power
  and level instead of saying the game rejects Uniques or works out your level from XP. Upgrade my gear is no
  longer marked experimental.

## What's new in 1.2.4

- **Equipped view**: a second tab next to your items lists all 12 gear slots and what's in each. Pick a slot to
  **put an item in it** or **unequip** it. The idea comes from the equipment screen of
  [MCDSaveEdit](https://github.com/CutFlame/MCDSaveEdit), the save editor for the first Minecraft Dungeons.
- **What a first real test showed** (with 1.2.3's fix):
  - **Stat changes stick**: 9,999 emeralds showed up in the game.
  - **Items with guessed IDs are removed by the game** when it loads the hero, and the rest of the hero is kept.
    Presets leave unconfirmed items out by default again and say so.
  - **The game works out your level from your XP**, so the Max level preset is gone, and changing Level now says
    the game will put it back.
  - **Uniques made by the editor haven't been tested in the game yet**, so Upgrade my gear is marked experimental.

## What's new in 1.2.3: important fix, please update

- **Saves are now written exactly the way the game writes them.** Earlier versions gave each new save file a new
  local name but kept its old cloud ID. The game always uses one new ID for both. Because of that, the Xbox app's
  cloud sync could bring back the old data: edits didn't show up in the game, and in one case the hero went back
  to a much older copy, losing progress.
- If an edited hero lost progress, the editor's backups hold your saves from just before each edit. Use an
  unedited backup, made before your first edit, and check one small change in the game before making more. The
  game's own cloud save, on by default, can also bring back an older copy of a hero.

## What's new in 1.2.2

- **No more "changed on disk" dead end.** If the game saves your hero while the editor is open (for example, you
  played to check a change), the editor now loads the new version by itself. If you have unsaved changes, pressing
  **Save to game** re-applies them to the newer save, matching items by their unique seed, and shows you the list
  of changes before saving. Your progress from playing and your edits are both kept.

## What's new in 1.2.1

- **Equipping is exact for every slot.** The game's own script cache (a readable file in the game's folder) names
  all 12 gear slots, and they match the editor's, so equipping armor, artifacts and talismans no longer asks first.

Item names are still the game's encrypted data, so items whose internal name hasn't been seen in a save remain
best guesses (marked Unconfirmed). See 1.2.0 below for equipping, the new presets and kits.

## What's new in 1.2.0

- **Equip gear**: an **Equip / Unequip** button on the Hero tab, and **Equip it** when adding items.
- **Most powerful gear presets** and six **kits** from MetaBot's builds, at the power and rarity you pick, equipped in
  one click, with the best enchantment for every piece and where its book drops.
- **Better item list** from MetaBot's game-data database: 181 items and all 116 Uniques with what they do.
- **Fixed**: the Add items window could cut off text and hide its Add button.

## Download

Download **MCD2SaveEditor.exe** below and double-click it. There's nothing to install.

- **"Windows protected your PC"?** The .exe isn't code-signed, so Windows may warn about it. Click **More info → Run
  anyway**. It's built by GitHub Actions straight from this repository's source ([the workflow](https://github.com/IshiakiZ/mcd2-save-editor/blob/main/.github/workflows/release.yml)),
  or you can run the source instead (see below).
- **Close Minecraft Dungeons II before saving.** Every save makes a backup first, and **Restore…** puts one back.
- Backups, item pictures and settings are kept in `%LOCALAPPDATA%\MCD2 Save Editor`.
- Works with the Xbox app / PC Game Pass version of the game, and edits **offline** heroes (online heroes live on the
  game's servers).

Prefer Python? Download the source code below and double-click **Start Save Editor.bat** (needs Python 3.10+).

See the [README](https://github.com/IshiakiZ/mcd2-save-editor/blob/main/README.md) for what it can and can't do.
