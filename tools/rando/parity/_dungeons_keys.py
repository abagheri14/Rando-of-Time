"""Small-key credits written the way the game writes its own keys (dungeons plugin).

The game's key add (GameSystemActor.EventGetDungeonSmallKey -> OneShotDungeonGetSmallKey, main 0x33ac500) works on
the dungeon the player stands in. It calls AddSmallKey 0x3283160, then sets UI_RequestSmallKeyCountUpDemo := True.
Dm_SY_Treasurebox Event30 and the key pickups run it. It writes three rows of that dungeon:
DungeonInfo.<area>.IsGetSmallKeyOnce := True (when the count was 0), SmallKeyTotalNum += n and SmallKeyNum += n.
The get scene around it then asks the HUD for the key counter (Dm_SY_TreasureboxSmall Event128 / Dm_SY_Get
Event175 UISystemActor.EventTriggerSetDisplaySmallKey, then 50 frames).

What reads them (main):
- SmallKeyNum: the doors (Obj_DoorChainLock AIs spend it) and the shown number, read live (main 0xb2b260). The
  HUD's per-frame key update (0x586170) rewrites a shown counter's number whenever the count changes.
- IsGetSmallKeyOnce: whether the number is shown at all, in the dungeon the player stands in. That's the HUD key
  counter and the map screen's small-key slot next to the map, compass and boss key.
  The HUD's update method (0x583fe0, vtable 0x4be8600) sets its show byte +0x235c from 0x586420. That's a get
  scene's display request, or on a dungeon map the current dungeon's IsGetSmallKeyOnce, or in Market_Child
  MiniGame_ChoiceTreasure_IsPlaying. Its boss-key byte +0x235d comes from 0x587260, the current dungeon's
  IsGetBossKey. On the map screen, main 0x33e1600 fills the four slots from IsGetMap, IsGetCompass, IsGetBossKey
  and IsGetSmallKeyOnce, and 0xb29684 shows the slot and its number T_KeyNum_00 (the live SmallKeyNum). Same as
  OoT's key counter, which stays hidden until the dungeon's first key.
- SmallKeyTotalNum: nothing a player sees and no door or logic. Its one reader is the event query
  QueryDungeonGetTotalGetSmallKeyNum (main 0x29ebc40), and no event flow or AI file of the game uses that.
Clawshot (hiKareeem/Clawshot, MIT, src/clawshot/patch/keys.py, which I've played) writes the same three rows and
adds the count-up request for keys of the dungeon the player is in.

A credit that only adds to SmallKeyNum opens the doors but leaves the dungeon's key counter and map-screen key
hidden until a key the game gives itself. So every credit writes all three (key_steps), and 'remove' starts a new
file with all three set.
A whole credit (show=True) then calls SHOW_CALL with the key's dungeon map. When the player stands in that dungeon
(Sequence_CurrentBanc, the current map's name, a saved String64 that OotrR's navi_return.rs compares the same way)
it runs the game's counter steps: the count-up request, 1 frame, EventTriggerSetDisplaySmallKey, 50 frames
(MiniGame_SequentialChoiceTreasure_GetKey's tail). So the counter comes up with its count-up during the get scene,
like after one of the game's keys. The flag alone would show it once the HUD's update runs again. A key for another
dungeon shows nothing, same as in the game (the HUD would show the current dungeon's number).
A boss key works the same way (dungeons.host_call's BOSS_ENTRY, and key rings that carry it): IsGetBossKey, then
BOSS_SHOW_CALL, and on its map the game's EventTriggerSetDisplayBossKey and 50 frames. That's Dm_SY_Treasurebox
Event82/Event94 after Event27 EventGetDungeonBossKey, whose add (main OneShotDungeonGetBossKey) only writes the
flag.

Read-back: verify() (parity/_gaps_check.py READERS "small_keys")."""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# the shared entry's argument name -> the DungeonInfo.<area> row it names
KEY_ROWS = {"GameDataName": "SmallKeyNum", "OnceName": "IsGetSmallKeyOnce", "TotalName": "SmallKeyTotalNum"}
BANC_ARG = "BancName"  # the shared entry's argument naming the key's dungeon map (SHOW_CALL's argument)
CURRENT = "Sequence_CurrentBanc"  # the map the player is on ("ForestTemple", "GerudoFortress_Adult", ...)
SHOW_FILE, SHOW_ENTRY = "GetPouchContent", "Rando_DI_KeyShow"  # GetPouchContent, so resident get scenes can call it
SHOW_CALL = f"{SHOW_FILE}:{SHOW_ENTRY}"
COUNT_UP = "UI_RequestSmallKeyCountUpDemo"
BOSS_ENTRY = "Rando_DI_BossKey"  # the shared boss-key entry in Dm_SY_GetInEvent (dungeons.host_call)
BOSS_ROW = "IsGetBossKey"
BOSS_SHOW_ENTRY = "Rando_DI_BossKeyShow"
BOSS_SHOW_CALL = f"{SHOW_FILE}:{BOSS_SHOW_ENTRY}"
# DungeonInfo area -> its map (Banc/<folder>/<map>_Static.bcett.byml.zs). The other maps are named like their area.
MAPS = {"GerudoFortress": "GerudoFortress_Adult"}


def banc(area):
    """The map a dungeon's keys are shown in (Sequence_CurrentBanc's value there)."""
    return MAPS.get(area, area)


def key_rows(area):
    """{argument name: value} for dungeon area `area`, the shared key entry's call arguments. That's its three save-data
    rows and its map."""
    return dict({k: f"DungeonInfo.{area}.{v}" for k, v in KEY_ROWS.items()}, **{BANC_ARG: banc(area)})


def key_args():
    """The shared key entry's rows and map as its own arguments ({"arg": name})."""
    return {k: {"arg": k} for k in list(KEY_ROWS) + [BANC_ARG]}


def key_steps(rows, n, show=False):
    """The save-data steps that add `n` small keys, in the game's order: the first-key flag, the total, the count. With
    show=True (a whole credit, not part of one) the counter request follows when the player is in that dungeon
    (SHOW_CALL). `rows` is key_rows(area) or key_args()."""
    steps = [{"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
              "params": {"Index": -1, "GameDataName": rows["OnceName"], "Value": True}},
             {"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt",
              "params": {"Index": -1, "GameDataName": rows["TotalName"], "Value": n}},
             {"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt",
              "params": {"Index": -1, "GameDataName": rows["GameDataName"], "Value": n}}]
    if show:
        steps.append({"call": SHOW_CALL, "params": {BANC_ARG: rows[BANC_ARG]}})
    return steps


def show_event():
    """The plan event that adds SHOW_ENTRY to GetPouchContent. When Sequence_CurrentBanc is the BancName argument (case
    0 = equal, the way ReplaceEquipmentForEraChange Event14 reads it) it runs the game's counter steps, otherwise
    nothing."""
    nodes = {
        "here": {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                 "params": {"Index": -1, "GameDataName": CURRENT, "Value": {"arg": BANC_ARG}},
                 "cases": {0: "countup", 1: None}},
        "countup": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                    "params": {"Index": -1, "GameDataName": COUNT_UP, "Value": True}, "next": "frame"},
        "frame": {"actor": "GameSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 1},
                  "next": "display"},
        "display": {"actor": "UISystemActor", "action": "EventTriggerSetDisplaySmallKey",
                    "params": {"IsDisplaySmallKey": True}, "next": "wait"},
        "wait": {"actor": "GameSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 50},
                 "next": None},
    }
    return {"file": SHOW_FILE, "flowchart": SHOW_FILE, "add_graph": SHOW_ENTRY, "nodes": nodes, "start": "here"}


def boss_show_step(map_value):
    """The step after a boss key's IsGetBossKey, the game's boss-key display when the player is in that dungeon.
    `map_value` is banc(area), or {"arg": BANC_ARG} in the shared boss-key entry."""
    return {"call": BOSS_SHOW_CALL, "params": {BANC_ARG: map_value}}


def boss_show_event():
    """The plan event that adds BOSS_SHOW_ENTRY to GetPouchContent. On the boss key's map it does what the game's
    boss-key get does after its add (Dm_SY_Treasurebox Event27 EventGetDungeonBossKey -> Event82
    EventTriggerSetDisplayBossKey -> Event94 50 frames), otherwise nothing."""
    nodes = {
        "here": {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                 "params": {"Index": -1, "GameDataName": CURRENT, "Value": {"arg": BANC_ARG}},
                 "cases": {0: "display", 1: None}},
        "display": {"actor": "UISystemActor", "action": "EventTriggerSetDisplayBossKey",
                    "params": {"IsDisplayBossKey": True}, "next": "wait"},
        "wait": {"actor": "GameSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 50},
                 "next": None},
    }
    return {"file": SHOW_FILE, "flowchart": SHOW_FILE, "add_graph": BOSS_SHOW_ENTRY, "nodes": nodes, "start": "here"}


def key_defaults(area, n):
    """New-file save data holding `n` keys (shuffle_smallkeys 'remove')."""
    rows = key_rows(area)
    return {rows["OnceName"]: True, rows["TotalName"]: n, rows["GameDataName"]: n}


NOTE = {"rows": KEY_ROWS, "show": SHOW_CALL, "boss_show": BOSS_SHOW_CALL}


def verify(patch, note, romfs):
    """Reads every small-key credit of the built patch back.
    - Each step adding to a DungeonInfo.<area>.SmallKeyNum (a name, or the shared entry's GameDataName argument)
      comes right after the same add to that area's SmallKeyTotalNum, which comes right after IsGetSmallKeyOnce set
      True. It's followed by the counter request with that area's map, or by a call to a shared key entry, which ends
      with it (a few keys added silently before the last one's credit).
    - Each call to the shared entry (Rando_DI_Key, its big-chest variant) passes the three rows and the map of one
      area.
    - The counter request entry checks the map and runs the game's counter steps.
    - Every map named exists.
    - A new-file key count (GameDataList default) comes with the same total and the flag set."""
    import sys
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from romtools import Romfs, byml_load, murmur3_32
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    rows = note.get("rows") or KEY_ROWS
    num, once, total = rows["GameDataName"], rows["OnceName"], rows["TotalName"]
    show_file, _, show_entry = (note.get("show") or SHOW_CALL).partition(":")
    boss_file, _, boss_entry = (note.get("boss_show") or BOSS_SHOW_CALL).partition(":")
    row_re = re.compile(r"DungeonInfo\.(\w+)\.(\w+)$")
    bad, credits, calls, shows = [], 0, 0, 0
    boss_credits, boss_calls = 0, 0
    maps = set()

    def items(e):
        return (e.get("params") or {}).get("items") or {}

    def val(e, k):
        return (items(e).get(k) or {}).get("value")

    def is_arg(e, k, name):
        it = items(e).get(k) or {}
        return it.get("type") == "argument" and it.get("value") == name

    def target(e, want_row):
        """(area,) for a named row, ("arg",) for the shared key entry's matching argument, else None."""
        it = items(e).get("GameDataName") or {}
        v = it.get("value")
        if it.get("type") == "argument":  # the shared key entry's own steps (named after it) write its arguments
            if not e["name"].startswith("Rando_DI_Key"):
                return None
            return ("arg",) if v == {num: "GameDataName", once: "OnceName", total: "TotalName"}[want_row] else None
        m = row_re.match(v or "")
        return (m.group(1),) if m and m.group(2) == want_row else None

    def action(fc, e):
        return fc["actors"][e["actor"]]["actions"][e["action"]] if e["type"] == "action" else None

    def shows_after(fn, fc, e, t):
        """("show" | "chain", None) or (None, problem). Credit step `e` (target t) has to be followed by the counter
        request for its own map, or by a call to a shared key entry's credit ("chain", a few keys added silently)."""
        nxt = e.get("next")
        f = fc["events"][nxt] if nxt not in (None, 0xFFFF) else None
        if f is None or f["type"] != "subflow":
            return None, f"{fn}: {e['name']} (keys of {t}) isn't followed by {show_file}:{show_entry}"
        fcn, ep = f.get("flowchart") or "", f.get("entry_point") or ""
        if re.fullmatch(r"Rando_DI_(Key(_Big)?|Call_SmallKey\w*)", ep):
            return "chain", None
        if (fcn, ep) != (show_file, show_entry):
            return None, f"{fn}: {e['name']} (keys of {t}) is followed by {fcn}:{ep}, not {show_file}:{show_entry}"
        want_ok = is_arg(f, BANC_ARG, BANC_ARG) if t == ("arg",) else val(f, BANC_ARG) == banc(t[0])
        if not want_ok:
            return None, f"{fn}: {f['name']} asks for the counter of map {val(f, BANC_ARG)!r}, not {t}'s"
        if t != ("arg",):
            maps.add(val(f, BANC_ARG))
        return "show", None

    folder = os.path.join(patch, "Event", "EventFlow")
    for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if ".bfevfl" not in fn:
            continue
        raw = fs.read(f"Event/EventFlow/{fn}")
        if num.encode() not in raw and b"Rando_DI_" not in raw and BOSS_ROW.encode() not in raw:
            continue
        for fc in Evfl(raw).flowcharts:
            ev = fc["events"]
            prev = {}
            for i, e in enumerate(ev):
                if e["type"] == "action" and e.get("next") not in (None, 0xFFFF):
                    prev.setdefault(e["next"], []).append(i)
            for i, e in enumerate(ev):
                ep = (e.get("entry_point") or "") if e["type"] == "subflow" else ""
                if re.fullmatch(r"Rando_DI_Flag(_Big)?", ep) and (val(e, "GameDataName") or "").endswith(
                        "." + BOSS_ROW):  # boss keys have their own entry (the display request)
                    bad.append(f"{fn}: {e['name']} gives {val(e, 'GameDataName')} through {ep}, without the "
                               f"boss-key display request")
                    continue
                if re.fullmatch(re.escape(BOSS_ENTRY) + r"(_Big)?", ep):
                    boss_calls += 1
                    m = row_re.match(val(e, "GameDataName") or "")
                    if not m or m.group(2) != BOSS_ROW or val(e, BANC_ARG) != banc(m.group(1)):
                        bad.append(f"{fn}: {e['name']} calls {ep} with {val(e, 'GameDataName')!r}, map "
                                   f"{val(e, BANC_ARG)!r}: not one dungeon's boss key and map")
                    else:
                        maps.add(val(e, BANC_ARG))
                    continue
                if action(fc, e) == "EventTriggerSetGameDataBool" and val(e, "Value") is True:
                    gi = items(e).get("GameDataName") or {}
                    m = row_re.match(gi.get("value") or "") if gi.get("type") != "argument" else None
                    shared = gi.get("type") == "argument" and gi.get("value") == "GameDataName" and \
                        e["name"].startswith(BOSS_ENTRY)
                    if shared or (m and m.group(2) == BOSS_ROW):
                        boss_credits += 1
                        nxt = e.get("next")
                        f = ev[nxt] if nxt not in (None, 0xFFFF) else None
                        want_map = (lambda x: is_arg(x, BANC_ARG, BANC_ARG)) if shared else \
                            (lambda x: val(x, BANC_ARG) == banc(m.group(1)))
                        if f is None or f["type"] != "subflow" or \
                                ((f.get("flowchart") or ""), f.get("entry_point")) != (boss_file, boss_entry) or \
                                not want_map(f):
                            bad.append(f"{fn}: {e['name']} sets {gi.get('value')} without the boss-key display "
                                       f"request for its map right after it")
                        elif not shared:
                            maps.add(val(f, BANC_ARG))
                        continue
                if e["type"] == "subflow" and re.fullmatch(r"Rando_DI_Key(_Big)?", e.get("entry_point") or ""):
                    calls += 1
                    got = {k: val(e, k) for k in KEY_ROWS}
                    areas = {k: row_re.match(v or "") for k, v in got.items()}
                    if not all(areas.values()) or len({m.group(1) for m in areas.values()}) != 1 or \
                            any(areas[k].group(2) != KEY_ROWS[k] for k in KEY_ROWS):
                        bad.append(f"{fn}: {e['name']} calls {e['entry_point']} with {got}, not one area's key rows")
                    elif val(e, BANC_ARG) != banc(areas["GameDataName"].group(1)):
                        bad.append(f"{fn}: {e['name']} calls {e['entry_point']} for {areas['GameDataName'].group(1)}"
                                   f" with map {val(e, BANC_ARG)!r}")
                    else:
                        maps.add(val(e, BANC_ARG))
                    continue
                if action(fc, e) != "EventTriggerAddOrSubGameDataInt":
                    continue
                t = target(e, num)
                if t is None:
                    continue
                credits += 1
                n = items(e).get("Value", {}).get("value")
                ok = False
                for j in prev.get(i, []):
                    ej = ev[j]
                    if action(fc, ej) != "EventTriggerAddOrSubGameDataInt" or target(ej, total) != t or \
                            items(ej).get("Value", {}).get("value") != n:
                        continue
                    for k in prev.get(j, []):
                        ek = ev[k]
                        if action(fc, ek) == "EventTriggerSetGameDataBool" and target(ek, once) == t and \
                                items(ek).get("Value", {}).get("value") is True:
                            ok = True
                if not ok or not isinstance(n, int) or n <= 0:
                    bad.append(f"{fn}: {e['name']} adds {n} to {t} without the first-key flag and the total "
                               f"right before it")
                kind, problem = shows_after(fn, fc, e, t)
                if problem:
                    bad.append(problem)
                shows += kind == "show"
    def entry_problems(file, entry, want):
        """Request entry `entry` has to compare CURRENT with its BancName argument, then (case 0) do exactly `want`."""
        fc = next((f for f in Evfl(fs.read(f"Event/EventFlow/{file}.bfevfl.zs")).flowcharts if f["name"] == file),
                  None)
        ent = (fc or {}).get("entry_points", {}).get(entry)
        if ent is None:
            return [f"{file}: no entry {entry}"]
        ev = fc["events"]
        i = ent.get("main", ent.get("event", ent.get("start"))) if isinstance(ent, dict) else ent
        q = ev[i]
        qa = fc["actors"][q["actor"]]["queries"][q["query"]] if q["type"] == "switch" else None
        from evfl_build import is_case_end  # a case's end goes through a do-nothing step (route_end_cases)
        cases = {c["value"]: (0xFFFF if c["next"] < len(ev) and is_case_end(ev[c["next"]]) else c["next"])
                 for c in q.get("cases", [])}
        if qa != "EventQueryIsGameDataString64" or val(q, "GameDataName") != CURRENT or \
                not is_arg(q, "Value", BANC_ARG) or cases.get(1, 0xFFFF) != 0xFFFF or 0 not in cases:
            return [f"{file}:{entry} doesn't start by comparing {CURRENT} with its {BANC_ARG}"]
        got, j = [], cases[0]
        while j not in (None, 0xFFFF) and len(got) < 8:
            got.append(ev[j])
            j = ev[j].get("next")
        if len(got) != len(want) or any(action(fc, e) != a or val(e, k) != v for e, (a, k, v) in zip(got, want)):
            return [f"{file}:{entry} runs {[(action(fc, e), e['name']) for e in got]} on the key's map, not {want}"]
        return []

    if credits or calls:  # the counter request: MiniGame_SequentialChoiceTreasure_GetKey's tail (Event105/104/64/102)
        bad += entry_problems(show_file, show_entry, [
            ("EventTriggerSetGameDataBool", "GameDataName", COUNT_UP), ("EventWait", "Frames", 1),
            ("EventTriggerSetDisplaySmallKey", "IsDisplaySmallKey", True), ("EventWait", "Frames", 50)])
    if boss_credits or boss_calls:  # the boss-key display: Dm_SY_Treasurebox Event82, Event94
        bad += entry_problems(boss_file, boss_entry, [("EventTriggerSetDisplayBossKey", "IsDisplayBossKey", True),
                                                      ("EventWait", "Frames", 50)])
    import glob
    have = {os.path.basename(p)[:-len("_Static.bcett.byml.zs")]
            for p in glob.glob(os.path.join(romfs, "Banc", "*", "*_Static.bcett.byml.zs"))}
    for m in sorted(maps - have):
        bad.append(f"map {m!r} (a key credit's dungeon) is no Banc of the game")
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]["Data"]
    vals = {}
    for table in ("Int", "Bool"):
        for r in gd.get(table, []):
            vals[r["Hash"]] = r.get("DefaultValue")
    if murmur3_32(COUNT_UP) not in vals:
        bad.append(f"GameDataList: {COUNT_UP} is missing")
    import json
    defaults = 0
    for d in json.load(open(os.path.join(HERE, "data", "rando", "dungeons_world.json"), encoding="utf-8"))[
            "dungeons"].values():
        r = key_rows(d["area"])
        have_n = vals.get(murmur3_32(r["GameDataName"]))
        if have_n is None:
            bad.append(f"GameDataList: {r['GameDataName']} is missing")
            continue
        if have_n:
            defaults += 1
            if vals.get(murmur3_32(r["TotalName"])) != have_n or vals.get(murmur3_32(r["OnceName"])) is not True:
                bad.append(f"GameDataList: {r['GameDataName']} starts at {have_n} but {r['TotalName']} at "
                           f"{vals.get(murmur3_32(r['TotalName']))} and {r['OnceName']} "
                           f"{vals.get(murmur3_32(r['OnceName']))}")
    if not bad:
        print(f"small keys: {credits} credits ({shows} with the counter request, {credits - shows} before a shared "
              f"entry's), {calls} calls to the shared key entry, {defaults} new-file key counts read back (first-key "
              f"flag and total with each); boss keys: {boss_credits} credits and {boss_calls} calls with the display "
              f"request; maps {sorted(maps)}")
    return bad
