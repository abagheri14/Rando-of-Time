"""The fishing pond owner's prize checks (MiniGame_Fishing), shared by remake_fishing_any_fish (extras_qol) and OoTR's
shuffle_loach_reward 'easy' (songs_trade).

How he decides, when you hand him a fish:
- Event226: a kept loach (MiniGame_Fishing_KeepLoach) goes to the loach's own path (Event346, a purple rupee, or the
  loach's shuffled item), anything else to the size checks.
- The size checks compare MiniGame_Fishing_KeepFishSize with 40 (Event581), 50 (Event489) and 60 (Event585).
  EventQueryIsGameDataInt answers 0 below, 1 equal, 2 above.
- Before each prize, Event59 and Event412 ask MiniGame_Fishing_UseSinkingLure: a fish caught with it gets his "that's
  against the rules" talk (Event494 / Event507) instead of the prize talk (Event135 / Event277, Talk_145).
any_fish: every size check compares with 0, the sinking lure doesn't matter, and a kept loach is weighed like a
fish (only when the loach's reward isn't shuffled, since that path gives it). OoTR's 'easy' loach gives the prizes
with the sinking lure too, which is the lure part alone. The size record and the texts stay as they are.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FILE = "MiniGame_Fishing"
SIZES = {"Event581": 40, "Event489": 50, "Event585": 60}
LURES = {"Event59": ("Event494", "Event135"), "Event412": ("Event507", "Event277")}  # (rule talk, prize talk)
LOACH = ("Event226", "Event346", "Event581")  # (the check, the loach's path, the first size check)
YES, NO = 0, 1


def ops(sizes=True, lure=True, loach=True):
    out = []
    if sizes:
        out += [{"file": FILE, "flowchart": FILE, "event": e, "param": "Value", "value": 0} for e in SIZES]
    if lure:
        out += [{"file": FILE, "flowchart": FILE, "event": e, "case": YES, "next": prize}
                for e, (_, prize) in LURES.items()]
    if loach:
        out.append({"file": FILE, "flowchart": FILE, "event": LOACH[0], "case": YES, "next": LOACH[2]})
    return out


def readback(sizes=True, lure=True, loach=True):
    return {"sizes": sorted(SIZES) if sizes else [], "lure": sorted(LURES) if lure else [], "loach": loach}


def _flow(fs, romfs):
    import sys
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from evfl import Evfl
    from parity._story_build import newest
    rel, versions = newest(romfs, FILE)
    return rel, versions, next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == FILE)


def _cases(fc, e):
    return {c["value"]: fc["events"][c["next"]]["name"] for c in e.get("cases") or []}


def check_sources(romfs):
    """[problem] where the vanilla fishing scene isn't as this module expects."""
    from romtools import Romfs
    from parity._story_build import flat
    rel, versions, fc = _flow(Romfs(romfs, os.path.join(HERE, "original")), romfs)
    by = {e["name"]: e for e in fc["events"]}
    bad = [] if len(versions) == 1 else [f"{FILE}: {versions}: one version expected"]
    for e, v in SIZES.items():
        p = flat(by[e].get("params"), {})
        if p.get("GameDataName") != "MiniGame_Fishing_KeepFishSize" or p.get("Value") != v:
            bad.append(f"{rel}: {e} doesn't compare the fish with {v}")
    for e, (rule, prize) in LURES.items():
        if _cases(fc, by[e]) != {YES: rule, NO: prize}:
            bad.append(f"{rel}: {e} no longer picks {rule} / {prize}")
    if _cases(fc, by[LOACH[0]]) != {YES: LOACH[1], NO: LOACH[2]}:
        bad.append(f"{rel}: {LOACH[0]} no longer sends a loach to {LOACH[1]}")
    return bad


def verify(patch, rb, romfs):
    """Reads the planned fishing edits back from a built patch."""
    from romtools import Romfs
    from parity._story_build import flat
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    rel, _, fc = _flow(fs, romfs)
    if not os.path.exists(os.path.join(patch, rel)):
        return [f"fishing: {rel} not in the patch"]
    by = {e["name"]: e for e in fc["events"]}
    bad = [f"fishing: {e} compares with {flat(by[e].get('params'), {}).get('Value')}, not 0" for e in rb["sizes"]
           if flat(by[e].get("params"), {}).get("Value") != 0]
    bad += [f"fishing: {e} still has the sinking lure's rule talk" for e in rb["lure"]
            if _cases(fc, by[e]).get(YES) != LURES[e][1]]
    if rb["loach"] and _cases(fc, by[LOACH[0]]).get(YES) != LOACH[2]:
        bad.append(f"fishing: {LOACH[0]} doesn't weigh a loach like a fish")
    return bad
