"""Performance audit of a built patch: what the randomizer adds that costs memory, load time or frame time.

usage: python tools/rando/perf_audit.py OUT_DIR        (OUT_DIR holds patch/ and plan.json, as generate.py writes)

Reports, against the vanilla files (original/ first):
  - every AI file the patch changed: vanilla and patched node counts, and the added nodes that can run every frame
    (selectors, Execute nodes, queries without OutputOnlyOnEnter, OneShots with ExecuteEveryFrame) as opposed to
    once (OneShots run once when their branch is entered, and queries feeding only them run then too). An AI shared
    by many placed objects (pots, grass) multiplies its per-frame cost by the objects loaded in an area;
  - ActorInfo instance-heap raises, times the number of placements of that type (memory reserved when all are
    loaded), the busiest level file per type;
  - level files that grew (twins, new placements), GameDataList growth (save size), and the biggest file growths.
Nothing here measures the game. It lists the costs, largest first, so they can be checked against Longshot's frame
statistics (the fps counter and the log's frame lines) in the busiest places it names.
"""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # REMAKE_ROMFS: the app
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
PER_FRAME_TYPES = {"S32Selector", "F32Selector", "BoolSelector", "StringSelector", "RandomSelector", "Simultaneous",
                   "Sequential"}


def _props(n):
    return {e["name"]: e.get("value") for t in n["properties"] for e in n["properties"][t]}


def per_frame(a, i):
    """True if node i can run or be evaluated every frame while its branch is active."""
    import ainb
    n = a.nodes[i]
    kind = ainb.NODE_TYPES.get(n["type"], "")
    if kind in PER_FRAME_TYPES:
        return True
    name = n["name"]
    p = _props(n)
    if name.startswith("OneShot") or name.startswith("Oneshot"):
        return bool(p.get("ExecuteEveryFrame"))
    if name.startswith("Query"):
        return not p.get("OutputOnlyOnEnter", False)
    return name.startswith("Execute")


def audit_ai(van, new):
    """{(pack, file): {...}} for every AI file the patch changed."""
    from romtools import sarc_files
    import ainb
    import packpaths  # noqa: F401 - for symmetry with the plan tools
    out = {}
    seen = set()
    patch_root = new.patch_dirs[0] if getattr(new, "patch_dirs", None) else None
    for dirpath, _, files in os.walk(os.path.join(patch_root, "Pack")) if patch_root else []:
        for fn in files:
            if not fn.endswith(".pack.zs"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), patch_root).replace("\\", "/")
            try:
                nf, vf = sarc_files(new.read(rel)), sarc_files(van.read(rel))
            except Exception:  # noqa: BLE001 - a pack new to the game
                continue
            for name, data in nf.items():
                if not name.endswith(".ainb") or vf.get(name) == data or name in seen:
                    continue
                seen.add(name)
                b = ainb.Ainb(data)
                a = ainb.Ainb(vf[name]) if name in vf else None
                n0 = len(a.nodes) if a else 0
                added = list(range(n0, len(b.nodes)))
                pf = Counter(b.nodes[i]["name"] or ainb.NODE_TYPES.get(b.nodes[i]["type"], "?")
                             for i in added if per_frame(b, i))
                out[(rel, name)] = {"vanilla_nodes": n0, "nodes": len(b.nodes), "added": len(added),
                                    "added_per_frame": sum(pf.values()), "per_frame_kinds": dict(pf.most_common(8))}
    return out


def placements_by_type(fs, romfs):
    """{actor type: (count, {level file: count})} over every vanilla level file."""
    from romtools import byml_load
    out = defaultdict(lambda: [0, Counter()])
    banc = os.path.join(romfs, "Banc")
    for area in sorted(os.listdir(banc)):
        d = os.path.join(banc, area)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".bcett.byml.zs"):
                continue
            rel = f"Banc/{area}/{fn}"
            try:
                acts = byml_load(fs.read(rel))[0].get("Actors", [])
            except Exception:  # noqa: BLE001
                continue
            for a in acts:
                g = a.get("Gyaml")
                out[g][0] += 1
                out[g][1][rel] += 1
    return out


def main(argv):
    from romtools import Romfs, byml_load
    import ainb  # noqa: F401
    out_dir = argv[1]
    romfs = argv[2] if len(argv) > 2 else DEFAULT_ROMFS
    patch = os.path.join(out_dir, "patch")
    van = Romfs(romfs, os.path.join(HERE, "original"))
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    new.patch_dirs = [patch]
    report = []
    ai = audit_ai(van, new)
    by_type = placements_by_type(van, romfs)
    # which actor types run each AI file (the pack names it)
    users = defaultdict(set)
    for (rel, name) in ai:
        users[name].add(os.path.basename(rel).replace(".pack.zs", ""))
    rows = []
    for name in sorted({n for _, n in ai}):
        info = next(v for (r, n), v in ai.items() if n == name)
        placed = sum(by_type.get(t, [0])[0] for t in users[name])
        busiest = Counter()
        for t in users[name]:
            busiest.update(by_type.get(t, [0, Counter()])[1])
        top = busiest.most_common(1)[0] if busiest else ("-", 0)
        rows.append((info["added_per_frame"] * max(top[1], 1), name, info, placed, top))
    report.append("== AI files changed (sorted by added per-frame nodes x objects in the busiest level)")
    for score, name, info, placed, top in sorted(rows, reverse=True):
        report.append(f"{name}: nodes {info['vanilla_nodes']} -> {info['nodes']} (+{info['added']}, "
                      f"{info['added_per_frame']} can run every frame: {info['per_frame_kinds']}); placed "
                      f"{placed}x, busiest {os.path.basename(top[0])} {top[1]}x")
    # heap raises
    old = {r.get("__RowId"): r.get("InstanceHeapSize") for r in byml_load(van.read(ACTOR_INFO))[0]}
    cur = {r.get("__RowId"): r.get("InstanceHeapSize") for r in byml_load(new.read(ACTOR_INFO))[0]}
    report.append("== instance heap raises (per instance; x placements = reserved if all were loaded)")
    heap = []
    for t, v in cur.items():
        if old.get(t) != v and v is not None:
            n, files = by_type.get(t, [0, Counter()])
            top = files.most_common(1)[0] if files else ("-", 0)
            heap.append(((v - (old.get(t) or 0)) * max(top[1], 1), t, old.get(t), v, n, top))
    for score, t, a, b, n, top in sorted(heap, reverse=True):
        report.append(f"{t}: {a} -> {b} (+{(b - (a or 0)) // 1024} KB each); placed {n}x, busiest "
                      f"{os.path.basename(top[0])} {top[1]}x = +{score // 1024} KB there")
    # level growth and save size
    report.append("== level files: placements added")
    grow = []
    for dirpath, _, files in os.walk(os.path.join(patch, "Banc")):
        for fn in files:
            rel = os.path.relpath(os.path.join(dirpath, fn), patch).replace("\\", "/")
            try:
                a = len(byml_load(van.read(rel))[0].get("Actors", []))
                b = len(byml_load(new.read(rel))[0].get("Actors", []))
            except Exception:  # noqa: BLE001
                continue
            if b != a:
                grow.append((b - a, rel, a, b))
    for d, rel, a, b in sorted(grow, reverse=True)[:15]:
        report.append(f"{rel}: {a} -> {b} actors (+{d}; only one of each twin pair is ever created)")
    report.append(f"   ... {len(grow)} level files grew, +{sum(g[0] for g in grow)} placements in all")
    gd = "GameData/GameDataList.Product.110.byml.zs"

    def meta(fs):
        raw = fs.read(gd)
        try:
            raw = fs.zs.decompress(raw)
        except Exception:  # noqa: BLE001
            pass
        return byml_load(raw, allow_big=True)[0]["MetaData"], len(raw)
    (m0, s0), (m1, s1) = meta(van), meta(new)
    report.append(f"== save data: progress.sav buffer {m0['SaveDataSize'][0]} -> {m1['SaveDataSize'][0]} bytes "
                  f"(+{m1['SaveDataSize'][0] - m0['SaveDataSize'][0]}); GameDataList {s0} -> {s1} bytes")
    # biggest file growths
    report.append("== biggest file growths (load time, memory)")
    sizes = []
    for dirpath, _, files in os.walk(patch):
        for fn in files:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, patch).replace("\\", "/")
            if rel.startswith("System/Resource"):
                continue
            try:
                v = len(van.raw(rel)) if os.path.exists(van.path(rel)) else 0
            except Exception:  # noqa: BLE001
                v = 0
            sizes.append((os.path.getsize(p) - v, rel, v, os.path.getsize(p)))
    for d, rel, a, b in sorted(sizes, reverse=True)[:12]:
        report.append(f"{rel}: {a} -> {b} (+{d // 1024} KB)")
    text = "\n".join(report)
    print(text)
    with open(os.path.join(out_dir, "perf_audit.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv))
