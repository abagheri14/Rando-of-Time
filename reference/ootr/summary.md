# OoTR logic: what is there and what a port needs

Source: OoT Randomizer `Dev` @ `526b4c8d` (2026-11-02), MIT. See `SOURCE.md`. All numbers below come from `logic.json` / `logic_mq.json` / `stats.json`, which `export_ootr.py` generates.

## Size

| | Vanilla (incl. Overworld + Bosses) | MQ dungeons |
|---|---:|---:|
| Logic files | 14 | 12 |
| Regions | 342 | 144 |
| Exit rules | 676 | 227 |
| Location rules (one per region listing) | 1,552 | 803 |
| Event rules | 58 | 10 |
| Distinct locations | 1,448 | 784 |
| Item checks (excl. Drop/Event/Hint/HintStone) | 1,370 | 774 |

Also: 156 helpers (12 take parameters), 286 items, 371 tricks (186 glitchless `logic_*`, 185 advanced/glitch), 29 `savewarp` regions, 11 `is_boss_room` regions. Every rule parsed. There were no duplicate keys, and every location named in a world file exists in LocationList and the other way round.

## Locations by type

"Vanilla world files" means the 14 non-MQ files. A location can be listed in both columns, like the 13 shared names such as `Sheik in Ice Cavern` and the refill `Drop`s.

| Type | What it is | LocationList (all) | in vanilla world files | in MQ world files |
|---|---|---:|---:|---:|
| Chest | treasure chests | 305 | 179 | 128 |
| Freestanding | freestanding rupees / recovery hearts (`shuffle_freestanding_items`) | 205 | 155 | 51 |
| Collectable | flagged collectibles: Pieces of Heart, a few freestanding small keys | 35 | 28 | 7 |
| RupeeTower | rupee "towers"/bean-platform rupee sets | 21 | 21 | 0 |
| GS Token | Gold Skulltulas | 144 | 100 | 44 |
| NPC | NPC gifts, minigames, Skulltula House, **cows** (9, category `Cows`) | 72 | 71 | 1 |
| Song | song teachers | 12 | 12 | 1 |
| Cutscene | cutscene gifts (Ocarina of Time, Light Arrows, Great Fairy spells/upgrades, Gift from Sages) | 9 | 9 | 0 |
| Boss | dungeon rewards (stones/medallions incl. Rauru's) | 9 | 9 | 0 |
| BossHeart | boss Heart Containers | 8 | 8 | 0 |
| Scrub | overworld/dungeon Deku Scrub salesmen | 23 | 13 | 10 |
| GrottoScrub | grotto Deku Scrubs | 23 | 23 | 0 |
| Shop | shop shelf slots (8 shops x 8) | 64 | 64 | 0 |
| MaskShop | Happy Mask Shop items | 8 | 8 | 0 |
| Pot | pots | 540 | 341 | 199 |
| FlyingPot | flying pots | 30 | 21 | 9 |
| Crate | large crates | 214 | 74 | 140 |
| SmallCrate | small crates | 35 | 6 | 29 |
| Beehive | beehives | 32 | 32 | 0 |
| Wonderitem | invisible "wonder item" drops (hidden rupees, etc.) | 197 | 116 | 81 |
| SilverRupee | silver rupees (`shuffle_silver_rupees`) | 154 | 80 | 74 |
| Drop | refill sources used only by logic (Deku Baba sticks/nuts, fairies, bugs, fish, blue fire) | 21 | 20 | 9 |
| Event | Ganon/Triforce, Scarecrow Song, Deliver Letter, Time Travel | 4 | 4 | 0 |
| Hint | static hint spots (ToT altar, Ganondorf, Deku Theater...) | 14 | 14 | 0 |
| HintStone | Gossip Stones | 40 | 40 | 1 |
| **Total** | | 2,219 | 1,448 | 784 |
| **Item checks** | (all minus Drop/Event/Hint/HintStone) | 2,140 | 1,370 | 774 |

Not modelled by OoTR at all: grass/bushes, rocks/boulders, trees, signs, icicles, red ice, fish, fairies as checks, beggar, Fire Temple gorons. These are SoH-only shuffles (see `../other_randomizers.md`). Cows have no type of their own: they are `NPC` with category `Cows`.

Other vanilla categories worth knowing: Cows 9, Great Fairies 6, Minigames 36, Grottos 131, Deku Scrub Upgrades 3, Skulltula House 6, Thieves' Hideout 46.

## Item checks by area (vanilla logic)

Area = dungeon, else the region's hint area. Interiors and grottos without a `hint` are assigned to the hint area of the region they are entered from (`area_inferred`). Bosses.json regions belong to their dungeon. Columns: Free = Freestanding + Collectable + RupeeTower, NPC/Song/CS = NPC + Song + Cutscene, Boss/Heart = Boss + BossHeart, Scrub = Scrub + GrottoScrub, Shop = Shop + MaskShop, Pot = Pot + FlyingPot, Crate = Crate + SmallCrate.

| Area (vanilla logic) | Chest | Free | GS | NPC/Song/CS | Boss/Heart | Scrub | Shop | Pot | Crate | Hive | Wonder | Silver | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ROOT |  |  |  | 1 |  |  |  |  |  |  |  |  | 1 |
| KOKIRI_FOREST | 6 | 22 | 3 | 1 |  |  | 8 | 5 |  | 2 | 9 |  | 56 |
| LOST_WOODS | 1 | 9 | 3 | 8 |  | 5 |  |  |  | 3 | 3 |  | 32 |
| SACRED_FOREST_MEADOW | 1 |  | 1 | 2 |  | 2 |  |  |  | 1 | 6 |  | 13 |
| HYRULE_FIELD | 3 | 1 | 2 | 3 |  | 1 |  | 2 |  | 7 | 3 |  | 22 |
| LON_LON_RANCH |  | 1 | 4 | 6 |  | 3 |  | 10 | 1 | 1 | 2 |  | 28 |
| MARKET | 11 |  | 1 | 8 |  |  | 32 | 58 | 13 |  | 7 |  | 130 |
| TEMPLE_OF_TIME |  |  |  | 2 | 1 |  |  |  |  |  |  |  | 3 |
| HYRULE_CASTLE |  |  | 2 | 4 |  |  |  | 4 |  |  | 13 |  | 23 |
| OUTSIDE_GANONS_CASTLE |  |  | 1 | 1 |  |  |  |  |  |  |  |  | 2 |
| KAKARIKO_VILLAGE | 2 | 2 | 6 | 16 |  |  | 16 | 11 | 18 | 2 | 2 |  | 75 |
| GRAVEYARD | 4 | 11 | 2 | 1 |  |  |  | 6 | 1 |  | 15 |  | 40 |
| DEATH_MOUNTAIN_TRAIL | 2 | 14 | 4 | 5 |  |  |  |  |  | 3 |  |  | 28 |
| GORON_CITY | 3 | 9 | 2 | 4 |  | 3 | 8 | 9 | 1 | 1 |  |  | 40 |
| DEATH_MOUNTAIN_CRATER | 1 | 17 | 2 | 2 |  | 4 |  | 4 |  | 3 |  |  | 33 |
| ZORA_RIVER | 1 | 6 | 4 | 8 |  | 2 |  |  |  | 3 | 31 |  | 55 |
| ZORAS_DOMAIN | 1 |  | 1 | 3 |  |  | 8 | 5 |  | 3 |  |  | 21 |
| ZORAS_FOUNTAIN |  | 20 | 3 | 1 |  |  |  | 7 |  |  |  |  | 31 |
| LAKE_HYLIA |  | 7 | 5 | 7 |  | 3 |  |  |  | 1 |  |  | 23 |
| GERUDO_VALLEY | 1 | 10 | 4 | 2 |  | 2 |  |  | 2 | 1 | 2 |  | 24 |
| GERUDO_FORTRESS | 1 | 1 | 2 | 2 |  |  |  |  | 20 |  | 2 |  | 28 |
| THIEVES_HIDEOUT |  | 4 |  | 1 |  |  |  | 16 | 13 |  | 12 |  | 46 |
| HAUNTED_WASTELAND | 1 |  | 1 | 1 |  |  |  | 4 | 5 |  |  |  | 12 |
| DESERT_COLOSSUS |  | 1 | 3 | 2 |  | 2 |  |  |  | 1 | 5 |  | 14 |
| Bottom of the Well | 13 | 8 | 3 |  |  |  |  | 22 |  |  |  | 5 | 51 |
| Deku Tree | 6 | 5 | 4 |  | 2 |  |  |  |  |  |  |  | 17 |
| Dodongos Cavern | 6 | 4 | 5 |  | 2 | 4 |  | 28 |  |  |  |  | 49 |
| Fire Temple | 14 | 9 | 5 |  | 2 |  |  | 15 | 2 |  |  |  | 47 |
| Forest Temple | 13 | 4 | 5 |  | 2 |  |  | 19 |  |  |  |  | 43 |
| Ganons Castle (incl. tower) | 16 | 5 |  |  |  | 4 |  | 34 |  |  |  | 20 | 79 |
| Gerudo Training Ground | 21 | 3 |  |  |  |  |  |  |  |  | 3 | 15 | 42 |
| Ice Cavern | 3 | 8 | 3 | 1 |  |  |  | 9 |  |  |  | 10 | 34 |
| Jabu Jabus Belly | 3 |  | 4 |  | 2 | 1 |  | 17 | 2 |  |  |  | 29 |
| Shadow Temple | 16 | 17 | 5 |  | 2 |  |  | 24 |  |  | 1 | 15 | 80 |
| Spirit Temple | 19 | 2 | 5 |  | 2 |  |  | 30 | 2 |  |  | 15 | 75 |
| Water Temple | 10 | 4 | 5 |  | 2 |  |  | 23 |  |  |  |  | 44 |
| **Total** | 179 | 204 | 100 | 92 | 17 | 36 | 72 | 362 | 80 | 32 | 116 | 80 | 1,370 |

"Classic" OoTR checks (no pots, crates, hives, wonderitems, freestanding or silver rupees) are about Chest + Collectable + GS + NPC/Song/CS + Boss/Heart + Scrub + Shop = 179 + 28 + 100 + 92 + 17 + 36 + 72 = 524.

### MQ dungeons (item checks in MQ files; bosses live in the shared Bosses.json)

| MQ dungeon | Chest | Free | GS | NPC/Song/CS | Scrub | Pot | Crate | Wonder | Silver | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Bottom of the Well | 3 | 9 | 3 |  |  | 7 |  | 12 |  | 34 |
| Deku Tree | 7 | 7 | 4 |  | 1 |  | 3 | 4 |  | 26 |
| Dodongos Cavern | 6 | 2 | 5 |  | 4 | 30 | 22 |  | 5 | 74 |
| Fire Temple | 11 | 4 | 5 |  |  | 28 | 30 | 14 |  | 92 |
| Forest Temple | 12 | 6 | 5 |  |  | 21 | 3 |  |  | 47 |
| Ganons Castle | 12 | 4 |  |  | 5 | 12 |  | 1 | 15 | 49 |
| Gerudo Training Ground | 17 |  |  |  |  | 4 | 1 | 2 | 14 | 38 |
| Ice Cavern | 3 | 1 | 3 | 1 |  | 11 |  |  |  | 19 |
| Jabu Jabus Belly | 11 | 5 | 4 | 1 |  | 9 | 4 | 23 |  | 57 |
| Shadow Temple | 19 | 17 | 5 |  |  | 23 | 4 | 1 | 30 | 99 |
| Spirit Temple | 22 | 2 | 5 |  |  | 32 | 8 | 2 | 10 | 81 |
| Water Temple | 5 | 1 | 5 |  |  | 31 | 94 | 22 |  | 158 |
| **Total** | 128 | 58 | 44 | 2 | 10 | 208 | 169 | 81 | 74 | 774 |

## Rule language a port must support

Rules are Python *expressions* (never statements). OoTR compiles them in `raw/semantics/RuleParser.py`. A port needs an evaluator for this subset:

**Syntax used.** `and` / `or` (about 1,150 / 1,100 uses across all rules), `not`, `==`, `!=`, `<` (once: `chicken_count < 7`), `in` (helpers only, e.g. `'Deku Tree' in dungeon_shortcuts`), parentheses, `True`/`False`, string literals, `(Item, n)` count tuples (245 uses; `n` may be a setting name), and subscripts `skipped_trials[Forest]`. No arithmetic, lambdas or attribute access.

**How names resolve** (in this order, as in `Rule_AST_Transformer.visit_Name`):
1. Parser builtins: `here(rule)`, `at('Region', rule)`, `at_day`, `at_night`, `at_dampe_time`.
2. Helpers from `LogicHelpers.json`. They expand by text substitution and the result is re-parsed. 144 are plain aliases and 12 take parameters: `can_use(item)`, `can_play(song)`, `can_play_ocarina(song)`, `can_play_item(song)`, `has_projectile(for_age)`, `_is_magic_item/_is_adult_item/_is_child_item/_is_magic_arrow/_is_swappable_adult/_is_swappable_child/_adult_slingshot(item)`. Helpers can alias items (`Hookshot` = `Progressive_Hookshot`, `Longshot` = `(Progressive_Hookshot, 2)`, `Goron_Tunic` = `'Goron Tunic' or Buy_Goron_Tunic`). Use the quoted `'Item'` form to reach the real item without recursion.
3. Item names, escaped (spaces become `_` and `'()[]-` are dropped; see `items[*].rule_name`). They mean `state.has(item)`. Progressive items are counted.
4. World attributes (derived per seed, not user settings): `skipped_trials[...]`, `selected_adult_trade_item`, `disable_trade_revert`, `skip_child_zelda`, `entrance_shuffle`, `keysanity`.
5. Settings, folded to constants at parse time. 53 are referenced, e.g. `open_forest`, `open_kakariko`, `zora_fountain`, `gerudo_fortress`, `bridge`/`lacs_condition`/`shuffle_ganon_bosskey` (+ `*_stones/_medallions/_rewards/_tokens/_hearts`), `open_door_of_time`, `damage_multiplier` (`'ohko'`, `'quadruple'`), `deadly_bonks`, `gold_skulls_ignore_daytime`, `free_bombchu_drops`, `plant_beans`, `dungeon_shortcuts`, `shuffle_*` (pots, scrubs, tcgkeys, silver_rupees, empty_pots, overworld/dungeon/interior/hideout entrances, expensive_merchants, individual_ocarina_notes, gerudo_fortress_heart_piece), `adult_trade_shuffle`, `complete_mask_quest`, `big_poe_count`, `chicken_count`, `starting_age`, `warp_songs`, `hints`, `blue_fire_arrows`, `scarecrow_behavior`, `skip_reward_from_rauru`, `fix_broken_drops`, `triforce_goal_per_world`. Full list: `stats.json` -> `rules_*` -> `name:setting`.
6. State methods: `has_bottle` (122 uses, written bare without parentheses), `had_night_start`, `has_soul(Enemy)` (enemy-soul shuffle, 28 enemy symbols), `can_live_dmg`, `has_all_notes_for_song` (ocarina-note shuffle), `has_stones`, `has_medallions`, `has_dungeon_rewards`, `has_hearts`, `region_has_shortcuts`.
7. Evaluation kwargs: `age`, `spot`, `tod`, `TimeOfDay`.
8. Any other CamelCase name, or any quoted string, is an **event** (`state.has('Event Name')`). 58 vanilla and 10 MQ events are defined in `events` blocks, e.g. `Drain Well`, `Raise Water Level`, `Child Water Temple`, `Defeat <Boss>`, trade-quest `* Access`, `* Trial Clear`, `Showed Mido Sword & Shield`, `Hideout N Torches Jail Gerudo/Carpenter`, `Links Cow`, `King Zora Thawed`. Item-table "Event" items such as `Time_Travel`, `Scarecrow_Song` and `Epona` are used the same way.

**`here()` and `at()`.** `here(rule)` (79 uses) and `at('Region', rule)` (83 uses, 47 distinct target regions) turn a sub-rule into a hidden event in the current or named region. The sub-rule is then checked with the age and time of day of whoever reaches that region, not of the spot being evaluated. Farore's Wind and savewarp logic rely on `at()`.

**Age.** Each rule is evaluated separately for child and adult (`age` kwarg). The constructs are: `is_child` / `is_adult` (`age == 'child'`), `is_starting_age`, the `Time_Travel` event, `can_use(item)` (checks whether the item is usable at this age via `_is_adult_item` / `_is_child_item`, plus magic for spells), and `has_projectile(child|adult|both|either)`. `Root` -> `Root Exits` -> `Child Spawn` / `Adult Spawn` / warp-song regions / `Farores Wind Warp` form the virtual start of the graph.

**Time of day.** `at_night` (44 uses, mostly Gold Skulltulas), `at_day` (43), `at_dampe_time` (5). Regions have `time_passes: true` (15 overworld regions where you can wait) or `provides_time` (blue warps give DAY, `Ganons Castle Grounds` gives DAMPE). Related: `can_play(Suns_Song)`, `gold_skulls_ignore_daytime`, `had_night_start`.

**Tricks.** 186 glitchless `logic_*` tricks are defined (display name, tags and tooltip in `logic.json` -> `tricks`) and 185 of them are referenced (129 in vanilla files, 81 in MQ files, 53 MQ-only). `logic_deku_mq_lobby_gs` is not referenced by any fetched logic file. The 185 `glitch_*` / `adv_*` advanced tricks are used only by glitch-related helpers (`can_isg`, `can_hover`, `can_hess`, `can_superslide`, `can_weirdshot`, `can_oi`, `can_gdv*`, `can_dotskip_*`, `can_tsc`, ...) and by `data/Glitched World` (not fetched).

**Other mechanics in the rules.** Key counts per dungeon (`(Small_Key_Fire_Temple, 8)`, key rings, TCG keys), silver-rupee counts, `Gold_Skulltula_Token` counts, bottles, damage and OHKO (`can_take_damage`, `can_live_dmg`), dungeon shortcuts (`*_shortcuts`), refills via `Drop` locations and `Buy_*` shop items, bean planting (`can_plant_bean`), the adult trade chain (`* Access` events, `guarantee_trade_path`), enemy-kill helpers (`can_kill_<enemy>`), and `savewarp: "A -> B"` (where save-and-quit puts you, needed for entrance shuffle).

## What won't carry over from N64

- **Engine data.** `scene_id`, `default` (chest/collectible/GS flags and `[room, setup, actor_index]` tuples), `n64_rom_addresses`, and `items[*].get_item_id` are all N64 ROM / actor-table identifiers. The remake stores placements in different files (`Banc/<Area>/*.bcett.byml` with per-actor `Hash`), so match by name, area and vanilla item, not by number. Pot/crate/freestanding/wonderitem/silver-rupee locations depend on the N64 actor layout, and their counts will drift if the remake moves or adds objects.
- **Glitch logic.** All 185 advanced tricks and their helpers (ISG, superslide, OI, HESS, megaflip, weirdshot, clips, equip swap, lunge storage, GDV, Door-of-Time skips, bomb hovering) exploit N64 engine bugs. Drop them.
- **Glitchless tricks.** Many of the 186 `logic_*` tricks are tied to N64 geometry or collision (jumps, ledge grabs, hover-boots routes, `logic_visible_collisions`, `logic_deku_b1_skip`, boulder/Boomerang tricks). Treat them all as "off until re-verified on the remake".
- **Master Quest.** Kept separate in `logic_mq.json`. It is only relevant if the remake ships MQ layouts.
- **OoTR-only hacks and extras.** Shop prices and `business_scrubs` text IDs, `fix_broken_drops`, `free_bombchu_drops`, ocarina-note shuffle (`has_all_notes_for_song`), enemy souls (`has_soul`), the `Gift from Sages` cutscene, `skip_child_zelda` / `skip_reward_from_rauru`, `Bonooru` and the scarecrow song (`scarecrow_behavior`), and Treasure Chest Game keys. They are randomizer features implemented by ROM patches. Port them only if the remake can be patched the same way.
- **Version-specific facts to re-check.** Day/night behaviour (`time_passes`, Dampé time, night-only GS), damage values, item-use ages (`_is_adult_item` / `_is_child_item`: OoTR assumes N64 age restrictions), and scarecrow/Epona behaviour.
