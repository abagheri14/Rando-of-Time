"""Gold Skulltulas in new positions (OoT3D Randomizer's Random GS Locations), with logic per spot.

The remake setting is remake_gs_positions. "off" is the default. "on" gives each movable skulltula a random spot
of its level, its vanilla spot included. "new" makes a movable skulltula with any free spot always leave its
vanilla spot (3DS's "guarantee new"). The data is data/rando/gs_positions.json, built by
tools/rando/parity/_gs_positions_build.py: which skulltulas can move, the spots, and why.

The spots are the remake's grass tufts that the drops plugin placed in an OoTR region with a certain or
stricter-than-the-game rule. They have to be in the skulltula's own level file (same age), and in a dungeon in
its own room. The skulltula stands on the ground there like the remake's own ground skulltulas do, with its web
under it.

Logic: the skulltula's OoTR location moves to the spot's region, with the rule
  spot rule (the drops plugin's, for reaching the tuft) and killing it on the ground:
    child level: is_child and (Slingshot or Sticks or Kokiri_Sword or has_explosives or Din's Fire or Hammer)
    adult level: is_adult; a dungeon (both ages): either.
  That's OoTR's can_child_attack without the Boomerang. Some skulltula modules can make it boomerang-proof, so
  the rule never counts on it. The token falls on the ground where it dies.
A night skulltula only moves within its own OoTR region, so OoTR's time-of-day logic stays the same, and it keeps
its own rule on top of the spot's (stricter than the game, never looser). The tokens stay as the drops plugin
handles them. The spot's random numbers come from the seed alone.
"""
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(HERE, "data", "rando", "gs_positions.json")
REMAKE_SETTINGS = {"remake_gs_positions": ("off", "on", "new")}
REMAKE_DEFAULTS = {"remake_gs_positions": "off"}
CHILD_KILL = ("(is_child and (Slingshot or Sticks or Kokiri_Sword or has_explosives or can_use(Dins_Fire) or "
              "can_use(Megaton_Hammer)))")
KILL = {"child": CHILD_KILL, "adult": "is_adult", "both": f"(is_adult or {CHILD_KILL})"}
_DATA = None
_MOVES = {}  # id(world) -> {OoTR location: spot}


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
        if v not in ok:
            problems.append(f"{k} = {v!r}: gs_positions can make {', '.join(map(repr, ok))}")
    return problems


def untested(settings):
    if _remake(settings, "remake_gs_positions") == "off":
        return []
    return ["remake_gs_positions: Gold Skulltulas (and their webs) moved onto grass tufts (Translate edits; the "
            "placements' SRTHash is left as is)"]


def _fits(gs, spot):
    return (spot["room"] == gs["room"] and (gs["age"] == spot["age"] or "both" in (gs["age"], spot["age"]))
            and (not gs["night"] or spot["region"] == gs["region"]))


def assign(seed, mode, regions=None):
    """{OoTR location: spot} for the skulltulas that move. `regions` is the OoTR region names that exist (None for
    any)."""
    rng = random.Random(f"remake_gs_positions:{seed}")
    d = data()
    taken, out = set(), {}
    for name in sorted(d["gs"]):
        gs = d["gs"][name]
        spots = [s for s in d["spots"].get(gs["level"], []) if _fits(gs, s) and (s["file"], s["hash"]) not in taken
                 and (regions is None or s["region"] in regions)]
        if not spots:
            continue
        choice = rng.choice(spots + ([None] if mode == "on" else []))
        if choice is None:
            continue
        taken.add((choice["file"], choice["hash"]))
        out[name] = choice
    return out


def rule_for(gs, spot, own_rule):
    kill = KILL[gs["age"] if gs["age"] in KILL else "both"]
    rule = f"({spot['spot_rule']}) and {kill}"
    if gs["night"]:
        rule = f"({own_rule or 'True'}) and {rule}"
    return rule


def before_fill(world, settings):
    mode = _remake(settings, "remake_gs_positions")
    _MOVES.pop(id(world), None)
    if mode == "off":
        return
    regions = {r.name for r in world.regions}
    moves = assign(settings.seed, mode, regions)
    d = data()
    for name, spot in moves.items():
        loc = world.get_location(name)
        gs = d["gs"][name]
        rule = rule_for(gs, spot, loc.rule_string)
        new_region = world.get_region(spot["region"])
        if loc.parent_region is not new_region:
            loc.parent_region.locations.remove(loc)
            new_region.locations.append(loc)
            loc.parent_region = new_region
        loc.rule_string = rule
        world.parser.parse_spot_rule(loc)
    _MOVES[id(world)] = moves


def world_plan(settings, world):
    moves = _MOVES.get(id(world))
    if not moves:
        return {}
    d = data()
    lift = d["web_drop"]
    ops, notes = [], []
    for name, spot in sorted(moves.items()):
        gs = d["gs"][name]
        x, y, z = spot["pos"]
        ops.append({"file": gs["file"], "hash": gs["hash"], "set": {"Translate": [x, y + lift, z]}, "remove": ["Rotate"],
                    "note": f"gs_positions: {name} -> {spot['id']} ({spot['region']})"})
        ops.append({"file": gs["web"]["file"], "hash": gs["web"]["hash"], "set": {"Translate": [x, y, z]},
                    "remove": ["Rotate"], "note": f"gs_positions: web of {name}"})
        notes.append(f"{name}: on the grass at {spot['pos']} ({spot['id']}, region {spot['region']})")
    return {"placements": ops, "_notes_gs_positions": notes}
