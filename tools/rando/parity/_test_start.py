"""Test start (dev only). A test build's new file asks which test to play, sets up what that test needs and starts
right at its spot. I'm not going to play through the game 200 times to get to my tests, so the build spawns me
where the test is, with its prerequisites.

Only a plan settings file with a top-level "test_start" section turns it on (generate.py main passes it to configure
before the seed is made). No setting, preset or app option reaches it, so every other seed is byte-identical without
it. The section:

  "test_start": {"tests": [
     {"title": "LW scrub near the bridge",        # the menu line (keep it short: about 28 characters)
      "age": "child" | "adult",                   # adult: the game's own child-to-adult steps first
      "at": {"location": "LW Deku Scrub Near Bridge"}   # an OoTR location (scrub, drop spot, chest), or
            | {"gyaml": "Npc_Hylia_044_Adult", "level": "HountedWasteland_Adult"}   # an actor of a level, or
            | {"file": "Banc/...bcett.byml.zs", "hash": "123"} | {"level": L, "pos": [x, y, z], "yaw": deg}
            | {"level": L, "start": "EntrancePos"},  # a named start position of the level (a dungeon's entrance:
                                                    # a respawn test there is left and re-entered in a few steps)
      "dist": 2.5, "side": 0,                     # stand this far from it, at this angle from its front (degrees)
      "time": [21, 0],                            # hour, minute (optional)
      "items": {"Progressive Wallet": 2},         # OoTR items added silently (world_settings.starting_adds)
      "rupees": 300,                              # added after the items (the wallet caps it)
      "flags": {"GameDataName": true | int},      # Bool or Int save data (optional)
      "quests": {"Get_Epona": "ReadyForGetEponaSong"},  # quests moved on to a step (optional, after the flags)
      "target": [x, y, z],                        # what the reach check walks to (default: the spot's actor)
      "reach": "why",                             # the target needs more than walking from the spot (an item, a
                                                  # puzzle): the reach check only reports it
      "snap": false},                             # keep the computed height (default: stand on the floor there)
     ...]}

What the patch does (read from the files: OpeningEvent, Market_Child_Field_ChildToAdult, GetPouchContent):
- The new-file opening (OpeningEvent:Opening_Introduction, Event11, where the story plugin's start steps and the
  password already run) calls GetPouchContent:Rando_TestHub. That's a system text box with choices, done the
  password's way (EventTalk ChoiceNumber 4, its option labels "0100"... of EventFlowMsg/Dm_SY_Get.msbt, the answer
  read by GameSystemActor.EventQueryTalkChoice4), with three tests per box plus "More tests...". The first entry
  plays normally.
- A picked test calls DoorOfTime:Rando_Test<N>, since DoorOfTime has every actor the steps need. It adds the items
  (PouchSystemActor.EventTriggerAddOrRemovePouchContent, IsGetEvent off, like the starting items), the rupees
  (PouchSystemActor.EventTriggerIncreaseRupee, the fishing pond's), the flags (GameDataActor) and the time
  (EventWorldManagerController.EventTrigger_SetTime, like the opening's own Event9). For an adult it runs the
  game's own child-to-adult steps (ReplaceEquipmentForEraChange, then Sequence_IsChildhood False:
  Market_Child_Field_ChildToAdult Event3/Event1). Then come the level's preload and the level change to the spot
  (GameSystemActor.EventReserveBancChange with NextPosition / NextStartRot, like that flow's Event0). The opening
  then saves, and the new file starts there.
A new file is a new test, no reinstall.

The spot is put on the floor under it, the first walkable surface from 2.5 m above with Link's headroom, because a
spot inside a slope made Link fall through the level. Every test is read back on the level's collision
(tools/reach.py). The spot has to be standable, and the target (its actor) within reach of a walk/drop/climb from
it, unless the test says why it isn't ("reach"). The results go into the plan note, and verify reports a spot that
isn't standable or can't reach its target without a reason, because tests did start where they couldn't be done."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OWNS = {}
READERS = {"test_start": "verify"}
HUB_FILE, HUB = "GetPouchContent", "Rando_TestHub"
TEST_FILE, TEST_ENTRY = "DoorOfTime", "Rando_Test{}"
MSBT = "EventFlowMsg/Dm_SY_Get.msbt"
MSG = "EventFlowMsg/Dm_SY_Get:{}"
OPT0, MORE = 100, 99  # option labels: "0100" + test index, "0099" more tests (the password uses 0000-0006)
GROUP0, MOREG, BACK = 600, 97, 98  # "0600" + group index, "0097" more groups, "0098" back to the group list
NORMAL = {"title": "Play normally (no test)"}
_spec = {"tests": None, "probes": ()}
# Probe "bossrush_chest": can a check live in a boss-rush chest? The ten chests of
# DreamWorld/BossRushIntervalRoom_Static (one per room before a boss, 200 rupees on every run) sit inside the rush,
# which lends Link a preset pouch per boss and gives his own back afterwards. This probe puts a Hylian Shield in the
# room-before-Gohma chest (child and full rushes). A child may own it and the child kit is unlikely to hold one, so a
# test shows whether an item handed over in the rush is still owned once the rush ends. Probe builds only.
BOSSRUSH_PROBE = "bossrush_chest"
BOSSRUSH_CHEST = "DreamWorld/chest/7589985979641292928"  # data/rewards.json: Obj_TBox_A_01, vanilla TBox_Rupee_Gold
BOSSRUSH_ITEM = "TBox_Shield_Hylian"  # config/item_map.json "Hylian Shield"


def configure(section):
    """Takes the settings file's "test_start" section, None turns it off."""
    _spec["tests"] = None if not section else [NORMAL] + list(section.get("tests") or [])
    _spec["probes"] = tuple((section or {}).get("probes") or ())


def probe(name):
    """Whether this test build asks for in-game probe `name`. A probe is a change normal seeds don't get until it has
    passed in game, e.g. "kf_heart" for parity/drops.py _new_type_ok."""
    return name in _spec["probes"]


def active():
    return bool(_spec["tests"])


def opening(settings, world):
    return [f"{HUB_FILE}:{HUB}"] if active() else []


# The spots
def _level_of(path):
    """'Banc/LostWood/LostWood_Child_Static.bcett.byml.zs' -> 'LostWood_Child'."""
    base = os.path.basename(path).split(".")[0]
    for tail in ("_Static", "_Dynamic"):
        if base.endswith(tail):
            return base[:-len(tail)]
    return base


def _files_of(level):
    area = None
    paths = json.load(open(os.path.join(HERE, "data", "rando", "entrances_remake.json"), encoding="utf-8"))["level_paths"]
    if level in paths:
        area = paths[level].split("/")[-2]
    if area is None:
        raise ValueError(f"test start: no level {level} (data/rando/entrances_remake.json level_paths)")
    return [f"Banc/{area}/{level}_{k}.bcett.byml.zs" for k in ("Static", "Dynamic")]


def _actors(fs, path):
    from romtools import byml_load
    try:
        return byml_load(fs.read(path), allow_big=True)[0].get("Actors") or []
    except (FileNotFoundError, OSError, KeyError):
        return []


def _placements(at, age):
    """[(file, hash)] that a test's "at" names, so an OoTR location's placements (shop_map, drop_map, chest_map)."""
    loc = at["location"]
    out = []
    shop = json.load(open(os.path.join(HERE, "data", "rando", "shop_map.json"), encoding="utf-8"))["locations"].get(loc)
    if shop:
        out += [(p["file"], str(p["hash"])) for p in ((shop.get("edit") or {}).get("placements") or [])]
    if not out:
        import drops as drop_tools
        e = drop_tools.lookup(loc) or {}
        out += [(p["file"], str(p["hash"])) for p in e.get("placements", [])]
    if not out:  # a chest, the core's (chest_map) or the chests plugin's own (chests_locations new and paired)
        ch = json.load(open(os.path.join(HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"].get(loc)
        if not (ch and ch.get("remake")):
            own = json.load(open(os.path.join(HERE, "data", "rando", "chests_locations.json"), encoding="utf-8"))
            ch = (own.get("new") or {}).get(loc) or (own.get("paired") or {}).get(loc)
        if ch and ch.get("remake"):
            r = next((x for x in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))
                      if x["id"] == ch["remake"]), None)
            if r:
                out += [(f, str(r["hash"])) for f in r.get("files", [])]
    want = "_Adult" if age == "adult" else "_Child"
    aged = [x for x in out if want in x[0]]
    res = aged or [x for x in out if "_Child" not in x[0] and "_Adult" not in x[0]] or out
    # A spot at a map edge is placed in both levels. The Lost Woods bridge scrub's Kokiri Forest copy stands at the
    # edge of that map, and a new file starting on it falls forever. So we start in the location's own area
    # (data/ootr_match.json "area"), the way Link reaches it in play.
    home = [x for x in res if x[0].split("/")[1:2] == [_ootr_area(loc)]]
    return home or res


def _ootr_area(loc):
    """The remake area (Banc folder) an OoTR location belongs to (data/ootr_match.json), or None."""
    global _AREAS
    if _AREAS is None:
        rows = json.load(open(os.path.join(HERE, "data", "ootr_match.json"), encoding="utf-8"))["ootr_locations"]
        _AREAS = {r["ootr"]: r.get("area") for r in (rows.values() if isinstance(rows, dict) else rows)
                  if isinstance(r, dict) and r.get("ootr")}
    return _AREAS.get(loc)


_AREAS = None


def _target(at, age):
    """(level, [x, y, z]) of a spot the data files only place by position, else None. That's a silver rupee ("<puzzle>
    Silver Rupee Spot <n>", data/rando/silver_rupees.json) or a generic cow (data/rando/songs_trade_cows.json)."""
    loc = at.get("location", "")
    if " Silver Rupee Spot " in loc:
        puzzle, n = loc.rsplit(" Silver Rupee Spot ", 1)
        p = json.load(open(os.path.join(HERE, "data", "rando", "silver_rupees.json"), encoding="utf-8"))["puzzles"].get(puzzle)
        if p:
            return _level_of(p["file"]), [float(v) for v in p["positions"][int(n) - 1]]
    cows = json.load(open(os.path.join(HERE, "data", "rando", "songs_trade_cows.json"), encoding="utf-8"))["generic"]
    for c in cows:
        if loc in c["ootr"]:
            return f"{c['area']}_{'Adult' if age == 'adult' else 'Child'}", [float(v) for v in c["cow"]]
    return None


def _facing(level, target, offset):
    pos = [round(t + o, 3) for t, o in zip(target, offset)]
    yaw = math.degrees(math.atan2(target[0] - pos[0], target[2] - pos[2])) % 360.0
    return level, pos, round(yaw, 2)


SNAP_UP, SNAP_DOWN = 1.0, 3.0  # Max snap above a slope / down to the floor.
# A bigger jump likely found the wrong floor. Collision data can miss interiors, moving rooms and invisible platforms.


def _start_pos(fs, level, name):
    """(pos, yaw) of the level's start position `name` (a placement Name, e.g. a dungeon's "EntrancePos")."""
    for f in _files_of(level):
        for a in _actors(fs, f):
            if a.get("Name") == name and "Translate" in a:
                yaw = math.degrees(float((a.get("Rotate") or [0, 0, 0])[1])) % 360.0
                return [round(float(v), 3) for v in a["Translate"]], round(yaw, 2)
    raise ValueError(f"test start: {level} has no placement named {name}")


def _world(fs, level, age, center, radius=30.0):
    """The level's collision around `center` (tools/reach.py World), or None if it can't be read."""
    import re
    import reach
    m = re.match(r"^(.+?)_(Child|Adult)(?:_(\w+))?$", level)
    area, lv_age, variant = (m.group(1), m.group(2), m.group(3)) if m else (level, None, None)
    try:
        return reach.World(fs, area, lv_age or ("Adult" if age == "adult" else "Child"), center=center, radius=radius,
                           variant=variant)
    except Exception:  # noqa: BLE001 (a level the collision reader can't decode: no snap, reported as unchecked)
        return None


def _snap(w, pos, age):
    """The spot moved onto the floor under it: the first up-facing surface from 2.5 m above with Link's headroom."""
    import reach
    height = reach.const(w.fs, f"{age}.PlayerHeight")
    x, y, z = pos
    top = y + 2.5
    for _ in range(6):
        h = w.floor_below((x, top, z), max_drop=top - (y - 12.0))
        if h is None:
            return None
        fy = float(h.y)
        if h.normal[1] >= reach.NavGrid.MAX_SLOPE_NY and w.ray((x, fy + 0.05, z), (x, fy + height, z)) is None:
            return [round(x, 3), round(fy + 0.05, 3), round(z, 3)]
        top = fy - 0.05
    return None


def check_spot(fs, level, pos, target, age):
    """{"stand": bool, "reach": bool | None, "why": str} for a test spot on the level's collision."""
    import reach
    w = _world(fs, level, age, pos, radius=max(30.0, math.dist(pos[::2], target[::2]) + 20.0))
    if w is None:
        return {"stand": None, "reach": None, "why": "collision not readable"}
    snapped = _snap(w, pos, age)
    if snapped is None or abs(snapped[1] - pos[1]) > 0.3:
        return {"stand": False, "reach": None, "why": f"no floor with headroom at the spot (found {snapped})"}
    x0, x1 = sorted((pos[0], target[0]))
    z0, z1 = sorted((pos[2], target[2]))
    g = reach.NavGrid(w, x0 - 6, z0 - 6, x1 + 6, z1 + 6, age, cell=0.5,
                      ymin=min(pos[1], target[1]) - 10.0, ymax=max(pos[1], target[1]) + 10.0)
    start = g.node_at(pos, tol=0.6)
    if start is None:
        return {"stand": False, "reach": None, "why": "the spot is no walk-grid floor (too steep or no headroom)"}
    seen = g.reach([start])
    near = [n for n in seen if math.hypot(g.xs[n[0][0]] - target[0], g.zs[n[0][1]] - target[2]) <= 2.5
            and abs(g.floors[n[0]][n[1]][0] - target[1]) <= 2.5]
    return {"stand": True, "reach": bool(near),
            "why": f"{len(seen)} floors reached, {len(near)} within reach of the target"}


def spot(test, fs):
    """(level, [x, y, z], yaw in degrees) where the test starts. Either `dist` metres from its actor at `side` degrees
    from the actor's front (its Rotate Y), facing it, or at `offset` from a position (an explicit "target", a silver
    rupee, a cow), facing it, or an explicit "pos" and "yaw"."""
    level, pos, yaw, _ = spot_and_target(test, fs)
    return level, pos, yaw


def spot_and_target(test, fs):
    """(level, pos, yaw, target position) of a test: spot() before the snap, and what the test is about."""
    at, age = test["at"], test.get("age", "child")
    if "pos" in at:
        p = [float(v) for v in at["pos"]]
        return at["level"], p, float(at.get("yaw", 0.0)), [float(v) for v in test.get("target", p)]
    if "start" in at:
        p, yaw = _start_pos(fs, at["level"], at["start"])
        return at["level"], p, yaw, [float(v) for v in test.get("target", p)]
    offset = [float(v) for v in test.get("offset", (0.0, 0.3, 2.0))]
    if "target" in at:
        tg = [float(v) for v in at["target"]]
        return _facing(at["level"], tg, offset) + (tg,)
    t = _target(at, age)
    if t is not None:
        return _facing(t[0], t[1], offset) + ([float(v) for v in t[1]],)
    if "location" in at:
        cands = _placements(at, age)
    elif "gyaml" in at:
        cands = [(f, str(a["Hash"])) for f in _files_of(at["level"]) for a in _actors(fs, f)
                 if a.get("Gyaml") == at["gyaml"]][at.get("index", 0):][:1]
    else:  # a placement by hash, in a file or in either file of a level
        cands = [(f, str(at["hash"])) for f in (_files_of(at["level"]) if "level" in at else [at["file"]])]
    for f, h in cands:
        a = next((x for x in _actors(fs, f) if str(x.get("Hash")) == h), None)
        if a is None:
            continue
        x, y, z = (float(v) for v in a.get("Translate", [0, 0, 0]))
        yaw = float((a.get("Rotate") or [0, 0, 0])[1]) + math.radians(float(test.get("side", 0)))
        d = float(test.get("dist", 2.0))
        pos = [round(x + d * math.sin(yaw), 3), round(y + float(test.get("up", 0.3)), 3), round(z + d * math.cos(yaw), 3)]
        tg = [float(v) for v in test.get("target", (x, y, z))]
        return _level_of(f), pos, round((math.degrees(yaw) + 180.0) % 360.0, 2), tg
    raise ValueError(f"test start: {test.get('title')}: no placement found for {at}")


# The plan
def _talk(label, choices):
    from parity._chests_scenes import TALK_PARAMS
    p = dict(TALK_PARAMS, MessageId=MSG.format(label), ChoiceNumber=len(choices))
    for k in range(4):
        p[f"ChoiceLabel{k + 1}"] = choices[k] if k < len(choices) else 0
    return {"actor": "SystemTextNPC", "action": "EventTalk", "params": p}


def _groups(tests):
    """[(group name, [test index])] in first-seen order, from each test's "group" (tests[0] is NORMAL: none)."""
    out = {}
    for i, t in enumerate(tests[1:], 1):
        out.setdefault(str(t.get("group") or "Tests"), []).append(i)
    return list(out.items())


def _pages(items, size=3):
    return [items[i:i + size] for i in range(0, len(items), size)]


def hub_graph(tests):
    """(nodes, start). Tests with a "group" get grouped, because scrolling through all the tests is a pain. The first
    boxes list the groups, three per box plus "More groups..." (the last box's goes back to the first), with "Play
    normally" after the last group. A group's box lists its tests, three per box plus "More tests..." to its next box,
    and on its last box "Back to the list" (the group box it came from). So any test is two picks away, plus a "More
    groups..." per three groups. Without groups it's pages of three tests and "More tests..." (the last page's More
    goes back to the first). A box with fewer than three entries repeats its last one in the free slots."""
    groups = _groups(tests)
    if len(groups) > 1:
        return _grouped_graph(groups)
    return _flat_graph(len(tests))


def _grouped_graph(groups):
    n = {}
    entries = [("g", gi) for gi in range(len(groups))] + [("normal", 0)]
    gpages = _pages(entries)
    home = {}
    for p, page in enumerate(gpages):
        slots = (page + [page[-1]] * 3)[:3]
        labels = [GROUP0 + e[1] if e[0] == "g" else OPT0 for e in slots]
        n[f"g{p}"] = dict(_talk(f"Rando_TestHubG{p}", labels + [MOREG]), next=f"g{p}q")
        n[f"g{p}q"] = {"actor": "GameSystemActor", "query": "EventQueryTalkChoice4",
                       "cases": {k: (f"x{e[1]}p0" if e[0] == "g" else None) for k, e in enumerate(slots)}}
        n[f"g{p}q"]["cases"][3] = f"g{(p + 1) % len(gpages)}"
        for e in page:
            if e[0] == "g":
                home[e[1]] = f"g{p}"
    for gi, (name, idx) in enumerate(groups):
        tpages = _pages(idx)
        for p, page in enumerate(tpages):
            slots = (page + [page[-1]] * 3)[:3]
            last = p == len(tpages) - 1
            n[f"x{gi}p{p}"] = dict(_talk(f"Rando_TestHub{gi}_{p}", [OPT0 + i for i in slots] + [BACK if last else MORE]),
                                   next=f"x{gi}p{p}q")
            n[f"x{gi}p{p}q"] = {"actor": "GameSystemActor", "query": "EventQueryTalkChoice4",
                                "cases": {k: f"t{slots[k]}" for k in range(3)}}
            n[f"x{gi}p{p}q"]["cases"][3] = home[gi] if last else f"x{gi}p{p + 1}"
            for i in page:
                n[f"t{i}"] = {"call": f"{TEST_FILE}:{TEST_ENTRY.format(i)}", "next": None}
    return n, "g0"


def hub_texts(tests):
    """The menu's message entries (Dm_SY_Get.msbt): the boxes' prompts and every choice line."""
    def entry(label, markup):
        return {"lang": "*", "file": MSBT, "label": label, "add": True, "note": "test start", "markup": markup}
    groups = _groups(tests)
    text = [entry(f"{OPT0 + i:04d}", (f"{i}: " if i else "") + str(t.get("title"))[:40]) for i, t in enumerate(tests)]
    text.append(entry(f"{MORE:04d}", "More tests..."))
    if len(groups) > 1:
        gpages = _pages(list(range(len(groups) + 1)))
        text += [entry(f"Rando_TestHubG{p}", f"Test build: pick a group (page {p + 1} of {len(gpages)}).")
                 for p in range(len(gpages))]
        for gi, (name, idx) in enumerate(groups):
            span = f"{idx[0]}" if len(idx) == 1 else f"{idx[0]}-{idx[-1]}"
            text.append(entry(f"{GROUP0 + gi:04d}", f"{name} ({span})"[:40]))
            tpages = _pages(idx)
            text += [entry(f"Rando_TestHub{gi}_{p}", f"{name}: pick a test"
                           + (f" (page {p + 1} of {len(tpages)})." if len(tpages) > 1 else "."))
                     for p in range(len(tpages))]
        text += [entry(f"{MOREG:04d}", "More groups..."), entry(f"{BACK:04d}", "Back to the list")]
    else:
        pages = (len(tests) + 2) // 3
        text += [entry(f"Rando_TestHub{p}", f"Test build: pick a test (page {p + 1} of {pages}).")
                 for p in range(pages)]
    return text


def _flat_graph(n_tests):
    n = {}
    pages = [list(range(i, min(i + 3, n_tests))) for i in range(0, n_tests, 3)]
    for p, idx in enumerate(pages):
        slots = (idx + [idx[-1]] * 3)[:3]
        n[f"p{p}"] = dict(_talk(f"Rando_TestHub{p}", [OPT0 + i for i in slots] + [MORE]), next=f"p{p}q")
        n[f"p{p}q"] = {"actor": "GameSystemActor", "query": "EventQueryTalkChoice4",
                       "cases": {k: (f"t{slots[k]}" if slots[k] else None) for k in range(3)}}
        n[f"p{p}q"]["cases"][3] = f"p{(p + 1) % len(pages)}"
    for i in range(1, n_tests):
        n[f"t{i}"] = {"call": f"{TEST_FILE}:{TEST_ENTRY.format(i)}", "next": None}
    return n, "p0"


_bools = []
ADULT_MAP_SCENE = "HavePlayedEvent.Dm_TimeTemple_0065"


def _is_bool(fs, name):
    """True if the game's save data has a Bool called `name`."""
    if not _bools:
        from romtools import byml_load
        gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
        _bools.append({e["Hash"] for e in gd["Data"]["Bool"]})
    from romtools import murmur3_32
    return murmur3_32(name) in _bools[0]


def test_steps(test, fs):
    """[(node)] of one test's entry, in order, and its spot."""
    import progressive
    import world_settings
    steps = []
    for name, count in sorted((test.get("items") or {}).items()):
        for actor, num in world_settings.starting_adds(name, count):
            steps.append({"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
                          "params": {"Actor": actor, "Num": num, "IsEquipDIrect": False, "IsGetEvent": False,
                                     "IsSetMessageTargetActorName": False}})
            after = (progressive.GIVE.get(actor) or {}).get("after") if actor in progressive.NO_POSE else None
            if after:  # an ocarina gets its "after" entry (equipment sync, action guide) like every ocarina give
                steps.append({"call": after})
    steps += world_settings.count_steps([s for name, count in sorted((test.get("items") or {}).items())
                                         for s in world_settings.count_sets(name, count)])  # a token count
    if test.get("rupees"):
        steps.append({"actor": "PouchSystemActor", "action": "EventTriggerIncreaseRupee",
                      "params": {"Value": int(test["rupees"])}})
    for name, value in sorted((test.get("flags") or {}).items()):
        if isinstance(value, bool):
            steps.append({"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                          "params": {"GameDataName": name, "Value": value, "Index": -1}})
        else:
            steps.append({"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                          "params": {"GameDataName": name, "Value": int(value), "Index": -1}})
    if test.get("quests"):
        from parity.story import progress
        steps += [progress(quest, step) for quest, step in sorted(test["quests"].items())]
    if test.get("time"):
        h, m = test["time"]
        steps.append({"actor": "EventWorldManagerController", "action": "EventTrigger_SetTime",
                      "params": {"TimeHour": int(h), "TimeMin": int(m)}})
    if test.get("age", "child") == "adult":
        steps.append({"call": "ReplaceEquipmentForEraChange:ReplaceEquipmentForEraChange"})
        steps.append({"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                      "params": {"GameDataName": "Sequence_IsChildhood", "Value": False, "Index": -1}})
    level, pos, yaw, target = spot_and_target(test, fs)
    age = test.get("age", "child")
    w = _world(fs, level, age, pos) if test.get("snap", True) else None
    snapped = _snap(w, pos, age) if w is not None else None
    if snapped is not None and -SNAP_DOWN <= snapped[1] - pos[1] <= SNAP_UP:
        pos = snapped
    else:  # no floor near: a floor the decoded collision lacks (an interior, a moving room, invisible platforms)
        snapped = None
    check = check_spot(fs, level, pos, target, age)
    check["snapped"] = snapped is not None
    # Each place's map stays "Unavailable right now" until the place counts as visited (IsVisitLocation.<place>,
    # read by main 0x805A5C60 when the map opens), which its arrival marks. A test start skips the arrival.
    # An adult's maps also wait for his first look at the ruined Market (main 0x80B47D70 reads
    # HavePlayedEvent.Dm_TimeTemple_0065), which a test start skips too.
    visit = [f"IsVisitLocation.{level.split('_')[0]}"] + (
        [ADULT_MAP_SCENE] if test.get("age", "child") == "adult" else [])
    for flag in visit:
        if flag not in (test.get("flags") or {}) and _is_bool(fs, flag):
            steps.append({"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                          "params": {"GameDataName": flag, "Value": True, "Index": -1}})
    paths = json.load(open(os.path.join(HERE, "data", "rando", "entrances_remake.json"), encoding="utf-8"))["level_paths"]
    steps.append({"actor": "GameSystemActor", "action": "EventTriggerBancRequestBeforehandLoad",
                  "params": {"BancPath": paths[level], "IsTargetRetry": False}})
    steps.append({"actor": "GameSystemActor", "action": "EventReserveBancChange",
                  "params": {"IsWaitEnd": True, "IsStartOnEvent": False, "NextStartPos": "", "NextBanc": level,
                             "BootEventName": "", "FadePattern": 2, "EventStarterName": "", "IsItemWarp": False,
                             "NextPosition": pos, "NextStartRot": [0.0, yaw, 0.0]}})
    return steps, (level, pos, yaw, check)


def world_plan(settings, world):
    if not active():
        return {}
    from romtools import Romfs
    fs = Romfs(os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(), os.path.join(HERE, "original"))
    tests = _spec["tests"]
    events, summary = [], []
    nodes, start = hub_graph(tests)
    events.append({"file": HUB_FILE, "flowchart": HUB_FILE, "add_graph": HUB, "nodes": nodes, "start": start})
    for i, test in enumerate(tests[1:], 1):
        steps, where = test_steps(test, fs)
        n = {f"s{k}": dict(s, next=f"s{k + 1}" if k + 1 < len(steps) else None) for k, s in enumerate(steps)}
        events.append({"file": TEST_FILE, "flowchart": TEST_FILE, "add_graph": TEST_ENTRY.format(i), "nodes": n,
                       "start": "s0"})
        summary.append({"n": i, "title": test.get("title"), "age": test.get("age", "child"), "level": where[0],
                        "pos": where[1], "yaw": where[2], "spot": where[3], "reach_note": test.get("reach")})
    out = {"events": events, "text": hub_texts(tests), "_gaps": {"test_start": {"tests": summary}}}
    if probe(BOSSRUSH_PROBE):  # Only probe builds swap the chest's reward.
        out["rewards"] = {BOSSRUSH_CHEST: {"item": BOSSRUSH_ITEM, "note": "test_start probe bossrush_chest: the boss rush's "
                                                             "room-before-Gohma chest gives a Hylian Shield"}}
        out["_gaps"]["test_start"]["probes"] = {BOSSRUSH_PROBE: {"reward": BOSSRUSH_CHEST, "item": BOSSRUSH_ITEM}}
    return out


def UNTESTED(settings):
    return ["test start (a dev test build: the new file picks a test and starts at its spot)"] if active() else []


# Read-back
def verify(patch, note, romfs):
    """Checks that the opening calls the hub, every test is one pick away and its entry ends in the level change to its
    spot, with the age, time, items, rupees and flags the plan asked for, and that the menu texts exist."""
    from romtools import Romfs
    from evfl import Evfl
    from parity import _dungeons_routes as R
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    flows = {}

    def fc_of(name):
        if name not in flows:
            flows[name] = next(f for f in Evfl(fs.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts
                               if f["name"] == name)
        return flows[name]

    op = fc_of("OpeningEvent")
    ep = op["entry_points"]["Opening_Introduction"]
    if not any(R._call(op, op["events"][i]) == f"{HUB_FILE}:{HUB}"
               for i in R._reachable(op, [ep["main"]])):
        bad.append(f"OpeningEvent: the new-file opening doesn't call {HUB_FILE}:{HUB}")
    hub = fc_of(HUB_FILE)
    if HUB not in hub["entry_points"]:
        return bad + [f"{HUB_FILE}: no entry {HUB}"]
    called = {R._call(hub, hub["events"][i]) for i in R._entry_steps(hub, HUB)}
    door = fc_of(TEST_FILE)
    for t in (note or {}).get("tests", []):
        entry = TEST_ENTRY.format(t["n"])
        if f"{TEST_FILE}:{entry}" not in called:
            bad.append(f"{HUB}: test {t['n']} ({t['title']}) can't be picked")
        if entry not in door["entry_points"]:
            bad.append(f"{TEST_FILE}: no entry {entry}")
            continue
        steps = [door["events"][i] for i in R._entry_steps(door, entry)]
        warp = [e for e in steps if e["type"] == "action"
                and door["actors"][e["actor"]]["actions"][e["action"]] == "EventReserveBancChange"]
        if len(warp) != 1:
            bad.append(f"{TEST_FILE}:{entry}: {len(warp)} level changes, want 1")
            continue
        p = R._params(warp[0])
        if p.get("NextBanc") != t["level"] or [round(v, 3) for v in p.get("NextPosition") or []] != t["pos"]:
            bad.append(f"{TEST_FILE}:{entry}: goes to {p.get('NextBanc')} {p.get('NextPosition')}, want {t['level']} "
                       f"{t['pos']}")
        sp = t.get("spot") or {}
        if sp.get("stand") is False and not t.get("reach_note"):
            bad.append(f"test {t['n']} ({t['title']}): the spot isn't standable ({sp.get('why')})")
        if sp.get("reach") is False and not t.get("reach_note"):
            bad.append(f"test {t['n']} ({t['title']}): its target can't be reached by walking from the spot "
                       f"({sp.get('why')}); give what the route needs and say so (\"reach\"), or move the spot")
        adult = any(e["type"] == "action" and R._params(e).get("GameDataName") == "Sequence_IsChildhood"
                    and R._params(e).get("Value") is False for e in steps)
        if adult != (t["age"] == "adult"):
            bad.append(f"{TEST_FILE}:{entry}: starts as {'adult' if adult else 'child'}, want {t['age']}")
    pr = ((note or {}).get("probes") or {}).get(BOSSRUSH_PROBE)
    if pr:  # the boss-rush chest probe: the chest's drop is the probe's item in the patched room
        from romtools import byml_load
        _, _, h = pr["reward"].split("/")
        rel = "Banc/DreamWorld/BossRushIntervalRoom_Static.bcett.byml.zs"
        a = next((x for x in byml_load(fs.read(rel), allow_big=True)[0].get("Actors") or [] if str(x.get("Hash")) == h),
                 None)
        got = ((a or {}).get("Dynamic") or {}).get("Drop__DropActor")
        if got != pr["item"]:
            bad.append(f"probe {BOSSRUSH_PROBE}: chest {h} drops {got}, want {pr['item']}")
    return bad
