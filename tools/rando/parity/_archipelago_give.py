"""Archipelago mailbox: the steps that give each received item. It's a helper of tools/rando/parity/archipelago.py
(data/archipelago/MAILBOX.md section 2, "reads Code and hands the item over exactly as a single-player NPC gift
would").

leaf(item, world, settings, mods) -> {"nodes", "start", "plan", "kind"}, tools/evfl_build.py add_graph nodes for
the mailbox's own scene file RandoAP_Mailbox. That's archipelago.EVENT_FILE, a renamed copy of DmF_SY_FallDown, so
the mailbox doesn't load with every NPC gift. Because of that:
  - every routine is called across files ("Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc", the way NPC scenes call it)
  - no step names an existing step ("@Event...")
  - the only actors used directly are ones that file declares (HOST_ACTORS). evfl_build adds an action or query to
    a declared actor and refuses an undeclared one.
leaf() checks all three. Every path that ends the give ends with "next": "@@DONE", which the caller replaces with
its counting step. It's only ever a "next" value, never a case target, so a branch that gives nothing goes through
a one-frame wait. Labels are plain identifiers, unique within the leaf.
leaves(world, settings, mods, codes) -> {code: leaf} for every code, or ValueError naming each item it can't give.

How single player gives an OoTR item at a core scene location (an NPC gift): generate.plugin_item(mods, item,
location, world) gives one of
  - an actor (make_patch rewrites the give step's ActorName)
  - a progressive name (make_patch scene_progressive_ops does tier checks, then the give routine with the tier,
    tools/progressive.py host_graph)
  - {"call": "File:Entry"} (make_patch scene_call_ops, the give step becomes a call)
The leaves reproduce those with the same entries and plugin registrations:

- "get": the actor plugin_item gives at REF_LOCATION (a core scene location whose give steps are GET_ROUTINE),
  handed over by GET_ROUTINE, Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc {ActorName, IsNpcEventStarter: False}.
  That's the vanilla give for Link alone with no NPC to turn to. MiniGame_FrogTenors Event384 and
  Npc_SkullKid_Child Event71 call it with exactly these two parameters, the dungeons plugin's hideout gives use it,
  and it's OotrR's mailbox give (seen in game). It holds the item up, shows the get window and adds it through
  GetPouchContent:GetPouchContent Event0, then Dm_SY_Get:CheckHeart (heart pieces, containers). That add is where
  parity/_ammo.py guards ammo. GetPouchContent Event0's predecessors are rerouted through Rando_AmmoGuard_Event0 in
  every seed (generate.py merges _ammo.guard_ops after the plugins), so ammo without its container adds nothing
  here, same as at an NPC.
  Covers OoTR's plain items, bottles and bottle contents, tokens (PouchData.Item_Token_Gold.StockNum), hearts,
  Double Defense, stones and medallions, masks, trade items (from plugin_item: Weird Egg comes hatched, the Pocket
  Egg hatched with the adult trade shuffle, the Broken Sword's own actor), the Master Sword, the Fishing Pole,
  consumables (Fairy Drop and Recovery Heart get single player's stand-in, config/item_map.json junk_for, a green
  rupee), Ice Arrows and Blue Fire Arrows (both Item_Arrow_Ice), and the Treasure Chest Game's rupees and heart
  piece.
- "progressive": progressive.host_graph's tier checks (highest owned first, OoTR's resolve_upgrades) with
  GET_ROUTINE and the tier. A tier with its own give entry (progressive.GIVE, progressive.give_node, like the child
  wallet's Kokiri Wallet, extras_items Rando_GetWalletSmall) calls that entry. The plan name is plugin_item's
  (extras_items gives "Progressive Kokiri Wallet" in a child-wallet seed). The Goron and progressive swords and the
  Deku stick and nut bags are progressive names too.
- "ocarina": the tier checks, then the tier's own give entry, like every single-player ocarina give
  (config/progressive.json "pose": false, tools/progressive.py NO_POSE). That's Dm_SY_GetInEvent:Rando_GiveOcarina
  {ActorName}, the fanfare, GetPouchContent:GetPouchContentByActorName (the vanilla ocarina give's window and
  silent add, Dm_Kokiri_0155 Event77/Event68) and the "after" call ActionGuide:OpenActionGuideSceenForOcarina.
  Without that call an ocarina found elsewhere can't be played, and tools/rando/no_pose_check.py enforces it.
  Never the hold-up, OotrR saw an ocarina held up crash the game. make_patch add_no_pose_entries adds that entry
  once when any step calls it.
- "song": GetPouchContent:GetPouchContentByActorName (get window, then the add), the call every vanilla song
  lesson gives its song with (Dm_MelodyGet_* in data/rewards.json, Dm_MelodyGet_Zelda Event111 for one). No
  hold-up pose, OotrR gives songs without one too.
- "dungeon": the owning plugin's credit entry, dungeons.call_target(item) -> Dm_SY_GetInEvent:Rando_DI_Call_<item>,
  the entry a core scene location's give step calls (dungeons.item_for for SCENE_LOCS). call_target records the
  item in dungeons._used["call"], so dungeons.world_plan adds that entry and its shared credit entry once (it runs
  after archipelago's, plugins run in name order).
  Covers small keys, key rings (the ring's full count, and its boss key with keyring_give_bk, dungeons._credit),
  boss keys, Ganon's boss key, maps, compasses, the Thieves' Hideout keys (the cells spend
  DungeonInfo.GerudoFortress.SmallKeyNum), the Treasure Chest Game's keys and rings in its keyed shuffle_tcgkeys
  modes, Triforce Hunt pieces, and silver rupees and pouches in their credited shuffle_silver_rupees modes. A pouch
  or rupee of the kind this seed doesn't hold for its puzzle goes through the held kind's credit (silver_leaf). A
  key ring of a dungeon without rings this seed is its keys and the small key's credit (ring_as_keys_leaf).
- "dungeon (current)": OoTR's generic Small Key / Boss Key / Map / Compass. No dungeon is named, so OoTR credits
  the dungeon the player is in (gSaveContext.mapIndex). We use the remake's own way, the big chest's
  Success_AddContent: Dm_SY_Treasurebox Event34 DisplayGetByActorName, Event23/26/27/30
  GameSystemActor.EventGetDungeon* (which credits the dungeon the player stands in, _dungeons_keys.py), then the
  pick-up window. Between the credit and the window the HUD shows the small key's counter (Dm_SY_Get
  Event175/Event183) or the boss key (Dm_SY_Treasurebox Event82/Event94), but only while the player is on a
  dungeon's map (hud_nodes, Sequence_CurrentBanc against every dungeon map). That matches how every named key
  credit asks for its counter in its own dungeon (GetPouchContent:Rando_DI_KeyShow). These are never in an OoTR or
  Archipelago item pool (only a /send can name them), and unseen outside a dungeon.
- "ice trap": _chests_scenes.freeze_graph()'s steps inline (the ice-trap attacker gets made, then "You are a
  FOOL!", GetPouchContent:Rando_IceTrapFool) and plan {"_ice_sensor": True}. generate.py then adds the attacker's
  files and the FOOL entry and text once (drops.ice_sensor_ops, _chests_scenes.fool_ops). It's always the ice
  kind, because remake_trap_weights draws a kind per OoTR location of this world and a received trap has none.
- "bean pack": the Magic Bean Pack the way _songs_trade_child._bean_pack_ops gives it (one bean held up, nine
  added), inline, because its entry RandoST_BeanPack only exists when this world places a pack.
- "soul": extras_souls' own give entry (Rando_Soul_* / Rando_SkeletonKey, with the soul's flag and message or the
  Skeleton Key's key counts), the entry extras_souls.item_for's call names. extras_souls.world_plan adds one per
  item its settings turn on.
- "milk": OoTR's Milk (GI_MILK puts milk into an empty bottle, and nothing without one, and there's no item_map
  entry). It's the cow's own hand-over, Dm_SY_GetInEvent:GetInEventInBottle {Item_Bottle_Milk, BottleItem 10,
  IsTalkCamera False} (Animal_Cow Event114), after PouchSystemActor.EventQueryIsAnyBottleEmpty (Animal_Cow
  Event113).
- "none": the item does nothing in this seed, same as in OoTR. That's Ocarina buttons (every button is playable,
  shuffle_individual_ocarina_notes is refused), Treasure Chest Game keys outside its keyed modes, Triforce pieces
  without a Triforce Hunt, silver rupees with the rooms' own counters (vanilla / remove) or of a Master Quest
  puzzle (mq_dungeons_mode must be vanilla), and soul items and the Skeleton Key with their extras_souls setting
  off.

Order: leaves() has to run before dungeons.world_plan, or the credit entries its leaves call never get added.
archipelago's world_plan does run first, since plugins run in name order.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
import progressive  # noqa: E402  (tools/progressive.py)

DONE = "@@DONE"
GET_FILE = "Dm_SY_GetInEvent"
GET_ROUTINE = "GetInEvent_NotTurn_NotNpc"
REF_LOCATION = "ZD Diving Minigame"  # a core scene location, MiniGame_Diving Event15/Event21 call GET_ROUTINE
DISPLAY = "GetPouchContent:DisplayGetByActorName"
SONG_GIVE = "GetPouchContent:GetPouchContentByActorName"
OCARINA = "Ocarina"
SONG_ACTOR = "Item_Melody_"
BEAN_PACK, BEAN, BEANS_MORE = "Magic Bean Pack", "Item_MagicBean", 9
MILK = "Milk"
OCARINA_BUTTONS = ("Ocarina A Button", "Ocarina C up Button", "Ocarina C down Button", "Ocarina C left Button",
                   "Ocarina C right Button")
# OoTR's generic dungeon items -> (model, the big chest's credit action for the dungeon the player stands in)
GENERIC = {"Small Key": ("Item_Dungeon_SmallKey", "EventGetDungeonSmallKey"),
           "Boss Key": ("Item_Dungeon_BossKey", "EventGetDungeonBossKey"),
           "Map": ("Item_Dungeon_Map", "EventGetDungeonMap"),
           "Compass": ("Item_Dungeon_Compass", "EventGetDungeonCompass")}
# the HUD display after a generic key's credit on a dungeon's map (hud_nodes), as (UISystemActor action, its
# parameter)
GENERIC_HUD = {"Small Key": ("EventTriggerSetDisplaySmallKey", "IsDisplaySmallKey"),
               "Boss Key": ("EventTriggerSetDisplayBossKey", "IsDisplayBossKey")}
SILVER_KINDS = ("Silver Rupee", "Silver Rupee Pouch")
TCG_ITEMS = ("Small Key (Treasure Chest Game)", "Small Key Ring (Treasure Chest Game)")
TRIFORCE = "Triforce Piece"
# Leaves can use these actors directly because DmF_SY_FallDown already declares them.
HOST_ACTORS = ("PouchSystemActor", "GameSystemActor", "UISystemActor", "EventSystemActor", "GameDataActor")


def _plugins(mods):
    return {m.__name__.rsplit(".", 1)[-1]: m for m in mods}


def _leaf(kind, nodes, start, plan=None):
    return {"nodes": nodes, "start": start, "plan": dict(plan or {}), "kind": kind}


def _wait(nxt):
    return {"actor": "EventSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 1},
            "next": nxt}


def _get(actor, nxt=DONE):
    """GET_ROUTINE with `actor` (MiniGame_FrogTenors Event384's parameters). An actor Link can't hold up as it is
    (config/hold_up.json, so stones, medallions, the Master Sword) gets its own hold-up (progressive.hold_node)."""
    held = progressive.hold_node(actor, nxt, "RandoAP_Mailbox")  # calls from the mailbox need a file name
    if held:
        return held
    return {"call": f"{GET_FILE}:{GET_ROUTINE}", "params": {"ActorName": actor, "IsNpcEventStarter": False},
            "next": nxt}


def _add(actor, nxt, num=1):
    """A silent pouch add (Dm_Kokiri_0155 Event68's parameters; the bean pack's nine more beans)."""
    return {"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
            "params": {"Actor": actor, "Num": num, "IsEquipDIrect": False, "IsSetMessageTargetActorName": num == 1,
                       "IsGetEvent": False}, "next": nxt}


def nothing(why):
    """A leaf that gives nothing (the caller still counts it)."""
    return _leaf(f"none: {why}", {"none": _wait(DONE)}, "none")


# Kinds
def get_leaf(actor):
    return _leaf("get", {"get": _get(actor)}, "get")


def progressive_leaf(name, kind="progressive"):
    """Tier checks (progressive.host_graph, owning tier k or above gives k+1 and the top tier repeats), then give{k}.
    That's the tier's own give entry (progressive.give_node, for the Kokiri Wallet and the ocarinas) or GET_ROUTINE
    with the tier."""
    tiers = progressive.PROGRESSIVE[name]["tiers"]
    n, start = progressive.host_graph(tiers, GET_ROUTINE, "ActorName")
    for k, tier in enumerate(tiers):
        n[f"give{k}"] = progressive.give_node(tier, DONE) if tier in progressive.GIVE else _get(tier)
    return _leaf(kind, _reachable(n, start), start)


def _reachable(n, start):
    """The nodes reachable from `start` (host_graph's own give steps, replaced above, may have had followers)."""
    seen, todo = set(), [start]
    while todo:
        lab = todo.pop()
        if lab in seen or lab not in n:
            continue
        seen.add(lab)
        v = n[lab]
        todo += [v.get("next"), v.get("join")] + list((v.get("cases") or {}).values()) + list(v.get("fork") or [])
    return {k: v for k, v in n.items() if k in seen}


def ocarina_leaf():
    """The ocarinas. Each tier uses its own give entry, never the hold-up (progressive.NO_POSE), and it's refused
    without one."""
    tiers = progressive.PROGRESSIVE[OCARINA]["tiers"]
    loose = [t for t in tiers if not progressive.no_pose(t) or t not in progressive.GIVE]
    if loose:
        raise ValueError(f"{OCARINA}: {loose} would be held up (config/progressive.json: no 'pose': false give)")
    return progressive_leaf(OCARINA, "ocarina")


def song_leaf(actor):
    return _leaf("song", {"song": {"call": SONG_GIVE, "params": {"ActorName": actor}, "next": DONE}}, "song")


def dungeon_leaf(dg, item):
    """The credit entry from dungeons.call_target, registered so dungeons.world_plan adds it."""
    return _leaf("dungeon", {"credit": {"call": dg.call_target(item), "next": DONE}}, "credit")


def silver_leaf(dg, silver, item, world):
    """A credited silver-rupee item.
    The puzzle's credit (its GetPouchContent entry with the count, text and the room's flags at 5) only exists for
    the kind this seed holds for that puzzle, rupees or the pouch (_dungeons_silver_shuffle.world_plan: _kinds,
    silver_rupee_pouches). So the other kind, which only a /send can bring, goes through that one:
      - a pouch for a rupee puzzle sets the count to 4, then the rupee's credit adds the fifth (its "all five" text,
        the room solved)
      - a rupee for a pouch puzzle adds 1 to the count, and the pouch's credit (its text, the room solved) runs when
        that makes 5. Below that it's silent, since no rupee text exists for that puzzle."""
    kind, puzzle = silver.dungeon_item_name(item)
    held = silver._kinds(world).get(puzzle)
    if held is None:
        return nothing(f"no silver-rupee item of {puzzle} in this seed (no credit entry for it)")
    if held == kind:
        return dungeon_leaf(dg, item)
    count = silver.COUNT.format(silver.index(puzzle))
    other = dg.call_target(f"{held} ({puzzle})")
    if kind == silver.KINDS[1]:  # a pouch, the puzzle's rupees in this seed
        n = {"four": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                      "params": {"Index": -1, "GameDataName": count, "Value": 4}, "next": "fifth"},
             "fifth": {"call": other, "next": DONE}}
        return _leaf("dungeon (pouch as the 5th rupee)", n, "four")
    n = {"add": {"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt",
                 "params": {"Index": -1, "GameDataName": count, "Value": 1}, "next": "five"},
         "five": {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                  "params": {"Index": -1, "GameDataName": count, "Value": 5},
                  "cases": {silver.BELOW: "quiet", silver.EQUAL: "pouch", silver.ABOVE: "quiet"}},
         "pouch": {"call": other, "next": DONE},
         "quiet": _wait(DONE)}
    return _leaf("dungeon (rupee in a pouch puzzle)", n, "add")


def ring_as_keys_leaf(dg, dungeon):
    """A key ring of a dungeon that has none in this seed (World.keyring false, so only a /send brings it).
    Its effect is the ring's credit, dungeons._credit, which is the dungeon's full key count (keys or locked doors,
    whichever is more). No boss key, World.keyring_give_bk needs the ring setting. Its look is the ring's,
    Item_Dungeon_SmallKey's hold-up and window (dungeons.MODEL). So all keys but one get added silently, then the
    dungeon's small-key credit entry runs (dungeons.call_target, the one key's hold-up and the last key). We do that
    instead of giving it a ring entry of its own, which would be about 17 steps in Dm_SY_GetInEvent (and every NPC
    gift loads that file) for a ring the seed doesn't use. The Treasure Chest Game's ring works the same way: five to
    Rando_TcgKeyNum, then the key's credit (its count message)."""
    from parity import _dungeons_keys as keys
    if dungeon == dg.TCG:
        steps = [{"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt",
                  "params": {"Index": -1, "GameDataName": dg.TCG_COUNT, "Value": dg.TCG_KEYS - 1}}]
    else:
        d = dg.DUNGEONS[dungeon]
        n = max(d["keys"], d["doors"])
        steps = keys.key_steps(keys.key_rows(d["area"]), n - 1) if n > 1 else []
    nodes = {f"k{i}": dict(st, next=f"k{i + 1}" if i + 1 < len(steps) else "last") for i, st in enumerate(steps)}
    nodes["last"] = {"call": dg.call_target(f"Small Key ({dungeon})"), "next": DONE}
    return _leaf("dungeon (ring as keys)", nodes, "k0" if steps else "last")


def dungeon_maps():
    """Every dungeon's map the way Sequence_CurrentBanc names it there (_dungeons_keys.banc, like "ForestTemple", or
    "GerudoFortress_Adult" for the hideout), in data/rando/dungeons_world.json's order."""
    import json
    from parity import _dungeons_keys as keys
    with open(os.path.join(HERE, "data", "rando", "dungeons_world.json"), encoding="utf-8") as f:
        areas = [d["area"] for d in json.load(f)["dungeons"].values()]
    return list(dict.fromkeys(keys.banc(a) for a in areas))


def hud_nodes(item, nxt):
    """{label: node} from "map0", the HUD display a generic key's credit asks for, only on a dungeon's map.
    The credit's dungeon is the one the player stands in. Anywhere else it credits nothing and shows nothing, like in
    OoTR. The checks compare Sequence_CurrentBanc with each dungeon map (EventQueryIsGameDataString64, case 0 = equal,
    the way _dungeons_keys.show_event and ReplaceEquipmentForEraChange Event14 read it). On a dungeon map we run the
    game's own steps after its own key or boss key:
      - Dm_SY_Get Event175 EventTriggerSetDisplaySmallKey and Event183's 50 frames. The credit's
        OneShotDungeonGetSmallKey already requested the count-up, so there's no second request, unlike
        GetPouchContent:Rando_DI_KeyShow after a save-data add.
      - Dm_SY_Treasurebox Event82/Event94 for the boss key"""
    from parity import _dungeons_keys as keys
    action, param = GENERIC_HUD[item]
    maps = dungeon_maps()
    n = {f"map{i}": {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                     "params": {"Index": -1, "GameDataName": keys.CURRENT, "Value": m},
                     "cases": {0: "hud", 1: f"map{i + 1}" if i + 1 < len(maps) else nxt}} for i, m in enumerate(maps)}
    n["hud"] = {"actor": "UISystemActor", "action": action, "params": {param: True}, "next": "hudwait"}
    n["hudwait"] = {"actor": "EventSystemActor", "action": "EventWait", "params": {"Frames": 50, "IsWaitEnd": True},
                    "next": nxt}
    return n


def generic_dungeon_leaf(item):
    model, action = GENERIC[item]
    n = {"show": {"call": DISPLAY, "params": {"ActorName": model}, "next": "credit"},
         "credit": {"actor": "GameSystemActor", "action": action, "params": {"IsWaitEnd": True},
                    "next": "map0" if item in GENERIC_HUD else "pickup"},
         "pickup": {"actor": "UISystemActor", "action": "EventTriggerRequestOpenPickUpWindow",
                    "params": {"ActorName": model}, "next": DONE}}
    if item in GENERIC_HUD:  # the key counter / boss key on the HUD, in a dungeon only
        n.update(hud_nodes(item, "pickup"))
    return _leaf("dungeon (current)", n, "show")


def ice_trap_leaf():
    from parity import _chests_scenes as scenes
    _, n, start = scenes.freeze_graph()
    n = {k: dict(v) for k, v in n.items()}
    for v in n.values():
        if "next" in v and v["next"] is None:
            v["next"] = DONE
    return _leaf("ice trap", n, start, {"_ice_sensor": True})


def trap_kind_leaf(kind, world, plugins):
    """A received Shock/Fire/Rupee Trap (remake_trap_weights' kinds, named in the spoiler and ids.json).
    It's the kind's effect entry in Dm_SY_GetInEvent, the one core scene locations call (chests.trap_call).
    chests.trap_host_ops adds that entry once per seed. That happens here first since plugins run in name order, so
    chests' own call adds nothing after that."""
    from parity import _chests_scenes as scenes
    ch = plugins.get("chests")
    ops = ch.trap_host_ops(world, kind) if ch is not None else scenes.trap_event_ops(kind, "host")
    plan = {"events": ops} if ops else {}
    if kind in scenes.SENSORS:  # its attacker (chests.finish_plan adds it, with the FOOL entry it ends on)
        plan["_trap_sensors"] = [kind]
    return _leaf(f"trap ({kind})", {"fx": {"call": scenes.trap_call(kind), "next": DONE}}, "fx", plan)


def bean_pack_leaf():
    return _leaf("bean pack", {"get": _get(BEAN, "more"), "more": _add(BEAN, DONE, BEANS_MORE)}, "get")


def soul_leaf(entry):
    return _leaf("soul", {"give": {"call": entry, "next": DONE}}, "give")


def milk_leaf():
    n = {"empty": {"actor": "PouchSystemActor", "query": "EventQueryIsAnyBottleEmpty",
                   "cases": {progressive.YES: "fill", progressive.NO: "none"}},
         "fill": {"call": f"{GET_FILE}:GetInEventInBottle", "next": DONE,
                  "params": {"ActorName": "Item_Bottle_Milk", "BottleItem": 10, "IsTalkCamera": False}},
         "none": _wait(DONE)}
    return _leaf("milk", n, "empty")


# Which kind
def _dungeon_item(plugins, item, settings, world):
    """leaf for an item the dungeons plugin credits, a "none" leaf where it means nothing in this seed, or None."""
    dg = plugins.get("dungeons")
    if item in TCG_ITEMS:
        if getattr(settings, "shuffle_tcgkeys", "vanilla") in ("vanilla", "remove") or "chests" not in plugins:
            return nothing("Treasure Chest Game keys count only in its keyed shuffle_tcgkeys modes")
    elif item == TRIFORCE:
        if not getattr(settings, "triforce_hunt", False) or "story" not in plugins:
            return nothing("no Triforce Hunt")
    elif item.split(" (")[0] in SILVER_KINDS:
        from parity import _dungeons_silver_shuffle as silver
        if silver.dungeon_item_name(item) is None:
            return nothing("a Master Quest silver-rupee puzzle (the remake has one layout per dungeon)")
        if dg is None or dg.dungeon_item(item) is None:
            return nothing("silver rupees count in their rooms (shuffle_silver_rupees vanilla / remove)")
        return silver_leaf(dg, silver, item, world)
    if dg is None:
        if item in TCG_ITEMS or item == TRIFORCE or item.endswith(")") and item.split(" (")[0] in (
                "Small Key", "Small Key Ring", "Boss Key", "Map", "Compass"):
            raise ValueError(f"{item}: needs the dungeons plugin (its credit entries)")
        return None
    info = dg.dungeon_item(item)
    if info is None:
        return None
    if info[0] == "Small Key Ring" and not world.keyring(info[1]):
        return ring_as_keys_leaf(dg, info[1])
    return dungeon_leaf(dg, item)


def _soul(plugins, item, settings):
    """extras_souls' items. Its give entry while its setting is on (it adds one per item then), else nothing. A
    disabled plugin's settings are refused, so then none is on."""
    from parity import extras_souls as ex
    if item not in _all_souls(ex):
        return None
    hit = ex.items(settings).get(item) if "extras_souls" in plugins else None
    if hit is None:
        return nothing("its extras_souls setting is off")
    return soul_leaf(f"{ex.HOST_FILE}:{ex._entry(*hit)}")


def _all_souls(ex):
    lg = ex.logic()
    return ({v["item"] for v in lg["bosses"].values()} | {lg["ganon"]["item"]} | {b["item"] for b in lg["beans"]}
            | {ex.SKELETON})


def check_host(lf):
    """[problem, ...] for a leaf that wouldn't fit the mailbox's file: an actor it doesn't declare, a step naming an
    existing step, a call without its file, a "@@DONE" outside "next", a label or start that isn't there."""
    bad, labels = [], set(lf["nodes"])
    if lf["start"] not in labels:
        bad.append(f"start {lf['start']} is no label")
    for lab, n in lf["nodes"].items():
        if "actor" in n and n["actor"] not in HOST_ACTORS:
            bad.append(f"{lab}: actor {n['actor']} (the mailbox's file declares {', '.join(HOST_ACTORS)})")
        if "call" in n and (not isinstance(n["call"], str) or n["call"].startswith(":") or ":" not in n["call"]):
            bad.append(f"{lab}: call {n['call']!r} without its file")
        others = list((n.get("cases") or {}).values()) + list(n.get("fork") or [])
        if n.get("join") not in (None, True):
            others.append(n["join"])
        for t in [x for x in [n.get("next")] if x != DONE] + others:  # (DONE only as a "next")
            if t is not None and t not in labels:
                bad.append(f"{lab}: goes to {t!r}")
    return bad


def leaf(item, world, settings, mods):
    """The mailbox's steps giving OoTR item `item` (module doc), checked against the mailbox's file (check_host)."""
    lf = _pick(item, world, settings, mods)
    bad = check_host(lf)
    if bad:
        raise ValueError(f"{item}: leaf doesn't fit the mailbox's file: {'; '.join(bad)}")
    return lf


def _pick(item, world, settings, mods):
    import generate
    plugins = _plugins(mods)
    if item == "Ice Trap":  # its files and text come from generate.py, whatever plugins are on
        return ice_trap_leaf()
    from parity import chests as _ch
    kinds = {name: k for k, name in _ch.TRAP_NAMES.items() if k != "ice"}
    if item in kinds:
        return trap_kind_leaf(kinds[item], world, plugins)
    if item in OCARINA_BUTTONS:
        return nothing("every Ocarina button is playable (shuffle_individual_ocarina_notes is refused)")
    if item in GENERIC:
        return generic_dungeon_leaf(item)
    if item == MILK:
        return milk_leaf()
    if item == BEAN_PACK:
        return bean_pack_leaf()
    found = _dungeon_item(plugins, item, settings, world) or _soul(plugins, item, settings)
    if found is not None:
        return found
    target = generate.plugin_item(mods, item, REF_LOCATION, world)
    if isinstance(target, dict):
        if set(target) != {"item"}:
            raise ValueError(f"{item}: single player gives {target} at a scene location, which this module doesn't "
                             f"know how to give from the mailbox")
        target = target["item"]
    if target == OCARINA:
        return ocarina_leaf()
    if target in progressive.PROGRESSIVE:
        return progressive_leaf(target)
    if target.startswith(SONG_ACTOR):
        return song_leaf(target)
    return get_leaf(target)


def leaves(world, settings, mods, codes):
    """{code: leaf} for every {item: code} of `codes`, or ValueError naming every item it can't give."""
    out, bad = {}, []
    for item, code in sorted(codes.items(), key=lambda kv: kv[1]):
        try:
            out[code] = leaf(item, world, settings, mods)
        except Exception as e:  # noqa: BLE001 - collected and reported together
            bad.append(f"{item} ({code}): {e}")
    if bad:
        raise ValueError(f"the mailbox can't give {len(bad)} item(s) faithfully: " + "; ".join(bad))
    return out
