"""List every check-like actor (chests, Gold Skulltulas, heart pieces, scrubs, cows) in the remake.

usage: python tools/survey.py ROMFS_DIR OUT.json
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from romtools import Zs, byml_load  # noqa: E402

CHECKY = re.compile(r"TBox|Skulltula_Gold|HeartPiece|Heart_Container|Scrub_Business|Animal_Cow", re.I)


def main(romfs, out_path):
    zs = Zs(os.path.join(romfs, "Pack", "ZsDic.pack.zs"))
    banc = os.path.join(romfs, "Banc")
    rows = []
    for area in sorted(os.listdir(banc)):
        p = os.path.join(banc, area)
        if not os.path.isdir(p) or area in ("BancBasedResource", "GameBancParam"):
            continue
        for fn in sorted(os.listdir(p)):
            if not fn.endswith(".bcett.byml.zs"):
                continue
            root, _ = byml_load(zs.decompress(open(os.path.join(p, fn), "rb").read()))
            for a in (root or {}).get("Actors", []) or []:
                g = a.get("Gyaml", "")
                dyn = a.get("Dynamic") or {}
                if g.startswith(("DropKeepAway", "Land_")) or "Pedestal" in g:
                    continue
                if dyn.get("Drop__DropActor") or CHECKY.search(g):
                    rows.append({
                        "area": area,
                        "file": f"Banc/{area}/{fn}",
                        "gyaml": g,
                        "hash": str(a.get("Hash")),
                        "dynamic": dyn,
                        "pos": [round(x, 1) for x in a.get("Translate", [0, 0, 0])],
                    })
    json.dump(rows, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    print(f"{len(rows)} entries -> {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
