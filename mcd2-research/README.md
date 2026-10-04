# Minecraft Dungeons II research

What Minecraft Dungeons II's readable game files say about loot, progression and secrets, cross-checked
against community datamines of the same build (1.1.1.0, internal codename "Spicewood"). The save editor's
presets are built from these findings.

Each finding is tagged with where it comes from:

- **[files]** read directly from the game's install (the plaintext script caches)
- **[community]** published community datamines of build 1.1.1.0 (see [Sources](#sources))
- **[inferred]** a reading of the code's structure

The game keeps its actual number tables (loot odds, XP curve, salvage constants, storm rotation) in an
AES-encrypted asset container that this research did not open. Numbers below come from community datamines;
**[files]** findings are field names and structure only. Patches and server-side table updates can change them.

## The short version

1. **Never farm on Easy.** Easy multiplies the Special and Unique drop weights by zero, so random drops there are never Special or Unique. **[community]**
2. **After the campaign, plan each hour around the Soul Storm.** Storm gear carries one extra modifier, which makes it the only source of 3-modifier Specials and Uniques. The reward chest is the best Unique source in the game, at about 20%. **[community]**
3. **Take the Hard storm generators.** Each generator is Easy, Normal or Hard; the game turns that into a score that picks a Low, Mid or High chest. **[files]**
4. **Level on boss re-kills.** Bosses can be killed again indefinitely. The final campaign boss gives roughly a level per kill, each boss drop has a 1-in-6 Unique chance, and equipped talismans level from the same XP. **[community]**
5. **Chase rarity and effects; Item Power can be bought.** The Blacksmith raises any item to the cap for your level in exchange for emeralds. A good low-level Unique is worth keeping. **[community]**
6. **Don't chain-reroll one item.** The nth reroll on the same item costs n Echo Shards, so costs grow quadratically. Reroll spare copies once each instead (see [Rerolls](#rerolls)). **[community]**
7. **Don't sit at a cap.** Emeralds stop at 99,999 (9,999 in the 1.1.1.0 datamines; the game has raised it since) and Echo Shards at 100; anything earned past the cap is lost. **[community]**
8. **Run Sift rifts on the Thrive tide.** The Wellspring Tides follow the day/night phase. Thrive speeds up soul generation and artifact cooldowns; Endure makes monsters stronger and turns off passive soul regeneration. **[files]**

## Route to level 42

The game's recommended levels for each step **[community]**, with the fixed-location secret talismans on the way.

| # | Area or boss | Level | Pick up here |
|---|---|---:|---|
| 1 | Brave Haven | 1 | Hub. The merchant restocks every 30 minutes. |
| 2 | Honeycomb Fields | 2 | Activate minecart stations as you pass them. |
| 3 | Howling Woods | 6 | **Amethyst Lens**: from the Hidden Grove waypoint, go down to the waterfall and climb the blocks above it to a hidden cave chest. Artifact slots 2 and 3 open at levels 5 and 10. Biggest Unique weapon pool (17). |
| 4 | Soul Corrupted Witch | 13 | Boss, re-killable. |
| 5 | The Deep Dark | 14 | Biggest Unique armor pool (20). At level 15, buy the first vendor upgrade: 300 emeralds, 50 Echo Shards and 4 enchantment books. |
| 6 | Twisted Warden | 16 | Boss, re-killable. |
| 7 | Rainy Plains | 21 | **Thrifty Pendant**: sinking-platform jumping puzzle over the water north of the White Tower, near a dungeon entrance. |
| 8 | Frozen Highlands | 26 | **Lucky Clover**: from the Frozen Fortress waypoint, go into Library Towers, climb the stairs, leave through the gap in the railing and take the hidden jump pad to the chest. |
| 9 | The Sift: Singer's Meadow | 33 | **Soul Chip** can turn up in Sift dungeons: jump pads lead to a raised green platform, and the chest appears when you get close. |
| 10 | Humbler Huskland | 36 | **Medallion of Momentum**: walk into the cliffside near the Echo Den entrance, then platform across the skeletal structures. |
| 11 | Monarch | 40 | Boss, re-killable. |
| 12 | Lullaby Hills | 42 | **Emerald of Good Fortune**: pipe jumping puzzle near the Lullaby Hilltop checkpoint. Finishing the campaign unlocks Soul Storms. |

**Quests with guaranteed Uniques [community]:** The Final Souldown (Emerald Hammer and the full Humbler set),
A Dip in Ichor Springs (the full Oracle set), The Redstone Monstrosity Revived (Redstone Wrecker and the
Monstrosity set). Emerald Hammer and Oracle Sandals each give 5% higher rarity chance, so do these early and
wear them while farming. Quest loot has a separate first-completion table **[files]**, so the first clear counts.

**Talismans without a fixed spot [community]:** Glowstone Flask (overworld dungeons: put out all 4 lit braziers
in a room and a floor tile opens) and Ocelot's Paw (overworld rifts: an interactable wall in a narrow canyon with
high walls). All 8 secret talismans open the Mosstrosity door in Hidden Grove: an ambush, a farmable boss,
4 chests and Wonderful Wheat.

## Loot odds

Rarity weights by source **[community]**. A Unique has one fixed signature effect plus one rerollable effect.
There are 116 Uniques (29 melee, 11 ranged, 76 armor in 19 sets); artifacts and talismans are never Unique.

| Source | Common | Rare | Special | Unique |
|---|---:|---:|---:|---:|
| Regular mob drop | 50% | 25% | 20% | 5% |
| Fancy chest or mini-boss | – | 50% | 40% | 10% |
| Boss | – | 50% | 33% | 16.7% |
| Soul Storm reward chest (+1 modifier) | – | – | 80% | 19.8% |
| Anything on Easy | – | – | 0% | 0% |

Rerollable effects by rarity: Common 0, Rare 1, Special 2, Unique 1 plus its fixed effect; Soul Storm gear adds one.

**How many drops until you get one?** With a per-drop Unique chance `u` for the source and `n` Uniques in the
pool you're after, the chance per drop is `p = u / n`. On average that takes `1 / p` drops, and to be `c` sure
(say 90%) it takes `ceil(ln(1 − c) / ln(1 − p))` drops. Example: any Unique from bosses (`p ≈ 0.167`) takes 6
kills on average and 13 to be 90% sure.

## Rerolls

At the Blacksmith the first reroll on an item costs 1 Echo Shard and each later reroll on the same item costs 1
more **[community]**, so `k` rerolls on one item cost `k(k + 1) / 2` (10 rerolls = 55 shards). If each reroll has
a 1-in-`M` chance of the effect you want, chasing it on one item costs about `M²` shards on average, while
rerolling spare copies once each costs about `M`. This assumes effects are picked uniformly; the real weights are
in the encrypted data.

## Caps and currencies

| Currency | Cap | Notes |
|---|---:|---|
| Emeralds | 99,999 (was 9,999) | Main source: salvage, which pays more for higher power and rarity along a power curve **[files]**. Main sink: Item Power upgrades. With the Thrifty Pendant, the damage bonus is full at 7,000 / 8,000 / 9,000 emeralds (+25 / 40 / 50%). |
| Echo Shards | 100 | Called `SpringStone` inside the game **[files]**. Best source: Soul Storms. Enchanting costs 1 each; the level-15 vendor upgrade 50; Blacksmith levels 2 / 3 cost 20 / 40; Enchantsmith levels 2 / 3 cost 30 / 60. One-time unlocks total about 200 shards. |
| Enchantment Points | – | 1 per level-up (level cap 100). Refunded when you disenchant or salvage, so always spend them. |

**Talismans [community]:** 3 slots. Level 2 takes 18,480 XP and level 3 another 73,920 (92,400 in all). Farming
loadout: **Lucky Clover** (+2 / 4 / 7% extra loot drops), **Looter's Charm** (+1 / 2 / 4% more enemy loot), and either
**Emerald of Good Fortune** (+10 / 20 / 25% emeralds) or **The Eye of Experience** (+4 / 6 / 10% XP). Level the
Clover first, since it boosts everything else you farm.

**Other numbers [community]:** 12 gear slots, 80 items per inventory category, 200 enchantment books held, 100 base
soul capacity, 20-second health potion cooldown, 30 minecart stations in the files.

## The endgame hour

Community timings put a Soul Storm in one area every hour, lasting about 40 minutes **[community]**. The code
stores this as a timetable (an anchor time, a duration and a cadence) plus an ordered list of areas called the
rotation **[files]**, so the next area is probably predictable once you've logged a full cycle **[inferred]**.
Clearing three generators ends the storm and pays the chest; a storm can also time out **[files]**.

- **Safe:** clear three Hard generators right away, then spend the rest of the hour on boss re-kills.
- **Greedy:** farm storm mobs for 3-modifier drops, then start the generators with enough time left to finish.
  Only once you know your clear time: if the storm times out, you lose the chest.

## Secrets built into the level code [files]

- **Breakable walls** that break after a short delay with a sound cue (`SecretBreakableActorStateGimmick`).
- **Secret blockers** that hide a route until something in the area changes (`SecretBlockerActorStateGimmick`).
- **Rotating statues**, each with a set number of positions and a start position (`StatueSwitchActorStateGimmick`).
- **Musical gates** wired to several singing-bean locks (`MusicalGateActorStateGimmick`).
- **Key golems and locks**; an abandoned key returns to its spawn point (`KeyGolemLockActorStateGimmick`).
- A **stronghold sub-dungeon** door (`StrongholdSubdungeonDoor`), a **credits plinth** (`SWCreditsPlinth`) and an
  **observatory telescope** with its own camera (`Telescope.as`).
- **Secret collections** with counters (`SecretItemCollectionData`), which is how the Mosstrosity door knows you
  have all 8 talismans.
- **Two unlisted minecart stations**: the files hold 30, but only 19 overworld and 9 Sift stations are known
  **[community]**.
- **Developer leftovers**: an inventory cheat mode (`ToggleCheatMode`, `GetCheatedItem`), a debug command menu, a
  UI action that sets any attribute, dev hint signs, a kiosk mode and loot simulation tables. They're almost
  certainly disabled in retail; this research didn't try to turn them on.

**Capes [community]:** Hero Cape (log in with the account you used for the first game before 31 December 2026),
Soul Cape (Deluxe Edition), Twisted Cape (pre-order code), Corrupted Creeper Cape (Twitch or TikTok drops,
21–26 September 2026). Codes are checked by the server, so the files contain none **[files]**.

## What the code shows [files]

The script bind cache lists the fields the designers tune. The values are encrypted, but the names show how each
system works.

- **Loot:** each source has slots with guaranteed drops, a number of random rolls, a chance per roll and a
  weighted table. Extra drops, drop-chance boosts and duplicate drops each come from a player stat that talismans
  and rarity gear modify. The game remembers recent drops per slot, likely to cut repeats. Procedural dungeons
  roll chests per tile. (`LootEntry`, `LootSlotData.RecentDropsToTrack`, `ATR_Loot`, `DungeonLootSpawnRules`)
- **XP and threat:** XP per level has a base, a growth factor and a ceiling, so past some level each level costs
  the same. XP from threat, mobs and quests each have their own multiplier. Recommended threat comes from your
  level, and target Item Power from threat. (`LevelUpXPCostBase`, `LevelUpXPCostIncreaseFactor`,
  `LevelUpXPCostLimit`, `XPAquisitionMultiplierThreat`)
- **Economy:** salvage pays a base plus a coefficient times item power raised to an exponent, with extra
  modifiers per tag such as rarity. A global currency multiplier and level milestones pace emeralds, Echo Shards,
  books and vendor upgrades. (`SalvageConstants`, `EconomyProgression`, `DuplicatePickupCompensationData`)
- **Soul Storms:** scheduled from an anchor time, duration and cadence over an ordered list of areas; generators
  are Easy, Normal or Hard; chest tiers are set per storm. (`SoulStormScheduleTimeTableRow`,
  `SoulStormScheduleAreaRotationTableRow`, `EStorminatorDifficulty`)
- **Co-op:** rewards scale per player count, some loot rolls once per party, some chests only open for their
  owner, and the party leader sets (and can lock) the difficulty. (`MultiplayerRewardScalingData`,
  `SingleRollPerParty`, `OnlyOwnerCanLoot`)
- **Quests:** first completions use a different loot source than repeats, quests can be replayable after a delay,
  and there's a built-in fixer for soft-locked quests. (`QuestRewardData.FirstCompletionLootSourceData`,
  `QuestReplaySettings`, `GA_TryFixQuestSoftLock`)

## Method

- **Read:** the three plaintext script caches in `Content\Dungeons\Script`: `PrecompiledScript.Cache` (1,067
  script modules, mostly UI), `Binds.Cache` (every C++ class exposed to scripts, with fields and functions) and
  `Binds.Cache.Headers` (paths of 1,853 C++ headers). [`mcd2_script_dump.py`](mcd2_script_dump.py) turns them into
  readable lists in `data\` from your own install:

  ```
  python mcd2_script_dump.py "C:\XboxGames\Minecraft Dungeons II"
  ```

  The generated lists aren't included here because they're extracted from the game's files.
- **Not read:** the asset container (`Dungeons-WinGDK.utoc/.ucas`: IoStore v8, compressed and AES-encrypted) and
  the `.pak`, whose index is also encrypted. These hold the actual numbers. The research didn't try to decrypt
  them or to get around the protection on the game executable.
- **Saves:** online heroes are stored on the game's servers. Offline heroes and settings are stored locally; the
  [save editor](../README.md) edits those.

## Sources

1. [MetaBot: Beginner's Guide](https://metabot.gg/en/minecraft-dungeons-2/guides/beginners-guide)
2. [MetaBot: Unique Items, Where to Farm](https://metabot.gg/en/minecraft-dungeons-2/guides/unique-items-farming)
3. [MetaBot: Progression and Levels](https://metabot.gg/en/minecraft-dungeons-2/progression)
4. [Maxroll: Endgame Farming Guide](https://maxroll.gg/minecraft-dungeons-2/guides/endgame-farming-guide-for-minecraft-dungeons-2)
5. [Maxroll: Secret Talisman Locations](https://maxroll.gg/minecraft-dungeons-2/guides/secret-talisman-locations-in-minecraft-dungeons-2)
6. [Maxroll: Talisman Guide](https://maxroll.gg/minecraft-dungeons-2/guides/talisman-guide-and-the-best-talismans-in-minecraft-dungeons-2)
7. [Maxroll: Blacksmith and Salvaging Guide](https://maxroll.gg/minecraft-dungeons-2/guides/blacksmith-and-salvaging-guide-for-minecraft-dungeons-2)
8. [Maxroll: Enchanting Guide](https://maxroll.gg/minecraft-dungeons-2/guides/enchanting-guide-for-minecraft-dungeons-2)
9. [Wikily: Inventory Space and Salvage Rules](https://wikily.gg/minecraft-dungeons-2/inventory-and-salvage)
10. [DungeonsDB: Talismans](https://www.dungeonsdb.com/talismans)
11. [games.gg: How to Get All 5 Capes](https://games.gg/minecraft-dungeons-ii/guides/minecraft-dungeons-2-how-to-get-all-5-capes/)
12. [Minecraft Wiki: Soul Storms](https://minecraft.wiki/w/Dungeons_II:Soul_Storms)
