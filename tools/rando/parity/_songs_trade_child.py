"""Child trade items (shuffle_child_trade), the Happy Mask Shop (MaskShop locations, complete_mask_quest) and the
Magic Bean salesman (shuffle_beans), for the songs/trade plugin (songs_trade.py).

The step data is data/rando/songs_trade_child.json (built from the game files by _songs_trade_child_build.py, which
checks every step named here).

OoTR's child trade locations are HC Malon Egg (Weird Egg, or the Chicken when only the Chicken is shuffled), HC
Zeldas Letter and the 8 Market Mask Shop items. The mask sales to the guard, Skull Kid, graveyard boy and running
man aren't OoTR locations. HC Malon Egg and HC Zeldas Letter are core scene locations (config/rando_locations.json
"testing"), and this module adds what their shuffle needs in the game:
- Weird Egg / Chicken. The remake hatches the egg by a story step (Goto_HyruleCastle Step03_01, the morning after
  Malon's gift, Navi's step-start scene), not by the item, so an egg found elsewhere would never hatch. That's why
  OoTR's Weird Egg is handed over already hatched (the Chicken, Item_AlarmCucco) everywhere but at Malon. The hatch
  scene now only hatches an egg the player holds (otherwise it just moves the step on, like the hatch does), so
  Malon's scene doesn't hand out a free Chicken any more. Waking Talon (shown the Chicken) moves the castle story
  past Malon's gift and she leaves, so the wake-up now needs Malon's gift to have been given (her own flag), which a
  child at the castle grounds can always do first. Malon's give step Event55 is the egg's removal at hatching
  (Num -1), and it has to stay the egg (see Needs).
- Zelda's Letter: the guard reacts to a shown letter until the gate is open (item-based), so nothing to change.
- Masks (any subset, complete_mask_quest either value): every shuffled mask's shelf slot gives its item once, free,
  from the shop's opening (Kakariko gate open), one shuffled slot at a time in GoodsList order. That's a 4-bit
  counter on spare save flags, and each slot's Release expression HappyMaskShop_HasMask_* becomes "shop open AND
  counter == k". The selection is caught before the shop's own checks (DisplayShop Event134): the screen closes,
  the item is handed over with the game's get routine, and the counter moves on. OoTR's rules for the slots ask
  more (the quest), so logic is never looser than the game. Renting a vanilla mask doesn't take back the masks the
  player holds any more, since the found masks are real items here. With the Mask of Truth shuffled, the
  remake-only Mask of Truth hand-over after the Bunny Hood payment (Npc_Hylia_023_Shop_Child Event51) is skipped.
- Beans: the salesman sells one item once for 60 rupees (his 60-rupee tier, no "can it go in the pouch" check),
  then says he has no more. OoTR's Magic Bean Pack gives 10 beans (one held up, nine added) and only goes to scene
  locations whose give step can call a scene (core scene locations and the salesman).
"""
import json
import os

from . import _songs_trade_ops as ops

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_PATH = os.path.join(HERE, "data", "rando", "songs_trade_child.json")
DATA = json.load(open(DATA_PATH, encoding="utf-8")) if os.path.exists(DATA_PATH) else None

EGG_LOCATION, LETTER_LOCATION = "HC Malon Egg", "HC Zeldas Letter"
CHILD_LOCATIONS = (EGG_LOCATION, LETTER_LOCATION)
MASK_LOCATIONS = {m: s["location"] for m, s in (DATA or {}).get("mask_shop", {}).get("slots", {}).items()}
BEAN_LOCATION = "ZR Magic Bean Salesman"
BEAN_PACK = "Magic Bean Pack"
BEAN_PACK_CALL = "Dm_SY_GetInEvent:RandoST_BeanPack"
CHICKEN = "Item_AlarmCucco"
# OoTR items config/item_map.json has no remake actor for (kept here: the map is shared)
ACTORS = {"Chicken": CHICKEN}
ACTORS.update({m: s["get_actor"] for m, s in (DATA or {}).get("mask_shop", {}).get("slots", {}).items()})


def _shuffled(settings):
    return set(getattr(settings, "shuffle_child_trade", None) or [])


def _masks(settings):
    """Shuffled masks in GoodsList order (the order their slots open)."""
    slots = DATA["mask_shop"]["slots"]
    return sorted((m for m in _shuffled(settings) if m in slots), key=lambda m: slots[m]["index"])


def check_settings(settings):
    problems = []
    if DATA is None:
        problems.append("data/rando/songs_trade_child.json missing: run tools/rando/parity/_songs_trade_child_build.py")
    bad = _shuffled(settings) - {"Weird Egg", "Chicken", "Zeldas Letter"} - set(MASK_LOCATIONS)
    if bad:
        problems.append(f"shuffle_child_trade: unknown {sorted(bad)}")
    if len(_masks(settings) if DATA else []) > 15:
        problems.append("shuffle_child_trade: more than 15 mask slots for the 4-bit counter")
    return problems


def active(settings):
    """OoTR locations this module patches for these settings (HC Malon Egg / HC Zeldas Letter are the core's)."""
    out = {MASK_LOCATIONS[m] for m in _masks(settings)}
    if getattr(settings, "shuffle_beans", False):
        out.add(BEAN_LOCATION)
    return out


def actor_for(item_name):
    """Remake get actor for an OoTR child-trade item config/item_map.json lacks (masks, Chicken), else None."""
    return ACTORS.get(item_name)


def item_for(item, location, world):
    """For songs_trade.item_for: chests and core scene locations."""
    if item == "Weird Egg" and location != EGG_LOCATION:
        return CHICKEN  # handed over hatched: the remake hatches only an egg held on the morning after Malon's gift
    if item == BEAN_PACK:
        import generate
        if location in generate.scene_locations():
            return {"item": "Item_MagicBean", "call": BEAN_PACK_CALL}
        return None
    return actor_for(item)


def target(item_name, location=None):
    """OoTR item -> the plugin's give target ({"actor"}, {"progressive"}, {"ice_trap"}), or {"call": scene} for the
    Magic Bean Pack. It knows the child-trade items config/item_map.json lacks. songs_trade._target uses it too.
    `location` is the OoTR location, for the trap kind an Ice Trap there drew."""
    if item_name == "Weird Egg":
        return {"actor": CHICKEN}
    if item_name == BEAN_PACK:  # ("model": what a core reward spec names, never handed over: ops.reward_spec)
        return {"call": BEAN_PACK_CALL, "model": "Item_MagicBean"}
    if actor_for(item_name):
        return {"actor": actor_for(item_name)}
    from . import songs_trade
    return songs_trade._target(item_name, location)


def give(o, t, nxt):
    """o.give for a target() result (the bean pack calls its scene)."""
    if "call" in t:
        return {"call": t["call"], "next": nxt}
    return o.give(t, nxt)


def _egg_mapping_has_removal():
    """Whether the core's HC Malon Egg location still includes the hatch's egg removal (Event55) as a give step."""
    match = json.load(open(os.path.join(HERE, "data", "ootr_match.json"), encoding="utf-8"))["ootr_locations"]
    x = next((m for m in match if m["ootr"] == EGG_LOCATION), {})
    return "event/Goto_HyruleCastle/Item_WeirdEgg" in (x.get("remake") or [])


def _resolved_here(kept):
    """Locations whose item this plugin resolves through item_for / target(): core chests (chest_map.json, written by
    the generator) other than the chests plugin's own, core scene locations, and the songs/trade plugin's kept ones.
    Other plugins (chests' own chests, shops, drops) read config/item_map.json, which has no mask or Chicken and an
    unhatched Weird Egg, so child-trade items stay out of their locations."""
    import generate
    from parity import chests
    cm = json.load(open(os.path.join(HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"]
    theirs = set(chests._mine())
    core = {n for n, v in cm.items() if v["mode"] in ("full", "group") and n not in theirs}
    return core | set(generate.scene_locations()) | set(kept)


def before_fill(world, settings, kept):
    """Item rules. The Magic Bean Pack only goes where a give step can call its scene (ops.no_call_locations: not chests
    or shop shelves). HC Malon Egg takes no progressive item or ice trap while the core still edits the hatch's
    removal step with it. The Weird Egg, the Chicken and the masks go anywhere, since every plugin hands them over
    through the shared resolver (songs_trade.hand_actor / _target, the egg hatched). Shop shelves refuse them by their
    own rule."""
    import generate
    names = {it.name for it in world.itempool}
    if BEAN_PACK in names:
        no_call = ops.no_call_locations(world)
        for loc in world.get_locations():
            if loc.type in generate.NOT_ITEM_CHECKS or loc.item is not None or loc.name not in no_call:
                continue
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: item.name != BEAN_PACK and prev(location, item))
    if _shuffled(settings) & {"Weird Egg", "Chicken"} and _egg_mapping_has_removal():
        try:
            loc = world.get_location(EGG_LOCATION)
        except KeyError:
            loc = None
        if loc is not None and loc.item is None:
            prev = loc.item_rule
            prog = ops.progressive.PROGRESSIVE
            loc.item_rule = (lambda location, item, prev=prev: item.name not in prog and item.name != "Ice Trap"
                             and prev(location, item))


def _item(world, name):
    try:
        loc = world.get_location(name)
    except KeyError:
        return None
    return loc.item.name if loc.item is not None else None


def _set(flag, value, nxt):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
            "params": {"GameDataName": flag, "Value": value, "Index": -1}, "next": nxt}


def _egg_ops(o, world, settings):
    if not _shuffled(settings) & {"Weird Egg", "Chicken"}:
        return
    d = DATA["egg"]
    f = d["file"]
    # hatch only an egg the player holds; otherwise move the step on as the hatch does (Step03_02)
    n = {"q": {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
               "params": {"Actor": "Item_WeirdEgg", "Num": 1},
               "cases": {ops.YES: ops.at(d["hatch_start"]["event"]), ops.NO: ops.at(d["after_hatch"]["event"])}}}
    o.replace(f, f, d["hatch_start"], "RandoST_EggHatchGate", n, "q")
    # Talon wakes only after Malon's gift (waking him first moves the story past her and she leaves the castle)
    n = {"q": ops.flag_query(d["gift_flag_name"], ops.at(d["wake"]["event"]), None)}
    o.replace(f, f, d["wake"], "RandoST_TalonWakeGate", n, "q")
    item = _item(world, EGG_LOCATION)
    # The core edits the hatch's egg removal (Event55) with HC Malon Egg's item while data/ootr_match.json pairs the
    # location with both steps. The gate above makes that step unreachable unless an Item_WeirdEgg is held, and only
    # Malon's own vanilla egg (or a starting Weird Egg) can be one, since every other Weird Egg comes hatched.
    o.notes.append(f"{EGG_LOCATION}: {item}; Weird Egg elsewhere comes hatched (the Chicken); the hatch needs a held "
                   "egg; Talon wakes only after Malon's gift")


def _mask_ops(o, world, settings, kept):
    masks = [m for m in _masks(settings) if MASK_LOCATIONS[m] in kept]
    if not masks:
        return
    d = DATA["mask_shop"]
    f = d["file"]
    bits = DATA["flags"]["mask_bits"]
    exps = {}
    n = {}
    for k, m in enumerate(masks):
        slot = d["slots"][m]
        # Release: the shop is open and the counter is at this slot
        steps = [[0, d["gate"]]]
        for i, b in enumerate(bits):
            steps.append([0, b])
            if not (k >> i) & 1:
                steps.append([5])
            steps.append([3])
        exps[slot["release"]] = steps
        nxt = f"q{k + 1}" if k + 1 < len(masks) else ops.at(d["sold_check"]["event"])
        n[f"q{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                      "params": {"GameDataName": "Shop_SelectItemName", "Index": -1, "Value": slot["pouch"]},
                      "cases": {ops.YES: f"close{k}", ops.NO: nxt}}
        n[f"close{k}"] = {"copy": d["close"]["event"], "next": f"give{k}"}
        item = _item(world, MASK_LOCATIONS[m])
        n[f"give{k}"] = give(o, target(item, MASK_LOCATIONS[m]), f"bit{k}_0")
        for i, b in enumerate(bits):
            last = i + 1 == len(bits)
            n[f"bit{k}_{i}"] = _set(b, bool(((k + 1) >> i) & 1), ops.at(d["end"]["event"]) if last else f"bit{k}_{i + 1}")
        o.notes.append(f"{MASK_LOCATIONS[m]} ({m} slot, opens {k + 1} of {len(masks)}): {item}")
        # got once the counter has moved past this slot (for the trackers: songs_trade.got_flags)
        o.mask_got = dict(getattr(o, "mask_got", None) or {},
                          **{MASK_LOCATIONS[m]: {"t": "count", "bits": list(bits), "min": k + 1}})
    o.replace(f, f, d["sold_check"], "RandoST_MaskShop", n, "q0")
    o.gamedata.append({"boolexp": exps})
    # renting a vanilla mask no longer takes back the masks the player holds
    o.events.append({"file": f, "flowchart": f, "entry": "Rental_Common", "next": d["borrow"]["event"]})
    if "Mask of Truth" in masks:  # the remake-only hand-over after the Bunny Hood payment gives the vanilla mask
        t = d["truth_handover"]
        for kind, where, idx in t["preds"]:
            op = {"file": d["truth_file"], "flowchart": d["truth_file"], "event": where, "next": None}
            if kind in ("case", "fork"):
                op[kind] = idx
            o.events.append(op)


def _bean_ops(o, world, settings, kept):
    if not getattr(settings, "shuffle_beans", False) or BEAN_LOCATION not in kept:
        return
    item = _item(world, BEAN_LOCATION)
    if item is None:
        return
    d = DATA["beans"]
    f = d["file"]
    flag = DATA["flags"]["beans_sold"]
    n = {"q": ops.flag_query(flag, ops.at(d["sold_out"]["event"]), ops.at(d["tier"]["event"]))}
    o.replace(f, f, d["branch"], "RandoST_BeanSale", n, "q")
    s = d["shop"]
    # The shuffled item skips this sale's pouch check, and the sold flag gets set after the hand-over.
    o.events.append({"file": "SimpleShop", "flowchart": "SimpleShop", "event": s["rupees"]["event"], "case": 0,
                     "next": s["buy"]["event"]})
    o.replace("SimpleShop", "SimpleShop", s["count"], "RandoST_BeansSold", {"set": _set(flag, True, ops.at(
        s["count"]["event"]))}, "set")
    rid = d["give_reward_id"]
    if item == "Ice Trap":
        from parity import chests
        o.rewards[rid] = dict(chests.scene_ice_spec(rid, BEAN_LOCATION, world), note=f"{BEAN_LOCATION}: {item}")
    elif item == BEAN_PACK:
        o.rewards[rid] = {"item": "Item_MagicBean", "call": BEAN_PACK_CALL, "note": f"{BEAN_LOCATION}: {item}"}
    else:
        t = target(item)
        o.rewards[rid] = ops.reward_spec(t, f"{BEAN_LOCATION}: {item}", [rid])
    o.notes.append(f"{BEAN_LOCATION}: {item} (once, 60 rupees), then no more beans")


def _bean_pack_ops(o, world):
    if not any(loc.item is not None and loc.item.name == BEAN_PACK for loc in world.get_locations()):
        return
    o.events.append({"file": ops.GET_FILE, "flowchart": ops.GET_FILE, "add_graph": "RandoST_BeanPack", "start": "get",
                     "nodes": {"get": {"call": f"{ops.GET_FILE}:{ops.GET_ROUTINE}",
                                       "params": {"ActorName": "Item_MagicBean"}, "next": "more"},
                               "more": {"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
                                        "params": {"Actor": "Item_MagicBean", "Num": 9, "IsEquipDIrect": False,
                                                   "IsSetMessageTargetActorName": False, "IsGetEvent": False},
                                        "next": None}}})
    o.notes.append(f"{BEAN_PACK}: one bean held up, nine more added ({BEAN_PACK_CALL})")


def world_plan_ops(o, world, settings, kept):
    """Adds this module's patch ops to `o`, an _songs_trade_ops.Ops. `o.gamedata` gets created if it's missing."""
    if not hasattr(o, "gamedata"):
        o.gamedata = []
    _egg_ops(o, world, settings)
    _mask_ops(o, world, settings, kept)
    _bean_ops(o, world, settings, kept)
    _bean_pack_ops(o, world)


def plan_gamedata(o):
    """The save-data ops we collected. Merge them into the plugin's plan as "gamedata"."""
    return list(getattr(o, "gamedata", []))


LOGIC = {}  # no rule changes, OoTR's rules for every location here are at least as strict as the patched game
