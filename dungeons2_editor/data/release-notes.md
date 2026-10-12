## What's new in 1.16.2

- **Which quests come back, put right.** 1.16.1 said the game's four golem quests. It is one of them, The Trembling Golem, and the eight boss fights that can be fought again. Story progress says so on each.

  ![Story progress on The Trembling Golem: the window says the game lets a hero do this quest again](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.16.2/dungeons2_editor/data/whats-new/1.16.2-comes-back.png)
- **Every step to defeat enemies has its number.** The last fourteen are in. A quest that was finished without them reads **finish again**.
- **Finish it lists what follows every quest,** not only the six that a play recording had shown.
- **Where this comes from.** The game's own quest tables, which [icicle1133](https://github.com/icicle1133) read out of the game and sent. They agree with everything the editor had learned from saves.

## What's new in 1.16.1

- **Finish all.** In **Menu → World → Story progress…**, every group of quests has **Finish all** on its own line, and **Finish the whole game…** finishes every quest the editor knows. Both ask first.

  ![Story progress: Finish all on a group's line, and Finish the whole game at the bottom](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.16.1/dungeons2_editor/data/whats-new/1.16.1-finish-all.png)
- **A finished quest gets its steps' numbers.** 1.16.0 left out some of the numbers a save holds with finished steps. Such a quest now reads **finish again**: finish it once more, or use Finish all.
- **Discover the whole map.** A new button in **Menu → World → World map…** lifts the fog from every region the editor knows, the ones your hero hasn't been to as well.
- **Open the shortcuts and the key gates.** Two more buttons there: one moves the rocks that block a way round, the other opens the gates a key opens, with their locks and keys.

  ![The world map: its three new buttons, and what the hero hasn't found as hollow dots](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.16.1/dungeons2_editor/data/whats-new/1.16.1-map.png)
- **The map shows more.** Doors, stations and chest spots your hero hasn't found are on it as hollow dots, and rocks, keys and gates where a play recording has placed them.
- **The play recorder says when a rock, a key, a lock or a gate changes,** and lists them in its summary.
- **Checked in the game.** It took a hero with every quest finished, the whole map discovered and the key gates opened just as saved.
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

## Earlier versions, and the details

Every version's changes, in full, are in the [changelog](https://github.com/IshiakiZ/mcd2-save-editor/blob/main/CHANGELOG.md).

## Download

Download **MCD2SaveEditor.zip** below, unzip it (right-click → **Extract All…**), open the **MCD2SaveEditor** folder and double-click **MCD2SaveEditor.exe**. There's nothing to install. Leave the .exe in its folder.

- **"Windows protected your PC"?** The .exe isn't code-signed. Click **More info → Run anyway**.
- **Close Minecraft Dungeons II before saving.** Every save makes a backup first, and **Menu → Restore a backup…** puts one back.
- It edits **offline** heroes, on the Xbox app / PC Game Pass and Steam versions of the game.

[What it can and can't do](https://github.com/IshiakiZ/mcd2-save-editor#readme) · [Getting started](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Getting-started) · [Linux, Mac and running from source](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Running-from-source) · [Safety and privacy](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Safety-and-privacy)
