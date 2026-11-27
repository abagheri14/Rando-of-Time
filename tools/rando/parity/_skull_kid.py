"""The Skull Kids' ocarina game in the Lost Woods, shortened (remake_faster_skull_kid, OOTRR's faster ocarina game).

In the game (Npc_SkullKid_Child_02) you play rallies of 6 notes, then 7, then 8
(Minigame_SkullKidSession_CurrentGradeSoundNumForSession), MaxRallyCount rallies each, with blue and red rupees
along the way, and the heart piece once you clear the 8-note game (Event10 asks whether the grade is 8: below goes
on to the next grade, Event243).
Here it's one turn of 6 notes and winning it gives the prize:
- a new file and every session start (SessionStart) set the grade to 6 and MaxRallyCount to 1 (the session's own
  two MaxRallyCount writes, Event126 and Event127, say 1 too)
- the example step (Event143) builds the 6 notes at once, the way it builds the 8-note game (its 8 case, Event142,
  adds the notes in one go)
- clearing a game below 8 notes goes the heart piece's way (Event68) instead of up a grade
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FILE = "Npc_SkullKid_Child_02"
GRADE, RALLY = "Minigame_SkullKidSession_CurrentGradeSoundNumForSession", "Minigame_SkullKidSession_MaxRallyCount"
NOTES, TURNS = 6, 1
CLEAR = ("Event10", 0, "Event243", "Event68")  # (step, the below-8 case, its vanilla target, the prize's way)
PREP = ("Event143", NOTES, "Event158", "Event142")  # (step, the 6-note case, vanilla, the 8-note way)
RALLY_SETS = ("Event126", "Event127")
START = ("SessionStart", "Event137")
ENTRY = "Rando_SkullKidOneTurn"


def _set_int(name, value, nxt):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
            "params": {"GameDataName": name, "Index": -1, "Value": value}, "next": nxt}


def ops():
    out = [{"file": FILE, "flowchart": FILE, "event": CLEAR[0], "case": CLEAR[1], "next": CLEAR[3]},
           {"file": FILE, "flowchart": FILE, "event": PREP[0], "case": PREP[1], "next": PREP[3]}]
    out += [{"file": FILE, "flowchart": FILE, "event": e, "param": "Value", "value": TURNS} for e in RALLY_SETS]
    out.append({"file": FILE, "flowchart": FILE, "add_graph": ENTRY, "start": "notes",
                "nodes": {"notes": _set_int(GRADE, NOTES, "turns"), "turns": _set_int(RALLY, TURNS, f"@{START[1]}")}})
    out.append({"file": FILE, "flowchart": FILE, "entry": START[0], "next": f"{ENTRY}_notes"})
    return out


def defaults():
    return {GRADE: NOTES, RALLY: TURNS}


def _flow(fs, romfs):
    import sys
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from evfl import Evfl
    from parity._story_build import newest
    rel, versions = newest(romfs, FILE)
    return rel, versions, next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == FILE)


def _case(fc, e, v):
    return next((fc["events"][c["next"]]["name"] for c in e.get("cases") or [] if c["value"] == v), None)


def check_sources(romfs):
    """[problem] where the vanilla scene isn't as this module expects."""
    from romtools import Romfs
    from parity._story_build import flat
    rel, versions, fc = _flow(Romfs(romfs, os.path.join(HERE, "original")), romfs)
    by = {e["name"]: e for e in fc["events"]}
    bad = [] if len(versions) == 1 else [f"{FILE}: {versions}: one version expected"]
    if flat(by[CLEAR[0]].get("params"), {}).get("Value") != 8 or _case(fc, by[CLEAR[0]], CLEAR[1]) != CLEAR[2]:
        bad.append(f"{rel}: {CLEAR[0]} no longer asks for the 8-note game")
    if _case(fc, by[PREP[0]], PREP[1]) != PREP[2] or _case(fc, by[PREP[0]], 8) != PREP[3]:
        bad.append(f"{rel}: {PREP[0]} no longer builds the notes by grade")
    for e in RALLY_SETS:
        if flat(by[e].get("params"), {}).get("GameDataName") != RALLY:
            bad.append(f"{rel}: {e} doesn't set {RALLY}")
    if fc["events"][fc["entry_points"][START[0]]["main"]]["name"] != START[1]:
        bad.append(f"{rel}: {START[0]} no longer starts at {START[1]}")
    return bad


def verify(patch, romfs):
    """Reads the shortened game back from a built patch."""
    from romtools import Romfs
    from parity._story_build import flat
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    rel, _, fc = _flow(fs, romfs)
    if not os.path.exists(os.path.join(patch, rel)):
        return [f"skull kids: {rel} not in the patch"]
    by = {e["name"]: e for e in fc["events"]}
    bad = []
    if _case(fc, by[CLEAR[0]], CLEAR[1]) != CLEAR[3]:
        bad.append(f"skull kids: {CLEAR[0]} doesn't give the prize below 8 notes")
    if _case(fc, by[PREP[0]], PREP[1]) != PREP[3]:
        bad.append(f"skull kids: {PREP[0]} doesn't build 6 notes at once")
    bad += [f"skull kids: {e} sets {flat(by[e].get('params'), {}).get('Value')} rallies" for e in RALLY_SETS
            if flat(by[e].get("params"), {}).get("Value") != TURNS]
    first = fc["events"][fc["entry_points"][START[0]]["main"]]
    p = flat(first.get("params"), {})
    if (p.get("GameDataName"), p.get("Value")) != (GRADE, NOTES):
        bad.append(f"skull kids: {START[0]} doesn't start by setting {NOTES} notes")
    return bad
