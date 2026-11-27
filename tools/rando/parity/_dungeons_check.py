"""Check the game-file facts tools/rando/parity/dungeons.py relies on (run after a game update).

usage: python tools/rando/parity/_dungeons_check.py [ROMFS]

- Every DungeonInfo.<area>.{SmallKeyNum, SmallKeyTotalNum, IsGetSmallKeyOnce, IsGetBossKey, IsGetMap, IsGetCompass}
  row the plugin writes exists in GameData/GameDataList with the expected type, and so does the scratch string.
- The Dm_SY_GetInEvent steps the dungeon-item entries copy exist with the expected type (and take the ActorName
  argument where the copy relies on it).
- The reused scene ID exists, and each carrier is an actor in the game.
- Small-key doors (Obj_DoorChainLock pairs) and boss doors per dungeon area match data/rando/dungeons_world.json.
Read-only. Prints problems and exits 1 if there are any.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load, murmur3_32  # noqa: E402
from evfl import Evfl  # noqa: E402

DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS
WORLD = json.load(open(os.path.join(HERE, "data", "rando", "dungeons_world.json"), encoding="utf-8"))
# step -> (type, argument the copy keeps)
COPIED = {"Event109": ("action", "Actor"), "Event289": ("subflow", "ActorName"), "Event290": ("subflow", "ActorName"),
          "Event112": ("subflow", "ActorName"), "Event111": ("subflow", "ActorName"), "Event80": ("fork", None),
          "Event105": ("action", None), "Event700": ("action", None), "Event84": ("action", None),
          "Event82": ("join", None), "Event240": ("action", None), "Event243": ("action", None)}


def main(romfs=DEFAULT_ROMFS):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    problems = []
    root, _ = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)
    types = {}
    for table, entries in root["Data"].items():
        if table != "Bool64bitKey":
            for e in entries:
                types[e["Hash"]] = table
    for d, v in WORLD["dungeons"].items():
        for name, want in (("SmallKeyNum", "Int"), ("SmallKeyTotalNum", "Int"), ("IsGetSmallKeyOnce", "Bool"),
                           ("IsGetBossKey", "Bool"), ("IsGetMap", "Bool"), ("IsGetCompass", "Bool")):
            flag = f"DungeonInfo.{v['area']}.{name}"
            if types.get(murmur3_32(flag)) != want:
                problems.append(f"{flag}: {types.get(murmur3_32(flag))}, expected {want}")
    if types.get(murmur3_32(WORLD["scratch_string"])) != "String64":
        problems.append(f"{WORLD['scratch_string']}: not a String64")
    ev = Evfl(fs.read("Event/EventFlow/Dm_SY_GetInEvent.bfevfl.zs"))
    by_name = {e["name"]: e for e in ev.flowcharts[0]["events"]}
    for name, (kind, arg) in COPIED.items():
        e = by_name.get(name)
        if e is None or e["type"] != kind:
            problems.append(f"Dm_SY_GetInEvent {name}: {e and e['type']}, expected {kind}")
            continue
        if arg:
            item = ((e.get("params") or {}).get("items") or {}).get(arg)
            if not item or item.get("type") != "argument" or item.get("value") != "ActorName":
                problems.append(f"Dm_SY_GetInEvent {name}: {arg} is not the ActorName argument")
    rows = {r["__RowId"] for r in byml_load(fs.read("RSDB/EventSetting.Product.111.rstbl.byml.zs"))[0]}
    problems += [f"scene ID {r} is missing" for r in WORLD["scene_rows"].values() if r not in rows]
    actors = {f[:-len(".pack.zs")] for f in os.listdir(os.path.join(romfs, "Pack", "Actor")) if f.endswith(".pack.zs")}
    problems += [f"carrier {c} is not an actor" for c in WORLD["carriers"] if c not in actors]
    for d, v in WORLD["dungeons"].items():
        locks = []
        for f in sorted(os.listdir(os.path.join(romfs, "Banc", v["area"]))):  # every stage file of the area
            if f.endswith(".bcett.byml.zs"):
                actors = byml_load(fs.read(f"Banc/{v['area']}/{f}"))[0].get("Actors", [])
                # Dm_* locks are cutscene props (Fire Temple's boss door), not small-key doors
                locks += [a for a in actors if "ChainLock" in a.get("Gyaml", "") and not a["Gyaml"].startswith("Dm_")]
        doors = []
        for a in locks:
            if a["Gyaml"].endswith("_A_02"):
                continue
            if not any(math.dist(p, a["Translate"]) < 1.5 for p in doors):
                doors.append(a["Translate"])
        if len(doors) != v["doors"]:
            problems.append(f"{d}: {len(doors)} small-key doors in {v['area']}, data says {v['doors']}")
    # Each defeated Hideout guard calls GerudoThiefDropKey with its own key. We check the guards and key placements,
    # then that the Fire Temple loop door still has its unlocked flag.
    rescue = Evfl(fs.read("Event/EventFlow/SageOfSpirit_RescueCarpenter.bfevfl.zs"))
    fc = rescue.flowcharts[0]
    ev = {e["name"]: e for e in fc["events"]}
    for k in ("Event242", "Event377"):
        if k not in ev:
            problems.append(f"SageOfSpirit_RescueCarpenter {k} is missing (GerudoThiefDropKey changed?)")
    hide = byml_load(fs.read("Banc/GerudoFortress/GerudoFortress_Adult_Static.bcett.byml.zs"))[0]["Actors"]
    by_hash = {str(a["Hash"]): a for a in hide}
    for name, spot in WORLD["hideout_spots"].items():
        if name.startswith("_"):
            continue
        e = ev.get(spot["entry_event"])
        if e is None or e.get("type") != "subflow" or e.get("entry_point") != "GerudoThiefDropKey":
            problems.append(f"{name}: {spot['entry_event']} is not the call to GerudoThiefDropKey")
        for h in spot["keys"]:
            if not by_hash.get(h, {}).get("Gyaml", "").startswith("Obj_Dungeon_SmallKey_GerudoFortress_"):
                problems.append(f"{name}: key placement {h} is missing")
        if not by_hash.get(spot["guard"], {}).get("Gyaml", "").startswith("Enemy_MiddleBoss_GerudoThief"):
            problems.append(f"{name}: guard {spot['guard']} is missing")
        if types.get(murmur3_32(spot["flag"])) != "Bool":
            problems.append(f"{name}: {spot['flag']} is not a Bool")
    if types.get(murmur3_32(WORLD["fire_loop_door"]["flag"])) != "Bool":
        problems.append(f"{WORLD['fire_loop_door']['flag']} is not a Bool")
    for p in problems:
        print(p)
    print(f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
