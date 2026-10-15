## What's new in 1.18.0

- **Soul Storms.** A new window, **Menu → World → Soul Storms…**, shows the storm that's on now and when each area gets its next one, on your PC's clock.

  ![Soul Storms: the storm on now, and the next one in each area](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.18.0/dungeons2_editor/data/whats-new/1.18.0-soul-storms.png)
- **From the game's own timetable,** which [icicle1133](https://github.com/icicle1133) sent: a storm every 40 minutes that lasts 20, in seven areas in turn. It needs no save, and nothing is fetched.
- **The Sift's areas go by their names:** Singer's Meadow, Humbler Huskland and Lullaby Hills, in Story progress, the World map and the play recorder.
- **An AI assistant can ask too,** with a new tool: `soul_storms`.
- **Two more enchantments, and one more effect tier,** from players' saves: Frost Crescent III, Tumbleshot III and Elemental Protection I. Prickly I is the only tier left unseen.

## What's new in 1.17.0

- **Next step.** A new button in **Menu → World → Story progress…** moves a quest on by one step, the way the game does: it begins a quest that's available, and finishes the step an active one is on.

  ![Story progress: the Next step button, and the steps of the quest picked](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.17.0/dungeons2_editor/data/whats-new/1.17.0-next-step.png)
- **It follows the game's own order.** Steps come one after the other, several at once, or as a choice. Replayed against 126 changes the game made in recordings, the editor reaches the same save each time.
- **Checked in the game.** A quest moved on three steps with **Next step** loaded just as it was saved, on its fourth step.
- **Where it stops.** One quest has a choice between steps, which no save has shown under way. There the editor says so and leaves the quest as it is.
- **An AI assistant can do it too:** `change_quest` has a new action, `next_step`.
- **Every quest by the game's name, and each step in the game's words** (Defeat the monsters, Open the gate), from the game's own quest text that [icicle1133](https://github.com/icicle1133) sent.

## What's new in 1.16.2

- **Which quests come back, put right.** 1.16.1 said the game's four golem quests. It is one of them, The Trembling Golem, and the eight boss fights that can be fought again. Story progress says so on each.

  ![Story progress on The Trembling Golem: the window says the game lets a hero do this quest again](https://raw.githubusercontent.com/IshiakiZ/mcd2-save-editor/v1.16.2/dungeons2_editor/data/whats-new/1.16.2-comes-back.png)
- **Every step to defeat enemies has its number.** The last fourteen are in. A quest that was finished without them reads **finish again**.
- **Finish it lists what follows every quest,** not only the six that a play recording had shown.
- **Where this comes from.** The game's own quest tables, which [icicle1133](https://github.com/icicle1133) read out of the game and sent. They agree with everything the editor had learned from saves.

## Earlier versions, and the details

Every version's changes, in full, are in the [changelog](https://github.com/IshiakiZ/mcd2-save-editor/blob/main/CHANGELOG.md).

## Download

Download **MCD2SaveEditor.zip** below, unzip it (right-click → **Extract All…**), open the **MCD2SaveEditor** folder and double-click **MCD2SaveEditor.exe**. There's nothing to install. Leave the .exe in its folder.

- **"Windows protected your PC"?** The .exe isn't code-signed. Click **More info → Run anyway**.
- **Close Minecraft Dungeons II before saving.** Every save makes a backup first, and **Menu → Restore a backup…** puts one back.
- It edits **offline** heroes, on the Xbox app / PC Game Pass and Steam versions of the game.

[What it can and can't do](https://github.com/IshiakiZ/mcd2-save-editor#readme) · [Getting started](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Getting-started) · [Linux, Mac and running from source](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Running-from-source) · [Safety and privacy](https://github.com/IshiakiZ/mcd2-save-editor/wiki/Safety-and-privacy)
