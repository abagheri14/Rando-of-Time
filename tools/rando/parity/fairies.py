"""Parity plugin for Ship of Harkinian's fairy shuffles (Shuffle Fountain / Stone / Bean / Song / Butterfly Fairies).

tools/rando/fairies.py builds data/rando/fairy_map.json and data/rando/logic/fairies.json from the game files.
The settings are remake ones, On/Off and off by default
(SoH's names work through config/setting_aliases.json):
  remake_shuffle_stone_fairies     80 locations, every talkable Gossip Stone's fairy (Zelda's Lullaby, Epona's Song,
                                   Sun's Song where OoTR counts it, Song of Time) and its big fairy (Song of Storms).
                                   The fairy still comes and heals, and the stone gives its item once. Each one has
                                   a borrowed saved flag, plus one scratch flag for which song was played.
  remake_shuffle_fountain_fairies  47 locations. The Desert Colossus oasis has 7, given by its once-only Song of
                                   Storms cutscene. The HF, SFM and ZR fairy fountain grottos and the Graveyard
                                   Shield Grave's fountain have 8 each, given on the grotto's or grave's first
                                   entry through a reused scene ID (the grave's keep SoH's rule, break the wall).
                                   Ganon's Castle's fountain room has 8 (SoH's Scrubs Fairies), given on entering
                                   the fountain through a copied area and requester running a vanilla area-event
                                   module, and a reused scene ID (tools/rando/fairies.py ROOMS).
  remake_shuffle_butterfly_fairies 15 locations, built by the drops plugin (its CATEGORY "butterfly"). A child's Deku
                                   Stick turns the butterfly into the seed's item, which it drops until taken.
  remake_shuffle_song_fairies      9 locations, the Fairy Note spots (Sun's Song or Song of Storms by a Note). The
                                   item comes once, before the fairy leaves (a borrowed flag each). We tell the spot
                                   by the fairy's own placement name with a "near the fairy named..." question,
                                   the same way vanilla asks.
  remake_shuffle_bean_fairies      30 locations, 3 per bean plant that calls a fairy (Song of Storms over a child's
                                   sprout), given together once (a borrowed flag per plant). We tell the soil by its
                                   placement name and the soil type by a scratch flag set at the flow's two entries.
A location whose setting is off holds a Recovery Heart, locked and with nothing patched. With it on, it takes
anything the get scene can give, which is the songs_trade plugin's give targets: progressive tiers, dungeon items
through the dungeons plugin's credit entries and ice traps through the chests plugin's freeze. The exceptions are
OoTR's "Nothing", shop items and, with remake_avoid_vanilla_spots, a Recovery Heart (that's what a fairy does
anyway). The give steps are built with songs_trade's Ops (its world_plan calls gift_ops), so their host entries
are shared with every other scene check.
"""
import sys

import fairies as data  # tools/rando/fairies.py

OWNS = {}
REMAKE_SETTINGS = {key: (False, True) for key in data.SETTINGS.values()}
REMAKE_DEFAULTS = {key: False for key in data.SETTINGS.values()}
STAND_IN = "Recovery Heart"
NEEDS = ("songs_trade", "drops", "chests")  # give steps, the scene-target table, the ice-trap freeze
SCRATCH = 1  # the stones' "which song" flag
_kept = {}    # id(world) -> {location}
_plan = {}    # id(world) -> {"gifts": [...], "flags": {location: flag}, "scratch": flag}
_avoid = {"on": True}


def _remake(settings, key):
    return (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS.get(key, False))


def _on(settings, kind):
    return _remake(settings, data.SETTINGS[kind]) is True


def _spots():
    return data.fairy_map()["spots"]


def check_settings(settings):
    import generate  # tools/rando/generate.py
    problems = []
    for kind, key in data.SETTINGS.items():
        v = _remake(settings, key)
        if v not in (False, True):
            problems.append(f"{key} = {v!r}: fairies can make False, True")
        elif v and kind not in data.BUILT:
            problems.append(f"{key}: not built yet")
    if any(_on(settings, k) for k in data.BUILT):
        missing = [p for p in NEEDS if p not in generate.enabled_plugins()]
        if missing:
            problems.append(f"fairy shuffles give through the {', '.join(missing)} plugin(s): enable them")
    return problems


def untested(settings):
    out = []
    if _on(settings, "stone"):
        out.append("fairies: Gossip Stone fairies (the stone's own number query, unused in vanilla; the give after "
                   "the fairy's heal)")
    if _on(settings, "fountain"):
        out.append("fairies: the Colossus oasis gives after its cutscene; the HF/SFM/ZR fairy grottos and the "
                   "Graveyard Shield Grave give on the first entry (reused scene IDs); Ganon's Castle's fountain "
                   "gives on entering it (a new logic group of a copied area and requester, first in game)")
    return out


def keep_locations(world, settings):
    from Item import ItemFactory
    from ItemPool import get_junk_item
    import no_vanilla  # tools/rando/no_vanilla.py (remake_avoid_vanilla_spots, off by default)
    _avoid["on"] = no_vanilla.enabled(settings)
    out = set()
    for name, s in sorted(_spots().items()):
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.item is not None or loc.locked:
            continue
        if s["kind"] not in data.BUILT or not _on(settings, s["kind"]):
            world.push_item(loc, ItemFactory(STAND_IN, world))
            loc.locked = True
            continue
        world.itempool.append(ItemFactory(get_junk_item()[0], world))  # OoTR's pool has nothing for it
        out.add(name)
    _kept[id(world)] = out
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "CALL_LOCATIONS"):  # a dungeon item here means the give step calls its credit
        dg.CALL_LOCATIONS.update(out)  # entry (the drops plugin's _scene_target asks call_target in world_plan)
    return out


def _target(name, location=None):
    dr = sys.modules.get("parity.drops")
    return dr._scene_target(name, location) if dr is not None else None


class _Like:
    """A junk OoTR item for a rule check (only its name, type and flags are read)."""

    def __init__(self, name):
        self.name, self.type, self.advancement, self.priority = name, "Item", False, False


def _allowed(item, spot=None):
    name = item.name
    if name == "Nothing":  # OoTR's Nothing becomes an Ice Trap or junk after the fill (drops._named_nothing)
        dr = sys.modules.get("parity.drops")
        return bool(dr is not None and dr.nothing_converted()) and (
            _allowed(_Like("Ice Trap"), spot) or _allowed(_Like("Rupees (5)"), spot))
    if getattr(item, "type", None) == "Shop":  # (Fairy Drop has its own give entry,
        return False  # dungeons.heal_graph through songs_trade._target)
    if _avoid["on"] and name == STAND_IN:  # a heal is what the fairy does anyway, so it reads as the vanilla spot
        return False
    if spot is not None and spot.get("confidence") not in ("high", "medium") and (getattr(item, "advancement", False) or
                                                                 getattr(item, "priority", False)):
        return False  # progression only where the spot's region is certain (as the drops plugin's _major_ok)
    return _target(name) is not None


def before_fill(world, settings):
    for name in sorted(_kept.get(id(world), ())):
        loc = world.get_location(name)
        prev = loc.item_rule
        spot = _spots()[name]
        loc.item_rule = (lambda location, item, prev=prev, spot=spot: _allowed(item, spot) and prev(location, item))


def after_fill(world, settings):
    """OoTR's last junk pass ignores item rules, so junk it left that the scene can't give gets swapped with junk that
    can go both here and there."""
    kept = _kept.get(id(world), set())
    bad = [world.get_location(n) for n in sorted(kept) if not _allowed(world.get_location(n).item, _spots()[n])]
    if not bad:
        return
    others = [loc for loc in world.get_locations() if loc.name not in kept and loc.item is not None and not loc.locked
              and not loc.item.advancement and not loc.item.priority and _allowed(loc.item)]
    for loc in bad:
        swap = next((o for o in others if o.item_rule(o, loc.item)), None)
        if swap is None:
            raise ValueError(f"{loc.name}: {loc.item.name} can't be given there and no junk can take its place")
        others.remove(swap)
        a, b = loc.item, swap.item
        loc.item, swap.item = b, a
        b.location, a.location = loc, swap


def claimed_rows(world):
    """Scene IDs this seed's fairy grottos and grave take (config/scene_rows.json). parity/chests.py budgets the
    rows."""
    kept = _kept.get(id(world), set())
    groups = {_spots()[n].get("group") for n in kept}
    m = data.fairy_map()
    return [g["row"] for region, g in sorted(m["grottos"].items()) + sorted((m.get("rooms") or {}).items())
            if region in groups]


def _give_key(target):
    """What a give of `target` shows in the built flow, its actor or the entry it calls (tools/rando/fairies.py
    verify)."""
    if "actor" in target:
        return target["actor"]
    if "progressive" in target:
        return "".join(w for w in target["progressive"].title().split() if w.isalnum())
    if target.get("ice_trap"):  # the trap kind its location drew, Rando_IceTrap or Rando_Trap_<Kind>
        return (target.get("call") or ":Rando_IceTrap").split(":")[-1]
    return target["call"].split(":")[-1]


def world_plan(settings, world):
    import free_flags  # tools/rando/free_flags.py
    kept = _kept.get(id(world), set())
    if not kept:
        return {}
    spots = _spots()
    gifts = []
    for name in sorted(kept):
        item = world.get_location(name).item
        target = _target(item.name, name)
        if target is None:
            raise ValueError(f"{name}: {item.name} can't be given by the get scene (the item rule should have kept "
                             f"it out)")
        gifts.append({"location": name, "item": item.name, "target": target, "spot": spots[name]})
    stones = [g for g in gifts if g["spot"]["kind"] == "stone"]
    notes = [g for g in gifts if g["spot"]["kind"] == "song"]
    soils = sorted({g["spot"]["group"] for g in gifts if g["spot"]["kind"] == "bean"})
    # We take flags from the back of the pool (tools/rando/free_flags.py), the drops plugin takes from the
    # front. Each stone, note and bean plant gets one flag, and a plant gives all three items together. The two
    # scratch flags track which song a stone heard and which soil type started the bean flow.
    need = len(stones) + (SCRATCH if stones else 0) + len(notes) + len(soils) + (1 if soils else 0)
    dr = sys.modules.get("parity.drops")
    used = set(dr.borrowed_flags(world)) if dr is not None and hasattr(dr, "borrowed_flags") else set()
    # free_flags.mint covers any overflow. All option combinations generate.
    take = iter(free_flags.take(need, used, reverse=True))
    scratch = next(take) if stones else None
    flags = {g["location"]: next(take) for g in stones}
    flags.update({g["location"]: next(take) for g in notes})
    bean_scratch = next(take) if soils else None
    soil_flag = {grp: next(take) for grp in soils}
    _plan[id(world)] = {"gifts": gifts, "flags": flags, "scratch": scratch, "bean_scratch": bean_scratch,
                        "soil_flag": soil_flag}
    rec = {"stones": {g["location"]: {"value": g["spot"]["value"], "big": g["spot"]["big"],
                                      "flag": flags[g["location"]], "give": _give_key(g["target"]),
                                      "item": g["item"]} for g in stones},
           "scratch": scratch,
           "colossus": [{"location": g["location"], "index": g["spot"]["index"], "give": _give_key(g["target"]),
                         "item": g["item"]} for g in gifts if g["spot"].get("group") == "colossus"],
           "grottos": {},
           "notes": {g["location"]: {"instance": g["spot"]["instance"], "flag": flags[g["location"]],
                                     "give": _give_key(g["target"]), "item": g["item"],
                                     "places": g["spot"]["places"]} for g in notes},
           "beans": {}, "bean_scratch": bean_scratch}
    for g in gifts:
        if g["spot"]["kind"] == "bean":
            b = rec["beans"].setdefault(g["spot"]["group"].split(":", 1)[1], {
                "instance": g["spot"]["instance"], "flag": soil_flag[g["spot"]["group"]], "gives": [],
                "places": g["spot"]["places"]})
            b["gives"].append({"location": g["location"], "index": g["spot"]["index"], "give": _give_key(g["target"]),
                               "item": g["item"]})
    rooms = data.fairy_map().get("rooms") or {}
    for g in gifts:
        grp = g["spot"].get("group")
        if g["spot"]["kind"] == "fountain" and grp != "colossus":
            sec = rec.setdefault("rooms", {}) if grp in rooms else rec["grottos"]  # (no "rooms" key without one)
            sec.setdefault(grp, []).append({"location": g["location"], "index": g["spot"]["index"],
                                            "give": _give_key(g["target"]), "item": g["item"]})
    lines = [f"{g['location']}: {g['item']}" + (f" (once: {flags[g['location']]})" if g["location"] in flags else "")
             for g in gifts]
    out = {"_fairies": rec, "_notes_fairies": lines}
    out.update(_room_triggers(sorted(rec.get("rooms") or {}), rooms))
    return out


def _room_triggers(regions, rooms):
    """The level edits that make a fountain room without an event give its items (tools/rando/fairies.py ROOMS). It's
    a copy of the fountain's music Area, gone the moment the room's once-flag is set (lazy Presence), and a copy of a
    requester asking for the room's scene row. A vanilla area-event module runs them as their own logic group
    (make_patch "groups"). The scene steps themselves come with the other gives (gift_ops)."""
    placements, groups = [], []
    for region in regions:
        g = rooms[region]
        ar, rq, gr = g["area"], g["requester"], g["group"]
        placements.append({"file": g["file"], "hash": ar["source"], "twin": ar["twin"], "join_groups": False,
                           "set": {"Presence": dict(g["presence"])}})
        placements.append({"file": g["file"], "hash": rq["source"], "twin": rq["twin"], "join_groups": False,
                           "remove": ["Links"], "set": {"Dynamic.RequestEventName": g["row"]}})
        groups.append({"file": g["file"], "logic": gr["logic"], "hash": gr["hash"], "spawn_group": True,
                       "references": [{"id": gr["area_id"], "reference": ar["twin"]},
                                      {"id": gr["event_id"], "reference": rq["twin"]}]})
    return {"placements": placements, "groups": groups} if placements else {}


def get_gifts(world):
    return _plan.get(id(world))


def gift_ops(o, world):
    """Adds this seed's fairy gives to songs_trade's Ops `o`. Its world_plan calls this, after ours."""
    from . import _drops_gifts as dg
    from . import _songs_trade_ops as st
    p = _plan.get(id(world))
    if not p:
        return
    m = data.fairy_map()
    by = {}
    for g in p["gifts"]:
        by.setdefault(g["spot"]["kind"] if g["spot"]["kind"] == "stone" else g["spot"]["group"], []).append(g)
    # song spots are group "notes", bean plants "bean:<soil hash>", the oasis "colossus" and grottos their region
    if by.get("stone"):
        s = m["stones"]
        f, scratch = s["flow"], p["scratch"]
        resume = f"@{s['resume']}"
        song = {"calm": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                         "params": {"GameDataName": scratch, "Value": False, "Index": -1}, "next": f"@{s['melody_next']}"},
                "storm": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                          "params": {"GameDataName": scratch, "Value": True, "Index": -1}, "next": f"@{s['melody_next']}"}}
        o.events.append({"file": f, "flowchart": f, "add_graph": "RandoFairy_Song", "start": "calm", "nodes": song})
        for pos in s["calm_cases"]:
            o.events.append({"file": f, "flowchart": f, "event": s["switch"], "case": pos, "next": "RandoFairy_Song_calm"})
        for pos in s["storm_cases"]:
            o.events.append({"file": f, "flowchart": f, "event": s["switch"], "case": pos, "next": "RandoFairy_Song_storm"})
        per = {}
        for g in by["stone"]:
            per.setdefault(g["spot"]["value"], {})["big" if g["spot"]["big"] else "normal"] = g
        nodes = {"q": {"actor": s["actor"], "query": s["query"], "params": {},
                       "cases": {v: (f"s{v}" if v in per else resume) for v in range(41)}}}
        for v, pair in sorted(per.items()):
            branch = {}
            for kind in ("big", "normal"):
                g = pair.get(kind)
                if g is None:
                    branch[kind] = resume
                    continue
                k = f"{kind[0]}{v}"
                flag = p["flags"][g["location"]]
                nodes[k] = st.flag_query(flag, resume, f"{k}s")
                nodes[f"{k}s"] = st.flag_set(flag, f"{k}g")
                nodes[f"{k}g"] = o.give(g["target"], resume)
                branch[kind] = k
            nodes[f"s{v}"] = st.flag_query(scratch, branch["big"], branch["normal"])
        o.events.append({"file": f, "flowchart": f, "add_graph": "RandoFairy_Stones", "start": "q", "nodes": nodes})
        o.events.append({"file": f, "flowchart": f, "event": s["after"], "next": "RandoFairy_Stones_q"})
        o.notes.append(f"Gossip Stone fairies: {len(by['stone'])} items after the fairy's heal ({f}:RandoFairy_Stones; "
                       f"which song: {scratch})")
    if by.get("colossus"):
        c = m["colossus"]
        gs = sorted(by["colossus"], key=lambda g: g["spot"]["index"])
        nodes = {}
        for i, g in enumerate(gs):
            nxt = f"g{i + 1}" if i + 1 < len(gs) else None
            nodes[f"g{i}"] = o.give(g["target"], nxt) if i == 0 else dg._window(o, g["target"], nxt)
        o.events.append({"file": c["flow"], "flowchart": c["flow"], "add_graph": "RandoFairy_Colossus", "start": "g0",
                         "nodes": nodes})
        o.events.append({"file": c["flow"], "flowchart": c["flow"], "event": c["after"], "next": "RandoFairy_Colossus_g0"})
        o.notes.append(f"Colossus oasis: {len(gs)} items after the Song of Storms cutscene ({c['flow']}:RandoFairy_Colossus)")
    for region, g in sorted(m["grottos"].items()):
        gs = sorted(by.get(region, []), key=lambda x: x["spot"]["index"])
        if not gs:
            continue
        sc = g["scene"]
        nodes = {"entry": {"call": f":{sc['vanilla']}", "next": "q"},
                 "q": st.flag_query(g["once"], None, "set"),
                 "set": st.flag_set(g["once"], "g0")}
        for i, x in enumerate(gs):
            nxt = f"g{i + 1}" if i + 1 < len(gs) else None
            nodes[f"g{i}"] = o.give(x["target"], nxt) if i == 0 else dg._window(o, x["target"], nxt)
        o.events.append({"file": sc["file"], "flowchart": sc["file"], "add_graph": sc["entry"], "start": "entry",
                         "nodes": nodes})
        o.byml.append({"file": data.EVENT_SETTING, "replace_row": {"row": g["row"], "copy_of": g["copy_of"],
                                                                 "set": {"EntryPointName": sc["entry"]}}})
        for t in g["triggers"]:
            o.placements.append({"file": t["file"], "hash": t["hash"], "set": {"Dynamic.RequestEventName": g["row"]}})
        o.notes.append(f"{region}: {len(gs)} items on the first entry (scene ID {g['row']} -> {sc['file']}:{sc['entry']}; "
                       f"once: {g['once']})")
    for region, g in sorted((m.get("rooms") or {}).items()):  # fountain rooms without an event (fairies.py ROOMS)
        gs = sorted(by.get(region, []), key=lambda x: x["spot"]["index"])
        if not gs:
            continue
        sc, ar, rq, gr = g["scene"], g["area"], g["requester"], g["group"]  # the trigger is _room_triggers
        nodes = {"q": st.flag_query(g["once"], None, "set"), "set": st.flag_set(g["once"], "g0")}
        for i, x in enumerate(gs):
            nxt = f"g{i + 1}" if i + 1 < len(gs) else None
            nodes[f"g{i}"] = o.give(x["target"], nxt) if i == 0 else dg._window(o, x["target"], nxt)
        o.events.append({"file": sc["file"], "flowchart": sc["file"], "add_graph": sc["entry"], "start": "q",
                         "nodes": nodes})
        o.byml.append({"file": data.EVENT_SETTING, "replace_row": {"row": g["row"], "copy_of": g["copy_of"],
                                                                 "set": {"EntryPointName": sc["entry"]}}})
        o.notes.append(f"{region}: {len(gs)} items on entering the fountain (area {ar['twin']} + requester "
                       f"{rq['twin']} in logic group {gr['hash']}; scene ID {g['row']} -> {sc['file']}:{sc['entry']}; "
                       f"once: {g['once']})")
    if by.get("notes"):  # Fairy Note spots, told by the fairy's spot name before it leaves (both tails)
        nt = m["notes"]
        f = nt["flow"]
        gs = sorted(by["notes"], key=lambda g: g["spot"]["index"])
        for g in gs:
            for pl in g["spot"]["places"]:
                o.placements.append({"file": pl["file"], "hash": pl["hash"], "set": {"Name": g["spot"]["instance"]}})
        for t, (wait, leave) in enumerate(nt["tails"]):
            resume, nodes = f"@{leave}", {}
            for i, g in enumerate(gs):
                nxt = f"q{i + 1}" if i + 1 < len(gs) else resume
                flag = p["flags"][g["location"]]
                nodes[f"q{i}"] = data._distance(nt["actor"], g["spot"]["instance"], f"c{i}", nxt)
                nodes[f"c{i}"] = st.flag_query(flag, resume, f"c{i}s")
                nodes[f"c{i}s"] = st.flag_set(flag, f"c{i}g")
                nodes[f"c{i}g"] = o.give(g["target"], resume)
            graph = f"RandoFairy_Notes{t}"
            o.events.append({"file": f, "flowchart": f, "add_graph": graph, "start": "q0", "nodes": nodes})
            o.events.append({"file": f, "flowchart": f, "event": wait, "next": f"{graph}_q0"})
        o.notes.append(f"Fairy Note fairies: {len(gs)} items before the fairy leaves ({f}:RandoFairy_Notes0/1)")
    soils = sorted((k.split(":", 1)[1], v) for k, v in by.items() if k.startswith("bean:"))
    if soils:  # bean plants by the soil's name, and a scratch flag at each entry says which soil type started it
        bn = m["beans"]
        f, scratch = bn["flow"], p["bean_scratch"]
        spec = {x["soil"]: x for x in bn["spots"]}
        entry = {}
        for k, (ep, actor) in enumerate(sorted(bn["entries"].items())):
            entry[f"e{k}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                              "params": {"GameDataName": scratch, "Value": actor == "Obj_SmallFarm_A_02", "Index": -1},
                              "next": f"@{bn['entry_steps'][ep]}"}
        o.events.append({"file": f, "flowchart": f, "add_graph": "RandoFairy_BeanEntry", "start": "e0", "nodes": entry})
        for k, ep in enumerate(sorted(bn["entries"])):
            o.events.append({"file": f, "flowchart": f, "entry": ep, "next": f"RandoFairy_BeanEntry_e{k}"})
        resume = f"@{bn['tail'][1]}"
        nodes, chains = {}, {"Obj_SmallFarm_A_02": [], "Obj_SmallFarm_A_01": []}
        for h, gs in soils:
            chains[spec[h]["actor"]].append((h, sorted(gs, key=lambda g: g["spot"]["index"])))
        heads = {}
        for actor, items in chains.items():
            tag = "a2" if actor.endswith("_02") else "a1"
            heads[actor] = f"{tag}q0" if items else resume
            for i, (h, gs) in enumerate(items):
                nxt = f"{tag}q{i + 1}" if i + 1 < len(items) else resume
                flag = p["soil_flag"][f"bean:{h}"]
                c = f"{tag}c{i}"
                nodes[f"{tag}q{i}"] = data._distance(actor, spec[h]["instance"], c, nxt)
                nodes[c] = st.flag_query(flag, resume, f"{c}s")
                nodes[f"{c}s"] = st.flag_set(flag, f"{c}g0")
                for j, g in enumerate(gs):
                    after = f"{c}g{j + 1}" if j + 1 < len(gs) else resume
                    nodes[f"{c}g{j}"] = o.give(g["target"], after) if j == 0 else dg._window(o, g["target"], after)
                for pl in spec[h]["places"]:
                    o.placements.append({"file": pl["file"], "hash": pl["hash"], "set": {"Name": spec[h]["instance"]}})
        nodes["t"] = st.flag_query(scratch, heads["Obj_SmallFarm_A_02"], heads["Obj_SmallFarm_A_01"])
        o.events.append({"file": f, "flowchart": f, "add_graph": "RandoFairy_Beans", "start": "t", "nodes": nodes})
        o.events.append({"file": f, "flowchart": f, "event": bn["tail"][0], "next": "RandoFairy_Beans_t"})
        o.notes.append(f"bean fairies: {sum(len(g) for _, g in soils)} items at {len(soils)} bean plants after the "
                       f"fairy leaves ({f}:RandoFairy_Beans; soil type: {scratch})")
