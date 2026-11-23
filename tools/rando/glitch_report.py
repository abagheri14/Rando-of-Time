"""Remake glitch logic report (data/rando/remake_glitch_tricks.json, tools/rando/parity/glitches.py).

  python tools/rando/glitch_report.py coverage [--settings FILE] [--tricks a,b] [--json OUT]
      Per trick: its live routes and its untested candidates, and how many checks each turns from unreachable to
      reachable. A check counts when, for at least one test inventory (STATES: the whole item pool less one kind of
      item the glitches stand in for, or an early inventory), the world built with the trick reaches it and the world
      built without it doesn't. "untested" counts the trick's candidates as live too (as if all were verified).
  python tools/rando/glitch_report.py checklist [OUT]
      Writes the in-game checklist: every route to try in the game, grouped by area.
  python tools/rando/glitch_report.py uses SEED [--settings FILE] [--tricks a,b] [--untested]
      Generates the seed with the tricks on, puts the same items in a world built with them off, and reports
      whether the seed is still beatable without them and which playthrough checks only the tricks reach.
  python tools/rando/glitch_report.py check [--settings FILE]
      Every route (candidates too) is well formed and still in its spot's rule after all plugins (exit 1 if not).

Nothing here changes a seed, it only builds worlds and reads them.
"""
import argparse
import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
DEFAULT_SETTINGS = os.path.join(HERE, "config", "rando_settings.json")
CHECKLIST = os.path.join(HERE, "out", "glitch_logic_checklist.md")
PRESET = os.path.join(HERE, "config", "glitched_settings.json")

# A state starts from the whole pool, drops the named items and their "(count)" variants, then adds back any listed
# copies. The "only" states start from the starting inventory and add just the listed items.
STATES = {
    "no Hookshot": {"less": ["Progressive Hookshot"]},
    "no Longshot": {"less": ["Progressive Hookshot"], "add": ["Progressive Hookshot"]},
    "no Hover Boots": {"less": ["Hover Boots"]},
    "no Hookshot/Hover Boots": {"less": ["Progressive Hookshot", "Hover Boots"]},
    "no Strength": {"less": ["Progressive Strength Upgrade"]},
    "no Silver Gauntlets": {"less": ["Progressive Strength Upgrade"], "add": ["Progressive Strength Upgrade"]},
    "no Iron Boots": {"less": ["Iron Boots"]},
    "no Scale": {"less": ["Progressive Scale"]},
    "no explosives": {"less": ["Bomb Bag", "Bombchus", "Bombchus (5)", "Bombchus (10)", "Bombchus (20)"]},
    "no Bow": {"less": ["Bow"]},
    "no Lens": {"less": ["Lens of Truth"]},
    "no Magic Beans": {"less": ["Magic Bean", "Magic Bean Pack"]},
    "no Nocturne": {"less": ["Nocturne of Shadow"]},
    "no Song of Time": {"less": ["Song of Time"]},
    "no Zelda's Lullaby": {"less": ["Zeldas Lullaby"]},
    "no Gerudo Card": {"less": ["Gerudo Membership Card"]},
    "no Ruto's Letter": {"less": ["Rutos Letter"]},
    "no Weird Egg": {"less": ["Weird Egg", "Chicken"]},
    "no Master Sword": {"less": ["Master Sword"]},
    "no Ocarina of Time": {"less": ["Ocarina"], "add": ["Ocarina"]},
    "no Song of Time/Hover Boots": {"less": ["Song of Time", "Hover Boots"]},
    "no Song of Time/Hover Boots/Hookshot": {"less": ["Song of Time", "Hover Boots", "Progressive Hookshot"]},
    "no Longshot/Hover Boots": {"less": ["Progressive Hookshot", "Hover Boots"], "add": ["Progressive Hookshot"]},
    "no Gerudo Card/Longshot": {"less": ["Gerudo Membership Card", "Progressive Hookshot"], "add": ["Progressive Hookshot"]},
    "no Nocturne/Hookshot": {"less": ["Nocturne of Shadow", "Progressive Hookshot"]},
    "no Silver Gauntlets/beans": {"less": ["Progressive Strength Upgrade", "Magic Bean", "Magic Bean Pack"],
                                  "add": ["Progressive Strength Upgrade"]},
    "child: Sticks only": {"only": ["Deku Stick Capacity"]},
    "child: Sticks, Ocarina": {"only": ["Deku Stick Capacity", "Ocarina"]},
    "child: Sticks, Ocarina, Goron Bracelet": {"only": ["Deku Stick Capacity", "Ocarina", "Progressive Strength Upgrade"]},
    "child: Sticks, Ocarina, Boomerang, bombs, Song of Storms": {"only": ["Deku Stick Capacity", "Ocarina", "Boomerang",
                                                                         "Bomb Bag", "Song of Storms"]},
    "child: Sticks, Bombs": {"only": ["Deku Stick Capacity", "Bomb Bag"]},
    "child: Sticks, Din's Fire, Lens, Lullaby": {"only": ["Deku Stick Capacity", "Dins Fire", "Magic Meter",
                                                          "Lens of Truth", "Zeldas Lullaby", "Ocarina",
                                                          "Kokiri Sword", "Slingshot"]},
}
MAJOR_TYPES = {"Chest", "GS Token", "Collectable", "NPC", "Song", "BossHeart", "Freestanding", "Scrub", "GrottoScrub",
               "Shop", "MaskShop", "Cutscene", "Boss", "SilverRupee", "Beehive", "Pot", "Crate", "FlyingPot",
               "SmallCrate", "RupeeTower", "Drop", "HintStone"}


def tricks_data():
    return json.load(open(os.path.join(HERE, "data", "rando", "remake_glitch_tricks.json"), encoding="utf-8"))


@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def build(settings_path=DEFAULT_SETTINGS, tricks=(), seed=1):
    """The world as the generator builds it (all enabled plugins' logic and before_fill), before the fill."""
    import generate
    Main = generate.ootr()[0]

    class Stop(Exception):
        pass
    got = {}

    def stop(worlds):
        got["world"] = worlds[0]
        raise Stop()
    orig_place, orig_load = Main.place_items, generate.load_settings

    def load(path, preset=None):
        d = orig_load(path, preset)
        d["allowed_tricks"] = sorted(set(d.get("allowed_tricks", [])) | set(tricks))
        return d
    Main.place_items, generate.load_settings = stop, load
    try:
        with _quiet():
            generate.generate(seed, settings_path)
    except Stop:
        pass
    finally:
        Main.place_items, generate.load_settings = orig_place, orig_load
    return got["world"]


def _pool(world):
    items = list(world.itempool)
    items += [loc.item for loc in world.get_locations() if loc.item is not None and loc.type != "Event"]
    return [i for i in items if i.solver_id is not None]


def _inventory(world, state):
    from Item import ItemFactory
    if "only" in state:
        return [ItemFactory(n, world) for n in state["only"]]
    less = state.get("less", [])
    out = [i for i in _pool(world) if not any(i.name == n or i.name.startswith(n + " (") for n in less)]
    out += [ItemFactory(n, world) for n in state.get("add", [])]
    return out


def reachable(world, items):
    """Names of the non-event locations either age reaches with these items (events collected as reached)."""
    from Search import Search
    search = Search([world.state.copy()])
    for i in items:
        search.collect(i)
    events = [loc for loc in world.get_locations() if loc.type == "Event" and loc.item is not None]
    search.collect_locations(events)
    # Shop items are left out. Their rules follow the shop's random prices, which differ between two builds.
    checks = [loc for loc in world.get_locations() if loc.type not in ("Event", "Shop", "MaskShop")]
    return {loc.name: loc.type for loc in search.iter_reachable_locations(checks)}


def routes(t, untested=False):
    import parity.glitches as g
    return g.live_routes(None, t, untested)


@contextlib.contextmanager
def _untested(on=True):
    import parity.glitches as g
    old, g.UNTESTED_ROUTES = g.UNTESTED_ROUTES, on
    try:
        yield
    finally:
        g.UNTESTED_ROUTES = old


def check(settings_path=DEFAULT_SETTINGS):
    """Every route (candidates too) is well formed, lands on a spot the world has, and is still in that spot's rule
    after every plugin's before_fill. Returns the problems."""
    import re
    d = tricks_data()["tricks"]
    problems, ids, checked = [], set(), [0]
    for name, t in d.items():
        for key in ("name", "description", "age", "items", "sources"):
            if not t.get(key):
                problems.append(f"{name}: no {key}")
        for r in t.get("rules", []) + t.get("candidates", []):
            rid = r.get("id")
            if not rid or rid in ids:
                problems.append(f"{name}: missing or repeated id {rid!r}")
            ids.add(rid)
            for key in ("region", "kind", "target", "add", "confidence"):
                if not r.get(key):
                    problems.append(f"{name} {rid}: no {key}")
            if r in t.get("rules", []) and r.get("confidence") != "high" and not r.get("verified"):
                problems.append(f"{name} {rid}: a live rule must be high confidence (or verified); move it to candidates")
            if r in t.get("candidates", []) and not (r.get("test") or r.get("note") or r.get("refuted")):
                problems.append(f"{name} {rid}: a candidate needs a 'test' (what to try in the game)")
    import parity.glitches as g
    names = [n for n, t in d.items() if not g.unmodeled(t, n)]  # all-refuted or blocked tricks can't be turned on
    preset = json.load(open(PRESET, encoding="utf-8"))["settings"]
    if preset.get("logic_rules") != g.GLITCHED or preset.get("allowed_tricks"):
        problems.append(f"config/glitched_settings.json should be logic_rules {g.GLITCHED} alone (it turns on every "
                        f"trick with live routes: {g.glitched_tricks()})")
    with _untested():
        w = build(settings_path, names)
    for name, t in d.items():
        for r in t.get("rules", []) + t.get("candidates", []):
            if r.get("refuted") or r.get("blocked") or name not in names:
                continue
            if r["kind"] == "helper":
                continue
            try:
                s = g._spot(w, r["region"], r["kind"], r["target"])
            except Exception as e:  # noqa: BLE001
                problems.append(f"{name} {r.get('id')}: {e}")
                continue
            if s is None:
                if r.get("optional"):
                    print(f"note: {name} {r.get('id')}: optional spot {r['target']!r} not in this world")
                else:
                    problems.append(f"{name} {r.get('id')}: no {r['kind']} {r['target']!r} in {r['region']!r}")
                continue
            checked[0] += 1
            core = re.sub(r"\s+", " ", g._route(name, r))
            if core not in re.sub(r"\s+", " ", s.rule_string or ""):
                problems.append(f"{name} {r.get('id')}: its route is no longer in the rule of {s.name} (a later "
                                f"plugin replaced the rule): {s.rule_string[:200]}")
    print(f"{checked[0]} routes found in place in the built world")
    return problems


def coverage(settings_path, names, out=None):
    data = tricks_data()["tricks"]
    import parity.glitches as g
    names = names or [n for n, t in data.items() if not g.unmodeled(t, n)]
    base = build(settings_path)
    base_reach = {s: reachable(base, _inventory(base, st)) for s, st in STATES.items()}
    report = {}
    for name in names:
        t = data[name]
        row = {"name": t["name"], "live_routes": len(routes(t)), "candidates": len(t.get("candidates", [])) -
               sum(1 for r in t.get("candidates", []) if r.get("verified"))}
        for label in ("live", "untested"):
            if label == "live" and not row["live_routes"]:
                row[label] = {"checks": 0, "major": 0, "by_state": {}, "examples": []}
                continue
            if label == "untested" and not row["candidates"]:
                row[label] = row["live"]
                continue
            try:
                with _untested(label == "untested"):
                    w = build(settings_path, [name])
            except Exception as e:  # noqa: BLE001 - report it, go on with the next trick
                row[label] = {"error": str(e)[:300]}
                continue
            gained, by_state = {}, {}
            for s, st in STATES.items():
                new = {k: v for k, v in reachable(w, _inventory(w, st)).items() if k not in base_reach[s]}
                if new:
                    by_state[s] = len(new)
                gained.update(new)
            row[label] = {"checks": len(gained), "major": sum(1 for v in gained.values() if v in MAJOR_TYPES),
                          "by_state": by_state, "examples": sorted(gained)[:400]}
        report[name] = row
        print(f"{name}: {row['live_routes']} live routes, {row['candidates']} candidates; "
              f"live opens {row['live'].get('checks', '?')} checks, with untested routes "
              f"{row['untested'].get('checks', '?')}", flush=True)
    if out:
        json.dump(report, open(out, "w", encoding="utf-8"), indent=1)
    return report


def uses(seed, settings_path, names, untested=False):
    """Is the seed (generated with the tricks) beatable without them, and which playthrough checks need them?"""
    import generate
    from Item import ItemFactory
    from Search import Search
    tricks = list(names)
    orig_load = generate.load_settings

    def load(path, preset=None):
        d = orig_load(path, preset)
        d["allowed_tricks"] = sorted(set(d.get("allowed_tricks", [])) | set(tricks))
        return d
    generate.load_settings = load
    try:
        with _quiet(), _untested(untested):
            got = generate.generate(seed, settings_path)
    finally:
        generate.load_settings = orig_load
    spoiler, w_on = got[1], got[2]
    w_off = build(settings_path, (), seed)
    for loc in w_on.get_locations():
        if loc.item is None or loc.type == "Event":
            continue
        try:
            target = w_off.get_location(loc.name)
        except KeyError:
            continue
        if target.item is None:
            try:
                item = ItemFactory(loc.item.name, w_off)
            except KeyError:  # hint-stone and other pseudo items
                continue
            w_off.push_item(target, item)
            target.locked = True

    def explore(world):
        s = Search([world.state.copy()])
        s.collect_locations([x for x in world.get_locations() if x.item is not None and x.item.solver_id is not None])
        return s
    s_on, s_off = explore(w_on), explore(w_off)
    reach_on = {x.name for x in w_on.get_locations() if s_on.visited(x)}
    reach_off = {x.name for x in w_off.get_locations() if s_off.visited(x)}
    play = [loc.name for sphere in spoiler.playthrough.values() for loc in sphere]
    needs = [n for n in play if n in reach_on and n not in reach_off]
    beat_off = s_off.can_beat_game(scan_for_items=False)
    return {"seed": seed, "tricks": tricks, "beatable_with": s_on.can_beat_game(scan_for_items=False),
            "beatable_without": beat_off, "playthrough_checks_needing_tricks": needs,
            "checks_only_with_tricks": len(reach_on - reach_off)}


# Checklist
AREA_ORDER = ["Kokiri Forest", "Lost Woods", "Sacred Forest Meadow", "Hyrule Field", "Lon Lon Ranch", "Market",
              "Hyrule Castle", "Kakariko Village", "Graveyard", "Death Mountain Trail", "Goron City",
              "Death Mountain Crater", "Zora's River", "Zora's Domain", "Zora's Fountain", "Lake Hylia",
              "Gerudo Valley", "Gerudo's Fortress", "Haunted Wasteland", "Desert Colossus", "Deku Tree",
              "Dodongo's Cavern", "Jabu Jabu's Belly", "Bottom of the Well", "Forest Temple", "Fire Temple",
              "Water Temple", "Ice Cavern", "Shadow Temple", "Spirit Temple", "Gerudo Training Ground",
              "Ganon's Castle", "Ganon's Tower"]
PREFIX_AREA = [("KF ", "Kokiri Forest"), ("Kokiri Forest", "Kokiri Forest"), ("LW ", "Lost Woods"),
               ("Lost Woods", "Lost Woods"), ("SFM", "Sacred Forest Meadow"), ("Sacred Forest", "Sacred Forest Meadow"),
               ("HF ", "Hyrule Field"), ("LLR", "Lon Lon Ranch"), ("Lon Lon Ranch", "Lon Lon Ranch"), ("Market", "Market"), ("ToT", "Market"),
               ("Hyrule Castle", "Hyrule Castle"), ("HC ", "Hyrule Castle"), ("Kak", "Kakariko Village"),
               ("Kakariko", "Kakariko Village"), ("Graveyard", "Graveyard"), ("Death Mountain Crater", "Death Mountain Crater"),
               ("DMC", "Death Mountain Crater"), ("Death Mountain", "Death Mountain Trail"), ("DMT", "Death Mountain Trail"),
               ("Goron City", "Goron City"), ("GC ", "Goron City"), ("Zora River", "Zora's River"), ("ZR ", "Zora's River"),
               ("Zoras Domain", "Zora's Domain"), ("ZD ", "Zora's Domain"), ("Zoras Fountain", "Zora's Fountain"),
               ("ZF ", "Zora's Fountain"), ("Lake Hylia", "Lake Hylia"), ("LH ", "Lake Hylia"),
               ("Gerudo Valley", "Gerudo Valley"), ("GV ", "Gerudo Valley"), ("Gerudo Fortress", "Gerudo's Fortress"),
               ("GF ", "Gerudo's Fortress"), ("Hideout", "Gerudo's Fortress"), ("Wasteland", "Haunted Wasteland"),
               ("Haunted Wasteland", "Haunted Wasteland"), ("Desert Colossus", "Desert Colossus"),
               ("Colossus", "Desert Colossus"), ("Remake Spirit Temple", "Desert Colossus"), ("Deku Tree", "Deku Tree"),
               ("Queen Gohma", "Deku Tree"), ("Dodongos Cavern", "Dodongo's Cavern"), ("King Dodongo", "Dodongo's Cavern"),
               ("Jabu", "Jabu Jabu's Belly"), ("Barinade", "Jabu Jabu's Belly"), ("Bottom of the Well", "Bottom of the Well"),
               ("Forest Temple", "Forest Temple"), ("Phantom Ganon", "Forest Temple"), ("Fire Temple", "Fire Temple"),
               ("Volvagia", "Fire Temple"), ("Water Temple", "Water Temple"), ("Morpha", "Water Temple"),
               ("Ice Cavern", "Ice Cavern"), ("Shadow Temple", "Shadow Temple"), ("Bongo Bongo", "Shadow Temple"),
               ("Spirit Temple", "Spirit Temple"), ("Twinrova", "Spirit Temple"),
               ("Gerudo Training", "Gerudo Training Ground"), ("Ganons Castle", "Ganon's Castle"),
               ("Ganons Tower", "Ganon's Tower"), ("Ganondorf", "Ganon's Tower"), ("Root", "Anywhere")]


def area_of(region):
    for prefix, area in PREFIX_AREA:
        if region.startswith(prefix):
            return area
    return "Other"


def _what(r):
    if r["kind"] == "exit":
        return f"{r['region']} -> {r['target']}"
    if r["kind"] == "event":
        return f"event '{r['target']}' at {r['region']}"
    return f"{r['target']} (in {r['region']})"


def checklist(out=CHECKLIST):
    d = tricks_data()
    helpers = json.load(open(os.path.join(HERE, "data", "rando", "logic", "glitches.json"), encoding="utf-8"))["helpers"]
    rows, gone = [], []
    for name, t in d["tricks"].items():
        for lst, live in ((t.get("rules", []), True), (t.get("candidates", []), False)):
            for r in lst:
                if r.get("refuted") or r.get("blocked"):
                    gone.append((name, t, r))
                    continue
                status = "live" if live else ("live (verified)" if r.get("verified") else "to test")
                rows.append((area_of(r["region"]), name, t, r, status))
    order = {a: i for i, a in enumerate(AREA_ORDER + ["Anywhere", "Other"])}
    rows.sort(key=lambda x: (order.get(x[0], 99), not x[4].startswith("live"), x[1], x[3].get("id", "")))
    n_live = sum(1 for x in rows if x[4].startswith("live"))
    n_test = len(rows) - n_live
    lines = ["# Remake glitch logic: in-game checklist", "",
             "Generated by `python tools/rando/glitch_report.py checklist` from `data/rando/remake_glitch_tricks.json`; "
             "don't edit it by hand.", "",
             f"{n_live} live routes (in logic when their trick is on) and {n_test} routes to test, grouped by area.", "",
             "* **live**: a source shows the route (high confidence), so the trick's logic uses it. One try in the game "
             "still helps.",
             "* **to test**: a candidate. No seed's logic uses it until it is marked verified (below).", "",
             "## Before testing", "",
             "* **IJSC height cap.** A jump slash cancel chain never rises above the height of Link's last normal jump or "
             "forward hop (a global height, carried across maps). Save and load from the title screen to remove the cap; "
             "an age change through the Master Sword also resets it.",
             "* **IJSC needs a second quick-menu item** to swap to (any of: Ocarina, Deku Nuts, bombs, bombchus, a "
             "bottle, Lens of Truth, a spell, Magic Beans, Slingshot or Boomerang as child, Bow or Hookshot as adult).",
             "* **Ceilings end a chain**; invisible walls stop it.",
             "* **Don't skip the Hyrule Field owl** with a jump: the time of day then stays frozen in the morning for the "
             "whole file, and night-only checks are lost.",
             "* Test on the game version you play (every route here is meant for 1.1.1; Hookshot Storage is 1.0 only and "
             "is in no route).", "",
             "## How to record a result", "",
             "1. Do the route on a test save with only the items it lists, at the age it says.",
             "2. Works: add `\"verified\": \"YYYY-MM-DD\"` to that route in `data/rando/remake_glitch_tricks.json` (it joins its "
             "trick's logic). Doesn't work: add `\"refuted\": \"YYYY-MM-DD: what happened\"` (it never joins any logic). "
             "Works only with something else: change its `add` and verify it.",
             "3. Run `python tools/rando/glitch_report.py check` and `python tools/rando/glitch_report.py checklist`.", "",
             "## Helpers the routes use", ""]
    lines += [f"* `{k}` = `{v}`" for k, v in helpers.items()]
    lines += ["", "## Tricks", ""]
    for name, t in d["tricks"].items():
        live = len([r for r in t.get("rules", []) if not r.get("refuted")]) + len([r for r in t.get("candidates", []) if r.get("verified") and not r.get("refuted") and not r.get("blocked")])
        cands = len([r for r in t.get("candidates", []) if not (r.get("verified") or r.get("refuted") or r.get("blocked"))])
        lines.append(f"* `{name}`: **{t['name']}**: {live} live, {cands} to test. Needs: {t.get('requires') or t.get('items', '?')}")
    area = None
    for a, name, t, r, status in rows:
        if a != area:
            lines += ["", f"## {a}", ""]
            area = a
        box = "x" if status.startswith("live (verified)") else " "
        lines.append(f"- [{box}] **{r.get('id', '')}** ({status}, {r.get('confidence', '?')}; {t['name']}): {_what(r)}")
        test = r.get("test") or r.get("note") or ""
        if test:
            lines.append(f"  - Try: {test}")
        if r.get("note") and r.get("test"):
            lines.append(f"  - Note: {r['note']}")
        lines.append(f"  - Rule added: `{r['add']}`")
        if r.get("source"):
            lines.append(f"  - Source: {r['source']}")
        else:
            lines.append(f"  - Source: none shows this spot yet; the technique: {(t.get('sources') or ['?'])[0]}")
    if d.get("open_tests"):
        lines += ["", "## Questions the logic waits on", ""]
        for q in d["open_tests"]:
            lines.append(f"- [ ] **{q['id']}**: {q['question']}")
            lines.append(f"  - If yes: {q['if_yes']}")
    if gone:
        lines += ["", "## Not in any logic (refuted or blocked)", ""]
        for name, t, r in gone:
            lines.append(f"- **{r.get('id', '')}** ({t['name']}): {_what(r)}: {r.get('refuted') or r.get('blocked')}")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{out}: {n_live} live, {n_test} to test, {len(gone)} not in logic")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("coverage", "checklist", "uses", "check"))
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--settings", default=DEFAULT_SETTINGS)
    ap.add_argument("--tricks", default="")
    ap.add_argument("--untested", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    names = [x for x in a.tricks.split(",") if x]
    if a.cmd == "coverage":
        coverage(a.settings, names, a.json)
    elif a.cmd == "checklist":
        checklist(a.arg or CHECKLIST)
    elif a.cmd == "check":
        problems = check(a.settings)
        print("\n".join(problems) or "glitch routes: no problems")
        sys.exit(1 if problems else 0)
    else:
        print(json.dumps(uses(int(a.arg), a.settings, names, a.untested), indent=1))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    main()
