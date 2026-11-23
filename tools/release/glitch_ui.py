"""How the randomizer app shows the remake's glitch logic. tools/release/export_schema.py calls apply and
tools/release/resolve_settings.py calls split.

  - Logic Rules has Glitchless, "Glitched (remake glitches)" and No Logic. Glitched is logic_rules
    "remake_glitched" from parity/glitches.py. Its explanation is written for the remake, since OoTR's talks about
    its N64 "Advanced" logic, which we don't offer.
  - Detailed Logic gets a "Remake glitches" section with one switch per remake glitch trick
    (data/rando/remake_glitch_tricks.json), saying what it is and where the logic may use it, instead of 14 unmarked
    entries among OoTR's 200 tricks. The app writes "logic_remake_glitch_...": true and generate.load_settings
    (trick_toggles) puts it in allowed_tricks. Glitched logic and No Logic grey the switches out, since Glitched
    already has every one with a route in logic.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))

SECTION = {"name": "remake_glitches_section", "text": "Remake glitches"}
GLITCHED = "remake_glitched"

LOGIC_RULES_TIP = (
    "How the randomizer makes sure every seed can be beaten. "
    "Glitchless: no glitch is ever needed; the tricks you turn on in Detailed Logic may be. "
    "Glitched (remake glitches): Glitchless plus every remake glitch with a route shown to work in this remake "
    "(jump slash cancels, actor jumps, the child Shadow Temple, the King Zora and Gerudo Card skips and more: Detailed "
    "Logic > Remake glitches lists them and where they apply). A seed may need any of them. "
    "OoT Randomizer's own glitched logic is for the N64 game, whose glitches don't work here, so it isn't offered. "
    "No Logic: items go anywhere and nothing is checked, so the seed may be impossible to beat.")
ALLOWED_TRICKS_TIP = (
    "OoT Randomizer's tricks the logic may expect: a seed may need any trick you turn on here, never one left off. "
    "The remake's glitches have their own list (Remake glitches).")
GLITCHED_NOTE = "Glitched logic already includes every remake glitch with a route in logic."

# name: (label, what it is, in plain words). The first sentence is the app's one-line summary.
GLITCHES = {
    "logic_remake_glitch_jsc": (
        "Infinite Jump Slash Cancel (IJSC)",
        "Link climbs to almost any height by chaining jump attacks through the item menu: Deku Sticks as a child, the "
        "Megaton Hammer as an adult, plus any second item to swap to. He can't go higher than his last normal jump."),
    "logic_remake_glitch_actor_jump": (
        "Actor Jump",
        "An adult is launched high into the air off a movable object (an open chest, a gravestone, a bean plant) by "
        "jumping just as an aimed Hookshot, Bow or Ocarina animation ends."),
    "logic_remake_glitch_child_shadow": (
        "Child Shadow Temple (Puberty Skip)",
        "A child does the Shadow Temple with jump slash cancels and Din's Fire, and Bongo Bongo's blue warp makes Link "
        "an adult without the Master Sword. The randomizer checks such seeds as you'd play them: everything the child "
        "can get first, then adult for good (a child again only through the Adult Deku Tree glitch)."),
    "logic_remake_glitch_kz_stick_lift": (
        "King Zora skip",
        "A child jump-slash-cancels over King Zora with Deku Sticks to Zora's Fountain, without Ruto's Letter."),
    "logic_remake_glitch_gf_skip": (
        "Gerudo Card skip",
        "An adult gets past the Gerudo Fortress gate without the Gerudo Card: an Actor Jump off the roof chest, or a "
        "jump slash cancel with the Hover Boots."),
    "logic_remake_glitch_bomb_pose_clip": (
        "Bomb Pose clip (Forest Temple)",
        "An adult clips through Forest Temple walls with the Bomb Pose (Ocarina and Bombs) and a save and reload: past "
        "the Song of Time block, into the Bow room, and through the well with the Iron Boots."),
    "logic_remake_glitch_adult_deku_tree": (
        "Adult Deku Tree (Reverse Puberty)",
        "An adult jump-slash-cancels onto the Deku Tree with the Megaton Hammer, and Gohma's blue warp (once she is "
        "beaten) always makes Link a child again."),
    "logic_remake_glitch_dc_skip": (
        "Dodongo's Cavern early Bomb Bag",
        "A child jump-slash-cancels from the cavern's lobby straight up to the Bomb Bag chest."),
    "logic_remake_glitch_infinite_hover": (
        "Infinite Hover Boots",
        "An adult keeps the Hover Boots hovering by using an empty bottle as they kick in, close to the ground only."),
    "logic_remake_glitch_collapse_hookshot": (
        "Tower collapse with the Hookshot",
        "In the tower collapse, an adult reaches with the plain Hookshot the spot the remake made need the Longshot "
        "(die once on the lower level, then jump-slash-cancel back up with the Megaton Hammer)."),
    "logic_remake_glitch_spirit_hand_entry": (
        "Spirit Temple through the Mirror Shield hand",
        "An adult on the Colossus's right hand walks into the temple through the hand's doorway."),
    "logic_remake_glitch_cucco_displacement": (
        "Cucco displacement (adult Bottom of the Well)",
        "Grabbing a Cucco just as it lands in deep water can carry Link through walls: the way into the Bottom of the "
        "Well as an adult."),
    "logic_remake_glitch_forest_temple_ledge": (
        "Forest Temple ledge without the Hookshot",
        "An adult jump-slash-cancels up to the Forest Temple's entrance ledge with the Megaton Hammer."),
    "logic_remake_glitch_gs_dupe": (
        "Gold Skulltula token duplication",
        "Saving and reloading at the right moment gives a Gold Skulltula's token again and again (vanilla tokens "
        "only)."),
}


def _areas(routes):
    """The places routes apply to, in map order (glitch_report's areas)."""
    import glitch_report
    order = []
    for _, area in glitch_report.PREFIX_AREA:
        if area not in order:
            order.append(area)
    found = set()
    for r in routes:
        for spot in (r.get("region") or "", r.get("target") or ""):
            area = glitch_report.area_of(spot) if spot else "Other"
            if area not in ("Anywhere", "Other"):
                found.add(area)
    return [a for a in order if a in found]


def toggles(offered):
    """The "Remake glitches" switches for the tricks the schema export found usable (`offered`), the ones with a route
    in logic first."""
    from parity import glitches
    tricks = glitches.tricks()
    live, later = [], []
    for name in (n for n in tricks if n in offered):
        t = tricks[name]
        label, what = GLITCHES.get(name, (t["name"], t.get("description", "")))
        routes = glitches.live_routes(name, t)
        if routes:
            n = len(routes)
            tip = (f"{what} In logic: {', '.join(_areas(routes)) or 'see the checklist'} ({n} route"
                   f"{'s' if n != 1 else ''}). Glitched logic includes it.")
            live.append({"name": name, "label": label, "tooltip": tip, "default": False, "type": "bool"})
        else:
            n = sum(1 for r in t.get("candidates", []) if not r.get("refuted") and not r.get("blocked"))
            tip = (f"{what} Not in logic yet: none of its routes has been done in the remake, so turning it on "
                   f"changes no seed until one is ({n} to try in the game).")
            later.append({"name": name, "label": f"{label} (not in logic yet)", "tooltip": tip, "default": False,
                          "type": "bool"})
    return live + later


def apply(tabs):
    """Fixes up the schema export's tabs for the remake's glitch logic. That's the Logic Rules explanation, OoTR's trick
    list without the remake glitches, and the "Remake glitches" section after it."""
    entries = {e["name"]: (t, sec, e) for t in tabs for sec in t["sections"] for e in sec["settings"]}
    if "logic_rules" not in entries or "allowed_tricks" not in entries:
        return
    tab, sec, tricks = entries["allowed_tricks"]
    offered = [k for k, _ in tricks.get("choices", []) if k.startswith("logic_remake_glitch_")]
    tricks["choices"] = [c for c in tricks.get("choices", []) if not c[0].startswith("logic_remake_glitch_")]
    tricks["tooltip"] = ALLOWED_TRICKS_TIP
    switches = toggles(offered)
    names = [e["name"] for e in switches]
    rules = entries["logic_rules"][2]
    rules["tooltip"] = LOGIC_RULES_TIP
    if not any(k == GLITCHED for k, _ in rules.get("choices", [])) or not names:
        return
    disable = rules.setdefault("disable", [])
    for when in ("none", GLITCHED):  # No Logic has no tricks, Glitched already has every one with a route
        rule = next((r for r in disable if r["when"] == when), None)
        if rule is None:
            rule = {"when": when, "settings": []}
            disable.append(rule)
        rule["settings"] += [n for n in names if n not in rule["settings"]]
        if when == GLITCHED:
            rule["note"] = GLITCHED_NOTE  # why they're greyed out, the app may show it instead of "turned off"
    at = tab["sections"].index(sec) + 1
    tab["sections"].insert(at, dict(SECTION, settings=switches))


def split(d):
    """Turns a resolved settings dict (generate.load_settings) into what the app shows, with the remake glitch tricks
    taken out of allowed_tricks as their own switches."""
    import generate
    names = set(generate.remake_tricks())
    tricks = d.get("allowed_tricks")
    if isinstance(tricks, list) and any(t in names for t in tricks):
        for t in tricks:
            if t in names:
                d[t] = True
        d["allowed_tricks"] = [t for t in tricks if t not in names]
    return d
