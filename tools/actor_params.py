"""Which per-placement settings ("Dynamic" keys in level files) each actor accepts.

If a level file gives an actor a setting it doesn't declare, the game stops loading the rest of that level's
objects. A Drop__CheckActor on a small chest made Kokiri Forest's houses vanish, for example.

An actor accepts a setting if its actor pack declares it as an instance parameter in a blackboard
table, or if vanilla level files already use it on that actor.

usage: python tools/actor_params.py ROMFS ACTOR [ACTOR ...]
"""
import json
import os
import sys
from functools import lru_cache

sys.path.insert(0, os.path.dirname(__file__))
from romtools import Romfs, byml_load, sarc_files  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, "data", "vanilla_dynamic_keys.json")


class ActorParams:
    def __init__(self, romfs):
        self.romfs = romfs
        self.fs = Romfs(romfs, os.path.join(HERE, "original"))
        self._vanilla = None

    @lru_cache(maxsize=None)
    def declared(self, actor):
        path = f"Pack/Actor/{actor}.pack.zs"
        if not os.path.exists(os.path.join(self.romfs, path)):
            return frozenset()
        keys = set()
        for name, blob in sarc_files(self.fs.read(path)).items():
            if "BlackboardParamTable" in name and blob[:2] == b"YB":
                root, _ = byml_load(blob)
                for arr in (root or {}).values():
                    if isinstance(arr, list):
                        for p in arr:
                            if isinstance(p, dict) and p.get("IsInstanceParam") and "BBKey" in p:
                                keys.add(p["BBKey"])
        return frozenset(keys)

    def vanilla(self):
        """Dynamic keys used on each actor in vanilla level files (cached in data/)."""
        if self._vanilla is None:
            if os.path.exists(CACHE):
                self._vanilla = {k: set(v) for k, v in json.load(open(CACHE, encoding="utf-8")).items()}
            else:
                seen = {}
                banc = os.path.join(self.romfs, "Banc")
                for area in os.listdir(banc):
                    p = os.path.join(banc, area)
                    if not os.path.isdir(p):
                        continue
                    for fn in os.listdir(p):
                        if fn.endswith(".bcett.byml.zs"):
                            root, _ = byml_load(self.fs.read(f"Banc/{area}/{fn}"))
                            for a in (root or {}).get("Actors", []) or []:
                                seen.setdefault(a.get("Gyaml", ""), set()).update((a.get("Dynamic") or {}).keys())
                os.makedirs(os.path.dirname(CACHE), exist_ok=True)
                json.dump({k: sorted(v) for k, v in seen.items()}, open(CACHE, "w", encoding="utf-8"), indent=0)
                self._vanilla = seen
        return self._vanilla

    # Engine-level placement keys that any actor accepts. DefaultDungeonRoomIndex (dungeon room membership) is
    # used on 532 unrelated actor types in vanilla, from objects and enemies to terrain, NPCs and invisible walls.
    UNIVERSAL = {"DefaultDungeonRoomIndex"}

    planned = {}  # {actor: {key}} of instance parameters the patch being built adds (make_patch sets it)

    def allowed(self, actor):
        return (set(self.declared(actor)) | self.vanilla().get(actor, set()) | self.UNIVERSAL
                | set(self.planned.get(actor, ())))


if __name__ == "__main__":
    ap = ActorParams(sys.argv[1])
    for a in sys.argv[2:]:
        print(f"{a}: declared {sorted(ap.declared(a))}")
        print(f"{' ' * len(a)}  used in vanilla {sorted(ap.vanilla().get(a, []))}")
