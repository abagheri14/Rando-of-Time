"""Test harness: drives the apworld (apworld/rando_of_time) the way Archipelago's generator does, with small
stand-ins for Archipelago's modules (BaseClasses, Options, worlds.AutoWorld, settings), so the world can be tested
without Archipelago's source.

  python tools/archipelago/harness.py OUT_DIR [--players N] [--seed S] [--settings P1.json,P2.json,...]

Each --settings file is a player's options ({"setting": value} with our names, like a YAML's game section), and
anything missing is the default. The steps go the way Archipelago's Main runs them: generate_early, create_regions,
create_items, set_rules, the locality rules (local_items), an assumed fill, then a playthrough (every location
reachable, every player's goal), fill_slot_data and generate_output (OUT_DIR/*.aprr). The fill does progression
first, by maximum exploration state like Archipelago's fill_restrictive, then useful, then filler and traps, and
every placement is checked with can_fill.
It's not Archipelago's own fill. This tests the world's rules, items and output, not Archipelago.
"""
import collections
import enum
import importlib
import json
import os
import random
import sys
import time
import types
from dataclasses import dataclass, fields

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APWORLD = os.path.join(HERE, "apworld")


# Archipelago stand-ins
def install_stubs():
    BaseClasses = types.ModuleType("BaseClasses")

    class ItemClassification(enum.IntFlag):
        filler = 0
        progression = 1
        useful = 2
        trap = 4
        skip_balancing = 8
        progression_skip_balancing = 9

    class Item:
        game = "Generic"

        def __init__(self, name, classification, code, player):
            self.name, self.classification, self.code, self.player = name, classification, code, player
            self.location = None

        @property
        def advancement(self):
            return bool(self.classification & ItemClassification.progression)

        @property
        def useful(self):
            return bool(self.classification & ItemClassification.useful)

        @property
        def trap(self):
            return bool(self.classification & ItemClassification.trap)

        def __repr__(self):
            return f"{self.name} (P{self.player})"

    class LocationProgressType(enum.IntEnum):
        DEFAULT = 1
        PRIORITY = 2
        EXCLUDED = 3

    class Location:
        game = "Generic"

        def __init__(self, player, name="", address=None, parent=None):
            self.player, self.name, self.address, self.parent_region = player, name, address, parent
            self.item = None
            self.locked = False
            self.access_rule = lambda state: True
            self.item_rule = lambda item: True
            self.progress_type = LocationProgressType.DEFAULT

        def can_reach(self, state):
            return self.access_rule(state)

        def can_fill(self, state, item, check_access=True):
            if self.progress_type == LocationProgressType.EXCLUDED and (item.advancement or item.useful):
                return False
            if not self.item_rule(item):
                return False
            return not check_access or self.can_reach(state)

        def place_locked_item(self, item):
            self.item, item.location, self.locked = item, self, True

        def __repr__(self):
            return f"{self.name} (P{self.player})"

    class Region:
        def __init__(self, name, player, multiworld):
            self.name, self.player, self.multiworld = name, player, multiworld
            self.locations = []

    for k, v in dict(ItemClassification=ItemClassification, Item=Item, LocationProgressType=LocationProgressType,
                     Location=Location, Region=Region).items():
        setattr(BaseClasses, k, v)

    Options = types.ModuleType("Options")

    class OptionError(ValueError):
        pass

    class Option:
        default = 0

        def __init__(self, value=None):
            self.value = self.default if value is None else value

    class Toggle(Option):
        default = 0

    class DefaultOnToggle(Toggle):
        default = 1

    class Choice(Option):
        pass

    class Range(Option):
        pass

    class OptionSet(Option):
        default = frozenset()

        def __init__(self, value=None):
            self.value = set(self.default if value is None else value)

    class OptionList(Option):
        default = []

        def __init__(self, value=None):
            self.value = list(self.default if value is None else value)

    class OptionDict(Option):
        default = {}

        def __init__(self, value=None):
            self.value = dict(self.default if value is None else value)

    class LocalItems(OptionSet):
        pass

    class NonLocalItems(OptionSet):
        pass

    class StartInventory(OptionDict):
        pass

    class StartInventoryPool(OptionDict):
        pass

    @dataclass
    class PerGameCommonOptions:
        local_items: LocalItems
        non_local_items: NonLocalItems
        start_inventory: StartInventory

    for k, v in dict(OptionError=OptionError, Toggle=Toggle, DefaultOnToggle=DefaultOnToggle, Choice=Choice,
                     Range=Range, OptionSet=OptionSet, OptionList=OptionList, OptionDict=OptionDict,
                     PerGameCommonOptions=PerGameCommonOptions, StartInventoryPool=StartInventoryPool).items():
        setattr(Options, k, v)

    settings = types.ModuleType("settings")

    class Group:
        pass

    class UserFolderPath(str):
        pass
    settings.Group, settings.UserFolderPath = Group, UserFolderPath

    worlds = types.ModuleType("worlds")
    worlds.__path__ = [APWORLD]
    AutoWorld = types.ModuleType("worlds.AutoWorld")

    class WebWorld:
        pass

    class World:
        def __init__(self, multiworld, player):
            self.multiworld, self.player = multiworld, player
            self.random = random.Random(multiworld.seed * 1000 + player)

        @property
        def player_name(self):
            return self.multiworld.get_player_name(self.player)
    AutoWorld.World, AutoWorld.WebWorld = World, WebWorld
    worlds.AutoWorld = AutoWorld
    sys.modules.update({"BaseClasses": BaseClasses, "Options": Options, "settings": settings, "worlds": worlds,
                        "worlds.AutoWorld": AutoWorld})
    return BaseClasses, Options


class CollectionState:
    def __init__(self, mw):
        self.prog_items = {p: collections.Counter() for p in mw.player_ids}

    def collect(self, item):
        if item.advancement:
            self.prog_items[item.player][item.name] += 1

    def copy(self):
        s = CollectionState.__new__(CollectionState)
        s.prog_items = {p: collections.Counter(c) for p, c in self.prog_items.items()}
        return s


class MultiWorld:
    def __init__(self, n, seed):
        self.seed, self.seed_name = seed, f"H{seed}"
        self.player_ids = list(range(1, n + 1))
        self.player_name = {p: f"Player{p}" for p in self.player_ids}
        self.worlds, self.regions, self.itempool = {}, [], []
        self.completion_condition = {}
        self.precollected_items = {p: [] for p in self.player_ids}
        self.random = random.Random(seed)

    def get_player_name(self, p):
        return self.player_name[p]

    def get_locations(self):
        return [loc for r in self.regions for loc in r.locations]

    def get_out_file_name_base(self, p):
        return f"AP_{self.seed_name}_P{p}_{self.player_name[p]}"


# The run
def sweep(mw, state, locs):
    """Collect every progression item at reachable filled locations until nothing new (state changes in place)."""
    done = set()
    while True:
        new = [loc for loc in locs if loc not in done and loc.item is not None and loc.can_reach(state)]
        if not new:
            return done
        for loc in new:
            done.add(loc)
            state.collect(loc.item)


def fill(mw, log):
    locs = mw.get_locations()
    local = {p: set(mw.worlds[p].options.local_items.value) for p in mw.player_ids}
    for loc in locs:  # Archipelago's locality_rules: another player's local items never land here
        prev = loc.item_rule
        loc.item_rule = (lambda item, prev=prev, player=loc.player:
                         (item.player == player or item.name not in local[item.player]) and prev(item))
    pool = list(mw.itempool)
    mw.random.shuffle(pool)
    prog = [i for i in pool if i.advancement]
    useful = [i for i in pool if not i.advancement and i.useful]
    rest = [i for i in pool if not i.advancement and not i.useful]
    empty = [loc for loc in locs if loc.item is None]
    mw.random.shuffle(empty)
    t0 = time.time()
    filled = [loc for loc in locs if loc.item is not None]
    base = CollectionState(mw)
    for p in mw.player_ids:
        for it in mw.precollected_items[p]:
            base.collect(it)
    while prog:
        item = prog.pop()
        state = base.copy()
        for it in prog:
            state.collect(it)
        sweep(mw, state, filled)
        spot = next((loc for loc in empty if loc.can_fill(state, item)), None)
        if spot is None:
            raise RuntimeError(f"no location for {item}")
        spot.item, item.location = item, spot
        empty.remove(spot)
        filled.append(spot)
    log(f"  progression placed in {time.time() - t0:.1f} s")
    for group in (useful, rest):
        for item in group:
            spot = next((loc for loc in empty if loc.can_fill(None, item, check_access=False)), None)
            if spot is None:
                raise RuntimeError(f"no location for {item}")
            spot.item, item.location = item, spot
            empty.remove(spot)
    if empty:
        raise RuntimeError(f"{len(empty)} locations left empty, e.g. {empty[:3]}")


def playthrough(mw):
    """Every location reachable and every goal met, collecting everything from nothing (accessibility full)."""
    state = CollectionState(mw)
    for p in mw.player_ids:
        for it in mw.precollected_items[p]:
            state.collect(it)
    locs = mw.get_locations()
    spheres, done = 0, set()
    while True:
        new = [loc for loc in locs if loc not in done and loc.can_reach(state)]
        if not new:
            break
        spheres += 1
        for loc in new:
            done.add(loc)
            state.collect(loc.item)
    unreached = [loc for loc in locs if loc not in done]
    goals = {p: bool(mw.completion_condition[p](state)) for p in mw.player_ids}
    return spheres, unreached, goals


def check_rules(mw):
    bad = []
    local = {p: set(mw.worlds[p].options.local_items.value) for p in mw.player_ids}
    for loc in mw.get_locations():
        it = loc.item
        if not loc.item_rule(it):
            bad.append(f"{loc}: {it} breaks the item rule")
        if it.name in local[it.player] and loc.player != it.player:
            bad.append(f"{loc}: {it} is local to P{it.player}")
        if loc.progress_type == 3 and (it.advancement or it.useful):
            bad.append(f"{loc}: excluded, holds {it}")
    return bad


def run(out, n=2, seed=1, settings_files=(), log=print):
    install_stubs()
    sys.path.insert(0, APWORLD)
    os.environ.setdefault("RANDO_OF_TIME", HERE)
    world_mod = importlib.import_module("worlds.rando_of_time")
    W = world_mod.RandoOfTimeWorld
    mw = MultiWorld(n, seed)
    for p in mw.player_ids:
        w = W(mw, p)
        opts = {f.name: f.type() for f in fields(world_mod.RandoOfTimeOptions)}
        if p - 1 < len(settings_files) and settings_files[p - 1]:
            given = json.load(open(settings_files[p - 1], encoding="utf-8"))
            extra = {}
            for k, v in given.items():
                spec = next((s for s in world_mod.options.SPECS if s["name"] == k), None)
                cls = type(opts.get(k)) if k in opts else None
                if spec is None or cls is None:
                    extra[k] = v
                elif spec["kind"] == "choice":
                    opts[k] = cls([our for _a, our in spec["values"]].index(v))
                elif spec["kind"] == "bool":
                    opts[k] = cls(int(bool(v)))
                else:
                    opts[k] = cls(v)
            opts["extra_settings"] = type(opts["extra_settings"])(extra)
        w.options = world_mod.RandoOfTimeOptions(**opts)
        mw.worlds[p] = w
    t0 = time.time()
    for p in mw.player_ids:
        mw.worlds[p].generate_early()
    for p in mw.player_ids:
        mw.worlds[p].create_regions()
    log(f"worlds built in {time.time() - t0:.1f} s: " + ", ".join(
        f"P{p} {len(mw.worlds[p].ap_locations)} locations ({len(mw.worlds[p].desc['locked'])} locked), "
        f"{len(mw.worlds[p].desc['pool'])} items, local {sorted(mw.worlds[p].options.local_items.value)[:6]}"
        for p in mw.player_ids))
    for p in mw.player_ids:
        mw.worlds[p].create_items()
    for p in mw.player_ids:
        mw.worlds[p].set_rules()
        for name, n_ in mw.worlds[p].options.start_inventory.value.items():
            for _ in range(n_):
                mw.precollected_items[p].append(mw.worlds[p].create_item(name))
    t0 = time.time()
    fill(mw, log)
    log(f"fill done in {time.time() - t0:.1f} s")
    bad = check_rules(mw)
    spheres, unreached, goals = playthrough(mw)
    log(f"playthrough: {spheres} spheres, {len(unreached)} unreachable {unreached[:5]}, goals {goals}; "
        f"rule problems: {len(bad)} {bad[:5]}")
    queries = {p: (mw.worlds[p].logic.queries, len(mw.worlds[p].logic.cache)) for p in mw.player_ids}
    log(f"worker queries (cache misses): {queries}")
    os.makedirs(out, exist_ok=True)
    slot = {}
    for p in mw.player_ids:
        slot[p] = mw.worlds[p].fill_slot_data()
        mw.worlds[p].generate_output(out)
    log(f"slot data: {slot}")
    cross = collections.Counter((loc.player, loc.item.player) for loc in mw.get_locations())
    log(f"placements (location's player, item's player): {dict(cross)}")
    return not bad and not unreached and all(goals.values())


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a.split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if not args:
        sys.exit(__doc__)
    ok = run(args[0], int(opts.get("--players", 2)), int(opts.get("--seed", 1)),
             [s for s in opts.get("--settings", "").split(",")])
    sys.exit(0 if ok else 1)
