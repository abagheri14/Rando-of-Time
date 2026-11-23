"""Read-back: every item a give step hands over by calling an entry of its own really gets given there. That covers
souls, the Magic Bean Pack, the Kokiri wallet, progressive items at steps that can't hand them over themselves,
the Treasure Chest Game salesman, and OoTR's "Nothing" given by the get scene. Dungeon items have their own
read-back (_dungeons_routes), and ice traps have the chests plugin's.

usage: python tools/rando/parity/_call_routes.py OUT_DIR [ROMFS] [--patch PATCH_DIR]
  (a seed folder: plan.json, spoiler.json and patch/; --patch reads another patch folder, for negative controls)

We read the built patch, not the plan's own claims. The plan says where each give was put and the spoiler what each
location holds, and the two have to agree:
1. core rewards whose spec calls an entry (make_patch scene_call_ops). Every file of the reward has a step calling
   the entry, reachable from one of its flowchart's vanilla entry points (or a scene ID's entry), and the replaced
   give step isn't reachable anymore.
2. Business Scrub sales whose ActorName is a call marker (progressive.CALL_MARKERS). The intercept compares the
   marker and its "yes" branch calls the entry. The carpet salesman's SimpleShop copy calls its entry.
3. the get-scene hook (Dm_SY_Get). Standing, a location's tag branch (songs_trade_notes "... tag N") calls its
   item's entry, and in the air or water its own entry copies the give (a soul's flag or message, the bean pack's
   add, the tier entry next to the get window). OoTR's "Nothing" (remake_empty_object_contents "nothing") reaches
   no give at all.
4. the hideout jails' and the Treasure Chest Game salesman's give steps call the planned entry, reached from the
   vanilla step they follow.
5. every entry called exists (Dm_SY_GetInEvent / GetPouchContent), a tier entry names each tier of its item, and
   every location holding a soul or the bean pack is covered by enough reachable call sites.
Prints problems and exits 1 if any."""
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GET_FILE, POUCH_FILE, HOOK = "Dm_SY_GetInEvent", "GetPouchContent", "Dm_SY_Get"
SCRUB_FILE, SCRUB_GRAPH, SHOP_FILE = "Enemy_Scrub_Business_Common", "Rando_HoldHandover", "SimpleShop"
if os.path.join(HERE, "tools") not in sys.path:  # romtools, for the default below
    sys.path.append(os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
TAG_NOTE = re.compile(r"^(.*): (.*) \(the heart's get scene gives it, tag (\d+)\)$")
# The lake pickups share the hook in parity/_songs_trade_lake.py, the letter on tag 0 and the arrow on tag 1. In
# the air or water they enter Dm_SY_Get at RandoST_LakeWP_<letter|arrow>, so we check both paths here. An audit
# that skips the hook in the site count and only visits its heart tags finds zero calls, even though both paths
# give the LH Underwater Item soul.
LAKE_NOTE = re.compile(r"^(LH Sun|LH Underwater Item): (.*) \(the pickup gives it once\)$")
LAKE_WP = {0: "RandoST_LakeWP_letter", 1: "RandoST_LakeWP_arrow"}
GIVE_FILES = (GET_FILE, POUCH_FILE)
OWN_ADD = "EventTriggerAddOwnToPouch"  # the pickup's own add (Dm_SY_Get Event35)


def _expected(item, plan, child_wallet):
    """The entry ('File:Entry') a call gives OoTR item `item` through, or None (not a call item)."""
    sys.path[:0] = [p for p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando"))
                    if p not in sys.path]
    from parity import _songs_trade_ops as ops
    import progressive
    souls = (plan.get("_extras_souls") or {}).get("gives") or {}
    if item in souls:
        return souls[item]["entry"]
    if item == "Magic Bean Pack":
        return f"{GET_FILE}:RandoST_BeanPack"
    if item in progressive.PROGRESSIVE:
        name = "Progressive Kokiri Wallet" if item == "Progressive Wallet" and child_wallet else item
        return f"{GET_FILE}:{ops.host_entry(name)}"
    return None


def verify(patch, plan, items, romfs=DEFAULT_ROMFS):
    """[problem, ...] (see the module docstring). items: {OoTR location: item} (the spoiler)."""
    sys.path[:0] = [p for p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando"))
                    if p not in sys.path]
    from romtools import Romfs, byml_load
    import progressive
    from . import _dungeons_routes as R
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    flows = R._Flows(fs, van)
    bad, n_checked = [], defaultdict(int)
    child_wallet = any("Progressive Kokiri Wallet" in str(s.get("call", "")) for s in plan.get("rewards", {}).values()
                       if isinstance(s, dict)) or any(e.get("add_graph") == "RandoST_ProgressiveKokiriWallet_Get"
                                                      for e in plan.get("events", []))
    catalog = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))}
    rows = byml_load(fs.read("RSDB/EventSetting.Product.111.rstbl.byml.zs"), allow_big=True)[0]
    rows = [r for r in (rows if isinstance(rows, list) else rows.get("Rows", [])) if isinstance(r, dict)]
    row_eps = defaultdict(set)
    for r in rows:
        m = re.search(r"/([^/]+)\.evfc$", str(r.get("FlowchartFileName", "")))
        if m and r.get("EntryPointName"):
            row_eps[m.group(1)].add(r["EntryPointName"])

    def fc_of(name, fcname=None):
        return next((fc for fc, _ in flows.get(name) if fc["name"] == (fcname or name)), None)

    def live(name, fcname=None):
        """(fc, steps reachable from its vanilla entry points and its scene IDs' entries)."""
        got = next(((fc, veps) for fc, veps in flows.get(name) if fc["name"] == (fcname or name)), None)
        if got is None:
            return None, set()
        fc, veps = got
        return fc, R._vanilla_reach(fc, set(veps) | row_eps.get(fc["name"], set()))

    called = set()  # every entry a checked give calls (5)

    def calls_in(fc, steps, want):
        return [i for i in steps if R._call(fc, fc["events"][i]) == want]

    def gives_anything(fc, steps):
        """A step among `steps` that gives: a call into the give files, or the pickup's own pouch add."""
        for i in steps:
            e = fc["events"][i]
            c = R._call(fc, e) or ""
            if c.split(":")[0] in GIVE_FILES:
                return e["name"]
            if e["type"] == "action" and e.get("action") == OWN_ADD:
                return e["name"]
        return None

    # ---- 1. core rewards replaced by a call
    for rid, spec in sorted(plan.get("rewards", {}).items()):
        if not isinstance(spec, dict) or not spec.get("call"):
            continue
        call = spec["call"]
        entry = call.split(":", 1)[1]
        if entry.startswith(("Rando_DI_", "Rando_IceTrap", "Rando_Trap_")):
            continue  # dungeon items (_dungeons_routes), traps (chests plugin)
        loc, _, item = str(spec.get("note", "")).partition(": ")
        want = _expected(items.get(loc), plan, child_wallet) if loc in items else None
        if want is not None and want != call and not (want.endswith("_Get") and call.endswith("_Get")
                                                      and items.get(loc) not in progressive.PROGRESSIVE):
            bad.append(f"{loc}: holds {items.get(loc)} (spoiler), but its reward {rid} calls {call}, not {want}")
        rws = [catalog[x] for x in ([rid] if rid in catalog else [k for k, v in catalog.items()
                                                                     if v.get("location") == rid])]
        for r in rws:
            if r.get("source") != "event":
                continue
            fname = os.path.basename(r["event_file"]).split(".")[0] if r.get("event_file") else None
            fc, steps = live(fname or r["flowchart"], r["flowchart"])
            if fc is None:
                bad.append(f"{loc} ({r['id']}): {r['flowchart']} unreadable")
                continue
            if not calls_in(fc, steps, call):
                bad.append(f"{loc} ({r['id']}): no step of {r['flowchart']} reachable from its entry points calls "
                           f"{call}")
            old = next((e["idx"] for e in fc["events"] if e["name"] == r["event"]), None)
            if old is not None and old in steps and r.get("call") not in progressive.DISPLAY_ROUTINES:
                bad.append(f"{loc} ({r['id']}): its vanilla give step {r['event']} is still reached")
        called.add(call)
        n_checked["reward"] += 1
    # ---- 2. scrub sales and the carpet salesman
    sfc, ssteps = live(SCRUB_FILE)
    markers = defaultdict(int)
    for op in plan.get("events", []):
        if op.get("file") != SCRUB_FILE:
            continue
        vals = [op.get("value")] if op.get("param") == "ActorName" else [
            (n.get("params_over") or n.get("params") or {}).get("ActorName") for n in (op.get("nodes") or {}).values()]
        for v in vals:
            if isinstance(v, str) and v.startswith(progressive.CALL_MARKERS) and not v.startswith(
                    progressive.DI_MARKER):
                markers[v] += 1
    for marker in sorted(markers):
        ok = False
        for i in R._entry_steps(sfc, SCRUB_GRAPH) if sfc else []:
            e = sfc["events"][i]
            if e["type"] == "switch" and R._params(e).get("Value") == marker:
                y = next((c["next"] for c in e.get("cases", []) if c["value"] == progressive.YES), None)
                if y is not None and calls_in(sfc, R._reachable(sfc, [y]), f"{GET_FILE}:{marker}"):
                    ok = True
        if not ok:
            bad.append(f"{SCRUB_FILE}:{SCRUB_GRAPH}: a scrub sells {marker}, but the intercept doesn't call it")
        if sfc is not None and not any(sfc["events"][i]["type"] in ("subflow", "subflow_switch")
                                       and R._params(sfc["events"][i]).get("ActorName") == marker for i in ssteps):
            bad.append(f"{SCRUB_FILE}: no reachable sale hands {marker} over")
        called.add(f"{GET_FILE}:{marker}")
        n_checked["scrub"] += markers[marker]
    shop = [op for op in plan.get("events", []) if op.get("file") == SHOP_FILE and op.get("add_graph")]
    for op in shop:
        for n in (op.get("nodes") or {}).values():
            c = str(n.get("call") or "")
            ep = c.split(":", 1)[-1]
            if c.startswith(f"{GET_FILE}:") and ep.startswith(progressive.CALL_MARKERS) and not ep.startswith(
                    progressive.DI_MARKER):
                fc = fc_of(SHOP_FILE)
                steps = R._entry_steps(fc, op["add_graph"]) if fc else []
                if not calls_in(fc, steps, c):
                    bad.append(f"{SHOP_FILE}:{op['add_graph']}: the carpet salesman's sale copy doesn't call {c}")
                called.add(c)
                n_checked["merchant"] += 1
    # ---- 3. the get-scene hook
    tags = []
    from parity import _songs_trade_lake as lake
    for line in plan.get("songs_trade_notes", []):
        m = TAG_NOTE.match(line)
        if m:
            for loc in m.group(1).split(", "):
                tags.append((loc, items.get(loc, m.group(2)), int(m.group(3))))
        m = LAKE_NOTE.match(line)
        if m:
            tags.append((m.group(1), items.get(m.group(1), m.group(2)), lake.TAG[m.group(1)]))
    hook = fc_of(HOOK)
    sw = next((e for e in (hook or {}).get("events", []) if e["name"] == "RandoST_LakePickups_tag"), None)
    for loc, item, tag in tags:
        nothing = item == "Nothing"
        want = None if nothing else _expected(item, plan, child_wallet)
        if want is None and not nothing:
            continue
        case = next((c["next"] for c in (sw or {}).get("cases", []) if c["value"] == tag), None)
        if case is None:
            bad.append(f"{loc}: the get scene has no branch for tag {tag} ({item})")
            continue
        steps = R._reachable(hook, [case])
        wp_entry = LAKE_WP.get(tag, f"RandoST_HeartWP_{tag}")
        wp = [i for i in R._entry_steps(hook, wp_entry)] if wp_entry in hook["entry_points"] else []
        if not wp:
            bad.append(f"{loc}: no Dm_SY_Get:{wp_entry} (its pickup in the air or water)")
        if nothing:
            got = gives_anything(hook, steps) or gives_anything(hook, wp)
            if got:
                bad.append(f"{loc}: OoTR's Nothing, but the get scene's tag {tag} branch gives something ({got})")
            n_checked["nothing"] += 1
            continue
        if item == "Ice Trap" or want is None:
            continue
        if item == "Magic Bean Pack":  # The hook handles both branches itself (_resident_give).
            # one bean from the get window and nine from the follow-up
            for where, st_ in (("standing", steps), ("in the air or water", wp)):
                one = any(R._call(hook, hook["events"][i]) == f"{POUCH_FILE}:GetPouchContentByActorName"
                          and R._params(hook["events"][i]).get("ActorName") == "Item_MagicBean" for i in st_)
                nine = any(R._params(hook["events"][i]).get("Actor") == "Item_MagicBean"
                           and R._params(hook["events"][i]).get("Num") == 9 for i in st_)
                if not (one and nine):
                    bad.append(f"{loc}: the get scene's tag {tag} branch ({where}) doesn't give the bean pack's "
                               f"10 beans")
            n_checked["hook"] += 1
            continue
        if not calls_in(hook, steps, want):
            bad.append(f"{loc}: the get scene's tag {tag} branch doesn't call {want} ({item})")
        called.add(want)
        souls = (plan.get("_extras_souls") or {}).get("gives") or {}
        if item in souls:  # in the air or water: a copy of the soul's give (its flag, or the key rows, and message)
            g = souls[item]
            marks = {f"{POUCH_FILE}:{g['message']}"} | ({g["flag"]} if g.get("flag") else set())
            if not any(R._call(hook, hook["events"][i]) in marks or R._params(hook["events"][i]).get("GameDataName")
                       in marks for i in wp):
                bad.append(f"{loc}: Dm_SY_Get:{wp_entry} (in the air or water) doesn't give {item}")
        elif item in progressive.PROGRESSIVE:
            name = "Progressive Kokiri Wallet" if item == "Progressive Wallet" and child_wallet else item
            pouch = f"{POUCH_FILE}:RandoST_Pouch_" + "".join(w for w in name.title().split() if w.isalnum())
            if not calls_in(hook, wp, pouch):
                bad.append(f"{loc}: Dm_SY_Get:{wp_entry} (in the air or water) doesn't call {pouch}")
            called.add(pouch)
        n_checked["hook"] += 1
    # ---- 4. the hideout jails and the Treasure Chest Game salesman
    for op in plan.get("events", []):
        g = str(op.get("add_graph", ""))
        if not g.startswith(("Rando_Hideout_", "Rando_TcgStart")):
            continue
        node = (op.get("nodes") or {}).get("give") or {}
        c = str(node.get("call") or "")
        ep = c.split(":", 1)[-1]
        if not c.startswith(f"{GET_FILE}:") or not ep.startswith(progressive.CALL_MARKERS) or ep.startswith(
                progressive.DI_MARKER):
            continue
        fc, steps = live(op["file"], op["flowchart"])
        if fc is None or not calls_in(fc, steps, c):
            bad.append(f"{op['file']}:{g}: its give step calling {c} isn't reached from the scene")
        called.add(c)
        n_checked["jail/salesman"] += 1
    # ---- 4b. any other plugin graph calling a tier entry, like the silver-rupee spots' give steps (held up, or in the
    # water the entry next to the get window). Each such call has to be reached from its scene, following calls across
    # files (the carpet salesman's sale step, in his own file, calls the SimpleShop copy that gives)
    xlive = {}

    def cross_live():
        """{flowchart: steps reached from any patched flowchart's vanilla or scene entry, following calls across
        files}."""
        if not xlive:
            import glob
            fcs = {}
            for p_ in glob.glob(os.path.join(patch, "Event", "EventFlow", "*.bfevfl.zs")):
                for fc, veps in flows.get(os.path.basename(p_).split(".")[0]):
                    fcs[fc["name"]] = (fc, set(veps) | row_eps.get(fc["name"], set()))
            xlive.update({n: set() for n in fcs})
            todo, done = [(n, ep) for n, (_, eps) in fcs.items() for ep in eps], set()
            while todo:
                n, ep = todo.pop()
                if (n, ep) in done or n not in fcs:
                    continue
                done.add((n, ep))
                fc = fcs[n][0]
                if ep not in fc["entry_points"]:
                    continue
                for i in R._reachable(fc, [fc["entry_points"][ep]["main"]]):
                    xlive[n].add(i)
                    e = fc["events"][i]
                    if e["type"] in ("subflow", "subflow_switch"):
                        todo.append((e.get("flowchart") or n, e["entry_point"]))
        return xlive

    for op in plan.get("events", []):
        g, f = str(op.get("add_graph", "")), op.get("file")
        if not g or f in (GET_FILE, POUCH_FILE, HOOK) or g.startswith(("Rando_Hideout_", "Rando_TcgStart")):
            continue
        tier_calls = {str(nd.get("call")) for nd in (op.get("nodes") or {}).values()
                      if re.match(rf"^({GET_FILE}:RandoST_.+_Get|{POUCH_FILE}:RandoST_Pouch_.+)$", str(nd.get("call")))}
        if not tier_calls:
            continue
        fc = fc_of(f, op["flowchart"])
        steps = cross_live().get(op["flowchart"], set())
        for c in sorted(tier_calls):
            if fc is None or not calls_in(fc, steps, c):
                bad.append(f"{f}:{g}: its give step calling {c} isn't reached from the scene")
            called.add(c)
            n_checked["other graphs"] += 1
    # ---- 5. the entries; every soul / bean pack location covered
    get_fc = fc_of(GET_FILE)
    pouch_fc = fc_of(POUCH_FILE)
    for c in sorted(called):
        f, ep = c.split(":", 1)
        fc = get_fc if f == GET_FILE else pouch_fc if f == POUCH_FILE else fc_of(f)
        if fc is None or ep not in fc["entry_points"]:
            bad.append(f"{c}: no such entry in the patch")
            continue
        m = re.fullmatch(r"RandoST_(?:Pouch_)?(.+?)(?:_Get)?", ep)
        names = {"".join(w for w in n.title().split() if w.isalnum()): n for n in progressive.PROGRESSIVE}
        if m and m.group(1) in names:  # a tier entry: it names every tier (or calls the tier's own give entry)
            steps = R._entry_steps(fc, ep)
            seen = set()
            for i in steps:
                e = fc["events"][i]
                seen |= {v for v in R._params(e).values() if isinstance(v, str)}
                seen.add(R._call(fc, e) or "")
            for t in progressive.PROGRESSIVE[names[m.group(1)]]["tiers"]:
                give = (progressive.GIVE.get(t) or {}).get("call")
                if t not in seen and give not in seen:
                    bad.append(f"{c}: its steps never name {t}")
    # souls and the bean pack: as many reachable call sites as locations (hook branches checked above)
    sites = defaultdict(int)
    import glob
    for p_ in glob.glob(os.path.join(patch, "Event", "EventFlow", "*.bfevfl.zs")):
        name = os.path.basename(p_).split(".")[0]
        for fc, veps in flows.get(name):
            for i in R._vanilla_reach(fc, set(veps) | row_eps.get(fc["name"], set())):
                c = R._call(fc, fc["events"][i])
                if c and fc["name"] != HOOK:
                    sites[c] += 1
    for c, k in markers.items():
        sites[f"{GET_FILE}:{c}"] += k  # (a scrub sale's marker: the intercept calls it)
    tagged = {loc for loc, _, _ in tags}
    need = defaultdict(list)
    for loc, item in items.items():
        want = _expected(item, plan, child_wallet)
        if want and item not in progressive.PROGRESSIVE and loc not in tagged:
            need[want].append(loc)
    for want, locs in sorted(need.items()):
        # a chest's item scene (dungeons.chest_call_item) calls the entry, its big-chest _Big variant, or for the bean
        # pack the chest entry Rando_DI_BeanPack (_dungeons_routes reads the chests)
        alias = [want, want + "_Big"] + ([f"{GET_FILE}:Rando_DI_BeanPack", f"{GET_FILE}:Rando_DI_BeanPack_Big"]
                                         if want == f"{GET_FILE}:RandoST_BeanPack" else [])
        have = sum(sites.get(a, 0) for a in alias)
        if have < len(locs):
            bad.append(f"{want}: {len(locs)} location(s) hold its item ({', '.join(sorted(locs))}), "
                       f"{have} reachable give step(s) call it")
        n_checked["covered"] += len(locs)
    # ---- 6. the Recovery Heart / Fairy Drop entries (dungeons.heal_graph). If one is called anywhere in the patch,
    # the entry has to exist, hold up the item's display (not the pickup, which can't be held up) and heal with the
    # game's cure for the item
    from parity import dungeons as dg
    for item, (entry, actor, display) in sorted(dg.HEAL.items()):
        want = f"{GET_FILE}:{entry}"
        n_sites = sum(k for c, k in sites.items() if c in (want, want + "_Big"))
        has = get_fc is not None and entry in get_fc["entry_points"]
        if not n_sites and not has:
            continue
        if not has:
            bad.append(f"{want}: called {n_sites} time(s), no such entry in the patch")
            continue
        steps = [get_fc["events"][i] for i in R._entry_steps(get_fc, entry)]
        cure = [e for e in steps if e["type"] == "action" and get_fc["actors"][e["actor"]]["actions"][e["action"]]
                == "EventTriggerRecoverByCureItem" and R._params(e).get("ActorName") == actor]
        shown = [e for e in steps if display in R._params(e).values()]
        if not cure or not shown:
            bad.append(f"{want}: {'no heal for ' + actor if not cure else ''}{' and ' if not cure and not shown else ''}"
                       f"{'no hold-up of ' + display if not shown else ''}")
        n_checked["heal entries"] += 1
    verify.counts = dict(n_checked)
    return bad


def main(argv):
    out_dir = argv[0]
    romfs = next((a for a in argv[1:] if not a.startswith("--") and argv[argv.index(a) - 1] != "--patch"),
                 DEFAULT_ROMFS)
    patch = argv[argv.index("--patch") + 1] if "--patch" in argv else os.path.join(out_dir, "patch")
    sys.path[:0] = [os.path.join(HERE, "tools", "rando"), os.path.join(HERE, "tools"),
                    os.path.join(HERE, "vendor", "ootr")]
    plan = json.load(open(os.path.join(out_dir, "plan.json"), encoding="utf-8"))
    sp = json.load(open(os.path.join(out_dir, "spoiler.json"), encoding="utf-8"))
    locs = sp.get("locations", sp)
    locs = locs.get("World 1", locs)
    items = {n: (v if isinstance(v, str) else v.get("item")) for n, v in locs.items()}
    from parity import _call_routes as me
    bad = me.verify(patch, plan, items, romfs)
    for b in bad:
        print(b)
    print(f"call routes: {getattr(me.verify, 'counts', {})} checked, {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
