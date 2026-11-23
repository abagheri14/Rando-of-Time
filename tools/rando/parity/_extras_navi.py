"""Return with Navi (remake_navi_return, OOTRR's navi_return): press D-pad right and Navi offers a trip back, the way
the N64 game's save and quit put Link back at a dungeon's entrance, in Kokiri Forest (child) or at the Temple of
Time (adult). "dungeons": inside a dungeon only, back to its entrance. "everywhere": in the overworld too, home.

How it's wired (every node and row is checked against the vanilla files at plan time, and read back from the patch):
- D-pad right is Navi's. Sequence/NaviHintEvent.module.ainb asks for an event when you press it, but only while an
  area hint is registered (node 9, SeqQueryIsNaviAreaHint), and then it plays that hint (node 19's EventName, the
  hint's file name). The game never clears an area hint once it's registered, so node 9's "no area hint" case now
  goes the same way (node 21), and node 19 asks for our scene instead. So the area tutorial hints are gone (Navi's
  enemy hints while you target something stay as they were).
- Our scene is a new entry of Navi's own flow (NaviHint, ENTRY) on a reused scene ID (ROW, config/scene_rows.json,
  make_patch clears that row from its vanilla chest), set up as a Navi talk event like her tutorial hints
  (NaviFieldTalkEvent), so it can talk and change the map.
- The scene: nothing while a minigame timer runs (Dampe's race and the like), then the current map
  (Sequence_CurrentBanc). In a dungeon Navi asks whether to go back to its entrance; with "everywhere", in the
  overworld she asks about Kokiri Forest (child) or the Temple of Time (adult). Boss and miniboss arenas, the Chamber
  of Sages, the boss rush, the final battle and the tower collapse never ask. The answers are the game's own "Let's
  go!" / "Not yet..." (the Deku Tree's warp), with "Not yet..." picked at first so a stray A press does nothing.
  "Let's go!" leaves the game's safety section, stops and hides a minigame timer (what the game's own exits do),
  loads the map and changes to it at its start position.
- Logic: "dungeons" is what dying already does in our no-save-warp model. "everywhere" is OoTR's save warp:
  tools/rando/no_savewarp.py lets every region outside a boss room reach home.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FLOW = "NaviHint"
ENTRY = "Rando_NaviReturn"
ROW = "DodongoCavern_GetCompass"  # a scene ID of config/scene_rows.json that no other feature takes
ROW_FROM = "NaviHint_Field"  # its EventSetting row is copied from Navi's own field event's
COMPONENTS = "Work/Event/EventSetting/EventSettingComponentList/NaviFieldTalkEvent.engine__event__EventSettingComponentList.gyml"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
MSBT = "EventFlowMsg/NaviHint.msbt"
MSG = "EventFlowMsg/NaviHint:{}"
ANSWERS = (("9998", "EventFlowMsg/Get_StoneOfForest.msbt"), ("9999", "EventFlowMsg/Get_StoneOfForest.msbt"))
VOICE = "{tag:3,0,0f0100}{tag:4,0,09004e6f746963655f303000}"  # Navi's style and her "Notice_00" call
LABEL = {"dungeon": "Rando_NaviReturn_Dungeon", "child": "Rando_NaviReturn_Child", "adult": "Rando_NaviReturn_Adult"}
ASK = {"dungeon": "Want to head back to the entrance?",
       "child": "Want to head back to Kokiri Forest?",
       "adult": "Want to head back to the Temple of Time?"}
SEQ = "Sequence/NaviHintEvent.module.ainb"
AREA_SELECTOR, AREA_PATH, REQUEST = 9, 21, 19  # the area hint's BoolSelector, the D-pad path, its event request
DUNGEONS = (("InsideTheDekuTree", "Entrance"), ("DodongoCavern", "DodongoCavern_MountainTrailSide"),
            ("InsideJabuJabuBelly", "InsideJabuJabuBelly_FromZoraFountain"), ("ForestTemple", "ForestTemple"),
            ("FireTemple", "FireTemple"), ("WaterTemple", "WaterTemple_FromLakeHylia"), ("ShadowTemple", "Entrance"),
            ("SpiritTemple", "SpiritTemple_Entrance"), ("BottomOfTheWell", "Well_KakarikoSide"),
            ("IceCavern", "IceCavern_FromZoraFountain"),
            ("GerudoTrainingGround", "GerudoTrainingGround_FromGerudoFortress"), ("InsideGanonCastle", "Entrance"))
HOME = {"child": ("KokiriForest_Child", "EntrancePos"), "adult": ("Market_Adult", "LightPrelude")}
NEVER = ("BossRushIntervalRoom", "EnemyMuseum", "SageRoom", "FinalBattleField", "CrumblingGanonCastle")
TALK = {"IsWaitEnd": True, "IsCloseDialog": True, "EndDialogOption": 0, "ASName": "", "IsAnimeDriven": False,
        "IsPlayASAllSlot": False, "ChoiceNumber": 2, "ChoiceLabel1": 9998, "ChoiceLabel2": 9999, "ChoiceLabel3": 0,
        "ChoiceLabel4": 0, "ChoiceDefaultNo": 1, "ChoiceCancelNo": 1, "IsNotBecomeSpeaker": False,
        "ChangeMstxtForActor": False, "IsAnonymous": False, "NotPlayLipSyncAnim": False,
        "IsNotOpenIfSkipedMostRecent": False, "IsOverrideStyle": False, "OverrideStyle": 0,
        "MaintainPerformanceState": 0}


def _levels():
    return json.load(open(os.path.join(HERE, "data", "rando", "entrances_remake.json"), encoding="utf-8"))["level_paths"]


def overworld():
    """The levels "everywhere" offers home from: every level that isn't a dungeon, a boss or miniboss stage or one of
    NEVER (an allow-list, so a level we don't know never asks)."""
    dungeons = {d for d, _ in DUNGEONS}
    return sorted(n for n in _levels() if n not in dungeons and not n.endswith("Stage") and n not in NEVER
                  and not n.startswith("Demo_"))


def _is_map(name, yes, no):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
            "params": {"GameDataName": "Sequence_CurrentBanc", "Value": name, "Index": -1}, "cases": {1: yes, 0: no}}


def _trip(n, tag, ask, level, start, paths):
    """The question `ask` (a LABEL key) and the trip for one destination, starting at node "a<tag>"."""
    n[f"a{tag}"] = {"actor": "Npc_Navi", "action": "EventTalk", "next": f"q{tag}", "share": True,
                    "params": dict(TALK, MessageId=MSG.format(LABEL[ask]))}
    n[f"q{tag}"] = {"actor": "GameSystemActor", "query": "EventQueryTalkChoice2", "cases": {0: f"g{tag}", 1: None}}
    n[f"g{tag}"] = {"actor": "GameSystemActor", "action": "EventTriggerLeaveGameSafetySection", "next": f"s{tag}"}
    n[f"s{tag}"] = {"actor": "ChallengeSystemActor", "action": "EventTriggerMiniGameTimerStop", "new_actor": True,
                    "next": f"u{tag}"}
    n[f"u{tag}"] = {"actor": "ChallengeSystemActor", "action": "EventTriggerUnshowTimerUI", "new_actor": True,
                    "next": f"l{tag}"}
    n[f"l{tag}"] = {"actor": "GameSystemActor", "action": "EventTriggerBancRequestBeforehandLoad", "next": f"w{tag}",
                    "params": {"BancPath": paths[level], "IsTargetRetry": False}}
    n[f"w{tag}"] = {"actor": "GameSystemActor", "action": "EventReserveBancChange", "next": None,
                    "params": {"IsWaitEnd": True, "IsStartOnEvent": False, "NextStartPos": start, "NextBanc": level,
                               "BootEventName": "", "FadePattern": 2, "EventStarterName": "", "IsItemWarp": False,
                               "NextPosition": [0.0, 0.0, 0.0], "NextStartRot": [0.0, 0.0, 0.0]}}


def graph(mode):
    """(nodes, start) of the scene for "dungeons" or "everywhere"."""
    paths = _levels()
    n = {"t": {"actor": "ChallengeSystemActor", "query": "EventQueryMiniGameTimerIsCounting", "new_actor": True,
               "cases": {1: None, 0: "d0"}}}
    after = "o0" if mode == "everywhere" else None
    for i, (level, start) in enumerate(DUNGEONS):
        n[f"d{i}"] = _is_map(level, f"a{i}", f"d{i + 1}" if i + 1 < len(DUNGEONS) else after)
        _trip(n, str(i), "dungeon", level, start, paths)
    if mode == "everywhere":
        names = overworld()
        for k, level in enumerate(names):
            n[f"o{k}"] = _is_map(level, "age", f"o{k + 1}" if k + 1 < len(names) else None)
        n["age"] = {"actor": "Player_Event", "query": "EventQueryPlayerIsChild", "cases": {1: "achild", 0: "aadult"}}
        for age, (level, start) in HOME.items():
            _trip(n, age, age, level, start, paths)
    return n, "t"


def plan(mode):
    """Plan sections and the read-back record for remake_navi_return "dungeons" or "everywhere"."""
    nodes, start = graph(mode)
    asks = ["dungeon"] + (["child", "adult"] if mode == "everywhere" else [])
    text = [{"lang": "*", "file": MSBT, "label": LABEL[a], "add": True, "markup": VOICE + ASK[a],
             "note": "remake_navi_return"} for a in asks]
    text += [{"lang": "*", "file": MSBT, "label": label, "add": True, "copy_from": {"file": src, "label": label},
              "note": "remake_navi_return"} for label, src in ANSWERS]
    return {
        "events": [{"file": FLOW, "flowchart": FLOW, "add_graph": ENTRY, "nodes": nodes, "start": start}],
        "byml": [{"file": EVENT_SETTING, "replace_row": {"row": ROW, "copy_of": ROW_FROM, "set": {
            "EntryPointName": ENTRY, "EventSettingComponentList": COMPONENTS}}}],
        "ainb": [{"file": SEQ, "edits": [
            {"set_child": {"parent": AREA_SELECTOR, "which": "False", "child": AREA_PATH}},
            {"cut": {"node": REQUEST, "input": "EventName", "value": ROW}}]}],
        "text": text,
    }, {"mode": mode, "row": ROW, "entry": ENTRY, "asks": [LABEL[a] for a in asks],
        "dungeons": [list(d) for d in DUNGEONS], "overworld": overworld() if mode == "everywhere" else []}


def check_sources(romfs):
    """[problem] where the vanilla files aren't as this module expects (run at plan time)."""
    import ainb
    from romtools import Romfs, byml_load
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    bad = []
    a = ainb.Ainb(fs.raw(SEQ))
    names = [nd["name"] or ainb.NODE_TYPES.get(nd["type"], "") for nd in a.nodes]  # BoolSelector & co. go by type
    want = {AREA_SELECTOR: "BoolSelector", AREA_PATH: "BoolSelector", REQUEST: "SeqOneShotRequestEvent",
            10: "SeqQueryIsNaviAreaHint"}
    for i, nm in want.items():
        if i >= len(names) or names[i] != nm:
            bad.append(f"{SEQ}: node {i} is {names[i] if i < len(names) else 'missing'}, not {nm}")
    rows = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING), allow_big=True)[0]}
    if ROW not in rows or ROW_FROM not in rows:
        bad.append(f"{EVENT_SETTING}: no row {ROW} or {ROW_FROM}")
    rows_cfg = json.load(open(os.path.join(HERE, "config", "scene_rows.json"), encoding="utf-8"))["rows"]
    if ROW not in rows_cfg:
        bad.append(f"{ROW} is not a free row of config/scene_rows.json")
    fc = Evfl(fs.read("Event/EventFlow/NaviHint.bfevfl.zs")).flowcharts[0]
    if ENTRY in fc["entry_points"]:
        bad.append(f"{FLOW} already has an entry {ENTRY}")
    return bad


def verify(patch, rb, romfs):
    """[problem]: the scene, its row, the D-pad sequence and the texts, read back from a built patch."""
    import ainb
    import msbt
    from romtools import Romfs, byml_load, sarc_files
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    fc = Evfl(fs.read("Event/EventFlow/NaviHint.bfevfl.zs")).flowcharts[0]
    if rb["entry"] not in fc["entry_points"]:
        return [f"{FLOW}: no entry {rb['entry']}"]
    steps = {e["name"]: e for e in fc["events"] if e["name"].startswith(rb["entry"] + "_")}
    acts = [(fc["actors"][e["actor"]]["name"], fc["actors"][e["actor"]]["actions"][e["action"]] if e["type"] == "action"
             else fc["actors"][e["actor"]]["queries"][e["query"]]) for e in steps.values() if e.get("actor") is not None]
    changes = [e for e in steps.values() if e["type"] == "action"
               and fc["actors"][e["actor"]]["actions"][e["action"]] == "EventReserveBancChange"]
    want_trips = len(rb["dungeons"]) + (2 if rb["mode"] == "everywhere" else 0)
    if len(changes) != want_trips:
        bad.append(f"{FLOW}:{rb['entry']}: {len(changes)} map changes, planned {want_trips}")
    for level, start in rb["dungeons"]:
        if not any(((e.get("params") or {}).get("items") or {}).get("NextBanc", {}).get("value") == level and
                   ((e.get("params") or {}).get("items") or {}).get("NextStartPos", {}).get("value") == start
                   for e in changes):
            bad.append(f"{FLOW}:{rb['entry']}: no trip to {level} {start}")
    if ("ChallengeSystemActor", "EventQueryMiniGameTimerIsCounting") not in acts:
        bad.append(f"{FLOW}:{rb['entry']}: no minigame timer check")
    rows = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING), allow_big=True)[0]}
    r = rows.get(rb["row"]) or {}
    if r.get("EntryPointName") != rb["entry"] or not str(r.get("FlowchartFileName", "")).endswith("/NaviHint.evfc") \
            or r.get("EventSettingComponentList") != COMPONENTS:
        bad.append(f"{EVENT_SETTING}: {rb['row']} is {r.get('FlowchartFileName')}:{r.get('EntryPointName')} "
                   f"({r.get('EventSettingComponentList')})")
    a = ainb.Ainb(fs.raw(SEQ))
    sel = a.nodes[AREA_SELECTOR]
    false_to = [pl["node"] for pl in sel["plugs"][ainb.PLUG_CHILD] if pl.get("name") == "False"]
    if false_to != [AREA_PATH]:
        bad.append(f"{SEQ}: node {AREA_SELECTOR}'s False case goes to {false_to}, planned {AREA_PATH}")
    t, e = a._input(REQUEST, "EventName")
    if e["node"] >= 0 or e["value"] != rb["row"]:
        bad.append(f"{SEQ}: node {REQUEST} asks for {e['value']!r} (fed by node {e['node']}), planned {rb['row']}")
    for lang, rel in msbt.archives(romfs).items():
        m = msbt.Msbt(sarc_files(fs.read(rel))[MSBT])
        missing = [lab for lab in rb["asks"] + [x for x, _ in ANSWERS] if lab not in m]
        if missing:
            bad.append(f"{rel}: {MSBT} lacks {missing}")
    return bad
