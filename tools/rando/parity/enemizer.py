"""Enemy randomizer (OoT3D Randomizer's Enemizer), limited to enemy types each level already places.

Remake setting remake_enemizer: "off" (default) or "on". remake_enemizer_vanilla is a list of enemy types (actor names,
e.g. "Enemy_Stalfos", default []) that keep every placement and are never put anywhere else. That's OoT3D Randomizer's
per-enemy list with its "Vanilla" choice. Data: data/rando/enemizer.json, built from the game files by
tools/rando/parity/_enemizer_build.py (the rules and the evidence for them are there).
TODO: OoT3D Randomizer's "Removed" choice isn't built, it needs per-enemy logic.

Each enemy placement (slot) the build didn't exclude gets a type, picked at random (its own type included) from the
enemy types placed anywhere in the same level:
- A slot something in the level watches (an enemy counter or shutter linking to it, a level logic module creating it)
  only takes a twin of its type: same character controller, AI graphs, damage parameters, logic node class, and
  save-data and death settings (Keese / Fire Keese, Stalfos / Weak Stalfos / child Stalfos, Iron Knuckles, Blue / Red
  Tektites, Beamos variants). The same weapons kill it and the same logic drives it, so every OoTR rule about that room
  still says exactly what the game needs.
- A free slot (nothing links to it, no logic module, no instance name, no rail, no event or item setting) is never
  needed by the logic. It can also take another type of its habitat: any flyer for a flyer, and for a walker a walker
  whose widest solid shape is no wider than the original's character controller, so no passage it left open gets
  blocked.
Every enemy type a level places keeps at least one placement there, so the level's set of types never changes. Other
features count on "a type the level already places", for example the drops plugin releases the level's own Keese type
from pots as an ice trap. The logic is unchanged, nothing about what can be reached or needed moves. The swap's random
numbers come from the seed alone (not OoTR's generator), so the item placement and spoiler are the same with the setting
on or off.
With enemy souls (extras_souls), a swapped enemy is gated on its new family's soul, and the souls' logic knows that.
swaps() gives the swaps from the seed alone, before the fill, and the souls plugin reads them there, not from the plan.

Patch: placement edits (Gyaml, with the per-placement settings the new type doesn't accept removed, as make_patch
requires). A per-placement drop table the new type's pack lacks gets removed so it drops its own.
"""
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(HERE, "data", "rando", "enemizer.json")
REMAKE_SETTINGS = {"remake_enemizer": ("off", "on"), "remake_enemizer_vanilla": None}  # (the list: check_settings)
REMAKE_DEFAULTS = {"remake_enemizer": "off", "remake_enemizer_vanilla": []}
_DATA = None


def data():
    global _DATA
    if _DATA is None:
        _DATA = json.load(open(DATA, encoding="utf-8"))
    return _DATA


def _remake(settings, key):
    return (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS[key])


def check_settings(settings):
    problems = []
    for k, ok in REMAKE_SETTINGS.items():
        v = _remake(settings, k)
        if ok is not None and v not in ok:
            problems.append(f"{k} = {v!r}: the enemizer can make {', '.join(map(repr, ok))}")
    keep = _remake(settings, "remake_enemizer_vanilla")
    if not isinstance(keep, list) or not all(isinstance(x, str) for x in keep):
        problems.append(f"remake_enemizer_vanilla = {keep!r}: a list of enemy actor names")
    else:
        unknown = sorted(set(keep) - set(data()["types"]))
        if unknown:
            problems.append(f"remake_enemizer_vanilla: {', '.join(unknown)} are no enemy types the enemizer swaps "
                            f"(data/rando/enemizer.json types)")
        elif keep and _remake(settings, "remake_enemizer") == "off":
            problems.append("remake_enemizer_vanilla is set but remake_enemizer is 'off'")
    return problems


def untested(settings):
    if _remake(settings, "remake_enemizer") == "off":
        return []
    return ["remake_enemizer on: enemy placements change type (Gyaml) to another type their level already places"]


def candidates(level, slot, keep=frozenset()):
    """The types slot `slot` of level `level` can take, its own included. Types in `keep` (remake_enemizer_vanilla)
    neither change nor spread."""
    d = data()
    types = d["types"]
    a = types.get(slot["actor"])
    if a is None or slot["skip"] or slot["actor"] in keep:
        return [slot["actor"]]
    out = set()
    for b_name in d["placed"].get(level, ()):
        b = types.get(b_name)
        if b is None or b_name in keep:
            continue
        if b["twin"] == a["twin"]:
            out.add(b_name)
        elif not slot["watched"] and not slot["rails"] and a.get("habitat") and a.get("habitat") == b.get("habitat"):
            if a["habitat"] == "flying":
                out.add(b_name)
            elif a.get("extent") and b.get("extent_max") and b["extent_max"] <= a["extent"]:
                out.add(b_name)
    out.add(slot["actor"])
    return sorted(out)


def swap_op(slot, new):
    """The placement edit turning slot `slot` into type `new`."""
    t = data()["types"][new]
    allowed = set(t["params"]) | {"DefaultDungeonRoomIndex"}
    removes = [f"Dynamic.{k}" for k in slot["keys"] if k not in allowed]
    if slot.get("drop_table") and slot["drop_table"] not in t["drop_tables"] and "Dynamic.Drop__DropTable" not in removes:
        removes.append("Dynamic.Drop__DropTable")
    return {"file": slot["file"], "hash": slot["hash"], "set": {"Gyaml": new}, "remove": removes,
            "note": f"enemizer: {slot['actor']} -> {new}"}


def plan(seed, keep=frozenset()):
    """Placement edits for seed `seed`. Every enemy type a level places keeps at least one placement there, because
    other features count on "a type the level already places" too (the drops plugin releases the level's own Keese type
    from pots as an ice trap). So if no fixed placement keeps a type, its first changeable placement stays as it is."""
    rng = random.Random(f"remake_enemizer:{seed}")
    ops = []
    for level, slots in sorted(data()["levels"].items()):
        fixed = {s["actor"] for s in slots if len(candidates(level, s, keep)) < 2}
        reserved = set()
        for i, slot in enumerate(slots):
            if slot["actor"] not in fixed:
                fixed.add(slot["actor"])
                reserved.add(i)
        for i, slot in enumerate(slots):
            if i in reserved:
                continue
            cands = candidates(level, slot, keep)
            if len(cands) < 2:
                continue
            new = rng.choice(cands)
            if new != slot["actor"]:
                ops.append(swap_op(slot, new))
    return ops


def swaps(settings):
    """{(file, hash): (slot, new type)}: this seed's swaps, exactly world_plan's ops, or {} with the enemizer off. They
    come from the seed alone, so a plugin whose logic is built before the fill has them before any plan exists
    (extras_souls, where a swapped enemy takes its new family's soul)."""
    if _remake(settings, "remake_enemizer") != "on":
        return {}
    slots = {(s["file"], s["hash"]): s for ss in data()["levels"].values() for s in ss}
    return {(op["file"], op["hash"]): (slots[(op["file"], op["hash"])], op["set"]["Gyaml"])
            for op in plan(settings.seed, frozenset(_remake(settings, "remake_enemizer_vanilla")))}


def world_plan(settings, world):
    if _remake(settings, "remake_enemizer") != "on":
        return {}
    ops = plan(settings.seed, frozenset(_remake(settings, "remake_enemizer_vanilla")))
    return {"placements": ops} if ops else {}
