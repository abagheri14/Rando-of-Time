"""Check a plan's entrance edits against the game: build a patch of only those edits and read it back.

usage: python tools/rando/parity/_entrances_verify.py ROMFS PLAN.json OUT_DIR

Takes the doorway edits (placements written by tools/rando/parity/entrances.py) and the scene edits of the files
entrances.py changes, builds them alone into OUT_DIR/patch with tools/make_patch.py, then checks that
- every edited doorway's settings are exactly vanilla + the plan's set/remove, with nothing else on it changed
- no other actor and no other section of those level files changed
Then it prints, per scene file, the steps whose parameters or routing changed and the steps added.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load  # noqa: E402
from evfl import Evfl  # noqa: E402

SCENE_FILES = {"Dm_SY_Ocarina", "Npc_Kaepora_DeathMountainTrail", "Npc_Kaepora_LakeHylia", "OpeningEvent",
               "Get_StoneOfWater"}
OCARINA_STEPS = {"Event15", "Event16", "Event17", "Event18", "Event20", "Event77", "Event147", "Event297"}


def entrance_ops(plan):
    def scene(op):
        f = op.get("file")
        if f not in SCENE_FILES:
            return False
        if f == "OpeningEvent":
            return op.get("add_graph") == "Rando_Spawn" or op.get("event") == "Event11"
        if f == "Dm_SY_Ocarina":
            return op.get("add_graph") in ("Rando_PreludeArrive", "Rando_PreludeStory") or op.get("event") in OCARINA_STEPS
        return True
    return {"placements": [p for p in plan.get("placements", []) if " leads (" in p.get("note", "")],
            "events": [e for e in plan.get("events", []) if scene(e)], "byml": plan.get("byml", [])
            if all("StartPos" in b.get("file", "") for b in plan.get("byml", [])) else []}


def norm(c):
    if not c:
        return None
    if c["type"] == "container":
        return {k: norm(v) for k, v in c["items"].items()}
    return c["type"], c["value"]


def main(romfs, plan_path, out):
    plan = entrance_ops(json.load(open(plan_path, encoding="utf-8")))
    os.makedirs(out, exist_ok=True)
    part = os.path.join(out, "entrance_plan.json")
    json.dump(plan, open(part, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    patch = os.path.join(out, "patch")
    r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "make_patch.py"), romfs, patch, part],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=HERE)
    if r.returncode:
        sys.exit(f"make_patch failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    vfs = Romfs(romfs, os.path.join(HERE, "original"))
    pfs = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch])
    errors = 0
    by_file = {}
    for p in plan["placements"]:
        by_file.setdefault(p["file"], []).append(p)
    for rel, ops in sorted(by_file.items()):
        vroot, proot = byml_load(vfs.read(rel))[0], byml_load(pfs.read(rel))[0]
        van = {str(a["Hash"]): a for a in vroot["Actors"]}
        pat = {str(a["Hash"]): a for a in proot["Actors"]}
        want = {}
        for op in ops:
            d = dict(van[op["hash"]].get("Dynamic") or {})
            for k in op.get("remove", []):
                d.pop(k.split(".", 1)[1], None)
            for k, v in op["set"].items():
                d[k.split(".", 1)[1]] = v
            want[op["hash"]] = d
        if list(van) != list(pat):
            print(f"{rel}: actors added, removed or reordered")
            errors += 1
        for h, a in van.items():
            b = pat[h]
            if h in want:
                if dict(b.get("Dynamic") or {}) != want[h]:
                    print(f"{rel} {h}: settings {b.get('Dynamic')} != planned {want[h]}")
                    errors += 1
                if {k: v for k, v in a.items() if k != "Dynamic"} != {k: v for k, v in b.items() if k != "Dynamic"}:
                    print(f"{rel} {h}: a field other than the settings changed")
                    errors += 1
            elif json.dumps(a, default=repr, sort_keys=True) != json.dumps(b, default=repr, sort_keys=True):
                print(f"{rel} {h} ({a.get('Gyaml')}): changed but not planned")
                errors += 1
        for k in vroot:
            if k != "Actors" and vroot[k] != proot[k]:
                print(f"{rel}: section {k} changed")
                errors += 1
    print(f"{len(by_file)} level files, {len(plan['placements'])} doorway edits read back")
    for f in sorted({e["file"] for e in plan["events"]}):
        rel = f"Event/EventFlow/{f}.bfevfl.zs"
        va = {e["name"]: e for fc in Evfl(vfs.read(rel)).flowcharts for e in fc["events"]}
        pa = {e["name"]: e for fc in Evfl(pfs.read(rel)).flowcharts for e in fc["events"]}
        changed = [n for n, e in va.items() if norm(e.get("params")) != norm(pa[n].get("params"))
                   or e.get("next") != pa[n].get("next")
                   or [c["next"] for c in e.get("cases", [])] != [c["next"] for c in pa[n].get("cases", [])]]
        print(f"{f}: steps changed {changed}, added {[n for n in pa if n not in va]}")
        for n in changed:
            a, b = norm(va[n].get("params")) or {}, norm(pa[n].get("params")) or {}
            diff = {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
            print(f"    {n}: {diff or 'routing only'}")
    print("errors:", errors)
    return errors


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(1 if main(*sys.argv[1:]) else 0)
