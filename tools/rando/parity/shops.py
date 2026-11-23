"""Parity plugin for shop shelves (shopsanity and its special-deal prices), Business Scrubs (shuffle_scrubs) and the
expensive merchants (shuffle_expensive_merchants).

The pairing and patch ops are in tools/rando/shops.py (data/rando/shop_map.json).
The logic the remake adds is in data/rando/logic/shops.json, and it's always there whatever the settings.

What OoTR randomizes and the remake can sell:
  - shopsanity on: every slot of the KF, GC, ZD, Market and Kak bazaar and Bombchu shops. A shelf only sells
    items with a Shop_* actor (shields, tunics, ammo, hearts...), of a type its level already places. A special
    deal sells anything else through its own DisplayShop steps (tools/rando/shops.py _deal_ops). There's a
    placeholder on the shelf, the pick is told apart by the shop's talking flag and Shop_SelectItemIndex, and then
    it's paid, given by the shared resolver and sold out. The mask shop stays vanilla, and so do the potion shops
    (one list for Market and Kakariko) unless remake_split_potion_shops is on (below).
  - always (like OoTR): the stick-bag, nut-bag and HF heart-piece scrubs. With shuffle_scrubs it's also every other
    scrub the remake has: the DMC scrub, the Lost Woods grotto's second scrub, the two scrubs by the Deku Theater,
    the three in the Lon Lon Ranch grotto, the Dodongo's Cavern and Jabu-Jabu scrubs (menu scrubs turned into
    one-time sellers, tools/rando/shops.py CONVERTED), and the remake-only Bottom of the Well and Shadow Temple
    scrubs (new OoTR locations). OoTR's other 24 scrubs don't exist in the remake and are out of logic.
    With shuffle_scrubs off, OoTR's vanilla stick/nut sale on a
    remake scrub that sells neither (the theater pair, Dodongo's Cavern, Jabu-Jabu) becomes a logic-free stand-in.
  - shuffle_expensive_merchants: the Wasteland carpet salesman. Medigoron and Granny stay vanilla (no sold flag).
  - shuffle_beans: the songs_trade plugin sells the salesman's item (tools/rando/parity/_songs_trade_child.py).
  - Medigoron, Granny and the mask shop slots: sold by the songs_trade plugin (shop_map.json mode "plugin").
Prices are OoTR's (location.price), and for merchants it's the vanilla OoT price.

Remake settings:
  - remake_split_potion_shops (true/false, default on): the Market and Kakariko potion shops take shopsanity items
    too. It's only off when remake_avoid_vanilla_spots is explicitly set false, and it only matters with
    shopsanity on. The Kakariko keeper gets a list of its own, a new file in its pack with its ShopRef pointing at
    it, like the Kakariko Bazaar keeper has in vanilla (tools/rando/shops.py split_potion_shops). That way each
    shop's 8 slots are kept apart, like OoTR's 16 locations.
  - remake_shuffle_bowling_bombchus (true/false, default on, only off when remake_avoid_vanilla_spots is explicitly
    set false): OoTR never shuffles "Market Bombchu Bowling Bombchus" (ItemPool.py locks its Bombchus (10)). With
    this on, the location joins the fill like any scene location. The bowling's first win gives the seed's item
    once (MiniGame_BombchuBowling Event309, only reached while MiniGame_BombchuBowling_ClearFirstTime is false,
    and Event89 sets it right after). Later wins give the bomb bag, the heart piece and then red rupees as before.
    Off gives exactly OoTR's output.
    Either way, when a bowling prize location holds another item, the keeper's announcement names it in every
    shipped language (tools/rando/parity/_shops_bowling.py).
  - remake_shop_shields_tunics_after_found (false = default, true): Ship of Harkinian's "shop shields and tunics
    only after you've found one" (facts only, no SoH code). A DisplayShop shelf won't sell the Deku Shield, Hylian
    Shield, Goron Tunic or Zora Tunic until the player has found one (IsGet.<item>, which the engine sets on every
    pouch add). New steps in front of DisplayShop NormalFlow's first step compare Shop_SelectItemName with each,
    and if it isn't found yet they play the shop's own sold-out talk (Event118, like vanilla's Blue Fire gate
    does). In logic the four helpers need the found item (Deku_Shield = (Buy_Deku_Shield and 'Deku Shield') or
    Deku_Shield_Drop, Hylian_Shield = Buy_Hylian_Shield and 'Hylian Shield', Goron_Tunic = 'Goron Tunic',
    Zora_Tunic = 'Zora Tunic'), both shields become progression items, and shop shelves don't sell the real four,
    since a shelf holding the only one could never sell it.
"""
import os
import sys

import shops as shop_tools  # tools/rando/shops.py

OWNS = {
    "shopsanity": ("off", "0", "1", "2", "3", "4", "random"),
    "special_deal_price_distribution": ("vanilla", "betavariate", "uniform"),
    "special_deal_price_min": None,
    "special_deal_price_max": None,
    "shuffle_scrubs": ("off", "low", "regular", "random"),
    "shuffle_expensive_merchants": (False, True),
    "shuffle_beans": (False, True),  # the songs_trade plugin sells the bean salesman's item
}
_kept = {}

BOWLING = "Market Bombchu Bowling Bombchus"
GATE = "remake_shop_shields_tunics_after_found"
BOWL = "remake_shuffle_bowling_bombchus"
SPLIT = "remake_split_potion_shops"
REMAKE_SETTINGS = {BOWL: (True, False), GATE: (True, False), SPLIT: (True, False)}
# OoTR item -> the pouch name Shop_SelectItemName holds when a shelf sells it (DisplayShop Event25/Event23 compare
# 'Armor_Adult_Goron' / 'Armor_Adult_Zora'). IsGet.<name> is the Bool the engine sets on every pouch add.
GATED = {"Deku Shield": "Weapon_Shield_Deku", "Hylian Shield": "Weapon_Shield_Hylian",
         "Goron Tunic": "Armor_Adult_Goron", "Zora Tunic": "Armor_Adult_Zora"}
GATE_HELPERS = {"Deku_Shield": "(Buy_Deku_Shield and 'Deku Shield') or Deku_Shield_Drop",
                "Hylian_Shield": "Buy_Hylian_Shield and 'Hylian Shield'",
                "Goron_Tunic": "'Goron Tunic'", "Zora_Tunic": "'Zora Tunic'"}
GATE_FILE, GATE_ENTRY, GATE_STEP, SOLD_OUT = "DisplayShop", "NormalFlow", "Event216", "Event118"
BLUE_FIRE_SLOTS = ("Market Potion Shop Item 2", "Kak Potion Shop Item 5")  # their rules need 'Blue Fire'
_gate = {"on": False, "advancement": {}}


def _remake(settings):
    return getattr(settings, "remake", None) or {}


def shuffle_bowling(settings):
    """remake_shuffle_bowling_bombchus, on by default. It's only off when remake_avoid_vanilla_spots is explicitly
    set false (that setting defaults to off, this one doesn't)."""
    r = _remake(settings)
    return bool(r.get(BOWL, r.get("remake_avoid_vanilla_spots", True)))


def gate_on(settings):
    return bool(_remake(settings).get(GATE, False))


def split_on(settings):
    """remake_split_potion_shops, on by default and off when remake_avoid_vanilla_spots is explicitly set false.
    Only with shopsanity on."""
    r = _remake(settings)
    return bool(r.get(SPLIT, r.get("remake_avoid_vanilla_spots", True))) and settings.shopsanity != "off"


def check_settings(settings):
    out = []
    for k, ok in REMAKE_SETTINGS.items():
        v = _remake(settings).get(k)
        if v is not None and v not in ok:
            out.append(f"{k} = {v!r}: must be true or false")
    return out


def untested(settings):
    out = []
    if shuffle_bowling(settings):
        out.append(f"shops: {BOWL} - the bowling's first prize gives the seed's item (in-place give, Event309)")
    if gate_on(settings):
        out.append(f"shops: {GATE} - shelves refuse shields and tunics until one is found (DisplayShop sold-out talk)")
    if split_on(settings):
        out.append(f"shops: {SPLIT} - a new list file inside Npc_Hylia_020_Shop_Adult's pack (new size-table entry) "
                   f"and the Kakariko keeper's ShopRef")
    return out


def before_build(settings):
    """For remake_shop_shields_tunics_after_found, puts in the logic helpers and the two shields' progression flag
    through OoTR's logic reader. The reader hook is installed once and reads the setting of the seed being built."""
    shop_tools.split_potion_shops(split_on(settings))
    on = gate_on(settings)
    _gate["on"] = on
    from Item import ItemInfo
    for name in ("Deku Shield", "Hylian Shield"):
        info = ItemInfo.items[name]
        _gate["advancement"].setdefault(name, info.advancement)
        info.advancement = True if on else _gate["advancement"][name]
    import RuleParser
    import Utils
    import World
    if getattr(Utils.read_logic_file, "remake_shop_gate", False):
        return
    inner = Utils.read_logic_file

    def read(path):
        data = inner(path)
        if _gate["on"] and os.path.basename(path) == "LogicHelpers.json":
            data = dict(data, **GATE_HELPERS)
        return data
    read.remake = True
    read.remake_shop_gate = True
    for module in (Utils, RuleParser, World):
        module.read_logic_file = read


def _active(settings):
    """OoTR locations this plugin patches for these settings (its setting on, a remake edit point)."""
    out = set()
    for name, loc in shop_tools.shop_map()["locations"].items():
        if loc["mode"] != "full":
            continue
        if loc["kind"] == "shop" and settings.shopsanity == "off":
            continue
        setting = (loc["edit"] or {}).get("setting")
        if setting == "shuffle_scrubs" and settings.shuffle_scrubs == "off":
            continue
        if setting == "shuffle_expensive_merchants" and not settings.shuffle_expensive_merchants:
            continue
        out.add(name)
    return out


def keep_locations(world, settings):
    """The shop, scrub and merchant locations patched for these settings, plus the shop slots and scrubs this plugin
    locks itself in before_fill (the shared potion list, scrubs with no one-time sale). OoTR's pool holds
    different items for those than the generator's vanilla lock would take."""
    names = shop_tools.shop_map()["locations"]
    active = {n for n in _active(settings) if _empty(world, n)}
    own_lock = {n for n, v in names.items() if v["mode"] == "vanilla" and _empty(world, n)
                and ((v["kind"] == "shop" and settings.shopsanity != "off")
                     or (v["kind"] == "scrub" and settings.shuffle_scrubs != "off"))}
    _kept[id(world)] = active
    import sys
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "CALL_LOCATIONS"):  # These sales can call a dungeon item's credit entry.
        dg.CALL_LOCATIONS.update(n for n in active if names[n]["kind"] in ("scrub", "merchant"))  # dungeon_marker
        dg.CALL_LOCATIONS.update(deal_locations(world))  # shop_tools.deal_give handles special deals
    return active | own_lock


def deal_locations(world):
    """The special deals this plugin patches (OoTR world.shop_prices among its active shop slots). Their steps give
    any item through the shared resolver, calls included, so call-only items aren't refused there (songs_trade
    no_call_locations)."""
    names = shop_tools.shop_map()["locations"]
    prices = getattr(world, "shop_prices", None) or {}
    return {n for n in _kept.get(id(world), ()) if names[n]["kind"] == "shop" and n in prices
            and (names[n]["edit"] or {}).get("shop") in shop_tools.TALKING}


def _empty(world, name):
    try:
        loc = world.get_location(name)
    except KeyError:
        return False
    return loc.item is None and not loc.locked


def before_fill(world, settings):
    """Locks the vanilla shop slots and scrubs with their pool items, only allows sellable items in the patched ones,
    and makes OoTR's last junk pass respect that (shop_tools.install_fill_guard)."""
    from Item import ItemFactory
    if shuffle_bowling(settings):
        _unlock_bowling(world)
    shop_tools.lock_vanilla(world, ItemFactory)
    shop_tools.install_fill_guard()
    if settings.shuffle_scrubs == "off":
        _stand_ins(world, ItemFactory)
    for name in sorted(_kept.get(id(world), ())):
        loc = world.get_location(name)
        if loc.locked or loc.item is not None:
            continue
        prev = loc.item_rule
        entry = shop_tools.shop_map()["locations"][name]
        gate = gate_on(settings) and entry["kind"] == "shop"
        # the potion keepers refuse Blue Fire until you've had it once (data/rando/logic/shops.json), so only their
        # two vanilla Blue Fire slots, whose rules need 'Blue Fire', may sell it
        no_blue = ((entry.get("edit") or {}).get("shop") in shop_tools.POTION_SHOPS
                   and name not in BLUE_FIRE_SLOTS)
        loc.item_rule = (lambda location, item, prev=prev, gate=gate, no_blue=no_blue:
                         shop_tools.item_allowed(location.name, item.name, shop_tools.NEW_TYPES,
                                                 shop_tools.is_deal(location))
                         and not (gate and item.name in GATED) and not (no_blue and item.name == "Buy Blue Fire")
                         and prev(location, item))


def _unlock_bowling(world):
    """OoTR placed and locked the bowling's Bombchus (10) because ItemPool.py never shuffles it. This puts the item
    back in the pool and frees the location, which the generator patches as a scene location
    (config/rando_locations.json)."""
    try:
        loc = world.get_location(BOWLING)
    except KeyError:
        return
    if loc.item is None or not loc.locked:
        return
    item = loc.item
    loc.item, item.location, loc.locked = None, None, False
    world.itempool.append(item)


def gate_plan():
    """DisplayShop steps in front of NormalFlow's first step. For each gated item, if the shelf sells it and it was
    never found, they play the shop's own sold-out talk (Event118, which goes back to the shelves)."""
    names = sorted(GATED.values())
    nodes = {}
    for i, name in enumerate(names):
        nxt = f"is{i + 1}" if i + 1 < len(names) else f"@{GATE_STEP}"
        nodes[f"is{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                           "params": {"GameDataName": "Shop_SelectItemName", "Index": -1, "Value": name},
                           "cases": {0: f"got{i}", 1: nxt}}
        nodes[f"got{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                            "params": {"GameDataName": f"IsGet.{name}", "Index": -1},
                            "cases": {0: f"@{GATE_STEP}", 1: f"@{SOLD_OUT}"}}
    graph = "Rando_ShopGate"
    return {"events": [
        {"file": GATE_FILE, "flowchart": GATE_FILE, "add_graph": graph, "nodes": nodes, "start": "is0"},
        {"file": GATE_FILE, "flowchart": GATE_FILE, "entry": GATE_ENTRY, "next": f"{graph}_is0"}]}


def _gate_defaults(settings, world):
    """Shields and tunics a new file starts with count as found (starting items are added without the get event, so
    IsGet may not be set by them)."""
    names = set(getattr(settings, "starting_items", None) or {})
    names |= set(getattr(world, "randomized_starting_items", None) or {})
    for setting in ("starting_equipment", "starting_inventory"):
        names |= set(getattr(settings, setting, None) or ())
    alias = {"deku_shield": "Deku Shield", "hylian_shield": "Hylian Shield", "goron_tunic": "Goron Tunic",
             "zora_tunic": "Zora Tunic"}
    found = {alias.get(n, n) for n in names}
    return {f"IsGet.{GATED[n]}": True for n in sorted(found & set(GATED))}


def _stand_ins(world, ItemFactory):
    """With shuffle_scrubs off OoTR places each scrub's vanilla "Buy" item itself. Where the remake scrub sells
    something else and OoTR's item counts in logic (Buy Deku Stick (1) -> Sticks, Buy Deku Nut (5) -> Nuts), logic
    would be looser than the game. So we put the edit's logic-free stand-in there instead, and the remake's own menu
    stays."""
    for name, v in shop_tools.shop_map()["locations"].items():
        stand_in = (v.get("edit") or {}).get("vanilla_stand_in")
        if not stand_in:
            continue
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.item is not None and loc.item.name == v["vanilla"] and loc.item.advancement:
            world.push_item(loc, ItemFactory(stand_in, world))
            loc.locked = True


def after_fill(world, settings):
    """If the generator calls it, swaps any unsellable junk out of patched slots. The fill guard should leave none."""
    return shop_tools.repair_special_deals(world)


def world_plan(settings, world):
    out = _world_plan(settings, world)
    from . import _shops_bowling
    ops, notes = _shops_bowling.text_ops(world)  # the bowling keeper names the seed's prizes (every language)
    if ops:
        out["text"] = out.get("text", []) + ops
        out["_notes_bowling_text"] = notes
    if gate_on(settings):
        gp = gate_plan()["events"]
        deal = next((ev for ev in out.get("events", []) if ev.get("add_graph") == shop_tools.DEAL_GRAPH), None)
        if deal is None:
            out["events"] = out.get("events", []) + gp
        else:  # both in front of NormalFlow: the deal steps fall through to the gate's, in one graph
            gate = {f"gate_{lab}": {k: ({c: (f"gate_{x}" if isinstance(x, str) and not x.startswith("@") else x)
                                         for c, x in v.items()} if k == "cases" else v) for k, v in n.items()}
                    for lab, n in gp[0]["nodes"].items()}
            deal["nodes"] = {lab: shop_tools._route(n, "@" + shop_tools.DEAL_NEXT, "gate_" + gp[0]["start"])
                             for lab, n in deal["nodes"].items()}
            deal["nodes"].update(gate)
        defaults = _gate_defaults(settings, world)
        if defaults:
            old = out.get("gamedata")
            out["gamedata"] = ([] if old is None else [old] if isinstance(old, dict) else list(old)) + [
                {"defaults": defaults}]
        out["_notes_shop_gate"] = [f"{GATE}: shelves refuse {', '.join(sorted(GATED))} until one is found"]
    return out


def _world_plan(settings, world):
    names = _kept.get(id(world))
    if names is None:
        names = {n for n in _active(settings)}
    assignments, looks, majors = {}, {}, set()
    for name in sorted(names):
        loc = world.get_location(name)
        if loc.item is not None:
            assignments[name] = (loc.item.name, loc.price)
            if loc.item.advancement or loc.item.priority:
                majors.add(loc.item.name)  # a special deal shows it with a major look (shop_tools.deal_look)
            if loc.item.name == "Ice Trap" and getattr(loc.item, "looks_like_item", None) is not None:
                looks[name] = loc.item.looks_like_item.name  # OoTR's disguise for it
    if not assignments:
        return {}
    deals = deal_locations(world)
    ice_calls = {}
    shop_locs = shop_tools.shop_map()["locations"]
    for name, (item, _p) in assignments.items():
        # Deals, scrubs and the carpet salesman play the trap the chests plugin picked for this location.
        if item == "Ice Trap" and (name in deals or (shop_locs.get(name) or {}).get("kind") in ("scrub", "merchant")):
            ch = sys.modules.get("parity.chests")
            call = ch.trap_call(world, name) if ch is not None and hasattr(ch, "trap_call") else None
            if call:
                ice_calls[name] = call
    plan = shop_tools.plan_ops(assignments, appearance=getattr(settings, "ice_trap_appearance", "anything"),
                               looks_like=looks, deals=deals, majors=majors, ice_calls=ice_calls)
    notes = plan.pop("_notes")
    out = {k: v for k, v in plan.items() if v}
    if notes:
        out["_notes_shops"] = notes
    return out
