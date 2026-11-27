"""Builds data/rando/songs_trade_adult.json, the scene steps, save data and AI nodes the adult trade module hooks.
The module is _songs_trade_adult.py, and all of it is read from the game files (vanilla view). The build stops if
anything it relies on changed.

usage: python tools/rando/parity/_songs_trade_adult_build.py ROMFS
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romtools import Romfs, byml_load, murmur3_32  # noqa: E402
from _songs_trade_build import BuildError, expect, single, step_info, params, wait_actor  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "songs_trade_adult.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
CHALLENGE = "SubEvent_GetSwordBigGoron"
LW_LOGIC = "Logic/LostWood_Adult_Prefab_b5e7.logic.module.ainb"
HAND = "NpcCommon:NpcCommon_HandOver_NpcToPlayer_NoDisplay"

# OoTR location -> (scene file, [(event, call, item param, vanilla item)]), every step that hands the location's
# vanilla item to the player. Removal steps (AddOrRemovePouchContent Num -1) aren't give steps.
GIVES = {
    "LW Trade Cojiro": ("Npc_Hylia_017_Adult", [("Event100", HAND, "ReveiveItem", "Item_OddMushroom"),
                                                ("Event116", HAND, "ReveiveItem", "Item_OddMushroom")]),
    "Kak Granny Trade Odd Mushroom": ("Npc_Hylia_053_Adult", [("Event167", HAND, "ReveiveItem", "Item_OddPowder")]),
    "LW Trade Odd Potion": ("Npc_Kokiri_Fado_Adult", [("Event123", "Dm_SY_GetInEvent:GetInEvent_NotTurn_Fado",
                                                      "ActorName", "Item_PoacherSaw")]),
    "GV Trade Poachers Saw": ("Npc_Hylia_012_Adult", [("Event58", HAND, "ReveiveItem", "Item_BrokenSword")]),
    "DMT Trade Broken Sword": ("Npc_Goron_Biggoron_Adult", [
        ("Event232", "Dm_SY_GetInEvent:GetInEvent_NotTurnForPosCamera_BigGoron", "ActorName", "Item_Prescription")]),
    "ZD Trade Prescription": ("Npc_Zora_KingZora_adult", [
        ("Event131", "Dm_SY_GetInEvent:GetInEvent_NotTurn_PosCamera", "ActorName", "Item_EyeballFrog"),
        ("Event87", "Dm_SY_GetInEvent:GetInEvent_NotTurn_PosCamera", "ActorName", "Item_EyeballFrog")]),
    "LH Trade Eyeball Frog": ("Npc_Hylia_045_Adult", [("Event26", HAND, "ReveiveItem", "Item_EyeDrop"),
                                                      ("Event27", HAND, "ReveiveItem", "Item_EyeDrop"),
                                                      ("Event45", HAND, "ReveiveItem", "Item_EyeDrop")]),
    "Kak Anju Trade Pocket Cucco": ("Npc_Hylia_049_Adult", [("Event234", HAND, "ReveiveItem", "Item_CojiroCucco")]),
}
# challenge progress steps the shuffle mode turns off: every SubEvent_GetSwordBigGoron step except Anju's own
# (StartSubEvent after her first adult talk, Step03 after her Cojiro trade) and the egg hatching (EggHatched).
# Otherwise waking Talon (Step01/Step01_01/Step02) would move the step past Anju's first-talk scene. Later steps only
# drive the Lost Woods pair (edited instead), dialogue, and the retry/give-up branches that re-give or take back
# trade items.
EARLY = {"StartSubEvent", "WaitEggHatch", "EggHatched", "Step03"}
PROGRESS_FILES = ("Dm_DeathMtTrail_0050", "Npc_Goron_Biggoron_Adult", "Npc_Hylia_012_Adult", "Npc_Hylia_017_Adult",
                  "Npc_Hylia_045_Adult", "Npc_Hylia_049_Adult", "Npc_Hylia_053_Adult", "Npc_Kokiri_Fado_Adult",
                  "Npc_Zora_KingZora_adult", "SubEvent_GetSwordBigGoron", "Npc_Hylia_Talon_Adult_Kakariko")
EXPRESSIONS = ("SubEvent_GetSwordBigGoron_TimerCountingStep", "SubEvent_GetSwordBigGoron_IsAfter_Step04_Exp",
               "SubEvent_GetSwordBigGoron_IsAfter_Step01_01_Exp", "SubEvent_GetSwordBigGoron_IsCompleted_Exp",
               "SubEvent_GetSwordBigGoron_IsAfter_WaitEggHatch_Exp", "SubEvent_GetSwordBigGoron_IsAfter_Ready_Exp")
BOOLS = ("KakarikoVillage_CrowedCucco_Npc_Hylia_Talon_Adult",
         "HavePlayedEvent.FocusOnGimmick_Basic_MultipleAnchor_FireTemple",
         "Sequence_IsChildhood")


def event(fc, name):
    e = next((x for x in fc["events"] if x["name"] == name), None)
    if e is None:
        raise BuildError(f"{fc['name']}: no step {name}")
    return e


def gives_data(fs, romfs):
    out = {}
    for loc, (f, steps) in GIVES.items():
        fc = single(fs, romfs, f)
        recs = []
        for ev, call, param, item in steps:
            expect(fc, ev, "call", (call, {param: item}))
            recs.append({"event": ev, "reward_id": f"event/{f}/{f}/{ev}/{param}", "item": item})
        out[loc] = {"file": f, "gives": recs}
    return out


def progress_data(fs, romfs):
    """Every ChallengeSystemActor progress call of the quest, in the files the trade scenes live in."""
    out = []
    for f in PROGRESS_FILES:
        fc = single(fs, romfs, f)
        for e in fc["events"]:
            if e["type"] != "action":
                continue
            a = fc["actors"][e["actor"]]
            if a["actions"][e["action"]] != "EventExecuteProgressChallengeStep":
                continue
            p = params(e)
            if p.get("ChallengeName") != CHALLENGE or p.get("StepName") in EARLY:
                continue
            rec = step_info(fc, e)
            rec.update(file=f, step=p["StepName"], wait_actor=wait_actor(fc))
            out.append(rec)
    names = {(r["file"], r["event"]) for r in out}
    for need in (("Npc_Hylia_017_Adult", "Event10"), ("Npc_Goron_Biggoron_Adult", "Event89"),
                 ("Dm_DeathMtTrail_0050", "Event57"), ("Npc_Kokiri_Fado_Adult", "Event18")):
        if need not in names:
            raise BuildError(f"{need}: expected progress step not found")
    return out


def timers_data(fs, romfs):
    fc = single(fs, romfs, CHALLENGE)
    out = {}
    for entry, ev in (("BigGoronTimer_Step04", "Event24"), ("BigGoronTimer_Step09", "Event30"),
                      ("BigGoronTimer_Step10", "Event38")):
        rec = expect(fc, ev, "action", ("ChallengeSystemActor.EventTriggerMiniGameTimerSetting", {"IsCountDown": True}))
        if ["entry", entry, None] not in rec["preds"]:
            raise BuildError(f"{CHALLENGE}:{ev} is no longer the start of {entry}")
        out[entry] = rec
    hatch = step_info(fc, fc["events"][fc["entry_points"]["EggHatch_PocketEgg"]["main"]])
    remove = expect(fc, "Event5", "action", ("PouchSystemActor.EventTriggerAddOrRemovePouchContent",
                                             {"Actor": "Item_PocketEgg", "Num": -1}))
    return {"file": CHALLENGE, "timers": out, "hatch_start": hatch, "egg_removal": remove, "wait_actor": wait_actor(fc)}


def npc_steps(fs, romfs):
    out = {}
    # 017: the Cojiro trade's removal step (right after the give) gets the "trade done" flag in front of it, and
    # his Talk goes straight to his idle chat (Event23) instead of the timer/give-up/retry branches
    fc = single(fs, romfs, "Npc_Hylia_017_Adult")
    out["son_remove_cojiro"] = expect(fc, "Event25", "action", ("PouchSystemActor.EventTriggerAddOrRemovePouchContent",
                                                                {"Actor": "Item_CojiroCucco", "Num": -1}))
    if out["son_remove_cojiro"]["preds"] != [["next", "Event100", None]]:
        raise BuildError("Npc_Hylia_017_Adult:Event25 is no longer reached only from the Cojiro give")
    out["son_talk_gate"] = expect(fc, "Event95", "call", (":Mask_All",))
    if out["son_talk_gate"]["next"] != "Event14":
        raise BuildError("Npc_Hylia_017_Adult:Event95 no longer leads to the step checks (Event14)")
    expect(fc, "Event23", "query", ("Npc_EventStarter.EventQueryAvoidDuplicationRandomChoice3",))
    out["son_idle"] = "Event23"
    # Anju takes the Pocket Cucco after handing over Cojiro.
    fc = single(fs, romfs, "Npc_Hylia_049_Adult")
    out["anju_remove_cucco"] = expect(fc, "Event77", "action", ("PouchSystemActor.EventTriggerAddOrRemovePouchContent",
                                                                {"Actor": "Item_PocketCucco", "Num": -1}))
    # Biggoron's claim check scene: Event49 IsCompleted? -> Event53 (Giant's Knife held? taken) / Event54 (broken
    # knife? taken) / Event71 (neither: 72 hours since the Eyedrops, then the sword at Event123)
    fc = single(fs, romfs, "Npc_Goron_Biggoron_Adult")
    done = expect(fc, "Event49", "query", ("GameDataActor.EventQueryIsGameDataBoolExp",
                                           {"GameDataName": "SubEvent_GetSwordBigGoron_IsCompleted_Exp"}))
    e49 = event(fc, "Event49")
    cases = {c["value"]: fc["events"][c["next"]]["name"] for c in e49["cases"]}
    if cases.get(1) != "Event53":
        raise BuildError("Npc_Goron_Biggoron_Adult:Event49 'not complete' no longer goes to Event53")
    expect(fc, "Event53", "query", ("PouchSystemActor.EventQueryIsExistInPouch", {"Actor": "Weapon_Sword_Giant"}))
    expect(fc, "Event71", "query", ("GameDataActor.EventQueryCheckElapsedTime", {"ElapsedHour": 72}))
    expect(fc, "Event123", "call", ("Dm_SY_GetInEvent:GetInEventItemSwordBiggoron", {"ActorName": "Item_Sword_Biggoron"}))
    out["biggoron_done_check"] = done
    out["biggoron_no_knife"] = "Event71"
    return out


def gamedata_check(fs):
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    exps = {e["Hash"]: e for e in gd["BoolExp"]}
    bools = {e["Hash"]: e for e in gd["Bool"]}
    out = {}
    for n in EXPRESSIONS:
        e = exps.get(murmur3_32(n.encode()))
        if e is None:
            raise BuildError(f"no expression {n} in GameDataList")
        out[n] = e["Values"]
    for n in BOOLS:
        e = bools.get(murmur3_32(n.encode()))
        if e is None or (n.startswith("HavePlayedEvent.") and (e["ResetTypeValue"] != 8 or e["DefaultValue"])):
            raise BuildError(f"{n}: not a saved, default-false Bool in GameDataList")
    return out


def lw_logic(fs):
    """The adult Lost Woods logic module that creates the Craftsman's son (Step03..Step04) and Fado (after Step04,
    up to Step06) at the stump, and the Skull Kid there otherwise, from the challenge step. We only check it, never
    edit it, because the shuffle keeps the step at Step03 until the son's trade and then Step05."""
    import ainb
    a = ainb.Ainb(fs.raw(LW_LOGIC))
    names = {}
    for i, n in enumerate(a.nodes):
        inst = next((e.get("value") for e in n["properties"]["string"] if e["name"] == "InstanceName"), None)
        if inst:
            names[inst] = i
    need = {"son": "Npc_Hylia_017_Adult_7d7e", "fado": "Npc_Kokiri_Fado_Adult_7409", "skullkid": "Enemy_SkullKid_5a60",
            "anchor": "AnchorAction1_7beb"}
    out = {"file": LW_LOGIC}
    for k, inst in need.items():
        if inst not in names:
            raise BuildError(f"{LW_LOGIC}: no node for {inst}")
        out[k] = names[inst]
    for k in ("son", "fado", "skullkid"):
        e = next(e for e in a.nodes[out[k]]["inputs"]["bool"] if e["name"] == "Logic_Create")
        if e["node"] < 0:
            raise BuildError(f"{LW_LOGIC}: {need[k]}'s Logic_Create is no longer fed by a node")
    anchor = next(e for e in a.nodes[out["anchor"]]["inputs"]["bool"] if e["name"] == "Logic_Create")
    if anchor["node"] >= 0 or anchor["value"] is not True:
        raise BuildError(f"{LW_LOGIC}: the stump anchor is no longer always created")
    steps = sorted({e["value"] for n in a.nodes if n["name"] == "HoldChallengeCurrentStepCheckOrder"
                    for e in n["inputs"]["string"] if e["name"] == "ChallengeStepName"})
    if steps != ["Step03", "Step04", "Step06"]:
        raise BuildError(f"{LW_LOGIC}: step checks changed: {steps}")
    return out


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    data = {"_about": __doc__.strip().splitlines()[0],
            "gives": gives_data(fs, romfs), "progress": progress_data(fs, romfs), "timers": timers_data(fs, romfs),
            "npc": npc_steps(fs, romfs), "expressions": gamedata_check(fs), "lw_logic": lw_logic(fs)}
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"{len(data['gives'])} trade locations, {len(data['progress'])} later progress steps -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except BuildError as e:
        sys.exit(f"build error: {e}")
