"""Dampé's race without the Hookshot gate.

Vanilla MiniGame_DampeRace decides "first prize already collected?" by asking whether the Hookshot is owned:
  - the finish (Finish_Npc_Hylia_Dampe_002_StepStart: Event31 -> Event442 PouchSystemActor.EventQueryIsExistInPouch
    Item_Hookshot) only counts a win (MiniGame_DampeRace_Clear, Event35: MiniGame_DampeRace_ClearCount += 1) with
    the Hookshot in the pouch
  - the result (Event275, a branch on ClearCount) offers the first prize (the Hookshot chest,
    Minigame_DampeRace_TreasureBoxState AppearHookShot) at ClearCount 0 and the heart piece from then on
  - the race start (MiniGame_DampeRace_Start: Event462 -> Event129 GameDataActor.EventQueryCheckIsGet Item_Hookshot)
    picks the first-race path (Event287..., Event187 re-arms the first-prize offer) when the Hookshot was never got
With the Hookshot anywhere in the seed, a player who finds it first never sees the first prize, and one who never
finds it never reaches the heart piece. So here "first prize collected" becomes "ClearCount >= 1", and opening the
first-prize chest (OpenGoalTBox: Event198 AppearHookShot -> Event201 set OpenedHookShot) adds that 1:
  Event31  -> Rando_DampeFinish: ClearCount < 1 -> Event33 (no count, as without the Hookshot), else -> Event379 (count)
  Event462 -> Rando_DampeStart:  ClearCount < 1 -> Event287 (first-race path), else -> Event131
  Event201 -> Rando_DampeFirstPrize: ClearCount += 1 -> Event95
So the first win shows the first-prize chest until it's opened, and a later win under one minute shows the heart
piece chest (Event275 case 2+, Event399: the heart piece while UnderTheGrave_DampeRace_HeartGeted is false).
Dialogue lines that still ask about the Hookshot (Event0/18/61/260/262/443/444, Event98's timer UI) stay as they
are. GameDataActor.EventQueryIsGameDataInt answers 0 below, 1 equal, 2 above the value (vanilla Event359/360/303).

skip_some_minigame_phases (event_ops(skip_phases=True)). In OoTR Dampe starts with the second race, one run under a
minute gives both prizes, and the first prize comes at any time. The setting is owned by parity/_gaps_minigames.py,
which reads these edits back:
  - every race is the second race. Rando_DampeStart sends ClearCount < 1 to "rearm" (HookShot_Event63 = false, what
    the first-race path's Event187 does, so the first prize is offered again) and then, like ClearCount >= 1, to
    Event131 (PlayingSecond, the timed course the 1:00 target was made for, timer on screen, Ready-Go). The
    first-race path (Event287..Event224, with Event132's SageOfForest -> Step03) isn't reached anymore.
  - the timer is hidden at the goal and on a failed race whatever the pouch holds (Event128 -> Event99,
    Event226 -> Event158). Vanilla only hides it with Item_Hookshot got, and only second races show it.
  - opening the first-prize chest (Event230 case OpenedHookShot) with the run at most 1:00.000 (Event359/360/303's
    test on MiniGame_TimerMinute/Second/MilliSecond) and the heart piece not taken yet
    (UnderTheGrave_DampeRace_HeartGeted) offers the heart-piece chest right away. That's TalkAfterRaceWithD = false
    (or the appearance scene ends at once, TreasureBox_Appearance Event174), :DampeRace_TreasureBoxHeartPiece (state
    AppearHeartPiece), then Event168's transition to MiniGame_DampeRace_TreasureBoxAppear. The level logic
    (UnderTheGrave_Prefab_6971) swaps the opened first-prize chest for the heart-piece chest at the same spot.
  - safety net: talking to Dampe while the state is still OpenedHookShot (Event413 case 0) runs the same checks and
    then :Result (ClearCount is 1 there, so Event359's heart branch with Dampe's own lines), else :SuggestExit as
    before.
A slow first run only gets the first prize, and the next run (ClearCount 1 -> 2 at the finish) offers the heart
piece through Event399 like it does without the setting.

fix_ops() (every seed, wired in parity/chests.py): the first-race path's Event132 sets SageOfForest Step03 with
IsIgnoreCompletedChallenge false, so also after the Forest Temple (SageOfForest Complete). With the Hookshot found
elsewhere the race comes after the temple, and Prelude / Nocturne / adult Mido lose SageOfForest_IsCompleted_Exp for
good. Event97 (first talk without Hookshot or Longshot) sets Step02 the same way. Both get a guard ("already past
that step? go on"). It also hides the timer like above, since races after the first prize use the second-race
path, which shows it with or without the Hookshot.
"""
FILE = "MiniGame_DampeRace"
COUNT = "MiniGame_DampeRace_ClearCount"

# Vanilla next steps and switch branches from the game files. check() verifies both tables.
ROUTES = {"Event31": "Event442", "Event462": "Event129", "Event201": "Event95",
          # skip_some_minigame_phases / fix_ops
          "Event128": "Event98", "Event226": "Event157", "Event95": "Event230", "Event130": "Event132",
          "Event132": "Event187", "Event136": "Event97", "Event97": "Event156", "Event99": "Event195"}
CHECKS = {"Event442": {0: "Event379", 1: "Event33"}, "Event129": {0: "Event131", 1: "Event287"},
          "Event98": {0: "Event99", 1: "Event195"}, "Event157": {0: "Event158"},
          "Event230": {0: "Event70", 1: "Event20"}, "Event413": {0: "Event422", 1: "Event424"}}
# make_patch takes the case's index in the list. In both switches, case value 0 sits at index 0.
CASE_INDEX = {"Event230": 0, "Event413": 0}
TIMER = ("MiniGame_TimerMinute", "MiniGame_TimerSecond", "MiniGame_TimerMilliSecond")
HEART_GOT = "UnderTheGrave_DampeRace_HeartGeted"
OFFER_FLAG = "HaveTalked_Special.MiniGame_DampeRace_HookShot_Event63"
APPEAR_SEEN = "MiniGame_DampeRace_TalkAfterRaceWithD"
TRANSITION = "Event168"  # EventTransition MiniGame_DampeRace_TreasureBoxAppear (Result's heart branch)
SKIP_GRAPHS = ("Rando_DampeBothPrizes", "Rando_DampeTalkHeart")


def _count_query(below, at_least):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
            "params": {"Index": -1, "GameDataName": COUNT, "Value": 1},
            "cases": {0: "@" + below, 1: "@" + at_least, 2: "@" + at_least}}


def _graph(entry, nodes, start):
    return {"file": FILE, "flowchart": FILE, "add_graph": entry, "nodes": nodes, "start": start}


def _route(event, target, case=None):
    op = {"file": FILE, "flowchart": FILE, "event": event, "next": target}
    if case is not None:
        op["case"] = case
    return op


def _int_query(name, value, cases):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
            "params": {"Index": -1, "GameDataName": name, "Value": value}, "cases": cases}


def _fast_heart_checks(go, no):
    """Nodes m -> s -> ms -> h: the run took at most 1:00.000 and the heart piece is not taken yet -> go, else no."""
    minute, second, milli = TIMER
    return {
        "m": _int_query(minute, 1, {0: "h", 1: "s", 2: no}),
        "s": _int_query(second, 0, {0: "ms", 1: "ms", 2: no}),
        "ms": _int_query(milli, 0, {0: "h", 1: "h", 2: no}),
        "h": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
              "params": {"Index": -1, "GameDataName": HEART_GOT}, "cases": {0: no, 1: go}},
    }


def timer_hide_ops():
    """The race timer is hidden at the goal and on a failed race whether or not the Hookshot was ever got."""
    return [_route("Event128", "Event99"), _route("Event226", "Event158")]


def skip_phase_ops():
    """skip_some_minigame_phases: the timer hides, the heart piece comes right after the first prize, and the talk
    safety net. The start routing is part of event_ops."""
    both = _fast_heart_checks("seen", "@Event70")
    both.update({
        "seen": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                 "params": {"Index": -1, "GameDataName": APPEAR_SEEN, "Value": False}, "next": "heart"},
        "heart": {"call": ":DampeRace_TreasureBoxHeartPiece", "next": "show"},
        "show": {"copy": TRANSITION, "next": "@Event70"},
    })
    talk = _fast_heart_checks("result", "@Event422")
    talk["result"] = {"call": ":Result", "next": None}
    return timer_hide_ops() + [
        _graph(SKIP_GRAPHS[0], both, "m"),
        _route("Event230", f"{SKIP_GRAPHS[0]}_m", CASE_INDEX["Event230"]),
        _graph(SKIP_GRAPHS[1], talk, "m"),
        _route("Event413", f"{SKIP_GRAPHS[1]}_m", CASE_INDEX["Event413"]),
    ]


def event_ops(skip_phases=False):
    """Plan "events" entries (tools/make_patch.py): three small graphs and the reroutes into them. With skip_phases
    (skip_some_minigame_phases) every race starts as the second race and a fast run gives both prizes."""
    if skip_phases:
        q = _count_query("Event131", "Event131")
        q["cases"][0] = "rearm"  # ClearCount < 1: offer the first prize again, then the second race like the rest
        start = {"q": q, "rearm": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                                   "params": {"Index": -1, "GameDataName": OFFER_FLAG, "Value": False},
                                   "next": "@Event131"}}
    else:
        start = {"q": _count_query("Event287", "Event131")}
    ops = [
        _graph("Rando_DampeFinish", {"q": _count_query("Event33", "Event379")}, "q"),
        _graph("Rando_DampeStart", start, "q"),
        _graph("Rando_DampeFirstPrize", {"inc": {"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt",
                                                 "params": {"GameDataName": COUNT, "Value": 1, "Index": -1},
                                                 "next": "@Event95"}}, "inc"),
        _route("Event31", "Rando_DampeFinish_q"),
        _route("Event462", "Rando_DampeStart_q"),
        _route("Event201", "Rando_DampeFirstPrize_inc"),
    ]
    return ops + (skip_phase_ops() if skip_phases else [])


def fix_ops(skip_phases=False):
    """Fixes for every seed (parity/chests.py):
      - SageOfForest's Step03 (Event132) and Step02 (Event97) don't move the story back once it's past them
      - the timer is hidden whatever the pouch holds (left out with skip_phases, whose event_ops already hide it)
      - a Link without a hookshot gets sent out of the goal room (exit_ops)"""
    def guard(entry, exp, step, after, pred):
        return [_graph(entry, {"g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                                     "params": {"GameDataName": exp}, "cases": {0: f"@{after}", 1: f"@{step}"}}},
                       "g"),
                _route(pred, f"{entry}_g")]
    ops = guard("Rando_DampeGuardStep03", "SageOfForest_IsAfter_Step03_Exp", "Event132", "Event187", "Event130")
    ops += guard("Rando_DampeGuardStep02", "SageOfForest_IsAfter_Step01_Exp", "Event97", "Event156", "Event136")
    return ops + ([] if skip_phases else timer_hide_ops()) + exit_ops()


# The goal room can only be left with the Hookshot. Vanilla gives it in the first-prize chest, and SuggestExit only
# points at the exit. With the first prize shuffled, a Link without the Hookshot or Longshot is stuck there, and the
# remake has no save warp (ItZPomme/OOTRR and Kaepora saw it in game).
# So both talks Dampe gives after a chest (SuggestExit after the first
# prize, RetryCheck after the others, whose "no" makes him leave) first ask for either hookshot. Without one, Link
# gets sent out the way the race's own end does it (a copy of Event104: Graveyard_Adult, start point 4), and the
# talk ends. ItZPomme's same exit was validated in game. It's a copy of that step, not a jump into the other
# entry's branch, which crashed.
EXIT_ENTRIES = (("SuggestExit", "Event416"), ("RetryCheck_Npc_Hylia_Dampe_002_Talk", "Event288"))
EXIT_STEP = "Event104"  # GameSystemActor.EventReserveBancChange NextBanc Graveyard_Adult, NextStartPos "4"
HOOKSHOTS = ("Item_Hookshot", "Item_Longshot")


def exit_ops():
    """Every seed: each EXIT_ENTRIES talk sends a Link without a hookshot out of the grave (see above)."""
    ops = []
    for k, (entry, first) in enumerate(EXIT_ENTRIES):
        graph = f"Rando_DampeExit{k}"
        nodes = {f"h{j}": {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                           "params": {"Actor": hs, "Num": 1},
                           "cases": {0: f"@{first}", 1: f"h{j + 1}" if j + 1 < len(HOOKSHOTS) else "out"}}
                 for j, hs in enumerate(HOOKSHOTS)}
        nodes["out"] = {"copy": EXIT_STEP, "next": None}
        ops += [_graph(graph, nodes, "h0"), {"file": FILE, "flowchart": FILE, "entry": entry, "next": f"{graph}_h0"}]
    return ops


def check(romfs, vanilla_dir=None):
    """Problems if the vanilla flow differs from what this patch assumes (run by hand / from a selftest)."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(romfs, vanilla_dir)
    fc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{FILE}.bfevfl.zs")).flowcharts if f["name"] == FILE)
    by_idx = {e["idx"]: e["name"] for e in fc["events"]}
    by = {e["name"]: e for e in fc["events"]}
    problems = []
    for step, nxt in ROUTES.items():
        if by_idx.get(by[step].get("next")) != nxt:
            problems.append(f"{step} no longer leads to {nxt}")
    for step, cases in CHECKS.items():
        got = {c["value"]: by_idx.get(c["next"]) for c in by[step].get("cases", [])}
        if got != cases:
            problems.append(f"{step} cases {got} != {cases}")
    for step, k in CASE_INDEX.items():
        if by[step]["cases"][k]["value"] != 0:
            problems.append(f"{step}: case {k} is no longer the value-0 case")
    t = by[TRANSITION]
    if t["type"] != "action" or fc["actors"][t["actor"]]["actions"][t["action"]] != "EventTransition" or \
            (t.get("params") or {}).get("items", {}).get("EventName", {}).get("value") != \
            "MiniGame_DampeRace_TreasureBoxAppear":
        problems.append(f"{TRANSITION} is no longer the transition to MiniGame_DampeRace_TreasureBoxAppear")
    for entry in ("Result", "DampeRace_TreasureBoxHeartPiece", "TreasureBox_Appearance"):
        if entry not in fc["entry_points"]:
            problems.append(f"no entry {entry}")
    for entry, first in EXIT_ENTRIES:
        ep = fc["entry_points"].get(entry)
        if ep is None or by_idx.get(ep.get("main")) != first:
            problems.append(f"entry {entry} no longer starts at {first}")
    x = by.get(EXIT_STEP)
    items = ((x or {}).get("params") or {}).get("items", {})
    if x is None or x["type"] != "action" or \
            fc["actors"][x["actor"]]["actions"][x["action"]] != "EventReserveBancChange" or \
            items.get("NextBanc", {}).get("value") != "Graveyard_Adult":
        problems.append(f"{EXIT_STEP} is no longer the race's change of area to Graveyard_Adult")
    return problems


FIX_GUARDS = (("Rando_DampeGuardStep03", "SageOfForest_IsAfter_Step03_Exp", "Event132", "Event187", "Event130"),
              ("Rando_DampeGuardStep02", "SageOfForest_IsAfter_Step01_Exp", "Event97", "Event156", "Event136"))


def verify_fix(patch, note, romfs):
    """Reads fix_ops back from the built MiniGame_DampeRace. Each guarded step's predecessor has to go to its guard,
    which skips the step once SageOfForest is past it, and the timer has to hide (unless skip_some_minigame_phases
    made them)."""
    import os
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, os.path.join(here, "tools"))
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(here, "original"), [patch])
    fc = Evfl(fs.read("Event/EventFlow/MiniGame_DampeRace.bfevfl.zs")).flowcharts[0]
    ev = fc["events"]
    by = {e["name"]: e for e in ev}

    def name(i):
        return ev[i]["name"] if i not in (None, 0xFFFF) and i < len(ev) else None
    bad = []
    for graph, exp, step, after, pred in FIX_GUARDS:
        g = by.get(name(by[pred]["next"])) if pred in by else None
        if g is None or g["name"] != f"{graph}_g" or g["type"] != "switch":
            bad.append(f"MiniGame_DampeRace: {pred} doesn't go to the {step} guard")
            continue
        cases = {c["value"]: name(c["next"]) for c in g["cases"]}
        got = ((g.get("params") or {}).get("items") or {}).get("GameDataName", {}).get("value")
        if got != exp or cases.get(0) != after or cases.get(1) != step:
            bad.append(f"MiniGame_DampeRace: {graph} asks {got} -> {cases}, want {exp} -> {after} / {step}")
    for src, dst in (("Event128", "Event99"), ("Event226", "Event158")):
        if name(by[src]["next"]) != dst:
            bad.append(f"MiniGame_DampeRace: {src} goes to {name(by[src]['next'])}, not {dst} (timer hide)")
    for k, (entry, first) in enumerate(EXIT_ENTRIES):  # the exit for a Link without a hookshot
        ep = fc["entry_points"].get(entry) or {}
        node, seen, asked = by.get(name(ep.get("main"))), set(), []
        while node is not None and node["type"] == "switch" and node["name"] not in seen:
            seen.add(node["name"])
            asked.append(((node.get("params") or {}).get("items") or {}).get("Actor", {}).get("value"))
            cases = {c["value"]: name(c["next"]) for c in node["cases"]}
            if cases.get(0) != first:
                bad.append(f"MiniGame_DampeRace: {entry}: owning {asked[-1]} doesn't go on to {first}")
            node = by.get(cases.get(1))
        x = (node.get("params") or {}).get("items", {}) if node else {}
        if asked != list(HOOKSHOTS) or node is None or node["type"] != "action" or \
                fc["actors"][node["actor"]]["actions"][node["action"]] != "EventReserveBancChange" or \
                x.get("NextBanc", {}).get("value") != "Graveyard_Adult" or name(node.get("next")) is not None:
            bad.append(f"MiniGame_DampeRace: {entry} doesn't ask {HOOKSHOTS} and then leave for Graveyard_Adult")
    return bad

