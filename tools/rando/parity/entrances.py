"""Entrance randomizer: OoTR's shuffled entrances -> the remake's level transitions.

OoT Randomizer shuffles the entrances (EntranceShuffle.py) while it builds the world. This plugin turns the result into
patch ops from data/rando/entrances_remake.json (tools/rando/parity/_entrances_build.py). The result is
world.get_shuffled_entrances(), where each entrance's .replaces is the entrance whose vanilla destination it now has.
- doorways between levels (FieldAndDungeonEntranceEventRequestActor, "FADE"): placement edits of the destination
  settings (level per age, start position, arrival and first-visit scenes) in every level file (child, adult,
  alternative) that has the doorway
- warp songs: the :OcarinaWarp call of each song in Dm_SY_Ocarina (ChildBanc, AdultBanc, NextStartPos)
- owls: the Death Mountain owl's level change (Npc_Kaepora_DeathMountainTrail). The Lake Hylia owl lands inside the
  Hyrule Field level, so it gets a level change after its flight scene.
- child spawn: a level change at the end of the new-file opening scene (OpeningEvent:Opening_Introduction)
- Jabu-Jabu: the first entry (the fish) is a level change in Get_StoneOfWater, moved with the doorway
- the Lake Hylia gate: when the Water Temple moves, the gate only opens from its switch (LAKE_GATE)

What the remake can't do: houses, shops, grottos, graves, the hideout, boss rooms and
Ganon's tower are inside their area's level, so the interior, hideout, grotto, boss and tower shuffles have nothing to
move. Five OoTR overworld connections are one continuous area in the remake (Lost Woods bridge, Lake Hylia, Lon Lon
Ranch, Market entrance, Temple of Time courtyard) and stay vanilla when the overworld is shuffled. Blue warps keep their
vanilla landing, since their landing scenes complete the dungeon's story stage in that level. One-way entrances only
lead to places both ages have a start position for.

Settings: shuffle_dungeon_entrances off/simple/all, shuffle_overworld_entrances, shuffle_gerudo_valley_river_exit,
owl_drops, warp_songs, spawn_positions [] or [child]. The rest have to stay off (check_settings explains why).
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TABLE_PATH = os.path.join(HERE, "data", "rando", "entrances_remake.json")
_TABLE = None


def table():
    global _TABLE
    if _TABLE is None:
        _TABLE = json.load(open(TABLE_PATH, encoding="utf-8"))
    return _TABLE


# Settings this plugin applies. None means check_settings checks it (and gives the reason a value can't be made).
OWNS = {name: None for name in (
    "shuffle_interior_entrances", "shuffle_hideout_entrances", "shuffle_grotto_entrances",
    "shuffle_dungeon_entrances", "shuffle_bosses", "shuffle_ganon_tower", "shuffle_overworld_entrances",
    "shuffle_gerudo_valley_river_exit", "owl_drops", "warp_songs", "spawn_positions", "starting_age")}

UNSUPPORTED = {
    "shuffle_interior_entrances": ("off", "houses and shops are modelled inside their area's level (the door opens "
                                          "into the room, no level change), so there is no transition to move"),
    "shuffle_hideout_entrances": (False, "the Thieves' Hideout is part of the Gerudo Fortress level"),
    "shuffle_grotto_entrances": (False, "grottos and graves are rooms under their area's level, entered by a scene "
                                        "that moves Link inside the level (HidingHole_Entry)"),
    "shuffle_bosses": ("off", "boss rooms are part of their dungeon's level (no level change at the boss door)"),
    "shuffle_ganon_tower": (False, "Ganon's tower is part of the InsideGanonCastle level"),
    "starting_age": ("child", "a new file starts in child Kokiri Forest with the child story; starting adult needs "
                              "the story steps of the child half and an adult opening"),
}
SUPPORTED = {
    "shuffle_dungeon_entrances": ("off", "simple", "all"),
    "shuffle_overworld_entrances": (False, True),
    "shuffle_gerudo_valley_river_exit": (False, True),
    "owl_drops": (False, True),
    "warp_songs": (False, True),
}
# TODO: applied by the patcher but not seen working in-game yet
UNTESTED = ("shuffle_dungeon_entrances", "shuffle_overworld_entrances", "shuffle_gerudo_valley_river_exit",
            "owl_drops", "warp_songs", "spawn_positions")

_ACTIVE = {"on": False}
_HOOKED = {"done": False}


def _active(settings):
    return (settings.shuffle_dungeon_entrances != "off" or settings.shuffle_overworld_entrances
            or settings.shuffle_gerudo_valley_river_exit or settings.owl_drops or settings.warp_songs
            or bool(settings.spawn_positions))


def check_settings(settings):
    problems = []
    _ACTIVE["on"] = False
    for name, (want, why) in UNSUPPORTED.items():
        v = getattr(settings, name, want)
        if v != want:
            problems.append(f"{name} = {v!r}: not possible in the remake yet, must be {want!r}: {why}")
    for name, ok in SUPPORTED.items():
        v = getattr(settings, name, None)
        if v not in ok:
            problems.append(f"{name} = {v!r}: the patcher can make {', '.join(map(repr, ok))}")
    spawns = list(getattr(settings, "spawn_positions", None) or [])
    if "adult" in spawns:
        problems.append("spawn_positions 'adult': adult first appears in the Temple of Time through the time-travel "
                        "scene (Market_Child_Field_ChildToAdult), which is staged there; only 'child' can be moved")
    if not problems:
        _ACTIVE["on"] = _active(settings)
        if _ACTIVE["on"]:
            install_hooks()
    return problems


# OoTR hooks (only act while _ACTIVE)
def _single_age_rule(age):
    rule = lambda state, age_=age, **kwargs: kwargs.get("age") == age_  # noqa: E731
    rule.remake_target_tag = True
    return rule


def _target_ages(name):
    """(child ok, adult ok, same start position for both) for arriving where OoTR entrance `name` leads."""
    e = table()["entrances"].get(name)
    t = (e or {}).get("target") or {}
    c, a = t.get("child"), t.get("adult")
    return bool(c), bool(a), bool(c and a and c["start"] == a["start"])


def _tag(entrance, target):
    """While `entrance` leads where `target` leads in vanilla, only the age(s) that can arrive there can use it."""
    child, adult, _ = _target_ages(target.name)
    if (child and adult) or getattr(entrance, "remake_tagged", False):
        return
    rule = _single_age_rule("adult" if adult else "child") if (child or adult) else (lambda state, **kw: False)
    rule.remake_target_tag = True
    entrance.remake_tagged = True
    if entrance.always:
        entrance.remake_was_always = True
        entrance.set_rule(rule)
        entrance.always = False
    else:
        entrance.add_rule(rule)


def _untag(entrance):
    if not getattr(entrance, "remake_tagged", False):
        return
    entrance.remake_tagged = False
    if getattr(entrance, "remake_was_always", False):
        entrance.remake_was_always = False
        entrance.set_rule(lambda state, **kwargs: True)
        entrance.always = True
    else:  # add_rule's combined rule reads access_rules when called
        entrance.access_rules[:] = [r for r in entrance.access_rules if not getattr(r, "remake_target_tag", False)]


def install_hooks():
    """Keeps OoTR's entrance shuffle within what the remake can move, so its own checks (every location reachable, time
    passing for both ages...) hold for the patched game. The vendored files stay untouched.
    - the overworld connections that are one area in the remake aren't shuffled (or used as targets)
    - doorways only one age's level has can only be used by that age (e.g. Gerudo Valley -> Gerudo Fortress)
    - an entrance placed where only one age can arrive in the remake (Gerudo Fortress, Jabu-Jabu's and the Ice Cavern's
      way out...) can only be used by that age while it's placed there
    - blue warps land where the remake's landing scenes are (they finish the dungeon's story stage there), also after
      OoTR moves dungeons, so OoTR's own blue-warp rewiring is ignored
    - one-way entrances (warp songs, owls, spawns, the river) only lead to places with a start position both ages share
      (unused one-way targets get removed again, like OoTR does with its own leftovers)"""
    if _HOOKED["done"]:
        return
    import EntranceShuffle
    from Entrance import Entrance
    orig = {k: getattr(EntranceShuffle, k) for k in ("set_all_entrances_data", "build_one_way_targets",
                                                      "change_connections", "restore_connections")}

    def set_all_entrances_data(world):
        orig["set_all_entrances_data"](world)
        if not _ACTIVE["on"]:
            return
        for name, e in table()["entrances"].items():
            if e["kind"] == "seamless":
                world.get_entrance(name).type = None  # out of every pool, as a target too
            elif e["kind"] == "fade":
                ages = {s["age"] for s in e["sources"]}
                if "both" in ages or {"child", "adult"} <= ages:
                    continue
                rule = _single_age_rule("adult" if "adult" in ages else "child")
                rule.remake_target_tag = False  # permanent
                world.get_entrance(name).add_rule(rule)
        for name, bw in table()["blue_warps"].items():
            e = world.get_entrance(name)
            region = world.get_region(bw["region"])
            if e.connected_region is not region:
                if e.connected_region is not None:
                    e.disconnect()
                Entrance.connect(e, region)
            e.connect = lambda _region, e=e, region=region: Entrance.connect(e, region)

    def build_one_way_targets(world, types_to_include, exclude=(), target_region_names=()):
        targets = orig["build_one_way_targets"](world, types_to_include, exclude, target_region_names)
        if not _ACTIVE["on"]:
            return targets
        keep = []
        for t in targets:
            if _target_ages(t.replaces.name)[2]:
                keep.append(t)
            else:
                EntranceShuffle.delete_target_entrance(t)
        return keep

    def change_connections(entrance, target_entrance):
        orig["change_connections"](entrance, target_entrance)
        if not _ACTIVE["on"]:
            return
        _tag(entrance, entrance.replaces)
        if entrance.reverse:
            _tag(target_entrance.replaces.reverse, entrance.reverse)

    def restore_connections(entrance, target_entrance):
        reverse = target_entrance.replaces.reverse if entrance.reverse else None
        orig["restore_connections"](entrance, target_entrance)
        _untag(entrance)
        if reverse is not None:
            _untag(reverse)

    for k, f in (("set_all_entrances_data", set_all_entrances_data), ("build_one_way_targets", build_one_way_targets),
                 ("change_connections", change_connections), ("restore_connections", restore_connections)):
        setattr(EntranceShuffle, k, f)
    _HOOKED["done"] = True


def before_fill(world, settings):
    """Check that the world OoTR built is one the patch can make (the hooks above keep it so)."""
    if not world.entrance_shuffle:
        return
    for name, bw in table()["blue_warps"].items():
        e = world.get_entrance(name)
        if e.connected_region is None or e.connected_region.name != bw["region"]:
            raise RuntimeError(f"{name} leads to {e.connected_region}, not where the remake lands ({bw['region']})")
    for e in world.get_shuffled_entrances():
        if e.replaces is not None and e.replaces is not e:
            child, adult, both = _target_ages(e.replaces.name)
            if not (child or adult) or (e.type in ONE_WAY and not both):
                raise RuntimeError(f"{e.name} leads where {e.replaces.name} does, which the patch can't make")


ONE_WAY = ("WarpSong", "OwlDrop", "Spawn", "OverworldOneWay")


# Patch plan
def _go_event(vanilla_go, dest):
    t = table()
    fam = (t["go_events"].get(vanilla_go) or {}).get("family", "source")
    if fam == "source":
        return vanilla_go
    return t["go_by_family"][fam].get(str(dest) if dest else "None", t["go_by_family"][fam]["None"])


def fade_ops(source_name, target_name):
    """Placement ops sending every doorway of OoTR entrance `source_name` where `target_name` leads in vanilla."""
    t = table()
    src, tgt = t["entrances"][source_name], t["entrances"][target_name]["target"]
    ops = []
    for s in src["sources"]:
        d = s["vanilla"]
        ages = ["child", "adult"] if s["age"] == "both" else [s["age"]]
        dest = [tgt.get(a) for a in ages]
        usable = [x for x in dest if x]
        if not usable:  # this level's age can't arrive there: the doorway keeps its own destination
            continue
        main = usable[-1] if s["age"] == "both" else usable[0]  # one start position per doorway
        child = tgt.get("child") or main
        adult = tgt.get("adult") or main
        if s["age"] == "both" and child["start"] != adult["start"]:
            child = adult = main
        sets = {"Dynamic.NextBancParamNameChild": child["level"], "Dynamic.NextBancParamNameAdult": adult["level"],
                "Dynamic.NextStartPosName": main["start"]}
        removes = []
        fields = dict(main["fields"])
        if fields.get("NextEventName") == "OcarinaWarp_Arrive":  # a warp pad reached through a doorway: plain arrival
            fields["NextEventName"] = "Dm_SY_BancChangeArrive"
        for k in t["dest_fields"]:
            if k in fields:
                sets[f"Dynamic.{k}"] = fields[k]
            elif k in d:
                removes.append(f"Dynamic.{k}")
        if main["air"]:
            sets["Dynamic.IsChangableAirPos"] = True
        elif "IsChangableAirPos" in d:
            removes.append("Dynamic.IsChangableAirPos")
        go = _go_event(d.get("FirstEventName"), main.get("go_dest"))
        if go != d.get("FirstEventName"):
            sets["Dynamic.FirstEventName"] = go
        ops.append({"file": s["file"], "hash": s["hash"], "set": sets, "remove": removes,
                    "note": f"{source_name} -> where {target_name} leads ({s['level']}/{s['name'] or 'unnamed'})"})
    return ops


def _rbc_params(level, start, boot, fade=1):
    return {"IsWaitEnd": True, "NextPosition": [0.0, 0.0, 0.0], "NextStartRot": [0.0, 0.0, 0.0],
            "IsStartOnEvent": False, "NextBanc": level, "NextStartPos": start, "BootEventName": boot,
            "EventStarterName": "", "IsItemWarp": False, "FadePattern": fade}


def _arrival(target_name, age):
    """(level, start position, arrival scene) for a scene-driven level change to where `target_name` leads. The
    warp-song arrival scene (OcarinaWarp_Arrive) checks the last song played, so other arrivals use the plain one."""
    tgt = table()["entrances"][target_name]["target"][age]
    boot = tgt["fields"].get("NextEventName", "Dm_SY_BancChangeArrive")
    return tgt["level"], tgt["start"], "Dm_SY_BancChangeArrive" if boot == "OcarinaWarp_Arrive" else boot


def _ev(file, event, param, value):
    return {"file": file, "flowchart": file, "event": event, "param": param, "value": value}


def warp_song_ops(song, target_name):
    ev = table()["events"]
    spec = ev["warp_songs"][song]
    c_level, start, _ = _arrival(target_name, "child")
    a_level, a_start, _ = _arrival(target_name, "adult")
    assert start == a_start, target_name
    ops = [_ev(spec["file"], spec["event"], "ChildBanc", c_level), _ev(spec["file"], spec["event"], "AdultBanc", a_level),
           _ev(spec["file"], spec["event"], "NextStartPos", start)]
    if song.startswith("Prelude of Light"):
        p = ev["prelude"]
        # The child Spirit-sage story scene after Prelude stays at the Temple of Time. The Temple-of-Time-only arrival
        # scenes (Light Arrows) don't run where Prelude now leads.
        ops += [{"file": p["file"], "flowchart": p["file"], "add_graph": "Rando_PreludeStory",
                 "nodes": {"warp": {"copy": p["story_warp"], "params_over": {"NextBanc": "Market_Child",
                                                                             "NextStartPos": "LightPrelude"},
                                    "next": "@" + p["story_next"]}}, "start": "warp"},
                {"file": p["file"], "flowchart": p["file"], "event": p["story_switch"], "case": p["story_case"],
                 "next": "Rando_PreludeStory_warp"},
                {"file": p["file"], "flowchart": p["file"], "add_graph": "Rando_PreludeArrive",
                 "nodes": {"done": {"actor": "GameSystemActor", "action": "EventWait",
                                    "params": {"IsWaitEnd": True, "Frames": 1}, "next": None}}, "start": "done"},
                {"file": p["file"], "flowchart": p["file"], "event": p["arrive_switch"], "case": p["arrive_case"],
                 "next": "Rando_PreludeArrive_done"}]
    return ops


def owl_ops(owl, target_name):
    t = table()
    spec = t["events"]["owls"][owl]
    level, start, boot = _arrival(target_name, "child")
    if owl.startswith("DMT"):
        path = t["level_paths"][level]  # preloaded during the flight
        return [_ev(spec["file"], spec["event"], "NextBanc", level),
                _ev(spec["file"], spec["event"], "NextStartPos", start),
                _ev(spec["file"], spec["event"], "BootEventName", boot),
                _ev(spec["file"], spec["preload"], "BancPath", path)]
    # Lake Hylia owl: after the flight scene, change level instead of landing in Hyrule Field
    return [{"file": spec["file"], "flowchart": spec["file"], "add_graph": "Rando_OwlFlight",
             "nodes": {"warp": {"actor": "GameSystemActor", "action": "EventReserveBancChange",
                                "params": _rbc_params(level, start, boot), "next": None}}, "start": "warp"},
            {"file": spec["file"], "flowchart": spec["file"], "event": spec["after_flight"], "next": "Rando_OwlFlight_warp"}]


def spawn_ops(spawn, target_name):
    spec = table()["events"]["spawns"][spawn]
    level, start, boot = _arrival(target_name, "child")
    return [{"file": spec["file"], "flowchart": spec["file"], "add_graph": "Rando_Spawn",
             "nodes": {"warp": {"actor": "GameSystemActor", "action": "EventReserveBancChange",
                                "params": _rbc_params(level, start, boot), "next": "@" + spec["next"]}},
             "start": "warp"},
            {"file": spec["file"], "flowchart": spec["file"], "event": spec["after"], "next": "Rando_Spawn_warp"}]


def jabu_ops(target_name):
    """Jabu-Jabu's first entry (the fish) follows the moved doorway. When Jabu-Jabu's Belly itself moved, its first
    arrival scene (story step) plays the first time Link arrives through its new doorway."""
    spec = table()["events"]["jabu_first_entry"]
    level, start, boot = _arrival(target_name, "child")
    return [_ev(spec["file"], spec["event"], "NextBanc", level), _ev(spec["file"], spec["event"], "NextStartPos", start),
            _ev(spec["file"], spec["event"], "BootEventName", boot)]


# The gate at the bottom of Lake Hylia. Its module opens it (node 2, an OR) on HavePlayedEvent.Dm_WaterTemple_0000
# (node 1) or on SageOfWater being past Step05 (node 3), and node 16 writes that flag from the same step check. Step06
# comes from the temple's arrival scene (SageOfWater_Arrival_WaterTemple), which moves with the doorway. In the
# normal game you can only get in through the gate, so it never shows. With the temple behind another door, walking in
# there opened the gate on the next lake visit, no switch needed. So when the temple moves, the gate only reads the
# flag, which only the switch's scene sets.
LAKE_GATE = {"file": "Logic/HyruleField_LakeHylia_Common_Prefab_6a9d.logic.module.ainb", "edits": [
    {"cut": {"node": 16, "input": "IsDrive", "value": False}},
    {"repoint_source": {"to": 2, "input": "BoolMulti", "old": 3, "from": 1, "output": "Bool"}}]}
WATER_TEMPLE = "Lake Hylia -> Water Temple Lobby"


def plan_for(pairs):
    """Patch plan for [(OoTR entrance, entrance whose vanilla destination it gets), ...]."""
    t = table()
    jabu = t["events"]["jabu_first_entry"]
    placements, events, notes = [], [], []
    if any(target == WATER_TEMPLE and name != target for name, target in pairs):
        ainb_ops = [json.loads(json.dumps(LAKE_GATE))]
    else:
        ainb_ops = []
    for name, target in pairs:
        if name == target:
            continue
        kind = t["entrances"].get(name, {}).get("kind")
        if name in t["events"]["warp_songs"]:
            events += warp_song_ops(name, target)
        elif name in t["events"]["owls"]:
            events += owl_ops(name, target)
        elif name in t["events"]["spawns"]:
            events += spawn_ops(name, target)
        elif kind == "fade":
            ops = fade_ops(name, target)
            if target == jabu["entrance"]:  # Jabu-Jabu's Belly now behind this doorway
                for op in ops:
                    op["set"]["Dynamic.InitEventFlag"] = "HavePlayedEvent." + jabu["boot"]
                    op["set"]["Dynamic.InitEventName"] = jabu["boot"]
                    op["remove"] = [r for r in op["remove"] if r not in ("Dynamic.InitEventFlag",
                                                                         "Dynamic.InitEventName")]
            placements += ops
            if name == jabu["entrance"]:
                events += jabu_ops(target)
        else:
            raise RuntimeError(f"entrance {name} ({kind}) can't be moved in the remake")
        notes.append(f"{name}  =>  where {target} leads")
    return {"placements": placements, "events": events, "ainb": ainb_ops}, notes


def world_plan(settings, world):
    if not world.entrance_shuffle:
        return {}
    pairs = [(e.name, e.replaces.name) for e in world.get_shuffled_entrances()
             if e.replaces is not None and e.replaces is not e]
    plan, notes = plan_for(sorted(pairs))
    plan = {k: v for k, v in plan.items() if v}
    if notes:
        plan["entrances"] = notes  # only for people to read: the moved entrances, as OoTR's spoiler names them
    return plan


def untested(settings):
    out = []
    for name in UNTESTED:
        v = getattr(settings, name, None)
        if v and v != "off":
            out.append(f"{name} = {v!r}")
    return out
