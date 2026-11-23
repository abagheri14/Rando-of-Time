"""data/archipelago/ids.json: the Archipelago ids of every location and item name our generator can create.

  python tools/archipelago/build_ids.py            add new names (append-only), report what's new
  python tools/archipelago/build_ids.py --check    exit 1 if a name is missing (nothing written)

It's append-only. A name keeps its id forever and new names get the next free number at the end. Names that no
setting creates any more stay, so their id is never reused. ids = base + n with n from 1, and locations and items
are numbered separately.

Sources, every one regardless of settings (data/archipelago/CONTRACT.md):
- locations: OoTR's whole location table (MQ included), every logic file's "new_locations" (data/rando/logic),
  the extras_npcs locations (beggar, fire gorons, hat, big poes, signs, fish), the shuffled Master Sword and the
  silver rupee spots
- items: OoTR's whole item table plus the items our plugins add (story's Master Sword, extras_items' swords and bags,
  extras_npcs' Fishing Pole, extras_souls' souls and Skeleton Key) and the trap names chests writes to the spoiler.
Event, Drop and Hint locations and event items aren't checks, so they're left out.
"""
import contextlib
import io
import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IDS = os.path.join(HERE, "data", "archipelago", "ids.json")
GAME = "Rando of Time"
BASE = 0x4F54520000
NOT_CHECKS = ("Event", "Drop", "Hint", "HintStone")


def _paths():
    for p in (os.path.join(HERE, "vendor", "ootr"), os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando")):
        if p not in sys.path:
            sys.path.insert(0, p)


def _all_on():
    """A settings stand-in with every remake feature that adds names on (the plugins' own name functions read it)."""
    remake = {"remake_shuffle_beggar": True, "remake_shuffle_fire_gorons": True, "remake_shuffle_fishermans_hat": True,
              "remake_shuffle_big_poes": True, "remake_shuffle_signs": "all", "remake_fishsanity": "both",
              "remake_fishsanity_pond_count": 17, "remake_fishsanity_age_split": True,
              "remake_shuffle_boss_souls": True, "remake_shuffle_ganons_soul": True, "remake_shuffle_bean_souls": True,
              "remake_skeleton_key": True, "remake_shuffle_fishing_pole": True}
    return SimpleNamespace(remake=remake)


def names():
    """(location names, item names) any setting can create."""
    _paths()
    with contextlib.redirect_stdout(io.StringIO()):
        import LocationList
        import ItemList
        import world_settings
        from parity import _dungeons_silver, chests, extras_items, extras_npcs, extras_souls, story
    locs = {n for n, v in LocationList.location_table.items() if v[0] not in NOT_CHECKS}
    for o in world_settings.logic_overrides(None):
        for n, v in (o.get("new_locations") or {}).items():
            kind = v.get("type") if isinstance(v, dict) else (v[0] if isinstance(v, (list, tuple)) else None)
            if kind not in NOT_CHECKS:
                locs.add(n)
    on = _all_on()
    locs |= set(extras_npcs.active(on))
    locs |= {n for n in extras_npcs.SPEC["signs"]["locations"]}
    for key in ("child", "adult"):
        locs |= set(extras_npcs.SPEC["fish"]["pond"][key])
    locs.add(story.MS_LOCATION)
    locs |= {spot for _p, _n, spot, _t, _h in _dungeons_silver.spots()}
    items = {n for n, v in ItemList.item_table.items() if v[0] not in ("Event",)}
    items.add(story.MS_ITEM)
    items |= set(extras_items.SWORD_ITEMS) | set(extras_items.BAGS)
    items.add(extras_npcs.SPEC["pole"]["item"])
    items |= set(extras_souls.items(on))
    items |= set(chests.TRAP_NAMES.values())
    return locs, items


def load():
    if os.path.exists(IDS):
        return json.load(open(IDS, encoding="utf-8"))
    return {"format": 1, "game": GAME, "base": BASE, "locations": {}, "items": {}}


def extend(table, new):
    """Append the new names (sorted) after the highest id: existing ids never change."""
    added = sorted(n for n in new if n not in table)
    nxt = max(table.values(), default=BASE) + 1
    for n in added:
        table[n] = nxt
        nxt += 1
    return added


def main(argv):
    locs, items = names()
    d = load()
    if "--check" in argv:
        miss_l = sorted(locs - set(d["locations"]))
        miss_i = sorted(items - set(d["items"]))
        print(f"{len(miss_l)} locations and {len(miss_i)} items missing from {IDS}")
        return 1 if miss_l or miss_i else 0
    new_l = extend(d["locations"], locs)
    new_i = extend(d["items"], items)
    os.makedirs(os.path.dirname(IDS), exist_ok=True)
    with open(IDS, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    print(f"{IDS}: {len(d['locations'])} locations (+{len(new_l)}), {len(d['items'])} items (+{len(new_i)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
