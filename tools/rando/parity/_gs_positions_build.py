"""Builds data/rando/gs_positions.json, the Gold Skulltulas that can move and the spots they can move to.

usage: python tools/rando/parity/_gs_positions_build.py ROMFS

Reads the level files (vanilla copies in original/ first) and data/rando/drop_map.json, which is the drops plugin's
pairing of OoTR's Gold Skulltula locations with placements, plus its regions for the remake's own grass.
In short:

- A Gold Skulltula can move when the drops plugin pairs it with one OoTR location for certain ("full"), it's one
  placement, and it's a plain one. Plain means it's shown all day or at night by its own small logic module
  (Gimmick_AllDay_Skulltula / Gimmick_Nighttime_Skulltula_Gold_Appear, which only tie it to its spider web), it's
  not in soil, a tree, a crate or a room script, and nothing links to it. Its web (Land_SkulltulaGold_SpiderWeb_A_01,
  in the same module) moves with it.
- Spots are the remake's cuttable grass tufts that the drops plugin placed in an OoTR region with a "high" or
  "medium" rule (certain, or stricter than the game). A tuft isn't solid and stands on ground the player walks on (he
  cuts it there), so a skulltula standing there is reachable exactly when the tuft is. We can't read the level
  collision (Havok), so no other ground point is proven, and wall spots would need it.
- Placing on the ground copies the remake's own ground skulltulas (Forest Temple, Desert Colossus, Spirit Temple):
  no rotation, and the web 0.3 below the skulltula.
- It stays in the same level file as the skulltula (so the same age), and inside a dungeon in the same room
  (DefaultDungeonRoomIndex).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "gs_positions.json")
PLAIN_MODULES = ("Gimmick_AllDay_Skulltula", "Gimmick_Nighttime_Skulltula_Gold_Appear")
WEB = "Land_SkulltulaGold_SpiderWeb_A_01"
WEB_DROP = 0.3  # the remake's ground skulltulas stand 0.298-0.302 above their web (3 vanilla placements)
SPOT_CONFIDENCE = ("high", "medium")


def level_of(rel):
    return re.sub(r"_(Static|Dynamic)$", "", rel.split("/")[-1].replace(".bcett.byml.zs", ""))


def module_name(logic):
    return re.sub(r"_[0-9a-f]{4}\.logic\.module\.ain$", "", logic.split("/")[-1])


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    dm = json.load(open(os.path.join(HERE, "data", "rando", "drop_map.json"), encoding="utf-8"))
    files = sorted({p["file"] for sec in ("drops", "new") for e in dm[sec].values() for p in e.get("placements", [])})
    actors, groups, linked = {}, {}, set()
    for rel in files:
        root, _ = byml_load(fs.read(rel))
        for a in (root or {}).get("Actors") or []:
            actors[(rel, str(a.get("Hash")))] = a
            for link in a.get("Links") or []:
                linked.add(str(link.get("Dst")))
                linked.add(str(a.get("Hash")))
        for g in (root or {}).get("AiGroups") or []:
            refs = [str(r.get("Reference")) for r in g.get("References") or []]
            for h in refs:
                groups.setdefault((rel, h), []).append((module_name(g["Logic"]), rel, refs))
    gs, skipped = {}, {}
    for name, e in sorted(dm["drops"].items()):
        ps = [p for p in e.get("placements", []) if p.get("category") == "gold_skulltula"]
        if not ps:
            continue
        why = None
        if e.get("mode") != "full":
            why = f"pairing {e.get('mode')} (which OoTR location is which placement is unknown)"
        elif len(ps) != 1:
            why = "more than one placement (child and adult copies)"
        p = ps[0]
        a = actors.get((p["file"], p["hash"])) or {}
        d = a.get("Dynamic") or {}
        mods = groups.get((p["file"], p["hash"]), [])
        if why is None:
            if d.get("Enemy_Skulltula_Gold_IsMagicBeanSoil"):
                why = "in a bean patch"
            elif d.get("Enemy_Skulltula_Gold_AppearPopOut"):
                why = "pops out of something (tree, crate, soil)"
            elif p["hash"] in linked:
                why = "linked to other actors"
            elif len(mods) != 1 or mods[0][0] not in PLAIN_MODULES:
                why = "driven by " + ",".join(sorted({m[0] for m in mods})) or "no logic module"
        if why:
            skipped[name] = why
            continue
        _, mod_file, refs = mods[0]
        webs = [(mod_file, h) for h in refs if (actors.get((mod_file, h)) or {}).get("Gyaml") == WEB]
        if len(webs) != 1:
            skipped[name] = f"{len(webs)} webs in its module"
            continue
        gs[name] = {"file": p["file"], "hash": p["hash"], "level": level_of(p["file"]), "age": p.get("age"),
                    "room": d.get("DefaultDungeonRoomIndex"), "night": bool(d.get("Enemy_Skulltula_Gold_Nocturnal")),
                    "region": e.get("region"), "rule": e.get("rule"), "pos": [round(x, 3) for x in a["Translate"]],
                    "web": {"file": webs[0][0], "hash": webs[0][1]}}
    spots = {}
    for name, e in sorted(dm["new"].items()):
        if e.get("type") != "RemakeGrass" or e.get("confidence") not in SPOT_CONFIDENCE:
            continue
        for p in e.get("placements", []):
            a = actors.get((p["file"], p["hash"])) or {}
            if not a.get("Translate"):
                continue
            spots.setdefault(level_of(p["file"]), []).append({
                "id": name, "file": p["file"], "hash": p["hash"], "age": p.get("age"),
                "room": (a.get("Dynamic") or {}).get("DefaultDungeonRoomIndex"), "region": e["region"],
                "spot_rule": e.get("spot_rule") or "True", "confidence": e["confidence"],
                "pos": [round(x, 3) for x in a["Translate"]]})
    out = {"_about": "Generated by tools/rando/parity/_gs_positions_build.py from the level files and data/rando/"
                     "drop_map.json. gs: Gold Skulltulas that can move (OoTR location -> placement, web, room, night, "
                     "OoTR region). skipped: the others and why. spots: grass tufts per level with the drops "
                     "plugin's region and spot rule (high/medium).",
           "web_drop": WEB_DROP, "gs": gs, "skipped": skipped, "spots": spots}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(gs)} movable Gold Skulltulas, {len(skipped)} kept, {sum(len(v) for v in spots.values())} grass spots "
          f"in {len(spots)} levels -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
