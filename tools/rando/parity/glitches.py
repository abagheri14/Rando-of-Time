"""Glitch logic for the remake (data/rando/remake_glitch_tricks.json).

Every trick is OFF. There are two ways to use them:
  - Logic Rules "Glitched (remake glitches)" (logic_rules "remake_glitched"): glitchless logic plus every trick that
    has a route in logic (glitched_tricks). resolve_settings turns it into exactly that before OoTR reads the
    settings, so OoTR runs glitchless logic with those tricks. OoTR's own glitched logic, "advanced", is the N64's,
    so we don't offer it. spoiler_settings puts "remake_glitched" back in the spoiler, and the spoiler's settings
    string makes the same seed.
  - One by one: a trick's name (logic_remake_glitch_...) in a settings file's allowed_tricks or in config/tricks.json
    "enabled", like OoTR's own tricks, or "logic_remake_glitch_...": true. The app's Detailed Logic > Remake glitches
    section writes that, and generate.load_settings moves it into allowed_tricks.
The names are registered with OoTR before settings are checked (generate.register_remake_tricks), so OoTR accepts
them and rules can name them.

Routes
Each trick has "rules" and "candidates". Rules are live, meaning a source shows the route and confidence is high.
Candidates are still to be tested in the game (glitch_report.py checklist). An enabled trick ORs
its live routes into the built world's rules (before_fill). "add" is the route the glitch opens, and it's kept
beside the normal rule, never replacing it. A candidate only goes live once it's marked "verified" (tested in the
game). A "refuted" one never does, and neither does a "blocked" one, which is a route logic can't express (e.g. one
that needs Link NOT to have an item). So the logic never counts on a route nobody has done in the remake.
glitch_report.py sets UNTESTED_ROUTES to measure the candidates, no seed does. A route marked "optional" targets a
spot another plugin makes (a drop-group event) and is skipped when that plugin is off.
Route kinds are exit, location, event (in a region) and helper. A helper is a LogicHelpers name, and every rule in
the world that names it gets "(helper or (route))", e.g. can_leave_forest for the forest escape.

What enabled tricks also change in the built world (before_fill). Nothing changes while every trick is off.
  - exits or events OoTR's world doesn't have ("new") start closed ("False") and the route opens them: Graveyard ->
    Graveyard Warp Pad Region, GF Chest Roof -> GF Outside Gate, the Forest Temple bow-room clip, and the
    child-Shadow and adult-Deku blue-warp events that Root -> Root Exits then accepts
  - the Shadow Temple age guards, with any live route into the Shadow Temple, since then a child may be inside.
    OoTR's raw adult items in Shadow Temple rules (Hover_Boots, Hookshot, Longshot, Bow) become can_use(...), so a
    child never counts on an adult item there. OoTR wrote those rules for an adult only because its child can never
    pass the entrance pit.
  - the Spirit Temple hands, for routes that name them. The regions 'Remake Spirit Temple Left Hand' (the Silver
    Gauntlets chest) and 'Remake Spirit Temple Right Hand' (the Mirror Shield chest) are in the Spirit Temple, so
    dungeon items and hints treat the chests as before. They're entered from the chests' old rooms under the
    chests' own rules, so the logic doesn't change, and they lead out to the Colossus. OoTR only checks a
    location's rule once its region is reached, so "reached from outside" needs a region of its own.
After the fill (after_fill) the child-Shadow age swap is checked the way the player actually lives it. OoTR's
search lets the child keep going after the adult appears, but if Link takes the Shadow blue warp as a child he IS
adult from then on. A seed that needs the warp has to be beatable by doing everything the child can first and
then playing on as adult. One that isn't goes back to the fill. The adult only becomes a child again through the
Deku Tree blue warp, which needs logic_remake_glitch_adult_deku_tree. That one's shown: it always loads child
Kokiri Forest, and blue warps can be taken again. The other way back is the Master Sword pedestal, once the
trick's "pedestal_return_verified" is set.
TODO: the pedestal return is untested, that adult never pulled the sword.
Glitched logic in OoTR's sense (glitch_* tricks built on the N64's ISG, hovering, seam walking) doesn't apply,
because those glitches don't work in the remake."""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(HERE, "data", "rando", "remake_glitch_tricks.json")
# OoTR's 'advanced' logic is its N64 glitched logic. Those glitches don't work in the remake,
# and its world files (data/Glitched World) aren't vendored, so a seed would fail to build. The remake's glitched
# logic is "remake_glitched", glitchless logic plus these tricks (resolve_settings).
GLITCHED = "remake_glitched"
GLITCHED_LABEL = "Glitched (remake glitches)"
OWNS = {"logic_rules": ("glitchless", GLITCHED, "none")}
# what PARITY.md adds to a setting's row (tools/rando/parity_report.py)
PARITY_NOTE = {"logic_rules": "advanced (OoTR's N64 glitched logic) loads as remake_glitched, the remake's glitches"}
UNTESTED_ROUTES = False  # glitch_report.py only, it counts candidates as live to measure them. Never in a seed
ADULT_ITEMS = re.compile(r"(?<!can_use\()\b(Hover_Boots|Hookshot|Longshot|Bow)\b(?!\s*,)")  # not "(Item, n)" counts
SHADOW_REGIONS = ("Shadow Temple", "Bongo Bongo")
CHILD_SHADOW_EVENT = "Remake Glitch Child Shadow Warp"
ADULT_DEKU_EVENT = "Remake Glitch Adult Deku Warp"
HANDS = {  # new region -> (the chest, the room it was reached from, where the hand leads)
    "Remake Spirit Temple Left Hand": ("Spirit Temple Silver Gauntlets Chest", "Spirit Temple Central Chamber",
                                       ("Desert Colossus Hands", "Desert Colossus")),
    "Remake Spirit Temple Right Hand": ("Spirit Temple Mirror Shield Chest", "Spirit Temple Beyond Anubis Room",
                                        ("Desert Colossus",)),
}


def tricks():
    return json.load(open(DATA, encoding="utf-8"))["tricks"]


def live_routes(name, t, untested=None):
    """The routes an enabled trick puts in the logic: its rules and its verified candidates."""
    untested = UNTESTED_ROUTES if untested is None else untested
    out = [r for r in t.get("rules", []) if not r.get("refuted") and not r.get("blocked")]
    for r in t.get("candidates", []):
        if not r.get("refuted") and not r.get("blocked") and (r.get("verified") or untested):
            out.append(r)
    return out


def unmodeled(t, name=None):
    """Why a trick can't be used, or None. A trick whose routes are all still untested can be turned on, it just
    changes nothing until one of them is verified."""
    if not live_routes(name, t, untested=True):
        return "has no routes (nothing logic can use)"
    return None


def glitched_tricks():
    """The tricks Logic Rules "Glitched (remake glitches)" turns on: every one with a route in logic."""
    return sorted(name for name, t in tricks().items() if live_routes(name, t))


def resolve_settings(settings):
    """Turns Logic Rules "remake_glitched" into what OoTR runs, "glitchless" with glitched_tricks() added to
    allowed_tricks. It runs before OoTR's Main.resolve_settings (generate.prepare), so OoTR sets the tricks' logic
    flags and makes the settings string and seed from these values. A Glitched seed is just the glitchless seed with
    those tricks. OoTR's own glitched logic ('advanced', the N64's) from a settings string comes here as Glitched
    (for files it's generate.load_settings).
    """
    if getattr(settings, "logic_rules", None) == "advanced":
        import generate
        settings.logic_rules = generate.advanced_as_glitched("settings string")
    if getattr(settings, "logic_rules", None) != GLITCHED:
        return
    settings.logic_rules = "glitchless"
    settings.allowed_tricks = sorted(set(settings.allowed_tricks or []) | set(glitched_tricks()))
    settings.remake_logic_rules = GLITCHED


def spoiler_settings(settings):
    """So the spoiler shows the Logic Rules the player chose (generate.main calls it just before writing it). Its
    settings say "remake_glitched" with the tricks it turned on, and its settings string gives the same seed back."""
    if getattr(settings, "remake_logic_rules", None) != GLITCHED:
        return
    settings.logic_rules = GLITCHED
    # We decode the original settings string because plugins can add disabled_locations during the build, and
    # only change Logic Rules for display. resolve_settings converts it back on reload.
    shown = type(settings)({"seed": settings.seed})
    shown.update_with_settings_string(settings.settings_string)
    shown.logic_rules = GLITCHED
    settings.settings_string = shown.get_settings_string()


def check_settings(settings):
    out = []
    for name, t in tricks().items():
        if name in (getattr(settings, "allowed_tricks", None) or []):
            why = unmodeled(t, name)
            if why:
                out.append(f"{name} ({t['name']}): not usable yet, it {why}")
    return out


def _spot(world, region_name, kind, target):
    region = world.get_region(region_name)
    if kind == "exit":
        name, pool = f"{region_name} -> {target}", region.exits
    else:
        name, pool = (f"{target} from {region_name}" if kind == "event" else target), region.locations
    return next((s for s in pool if s.name == name), None)


def _reparse(world, spot, rule):
    spot.rule_string = rule
    spot.never = False
    world.parser.parse_spot_rule(spot)


def _new_exit(world, region, target, rule="False"):
    from Entrance import Entrance
    e = Entrance(f"{region.name} -> {target}", region)
    e.world = world
    _reparse(world, e, rule)
    region.exits.append(e)
    e.connect(world.get_region(target))
    return e


def _new_event(world, region, event, rule="False"):
    from Item import make_event_item
    from Location import Location
    loc = Location(f"{event} from {region.name}", location_type="Event", parent=region)
    loc.world = world
    _reparse(world, loc, rule)
    region.locations.append(loc)
    make_event_item(event, loc)
    return loc


def _shadow_guards(world):
    """Raw adult items in the Shadow Temple's rules become can_use(...) (a child may be inside)."""
    n = 0
    for region in world.regions:
        if not region.name.startswith(SHADOW_REGIONS):
            continue
        for spot in list(region.exits) + list(region.locations):
            rule = getattr(spot, "rule_string", None)
            if not rule:
                continue
            new = ADULT_ITEMS.sub(r"can_use(\1)", rule)
            if new != rule:
                _reparse(world, spot, new)
                n += 1
    return n


def _hands(world):
    """The Spirit Temple hand regions. Each chest moves into a region of its own, entered from its old room under
    its old rule (so logic doesn't change) and leading out to the Colossus."""
    from Region import Region
    for name, (chest, room_name, outs) in HANDS.items():
        if any(r.name == name for r in world.regions):
            continue
        room = world.get_region(room_name)
        loc = next((x for x in room.locations if x.name == chest), None)
        if loc is None:
            raise RuntimeError(f"glitches: no {chest} in {room_name}")
        hand = Region(world, name, room.type)
        for attr in ("dungeon", "dungeon_name", "hint_name", "alt_hint_name", "scene", "time_passes", "provides_time",
                     "savewarp", "is_boss_room"):
            if hasattr(room, attr):
                setattr(hand, attr, getattr(room, attr))
        hand.world = world
        world.regions.append(hand)
        world._region_cache[name] = hand
        if room.dungeon is not None and hand not in room.dungeon.regions:
            room.dungeon.regions.append(hand)  # its chest stays a Spirit Temple location (dungeon items, hints)
        rule = loc.rule_string or "True"
        room.locations.remove(loc)
        loc.parent_region = hand
        _reparse(world, loc, "True")
        hand.locations.append(loc)
        _new_exit(world, room, name, rule)
        for out in outs:
            _new_exit(world, hand, out, "True")


def _route(name, r):
    import world_settings  # tools/rando (the generator's path)
    add = world_settings._rule(r["add"])
    return add if re.search(rf"\b{name}\b", add) else f"{name} and ({add})"


def _helper_routes(world, helpers):
    """Every rule that names a helper gets the helper's glitch routes beside it."""
    for helper, adds in helpers.items():
        token = re.compile(rf"\b{re.escape(helper)}\b(?!\s*\()")
        wider = "(" + " or ".join([helper] + [f"({a})" for a in adds]) + ")"
        for region in world.regions:
            for spot in list(region.exits) + list(region.locations):
                rule = getattr(spot, "rule_string", None)
                if rule and token.search(rule):
                    _reparse(world, spot, token.sub(wider, rule))


def before_fill(world, settings):
    """Each enabled trick's structural changes, missing exits and events, then its routes ORed onto the rules."""
    on = set(getattr(settings, "allowed_tricks", None) or [])
    active = {}
    for name, t in tricks().items():
        if name in on:
            rs = live_routes(name, t)
            if rs:
                active[name] = rs
    if not active:
        return
    routes = [(name, r) for name, rs in active.items() for r in rs]
    if any(r["region"].startswith(SHADOW_REGIONS) or r["target"].startswith(SHADOW_REGIONS) for _, r in routes):
        _shadow_guards(world)
    if any(r["region"] in HANDS or r["target"] in HANDS for _, r in routes):
        _hands(world)
    for name, r in routes:  # exits and events OoTR's world lacks start closed and the route below opens them
        if not r.get("new") or _spot(world, r["region"], r["kind"], r["target"]) is not None:
            continue
        region = world.get_region(r["region"])
        if r["kind"] == "exit":
            _new_exit(world, region, r["target"])
        elif r["kind"] == "event":
            _new_event(world, region, r["target"])
        else:
            raise RuntimeError(f"{name}: can't make a new {r['kind']} {r['target']!r}")
    helpers = {}
    for name, r in routes:
        if r["kind"] == "helper":
            helpers.setdefault(r["target"], []).append(_route(name, r))
            continue
        s = _spot(world, r["region"], r["kind"], r["target"])
        if s is None and r.get("optional"):
            continue
        if s is None:
            raise RuntimeError(f"{name}: no {r['kind']} {r['target']!r} in {r['region']!r}")
        _reparse(world, s, f"({s.rule_string}) or ({_route(name, r)})")
    if helpers:
        _helper_routes(world, helpers)
    world.parser.create_delayed_rules()
    world._cached_locations = []


# The child-Shadow age swap, as the player lives it
def _explore(world):
    from Search import Search
    s = Search([world.state.copy()])
    s.collect_locations()
    return s


def child_shadow_problem(world):
    """None if the seed is beatable the way the player can actually play it with the child-Shadow age swap, else
    why not.
    1. Beatable without the warp: fine, the glitch is optional.
    2. Otherwise get everything the child (and an adult, if Time_Travel is reachable) can get first. Then the child
       has to reach the warp, and from there Link is adult. He's only a child again through the adult-Deku warp event
       (when that trick is on) or, once it's verified in the game, the pedestal (Time_Travel)."""
    warp = next((loc for loc in world.get_locations() if loc.type == "Event" and loc.item is not None
                 and loc.item.name == CHILD_SHADOW_EVENT), None)
    if warp is None or world.settings.starting_age != "child":
        return None
    item = warp.item
    root = next(e for e in world.get_region("Root").exits if e.connected_region.name == "Root Exits")
    old_rule = root.rule_string
    warp.item = None
    world._cached_locations = []
    try:
        first = _explore(world)
        if first.can_beat_game(scan_for_items=False):
            return None
        if not first.spot_access(warp, age="child"):
            return "the seed needs the child-Shadow warp, but the child can't reach it with what he can get first"
        from Search import Search
        state = first.state_list[world.id].copy()
        state.collect(item)
        back = [f"'{e}'" for e in _events_in(world, (ADULT_DEKU_EVENT,))]  # the Deku Tree warp: adult -> child
        if tricks().get("logic_remake_glitch_child_shadow", {}).get("pedestal_return_verified"):
            back.append("Time_Travel")
        _reparse(world, root, " or ".join(back + [f"(is_adult and '{CHILD_SHADOW_EVENT}')"]))
        second = Search([state])
        second.collect_locations()
        if not second.can_beat_game(scan_for_items=False):
            return ("the seed needs the child-Shadow warp, and after it (Link adult for good, unless the Deku Tree warp "
                    "or a verified pedestal return makes him a child) it can't be beaten")
        return None
    finally:
        warp.item = item
        _reparse(world, root, old_rule)
        world._cached_locations = []


def _events_in(world, names):
    return [n for n in names if any(loc.type == "Event" and loc.item is not None and loc.item.name == n
                                    for loc in world.get_locations())]


def after_fill(world, settings):
    problem = child_shadow_problem(world)
    if problem:
        from Fill import ShuffleError
        raise ShuffleError(f"glitches: {problem}")
