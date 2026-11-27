# Known limitations

These are the limits I'm living with for now, whether they come from the remake, a platform or the tools. Each one
says what would have to change.

Checked on Longshot 3.1.1.

## Gameplay

### Eight enemies have no soul
With enemy souls shuffled, 872 enemy placements wait for their soul. These eight always show up:
- The scrub leaf at the Lost Woods target practice. It's part of an NPC, not an enemy by itself.
- Six Water Temple Tektites. The water-rise scene (`WaterTemple_Room06_Waterlevelrise_FocusOnGimmick`) waits on them
  with `EventTektiteWait`, and something other than beating them starts it.
- The Shell Blade that drops in the Water Temple focus scene (`WaterTemple_FocusonGimmick_02`, with
  `EventWarpToHomeMatrix` and `EventShellBladeDemoFall`).

**Why:** a scene that acts on an actor that isn't there can wait forever, and that would hang the game.
**To lift it:** give each of those scenes a guard that skips its steps when the actor is missing (the game's query
for whether an actor is there, if one fits). Then prove the scene ends without it, and gate the eight like the others.

### Cows: 7 of OoTR's 9 (plus a new one)
The remake has no cows in the Lon Lon Ranch tower (OoTR's `LLR Tower Left Cow` and `LLR Tower Right Cow`) and no
Master Quest Jabu-Jabu cow. It does have a new cow in Gerudo Fortress, by the horseback archery stable, and that one
is a check. It's `GF Cow` (adult, with the Gerudo Membership Card and Epona's Song), so Shuffle Cows has 8 cows.
**To lift it:** the two tower cows can't come back, because they aren't in the game.
The details are in `data/rando/songs_trade_cows.json` (`not_in_remake`, `remake_only`).

### The boss-rush chests aren't checks
The boss rush in the dream world (you start it from Link's bed) has ten chests, one in the room before each boss, and
each one gives 200 rupees on every run. They're remake-only content, so they belong in the shuffle, but they aren't
checks yet.
**Why:** the rush lends Link a preset kit for each boss and gives his own pouch back afterwards, so an item you get
inside the rush may be lost. The room logic creates the chests again on every run, and nothing lets a chest give the
seed's item once and rupees after that yet. Two of them (the rooms before Ganondorf and Ganon) only open in the rush
you unlock by beating Ganon.
**To lift it:** first a test build that puts an item in the chest before Gohma, to see if you still own it after the
rush. Then a chest whose contents follow a saved flag, then logic for what unlocks each of the three rushes.

### No wonder items
OoTR's wonder items (invisible items that drop something when Link touches or hits a spot) aren't in the remake, so
**Shuffle Wonderitems** and **Wonderitems Shuffled In** change nothing. The app's tooltips say so.
**To lift it:** only if a later game update adds objects like that.

### Damage multipliers leave pits and lava respawns alone
OoTR's damage multiplier (and our x8 / x16) scales everything that hurts Link here: hits, shots, bosses, falls,
fire, ice, lava floors, shocks, poison bog, heat, drowning and grabs. Falling into a pit or into lava, where Link
loses a heart and wakes up at the last safe spot, isn't scaled. In OoTR that hurt is multiplied too, so with OHKO a
pit kills you there and doesn't here.

**Why:** that respawn is the game's own code (`EventPlayerAbyss` in the player's AI), and no file has a damage
number for it that I've found.
**To lift it:** a code patch on the respawn's health change.

## Platforms

### Only Longshot has been played
The app also builds seeds for Rekarina, Switch emulators (a LayeredFS mod folder) and a modded Switch console (an
Atmosphere SD card). A seed is plain game data in the standard mod layout, so these should work, but nobody has played
a seed on them yet. A Switch 2 console can't easily be modded yet, so that target waits for the modding scene.
**To lift it:** play one seed on each target as it becomes available.

### Master Quest
The game has no Master Quest yet. It might come later as paid extra content. The game files already have an add-on
folder (`AoC1`, title `0400486024DED001`), and seeds patch it along with the base game. I haven't checked anything
against a released Master Quest.
**To lift it:** when it ships, check its files against what the patch assumes, and its layouts against the logic.

### Built for one game version
The location tables (object IDs, save flags, positions) come from the game version Longshot supports (`v131072`,
build `e0f3ccfa`). A Longshot update that keeps that game version changes nothing: going from Longshot 3.1.0 to 3.1.1
rebuilt the same seed byte for byte. A game update that rebuilds levels would mean reading the tables again
(`tools/catalog.py`, `tools/gamedb`, `data/rando/drop_map.json`). The read-back checks refuse any seed whose spots
don't match. The D-pad gear wheels' code patch (`exefs/rando_of_time_gear_wheel.pchtxt`) is tied to that build too:
it checks every place it changes against your game's code and refuses to build otherwise.
**To lift it:** nothing to do until an update like that. Then rebuild the tables and rerun the checks, and move the
wheels' patch to the new build's addresses (`tools/rando/parity/_extras_wheel.py`).

## Tools

### Test builds need a new file per test
The test menu runs in the new-file opening, so each test starts from a clean save and nothing left over from one test
can fake or spoil the next. There's no way to reopen the menu once you're playing.
**To lift it:** an event the player can start anywhere (I haven't found one in the game's files), plus a way to reset
what a test changed.

### The spoiler's playthrough order
The playthrough section of OoTR's spoiler can come out differently for the same seed. The seed itself is identical,
every item's spot and every patched file.
**To lift it:** make OoTR's playthrough search deterministic.

## My rule: the logic counts what the remake allows

When OoTR and the remake disagree, I follow what the remake actually lets the player do.
- If the remake lets you reach or break a check in more ways than OoTR's logic counts, our logic counts them too.
  Players and speedrunners want those checks earlier, so a rule that's stricter than the game is wrong.
- A way counts once it's proven, either read from the game files with high confidence or seen in game. Anything less
  gets an in-game test first and isn't applied yet.
- Real glitches stay tricks, off by default.
- Remake-only content belongs in the shuffle and the logic (the Gerudo Fortress cow, the remake-only chests, the
  objects only the remake has).

Applied so far: the Bow and Din's Fire break beehives, bombs and Din's Fire take grass tufts, and the Bow or the
Hookshot drop every Gerudo cow skull and sign. Not in the logic yet: lifting grass, bombs and bombchus at the high
Kakariko beehives, and bombs at the wall webs.
