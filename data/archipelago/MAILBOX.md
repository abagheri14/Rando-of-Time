# Archipelago mailbox: other players' items in our seed, and items received in game

This is the in-game side of the Archipelago contract, marked M in `CONTRACT.md`.

- `tools/rando/parity/archipelago.py` is the plugin. It's only active when the settings hold `remake_archipelago`,
  and without it a seed comes out byte-identical (checked A/B).
- `_archipelago_give.py`: one give per item code, the single-player way.
- `_archipelago_text.py`: the found texts in 16 languages.
- The machine-readable tables are in `data/archipelago/mailbox.json`
  (`python tools/rando/parity/archipelago.py --tables`).

The design is ported from OotrR (github.com/Mozencaz/OotrR, MIT, Copyright (c) 2026 Mozencaz, licence in
`data/archipelago/LICENSE-OotrR`):

- `ap_mailbox.py`: the client writes a GameData Bool in memory, and a watcher in `Sequence/MainUpdate.module.ainb`
  requests an item-get event.
- `archipelago/receive.py`: one signal at a time, with retries.

Our patch uses one watcher and one event for all items. The client writes the item code as a set of Bools. Any item
can arrive at any time, starting items, `/send` and item links included. The watcher reads one Bool per frame.

**`mailbox_version`: 1.**

**Status: built and read back statically, but nothing has been seen in game yet.** The probe (section 5) has to pass
first.

## 1. Placeholder items (A: build_patch, the apworld)

### Names

Our generator places one of these OoTR item names at a location holding another player's item. In an Archipelago
seed, the plugin's `before_build` registers them in OoTR's tables (`register_items()`). Each one has hint words in
every language.

| AP classification | Item name | Our own world sees | Hint words |
|---|---|---|---|
| progression | `Archipelago Item (Progression)` | priority (never advancement) | something important for another world |
| useful | `Archipelago Item (Useful)` | junk | something useful for another world |
| filler | `Archipelago Item (Filler)` | junk | something for another world |
| trap | `Archipelago Item (Trap)` | junk | a trap for another world |

- Precedence follows `CONTRACT.md`: progression > trap > useful > filler.
- Progression counts as "priority", so chest looks by contents (`correct_chest_appearances`) show it as a major item,
  like OoTR's multiworld does. Our logic never needs it.

### Where they may go (the apworld's item rule)

`parity.archipelago.takes_foreign(location_name) -> bool` is pure (no world, no settings). `foreign_locations()`
returns the whole set, 221 locations in version 1.

- **166 chests** that can run their own scene. Those are the small and big chests without a story or minigame scene,
  the same chests that can hold an ice trap.
  - They're the chests in `data/rando/chest_map.json` (mode `full`/`group`), the chests plugin's chests
    (`chests_locations.json`, with their copies) and the dungeons plugin's kept chests.
  - Not the Treasure Chest Game's rooms, and not the remake's ice-trap chests (A_04).
- **55 core scene locations** (`config/rando_locations.json` verified + testing). That's NPC gifts, songs, cutscenes,
  boss rewards, Great Fairies and the songs/trade plugin's NPCs.
- Every other location refuses foreign items in version 1: pots, grass, crates, rocks, bushes, Skulltulas, shops,
  scrubs, freestanding hearts, fairies, silver rupees, the Treasure Chest Game and the A_04 chests.
  - **The version 1 restriction is temporary.** The plan is for items to be allowed at every spot.
  - Each of those location kinds already has an Ice Trap path (give nothing, play a scene). Each one needs the same
    hook to call the location's found text instead, and the songs/trade NPCs already have it
    (`songs_trade._target`).
  - `takes_foreign` widens as each kind gets wired up. The apworld reads it, so nothing else has to change.
- A location that a setting locks (like HC Malon Egg without the child trade shuffle) is `locked` in the `.aprr`.
- The generator refuses a placeholder anywhere else (`check_settings`, `item_for`, `foreign_plan`).

### What the player sees

- **Chest:** the chest opens the way it normally does (a small one from the front or with a kick, a big one with the
  whole suspense opening). Nothing is shown above Link. Then a text box comes up and the chest stays open. Nothing
  gets added to the inventory.
  - Each of those chests gets its own scene row, a new `RSDB/EventSetting` row, the way OotrR adds hundreds of them
    on Hookshot. That's unproven on Longshot until the probe passes.
  - If it fails, chests fall back to one shared scene per chest size, with a text that doesn't name a player
    (`_archipelago_text.generic_ops`, "You found an item for another world!").
- **NPC or scene location:** the same text box comes up where the NPC would hand the item over. Nothing gets added.
- **Text:** `You found <item> for <player>!` in all 16 languages (`_archipelago_text.py`). One shared step,
  `RandoAP_FoundTexts:RandoAP_Say`, takes the flag and the message as arguments, like vanilla text steps do.
  - The item name is highlighted like OoTR's key words.
  - Names are cleaned up for each language's font. A character the font can't draw becomes a look-alike, or `?` if
    there isn't one.
  - Names are cut at 40 (item) and 16 (player) characters with `…`.
  - Lines are broken the same way the game's texts are, since the game doesn't wrap by itself.
- **Saved flag:** the location also sets the saved Bool `RandoAP_Found_<location_id>` (AP location id, in decimal).
  The client sees the check even where the game keeps no flag for it (OotrR found chests write none).

### What build_patch must add (settings, before it runs the generator)

```json
"remake_archipelago": {
  "mailbox_version": 1,
  "seed_key": "8 to 16 characters [A-Za-z0-9]",
  "foreign": {
    "KF Midos Top Right Chest": {"item": "Hammer", "player_name": "Bob", "classification": "progression",
                                 "location_id": 340578566301}
  }
}
```

- `foreign` is exactly `ap.json` `"foreign"` plus `location_id`. Every key must be a location whose placed item is
  the placeholder for its classification, and every placeholder must have an entry.
- `seed_key` is the seed's identity in saves (`RandoAP_Seed_<seed_key>`, section 2). Put it in `ap.json` too.
- Checks with no save flag. This is planned for version 2, and the function doesn't exist yet. Some AP locations of a
  seed have no `tracker.json` flag, own items included. build_patch writes them to `ap.json` `"flagless"` once
  `tracker.json` exists. Then it calls
  `parity.archipelago.flagless_plan(settings, world, flagless) -> {plan section: value}` (`flagless` is
  `{location name: AP location id}`) and merges the result into `plan.json` with `generate.merge_plan` before
  make_patch. The call is skipped while the function isn't there. Version 2 will set
  `RandoAP_Found_<id>` at those spots, so the client sees every check. That needs a flag step at each location kind's
  give, the same hooks as widening `takes_foreign`.
- The plugin `archipelago` must be enabled. It's in `config/plugins.json` and does nothing without this setting. The
  setting is `REMAKE_INTERNAL`, so the app never shows it as a setting.

## 2. Receiving items (C: the client)

### GameData the client reads and writes

They're all plain Bools, saved with the file, as new rows of `GameData/GameDataList` that default to false.

| Name | Who writes | Meaning |
|---|---|---|
| `RandoAP_Seed_<seed_key>` | game (the new file's opening) | this save belongs to this seed. Deliver nothing unless true. |
| `RandoAP_Count0` to `RandoAP_Count15` | game | received items the game has taken, in binary (bit 0 = 1). Saved, so an older save gets back what it lost. |
| `RandoAP_Code0` to `RandoAP_Code9` | client | the item code (section 3), in binary (bit 0 = 1). |
| `RandoAP_Idx0` to `RandoAP_Idx3` | client | the low 4 bits of the received-item index being delivered. |
| `RandoAP_Signal` | client sets true, game clears | "an item is waiting". |

- Hashes are `murmur3_32(name)` (seed 0, `tools/romtools.murmur3_32`), all precomputed in `mailbox.json`.
- These are rows in the plain Bool table, like OotrR's `RandoAP.Recv.*`. Bool writes are the memory access OotrR
  proved.

### How the game takes an item

1. Every frame of play, `Sequence/MainUpdate.module.ainb` reads `RandoAP_Signal`.
   - When it's true and no main event is playing or requested (`SeqQueryIsPlayingMainEvent`, prepare and request
     included), it requests the scene row `RandoAP_Mailbox`.
   - In the same frame it sets `RandoAP_Signal` back to false. This is OotrR's pattern, built from vanilla
     `Sequence/AfterEvent.module.ainb` nodes 24/35/36/38/40.
2. The row plays `RandoAP_Mailbox:RandoAP_Receive`, which lives in its own new scene file:
   - It compares `Idx` with the low 4 bits of `Count`. If they differ, it ends right away, so a stale or repeated
     request gives nothing and counts nothing.
   - It reads `Code` and hands the item over the way a single-player NPC gift would:
     - the item-get pose and text
     - the right progressive tier
     - dungeon keys, boss keys, maps, compasses and key rings credited to their own dungeon from anywhere
     - a small key received while Link is in its dungeon brings up the HUD key counter right away, like a vanilla
       key does (named keys and rings go through the dungeons plugin's `GetPouchContent:Rando_DI_KeyShow`). OoTR's
       generic Small Key and Boss Key (only from a /send) credit the dungeon Link is in. On a dungeon's map they
       then show the key counter or the boss key with the game's HUD steps. Anywhere else nothing is shown.
     - no ammo without its container
     - an Ice Trap freezes
   - It adds 1 to `Count`.
   - Code 0, or a code this patch doesn't know, gives nothing but still counts, so the queue never gets stuck.

### The client's loop (one item at a time)

```
received = ReceivedItems from the server, in index order (items_handling 0b101: remote items and start inventory)
loop every ~0.25 s while the game runs:
    if not RandoAP_Seed_<seed_key>: wait                      # title screen, or another seed's save
    n = Count
    if n >= len(received): continue                            # up to date
    if Signal is true: wait                                    # not taken yet (menu, cutscene, loading)
    if an attempt for index n is in flight and less than 8 s old: wait
    code = codes[item name of received[n]]                      # mailbox.json "codes"; 0 if it has none
    write Idx  = (n + 1) & 15                                  # invalidates the old code while it changes
    write Code = code
    write Idx  = n & 15
    write Signal = true                                        # last
```

- `Count` going from n to n+1 is the delivery receipt.
  - If it hasn't moved 8 s after `Signal` went false, send index n again. The Idx check makes a repeat harmless
    (OotrR's retry, `receive.py`).
  - If a save gets loaded in the meantime, it just shows another `Count`, and the loop continues from that.
- A received item with no code (an item from a newer apworld) gets sent with code 0 and reported to the player, so
  the queue moves on. (`CONTRACT.md` says such items stay in their own world.)

### Ordering and duplicates

- The game's `Count` is the only record. It's saved with the file, so a reload, a reconnect or a second client gives
  nothing twice and loses nothing.
- Start inventory (location -2), `/send` and item links are ordinary received items, and they arrive in server order.

## 3. Item codes

`mailbox.json` `"codes"`: `{OoTR item name: code}`.

- Codes run from 1 to 1023 (10 bits). 0 means nothing (counted, nothing given).
- Append-only and never renumbered. A new item takes the next free code.
- Version 1 has 254 codes, and every one has a give. They cover every OoTR item a player can receive (types `Item`,
  `Song`, `SmallKey`, `SmallKeyRing`, `BossKey`, `GanonBossKey`, `Map`, `Compass`, `Token`, `HideoutSmallKey(Ring)`,
  `TCGSmallKey(Ring)`, `SilverRupee`, `DungeonReward`), plus the items our plugins add (progressive swords, stick and
  nut bags, the Fishing Pole, the Master Sword, souls, the Skeleton Key) and the trap kinds of `remake_trap_weights`
  as the spoiler and `ids.json` name them. Each of those (`Shock Trap`, `Fire Trap`, `Rupee Trap`) plays its kind's
  effect.
- `Shop`, `Event`, `Drop` and `Refill` entries and the four placeholders have no code.

## 4. Cost

- **Per frame:** one GameData Bool read and one selector in `MainUpdate`. The main-event query only runs while
  `Signal` is true. There's no new actor and no resident model.
- **No vanilla scene file grows** except `OpeningEvent` (+1 call, the seed marker). Four new scene files, each a
  renamed copy of a small vanilla file, only get loaded by the scenes that use them:
  - `RandoAP_Mailbox` (copy of `DmF_SY_FallDown`): the mailbox, only loaded when an item arrives
  - `RandoAP_FoundTexts` (copy of `Dm_SY_LetterBottle`): the found texts and the seed marker
  - `RandoAP_TreasureboxSml` and `RandoAP_BigChests` (copies of the two chest scene files): the opening of a chest
    holding another player's item
  - Ordinary chests and NPC gifts load exactly what they would without the mailbox.
- **Boot-loaded tables:** one `EventSetting` row and one scene-info row per foreign chest (at most 166), plus the
  mailbox's. Then 31 save Bools, plus 1 seed marker, plus 1 per foreign location (at most 221).
- **Measured** in a stress seed with 220 foreign locations and 254 codes, decompressed:

  | File | Size |
  |---|---|
  | `RandoAP_Mailbox` | 199 KB |
  | `RandoAP_FoundTexts` | 110 KB (385 KB without the shared found step) |
  | `RandoAP_TreasureboxSml` | 133 KB |
  | `RandoAP_BigChests` | 64 KB |
  | `MainUpdate` | 4.8 to 7.1 KB |
  | `OpeningEvent` | +0.2 KB |
  | `Dm_SY_GetInEvent` | +6 KB, the dungeons plugin's credit entries for received keys |

  - `GetPouchContent` and the vanilla chest files are unchanged.
  - Frame time still has to be compared in game (probe step 7).
- **Heap reservations:** make_patch's size-table rule for byml files adds 384 bytes per new dict or array element.
  That raises the boot tables' entries by about 0.85 MB in that seed (`EventSetting` +271 KB, scene info +575 KB).
  - The vanilla entries of these tables are only their file size plus about 280 bytes.
  - So once the probe proves the rows, an RSDB-specific rule could give most of that back. Until then I'm keeping it
    generous.

## 5. In-game probe (before the first multiworld)

The probe is `plans/ap_mailbox_probe.json`, built by
`python tools/rando/parity/archipelago.py --probe out/ap_probe`. The steps are in the plan's `description` and
in `out/ap_probe/CHECKLIST.md`. It doesn't need a client:

- The four chests in Mido's House hold "other players' items".
- Each chest's found scene then writes Code, Idx and Signal as the client would.
- The third chest repeats an index on purpose, and it has to give nothing.

In one new file, it tests:

- new EventSetting rows
- new scene files
- the MainUpdate watcher
- the mailbox (Hookshot, then Longshot, then a Piece of Heart)
- the duplicate guard
- the found texts
- the new save rows and the seed marker
- frame time
