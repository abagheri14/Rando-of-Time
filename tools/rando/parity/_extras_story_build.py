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
- intros: the area intros remake_skip_area_intros skips (INTRO_NEW_FILE, INTRO_EDITS), each checked to only show
  things, and what each skip keeps or would lose
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
import progressive  # noqa: E402

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

# Skip area intros: the first-visit scenes that only show a place (camera, the place's name, Navi, sound) and keep
# nothing. Each one opens its place's name (UISystemActor.EventTriggerOpenLocationUI), which is what marks the place
# visited (IsVisitLocation.<place>; Lake Hylia's owl waits for it, HyruleField_LakeHylia_Child_Prefab). The place's
# LocationArea leaves that to the intro: it opens the name only once the place is visited when the Location table
# says IsShowLocationUIFirstTimeInDemo (AI/LocationArea.root). So a skipped intro's place has that switched off and
# shows its name, and gets marked visited, when you get there, like a place without an intro; an edited arrival sets
# the visit itself.
# INTRO_NEW_FILE: nothing else hangs on what plays them, so a new file starts with them played. They play straight
# from a level doorway's InitEventName (Kakariko, Gerudo Fortress, the graveyard, the castle grounds, the Fire and
# Spirit Temples, the well, Zora's River), from an area's EventRequestActor that waits for the played flag (Gerudo
# Valley, the Water Temple), or from an arrival entry of Dm_SY_BancChangeArrive (INTRO_SITES) that does nothing
# else, or whose intro step leads on to the same steps as its plain arrival. Lake Hylia's three (0000 from the
# field, 0003 and 0005 from the valley and Zora's Domain) all wait for InitDemo_LakeHylia, which 0000 played makes
# true. Left out: Dodongo's Cavern (once its intro counts as played, Gimmick_DodongoCavern_FirstDemo deletes the
# bombable wall at the entrance) and the intros that move a quest or set something in their own scene (Temple of
# Time, the Forest and Water Temples' first rooms, Hyrule Field, Lon Lon Ranch, the Lost Woods, Zora's River's owl,
# Ganon's tower barrier, Darunia's room, Sacred Forest Meadow's Moblin).
INTRO_NEW_FILE = ("Dm_Kakariko_0000", "Dm_Gerudo_0000", "Dm_Graveyard_0000", "Dm_HrlCastle_0000", "Dm_LakeHrl_0000",
                  "Goto_FireTemple", "Goto_KakarikoWells", "Goto_SpritTemple", "Goto_ZoraRiver",
                  "Dm_GerudoValley_0000", "Goto_WaterTemple", "Dm_GanonCastle_0000", "Goto_IceCave",
                  "Goto_SacredForest", "Goto_ShadowTemple")
# INTRO_EDITS: the arrival entry that plays the intro does more after it (a quest step, Navi, a flag), and a played
# flag would skip the whole entry. So its step into the intro goes to the plain arrival instead (EventTransition to
# Dm_SY_BancChangeArrive, what every later arrival plays), then sets the intro played and the place visited.
# {intro: (entry, step)}
INTRO_EDITS = {
    "Dm_DeathMtTrail_0000": ("DeathMountainTrail_Arrive", "Event36"),          # then Get_StoneOfFire DeathMtTrailNpc
    "Dm_Goron_0000": ("GoronCity_InitDemo_Arrive", "Event30"),                 # then Get_StoneOfFire ArriveCity
    "Dm_DeathMtCrater_0000_FromTop": ("GoTo_DeathMountainCrater", "Event227"),  # then Navi on the heat, a flag
    "Dm_DeathMtCrater_0000": ("GoTo_DeathMountainCrater_FromGoronCity", "Event248"),
    "Dm_ZoraFountain_0000": ("FromZoraDomain_arriveZoraFountain", "Event300"),  # then Navi's balloon
    "Dm_HrlCastle_0005": ("Dm_SY_BancChangeArrive_Market", "Event200"),         # then Goto_HyruleCastle Step02_01
    "Dm_DesertColossus_0000": ("FromWasteland_ArriveColossus", "Event82"),      # then SageOfSpirit Step04
    "Dm_Zora_0000": ("Goto_ZoraDomain", "Event48"),                             # then Get_StoneOfWater Step03
    "Dm_Deku_0000": ("InsideTheDekuTree_Arrive", "Event9"),                     # then Navi's tutorial, MeetBoss
    "Goto_GerudoTrainingGround": ("FromGerudoFortress_ArriveTrainingGround", "Event182"),  # then SubEvent_GetIceArrow
}
# the NEW_FILE intros an arrival entry plays: {intro: its step}
INTRO_SITES = {"Dm_LakeHrl_0000": "Event142", "Dm_GanonCastle_0000": "Event98", "Goto_IceCave": "Event224",
               "Goto_SacredForest": "Event20", "Goto_ShadowTemple": "Event293"}
ARRIVE = "Dm_SY_BancChangeArrive"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
LOCATIONS = "RSDB/Location.Product.111.rstbl.byml.zs"
# what an intro may do: show things and move people for the camera, nothing kept
INTRO_ACTORS = ("EventCamera", "Player_Event", "Npc_", "Animal_", "UISystemActor", "SoundSystemActor",
                "PostProcessingActor", "DevelopEventSystemActor", "Dm_Locator", "CameraXLinkControl",
                "EventEffectEmitter", "TerrainSystemActor", "EventWorldManagerController")
INTRO_ACTIONS = {"EventSystemActor": ("EventWait",),
                 "GameSystemActor": ("EventWait", "EventTriggerControllerRumble",
                                     "EventTriggerAddPreComputedCullingBasePos",
                                     "EventTriggerPreComputedCullingDisableUntilEventEnd")}
INTRO_CALLS = ("Common_Camera_Pln:", "NaviEventCommon:NaviWarp_PlayerHomePos_Choice")
# what an arrival entry may do before its intro step (a played flag skips these too)
ARRIVE_LEAD = ("Player_Event.EventTriggerParticipateEvent",
               "EventCamera.EventTriggerSendReserveCameraResetMessageToPlayerCamera")


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


def _reach(fc, starts):
    """Indexes of every step reachable from `starts` (next, switch cases, forks, joins)."""
    seen, todo = set(), list(starts)
    while todo:
        i = todo.pop()
        if i is None or i in seen or i >= len(fc["events"]):
            continue
        seen.add(i)
        e = fc["events"][i]
        todo += [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])] + list(e.get("forks", []))
    return seen


def _call(fc, e):
    if e["type"] == "subflow":
        return f"{e.get('flowchart', '')}:{e.get('entry_point', '')}"
    if e["type"] in ("action", "switch"):
        a = fc["actors"][e["actor"]]
        return f"{a['name']}.{a['actions'][e['action']] if e['type'] == 'action' else a['queries'][e['query']]}"
    return None


def _intro_scene(fs, romfs, rows, intro):
    """(flow, places) of an intro: it must only show things (INTRO_ACTORS...), and it names at least one place."""
    from parity._story_build import flat
    row = rows.get(intro)
    if row is None:
        raise SystemExit(f"intro {intro}: not in the scenes table")
    flow = os.path.basename(str(row.get("FlowchartFileName", ""))).split(".")[0]
    rel, versions = newest(romfs, flow)
    if len(versions) != 1:
        raise SystemExit(f"intro {intro}: {versions}: one version only")
    fc = Evfl(fs.read(rel)).flowcharts[0]
    eps = fc["entry_points"]
    ep = row.get("EntryPointName") or ("EntryPoint0" if "EntryPoint0" in eps or len(eps) != 1 else next(iter(eps)))
    if ep not in eps:
        raise SystemExit(f"intro {intro}: {flow} has no entry {ep}")
    steps, todo, done = set(), [ep], set()
    while todo:
        name = todo.pop()
        if name in done:
            continue
        done.add(name)
        for i in _reach(fc, [eps[name]["main"]] + list(eps[name].get("sub_flow_events", []))):
            steps.add(i)
            e = fc["events"][i]
            if e["type"] == "subflow" and not e.get("flowchart"):
                todo.append(e["entry_point"])
    places = set()
    for i in sorted(steps):
        e, c = fc["events"][i], _call(fc, fc["events"][i])
        if c is None or e["type"] == "switch" or (e["type"] == "subflow" and not e.get("flowchart")):
            continue
        actor, _, act = c.partition(".")
        actor = actor.split("[")[0]
        ok = (c.startswith(INTRO_CALLS) if e["type"] == "subflow" else
              actor.startswith(INTRO_ACTORS) or act in INTRO_ACTIONS.get(actor, ()))
        if not ok:
            raise SystemExit(f"intro {intro}: {flow} {e['name']} {c} may keep something")
        if c == "UISystemActor.EventTriggerOpenLocationUI":
            places.add(os.path.basename(str(flat(e.get("params"), {}).get("LocationName", ""))).split(".")[0])
    if not places or "" in places:
        raise SystemExit(f"intro {intro}: {flow} names no place ({places})")
    return flow, sorted(places)


def _intros(fs, romfs):
    from parity._story_build import flat
    rows = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING), allow_big=True)[0]}
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    bools = {e["Hash"]: e for e in gd["Data"]["Bool"]}

    def false_bool(name):
        if bools.get(murmur3_32(name), {}).get("DefaultValue") is not False:
            raise SystemExit(f"intros: {name} is not a Bool that starts false")
        return name

    rel, versions = newest(romfs, ARRIVE)
    if len(versions) != 1:
        raise SystemExit(f"{ARRIVE}: {versions}: one version only")
    fc = Evfl(fs.read(rel)).flowcharts[0]
    by = {e["name"]: e for e in fc["events"]}
    skipped = set(INTRO_NEW_FILE) | set(INTRO_EDITS)
    # every step of the arrival file that plays one of them is one we know
    sites = {}
    for e in fc["events"]:
        if _call(fc, e) == "EventSystemActor.EventTransition":
            name = flat(e.get("params"), {}).get("EventName")
            if name in skipped:
                sites.setdefault(name, []).append(e["name"])
    want = {k: [v] for k, v in INTRO_SITES.items()}
    want.update({k: [v[1]] for k, v in INTRO_EDITS.items()})
    if sites != want:
        raise SystemExit(f"intros: {ARRIVE} plays them at {sites}, expected {want}")

    def lost(step):
        """Steps a played intro would skip: before the intro step of an entry (when the entry is a doorway's
        InitEventName, a played flag skips all of it) or, past a switch on the played flag, the intro side's steps
        that the plain side doesn't reach."""
        e = by[step]
        preds = progressive.predecessors(fc, e)
        cases = [p for p in preds if p[0] == "case"]
        if cases:
            (_, sw, k), = cases
            other = [c["next"] for j, c in enumerate(by[sw]["cases"]) if j != k]
            return sorted(fc["events"][i]["name"] for i in _reach(fc, [e.get("next")]) - _reach(fc, other))
        out, cur = [], e
        while True:
            p = progressive.predecessors(fc, cur)
            if len(p) != 1:
                raise SystemExit(f"intros: {ARRIVE} {cur['name']} has {p}")
            if p[0][0] == "entry":
                break
            cur = by[p[0][1]]
            if _call(fc, cur) not in ARRIVE_LEAD:
                out.append(cur["name"])
        return out + sorted(fc["events"][i]["name"] for i in _reach(fc, [e.get("next")]))

    locs = {r["__RowId"]: r for r in byml_load(fs.read(LOCATIONS), allow_big=True)[0]}

    def location(place):
        row = f"Work/Location/{place}.game__location__Location.gyml"
        if locs.get(row, {}).get("IsShowLocationUIFirstTimeInDemo") is not True:
            raise SystemExit(f"intros: {LOCATIONS} {row} doesn't leave its first name to an intro")
        return row
    out = {"new_file": [], "edits": [], "flowchart": fc["name"], "arrive": ARRIVE, "locations": LOCATIONS}
    for intro in INTRO_NEW_FILE:
        flow, places = _intro_scene(fs, romfs, rows, intro)
        if intro in INTRO_SITES and lost(INTRO_SITES[intro]):
            raise SystemExit(f"intros: a played {intro} would skip {lost(INTRO_SITES[intro])} in {ARRIVE}")
        out["new_file"].append({"intro": intro, "flow": flow, "played": false_bool(f"HavePlayedEvent.{intro}"),
                                "rows": [location(p) for p in places]})
    for intro, (entry, step) in INTRO_EDITS.items():
        flow, places = _intro_scene(fs, romfs, rows, intro)
        e = by[step]
        if step not in {fc["events"][i]["name"] for i in _reach(fc, [fc["entry_points"][entry]["main"]])}:
            raise SystemExit(f"intros: {entry} doesn't reach {step}")
        keeps = lost(step)
        if not keeps:
            raise SystemExit(f"intros: nothing hangs on {intro}'s step in {entry}: make it a NEW_FILE one")
        info = step_info(fc, e)
        out["edits"].append({"intro": intro, "flow": flow, "entry": entry, "step": step, "next": info["next"],
                             "preds": info["preds"], "params": info["params"], "keeps": keeps,
                             "played": false_bool(f"HavePlayedEvent.{intro}"),
                             "visit": [false_bool(f"IsVisitLocation.{p}") for p in places]})
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
    out["intros"] = _intros(fs, romfs)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {OUT}: {sum(len(v['steps']) for v in out['hooks'].values())} hook steps, "
          f"{len(out['gamedata'])} flags, {len(out['placements'])} placements, "
          f"{sum(len(v) for v in out['ainb'].values())} AINB words, {len(out['text']['languages'])} languages, "
          f"{len(out['intros']['new_file'])} + {len(out['intros']['edits'])} area intros")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(*sys.argv[1:])
