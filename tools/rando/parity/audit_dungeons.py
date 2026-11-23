"""Dungeon requirements audit: OoTR's dungeon logic made at least as strict as the remake. TODO: not enabled yet.

OoTR's logic (vendor/ootr/data/World/<Dungeon>.json, Bosses.json) describes the original game plus OoTR's own ROM
patches. I checked every dungeon location in play (chests, Gold Skulltulas, freestanding items, pots, crates, boss
hearts and rewards, Sheik in the Ice Cavern), the locked locations logic still counts on (vanilla keys, silver
rupees, events) and every exit inside the dungeons, boss rooms included, against the game files and remake guides.
From the files that's Banc placements (positions, rooms, Dynamic parameters, switch -> door/chest links, Presence
flags), doors and their locks, and event flows. Where the remake is easier, OoTR's rule stays, since stricter is
safe. Where the remake is harder, the rule is in data/rando/logic/audit_dungeons.json: OoTR's rule AND what the
remake adds, or a rule that implies OoTR's and drops a branch the remake doesn't have.

The logic file is applied when the world is built (tools/rando/world_settings.py logic_overrides, file-name order,
so before chests.json, dungeons.json, drops.json...). Keys another logic file owns aren't restated there. Today
that's the Water Temple North Basement -> Boss Key Chest Room exit in dungeons.json, with the remake's key counts.
For those, and for any key a later file replaces, before_fill ANDs the audit's "_reapply" rule (only what the
remake adds) onto the built rule. So another file can tighten a rule but never undo the audit's, and the audit
never restates a key count another file owns.

No settings are owned, the rules hold for every setting. Fire Temple keys (8 small-key doors, 8 keys): OoTR (not
keysanity) lets the boss-key loop door open with no key and puts one free Fire Temple key in the starting state
(ItemPool.py), because its ROM patch removes that lock (Patches.py "Remove locked door to Boss Key Chest"). The
remake keeps the lock, but the dungeons plugin opens it on a new file whenever small keys are vanilla or dungeon
(IsChainLockDoorOpen.4189300454150217955), so the loop's rule is OoTR's own (8 keys with keysanity, none
otherwise). The narrow path -> upper boulder maze exit uses the remake's
count (no lock there, 5 vs OoTR's 6), and that's the one rule here that isn't stricter than OoTR's.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LOGIC = os.path.join(HERE, "data", "rando", "logic", "audit_dungeons.json")

OWNS = {}


def _norm(rule):
    return " ".join((rule or "").split())


def rules():
    """[(region, section, key, full rule or None, added rule)] from the logic file. The full rule comes from "regions"
    and gets applied when the world is built, None for a key another logic file owns. The added rule ("_reapply") is
    what the remake adds to OoTR's rule or to the rule replacing it."""
    d = json.load(open(LOGIC, encoding="utf-8"))
    return [(region, sec, key, d["regions"].get(region, {}).get(sec, {}).get(key), extra)
            for region, sections in d["_reapply"].items() for sec, entries in sections.items()
            for key, extra in entries.items()]


def spot(world, region_name, sec, key):
    """The built world's exit, event or location for a logic-file entry (events are named '<event> from <region>')."""
    region = world.get_region(region_name)
    if sec == "exits":
        name, pool = f"{region_name} -> {key}", region.exits
    else:
        name, pool = (f"{key} from {region_name}" if sec == "events" else key), region.locations
    found = next((s for s in pool if s.name == name), None)
    if found is None:
        raise RuntimeError(f"data/rando/logic/audit_dungeons.json: no {sec[:-1]} {key!r} in {region_name!r}")
    return found


def overwritten(world, s, full):
    """True if the spot doesn't hold this file's full rule: another logic file owns the key, or replaced it."""
    import world_settings  # tools/rando (the generator's path)
    return full is None or _norm(s.rule_string) != _norm(world_settings._rule(full))


def before_fill(world, settings):
    """Where a later logic file replaced this file's rule, ANDs what the remake adds back on. That's the "_reapply"
    rule, only the extra requirement and not OoTR's whole rule, so a later file's own evidence-based change stays."""
    import world_settings  # tools/rando (the generator's path)
    added = False
    for region_name, sec, key, full, extra in rules():
        s = spot(world, region_name, sec, key)
        if not overwritten(world, s, full):
            continue
        mine = world_settings._rule(extra)
        s.rule_string = f"({s.rule_string}) and ({mine})"
        s.add_rule(world.parser.parse_rule(mine, s))
        added = True
    if added:
        world.parser.create_delayed_rules()  # at()/here() subrule events of the added rules
        world._cached_locations = []  # so searches see those events
