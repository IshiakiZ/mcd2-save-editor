## What's new in 1.15.0

- **A second look: Liquid Glass.** **Menu → Look → Liquid Glass** gives Simple mode rounded glass panels and
  buttons, pill-shaped tabs, a switch for Advanced mode, slim scroll bars, and top and bottom bars that float clear
  of the window's edges. The colours, the lettering and the item tiles' pictures are still the game's, and
  everything is where it was.
- **Original stays the look the editor opens in.** The menu switches between the two on the spot, and the editor
  remembers your choice with its other settings, which an update doesn't touch.
- The windows Simple mode opens (Add items, Presets, Change effects and the rest) follow the look you picked.
  Advanced mode keeps the Windows look.
- Every shape in Liquid Glass is drawn by the editor itself, the first time you pick the look. No picture files
  were added, the download is no bigger, and the editor opens as quickly as before in the Original look.
- New pictures in the README.
- **The world map.** **Menu → World map…** draws the ground your hero has explored, straight from its save and
  the same way round as the game's own map: the clearer the fog over a square, the greener, with every door you've
  found on it. Scroll to zoom, drag to move, tick **Names** to label the dots. Beside it is how far the hero has
  got: the story quests, every quest and its steps, minecart stations by the game's names, what you may have
  missed, and the game's own counts, such as chests opened. It's a view: nothing is changed.
- **The play recorder.** **Menu → Play recorder…** writes down what the game saves while you play: items picked
  up and changed, stats, every quest step, minecart stations, doors, cutscenes, chests you open and the ground you
  explored, each with where it happened. What it records puts more on the world map: where a station, a cutscene
  or a chest turned up. It can't see a chest or a secret you haven't touched, because the game writes those to a
  save only once you have. It only reads your saves, and what it writes stays on your PC. It's also how the editor
  learned how effects, enchantments and books are saved.
- **Share item IDs… tells of the world too.** The editor now keeps a list of the game's world, learned from saves
  like its item list: quests and their steps, doors and where they are, minecart stations, regions. It starts
  with what the developer's hero has seen, which is early in the story, so a hero further along has the rest.
  Under the items, the share list now adds what your saves show of the world that the editor doesn't know yet,
  and, if you've made play recordings, where they saw chests opened and stations turn up. It's all in the game's
  own names and numbers, with no hero's ID or name; you see every line first, and a tick box leaves the world out.
- **Launch game.** A button next to **Save to game** (and at the top of the menu) starts Minecraft Dungeons II for
  you: the Xbox app's copy or Steam's, whichever your saves belong to. If you have unsaved changes it asks first,
  because the editor can't save while the game is running. On a Mac, where the game runs inside CrossOver or
  Whisky, the button is switched off.
- **Kits enchant every piece.** Once your hero has unlocked the Enchantsmith, a kit (and the best-weapon and
  best-armor presets) puts an enchantment on every weapon and armor piece it adds: the one its build names where
  the editor can write it, and otherwise the editor's own pick for that kind of gear, a different one on each
  piece. Until now the leggings, the boots and any piece whose pick the editor couldn't write were left bare. The
  kit also adds the books of the enchantments its build names, so the Enchantsmith offers those in the game.
- **Five enchantments get their names.** The ones a save calls Blowback, Borealis, Channeling, Lingering Power and
  Soul Fire Aspect are Crash Landing, Ender Mines, Lightning Surge, Power Amplifier and Soul Blast: put on plain
  items with the editor and read off in the game. Four books take their names with them, which leaves five books
  that go by their IDs. Thundering is Thundering, which settles the doubt 1.14.2 left. Kits whose builds name
  Lightning Surge, Power Amplifier or Soul Blast now put those on.
- **What's new, in the editor.** The first time a new version opens, after an update or a fresh download, it
  shows what changed since the version you had. **Menu → What's new…** (and a button on the Help page) shows it
  again. These notes come with the editor, so nothing is fetched to show them.
- **A first step towards the Soulstorm Enhanced tag.** Nobody has shown the editor how the game saves it: no save
  it has seen holds a piece with the tag. So **Share item IDs…** now also lists any item the game saved with a mark
  or a field the editor has never met, as the save holds it. If you have a Soul Storm piece, that list is what
  teaches the editor the tag. Until then, **Change effects…** can already give an item the extra effect such a
  piece carries, though that alone doesn't make the game show the tag.
- An item you add no longer takes on the marks of the item its layout was copied from: it gets the one for an item
  you haven't looked at and no other, as the game hands one over.

## What's new in 1.14.2

- **Every enchantment book has its ID now: 32 of 32.** The last one, which a save calls Multi Potion, was in the
  game's own collections on three lists players had already sent ([issue 17](https://github.com/IshiakiZ/mcd2-save-editor/issues/17), [issue 20](https://github.com/IshiakiZ/mcd2-save-editor/issues/20)
  and [issue 23](https://github.com/IshiakiZ/mcd2-save-editor/issues/23)), and was overlooked when the other unnamed books went in. **Add every book** adds it
  with the rest. Nine books still go by their save IDs, and the game's published list has nine enchantments that no
  ID has been tied to, so the two most likely pair off; which goes with which is still for someone who has the book
  to say.
- **Poison Fog can be put on an item,** at tier III. [Armagedon13](https://github.com/Armagedon13)'s lists
  ([issue 29](https://github.com/IshiakiZ/mcd2-save-editor/issues/29), [issue 30](https://github.com/IshiakiZ/mcd2-save-editor/issues/30)) have it on the Venomous Fangs, from a version of the editor that
  had no tier of it to write, so it's the game's. That makes 21 enchantments.
- **Somersault at tier III,** from [icicle1133](https://github.com/icicle1133)'s list ([issue 31](https://github.com/IshiakiZ/mcd2-save-editor/issues/31)).
- **Book names from that list are held for now.** It puts names to four of the unnamed books, worked out by
  elimination. One of them, Thundering for the book a save calls Channeling, is the name the editor already gives
  another book (the one saved as Thundering), so one of the two is wrong. Both keep the names they have until
  someone who has both books says which is which.
- Not taken from these lists: 23 rolled tiers that equal what the editor already offers on the published table's
  word. A version that offers a tier can write it, so a list made with it can't show the game did; they stay marked
  as not seen.

## What's new in 1.14.1

- **Eight more enchantment books: 31 of the game's 32.** A player's list
  ([blasterguy24](https://github.com/blasterguy24),
  [issue 28](https://github.com/IshiakiZ/mcd2-save-editor/issues/28)) had them in the game's own collections: the
  books a save calls Blowback, Borealis, Burst Bowstring, Channeling, Guarding Strike, Lingering Power, Shadow
  Strike and Soul Aspect. Nobody has said what the game calls them yet, so they go by those names, and **Add every
  book** adds them with the rest. If you have one, **Name it…** on its card and **Share item IDs…** teach the editor
  its name.
- **Every Unique's ID has now been seen.** The same list has the Packleader Muzzle in its collections, the last of
  the 116 that hadn't been. It's saved the way the pattern said.
- **Two more enchantments, 20 in all:** the ones a save calls Channeling and Soul Fire Aspect, at tier III. Health
  Synergy can now be put on at tier III as well.
- **Recovery III:** the one tier where the game's published table and its wording disagreed and no save had settled
  it. It's 30%, the table's number. Seven more tiers the editor offered on that table's word have now been seen in a
  save, each as written: Pack Leader III, Totem Radius III, Momentum III, Evasion II, Brawler III, Prowler III and
  Prickly III.
- Not taken from that list: two tiers that the version which made it could have written itself, and the own effects
  on eight armor pieces that were copies of another Unique.
- The README's note on code signing now says where that stands: releases aren't code-signed.

## What's new in 1.14.0

- **Enchantment books.** The inventory has a **Books** tab, and **Add every book** on it gives your hero all 23
  books the editor knows in one go. **Add items** lists them too, one at a time (it starts on the kind of item the
  inventory is showing), and Delete on a book's card takes one away. Asked for by
  [gabrielgm0803-ctrl](https://github.com/gabrielgm0803-ctrl) in
  [discussion 27](https://github.com/IshiakiZ/mcd2-save-editor/discussions/27).
- **Saved exactly like the game's.** The developer's own save shows how the game saves a book it hands over: seven
  of them, alike in everything but the ID. A book the editor adds is that very entry, key for key, whatever item it
  borrows the layout from. A book has no rarity or power and a hero has one of each, so the editor adds or deletes
  one and changes nothing on it. Its card says what its enchantment does and what it goes on.
- **Checked in the game.** The developer added 17 books with the editor: the game kept every one through its own
  saves, and the Enchantsmith offered Fire Aspect and Poison Fog on a melee weapon, two enchantments the hero had no
  book for before. So the Enchantsmith goes by the books in your inventory. The game's collections and its
  achievement for collecting every book are the game's to write: the editor leaves them alone, as it does for every
  item, and the game didn't add the editor's books to either, so a book added here counts for neither.
- Nine of the game's 32 books can't be added yet, because nobody has sent the ID the game saves them under:
  Bottomless Brew, Crash Landing, Ender Mines, Lightning Surge, Power Amplifier, Shadowcloak, Shielding Smite, Soul
  Blast and Tumbleshot. If you have one, **Share item IDs…** sends it.
- The AI server has `add_enchantment_books`, and its `find_items` lists books.
- **The inventory's tabs wrap** onto another row when there isn't room for them side by side. On a 1080p display
  scaled up to 200% the last ones used to be cut off.
- The editor's own notes about level 100 now say what 1.13.0's README said: a hero set to 100 has kept it.

## What's new in 1.13.0

- **Level up a talisman.** A talisman's card has **Level up** now: it raises the talisman a level, saved exactly as
  the game saves a level-up. The developer's own save showed how: the level goes up by one, the talisman's effect
  becomes the next level's (the item carries every level's effect with it), and its XP carries on from where it
  was. Done with the editor to three talismans in the save from before, it gave the very entries the game had
  written, key for key. Level 3 follows the same pattern; no save with a level-3 talisman has been seen yet.
- A companion's talisman (the Tasty Bone and the like) levels up another way, which hasn't been seen, so it keeps
  **Ready to level up**: one XP short, and the game does the rest.
- The list of changes before you save names a talisman's new level, and the AI server has `set_talisman_level`.
- **Two more tiers seen in the game:** Ally II and Healer III, on gear the game dropped. Both were already offered
  from the game files' numbers, and both turned out as written.
- **Level 100 holds.** A hero set to level 100 has kept it, and the game drops gear at power 150 for it. The README's
  caution about very high values now speaks of power, not level.

## What's new in 1.12.1

- **Fixed: enchantment points and Echo Shards were under each other's picture.** In the game the purple square is
  enchantment points and the blue sparkle is Echo Shards; the editor's top bar had the two numbers the other way
  round, so the one you changed wasn't the one you meant. The numbers themselves were always saved right. Thanks to
  [gabrielgm0803-ctrl](https://github.com/gabrielgm0803-ctrl) for
  [reporting it](https://github.com/IshiakiZ/mcd2-save-editor/discussions/27).
- **Best for no longer picks the effect a Unique already comes with.** It could put a rolled Duelist on the Pride of
  the Plains, whose own effect is Duelist. The game does roll that, but nobody knows that the two add up, so the
  place now goes to the next pick, as it already did in the kits.
- **Two more gear effects, 60 in all:** Shackler and Point Blank, from
  [Frikduf](https://github.com/Frikduf)'s list ([issue 26](https://github.com/IshiakiZ/mcd2-save-editor/issues/26)).
- **Five more enchantments, 18 in all:** Chain Reaction and Thundering at tier III, Somersault at tier II, Health
  Synergy at tier I, and one the save calls Lingering Power, from the same list. Ender Quiver can now be put on at
  tier II as well.
- The Greatbow kit enchants the Humbler Heartstring with Chain Reaction, the build's first choice for it, now that
  the editor knows how the game saves it.

## What's new in 1.12.0

- **The editor on a Mac.** The game runs there through a Windows layer, and the editor now looks for your saves
  where those keep them: in CrossOver's and Whisky's bottles, and in a plain Wine prefix (`~/.wine`, on Linux too).
  It can tell when the game is running on a Mac, so it won't save over a game in play. Run it from source by
  double-clicking **Start Save Editor.command** (the first time, right-click it and choose Open); it needs Python
  3.10 or newer from python.org. The tests of everything but the window now pass on GitHub's Macs; the window's own
  tests can't run there yet, and nobody has tried the editor on a real Mac, so try a small change first and say
  how it went. This download is still the Windows
  program: on a Mac and on Linux the editor runs from the source.

## What's new in 1.11.1

- **A new icon:** a chest, in the editor's own colours.
- **Two enchantments under the game's names.** What the save calls Unstoppable is **Cow Stampede**:
  [gabrielgm0803-ctrl](https://github.com/gabrielgm0803-ctrl) read the name off the game
  ([issue 23](https://github.com/IshiakiZ/mcd2-save-editor/issues/23)). And what it calls Arcane is **Artifact
  Amplifier**, the one armor enchantment whose tier III number is the 9 a save holds for it. Both are now offered
  for armor only, with what they do, and their books go by those names.
- Questions, ideas and builds now have a home: [Discussions](https://github.com/IshiakiZ/mcd2-save-editor/discussions).

## What's new in 1.11.0

- **Best for: the editor's picks of effects for an item.** In the effects window (Change effects…), choose what you
  want from the item: damage, survival, mobility, loot, artifacts and souls, or companions. The editor puts the best
  effects for it on, ahead of what the item has, and says what it did.
  - **A pick is always an effect the game can roll on that very item.** The game rolls an item's effects from the
    pool of its slot and from one pool for each archetype it carries, so a Sword (Fighter gear) gets Sharpness,
    Duelist, Swiftness and Critical Hit for damage, the Humbler Heartstring gets Impact, Ranger and Sharpshooter,
    and a Tank's chestplate is told that the game rolls no mobility effect on it, and which gear it does roll them
    on. Each item's archetypes and each effect's pools come from MetaBot's tables, and players' lists bear them
    out: 338 of the 342 effects the game rolled on those items are in the pool this predicts, and the other four
    are on items their owner had changed with the editor. All nine effects on the next drops in the developer's
    own game were in their item's pool too.
  - **Which of them is best is the editor's own judgement,** not a measurement: bonuses that always apply come
    first, then critical hits and charged shots, then the ones that need the right enemy or moment. Each pick is
    at the best tier a real save has shown.
  - An effect that boosts one element's attacks (Pyromancer and the like) is only picked when your hero has an
    artifact of that element equipped. No effect on gear gives XP: the window points to The Eye of Experience.
  - Picking an effect by hand, the window now says when the game wouldn't roll it on that item. You can still add
    it, and the game keeps it (The Close Ranger wore a Ranger's Marksman through eleven of the game's own saves);
    whether it does anything there hasn't been tested.
- **Kits follow the same rule.** A kit no longer gives an item an effect the game doesn't roll on it: The Close
  Ranger, which is Fighter and Tank gear, got Marksman (a Ranger's and Trickster's effect) and now gets Critical
  Edge.
- **Checked in the game: a Unique from the editor has its own effect working.** The Prime Enchanter's Gauntlets,
  added with the editor, came with their effect in play. Theirs is one of the odd ones (an enchantment saved
  under another name), so it was the one to try. And a whole kit from the editor (Pride of the Plains, The Close
  Ranger, the Twisted Warden set, three artifacts and a talisman) was worn through eleven of the game's saves
  with every effect, own effect and enchantment kept as the editor wrote it.
- **Flatpak Steam:** the editor already looked in Flatpak Steam's folder for your saves; it now looks under each
  of the names Flatpak gives that folder.
- **Three more Uniques' own effects count as seen:** the Alchemist Top Hat, the Woodsprite Crown and the Dreamruler
  Cover. The editor had worked each out from a Unique described in the same words, and a player's list holds all
  three exactly as it wrote them: 96 of the 115 are now from saves.

## What's new in 1.10.2

- **115 of the 116 Uniques come with their own effect** (85 in 1.10.1).
  [gabrielgm0803-ctrl](https://github.com/gabrielgm0803-ctrl)'s list
  ([issue 23](https://github.com/IshiakiZ/mcd2-save-editor/issues/23)) has twenty-seven that nobody had sent: the
  Shackler, the Elemental Staff, the Golden Glaive, the Soul Reaper, the Sage Belt, the Woodsprite Barkpiece and
  more. [Blake5256](https://github.com/Blake5256)'s ([issue 22](https://github.com/IshiakiZ/mcd2-save-editor/issues/22))
  has the Humbler Heartstring, the Greatbow kit's bow, whose arrows pierce ten enemies. The one left is the
  Packleader Paws.
- **All 24 talismans come with what they do.** The Ocelot's Paw, the Medallion of Momentum and the Wonderful Wheat
  were the last three, and every item in the game now has an ID seen in a real save.
- **58 gear effects, each under the game's name for it,** and **13 enchantments:** Fire Aspect and Springload at
  tier III, and two more the save calls Arcane and Unstoppable.
- **Share item IDs only lists a Unique's own effect when the editor wouldn't have written it.** Since 1.10.0 the
  editor gives a Unique its own effect, so finding that same effect on a Unique in a save proves nothing: it may be
  an item you made Unique with the editor. The list now shows a Unique's own effect only where the editor has none
  for that Unique, or would write a different one.
- **Kits don't double up on what a Unique already does.** The Humbler Heartstring comes with Piercing, so the
  Greatbow kit no longer spends its enchantment on Piercing too. You still can, by hand: the game allows it.
- The editor writes three things the way the game spells them, odd as they are: the Wonderful Wheat's ID with a
  small "sw", Springload's template with a small l, and one effect template with a small t.
- Rebuilt with the editor, all 180 items on the three biggest lists come out the same as the game's own, key for
  key.

## What's new in 1.10.1

- **85 of the 116 Uniques come with their own effect** (73 in 1.10.0). [Blake5256](https://github.com/Blake5256)'s
  list ([issue 21](https://github.com/IshiakiZ/mcd2-save-editor/issues/21)) has thirty-one Uniques the game made.
  Nine are new to the editor, the Ranger's Promise, the Venomous Fangs and the Lullaby Blade among them, and every
  Unique on both players' lists is saved the same way on each. It also held five Uniques whose effect 1.10.0 had
  taken from a Unique that does the same thing: each is saved exactly as the editor wrote it.
- **53 gear effects, up from 37:** Sharpness, Impact, Venomancer, Cryomancer, Evasion, Recovery, Aim, Stealth,
  Swiftness, Momentum, Ranger, Fletcher, Sniper and others, most under the game's name for them. Critical Edge III
  is in too: the game's files give two numbers for it, and a save settled it at 30%.
- **Nine enchantments, up from six:** Ender Quiver, Gravity Pulse and one the save calls Borealis at tier III, and
  Healing Smite and Piercing at tier III as well as I. Kits put on the highest tier a save has shown, so the
  Greatbow kit's Ender Quiver goes on now.
- **Prickle's Mark is added the way the game saves it,** which makes 21 of the 24 talismans; the other three haven't
  turned up in anyone's save yet.
- **105 of the 116 Uniques have their own ID confirmed** (four more).
- Rebuilt with the editor, all 120 items on the two lists come out the same as the game's own, key for key.

## What's new in 1.10.0

- **Uniques come with their own effect.** In the game a Unique has an effect of its own, the one its card describes.
  [darklynkttv](https://github.com/darklynkttv) sent a list from a first playthrough with sixty Uniques the game
  made ([issue 20](https://github.com/IshiakiZ/mcd2-save-editor/issues/20)), and it shows how the game saves that
  effect: on the item, apart from the effects it rolls and ahead of them. The editor now writes it exactly that way
  for 73 of the 116 Uniques: the 51 on the list, and 22 that the game's files describe in the very same words as one
  of those. Rebuilt with the editor, all sixty Uniques on the list came out the same as the game's own, key for
  key. The Prime Enchanter's Gauntlets get their waves of lightning and ice
  ([issue 19](https://github.com/IshiakiZ/mcd2-save-editor/issues/19)).
- **A Unique you made before can be given its effect.** Pick it and press **Add its own effect** on its card. Kits
  and Add items give it from the start.
- **43 Uniques are still added without theirs.** A Unique's own effect follows no rule the editor could work the
  others out from (a few are enchantments under another name, with numbers of their own), so it only writes the
  ones it has seen. Add items says which those are before you add one, kits name them in their preview, and the
  card says so. **Share item IDs** lists the own effect of any Unique of yours that the editor hasn't seen it on.
- **37 gear effects, up from 18,** and more tiers of the ones it had: Bounty Hunter, Brawler, Bully, Finesse,
  Persistence, Protection, Pyromancer, Raider, Reaper, Regeneration, Soulmancer, Strength, Prickly and others, most
  under the name the game gives them. Kits put on the highest tier a save has shown.
- **Six enchantments, up from three:** Swirling, Barrier Brew and one the save calls Blowback, each at tier III, and
  Ancient Alchemy at all three tiers.
- **20 of the 24 talismans come with their effect.** The Lucky Clover has its real ID and effect, and the Golem Kit
  and the Wobblestone, two companion talismans, are added the way the game saves them.
- **101 of the 116 Uniques have their own ID confirmed** (six more), and 177 of the 180 items.
- For AI assistants (MCP): `add_unique_effect` gives a Unique that's without it the effect of its own, and an
  item's effects say which one is the Unique's own.
- Thanks to [dtreddy30-source](https://github.com/dtreddy30-source) for checking in the game that Uniques from the
  editor were missing their effect, which is what this fixes.

## What's new in 1.9.1

- **The editor says when a Unique comes without its own effect.** In the game a Unique has an effect of its own, the
  one its card describes. The editor can't write it yet, so a Unique it adds, or makes from another item, is that
  Unique in name, look, rarity and power only. [dtreddy30-source](https://github.com/dtreddy30-source) checked in
  the game: Prime Enchanter's Gauntlets from the editor have no waves of lightning and ice
  ([issue 19](https://github.com/IshiakiZ/mcd2-save-editor/issues/19)). Until now the editor showed what a Unique
  does as if the one it made would do it. Now Add items says so before you add one, kits say so in their preview,
  and an item's card says when a Unique is without its own effect, or may be.
- **One real Unique would fix it for all of them.** The editor writes only what it has seen in a real save, and
  every Unique in the saves it has seen was one it made. So **Share item IDs** now lists what each of your Uniques
  holds, whatever that is. If the game itself has given you one (a drop, a reward or a purchase), open
  **Menu > Share item IDs…**, write "from the game" at the end of that Unique's line and send the list. It holds
  item IDs and the effects on your gear, nothing else from your save.
- Nothing changes in what the editor writes to a save.

## What's new in 1.9.0

- **Abilities on your gear.** Pick a weapon, armor piece or artifact and press **Change effects…**. Choose its
  effects from a list, each at the tier you want, up to the game's four (the game itself rolls a Rare item one and a
  Special item two). The editor writes an effect exactly as the game saves it: checked against a real save, all 21
  items it rewrote came out the same as the game's own, key for key. It knows 18 effects so far, among them Critical
  Edge, Critical Hit, Looter, Luck, Knockback, Vanguard, Marksman, Acrobat, Cooldown and Spiritual, most with the
  game's own wording for what each tier does.
- **Enchantments.** The same window enchants a weapon or armor piece, and counts the enchantment points as the
  game's cost table has them. Three enchantments are in so far: Healing Smite, Piercing and Ancient Alchemy, not yet
  at every tier. The strength a save holds for an enchantment isn't the number the game shows, so each tier of each
  one has to be seen in a save once before the editor can write it.
- **Anything on your own gear can be copied.** An effect or an enchantment on any item in your saves can go on any
  other item that takes it, whether the editor's list has it or not. Enchant one item in the game, and the editor
  can put that enchantment on the rest. **Share item IDs** sends what's on your gear, so everyone gets it.
- **Kits come enchanted once you've unlocked the Enchantsmith.** The editor now tells which of the three town
  vendors your hero has unlocked (the Merchant, the Blacksmith and the Enchantsmith), and says so under Stats & town.
  When the Enchantsmith is one of them, a kit puts on the enchantments its build names, where the editor can write
  them, and lists the rest for you to pick in the game. Gear a kit adds also gets the effects the game would roll
  for it.
- **Kits checked again against MetaBot's guides** (updated 2 October): the same five builds and the same gear.
  Enchantments now go where its build planner puts them: on one weapon, the helmet and the chestplate. The melee
  kit's crossbow and the bow kit's hatchet no longer name one, and the bow takes Piercing, the guide's second
  choice, until the editor can write Chain Reaction.
- **Talismans: how far to the next level, and Ready to level up.** A talisman's card shows its progress (18,480 XP
  for level 2, then 73,920 more for level 3). **Ready to level up** puts it one XP short, and the game levels it up
  the next time you earn XP with it on. The levelling itself is left to the game.
- **The Tasty Bone is added the way the game saves it.** A companion's talisman has no effect of its own: each of
  its levels carries a tag instead. That makes 17 of the 24 talismans.
- **The item card scrolls on small and scaled-up displays.** With Windows at 150% on a 1080p screen, the card's
  lower buttons (Change item…, Delete, Paste picture, Name it…) were cut off. The card now scrolls when it has to,
  and what it says about your last change stays in view below it.
- **A Unique's own effect is still missing.** In the game a Unique comes with an effect of its own, the one its
  card describes. No save holding one has reached the editor yet, so it can't write it, and a Unique the editor
  added may be without it. Share item IDs lists what each Unique you've found comes with: if the game has given you
  one, please share.
- The book the editor called Radiance is Healing Smite. Share item IDs lists only the effects and enchantments the
  editor doesn't have yet.
- If the game saved your hero while the editor had it open, changed effects are carried over to the newer save
  along with your other changes.
- Fully upgraded town says what each vendor level unlocks. The Echo Shard prices it gave for the later levels are
  gone: they aren't in MetaBot's data.
- For AI assistants (MCP): `list_effects`, `set_item_effects` and `ready_talisman`, and `get_hero` says which
  vendors are unlocked.
- Thanks to [MetaBot.GG](https://metabot.gg/en/minecraft-dungeons-2) for the effect names and numbers
  ([gear effects](https://metabot.gg/en/minecraft-dungeons-2/effects)), what an enchantment costs
  ([enchanting guide](https://metabot.gg/en/minecraft-dungeons-2/guides/enchanting-guide)) and the XP a talisman
  level takes ([talismans](https://metabot.gg/en/minecraft-dungeons-2/talismans)).

## What's new in 1.8.1

- **Sixteen talismans come with their effect now** (it was one). Players sent in what theirs do with 1.8.0's Share
  item IDs, and thirteen more talismans got their real save ID from it, matched to their names by the numbers: a
  talisman saved with a rolling cooldown of 0.45 at level 3 is the Armadillo Amulet, which cuts it by 45%. The Eye
  of Experience, Looter's Charm, Emerald of Good Fortune, Healing Heart, Soul Chip and the rest are Confirmed, so
  the presets that use them (Most XP, Most money, Best loot) add them with their effect.
- **176 of the 180 items and 95 of the 116 Uniques are confirmed.** Thank you
  [Blake5256](https://github.com/Blake5256), [mauricioggizi](https://github.com/mauricioggizi),
  [icicle1133](https://github.com/icicle1133) and [WyattDrako](https://github.com/WyattDrako). All 60 Uniques
  reported since 1.8.0 are saved under the pattern that version began to trust. The Mob Mallet, Blizzard Bangle,
  Picnic Basket and Tempo Truffle have their real IDs, and the only items still guessed are four talismans.
- **Add items no longer lists enchantment books you can't add.** Every book in the game's collections showed up
  there, most of them under a made-up name. A book is on offer only when your hero has one to copy.
- **Share item IDs also lists the effects on your weapons, armor and artifacts**, exactly as the game saved them.
  The editor can't add an effect it has never seen, and this is how it will learn them: it's the groundwork for
  putting abilities on the weapons you add. If you have enchanted or Rare gear, please share. A list too long for a
  link is copied for you to paste in, since GitHub turns long links away.
- If the game, the Xbox app or Steam asks which save to keep, the cloud's or this PC's, keep this PC's: that's the
  one with your changes. The editor says so after it saves.

## What's new in 1.8.0

- **Effects on the item card.** An item's effects are listed with their strength, as the game saved them, and a
  talisman shows its level and what its effect becomes at the next ones. They are shown only: the editor can't
  change effects or add enchantments yet.
- **Kits work at Unique rarity.** Every Unique found in a save so far has its base item's ID with `_Unique1`
  (weapons) or `_Unique` (armor) on the end. The editor now adds the other Uniques under the ID that pattern gives,
  without asking, and kits include them. If one turns out wrong, the game drops that one item and keeps the rest.
  Making an item you already own Unique still waits until that Unique's own ID has been seen.
- **"Confirmed" means the game said so.** An item ID counted as seen in your saves when it was anywhere in them.
  But the editor writes to the inventory and the discovered-loot list itself, so an item it had added under a
  guessed ID looked confirmed. Now an ID counts only when the game vouches for it: it's in the game's own
  collections, in the Village Merchant's stock, or on an item the game has kept and shown you. **Share item IDs**
  lists only those, and says how each one is known. In earlier reports, an ID that was new to the editor (most
  Uniques, and every item saved under a name of its own) can't have come from the editor; one that only
  "confirmed a guess" can't be told apart from the editor's own.
- **A note when there's something to share.** When your saves hold item IDs or talisman effects the editor's list
  doesn't have, a **Share item IDs** button with the count appears at the top. Nothing is sent unless you send it.
  Every gap in the list closes only when players share what they've found, so please do.
- **A heads-up after game updates.** If the game has changed how heroes are saved since this version was checked,
  the editor says so before you save.
- The Add items and Connect an AI windows keep their buttons on screens too small to show the whole window.
- What's in the Village Merchant's stock can't be turned into another item any more: make a copy and change that.

## What's new in 1.7.2

- **Restore works on scaled-up displays.** With Windows set to show everything at 125% or more, as it is on many
  laptops, the Restore window opened too small for its list of backups, and its Restore and Cancel buttons didn't
  show at all: you could pick a backup but not put it back. The window now fits what's in it, the list scrolls, and
  double-clicking a backup (or pressing Enter) restores it too. Thanks to [Blake5256](https://github.com/Blake5256)
  for reporting it.
- **The main window opens at a size that suits your display.** At 150% and up, buttons could be cut off until you
  made the window bigger, among them Restore… and Back up now in Advanced mode. On a small screen the window no
  longer opens taller than the screen.
- Restore says what it put back by name ("Restored: Offline hero (Ranger)"). When a backup holds a hero that has
  since been deleted in the game, it now says that hero can't be put back, where it used to say there was nothing
  to restore.

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
- **More confirmed items.** A third player's saves (thank you, [WyattDrako](https://github.com/WyattDrako))
  confirmed the Death Cap Mushroom, the Sorcerer Leggings and the Realmreacher Hat, a quiver saved as
  `LightningQuiver` (by its name, the Conductive Quiver), and five more Uniques' own IDs: Venomous Fangs, The Close
  Ranger, the Twisted Warden Blindfold, the Humbler Carapace and the Humbler Tarsi. Four more enchantment books
  get their names too. 154 of the 181 items and 35 of the 116 Uniques are confirmed now.

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
