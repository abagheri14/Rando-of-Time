"""Self-test the readers, writers and patcher against the game files. Run after any game or Longshot update.

usage: python tools/selftest.py ROMFS_DIR

1. every Banc placement file and RSDB table re-saves byte-for-byte, and every pack
   (actor packs and the other Pack/*.pack.zs) repacks byte-for-byte
2. every event flow reads completely and its pointers match its relocation table
3. a plan that sets every reward to its vanilla item writes no files
4. a plan that changes every reward builds, and reading the patched game back shows exactly
   the planned items, with every other actor field and event structure untouched
5. every text file (.msbt) of every language re-saves byte-for-byte, and with a label added it still
   finds every label through its hash table
6. the seed generator (OoT Randomizer's, vendor/ootr) makes a beatable seed, and every chest it fills maps to a
   remake actor the game has or to a progressive item. 6b: a seed with the minigame gap settings
   (STORY_HOOK_SETTINGS, no_epona_race...) generates with every story guard chained (a world_plan reroute of a
   step the story Plan hooks is refused)
7. the save-data list re-saves byte-for-byte, default edits change exactly the named flags, and the remake's
   story rules reach OoTR's logic
8. every AI graph (.ainb: AI/, Logic/, Sequence/ and inside every pack) re-saves byte-for-byte, and an "ainb"
   plan edit (nodes copied in, linked, a property set) reads back exactly, leaving every other node as it was
9. files inside packs: every path held by several packs has the same bytes in all of them (the rule make_patch
   enforces, tools/packpaths.py), and make_patch's check refuses a shared file edited in one pack only
10. a copied scene step (add_graph "copy") and its original keep their own values when a plan edits either one
   (make_patch unshare_copies), and an edit that would still reach two steps is refused (check_unshared)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from romtools import Romfs, byml_load, byml_dump, sarc_files, sarc_write  # noqa: E402
from evfl import Evfl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(HERE, "tools")
VANILLA = os.path.join(HERE, "original")


def run(*args):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"FAILED: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def main(romfs):
    fs = Romfs(romfs, VANILLA)
    ok = True

    # 1. Round-trip the BYML files and SARC packs.
    n = bad = 0
    for sub in ("Banc", "RSDB"):
        for dp, _, fns in os.walk(os.path.join(romfs, sub)):
            for fn in fns:
                if fn.endswith(".byml.zs"):
                    rel = os.path.relpath(os.path.join(dp, fn), romfs).replace("\\", "/")
                    data = fs.read(rel)
                    root, ver = byml_load(data)
                    n += 1
                    if byml_dump(root, ver) != data:
                        bad += 1
                        print("  not byte-identical:", rel)
    print(f"1. BYML round trip: {n - bad}/{n} files byte-identical")
    ok &= bad == 0
    n = bad = 0
    for sub in ("Pack/Actor", "Pack"):
        for fn in sorted(os.listdir(os.path.join(romfs, sub))):
            if fn.endswith(".pack.zs"):
                d = fs.read(f"{sub}/{fn}")
                n += 1
                if sarc_write(sarc_files(d)) != d:
                    bad += 1
                    print("  pack not byte-identical:", f"{sub}/{fn}")
    print(f"   Pack round trip: {n - bad}/{n} packs byte-identical")
    ok &= bad == 0

    # 2. Check event-flow pointers, dictionaries and relocation tables.
    import struct
    import evfl as evfl_mod
    from evfl_build import dic_tree, relt_bytes
    seen_dics = []
    orig_dict_at = evfl_mod.Evfl.dict_at

    def recording_dict_at(self, p):
        names = orig_dict_at(self, p)
        if p:
            seen_dics.append((p, names))
        return names

    evfl_mod.Evfl.dict_at = recording_dict_at
    n = bad = dics = dic_bad = relt_bad = rule_bad = 0
    edir = os.path.join(romfs, "Event", "EventFlow")
    for fn in sorted(os.listdir(edir)):
        if fn.endswith(".bfevfl.zs"):
            n += 1
            d = fs.read(f"Event/EventFlow/{fn}")
            seen_dics.clear()
            ev = Evfl(d)
            missing, unlisted = ev.check()
            if missing or unlisted:
                bad += 1
                print("  pointer mismatch:", fn)
            if ev.relt_rule_violations():  # Nintendo's rule for which pointers are listed (built files must follow it)
                rule_bad += 1
                print("  relocation rule broken:", fn)
            for p, names in seen_dics:  # the name-dictionary builder must reproduce every dictionary
                dics += 1
                want = [struct.unpack_from("<IHH", d, p + 8 + 16 * i) for i in range(len(names) + 1)]
                if want != [(b & 0xFFFFFFFF, lft, rgt) for b, lft, rgt in dic_tree(names)]:
                    dic_bad += 1
            r = ev.reloc_off  # and the relocation-table builder every table
            if relt_bytes(ev.relt_slots(), r, struct.unpack_from("<I", d, r + 0x1C)[0]) != d[r:]:
                relt_bad += 1
    evfl_mod.Evfl.dict_at = orig_dict_at
    print(f"2. Event flows: {n - bad}/{n} read completely, pointers match relocation tables")
    print(f"   Builders: {dics - dic_bad}/{dics} name dictionaries and {n - relt_bad}/{n} relocation tables rebuilt byte for byte")
    print(f"   Relocation rule (which pointers are listed): {n - rule_bad}/{n} files follow it")
    ok &= bad == 0 and dic_bad == 0 and relt_bad == 0 and rule_bad == 0

    # a scene graph (every progressive item's chest scene) built into the small-chest scene file must read
    # back whole, follow the rule, and leave every vanilla entry point's steps as they were
    import progressive
    from evfl_build import EvflBuilder
    d = fs.read("Event/EventFlow/Dm_SY_TreasureboxSmall.bfevfl.zs")
    b = EvflBuilder(d)
    fc = b.flowchart("Dm_SY_TreasureboxSmall")
    for name, info in progressive.PROGRESSIVE.items():
        nodes, start = progressive.chest_scene(info["tiers"])
        b.add_graph(fc, progressive.entry_name(name, "small"), nodes, start)
    built, orig = Evfl(b.build()), Evfl(d)

    def steps(ev, entry):
        f = ev.flowcharts[0]
        out, stack, seen = [], [f["entry_points"][entry]["main"]], set()
        while stack:
            i = stack.pop()
            if i in seen or i >= len(f["events"]):
                continue
            seen.add(i)
            e = f["events"][i]
            out.append((e["name"], e["type"], sorted(((e.get("params") or {}).get("items") or {}).keys())))
            stack += [e[k] for k in ("next", "join") if k in e] + [c["next"] for c in e.get("cases", [])] + e.get("forks", [])
        return sorted(out)
    kept = all(steps(orig, ep) == steps(built, ep) for ep in orig.flowcharts[0]["entry_points"])
    added = len(built.flowcharts[0]["entry_points"]) - len(orig.flowcharts[0]["entry_points"])
    scene_ok = not built.check()[1] and not built.relt_rule_violations() and kept and added == len(progressive.PROGRESSIVE)
    print(f"   Scene builder: {added} progressive chest scenes added; reads back whole, follows the rule, "
          f"vanilla entry points unchanged: {'yes' if scene_ok else 'NO'}")
    ok &= scene_ok

    tmp = tempfile.mkdtemp(prefix="rando-of-time-selftest-")
    try:
        cat_dir = os.path.join(tmp, "cat")
        run(os.path.join(TOOLS, "catalog.py"), romfs, cat_dir)
        rewards = json.load(open(os.path.join(cat_dir, "rewards.json"), encoding="utf-8"))

        # 3. A plan that matches vanilla should emit no patch files.
        noop = os.path.join(tmp, "noop.json")
        json.dump({"rewards": {r["id"]: r["item"] for r in rewards if r["item"]}}, open(noop, "w"))
        out = os.path.join(tmp, "noop_out")
        run(os.path.join(TOOLS, "make_patch.py"), romfs, out, noop)
        written = [f for _, _, fns in os.walk(out) for f in fns if f.endswith(".zs")]
        print(f"3. No-op plan over {len(rewards)} rewards: {len(written)} files written")
        ok &= not written

        # 4. Patch every reward and check that unrelated data survives.
        pools = {}
        for r in rewards:
            pools.setdefault("shop" if r["kind"] == "shop" else "freestanding" if r["kind"] == "freestanding"
                             else "event" if r["kind"] == "event" else "dynamic", set()).add(r["item"])
        # Items Link can't hold up as they are (config/hold_up.json show/window, the ocarinas) never get written into a
        # hold-up step as a plain value. make_patch gives them their own hold-up there (a new call, on purpose), so this
        # writer check leaves them out. tools/rando/no_pose_check.py reads those gives back on every build.
        held = set(progressive.HOLD_SHOW) | set(progressive.HOLD_WINDOW) | set(progressive.NO_POSE)
        pools = {k: sorted(v - {None} - held) for k, v in pools.items()}
        plan = {}
        for i, r in enumerate(rewards):
            if not r["item"]:
                continue
            pool = pools["shop" if r["kind"] == "shop" else "freestanding" if r["kind"] == "freestanding"
                         else "event" if r["kind"] == "event" else "dynamic"]
            new = pool[(pool.index(r["item"]) + 1) % len(pool)] if r["item"] in pool else pool[0]
            if r["kind"] == "event" and i % 7 == 0:
                new = f"Item_SelfTest_New_String_{i}"  # forces new strings into the pool
            if new != r["item"]:
                plan[r["id"]] = new
        full = os.path.join(tmp, "full.json")
        # The made-up names aren't real actors, so they need "force" to get past the name check.
        # Shop shelf and scrub keys are refused in real plans (they don't decide what's sold), but this checks the
        # writer.
        kinds = {r["id"]: r["kind"] for r in rewards}
        json.dump({"rewards": {rid: {"item": v, "force": True} if "SelfTest" in v or kinds[rid] in ("shop", "scrub") else v
                               for rid, v in plan.items()}}, open(full, "w"))
        out = os.path.join(tmp, "full_out")
        run(os.path.join(TOOLS, "make_patch.py"), romfs, out, full)
        after_dir = os.path.join(tmp, "after")
        run(os.path.join(TOOLS, "catalog.py"), romfs, after_dir, out)
        after = {r["id"]: r for r in json.load(open(os.path.join(after_dir, "rewards.json"), encoding="utf-8"))}
        before = {r["id"]: r for r in rewards}
        wrong = [rid for rid, want in plan.items() if after.get(rid, {}).get("item") != want]
        untouched_changed = [rid for rid in before if rid not in plan and after.get(rid, {}).get("item") != before[rid]["item"]]
        lost = set(before) - set(after)

        # structure check on every written file
        struct_bad = 0
        pfs = Romfs(romfs, VANILLA, [out])
        for dp, _, fns in os.walk(out):
            for fn in fns:
                if not fn.endswith(".zs") or "ResourceSizeTable" in fn:
                    continue
                rel = os.path.relpath(os.path.join(dp, fn), out).replace("\\", "/")
                if rel.startswith("Event/"):
                    a, b = Evfl(fs.read(rel)), Evfl(pfs.read(rel))
                    def shape(c):  # parameter layout with text values blanked (text edits are expected)
                        if c is None:
                            return None
                        if c["type"] == "container":
                            return {k: shape(v) for k, v in c["items"].items()}
                        return (c["type"], None if c["type"] in ("string", "argument") else c["value"])

                    def flow_shape(ev):
                        return [(fc["name"], [(x["name"], x["sub_name"], x["actions"], x["queries"]) for x in fc["actors"]],
                                 [(e["name"], e["type"], e.get("next"), [c["next"] for c in e.get("cases", [])],
                                   e.get("forks"), e.get("flowchart"), e.get("entry_point"), shape(e.get("params")))
                                  for e in fc["events"]],
                                 {k: (v["main"], v["sub_flow_events"]) for k, v in fc["entry_points"].items()})
                                for fc in ev.flowcharts]
                    if b.check()[1] or flow_shape(a) != flow_shape(b):
                        struct_bad += 1
                        print("  event structure changed:", rel)
                elif rel.startswith("Banc/"):  # (packs and RSDB tables: deliberate ops, e.g. hold-up animation)
                    va, _ = byml_load(fs.read(rel))
                    vb, _ = byml_load(pfs.read(rel))
                    strip = lambda act: {k: v for k, v in act.items() if k not in ("Gyaml", "Dynamic")}
                    dyn = lambda act: {k: v for k, v in (act.get("Dynamic") or {}).items()
                                       if not k.startswith(("Drop__", "ScrubBusiness_ShopItemActorName", "GetEventName"))}
                    if set(va) != set(vb) or len(va["Actors"]) != len(vb["Actors"]) or any(
                            strip(x) != strip(y) or dyn(x) != dyn(y) for x, y in zip(va["Actors"], vb["Actors"])) or \
                            any(va[k] != vb[k] for k in va if k != "Actors"):
                        struct_bad += 1
                        print("  placement structure changed:", rel)
        nfiles = sum(1 for _, _, fns in os.walk(out) for f in fns if f.endswith(".zs"))
        print(f"4. Full plan: {len(plan)} rewards changed across {nfiles} files; "
              f"read back wrong: {len(wrong)}, others changed: {len(untouched_changed)}, lost: {len(lost)}, "
              f"files with other changes: {struct_bad}")
        for rid in wrong[:10]:
            print("   wrong:", rid, "want", plan[rid], "got", after.get(rid, {}).get("item"))
        ok &= not (wrong or untouched_changed or lost or struct_bad)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 5. Round-trip the message tables and verify label lookup.
    import msbt
    n = bad = add_bad = 0
    langs = msbt.archives(romfs)
    for lang in langs:
        for name, d in msbt.read_archive(fs, lang).items():
            n += 1
            m = msbt.Msbt(d)
            if m.dump() != d:
                bad += 1
                print("  text not byte-identical:", lang, name)
            m.add("SelfTest_New_Label", "x")
            added = m.dump()
            back = msbt.Msbt(added)
            if msbt.misplaced_labels(added) or back.labels != m.labels or back.text("SelfTest_New_Label") != "x":
                add_bad += 1
                print("  label added but not found:", lang, name)
    print(f"5. Text round trip: {n - bad}/{n} .msbt files in {len(langs)} languages byte-identical; "
          f"with a label added, {n - add_bad}/{n} find every label")
    ok &= n > 0 and bad == 0 and add_bad == 0

    # 6. Generate a seed and check its placements against the remake.
    tmp6 = tempfile.mkdtemp(prefix="rando-of-time-seed-")
    try:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "rando", "generate.py"), tmp6, "--seed", "selftest"],
                           capture_output=True, text=True, env=dict(os.environ, PYTHONUTF8="1"))
        seed_ok = r.returncode == 0
        bad_items = []
        if seed_ok:
            plan = json.load(open(os.path.join(tmp6, "plan.json"), encoding="utf-8"))
            summary = json.load(open(os.path.join(tmp6, "seed.json"), encoding="utf-8"))
            actors = {f[:-len(".pack.zs")] for f in os.listdir(os.path.join(romfs, "Pack", "Actor"))}
            prog = json.load(open(os.path.join(os.path.dirname(TOOLS), "config", "progressive.json"), encoding="utf-8"))["items"]
            # A chest's carrier can be one of ours, either a type the plan makes ("new_files") or a display
            # make_patch builds when it's named (config/hold_up.json "displays"). See parity/dungeons.py CARRIER.
            made = {op["to"][len("Pack/Actor/"):-len(".pack.zs")] for op in plan.get("new_files", [])
                    if op["to"].startswith("Pack/Actor/") and op["to"].endswith(".pack.zs")}
            made |= set(json.load(open(os.path.join(os.path.dirname(TOOLS), "config", "hold_up.json"),
                                       encoding="utf-8")).get("displays") or {})
            bad_items = sorted({v["item"] for v in plan["rewards"].values() if v["item"] not in actors
                                and v["item"] not in prog and not (v.get("force") and v["item"] in made)})
            seed_ok = not bad_items and summary["playthrough_spheres"] > 0
            print(f"6. Seed generator: beatable seed in {summary['attempts']} attempt(s), {summary['chests_in_play']} chests "
                  f"in play, {summary['playthrough_spheres']} playthrough spheres; items the game lacks: {bad_items or 'none'}")
        else:
            print("6. Seed generator FAILED:", (r.stderr or r.stdout).strip().splitlines()[-1:])
        ok &= seed_ok
    finally:
        shutil.rmtree(tmp6, ignore_errors=True)
    ok &= story_hooks()

    # 7. Check GameData layout, flag defaults and story logic.
    import make_patch
    from romtools import byml_load as _load, byml_dump as _dump, murmur3_32
    gd = fs.read(make_patch.GAMEDATA)
    root, ver = _load(gd, allow_big=True)
    gd_same = _dump(root, ver, big=True) == gd
    want = {"KokiriForest_Npc_Kokiri_Mido_Child_Blocker": False, "PlayerStatus.CurrentRupee": 99,
            "Step_Meet_DekuTree": "Step03"}
    new = make_patch.patch_gamedata(gd, [{"defaults": want}], make_patch.GAMEDATA)
    a, _ = _load(gd, allow_big=True)
    b, _ = _load(new, allow_big=True)
    changed = {x["Hash"]: y["DefaultValue"] for t in a["Data"] for x, y in zip(a["Data"][t], b["Data"][t]) if x != y}
    expect = {murmur3_32(k): (murmur3_32(v) if isinstance(v, str) else v) for k, v in want.items()}
    gd_edit = len(new) == len(gd) and changed == expect
    print(f"7. Save-data list: {len(gd)} bytes re-saved byte-identical: {'yes' if gd_same else 'NO'}; "
          f"new-file default edits change exactly the named flags: {'yes' if gd_edit else 'NO'}")
    ok &= gd_same and gd_edit
    code = ("import sys, json; sys.path.insert(0, %r); import generate as g, world_settings as w, RuleParser; "
            "s, sp, world, *_ = g.generate('selftest', %r); "
            "print(json.dumps([RuleParser.rule_aliases['has_all_stones'][1], "
            "any(l.name.startswith(w.LACS_EVENT) for l in world.get_region('Temple of Time').locations), "
            "w.LACS_EVENT in RuleParser.rule_aliases['can_build_rainbow_bridge'][1], "
            "world.get_location('Sheik at Temple').rule_string]))") % (
        os.path.join(TOOLS, "rando"), os.path.join(os.path.dirname(TOOLS), "config", "rando_settings.json"))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ, PYTHONUTF8="1"))
    try:
        stones, lacs_event, bridge, sheik = json.loads(r.stdout.strip().splitlines()[-1])
        logic_ok = ("Defeat King Dodongo" in stones and "Goron_Ruby" not in stones and lacs_event and bridge
                    and "Defeat Phantom Ganon" in sheik)
    except (ValueError, IndexError):
        logic_ok, stones = False, (r.stderr or r.stdout).strip().splitlines()[-1:]
    print(f"   Remake story rules in OoTR's logic (stones/medallions -> boss defeats, bridge after the Light Arrow "
          f"cutscene): {'yes' if logic_ok else 'NO ' + str(stones)}")
    ok &= logic_ok
    sys.path.insert(0, os.path.join(TOOLS, "rando"))
    import world_settings
    clashes = world_settings.override_clashes()
    print(f"   Logic files setting the same rule key: {'none' if not clashes else len(clashes)}")
    for sec, reg, k, files in clashes:
        print(f"   clash: {sec} {reg or '(helper)'} {k}: {', '.join(files)}")
    ok &= not clashes

    # 8. Round-trip AINB graphs and check node edits.
    import ainb
    n = bad = 0
    for sub in ("AI", "Logic", "Sequence"):
        for fn in sorted(os.listdir(os.path.join(romfs, sub))):
            if fn.endswith(".ainb"):
                d = fs.raw(f"{sub}/{fn}")
                n += 1
                try:
                    same = ainb.Ainb(d).dump() == d
                except ainb.AinbError as ex:
                    same = False
                    print("  AI file unreadable:", f"{sub}/{fn}", ex)
                if not same:
                    bad += 1
                    print("  AI file not byte-identical:", f"{sub}/{fn}")
    for sub in ("Pack", "Pack/Actor"):
        for fn in sorted(os.listdir(os.path.join(romfs, sub))):
            if not fn.endswith(".pack.zs"):
                continue
            for inner, d in sarc_files(fs.read(f"{sub}/{fn}")).items():
                if inner.endswith(".ainb"):
                    n += 1
                    try:
                        same = ainb.Ainb(d).dump() == d
                    except ainb.AinbError as ex:
                        same = False
                        print("  AI file unreadable:", f"{sub}/{fn}:{inner}", ex)
                    if not same:
                        bad += 1
                        print("  AI file not byte-identical:", f"{sub}/{fn}:{inner}")
    print(f"8. AI graph round trip: {n - bad}/{n} .ainb files byte-identical")
    ok &= n > 0 and bad == 0
    make_patch.AINB_FS = fs
    pot_pack = sarc_files(fs.read("Pack/Actor/Obj_Pot_A_01.pack.zs"))
    vanilla = pot_pack["AI/Obj_Pot.root.ainb"]
    op = {"pack": "Pack/Actor/Obj_Pot_A_01.pack.zs", "file": "AI/Obj_Pot.root.ainb", "edits": [
        {"copy": {"from": {"pack": "Pack/Actor/Enemy_Skulltula_Gold.pack.zs",
                           "file": "AI/Enemy_Skulltula_Gold.utility.root.ainb"},
                  "nodes": ["OneShotDropSetOverWriteParam"], "label": "d"}},
        {"set_property": {"node": "d:1", "name": "Key", "value": "RespawnGmdHash"}},
        {"add_child": {"parent": "@Root", "child": "d:2"}}]}
    try:
        built = make_patch.patch_ainb_one(vanilla, op, "selftest")
        a, b = ainb.Ainb(vanilla), ainb.Ainb(built)
        added = b.nodes[len(a.nodes):]
        root = b.nodes[b.commands[0]["main"]]
        edit_ok = ([x["name"] for x in added] == ["OneShotDropSetOverWriteParam",
                                                   "QueryBlackboardOverwriteParamAddNoRespawnGmdHash",
                                                   "QueryGenericMakeOverwriteParam"]
                   and b._param(len(a.nodes) + 1, "properties", "Key")[1]["value"] == "RespawnGmdHash"
                   and root["plugs"][ainb.PLUG_CHILD][-1]["node"] == len(a.nodes)
                   and b._input(len(a.nodes), "OverwriteParam")[1]["node"] == len(a.nodes) + 1
                   and b.nquery == a.nquery + 2
                   and all(ainb.describe_node(a, i) == ainb.describe_node(b, i) for i in range(len(a.nodes))
                           if i != b.commands[0]["main"]))
    except make_patch.PlanError as ex:
        edit_ok = False
        print("  ainb edit failed:", ex)
    print(f"   AI graph edit (Skulltula drop-hash nodes copied into the pot's AI): reads back exactly, other nodes "
          f"unchanged: {'yes' if edit_ok else 'NO'}")
    ok &= edit_ok

    # 9. Any file shared by several packs must have matching bytes.
    import hashlib
    import packpaths
    import make_patch
    idx = packpaths.index(romfs)
    shared = {k: v for k, v in idx.items() if len(v) > 1}
    files_of = {}
    differ = 0
    for inner, packs in shared.items():
        digests = set()
        for pk in packs:
            if pk not in files_of:
                files_of[pk] = sarc_files(fs.read(pk))
            digests.add(hashlib.sha1(files_of[pk][inner]).hexdigest())
        differ += len(digests) > 1
    print(f"9. Pack paths: {len(idx)} paths, {len(shared)} held by several packs, {differ} with different bytes")
    one = "Pack/Actor/Obj_Heart_Piece.pack.zs"
    hp = dict(sarc_files(fs.read(one)))
    ai = "AI/PouchContentUtuwa.event.root.ainb"
    hp[ai] = hp[ai] + b"\0" * 16  # a different copy in one of its five packs

    def load(rel):
        return fs.read(rel), None
    refused = bool(make_patch.check_shared_paths({one: hp}, load, romfs))
    print(f"   A shared file edited in one pack only is refused: {'yes' if refused else 'NO'}")
    ok &= differ == 0 and refused
    # A new pack (a copy of a game pack, like shelf types, carrier copies and displays) gets the plan's edits to the
    # files it shares with the game's packs (make_patch.sync_new_packs).
    src = "Pack/Actor/Shop_DekuStick.pack.zs"
    inner = "Component/PouchContentParam/Obj_DekuStick.game__component__PouchContentParam.bgyml"
    new_rel = "Pack/Actor/Rando_SelftestCopy.pack.zs"
    edited_files = dict(sarc_files(fs.read(src)))
    edited_files[inner] = edited_files[inner] + b"\0" * 16
    built_ = {src: make_patch.sarc_write(edited_files)}

    def load_(rel):
        return fs.read(src if rel == new_rel else rel), None
    synced = make_patch.sync_new_packs(built_, [new_rel], load_)
    others = {k: v for k, v in sarc_files(built_.get(new_rel, b"")).items() if k != inner} if synced else {}
    copy_ok = (synced == [new_rel] and sarc_files(built_[new_rel])[inner] == edited_files[inner]
               and others == {k: v for k, v in sarc_files(fs.read(src)).items() if k != inner})
    print(f"   A new pack copying a game pack gets the plan's edits to its shared files: {'yes' if copy_ok else 'NO'}")
    ok &= copy_ok

    ok &= copied_steps(romfs)
    print("ALL PASSED" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


# Settings whose gaps modules hook story steps that the story traps guard too. story.Plan chains them, and doing the
# reroute in world_plan instead leaves the order guards orphaned. These are the minigame gap settings (no_epona_race,
# skip_some_minigame_phases, ruto_already_f1_jabu) on top of most of the object shuffles and story settings.
STORY_HOOK_SETTINGS = "plans/story_hooks_settings.json"
EPONA_GUARDS = {("Dm_MelodyGet_Epona", "Event82"): ("Get_Epona_IsCompleted_Exp", "Get_Epona_IsAfter_AfterGetEponaSong_Exp"),
                ("Npc_Hylia_Malon_Adult", "Event86"): ("Get_Epona_IsCompleted_Exp", "Get_Epona_IsAfter_AfterTalkMalon_Exp")}


def story_hooks():
    """6b: a seed with STORY_HOOK_SETTINGS generates, each Epona step's one hook graph holds both guards (keep-complete
    and the order guard), and no plan edge gets routed twice.
    story.world_plan refuses a gaps module's reroute of an edge its Plan hooks, and also a new step of the module's
    own that goes straight to a hooked step."""
    root = os.path.dirname(TOOLS)
    tmp = tempfile.mkdtemp(prefix="rando-of-time-hooks-")
    try:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "rando", "generate.py"), tmp, "--seed", "selftest",
                            "--settings", os.path.join(root, STORY_HOOK_SETTINGS)],
                           capture_output=True, text=True, env=dict(os.environ, PYTHONUTF8="1"), cwd=root)
        if r.returncode:
            print("6b. Story hooks: the seed FAILED:", (r.stderr or r.stdout).strip().splitlines()[-1:])
            return False
        events = json.load(open(os.path.join(tmp, "plan.json"), encoding="utf-8")).get("events", [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = []
    for (file, step), exps in EPONA_GUARDS.items():
        graphs = [op for op in events if op.get("file") == file and op.get("add_graph") == f"Rando_Story_{step}"]
        got = {n.get("params", {}).get("GameDataName") for g in graphs for n in g["nodes"].values()}
        if len(graphs) != 1 or not set(exps) <= got:
            bad.append(f"{file} {step}: {len(graphs)} hook graphs, guards on {sorted(x for x in got if x)}")
    edges = {}
    for op in events:
        if "next" in op and "event" in op and not ({"add_graph", "add_entry", "param"} & set(op)):
            k = (op["file"], op.get("flowchart"), op["event"], op.get("case"), op.get("fork"))
            if edges.setdefault(k, op["next"]) != op["next"]:
                bad.append(f"{k} routed to both {edges[k]} and {op['next']}")
    print(f"6b. Story hooks ({STORY_HOOK_SETTINGS}): the seed generates, both Epona steps chain their keep-complete "
          f"and order guards, no edge routed twice: {'yes' if not bad else 'NO ' + '; '.join(bad[:3])}")
    return not bad


def copied_steps(romfs):
    """10. Copy-on-write for copied scene steps. A number edit on a copy or on its original only changes that step, and
    make_patch refuses an edit that would still reach two steps."""
    import make_patch
    from evfl import Evfl
    print("10. copied scene steps keep their own values")
    fs = Romfs(romfs, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "original"))
    name = "Npc_Hylia_053_Adult"  # Event179: GameDataActor.EventTriggerSetGameDataInt SimpleShop_Price = 100
    data = fs.read(f"Event/EventFlow/{name}.bfevfl.zs")
    f = {"file": name, "flowchart": name}
    graph = dict(f, add_graph="SelfTestCopy", start="a", nodes={"a": {"copy": "Event179", "next": None}})

    def values(ops):
        fc = next(x for x in Evfl(make_patch.patch_event(data, ops, "selftest")).flowcharts if x["name"] == name)
        by = {e["name"]: e for e in fc["events"]}
        return [by[e]["params"]["items"]["Value"]["value"] for e in ("Event179", "SelfTestCopy_a")]
    cases = [([dict(f, event="Event179", param="Value", value=7)], [7, 100]),
             ([dict(f, event="SelfTestCopy_a", param="Value", value=9)], [100, 9]),
             ([dict(f, event="Event179", param="Value", value=7), dict(f, event="SelfTestCopy_a", param="Value",
                                                                       value=9)], [7, 9])]
    good = all(values([dict(graph)] + edits) == want for edits, want in cases)
    print(f"   An edit changes only the step it names (original, copy, both): {'yes' if good else 'NO'}")
    keep = make_patch.unshare_copies
    make_patch.unshare_copies = lambda ops, probe, rel: ops  # without the fix the copy shares the original's block
    try:
        make_patch.patch_event(data, [dict(graph), dict(f, event="Event179", param="Value", value=7)], "selftest")
        refused = False
    except make_patch.PlanError:
        refused = True
    finally:
        make_patch.unshare_copies = keep
    print(f"   An edit that would reach two steps is refused: {'yes' if refused else 'NO'}")
    return good and refused


if __name__ == "__main__":
    main(sys.argv[1])
