"""No check keeps its own vanilla item by chance (remake setting remake_avoid_vanilla_spots, off by default).

OoT Randomizer's fill may put an item back where the game has it: a dungeon key in its own key chest, a Piece of Heart
on its own ledge, a shop's own item in its own slot, a token on its own Skulltula. To the player that looks like the
check was never randomized. With the setting on, nothing stays vanilla unless a setting says so (those locations are
locked before the fill and left alone). With it off, OoTR's fill is left exactly as it is. Off is the default, my
call for OoT Randomizer parity since OoTR keeps no item out of its own spot, and players can switch it on.

Before the fill, items a setting keeps to a few locations (dungeon items in their own dungeon, hideout keys in the
fortress) refuse their own vanilla location, so OoTR's dungeon fill places them around it (install_rules).
After OoTR's fill, every other location holding its own vanilla item swaps it with another location's item:
- Both locations must take the other's item under every rule OoTR and the plugins set: item rules (the patcher's
  limits), dungeon and region restrictions, minor-only spots, song spots (shuffle_song_items "song" or "dungeon").
- Neither may end up with its own vanilla item.
- When either item is progression, the swap is kept only if the game is still beatable and every location that was
  reachable before still is.
- Shop slots that sell only shop items (OoTR fills them first, from the shop pool) swap only with each other. OoTR's
  shop rules depend on what a slot sells (wallets, adult, a bottle, found bombchus), so the two slots get their rules
  from before the fill back and OoTR's own Rules.set_shop_rules adds the right ones, then the logic is checked.
Locations the distribution file (OoTR's plando) names never move, either way.
Where no swap exists (the remake's Bombchu Shop is the only shelf that can show bombchus, and all its slots sell them),
the item stays and seed.json lists it with the reason.

"Its own vanilla item" compares how the item looks: Bombs (5) and Bombs (10) are both bombs, any bottle is a bottle,
the Treasure Chest Game's Piece of Heart is a Piece of Heart, a Progressive Hookshot is one at any tier. Shop items
compare by exact name (the shelf shows the amount and price).

seed.json "vanilla_spots" (report) judges what a spot gives in the game, not only the item's name. A plugin with
in_game(world, loc) -> (plays_as_vanilla, how) answers for its own spots. For the drops plugin that's what its plan
makes a pot, grass tuft, rock or placed pickup give, against what the vanilla object gives. So another item that
plays exactly as the vanilla spot is listed too ("hidden": true), and a spot holding its vanilla item's name that
gives something else (OoTR's "Nothing" given the empty drop table) isn't. tools/rando/in_game_check.py reads a built
seed back the same way, independently.
"""
import random

SETTING = "remake_avoid_vanilla_spots"
AMMO = ("Bombs", "Arrows", "Deku Nuts", "Deku Seeds", "Deku Stick", "Bombchus", "Bombchu")
SKIP_TYPES = ("Event", "Hint", "HintStone", "Drop")

_shop = {}  # id(world) -> {location name: (access_rule, access_rules, always, never) before the fill}


DEFAULT = False  # off by default (OoTR parity, my call), every reader asks enabled()


def enabled(settings):
    return bool((getattr(settings, "remake", None) or {}).get(SETTING, DEFAULT))


def look(name):
    """What the player sees an item as, for the vanilla comparison."""
    if name is None:
        return None
    if name.startswith("Buy "):
        return name
    name = name.replace(" (Treasure Chest Game)", "")
    if name.startswith("Bottle") or name.startswith("Rutos Letter"):
        return "Bottle"
    for a in AMMO:
        if name.startswith(a + " (") or name == a:
            return a
    return name


def is_vanilla(loc, item=None):
    item = loc.item if item is None else item
    return item is not None and loc.vanilla_item is not None and look(item.name) == look(loc.vanilla_item)


# OoTR item type -> the setting that can keep it to a few locations (Region.can_fill), and the values that do
CONFINING = {"Map": "shuffle_map", "Compass": "shuffle_compass", "SmallKey": "shuffle_smallkeys",
             "SmallKeyRing": "shuffle_smallkeys", "BossKey": "shuffle_bosskeys", "GanonBossKey": "shuffle_ganon_bosskey",
             "HideoutSmallKey": "shuffle_hideoutkeys", "HideoutSmallKeyRing": "shuffle_hideoutkeys",
             "TCGSmallKey": "shuffle_tcgkeys", "TCGSmallKeyRing": "shuffle_tcgkeys",
             "SilverRupee": "shuffle_silver_rupees", "DungeonReward": "shuffle_dungeon_rewards"}
CONFINED = ("dungeon", "regional", "fortress")


def confined(item, settings):
    """True if a setting keeps this item to a few locations (its dungeon, its region, the fortress)."""
    setting = CONFINING.get(item.type)
    return setting is not None and getattr(settings, setting, None) in CONFINED


def install_rules(world, settings, strict=True, relaxed=()):
    """Before the fill. Remembers the shop-only slots (OoTR's shop pool goes there) and their rules. With `strict`,
    items a setting keeps to a few locations (dungeon keys, maps, compasses, boss keys in their own dungeon, hideout
    keys in the fortress) also refuse their own vanilla location. OoTR's dungeon fill then finds a placement around
    it, where a swap after the fill often can't (an early key that every later door needs). The generator drops
    `strict` after 10 failed attempts, so a setting that leaves no other spot never blocks a seed. `relaxed` names
    items an earlier attempt found no spot for (the remake's Water Temple logic can leave its first keys only their
    vanilla chests), and those take any spot."""
    snap, n = {}, 0
    if enabled(settings):
        for loc in world.get_locations():
            if loc.item is not None or loc.locked:
                continue
            if loc.type == "Shop" and loc.price is None:
                snap[loc.name] = (loc.access_rule, list(loc.access_rules), loc.always, loc.never)
            elif strict and loc.vanilla_item:
                prev, v = loc.item_rule, look(loc.vanilla_item)
                loc.item_rule = (lambda location, item, prev=prev, v=v, relaxed=frozenset(relaxed):
                                 (look(item.name) != v or not confined(item, settings) or item.name in relaxed)
                                 and prev(location, item))
                n += 1
    _shop[id(world)] = snap
    return n


# OoTR's song spots under shuffle_song_items "dungeon" (Fill.distribute_items_restrictive; MQ ones absent here)
DUNGEON_SONG_SPOTS = (
    "Deku Tree Queen Gohma Heart", "Dodongos Cavern King Dodongo Heart", "Jabu Jabus Belly Barinade Heart",
    "Forest Temple Phantom Ganon Heart", "Fire Temple Volvagia Heart", "Water Temple Morpha Heart",
    "Spirit Temple Twinrova Heart", "Shadow Temple Bongo Bongo Heart", "Sheik in Ice Cavern", "Song from Impa",
    "Gerudo Training Ground MQ Ice Arrows Chest", "Gerudo Training Ground Maze Path Final Chest",
    "Bottom of the Well Lens of Truth Chest", "Bottom of the Well MQ Lens of Truth Chest")


def _song_spots(world, settings):
    """The locations OoTR fills from the song pool (songs stay there, nothing else goes there)."""
    mode = getattr(settings, "shuffle_song_items", "song")
    if mode == "song":
        from LocationList import location_groups
        names = location_groups["Song"]
    elif mode == "dungeon":
        names = DUNGEON_SONG_SPOTS
    else:
        return set()
    out = set()
    for name in names:
        try:
            out.add(world.get_location(name))
        except KeyError:
            pass
    return out


def _movable(loc):
    return (loc.item is not None and not loc.locked and not loc.is_disabled and loc.parent_region is not None
            and not any(loc.type.startswith(t) for t in SKIP_TYPES) and not _planned(loc))


def _planned(loc):
    """A location the seed's distribution file (OoTR's plando) names. What it holds is the player's own choice, so a
    swap must never move it away. Otherwise plando'd scrub, mask shop and NPC items get swapped onto junk spots for
    a vanilla item elsewhere, leaving "Nothing" turned into ice traps where the plan put them."""
    d = getattr(getattr(loc, "world", None), "distribution", None)
    records = getattr(d, "locations", None) or {}
    return loc.name in records


def _takes(loc, item):
    if loc.minor_only and item.majoritem:
        return False
    return loc.can_fill_fast(item) and not is_vanilla(loc, item)


def _logic(world, locs):
    from Search import Search
    s = Search([world.state])
    s.collect_locations()
    won = s.can_beat_game(scan_for_items=False)
    return won, frozenset(loc for loc in locs if s.spot_access(loc, "either"))


class _Slots:
    """Just enough of a World for OoTR's Rules.set_shop_rules on a few slots."""

    def __init__(self, world, locs):
        self.parser, self._locs = world.parser, locs

    def get_filled_locations(self):
        return [loc for loc in self._locs if loc.item is not None]


def _place(a, b, x, y, shop):
    """Puts y at a and x at b. Shop-only slots charge their item's own price, other slots keep their price."""
    a.item, b.item = y, x
    y.location, x.location = a, b
    for loc, it in ((a, y), (b, x)):
        if shop:
            loc.price = it.price
        elif loc.price is not None:
            it.price = loc.price


def _shop_rules(world, snap, locs):
    import Rules
    for loc in locs:
        loc.access_rule, rules, loc.always, loc.never = snap[loc.name]
        loc.access_rules = list(rules)
    Rules.set_shop_rules(_Slots(world, locs))


def fix(world, settings, tries=40):
    """After the fill, swaps every item sitting on its own vanilla location with one elsewhere (see the module
    docstring). Returns {"swapped": [(a, b), ...], "left": [(location, item), ...]}."""
    out = {"swapped": [], "left": []}
    _why.clear()
    _areas.clear()
    if not enabled(settings):
        return out
    snap = _shop.get(id(world), {})
    locs = [loc for loc in world.get_locations() if _movable(loc)]
    bad = [loc for loc in locs if is_vanilla(loc)]
    if not bad:
        return out
    songs = _song_spots(world, settings)
    all_locs = [loc for loc in world.get_locations() if loc.item is not None]
    base = [None]

    def logic_ok():
        won, reach = _logic(world, all_locs)
        return won and reach >= base[0], reach

    random.shuffle(bad)
    for a in bad:
        if not is_vanilla(a):  # an earlier swap already moved it
            continue
        x, shop = a.item, a.name in snap
        cands = [b for b in locs if b is not a and b.item.name != x.name and (b in songs) == (a in songs)
                 and (b.name in snap) == shop and _takes(a, b.item) and _takes(b, x)]
        random.shuffle(cands)
        # Junk swaps go first, since they need no logic search outside shops. Within each group the same area
        # comes first, because a closed forest only leaves a few nearby spots for the Kokiri Sword.
        cands.sort(key=lambda b: (bool(x.advancement or b.item.advancement), _area(b) != _area(a)))
        searched, done = 0, False
        for b in cands:
            y = b.item
            check = shop or x.advancement or y.advancement
            if check:
                searched += 1
                if searched > tries:  # each try is a full logic search
                    break
                if base[0] is None:
                    base[0] = _logic(world, all_locs)[1]  # before any logic-changing swap
            prices = (a.price, b.price, x.price, y.price)
            _place(a, b, x, y, shop)
            if shop:
                _shop_rules(world, snap, (a, b))
            if check:
                ok, reach = logic_ok()
                if not ok:
                    _place(a, b, y, x, shop)  # back: x at a, y at b
                    a.price, b.price, x.price, y.price = prices
                    if shop:
                        _shop_rules(world, snap, (a, b))
                    continue
                base[0] = reach
            out["swapped"].append((a.name, b.name))
            done = True
            break
        if not done:
            out["left"].append((a.name, x.name))
            _why[a.name] = (ONLY_OWN if not cands else NO_LOGIC)
    for loc in world.get_filled_locations():  # OoTR's wallet count for priced progression (Fill.py, end of fill)
        if world.maximum_wallets < 3 and loc.price and loc.item.advancement:
            if loc.price > 500:
                world.maximum_wallets = 3
            elif world.maximum_wallets < 2 and loc.price > 200:
                world.maximum_wallets = 2
            elif world.maximum_wallets < 1 and loc.price > 99:
                world.maximum_wallets = 1
    return out


ONLY_OWN = ("only its own kind of item fits here under these settings (e.g. a Skulltula spot takes only tokens "
            "unless remake_drop_contents is 'all'; an auto-collected rupee only rupees)")
NO_LOGIC = "every swap that fits the rules would break the logic (e.g. an early key the dungeon's doors need)"
_why = {}    # location name -> why it stays vanilla (this fill)
_areas = {}  # id(location) -> OoTR hint area (this fill)


def _area(loc):
    if id(loc) not in _areas:
        try:
            from Hints import HintArea
            _areas[id(loc)] = HintArea.at(loc)
        except Exception:  # noqa: BLE001 - a location OoTR can't place in an area: no preference
            _areas[id(loc)] = None
    return _areas[id(loc)]


def _judges():
    """Plugins that judge their own locations in-game (parity/<area>.py in_game(world, loc) -> (vanilla, how) | None)."""
    import sys
    return [m for n, m in sorted(sys.modules.items()) if n.startswith("parity.") and m is not None
            and hasattr(m, "in_game")]


def in_game(world, loc, judges=None):
    """(plays_as_vanilla, how) for a location. That's a plugin's in-game judgment of what its spot gives where it has
    one (for the drops plugin: drop actors, empty tables, objects left as they are, type swaps, the get scene), else
    the name check (is_vanilla)."""
    for m in judges if judges is not None else _judges():
        r = m.in_game(world, loc)
        if r is not None:
            return r
    return is_vanilla(loc), None


def report(world, settings):
    """Locations that play as the vanilla game after the fill, with why. Either they hold their own vanilla item, or
    (judged in-game, see in_game) another item that gives exactly what the vanilla spot gives ("hidden" true). A
    spot holding its vanilla item's name that gives something else in-game (OoTR's "Nothing" made empty) isn't
    listed."""
    snap = _shop.get(id(world), {})
    judges = _judges()
    rows = []
    for loc in world.get_locations():
        if loc.item is None or any(loc.type.startswith(t) for t in SKIP_TYPES):
            continue
        vanilla, how = in_game(world, loc, judges)
        if not vanilla:
            continue
        if is_vanilla(loc):
            why = ("locked before the fill (a setting, or a spot that only takes its own pickup)" if loc.locked
                   else "no other shop slot can sell it in exchange" if loc.name in snap
                   else _why.get(loc.name, "no location can take it in exchange under the rules and logic"))
            row = {"location": loc.name, "item": loc.item.name, "why": why + (f"; in-game: {how}" if how else "")}
        else:
            row = {"location": loc.name, "item": loc.item.name, "why": f"plays as the vanilla spot in-game: {how}",
                   "hidden": True}
        rows.append(row)
    return rows
