"""remake_kakariko_owl (OOTRR's Kakariko owl, part of their owl_warps): an owl stands in child Kakariko, just inside
the village gate, and flies a child Link to Kokiri Forest whenever he asks. (The other half of their owl_warps, the
Death Mountain and Lake Hylia owls staying all game and the summit ride without Din's Fire, is always ours:
parity/_story_traps.py OWLS_STAY and DMT_OWL.)

How (Longshot v3.2.0's game files):
- The owl is a new placement of the summit owl's own actor (Npc_Kaepora_DeathMountainTrail) in
  KakarikoVillage_Child_Static, made as a twin of an anchor by the gate. Like the summit owl it gets an AnchorAction1
  and AnchorAction2 of its own on its spot (the summit's two anchors sit on the owl, the second turned 155 degrees),
  linked the same way. The summit owl's third link, the falling-rock manager up there, has no Kakariko twin.
- Both owls run the same scene, Npc_Kaepora_DeathMountainTrail. Its Talk entry (after the mask chat, Event41) now
  asks GameSystemActor.EventQueryExistActor, the game's own "is there one of these here" query, for two actors child
  Kakariko has by the gate and no Death Mountain Trail map has (KAKARIKO_ONLY). Neither there: the summit owl's
  talk, as before. Either there: the Kakariko ride. That's the summit ride's own steps, copied (the offer with its
  yes/no, the yes nod, "grab hold of my talons", the fade), with a new offer line and the level change going to
  Kokiri Forest, where the Lost Woods path lands (KokiriForest_FrontOfLostWood, the plain arrival scene, like our
  entrance table's LW Forest Exit -> Kokiri Forest). The summit's flight scene isn't played, since its cameras are
  the mountain's.
- Logic: a child exit Kakariko Village -> Kokiri Forest (OoTR's owl rides are is_child)."""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

NOTE = "remake_kakariko_owl"
LEVEL = "Banc/KakarikoVillage/KakarikoVillage_Child_Static.bcett.byml.zs"
LEVEL_FILES = (LEVEL, "Banc/KakarikoVillage/KakarikoVillage_Child_Dynamic.bcett.byml.zs")
SOURCE = "18271398448784052038"  # the AnchorAction1 by the gate (the soldier's), what the twins copy
OWL = "Npc_Kaepora_DeathMountainTrail"
SPOT = (-106.5, 97.687, 59.6)  # just inside the gate, north of the path, on the flat ground there
YAW = -1.9                      # facing the gate and the path (yaw pi/2 faces +x, as the entrance start does)
ANCHOR2_TURN = -2.7053          # the summit's AnchorAction2 against its owl (Rotate (pi, -1.309, pi) = yaw -1.833)
FLOW = "Npc_Kaepora_DeathMountainTrail"
MSBT = "EventFlowMsg/Npc_Kaepora_DeathMountainTrail.msbt"
LABEL = "Rando_KakOwl_Ask"
OFFER = "{tag:3,0,0f0000}If you're heading home, I can carry you\nas far as Kokiri Forest. {tag:5,0}What do you say?"
KAKARIKO_ONLY = ("Npc_Hylia_Soldier_001", "HorseAnchor")  # by the gate in child Kakariko, in no DMT map
GRAPH = "Rando_KakOwl"
EXPECT = {  # the summit ride's steps this copies (Talk entry): name -> call
    "Event41": ":Mask_All", "Event4": "GameDataActor.EventQueryIsGameDataBool",
    "Event13": f"{OWL}.EventTalk", "Event14": "GameSystemActor.EventQueryTalkChoice2",
    "Event53": "GameSystemActor.EventTriggerBancRequestBeforehandLoad", "Event0": "NpcCommon:Npc_IsConfront_WithLinkAS",
    "Event15": f"{OWL}.EventTalk", "Event24": "Minigame_CatchCucco:CatchCucco_ResetTimeCheck",
    "Event8": "UISystemActor.EventEventFadeOut", "Event45": "GameSystemActor.EventReserveBancChange",
    "Event54": "Player_Event.EventPlayerPlayASForFlowchart", "Event16": f"{OWL}.EventTalk"}
EXIT = ("Kakariko Village", "Kokiri Forest", "is_child")
ARRIVAL_FROM = "LW Forest Exit -> Kokiri Forest"


def new_hash(k):
    """New placement hash number k: never a vanilla one of the map (plan checks)."""
    return int.from_bytes(hashlib.sha1(f"{NOTE}:{k}".encode()).digest()[:8], "little") % (1 << 63)


def _yaw(a):
    while a > 3.141592653589793:
        a -= 6.283185307179586
    while a < -3.141592653589793:
        a += 6.283185307179586
    return a


def _flow(fs, romfs):
    from evfl import Evfl
    from parity._story_build import newest
    rel, _ = newest(romfs, FLOW)
    return rel, next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == FLOW)


def _call(fc, e):
    """'Actor.Action' / 'File:Entry' of a step (as tools/gamedb names it)."""
    if e["type"] == "subflow":
        return f"{e.get('flowchart') or ''}:{e.get('entry_point')}"
    a = fc["actors"][e["actor"]]
    kind = "action" if e["type"] == "action" else "query"
    names = a["actions"] if kind == "action" else a["queries"]
    return f"{a['name']}.{names[e[kind]]}"


def arrival(romfs=None):
    """(level, start position, arrival scene, preload path) of the ride's landing."""
    from parity import entrances
    level, start, boot = entrances._arrival(ARRIVAL_FROM, "child")
    return level, start, boot, entrances.table()["level_paths"][level]


def plan(romfs):
    """(placement ops, event ops, text ops, read-back) for remake_kakariko_owl."""
    import romtools
    fs = romtools.Romfs(romfs, os.path.join(HERE, "original"))
    have = set()
    for f in LEVEL_FILES:
        have |= {int(a["Hash"]) for a in romtools.byml_load(fs.read(f))[0].get("Actors") or []}
    acts = {str(a["Hash"]): a for a in romtools.byml_load(fs.read(LEVEL))[0].get("Actors") or []}
    if acts.get(SOURCE, {}).get("Gyaml") != "AnchorAction1":
        raise RuntimeError(f"{NOTE}: {LEVEL} #{SOURCE} isn't the AnchorAction1 by the gate")
    gyamls = {a.get("Gyaml") for f in LEVEL_FILES for a in romtools.byml_load(fs.read(f))[0].get("Actors") or []}
    if not all(g in gyamls for g in KAKARIKO_ONLY):
        raise RuntimeError(f"{NOTE}: child Kakariko has no {' or '.join(KAKARIKO_ONLY)}")
    for f in sorted(os.listdir(os.path.join(romfs, "Banc", "DeathMountainTrail"))):
        if f.endswith(".bcett.byml.zs"):
            names = {a.get("Gyaml") for a in romtools.byml_load(fs.read(f"Banc/DeathMountainTrail/{f}"))[0]
                     .get("Actors") or []}
            if names & set(KAKARIKO_ONLY):
                raise RuntimeError(f"{NOTE}: {f} has {names & set(KAKARIKO_ONLY)}, so the summit owl would fly "
                                   f"to Kokiri Forest too")
    owl, a1, a2 = (new_hash(k) for k in range(3))
    if {owl, a1, a2} & have:
        raise RuntimeError(f"{NOTE}: a new placement hash is already in child Kakariko")
    x, y, z = SPOT
    keep = ["Dynamic", "Links", "Name", "Scale", "Presence"]
    placements = [
        {"file": LEVEL, "hash": SOURCE, "twin": str(a1), "join_groups": False, "note": NOTE,
         "set": {"Translate": [x, y, z], "Rotate": [0.0, YAW, 0.0]}, "remove": keep},
        {"file": LEVEL, "hash": SOURCE, "twin": str(a2), "join_groups": False, "note": NOTE,
         "set": {"Gyaml": "AnchorAction2", "Translate": [x, y, z], "Rotate": [0.0, _yaw(YAW + ANCHOR2_TURN), 0.0]},
         "remove": keep},
        {"file": LEVEL, "hash": SOURCE, "twin": str(owl), "join_groups": False, "note": NOTE,
         "set": {"Gyaml": OWL, "Translate": [x, y, z], "Rotate": [0.0, YAW, 0.0]},
         "remove": [k for k in keep if k != "Links"],  # (removes come after add_links; the anchor has none)
         "add_links": [{"dst": str(a1)}, {"dst": str(a2)}]}]
    if acts[SOURCE].get("Links"):
        raise RuntimeError(f"{NOTE}: {LEVEL} #{SOURCE} has links now; the owl twin would copy them")

    rel, fc = _flow(fs, romfs)
    ev = {e["name"]: e for e in fc["events"]}
    for name, call in EXPECT.items():
        if name not in ev or _call(fc, ev[name]) != call:
            raise RuntimeError(f"{NOTE}: {rel} {name} isn't {call}")
    if fc["events"][ev["Event41"]["next"]]["name"] != "Event4" or fc["entry_points"]["Talk"]["main"] != ev["Event41"]["idx"]:
        raise RuntimeError(f"{NOTE}: {rel}'s Talk entry isn't the mask chat then Event4")
    level, start, boot, path = arrival(romfs)
    ask = {"actor": "GameSystemActor", "query": "EventQueryExistActor",
           "params": {"IsCheckLife": False, "IsCheckEquippedNPC": False, "IsCheckEquippedEnemy": False}}
    nodes = {
        "here": dict(ask, params=dict(ask["params"], ActorName=KAKARIKO_ONLY[0]), cases={0: "here2", 1: "offer"}),
        "here2": dict(ask, params=dict(ask["params"], ActorName=KAKARIKO_ONLY[1]), cases={0: "@Event4", 1: "offer"}),
        "offer": {"copy": "Event13", "params_over": {"MessageId": f"{MSBT[:-5]}:{LABEL}"}, "next": "pick"},
        "pick": {"copy": "Event14", "cases": {0: "load", 1: "no"}},
        "load": {"copy": "Event53", "params_over": {"BancPath": path}, "next": "nod"},
        "nod": {"copy": "Event0", "next": "grab"},
        "grab": {"copy": "Event15", "next": "cucco"},
        "cucco": {"copy": "Event24", "next": "fade"},
        "fade": {"copy": "Event8", "next": "go"},
        "go": {"copy": "Event45", "params_over": {"NextBanc": level, "NextStartPos": start, "BootEventName": boot},
               "next": None},
        "no": {"copy": "Event54", "next": "hoot"},
        "hoot": {"copy": "Event16", "next": None}}
    events = [{"file": FLOW, "flowchart": FLOW, "add_graph": GRAPH, "nodes": nodes, "start": "here", "note": NOTE},
              {"file": FLOW, "flowchart": FLOW, "event": "Event41", "next": f"{GRAPH}_here", "note": NOTE}]
    text = [{"lang": "*", "file": MSBT, "label": LABEL, "markup": OFFER, "add": True, "note": NOTE}]
    rb = {"owl": str(owl), "anchors": [str(a1), str(a2)], "spot": list(SPOT), "level": level, "start": start,
          "boot": boot, "path": path}
    return placements, events, text, rb


def before_fill(world):
    """The ride for the logic: Kakariko Village -> Kokiri Forest, as a child."""
    from Entrance import Entrance
    src, dst, rule = EXIT
    region = world.get_region(src)
    if any(e.name == f"{src} -> {dst}" for e in region.exits):
        return
    e = Entrance(f"{src} -> {dst}", region)
    e.world = world
    e.rule_string = rule
    world.parser.parse_spot_rule(e)
    region.exits.append(e)
    e.connect(world.get_region(dst))


def verify(patch, rb, romfs):
    """[problem] reading the Kakariko owl back from a built patch."""
    import romtools
    fs = romtools.Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    acts = {str(a["Hash"]): a for a in romtools.byml_load(fs.read(LEVEL))[0].get("Actors") or []}
    owl = acts.get(rb["owl"])
    if not owl or owl.get("Gyaml") != OWL:
        bad.append(f"{LEVEL}: no {OWL} #{rb['owl']}")
    else:
        if any(abs(a - b) > 0.01 for a, b in zip(owl.get("Translate") or [], rb["spot"])):
            bad.append(f"{LEVEL}: the owl isn't at {rb['spot']}")
        if "Presence" in owl:
            bad.append(f"{LEVEL}: the owl has a Presence")
        dst = sorted(str(l.get("Dst")) for l in owl.get("Links") or [])
        if dst != sorted(rb["anchors"]):
            bad.append(f"{LEVEL}: the owl links {dst}, planned its anchors {rb['anchors']}")
    for h, g in zip(rb["anchors"], ("AnchorAction1", "AnchorAction2")):
        if (acts.get(h) or {}).get("Gyaml") != g:
            bad.append(f"{LEVEL}: no {g} #{h}")
    rel, fc = _flow(fs, romfs)
    ev = {e["name"]: e for e in fc["events"]}
    e41 = ev.get("Event41")
    if not e41 or fc["events"][e41["next"]]["name"] != f"{GRAPH}_here":
        bad.append(f"{rel}: the Talk entry doesn't ask where the owl is")
    from parity._story_build import flat
    p = lambda n: flat((ev.get(f"{GRAPH}_{n}") or {}).get("params"), {})  # noqa: E731
    if p("here").get("ActorName") != KAKARIKO_ONLY[0] or p("here2").get("ActorName") != KAKARIKO_ONLY[1]:
        bad.append(f"{rel}: the Kakariko check doesn't ask for {KAKARIKO_ONLY}")
    go = p("go")
    if (go.get("NextBanc"), go.get("NextStartPos"), go.get("BootEventName")) != (rb["level"], rb["start"], rb["boot"]):
        bad.append(f"{rel}: the Kakariko ride goes to {go.get('NextBanc')} {go.get('NextStartPos')}")
    if p("load").get("BancPath") != rb["path"]:
        bad.append(f"{rel}: the Kakariko ride preloads {p('load').get('BancPath')}")
    if p("offer").get("MessageId") != f"{MSBT[:-5]}:{LABEL}":
        bad.append(f"{rel}: the Kakariko owl's offer isn't {LABEL}")
    nxt = (ev.get(f"{GRAPH}_here2") or {}).get("cases") or []
    if not any(c["value"] == 0 and fc["events"][c["next"]]["name"] == "Event4" for c in nxt):
        bad.append(f"{rel}: the summit owl's talk isn't kept when neither Kakariko actor is there")
    return bad
