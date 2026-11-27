"""Silver-rupee spots that also give a seed item (remake setting remake_silver_rupee_items, dungeons plugin).

The facts per room are in data/rando/silver_rupees.json.

OoTR's shuffle_silver_rupees values other than 'vanilla' (and its pouches) live in _dungeons_silver_shuffle.py. That
one keeps a saved count per puzzle with the counter leaving on a Presence at 5, and it reuses this module's token
Names, token AI edit and scene, with OoTR's own silver-rupee locations as the spots. A room counts its silver rupees
in engine code (ActorLogicRupeeCounter / ExecuteRupeeCounterControl) over the token placements its counter links.
The counter itself is the glass or gate the set removes.

remake_silver_rupee_items is true/false and only applies with shuffle_silver_rupees 'vanilla'. It's on by default
and off only when remake_avoid_vanilla_spots is set false explicitly (that setting's own default is off, this one's
stayed on). Every one of OoTR's 80 silver-rupee spots stays a silver rupee that counts for its own room exactly like
in vanilla (the room's puzzle, counter, doors and logic are untouched), and taking it ALSO gives a seed item held at
a new OoTR location "<puzzle> Silver Rupee Spot <n>" (80 new locations, one per spot). The item comes through a get
scene, like the drops plugin's heart spots:
  1. Each token placement gets a Name (RandoSilver<NN>). The two Gerudo Training Ground boulder-room tokens standing
     at one spot share it, so either set gives the spot's item, once (give_once). Without that, taking spot n's
     token on one side and then its twin on the other gave the item twice.
  2. The tokens' AI (AI/Obj_Rupee_Silver.root.ainb, in both packs that carry that path) gets a Sequential in its
     pickup step (node 11, the Simultaneous that hides the token and starts its flight to the counter). It copies
     the token's instance name into a scratch String64 (OneShotSetNonStructGameDataString64, copied from
     NpcCommon.event, and QueryGetActorInstanceName from the dog AI, like the heart spots use) and then requests one
     scene by name (OneShotEventMemberRequestEventByEventName, the way Obj_CheckActor's signboards do). That node is
     copied from SimpleRequestEvent.module, whose copy has no resident-init flag. The token is an AlwaysEventMember.
  3. That scene (a reused scene ID, data/rando/silver_rupees.json "scene_row", rewritten with the plain settings of
     BottomOfTheWell_SilverToken_Unlock) compares the scratch name with each spot's name. A match starts the
     player's event, clears the scratch and gives the item (Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc with the
     item's model, a dungeon item's credit entry, or the chests plugin's freeze for an ice trap). No match ends
     right away.
The token still dies and counts for its room like before, so the room opens exactly when OoTR's 'vanilla' logic
says. For logic, each new location needs every OoTR silver-rupee location of its puzzle reachable (one event per
OoTR location under its own rule, like generate.apply_group_logic does for chests paired by group), so which
physical token is which OoTR name never matters. Progressive items stay out (the give step has no tier scene), like
the hideout spots.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = json.load(open(os.path.join(HERE, "data", "rando", "silver_rupees.json"), encoding="utf-8"))
PUZZLES = DATA["puzzles"]
SETTING = "remake_silver_rupee_items"
# OoTR shuffle_silver_rupees values we build (dungeons.OWNS reads this). 'vanilla' is here, the others are in
# _dungeons_silver_shuffle.py.
SHUFFLE_MODES = ("vanilla", "remove", "dungeon", "regional", "overworld", "any_dungeon", "anywhere")
SPOT_NAME = "{puzzle} Silver Rupee Spot {n}"
TOKEN_NAME = "RandoSilver{:02d}"
SPOT_VANILLA = "Rupees (5)"  # the junk the pool gains per new location (the spot's own vanilla reward is the rupee)
GIVE_ROUTINE = "Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc"  # Link alone, no NPC turn (diving/frog games' give)
AI_GLOBAL = "Pack/AI.Global.Product.111.pack.zs"
NAME_SRC = {"pack": "Pack/Actor/Animal_Dog_Base.pack.zs", "file": "AI/Animal_Dog.event.root.ainb"}
SETSTR_SRC = {"pack": AI_GLOBAL, "file": "AI/NpcCommon.event.root.ainb"}
REQUEST_SRC = {"pack": AI_GLOBAL, "file": "AI/SimpleRequestEvent.module.ainb"}  # no resident-init flag
# The spot scene isn't a resident event, and a level only loads the scenes its own actors name. Its flowchart
# (BottomOfTheWell_Gimmick) was only loaded in the Bottom of the Well, so the token's request found it there and
# nowhere else. That's why the Ice Cavern scythe room played fully vanilla.
# So every token registers the scene for loading when it appears, the way a chest registers its get scene
# (Obj_TBox_A_01.root's OneShotBeforehandLoadEventRequestRegister, run once by its root's first Simultaneous). The
# token AI's enter step (its root SplitTiming's first child) gets that node, with EventName = the scene row.
PRELOAD_SRC = {"pack": AI_GLOBAL, "file": "AI/Obj_TBox_A_01.root.ainb"}
# Taken in the air
# Silver rupees taken while Link was falling or pulled by the Hookshot gave nothing, and the one taken standing gave
# its item. The token asks for the spot scene once, at the take. The scene's settings were copied from the room's
# unlock scene (BottomOfTheWell_SilverToken_Unlock, the plain FlowchartEvent list, AllPause and nothing more), and a
# plain flowchart event doesn't start while a member dissents. Link in the air or on the Hookshot can't join one, so
# the request got dropped.
# The game's own get scene, which a pickup taken in the air starts too, shows the way. Dm_SY_Get's list
# (FIGFlowchartWithIgnoreDissentPlay_...) and Dm_SY_Get_WithoutPlayer's carry IgnoreDissentPlayEvent
# (FlowchartWithIgnoreDissentPlay, its parent, 109 vanilla scenes). After starting the player's event Dm_SY_Get calls
# Common:AirStartUp, which settles Link by his state (EventQueryCheckPlayerState: stopped in the air, or waiting,
# before the hold-up). So the spot scene's row takes the list that also ignores the start interval, for a rupee taken
# right after another one's scene. That's HidingHole_Entry_01's and ShadowTemple_BossRoomIn_AfterBossWin's list,
# which start with Link possibly in the air, and the fairies' and drop gifts' scenes copy HidingHole_Entry_01's row.
# Each branch calls AIR_START after its player start, like Dm_SY_Get does.
SCENE_COMPONENTS = ("Work/Event/EventSetting/EventSettingComponentList/"
                    "FlowchartWithIgnoreDissentPlayAndStartInterval.engine__event__EventSettingComponentList.gyml")
AIR_START = "Common:AirStartUp"
YES, NO = 0, 1
# Gerudo Training Ground's boulder room has two token sets (one per side you enter the room from) at the same 5
# spots. Spot n's item is given once through a saved Int per spot, set after the give (give_once, which both this
# module and _dungeons_silver_shuffle.py use).
GTG = "Gerudo Training Ground Slopes"
GTG_TAKEN = "Rando_SilverGtg_{}"
BELOW, EQUAL, ABOVE = 0, 1, 2  # EventQueryIsGameDataInt answers


def _value(settings):
    """The setting as given. It's on by default (off when remake_avoid_vanilla_spots is set false explicitly)."""
    r = getattr(settings, "remake", None) or {}
    return r.get(SETTING, r.get("remake_avoid_vanilla_spots", True))


def enabled(settings):
    v = _value(settings)
    return (v is True or v == "on") and getattr(settings, "shuffle_silver_rupees", "vanilla") == "vanilla"


def check_settings(settings):
    v = _value(settings)
    if v not in (False, True, "off", "on"):
        return [f"{SETTING} = {v!r}: must be true or false"]
    explicit = SETTING in (getattr(settings, "remake", None) or {})
    if explicit and v in (True, "on") and settings.shuffle_silver_rupees != "vanilla":
        return [f"{SETTING} needs shuffle_silver_rupees 'vanilla' (each spot keeps its silver rupee for its room)"]
    return []


def untested(settings):
    if not enabled(settings):
        return []
    return [f"dungeons: {SETTING} - taking a silver rupee also gives its spot's item: the tokens' AI requests the "
            f"scene {DATA['scene_row']} (OneShotEventMemberRequestEventByEventName from a token, new); the room still "
            f"counts the token"]


def spots():
    """[(puzzle, n (1-based), spot location name, token name, [token hashes])] in a fixed order."""
    out, k = [], 0
    for puzzle in sorted(PUZZLES):
        for n, hashes in enumerate(PUZZLES[puzzle]["tokens"], 1):
            out.append((puzzle, n, SPOT_NAME.format(puzzle=puzzle, n=n), TOKEN_NAME.format(k), hashes))
            k += 1
    return out


def ootr_locations(puzzle):
    """OoTR's (non-MQ) silver-rupee locations of a puzzle, sorted by name."""
    import LocationList
    item = f"Silver Rupee ({puzzle})"
    return sorted(n for n, v in LocationList.location_table.items() if v[4] == item and " MQ " not in n)


# The new locations, in OoTR's own tables
_installed = {"on": False, "active": False}


def before_build(settings):
    """Register the spot locations and add each one to the region of its puzzle's n-th OoTR location, with rule True
    (before_fill sets the group rule). We do it by wrapping OoTR's logic reader once, and it only adds them while the
    seed being built has the setting on."""
    _installed["active"] = enabled(settings)
    if not enabled(settings) or _installed["on"]:
        return
    import LocationList
    import RuleParser
    import Utils
    import World
    where = {}
    for puzzle, n, name, _, _ in spots():
        locs = ootr_locations(puzzle)
        if len(locs) != len(PUZZLES[puzzle]["tokens"]):
            raise RuntimeError(f"data/rando/silver_rupees.json: {puzzle} has {len(PUZZLES[puzzle]['tokens'])} spots, "
                               f"OoTR {len(locs)} silver rupees")
        where[locs[n - 1]] = name
        tags = tuple(LocationList.location_table[locs[n - 1]][5] or ())
        LocationList.location_table[name] = ("Collectable", None, None, None, SPOT_VANILLA,
                                             tuple(t for t in tags if t != "Silver Rupees"))
    inner = Utils.read_logic_file

    def read(path):
        regions = inner(path)
        if not _installed["active"]:
            return regions
        for region in regions if isinstance(regions, list) else ():
            locs = region.get("locations") or {}
            add = {where[k]: "True" for k in locs if k in where}
            if add:
                region["locations"] = dict(locs, **add)
        return regions
    read.remake = True
    for module in (Utils, RuleParser, World):
        module.read_logic_file = read
    _installed["on"] = True


def keep_locations(world, settings):
    if not enabled(settings):
        return set()
    names = {loc.name for loc in world.get_locations()}
    out = {s[2] for s in spots() if s[2] in names}
    if len(out) != len(spots()):
        raise RuntimeError(f"{SETTING}: {len(spots()) - len(out)} silver-rupee spots missing from the world")
    return out


def givable(item):
    """True if the scene can give OoTR item `item` at a spot. OoTR's "Nothing" counts where the drops plugin makes it an
    Ice Trap or a junk item after the fill (remake_empty_object_contents "ice_trap" / "junk", drops._named_nothing),
    since my rule is that OoTR's Nothing goes anywhere. With "vanilla" or "nothing" it stays out, because the spot
    would play as a plain silver rupee or the scene would give config/item_map.json's junk_for green rupee."""
    if item == "Nothing":
        dr = sys.modules.get("parity.drops")
        return bool(dr is not None and hasattr(dr, "nothing_converted") and dr.nothing_converted())
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and dg.dungeon_item(item) is not None:
        return True
    if item == "Ice Trap":
        ch = sys.modules.get("parity.chests")
        return ch is not None and hasattr(ch, "scenes")
    import generate
    st = sys.modules.get("parity.songs_trade")  # the shared resolver: a hatched egg, a mask, the bean pack's or a
    if st is not None and hasattr(st, "plain_give"):  # soul's entry, and a progressive item's tier entry
        if item in generate.PROGRESSIVE:  # (the token's give step calls it, held up or in the
            return True                   # water next to the get window: songs_trade.plain_give)
        return st.plain_give(item) is not None
    if item in generate.PROGRESSIVE:
        return False
    try:
        generate.remake_item(item)
    except generate.SeedError:
        return False
    return True


def before_fill(world, settings):
    """Group rule (every OoTR silver rupee of the puzzle reachable) and the item rule on each spot."""
    if not enabled(settings):
        return
    from Location import Location
    from Item import make_event_item
    for puzzle in sorted(PUZZLES):
        events = []
        for i, name in enumerate(ootr_locations(puzzle), 1):
            loc = world.get_location(name)
            ev = f"Remake silver rupee {puzzle} {i}"
            ev_loc = Location(f"{ev} from {loc.parent_region.name}", location_type="Event", parent=loc.parent_region)
            ev_loc.rule_string = loc.rule_string
            ev_loc.access_rule = loc.access_rule
            ev_loc.world = world
            loc.parent_region.locations.append(ev_loc)
            make_event_item(ev, ev_loc)
            events.append(ev)
        rule = " and ".join(f"'{e}'" for e in events)
        for p, n, name, _, _ in spots():
            if p != puzzle:
                continue
            loc = world.get_location(name)
            loc.rule_string = rule
            world.parser.parse_spot_rule(loc)
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: givable(item.name) and prev(location, item))
    world._cached_locations = []


# Plan
def _sources():
    """Source node indices for the token AI edit, read from the vanilla files."""
    import ainb
    from romtools import Romfs, sarc_files
    import drops as drop_tools
    fs = Romfs(drop_tools.DEFAULT_ROMFS, os.path.join(HERE, "original"))

    def idx(spec, name):
        return ainb.Ainb(sarc_files(fs.read(spec["pack"]))[spec["file"]]).node(name)
    tok = ainb.Ainb(sarc_files(fs.read(DATA["token_pack"]))[DATA["token_ai"]])
    pick = DATA["token_pickup_node"]
    if ainb.NODE_TYPES.get(tok.nodes[pick]["type"]) != "Simultaneous" or not any(
            tok.nodes[pl["node"]]["name"] == "OneShotGameModelControllerSetVisible"
            for pl in tok.nodes[pick]["plugs"][ainb.PLUG_CHILD]):
        raise RuntimeError(f"{DATA['token_ai']}: node {pick} is no longer the token's pickup step")
    seq = next(i for i, n in enumerate(tok.nodes) if ainb.NODE_TYPES.get(n["type"]) == "Sequential")
    return {"name": idx(NAME_SRC, "QueryGetActorInstanceName"),
            "set": idx(SETSTR_SRC, "OneShotSetNonStructGameDataString64"),
            "req": idx(REQUEST_SRC, "OneShotEventMemberRequestEventByEventName"), "seq": seq, "pick": pick,
            "pre": idx(PRELOAD_SRC, "OneShotBeforehandLoadEventRequestRegister"), "enter": token_enter(tok)}


def token_enter(tok):
    """The token AI's enter step: its Root command's SplitTiming's first child, a Simultaneous run once."""
    import ainb
    c = next(c for c in tok.commands if c["name"] == "Root")
    kids = [pl["node"] for pl in tok.nodes[c["main"]]["plugs"][ainb.PLUG_CHILD]]
    if ainb.NODE_TYPES.get(tok.nodes[c["main"]]["type"]) != "SplitTiming" or not kids or ainb.NODE_TYPES.get(tok.nodes[kids[0]]["type"]) != "Simultaneous":
        raise RuntimeError(f"{DATA['token_ai']}: the Root command no longer starts at a SplitTiming whose enter step "
                           f"is a Simultaneous")
    return kids[0]


def ai_edits(src):
    """The token AI edit (identical for both packs carrying the file)."""
    own = {"pack": DATA["token_pack"], "file": DATA["token_ai"]}
    n, s, r, q = f"name:{src['name']}", f"set:{src['set']}", f"req:{src['req']}", f"seq:{src['seq']}"
    return [
        {"copy": {"from": NAME_SRC, "nodes": [src["name"]], "label": "name", "follow": False}},
        {"copy": {"from": SETSTR_SRC, "nodes": [src["set"]], "label": "set", "follow": False}},
        {"copy": {"from": REQUEST_SRC, "nodes": [src["req"]], "label": "req", "follow": False}},
        {"copy": {"from": own, "nodes": [src["seq"]], "label": "seq", "follow": False}},
        {"set_input": {"node": s, "name": "GameDataFullName", "value": DATA["scratch_string"]}},
        {"feed": {"from": n, "output": "InstanceName", "to": s, "input": "Value"}},
        {"set_input": {"node": r, "name": "EventName", "value": DATA["scene_row"]}},
        {"set_property": {"node": r, "name": "ExecuteEveryFrame", "value": False}},
        {"add_child": {"parent": q, "child": s}},
        {"add_child": {"parent": q, "child": r}},
        {"add_child": {"parent": src["pick"], "child": q}},
        {"copy": {"from": PRELOAD_SRC, "nodes": [src["pre"]], "label": "pre", "follow": False,
                  "values": {str(src["pre"]): {"EventName": DATA["scene_row"]}}}},
        {"add_child": {"parent": src["enter"], "child": f"pre:{src['pre']}"}},
    ]


WINDOW_ROUTINE = "GetPouchContent:GetPouchContentByActorName"  # the get window (Dm_SY_Get_WithoutPlayer's, in water)


def give_node(item, nxt=None, window=False):
    """The scene step that gives OoTR item `item`, the way dungeons.hideout_plan gives at the hideout spots. `window`
    uses the get window instead of the hold-up, for spots under water."""
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and dg.dungeon_item(item) is not None:
        return {"call": dg.call_target(item), "next": nxt}
    if item == "Ice Trap":
        return {"call": sys.modules["parity.chests"].scenes.CALL, "next": nxt}
    import generate
    import progressive
    st = sys.modules.get("parity.songs_trade")  # the shared resolver
    how = st.plain_give(item, window=window) if st is not None and hasattr(st, "plain_give") else None
    if how and how[0] == "call":
        return {"call": how[1], "next": nxt}
    actor = how[1] if how else generate.remake_item(item)
    held = None if window else progressive.hold_node(actor, nxt)  # an item Link can't hold up (config/hold_up.json)
    if held:
        return held
    return {"call": WINDOW_ROUTINE if window else GIVE_ROUTINE, "params": {"ActorName": actor}, "next": nxt}


def scene_graph(items):
    """(nodes, start) for the scene: items = [(token name, OoTR item, window give)]."""
    nodes, scratch = {}, DATA["scratch_string"]
    for k, (token, item, window) in enumerate(items):
        nodes[f"q{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                          "params": {"GameDataName": scratch, "Index": -1, "Value": token},
                          "cases": {YES: f"start{k}", NO: f"q{k + 1}" if k + 1 < len(items) else None}}
        nodes[f"start{k}"] = {"copy": DATA["scene_player_start"], "next": f"air{k}"}
        nodes[f"air{k}"] = {"call": AIR_START, "next": f"clear{k}"}  # see "Taken in the air" above
        nodes[f"clear{k}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                              "params": {"GameDataName": scratch, "Index": -1, "Value": ""}, "next": f"give{k}"}
        nodes[f"give{k}"] = give_node(item, window=window)
    return nodes, "q0"


def give_once(nodes, k, n):
    """Branch k of the scene (boulder-room spot n) gives its item once. It first asks GTG_TAKEN n == 0 and ends right
    away otherwise, then sets it to 1 after the give (a saved Int, gtg_ints)."""
    taken = GTG_TAKEN.format(n)
    nodes[f"q{k}"]["cases"][YES] = f"once{k}"
    nodes[f"once{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                         "params": {"Index": -1, "GameDataName": taken, "Value": 0},
                         "cases": {BELOW: None, EQUAL: f"start{k}", ABOVE: None}}
    nodes[f"give{k}"]["next"] = f"taken{k}"
    nodes[f"taken{k}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                          "params": {"Index": -1, "GameDataName": taken, "Value": 1}, "next": None}


def gtg_ints():
    """The gamedata op's add_ints for give_once (saved, new file 0)."""
    return {GTG_TAKEN.format(n): 0 for n in range(1, 6)}


_extras = {}  # id(world) -> save rows and read-back note, which aren't lists
# dungeons.world_plan only merges lists from here. _dungeons_silver_shuffle.world_plan passes these on.


def extras(world):
    return _extras.pop(id(world), {})


def world_plan(settings, world):
    if not enabled(settings):
        return {}
    placements, items, notes, spot_note = [], [], [], {}
    for puzzle, n, name, token, hashes in spots():
        item = world.get_location(name).item.name
        items.append((token, item, PUZZLES[puzzle].get("give") == "window"))
        for h in hashes:
            placements.append({"file": PUZZLES[puzzle]["file"], "hash": h, "set": {"Name": token}})
        notes.append(f"{name}: {item} (token{'s' if len(hashes) > 1 else ''} {', '.join(hashes)} named {token})")
        spot_note[token] = {"location": name, "item": item, "file": PUZZLES[puzzle]["file"], "tokens": list(hashes),
                            "gtg": n if puzzle == GTG else None}
    src = _sources()
    nodes, start = scene_graph(items)
    ch = sys.modules.get("parity.chests")  # an Ice Trap plays the trap kind its spot drew (remake_trap_weights)
    for k, (_puzzle, _n, name, _token, _hashes) in enumerate(spots()):
        if items[k][1] == "Ice Trap" and ch is not None:
            nodes[f"give{k}"]["call"] = ch.trap_call(world, name)
    for k, (token, _, _) in enumerate(items):
        g = nodes[f"give{k}"]
        spot_note[token]["give"] = {"call": g["call"], "actor": (g.get("params") or {}).get("ActorName")}
        if spot_note[token]["gtg"] is not None:
            give_once(nodes, k, spot_note[token]["gtg"])
    f = DATA["scene_file"]
    # The save rows give_once uses and the read-back (_dungeons_silver_shuffle.verify, mode 'vanilla').
    # _dungeons_silver_shuffle.world_plan hands them on, since dungeons.world_plan merges this module's sections as
    # lists.
    _extras[id(world)] = {
        "gamedata": {"add_ints": gtg_ints()},
        "_gaps": {"silver_rupees": {
            "mode": "vanilla", "credit": False, "spots": spot_note,
            "gtg": {str(n): {"taken": GTG_TAKEN.format(n), "chk": None} for n in range(1, 6)},
            "scene": {"file": f, "entry": DATA["scene_entry"], "row": DATA["scene_row"]},
            "token_ai": {"file": DATA["token_ai"], "packs": DATA["token_ai_packs"], "pickup": DATA["token_pickup_node"]},
            "counter_ai": None, "routes": {}}}}
    return {
        "placements": placements,
        "ainb": [{"pack": p, "file": DATA["token_ai"], "edits": ai_edits(src)} for p in DATA["token_ai_packs"]],
        "events": [{"file": f, "flowchart": f, "add_graph": DATA["scene_entry"], "nodes": nodes, "start": start}],
        "byml": [{"file": "RSDB/EventSetting.Product.111.rstbl.byml.zs", "replace_row": {
            "row": DATA["scene_row"], "copy_of": DATA["scene_row_settings_from"],
            "set": {"FlowchartFileName": f"Work/Event/EventFlow/{f}.evfc", "EntryPointName": DATA["scene_entry"],
                    "EventSettingComponentList": SCENE_COMPONENTS}}}],
        "_notes_dungeons_silver": notes,
    }
