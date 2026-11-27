"""Which placed actors have collision baked into their area's static body (Phive/StaticCompoundBody).

Each area and age has tiles `Phive/StaticCompoundBody/<Area>/<Area>_<Age>_X<x>_Z<z>.Nin_Ounce_NVN2.bphsc.zs`
(magic "Phive\\0"). The u32 at 0x10 is where its actor table starts and the u32 at 0x14 where it ends (the next
section). The table holds 32-byte records {u32 shape_start, u32 shape_end, u64 placement ID, u64, u64},
and shape_start 0xFFFFFFFF means no baked shapes. In vanilla every placed actor's `Phive.Placement.ID` equals its Hash
(120,598 of 120,598) and every one is listed in a tile of its area. Each type is baked in all of its placements or
in none.

Baked collision is found by placement ID, so a copy of a placement under a new ID (the respawn model's vanilla twin)
has no entry. OotrR saw this in game with a tree's copy that had no collision (their issue #37). drops.BAKED_TYPES
lists the twinnable types that are baked, and their twins keep their source's ID (make_patch "keep_phive_id").

  python tools/phive_static.py --check [ROMFS]   compare drops.BAKED_TYPES with the game data
  python tools/phive_static.py TYPE... [ROMFS]   how many placements of each type are baked
"""
import glob
import os
import struct
import sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = __import__("romtools").longshot_romfs()
NO_SHAPE = 0xFFFFFFFF


def actor_table(raw):
    """{placement ID: (shape_start, shape_end)} of one decompressed bphsc tile."""
    if raw[:6] != b"Phive\0":
        raise ValueError("not a Phive static compound")
    start, end = struct.unpack_from("<II", raw, 0x10)
    if (end - start) % 32:
        raise ValueError(f"actor table {start:#x}..{end:#x} is not whole 32-byte records")
    return {pid: (a, b) for a, b, pid in (struct.unpack_from("<IIQ", raw, o) for o in range(start, end, 32))}


def baked_ids(romfs=DEFAULT_ROMFS, areas=None):
    """{placement ID: True if it has baked shapes} over every tile (or those of the named area folders)."""
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = {}
    for f in sorted(glob.glob(os.path.join(romfs, "Phive", "StaticCompoundBody", "*", "*.bphsc.zs"))):
        rel = os.path.relpath(f, romfs).replace("\\", "/")
        if areas and rel.split("/")[2] not in areas:
            continue
        for pid, (a, _) in actor_table(fs.read(rel)).items():
            out[pid] = out.get(pid, False) or a != NO_SHAPE
    return out


def type_counts(types, romfs=DEFAULT_ROMFS):
    """{type: Counter(baked=, not_baked=, not_listed=, no_id=)} over every vanilla level file."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    ids = baked_ids(romfs)
    out = {t: Counter() for t in types}
    for f in sorted(glob.glob(os.path.join(romfs, "Banc", "*", "*.bcett.byml.zs"))):
        rel = os.path.relpath(f, romfs).replace("\\", "/")
        try:
            actors = byml_load(fs.read(rel))[0].get("Actors", [])
        except Exception:  # noqa: BLE001 - not a level file
            continue
        for a in actors:
            if a.get("Gyaml") not in out:
                continue
            pid = ((a.get("Phive") or {}).get("Placement") or {}).get("ID")
            key = "no_id" if pid is None else ("not_listed" if int(pid) not in ids else
                                               "baked" if ids[int(pid)] else "not_baked")
            out[a["Gyaml"]][key] += 1
    return out


def check(romfs=DEFAULT_ROMFS):
    """Returns [problem, ...]. Checks that every type the drops code can twin is in drops.BAKED_TYPES exactly when
    it's baked."""
    sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
    import drops
    types = sorted(set(drops.PICKUP_SAVE_DROPPERS) | set(drops.RESPAWN_DROPPERS) | set(drops.FLAGLESS_DROPPERS)
                   | set(drops.BAKED_TYPES))
    bad = []
    for t, c in type_counts(types, romfs).items():
        if not c:
            bad.append(f"{t}: no placements")
        elif c["baked"] and (c["not_baked"] or c["not_listed"] or c["no_id"]):
            bad.append(f"{t}: baked in some placements only {dict(c)}")
        elif bool(c["baked"]) != (t in drops.BAKED_TYPES):
            bad.append(f"{t}: {'baked' if c['baked'] else 'not baked'} {dict(c)}, but "
                       f"{'not ' if t not in drops.BAKED_TYPES else ''}in drops.BAKED_TYPES")
    return bad


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rom = next((a for a in args if os.path.isdir(a)), DEFAULT_ROMFS)
    if "--check" in sys.argv:
        problems = check(rom)
        print("\n".join(problems) or "drops.BAKED_TYPES matches the game data")
        sys.exit(1 if problems else 0)
    for t, c in type_counts([a for a in args if a != rom], rom).items():
        print(f"{t:45s} {dict(c)}")
