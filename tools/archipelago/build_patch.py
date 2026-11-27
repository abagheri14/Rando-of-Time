"""Turn one Archipelago slot (.aprr, from the apworld) into a normal seed folder.

  python tools/archipelago/build_patch.py FILE.aprr OUT
  python tools/archipelago/build_patch.py FILE.aprr --check     (does it build? nothing kept)
then, as for any seed:
  python tools/make_patch.py ROMFS OUT/patch OUT/plan.json
  python tools/rando/in_game_check.py OUT

Writes OUT/plan.json, spoiler.json, seed.json, tracker.json and settings_used.json exactly like tools/rando/generate.py
does, plus OUT/ap.json (data/archipelago/CONTRACT.md) with this seed's Archipelago location ids, its other players'
items and the mailbox interface version.

How it works: generate.py's own main() runs with the .aprr's seed, settings and plugins, and generate.py itself isn't
changed. Only OoTR's main fill is replaced (tools/archipelago/world.py fill_hooks). At the point where it would start,
every Archipelago placement goes in, and then OoTR's fill ends as usual (its end checks, the plugins' after_fill, the
spoiler, hints, the plan). Up to that point the run is the same as the apworld's worker's, so the world is the same.
We check that with the world's fingerprint, the attempt, the location set and every item our rules placed themselves.
- Other players' items get the mailbox's placeholder for the item's classification (data/archipelago/MAILBOX.md),
  and the "foreign" table of the remake_archipelago setting names each one. That way the mailbox plugin
  (tools/rando/parity/archipelago.py) gives the found text and flag there and adds the receiving side.
- This player's items found in other worlds, and Archipelago's starting items, are free events at the start of this
  world (Root, locked, internal). That way OoTR's end-of-fill check, playthrough, hints and our post-fill checks see
  this player's world as a whole, like Archipelago does. They aren't checks, so the spoiler's locations and
  tracker.json skip them.
- no_vanilla.fix runs with Archipelago's placements and every progression item held in place, since the apworld's
  item rules already keep Archipelago's items off their vanilla spots. It only swaps junk among the spots our
  plugins filled before the fill. A no-save-warp stranding (no_savewarp.check) goes in ap.json "warnings" instead
  of failing, because in a multiworld items from others can arrive at any time.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world as W  # noqa: E402

FORMAT, VERSION = "rando-of-time-ap", 1
MAX_NAME = 512
MAX_ENTRIES = 200_000
FREE_PREFIX = "Archipelago: "


class PatchError(Exception):
    pass


# Reading an .aprr (hostile input refused)
def _text(value, field):
    if not isinstance(value, str) or len(value) > MAX_NAME or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise PatchError(f"invalid .aprr: {field}")
    return value


def _int(value, field):
    if type(value) is not int or not -(1 << 53) < value < 1 << 53:
        raise PatchError(f"invalid .aprr: {field}")
    return value


def check_aprr(d):
    """Checks the .aprr's whole shape (CONTRACT.md). Names end up in game texts and the spoiler, so a malformed or
    hostile file stops here. OotrR's bridge.check_patch does the same for its .aprmk."""
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        raise PatchError("not a Rando of Time Archipelago file (.aprr)")
    if d.get("version") != VERSION:
        raise PatchError(f".aprr version {d.get('version')!r}: this randomizer reads version {VERSION}")
    if d.get("game") != W.GAME:
        raise PatchError(f".aprr of another game: {d.get('game')!r}")
    for k in ("seed", "seed_name", "slot_name"):
        _text(d.get(k), k)
    _int(d.get("slot"), "slot")
    if not isinstance(d.get("settings"), dict) or not isinstance(d.get("plugins"), list):
        raise PatchError("invalid .aprr: settings")
    for p in d["plugins"]:
        _text(p, "plugins")
    players = d.get("players")
    if not isinstance(players, dict) or len(players) > MAX_ENTRIES:
        raise PatchError("invalid .aprr: players")
    for k, v in players.items():
        if not isinstance(v, dict):
            raise PatchError("invalid .aprr: players")
        _text(k, "players")
        _text(v.get("name"), "player name")
        _text(v.get("game"), "player game")
    pl = d.get("placements")
    if not isinstance(pl, dict) or len(pl) > MAX_ENTRIES:
        raise PatchError("invalid .aprr: placements")
    for name, p in pl.items():
        _text(name, "placement")
        if not isinstance(p, dict) or type(p.get("own")) is not bool or type(p.get("locked", False)) is not bool:
            raise PatchError(f"invalid .aprr placement: {name[:80]}")
        for k in ("item", "player_name", "game", "classification"):
            _text(p.get(k), f"placement {name[:80]} {k}")
        for k in ("item_id", "player", "location_id"):
            _int(p.get(k), f"placement {name[:80]} {k}")
    remote = d.get("remote")
    if not isinstance(remote, list) or len(remote) > MAX_ENTRIES:
        raise PatchError("invalid .aprr: remote")
    for r in remote:
        if not isinstance(r, dict):
            raise PatchError("invalid .aprr: remote")
        for k in ("item", "location", "player_name"):
            _text(r.get(k), f"remote {k}")
        _int(r.get("player"), "remote player")
    start = d.get("start_inventory")
    if not isinstance(start, dict) or len(start) > MAX_ENTRIES:
        raise PatchError("invalid .aprr: start_inventory")
    for k, v in start.items():
        _text(k, "start_inventory")
        _int(v, "start_inventory")
    fixed = d.get("fixed", {})
    if not isinstance(fixed, dict) or len(fixed) > MAX_ENTRIES:
        raise PatchError("invalid .aprr: fixed")
    for k, v in fixed.items():
        _text(k, "fixed")
        _text(v, f"fixed {k[:80]}")
    wc = d.get("world_check")
    if not isinstance(wc, dict):
        raise PatchError("invalid .aprr: world_check")
    _text(wc.get("world"), "world_check")
    _int(wc.get("attempt"), "world_check attempt")
    return d


def load_aprr(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise PatchError(f"unreadable .aprr: {e}") from e
    return check_aprr(d)


# The build
def match_locked(world, filled, placements, error, fixed=None):
    """What OoTR's fill placed before its main fill must be what the .aprr has. The apworld's worker may have swapped
    shop-only slots or song spots among themselves (world.py _avoid_vanilla_locked), so we do the same swaps here, with
    the same price and shop-rule handling (no_vanilla._place, _shop_rules). Any other difference is an error."""
    import no_vanilla
    snap = no_vanilla._shop.get(id(world), {})
    fixed = fixed or {}
    for loc in [loc for loc in filled if loc.name in fixed]:  # spots our logic never reaches (not AP locations)
        if loc.item.name != fixed[loc.name]:
            raise error(f"{loc.name}: our rules placed {loc.item.name}, the .aprr has {fixed[loc.name]}")
    filled = [loc for loc in filled if loc.name not in fixed]
    for loc in filled:
        p = placements[loc.name]
        if not p["own"] or not p.get("locked"):
            raise error(f"{loc.name}: our rules placed {loc.item.name}, the .aprr has {p['item']} ({p['player_name']})")
    want = {loc.name: placements[loc.name]["item"] for loc in filled}
    if sorted(want.values()) != sorted(loc.item.name for loc in filled):
        raise error("our rules placed other items before the main fill than the .aprr has")
    for a in sorted(filled, key=lambda loc: loc.name):
        if a.item.name == want[a.name]:
            continue
        shop = a.name in snap
        b = next((b for b in filled if b is not a and b.item.name == want[a.name] and b.item.name != want[b.name]
                  and (b.name in snap) == shop), None)
        if b is None:
            raise error(f"{a.name}: the .aprr's {want[a.name]} is not among the spots it can swap with")
        no_vanilla._place(a, b, a.item, b.item, shop)
        if shop:
            no_vanilla._shop_rules(world, snap, (a, b))


def add_free(world, entries):
    """Free events at Root holding these items: (location name, item name)."""
    from Item import ItemFactory
    from Location import Location
    root = world.get_region("Root")
    for name, item in entries:
        loc = Location(name, location_type="Event", parent=root, internal=True)
        loc.world = world
        loc.rule_string = "True"
        world.parser.parse_spot_rule(loc)
        root.locations.append(loc)
        world.push_item(loc, ItemFactory(item, world))
        loc.locked = True
    world._cached_locations = []


def build(aprr, out, log=print):
    os.environ["RANDO_PLUGINS"] = ",".join(aprr["plugins"])
    os.environ.setdefault("RANDO_DEBUG", "1")  # a failed attempt's reason on stderr
    W.paths()
    import generate
    import no_savewarp
    mb = W.mailbox()
    placements = aprr["placements"]
    fixed = aprr.get("fixed") or {}
    cfg = dict(aprr["settings"])
    seed_key = (cfg.get(W.MAILBOX_SETTING) or {}).get("seed_key")
    if mb["plugin"]:
        # the mailbox plugin names every other player's item where it stands (MAILBOX.md section 1)
        foreign = {n: {"item": p["item"], "player_name": p["player_name"], "classification": p["classification"],
                       "location_id": p["location_id"]} for n, p in sorted(placements.items()) if not p["own"]}
        cfg, _plugins = W.with_mailbox(cfg, aprr["plugins"], seed_key, foreign)
    cfg = dict(sorted(cfg.items()))
    expect_attempt = aprr["world_check"]["attempt"]
    state = {"world": None, "foreign": {}, "warnings": [], "changed": []}

    def forced(local, snap):
        from Item import ItemFactory
        world = snap["world"]
        if snap["attempt"] != expect_attempt:
            raise generate.SeedError(
                f"the seed needed attempt {snap['attempt']}, the apworld's world was attempt {expect_attempt}: the "
                "placements failed a check after the fill (the line above names it), or the randomizer changed since "
                "the multiworld was generated")
        if snap["check"] != aprr["world_check"]["world"]:
            raise generate.SeedError("this randomizer builds another world than the one the multiworld was generated "
                                     "with (another version, other plugins or data): use the randomizer that "
                                     "generated it")
        names = [loc.name for loc in snap["locs"]]
        if sorted(names) != sorted(list(placements) + list(fixed)) or set(placements) & set(fixed):
            raise generate.SeedError("the .aprr's locations are not this world's")
        match_locked(world, [loc for loc in snap["locs"] if loc.item is not None], placements, generate.SeedError,
                     fixed)
        pool = collections.defaultdict(list)
        for it in list(local["progitempool"]) + list(local["prioitempool"]) + list(local["restitempool"]):
            pool[it.name].append(it)
        for loc in sorted(local["fill_locations"], key=lambda loc: loc.name):
            p = placements.get(loc.name) or {"item": fixed[loc.name], "own": True}
            if p["own"]:
                item = pool[p["item"]].pop() if pool[p["item"]] else ItemFactory(p["item"], world)
            else:
                item = ItemFactory(W.placeholder_for(mb, p["classification"]), world)
                state["foreign"][loc.name] = p
            world.push_item(loc, item)
        free = [(f"{FREE_PREFIX}{r['item']} from {r['player_name']}'s {r['location']}", r["item"])
                for r in aprr["remote"]]
        for name, n in sorted(aprr["start_inventory"].items()):
            free += [(f"{FREE_PREFIX}{name} (starting item {k + 1})", name) for k in range(n)]
        add_free(world, free)
        for lst in ("fill_locations", "progitempool", "prioitempool", "restitempool"):
            del local[lst][:]
        state["world"] = world
        return None

    orig_fix = generate.no_vanilla.fix

    def no_fix(world, settings, tries=40):
        """no_vanilla.fix with Archipelago's placements and every progression item held where they are. It can still
        swap junk among the spots our plugins filled before the fill (the drops plugin's freestanding pickups). No
        Archipelago rule covers those and they don't change any logic."""
        hold = [loc for loc in world.get_locations() if loc.item is not None and not loc.locked
                and (loc.name in placements or loc.item.advancement)]
        for loc in hold:
            loc.locked = True
        try:
            return orig_fix(world, settings, tries)
        finally:
            for loc in hold:
                loc.locked = False

    orig_check = no_savewarp.check

    def check(world):
        """Right after the plugins' after_fill: Archipelago's placements must all still be there."""
        for name, p in placements.items():
            loc = world.get_location(name)
            want = p["item"] if p["own"] else W.placeholder_for(mb, p["classification"])
            got = loc.item.name if loc.item is not None else None
            if got == want:
                continue
            if p["own"] and want == "Nothing" and loc.item is not None and not loc.item.advancement:
                state["changed"].append(f"{name}: Nothing -> {got} (drops plugin, remake_empty_object_contents)")
                continue
            raise generate.SeedError(f"a plugin moved an Archipelago placement: {name} holds {got}, not {want}")
        stranded = orig_check(world)
        for sphere, age, region in stranded:
            state["warnings"].append(f"no save warp: {region} as {age} in sphere {sphere} could strand the player")
        return []

    saved = (generate.load_settings, generate.no_vanilla.fix, no_savewarp.check, sys.argv)
    generate.load_settings = lambda path, preset=None: dict(cfg)
    generate.no_vanilla.fix = no_fix
    no_savewarp.check = generate.no_savewarp.check = check
    sys.argv = ["generate.py", out, "--seed", str(aprr["seed"]), "--settings", "archipelago.aprr"]
    try:
        with W.fill_hooks(forced):
            generate.main()
    finally:
        (generate.load_settings, generate.no_vanilla.fix, no_savewarp.check, sys.argv) = saved
        generate.no_savewarp.check = no_savewarp.check
    world = state["world"]
    if world is None:
        raise PatchError("the generator never reached its fill")
    flagless = flagless_of(aprr, out)
    flagless_plan(world, out, flagless, log)
    write_ap(aprr, out, state, mb, seed_key, goal_of(world, out), flagless)
    for w in state["warnings"]:
        log(f"warning: {w}")
    log(f"wrote {out}/ap.json: {len(placements)} Archipelago locations, {len(state['foreign'])} with another "
        f"player's item, {len(aprr['remote'])} of this player's items in other worlds")
    return state


def goal_of(world, out):
    """The seed's goal for the client's StatusUpdate: {"kind": "ganon"} or {"kind": "triforce_hunt", "count": N}.
    It's the plan's own Triforce goal when the triforce plugin wrote one, else the one from the settings."""
    s = world.settings
    if not getattr(s, "triforce_hunt", False):
        return {"kind": "ganon"}
    plan = json.load(open(os.path.join(out, "plan.json"), encoding="utf-8"))
    n = ((plan.get("_gaps") or {}).get("triforce") or {}).get("goal")
    return {"kind": "triforce_hunt", "count": int(n if n is not None else s.triforce_goal_per_world)}


def flagless_of(aprr, out):
    """{location: AP id} of the Archipelago locations whose tracker.json check has no save flag (own items included).
    We only know that once tracker.json is written, after the plan."""
    tracker = json.load(open(os.path.join(out, "tracker.json"), encoding="utf-8"))
    flagged = {c["name"] for c in tracker.get("checks", []) if c.get("flags")}
    return {name: p["location_id"] for name, p in sorted(aprr["placements"].items()) if name not in flagged}


def flagless_plan(world, out, flagless, log=print):
    """The mailbox's hook (MAILBOX.md). parity.archipelago.flagless_plan(settings, world, flagless) -> {plan section:
    value} gets merged into plan.json (generate.merge_plan) before make_patch, so a check with no save flag of its own
    sets RandoAP_Found_<id> and the client sees it. Skipped while the mailbox has no such function."""
    import importlib
    import generate
    try:
        m = importlib.import_module("parity.archipelago")
    except ImportError:
        return False
    if not hasattr(m, "flagless_plan") or not flagless:
        return False
    part = m.flagless_plan(world.settings, world, flagless)
    if not part:
        return False
    path = os.path.join(out, "plan.json")
    plan = json.load(open(path, encoding="utf-8"))
    generate.merge_plan(plan, part)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)
    log(f"plan.json: the mailbox's flagless steps added ({len(flagless)} Archipelago locations without a save flag)")
    return True


def write_ap(aprr, out, state, mb, seed_key, goal, flagless):
    foreign = {name: {"item": p["item"], "player": p["player"], "player_name": p["player_name"], "game": p["game"],
                      "classification": p["classification"]} for name, p in sorted(state["foreign"].items())}
    ap = {"format": 1, "game": W.GAME, "mailbox_version": mb["version"], "seed_key": seed_key,
          "seed_name": aprr["seed_name"], "seed": aprr["seed"], "slot": aprr["slot"], "slot_name": aprr["slot_name"],
          "team": aprr.get("team", 0), "players": aprr["players"],
          "locations": {name: p["location_id"] for name, p in sorted(aprr["placements"].items())},
          "foreign": foreign, "flagless": flagless, "start_inventory": aprr["start_inventory"], "goal": goal,
          "warnings": state["warnings"],
          "changed": state["changed"]}
    with open(os.path.join(out, "ap.json"), "w", encoding="utf-8") as f:
        json.dump(ap, f, indent=1, ensure_ascii=False)
    # Append the foreign names after OoTR's last key to preserve its formatting.
    # The original "locations" entries still hold the placeholder items.
    sp_path = os.path.join(out, "spoiler.json")
    text = open(sp_path, encoding="utf-8").read().rstrip()
    section = {"seed_name": aprr["seed_name"], "slot": aprr["slot"], "slot_name": aprr["slot_name"],
               "foreign": {n: f"{p['item']} ({p['player_name']})" for n, p in foreign.items()},
               "remote": [f"{r['item']} at {r['player_name']}'s {r['location']}" for r in aprr["remote"]],
               "start_inventory": aprr["start_inventory"]}
    if not text.endswith("}"):
        raise PatchError("spoiler.json: not a JSON object")
    text = text[:-1].rstrip() + ',\n  ":archipelago": ' + json.dumps(section, ensure_ascii=False, indent=1) + "\n}\n"
    json.loads(text)
    with open(sp_path, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv):
    """FILE OUT, or FILE --check to build into a throwaway folder and only say whether the slot builds. The apworld
    runs this as it writes each .aprr, so a multiworld whose placements fail our post-fill checks fails at
    generation, not when a player builds the patch."""
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != (1 if check else 2):
        sys.exit(__doc__)
    import shutil
    import tempfile
    out = tempfile.mkdtemp(prefix="aprr_check_") if check else args[1]
    try:
        build(load_aprr(args[0]), out, log=(lambda msg: None) if check else print)
    except PatchError as e:
        sys.exit(f"error: {e}")
    finally:
        if check:
            shutil.rmtree(out, ignore_errors=True)
    if check:
        print(f"{args[0]}: builds")
    return 0


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        import subprocess
        sys.exit(subprocess.call([sys.executable] + sys.argv, env=dict(os.environ, PYTHONHASHSEED="0")))
    W.paths()
    import generate
    try:
        sys.exit(main(sys.argv[1:]))
    except generate.SeedError as e:
        sys.exit(f"seed error: {e}")
