"""Build the catalog of every reward in the remake.

usage: python tools/catalog.py ROMFS_DIR OUT_DIR [PATCH_DIR ...]
(with PATCH_DIRs, the catalog shows the game as it would be with those patches installed)

Files saved in ./original (vanilla copies of anything we patched) are read instead of the live ones.

Writes:
  OUT_DIR/rewards.json      every reward (one field that gives an item), with a stable id and its location
  OUT_DIR/locations.json    rewards grouped into checks (an NPC gift can be an inventory add + a display)
  OUT_DIR/rewards.csv       one row per location, with an empty `new_item` column to fill in
  OUT_DIR/event_checks.json every place an event checks for an item (needed when moving NPC rewards)
  OUT_DIR/items.json        every item-like actor name the game has, with its pouch category

Reward kinds
  chest            Dynamic.Drop__DropActor on Obj_TBox* (plus GetEventName / substitute fields)
  drop             Dynamic.Drop__DropActor on pots, rocks, crates, beehives, trees, grass, enemies
  gold_skulltula   Enemy_Skulltula_Gold; vanilla drop comes from its drop table (Obj_Token_Gold),
                   editing sets an instance Dynamic.Drop__DropActor (works for normal Skulltulas)
  freestanding     an item actor placed in the world; editing swaps the actor (Gyaml)
  shop             a Shop_* display actor; editing swaps it for another Shop_* actor
  scrub            Enemy_Scrub_Business offers: Dynamic.ScrubBusiness_ShopItemActorName0..2
  event            an item handed over by an event flow (NPCs, songs, medallions, minigames, ...)
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from romtools import Romfs, byml_load  # noqa: E402
from evfl import Evfl  # noqa: E402

FREESTANDING = re.compile(
    r"^(Obj_Heart_Piece|Obj_GerudoValley_Heart_Piece|Obj_Heart_Container|Obj_Dungeon_SmallKey\w*|"
    r"Obj_Dungeon_BossKey\w*|Obj_Bottle_Letter|Obj_Arrow_Fire|Obj_Token_Gold|Item_\w+|Weapon_Bottle|"
    r"Obj_Rupee_(Red|Purple|Gold|Silver|Big)\w*|Obj_DekuNut|Obj_DekuSeed|Obj_DekuStick)$")
DROP_FIELDS = ("Drop__DropActor",)
CHEST_EXTRA = ("GetEventName", "Drop__DropActor_Substitute", "Drop__CheckActor", "DropViewActor")
SCRUB_FIELDS = ("ScrubBusiness_ShopItemActorName0", "ScrubBusiness_ShopItemActorName1",
                "ScrubBusiness_ShopItemActorName2")

# Event parameters that hand an item to the player: (event kind, call pattern, param name).
# Call is "Actor.Action" for actions and "Flowchart:EntryPoint" for sub-flows (flowchart may be empty).
GIVE_PATTERNS = [
    ("subflow", r"^GetPouchContent:(GetPouchContentByActorName|DisplayGetByActorName|DisplayRutoGetByActorName)$", "ActorName"),
    ("subflow", r"^Dm_SY_GetInEvent:GetInEvent\w*$", "ActorName"),
    ("subflow", r"^GetInEvent_EggHatche:\w+$", "ActorName"),
    ("subflow", r"^(NpcCommon)?:NpcCommon_HandOver_NpcToPlayer\w*$", "ReveiveItem"),
    ("subflow", r"^(NpcCommon)?:SellMask$", "ReceiveItem"),
    ("subflow", r"^:TakenReward_Common_Event$", "TakenRewardActor"),
    ("subflow", r"^(Enemy_Scrub_Business_Common)?:SimpleShopSub_Scrub_Business_OneTime$", "ActorName"),
    ("subflow", r"^SimpleShop:SimpleShopRoot\w*$", "ActorName"),
    ("subflow", r"^:MushiToriGame$", "ActorName"),
    ("subflow", r"^:DiggingHoleTour_Demo$", "DropActorName"),
    ("subflow", r"^:GerudoThiefDropKey$", "Obj_SmallKey"),
    ("action", r"^PouchSystemActor\.EventTriggerAddOrRemovePouchContent$", "Actor"),
    ("action", r"^Npc_Hylia_Dampe_001\.EventMiniGameDiggingHoleAdventActor$", "ActorName"),
]
CHECK_PATTERNS = [
    ("switch", r"^PouchSystemActor\.EventQueryIsExistInPouch$", "Actor"),
    ("switch", r"^GameDataActor\.EventQueryCheckIsGet$", "ActorName"),
    ("switch", r"^PouchSystemActor\.EventQueryCanAddToPorch$", "Actor"),
    ("switch", r"^Player_Event\.EventQueryPlayerIsEquip(Armor|Weapon)$", "ArmorName"),
]


def walk_params(c, path=""):
    if not c:
        return
    if c["type"] == "container":
        for k, v in c["items"].items():
            yield from walk_params(v, f"{path}.{k}" if path else k)
    else:
        yield path, c


def event_calls(fc):
    for ev in fc["events"]:
        t = ev["type"]
        if t in ("action", "switch"):
            a = fc["actors"][ev["actor"]]
            name = a["name"] + "." + (a["actions"][ev["action"]] if t == "action" else a["queries"][ev["query"]])
            kind = t
        elif t in ("subflow", "subflow_switch"):
            name = f"{ev['flowchart'] or ''}:{ev['entry_point']}"
            kind = "subflow"
        else:
            continue
        yield ev, kind, name


def matches(patterns, kind, call, param):
    return any(k == kind and re.match(rx, call) and p == param for k, rx, p in patterns)


def event_base(fn):
    """Get_Foo.110.bfevfl.zs and Get_Foo.bfevfl.zs are versions of the same event file."""
    return re.sub(r"(\.\d{3})?\.bfevfl\.zs$", "", fn)


VANILLA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "original")


def main(romfs, out_dir, *overlays):
    fs = Romfs(romfs, VANILLA, overlays)
    load = fs.read
    os.makedirs(out_dir, exist_ok=True)

    pouch, _ = byml_load(load("RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"))
    pouch = {r["__RowId"]: r for r in pouch}
    actors = sorted(f[:-len(".pack.zs")] for f in os.listdir(os.path.join(romfs, "Pack", "Actor")) if f.endswith(".pack.zs"))
    item_like = re.compile(r"^(Item_|Obj_Heart|Obj_Token|Obj_Rupee|Obj_Dungeon_|TBox_|Tbox_|Shop_|Weapon_|Armor_|Pouch_|Obj_Deku|Obj_Arrow|Obj_Bottle|Obj_MagicJar)")
    items = {a: {"pouch_category": pouch.get(a, {}).get("PouchCategory"),
                 "pouch_get_type": pouch.get(a, {}).get("PouchGetType")}
             for a in actors if item_like.match(a) or a in pouch}
    json.dump(items, open(os.path.join(out_dir, "items.json"), "w", encoding="utf-8"), indent=1)

    rewards = {}

    # Placements
    banc = os.path.join(romfs, "Banc")
    for area in sorted(os.listdir(banc)):
        p = os.path.join(banc, area)
        if not os.path.isdir(p) or area in ("BancBasedResource", "GameBancParam"):
            continue
        for fn in sorted(os.listdir(p)):
            if not fn.endswith(".bcett.byml.zs"):
                continue
            rel = f"Banc/{area}/{fn}"
            stage = fn.replace(".bcett.byml.zs", "")
            root, _ = byml_load(load(rel))
            for a in (root or {}).get("Actors", []) or []:
                g, h = a.get("Gyaml", ""), str(a.get("Hash"))
                dyn = a.get("Dynamic") or {}
                found = []
                if "TBox" in g and not g.startswith(("Land_", "DropKeepAway")) and "Pedestal" not in g:
                    found.append(("chest", "Dynamic.Drop__DropActor", dyn.get("Drop__DropActor")))
                elif g == "Enemy_Skulltula_Gold":
                    found.append(("gold_skulltula", "Dynamic.Drop__DropActor", dyn.get("Drop__DropActor") or "Obj_Token_Gold"))
                elif g == "Enemy_Scrub_Business":
                    for i, f in enumerate(SCRUB_FIELDS):
                        if f in dyn:
                            found.append(("scrub", f"Dynamic.{f}", dyn[f]))
                elif g.startswith("Shop_") and not g.startswith("Shop_Board_"):  # boards = price tags / sold-out signs
                    found.append(("shop", "Gyaml", g))
                elif FREESTANDING.match(g):
                    found.append(("freestanding", "Gyaml", g))
                elif dyn.get("Drop__DropActor"):
                    found.append(("drop", "Dynamic.Drop__DropActor", dyn["Drop__DropActor"]))
                for kind, field, value in found:
                    rid = f"{area}/{kind}/{h}" + (f"/{field.split('.')[-1]}" if kind == "scrub" else "")
                    r = rewards.setdefault(rid, {
                        "id": rid, "kind": kind, "area": area, "source": "placement",
                        "actor": g, "hash": h, "field": field, "item": value,
                        "pos": [round(x, 1) for x in a.get("Translate", [0, 0, 0])],
                        "room": dyn.get("DefaultDungeonRoomIndex"),
                        "extra": {k: dyn[k] for k in CHEST_EXTRA if k in dyn},
                        "files": [], "stages": [],
                        "dreamworld": area == "DreamWorld",
                    })
                    r["files"].append(rel)
                    r["stages"].append(stage)
                    if r["item"] != value:
                        r.setdefault("differs_by_file", {})[rel] = value

    # Events
    checks = []
    edir = os.path.join(romfs, "Event", "EventFlow")
    parsed = {}
    callers = defaultdict(set)  # flowchart name -> other event files that call into it
    for fn in sorted(os.listdir(edir)):
        if not fn.endswith(".bfevfl.zs"):
            continue
        rel = f"Event/EventFlow/{fn}"
        parsed[fn] = ev = Evfl(load(rel))
        for fc in ev.flowcharts:
            for e in fc["events"]:
                if e["type"] in ("subflow", "subflow_switch") and e.get("flowchart") and e["flowchart"] != fc["name"]:
                    callers[e["flowchart"]].add(event_base(fn))
    called_from_elsewhere = {name for name, files in callers.items() if len(files) >= 3}
    for fn, ev in parsed.items():
        rel = f"Event/EventFlow/{fn}"
        for fc in ev.flowcharts:
            for e, kind, call in event_calls(fc):
                for path, c in walk_params(e.get("params")):
                    if c["type"] != "string":  # "argument" = passed through from the caller, not a reward
                        continue
                    v = c["value"]
                    if matches(GIVE_PATTERNS, kind, call, path):
                        rid = f"event/{event_base(fn)}/{fc['name']}/{e['name']}/{path}"
                        r = rewards.setdefault(rid, {
                            "id": rid, "kind": "event", "area": None, "source": "event",
                            "event_file": event_base(fn), "flowchart": fc["name"], "event": e["name"],
                            "call": call, "param": path, "item": v, "files": [],
                            "shared": fc["name"] in called_from_elsewhere,
                            "dreamworld": bool(re.search(r"Dream|AllBossBattle|BossRush", fn)),
                        })
                        r["files"].append(rel)
                        if r["item"] != v:
                            r.setdefault("differs_by_file", {})[rel] = v
                    elif matches(CHECK_PATTERNS, "switch" if kind == "switch" else kind, call, path):
                        checks.append({"file": rel, "flowchart": fc["name"], "event": e["name"],
                                       "call": call, "param": path, "item": v})

    out = sorted(rewards.values(), key=lambda r: (r["source"], r.get("area") or "", r["kind"], r["id"]))
    # A location groups the rewards that make up one check. In an event file that's every give/display of
    # the same vanilla item, e.g. Saria's ocarina is an inventory add plus a "you got" display.
    locations = {}
    for r in out:
        loc = f"event/{r['event_file']}/{r['item']}" if r["source"] == "event" else r["id"]
        r["location"] = loc
        L = locations.setdefault(loc, {"location": loc, "kind": r["kind"], "area": r.get("area"), "item": r["item"],
                                       "members": [], "dreamworld": r.get("dreamworld", False),
                                       "shared": r.get("shared", False)})
        L["members"].append(r["id"])
        L["shared"] |= r.get("shared", False)
        if r["source"] == "placement":
            L["where"] = f"{r['actor']} @ {r['pos']}" + (f" room {r['room']}" if r["room"] is not None else "")
        else:
            L.setdefault("calls", []).append(f"{r['call']} ({r['event']})")
    json.dump(out, open(os.path.join(out_dir, "rewards.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(sorted(locations.values(), key=lambda L: L["location"]),
              open(os.path.join(out_dir, "locations.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(checks, open(os.path.join(out_dir, "event_checks.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "rewards.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "area", "where", "notes", "vanilla_item", "new_item"])
        for L in sorted(locations.values(), key=lambda L: (L["kind"] == "event", L["area"] or "", L["kind"], L["location"])):
            where = L.get("where") or "; ".join(L["calls"])
            notes = "; ".join(n for n, on in (("boss rush mode", L["dreamworld"]),
                                              ("shared flow: affects every caller", L["shared"]),
                                              (f"{len(L['members'])} parts edited together", len(L["members"]) > 1)) if on)
            w.writerow([L["location"], L["kind"], L["area"] or "", where, notes, L["item"] or "", ""])

    by = defaultdict(int)
    for r in out:
        by[r["kind"]] += 1
    print(f"{len(out)} rewards in {len(locations)} locations: " + ", ".join(f"{k} {n}" for k, n in sorted(by.items())))
    print(f"{len(checks)} event item checks, {len(items)} item-like actors")


if __name__ == "__main__":
    main(*sys.argv[1:])
