"""Story settings (story plugin).

zora_fountain 'fast'
In OoTR King Zora moves for both ages as soon as Ruto's Letter is found, and the letter's bottle is then an empty
bottle. In logic "Deliver Letter" comes from Root with the letter, and has_bottle counts it.
  - What moves the King: the child and adult King's utility AIs read
    Get_StoneOfWater_IsAfter_Step06_Exp (robe collision Floor/Wall, attention). The child's passage also has an
    invisible wall (FldObj_AirWall_Player #14853753789178157158, ZoraDomain_Child_Dynamic) that's there while
    HavePlayedEvent.Dm_Zora_0010 (the delivery cutscene) is false. Nothing else in the game reads the Step05-08
    expressions (I scanned every Logic module and actor pack), and no placement is gated on them.
  - So Get_StoneOfWater_IsAfter_Step06_Exp becomes "after Step06 OR IsGet.Item_Bottle_Letter", and the wall's
    Presence reads a new expression "Dm_Zora_0010 played OR IsGet.Item_Bottle_Letter". IsGet.<pouch item> is the
    game's "ever got it" flag and the pouch add sets it from any source (vanilla scrub flows read
    IsGet.Item_Bottle_Letter to tell a bottle was had). So the King moves wherever the letter is found, a chest, an
    NPC, a pickup or the start.
  - The letter becomes an empty bottle right after it enters the pouch. Every give passes one of three pouch-add
    steps: GetPouchContent Event0 (chests, NPC and scene gifts), Dm_SY_Get Event35 (pickups held up) and
    Dm_SY_Get_WithoutPlayer Event11 after its add (in the air or water). Those now go on to "a bottle holds the
    letter (BottleItem 5)? then PouchSystemActor.EventTriggerRemoveFromSpecificBottle {Item=5}", the same step King
    Zora's delivery runs (Get_StoneOfWater Event231). A letter given any other way (a starting item) is emptied by
    the next give.
  - Ruto's Letter's vanilla pickup hook (StoneOfWater_GetRutoletter: Get_StoneOfWater_GetRutoLetter, Step05_01)
    still runs. The delivery cutscene never plays since there's nothing to deliver, so Get_StoneOfWater stays below
    Step07, and nothing but those expressions reads that."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

LETTER_FLAG = "IsGet.Item_Bottle_Letter"
LETTER_BOTTLE = 5  # BottleItem / Item of the letter (Get_StoneOfWater Event231, the delivery)
KING_EXP = "Get_StoneOfWater_IsAfter_Step06_Exp"
WALL_EXP = "Rando_ZoraWall_Exp"
WALL = ("Banc/ZoraDomain/ZoraDomain_Child_Dynamic.bcett.byml.zs", "14853753789178157158")
WALL_FLAG = "HavePlayedEvent.Dm_Zora_0010"
# (file, step after the pouch add, its vanilla action, the step it goes on to)
EMPTY_AT = (("GetPouchContent", "Event0", "PouchSystemActor.EventTriggerAddOrRemovePouchContent", "Event83"),
            ("Dm_SY_Get", "Event35", "PouchContentGuestPerformer.EventTriggerAddOwnToPouch", "Event181"),
            ("Dm_SY_Get_WithoutPlayer", "Event11", "UISystemActor.EventTriggerRequestOpenPickUpWindow", "Event1"))
GRAPH = "Rando_FastFountain"


def _check_steps(fs):
    from evfl import Evfl
    for file, ev, action, after in EMPTY_AT:
        fc = Evfl(fs.read(f"Event/EventFlow/{file}.bfevfl.zs")).flowcharts[0]
        e = next((x for x in fc["events"] if x["name"] == ev), None)
        if e is None or e["type"] != "action":
            raise RuntimeError(f"{file}: {ev} is no longer an action step (game update?)")
        a = fc["actors"][e["actor"]]
        if f"{a['name']}.{a['actions'][e['action']]}" != action or fc["events"][e["next"]]["name"] != after:
            raise RuntimeError(f"{file}: {ev} is no longer {action} -> {after}")
        if not any(x["name"] == "PouchSystemActor" for x in fc["actors"]):
            raise RuntimeError(f"{file}: no PouchSystemActor")


def zora_fast_plan(fs):
    """Plan sections for zora_fountain 'fast'."""
    from parity import _story_conditions as C
    _check_steps(fs)
    king = C.enum_after("Step_Get_StoneOfWater", "Step06") + [[C.BOOL, LETTER_FLAG], [C.OR]]
    wall = [[C.BOOL, WALL_FLAG], [C.BOOL, LETTER_FLAG], [C.OR]]
    events = []
    for file, ev, _, after in EMPTY_AT:
        events.append({"file": file, "flowchart": file, "add_graph": GRAPH, "start": "q", "nodes": {
            "q": {"actor": "PouchSystemActor", "query": "EventQueryIsExistBottleTypeInPouch",
                  "params": {"BottleItem": LETTER_BOTTLE}, "cases": {0: "empty", 1: f"@{after}"}},
            "empty": {"actor": "PouchSystemActor", "action": "EventTriggerRemoveFromSpecificBottle",
                      "params": {"Item": LETTER_BOTTLE}, "next": f"@{after}"}}})
        events.append({"file": file, "flowchart": file, "event": ev, "next": f"{GRAPH}_q"})
    return {
        "gamedata": [{"boolexp": {KING_EXP: king}}, {"add_boolexp": {WALL_EXP: wall}}],
        "placements": [{"file": WALL[0], "hash": WALL[1], "set": {
            "Presence": {"FlagName": WALL_EXP, "IsCheckLazy": False, "IsNegation": True}}}],
        "events": events,
        "_gaps": {"zora_fountain_fast": {"king": [KING_EXP, king], "wall": [WALL_EXP, wall, list(WALL)],
                                         "empty_at": [[f, ev, after] for f, ev, _, after in EMPTY_AT]}},
    }


def world_plan(settings, world):
    """This module's plan sections for the seed's settings ({} when none applies)."""
    from romtools import Romfs
    ws = getattr(world, "settings", settings)
    out = {}
    if ws.zora_fountain == "fast":
        fs = Romfs(os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(),
                   os.path.join(HERE, "original"))
        out = zora_fast_plan(fs)
    return out


# Read-back (parity/_gaps_check.py)
def _exp_values(gd, name):
    from romtools import murmur3_32
    row = next((e for e in gd["Data"]["BoolExp"] if e["Hash"] == murmur3_32(name)), None)
    return None if row is None else [[int(v) for v in st] for st in row["Values"]]


def _want(steps):
    from romtools import murmur3_32
    return [[murmur3_32(x) if isinstance(x, str) else int(x) for x in st] for st in steps]


def verify_zora_fast(patch, note, romfs):
    from romtools import Romfs, byml_load
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    for name, steps in (note["king"], note["wall"][:2]):
        if _exp_values(gd, name) != _want(steps):
            bad.append(f"GameDataList: {name} doesn't hold the planned expression")
    f, h = note["wall"][2]
    a = next((x for x in byml_load(fs.read(f))[0].get("Actors") or [] if str(x.get("Hash")) == h), None)
    if a is None or (a.get("Presence") or {}).get("FlagName") != note["wall"][0] or \
            not (a.get("Presence") or {}).get("IsNegation"):
        bad.append(f"{f} #{h}: the wall's Presence is {a and a.get('Presence')}")
    for file, ev, after in note["empty_at"]:
        fc = Evfl(fs.read(f"Event/EventFlow/{file}.bfevfl.zs")).flowcharts[0]
        evs = {e["name"]: e for e in fc["events"]}
        q = evs.get(ev) and fc["events"][evs[ev]["next"]]
        if q is None or q["type"] != "switch" or \
                fc["actors"][q["actor"]]["queries"][q["query"]] != "EventQueryIsExistBottleTypeInPouch":
            bad.append(f"{file}: {ev} doesn't go on to the letter check")
            continue
        cases = {c["value"]: fc["events"][c["next"]]["name"] for c in q["cases"]}
        rm = next((e for e in fc["events"] if e["name"] == cases.get(0)), None)
        if cases.get(1) != after or rm is None or rm["type"] != "action" or \
                fc["actors"][rm["actor"]]["actions"][rm["action"]] != "EventTriggerRemoveFromSpecificBottle" or \
                fc["events"][rm["next"]]["name"] != after:
            bad.append(f"{file}: the letter check doesn't empty the letter and go on to {after} ({cases})")
        prm = (q.get("params") or {}).get("items", {}).get("BottleItem", {}).get("value")
        if prm != LETTER_BOTTLE:
            bad.append(f"{file}: the letter check asks BottleItem {prm}")
    return bad
