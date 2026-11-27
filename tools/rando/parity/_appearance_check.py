"""Reads a built patch back and checks the appearance edits: exactly the planned colours and chest types, the right
item and scene in every retyped chest, and nothing else changed.

usage: python tools/rando/parity/_appearance_check.py ROMFS PATCH_DIR PLAN.json [--list]

For every level file the plan's appearance edits touch (colours are placements setting
GameModelController_GeneralInstanceParam*, chest types are placements whose note starts with "appearance:" setting
Gyaml):
- each coloured placement holds exactly the planned three values. Each retyped chest has the planned type, still
  accepts every Dynamic key it carries (tools/actor_params.py), holds the item the plan's reward gives it (a
  progressive item's first tier) and opens with a scene of its new size. That's no GetEventName (the type's own
  default, Dm_SY_TreasureboxSmall / Dm_SY_Treasurebox) or a scene ID whose scene file (RSDB EventSetting, the
  patched table when the patch has one) is that size's chest scene. A scene of the old size, or a story scene on a
  chest that changed size, is an error.
- its other fields differ from vanilla only where another plan edit names them
- every other placement of the file is unchanged unless some plan edit or reward names it, and no placement is
  added or lost
--list prints one line per retyped chest (type, item, scene). Exits non-zero on any mismatch.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load  # noqa: E402
from actor_params import ActorParams  # noqa: E402

KEY = "GameModelController_GeneralInstanceParam"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
FAMILY = {"Obj_TBox_A_01": "small", "Obj_TBox_A_01_NoBake": "small", "Obj_TBox_GlassTruth_A_01": "small",
          "Obj_TBox_A_02": "big", "Obj_TBox_A_02_NoBake": "big", "Obj_TBox_A_03": "big", "Obj_TBox_A_03_NoBake": "big"}
SCENE_FILE = {"small": "Dm_SY_TreasureboxSmall", "big": "Dm_SY_Treasurebox"}


def _flat(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out.update(_flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def scene_files(fs, patch_dir):
    """{scene ID: flowchart file base name} from the patched EventSetting table (vanilla if the patch has none)."""
    p = os.path.join(patch_dir, EVENT_SETTING)
    data = fs.zs.decompress(open(p, "rb").read()) if os.path.exists(p) else fs.read(EVENT_SETTING)
    # Archipelago uses renamed copies of both chest scenes, so they count as their originals here (CHEST_HOSTS in
    # parity/archipelago.py).
    from parity import archipelago
    copies = {host: archipelago.CHEST_FILES[size] for size, host in archipelago.CHEST_HOSTS.items()}
    out = {r["__RowId"]: (r.get("FlowchartFileName") or "").rsplit("/", 1)[-1].replace(".evfc", "")
           for r in byml_load(data)[0]}
    return {k: copies.get(v, v) for k, v in out.items()}


def check(romfs, patch_dir, plan, flags=()):
    """(problems, lines, coloured read back, coloured planned, retyped read back, retyped planned)."""
    import make_patch  # tools/make_patch.py, for the instance keys the plan adds (the drops plugin's Drop__RandoChk...)
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    ap = ActorParams(romfs)
    ap.planned = make_patch.planned_instance_keys(dict({"ainb": []}, **plan), romfs)
    catalog = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))}
    progressive = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]
    tints, retypes, named = {}, {}, {}
    for op in plan.get("placements", []):
        key = (op["file"], str(op["hash"]))
        named.setdefault(key, set()).update(set(op.get("set", {})) | set(op.get("remove", [])))
        if any(k.startswith(f"Dynamic.{KEY}") for k in op.get("set", {})):
            tints[key] = {k: v for k, v in op["set"].items() if k.startswith(f"Dynamic.{KEY}")}
        if str(op.get("note", "")).startswith("appearance:") and "Gyaml" in op.get("set", {}):
            retypes[key] = (op["set"]["Gyaml"], op["note"])
    reward_hashes, planned_item = set(), {}
    for rid, spec in plan.get("rewards", {}).items():
        for r in [catalog[rid]] if rid in catalog else [x for x in catalog.values() if x.get("location") == rid]:
            if r.get("hash"):
                reward_hashes.add(str(r["hash"]))
                item = spec["item"] if isinstance(spec, dict) else spec
                planned_item[str(r["hash"])] = progressive[item]["tiers"][0] if item in progressive else item
    by_hash = {str(r["hash"]): r for r in catalog.values() if r.get("kind") == "chest"}
    scenes = scene_files(fs, patch_dir) if retypes else {}
    problems, lines, n_tint, n_type = [], [], 0, 0
    for file in sorted({f for f, _ in list(tints) + list(retypes)}):
        dst = os.path.join(patch_dir, file)
        if not os.path.exists(dst):
            problems.append(f"{file}: not in the patch")
            continue
        renamed = {str(op["hash"]): str(op["set"]["Hash"]) for op in plan.get("placements", [])
                   if op["file"] == file and "Hash" in op.get("set", {})}  # another plugin's new save flag
        old = {renamed.get(str(a["Hash"]), str(a["Hash"])): a for a in byml_load(fs.read(file))[0]["Actors"]}
        new = {str(a["Hash"]): a for a in byml_load(fs.zs.decompress(open(dst, "rb").read()))[0]["Actors"]}
        for h_old, h_new in renamed.items():
            named[(file, h_new)] = named.get((file, h_old), set()) | {"Hash"}
        ops = [op for op in plan.get("placements", []) if op["file"] == file]
        twins = {str(op["twin"]) for op in ops if op.get("twin")}  # new actors: vanilla copies (the respawn model)
        gone = {str(op["hash"]) for op in ops if op.get("delete")}
        if set(new) != (set(old) - gone) | twins:
            problems.append(f"{file}: placements added or removed ({len(old)} -> {len(new)}; planned "
                            f"{len(gone)} deleted, {len(twins)} twins)")
        for h, a in new.items():
            b = old.get(h)
            if b is None:
                continue
            fa, fb = _flat(a), _flat(b)
            key = (file, h)
            names = named.get(key, set())
            # a planned key covers its sub-fields (a set Presence is flattened to Presence.FlagName, ...)
            diff = {k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)
                    and not any(k.startswith(n + ".") for n in names)}
            if key in tints:
                n_tint += 1
                for k, v in tints[key].items():
                    if abs(float(fa.get(k, 1.0)) - v) > 1e-6:
                        problems.append(f"{file} {h}: {k} = {fa.get(k)}, planned {v}")
            if key in retypes:
                n_type += 1
                target, note = retypes[key]
                dyn = a.get("Dynamic") or {}
                if a.get("Gyaml") != target:
                    problems.append(f"{file} {h}: type {a.get('Gyaml')}, planned {target}")
                want_item = planned_item.get(h, (by_hash.get(h) or {}).get("item"))
                if dyn.get("Drop__DropActor") != want_item:
                    problems.append(f"{file} {h}: holds {dyn.get('Drop__DropActor')}, the plan gives {want_item}")
                ev = dyn.get("GetEventName")
                fam_old, fam_new = FAMILY.get(b.get("Gyaml")), FAMILY.get(target)
                scene = scenes.get(ev) if ev else SCENE_FILE.get(fam_new)
                if ev and fam_old != fam_new and scene != SCENE_FILE.get(fam_new):
                    problems.append(f"{file} {h}: became {fam_new} but opens with {ev} ({scene})")
                lines.append(f"{note.split(': ', 1)[1]} | holds {dyn.get('Drop__DropActor')} | scene "
                             f"{ev or 'type default'} ({scene})")
            if key in tints or key in retypes:
                bad = set((a.get("Dynamic") or {}).keys()) - ap.allowed(a.get("Gyaml", ""))
                if bad:
                    problems.append(f"{file} {h}: {a.get('Gyaml')} does not accept {sorted(bad)}")
                extra = diff - named.get(key, set()) - {k for k in diff if k.startswith(f"Dynamic.{KEY}")}
                if h in reward_hashes:  # the reward's own fields (item, scene, chest-bound settings)
                    extra -= {"Dynamic.Drop__DropActor", "Dynamic.GetEventName", "Dynamic.Drop__CheckActor",
                              "Dynamic.Drop__DropActor_Substitute", "Gyaml"}
                    # with "Ammo Without Its Bag: Blue Rupee" a chest holding container ammo names its ammo, Blue
                    # Rupee and container (drops.py AMMO SWITCH, parity/_ammo.py switch_ops)
                    extra -= {"Dynamic.Drop__RandoAmmo", "Dynamic.Drop__RandoAmmoNo", "Dynamic.Drop__RandoAmmoBag"}
                if extra:
                    problems.append(f"{file} {h}: unplanned changes {sorted(extra)}")
            elif diff and key not in named and h not in reward_hashes:
                problems.append(f"{file} {h} ({a.get('Gyaml')}): changed but no plan edit names it: {sorted(diff)}")
    if n_tint != len(tints) or n_type != len(retypes):
        problems.append(f"read back {n_tint}/{len(tints)} coloured and {n_type}/{len(retypes)} retyped placements")
    return problems, lines, n_tint, len(tints), n_type, len(retypes)


def main(romfs, patch_dir, plan_path, *flags):
    problems, lines, n_tint, tints, n_type, retypes = check(
        romfs, patch_dir, json.load(open(plan_path, encoding="utf-8")), flags)
    if "--list" in flags:
        for ln in sorted(lines):
            print("  " + ln)
    print(f"appearance check: {n_tint}/{tints} coloured placements and {n_type}/{retypes} retyped chest "
          f"placements read back; {len(problems)} problems")
    for p in problems[:50]:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
