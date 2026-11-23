"""Read-back check that every placed dungeon item's give path reaches its credit (dungeons plugin,
parity/_gaps_check.py READERS "dungeon_items").

usage: python tools/rando/parity/_dungeons_routes.py OUT_DIR [ROMFS]
  (a seed folder: spoiler.json and patch/; works on any build, old ones too: the items come from the spoiler)

It reads the built patch, not the plan, for each OoTR location holding a dungeon item (small keys, key rings, boss
keys, maps, compasses, silver rupees and pouches, the Treasure Chest Game's keys, Triforce pieces) and each chest
holding an item given by an entry of its own (dungeons.chest_call_item: a soul, the Skeleton Key, the Magic Bean
Pack).
- A chest (the core's, the dungeons plugin's kept chests, the chests plugin's own, every remake chest of the
  location). Its placement in every level file holding it either holds the plain item (Item_Dungeon_*) and stands in
  that item's own dungeon, as a chest type whose own add credits it (plain_ok), or holds the item's carrier with the
  dungeon-item scene's scene ID. That ID's EventSetting row runs the scene's entry, and its branch for the carrier
  calls the item's host entry (the big chest's _Big variant).
- Any other location. Its credit entry (Dm_SY_GetInEvent:Rando_DI_Call_<item>) calls the item's host entry with the
  item's own arguments (dungeons.host_call: its dungeon's save-data rows and map, its silver-rupee puzzle). The patch
  has to hold at least one give step per location that calls it, each reachable from one of its flowchart's vanilla
  entry points. That's a scene step calling the entry, a scrub sale handing the entry's name to the one-time sale
  whose intercept pays and calls it, the carpet salesman's sale copy (SimpleShop) calling it, or a resident get
  scene's copy of its credit steps (in the air or water) next to a standing branch calling it.
Prints problems and exits 1 if there are any."""
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GET_FILE = "Dm_SY_GetInEvent"
SCRUB_FILE, SCRUB_GRAPH = "Enemy_Scrub_Business_Common", "Rando_HoldHandover"
SHOP_FILE = "SimpleShop"
if os.path.join(HERE, "tools") not in sys.path:  # romtools, for the default below
    sys.path.append(os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()


# OoTR locations whose dungeon item no give step hands over, and what credits it instead (each has its own read-back)
ELSEWHERE = {"Gift from Sages": "Ganon's boss lock opens on OoTR's condition (_dungeons_ganon, _gaps ganon_bosskey)"}
LAKE_TAGS = {"LH Underwater Item": 0, "LH Sun": 1}  # the get-scene hook's own branches (_songs_trade_lake.TAG)
TAG_NOTE = re.compile(r"^(.*): (.*) \(the heart's get scene gives it, tag (\d+)\)$")


def note(world, settings):
    """The note dungeons.world_plan writes: {"items": {OoTR location: dungeon item}, "silver_credit": bool, "tags":
    {OoTR location: the get-scene hook's tag giving it}}. Tags cover the drops plugin's heart spots, scene drops and
    flagless drops (their plan runs before the dungeons plugin's) and the lake pickups' fixed tags."""
    from . import dungeons as dg
    items = {loc.name: loc.item.name for loc in world.get_locations()
             if loc.item is not None and dg.dungeon_item(loc.item.name) is not None}
    tags = {n: t for n, t in LAKE_TAGS.items() if n in items}
    dr = sys.modules.get("parity.drops")
    for p in (dr.get_scene_pickups(world) if dr is not None and hasattr(dr, "get_scene_pickups") else []):
        for n in str(p["location"]).split(", "):
            if n in items:
                tags[n] = p["tag"]
    calls = {loc.name: loc.item.name for loc in world.get_locations()
             if loc.item is not None and ((dg.chest_call_item(loc.item.name) and dg.chest_calls_ok(loc.name))
                                          or (hasattr(dg, "story_prog") and dg.story_prog(loc.item.name, loc.name)))}
    return {"items": dict(sorted(items.items())), "tags": dict(sorted(tags.items())),
            "chest_calls": dict(sorted(calls.items())),
            "silver_credit": getattr(settings, "shuffle_silver_rupees", "vanilla") in dg.silver_shuffle.SHUFFLED}


def _credit_mark(dg, item):
    """What the item's credit writes first (a save-data name, or the call it makes), for checking the resident copy."""
    st = dg._credit(item, None)[0]
    return st.get("call") or (st.get("params") or {}).get("GameDataName")


class _Flows:
    """Patched event flows (patch over the game's files), parsed once each."""

    def __init__(self, fs, van):
        self.fs, self.van, self.cache = fs, van, {}

    def get(self, name):
        if name not in self.cache:
            from evfl import Evfl
            try:
                fcs = Evfl(self.fs.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts
            except (FileNotFoundError, OSError, KeyError):
                fcs = []
            try:
                vfcs = Evfl(self.van.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts
            except (FileNotFoundError, OSError, KeyError):
                vfcs = []
            vanilla_eps = {f["name"]: set(f["entry_points"]) for f in vfcs}
            self.cache[name] = [(fc, vanilla_eps.get(fc["name"], set())) for fc in fcs]
        return self.cache[name]


def _nexts(e):
    out = [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])] + list(e.get("forks", []))
    return [x for x in out if x is not None and x != 0xFFFF]


def _reachable(fc, starts):
    seen, todo = set(), list(starts)
    while todo:
        i = todo.pop()
        if i in seen or i >= len(fc["events"]):
            continue
        seen.add(i)
        todo += _nexts(fc["events"][i])
    return seen


def _params(e):
    return {k: v.get("value") for k, v in (((e.get("params") or {}).get("items")) or {}).items()}


def _call(fc, e):
    return f"{e.get('flowchart') or fc['name']}:{e['entry_point']}" if e["type"] in ("subflow", "subflow_switch") \
        else None


def _story_route(flows, dg, route, rows):
    """(scene kind, None) if a story chest's scene runs the item scene (dungeons.STORY_ROUTES), else (None, why)."""
    fc = next((fc for fc, _ in flows.get(route["file"]) if fc["name"] == route["file"]), None)
    if fc is None:
        return None, f"has no flow {route['file']}"
    if route.get("entry"):  # Mido's chests: after the flag, a call of the item scene's entry
        want = f"{route['file']}:{dg.SCENE_ENTRY[route['chest']]}"
        if not any(_call(fc, fc["events"][i]) == want for i in _entry_steps(fc, route["entry"])):
            return None, f"never calls {want} from {route['entry']}"
        return route["chest"], None
    if route.get("branch"):  # the state's branch reaches a transition naming the item scene's row
        b = next((x for x in fc["events"] if x["name"] == route["branch"]), None)
        nxt = next((c["next"] for c in (b or {}).get("cases", []) if c["value"] == route["case"]), None)
        e = fc["events"][nxt] if nxt is not None and nxt < len(fc["events"]) else None
        if e is None or _params(e).get("EventName") != dg.ROWS[route["chest"]]:
            return None, f"branch {route['branch']}/{route['case']} doesn't run {dg.ROWS[route['chest']]}"
        return route["chest"], None
    e = next((x for x in fc["events"] if x["name"] == route["event"]), None)
    if e is None or _params(e).get("EventName") != dg.ROWS[route["chest"]]:
        return None, f"step {route['event']} doesn't run {dg.ROWS[route['chest']]}"
    return route["chest"], None


def _entry_steps(fc, entry):
    ep = fc["entry_points"].get(entry)
    return [] if ep is None else sorted(_reachable(fc, [ep["main"]]))


def _vanilla_reach(fc, vanilla_eps):
    """Steps reachable from the flowchart's vanilla entry points, following calls into the same flowchart's own
    entries. A plugin's graph is an entry of its own, entered through a routed vanilla step or a local call."""
    starts = [fc["entry_points"][n]["main"] for n in vanilla_eps if n in fc["entry_points"]]
    seen = _reachable(fc, starts)
    while True:
        more = set()
        for i in seen:
            e = fc["events"][i]
            if e["type"] in ("subflow", "subflow_switch") and (e.get("flowchart") or fc["name"]) == fc["name"]:
                ep = fc["entry_points"].get(e["entry_point"])
                if ep is not None and ep["main"] not in seen:
                    more.add(ep["main"])
        if not more:
            return seen
        seen |= _reachable(fc, more)


def verify(patch, note, romfs, plan_files=None):
    sys.path.insert(0, os.path.join(HERE, "tools"))
    if os.path.join(HERE, "vendor", "ootr") not in sys.path:  # (LocationList: OoTR's vanilla items)
        sys.path.append(os.path.join(HERE, "vendor", "ootr"))
    from romtools import Romfs, byml_load
    from . import dungeons as dg
    dg.silver_shuffle._state["credit"] = bool(note.get("silver_credit"))
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    flows = _Flows(fs, van)
    bad = []
    levels = {}

    def actors(f):
        if f not in levels:
            levels[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f))[0].get("Actors") or []}
        return levels[f]

    def field(a, dotted):
        v = a
        for k in dotted.split("."):
            v = v.get(k) if isinstance(v, dict) else None
        return v
    rows = byml_load(fs.read("RSDB/EventSetting.Product.111.rstbl.byml.zs"), allow_big=True)[0]
    rows = {r.get("__RowId"): r for r in (rows if isinstance(rows, list) else rows.get("Rows", [])) if isinstance(r, dict)}
    get_fc = next((fc for fc, _ in flows.get(GET_FILE) if fc["name"] == GET_FILE), None)
    if get_fc is None:
        return [f"{GET_FILE}: unreadable"]
    by_call = defaultdict(list)  # location -> how it is given (for the summary)
    tagged = []  # (location, item, tag): given by the get-scene hook's branch for that tag
    try:  # OoTR's vanilla items (as the dungeons plugin corrects them for the remake)
        import LocationList
        vanilla = {n: t[4] for n, t in LocationList.location_table.items()}
    except ImportError:
        vanilla = {}
    call_items = defaultdict(list)  # credit entry -> [locations] given by a give step calling it
    ch = dg._chests_plugin()
    if ch is None:
        import importlib
        try:
            ch = importlib.import_module("parity.chests")
        except ImportError:
            ch = None
    for location, item in sorted(note["items"].items()) + sorted((note.get("chest_calls") or {}).items()):
        info = dg.dungeon_item(item)
        if info is None and (dg.chest_call_item(item) or item in dg.PROGRESSIVE) \
                and location in (note.get("chest_calls") or {}):
            info = (None, None)  # its carrier and the chest's item scene, checked as a dungeon item's
            if dg.chest_rid(location) is None:
                bad.append(f"{location}: {item} listed as a chest's item, but no chest of the patch is there")
                continue
        if info is None:
            bad.append(f"{location}: {item} is not a dungeon item the dungeons plugin knows")
            continue
        kind, dungeon = info
        rid = dg.chest_rid(location)
        if location in ELSEWHERE:
            by_call[location].append(ELSEWHERE[location])
            continue
        if rid is None and vanilla.get(location) == item:
            by_call[location].append("its vanilla item, given by the game itself")
            continue
        if rid is not None:
            also = (ch._also(location) if ch is not None and rid not in dg.REMAKE_OF.values()
                    and hasattr(ch, "_also") else ([], False))
            rids = [rid] + list(also[0])
            for cid in rids:
                r = dg.REWARDS[cid]
                for f in r["files"]:
                    a = actors(f).get(str(r["hash"]))
                    if a is None and cid != rid and also[1]:
                        # a copy that shares the main chest's save flag carries the main chest's instance hash
                        # (parity/chests.py "share" sets its placement's Hash to the main one's)
                        a = actors(f).get(str(dg.REWARDS[rid]["hash"]))
                    if a is None:
                        bad.append(f"{location}: {f} #{r['hash']} is gone")
                        continue
                    content = field(a, r["field"])
                    ev = field(a, "Dynamic.GetEventName")
                    actor = a.get("Gyaml")
                    if content == dg.CARRIER.get(item):
                        scene = next((k for k, row in dg.ROWS.items() if row == ev), None)
                        route = (getattr(dg, "STORY_ROUTES", None) or {}).get(cid)
                        if scene is None and route is not None:  # a story chest: its scene's step runs the item scene
                            scene, why = _story_route(flows, dg, route, rows)
                            if why:
                                bad.append(f"{location}: {f} #{r['hash']} holds {item}'s carrier {content}, but its "
                                           f"story scene {ev!r} {why}")
                                continue
                            ev = dg.ROWS[scene]  # (the row its story scene runs)
                        if scene is None:
                            bad.append(f"{location}: {f} #{r['hash']} holds {item}'s carrier {content} but plays "
                                       f"{ev!r}, not the dungeon-item scene")
                            continue
                        row = rows.get(ev) or {}
                        if row.get("EntryPointName") != dg.SCENE_ENTRY[scene]:
                            bad.append(f"EventSetting {ev}: runs {row.get('EntryPointName')}, not {dg.SCENE_ENTRY[scene]}")
                        entry, _, _ = dg.host_call(item)
                        want = f"{GET_FILE}:{entry}" + (dg.BIG_SUFFIX if scene == "big" else "")
                        cfc = next((fc for fc, _ in flows.get(dg.CHEST_FILE[scene]) if fc["name"] ==
                                    dg.CHEST_FILE[scene]), None)
                        hit = False
                        for i in _entry_steps(cfc, dg.SCENE_ENTRY[scene]) if cfc else []:
                            e = cfc["events"][i]
                            if e["type"] == "switch" and _params(e).get("Value") == content:
                                y = next((c["next"] for c in e.get("cases", []) if c["value"] == dg.YES), None)
                                if y is not None and _call(cfc, cfc["events"][y]) == want:
                                    hit = True
                        if item in dg.PROGRESSIVE:  # the tier Link gets: big, shown per tier, then its window;
                            # first the chest's content display gets deleted (what rises is the tier, not the carrier)
                            want = (dg._tier_window(item) if scene == "big" else want)
                            steps = [cfc["events"][i] for i in _entry_steps(cfc, dg.SCENE_ENTRY[scene])] if cfc else []
                            if not any(e["type"] == "action" and cfc["actors"][e["actor"]]["actions"][e["action"]]
                                       == "EventTriggerTBoxRequestDeleteContentDisplay" for e in steps):
                                bad.append(f"{location}: {dg.SCENE_ENTRY[scene]} never deletes the chest's content "
                                           f"display before {item}'s tier is shown")
                            hit = any(_call(cfc, e) == want for e in steps) if cfc else False
                        if not hit:
                            bad.append(f"{location}: {dg.CHEST_FILE[scene]}:{dg.SCENE_ENTRY[scene]} has no branch "
                                       f"from {content} to {want} ({item})")
                        by_call[location].append(f"chest {scene} scene")
                    elif vanilla.get(location) == item and content == r["item"]:
                        by_call[location].append("its vanilla item in its vanilla chest, untouched")
                    elif content == dg.MODEL.get(kind) or content in ("Item_Dungeon_SmallKey",):
                        area_ok = dungeon in dg.DUNGEONS and r["area"] == dg.DUNGEONS[dungeon]["area"]
                        type_ok = kind == "Small Key" or actor in dg.BIG_CHESTS
                        if kind not in dg.FLAG and kind != "Small Key" or not area_ok or not type_ok:
                            bad.append(f"{location}: {f} #{r['hash']} ({actor}) holds the plain {content}, which "
                                       f"credits the dungeon Link stands in ({r['area']}), not {item}'s")
                        by_call[location].append("plain item in its own dungeon")
                    else:
                        bad.append(f"{location}: {f} #{r['hash']} holds {content!r} with scene {ev!r}: no credit "
                                   f"for {item}")
            continue
        if kind == "Small Key" and location not in dg.CALL_LOCATIONS:
            import drops as drop_tools  # tools/rando/drops.py, the key's own pickup credits the dungeon it lies in
            e = drop_tools.lookup(location)
            if e is not None and drop_tools.KEY_AREA.get(item) == e.get("area"):
                by_call[location].append("its own pickup in its dungeon")
                continue
        entry = dg.call_entry(item)
        if location in note.get("tags", {}):
            tagged.append((location, item, note["tags"][location]))
            continue
        call_items[entry].append((location, item))
    # The standing Dm_SY_Get branch calls the tag's credit entry. In air or water, Dm_SY_Get_WithoutPlayer
    # jumps to a Dm_SY_Get entry for that tag that runs a copy of the credit steps.
    hook = next((fc for fc, _ in flows.get("Dm_SY_Get") if fc["name"] == "Dm_SY_Get"), None) if tagged else None
    for location, item, tag in tagged:
        entry = dg.call_entry(item)
        if hook is None:
            bad.append(f"{location}: Dm_SY_Get unreadable")
            continue
        sw = next((e for e in hook["events"] if e["name"] == "RandoST_LakePickups_tag"), None)
        case = next((c["next"] for c in (sw or {}).get("cases", []) if c["value"] == tag), None)
        if case is None or not any(_call(hook, hook["events"][i]) == f"{GET_FILE}:{entry}"
                                   for i in _reachable(hook, [case])):
            bad.append(f"{location}: the get scene's tag {tag} branch doesn't call {GET_FILE}:{entry} ({item})")
        wp = "RandoST_LakeWP_" + ("letter" if tag == 0 else "arrow") if location in LAKE_TAGS else f"RandoST_HeartWP_{tag}"
        mark = _credit_mark(dg, item)
        steps = [hook["events"][i] for i in _entry_steps(hook, wp)]
        if not any(_call(hook, e) == mark or _params(e).get("GameDataName") == mark for e in steps):
            bad.append(f"{location}: Dm_SY_Get:{wp} (in the air or water) doesn't credit {item} ({mark})")
        by_call[location].append(f"get-scene tag {tag}")
    # The credit entries. Each one calls its host entry with the item's own arguments.
    needed = {dg.call_entry(i): (i, [l for l, _ in locs]) for e, locs in call_items.items() for _, i in locs[:1]}
    for location, item, _ in tagged:
        needed.setdefault(dg.call_entry(item), (item, []))[1].append(location)
    for entry, (item, locs) in sorted(needed.items()):
        host, params, _ = dg.host_call(item)
        steps = _entry_steps(get_fc, entry)
        calls = [get_fc["events"][i] for i in steps if _call(get_fc, get_fc["events"][i])]
        if not calls:
            bad.append(f"{GET_FILE}: no credit entry {entry} ({item}; {', '.join(locs)})")
            continue
        c = calls[0]
        if _call(get_fc, c) != f"{GET_FILE}:{host}" or _params(c) != params:
            bad.append(f"{GET_FILE}:{entry} calls {_call(get_fc, c)} {_params(c)}, want {host} {params} ({item})")
        if host not in get_fc["entry_points"]:
            bad.append(f"{GET_FILE}: no host entry {host} ({item})")
    # The give steps that call them, or hand their name to a sale that calls them. These are steps reachable from a
    # vanilla entry point, a scene ID's entry (EventSetting) or an entry such a step calls, across the patched files.
    import glob
    names = sorted({os.path.basename(p_).split(".")[0]
                    for p_ in glob.glob(os.path.join(patch, "Event", "EventFlow", "*.bfevfl.zs"))})
    row_eps = defaultdict(set)
    for r in rows.values():
        m = re.search(r"/([^/]+)\.evfc$", str(r.get("FlowchartFileName", "")))
        if m and r.get("EntryPointName"):
            row_eps[m.group(1)].add(r["EntryPointName"])
    fcs = {}
    for name in names:
        for fc, veps in flows.get(name):
            fcs[fc["name"]] = (name, fc, set(veps) | row_eps.get(fc["name"], set()))
    live = {fname: set() for fname in fcs}
    todo = [(fname, ep) for fname, (_, fc, eps) in fcs.items() for ep in eps if ep in fc["entry_points"]]
    done = set()
    while todo:
        fname, ep = todo.pop()
        if (fname, ep) in done or fname not in fcs:
            continue
        done.add((fname, ep))
        fc = fcs[fname][1]
        if ep not in fc["entry_points"]:
            if ep.startswith("Rando_DI_"):
                bad.append(f"{fname}: a step calls {ep}, which isn't there")
            continue
        for i in _reachable(fc, [fc["entry_points"][ep]["main"]]):
            live[fname].add(i)
            e = fc["events"][i]
            if e["type"] in ("subflow", "subflow_switch"):
                todo.append((e.get("flowchart") or fname, e["entry_point"]))
    sites = defaultdict(list)  # credit entry -> [file:event]
    scrub_markers = defaultdict(int)
    for fname, (name, fc, _) in sorted(fcs.items()):
        for i in sorted(live[fname]):
            e = fc["events"][i]
            target = _call(fc, e)
            if target and target.startswith(f"{GET_FILE}:Rando_DI_Call_"):
                sites[target.split(":", 1)[1]].append(f"{fname}:{e['name']}")
            if fname == SCRUB_FILE and e["type"] in ("subflow", "subflow_switch"):
                v = _params(e).get("ActorName")
                if isinstance(v, str) and v.startswith("Rando_DI_Call_"):
                    scrub_markers[v] += 1
    # a scrub sale hands the entry's name over, and the intercept (inside the vanilla one-time sale) has to pay
    # and call it
    if scrub_markers:
        sfc = fcs.get(SCRUB_FILE, (None, None))[1]
        steps = _entry_steps(sfc, SCRUB_GRAPH) if sfc else []
        for marker, n in sorted(scrub_markers.items()):
            ok = False
            for i in steps:
                e = sfc["events"][i]
                if e["type"] == "switch" and _params(e).get("Value") == marker:
                    j = next((c["next"] for c in e.get("cases", []) if c["value"] == dg.YES), None)
                    for k in sorted(_reachable(sfc, [j])) if j is not None else []:
                        if _call(sfc, sfc["events"][k]) == f"{GET_FILE}:{marker}":
                            ok = True
            if not ok:
                bad.append(f"{SCRUB_FILE}:{SCRUB_GRAPH}: a scrub sells {marker}, but the intercept doesn't call it")
            else:
                sites[marker] += [f"{SCRUB_FILE}: scrub sale"] * n
    # The carpet salesman is counted above. His SimpleShop copy's Buy calls the entry and is reached from his sale step.
    for entry, locs in sorted(call_items.items()):
        got = [x for x in sites.get(entry, []) if not x.startswith("Dm_SY_Get:RandoST_")]  # hook tags checked above

        if len(got) < len(locs):
            bad.append(f"{entry}: {len(locs)} location(s) hold {locs[0][1]} ({', '.join(l for l, _ in locs)}), "
                       f"{len(got)} reachable give step(s) call it ({got})")
    return bad


def main(out_dir, romfs=DEFAULT_ROMFS):
    sys.path[:0] = [os.path.join(HERE, "tools", "rando"), os.path.join(HERE, "tools"), os.path.join(HERE, "vendor", "ootr")]
    spoiler = json.load(open(os.path.join(out_dir, "spoiler.json"), encoding="utf-8"))
    import importlib
    dg = importlib.import_module("parity.dungeons")
    importlib.import_module("parity.chests")
    silver = spoiler.get("settings", {}).get("shuffle_silver_rupees", "vanilla") in dg.silver_shuffle.SHUFFLED
    dg.silver_shuffle._state["credit"] = silver
    items = {}
    for loc, v in spoiler.get("locations", {}).items():
        name = v["item"] if isinstance(v, dict) else v
        if dg.dungeon_item(name) is not None:
            items[loc] = name
    tags = {n: t for n, t in LAKE_TAGS.items() if n in items}
    plan = json.load(open(os.path.join(out_dir, "plan.json"), encoding="utf-8"))
    for line in plan.get("songs_trade_notes", []):  # (the plan's own record of the hook's tags)
        m = TAG_NOTE.match(line)
        if m:
            for name in m.group(1).split(", "):
                if name in items:
                    tags[name] = int(m.group(3))
    n = {"items": items, "silver_credit": silver, "tags": tags}
    from parity import _dungeons_routes as me
    bad = me.verify(os.path.join(out_dir, "patch"), n, romfs)
    for b in bad:
        print(b)
    print(f"dungeon items: {len(items)} placed, {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
