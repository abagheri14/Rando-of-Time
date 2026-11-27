"""Parity plugin for price modes on shop special deals, Business Scrubs and merchants, from Ship of Harkinian (SoH)
and the 3DS randomizer (OoT3DR). OoTR already has special-deal prices (special_deal_price_distribution/min/max)
and scrub prices (shuffle_scrubs low/regular/random). SoH adds price modes per kind and OoT3DR adds wallet-capped
shop prices. Every setting is a remake setting and off by default ("ootr" means OoTR's prices). With all of them
off the plugin changes nothing: no hook runs, no random number is drawn, no plan section.

Facts used (SoH 3drando/shops.cpp and OoT3DR source/shops.cpp, read as a reference, no code copied):
  - cheap_balanced: a Beta(1, 2) draw scaled to 20 steps of 5 rupees (0-95, mean ~31)   SoH Cheap Balanced,
    OoT3DR's random scrub price
  - balanced: a Beta(1.5, 2) draw scaled to 60 steps of 5 (0-295, mean ~126)            SoH Balanced, OoT3DR Random
  - fixed / range: one price / uniform between two prices                                SoH Fixed / Range
  - wallet: a wallet tier drawn by weight (none 0, child 1-99, adult 100-200, giant 201-500)   SoH Set By Wallet
  - affordable: 10 rupees each                                                           OoT3DR Affordable
  - child_wallet / adult_wallet / giant_wallet: the Beta(1.5, 2) shape over 0-99 / 0-200 / 0-500 in steps of 5
                                                                                         OoT3DR wallet caps
  - remake_<kind>_prices_affordable: each price drops to the cheapest of its wallet tier (5, 100, 205)
                                                                                         SoH Affordable
SoH's tycoon tier (501-998) needs a fourth wallet the remake doesn't have. The remake has the starting wallet and
two upgrades, and OoTR asks for a third Progressive Wallet above 500, which has no remake tier. So every price
here is 0-500.

How each kind is priced. The remake writes location.price and logic follows the price the same way OoTR's does.
  - shop special deals (shopsanity): OoTR's World.new_shop_price, for the shelf slots the remake patches.
    Rules.create_shop_rule turns the price into its wallet rule.
  - Business Scrubs: after OoTR's World.set_scrub_prices, each scrub the remake patches gets a price of its own
    (SoH prices every scrub separately, OoTR prices by item type). Same wallet rule.
  - merchants: the Wasteland carpet salesman, Medigoron and Granny with shuffle_expensive_merchants, and the bean
    salesman with shuffle_beans. OoTR doesn't give them a price, so they keep the vanilla one. Here each one gets a
    price, and the Progressive_Wallet in its rule becomes the count that price needs. The shops plugin prices the
    carpet salesman from location.price. The others get in-place edits here: Medigoron (Event29 SimpleShop_Price,
    Event11 Price/MinusRupeeValue), the bean salesman (Event10 SellBeans Price) and Granny (the Event11 rupee
    check, the songs_trade plugin's copy of Event179, and her offer Talk_101, whose "100" is literal text in every
    language).
  - Great Fairies (OOTRR Great Fairy Prices): the remake's fairies ask an offering (25, 50, 100, 200, 300, 500). Each
    one's scene checks it (EventQueryHasRuppe Value) and takes it (Value -price), and her lines show it through a
    save-data number (GreatFairy_Price1-6, not saved, so its default is what she says). Logic follows the price in
    the remake's wallets (fairy_wallets).
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))

KINDS = ("shop", "scrub", "merchant", "fairy")
MODES = ("ootr", "vanilla", "cheap_balanced", "balanced", "fixed", "range", "wallet", "affordable", "child_wallet",
         "adult_wallet", "giant_wallet")
MAX_PRICE = 500
WEIGHTS = ("none", "child", "adult", "giant")
CAPS = {"child_wallet": 99, "adult_wallet": 200, "giant_wallet": 500}


def _keys(kind):
    return {"mode": f"remake_{kind}_prices", "fixed": f"remake_{kind}_price_fixed",
            "range_1": f"remake_{kind}_price_range_1", "range_2": f"remake_{kind}_price_range_2",
            "affordable": f"remake_{kind}_prices_affordable",
            **{f"weight_{w}": f"remake_{kind}_price_weight_{w}" for w in WEIGHTS}}


REMAKE_SETTINGS, REMAKE_DEFAULTS = {}, {}
for _k in KINDS:
    _n = _keys(_k)
    REMAKE_SETTINGS[_n["mode"]] = MODES
    REMAKE_DEFAULTS[_n["mode"]] = "ootr"
    REMAKE_SETTINGS[_n["affordable"]] = (False, True)
    REMAKE_DEFAULTS[_n["affordable"]] = False
    for _p, _d in (("fixed", 50), ("range_1", 50), ("range_2", 500)):
        REMAKE_SETTINGS[_n[_p]] = None  # 0-500 rupees, checked in check_settings
        REMAKE_DEFAULTS[_n[_p]] = _d
    for _w in WEIGHTS:
        REMAKE_SETTINGS[_n[f"weight_{_w}"]] = None  # 0-100, checked in check_settings
        REMAKE_DEFAULTS[_n[f"weight_{_w}"]] = 10

# Each merchant's shuffle setting. The shops plugin prices the carpet salesman from location.price.
MERCHANTS = {
    "Wasteland Bombchu Salesman": "shuffle_expensive_merchants",
    "GC Medigoron": "shuffle_expensive_merchants",
    "Kak Granny Buy Blue Potion": "shuffle_expensive_merchants",
    "ZR Magic Bean Salesman": "shuffle_beans",
}
GRANNY = "Kak Granny Buy Blue Potion"
# In-place price edits (scene file, event, parameter, vanilla value, sign). The flowchart shares the file name.
EDITS = {
    "GC Medigoron": [("Npc_Goron_Medigoron_Adult", "Event29", "Value", 200, 1),
                     ("Npc_Goron_Medigoron_Adult", "Event11", "Price", 200, 1),
                     ("Npc_Goron_Medigoron_Adult", "Event11", "MinusRupeeValue", -200, -1)],
    "ZR Magic Bean Salesman": [("Npc_Hylia_047_Child", "Event10", "Price", 60, 1)],
    GRANNY: [("Npc_Hylia_053_Adult", "Event11", "Value", 100, 1)],  # her "has 100 rupees?" check
}
# Granny's sale (songs_trade _granny_ops) runs graph RandoST_Granny from node "price" (a copy of Event179 with
# SimpleShop_Price = 100) to node "pay", which takes SimpleShop_Price. make_patch checks numeric edits against the
# file before new graphs exist, so the copy can't be edited. Instead a one-step graph of ours sets the new price
# between the two, which works because routing ops run after every graph is built.
GRANNY_FILE, GRANNY_FROM, GRANNY_TO = "Npc_Hylia_053_Adult", "RandoST_Granny_price", "RandoST_Granny_pay"
GRANNY_GRAPH = "Rando_Prices_Granny"
GRANNY_TEXT = ("EventFlowMsg/Npc_Hylia_053_Adult.msbt", "Talk_101")
GRANNY_PRICE_MARK = "{tag:0,3,0000}100"  # her price, coloured, in every language's offer
HINTS_EXTRA = os.path.join(HERE, "data", "rando", "hints_extra.json")
# The Great Fairies' offerings: location -> (scene file = flowchart, the rupee check, the payment, the save-data number
# her lines show, the vanilla price)
FAIRIES = {
    "DMT Great Fairy Reward": ("Dm_FairyFountain_Din", "Event69", "Event123", "GreatFairy_Price1", 25),
    "HC Great Fairy Reward": ("Dm_FairyFountain_Power", "Event14", "Event29", "GreatFairy_Price2", 50),
    "ZF Great Fairy Reward": ("Dm_FairyFountain_Frore", "Event17", "Event24", "GreatFairy_Price3", 100),
    "DMC Great Fairy Reward": ("Dm_FairyFountain_Wisdom", "Event17", "Event23", "GreatFairy_Price4", 200),
    "Colossus Great Fairy Reward": ("Dm_FairyFountain_Nayru", "Event17", "Event23", "GreatFairy_Price5", 300),
    "OGC Great Fairy Reward": ("Dm_FairyFountain_Courage", "Event18", "Event24", "GreatFairy_Price6", 500),
}
WALLET_CAPS = (200, 500, 1000)  # the remake's wallets: the one you start with, then each Progressive Wallet

_state = {}


def _remake(settings):
    return getattr(settings, "remake", None) or {}


def value(settings, key):
    return _remake(settings).get(key, REMAKE_DEFAULTS[key])


def mode(settings, kind):
    return value(settings, _keys(kind)["mode"])


def active(settings):
    return {k: value(settings, k) for k in REMAKE_SETTINGS if value(settings, k) != REMAKE_DEFAULTS[k]}


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


# Settings
def check_settings(settings):
    out = []
    remake = _remake(settings)
    for k, v in remake.items():
        if k not in REMAKE_SETTINGS:
            continue
        ok = REMAKE_SETTINGS[k]
        if ok is not None:
            if v not in ok or isinstance(v, bool) != isinstance(ok[0], bool):
                out.append(f"{k} = {v!r}: extras_prices can make {', '.join(map(repr, ok))}")
        elif "_weight_" in k:
            if not _int(v) or not 0 <= v <= 100:
                out.append(f"{k} = {v!r}: a weight from 0 to 100")
        elif not _int(v) or not 0 <= v <= MAX_PRICE:
            out.append(f"{k} = {v!r}: a price from 0 to {MAX_PRICE} rupees (the remake has no tycoon's wallet)")
    for kind in KINDS:
        m = mode(settings, kind)
        if m == "ootr":
            continue
        if kind == "shop" and getattr(settings, "shopsanity", "off") == "off":
            out.append(f"remake_shop_prices = {m!r}: shops sell no special deals without shopsanity")
        if kind == "merchant" and not (getattr(settings, "shuffle_expensive_merchants", False)
                                       or getattr(settings, "shuffle_beans", False)):
            out.append(f"remake_merchant_prices = {m!r}: no merchant sells a shuffled item without "
                       f"shuffle_expensive_merchants or shuffle_beans")
    if (mode(settings, "merchant") != "ootr" and getattr(settings, "shuffle_expensive_merchants", False)
            and "merchants" in (remake.get("remake_extra_hints") or [])):
        out.append("remake_merchant_prices with remake_extra_hints 'merchants': that hint rewrites Granny's offer "
                   "with her vanilla 100-rupee price (tools/rando/parity/_hints_extra.py SPECIAL_PRICE); leave one off")
    return out


def untested(settings):
    out = []
    for kind in KINDS:
        m = mode(settings, kind)
        if m != "ootr":
            extra = " (affordable)" if value(settings, _keys(kind)["affordable"]) else ""
            out.append(f"extras_prices: remake_{kind}_prices {m}{extra}")
    if mode(settings, "fairy") != "ootr":
        out.append("extras_prices: Great Fairy offerings (each fountain's rupee check and payment, and the save-data "
                   "number her lines show, GreatFairy_Price1-6)")
    if mode(settings, "merchant") != "ootr":
        out.append("extras_prices: merchant price edits (Medigoron Event29/Event11, bean salesman Event10, Granny "
                   "Event11 + her sale's copied price step + Talk_101 text)")
    return out


# Prices
def _beta_steps(rng, a, steps):
    """A Beta(a, 2) draw on `steps` steps of 5 rupees: 0, 5, ..., 5 * (steps - 1)."""
    return min(int(rng.betavariate(a, 2) * steps), steps - 1) * 5


def _affordable(p):
    """SoH's Affordable. The cheapest price in the wallet tier that `p` needs (no tycoon tier, see MAX_PRICE)."""
    if p > 200:
        return 205
    if p > 99:
        return 100
    if p > 0:
        return 5
    return 0


def new_price(settings, kind, vanilla, rng=random):
    """A price for one location of `kind` under its mode. `vanilla` is that location's vanilla price."""
    n = _keys(kind)
    m = value(settings, n["mode"])
    if m == "vanilla":
        p = vanilla
    elif m == "cheap_balanced":
        p = _beta_steps(rng, 1, 20)
    elif m == "balanced":
        p = _beta_steps(rng, 1.5, 60)
    elif m == "fixed":
        return value(settings, n["fixed"])  # SoH: Affordable doesn't apply to a fixed price
    elif m == "range":
        a, b = sorted((value(settings, n["range_1"]), value(settings, n["range_2"])))
        p = rng.randint(a, b)
    elif m == "wallet":
        w = [value(settings, n[f"weight_{x}"]) for x in WEIGHTS]
        total = sum(w)
        if not total:
            p = rng.randint(0, MAX_PRICE)
        else:
            pick = rng.randint(1, total)
            tier = 0
            while pick > w[tier]:
                pick -= w[tier]
                tier += 1
            p = (0, rng.randint(1, 99), rng.randint(100, 200), rng.randint(201, 500))[tier]
    elif m == "affordable":
        return 10
    elif m in CAPS:
        p = _beta_steps(rng, 1.5, CAPS[m] // 5 + 1)
    else:
        raise ValueError(f"extras_prices: no mode {m!r}")
    p = min(max(int(p), 0), MAX_PRICE)
    return _affordable(p) if value(settings, n["affordable"]) else p


def _patched(settings, kind):
    """OoTR locations of `kind` ("shop", "scrub", "merchant") whose price the remake's patch writes."""
    from parity import shops as shop_plugin
    import shops as shop_tools
    table = shop_tools.shop_map()["locations"]
    return {n for n in shop_plugin._active(settings) if table[n]["kind"] == kind}


def _wallets(price):
    """OoTR's wallet count for a price (Rules.create_shop_rule)."""
    return 0 if price <= 99 else 1 if price <= 200 else 2 if price <= 500 else 3


def fairy_wallets(price, child_wallet=False):
    """Progressive Wallets a Great Fairy's offering needs, in the remake's wallets (the one you start with holds 200,
    then 500 and 1000). With remake_shuffle_child_wallet you start with none and the first is the 200 one."""
    if price <= 0:
        return 0
    return next(i for i, cap in enumerate(WALLET_CAPS) if price <= cap) + (1 if child_wallet else 0)


def _set_wallets(world, loc, n):
    """The location's rule with `n` Progressive Wallets in place of a bare Progressive_Wallet (or added)."""
    need = "True" if n == 0 else f"(Progressive_Wallet, {n})"
    rule = loc.rule_string or "True"
    new, k = re.subn(r"\bProgressive_Wallet\b(?!\s*,)", need, rule)
    if not k and n:
        new = f"({rule}) and {need}"
    if new != rule:
        loc.rule_string = new
        world.parser.parse_spot_rule(loc)


# OoTR hooks (installed once per process)
def _install():
    import World
    W = World.World
    if getattr(W.new_shop_price, "remake_prices", False):
        return
    shop_price, scrub_prices = W.new_shop_price, W.set_scrub_prices

    def new_shop_price(self, location, _original=shop_price):
        # OoTR calls this for every special deal of a shopsanity shop (World.random_shop_prices). It calls it again
        # in World.push_item for any priced location that gets a cheap refill, the "obvious scam" reroll that keeps the
        # lower of the two prices. So our priced scrubs and merchants come through here too.
        st = _state.get("settings")
        if st is None:
            return _original(self, location)
        if location.name in _state["merchants"] or location.name in _state["fairies"]:
            return location.price  # no reroll: the rule was set for this price (keep_locations)
        kind = "scrub" if location.name in _state["scrubs"] else "shop" if location.name in _state["shops"] else None
        if kind is None:
            return _original(self, location)
        vanilla = location.price
        if vanilla is None:
            from Item import ItemInfo
            vanilla = ItemInfo.items[location.vanilla_item].price
        return new_price(st, kind, vanilla)

    def set_scrub_prices(self, _original=scrub_prices):
        _original(self)
        st = _state.get("settings")
        if st is None or mode(st, "scrub") == "ootr":
            return
        from LocationList import business_scrubs
        default = {item: price for item, price, _t, _r in business_scrubs}
        for location in sorted(self.get_locations(), key=lambda x: x.name):
            if location.type not in ("Scrub", "GrottoScrub") or location.name not in _state["scrubs"]:
                continue
            p = new_price(st, "scrub", default.get(location.default, location.price or 0))
            location.price = p
            if location.item is not None:
                location.item.price = p

    new_shop_price.remake_prices = True
    W.new_shop_price = new_shop_price
    W.set_scrub_prices = set_scrub_prices


def before_build(settings):
    if not active(settings):
        _state.clear()
        return
    _install()
    _state.clear()
    _state.update(settings=settings, merchants=set(), fairies=set(),
                  shops=_patched(settings, "shop") if mode(settings, "shop") != "ootr" else set(),
                  scrubs=_patched(settings, "scrub") if mode(settings, "scrub") != "ootr" else set())


def keep_locations(world, settings):
    """Puts a price on each merchant the remake sells a shuffled item at, and on each Great Fairy, and swaps the
    Progressive_Wallet in its rule for the wallet count that price needs. This runs before any plugin's before_fill
    adds more rules."""
    if not _state:
        return set()
    if mode(settings, "fairy") != "ootr":
        child = bool(_remake(settings).get("remake_shuffle_child_wallet"))
        for name, (_f, _c, _p, _row, vanilla) in sorted(FAIRIES.items()):
            try:
                loc = world.get_location(name)
            except KeyError:
                continue
            loc.price = new_price(settings, "fairy", vanilla)
            _set_wallets(world, loc, fairy_wallets(loc.price, child))
            _state["fairies"].add(name)
    if mode(settings, "merchant") == "ootr":
        return set()
    import shops as shop_tools
    vanilla = {n: v["price"] for n, v in shop_tools.MERCHANTS.items()}  # the vanilla OoT prices OoTR sells at
    for name, setting in sorted(MERCHANTS.items()):
        if not getattr(settings, setting, False):
            continue
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        p = new_price(settings, "merchant", vanilla[name])
        loc.price = p
        _set_wallets(world, loc, _wallets(p))
        _state["merchants"].add(name)
    return set()


# Patch plan
def _granny_text(price):
    """Granny's offer with her new price, every language (vanilla markup from data/rando/hints_extra.json)."""
    msgs = json.load(open(HINTS_EXTRA, encoding="utf-8"))["messages"]
    per_lang = msgs[f"{GRANNY_TEXT[0]}:{GRANNY_TEXT[1]}"]
    ops = []
    for lang, markup in sorted(per_lang.items()):
        if markup.count(GRANNY_PRICE_MARK) != 1:
            raise RuntimeError(f"extras_prices: {lang} {GRANNY_TEXT[1]} doesn't show her price as "
                               f"{GRANNY_PRICE_MARK!r} once")
        ops.append({"lang": lang, "file": GRANNY_TEXT[0], "label": GRANNY_TEXT[1],
                    "markup": markup.replace(GRANNY_PRICE_MARK, "{tag:0,3,0000}" + str(price)),
                    "note": f"extras_prices: Granny's offer at {price} rupees"})
    return ops


def world_plan(settings, world):
    """The final prices, read from the world after OoTR's rerolls and the no-vanilla swaps (those carry prices along
    with items between special-deal slots). The shops and songs_trade plugins write location.price."""
    if not _state:
        return {}
    prices = {}
    for name in sorted(_state["shops"] | _state["scrubs"] | _state["merchants"] | _state["fairies"]):
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.price is not None and loc.item is not None:
            prices[name] = loc.price
    if not prices:
        return {}
    plan = {"_extras_prices": {"prices": prices, "edits": []}, "_verify_plugins": ["extras_prices"]}
    events, text = [], []
    for name, edits in sorted(EDITS.items()):
        if name not in prices:
            continue
        p = prices[name]
        for file, event, param, vanilla, sign in edits:
            v = sign * p
            if v == vanilla:
                continue
            events.append({"file": file, "flowchart": file, "event": event, "param": param, "value": v,
                           "note": f"extras_prices: {name} at {p} rupees"})
            plan["_extras_prices"]["edits"].append([file, event, param, v])
    defaults = {}
    for name, (file, check, pay, row, vanilla) in sorted(FAIRIES.items()):  # her check, her payment, her lines
        p = prices.get(name) if name in _state["fairies"] else None
        if p is None or p == vanilla:
            continue
        for event, v in ((check, p), (pay, -p)):
            events.append({"file": file, "flowchart": file, "event": event, "param": "Value", "value": v,
                           "note": f"extras_prices: {name} at {p} rupees"})
            plan["_extras_prices"]["edits"].append([file, event, "Value", v])
        defaults[row] = p
    if defaults:
        plan["gamedata"] = {"defaults": defaults}
        plan["_extras_prices"]["defaults"] = defaults
    if GRANNY in prices and prices[GRANNY] != 100:
        p = prices[GRANNY]
        f = {"file": GRANNY_FILE, "flowchart": GRANNY_FILE}
        events.append(dict(f, add_graph=GRANNY_GRAPH, start="set", nodes={"set": {
            "actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
            "params": {"Index": -1, "GameDataName": "SimpleShop_Price", "Value": p}, "next": None}},
            note=f"extras_prices: Granny's sale at {p} rupees"))
        events.append(dict(f, event=GRANNY_FROM, next=f"{GRANNY_GRAPH}_set"))
        events.append(dict(f, event=f"{GRANNY_GRAPH}_set", next=GRANNY_TO))
        plan["_extras_prices"]["granny"] = [GRANNY_FILE, GRANNY_FROM, f"{GRANNY_GRAPH}_set", GRANNY_TO, p]
        text += _granny_text(p)
    if events:
        plan["events"] = events
    if text:
        plan["text"] = text
    return plan


# Read-back (tools/rando/in_game_check.py)
def verify(patch, plan, romfs):
    """Reads back every price this plugin set. The merchants' event parameters come from the built scene files, and
    the shop and scrub prices from the plan ops that carry them (the shops plugin's notes,
    "<location>: ... for <price>")."""
    from romtools import Romfs
    from evfl import Evfl
    sec = plan.get("_extras_prices") or {}
    problems = []
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    flows = {}
    for file, event, param, want in sec.get("edits", []):
        if file not in flows:
            flows[file] = None
            for path in (f"Event/EventFlow/{file}.110.bfevfl.zs", f"Event/EventFlow/{file}.bfevfl.zs"):
                try:  # the numbered copy is the one the game reads (make_patch edits every copy)
                    flows[file] = Evfl(fs.read(path))
                    break
                except (OSError, KeyError):
                    continue
        ev = flows[file]
        if ev is None:
            problems.append(f"extras_prices: no scene file {file}")
            continue
        fc = next((x for x in ev.flowcharts if x["name"] == file), None)
        e = next((x for x in (fc or {}).get("events", []) if x["name"] == event), None)
        if e is None:
            problems.append(f"extras_prices: {file} has no step {event}")
            continue
        node = e.get("params")
        for k in param.split("."):
            node = (node or {}).get("items", {}).get(k) if (node or {}).get("type") == "container" else None
        got = (node or {}).get("value")
        if got != want:
            problems.append(f"extras_prices: {file} {event} {param} = {got!r}, planned {want!r}")
    if sec.get("granny"):  # her sale: songs_trade's price step -> ours (SimpleShop_Price = p) -> songs_trade's pay
        file, src, mid, dst, want = sec["granny"]
        try:
            fc = next(x for x in Evfl(fs.read(f"Event/EventFlow/{file}.bfevfl.zs")).flowcharts if x["name"] == file)
            by = {e["name"]: e for e in fc["events"]}
            a, b, c = by.get(src), by.get(mid), by.get(dst)
            got = ((b or {}).get("params") or {}).get("items", {}).get("Value", {}).get("value")
            if None in (a, b, c) or a.get("next") != b["idx"] or b.get("next") != c["idx"] or got != want:
                problems.append(f"extras_prices: Granny's sale doesn't run {src} -> {mid} (SimpleShop_Price "
                                f"{got!r}, planned {want}) -> {dst}")
        except (OSError, KeyError, StopIteration) as e:
            problems.append(f"extras_prices: Granny's scene file unreadable ({e})")
    notes = [str(x) for k, v in plan.items() if k.startswith("_notes") and isinstance(v, list) for x in v]
    notes += [str(op["note"]) for k in ("packs", "events", "placements") for op in plan.get(k) or []
              if isinstance(op, dict) and op.get("note")]  # the shelves' notes ride on their pack ops
    notes = "\n".join(notes)
    import shops as shop_tools
    table = shop_tools.shop_map()
    if sec.get("defaults"):  # the fairies' lines: the save-data number each one shows
        from romtools import byml_load, murmur3_32
        gd, _ = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)
        ints = {e["Hash"]: e for e in gd["Data"]["Int"]}
        for row, want in sorted(sec["defaults"].items()):
            got = (ints.get(murmur3_32(row)) or {}).get("DefaultValue")
            if got != want:
                problems.append(f"extras_prices: save data {row} default = {got!r}, planned {want}")
    for name, p in (sec.get("prices") or {}).items():
        if name in EDITS or name in FAIRIES:
            continue  # read back above
        e = (table["locations"].get(name) or {}).get("edit") or {}
        if e.get("calls") and e.get("scene") and not e.get("converted"):
            # a tier scrub (tools/rando/shops.py _scrub_ops), where every sale call it uses charges the price
            item = next((x for x in plan.get("events", []) if x.get("add_graph") == e.get("graph")), None)
            fc = None
            for path in (f"Event/EventFlow/{e['scene']}.110.bfevfl.zs", f"Event/EventFlow/{e['scene']}.bfevfl.zs"):
                try:
                    fc = next(x for x in Evfl(fs.read(path)).flowcharts if x["name"] == e["scene"])
                    break
                except (OSError, KeyError, StopIteration):
                    continue
            if fc is not None and item is not None:
                by = {x["name"]: x for x in fc["events"]}
                tiers = len(table["scrub_items"].get(str(item.get("note", "")).rsplit("sell ", 1)[-1], {})
                            .get("tiers") or [None])
                got = [((by.get(c["event"]) or {}).get("params") or {}).get("items", {}).get("Price", {}).get("value")
                       for c in e["calls"][:tiers]]
                if any(g != p for g in got):
                    problems.append(f"extras_prices: {name}: its sale calls charge {got}, planned {p}")
                continue
        if not re.search(rf"(?m)^{re.escape(name)}: .*\b(for|at) {p}\b", notes):
            problems.append(f"extras_prices: {name}: no plan op prices it at {p}")
    return problems
