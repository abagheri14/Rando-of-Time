# Source of the OoTR reference data

- Project: OoT Randomizer, https://github.com/OoTRandomizer/OoT-Randomizer
- Branch: `Dev`
- Commit: `526b4c8d81b7c4023ef4573ffbaf39344e270d5b` (committed 2026-11-02T19:27:43Z)
- Fetched from `https://raw.githubusercontent.com/OoTRandomizer/OoT-Randomizer/526b4c8d81b7c4023ef4573ffbaf39344e270d5b/<path>`
  (pinned to the SHA, not the moving branch). File sizes match the GitHub contents API listing.

## License

`raw/LICENSE`: "All files are MIT licensed unless stated otherwise. Folders licensed under a different
license (GPLv2+) include the respective license file." The only other license files in the repo tree at this
commit are under `bin/` (Compress, Decompress, gzinject, minibsdiff) and `Notes/Chest Textures/rgba5551topng/`.
Nothing was taken from those folders. Every file here is from the repo root or `data/`, so all of it is MIT.
Keep `raw/LICENSE` with anything derived from it: the MIT notice must travel with copies and substantial portions.

## What is in raw/

| Local path | Upstream path | Notes |
|---|---|---|
| `raw/LICENSE` | `LICENSE` | MIT |
| `raw/World/*.json` (14 files) | `data/World/<name>.json` | 12 vanilla dungeons + `Overworld.json` + `Bosses.json` |
| `raw/World_MQ/*.json` (12 files) | `data/World/<name> MQ.json` | Master Quest dungeons, kept separate |
| `raw/LogicHelpers.json` | `data/LogicHelpers.json` | rule aliases and macros |
| `raw/LocationList.py` | `LocationList.py` | location table |
| `raw/ItemList.py` | `ItemList.py` | item table |
| `raw/SettingsListTricks.py` | `SettingsListTricks.py` | names and descriptions of the `logic_*` tricks and the glitch/advanced tricks (extra, for trick names) |
| `raw/semantics/RuleParser.py`, `State.py`, `RulesCommon.py`, `World.py`, `SettingsList.py` | same names at repo root | extra: they define how rule strings are interpreted (reference reading only) |

Not fetched: `data/Glitched World/` (glitch logic, N64-only), `data/Hints/`, the patcher, and the ASM.

## Safety / how it was processed

- None of OoTR's Python was imported or executed. `export_ootr.py` (in this folder, outside `raw/`) reads
  `LocationList.py`, `ItemList.py`, `SettingsListTricks.py`, `State.py`, `SettingsList.py` and `World.py` with
  `ast.parse`. It evaluates only literal table entries with its own small evaluator (constants, tuples, lists,
  dicts, `GetItemId.X` lookups from the parsed enum, `float('Inf')` stored as `"Infinity"`, and a reimplementation
  of the one-line `shop_address()` formula). Run it with `python -I export_ootr.py`.
- The world JSON files are not strict JSON (`#` comments, newlines inside strings). They are loaded the same way
  OoTR's `Utils.read_logic_file` does it: cut each line at `#`, join the lines with spaces, collapse runs of spaces,
  then `json.loads`. Rule strings are therefore OoTR's text with comments removed and whitespace collapsed
  (then trimmed). No tokens are changed. Duplicate keys were checked for and none were found.
- Every rule string (2,286 vanilla, 1,040 MQ, 156 helpers) was syntax-checked with `ast.parse(mode='eval')`
  and walked to build the identifier inventory in `stats.json`. All of them parsed, and every identifier was
  classified (item / helper / trick / setting / world attribute / event / State method / parser builtin).

## Outputs (this folder)

- `logic.json`: `source`, `notes`, `regions` (342 vanilla regions from the 14 files), `locations` (1,448:
  every LocationList entry except the MQ-only ones, joined to the region(s) that list it), `helpers`
  (LogicHelpers.json as-is), plus `items` (286, from ItemList.py, with `rule_name` = the identifier used in rules)
  and `tricks` (371: 186 glitchless `logic_*` and 185 advanced/glitch).
- `logic_mq.json`: `regions` (144 MQ regions) and `locations` (784 that appear in MQ files). Use it with the
  Overworld/Bosses regions, helpers, items and tricks from `logic.json`. 13 shared names, such as
  `Sheik in Ice Cavern` and the `Drop` refills, are in both files.
- `stats.json`: counts and the rule-language inventory used for `summary.md`.
- Region fields: `name, file, scene, dungeon, hint, time_passes, events, locations, exits`, plus
  `alt_hint / provides_time / is_boss_room / savewarp` when present, plus derived `area` (dungeon, else hint
  area, else the nearest hint area found by walking incoming exits backwards; such regions have `area_inferred: true`).
- Location fields: `type, scene_id, scene_hex, default, vanilla_item, categories, n64_rom_addresses, regions,
  region (null if listed in more than one region), area, logic_file`. `default` is the N64 flag: chest flag,
  collectible flag, GS flag bits, or `[room, scene_setup, actor_index]` tuple(s) for pots, crates,
  freestanding items and wonderitems. See the header comment in `raw/LocationList.py`.
