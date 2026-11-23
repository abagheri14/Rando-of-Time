# Archipelago contract (Rando of Time)

This is the contract between the three parts of our Archipelago support: the apworld and seed builder (**A**), the
in-game receive patch (**M**) and the client app (**C**). Each part follows the sections marked with its letter. If
you change a shared section, update all three parts together.

## Game name

The game name is `"Rando of Time"`. OotrR registers `"OoT Remake"`, and the names have to stay different so players
can install both apworlds side by side.

## A: `data/archipelago/ids.json`

```json
{"format": 1, "game": "Rando of Time", "base": 340717076480,
 "locations": {"KF Midos Top Left Chest": 340717076481, "...": 0},
 "items": {"Progressive Hookshot": 340717076481, "...": 0}}
```

- `base` is `0x4F54520000`. Every id is `base + n`, with n starting at 1. Locations and items are numbered separately
  (AP keeps them in separate tables).
- **Append-only.** `tools/archipelago/build_ids.py` gives each new name the next free number. Every existing name
  keeps its number across versions, even after the settings stop generating that name.
- **Location names** come from our generator, so they're OoTR's location names plus the ones the remake adds (drops,
  bushes, fairies, silver rupees...). They're exactly the names in `spoiler.json` `"locations"` and `tracker.json`
  `checks[].name`. The table covers every location any setting can create, which is OoTR's whole location table (MQ
  included) plus every location our plugins add.
- **Item names** are the names `spoiler.json` shows, so OoTR's item table plus the items our plugins add.
- The apworld bundles a copy, because Archipelago needs both tables when it imports the world.

## A: the `.aprr` file (one per player of this game)

Archipelago's generation writes `AP_<seed>_P<slot>_<name>.aprr` (JSON, UTF-8) into its output zip.

```json
{
 "format": "rando-of-time-ap", "version": 1,
 "game": "Rando of Time", "world_version": "0.8.1",
 "seed_name": "AP seed name",
 "seed": "our generator seed (a string)",
 "settings": {"the settings dict, as settings_used.json \"settings\"": 0},
 "plugins": ["the enabled plugins, as settings_used.json \"plugins\""],
 "slot": 1, "slot_name": "Alice", "team": 0,
 "players": {"1": {"name": "Alice", "game": "Rando of Time"}, "2": {"name": "Bob", "game": "A Link to the Past"}},
 "placements": {
   "KF Midos Top Left Chest": {"item": "Progressive Hookshot", "item_id": 340717076600, "player": 1,
                               "player_name": "Alice", "game": "Rando of Time", "own": true,
                               "classification": "progression", "flags": 1, "location_id": 340717080000,
                               "locked": false},
   "KF Midos Top Right Chest": {"item": "Hammer", "item_id": 1234, "player": 2, "player_name": "Bob",
                                "game": "A Link to the Past", "own": false, "classification": "progression",
                                "flags": 1, "location_id": 340717080001, "locked": false}
 },
 "remote": [{"item": "Bow", "location": "Bob's location name", "location_id": 59012, "player": 2,
             "player_name": "Bob"}],
 "start_inventory": {"Deku Shield": 1},
 "world_check": {"locations": "sha256 of the sorted location names", "pool": "sha256 of the sorted item pool"}
}
```

- `placements` holds every location of this player that Archipelago knows, with this player's items and other
  players' items alike.
  - `own`: the item is this player's own item of this game. It goes into our seed like any single-player item.
  - `own: false`: another player's item (any game). Our seed puts M's placeholder there (see below).
  - `classification` is `"progression"`, `"trap"`, `"useful"` or `"filler"` (in that order of precedence), from
    Archipelago's ItemClassification. `flags` is the raw value.
  - `locked` means our generator placed it before Archipelago's fill. That's whatever OoTR's fill places before its
    main fill (shop items, songs on song spots, dungeon-bound keys...), plus the spots that can't show another
    player's item (MAILBOX.md `takes_foreign`). Only this player's own items can fill those
    (`tools/archipelago/world.py` `_home_fill`).
- `fixed`: `{location: item}`, the spots our logic never reaches even with every item (a rule `False`, like an
  unproven chest that only takes junk). Archipelago needs every location it knows to be reachable, so these aren't
  Archipelago locations. Our generator puts this player's own junk there, build_patch places it, and they have no id.
- `remote`: this player's items that sit in other players' worlds (the server sends them when they're found).
- `start_inventory`: this player's starting items from Archipelago (`start_inventory`, `start_inventory_from_pool`).
  build_patch does **not** bake them into the seed. The server sends them as received items (location -2), so the
  client delivers them once, like any other received item.
- Starting items from the settings (`starting_items`, `starting_inventory`...) stay ours, and the seed gives them
  itself.
- `world_check` lets build_patch prove it rebuilt the same world as the apworld.
- `settings` holds `remake_archipelago` with this seed's `seed_key` (MAILBOX.md section 1) and an empty `foreign`,
  which build_patch fills in.

## A: `python tools/archipelago/build_patch.py FILE.aprr OUT`

Builds a normal seed folder from one `.aprr`:

- `OUT/plan.json`, `spoiler.json`, `seed.json`, `tracker.json`, `settings_used.json`, as `tools/rando/generate.py`
  writes them. `tools/make_patch.py` and `tools/rando/in_game_check.py` then work unchanged.
- It runs our generator with the `.aprr`'s seed, settings and plugins, and only replaces the fill. Every placement is
  forced, and other players' items become M's placeholder for their classification, named in
  `remake_archipelago.foreign`. It refuses a `.aprr` whose world it can't rebuild exactly (`world_check`), or a
  placement a plugin moved after the fill.
- `OUT/ap.json`:

```json
{
 "format": 1, "game": "Rando of Time", "mailbox_version": 1, "seed_key": "Tu7Q1xSRiQxU",
 "seed_name": "...", "seed": "...", "slot": 1, "slot_name": "Alice", "team": 0,
 "players": {"1": {"name": "Alice", "game": "Rando of Time"}},
 "locations": {"KF Midos Top Left Chest": 340717080000},
 "foreign": {"KF Midos Top Right Chest": {"item": "Hammer", "player": 2, "player_name": "Bob",
                                         "game": "A Link to the Past", "classification": "progression"}},
 "start_inventory": {"Deku Shield": 1}, "goal": {"kind": "ganon"}, "warnings": [], "changed": []
}
```

  - `locations`: every location of this seed that Archipelago knows, by our location name (the `tracker.json` check
    names), with its AP id. C sends `LocationChecks` with these ids.
  - `foreign`: the locations holding another player's item.
  - `flagless`: `{location: id}`, the Archipelago locations whose `tracker.json` check has no save flag (own items
    included). The client can't see those from the save unless the mailbox sets `RandoAP_Found_<id>` there.
  - `mailbox_version` is the version of M's interface this seed's patch was built for. `seed_key` is the seed's
    identity in saves (`RandoAP_Seed_<seed_key>`).
  - `goal`: `{"kind": "ganon"}` or `{"kind": "triforce_hunt", "count": N}` (the plan's own Triforce goal, else the
    settings' `triforce_goal_per_world`).
  - `warnings`: no-save-warp strandings our post-fill check found. They're reported, not refused, because in a
    multiworld items from others can arrive at any time. `changed`: own placements a plugin rewrote after the fill
    (the drops plugin turns an own "Nothing" into an Ice Trap or junk).
- Once `tracker.json` is written, build_patch calls the mailbox's `parity.archipelago.flagless_plan(settings, world,
  flagless)` (skipped while it doesn't exist) and merges what it returns into `plan.json` (`generate.merge_plan`)
  before `make_patch`. So it's one build, with no settings key.

## A: the apworld

- `apworld/rando_of_time/` (the world's source) and `tools/archipelago/build_apworld.py`, which writes
  `rando_of_time.apworld` (put it in Archipelago's `custom_worlds`).
- The world runs our generator from an installed randomizer folder, set in Archipelago's `host.yaml`
  (`rando_of_time_options: randomizer_folder, python`).
- `slot_data`: `{"world_version", "seed", "seed_key", "mailbox_version", "death_link": false}`.
- Items with no mailbox code (`mailbox.json` `codes`) stay in their own world (`local_items`).
- As it writes each `.aprr`, the world runs `build_patch.py FILE --check` (a throwaway build). If our generator can't
  build a slot, Archipelago's generation fails right there with the reason, instead of it failing later on the
  player's machine.

## M: other players' items in our seed (details in `data/archipelago/MAILBOX.md`)

MAILBOX.md section 1 defines these and we use them as they are: the four placeholder items
`Archipelago Item (<class>)`, the plugin `archipelago` with the setting `remake_archipelago` (`mailbox_version`,
`seed_key`, `foreign`), `takes_foreign` (through the plugin's item rule) and `mailbox.json` (`mailbox_version`,
`placeholders`, `codes`). Without the plugin, build_patch falls back to a `Recovery Heart` stand-in.

## C: what the client can rely on

- `ap.json` (above), next to the seed's other files.
- Own items at own locations are already in the seed, and the game gives them. Only ask the server for remote items
  and the starting inventory (`items_handling` 0b101), so nothing gets delivered twice.
- The goal is OoTR's goal for the settings (Ganon, or the Triforce Hunt), same as single player.

## C: the client (code in `tools/archipelago/client/`)

`python tools/archipelago/ap_client.py [OUT] [--connect SERVER] [--slot NAME] [--nogui]`. The randomizer app's
button runs `pythonw tools/archipelago/ap_client.py "<OUT>"`. Here's what it reads and sends, so A and M can rely on
it:

- **Connect:** game `"Rando of Time"`, name = `ap.json` `slot_name` (or the one typed), `items_handling` 0b101, and
  it asks for `slot_data`. It refuses, with no retry, when `slot_data.seed` differs from `ap.json` `seed`, or when
  `slot_data.mailbox_version` (else `ap.json`'s) isn't one it knows (1).
- **Which save:** the newest `slot_NN/progress.sav` under the save folder whose `RandoAP_Seed_<ap.json seed_key>` is
  true. The running game is only read while that marker is true in memory too. Without `seed_key` in `ap.json` the
  client can't tell seeds apart, so it just reads the newest save and never reads or writes the game.
- **Checks out:** a location is done when any `tracker.json` flag of its check is set (`b64`, `bit`, `bool`, same as
  the tracker) or the Bool `RandoAP_Found_<location id>` is (read for every AP location, foreign or not). The checks
  marked by hand in the tracker count too (an option, on by default). They're sent as `LocationChecks` with the
  `ap.json` ids, and only ids of this slot are ever sent.
- **Goal:** `StatusUpdate` 30 once the save shows Ganon beaten (Enum `Step_Defeat_Ganon` = `Complete`, or the Bool
  `HavePlayedEvent.Dm_Ending_0000`) or the running game does (that Bool, or `Sequence_ToTitleFromGameClear`). In a
  Triforce Hunt it's once the saved Int `Rando_TriforcePieceNum` reaches `plan.json` `_gaps.triforce.goal` (else the
  settings' `triforce_goal_per_world`).
- **Items in:** exactly as MAILBOX.md section 2 says (codes from `data/archipelago/mailbox.json`, item names from the
  server's DataPackage, else `ids.json`). The only memory it writes is `RandoAP_Code*`, `RandoAP_Idx*` and
  `RandoAP_Signal`, and an allowlist in the code enforces that.
