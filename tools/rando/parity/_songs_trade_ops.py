"""Patch-plan building blocks for the songs/trade/cows plugin (songs_trade.py).

Every edit replaces one vanilla scene step with a small graph (EvflBuilder.add_graph) and points everything that led
to that step at the graph, the same way the patcher's progressive scenes do. Step names, routing and predecessors
come from data/rando/songs_trade_data.json (built from the game files by _songs_trade_build.py).

Items are handed over with the game's in-cutscene get routine Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff
{ActorName}. Link holds it up, the message shows and it goes in the pouch. NPC scenes like the Lost Woods bullet bag
use it, and so do the progressive chest scenes, where I've seen it working in game. A progressive item calls a "give
the right tier" entry added next to that routine (tools/progressive.py host_graph). Those are named RandoST_* so they
never clash with the patcher's own Rando_* host entries.
"""
import json
import os
import re

import progressive  # tools/progressive.py

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GET_FILE, GET_ROUTINE = "Dm_SY_GetInEvent", "GetInEvent_NotLookatObjectTurnOff"
ICE_CALL = "Dm_SY_GetInEvent:Rando_IceTrap"  # added by tools/rando/parity/chests.py when any ice trap needs it
YES, NO = progressive.YES, progressive.NO


def load(name):
    return json.load(open(os.path.join(HERE, "data", "rando", name), encoding="utf-8"))


class Ops:
    """Collects the plan sections, one instance per seed."""

    def __init__(self):
        self.events, self.byml, self.rewards, self.notes, self.placements = [], [], {}, [], []
        self._hosts = set()

    # -- items
    def give(self, target, nxt, copy=None):
        """A node that hands over `target` ({"actor": X} or {"progressive": name}), then goes to `nxt`.
        `copy` is a vanilla give step of the same flowchart. We reuse its call (routine, NPC and camera arguments) and
        only change ActorName. Progressive items always use the tier entry.
        A {"call": scene} target (the Magic Bean Pack, _songs_trade_child.target) calls its scene. The bean pack's item
        rule allows every core scene location, and the 100-Skulltula reward, loach and frogs build their give step
        here."""
        if "call" in target:
            return {"call": target["call"], "next": nxt}
        if target.get("ice_trap"):  # the shared freeze (tools/rando/parity/_chests_scenes.py host_graphs)
            return {"call": ICE_CALL, "next": nxt}
        if "progressive" in target:
            name = target["progressive"]
            entry = host_entry(name)
            if entry not in self._hosts:
                self._hosts.add(entry)
                nodes, start = progressive.host_graph(progressive.PROGRESSIVE[name]["tiers"], GET_ROUTINE, "ActorName")
                self.events.append({"file": GET_FILE, "flowchart": GET_FILE, "add_graph": entry, "nodes": nodes,
                                    "start": start})
            return {"call": f"{GET_FILE}:{entry}", "next": nxt}
        held = progressive.hold_node(target["actor"], nxt)  # an item Link can't hold up (config/hold_up.json)
        if held:
            return held
        if copy:
            return {"copy": copy, "params_over": {"ActorName": target["actor"]}, "next": nxt}
        return {"call": f"{GET_FILE}:{GET_ROUTINE}", "params": {"ActorName": target["actor"]}, "next": nxt}

    # -- routing
    def replace(self, file, flowchart, step, graph, nodes, start):
        """Adds `nodes` as entry `graph` and routes every predecessor of `step` (a data record) to its start."""
        self.events.append({"file": file, "flowchart": flowchart, "add_graph": graph, "nodes": nodes, "start": start})
        target = f"{graph}_{start}"
        for kind, where, k in step["preds"]:
            op = {"file": file, "flowchart": flowchart, "next": target}
            if kind == "entry":
                op["entry"] = where
            else:
                op["event"] = where
                if kind in ("case", "fork"):
                    op[kind] = k
            self.events.append(op)

    def param(self, file, flowchart, event, name, value):
        self.events.append({"file": file, "flowchart": flowchart, "event": event, "param": name, "value": value})

    def plan(self):
        out = {}
        if self.events:
            out["events"] = self.events
        if self.byml:
            out["byml"] = self.byml
        if self.rewards:
            out["rewards"] = self.rewards
        if self.placements:
            out["placements"] = self.placements
        if self.notes:
            out["songs_trade_notes"] = self.notes
        return out


def reward_spec(target, note, rids=()):
    """A core reward spec (make_patch "rewards", an event reward's give steps) for give target `target`.
    That's its actor or progressive name, or for a scene call (a dungeon item's credit entry, songs_trade._target) the
    call itself, and make_patch scene_call_ops replaces every give step with it. There "item" names the item's model and
    is never handed over. A progressive item whose give steps `rids` can't hand it over themselves (takes_progressive)
    is given by a call to its tier entry instead (call_spec)."""
    if "call" in target and target.get("model"):
        return {"item": target["model"], "call": target["call"], "note": note}
    if "progressive" in target and rids and not takes_progressive(rids, target["progressive"]):
        return call_spec(target["progressive"], note)
    return {"item": target.get("actor") or target["progressive"], "note": note}


# Progressive items through their tier entry
# Some give steps can't hand over a progressive item themselves. Either the flowchart has no PouchSystemActor and the
# step isn't a plain give-routine call (data/rando/scene_give_modes.json mode None), or it's a tier with its own give
# entry, like the Kokiri wallet, at an in-place copy. Those steps get replaced by a call to the item's "give the right
# tier" entry (RandoST_<Item>_Get next to the get routine, progressive.host_graph), the same way ice traps and dungeon
# items already are at those steps (make_patch scene_call_ops).
# Other plugins' give steps (scrub sales, the carpet salesman, the hideout jails) call it too, and request_host makes
# the songs/trade plugin's plan add the entry. That works because its world_plan runs after the plugins whose names
# sort before it, and the core's rewards are built before every plugin plan.
GIVE_MODES = load("scene_give_modes.json")["locations"]
_requested = {"names": set(), "window": set(), "built": False}


def host_entry(name):
    """The tier entry's name in Dm_SY_GetInEvent for progressive item `name` (its plan name)."""
    return "RandoST_" + "".join(w for w in name.title().split() if w.isalnum()) + "_Get"


def request_host(name, window=False):
    """Returns 'Dm_SY_GetInEvent:<tier entry>' for progressive item `name`. The songs/trade plugin's plan adds the
    entry. With window=True (a spot in the water, so no hold-up) it's the tier entry next to the get window instead,
    'GetPouchContent:RandoST_Pouch_<Item>' (_songs_trade_lake._window_give)."""
    pool = _requested["window"] if window else _requested["names"]
    if _requested["built"] and name not in pool:
        raise RuntimeError(f"{name}: its tier entry was asked for after the songs/trade plugin's plan was built")
    pool.add(name)
    if window:
        return "GetPouchContent:RandoST_Pouch_" + "".join(w for w in name.title().split() if w.isalnum())
    return f"{GET_FILE}:{host_entry(name)}"


def requested_window_hosts():
    """The progressive items whose window tier entry other give steps call (request_host window=True)."""
    _requested["built"] = True
    return sorted(_requested["window"])


def requested_hosts():
    """The progressive items whose tier entry other give steps call (for the songs/trade plugin's plan, once)."""
    _requested["built"] = True
    return sorted(_requested["names"])


def call_spec(name, note=None):
    """A core reward spec that gives progressive item `name` through its tier entry. Every give step becomes a call to
    it (make_patch scene_call_ops). "item" is its first tier and only there as a name, since the step's own hand-over is
    gone."""
    spec = {"item": progressive.PROGRESSIVE[name]["tiers"][0], "call": request_host(name)}
    if note:
        spec["note"] = note
    return spec


def no_call_locations(world):
    """Locations where no give step can call an entry, so items that only an entry of their own can give (the Magic Bean
    Pack, the souls) can't go there. That's the chests and the shop shelves (Shop_* actors only), except core scene
    locations, whose steps become the call. The chests are the core's chest_map ones, the chests plugin's own, the
    dungeons plugin's kept ones and any OoTR Chest, because a chest gives one actor and has no scene for these items.
    Everything else can call: NPC and scene gives, the get scene of drop spots and fairies, scrub sales and the carpet
    salesman, silver-rupee spots, the hideout jails and the Treasure Chest Game salesman."""
    import sys
    import generate
    cm = load("chest_map.json")["chests"]
    out = {n for n, v in cm.items() if v["mode"] in ("full", "group")}
    ch = sys.modules.get("parity.chests")
    if ch is not None:
        out |= set(ch._mine())
        out.discard(getattr(getattr(ch, "tcg", None), "SALESMAN", None))  # he's an NPC and his sale calls
    dg = sys.modules.get("parity.dungeons")
    if dg is not None:
        out |= set(dg.WORLD.get("kept_chests", {}))
    out |= {loc.name for loc in world.get_locations() if loc.type in ("Chest", "Shop")}
    # Some chests can call the entry for a soul, the Skeleton Key or the bean pack through dungeons.chest_call_item.
    # Special deals can give anything through their own steps (shops.deal_locations).
    if dg is not None and hasattr(dg, "chest_calls_ok"):
        out = {n for n in out if not dg.chest_calls_ok(n)}
    sh = sys.modules.get("parity.shops")
    if sh is not None and hasattr(sh, "deal_locations"):
        out -= sh.deal_locations(world)
    return out - set(generate.scene_locations())


def _step_modes(rid):
    """The give modes of the steps of scene location or reward id `rid` (data/rando/scene_give_modes.json). A reward id
    is matched by its step, File.bfevfl.zs:EventN in any version of the file."""
    if rid in GIVE_MODES:
        return list((GIVE_MODES[rid].get("steps") or {}).values())
    parts = str(rid).split("/")
    if len(parts) != 5:
        return []
    rx = re.compile(rf"^{re.escape(parts[1])}(\.\d+)?\.bfevfl\.zs:{re.escape(parts[3])}$")
    return [m for loc in GIVE_MODES.values() for k, m in (loc.get("steps") or {}).items() if rx.match(k)]


def takes_progressive(rids, name):
    """True if every give step of `rids` (scene location or reward ids) hands over progressive item `name` (its plan
    name) by itself. That's an in-place copy ("inplace", the giver's flowchart has a PouchSystemActor) or a give-routine
    host ("host"). A tier with its own posing give entry (progressive.GIVE, the Kokiri wallet) only counts through a
    host."""
    tiers = progressive.PROGRESSIVE[name]["tiers"]
    host_only = any(t in progressive.GIVE and t not in progressive.NO_POSE for t in tiers)
    modes = [m for rid in rids for m in _step_modes(rid)]
    return bool(modes) and all((m == "host") if host_only else (m in ("inplace", "host")) for m in modes)


def at(event):
    return f"@{event}" if event else None


def flag_query(name, yes, no):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool", "params": {"GameDataName": name, "Index": -1},
            "cases": {YES: yes, NO: no}}


def flag_set(name, nxt):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
            "params": {"GameDataName": name, "Value": True, "Index": -1}, "next": nxt}


COW_ANCHOR_DISTANCE = 40.0  # any distance Link can play to a cow from; the anchor's name tells the cows apart


def anchor_query(name, yes, no):
    """Whether the actor that started this event links a DestinationAnchor named `name` (a cow's anchor,
    songs_trade_cows.json). It's the vanilla distance query with IsAnchorActorB, which looks the anchor up among the
    starter's links. An anchor nothing in the event links isn't found, and that's the 'not close' case."""
    return near_query({"ActorNameB": "DestinationAnchor", "InstanceNameB": name, "IsAnchorActorB": True,
                       "CheckDistance": COW_ANCHOR_DISTANCE}, yes, no)


def near_query(near, yes, no):
    p = {"ActorNameA": "Player_Event", "InstanceNameA": "", "IsAnchorActorA": False, "IsTargetPlayingAllEvent": False}
    p.update(near)
    return {"actor": "GameSystemActor", "query": "EventQueryIsDistanceBetweenActorsClose", "params": p,
            "cases": {YES: yes, NO: no}}


def wait_node(actor, nxt):
    return {"actor": actor, "action": "EventWait", "params": {"Frames": 1, "IsWaitEnd": True}, "next": nxt}
