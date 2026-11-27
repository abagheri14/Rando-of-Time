"""LH Sun (Fire Arrows) and LH Underwater Item (Ruto's Letter) for the songs/trade plugin (songs_trade.py).
They're NPC locations in OoTR but world pickups in the remake.

Both pickups are placed actors. The arrow is HyruleField_Adult_Static Obj_Arrow_Fire 4598657944866228526, named
"Item", because the sun-shot cutscene Dm_LakeHrl_0030 lowers it by that name. The letter is HyruleField_Child_Static
Obj_Bottle_Letter 474136620438465634, AlwaysRespawn, with no save flag. Picking one up runs the shared get scenes
Dm_SY_Get (standing) or Dm_SY_Get_WithoutPlayer (in the air or water), and both have scene IDs. They add the picked
actor itself (EventTriggerAddOwnToPouch) and branch on its tag (EventQueryCheckTagOnPouchActor). Tag 0 runs
Get_StoneOfWater:StoneOfWater_GetRutoletter (only the letter) and tag 1 runs SubEvent_GetFireArrow:GetFireArrow (only
the Fire Arrows). Swapping the placed actor isn't an option. The cutscene finds the arrow by type and name, and the
letter has no save flag a new pickup type could keep.

So both get scenes now ask the tag first. On tag 0 or 1, if the location's item hasn't been given yet, the picked
actor is hidden and the location's item is given with the get window (GetPouchContent:GetPouchContentByActorName,
what the vanilla scene shows in water or air, see RESIDENT_HOST for why there's no hold-up). A save flag records it,
and for the arrow the Fire Arrow challenge completes the way its pickup does. If it was given already, the actor is
hidden and nothing else happens, so no second item and no vanilla Fire Arrows or letter. The letter's placement also
gets a Presence on that flag, so it stops appearing once its item is given. Every other pickup (tags 2-4 or none)
runs the vanilla scene unchanged. A location holding its vanilla item keeps the vanilla pickup.

The same hook gives the drops plugin's heart spots, the placed heart pieces and heart containers that hold another
item (drops.get_scene_pickups). Each of those placements has a Name, and its pickup's event AI answers
EventQueryCheckTagOnPouchActor with the spot's tag (5 and up) for that name (tools/rando/drops.py get_scene_ops).
A tag's branch hides the heart, gives the item and requests the heart's death. The give is _resident_give, so the
get window, with traps, dungeon items and the bean pack going through their own steps in Dm_SY_Get. The death
request is the step the vanilla scene runs after its give, and the PickedUp death saves the placement's flag. With
no heart spot the hook is exactly the lake one above, and the lake branches never change.
"""
from . import _songs_trade_ops as ops

LH_SUN = "LH Sun"
LH_LETTER = "LH Underwater Item"
LOCATIONS = (LH_SUN, LH_LETTER)
VANILLA = {LH_SUN: "Fire Arrows", LH_LETTER: "Rutos Letter"}
TAG = {LH_LETTER: 0, LH_SUN: 1}  # EventQueryCheckTagOnPouchActor case read from Dm_SY_Get Event43/Event115
LETTER_PLACEMENT = {"file": "Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs", "hash": "474136620438465634"}
POUCH_FILE, POUCH_ROUTINE = "GetPouchContent", "GetPouchContentByActorName"


def active(settings):
    return set(LOCATIONS)


def _window_give(o, target, nxt):
    """Gives through GetPouchContent's add-and-window routine, or for a progressive item through a tier entry next to
    it."""
    if "progressive" in target:
        name = target["progressive"]
        entry = "RandoST_Pouch_" + "".join(w for w in name.title().split() if w.isalnum())
        if entry not in o._hosts:
            o._hosts.add(entry)
            nodes, start = ops.progressive.host_graph(ops.progressive.PROGRESSIVE[name]["tiers"], POUCH_ROUTINE,
                                                      "ActorName", host=POUCH_FILE)
            o.events.append({"file": POUCH_FILE, "flowchart": POUCH_FILE, "add_graph": entry, "nodes": nodes,
                             "start": start})
        return {"call": f"{POUCH_FILE}:{entry}", "next": nxt}
    return {"call": f"{POUCH_FILE}:{POUCH_ROUTINE}", "params": {"ActorName": target["actor"]}, "next": nxt}


# The get scenes are resident events (Event/ResidentEventList, loaded at boot and kept). The hook's calls have to be in
# Dm_SY_Get's entry-point sub-flow list, because that's where the game binds a scene's actors from. Without them the
# disguised ice trap froze (null handler) and then crashed (garbage handler). tools/evfl_build.py sync_sub_flows fixes
# that for every scene file, and I confirmed it in game.
# Standing, an item is handed over with the hold-up routine every other check uses (Dm_SY_GetInEvent, fanfare and
# Link raises it). The window-only give we had before as a precaution came out as "no fanfare, no animation".
# In the air or water (Dm_SY_Get_WithoutPlayer's path) the give stays in Dm_SY_Get or GetPouchContent. An item goes
# through GetPouchContent's add-and-window routine (the vanilla in-water give), a dungeon item as its save-data steps
# plus the get window, and the bean pack as the window plus nine more beans. A trap is always a local copy of its
# steps, since they only use Player_Event, GameSystemActor, GameDataActor, PouchSystemActor and UISystemActor, and
# Dm_SY_Get has all of those.
RESIDENT_HOST = "Dm_SY_Get"


def _resident_trap(o, call):
    """The Dm_SY_Get entry with a local copy of trap scene `call` (Dm_SY_GetInEvent:Rando_IceTrap or
    :Rando_Trap_<Kind>). It only gets added once."""
    from parity import _chests_scenes as scenes
    entry = call.split(":", 1)[1]
    key = f"{RESIDENT_HOST}:{entry}"
    if key not in o._hosts:
        o._hosts.add(key)
        if entry == scenes.HOST_ENTRY:
            _, nodes, start = scenes.freeze_graph()
        elif entry.startswith("Rando_Trap_"):
            _, nodes, start = scenes.trap_graph(entry[len("Rando_Trap_"):].lower())
        else:
            raise ValueError(f"get-scene hook: no resident copy of trap scene {call}")
        o.events.append({"file": RESIDENT_HOST, "flowchart": RESIDENT_HOST, "add_graph": entry, "nodes": nodes,
                         "start": start})
    return entry


def _resident_give(o, n, k, t, item, nxt, hold=False):
    """Nodes in a Dm_SY_Get graph that hand over target `t` (OoTR item `item`). Returns the first node's label.
    With hold=True (standing) it's the hold-up routine, so o.give or the target's own call (a dungeon item's credit
    entry). Otherwise it gives without leaving the files a resident scene used (see RESIDENT_HOST).
    A {"nothing"} target adds no node and the label returned is `nxt` itself, so the scene goes straight on with the
    pickup hidden, its death requested and no item. That's OoTR's "Nothing" with remake_empty_object_contents
    "nothing" (parity/drops.py _scene_target)."""
    from . import _songs_trade_child as child
    if t.get("nothing"):
        return nxt
    first = f"{k}_give"
    call = t.get("call", "")
    if t.get("ice_trap"):
        n[first] = {"call": ":" + _resident_trap(o, call or ops.ICE_CALL), "next": nxt}
    elif hold and call != child.BEAN_PACK_CALL:
        n[first] = {"call": call, "next": nxt} if call else o.give(t, nxt)
    elif call == child.BEAN_PACK_CALL:
        n[first] = {"call": f"{POUCH_FILE}:{POUCH_ROUTINE}", "params": {"ActorName": "Item_MagicBean"},
                    "next": f"{k}_beans"}
        n[f"{k}_beans"] = {"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
                           "params": {"Actor": "Item_MagicBean", "Num": 9, "IsEquipDIrect": False,
                                      "IsSetMessageTargetActorName": False, "IsGetEvent": False}, "next": nxt}
    elif call.split(":")[-1].startswith("Rando_DI_Call_"):
        from parity import dungeons
        model, credit = dungeons.resident_give(item, getattr(o, "world", None))
        if model is None:  # a Triforce Piece has no stand-in window, its credit steps show its message
            for i, st in enumerate(credit):
                n[first if i == 0 else f"{k}_credit{i}"] = dict(st, next=f"{k}_credit{i + 1}" if i + 1 < len(credit)
                                                                else nxt)
            return first
        # the window names the dungeon in OoTR's words (dungeons.window_step, a GetPouchContent call)
        window = dungeons.window_step(item, getattr(o, "world", None)) or \
            {"call": f"{POUCH_FILE}:DisplayGetByActorName", "params": {"ActorName": model}}
        n[first] = dict(window, next=f"{k}_credit0" if credit else f"{k}_pickup")
        for i, st in enumerate(credit):
            n[f"{k}_credit{i}"] = dict(st, next=f"{k}_credit{i + 1}" if i + 1 < len(credit) else f"{k}_pickup")
        n[f"{k}_pickup"] = {"actor": "UISystemActor", "action": "EventTriggerRequestOpenPickUpWindow",
                            "params": {"ActorName": model}, "next": nxt}
    elif t.get("heal"):  # a heart or fairy in the air or water gets its window and the heal (dungeons.heal_steps)
        from parity import dungeons
        steps = [{"call": f"{POUCH_FILE}:DisplayGetByActorName", "params": {"ActorName": t["model"]}}]
        steps += dungeons.heal_steps(t["model"], wait_actor="EventSystemActor")
        for i, st in enumerate(steps):
            n[first if i == 0 else f"{k}_heal{i}"] = dict(st, next=f"{k}_heal{i + 1}" if i + 1 < len(steps) else nxt)
    elif call.split(":")[-1].startswith(("Rando_Soul_", "Rando_SkeletonKey")):
        # A soul or the Skeleton Key in the air or water gets a copy of its give entry's steps
        # (extras_souls.resident_steps). That's the flag or key rows, then its message through GetPouchContent.
        from parity import extras_souls
        steps = extras_souls.resident_steps(item, getattr(o, "world", None))
        for i, st in enumerate(steps):
            n[first if i == 0 else f"{k}_soul{i}"] = dict(st, next=f"{k}_soul{i + 1}" if i + 1 < len(steps) else nxt)
    elif call:
        raise ValueError(f"get-scene hook: {item}'s give {call} is outside the files a resident scene can call")
    else:
        n[first] = _window_give(o, t, nxt)
    return first


QUIET_ADD = {"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent"}


def _quiet_give(n, k, t, nxt):
    """Nodes that hand over junk target `t` the way its own pickup is taken (drops.QUIET_JUNK: rupees, recovery hearts,
    ammo). No hold-up and no window, only GetPouchContent Event0's pouch add (one of the bundle actor, no get event, no
    message target). Ammo whose container you don't own adds nothing or a Blue Rupee (remake_ammo_without_container),
    whichever parity/_ammo.py's guard on Event0 decides. That guard is the same EventQueryIsExistInPouch on every tier
    of the container. Returns the first node's label."""
    from . import _ammo
    import progressive
    if t.get("heal"):  # a recovery heart taken like its own pickup, the game's heal (dungeons.heal_steps), no hold-up
        from parity import dungeons
        steps = dungeons.heal_steps(t["model"], wait_actor="EventSystemActor")
        for i, st in enumerate(steps):
            n[f"{k}_add" if i == 0 else f"{k}_heal{i}"] = dict(st, next=f"{k}_heal{i + 1}" if i + 1 < len(steps)
                                                              else nxt)
        return f"{k}_add"
    actor = t.get("actor")
    if not actor:
        raise ValueError(f"get-scene hook: quiet give needs an actor target, not {t}")
    add = f"{k}_add"
    n[add] = dict(QUIET_ADD, params={"Actor": actor, "Num": 1, "IsEquipDIrect": False,
                                     "IsSetMessageTargetActorName": False, "IsGetEvent": False}, next=nxt)
    group = next((g for g, actors in _ammo.GROUPS.items() if actor in actors), None)
    if group is None:
        return add
    owners = list(dict.fromkeys(o_ for tier in progressive.PROGRESSIVE[group]["tiers"]
                                for o_ in progressive.owned_by(tier)))
    rupee = _ammo.rupee_node(nxt)  # remake_ammo_without_container "blue_rupee" gives a Blue Rupee instead, like OoTR
    if rupee:
        n[f"{k}_rupee"] = rupee
    for j, own in enumerate(owners):
        n[f"{k}_own{j}"] = {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                            "params": {"Actor": own, "Num": 1},
                            "cases": {_ammo.YES: add, _ammo.NO: f"{k}_own{j + 1}" if j + 1 < len(owners)
                                      else (f"{k}_rupee" if rupee else nxt)}}
    return f"{k}_own0"


def _branch(o, n, name, k, flag, target, item, hide, death, hold=False):
    """Nodes for one pickup in a Dm_SY_Get graph, since that file has the GameDataActor the flag needs."""
    n[f"{k}_q"] = ops.flag_query(flag, f"{k}_gone", f"{k}_hide")
    n[f"{k}_gone"] = {"copy": hide, "next": None}
    n[f"{k}_hide"] = {"copy": hide, "next": f"{k}_set"}
    import drops as drop_tools  # tools/rando/drops.py
    done = f"{k}_challenge" if name == LH_SUN else None
    quiet = item in drop_tools.QUIET_JUNK and (target.get("actor") or target.get("heal"))
    # Junk goes through _quiet_give so there's no hold-up or window, everything else through _resident_give.
    # A {"nothing"} target from world_plan_ops goes straight on and gives nothing.
    after = done if target.get("nothing") else _quiet_give(n, k, target, done) if quiet else f"{k}_give"
    if death:
        n[f"{k}_set"] = ops.flag_set(flag, f"{k}_death")
        n[f"{k}_death"] = {"copy": death, "next": after}
    else:
        n[f"{k}_set"] = ops.flag_set(flag, after)
    if not quiet and not target.get("nothing"):
        _resident_give(o, n, k, target, item, done, hold)
    if name == LH_SUN:  # the Fire Arrow challenge completes like the arrow's pickup does
        n[f"{k}_challenge"] = {"call": "SubEvent_GetFireArrow:GetFireArrow", "next": None}


def _heart_branch(o, n, p, hide, death, hold=False):
    """Nodes for a heart spot of the drops plugin (drops.get_scene_pickups). They hide the heart, give the spot's item
    (_resident_give), then request the heart's death (DeathReason 10). That's the step the vanilla scene runs after its
    give, and the PickedUp death saves the placement's flag so the heart never comes back. We don't need a flag of our
    own, the heart is gone once taken like in vanilla."""
    k, t = f"heart{p['tag']}", p["target"]
    if p.get("disguise"):  # the disguised trap: hide it, run the shared freeze, then the PickedUp death
        # The freeze is a local copy. Link flinches, his frozen sound plays, a rumble, then it creates the ice-trap
        # attacker (drops.ice_sensor_ops).
        n[f"{k}_hide"] = {"copy": hide, "next": f"{k}_shown"}
        n[f"{k}_shown"] = {"call": ":" + _resident_trap(o, ops.ICE_CALL), "next": f"{k}_death"}
        n[f"{k}_death"] = {"copy": death, "next": None}
        return f"{k}_hide"
    if t.get("ice_trap") and "call" not in t and getattr(o, "world", None) is not None:
        from parity import chests  # the trap kind this heart spot's Ice Trap drew (remake_trap_weights)
        t = dict(t, call=chests.trap_call(o.world, p["location"]))
    if p.get("flag"):  # a scene drop from an object with no save flag of its own (drops.py "flagless drops")
        # Its borrowed flag says the item was given, so a carrier dropped again after that gives nothing.
        n[f"{k}_q"] = ops.flag_query(p["flag"], f"{k}_gone", f"{k}_hide")
        n[f"{k}_gone"] = {"copy": hide, "next": f"{k}_gonedeath"}
        n[f"{k}_gonedeath"] = {"copy": death, "next": None}
        n[f"{k}_hide"] = {"copy": hide, "next": f"{k}_visit" if p.get("visit") is not None else f"{k}_set"}
        if p.get("visit") is not None:  # this visit's bit first so the spot's vanilla twin waits for the next map
            n[f"{k}_visit"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",  # drops.py VISIT
                               "params": {"GameDataName": "RandoVisit", "Value": True, "Index": p["visit"]},
                               "next": f"{k}_set"}
        n[f"{k}_set"] = ops.flag_set(p["flag"], _give(o, n, k, t, p, hold))
        n[f"{k}_death"] = {"copy": death, "next": None}
        return f"{k}_q"
    n[f"{k}_hide"] = {"copy": hide, "next": _give(o, n, k, t, p, hold)}
    n[f"{k}_death"] = {"copy": death, "next": None}
    return f"{k}_hide"


def _give(o, n, k, t, p, hold):
    """A heart spot's or scene drop's give. Junk a carrier brings (p["quiet"], drops.QUIET_JUNK) is taken like its own
    pickup (_quiet_give), anything else goes through _resident_give (the hold-up standing, the window in the air or
    water)."""
    if p.get("quiet") and (t.get("actor") or t.get("heal")):  # a recovery heart gets the game's heal, quietly
        return _quiet_give(n, k, t, f"{k}_death")
    return _resident_give(o, n, k, t, p["item"], f"{k}_death", hold)


def world_plan_ops(o, items, targets, flags, data, pickups=()):
    """Adds the get-scene hook for the lake pickups and the heart spots to `o`.
    items: {location: OoTR item}, targets: {location: songs_trade._target(item)}, flags: {location: save flag}.
    data: songs_trade_data.json "lake", the hooked steps (checked by _songs_trade_build.py).
    pickups: the drops plugin's heart spots given through the same hook, [{"location", "tag", "item", "target"}] from
    drops.get_scene_pickups. The pickup's event AI answers each spot's tag (>= 5), and each tag gets its own branch in
    both scenes. With no pickups the hook is exactly the lake one."""
    shuffled = [n for n in LOCATIONS if items.get(n) is not None and items[n] != VANILLA[n]]
    pickups = sorted(pickups, key=lambda p: p["tag"])
    if not shuffled and not pickups:
        return
    # drops._scene_target decides what OoTR's "Nothing" does. With remake_empty_object_contents "nothing" we hide the
    # pickup and set its flag without giving an item. Otherwise the usual songs/trade fallback gives a green rupee,
    # which is what the letter spot used to do.
    import sys
    dr = sys.modules.get("parity.drops")
    if dr is not None and hasattr(dr, "_scene_target") and (dr._scene_target("Nothing") or {}).get("nothing"):
        targets = {loc: {"nothing": True} if items.get(loc) == "Nothing" else t for loc, t in targets.items()}
    get, wp = "Dm_SY_Get", "Dm_SY_Get_WithoutPlayer"
    hide, death = data["scenes"][get]["hide"]["event"], data["scenes"][get]["death"]["event"]
    # Standing (Dm_SY_Get, after the player's event start), the hook and both branches go in place.
    step = data["scenes"][get]["hook"]
    n = {"tag": {"actor": "PouchContentGuestPerformer", "query": "EventQueryCheckTagOnPouchActor",
                 "cases": {t: ops.at(step["event"]) for t in range(5)}}}
    for name in shuffled:
        k = "letter" if name == LH_LETTER else "arrow"
        n["tag"]["cases"][TAG[name]] = f"{k}_q"
        _branch(o, n, name, k, flags[name], targets[name], items[name], hide, death, hold=True)
    for p in pickups:
        n["tag"]["cases"][p["tag"]] = _heart_branch(o, n, p, hide, death, hold=True)
    o.replace(get, get, step, "RandoST_LakePickups", n, "tag")
    # In the air or water. Dm_SY_Get_WithoutPlayer has no GameDataActor, so its first step asks the tag and calls a
    # Dm_SY_Get entry that checks the flag, hides the pickup and gives the item with the get window.
    step = data["scenes"][wp]["hook"]
    n = {"tag": {"actor": "PouchContentGuestPerformer", "query": "EventQueryCheckTagOnPouchActor",
                 "cases": {t: ops.at(step["event"]) for t in range(5)}}}
    for name in shuffled:
        k = "letter" if name == LH_LETTER else "arrow"
        entry = f"RandoST_LakeWP_{k}"
        sub = {}
        _branch(o, sub, name, k, flags[name], targets[name], items[name], hide, None)
        o.events.append({"file": get, "flowchart": get, "add_graph": entry, "nodes": sub, "start": f"{k}_q"})
        n["tag"]["cases"][TAG[name]] = f"{k}_call"
        n[f"{k}_call"] = {"call": f"{get}:{entry}", "next": None}
    for p in pickups:  # a heart spot in the air or water works the same, with the get window and the death request
        k, entry, sub = f"heart{p['tag']}", f"RandoST_HeartWP_{p['tag']}", {}
        start = _heart_branch(o, sub, p, hide, death)
        o.events.append({"file": get, "flowchart": get, "add_graph": entry, "nodes": sub, "start": start})
        n["tag"]["cases"][p["tag"]] = f"{k}_call"
        n[f"{k}_call"] = {"call": f"{get}:{entry}", "next": None}
    o.replace(wp, wp, step, "RandoST_LakePickups", n, "tag")
    if LH_LETTER in shuffled:
        o.placements.append(dict(LETTER_PLACEMENT, set={"Presence": {"FlagName": flags[LH_LETTER],
                                                                     "IsCheckLazy": False, "IsNegation": True}},
                                 note=f"{LH_LETTER}: the bottle is gone once its item is given"))
    for name in shuffled:
        o.notes.append(f"{name}: {items[name]} (the pickup gives it once)")
    for p in pickups:
        o.notes.append(f"{p['location']}: {p['item']} (the heart's get scene gives it, tag {p['tag']})")
