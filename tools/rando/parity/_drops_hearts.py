"""no_collectible_hearts (OoTR's "Hero Mode", no recovery hearts drop from enemies or objects) for the drops plugin.
parity/drops.py world_plan calls plan() and tools/rando/in_game_check.py calls verify().

OoTR does it in ASM/c/get_items.c get_override_drop_id, which replaces func_8001F404, the drop conversion every
Item_DropCollectible and Item_DropCollectibleRandom goes through. A recovery-heart drop becomes a green rupee. That's
vanilla's full-health rule made unconditional, so every other drop keeps its odds. Freestanding hearts, shop hearts,
fairies and items the seed places (a "Recovery Heart" in a chest or in a shuffled pot) are untouched.

The remake does the same with its own data (read as vanilla, the same edit in every pack holding a file):
  1. GameParameter/DropGlobalParam/Default (DropLotteryMasterData). HpActor is the actor every lottery result of
     type Hp becomes (chance entries, the need-driven entries at 0 %, the before-boss "Max" lotteries, foliage
     grass). It becomes Obj_Rupee_Green, and so do the ReplaceSetting rules that turn a drop into a heart
     (FairyMax, a fairy the player can't take). ReplaceSetting's own heart -> green rupee rule (full health) stays.
  2. Every drop sub-table (Drop/DropSubTable/*, in actor packs and Pack/FoliageDropParam) with a heart, meaning an
     Items entry or Items_Max_* candidate of type Hp or one naming Obj_Heart, gets DropActorName Obj_Rupee_Green.
     Type, chance and count stay, so every other drop keeps its odds, and the tables give no heart even if the
     engine ignored HpActor.
  3. Placements that drop Obj_Heart themselves (Banc Dynamic.Drop__DropActor: Jabu-Jabu's Barinade pots, the Queen
     Gohma room grass, Spirit Temple Iron Knuckle thrones, crumbling Ganon's Castle pots, boss-rush stages) and the
     drops plugin's twins of them (vanilla copies) -> Obj_Rupee_Green. Not if the seed gives the spot an item (the
     plan sets its drop, or it holds an OoTR-placed Recovery Heart, which stays a heart like in OoTR).
  4. Get_StoneOfForest "Disappear" (the Deku Tree scrub brothers). When a scrub runs away, its heart appears if the
     player can take one, else its green rupee (a switch on PouchSystemActor.EventQueryCanAddToPorch Shop_Heart).
     Every case goes to the green-rupee branch. A scrub whose heart or rupee the seed uses no longer reaches it
     (_drops_scrubs.py).
Not changed: freestanding hearts (placed Obj_Heart / Obj_Heart_InWater), hearts sold by shops and business scrubs
(Shop_Heart, Shop_Heart_Bundle), fairies, heart pieces and containers, adult Zelda's EventScatterHeart (no event
calls it).
"""
import os
import re
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for _p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RUPEE_ACTOR = "Obj_Rupee_Green"
RUPEE = f"Work/Actor/{RUPEE_ACTOR}.engine__actor__ActorParam.gyml"
HEARTS = ("Obj_Heart", "Obj_Heart_InWater")  # recovery hearts (not pieces, containers, Zelda's Obj_Heart_Shootable)
HEART_ITEM = "Recovery Heart"
HP = 1872319531  # murmur3 "Hp", the drop type of recovery hearts (DropLotteryMasterData.HpActor)
GLOBAL = "GameParameter/DropGlobalParam/Default.game__drop__DropGlobalParam.bgyml"
SUB_DIR = "Drop/DropSubTable/"
CANDIDATES = ("Items_Max_FirstCandidate", "Items_Max_SecondCandidate", "Items_Max_ThirdCandidate")
SCRUB_EVENT = "Get_StoneOfForest"  # the only event showing a dropped heart by the pouch test (I read every Event/ file)
SCRUB_QUERY = ("PouchSystemActor", "EventQueryCanAddToPorch", "Shop_Heart")


def _romfs():
    import drops  # tools/rando/drops.py
    return drops.DEFAULT_ROMFS


def _fs(romfs, overlays=()):
    from romtools import Romfs
    return Romfs(romfs, os.path.join(HERE, "original"), list(overlays))


def _actor(path):
    """The actor a Work/Actor/... path (or a bare name) names."""
    return (path or "").split("/")[-1].split(".")[0]


def is_heart(path):
    return _actor(path) in HEARTS


def heart_entry(e):
    """Whether an Items entry or Items_Max candidate gives a recovery heart, either type Hp (with no other actor named)
    or naming a heart."""
    if not isinstance(e, dict):
        return False
    name = e.get("DropActorName") or ""
    return is_heart(name) or (e.get("Type") == HP and _actor(name) in ("",) + HEARTS)


def table_sets(d):
    """{path: Obj_Rupee_Green} for every heart entry of sub-table `d` (a parsed DropSubTable)."""
    out = {}
    for i, e in enumerate(d.get("Items") or []):
        if heart_entry(e):
            out[f"Items.{i}.DropActorName"] = RUPEE
    for key in CANDIDATES:
        c = d.get(key)
        if isinstance(c, list):
            for i, e in enumerate(c):
                if heart_entry(e):
                    out[f"{key}.{i}.DropActorName"] = RUPEE
        elif heart_entry(c):
            out[f"{key}.DropActorName"] = RUPEE
    return out


def table_hearts(d):
    """The entries of sub-table `d` that still give a heart (heart entries not naming Obj_Rupee_Green)."""
    left = []
    for path in table_sets(d):
        node = d
        for t in path.split(".")[:-1]:
            node = node[int(t)] if isinstance(node, list) else node[t]
        if node.get("DropActorName") != RUPEE:
            left.append(path.rsplit(".", 1)[0])
    return left


def global_sets(d):
    """{path: Obj_Rupee_Green} for DropGlobalParam's heart outputs, HpActor and every ReplaceSetting rule's heart."""
    m = d.get("DropLotteryMasterData") or {}
    out = {}
    if is_heart(m.get("HpActor")):
        out["DropLotteryMasterData.HpActor"] = RUPEE
    for i, rule in enumerate(m.get("ReplaceSetting") or []):
        for j, r in enumerate(rule.get("ReplaceActor") or []):
            if is_heart(r.get("ReplaceActor")):
                out[f"DropLotteryMasterData.ReplaceSetting.{i}.ReplaceActor.{j}.ReplaceActor"] = RUPEE
    return out


def _banc_files(romfs):
    root = os.path.join(romfs, "Banc")
    for dp, _, fns in os.walk(root):
        for fn in sorted(fns):
            if fn.endswith(".bcett.byml.zs"):
                yield os.path.relpath(os.path.join(dp, fn), romfs).replace(os.sep, "/")


def heart_droppers(fs, romfs):
    """[(file, hash)] of every placement whose Dynamic.Drop__DropActor is a heart, as `fs` reads the level files."""
    from romtools import byml_load
    out = []
    for rel in sorted(_banc_files(romfs)):
        for a in byml_load(fs.read(rel))[0].get("Actors") or []:
            if is_heart((a.get("Dynamic") or {}).get("Drop__DropActor")):
                out.append((rel, str(a.get("Hash"))))
    return out


def _event_path(romfs):
    d = os.path.join(romfs, "Event", "EventFlow")
    rx = re.compile(re.escape(SCRUB_EVENT) + r"(\.\d{3})?\.bfevfl\.zs$")
    return sorted(f"Event/EventFlow/{f}" for f in os.listdir(d) if rx.match(f))


def scrub_switches(fs, romfs):
    """[{"file", "flowchart", "event", "cases": [index...], "next", "heart_cases"}] for the scrub event. One per switch
    that asks whether a heart fits the pouch, with the cases that lead to its heart branch and the green-rupee
    branch."""
    from evfl import Evfl
    out = []
    for rel in _event_path(romfs):
        ev = Evfl(fs.read(rel))
        for fc in ev.flowcharts:
            by_idx = {e["idx"]: e for e in fc["events"]}

            def actor_of(e):
                return fc["actors"][e["actor"]]["name"] if e.get("actor") is not None and "actor" in e else None
            for e in fc["events"]:
                if e["type"] != "switch":
                    continue
                a = fc["actors"][e["actor"]]
                q = a["queries"][e["query"]] if e["query"] < len(a.get("queries", [])) else None
                items = ((e.get("params") or {}).get("items") or {})
                if (a["name"], q, (items.get("Actor") or {}).get("value")) != SCRUB_QUERY:
                    continue
                kinds = {}
                for k, c in enumerate(e["cases"]):
                    t = by_idx.get(c["next"])
                    kinds[k] = actor_of(t) if t is not None else None
                rupee = [k for k, a_ in kinds.items() if a_ == RUPEE_ACTOR]
                heart = [k for k, a_ in kinds.items() if a_ in HEARTS]
                if not rupee or not heart:
                    continue
                out.append({"file": rel, "flowchart": fc["name"], "event": e["name"], "heart_cases": heart,
                            "next": by_idx[e["cases"][rupee[0]]["next"]]["name"]})
    return out


@lru_cache(maxsize=2)
def survey(romfs=None):
    """What the setting edits in the vanilla game: {"global": sets, "tables": {sub-table: sets}, "droppers": [(file,
    hash)], "switches": [...]}."""
    import packpaths
    from romtools import byml_load, sarc_files
    romfs = romfs or _romfs()
    fs = _fs(romfs)
    tables = {}
    for inner, packs in sorted(packpaths.index(romfs).items()):
        if inner.startswith(SUB_DIR) and packs:
            sets = table_sets(byml_load(sarc_files(fs.read(packs[0]))[inner], allow_big=True)[0])
            if sets:
                tables[inner] = sets
    return {"global": global_sets(byml_load(fs.raw(GLOBAL))[0]), "tables": tables,
            "droppers": heart_droppers(fs, romfs), "switches": scrub_switches(fs, romfs)}


def plan(kept, placements, romfs=None):
    """The plan sections for no_collectible_hearts. `kept` is {location: (drop-map entry, item name)} for the drop
    plugin's shuffled spots. `placements` is the plugin's placement ops, and its twins of heart droppers get the green
    rupee here, in place."""
    s = survey(romfs)
    spot = {}  # (file, hash) -> item name, for the spots the seed shuffles
    for name, (e, item) in kept.items():
        for p in (e or {}).get("placements", []):
            spot[(p["file"], str(p["hash"]))] = item
    sets_drop, deleted = set(), set()
    for op in placements:
        key = (op["file"], str(op["hash"]))
        if op.get("twin") is not None:
            continue
        if op.get("delete"):
            deleted.add(key)
        if "Dynamic.Drop__DropActor" in (op.get("set") or {}):
            sets_drop.add(key)
    droppers = set(s["droppers"])
    ops, allowed, twins = [], [], 0
    for key in s["droppers"]:
        if key in sets_drop or key in deleted:
            continue  # the seed's item decides what it drops
        if spot.get(key) == HEART_ITEM:
            allowed.append(list(key))  # an OoTR-placed Recovery Heart is a placed item, not a collectible drop
            continue
        ops.append({"file": key[0], "hash": key[1], "set": {"Dynamic.Drop__DropActor": RUPEE_ACTOR}})
    for op in placements:  # twins (vanilla copies, the respawn model) of a heart dropper drop what vanilla would
        if op.get("twin") is not None and (op["file"], str(op["hash"])) in droppers:
            st = op.setdefault("set", {})
            if "Dynamic.Drop__DropActor" not in st:
                st["Dynamic.Drop__DropActor"] = RUPEE_ACTOR
                twins += 1
    # _drops_scrubs.py skips this switch when the seed shuffles the pickup. For the other scrubs the heart branches go
    # to the green rupee too.
    events = []
    for sw in s["switches"]:
        base = os.path.basename(sw["file"]).split(".")[0]
        events += [{"file": base, "flowchart": sw["flowchart"], "event": sw["event"], "case": k,
                    "next": sw["next"]} for k in sw["heart_cases"]]
    packs = [{"pack": "*", "file": inner, "set": dict(sets)} for inner, sets in sorted(s["tables"].items())]
    rules = sum(1 for k in s["global"] if ".ReplaceSetting." in k)
    out = {"packs": packs, "placements": ops, "events": events,
           "_drops_no_hearts": {"tables": sorted(s["tables"]), "global": sorted(s["global"]),
                                "placements": [list(k) for k in s["droppers"] if list(k) not in allowed],
                                "allowed": allowed, "switches": s["switches"],
                                "twins": twins},
           "_notes_drops_no_hearts": [
               f"no_collectible_hearts: recovery hearts dropped by enemies and objects become green rupees "
               f"(DropGlobalParam HpActor and {rules} replace rule(s); {len(packs)} drop tables; {len(ops)} "
               f"placements and {twins} twins dropping a heart; the Deku Tree scrubs' heart)"]}
    if s["global"]:
        out["byml"] = [{"file": GLOBAL, "set": dict(s["global"])}]
    if allowed:
        out["_notes_drops_no_hearts"].append(f"{len(allowed)} spots keep their heart drop: OoTR placed a Recovery "
                                             f"Heart there (a placed item, as in OoTR)")
    return out


def seed_hearts(plan):
    """{(file, hash)} the plan itself makes drop a heart, as a seed item (OoTR's "Recovery Heart" at a shuffled object)
    set by any plugin's placement op. Twins (vanilla copies) never count."""
    return {(op["file"], str(op["hash"])) for op in (plan or {}).get("placements", [])
            if op.get("twin") is None and is_heart((op.get("set") or {}).get("Dynamic.Drop__DropActor"))}


def verify(patch_dir, spec, romfs=None, plan=None):
    """Reads the built patch back and returns [problem]. No drop sub-table in any pack still gives a heart,
    DropGlobalParam gives none, and the scrub switches lead to the green rupee. No placement drops one either, except
    the spots OoTR gave a Recovery Heart (spec "allowed") and, with `plan`, the placements its ops make drop one."""
    import packpaths
    from evfl import Evfl
    from romtools import byml_load, sarc_files
    romfs = romfs or _romfs()
    fs = _fs(romfs, [patch_dir])
    bad = []
    g = byml_load(fs.raw(GLOBAL))[0]
    bad += [f"{GLOBAL}: {p} still gives a heart" for p in global_sets(g)]
    by_pack = {}
    for inner, packs in packpaths.index(romfs).items():
        if inner.startswith(SUB_DIR):
            for pk in packs:
                by_pack.setdefault(pk, []).append(inner)
    n = 0
    for pk in sorted(by_pack):
        files = sarc_files(fs.read(pk))
        for inner in sorted(by_pack[pk]):
            left = table_hearts(byml_load(files[inner], allow_big=True)[0])
            n += 1
            if left:
                bad.append(f"{pk}:{inner}: {', '.join(left)} still give a heart")
    allowed = {tuple(k) for k in spec.get("allowed", [])} | seed_hearts(plan)
    for key in heart_droppers(fs, romfs):
        if key not in allowed:
            bad.append(f"{key[0]} placement {key[1]} still drops a heart")
    for sw in spec.get("switches", []):
        ev = Evfl(fs.read(sw["file"]))
        fc = next((f for f in ev.flowcharts if f["name"] == sw["flowchart"]), None)
        e = next((x for x in (fc or {}).get("events", []) if x["name"] == sw["event"]), None)
        if e is None:
            bad.append(f"{sw['file']}: no {sw['event']}")
            continue
        names = {x["idx"]: x["name"] for x in fc["events"]}
        wrong = [k for k, c in enumerate(e["cases"]) if names.get(c["next"]) != sw["next"]]
        if wrong:
            bad.append(f"{sw['file']} {sw['event']}: case(s) {wrong} still lead to the heart")
    if n == 0:
        bad.append("no drop sub-table read back")
    return bad


if __name__ == "__main__":
    import json
    s = survey(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({"global": s["global"], "tables": {k: sorted(v) for k, v in s["tables"].items()},
                      "droppers": len(s["droppers"]), "switches": s["switches"]},
                     indent=1))
