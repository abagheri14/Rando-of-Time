"""The big-chest cinematic the dungeon-item scene copies (helper of tools/rando/parity/dungeons.py).

usage: python tools/rando/parity/_dungeons_scenes.py [ROMFS]
       writes data/rando/dungeons_scenes.json, so seed generation needs no game files

Same idea as the progressive big-chest scene (tools/progressive.py big_chest_graphs). It's the big chest's whole
vanilla cinematic (Dm_SY_Treasurebox Success_PlayerPerform from Event37: camera, Link's lift, the lid through
Process_Treasurebox from Event14, the suspense wait, rumbles, Navi) copied step for step. The one exception is the
step that shows the chest's own contents (Event9, call :Item_Rotation), which becomes the label "get" (the
dungeon-item branch).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs  # noqa: E402
from evfl import Evfl  # noqa: E402
import progressive  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "dungeons_scenes.json")
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS
BIG_FILE = "Dm_SY_Treasurebox"


def build(romfs=DEFAULT_ROMFS):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    d = os.path.join(romfs, "Event", "EventFlow")
    files = sorted(f for f in os.listdir(d) if f.startswith(BIG_FILE + ".") and f.endswith(".bfevfl.zs"))
    out = {"_about": __doc__.strip().splitlines()[0] + " (made by tools/rando/parity/_dungeons_scenes.py)",
           "file": BIG_FILE, "big": None}
    for f in files:  # every version the patcher edits must have the same steps
        fc = Evfl(fs.read(f"Event/EventFlow/{f}")).flowcharts[0]
        proc, proc_start = progressive.clone(fc, "Event14", "p_", {"Event9": "get"})
        pp, pp_start = progressive.clone(fc, "Event37", "pp_", {"Event28": proc_start, "Event5": proc_start})
        nodes = dict(pp)
        nodes.update(proc)
        big = {"nodes": nodes, "start": pp_start, "stop": "get", "wait90": "Event45"}
        if out["big"] is not None and out["big"] != big:
            raise SystemExit(f"{f}: the big-chest cinematic differs between versions")
        out["big"] = big
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"wrote {OUT}: {len(out['big']['nodes'])} copied steps from {', '.join(files)}")


if __name__ == "__main__":
    build(*sys.argv[1:])
