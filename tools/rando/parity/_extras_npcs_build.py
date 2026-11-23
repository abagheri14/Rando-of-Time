"""Build data/rando/extras_npcs_data.json: the scene steps the extras plugin (extras_npcs.py) hooks, read from the
game files (vanilla view), so the plugin writes patch plans without the romfs.

usage: python tools/rando/parity/_extras_npcs_build.py ROMFS

Every step is found by what it does (its call, action, query and parameters), checked in every version of its file,
and recorded with its routing (next step, every step or entry leading to it). The build stops if the game differs
from what the plugin expects.
- fire_gorons: the 9 Fire Temple gorons (Npc_Goron_<n>_Adult:Talk). After the "you freed me" talk the flow fades
  out, plays the goron's run-away scene and sets Npc_Goron_<n>_Delete (saved). The fade step is the hook.
- beggar: Npc_Hylia_046_BottleShop_Child (Market child, Kakariko adult). The first step after each bottle choice
  (fish, bug, blue fire), before Link shows the bottle.
- hat: MiniGame_Fishing_Sub:Talk_TakeOffHat, the owner's "keep this a secret" talk after the hat is given back.
- pole: MiniGame_Fishing:PaymentCheck, its first step (every rental passes it) and the "not enough rupees" talk.
- big_poes: Dm_SY_InsertBottle, the two calls of :Market_Item_Bottle_TutorialEvent_ClearFlow that end the bottle
  catch (short path, then the poe checks; long path, the first catch ever).
- signs: for every sign spot with a scene row of its own (data/rando/extras_npcs.json "signs"), the row's flow
  entry and its first step.
- fish: MiniGame_Fishing's two catch entries (Step01_CatchFish_Child / _Adult, each a call of :CatchFish_Sub and
  then the end, and the only callers), Dm_SY_InsertBottle's step where the caught actor is still the guest
  performer (its EventTriggerAttentionOffClientAll), and the child Zora's Domain layout's five Animal_Fish_Blue (by
  position).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romtools import Romfs, byml_load  # noqa: E402
import progressive  # noqa: E402
from _songs_trade_build import BuildError, load_all, params, step_info  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "extras_npcs_data.json")
SPEC = os.path.join(HERE, "data", "rando", "extras_npcs.json")
GORONS = ("001", "002", "003", "004", "005", "007", "008", "009", "010")
BOTTLES = {"fish": 4, "bugs": 8, "blue_fire": 3}  # BottleItem values the beggar's choices show


def _what(fc, e):
    if e["type"] in ("subflow", "subflow_switch"):
        return f"{e.get('flowchart') or ''}:{e['entry_point']}"
    if e["type"] == "action":
        a = fc["actors"][e["actor"]]
        return f"{a['name']}.{a['actions'][e['action']]}"
    if e["type"] == "switch":
        a = fc["actors"][e["actor"]]
        return f"{a['name']}.{a['queries'][e['query']]}"
    return e["type"]


def _reach(fc, entry):
    """Steps reachable from an entry point, in walk order."""
    ev = fc["events"]
    start = fc["entry_points"][entry]["main"]
    seen, order, stack = set(), [], [start]
    while stack:
        i = stack.pop()
        if i is None or i == 0xFFFF or i in seen or i >= len(ev):
            continue
        seen.add(i)
        order.append(ev[i])
        e = ev[i]
        nxt = [e.get("next")] + [c["next"] for c in e.get("cases", [])] + list(e.get("forks", [])) + [e.get("join")]
        stack.extend(reversed([n for n in nxt if n is not None]))
    return order


def _nx(fc, e, key="next"):
    """The step `key` points to, or None for the end."""
    j = e.get(key)
    return fc["events"][j] if j is not None and j != 0xFFFF and j < len(fc["events"]) else None


def _by_name(fc, name):
    return next(e for e in fc["events"] if e["name"] == name)


def _same(per_version, what):
    first = per_version[0][1]
    for rel, d in per_version[1:]:
        if d != first:
            raise BuildError(f"{rel}: {what} differs from {per_version[0][0]}")
    return first


def goron_data(fs, romfs):
    out = {}
    for n in GORONS:
        name = f"Npc_Goron_{n}_Adult"
        per = []
        for rel, fc in load_all(fs, romfs, name):
            steps = _reach(fc, "Talk")
            shutter = [e for e in steps if _what(fc, e) == "GameDataActor.EventQueryIsGameDataBool"
                       and params(e).get("GameDataName") == f"Npc_Goron_{n}_ShutterisOpen"]
            trans = [e for e in steps if _what(fc, e) == "EventSystemActor.EventTransition"
                     and str(params(e).get("EventName", "")).startswith("Dm_FireTemple_")]
            if len(shutter) != 1 or len(trans) != 1:
                raise BuildError(f"{rel}: {len(shutter)} cell checks, {len(trans)} run-away scenes (expected 1 and 1)")
            t = trans[0]
            delete = _nx(fc, t)
            if delete is None or _what(fc, delete) != "GameDataActor.EventTriggerSetGameDataBool" or \
                    params(delete).get("GameDataName") != f"Npc_Goron_{n}_Delete" or params(delete).get("Value") is not True:
                raise BuildError(f"{rel}: the run-away scene isn't followed by Npc_Goron_{n}_Delete = True")
            # the fade before the unequip step and the scene transition
            fades = [e for e in steps if _what(fc, e) == "UISystemActor.EventEventFadeOut"]
            fade = None
            for f in fades:
                j, hops = _nx(fc, f), 0
                while j is not None and hops < 3:
                    if j["name"] == t["name"]:
                        fade = f
                        break
                    j, hops = _nx(fc, j), hops + 1
            if fade is None:
                raise BuildError(f"{rel}: no fade-out before {t['name']}")
            preds = progressive.predecessors(fc, fade)
            talk = _by_name(fc, preds[0][1]) if len(preds) == 1 and preds[0][0] == "next" else None
            if talk is None or _what(fc, talk) != "Npc_EventStarter.EventTalk":
                raise BuildError(f"{rel}: the fade-out {fade['name']} doesn't follow the freed goron's talk alone")
            # the cell check's yes case (0) leads to the freed talk
            per.append((rel, {"file": name, "flowchart": fc["name"], "fade": step_info(fc, fade),
                              "talk": talk["name"], "message": params(talk).get("MessageId"),
                              "shutter_flag": f"Npc_Goron_{n}_ShutterisOpen", "delete_flag": f"Npc_Goron_{n}_Delete",
                              "scene": params(t).get("EventName")}))
        out[n] = _same(per, f"goron {n} steps")
    return out


def beggar_data(fs, romfs):
    name = "Npc_Hylia_046_BottleShop_Child"
    per = []
    for rel, fc in load_all(fs, romfs, name):
        found = {}
        for e in fc["events"]:
            if _what(fc, e) != "GameDataActor.EventTriggerSetGameDataBool" or \
                    params(e).get("GameDataName") != "Shop_IsUpdatableStockNumDisplay" or params(e).get("Value") is not False:
                continue
            n = _nx(fc, e)
            if n is None or _what(fc, n) != "ShowItem:ShowItemSuccess_NoCamera_BottleItem":
                continue
            b = params(n).get("BottleItem")
            kind = next((k for k, v in BOTTLES.items() if v == b), None)
            if kind is None:
                raise BuildError(f"{rel}: a bottle choice shows BottleItem {b}")
            rec = step_info(fc, e)
            if not rec["preds"] or any(p[0] != "case" for p in rec["preds"]):
                raise BuildError(f"{rel}:{e['name']}: reached other than by a talk choice ({rec['preds']})")
            found[kind] = rec
        if sorted(found) != sorted(BOTTLES):
            raise BuildError(f"{rel}: bottle choices found {sorted(found)}")
        age = any("EventQueryPlayerIsChild" in a["queries"] for a in fc["actors"] if a["name"] == "Player_Event")
        per.append((rel, {"file": name, "flowchart": fc["name"], "choices": found, "player_has_age_query": age}))
    return _same(per, "beggar steps")


def hat_data(fs, romfs):
    name = "MiniGame_Fishing_Sub"
    per = []
    for rel, fc in load_all(fs, romfs, name):
        steps = _reach(fc, "Talk_TakeOffHat")
        talk = [e for e in steps if _what(fc, e) == "Npc_EventStarter.EventTalk"
                and params(e).get("MessageId") == "EventFlowMsg/MiniGame_Fishing:Talk_79"]
        if len(talk) != 1:
            raise BuildError(f"{rel}: {len(talk)} 'keep it a secret' talks after the hat's return")
        rec = step_info(fc, talk[0])
        # it follows the return only: the join after "thank goodness" / "that was easier" and the hat put back on
        if [p[0] for p in rec["preds"]] != ["next"] or _by_name(fc, rec["preds"][0][1])["type"] != "join":
            raise BuildError(f"{rel}: Talk_79 is reached other than by the return's join ({rec['preds']})")
        per.append((rel, {"file": name, "flowchart": fc["name"], "returned": rec}))
    return _same(per, "hat steps")


def pole_data(fs, romfs):
    name = "MiniGame_Fishing"
    per = []
    for rel, fc in load_all(fs, romfs, name):
        first = fc["events"][fc["entry_points"]["PaymentCheck"]["main"]]
        if _what(fc, first) != "Player_Event.EventQueryPlayerIsChild":
            raise BuildError(f"{rel}: PaymentCheck starts with {_what(fc, first)}")
        # every way to the rod hand-over starts at PaymentCheck
        hand = [e for e in fc["events"] if _what(fc, e) == "NpcCommon:NpcCommon_HandOver_NpcToPlayer_FishingOnly"]
        if len(hand) != 1:
            raise BuildError(f"{rel}: {len(hand)} rod hand-overs")
        seen, stack, entries = set(), [hand[0]["name"]], set()
        while stack:
            s = stack.pop()
            if s in seen:
                continue
            seen.add(s)
            for kind, where, _k in progressive.predecessors(fc, _by_name(fc, s)):
                if kind == "entry":
                    entries.add(where)
                else:
                    stack.append(where)
        if entries != {"PaymentCheck"}:
            raise BuildError(f"{rel}: the rod hand-over is reached from {sorted(entries)}")
        broke = [e for e in _reach(fc, "PaymentCheck") if _what(fc, e) == "Npc_EventStarter.EventTalk"
                 and params(e).get("MessageId") == "EventFlowMsg/MiniGame_Fishing:Talk_07"]
        if len(broke) != 1:
            raise BuildError(f"{rel}: {len(broke)} 'not enough rupees' talks in PaymentCheck")
        per.append((rel, {"file": name, "flowchart": fc["name"], "payment": step_info(fc, first),
                          "no_rupees": broke[0]["name"], "message": "EventFlowMsg/MiniGame_Fishing.msbt:Talk_07"}))
    return _same(per, "fishing payment steps")


def poe_data(fs, romfs):
    name = "Dm_SY_InsertBottle"
    per = []
    for rel, fc in load_all(fs, romfs, name):
        calls = [e for e in fc["events"] if _what(fc, e) == ":Market_Item_Bottle_TutorialEvent_ClearFlow"]
        ends = {}
        for e in calls:
            nxt = _nx(fc, e)
            if nxt is None:
                ends["long"] = step_info(fc, e)
            elif _what(fc, nxt) == "Player_Event.EventQueryGetBottleContent":
                ends["short"] = step_info(fc, e)
        if sorted(ends) != ["long", "short"] or len(calls) != 2:
            raise BuildError(f"{rel}: bottle-catch endings found {sorted(ends)} ({len(calls)} calls)")
        pushes = [e for e in fc["events"] if _what(fc, e) == "PouchSystemActor.EventTriggerPushToEmptyBottle"]
        for e in pushes:
            arg = ((e.get("params") or {}).get("items") or {}).get("BigPoeFenceId") or {}
            if arg.get("type") != "argument" or arg.get("value") != "BigPoeFenceId":
                raise BuildError(f"{rel}:{e['name']}: BigPoeFenceId isn't the scene's argument")
        acts = {a["name"]: a for a in fc["actors"] if not a["sub_name"]}
        per.append((rel, {"file": name, "flowchart": fc["name"], "ends": ends, "pushes": [e["name"] for e in pushes],
                          "gamedata_actor": "GameDataActor" in acts}))
    return _same(per, "bottle-catch steps")


def sign_data(fs, romfs):
    spec = json.load(open(SPEC, encoding="utf-8"))["signs"]
    es = byml_load(fs.read("RSDB/EventSetting.Product.111.rstbl.byml.zs"))[0]
    rows = {r["__RowId"]: r for r in es}
    users = {}
    for r in es:
        key = (r.get("FlowchartFileName"), r.get("EntryPointName"))
        users.setdefault(key, []).append(r["__RowId"])
    out = {}
    for loc, s in spec["locations"].items():
        recs = []
        for row in s["rows"]:
            r = rows.get(row)
            if r is None:
                raise BuildError(f"{loc}: no scene row {row}")
            key = (r.get("FlowchartFileName"), r.get("EntryPointName"))
            if users[key] != [row]:
                raise BuildError(f"{loc}: {row}'s entry {key} is shared with {users[key]}")
            flow = os.path.basename(r["FlowchartFileName"]).replace(".evfc", "")
            entry = r["EntryPointName"]
            per = []
            for rel, fc in load_all(fs, romfs, flow):
                if entry not in fc["entry_points"]:
                    raise BuildError(f"{rel}: no entry {entry}")
                first = fc["events"][fc["entry_points"][entry]["main"]]
                rec = step_info(fc, first)
                acts = sorted({a["name"] for a in fc["actors"] if not a["sub_name"]})
                per.append((rel, {"row": row, "file": flow, "flowchart": fc["name"], "entry": entry, "first": rec,
                                  "gamedata_actor": "GameDataActor" in acts}))
            recs.append(_same(per, f"{loc} entry"))
        # no other flow calls these entries, otherwise an item given there would be given away from the sign
        out[loc] = recs
    calls = {}
    d = os.path.join(romfs, "Event", "EventFlow")
    from evfl import Evfl
    wanted = {(r["file"], r["entry"]) for recs in out.values() for r in recs}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".bfevfl.zs"):
            continue
        fc_name = fn.split(".")[0]
        ev = Evfl(fs.read("Event/EventFlow/" + fn))
        if not ev.flowcharts:  # timeline-only files (_Env, _Effect...) have no steps
            continue
        fc = ev.flowcharts[0]
        for e in fc["events"]:
            if e["type"] in ("subflow", "subflow_switch"):
                tgt = (e.get("flowchart") or fc_name, e["entry_point"])
                if tgt in wanted:
                    calls.setdefault(f"{tgt[0]}:{tgt[1]}", set()).add(f"{fc_name}:{e['name']}")
    for loc, recs in out.items():
        for r in recs:
            c = calls.get(f"{r['file']}:{r['entry']}")
            if c:
                raise BuildError(f"{loc}: {r['file']}:{r['entry']} is also called from {sorted(c)}")
    return out


def fish_data(fs, romfs):
    spec = json.load(open(SPEC, encoding="utf-8"))["fish"]
    per = []
    for rel, fc in load_all(fs, romfs, "MiniGame_Fishing"):
        catch = {}
        for age, entry in (("child", "Step01_CatchFish_Child"), ("adult", "Step01_CatchFish_Adult")):
            e = fc["events"][fc["entry_points"][entry]["main"]]
            if _what(fc, e) != ":CatchFish_Sub" or _nx(fc, e) is not None:
                raise BuildError(f"{rel}: {entry} is {_what(fc, e)} then {e.get('next')}, not a call of CatchFish_Sub "
                                 f"then the end")
            catch[age] = step_info(fc, e)
        callers = sorted(e["name"] for e in fc["events"] if _what(fc, e) == ":CatchFish_Sub")
        if callers != sorted(c["event"] for c in catch.values()):
            raise BuildError(f"{rel}: CatchFish_Sub is called by {callers}")
        per.append((rel, {"file": "MiniGame_Fishing", "flowchart": fc["name"], "catch": catch}))
    pond = _same(per, "fishing catch steps")
    per = []
    for rel, fc in load_all(fs, romfs, "Dm_SY_InsertBottle"):
        off = [e for e in fc["events"] if _what(fc, e) == "PouchContentGuestPerformer.EventTriggerAttentionOffClientAll"]
        if len(off) != 1 or _nx(fc, off[0]) is None:
            raise BuildError(f"{rel}: {len(off)} guest-performer attention steps")
        acts = {a["name"] for a in fc["actors"] if not a["sub_name"]}
        if "GameDataActor" not in acts:
            raise BuildError(f"{rel}: no GameDataActor")
        per.append((rel, {"file": "Dm_SY_InsertBottle", "flowchart": fc["name"], "guest": step_info(fc, off[0])}))
    bottle = _same(per, "bottle-catch guest step")
    zd = spec["zd"]
    acts = [a for a in byml_load(fs.read(zd["file"]))[0]["Actors"] if a.get("Gyaml") == "Animal_Fish_Blue"]
    if len(acts) != len(zd["locations"]) or any(a.get("Name") for a in acts):
        raise BuildError(f"{zd['file']}: {len(acts)} fish (named: {[a.get('Name') for a in acts if a.get('Name')]})")
    acts.sort(key=lambda a: (round(a["Translate"][0], 2), round(a["Translate"][2], 2)))
    fish = [{"location": n, "hash": str(a["Hash"]), "pos": [round(x, 1) for x in a["Translate"]]}
            for n, a in zip(zd["locations"], acts)]
    return {"pond": pond, "bottle": bottle, "zd": fish}


def flag_names(data):
    """Every save flag the plugin reads or sets as a check's 'given' record (extras_npcs.flags)."""
    spec = json.load(open(SPEC, encoding="utf-8"))
    out = {v for k, v in spec["flags_claimed"].items() if not k.startswith("_")}
    out |= {g["delete_flag"] for g in data["fire_gorons"].values()}
    out |= {f"HyruleField_Defeat_BigPoe_{v['fence']:02d}" for v in spec["big_poes"]["locations"].values()}
    out.add(spec["pole"]["flag"])
    for loc, s in spec["signs"]["locations"].items():
        if s.get("flag") != "claimed":
            out.add("HavePlayedEvent." + s.get("flag_row", s["rows"][0]))
    return sorted(out)


def check_flags(fs, names):
    """Each flag must be a saved Bool (ResetTypeValue 8: only a new file resets it) defaulting to false."""
    from romtools import murmur3_32
    root = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    bools = {int(e["Hash"]): e for e in root["Data"]["Bool"]}
    for n in names:
        e = bools.get(murmur3_32(n))
        if e is None:
            raise BuildError(f"save flag {n} is not a Bool in GameDataList")
        if e.get("ResetTypeValue") != 8 or e.get("DefaultValue") is not False or e.get("SaveFileIndex") != 0:
            raise BuildError(f"save flag {n}: {e} (not a saved Bool defaulting to false)")
    return names


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    data = {"_about": __doc__.strip().splitlines()[0] + " Built by tools/rando/parity/_extras_npcs_build.py.",
            "fire_gorons": goron_data(fs, romfs), "beggar": beggar_data(fs, romfs), "hat": hat_data(fs, romfs),
            "pole": pole_data(fs, romfs), "big_poes": poe_data(fs, romfs), "signs": sign_data(fs, romfs),
            "fish": fish_data(fs, romfs)}
    data["flags_checked"] = check_flags(fs, flag_names(data))
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1, sort_keys=False)
    print(f"{len(data['fire_gorons'])} gorons, {len(data['beggar']['choices'])} beggar choices, hat, pole, big poes, "
          f"{len(data['signs'])} signs, pond and {len(data['fish']['zd'])} ZD fish -> {os.path.relpath(OUT, HERE)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except BuildError as e:
        sys.exit(f"build error: {e}")
