"""Triforce Hunt (OoTR triforce_hunt, triforce_count_per_world, triforce_goal_per_world). Story plugin module.

In OoTR, triforce_count_per_world "Triforce Piece" items join the pool (ItemPool: pending junk, placed anywhere) and
the seed is won with triforce_goal_per_world of them (State.won_triforce_hunt). Ganon's boss key is forced to
'triforce' (World: the key is at "Gift from Sages" once the goal is reached). The game is saved on completion and
the credits roll.

The remake has no Triforce Piece item or model, so here:
  - A piece is given like the keyed Treasure Chest Game's keys (dungeons plugin: dungeon_item, its carrier in
    chests, a scene location's call, the drops plugin's scene drops and heart spots). Its credit step adds one to a
    new saved Int, Rando_TriforcePieceNum, which the Ganon's boss-key module adds with the key's condition
    (_dungeons_ganon.py). The get scene holds up one golden triangle of the game's Triforce without a get or pick-up
    window (_gaps_triforce_look.py: the Temple of Time relief's top triangle on a repurposed display actor, and the
    hold-up is still the Light Medallion's). Then the credit calls GetPouchContent:Rando_TriforceAfter.
  - Rando_TriforceAfter tells the count (one message per count, "Triforce Piece! n of goal") through a chain of
    EventQueryIsGameDataInt branches, one per possible count, and only at a piece's get.
  - The goal-th piece shows "the Triforce is complete", autosaves, loads the staff roll table and changes level into
    the staff roll exactly the way Ganon's death does. It's the count equal to the goal, so pieces past the goal
    never end the game again. Ganon's death is Defeat_Ganon InsideGanonCastle_Dungeon_BossDie_2: Event667
    UISystemActor.EventTriggerRequestLoadStaffRollTable, then Event176 GameSystemActor.EventReserveBancChange to
    Demo_ShootingLocation_Tapestry_ED / 'Ending' with boot event InsideGanonCastle_Dungeon_StaffRoll_HyruleCastle,
    which ends in Defeat_Ganon:EndingProcess, the game-clear return to the title. Ganon's cinematic ending itself
    (Dm_Ending_0000) is staged in Ganon's arena and doesn't play.
  - Ganon's boss lock opens at the goal (shuffle_ganon_bosskey 'triforce', _dungeons_ganon.py), so beating Ganon
    again stays possible, like OoTR's tooltip says.
Logic is OoTR's. Items: the dungeons plugin keeps pieces to the spots that can credit them (allowed)."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

OWNS = {"triforce_hunt": (False, True), "triforce_count_per_world": None, "triforce_goal_per_world": None}
READERS = {"triforce": "verify"}
FILE, ENTRY = "GetPouchContent", "Rando_TriforceAfter"
MSBT = "EventFlowMsg/Dm_SY_Get.msbt"
MSG = "EventFlowMsg/Dm_SY_Get:{}"
DONE = "Rando_TriforceDone"
ENDING = {"IsWaitEnd": True, "NextStartRot": [0.0, 0.0, 0.0], "EventStarterName": "",
          "BootEventName": "InsideGanonCastle_Dungeon_StaffRoll_HyruleCastle", "IsStartOnEvent": False,
          "NextStartPos": "Ending", "NextPosition": [0.0, 0.0, 0.0], "FadePattern": 3,
          "NextBanc": "Demo_ShootingLocation_Tapestry_ED", "IsItemWarp": False}  # Defeat_Ganon Event176


def _count_name():
    from parity import dungeons
    return dungeons.TRIFORCE_COUNT


def _talk(label):
    from parity._chests_scenes import TALK_PARAMS
    return {"actor": "SystemTextNPC", "action": "EventTalk", "params": dict(TALK_PARAMS, MessageId=MSG.format(label))}


def graph(count, goal):
    """(nodes, start) for the message for the count just reached and, at the goal, the ending.

    Every caller has just added one to the count, and a game-data write lands a frame or two later. With
    test_guardroom3 the first piece read the old 0 and showed nothing, and the second read 1 and said "1 of 20". So the
    chain waits first (write_read_check.settle, the same write-then-read pattern the game uses)."""
    from write_read_check import settle
    name = _count_name()
    n = {"settle": settle("q1")}
    for k in range(1, count + 1):
        above = f"q{k + 1}" if k < count else f"t{count}"
        n[f"q{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                      "params": {"GameDataName": name, "Value": k, "Index": -1},
                      "cases": {0: None, 1: f"t{k}", 2: above}}
        n[f"t{k}"] = dict(_talk(f"Rando_Triforce{k}"), next="done" if k == goal else None)
    n["done"] = dict(_talk(DONE), next="save")
    n["save"] = {"actor": "GameSystemActor", "action": "EventTriggerRequestAutoSave", "next": "roll"}
    n["roll"] = {"actor": "UISystemActor", "action": "EventTriggerRequestLoadStaffRollTable", "next": "ending"}
    n["ending"] = {"actor": "GameSystemActor", "action": "EventReserveBancChange", "params": dict(ENDING), "next": None}
    return n, "settle"


def texts(count, goal):
    out = {}
    for k in range(1, count + 1):
        tail = f"{k} of {goal}" + (" (the Triforce is already complete)" if k > goal else "")
        out[f"Rando_Triforce{k}"] = f"You found a {{tag:0,3,0000}}Triforce Piece{{tag:0,3,ffff}}!\n{tail}."
    out[DONE] = ("The Triforce is complete!\nYour quest is over: the game is saved,\nand the credits roll.")
    return out


def world_plan(settings, world):
    ws = getattr(world, "settings", settings)
    if not getattr(ws, "triforce_hunt", False):
        return {}
    count, goal = int(ws.triforce_count_per_world), int(ws.triforce_goal_per_world)
    if getattr(ws, "shuffle_ganon_bosskey", None) != "triforce":
        raise RuntimeError("triforce_hunt without OoTR's forced shuffle_ganon_bosskey 'triforce'")
    nodes, start = graph(count, goal)
    text = [{"lang": "*", "file": MSBT, "label": k, "markup": v, "add": True, "note": "triforce_hunt"}
            for k, v in texts(count, goal).items()]
    placed = sum(1 for loc in world.get_locations() if loc.item is not None and loc.item.name == "Triforce Piece"
                 and loc.item.world.id == world.id)
    return {"events": [{"file": FILE, "flowchart": FILE, "add_graph": ENTRY, "nodes": nodes, "start": start}],
            "text": text,
            "_gaps": {"triforce": {"count": count, "goal": goal, "placed": placed, "counter": _count_name()}}}


def UNTESTED(settings):
    return ["triforce_hunt (pieces counted in a new saved Int; the goal piece rolls the staff credits)"] if getattr(
        settings, "triforce_hunt", False) else []


def verify(patch, note, romfs):
    """Checks the counter row, each count's message, the goal's ending steps, and that every piece credit adds to the
    count."""
    from romtools import Romfs, byml_load, murmur3_32
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    row = next((e for e in gd["Data"]["Int"] if e["Hash"] == murmur3_32(note["counter"])), None)
    if row is None or row["SaveFileIndex"] != 0 or row["DefaultValue"] != 0:
        bad.append(f"GameDataList: {note['counter']} is not a saved Int starting at 0")
    fc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{FILE}.bfevfl.zs")).flowcharts if f["name"] == FILE)
    ev = fc["events"]
    by = {e["name"]: e for e in ev}

    def prm(e, k):
        return ((e.get("params") or {}).get("items") or {}).get(k, {}).get("value")

    def name(i):
        return ev[i]["name"] if i not in (None, 0xFFFF) and i < len(ev) else None
    for k in range(1, note["count"] + 1):  # walk the chain with count k
        e = by.get(f"{ENTRY}_q1")
        while e is not None and e["type"] == "switch":
            v = prm(e, "Value")
            case = 0 if k < v else 1 if k == v else 2
            e = by.get(name(next((c["next"] for c in e["cases"] if c["value"] == case), None)))
        if e is None or prm(e, "MessageId") != MSG.format(f"Rando_Triforce{k}"):
            bad.append(f"{FILE}:{ENTRY}: count {k} doesn't show its message")
            continue
        after = by.get(name(e["next"]))
        if (k == note["goal"]) != (after is not None):
            bad.append(f"{FILE}:{ENTRY}: count {k} {'does not end' if k == note['goal'] else 'ends'} the game")
    e = by.get(f"{ENTRY}_ending")
    if e is None or prm(e, "BootEventName") != ENDING["BootEventName"] or prm(e, "NextBanc") != ENDING["NextBanc"]:
        bad.append(f"{FILE}:{ENTRY}: no level change into the staff roll")
    gi = Evfl(fs.read("Event/EventFlow/Dm_SY_GetInEvent.bfevfl.zs")).flowcharts[0]
    credits = [e for e in gi["events"] if e["name"].startswith("Rando_DI_Triforce") and e["type"] == "action"
               and ((e.get("params") or {}).get("items") or {}).get("GameDataName", {}).get("value") == note["counter"]]
    if note["placed"] and not credits:
        bad.append(f"Dm_SY_GetInEvent: no Rando_DI_Triforce credit step adds to {note['counter']}")
    for e in credits:
        a = gi["actors"][e["actor"]]["actions"][e["action"]]
        nxt = gi["events"][e["next"]] if e["next"] not in (None, 0xFFFF) else None
        if a != "EventTriggerAddOrSubGameDataInt" or prm(e, "Value") != 1 or nxt is None or nxt["type"] != "subflow" \
                or f"{nxt.get('flowchart')}:{nxt.get('entry_point')}" != f"{FILE}:{ENTRY}":
            bad.append(f"Dm_SY_GetInEvent: {e['name']} doesn't add one and then tell the count")
    return bad
