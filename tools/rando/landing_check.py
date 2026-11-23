"""Where each shuffled object's drop lands, and whether Link can get it there.

A drop is made where its object says (drops.py "Falling pickups"). A pot, rock, crate or grass makes it where it
breaks (on its own floor, or wherever Link throws it), a tree at its canopy bone, a Gold Skulltula where it dies,
and a beehive or a Gerudo decoration where it hangs. Every dropped pickup now falls straight down to the first
solid floor. This tool follows that fall for every drop placement of data/rando/drop_map.json over the level
collision (tools/reach.py) and records where it ends:

  base        lands at its object's own base (falls at most BASE_DROP m): where Link stood to break it
  kept_away   made inside one of the game's own DropKeepAwayArea boxes, which move a drop out (the boulders and
              silver rocks on grotto holes: vanilla puts one on each)
  with_object the object itself comes down (or flies) first and breaks where it lands or is hit: the drop is made there
  falls       comes down from high up to a floor that Link can walk, drop or climb to from the floor around it
              (reach.NavGrid, no items): the floor under a wall Skulltula, a hive or a hanging decoration
  no_collision the level's collision isn't decoded there (tools/phive_shape.py): ground objects only, which rest on
              their floor in the game
  bad         falls into a grotto hole or a pit, onto a ledge cut off from its surroundings, into lava, or under
              deeper water than Link can reach without diving

data/rando/drop_landings.json holds the result (python tools/rando/landing_check.py [ROMFS]: ~5 min on 12 workers).
Every "bad" spot needs an entry in HANDLED, either a game fix in drops.py or a logic rule that asks what the game
asks. verify() is in_game_check's read-back: every object a built plan gives a falling drop has a landing record,
and none is "bad" unless HANDLED says how it's dealt with.
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "gamedb"), os.path.join(HERE, "tools", "rando")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = os.path.join(HERE, "data", "rando", "drop_landings.json")
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
BASE_DROP = 2.0            # m: a drop falling this far or less lands at its object's base
TREE_BONE_Y = 6.0          # Obj_Tree_A_01's model (Model/Obj_Tree_A.Obj_Tree_A_01.bfres): bone ItemDropPoint (0, 6, 0)
TREE_RING = (0.0, 1.5, 3.0)  # where around the trunk the canopy drop may start (QueryShakingTreeCalcDropPos turns it
#                              DropDirRotateOffset +- DropDirRotateOffsetRandam off the hit's direction)
TREE_BASE_DROP = TREE_BONE_Y + 1.5
DIVE_DEPTH = 1.0           # m of water over a landing: deeper needs a dive (OoTR: Silver Scale / Iron Boots)
REACH_WINDOW = 14.0        # m around a "falls" landing: the NavGrid box
REACH_FROM = 9.0           # m: the landing must be reachable from floors at least this far from it
NEAR_FLOOR, NEAR_ACROSS = 8.0, 10.0  # m: a floor this close under and beside an object is one Link hits it from
PICK_REACH = 1.5           # m: Link takes a pickup lying this close to where he stands (a root, a step, a bump)
HAZARD = {"Lava", "Bog", "PoisonBog"}
WATER_MAT = {"Water", "HotWater", "IceWater", "ContaminatedWater", "WaterSlip"}
# objects resting on a floor: broken where they stand, or lifted and thrown (then the drop is where Link throws it)
GROUND = {"pot", "pot_always_respawn", "crate", "rock_liftable", "rock_bombable", "grass",
          "grass_always_respawn", "bush", "red_ice", "icicle"}
WITH_OBJECT = {"icicle_falling": "the icicle falls and breaks on the floor first; the drop is made there",
               "palm_fruit": "the fruit falls and breaks on the ground (PalmFruit.root: dies on contact)",
               "butterfly": "the butterfly flies about; it turns into its fairy where Link hits it",
               "flying_pot": "the pot flies at Link and breaks where it hits",
               "rock_silver": "Link lifts the silver rock and throws it; it breaks where it lands"}
# "Bad" landings the spot's own logic already covers (verify() accepts them). Every other "bad" landing needs the
# game fix, where its placement's drop is made at the record's "drop_at" (drops.DROP_AT_*).
HANDLED = {"Water Temple GS Behind Gate": "its rule asks for the Iron Boots (with the Hookshot and the Zora Tunic): "
                                          "Link walks the floor under that water, where the drop sinks"}


UNDECODED = ("InsideJabuJabuBelly",)  # areas whose walkable floors tools/phive_shape.py doesn't decode (living walls)


def area_undecoded(p):
    return p["file"].split("/")[1] in UNDECODED


KEEP_AWAY = "DropKeepAwayArea"  # The game moves drops out of these boxes (unit cubes scaled by the placement).
# Grotto holes under boulders or silver rocks use 2.75 x 7.7 x 2.75.
# Pits and moving floors can have boxes too.


def _keep_away_boxes(area_dir, age, romfs):
    """[(translate, rotation matrix, half extents)] of the area's DropKeepAwayArea placements (this age's files and
    the shared ones)."""
    import drops as D
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    other = "_Adult" if age == "Child" else "_Child"
    out = []
    for f in sorted(os.listdir(os.path.join(romfs, area_dir))):
        if not f.endswith(".bcett.byml.zs") or other in f:
            continue
        for a in byml_load(fs.read(f"{area_dir}/{f}"))[0].get("Actors", []):
            if a.get("Gyaml") != KEEP_AWAY or not a.get("Translate"):
                continue
            sc = a.get("Scale") or [1.0, 1.0, 1.0]
            sc = [float(sc)] * 3 if not isinstance(sc, list) else [float(v) for v in sc]
            out.append((a["Translate"], D._euler(a.get("Rotate")), [0.5 * v for v in sc]))
    return out


def _kept_away(o, boxes):
    for t, rot, half in boxes:
        d = [o[i] - t[i] for i in range(3)]
        local = [sum(rot[k][i] * d[k] for k in range(3)) for i in range(3)]
        if all(abs(local[i]) <= half[i] for i in range(3)):
            return t
    return None


def _key(p):
    return f"{p['file']}#{p['hash']}"


def _age(p):
    f = os.path.basename(p["file"])
    m = re.search(r"_(Child|Adult)", f)
    return m.group(1) if m else ("Child" if p.get("age") == "child" else "Adult")


def _groups(m):
    out = {}
    for sec in ("drops", "new"):
        for n, e in m[sec].items():
            if e.get("kind") != "drop":
                continue
            for p in e.get("placements", []):
                if not p.get("pos"):
                    continue
                area = p["file"].split("/")[1]
                variant = "Alternative" if "Alternative" in os.path.basename(p["file"]) else None
                out.setdefault((area, _age(p), variant), []).append((n, p))
    return out


def origins(p):
    """Where the object makes its drop (for a tree: a ring around its canopy bone)."""
    x, y, z = p["pos"]
    if p["category"] == "tree":
        return [(x + r * math.cos(a), y + TREE_BONE_Y, z + r * math.sin(a))
                for r in TREE_RING for a in ([0.0] if r == 0 else [k * math.pi / 4 for k in range(8)])]
    return [(x, y + 0.4, z)]


def _fall(w, o, own):
    """The first floor a drop made at `o` falls onto: (Hit or None, hazard, abyss)."""
    import reach
    hazard = abyss = None
    for h in w.hits(o, (o[0], o[1] - 300.0, o[2])):
        g = h.part.get("gyaml") or ""
        mat = (h.material or "").split(":")[0]
        if "Abyss" in g and abyss is None:
            abyss = (g, round(h.y, 2))
        if mat in HAZARD and h.normal[1] > 0.05:
            hazard = (mat, round(h.y, 2))
            return None, hazard, abyss
        if mat in WATER_MAT or not reach.LINE(h.part) or h.normal[1] <= 0.3:
            continue
        if str(h.part.get("hash")) == own:
            continue  # the object's own body: gone once it breaks (a tree keeps its own, so it never matches below)
        return h, hazard, abyss
    return None, hazard, abyss


def _water_depth(p, pt, romfs):
    """How deep under a fixed water surface of its scene the point lies (0 if none)."""
    import drops as D
    base = os.path.basename(p["file"])
    other = "_Child" if "_Adult" in base else "_Adult" if "_Child" in base else None
    best = 0.0
    for t, rot, sc, mn, mx in D._water_surfaces(os.path.dirname(p["file"]), other, romfs):
        d = [pt[i] - t[i] for i in range(3)]
        local = [sum(rot[k][i] * d[k] for k in range(3)) / (sc[i] or 1.0) for i in range(3)]
        if mn[0] <= local[0] <= mx[0] and mn[2] <= local[2] <= mx[2]:
            depth = (mx[1] - local[1]) * abs(sc[1] or 1.0)
            if 0 < depth < 60:
                best = max(best, depth)
    return round(best, 2)


def _reachable(w, fs, land, age):
    """Can Link walk, drop or climb (no items) to `land` from the floors around it (REACH_FROM m and more away)?"""
    import reach
    x, y, z = land
    g = reach.NavGrid(w, x - REACH_WINDOW, z - REACH_WINDOW, x + REACH_WINDOW, z + REACH_WINDOW, age, cell=0.5,
                      ymin=y - 8.0, ymax=y + 16.0)
    near = [((i, j), k) for (i, j), fl in g.floors.items() for k, (fy, _) in enumerate(fl)
            if math.hypot(g.xs[i] - x, g.zs[j] - z) <= PICK_REACH and y - 1.5 <= fy <= y + 0.6]
    if not near:
        return None, "no floor Link can stand on within reach of it (too steep, no headroom, or off the grid)"
    starts = [((i, j), k) for (i, j), fl in g.floors.items() for k in range(len(fl))
              if math.hypot(g.xs[i] - x, g.zs[j] - z) >= REACH_FROM]
    seen = g.reach(starts)
    got = [nd for nd in near if nd in seen]
    return bool(got), f"{len(got)} of {len(near)} floors within reach of it reached from {len(starts)} floors "                       f"{REACH_FROM:.0f}+ m away"


def drop_at(w, o, age, depth=None):
    """For a drop that would land out of reach, the walkable floor nearest under the object (horizontally) that Link
    reaches from the floors around it (REACH_FROM m and more away, no items), as [x, y, z] just above the floor. None
    if there's none in the window. The object's drop is then made there (drops.DROP_AT_*)."""
    import reach
    x, y, z = o
    g = reach.NavGrid(w, x - REACH_WINDOW, z - REACH_WINDOW, x + REACH_WINDOW, z + REACH_WINDOW, age, cell=0.5,
                      ymin=y - 40.0, ymax=y + 0.5)
    starts = [((i, j), k) for (i, j), fl in g.floors.items() for k in range(len(fl))
              if math.hypot(g.xs[i] - x, g.zs[j] - z) >= REACH_FROM]
    seen = g.reach(starts)
    best = None
    for nd in seen:
        (i, j), k = nd
        fy = g.floors[(i, j)][k][0]
        d = math.hypot(g.xs[i] - x, g.zs[j] - z)
        if depth is not None and depth((float(g.xs[i]), fy, float(g.zs[j]))) > DIVE_DEPTH:
            continue
        # A floor Link would stand on to hit the object (within NEAR_FLOOR m under it and NEAR_ACROSS m across)
        # comes first, then the nearest across, then the highest.
        key = (0 if (y - fy <= NEAR_FLOOR and d <= NEAR_ACROSS) else 1, round(d * 2) / 2, -fy)
        if best is None or key < best[0]:
            best = (key, [round(float(g.xs[i]), 2), round(fy + 0.3, 2), round(float(g.zs[j]), 2)], d)
    return (best[1], round(best[2], 2)) if best else (None, None)


def _spot(w, fs, n, p, romfs):
    import reach
    rec = {"name": n, "category": p["category"], "actor": p["actor"], "pos": p["pos"]}
    cat = p["category"]
    if cat in WITH_OBJECT:
        rec.update(verdict="with_object", why=WITH_OBJECT[cat])
        return rec
    if w is None:
        rec.update(verdict="no_collision" if cat in GROUND else "bad",
                   why="the level's collision isn't decoded here" + ("" if cat in GROUND else ": not checked"))
        return rec
    boxes = _keep_away_boxes(os.path.dirname(p["file"]), _age(p), romfs)
    if cat in GROUND and any(_kept_away(o, boxes) for o in origins(p)):
        t = next(_kept_away(o, boxes) for o in origins(p) if _kept_away(o, boxes))
        rec.update(verdict="kept_away", why=f"made inside the game's own {KEEP_AWAY} at "
                                            f"{[round(v, 2) for v in t]}: the game moves it out (the grotto hole's rim)")
        return rec
    worst = None
    for o in origins(p):
        h, hazard, abyss = _fall(w, o, str(p["hash"]))
        if h is None and not hazard and cat in GROUND:
            # For an object sunk into the ground (its origin under the surface) the drop starts on the surface above.
            g, _, _ = _fall(w, (o[0], o[1] + 1.5, o[2]), str(p["hash"]))
            if g is not None and g.y >= o[1] - 0.5:
                h = g
        land = {"o": [round(v, 2) for v in o]}
        if hazard:
            land["hazard"] = hazard
        if h is not None:
            land.update(y=round(h.y, 2), drop=round(o[1] - h.y, 2),
                        on=(h.part.get("gyaml") or h.part.get("kind") or "")[:60])
            depth = _water_depth(p, (o[0], h.y, o[2]), romfs)
            if depth:
                land["water"] = depth
        if abyss and (h is None or abyss[1] > h.y):
            land["abyss"] = abyss
        if worst is None or land.get("drop", 1e9) > worst.get("drop", -1) or "y" not in land:
            worst = land
    rec["land"] = worst
    lim = TREE_BASE_DROP if cat == "tree" else BASE_DROP
    if area_undecoded(p) and worst.get("drop", 0) > lim:
        rec.update(verdict="no_collision", why=f"falls {worst.get('drop')} m in a level whose floors aren't all "
                                               f"decoded (tools/phive_shape.py): not judged")
        return rec
    if "y" not in worst:
        if area_undecoded(p) and not worst.get("hazard"):
            rec.update(verdict="no_collision", why="the level's floors aren't decoded here (tools/phive_shape.py)")
        elif "Abyss" in str(worst.get("abyss")) or cat not in GROUND:
            rec.update(verdict="bad", why="nothing under it: it falls out of the level" if not worst.get("hazard")
                       else f"it falls into {worst['hazard'][0]}")
        else:
            rec.update(verdict="no_collision", why="no floor decoded under a ground object (it rests on one in game)")
        if rec["verdict"] == "bad" and cat not in GROUND:
            at, d = drop_at(w, origins(p)[0], _age(p), lambda pt: _water_depth(p, pt, romfs))
            if at is not None:
                rec.update(drop_at=at, drop_at_across=d)
        return rec
    if worst.get("hazard"):
        rec.update(verdict="bad", why=f"it falls into {worst['hazard'][0]}")
    elif worst.get("water", 0) > DIVE_DEPTH and worst["drop"] > lim:
        rec.update(verdict="bad", why=f"it sinks to a floor {worst['water']} m under water (a dive)")
    elif "HidingHoleJoint" in worst.get("on", "") and worst["drop"] > lim:
        rec.update(verdict="bad", why=f"it falls {worst['drop']} m into the grotto hole under it ({worst['on']})")
    elif worst["drop"] <= lim:
        rec.update(verdict="base", why=f"lands {worst['drop']} m below where it is made, at its base")
    else:
        ok, how = _reachable(w, fs, (worst["o"][0], worst["y"], worst["o"][2]), _age(p))
        if ok:
            rec.update(verdict="falls", why=f"falls {worst['drop']} m onto {worst['on']}, reachable from around it "
                                            f"({how})")
        else:
            rec.update(verdict="bad", why=f"falls {worst['drop']} m onto {worst['on']}, which Link can't walk, drop "
                                          f"or climb to from around it ({how})")
    if rec["verdict"] == "bad" and cat not in GROUND and w is not None:
        o = origins(p)[0]
        w.set_filter(reach.EVERYTHING)
        at, d = drop_at(w, o, _age(p), lambda pt: _water_depth(p, pt, romfs))
        if at is not None:
            rec.update(drop_at=at, drop_at_across=d)
    return rec


def _work(args):
    key, items, romfs = args
    area, age, variant = key
    from romtools import Romfs
    import reach
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    try:
        w = reach.World(fs, area, age, variant=variant, include=reach.EVERYTHING)
    except Exception as ex:  # noqa: BLE001  (a level the collision decoder can't read: recorded as such)
        w = None
        err = f"{type(ex).__name__}: {ex}"
    out = {}
    for n, p in items:
        if w is not None:
            w.set_filter(reach.EVERYTHING)
        rec = _spot(w, fs, n, p, romfs)
        if w is None:
            rec["collision_error"] = err
        out[_key(p)] = rec
    return out


def compute(romfs=DEFAULT_ROMFS, workers=12):
    """{file#hash: landing record} for every drop placement of the drop map."""
    import multiprocessing as mp
    import drops as D
    m = D._map()
    jobs = [(k, v, romfs) for k, v in sorted(_groups(m).items(), key=lambda kv: -len(kv[1]))]
    out = {}
    with mp.Pool(workers) as pool:
        for part in pool.imap_unordered(_work, jobs):
            out.update(part)
    return dict(sorted(out.items()))


def _drop_placements(plan):
    """{file#hash: drop actor} of every object the plan gives a falling drop (a skulltula's own token stays)."""
    import drops as D
    falling = set(D.DROP_ACTOR.values()) | {D.DISGUISE_ACTOR, "Obj_Dungeon_SmallKey"}
    out = {}
    for op in plan.get("placements", []):
        a = (op.get("set") or {}).get("Dynamic.Drop__DropActor")
        if a and a in falling and op.get("twin") is None and a not in D.FLIES:
            out[f"{op['file']}#{op['hash']}"] = a
    return out


def verify(plan, data=None):
    """Checks a built plan and returns [problem]. Every object it gives a falling drop has a landing record
    (data/rando/drop_landings.json), and none lands "bad" unless HANDLED deals with it. Also returns {verdict:
    count}."""
    data = data if data is not None else json.load(open(OUT, encoding="utf-8"))
    spots = data["spots"]
    import drops as D
    m = D._map()
    cat = {}
    for sec in ("drops", "new"):
        for e in m[sec].values():
            for p in e.get("placements", []):
                cat[_key(p)] = p.get("category")
    bad, counts = [], {}
    at = {}  # placements the plan makes drop elsewhere (DROP_AT_*): {file#hash: [x, y, z]}
    for op in plan.get("placements", []):
        st = op.get("set") or {}
        if st.get(f"Dynamic.{D.DROP_AT_KEY}"):
            at[f"{op['file']}#{op['hash']}"] = [float(st.get(f"Dynamic.{x}", 0.0)) for x in D.DROP_AT_XYZ]
    for k, actor in sorted(_drop_placements(plan).items()):
        if cat.get(k) is None:
            continue  # not a shuffled object (a vanilla drop the plan only retypes, e.g. a heart turned rupee)
        if cat.get(k) == "gold_skulltula" and actor == "Obj_Token_Gold":
            continue
        rec = spots.get(k)
        if rec is None:
            bad.append(f"{k}: no landing record (run tools/rando/landing_check.py)")
            continue
        v = rec["verdict"]
        if v == "bad" and rec["name"] in HANDLED:
            v = "logic"
        elif v == "bad" and rec.get("drop_at") and at.get(k) == [float(x) for x in rec["drop_at"]]:
            v = "drop_at"
        counts[v] = counts.get(v, 0) + 1
        if v == "bad":
            bad.append(f"{rec['name']} ({k.split('/')[-1]}): its drop {rec['why']}"
                       + (f"; the plan doesn't make it at {rec['drop_at']}" if rec.get("drop_at") else ""))
    return bad, counts


def main(argv):
    romfs = argv[1] if len(argv) > 1 else DEFAULT_ROMFS
    spots = compute(romfs)
    counts = {}
    for r in spots.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    data = {"_about": __doc__.split("\n\n")[0] + " Written by tools/rando/landing_check.py.",
            "counts": dict(sorted(counts.items())), "spots": spots}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(f"{len(spots)} drop placements: " + ", ".join(f"{v} {n}" for v, n in sorted(counts.items())))
    for k, r in spots.items():
        if r["verdict"] == "bad":
            print(f"  bad: {r['name']} ({k.split('/')[-1]}): {r['why']}"
                  + (f" [handled: {HANDLED[r['name']]}]" if r["name"] in HANDLED else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
