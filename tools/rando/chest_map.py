"""Pair OoT Randomizer's chests with the remake's chests.

usage: python tools/rando/chest_map.py            (writes data/rando/chest_map.json and prints a summary)

We start from data/ootr_match.json (OoTR location -> candidate remake locations in the same area). Then, within
each set of candidates, we go by vanilla item (OoTR item names translated with config/item_map.json):
  full     the pair is certain: an exact match, or the vanilla item is the only one of its kind on both sides.
           Fully randomized.
  group    same number of chests with the same vanilla item on both sides, but no way to tell which is which (say
           three small-key chests in one room list). They're paired in order and fully randomized. The generator
           gives every chest of the group the rule "every chest of the group is reachable" (OoTR events, one per
           chest under its own rule), so whichever chest an item really lands in is reachable when logic says so.
  vanilla  no reliable counterpart (counts differ, no remake chest, or a minigame chest). It's locked to its
           vanilla item, and the remake chest, if there is one, is left alone.
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(HERE, "data", "rando", "chest_map.json")
ITEM_MAP = json.load(open(os.path.join(HERE, "config", "item_map.json"), encoding="utf-8"))
PROGRESSIVE = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]

# Chests that belong to a minigame or story sequence the remake runs itself. These never move.
ALWAYS_VANILLA = ("Market Treasure Chest Game",)
# Small rewards (rupees, ammo, hearts...) are all junk, so junk chests pair with junk chests whatever the exact amount.
# The remake often changed the amount, OoTR's 5-rupee chests hold red rupees for example.
MINOR_PREFIXES = ("TBox_Rupee_", "TBox_ArrowBundle_", "Item_BombBundle_", "Item_BombchuBundle_", "TBox_DekuNutBundle",
                  "Item_DekuStickBundle_", "TBox_DekuSeedBundle", "Tbox_MagicJar_", "Item_ScrubBusinessSeed")


def is_minor(actor):
    return actor is None or str(actor).startswith(MINOR_PREFIXES)


def remake_name(item):
    """The remake actor a vanilla OoTR chest item corresponds to (for comparing vanilla contents)."""
    if item in ITEM_MAP.get("match_vanilla", {}):  # where the remake's chests hold a different amount than OoT's
        return ITEM_MAP["match_vanilla"][item]
    if item in ITEM_MAP["items"]:
        return ITEM_MAP["items"][item]
    if item in PROGRESSIVE:
        return PROGRESSIVE[item]["tiers"][0]
    return ITEM_MAP["junk_for"].get(item, item)


def build():
    match = json.load(open(os.path.join(HERE, "data", "ootr_match.json"), encoding="utf-8"))["ootr_locations"]
    rewards = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))
               if r["kind"] == "chest"}
    chests = [x for x in match if x["type"] == "Chest"]
    out, used = {}, set()

    def put(x, rid, mode, why, group=None):
        out[x["ootr"]] = {"remake": rid, "mode": mode, "why": why, "vanilla": x["vanilla"]}
        if group:
            out[x["ootr"]]["group"] = group
        if rid:
            used.add(rid)

    # 1. exact matches, minigame chests
    for x in chests:
        if x["ootr"].startswith(ALWAYS_VANILLA):
            put(x, None, "vanilla", "minigame chest")
        elif x["status"] == "exact" and len(x["remake"]) == 1 and x["remake"][0] in rewards:
            put(x, x["remake"][0], "full", "exact match")
    # 2. the rest, per set of candidates, by vanilla item
    groups = defaultdict(list)
    for x in chests:
        if x["ootr"] not in out:
            groups[tuple(sorted(x["remake"]))].append(x)
    for cands, xs in groups.items():
        free = [rid for rid in cands if rid in rewards and rid not in used]
        by_r = defaultdict(list)
        for rid in free:
            by_r[rewards[rid]["item"]].append(rid)
        by_o = defaultdict(list)
        for x in xs:
            by_o[remake_name(x["vanilla"])].append(x)
        minor_o, minor_r = [], []
        for actor, os_ in by_o.items():
            rs = sorted(by_r.get(actor, []))
            if len(os_) == 1 and len(rs) == 1:
                put(os_[0], rs[0], "full", f"only {actor} chest in its area on both sides")
            elif len(os_) == len(rs) and rs:
                for x, rid in zip(sorted(os_, key=lambda x: x["ootr"]), rs):
                    put(x, rid, "group", f"{len(rs)} {actor} chests on both sides, order unknown",
                        group=f"{cands[0].split('/')[0] if cands else '?'}:{actor}")
            elif is_minor(actor):
                minor_o += os_  # paired as junk below, with the area's other small rewards
            else:
                for x in os_:
                    put(x, None, "vanilla", f"{len(os_)} OoTR vs {len(rs)} remake {actor} chests")
        for actor, rs in by_r.items():
            if is_minor(actor) and len(by_o.get(actor, [])) != len(rs):
                minor_r += [rid for rid in rs if rid not in used]
        minor_o.sort(key=lambda x: x["ootr"])
        minor_r.sort()
        for i, x in enumerate(minor_o):
            if i < len(minor_r):
                put(x, minor_r[i], "group", f"small-reward chest ({len(minor_o)} OoTR, {len(minor_r)} remake), order unknown",
                    group=f"{minor_r[0].split('/')[0]}:minor")
            else:
                put(x, None, "vanilla", f"more small-reward chests in OoTR ({len(minor_o)}) than the remake ({len(minor_r)})")
    # 3. Group the leftovers if both games have the same number of unpaired chests in the candidate set.
    #    The items may differ. If a chest was added or removed, those chests stay vanilla.
    #    TODO: check those chests one by one.
    for cands, xs in groups.items():
        os_left = sorted((x for x in xs if out[x["ootr"]]["mode"] == "vanilla"
                          and not x["vanilla"].startswith(("Small Key", "Boss Key"))), key=lambda x: x["ootr"])
        rs_left = sorted(rid for rid in cands if rid in rewards and rid not in used)
        if os_left and len(os_left) == len(rs_left):
            for x, rid in zip(os_left, rs_left):
                put(x, rid, "group", f"leftover chest ({len(rs_left)} on both sides, contents differ), order unknown",
                    group=f"{rid.split('/')[0]}:leftover")
    upgrade_same_logic(out)
    return out, rewards, used


def upgrade_same_logic(out):
    """A group whose OoTR chests all sit in the same logic region under the same rule is logically one chest repeated.
    Which pairs with which can't matter, so it doesn't need a group rule."""
    logic = json.load(open(os.path.join(HERE, "reference", "ootr", "logic.json"), encoding="utf-8"))
    rules = defaultdict(list)
    for region in logic["regions"]:
        for name, rule in (region.get("locations") or {}).items():
            rules[name].append((region["name"], rule))
    groups = defaultdict(list)
    for name, v in out.items():
        if v["mode"] == "group":
            groups[v["group"]].append(name)
    for members in groups.values():
        if len({tuple(rules.get(n, [])) for n in members}) == 1 and rules.get(members[0]):
            for n in members:
                out[n]["mode"] = "full"
                out[n]["why"] += "; same region and rule for all of them, so any pairing is right"


RECONCILE = os.path.join(HERE, "data", "rando", "reconcile.json")
# The remake has a different number of small keys (or locked doors) than OoT here, so OoTR's key logic doesn't
# describe it. Chests that hold a key on either side keep their vanilla contents.
NO_ITEM_FIELD = ("Obj_TBox_A_04",)
KEY_COUNT_DIFFERS = ("Water Temple", "Bottom of the Well", "Ganons Castle", "Gerudo Training Ground")


def apply_reconcile(out):
    """Pairs checked room by room (data/rando/reconcile.json, made from positions, rooms and room contents) override the
    item-based pairing. High and medium confidence pairs are certain, low ones stay vanilla, and OoTR chests the remake
    doesn't have are locked to their vanilla item."""
    if not os.path.exists(RECONCILE):
        return 0
    pairs = json.load(open(RECONCILE, encoding="utf-8"))["pairs"]
    actors = {r["id"]: r.get("actor") for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))}
    changed = 0
    for name, p in pairs.items():
        if name not in out or name.startswith(ALWAYS_VANILLA):
            continue  # freestanding keys and other non-chest locations, and minigame chests
        if actors.get(p["remake"]) in NO_ITEM_FIELD:
            out[name] = dict(out[name], mode="vanilla", remake=p["remake"],
                             why=f"{actors[p['remake']]} has no item setting (an ice-trap chest; untested)")
            continue
        old = (out[name]["mode"], out[name].get("remake"))
        v = {"remake": None if p["remake"] == "absent" else p["remake"], "vanilla": out[name]["vanilla"]}
        is_key = "Small Key" in p["ootr_vanilla"] or "SmallKey" in (p.get("remake_item") or "")
        if p["remake"] == "absent":
            v.update(mode="vanilla", why="the remake has no such chest (reconcile)")
        elif p["confidence"] == "low":
            v.update(mode="vanilla", why=f"low-confidence pair (reconcile): {p['evidence']}")
        elif is_key and name.startswith(KEY_COUNT_DIFFERS):
            v.update(mode="vanilla", why="key chest in a dungeon whose key count differs from OoT (reconcile)")
        else:
            v.update(mode="full", why=f"{p['confidence']} (reconcile): {p['evidence']}")
        if old != (v["mode"], v["remake"]):
            changed += 1
        out[name] = v
    # one remake chest, one OoTR chest
    owner = {}
    for name, v in out.items():
        if v["mode"] in ("full", "group") and v.get("remake"):
            if v["remake"] in owner:
                keep = owner[v["remake"]] if owner[v["remake"]] in pairs else name
                drop = name if keep == owner[v["remake"]] else owner[v["remake"]]
                out[drop] = dict(out[drop], mode="vanilla", why="its remake chest belongs to " + keep)
                owner[v["remake"]] = keep
            else:
                owner[v["remake"]] = name
    return changed


# Pairs with conflicting evidence stay vanilla until they're settled. None are left now. KF Storms Grotto Chest got
# settled by tracing its grotto entrance's DestinationAnchor link.
DISPUTED = {}


def main():
    out, rewards, used = build()
    print(f"reconcile: {apply_reconcile(out)} pairings changed")
    for name, why in DISPUTED.items():
        if name in out:
            out[name] = dict(out[name], mode="vanilla", why=f"disputed: {why}")
    used = {v["remake"] for v in out.values() if v["mode"] in ("full", "group")}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"_about": __doc__.strip().splitlines()[0], "chests": out}, open(OUT, "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    modes = defaultdict(int)
    for v in out.values():
        modes[v["mode"]] += 1
    print(f"{len(out)} OoTR chests: " + ", ".join(f"{n} {m}" for m, n in sorted(modes.items())))
    print(f"remake chests paired: {len(used)} of {len(rewards)}")
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
