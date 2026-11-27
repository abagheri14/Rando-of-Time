"""Map spots for the checks the map research has none for: NPC gifts, shop slots, scrubs, songs, bosses, Big Poes,
fish and the silver rupee spots. Both trackers use them (tools/tracker/build_data.py for the outside one,
rando/native_tracker.py for the game's own map), so a check sits where you get it.

Where each one comes from (all read from the player's game files when the seed is made):
  facility  next to the map's own icon for the place: the shop, the minigame, the Great Fairy's fountain, the
            Skulltula House, the frogs... (MapParam Facility of that IconType on the area's map)
  actor     at an object of the level: the NPC who gives it (Anju, King Zora, Biggoron...), Sheik's warp pad for
            the song he teaches there, the Ocarina of Time in the moat, the Temple of Time's door
  boss      at the boss room's door on its dungeon's map (MapParam Floor Door IsBossRoom)
  scrub     at the scrub (the shop map's placements), a grotto's at the grotto's way in
  silver    at the spot's silver rupee (the dungeons plugin's tokens, plan "_gaps" silver_rupees)
  poe/fish  at the Big Poe of its fence number, the Zora's Domain fish of its number
Each spot also names its icon (parity/_map_icons.py key, or "type" for one of the map's own pictures).
"""
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
MAPPARAM = "Banc/BancBasedResource/MapParam.byml.zs"

# (name pattern, the facility's IconType, the icon). The icon is ours (a key) or a map picture ("type": n).
FACILITY = (
    (r"Great Fairy Reward$", 11, {"type": 11}),
    (r"Gold Skulltula Reward$", 24, "gs"),
    (r"Fishing$|Pond (Fish|Loach)", 28, "fish"),
    (r"^Market Bombchu Bowling", 22, {"type": 22}),
    (r"^Market Shooting Gallery", 20, {"type": 20}),
    (r"^Kak Shooting Gallery", 21, {"type": 21}),
    (r"^Market Treasure Chest Game", 23, "chest"),
    (r"^Market 10 Big Poes", 30, "big_poe"),
    (r"^Market Mask Shop", 1, {"type": 1}),
    (r"^Market Potion Shop", 16, {"type": 16}),
    (r"^Market Bazaar", 18, {"type": 18}),
    (r"^Market Bombchu Shop", 4, {"type": 4}),
    (r"^Kak Bazaar", 19, {"type": 19}),
    (r"^Kak Potion Shop", 17, {"type": 17}),
    (r"^Kak Granny", 29, {"type": 29}),
    (r"^GC Shop", 14, {"type": 14}),
    (r"^KF Shop", 13, {"type": 13}),
    (r"^ZD Shop", 15, {"type": 15}),
    (r"^ZD Diving", 27, {"type": 27}),
    (r"^ZR Frogs (in the Rain|Ocarina Game)", 6, {"type": 6}),
    (r"^ZR Frogs Zeldas Lullaby", 6, "song_zelda"),
    (r"^ZR Frogs Eponas Song", 6, "song_epona"),
    (r"^ZR Frogs Sarias Song", 6, "song_saria"),
    (r"^ZR Frogs Suns Song", 6, "song_sun"),
    (r"^ZR Frogs Song of Time", 6, "song_time"),
    (r"^ZR Magic Bean Salesman", 34, "bean"),
    (r"^LW (Skull Kid|Ocarina Memory Game)", 31, {"type": 31}),
    (r"^Deku Theater", 33, {"type": 33}),
    (r"^LLR Talons Chickens", 8, "cucco"),
    (r"^Graveyard Dampe Gravedigging", 26, {"type": 26}),
    (r"^GF HBA", 7, {"type": 7}),
    (r"^Hideout 1 Torch Jail", 35, "key"),
    (r"^Hideout 2 Torches Jail", 36, "key"),
    (r"^Hideout 3 Torches Jail", 37, "key"),
    (r"^Hideout 4 Torches Jail", 38, "key"),
    (r"^Hideout Gerudo Membership Card", 38, {"type": 3}),  # (types 35-38 run the map's carpenter check)
)
# A Great Fairy's fountain icon is on six places' maps: each reward goes only on its own place's (the name's first word)
FAIRY_PLACE = {"HC": "HyruleCastle", "OGC": "GanonCastle", "DMT": "DeathMountainTrail", "DMC": "DeathMountainCrater",
               "ZF": "ZoraFountain", "Colossus": "DesertColossus"}
# name -> (level, actor Gyaml, icon). A level's base name (no age) means every age's map that has it.
ACTOR = {
    "Song from Saria": ("SacredForestMeadow_Child", "Npc_Kokiri_Saria_Child_SacredForestMeadow", "song_saria"),
    "Sheik in Forest": ("SacredForestMeadow_Adult", "Obj_WarpPoint_A_02", "song_minuet"),
    "Song from Malon": ("HyruleField_Child", "Npc_Hylia_Malon_Child", "song_epona"),
    "Song from Impa": ("HyruleCastle", "Npc_Hylia_Impa_Child", "song_zelda"),
    "Song from Windmill": ("KakarikoVillage_Adult", "OcarinaPoint_Kakariko_WindmillHouse_Adult", "song_storms"),
    "Song from Royal Familys Tomb": ("Graveyard_Child", "Obj_Graveyard_Tombstone_A_03", "song_sun"),
    "Song from Ocarina of Time": ("HyruleField_Child", "Obj_Ocarina_Time_A_01", "song_time"),
    "Sheik in Crater": ("DeathMountainCrater_Adult", "Obj_DeathMtCrater_WarpPoint_A_01", "song_bolero"),
    "Sheik in Ice Cavern": ("IceCavern", "Obj_IceCave_TBoxPedestal_A_01", "song_serenade"),
    "Sheik at Colossus": ("DesertColossus_Adult", "Obj_DesertColossus_WarpPoint_A_01", "song_requiem"),
    "Sheik in Kakariko": ("KakarikoVillage_Adult", "Land_Kakariko_WellParts_A_01", "song_nocturne"),
    "Sheik at Temple": ("Market_Adult", "Obj_TimeTemple_Door_A_01", "song_prelude"),
    "HC Zeldas Letter": ("HyruleCastle", "Npc_Hylia_Zelda_Child", "letter"),
    "HC Malon Egg": ("HyruleCastle", "Npc_Hylia_Malon_Child", "egg"),
    "HF Ocarina of Time Item": ("HyruleField_Child", "Obj_Ocarina_Time_A_01", "ocarina_time"),
    "LW Gift from Saria": ("KokiriForest_Child", "Npc_Kokiri_Saria_Child_OcarinaHolder", "ocarina_fairy"),
    "LW Target in Woods": ("LostWood_Child", "Obj_LostWood_Target_A_01", {"type": 20}),
    "LW Trade Cojiro": ("LostWood_Adult", "Npc_Hylia_017_Adult", {"type": 18}),
    "LW Trade Odd Potion": ("LostWood_Adult", "Npc_Kokiri_Fado_Adult", {"type": 18}),
    "Kak Anju as Child": ("KakarikoVillage_Child", "Npc_Hylia_049_Child", "cucco"),
    "Kak Anju as Adult": ("KakarikoVillage_Adult", "Npc_Hylia_049_Adult", "cucco"),
    "Kak Anju Trade Pocket Cucco": ("KakarikoVillage_Adult", "Npc_Hylia_049_Adult", "cucco"),
    "Kak Man on Roof": ("KakarikoVillage_Child", "Land_Kakariko_ImpaProp_A_01", {"type": 18}),
    "GC Darunias Joy": ("GoronCity_Child", "Npc_Goron_Darunia_Child", {"type": 18}),
    "GC Medigoron": ("GoronCity_Adult", "Npc_Goron_Medigoron_Adult", {"type": 18}),
    "GC Rolling Goron as Adult": ("GoronCity_Adult", "Npc_Goron_DaruniaJr_Adult", {"type": 18}),
    "GC Rolling Goron as Child": ("GoronCity_Child", "Obj_GoronCity_LargePot_A_01", {"type": 18}),
    "GC Pot Freestanding PoH": ("GoronCity_Child", "Obj_GoronCity_LargePot_A_01", "pot"),
    "DMT Biggoron": ("DeathMountainTrail_Adult", "Npc_Goron_Biggoron_Adult", {"type": 18}),
    "DMT Trade Broken Sword": ("DeathMountainTrail_Adult", "Npc_Goron_Biggoron_Adult", {"type": 18}),
    "DMT Trade Eyedrops": ("DeathMountainTrail_Adult", "Npc_Goron_Biggoron_Adult", {"type": 18}),
    "ZD King Zora Thawed": ("ZoraDomain_Adult", "Npc_Zora_KingZora_adult", {"type": 18}),
    "ZD Trade Prescription": ("ZoraDomain_Adult", "Npc_Zora_KingZora_adult", {"type": 18}),
    "LH Lab Dive": ("HyruleField_Child", "Npc_Hylia_045_Child", {"type": 27}),
    "LH Trade Eyeball Frog": ("HyruleField_Adult", "Npc_Hylia_045_Adult", {"type": 18}),
    "GV Trade Poachers Saw": ("GerudoValley_Adult", "Npc_Hylia_012_Adult", {"type": 18}),
    "Market Lost Dog": ("Market_Child", "Animal_Dog_Richard_01", {"type": 18}),
    "Wasteland Bombchu Salesman": ("HountedWasteland_Adult", "Npc_Hylia_044_Adult", {"type": 4}),
    "ToT Light Arrows Cutscene": ("Market_Adult", "Obj_TimeTemple_Door_A_01", "light_arrow"),
    "ToT Master Sword": ("Market_Adult", "Obj_TimeTemple_Door_A_01", "master_sword"),
    "ToT Reward from Rauru": ("Market_Adult", "Obj_TimeTemple_Door_A_01", {"type": 18}),
    "LH Sun": ("HyruleField_Adult", "Obj_Arrow_Fire", "arrow_fire"),
    "LH Underwater Item": ("HyruleField_Child", "Obj_Bottle_Letter", "letter"),
}
BOSS = {"Queen Gohma": "InsideTheDekuTree", "King Dodongo": "DodongoCavern", "Barinade": "InsideJabuJabuBelly",
        "Phantom Ganon": "ForestTemple", "Volvagia": "FireTemple", "Morpha": "WaterTemple",
        "Bongo Bongo": "ShadowTemple", "Twinrova": "SpiritTemple"}
SPREAD = 2.0  # m: checks sharing one spot (a shop's slots) sit around it this far, so each one shows


def _hash64(text):
    """A stable 64-bit id for a spot (its icon's InstanceID): the first 8 bytes of SHA-1."""
    import hashlib
    return struct.unpack("<Q", hashlib.sha1(text.encode()).digest()[:8])[0]


class _Levels:
    """Placements of the game's levels, read once each: {level: [(Gyaml, Hash, Translate, Dynamic)]}."""

    def __init__(self, fs):
        self.fs, self.cache = fs, {}

    def actors(self, level):
        if level not in self.cache:
            import romtools
            area = level.split("_")[0]
            out = []
            for part in ("Static", "Dynamic"):
                try:
                    root = romtools.byml_load(self.fs.read(f"Banc/{area}/{level}_{part}.bcett.byml.zs"))[0]
                except (OSError, KeyError, ValueError):
                    continue
                for a in root.get("Actors") or []:
                    if a.get("Translate"):
                        out.append((a.get("Gyaml"), str(a.get("Hash")), [float(v) for v in a["Translate"]],
                                    a.get("Dynamic") or {}))
            self.cache[level] = out
        return self.cache[level]

    def find(self, level, gyaml=None, hash_=None):
        for g, h, pos, dyn in self.actors(level):
            if (gyaml is None or g == gyaml) and (hash_ is None or h == str(hash_)):
                return pos, dyn
        return None


def _level_of(file):
    """The level of a Banc file path ("Banc/X/X_Child_Static.bcett.byml.zs" -> "X_Child")."""
    return re.sub(r"_(Static|Dynamic)$", "", os.path.basename(file).split(".")[0])


def _rec(name, level, pos, icon, kind, floor_index=None, n=0):
    r = {"loc": name, "kind": kind, "level": level, "pos": [round(v, 2) for v in pos], "has_flag": False,
         "hash": str(_hash64(f"{name}#{n}")), "map": "dungeon" if floor_index is not None else "field",
         "floor": None, "icon": icon, "spot": True}
    if floor_index is not None:
        r["floor_index"] = floor_index
    return r


def _spread(recs):
    """Spots sharing one position are spread around it (SPREAD m), in name order."""
    groups = {}
    for r in recs:
        groups.setdefault((r["level"], tuple(r["pos"])), []).append(r)
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda r: r["loc"])
        for i, r in enumerate(g):
            a = 2 * math.pi * i / len(g)
            r["pos"] = [round(r["pos"][0] + SPREAD * math.cos(a), 2), r["pos"][1],
                        round(r["pos"][2] + SPREAD * math.sin(a), 2)]


def records(fs, plan, names, proto=None):
    """{check: [map record]} for `names` (the checks without one), from the sources in the module docstring.
    Records are like the map research's, plus "icon" and, on a dungeon floor, "floor_index"."""
    import romtools
    lv = _Levels(fs)
    mp = romtools.byml_load(fs.read(MAPPARAM), allow_big=True)[0]
    out = {}

    def add(name, rec):
        out.setdefault(name, []).append(rec)
    facilities = {}
    for level, param in mp.items():
        for f in param.get("Facility") or []:
            facilities.setdefault(f.get("IconType"), []).append((level, f["Trans"]))
    # silver rupee spots: at their token
    spots = (((plan.get("_gaps") or {}).get("silver_rupees") or {}).get("spots")) or {}
    for s in spots.values():
        if s.get("location") not in names:
            continue
        level = _level_of(s["file"])
        for k, h in enumerate(s["tokens"]):
            at = lv.find(level, hash_=h)
            if at:
                add(s["location"], dict(_rec(s["location"], level, at[0], "rupee_silver", "freestanding", n=k),
                                        hash=str(h), actor="Obj_Rupee_Silver"))
    # Zora's Domain fish: at the fish of its number
    for row in (plan.get("_extras_fish") or {}).get("zd") or []:
        name, h = row[0], row[3] if len(row) > 3 else None
        if name in names and h:
            for level in ("ZoraDomain_Child", "ZoraDomain_Adult"):
                at = lv.find(level, hash_=h)
                if at:
                    add(name, _rec(name, level, at[0], "fish", "npc"))
                    break
    # Big Poes: at the poe of its fence number
    try:
        from parity import extras_npcs
        fences = {n: s["fence"] for n, s in extras_npcs.SPEC["big_poes"]["locations"].items()}
    except Exception:  # noqa: BLE001 - without the plugin's data the poes stay without a spot
        fences = {}
    poes = [(pos, dyn) for g, h, pos, dyn in lv.actors("HyruleField_Adult") if g == "Enemy_Poe_Big"]
    for name, fence in fences.items():
        if name in names:
            at = next((pos for pos, dyn in poes if dyn.get("PoeBig_FenceID") == fence), None)
            if at:
                add(name, _rec(name, "HyruleField_Adult", at, "big_poe", "npc"))
    # scrubs: at the scrub (the shop map's placements)
    try:
        import shops
        shop_locs = shops.shop_map()["locations"]
    except Exception:  # noqa: BLE001
        shop_locs = {}
    for name in sorted(names):
        e = (shop_locs.get(name) or {})
        if e.get("kind") != "scrub" or name in out:
            continue
        for k, p in enumerate((e.get("edit") or {}).get("placements") or []):
            at = lv.find(_level_of(p["file"]), hash_=p["hash"])
            if at:
                add(name, _rec(name, _level_of(p["file"]), at[0], "scrub", "scrub", n=k))
                break
    # bosses: at the boss room's door
    for name, dungeon in BOSS.items():
        if name not in names or dungeon not in mp:
            continue
        base = mp[dungeon]
        for i, fl in enumerate(base.get("Floor") or []):
            door = next((d for d in fl.get("Door") or [] if d.get("IsBossRoom")), None)
            if door:
                add(name, _rec(name, dungeon, door["Trans"], "boss", "npc", floor_index=i))
                break
        else:  # no boss door on its map (the child dungeons): the boss room itself (BossRoomId)
            rooms, b = base.get("Room") or [], base.get("BossRoomId", -1)
            if 0 <= b < len(rooms) and rooms[b].get("CenterTrans"):
                fl = (rooms[b].get("Floor") or [base.get("MinFloor", 0)])[0] - base.get("MinFloor", 0)
                add(name, _rec(name, dungeon, rooms[b]["CenterTrans"], "boss", "npc", floor_index=fl))
    # NPCs and markers
    for name, (level, gyaml, icon) in ACTOR.items():
        if name in names and name not in out:
            at = lv.find(level, gyaml=gyaml)
            if at:
                add(name, _rec(name, level, at[0], icon, "song" if str(icon).startswith("song_") else "npc"))
    # next to the place's own map icon
    for name in sorted(names):
        if name in out:
            continue
        hit = next(((t, icon) for rx, t, icon in FACILITY if re.search(rx, name)), None)
        if hit is None:
            continue
        place = FAIRY_PLACE.get(name.split()[0]) if hit[0] == 11 else None
        for level, trans in facilities.get(hit[0], []):
            if level.endswith("_Alternative"):
                continue  # (the tracker copies Kakariko's and Zora's Domain's checks there itself)
            if place and level.split("_")[0] != place:
                continue
            add(name, _rec(name, level, trans, hit[1], "shop" if re.search(r"Shop|Bazaar", name) else "npc"))
    # a spot inside a grotto or a room shows at its way in, like the research's records there: the nearest research
    # record of the level within 20 m that has a way in lends it
    if proto:
        for recs in out.values():
            for r in recs:
                near = [x for x in proto if x.get("level") == r["level"] and x.get("entrance") and x.get("pos")
                        and math.dist(x["pos"], r["pos"]) < 20.0]
                if near:
                    r["entrance"] = min(near, key=lambda x: math.dist(x["pos"], r["pos"]))["entrance"]
    _spread([r for recs in out.values() for r in recs])
    return out
