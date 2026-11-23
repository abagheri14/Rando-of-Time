"""Data for the tracker app (tracker/dist/RandoOfTimeTracker.exe).

  python tools/tracker/build_data.py assets [ROMFS]      the game's map art and item icons, decoded from your own
                                                         game files into tracker/dist/data (maps/*.jpg at the game's
                                                         native 2000x1440, maps/bounds.json, icons/*.png); nothing of
                                                         the game is shipped, every player builds their own. Ends with
                                                         maps/full.txt (the randomizer app rebuilds while it's missing)
  python tools/tracker/build_data.py seed OUT_DIR        OUT_DIR/tracker.json for a generated seed (spoiler-free): its
                                                         maps, every check in play with its spot on the map art and the
                                                         save flags that say it is done, and the items to show

Check flags (what the tracker reads from slot_NN/progress.sav):
  b64   a placement's save flag (Bool64bitKey). Gold Skulltulas, freestanding pickups, objects that are gone for good
        once their item is taken, and the remake's ice-trap chest (it breaks). Not chests, opening one never writes
        it (tools/rando/chest_flags.py)
  bit   an element of the saved bool array RandoChecked, for the respawn model (tools/rando/drops.py CHECKED_ARRAY)
  bool  a named saved flag. A chest's IsTreasureBoxOpen.<placement hash>, which is the game's "opened" record
        (tools/rando/chest_flags.py), a flagless drop's borrowed flag (tools/rando/free_flags.py), or a fairy's flag
Checks without a spot or a flag (NPC gifts, songs, shops, scrubs) are listed under "Other checks" and marked by hand.
Map pixel positions come from tracker/research (mapinfo.py and build_checks.py, from the game's map cameras).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
RESEARCH = os.path.join(HERE, "tracker", "research")
sys.path.insert(0, RESEARCH)
DIST = os.path.join(HERE, "tracker", "dist", "data")
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS
SCALE = 1.0  # map art and the checks' map spots, at the game's native 2000x1440
# Older seeds are at half that size, without "map_scale" in tracker.json, and the app reads both.
MAP_W, MAP_H = 2000, 1440

# the items to show: (shown name, group, pouch actor (StockNum) or None, IsGet flag or None, icon actor)
ITEMS = [
    ("Kokiri Sword", "Equipment", "Weapon_Sword_Kokiri", None, "Weapon_Sword_Kokiri"),
    ("Master Sword", "Equipment", "Weapon_Sword_Master", None, "Weapon_Sword_Master"),
    ("Biggoron's Sword", "Equipment", "Weapon_Sword_Biggoron", None, "Weapon_Sword_Biggoron"),
    ("Deku Shield", "Equipment", "Weapon_Shield_Deku", None, "Weapon_Shield_Deku"),
    ("Hylian Shield", "Equipment", "Weapon_Shield_Hylian", None, "Weapon_Shield_Hylian"),
    ("Mirror Shield", "Equipment", "Weapon_Shield_Mirror", None, "Weapon_Shield_Mirror"),
    ("Goron Tunic", "Equipment", "Armor_Adult_Goron", None, "Armor_Adult_Goron"),
    ("Zora Tunic", "Equipment", "Armor_Adult_Zora", None, "Armor_Adult_Zora"),
    ("Iron Boots", "Equipment", "Armor_Adult_HeavyBoot", None, "Armor_Adult_HeavyBoot"),
    ("Hover Boots", "Equipment", "Armor_Adult_HoverBoot", None, "Armor_Adult_HoverBoot"),
    ("Deku Sticks", "Items", "Item_DekuStick", None, "Item_DekuStick"),
    ("Deku Nuts", "Items", "Item_DekuNut", None, "Item_DekuNut"),
    ("Bombs", "Items", "Item_Bomb", None, "Item_Bomb"),
    ("Bombchus", "Items", "Item_Bombchu", None, "Item_Bombchu"),
    ("Slingshot", "Items", "Weapon_Range_SlingShot", None, "Weapon_Range_SlingShot"),
    ("Bow", "Items", "Weapon_Range_Bow", None, "Weapon_Range_Bow"),
    ("Fire Arrows", "Items", "Item_Arrow_Fire", None, "Item_Arrow_Fire"),
    ("Ice Arrows", "Items", "Item_Arrow_Ice", None, "Item_Arrow_Ice"),
    ("Light Arrows", "Items", "Item_Arrow_Light", None, "Item_Arrow_Light"),
    ("Boomerang", "Items", "Item_Boomerang", None, "Item_Boomerang"),
    ("Hookshot", "Items", "Item_Hookshot", None, "Item_Hookshot"),
    ("Longshot", "Items", "Item_Longshot", None, "Item_Longshot"),
    ("Megaton Hammer", "Items", "Item_Hammer", None, "Item_Hammer"),
    ("Lens of Truth", "Items", "Item_GlassTruth", None, "Armor_GlassTruth"),
    ("Din's Fire", "Items", "Item_DinFire", None, "Item_DinFire"),
    ("Farore's Wind", "Items", "Item_FaroreWind", None, "Item_FaroreWind"),
    ("Nayru's Love", "Items", "Item_NayruLove", None, "Item_NayruLove"),
    ("Fairy Ocarina", "Items", "Item_Ocarina_Fairy", None, "Item_Ocarina_Fairy"),
    ("Ocarina of Time", "Items", "Item_Ocarina_Time", None, "Item_Ocarina_Time"),
    ("Bottles", "Items", "Item_Bottle", None, "Item_Bottle"),
    ("Magic Beans", "Items", "Item_MagicBean", None, "Item_MagicBean"),
    ("Goron's Bracelet", "Upgrades", "Item_Gauntlet_Goron", None, "Armor_Child_Gauntlet_Goron"),
    ("Silver Gauntlets", "Upgrades", "Armor_Adult_Gauntlet_Silver", None, "Armor_Adult_Gauntlet_Silver"),
    ("Golden Gauntlets", "Upgrades", "Armor_Adult_Gauntlet_Gold", None, "Armor_Adult_Gauntlet_Gold"),
    ("Silver Scale", "Upgrades", "Item_Scale_Silver", None, "Item_Scale_Silver"),
    ("Golden Scale", "Upgrades", "Item_Scale_Gold", None, "Item_Scale_Gold"),
    ("Adult's Wallet", "Upgrades", "Item_Wallet_Medium", None, "Item_Wallet_Medium"),
    ("Giant's Wallet", "Upgrades", "Item_Wallet_Large", None, "Item_Wallet_Large"),
    ("Bomb Bag", "Upgrades", "Item_BombBag_Small", None, "Item_BombBag_Small"),
    ("Quiver", "Upgrades", "Item_Quiver_Small", None, "Item_Quiver_Small"),
    ("Bullet Bag", "Upgrades", "Item_BulletBag_Small", None, "Item_BulletBag_Small"),
    ("Magic", "Upgrades", "Item_FairyBless_MP", None, "Item_FairyBless_MP"),
    ("Double Defense", "Upgrades", "Item_FairyBless_DefenseDouble", None, "Item_FairyBless_DefenseDouble"),
    ("Stone of Agony", "Upgrades", "Item_AgonyStone", None, "Item_AgonyStone"),
    ("Gerudo Card", "Upgrades", "Item_Token_Gerudo", None, "Item_Token_Gerudo"),
    ("Gold Skulltula Tokens", "Upgrades", "Item_Token_Gold", None, "Item_Token_Gold"),
    ("Kokiri Emerald", "Quest", "Item_Stone_Forest", None, "Rando_Stone_Forest"),
    ("Goron Ruby", "Quest", "Item_Stone_Fire", None, "Rando_Stone_Fire"),
    ("Zora Sapphire", "Quest", "Item_Stone_Water", None, "Rando_Stone_Water"),
    *[(f"{n} Medallion", "Quest", f"Item_Medal_{n}", None, f"Rando_Medal_{n}")
      for n in ("Forest", "Fire", "Water", "Shadow", "Spirit", "Light")],
    *[(n, "Songs", f"Item_Melody_{a}", None, f"OcarinaMelodyIcon_{i:02d}") for i, (n, a) in enumerate((
        ("Zelda's Lullaby", "ZeldaLullaby"), ("Epona's Song", "EponaSong"), ("Saria's Song", "SariaSong"),
        ("Sun's Song", "SunSong"), ("Song of Time", "TimeSong"), ("Song of Storms", "StormSong"), (None, None),
        ("Minuet of Forest", "ForestMinuet"), ("Bolero of Fire", "FireBolero"), ("Serenade of Water", "WaterSerenade"),
        ("Nocturne of Shadow", "ShadowNocturne"), ("Requiem of Spirit", "SpiritRequiem"),
        ("Prelude of Light", "LightPrelude"))) if n],
]
# The game's song symbols are Common bntx OcarinaMelodyIcon_00..12 (decoded by tracker/research/build_maps.py). In
# order: Lullaby, Epona, Saria, Sun, Time, Storms, Scarecrow, then the six warp songs in medallion order (forest ...
# light).
MEDAL_SYMBOL = {"Forest": 7, "Fire": 8, "Water": 9, "Shadow": 10, "Spirit": 11, "Light": 12}
MEDAL_COLOUR = {"Forest": (40, 160, 70), "Fire": (210, 60, 40), "Water": (50, 110, 220), "Shadow": (130, 60, 170),
                "Spirit": (230, 140, 40), "Light": (235, 205, 70)}
STONE_COLOUR = {"Forest": (40, 200, 90), "Fire": (220, 40, 60), "Water": (70, 140, 255)}
NICE = {"InsideTheDekuTree": "Deku Tree", "DodongoCavern": "Dodongo's Cavern", "InsideJabuJabuBelly": "Jabu-Jabu's Belly",
        "GanonCastle": "Outside Ganon's Castle", "HyruleCastle": "Hyrule Castle", "LakeHylia": "Lake Hylia",
        "BottomOfTheWell": "Bottom of the Well", "InsideGanonCastle": "Ganon's Castle", "GanonTower": "Ganon's Tower",
        "GerudoTrainingGround": "Gerudo Training Ground", "IceCavern": "Ice Cavern", "HountedWasteland": "Haunted Wasteland",
        "LonLonRanch": "Lon Lon Ranch", "Market": "Hyrule Market", "LostWood": "Lost Woods",
        "ZoraDomain": "Zora's Domain", "ZoraFountain": "Zora's Fountain", "ZoraRiver": "Zora's River"}


def nice(level):
    if level in NICE:
        return NICE[level]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", level)


def map_title(tex):
    """("Kokiri Forest (child)", level) for "KokiriForest_Child_00"; ("Deku Tree B1", ...) for a dungeon floor."""
    parts = tex.split("_")
    if len(parts) >= 3 and parts[1] in ("Child", "Adult"):
        t = f"{nice(parts[0])} ({parts[1].lower()})" + (" (later)" if parts[2] != "00" else "")
        return t, f"{parts[0]}_{parts[1]}", parts[1].lower(), None, "field"
    return f"{nice(parts[0])} {parts[1]}", parts[0], None, parts[1], "dungeon"


def assets(romfs=DEFAULT_ROMFS):
    os.environ["REMAKE_ROMFS"] = romfs  # the map decoders (tracker/research) read the game from there
    from PIL import Image
    import bntx
    bntx.ROMFS = romfs
    maps_dir = os.path.join(DIST, "maps")
    os.makedirs(maps_dir, exist_ok=True)
    os.makedirs(os.path.join(DIST, "icons"), exist_ok=True)
    marker = os.path.join(maps_dir, "full.txt")
    if os.path.exists(marker):
        os.remove(marker)  # written again at the end, once every map is at full size
    import build_maps
    cache = build_maps.cache_dir(SCALE)  # a separate folder, so the old half-size cache is never reused
    if not os.path.isdir(cache) or len([f for f in os.listdir(cache) if f.endswith(".webp")]) < 50:
        build_maps.main(["--scale", str(SCALE), "--out", cache])  # decode the game's maps first (a few minutes)
    bounds_path = os.path.join(maps_dir, "bounds.json")
    try:
        with open(bounds_path, encoding="utf-8") as f:
            bounds = json.load(f)
    except (OSError, ValueError):
        bounds = {}
    n = 0
    for fn in sorted(os.listdir(cache)):
        if not fn.endswith(".webp"):
            continue
        name = fn[:-5]
        dst = os.path.join(maps_dir, name + ".jpg")
        with Image.open(os.path.join(cache, fn)) as src:
            stale = True
            if os.path.exists(dst):
                try:
                    with Image.open(dst) as old:
                        stale = old.size != src.size  # an old half-size map gets written again at full size
                except OSError:
                    stale = True
            if not stale and name in bounds:
                continue
            im = src.convert("RGBA")
        alpha = im.split()[3]
        # the art's real extent, which the tracker fits to its panel instead of the empty frame around it
        box = alpha.point(lambda a: 255 if a > 24 else 0).getbbox()
        if box:
            bounds[name] = [box[0], box[1], box[2], box[3], im.size[0], im.size[1]]
        if stale:
            bg = Image.new("RGB", im.size, (46, 32, 20))
            bg.paste(im, mask=alpha)
            bg.save(dst, quality=90, optimize=True)
            n += 1
    with open(bounds_path, "w", encoding="utf-8") as f:
        json.dump(bounds, f, indent=0, sort_keys=True)
    fs = bntx.romfs()
    k = 0
    _quest_icons(os.path.join(DIST, "icons"))
    for name, _, _, _, icon in ITEMS:
        dst = os.path.join(DIST, "icons", icon + ".png")
        rel = f"UI/Tex/Icon/{icon}.bntx.zs"
        if os.path.exists(dst):
            continue
        try:
            t = bntx.textures(fs.read(rel))[0]
        except Exception:  # noqa: BLE001 - no icon of that name: the tracker shows the name
            continue
        Image.fromarray(bntx.decode(t), "RGBA").resize((96, 96), Image.LANCZOS).save(dst)
        k += 1
    full = [f for f in os.listdir(maps_dir) if f.endswith(".jpg")]
    with open(marker, "w", encoding="utf-8") as f:
        f.write(f"{MAP_W}x{MAP_H}: {len(full)} maps at the game's native size\n")
    print(f"{DIST}: {n} maps and {k} icons written")


def _quest_icons(dst):
    """Song symbols come from the decoded game icons. The game has no 2D icon for the medallions or the three stones, so
    we draw those here. A medallion is a disc in the sage's colour under the game's symbol, and a stone is a cut gem in
    a gold setting."""
    from PIL import Image, ImageDraw
    src = os.path.join(RESEARCH, "cache", "icons")
    for i in range(13):
        p = os.path.join(src, f"OcarinaMelodyIcon_{i:02d}.png")
        q = os.path.join(dst, f"OcarinaMelodyIcon_{i:02d}.png")
        if os.path.exists(p) and not os.path.exists(q):
            Image.open(p).convert("RGBA").resize((96, 96), Image.LANCZOS).save(q)
    for n, sym in MEDAL_SYMBOL.items():
        q = os.path.join(dst, f"Rando_Medal_{n}.png")
        im = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((4, 4, 92, 92), fill=(214, 178, 92, 255))
        d.ellipse((10, 10, 86, 86), fill=MEDAL_COLOUR[n] + (255,))
        p = os.path.join(src, f"OcarinaMelodyIcon_{sym:02d}.png")
        if os.path.exists(p):
            s_ = Image.open(p).convert("RGBA").resize((60, 60), Image.LANCZOS)
            im.alpha_composite(s_, (18, 18))
        im.save(q)
    for n, col in STONE_COLOUR.items():
        q = os.path.join(dst, f"Rando_Stone_{n}.png")
        im = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.polygon([(48, 6), (84, 40), (48, 90), (12, 40)], fill=(214, 178, 92, 255))
        d.polygon([(48, 14), (76, 40), (48, 80), (20, 40)], fill=col + (255,))
        d.polygon([(48, 14), (62, 40), (48, 52), (34, 40)], fill=tuple(min(255, c + 70) for c in col) + (255,))
        im.save(q)


def seed(out_dir):
    import drops as D
    spoiler = json.load(open(os.path.join(out_dir, "spoiler.json"), encoding="utf-8"))
    plan = json.load(open(os.path.join(out_dir, "plan.json"), encoding="utf-8"))
    proto = json.load(open(os.path.join(RESEARCH, "checks_proto.json"), encoding="utf-8"))
    seed_p = os.path.join(out_dir, "seed.json")
    ages = (json.load(open(seed_p, encoding="utf-8")).get("check_ages") or {}) if os.path.exists(seed_p) else {}
    m = D._map()
    extras_name = {k: e.get("location") for k, e in m.get("extras", {}).items() if e.get("location")}
    by_loc = {}
    for r in proto:
        by_loc.setdefault(extras_name.get(r["loc"], r["loc"]), []).append(r)
    # Hyrule Field's level also holds Lake Hylia and Lon Lon Ranch, which have their own map art. A field spot goes on
    # the most zoomed-in map (smallest camera Height) of its level whose frame holds it, trying the maps of the check's
    # own area first. The area comes from the check's name, the way OoTR names them. So an HF check beside the ranch
    # stays on Hyrule Field's map and in its count, and a ranch check goes on the ranch's.
    own_area = (("HF ", "HyruleField"), ("Hyrule Field ", "HyruleField"), ("LLR ", "LonLonRanch"),
                ("Lon Lon Ranch ", "LonLonRanch"), ("LH ", "LakeHylia"), ("Lake Hylia ", "LakeHylia"))
    import mapinfo
    cams = []
    for area, a_ in mapinfo.areas().items():
        mm, cap = a_["menu"], a_["capture"]
        if cap.get("IsDungeon"):
            continue
        for i, (banc, tex) in enumerate(zip(mm.get("BancName") or [], mm.get("TextureName") or [])):
            if banc and tex:
                cams.append((banc, tex, cap))
    also = {"HyruleField": ("LakeHylia", "LonLonRanch")}

    def best_map(r, name):
        if r.get("map") != "field" or not r.get("pos") or not r.get("level"):
            return r.get("texture"), r.get("px"), r.get("py")
        level = r["level"]
        base, _, age = level.partition("_")
        ok = {level} | {f"{x}_{age}" for x in also.get(base, ())}
        found = []
        for banc, tex, cap in cams:
            if banc in ok:
                px, py = mapinfo.project(cap, r["pos"][0], r["pos"][2])
                if 0 <= px <= mapinfo.TEX_W and 0 <= py <= mapinfo.TEX_H:
                    found.append((cap["Height"], tex, px, py, banc.partition("_")[0]))
        if not found:
            return r.get("texture"), r.get("px"), r.get("py")
        own = next((b for pre, b in own_area if name.startswith(pre)), None)
        _, tex, px, py, _ = min([f for f in found if f[4] == own] or found)
        return tex, px, py
    # Cows, including the remake-only GF Cow. The map research has no cow record, so each cow holding a check gets one
    # here, at the cow (a grotto cow at the grotto's way in). It's done when its give flag is set (_cow_records).
    cow_recs, cow_flag = _cow_records(proto)
    for name, recs in cow_recs.items():
        if name in by_loc:
            continue
        for r in recs:
            tex, px, py = best_map(r, name)
            if tex and px is not None:
                by_loc.setdefault(name, []).append(dict(r, texture=tex, px=round(px, 1), py=round(py, 1)))
    respawn = (plan.get("_drops_respawn") or {}).get("spots", {})
    array = (plan.get("_drops_respawn") or {}).get("array", D.CHECKED_ARRAY)
    flagless = plan.get("_drops_flag_spots") or {}
    flagless_own = plan.get("_drops_flagless_own") or {}  # FLAGLESS OWN drops get a RandoChecked bit, like respawns
    # The fairy shuffles (parity/fairies.py). A stone uses its borrowed flag, the oasis its cutscene's once-flag, and a
    # grotto its scene-ID flag, since its 8 items come together.
    fa = plan.get("_fairies") or {}
    fairy_flag = {n: x["flag"] for n, x in (fa.get("stones") or {}).items()}
    try:
        import fairies as FA  # tools/rando/fairies.py
        fm = FA.fairy_map()
        fairy_flag.update({x["location"]: fm["colossus"]["once"] for x in fa.get("colossus") or []})
        fairy_flag.update({x["location"]: fm["grottos"][g]["once"] for g, xs in (fa.get("grottos") or {}).items()
                           for x in xs})
        fairy_flag.update({x["location"]: fm["rooms"][g]["once"] for g, xs in (fa.get("rooms") or {}).items()
                           for x in xs})  # Ganon's Castle fountain room uses its scene ID flag, like a grotto
        fairy_flag.update({n: x["flag"] for n, x in (fa.get("notes") or {}).items()})
        fairy_flag.update({g["location"]: x["flag"] for x in (fa.get("beans") or {}).values() for g in x["gives"]})
    except (ImportError, OSError, KeyError):
        pass
    # Chests use the game's saved IsTreasureBoxOpen.<hash>, since their Bool64bitKey is never written. The trap chest
    # uses its per-object flag and the Treasure Chest Game uses its own flags (tools/rando/chest_flags.py).
    import chest_flags  # tools/rando/chest_flags.py
    chest_flag = chest_flags.tracker_flags(spoiler.get("locations", {}), plan, spoiler.get("settings") or {})
    # The scene gifts (drops.SCENE_GIFTS, plan "_notes_drops_scene_gifts"). The Goron City pot uses its once-flag. The
    # Zora's Domain grotto's six items come together and are marked by the HavePlayedEvent flag of its reused scene ID.
    # Their rupee placements are deleted, so their Bool64bitKey is never written (the gamedb tracker audit found that).
    gift_flag = {}
    for x in plan.get("_notes_drops_scene_gifts") or []:
        n = x.split(":")[0]
        g = ((m.get("scene_gifts") or {}).get(n) or {}).get("scene_gift") or {}
        if g.get("flag"):
            gift_flag[n] = g["flag"]
        elif g.get("row"):
            gift_flag[n] = "HavePlayedEvent." + g["row"]
    maps, checks = {}, []
    for name in sorted(spoiler.get("locations", {})):
        recs = by_loc.get(name, [])
        flags = []
        if name in respawn:
            flags.append({"t": "bit", "a": array, "i": respawn[name]["bit"]})
        elif name in flagless_own:
            flags.append({"t": "bit", "a": array, "i": flagless_own[name]["bit"]})
        elif name in flagless:
            flags.append({"t": "bool", "n": flagless[name]})
        elif name in fairy_flag:
            flags.append({"t": "bool", "n": fairy_flag[name]})
        elif name in gift_flag:
            flags.append({"t": "bool", "n": gift_flag[name]})
        elif name in chest_flag:
            flags += chest_flag[name]
        elif name in cow_flag:
            flags.append({"t": "bool", "n": cow_flag[name]})
        else:
            flags += [{"t": "b64", "h": str(r["hash"])} for r in recs if r.get("has_flag")]
        spot = _pick_spot(recs, ages.get(name))
        c = {"name": name, "kind": (recs[0]["kind"] if recs else _kind(name)), "flags": flags}
        if spot:
            tex, px, py = best_map(spot, name)
            spot = dict(spot, texture=tex, px=px, py=py)
            spot = _at_entrance(spot, name, best_map)  # inside a room, so at the room's way in (_place_rooms)
            title, level, age, floor, kind = map_title(spot["texture"])
            mp = maps.setdefault(spot["texture"], {"id": spot["texture"], "title": title, "area": title,
                                                    "image": f"maps/{spot['texture']}.jpg", "age": age,
                                                    "floor": floor, "kind": kind, "levels": []})
            if level not in mp["levels"] and not any(level in x["levels"] for x in maps.values()):
                mp["levels"].append(level)
            c.update(map=spot["texture"], area=mp["area"], x=round(spot["px"] * SCALE, 1), y=round(spot["py"] * SCALE, 1))
            if spot.get("_room"):
                c["_room"] = spot["_room"]
        checks.append(c)
    _place_rooms(checks)
    items = [{"name": n, "group": g, "pouch": p, "bool": b, "icon": f"icons/{i}.png"} for n, g, p, b, i in ITEMS]
    s = json.load(open(os.path.join(out_dir, "seed.json"), encoding="utf-8")) if os.path.exists(
        os.path.join(out_dir, "seed.json")) else {}
    out = {"format": 1, "map_scale": SCALE, "seed": str(s.get("seed") or spoiler.get(":seed") or "?"),
           "title": f"Seed {s.get('seed') or spoiler.get(':seed')} ({os.path.basename(os.path.normpath(out_dir))})",
           "spoiler": "spoiler.json", "settings": [f"{k}: {v}" for k, v in sorted((spoiler.get("settings") or {}).items())
                                                   if not isinstance(v, (list, dict))][:200],
           "maps": sorted(maps.values(), key=lambda x: (x["kind"] != "field", x["title"])),
           "checks": checks, "items": items}
    p = os.path.join(out_dir, "tracker.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    placed = sum(1 for c in checks if "map" in c)
    auto = sum(1 for c in checks if c["flags"])
    print(f"{p}: {len(checks)} checks ({placed} on a map, {auto} tracked from the save), {len(maps)} maps")
    return p


# Room checks go at the room's way in
# A check inside a grotto, a grave, a tomb, the castle courtyard, a hidden cave or a boss room is pinned where the
# player goes in, the way the game's map and Nintendo's Zelda Notes do it. tracker/research/build_checks.py
# entrances() gives its record the way in: a hole's mouth, the actor its ROOM_TABLE names, or for a boss room the
# doorway of the drawn room it's entered from. A proto built before that has none, and its checks stay where they are.
# A room's checks share that spot, so they're laid out as one small cluster, ROOM_PIN_GAP screen px apart at the
# tracker's fit zoom. MapView pins are 13 px across, so they just touch. It's side by side, a triangle, a square, a
# ring up to 6 and a honeycomb from 7, in kind and name order. The cluster sits on the way in, or as close beside it
# as it fits without covering another check's pin (the rocks or grass over a grotto's mouth). At a doorway it goes on
# the drawn side of the door.
# When the map art is there (assets), it also keeps the cluster on the drawn art, and any other pin that's off the
# art (on the dark frame or the soft glow around the art) moves to the nearest drawn art. Only the spots change, every
# check keeps its name, kind and flags.
ROOM_PIN_GAP = 11.5      # screen px between a cluster's pins at fit zoom
ROOM_VIEW = (873, 550)   # map panel of a 1500x900 tracker window in screen px, the fit zoom the gap is set for
ROOM_FRAME = (46, 32, 20)  # the frame colour assets() pastes the art on
ROOM_SOLID = 52          # the drawn art is this far from it or more (largest channel), the glow's fade less, measured
ROOM_OFF = 30            # a pin whose spot is nearer the frame than this (at 1/8 size) is off the art (measured)
ROOM_KINDS = ("chest", "boss_heart", "gs", "freestanding", "freestanding_rupee_heart", "pot", "flying_pot", "crate",
              "beehive", "grass", "rock_liftable", "rock_bombable", "tree", "bush", "icicle", "fairy")
_ROOM_BOUNDS = {}


def _at_entrance(spot, name, best_map):
    """Moves a room check's spot to the room's way in (its record's "entrance"). The room goes along in "_room"."""
    e = spot.get("entrance")
    if not e:
        return spot
    if e.get("texture"):  # a dungeon doorway: on its floor's map
        return dict(spot, texture=e["texture"], px=e["px"], py=e["py"], _room=e)
    tex, px, py = best_map(dict(spot, pos=e["pos"]), name)  # the field map showing the way in (the check's own area)
    if (tex, px, py) == (spot.get("texture"), spot.get("px"), spot.get("py")):
        return spot  # the way in isn't on any map of the level, so the check stays put
    return dict(spot, texture=tex, px=px, py=py, _room=e)


def _room_spacing(map_id):
    """Map px between a cluster's pins on this map. It comes from the art's size, since the tracker fits the art to its
    panel."""
    if not _ROOM_BOUNDS:
        try:
            with open(os.path.join(DIST, "maps", "bounds.json"), encoding="utf-8") as f:
                _ROOM_BOUNDS.update(json.load(f))
        except (OSError, ValueError):
            _ROOM_BOUNDS[""] = None
    b = _ROOM_BOUNDS.get(map_id)
    if not b:
        return 22.0 * SCALE
    k = MAP_W / b[4]  # the art's box is in the image's pixels, which are now the map's native ones
    w, h = max(1, b[2] - b[0]) * k, max(1, b[3] - b[1]) * k
    fit = min(ROOM_VIEW[0] / (w * 1.05), ROOM_VIEW[1] / (h * 1.05))  # MapView.FitBounds pads the art by 2.5%
    return max(10.0, min(32.0, ROOM_PIN_GAP / fit)) * SCALE


def _room_cluster(n, s):
    """n offsets around the way in, s apart, in the order the room's checks take them."""
    import math
    if n <= 1:
        return [(0.0, 0.0)] * n
    if n <= 6:  # 2 side by side, 3 a triangle, 4 a square, 5 and 6 a ring, clockwise from the top (left)
        r = s / (2 * math.sin(math.pi / n))
        a0 = {2: math.pi, 4: 1.25 * math.pi}.get(n, -0.5 * math.pi)
        return [(r * math.cos(a0 + 2 * math.pi * i / n), r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]
    return _room_honeycomb(n, s)


def _room_honeycomb(n, s, taken=()):
    """n spots of a honeycomb grown ring by ring from the middle, staying clear of the spots in taken (other pins
    there), read row by row."""
    import math
    h = s * math.sqrt(3) / 2
    k = 1
    while True:
        grid = [(s * (i + j / 2), h * j) for j in range(-k, k + 1) for i in range(-2 * k - 1, 2 * k + 2)]
        pts = [p for p in grid if math.hypot(*p) <= (k + 0.5) * s and all(
            math.hypot(p[0] - x, p[1] - y) >= s for x, y in taken)]
        if len(pts) >= n:
            break
        k += 1
    pts.sort(key=lambda p: (round(math.hypot(*p) / s, 2), math.atan2(p[0], -p[1]) % (2 * math.pi)))
    pts = pts[:n]
    if not taken:
        mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
        pts = [(x - mx, y - my) for x, y in pts]
    return sorted(pts, key=lambda p: (round(p[1] / h), p[0]))


def _room_steps(s, reach=5.0):
    """The places a cluster may sit beside its way in, as offsets s/2 apart out to reach * s, nearest first."""
    import math
    n = int(2 * reach)
    steps = [(i * s / 2, j * s / 2) for i in range(-n, n + 1) for j in range(-n, n + 1) if i * i + j * j <= n * n]
    return sorted(steps, key=lambda d: (round(math.hypot(*d), 3), math.atan2(d[0], -d[1]) % (2 * math.pi)))


def _room_order(c):
    kind = ROOM_KINDS.index(c["kind"]) if c["kind"] in ROOM_KINDS else len(ROOM_KINDS)
    return kind, [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", c["name"])]


class _ArtMask:
    """Where each map's art is, from maps/<map>.jpg decoded at 1/8 size (None without the art). The frame is flat
    ROOM_FRAME. Around the art there's a soft dark glow (its alpha's fade pasted on the frame) that's less than
    ROOM_SOLID from the frame's colour, and the drawn art is more. A cluster goes on the drawn art. Any other pin counts
    as off the art when the art around its spot is nearer the frame than ROOM_OFF, reading the 1/8 image between its
    cells."""

    def __init__(self):
        self.cache = {}

    def get(self, map_id):
        if map_id not in self.cache:
            self.cache[map_id] = None
            try:
                from PIL import Image, ImageChops
                with Image.open(os.path.join(DIST, "maps", map_id + ".jpg")) as im:
                    im.draft("RGB", (im.size[0] // 8, im.size[1] // 8))  # the JPEG decoder does the downscale, ~2 ms
                    im = im.convert("RGB")
                r, g, b = ImageChops.difference(im, Image.new("RGB", im.size, ROOM_FRAME)).split()
                far = ImageChops.lighter(ImageChops.lighter(r, g), b)  # each cell's distance from the frame's colour
                art = far.point(lambda v: 255 if v > ROOM_SOLID else 0)
                # the drawn art, the distances, the size, and one cell in tracker.json's units (the map's px * SCALE)
                self.cache[map_id] = (art.load(), far.load(), art.size, MAP_W / art.size[0] * SCALE)
            except Exception:  # noqa: BLE001 - no art (yet): the pins stay as they are
                pass
        return self.cache[map_id]

    @staticmethod
    def on(m, x, y, margin=0.0):
        """On the drawn art (and margin inside it, when given)."""
        art, _, (w, h), cell = m
        for dx, dy in ((0, 0), (margin, 0), (-margin, 0), (0, margin), (0, -margin))[:5 if margin else 1]:
            i, j = int((x + dx) // cell), int((y + dy) // cell)
            if not (0 <= i < w and 0 <= j < h and art[i, j]):
                return False
        return True

    @staticmethod
    def off(m, x, y):
        """Off the art, meaning the frame or its glow around the spot. It reads between the cells, so a narrow path
        stays on."""
        _, far, (w, h), cell = m
        u, v = x / cell - 0.5, y / cell - 0.5
        i, j = int(u // 1), int(v // 1)
        fu, fv = u - i, v - j
        val = 0.0
        for a, b, k in ((0, 0, (1 - fu) * (1 - fv)), (1, 0, fu * (1 - fv)), (0, 1, (1 - fu) * fv), (1, 1, fu * fv)):
            if 0 <= i + a < w and 0 <= j + b < h:
                val += far[i + a, j + b] * k
        return val < ROOM_OFF

    def shift(self, map_id, pts, margin, reach):
        """The smallest (dx, dy) that puts every point on the art (margin from its edge if it can), or (0, 0)."""
        m = self.get(map_id)
        if m is None or all(self.on(m, x, y, margin) for x, y in pts):
            return 0.0, 0.0
        cell = m[3]
        n = int(reach // cell)
        steps = sorted(((i * cell, j * cell) for i in range(-n, n + 1) for j in range(-n, n + 1)
                        if i * i + j * j <= n * n), key=lambda d: d[0] * d[0] + d[1] * d[1])
        for need in (margin, 0.0):
            for dx, dy in steps:
                if all(self.on(m, x + dx, y + dy, need) for x, y in pts):
                    return dx, dy
        return 0.0, 0.0


def _pick_spot(recs, age):
    """The record a check is drawn from. If both ages' maps draw a check (the same chest in KokiriForest_Child and
    _Adult), it goes on the map of the age that gets it, from seed.json "check_ages" (OoTR's search with every item).
    That's the adult map for an adult-only check and the child map otherwise, including both ages or no age known."""
    drawn = [r for r in recs if r.get("texture") and r.get("px") is not None]
    if not drawn:
        return None
    want = "_Adult" if age == "adult" else "_Child"
    return next((r for r in drawn if (r.get("level") or "").endswith(want)), drawn[0])


def _place_rooms(checks):
    """Lays each room's checks out around its way in, then keeps every pin on its map's art (see above)."""
    import math
    rooms = {}  # rooms entered at the same spot (a boss room and the undrawn room before it) share one cluster
    for c in checks:
        e = c.pop("_room", None)
        if e is not None and "map" in c:
            rooms.setdefault((c["map"], round(c["x"]), round(c["y"])), (e, []))[1].append(c)
    mask = _ArtMask()
    placed = {id(c) for _, cs in rooms.values() for c in cs}
    moved = 0
    for c in checks:  # any other pin on the frame (a spot the art doesn't draw) goes onto the nearest art
        if "map" not in c or id(c) in placed:
            continue
        m = mask.get(c["map"])
        if m is None or not mask.off(m, c["x"], c["y"]):
            continue
        s = _room_spacing(c["map"])
        dx, dy = mask.shift(c["map"], [(c["x"], c["y"])], 0.5 * s, 12 * s)
        if dx or dy:
            c["x"], c["y"] = round(c["x"] + dx, 1), round(c["y"] + dy, 1)
            moved += 1
    fixed = {}  # each map's pins that are already where they go, the others first, then each room's as it's laid out
    for c in checks:
        if "map" in c and id(c) not in placed:
            fixed.setdefault(c["map"], []).append((c["x"], c["y"]))
    for (map_id, _, _), (e, cs) in sorted(rooms.items(), key=lambda kv: kv[0]):
        s = _room_spacing(map_id)
        shape = _room_cluster(len(cs), s)
        r = max(math.hypot(*o) for o in shape)
        cx, cy = cs[0]["x"], cs[0]["y"]  # all of them are at the way in
        if e.get("toward"):  # a doorway, so into the drawn room behind it, just past the door
            tx, ty = e["toward"][0] * SCALE, e["toward"][1] * SCALE
            d = math.hypot(tx - cx, ty - cy)
            k = min(1.0, (r + 0.7 * s) / d) if d else 0.0
            cx, cy = cx + (tx - cx) * k, cy + (ty - cy) * k
        m = mask.get(map_id)
        near = [(x, y) for x, y in fixed.get(map_id, []) if math.hypot(x - cx, y - cy) < r + 7 * s]
        pts = None
        for dx, dy in _room_steps(s):  # cluster as is, at or just beside the way in, off other pins and on the art
            p = [(cx + dx + ox, cy + dy + oy) for ox, oy in shape]
            if all(math.hypot(x - u, y - v) >= s for x, y in p for u, v in near) and (
                    m is None or all(mask.on(m, x, y, 0.5 * s) for x, y in p)):
                pts = p
                break
        if pts is None:  # no room beside it, so around the other pins there, then onto the art
            p = [(cx + ox, cy + oy) for ox, oy in _room_honeycomb(len(cs), s, [(x - cx, y - cy) for x, y in near])]
            dx, dy = mask.shift(map_id, p, 0.5 * s, 6 * s)
            pts = [(x + dx, y + dy) for x, y in p]
        cs.sort(key=_room_order)
        for c, (x, y) in zip(cs, pts):
            c["x"], c["y"] = round(x, 1), round(y, 1)
            fixed.setdefault(map_id, []).append((c["x"], c["y"]))
    print(f"rooms: {len(placed)} checks of {len(rooms)} rooms at their way in; {moved} other pins moved onto the art")


def _cow_records(proto):
    """({cow location: [map records]}, {cow location: its give flag}) for every cow the songs plugin gives items from.
    The cows come from parity/_marker.cow_spots (the generic groups, KF, GV and the remake-only GF Cow) and the flags
    from data/rando/songs_trade_flags.json. A group of two (the Lon Lon Ranch stable) gives its items in order from
    either cow, so its names go to its two cows in turn. A cow inside a grotto takes the way in of the grotto's other
    checks, meaning a research record of its level within 20 m. Without the game files there's nothing."""
    import math
    try:
        from parity import _marker
        spots_of = _marker.cow_spots()
    except Exception:  # noqa: BLE001 - no game files here: the cows stay in "Other checks"
        return {}, {}
    flags = json.load(open(os.path.join(HERE, "data", "rando", "songs_trade_flags.json"), encoding="utf-8"))["assigned"]
    recs, flag = {}, {}
    for names, _, spots in spots_of:
        rows = []
        for file, hash_, pos, _own in spots:
            level = re.sub(r"_(Static|Dynamic)$", "", os.path.basename(file).split(".")[0]).replace("_Alternative", "")
            near = [r for r in proto if (r.get("level") or "").replace("_Alternative", "") == level and r.get("pos")
                    and math.dist(r["pos"], pos) < 20.0]
            r = {"kind": "npc", "level": level, "hash": str(hash_), "has_flag": False, "pos": pos, "map": "field",
                 "floor": None}
            way = next((x["entrance"] for x in sorted(near, key=lambda x: math.dist(x["pos"], pos)) if x.get("entrance")),
                       None)
            if way:
                r["entrance"] = way
            rows.append(r)
        cows = []  # the group's cows, placements (one per age layout) within 2 m of each other count as one cow
        for r in rows:
            at = (r["pos"][0], r["pos"][2])
            c = next((c for c in cows if math.dist(c[0], at) < 2.0), None)
            if c is None:
                cows.append((at, [r]))
            else:
                c[1].append(r)
        cows.sort(key=lambda c: (-c[0][1], c[0][0]))
        for i, name in enumerate(names):
            if name not in flags:
                continue
            flag[name] = flags[name]
            mine = rows if len(names) == 1 else cows[i % len(cows)][1]
            recs[name] = [dict(r, loc=name) for r in mine]
    return recs, flag


def _kind(name):
    """A check's map kind from its OoTR name, for checks the map research has no record of. Whole words only, since a
    "Silver Rupee Spot" is no pot, "Sheik in Crater" no crate, "ZR Frogs ..." no Gold Skulltula, and "OGC GS" ends in
    one. The gamedb tracker audit found 89 mislabels like that."""
    n = name.lower()
    for pattern, kind in ((r"\bgreat fairy\b", "npc"), (r"\bsong\b", "song"), (r"\bshop\b", "shop"),
                          (r"\bscrubs?\b", "scrub"), (r"\bgs\b", "gs"), (r"\bchests?\b", "chest"),
                          (r"\bsilver rupee\b", "freestanding"),  # OoTR's silver rupees lie on the ground
                          (r"\bpots?\b", "pot"), (r"\bcrates?\b", "crate"), (r"\bbeehives?\b", "beehive"),
                          (r"\bgrass\b", "grass"), (r"\bbush(es)?\b", "bush"), (r"\bfair(y|ies)\b", "fairy"),
                          # the object shuffles' own words ("Deku Tree" is no tree, a "Rocky" name no rock)
                          (r"\bsilver rock\b", "rock_silver"), (r"\bboulder\b", "rock_bombable"),
                          (r"\brock\b", "rock_liftable"), (r"\bred ice\b", "red_ice"), (r"\bicicle\b", "icicle")):
        if re.search(pattern, n):
            return kind
    return "npc"


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("assets", "seed"):
        sys.exit(__doc__)
    if sys.argv[1] == "assets":
        assets(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_ROMFS)
    else:
        for d in sys.argv[2:]:
            seed(d)
