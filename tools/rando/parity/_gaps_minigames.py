"""Minigame and dungeon-NPC settings, owned by the story plugin. The research is in my note dampe_epona_ruto.md and
it's summarised here. None of this has been seen in-game yet (UNTESTED lists it for seed.json).

skip_some_minigame_phases
In OoTR, Dampe starts with the second race, one run under a minute gives both prizes, and the first prize comes at
any time. Horseback archery gives both prizes from the first try.
  - Horseback archery needs nothing. Minigame_HorsebackArchery:MiniGame_HorsebackArchery_FinishRetry already gives
    the heart piece and the quiver together on a first score of 1400+ (Event11 -> Event119 + Event110).
  - Dampe's race: the four goal chests share one spot and one state (Minigame_DampeRace_TreasureBoxState, read by
    Logic/UnderTheGrave_Prefab_6971), so the two prizes come one after the other. The edits are routing in
    MiniGame_DampeRace and the chests plugin makes them (parity/_chests_dampe.py event_ops(skip_phases=True), which
    chests.py calls with this setting). Every race is the second race, the timed course the 1:00 target was made
    for. The first-prize chest is offered after any finish, opening it within 1:00.000 brings the heart-piece chest
    right away, and talking to Dampe again does the same if that didn't happen. This module checks the chests plugin
    is on and reads every edit back. OoTR's logic doesn't change with the setting, and neither does the remake's.

no_epona_race (stricter than OoTR, one ranch visit)
In OoTR the adult calls Epona with her song without racing Ingo.
  - In the remake the owned horse is engine state, and only Animal_Epona_Adult.EventCopyAndRegisterOwnedHorse
    creates it. That runs on the ranch's Epona (HyruleField_Adult_Static #13923248577548723172, Presence NOT
    Get_Epona_IsCompleted_Exp) in the four Get_Epona:Sub_Get_Epona_EscapeRanch_*_Warp entries after the race.
    Epona's Song (Dm_SY_Ocarina_EponaSong:EponaSong Event1 EventQueryHasOwnedHorse) only calls an owned horse.
  - So when the adult plays Epona's Song with no owned horse (Event1's "no" case), it first checks that Get_Epona
    isn't Complete and that the ranch Epona is within CALL_RANGE of the player
    (GameSystemActor.EventQueryIsDistanceBetweenActorsClose). Then it calls the new Get_Epona:Rando_RegisterEpona,
    which is exact copies of the escape's steps: CopyAndRegisterOwnedHorse (Event202), GoOffstageForUser
    (Event201), Get_Epona -> Complete (Event200) and Skullchild_JustAfterGetEpona (Event210). After that it goes on
    to Event5, the song's normal "call the owned horse" path. Anywhere else, or once Complete, the song is unchanged.
  - Story steps go backwards (IsIgnoreCompletedChallenge false). The child's lesson Dm_MelodyGet_Epona Event82
    (AfterGetEponaSong) and adult Malon's "about Epona" answer Npc_Hylia_Malon_Adult Event86 (AfterTalkMalon) get
    skipped once Get_Epona is Complete, or the ranch Epona and the race would come back. The skip is a guard on the
    story plugin's Plan (hooks() below, story.Plan.guard), like the order guard _story_traps puts on the same two
    steps. The Plan chains every guard of a step in front of it (Event81 -> guards -> Event82, Event178 case 0 ->
    guards -> Event86).
    Don't make it a separate graph rerouted in world_plan. world_plan runs after the Plan is assembled, so the
    reroute takes the predecessor edge from the order guard and leaves it orphaned in every no_epona_race seed.
  - Logic (data/rando/logic/story.json, helper can_ride_epona): OoTR precollects its Epona event at the start
    (ItemPool.py) and this module has no hook before the fill. So with the setting on, the helper stops reading that
    event and asks for at('Lon Lon Ranch', is_adult and can_play(Eponas_Song) and at_day) instead, which is OoTR's
    Lon Lon Ranch Epona rule without the race. With the setting off the helper folds back to OoTR's. The
    precollected event stays in OoTR's state, but nothing reads it any more except "Links Cow", and that's a Lon Lon
    Ranch rule with the same song/adult/day conditions anyway. It's stricter than OoTR because the generator needs
    one daytime ranch visit with the song before any Epona location.

ruto_already_f1_jabu
In OoTR Ruto waits on the top floor of Jabu-Jabu's Belly instead of the basement.
  - After the meeting scene, Get_StoneOfWater:StoneOfWater_MeetRuto Event88 warps Ruto with
    EventAIScheduleWarpToAnchor AnchorType 2, her linked AnchorAction2 (7.5, 81.8, -82.8, the floor below room 2).
    Her Step10 schedule (Pack/AIScheduleParam.pack.zs, Get_StoneOfWater_Step10_Npc_Zora_Ruto_Child_001_Step1) keeps
    her at ActionType "Action2". AnchorType N is the NPC's linked AnchorActionN (Dampe's AnchorType 2 is his goal
    anchor, and ActionType hashes are murmur3 "Action1".."Action4").
  - Both become 1. AnchorAction1 (2.6, 91.0, -73.4) is on the top floor of room 2, 2.5 units from where Link stands
    after the scene (After_MeetRuto), away from the floor holes. The talk ("carry me?" -> LiftUp_Ruto -> Step11) is
    unchanged. Step11 turns on Ruto's spawn-position save, which would still hold (0,0,0) if we set it at the
    meeting. No logic change (OoTR's logic doesn't model Ruto).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()

OWNS = {"skip_some_minigame_phases": (False, True), "no_epona_race": (False, True),
        "ruto_already_f1_jabu": (False, True)}
READERS = {"dampe_skip": "verify_dampe", "no_epona_race": "verify_epona", "ruto_f1": "verify_ruto"}
PARITY_NOTE = {
    "no_epona_race": "Epona registered by her song at the ranch (logic: one daytime ranch visit, stricter than "
                     "OoTR); OoTR's exact variant (owned from a new file) isn't tested in game yet",
}

# Dampe (edits: parity/_chests_dampe.py)
DAMPE = "MiniGame_DampeRace"

# Epona
SONG = "Dm_SY_Ocarina_EponaSong"
SONG_GRAPH = "Rando_NoEponaRace"
EPONA = "Get_Epona"
REGISTER = "Rando_RegisterEpona"
CALL_RANGE = 60.0  # the corral is about 60 x 40 around the ranch Epona's spot (-100.5, 150.6, 264.5)
COMPLETE = "Get_Epona_IsCompleted_Exp"
# the escape's steps copied into Rando_RegisterEpona: (label, step, actor.action)
REGISTER_STEPS = (("reg", "Event202", "Animal_Epona_Adult.EventCopyAndRegisterOwnedHorse"),
                  ("off", "Event201", "Animal_Epona_Adult.EventGoOffstageForUser"),
                  ("done", "Event200", "ChallengeSystemActor.EventExecuteProgressChallengeStep"),
                  ("flag", "Event210", "GameDataActor.EventTriggerSetGameDataBool"))
# Steps that can rewind Get_Epona once it's complete: (file, step, StepName of the action)
KEEP_COMPLETE = (("Dm_MelodyGet_Epona", "Event82", "AfterGetEponaSong"),
                 ("Npc_Hylia_Malon_Adult", "Event86", "AfterTalkMalon"))
DISTANCE = {"ActorNameA": "Player_Event", "InstanceNameA": "", "IsAnchorActorA": False,
            "ActorNameB": "Animal_Epona_Adult", "InstanceNameB": "", "IsAnchorActorB": False,
            "CheckDistance": CALL_RANGE, "IsTargetPlayingAllEvent": False}  # as Dampe's Event333 sets them

# Ruto
RUTO_FILE = "Get_StoneOfWater"
RUTO_STEP = "Event88"
RUTO_ANCHOR = 1  # vanilla 2
RUTO_PACK = "Pack/AIScheduleParam.pack.zs"
RUTO_SCHEDULE = ("Component/AIScheduleParam/Get_StoneOfWater_Step10_Npc_Zora_Ruto_Child_001_Step1"
                 ".game__component__AIScheduleParam.bgyml")
RUTO_PATH = "DefaultSchedule.ActionSchedule.0.ActionType"
ACTION1, ACTION2 = 4013411249, 3610578669  # murmur3("Action1"), murmur3("Action2")


def _fs(romfs=None, patch=None):
    from romtools import Romfs
    return Romfs(romfs or DEFAULT_ROMFS, os.path.join(HERE, "original"), [patch] if patch else [])


def _flow(fs, name):
    """The first flowchart of the newest version of an event file (Name.110.bfevfl.zs over Name.bfevfl.zs)."""
    import re
    from evfl import Evfl
    d = os.path.join(fs.root if hasattr(fs, "root") else DEFAULT_ROMFS, "Event", "EventFlow")
    pat = re.compile(re.escape(name) + r"(?:\.(\d{3}))?\.bfevfl\.zs$")
    try:
        cands = sorted((int(m.group(1) or -1), f) for f in os.listdir(d) for m in [pat.match(f)] if m)
        rel = "Event/EventFlow/" + cands[-1][1]
    except (OSError, IndexError):
        rel = f"Event/EventFlow/{name}.bfevfl.zs"
    return Evfl(fs.read(rel)).flowcharts[0]


def _member(fc, e):
    if e["type"] == "subflow":
        return f"{e.get('flowchart') or ''}:{e.get('entry_point')}"
    if "actor" not in e:
        return e["type"]
    a = fc["actors"][e["actor"]]
    if e["type"] == "action":
        return f"{a['name']}.{a['actions'][e['action']]}"
    if e["type"] == "switch":
        return f"{a['name']}.{a['queries'][e['query']]}"
    return e["type"]


def _param(e, key):
    v = ((e.get("params") or {}).get("items") or {}).get(key)
    return v.get("value") if isinstance(v, dict) else v


def _name(fc, i):
    return None if i == 0xFFFF else fc["events"][i]["name"]


def _case_index(e, value):
    return next(k for k, c in enumerate(e["cases"]) if c["value"] == value)


# Plan
def epona_plan(fs):
    song = _flow(fs, SONG)
    by = {e["name"]: e for e in song["events"]}
    ask = by["Event1"]
    if _member(song, ask) != "GameSystemActor.EventQueryHasOwnedHorse" or \
            {c["value"]: _name(song, c["next"]) for c in ask["cases"]} != {0: "Event5", 1: "Event23"}:
        raise RuntimeError(f"{SONG}: Event1 is no longer 'owned horse? Event5 : Event23' (game update?)")
    epona = _flow(fs, EPONA)
    eby = {e["name"]: e for e in epona["events"]}
    for _, step, member in REGISTER_STEPS:
        if step not in eby or _member(epona, eby[step]) != member:
            raise RuntimeError(f"{EPONA}: {step} is no longer {member} (game update?)")
    if _param(eby["Event200"], "StepName") != "Complete" or _param(eby["Event200"], "ChallengeName") != "Get_Epona" \
            or _param(eby["Event210"], "GameDataName") != "Skullchild_JustAfterGetEpona":
        raise RuntimeError(f"{EPONA}: Event200/Event210 changed (game update?)")
    events = [
        {"file": SONG, "flowchart": SONG, "add_graph": SONG_GRAPH, "start": "a", "nodes": {
            "a": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                  "params": {"GameDataName": COMPLETE}, "cases": {0: "@Event23", 1: "b"}},
            "b": {"actor": "GameSystemActor", "query": "EventQueryIsDistanceBetweenActorsClose",
                  "params": dict(DISTANCE), "cases": {0: "c", 1: "@Event23"}},
            "c": {"call": f"{EPONA}:{REGISTER}", "next": "@Event5"}}},
        {"file": SONG, "flowchart": SONG, "event": "Event1", "case": _case_index(ask, 1), "next": f"{SONG_GRAPH}_a"},
    ]
    labels = [lab for lab, _, _ in REGISTER_STEPS]
    events.append({"file": EPONA, "flowchart": EPONA, "add_graph": REGISTER, "start": labels[0], "nodes": {
        lab: {"copy": step, "next": (labels[i + 1] if i + 1 < len(labels) else None)}
        for i, (lab, step, _) in enumerate(REGISTER_STEPS)}})
    keep = []
    for file, step, name in KEEP_COMPLETE:
        fc = _flow(fs, file)
        ev = next(e for e in fc["events"] if e["name"] == step)
        if _member(fc, ev) != "ChallengeSystemActor.EventExecuteProgressChallengeStep" or \
                _param(ev, "ChallengeName") != "Get_Epona" or _param(ev, "StepName") != name:
            raise RuntimeError(f"{file}: {step} no longer sets Get_Epona {name} (game update?)")
        after = _name(fc, ev["next"])
        from parity import story
        if story._step(file, step)["next"] != after:  # the guard skips to the step the story data knows as next
            raise RuntimeError(f"{file}: {step} goes on to {after}, data/rando/story_data.json says "
                               f"{story._step(file, step)['next']} (run _story_build.py)")
        keep.append([file, step, after])  # the guard itself is in hooks()
    note = {"song": [SONG, "Event1", SONG_GRAPH], "register": [EPONA, REGISTER, [s for _, s, _ in REGISTER_STEPS]],
            "keep": keep, "range": CALL_RANGE}
    return events, note


def hooks(p, settings, world):
    """no_epona_race's keep-complete guards, put on the story plugin's Plan. story.world_plan calls this before it
    assembles, so they chain with any other guard on the same steps (_story_traps' order guards)."""
    ws = getattr(world, "settings", settings)
    if getattr(ws, "no_epona_race", False):
        for file, step, _ in KEEP_COMPLETE:
            p.guard(file, step, COMPLETE)


def ruto_plan(fs):
    from romtools import byml_load, sarc_files
    fc = _flow(fs, RUTO_FILE)
    ev = next(e for e in fc["events"] if e["name"] == RUTO_STEP)
    if _member(fc, ev) != "Npc_Zora_Ruto_Child_001.EventAIScheduleWarpToAnchor" or _param(ev, "AnchorType") != 2:
        raise RuntimeError(f"{RUTO_FILE}: {RUTO_STEP} is no longer Ruto's AnchorType 2 warp (game update?)")
    sched = byml_load(sarc_files(fs.read(RUTO_PACK))[RUTO_SCHEDULE], allow_big=True)[0]
    if int(sched["DefaultSchedule"]["ActionSchedule"][0]["ActionType"]) != ACTION2:
        raise RuntimeError(f"{RUTO_SCHEDULE}: Ruto's Step10 action is no longer Action2 (game update?)")
    events = [{"file": RUTO_FILE, "flowchart": RUTO_FILE, "event": RUTO_STEP, "param": "AnchorType",
               "value": RUTO_ANCHOR}]
    packs = [{"pack": RUTO_PACK, "file": RUTO_SCHEDULE, "set": {RUTO_PATH: ACTION1}}]
    return events, packs, {"warp": [RUTO_FILE, RUTO_STEP, RUTO_ANCHOR], "schedule": [RUTO_PACK, RUTO_SCHEDULE, ACTION1]}


def world_plan(settings, world):
    """This module's plan sections for the seed's settings ({} when none applies)."""
    ws = getattr(world, "settings", settings)
    events, packs, gaps = [], [], {}
    if getattr(ws, "skip_some_minigame_phases", False):
        import generate
        if "chests" not in generate.enabled_plugins():
            raise ValueError("skip_some_minigame_phases: Dampe's race edits are made by the chests plugin "
                             "(parity/_chests_dampe.py), which is not enabled")
        from parity import _chests_dampe as dampe
        gaps["dampe_skip"] = {"file": DAMPE, "graphs": ["Rando_DampeStart"] + list(dampe.SKIP_GRAPHS)}
    fs = None
    if getattr(ws, "no_epona_race", False):
        fs = fs or _fs()
        ev, note = epona_plan(fs)
        events += ev
        gaps["no_epona_race"] = note
    if getattr(ws, "ruto_already_f1_jabu", False):
        fs = fs or _fs()
        ev, pk, note = ruto_plan(fs)
        events += ev
        packs += pk
        gaps["ruto_f1"] = note
    out = {}
    if events:
        out["events"] = events
    if packs:
        out["packs"] = packs
    if gaps:
        out["_gaps"] = gaps
    return out


def UNTESTED(settings):
    out = []
    if getattr(settings, "skip_some_minigame_phases", False):
        out.append("skip_some_minigame_phases = True (Dampe: every race timed as the second race; first prize after "
                   "any finish, heart piece right after it within 1:00 — a transition started from the chest's own "
                   "opening; talking to Dampe again as the fallback)")
    if getattr(settings, "no_epona_race", False):
        out.append("no_epona_race = True (Epona's Song next to the ranch Epona registers her as the owned horse: "
                   "EventCopyAndRegisterOwnedHorse outside the race's escape; logic needs one ranch visit)")
    if getattr(settings, "ruto_already_f1_jabu", False):
        out.append("ruto_already_f1_jabu = True (Ruto warped to and kept at her top-floor anchor after the meeting)")
    return out


# Read-back (parity/_gaps_check.py)
class _Flow:
    def __init__(self, fs, name):
        self.name = name
        self.fc = _flow(fs, name)
        self.by = {e["name"]: e for e in self.fc["events"]}

    def step(self, name):
        return self.by.get(name)

    def next(self, e):
        return _name(self.fc, e["next"]) if e and "next" in e else None

    def cases(self, e):
        return {c["value"]: _name(self.fc, c["next"]) for c in (e or {}).get("cases", [])}

    def expect(self, bad, name, member, params=None, nxt="-", cases=None):
        """Problems unless step `name` is `member` with `params` and the given routing."""
        e = self.step(name)
        if e is None:
            bad.append(f"{self.name}: no step {name}")
            return None
        got = _member(self.fc, e)
        if got != member:
            bad.append(f"{self.name}: {name} is {got}, not {member}")
        for k, v in (params or {}).items():
            if _param(e, k) != v:
                bad.append(f"{self.name}: {name} {k} = {_param(e, k)!r}, not {v!r}")
        if nxt != "-" and self.next(e) != nxt:
            bad.append(f"{self.name}: {name} goes on to {self.next(e)}, not {nxt}")
        if cases is not None and self.cases(e) != cases:
            bad.append(f"{self.name}: {name} cases {self.cases(e)} != {cases}")
        return e


def _timer_nodes(f, bad, graph, go, no):
    from parity import _chests_dampe as dampe
    minute, second, milli = dampe.TIMER
    q = "GameDataActor.EventQueryIsGameDataInt"
    f.expect(bad, f"{graph}_m", q, {"GameDataName": minute, "Value": 1},
             cases={0: f"{graph}_h", 1: f"{graph}_s", 2: no})
    f.expect(bad, f"{graph}_s", q, {"GameDataName": second, "Value": 0},
             cases={0: f"{graph}_ms", 1: f"{graph}_ms", 2: no})
    f.expect(bad, f"{graph}_ms", q, {"GameDataName": milli, "Value": 0},
             cases={0: f"{graph}_h", 1: f"{graph}_h", 2: no})
    f.expect(bad, f"{graph}_h", "GameDataActor.EventQueryIsGameDataBool", {"GameDataName": dampe.HEART_GOT},
             cases={0: no, 1: go})


def verify_dampe(patch, note, romfs):
    from parity import _chests_dampe as dampe
    fs = _fs(romfs, patch)
    f = _Flow(fs, note["file"])
    bad = []
    f.expect(bad, "Event462", "GameDataActor.EventTriggerSetGameDataBool", nxt="Rando_DampeStart_q")
    f.expect(bad, "Rando_DampeStart_q", "GameDataActor.EventQueryIsGameDataInt",
             {"GameDataName": dampe.COUNT, "Value": 1},
             cases={0: "Rando_DampeStart_rearm", 1: "Event131", 2: "Event131"})
    f.expect(bad, "Rando_DampeStart_rearm", "GameDataActor.EventTriggerSetGameDataBool",
             {"GameDataName": dampe.OFFER_FLAG, "Value": False}, nxt="Event131")
    f.expect(bad, "Event128", "ChallengeSystemActor.EventTriggerMiniGameTimerStop", nxt="Event99")
    f.expect(bad, "Event226", "ChallengeSystemActor.EventTriggerMiniGameTimerStop", nxt="Event158")
    both, talk = dampe.SKIP_GRAPHS
    e230 = f.step("Event230")
    if e230 is None or _name(f.fc, e230["cases"][dampe.CASE_INDEX["Event230"]]["next"]) != f"{both}_m":
        bad.append(f"{f.name}: opening the first-prize chest (Event230) doesn't go on to {both}")
    _timer_nodes(f, bad, both, f"{both}_seen", "Event70")
    f.expect(bad, f"{both}_seen", "GameDataActor.EventTriggerSetGameDataBool",
             {"GameDataName": dampe.APPEAR_SEEN, "Value": False}, nxt=f"{both}_heart")
    f.expect(bad, f"{both}_heart", ":DampeRace_TreasureBoxHeartPiece", nxt=f"{both}_show")
    f.expect(bad, f"{both}_show", "EventSystemActor.EventTransition",
             {"EventName": "MiniGame_DampeRace_TreasureBoxAppear"}, nxt="Event70")
    e413 = f.step("Event413")
    if e413 is None or _name(f.fc, e413["cases"][dampe.CASE_INDEX["Event413"]]["next"]) != f"{talk}_m":
        bad.append(f"{f.name}: Dampe's talk at OpenedHookShot (Event413) doesn't go on to {talk}")
    _timer_nodes(f, bad, talk, f"{talk}_result", "Event422")
    f.expect(bad, f"{talk}_result", ":Result", nxt=None)
    return bad


def verify_epona(patch, note, romfs):
    fs = _fs(romfs, patch)
    bad = []
    file, step, graph = note["song"]
    s = _Flow(fs, file)
    e1 = s.step(step)
    if e1 is None or s.cases(e1).get(1) != f"{graph}_a":
        bad.append(f"{file}: no owned horse ({step} case 1) doesn't go on to {graph}")
    s.expect(bad, f"{graph}_a", "GameDataActor.EventQueryIsGameDataBoolExp", {"GameDataName": COMPLETE},
             cases={0: "Event23", 1: f"{graph}_b"})
    s.expect(bad, f"{graph}_b", "GameSystemActor.EventQueryIsDistanceBetweenActorsClose",
             {"ActorNameA": "Player_Event", "ActorNameB": "Animal_Epona_Adult", "CheckDistance": note["range"]},
             cases={0: f"{graph}_c", 1: "Event23"})
    s.expect(bad, f"{graph}_c", f"{EPONA}:{REGISTER}", nxt="Event5")
    efile, entry, steps = note["register"]
    g = _Flow(fs, efile)
    if entry not in g.fc["entry_points"]:
        bad.append(f"{efile}: no entry {entry}")
    labels = [lab for lab, _, _ in REGISTER_STEPS]
    for i, (lab, _, member) in enumerate(REGISTER_STEPS):
        g.expect(bad, f"{entry}_{lab}", member, nxt=f"{entry}_{labels[i + 1]}" if i + 1 < len(labels) else None)
    g.expect(bad, f"{entry}_done", "ChallengeSystemActor.EventExecuteProgressChallengeStep",
             {"ChallengeName": "Get_Epona", "StepName": "Complete"})
    g.expect(bad, f"{entry}_flag", "GameDataActor.EventTriggerSetGameDataBool",
             {"GameDataName": "Skullchild_JustAfterGetEpona", "Value": True})
    import progressive
    van = _fs(romfs)
    for kfile, kstep, after in note["keep"]:
        k = _Flow(fs, kfile)
        graph = f"Rando_Story_{kstep}_"  # story.Plan.assemble's graph of the step's guards
        guards = [e for e in k.fc["events"] if e["name"].startswith(graph) and
                  _member(k.fc, e) == "GameDataActor.EventQueryIsGameDataBoolExp" and
                  _param(e, "GameDataName") == COMPLETE]
        ok = [g for g in guards if (k.cases(g).get(0) == after or (after and (k.cases(g).get(0) or "").startswith(
            f"Rando_Story_{after}_") and _reaches(k, k.cases(g)[0], after))) and _reaches(k, k.cases(g).get(1), kstep)]
        if len(ok) != 1:
            bad.append(f"{kfile}: {kstep} has {len(ok)} guards on {COMPLETE} skipping to {after} (want 1)")
        vf = _Flow(van, kfile)
        for kind, where, idx in progressive.predecessors(vf.fc, vf.step(kstep)):
            if kind == "entry":
                got = _name(k.fc, k.fc["entry_points"][where]["main"])
            else:
                e = k.step(where)
                if e is None:
                    got = None
                elif kind == "case":
                    got = _name(k.fc, e["cases"][idx]["next"])
                elif kind == "fork":
                    got = _name(k.fc, e["forks"][idx])
                else:
                    got = k.next(e)
            if not (got or "").startswith(graph) or not ok or not _reaches(k, got, ok[0]["name"]):
                bad.append(f"{kfile}: {where} doesn't go through the {COMPLETE} guard to {kstep} ({got})")
    logic = json.load(open(os.path.join(HERE, "data", "rando", "logic", "story.json"), encoding="utf-8"))
    if "no_epona_race" not in (logic.get("helpers") or {}).get("can_ride_epona", ""):
        bad.append("data/rando/logic/story.json: can_ride_epona no longer asks for the ranch with no_epona_race")
    return bad


def _reaches(f, start, target, hops=8):
    """Step `start` of _Flow `f` reaches step `target` within `hops` steps (any branch)."""
    todo, seen = [(start, 0)], set()
    while todo:
        n, d = todo.pop()
        if n == target:
            return True
        e = f.step(n) if n else None
        if e is None or n in seen or d > hops:
            continue
        seen.add(n)
        todo += [(x, d + 1) for x in [f.next(e)] + list(f.cases(e).values()) if x]
    return False


def verify_ruto(patch, note, romfs):
    from romtools import byml_load, sarc_files
    fs = _fs(romfs, patch)
    bad = []
    file, step, anchor = note["warp"]
    f = _Flow(fs, file)
    f.expect(bad, step, "Npc_Zora_Ruto_Child_001.EventAIScheduleWarpToAnchor", {"AnchorType": anchor}, nxt="Event91")
    pack, inner, want = note["schedule"]
    files = sarc_files(fs.read(pack))
    if inner not in files:
        bad.append(f"{pack}: no {inner}")
    else:
        sched = byml_load(files[inner], allow_big=True)[0]
        got = int(sched["DefaultSchedule"]["ActionSchedule"][0]["ActionType"])
        if got != want:
            bad.append(f"{pack}: Ruto's Step10 action is {got}, not {want} (Action1)")
    return bad
