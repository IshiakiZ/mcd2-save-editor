## What's new in 1.16.1

- **Finish all.** In **Menu → World → Story progress…**, every group of quests has **Finish all** on its own line, and **Finish the whole game…** finishes every quest the editor knows. Both ask first.

  ![Story progress: Finish all on a group's line, and Finish the whole game at the bottom](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.16.1/dungeons2_editor/data/whats-new/1.16.1-finish-all.png)
- **A finished quest gets its steps' numbers.** 1.16.0 left out some of the numbers a save holds with finished steps. Such a quest now reads **finish again**: finish it once more, or use Finish all.
- **Discover the whole map.** A new button in **Menu → World → World map…** lifts the fog from every region the editor knows, the ones your hero hasn't been to as well.
- **Open the shortcuts and the key gates.** Two more buttons there: one moves the rocks that block a way round, the other opens the gates a key opens, with their locks and keys.

  ![The world map: its three new buttons, and what the hero hasn't found as hollow dots](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.16.1/dungeons2_editor/data/whats-new/1.16.1-map.png)
- **The map shows more.** Doors, stations and chest spots your hero hasn't found are on it as hollow dots, and rocks, keys and gates where a play recording has placed them.
- **The play recorder says when a rock, a key, a lock or a gate changes,** and lists them in its summary.
- **Checked in the game.** It took a hero with every quest finished, the whole map discovered and the key gates opened just as saved. Its four golem quests come back on its map: it offers them again.
- **An AI assistant can do these too,** with three new tools: `finish_quests`, `discover_map` and `open_shortcuts_and_gates`.

## What's new in 1.16.0

- **Story progress.** A new window, **Menu → World → Story progress…**, lists every quest with its steps. Finish a quest, start one over, add one your hero hasn't met, or pick the quest the game tracks.

  ![Story progress: a hero's quests and steps, with the buttons that change them](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.16.0/dungeons2_editor/data/whats-new/1.16.0-story.png)
- **It writes a quest the way a save holds one,** and none of what the game gives for it: no items, no XP, no achievement. Checked in the game: it opens the quests that follow by itself.
- **Start at any minecart station you've found.** Pick one under **Where the hero starts** in the same window, and the game starts your hero there. Checked in the game.
- **The editor learns what a quest opens.** **Share item IDs…** now tells which quests your recordings saw the game open after one, and the number saved with a finished step.
- **An AI assistant can do the same,** with three new tools: `list_quests`, `change_quest` and `start_at_station`.
- **Suggest something.** **Menu → Share and suggest → Suggest something…** is a place to leave an idea for the editor, or to say what it gets wrong.
- **A shorter menu.** Pictures, World, Share and suggest, and Updates are submenus now, like Look.
- **Buddy Brew can be put on armor,** at tier III, on [icicle1133](https://github.com/icicle1133)'s word. Four of the 32 enchantments are left.

## What's new in 1.15.4

- **The game's own item pictures.** The editor now gets them by itself when it opens, for every item but one. **Menu → Pictures → Don't get item pictures automatically** turns that off. <!-- online -->

  ![The editor showing the game's item pictures](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.15.4/dungeons2_editor/data/whats-new/1.15.4-pictures.png)
- **What's new can show pictures.** After an update it waits for you to close it, so the news isn't missed.
- **Two more effect tiers count as seen,** on [darklynkttv](https://github.com/darklynkttv)'s and [hayden-xyz](https://github.com/hayden-xyz)'s word: Deflection I and Swiftness I. Two of the 180 are left.
- **Two more doors** in the Frozen Highlands, from hayden-xyz's list.

## Earlier versions, and the details

Every version's changes, in full, are in the [changelog](https://github.com/IshiakiZ/mcd2-save-editor/blob/main/CHANGELOG.md).

## Download

Download **MCD2SaveEditor.zip** below, unzip it (right-click → **Extract All…**), open the **MCD2SaveEditor** folder and double-click **MCD2SaveEditor.exe**. There's nothing to install. Leave the .exe in its folder.

- **"Windows protected your PC"?** The .exe isn't code-signed. Click **More info → Run anyway**.
- **Close Minecraft Dungeons II before saving.** Every save makes a backup first, and **Menu → Restore a backup…** puts one back.
- It edits **offline** heroes, on the Xbox app / PC Game Pass and Steam versions of the game.

[What it can and can't do](https://github.com/IshiakiZ/mcd2-save-editor#readme) · [Getting started](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Getting-started) · [Linux, Mac and running from source](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Running-from-source) · [Safety and privacy](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Safety-and-privacy)
