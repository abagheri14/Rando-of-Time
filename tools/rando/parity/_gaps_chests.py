"""OoTR's fast_chests (Fast Chest Cutscenes): big chests open as quickly as small ones.

Small chests are already quick in the remake. A big chest (Obj_TBox_A_02 / A_03 and their NoBake twins) plays
Dm_SY_Treasurebox's cinematic instead: Success_ plays the fanfare, then Success_PlayerPerform, a fork of
  - the camera's cinematic shots (C01-x as a child, C02-x as an adult), each waiting for its end
  - Link walking up (Event44 / Event50) and his long lift (DemoOpenTreasureBox, Event40 / Event33)
  - Process_Treasurebox: 473 frames (Event52) before the item shows (Item_Rotation), the lid (:Open, FrontOpen or
    FrontOpen_Adult, waiting for its end) and Navi's flight
  - the rumbles, 340 frames of waits (Event97, Event65, Event105, Event107; Event100, Event103 as an adult)
then 90 more frames (Event45) before the get window. That's about 11 seconds.

With fast_chests, Link does the small chest's lift (DemoOpenTreasureBoxFront, the move Dm_SY_TreasureboxSmall plays
on both ages) and, once the lid starts, turns and holds the item up the way a small chest has him do it
(GetAnimationAction's DemoGet and DemoGetLoop, after HOLD_WAIT frames). The shots, the lid and the rumbles stop
holding the scene up, the item shows after SHOW_FRAMES and the get window comes REST_FRAMES later.

Every big-chest scene we build (progressive items, dungeon items, traps, Archipelago) copies these steps from
Dm_SY_Treasurebox, so the edits go to the copies too (make_patch "with_copies"). The lid's entry (:Open) is called
by all of them, which is where the hold-up goes.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FILE = "Dm_SY_Treasurebox"
SHOW_FRAMES = 60  # from the lift's start to the item showing above Link
REST_FRAMES = 30  # the item held up before the get window
HOLD_WAIT = 40  # from the lid's start to Link turning to hold the item up
LIFT = "DemoOpenTreasureBoxFront"
# (event, parameter, vanilla value, fast value)
EDITS = [
    ("Event52", "Frames", 473, SHOW_FRAMES),
    ("Event45", "Frames", 90, REST_FRAMES),
    ("Event40", "ASCommand", "DemoOpenTreasureBox", LIFT), ("Event40", "IsWaitEnd", False, True),
    ("Event33", "ASCommand", "DemoOpenTreasureBox", LIFT), ("Event33", "IsWaitEnd", False, True),
    ("Event44", "ASCommand", "DemoOpenTreasureBox", LIFT),
    ("Event50", "ASCommand", "DemoOpenTreasureBox", LIFT),
    ("Event4", "IsWaitEnd", True, False), ("Event68", "IsWaitEnd", True, False),
] + [(e, "IsWaitEnd", True, False) for e in ("Event61", "Event55", "Event41", "Event77", "Event123", "Event120",
                                             "Event47")] \
  + [(e, "Frames", f, 1) for e, f in (("Event97", 230), ("Event65", 70), ("Event105", 20), ("Event107", 20),
                                      ("Event100", 230), ("Event103", 110))]
LID = ("Event4", "Event68")  # the lid's last steps (child, adult): the hold-up follows them
HOLD_ENTRY = "Rando_FastChestHold"
# Dm_SY_TreasureboxSmall GetAnimationAction Event11 and Event32 (its no-smile branch)
TURN = {"ActorName": "PlayerCamera", "IsWaitEnd": True, "InstanceName": "", "WorldPos": [0.0, 0.0, 0.0],
        "PosOffset": [0.0, 0.0, 0.0], "Direction": 0.0, "KeepTalkWait": True, "OffsetBase": 0,
        "UpperASCommand": "DemoGet", "IgnoreTargetPosMove": True, "SlowTurn": False, "UseNormalTurn": False,
        "TurnFaceControlType": 2, "Target": 7, "IsDoNavi": False}
LOOP = {"KeepOneTimeAnm": False, "ForceFadeFrame": -1.0, "IsWaitEnd": False, "IsAllSlot": True,
        "ASCommand": "DemoGetLoop", "UseAnmDriven": False, "ClothWarpMode": 0}
# What a fast chest scene may not hold anywhere in the file: (actor, action, parameter, value)
SLOW = [("EventSystemActor", "EventWait", "Frames", 473), ("GameSystemActor", "EventWait", "Frames", 90),
        ("Player_Event", "EventPlayerPlayASForFlowchart", "ASCommand", "DemoOpenTreasureBox"),
        ("TreasureBox_EventStarter", "EventPlayAS", "IsWaitEnd", True)]

OWNS = {"fast_chests": (False, True)}


def hold_graph():
    nodes = {"wait": {"actor": "EventSystemActor", "action": "EventWait",
                      "params": {"IsWaitEnd": True, "Frames": HOLD_WAIT}, "next": "turn"},
             "turn": {"actor": "Player_Event", "action": "EventPlayerTurnAndLook", "params": dict(TURN),
                      "next": "loop"},
             "loop": {"actor": "Player_Event", "action": "EventPlayerPlayASForFlowchart", "params": dict(LOOP),
                      "next": None}}
    return nodes, "wait"


def events():
    ops = [{"file": FILE, "flowchart": FILE, "event": e, "param": p, "value": v, "with_copies": True}
           for e, p, _, v in EDITS]
    nodes, start = hold_graph()
    ops.append({"file": FILE, "flowchart": FILE, "add_graph": HOLD_ENTRY, "nodes": nodes, "start": start})
    ops += [{"file": FILE, "flowchart": FILE, "event": e, "next": f"{HOLD_ENTRY}_{start}"} for e in LID]
    return ops


def check_sources(romfs):
    """[problem] where the vanilla big chest scene isn't as this module expects."""
    import sys
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from romtools import Romfs
    from evfl import Evfl
    from parity._story_build import newest, flat
    rel, _ = newest(romfs, FILE)
    fc = next(f for f in Evfl(Romfs(romfs, os.path.join(HERE, "original")).read(rel)).flowcharts if f["name"] == FILE)
    by = {e["name"]: e for e in fc["events"]}
    bad = []
    for e, p, old, _ in EDITS:
        got = flat((by.get(e) or {}).get("params"), {}).get(p)
        if got != old:
            bad.append(f"{rel}: {e} {p} is {got!r}, not {old!r}")
    for e in LID:
        if by.get(e, {}).get("next") is not None:
            bad.append(f"{rel}: {e} no longer ends the lid's entry")
    return bad


def world_plan(settings, world):
    ws = getattr(world, "settings", settings)
    if not getattr(ws, "fast_chests", False):
        return {}
    return {"events": events(), "_fast_chests": {"file": FILE, "hold": HOLD_ENTRY},
            "_verify_plugins": ["_gaps_chests"]}


def verify(patch, plan, romfs):
    """Reads the fast big chest scene back from a built patch: no slow step left in the whole file (the vanilla
    steps and every copy of them) and the lid's entry leading into the hold-up."""
    rb = plan.get("_fast_chests")
    if not rb:
        return []
    import sys
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from romtools import Romfs
    from evfl import Evfl
    from parity._story_build import newest, flat
    rel, _ = newest(romfs, FILE)
    if not os.path.exists(os.path.join(patch, rel)):
        return [f"fast_chests: {rel} not in the patch"]
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad, n = [], 0
    for fc in Evfl(fs.read(rel)).flowcharts:
        for e in fc["events"]:
            if e.get("actor") is None or "action" not in e:
                continue
            a = fc["actors"][e["actor"]]
            act, p = a["actions"][e["action"]], flat(e.get("params"), {})
            for actor, action, key, value in SLOW:
                if (a["name"], act) == (actor, action) and p.get(key) == value:
                    if key == "IsWaitEnd" and p.get("ASName") not in ("FrontOpen", "FrontOpen_Adult"):
                        continue
                    bad.append(f"fast_chests: {fc['name']}:{e['name']} still has {key} {value!r}")
            n += (a["name"], act, p.get("ASCommand")) == ("Player_Event", "EventPlayerPlayASForFlowchart", LIFT)
        if fc["name"] == FILE:
            by = {e["name"]: e for e in fc["events"]}
            for e in LID:
                nxt = by[e].get("next")
                if nxt is None or fc["events"][nxt]["name"] != f"{rb['hold']}_wait":
                    bad.append(f"fast_chests: {e} doesn't lead into {rb['hold']}")
    if not n:
        bad.append("fast_chests: no step plays the quick lift")
    return bad


def UNTESTED(settings):
    if getattr(settings, "fast_chests", False):
        return ["fast_chests: big chests open with the small chest's lift and hold-up (Dm_SY_Treasurebox's "
                "cinematic steps shortened in every copy)"]
    return []
