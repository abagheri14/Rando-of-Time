"""Prototype that places every check the randomizer knows (data/rando/chest_map.json, data/rando/drop_map.json) on
the game's own map art and draws verification overlays.

Output: tracker/research/checks_proto.json, one record per placement:
  {"loc": OoTR location name or extras key, "kind": chest|pot|grass|rock_liftable|gs|..., "level": Banc level
   ("KokiriForest_Child", "InsideTheDekuTree"), "map": "field" | "dungeon", "texture": texture stem
   ("KokiriForest_Child_00" or "InsideTheDekuTree_B1"), "floor": "B1" | null, "px": .., "py": .. (2000x1440 map
   pixels), "hash": placement Hash (= its Bool64bitKey save flag), "has_flag": bool, "pos": [x, y, z]}

Run:  python tracker/research/build_checks.py [--overlay KokiriForest_Child_00 InsideTheDekuTree_B1 ...]
Overlays go to tracker/research/samples/overlay_<texture>.jpg (needs the decoded map, made on the fly).
"""
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mapinfo  # noqa: E402
import romtools  # noqa: E402

ROMFS = mapinfo.ROMFS
KIND_COLOURS = {"chest": (200, 60, 200), "gs": (255, 210, 0), "pot": (60, 140, 255), "flying_pot": (60, 140, 255),
                "grass": (40, 200, 40), "rock_liftable": (150, 150, 150), "rock_bombable": (110, 80, 60),
                "crate": (200, 130, 50), "beehive": (255, 160, 0), "freestanding": (255, 60, 60),
                "freestanding_rupee_heart": (255, 120, 120), "boss_heart": (255, 0, 0), "icicle": (160, 220, 255),
                "tree": (20, 120, 20), "bush": (90, 170, 60), "fairy": (255, 150, 220), "other": (0, 0, 0)}


def kind_of(entry, placement):
    t = (entry.get("type") or entry.get("category") or placement.get("category") or "").lower()
    if "gs" in t or "token" in t or "skull" in t:
        return "gs"
    for k, v in (("chest", "chest"), ("boss", "boss_heart"), ("flyingpot", "flying_pot"), ("flying_pot", "flying_pot"),
                 ("pot", "pot"), ("grass", "grass"), ("boulder", "rock_bombable"), ("rock_bombable", "rock_bombable"),
                 ("rock", "rock_liftable"), ("crate", "crate"), ("beehive", "beehive"), ("icicle", "icicle"),
                 ("redice", "icicle"), ("tree", "tree"), ("bush", "bush"), ("butterfly", "fairy"),
                 ("freestanding_rupee", "freestanding_rupee_heart"),
                 ("freestanding", "freestanding"), ("collectable", "freestanding"), ("rupeetower", "freestanding")):
        if k in t:
            return v
    return "other"


def level_of(rel):
    base = os.path.basename(rel).split(".")[0]
    for suf in ("_Static", "_Dynamic"):
        if base.endswith(suf):
            return base[:-len(suf)]
    return base


def banc_index(want):
    """{hash: [(rel, actor dict)]} for the wanted placement hashes, from every level file."""
    fs = mapinfo.fs()
    out = {}
    for p in sorted(glob.glob(os.path.join(ROMFS, "Banc", "*", "*.bcett.byml.zs"))):
        rel = os.path.relpath(p, ROMFS).replace(os.sep, "/")
        try:
            r, _ = romtools.byml_load(fs.read(rel))
        except Exception:
            continue
        for a in r.get("Actors") or []:
            h = a.get("Hash")
            if h in want:
                out.setdefault(h, []).append((rel, a))
    return out


def collect():
    """[(loc name, kind, hash)] from the chest and drop maps."""
    rows = []
    chests = json.load(open(os.path.join(ROOT, "data/rando/chest_map.json"), encoding="utf-8"))["chests"]
    # For chests left vanilla by chest_map, use the dungeon pairing in dungeons_world.json's kept_chests
    # (also used by parity/dungeons.py's _remake_of). For example, the Water Temple Compass Chest uses
    # the remake chest that chest_map's vanilla entry names for the Cracked Wall Chest.
    kept = json.load(open(os.path.join(ROOT, "data/rando/dungeons_world.json"), encoding="utf-8")).get("kept_chests") or {}
    for name, e in chests.items():
        rid = kept.get(name) if e.get("mode") not in ("full", "group") and name in kept else e.get("remake")
        if rid:
            rows.append((name, "chest", int(rid.split("/")[-1])))
    for name, rid in kept.items():
        if name not in chests:
            rows.append((name, "chest", int(rid.split("/")[-1])))
    cl = json.load(open(os.path.join(ROOT, "data/rando/chests_locations.json"), encoding="utf-8"))
    for sec in ("new", "paired"):  # paired also has the chests standing in for OoTR's Dampe race / GV crate hearts
        for name, e in (cl.get(sec) or {}).items():  # and the Treasure Chest Game reward (trap chests are in chest_map)
            if isinstance(e, dict) and e.get("remake") and (sec == "new" or not (chests.get(name) or {}).get("remake")):
                rows.append((name, "chest", int(e["remake"].split("/")[-1])))
    drops = json.load(open(os.path.join(ROOT, "data/rando/drop_map.json"), encoding="utf-8"))
    for sec in ("drops", "new", "extras", "key_spots", "scene_gifts"):
        for name, e in drops[sec].items():
            for p in e.get("placements") or []:
                rows.append((e.get("location") or name, kind_of(e, p), int(p["hash"])))
    fairies = os.path.join(ROOT, "data/rando/fairy_map.json")  # tools/rando/fairies.py has the stone, oasis or
    if os.path.exists(fairies):                                 # grotto fairy each spot stands for
        for name, s in json.load(open(fairies, encoding="utf-8"))["spots"].items():
            for p in s.get("places") or []:
                rows.append((name, "fairy", int(p["hash"])))
    return rows


def main(argv):
    mp_all = mapinfo.map_param()
    areas = mapinfo.areas()
    gdl = romtools.byml_load(mapinfo.fs().read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    flags = {e["Hash"] for e in gdl["Data"]["Bool64bitKey"]}
    rows = collect()
    idx = banc_index({h for _, _, h in rows})
    # level -> capture entry (field levels by BancName, dungeons by name)
    cap_of = {}
    for name, a in areas.items():
        for b in a["menu"]["BancName"]:
            cap_of.setdefault(b, (name, a["capture"]))
        cap_of.setdefault(name, (name, a["capture"]))
    # the game's floor for the instances its map draws (chests, Skulltulas, heart pieces), from MapParam Floor[i]
    game_floor = {}
    for lvl, mp in mp_all.items():
        for i, f in enumerate(mp.get("Floor") or []):
            for k in ("TBox", "CollectSign", "CollectHeart"):
                for e in f.get(k) or []:
                    game_floor[(lvl, e["InstanceID"])] = mapinfo.floor_name(mp, i)
    out, missing, seen = [], [], set()
    for loc, kind, h in rows:
        for rel, a in idx.get(h, []):
            level = level_of(rel)
            key = (loc, h, level)
            if key in seen:
                continue
            seen.add(key)
            base_level = level.replace("_Alternative", "")
            area_name, cap = cap_of.get(base_level, (None, None))
            x, y, z = a["Translate"]
            rec = {"loc": loc, "kind": kind, "level": level, "hash": str(h), "has_flag": h in flags,
                   "pos": [round(x, 2), round(y, 2), round(z, 2)], "actor": a.get("Gyaml")}
            if cap is None:
                rec.update(map=None, texture=None, floor=None, px=None, py=None)
                missing.append(level)
                out.append(rec)
                continue
            px, py = mapinfo.project(cap, x, z)
            mp = mp_all.get(base_level) or {}
            if mp.get("Floor"):
                room = (a.get("Dynamic") or {}).get("DefaultDungeonRoomIndex")
                fi = mapinfo.floor_of(mp, y)
                if room is not None and 0 <= room < len(mp.get("Room", [])):
                    allowed = [f - mp.get("MinFloor", 0) for f in mp["Room"][room].get("Floor", [])]
                    if allowed and fi not in allowed:
                        fi = min(allowed, key=lambda i: abs(i - fi))
                fname = game_floor.get((base_level, h)) or mapinfo.floor_name(mp, fi)
                rec.update(map="dungeon", floor=fname, room=room, texture=f"{base_level}_{fname}",
                           floor_from="game" if (base_level, h) in game_floor else "rule")
            else:
                age_tex = areas[area_name]["menu"]["TextureName"]
                tex = base_level + "_00"
                if tex not in age_tex:
                    tex = age_tex[1] if base_level.endswith("Adult") or base_level == "GanonCastle" else age_tex[0]
                rec.update(map="field", floor=None, texture=tex)
            rec.update(px=round(px, 1), py=round(py, 1))
            out.append(rec)
    entrances(out, mp_all, cap_of)
    json.dump(out, open(os.path.join(HERE, "checks_proto.json"), "w", encoding="utf-8"), indent=0)
    import collections
    placed = [r for r in out if r["texture"]]
    inside = [r for r in placed if 0 <= r["px"] < 2000 and 0 <= r["py"] < 1440]
    print(f"{len(rows)} location rows, {len(out)} placements ({len(set(r['loc'] for r in out))} locations); "
          f"on a map: {len(placed)}, inside the 2000x1440 frame: {len(inside)}; with a save flag: "
          f"{sum(r['has_flag'] for r in out)}")
    print("no map art for levels:", dict(collections.Counter(missing)))
    print("not found in any level file:", len({h for _, _, h in rows} - set(idx)))
    if "--overlay" in argv:
        for tex in argv[argv.index("--overlay") + 1:]:
            overlay(tex, [r for r in out if r["texture"] == tex])


# Room checks go to the room's entrance
# The game's own map (and Nintendo's Zelda Notes) shows what's inside a grotto, a grave, a tomb or a boss room at the
# place you go in, not where the room really is. A grotto's room lies under its hole but up to ~40 m to the side, a
# grave's lies under the graveyard, Dampe's race tunnel runs far past the map's edge, and a boss room lies off its
# floor's drawing.
# entrances() gives such a record "entrance": {"room": key shared by the room's checks, "why": what found it, "pos":
# [x, y, z] of the way in}. On a dungeon floor it also gets the doorway's "texture", "floor", "px", "py" and "toward".
# "toward" is the pixel of the drawn room behind it, and the tracker keeps the room's pins on that side of the doorway.
#
# Field levels:
#   holes       every grotto and grave is a HidingHole, with DestinationAnchor "HidingHole_FieldEntranceGo" at its
#               mouth and "HidingHole_HoleEntrance" straight below, where the player lands. A check is in a hole's
#               room when it's within HOLE_REACH m of the mouth (sideways), more than HOLE_BELOW m below it, and at
#               the landing's floor height (HOLE_FLOOR). The nearest such hole wins. I measured this on every named
#               grotto and grave check. The rooms reach 40 m out, and the closest outdoor checks that pass the
#               height test are Lake Hylia's lake bed rupees, 43 m from the lake grotto's mouth.
#   ROOM_TABLE  the rooms the level data doesn't tie to a door the map shows: a tunnel that runs far from its grave,
#               a courtyard behind a crawlspace, a cave behind a rock, a tomb behind a tombstone. The location's OoTR
#               name says which room, and the table says which actor of the level marks its way in.
# Dungeons (MapParam Room[], BossRoomId): a check in the boss room or in a room the map doesn't draw
#   (IsInvisibleMiniMap) goes to the doorway of the drawn room it's entered from. We go from the boss door
#   (Floor[].Door IsBossRoom) or the room's own Entrance points, through any undrawn rooms on the way, to the nearest
#   Entrance point of a drawn room (DOOR_REACH m sideways, DOOR_RISE m up or down). Each room lists one Entrance point
#   just inside each of its doorways, so two rooms' points meet at their shared door.
HOLE_REACH, HOLE_BELOW, HOLE_FLOOR = 42.0, 11.0, (-12.0, 8.0)
DOOR_REACH, DOOR_RISE = 10.0, 4.0
ROOM_TABLE = (
    # (level, OoTR location name pattern, room, the actor at its way in, use the mouth of the hole nearest that actor).
    # The actor is (Gyaml, Name or {Dynamic key: value}).
    ("Graveyard", r"Dampe Race", "Dampe's grave", ("Obj_Tombstone_A_02", "GraveYard_TombDampe"), True),
    ("Graveyard", r"Royal Familys Tomb", "Royal Family's Tomb",
     ("Obj_Graveyard_Tombstone_A_03", "GraveYard_Monument_00"), False),
    ("HyruleCastle", r"^HC Garden", "castle courtyard", ("DestinationAnchor", "Player_KickOutPos_Courtyard"), False),
    ("ZoraFountain", r"Hidden Cave", "hidden cave",
     ("VolumeFogArea", {"FogParams": "ZoraFountain_Cave_Entrance"}), False),
    # The minigame's rooms run west of the drawn market (the reward chest is at x -103 m), so use its shop door. That's
    # where the game's map puts its heart piece (HeartPieceAnchor MiniGame_ChoiceTreasure_IsClear, 2 m away).
    ("Market", r"Treasure Chest Game", "Treasure Chest Game",
     ("Obj_Door_ShopTreasureBox", "RestrictedDoor_Market_01"), False),
)


def _hd(a, b):
    return ((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _room_actors(levels):
    """{level: [actor]} of the actors that mark rooms' ways in (both files of each level)."""
    fs = mapinfo.fs()
    names = {"HidingHole_FieldEntranceGo", "HidingHole_HoleEntrance"}
    marks = {g for _, _, _, (g, _), _ in ROOM_TABLE}
    out = {}
    for level in levels:
        area = level.split("_")[0]
        for part in ("Static", "Dynamic"):
            rel = f"Banc/{area}/{level}_{part}.bcett.byml.zs"
            try:
                r, _ = romtools.byml_load(fs.read(rel))
            except Exception:
                continue
            out.setdefault(level, []).extend(
                a for a in r.get("Actors") or []
                if a.get("Translate") and (a.get("Name") in names or a.get("Gyaml") in marks))
    return out


def _holes(actors):
    """[(mouth, landing)] of a level's HidingHoles."""
    mouths = [a["Translate"] for a in actors if a.get("Name") == "HidingHole_FieldEntranceGo"]
    lands = [a["Translate"] for a in actors if a.get("Name") == "HidingHole_HoleEntrance"]
    out = []
    for m in mouths:
        below = [h for h in lands if _hd(m, h) < 2.0 and h[1] < m[1]]
        out.append((m, max(below, key=lambda h: h[1]) if below else [m[0], m[1] - 14.0, m[2]]))
    return out


def _table_entrance(entry, actors, holes):
    _, _, _, (gyaml, which), via_hole = entry
    for a in actors:
        if a.get("Gyaml") != gyaml:
            continue
        if isinstance(which, dict):
            dyn = a.get("Dynamic") or {}
            if any(dyn.get(k) != v for k, v in which.items()):
                continue
        elif a.get("Name") != which:
            continue
        p = a["Translate"]
        if via_hole and holes:
            p = min(holes, key=lambda h: _hd(h[0], p))[0]
        return [round(v, 2) for v in p]
    return None


def _doorway(mp, idx):
    """(drawn room, Entrance point) a dungeon room is entered from, or None."""
    rooms = mp.get("Room") or []
    boss = mp.get("BossRoomId", -1)
    undrawn = {i for i, r in enumerate(rooms) if r.get("IsInvisibleMiniMap") or i == boss}

    def ents(i):
        return [e["Trans"] for e in rooms[i].get("Entrance") or []]

    starts = []
    if idx == boss:
        starts = [d["Trans"] for f in mp.get("Floor") or [] for d in f.get("Door") or [] if d.get("IsBossRoom")]
    starts += ents(idx)
    seen = {idx}
    while starts:
        p = starts.pop(0)
        near = [(_hd(p, q), j, q) for j, r in enumerate(rooms) if j not in undrawn and r.get("CenterTrans")
                for q in ents(j) if _hd(p, q) <= DOOR_REACH and abs(p[1] - q[1]) <= DOOR_RISE]
        if near:
            _, j, q = min(near, key=lambda t: t[0])
            return j, q
        for j in sorted(undrawn - seen):  # a doorway into (or a drop from) another undrawn room, keep going through it
            r = rooms[j]
            if any(_hd(p, q) <= DOOR_REACH and abs(p[1] - q[1]) <= DOOR_RISE for q in ents(j)) or (
                    r.get("CenterTrans") and _hd(p, r["CenterTrans"]) <= 6.0):
                seen.add(j)
                starts += ents(j)
    return None


def entrances(out, mp_all, cap_of):
    """Gives the records of checks inside a room an "entrance" (see above)."""
    field = sorted({r["level"] for r in out if r.get("map") == "field"})
    actors = _room_actors(field)
    holes = {lv: _holes(actors.get(lv, [])) for lv in field}
    counts = {}
    for r in out:
        if not r.get("texture") or not r.get("pos"):
            continue
        x, y, z = r["pos"]
        ent = None
        if r["map"] == "field":
            lv = r["level"]
            for entry in ROOM_TABLE:
                if lv.split("_")[0] == entry[0] and re.search(entry[1], r["loc"]):
                    p = _table_entrance(entry, actors.get(lv, []), holes[lv])
                    if p:
                        ent = {"room": f"{entry[0]}:{entry[2]}", "why": "table", "pos": p}
                    break
            if ent is None:
                inside = [(_hd(m, r["pos"]), m) for m, h in holes[lv] if _hd(m, r["pos"]) <= HOLE_REACH
                          and y < m[1] - HOLE_BELOW and HOLE_FLOOR[0] < y - h[1] < HOLE_FLOOR[1]]
                if inside:
                    m = min(inside, key=lambda t: t[0])[1]
                    ent = {"room": f"{lv.split('_')[0]}:hole@{m[0]:.0f},{m[2]:.0f}", "why": "hole",
                           "pos": [round(v, 2) for v in m]}
        else:
            base = r["level"].replace("_Alternative", "")
            mp = mp_all.get(base) or {}
            rooms = mp.get("Room") or []
            idx = r.get("room")
            if idx is None:  # no room in its placement, so take the room whose centre is clearly nearest
                d = sorted((math.dist(r["pos"], q["CenterTrans"]), i) for i, q in enumerate(rooms)
                           if q.get("CenterTrans"))
                if d and (len(d) == 1 or d[0][0] < 0.6 * d[1][0]):
                    idx = d[0][1]
            if idx is not None and 0 <= idx < len(rooms) and (
                    idx == mp.get("BossRoomId", -1) or rooms[idx].get("IsInvisibleMiniMap")):
                found = _doorway(mp, idx)
                if found:
                    j, q = found
                    allowed = [f - mp.get("MinFloor", 0) for f in rooms[j].get("Floor", [])]
                    fi = mapinfo.floor_of(mp, q[1])
                    if allowed and fi not in allowed:
                        fi = min(allowed, key=lambda i: abs(i - fi))
                    fname = mapinfo.floor_name(mp, fi)
                    cap = cap_of[base][1]
                    px, py = mapinfo.project(cap, q[0], q[2])
                    tx, ty = mapinfo.project(cap, rooms[j]["CenterTrans"][0], rooms[j]["CenterTrans"][2])
                    ent = {"room": f"{base}:room{idx}", "why": "boss room" if idx == mp.get("BossRoomId") else
                           "undrawn room", "pos": [round(v, 2) for v in q], "texture": f"{base}_{fname}",
                           "floor": fname, "px": round(px, 1), "py": round(py, 1),
                           "toward": [round(tx, 1), round(ty, 1)]}
        if ent:
            r["entrance"] = ent
            counts[ent["why"]] = counts.get(ent["why"], 0) + 1
    rooms_n = len({r["entrance"]["room"] for r in out if "entrance" in r})
    print(f"rooms: {sum(counts.values())} placements in {rooms_n} rooms go to their entrance {counts}")


def overlay(tex, recs):
    from PIL import Image, ImageDraw
    import bntx
    sub = "Dungeon" if any(tex.endswith(f"_{f}") for f in ("B4", "B3", "B2", "B1", "1F", "2F", "3F", "4F", "5F")) \
        else "Field"
    fs = bntx.romfs()
    if sub == "Field":
        layers = [tex]
    else:
        names = sorted(os.path.basename(p).split(".")[0] for p in glob.glob(
            os.path.join(ROMFS, "UI/CustomTex/Map/Dungeon", tex + "_*")))
        main_ = [n for n in names if n.endswith("_Main")]
        layers = [n for n in names if n.endswith("_Back")] + main_[:1]
    im = Image.new("RGBA", (2000, 1440), (233, 220, 180, 255))
    for n in layers:
        t = bntx.textures(fs.read(f"UI/CustomTex/Map/{sub}/{n}.bntx.zs"))[0]
        im.alpha_composite(Image.fromarray(bntx.decode(t), "RGBA"))
    d = ImageDraw.Draw(im)
    for r in recs:
        c = KIND_COLOURS.get(r["kind"], (0, 0, 0)) + (255,)
        x, y = r["px"], r["py"]
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=c, outline=(0, 0, 0, 255), width=2)
    out = os.path.join(HERE, "samples", f"overlay_{tex}.jpg")
    im.convert("RGB").save(out, quality=88)
    print(out, len(recs), "pins")


if __name__ == "__main__":
    main(sys.argv[1:])
