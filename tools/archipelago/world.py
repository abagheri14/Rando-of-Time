"""One player's world of our generator for Archipelago, built up to its main fill and then asked "which locations can
these items reach". The apworld's worker (worker.py) and build_patch.py share it.

Archipelago fills our locations, and our generator (tools/rando/generate.py) builds the world they belong to.
- `UnfilledWorld(seed, settings)` runs generate.generate itself and stops it where OoTR's fill
  (vendor/ootr/Fill.py distribute_items_restrictive) starts its main fill (fill_hooks). Everything up to there runs
  like in a single-player seed: the attempts loop, the plugins' hooks and their wrappers on the fill, the ice trap
  looks, shop items on shop-only slots, dungeon-bound items in their dungeons, songs on song spots, junk in empty
  dungeons. Those placements become Archipelago locations with locked own items. The pool of the main fill
  (progitempool + prioitempool + restitempool) is the Archipelago item pool, and the locations still empty are
  Archipelago's to fill. build_patch.py runs the same path and puts Archipelago's placements in at that point, so
  OoTR's fill then ends as usual.
- `reach(have)` is OoTR's own Search over a State holding `have` (this player's collected items), with the world's
  fixed contents (events, drops, vanilla items the patcher keeps) collected wherever reachable, the same way
  tools/tracker/logic_server.py does it. -> (bitmask of reachable Archipelago locations, goal reached).
- Item rules say what each location may hold and whether it can show another player's item (the mailbox's
  placeholder, data/archipelago/mailbox.json). What it may hold comes from OoTR's and the plugins' item rules,
  region restrictions, minor-only spots, and no item on its own vanilla spot with remake_avoid_vanilla_spots.
- `fingerprint(world)` is the world as the fill starts (every location's content and price, the entrances, the
  pool), so build_patch can prove it rebuilt the same world.

Needs PYTHONHASHSEED=0 like generate.py does, because OoTR orders sets of names by hash.
"""
import collections
import contextlib
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RANDO = os.path.join(HERE, "tools", "rando")
GAME = "Rando of Time"
WORLD_VERSION = "0.8.0"
AP_DIR = os.path.join(HERE, "data", "archipelago")
# With no mailbox plugin (tools/rando/parity/archipelago.py) the placeholder is an item every location kind can give
DEFAULT_PLACEHOLDER = "Recovery Heart"
FILLER_CANDIDATES = ("Rupees (5)", "Recovery Heart", "Rupee (1)", "Rupees (20)", "Deku Nuts (5)", "Arrows (10)")
CLASSES = ("progression", "useful", "filler", "trap")
MAILBOX_PLUGIN = "archipelago"
MAILBOX_SETTING = "remake_archipelago"


def paths():
    for p in (os.path.join(HERE, "tools"), RANDO):
        if p not in sys.path:
            sys.path.insert(0, p)


def mailbox():
    """The mailbox's interface: version, the placeholder item per Archipelago classification and the item codes it can
    hand over. See data/archipelago/MAILBOX.md and mailbox.json. Its plugin is tools/rando/parity/archipelago.py."""
    p = os.path.join(AP_DIR, "mailbox.json")
    d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    plugin = os.path.exists(os.path.join(RANDO, "parity", MAILBOX_PLUGIN + ".py"))
    ph = d.get("placeholders") or {}
    return {"version": int(d.get("mailbox_version", 0)), "plugin": plugin and bool(ph),
            "placeholders": {c: ph.get(c) or DEFAULT_PLACEHOLDER for c in CLASSES},
            "codes": d.get("codes"), "data": d}


def placeholder_for(mb, classification):
    return mb["placeholders"].get(classification) or DEFAULT_PLACEHOLDER


def with_mailbox(cfg, plugins, seed_key, foreign=None):
    """cfg and the plugin list with the mailbox plugin on (it does nothing without remake_archipelago). The worker
    runs it with no foreign items and build_patch with them, so both build the same world."""
    mb = mailbox()
    if not mb["plugin"]:
        return cfg, plugins
    cfg = dict(cfg)
    cfg[MAILBOX_SETTING] = {"mailbox_version": mb["version"], "seed_key": seed_key, "foreign": foreign or {}}
    plugins = list(plugins)
    if MAILBOX_PLUGIN not in plugins:
        plugins = sorted(plugins + [MAILBOX_PLUGIN])
    return dict(sorted(cfg.items())), plugins


def resolve_settings(user):
    """Archipelago options over config/rando_settings.json, read exactly the way the app's own settings files are
    (generate.load_settings with "base"). The options use our settings names from settings_schema.json,
    config/setting_aliases.json and the logic_remake_glitch_* toggles. -> the resolved dict (settings_used.json
    "settings")."""
    paths()
    import generate
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "archipelago_options.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"base": "config/rando_settings.json", "settings": user}, f)
        try:
            return dict(sorted(generate.load_settings(p).items()))
        except generate.SeedError as e:
            raise generate.SeedError(str(e).replace(p.replace(os.sep, "/"), "Archipelago options")) from None


def class_of(item):
    """Archipelago classification of an OoTR item, as OoTR's own fill sorts its pool (Fill.distribute_items_restrictive:
    advancement -> progression, priority -> useful)."""
    if item.advancement:
        return "progression"
    if item.name == "Ice Trap":
        return "trap"
    if item.priority or item.majoritem:
        return "useful"
    return "filler"


def fingerprint(world):
    """sha256 of the world before the fill: every location's type, region, content and price, the entrances' targets
    and the item pool."""
    h = hashlib.sha256()
    rows = sorted((loc.name, loc.type, loc.parent_region.name if loc.parent_region else None,
                   loc.item.name if loc.item is not None else None, loc.price, bool(loc.locked))
                  for loc in world.get_locations())
    ents = sorted((e.name, e.connected_region.name if e.connected_region is not None else None)
                  for r in world.regions for e in r.exits)
    pool = sorted(i.name for i in world.itempool)
    for part in (rows, ents, pool):
        h.update(json.dumps(part, default=str).encode("utf-8"))
    return h.hexdigest()


def pseudo_start_names(world):
    """Locations whose item the seed gives at the start (OoTR's skipped locations, Plandomizer
    configure_effective_starting_items). They're always reachable."""
    s, out = world.settings, []
    if s.skip_reward_from_rauru in ("free", "free_forced"):
        out.append("ToT Reward from Rauru")
    if world.skip_child_zelda:
        out += ["HC Zeldas Letter", "Song from Impa"]
    if s.gerudo_fortress == "open" and not s.shuffle_gerudo_card:
        out.append("Hideout Gerudo Membership Card")
    return out


class MainFill(Exception):
    """Raised by the worker's hook when OoTR's fill reaches its main fill: (the fill's locals, the snapshot)."""


@contextlib.contextmanager
def fill_hooks(on_main_fill):
    """While this is active, generate.generate runs as always except at one point. When OoTR's fill
    (Fill.distribute_items_restrictive) starts its main fill, which is its own fill_restrictive call for the progression
    pool, on_main_fill(fill's locals, snapshot) runs instead.
    Everything before that runs unchanged: the attempts loop, every plugin's hooks and wrappers (extras_items' pool
    swaps, extras_pool's vanilla placements), the ice trap looks, the plando, the shop items, dungeon-bound items, songs
    on song spots. The snapshot is taken as the fill starts (Distribution.fill, before any placement) and holds
    "world", "locs" (ap_locations), "check" (fingerprint) and "attempt"."""
    paths()
    import Fill
    import Plandomizer
    import generate
    snap = {"attempt": 0}
    orig_fill, orig_dist, orig_build = Fill.fill_restrictive, Plandomizer.Distribution.fill, generate.build_unfilled

    def dist_fill(self, worlds, location_pools, item_pools):
        shop, song, fill = location_pools
        world = worlds[0]
        snap.update(world=world, worlds=worlds, check=fingerprint(world),
                    locs=sorted([*shop, *(loc for loc in song if loc.item is None), *fill], key=lambda loc: loc.name))
        return orig_dist(self, worlds, location_pools, item_pools)

    def fill_restrictive(worlds, base_search, locations, itempool, count=-1):
        frame = sys._getframe(1)
        if frame.f_code.co_name == "distribute_items_restrictive" and "locs" in snap:
            return on_main_fill(frame.f_locals, snap)
        return orig_fill(worlds, base_search, locations, itempool, count)

    def build_unfilled(ctx, attempt=1):
        snap["attempt"] = attempt
        snap.pop("locs", None)
        return orig_build(ctx, attempt)
    Fill.fill_restrictive, Plandomizer.Distribution.fill, generate.build_unfilled = (
        fill_restrictive, dist_fill, build_unfilled)
    try:
        yield snap
    finally:
        Fill.fill_restrictive, Plandomizer.Distribution.fill, generate.build_unfilled = (
            orig_fill, orig_dist, orig_build)


class UnfilledWorld:
    def __init__(self, seed, cfg, plugins=None, log=None, seed_key=None):
        self.log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
        paths()
        import generate
        self.mailbox = mailbox()
        if self.mailbox["plugin"]:
            cfg, plugins = with_mailbox(cfg, plugins or generate.enabled_plugins(), seed_key or "AP" + hashlib.sha256(str(seed).encode()).hexdigest()[:12])
        if plugins:
            os.environ["RANDO_PLUGINS"] = ",".join(plugins)
        self.seed, self.cfg = str(seed), cfg

        def stop(local, snap):
            raise MainFill(local, snap)
        with contextlib.redirect_stdout(sys.stderr):
            self.plugins = generate.enabled_plugins()
            with fill_hooks(stop):
                try:
                    generate.generate(self.seed, None, None, None, cfg=cfg)
                except MainFill as m:
                    local, snap = m.args
                else:
                    raise RuntimeError("our generator's fill never reached its main fill")
            self.world, self.settings = snap["world"], snap["world"].settings
            self.check, self.attempt, self.locs = snap["check"], snap["attempt"], snap["locs"]
            self.index = {loc.name: i for i, loc in enumerate(self.locs)}
            self.locked = {i: loc.item for i, loc in enumerate(self.locs) if loc.item is not None}
            self.open = [i for i, loc in enumerate(self.locs) if loc.item is None]
            self.pool_items = list(local["progitempool"]) + list(local["prioitempool"]) + list(local["restitempool"])
            left = {loc.name for loc in local["fill_locations"]}
            if left != {self.locs[i].name for i in self.open}:
                raise RuntimeError("the fill's open locations are not the Archipelago locations left empty")
            if len(self.pool_items) != len(self.open):
                raise RuntimeError(f"{len(self.pool_items)} items for {len(self.open)} locations")
            self._logic_setup()
            self.fixed = self._drop_unreachable()
            self.vanilla_swaps = self._avoid_vanilla_locked()
            self._rules()
            self.home = self._home_fill()

    # Logic
    def _logic_setup(self):
        from Item import ItemFactory
        from State import State
        world = self.world
        self._items = {}
        self.ItemFactory, self.State = ItemFactory, State
        names = set(self.index)
        start_names = set(pseudo_start_names(world))
        self.always = 0
        for n in start_names & names:
            self.always |= 1 << self.index[n]
        base = world.state.copy()
        auto = []
        for loc in world.get_locations():
            if loc.name in names or loc.item is None or loc.item.solver_id is None:
                continue
            if loc.name in start_names:
                base.collect(loc.item)  # given at the start (OoTR's pseudo-starting items)
            else:
                auto.append(loc)
        self.auto = auto
        self.base = list(base.solv_items)
        self.start_names = start_names
        self.progression = {i.name for i in self.pool_items if i.advancement} | {
            it.name for it in self.locked.values() if it.advancement}

    def _reindex(self, locs):
        self.locs = locs
        self.index = {loc.name: i for i, loc in enumerate(locs)}
        self.locked = {i: loc.item for i, loc in enumerate(locs) if loc.item is not None}
        self.open = [i for i, loc in enumerate(locs) if loc.item is None]
        self.always = 0
        for n in self.start_names & set(self.index):
            self.always |= 1 << self.index[n]

    def _drop_unreachable(self):
        """Spots our logic never reaches, even with every item of this player. That's a rule "False", an unproven spot
        that only takes junk, like data/rando/logic/chests.json "LLR Tower Chest".
        OoTR's fill gives them junk without reaching them, but Archipelago wants every location it knows to be
        reachable (accessibility). So they aren't Archipelago locations. This player's own junk goes there now (OoTR's
        rules, and its own vanilla item only if nothing else fits), and they're reported separately as "fixed" for
        build_patch to place. -> {name: item}."""
        import no_vanilla
        every = collections.Counter(i.name for i in self.pool_items if i.advancement)
        every.update(it.name for it in self.locked.values() if it.advancement)
        bits, _goal = self.reach(every)
        never = [loc for i, loc in enumerate(self.locs) if not (bits >> i) & 1]
        if not never:
            return {}
        junk = [it for it in self.pool_items if not it.advancement]
        for loc in never:
            if loc.item is not None:
                continue
            fits = [it for it in junk if loc.can_fill_fast(it) and not (loc.minor_only and it.majoritem)]
            other = [it for it in fits if not no_vanilla.is_vanilla(loc, it)]
            pick = sorted(other or fits, key=lambda it: (it.priority, it.name == "Ice Trap"))
            if not pick:
                raise RuntimeError(f"{loc.name}: our logic never reaches it and none of this player's junk fits it")
            item = pick[0]
            self.world.push_item(loc, item)
            junk.remove(item)
            self.pool_items.remove(item)
        dropped = {id(loc) for loc in never}
        self.auto += [loc for loc in never if loc.item.solver_id is not None]
        self._reindex([loc for loc in self.locs if id(loc) not in dropped])
        return {loc.name: loc.item.name for loc in never}

    def _avoid_vanilla_locked(self):
        """remake_avoid_vanilla_spots for what OoTR's fill placed before its main fill.
        A shop-only slot or song spot holding its own vanilla item swaps with another of its kind, like
        no_vanilla.fix does after a single-player fill. Same partner rules too: no_vanilla._takes both ways, and shop
        slots charge their item's price and get their shop rules again. A swap is only kept if each item's new spot
        is reachable with every other item of this player (OoTR's assumed-fill rule), since Archipelago's fill hasn't
        run yet. build_patch.py replays the result (match_locked). -> [(a, b)] swapped."""
        import no_vanilla
        if not no_vanilla.enabled(self.settings):
            return []
        world = self.world
        snap = no_vanilla._shop.get(id(world), {})
        songs = no_vanilla._song_spots(world, self.settings)
        kind = {}
        for i, loc in self.locked.items():
            loc = self.locs[i]
            if loc.name in snap:
                kind[loc] = "shop"
            elif loc in songs:
                kind[loc] = "song"
        every = collections.Counter(i.name for i in self.pool_items if i.advancement)
        every.update(loc.item.name for loc in kind if loc.item.advancement)
        every.update(it.name for i, it in self.locked.items() if self.locs[i] not in kind and it.advancement)

        def fits(spot, item):
            if not item.advancement:
                return True
            have = collections.Counter(every)
            have[item.name] -= 1
            return bool((self.reach(have)[0] >> self.index[spot.name]) & 1)
        swaps = []
        rnd = __import__("random").Random(self.seed)
        bad = sorted((loc for loc in kind if no_vanilla.is_vanilla(loc)), key=lambda loc: loc.name)
        for a in bad:
            if not no_vanilla.is_vanilla(a):
                continue
            x, shop = a.item, kind[a] == "shop"
            cands = [b for b in kind if b is not a and kind[b] == kind[a] and b.item.name != x.name
                     and no_vanilla._takes(a, b.item) and no_vanilla._takes(b, x)]
            rnd.shuffle(cands)
            for b in cands:
                y = b.item
                prices = (a.price, b.price, x.price, y.price)
                no_vanilla._place(a, b, x, y, shop)
                if shop:
                    no_vanilla._shop_rules(world, snap, (a, b))
                if fits(b, x) and fits(a, y):
                    swaps.append((a.name, b.name))
                    break
                no_vanilla._place(a, b, y, x, shop)
                a.price, b.price, x.price, y.price = prices
                if shop:
                    no_vanilla._shop_rules(world, snap, (a, b))
        self.locked = {i: loc.item for i, loc in enumerate(self.locs) if loc.item is not None}
        return swaps

    def _home_fill(self):
        """Spots that can't show another player's item (the mailbox's takes_foreign: pots, Skulltulas, freestanding
        items, scrubs, shop slots...) can only ever hold this player's own items. Left to Archipelago, its fill can send
        so many of this player's items abroad that these spots end up with nothing left that fits. So we fill them here
        with OoTR's own rules and they become locked.
        - Progression first, the same share of this player's progression as these spots are of its open spots. Each item
          is placed the way OoTR's fill_restrictive does it (a spot reachable with every other item of this player,
          Fill.py), and an item with no such spot goes back to Archipelago's pool.
        - Then the rest of the spots, fewest fitting items first, with this player's other items.
        The item rules here are the Archipelago ones (the deny matrix, no-vanilla included). -> number of spots
        filled."""
        import random
        from Location import DisableType
        from Search import Search
        world = self.world
        fd = set(self.foreign_deny)
        spots = [self.locs[i] for i in self.open if i in fd]
        if not spots:
            return 0
        deny = {i: {self.rule_items[k] for k in ks} for i, ks in self.deny.items()}

        def ok(loc, item):
            return (
                item.name in self.rule_items
                and item.name not in deny.get(self.index[loc.name], ())
                and loc.can_fill_fast(item)
                and not (loc.minor_only and item.majoritem)
            )
        prog = [it for it in self.pool_items if it.advancement]
        rest = [it for it in self.pool_items if not it.advancement]
        random.shuffle(prog)
        k = round(len(prog) * len(spots) / max(1, len(self.open)))
        home, away = prog[:k], prog[k:]
        base = Search([world.state])
        base.collect_all(away)
        items_search = base.copy()
        items_search.collect_all(home)
        left = [loc for loc in spots]
        placed = set()
        for item in list(home):
            items_search.uncollect(item)
            max_search = items_search.copy()
            max_search.collect_locations()
            cands = [loc for loc in left if loc.disabled == DisableType.ENABLED and ok(loc, item)]
            random.shuffle(cands)
            spot = next((loc for loc in cands if max_search.spot_access(loc)), None)
            if spot is None:
                items_search.collect(item)  # back to Archipelago's pool, still assumed found
                continue
            world.push_item(spot, item)
            left.remove(spot)
            placed.add(id(item))
        random.shuffle(rest)
        fits = {loc: [it for it in rest if ok(loc, it)] for loc in left}
        for loc in sorted(left, key=lambda loc: (len(fits[loc]), loc.name)):
            cand = [it for it in fits[loc] if id(it) not in placed]
            if not cand:
                continue  # Archipelago fills it (an item of this player only)
            item = random.choice(cand)
            world.push_item(loc, item)
            placed.add(id(item))
        self.pool_items = [it for it in self.pool_items if id(it) not in placed]
        self.locked = {i: loc.item for i, loc in enumerate(self.locs) if loc.item is not None}
        self.open = [i for i, loc in enumerate(self.locs) if loc.item is None]
        still = set(self.open)
        self.deny = {i: v for i, v in self.deny.items() if i in still}
        self.foreign_deny = [i for i in self.foreign_deny if i in still]
        self.excluded = [i for i in self.excluded if i in still]
        for it in self.locked.values():
            self.classes.setdefault(it.name, class_of(it))
        return len(placed)

    def item(self, name):
        if name not in self._items:
            try:
                self._items[name] = self.ItemFactory(name, self.world)
            except Exception:  # noqa: BLE001 - not one of our items
                self._items[name] = None
        return self._items[name]

    def reach(self, have):
        """have: {our item name: count} -> (bitmask of reachable Archipelago locations (by index), goal reached)."""
        from Search import Search
        state = self.State(self.world)
        state.solv_items[:len(self.base)] = self.base
        for name, n in have.items():
            it = self.item(name)
            if it is not None and it.solver_id is not None:
                for _ in range(max(0, int(n))):
                    state.collect(it)
        search = Search([state])
        search.collect_locations(self.auto)
        bits = self.always
        for i, loc in enumerate(self.locs):
            if not (bits >> i) & 1 and search.spot_access(loc):
                bits |= 1 << i
        return bits, bool(search.can_beat_game(scan_for_items=False))

    # Item rules
    def _rules(self):
        from Item import ItemFactory
        world = self.world
        distinct = {}
        for it in self.pool_items:
            distinct.setdefault(it.name, it)
        for name in FILLER_CANDIDATES:
            if name not in distinct:
                distinct[name] = ItemFactory(name, world)
        self.rule_items = sorted(distinct)
        placeholders = [ItemFactory(n, world) for n in sorted(set(self.mailbox["placeholders"].values()))]
        self.deny, self.foreign_deny, self.excluded = {}, [], []
        from Location import DisableType
        import no_vanilla
        avoid = no_vanilla.enabled(self.settings)
        looks = {name: no_vanilla.look(name) for name in self.rule_items}
        accepts = collections.Counter()
        self.no_vanilla_rules = 0
        for i in self.open:
            loc = self.locs[i]
            if loc.disabled != DisableType.ENABLED:
                self.excluded.append(i)
            fits = [k for k, name in enumerate(self.rule_items)
                    if loc.can_fill_fast(distinct[name]) and not (loc.minor_only and distinct[name].majoritem)]
            # remake_avoid_vanilla_spots means no own item on its own vanilla spot. no_vanilla.fix swaps them away
            # after OoTR's fill, and Archipelago's fill avoids them instead. A spot that takes only its own kind keeps
            # it, the same way no_vanilla.fix leaves it (seed.json "still_vanilla").
            if avoid and loc.vanilla_item:
                v = no_vanilla.look(loc.vanilla_item)
                other = [k for k in fits if looks[self.rule_items[k]] != v]
                if other and len(other) < len(fits):
                    fits = other
                    self.no_vanilla_rules += 1
            ok = set(fits)
            bad = [k for k in range(len(self.rule_items)) if k not in ok]
            for k in fits:
                accepts[self.rule_items[k]] += 1
            if bad:
                self.deny[i] = bad
            # Another player's item: every one of the mailbox's placeholders has to pass every rule, its plugin's
            # takes_foreign among them.
            if not all(loc.can_fill_fast(ph) for ph in placeholders):
                self.foreign_deny.append(i)
        # the filler Archipelago adds (start_inventory_from_pool, item links) is the junk most locations take
        self.filler = max(FILLER_CANDIDATES, key=lambda n: (accepts[n], -FILLER_CANDIDATES.index(n)))
        # items our rules keep to some of this world's regions (dungeon items in their dungeon, "overworld"...) or that
        # the mailbox can't hand over stay in this world
        codes = self.mailbox["codes"]
        self.local = set()
        for name, it in distinct.items():
            if codes is not None and name not in codes:  # the mailbox can't hand it over (data/archipelago/mailbox.json)
                self.local.add(name)
                continue
            if any(not self.locs[i].parent_region.can_fill(it) for i in self.open):
                self.local.add(name)
        self.classes = {}
        for it in list(distinct.values()) + list(self.locked.values()):
            self.classes.setdefault(it.name, class_of(it))

    # For the apworld
    def describe(self):
        pool = [i.name for i in self.pool_items]
        start = collections.Counter()
        for name, rec in self.world.distribution.starting_items.items():
            start[name] += getattr(rec, "count", rec)
        return {
            "game": GAME, "world_version": WORLD_VERSION, "seed": self.seed, "settings": self.cfg,
            "plugins": self.plugins, "world_check": self.check, "mailbox_version": self.mailbox["version"],
            "placeholders": self.mailbox["placeholders"],
            "locations": [loc.name for loc in self.locs],
            "locked": {str(i): it.name for i, it in self.locked.items()},
            "excluded": self.excluded, "pool": pool,
            "items": {n: {"class": c, "local": n in self.local} for n, c in sorted(self.classes.items())},
            "progression": sorted(self.progression),
            "rule_items": self.rule_items, "deny": {str(i): v for i, v in self.deny.items()},
            "foreign_deny": self.foreign_deny, "filler": self.filler,
            "always": [i for i in range(len(self.locs)) if (self.always >> i) & 1], "fixed": self.fixed,
            "start_items": dict(start), "attempt": self.attempt, "no_vanilla_rules": self.no_vanilla_rules,
            "vanilla_swaps": self.vanilla_swaps, "home_filled": self.home,
        }
