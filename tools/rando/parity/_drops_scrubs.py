"""The Deku Tree scrubs' heart-or-rupee scene, for the drops plugin. parity/drops.py world_plan calls plan() and
tools/rando/in_game_check.py calls verify().

In vanilla (Get_StoneOfForest, InsideTheDekuTree_Static) there are three Deku scrubs, each with a heart and a green
rupee placed at its hole. Their Presence is the scrub's drop flag, so both appear once it's beaten. The talk entries
(Talk_Deku_0N and Talk_Deku_0N_Attacked) reach one `call :Disappear {Enemy_Scrub_Deku, Obj_Heart, Obj_Rupee_Green}`
(instances ScrubDekuHeart_0N / ScrubDekuRupee_0N). Disappear runs the scrub away and at the same time warps the
heart to it and deletes the rupee if a heart fits the pouch, or the other way round if not. Then it waits and turns
the player. The step after the call goes on to the room's clear flag, the scrub's death and the autosave.

All six pickups are drop-map locations (shuffle_freestanding_items: Deku Tree Slingshot Room / Basement / Before Boss
Recovery Heart and Green Rupee). When a scrub's heart or rupee is a seed location, or the plan renames, retypes or
deletes either one (the get-scene spots get a RandoGetScene name and often another type), the vanilla call would
bind an argument actor that doesn't exist anymore and would delete one location's item. We don't know what the
engine does then (skip it, hang, or end the scene before the clear flag). So that scrub's call is bypassed. The step
leading to it goes to a new graph that runs the caller's scrub away (Disappear's run-away step on the actor the call
passes), waits and turns the player (copies of Disappear's last two steps), then goes on where the call returned.
Both pickups stay at the hole and nothing in the scene names them. With no_collectible_hearts, a bypassed scrub's
heart that isn't a seed location and that the plan leaves alone gets deleted first, since it would be a dropped
heart.
A scrub whose pickups are both left alone keeps the vanilla call (and no_collectible_hearts' edit of its switch).
The flowchart's actor table still lists all six pickups. Vanilla's does too while two of the three scrubs' pickups
don't exist yet, so actors that no reachable step uses are harmless.
"""
import os
import re
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for _p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FILE = "Get_StoneOfForest"
ENTRY = "Disappear"
STAGE = "Banc/InsideTheDekuTree/"
SCRUB_ARG, ROLES = "Enemy_Scrub_Deku", {"heart": "Obj_Heart", "rupee": "Obj_Rupee_Green"}
GRAPH = "Rando_ScrubKeep_"  # + the call's step name
FLAG_ACTION = ("GameDataActor", "EventTriggerSetGameDataBool")


def _romfs():
    import drops  # tools/rando/drops.py
    return drops.DEFAULT_ROMFS


def _fs(romfs, overlays=()):
    from romtools import Romfs
    return Romfs(romfs, os.path.join(HERE, "original"), list(overlays))


def _event_files(romfs):
    d = os.path.join(romfs, "Event", "EventFlow")
    rx = re.compile(re.escape(FILE) + r"(\.\d{3})?\.bfevfl\.zs$")
    return sorted(f"Event/EventFlow/{f}" for f in os.listdir(d) if rx.match(f))


def _flowchart(fs, romfs):
    from evfl import Evfl
    files = _event_files(romfs)
    if len(files) != 1:
        raise ValueError(f"{FILE}: expected one event file, found {files}")
    return files[0], next(f for f in Evfl(fs.read(files[0])).flowcharts if f["name"] == FILE)


def _items(e):
    return ((e.get("params") or {}).get("items") or {})


def _plain(e):
    """An event's simple parameters ({name: bool/int/float/str})."""
    return {k: v["value"] for k, v in _items(e).items() if v.get("type") in ("bool", "int", "float", "string")}


def _succ(e):
    out = []
    if e["type"] in ("action", "join", "subflow") and e.get("next") not in (None, 0xFFFF):
        out.append(e["next"])
    out += [c["next"] for c in e.get("cases", []) if c["next"] != 0xFFFF]
    if e["type"] == "fork":
        out += list(e["forks"]) + [e["join"]]
    return out


def reachable(fc, entries=None):
    """Event indices reachable from the flowchart's entry points (all, or those named)."""
    seen, todo = set(), [ep["main"] for n, ep in fc["entry_points"].items() if entries is None or n in entries]
    while todo:
        i = todo.pop()
        if i in seen or i == 0xFFFF:
            continue
        seen.add(i)
        todo += _succ(fc["events"][i])
    return seen


def _names(fs, romfs):
    """{(Gyaml, Name): (file, hash)} for the named pickups of the scrubs' stage."""
    from romtools import byml_load
    out = {}
    root = os.path.join(romfs, "Banc", "InsideTheDekuTree")
    for fn in sorted(os.listdir(root)):
        if fn.endswith(".bcett.byml.zs"):
            rel = f"{STAGE}{fn}"
            for a in byml_load(fs.read(rel))[0].get("Actors") or []:
                if a.get("Name") and a.get("Gyaml") in ROLES.values():
                    out[(a["Gyaml"], a["Name"])] = (rel, str(a["Hash"]))
    return out


@lru_cache(maxsize=2)
def survey(romfs=None):
    """The vanilla scene: {"file", "calls": [{"event", "next", "preds", "scrub": [actor, sub], "pickups": {role:
    [file, hash, instance]}, "flags": [...]}], "run": {"action", "params"}, "tail": [step names]}."""
    import progressive
    romfs = romfs or _romfs()
    fs = _fs(romfs)
    rel, fc = _flowchart(fs, romfs)
    ev = fc["events"]
    main = ev[fc["entry_points"][ENTRY]["main"]]
    if main["type"] != "fork":
        raise ValueError(f"{FILE}:{ENTRY} no longer starts with its fork")
    run = next((ev[i] for i in main["forks"] if ev[i]["type"] == "action"
                and fc["actors"][ev[i]["actor"]]["argument"] == SCRUB_ARG), None)
    if run is None:
        raise ValueError(f"{FILE}:{ENTRY}: no run-away step on its scrub argument")
    tail, i = [], ev[main["join"]]["next"]
    while i not in (None, 0xFFFF):
        if ev[i]["type"] != "action":
            raise ValueError(f"{FILE}:{ENTRY}: its tail is no plain chain of steps")
        tail.append(ev[i]["name"])
        i = ev[i]["next"]
    names = _names(fs, romfs)
    calls = []
    for e in ev:
        if e["type"] != "subflow" or e.get("entry_point") != ENTRY or (e.get("flowchart") or FILE) != FILE:
            continue
        it = _items(e)
        pickups = {}
        for role, actor in ROLES.items():
            name, inst = it[actor]["value"]
            if (name, inst) not in names:
                raise ValueError(f"{FILE} {e['name']}: no {name} named {inst} in {STAGE}")
            pickups[role] = list(names[(name, inst)]) + [inst]
        calls.append({"event": e["name"], "next": None if e["next"] in (None, 0xFFFF) else ev[e["next"]]["name"],
                      "preds": progressive.predecessors(fc, e), "scrub": list(it[SCRUB_ARG]["value"]),
                      "pickups": pickups})
    if len(calls) != 3:
        raise ValueError(f"{FILE}: {len(calls)} calls of {ENTRY}, expected the three scrubs'")
    return {"file": rel, "calls": calls, "tail": tail,
            "run": {"action": fc["actors"][run["actor"]]["actions"][run["action"]], "params": _plain(run)}}


def plan(kept, placements, hero=False, romfs=None):
    """{"events": [...], "_drops_scrubs": spec, "_notes_drops_scrubs": [...]} for the scrubs whose pickups the seed
    uses ({} when every scrub keeps its vanilla scene). `kept` is {location: (drop-map entry, item)}, `placements` the
    drops plugin's placement ops and `hero` means no_collectible_hearts."""
    s = survey(romfs)
    spots = {(p["file"], str(p["hash"])) for e, _ in kept.values() for p in (e or {}).get("placements", [])}
    touched = {(op["file"], str(op["hash"])) for op in placements if op.get("twin") is None
               and (op.get("delete") or {"Name", "Gyaml"} & set(op.get("set") or {}))}
    events, done, notes = [], [], []
    for c in s["calls"]:
        keys = {role: (p[0], p[1]) for role, p in c["pickups"].items()}
        why = sorted(f"{role} {'is a seed location' if k in spots else 'is renamed or retyped'}"
                     for role, k in keys.items() if k in spots or k in touched)
        if not why:
            continue
        graph, order, nodes = GRAPH + c["event"], [], {}
        heart = c["pickups"]["heart"]
        deleted = None
        if hero and keys["heart"] not in spots and keys["heart"] not in touched:
            nodes["del"] = {"actor": ROLES["heart"], "sub_name": heart[2], "action": "EventTriggerDeleteSelf"}
            order.append("del")
            deleted = list(keys["heart"])
        nodes["run"] = {"actor": c["scrub"][0], "sub_name": c["scrub"][1], "action": s["run"]["action"],
                        "params": dict(s["run"]["params"])}
        order.append("run")
        for k, name in enumerate(s["tail"]):
            nodes[f"t{k}"] = {"copy": name}
            order.append(f"t{k}")
        for a, b in zip(order, order[1:]):
            nodes[a]["next"] = b
        nodes[order[-1]]["next"] = f"@{c['next']}" if c["next"] else None
        events.append({"file": FILE, "flowchart": FILE, "add_graph": graph, "nodes": nodes, "start": order[0]})
        start = f"{graph}_{order[0]}"
        for kind, where, k in c["preds"]:
            op = {"file": FILE, "flowchart": FILE, "next": start}
            if kind == "entry":
                op["entry"] = where
            else:
                op["event"] = where
                if kind in ("case", "fork"):
                    op[kind] = k
            events.append(op)
        done.append({"call": c["event"], "start": start, "graph": [f"{graph}_{o}" for o in order],
                     "pickups": {r: list(k) for r, k in keys.items()}, "deleted": deleted})
        notes.append(f"{FILE} {c['event']} ({c['scrub'][0]}{' ' + c['scrub'][1] if c['scrub'][1] else ''}): its "
                     f"heart-or-rupee scene bypassed ({', '.join(why)}); both pickups stay at the hole"
                     + ("; its vanilla heart deleted (no_collectible_hearts)" if deleted else ""))
    if not done:
        return {}
    return {"events": events, "_drops_scrubs": {"bypassed": done, "spots": sorted(list(k) for k in spots | touched
                                                                                  if k[0].startswith(STAGE))},
            "_notes_drops_scrubs": notes}


def verify(patch_dir, spec, romfs=None, located=None):
    """Reads the built scene back and returns [problem].
    - Every reachable step and call of Get_StoneOfForest that names a scrub pickup names one the patched level still
      has (type and name) and that isn't a seed location. Seed locations come from the plan's spec and, with `located`
      (the spoiler's location names), the drop-map placements of those in the scrubs' stage.
    - Each bypassed call is unreachable and its graph is reached in its place.
    - The game-data flags the scene sets are the vanilla ones.
    It runs for every built patch, so a plan that renames the pickups without a bypass fails here."""
    romfs = romfs or _romfs()
    van, new = _fs(romfs), _fs(romfs, [patch_dir])
    _, fc0 = _flowchart(van, romfs)
    rel, fc = _flowchart(new, romfs)
    names = _names(new, romfs)
    spots = {tuple(k) for k in spec.get("spots", [])} | {tuple(v) for b in spec.get("bypassed", [])
                                                          for v in b["pickups"].values()}
    if located:
        import drops as D  # tools/rando/drops.py
        m = D._map()
        spots |= {(p["file"], str(p["hash"])) for sec in ("drops", "new") for n, e in (m.get(sec) or {}).items()
                  if n in located for p in e.get("placements", []) if p["file"].startswith(STAGE)}
    spots -= {tuple(b["deleted"]) for b in spec.get("bypassed", []) if b.get("deleted")}
    bad = []
    seen = reachable(fc)
    by_name = {e["name"]: e for e in fc["events"]}

    def check(actor, inst, where):
        if actor not in ROLES.values() or not inst:
            return
        k = names.get((actor, inst))
        if k is None:
            bad.append(f"{rel} {where}: names {actor} {inst}, which the patched level no longer has")
        elif k in spots:
            bad.append(f"{rel} {where}: names {actor} {inst}, a seed location ({k[1]})")
    for i in sorted(seen):
        e = fc["events"][i]
        if e["type"] in ("action", "switch"):
            a = fc["actors"][e["actor"]]
            if not a["argument"]:
                check(a["name"], a["sub_name"], e["name"])
        if e["type"] == "subflow":
            for v in _items(e).values():
                if v.get("type") == "actor":
                    check(v["value"][0], v["value"][1], e["name"])
    for b in spec.get("bypassed", []):
        c = by_name.get(b["call"])
        if c is not None and c["idx"] in seen:
            bad.append(f"{rel}: {b['call']} is still reached (its scene should be bypassed)")
        for g in b["graph"]:
            if g not in by_name or by_name[g]["idx"] not in seen:
                bad.append(f"{rel}: bypass step {g} missing or not reached")

    def flags(f, idx):
        out = set()
        for i in idx:
            e = f["events"][i]
            a = f["actors"][e["actor"]] if e["type"] == "action" else None
            if a and (a["name"], a["actions"][e["action"]]) == FLAG_ACTION:
                out.add((_plain(e).get("GameDataName"), _plain(e).get("Value")))
        return out
    lost = flags(fc0, reachable(fc0)) - flags(fc, seen)
    if lost:
        bad.append(f"{rel}: the scene no longer sets {sorted(lost)}")
    return bad


if __name__ == "__main__":
    import json
    print(json.dumps(survey(sys.argv[1] if len(sys.argv) > 1 else None), indent=1))
