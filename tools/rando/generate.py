"""Generate a randomized seed for the remake with OoT Randomizer's own generator (vendor/ootr, MIT).

usage: python tools/rando/generate.py OUT_DIR [--seed SEED] [--settings config/rando_settings.json]
then:  python tools/make_patch.py ROMFS OUT_DIR/patch OUT_DIR/plan.json
       python tools/install.py install ROMFS OUT_DIR/patch

OoTR builds the world from its logic (tricks from config/tricks.json, all off by default), fills it so the seed
is always beatable, and writes its playthrough, hints and spoiler. On top of that, for the remake:
- Only locations the patcher can change take part: chests paired in data/rando/chest_map.json, any item.
  "group" chests (paired in order, which is which unknown) get the rule "every chest of the group is reachable"
  (one OoTR event per chest, under its own rule), so the real chest is always reachable when logic says so.
  Every other location is locked to its vanilla item before the fill and taken out of OoTR's item pool, so logic
  sees the world exactly as the remake has it.
- Progressive items never go into a chest that runs its own story or minigame scene (Dampe's race, Navi's
  tutorial...), since the progressive scene would replace it.
- The placements become a patch plan (OUT_DIR/plan.json): remake chest -> remake actor (config/item_map.json) or
  progressive item name (the patcher adds the "give the right tier" scenes).
Writes OUT_DIR/plan.json, OUT_DIR/spoiler.json (OoTR's spoiler log) and OUT_DIR/seed.json (summary).
"""
import argparse
import contextlib
import io
import json
import logging
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "vendor", "ootr"))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world_settings  # noqa: E402
import no_savewarp  # noqa: E402
import no_vanilla  # noqa: E402
import progress  # noqa: E402  (tools/progress.py: the app's progress bar, prints only when the app asks)

ITEM_MAP = json.load(open(os.path.join(HERE, "config", "item_map.json"), encoding="utf-8"))
PROGRESSIVE = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]
CHEST_RULES = json.load(open(os.path.join(HERE, "config", "chest_rules.json"), encoding="utf-8"))
LOCATIONS = json.load(open(os.path.join(HERE, "config", "rando_locations.json"), encoding="utf-8"))
NOT_ITEM_CHECKS = ("Event", "Drop", "Hint", "HintStone")


class SeedError(Exception):
    pass


# Each stone reads its placement's GOSSIP_<AREA>_NN label in EventFlowMsg/GossipStone.msbt. A label can name a
# different area than the stone's actual level, grottos for example. The area and name order here are only a
# fallback. With the hints plugin on, gossip_text uses the exact OoTR-to-remake pairing from
# data/rando/hints_stones.json instead.
GOSSIP_AREAS = {"KF": "KOKIRI_FOREST", "LW": "LOST_WOOD", "SFM": "SACRED_FOREST_MEADOW", "HF": "HYRULE_FIELD",
                "HC": "HYRULE_CASTLE", "ToT": "HYRULE_MARKET", "Kak": "KAKARIKO_VILLAGE", "Graveyard": "GRAVEYARD",
                "DMT": "DEATH_MOUNTAIN_TRAIL", "DMC": "DEATH_MOUNTAIN_CRATER", "GC": "GORON_CITY", "ZR": "ZORA_RIVER",
                "ZD": "ZORA_DOMAIN", "ZF": "ZORA_FOUNTAIN", "LH": "LAKE_HYLIA", "GV": "GERUDO_VALLEY",
                "Colossus": "DESERT_COLOSSUS", "Dodongos Cavern": "DODONGO_CAVERN"}
# Event112 asks if Link has the Mask of Truth and Event25 asks if he's wearing it (case 0 yes, case 1 no). For
# hints that don't need the mask, case 1 goes to Event6. In "agony" mode Event112 asks for the Stone of Agony
# instead and Event25 takes the no-mask route.
HINTS_AGONY = [{"file": "GossipStone", "flowchart": "GossipStone", "event": "Event112", "param": "Actor",
                "value": "Item_AgonyStone"},
               {"file": "GossipStone", "flowchart": "GossipStone", "event": "Event25", "case": 1, "next": "Event6"}]
HINTS_ALWAYS = [{"file": "GossipStone", "flowchart": "GossipStone", "event": "Event112", "case": 1, "next": "Event6"},
                {"file": "GossipStone", "flowchart": "GossipStone", "event": "Event25", "case": 1, "next": "Event6"}]
# Event6 (the stone's talk opening) goes on to Event90, whose first-talk branch says the Mask of Truth lines ("Now
# there's a mask I haven't seen for a long time.") before the hint at Event18. Without the mask those lines are
# wrong, so the opening goes straight to the hint (Kaepora 1f3a4a6, seen in game).
STONE_SKIP_MASK_LINES = {"file": "GossipStone", "flowchart": "GossipStone", "event": "Event6", "next": "Event18"}
HINTS_AGONY.append(STONE_SKIP_MASK_LINES)
HINTS_ALWAYS.append(STONE_SKIP_MASK_LINES)


def hint_text(text, width=48):
    """OoTR hint text (#...# marks coloured words) -> plain text in lines of about `width` characters."""
    words, lines, line = text.replace("#", "").split(), [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}" if line else w
    return "\n".join(lines + [line] if line else lines)


def gossip_text_ops(gossip_stones):
    by_area = {}
    for name in gossip_stones:
        by_area.setdefault(name.split(" (")[0], []).append(name)
    ops = []
    for area, names in sorted(by_area.items()):
        label_area = GOSSIP_AREAS.get(area)
        if not label_area:
            raise SeedError(f"no remake Gossip Stones for OoTR's {area}")
        for i, name in enumerate(sorted(names), 1):
            ops.append({"lang": "*", "file": "EventFlowMsg/GossipStone.msbt", "label": f"GOSSIP_{label_area}_{i:02d}",
                        "text": hint_text(gossip_stones[name]["text"]), "note": name})
    return ops


def ootr():
    with contextlib.redirect_stdout(io.StringIO()):  # OoTR prints hint-table notes on import
        import Main  # noqa: F401
    import Main
    import Goals
    from Fill import ShuffleError
    from Item import ItemFactory
    from Settings import Settings
    from SettingsList import SettingInfos
    return Main, Goals, ShuffleError, ItemFactory, Settings, SettingInfos


def remake_item(item):
    """OoTR item name -> what the plan puts in a remake chest."""
    if item in PROGRESSIVE:
        return item
    if item in ITEM_MAP["items"]:
        return ITEM_MAP["items"][item]
    if item in ITEM_MAP["junk_for"]:
        return ITEM_MAP["junk_for"][item]
    raise SeedError(f"no remake item for OoTR's {item!r} (config/item_map.json)")


DUNGEON_ITEM_SETTING = {"Small Key": "shuffle_smallkeys", "Boss Key": "shuffle_bosskeys", "Map": "shuffle_map",
                        "Compass": "shuffle_compass"}


def prefilled(vanilla_item, settings):
    """OoTR places this location's vanilla item itself (a dungeon item that stays vanilla), so there's nothing to
    exclude."""
    kind = vanilla_item.split(" (")[0]
    key = DUNGEON_ITEM_SETTING.get(kind)
    return bool(key) and settings.get(key) == "vanilla"


def settings_name(path):
    """A settings file the way error messages name it. That's relative to the randomizer's folder when it's inside it,
    else its full path (not "../../../Documents/x.json")."""
    if not path:
        return "settings"
    try:
        rel = os.path.relpath(path, HERE)
    except ValueError:  # another drive than the randomizer's
        rel = os.pardir
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return os.path.abspath(path).replace(os.sep, "/")
    return rel.replace(os.sep, "/")


# Entries here go into OoTR's disabled_locations and can only hold junk. The list is empty. Dampe's race checked
# for the Hookshot in the pouch before counting a finish, but the race patch (tools/rando/parity/_chests_dampe.py)
# made both prizes valid checks. Checks the remake doesn't have at all are disabled by plugins, chests.before_build
# for example.
REMAKE_DISABLED = ()


def register_remake_tricks():
    """Registers the remake's own tricks (data/rando/remake_glitch_tricks.json, parity/glitches.py) as OoTR tricks, so
    OoTR's settings check accepts their names in allowed_tricks and Main sets their logic flags. Every one is off."""
    import SettingsListTricks
    from SettingsList import SettingInfos
    path = os.path.join(HERE, "data", "rando", "remake_glitch_tricks.json")
    if not os.path.exists(path):
        return
    info = SettingInfos.setting_infos["allowed_tricks"]
    for name, t in json.load(open(path, encoding="utf-8"))["tricks"].items():
        text = f"Remake glitch: {t['name']}"
        if text not in SettingsListTricks.logic_tricks:
            SettingsListTricks.logic_tricks[text] = {"name": name, "tags": ("Remake Glitches",),
                                                     "tooltip": t.get("description", "")}
        if name not in info.choice_list:
            info.choices[name] = text
            if isinstance(info.choice_list, list):
                info.choice_list.append(name)
            else:
                info.choice_list = list(info.choice_list) + [name]
    # Logic Rules "Glitched (remake glitches)". parity/glitches.py resolve_settings turns it into glitchless logic plus
    # the remake's glitch tricks before OoTR reads it. It's appended to OoTR's value list, so the settings string of
    # every other value stays as it was (same 2 bits), and it shows between Glitchless and No Logic.
    info = SettingInfos.setting_infos["logic_rules"]
    if "remake_glitched" not in info.choice_list:
        info.choices = {k: v for k, v in list(info.choices.items())[:-1]} | {
            "remake_glitched": "Glitched (remake glitches)"} | dict(list(info.choices.items())[-1:])
        info.choice_list = list(info.choice_list) + ["remake_glitched"]
        info.disable["remake_glitched"] = info.disable.get("glitchless", {})  # OoTR's N64 glitch tricks stay off


def remake_tricks():
    """{name: trick} of data/rando/remake_glitch_tricks.json (the remake's glitch tricks)."""
    path = os.path.join(HERE, "data", "rando", "remake_glitch_tricks.json")
    return json.load(open(path, encoding="utf-8"))["tricks"] if os.path.exists(path) else {}


def trick_toggles(cfg, where="settings"):
    """The remake's glitch tricks given one by one ("logic_remake_glitch_jsc": true, the way the app's Detailed Logic >
    Remake glitches section writes them) go into allowed_tricks, where OoTR takes tricks."""
    names = [k for k in cfg if k.startswith("logic_remake_glitch_")]
    if not names:
        return cfg
    known = remake_tricks()
    tricks = list(cfg.get("allowed_tricks") or [])
    for k in names:
        v = cfg.pop(k)
        if k not in known:
            import difflib
            near = difflib.get_close_matches(k, sorted(known), n=1)
            raise SeedError(f"{where}: {k}: not a remake glitch trick" + (f" (did you mean {near[0]}?)" if near else ""))
        if not isinstance(v, bool):
            raise SeedError(f"{where}: {k} = {v!r}: true or false")
        if v and k not in tricks:
            tricks.append(k)
        elif not v and k in tricks:
            tricks.remove(k)
    cfg["allowed_tricks"] = tricks
    return cfg


def reset_disabled(d):
    """Settings that another setting's value turns off take their "disabled" default, as OoTR's GUI does. Otherwise a
    settings file over config/rando_settings.json (the app's triforce hunt, say) would clash with the base file's
    Ganon's boss key, which triforce hunt turns off."""
    from SettingsList import SettingInfos, get_settings_from_section, get_settings_from_tab
    infos = SettingInfos.setting_infos
    for _ in range(5):  # a removed value can itself have turned others on or off
        changed = False
        for name, value in list(d.items()):
            info = infos.get(name)
            if info is None or not info.disable or isinstance(value, (list, dict)):
                continue
            for option, what in info.disable.items():
                neg = isinstance(option, str) and option.startswith("!")
                if (value == (option[1:] if neg else option)) == neg:
                    continue
                off = list(what.get("settings", []))
                off += [n for sec in what.get("sections", []) for n in get_settings_from_section(sec)]
                off += [n for tab in what.get("tabs", []) for n in get_settings_from_tab(tab)]
                for other in off:
                    if other in d and other in infos and d[other] != infos[other].disabled_default:
                        del d[other]  # OoTR then gives it its disabled default (which may be a hidden value)
                        changed = True
        if not changed:
            return


def make_settings(Settings, cfg, seed, excluded, path=None):
    """OoTR Settings from a settings dict. Keys starting with "remake_" are the remake's own settings (features OoTR
    doesn't have, grass drops for example). They skip OoTR's validation and are kept on settings.remake for plugins."""
    register_remake_tricks()
    remake = {k: v for k, v in cfg.items() if k.startswith("remake_")}
    d = {k: v for k, v in cfg.items() if not k.startswith("remake_")}
    from SettingsList import validate_settings
    reset_disabled(d)
    low_hearts = d.get("starting_hearts")  # 1 or 2: below OoTR's minimum, OoTR runs with 3 (world_settings.LOW_HEARTS)
    if isinstance(low_hearts, int) and not isinstance(low_hearts, bool) and \
            world_settings.LOW_HEARTS_MIN <= low_hearts < 3:
        d["starting_hearts"] = 3
    else:
        low_hearts = None
    try:
        validate_settings(d)  # OoTR's own check: names, types, allowed values
    except (TypeError, ValueError) as e:
        raise SeedError(f"{settings_name(path)}: {e}")
    tricks = json.load(open(os.path.join(HERE, "config", "tricks.json"), encoding="utf-8")).get("enabled", [])
    d.update(seed=str(seed), create_spoiler=True, create_patch_file=False, create_compressed_rom=False,
             create_uncompressed_rom=False, create_wad_file=False, patch_without_output=False,
             allowed_tricks=sorted(set(tricks) | set(d.get("allowed_tricks") or [])),  # the file's (the app's) too
             disabled_locations=sorted(set(excluded) | set(d.get("disabled_locations", [])) | set(REMAKE_DISABLED)))
    s = Settings(d)
    s.remake = remake
    if low_hearts:
        setattr(s, world_settings.LOW_HEARTS, low_hearts)
    return s


def lock_unpatchable(world, ItemFactory, keep):
    """Every empty location outside `keep` gets its vanilla item, taken out of the item pool, and is locked.
    Where OoTR's pool holds a stand-in from the item's group instead (a random bottle content for "Bottle", a
    trade item), the stand-in goes, as OoTR's own plando does with #Bottle / #AdultTrade / #ChildTrade."""
    from Plandomizer import item_groups
    pool, made = world.itempool, []
    for loc in world.get_locations():
        if loc.item is not None or loc.locked or loc.name in keep or loc.type in NOT_ITEM_CHECKS:
            continue
        if not loc.vanilla_item:  # nothing to keep (an empty pot...): junk, so OoTR puts nothing else there
            junk = next((it for it in pool if not it.advancement and not it.priority and not it.dungeonitem), None)
            if junk is None:
                raise SeedError(f"{loc.name}: no junk left to fill a location the patcher can't change")
            pool.remove(junk)
            world.push_item(loc, junk)
            loc.locked = True
            continue
        item = next((it for it in pool if it.name == loc.vanilla_item), None)
        if item is None:  # OoTR's pool holds a stand-in from the same group (bottle contents, trade items)
            group = next((g for g in ("Bottle", "AdultTrade", "ChildTrade") if loc.vanilla_item in item_groups[g]), None)
            stand_in = next((it for it in pool if group and it.name in item_groups[group]), None)
            if stand_in is not None:
                pool.remove(stand_in)
                item = ItemFactory(loc.vanilla_item, world)
                world.push_item(loc, item)
                loc.locked = True
                continue
        if item is not None:
            pool.remove(item)
        else:
            item = ItemFactory(loc.vanilla_item, world)
            made.append(f"{loc.name}: {loc.vanilla_item}")
        world.push_item(loc, item)
        loc.locked = True
    # Each fresh item replaces one the pool no longer needs, so we drop the same number of junk items.
    junk = [it for it in pool if not it.advancement and not it.priority and not it.dungeonitem]
    for _ in made:
        if not junk:
            raise SeedError("the item pool has no junk left to balance locked vanilla items")
        pool.remove(junk.pop())
    return made


def guard_progressive(world, chest_map, rewards, modes):
    """No progressive item where the patcher can't give one. That's chests whose own scene must keep running
    (location/story scenes) and chest types without a progressive scene. A chest scene runs on the small and big
    chests' families (progressive.scene_family), the Lens chest and the boss-key chest too."""
    import re
    import progressive
    loc_rx = CHEST_RULES["get_events"]["location"]
    guarded = []
    for name, v in chest_map.items():
        if modes[name] not in ("full", "group"):
            continue
        r = rewards[v["remake"]]
        ev = (r.get("extra") or {}).get("GetEventName")
        actor = {"Obj_TBox_A_06": "Obj_TBox_A_01", "Obj_TBox_A_06_NoBake": "Obj_TBox_A_01_NoBake"}.get(
            r["actor"], r["actor"])  # a check-actor chest holding one becomes the plain small chest (make_patch)
        dg = sys.modules.get("parity.dungeons")  # a story chest the item scene is routed into: its tier entry
        if dg is not None and v["remake"] in getattr(dg, "STORY_ROUTES", {}):  # (dungeons.story_prog)
            continue
        if actor == "Obj_TBox_A_01_memo11":  # (the Fairy Note chest plays its GetEventName: make_patch)
            continue
        if (ev and any(re.search(rx, ev) for rx in loc_rx)) or progressive.scene_family(actor) is None:
            loc = world.get_location(name)
            old = loc.item_rule
            loc.item_rule = (lambda location, item, old=old: item.name not in PROGRESSIVE and old(location, item))
            guarded.append(name)
    return guarded


def scene_locations():
    """{OoTR name: remake location id} for the scene locations we randomize (NPC, story, song), verified + testing."""
    match = {x["ootr"]: x for x in json.load(open(os.path.join(HERE, "data", "ootr_match.json"),
                                                  encoding="utf-8"))["ootr_locations"]}
    out = {}
    for name in LOCATIONS.get("verified", []) + LOCATIONS.get("testing", []):
        x = match.get(name)
        if not x or x["status"] != "exact" or len(x["remake"]) != 1:
            raise SeedError(f"config/rando_locations.json: {name} has no one-to-one remake location")
        out[name] = x["remake"][0]
    # Each give step can write one item. Two locations on the same step leave one prize out of every seed, as
    # happened with the two frog prizes.
    seen = {}
    for name, rid in out.items():
        if rid in seen:
            raise SeedError(f"config/rando_locations.json: {seen[rid]} and {name} both map to {rid}")
        seen[rid] = name
    return out


def apply_group_logic(world, chest_map, modes):
    """Every chest of a "group" (paired in order, real pairing unknown) needs all of the group reachable."""
    from Location import Location
    from Item import make_event_item
    groups = {}
    for name, m in modes.items():
        if m == "group":
            groups.setdefault(chest_map[name]["group"], []).append(name)
    for gid, members in list(groups.items()):
        # Chests already holding their vanilla item (dungeon items OoTR keeps vanilla) keep their own rule. The remake's
        # chests of that kind are the same set, so those items are exactly where OoTR thinks.
        if all(world.get_location(n).item is not None for n in members):
            del groups[gid]
            continue
        events = []
        for i, name in enumerate(sorted(members), 1):
            loc = world.get_location(name)
            ev = f"Remake group {gid} chest {i}"
            ev_loc = Location(f"{ev} from {loc.parent_region.name}", location_type="Event", parent=loc.parent_region)
            ev_loc.rule_string = loc.rule_string
            world.parser.parse_spot_rule(ev_loc)
            ev_loc.world = world
            loc.parent_region.locations.append(ev_loc)
            make_event_item(ev, ev_loc)
            events.append(ev)
        rule = " and ".join(f"'{e}'" for e in events)
        for name in members:
            loc = world.get_location(name)
            if loc.item is None:
                loc.rule_string = rule
                world.parser.parse_spot_rule(loc)
    return {g: len(m) for g, m in groups.items()}


def unknown_remake_settings(settings, mods):
    """Default-deny for the remake's own settings: a remake_* key no enabled plugin declares (REMAKE_SETTINGS,
    REMAKE_DEFAULTS or REMAKE_KEYS) is refused, so a misspelled key or one whose plugin isn't enabled can't silently
    leave its option off."""
    import difflib
    known = {no_vanilla.SETTING}
    for m in mods:  # REMAKE_INTERNAL is keys a tool writes that never show as app settings (remake_archipelago)
        for attr in ("REMAKE_SETTINGS", "REMAKE_DEFAULTS", "REMAKE_KEYS", "REMAKE_INTERNAL"):
            known |= set(getattr(m, attr, None) or ())
    out = []
    for k in sorted(getattr(settings, "remake", None) or {}):
        if k not in known:
            near = difflib.get_close_matches(k, sorted(known), n=1)
            out.append(f"{k}: no enabled plugin has this remake setting"
                       + (f" (did you mean {near[0]}?)" if near else " (is its plugin in config/plugins.json?)"))
    return out


ALIASES = os.path.join(HERE, "config", "setting_aliases.json")


def apply_aliases(cfg, where="settings"):
    """Turns settings under their familiar names into the remake keys. config/setting_aliases.json has Ship of
    Harkinian's or OoTR-style names for the remake's own settings, with their values. A file giving both names a
    different value is refused."""
    table = json.load(open(ALIASES, encoding="utf-8"))["names"]
    out, folds = {}, {}
    for k, v in cfg.items():
        a = table.get(k)
        if a is None:
            if k in out and out[k] != v:
                raise SeedError(f"{where}: {k} is given twice ({out[k]!r} and {v!r})")
            out[k] = v
            continue
        vals = a.get("values") or {}
        key = json.dumps(v) if not isinstance(v, str) else v
        if vals and key not in vals:
            raise SeedError(f"{where}: {k} takes {', '.join(vals)}, not {v!r}")
        val = vals[key] if vals else v
        if "item" in a:  # one entry of a table setting (the app's "Trap kinds: shock" -> remake_trap_weights)
            folds.setdefault(a["key"], (a.get("base") or {}, {}))[1][a["item"]] = val
            continue
        if a["key"] in out and out[a["key"]] != val:
            raise SeedError(f"{where}: {k} ({v!r}) and {a['key']} ({out[a['key']]!r}) disagree")
        out[a["key"]] = val
    for key, (base, items) in folds.items():  # over the table given whole (the older form), else the default table
        whole = out.get(key)
        if whole is not None:
            clash = [i for i, v in items.items() if i in whole and whole[i] != v]
            if not isinstance(whole, dict) or clash:
                raise SeedError(f"{where}: {key} ({whole!r}) and its entries {items!r} disagree")
        out[key] = dict(whole if whole is not None else base, **items)
    return out


def load_settings(path, preset=None):
    """A settings file's "settings", over the file named in its "base" (relative to the project), if any, and over
    an OoTR preset (vendor/ootr/data/presets_default.json, by name) when one is given. Familiar names
    (apply_aliases) become the remake keys first, and remake glitch tricks given one by one join allowed_tricks
    (trick_toggles)."""
    d = json.load(open(path, encoding="utf-8"))
    if not isinstance(d, dict):
        raise SeedError(f"{settings_name(path)}: not a settings file (a JSON object)")
    if "settings" not in d:  # OoT Randomizer's own settings file: the settings themselves, no "base"
        d = {"settings": {k: v for k, v in d.items() if not k.startswith("_")}}
    base = load_settings(os.path.join(HERE, d["base"])) if d.get("base") else {}
    out = trick_toggles(dict(base, **apply_aliases(d["settings"], settings_name(path))), settings_name(path))
    if preset:
        presets = json.load(open(os.path.join(HERE, "vendor", "ootr", "data", "presets_default.json"), encoding="utf-8"))
        if preset not in presets:
            raise SeedError(f"no OoTR preset {preset!r} ({', '.join(presets)})")
        out.update(presets[preset])
    if out.get("logic_rules") == "advanced":
        out["logic_rules"] = advanced_as_glitched(settings_name(path) if not preset else f"preset {preset!r}")
    return out


ADVANCED_NOTE = ("logic_rules 'advanced' is OoT Randomizer's N64 glitched logic, whose glitches don't work in the remake: "
                 "made as 'remake_glitched' (Glitched: the remake's own glitches)")


def advanced_as_glitched(where):
    """Maps OoTR's 'advanced' logic to the remake's closest real one, 'remake_glitched' (parity/glitches.py), with a
    line on stderr since stdout may be JSON (tools/release/resolve_settings.py). Also used for settings strings
    (glitches.resolve_settings)."""
    print(f"note: {where}: {ADVANCED_NOTE}", file=sys.stderr)
    return "remake_glitched"


def plugins():
    """Parity plugins (tools/rando/parity/*.py), each a module that may define:
      OWNS = {"setting": (allowed values...)}       settings it applies (or checks itself with check_settings)
      check_settings(settings) -> [problem, ...]
      resolve_settings(settings)                    before OoTR's Main.resolve_settings: a plugin's own value of an
                                                    OoTR setting -> the values OoTR runs (spoiler_settings(settings)
                                                    puts it back for the spoiler)
      keep_locations(world, settings) -> {OoTR location name, ...}   locations it can patch (not locked vanilla)
      before_build(settings)                        just before OoTR builds the world (hooks on OoTR itself)
      untested(settings) -> [str, ...]              applied values not yet seen in-game (listed in seed.json)
      before_fill(world, settings)                  item rules, events, extra locks before OoTR's fill
      after_fill(world, settings)                   fix-ups after the fill, before the spoiler (OoTR's junk pass
                                                    ignores item rules: swap junk that can't go where it landed)
      world_plan(settings, world) -> {plan section: value}           patch plan for what landed there
      finish_plan(settings, plan, cfg)                               the whole plan, before it is written (cfg: the
                                                                     settings_used.json record, e.g. resolved values)
      item_for(item, location, world) -> actor or reward spec | None   remake item for an OoTR item at a chest or
                                                    scene location (e.g. an ice trap scene), before item_map.json
    Logic changes go in data/rando/logic/*.json (tools/rando/world_settings.py logic_overrides)."""
    import importlib
    return [importlib.import_module(f"parity.{name}") for name in enabled_plugins()]


def all_plugins():
    import pkgutil
    pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parity")
    return sorted(m.name for m in pkgutil.iter_modules([pkg]) if not m.name.startswith("_"))


def enabled_plugins():
    """config/plugins.json "enabled", changed by the RANDO_PLUGINS environment variable: "all", a comma list
    (replaces the list) or "+name" entries (added to it). Unfinished plugins in the folder never join a seed."""
    names = json.load(open(os.path.join(HERE, "config", "plugins.json"), encoding="utf-8"))["enabled"]
    env = os.environ.get("RANDO_PLUGINS", "").strip()
    if env == "all":
        names = all_plugins()
    elif env:
        parts = [p.strip() for p in env.split(",") if p.strip()]
        if all(p.startswith("+") for p in parts):
            names = names + [p[1:] for p in parts]
        else:
            names = [p.lstrip("+") for p in parts]
    present = set(all_plugins())
    missing = [n for n in names if n not in present]
    if missing:
        raise SeedError(f"plugins not found in tools/rando/parity: {', '.join(missing)}")
    return sorted(set(names))


FALLBACK_JUNK = ("Rupees (5)", "Recovery Heart", "Rupee (1)", "Rupees (20)")


def install_rule_fill():
    """OoTR places its last junk with Fill.fast_fill, which ignores item rules (junk "goes anywhere" in the original).
    In the remake it doesn't: a shelf can't show rupees, a pot can't drop an ice trap, a chest without a progressive
    scene can't take a capacity upgrade. Each location here takes the first remaining item its rules accept."""
    import random
    import Fill
    if getattr(Fill.fast_fill, "remake_rules", False):
        return

    from Item import ItemFactory

    def fast_fill(locations, itempool):
        random.shuffle(locations)
        while itempool and locations:
            loc = locations.pop()
            k = next((i for i in range(len(itempool) - 1, -1, -1) if loc.can_fill_fast(itempool[i])), None)
            if k is None:
                # Nothing left fits (a pot takes rupees and hearts, not ammo), so we make a fresh junk item that does
                # and drop one leftover junk item so the counts still match. Junk never matters to logic.
                fresh = next((it for it in (ItemFactory(n, loc.world) for n in FALLBACK_JUNK)
                              if loc.can_fill_fast(it)), None)
                spare = next((i for i in range(len(itempool) - 1, -1, -1)
                              if not itempool[i].advancement and not itempool[i].priority), None)
                if fresh is None or spare is None:
                    raise Fill.FillError(f"{loc.name}: no remaining item fits its rules")
                itempool.pop(spare)
                loc.world.push_item(loc, fresh)
                continue
            loc.world.push_item(loc, itempool.pop(k))
    fast_fill.remake_rules = True
    Fill.fast_fill = fast_fill


def plugin_item(mods, item, location, world):
    """What the plan puts at `location` for OoTR's `item`. That's a plugin's answer (item_for(item, location, world) ->
    actor name or reward spec dict, or None), else config/item_map.json."""
    for m in mods:
        if hasattr(m, "item_for"):
            target = m.item_for(item, location, world)
            if target is not None:
                return target
    return remake_item(item)


def merge_plan(plan, part):
    for section, value in part.items():
        if section == "gamedata":  # save-data edits from several features: a list of ops (make_patch takes one)
            old = plan.get(section)
            ops = [] if old is None else [old] if isinstance(old, dict) else list(old)
            plan[section] = ops + ([value] if isinstance(value, dict) else list(value))
        elif isinstance(value, list):
            plan[section] = plan.get(section, []) + value
        elif isinstance(value, dict) and isinstance(plan.get(section), dict):
            plan[section] = dict(plan[section], **value)
        else:
            plan[section] = value


merge_plan._keeps_gamedata = True  # the fix plugins used to install themselves is in the core now


def settings_problems(settings, mods):
    """Why the remake can't make these (resolved) settings: [] when it can. Also used by tools/release/export_schema.py
    to offer only values that pass."""
    owned = {name for m in mods for name in getattr(m, "OWNS", {})}
    problems = world_settings.check_settings(settings, owned)
    for m in mods:
        for name, ok in getattr(m, "OWNS", {}).items():
            if ok is not None and getattr(settings, name, None) not in ok:
                problems.append(f"{name} = {getattr(settings, name, None)!r}: {m.__name__} can make "
                                f"{', '.join(map(repr, ok))}")
        if hasattr(m, "check_settings"):
            problems += m.check_settings(settings)
    problems += [p for p in unknown_remake_settings(settings, mods)
                 if not any(p.split(":", 1)[0] in q for q in problems)]  # a plugin may already have named it
    return problems


def prepare(seed, cfg, settings_path=None, settings_string=None):
    """generate's setup before its fill attempts, from resolved settings (load_settings). Builds OoTR's settings,
    checks them against the enabled plugins, installs the remake's logic and returns a namespace for
    build_unfilled. tools/tracker/logic_server.py rebuilds a seed's world with these two (from
    OUT_DIR/settings_used.json)."""
    from types import SimpleNamespace
    Main, Goals, ShuffleError, ItemFactory, Settings, SettingInfos = ootr()
    chest_map = json.load(open(os.path.join(HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"]
    rewards = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))}
    logging.getLogger("").setLevel(logging.WARNING)
    modes = {n: v["mode"] for n, v in chest_map.items()}
    scene_locs = scene_locations()
    keep = {n for n, m in modes.items() if m in ("full", "group")} | set(scene_locs)
    settings = make_settings(Settings, cfg, seed, [], settings_path)
    if settings_string:  # an OoTR settings string (as OoTR's GUI shows): its seed settings over the file's
        try:
            settings.update_with_settings_string(settings_string)
        except Exception as e:  # noqa: BLE001 - OoTR raises plain exceptions for bad strings
            raise SeedError(f"settings string: {e}")
        settings.seed = str(seed)
        if hasattr(settings, world_settings.LOW_HEARTS):  # the string's starting hearts (3-20) win over the file's
            delattr(settings, world_settings.LOW_HEARTS)
    mods = plugins()
    for m in mods:  # a plugin's own value of an OoTR setting -> the values OoTR runs (glitches: "remake_glitched")
        if hasattr(m, "resolve_settings"):
            m.resolve_settings(settings)
    if settings.logic_rules == "remake_glitched":
        raise SeedError(f"{settings_name(settings_path)}: logic_rules remake_glitched needs the glitches plugin "
                        "(config/plugins.json)")
    Main.resolve_settings(settings)
    problems = settings_problems(settings, mods)
    if problems:
        raise SeedError(f"{settings_name(settings_path)}: " + "; ".join(problems))
    # the active plugins' logic, including story gates that check boss defeats instead of rewards
    world_settings.install_logic(enabled=set(enabled_plugins()), plugins=set(all_plugins()))
    if world_settings.heart_deficit(settings):  # 1 or 2 starting hearts: OoTR's heart count and goals see them
        world_settings.install_low_hearts()
    return SimpleNamespace(Main=Main, Goals=Goals, ShuffleError=ShuffleError, ItemFactory=ItemFactory,
                           settings=settings, mods=mods, chest_map=chest_map, rewards=rewards, modes=modes,
                           scene_locs=scene_locs, keep=keep)


def build_unfilled(ctx, attempt=1):
    """One fill attempt's world as generate builds it, up to and including the plugins' before_fill. That's OoTR's
    world graph with the remake's locks, group logic and item rules, not filled. `ctx` is prepare's namespace.
    Returns (worlds, world, extra, made, guarded), extra being the locations plugins keep, patchable besides
    ctx.keep."""
    Main, settings, mods = ctx.Main, ctx.settings, ctx.mods
    if attempt > 1:
        settings.reset_distribution()
    from parity import _ammo  # remake_ammo_without_container: every give step of ammo reads it (guards, drops)
    _ammo.configure(settings)
    for m in mods:  # e.g. hooks on OoTR's entrance shuffle, before OoTR builds the world
        if hasattr(m, "before_build"):
            m.before_build(settings)
    worlds = Main.build_world_graphs(settings)
    world = worlds[0]
    world_settings.add_heart_containers(world, ctx.ItemFactory)  # (1 or 2 starting hearts: 20 stay reachable)
    extra = set().union(*(m.keep_locations(world, settings) for m in mods if hasattr(m, "keep_locations")))
    made = lock_unpatchable(world, ctx.ItemFactory, ctx.keep | extra)
    apply_group_logic(world, ctx.chest_map, ctx.modes)
    guarded = guard_progressive(world, ctx.chest_map, ctx.rewards, ctx.modes)
    give_modes = json.load(open(os.path.join(HERE, "data", "rando", "scene_give_modes.json"),
                                encoding="utf-8"))["locations"]
    # Progressive items only go where every give step can take one, unless the songs/trade plugin gives them through
    # their tier entry where a step can't (songs_trade.progressive_spec).
    calls = "songs_trade" in enabled_plugins()
    for name, rid in ctx.scene_locs.items():
        if calls or give_modes.get(rid, {}).get("progressive"):
            continue
        loc = world.get_location(name)
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: item.name not in PROGRESSIVE and prev(location, item))
        guarded.append(name)
    install_rule_fill()
    for m in mods:
        if hasattr(m, "before_fill"):
            m.before_fill(world, settings)
    # Group logic (apply_group_logic, plugins' before_fill) adds Event locations to regions after lock_unpatchable
    # cached world.get_locations(). Without a refresh the search never collects those events, and every location
    # gated on them is unreachable in logic (it can only ever get junk).
    world._cached_locations = []
    return worlds, world, extra, made, guarded


def generate(seed, settings_path, preset=None, settings_string=None, cfg=None):
    # a seed depends on the settings' values, not on how a file lays them out (a base chain, the app's own file)
    if cfg is None:
        cfg = dict(sorted(load_settings(settings_path, preset).items()))
    ctx = prepare(seed, cfg, settings_path, settings_string)
    import free_flags  # (a new seed mints its own flags from 000: free_flags.mint)
    free_flags.MINTED.clear()
    progress.report(0.07)
    Main, Goals, ShuffleError, settings, mods, keep = ctx.Main, ctx.Goals, ctx.ShuffleError, ctx.settings, ctx.mods, \
        ctx.keep
    chest_map, modes, rewards, scene_locs = ctx.chest_map, ctx.modes, ctx.rewards, ctx.scene_locs
    last, relaxed = None, set()
    for attempt in range(1, 21):
        try:
            worlds, world, extra, made, guarded = build_unfilled(ctx, attempt)
            # remake_avoid_vanilla_spots (tools/rando/no_vanilla.py): dungeon items refuse their own vanilla spot. An
            # item the fill found no spot for drops the rule from then on (the logic leaves it only its vanilla spots),
            # and after 10 attempts no item keeps it. The swaps after the fill still apply.
            no_vanilla.install_rules(world, settings, strict=attempt <= 10, relaxed=relaxed)
            Main.place_items(worlds)
            progress.report(0.26)
            # Nothing keeps its own vanilla item by chance. The swaps keep every rule and the logic, and they run before
            # the plugins' fix-ups so those see the final placements.
            world.remake_no_vanilla = no_vanilla.fix(world, settings)
            for m in mods:  # OoTR's last junk pass ignores item rules: plugins swap junk that can't go where it landed
                if hasattr(m, "after_fill"):
                    m.after_fill(world, settings)
            stranded = no_savewarp.check(world)  # the remake has no save warp (tools/rando/no_savewarp.py)
            if stranded:
                sphere, age, region = stranded[0]
                raise ShuffleError(f"{len(stranded)} places could strand the player with no save warp, "
                                   f"e.g. {region} as {age} in sphere {sphere}")
            patchable = keep | extra
            stray = [loc.name for loc in world.get_locations() if loc.item is not None and not loc.locked
                     and loc.name not in patchable and loc.type not in NOT_ITEM_CHECKS]
            if stray:  # an item the patcher would never write: the seed could be unbeatable in the game
                raise SeedError(f"OoTR placed items where the patcher can't: {', '.join(sorted(stray)[:10])}")
            world.distribution.configure_effective_starting_items(worlds, world)
            if world.enable_goal_hints:
                Goals.replace_goal_names(worlds)
            spoiler = Main.make_spoiler(settings, worlds)
            return settings, spoiler, world, chest_map, modes, rewards, made, guarded, attempt, scene_locs
        except ShuffleError as e:
            last = e
            stuck = re.search(r"No more spots to place (.+?) \[World", str(e))
            if stuck:
                relaxed.add(stuck.group(1))
            if os.environ.get("RANDO_DEBUG"):
                print(f"attempt {attempt} failed: {e}", file=sys.stderr)
    raise SeedError(f"no beatable fill in 20 attempts: {last}")


def write_settings_used(out, seed, cfg, settings_string=None):
    """Writes OUT_DIR/settings_used.json, what the seed was generated from, so its world can be rebuilt
    (tools/tracker/logic_server.py). It has "settings" (the resolved settings dict from load_settings, remake_* keys
    included), "seed", "plugins" (the enabled plugins, from config/plugins.json or RANDO_PLUGINS) and
    "settings_string" when one was given. load_settings reads it back as a settings file (its "settings")."""
    d = {"seed": str(seed), "settings": cfg, "plugins": enabled_plugins()}
    if settings_string:
        d["settings_string"] = settings_string
    with open(os.path.join(out, "settings_used.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)


def spoiler_gossip(settings, spoiler):
    """{stone name: {"text": ...}} for world 1, as written to the spoiler log."""
    settings.distribution.update_spoiler(spoiler, True)
    data = (
        json.loads(json.dumps(settings.distribution.to_json(include_output=True, spoiler=True), default=str))
        if hasattr(settings.distribution, "to_json")
        else None
    )
    gs = (data or {}).get("gossip_stones") or {}
    if "World 1" in gs:
        gs = gs["World 1"]
    return gs


def _test_start(path):
    """A dev test build's "test_start" section, at the top level of the plan settings file next to "settings". The new
    file picks a test and starts at its spot (parity/_test_start.py). No other settings file has one, so no other
    seed changes."""
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        d = None
    from parity import _test_start as ts
    ts.configure(d.get("test_start") if isinstance(d, dict) else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--seed", default=None)
    ap.add_argument("--settings", default=os.path.join(HERE, "config", "rando_settings.json"))
    ap.add_argument("--preset", help="an OoTR preset by name (vendor/ootr/data/presets_default.json), over --settings")
    ap.add_argument("--settings-string", help="an OoTR settings string, over --settings and --preset")
    a = ap.parse_args()
    seed = a.seed or str(int.from_bytes(os.urandom(4), "little"))
    cfg = dict(sorted(load_settings(a.settings, a.preset).items()))  # also written to settings_used.json
    _test_start(a.settings)
    settings, spoiler, world, chest_map, modes, rewards, made, guarded, attempt, scene_locs = generate(
        seed, a.settings, a.preset, a.settings_string, cfg=cfg
    )
    mods = plugins()

    plan = {"description": f"Randomized seed {seed} (OoT Randomizer generator, {len(chest_map)} chests mapped)",
            "chest_size": "keep", "rewards": {}}
    changed, unmapped = 0, []
    for name, v in sorted(chest_map.items()):
        if modes[name] not in ("full", "group"):
            continue
        item = world.get_location(name).item.name
        try:
            target = plugin_item(mods, item, name, world)
        except SeedError as e:
            unmapped.append(str(e))
            continue
        r = rewards[v["remake"]]
        spec = dict(target) if isinstance(target, dict) else {"item": target}
        if spec["item"] != r["item"] or spec.get("extra"):
            changed += 1
        plan["rewards"][v["remake"]] = dict(spec, note=f"{name}: {item}")
    for name, rid in sorted(scene_locs.items()):  # a location id: the patcher changes every give step of it
        item = world.get_location(name).item.name
        try:
            target = plugin_item(mods, item, name, world)
            plan["rewards"][rid] = (
                dict(target, note=f"{name}: {item}")
                if isinstance(target, dict)
                else {"item": target, "note": f"{name}: {item}"}
            )
            changed += 1
        except SeedError as e:
            unmapped.append(str(e))
    if unmapped:
        raise SeedError("; ".join(sorted(set(unmapped))))

    world.spoiler = spoiler  # plugins may read it (the seed's file hash, hints)
    merge_plan(plan, world_settings.world_plan(settings, world))
    progress.report(0.53)  # the plugins' plans: the first ones take most of it
    for m in progress.span(plugins(), 0.53, 0.95):
        if hasattr(m, "world_plan"):
            merge_plan(plan, m.world_plan(settings, world))
    from parity import extras_souls  # enemy souls: every gated enemy and its twins read "soul AND its Presence", after
    merge_plan(plan, extras_souls.finalize(plan, settings, world))  # every plugin's placements ({} when off)
    if plan.pop("_ice_sensor", False):  # some freeze scene creates the ice-trap attacker, so add its files once
        import drops as drop_tools
        merge_plan(plan, drop_tools.ice_sensor_ops())
        from parity import _chests_scenes  # and the freeze's "You are a FOOL!" (its GetPouchContent entry, text)
        merge_plan(plan, _chests_scenes.fool_ops())
    from parity import _ammo  # ammo without its container adds nothing (OoTR)
    merge_plan(plan, _ammo.guard_ops())
    merge_plan(plan, _ammo.container_ops())  # Bow/Slingshot bring their container, bombs need no bracelet (Kaepora)
    merge_plan(plan, _ammo.switch_ops(plan, rewards))  # a chest or object gives a Blue Rupee while no container
    from parity import _room_exits  # dungeon rooms that lock Link in without their item: solved on a new file
    merge_plan(plan, _room_exits.ops())
    import free_flags  # once-flags past the borrowed pool's end: new saved Bools of our own (free_flags.mint)
    merge_plan(plan, free_flags.minted_plan())

    hints = settings.hints
    if hints not in ("none", "mask", "agony", "always"):
        raise SeedError(f"hints {hints!r}: unknown hint mode")
    if hints != "none":
        stones = spoiler_gossip(settings, spoiler)
        ops = gossip_text_ops(stones)
        for m in mods:
            if hasattr(m, "gossip_text"):  # a plugin may re-pair and reword the stones' ops (hints: real labels)
                ops = m.gossip_text(stones, ops)
        plan["text"] = plan.get("text", []) + ops  # keep plugins' text
    if hints == "always":
        plan["events"] = plan.get("events", []) + list(HINTS_ALWAYS)
    elif hints == "agony":
        plan["events"] = plan.get("events", []) + list(HINTS_AGONY)

    progress.report(0.965)
    for m in mods:  # plugins that finish the whole plan (songs_trade: the Ocarina buttons' labels, recorded in cfg)
        if hasattr(m, "finish_plan"):
            m.finish_plan(settings, plan, cfg)
    os.makedirs(a.out, exist_ok=True)
    json.dump(plan, open(os.path.join(a.out, "plan.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for m in mods:  # the spoiler shows the value the player chose (glitches: Logic Rules "remake_glitched")
        if hasattr(m, "spoiler_settings"):
            m.spoiler_settings(settings)
    if getattr(settings, world_settings.LOW_HEARTS, None):  # and 1 or 2 starting hearts (its settings string can't:
        settings.starting_hearts = getattr(settings, world_settings.LOW_HEARTS)  # it stays OoTR's, with 3)
    settings.distribution.update_spoiler(spoiler, True)
    settings.distribution.to_file(os.path.join(a.out, "spoiler.json"), True)
    summary = {"seed": seed, "attempts": attempt, "chests_in_play": len(plan["rewards"]), "chests_changed": changed,
               "locked_vanilla_items_made": made, "progressive_kept_out_of": guarded,
               "playthrough_spheres": len(spoiler.playthrough),
               "world_settings": {k: v for k, v in plan.items() if k in ("gamedata", "binary")},
               "world_settings_not_yet_seen_in_game": world_settings.untested(settings) + [
                   x for m in mods if hasattr(m, "untested") for x in m.untested(settings)],
               "chest_modes": {m: sum(1 for x in modes.values() if x == m) for m in ("full", "group", "vanilla")},
               "vanilla_spots": {"setting": no_vanilla.enabled(settings),
                                 "swapped_away": len(getattr(world, "remake_no_vanilla", {}).get("swapped", [])),
                                 "still_vanilla": no_vanilla.report(world, settings)}}
    summary["check_ages"] = check_ages([world])  # the tracker draws each check on the map of the age that gets it
    json.dump(summary, open(os.path.join(a.out, "seed.json"), "w", encoding="utf-8"), indent=1)
    write_settings_used(a.out, seed, cfg, a.settings_string)
    print(f"seed {seed}: {len(plan['rewards'])} chests in play, {changed} changed, "
          f"{len(spoiler.playthrough)} playthrough spheres; {len(made)} locked items made, "
          f"progressive kept out of {len(guarded)} chests (own scene or no progressive scene for the type)")
    left = summary["vanilla_spots"]["still_vanilla"]
    print(f"vanilla spots: {summary['vanilla_spots']['swapped_away']} items swapped away, {len(left)} still vanilla "
          f"({sum(1 for r in left if r['why'].startswith('locked'))} locked before the fill)")
    print(f"wrote {a.out}/plan.json, spoiler.json, seed.json")
    try:  # the tracker's seed file (tracker/dist/RandoOfTimeTracker.exe opens it): spoiler-free, next to the patch
        sys.path.insert(0, os.path.join(HERE, "tools", "tracker"))
        import build_data
        build_data.seed(a.out)
    except Exception as e:  # noqa: BLE001 - the seed is fine without it
        print(f"tracker.json not written: {e}")


def check_ages(worlds):
    """{location: "child" | "adult" | "both"} for every check one age or both can get with every item (OoTR's own
    search, all progression collected). The tracker puts a check that both ages' maps draw (Mido's house, grottos,
    the Kokiri Sword chest...) on the map of the age that gets it, the child's when both can. Checks neither age
    can reach are left out (the tracker keeps its first map for them)."""
    from Search import Search
    from Region import TimeOfDay
    s = Search.max_explore([w.state for w in worlds])
    out = {}
    for loc in worlds[0].get_locations():
        if loc.type in ("Event", "Drop", "HintStone", "Hint") or loc.parent_region is None:
            continue
        got = [age for age in ("child", "adult")
               if s.spot_access(loc, age) or s.spot_access(loc, age, tod=TimeOfDay.ALL)]
        if got:
            out[loc.name] = "both" if len(got) == 2 else got[0]
    return out


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        # A seed has to reproduce, and Python orders sets of names differently on each run unless hashing is fixed.
        import subprocess
        sys.exit(subprocess.call([sys.executable] + sys.argv, env=dict(os.environ, PYTHONHASHSEED="0")))
    try:
        main()
    except SeedError as e:
        sys.exit(f"seed error: {e}")
