"""Which packs hold a given file (path inside a pack), read from the vanilla game files.

The game names every file inside a pack by a global path (ActorParams refer to "Work/AI/Root/X.root.ain", and
the size table has one entry per path). In the vanilla game every path that sits in several packs has the same
bytes in all of them (13,830 such paths in 8,385 packs, none differs, see tools/selftest.py step 9). That's how
a path-keyed resource cache behaves: whichever pack loads a path first supplies it to every actor. So an edited
path has to end with the same bytes in every pack that holds it. tools/make_patch.py refuses a patch that
breaks this, and plan ops may name "pack": "*" ("every pack that holds this file", expanded with carriers()).

usage: python tools/packpaths.py ROMFS PATH [PATH ...]    (lists the packs holding each path)
"""
import os
import sys
from functools import lru_cache

sys.path.insert(0, os.path.dirname(__file__))
from romtools import Romfs, sarc_files  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # REMAKE_ROMFS: the app
PACK_DIRS = ("Pack", "Pack/Actor")


CACHE = os.path.join(HERE, "cache", "packpaths_index.json")


@lru_cache(maxsize=4)
def index(romfs=DEFAULT_ROMFS):
    """{inner path: (pack rel, ...)} over every pack of the game (vanilla copies: ./original first).
    Reading all 8,385 packs takes ~1 s and generate, make_patch and in_game_check each need it, so the result is
    cached in cache/packpaths_index.json under a key of everything it comes from. That's the romfs, the file each
    pack is read from (Romfs.path, which still makes its checks here), each one's size and time, and the code of
    this file and romtools.py. Any change rebuilds it."""
    import hashlib
    import json
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    stamp = [romfs, fs.vanilla] + [hashlib.sha1(open(f, "rb").read()).hexdigest()
                                   for f in (__file__, os.path.join(os.path.dirname(__file__), "romtools.py"))]
    for sub in PACK_DIRS:
        for fn in sorted(os.listdir(os.path.join(romfs, sub))):
            if fn.endswith(".pack.zs"):
                p = fs.path(f"{sub}/{fn}")
                st = os.stat(p)
                stamp.append([f"{sub}/{fn}", p, st.st_size, st.st_mtime_ns])
    key = hashlib.sha1(json.dumps(stamp).encode()).hexdigest()
    try:
        with open(CACHE, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("key") == key:
            packs = cached["packs"]
            return {k: tuple(packs[i] for i in v) for k, v in cached["index"].items()}
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    out = _index(fs, romfs)
    tmp = f"{CACHE}.{os.getpid()}.tmp"
    try:  # written whole and then moved into place, so a tool reading it meanwhile sees the old file or the new one
        packs = sorted({p for v in out.values() for p in v})
        pos = {p: i for i, p in enumerate(packs)}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "packs": packs, "index": {k: [pos[p] for p in v] for k, v in out.items()}}, f)
        os.replace(tmp, CACHE)
    except OSError:  # a folder we can't write to, or another tool holding the file, means no cache but the same index
        try:
            os.remove(tmp)
        except OSError:
            pass
    return out


def _index(fs, romfs):
    out = {}
    for sub in PACK_DIRS:
        d = os.path.join(romfs, sub)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".pack.zs"):
                rel = f"{sub}/{fn}"
                for inner in sarc_files(fs.read(rel)):
                    out.setdefault(inner, []).append(rel)
    return {k: tuple(v) for k, v in out.items()}


def carriers(inner, romfs=DEFAULT_ROMFS):
    """Every pack (romfs-relative, sorted) that holds `inner`; empty if no pack does."""
    return index(romfs).get(inner, ())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    for p in sys.argv[2:]:
        print(p, len(carriers(p, sys.argv[1])), list(carriers(p, sys.argv[1])))
