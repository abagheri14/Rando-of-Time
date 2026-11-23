# Rando of Time

Rando of Time is a randomizer for the Ocarina of Time remake. I built and playtested it on PC with the Longshot
recomp.

I wanted the most complete randomizer the remake can have. It starts from OoT Randomizer's generator and logic, then
goes further: it shuffles pretty much everything the remake lets you open, pick up, break, catch or talk to, and its
logic counts the remake's own ways to reach a check. One of my test seeds with nearly every shuffle on has **2,256
checks**.

## What sets it apart

- **Every OoT Randomizer setting is here.** All 235 of OoTR's settings, seed and cosmetic, are mapped to the remake
  in [PARITY.md](PARITY.md), and all but 42 of them take every value OoTR offers. On top of that there are 104 remake
  settings, including most of what Ship of Harkinian and the 3DS randomizer add.
- **Enemy souls and boss souls.** Turn on enemy souls and 39 enemy families (872 enemies in all) stay out of the
  world until you find their soul. Every dungeon boss waits for its own soul before you can fight it. There's a
  regional mode too, with one soul per area. Rooms that lock you in until their enemies are beaten stay open until
  you find those souls, and the logic knows exactly what each soul opens up. Bean souls and Ganon's soul are in as
  well.
- **Souls look like their enemies.** A soul isn't a generic icon. Every enemy and boss soul is a small figure of that
  enemy, posed the way the game's Hall of Fallen Foes shows it and built from its own model, materials and textures.
  You know whose soul you just picked up the moment you see it.
- **Every item looks like itself.** Pickups out in the world show the item they give. Songs are music notes in each
  song's colour, the Ocarina note items are gold buttons labelled with the button that plays the note on your
  controller, and the Master Sword gets its own standing model. Progressive items show the tier you'll get next, and
  small items are scaled up so you can actually see them.
- **You can tell what's left.** Unchecked pots and grass get a blue tint, crates and rocks can take OoTR's colours,
  and chests change size and look to match what's inside, down to the ornate chest for boss keys. Traps look like
  real items, and there are four kinds: ice, shock, fire and rupee traps.
- **Logic made for the remake.** If the remake lets you reach a check or break an object in more ways than OoTR's
  logic counts, mine counts them too. Remake-only content is in the shuffle as well: the Gerudo Fortress cow, 14
  chests OoT never had, and the objects only the remake has.
- **Every object can hold an item.** Pots, crates, beehives, grass, bushes, rocks, boulders, silver rocks, trees,
  icicles, red ice, palm fruit, fairies, silver rupees, signs, fish and more. A checked object comes back as its
  vanilla self, the way OoTR and Ship of Harkinian do it, so you never re-check something you already got.
- **Triforce Hunt with a real Triforce piece.** Each piece is a golden triangle cut from the Triforce relief in the
  Temple of Time.
- **The remake's own traps are fixed on every seed.** A randomized remake has a few ways to soft-lock or freeze, and
  players of the other remake randomizers ran into a lot of them first (thanks to them). Every seed fixes:
  - the shared trade button hiding the Cucco behind the Pocket Egg
  - a Bow or Slingshot from anywhere but a chest coming with no quiver or bullet bag
  - bombs needing the Goron Bracelet
  - Link freezing while he holds up an item the game never meant him to hold
  - the windmill man refusing to teach when you already have the Song of Storms
  - Dampe's race room only letting you out with the Hookshot
  - the Deku Tree slingshot room, the Forest Temple bow room and the Spirit Temple statue room trapping you
  - the Water Temple gate switch being walled off until the Serenade
  - Gossip Stones talking about a Mask of Truth you don't have
- **Seeds that don't break.** Every seed is beatable in logic, and the generator rerolls any seed where the remake's
  missing save warp could strand you. Before you play, every patched file gets read back and checked against the
  game: placements, scenes, text, AI files and every item Link holds up.
- **Multiworld.** An Archipelago world and client, with an in-game mailbox for items from other players. It's built
  and still being tested.
- **A real map tracker.** It reads your save, ticks off checks as you get them, shows them on the game's own maps
  and knows which ones are in logic right now.
- **One app for everything.** Pick your settings and press one button, and the seed installs as a Longshot mod you
  can take out again. It also builds seeds for Rekarina, Switch emulators and modded Switch consoles.

As far as I know, no other remake randomizer does all of this in one place.

## What gets shuffled

- **Every OoTR location type:** chests, NPC gifts, songs, boss rewards, Great Fairies, freestanding items, heart
  pieces, Gold Skulltula tokens, cows, frogs, beans, the Treasure Chest Game, minigames and the 100-Skulltula reward.
- **Shops, scrubs and merchants:** 48 shop shelves, the Business Scrubs and the carpet salesman, with OoTR's, Ship of
  Harkinian's and the 3DS randomizer's price modes.
- **Dungeon items:** small keys, boss keys, the Gerudo Fortress keys, maps, compasses and all 80 silver rupees,
  anywhere OoTR can put them. Plus every Ganon's boss key mode, and a Triforce Hunt with its own Triforce piece model.
- **Objects:** pots, crates, beehives, grass tufts, the Hyrule Field bushes, rocks, bomb boulders, silver rocks,
  trees, icicles, red ice and palm fruit.
- **Fairies:** Ship of Harkinian's five fairy shuffles, with over 160 fairy spots.
- **NPCs and extras:** the beggar, the nine Fire Temple Gorons, the Big Poes, 35 signs, the fishing pole, the
  fisherman's hat and the Gerudo Fortress cow.
- **Fishsanity:** the fishing pond and the overworld fish.
- **Souls and enemies:** enemy souls (every family or one per area), boss souls, bean souls and Ganon's soul, each
  shown as a figure of its enemy, plus an enemizer that swaps enemy types.
- **Traps:** ice, shock, fire and rupee traps, disguised as real items.
- **Equipment:** the Master Sword, the child wallet, the Deku stick and nut bags, progressive swords and the Goron
  sword.
- **Entrances:** dungeon and overworld entrances, the Gerudo Valley river, both owls, warp songs and the child spawn.

## Everything else you can change

- **Hints:** OoTR's Gossip Stone hints in all 16 languages, with OoTR's, Ship of Harkinian's and the 3DS randomizer's
  hint mixes, plus extra hints like the scrubs and the loach.
- **The world:** starting items and time of day, open forest, Kakariko and Door of Time, trials, the rainbow bridge
  and Ganon's boss key conditions, story skips and quality-of-life options.
- **Cosmetics:** shuffled music, fanfares and sound effects, tunic, gauntlet and shield colours, the HUD hearts and
  magic meter, sword, boomerang and bombchu trails, and Navi's colour.
- **Glitch logic:** the remake's own glitches as optional tricks (62 routes so far), plus a Glitched logic mode.
  Every trick is off by default.
- **OoTR's presets and settings strings** work too.

A few of the newest features haven't had a full playthrough yet. [PARITY.md](PARITY.md) marks those "not seen
in-game". What the project can't do yet, and why, is in [LIMITATIONS.md](LIMITATIONS.md).

## Playing it

1. Get Longshot running with your own copy of the game.
2. Open `RandoOfTime.exe` and choose your target (Longshot, Rekarina, a Switch emulator or a modded Switch). Pick
   your settings and press **Make the seed**. On Longshot the seed installs as a separate mod, and **Restore the
   original game** takes it out again so you play from the original files.
3. Start a new save file for every seed.
4. Run `RandoOfTimeTracker.exe` next to the game. It reads your save, marks checks as you do them and shows where
   they are on the game's maps.

The download is only the randomizer. It builds the text, maps and icons from your own copy of the game the first
time it needs them. Longshot is the only target I've playtested so far.

## How I made this

I designed Rando of Time, wrote a good amount of the code myself, and made the calls on what gets shuffled and
what the logic should allow. I tested the builds in-game myself, one after another, so when the docs or the code
say I saw something in-game, that's from my own playtesting.

I used Claude for the engineering work that could have taken me months or years by hand. That's the reverse
engineering of the remake's formats and game data, and working through the OoTR logic port, the patching code and
the audit of thousands of checks.

I also used Claude on a lot of the README and the other docs, to reformat them, spell check them, edit and clean up
the wording, and organize everything so it reads clearly.

## Credits

- [OoT Randomizer](https://github.com/OoTRandomizer/OoT-Randomizer) (MIT, in `vendor/ootr`): its generator, logic and
  hints are the core of every seed.
- Longshot and its launcher, the recomp the game runs on.
- [OotrR](https://github.com/Mozencaz/OotrR) by Mozencaz (MIT): the Archipelago client's connection and live-memory
  code started as a port of theirs (`tools/archipelago/client`, licence included there).
- Ship of Harkinian and the OoT 3DS randomizer, whose settings I matched where the remake allows.
- The other remake randomizers (OOTRR, Kaepora, Clawshot, Barajador de Hyrule, NX2-ZOOTR and more): their players'
  in-game findings saved me a lot of guessing. From the GPL ones I took facts only, no code.

## License

Rando of Time is under the [MIT License](LICENSE), so do whatever you want with it. Fork it, send changes back, take
code for your own projects, build a better randomizer on top of it. The only thing the licence asks is that you keep
its notice with any copy of the code.

The parts that came from other projects keep their own licences, and both of those are MIT too: OoT Randomizer in
`vendor/ootr` and the OotrR-based client code in `tools/archipelago/client`.

Ocarina of Time and everything in it belong to Nintendo. This project isn't affiliated with Nintendo, and it has no
game files in it. You need your own copy of the game.

## The toolkit

The tools below read and change the rewards in the remake as it runs under Longshot, and they map OoT Randomizer's
logic onto the remake's checks. The project ships the tools only. Any unpatched game files from your own dump go in
the local `original/` folder, and both the patch builder and the restore command use those copies.

Run the commands from the project folder. `ROMFS` means the game's `romfs` folder, for example
`E:/LongshotLauncher-data/builds/stable/v3.1.1/romfs`. If `REMAKE_ROMFS` is set the tools use it, and the app sets
it for each step. If it isn't set, `romtools.longshot_romfs` finds Longshot's default build from `builds.json`, the
same way the app does. So a Longshot update that renames the build folder doesn't need a path change here.

Players don't need any of this, because the app (`RandoOfTime.exe`) runs all these steps for them. To build the
portable release, run `release/build.ps1` and `tracker/build.ps1`, then `python tools/release/build_release.py`.
`python tools/release/make_icons.py` draws the icons.

## Workflow

1. Build the catalog (once, and again after any game update):
   `python tools/catalog.py ROMFS data`
2. Find what you want to change with `python tools/find.py Ocarina_Fairy`, or open `data/rewards.csv`.
3. Fill in `new_item` in a copy of `data/rewards.csv`, or write a JSON plan (see below).
4. Build: `python tools/make_patch.py ROMFS out/mypatch my_rewards.csv`
5. Install with Longshot closed: `python tools/install.py install ROMFS out/mypatch`.
   It puts back the previous patch's files first. Undo it with `python tools/install.py restore ROMFS`, and see
   what's installed with `python tools/install.py status ROMFS`.
   Longshot also serves its own copy of each language's text (`<game folder>/texts/`), built from whatever text was
   installed the last time Longshot was built. So install rewrites those copies from the patch's text plus
   Longshot's own PC changes (`data/longshot_pc_text.json`), otherwise you'd keep seeing an older patch's text. It
   also makes their size-table entries fit, because text entries that are too small crash the game at boot.
   To check that it boots, run `powershell tools/boot_test.ps1`. It prints PASS or CRASH, and it starts the game,
   so save first.
6. After a game or Longshot update, run `python tools/selftest.py ROMFS`.

**Always install with `tools/install.py` for the workflow above.** Longshot serves its resource size table from
`<game folder>/prompts/rsizetable.zs`, and the entries for its PC button icons are already raised there. A file
bigger than its entry fails to load. I once had the small-chest scene go 18 KB over its entry, and none of the small
chests opened. Two earlier builds that grew scene files most likely hit the same problem.

The patcher lists the files that outgrow their entries. The installer applies the same increases to Longshot's copy
of the table, saves the original in `original/_longshot` and puts it back on restore. Longshot's mod loader can also
merge the mod's own table if you configure it with `HOS_MODS`.

The patcher checks item names against the game's actor list and suggests a match if you make a typo.

## Seed generator (`tools/rando/`)

Seeds use OoT Randomizer's logic, item pool and fill, so every seed is beatable. The same generator writes the
playthrough, hints and spoiler log. The copy in `vendor/ootr/` is pinned, MIT and unmodified, see
[`SOURCE.md`](vendor/ootr/SOURCE.md).

    python tools/rando/generate.py out/myseed --seed 1234
    python tools/make_patch.py ROMFS out/myseed/patch out/myseed/plan.json
    python tools/install.py install ROMFS out/myseed/patch

- `config/rando_settings.json` holds the OoTR settings that describe the remake's world as we patch it. The forest
  and the Door of Time are vanilla (`open_door_of_time: stones_oot_sot`), dungeon keys are vanilla, maps and
  compasses are removed, and it has `free_bombchu_drops: false` because remake bombchus share the bomb bag's capacity.
  The generator checks them with OoTR's own `validate_settings`. Tricks are in `config/tricks.json`, all off. A
  settings file can name a `"base"` file and override only some settings.
- **OoTR parity.** `PARITY.md` has every OoTR setting, its plugin and what works, and
  `tools/rando/parity_report.py` writes it from OoTR's settings list and our code. Each feature area plugs into the
  generator without touching it. It's a `tools/rando/parity/<area>.py` module with `OWNS` (its settings and values),
  `check_settings`, `keep_locations`, `before_fill`, `after_fill`, `world_plan` and `item_for` (see
  `generate.plugins()`). The remake's logic for that area goes in `data/rando/logic/<area>.json`, with rule changes,
  new regions and new OoTR locations (see `world_settings.logic_overrides()`). The generator refuses settings that no
  code supports, and it refuses a seed where OoTR put an item somewhere the patcher can't write.
- **Which plugins run.** `config/plugins.json` lists the reviewed plugins. Unfinished plugins and their logic files
  never get into a seed, though `RANDO_PLUGINS=+name` (or `all`) adds others for a test run. Every `remake_*` setting
  has to be declared by an enabled plugin, in `REMAKE_SETTINGS`, `REMAKE_DEFAULTS` or `REMAKE_KEYS`. If you misspell
  one, or its plugin is off, it's refused with the closest known name (`generate.unknown_remake_settings`).
  Game files are always read as vanilla through `original/`. If the install record (`installed.json`) lists a file
  as patched and there's no original copy of it there, the tools stop rather than read the installed patch as the
  original game (`romtools.Romfs`).
  OoTR's last junk pass is made to respect item rules (`install_rule_fill`). The generator runs with
  `PYTHONHASHSEED=0` so a seed always comes out as the same game, and `RANDO_DEBUG=1` prints why each failed attempt
  failed.
- **No vanilla spots by chance** (`tools/rando/no_vanilla.py`). Nothing keeps its own vanilla item unless a setting
  locks it there. It's the remake setting `remake_avoid_vanilla_spots`, on by default, and `false` leaves OoTR's fill
  exactly as it is.
  - Dungeon-confined items (keys, maps, compasses and boss keys in their own dungeon, hideout keys in the fortress)
    refuse their own vanilla spot during OoTR's fill. If the fill finds no spot for an item, that item drops the
    rule, and after 10 failed attempts every item does.
  - Everything else that lands on its own vanilla spot swaps with another location after the fill. Both locations
    have to take the other's item under every rule, and a swap that involves progression has to keep the seed
    beatable with every location still reachable. Shop-only slots only swap with each other, and then OoTR's shop
    rules are set again for both slots. Items compare by look, so any bombs are bombs and any bottle is a bottle.
    Shop items compare by exact name.
  - Heart spots also refuse any heart (drops plugin), since a heart there looks vanilla.
  - Two more rules, always on, stop a drop spot from playing as vanilla under another item's name. OoTR's "Nothing"
    only goes to objects whose own drop is OoTR's "Nothing" too. The patcher leaves the object as it is, so on a
    fixed drop or a Skulltula it gave the vanilla rupees or token, and that was 95 spots on one early test seed. And
    an ice trap's stand-in pickup is never the spot's own pickup (34 green rupees or hearts there).
  - `seed.json` "vanilla_spots" counts the swaps and lists every spot that's still vanilla, with the reason. It
    judges what a spot gives in the game. A plugin's `in_game(world, loc)` answers for its own spots, so another item
    that plays exactly like the vanilla spot gets listed too (`"hidden": true`).
    `python tools/rando/in_game_check.py OUT_DIR` reads a built seed back the same way, on its own.
- **Spots that could only give their own kind** (drops plugin). These are
  remake settings, and each list of values has the old value first and the default last.
  - `remake_empty_object_contents` (`vanilla`/`nothing`/`junk`/`ice_trap`) is what OoTR's "Nothing" gives in an
    empty pot, crate, grass tuft, rock, boulder, palm fruit or decoration. `nothing` is OoTR's behaviour, where the
    object gets the empty drop table "None". `junk` gives a rupee. `ice_trap` gives a disguised ice trap: the object
    drops `Obj_GerudoValley_Heart_Piece`, which shows a random item from OoTR's ice-trap look pool (see "Item looks"
    below). When you take it, the get scene removes it and plays the ice trap, like every ice trap does (see "Ice
    traps"). "Nothing" at a chest, NPC, scrub or shop follows the same setting and becomes a real Ice Trap or a named
    junk item, so the spoiler always names what the game gives.
  - `remake_drop_ice_traps` (`classic`/`disguised`) turns OoTR's ice traps in drop spots into that disguised trap.
  - `remake_touch_pickups` (`own_kind`/`any`) turns the Zora's Fountain and Dampe's-race green rupees and the Deku
    Tree and Fire Temple recovery hearts into the heart piece or heart container their stage places, so they give any
    item through the get scene.
  - `remake_freestanding_keys` (`vanilla`/`any`) lets the Bottom of the Well and Shadow Temple freestanding keys give
    any item. The Bool in their room logic saves them.
  - Bug sources: OoTR's bug locations only count the sources we can prove in the remake, which are unshuffled bug
    grass, bug rocks and Hyrule Field bushes.
  - There are two spots where no pickup can carry the item, so each of them gets a scene of its own.
    GC Pot Freestanding PoH comes from the spinning pot's heart-piece scene
    (`remake_gc_pot_prize`: vanilla | any, default any), and the pot's own save flag `GoronLargePot_IsGetHeartPiece`
    keeps it once-only. ZD Storms Grotto Blue Rupee 1-6 come the first time you enter the grotto
    (`remake_zd_grotto_rupees`: vanilla | gift, default gift, scene ID ShadowTemple_GetMap). The first item is held
    up, the others come in the get window, and the rupees are deleted.
  - Every scene row has its own `HavePlayedEvent.<row>` flag, which the engine sets after the scene plays. So reusing
    a row gets you a free once-only flag.
- **Ice traps.** Every kind works the same way: chests, NPC and scene gifts, shops, scrubs, heart spots and disguised
  drops. The shared freeze scene (`parity/_chests_scenes.freeze_graph`) creates the ice-trap attacker and shows
  OoTR's "You are a FOOL!" in a system text box, with FOOL in the game's highlight (`fool_ops`).
  - The attacker is `ConditionSensorActor`, the base actor of the song sensors, which the game never creates. We
    give it the attack of the remake's ice-trap chest (`drops.ice_sensor_ops`): its sensor, SensorHit and
    AttackParam, half a heart, ice. It also gets an actor-table row with an instance heap, since it had none.
  - `GameSystemActor.EventTriggerRequestCreateConditionSensor` creates it 1 m above Link. It stays on him, plays the
    chest's freeze breath, waits until no main event is playing, then attacks for 90 frames. I've seen it work
    in-game.
  - Every chest type runs a trap. Story and minigame chests do it through their own scene (Mido's house, the
    Treasure Chest Game, Dampe's race, the Ice Cavern, Jabu-Jabu, and the Water and Spirit Temple story chests).
  - With `remake_trap_weights` every path plays the kind it drew. Shock and fire are the same freeze with an attacker
    of their element (Link's own shock or burning), and the rupee trap takes 10 rupees. That's in
    `parity/_chests_scenes.py`, and `parity/_chests_traps.py` reads it back.
- **Ammo without its container adds nothing**, like in OoTR (`parity/_ammo.py`, every seed). Bombs need a Bomb Bag,
  arrows need a Bow and Deku Seeds need a Slingshot. Otherwise the remake's pouch gives you the container itself, and
  a "Bombs (5)" chest gave a full Bomb Bag. So we guard the three pouch-add steps that every non-shop give goes
  through. The item still shows, but the add is skipped. Shop bundles are left alone, because a sale mustn't take
  your rupees for nothing.
- **Chests plugin** (`parity/chests.py`). It does ice traps in all `junk_ice_traps`
  modes, where the chest plays its own opening and then the ice trap above. The six real trap chests stay traps or
  become plain small chests holding an item. It also does the Treasure Chest Game's prize, Dampe's race heart-piece
  chest, and 14 remake-only chests that we add as new OoTR locations (`data/rando/logic/chests.json`).
- **Entrances plugin** (`parity/entrances.py`). It shuffles dungeon and overworld
  entrances, the Gerudo Valley river, both owls, warp songs and the child spawn, by retargeting the remake's level
  doorways (`FieldAndDungeonEntranceEventRequestActor`) and scene level changes. In the remake, interiors, grottos,
  graves, the hideout, boss rooms and Ganon's Tower are part of the level around them and have no level change, so
  those settings stay off for now. Starting as an adult isn't done yet.
- **Cosmetics plugin** (`parity/cosmetics.py`).
  - Sound: music, fanfares and battle music, 19 sound effects, Link's voices and the ocarina sound. The sound links
    are in `SLink2`. A shuffled track plays whole and loops on its own loop points, because the music graph's segment
    nodes lose their fixed length (`_cosmetics_bgm.py`). Fanfares are one pool, like in OoTR and Ship of Harkinian.
    `remake_shuffle_all_sfx` shuffles every sound effect within its own archive and kind.
  - The Kokiri tunic colour covers every tunic texture, child and adult: the plaid, both vests, the cloth parts and
    the trims. Only the green in each one gets recoloured, in place, at its own brightness against the shirt. ASTC
    textures are recoloured block by block by rewriting their end colours (`parity/_astc.py`). Mido and a few Kokiri
    props share the plaid.
  - Also the Goron and Zora tunics, both gauntlets, the mirror shield frame, the HUD hearts and magic meter
    (`_cosmetics_hud.py`), the sword, boomerang and bombchu trails and Navi's glow (particle effects,
    `_cosmetics_vfx.py`), the default targeting mode and the credits music.
  - Plans carry a "cosmetics" section that `make_patch.py` writes itself. `_cosmetics_render.py` turns any game
    texture into a PNG.
- **Story plugin** (`parity/story.py`). It covers the bridge and Light Arrow cutscene
  conditions (stones, medallions, rewards, tokens or hearts, counted from the save data the way OoTR counts items),
  every Door of Time mode, Zora's Fountain (closed, adult, open), Gerudo Fortress (normal, fast, open), skipping
  child Zelda and Rauru's reward, the mask quest, starting time of day, no escape sequence, no guard stealth, fast
  scarecrow, fast Shadow boat and the damage multiplier. When a setting skips story steps, whatever sets the older
  steps is guarded, since remake story steps can move backwards. Dampe's race chests are OoTR disabled locations
  (junk only), because the race only counts a finish while the Hookshot is in the pouch.
- **Closed OoTR gameplay gaps.** These are No Logic, `trials_random`, every Ganon's boss-key mode, Zora's
  Fountain 'fast', night Skulltulas at day, the Spirit Temple Deku Shield pot, the Treasure Chest Game's keyed modes
  (a saved key count), the password lock, Triforce Hunt, every silver-rupee value and the pouches, the easier Fire
  Arrow entry (the game's own bool counter), blue fire arrows (red ice, and 4 of Dodongo's Cavern's breakables),
  Dampe's one-race prizes, Epona without the race, Ruto on Jabu-Jabu's top floor, and two experiments, the fast
  Bunny Hood (AS rate) and deadly bonks (a life write when the roll hits a wall).
  - For Ganon's boss key, the conditions open Ganon's Tower's boss lock through its AI (`_dungeons_ganon.py`).
  - A Triforce piece shows one golden triangle cut from the Temple of Time's Triforce relief, held like the Light
    Medallion.
  - Epona without the race is stricter than OoTR, with one ranch visit.
  - `auto_equip_masks`: the remake already keeps masks, which is OoTR's True. Its False is my call.
  - OoTR's 'advanced' logic (N64 glitch logic, its files aren't vendored) loads as the remake's Glitched logic,
    `remake_glitched` (see the remake glitch tricks below).
  - On every seed, Dampe's race doesn't undo the Forest Temple.
  - The story plugin loads all of these as self-contained modules. `GAPS_MODULES` in `parity/story.py` lists the
    `_gaps_*.py` files, each with OWNS, world_plan, UNTESTED and READERS. Their read-backs run in `in_game_check`
    through `parity/_gaps_check.py`. `make_patch`'s gamedata op also adds saved Ints (`add_ints`), and several ops can
    each add rows. None of it has been seen in-game yet.
- **Scene-call rewards.** If a scene location's reward is `{"item": ..., "call": "File:Entry"}`, its give steps get
  replaced with a call to a shared scene, like an ice trap's freeze or a dungeon item credited to its dungeon
  (`make_patch.scene_call_ops`).
- **Default-deny.** A seed setting that no code handles has to stay at OoTR's default (`world_settings.unhandled`).
  Settings whose OoTR default isn't what the remake does are pinned (`REMAKE_ONLY`, `SUPPORTED`).
- **Choosing settings.** Use `--settings FILE` with OoTR setting names (a file can name a `"base"` file),
  `--preset NAME` for OoTR's presets (`vendor/ootr/data/presets_default.json`), or `--settings-string STRING` for
  OoTR's settings strings. The remake's own settings also take familiar names, so instead of the `remake_*` key or
  the OoTR value you can use the Ship of Harkinian (or OoT3D Randomizer) setting with its option strings. For example
  `"shuffle_grass": "Overworld"`, `"shuffle_rocks": true`, `"mysterious_shuffled_items": false` or
  `"containers_match_contents": true`. The table is `config/setting_aliases.json`, and `generate.py apply_aliases`
  applies it. `PARITY.md` lists every setting with its familiar name.
- **Shops plugin** (`parity/shops.py`, pairing in `tools/rando/shops.py`). It does shopsanity, shuffle_scrubs with
  OoTR's always-shuffled upgrade scrubs, and the carpet salesman. Shopsanity covers 48 shelves in the Kokiri, Goron,
  Zora, Bombchu and both bazaar shops, and the two potion shops share one list unless they're split (see below).
  Shelves only sell items that have a shop version (shields, tunics, ammo, hearts). Scrubs and the carpet salesman
  sell anything that has a remake item.
  - `remake_split_potion_shops` (default: `remake_avoid_vanilla_spots`) gives the Kakariko potion keeper its own list
    file through a "packs" op with `"new_from"`, so both potion shops get shuffled.
  - `remake_shuffle_bowling_bombchus` (same default) shuffles the bowling's first prize, and the keeper announces the
    seed's prizes in every language.
  - `remake_shop_shields_tunics_after_found` (off, from Ship of Harkinian) only sells shop shields and tunics once
    you've found one.
  - Blue Fire from either potion keeper is only in logic once you've had Blue Fire, because the game won't sell it
    before that.
- **Silver rupees** (`remake_silver_rupee_items`, default: `remake_avoid_vanilla_spots`). It's in the dungeons
  plugin's `_dungeons_silver.py`. With OoTR's
  `shuffle_silver_rupees` at `vanilla`, each of the 80 silver rupees still counts for its room and also gives a seed
  item, held at `<puzzle> Silver Rupee Spot n`.
  - OoTR's other values and the pouches are in `_dungeons_silver_shuffle.py`.
    Each puzzle's count is a new saved Int. Its counter (the barrier)
    leaves on a Presence at 5, and the get scene sets the room's done flags. The silver rupees and pouches are dungeon
    items, credited through the dungeons plugin's scenes. The room's own tokens are OoTR's 80 locations and open
    nothing. 'remove' starts every count at 5. Not seen in-game yet.
  - Dungeon logic: the Fire Temple boss-key loop uses OoTR's rule, since its door starts open with vanilla or
    dungeon keys. The Water Temple's first door needs 3 keys. With keys in their own dungeon, the layout can still
    force the Water Temple, the Forest Temple's first room and one Fire Temple chest to keep a key.
- **Extras from Ship of Harkinian and the 3DS randomizer.** Each one is a remake setting, off by default, and with
  all of them off a seed comes out byte-identical.
  - `parity/extras_story.py` has `remake_sleeping_waterfall` (open),
    `remake_skip_four_poes`, `remake_skip_lake_owl`, `remake_jabu_mouth` (open), `remake_medallion_trials` (each
    trial's barrier-room door needs its medallion), `remake_ganons_soul` (stones/medallions/dungeons/tokens/hearts,
    with `remake_ganons_soul_count`), `remake_king_zora_speed` (fast) and `remake_racing`.
  - `parity/extras_items.py` has `remake_progressive_goron_sword` (Giant's
    Knife, then Biggoron Sword), `remake_progressive_swords` (Kokiri Sword, Master Sword, Giant's Knife, Biggoron
    Sword, and it needs `remake_shuffle_master_sword`), `remake_gk_durability`, `remake_remove_double_defense`,
    `remake_shuffle_deku_stick_bag` / `_deku_nut_bag` and `remake_shuffle_child_wallet`. With that last one you have
    no wallet on a new file, and every fee needs one in logic. The chests plugin's `remake_trap_weights` adds shock,
    fire and rupee traps.
  - `parity/extras_npcs.py` has `remake_shuffle_beggar` (6),
    `remake_shuffle_fire_gorons` (9), `remake_shuffle_fishermans_hat`, `remake_shuffle_fishing_pole`,
    `remake_shuffle_big_poes` (10, given when you bottle each soul) and `remake_shuffle_signs` (35 spots, each with
    its own scene row). The hints plugin's `remake_extra_hints` adds the static NPC hints in every language.
  - Fishsanity is in `parity/extras_npcs.py` too, and works like Ship of Harkinian's.
    The settings are `remake_fishsanity` (off / pond / overworld / both),
    `remake_fishsanity_pond_count` (0-17) and `remake_fishsanity_age_split`, also under SoH's names `fishsanity`
    ("Shuffle Fishing Pond"...), `fishsanity_pond_count` and `fishsanity_age_split`.
    In the pond, every catch ends in `MiniGame_Fishing:Step01_CatchFish_Child` / `_Adult`, and those hand over the
    first unclaimed check on the age's list (the child list for both ages without the split), like SoH does for
    counts 1-16. Count 17 uses the same order, since no pond fish has an identity of its own.
    In the overworld, the five fish in the child Zora's Domain layout get placement Names, and the pouch event AI
    (`AI/PouchContent.event.root.ainb`) answers the tag query for them. The bottle scene asks the caught actor's tag
    after its attention step and keeps the fish number in `SimpleShop_Price`. Both catch endings then give that
    fish's item once, before the Big Poe checks.
    SoH's nine grotto fish don't exist here, because the remake's grottos have no fish. SoH's "Shuffle only Hyrule
    Loach" is OoTR's `shuffle_loach_reward`. Fishsanity claims 38 flags in `data/rando/extras_npcs.json`, and
    `in_game_check` reads it back (`extras_npcs.verify_fish`). Not tested
    in-game yet.
  - `parity/enemizer.py` (`remake_enemizer`) swaps enemy types, but only among the ones their level already places.
    An enemy that a room or module watches only takes a twin with the same weapons. With enemy souls on, a swapped
    enemy takes its new family's soul and the logic knows it. A Poe it places has no soul, so it's always there.
    The enemizer's `remake_enemizer_vanilla` keeps the listed enemy types out of the swap (OoT3DR's per-enemy
    "Vanilla").
  - `parity/gs_positions.py` (`remake_gs_positions`) moves 13 Gold Skulltulas to grass tufts in their own level, with
    logic per spot.
  - `parity/extras_prices.py` has SoH's and OoT3DR's price modes for
    shop special deals, Business Scrubs and merchants. The settings are `remake_shop_prices` / `remake_scrub_prices` /
    `remake_merchant_prices` (SoH's names `shopsanity_prices`, `scrubs_prices`, `merchant_prices`...). The modes are
    vanilla, cheap_balanced, balanced, fixed, range, wallet weights, affordable and child / adult / giant wallet caps,
    with their fixed price, range, weights and affordable switch. Prices go from 0 to 500, since there's no tycoon's
    wallet.
  - `parity/extras_pool.py` has `remake_links_pocket` / `_reward` (Rauru's reward),
    `remake_vanilla_songs`, `remake_vanilla_freestanding_rupees` / `_hearts`, `remake_wonderitems_area` and
    `remake_vanilla_items` (OoT3DR's Vanilla logic).
  - `parity/extras_hints.py` has `remake_scrub_text_hint`, `remake_loach_hint`
    and `remake_hint_distribution`. That last one gives SoH's and OoT3DR's Gossip Stone mixes, and OoT3DR's
    Playthrough with `remake_hint_specificity` and `remake_bonus_gossip_hints`.
  - `parity/extras_qol.py` has `remake_skip_talon`, `remake_early_grannys_shop`,
    `remake_full_wallets`, `remake_frog_song_timer`, `remake_skip_song_replays`, `remake_slingshot_beehives` and
    `remake_damage_multiplier` (x8, x16).
  - `parity/extras_souls.py` has `remake_shuffle_boss_souls`,
    `remake_shuffle_bean_souls`, `remake_shuffle_ganons_soul` (Ganon's Soul as an item) and `remake_skeleton_key`.
    The souls are only given at core scene locations.
  - Entrance extras (decoupled and mixed pools) aren't done yet.
- **Respawn model** (`tools/rando/drops.py` CHECKED_ARRAY). This is how OoTR and Ship of Harkinian do it, and it's
  what I wanted. A shuffled pot, crate, grass tuft, rock, beehive, icicle or palm fruit respawns like in vanilla
  and drops its item every time, until you take the item. From the next load on, its vanilla twin stands there
  instead, with the vanilla drop, no blue marker and vanilla respawning. Breaks save like in vanilla, so a broken pot
  stays broken for the visit.
  - **Checked record.** A new saved bool array, `RandoChecked`, with one bit per location. The save list can grow.
    `make_patch.gamedata_layout` reproduces the vanilla MetaData exactly and recomputes it for the new rows, and
    that's proven in-game: old saves load, and new ones save and reload.
  - **Bit hand-over.** The placement names its bit in `Drop__RandoChk`, an S32 instance parameter of the Drop table.
    Its root AI hands the bit to the drop as `RandoChk` (`QueryBlackboardOverwriteParamAddS32`). When you take the
    pickup, it sets `RandoChecked[bit]` with `OneShotSetNonStructGameDataBool` (`GameDataIndex` = the bit), as the
    first child of the branch that saves and signals death. The heart-piece carrier and the Gold Skulltula token's
    own `Item_Token_Gold.root` do the same. A drop that can't do that (an enemy, ammo) sets it on break instead
    (`Drop__RandoSaveOnBreak`). Every table those AIs read has the keys, whether or not this seed drops that type, and
    the array exists whenever a setter does.
  - **AI input shapes.** In the game's files, an input fed by a node has flags 0, and one that holds its own value
    has 0x800000 or 0x1800000 (never 0). `tools/ainb.py` keeps to that in `feed`, `link`, `set_input` and copies, and
    make_patch refuses an edited AI file that doesn't (`Ainb.input_shape_problems`). We once had a setter with a fed
    index still flagged as a constant.
  - **Swap.** The placement gets a lazy negated `Presence` on an expression flag of its own, `RandoChk_NNNN` (BoolExp
    opcode 8, one array element). Its twin is a copy of the vanilla placement under `hash ^ 2` with the positive
    Presence. That row gets the object's own reset type and area, and icicles get a new row. Objects that are
    permanent in vanilla (bomb boulders, red ice, silver rocks) get an area reset instead and no twin. Flying pots and
    Gerudo cow skulls keep the old "gone once taken" behaviour.
  - **What a twin can't replace.** Some objects keep the old model (`drops._inbound_refs`, about 200 objects in one of
    my test builds). Those are objects another actor links to (palm trees' fruit, red ice holding pots,
    Obj_BrokenBox_A_06's respawn-sync crates, two NPC/event links), and objects a room's logic module references,
    since AiGroups find actors by name (Ice Cavern, Bottom of the Well, Ganon's Castle rooms...). A twin takes its
    source's place in `FarDeleteGroups` / `SimultaneousGroups`. A reset-group member's twin joins the group through
    the reset actor's link and every GmdReset copy (`drops.group_join_ops`), so the vanilla pot refills with the room
    (`verify_group_twins`).
  - **Baked collision.** OotrR hit this in their issue #37, a tree's copy with no collision. Crates and the Hyrule
    Field bushes are the only twinned types with baked collision. It lives in the area's `Phive/StaticCompoundBody`
    and is found by placement ID, and each placement's `Phive.Placement.ID` is its hash. So their twins (29 crates,
    26 bushes) keep their source's ID (`drops.BAKED_TYPES`, make_patch `keep_phive_id`), and the pair is never there
    at the same time. Pots, grass and the other twinned types have no baked shapes and get a new ID.
    `python tools/phive_static.py --check` compares the list with the game data. Not tested in-game yet: whether two
    placements sharing an ID load fine, since vanilla never does that.
  - **Can a checked original come back?** No. Its Presence reads a `RandoChecked` bit, and only a new file clears
    that. A broken original whose item is still lying there (an item that saves on pickup) keeps a true lazy
    Presence. OotrR saw breakables like that come back "almost at once" after a camera turn (their #36). We haven't
    tested that here.
  - `in_game_check` reads all of it back (`drops.verify_respawn`, `verify_pickup_save`).
- **Logic corrections from the region reviews.**
  - 122 object regions and rules (`drops_regions_*.json`) and 57 dungeon rules (`logic/audit_dungeons.json`).
  - Remake helpers (`drops.REMAKE_HELPERS`): Deku Sticks cut no grass or bush, beehives break with arrows and Din's
    Fire, and kills for Armos, Biri, Bari and Flare Dancer.
  - No bottled fairy from gossip stones or bean plants, bronze boulders are hammer-only, and Gerudo decorations need
    the Bow or Hookshot.
  - The two adult layouts (`drops.ALT_LAYOUTS`) are Kakariko after the fire and the thawed Zora's Domain. Objects that
    are only in the later layout need its bosses, and objects only in the earlier one keep their vanilla item.
  - Loosenings below high confidence wait for an in-game check.
  - The two Goron City Lost Woods boulders are locations (Goron City Boulder 20 / 21).
  - An object of one age in a region that age never reaches isn't a location (`drops.AGE_NEVER`, noted as
    `not_a_location` in drop_map "extras"). That's the child copies of GV Fortress Side Rock 2/4/6 and GV Storms
    Grotto Pot 2/3/6/8, because a Gerudo guard sends a child back at the bridge. The adult copies at the same spots
    stay locations. The tracker logic server's `--validate` found these, since they're never available even with
    every item.
- **Tracker** (`tracker/dist/RandoOfTimeTracker.exe`, sources in `tracker/app/*.cs`). `tracker/build.ps1` builds it
  with the .NET Framework compiler that every Windows PC has. It shows the game's own map art and icons, decoded from
  your game by `tools/tracker/build_data.py assets`, with every check of the seed at its spot, your items, places with
  done/total, and a live log. It tracks automatically from the save (`progress.sav`: placement flags, `RandoChecked`
  bits and pouch counts) and from Longshot's log (current map, hearts, Skulltulas). `generate.py` writes a
  spoiler-free `tracker.json` for each seed. Opening the spoiler marks that seed and save as spoiled. `--save DIR` /
  `--log FILE` set where it reads, and the app passes the ones for the chosen game: Longshot's `user/save` and its
  log, or Rekarina's `profile/save`.
- **Randomizer app** (`release/dist/RandoOfTime.exe`, source in `release/app/Randomizer.cs`, built by
  `release/build.ps1`). It's a WinForms window in the remake's colours.
  - It has every setting the remake can make, in OoTR's tabs and sections with OoTR's labels and explanations. The
    remake's own settings sit among them, each one next to the OoTR setting that OoTR or Ship of Harkinian lists it
    with (`tools/release/remake_ui.py`). So grass, rocks and the other objects come after Shuffle Beehives, Ganon's
    Soul after Ganon's Boss Key, and so on. The one with no such home (Racing) ends the Other tab. Settings that
    another one turns off are greyed out, following OoTR's rules.
  - It makes the seed (generate, patch, cosmetics, both checks) and puts it where you play: Longshot
    (`tools/install.py`), Rekarina (`<game>\mods\OoT Remake Randomizer\romfs`, Rekarina's mods folder) or a LayeredFS
    folder for emulators and consoles (`atmosphere\contents\0400486024DEC000\romfs`). Then it opens the tracker,
    which builds its maps from your own game the first time.
  - "Restore the original game" takes the seed back out of wherever it went. On Longshot that puts the original
    files back (`tools/install.py restore`). In a mod folder it removes the seed's files, going by its
    `randomizer_files.txt` list, so other mods stay.
  - Settings files load through `tools/release/resolve_settings.py`, which handles base chains and familiar names,
    and they keep their list order. The app only writes what differs from each setting's default. That's the base
    file's value, or else the generator's own, which for remake settings without `REMAKE_DEFAULTS` is
    `remake_ui.DEFAULTS`. The export refuses a setting with no default at all. So a setting you leave alone behaves
    the same as without the app, and the same settings make the same seed. We checked that, and one of my test plans
    run through the app gives exactly the spoiler it gave without it. `--export-settings IN OUT` writes what the app
    would use. `generate.py` also sorts the settings before using them, so a file's key order can't change a seed.
    Each seed's log is `out/seed_N/app.log`.
  - `tools/release/export_schema.py` writes `release/data/settings_schema.json` with the OoTR settings that the
    plugins or `world_settings` accept. Each value is tried against `generate.settings_problems` on top of the
    defaults, with whatever parent value turns it on. That way the app never offers something a seed would refuse,
    so there's no Master Quest, empty dungeons, dungeon shortcuts, Ganon's boss key on medallions/stones/... or
    unmodeled glitch tricks.
  - When another setting turns one off, `generate.make_settings` gives it its disabled default, like OoTR's GUI
    does, so a file's triforce hunt doesn't clash with the base file's Ganon's boss key. It also honours a file's
    `allowed_tricks`.
  - **Rekarina** (from reading its loader, `setup/<ver>/runtime/mods.c` and `romfs.c`). A player mod's file beats
    Rekarina's own `romfs-patches*` for the same path. At start Rekarina rebuilds the resource size table, merging
    in the tables that mods ship and raising their files' entries, so the seed's size table is fine there. Known gap:
    the seed's 16 text files (`Mals/*`) replace the ones in Rekarina's optional fast-text set, so with fast text on,
    the text plays at normal speed. Merging our changed messages over its files would keep both.
  - **Progress bar.** While a seed is being made, the "Make the seed" button fills with gold
    ("Making the seed · 42%") and the log header shows a bar and the time so far. Each step is weighted by how long
    it took last time on that PC (`StepSeconds` in `%APPDATA%\RemakeRandomizer\app.json`). `generate.py` and
    `make_patch.py` report how far along they are with "@progress F" lines on stdout (`tools/progress.py`), but only
    with `REMAKE_PROGRESS=1`, which the app sets. The other steps go by the clock. Cosmetics are written once, by
    `make_patch.py`, and the app only runs `_cosmetics_apply.py --check`.
  - Self-test: `RandoOfTime.exe --selftest DIR SEED --load SETTINGS` does a LayeredFS export to DIR and logs to
    `DIR/selftest.log`. `--frames FRAMEDIR` keeps the window up and saves it every 1.5 s, and `--scroll left:N`
    scrolls the left column. `--screenshot FILE [TAB]` renders the window.
  - Targets: Longshot (install), Rekarina (`<game>\mods\Rando of Time`, which needs Rekarina.exe there and is refused
    while it runs), a Switch SD card and an emulator's mod folder for the game (`<folder>\Rando of Time\romfs`). The
    SD card folder (`atmosphere\contents\0400486024DEC000\romfs`) is shared with other mods, so only the files the
    previous seed wrote, listed in `randomizer_files.txt`, get replaced. A seed is built in `out\seed_N.new` and only
    replaces `out\seed_N` once it fully succeeded. The settings in use are kept in
    `%APPDATA%\RemakeRandomizer\last_settings.json`.
  - **Install state next to the game** (`REMAKE_ORIGINAL`, read by `romtools.Romfs`, `install.py`, `make_patch.py`
    and `_cosmetics_apply.py`). For Longshot it's `<game folder>\rando-of-time\original`, with `installed.json` beside
    it, so a new copy of the randomizer finds what an older one installed. The `remake-rando` folder from before the
    rename still gets used when it's there. For dumps there's one store per game copy under
    `%LOCALAPPDATA%\RemakeRandomizer\originals`. A setup that installed from the randomizer's own `original\` keeps
    it. `data/vanilla_sha256.json` (hashes only, from `tools/release/vanilla_hashes.py`) makes `Romfs` refuse a live
    file that isn't vanilla when there's no original copy of it. That catches a game folder that already has another
    seed or mod in it, or another game version.
  - **First run** (`tools/release/first_run.py ROMFS`, which the app runs before the first seed). It builds what the
    release doesn't ship from your game: the hint text (`hints_messages.json`, `hints_extra.json`) and the tracker's
    check list (`tracker/research/checks_proto.json`, which `tracker.json` needs). Built this way, the two text files
    match the ones we'd been using byte for byte. The rebuilt check list also picked up the Goron City boulders that
    the old, stale one was missing. `install.py derive_pc_text` works out Longshot's PC wording from its own text
    copies (LayoutMsg only), and the result equals `data/longshot_pc_text.json`.
- **Release.** `tools/release/build_release.py` builds `release/Rando-of-Time/` and its zip, about 35 MB. It has the
  app, the tracker, the tools and data, OoTR (MIT) and a Python of its own. That's this machine's Python with only
  the standard library, numpy and Pillow, run with `PYTHONNOUSERSITE` and without `PYTHONPATH`. Nothing from the game
  goes in: no `original/`, no tracker maps or icons, no seeds.
- **Drops plugin** (`parity/drops.py`, pairing in `tools/rando/drops.py`). It shuffles Gold Skulltula tokens,
  freestanding items, pots and crates (tokensanity, shuffle_freestanding_items, shuffle_pots, shuffle_crates), plus
  the remake's own grass, rocks, boulders and other objects (remake_shuffle_grass / _rocks / _boulders / _misc).
  - What a drop spot can hold is `remake_drop_contents`. "all" is the default, like OoTR and Ship of Harkinian (see
    below). "safe" means junk and repeat-safe items, and placed pickups take any pickup their level places, heart
    pieces included. The third value is "junk".
  - With "all", pots, small crates, grass, small rocks and Gold Skulltulas are "checked on pickup". That's the
    **respawn model** above: the object keeps its vanilla respawning until you take its item, then its vanilla twin
    stands there. They take anything with a world pickup (heart pieces, tokens, own-dungeon small keys, Ruto's
    Letter...) and every other item the get scene can give, like Ship of Harkinian allows. "all" isn't tested
    in-game yet.
  - **Scene drops** (`drops.py` "scene drops"). Major items have no world pickup in the remake, so for those the
    object drops the disguise carrier (a heart piece) with a tag of its own for that item. The tag is the
    placement's `Drop__RandoTag`, an F32 instance parameter we add to the shared Drop table (195 packs), and the
    dropper's AI hands it to its drop as `RandoDropTag`. The carrier's event AI answers the get scene's tag query with
    it, its root AI shows the item's model, and the get-scene hook gives the item, the same as at a heart spot.
    Dungeon items are credited through the dungeons plugin's entries. Spots holding the same item share a tag. The
    heart pickups get 256 KB more instance heap for their bigger AIs. Seed 2323 has 102 scene drops of 83 items, and
    `in_game_check` reads them back (`drops.verify_scene_drops`).
  - `remake_reset_group_objects` (`one_time`, the default, or `respawn`). 113 `SupplyItemResetSystemActor`
    placements (dungeons, Kakariko, Market, Lost Woods, SFM, Goron City) bring back the 2-3 pots, grass, crates or
    rocks they link every time they fire, so those objects could only ever hold repeatable junk. `one_time` takes
    every object holding a shuffled item out of its group, like OoTR's one-time pot checks (`drops.ungroup_ops`). It
    comes out of the actor's Links and out of both `GmdReset` copies. A group left empty loses its actor, the two
    pots' reverse links to it and its `GmdReset` entry. The object's flag is then made permanent like any other.
    Seed 2323 frees 338 objects from 109 groups, and `in_game_check` reads it back (`drops.verify_ungroup`).
    `respawn` gives the old behaviour (byte-identical plan). Not tested in-game yet.
  - **Object shuffles**, from Ship of Harkinian's Shuffle Trees / Icicles / Red Ice, all off by default.
    `remake_shuffle_trees` has 59 trees in 8 areas, counted per age layout, and you get one by rolling into it or
    with a blast (`can_bonk or can_blast_or_smash`). `remake_shuffle_icicles` has the 216 icicles in the Ice Cavern
    and the water trial. Stalagmites need a sword or explosives, and stalactites fall on their own.
    `remake_shuffle_red_ice` has the 12 usable blocks, which need Blue Fire. `remake_shuffle_boulders` also takes the
    silver rocks (23, Silver Gauntlets). The regions are in `data/rando/drops_regions_x1.json` (trees, bushes,
    respawning grass and pots, rocks) and `_x2.json` (icicles and red ice, from `tools/rando/_regions_ice_build.py`).
    Not built: palm trees (they never drop) and the Zora's Domain shop red ice.
  - Icicles, red ice and silver rocks had no Drop component, so `drops.drop_component_ops` gives them the bomb
    boulder's five Drop files, `Components.DropRef`, the icicles' DeathParam (for red ice and silver rocks), the empty
    table name on each placement and 32 KB more heap. The icicles' death table stops saving on break, and red ice's
    Blue-Fire hit stops saving its flag (node 42), so the pickup saves it like it does for pots.
  - **Flagless drops.** Trees and the respawning pots and grass have no save flag. So each one that holds an item
    borrows a saved Bool that nothing uses (`tools/rando/free_flags.py`). Those are
    `HavePlayedNaviBalloonMessage.typeNNN` flags with empty, unrequested balloons, minus the ones extras_npcs claims,
    which leaves 222. The object always drops the carrier with a tag of its own, and the get-scene hook gives the
    item once and sets the flag. After that a respawning pot or grass is gone (negated placement `Presence` on the
    flag). A tree's placement names the flag in `Drop__RandoFlag`, a String instance parameter in the Drop table, and
    its root AI marks the tree as already shaken while the flag is set (`drops._tree_edits`). `in_game_check` reads
    all of it back (`drops.verify_object_drops`). With every object shuffle on, one of my seeds has 80
    flagless drops and 171 scene drops. Not tested in-game yet.
  - **Bushes** (`remake_shuffle_bushes`, On/Off, default off). It's Ship of Harkinian's Shuffle Bushes, alias
    `shuffle_bushes`. The 26 Hyrule Field bushes are `RemakeBush` locations (`can_cut_shrubs`). That's 13 per age
    layout, all `Land_kokiri_Plant_A_02_DropFixed_03`, the only bush in the remake with a drop. The type has no AI
    and no save flag, so the patch gives it an AI (`drops.NEW_AI_DROPPERS`). It's the bronze boulder's 8-node root AI
    copied in as `AI/RandoBush.root.ainb`, with its own AIInfo, `Components.AIInfoRef` and 32 KB more heap, and it
    carries the usual hand-over. Each spot borrows a flag (flagless "presence"). The bush drops the carrier once, then
    a vanilla twin (bugs) stands there. An unshuffled bush still counts as a bug source. Seed 2929 read back with 0
    problems. Not tested in-game yet.
  - **Fairy shuffles**, Ship of Harkinian's five settings, On/Off, default off, with aliases like
    `shuffle_stone_fairies`. `tools/rando/fairies.py` builds `data/rando/fairy_map.json` and
    `data/rando/logic/fairies.json`, and the plugin is `tools/rando/parity/fairies.py`.
    The vanilla fairy still comes and heals you, and the item comes once
    along with it through songs_trade's give steps.
    - `remake_shuffle_stone_fairies` has 80. That's each talkable stone's "Fairy" for Zelda's Lullaby, Epona's, Sun's
      (where OoTR counts it) or Time, and "Big Fairy" for Storms. The stone asks its own number with
      `EventQueryGossipStoneCheckInstanceName`, which vanilla never uses.
    - `remake_shuffle_fountain_fairies` has 47. The Colossus oasis has 7, given after its once-only Storms cutscene.
      The HF, SFM and ZR fairy grottos have 8 each, given the first time you enter, through the reused scene IDs
      `WaterTemple_GetMap`, `SpiritTemple_GetCompass` and `FireTemple_GetMap`, which the chests plugin's scene-ID
      budget then leaves alone. The Graveyard Shield Grave's 8 work the same way, the first time you enter the grave
      whose corridor ends at the fountain room's bombable wall (scene ID `InsideTheDekuTree_GetSlingShot`). We kept
      SoH's rule there, so you have to break the wall. The last 8 are in Ganon's Castle's fountain room under the
      lobby's fake floor, SoH's "Scrubs Fairy 1-8", given when you enter the fountain. No event plays there, so a
      copy of the fountain's music Area and a copied requester run Gerudo Valley's vanilla area-event module as a new
      logic group (make_patch plan section `groups`, scene ID `ForestTemple_GetBow`). A lazy Presence hides the area
      copy once the gift has played.
    - `remake_shuffle_song_fairies` has the 9 Fairy Note spots, and `remake_shuffle_bean_fairies` has 30 (3 per bean
      plant). Both tell the spot apart by naming the fairy's or the soil's placement and asking `is Link near <it>?`,
      a question shape vanilla already uses.
    - `remake_shuffle_butterfly_fairies` makes 15 butterflies into drop spots (`drops.py` CATEGORY "butterfly", the
      respawn model, `data/rando/drops_regions_x3.json`, child Deku Sticks).
    - Stones, notes and beans borrow flags from the end of the free pool, while the drops plugin takes from the
      front, and `in_game_check` refuses a flag used twice. Seed 2930 with every fairy kind read back with 0
      problems. Not tested in-game yet.
  - The 14 freestanding PoHs and 8 boss Heart Containers take any item in every mode. Taking one plays the shared get
    scene, which tells the spot by its placement Name (the pickup's event AI answers the scene's tag query) and gives
    the seed's item instead of the heart. It needs the songs_trade plugin's get-scene hook.
    If you're standing, the hook hands the item over with the same hold-up routine every other check uses, with the
    fanfare and Link raising it. In the air or in water it uses the get window, like the game's own in-water give
    does (`_songs_trade_lake._resident_give`).
  - **Item looks** (remake setting `remake_item_looks`). "item" is the default, since OoTR always draws the real
    model, and "heart" keeps the pickup's own look. With "item", every get-scene spot shows the item it gives: heart
    pieces, heart containers, the two freestanding keys and the touch pickups turned into hearts.
    - The pickup type gets an ActorHolder component, a copy of a vanilla wild holder slot bound to the pickup's Root
      bone. For the spot's placement Name, its root AI hides its own model and creates the item's display actor by
      name, the way chests create their contents. Those are the `Item_*` / `TBox_*` models that chests and the get
      scene show (`drops.item_display`). The get scene's hide step deletes it.
    - A display smaller than 0.35 m (Stone of Agony, Goron Bracelet, compass, bottles...) is drawn scaled up to that
      size, keeping its proportions (`drops.look_scales`). At a spot under water the pickup keeps its own idle glow
      (`drops.under_water`).
    - Progressive items show the next tier, checked when the spot appears, in the tier order from
      `tools/progressive.py`. Ice traps show their OoTR `looks_like_item` (`ice_trap_appearance`). Items with no
      display model keep the pickup's look: Heart Container, Piece of Heart, tunics, Progressive Sword, the Kokiri
      Wallet tier and silver rupees.
    - The disguised ice trap that a pot or crate drops can't be told apart by spot, because a dropped pickup has no
      placement Name. So its root AI checks its own type and, when it appears, shows one of up to 12 display models
      picked at random (a RandomSelector, weights 1.0). They come from the pool OoTR's `ice_trap_appearance` uses,
      which is major items by default, with songs only when they're shuffled anywhere (`parity/drops._disguise_looks`,
      plan note `_drops_looks_disguise`).
    - The wild slot only creates actors that are already loaded. In one of my test builds the trap hid its heart
      model and showed no item at all because of that. So the look holder also declares every display of the seed as
      a named slot (`"Actor"`: its ActorParam), the same way the chest's holder declares its content displays, and
      they load with the carrier. That's about 18 MB compressed for 103 displays, and `verify_looks` checks that every
      display is declared.
    - A holder also creates its actors asleep. The falling rocks wake theirs with
      `OneShotActorHolderTryCancelSleepActor`, and chests wake their content when opened. So the look branch wakes the
      display at the carrier's position every frame until none is asleep (`look_ops` `wake`, also checked by
      `verify_looks`).
    - The Treasure Chest Game chests also show their contents' display actor (`DropViewActor`, chests plugin).
    - Not seen in-game yet.
- **Unchecked pots and grass** (OoTR's `correct_potcrate_appearances`, `parity/_marker.py`). Crates and lift rocks
  take a colour per placement, but pots and grass don't have one. So a pot or grass tuft holding a shuffled item gets
  the placement Name `RandoUnchecked`, and its type's root AI tints it blue while it has that Name. It's the game's
  own blue "stunned" tint (`ExecuteSetModelExtraColor`), and blue is the only colour that node offers. In
  `textures_content` only the categories the setting colours get it. Spots that come back after their check keep
  their own look, crates and rocks too. Those are spots with no save flag, a reset group kept by
  `remake_reset_group_objects` "respawn", or an item whose second pickup changes nothing. So a marked object is
  always an unchecked one. Not seen in-game yet.
- **No save warp** (`tools/rando/no_savewarp.py`). In the remake, loading picks up where you saved and a game over
  reloads the latest save, and the game autosaves after every level change. So nothing sends Link back to his spawn
  like OoT's save warp does. Every seed gets checked sphere by sphere. Everywhere either age can reach has to lead
  home by walking, by dying (back to where you entered the dungeon or area) or by a warp song you can already play.
  If it doesn't, the generator rerolls. Vanilla-entrance seeds pass, and about half of entrance-shuffled seeds need a
  second attempt.
- **The remake's story rules in OoTR's logic** (`tools/rando/world_settings.py`). In the remake every dungeon's story
  stage completes in its exit scene after the boss, and nothing checks the stones or medallions themselves. So we
  rewrite OoTR's rules as they load. In the rules for the Door of Time, the Ocarina of Time scene, Sheik's songs and
  the Light Arrow cutscene, each stone or medallion becomes its boss's "Defeat X" event. The vanilla rainbow bridge
  waits for the Light Arrow cutscene, a new OoTR event, instead of the Light Arrows item. That way stones and
  medallions can go anywhere.
- **World settings** (`world_settings.py`). These go in
  as new-file defaults in the save-data list (`GameData/GameDataList`, big-endian), as scene values and in the
  game-start sequence. A new file starts from those defaults, and existing saves keep theirs. The settings are
  `open_forest` closed / closed_deku / open, `open_kakariko` closed / zelda / open, `open_door_of_time`
  stones_oot_sot / open, `trials` 0-6, `plant_beans`, `scarecrow_behavior` free, `start_with_rupees`,
  `starting_hearts`, `chicken_count` 1-7 and `big_poe_count`. Everything else has to describe the remake as it is
  (`REMAKE_ONLY`), or the generator refuses it. `seed.json` lists the applied values that haven't been seen working
  in-game yet.
- `tools/rando/chest_map.py` writes `data/rando/chest_map.json`, which pairs OoTR chests with remake chests.
  - The room-by-room reconciliation (`data/rando/reconcile.json`) goes by
    positions, room numbers and room contents, and it overrides the item-based pairing below. High and medium pairs
    are certain. Low pairs stay vanilla, and so do OoTR chests the remake doesn't have, ice-trap chests
    (`Obj_TBox_A_04`, no item setting) and key chests in dungeons whose key count differs from OoT (Water, Bottom of
    the Well, Ganon's Castle, Gerudo Training Ground). That's 123 certain and 56 vanilla. It caught 12 wrong
    "certain" pairs from the item-based pass.
  - The item-based pass has three kinds. `full` is a certain pair: an exact match, a unique vanilla item in the
    area, or a group with identical logic. `group` means the same vanilla items (or leftovers whose contents
    changed) in an unknown order. Every chest of the group gets the rule "every chest of the group is reachable"
    (one OoTR event per chest under its own rule), so whichever chest an item really lands in is reachable when
    logic says so. Both of those take any item. `vanilla` means there's no reliable pair yet (Treasure Chest Game,
    dungeons where the remake moved small keys). That's 38 of 179, and they're being reconciled.
- `config/rando_locations.json` lists the scene locations we randomize, by OoTR name: NPCs, songs, boss rewards,
  Great Fairies, minigames and the Skulltula House. It's `verified` plus `testing` (57). Each one has to match one
  remake location, and the patcher changes every give step of it. Progressive items go there too, wherever every
  give step can take one. `tools/rando/scene_modes.py` works that out into `data/rando/scene_give_modes.json`, and
  it's 166 of 186 scene locations.
- Every location the patcher can't change yet is locked to its vanilla item before the fill. OoTR stand-ins from the
  same group, like random bottle contents, get swapped back the way OoTR's plando does it.
- `config/item_map.json` maps each OoTR item to a remake chest actor. Progressive items go to the progressive chest
  scenes.
- The output is `plan.json` (for `make_patch.py`), `spoiler.json` (OoTR's) and `seed.json` (a summary).
- Section 6 of `tools/selftest.py` generates a seed and checks that every placed item exists in the game.
- **Hints.** OoTR's Gossip Stone hints go into `EventFlowMsg/GossipStone.msbt` as `GOSSIP_<AREA>_NN`, in every
  language, keeping the original style tags. OoTR's colour marks are dropped for now. OoTR's 40 stones match the
  remake's 40 one for one by area. With `hints: always`, the stones' Mask of Truth checks (GossipStone Event112 /
  Event25) go to the rumour.
- Plans can set any message's text with `"text": [{"lang": "*", "file": ..., "label": ..., "text": ...}]`. That's
  `tools/msbt.py`, which round-trips all 8,640 text files byte for byte.

## Installing safely (`tools/install.py`)

- Every check runs before anything changes. The old patch has to come off whole, and then each file the new one
  writes has to be the original. If not, nothing gets touched ("Stopped, nothing changed").
- The install record (`installed.json`) gets written before the first file is copied. So if an install stops half
  way (the app closed, a locked file, a full disk), each file is either the original or the new patch's, and
  `restore` takes them all back. `restore` checks every file first too.
- If there's no record (an old install), a patch that's found whole in the game folder (`out/<seed>/patch`, or the
  old flat `out/<seed>`) gets its record back, including new files and Longshot's raised size table.
- When a Longshot update rewrites `prompts/rsizetable.zs` or its `texts/`, we take that as Longshot's new original
  instead of stopping every install or restore after it.
- `tools/make_patch.py` empties an old patch folder before building into it, because otherwise stale files get
  installed.

## Read-back coverage (`tools/rando/in_game_check.py`)

The checker reads the built patch back and checks drops, fairies and fishsanity, and every placed reward too, like
chests, freestanding pickups and scrubs. For each one it compares the planned item, the first tier of a progressive
item and any extra settings.

`parity/_hints_check.py` checks every text edit, hints and the FOOL text included. `parity/_hints_stones.py --verify`
checks the Gossip Stone pairings, and `parity/_appearance_check.py` checks the appearance plugin's chest types and
colours. Plugins listed under `_verify_plugins` in the plan run their own `verify(patch, plan, romfs)` checks, the
SoH and 3DR extras too. This read-back doesn't cover entrance shuffle yet, but you can run `parity/_entrances_verify.py` by
hand, and it builds a separate patch.

## Known limits of the catalog

All of this is read from the game's files.

- **Shops.** A shelf's item comes from the shopkeeper's `ShopParam.GoodsList`, not just the shelf's `Gyaml` that the
  catalog records. So the patcher refuses shelf `Gyaml` changes unless you set `"force": true`. A price is the
  `Shop_*` actor's `BuyingPrice` plus the slot's `PriceOffset`.
- **Scrubs.** `ScrubBusiness_ShopItemActorName*` is a lookup key, not the item sold, so it's refused too. The item
  and price of the sale are in the `SimpleShopSub_Scrub_Business_OneTime` call in the scene, which is already
  catalogued as event rewards.
- **Freestanding.** 112 green rupees, 48 blue rupees and 22 recovery hearts with permanent flags aren't catalogued
  yet. Freestanding items have no content setting, so the object type itself changes, and you have to stick to
  types the level already loads.
- **Pots, crates, grass, beehives, rocks, trees.** They're in `data/rando/drop_objects.csv` (1,986 placements). Any
  of them can drop a chosen pickup with `Drop__DropActor` on the same object, but only 44 pickup types exist. And
  they come back when you leave the area unless the reset type of their save flag changes.

## What is editable

| Kind | Count | Where it lives | How it is edited |
|---|---:|---|---|
| chest | 213 | placement `Dynamic.Drop__DropActor` | item name; chest rules below apply automatically |
| gold_skulltula | 100 | placement; vanilla drop comes from the actor's drop table | sets an instance `Drop__DropActor` |
| event | 186 locations (228 parts) | event flows: NPCs, songs, medallions, stones, Great Fairies, minigames, trade quest, Skulltula House | the item parameter of the give/display calls; multi-part locations are edited together |
| shop | 128 | `Shop_*` display actors (child and adult shelves are separate) | swap for another `Shop_*` actor |
| scrub | 87 offers | `Dynamic.ScrubBusiness_ShopItemActorName0..2` | item name |
| freestanding | 45 | heart pieces, heart containers, keys, letters, placed items | swap the actor |
| drop | 229 | pots, rocks, crates, beehives, trees, grass, enemies with `Drop__DropActor` | item name |

`data/rewards.csv` has one row per location, 988 in all, counting the remake's boss-rush mode. The rows mark
boss-rush-mode entries and shared flows, like `Dm_SY_Ocarina`, the song-learning flow every song uses.

Beyond rewards, a plan can change anything:

```json
{
  "rewards":    {"<location or reward id>": "Item_Hookshot",
                 "<chest id>": {"item": "Item_Bow", "extra": {"GetEventName": null}}},
  "placements": [{"file": "Banc/X/X_Dynamic.bcett.byml.zs", "hash": "123", "set": {"Dynamic.Foo": 1}, "remove": ["Dynamic.Bar"]}],
  "events":     [{"file": "Npc_X", "flowchart": "Npc_X", "event": "Event46", "param": "ActorName", "value": "Item_Y"},
                 {"file": "Npc_X", "flowchart": "Npc_X", "event": "Event10", "next": "Event12"},
                 {"file": "Npc_X", "flowchart": "Npc_X", "event": "Event20", "case": 0, "next": "Event12"}],
  "packs":      [{"pack": "Pack/Actor/Enemy_Skulltula_Gold.pack.zs",
                  "file": "Drop/DropSubTable/DropTable_Token_Gold.game__drop__DropSubTable.bgyml",
                  "set": {"Items.0.DropActorName": "Work/Actor/Obj_Rupee_Gold.engine__actor__ActorParam.gyml"}}],
  "chest_event_policy": "auto",
  "chest_size": "keep"
}
```

- `"placements"` also takes `{"file": ..., "hash": ..., "delete": true}`, which takes a placed actor out of the file.
  It's refused if another op edits that actor, if anything in the file links to it, or if an AiGroup or group names
  it.
- A `"packs"` op can add a file to a pack with `"new_from"`. The new file is a copy of another file in that pack,
  with its own size-table entry.
- Size-table entries. The game gives each file a heap the size of its entry, and many types need memory for each
  block they parse, not just for their bytes. So every file the patch changes or adds, inside packs too, gets at
  least what the game's rule for its type asks for. Those rules are in `make_patch.rule_entry`, fitted over every
  vanilla file of the type: AI files, event flows, levels, actor params, holders, death params, blackboard tables
  and death tables. Other byml types go up by their growth plus 384 bytes for each dict or array element they gain.
  Raising them by bytes alone crashed the game twice.
- When a plan rewrites a scene ID (`replace_row`), that ID is taken off every chest whose vanilla GetEventName names
  it, unless that chest's reward asks for a scene itself. A reward asking for a scene also wins over a plugin's own
  "remove GetEventName" op. Two different rewrites of one row are refused.

### Progressive items (OoT Randomizer style)

`config/progressive.json` maps OoTR's progressive item names (from OoTR's ItemList) to the remake item for each
tier, in order. A plan can put them in **small chests**:
`"KokiriForest/chest/4555665598794293658": "Progressive Hookshot"`.

Like in OoTR, the tier is decided when the chest opens. The chest runs a shared "give the right tier" scene, one per
item, that `tools/progressive.py` adds to `Dm_SY_TreasureboxSmall`. That scene plays the chest's own opening (front
or kick, whichever vanilla picks) and checks what you own, highest tier first, with
`PouchSystemActor.EventQueryIsExistInPouch`. Then it gives the tier with the game's own in-cutscene get routine,
`Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff`, the one NPC cutscenes like the Lost Woods bullet bag use. Link
holds it up, the message shows and it's added. Last, it marks the chest opened. The chest's own contents (the first
tier) are never shown. I tested this in-game and it works.

Each scene needs a scene ID and the table can't grow, so it reuses a chest item-scene row from
`config/scene_rows.json`. The vanilla chest that used that row keeps its item but plays the normal opening.

**Query answers in scenes: case 0 is "yes", case 1 "no".** Getting those backwards gave the Longshot first. And
copying the fishing pond's show-item step instead of the get routine left Link holding nothing.

Big chests clone the big chest's own opening (`big_chest_graphs`).

**Scene rewards** (NPCs, songs, cutscenes). The give step gets replaced by the same checks, and then each tier gets
one of two things. If the giver's flowchart has a `PouchSystemActor`, it's a copy of the give step with only the
item changed, keeping the camera, NPC and animation arguments. If the giver calls the give routine with nothing but
the item, it's a call to a new entry next to that routine (`GetPouchContent` / `Dm_SY_GetInEvent`, which have one).
Everything that led to the give step gets pointed at the replacement: next, branch cases, parallel-step targets and
entry points. A step that only shows the item, after the same scene's add step, shows the tier that was just given.

My first try used the game's own "if the player has X, give Y instead" chest rule (`Drop__CheckActor` /
`Drop__DropActor_Substitute`). Only `Obj_TBox_A_06` runs it, which is the small chest plus that check. In Kokiri
Forest it made the level stop loading its objects, so the houses were gone. That happened in three builds, even with
the A_06 set up like vanilla's, and the game log shows no error. Vanilla only places A_06 in five areas (Bottom of
the Well, Dodongo's Cavern, Gerudo Training Ground, Graveyard, Spirit Temple) and only ever checks for
`TBox_Shield_*`. So I tried one set up exactly like vanilla's, checking `TBox_Shield_Deku` with no scene name, and the
houses still vanished. **A_06 can't be placed in Kokiri Forest at all**, so it's no route to progressive items. It
would only ever have covered two tiers in small chests anyway. We still don't know why. A_06's actor-table rows match
the plain small chest's apart from memory size, its extra shared file is always loaded, and its "opened" save flag
is the same kind every chest has.

### Settings each object accepts (`tools/actor_params.py`)

As a precaution the patcher refuses any setting on a placed object that its actor pack doesn't declare and vanilla
never uses on it, apart from `DefaultDungeonRoomIndex`, which all objects take. This went in after putting check
settings on ordinary small chests made Kokiri Forest's houses vanish. Later a build broke the level with only
declared settings, so undeclared settings are suspected to be harmful, not proven. A declared setting that's new to a
level file is fine, I tested that. `python tools/actor_params.py ROMFS Obj_TBox_A_01` lists what an object accepts.

### Chests, openings and item scenes

How the game decides what plays when a chest opens:
- Every chest type has a default opening scene. For the small chest it's `Dm_SY_TreasureboxSmall`, and for the big
  chest it's `Dm_SY_Treasurebox` (kick-open, fanfare, item held up). A chest's `GetEventName` in the level data
  replaces it.
- **The chest decides, not the item.** Chests keep their type (`"chest_size": "keep"`, the default), so a big chest
  plays the full suspense opening even for 5 rupees. I tried converting chest types and it lost the animation,
  because the chest kept the other type's opening scene. It's still there as `"chest_size": "match_contents"`.
- `GetEventName` values are IDs in `RSDB/EventSetting...` that point to an event file and entry point.
  `config/chest_rules.json` sorts them into two kinds. **Location/story scenes** stay whatever the chest holds: Sheik
  after the Iron Boots, Nabooru taken, Ruto chests, Dampe's race, the treasure chest game, Navi's tutorial in Mido's
  house. **Item scenes** get dropped when the item changes, so the chest falls back to its normal opening.
- The chest plays the `Open` step of the scene file its `GetEventName` points to, then that scene's entry. If the
  scene file has no `Open` (like the sword's `Get_StoneOfForest`), there's no opening animation.
- Cinematics can hard-code positions. `Dm_Kokiri_0063` (the sword) warps Link and Navi to fixed coordinates and
  stages its camera at a fixed world point (`GameEventBaseSetting/Dm_Kokiri_0063`). That's the teleport, not the
  scene settings anchor, and re-anchoring the settings still teleported.
- **The scene table can't grow.** Adding a row to `RSDB/EventSetting` (or `RSDB/Location`) aborts the game at
  startup. Renaming or rewriting a row is fine, and `GameAnalyzedEventInfo` can grow. So a moved item reuses its own
  scene ID, which is free once the item leaves its vanilla chest, rewritten with `"replace_row"`. The patcher refuses
  `add_row` on those tables and mirrors scene rows into `GameAnalyzedEventInfo`.
- `powershell tools/boot_check.ps1` starts Longshot, waits for a crash or for startup to get past resource loading,
  and closes it. It's a 10-second check that a patch boots.
- **Keep the precomputed scene info in step.** For each scene ID, `RSDB/GameAnalyzedEventInfo` lists the scenes it
  hands off to (`ChildEventList`, `EventTransition` targets) and the scene files it calls (`SubFlowList`).
  - One build changed the sword scene's hand-off from the big-chest scene to the small-chest one without updating
    the list. The scene played, but the chest closed again afterwards and gave the sword every time. Now the patcher
    updates `ChildEventList` for every scene ID whose reachable hand-offs an edit changes, and with that the chest
    stays open.
  - It also keeps `SubFlowList` in step, following calls into other scene files. The same calculation matches
    Nintendo's lists for 2,161 of 2,319 scene IDs. Lists only get added to, never cut, except for what an edit
    removes.
  - Its reachability matches Nintendo's lists exactly for 2,200 of 2,319 scene IDs. The rest also count hand-offs
    inside called scene files, and those are left as they are.
- **New steps follow Nintendo's relocation rule.** Adding an entry to `Dm_SY_TreasureboxSmall`, which every small
  chest uses, once meant no chest would open. The builder was breaking a rule that every vanilla file follows
  (checked on ~52,000 pointers, `Evfl.relt_rule_violations()`). Array pointers (actor actions and queries, entry step
  lists and variables, branch cases, fork targets) are listed for relocation even when they're empty, and parameter
  blocks only when they're set. The builder dropped the empty-but-listed ones for every entry point it copied. Now it
  follows the rule, the patcher refuses to write a scene file that breaks it, and adding steps to
  `Dm_SY_TreasureboxSmall` works again.
- Another way to move the sword's scene gives the item's own scene file (`Get_StoneOfForest`) an `Open` step that
  calls the destination chest's opening, retargets its chest-success transition to the destination chest's, and
  moves the cinematic, with no scene-table rows changed.
- New structures are laid out like Nintendo's files: data, then string pool, then relocation table. Text values are
  stored inline right after their parameter, like in every vanilla file (8,755 of 8,755 checked). Text edits create a
  fresh parameter with the text inline. Putting text in the shared pool instead made the edited scenes fail.
- Vanilla big-chest item scenes have no Open step of their own, so the chest's opening doesn't come from the scene
  file.
- An older way to move an item scene, now replaced, put a new entry in the destination chest's own opening file
  (`Dm_SY_TreasureboxSmall`, with Mido chest success and then the transition to the cinematic) with its own
  scene-table row. The cinematic's warp targets and stage point moved together to the new chest.
- Plans can add entry points with new steps to any event flow, either with `"add_entry"` + `"steps"` or as a graph
  with branches and parallel steps (`"add_graph"` + `"nodes"` + `"start"`, see `EvflBuilder.add_graph`). They can
  also add table rows (`"add_row"`) and edit number lists like positions. That's all built with
  `tools/evfl_build.py`, and its dictionary and relocation-table builders reproduce all 76,529 dictionaries and 914
  tables in the game byte for byte.
- `python tools/evfl_dump.py ROMFS Get_StoneOfForest GetSword` prints any scene as readable steps.

Plans can also edit any data file (`"byml"`, with `[__RowId=X]` selectors for tables) and replace files (`"copy"`).

`data/event_checks.json` lists the 921 places where events check for an item ("is it in the pouch?").
When an NPC's reward moves, these checks decide whether the NPC gives it again, so change them with `events` edits.

## Verified vs. not yet verified

Checked on the files by `tools/selftest.py`, all passing:
- 187/187 placement and table files re-save byte for byte, and 8,385/8,385 packs repack byte for byte.
- 914/914 event flows read completely, and every pointer matches the file's relocation table.
- Setting every reward to its vanilla value writes nothing. Changing all 1,020 at once reads back exactly, with no
  other actor field or event structure touched.

What I tried in the game:
- Turning any Mido's house chest into `Obj_TBox_A_06` made Kokiri Forest stop loading its objects (houses gone),
  even set up exactly like vanilla's. A declared setting that's new to the level file was fine.
- The Kokiri Sword in a Mido's house small chest. The small-chest opening played and the sword cutscene played right
  at that chest with no teleport, so moving the warp targets and stage point works, and so do text edits stored
  inline. But the chest closed again after the cutscene and gave the sword again every time I opened it (see "Keep
  the precomputed scene info in step").
- The same thing with the corrected hand-off list: the chest stays open. **Moving an item that has its own scene into
  another chest works end to end.** Point the scene's chest step at the new chest's type, move the cinematic's warp
  targets and stage point to the new chest, and keep the scene-info hand-off list in step.
- Two Progressive Hookshot chests. On the first install no chest opened, because of the size table (see Workflow).
  With Longshot's size table raised the chests opened, but both gave the Longshot with nothing held up (see
  Progressive items).
- **Progressive Hookshot in two small chests works.** At the first chest Link holds up and gets the Hookshot, and the
  second gives the Longshot. Both stay open, and the sword chest and an ordinary chest are unaffected. That build
  proved new scene steps with branches and parallel steps in a shared scene file, calls into other scene files, a
  reused scene ID, the scene-info lists and Longshot's size table.
- Bombchus from a chest showed 0. Remake bombchus take their capacity from the bomb bag (`Item_Bombchu`
  PouchContentParam `MaxNumGameData: "Bomb"`). OoTR's `free_bombchu_drops`, on by default, lets its logic count
  bombchus without a bomb bag, so it's off here.

Not verified in the game yet:
- Item looks (`remake_item_looks` "item"). That's a holder added to a pickup type, the display created and bound to
  the hidden pickup and deleted at the get scene's hide step, next-tier progressive displays, the Treasure Chest Game
  showing any `Item_*` as its content, and small displays drawn scaled up with the glow kept under water.
- Shared-file consistency (one file per path in every pack). It isn't meant to change any behaviour, but the heart,
  key and pot AI files now also go into the packs that had a vanilla copy.
- The save-data defaults (forest exit open, Kakariko gate open, 99 rupees, beans planted, Pierre everywhere, 4
  cuccos) and the starting hearts (a number edit in the game-start sequence).
- Item scenes moved by hand so far, which is only the sword. The patcher doesn't do the three steps itself for any
  item yet.
- Progressive items in big chests and in NPC and cutscene rewards, and other progressive items (same scene, other
  tiers).
- Gold Skulltula instance drops, freestanding and shop actor swaps, and event item swaps (does the scene show the new
  item, do the flags follow).

## OoT Randomizer logic as reference (`reference/`)

- `reference/ootr/logic.json` is OoTR (MIT, commit in `SOURCE.md`) exported to JSON, with 342 regions, 1,448
  locations, 156 helpers and the rule strings verbatim. `summary.md` explains the rule language.
- `python tools/match_ootr.py` matches OoTR's 523 classic checks to the remake and writes `data/ootr_match.csv`. A
  match is exact, group (same set, pairing still open, e.g. a dungeon's Gold Skulltulas), area_set (same area and
  type, contents changed), event_item_differs, ambiguous_event or no_match (mostly the business scrubs the remake
  removed or reworked), and then there are the remake-only checks.
- Tricks and glitches: **nothing is on by default.** All 186 glitchless tricks and all 185 N64 glitches are off. You
  only turn one on for testing, by adding its exact name to `enabled` in `config/tricks.json`.
  `python tools/logic_settings.py` checks that, and logic code has to read trick values through it.
  `data/trick_checklist.csv` (from `python tools/trick_checklist.py`) lists what each one affects, with a
  `tested_in_remake` notes column. The N64 glitches only show up as optional "or" branches inside helpers, so with
  them off those branches just disappear. Remake-only glitches get added as new tricks.
- Remake glitch tricks (`tools/rando/parity/glitches.py`, `data/rando/remake_glitch_tricks.json`), all off.
  - Each trick has **live routes** and **candidates**. A live route is one a source shows, and it's in the trick's
    logic when the trick is on. A candidate is something to try in the game, and it's in no logic until it's marked
    `"verified"`. `"refuted"` and `"blocked"` ones never are. There are 62 live routes and 111 candidates, and
    `python tools/rando/glitch_report.py checklist` writes the list to try in game.
  - The techniques are logic helpers in `data/rando/logic/glitches.json`. For example `remake_ijsc` is Deku Sticks as
    child or the Megaton Hammer as adult, plus another quick-menu item.
  - An enabled trick ORs its routes into the built world and makes the exits and events that OoTR's world lacks,
    closed until a route opens them. It turns OoTR's raw adult items in the Shadow Temple into `can_use(...)` once a
    child may enter, gives the Spirit Temple hand chests regions of their own (reachable from the Colossus), and puts
    helper routes (`can_leave_forest`) beside every use of the helper.
  - After the fill, a seed that needs the child-Shadow age swap has to be beatable the way you'd actually play it:
    all child progress first, then adult, and child again only through the pedestal. If it isn't, the fill is redone.
  - **Glitched logic.** Logic Rules "Glitched (remake glitches)" (`logic_rules: "remake_glitched"`,
    `config/glitched_settings.json`) is glitchless logic plus every trick that has live routes.
    `glitches.resolve_settings` turns it into exactly that before OoTR reads the settings. OoTR's own glitched logic,
    `advanced`, is the N64's and never gets handed over. A settings file or string that asks for it gets
    `remake_glitched`, with a note on stderr. The spoiler shows `remake_glitched`, with a settings string that makes
    the same seed. Seed 4242 gives the same plan as Glitchless with those tricks, and the same again from its own
    string read back.
  - In the app, Detailed Logic has a **Remake glitches** section with one switch per trick
    (`"logic_remake_glitch_jsc": true`, which `generate.load_settings` moves into `allowed_tricks`). Each one says
    what it is and where the logic uses it (`tools/release/glitch_ui.py`). Glitched and No Logic grey them out.
    OoTR's Enable Tricks list doesn't hold them.
  - `python tools/rando/glitch_report.py check | coverage | uses SEED` checks the routes, counts the checks each
    trick opens, and tells you whether a seed's playthrough needs its tricks.
  - With every trick off, a seed is byte-identical to one built before the glitch tricks (checked on seed 2828).
- Ganon's tower collapse needs the Longshot (`data/rando/logic/ganon_collapse.json`, from runners' reports).

## Format notes

- Placements are `Banc/<Area>/<Stage>_{Child,Adult}_{Dynamic,Static}.bcett.byml.zs`, zstd with dictionary 3 from
  `Pack/ZsDic.pack.zs`. They're BYML v7, and dictionaries are written with the entries sorted but the children in
  insertion order.
- Event flows are BFEVFL v4 (`Event/EventFlow`). It's the same as the documented v3, except events are 0x30 bytes
  and there are two new event types (5 is a sub-flow with branches, 6 is index + hash). `X.110.bfevfl.zs` is a newer
  version of `X`, and edits go to both. New strings get appended to the string pool, before the relocation table.
- In the size table (`System/Resource/ResourceSizeTable...rsizetable.zs`), bcett entries are size + 292 and event
  flows are round_up(size, 32) + 272. The patcher raises entries by the growth, rounded up to 32.
- **Files inside packs are path-keyed.** Every file in a pack has a global path. ActorParams name
  `Work/AI/Root/X.root.ain`, and the size table has one entry per path. In the vanilla game, a path that sits in
  several packs has the same bytes in all of them: 13,830 such paths in 8,385 packs, and none differs (selftest
  step 9).
  - A path-keyed resource cache would hand whichever copy loads first to every actor, so an edited file has to end up
    the same in every pack that holds it. `make_patch.py` refuses a patch that breaks this (it compares every pack in
    the game, `tools/packpaths.py`). A plan op can say `"pack": "*"` for every pack holding the file, or give a list
    of packs.
  - Per-type behaviour inside a shared file goes through checks on the actor itself (its instance name, or
    `QueryGenericGetActorName` for its type), not through per-pack copies.
  - `"from_pack"` copies a file from another pack, to the same path or to a new one with `"new_from"`.
  - The drops plugin's get-scene, key and checked-on-pickup edits all follow this, with one file per path. The heart
    event AI is in 5 packs, the key one in 15 and `Obj_Pot.root` in 21. Grass and rock DeathParams get a new file of
    their own instead of the shared one, which Dampe's soil and respawning pots also use.
- AINB blackboard reads: in these 0x408 files, a parameter read from the blackboard has its top two flag bits set to
  `10` and the blackboard index in the low 16 bits (13,889 inputs, 7,526 properties). `tools/ainb.py` tests bit 31
  (`BB_INDEXED`). `copy_nodes` refuses a node like that unless the copy gets its own value (`values`), `describe`
  shows the source (`bb#N`), and `set_input` refuses it. No file sets bits 0x10000/0x20000, so those aren't the
  ones to test. None of the nodes the plugins copy read the blackboard, which we checked for every copy in seeds 2323
  and 4646.
