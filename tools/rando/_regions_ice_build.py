"""Writes data/rando/drops_regions_x2.json, the OoTR regions for the icicles and red ice.
That's Ship of Harkinian's Shuffle Icicles / Shuffle Red Ice.

Icicles (Obj_BrokenIcePillar_A_01..A_04 stalagmites, Obj_FallingIcicle_A_01/_A_02 stalactites) get their region
from their dungeon room (Dynamic.DefaultDungeonRoomIndex) through the room table of data/rando/drops_regions_d2.json,
which the research checked by position. Red ice is the 12 blocks the research found usable, with the regions it
gave. The three round the map room's Blue Fire (scripted reveal) and King Zora's / the shop's are left out. The
boss-rush copies (DreamWorld) and the Blue Fire pedestal lid aren't locations.

usage: python tools/rando/_regions_ice_build.py [ROMFS]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load  # noqa: E402

ROMFS = sys.argv[1] if len(sys.argv) > 1 else __import__("romtools").longshot_romfs()
OUT = os.path.join(HERE, "data", "rando", "drops_regions_x2.json")
ICICLES = {"Obj_BrokenIcePillar_A_01", "Obj_BrokenIcePillar_A_02", "Obj_BrokenIcePillar_A_03",
           "Obj_BrokenIcePillar_A_04", "Obj_FallingIcicle_A_01", "Obj_FallingIcicle_A_02"}
LEVELS = {"IceCavern": ["Banc/IceCavern/IceCavern_Static.bcett.byml.zs", "Banc/IceCavern/IceCavern_Dynamic.bcett.byml.zs"],
          "InsideGanonCastle": ["Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs",
                                "Banc/InsideGanonCastle/InsideGanonCastle_Dynamic.bcett.byml.zs"]}
# Usable red ice from research table 3.2, hash -> (area, region, description).
RED_ICE = {
    "16919949776496418098": ("IceCavern", "Ice Cavern Beginning", "encases a pot (room 0)"),
    "11834825470400057740": ("IceCavern", "Ice Cavern Beginning", "encases a pot (room 1)"),
    "6768917453344093312": ("IceCavern", "Ice Cavern Beginning", "encases a pot (room 1)"),
    "6188311488374461733": ("IceCavern", "Ice Cavern Spinning Scythe Room", "wall, hub -> compass room (melted from the hub)"),
    "12214319674592646459": ("IceCavern", "Ice Cavern Spinning Scythe Room", "wall, hub -> push-block room"),
    "3200723622177405753": ("IceCavern", "Ice Cavern Map Room", "encases the Map chest"),
    "8455825898678675056": ("IceCavern", "Ice Cavern Map Room", "encases the Frozen Pot"),
    "5982607659326270053": ("IceCavern", "Ice Cavern Behind Ice Walls", "encases two pots (compass room)"),
    "12153144952635432432": ("IceCavern", "Ice Cavern Behind Ice Walls", "by the push-block room silver rupee"),
    "16134962554615344128": ("IceCavern", "Ice Cavern End", "wall to the White Wolfos room"),
    "11193391832596447117": ("InsideGanonCastle", "Ganons Castle Water Trial", "water-trial wall, room 5 -> 6"),
    "5592929323455584189": ("InsideGanonCastle", "Ganons Castle Water Trial", "over the rusty hammer switch"),
}


def main():
    fs = Romfs(ROMFS, os.path.join(HERE, "original"))
    rooms = json.load(open(os.path.join(HERE, "data", "rando", "drops_regions_d2.json"), encoding="utf-8"))
    out = {"_about": __doc__.strip().splitlines()[0] + " Written by tools/rando/_regions_ice_build.py."}
    counts = {}
    for area, files in LEVELS.items():
        table = rooms[area]["rooms"]
        objs = {}
        for rel in files:
            for a in byml_load(fs.read(rel))[0].get("Actors", []):
                if a.get("Gyaml") not in ICICLES:
                    continue
                room = (a.get("Dynamic") or {}).get("DefaultDungeonRoomIndex")
                region = table.get(str(room))
                if region is None:
                    raise SystemExit(f"{rel}: icicle {a['Hash']} in room {room}, which has no region")
                falling = a["Gyaml"].startswith("Obj_FallingIcicle")
                objs[str(a["Hash"])] = {"region": region, "rule": "True", "confidence": "high",
                                        "why": f"{'stalactite' if falling else 'stalagmite'} in room {room} "
                                               f"({rel.rsplit('/', 1)[1].split('.')[0]})"}
                counts[region] = counts.get(region, 0) + 1
        for h, (ar, region, why) in RED_ICE.items():
            if ar == area:
                objs[h] = {"region": region, "rule": "True", "confidence": "high", "why": f"red ice: {why}"}
        out[area] = {"objects": dict(sorted(objs.items()))}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"{sum(counts.values())} icicles, {len(RED_ICE)} red ice -> {os.path.relpath(OUT, HERE)}; {counts}")


if __name__ == "__main__":
    main()
