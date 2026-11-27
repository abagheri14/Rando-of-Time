"""remake_no_objective_card (OOTRR's no "next objective" card): no card pops up when a quest moves on, and Threads of
Time still follows the quests.

Where the card comes from (Longshot v3.2.0's game files):
- Every scene's quest step runs through ChallengeSystemActor's event graph (GRAPH, the game spells it "Challange").
  EventExecuteProgressChallengeStep, EventTriggerProgressChallengeStep and EventExecuteRollbackChallengeStep hand the
  scene's IsIgnoreChallengeProgressUI to their step nodes (OneShotChallengeSetStep, OneShotChallengeProgressNextStep).
  225 of the scenes' 286 step calls say false, and that's the card. Those inputs hold true now, so the step still
  moves on and the quest log still changes, just without the card.
- EventTriggerShowChallengeProgressUI shows the card by itself (36 scene steps, the "IsFirstStep" ones for a new
  quest). Its Execute runs a do-nothing action now, a copy of the one the graph's own EventDoNothing runs.
- Adult Zelda's walk in the castle escape moves her quest on with the card (ZELDA_GRAPH). Its input holds true too.
- Logic modules set steps with TriggerChallengeSetStep, which has no card input, and some steps move on by themselves
  once a save flag is set (ForceProgressGameData, like SageOfForest Step03 on getting the Hookshot). Those steps get
  IsNotChangeAdventureLog in the quest table, the game's own mark for steps that leave the log alone (minigame steps
  and most dungeon steps have it), so no card. Their own log line is skipped; every other step's stays."""
import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

PACK = "Pack/Actor/ChallengeSystemActor.pack.zs"
GRAPH = "AI/ChallangeSystemActor.event.root.ainb"
ZELDA_GRAPH = "AI/Npc_Hylia_Zelda_Adult_Patrol_RailEndPointSpecialAction.actionseq.root.ainb"
TABLE = "RSDB/Challenge.Product.111.rstbl.byml.zs"
ROW = "Work/Challenge/{}.game__challenge__Challenge.gyml"
NO_CARD = "IsIgnoreChallengeProgressUI"
QUIET = "IsNotChangeAdventureLog"
STEP_NODES = ("OneShotChallengeSetStep", "OneShotChallengeProgressNextStep")
SHOW = "EventTriggerShowChallengeProgressUI"
DO_NOTHING = "EventDoNothing"
DUMMY = "ExecuteGenericDummyAction"
LOGIC_SET = "TriggerChallengeSetStep"  # and TriggerChallengeSetStepNoEventPause
NOTE = "remake_no_objective_card"


def _fs(romfs):
    import romtools
    return romtools.Romfs(romfs, os.path.join(HERE, "original"))


def _graph(fs, pack=PACK, graph=GRAPH):
    import ainb
    import romtools
    return ainb.Ainb(romtools.sarc_files(fs.read(pack))[graph])


def _card_input(n):
    return next((x for x in (n.get("inputs") or {}).get("bool") or [] if x["name"] == NO_CARD), None)


def _kids(a, i):
    return {p["name"]: p["node"] for p in a.nodes[i]["plugs"][2]}


def _show_node(a):
    shows = [i for i, n in enumerate(a.nodes) if n["name"] == SHOW]
    if len(shows) != 1:
        raise RuntimeError(f"{NOTE}: {GRAPH} has {len(shows)} {SHOW} nodes")
    return shows[0]


def logic_steps(romfs):
    """{(quest, step)} the game's logic modules set (TriggerChallengeSetStep*, constant names only)."""
    import ainb
    out = set()
    for sub in ("Logic", "Sequence", "AI"):
        for p in sorted(glob.glob(os.path.join(romfs, sub, "*.ainb"))):
            d = open(p, "rb").read()
            if LOGIC_SET.encode() not in d:
                continue
            for i, n in enumerate(ainb.Ainb(d).nodes):
                if not str(n.get("name", "")).startswith(LOGIC_SET):
                    continue
                s = {x["name"]: x for x in (n.get("inputs") or {}).get("string") or []}
                c, st = s.get("ChallengeName"), s.get("StepName")
                if c is None or st is None or c["node"] >= 0 or st["node"] >= 0:
                    raise RuntimeError(f"{NOTE}: {os.path.basename(p)} node {i} doesn't name its quest step")
                out.add((os.path.basename(c["value"]).split(".", 1)[0], st["value"]))
    return out


def quiet_steps(romfs):
    """[(quest, step index, step name)] that need the table's mark: set by a logic module or moving on by itself,
    and not marked yet. A step a module names in other letter case is the table's step ("step04")."""
    import romtools
    rows = romtools.byml_load(_fs(romfs).read(TABLE))[0]
    table = {os.path.basename(r["__RowId"]).split(".", 1)[0]: r.get("Steps") or [] for r in rows}
    want = set()
    for quest, step in logic_steps(romfs):
        steps = table.get(quest)
        if steps is None:
            raise RuntimeError(f"{NOTE}: a logic module sets {quest}, which isn't in the quest table")
        if step == "Complete":
            continue  # the end of a quest, no step row (the two the modules set: Lens of Truth, Song of Storms)
        k = next((k for k, s in enumerate(steps) if s["Name"].lower() == step.lower()), None)
        if k is None:
            raise RuntimeError(f"{NOTE}: a logic module sets {quest} {step}, which the quest table doesn't have")
        want.add((quest, k))
    for quest, steps in table.items():
        want |= {(quest, k) for k, s in enumerate(steps) if s.get("ForceProgressGameData")}
    out = []
    for quest, k in sorted(want):
        s = table[quest][k]
        if QUIET not in s:
            raise RuntimeError(f"{NOTE}: {quest} {s['Name']} has no {QUIET}")
        if s[QUIET] is False:
            out.append((quest, k, s["Name"]))
    return out


def plan(romfs):
    """(ainb ops, byml ops, read-back) for remake_no_objective_card."""
    import packpaths
    fs = _fs(romfs)
    a = _graph(fs)
    edits, cut, kept = [], [], []
    for i, n in enumerate(a.nodes):
        if n["name"] not in STEP_NODES:
            continue
        e = _card_input(n)
        if e is None:
            raise RuntimeError(f"{NOTE}: {GRAPH} node {i} ({n['name']}) has no {NO_CARD} input")
        if e["node"] >= 0:
            edits.append({"cut": {"node": i, "input": NO_CARD, "value": True}})
            cut.append(i)
        elif e["value"] is not True:
            edits.append({"set_input": {"node": i, "name": NO_CARD, "value": True, "const": True}})
            cut.append(i)
        else:
            kept.append(i)
    if len(cut) < 5:
        raise RuntimeError(f"{NOTE}: {GRAPH} has only {len(cut)} step nodes that show the card")
    show = _show_node(a)
    names = [n["name"] for n in a.nodes]
    nothing = _kids(a, names.index(DO_NOTHING)).get("Execute")
    if names.count(DO_NOTHING) != 1 or nothing is None or names[nothing] != DUMMY:
        raise RuntimeError(f"{NOTE}: {GRAPH}'s {DO_NOTHING} doesn't run {DUMMY}")
    if "Execute" not in _kids(a, show):
        raise RuntimeError(f"{NOTE}: {GRAPH}'s {SHOW} has no Execute")
    edits += [{"copy": {"from": {"pack": PACK, "file": GRAPH}, "nodes": [nothing], "label": "nocard",
                        "follow": False}},
              {"set_child": {"parent": show, "which": "Execute", "child": f"nocard:{nothing}"}}]
    ops = [{"pack": PACK, "file": GRAPH, "edits": edits, "note": NOTE}]

    zelda_packs = sorted(packpaths.index(romfs).get(ZELDA_GRAPH) or ())
    if not zelda_packs:
        raise RuntimeError(f"{NOTE}: no pack holds {ZELDA_GRAPH}")
    za = _graph(fs, zelda_packs[0], ZELDA_GRAPH)
    zelda = [i for i, n in enumerate(za.nodes) if n["name"] in STEP_NODES]
    if not zelda:
        raise RuntimeError(f"{NOTE}: {ZELDA_GRAPH} has no quest step node")
    zedits = []
    for i in zelda:
        e = _card_input(za.nodes[i])
        if e is None or e["node"] >= 0:
            raise RuntimeError(f"{NOTE}: {ZELDA_GRAPH} node {i}'s {NO_CARD} isn't a plain value")
        if e["value"] is not True:
            zedits.append({"set_input": {"node": i, "name": NO_CARD, "value": True, "const": True}})
    if zedits:
        ops.append({"pack": zelda_packs, "file": ZELDA_GRAPH, "edits": zedits, "note": NOTE})

    steps = quiet_steps(romfs)
    sets = {f"[__RowId={ROW.format(q)}].Steps.{k}.{QUIET}": True for q, k, _ in steps}
    byml = [{"file": TABLE, "set": sets, "note": NOTE}] if sets else []
    rb = {"steps": cut + kept, "show": show, "zelda": {"packs": zelda_packs, "nodes": zelda},
          "quiet": [[q, k, name] for q, k, name in steps]}
    return ops, byml, rb


def verify(patch, rb, romfs):
    """[problem] reading the card's removal back from a built patch."""
    import romtools
    fs = romtools.Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    a = _graph(fs)
    for i in rb["steps"]:
        e = _card_input(a.nodes[i])
        if e is None or e["node"] >= 0 or e["value"] is not True:
            bad.append(f"{GRAPH} node {i} ({a.nodes[i]['name']}): {NO_CARD} isn't always true")
    if not any(n["name"] in STEP_NODES and _card_input(n) and _card_input(n)["node"] < 0 for n in a.nodes):
        bad.append(f"{GRAPH}: no quest step node left")
    show = rb["show"]
    kid = _kids(a, show).get("Execute")
    if a.nodes[show]["name"] != SHOW or kid is None or a.nodes[kid]["name"] != DUMMY:
        bad.append(f"{GRAPH}: {SHOW} still runs {a.nodes[kid]['name'] if kid is not None else 'nothing'}")
    for pk in rb["zelda"]["packs"]:
        za = _graph(fs, pk, ZELDA_GRAPH)
        for i in rb["zelda"]["nodes"]:
            e = _card_input(za.nodes[i])
            if e is None or e["value"] is not True or e["node"] >= 0:
                bad.append(f"{pk} {ZELDA_GRAPH} node {i}: {NO_CARD} isn't true")
    if rb["quiet"]:
        rows = romtools.byml_load(fs.read(TABLE))[0]
        table = {os.path.basename(r["__RowId"]).split(".", 1)[0]: r.get("Steps") or [] for r in rows}
        for q, k, name in rb["quiet"]:
            s = (table.get(q) or [])[k] if k < len(table.get(q) or []) else None
            if s is None or s["Name"] != name or s.get(QUIET) is not True:
                bad.append(f"{TABLE}: {q} {name} isn't marked {QUIET}")
    return bad
