"""The remake's world, for OoT Randomizer's logic and for the patcher.

1. Story rules (install_logic). The remake completes a dungeon's story stage in its exit scene after the boss
   (Dm_SY_BancChange_EscapeDungeon), and no scene or save-data expression checks the spiritual stones or the
   medallions themselves. So every gate OoTR ties to holding a stone or medallion follows that boss's defeat here:
   the Door of Time (DoorOfTime_CheckStoneNum waits for the Fire and Water stages, then the moat scene), Sheik's
   songs, the Light Arrow cutscene (Spirit and Shadow sages awake) and the vanilla rainbow bridge, which appears
   after the Light Arrow cutscene, not when Light Arrows are found. OoTR's rules get rewritten that way as they
   load, and the vendored files stay untouched.
   Bombchus take their capacity from the bomb bag (Item_Bombchu's PouchContentParam has MaxNumGameData "Bomb"),
   so OoTR's free_bombchu_drops (bombchus usable with no bomb bag) has to stay off.

2. World settings (check_settings, world_plan). These are the OoTR settings the patcher can apply, as new-file
   save-data defaults (GameData/GameDataList, a new file starts from them and existing saves keep theirs), scene
   values and the starting-hearts number in the game-start sequence.
   Every other world setting has to stay at the remake's own behaviour
   (REMAKE_ONLY) so logic matches the game.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGIC_DIR = os.path.join(HERE, "data", "rando", "logic")

BOSS_EVENT = {
    "Kokiri_Emerald": "Defeat Queen Gohma", "Goron_Ruby": "Defeat King Dodongo", "Zora_Sapphire": "Defeat Barinade",
    "Forest_Medallion": "Defeat Phantom Ganon", "Fire_Medallion": "Defeat Volvagia", "Water_Medallion": "Defeat Morpha",
    "Shadow_Medallion": "Defeat Bongo Bongo", "Spirit_Medallion": "Defeat Twinrova",
}
LACS_EVENT = "Remake Light Arrow Cutscene"
BRIDGE_VANILLA = re.compile(r"\(\s*bridge == 'vanilla' and Shadow_Medallion and Spirit_Medallion and Light_Arrows\s*\)")


def _rule(s):
    for token, event in BOSS_EVENT.items():
        s = re.sub(rf"\b{token}\b", f"'{event}'", s)
    return s


def logic_overrides(enabled=None, plugins=()):
    """The remake's own logic from data/rando/logic/*.json (one file per plugin), applied in file-name order:
    {
      "helpers": {"helper_name": "rule"},                          add or replace OoTR LogicHelpers
      "regions": {"Region Name": {"locations": {"Loc": "rule" or null (remove)},
                                  "events": {...}, "exits": {...}}},  change rules inside existing regions
      "new_regions": [{"region_name": ..., "file": "Overworld.json", ...OoTR region fields}],
      "new_locations": {"Loc": {"type": "Chest", "vanilla_item": "Rupees (5)",
                                "filter_tags": ["Kokiri Forest", "Forest Area", "Chests"],
                                "scene": null, "default": null}}   new OoTR locations (place them with a region rule)
    }
    Rules are OoTR rule strings, and the boss-defeat rewrite applies to them too."""
    out = []
    for path in sorted(glob.glob(os.path.join(LOGIC_DIR, "*.json"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        if enabled is not None and stem in plugins and stem not in enabled:
            continue  # a plugin's logic only with that plugin (config/plugins.json)
        d = json.load(open(path, encoding="utf-8"))
        d["_file"] = os.path.basename(path)
        out.append(d)
    return combine_overrides(out)


def override_keys(overrides):
    """{(section, region or "", key): [file, ...]} for every rule key the override files set."""
    keys = {}
    for o in overrides:
        for k in o.get("helpers", {}):
            keys.setdefault(("helpers", "", k), []).append(o["_file"])
        for region, sections in (o.get("regions") or {}).items():
            for section, changes in (sections or {}).items():
                for k in changes:
                    keys.setdefault((section, region, k), []).append(o["_file"])
    return keys


def override_clashes(overrides=None):
    """Rule keys set by more than one logic file (logic_overrides joins them with "and"), as
    [(section, region, key, [files])]. The selftest checks this."""
    overrides = logic_overrides() if overrides is None else overrides
    return [(sec, reg, k, files) for (sec, reg, k), files in sorted(override_keys(overrides).items())
            if len(files) > 1]


def combine_overrides(overrides):
    """Two files setting the same rule both mean "the remake needs this too", so a later file's rule becomes
    "(earlier) and (later)" instead of quietly replacing it. Removing a rule (null) that another file sets is an
    error, and so are two different definitions of a helper with arguments."""
    seen = {}
    for o in overrides:
        for k, v in list(o.get("helpers", {}).items()):
            key = ("helpers", "", k)
            if key in seen and seen[key] != v:
                if v is None or seen[key] is None or "(" in k:
                    raise ValueError(f"logic files disagree on helper {k} ({o['_file']})")
                v = o["helpers"][k] = f"({seen[key]}) and ({v})"
            seen[key] = v
        for region, sections in (o.get("regions") or {}).items():
            for section, changes in (sections or {}).items():
                for k, v in list(changes.items()):
                    key = (section, region, k)
                    if key in seen and seen[key] != v:
                        if v is None or seen[key] is None:
                            raise ValueError(f"logic files disagree on {region} / {k}: one removes it "
                                             f"({o['_file']})")
                        v = changes[k] = f"({seen[key]}) and ({v})"
                    seen[key] = v
    return overrides


def _apply_section(target, changes):
    for k, v in changes.items():
        if v is None:
            target.pop(k, None)
        else:
            target[k] = v


def rewrite_logic(path, data, overrides=None):
    name = os.path.basename(path)
    overrides = logic_overrides() if overrides is None else overrides
    if name == "LogicHelpers.json":
        bridge, n = BRIDGE_VANILLA.subn(f"(bridge == 'vanilla' and '{LACS_EVENT}')", data["can_build_rainbow_bridge"])
        if n != 1:
            raise RuntimeError("OoTR's vanilla rainbow bridge rule changed: update tools/rando/world_settings.py")
        data["can_build_rainbow_bridge"] = bridge
        for o in overrides:
            _apply_section(data, o.get("helpers", {}))
        return {k: _rule(v) if isinstance(v, str) else v for k, v in data.items()}
    if isinstance(data, list):  # a region file
        names = {r.get("region_name") for r in data}
        for o in overrides:
            for r in o.get("new_regions", []):
                if r.get("file", "Overworld.json") == name and r["region_name"] not in names:
                    data.append({k: v for k, v in r.items() if k != "file"})
                    names.add(r["region_name"])
        for region in data:
            for o in overrides:
                for section, changes in (o.get("regions", {}).get(region.get("region_name")) or {}).items():
                    region.setdefault(section, {})
                    _apply_section(region[section], changes)
            for section in ("locations", "events", "exits"):
                if isinstance(region.get(section), dict):
                    region[section] = {k: _rule(v) if isinstance(v, str) else v for k, v in region[section].items()}
            if name == "Overworld.json" and region.get("region_name") == "Temple of Time":
                region.setdefault("events", {})[LACS_EVENT] = "is_adult and can_trigger_lacs"
    return data


def register_locations(overrides):
    """Add new_locations from the logic overrides to OoTR's location table and groups."""
    import LocationList
    for o in overrides:
        for loc, v in o.get("new_locations", {}).items():
            if loc in LocationList.location_table:
                continue
            tags = tuple(v.get("filter_tags", ()))
            LocationList.location_table[loc] = (v.get("type", "Chest"), v.get("scene"), v.get("default"), None,
                                               v.get("vanilla_item"), tags)
            for group in (v.get("type", "Chest"),) + tags:
                if group in LocationList.location_groups:
                    LocationList.location_groups[group].append(loc)


def startable(name):
    """Whether a new file can start with OoTR item `name`. That's the hearts (the game-start sequence's life) or an
    item with a start routine (starting_actor)."""
    if name in HEART_ITEMS:
        return True
    try:
        return starting_actor(name, 1) is not None
    except Exception:  # noqa: BLE001 - an item the remake has no start routine for
        return False


def install_start_filter():
    """OoTR's random starting items (add_random_starting_items) come from ItemPool.configure_random_starting_items_pool,
    which leaves out what OoTR itself can't start with (shop items). The remake also can't start with items that have
    no start routine (silver rupees, the Magic Bean Pack...), and starting_items_plan refuses those seeds ("no remake
    item to start with"). So we leave them out of the draw the same way.
    Same for Gold Skulltula Tokens while the seed needs every one that's left. OoTR's own count (ItemPool "Not enough
    available Gold Skulltula Tokens") leaves out randomly drawn starting items, so one drawn token would stop a seed
    that needs all 100 (OoTR itself stops there too)."""
    import ItemPool
    if getattr(ItemPool.configure_random_starting_items_pool, "remake_startable", False):
        return
    original = ItemPool.configure_random_starting_items_pool
    token, all_tokens = "Gold Skulltula Token", 100

    def pool(world, items, _original=original):
        drawn = (getattr(world, "randomized_starting_items", None) or {}).get(token, 0)
        need = (getattr(world, "max_progressions", None) or {}).get(token, 0)
        return [i for i in _original(world, items) if startable(i)
                and not (i == token and need > all_tokens - 1 - drawn)]
    pool.remake_startable = True
    ItemPool.configure_random_starting_items_pool = pool


def install_logic(enabled=None, plugins=()):
    """Makes OoTR read its rules through rewrite_logic. Call it before building worlds."""
    import RuleParser
    import Utils
    import World
    install_start_filter()  # random starting items, only what a new file can start with
    if getattr(Utils.read_logic_file, "remake", False):
        return
    original = Utils.read_logic_file
    overrides = logic_overrides(enabled, plugins)
    register_locations(overrides)

    def read(path):
        return rewrite_logic(path, original(path), overrides)
    read.remake = True
    for module in (Utils, RuleParser, World):
        module.read_logic_file = read
    RuleParser.rule_aliases.clear()  # helpers reload through the rewrite on the next parse
    RuleParser.nonaliases.clear()


# World settings
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
GAME_START = "Sequence/SetPouchAndStatusForGameStart.module.ainb"
HEART_OFFSETS = (0x11C8, 0x11E8)  # GAME_START's PlayerStatus.Life and MaxLife (i32, quarter hearts; 12)
TRIALS = ("Forest", "Fire", "Water", "Shadow", "Spirit", "Light")
BEAN_SOILS = ("12044463103654268862", "18350441421271687772", "14429198438059673734", "10857724324414230743",
              "17500344509500247365", "6833516270248855649", "9976156629905609191", "6092667454768667954",
              "176409868210268833", "5234955674857122897", "17092212646454540992")
SCARECROW_SPOTS = ("DEATH_MOUNTAIN_CRATER_01", "DEATH_MOUNTAIN_CRATER_02", "DODONGO_CAVERN_01", "FIRE_TEMPLE_01",
                   "FOREST_TEMPLE_01", "GERUDO_FORTRESS_01", "GERUDO_TRAINING_GROUND_01", "LAKE_HYLIA_01",
                   "LAKE_HYLIA_02", "LAKE_HYLIA_03", "SACRED_FOREST_MEADOW_01", "SHADOW_TEMPLE_01", "SHADOW_TEMPLE_02",
                   "SPIRIT_TEMPLE_01", "WATER_TEMPLE_01", "ZORA_FOUNTAIN_01")

# Settings the patcher applies: setting -> values it can make (the remake's own behaviour needs no change).
APPLIED = {
    "open_forest": ("closed", "closed_deku", "open"),
    "open_kakariko": ("closed", "zelda", "open"),  # zelda: the guard still takes the letter, logic is the same
    "open_door_of_time": ("stones_oot_sot", "open"),
    "trials": tuple(range(7)),
    "plant_beans": (False, True),
    "scarecrow_behavior": ("vanilla", "free"),
    "start_with_rupees": (False, True),
    "starting_hearts": tuple(range(1, 21)),
    "chicken_count": tuple(range(1, 8)),  # 0 would read as both "not started" and "done"
    "big_poe_count": tuple(range(1, 11)),
}
# TODO: these are applied but I haven't seen them working in game yet.
UNTESTED = {("open_forest", "closed_deku"), ("open_forest", "open"), ("open_kakariko", "open"),
            ("open_door_of_time", "open"), ("plant_beans", True), ("scarecrow_behavior", "free"),
            ("start_with_rupees", True), ("chicken_count", "any"), ("big_poe_count", "any"),
            ("trials", "any"), ("starting_hearts", "any")}
# TODO: the patcher can't apply these settings yet, so they have to describe the remake as it is.
REMAKE_ONLY = {
    "free_bombchu_drops": False, "zora_fountain": "closed", "gerudo_fortress": "normal", "bridge": "vanilla",
    "lacs_condition": "vanilla", "shuffle_ganon_bosskey": "vanilla", "skip_child_zelda": False,
    "complete_mask_quest": False, "starting_age": "child", "no_escape_sequence": False,
    "dungeon_shortcuts_choice": "off", "mq_dungeons_mode": "vanilla", "empty_dungeons_mode": "none",
    "triforce_hunt": False, "starting_tod": "default",
    "damage_multiplier": "normal", "deadly_bonks": "none", "junk_ice_traps": "off",
}
HEART_ITEMS = ("Piece of Heart", "Heart Container")
# Starting with 1 or 2 hearts. Ship of Harkinian's RSK_STARTING_HEARTS and the 3DS randomizer's StartingHearts go
# down to 1, but OoTR's starting_hearts stops at 3 (SettingsList.py).
# OoTR runs with 3, since its validation, pool and settings string can't take less (the string reads 1 back as 5).
# The player's value is kept on OoTR's Settings as LOW_HEARTS (generate.make_settings). Then we do what SoH
# (item_pool.cpp) and the 3DS randomizer (ReplaceMaxItem(HEART_CONTAINER, 2 - StartingHearts)) do:
#   - 3 - n Heart Containers replace junk in the pool, so the maximum stays 20
#   - OoTR's heart count (State.heart_count, pieces // 4 + 3) counts 3 - n fewer. It's the only heart logic: the
#     'hearts' bridge, LACS and Ganon's boss key, which the game checks as PlayerStatus.MaxLife.
#   - its goals (World.set_goals, the hearts goal's minimum) see n
#   - the new file's Life and MaxLife are 4 n (world_plan)
LOW_HEARTS = "remake_low_starting_hearts"
LOW_HEARTS_MIN = 1


def starting_hearts(settings):
    """The hearts a new file starts with. That's the player's value, even below OoTR's minimum of 3 (LOW_HEARTS)."""
    return getattr(settings, LOW_HEARTS, None) or settings.starting_hearts


def heart_deficit(settings):
    """Heart Containers added to the pool (and hearts OoTR's count drops) for a start below 3."""
    return 3 - getattr(settings, LOW_HEARTS) if getattr(settings, LOW_HEARTS, None) else 0


def add_heart_containers(world, ItemFactory):
    """3 - n Heart Containers take the place of the first junk items in the pool (OoTR's junk, ItemPool
    junk_pool_base). The pool's order comes from the seed, so the seed still reproduces. Returns the items replaced."""
    k = heart_deficit(world.settings)
    if not k:
        return []
    from ItemPool import junk_pool_base
    junk = {name for name, _ in junk_pool_base}
    spots = [i for i, it in enumerate(world.itempool) if it.name in junk and not it.advancement][:k]
    if len(spots) < k:
        raise ValueError(f"starting_hearts {starting_hearts(world.settings)}: the item pool has {len(spots)} junk "
                         f"items for the {k} Heart Containers that keep 20 hearts reachable")
    replaced = [world.itempool[i].name for i in spots]
    for i in spots:
        world.itempool[i] = ItemFactory("Heart Container", world)
    world.remake_low_hearts = {"hearts": starting_hearts(world.settings), "containers_added": k, "replaced": replaced}
    return replaced


def install_low_hearts():
    """OoTR hooks for a start below 3 hearts, no effect on any other seed. State.heart_count counts 3 - n fewer and
    World.set_goals sees n hearts."""
    import State
    import World
    if getattr(State.State.heart_count, "remake_low_hearts", False):
        return
    count = State.State.heart_count

    def heart_count(self):
        return count(self) - heart_deficit(self.world.settings)
    heart_count.remake_low_hearts = True
    State.State.heart_count = heart_count
    goals = World.World.set_goals

    def set_goals(self):
        low = getattr(self.settings, LOW_HEARTS, None)
        if not low:
            return goals(self)
        shown, self.settings.starting_hearts = self.settings.starting_hearts, low
        try:
            return goals(self)
        finally:
            self.settings.starting_hearts = shown
    World.World.set_goals = set_goals


# Big Poe buyer (Npc_Hylia_048_BottleShop). Coupon compares with 400 decide the bottle sale and its texts.
BIG_POE_REMAKE = 5
BIG_POE_QUERIES = ("Event2", "Event21", "Event258", "Event259", "Event261", "Event262", "Event265")
# Values the generator and patcher handle with no world-settings edit of their own (chests, scenes, the item pool).
SUPPORTED = {
    "shuffle_map": ("remove", "vanilla"), "shuffle_compass": ("remove", "vanilla"),
    "shuffle_smallkeys": ("vanilla",), "shuffle_bosskeys": ("vanilla",), "shuffle_hideoutkeys": ("vanilla",),
    "misc_hints": ([],), "shuffle_song_items": ("song",),
}
# Entrances: no edit moves them unless the entrances plugin is enabled.
REMAKE_ONLY.update({
    "shuffle_interior_entrances": "off", "shuffle_hideout_entrances": False, "shuffle_grotto_entrances": False,
    "shuffle_dungeon_entrances": "off", "shuffle_bosses": "off", "shuffle_ganon_tower": False,
    "shuffle_overworld_entrances": False, "shuffle_gerudo_valley_river_exit": False, "owl_drops": False,
    "warp_songs": False, "spawn_positions": [],
    "fast_chests": False,  # my rule: chests always play their own full opening
    "adult_trade_start": ["Pocket Egg"],  # the remake's trade sequence starts at the Pocket Egg
    "world_count": 1,  # multiworld needs items sent between games while playing
})
STARTING = ("starting_items", "starting_equipment", "starting_songs", "starting_inventory")


def check_settings(settings, owned=()):
    """Problems with resolved OoTR settings (empty means the patcher can make this world). Settings in `owned` get
    checked by the parity plugin that owns them (tools/rando/parity/)."""
    problems = []
    for name, ok in APPLIED.items():
        if name in owned:
            continue
        v = getattr(settings, name, None)
        if v not in ok:
            problems.append(f"{name} = {v!r}: the patcher can make {', '.join(map(repr, ok))}")
    for name, ok in SUPPORTED.items():
        if name in owned:
            continue
        v = getattr(settings, name, None)
        if v not in ok:
            problems.append(f"{name} = {v!r}: supported: {', '.join(map(repr, ok))}")
    for name, want in REMAKE_ONLY.items():
        if name in owned:
            continue
        v = getattr(settings, name, want)
        if v != want:
            problems.append(f"{name} = {v!r}: not supported yet, must be {want!r} (the remake's own behaviour)")
    problems += unhandled(settings, owned)
    for name in STARTING:
        value = getattr(settings, name, None)
        if name == "starting_items" and value:
            # hearts go through the game-start sequence, the rest through the opening scene (world_plan)
            value = [k for k, v in value.items() if k not in HEART_ITEMS and getattr(v, "count", v)
                     and starting_actor(k, getattr(v, "count", v)) is None]
        if value:
            problems.append(f"{name}: no remake item to start with for {', '.join(map(str, value))}")
    return problems


# Seed settings the generator handles for any value: OoTR's own fill, pool, hints, tricks and starting items.
GENERATOR_ANY = {
    "create_spoiler", "logic_rules", "reachable_locations", "disabled_locations", "allowed_tricks",
    "advanced_allowed_tricks", "item_pool_value", "one_item_per_dungeon", "hints", "hint_dist", "hint_dist_user",
    "shuffle_kokiri_sword", "shuffle_ocarinas", "shuffle_dungeon_rewards", "add_random_starting_items",
    "random_starting_items_exclude", "random_starting_items_count", "start_with_consumables", "randomize_settings",
    "plandomized_locations", "show_seed_info", "user_message", "password_lock", "clearer_hints", "item_hints",
}


def unhandled(settings, owned=()):
    """Default-deny: a seed setting no code handles has to stay at OoTR's default.
    No code handles it means no enabled plugin owns it, world_settings doesn't apply or pin it and the generator
    doesn't take it as is. Otherwise OoTR's logic would assume something the patch doesn't make, like shuffled
    entrances with nothing moved."""
    from SettingsList import SettingInfos
    out = []
    disabled = getattr(settings, "_disabled", set())  # switched off by another setting (OoTR zeroes those)
    for name, info in SettingInfos.setting_infos.items():
        if (not info.shared or name in owned or name in APPLIED or name in REMAKE_ONLY or name in GENERATOR_ANY
                or name in SUPPORTED
                or name in STARTING or name in disabled):
            continue
        v = getattr(settings, name, info.default)
        if v != info.default:
            out.append(f"{name} = {v!r}: not supported yet, only OoTR's default {info.default!r} (PARITY.md)")
    return out


AMMO = {"Deku Sticks": "Item_DekuStick", "Deku Nuts": "Item_DekuNut", "Bombs": "Item_Bomb",
        "Arrows": "Item_Arrow_Normal", "Deku Seeds": "Item_DekuSeed", "Bombchus": "Item_Bombchu"}


def starting_actor(name, count):
    """(remake actor, number) a new file starts with for OoTR's starting item `name` x count, or None."""
    import json
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    prog = json.load(open(os.path.join(here, "config", "progressive.json"), encoding="utf-8"))["items"]
    items = json.load(open(os.path.join(here, "config", "item_map.json"), encoding="utf-8"))["items"]
    if name in prog:  # the tier for that many copies
        tiers = prog[name]["tiers"]
        return tiers[min(count, len(tiers)) - 1], 1
    if name in AMMO:
        return AMMO[name], count
    if name in items:  # what that item's pickup puts in the inventory (a shield, not its chest version)
        pouch = json.load(open(os.path.join(here, "data", "rando", "pouch_actors.json"), encoding="utf-8"))["actors"]
        actor, num = pouch.get(items[name], [items[name], 1])
        return actor, num
    return None


# starting_actor adds one pickup, so starting with 10 Gold Skulltula Tokens only gives 1. The Skulltula House and
# the other token readers use PouchData.Item_Token_Gold.StockNum (_story_conditions.TOKENS). So we keep the pickup,
# wait for it to land (write_read_check.SETTLE_FRAMES), then write the starting count to that row (count_sets).
COUNT_ROWS = {"Gold Skulltula Token": "PouchData.Item_Token_Gold.StockNum"}
# Starting items OoTR counts in copies, each a pouch slot of its own (OoTR's StartingItems "bottle", available=3,
# is three empty bottles). One add per copy, the same as each bottle found adds one. A single add for two or three
# gives you just one.
COPIES = ("Bottle",)


def count_sets(name, count):
    """[(game-data Int row, value)] a new file sets after adding OoTR's starting item `name` x count (COUNT_ROWS)."""
    return [(COUNT_ROWS[name], int(count))] if name in COUNT_ROWS and count else []


def count_steps(sets):
    """Event nodes (no "next") that set each (row, value) of count_sets once the pouch adds before them have landed.
    That's the game's settle wait (write_read_check.settle), then GameDataActor.EventTriggerSetGameDataInt per row."""
    if not sets:
        return []
    from write_read_check import SETTLE_FRAMES
    wait = {"actor": "GameSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": SETTLE_FRAMES}}
    return [wait] + [
        {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
         "params": {"GameDataName": row, "Value": int(v), "Index": -1}} for row, v in sets]


def starting_adds(name, count):
    """[(remake actor, number)] a new file adds for OoTR's starting item `name` x count, in order.
    A progressive item adds every tier up to its count, like playing finds them. If you only add the top tier, two
    Progressive Hookshots add just the Longshot and IsGet.Item_Hookshot stays false. The engine sets that flag on
    the pouch add and 20+ flows read it, the Gerudo guards' jail choice and Dampe's race among them. A tier with its
    own give entry adds what that entry adds (progressive.GIVE "add", the Kokiri wallet's Item_Wallet_Small). COPIES
    add one per copy, and a COUNT_ROWS item adds one (its count gets set after, count_sets)."""
    import json
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    prog = json.load(open(os.path.join(here, "config", "progressive.json"), encoding="utf-8"))["items"]
    if name not in prog:
        got = starting_actor(name, count)
        if got and name in COPIES:
            return [got] * max(int(count), 1)
        return [got] if got else []
    import sys
    if os.path.join(here, "tools") not in sys.path:
        sys.path.insert(0, os.path.join(here, "tools"))
    import progressive
    tiers = prog[name]["tiers"][:min(count, len(prog[name]["tiers"]))]
    return [((progressive.GIVE.get(t) or {}).get("add", t), 1) for t in tiers]


def starting_items_plan(settings, world=None):
    """Plan sections that give OoTR's starting items when a new file starts.
    A new entry next to the game's pouch routines (GetPouchContent, which has a PouchSystemActor) adds them silently,
    the way vanilla adds songs (PouchSystemActor.EventTriggerAddOrRemovePouchContent, IsGetEvent off). The
    once-per-file opening scene (OpeningEvent:Opening_Introduction) calls it right after Navi's first story step,
    before the autosave."""
    gives = []
    items = {k: getattr(v, "count", v) for k, v in (getattr(settings, "starting_items", None) or {}).items()}
    for name, count in (getattr(world, "randomized_starting_items", None) or {}).items():  # random starting items
        items[name] = items.get(name, 0) + count
    if getattr(settings, "start_with_consumables", False):  # full sticks and nuts, as OoTR gives
        items["Deku Sticks"] = max(items.get("Deku Sticks", 0), 99)
        items["Deku Nuts"] = max(items.get("Deku Nuts", 0), 99)
    for name, count in sorted(items.items()):
        if name in HEART_ITEMS or not count:
            continue
        if starting_actor(name, count) is None:
            raise ValueError(f"no remake item to start with for {name}")
        for actor, num in starting_adds(name, count):
            gives.append({"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
                          "params": {"Actor": actor, "Num": num, "IsEquipDIrect": False, "IsGetEvent": False,
                                     "IsSetMessageTargetActorName": False}})
    gives += count_steps([s for name, count in sorted(items.items()) if name not in HEART_ITEMS
                          for s in count_sets(name, count)])
    if not gives:
        return []
    return [{"file": "GetPouchContent", "flowchart": "GetPouchContent", "add_entry": "Rando_StartingItems",
             "steps": gives},
            {"file": "OpeningEvent", "flowchart": "OpeningEvent", "add_graph": "Rando_Start",
             "nodes": {"give": {"call": "GetPouchContent:Rando_StartingItems", "next": "@Event31"}}, "start": "give"},
            {"file": "OpeningEvent", "flowchart": "OpeningEvent", "event": "Event8", "next": "Rando_Start_give"}]


def untested(settings):
    out = [f"starting item {k}" for k, v in (getattr(settings, "starting_items", None) or {}).items()
           if k not in HEART_ITEMS and getattr(v, "count", v)]
    for name in APPLIED:
        v = starting_hearts(settings) if name == "starting_hearts" else getattr(settings, name, None)
        if (name, v) in UNTESTED or ((name, "any") in UNTESTED and v != _VANILLA[name]):
            out.append(f"{name} = {v!r}")
    if getattr(settings, "big_poe_count", BIG_POE_REMAKE) == 10:  # OoTR's default, the buyer's own count is 5
        out.append("big_poe_count = 10 (the Big Poe buyer's bottle moved from the 5th to the 10th Poe)")
    return out


_VANILLA = {"open_forest": "closed", "open_kakariko": "closed", "open_door_of_time": "stones_oot_sot", "trials": 6,
            "plant_beans": False, "scarecrow_behavior": "vanilla", "start_with_rupees": False, "starting_hearts": 3,
            "chicken_count": 7, "big_poe_count": 10}


def world_plan(settings, world):
    """Patch plan sections for the resolved settings: {"gamedata": {...}, "events": [...], "binary": [...]}."""
    defaults, events, binary = {}, [], []
    s = getattr(world, "settings", settings)  # OoTR resolves random values (trials, counts) per world
    if s.open_forest in ("closed_deku", "open"):
        defaults["KokiriForest_Npc_Kokiri_007_Child_Blocker_00"] = False  # the forest exit
    if s.open_forest == "open":
        defaults["KokiriForest_Npc_Kokiri_Mido_Child_Blocker"] = False  # Mido, in front of the Deku Tree
    if s.open_kakariko == "open":
        defaults["Npc_Hylia_Soldier_003_GateOpen"] = True  # also opens the Happy Mask Shop, as the letter does
    if s.open_door_of_time == "open":
        defaults["Market_Child_TimeTempleDoor_Opened"] = True
    skipped = [t for t in TRIALS if world.skipped_trials.get(t)] if hasattr(world, "skipped_trials") else []
    if s.trials != 6:
        if len(skipped) != 6 - s.trials:
            raise ValueError(f"{s.trials} trials but OoTR skipped {skipped}")
        for t in skipped:
            defaults[f"InsideGanonCastle_Dungeon_BarrierRemove_{t}"] = True
            defaults[f"HavePlayedEvent.InsideGanonCastle_Dungeon_BarrierRemove_{t}"] = True
        defaults["InsideGanonCastle_Dungeon_Barrier_Count"] = s.trials
    if s.plant_beans:
        for h in BEAN_SOILS:
            defaults[f"IsPlantedMagicBean_SmallFarm.{h}"] = True
    if s.scarecrow_behavior == "free":
        for spot in SCARECROW_SPOTS:
            defaults[f"Appear_SCARECROW_{spot}"] = True
    if s.start_with_rupees:
        # a full wallet like OoTR gives. The remake's wallets hold 200 / 500 / 1000 (their capacity rows), not OoTR's
        # 99 / 200 / 500, and starting wallet upgrades (added in the opening scene) raise it
        wallets = sum(getattr(v, "count", v) for k, v in (getattr(s, "starting_items", None) or {}).items()
                      if k == "Progressive Wallet")
        defaults["PlayerStatus.CurrentRupee"] = (200, 500, 1000)[min(int(wallets), 2)]
    if s.chicken_count != 7:
        defaults["Npc_Hylia_049_Child_HowManyCuccos"] = s.chicken_count
        for ev in ("Event3", "Event82"):
            events.append({"file": "Minigame_CatchCucco", "flowchart": "Minigame_CatchCucco", "event": ev,
                           "param": "Value", "value": s.chicken_count})
    if s.big_poe_count != 10:  # Navi's line when the bottle holds that many
        events.append({"file": "Dm_SY_InsertBottle", "flowchart": "Dm_SY_InsertBottle", "event": "Event76",
                       "param": "Value", "value": s.big_poe_count})
    if s.big_poe_count != BIG_POE_REMAKE:
        # the buyer gives the bottle on the sale made with GhostShop_CouponNum == 400 (100 per Big Poe, so the 5th).
        # Every "== 400" in his scene moves to the count before the N-th sale, and the gold rupee at 900 stays
        for ev in BIG_POE_QUERIES:
            events.append({"file": "Npc_Hylia_048_BottleShop", "flowchart": "Npc_Hylia_048_BottleShop", "event": ev,
                           "param": "Value", "value": 100 * (s.big_poe_count - 1)})
    hearts = starting_hearts(s)  # below 3 too (LOW_HEARTS)
    if hearts != 3:
        for off in HEART_OFFSETS:  # PlayerStatus.Life and MaxLife, in quarter hearts
            binary.append({"file": GAME_START, "offset": off, "i32": 4 * hearts, "expect": 12})
    events += starting_items_plan(s, world)
    plan = {}
    if defaults:
        plan["gamedata"] = {"defaults": defaults}
    if events:
        plan["events"] = events
    if binary:
        plan["binary"] = binary
    if hearts != 3:  # read back (parity/_start_hearts.py): Life and MaxLife, and below 3 the containers added
        low = getattr(world, "remake_low_hearts", {})
        plan["_gaps"] = {"starting_hearts": {"hearts": hearts, "file": GAME_START, "offsets": list(HEART_OFFSETS),
                                             "containers_added": low.get("containers_added", 0),
                                             "replaced": low.get("replaced", [])}}
    return plan



def verify_starting(patch, out_dir, romfs=None):
    """Checks the built GetPouchContent:Rando_StartingItems against the seed's settings_used.json, returns [problem,
    ...]. It has to add every starting item the way starting_adds says, in order (each tier up to its count for a
    progressive item, one add per copy for COPIES). And it has to set each COUNT_ROWS row to the item's count after a
    settle wait that follows its add."""
    import json
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        cfg = json.load(open(os.path.join(out_dir, "settings_used.json"), encoding="utf-8"))["settings"]
    except (OSError, ValueError, KeyError):
        return []
    items = {k: v for k, v in (cfg.get("starting_items") or {}).items() if k not in HEART_ITEMS and v}
    prog = json.load(open(os.path.join(here, "config", "progressive.json"), encoding="utf-8"))["items"]
    if not any(k in prog or k in COPIES or k in COUNT_ROWS for k in items):
        return []
    import sys
    if os.path.join(here, "tools") not in sys.path:
        sys.path.insert(0, os.path.join(here, "tools"))
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(romfs or __import__("romtools").longshot_romfs(), os.path.join(here, "original"), [patch])
    fc = next(f for f in Evfl(fs.read("Event/EventFlow/GetPouchContent.bfevfl.zs")).flowcharts
              if f["name"] == "GetPouchContent")
    ep = fc["entry_points"].get("Rando_StartingItems")
    if ep is None:
        return ["GetPouchContent: no Rando_StartingItems entry"]
    got, i, seen, line = [], ep["main"], set(), []
    while i is not None and i != 0xFFFF and i < len(fc["events"]) and i not in seen:
        seen.add(i)
        e = fc["events"][i]
        p = {k: v.get("value") for k, v in (((e.get("params") or {}).get("items")) or {}).items()}
        act = fc["actors"][e["actor"]]["actions"][e["action"]] if e["type"] == "action" else e["type"]
        line.append((act, p))
        if "Actor" in p:
            got.append((p["Actor"], p.get("Num")))
        i = e.get("next")
    bad = []
    from write_read_check import SETTLE_FRAMES
    for name, count in sorted(items.items()):
        if name in COPIES:
            want = starting_adds(name, count)
            n_ = sum(1 for g in got if g == want[0])
            if n_ != len(want):
                bad.append(f"starting {name} x{count}: Rando_StartingItems adds {want[0][0]} {n_} time(s), want "
                           f"{len(want)}")
        for row, v in count_sets(name, count):
            actor = starting_adds(name, count)[0][0]
            add = next((k for k, (a, p) in enumerate(line) if p.get("Actor") == actor), None)
            wait = next((k for k, (a, p) in enumerate(line) if add is not None and k > add and a == "EventWait"
                         and int(p.get("Frames") or 0) >= SETTLE_FRAMES), None)
            sets = [(k, p.get("Value")) for k, (a, p) in enumerate(line)
                    if a == "EventTriggerSetGameDataInt" and p.get("GameDataName") == row]
            if add is None or wait is None or [s for k, s in sets if k > wait] != [v] or len(sets) != 1:
                bad.append(f"starting {name} x{count}: Rando_StartingItems doesn't add {actor}, wait "
                           f"{SETTLE_FRAMES}+ frames and then set {row} to {v} (adds at {add}, wait at {wait}, "
                           f"sets {sets})")
    for name, count in sorted(items.items()):
        if name not in prog:
            continue
        want = starting_adds(name, count)
        it = iter(got)
        if not all(w in it for w in want):  # in order, as a subsequence
            bad.append(f"starting {name} x{count}: Rando_StartingItems adds {[g for g in got if g[0] in prog[name]['tiers'] or g[0] == 'Item_Wallet_Small']}, want {want}")
    return bad
