## What's new in 1.7.1

- **Talismans are added the way the game saves them.** A talisman has no rarity or power: a save holds what it does
  at each of its three levels instead. The editor used to add talismans as Common items with a power and no effect,
  so a talisman it added probably did nothing in the game. A Sigil of Beeswax is now written exactly as the game
  writes one (checked against a real save, character for character): +20% max health, rising to +35% as it levels
  up. A talisman one of your heroes has found is added the same way, by copying yours.
- **The other talismans are Unconfirmed for now.** The editor can't know what a talisman's effect is saved as until
  it has seen one in a real save, and so far it has seen one. It still adds the others if you say so, but without
  their effect, and it tells you that first. Kits leave them out unless you tick "Also add unconfirmed items".
- **You can help with that.** **Share item IDs…** now also lists what the talismans in your saves do, so the editor
  can learn them for everyone. If you've found talismans in the game, please send them in.
- A talisman no longer shows a rarity of "None" or a power of -1, and those two can't be changed for one. A
  talisman that an older version added has no effect saved; the editor says so when you pick it, and you can
  delete it and add it again.

## What's new in 1.7.0

- **The editor updates itself.** When a newer version is out, an **Update** button appears at the top. Press it and
  the editor downloads the new version from GitHub, checks the download against the checksum GitHub lists for it,
  replaces its own folder and opens again. Your saves, backups, pictures and settings aren't touched. Run from
  source, the button opens the download page instead. **Menu → Check for updates** looks whenever you like, and
  `MCD2SaveEditor.exe update` does it from a command line.
- To know about new versions, the editor asks GitHub which version is the latest each time its window opens. That
  request says nothing about you or your saves; the README's privacy policy spells out everything the editor
  contacts.
- **More confirmed items.** A second player's saves (thank you, [MEGASLAVMAN](https://github.com/MEGASLAVMAN))
  confirmed 17 more items and 18 more Uniques' own IDs, among them the whole Oracle, Hivemind, Sharpshooter and
  Dauntless sets. 150 of the 181 items and 30 of the 116 Uniques are confirmed now.

## What's new in 1.6.0

- **Far more added items stick.** A save stores each item under an internal name, and for most items the editor used
  to work it out from the name you see. A player sent in 150 names from real saves (thank you,
  [icicle1133](https://github.com/icicle1133)), and about 60 of the editor's guesses were wrong: the Riftslasher is
  really `CurvedLongsword`, the Sculk Digger set is `CaveCrawler` and the Amethyst Lens is `Talisman.RangedBuff`.
  133 of the 181 items are now **Confirmed** (it was 12), so kits, presets and Add items put far more gear on your
  hero that the game keeps.
- **Uniques are added as the real item.** A Unique has a name of its own in a save: The Burning Blade, the Unique
  Sword, is `Sword_Unique1`. Pick Unique rarity in Add items, a preset or a kit and the editor now adds that item.
  Twelve of those names have been seen in real saves. The others follow the same pattern and count as Unconfirmed, so
  the editor asks first. Making an item you already own Unique only turns it into its Unique when that name has been
  seen; otherwise it keeps its name and gets Unique rarity, because a wrong guess would cost you the item.
- **Real names for items you've found:** the Curved Greatsword is the Cookiecutter, the Rallying Horn is the
  Humbling Horn, and enchantment books are called after their enchantment.

## What's new in 1.5.0

- **The Steam version is supported**, on Windows and on Linux (Steam through Proton). The editor finds the Steam
  saves by itself and edits offline heroes the same way, with the same backups, restore and checks. Thanks to
  [icicle1133](https://github.com/icicle1133), who wrote and tested it, and [douglas-93](https://github.com/douglas-93).
  It's new, so try a small change first and report anything odd.
- **The download is now a zip with a folder in it**, not a single .exe. Unzip it and open **MCD2SaveEditor.exe**
  inside. The single .exe unpacked itself every time it started; the folder starts quicker. Your backups, pictures
  and settings stay where they were.
- **Fewer antivirus false alarms, and a way to check your download.** A few antivirus engines flagged the 1.4.0 .exe
  (6 of 71 on VirusTotal, all generic or machine-learning verdicts), because it was packaged the way a lot of malware
  is. The folder no longer unpacks itself, its launcher is compiled during the build, and the .exe says what it is
  and which version. Each release now comes with a build attestation: with the [GitHub CLI](https://cli.github.com),
  `gh attestation verify MCD2SaveEditor.zip --repo IshiakiZ/mcd2-save-editor` confirms the zip was built by this
  repository's workflow from its source.
- **Emeralds go up to 99,999** in Simple mode, the game's limit now (it was 9,999).
- Numbers the game writes in an unusual form are written back exactly as they were, so an unedited save stays
  byte for byte identical.

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

Download **MCD2SaveEditor.zip** below, unzip it (right-click → **Extract All…**), open the **MCD2SaveEditor** folder
and double-click **MCD2SaveEditor.exe**. There's nothing to install. Leave the .exe in its folder: it needs the
`_internal` folder next to it.

- **"Windows protected your PC"?** The .exe isn't code-signed, so Windows may warn about it. Click **More info → Run
  anyway**. It's built by GitHub Actions straight from this repository's source ([the workflow](https://github.com/IshiakiZ/mcd2-save-editor/blob/main/.github/workflows/release.yml)),
  or you can run the source instead (see below).
- **Close Minecraft Dungeons II before saving.** Every save makes a backup first, and **Restore…** puts one back.
- Backups, item pictures and settings are kept in `%LOCALAPPDATA%\MCD2 Save Editor`.
- Works with the Xbox app / PC Game Pass and Steam versions of the game, and edits **offline** heroes (online heroes
  live on the game's servers).

Prefer Python? Download the source code below and double-click **Start Save Editor.bat** (needs Python 3.10+; on
Linux, run **Start Save Editor.sh**).

See the [README](https://github.com/IshiakiZ/mcd2-save-editor/blob/main/README.md) for what it can and can't do.
