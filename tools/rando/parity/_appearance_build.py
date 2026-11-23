"""Build data/rando/appearance_objects.json: which item holders can show a per-placement look, and the evidence.

usage: python tools/rando/parity/_appearance_build.py [ROMFS]

What it reads (vanilla files only, ./original copies win over the live romfs):
- every item-holding object type of data/rando/drop_map.json (pots, crates, rocks, grass, beehives, flying pots...),
  the chests and the chest pedestals. For each: whether the type declares the per-placement colour keys
  GameModelController_GeneralInstanceParam0..3 (a BlackboardParamTable of its actor pack, tools/actor_params.py),
  which model it shows (ActorParam ModelInfoRef, $parent chains followed) and whether that model's materials
  build their albedo from an expression graph (tools/rando/parity/_appearance_bfres.py)
- every level file (Banc/*/*.bcett.byml.zs), for the colours vanilla sets with those keys per type, and the chest
  pedestals (Obj_TBoxPedestal_*) with the chest standing on them
A type gets "tint": "proven" when it declares the keys and its model uses an expression graph that a vanilla
placement already colours with them (so the graph reads the colour). It gets "declared" when it declares the keys
but its materials have no such graph (setting them is harmless, nothing's expected to show), and "none" otherwise.
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romtools import Romfs, byml_load, sarc_files  # noqa: E402
from actor_params import ActorParams  # noqa: E402
import _appearance_bfres as bfres  # noqa: E402

DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS
OUT = os.path.join(HERE, "data", "rando", "appearance_objects.json")
DROP_MAP = os.path.join(HERE, "data", "rando", "drop_map.json")
KEYS = [f"GameModelController_GeneralInstanceParam{i}" for i in range(3)]
CHESTS = ("Obj_TBox_A_01", "Obj_TBox_A_01_NoBake", "Obj_TBox_A_02", "Obj_TBox_A_02_NoBake", "Obj_TBox_A_03",
          "Obj_TBox_A_03_NoBake", "Obj_TBox_A_04", "Obj_TBox_A_06", "Obj_TBox_A_06_NoBake", "Obj_TBox_GlassTruth_A_01")
PEDESTALS = ("Obj_TBoxPedestal_A_01", "Obj_TBoxPedestal_A_02")
# chest types a look option may swap between (same AI; small ones share Obj_TBox_A_01's opening, big ones A_02's)
LOOK_TYPES = ("Obj_TBox_A_01", "Obj_TBox_A_01_NoBake", "Obj_TBox_A_02", "Obj_TBox_A_02_NoBake", "Obj_TBox_A_03",
              "Obj_TBox_A_03_NoBake", "Obj_TBox_GlassTruth_A_01")
# Room for a big chest: horizontal clearance from objects within 1.5 m of the same height. Another chest needs room
# for two big chest half-widths (0.64 + 0.64 m) between their centres.
ROOM_OBJECT, ROOM_CHEST, ROOM_HEIGHT = 1.0, 1.3, 1.5
# a pedestal belongs to the chest standing on it: same level, centres within this distance (vanilla: 0.0-0.41)
PEDESTAL_REACH = 1.0


def level_of(rel):
    """Banc/Area/Area_Child_Static.bcett.byml.zs -> 'Area/Area_Child' (a level loads its Static and Dynamic file)."""
    area, fn = rel.split("/")[1], rel.rsplit("/", 1)[-1].replace(".bcett.byml.zs", "")
    for s in ("_Static", "_Dynamic"):
        if fn.endswith(s):
            fn = fn[:-len(s)]
    return f"{area}/{fn}"


def _byml(blob):
    return byml_load(blob, allow_big=True)[0]


def model_of(fs, actor):
    """(ModelProjectName, FmdbName) the actor's pack names, following $parent chains inside the pack."""
    files = sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))

    def load(work_path):
        rel = work_path.replace("Work/", "", 1).replace(".gyml", ".bgyml").lstrip("?")
        return _byml(files[rel]) if rel in files else None

    comps, node = {}, _byml(files[f"Actor/{actor}.engine__actor__ActorParam.bgyml"])
    while node is not None:
        for k, v in (node.get("Components") or {}).items():
            comps.setdefault(k, v)
        node = load(node["$parent"]) if node.get("$parent") else None
    ref = comps.get("ModelInfoRef")
    if not ref:
        return None
    info, node = {}, load(ref)
    while node is not None:
        for k, v in node.items():
            info.setdefault(k, v)
        node = load(node["$parent"]) if node.get("$parent") else None
    if "FmdbName" not in info:
        return None
    return info["ModelProjectName"], info["FmdbName"], info.get("ModelVariationAnims") or []


def model_materials(fs, romfs, project, fmdb):
    rel = f"Model/{project}.{fmdb}.bfres.zs"
    if not os.path.exists(os.path.join(romfs, rel)):
        return rel, None
    d = fs.read(rel)
    return rel, [{"material": m["material"], "albedo": [t for t in m["textures"] if "_Alb" in t],
                  "graphs": bfres.graph_ids(d, m["fmat"])} for m in bfres.materials(d)]


def scan_levels(fs, romfs):
    """(vanilla tints {actor: Counter}, placements of pedestals and chests, pot types per level, solid objects per
    level [(file, actor)] for the room check)."""
    tints, peds, chests, pots, solid = defaultdict(Counter), [], [], defaultdict(Counter), defaultdict(list)
    banc = os.path.join(romfs, "Banc")
    for area in sorted(os.listdir(banc)):
        p = os.path.join(banc, area)
        if not os.path.isdir(p):
            continue
        for fn in sorted(os.listdir(p)):
            if not fn.endswith(".bcett.byml.zs"):
                continue
            rel = f"Banc/{area}/{fn}"
            for a in (_byml(fs.read(rel)) or {}).get("Actors", []) or []:
                g = a.get("Gyaml", "")
                dyn = a.get("Dynamic") or {}
                if any(k in dyn for k in KEYS):
                    rgb = tuple(round(float(dyn.get(k, 1.0)), 3) for k in KEYS)
                    tints[g][str(rgb)] += 1
                if g in PEDESTALS:
                    peds.append((rel, a))
                elif g.startswith("Obj_TBox_") or g.startswith("Obj_HrlCity_Shop_TBox"):
                    chests.append((rel, a))
                if g.startswith("Obj_Pot_") or g.startswith("Enemy_FlyingPot"):
                    pots[level_of(rel)][g] += 1
                if g.startswith(("Obj_", "Npc_")) and g not in PEDESTALS and a.get("Translate"):
                    solid[level_of(rel)].append((rel, a))
    return tints, peds, chests, pots, solid


def pair_pedestals(peds, chests):
    out = []
    for rel, p in peds:
        pt, best = p["Translate"], None
        for crel, c in chests:
            if level_of(crel) != level_of(rel):
                continue
            ct = c["Translate"]
            dh = math.hypot(ct[0] - pt[0], ct[2] - pt[2])
            if best is None or dh < best[0]:
                best = (dh, ct[1] - pt[1], crel, c)
        if best is None or best[0] > PEDESTAL_REACH or not (-0.5 <= best[1] <= 1.5):
            out.append({"file": rel, "hash": str(p["Hash"]), "actor": p["Gyaml"], "chest": None,
                        "why": "no chest stands on it in this level (boss-rush rooms, an adult-only Zora's Domain "
                               "pedestal)"})
            continue
        dh, dy, crel, c = best
        out.append({"file": rel, "hash": str(p["Hash"]), "actor": p["Gyaml"], "chest_hash": str(c["Hash"]),
                    "chest_file": crel, "chest_actor": c["Gyaml"], "distance": round(dh, 3)})
    return out


def shape_box(files, name):
    b = _byml(files[name])["AutoCalc"]
    return [round(b["Min"][k], 3) for k in "XYZ"], [round(b["Max"][k], 3) for k in "XYZ"]


def chest_spots(fs, ap, chests, solid, peds):
    """{chest hash: [spot per level file]} for the chests a look option may retype, plus the chest types of every level.
    Each spot has what a swap needs: the target types that accept every setting the placement carries
    (tools/actor_params.py), a pedestal under it, the nearest other object (room for a big chest) and appear/spawn
    settings."""
    types = defaultdict(set)
    for rel, c in chests:
        types[level_of(rel)].add(c["Gyaml"])
    pedestal_of = {(level_of(p["chest_file"]), p["chest_hash"]) for p in peds if p.get("chest_hash")}
    spots = defaultdict(list)
    for rel, c in chests:
        if c["Gyaml"] not in LOOK_TYPES:
            continue
        lvl, t = level_of(rel), c["Translate"]
        dyn = sorted((c.get("Dynamic") or {}).keys())
        near = None
        for _orel, o in solid[lvl]:
            if o is c:
                continue
            u = o["Translate"]
            if abs(u[1] - t[1]) > ROOM_HEIGHT:
                continue
            dh = math.hypot(u[0] - t[0], u[2] - t[2])
            limit = ROOM_CHEST if o["Gyaml"].startswith("Obj_TBox") else ROOM_OBJECT
            if dh < limit and (near is None or dh < near[1]):
                near = [o["Gyaml"], round(dh, 2)]
        spots[str(c["Hash"])].append({
            "file": rel, "level": lvl, "actor": c["Gyaml"], "dynamic": dyn,
            "accepted_by": [x for x in LOOK_TYPES if set(dyn) <= ap.allowed(x)],
            "pedestal": (lvl, str(c["Hash"])) in pedestal_of,
            "blocked_by": near, "spawn_type": (c.get("Dynamic") or {}).get("SpawnType"),
            "linked": bool(c.get("Links"))})
    sizes = {}
    for actor, shape in (("Obj_TBox_A_01", "Obj_TBox_A_01__Body_0"), ("Obj_TBox_A_02", "Obj_TBox_A_02__Body_0")):
        files = sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))
        sizes[actor] = shape_box(files, f"Phive/ShapeParam/{shape}.phive__ShapeParam.bgyml")
    return {lvl: sorted(ts) for lvl, ts in sorted(types.items())}, dict(spots), sizes


def build(romfs=DEFAULT_ROMFS, write=True):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    ap = ActorParams(romfs)
    dm = json.load(open(DROP_MAP, encoding="utf-8"))
    kinds = {}
    for sec in ("drops", "extras"):
        for e in dm[sec].values():
            for p in e.get("placements", []):
                kinds.setdefault(p["actor"], p["category"])
    for a in CHESTS:
        kinds[a] = "chest"
    for a in PEDESTALS:
        kinds[a] = "chest_pedestal"
    tints, peds, chests, pots, solid = scan_levels(fs, romfs)
    actors = {}
    for actor, kind in sorted(kinds.items()):
        if kind.startswith("freestanding") or kind == "gold_skulltula":
            continue  # pickups show themselves, and a Gold Skulltula isn't a container
        declared = sorted(ap.declared(actor) & set(KEYS + ["GameModelController_GeneralInstanceParam3"]))
        m = model_of(fs, actor)
        model, mats, variation = None, None, []
        if m:
            model, mats = model_materials(fs, romfs, m[0], m[1])
            variation = [v.get("Fmab") for v in m[2]]
        actors[actor] = {"kind": kind, "declares": declared, "model": model, "materials": mats,
                         "model_variation": variation, "vanilla_tints": dict(tints.get(actor, {}))}
    # graphs that read the colour, which are those of models vanilla colours per placement. Any declaring type counts,
    # not just item holders, since candle sticks, push blocks and pedestals share graphs with rocks.
    proven = defaultdict(set)
    for actor, kind in list(actors.items()):
        if kind["vanilla_tints"] and any(v != str((1.0, 1.0, 1.0)) for v in kind["vanilla_tints"]):
            for mat in kind["materials"] or []:
                for gid in mat["graphs"]:
                    proven[gid].add(actor)
    for extra in ("Obj_CandleStick_A_01", "Obj_SpiritTemple_MovableBox_A_01", "Obj_FireTemple_HammerSlipPillar_A_01"):
        try:
            m = model_of(fs, extra)
            _, mats = model_materials(fs, romfs, m[0], m[1])
        except (KeyError, TypeError, ValueError):
            continue
        if tints.get(extra) and mats:
            for mat in mats:
                for gid in mat["graphs"]:
                    proven[gid].add(extra)
    for actor, info in actors.items():
        graphs = {g for mat in info["materials"] or [] for g in mat["graphs"]}
        if len(info["declares"]) >= 3 and graphs & set(proven):
            info["tint"] = "proven"
        elif len(info["declares"]) >= 3:
            info["tint"] = "declared"
            info["why"] = "declares the colour keys, but no material builds its albedo from an expression graph"
        else:
            info["tint"] = "none"
            info["why"] = "no per-placement look setting (its actor pack declares only " + \
                          (", ".join(sorted(ap.declared(actor))) or "nothing") + ")"
    pedestals = pair_pedestals(peds, chests)
    level_types, spots, sizes = chest_spots(fs, ap, chests, solid, pedestals)
    out = {
        "_about": "Built by tools/rando/parity/_appearance_build.py from the game files. Which item holders can show "
                  "a look per placement (tint), with the evidence; chest pedestals with the chest on them; pot "
                  "types per level; chest types per level and every retypable chest spot (types its settings "
                  "allow, pedestal, nearest object for the room check, appear settings). Read by "
                  "tools/rando/parity/appearance.py.",
        "romfs": romfs,
        "tint_keys": KEYS,
        "tint_graphs": {g: sorted(a) for g, a in sorted(proven.items())},
        "actors": actors,
        "pedestals": pedestals,
        "pot_types_per_level": {lvl: dict(c) for lvl, c in sorted(pots.items())},
        "chest_body_boxes": {a: {"min": mn, "max": mx} for a, (mn, mx) in sizes.items()},
        "chest_types_per_level": level_types,
        "chest_spots": spots,
    }
    if write:
        json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out


def main(argv):
    out = build(argv[1] if len(argv) > 1 else DEFAULT_ROMFS)
    by = Counter(v["tint"] for v in out["actors"].values())
    print(f"{len(out['actors'])} item-holder types: " + ", ".join(f"{n} {k}" for k, n in sorted(by.items())))
    for a, v in sorted(out["actors"].items()):
        print(f"  {v['tint']:8s} {a} ({v['kind']})")
    paired = [p for p in out["pedestals"] if p.get("chest_hash")]
    print(f"{len(paired)}/{len(out['pedestals'])} chest pedestals carry a chest")
    multi = [lvl for lvl, c in out["pot_types_per_level"].items() if len([t for t in c if t.startswith("Obj_Pot")]) > 1]
    print(f"levels with more than one pot type: {len(multi)} of {len(out['pot_types_per_level'])}")
    spots = [x for v in out["chest_spots"].values() for x in v]
    print(f"{len(spots)} retypable chest spots ({len(out['chest_spots'])} placements); no room for a big chest at "
          f"{sum(1 for x in spots if x['blocked_by'])}, on a pedestal {sum(1 for x in spots if x['pedestal'])}")
    print(f"written to {os.path.relpath(OUT, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
