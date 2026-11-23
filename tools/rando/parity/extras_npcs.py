"""Parity plugin for checks OoT Randomizer doesn't have, taken from Ship of Harkinian (SoH) and the 3DS randomizer
(OoT3DR).

Every feature is a remake setting and off by default. A feature that's off doesn't exist at all. Its locations,
pool items and rule changes only get added after OoTR builds the world (the same way story.py adds the Master Sword
pedestal), so with every setting off a seed comes out byte for byte the same as without this plugin.
The data is in data/rando/extras_npcs.json (locations, regions, rules, claimed flags) and
data/rando/extras_npcs_data.json (the hooked scene steps, which _extras_npcs_build.py builds from the game files).

remake_shuffle_beggar (SoH Shuffle Beggar): the beggar who buys bottled fish, bugs and blue fire gives an item the
  first time each content is offered at each age, so 6 checks. He's Npc_Hylia_046_BottleShop_Child, in the Market
  as child and in Kakariko as adult, one actor and one scene file. The item comes right after the player picks the
  content, before Link shows the bottle and the price talk, and then the sale goes on like vanilla.
remake_shuffle_fire_gorons (SoH Shuffle Fire Gorons): each of the 9 jailed Fire Temple gorons gives an item when
  you talk to him after his cell opens. It comes between his thank-you and the fade to his run-away scene, which
  then sets his Npc_Goron_<n>_Delete so he's gone. He uses the rule and region of the chest in his cell.
remake_shuffle_fishermans_hat (SoH Shuffle Fisherman's Hat): returning the pond owner's hat (you hook it off his
  head with the line as adult) gives an item once, before his "keep this a secret" line.
remake_shuffle_fishing_pole (SoH Shuffle Fishing Pole): a new item, "Fishing Pole". It's the remake's
  Item_FishingRod, a pouch item no menu shows. The pond owner won't rent you a rod until you've found it, and his
  "not enough rupees" line is reworded in every language to say so. Found means IsGet.Item_FishingRod, which the
  engine sets on the pouch add and nothing else sets (the vanilla rental only shows the rod and lends a minigame
  item). Child fishing, adult fishing, the loach and the hat need it in logic. The pole can go anywhere OoTR could
  put an item because config/item_map.json names it, so every give path hands it over: chests, scene and NPC
  gives, scrubs, the get scene of drop spots and fairies, and silver-rupee spots.
remake_shuffle_big_poes (OoT3DR Shuffle Big Poes): each of the 10 Big Poes gives an item the first time you bottle
  its soul. Dm_SY_InsertBottle gets the poe's fence number in its argument BigPoeFenceId (-1 for any other catch).
  The hook copies it into a scratch number and branches on it. The scratch is SimpleShop_Price, which isn't saved
  and gets set before every vanilla use. The bottled soul still sells, so OoTR's Big Poe rules don't change.
remake_shuffle_signs (SoH Shuffle Signs; off / dungeons / overworld / all): 35 readable signs, tablets, graves,
  the plinth-like poem and the Temple of Time altar give an item the first time you read them. Those are the ones
  with a scene row of their own. Signs on the two shared generic rows aren't built.
remake_fishsanity (SoH Fishsanity; off / pond / overworld / both), remake_fishsanity_pond_count (SoH Pond Fish
  Count, 0-17) and remake_fishsanity_age_split (SoH Pond Age Split).
  Pond: every catch ends in MiniGame_Fishing:Step01_CatchFish_Child / _Adult, which calls :CatchFish_Sub and then
  ends. After that the catch hands over the first unclaimed check of the age's list (the child list for both ages
  without the split). That's what SoH does for counts 1-16. No fish has an identity of its own, so count 17 uses
  the same order. The child list is 15 fish and 2 loaches, the adult list 15 fish and a loach.
  Overworld: the five fish of the child Zora's Domain layout. Each gets a placement Name (RandoFish<k>), and the
  pouch event AI (AI/PouchContent.event.root.ainb, AI.Global) answers EventQueryCheckTagOnPouchActor with 4 + k
  for that name (drops.get_scene_ops). Dm_SY_InsertBottle asks the caught actor for that tag while it's still the
  guest performer, after its attention step, and keeps the fish number in SimpleShop_Price. Then the catch's two
  endings give that fish's item once, before the Big Poe checks (those set SimpleShop_Price again). The fish stays
  in the bottle. SoH's nine grotto fish aren't built because the remake's grottos have no fish.
  SoH's "Shuffle only Hyrule Loach" is OoTR's shuffle_loach_reward (songs_trade.py).

Every check marks itself given with a saved flag that's set right before the hand-over, so an autosave inside the
get routine can't keep the item without the flag. That's the goron's, poe's or sign's own flag, or a claimed flag
nothing in the game uses (extras_npcs.json flags_claimed). Items are handed over with the game's in-cutscene get
routine (Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff), a progressive tier entry, the chests plugin's freeze
for ice traps or the dungeons plugin's credit entry for dungeon items. Items none of those can give are kept out
by item rule.
"""
import json
import os
import re
import sys

from . import _songs_trade_ops as ops

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SPEC = json.load(open(os.path.join(HERE, "data", "rando", "extras_npcs.json"), encoding="utf-8"))
DATA = json.load(open(os.path.join(HERE, "data", "rando", "extras_npcs_data.json"), encoding="utf-8"))
ITEM_MAP = json.load(open(os.path.join(HERE, "config", "item_map.json"), encoding="utf-8"))
PROGRESSIVE = ops.progressive.PROGRESSIVE
GET_FILE, GET_ROUTINE = ops.GET_FILE, ops.GET_ROUTINE
PREFIX = "RandoEX_"  # entry names this plugin adds (other plugins use Rando_ and RandoST_)

OWNS = {}  # everything here is a remake setting, no OoTR ones
SIGN_LEVELS = ("off", "dungeons", "overworld", "all")
REMAKE_SETTINGS = {
    "remake_shuffle_beggar": (False, True),
    "remake_shuffle_fire_gorons": (False, True),
    "remake_shuffle_fishermans_hat": (False, True),
    "remake_shuffle_fishing_pole": (False, True),
    "remake_shuffle_big_poes": (False, True),
    "remake_shuffle_signs": SIGN_LEVELS,
    "remake_fishsanity": ("off", "pond", "overworld", "both"),
    "remake_fishsanity_pond_count": tuple(range(18)),
    "remake_fishsanity_age_split": (False, True),
}
REMAKE_DEFAULTS = {k: v[0] for k, v in REMAKE_SETTINGS.items()}
POLE = SPEC["pole"]["item"]
POLE_ACTOR = SPEC["pole"]["actor"]
FLAGS = {k: v for k, v in SPEC["flags_claimed"].items() if not k.startswith("_")}
# OoTR junk that would be a stand-in here (config/item_map.json junk_for) is refused, so the item given is always
# the one the spoiler names.
STAND_INS = {k for k in ITEM_MAP["junk_for"] if k not in ITEM_MAP["items"]}
TYPE = "NPC"
_state = {}  # id(world) -> {"locs": {name: feature}, "dungeon_calls": set}


# Settings
def _remake(settings, key):
    return (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS[key])


def check_settings(settings):
    problems = []
    remake = getattr(settings, "remake", None) or {}
    for k, ok in REMAKE_SETTINGS.items():
        if k in remake and remake[k] not in ok:
            problems.append(f"{k} = {remake[k]!r}: extras_npcs can make {', '.join(map(repr, ok))}")
    return problems


def untested(settings):
    out = []
    names = {"remake_shuffle_beggar": "beggar: an item at the bottle choice, once per content and age",
             "remake_shuffle_fire_gorons": "Fire Temple gorons: an item after the freed goron's thank-you",
             "remake_shuffle_fishermans_hat": "fishing pond owner's hat: an item when it is given back",
             "remake_shuffle_fishing_pole": "fishing pole: the owner refuses to rent until Item_FishingRod is found",
             "remake_shuffle_big_poes": "Big Poes: an item when each poe's soul is bottled (the fence number "
                                        "argument read in new steps)"}
    for k, text in names.items():
        if _remake(settings, k):
            out.append(f"extras_npcs: {text}")
    if _remake(settings, "remake_shuffle_signs") != "off":
        out.append(f"extras_npcs: signs ({_remake(settings, 'remake_shuffle_signs')}): an item at the first read")
    if _pond_lists(settings)[0]:
        out.append("extras_npcs: fishsanity pond: each catch gives the next unclaimed check of the age's list, after "
                   "the keep/release talk")
    if _remake(settings, "remake_fishsanity") in ("overworld", "both"):
        out.append("extras_npcs: fishsanity Zora's Domain: an item the first time each child ZD fish is bottled "
                   "(the bottle scene asks the caught fish's tag)")
    return out


def _pond_lists(settings):
    """(child list, adult list) of the pond checks these settings turn on, in claiming order."""
    if _remake(settings, "remake_fishsanity") not in ("pond", "both"):
        return [], []
    n = int(_remake(settings, "remake_fishsanity_pond_count"))
    child = SPEC["fish"]["pond"]["child"][:n]
    adult = SPEC["fish"]["pond"]["adult"][:n] if _remake(settings, "remake_fishsanity_age_split") else []
    return child, adult


def _sign_on(settings, spec):
    level = _remake(settings, "remake_shuffle_signs")
    return level == "all" or (level == "dungeons" and spec["dungeon"]) or (level == "overworld" and not spec["dungeon"])


def active(settings):
    """{OoTR location name: feature} for the features these settings turn on (data/rando/extras_npcs.json)."""
    out = {}
    if _remake(settings, "remake_shuffle_beggar"):
        out.update({n: "beggar" for n in SPEC["beggar"]["locations"]})
    if _remake(settings, "remake_shuffle_fire_gorons"):
        out.update({n: "fire_gorons" for n in SPEC["fire_gorons"]["locations"]})
    if _remake(settings, "remake_shuffle_fishermans_hat"):
        out.update({n: "hat" for n in SPEC["hat"]["locations"]})
    if _remake(settings, "remake_shuffle_big_poes"):
        out.update({n: "big_poes" for n in SPEC["big_poes"]["locations"]})
    for n, s in SPEC["signs"]["locations"].items():
        if _sign_on(settings, s):
            out[n] = "signs"
    child, adult = _pond_lists(settings)
    out.update({n: "fish" for n in child + adult})
    if _remake(settings, "remake_fishsanity") in ("overworld", "both"):
        out.update({n: "fish" for n in SPEC["fish"]["zd"]["locations"]})
    return out


def _location_spec(name, feature):
    if feature == "big_poes":
        b = SPEC["big_poes"]
        return dict(b["locations"][name], region=b["region"], rule=b["rule"], tags=b["tags"])
    if feature == "fish":
        f = SPEC["fish"]
        part = f["zd"] if name in f["zd"]["locations"] else f["pond"]
        return {"region": part["region"], "rule": part.get("rule"), "tags": part["tags"]}
    s = dict(SPEC[feature]["locations"][name])
    if feature == "signs":
        s.setdefault("tags", ["Signs"])
    return s


# OoTR tables (before the world is built)
def _register(settings):
    """Adds the pole as an OoTR item (Fishing_Pole in rules) and this seed's locations to OoTR's tables, without
    editing vendor/ootr. Those are the tables OoTR builds from ItemList / LocationList / HintList at import, and
    story.py does the same thing."""
    import HintList
    import Item
    import ItemList
    import Language
    import LocationList
    texts = {}
    if _remake(settings, "remake_shuffle_fishing_pole"):
        if POLE not in ItemList.item_table:
            ItemList.item_table[POLE] = ("Item", True, None, None)
        if POLE not in Item.ItemInfo.items:
            Item.ItemInfo.items[POLE] = Item.ItemInfo(POLE)
        vague, clear = SPEC["pole"]["hint"]
        texts[POLE] = (vague, clear, "item")
    for name, feature in active(settings).items():
        if name not in LocationList.location_table:
            tags = tuple(_location_spec(name, feature).get("tags") or ())
            LocationList.location_table[name] = (TYPE, None, None, None, None, tags)
            for group in (TYPE,) + tags:
                if group in LocationList.location_groups:
                    LocationList.location_groups[group].append(name)
        texts[name] = (f"#{name}# holds", None, "exclude")
    for name, row in texts.items():
        HintList.hintTable.setdefault(name, row)
    _register.texts.update(texts)
    if not getattr(Language.Language.__init__, "remake_extras_npcs", False):
        original = Language.Language.__init__

        def init(self, lang, _original=original):  # every language's hint table (World makes one per world)
            _original(self, lang)
            for name, (vague, clear, _) in _register.texts.items():
                self.hintTable.setdefault(name, {"vague_hint": vague, "clear_hint": clear, "gender": "no_gender"})
        init.remake_extras_npcs = True
        Language.Language.__init__ = init


_register.texts = {}


def before_build(settings):
    import free_flags  # only the flags of this seed's features are held (tools/rando/free_flags.py hold)
    free_flags.hold("extras_npcs", [FLAGS[n] for n in sorted(active(settings)) if n in FLAGS])
    if active(settings) or _remake(settings, "remake_shuffle_fishing_pole"):
        _register(settings)


# Locations, pool, rules
def _add_location(world, name, region_name, rule):
    from Location import LocationFactory
    region = world.get_region(region_name)
    loc = next((x for x in region.locations if x.name == name), None)
    if loc is None:
        loc = LocationFactory(name)
        loc.parent_region = region
        loc.world = world
        region.locations.append(loc)
        if world._cached_locations:
            world._cached_locations.append(loc)
    loc.rule_string = rule
    world.parser.parse_spot_rule(loc)
    return loc


def _junk(world):
    """One junk item for the pool, picked the way OoTR picks junk. Stand-ins become 5 rupees."""
    from Item import ItemFactory
    from ItemPool import get_junk_item
    name = get_junk_item()[0]
    return ItemFactory("Rupees (5)" if name in STAND_INS else name, world)


def keep_locations(world, settings):
    """Puts this seed's new locations in their regions with their rules, and one junk item each in the pool. With the
    pole shuffled the fishing locations need it, and it takes the place of one junk item."""
    locs = active(settings)
    st = _state[id(world)] = {"locs": dict(locs), "dungeon_calls": set()}
    for name, feature in sorted(locs.items()):
        s = _location_spec(name, feature)
        if feature == "fire_gorons":
            chest = world.get_location(s["copy_rule_of"])
            _add_location(world, name, chest.parent_region.name, chest.rule_string)
        elif feature == "fish" and s["rule"] is None:  # a pond check: SoH's rule (IsChild || !split) / IsAdult
            pond = SPEC["fish"]["pond"]
            split = _remake(settings, "remake_fishsanity_age_split")
            rule = (pond["rule_adult"] if name in pond["adult"] else
                    pond["rule_child_split"] if split else pond["rule_child"])
            _add_location(world, name, s["region"], rule)
        else:
            _add_location(world, name, s["region"], s["rule"])
        world.itempool.append(_junk(world))
    if _remake(settings, "remake_shuffle_fishing_pole"):
        from Item import ItemFactory
        child, adult = _pond_lists(settings)
        for name in SPEC["pole"]["needs_pole"] + child + adult:
            try:
                loc = world.get_location(name)
            except KeyError:
                continue
            if "Fishing_Pole" not in (loc.rule_string or ""):
                loc.rule_string = f"({loc.rule_string or 'True'}) and Fishing_Pole"
                world.parser.parse_spot_rule(loc)
        pool = world.itempool
        k = next((i for i in range(len(pool) - 1, -1, -1) if not pool[i].advancement and not pool[i].priority
                  and not pool[i].dungeonitem), None)
        if k is None:
            raise ValueError("remake_shuffle_fishing_pole: no junk item left to make room for the Fishing Pole")
        pool[k] = ItemFactory(POLE, world)
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "CALL_LOCATIONS"):
        dg.CALL_LOCATIONS.update(locs)  # a dungeon item here is given through its credit entry (dungeons.call_target)
    return set(locs)


def _target(item_name, location=None):
    """How one of our checks hands over OoTR item `item_name`, or None if it can't. `location` is the OoTR location
    the plan gives it at, so an Ice Trap there gets the effect of the trap kind it drew."""
    if item_name == "Ice Trap":
        ch = sys.modules.get("parity.chests")
        if ch is None:
            return None
        return dict({"ice_trap": True}, **({"call": ch.trap_call_at(location)} if location else {}))
    if item_name in PROGRESSIVE:
        return {"progressive": item_name}
    if item_name == POLE:
        return {"actor": POLE_ACTOR}
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and dg.dungeon_item(item_name) is not None:
        return {"dungeon": item_name} if hasattr(dg, "call_target") else None
    if item_name in STAND_INS:
        return None
    try:
        from Item import ItemInfo
        info = ItemInfo.items.get(item_name)
        if info is not None and (info.trade or info.type in ("Event", "Shop")):
            return None  # trade items have their own timers and hatching (songs_trade.py's targets)
    except ImportError:
        pass
    actor = ITEM_MAP["items"].get(item_name)
    return {"actor": actor} if actor else None


def before_fill(world, settings):
    st = _state.get(id(world))
    if st is None:
        return
    for name, feature in sorted(st["locs"].items()):
        loc = world.get_location(name)
        if feature == "fire_gorons":  # the chest's final rule (group logic may have replaced it)
            chest = world.get_location(SPEC["fire_gorons"]["locations"][name]["copy_rule_of"])
            if chest.rule_string != loc.rule_string:
                loc.rule_string = chest.rule_string
                world.parser.parse_spot_rule(loc)
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: _target(item.name) is not None and prev(location, item))


def after_fill(world, settings):
    """Dungeon items at these checks need credit entries from the dungeons plugin, so we ask for them now, before its
    world_plan builds them (that runs earlier than ours). Requests from a failed attempt are taken back first."""
    st = _state.get(id(world))
    dg = sys.modules.get("parity.dungeons")
    if st is None or dg is None or not hasattr(dg, "call_target"):
        return
    used = getattr(dg, "_used", {}).get("call")
    if used is not None:
        used.difference_update(st["dungeon_calls"])
    st["dungeon_calls"] = set()
    for name in st["locs"]:
        item = world.get_location(name).item
        if item is not None and dg.dungeon_item(item.name) is not None:
            dg.call_target(item.name)
            st["dungeon_calls"].add(item.name)


def item_for(item, location, world):
    """The pole at a core chest or scene location is the remake's fishing rod item."""
    if item == POLE:
        return POLE_ACTOR
    return None


# Patch plan
class Ops(ops.Ops):
    """songs_trade's plan builder with our entry names and the hand-over targets above."""

    def give(self, target, nxt, copy=None, host=False):
        """A node that hands over `target`. With host=True the node sits in Dm_SY_GetInEvent itself, so calls are
        local."""
        def call(entry):
            f, e = entry.split(":")
            return {"call": f":{e}" if host and f == GET_FILE else entry, "next": nxt}
        if target.get("ice_trap"):
            return call(target.get("call") or ops.ICE_CALL)
        if "dungeon" in target:
            dg = sys.modules["parity.dungeons"]
            return call(f"{dg.GET_FILE}:{dg.call_entry(target['dungeon'])}")
        if "progressive" in target:
            name = target["progressive"]
            entry = PREFIX + "".join(w for w in name.title().split() if w.isalnum()) + "_Get"
            if entry not in self._hosts:
                self._hosts.add(entry)
                nodes, start = ops.progressive.host_graph(PROGRESSIVE[name]["tiers"], GET_ROUTINE, "ActorName")
                self.events.append({"file": GET_FILE, "flowchart": GET_FILE, "add_graph": entry, "nodes": nodes,
                                    "start": start})
            return call(f"{GET_FILE}:{entry}")
        held = ops.progressive.hold_node(target["actor"], nxt, GET_FILE if host else None)
        if held:  # an item Link can't hold up (config/hold_up.json)
            return held
        node = call(f"{GET_FILE}:{GET_ROUTINE}")
        node["params"] = {"ActorName": target["actor"]}
        return node


def _item(world, name):
    loc = world.get_location(name)
    return loc.item.name if loc.item is not None else None


def _given_once(o, flag, target, nxt, host=False):
    """Nodes that go to nxt if the flag is set. Otherwise they set it, hand over the item and then go to nxt.
    Returns (nodes, start)."""
    n = {"q": ops.flag_query(flag, nxt, "set"), "set": ops.flag_set(flag, "give"),
         "give": o.give(target, nxt, host=host)}
    return n, "q"


def _beggar_ops(o, world, items, notes):
    d = DATA["beggar"]
    locs = SPEC["beggar"]["locations"]
    for kind, step in sorted(d["choices"].items()):
        by_age = {s["age"]: n for n, s in locs.items() if s["bottle"] == kind}
        vanilla = ops.at(step["event"])
        n = {"age": {"actor": "Player_Event", "query": "EventQueryPlayerIsChild",
                     "cases": {ops.YES: "child_q", ops.NO: "adult_q"}}}
        for age, name in by_age.items():
            item = items[name]
            n[f"{age}_q"] = ops.flag_query(FLAGS[name], vanilla, f"{age}_set")
            n[f"{age}_set"] = ops.flag_set(FLAGS[name], f"{age}_give")
            n[f"{age}_give"] = o.give(_target(item, name), vanilla)
            notes.append(f"{name}: {item}")
        o.replace(d["file"], d["flowchart"], step, f"{PREFIX}Beggar_{kind}", n, "age")


def _goron_ops(o, world, items, notes):
    for name, s in sorted(SPEC["fire_gorons"]["locations"].items()):
        d = DATA["fire_gorons"][s["goron"]]
        item = items[name]
        fade = ops.at(d["fade"]["event"])
        # His run-away scene sets Npc_Goron_<n>_Delete after the gift. Set the claimed flag before giving it
        # so an autosave in the get scene can't let the player claim the item again.
        n = {"gone": ops.flag_query(d["delete_flag"], fade, "q")}
        g, start = _given_once(o, FLAGS[name], _target(item, name), fade)
        n.update(g)
        o.replace(d["file"], d["flowchart"], d["fade"], f"{PREFIX}Goron", n, "gone")
        notes.append(f"{name}: {item} (goron {s['goron']}, after {d['message'].split(':')[-1]})")


def _hat_ops(o, world, items, notes):
    d = DATA["hat"]
    name = next(iter(SPEC["hat"]["locations"]))
    item = items[name]
    n, start = _given_once(o, FLAGS[name], _target(item, name), ops.at(d["returned"]["event"]))
    o.replace(d["file"], d["flowchart"], d["returned"], f"{PREFIX}Hat", n, start)
    notes.append(f"{name}: {item}")


def _pole_ops(o, world, notes):
    d = DATA["pole"]
    flag = SPEC["pole"]["flag"]
    n = {"q": ops.flag_query(flag, ops.at(d["payment"]["event"]), ops.at(d["no_rupees"]))}
    o.replace(d["file"], d["flowchart"], d["payment"], f"{PREFIX}PoleGate", n, "q")
    loc = next((x for x in world.get_locations() if x.item is not None and x.item.name == POLE), None)
    hint = loc is not None and "fishing_pole" in ((getattr(world.settings, "remake", None) or {})
                                                  .get("remake_extra_hints") or [])
    o.text += pole_text_ops(world, loc.name if hint else None)
    notes.append(f"{POLE}: {loc.name if loc else '?'} (the owner rents no rod before {flag}"
                 f"{'; his line says where it is' if hint else ''})")


SCRATCH = "SimpleShop_Price"  # a number nothing saves and every vanilla user sets first (the shops' price)


def _poe_ops(o, world, items, notes, poes=True, fish=False):
    """The two endings of the bottle catch (Dm_SY_InsertBottle). First come the ZD fish checks when fish is on, using
    the number the guest step kept in SCRATCH. Then the Big Poe checks when poes is on, which put the scene's
    BigPoeFenceId in SCRATCH. Then the vanilla ending."""
    d = DATA["big_poes"]
    by_fence = {s["fence"]: n for n, s in SPEC["big_poes"]["locations"].items()}
    from write_read_check import settle  # a write lands a frame or two later, so compare after it
    scratch = SCRATCH
    for path, step in sorted(d["ends"].items()):
        cont = ops.at(step["next"]) if step["next"] else None
        n = {}
        if poes:
            n["num"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                        "params": {"GameDataName": scratch, "Index": -1, "Value": {"arg": "BigPoeFenceId"}},
                        "next": "num_settle"}
            n["num_settle"] = settle("c1")
            fences = sorted(by_fence)
            for i, k in enumerate(fences):
                nxt_cmp = f"c{fences[i + 1]}" if i + 1 < len(fences) else cont
                # EventQueryIsGameDataInt cases are 0 lower, 1 equal, 2 higher. The poe buyer uses it that way on
                # GhostShop_CouponNum.
                n[f"c{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                              "params": {"GameDataName": scratch, "Index": -1, "Value": k},
                              "cases": {0: cont, 1: f"q{k}", 2: nxt_cmp}}
                name = by_fence[k]
                flag = f"HyruleField_Defeat_BigPoe_{k:02d}"
                n[f"q{k}"] = ops.flag_query(flag, cont, f"s{k}")
                n[f"s{k}"] = ops.flag_set(flag, f"g{k}")
                n[f"g{k}"] = o.give(_target(items[name], name), cont)
        start = "num" if poes else None
        if fish:
            after = "num" if poes else cont
            zd = [(k, r["location"]) for k, r in enumerate(DATA["fish"]["zd"], 1)]
            for i, (k, name) in enumerate(zd):
                nxt_cmp = f"fc{zd[i + 1][0]}" if i + 1 < len(zd) else after
                n[f"fc{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                               "params": {"GameDataName": scratch, "Index": -1, "Value": k},
                               "cases": {0: after, 1: f"fq{k}", 2: nxt_cmp}}
                n[f"fq{k}"] = ops.flag_query(FLAGS[name], after, f"fs{k}")
                n[f"fs{k}"] = ops.flag_set(FLAGS[name], f"fg{k}")
                n[f"fg{k}"] = o.give(_target(items[name], name), after)
            n["fish_settle"] = settle(f"fc{zd[0][0]}")  # the tag step's fish number (FishTag) before it is read
            start = "fish_settle"
        graph = f"{PREFIX}{'Bottle' if fish else 'BigPoe'}_{path}"
        o.events.append({"file": d["file"], "flowchart": d["flowchart"], "add_graph": graph, "nodes": n,
                         "start": start})
        o.events.append({"file": d["file"], "flowchart": d["flowchart"], "event": step["event"],
                         "next": f"{graph}_{start}"})
    if poes:
        for k, name in sorted(by_fence.items()):
            notes.append(f"{name}: {items[name]} (fence {k})")


def _fish_ops(o, world, items, notes, settings):
    """Pond: the end of each catch entry goes to the first unclaimed check of the age's list. ZD: the fish names, the
    pouch AI's tag answers and the bottle scene's tag step (the endings are _poe_ops with fish=True). Returns the
    AINB section."""
    child, adult = _pond_lists(settings)
    d = DATA["fish"]["pond"]
    lists = {"child": child, "adult": adult or child}
    o.fish = {"pond": {age: [[n, FLAGS[n]] for n in names] for age, names in lists.items() if names}}
    graphs = {}
    for age in ("child", "adult"):
        names = lists[age]
        if not names:
            continue
        key = tuple(names)
        if key not in graphs:  # without the split both ages claim from the child list (one graph)
            graph = f"{PREFIX}Pond_{age}"
            n = {}
            for i, name in enumerate(names):
                n[f"q{i}"] = ops.flag_query(FLAGS[name], f"q{i + 1}" if i + 1 < len(names) else None, f"s{i}")
                n[f"s{i}"] = ops.flag_set(FLAGS[name], f"g{i}")
                n[f"g{i}"] = o.give(_target(items[name], name), None)
                notes.append(f"{name}: {items[name]} (catch {i + 1} as {'either age' if not adult else age})")
            o.events.append({"file": d["file"], "flowchart": d["flowchart"], "add_graph": graph, "nodes": n,
                             "start": "q0"})
            graphs[key] = graph
        o.events.append({"file": d["file"], "flowchart": d["flowchart"], "event": d["catch"][age]["event"],
                         "next": f"{graphs[key]}_q0"})
    if _remake(settings, "remake_fishsanity") not in ("overworld", "both"):
        return []
    import drops as drop_tools  # tools/rando/drops.py
    zd, b = SPEC["fish"]["zd"], DATA["fish"]["bottle"]
    entries = [{"get_scene": {"name": f"{zd['name']}{k}", "tag": zd["tag_base"] - 1 + k, "ai": zd["ai"]},
                "placements": [{"file": zd["file"], "hash": int(r["hash"]), "actor": "Animal_Fish_Blue"}]}
               for k, r in enumerate(DATA["fish"]["zd"], 1)]
    sec = drop_tools.get_scene_ops(entries)
    o.placements += sec["placements"]
    nodes = {"tag": {"actor": "PouchContentGuestPerformer", "query": "EventQueryCheckTagOnPouchActor",
                     "cases": {v: "none" for v in range(zd["tag_base"])}}}
    nodes["none"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                     "params": {"GameDataName": SCRATCH, "Index": -1, "Value": 0}, "next": ops.at(b["guest"]["next"])}
    for k, r in enumerate(DATA["fish"]["zd"], 1):
        nodes["tag"]["cases"][zd["tag_base"] - 1 + k] = f"f{k}"
        nodes[f"f{k}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                          "params": {"GameDataName": SCRATCH, "Index": -1, "Value": k},
                          "next": ops.at(b["guest"]["next"])}
        notes.append(f"{r['location']}: {items[r['location']]} (child ZD fish at {r['pos']}, named {zd['name']}{k})")
    o.replace(b["file"], b["flowchart"], dict(b["guest"], preds=[["next", b["guest"]["event"], None]]),
              f"{PREFIX}FishTag", nodes, "tag")
    o.fish["zd"] = [[r["location"], FLAGS[r["location"]], k, r["hash"]] for k, r in enumerate(DATA["fish"]["zd"], 1)]
    return sec["ainb"]


def _sign_ops(o, world, items, notes):
    for k, (name, recs) in enumerate(sorted(DATA["signs"].items())):
        if name not in items:
            continue
        s = SPEC["signs"]["locations"][name]
        flag = FLAGS[name] if s.get("flag") == "claimed" else "HavePlayedEvent." + s.get("flag_row", s["rows"][0])
        host = f"{PREFIX}Sign_{k:02d}"
        n, start = _given_once(o, flag, _target(items[name], name), None, host=True)
        o.events.append({"file": GET_FILE, "flowchart": GET_FILE, "add_graph": host, "nodes": n, "start": start})
        for j, r in enumerate(recs):  # every row of the spot (the Sun's Song graves have two) calls the check first
            nodes = {"chk": {"call": f"{GET_FILE}:{host}", "next": ops.at(r["first"]["event"])}}
            o.replace(r["file"], r["flowchart"], r["first"], f"{PREFIX}SignCheck_{k:02d}_{j}", nodes, "chk")
        notes.append(f"{name}: {items[name]} ({', '.join(s['labels'])}; flag {flag})")


def verify_fish(patch_dir, rec, romfs=None):
    """Reads the fishsanity edits back from a built patch (plan "_extras_fish") and returns [problem, ...].
    Pond: each catch entry runs its call and then goes through the age's list in order. If flag k is set it moves
    on to the next one, otherwise it sets it and hands over the item (a call), then ends.
    ZD: the bottle scene asks for the caught actor's tag right after its attention step and keeps 0 or the fish
    number in SCRATCH, then goes on as before. Both endings first compare SCRATCH with each fish number and give once
    by that fish's flag. The fish carry their names and the pouch AI answers each name with its tag
    (drops.verify_get_scene)."""
    import evfl
    import drops as drop_tools
    from romtools import Romfs
    romfs = romfs or drop_tools.DEFAULT_ROMFS
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad = []

    def load(name):
        fc = evfl.Evfl(new.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts[0]
        return fc, {e["name"]: e for e in fc["events"]}

    def what(fc, e):
        if e["type"] in ("subflow", "subflow_switch"):
            return f"{e.get('flowchart') or ''}:{e['entry_point']}"
        a = fc["actors"][e["actor"]]
        return a["name"] + "." + (a["actions"][e["action"]] if e["type"] == "action" else a["queries"][e["query"]])

    def prm(e):
        return {k: v.get("value") for k, v in ((e.get("params") or {}).get("items") or {}).items()}

    def ev(fc, i):
        from evfl_build import is_case_end  # a case's end goes through a do-nothing step (route_end_cases)
        e = fc["events"][i] if i is not None and i != 0xFFFF and i < len(fc["events"]) else None
        return None if is_case_end(e) else e

    def case(e, v):
        return next((c["next"] for c in e.get("cases") or [] if c["value"] == v), None)
    pond = (rec or {}).get("pond") or {}
    if pond:
        d = DATA["fish"]["pond"]
        fc, _ = load(d["file"])
        for age, names in sorted(pond.items()):
            call = ev(fc, fc["entry_points"][{"child": "Step01_CatchFish_Child",
                                               "adult": "Step01_CatchFish_Adult"}[age]]["main"])
            if call is None or what(fc, call) != ":CatchFish_Sub":
                bad.append(f"{d['file']}: the {age} catch no longer starts with its call")
                continue
            e = ev(fc, call.get("next"))
            for k, (name, flag) in enumerate(names):
                if e is None or e["type"] != "switch" or prm(e).get("GameDataName") != flag:
                    bad.append(f"{d['file']}: {age} catch {k + 1} ({name}) doesn't ask {flag}")
                    break
                st = ev(fc, case(e, ops.NO))  # EventQueryIsGameDataBool: case 0 set, 1 not set
                give = ev(fc, st.get("next")) if st else None
                if st is None or what(fc, st) != "GameDataActor.EventTriggerSetGameDataBool" or \
                        prm(st).get("GameDataName") != flag or give is None or \
                        give["type"] not in ("subflow", "subflow_switch") or ev(fc, give.get("next")) is not None:
                    bad.append(f"{d['file']}: {age} catch {k + 1} ({name}) doesn't set {flag}, give, then end")
                e = ev(fc, case(e, ops.YES))
            else:
                if e is not None:
                    bad.append(f"{d['file']}: the {age} list goes on past its {len(names)} checks")
    zd = (rec or {}).get("zd") or []
    if zd:
        b, spec = DATA["fish"]["bottle"], SPEC["fish"]["zd"]
        fc, by = load(b["file"])
        tag = ev(fc, by[b["guest"]["event"]].get("next"))
        if tag is None or what(fc, tag) != "PouchContentGuestPerformer.EventQueryCheckTagOnPouchActor":
            bad.append(f"{b['file']}: {b['guest']['event']} isn't followed by the tag query")
        else:
            want = {v: 0 for v in range(spec["tag_base"])}
            want.update({spec["tag_base"] - 1 + k: k for _, _, k, _ in zd})
            for v, num in sorted(want.items()):
                st = ev(fc, case(tag, v))
                if st is None or what(fc, st) != "GameDataActor.EventTriggerSetGameDataInt" or \
                        prm(st).get("GameDataName") != SCRATCH or prm(st).get("Value") != num or \
                        ev(fc, st.get("next")) is not by[b["guest"]["next"]]:
                    bad.append(f"{b['file']}: tag {v} doesn't keep {num} in {SCRATCH} and go on to "
                               f"{b['guest']['next']}")
        for path, step in sorted(DATA["big_poes"]["ends"].items()):
            e = ev(fc, by[step["event"]].get("next"))
            if e is None or what(fc, e) != "GameSystemActor.EventWait" or (prm(e).get("Frames") or 0) < 2:
                bad.append(f"{b['file']}: the {path} ending doesn't wait for the fish number before comparing it")
            else:
                e = ev(fc, e.get("next"))
            for name, flag, k, _ in zd:
                if e is None or what(fc, e) != "GameDataActor.EventQueryIsGameDataInt" or \
                        prm(e).get("GameDataName") != SCRATCH or prm(e).get("Value") != k:
                    bad.append(f"{b['file']}: the {path} ending doesn't compare fish {k}")
                    break
                q = ev(fc, case(e, 1))
                if q is None or prm(q).get("GameDataName") != flag:
                    bad.append(f"{b['file']}: the {path} ending's fish {k} doesn't ask {flag}")
                e = ev(fc, case(e, 2))
        entries = [{"get_scene": {"name": f"{spec['name']}{k}", "tag": spec["tag_base"] - 1 + k, "ai": spec["ai"]},
                    "placements": [{"file": spec["file"], "hash": h, "actor": "Animal_Fish_Blue"}]}
                   for _, _, k, h in zd]
        bad += drop_tools.verify_get_scene(patch_dir, entries, romfs)
    return bad


# The pond owner's "not enough rupees" line (MiniGame_Fishing:Talk_07), reworded in each language so he asks for
# a rod as well. I wrote these for the project. The speaker tag stays the same as in every vanilla version.
POLE_TEXT = {
    "en": "Uh... Ya gotta come back with enough rupees\nand a fishing rod of your own. I can't let\nfolks fish without 'em!",
    "de": "Ah... Komm wieder, wenn du genug Rubine\nund eine eigene Angel dabeihast. Ohne die\nlass ich niemanden angeln!",
    "es": "Ay, vuelve cuando tengas rupias y una caña\npropia, anda... ¡Sin eso no dejo pescar\na nadie!",
    "es_us": "Ay, vuelve cuando tengas rupias y una caña\npropia, eh... ¡Sin eso no dejo pescar\na nadie!",
    "fr": "Hum... Reviens quand t'auras des rubis et ta\npropre canne à pêche, l'ami. Sans ça, pas\nde pêche !",
    "it": "Acciderbolina! Torna quando avrai abbastanza\nrupie e una canna da pesca tutta tua.\nSenza, niente pesca!",
    "nl": "Eh... Kom maar terug als je genoeg rupees\nén een eigen hengel hebt. Zonder laat ik\nje niet vissen!",
    "pl": "Ech... Wróć, jak będziesz miał mamonę\ni własną wędkę. Bez tego nie ma\nłowienia!",
    "ru": "Ох... Возвращайся, когда у тебя будут\nрупии и своя удочка. Без этого\nрыбачить нельзя!",
    "pt": "Hã... Volte quando tiver rupias suficientes\ne sua própria vara de pescar. Sem isso,\nnada de pescar!",
    "ja": "お金と 自分の つりざお 持って\nまた来てや。{tag:5,0}それが ないと\nつりは させられへんで…",
    "ko": "돈이랑 네 낚싯대를 가지고 다시 와…\n{tag:5,0}그게 없으면 낚시는 못 해…",
    "zh_cn": "带着足够的钱和你自己的钓竿再来吧……\n{tag:5,0}没有这些可没法钓鱼……",
    "zh_tw": "帶著足夠的錢和你自己的釣竿再來吧……\n{tag:5,0}沒有這些可沒辦法釣魚……",
}
LANG_TEXT = {"USen": "en", "EUen": "en", "EUde": "de", "EUes": "es", "USes": "es_us", "EUfr": "fr", "USfr": "fr",
             "EUit": "it", "EUnl": "nl", "EUpl": "pl", "EUru": "ru", "USpt": "pt", "JPja": "ja", "KRko": "ko",
             "CNzh": "zh_cn", "TWzh": "zh_tw"}


def pole_text_ops(world=None, pole_location=None):
    """Talk_07 in every language. With remake_extra_hints "fishing_pole" a second page says where the pole is."""
    from . import _hints_extra as X
    out = []
    for lang, key in sorted(LANG_TEXT.items()):
        body = POLE_TEXT[key]
        markup = "{tag:3,0,120000}" + body
        if pole_location is not None:
            where = X.where_text(X.item_name(POLE, lang), X.location_area(world, pole_location, lang), lang)
            markup += X.PAGE + X.page_markup(where, X.LANG[lang])
        plain = re.sub(r"\{tag:[^}]*\}", "", markup.replace(X.PAGE, "\n"))
        out.append({"lang": lang, "file": "EventFlowMsg/MiniGame_Fishing.msbt", "label": "Talk_07",
                    "markup": markup, "text": plain, "note": "remake_shuffle_fishing_pole"})
    return out


def world_plan(settings, world):
    st = _state.get(id(world))
    pole = _remake(settings, "remake_shuffle_fishing_pole")
    if not (st or {}).get("locs") and not pole:
        return {}  # every feature off: nothing in the plan
    o = Ops()
    o.text = []
    o.fish = None
    notes = []
    locs = (st or {}).get("locs", {})
    items = {n: _item(world, n) for n in locs}
    if any(f == "beggar" for f in locs.values()):
        _beggar_ops(o, world, items, notes)
    if any(f == "fire_gorons" for f in locs.values()):
        _goron_ops(o, world, items, notes)
    if any(f == "hat" for f in locs.values()):
        _hat_ops(o, world, items, notes)
    zd_fish = any(n in SPEC["fish"]["zd"]["locations"] for n in locs)
    poes = any(f == "big_poes" for f in locs.values())
    ainb_ops = _fish_ops(o, world, items, notes, settings) if any(f == "fish" for f in locs.values()) else []
    if poes or zd_fish:
        _poe_ops(o, world, items, notes, poes=poes, fish=zd_fish)
    if any(f == "signs" for f in locs.values()):
        _sign_ops(o, world, items, notes)
    if pole:
        _pole_ops(o, world, notes)
    out = o.plan()
    out.pop("songs_trade_notes", None)
    if ainb_ops:
        out["ainb"] = ainb_ops
    if o.fish:
        out["_extras_fish"] = o.fish  # read back by verify_fish (tools/rando/in_game_check.py)
    if o.text:
        out["text"] = o.text
    out["_notes_extras_npcs"] = notes
    import free_flags  # the flags held for this seed, for the read-back (tools/rando/free_flags.py restore)
    out.update(free_flags.held_plan("extras_npcs"))
    return out
