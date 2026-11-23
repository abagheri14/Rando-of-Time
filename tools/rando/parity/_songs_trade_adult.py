"""adult_trade_shuffle for the songs/trade plugin (songs_trade.py). The 8 adult trade NPCs become real checks, with
the trade timers off the way OoTR models them (World.disable_trade_revert: no timers, no reverts).

The step data is data/rando/songs_trade_adult.json, built from the game files by _songs_trade_adult_build.py, which
checks every step named here.

How the remake runs the trade (read from the files): a trade NPC reacts to a shown item
(GameParameter/ShowItemReplaceEventParam in its pack) with a step scene (SubEvent_GetSwordBigGoron_Step03..Step11).
That scene gives the next item, takes the shown one, may start a timer, and moves the quest's challenge step
(Step_SubEvent_GetSwordBigGoron). The step also decides who stands at the Lost Woods stump (the Craftsman's son
from Step03 to Step04, Fado after Step04 up to Step06: logic module LostWood_Adult_Prefab_b5e7 and both
placements' Presence), Anju's talk branches, the timer prompts and every retry/give-up branch.

With adult_trade_shuffle on, trades come in any order, so:
- every give step of each trade location gets the location's item (progressive items and ice traps the way the
  core does them). The NPC still takes the shown item, so each gives once.
- the step only follows Anju's own scenes (StartSubEvent after her first adult talk, EggHatched, Step03 after her
  Cojiro trade) and the son's trade, which now moves it to Step05 (so Fado comes, like after Granny's trade in
  vanilla). Every other progress call becomes a 1-frame wait, and the quest's "Complete" sets a spare flag instead
  (SubEvent_GetSwordBigGoron_IsCompleted_Exp reads it). So no retry, give-up or "after" branch ever opens, and the
  Lost Woods stump (logic module LostWood_Adult_Prefab_b5e7 and the two placements' Presence, which all read the
  step) shows the son from Anju's Cojiro trade until his own trade, then Fado.
- timers are off. The three BigGoronTimer entries do nothing and SubEvent_GetSwordBigGoron_TimerCountingStep is
  false (no Navi prompt, no trade item removed on a warp, sleep or cutscene).
- Anju trades Cojiro once Talon is awake (IsAfter_Step01_01_Exp reads Talon's crowed flag, and vanilla also waits
  for Talon to leave Kakariko, which needs Epona). Her egg-hatched branch follows her first adult talk
  (IsAfter_WaitEggHatch_Exp reads IsAfter_Ready_Exp).
- the Pocket Egg is handed over hatched (Item_PocketCucco) wherever songs_trade resolves the item, and elsewhere
  it's kept out. The egg-hatch scene only hatches an egg the player holds.
With adult_trade_shuffle off nothing here changes the game, except biggoron_keep_knife_ops (always call it).
"""
import json
import os

from . import _songs_trade_ops as ops

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_PATH = os.path.join(HERE, "data", "rando", "songs_trade_adult.json")
DATA = json.load(open(DATA_PATH, encoding="utf-8")) if os.path.exists(DATA_PATH) else None

ADULT_TRADE_LOCATIONS = tuple((DATA or {}).get("gives", {}))
# We borrow an unreferenced scene row's HavePlayedEvent flag for "Biggoron has given his item". It's a saved Bool
# (ResetType 8, default false) and no game file names it (data/eventsetting_unreferenced.json).
FLAG_SWORD_DONE = "HavePlayedEvent.FocusOnGimmick_Basic_MultipleAnchor_FireTemple"
SON_TRADE_STEP = ("Npc_Hylia_017_Adult", "Event10")  # Step04 -> Step05
POCKET_CUCCO = "Item_PocketCucco"
DMT_BIGGORON = "DMT Biggoron"
CROWED = "KakarikoVillage_CrowedCucco_Npc_Hylia_Talon_Adult"
FALSE_EXP = [[0, "Sequence_IsChildhood"], [0, "Sequence_IsChildhood"], [5], [3]]  # x and not x


def shuffled(settings):
    return bool(getattr(settings, "adult_trade_shuffle", False))


def check_settings(settings):
    if shuffled(settings) and DATA is None:
        return ["adult_trade_shuffle: data/rando/songs_trade_adult.json missing: run "
                "tools/rando/parity/_songs_trade_adult_build.py"]
    return []


def active(settings):
    """OoTR locations this module patches for these settings."""
    return set(ADULT_TRADE_LOCATIONS) if shuffled(settings) else set()


def item_for(item, location, world):
    """The Pocket Egg is handed over hatched with the shuffle on (the remake hatches it only through Anju's step)."""
    if item == "Pocket Egg" and shuffled(world.settings):
        return POCKET_CUCCO
    return None


_HATCH = {"on": False}


def configure(settings):
    """Call this first in songs_trade.world_plan. target() only hatches the Pocket Egg with the shuffle on, because with
    it off the vanilla egg-hatch step still runs and the egg is given as is."""
    _HATCH["on"] = shuffled(settings)


def target(item_name, base_target):
    """songs_trade._target with the Pocket Egg hatched (shuffle on, see configure)."""
    if item_name == "Pocket Egg" and _HATCH["on"]:
        return {"actor": POCKET_CUCCO}
    return base_target(item_name)


def before_fill(world, settings, kept):
    """No item rule. The Pocket Egg goes anywhere and every plugin hands it over hatched through the shared resolver
    (songs_trade.hand_actor / _target; configure runs from keep_locations on). A progressive item at a give step that
    can't hand it over itself is given by a call to its tier entry (ops.reward_spec)."""
    return


def _item(world, name):
    try:
        loc = world.get_location(name)
    except KeyError:
        return None
    return loc.item.name if loc.item is not None else None


def biggoron_keep_knife_ops(o, world):
    """DMT Biggoron (a core scene location). When he gives anything but the Biggoron Sword, his claim-check scene
    doesn't take the player's Giant's Knife or broken knife any more (Event53/Event54 -> Event96/Event106). The 'quest
    not complete' branch goes straight to his no-knife path (Event71: the 72-hour wait, then the give)."""
    item = _item(world, DMT_BIGGORON)
    if DATA is None or item is None or item == "Biggoron Sword":
        return
    d = DATA["npc"]
    f = "Npc_Goron_Biggoron_Adult"
    o.events.append({"file": f, "flowchart": f, "event": d["biggoron_done_check"]["event"], "case": ops.NO,
                     "next": d["biggoron_no_knife"]})
    o.notes.append(f"{DMT_BIGGORON}: {item}; the Giant's Knife is no longer taken")


def world_plan_ops(o, world, settings, kept, base_target, ice_spec):
    """Adds the shuffle's ops to `o` (o.gamedata gets created if it's missing). base_target is songs_trade._target and
    ice_spec is songs_trade._ice_spec."""
    if not shuffled(settings) or DATA is None:
        return
    if not hasattr(o, "gamedata"):
        o.gamedata = []
    # 1. each trade location's give steps
    for name in ADULT_TRADE_LOCATIONS:
        item = _item(world, name)
        if item is None or name not in kept:
            continue
        t = target(item, base_target)
        for g in DATA["gives"][name]["gives"]:
            rid = g["reward_id"]
            if t.get("ice_trap"):
                o.rewards[rid] = dict(ice_spec(rid, name), note=f"{name}: {item}")
            else:
                o.rewards[rid] = ops.reward_spec(t, f"{name}: {item}", [rid])
        o.notes.append(f"{name}: {item}")
    # 2. challenge progress. The son's trade goes to Step05 (Fado comes, the son leaves), every other step after
    # Anju's own is off, and "Complete" sets the spare flag.
    for r in DATA["progress"]:
        nxt = ops.at(r["next"])
        if (r["file"], r["event"]) == SON_TRADE_STEP:
            o.param(r["file"], r["file"], r["event"], "StepName", "Step05")
            continue
        if r["step"] == "Complete":
            nodes = {"set": ops.flag_set(FLAG_SWORD_DONE, nxt)}
            start = "set"
        else:
            nodes = {"wait": ops.wait_node(r["wait_actor"], nxt)}
            start = "wait"
        o.replace(r["file"], r["file"], r, f"RandoST_NoStep_{r['event']}", nodes, start)
    # 3. timers off; the egg hatches only when held
    tm = DATA["timers"]
    s = tm["file"]
    for entry, rec in tm["timers"].items():
        o.replace(s, s, rec, f"RandoST_NoTimer_{entry}", {"wait": ops.wait_node(tm["wait_actor"], None)}, "wait")
    hatch = tm["hatch_start"]
    o.replace(s, s, hatch, "RandoST_HatchHeldEgg",
              {"q": {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                     "params": {"Actor": "Item_PocketEgg", "Num": 1},
                     "cases": {ops.YES: ops.at(hatch["event"]), ops.NO: None}}}, "q")
    # 4. expressions (not saved: they apply to existing saves too)
    o.gamedata.append({"boolexp": {
        "SubEvent_GetSwordBigGoron_TimerCountingStep": FALSE_EXP,
        "SubEvent_GetSwordBigGoron_IsAfter_Step01_01_Exp": [[0, CROWED]],
        "SubEvent_GetSwordBigGoron_IsAfter_WaitEggHatch_Exp": [[10, "SubEvent_GetSwordBigGoron_IsAfter_Ready_Exp"]],
        "SubEvent_GetSwordBigGoron_IsCompleted_Exp": [[0, FLAG_SWORD_DONE]],
    }})
    o.notes.append("adult_trade_shuffle: trade timers off, quest steps only from Anju's scenes and the son's trade "
                   "(-> Step05, Fado), Anju trades once Talon is awake, the Pocket Egg comes hatched")


# Logic the remake needs (merged into data/rando/logic/songs_trade.json). It's never looser than the game:
# - 'Cojiro Access' (Kak Anju Trade Pocket Cucco): without the shuffle the remake's Anju only trades Cojiro after
#   Talon has left Kakariko for the ranch (challenge Step02, set by Npc_Hylia_Talon_Adult_Kakariko's
#   SubEvent_GetSwordBigGoron_LeaveKakariko, which is only reached when Get_Epona_IsCompleted_Exp). With the shuffle
#   this module lets her trade once Talon is awake.
# - 'Broken Sword Access' (GV Trade Poachers Saw): the remake's Master Craftsman is past a rock pile the Megaton
#   Hammer clears (KeenGamer and Power Up's remake guides; Obj_BrokenRock_A_02 placements near him).
# - LW Trade Cojiro / LW Trade Odd Potion: the stump shows the son only from Anju's Cojiro trade (Step03) until his
#   own trade, then Fado (Step05). So with the shuffle the son needs Anju's trade done ('Cojiro Access'), and Fado
#   needs the son's trade done too. Without the shuffle the vanilla chain already implies both.
LOGIC = {
    "regions": {
        "Kakariko Village": {"events": {
            "Cojiro Access": "is_adult and at_day and 'Wake Up Adult Talon' and (adult_trade_shuffle or Epona)"}},
        "GV Fortress Side": {"events": {
            "Broken Sword Access": "is_adult and (('Poachers Saw Access' and not adult_trade_shuffle) or "
                                   "Poachers_Saw) and can_use(Megaton_Hammer)"}},
        "Lost Woods": {"locations": {
            "LW Trade Cojiro": "'Odd Mushroom Access' and (not adult_trade_shuffle or 'Cojiro Access')",
            "LW Trade Odd Potion": "'Poachers Saw Access' and "
                                   "(not adult_trade_shuffle or ('Odd Mushroom Access' and 'Cojiro Access'))"}},
    }
}
