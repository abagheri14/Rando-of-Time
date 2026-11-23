"""Parity plugin for item-placement settings from Ship of Harkinian (SoH) and the 3DS randomizer (OoT3DR) that OoTR
doesn't have. They only steer the generator's fill, meaning which item may go where. The patch is the usual one,
so nothing here touches the game files. Every one is a remake setting and off by default, and with all of them
off the plugin changes nothing: no rule, no random number, no plan section.

Settings (value: default first):
- remake_links_pocket "ootr" | "reward" | "advancement" | "anything" | "nothing" (SoH Link's Pocket, OoT3DR Link's
  Pocket): what "ToT Reward from Rauru" holds. That's the item OoTR's skip_reward_from_rauru 'free' gives at the
  start, SoH's and OoT3DR's pocket. "ootr" keeps OoTR's rules (a reward in OoTR's vanilla/reward reward modes,
  anything otherwise). "reward" is a Spiritual Stone or Medallion (rewards shuffled overworld or anywhere),
  "advancement" an item logic may need, "anything" any item and "nothing" a junk item. The last three need the
  rewards shuffled beyond OoTR's vanilla/reward modes, because in those OoTR keeps a reward at Rauru.
- remake_links_pocket_reward "any" | "stone" | "medallion" | "light_medallion" (SoH Link's Pocket Reward): which
  reward the pocket holds when it holds one (OoTR's 'reward' mode, or remake_links_pocket "reward").
- remake_vanilla_songs False | True (SoH Shuffle Songs "Off"): every song goes to its vanilla song location.
  Needs OoTR's shuffle_song_items 'song'. A starting song leaves its spot to the fill.
- remake_vanilla_freestanding_rupees False | True, remake_vanilla_freestanding_hearts False | True (OoT3DR Shuffle
  Standing Rupees / Shuffle Recovery Hearts "Off"): that kind of freestanding item stays vanilla even where OoTR's
  shuffle_freestanding_items shuffles freestanding items, the same way OoTR handles the areas it leaves out. No
  effect with shuffle_freestanding_items off.
- remake_wonderitems_area "all" | "dungeons" | "overworld" (SoH Shuffle Wonder Items Dungeons / Overworld): where
  OoTR's shuffle_wonderitems shuffles wonder items. The rest stay vanilla. No effect with it off.
- remake_vanilla_items False | True (OoT3DR Logic "Vanilla"): every shuffled item whose vanilla spot is in play
  goes back there. The fill still handles spots whose remake rules refuse their item (say a chest that can't take
  a progressive item) and items OoTR's settings replaced, like ice traps or the item pool's junk. Keys, maps,
  compasses and silver rupees have to be vanilla (or removed / started with) for it, since OoT3DR's Vanilla logic
  keeps them that way, and remake_avoid_vanilla_spots has to be off.
"""
import difflib
import random

RAURU = "ToT Reward from Rauru"
STONES = ("Kokiri Emerald", "Goron Ruby", "Zora Sapphire")
MEDALLIONS = ("Light Medallion", "Forest Medallion", "Fire Medallion", "Water Medallion", "Shadow Medallion",
              "Spirit Medallion")
POCKET = ("ootr", "reward", "advancement", "anything", "nothing")
POCKET_REWARD = ("any", "stone", "medallion", "light_medallion")
FREESTANDING_TYPES = ("ActorOverride", "Freestanding", "RupeeTower")
HEART_ITEMS = ("Recovery Heart",)
REMAKE_SETTINGS = {
    "remake_links_pocket": POCKET,
    "remake_links_pocket_reward": POCKET_REWARD,
    "remake_vanilla_songs": (False, True),
    "remake_vanilla_freestanding_rupees": (False, True),
    "remake_vanilla_freestanding_hearts": (False, True),
    "remake_wonderitems_area": ("all", "dungeons", "overworld"),
    "remake_vanilla_items": (False, True),
}
REMAKE_DEFAULTS = {"remake_links_pocket": "ootr", "remake_links_pocket_reward": "any", "remake_vanilla_songs": False,
                   "remake_vanilla_freestanding_rupees": False, "remake_vanilla_freestanding_hearts": False,
                   "remake_wonderitems_area": "all", "remake_vanilla_items": False}
# dungeon item settings OoT3DR's Vanilla logic keeps vanilla (OoTR places "vanilla" ones itself)
VANILLA_ITEM_SETTINGS = {
    "shuffle_smallkeys": ("vanilla", "remove"), "shuffle_bosskeys": ("vanilla", "remove"),
    "shuffle_map": ("vanilla", "remove", "startwith"), "shuffle_compass": ("vanilla", "remove", "startwith"),
    "shuffle_hideoutkeys": ("vanilla", "remove"), "shuffle_tcgkeys": ("vanilla", "remove"),
    "shuffle_ganon_bosskey": ("vanilla", "remove"), "shuffle_silver_rupees": ("vanilla", "remove"),
    "shuffle_dungeon_rewards": ("vanilla",), "shuffle_song_items": ("song",),
}
_notes = {}


def _remake(settings):
    return getattr(settings, "remake", None) or {}


def value(settings, key):
    return _remake(settings).get(key, REMAKE_DEFAULTS[key])


def active(settings):
    return {k: value(settings, k) for k in REMAKE_SETTINGS if value(settings, k) != REMAKE_DEFAULTS[k]}


def _reward_kind_ok(kind, name):
    return (kind == "any" or (kind == "stone" and name in STONES) or (kind == "medallion" and name in MEDALLIONS)
            or (kind == "light_medallion" and name == "Light Medallion"))


# Settings
def check_settings(settings):
    out = []
    for k, v in _remake(settings).items():
        if k in REMAKE_SETTINGS:
            ok = REMAKE_SETTINGS[k]
            if v not in ok or isinstance(v, bool) != isinstance(ok[0], bool):
                out.append(f"{k} = {v!r}: extras_pool can make {', '.join(map(repr, ok))}")
            continue
        near = difflib.get_close_matches(k, list(REMAKE_SETTINGS), n=1, cutoff=0.85)
        if near:
            out.append(f"{k}: unknown remake setting; did you mean {near[0]}?")
    rewards = getattr(settings, "shuffle_dungeon_rewards", "reward")
    pocket, kind = value(settings, "remake_links_pocket"), value(settings, "remake_links_pocket_reward")
    if pocket in ("advancement", "anything", "nothing") and rewards in ("vanilla", "reward"):
        out.append(f"remake_links_pocket = {pocket!r}: with shuffle_dungeon_rewards {rewards!r} OoTR keeps a reward at "
                   f"{RAURU}; shuffle the rewards (dungeon, regional, overworld, any_dungeon or anywhere)")
    if pocket == "reward" and rewards not in ("vanilla", "reward", "overworld", "anywhere"):
        out.append(f"remake_links_pocket = 'reward': shuffle_dungeon_rewards {rewards!r} keeps the rewards in "
                   f"dungeons or their regions, and {RAURU} is neither; use overworld or anywhere")
    if kind != "any":
        if pocket in ("advancement", "anything", "nothing") or (pocket == "ootr" and rewards not in ("vanilla",
                                                                                                    "reward")):
            out.append(f"remake_links_pocket_reward = {kind!r}: {RAURU} holds no reward with these settings "
                       f"(use shuffle_dungeon_rewards 'reward', or remake_links_pocket 'reward')")
        elif rewards == "vanilla" and kind == "stone":
            out.append("remake_links_pocket_reward = 'stone': with vanilla rewards Rauru gives the Light Medallion")
    if value(settings, "remake_vanilla_songs") and getattr(settings, "shuffle_song_items", "song") != "song":
        out.append("remake_vanilla_songs: songs stay on song locations only with shuffle_song_items 'song'")
    if value(settings, "remake_vanilla_items"):
        import no_vanilla  # tools/rando/no_vanilla.py (remake_avoid_vanilla_spots, off by default)
        if no_vanilla.enabled(settings):
            out.append("remake_vanilla_items puts items back on their own spots: turn remake_avoid_vanilla_spots "
                       "(\"No item in its own spot\") off")
        for name, ok in VANILLA_ITEM_SETTINGS.items():
            v = getattr(settings, name, ok[0])
            if v not in ok:
                out.append(f"remake_vanilla_items: {name} = {v!r}; OoT3DR's Vanilla logic keeps it "
                           f"{' or '.join(map(repr, ok))}")
    return out


def untested(settings):
    return [f"extras_pool: {k} = {v!r} (fill rules only)" for k, v in active(settings).items()]


# Fill rules
def _restrict(loc, test):
    prev = loc.item_rule
    loc.item_rule = (lambda location, item, prev=prev: test(item) and prev(location, item))


def _take(world, name):
    """One item named `name` out of the pool (None if the pool has none)."""
    pool = world.itempool
    k = next((i for i in range(len(pool) - 1, -1, -1) if pool[i].name == name), None)
    return pool.pop(k) if k is not None else None


def _junk_out(world):
    """Takes one junk item out of the pool. A vanilla placement made from a fresh item needs that to keep the item
    and location counts equal."""
    pool = world.itempool
    k = next((i for i in range(len(pool) - 1, -1, -1) if not pool[i].advancement and not pool[i].priority
              and pool[i].type not in ("Shop", "Song") and not pool[i].dungeonitem), None)
    if k is None:
        raise RuntimeError("extras_pool: no junk item left in the pool")
    pool.pop(k)


def _lock(world, loc, item, lock=True, disable=False):
    """Places `item`. OoTR's spoiler leaves out locked locations, so we only lock spots that no other check reads
    back from the spoiler. That's the songs, the same way OoTR locks what it keeps vanilla. Junk on a drops-plugin
    spot gets marked disabled instead, which takes it out of logic and out of the no-vanilla swaps but keeps it in
    the spoiler the read-back compares with."""
    world.push_item(loc, item)
    loc.locked = lock
    if disable:
        from Location import DisableType
        loc.disabled = DisableType.DISABLED


def _pocket(world, settings):
    loc = world.get_location(RAURU)
    pocket, kind = value(settings, "remake_links_pocket"), value(settings, "remake_links_pocket_reward")
    note = []
    if loc.item is not None:  # OoTR's vanilla/reward modes placed a reward here (World.fill_bosses)
        if kind != "any" and not _reward_kind_ok(kind, loc.item.name):
            from LocationList import location_groups
            spots = [world.get_location(n) for n in location_groups["Boss"] if n != RAURU]
            ok = [s for s in spots if s.item is not None and _reward_kind_ok(kind, s.item.name)]
            if not ok:
                raise RuntimeError(f"extras_pool: no {kind} reward to swap onto {RAURU}")
            other = random.choice(sorted(ok, key=lambda s: s.name))
            a, b = loc.item, other.item
            for spot, it in ((loc, b), (other, a)):
                was = spot.locked
                world.push_item(spot, it)
                spot.locked = was
            note.append(f"{RAURU}: {b.name} (swapped with {other.name}, which now holds {a.name})")
        return note
    if pocket == "reward":
        _restrict(loc, lambda item: item.type == "DungeonReward" and _reward_kind_ok(kind, item.name))
    elif pocket == "advancement":
        _restrict(loc, lambda item: item.advancement)
    elif pocket == "nothing":
        from Item import ItemFactory
        from ItemPool import get_junk_item
        _junk_out(world)
        _lock(world, loc, ItemFactory(get_junk_item()[0], world), lock=False)
        note.append(f"{RAURU}: {loc.item.name} (nothing)")
    return note


def _vanilla_songs(world):
    note = []
    for loc in sorted(world.get_locations(), key=lambda x: x.name):
        if loc.type != "Song" or loc.item is not None or loc.locked or not loc.vanilla_item:
            continue
        item = _take(world, loc.vanilla_item)
        if item is None:  # a starting song, so the fill gives this spot something else
            continue
        _lock(world, loc, item)
        note.append(f"{loc.name}: {item.name}")
    return note


def _freestanding(world, settings):
    rupees, hearts = (value(settings, "remake_vanilla_freestanding_rupees"),
                      value(settings, "remake_vanilla_freestanding_hearts"))
    from Item import ItemFactory
    note = []
    for loc in sorted(world.get_locations(), key=lambda x: x.name):
        if loc.type not in FREESTANDING_TYPES or loc.item is not None or loc.locked or not loc.vanilla_item:
            continue
        heart = loc.vanilla_item in HEART_ITEMS
        if not (hearts if heart else rupees):
            continue
        item = _take(world, loc.vanilla_item)
        if item is None:  # OoTR's pool changed it (e.g. into an ice trap), so a fresh one and a junk item out
            _junk_out(world)
            item = ItemFactory(loc.vanilla_item, world)
        _lock(world, loc, item, lock=False, disable=True)
        note.append(loc.name)
    kinds = " and ".join(k for k, on in (("rupees", rupees), ("hearts", hearts)) if on)
    return [f"{len(note)} freestanding spots ({kinds}) stay vanilla"] if note else []


def _wonderitems(world, settings):
    area = value(settings, "remake_wonderitems_area")
    from Item import ItemFactory
    n = 0
    for loc in sorted(world.get_locations(), key=lambda x: x.name):
        if loc.type != "Wonderitem" or loc.item is not None or loc.locked or not loc.vanilla_item:
            continue
        if (loc.dungeon is not None) == (area == "dungeons"):
            continue  # in the shuffled area
        item = _take(world, loc.vanilla_item)
        if item is None:
            _junk_out(world)
            item = ItemFactory(loc.vanilla_item, world)
        _lock(world, loc, item, lock=False, disable=True)
        n += 1
    return [f"{n} wonder items outside the {area} stay vanilla"] if n else []


def _vanilla_items(world):
    """Every spot gets its vanilla item from the pool. OoTR's pool holds a different junk mix than the spots' vanilla
    junk (item_pool_value, ice traps, cows' milk). So when the pool has run out of a spot's vanilla junk item, the
    spot gets a fresh copy and one junk item leaves the pool. Junk never matters to logic, and we only use names
    OoTR's pool uses, which the remake can give."""
    from Item import ItemFactory
    pool_names = {it.name for it in world.itempool}
    spots = [loc for loc in sorted(world.get_locations(), key=lambda x: x.name)
             if loc.item is None and not loc.locked and loc.vanilla_item
             and loc.type not in ("Event", "Hint", "HintStone")]
    placed, fresh, left, short = 0, 0, [], []
    for loc in spots:
        k = next((i for i in range(len(world.itempool) - 1, -1, -1)
                  if world.itempool[i].name == loc.vanilla_item), None)
        if k is None:
            short.append(loc)
            continue
        item = world.itempool[k]
        if not loc.can_fill_fast(item):
            left.append(f"{loc.name} ({item.name})")
            continue
        world.itempool.pop(k)
        _lock(world, loc, item, lock=False)  # remake_avoid_vanilla_spots is off, so nothing swaps it after the fill
        placed += 1
    for loc in short:  # the pool's copies ran out, so a fresh junk copy and one other junk item out
        if loc.vanilla_item not in pool_names:
            continue
        item = ItemFactory(loc.vanilla_item, world)
        if item.advancement or item.priority or not loc.can_fill_fast(item):
            continue
        _junk_out(world)
        _lock(world, loc, item, lock=False)
        fresh += 1
    return [f"{placed + fresh} items at their vanilla spots ({fresh} junk copies for the pool's other junk)"] + (
        [f"left to the fill (its rules refuse the vanilla item there): {', '.join(left)}"] if left else [])


def before_fill(world, settings):
    on = active(settings)
    _notes.pop(id(world), None)
    _late.pop(id(world), None)
    if not on:
        return
    note = []
    if value(settings, "remake_links_pocket") != "ootr" or value(settings, "remake_links_pocket_reward") != "any":
        note += _pocket(world, settings)
    if value(settings, "remake_vanilla_songs"):
        note += _vanilla_songs(world)
    if value(settings, "remake_vanilla_freestanding_rupees") or value(settings, "remake_vanilla_freestanding_hearts"):
        note += _freestanding(world, settings)
    if value(settings, "remake_wonderitems_area") != "all":
        note += _wonderitems(world, settings)
    if value(settings, "remake_vanilla_items"):
        _install_late()
        _late[id(world)] = _vanilla_items  # once every plugin's item rules are in (OoTR's fill starts)
    _notes[id(world)] = note


_late = {}


def _install_late():
    """Runs the vanilla placements when OoTR's fill starts (Main.place_items -> distribute_items_restrictive).
    Plugins run in name order, so the other plugins' before_fill rules (which items a give step can take) are only
    all in place by then."""
    import Main
    if getattr(Main.distribute_items_restrictive, "remake_pool", False):
        return
    original = Main.distribute_items_restrictive

    def distribute(worlds, fill_locations=None, _original=original):
        for w in worlds:
            job = _late.pop(id(w), None)
            if job is not None:
                _notes.setdefault(id(w), []).extend(job(w))
        return _original(worlds, fill_locations)
    distribute.remake_pool = True
    Main.distribute_items_restrictive = distribute


def world_plan(settings, world):
    note = _notes.get(id(world))
    if not note:
        return {}
    return {"_notes_extras_pool": note}
