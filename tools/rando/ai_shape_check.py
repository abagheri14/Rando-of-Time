"""Read-back check that every AI node the patch adds or changes has a shape the game's own AI files use.

Writing an instance param like Drop__DropActor through ExecuteBlackboardSetString (BlackboardType 1) crashes the
game on New Game. Instance params (IsInstanceParam in the Drop blackboard table) are set by the placement, so the
node's first run caches no change counter for them (-1) and the write goes to address -1 (exception 0xc0000005 in
Land_Tree_BeechMiddle_A_01.root, Kokiri Forest trees 2, 3 and 5). The game's own AI writes 808 different keys
through BlackboardType 1 and none of them is an instance parameter.

verify(patch, romfs) reads every AI file (.ainb, in a pack or loose) the patch changes and refuses, per node:
  - a node name the game's AI files never use (a module reference, "*.module", names a file and is left alone);
  - a parameter (properties, inputs, outputs: its kind, type and name) that node never has in the game's files;
  - a BlackboardType value the game never gives that node (e.g. QueryBlackboardGetString only reads 1 and 3);
  - a blackboard write (ExecuteBlackboardSet*, BlackboardType 1) to a key that is an instance parameter in any
    blackboard table, the game's or the patch's (the New Game crash above).
PROVEN lists the shapes outside the game's that I've seen run in game, each with what ran it.

The game's shapes are read once from the romfs and kept in cache/ai_shapes.json (rebuilt when the romfs path or its
AI pack changes).
usage: python tools/rando/ai_shape_check.py PATCH_DIR [ROMFS]
verify(patch, romfs) -> (problems, files checked)"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))

CACHE = os.path.join(HERE, "cache", "ai_shapes.json")
GLOBAL_AI = "Pack/AI.Global.Product.111.pack.zs"
WRITES = ("ExecuteBlackboardSetString", "ExecuteBlackboardSetBool", "ExecuteBlackboardSetF32",
          "ExecuteBlackboardSetS32", "ExecuteBlackboardSetVec3f", "ExecuteBlackboardSetU32")
# Extra (node name, BlackboardType) pairs that worked in playtests.
PROVEN = {("QueryBlackboardGetString", 0): "seen in game (DropItem.root's taken-pickup read of its AI-local name)",
          ("QueryBlackboardGetF32", 1): "seen in game (drops DROP_TAG_KEY: every shuffled dropper's root AI reads its "
                                        "tag; Kokiri Forest's trees ran it)"}


def _params(nd):
    """{(kind, type, name)} of a node's parameter tables."""
    import ainb
    return {(kind, t, e["name"]) for kind in ("properties", "inputs", "outputs")
            for t in ainb.PTYPES for e in nd[kind][t]}


def _prop(nd, name):
    return next((e.get("value") for arr in nd["properties"].values() for e in arr if e["name"] == name), None)


def _ainb_files(fs, rel):
    """{name: bytes} of the AI files a romfs file holds (a pack's .ainb, or the loose file itself)."""
    from romtools import sarc_files
    try:
        data = fs.read(rel) if rel.endswith(".zs") else fs.raw(rel)
    except Exception:
        return {}
    if rel.endswith(".ainb") or rel.endswith(".ainb.zs"):
        return {rel: data}
    try:
        return {n: d for n, d in sarc_files(data).items() if n.endswith(".ainb")}
    except Exception:
        return {}


def _tables(fs, rel):
    """{key: IsInstanceParam} of the blackboard tables a pack holds."""
    from romtools import sarc_files, byml_load
    out = {}
    try:
        files = sarc_files(fs.read(rel))
    except Exception:
        return out
    for n, d in files.items():
        if "BlackboardParamTable" not in n:
            continue
        try:
            root = byml_load(d)[0]
        except Exception:
            continue
        for v in root.values():
            for e in v if isinstance(v, list) else []:
                if isinstance(e, dict) and "BBKey" in e:
                    out[e["BBKey"]] = out.get(e["BBKey"], False) or bool(e.get("IsInstanceParam"))
    return out


def _vanilla_rels(romfs):
    rels = [os.path.relpath(p, romfs).replace(os.sep, "/") for p in sorted(glob.glob(os.path.join(romfs, "Pack", "Actor", "*.pack.zs")))]
    rels.append(GLOBAL_AI)
    for d in ("AI", "Logic", "Sequence"):
        rels += [os.path.relpath(p, romfs).replace(os.sep, "/")
                 for p in sorted(glob.glob(os.path.join(romfs, d, "*.ainb*")))]
    return rels


def vanilla_shapes(romfs):
    """The game's own AI node shapes and instance-parameter keys (cached), as
    {"names": [...], "params": {name: [[kind, type, name]]}, "bbtype": {name: [values]}, "instance": [keys]}."""
    stamp = [os.path.abspath(romfs), os.path.getmtime(os.path.join(romfs, GLOBAL_AI))]
    if os.path.exists(CACHE):
        c = json.load(open(CACHE, encoding="utf-8"))
        if c.get("stamp") == stamp:
            return c
    import ainb
    from romtools import Romfs
    fs = Romfs(romfs, os.environ.get("REMAKE_ORIGINAL") or os.path.join(HERE, "original"))
    params, bbtype, inst, seen = {}, {}, {}, set()
    for rel in _vanilla_rels(romfs):
        if rel.startswith("Pack/Actor/"):
            for k, v in _tables(fs, rel).items():
                inst[k] = inst.get(k, False) or v
        for n, d in _ainb_files(fs, rel).items():
            if n in seen:
                continue
            seen.add(n)
            try:
                a = ainb.Ainb(d)
            except Exception:
                continue
            for nd in a.nodes:
                name = nd["name"] or ""
                params.setdefault(name, set()).update(_params(nd))
                t = _prop(nd, "BlackboardType")
                if t is not None:
                    bbtype.setdefault(name, set()).add(t)
    c = {"stamp": stamp, "files": len(seen),
         "params": {k: sorted(map(list, v)) for k, v in sorted(params.items())},
         "bbtype": {k: sorted(v) for k, v in sorted(bbtype.items())},
         "instance": sorted(k for k, v in inst.items() if v)}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(c, open(CACHE, "w", encoding="utf-8"))
    return c


def node_problems(a, shapes, instance, changed=None):
    """[problem] for the nodes of AI file `a` (all, or the indices in `changed`)."""
    params = shapes["_params"]
    bbtype = shapes["bbtype"]
    out = []
    for i, nd in enumerate(a.nodes):
        if changed is not None and i not in changed:
            continue
        name = nd["name"] or ""
        if name.endswith(".module"):
            continue
        if name not in params:
            out.append(f"node {i} {name}: a node the game's AI files never use")
            continue
        extra = sorted(_params(nd) - params[name])
        if extra:
            out.append(f"node {i} {name}: parameter(s) {extra} the game's {name} never has")
        t = _prop(nd, "BlackboardType")
        if t is not None and t not in bbtype.get(name, ()) and (name, t) not in PROVEN:
            out.append(f"node {i} {name}: BlackboardType {t}, the game's {name} uses only {bbtype.get(name)}")
        if name in WRITES and t == 1 and _prop(nd, "BlackboardKey") in instance:
            out.append(f"node {i} {name}: writes instance parameter {_prop(nd, 'BlackboardKey')} (BlackboardType 1): "
                       f"the game crashes there; the game's AI never writes one")
    return out


def _changed(a, b):
    """Indices of a's nodes that are new or differ from original file b's node of the same index."""
    import ainb
    if b is None:
        return set(range(len(a.nodes)))
    out = set(range(len(b.nodes), len(a.nodes)))
    for i in range(min(len(a.nodes), len(b.nodes))):
        x, y = a.nodes[i], b.nodes[i]
        if x["name"] != y["name"] or ainb.describe_node(a, i) != ainb.describe_node(b, i):
            out.add(i)
    return out


def verify(patch, romfs):
    """Reads the patch's changed AI files against the game's shapes. Returns (problems, AI files checked)."""
    import ainb
    from romtools import Romfs
    shapes = vanilla_shapes(romfs)
    shapes["_params"] = {k: {tuple(x) for x in v} for k, v in shapes["params"].items()}
    orig = os.environ.get("REMAKE_ORIGINAL") or os.path.join(HERE, "original")
    van = Romfs(romfs, orig)
    new = Romfs(romfs, orig, [patch])
    rels = [os.path.relpath(p, patch).replace(os.sep, "/") for p in glob.glob(os.path.join(patch, "**", "*"), recursive=True)
            if os.path.isfile(p) and (p.endswith(".pack.zs") or ".ainb" in os.path.basename(p))]
    instance = set(shapes["instance"])
    for rel in rels:  # the patch's own tables (keys it adds as instance parameters)
        if rel.endswith(".pack.zs"):
            instance |= {k for k, v in _tables(new, rel).items() if v}
    bad, n = [], 0
    for rel in sorted(rels):
        files = _ainb_files(new, rel)
        if not files:
            continue
        try:
            old = _ainb_files(van, rel) if os.path.exists(os.path.join(romfs, rel)) else {}
        except Exception:
            old = {}
        for f, d in sorted(files.items()):
            if old.get(f) == d:
                continue
            n += 1
            a = ainb.Ainb(d)
            b = ainb.Ainb(old[f]) if f in old else None
            bad += [f"{rel}:{f}: {x}" for x in node_problems(a, shapes, instance, _changed(a, b))]
    return bad, n


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
    import drops as D
    p, n = verify(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else D.DEFAULT_ROMFS)
    for x in p:
        print(x)
    print(f"{len(p)} problem(s) in {n} changed AI file(s)")
    sys.exit(1 if p else 0)
