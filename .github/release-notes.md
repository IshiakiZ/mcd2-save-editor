## What's new in 1.1.0

- **Add any item in the game**: all 170+ weapons, armor pieces, artifacts and talismans, not just ones you've found.
  Items whose internal name has been seen in a real save are marked Confirmed; the rest are best guesses and the
  editor asks before adding them.
- **In-game names**: the save's `MysticHelmet` now shows as the Mystic Circlet, and as the Oracle Crown at Unique rarity.
- **Uniques**: pick Unique rarity to get an item's Unique version (a Unique Battle Hammer is the Emerald Hammer).
- Presets can add unconfirmed items if you tick the box.

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
