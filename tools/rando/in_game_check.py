"""Read a built seed back and judge every drop-plugin spot by what the patch makes it give in-game.

usage: python tools/rando/in_game_check.py OUT_DIR [ROMFS]
  OUT_DIR holds plan.json, spoiler.json and (optional) patch/, tools/make_patch.py's output.

This doesn't rely on the generator's own judgment (parity/drops.py in_game, seed.json "vanilla_spots"). It reads
the patch plan's placement edits (Gyaml, Name, Dynamic.Drop__DropActor, Dynamic.Drop__DropTable) for every OoTR
location in data/rando/drop_map.json (with its stage-heart and key-spot variants) and reports:
  - spots whose in-game result is the vanilla one although the spoiler names another item (hidden vanilla)
  - spoiler items the plan doesn't give (OoTR's "Nothing" on an object the plan leaves as it is, an Ice Trap that
    is a stand-in pickup)
  - with the patch built, drops.verify_get_scene (every RandoGetScene name, the name chains, the disguise
    fallthrough) and, for remake_item_looks "item" (plan "_drops_looks"), drops.verify_looks (holders, display
    chains, hide step)
Scene gifts are judged apart. Those are drop_map "scene_gifts" (GC Pot Freestanding PoH, ZD Storms Grotto Blue
Rupee 1-6), given by a scene of their own (plan note "_notes_drops_scene_gifts"). The plan must name the
spoiler's item, hold the gift's scene steps and, for the grotto rupees, delete every rupee placement. With the
patch built that's drops.verify_scene_gifts.
With the patch built, every chest location's "opened" flag (the tracker's) is read back too. chest_flags.verify
checks the saved IsTreasureBoxOpen member, the chest type, no IsEnableRepeatOpen, the scene marking it opened,
and that tracker.json agrees.
Exit status 1 if anything is found.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
sys.path.insert(0, os.path.join(HERE, "tools"))
import drops as D  # noqa: E402  tools/rando/drops.py


def verify_rewards(patch, plan, romfs):
    """Reads back the plan's rewards written into level files (chests, freestanding pickups, scrubs..., the
    rewards.json "source" placement). Every placement holds its planned item (a progressive item's first tier, as
    make_patch's resolve_progressive writes it) and the reward's extra settings. Returns ([problem], number read
    back)."""
    from romtools import Romfs, byml_load
    cat = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))}
    prog = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]
    groups = {}
    for r in cat.values():
        groups.setdefault(r["location"], []).append(r["id"])
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    levels, bad, n = {}, [], 0
    renamed = {(op["file"], str(op["hash"])): str(op["set"]["Hash"]) for op in plan.get("placements", [])
               if "Hash" in op.get("set", {})}  # another plugin's own save flag for the placement (a new hash)

    def flat(d, pre=""):
        out = {}
        for k, v in (d or {}).items():
            out.update(flat(v, f"{pre}{k}.") if isinstance(v, dict) else {f"{pre}{k}": v})
        return out
    for rid, spec in sorted(plan.get("rewards", {}).items()):
        spec = {"item": spec} if isinstance(spec, str) else spec
        for member in ([rid] if rid in cat else groups.get(rid, [])):
            r = cat[member]
            if r["source"] != "placement":
                continue
            item = prog[spec["item"]]["tiers"][0] if spec["item"] in prog else spec["item"]
            want = {r["field"]: item}
            for k, v in (spec.get("extra") or {}).items():
                if v is not None and not (k == "GetEventName" and spec["item"] in prog):  # (its row: make_patch's)
                    want["Gyaml" if k == "Gyaml" else f"Dynamic.{k}"] = v
            for f in r["files"]:
                if f not in levels:
                    levels[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f))[0].get("Actors") or []}
                a = levels[f].get(renamed.get((f, str(r["hash"])), str(r["hash"])))
                if a is None:
                    bad.append(f"{member}: no placement {r['hash']} in {f}")
                    continue
                got = flat(a)
                n += 1
                for k, v in want.items():
                    if got.get(k) != v:
                        bad.append(f"{member} ({spec.get('note', '')}): {f} {k} = {got.get(k)!r}, planned {v!r}")
    return bad, n
import no_vanilla  # noqa: E402  tools/rando/no_vanilla.py (look: how an item's name compares)

TRAPS = ("Enemy_Keese_Ice", "Enemy_Keese_Fire", "Enemy_Keese")
HEARTS = {("actor", "Obj_Heart"), ("actor", "Obj_Heart_InWater")}


def variants(m):
    """name -> [drop-map entries]: the base entry and its setting-dependent variants (stage heart, key spot)."""
    out = {}
    for sec in ("drops", "new"):
        for n, e in m.get(sec, {}).items():
            out.setdefault(n, []).append(e)
            if "stage_get_scene" in e:
                out[n].append(dict(e, get_scene=e["stage_get_scene"],
                                   allowed_actors=e.get("stage_actors", e.get("allowed_actors", []))))
    for n, e in m.get("key_spots", {}).items():
        out.setdefault(n, []).append(e)
    return out


def _drop_result(p, o, tables):
    """What one dropper placement gives with plan edits `o` applied."""
    actor = o["Dynamic.Drop__DropActor"] if "Dynamic.Drop__DropActor" in o else p.get("drop")
    table = o["Dynamic.Drop__DropTable"] if "Dynamic.Drop__DropTable" in o else p.get("drop_table")
    t = tables.get(p["actor"], {})
    if actor:
        return ("actor", actor)
    if table == D.EMPTY_TABLE:
        return ("empty",)
    if p.get("category") == "gold_skulltula":
        return ("actor", "Obj_Token_Gold")
    fixed = t.get("named", {}).get(table) if table else t.get("default")
    return ("actor", fixed) if fixed else ("table", table or "default")


def _avoid_vanilla(out_dir):
    """The seed's remake_avoid_vanilla_spots (seed.json "vanilla_spots", else settings_used.json, else the default)."""
    try:
        return bool(json.load(open(os.path.join(out_dir, "seed.json"), encoding="utf-8"))["vanilla_spots"]["setting"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        s = json.load(open(os.path.join(out_dir, "settings_used.json"), encoding="utf-8"))["settings"]
        return bool(s.get(no_vanilla.SETTING, no_vanilla.DEFAULT))
    except (OSError, ValueError, KeyError, TypeError):
        return no_vanilla.DEFAULT


def main(out_dir, romfs=D.DEFAULT_ROMFS):
    m = D._map()
    plan = json.load(open(os.path.join(out_dir, "plan.json"), encoding="utf-8"))
    import free_flags  # the borrowed saved flags this seed's features held (plan "_flags_held"). The drops read-back
    free_flags.restore(plan)  # checks its flags against them, the fairies' are checked below
    sp = json.load(open(os.path.join(out_dir, "spoiler.json"), encoding="utf-8"))
    locs = sp.get("locations", sp)
    locs = locs.get("World 1", locs)
    item = {n: (v if isinstance(v, str) else v.get("item")) for n, v in locs.items()}
    ops = {}
    for p in plan.get("placements", []):
        if p.get("twin") is not None:
            continue  # A twin applies its edits to a copy with a new hash.
        o = ops.setdefault((p["file"], str(p["hash"])), {})
        o.update(p.get("set", {}))
        for k in p.get("remove", []):
            o[k] = None
    disguise = m.get("disguise") or {}
    tables = m.get("dropper_tables", {})
    scene_notes = {x.split(":")[0] for x in plan.get("_notes_drops_get_scene", [])}
    avoid = _avoid_vanilla(out_dir)  # hidden vanilla only counts with remake_avoid_vanilla_spots on
    problems, named = [], []
    got = []  # (location, item, named entry): drops.verify_heart_looks
    gifts = D.plan_scene_gifts(plan, m)
    for x in plan.get("_notes_drops_scene_gifts", []):
        n, _, rest = x.partition(": ")
        if item.get(n) != rest.rsplit(" (", 1)[0]:
            problems.append(f"{n}: the plan's scene gives {rest}, the spoiler says {item.get(n)}")
    problems += [f"{n}: {why}" for n, why in sorted(gifts.items()) if why]
    for n, es in sorted(variants(m).items()):
        if n not in item or n in gifts:
            continue
        it = item[n]

        def has_name(x):
            return "get_scene" in x and all(ops.get((p["file"], p["hash"]), {}).get("Name") == x["get_scene"]["name"]
                                            for p in x["placements"])
        e = next((x for x in es if has_name(x)), es[0])
        if not e.get("placements"):
            continue
        res, van = set(), set()
        for p in e["placements"]:
            o = ops.get((p["file"], p["hash"]), {})
            if e.get("kind") == "freestanding":
                van.add(("actor", p["actor"]))
                scene = has_name(e) and (n in scene_notes or n != disguise.get("spot"))
                res.add(("scene", o["Name"]) if scene else ("actor", o.get("Gyaml") or p["actor"]))
            else:
                van.add(_drop_result(p, {}, tables))
                res.add(_drop_result(p, o, tables))
        same = res == van or (res <= HEARTS and van <= HEARTS)
        if avoid and e.get("vanilla") and no_vanilla.look(it) != no_vanilla.look(e["vanilla"]) and same:
            problems.append(f"hidden vanilla: {n} holds {it} but gives {sorted(res)}, as in the vanilla game")
        if it == "Nothing" and e.get("kind") == "drop" and res == van:
            problems.append(f"{n}: Nothing, but the object keeps its own drop {sorted(van)} "
                            f"(remake_empty_object_contents 'vanilla')")
        if it == "Ice Trap" and not any(r[0] == "scene" or r[1] in (disguise.get("actor"),) + TRAPS for r in res):
            problems.append(f"{n}: Ice Trap, but the spot gives {sorted(res)} (a stand-in pickup)")
        if has_name(e):
            g = dict(e["get_scene"])
            if n == disguise.get("spot") and n not in scene_notes:
                g["value"] = D.GET_SCENE_VANILLA_ANSWER
            named.append(dict(e, get_scene=g))
            got.append((n, it, named[-1]))
    patch = os.path.join(out_dir, "patch")
    fall = {disguise["pack"]: disguise["tag"]} if plan.get("_notes_drops_disguise") and disguise else None
    drop_tags = sorted((plan.get("_drops_scene_drops") or {}).values())  # remake_drop_contents "all": any item
    checked = os.path.isdir(patch) and (named or fall or drop_tags)
    if checked:
        problems += [f"patch: {x}" for x in D.verify_get_scene(patch, named, romfs, fall, drop_tags)]
    if os.path.isdir(patch) and plan.get("_drops_lake_guard"):  # the lake hook answers for the lake's own spots only
        problems += [f"patch: {x}" for x in D.verify_lake_guard(patch, romfs)]
    if os.path.isdir(patch) and drop_tags:
        problems += [f"patch: {x}" for x in D.verify_scene_drops(
            patch, plan["_drops_scene_drops"], plan.get("_drops_looks_tags"), romfs,
            droppers=(plan.get("_checked_on_pickup") or {}).get("droppers"))]
    if os.path.isdir(patch) and plan.get("_drops_respawn"):  # the respawn model: bits, Presences, twins, save rows
        problems += [f"patch: {x}" for x in D.verify_respawn(patch, plan["_drops_respawn"], romfs,  # (enemy souls
                                                             (plan.get("_extras_souls") or {}).get("enemy_expressions"))]
        # objects a story flag's logic deletes come back while their item is there (drops.LOGIC_DELETE)
        problems += [f"patch: {x}" for x in D.verify_logic_delete(patch, plan, romfs)]
    lost_left = None
    if os.path.isdir(patch):  # Missed-item respawn: every shuffled object whose item was left behind comes back with it
        lost, lost_left = D.verify_no_lost_items(patch, plan, item, romfs, m)
        problems += [f"patch: {x}" for x in lost]
    if os.path.isdir(patch):  # OoTR gives a check's item once: no location's copies may each give it (drops COPIES)
        problems += [f"patch: {x}" for x in D.verify_one_give(patch, plan, item, romfs)]
    if os.path.isdir(patch) and plan.get("_drops_group_twins"):  # twins of reset-group pots refill with their room
        problems += [f"patch: {x}" for x in D.verify_group_twins(patch, plan["_drops_group_twins"], romfs)]
    cop = plan.get("_checked_on_pickup")
    if os.path.isdir(patch) and cop:  # objects saved when their item is taken (directly or through the get scene)
        problems += [f"patch: {x}" for x in D.verify_pickup_save(patch, cop["droppers"], cop["pickups"], romfs)]
    n_falls = None
    if os.path.isdir(patch):  # every pickup an object drops comes down to the ground (drops.verify_falls), so no
        bad_f, n_falls = D.verify_falls(patch, plan, romfs, m)  # tree's item hangs in its branches
        bad_r, n_res = D.verify_drop_resources(patch, plan, romfs)  # every drop is a resource of its dropper
        problems += [f"patch: resident: {x}" for x in bad_r]
        bad_v, n_resolve, _ = D.verify_drop_resolve(patch, plan, romfs)  # each spot drops its item, vanilla-shaped
        problems += [f"patch: resolve: {x}" for x in bad_v]  # drop resources, the pot tables included
        problems += [f"patch: falls: {x}" for x in bad_f]
    n_land = None
    if os.path.isdir(patch):  # every falling drop lands where Link can get it (tools/rando/landing_check.py, data/
        import landing_check  # rando/drop_landings.json), and the relocated ones are made there
        bad_l, n_land = landing_check.verify(plan)
        bad_a, n_at = D.verify_drop_at(patch, plan, romfs)
        problems += [f"patch: landing: {x}" for x in bad_l + bad_a]
    n_touch = None
    if os.path.isdir(patch):  # the carrier is taken by touch, and junk it brings skips the hold-up and the window
        bad_t, n_touch = D.verify_touch(patch, plan, item, romfs)  # (drops.verify_touch)
        problems += [f"patch: touch: {x}" for x in bad_t]
    n_ammo = None
    if os.path.isdir(patch):  # junk ammo at a checked drop spot drops as its own touch pickup, saved when taken
        bad_am, n_ammo = D.verify_ammo_touch(patch, plan, item, romfs, m)
        problems += [f"patch: ammo: {x}" for x in bad_am]
    n_fown = None
    if os.path.isdir(patch) and (plan.get("_drops_flag_spots") or plan.get("_drops_flagless_own")):
        # junk at a flagless spot (trees, bushes, respawning pots) drops as its own pickup, its bit recorded on take
        bad_fo, n_fown = D.verify_flagless_own(patch, plan, item, romfs, m, avoid=avoid)  # (flagless pickup support in drops.py)
        problems += [f"patch: flagless own: {x}" for x in bad_fo]
    if os.path.isdir(patch) and (plan.get("_drops_flag_spots") or drop_tags or plan.get("_drops_components")):
        problems += [f"patch: {x}" for x in D.verify_object_drops(  # the object shuffles' own edits
            patch, plan.get("_drops_scene_drops"), plan.get("_drops_flag_spots"),
            (plan.get("_checked_on_pickup") or {}).get("droppers"), romfs,
            components=plan.get("_drops_components") or [])]
    if os.path.isdir(patch) and plan.get("_extras_fish"):  # fishsanity (extras_npcs)
        from parity import extras_npcs
        problems += [f"patch: {x}" for x in extras_npcs.verify_fish(patch, plan["_extras_fish"], romfs)]
    held = {f: k for k, fl in (plan.get("_flags_held") or {}).items() for f in fl}  # no fairy flag another feature holds
    fa = plan.get("_fairies") or {}
    fa_flags = [x.get("flag") for s in ("stones", "notes", "beans") for x in (fa.get(s) or {}).values()]
    problems += [f"fairies: flag {f} is held by {held[f]}" for f in sorted(set(fa_flags + [fa.get("scratch"),
                                                                                      fa.get("bean_scratch")]) & set(held))]
    for name in sorted(set(plan.get("_verify_plugins") or [])):  # plugins that read their own edits back
        if os.path.isdir(patch):  # (SoH/3DR extras: parity/<name>.py verify(patch, plan, romfs) -> [problem])
            import importlib
            problems += [f"patch: {x}" for x in importlib.import_module(f"parity.{name}").verify(patch, plan, romfs)]
    trade_notes = None
    if os.path.isdir(patch) and plan.get("trade_slot") and "songs_trade" in (plan.get("_verify_plugins") or []):
        import importlib  # the trade button's read-back (tools/trade_slot.py), run by songs_trade.verify above
        trade_notes = getattr(importlib.import_module("parity.songs_trade").verify, "notes", None)
        for line in trade_notes or []:
            print(f"  trade button: {line}")
        for line in getattr(importlib.import_module("parity.songs_trade").verify, "mask_notes", None) or []:
            print(f"  mask button: {line}")  # the mask button's read-back (tools/mask_slot.py)
    if os.path.isdir(patch) and plan.get("_drops_no_hearts"):  # no_collectible_hearts: no drop gives a heart
        from parity import _drops_hearts
        problems += [f"patch: hearts: {x}" for x in _drops_hearts.verify(patch, plan["_drops_no_hearts"], romfs, plan)]
    n_no_pose = None
    if os.path.isdir(patch):  # no give of an ocarina reaches Link's hold-up, each opens its action guide (D1/D2)
        import no_pose_check  # tools/rando/no_pose_check.py
        bad_np, n_no_pose = no_pose_check.verify(patch, romfs)
        problems += [f"patch: no-pose: {x}" for x in bad_np]
    if os.path.isdir(patch):  # every model a patched ModelInfo or ActorInfo row names loads by name, and every model
        import model_check  # and texture file fits its size entry (tools/rando/model_check.py; test_guardroom3)
        problems += [f"patch: model: {x}" for x in model_check.verify(patch, romfs)[0]]
    if os.path.isdir(patch):  # no flow of ours reads a game-data value right after writing it: the read gets the old
        import write_read_check  # value (tools/rando/write_read_check.py; test_guardroom3's count text)
        problems += [f"patch: write-read: {x}" for x in write_read_check.verify(patch, romfs)[0]]
    if os.path.isdir(patch):  # every changed AI node has a shape the game's AI files use, and no blackboard write
        import ai_shape_check  # goes to an instance parameter, which crashes New Game (tools/rando/ai_shape_check.py)
        problems += [f"patch: ai shape: {x}" for x in ai_shape_check.verify(patch, romfs)[0]]
    if os.path.isdir(patch):  # the Deku Tree scrubs' scene never names a missing pickup or deletes a seed location
        from parity import _drops_scrubs
        problems += [f"patch: scrubs: {x}" for x in _drops_scrubs.verify(patch, plan.get("_drops_scrubs") or {},
                                                                          romfs, located=set(item))]
    if os.path.isdir(patch) and plan.get("_gaps"):  # closed OoTR gameplay settings (parity/_gaps_check.py)
        from parity import _gaps_check
        problems += [f"patch: {x}" for x in _gaps_check.verify(patch, plan["_gaps"], romfs)]
    fa = plan.get("_fairies")  # the fairy shuffles (parity/fairies.py): their flags, gives and grotto scene IDs
    if fa:
        import fairies as FA  # tools/rando/fairies.py
        mine = [x["flag"] for x in (fa.get("stones") or {}).values()] + ([fa["scratch"]] if fa.get("scratch") else [])
        mine += [x["flag"] for x in (fa.get("notes") or {}).values()] + [x["flag"] for x in (fa.get("beans") or {}).values()]
        mine += [fa["bean_scratch"]] if fa.get("bean_scratch") else []
        clash = sorted(set(mine) & set((plan.get("_drops_flag_spots") or {}).values()))
        if clash or len(mine) != len(set(mine)):
            problems.append(f"fairies: borrowed flags used twice ({clash or 'among the stones'})")
        if os.path.isdir(patch):
            problems += [f"patch: {x}" for x in FA.verify(patch, fa, romfs)]
    n_text = None
    if os.path.isdir(patch) and plan.get("text"):  # every text op (hints, the FOOL text, any plugin's), read back
        from parity import _hints_check
        n_text, bad_text, _, _ = _hints_check.check(romfs, patch, plan)
        problems += [f"patch: text: {x}" for x in bad_text]
        if any(op.get("file") == "EventFlowMsg/GossipStone.msbt" for op in plan["text"]) and \
                os.path.exists(os.path.join(out_dir, "spoiler.json")):
            sys.path.insert(0, os.path.join(HERE, "vendor", "ootr"))
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                import Hints  # noqa: F401  (OoTR prints notes on import)
            from parity import _hints_stones
            _hints_stones.install()
            problems += [f"patch: hints: {x}" for x in _hints_stones.verify(romfs, out_dir)[3]]
    n_rewards = None
    if os.path.isdir(patch) and plan.get("rewards"):
        bad_r, n_rewards = verify_rewards(patch, plan, romfs)
        problems += [f"patch: reward: {x}" for x in bad_r]
    n_chest_flags = None
    if os.path.isdir(patch):  # every chest location's saved "opened" flag, as the tracker reads it (chest_flags.py)
        import chest_flags  # tools/rando/chest_flags.py
        bad_cf, n_chest_flags = chest_flags.verify(patch, plan, out_dir, romfs)
        problems += [f"patch: chest flag: {x}" for x in bad_cf]
    n_look = None
    if os.path.isdir(patch) and any(str(op.get("note", "")).startswith("appearance:") or any(
            k.startswith("Dynamic.GameModelController_GeneralInstanceParam") for k in op.get("set", {}))
            for op in plan.get("placements", [])):  # the appearance plugin's chest types and colours
        from parity import _appearance_check
        bad_look, _, n_t, _, n_r, _ = _appearance_check.check(romfs, patch, plan)
        problems += [f"patch: appearance: {x}" for x in bad_look]
        n_look = n_t + n_r
    n_mark = None
    from parity import _marker
    if os.path.isdir(patch) and _marker.in_plan(plan):  # the unchecked marker and cues (parity/_marker.py)
        bad_m, n_mark = _marker.verify(patch, plan, romfs)
        problems += [f"patch: unchecked marker: {x}" for x in bad_m]
    if os.path.isdir(patch) and plan.get("_drops_looks_silver"):  # silver tokens show their item
        problems += [f"patch: silver look: {x}" for x in D.verify_silver_looks(patch, plan["_drops_looks_silver"],
                                                                                 romfs)]
        bad_si, n_si = D.verify_silver_items(plan, item)  # every silver spot holding an item shows it
        problems += [f"patch: silver look: {x}" for x in bad_si]
    if os.path.isdir(patch) and plan.get("_drops_looks_lake"):  # the lake pickups show their item
        problems += [f"patch: lake look: {x}" for x in D.verify_lake_looks(patch, plan["_drops_looks_lake"], romfs)]
    if os.path.isdir(patch) and plan.get("_drops_looks_types"):  # no container: the ammo turns into the Blue Rupee (Ammo-to-rupee conversion)
        problems += [f"patch: type look: {x}" for x in D.verify_type_looks(patch, plan["_drops_looks_types"], romfs)]
    looks = plan.get("_drops_looks") or {}  # remake_item_looks "item": what each get-scene spot shows
    names = {e["get_scene"]["name"] for e in named}
    problems += [f"{n}: shows {lk['shows']} but is no named get-scene spot of this plan"
                 for n, lk in sorted(looks.items()) if n not in names]
    if looks:  # a Piece of Heart (or a trap) on a get-scene carrier that isn't a heart piece shows one
        problems += [f"get-scene look: {x}" for x in D.verify_heart_looks(got, looks)[0]]
    silver_looks = (plan.get("_drops_looks_silver") or {}).get("looks") or {}
    if os.path.isdir(patch) and (looks or plan.get("_drops_looks_disguise") or plan.get("_drops_looks_tags")
                                 or plan.get("_drops_looks_lake") or silver_looks):  # (lake, silver looks too)
        problems += [f"patch: {x}" for x in D.verify_looks(patch, {**looks, **(plan.get("_drops_looks_lake") or {}),
                                                                   **silver_looks},
                                                                 romfs, plan.get("_drops_looks_disguise"),
                                                                 plan.get("_drops_looks_tags"),
                                                                 plan.get("_drops_looks_water"))]  # + sizes, glow
    if os.path.isdir(patch) and plan.get("_drops_ungrouped"):  # remake_reset_group_objects "one_time"
        problems += [f"patch: {x}" for x in D.verify_ungroup(patch, plan["_drops_ungrouped"], romfs)]
    if os.path.isdir(patch) and plan.get("_flags_minted"):  # once-flags past the borrowed pool: new saved Bools
        problems += [f"patch: {x}" for x in free_flags.verify_minted(patch, plan["_flags_minted"], romfs)]
    if os.path.isdir(patch):  # progressive starting items: every tier up to the count (world_settings.starting_adds)
        import world_settings
        problems += [f"patch: {x}" for x in world_settings.verify_starting(patch, out_dir, romfs)]
    n_calls = None
    if os.path.isdir(patch):  # items a give step hands over by calling an entry of their own (souls, the bean pack,
        from parity import _call_routes  # tier entries, OoTR's Nothing by the get scene)
        problems += [f"patch: calls: {x}" for x in _call_routes.verify(patch, plan, item, romfs)]
        n_calls = sum(getattr(_call_routes.verify, "counts", {}).values())
    n_traps = None
    if os.path.isdir(patch):  # every trap plays the kind the spoiler names (chests by their scene, the others by their
        from parity import _chests_traps  # recorded give step)
        bad_traps, n_traps = _chests_traps.verify(patch, plan, item, romfs)
        problems += [f"patch: traps: {x}" for x in bad_traps]
    n_sound = None
    if os.path.isdir(patch) and (plan.get("cosmetics") or {}).get("slink"):  # music graph and sound pools
        sys.path.insert(0, os.path.join(HERE, "tools", "rando", "parity"))
        import _cosmetics_apply
        bad_sound = _cosmetics_apply.verify(romfs, patch, plan)
        problems += [f"patch: {x}" for x in bad_sound]
        n_sound = len(plan["cosmetics"]["slink"])
    ok_gifts = sorted(n for n, why in gifts.items() if not why)
    if os.path.isdir(patch) and ok_gifts:
        problems += [f"patch: {x}" for x in D.verify_scene_gifts(patch, ok_gifts, romfs, m,
                                                                  nothing={n for n in ok_gifts if item.get(n) == "Nothing"})]
    for x in problems:
        print(x)
    print(f"{len(problems)} problems; {len(named)} named get-scene spots"
          + (" read back from the patch" if checked else " (no patch built)")
          + (f"; disguise fallthrough tag {disguise['tag']}" if fall else "")
          + (f"; {len(looks)} spots show their item" + (" (read back)" if os.path.isdir(patch) else "") if looks else "")
          + (f"; {len(gifts)} scene gifts" + (" read back from the patch" if os.path.isdir(patch) else "")
             if gifts else "")
          + (f"; {len(plan['_drops_flag_spots'])} flagless drops" + (" read back" if os.path.isdir(patch) else "")
             if plan.get("_drops_flag_spots") else "")
          + (f"; respawn model: {len(plan['_drops_respawn']['spots'])} spots, "
             f"{sum(1 for v in plan['_drops_respawn']['spots'].values() for p_ in v['placements'] if p_['twin'])} "
             f"vanilla twins" + (" read back" if os.path.isdir(patch) else "") if plan.get("_drops_respawn") else "")
          + (f"; no lost item read back" + (" (junk-only spots without the model: " + ", ".join(
              f"{n_} {a_}" for a_, n_ in sorted(lost_left.items())) + ")" if lost_left else "")
             if lost_left is not None else "")
          + (f"; fairies: {len((fa or {}).get('stones') or {})} stone, {len((fa or {}).get('colossus') or [])} oasis, "
             f"{sum(len(v) for v in ((fa or {}).get('grottos') or {}).values())} grotto, "
             + (f"{sum(len(v) for v in fa['rooms'].values())} fountain room, " if (fa or {}).get("rooms") else "")
             + f"{len((fa or {}).get('notes') or {})} note, "
             f"{sum(len(v['gives']) for v in ((fa or {}).get('beans') or {}).values())} bean"
             + (" read back" if os.path.isdir(patch) else "") if fa else "")
          + (f"; {n_rewards} placed rewards read back" if n_rewards is not None else "")
          + (f"; dropped pickups fall: {sum(n_falls.values())} objects, {len(n_falls)} pickup types read back"
             if n_falls else "")
          + (f"; drops resolved like the game: {n_resolve} spots read back" if n_falls is not None and n_resolve else "")
          + (f"; carrier taken by touch, {n_touch['quiet']} junk tags with no hold-up, {n_touch['held']} held up"
             if n_touch and n_touch.get("carrier") else "")
          + (f"; ammo as its own touch pickup at {n_ammo['own']} drop spots ({', '.join(n_ammo['types'])})"
             + (f", {n_ammo['flagless']} of them flagless" if n_ammo['flagless'] else "")
             if n_ammo and (n_ammo['own'] or n_ammo['flagless']) else "")
          + (f"; flagless own pickups at {n_fown['spots']} spots ({n_fown['placements']} objects) read back"
             if n_fown and n_fown['spots'] else "")
          + (f"; landings: " + ", ".join(f"{v} {c}" for v, c in sorted(n_land.items())) if n_land else "")
          + (f"; hold-ups read back ({n_no_pose.get('holds', 0)} of a named item, each with a working "
             f"Rotate_GetDemo, a model bind and a name the create keeps; {n_no_pose.get('gives', 0)} new ocarina gives "
             f"with the sync and guide, {n_no_pose.get('chests', 0)} ocarina chests; {n_no_pose.get('bound', 0)} new "
             f"steps on a bound actor; {n_no_pose.get('models', 0)} show models)"
             if n_no_pose else "")
          + (f"; trade button: " + ", ".join(n for n in trade_notes if n.startswith(("hooked", "no picker"))
                                              or "trades walked" in n) if trade_notes else "")
          + (f"; {n_chest_flags} chest flags read back" if n_chest_flags is not None else "")
          + (f"; {n_calls} gives by an entry of their own read back" if n_calls else "")
          + (f"; traps play their kind: " + ", ".join(f"{v} {k}" for k, v in sorted(n_traps.items())) + " read back"
             if n_traps else "")
          + (f"; {n_text} text messages read back" if n_text is not None else "")
          + (f"; {n_look} coloured or retyped placements read back" if n_look is not None else "")
          + (f"; {n_mark} unchecked-marker placements read back" if n_mark is not None else "")
          + (f"; {n_sound} sound-link edits read back (music graph, pools)" if n_sound is not None else "")
          + (f"; fishsanity ({sum(len(v) for v in plan['_extras_fish'].get('pond', {}).values())} pond list entries, "
             f"{len(plan['_extras_fish'].get('zd', []))} ZD fish)" + (" read back" if os.path.isdir(patch) else "")
             if plan.get("_extras_fish") else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
