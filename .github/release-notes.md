## What's new in 1.2.0

- **Equip gear**: an **Equip / Unequip** button on the Hero tab, and **Equip it** when adding items, so new gear goes
  straight onto your hero. Whatever was in that slot goes back to your inventory.
- **Most powerful gear presets**: the best melee weapon, ranged weapon, armor, artifacts and talismans, added at the
  power and rarity you pick.
- **Kits**: six complete loadouts from [MetaBot](https://metabot.gg/en/minecraft-dungeons-2/guides/best-builds)'s
  data-backed builds (Melee damage, Greatbow sharpshooter, Close-range crossbow, Humbler tank, Soul caster and
  Companion support). Each has a full set of armor, weapons, three artifacts and three talismans, Unique by
  default, at the power you choose, and equipped in one click.
- **Enchantment suggestions**: presets list the best enchantment for every weapon and armor piece, what it does and
  where its book drops. The editor can't add enchantments itself yet, so you put them on at the Enchantsmith.
- **Better item list**: names now come from [MetaBot](https://metabot.gg/en/minecraft-dungeons-2/uniques)'s
  database built from the game files: 181 items, all 116 Uniques with what they do, and the right names where the
  wiki still had placeholders. For example, the Unique War Hammer is the Heartbreaker.
- **Fixed**: the Add items window could cut off text and hide its Add button.

Equipping weapons uses slot names seen in real saves. For armor, artifacts and talismans the slot names are best
guesses until the editor sees one in a save: equip one of each in the game and it learns them.

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
