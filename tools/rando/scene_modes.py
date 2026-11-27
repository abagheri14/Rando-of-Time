"""Which scene reward locations (NPC gifts, songs, cutscenes) can give a progressive item, and how.

usage: python tools/rando/scene_modes.py ROMFS        -> data/rando/scene_give_modes.json, data/rando/pouch_actors.json

A location can take a progressive item when every give step of it can be replaced by "give the right tier"
steps (tools/progressive.py scene_give_mode: "inplace" or "host"). The seed generator reads the result so it
never puts a progressive item where the patcher can't give one.
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load, sarc_files  # noqa: E402
from evfl import Evfl  # noqa: E402
import progressive  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "scene_give_modes.json")
POUCH = os.path.join(HERE, "data", "rando", "pouch_actors.json")


def pouch_actors(fs, romfs):
    """{item actor in config/item_map.json: (pouch actor, count)}: what a chest item puts in the inventory
    (PouchContentParam PouchActor, or BundleActor x BundleActorNum for ammo and rupees), for starting items."""
    items = json.load(open(os.path.join(HERE, "config", "item_map.json"), encoding="utf-8"))["items"]
    out = {}
    for actor in sorted(set(items.values())):
        path = f"Pack/Actor/{actor}.pack.zs"
        if not os.path.exists(os.path.join(romfs, path)):
            continue
        files = sarc_files(fs.read(path))
        name = lambda ref: ref.rsplit("/", 1)[-1].split(".")[0]  # noqa: E731
        # the actor's own parameter file names its pouch parameters (PouchContentRef)
        own = byml_load(files[f"Actor/{actor}.engine__actor__ActorParam.bgyml"])[0]
        ref = ((own.get("Components") or {}).get("PouchContentRef") or "").lstrip("?")
        r = byml_load(files[ref])[0] if ref in files else {}
        if r.get("PouchActor"):
            out[actor] = [name(r["PouchActor"]), 1]
        elif r.get("BundleActor"):
            out[actor] = [name(r["BundleActor"]), r.get("BundleActorNum", 1)]
        elif ref and os.path.exists(os.path.join(romfs, "Pack", "Actor", name(ref) + ".pack.zs")):
            out[actor] = [name(ref), 1]  # e.g. Item_Sword_Kokiri's pouch entry is Weapon_Sword_Kokiri
        else:
            out[actor] = [actor, 1]
    return out


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rewards = [r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))
               if r["source"] == "event" and r.get("location")]
    cache, modes = {}, defaultdict(dict)
    for r in rewards:
        for f in r["files"]:
            if f not in cache:
                cache[f] = Evfl(fs.read(f))
            fc = next(x for x in cache[f].flowcharts if x["name"] == r["flowchart"])
            e = next(x for x in fc["events"] if x["name"] == r["event"])
            modes[r["location"]][f"{f.rsplit('/', 1)[-1]}:{r['event']}"] = progressive.scene_give_mode(fc, e, r["param"])
    out = {"_about": __doc__.strip().splitlines()[0],
           "locations": {loc: {"progressive": all(v is not None for v in steps.values()), "steps": steps}
                         for loc, steps in sorted(modes.items())}}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    json.dump({"_about": pouch_actors.__doc__.strip().splitlines()[0], "actors": pouch_actors(fs, romfs)},
              open(POUCH, "w", encoding="utf-8"), indent=1)
    ok = sum(1 for v in out["locations"].values() if v["progressive"])
    print(f"{len(out['locations'])} scene locations, {ok} can give a progressive item -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
