"""Build data/rando/extras_story_data.json: the game facts the extras_story plugin (extras_story.py) relies on, read
from the game files (vanilla view), so the plugin can write patch plans without the romfs.

usage: python tools/rando/parity/_extras_story_build.py ROMFS [VANILLA_DIR]
       (VANILLA_DIR: the saved originals of patched files; default ./original)

What it records and checks (the build stops when a file differs from what the plugin was written against):
- hooks: every scene step the plugin puts steps in front of or copies, with its next step, every step or entry
  point leading to it (tools/progressive.predecessors), its kind and parameters
- gamedata: the save-data flags the plugin sets or reads (type, default)
- placements: the placed objects the plugin edits (level file, hash, type, current settings)
- ainb: the level-logic words the plugin rewrites (offset, current value)
- anchors: named anchors the plugin measures distances to (unique in their level)
- text: the message file the plugin adds its messages to, in every language
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from romtools import Romfs, byml_load, murmur3_32  # noqa: E402
from evfl import Evfl  # noqa: E402
from parity._story_build import newest, step_info  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "extras_story_data.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"

# file -> {step: what it must be} ("action Actor.Action", "query Actor.Query", "call File:Entry", "fork")
HOOKS = {
    # medallion-locked trials. The doors into each trial's barrier room have their own scene: you pass the door, then
    # get the first-time look at the barrier. The Light trial's barrier door just plays the default door scene.
    "InsideGanonCastle_CommonGimmick": {
        "Event138": "call Common_Dungeon_OpenShutterMove:MoveToPlusZ",   # LookBarrierFromDoor_Forest
        "Event141": "call Common_Dungeon_OpenShutterMove:MoveToPlusZ",   # LookBarrierFromDoor_Water
        "Event144": "call Common_Dungeon_OpenShutterMove:MoveToPlusZ",   # LookBarrierFromDoor_Fire
        "Event164": "call Common_Dungeon_OpenShutterMove:MoveToPlusZ",   # LookBarrierFromDoor_Shadow
        "Event167": "call Common_Dungeon_OpenShutterMove:MoveToPlusZ",   # LookBarrierFromDoor_Spirit
    },
    # Ganon's soul: the boss-key door to Ganondorf. Its scene ends by starting the fight.
    "Common_Dungeon_OpenShutterMove": {
        "Event307": "action Player_Event.EventPlayerMove",               # UnlockGanonBossRoomMoveTo0
        "Event100": "call Defeat_Ganon:InsideGanonCastle_Dungeon_BossAppear_1",
    },
    # four Poes: the main-hall door's scene plays the cutscene on the first pass
    "ForestTemple_OpenDoor_Room01To02": {
        "Event2": "query GameDataActor.EventQueryHavePlayedEvent",       # Dm_ForestTemple_0010 played?
        "Event3": "action Player_Event.EventPlayerMove",                 # not played: walk in ...
        "Event4": "action EventSystemActor.EventTransition",             # ... then the cutscene
        "Event11": "action EventCamera.EventTriggerSendKeepStateMessageToPlayerCamera",
    },
    "Dm_ForestTemple_0010": {                                            # the cutscene's lasting effects
        "Event305": "action GameDataActor.EventTriggerSetGameDataBool",  # ForestTemple_Elevator_BeforeDm0010
        "Event2": "action ChallengeSystemActor.EventExecuteProgressChallengeStep",  # SageOfForest Step06
        "Event307": "action ChallengeSystemActor.EventTriggerShowChallengeProgressUI",
    },
    # Lake Hylia owl: the flight cutscene between the fade-out and the landing scene
    "Npc_Kaepora_LakeHylia": {
        "Event18": "action SoundSystemActor.EventTriggerStopInGameBgm",
        "Event19": "action EventSystemActor.EventTransition",            # Dm_LakeHrl_0010 (the flight)
        "Event22": "action SoundSystemActor.EventTriggerSoundBeginForbidScreenDucking",
    },
    # King Zora: C10, his 1500-frame shuffle aside
    "Dm_Zora_0010": {
        "Event3": "fork",                                                # C10: the move and its camera waits
        "Event55": "action GameDataActor.EventTriggerSetGameDataBool",   # his robe becomes walkable
        "Event195": "action Npc_Zora_007.EventAIScheduleWarpToAnchor",
        "Event177": "action EventWorldManagerController.EventTriggerResetDemoPaletteForFlowchart",
        "Event232": "call Common_Camera_Pln:CameraDoF_Default",
        "Event175": "action Npc_Zora_KingZora_child.EventTriggerChangeEmotion",
        "Event92": "action Npc_Zora_KingZora_child.EventTalk",           # "Whew..."
        "Event184": "action Npc_Zora_KingZora_child.EventTriggerChangeEmotion",  # after the move
        "Event67": "action Npc_Zora_KingZora_child.EventPlayAS",         # the move itself (AS C10)
    },
    # messages: the plugin adds its entries next to the game's system-text talks
    "GetPouchContent": {
        "Event23": "action SystemTextNPC.EventTalk",
    },
}
ENTRIES = {  # entry points the plugin relies on: file -> {entry: first step}
    "InsideGanonCastle_CommonGimmick": {"InsideGanonCastle_LookBarrierFromDoor_Forest": "Event138",
                                        "InsideGanonCastle_LookBarrierFromDoor_Water": "Event141",
                                        "InsideGanonCastle_LookBarrierFromDoor_Fire": "Event144",
                                        "InsideGanonCastle_LookBarrierFromDoor_Shadow": "Event164",
                                        "InsideGanonCastle_LookBarrierFromDoor_Spirit": "Event167"},
    "Common_Dungeon_OpenShutterMove": {"UnlockGanonBossRoomMoveTo0": "Event307"},
    "Dm_Zora_0010": {"C10": "Event3"},
}
GAMEDATA_FLAGS = (
    "Zorariver_TheWaterfallsplits", "HavePlayedEvent.Dm_ForestTemple_0010", "ForestTemple_Elevator_BeforeDm0010",
    "HavePlayedEvent.Get_StoneOfWater_ArriveJabuJabuBelly", "JabJabOpenedMouth",
    "Npc_Zora_KingZora_child_EnableClothCollidable", "HavePlayedEvent.Dm_Zora_0010",
    "IsGet.Item_Medal_Forest", "IsGet.Item_Medal_Fire", "IsGet.Item_Medal_Water", "IsGet.Item_Medal_Shadow",
    "IsGet.Item_Medal_Spirit", "IsGet.Item_Medal_Light", "IsGet.Item_Stone_Forest", "IsGet.Item_Stone_Fire",
    "IsGet.Item_Stone_Water", "PouchData.Item_Token_Gold.StockNum", "PlayerStatus.MaxLife",
    "InsideGanonCastle_Dungeon_BarrierRemove_Light",
)
PLACEMENTS = {  # name -> (level file, hash, Gyaml, settings that must be absent or have this value)
    # the fountain's doorway into Jabu-Jabu, at his mouth. It exists while JabJabOpenedMouth is set (prefab
    # Common_FieldDungeonEntranceSet).
    "jabu_mouth": ("Banc/ZoraFountain/ZoraFountain_Child_Static.bcett.byml.zs", "4228704915231375030",
                   "FieldAndDungeonEntranceEventRequestActor",
                   {"NextEventName": "Dm_SY_BancChangeArrive", "InitEventName": None, "InitEventFlag": None,
                    "NextStartPosName": "InsideJabuJabuBelly_FromZoraFountain"}),
    # the door into the Light trial's barrier room (room 14 -> 15), it plays the default door scene
    "light_barrier_door": ("Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs", "18370141889105081871",
                           "Obj_InsideGanonCastle_SwitchShutter_A_01", {"NomralEvent": None}),
    # the other five barrier doors already play their own LookBarrierFromDoor scene
    "forest_barrier_door": ("Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs", "16547757579712762477",
                            "Obj_InsideGanonCastle_SwitchShutter_A_01",
                            {"NomralEvent": "InsideGanonCastle_LookBarrierFromDoor_Forest"}),
    "water_barrier_door": ("Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs", "9454360734666596216",
                           "Obj_InsideGanonCastle_SwitchShutter_A_01",
                           {"NomralEvent": "InsideGanonCastle_LookBarrierFromDoor_Water"}),
    "shadow_barrier_door": ("Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs", "15970872372384393881",
                            "Obj_InsideGanonCastle_SwitchShutter_A_01",
                            {"NomralEvent": "InsideGanonCastle_LookBarrierFromDoor_Shadow"}),
    "fire_barrier_door": ("Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs", "8540530808124215779",
                          "Obj_InsideGanonCastle_SwitchShutter_A_01",
                          {"NomralEvent": "InsideGanonCastle_LookBarrierFromDoor_Fire"}),
    "spirit_barrier_door": ("Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs", "9280501248130802789",
                            "Obj_InsideGanonCastle_SwitchShutter_A_01",
                            {"NomralEvent": "InsideGanonCastle_LookBarrierFromDoor_Spirit"}),
    # Ganondorf's boss-key door, its scene starts the fight
    "ganondorf_door": ("Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs", "4569037702968299446",
                       "Obj_InsideGanonCastle_SwitchShutter_A_03",
                       {"NomralEvent": "Common_Dungeon_OpenDoorChainLock_UnlockGanonBossRoomMoveTo0",
                        "OpenChainEvent": "Common_Dungeon_OpenDoorChainLock_UnlockGanonBossRoomMoveTo0"}),
}
# Jabu-Jabu. The open-mouth areas (nodes 8 and 9) only get created after Get_StoneOfWater Step08 (node 18).
# Node 6 checks Step07, and its IsEqual is what sets Step08 when the player reaches Jabu-Jabu. So we switch their source
# to node 6, output IsAfter.
AINB = {
    "jabu_open_mouth": [("Logic/ZoraFountain_Child_Prefab_41c4.logic.module.ainb", 0x17C8, 6, 18),
                        ("Logic/ZoraFountain_Child_Prefab_41c4.logic.module.ainb", 0x17F8, 6, 18)],
}
AINB_NODES = {  # what the rewritten words point at (file, node index, node type, string parameter)
    "jabu_open_mouth": [("Logic/ZoraFountain_Child_Prefab_41c4.logic.module.ainb", 6,
                         "HoldChallengeCurrentStepCheckOrder", "Step07"),
                        ("Logic/ZoraFountain_Child_Prefab_41c4.logic.module.ainb", 18,
                         "HoldChallengeCurrentStepCheckOrder", "Step08")],
}
ANCHORS = {"light_barrier_door": ("InsideGanonCastle", "room14_lookPos01")}
TEXT_FILE = "EventFlowMsg/Item_Event.msbt"


def _flags(fs):
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    index = {}
    for table, entries in gd["Data"].items():
        if table == "Bool64bitKey":
            continue
        for e in entries:
            index.setdefault(e["Hash"], (table, e))
    out = {}
    for name in GAMEDATA_FLAGS:
        hit = index.get(murmur3_32(name))
        if hit is None:
            raise SystemExit(f"no save-data flag {name}")
        table, e = hit
        out[name] = {"type": table, "default": e.get("DefaultValue")}
    return out


def _placements(fs):
    out, cache = {}, {}
    for key, (rel, h, gyaml, want) in PLACEMENTS.items():
        if rel not in cache:
            cache[rel] = byml_load(fs.read(rel))[0]
        actors = [a for a in cache[rel].get("Actors", []) if str(a.get("Hash")) == h]
        if len(actors) != 1 or actors[0].get("Gyaml") != gyaml:
            raise SystemExit(f"{key}: {rel} has no single {gyaml} {h}")
        dyn = actors[0].get("Dynamic") or {}
        for k, v in want.items():
            if dyn.get(k) != v:
                raise SystemExit(f"{key}: {k} is {dyn.get(k)!r}, expected {v!r}")
        out[key] = {"file": rel, "hash": h, "gyaml": gyaml, "dynamic": dyn,
                    "translate": [round(x, 3) for x in actors[0].get("Translate", [])]}
    return out


def _ainb(fs):
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from ainb import Ainb  # the project's AINB reader (tools/ainb.py)
    out = {}
    for key, edits in AINB.items():
        rows = []
        for rel, off, new, old in edits:
            data = fs.raw(rel)
            got = struct.unpack_from("<i", data, off)[0]
            if got != old:
                raise SystemExit(f"{rel} @0x{off:x}: {got}, expected {old}")
            rows.append({"file": rel, "offset": off, "i32": new, "expect": old})
        for rel, idx, typ, sval in AINB_NODES[key]:
            a = Ainb(fs.raw(rel))
            nd = a.nodes[idx]
            if nd["name"] != typ or sval not in json.dumps(nd, default=str):
                raise SystemExit(f"{rel}: node {idx} is {nd['name']}, expected {typ} ({sval})")
        out[key] = rows
    return out


def _anchors(fs):
    out = {}
    for key, (level, name) in ANCHORS.items():
        found = []
        for side in ("Static", "Dynamic"):
            rel = f"Banc/{level}/{level}_{side}.bcett.byml.zs"
            for a in byml_load(fs.read(rel))[0].get("Actors", []):
                if a.get("Name") == name:
                    found.append((rel, a))
        if len(found) != 1 or found[0][1].get("Gyaml") != "DestinationAnchor":
            raise SystemExit(f"anchor {name}: {len(found)} placements in {level}")
        out[key] = {"name": name, "translate": [round(x, 3) for x in found[0][1]["Translate"]]}
    return out


def _text(fs, romfs):
    import msbt
    langs = []
    for lang in msbt.archives(romfs):
        files = msbt.read_archive(fs, lang)
        if TEXT_FILE not in files:
            raise SystemExit(f"{lang}: no {TEXT_FILE}")
        langs.append(lang)
    return {"file": TEXT_FILE, "languages": langs}


def main(romfs, vanilla=None):
    fs = Romfs(romfs, vanilla or os.path.join(HERE, "original"))
    out = {"_about": "Built by tools/rando/parity/_extras_story_build.py from the game files; read by "
                     "extras_story.py.",
           "hooks": {}, "entries": ENTRIES, "actors": {}}
    for base, steps in HOOKS.items():
        rel, versions = newest(romfs, base)
        if len(versions) != 1:
            raise SystemExit(f"{base}: {versions}: the plugin edits one version only, check the step names")
        fc = Evfl(fs.read(rel)).flowcharts[0]
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
        for ep, first in ENTRIES.get(base, {}).items():
            got = fc["events"][fc["entry_points"][ep]["main"]]["name"]
            if got != first:
                raise SystemExit(f"{base}: entry {ep} starts at {got}, expected {first}")
    out["gamedata"] = _flags(fs)
    out["placements"] = _placements(fs)
    out["ainb"] = _ainb(fs)
    out["anchors"] = _anchors(fs)
    out["text"] = _text(fs, romfs)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {OUT}: {sum(len(v['steps']) for v in out['hooks'].values())} hook steps, "
          f"{len(out['gamedata'])} flags, {len(out['placements'])} placements, "
          f"{sum(len(v) for v in out['ainb'].values())} AINB words, {len(out['text']['languages'])} languages")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(*sys.argv[1:])
