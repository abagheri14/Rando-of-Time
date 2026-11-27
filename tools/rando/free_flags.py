"""Saved Bool flags nothing in the game uses, for features that need a "given once" record of their own (the save
list can't grow).

The pool is the `HavePlayedNaviBalloonMessage.typeNNN` flags (GameDataList Bool, ResetTypeValue 8 so only a new
file resets it, default false) where:
- the balloon type has an empty entry in `GameParameter/NaviMgrGlobalParam/GlobalGameParameterTable`
  BalloonMessageParamList (keyed by murmur3 of "typeNNN")
- no event flow requests it (any action parameter naming the type)
- no AI file names it as a constant
- no plugin already claims it (`CLAIMED`)
The only thing in the game that writes these flags is the Navi brain, for a balloon that's actually requested, so
an unrequested type's flag stays false until a feature sets it.

usage: python tools/rando/free_flags.py        (prints the pool)
"""
import glob
import json
import os
import re
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # REMAKE_ROMFS: the app
PREFIX = "HavePlayedNaviBalloonMessage.type"
NAVI_TABLE = "GameParameter/NaviMgrGlobalParam/GlobalGameParameterTable.game__navi__NaviMgrGlobalParam.bgyml"
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"


# Drops take flags from the front of the pool and fairies from the back, and both skip flags other features hold.
# CLAIM_FILES points at each feature's fixed list under "flags_claimed" (a {name: flag} table or a list). While a
# seed is made, hold() claims just the flags the seed uses, so a feature that's off claims none. held_plan()
# records the nonempty claims under "_flags_held", and restore() uses those same claims when a built seed is
# checked. If neither hold() nor restore() has run, every listed flag stays out of the pool.

CLAIM_FILES = {"extras_npcs": "extras_npcs.json", "extras_souls": "extras_souls_data.json",
               "songs_trade": "songs_trade_slot.json",  # the trade button's owned record (tools/trade_slot.py)
               "songs_trade_masks": "songs_trade_masks.json",  # the mask button's (tools/mask_slot.py)
               "songs_trade_cows": "songs_trade_flags.json"}  # the remake-only GF Cow's give flag (shuffle_cows)
HELD = None  # {feature: flags} once a feature of the seed being made has said what it holds


def hold(feature, flags):
    """`feature` holds these flags for the seed being made (from its plugin, before the world is built)."""
    global HELD
    HELD = dict(HELD or {}, **{feature: tuple(flags)})


def held_plan(feature):
    """The plan part that records the flags `feature` holds in this seed ({} when none)."""
    flags = (HELD or {}).get(feature)
    return {"_flags_held": {feature: list(flags)}} if flags else {}


def restore(plan):
    """For a built seed's read-back. Holds what its plan records (nothing for a feature it doesn't name) and picks up
    the flags it minted (plan "_flags_minted")."""
    global HELD
    HELD = {k: tuple(v) for k, v in (plan.get("_flags_held") or {}).items()}
    MINTED[:] = list(plan.get("_flags_minted") or [])


# Minted flags
# When a seed needs more once-flags than the borrowed pool holds (every extras option and the five fairy shuffles
# want 307, the family has 271), the rest are new saved plain Bools of our own, Rando_Flag_NNN. make_patch gamedata
# "add_bools" adds them (save file 0, reset on a new file, default false). The save list does grow, that's proven
# in game with the respawn model's RandoChecked and the story plugin's RandoGreatFairy_* rows.
# They're read and written by name like any borrowed flag (event GameDataActor steps, a placement's Presence, the
# tree gate's AI), and nothing in the game knows them, so they're free by construction. We only mint for the
# overflow, in the order the plugins ask (the drops plugin's plan first, then the fairies'), so a seed that fits
# the pool is unchanged.
MINT_PREFIX = "Rando_Flag_"
MINTED = []  # this seed's minted flags in order (minted_plan writes their rows, restore reads them back)


def mint(n):
    """`n` new flags of our own (MINTED), continuing this seed's numbering."""
    out = [f"{MINT_PREFIX}{len(MINTED) + i:03d}" for i in range(n)]
    MINTED.extend(out)
    return out


def minted_plan():
    """The plan part adding this seed's minted flags ({} when none): their saved Bool rows, and the record."""
    if not MINTED:
        return {}
    return {"gamedata": [{"add_bools": {f: False for f in MINTED}}], "_flags_minted": list(MINTED)}


def is_free(flag, romfs=DEFAULT_ROMFS):
    """A flag a feature may hold: in the borrowed pool, or minted by this seed (MINTED)."""
    return flag in MINTED or flag in set(pool(romfs))


def listed(feature):
    """`feature`'s whole fixed list (CLAIM_FILES)."""
    path = os.path.join(HERE, "data", "rando", CLAIM_FILES[feature])
    if not os.path.exists(path):
        return set()
    flags = json.load(open(path, encoding="utf-8")).get("flags_claimed") or {}
    return {v for k, v in flags.items() if not k.startswith("_")} if isinstance(flags, dict) else set(flags)


def claimed(own=None):
    """Flags of this pool that other features hold, leaving out `own`'s (a feature's build script re-deriving its own
    list from the pool). While a seed is made that's what each feature said it holds, otherwise every CLAIM_FILES
    list."""
    out = set()
    for feature in CLAIM_FILES:
        if feature != own:
            out |= set(HELD.get(feature, ())) if HELD is not None else listed(feature)
    return out


def pool(romfs=DEFAULT_ROMFS, own=None):
    """The free flags in type order, leaving out the flags other features hold (but not `own`'s)."""
    taken = claimed(own)
    return tuple(f for f in unused_flags(romfs) if f not in taken)


@lru_cache(maxsize=None)
def unused_flags(romfs=DEFAULT_ROMFS):
    """Every flag of the family nothing in the game uses (see the module docstring), in type order. That's the pool
    before any feature holds one."""
    from romtools import Romfs, byml_load, murmur3_32, sarc_files
    import evfl
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    table = byml_load(fs.raw(NAVI_TABLE))[0]["BalloonMessageParamList"]
    entries = {int(k): v for k, v in table.items()}
    empty = [t for t in range(1000) if entries.get(murmur3_32(f"type{t:03d}".encode())) == ""]
    root = byml_load(fs.read(GAMEDATA), allow_big=True)[0]
    bools = {int(e["Hash"]): e for e in root["Data"]["Bool"]}
    saved = [t for t in empty if (lambda e: e is not None and e.get("ResetTypeValue") == 8
                                  and e.get("DefaultValue") is False and e.get("SaveFileIndex") == 0)(
        bools.get(murmur3_32(f"{PREFIX}{t:03d}")))]
    requested = set()
    for p in sorted(glob.glob(os.path.join(romfs, "Event", "EventFlow", "*.bfevfl.zs"))):
        rel = os.path.relpath(p, romfs).replace(os.sep, "/")
        try:
            ev = evfl.Evfl(fs.read(rel))
        except Exception:  # noqa: BLE001 - timeline-only or unreadable files request nothing
            continue
        for fc in ev.flowcharts:
            for e in fc["events"]:
                if e["type"] != "action":
                    continue
                actor = fc["actors"][e["actor"]]
                action = actor["actions"][e["action"]] if e["action"] < len(actor["actions"]) else ""
                if "NaviRequestBallon" not in str(action) and "NaviRequestBalloon" not in str(action):
                    continue  # EventNaviRequestBallonMessage uses Index for the balloon type (188 steps).
                for k, v in ((e.get("params") or {}).get("items") or {}).items():
                    val = v.get("value") if isinstance(v, dict) else None
                    if isinstance(val, int):
                        requested.add(val)
                    elif not isinstance(val, (bool, float, type(None))):
                        requested.add(-1)  # an argument: unknown type, see REQUESTED_BY_ARGUMENT
    named = set()
    for pk in [os.path.relpath(p, romfs).replace(os.sep, "/") for p in glob.glob(os.path.join(romfs, "Pack", "*.pack.zs"))]:
        try:
            files = sarc_files(fs.read(pk))
        except Exception:  # noqa: BLE001
            continue
        for f, d in files.items():
            if f.endswith(".ainb") and b"NaviBalloon" in d:
                a = ainb.Ainb(d)
                for n in a.nodes:
                    if "NaviBalloon" in n["name"] or "BalloonMessage" in n["name"]:
                        for sec in ("properties", "inputs"):
                            for e in n[sec]["int"]:
                                named.add(e["value"])
    # Logic modules request balloons by number too, with TriggerNaviRequestBallonMessage (the game's spelling,
    # "Ballon") and input Index = the type. The loop above misses them, because they sit in the loose Logic/ files and
    # because of the spelling. Types 118, 239, 241, 246, 371, 432 and 445 were in the pool even though
    # ZoraDomain_Adult_Common_1b33 (after King Zora's red ice), DodongoCavern_Level_Room_19_Prefab_6291, the Dodongo's
    # Cavern mid-boss gimmicks and InsideTheDekuTree_Level_Room_E_Prefab_e259 make Navi record them (the tools/gamedb
    # tracker audit found it).
    for sub in ("Logic", "Sequence", "AI"):
        for p in sorted(glob.glob(os.path.join(romfs, sub, "*.ainb"))):
            rel = os.path.relpath(p, romfs).replace(os.sep, "/")
            d = fs.raw(rel)
            if b"NaviRequestBallon" not in d and b"NaviRequestBalloon" not in d:
                continue
            for n in ainb.Ainb(d).nodes:
                if "NaviRequestBallon" in n["name"] or "NaviRequestBalloon" in n["name"]:
                    named.update(e["value"] for e in n["inputs"]["int"] + n["properties"]["int"]
                                 if e["name"] == "Index")
    if -1 in requested:
        raise RuntimeError("a scene requests a Navi balloon type passed as an argument: check which before borrowing")
    pool.requested = sorted(requested)
    return tuple(f"{PREFIX}{t:03d}" for t in saved if t not in requested and t not in named)


def take(n, used=(), romfs=DEFAULT_ROMFS, reverse=False):
    """`n` flags from the pool (from its end with `reverse`), skipping `used` (flags another feature of the same seed
    holds). Past the pool's end we mint new flags of our own."""
    free = [f for f in (reversed(pool(romfs)) if reverse else pool(romfs)) if f not in set(used)]
    if n > len(free):
        return free + mint(n - len(free))
    return free[:n]


if __name__ == "__main__":
    r = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROMFS
    p = pool(r)
    print(f"{len(unused_flags(r))} unused flags in the family; {len(p)} free with every claimed list held "
          f"({', '.join(f'{k} {len(listed(k))}' for k in CLAIM_FILES)}): {p[0]} .. {p[-1]}")


def verify_minted(patch, flags, romfs=DEFAULT_ROMFS):
    """Checks every minted flag (plan "_flags_minted") is a saved plain Bool row of the patched GameDataList (save file
    0, reset on a new file, default false) and that no vanilla row has its hash. Returns [problem, ...]."""
    from romtools import Romfs, byml_load, murmur3_32
    van = byml_load(Romfs(romfs, os.path.join(HERE, "original")).read(GAMEDATA), allow_big=True)[0]
    new = byml_load(Romfs(romfs, os.path.join(HERE, "original"), [patch]).read(GAMEDATA), allow_big=True)[0]
    vh = {int(e["Hash"]) for k in van["Data"] for e in (van["Data"][k] or []) if isinstance(e, dict) and "Hash" in e}
    rows = {int(e["Hash"]): e for e in new["Data"]["Bool"]}
    bad = []
    for f in flags:
        h = murmur3_32(f)
        r = rows.get(h)
        if h in vh:
            bad.append(f"minted flag {f}: its hash is a vanilla save-data row's")
        if r is None or r.get("SaveFileIndex") != 0 or r.get("ResetTypeValue") != 8 or r.get("DefaultValue") is not False:
            bad.append(f"minted flag {f}: no saved Bool row (save file 0, new-file reset, false) in {GAMEDATA}: {r}")
    return bad
