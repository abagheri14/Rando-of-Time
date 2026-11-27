"""Scene gifts for the drops plugin. These are spots no pickup can carry a seed item from, so a scene of their own
gives it. The settings are drops.py remake_gc_pot_prize / remake_zd_grotto_rupees, the drop_map entry is
"scene_gifts" (built and checked against the game files by tools/rando/drops.py SCENE_GIFTS).

The steps are built with the songs_trade plugin's Ops (its world_plan calls parity.drops.scene_gift_ops), which owns
the give steps: Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff (Link holds the item up), the progressive tier
entries, the dungeon items' credit calls, the chests plugin's ice-trap freeze and the get window
(GetPouchContent:GetPouchContentByActorName, _songs_trade_lake._window_give). Sharing one Ops means every host entry
gets added once.

GC Pot Freestanding PoH (group "gc_pot"). The pot requests its heart-piece scene (GoronCity_LargePot entry
GoronCity_LargePotRoulette_HeartPieceDrop) only while its holder keeps the heart piece. Its code only allows that
while the save flag GoronLargePot_IsGetHeartPiece is false, and it sets that flag when the held heart piece dies
with DeathReason 10 (LifeDepleted).
  - Dm_Goron_0045 (the drop cutscene), after its last step: the heart piece goes offstage and is killed with
    DeathReason 10 (the same parameters as Dm_SY_Get's Event47 / Event124).
  - GoronCity_LargePot, after the entry's last step (GoronCity_LargePot_HeartPieceDrop set): if the scene ID has
    never played (its HavePlayedEvent flag, which the engine sets after a play), set GoronLargePot_IsGetHeartPiece
    and give the seed's item, held up.
ZD Storms Grotto Blue Rupee 1-6 (group "zd_grotto"). The grotto's entry requester in each Zora's Domain stage asks
for a reused scene ID (replace_row, a copy of HidingHole_Entry_01's row pointing at a new GimmickFlow_Common entry).
That entry runs the vanilla entry as a sub-flow, then, if that scene ID has never played, sets its HavePlayedEvent
flag and gives the six items, the first held up and the others in the get window. The six rupee placements are
deleted in all three stages. make_patch takes the reused row's old chest scene off its chest (compile_plan: reused
scene IDs).
"""
from . import _songs_trade_lake as lake
from . import _songs_trade_ops as st

EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
GC_REMOVE, GC_GIVE = "Rando_GCPot_Remove", "Rando_GCPot_Give"
HIDE = {"IsWaitEnd": True, "IsSleepXLink": True, "ExecuteSetSpeedZeroEveryFrame": False,
        "IsRidingTargetGoOffstage": False}  # Dm_SY_Get Event47 (EventGoOffstageForUser)
PICKED_UP = 10  # LifeDepleted (10) like Dm_SY_Get Event124, the pot then sets its flag


def _window(o, target, nxt):
    """The get window give (a dungeon item's credit call or a trap's call either way). These scenes aren't resident, so
    the Dm_SY_GetInEvent entries are theirs to call."""
    if "call" in target:
        return {"call": target["call"], "next": nxt}
    if target.get("ice_trap"):
        return {"call": st.ICE_CALL, "next": nxt}
    return lake._window_give(o, target, nxt)


def gc_pot(o, gift):
    g = gift["gift"]
    d, s = g["drop_scene"], g["give_scene"]
    o.events.append({"file": d["file"], "flowchart": d["file"], "add_graph": GC_REMOVE, "start": "hide", "nodes": {
        "hide": {"actor": d["actor"], "action": "EventGoOffstageForUser", "params": dict(HIDE), "next": "death"},
        "death": {"actor": d["actor"], "action": "EventTriggerRequestDeath", "params": {"DeathReason": PICKED_UP},
                  "next": None}}})
    o.events.append({"file": d["file"], "flowchart": d["file"], "event": d["after"], "next": f"{GC_REMOVE}_hide"})
    nodes = {"q": st.flag_query(g["once"], None, "flag")}
    if gift["target"].get("nothing"):  # OoTR's "Nothing" (remake_empty_object_contents "nothing") gives nothing
        nodes["flag"] = st.flag_set(g["flag"], None)
    else:
        nodes["flag"] = st.flag_set(g["flag"], "give")
        nodes["give"] = o.give(gift["target"], None)
    o.events.append({"file": s["file"], "flowchart": s["file"], "add_graph": GC_GIVE, "start": "q", "nodes": nodes})
    o.events.append({"file": s["file"], "flowchart": s["file"], "event": s["after"], "next": f"{GC_GIVE}_q"})
    o.notes.append(f"{gift['location']}: {gift['item']} from the spinning pot's heart-piece scene "
                   f"({s['file']}:{GC_GIVE}; the heart piece removed in {d['file']}:{GC_REMOVE}; once: {g['flag']})")


def zd_grotto(o, gifts):
    gifts = sorted(gifts, key=lambda x: x["gift"]["index"])
    g = gifts[0]["gift"]
    sc = g["scene"]
    nodes = {"entry": {"call": f":{sc['vanilla']}", "next": "q"},
             "q": st.flag_query(g["once"], None, "set")}
    given = [x for x in gifts if not x["target"].get("nothing")]  # OoTR's "Nothing" ("nothing" mode) gives nothing
    nodes["set"] = st.flag_set(g["once"], "g0" if given else None)
    for i, x in enumerate(given):
        nxt = f"g{i + 1}" if i + 1 < len(given) else None
        nodes[f"g{i}"] = o.give(x["target"], nxt) if i == 0 else _window(o, x["target"], nxt)
    o.events.append({"file": sc["file"], "flowchart": sc["file"], "add_graph": sc["entry"], "start": "entry",
                     "nodes": nodes})
    o.byml.append({"file": EVENT_SETTING, "replace_row": {"row": g["row"], "copy_of": g["copy_of"],
                                                          "set": {"EntryPointName": sc["entry"]}}})
    for t in g["triggers"]:
        o.placements.append({"file": t["file"], "hash": t["hash"], "set": {"Dynamic.RequestEventName": g["row"]}})
    for x in gifts:
        for p in x["placements"]:
            o.placements.append({"file": p["file"], "hash": p["hash"], "delete": True})
    o.notes.append(f"ZD Storms Grotto: {len(gifts)} items on the first entry into the grotto (scene ID {g['row']} -> "
                   f"{sc['file']}:{sc['entry']}; once: {g['once']}): "
                   + "; ".join(f"{x['location']}: {x['item']}" for x in gifts))


def ops(o, gifts):
    """Add every scene gift of this seed to songs_trade's Ops `o` (`gifts` from drops.get_scene_gifts)."""
    by = {}
    for x in gifts:
        by.setdefault(x["gift"]["group"], []).append(x)
    for x in by.get("gc_pot", []):
        gc_pot(o, x)
    if by.get("zd_grotto"):
        zd_grotto(o, by["zd_grotto"])
