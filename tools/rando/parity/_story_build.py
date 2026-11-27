"""Builds data/rando/story_data.json, the scene steps the story plugin (story.py) hooks into, read from the game
files (vanilla view) so the plugin can write patch plans without the romfs.

usage: python tools/rando/parity/_story_build.py ROMFS

What it records. Every name is read from the files, and the build stops if a step differs from what the plugin
expects.
- hooks: every step the plugin puts new steps in front of (or replaces), with the step's next step, every step or
  entry point leading to it (tools/progressive.predecessors) and its actor/action or query, checked.
- guards: every step in any scene file that sets a story challenge to a step *before* the one the plugin starts a
  new file at, with what leads to it, so the plugin can skip it once the challenge is that far. Story steps can go
  backwards, EscapeFromCrumblingGanonCastle:Event55 sets Ready.
- enums: the step order of the challenges the plugin reads or sets (GameDataList Step_<Challenge>).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load, murmur3_32  # noqa: E402
from evfl import Evfl  # noqa: E402
import progressive  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "story_data.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"

# file -> {step: what it must be}  ("action" Actor.Action, "query" Actor.Query, "call" Flowchart:Entry, "any")
HOOKS = {
    "DoorOfTime": {
        "Event92": "action SoundSystemActor.EventSoundRequestDucking",       # OpenDoor, before the Step04 check
        "Event60": "query GameDataActor.EventQueryIsGameDataBoolExp",        # DoorOfTime_IsAfter_Step04_Exp
        "Event69": "query GameDataActor.EventQueryIsGameDataBool",           # door not opened yet
        "Event172": "call SignboardWood:CommonFloorSignCamera",              # Check_SpiritStoneBase (the altar)
        "Event38": "query GameDataActor.EventQueryIsGameDataBoolExp",        # DoorOfTime_CheckStoneNum
        "Event22": "action EventSystemActor.EventTransition",                # a transition step to copy
        "Event57": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # OpenDoor: DoorOfTime Step06
        "Event115": "action PouchSystemActor.EventTriggerAddOrRemovePouchContent",   # first trip: the Master Sword
        "Event62": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # send-off: Fire KakarikoVillageNpc
        "Event93": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # Rauru: DoorOfTime Complete
        "Event14": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # Song of Time lesson: Step05
    },
    "Get_StoneOfFire": {
        "Event39": "query GameDataActor.EventQueryIsGameDataBoolExp",        # after the dance: past SariaMelodyPlay?
    },
    "SubEvent_GetEponaSong": {
        "Event36": "action GameDataActor.EventTriggerSetGameDataBool",       # Malon's second castle visit
    },
    "SageOfFire": {
        "Event396": "action EventSystemActor.EventWait",                     # right after the Goron Tunic's thanks
    },
    "Npc_Goron_DaruniaJr_Adult": {
        "Event99": "call :Mask_All",                                          # his plain talk (entry Talk)
        "Event0": "call InitTalk:InitTalk",                                   # his talk after the crater/DMT arrivals
    },
    "AllSage": {
        "Event40": "action Player_Event.EventTriggerParticipateEvent",       # Light Arrow cutscene start
        "Event175": "action Player_Event.EventTriggerEquipmentUserRequestCreateStaticEquipment",  # its variant
        "Event10": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # AllSage -> Complete
        "Event11": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # Defeat_Ganon -> Step01
        "Event34": "action ChallengeSystemActor.EventExecuteRollbackChallengeStep",  # Prelude: AllSage back to Step01_01
    },
    "Dm_SY_BancChange_EscapeDungeon": {
        "Event1": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",   # Get_StoneOfForest Complete
        "Event4": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",   # Goto_HyruleCastle Step01
        "Event208": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # Forest Temple: AllSage Step01_00
    },
    "ReplaceEquipmentForEraChange": {                                         # weapons swapped at each time travel
        "Event5": "action GameDataActor.EventTriggerSetGameDataString64",    # first adult: the Master Sword
        "Event11": "action GameDataActor.EventTriggerSetGameDataString64",   # first child: the Kokiri Sword
    },
    "Market_Child_Field_ChildToAdult": {
        "Event9": "action GameSystemActor.EventTriggerBancRequestBeforehandLoad",
    },
    "Npc_Gerudo_006": {
        "Event61": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # gatekeeper: SageOfSpirit Step02
    },
    "SageOfSpirit": {
        "Event146": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # 4th carpenter: Step02
        "Event292": "action Npc_Gerudo_017.EventAIScheduleWarpToAnchor",     # the step after it
    },
    "Dm_MelodyGet_Spilit": {
        "Event282": "call AllSage:MeetSheik_And_Gone",                      # end of Sheik's Requiem scene
    },
    "Dm_SY_BancChangeArrive": {
        "Event76": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # Colossus arrival: Step04
    },
    "MiniGame_BombchuBowling": {
        "Event137": "query GameDataActor.EventQueryIsGameDataBoolExp",       # open only after King Dodongo
    },
    "Npc_Goron_Biggoron_Adult": {                                            # Claim Check: 72 hours since the Eyedrops
        "Event82": "query GameDataActor.EventQueryCheckElapsedTime",
        "Event71": "query GameDataActor.EventQueryCheckElapsedTime",
        "Event115": "query GameDataActor.EventQueryCheckElapsedTime",
        "Event116": "query GameDataActor.EventQueryCheckElapsedTime",
    },
    "Npc_Hylia_048_BottleShop": {                                            # Big Poe buyer: coupon == 400 -> bottle
        "Event2": "query GameDataActor.EventQueryIsGameDataInt",
        "Event21": "query GameDataActor.EventQueryIsGameDataInt",
        "Event258": "query GameDataActor.EventQueryIsGameDataInt",
        "Event259": "query GameDataActor.EventQueryIsGameDataInt",
        "Event261": "query GameDataActor.EventQueryIsGameDataInt",
        "Event262": "query GameDataActor.EventQueryIsGameDataInt",
        "Event265": "query GameDataActor.EventQueryIsGameDataInt",
        "Event70": "query GameDataActor.EventQueryIsGameDataInt",
    },
    "OpeningEvent": {
        "Event9": "action EventWorldManagerController.EventTrigger_SetTime",
        "Event10": "action Npc_Navi.EventTriggerSetHaveTalked",
        "Event11": "action EventCamera.EventTriggerSendKeepStateMessageToPlayerCamera",
    },
    "Defeat_Ganon": {
        "Event42": "action GameSystemActor.EventReserveBancChange",          # after Ganondorf: to the escape
    },
    "Dm_SY_Ocarina": {
        "Event19": "call :PlayOcarinaFree",                                  # EntryPoint0: take out the ocarina
        "Event135": "query GameSystemActor.EventQueryCheckContactAreaCanCallPierre",
    },
    "MiniGame_DampeRace": {
        "Event31": "action ChallengeSystemActor.EventTriggerMiniGameTimerStop",
        "Event442": "query PouchSystemActor.EventQueryIsExistInPouch",       # Hookshot in the pouch?
        "Event379": "call :",
        "Event33": "query GameDataActor.EventQueryIsGameDataBool",
        "Event132": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",
        "Event187": "action GameDataActor.EventTriggerSetGameDataBool",
        "Event224": "action ChallengeSystemActor.EventTriggerMiniGameTimerStart",
    },
    "SageOfSpirit_RescueCarpenter": {
        "Event119": "action Player_Event.EventTriggerParticipateEvent",      # DoDoor_AnotherKey 013
        "Event113": "action Player_Event.EventTriggerParticipateEvent",      # 014
        "Event116": "action Player_Event.EventTriggerParticipateEvent",      # 015
        "Event204": "action Player_Event.EventTriggerParticipateEvent",      # 016
    },
}
ENTRIES = {  # entry points the plugin repoints: file -> {entry: first step}
    "DoorOfTime": {"Check_SpiritStoneBase": "Event172", "DoorOfTime_CheckStoneNum": "Event38",
                   "DoorOfTime_OpenDoor": "Event18"},
    "AllSage": {"Market_Adult_Field_GetArrowLight": "Event40", "GetArrowLight_OcarinaBackTimeTemple": "Event175"},
    "Dm_SY_Ocarina": {"EntryPoint0": "Event19", "AppearPierreEventTransition": "Event109"},
}
# challenge -> (step a new file is moved to by some setting, the expression that is true from that step on)
GUARDS = {
    "Goto_HyruleCastle": ("Complete", "Goto_HyruleCastle_IsCompleted_Exp"),
    "DoorOfTime": ("Step02", "DoorOfTime_IsAfter_Step01_Exp"),  # skip child Zelda starts after Impa's send-off
    "SubEvent_MaskSalesman": ("Complete", "SubEvent_MaskSalesman_IsCompleted_Exp"),
    "SageOfSpirit": ("Step02", "SageOfSpirit_IsAfter_Step01_Exp"),
    "Get_StoneOfWater": ("Step07", "Get_StoneOfWater_IsAfter_Step06_Exp"),
}
PROGRESS = ("EventExecuteProgressChallengeStep", "EventTriggerProgressChallengeStep")
# Quests whose progress requests the story plugin guards so they never move back, in any seed (_story_traps.py
# order_guards). We record every progress
# request of them in any scene file, with what leads to it ("requests"). For SageOfShadow and AllSage only some are
# guarded.
ORDERED = ("Get_StoneOfFire", "DoorOfTime", "Get_StoneOfWater", "SageOfWater", "SageOfFire", "SageOfSpirit",
           "Get_Epona", "SageOfShadow", "AllSage", "SageOfForest")


def newest(romfs, base):
    d = os.path.join(romfs, "Event", "EventFlow")
    rx = re.compile(re.escape(base) + r"(\.\d{3})?\.bfevfl\.zs$")
    found = sorted(f for f in os.listdir(d) if rx.match(f))
    if not found:
        raise SystemExit(f"no event file {base}")
    return "Event/EventFlow/" + found[-1], found


def flat(c, out, prefix=""):
    if not c:
        return out
    if c["type"] == "container":
        for k, v in c["items"].items():
            flat(v, out, k)
    else:
        out[prefix] = c["value"] if c["type"] != "argument" else f"<arg {c['value']}>"
    return out


def describe(fc, e):
    if e["type"] == "action":
        a = fc["actors"][e["actor"]]
        return f"action {a['name']}.{a['actions'][e['action']]}"
    if e["type"] == "switch":
        a = fc["actors"][e["actor"]]
        return f"query {a['name']}.{a['queries'][e['query']]}"
    if e["type"] == "subflow":
        return f"call {e.get('flowchart', '')}:{e.get('entry_point', '')}"
    return e["type"]


def step_info(fc, e):
    nxt = e.get("next")
    return {"next": fc["events"][nxt]["name"] if nxt is not None and nxt < len(fc["events"]) else None,
            "preds": [list(p) for p in progressive.predecessors(fc, e)],
            "kind": describe(fc, e), "params": flat(e.get("params"), {})}


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    enums = {}
    for e in gd["Data"]["Enum"]:
        for ch in list(GUARDS) + ["AllSage", "Defeat_Ganon", "Meet_DekuTree"] + list(ORDERED):
            if e["Hash"] == murmur3_32(f"Step_{ch}"):
                enums[ch] = e["RawValues"]
    # the "<challenge>_IsAfter_<step>_Exp" expressions the game has (story.py's order guards use them)
    boolexp = {e["Hash"] for e in gd["Data"]["BoolExp"]}
    after_exp = {ch: [s for s in enums[ch] if murmur3_32(f"{ch}_IsAfter_{s}_Exp") in boolexp] for ch in ORDERED}
    out = {"_about": "Built by tools/rando/parity/_story_build.py from the game files; read by story.py.",
           "hooks": {}, "entries": {}, "guards": {}, "enums": enums, "actors": {}, "requests": {},
           "after_exp": after_exp}
    flows = {}
    for base, steps in HOOKS.items():
        rel, versions = newest(romfs, base)
        if len(versions) != 1:
            raise SystemExit(f"{base}: {versions}: the plugin edits one version only, check the step names")
        fc = Evfl(fs.read(rel)).flowcharts[0]
        flows[base] = fc
        by = {e["name"]: e for e in fc["events"]}
        out["hooks"][base] = {"flowchart": fc["name"], "steps": {}}
        out["actors"][base] = [a["name"] for a in fc["actors"]]
        for name, want in steps.items():
            e = by.get(name)
            if e is None:
                raise SystemExit(f"{base}: no step {name}")
            info = step_info(fc, e)
            if not info["kind"].startswith(want):
                raise SystemExit(f"{base}:{name} is {info['kind']}, expected {want}")
            out["hooks"][base]["steps"][name] = info
    for base, eps in ENTRIES.items():
        fc = flows.get(base) or Evfl(fs.read(newest(romfs, base)[0])).flowcharts[0]
        for ep, first in eps.items():
            got = fc["events"][fc["entry_points"][ep]["main"]]["name"]
            if got != first:
                raise SystemExit(f"{base}: entry {ep} starts at {got}, expected {first}")
        out["entries"][base] = eps
    # every step that sets a guarded challenge back before its start step
    d = os.path.join(romfs, "Event", "EventFlow")
    bases = sorted({re.sub(r"(\.\d{3})?\.bfevfl\.zs$", "", f) for f in os.listdir(d) if f.endswith(".bfevfl.zs")})
    for base in bases:
        rel, versions = newest(romfs, base)
        try:
            ev = Evfl(fs.read(rel))
        except Exception:  # noqa: BLE001 - a file the reader can't take has no steps we could edit either
            continue
        for fc in ev.flowcharts:
            for e in fc["events"]:
                if e["type"] != "action":
                    continue
                a = fc["actors"][e["actor"]]
                if a["name"] != "ChallengeSystemActor" or a["actions"][e["action"]] not in PROGRESS:
                    continue
                p = flat(e.get("params"), {})
                ch, step = p.get("ChallengeName"), p.get("StepName")
                if ch not in enums or step not in enums[ch]:
                    continue
                info = step_info(fc, e)
                info.update(file=base, flowchart=fc["name"], event=e["name"], step=step, versions=versions,
                            has_gamedata=any(x["name"] == "GameDataActor" for x in fc["actors"]))
                if ch in ORDERED:
                    out["requests"].setdefault(ch, []).append(info)
                if ch not in GUARDS:
                    continue
                target, exp = GUARDS[ch]
                if enums[ch].index(step) >= enums[ch].index(target):
                    continue
                out["guards"].setdefault(ch, []).append(info)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {OUT}: {sum(len(v['steps']) for v in out['hooks'].values())} hook steps, "
          + ", ".join(f"{k} {len(v)} guards" for k, v in out["guards"].items())
          + "; requests: " + ", ".join(f"{k} {len(v)}" for k, v in out["requests"].items()))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
