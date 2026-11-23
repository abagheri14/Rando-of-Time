"""Read-back check that every trap plays the kind the spoiler names (run by tools/rando/in_game_check.py).

What it reads, from the built patch over the game's files (and not from the plan, where it can):
1. Chests. For every chest location where the spoiler has a trap (Ice, Shock, Fire or Rupee Trap), it takes each
   of its chests as the patched level places it (type, Drop__DropActor and GetEventName) and walks the scene that
   opening runs, from the scene ID's EventSetting row on, the way the game would for that content. A content compare
   (GameDataActor.EventQueryIsGameDataString64 on the scratch string after the ContentName copy) follows the branch
   the chest's content takes, a story step naming a scene ID (EventTransition's EventName) goes on into that row's
   scene, and calls into the chest scene files are followed. The chest has to reach exactly the effect of its kind
   (Rando_IceTrap_Freeze, Rando_Trap_<Kind>) and never the plain opening that hands the content over (Success_ /
   Open). That plain opening is what a placed Ice Trap in Mido's chests, the Treasure Chest Game's rooms and the
   other story chests used to do (a blue rupee), and what a kind out of scene IDs did (the ice trap under another
   name).
2. The effects. Each effect entry reached creates its kind's attacker (ice: ConditionSensorActor, shock and fire:
   _chests_scenes.SENSORS) or takes rupees (rupee). Each kind's attacker is in the patch with its rows and an
   AttackParam of its element (_chests_scenes.ELEMENTS).
3. Other locations. remake_trap_weights without ice draws no Ice Trap, so an Ice Trap in the spoiler is one a path
   gave no kind. Only the disguised drop spots, which can't hand a kind on, keep the ice trap, and the spoiler names
   them that way. Where the plan records a location's give step (scene and NPC rewards' calls, the get scene's tags
   in Dm_SY_Get as patched, silver-rupee spots), that step has to call its kind's effect.
"""
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TRAPS = {"Ice Trap": "ice", "Shock Trap": "shock", "Fire Trap": "fire", "Rupee Trap": "rupee"}
EFFECTS = {"Rando_IceTrap_Freeze": "ice", "Rando_IceTrap": "ice", "Rando_Trap_Shock": "shock", "Rando_Trap_Fire": "fire",
           "Rando_Trap_Rupee": "rupee"}
CHEST_FILES = ("Dm_SY_TreasureboxSmall", "Dm_SY_Treasurebox")
# The chest's plain opening, the one that wakes and hands over its content. A small chest's Open does that. A big
# chest's Open is only the lid, which its trap scene plays too, and Success_AddContent is what hands it over.
PLAIN = {"Dm_SY_TreasureboxSmall": ("Success_", "Open"), "Dm_SY_Treasurebox": ("Success_", "Success_AddContent")}
SCENE_TABLE = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
DEFAULT_SCENE = {"small": ("Dm_SY_TreasureboxSmall", "Success"), "big": ("Dm_SY_Treasurebox", "Success")}


def _p(e):
    return {k: v.get("value") for k, v in (((e.get("params") or {}).get("items")) or {}).items()}


class _Walk:
    """Follows a chest's scene for one content (see the module docstring)."""

    def __init__(self, flows, rows, scratch):
        self.flows, self.rows, self.scratch = flows, rows, scratch

    def fc(self, file):
        return next((fc for fc, _ in self.flows.get(file) if fc["name"] == file), None)

    def run(self, file, entry, content, at=None):
        """Outcomes of the scene `file`:`entry` (or from step index `at` of `file`) for chest content `content`, as
        ("effect" | "plain" | "missing", file, entry)."""
        out, seen, todo = set(), set(), []
        if at is None:
            self._enter(file, entry, todo, out)
        else:
            todo.append((file, at))
        while todo:
            file, i = todo.pop()
            if (file, i) in seen:
                continue
            seen.add((file, i))
            fc = self.fc(file)
            e = fc["events"][i]
            t = e["type"]
            nxt = []
            if t in ("subflow", "subflow_switch"):
                f2, ep = e.get("flowchart") or file, e.get("entry_point")
                if ep in EFFECTS:
                    out.add(("effect", f2, ep))
                elif f2 in CHEST_FILES and ep in PLAIN[f2]:
                    out.add(("plain", f2, ep))
                elif f2 == file or f2 in CHEST_FILES:
                    self._enter(f2, ep, todo, out)
                nxt = [e.get("next")] + [c["next"] for c in e.get("cases", [])]
            elif t == "switch" and e.get("query_name", self._query(fc, e)) == "EventQueryIsGameDataString64" \
                    and _p(e).get("GameDataName") == self.scratch and isinstance(_p(e).get("Value"), str):
                case = 0 if _p(e)["Value"] == content else 1
                nxt = [c["next"] for c in e.get("cases", []) if c["value"] == case]
            else:
                if t == "action":
                    row = _p(e).get("EventName")
                    if isinstance(row, str) and row in self.rows:
                        self._enter(*self.rows[row], todo, out)
                nxt = [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])] + list(e.get("forks", []))
            for x in nxt:
                if x is not None and x != 0xFFFF:
                    todo.append((file, x))
        return out

    @staticmethod
    def _query(fc, e):
        try:
            return fc["actors"][e["actor"]]["queries"][e["query"]]
        except (KeyError, IndexError, TypeError):
            return None

    def _enter(self, file, entry, todo, out):
        fc = self.fc(file)
        ep = (fc or {}).get("entry_points", {}).get(entry)
        if ep is None:
            out.add(("missing", file, entry))
        elif ep["main"] != 0xFFFF:
            todo.append((file, ep["main"]))


def _effect_ok(walk, file, entry, kind):
    """Problem text, or None if entry `entry` of `file` makes kind `kind`'s effect."""
    import parity._chests_scenes as scenes
    fc = walk.fc(file)
    ep = (fc or {}).get("entry_points", {}).get(entry)
    if ep is None:
        return f"{file}:{entry} is missing"
    seen, todo, found = set(), [ep["main"]], []
    while todo:
        i = todo.pop()
        if i in seen or i == 0xFFFF:
            continue
        seen.add(i)
        e = fc["events"][i]
        found.append((e.get("action_name") or _action(fc, e), _p(e)))
        todo += [x for x in [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])]
                 + list(e.get("forks", [])) if x is not None]
    if kind == "rupee":
        ok = any(a == "EventTriggerIncreaseRupee" and p.get("Value") == -scenes.RUPEE_LOSS for a, p in found)
        return None if ok else f"{file}:{entry} takes no {scenes.RUPEE_LOSS} rupees"
    want = "ConditionSensorActor" if kind == "ice" else scenes.SENSORS[kind]
    ok = any(a == "EventTriggerRequestCreateConditionSensor" and p.get("ActorName") == want for a, p in found)
    return None if ok else f"{file}:{entry} doesn't create {want}"


def _action(fc, e):
    try:
        return fc["actors"][e["actor"]]["actions"][e["action"]]
    except (KeyError, IndexError, TypeError):
        return None


def _sensor_ok(fs, kind):
    """Problems with kind `kind`'s attacker in the patch (_chests_scenes.kind_sensor_ops)."""
    import parity._chests_scenes as scenes
    from romtools import byml_load, sarc_files
    name = scenes.SENSORS[kind]
    try:
        files = sarc_files(fs.read(f"Pack/Actor/{name}.pack.zs"))
    except (FileNotFoundError, OSError, KeyError):
        return [f"no Pack/Actor/{name}.pack.zs (the {kind} trap's attacker)"]
    bad = []
    ap = byml_load(files[f"Actor/{name}.engine__actor__ActorParam.bgyml"])[0]["Components"]
    gpt = ap.get("GameParameterTableRef", "").lstrip("?")
    atk = byml_load(files[gpt])[0]["Components"].get("gamebalance_AttackParam", "").lstrip("?") if gpt in files else ""
    if atk not in files:
        bad.append(f"{name}: its parameter table names no AttackParam in its pack ({gpt or 'none'})")
    else:
        el = [int(x) for p in byml_load(files[atk])[0]["AttackParams"] for x in p.get("DamageElements", [])]
        if el != [scenes.ELEMENTS[kind]]:
            bad.append(f"{name}: its attack's elements are {el}, not {kind} ({scenes.ELEMENTS[kind]})")
    info = ap.get("AIInfoRef", "").lstrip("?")
    if info not in files:
        bad.append(f"{name}: no AI info {info} in its pack")
    row = next((r for r in byml_load(fs.read(ACTOR_INFO), allow_big=True)[0] if r.get("__RowId") == name), None)
    if row is None or not row.get("InstanceHeapSize"):
        bad.append(f"{name}: no actor row with an instance heap (the manager can't create it)")
    return bad


def verify(patch, plan, items, romfs):
    """([problem], {count}), see the module docstring. `items` is the spoiler, {OoTR location: item}."""
    sys.path[:0] = [p for p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando"))
                    if p not in sys.path]
    from romtools import Romfs, byml_load
    import chest_flags
    from . import _dungeons_routes as R
    from . import _chests_scenes as scenes
    from . import dungeons  # noqa: F401 (STORY_ROUTES: a story scene serving two chests, one branch each)
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    flows = R._Flows(fs, van)
    rows = {}
    for r in byml_load(fs.read(SCENE_TABLE), allow_big=True)[0]:
        m = re.search(r"/([^/]+)\.evfc$", str(r.get("FlowchartFileName", "")))
        if m and r.get("EntryPointName") and r.get("__RowId"):
            rows[r["__RowId"]] = (m.group(1), r["EntryPointName"])
    walk = _Walk(flows, rows, scenes.SCRATCH)
    traps = {n: TRAPS[it] for n, it in items.items() if it in TRAPS}
    bad, count, effects = [], defaultdict(int), set()
    catalog = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))}
    renames = chest_flags._renames(plan)
    levels = {}

    def placed(r):
        for f in r["files"]:
            if f not in levels:
                levels[f] = {int(a["Hash"]): a for a in byml_load(fs.read(f), allow_big=True)[0].get("Actors", [])}
            for h in chest_flags._final_hashes(r, renames):
                if h in levels[f]:
                    return levels[f][h]
        return None
    small = ("Obj_TBox_A_01", "Obj_TBox_A_01_NoBake", "Obj_TBox_GlassTruth_A_01", "Obj_TBox_A_06",
             "Obj_TBox_A_06_NoBake", "Obj_TBox_A_01_memo11", "Obj_HrlCity_Shop_TBox_A_01")
    # 1. Chest scenes
    for loc, rids in sorted(chest_flags.location_chests(traps).items()):
        want = traps[loc]
        for rid in rids:
            a = placed(catalog[rid])
            if a is None:
                bad.append(f"{loc} ({rid}): not in its level files")
                continue
            dyn = a.get("Dynamic") or {}
            content, row = dyn.get("Drop__DropActor") or "", dyn.get("GetEventName") or ""
            if a.get("Gyaml") == "Obj_TBox_A_04":  # the remake's trap chest, its AI does the ice attack
                if want != "ice":
                    bad.append(f"{loc} ({rid}): the remake's own ice-trap chest freezes, not the {items[loc]}")
                count["chest"] += 1
                continue
            start = rows.get(row) if row else DEFAULT_SCENE["small" if a.get("Gyaml") in small else "big"]
            if start is None:
                bad.append(f"{loc} ({rid}): its scene ID {row} is in no EventSetting row")
                continue
            route = (getattr(sys.modules.get("parity.dungeons"), "STORY_ROUTES", None) or {}).get(rid) or {}
            at = None
            if route.get("branch") and row and route["file"] == rows[row][0]:  # one scene for two chests,
                fc = walk.fc(route["file"])  # so start at the branch for this chest's state (Dampe's race)
                sw = next(e for e in fc["events"] if e["name"] == route["branch"])
                at = next(c["next"] for c in sw["cases"] if c["value"] == route["case"])
            got = walk.run(*start, content, at=at) if at is None else walk.run(route["file"], None, content, at=at)
            kinds = {EFFECTS[ep] for k, f, ep in got if k == "effect"}
            effects |= {(f, ep, EFFECTS[ep]) for k, f, ep in got if k == "effect"}
            plain = sorted(f"{f}:{ep}" for k, f, ep in got if k == "plain")
            missing = sorted(f"{f}:{ep}" for k, f, ep in got if k == "missing")
            if missing:
                bad.append(f"{loc} ({rid}): its scene calls missing entries {missing}")
            if kinds != {want} or plain:
                does = (" and ".join(sorted(kinds)) + " trap" if kinds else "no trap") + \
                       (f", and opens as a plain chest giving {content} ({', '.join(plain)})" if plain else "")
                bad.append(f"{loc} ({rid}, {a.get('Gyaml')}, holds {content}, scene ID {row or 'none'}): the spoiler "
                           f"says {items[loc]}, the chest plays {does}")
            count["chest"] += 1
    # 3. Give steps recorded in the plan
    for rid, spec in sorted((plan.get("rewards") or {}).items()):
        call = str((spec or {}).get("call") or "") if isinstance(spec, dict) else ""
        ep = call.split(":")[-1]
        loc = str(spec.get("note", "")).split(": ")[0] if isinstance(spec, dict) else ""
        if ep in EFFECTS and loc in traps:
            effects.add((call.split(":")[0], ep, EFFECTS[ep]))
            if EFFECTS[ep] != traps[loc]:
                bad.append(f"{loc} ({rid}): the spoiler says {items[loc]}, its give steps call {call}")
            count["call"] += 1
    for token, sp in sorted((((plan.get("_gaps") or {}).get("silver_rupees") or {}).get("spots") or {}).items()):
        call = str((sp.get("give") or {}).get("call") or "")
        if sp.get("location") in traps:
            ep = call.split(":")[-1]
            if EFFECTS.get(ep) != traps[sp["location"]]:
                bad.append(f"{sp['location']} ({token}): the spoiler says {items[sp['location']]}, the spot gives {call}")
            count["silver"] += 1
    fa = plan.get("_fairies") or {}  # fairy shuffle give keys (parity/fairies.py _give_key, the entry called)
    gives = [(n, v.get("give")) for n, v in (fa.get("stones") or {}).items()]
    gives += [(n, v.get("give")) for n, v in (fa.get("notes") or {}).items()]
    gives += [(g["location"], g.get("give")) for g in fa.get("colossus") or []]
    gives += [(g["location"], g.get("give")) for sec in ("grottos", "rooms") for v in (fa.get(sec) or {}).values()
              for g in v]
    gives += [(g["location"], g.get("give")) for b in (fa.get("beans") or {}).values() for g in b.get("gives", [])]
    deals = (((plan.get("_gaps") or {}).get("shop_deals") or {}).get("deals") or {})  # special deals' give steps
    gives += [(n, str((d.get("give") or {}).get("call") or "").split(":")[-1]) for n, d in deals.items()]
    for loc, key in gives:
        if loc in traps:
            if EFFECTS.get(key) != traps[loc]:
                bad.append(f"{loc}: the spoiler says {items[loc]}, its give step is {key}")
            count["fairy or deal"] += 1
    # Scrubs and merchants. Their sale steps name no location, so we count the kinds and compare them with the spoiler.
    # For a scrub that's each sale's marker (ActorName beside a SellerMessageId, which is Rando_IceTrap or the kind's
    # effect entry that the intercept calls). For the carpet salesman it's the root of each sale copy
    # (SimpleShop:Rando_IceTrap_SimpleShopRoot[_<Kind>]).
    import shops as shop_tools  # tools/rando/shops.py
    sm = shop_tools.shop_map()["locations"]
    want, got = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
    for loc, k in traps.items():
        e = sm.get(loc) or {}
        if e.get("mode") == "full" and e.get("kind") in ("scrub", "merchant") and loc not in deals:
            want[e["kind"]][k] += 1
    root = "SimpleShop:Rando_IceTrap_SimpleShopRoot"
    for op in plan.get("events", []):
        for n in (op.get("nodes") or {}).values():
            po = n.get("params_over") or {}
            if "SellerMessageId" in po and po.get("ActorName") in EFFECTS:
                got["scrub"][EFFECTS[po["ActorName"]]] += 1
            c = str(n.get("call") or "")
            if c.startswith(root):
                got["merchant"][(c[len(root) + 1:] or "ice").lower()] += 1
    for kind_ in ("scrub", "merchant"):
        if dict(want[kind_]) != dict(got[kind_]):
            bad.append(f"{kind_} traps: the spoiler names {dict(want[kind_])}, their sales play {dict(got[kind_])}")
        count[kind_] += sum(want[kind_].values())
    tags = defaultdict(list)  # get-scene tag -> trap locations (scene drops, heart spots and flagless drops)
    for loc, tag in (plan.get("_drops_scene_drops") or {}).items():
        if loc in traps:
            tags[int(tag)].append(loc)
    for line in plan.get("_notes_drops_get_scene", []):
        m = re.match(r"^(.*): (.*) \(get scene, tag (\d+)", line)
        if m and m.group(1) in traps:
            tags[int(m.group(3))].append(m.group(1))
    hook = walk.fc("Dm_SY_Get")
    sw = None
    for e in (hook or {}).get("events", []):
        if e["type"] == "switch" and _Walk._query(hook, e) == "EventQueryCheckTagOnPouchActor" and \
                e["name"].startswith("RandoST_LakePickups"):
            sw = e
    for tag, locs in sorted(tags.items()):
        case = next((c["next"] for c in (sw or {}).get("cases", []) if c["value"] == tag), None)
        got = set()
        if case is not None:
            todo, seen = [case], set()
            while todo:
                i = todo.pop()
                if i in seen or i == 0xFFFF:
                    continue
                seen.add(i)
                e = hook["events"][i]
                if e["type"] in ("subflow", "subflow_switch"):
                    if e.get("entry_point") in EFFECTS:
                        got.add(EFFECTS[e["entry_point"]])
                        effects.add((e.get("flowchart") or "Dm_SY_Get", e["entry_point"], EFFECTS[e["entry_point"]]))
                todo += [x for x in [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])]
                         + list(e.get("forks", [])) if x is not None]
        for loc in sorted(set(locs)):
            if got != {traps[loc]}:
                bad.append(f"{loc} (get scene, tag {tag}): the spoiler says {items[loc]}, the hook's branch plays "
                           f"{' and '.join(sorted(got)) or 'no trap'}")
            count["get scene"] += 1
    # 2. Trap effects and attackers
    for f, ep, kind in sorted(effects):
        why = _effect_ok(walk, f, ep, kind)
        if why:
            bad.append(why)
    for kind in sorted({k for _f, _e, k in effects} & set(scenes.SENSORS)):
        bad += _sensor_ok(fs, kind)
    count["effects"] = len(effects)
    # 3b. Seeds with ice traps disabled
    try:
        w = json.load(open(os.path.join(os.path.dirname(patch), "settings_used.json"),
                           encoding="utf-8"))["settings"].get("remake_trap_weights")
    except (OSError, ValueError, KeyError, TypeError):
        w = None
    if isinstance(w, dict) and not w.get("ice"):
        disguised = {x.split(":")[0] for x in plan.get("_notes_drops_disguise", [])}
        for loc in sorted(n for n, k in traps.items() if k == "ice"):
            if loc in disguised:
                count["disguised ice"] += 1  # can't hand a kind on, so the spoiler names it the Ice Trap it plays
                continue
            bad.append(f"{loc}: remake_trap_weights {w} draws no ice trap, but this spot gives one (its path drew "
                       f"no kind)")
    return bad, dict(count)
