"""Ice-trap chest scenes (helper of tools/rando/parity/chests.py).

usage: python tools/rando/parity/_chests_scenes.py [ROMFS]
       writes data/rando/chests_scenes.json (the scene graphs, so seed generation needs no game files)

What an ice trap does in the remake:
- The remake's own ice-trap chest (Obj_TBox_A_04) freezes Link through its AI. After the kick-open
  (Dm_SY_TreasureboxSmall:TrapOpen) it blows "TBox_FreezeBreath" and its attack sensor hits Link with an ice
  attack (AttackParam: BaseAttackPower 2 = half a heart, ice damage element), and Link's own frozen condition
  does the rest. No scene action can make that attack, so other chests get a scene that shows the same thing:
  1. the chest's own opening (small: front or kick as vanilla picks, big: the whole suspense cinematic, copied
     step for step like the progressive big-chest scene, with the item display replaced by step 2)
  2. Link flinches (ASCommand EvtFlinch, held) and Link's own frozen effect and sound play on him
     (Player ELink/SLink user "Player", keys Condition_Frozen / Condition_Frozen_End, the ones his frozen condition
     uses), with a rumble, held 65 frames (Player ConditionParam FrozenDurationFrame)
  3. the ice shatters (Condition_Frozen_End) and Link takes half a heart (Player_Event.EventTriggerHealLife with
     -2 quarter hearts), unless that would leave him with no life. At PlayerStatus.Life 1 or 2 there's no damage,
     so a chest scene can never kill him. The life game data is the one Link's life syncs with,
     LifeGameDataSyncParam hash = murmur3("PlayerStatus.Life").
  4. same as the chest's own ending: mark opened, release the pause, save
The chest's own contents (a stand-in) are never woken, so they never show.
Unverified in-game: the frozen effect keys called from a scene, a negative HealLife.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
OUT = os.path.join(HERE, "data", "rando", "chests_scenes.json")
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS

SMALL_FILE, BIG_FILE = "Dm_SY_TreasureboxSmall", "Dm_SY_Treasurebox"
FREEZE = "Rando_IceTrap_Freeze"
ENTRY = {"small": "Rando_IceTrap_small", "big": "Rando_IceTrap_big"}
STAND_IN = "TBox_Rupee_Blue"  # the hidden contents (config/item_map.json junk_for "Ice Trap")
DAMAGE = -2               # quarter hearts (the remake's ice-trap chest: BaseAttackPower 2)
FROZEN_FRAMES = 65        # Player ConditionParam FrozenDurationFrame
YES, NO = 0, 1            # query answers (README: case 0 = yes)
# makes the ice-trap attacker from drops.ice_sensor_ops, which hits Link with the game's own chest attack after
# the scene ends
CREATE_SENSOR = {"actor": "GameSystemActor", "action": "EventTriggerRequestCreateConditionSensor",
                 "params": {"ActorName": "ConditionSensorActor"}}
# OoTR's ice-trap message (message 0x9002, "You are a FOOL!" with FOOL in red), using the remake's key-word
# highlight ({tag:0,3,0000}). Which colour each index shows is unverified (data/rando/hints_targets.json).
FOOL_FILE, FOOL_ENTRY = "GetPouchContent", "Rando_IceTrapFool"
FOOL_MSBT, FOOL_LABEL = "EventFlowMsg/Dm_SY_Get.msbt", "Rando_IceTrapFool"
FOOL_MESSAGE = "EventFlowMsg/Dm_SY_Get:Rando_IceTrapFool"
FOOL_MARKUP = "You are a {tag:0,3,0000}FOOL{tag:0,3,ffff}!"
# GetPouchContent's get messages' own talk settings (Event23)
TALK_PARAMS = {"IsWaitEnd": True, "IsCloseDialog": True, "EndDialogOption": 0, "ASName": "", "IsAnimeDriven": False,
               "IsPlayASAllSlot": False, "ChoiceNumber": 0, "ChoiceLabel1": 0, "ChoiceLabel2": 0, "ChoiceLabel3": 0,
               "ChoiceLabel4": 0, "ChoiceDefaultNo": 0, "ChoiceCancelNo": 0, "IsNotBecomeSpeaker": False,
               "ChangeMstxtForActor": False, "IsAnonymous": False, "NotPlayLipSyncAnim": False,
               "IsNotOpenIfSkipedMostRecent": False, "IsOverrideStyle": True, "OverrideStyle": 4,
               "MaintainPerformanceState": 0}


def _pose(command, keep=False, wait=False):
    return {"actor": "Player_Event", "action": "EventPlayerPlayASForFlowchart",
            "params": {"UseAnmDriven": False, "IsAllSlot": False, "KeepOneTimeAnm": keep, "ForceFadeFrame": -1.0,
                       "ASCommand": command, "IsWaitEnd": wait, "ClothWarpMode": 0}}


def _wait(frames, nxt):
    return {"actor": "GameSystemActor", "action": "EventWait", "params": {"Frames": frames, "IsWaitEnd": True},
            "next": nxt}


def freeze_graph():
    """(entry, nodes, start) for the ice trap, added to each scene file that uses it.
    It makes the ice-trap attacker (tools/rando/drops.py ice_sensor_ops, the remake's ice-trap chest's own attack once
    the scene is over), then shows OoTR's ice-trap message, "You are a FOOL!" (FOOL_ENTRY, a system text box).
    I used to also play a stand-in freeze here (Link's flinch pose and frozen effect, a shatter, a negative heal that
    did nothing), but with the real freeze after it it looked off, so it's gone."""
    n = {
        "sensor": dict(CREATE_SENSOR, next="fool"),
        "fool": {"call": f"{FOOL_FILE}:{FOOL_ENTRY}", "next": None},
    }
    return FREEZE, n, "sensor"


def fool_ops():
    """Plan ops for the ice-trap message: its text (a new label beside the get messages, every language) and the
    GetPouchContent entry that shows it (SystemTextNPC, like that file's own get messages). Every file holding the
    freeze already calls GetPouchContent."""
    talk = {"actor": "SystemTextNPC", "action": "EventTalk", "params": dict(TALK_PARAMS, MessageId=FOOL_MESSAGE),
            "next": None}
    return {"events": [{"file": FOOL_FILE, "flowchart": FOOL_FILE, "add_graph": FOOL_ENTRY, "nodes": {"talk": talk},
                        "start": "talk"}],
            "text": [{"lang": "*", "file": FOOL_MSBT, "label": FOOL_LABEL, "markup": FOOL_MARKUP, "add": True,
                      "note": "OoTR's ice-trap message (its message 0x9002)"}]}


def _ending(n, first):
    """As the chest scenes' own endings: mark opened, release the pause, save."""
    n[first] = _wait(1, "markopened")
    n["markopened"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTreasureBoxOpened",
                       "next": "unpause"}
    n["unpause"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTBoxErasePauseMask", "next": "save"}
    n["save"] = {"actor": "GameSystemActor", "action": "EventTriggerRequestAutoSave", "next": None}


def small_graph():
    """(entry, nodes, start): the small-chest ice trap (opening as tools/progressive.py chest_scene)."""
    n = {"face": {"actor": "TreasureBox_EventStarter", "query": "EventQueryIsFaceToFace",
                  "params": {"ActorName": "Player_Event"}, "cases": {YES: "front", NO: "kick"}}}
    for side, pose, rumble in (("front", "DemoOpenTreasureBoxFront", ":FrontVibration"),
                               ("kick", "DemoOpenTreasureBoxWithKick", ":KickVibration")):
        n[side] = {"fork": [f"pose_{side}", f"lid_{side}", f"rumble_{side}"], "join": f"opened_{side}"}
        n[f"pose_{side}"] = dict(_pose(pose, wait=True), next=None)
        n[f"pose_{side}"]["params"].update(UseAnmDriven=True, IsAllSlot=True)
        n[f"lid_{side}"] = {"call": ":TresureboxSmall_Animation", "next": None}
        n[f"rumble_{side}"] = {"call": rumble, "next": None}
        n[f"opened_{side}"] = {"join": True, "next": "freeze"}
    n["freeze"] = {"call": f":{FREEZE}", "next": "wait1"}
    _ending(n, "wait1")
    return ENTRY["small"], n, "face"


def big_graphs(model):
    """[(entry, nodes, start)] for the big chest's whole opening cinematic, copied the way the progressive big-chest
    scene does it (tools/progressive.py big_chest_graphs), with the item display (call :Item_Rotation) replaced by
    the freeze and then the chest's ending."""
    import progressive
    graphs = progressive.big_chest_graphs(ENTRY["big"], [STAND_IN], model)
    (perform, pnodes, pstart), (entry, n, _) = graphs
    # the freeze replaces the display, so Link never holds up or gets the stand-in
    for label in ("showlod", "showfire", "showglow"):
        pnodes.pop(label, None)
    pnodes["show"] = {"call": f":{FREEZE}", "next": None}
    n.pop("has0", None)
    n.pop("add0", None)
    n.pop("hide", None)
    n["wait90_0"]["next"] = "wait1"
    n["fanfare0"]["params"]["ActorName"] = STAND_IN  # the suspense intro, as for any big chest
    return [(perform, pnodes, pstart), (entry, n, "fanfare0")]


# Ice traps outside chests
# One shared freeze entry for every scene that hands over an item (NPCs, songs, cutscenes, boss rewards, Great
# Fairies, cows, frogs...). tools/make_patch.py replaces the give step with a call to it ("call" reward spec).
HOST_FILE = "Dm_SY_GetInEvent"           # has Player_Event, GameSystemActor, GameDataActor, PouchSystemActor
HOST_ENTRY = "Rando_IceTrap"
CALL = f"{HOST_FILE}:{HOST_ENTRY}"
PAY_ENTRY = "Rando_IceTrap_Pay"          # a sale: take SimpleShop_Price rupees, then freeze
SCRUB_FILE, SCRUB_ENTRY = "Enemy_Scrub_Business_Common", "Rando_IceTrap_ScrubSale"
SHOP_FILE, SHOP_ROOT, SHOP_BUY = "SimpleShop", "Rando_IceTrap_SimpleShopRoot", "Rando_IceTrap_SimpleShop_Buy"


def host_graphs():
    """[(entry, nodes, start)] for Dm_SY_GetInEvent: the freeze, and the freeze after paying a sale."""
    _, n, start = freeze_graph()
    pay = {"pay": {"actor": "PouchSystemActor", "action": "EventTriggerAddGameDataIntToRupee",
                   "params": {"IsSignInverse": True, "GameDataName": "SimpleShop_Price"}, "next": "stable"},
           "stable": {"actor": "UISystemActor", "action": "EventWaitStableNumDisplay", "params": {"IsWaitEnd": True},
                      "next": "freeze"},
           "freeze": {"call": f":{HOST_ENTRY}", "next": None}}
    return [(HOST_ENTRY, n, start), (PAY_ENTRY, pay, "pay")]


def _clone_around(fc, start, prefix, stop_event, node):
    """Copies the steps reachable from `start`, with step `stop_event` replaced by `node`. Its "next" names the
    vanilla step it continues with, and that's copied too."""
    import progressive
    events = fc["events"]
    by_name = {e["name"]: e for e in events}
    stop = by_name[stop_event]
    after = events[stop["next"]]["name"] if stop.get("next", 0xFFFF) < len(events) else None
    nodes, first = progressive.clone(fc, start, prefix, {stop_event: "rando_replaced"})
    node = dict(node)
    if after:
        more, label = progressive.clone(fc, after, prefix, {stop_event: "rando_replaced"})
        nodes.update(more)
        node["next"] = label
    else:
        node["next"] = None
    nodes["rando_replaced"] = node
    return nodes, first


def scrub_graphs(model):
    """The Business Scrub one-time sale (Enemy_Scrub_Business_Common:SimpleShopSub_Scrub_Business_OneTime), copied
    with its hand-over (call Dm_SY_GetInEvent:GetInEvent_NotTurn_2DShop, pay then give) replaced by pay + freeze.
    Everything else stays vanilla (prices, lines, cancel, not enough rupees, the scrub fleeing)."""
    fc = model.flowcharts[0]
    ep = fc["entry_points"]["SimpleShopSub_Scrub_Business_OneTime"]["main"]
    nodes, first = _clone_around(fc, fc["events"][ep]["name"], "s_", "Event4", {"call": f"{HOST_FILE}:{PAY_ENTRY}"})
    return [(SCRUB_ENTRY, nodes, first)]


def simpleshop_graphs(model):
    """SimpleShop, the Wasteland carpet salesman's sale. SimpleShopRoot gets copied without the "room in the pouch?"
    check (an ice trap always fits) and calls a copy of Sub_SimpleShop_Buy where the freeze replaces the hand-over
    (the NpcCommon hand-over call). The price is taken as vanilla, its AddGameDataIntToRupee step stays."""
    fc = model.flowcharts[0]
    eps = fc["entry_points"]
    root = fc["events"][eps["SimpleShopRoot"]["main"]]["name"]
    buy = fc["events"][eps["Sub_SimpleShop_Buy"]["main"]]["name"]
    hand = next(e["name"] for e in fc["events"] if e["type"] == "subflow" and e.get("flowchart") == "NpcCommon"
                and _reachable_from(fc, eps["Sub_SimpleShop_Buy"]["main"], e["idx"]))
    can_add = next(e["name"] for e in fc["events"] if e["type"] == "switch"
                   and fc["actors"][e["actor"]]["queries"][e["query"]] == "EventQueryCanAddToPorch")
    buy_call = next(e["name"] for e in fc["events"] if e["type"] == "subflow"
                    and e.get("entry_point") == "Sub_SimpleShop_Buy" and not e.get("flowchart")
                    and _reachable_from(fc, eps["SimpleShopRoot"]["main"], e["idx"]))
    rn, rfirst = _clone_around(fc, root, "r_", can_add, {"copy": buy_call, "call": f":{SHOP_BUY}"})
    rn["rando_replaced"]["next"] = None
    bn, bfirst = _clone_around(fc, buy, "b_", hand, {"call": CALL})
    return [(SHOP_BUY, bn, bfirst), (SHOP_ROOT, rn, rfirst)]


def _reachable_from(fc, start, goal):
    import progressive
    return start == goal or progressive.reachable(fc, start, goal)


def build(romfs=DEFAULT_ROMFS, write=True):
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    big = Evfl(fs.read(f"Event/EventFlow/{BIG_FILE}.bfevfl.zs"))
    scrub = Evfl(fs.read(f"Event/EventFlow/{SCRUB_FILE}.bfevfl.zs"))
    shop = Evfl(fs.read(f"Event/EventFlow/{SHOP_FILE}.bfevfl.zs"))
    out = {"_about": __doc__.strip().splitlines()[0] + " (made by tools/rando/parity/_chests_scenes.py)",
           "stand_in": STAND_IN,
           "files": {"small": SMALL_FILE, "big": BIG_FILE, "host": HOST_FILE, "scrub": SCRUB_FILE, "shop": SHOP_FILE},
           "entry": ENTRY,
           "graphs": {"small": [list(freeze_graph()), list(small_graph())],
                      "big": [list(freeze_graph())] + [list(g) for g in big_graphs(big)],
                      "host": [list(g) for g in host_graphs()],
                      "scrub": [list(g) for g in scrub_graphs(scrub)],
                      "shop": [list(g) for g in simpleshop_graphs(shop)]}}
    if write:
        json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out


def load():
    return json.load(open(OUT, encoding="utf-8"))


def event_ops(size):
    """Plan "events" ops adding the ice-trap scene for a chest size ("small" or "big")."""
    d = load()
    f = d["files"][size]
    return [{"file": f, "flowchart": f, "add_graph": e, "nodes": nodes, "start": start}
            for e, nodes, start in d["graphs"][size]]


# Other trap kinds (remake_trap_weights)
# OoT3DR's trap types, as far as the remake's own steps can make them.
# Each kind is one effect graph, added next to the ice trap's in the file that uses it (the small or big chest scene
# file, Dm_SY_GetInEvent for every other location, a local copy in the resident get scene Dm_SY_Get), and called
# where the freeze would be.
#  - shock, fire: the ice trap's own freeze_graph with an attacker of the kind's element. A scene can't hurt Link (a
#    negative EventTriggerHealLife does nothing), so a scene-only effect (Link's Condition_ElectricShock /
#    Condition_Lava effect and a negative heal) shows the effect and takes no life. Instead the scene creates the
#    kind's attacker (SENSORS, a copy of the ice-trap attacker made by kind_sensor_ops, whose AttackParam is the trap
#    chest's with the element ElectricShock or Fire, the way Enemy_Biri's and the fire Keese's attacks name them),
#    then "You are a FOOL!". Once no main event plays it hits Link with his own electric-shock or burning condition
#    (Player ConditionParam IsEnableElectricShock / IsEnableBurn, child Link too), half a heart.
#  - rupee: Link flinches, the rupee counter opens and he loses 10 rupees (PouchSystemActor.EventTriggerIncreaseRupee
#    -10, the minigames' own fee step), or all he has if fewer (EventQueryHasRuppe, then the fishing pond's own "lose
#    all rupees" step, AddGameDataIntToRupee of PlayerStatus.CurrentRupee, inverted).
TRAP_KINDS = ("shock", "fire", "rupee")
SENSORS = {"shock": "RandoShockTrapSensor", "fire": "RandoFireTrapSensor"}  # the kinds' attackers (new actor types)
ELEMENTS = {"shock": 702910523, "fire": 1305706849}  # murmur3 "ElectricShock", "Fire" (Enemy_Biri, Enemy_Keese_Fire)
RUPEE_LOSS = 10


def trap_effect_entry(kind):
    return "Rando_Trap_" + kind.title()


def trap_chest_entry(kind, size):
    return f"{trap_effect_entry(kind)}_{size}"


def trap_call(kind):
    """The scene entry a non-chest location calls for this kind (CALL, the ice trap's freeze, for "ice")."""
    return CALL if kind == "ice" else f"{HOST_FILE}:{trap_effect_entry(kind)}"


def trap_graph(kind):
    """(entry, nodes, start) for the effect of trap kind `kind` (not "ice"), for any of the host files. Shock and fire
    are the freeze_graph with the kind's attacker (SENSORS), rupee is the rupee loss."""
    n = {}
    if kind in SENSORS:
        _, n, start = freeze_graph()
        n = dict(n, sensor=dict(n["sensor"], params={"ActorName": SENSORS[kind]}))
        return trap_effect_entry(kind), n, start
    if kind == "rupee":
        n["fx"] = {"fork": ["pose", "show", "rumble"], "join": "shown"}
        n["show"] = {"actor": "UISystemActor", "action": "EventTriggerOpenRupeeDisplay",
                     "params": {"IsNeedMaxNum": False, "IsWaitChoiceBtnIn": False}, "next": None}
        n["shown"] = {"join": True, "next": "has"}
        n["has"] = {"actor": "PouchSystemActor", "query": "EventQueryHasRuppe", "params": {"Value": RUPEE_LOSS},
                    "cases": {YES: "lose", NO: "loseall"}}
        n["lose"] = {"actor": "PouchSystemActor", "action": "EventTriggerIncreaseRupee",
                     "params": {"Value": -RUPEE_LOSS}, "next": "stable"}
        n["loseall"] = {"actor": "PouchSystemActor", "action": "EventTriggerAddGameDataIntToRupee",
                        "params": {"IsSignInverse": True, "GameDataName": "PlayerStatus.CurrentRupee"},
                        "next": "stable"}
        n["stable"] = {"actor": "UISystemActor", "action": "EventWaitStableNumDisplay", "params": {"IsWaitEnd": True},
                       "next": "close"}
        n["close"] = {"actor": "UISystemActor", "action": "EventTriggerCloseRupeeDisplay", "next": "recover"}
    else:
        raise ValueError(f"no trap kind {kind!r}")
    n["pose"] = dict(_pose("EvtFlinch", keep=True), next=None)
    n["rumble"] = {"actor": "GameSystemActor", "action": "EventTriggerControllerRumble",
                   "params": {"RumbleCall": "Demo_Middle_Don", "Length": 0.0}, "next": None}
    n["recover"] = dict(_pose("EvtWait"), next="settle")
    n["settle"] = _wait(20, None)
    return trap_effect_entry(kind), n, "fx"


def _rename_calls(nodes, old, new):
    return {k: (dict(v, call=new) if v.get("call") == old else dict(v)) for k, v in nodes.items()}


def trap_chest_graphs(kind, size):
    """[(entry, nodes, start)] for a chest scene file: the effect and the chest's own opening calling it (the ice
    trap's chest scenes with the freeze call and entry names changed)."""
    d = load()
    out = [trap_graph(kind)]
    effect, entry = f":{trap_effect_entry(kind)}", trap_chest_entry(kind, size)
    if size == "small":
        _, n, start = d["graphs"]["small"][1]
        out.append((entry, _rename_calls(n, f":{FREEZE}", effect), start))
    else:
        (_, pn, pstart), (_, n, start) = d["graphs"]["big"][1], d["graphs"]["big"][2]
        perform = f"{entry}_perform0"
        out.append((perform, _rename_calls(pn, f":{FREEZE}", effect), pstart))
        out.append((entry, _rename_calls(n, f":{ENTRY['big']}_perform0", f":{perform}"), start))
    return out


def trap_event_ops(kind, where):
    """Plan "events" ops adding trap kind `kind`: where = "small" / "big" (that chest scene file) or "host"."""
    f = HOST_FILE if where == "host" else load()["files"][where]
    graphs = [trap_graph(kind)] if where == "host" else trap_chest_graphs(kind, where)
    return [{"file": f, "flowchart": f, "add_graph": e, "nodes": nodes, "start": start} for e, nodes, start in graphs]


# Every chest type runs its trap
# A chest tells its trap by what it holds. The ice trap in a chest that runs a reused scene ID of its own keeps
# STAND_IN, since the scene ID says it all. Everywhere else the chest holds a stand-in of the trap's own, a type of
# ours that no item ever is (TRAP_STAND_INS, copies of STAND_IN's pack and rows under a new name made by
# stand_in_ops, so they behave in a chest exactly like STAND_IN does: never woken, never shown). The scene that runs
# compares the chest's ContentName with them, using the dungeons plugin's carrier compare (the name copied into the
# scrub flows' scratch string, read two frames later, GameDataActor.EventQueryIsGameDataString64):
#  - the other kinds share the ice trap's two scene IDs (the rows can't grow), so the ice entry first sends a kind's
#    stand-in to that kind's chest entry (with_kinds)
#  - for chests whose own story or minigame scene stays (Mido's house, the Treasure Chest Game), that scene's entry
#    point first sends a trap's stand-in to its trap entry (story_dispatch). The game's own steps before the chest's
#    opening (Navi's chat flag) get copied in front of it. The Treasure Chest Game opens with the minigame poses
#    (Dm_SY_TreasureboxSmall Open, IsMiniGame: DemoOpenBoxFront_Mini / DemoOpenBoxWithKick_Mini), so its trap
#    entries are copies with those poses (mini).
TRAP_STAND_INS = {k: f"TBox_RandoTrap_{k.title()}" for k in ("ice",) + TRAP_KINDS}
SCRATCH = "Scrub_Business_TempItemName_03"  # (progressive.SCRUB_SCRATCH, the dungeons plugin's scratch_string)
MINI_POSES = {"DemoOpenTreasureBoxFront": "DemoOpenBoxFront_Mini",
              "DemoOpenTreasureBoxWithKick": "DemoOpenBoxWithKick_Mini"}
MINI = "_mini"
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
GAME_ACTOR_INFO = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"


def chest_entry(kind, size):
    """The chest scene entry of trap kind `kind` for a chest of `size` (the ice trap's ENTRY for "ice")."""
    return ENTRY[size] if kind == "ice" else trap_chest_entry(kind, size)


def content_dispatch(n, prefix, cases, nomatch):
    """Nodes in `n` comparing the chest's ContentName with each stand-in of `cases` [(stand-in, label)] in order. A
    match goes to its label and no match to `nomatch`. Returns the first node's label."""
    from write_read_check import settle
    n[f"{prefix}set"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                         "params": {"GameDataName": SCRATCH, "Index": -1, "Value": {"arg": "ContentName"}},
                         "next": f"{prefix}settle"}
    n[f"{prefix}settle"] = settle(f"{prefix}is0")
    for i, (stand_in, go) in enumerate(cases):
        n[f"{prefix}is{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                               "params": {"GameDataName": SCRATCH, "Index": -1, "Value": stand_in},
                               "cases": {YES: go, NO: f"{prefix}is{i + 1}" if i + 1 < len(cases) else nomatch}}
    return f"{prefix}set"


def with_kinds(size, kinds):
    """The ice trap's chest entry for `size` (its graphs as event_ops gives them), with the entry first sending each
    kind of `kinds` (not "ice") to that kind's chest entry by its stand-in. -> [(entry, nodes, start)]."""
    graphs = [tuple(g) for g in load()["graphs"][size]]
    out = []
    for entry, nodes, start in graphs:
        if entry == ENTRY[size] and kinds:
            nodes = dict(nodes)
            cases = []
            for k in kinds:
                nodes[f"kind_go_{k}"] = {"call": f":{trap_chest_entry(k, size)}", "next": None}
                cases.append((TRAP_STAND_INS[k], f"kind_go_{k}"))
            start = content_dispatch(nodes, "kind_", cases, start)
        out.append((entry, nodes, start))
    return out


def mini(entry, nodes, start):
    """A small chest trap entry with the Treasure Chest Game's opening poses (MINI_POSES), as entry + MINI."""
    out = {}
    for lab, v in nodes.items():
        cmd = (v.get("params") or {}).get("ASCommand")
        out[lab] = dict(v, params=dict(v["params"], ASCommand=MINI_POSES[cmd])) if cmd in MINI_POSES else dict(v)
    return entry + MINI, out, start


def small_entry_graph(kind):
    """(entry, nodes, start) of the small chest trap entry of `kind` (its effect graph is added separately)."""
    if kind == "ice":
        return tuple(load()["graphs"]["small"][1])
    return trap_chest_graphs(kind, "small")[1]


def story_dispatch(file, graph, kinds, size, before, nomatch, minigame=False):
    """Plan event op for entry `graph` in chest scene file `file`, which compares ContentName with the stand-ins of
    `kinds`. A match runs a copy of step `before` (or nothing) and then the kind's chest entry (its minigame copy),
    and no match goes on with vanilla step `nomatch`."""
    n, cases = {}, []
    for k in kinds:
        go = f"go_{k}"
        n[go] = {"call": ":" + chest_entry(k, size) + (MINI if minigame else ""), "next": None}
        if before:
            n[f"pre_{k}"] = {"copy": before, "next": go}
            go = f"pre_{k}"
        cases.append((TRAP_STAND_INS[k], go))
    start = content_dispatch(n, "", cases, "@" + nomatch)
    return {"file": file, "flowchart": file, "add_graph": graph, "nodes": n, "start": start}


def shop_kind_graphs(kind):
    """The carpet salesman's ice-trap sale (simpleshop_graphs) for trap kind `kind`: entries SHOP_ROOT_<Kind> and
    SHOP_BUY_<Kind>, the hand-over calling the kind's effect. -> [(entry, nodes, start)]."""
    (buy, bn, bfirst), (root, rn, rfirst) = load()["graphs"]["shop"]
    sfx = "_" + kind.title()
    bn = {k: (dict(v, call=trap_call(kind)) if v.get("call") == CALL else dict(v)) for k, v in bn.items()}
    rn = {k: (dict(v, call=f":{SHOP_BUY}{sfx}") if v.get("call") == f":{SHOP_BUY}" else dict(v))
          for k, v in rn.items()}
    return [(buy + sfx, bn, bfirst), (root + sfx, rn, rfirst)]


def stand_in_ops(names):
    """{"new_files", "packs", "byml"} for the trap stand-in types `names` (TRAP_STAND_INS values). Each is a copy of
    STAND_IN's pack and of its ActorInfo and GameActorInfo rows under its own name."""
    out = {"new_files": [], "packs": [], "byml": []}
    for name in sorted(names):
        rel = f"Pack/Actor/{name}.pack.zs"
        out["new_files"].append({"to": rel, "from": f"Pack/Actor/{STAND_IN}.pack.zs",
                                 "note": f"{name}: a trap's chest stand-in (a copy of {STAND_IN})"})
        out["packs"].append({"pack": rel, "file": f"Actor/{name}.engine__actor__ActorParam.bgyml",
                             "new_from": f"Actor/{STAND_IN}.engine__actor__ActorParam.bgyml"})
        out["byml"].append({"file": ACTOR_INFO, "add_row": {"copy_of": STAND_IN, "set": {"__RowId": name}},
                            "note": f"{name}: a trap's chest stand-in"})
        out["byml"].append({"file": GAME_ACTOR_INFO, "add_row": {"copy_of": STAND_IN, "set": {"__RowId": name}}})
    return out


BREATH_LABELS = ("x1", "x2")  # drops.ice_sensor_ops: the trap chest's freeze breath, the ice kind's own look


def kind_sensor_ops(kind):
    """{"new_files", "packs", "ainb", "byml"} for SENSORS[kind], the attacker of trap kind `kind` (shock, fire).
    It's a new actor type, a copy of the ice-trap attacker (drops.ice_sensor_ops, ConditionSensorActor's pack with
    the trap chest's sensor, SensorHit and attack) under its own name and rows. Its AttackParam is the trap chest's
    with the kind's element (ELEMENTS), and its AI is the ice attacker's without the chest's freeze breath. Its own
    pack holds every file it names. It's a new pack so no "*" op reaches it, and its copy of ConditionSensorActor's
    ActorParam gets the same edit explicitly and ends like every other copy."""
    import drops as drop_tools  # tools/rando/drops.py
    d = drop_tools
    ice = d.ice_sensor_ops()
    name = SENSORS[kind]
    pack = f"Pack/Actor/{name}.pack.zs"
    parent_ap = f"Actor/{d.SENSOR_ACTOR}.engine__actor__ActorParam.bgyml"
    out = {"new_files": [{"to": pack, "from": d.SENSOR_PACK,
                          "note": f"{name}: the {kind} trap's attacker (a copy of the ice-trap attacker)"}],
           "packs": [], "ainb": [], "byml": []}
    for op in ice["packs"]:
        if op["pack"] == d.SENSOR_PACK:
            out["packs"].append(dict(op, pack=pack))
        elif op["pack"] == "*" and op["file"] == parent_ap:
            out["packs"].append(dict(op, pack=pack))
    src = [op for op in ice["ainb"] if op["pack"] == d.SENSOR_PACK]
    if len(src) != 1:
        raise ValueError("drops.ice_sensor_ops: not one AI edit of the attacker")
    out["ainb"].append(dict(src[0], pack=pack))  # (its copy of the ice AI ends like the ice pack's)
    edits = [e for e in src[0]["edits"]
             if not ("copy" in e and e["copy"].get("label") in BREATH_LABELS)
             and not ("add_child" in e and str(e["add_child"].get("child")).split(":")[0] in BREATH_LABELS)]
    if len(src[0]["edits"]) - len(edits) != 2 * len(BREATH_LABELS):
        raise ValueError("drops.ice_sensor_ops: the freeze breath is no longer two copied nodes")
    atk = f"GameBalance/AttackParam/{name}.game__gamebalance__AttackParam.bgyml"
    gpt = f"GameParameter/GameParameterTable/{name}.engine__actor__GameParameterTable.bgyml"
    info = f"AI/AIInfo/{name}.engine__actor__AIInfo.bgyml"
    ai = f"AI/{name}.root.ainb"
    sun_gpt = f"GameParameter/GameParameterTable/{d.SUN}.engine__actor__GameParameterTable.bgyml"  # vanilla parameter-table donor
    own_info = f"AI/AIInfo/{d.SENSOR_ACTOR}.engine__actor__AIInfo.bgyml"  # vanilla AIInfo donor
    own_ai = f"AI/{d.SENSOR_ACTOR}.root.ainb"
    out["packs"] += [
        {"pack": pack, "file": atk, "from_pack": d.TRAP_SRC["pack"], "new_from": d.TRAP_FILES[5],
         "set": {"AttackParams.0.DamageElements.0": ELEMENTS[kind]}},
        {"pack": pack, "file": gpt, "from_pack": f"Pack/Actor/{d.SUN}.pack.zs", "new_from": sun_gpt,
         "set": {"Components.gamebalance_AttackParam": "?" + atk}},
        {"pack": pack, "file": info, "new_from": own_info, "set": {"RootAIRef": f"Work/AI/Root/{name}.root.ain"}},
        {"pack": pack, "file": ai, "from_pack": d.SENSOR_PACK, "new_from": own_ai},
        {"pack": pack, "file": f"Actor/{name}.engine__actor__ActorParam.bgyml", "new_from": parent_ap,
         "set": {"Components.AIInfoRef": "?" + info, "Components.GameParameterTableRef": "?" + gpt}}]
    out["ainb"].append({"pack": pack, "file": ai, "edits": edits})
    row = next(op for op in ice["byml"] if op["file"] == d.ACTOR_INFO)["set"]
    heap = {k.split(".", 1)[1]: v for k, v in row.items()}
    out["byml"] += [{"file": d.ACTOR_INFO, "add_row": {"copy_of": d.SENSOR_ACTOR, "set": dict(heap, __RowId=name)},
                     "note": f"{name}: the {kind} trap's attacker"},
                    {"file": GAME_ACTOR_INFO, "add_row": {"copy_of": d.SENSOR_ACTOR, "set": {"__RowId": name}}}]
    return out


if __name__ == "__main__":
    o = build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROMFS)
    print(f"wrote {OUT}: " + ", ".join(f"{k}: {len(v)} graphs" for k, v in o["graphs"].items()))
