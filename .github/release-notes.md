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
