"""Logic server for the tracker (tracker/app). It works out which of a seed's checks are in logic right now.

  python tools/tracker/logic_server.py SEED_FOLDER              serve: JSON lines on stdin, JSON lines on stdout
  python tools/tracker/logic_server.py SEED_FOLDER --validate   check the server against the spoiler's playthrough

SEED_FOLDER is a seed from tools/rando/generate.py, with settings_used.json (what it was generated from),
tracker.json (the checks) and spoiler.json unless it's a race seed. At start the server rebuilds the seed's world
exactly like the generator does, up to the plugins' before_fill (generate.prepare + generate.build_unfilled,
attempt 1, the seed's own settings and plugins). It doesn't fill it. Then it prints one line:
    {"ready": true, "checks": N, "ms": T}          or   {"ready": false, "error": "..."}
Then each request line
    {"id": n, "done": [check names], "inventory": {tracker item name: count}}
gets one reply line
    {"id": n, "available": [not-done checks reachable now], "have": {OoTR item: count}, "ms": T}
or {"id": n, "error": "..."} for a request it can't read.

What the player has ("have") is the starting items, plus the items the spoiler places at the done checks, plus the
inventory mapped to OoTR names with progressive tiers counted. Per item we take the larger of (starting + done) and
inventory. Reachability is OoTR's own Search (ages, time of day, helpers) over a State holding that.
Items at locations that aren't tracker checks are the world's fixed contents: story and boss events, group events,
renewable drops, silver rupees, vanilla items the patcher keeps. The search collects those wherever it can reach
them, over and over. Items at tracker checks are never collected unless the check is done.
Everything else (warnings, unknown names, once each) goes to stderr, so stdout only carries protocol lines.
"""
import collections
import contextlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RANDO = os.path.join(HERE, "tools", "rando")
# A plugin imports NumPy, but the tracker has no BLAS work. One thread kept committed memory down
# from 570 MB to 87 MB on a 16-thread PC.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

_SONGS = {"Zelda's Lullaby": "Zeldas Lullaby", "Epona's Song": "Eponas Song", "Saria's Song": "Sarias Song",
          "Sun's Song": "Suns Song", "Song of Time": "Song of Time", "Song of Storms": "Song of Storms",
          "Minuet of Forest": "Minuet of Forest", "Bolero of Fire": "Bolero of Fire",
          "Serenade of Water": "Serenade of Water", "Nocturne of Shadow": "Nocturne of Shadow",
          "Requiem of Spirit": "Requiem of Spirit", "Prelude of Light": "Prelude of Light"}
# tracker item (first field of tools/tracker/build_data.py ITEMS) -> OoTR item, owned when the count is above 0
OWNED = dict({
    "Kokiri Sword": "Kokiri Sword", "Master Sword": "Master Sword", "Biggoron's Sword": "Biggoron Sword",
    "Deku Shield": "Deku Shield", "Hylian Shield": "Hylian Shield", "Mirror Shield": "Mirror Shield",
    "Goron Tunic": "Goron Tunic", "Zora Tunic": "Zora Tunic", "Iron Boots": "Iron Boots", "Hover Boots": "Hover Boots",
    "Bombchus": "Bombchus", "Fire Arrows": "Fire Arrows", "Ice Arrows": "Ice Arrows", "Light Arrows": "Light Arrows",
    "Boomerang": "Boomerang", "Megaton Hammer": "Megaton Hammer", "Lens of Truth": "Lens of Truth",
    "Din's Fire": "Dins Fire", "Farore's Wind": "Farores Wind", "Nayru's Love": "Nayrus Love",
    "Double Defense": "Double Defense", "Stone of Agony": "Stone of Agony", "Gerudo Card": "Gerudo Membership Card",
    "Kokiri Emerald": "Kokiri Emerald", "Goron Ruby": "Goron Ruby", "Zora Sapphire": "Zora Sapphire",
    **{f"{m} Medallion": f"{m} Medallion" for m in ("Forest", "Fire", "Water", "Shadow", "Spirit", "Light")},
}, **_SONGS)
# tracker item -> (OoTR progressive item, the tier owning it proves)
TIER = {
    "Hookshot": ("Progressive Hookshot", 1), "Longshot": ("Progressive Hookshot", 2),
    "Goron's Bracelet": ("Progressive Strength Upgrade", 1), "Silver Gauntlets": ("Progressive Strength Upgrade", 2),
    "Golden Gauntlets": ("Progressive Strength Upgrade", 3),
    "Silver Scale": ("Progressive Scale", 1), "Golden Scale": ("Progressive Scale", 2),
    "Adult's Wallet": ("Progressive Wallet", 1), "Giant's Wallet": ("Progressive Wallet", 2),
    "Tycoon's Wallet": ("Progressive Wallet", 3),
    "Fairy Ocarina": ("Ocarina", 1), "Ocarina of Time": ("Ocarina", 2),
    "Slingshot": ("Slingshot", 1), "Bow": ("Bow", 1), "Bombs": ("Bomb Bag", 1),  # ammo held means its container too
    # tier names the tracker may send instead of a tier count
    "Big Bomb Bag": ("Bomb Bag", 2), "Biggest Bomb Bag": ("Bomb Bag", 3), "Big Quiver": ("Bow", 2),
    "Biggest Quiver": ("Bow", 3), "Big Bullet Bag": ("Slingshot", 2), "Biggest Bullet Bag": ("Slingshot", 3),
    "Double Magic": ("Magic Meter", 2),
}
# tracker item -> (OoTR item, highest tier). The count is the number of copies (None) or the tier reached. A count
# above the highest tier is read as "owned" (tier 1), e.g. a capacity instead of a tier.
COUNT = {
    "Bottles": ("Bottle", None), "Gold Skulltula Tokens": ("Gold Skulltula Token", None),
    "Magic Beans": ("Magic Bean", None),
    "Bomb Bag": ("Bomb Bag", 3), "Quiver": ("Bow", 3), "Bullet Bag": ("Slingshot", 3), "Magic": ("Magic Meter", 2),
}
# ammo with no logic item of its own (OoTR's Sticks and Nuts are drops and shop items), unless a remake bag setting
AMMO = {"Deku Sticks", "Deku Nuts"}


def _item_name(v):
    return v["item"] if isinstance(v, dict) else v


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class LogicServer:
    def __init__(self, folder, log=None):
        self.log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self.folder = folder
        self._items = {}  # OoTR item name -> Item, None if it's not an OoTR item
        self._unknown_seen = set()
        self._last = None  # (request key, reply), the same save again gets the same answer
        su_path = os.path.join(folder, "settings_used.json")
        if not os.path.exists(su_path):
            raise RuntimeError(f"{su_path} missing: seeds generated before settings_used.json existed can't be "
                               f"rebuilt (generate the seed again with tools/rando/generate.py)")
        used = _json(su_path)
        tracker_path = os.path.join(folder, "tracker.json")
        spoiler_path = os.path.join(folder, "spoiler.json")
        self.spoiler = _json(spoiler_path) if os.path.exists(spoiler_path) else None
        if os.path.exists(tracker_path):
            self.check_names = [c["name"] for c in _json(tracker_path)["checks"]]
        elif self.spoiler is not None:
            self.check_names = list(self.spoiler.get("locations", {}))
        else:
            raise RuntimeError(f"{tracker_path} missing (and no spoiler.json to take the checks from)")
        seed_json = os.path.join(folder, "seed.json")
        self.attempt = int(_json(seed_json).get("attempts", 1)) if os.path.exists(seed_json) else 1

        # the seed's own plugins. generate.enabled_plugins reads RANDO_PLUGINS, and a comma list there replaces the
        # list.
        if used.get("plugins"):
            os.environ["RANDO_PLUGINS"] = ",".join(used["plugins"])
        for p in (RANDO, os.path.join(HERE, "tools")):
            if p not in sys.path:
                sys.path.insert(0, p)
        with contextlib.redirect_stdout(sys.stderr):  # OoTR and plugins print notes, keep them off the protocol stream
            ctx, world = self._rebuild(used)
        from Item import ItemFactory, ItemInfo
        from Search import Search
        from State import State
        self.ItemFactory, self.ItemInfo, self.Search, self.State = ItemFactory, ItemInfo, Search, State
        self.world, self.settings = world, ctx.settings
        self.remake = getattr(ctx.settings, "remake", None) or {}

        locs = {loc.name: loc for loc in world.get_locations()}
        self.unknown = [n for n in self.check_names if n not in locs]
        if self.unknown:
            self.log(f"{len(self.unknown)} tracker checks are not in the rebuilt world (always reported available): "
                     + ", ".join(self.unknown))
        self.checks = [(n, locs.get(n)) for n in self.check_names]
        self.check_set = set(self.check_names)
        not_auto = set(self.check_names) | set((self.spoiler or {}).get("locations", {}))
        # The world's fixed contents, meaning everything placed outside the tracker's checks (events, drops, silver
        # rupees, locked vanilla items). They get collected wherever they're reachable.
        self.auto = [loc for loc in world.get_locations() if loc.item is not None and loc.item.solver_id is not None
                     and loc.name not in not_auto]
        self.placed = {n: _item_name(v) for n, v in (self.spoiler or {}).get("locations", {}).items()}
        # The renewable shop items the spoiler shows on shop checks ("Buy Deku Shield"...). With "buyable" in a request
        # they count wherever their shop can be reached, the way OoTR's logic counts them (its Sticks, Nuts, shields,
        # bombchu refills, Blue Fire, Fish, Bugs, Fairy helpers). By default they only count once their check is done.
        self.buyable = []
        for name, loc in self.checks:
            item = self.placed.get(name, "")
            if loc is not None and loc.item is None and item.startswith("Buy ") and self._logic_item(item):
                with contextlib.redirect_stdout(sys.stderr):
                    loc.item = ItemFactory(item, world)  # it's a check, so no other search collects it
                self.buyable.append(loc)

        # Starting items are OoTR's start state (the settings' starting items, the random ones, the ocarina notes, free
        # scarecrow, the keys OoTR hands out) plus the spoiler's pseudo-starting (skipped) locations.
        self.start = collections.Counter()
        for name, rec in world.distribution.starting_items.items():
            self.start["Bottle" if name == "Bottle with Milk (Half)" else name] += getattr(rec, "count", rec)
        rand = collections.Counter(getattr(world, "randomized_starting_items", None) or {})
        if self.spoiler is not None:
            srand = collections.Counter(self.spoiler.get(":randomized_starting_items") or {})
            if srand != rand:
                self.log(f"warning: random starting items differ: spoiler {dict(srand)}, rebuilt world {dict(rand)}")
            rand = rand | srand
        self.start.update(rand)
        base = world.state.copy()
        for item, n in (rand - collections.Counter(getattr(world, "randomized_starting_items", None) or {})).items():
            self._collect(base, item, n)
        self.skipped = set()
        for loc_name, v in ((self.spoiler or {}).get(":skipped_locations") or {}).items():
            self.skipped.add(loc_name)
            self.start[_item_name(v)] += 1
            self._collect(base, _item_name(v), 1)
        self.base = list(base.solv_items)
        self._check_drift(world, locs)

    def _rebuild(self, used):
        """The seed's world before its fill. This is generate.generate itself (generate.prepare, then its attempt loop),
        stopped at the seed's attempt (seed.json "attempts") right after generate.build_unfilled. Attempt 1 is the
        usual case and builds one world and fills nothing. A seed that took N attempts first replays the N-1 fills that
        failed, since each one moves OoTR's random state on (prices, junk, every shuffle before the fill)."""
        import generate
        target, orig = self.attempt, generate.build_unfilled

        class Unfilled(Exception):
            pass

        def build(ctx, attempt=1):
            got = orig(ctx, attempt)
            if attempt >= target:
                raise Unfilled(ctx, got)
            return got
        generate.build_unfilled = build
        try:
            generate.generate(str(used["seed"]), None, None, used.get("settings_string"), cfg=used["settings"])
        except Unfilled as stop:
            ctx, (_worlds, world, _extra, _made, _guarded) = stop.args
            return ctx, world
        finally:
            generate.build_unfilled = orig
        # An earlier attempt's fill now succeeds with the current code, so we can't rebuild the seed's world any more
        self.log(f"warning: the seed took {target} attempts but attempt {target - 1} or earlier fills now (the code "
                 f"changed since the seed was made): using attempt 1's world")
        ctx = generate.prepare(str(used["seed"]), used["settings"], None, used.get("settings_string"))
        return ctx, generate.build_unfilled(ctx, 1)[1]

    # Items
    def _item(self, name):
        if name not in self._items:
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    self._items[name] = self.ItemFactory(name, self.world)
            except Exception:  # noqa: BLE001 - not an OoTR item
                self._items[name] = None
        return self._items[name]

    def _collect(self, state, name, n):
        it = self._item(name)
        if it is not None and it.solver_id is not None:
            for _ in range(max(0, n)):
                state.collect(it)

    def _logic_item(self, name):
        it = self._item(name)
        return it is not None and it.solver_id is not None

    def _once(self, what, name):
        if (what, name) not in self._unknown_seen:
            self._unknown_seen.add((what, name))
            self.log(f"unknown {what}: {name!r}")

    def inventory_items(self, inventory):
        """The tracker's inventory {tracker item: count} -> Counter {OoTR item: count}."""
        out = collections.Counter()
        swords = self.remake.get("remake_progressive_swords")
        goron = self.remake.get("remake_progressive_goron_sword")
        wallet_shift = 1 if self.remake.get("remake_shuffle_child_wallet") else 0

        def at_least(item, n):
            out[item] = max(out[item], n)
        for name, count in (inventory or {}).items():
            try:
                c = int(count)
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            if swords and name in ("Kokiri Sword", "Master Sword", "Biggoron's Sword"):
                at_least("Progressive Sword", {"Kokiri Sword": 1, "Master Sword": 2, "Biggoron's Sword": 4}[name])
            elif goron and name == "Biggoron's Sword":
                at_least("Progressive Goron Sword", 2)
            elif name in TIER:
                item, tier = TIER[name]
                at_least(item, tier + (wallet_shift if item == "Progressive Wallet" else 0))
            elif name in COUNT:
                item, hi = COUNT[name]
                at_least(item, c if hi is None or c <= hi else 1)
            elif name in OWNED:  # with blue_fire_arrows OoTR's pool has "Blue Fire Arrows" instead of Ice Arrows
                at_least("Blue Fire Arrows" if name == "Ice Arrows" and getattr(self.settings, "blue_fire_arrows", False)
                         else OWNED[name], 1)
            elif name in AMMO:
                bag = {"Deku Sticks": ("remake_shuffle_deku_stick_bag", "Deku Stick Bag"),
                       "Deku Nuts": ("remake_shuffle_deku_nut_bag", "Deku Nut Bag")}[name]
                if self.remake.get(bag[0]):
                    at_least(bag[1], 1)
            elif self._logic_item(name):  # an OoTR item by its own name (keys, trade items, Ruto's Letter...)
                at_least(name, c)
            else:
                self._once("inventory item", name)
        return out

    def have(self, done, inventory):
        """Counter {OoTR item: count}, per item the larger of (starting + done checks' items) and the inventory."""
        found = collections.Counter(self.start)
        for name in done:
            if name in self.skipped:
                continue  # already a starting item
            item = self.placed.get(name)
            if item is not None:
                found[item] += 1
        inv = self.inventory_items(inventory)
        have = collections.Counter()
        for item in set(found) | set(inv):
            n = max(found[item], inv[item])
            if n > 0 and self._logic_item(item):
                have[item] = n
        return have

    # Logic
    def search(self, have, buyable=False):
        """OoTR's Search over a State holding `have`, collecting every fixed content of the world it can reach (plus the
        seed's renewable shop items with `buyable`)."""
        state = self.State(self.world)
        state.solv_items[:len(self.base)] = self.base
        for item, n in have.items():
            self._collect(state, item, n - self.start.get(item, 0))
        search = self.Search([state])
        collect = self.auto + self.buyable if buyable else self.auto
        if collect:
            search.collect_locations(collect)
        return search

    def available(self, search, done):
        out = []
        for name, loc in self.checks:
            if name in done:
                continue
            if loc is None or search.spot_access(loc):
                out.append(name)
        return out

    def query(self, req):
        t0 = time.perf_counter()
        if not isinstance(req, dict):
            raise ValueError("a request is a JSON object")
        done = req.get("done") or []
        inventory = req.get("inventory") or {}
        if not isinstance(done, list) or not isinstance(inventory, dict):
            raise ValueError('"done" is a list of check names, "inventory" an object {item: count}')
        done = set(done)
        for name in done - self.check_set:
            if name not in self.placed:
                self._once("done check", name)
        buyable = bool(req.get("buyable"))
        key = (frozenset(done), tuple(sorted((str(k), str(v)) for k, v in inventory.items())), buyable)
        if self._last and self._last[0] == key:  # same save again, same answer
            reply = dict(self._last[1])
        else:
            have = self.have(done, inventory)
            with contextlib.redirect_stdout(sys.stderr):
                search = self.search(have, buyable)
                avail = self.available(search, done)
            reply = {"available": avail, "have": dict(sorted(have.items()))}
            self._last = (key, reply)
        reply = {"id": req.get("id"), **reply, "ms": round((time.perf_counter() - t0) * 1000, 1)}
        return reply

    # Checks against the seed's own files
    def _check_drift(self, world, locs):
        """The rebuilt world should be the seed's, so warn if the code changed it since the seed was made."""
        if self.spoiler is None:
            return
        try:
            now = json.loads(json.dumps(self.settings.to_json(), default=str))
            then = self.spoiler.get("settings") or {}
            diff = sorted(k for k in then if k in now and now[k] != then[k] and k not in ("seed",))
            if diff:
                self.log("warning: OoTR settings differ from the spoiler's: " + ", ".join(diff))
        except Exception as e:  # noqa: BLE001 - only a warning
            self.log(f"(settings not compared: {e})")
        # Items placed before the fill prove nothing here, the no-vanilla swaps and the plugins' after_fill move junk
        # later.
        gone = [n for n in self.placed if n not in locs]
        if gone:
            self.log(f"warning: {len(gone)} spoiler locations are not in the rebuilt world (the code changed since the "
                     f"seed was made?), e.g. {gone[:5]}")


# Validation (--validate)
def _inventory_from_items(items):
    """OoTR items -> the tracker inventory a save would show, for the inventory-only test (a race seed). Only what
    tools/tracker/build_data.py ITEMS tracks, so keys, trade items, Ruto's Letter, hearts... aren't in it."""
    rev_owned = {v: k for k, v in OWNED.items()}
    rev_owned["Blue Fire Arrows"] = "Ice Arrows"  # with blue_fire_arrows it's the same item in the remake
    tiers = {"Progressive Hookshot": ("Hookshot", "Longshot"),
             "Progressive Strength Upgrade": ("Goron's Bracelet", "Silver Gauntlets", "Golden Gauntlets"),
             "Progressive Scale": ("Silver Scale", "Golden Scale"),
             "Progressive Wallet": ("Adult's Wallet", "Giant's Wallet", "Tycoon's Wallet"),
             "Ocarina": ("Fairy Ocarina", "Ocarina of Time")}
    counted = {"Bomb Bag": ("Bombs", "Bomb Bag"), "Bow": ("Bow", "Quiver"), "Slingshot": ("Slingshot", "Bullet Bag"),
               "Magic Meter": ("Magic", "Magic")}
    inv = collections.Counter()
    for item, n in items.items():
        if n <= 0:
            continue
        if item in rev_owned:
            inv[rev_owned[item]] = 1
        elif item in tiers:
            for name in tiers[item][:n]:
                inv[name] = 1
        elif item in counted:
            owned, tier = counted[item]
            inv[owned] = max(inv[owned], 1)
            inv[tier] = max(inv[tier], n)
        elif item.startswith("Bottle"):
            inv["Bottles"] += n
        elif item == "Gold Skulltula Token":
            inv["Gold Skulltula Tokens"] += n
        elif item.startswith("Bombchus"):
            inv["Bombchus"] = 1
        elif item in ("Magic Bean", "Magic Bean Pack"):
            inv["Magic Beans"] += 10 * n if item == "Magic Bean Pack" else n
    return dict(inv)


def validate(folder):
    t0 = time.perf_counter()
    srv = LogicServer(folder)
    ready_ms = (time.perf_counter() - t0) * 1000
    sp = srv.spoiler
    if sp is None:
        sys.exit("--validate needs spoiler.json")
    checks = set(srv.check_names)
    spheres = [sp[":playthrough"][k] for k in sorted(sp[":playthrough"], key=int)]
    print(f"{folder}: ready in {ready_ms:.0f} ms, {len(srv.check_names)} checks ({len(srv.unknown)} not in the world), "
          f"{len(srv.auto)} fixed contents collected by the search, {len(spheres)} playthrough spheres "
          f"(sphere 0 included)")
    times, problems = [], 0

    def ask(done, inventory=None, buyable=False):
        r = srv.query({"id": len(times), "done": sorted(done), "inventory": inventory or {}, "buyable": buyable})
        srv._last = None  # time every query in full
        times.append(r["ms"])
        return r
    # Sphere k: with every check of spheres <= k-1 done (none for sphere 0), every check of sphere k should be
    # available.
    done, found_items = set(), collections.Counter()
    for k, sphere in enumerate(spheres):
        r = ask(done)
        avail = set(r["available"])
        need = [n for n in sphere if n in checks]
        missing = [n for n in need if n not in avail]
        search = srv.search(collections.Counter(r["have"]))
        fixed = [n for n in sphere if n not in checks]
        fixed_missing = [n for n in fixed if not search.spot_access(srv.world.get_location(n))]
        # the same with nothing done, only the inventory a save would show (a race seed)
        r2 = ask(set(), _inventory_from_items(found_items))
        inv_missing = [n for n in need if n not in set(r2["available"])]
        r3 = ask(set(), _inventory_from_items(found_items), buyable=True)
        buy_missing = [n for n in need if n not in set(r3["available"])]
        status = "ok" if not missing and not fixed_missing else "FAIL"
        problems += bool(missing or fixed_missing)
        print(f"  sphere {k:2}: {len(need):2} checks{' + ' + str(len(fixed)) + ' fixed' if fixed else ''}: {status}; "
              f"{len(r['available'])} available, {r['ms']:.0f} ms"
              + (f"; missing {missing}" if missing else "") + (f"; fixed not reached {fixed_missing}" if fixed_missing else "")
              + (f"; inventory only: {len(inv_missing)} missing {inv_missing[:6]}" if inv_missing else "; inventory only: ok")
              + (f"; + buyable: {len(buy_missing)} missing {buy_missing[:6]}" if buy_missing else "; + buyable: ok"))
        for n in sphere:
            if n in checks:
                done.add(n)
                found_items[srv.placed[n]] += 1
    # every item, meaning everything the spoiler places, with nothing done
    every = collections.Counter(srv.placed.values())
    every.update(srv.start)
    have = collections.Counter({k: v for k, v in every.items() if srv._logic_item(k)})
    t = time.perf_counter()
    avail = set(srv.available(srv.search(have), set()))
    ms = (time.perf_counter() - t) * 1000
    never = [n for n in srv.check_names if n not in avail]
    print(f"  every item (all {sum(have.values())} logic items the seed places or starts with, nothing done): "
          f"{len(avail)}/{len(srv.check_names)} available, {ms:.0f} ms")
    r = ask(set(), _inventory_from_items(have))
    r2 = ask(set(), _inventory_from_items(have), buyable=True)
    print(f"  every item as a save's inventory (nothing done): {len(r['available'])}/{len(srv.check_names)} "
          f"available, {r['ms']:.0f} ms; with buyable: {len(r2['available'])}, {r2['ms']:.0f} ms")
    for n in never:
        loc = srv.world.get_location(n) if n not in srv.unknown else None
        print(f"    never available: {n} ({loc.parent_region.name if loc else '?'}: {srv.placed.get(n)})")
    times_sorted = sorted(times)
    print(f"  queries: {len(times)}, ms min {times_sorted[0]:.0f} / median {times_sorted[len(times) // 2]:.0f} / "
          f"max {times_sorted[-1]:.0f}")
    return problems, never


def serve(folder):
    out = sys.stdout
    sys.stdout = sys.stderr  # stray prints (OoTR, plugins) never reach the protocol stream
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    def send(obj):
        out.write(json.dumps(obj, ensure_ascii=True) + "\n")
        out.flush()
    t0 = time.perf_counter()
    try:
        srv = LogicServer(folder)
    except BaseException as e:  # noqa: BLE001 - the tracker shows the reason
        import traceback
        traceback.print_exc()
        send({"ready": False, "error": f"{type(e).__name__}: {e}"})
        return 1
    send({"ready": True, "checks": len(srv.check_names), "ms": round((time.perf_counter() - t0) * 1000)})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = None
        try:
            req = json.loads(line)
            reply = srv.query(req)
        except Exception as e:  # noqa: BLE001 - one bad request doesn't stop the server
            reply = {"id": req.get("id") if isinstance(req, dict) else None, "error": f"{type(e).__name__}: {e}"}
        send(reply)
    return 0


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    if "--validate" in argv:
        problems, _ = validate(args[0])
        return 1 if problems else 0
    return serve(args[0])


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        # The world has to come out exactly like the generator built it, and Python only orders sets the same way
        # with PYTHONHASHSEED=0 (generate.py runs with it). The hash seed is fixed when Python starts, so if the
        # tracker didn't set it we restart once. Set it when launching and you skip the restart.
        import subprocess
        sys.exit(subprocess.call([sys.executable] + sys.argv, env=dict(os.environ, PYTHONHASHSEED="0")))
    sys.exit(main(sys.argv[1:]))
