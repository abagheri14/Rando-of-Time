"""The tracker in the game's own map: every check of the seed as an icon on its area's map (and its dungeon floor),
gone the moment you get it.

How the game's map works (reference notes: the pause map and minimap icon code): each level's icons come from
Banc/BancBasedResource/MapParam.byml.zs. A Facility icon shows while its GameDataHashName is true, and that name may
be an expression flag (BoolExp), which the game evaluates itself. So each check gets an icon whose flag is an
expression of its own, "not got yet" (and with the compass option, inside a dungeon, "and you have its compass").
Getting the check turns the expression false and the icon goes away, with nothing per check in code.

The picture is the facility's IconType. Our own icons (parity/_map_icons.py: a pot for a pot, a rupee of its colour,
a Gossip Stone, a tree, the song's own symbol...) are made from the game's art when the patch is built and shown as
new IconTypes (39 and up); a check none of them fits yet uses the map's own picture closest to it (PICTURE).

A check's "got" flag comes from the tracker data (tools/tracker/build_data.py): a named Bool (a chest's
IsTreasureBoxOpen.<hash>, a borrowed flag) or a RandoChecked bit, which an expression reads. Gold Skulltulas and
pickups whose flag is their object's own row (b64) can't be read by one, so the code patch hides those (OBJECT_MARK).
A check with no flag the game keeps (NPC gifts, shop items, silver rupees, scrubs, songs) has no icon yet.
The game makes room for 10 icons a map; the code patch (parity/_native_tracker_code.py) makes it the seed's busiest
map's count (pool_size).

  python tools/rando/native_tracker.py OUT_DIR [--compass]   report what a seed's map would get (no plan change)
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
MAPPARAM = "Banc/BancBasedResource/MapParam.byml.zs"
FACILITY_LIKE = "KokiriForest_Child.Facility"  # a vanilla facility list to type new entries like
EXP_NAME = "RandoMap_{:04d}"
# A check whose flag is its object's own row (Bool64bitKey: Gold Skulltulas, freestanding items, heart containers)
# can't be read by an expression. Its icon names RandoMapObj_Field (always on) or, with the compass option, its
# dungeon's RandoMapObj_<dungeon> (the compass), and carries OBJECT_MARK in HeartPieceHash0: the code hook
# (_native_tracker_code) hides it once the row of its InstanceID is set. Vanilla only puts heart piece hashes there.
# (It has to be Hash0: the game keeps a lone Hash1 in Hash0's place, so a mark in Hash1 was never seen.)
OBJECT_EXP = "RandoMapObj_{}"
OBJECT_MARK = 0xFFFFFFFFFFFFFFFF
ALWAYS_BOOL = "DungeonInfo.InsideTheDekuTree.IsGetCompass"  # any flag: "it or not it" is always true
# The dungeons with a compass (DungeonInfo.<area>.IsGetCompass); the others always show their checks.
COMPASS = ("InsideTheDekuTree", "DodongoCavern", "InsideJabuJabuBelly", "ForestTemple", "FireTemple", "WaterTemple",
           "ShadowTemple", "SpiritTemple", "BottomOfTheWell", "IceCavern")
# The map's own pictures, for a check none of ours fits (by kind): IconType -> a chest, a jar, a leafy flower, a bomb,
# a fairy fountain, a spider web, a red crest, a bean pod, a flute, a horseshoe, a fish, a face. A check shows our
# copy of the picture (_map_icons.game_key), never the game's own IconType: the map switches tell them apart by it,
# IconType 0 is the map's single special facility (the parser keeps one) and 35-38 run a carpenter test.
PICTURE = {"chest": 23, "pot": 16, "flying_pot": 16, "crate": 16, "beehive": 16, "icicle": 16, "other": 16,
           "grass": 33, "bush": 33, "tree": 33, "rock_liftable": 14, "rock_bombable": 14, "fairy": 11, "gs": 24,
           "freestanding": 13, "boss_heart": 13, "scrub": 34, "song": 31, "cow": 9, "fish": 28, "npc": 18, "shop": 18}
GENERIC = 18


def icon_type(rec, name):
    """The IconType of a check's icon: by its name (parity/_map_icons.py BY_NAME: a song, a fairy fountain, a trade
    item), the spot's own (tools/tracker/spots.py), ours for the object or kind, else the map's own picture for its
    kind (our copy of it)."""
    from parity import _map_icons
    icon = _map_icons.icon_for_name(name) or rec.get("icon")
    if isinstance(icon, dict):
        return _map_icons.icon_type(_map_icons.game_key(int(icon["type"]), rec.get("kind")))
    key = icon or _map_icons.icon_for(rec.get("actor"), rec.get("kind"), name)
    if key:
        return _map_icons.icon_type(key)
    return _map_icons.icon_type(_map_icons.game_key(PICTURE.get(rec.get("kind"), GENERIC), rec.get("kind")))


def _floor_number(name):
    """A floor's name as a signed number: "B2" -2, "B1" -1, "1F" 0, "2F" 1."""
    return -int(name[1:]) if name[0] == "B" else int(name[:-1]) - 1


def _floor_index(param, rec, chest_floor=None):
    """The Floor[] index a check goes on, or None on a map without floors. Its floor name less MinFloor (that matches
    every vanilla chest's list); a dungeon whose map research has no floors (Gerudo Training Ground, Ganon's Castle)
    goes by the vanilla chest list (chest_floor) or the floor heights (TransY, a floor starts a bit below it)."""
    floors = param.get("Floor") or []
    if not floors:
        return None
    if rec.get("floor_index") is not None:  # a spot that knows its floor (tools/tracker/spots.py: a boss door)
        i = int(rec["floor_index"])
    elif rec.get("floor"):
        i = _floor_number(rec["floor"]) - int(param.get("MinFloor", 0))
    elif chest_floor is not None:
        i = chest_floor
    else:
        y = float(rec["pos"][1])
        i = max([n for n, f in enumerate(floors) if y >= float(f["TransY"]) - 3] or [0])
    return min(max(i, 0), len(floors) - 1)


def _got_steps(flags):
    """Expression steps that are true once the check is got, or None when its flags can't all be read by an
    expression (a per-object row, b64)."""
    parts = []
    for f in flags or []:
        if f.get("t") == "bool":
            parts.append([[0, f["n"]]])
        elif f.get("t") == "nbool":  # got once it's false (a special deal's in-stock flag)
            parts.append([[0, f["n"]], [5]])
        elif f.get("t") == "bit":
            parts.append([[8, f["a"], int(f["i"])]])
        elif f.get("t") == "count":  # a counter in bits (low bit first) at least "min" (the Mask Shop's slots)
            parts.append(_count_at_least(f["bits"], int(f["min"])))
        else:
            return None
    if not parts:
        return None
    out = list(parts[0])
    for p in parts[1:]:
        out += p + [[4]]  # any of them (OR)
    return out


def _count_at_least(bits, m):
    """Expression steps true while the number in `bits` (saved Bools, low bit first) is at least m (m >= 1): from the
    top bit down, a bit m has must be set and the rest at least m's rest, a bit m lacks set is enough on its own."""
    def ge(i, m):
        bit, rest = (m >> i) & 1, m & ((1 << i) - 1)
        if i == 0 or rest == 0:
            here = [[0, bits[i]]]
            if bit:
                return here
            return here + ge(i - 1, rest) + [[4]] if rest else here  # (a 0 bit with nothing below: never)
        return [[0, bits[i]]] + ge(i - 1, rest) + [[3] if bit else [4]]
    top = len(bits) - 1
    if m >= (1 << len(bits)) or m < 1:
        raise ValueError(f"count at least {m} doesn't fit {len(bits)} bits")
    return ge(top, m)


# Got flags. A check given by a scene step (NPC gifts, songs, bosses, minigames...) keeps no record of its own, so the
# map couldn't tell it's got. Each of those gets a new saved Bool of ours (make_patch gamedata "add_bools", false on a
# new file, like the minted flags of free_flags.py) and the reward's "got": make_patch puts a step setting it just
# before the give (got_ops, or first in the call / tier steps that replace it). The trackers read it like any flag.
GOT_PREFIX = "RandoGot_"


def got_name(location):
    """The got flag of an OoTR location: RandoGot_ and its words run together ("Kak Anju as Adult" ->
    RandoGot_KakAnjuAsAdult)."""
    return GOT_PREFIX + "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", location))


def _got_node(flag, nxt):
    """A new step setting saved Bool `flag`, then `nxt` (make_patch.got_node in a plugin's own graph)."""
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "new_actor": True,
            "params": {"GameDataName": flag, "Value": True, "Index": -1}, "next": nxt}


def _got_before(plan, op, label, flag):
    """In a plugin's new graph (a plan "add_graph" op), sets `flag` just before node `label`: every way into it goes
    through the new step first, from the graph's own steps, its start and the plan's routes to its event."""
    new = f"got_{label}"
    for lab, nd in op["nodes"].items():
        if nd.get("next") == label:
            nd["next"] = new
        for k, v in list((nd.get("cases") or {}).items()):
            if v == label:
                nd["cases"][k] = new
        if nd.get("fork"):
            nd["fork"] = [new if x == label else x for x in nd["fork"]]
    if op.get("start") == label:
        op["start"] = new
    old_ev, new_ev = f"{op['add_graph']}_{label}", f"{op['add_graph']}_{new}"
    for o2 in plan.get("events") or []:
        if o2.get("file") == op["file"] and o2.get("flowchart") == op["flowchart"] and o2.get("next") == old_ev:
            o2["next"] = new_ev
    op["nodes"][new] = _got_node(flag, label)


def _graph_gives(plan):
    """[(location, graph op, give label)] for the gives in plugins' own graphs that keep no record: the silver-rupee
    spots' scene (a branch per token), the frogs' song rewards and the hideout jail keys (a graph per guard)."""
    from parity import _dungeons_silver as silver, dungeons, songs_trade
    import shops
    shop_locs = shops.shop_map()["locations"]
    spots = (((plan.get("_gaps") or {}).get("silver_rupees") or {}).get("spots")) or {}
    jail = {v["entry_event"]: n for n, v in dungeons.HIDEOUT.items()}
    out = []
    for op in plan.get("events") or []:
        g, nodes = op.get("add_graph"), op.get("nodes") or {}
        if g == silver.DATA["scene_entry"] and op.get("file") == silver.DATA["scene_file"]:
            for lab, nd in nodes.items():
                if re.fullmatch(r"q\d+", lab) and f"give{lab[1:]}" in nodes:
                    loc = (spots.get((nd.get("params") or {}).get("Value")) or {}).get("location")
                    if loc:
                        out.append((loc, op, f"give{lab[1:]}"))
        elif g == "RandoST_FrogSongs":
            out += [(loc, op, f"give{t}") for loc, t in songs_trade.FROG_SONGS.items() if f"give{t}" in nodes]
        elif g and g.startswith("Rando_Hideout_") and op.get("file") == dungeons.RESCUE and "give" in nodes:
            loc = jail.get(g[len("Rando_Hideout_"):])
            if loc:
                out.append((loc, op, "give"))
        elif g == "Rando_ScrubsConverted":  # a scrub without a sold flag: after its sale (_got_after_sale)
            keyed = {(e.get("edit") or {}).get("key"): n for n, e in shop_locs.items() if e.get("kind") == "scrub"}
            for lab, nd in nodes.items():
                m = re.fullmatch(r"key(\d+)", lab)
                loc = keyed.get((nd.get("params") or {}).get("Value")) if m else None
                if loc and f"sold{m.group(1)}" not in nodes:
                    out += [(loc, op, ("after_sale", x)) for x in nodes
                            if re.fullmatch(rf"(sell{m.group(1)}|sale{m.group(1)}_\d+)", x) and nodes[x].get("next") is None]
    return out


def _got_after_sale(op, label, flag):
    """In a scrub's sale graph, sets `flag` after sale step `label` when the sale went through (the game's
    ScrubBusiness_BuySuccess, as the graph's own sold flags are set)."""
    q, setter = f"got_q_{label}", f"got_{label}"
    op["nodes"][label]["next"] = q
    op["nodes"][q] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                      "params": {"GameDataName": "ScrubBusiness_BuySuccess", "Index": -1},
                      "cases": {"0": setter, "1": None}}
    op["nodes"][setter] = dict(_got_node(flag, None))


def add_got_flags(out_dir):
    """Gives every check of the seed that a scene step gives, and that has no flag in tracker.json, a got flag:
    the reward's "got" (or a step in the plugin's own graph, _graph_gives), the flag's save row and plan
    "_got_flags" (read by tools/tracker/build_data.py, so run build_data.seed again after). Returns
    {location: flag}."""
    p = os.path.join(out_dir, "plan.json")
    plan = json.load(open(p, encoding="utf-8"))
    tracker = json.load(open(os.path.join(out_dir, "tracker.json"), encoding="utf-8"))
    flagless = {c["name"] for c in tracker["checks"] if not c.get("flags")} - set(plan.get("_got_flags") or {})
    got = {}
    for rid, spec in sorted(plan.get("rewards", {}).items()):
        note = spec.get("note") if isinstance(spec, dict) else None
        loc = (note or "").split(":")[0]
        if not rid.startswith("event/") or loc not in flagless:
            continue
        got[loc] = got_name(loc)
        plan["rewards"][rid] = dict(spec, got=got[loc])
    for loc, op, label in _graph_gives(plan):
        if loc in flagless:
            got[loc] = got_name(loc)
            if isinstance(label, tuple):
                _got_after_sale(op, label[1], got[loc])
            else:
                _got_before(plan, op, label, got[loc])
    if len(set(got.values())) != len(got):
        raise RuntimeError("remake_native_tracker: two checks would share a got flag")
    if got:
        old = plan.get("gamedata")
        plan["gamedata"] = ([] if old is None else [old] if isinstance(old, dict) else list(old)) + [
            {"add_bools": {f: False for f in sorted(got.values())}}]
        plan["_got_flags"] = dict(plan.get("_got_flags") or {}, **{n: {"t": "bool", "n": f} for n, f in got.items()})
        plan["_native_tracker_got"] = got
        json.dump(plan, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return got


def verify_got(patch, plan, romfs=None):
    """[problem, ...] for the got flags (plan "_native_tracker_got"): each one is set by a step of a patched scene
    file that an entry point reaches, and its save row exists."""
    import romtools
    from evfl import Evfl
    want = set((plan.get("_native_tracker_got") or {}).values())
    if not want:
        return []
    zs = romtools.Romfs(romfs or romtools.longshot_romfs(), os.path.join(HERE, "original")).zs
    found = set()
    d = os.path.join(patch, "Event", "EventFlow")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        ev = Evfl(zs.decompress(open(os.path.join(d, f), "rb").read()))
        for fc in ev.flowcharts:
            starts = [ep["main"] for ep in fc["entry_points"].values()]
            seen, todo = set(), list(starts)
            while todo:
                i = todo.pop()
                if i is None or i in seen or i >= len(fc["events"]):
                    continue
                seen.add(i)
                e = fc["events"][i]
                todo += [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])] + \
                    list(e.get("forks", []))
            for i in seen:
                e = fc["events"][i]
                if e["type"] != "action":
                    continue
                a = fc["actors"][e["actor"]]
                if a["name"] != "GameDataActor" or a["actions"][e["action"]] != "EventTriggerSetGameDataBool":
                    continue
                name = (((e.get("params") or {}).get("items") or {}).get("GameDataName") or {}).get("value")
                if name in want:
                    found.add(name)
    bad = [f"got flag {f}: no reachable step sets it in the patched scenes" for f in sorted(want - found)]
    added = {k for op in (plan.get("gamedata") or []) if isinstance(op, dict) for k in (op.get("add_bools") or {})}
    bad += [f"got flag {f}: no save row added" for f in sorted(want - added)]
    return bad


def _object_keys(flags):
    """The per-object rows (Bool64bitKey hashes) of a check whose flags are all of that kind, else None."""
    keys = [int(f["h"]) for f in flags or [] if f.get("t") == "b64"]
    return keys if keys and len(keys) == len(flags) else None


def _chest_floors(mapparam):
    """{chest placement hash: Floor[] index} from the vanilla chest lists (TBox) of every dungeon floor."""
    out = {}
    for level, param in mapparam.items():
        for i, fl in enumerate(param.get("Floor") or []):
            for t in fl.get("TBox") or []:
                out[(level, int(t["InstanceID"]))] = i
    return out


# Maps inside another area's level: the game shows Lake Hylia and Lon Lon Ranch on maps of their own, though their
# objects are placed in Hyrule Field's level (the map research's own "also" rule, tools/tracker/build_data.py).
SUB_MAPS = {"HyruleField": ("LakeHylia", "LonLonRanch")}
_cams = {}  # field map level -> (capture camera, map art texture)
_masks = {}
MASK_CACHE = os.path.join(HERE, "cache", "map_masks")
MASK_STEP = 4    # one texture block in every MASK_STEP x MASK_STEP tells whether that patch of the map art is drawn
MASK_ALPHA = 200  # this opaque is the drawing itself (the soft glow round it and its faded borders are less)
EDGE_CELLS = 1   # a spot this many mask cells from the drawing still counts as on it
SAME_PX = 6      # icons this close on one map (map pixels, 2000 wide) are on one spot
ICON_GAP = 44    # how far apart icons end up (an icon is about 60 pixels: they touch, none hides another)
PUSH_ROUNDS = 120


def _mapinfo():
    sys.path.insert(0, os.path.join(HERE, "tracker", "research"))
    import mapinfo
    if not _cams:
        for a_ in mapinfo.areas().values():
            if not a_["capture"].get("IsDungeon"):
                for b, t in zip(a_["menu"].get("BancName") or [], a_["menu"].get("TextureName") or []):
                    # a level on two places' maps (Ganon's Castle: Hyrule Castle's adult map and its own) goes by
                    # the camera of the place named like it, the one its map art was drawn with
                    if b and t and (b not in _cams or a_["menu"].get("LocationName") == b.split("_")[0]):
                        _cams[b] = (a_["capture"], t)
    return mapinfo


def _mask(tex):
    """The drawn part of a field map's art: (cell size in pixels, rows of 0/1), from the alpha of one texture block in
    every MASK_STEP x MASK_STEP (the art is transparent around the drawing). Made from the game's files the first time
    and kept in cache/map_masks, named by the file's bytes. None if the art can't be read."""
    if tex in _masks:
        return _masks[tex]
    import hashlib
    import romtools
    fs = romtools.Romfs(romtools.longshot_romfs(), os.path.join(HERE, "original"))
    rel = f"UI/CustomTex/Map/Field/{tex}.bntx.zs"
    try:
        raw = fs.raw(rel)
    except (OSError, KeyError):
        _masks[tex] = None
        return None
    path = os.path.join(MASK_CACHE, f"{tex}-{hashlib.sha1(raw).hexdigest()[:16]}-a{MASK_ALPHA}.json")
    if os.path.exists(path):
        m = json.load(open(path, encoding="utf-8"))
        _masks[tex] = (m["cell"], m["rows"])
        return _masks[tex]
    sys.path.insert(0, os.path.join(HERE, "tracker", "research"))
    sys.path.insert(0, os.path.join(HERE, "tools", "rando", "parity"))
    import numpy as np
    import bntx
    t = bntx.textures(fs.zs.decompress(raw))[0]
    blocks, (bw, bh) = bntx.deswizzle(t)
    sub = blocks[::MASK_STEP, ::MASK_STEP]
    if 0x2D <= t["fmt"] <= 0x3A:  # ASTC: decode just the sampled blocks
        import _astc
        flat = sub.reshape(-1, sub.shape[2])
        cache = {}
        tiles = []
        for blk in flat:
            k = blk.tobytes()
            if k not in cache:
                cache[k] = np.array(_astc.decode_block(k, bw, bh), np.uint8).reshape(bh, bw, 4)
            tiles.append(cache[k])
        img = np.stack(tiles).reshape(sub.shape[0], sub.shape[1], bh, bw, 4).transpose(0, 2, 1, 3, 4)
        img = bntx._apply_comp(img.reshape(sub.shape[0] * bh, sub.shape[1] * bw, 4), t["comp"])
        alpha = img[..., 3].reshape(sub.shape[0], bh, sub.shape[1], bw).max(axis=(1, 3))
    else:  # anything else: the whole picture, then the same cells
        img = bntx.decode(t)
        cell = MASK_STEP * bw
        hh, ww = img.shape[0] // cell, img.shape[1] // cell
        alpha = img[:hh * cell, :ww * cell, 3].reshape(hh, cell, ww, cell).max(axis=(1, 3))
    rows = ["".join("1" if v >= MASK_ALPHA else "0" for v in row) for row in alpha]
    os.makedirs(MASK_CACHE, exist_ok=True)
    json.dump({"tex": tex, "cell": MASK_STEP * bw, "rows": rows}, open(path, "w", encoding="utf-8"))
    _masks[tex] = (MASK_STEP * bw, rows)
    return _masks[tex]


def _drawn(tex, px, py, reach=EDGE_CELLS):
    """True if the map's drawing covers (px, py) or comes within `reach` cells of it (True without a mask)."""
    m = _mask(tex)
    if m is None:
        return True
    cell, rows = m
    cx, cy = int(px // cell), int(py // cell)
    for y in range(cy - reach, cy + reach + 1):
        for x in range(cx - reach, cx + reach + 1):
            if 0 <= y < len(rows) and 0 <= x < len(rows[y]) and rows[y][x] == "1":
                return True
    return False


def _grid(tex):
    """(cell size, drawn cells, cells well inside the drawing: drawn with all four neighbours drawn) as numpy arrays
    [row][column], or None without a mask."""
    import numpy as np
    m = _mask(tex)
    if m is None:
        return None
    cell, rows = m
    on = np.array([[c == "1" for c in r] for r in rows], dtype=bool)
    inner = on.copy()
    inner[1:] &= on[:-1]
    inner[:-1] &= on[1:]
    inner[:, 1:] &= on[:, :-1]
    inner[:, :-1] &= on[:, 1:]
    return cell, on, inner if inner.any() else on


def sub_maps(rec, mapparam):
    """The map levels a record shows on: its own, or for a level with sub-maps every one of them (and its own) whose
    drawing holds its spot (the map camera's projection, tracker/research/mapinfo.py, and the map art's drawn part,
    _mask). Its own when none does."""
    base, _, age = rec["level"].partition("_")
    if base not in SUB_MAPS or not rec.get("pos"):
        return [rec["level"]]
    mi = _mapinfo()
    out = []
    for banc in [rec["level"]] + [f"{x}_{age}" for x in SUB_MAPS[base]]:
        if banc in _cams and banc in mapparam and banc not in out:
            cap, tex = _cams[banc]
            px, py = mi.project(cap, rec["pos"][0], rec["pos"][2])
            if 0 <= px <= mi.TEX_W and 0 <= py <= mi.TEX_H and _drawn(tex, px, py):
                out.append(banc)
    return out or [rec["level"]]


def _slots(n, gap):
    """Offsets for n icons round one spot: a ring for a few, else one in the middle and rings of 6, 12, 18... (packed
    like coins), each `gap` apart."""
    import math
    if n == 1:
        return [(0.0, 0.0)]
    if n <= 7:
        r = max(gap * 0.75, gap * n / (2 * math.pi))
        return [(r * math.cos(2 * math.pi * k / n - math.pi / 2), r * math.sin(2 * math.pi * k / n - math.pi / 2))
                for k in range(n)]
    out, ring = [(0.0, 0.0)], 1
    while len(out) < n:
        take = min(6 * ring, n - len(out))
        r = gap * ring * 0.9
        out += [(r * math.cos(2 * math.pi * k / take - math.pi / 2), r * math.sin(2 * math.pi * k / take - math.pi / 2))
                for k in range(take)]
        ring += 1
    return out


def arrange(level, values):
    """On a field map: icons on one spot (a grotto's, a room's, a shop's) go round it (_slots), then icons that still
    cover each other are pushed apart a little at a time until they're ICON_GAP apart, so each check shows and every
    icon stays near its own spot. An icon off the map's drawing (an NPC past the drawn edge, the Temple of Time's door)
    moves to the nearest spot well inside it, every round, so the push never leaves one outside. Changes each entry's
    Trans (x and z; y stays)."""
    import numpy as np
    mi = _mapinfo()
    if level not in _cams or not values:
        return
    cap, tex = _cams[level]
    scale = mi.TEX_W / cap["Height"]
    cx0, cz0 = cap.get("CameraPos", {}).get("X", 0.0), cap.get("CameraPos", {}).get("Z", 0.0)
    pts = np.array([mi.project(cap, v["Trans"][0], v["Trans"][2]) for v in values], dtype=np.float64)
    spots = {}
    for i, (px, py) in enumerate(pts):
        spots.setdefault((round(px / SAME_PX), round(py / SAME_PX)), []).append(i)
    for g in spots.values():
        if len(g) > 1:
            mx, my = pts[g].mean(axis=0)
            pts[g] = np.array([mx, my]) + np.array(_slots(len(g), ICON_GAP))
    grid = _grid(tex)
    if grid is not None:
        cell, on, inner = grid
        targets = (np.argwhere(inner)[:, ::-1] + 0.5) * cell  # (x, y) of each inner cell's middle

    def pull():
        if grid is None:
            return 0
        ix, iy = np.floor(pts[:, 0] / cell).astype(int), np.floor(pts[:, 1] / cell).astype(int)
        ok = (ix >= 0) & (iy >= 0) & (ix < on.shape[1]) & (iy < on.shape[0])
        ok[ok] = on[iy[ok], ix[ok]]
        off = np.flatnonzero(~ok)
        for i in off:
            pts[i] = targets[((targets - pts[i]) ** 2).sum(axis=1).argmin()]
        return len(off)
    # icons pulled to one spot separate along a direction of their own (golden angle steps), the same every build
    turn = np.arange(len(pts)) * 2.399963
    way = np.stack([np.cos(turn), np.sin(turn)], axis=1)
    for _ in range(PUSH_ROUNDS):
        pulled = pull()
        d = pts[:, None, :] - pts[None, :, :]
        dist = np.sqrt((d ** 2).sum(-1))
        same = dist < 1e-6
        d = np.where(same[..., None], way[:, None, :] - way[None, :, :], d)
        np.fill_diagonal(dist, np.inf)
        close = dist < ICON_GAP * 0.98
        if not close.any():
            if not pulled:
                break
            continue
        norm = np.sqrt((d ** 2).sum(-1))
        norm = np.where(norm == 0, 1.0, norm)
        push = np.where(close, (ICON_GAP - dist) / 2, 0.0)[..., None] * d / norm[..., None]
        pts += push.sum(axis=1) * 0.5
    pull()
    for v, (px, py) in zip(values, pts):
        v["Trans"] = [round(cx0 + (px - mi.TEX_W / 2) / scale, 3), v["Trans"][1],
                      round(cz0 + (py - mi.TEX_H / 2) / scale, 3)]


def _always(any_bool):
    """Steps of an expression that's always true (a flag or not that flag)."""
    return [[0, any_bool], [0, any_bool], [5], [4]]


def plan_sections(out_dir, compass=False, mapparam=None):
    """(byml ops, add_boolexp dict, report, {list path: entries}, {level: icons}) for a generated seed's map icons."""
    import romtools
    tracker = json.load(open(os.path.join(out_dir, "tracker.json"), encoding="utf-8"))
    proto = json.load(open(os.path.join(HERE, "tracker", "research", "checks_proto.json"), encoding="utf-8"))
    if mapparam is None:
        fs = romtools.Romfs(romtools.longshot_romfs(), os.path.join(HERE, "original"))
        mapparam = romtools.byml_load(fs.read(MAPPARAM), allow_big=True)[0]
    sys.path.insert(0, os.path.join(HERE, "tools", "tracker"))
    import build_data  # the outside tracker's records: the same spots and names
    recs = build_data.location_records(proto)
    for name, rows in build_data._cow_records(proto)[0].items():
        recs.setdefault(name, rows)
    # checks the map research has no spot for (NPC gifts, shops, scrubs, songs, bosses, silver rupees...) get one from
    # the game's own placements and map icons (tools/tracker/spots.py)
    import romtools
    import spots
    plan = json.load(open(os.path.join(out_dir, "plan.json"), encoding="utf-8"))
    bare = {c["name"] for c in tracker["checks"]
            if not any(r.get("level") in mapparam and r.get("pos") for r in recs.get(c["name"], []))}
    fs = romtools.Romfs(romtools.longshot_romfs(), os.path.join(HERE, "original"))
    for name, rows in spots.records(fs, plan, bare, proto).items():
        recs[name] = rows
    chest_floor = _chest_floors(mapparam)
    sp = os.path.join(out_dir, "spoiler.json")
    placed_items = json.load(open(sp, encoding="utf-8")).get("locations", {}) if os.path.exists(sp) else {}
    entries, exps = collections.defaultdict(list), {}
    report, per_level = collections.Counter(), collections.Counter()
    for n, c in enumerate(tracker["checks"]):
        item = placed_items.get(c["name"])
        item = item.get("item") if isinstance(item, dict) else item
        if str(item or "").startswith("Buy "):  # a shop's own stock (OoTR's "Buy ..." items): sold any time, no check
            report["shop stock, no check"] += 1
            continue
        got, keys = _got_steps(c.get("flags")), _object_keys(c.get("flags"))
        if got is None and keys is None:
            report["no flag yet (" + (c.get("kind") or "?") + ")"] += 1
            continue
        placed = [r for r in recs.get(c["name"], []) if r.get("level") in mapparam and r.get("pos")]
        if keys:  # each of its spots is the object whose row it is
            placed = [r for r in placed if int(r["hash"]) in keys]
        # Hyrule Field's level holds Lake Hylia's and Lon Lon Ranch's maps too: a check goes on every map whose
        # drawing holds it (sub_maps)
        placed = [dict(r, level=m) for r in placed for m in sub_maps(r, mapparam)]
        # Kakariko's and Zora's Domain's second map (_Alternative) shows the same checks
        placed += [dict(r, level=r["level"] + "_Alternative") for r in placed
                   if r["level"] + "_Alternative" in mapparam]
        if not placed:
            report["no spot on a map (" + (c.get("kind") or "?") + ")"] += 1
            continue
        gate = [[0, f"DungeonInfo.{placed[0]['level']}.IsGetCompass"]] if compass and placed[0]["level"] in COMPASS \
            else []
        if got is not None:
            name = EXP_NAME.format(n)
            exps[name] = got + [[5]] + (gate + [[3]] if gate else [])  # not got (and the compass)
        else:  # the code hook hides it once its object's row is set (OBJECT_MARK)
            name = OBJECT_EXP.format(placed[0]["level"] if gate else "Field")
            exps[name] = gate[:1] if gate else _always(ALWAYS_BOOL)
        for r in placed:
            param = mapparam[r["level"]]
            fi = _floor_index(param, r, chest_floor.get((r["level"], int(r["hash"]))))
            path = f"{r['level']}.Floor.{fi}.Facility" if fi is not None else f"{r['level']}.Facility"
            # a field map shows a grotto's or a grave's check at its way in, like the outside tracker
            way = (r.get("entrance") or {}).get("pos") if fi is None else None
            entries[path].append({"GameDataHashName": name, "IconType": icon_type(r, c["name"]),
                                  "HeartPieceHash0": OBJECT_MARK if got is None else 0, "HeartPieceHash1": 0,
                                  "InstanceID": int(r["hash"]), "Trans": [float(x) for x in (way or r["pos"])]})
            per_level[r["level"]] += 1
            report["icons"] += 1
    for path, values in entries.items():  # field maps: spread shared spots, keep every icon on the drawing
        if ".Floor." not in path:
            arrange(path.split(".")[0], values)
    ops = [{"file": MAPPARAM, "note": "native tracker",
            "add_entries": {p: {"like": FACILITY_LIKE, "values": v} for p, v in sorted(entries.items())}}]
    return ops, exps, report, entries, per_level


def pool_size(mapparam, per_level):
    """Icons the busiest map needs: its vanilla facilities plus ours, rounded up to 8 (the game makes 10)."""
    def vanilla(param):
        return len(param.get("Facility") or []) + sum(len(f.get("Facility") or []) for f in param.get("Floor") or [])
    need = max([vanilla(mapparam[lv]) + n for lv, n in per_level.items()] or [0])
    return max(10, -(-need // 8) * 8)


def add_to_plan(out_dir, mode):
    """Adds the map icons (MapParam), their expression flags and the code patch to out_dir/plan.json. mode "on" or
    "compass" (a dungeon's checks show once you have its compass). Needs the seed's tracker.json."""
    import romtools
    from parity import _native_tracker_code as code
    bad = code.check_here()
    if bad:
        raise RuntimeError("remake_native_tracker: the code patch doesn't fit this game: " + "; ".join(bad[:3]))
    fs = romtools.Romfs(romtools.longshot_romfs(), os.path.join(HERE, "original"))
    mapparam = romtools.byml_load(fs.read(MAPPARAM), allow_big=True)[0]
    ops, exps, report, entries, per_level = plan_sections(out_dir, compass=mode == "compass", mapparam=mapparam)
    n = pool_size(mapparam, per_level)
    p = os.path.join(out_dir, "plan.json")
    plan = json.load(open(p, encoding="utf-8"))
    plan["byml"] = plan.get("byml", []) + ops
    old = plan.get("gamedata")
    plan["gamedata"] = ([] if old is None else [old] if isinstance(old, dict) else list(old)) + [
        {"add_boolexp": exps}]
    plan["exefs"] = plan.get("exefs", []) + [{"file": code.PATCH_FILE, "text": code.pchtxt(n)}]
    # the map switches: hide a kind of icon from Longshot's Insert menu (the Mods tab), while playing
    plan["cheats"] = plan.get("cheats", []) + [{"file": code.CHEATS_FILE, "text": code.cheats()}]
    from parity import _map_icons  # our icons, made from the game's art when the patch is built
    cos = plan.setdefault("cosmetics", {})
    cos["map_icons"] = list(_map_icons.KEYS)
    plan["_native_tracker"] = {"mode": mode, "pool": n, "lists": {k: len(v) for k, v in entries.items()},
                               "expressions": len(exps), "left_out": {k: v for k, v in report.items() if k != "icons"}}
    plan["_verify_plugins"] = sorted(set(plan.get("_verify_plugins") or []) | {"_native_tracker_code"})
    notes = plan.setdefault("_notes_native_tracker", [])
    notes.append(f"remake_native_tracker {mode}: {report['icons']} icons on {len(per_level)} maps, up to {n} on one; "
                 f"the code patch (exefs) needs the game built again in Longshot")
    json.dump(plan, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return plan["_native_tracker"]


if __name__ == "__main__":
    out = sys.argv[1]
    ops, exps, report, entries, per_level = plan_sections(out, compass="--compass" in sys.argv)
    print(dict(report))
    print("maps:", len(per_level), "expressions:", len(exps))
    print("busiest:", per_level.most_common(15))
