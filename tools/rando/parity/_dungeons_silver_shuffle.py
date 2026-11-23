"""OoT Randomizer's shuffle_silver_rupees 'remove', 'dungeon', 'regional', 'overworld', 'any_dungeon', 'anywhere' and
its silver-rupee pouches (silver_rupee_pouches_choice / silver_rupee_pouches), for the dungeons plugin.

Rooms are in data/rando/silver_rupees.json and this module's own data in
data/rando/silver_shuffle.json. Puzzle i is the i-th of sorted(silver_rupees.json "puzzles") (0 Bottom of the Well
... 15 Spirit Temple Sun Block).

How a puzzle gets solved without its tokens (data edits only):
- Save data (gamedata op). A saved Int per puzzle, COUNT ("Rando_SilverNum_<ii>", the puzzle's silver rupees held,
  0 on a new file and 5 with 'remove'), and an expression flag SOLVED ("Rando_SilverSolved_<ii>" = COUNT > 4,
  BoolExp opcodes 19/16, the way 137 vanilla expressions test an Int). It's an Int and not the recipe's 5 bits of a
  bool array, because then the credit adds 1 with GameDataActor.EventTriggerAddOrSubGameDataInt (the dungeon keys'
  own step), and no event ever writes a bool-array element by index (the recipe's T5 is gone).
  HaveEncountered_Token starts true, since the first-encounter appear events of the four rooms that gate on it link
  the counter, which may be absent.
- Each counter (17 placements, the barrier) gets a lazy negated Presence on its puzzle's SOLVED. It leaves the
  moment the puzzle is solved and is never placed again (the drops plugin's proven live Presence).
- The room's own done flags (silver_rupees.json "done") and its appear flags (silver_shuffle.json) get set when the
  count reaches 5 (new-file defaults with 'remove'). So the doors, the Spirit net, the Fire Trial pillars and the
  Ice Cavern blade react through their own live reads (Hold nodes), like after a vanilla solve.
  The Gerudo Training Ground boulder room's done flag is never set, because it deletes both token groups
  (Room_02_Prefab_e14a nodes 0 -> 3/4 -> PrefabAllDelete), so the room keeps its 5 spots. Its only other reader is
  the room's map step (_08f2 TriggerDungeonRoomStepClear), which then stays uncleared. The recipe's e14a input edit
  would point node 0 at a bool-array element, but ainb.set_input keeps the 0x1000000 flag of the vanilla -1 index,
  which every vanilla constant index >= 0 lacks. So that's not used, see my research note.
- The shuffled values ('dungeon' ... 'anywhere') also edit the shared counter AI
  (AI/Obj_silverRupeeCounter.root.ainb, every pack holding it). The child of the Update Simultaneous that reports
  AllGet to the room logic (node 7, ExecuteLogicSetBool 'AllGet') becomes a copied ExecuteGenericDummyAction, so
  picking up the 5 tokens of a room opens nothing (no unlock event, no vanilla done flags, no Vanish). The on-load
  selector's "no live token left" case (node 2 case 0 -> node 3 delete) goes to the default instead (node 34,
  stand in front of the shutter), so an unsolved room keeps its barrier after its tokens are taken. The tokens stay
  linked: appear flight, sparkle, count lights (which count the tokens taken in the room, not the silver rupees
  held, recipe K). No per-frame cost is added (one Execute node swapped for a dummy, one selector case
  retargeted). 'remove' needs no AI edit since no counter is placed.
- The 80 tokens are OoTR's 80 silver-rupee locations. OoTR fills them from the pool ('remove' puts the rupees' junk
  in the pool, the other values the rupees themselves). remake_silver_rupee_items' machinery gives their items
  (_dungeons_silver: token Names, the token AI's scene request, one scene comparing the names), with OoTR's own
  location as spot n. The Gerudo Training Ground boulder room's two token sets stand at the same 5 spots. Each spot
  is given once (a saved Int per spot, Rando_SilverGtg_<n>, set after the give, and the scene ends right away when
  it's set), and both twins get a lazy negated Presence on it (Rando_SilverGtgChk_<n> = Int > 0), so the other
  side's token is gone too.
- The items. "Silver Rupee (P)" and "Silver Rupee Pouch (P)" are dungeon items of the dungeons plugin (its carriers,
  chest scenes, scene-location calls, hideout and spot gives). Each one's Dm_SY_GetInEvent entry (host_graph:
  Rando_DI_Silver_<ii> / Rando_DI_SilverPouch_<ii>) calls a GetPouchContent entry, which has GameDataActor and
  SystemTextNPC. A rupee adds 1 to COUNT, shows OoTR's get text with the count ("You have found N so far!", one
  message per count, every language), and at 5 or more sets the done and appear flags. A pouch sets COUNT to 5,
  shows its text and sets them. Back in Dm_SY_GetInEvent the solved jingle (EventTriggerSoundReadRiddle, the unlock
  flows' own) plays when SOLVED holds.
  Link holds the silver rupee up first. That's the display actor Rando_Show_SilverRupee (config/hold_up.json
  "displays", Obj_Rupee_Silver's model) with the locator, pose, fanfare and glow of a rupee (HOLD_AS, since a
  silver rupee has no pouch row), then the credit, then it's put away. A big chest's cinematic shows the same
  display (SHOW_ENTRY) and the _Big entry gives without a second hold-up. Its fanfare is a rupee's
  (silver_shuffle.json fanfare_model). In the air or water (a resident get scene, dungeons.resident_give) nothing is
  held up for any item, and the credit's own message is the silver rupee's window.
- Where they can be: everywhere OoTR puts them (the dungeons plugin's allowed, so every chest that runs the
  dungeon-item scene, every scene-given location, the hideout guards and OoTR's silver-rupee locations themselves).
Logic is OoTR's own (the room opens exactly when OoTR's 5 items, or the pouch, are held), with one remake rule. We
don't know which remake token is which OoTR location of its puzzle, so each of a puzzle's locations needs all of
them reachable (the group rule remake_silver_rupee_items uses). That's never looser than OoTR's.
Read-back: verify() (parity/_gaps_check.py READERS "silver_rupees").
"""
import json
import os
import re
import sys

from . import _dungeons_silver as silver

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = json.load(open(os.path.join(HERE, "data", "rando", "silver_shuffle.json"), encoding="utf-8"))
PUZZLES = silver.PUZZLES
ORDER = sorted(PUZZLES)
SHUFFLED = ("dungeon", "regional", "overworld", "any_dungeon", "anywhere")  # the rupees are items (credited)
MODES = ("remove",) + SHUFFLED
KINDS = ("Silver Rupee", "Silver Rupee Pouch")
ITEMS = [f"{k} ({p})" for p in ORDER for k in KINDS]
CARRIERS = DATA["carriers"]
if len(CARRIERS) != len(ITEMS) or len(set(CARRIERS)) != len(CARRIERS):
    raise RuntimeError("data/rando/silver_shuffle.json: one distinct carrier per silver-rupee item")
if sorted(DATA["puzzles"]) != ORDER:
    raise RuntimeError("data/rando/silver_shuffle.json: puzzles differ from data/rando/silver_rupees.json")
MODEL = "Obj_Rupee_Silver"  # what a scene location's reward names (scene_call_ops gives through the call)
FANFARE = DATA["fanfare_model"]
COUNT = "Rando_SilverNum_{:02d}"
SOLVED = "Rando_SilverSolved_{:02d}"
GTG = silver.GTG
GTG_TAKEN = silver.GTG_TAKEN  # silver.give_once gives each boulder-room spot once, in every value
GTG_CHK = "Rando_SilverGtgChk_{}"
INT_GT, INT_CONST = 19, 16  # BoolExp opcodes (_story_conditions)
HOST_FILE = "Dm_SY_GetInEvent"
MSG_FILE = "GetPouchContent"
MSBT = "EventFlowMsg/Dm_SY_Get.msbt"
COUNTER_AI = DATA["counter_ai"]
JINGLE = {"actor": "SoundSystemActor", "action": "EventTriggerSoundReadRiddle",
          "params": {"IsWaitEnd": True, "BgmReadRiddleType": 0}}
HL, END = "{tag:0,3,0000}", "{tag:0,3,ffff}"  # the game's highlight colour (as the ice trap's FOOL)
WIDTH = 46  # characters a line (vanilla boxes: about 52, 3 lines; data/rando/hints_targets.json)
YES, NO = 0, 1
BELOW, EQUAL, ABOVE = 0, 1, 2  # EventQueryIsGameDataInt answers
_state = {"credit": False}


# Settings
def value(settings):
    return getattr(settings, "shuffle_silver_rupees", "vanilla")


def active(settings):
    return value(settings) in MODES


def credited(settings):
    return value(settings) in SHUFFLED


def before_build(settings):
    _state["credit"] = credited(settings)


def untested(settings):
    if not active(settings):
        return []
    out = [f"dungeons: shuffle_silver_rupees {value(settings)!r} - each counter has a lazy negated Presence on its "
           f"puzzle's solved expression (Int > 4); the tokens of a room whose counter is absent are taken (T1), the "
           f"OoTR silver-rupee locations are given by the token scene; Gerudo Training Ground boulder room: each spot "
           f"once, its twin removed (T6)"]
    if credited(settings):
        out.append("dungeons: silver rupees as items - the counter AI never reports AllGet and keeps its barrier with "
                   "no token left (T3); each silver rupee adds 1 to a saved Int (GetPouchContent text, done and appear "
                   "flags at 5, the solved jingle); a big chest shows nothing above Link")
    return out


def dungeon_item(name):
    """(kind, puzzle) for a silver-rupee item while a credited value is on (before_build), else None."""
    if not _state["credit"]:
        return None
    m = re.fullmatch(r"(Silver Rupee(?: Pouch)?) \((.+)\)", name or "")
    if not m or m.group(2) not in PUZZLES:
        return None
    return m.group(1), m.group(2)


def index(puzzle):
    return ORDER.index(puzzle)


def host_entry(item):
    kind, puzzle = re.fullmatch(r"(Silver Rupee(?: Pouch)?) \((.+)\)", item).groups()
    return ("Rando_DI_SilverPouch_" if kind == KINDS[1] else "Rando_DI_Silver_") + f"{index(puzzle):02d}"


def _msg_entry(item):
    return host_entry(item).replace("Rando_DI_", "Rando_SR_")


def message_call(item):
    """The GetPouchContent entry crediting `item` (also callable from the resident get scenes: dungeons.resident_give)."""
    return f"{MSG_FILE}:{_msg_entry(item)}"


# Locations
SPOTS = set()  # OoTR's 80 silver-rupee locations while a value here is on (keep_locations), for dungeons.allowed


def spots():
    """[(puzzle, n, OoTR location, token name, [token hashes])]. OoTR's n-th silver-rupee location of the puzzle
    (sorted by name) is the remake's n-th spot (silver_rupees.json token order, the counter's links)."""
    out = []
    for puzzle, n, _, token, hashes in silver.spots():
        out.append((puzzle, n, silver.ootr_locations(puzzle)[n - 1], token, hashes))
    return out


def keep_locations(world, settings):
    SPOTS.clear()
    if not active(settings):
        return set()
    names = {loc.name for loc in world.get_locations()}
    out = {s[2] for s in spots()}
    missing = sorted(out - names)
    if missing:
        raise RuntimeError(f"shuffle_silver_rupees: OoTR silver-rupee locations missing from the world: {missing[:3]}")
    SPOTS.update(out)
    return out


def before_fill(world, settings):
    """The group rule (each of a puzzle's locations needs every one of them reachable) and the spot item rule."""
    if not active(settings):
        return
    from Location import Location
    from Item import make_event_item
    for puzzle in ORDER:
        locs = [world.get_location(n) for n in silver.ootr_locations(puzzle)]
        events = []
        for k, loc in enumerate(locs, 1):
            ev = f"Remake silver rupee {puzzle} {k}"
            ev_loc = Location(f"{ev} from {loc.parent_region.name}", location_type="Event", parent=loc.parent_region)
            ev_loc.rule_string = loc.rule_string
            ev_loc.access_rule = loc.access_rule
            ev_loc.world = world
            loc.parent_region.locations.append(ev_loc)
            make_event_item(ev, ev_loc)
            events.append(ev)
        rule = " and ".join(f"'{e}'" for e in events)
        for loc in locs:
            if loc.item is not None or loc.locked:
                continue
            loc.rule_string = rule
            world.parser.parse_spot_rule(loc)
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: silver.givable(item.name) and prev(location, item))
    world._cached_locations = []


# Scenes
def _wrap(tokens):
    """Lines of at most WIDTH characters from (text, highlighted[, kept whole]) tokens. A highlighted or kept token
    never breaks."""
    words = []
    for text, hl, *keep in tokens:
        if hl or keep:
            words.append((text, hl))
        else:
            words += [(w, False) for w in text.split(" ") if w]
    lines, cur, length = [], [], 0
    for w, hl in words:
        if cur and length + 1 + len(w) > WIDTH:
            lines.append(cur)
            cur, length = [], 0
        length += len(w) + (1 if cur else 0)
        cur.append(HL + w + END if hl else w)
    if cur:
        lines.append(cur)
    if len(lines) > 3:
        raise RuntimeError(f"silver-rupee text over 3 lines: {lines}")
    return "\n".join(" ".join(x) for x in lines)


def messages(puzzle, kind):
    """{label: markup}: OoTR's get text (data/lang/English/property.json wording) for a rupee (one per count 1..5)
    or the pouch."""
    room, i = DATA["puzzles"][puzzle]["room"], index(puzzle)
    if kind == KINDS[1]:
        return {f"Rando_SRP_{i:02d}": _wrap([("You found a", False), ("Pouch of Silver Rupees", True),
                                             (f"for the {room}!", False)])}
    return {f"Rando_SR_{i:02d}_{n}": _wrap([("You found a", False), ("Silver Rupee", True),
                                            (f"for the {room}! You have found", False), (str(n), True),
                                            ("so far!", False, True)]) for n in range(1, 6)}


def _message_id(label):
    return f"{MSBT[:-len('.msbt')]}:{label}"


def flags_on_solve(puzzle):
    """The saved Bools a vanilla solve leaves true (done and appear flags), minus those this module never sets."""
    skip = set(DATA["puzzles"][puzzle].get("skip_done", ()))
    return [f for f in PUZZLES[puzzle]["done"] if f not in skip] + list(DATA["puzzles"][puzzle]["appear"])


def _talk(label, nxt):
    from . import _chests_scenes as scenes  # GetPouchContent's get messages' own talk settings
    return {"actor": "SystemTextNPC", "action": "EventTalk",
            "params": dict(scenes.TALK_PARAMS, MessageId=_message_id(label)), "next": nxt}


def _set_true(name, nxt):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
            "params": {"Index": -1, "GameDataName": name, "Value": True}, "next": nxt}


def _solve_steps(n, puzzle, first):
    """Nodes setting the puzzle's done and appear flags from `first`; returns the first label (None if none)."""
    flags = flags_on_solve(puzzle)
    for k, f in enumerate(flags):
        n[f"{first}{k}"] = _set_true(f, f"{first}{k + 1}" if k + 1 < len(flags) else None)
    return f"{first}0" if flags else None


def message_graph(item):
    """(entry, nodes, start) in GetPouchContent: the count, the text, the room's flags at 5."""
    kind, puzzle = re.fullmatch(r"(Silver Rupee(?: Pouch)?) \((.+)\)", item).groups()
    count, msgs, n = COUNT.format(index(puzzle)), list(messages(puzzle, kind)), {}
    if kind == KINDS[1]:
        n["set"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                    "params": {"Index": -1, "GameDataName": count, "Value": 5}, "next": "talk"}
        n["talk"] = _talk(msgs[0], None)
        n["talk"]["next"] = _solve_steps(n, puzzle, "done")
        return _msg_entry(item), n, "set"
    n["add"] = {"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt",
                "params": {"Index": -1, "GameDataName": count, "Value": 1}, "next": "settle"}
    from write_read_check import settle  # the add lands a frame or two later, so read the count after it
    n["settle"] = settle("is1")
    for v in range(1, 5):  # the count after the add: 1..4 exactly, or 5 and up
        n[f"is{v}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                       "params": {"Index": -1, "GameDataName": count, "Value": v},
                       "cases": {BELOW: f"talk{max(v - 1, 1)}", EQUAL: f"talk{v}",
                                 ABOVE: f"is{v + 1}" if v < 4 else "talk5"}}
    for v in range(1, 6):
        n[f"talk{v}"] = _talk(msgs[v - 1], None)
    n["talk5"]["next"] = _solve_steps(n, puzzle, "done")
    return _msg_entry(item), n, "add"


# The hold-up
# Link holds up the silver rupee's own display actor, like for every other item. That's config/hold_up.json
# "displays" Rando_Show_SilverRupee, an item-get actor of ours with Obj_Rupee_Silver's model (progressive.display_ops).
# The locator, pose, fanfare and glow steps look their ActorName up in the pouch tables (Dm_SY_GetInEvent
# GetInEvent_SetLocator Event253/Event268, GetInEvent_Animation Event277/Event279 EventQueryPouchContentGetType;
# Item_Position Event186 fanfare, Event79 glow), and a silver rupee has no row there (RSDB/PouchActorInfo has no
# Obj_Rupee_Silver and no Obj_RupeeToken_Silver). So they name HOLD_AS, a rupee the game hands over with these
# routines itself (PouchGetType Small, so the small-item locator and pose and a rupee's fanfare and glow). There's no
# pouch add and no get window. The credit's own message ("You found N so far") is the item's text.
DISPLAY = "Rando_Show_SilverRupee"
HOLD_AS = "Obj_Rupee_Red"
SHOW_ENTRY = "Rando_DI_ShowSilver"  # a big chest's show of the silver rupee (dungeons.show_graph)
BIG_SUFFIX = "_Big"


def host_graph(item, big=False):
    """(entry, nodes, start) in Dm_SY_GetInEvent for silver-rupee item `item` (dungeons.host_graphs). In order:
    - the display held up (Event109 create with Actor DISPLAY; Event289 locator, Event290 pose, Event112 fanfare and
      glow with ActorName HOLD_AS)
    - the GetPouchContent entry (count, text, the room's flags at 5)
    - the item put away (Event80's fork: Event105 delete, Event700/Event84 glow off)
    - the solved jingle when the puzzle is solved, and Navi's return (Event240, Event243)
    big=True gives the entry after a big chest's cinematic. That already shows the display (SHOW_ENTRY), so there's
    no second hold-up."""
    puzzle = re.fullmatch(r"Silver Rupee(?: Pouch)? \((.+)\)", item).group(1)
    n = {"show": {"copy": "Event109", "params_over": {"Actor": DISPLAY}, "next": "loc"},
         "loc": {"copy": "Event289", "params_over": {"ActorName": HOLD_AS}, "next": "anim"},
         "anim": {"copy": "Event290", "params_over": {"ActorName": HOLD_AS}, "next": "pos"},
         "pos": {"copy": "Event112", "params_over": {"ActorName": HOLD_AS}, "next": "credit"},
         "credit": {"call": f"{MSG_FILE}:{_msg_entry(item)}", "next": "putaway"},
         "putaway": {"copy": "Event80", "fork": ["delete", "wait"], "join": "joined"},
         "delete": {"copy": "Event105", "next": None},
         "wait": {"copy": "Event700", "next": "glowoff"},
         "glowoff": {"copy": "Event84", "next": None},
         "joined": {"copy": "Event82", "next": "solved"},
         "solved": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                    "params": {"GameDataName": SOLVED.format(index(puzzle))}, "cases": {YES: "jingle", NO: "navi"}},
         "jingle": dict(JINGLE, next="navi"),
         "navi": {"copy": "Event240", "next": "navi2"},
         "navi2": {"copy": "Event243", "next": None}}
    if big:
        for label in ("show", "loc", "anim", "pos"):
            del n[label]
        return host_entry(item) + BIG_SUFFIX, n, "credit"
    return host_entry(item), n, "show"


def show_graph():
    """(entry, nodes, start) in Dm_SY_GetInEvent that shows the silver rupee's display above Link the way a big chest
    shows its contents. Same steps as dungeons.show_graph (Event109 create, Event686 model detail, Event51 show with
    the rotating get animation, Event79 glow), with the create naming DISPLAY and the glow HOLD_AS."""
    n = {"show": {"copy": "Event109", "params_over": {"Actor": DISPLAY}, "next": "lod"},
         "lod": {"copy": "Event686", "next": "fire"},
         "fire": {"copy": "Event51", "next": "glow"},
         "glow": {"copy": "Event79", "params_over": {"ActorName": HOLD_AS}, "next": None}}
    return SHOW_ENTRY, n, "show"


# Plan
def _counter_edits(fs):
    """The shared counter AI edit (shuffled values), checked against the vanilla file first."""
    import ainb
    from romtools import sarc_files
    c = COUNTER_AI
    a = ainb.Ainb(sarc_files(fs.read(c["pack"]))[c["file"]])
    kids = a.nodes[c["update"]]["plugs"][ainb.PLUG_CHILD]
    sel = a.nodes[c["count_selector"]]["plugs"][ainb.PLUG_CHILD]
    want = {c["allget"]: "ExecuteLogicSetBool", c["dummy"]: "ExecuteGenericDummyAction",
            c["delete"]: "OneShotGenericDeleteThisActor", c["update"]: "Simultaneous"}
    for i, name in want.items():
        got = a.nodes[i]["name"] or ainb.NODE_TYPES.get(a.nodes[i]["type"])
        if got != name and ainb.NODE_TYPES.get(a.nodes[i]["type"]) != name:
            raise RuntimeError(f"{c['file']}: node {i} is {got}, not {name} (game update?)")
    plug = [s for s in a.nodes[c["allget"]]["inputs"]["string"] if s["name"] == "PlugName"]
    if kids[c["allget_child"]]["node"] != c["allget"] or not plug or plug[0]["value"] != "AllGet":
        raise RuntimeError(f"{c['file']}: node {c['update']} child {c['allget_child']} no longer reports AllGet")
    if [p_["node"] for p_ in sel] != [c["delete"], c["stay"]]:
        raise RuntimeError(f"{c['file']}: node {c['count_selector']} no longer deletes the counter with no token left")
    src = {"pack": c["pack"], "file": c["file"]}
    return [{"copy": {"from": src, "nodes": [c["dummy"]], "label": "dummy", "follow": False}},
            {"set_child": {"parent": c["update"], "which": c["allget_child"], "child": f"dummy:{c['dummy']}"}},
            {"set_child": {"parent": c["count_selector"], "which": 0, "child": c["stay"]}}]


def _kinds(world):
    """{puzzle: "Silver Rupee" | "Silver Rupee Pouch"}: which item the seed holds for each puzzle (OoTR's pool)."""
    out = {}
    for loc in world.get_locations():
        d = dungeon_item(loc.item.name) if loc.item is not None else None
        if d is not None:
            out.setdefault(d[1], d[0])
    return out


def world_plan(settings, world):
    """Plan sections for an active value, else {}. dungeons.world_plan merges them, and its _used then holds the silver
    items the seed gives, for its chest scenes and call entries, and note_routes records them. With 'vanilla' it's
    remake_silver_rupee_items' save rows and read-back note (_dungeons_silver.extras), if that's on."""
    if not active(settings):
        return silver.extras(world)
    from romtools import Romfs
    import drops as drop_tools
    fs = Romfs(drop_tools.DEFAULT_ROMFS, os.path.join(HERE, "original"))
    mode, credit = value(settings), credited(settings)
    kinds = _kinds(world) if credit else {}
    defaults, ints, exps = {"HaveEncountered_Token": True}, {}, {}
    for i, p in enumerate(ORDER):
        ints[COUNT.format(i)] = 0 if credit else 5
        exps[SOLVED.format(i)] = [[INT_GT, COUNT.format(i)], [INT_CONST, 4]]
        if not credit:
            defaults.update({f: True for f in flags_on_solve(p)})
    for n in range(1, 6):
        ints[GTG_TAKEN.format(n)] = 0
        exps[GTG_CHK.format(n)] = [[INT_GT, GTG_TAKEN.format(n)], [INT_CONST, 0]]
    placements, items, spot_note = [], [], {}
    for p in ORDER:
        f = PUZZLES[p]["file"]
        for h in PUZZLES[p]["counters"]:
            placements.append({"file": f, "hash": h, "set": {"Presence": {
                "FlagName": SOLVED.format(index(p)), "IsCheckLazy": True, "IsNegation": True}},
                "note": f"silver rupees: {p} counter (barrier) gone once solved"})
    for puzzle, n, loc, token, hashes in spots():
        item = world.get_location(loc).item.name
        items.append((token, item, PUZZLES[puzzle].get("give") == "window"))
        f = PUZZLES[puzzle]["file"]
        for h in hashes:
            s = {"Name": token}
            if puzzle == GTG:
                s["Presence"] = {"FlagName": GTG_CHK.format(n), "IsCheckLazy": True, "IsNegation": True}
            placements.append({"file": f, "hash": h, "set": s})
        spot_note[token] = {"location": loc, "item": item, "file": f, "tokens": list(hashes),
                            "gtg": n if puzzle == GTG else None}
    nodes, start = silver.scene_graph(items)
    for k, (token, _, _) in enumerate(items):
        g = nodes[f"give{k}"]
        spot_note[token]["give"] = {"call": g["call"], "actor": (g.get("params") or {}).get("ActorName")}
        if spot_note[token]["gtg"] is not None:  # the boulder room: each spot once (the twin is the other side's)
            silver.give_once(nodes, k, spot_note[token]["gtg"])
    sf = silver.DATA["scene_file"]
    plan = {
        "gamedata": {"defaults": defaults, "add_ints": ints, "add_boolexp": exps},
        "placements": placements,
        "ainb": [{"pack": pk, "file": silver.DATA["token_ai"], "edits": silver.ai_edits(silver._sources())}
                 for pk in silver.DATA["token_ai_packs"]],
        "events": [{"file": sf, "flowchart": sf, "add_graph": silver.DATA["scene_entry"], "nodes": nodes,
                    "start": start}],
        "byml": [{"file": "RSDB/EventSetting.Product.111.rstbl.byml.zs", "replace_row": {
            "row": silver.DATA["scene_row"], "copy_of": silver.DATA["scene_row_settings_from"],
            "set": {"FlowchartFileName": f"Work/Event/EventFlow/{sf}.evfc",
                    "EntryPointName": silver.DATA["scene_entry"],
                    "EventSettingComponentList": silver.SCENE_COMPONENTS}}}],  # _dungeons_silver "Taken in the air"
        "text": [],
        "_notes_dungeons_silver": [f"{v['location']}: {v['item']} (token{'s' if len(v['tokens']) > 1 else ''} "
                                   f"{', '.join(v['tokens'])} named {t})" for t, v in spot_note.items()],
    }
    if credit:
        plan["ainb"].append({"pack": "*", "file": COUNTER_AI["file"], "edits": _counter_edits(fs)})
    msgs = {}
    for p, kind in sorted(kinds.items()):
        item = f"{kind} ({p})"
        entry, mn, mstart = message_graph(item)
        plan["events"].append({"file": MSG_FILE, "flowchart": MSG_FILE, "add_graph": entry, "nodes": mn,
                               "start": mstart})
        for label, markup in messages(p, kind).items():
            msgs[label] = markup
            plan["text"].append({"lang": "*", "file": MSBT, "label": label, "markup": markup, "add": True,
                                 "note": f"{item}: OoTR's get text"})
    plan["_gaps"] = {"silver_rupees": {
        "mode": mode, "credit": credit, "kinds": kinds,
        "puzzles": {p: {"index": index(p), "count": COUNT.format(index(p)), "solved": SOLVED.format(index(p)),
                        "default": 0 if credit else 5, "file": PUZZLES[p]["file"], "counters": PUZZLES[p]["counters"],
                        "flags": flags_on_solve(p)} for p in ORDER},
        "gtg": {str(n): {"taken": GTG_TAKEN.format(n), "chk": GTG_CHK.format(n)} for n in range(1, 6)},
        "gtg_done_kept": DATA["puzzles"][GTG].get("skip_done", []),
        "spots": spot_note, "defaults": defaults,
        "scene": {"file": sf, "entry": silver.DATA["scene_entry"], "row": silver.DATA["scene_row"]},
        "token_ai": {"file": silver.DATA["token_ai"], "packs": silver.DATA["token_ai_packs"],
                     "pickup": silver.DATA["token_pickup_node"]},
        "counter_ai": COUNTER_AI if credit else None,
        "messages": msgs,
        "routes": {}}}
    return plan


def note_routes(plan, used, dg):
    """Called by dungeons.world_plan (module dg) once its scenes are known. Records how each silver-rupee item is
    given (its chest scenes, its scene-location call entry) for the read-back."""
    note = (plan.get("_gaps") or {}).get("silver_rupees")
    if note is None:
        return
    routes = {}
    for way, its in sorted(used.items()):
        for item in sorted(its):
            if dungeon_item(item) is None:
                continue
            r = routes.setdefault(item, {"host": host_entry(item), "message": _msg_entry(item), "chests": {},
                                         "call": None, "carrier": dg.CARRIER[item]})
            if way == "call":
                r["call"] = dg.call_entry(item)
            else:
                r["chests"][way] = {"file": dg.CHEST_FILE[way], "entry": dg.SCENE_ENTRY[way], "row": dg.ROWS[way]}
    note["routes"] = routes




# Read-back
def dungeon_item_name(name):
    """(kind, puzzle) for a silver-rupee item name, whatever the settings (the read-back has no settings)."""
    m = re.fullmatch(r"(Silver Rupee(?: Pouch)?) \((.+)\)", name or "")
    return (m.group(1), m.group(2)) if m and m.group(2) in PUZZLES else None


def _flow(fs, name):
    from evfl import Evfl
    return next(f for f in Evfl(fs.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts if f["name"] == name)


class _Graph:
    """Steps of one flowchart, by index, with their actor action / query names and plain parameters."""

    def __init__(self, fc):
        self.fc, self.ev = fc, fc["events"]

    def at(self, i):
        from evfl_build import is_case_end  # a case's end goes through a do-nothing step (route_end_cases)
        e = self.ev[i] if i is not None and i != 0xFFFF and i < len(self.ev) else None
        return None if is_case_end(e) else e

    def entry(self, name):
        ep = self.fc["entry_points"].get(name)
        return None if ep is None else self.at(ep["main"])

    def what(self, e):
        if e is None or e["type"] not in ("action", "switch"):
            return None, None
        a = self.fc["actors"][e["actor"]]
        return a["name"], a["actions"][e["action"]] if e["type"] == "action" else a["queries"][e["query"]]

    @staticmethod
    def params(e):
        return {k: (v.get("value") if isinstance(v, dict) else v)
                for k, v in (((e or {}).get("params") or {}).get("items") or {}).items()}

    def case(self, e, value):
        return self.at(next((c["next"] for c in e.get("cases", []) if c["value"] == value), None))

    @staticmethod
    def call(e):
        return f"{e.get('flowchart') or ''}:{e['entry_point']}" if e is not None and e["type"] == "subflow" else None


def _walk_message(g, start, count_before):
    """Run a GetPouchContent message entry with the count at `count_before`. Returns (count after, message shown,
    [flags set]) or a problem string. A query reads the count as it was before a write until a wait of 2 frames or
    more (or a talk) has let the write land (write_read_check.py). Without the wait the count text runs one
    behind, like the Triforce count did in test_guardroom3."""
    e, count, shown, flags, steps = start, count_before, None, [], 0
    seen = count  # what a query reads now
    while e is not None and steps < 60:
        steps += 1
        if e["type"] == "action":
            _, act = g.what(e)
            p = g.params(e)
            if act == "EventTriggerAddOrSubGameDataInt":
                count += p.get("Value", 0)
            elif act == "EventTriggerSetGameDataInt":
                count = p.get("Value", 0)
            elif act == "EventTalk":
                shown = (p.get("MessageId") or "").split(":")[-1]
                seen = count  # a talk waits on the player, so the write has landed
            elif act == "EventWait":
                if (p.get("Frames") or 0) >= 2:
                    seen = count
            elif act == "EventTriggerSetGameDataBool" and p.get("Value") is True:
                flags.append(p.get("GameDataName"))
            else:
                return f"{e['name']}: unexpected step {act}"
            e = g.at(e["next"])
        elif e["type"] == "switch":
            _, q = g.what(e)
            if q != "EventQueryIsGameDataInt":
                return f"{e['name']}: unexpected query {q}"
            v = g.params(e).get("Value", 0)
            e = g.case(e, BELOW if seen < v else EQUAL if seen == v else ABOVE)
        else:
            return f"{e['name']}: unexpected step type {e['type']}"
    return count, shown, flags


def _spot_branches(g, entry, air=None):
    """{token name: (gives [(call, ActorName)], once-only Int or None, Ints set [(name, value)])} of the spot scene.
    `air` (a dict) gets each token's branch -> whether it calls _dungeons_silver.AIR_START before its first give.
    The call itself doesn't count as a give (see "Taken in the air" in _dungeons_silver)."""
    from parity._dungeons_silver import AIR_START
    out, e, steps = {}, g.entry(entry), 0
    while e is not None and steps < 200:
        steps += 1
        if g.what(e)[1] != "EventQueryIsGameDataString64":
            out["?"] = ([], f"{e['name']} is not a name compare", [])
            break
        token = g.params(e).get("Value")
        y, gives, once, sets, k = g.case(e, YES), [], None, [], 0
        while y is not None and k < 30:
            k += 1
            if y["type"] == "switch":
                if g.what(y)[1] == "EventQueryIsGameDataInt" and g.params(y).get("Value") == 0:
                    once = g.params(y).get("GameDataName")
                    if g.case(y, BELOW) is not None or g.case(y, ABOVE) is not None:
                        once = f"{once} (doesn't end when set)"
                    y = g.case(y, EQUAL)
                    continue
                break
            if y["type"] == "subflow" and g.call(y) == AIR_START:
                if air is not None and not gives:
                    air[token] = True
            elif y["type"] == "subflow":
                gives.append((g.call(y), g.params(y).get("ActorName")))
            elif y["type"] == "action" and g.what(y)[1] == "EventTriggerSetGameDataInt":
                sets.append((g.params(y).get("GameDataName"), g.params(y).get("Value")))
            y = g.at(y.get("next"))
        out[token] = (gives, once, sets)
        e = g.case(e, NO)
    return out


def _host_problems(host, entry, item, solved, held=True):
    """What's wrong with Dm_SY_GetInEvent `entry`, the hold-up for silver-rupee item `item` (host_graph, or with
    held=False the big chest's variant with no hold-up). It wants the display created first (Actor DISPLAY), the
    locator, pose and position steps named HOLD_AS, the credit call, the display put away, then the solved jingle when
    `solved` holds."""
    e = host.entry(entry)
    if e is None:
        return [f"{HOST_FILE}: no entry {entry}"]
    seq, forked, guard = [], [], 0
    while e is not None and guard < 64:
        guard += 1
        seq.append(e)
        if e["type"] == "fork":
            forked += [host.at(f) for f in e.get("forks", [])]
            j = host.at(e.get("join"))
            e = host.at(j.get("next")) if j is not None else None
        elif e["type"] == "switch":
            break
        else:
            e = host.at(e.get("next"))
    out = []
    calls = [_Graph.call(x) for x in seq]
    credit = f"{MSG_FILE}:{_msg_entry(item)}"
    if credit not in calls:
        return [f"{HOST_FILE}:{entry} doesn't call {credit}"]
    k = calls.index(credit)
    if held:
        first = host.what(seq[0])
        if first[1] != "EventCreateShowItemFromActorFileName" or host.params(seq[0]).get("Actor") != DISPLAY:
            out.append(f"{HOST_FILE}:{entry}: doesn't hold up {DISPLAY} first ({first})")
        named = [host.params(x).get("ActorName") for x in seq[1:k] if _Graph.call(x)]
        if [c.split(":")[-1] for c in calls[1:k] if c] != ["GetInEvent_SetLocator", "GetInEvent_Animation",
                                                           "Item_Position"] or set(named) != {HOLD_AS}:
            out.append(f"{HOST_FILE}:{entry}: the locator, pose and position before the credit aren't "
                       f"{HOLD_AS}'s ({calls[1:k]}, {named})")
    elif k != 0:
        out.append(f"{HOST_FILE}:{entry}: steps before the credit after a big chest's cinematic ({calls[:k]})")
    if not any(host.what(x)[1] == "EventDeleteShowItem" for x in forked if x is not None):
        out.append(f"{HOST_FILE}:{entry}: the display isn't put away after the credit")
    q = seq[-1] if seq[-1]["type"] == "switch" else None
    if q is None or host.what(q)[1] != "EventQueryIsGameDataBoolExp" or host.params(q).get("GameDataName") != solved \
            or host.what(host.case(q, YES))[1] != "EventTriggerSoundReadRiddle":
        out.append(f"{HOST_FILE}:{entry}: no solved jingle after the credit")
    return out


def verify(patch, note, romfs):
    """Reads the built patch back:
    - save rows (Ints, expressions, new-file defaults)
    - counter and token placements (Presence, Names)
    - the counter AI edit (or none for 'remove') and the token AI's scene request
    - the spot scene (each token gives its OoTR location's item, the boulder room's spots once)
    - each silver-rupee item's credit (count, text, flags at 5, jingle) and how each one is reached (chest scenes,
      scene-location call entries)
    - the boulder room's done flag is never set
    A 'vanilla' note (remake_silver_rupee_items, _dungeons_silver.world_plan) has no puzzles, counters or credit. Its
    tokens, scene and once-only boulder-room spots are read the same way, the counter AI has to be untouched and the
    boulder room's twins have no Presence."""
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from romtools import Romfs, sarc_files, byml_load, murmur3_32
    import ainb
    import packpaths
    bad = []
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    # Save data
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]["Data"]
    ints = {e["Hash"]: e for e in gd["Int"]}
    exps = {e["Hash"]: e for e in gd["BoolExp"]}
    bools = {e["Hash"]: e for e in gd["Bool"]}

    def exp_is(name, want):
        row = exps.get(murmur3_32(name))
        return row is not None and [[int(x) for x in st] for st in row["Values"]] == want
    for p, v in note.get("puzzles", {}).items():
        row = ints.get(murmur3_32(v["count"]))
        if row is None or int(row["SaveFileIndex"]) != 0 or int(row["DefaultValue"]) != v["default"]:
            bad.append(f"GameDataList: {v['count']} ({p}) is not a saved Int starting at {v['default']} ({row})")
        if not exp_is(v["solved"], [[INT_GT, murmur3_32(v["count"])], [INT_CONST, 4]]):
            bad.append(f"GameDataList: {v['solved']} is not {v['count']} > 4")
    for n, v in note["gtg"].items():
        row = ints.get(murmur3_32(v["taken"]))
        if row is None or int(row["SaveFileIndex"]) != 0 or int(row["DefaultValue"]) != 0:
            bad.append(f"GameDataList: {v['taken']} is not a saved Int starting at 0")
        if v["chk"] and not exp_is(v["chk"], [[INT_GT, murmur3_32(v["taken"])], [INT_CONST, 0]]):
            bad.append(f"GameDataList: {v['chk']} is not {v['taken']} > 0")
    for name, want in note.get("defaults", {}).items():
        row = bools.get(murmur3_32(name))
        if row is None or bool(row["DefaultValue"]) is not want:
            bad.append(f"GameDataList: new-file {name} is not {want}")
    for name in note.get("gtg_done_kept", []):
        row = bools.get(murmur3_32(name))
        if row is None or row["DefaultValue"]:
            bad.append(f"GameDataList: {name} must stay false on a new file (it deletes the boulder room's tokens)")
    # Placements
    levels = {}

    def actors(f):
        if f not in levels:
            levels[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f))[0].get("Actors") or []}
        return levels[f]
    for p, v in note.get("puzzles", {}).items():
        for h in v["counters"]:
            a = actors(v["file"]).get(h)
            want = {"FlagName": v["solved"], "IsCheckLazy": True, "IsNegation": True}
            if a is None or not str(a.get("Gyaml", "")).startswith("Obj_silverRupeeCounter") or a.get("Presence") != want:
                bad.append(f"{v['file']} #{h} ({p} counter): Presence {a and a.get('Presence')}, want {want}")
    named = set()
    for token, s in note["spots"].items():
        for h in s["tokens"]:
            a = actors(s["file"]).get(h)
            if a is None or a.get("Gyaml") != "Obj_RupeeToken_Silver" or a.get("Name") != token:
                bad.append(f"{s['file']} #{h}: not a silver token named {token}")
                continue
            named.add((s["file"], h))
            if s["gtg"] is not None and note["gtg"][str(s["gtg"])]["chk"]:
                want = {"FlagName": note["gtg"][str(s["gtg"])]["chk"], "IsCheckLazy": True, "IsNegation": True}
                if a.get("Presence") != want:
                    bad.append(f"{s['file']} #{h} (boulder room spot {s['gtg']}): Presence {a.get('Presence')}")
            elif "Presence" in a:
                bad.append(f"{s['file']} #{h}: a Presence it shouldn't have ({a['Presence']})")
    for f in sorted({s["file"] for s in note["spots"].values()}):
        extra = [h for h, a in actors(f).items() if str(a.get("Name", "")).startswith("RandoSilver")
                 and (f, h) not in named]
        if extra:
            bad.append(f"{f}: other placements named RandoSilver*: {extra}")
    # AI: the counter (shuffled values only) and the token pickup's scene request
    c = note.get("counter_ai")
    cpacks = packpaths.carriers(COUNTER_AI["file"], romfs)
    if not cpacks:
        bad.append(f"{COUNTER_AI['file']}: in no pack")
    for pk in cpacks:
        raw = sarc_files(fs.read(pk))[COUNTER_AI["file"]]
        if c is None:
            if raw != sarc_files(van.read(pk))[COUNTER_AI["file"]]:
                bad.append(f"{pk} {COUNTER_AI['file']}: edited, but 'remove' places no counter")
            continue
        a = ainb.Ainb(raw)
        kids = [pl["node"] for pl in a.nodes[c["update"]]["plugs"][ainb.PLUG_CHILD]]
        sel = [pl["node"] for pl in a.nodes[c["count_selector"]]["plugs"][ainb.PLUG_CHILD]]
        d = kids[c["allget_child"]] if len(kids) > c["allget_child"] else -1
        if d < 0 or a.nodes[d]["name"] != "ExecuteGenericDummyAction" or d == c["dummy"] or c["allget"] in kids:
            bad.append(f"{pk} {COUNTER_AI['file']}: node {c['update']} still reports AllGet (child "
                       f"{c['allget_child']} is node {d})")
        if len(kids) != 7:
            bad.append(f"{pk} {COUNTER_AI['file']}: node {c['update']} has {len(kids)} children, not 7")
        if sel != [c["stay"], c["stay"]]:
            bad.append(f"{pk} {COUNTER_AI['file']}: with no token left the counter doesn't stay ({sel})")
        if a.input_shape_problems():
            bad.append(f"{pk} {COUNTER_AI['file']}: input shapes {a.input_shape_problems()[:2]}")
    tai = note["token_ai"]
    for pk in tai["packs"]:
        a = ainb.Ainb(sarc_files(fs.read(pk))[tai["file"]])
        kids = [pl["node"] for pl in a.nodes[tai["pickup"]]["plugs"][ainb.PLUG_CHILD]]
        seqs = [k for k in kids if ainb.NODE_TYPES.get(a.nodes[k]["type"]) == "Sequential"
                and [a.nodes[x["node"]]["name"] for x in a.nodes[k]["plugs"][ainb.PLUG_CHILD]]
                == ["OneShotSetNonStructGameDataString64", "OneShotEventMemberRequestEventByEventName"]]
        if len(seqs) != 1:
            bad.append(f"{pk} {tai['file']}: the pickup step doesn't request the spot scene")
            continue
        req = a.nodes[a.nodes[seqs[0]]["plugs"][ainb.PLUG_CHILD][1]["node"]]
        ev = [x["value"] for x in req["inputs"]["string"] if x["name"] == "EventName"]
        if ev != [note["scene"]["row"]]:
            bad.append(f"{pk} {tai['file']}: the pickup requests {ev}, not {note['scene']['row']}")
        # The spot scene isn't resident, so the token registers it for loading when it appears.
        # That way it works in every dungeon (see PRELOAD_SRC in _dungeons_silver).
        from parity._dungeons_silver import token_enter
        pre = [a.nodes[pl["node"]] for pl in a.nodes[token_enter(a)]["plugs"][ainb.PLUG_CHILD]
               if a.nodes[pl["node"]]["name"] == "OneShotBeforehandLoadEventRequestRegister"]
        if [[x["value"] for x in n["inputs"]["string"] if x["name"] == "EventName"] for n in pre] != [[note["scene"]["row"]]]:
            bad.append(f"{pk} {tai['file']}: the token doesn't register {note['scene']['row']} for loading when it "
                       f"appears (the spot scene then plays only where its flowchart is loaded anyway)")
    # The spot scene and its scene ID
    rows = byml_load(fs.read("RSDB/EventSetting.Product.111.rstbl.byml.zs"), allow_big=True)[0]
    rows = rows if isinstance(rows, list) else rows.get("Rows", rows.get("rows", []))
    row = next((r for r in rows if isinstance(r, dict) and r.get("__RowId") == note["scene"]["row"]), None)
    if row is None or row.get("EntryPointName") != note["scene"]["entry"] or \
            not str(row.get("FlowchartFileName", "")).endswith(f"/{note['scene']['file']}.evfc"):
        bad.append(f"EventSetting {note['scene']['row']}: not {note['scene']['file']}:{note['scene']['entry']}")
    # Taken in the air (see _dungeons_silver). The scene plays even though Link dissents (in the air, on the
    # Hookshot), and each branch settles him (Common:AirStartUp) before it gives.
    from parity._dungeons_silver import SCENE_COMPONENTS, AIR_START
    if row is not None and row.get("EventSettingComponentList") != SCENE_COMPONENTS:
        bad.append(f"EventSetting {note['scene']['row']}: settings {str(row.get('EventSettingComponentList')).split('/')[-1]}"
                   f", not {SCENE_COMPONENTS.split('/')[-1]}: a silver rupee taken in the air (Link can't join a plain "
                   f"flowchart event) gives nothing")
    air = {}
    branches = _spot_branches(_Graph(_flow(fs, note["scene"]["file"])), note["scene"]["entry"], air)
    no_air = sorted(t for t in note["spots"] if t in branches and not air.get(t))
    if no_air:
        bad.append(f"{note['scene']['file']}: {len(no_air)} spot branches (e.g. {no_air[0]}) give without {AIR_START} "
                   f"after the player start (Link in the air isn't settled first, as Dm_SY_Get does)")
    if "?" in branches:
        bad.append(f"{note['scene']['file']}: {branches['?'][1]}")
    for token, s in note["spots"].items():
        gives, once, sets = branches.get(token, (None, None, None))
        if gives is None:
            bad.append(f"{note['scene']['file']}: no branch for {token} ({s['location']})")
            continue
        want = (s["give"]["call"], s["give"]["actor"])
        if gives != [want]:
            bad.append(f"{note['scene']['file']}: {token} ({s['location']}: {s['item']}) gives {gives}, want {[want]}")
        if s["gtg"] is not None:
            t = note["gtg"][str(s["gtg"])]["taken"]
            if once != t or sets != [(t, 1)]:
                bad.append(f"{note['scene']['file']}: boulder room {token} isn't given once ({once}, {sets})")
        elif once is not None or sets:
            bad.append(f"{note['scene']['file']}: {token} has a once-only check ({once}, {sets})")
        r = note["routes"].get(s["item"])
        if dungeon_item_name(s["item"]) and note["credit"] and (r is None or want[0] != f"{HOST_FILE}:{r['call']}"):
            bad.append(f"{note['scene']['file']}: {token} ({s['item']}) isn't given by its credit entry")
    # Each silver-rupee item: its host and message entries, and how it's reached
    if note["credit"]:
        host, msg = _Graph(_flow(fs, HOST_FILE)), _Graph(_flow(fs, MSG_FILE))
        for p, kind in sorted(note["kinds"].items()):
            item, v = f"{kind} ({p})", note["puzzles"][p]
            r = note["routes"].get(item) or {}
            for suffix in ("", BIG_SUFFIX) if r.get("chests", {}).get("big") else ("",):
                bad += _host_problems(host, host_entry(item) + suffix, item, v["solved"], held=not suffix)
            start = msg.entry(_msg_entry(item))
            if start is None:
                bad.append(f"{MSG_FILE}: no entry {_msg_entry(item)}")
                continue
            labels = list(messages(p, kind))
            if any(note["messages"].get(lb) is None for lb in labels):
                bad.append(f"{item}: its text labels {labels} are not all planned")
            for before in ([0, 3] if kind == KINDS[1] else range(0, 6)):
                r = _walk_message(msg, start, before)
                if isinstance(r, str):
                    bad.append(f"{MSG_FILE}:{_msg_entry(item)}: {r}")
                    break
                after, shown, flags = r
                want_after = 5 if kind == KINDS[1] else before + 1
                want_msg = labels[0] if kind == KINDS[1] else labels[min(want_after, 5) - 1]
                want_flags = v["flags"] if want_after >= 5 else []
                if after != want_after or shown != want_msg or flags != want_flags:
                    bad.append(f"{MSG_FILE}:{_msg_entry(item)} with {before} held: count {after}, text {shown}, "
                               f"flags {flags}; want {want_after}, {want_msg}, {want_flags}")
                if set(flags) & set(note.get("gtg_done_kept", [])):
                    bad.append(f"{MSG_FILE}:{_msg_entry(item)} sets the boulder room's done flag")
            r = note["routes"].get(item)
            if r is None:
                bad.append(f"{item}: given nowhere this seed (no chest scene or call entry asked for it)")
                continue
            if r["call"] and _Graph.call(host.entry(r["call"])) != f":{host_entry(item)}":
                bad.append(f"{HOST_FILE}:{r['call']} doesn't call {host_entry(item)} "
                           f"({_Graph.call(host.entry(r['call']))})")
            for way, ch in r["chests"].items():
                cg = _Graph(_flow(fs, ch["file"]))
                hits, shows = [], []
                want = f"{HOST_FILE}:{host_entry(item)}" + (BIG_SUFFIX if way == "big" else "")
                for ev in cg.ev:
                    if cg.what(ev)[1] == "EventQueryIsGameDataString64" and cg.params(ev).get("Value") == r["carrier"]:
                        y = cg.case(ev, YES)
                        if _Graph.call(y) == want:
                            hits.append(ev["name"])
                        elif _Graph.call(y) == f"{HOST_FILE}:{SHOW_ENTRY}":
                            shows.append(ev["name"])
                        elif _Graph.call(y) and ":Rando_DI_Show" in _Graph.call(y):
                            bad.append(f"{ch['file']}: {item} shows another item's model ({_Graph.call(y)})")
                if not hits:
                    bad.append(f"{ch['file']}: no branch from carrier {r['carrier']} to {want} ({item}, {way} chests)")
                if way == "big":  # the cinematic shows the silver rupee's display, held by the _Big entry
                    sg = host.entry(SHOW_ENTRY)
                    if not shows:
                        bad.append(f"{ch['file']}: {item}'s cinematic doesn't show {SHOW_ENTRY}")
                    elif host.what(sg)[1] != "EventCreateShowItemFromActorFileName" or \
                            host.params(sg).get("Actor") != DISPLAY:
                        bad.append(f"{HOST_FILE}:{SHOW_ENTRY} doesn't create {DISPLAY}")
                srow = next((x for x in rows if isinstance(x, dict) and x.get("__RowId") == ch["row"]), None)
                if srow is None or srow.get("EntryPointName") != ch["entry"]:
                    bad.append(f"EventSetting {ch['row']}: not the {way} chests' dungeon-item scene {ch['entry']}")
    return bad
