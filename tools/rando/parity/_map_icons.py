"""The map tracker's own icons (rando/native_tracker.py): a picture for each kind of check, made from the game's own
art when the patch is built (parity/_map_icon_art.py), added to the UI's texture archive (_bntx_add.py) and shown
as new frames of the map's facility icon (_map_icon_layout.py).

ICONS is the set, in a fixed order: icon k shows at IconType FIRST + k, so the tracker knows every icon's IconType
without building anything. Each is one of:
  model   a render of the object's own model (pots, rocks, trees, grass, Gossip Stones, cows, hearts, rupees...)
  item    an item icon (UI/Tex/Icon: keys, the Gold Skulltula token, bottles, the magic bean, fish)
  common  a texture of the UI's own archive (the song symbols, the map's heart piece)
  map     one of the map's own icons as it is (the chest, the boss skull): no new texture, just a frame
Every picture gets the map icons' outline and glow (except the map's own ones, which have theirs).

Building them takes a while (renders and ASTC encoding), so each icon's stored bytes are cached in
cache/map_icons/, keyed by its recipe and the bytes of every game file it reads.

  python tools/rando/parity/_map_icons.py sheet OUT.png   every icon on one picture, to look at
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _map_icon_layout as layout  # noqa: E402

BNTX = "UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs"
BLARC = "UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.blarc.zs"
FIRST = layout.FIRST_NEW
CACHE = os.path.join(HERE, "cache", "map_icons")
RECIPE_VERSION = 1  # raise when the art code changes, so cached icons are made again
# (key, recipe). The song symbols are OcarinaMelodyIcon_NN in the game's melody order: Zelda's Lullaby, Epona's,
# Saria's, Sun's, Time, Storms, Scarecrow's, then Minuet, Bolero, Serenade, Nocturne, Requiem, Prelude.
SONGS = ("zelda", "epona", "saria", "sun", "time", "storms", "scarecrow", "minuet", "bolero", "serenade", "nocturne",
         "requiem", "prelude")
ICONS = [
    ("chest", {"map": ("MapIconTreasure_00", "MapIconTreasureSh_00")}),
    ("boss", {"map": ("MapIconBoss_01", "MapIconBossSh_00")}),
    ("pot", {"model": ("Obj_Pot_A", "Obj_Pot_A_01")}),
    # the crate (Obj_BrokenBox_A_01 and its kin draw model Obj_BrokenBox_A_04, whose whole shape isn't in the file:
    # the game builds it from its fracture pieces), built from its own plank texture (crate_face)
    ("crate", {"box": "Obj_BrokenBox_A_04_Alb"}),
    ("beehive", {"model": ("Obj_Kokiri_Beehive_A", "Obj_Kokiri_Beehive_A_01")}),
    ("grass", {"model": ("Obj_Plant_A", "Obj_Plant_Grass_A_02"), "keep": "low_Obj_Plant_Grass", "alpha_test": 0.15}),
    ("tree", {"model": ("Obj_Tree_A", "Obj_Tree_A_01"), "pitch": 8, "alpha_test": 0.05, "close": 9}),
    ("rock", {"model": ("Obj_Rock_A", "Obj_LiftRock_A_01")}),
    ("boulder", {"model": ("Obj_RockBroken_A", "Obj_RockBroken_A_01")}),
    ("icicle", {"model": ("Obj_FallingIcicle_A", "Obj_FallingIcicle_A_02"), "pitch": 5}),
    ("gossip_stone", {"model": ("Obj_GossipStone_A", "Obj_GossipStone_A_01"), "pitch": 10}),
    ("cow", {"model": ("Animal_Cow", "Animal_Cow"), "yaw": -35, "pitch": 12}),
    ("palm_fruit", {"model": ("Obj_Gerudo_PalmFruit_A", "Obj_Gerudo_PalmFruit_A_01")}),
    ("cow_skull", {"model": ("Obj_Gerudo_CowBoneDecoration_A", "Obj_Gerudo_CowBoneDecoration_B_01")}),
    # the Gerudo hanging sign (Obj_Gerudo_HangingSign_B_01: model Obj_Gerudo_HangingSign_B_01, whose shape isn't in its
    # file either) from its own texture: the emblem board over the red cloth (sign_face)
    ("hanging_sign", {"sign": "Land_gerudoValley_FlagSign_A_01_Alb"}),
    ("heart", {"model": ("Obj_Heart", "Obj_Heart"), "yaw": 0, "pitch": 5, "tint": (1.0, 0.22, 0.25)}),
    ("heart_container", {"model": ("Obj_Heart_Container", "Obj_Heart_Container"), "yaw": 0, "pitch": 5,
                         "tint": (1.0, 0.3, 0.3)}),
    ("heart_piece", {"common": "MapIconCollectHeartPiece_00", "outline": False}),
    ("rupee_green", {"item": "Obj_Rupee_Green"}),
    ("rupee_blue", {"item": "Obj_Rupee_Blue"}),
    ("rupee_red", {"item": "Obj_Rupee_Red"}),
    ("rupee_purple", {"item": "Obj_Rupee_Purple"}),
    ("rupee_gold", {"item": "Obj_Rupee_Gold"}),
    ("rupee_silver", {"model": ("Obj_Rupee", "Obj_Rupee_Silver"), "yaw": 0, "pitch": 0}),
    ("gs", {"item": "Item_Token_Gold"}),
    ("key", {"item": "Item_Dungeon_SmallKey"}),
    ("boss_key", {"item": "Item_Dungeon_BossKey"}),
    ("fairy", {"model": ("Obj_Fairy", "Obj_Fairy"), "yaw": 0, "pitch": 10}),   # a free fairy (Obj_Fairy)
    ("bean", {"item": "Item_MagicBean"}),
    ("fish", {"item": "Animal_Fish_Bass"}),
    ("big_poe", {"model": ("Enemy_Poe_Hyrule", "Enemy_Poe_Hyrule"), "yaw": -20, "pitch": 8}),  # the Big Poe itself
] + [(f"song_{s}", {"common": f"OcarinaMelodyIcon_{i:02d}"}) for i, s in enumerate(SONGS)] + [
    ("arrow_fire", {"item": "Item_Arrow_Fire"}),
    ("deku_stick", {"item": "Item_DekuStick"}),
    ("deku_nut", {"item": "Item_DekuNut"}),
    ("deku_seed", {"item": "Item_DekuSeed"}),
    ("scrub", {"item": "Item_ScrubBusinessSeed"}),
    ("letter", {"item": "Item_ZeldaLetter"}),
    ("egg", {"item": "Item_WeirdEgg"}),
    ("ocarina_fairy", {"item": "Item_Ocarina_Fairy"}),
    ("ocarina_time", {"item": "Item_Ocarina_Time"}),
    ("cucco", {"item": "Item_PocketCucco"}),
    ("master_sword", {"item": "Weapon_Sword_Master"}),
    ("light_arrow", {"item": "Item_Arrow_Light"}),
    ("butterfly", {"model": ("Animal_Butterfly", "Animal_Butterfly"), "yaw": 0, "pitch": 70}),
    ("dog", {"model": ("Animal_Dog", "Animal_Dog"), "yaw": -35, "pitch": 12}),
    ("bomb", {"item": "Item_Bomb"}),
    ("blue_fire", {"item": "Item_Bottle_BlueFire"}),
    ("claim_check", {"item": "Item_ClaimCheck"}),
    ("giant_knife", {"item": "Weapon_Sword_Giant"}),
    ("broken_sword", {"item": "Item_BrokenSword"}),
    ("cojiro", {"item": "Item_CojiroCucco"}),
    ("eye_drops", {"item": "Item_EyeDrop"}),
    ("eyeball_frog", {"item": "Item_EyeballFrog"}),
    ("odd_potion", {"item": "Item_OddPowder"}),
    ("poacher_saw", {"item": "Item_PoacherSaw"}),
    ("prescription", {"item": "Item_Prescription"}),
    # the remake's eight pot models (Obj_Pot_A_01 is "pot" above): each pot check shows its own pot
    *[(f"pot_{i}", {"model": ("Obj_Pot_A", f"Obj_Pot_A_0{i}")}) for i in range(2, 9)],
    ("flying_pot", {"model": ("Enemy_FlyingPot", "Enemy_FlyingPot")}),
    ("silver_rock", {"model": ("Obj_LiftRock_B", "Obj_LiftRock_B_01")}),
    ("ice_pillar", {"model": ("Obj_BrokenIcePillar_A", "Obj_BrokenIcePillar_A_02"), "pitch": 10}),
    ("red_ice", {"model": ("Obj_RedIce_A", "Obj_RedIce_A_01"), "tint": (1.0, 0.28, 0.25)}),
    ("ruto_letter", {"item": "Item_Bottle_Letter"}),
    ("gerudo_card", {"item": "Item_Token_Gerudo"}),
]
# The map's own pictures, by IconType (1-38: the layout's Type animation, read back by verify). A check of ours that
# shows one of them gets a copy at an IconType of its own ("game_<type>", and "npc" for the people's bazaar bag), so a
# map switch (HIDE_GROUPS) hiding our icons never hides the game's own markers, and the other way round.
GAME_PICTURES = {t: (f"MapIcon{n}_{i:02d}", f"MapIcon{n}Sh_{i:02d}") for t, n, i in (
    (1, "ShopMask", 0), (2, "ShopMask", 0), (3, "Training", 0), (4, "ShopBombchu", 0), (5, "MiniGameDampe", 1),
    (6, "MiniGameFrog", 0), (7, "MiniGameArchery", 0), (8, "MiniGameCocco", 0), (9, "MiniGameEpona", 0),
    (10, "MiniGameEpona", 0), (11, "GreatFairy", 0), (12, "GreatFairy", 0), (13, "KokiriShop", 0), (14, "GoronShop", 0),
    (15, "ZolaShop", 0), (16, "ShopMedicine", 0), (17, "ShopMedicine", 0), (18, "ShopGeneral", 0),
    (19, "ShopGeneral", 0), (20, "MiniGameTarget", 0), (21, "MiniGameTarget", 0), (22, "MiniGameBowling", 0),
    (23, "ShopTreasure", 0), (24, "Sign", 0), (25, "Sign", 0), (26, "MiniGameDampe", 0), (27, "MiniGameDiving", 0),
    (28, "MiniGameFishing", 0), (29, "Obaba", 0), (30, "GhostShop", 0), (31, "SkullKid", 0), (32, "RunningRace", 0),
    (33, "SurfaceFair", 0), (34, "MagicBean", 0), (35, "Carpenter", 0), (36, "Carpenter", 1), (37, "Carpenter", 2),
    (38, "Carpenter", 3))}
ICONS += [("npc", {"map": GAME_PICTURES[18]})] + [(f"game_{t}", {"map": p}) for t, p in sorted(GAME_PICTURES.items())]


def game_key(t, kind=None):
    """Our icon showing the map's own picture of IconType t: the people's bag ("npc") for a person (anything but a shop
    at the bazaar's picture), else that picture's copy."""
    return "npc" if t == 18 and kind != "shop" else f"game_{t}"


# The map switches in Longshot's Insert menu (the Mods tab, under the mod): each hides one group of the tracker's
# icons, and the last one the game's own markers (_native_tracker_code.cheats). Every icon of ours is in one group.
SHOPS = (1, 2, 4, 13, 14, 15, 16, 17, 18, 19, 29, 30)
HIDE_GROUPS = [
    ("Gossip Stones (Sheikah Stones)", ["gossip_stone"]),
    ("pots", ["pot"] + [f"pot_{i}" for i in range(2, 9)] + ["flying_pot"]),
    ("crates", ["crate"]),
    ("grass and bushes", ["grass"]),
    ("rocks and boulders", ["rock", "boulder", "silver_rock"]),
    ("trees", ["tree"]),
    ("beehives", ["beehive"]),
    ("ice (icicles, red ice, ice pillars)", ["icicle", "red_ice", "ice_pillar"]),
    ("rupees", ["rupee_green", "rupee_blue", "rupee_red", "rupee_purple", "rupee_gold"]),
    ("silver rupees", ["rupee_silver"]),
    ("hearts and heart pieces", ["heart", "heart_piece", "heart_container"]),
    ("Gold Skulltulas", ["gs"]),
    ("chests", ["chest"]),
    ("fairies, fountains and bean spots", ["fairy", "butterfly", "bean", "game_11", "game_12"]),
    ("songs and song spots", [f"song_{s}" for s in SONGS]),
    ("cows", ["cow"]),
    ("scrubs", ["scrub", "deku_stick", "deku_nut", "deku_seed"]),
    ("fish", ["fish"]),
    ("Big Poes", ["big_poe"]),
    ("shop items", [f"game_{t}" for t in SHOPS]),
    ("minigames and rewards", [f"game_{t}" for t in GAME_PICTURES if t not in SHOPS + (11, 12)]),
    ("people, trades and gifts", ["npc", "letter", "egg", "ocarina_fairy", "ocarina_time", "cucco", "master_sword",
                                  "light_arrow", "arrow_fire", "dog", "bomb", "blue_fire", "claim_check", "giant_knife",
                                  "broken_sword", "cojiro", "eye_drops", "eyeball_frog", "odd_potion", "poacher_saw",
                                  "prescription", "ruto_letter", "gerudo_card", "key", "boss_key"]),
    ("bosses", ["boss"]),
    ("Gerudo signs, palm fruit and skulls", ["hanging_sign", "palm_fruit", "cow_skull"]),
]
GAME_MARKERS = "the game's own markers (shops, minigames, Great Fairies)"  # IconType 1-38, the game's own records
FOUNTAIN_KEY = "@fountain"  # in BY_ACTOR: the map's own fairy fountain picture (FOUNTAIN)
# The picture of each object a check sits on (research record "actor"), then of each check kind.
BY_ACTOR = {"Obj_Rupee_Green": "rupee_green", "Obj_Rupee_Blue": "rupee_blue", "Obj_Rupee_Red": "rupee_red",
            "Obj_Rupee_Purple": "rupee_purple", "Obj_Rupee_Gold": "rupee_gold", "Obj_Rupee_Silver": "rupee_silver",
            "Obj_Heart_Piece": "heart_piece", "Obj_GerudoValley_Heart_Piece": "heart_piece", "Obj_Heart": "heart",
            "Obj_Heart_InWater": "heart", "Obj_Heart_Container": "heart_container", "Obj_Dungeon_SmallKey": "key",
            "Obj_Arrow_Fire": "arrow_fire", "Obj_DekuStick": "deku_stick", "Obj_DekuNut": "deku_nut",
            "Obj_DekuSeed": "deku_seed", "Obj_GossipStone_A_01": "gossip_stone", "Obj_SmallFarm_A_01": "bean",
            "Obj_SmallFarm_A_02": "bean", "Obj_Gerudo_PalmFruit_A_01": "palm_fruit",
            "Obj_Gerudo_HangingSign_B_01": "hanging_sign",
            **{f"Obj_Pot_A_0{i}": f"pot_{i}" for i in range(2, 9)}, "Obj_Pot_A_01": "pot",
            "Enemy_FlyingPot_SpiritTemple": "flying_pot", "Enemy_FlyingPot_ShadowTemple": "flying_pot",
            "Enemy_FlyingPot_IceCavern": "flying_pot", "Obj_LiftRock_B_01": "silver_rock",
            **{f"Obj_BrokenIcePillar_A_0{i}": "ice_pillar" for i in range(1, 5)},
            "Obj_FallingIcicle_A_01": "icicle", "Obj_FallingIcicle_A_02": "icicle",
            "Obj_RedIce_A_01": "red_ice", "Obj_RedIce_A_04": "red_ice", "Obj_Fairy": "fairy",
            "Animal_ButterflyToFairy": "butterfly", "Obj_Fairy_HidingHole_FairyFountain": FOUNTAIN_KEY}
BY_KIND = {"chest": "chest", "pot": "pot", "flying_pot": "pot", "crate": "crate", "beehive": "beehive",
           "icicle": "icicle", "red_ice": "icicle", "grass": "grass", "bush": "grass", "tree": "tree",
           "rock_liftable": "rock", "rock_bombable": "boulder", "rock_silver": "boulder", "fairy": "fairy",
           "gs": "gs", "boss_heart": "heart_container", "freestanding": "rupee_green", "cow": "cow", "fish": "fish"}


FOUNTAIN = {"type": 11}  # the map's own fairy fountain picture (MapIconGreatFairy_00)
# What a check is about, by its name, before the object it sits on or its kind: the song that opens a grotto or calls
# a fairy, a fairy fountain, the item a trade takes, what an NPC wants from you. (pattern, icon key or map picture)
BY_NAME = [
    (r"\bStorms Grotto\b", "song_storms"),            # everything in a grotto the Song of Storms opens
    (r"\b(Storms|Oasis) Fairy\b", "song_storms"),     # fairies the Song of Storms calls
    (r"\bSun Fairy\b", "song_sun"),                   # fairies the Sun's Song calls
    (r"\bButterfly Fairy\b", "butterfly"),
    (r"\b(Fairy Grotto|Scrubs) Fairy\b", FOUNTAIN),     # a fairy fountain (the Shield Grave's are free fairies)
    (r"^LH Underwater Item$", "ruto_letter"),           # Ruto's Letter, in its bottle
    (r"^Hideout Gerudo Membership Card$", "gerudo_card"),
    (r"\bTrade Eyeball Frog$", "eyeball_frog"),
    (r"\bTrade Broken Sword$", "broken_sword"),
    (r"\bTrade Eyedrops$", "eye_drops"),
    (r"\bTrade Poachers Saw$", "poacher_saw"),
    (r"\bTrade Cojiro$", "cojiro"),
    (r"\bTrade Odd Potion$", "odd_potion"),
    (r"\bTrade Prescription$", "prescription"),
    (r"^DMT Biggoron$", "claim_check"),                 # the Claim Check gets you his sword
    (r"^GC Darunias Joy$", "song_saria"),               # play Saria's Song for him
    (r"^GC Rolling Goron as (Child|Adult)$", "bomb"),   # a bomb stops him
    (r"^GC Medigoron$", "giant_knife"),                 # he sells the Giant's Knife
    (r"^Market Lost Dog$", "dog"),
    (r"^ZD King Zora Thawed$", "blue_fire"),            # Blue Fire thaws him
]


def icon_for_name(name):
    """The icon a check gets by its name (BY_NAME): an icon key, a map picture {"type": n}, or None."""
    for pattern, icon in BY_NAME:
        if re.search(pattern, name or ""):
            return icon
    return None


def icon_for(actor, kind, name=""):
    """The icon key of a check: by the object it's on, then its kind (None: no icon of ours fits)."""
    if actor in BY_ACTOR:
        return FOUNTAIN if BY_ACTOR[actor] == FOUNTAIN_KEY else BY_ACTOR[actor]
    if (actor or "").startswith("Obj_Gerudo_CowBoneDecoration"):
        return "cow_skull"
    if "Silver Rupee Spot" in name:
        return "rupee_silver"
    if name.endswith(" Cow") or " Cow " in name:
        return "cow"
    return BY_KIND.get(kind)
KEYS = [k for k, _ in ICONS]
if len(set(KEYS)) != len(KEYS):
    raise RuntimeError("two map icons share a key")


def icon_type(key):
    """The IconType showing icon `key`."""
    return FIRST + KEYS.index(key)


def hide_types():
    """[(switch name, [IconType])]: HIDE_GROUPS, then the game's own markers (IconType 1-38). Every icon of ours is in
    exactly one group (a new icon has to be given one)."""
    grouped = [k for _, keys in HIDE_GROUPS for k in keys]
    if sorted(grouped) != sorted(KEYS):
        raise RuntimeError(f"map switches: icons in no group {sorted(set(KEYS) - set(grouped))}, unknown or twice "
                           f"{sorted({k for k in grouped if k not in KEYS or grouped.count(k) > 1})}")
    return [(name, [icon_type(k) for k in keys]) for name, keys in HIDE_GROUPS] + [(GAME_MARKERS, list(range(1, 39)))]


def texture_names(key):
    """(picture, glow) texture names of icon `key`."""
    spec = dict(ICONS)[key]
    if "map" in spec:
        return tuple(spec["map"])
    base = "RandoMapIcon_" + "".join(w.title() for w in key.split("_"))
    return base + "_00", base + "Sh_00"


def _sources(spec):
    """The game files a recipe reads."""
    if "model" in spec:
        return [f"Model/{spec['model'][0]}.{spec['model'][1]}.bfres.zs"]
    if "box" in spec or "sign" in spec:
        return [f"Tex/{spec.get('box') or spec['sign']}.bntx.zs"]
    if "item" in spec:
        return [f"UI/Tex/Icon/{spec['item']}.bntx.zs"]
    if "common" in spec:
        return [BNTX]
    return []


def _picture(fs, spec, common=None):
    """The icon's picture before styling (PIL RGBA)."""
    import _map_icon_art as art
    if "model" in spec:
        kw = {k: spec[k] for k in ("yaw", "pitch", "keep", "alpha_test") if k in spec}
        img = art.render(fs, spec["model"][0], spec["model"][1], **kw)
        return art.lift(img, close=spec.get("close", 0), tint=spec.get("tint"))
    if "item" in spec:
        return art.decode(fs.read(f"UI/Tex/Icon/{spec['item']}.bntx.zs"))
    if "sign" in spec:
        import numpy as np
        alb = np.asarray(art.decode(fs.read(f"Tex/{spec['sign']}.bntx.zs")), dtype=np.float64) / 255.0
        face = art.sign_face(alb)
        return art.lift(art.render_box(face, yaw=-20, pitch=8, dims=(1.0, face.shape[0] / face.shape[1], 0.08),
                                       side=face[:8]))
    if "box" in spec:
        import numpy as np
        alb = np.asarray(art.decode(fs.read(f"Tex/{spec['box']}.bntx.zs")), dtype=np.float64) / 255.0
        return art.lift(art.render_box(art.crate_face(alb)))
    return art.decode(common if common is not None else fs.read(BNTX), spec["common"])


def _cache_key(fs, key, spec):
    h = hashlib.sha1(json.dumps([RECIPE_VERSION, key, spec], sort_keys=True).encode())
    for rel in _sources(spec):
        if rel == BNTX:
            h.update(b"common")  # the UI archive is too big to hash every time; the recipe names its texture
        else:
            h.update(hashlib.sha1(fs.read(rel)).digest())
    return h.hexdigest()


def stored(fs, key, common=None):
    """(picture bytes, glow bytes) of icon `key` as the textures store them (ASTC / BC4, block-linear)."""
    import _map_icon_art as art
    spec = dict(ICONS)[key]
    ck = _cache_key(fs, key, spec)
    path = os.path.join(CACHE, f"{key}-{ck}.bin")
    if os.path.exists(path):
        raw = open(path, "rb").read()
        return raw[:16384], raw[16384:]
    pic, glow = art.style(_picture(fs, spec, common), outline=spec.get("outline", True))
    out = art.encode_picture(pic), art.encode_glow(glow)
    os.makedirs(CACHE, exist_ok=True)
    tmp = path + ".tmp"
    open(tmp, "wb").write(out[0] + out[1])
    os.replace(tmp, path)
    return out


def build(fs, files=None):
    """{romfs path: new decompressed bytes}: the UI texture archive with every icon's textures added, and the layout
    archive with their frames. `files` holds the same files as another step already changed them (the HUD colours),
    which these changes go on top of."""
    import _bntx_add as add
    files = files or {}
    common = files.get(BNTX) or fs.read(BNTX)
    new, pairs = [], []
    for key, spec in ICONS:
        names = texture_names(key)
        pairs.append(names)
        if "map" in spec:
            continue
        pic, glow = stored(fs, key, common)
        new += [(names[0], "MapIconKokiriShop_00", pic), (names[1], "MapIconKokiriShopSh_00", glow)]
    out_bntx = add.add_textures(common, new)
    from _cosmetics_hud import sarc_entries
    blarc = files.get(BLARC) or fs.read(BLARC)
    copies = {blarc[s:e] for n, s, e in sarc_entries(blarc) if n == layout.LAYOUT}
    if len(copies) != 1:
        raise ValueError(f"{layout.LAYOUT}: its copies in the archive differ")
    buil = layout.add_pictures(copies.pop(), pairs)
    return {BNTX: out_bntx, BLARC: layout.sarc_replace(blarc, layout.LAYOUT, buil)}


def verify(patch, romfs):
    """[problem] reading the icons back from a built patch: every IconType's frame shows its pair, and every texture
    it names is in the texture archive with the template's size and format."""
    from romtools import Romfs
    import _bntx_add as add
    from _cosmetics_hud import sarc_entries
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    blarc = fs.read(BLARC)
    shown = None
    for n, s, e in sarc_entries(blarc):
        if n == layout.LAYOUT:
            pics = layout.read_pictures(blarc[s:e])
            if shown is not None and pics != shown:
                bad.append(f"{layout.LAYOUT}: its copies show different pictures")
            shown = pics
    if shown is None:
        return [f"{layout.LAYOUT}: not in the archive"]
    common = fs.read(BNTX)
    bad += [f"{BNTX}: {x}" for x in add.check(common)]
    have = {n.decode(): b for n, b in add.textures(common)}
    for key in KEYS:
        t = icon_type(key)
        want = texture_names(key)
        if shown.get(t) != want:
            bad.append(f"icon {key}: IconType {t} shows {shown.get(t)}, not {want}")
        for name in want:
            if name not in have:
                bad.append(f"icon {key}: no texture {name}")
    return bad


def sheet(fs, out):
    """Every icon on one picture: picture over glow, full size and minimap size."""
    import _map_icon_art as art
    from PIL import Image, ImageDraw
    cols = 8
    rows = -(-len(ICONS) // cols)
    im = Image.new("RGBA", (cols * 150, rows * 170), (120, 110, 90, 255))
    dr = ImageDraw.Draw(im)
    common = fs.read(BNTX)
    for i, (key, spec) in enumerate(ICONS):
        if "map" in spec:
            pic = art.decode(common, spec["map"][0])
            glow = art.decode(common, spec["map"][1]).getchannel("A")
        else:
            pic, glow = art.style(_picture(fs, spec, common), outline=spec.get("outline", True))
        tile = Image.new("RGBA", (128, 128), (255, 255, 255, 0))
        white = Image.new("RGBA", (128, 128), (255, 255, 255, 255))
        white.putalpha(glow.resize((128, 128)))
        tile.alpha_composite(white)
        tile.alpha_composite(pic.resize((128, 128)))
        x, y = (i % cols) * 150 + 10, (i // cols) * 170 + 4
        im.alpha_composite(tile, (x, y))
        im.alpha_composite(tile.resize((40, 40), Image.LANCZOS), (x + 100, y + 120))
        dr.text((x, y + 132), f"{icon_type(key)} {key}"[:20], fill=(255, 255, 255, 255))
    im.save(out)


if __name__ == "__main__":
    from romtools import Romfs, longshot_romfs
    if len(sys.argv) == 3 and sys.argv[1] == "sheet":
        sheet(Romfs(longshot_romfs(), os.path.join(HERE, "original")), sys.argv[2])
    else:
        sys.exit(__doc__)
