"""data/vanilla_sha256.json holds the vanilla SHA-256 of every game file a seed may change (hashes only, no game
content).

That's each file any built patch under out/ wrote, plus the size table and text, read as vanilla (./original copies
win over the live romfs). romtools.Romfs checks a live file against it before reading it as vanilla, so a game
folder that already holds another seed (a randomizer folder that lost its install record) or another game version
gets refused instead of patched on top of.

  python tools/release/vanilla_hashes.py [ROMFS]
"""
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
OUT = os.path.join(HERE, "data", "vanilla_sha256.json")


def main(romfs=None):
    from romtools import Romfs
    romfs = romfs or os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rels = set()
    for pd in glob.glob(os.path.join(HERE, "out", "*", "patch")):
        for root, _, files in os.walk(pd):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), pd).replace(os.sep, "/")
                if rel != "patch_report.json":
                    rels.add(rel)
    out = {}
    for rel in sorted(rels):
        p = fs.path(rel)
        if os.path.exists(p):  # files a patch adds aren't the game's
            out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    json.dump({"_about": __doc__.split("\n\n")[0], "files": out}, open(OUT, "w", encoding="utf-8"), indent=0,
              sort_keys=True)
    print(f"{OUT}: {len(out)} files")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
