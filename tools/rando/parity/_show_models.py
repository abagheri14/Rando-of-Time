"""Item models for OoTR items the remake has no model for: the twelve songs (a music note in the song's colour), the
five Ocarina note items (a gold button labelled with the button that plays the note in the remake, for the player's
controller), and the Master Sword (its own model, standing). The hold-up displays that show them are made elsewhere
(the hold-up display builder, Rando_Show_*). This module gives each display its model: plan(display).

What the game has (I surveyed it): no note model in Model/ (6,464 files searched
for note, melody, music and button names). The only 3D note anywhere is the scarecrows' straw note, a particle mesh
(Effect Npc_Bonooru / Npc_Pierre / static: Symbol_Note_Straw_Mesh_00, 189 vertices, a lumpy straw bundle and a flat
one-sided stem). The ocarina's own note effects are rings and planes with symbol textures. So we build the note and
the buttons here, in the shape OoT's song item has (object_gi_melody, an eighth note) and the button shapes OoT's
quest screen and Ship of Harkinian's ocarina-button items use, coloured the way OoT colours them:
  - songs: OoT's quest screen (decomp z_kaleido_collect.c sSongsPrim*) has Minuet (150, 255, 100), Bolero (255, 80,
    40), Serenade (100, 150, 255), Requiem (255, 160, 0), Nocturne (255, 100, 255) and Prelude (255, 240, 100).
    Zelda's Lullaby, Epona's Song, Saria's Song, Sun's Song, Song of Time and Song of Storms are white there, so
    they take Ship of Harkinian's song-note tints instead (SONG_COLOURS).
  - Ocarina note items: the remake plays the five notes on Switch buttons, not the N64's A and C buttons (its
    Options "Ocarina controls": Normal (two-handed) L R Y X A, Classic (one-handed) R B Y X A; NOTE_PITCH,
    OCARINA_CONTROLS). Each item shows that button in gold (my pick), with its label raised and dimmer. A, B, X and
    Y are discs, and L and R are the remake's slanted slabs (its OcarinaButtonL/R icons), named for the player's
    controller by position (CONTROLLERS: Nintendo, Xbox, PlayStation). The seed's remake_ocarina_controls and
    remake_controller choose (plan(display, romfs, controls, controller)).

How: the same technique as the Triforce piece (parity/_gaps_triforce_model.py), a same-size copy of a game model
with checked same-size byte edits through make_patch "new_files".
  - DONOR is the fire arrow's model. Its metal material (Mt_Item_Arrow_Metal) is in the shader graph whose glow is
    the _Emm mask x ns_param_color5 x ns_emission_intensity (the relief and the fire arrow differ only there), and
    its metal shape has room (5,350 vertices; LODs of 11,814 / 5,496 / 2,430 indices). The copy keeps every
    pointer. The edits write the item's vertices into the metal shape's first slots (positions, normals, tangents,
    UVs, and the donor's bone index), its triangles into each of the three LOD meshes (count and sub-mesh set,
    first vertex 0, so every LOD shows the same item), and the shape's bounding boxes and sphere. The fire crystal
    shape draws one degenerate triangle (count 3, indices 0) in each LOD. The glow colour and strength get written
    too.
  - The glow mask. The donor's own mask is dark (at most 0.43, and only on the crystal), so each copy names MASK
    instead (a same-length rename of its _Emm slot). That's a new texture, a copy of MASK_SRC (a small 85 x 85
    single-channel mask whose name has the same length) under the new name, with every block set by MASK_BANDS:
    three bands across u (1.0, 0.75, 0.30).
  - UVs. Every vertex of a part samples one point (PART_UV: a button's body and label, a note's rim and faces), so
    its colour is even and the texture is always read at full resolution (no UV change across a triangle, so no
    mip). Every point is in a neutral patch of the donor's textures (grey base colour 0.26-0.31, not metal, ambient
    occlusion 1.0, flat normal) and in its mask band. The note's points are the glossiest (roughness about 0.2) so
    the shading shows highlights. Its rim, stem and flag glow at full strength, and its head's faces at 75%.
  - Names: FmdbName per item (15 characters, like the donor's), project Item_Arrow_Fire. The bones are Root (the
    one the item animations turn) and its child Skl_Root, the shapes' rigid bone.
Every model is a new file, and no game file is changed (the donor model, its textures and MASK_SRC stay as they
are).
"""
import functools
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
import res_dict  # noqa: E402  tools/rando/res_dict.py: the name dictionaries a renamed copy must keep findable

DONOR_PROJECT = "Item_Arrow_Fire"
DONOR = f"Model/{DONOR_PROJECT}.{DONOR_PROJECT}.bfres.zs"
BODY_SHAPE = "Base_Feather_1__Mt_Item_Arrow_Metal"
EMPTY_SHAPE = "Fire_Stone_Crystal__Mt_Item_Arrow_Fire"
GLOW_MATERIAL = "Mt_Item_Arrow_Metal"
DONOR_MASK = "Mt_Item_Arrow_Fire_Emm"
MASK_SRC_NAME = "Obj_EyeSwitch_Body_Emm"
MASK_SRC = f"Tex/{MASK_SRC_NAME}.bntx.zs"
MASK = "Rando_ShowItem_All_Emm"
MASK_FILE = f"Tex/{MASK}.bntx.zs"
MASK_BANDS = ((0.34, 255), (0.67, 191), (2.0, 77))  # (u below, BC4 value): rims 1.0, faces 0.75, button labels 0.30
# every vertex of a part samples one point (parts: 0 button body, 1 button label, 2 note rim, 3 note face). Each
# point is in a neutral patch of the donor's textures (grey base colour 0.26-0.31, not metal, ambient occlusion 1.0,
# flat normal) and in its glow band. The notes' two are the glossiest (roughness about 0.2, so real highlights), and
# the buttons' are about 0.3.
BODY_UV = (0.1201, 0.9072)  # band 1: base 0.30, roughness 0.30
GLYPH_UV = (0.8955, 0.8682)  # band 3: base 0.30, roughness 0.29
NOTE_RIM_UV = (0.0713, 0.8486)  # band 1: base 0.27, roughness 0.18
NOTE_FACE_UV = (0.5830, 0.8408)  # band 2: base 0.28, roughness 0.22
PART_UV = (BODY_UV, GLYPH_UV, NOTE_RIM_UV, NOTE_FACE_UV)
VERTEX_FORMATS = {"_p0": (0x1505, 0), "_n0": (0x0E02, 8), "_t0": (0x0E02, 12), "_u0": (0x1201, 16),
                  "_i0": (0x0203, 20)}
GLOW_PARAMS = {"ns_emission_intensity": (0xF686DFDEF5207CB8, 12), "ns_param_color5": (0xF98173481C0CBF24, 15)}

if len(MASK) != len(DONOR_MASK) or len(MASK_SRC_NAME) != len(MASK):
    raise RuntimeError("the mask's name must keep the donor slot's and the source texture's length")


def mask_value(u):
    """The glow mask's BC4 value at u (MASK_BANDS)."""
    return next(v for edge, v in MASK_BANDS if u < edge)


def _lin(c):
    """sRGB 0-255 -> linear 0-1 (material colours are linear)."""
    x = c / 255.0
    return round(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4, 4)


SONG_COLOURS = {  # sRGB. The six warp songs take OoT's quest screen colours (decomp z_kaleido_collect.c sSongsPrim*).
    # The other six are white there, and in game they read as plain white notes (Saria's Song, Song of Storms), so
    # they take Ship of Harkinian's song-note tints instead (soh Enhancements/randomizer GetItem_DrawGenericMusicNote
    # kNoteTints: Zelda's Lullaby purple, Epona's Song orange, Saria's Song green, Sun's Song yellow, Song of Time
    # light blue, Song of Storms grey).
    "Minuet": (150, 255, 100), "Bolero": (255, 80, 40), "Serenade": (100, 150, 255), "Requiem": (255, 160, 0),
    "Nocturne": (255, 100, 255), "Prelude": (255, 240, 100), "Zelda": (109, 73, 143), "Epona": (217, 110, 48),
    "Saria": (62, 109, 23), "Sun": (237, 231, 62), "Time": (98, 177, 211), "Storm": (146, 146, 146)}
# Ocarina note items (OoTR's shuffle_individual_ocarina_notes: "Ocarina A Button", "Ocarina C up Button", ...). Each
# shows the button that plays its note in the remake, labelled for the player's controller.
# This is read from the game's code (main = 0x80020000 +
# offset in work/sa/image/image.bin). The ocarina manager turns the pressed button into a note at m+0x3293E70: L
# (0x2000) -> 4 (D4), R (0x4000) -> 7 (F4), A (1) -> 11 (A4), Y (0x10) -> 13 (B4), X (8) -> 16 (D5). With the
# one-handed option R plays the D (0x4000 -> 4) and B (2) the F (two flags it reads, m+0x4E6C808 / 80C). Its finger
# animations agree (m+0x28946D0, table m+0x3EEA60C: note 7 Ocarina_Finger_R, 11 _A, 13 _Y, 16 _X, the rest _L). So
# the face buttons sit where the N64's C buttons sat: Y left = C-left, X top = C-up, A right = C-right (and B bottom =
# C-down when one-handed). OptionData.OcarinaKeyAssign is "Game" (the default: Normal, two-handed) or "Performance"
# (Classic, one-handed; m+0x3291C90 tests it). Other controllers get labels by position.
NOTE_PITCH = {"Rando_Show_OcaA": "D4", "Rando_Show_OcaCDown": "F4", "Rando_Show_OcaCRight": "A4",
              "Rando_Show_OcaCLeft": "B4", "Rando_Show_OcaCUp": "D5"}
OCARINA_CONTROLS = {"normal": {"D4": "L", "F4": "R", "A4": "A", "B4": "Y", "D5": "X"},
                    "classic": {"D4": "R", "F4": "B", "A4": "A", "B4": "Y", "D5": "X"}}
CONTROLLERS = {"nintendo": {},
               "xbox": {"A": "B", "B": "A", "X": "Y", "Y": "X", "L": "LB", "R": "RB"},
               "playstation": {"A": "Circle", "B": "Cross", "X": "Triangle", "Y": "Square", "L": "L1", "R": "R1"},
               "steamdeck": {"A": "B", "B": "A", "X": "Y", "Y": "X", "L": "L1", "R": "R1"}}  # Xbox letters, L1/R1
# "auto" means the controller Longshot shows prompts for. It's read when the seed is made (resolve_controller) and
# written into the seed (plan["_show_models"], settings_used.json), so a seed always rebuilds the same. Longshot's
# prompt sets (builds/rc/prompts/<set>) -> ours, and keyboard and anything unknown map to nintendo.
PROMPT_SETS = {"switch": "nintendo", "xbox": "xbox", "ps4": "playstation", "ps5": "playstation",
               "steamdeck": "steamdeck", "keyboard": "nintendo"}
LONGSHOT_BUILD = os.environ.get("LONGSHOT_BUILD") or os.path.dirname(__import__("romtools").longshot_romfs())
# the randomizer settings choosing them (parity/songs_trade.py declares them and writes plan["_show_models"])
REMAKE_SETTINGS = {"remake_ocarina_controls": tuple(OCARINA_CONTROLS),
                   "remake_controller": ("auto",) + tuple(CONTROLLERS)}
REMAKE_DEFAULTS = {"remake_ocarina_controls": "normal", "remake_controller": "auto"}
UI = {"remake_ocarina_controls": ("Controls", "Ocarina controls",
                                  {"normal": "Normal (two-handed)", "classic": "Classic (one-handed)"},
                                  "As in the game's Options. Ocarina note items show the button that plays their "
                                  "note."),
      "remake_controller": ("Controls", "Controller",
                            {"auto": "Auto (the controller Longshot is using)",
                             "nintendo": "Nintendo (A B X Y, L R)", "xbox": "Xbox (A B X Y, LB RB)",
                             "playstation": "PlayStation (cross circle square triangle, L1 R1)",
                             "steamdeck": "Steam Deck (A B X Y, L1 R1)"},
                            "The button labels Ocarina note items show.")}
# label -> (shape, glyphs, FmdbName code): face buttons are discs, shoulder buttons the remake's slanted slabs
BUTTON_MODELS = {"A": ("face", ["A"], "A_"), "B": ("face", ["B"], "B_"), "X": ("face", ["X"], "X_"),
                 "Y": ("face", ["Y"], "Y_"), "L": ("shoulder_l", ["L"], "L_"), "R": ("shoulder_r", ["R"], "R_"),
                 "LB": ("shoulder_l", ["L", "B"], "LB"), "RB": ("shoulder_r", ["R", "B"], "RB"),
                 "L1": ("shoulder_l", ["L", "1"], "L1"), "R1": ("shoulder_r", ["R", "1"], "R1"),
                 "Cross": ("face", ["Cross"], "Cr"), "Circle": ("face", ["Circle"], "Ci"),
                 "Square": ("face", ["Square"], "Sq"), "Triangle": ("face", ["Triangle"], "Tr")}
BUTTON_FMDB = "Rando_OcaBtn_"  # + the code: 15 characters, the donor's length
BUTTON_COLOUR = (255, 255, 50)  # gold (OoT's C buttons; my pick for every button)
GLOW_LUMINANCE = 0.7  # each item's glow strength makes its glow this bright (linear luminance) at the mask's 1.0
GLOW_PEAK = 1.3  # but its brightest channel at most this. A deep red or blue pushed to 0.7 luminance (strength 2-2.5)
# goes past what the tone mapping keeps in hue and reads pale (Bolero peach, Serenade sky blue). White, Minuet,
# Prelude and the gold buttons stay below it (strengths 0.7-0.89).

# display (hold-up display builder's name) -> (kind, key, FmdbName: 15 characters, the donor's length)
SONG_CODES = {"Minuet": "Minu", "Bolero": "Bole", "Serenade": "Sere", "Requiem": "Requ", "Nocturne": "Noct",
              "Prelude": "Prel", "Zelda": "Zeld", "Epona": "Epon", "Saria": "Sari", "Sun": "SunS", "Time": "Time",
              "Storm": "Stor"}
DISPLAYS = {f"Rando_Show_Song{k}": ("song", k, f"Rando_Song_{SONG_CODES[k]}") for k in SONG_COLOURS}
DISPLAYS.update({d: ("button", pitch, None) for d, pitch in NOTE_PITCH.items()})  # (model: by label, button_label)
# The Master Sword uses its own model (Weapon_Sword_Master) with the display pose baked in. The sword actors' models
# lie along +Z (tip), centred on bone Skl_Root (rest at z 0.445, and the vertices are Skl_Root's). The sword displays
# (Item_Sword_Kokiri, Item_Sword_Giant) stand them up with their own Pose_Common on Skl_Root (Kokiri: scale 1.05,
# turned -100, -10, -40 degrees; Biggoron: 0.8). There's no Weapon_Sword_Master_Animation, and with no pose playing
# (an item look on the ground) a sword lies flat and spins like a 1.3 m propeller. So the copy's vertices get turned
# tip up, (x, y, z) -> (x, z, -y) with the crossguard across and the flat to the front, then scaled SWORD_SCALE and
# centred, with Skl_Root's rest offset zeroed. That way it shows upright and centred on the ground, in chests and
# held up alike, with the item animation set every holdable display uses (Item_Common_Animation +
# Obj_Token_Gold_Animation: Root turns, Skl_Root stays identity). Don't use a sword pose set
# (Weapon_Sword_*_Animation) with it, it would turn it again.
SWORD_PROJECT = "Weapon_Sword_Master"
SWORD_DONOR = f"Model/{SWORD_PROJECT}.{SWORD_PROJECT}.bfres.zs"
SWORD_SHAPES = {"Blade_Mark__Mt_Weapon_Sword_Master_Metal", "Grip_Coart__Mt_Weapon_Sword_Master_Coat",
                "Grip__Mt_Weapon_Sword_Master"}
SWORD_BONE = "Skl_Root"
SWORD_SCALE = 0.75  # 1.31 m -> 0.98 m upright (the vanilla Giant's Knife display shows its 2.1 m sword at 0.8)
DISPLAYS["Rando_Show_MasterSword"] = ("sword", "Master", "Rando_MasterSwordUp")
# The souls (extras_souls: Ship of Harkinian's boss souls, Ganon's soul, bean souls). Each shows its own enemy the
# way the Hall of Fallen Foes shows it, with the enemy's own materials and textures. parity/_soul_figures.py builds
# each figure: a smaller copy of the boss's own model with the museum's pose, visibility and material anims baked in,
# and its textures from smaller mips. Baking them into the fire arrow's glow material in one colour didn't work, they
# didn't look like real models at all. Bean souls show the magic bean itself (config/hold_up.json
# Rando_Show_SoulBean: model_from Item_MagicBean, its own model and textures).
# soul key -> (display, the figure's FmdbName or None for a display whose model is a game actor's, config "model_from")
SOUL_DISPLAYS = {"gohma": ("Rando_Show_SoulGohma", "Rando_DungeonBoss_Gohma"),
                 "king_dodongo": ("Rando_Show_SoulDodongo", "Rando_DungeonBoss_Dodongo"),
                 "barinade": ("Rando_Show_SoulBarinade", "Rando_DungeonBoss_Barinade"),
                 "phantom_ganon": ("Rando_Show_SoulPhantom", "Rnd_DungeonBoss_PhantomGanon"),
                 "volvagia": ("Rando_Show_SoulVolvagia", "Rando_DungeonBoss_Volvagia"),
                 "morpha": ("Rando_Show_SoulMorpha", "Rando_DungeonBoss_Morpha"),
                 "bongo_bongo": ("Rando_Show_SoulBongo", "Rando_DungeonBoss_BongoBongo"),
                 "twinrova": ("Rando_Show_SoulTwinrova", "Rando_DungeonBoss_Twinrova"),
                 "ganon": ("Rando_Show_SoulGanon", "Rando_DungeonBoss_Ganon"),  # the beast (my call)
                 "bean": ("Rando_Show_SoulBean", None)}
def _enemy_soul_displays():
    """{"enemy_<Family>": (display, figure FmdbName)} of the regular-enemy souls (data/rando/extras_enemy_souls.json)."""
    import json as _json
    path = os.path.join(HERE, "data", "rando", "extras_enemy_souls.json")
    if not os.path.exists(path):
        return {}
    fams = _json.load(open(path, encoding="utf-8"))["families"]
    return {"enemy_" + k: (e["display"], e["figure"]["figure_fmdb"]) for k, e in fams.items() if e.get("display")}


_enemy_shows = _enemy_soul_displays()
# a shared name would make two souls one display (King Dodongo's and the Dodongo's once did)
for _k, (_d, _f) in _enemy_shows.items():
    if any(_d == d or _f == f for d, f in SOUL_DISPLAYS.values()):
        raise RuntimeError(f"{_k}: display {_d} or figure {_f} is another soul's")
SOUL_DISPLAYS.update(_enemy_shows)
DISPLAYS.update({d: ("soul", k, f) for k, (d, f) in SOUL_DISPLAYS.items() if f})


def _region_soul_displays():
    """{"enemy_R_<code>": (display, figure FmdbName, the figure's soul key)} of the regional souls (extras_souls
    remake_shuffle_enemy_souls "regional"). Each shows the figure of its region's boss or most common enemy (data
    "figure_of"), that soul's figure model under a display of its own. So it's one model and two displays, the
    region's and the soul's, and they're never in one seed together."""
    import json as _json
    path = os.path.join(HERE, "data", "rando", "extras_enemy_souls.json")
    if not os.path.exists(path):
        return {}
    regs = _json.load(open(path, encoding="utf-8")).get("regions") or {}
    return {"enemy_R_" + r["code"]: (r["display"], SOUL_DISPLAYS[r["figure_of"]][1], r["figure_of"])
            for r in regs.values()}


for _k, (_d, _f, _rep) in _region_soul_displays().items():
    if any(_d == d for d, f in SOUL_DISPLAYS.values()):
        raise RuntimeError(f"{_k}: display {_d} is another soul's")
    SOUL_DISPLAYS[_k] = (_d, _f)
    DISPLAYS[_d] = ("soul", _rep, _f)
DONORS = {"song": (DONOR_PROJECT, DONOR), "button": (DONOR_PROJECT, DONOR), "sword": (SWORD_PROJECT, SWORD_DONOR)}
# the old one-colour soul figures (Item_Arrow_Fire copies). verify reports any row that still names one.
FLAT_SOUL_FIGURES = {"Rando_Fig_Gohma", "Rando_Fig_KDodo", "Rando_Fig_Barin", "Rando_Fig_PhGan", "Rando_Fig_Volva",
                     "Rando_Fig_Morph", "Rando_Fig_Bongo", "Rando_Fig_Twinr", "Rando_Fig_Ganon", "Rando_Fig_Beans"}
ANIM_FROM = "Item_Token_Gold"  # the animation set every model here is shown with (plan()["anim_from"])
for _code in [v[2] for v in BUTTON_MODELS.values()]:
    if len(BUTTON_FMDB + _code) != len(DONOR_PROJECT):
        raise RuntimeError(f"{BUTTON_FMDB + _code} must have {len(DONOR_PROJECT)} characters")
for _d, (_k, _key, _f) in DISPLAYS.items():
    if _f is not None and _k != "soul" and len(_f) != len(DONORS[_k][0]):
        raise RuntimeError(f"{_d}: FmdbName {_f} must have {len(DONORS[_k][0])} characters")
    if len(_d) > 25:
        raise RuntimeError(f"{_d}: display names over 25 characters can't be created")


class ModelError(Exception):
    pass


# Geometry (metres; +Y up, the front faces +Z)
class Mesh:
    def __init__(self):
        self.pos, self.nrm, self.part, self.tris = [], [], [], []

    def vert(self, p, n, part=0):
        self.pos.append(tuple(float(x) for x in p))
        ln = math.sqrt(sum(x * x for x in n)) or 1.0
        self.nrm.append(tuple(float(x) / ln for x in n))
        self.part.append(part)
        return len(self.pos) - 1

    def tri(self, a, b, c):
        self.tris.append((a, b, c))

    def quad(self, a, b, c, d):  # a b c d counter-clockwise seen from outside
        self.tri(a, b, c)
        self.tri(a, c, d)


def _rot_z(p, ang):
    c, s = math.cos(ang), math.sin(ang)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def _prism(m, outline, z0, z1, part=0, bottom=False):
    """An extruded convex or simple polygon (outline counter-clockwise in XY, seen from +Z). It has its top at z1 (+Z
    normal), side walls, and with bottom set its face at z0."""
    n = len(outline)
    top = [m.vert((x, y, z1), (0, 0, 1), part) for x, y in outline]
    for i in range(1, n - 1):  # fan (outlines here are convex or star-shaped from point 0)
        m.tri(top[0], top[i], top[i + 1])
    if bottom:
        bot = [m.vert((x, y, z0), (0, 0, -1), part) for x, y in outline]
        for i in range(1, n - 1):
            m.tri(bot[0], bot[i + 1], bot[i])
    for i in range(n):
        (ax, ay), (bx, by) = outline[i], outline[(i + 1) % n]
        nx, ny = by - ay, -(bx - ax)  # outward for a counter-clockwise outline
        a0, b0 = m.vert((ax, ay, z0), (nx, ny, 0), part), m.vert((bx, by, z0), (nx, ny, 0), part)
        a1, b1 = m.vert((ax, ay, z1), (nx, ny, 0), part), m.vert((bx, by, z1), (nx, ny, 0), part)
        m.quad(a0, b0, b1, a1)


def _ccw(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0


def _rounded_head(m, a, b, t, rb, tilt, dome=0.0, seg=28, steps=6, rim=2, face=3):
    """A note head: an ellipse (semi-axes a, b) with a rounded rim (a half-ellipse profile rb across, t/2 deep, part
    `rim`) and front and back faces (part `face`), tilted `tilt` radians and centred on the origin.
    The faces are domed `dome` higher in the middle, z = t/2 + dome (1 - s^2)^2 with s the elliptical radius. That's
    flat where they meet the rim, so the surface runs on without a crease."""
    ai, bi = a - rb, b - rb
    rings = []
    for k in range(seg):
        ph = 2 * math.pi * k / seg
        q = (ai * math.cos(ph), bi * math.sin(ph))
        n = (bi * math.cos(ph), ai * math.sin(ph))
        ln = math.hypot(*n)
        n = (n[0] / ln, n[1] / ln)
        ring = []
        for j in range(steps):
            be = -math.pi / 2 + math.pi * j / (steps - 1)
            p = (q[0] + rb * math.cos(be) * n[0], q[1] + rb * math.cos(be) * n[1], (t / 2) * math.sin(be))
            nn = (math.cos(be) / rb * n[0], math.cos(be) / rb * n[1], math.sin(be) / (t / 2))
            ring.append(m.vert(_rot_z(p, tilt), _rot_z(nn, tilt), rim))
        rings.append(ring)
    for k in range(seg):
        k2 = (k + 1) % seg
        for j in range(steps - 1):
            m.quad(rings[k][j], rings[k2][j], rings[k2][j + 1], rings[k][j + 1])
    for sg in (1, -1):  # the faces: a centre point and two rings (half way, and the rim's inner edge)
        def at(s, ph):
            x, y = ai * s * math.cos(ph), bi * s * math.sin(ph)
            k4 = 4 * dome * (1 - s * s)
            p = (x, y, sg * (t / 2 + dome * (1 - s * s) ** 2))
            return m.vert(_rot_z(p, tilt), _rot_z((k4 * x / ai ** 2, k4 * y / bi ** 2, sg), tilt), face)
        c = at(0.0, 0.0)
        face_rings = [[at(s, 2 * math.pi * k / seg) for k in range(seg)] for s in (0.55, 1.0)]
        for k in range(seg):
            k2 = (k + 1) % seg
            m.tri(c, face_rings[0][k], face_rings[0][k2])
            m.quad(face_rings[0][k], face_rings[1][k], face_rings[1][k2], face_rings[0][k2])


def _stem(m, x, y0, y1, r, seg=12, part=2):
    ring0, ring1 = [], []
    for j in range(seg):
        a = 2 * math.pi * j / seg
        n = (math.cos(a), 0.0, math.sin(a))
        ring0.append(m.vert((x + r * n[0], y0, r * n[2]), n, part))
        ring1.append(m.vert((x + r * n[0], y1, r * n[2]), n, part))
    for j in range(seg):
        k = (j + 1) % seg
        m.quad(ring0[j], ring1[j], ring1[k], ring0[k])
    c = m.vert((x, y1, 0.0), (0, 1, 0), part)
    cap = [m.vert((x + r * math.cos(2 * math.pi * j / seg), y1, r * math.sin(2 * math.pi * j / seg)), (0, 1, 0), part)
           for j in range(seg)]
    for j in range(seg):
        m.tri(c, cap[(j + 1) % seg], cap[j])


def _ribbon(m, ctrl, width, tz, steps=12, semi=5, rim=2, face=3):
    """An eighth note's flag: a ribbon along the cubic Bezier `ctrl` (in XY), `width(t)` wide and tz thick, its two
    long edges rounded (half-circles, part `rim`), its front and back flat (part `face`), both ends closed."""
    def bez(t):
        u = 1 - t
        w = (u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3)
        return (sum(w[i] * ctrl[i][0] for i in range(4)), sum(w[i] * ctrl[i][1] for i in range(4)))
    pts = [bez(k / steps) for k in range(steps + 1)]
    r = tz / 2
    sections = []
    for k, (x, y) in enumerate(pts):
        a, b = pts[max(0, k - 1)], pts[min(steps, k + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, ty)
        nx, ny = -ty / ln, tx / ln  # left of travel (in plane)
        half = max(width(k / steps) / 2 - r, 0.0005)
        sec = {"right": [], "left": [], "front": [], "back": []}
        for side, sign in (("left", 1), ("right", -1)):
            cx, cy = x + sign * nx * half, y + sign * ny * half
            for j in range(semi):
                th = -math.pi / 2 + math.pi * j / (semi - 1)  # back (-z) to front (+z)
                ox, oy = sign * nx * math.cos(th), sign * ny * math.cos(th)
                p = (cx + ox * r, cy + oy * r, r * math.sin(th))
                sec[side].append(m.vert(p, (ox, oy, math.sin(th)), rim))
            for z, key in ((r, "front"), (-r, "back")):
                sec[key].append(m.vert((cx, cy, z), (0, 0, 1 if z > 0 else -1), face))
        sections.append(sec)
    for k in range(steps):
        s0, s1 = sections[k], sections[k + 1]
        for side in ("left", "right"):
            for j in range(semi - 1):
                m.quad(s0[side][j], s1[side][j], s1[side][j + 1], s0[side][j + 1])
        for key in ("front", "back"):
            m.quad(s0[key][0], s1[key][0], s1[key][1], s0[key][1])
    for sec in (sections[0], sections[-1]):  # the ends: a fan over the outline
        loop = sec["left"] + sec["right"][::-1]
        c = sum((m.pos[i][0] for i in loop)) / len(loop), sum((m.pos[i][1] for i in loop)) / len(loop)
        k_end = 0 if sec is sections[0] else steps
        a, b = pts[max(0, k_end - 1)], pts[min(steps, k_end + 1)]
        d = (b[0] - a[0], b[1] - a[1]) if sec is sections[-1] else (a[0] - b[0], a[1] - b[1])
        cv = m.vert((c[0], c[1], 0.0), (d[0], d[1], 0.0), rim)
        ring = [m.vert(m.pos[i], (d[0], d[1], 0.0), rim) for i in loop]
        for j in range(len(ring)):
            m.tri(cv, ring[j], ring[(j + 1) % len(ring)])


def note_mesh():
    """An eighth note, the shape of OoT's song item: a tilted elliptical head with a rounded rim and gently domed faces,
    a slim stem from its right side, and a flag that tapers and curls down to the right. The head's faces glow a
    little less than its rim, the stem and the flag (parts 3 and 2: NOTE_FACE_UV, NOTE_RIM_UV). The flag is thin, so
    in two glows it would read as two strips."""
    m = Mesh()
    tilt = math.radians(22)
    a, b = 0.072, 0.050
    _rounded_head(m, a, b, 0.040, 0.016, tilt, dome=0.007)
    r = 0.0085
    sx = a * math.cos(tilt) - r * 1.2
    top = 0.335
    _stem(m, sx, 0.015, top, r)
    w0, w1 = 0.040, 0.008
    # the flag starts level with the stem's top, its left edge on the stem's (heading straight down at first, so its
    # top end is flat and flush), then sweeps out to the right and curls down
    x0 = sx - r + w0 / 2
    ctrl = [(x0, top), (x0, top - 0.06), (sx + 0.112, top - 0.095), (sx + 0.078, top - 0.215)]
    _ribbon(m, ctrl, lambda t: w0 * (1 - t) ** 0.85 + w1 * t, 0.022, face=2)
    return _fix_winding(m)


GLYPHS = {  # strokes in a box 1 high (-0.5..0.5): polylines; a closed one repeats its first point
    "A": [[(-0.36, -0.5), (0.0, 0.5), (0.36, -0.5)], [(-0.19, -0.08), (0.19, -0.08)]],
    "B": [[(-0.3, -0.5), (-0.3, 0.5)], [(-0.3, 0.5), (0.1, 0.5), (0.26, 0.4), (0.28, 0.2), (0.12, 0.04), (-0.3, 0.04)],
          [(0.12, 0.04), (0.3, -0.08), (0.32, -0.32), (0.16, -0.5), (-0.3, -0.5)]],
    "X": [[(-0.34, -0.5), (0.34, 0.5)], [(-0.34, 0.5), (0.34, -0.5)]],
    "Y": [[(-0.34, 0.5), (0.0, 0.02)], [(0.34, 0.5), (0.0, 0.02)], [(0.0, 0.02), (0.0, -0.5)]],
    "L": [[(-0.24, 0.5), (-0.24, -0.5), (0.3, -0.5)]],
    "R": [[(-0.28, -0.5), (-0.28, 0.5), (0.1, 0.5), (0.27, 0.38), (0.28, 0.16), (0.1, 0.02), (-0.28, 0.02)],
          [(0.02, 0.02), (0.32, -0.5)]],
    "1": [[(-0.14, 0.32), (0.04, 0.5), (0.04, -0.5)], [(-0.16, -0.5), (0.24, -0.5)]],
    "Cross": [[(-0.4, -0.4), (0.4, 0.4)], [(-0.4, 0.4), (0.4, -0.4)]],
    "Circle": [[(0.42 * math.cos(2 * math.pi * k / 20), 0.42 * math.sin(2 * math.pi * k / 20)) for k in range(21)]],
    "Square": [[(-0.38, -0.38), (0.38, -0.38), (0.38, 0.38), (-0.38, 0.38), (-0.38, -0.38)]],
    "Triangle": [[(0.0, 0.44), (0.42, -0.3), (-0.42, -0.3), (0.0, 0.44)]],
}
GLYPH_STROKE = 0.15  # of the glyph's height


def _glyph(m, name, cx, cy, height, z0, z1, part=1):
    """Glyph `name` raised from z0 to z1, centred at (cx, cy), `height` high: each stroke segment a bar (its ends
    run on by half the stroke so joints close)."""
    w = GLYPH_STROKE * height
    for line in GLYPHS[name]:
        pts = [(cx + x * height, cy + y * height) for x, y in line]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            ln = math.hypot(x1 - x0, y1 - y0)
            if ln < 1e-9:
                continue
            dx, dy = (x1 - x0) / ln * w / 2, (y1 - y0) / ln * w / 2
            a, b = (x0 - dx, y0 - dy), (x1 + dx, y1 + dy)
            quad = [(a[0] + dy, a[1] - dx), (b[0] + dy, b[1] - dx), (b[0] - dy, b[1] + dx), (a[0] - dy, a[1] + dx)]
            if not _ccw(*quad[:3]):
                quad = quad[::-1]
            _prism(m, quad, z0, z1, part=part)


def _disc(m, r=0.15, t=0.05, b=0.014, seg=40):
    """A face button: a bevelled disc facing +Z. Returns the front face's z."""
    zf, zb = t / 2, -t / 2
    ring = [(math.cos(2 * math.pi * j / seg), math.sin(2 * math.pi * j / seg)) for j in range(seg)]
    for z, nz in ((zf, 1), (zb, -1)):  # front and back faces
        c = m.vert((0, 0, z), (0, 0, nz))
        rim = [m.vert(((r - b) * x, (r - b) * y, z), (0, 0, nz)) for x, y in ring]
        for j in range(seg):
            m.tri(c, rim[j], rim[(j + 1) % seg])
    for zin, zout, nz in ((zf, zf - b, 1), (zb, zb + b, -1)):  # bevels
        inner = [m.vert(((r - b) * x, (r - b) * y, zin), (x, y, nz)) for x, y in ring]
        outer = [m.vert((r * x, r * y, zout), (x, y, nz)) for x, y in ring]
        for j in range(seg):
            k = (j + 1) % seg
            m.quad(inner[j], outer[j], outer[k], inner[k])
    top = [m.vert((r * x, r * y, zf - b), (x, y, 0)) for x, y in ring]  # side wall
    bot = [m.vert((r * x, r * y, zb + b), (x, y, 0)) for x, y in ring]
    for j in range(seg):
        k = (j + 1) % seg
        m.quad(bot[j], bot[k], top[k], top[j])
    return zf


def _shoulder(m, side, w=0.34, h=0.2, t=0.05, slant=0.06):
    """A shoulder button: the remake's icon shape (OcarinaButtonL/R), a slab with its outer top corner cut on a
    slant, facing +Z. Returns the front face's z."""
    hw, hh = w / 2, h / 2
    if side == "l":
        outline = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw + slant, hh)]
    else:
        outline = [(-hw, -hh), (hw, -hh), (hw - slant, hh), (-hw, hh)]
    _prism(m, outline, -t / 2, t / 2, part=0, bottom=True)
    return t / 2


def button_mesh(label):
    """Button `label` (BUTTON_MODELS): its shape with the label raised on the front, the label a part of its own
    (GLYPH_UV: glows dimmer)."""
    m = Mesh()
    shape, glyphs, _ = BUTTON_MODELS[label]
    zf = _disc(m) if shape == "face" else _shoulder(m, shape[-1])
    g0, g1 = zf - 0.002, zf + 0.016
    height = 0.13 if shape == "face" else 0.11
    if len(glyphs) == 1:
        symbol = glyphs[0] in ("Circle", "Square", "Triangle", "Cross")
        _glyph(m, glyphs[0], 0.0, 0.0, height * (0.82 if symbol else 1.0), g0, g1)
    else:  # two characters side by side
        h2 = height * 0.85
        for k, g in enumerate(glyphs):
            _glyph(m, g, (k - 0.5) * h2 * 0.78, 0.0, h2, g0, g1)
    return _fix_winding(m)


def button_label(display, controls=None, controller=None):
    """The label an Ocarina note item's display shows: the button playing its note under `controls`, named for
    `controller` (defaults: normal controls, Nintendo labels; "auto" is resolved here, resolve_controller)."""
    controls = controls or REMAKE_DEFAULTS["remake_ocarina_controls"]
    controller = controller or "nintendo"
    if controller == "auto":
        controller = resolve_controller()[0]
    button = OCARINA_CONTROLS[controls][NOTE_PITCH[display]]
    return CONTROLLERS[controller].get(button, button)


def _ini_value(path, key):
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            k, sep, v = line.strip().partition("=")
            if sep and k.strip() == key:
                return v.strip()
    except OSError:
        return None
    return None


def resolve_controller(build=None):
    """(controller, where from) for remake_controller "auto", the prompt set Longshot shows. It reads Longshot's options
    (longshot_options.ini button_prompts: 0 = auto) and the newest log (logs/longshot_log*.txt). With auto that's the
    line 'prompts: auto: controller "<pad>": <set>'. With a chosen set (the numbers' names aren't known) it's the set
    its 'prompts: <set> icons' line loaded. Keyboard, no log or an unknown set give nintendo."""
    import glob
    import re
    build = build or LONGSHOT_BUILD
    chosen = _ini_value(os.path.join(build, "longshot_options.ini"), "button_prompts")
    logs = sorted(glob.glob(os.path.join(build, "logs", "longshot_log*.txt")), key=os.path.getmtime, reverse=True)
    auto = chosen in (None, "", "0")
    pat = re.compile(r'prompts: auto: controller "([^"]*)": (\w+)') if auto else re.compile(r"prompts: (\w+) icons")
    for log in logs:
        try:
            lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            m = pat.search(line)
            if m:
                prompt = m.groups()[-1]
                why = f"pad {m.group(1)}" if auto else f"button_prompts={chosen}"
                return (PROMPT_SETS.get(prompt, "nintendo"),
                        f"Longshot prompts {prompt} ({why}), {os.path.basename(log)}")
    return "nintendo", "no Longshot prompt line found"


def context(settings):
    """plan["_show_models"] for a seed, {"controls", "controller"} from its remake settings (a dict, or an object with
    .remake). "auto" gets resolved now (resolve_controller), and "controller_from" says from what."""
    remake = settings if isinstance(settings, dict) else (getattr(settings, "remake", None) or {})
    controller = remake.get("remake_controller", REMAKE_DEFAULTS["remake_controller"])
    out = {"controls": remake.get("remake_ocarina_controls", REMAKE_DEFAULTS["remake_ocarina_controls"])}
    if controller == "auto":
        controller, out["controller_from"] = resolve_controller()
    out["controller"] = controller
    return out


def _fix_winding(m):
    """Winds every triangle so its face normal agrees with its vertex normals (the donor's front is counter-clockwise),
    and drops degenerate ones."""
    fixed = []
    for a, b, c in m.tris:
        pa, pb, pc = m.pos[a], m.pos[b], m.pos[c]
        e1 = [pb[i] - pa[i] for i in range(3)]
        e2 = [pc[i] - pa[i] for i in range(3)]
        fn = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        if sum(x * x for x in fn) < 1e-14:
            continue
        vn = [sum(m.nrm[v][i] for v in (a, b, c)) for i in range(3)]
        fixed.append((a, b, c) if sum(fn[i] * vn[i] for i in range(3)) > 0 else (a, c, b))
    m.tris = fixed
    return m


def centred(m):
    """The mesh moved so its bounding box is centred on the origin (items turn about their centre)."""
    lo = [min(p[i] for p in m.pos) for i in range(3)]
    hi = [max(p[i] for p in m.pos) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    m.pos = [tuple(p[i] - c[i] for i in range(3)) for p in m.pos]
    return m


def mesh_for(display, label=None):
    """The item's mesh: a song's note, a soul's figure (with "lods"), or (label: BUTTON_MODELS) an Ocarina button."""
    if label is not None:
        return centred(button_mesh(label))
    kind, key, _ = DISPLAYS[display]
    if kind == "button":
        return centred(button_mesh(button_label(display)))
    return centred(note_mesh())


def colour_for(display):
    """A display's colour, or (a BUTTON_MODELS label) a button's."""
    if display in BUTTON_MODELS or DISPLAYS.get(display, ("",))[0] == "button":
        return BUTTON_COLOUR
    return SONG_COLOURS[DISPLAYS[display][1]]


# Skeleton readers (parity/_soul_figures.py uses them)
def _euler(r):
    import numpy as np
    x, y, z = r[:3]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return (np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]))


def _skeleton(d):
    """(bones [{name, parent, s, r, t}], matrix-to-bone list, inverse bind matrices of the smooth matrices)."""
    import numpy as np
    sk = _q(d, _q(d, 0x28) + 0x18)
    if d[sk:sk + 4] != b"FSKL":
        raise ModelError("no skeleton")
    ba, nb, ns, nr = _q(d, sk + 0x10), _u16(d, sk + 0x38), _u16(d, sk + 0x3A), _u16(d, sk + 0x3C)
    bones = []
    for i in range(nb):
        b = ba + 0x58 * i
        bones.append({"name": _str(d, _q(d, b)), "parent": struct.unpack_from("<h", d, b + 0x22)[0],
                      "s": struct.unpack_from("<3f", d, b + 0x30), "r": struct.unpack_from("<4f", d, b + 0x3C),
                      "t": struct.unpack_from("<3f", d, b + 0x4C)})
    m2b = [_u16(d, _q(d, sk + 0x18) + 2 * i) for i in range(ns + nr)]
    inv = []
    for i in range(ns):
        m = np.eye(4)
        m[:3] = np.array(struct.unpack_from("<12f", d, _q(d, sk + 0x20) + 48 * i)).reshape(3, 4)
        inv.append(m)
    return bones, m2b, inv


def _pose(anim_data, name):
    """{bone: {"s", "r", "t"}} of one-frame skeletal anim `name` (base values only; curves refused)."""
    import re
    for m in re.finditer(b"FSKA", anim_data):
        o = m.start()
        try:
            if _str(anim_data, _q(anim_data, o + 8)) != name:
                continue
        except (struct.error, UnicodeDecodeError, IndexError):
            continue
        out = {}
        for i in range(_u16(anim_data, o + 0x4C)):
            b = _q(anim_data, o + 0x28) + 0x38 * i
            flags, ncurve, base = _u32(anim_data, b + 0x28), anim_data[b + 0x2E], _q(anim_data, b + 0x10)
            if ncurve:
                raise ModelError(f"{name}: bone {_str(anim_data, _q(anim_data, b))} has {ncurve} curves")
            e, k = {}, 0
            for bit, key, n in ((0x20, "s", 3), (0x10, "r", 4), (0x08, "t", 3)):
                if flags & bit:
                    e[key] = struct.unpack_from(f"<{n}f", anim_data, base + 4 * k)
                    k += n
            out[_str(anim_data, _q(anim_data, b))] = e
        return out
    raise ModelError(f"no skeletal anim {name}")


def glow_for(display):
    """(ns_param_color5, ns_emission_intensity): the linear colour, and the strength that brings it to GLOW_LUMINANCE
    with its brightest channel at most GLOW_PEAK. display is a display or a button label."""
    srgb = colour_for(display)
    c = [_lin(x) for x in srgb]
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    if max(srgb) - min(srgb) < 8 and max(srgb) < 250:  # a grey (Song of Storms): raised to the others' brightness
        return (c[0], c[1], c[2], 1.0), GLOW_LUMINANCE  # it would be white again; it keeps its own (white's strength)
    return (c[0], c[1], c[2], 1.0), round(min(GLOW_LUMINANCE / lum, GLOW_PEAK / max(c)), 3)


# The donor (BFRES 10.4; see _gaps_triforce_model)
def _q(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def _u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def _str(d, o):
    n = _u16(d, o)
    return d[o + 2:o + 2 + n].decode("ascii", "replace")


def layout(d):
    """Shapes (name, vertex buffer, attributes, meshes, bounds) and materials of the donor or a copy."""
    if d[:4] != b"FRES" or _u32(d, 8) != 0x000A0400:
        raise ModelError("not a BFRES 10.4 file")
    fm = _q(d, 0x28)
    pool = _q(d, _q(d, 0xB0) + 8)
    shapes = {}
    for i in range(_u16(d, fm + 0x6A)):
        sh = _q(d, fm + 0x28) + 0x60 * i
        vb = _q(d, sh + 0x10)
        attrs = {}
        for k in range(d[vb + 0x4C]):
            a = _q(d, vb + 0x08) + 0x10 * k
            attrs[_str(d, _q(d, a))] = (_u16(d, a + 8), _u16(d, a + 0x0C))
        meshes = []
        for k in range(d[sh + 0x5B]):
            me = _q(d, sh + 0x18) + 0x38 * k
            meshes.append({"at": me, "sub": _q(d, me), "nsub": _u16(d, me + 0x34), "ibuf": pool + _u32(d, me + 0x20),
                           "count": _u32(d, me + 0x2C), "first": _u32(d, me + 0x30), "prim": _u32(d, me + 0x24),
                           "fmt": _u32(d, me + 0x28)})
        nboxes = sum(1 + m["nsub"] for m in meshes)
        shapes[_str(d, _q(d, sh + 8))] = {
            "at": sh, "vbuf": pool + _u32(d, vb + 0x48), "count": _u32(d, vb + 0x50),
            "stride": _u32(d, _q(d, vb + 0x38)), "attrs": attrs, "meshes": meshes, "bounds": _q(d, sh + 0x38),
            "nboxes": nboxes, "sphere": _q(d, sh + 0x40), "skin": d[sh + 0x5A]}
    mats = {}
    for k in range(_u16(d, fm + 0x6C)):
        m = _q(d, fm + 0x38) + 0xB0 * k
        texs = [_str(d, _q(d, _q(d, m + 0x20) + 8 * i)) for i in range(d[m + 0xA3])]
        mats[_str(d, _q(d, m + 8))] = {"at": m, "textures": texs}
    return {"shapes": shapes, "materials": mats, "name": _str(d, _q(d, fm + 8)), "file_name": _str(d, _q(d, 0x20))}


def glow_params(d, material):
    """{param name: file offset} of GLOW_PARAMS in material `material` (hash and type checked)."""
    m = layout(d)["materials"][material]["at"]
    sa = _q(d, _q(d, m + 0x10))
    arr, data = _q(d, sa + 0x20), _q(d, m + 0x58)
    found = {}
    for i in range(_u16(d, sa + 0x4A)):
        off, typ = struct.unpack_from("<HH", d, arr + 24 * i + 16)
        found[_q(d, arr + 24 * i + 8)] = (data + off, typ)
    out = {}
    for name, (h, typ) in GLOW_PARAMS.items():
        if found.get(h, (0, None))[1] != typ:
            raise ModelError(f"{material} has no {name} of type {typ}")
        out[name] = found[h][0]
    return out


def _pack_snorm10(v, w_bits):
    word = (w_bits & 3) << 30
    for k in range(3):
        word |= (int(round(max(-1.0, min(1.0, float(v[k]))) * 511)) & 0x3FF) << (10 * k)
    return word


def _snorm10(word):
    out = []
    for k in range(3):
        v = (word >> (10 * k)) & 0x3FF
        out.append(max((v - 1024 if v >= 512 else v) / 511.0, -1.0))
    return out


def _tangent(n):
    """A unit vector at right angles to normal n (the UVs don't vary, so any such direction is right)."""
    a = (0.0, 1.0, 0.0) if abs(n[1]) < 0.9 else (1.0, 0.0, 0.0)
    t = (a[1] * n[2] - a[2] * n[1], a[2] * n[0] - a[0] * n[2], a[0] * n[1] - a[1] * n[0])
    ln = math.sqrt(sum(x * x for x in t))
    return tuple(x / ln for x in t)


def _check_donor(lay, mask=DONOR_MASK):
    body, empty = lay["shapes"].get(BODY_SHAPE), lay["shapes"].get(EMPTY_SHAPE)
    if body is None or empty is None or set(lay["shapes"]) != {BODY_SHAPE, EMPTY_SHAPE}:
        raise ModelError(f"the donor's shapes are {sorted(lay['shapes'])}")
    for s in (body, empty):
        if s["stride"] != 24 or s["attrs"] != VERTEX_FORMATS or s["skin"] != 1:
            raise ModelError(f"a donor shape's vertex layout is {s['attrs']} (stride {s['stride']})")
        for m in s["meshes"]:
            if m["prim"] != 3 or m["fmt"] != 1 or m["nsub"] != 1:
                raise ModelError("expected u16 triangle lists with one sub-mesh per mesh")
    if mask not in lay["materials"].get(GLOW_MATERIAL, {}).get("textures", []):
        raise ModelError(f"{GLOW_MATERIAL} doesn't read {mask}")


def _lods(mesh, n):
    """Each of the n LODs' triangles: a soul figure's own (mesh.lods), else the same item in every LOD."""
    lods = list(getattr(mesh, "lods", None) or [mesh.tris])
    return (lods + [lods[-1]] * n)[:n]


def build(src, mesh, glow):
    """(edits, info): byte edits making donor `src` (decompressed) show `mesh` with `glow` (colour, strength)."""
    d = bytes(src)
    lay = layout(d)
    _check_donor(lay)
    body, empty = lay["shapes"][BODY_SHAPE], lay["shapes"][EMPTY_SHAPE]
    n = len(mesh.pos)
    lods = _lods(mesh, len(body["meshes"]))
    if n > body["count"] or any(len(t) * 3 > m["count"] for t, m in zip(lods, body["meshes"])):
        raise ModelError(f"{n} vertices / {[len(t) * 3 for t in lods]} indices don't fit the donor's metal shape")
    edits = []

    def put(off, new):
        old = d[off:off + len(new)]
        if old != new:
            edits.append({"offset": off, "expect": old.hex(), "bytes": new.hex()})
    import numpy as np
    s = body["stride"]
    old = d[body["vbuf"]:body["vbuf"] + n * s]
    i0 = d[body["vbuf"] + 20:body["vbuf"] + 24]  # the donor's bone index (every vertex has the same)
    t_w = (_u32(d, body["vbuf"] + 12) >> 30) & 3
    vb = bytearray()
    uvs = PART_UV
    for p, nr, part in zip(mesh.pos, mesh.nrm, mesh.part):
        rec = np.array([p[0], p[1], p[2], 1.0], dtype=np.float16).tobytes()
        rec += struct.pack("<II", _pack_snorm10(nr, 1), _pack_snorm10(_tangent(nr), t_w))
        u, v = uvs[part]
        rec += struct.pack("<HH", int(round(u * 65535)), int(round(v * 65535))) + i0
        vb += rec
    if len(vb) != len(old):
        raise ModelError("vertex record size")
    put(body["vbuf"], bytes(vb))
    for m, lod in zip(body["meshes"], lods):  # every LOD: the item's triangles (a soul's: that LOD's) from vertex 0
        idx = struct.pack(f"<{len(lod) * 3}H", *[i for t in lod for i in t])
        put(m["ibuf"], idx)
        put(m["at"] + 0x2C, struct.pack("<I", len(idx) // 2))
        put(m["at"] + 0x30, struct.pack("<I", 0))
        put(m["sub"], struct.pack("<II", 0, len(idx) // 2))
    for m in empty["meshes"]:  # the crystal: one degenerate triangle
        put(m["ibuf"], bytes(6))
        put(m["at"] + 0x2C, struct.pack("<I", 3))
        put(m["sub"], struct.pack("<II", 0, 3))
    # bounds from the positions as stored (half floats)
    ph = [tuple(float(x) for x in np.array(p, dtype=np.float16)) for p in mesh.pos]
    lo = [min(p[i] for p in ph) for i in range(3)]
    hi = [max(p[i] for p in ph) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    h = [(hi[i] - lo[i]) / 2 for i in range(3)]
    radius = max(math.sqrt(sum((p[i] - c[i]) ** 2 for i in range(3))) for p in ph)
    put(body["bounds"], struct.pack("<6f", *c, *h) * body["nboxes"])
    put(body["sphere"], struct.pack("<4f", *c, radius))
    at = glow_params(d, GLOW_MATERIAL)
    colour, strength = glow
    put(at["ns_param_color5"], struct.pack("<4f", *colour))
    put(at["ns_emission_intensity"], struct.pack("<f", strength))
    info = {"vertices": n, "indices": [len(t) * 3 for t in lods], "min": lo, "max": hi, "radius": radius,
            "glow": [list(colour), strength]}
    return edits, info


def apply(src, edits):
    d = bytearray(src)
    for e in edits:
        o, old, new = e["offset"], bytes.fromhex(e["expect"]), bytes.fromhex(e["bytes"])
        if d[o:o + len(old)] != old:
            raise ModelError(f"byte edit at {o:#x} doesn't match the source")
        d[o:o + len(new)] = new
    return bytes(d)


def mask_edits(src):
    """Byte edits making MASK_SRC's data the banded mask (every block of every mip set by MASK_BANDS from its u),
    from the block positions in the block-linear layout."""
    from parity import _cosmetics_tex as tex
    t = tex.info(src)
    if t["fmt"] != 0x1D:
        raise ModelError(f"{MASK_SRC} is format {t['fmt']:#x}, not BC4")
    pos = tex.block_positions(src)
    if len(pos) * 8 != t["size"] and sum(1 for _ in pos) == 0:
        raise ModelError(f"{MASK_SRC}: no blocks")
    d = bytearray(src[t["start"]:t["start"] + t["size"]])
    for off, (u, _v) in pos.items():
        val = mask_value(u)
        o = off - t["start"]
        if 0 <= o <= len(d) - 8:
            d[o:o + 8] = bytes([val, val]) + bytes(6)
    old = src[t["start"]:t["start"] + t["size"]]
    return [{"offset": t["start"], "expect": old.hex(), "bytes": bytes(d).hex()}] if bytes(d) != old else []


def _fs(romfs):
    from romtools import Romfs
    return Romfs(romfs, os.path.join(HERE, "original"))


def _romfs():
    import drops as drop_tools
    return drop_tools.DEFAULT_ROMFS


def button_fmdb(label):
    return BUTTON_FMDB + BUTTON_MODELS[label][2]


def button_model_path(label):
    return f"Model/{DONOR_PROJECT}.{button_fmdb(label)}.bfres.zs"


def model_path(display, controls=None, controller=None):
    """The model file a display shows (an Ocarina note item's: its label's under these controls)."""
    kind = DISPLAYS[display][0]
    if kind == "button":
        return button_model_path(button_label(display, controls, controller))
    if kind == "soul":
        from parity import _soul_figures
        return _soul_figures.figure_path(DISPLAYS[display][1])
    return f"Model/{DONORS[kind][0]}.{DISPLAYS[display][2]}.bfres.zs"


def _sword_up(v):
    """The sword pose: (x, y, z) -> (x, z, -y): the blade (+Z, the tip) up, the crossguard across, the flat front."""
    return (v[0], v[2], -v[1])


def _bone_at(d, name):
    """File offset of bone `name`'s record (FSKL bone array, 0x58 each; +0x30 scale, rotation, +0x4C translation)."""
    fm = _q(d, 0x28)
    sk = _q(d, fm + 0x18)
    if d[sk:sk + 4] != b"FSKL":
        raise ModelError("no skeleton")
    arr = _q(d, sk + 0x10)
    for i in range(64):
        b = arr + 0x58 * i
        try:
            if _str(d, _q(d, b)) == name:
                return b
        except (struct.error, IndexError):
            break
    raise ModelError(f"no bone {name}")


def sword_build(src):
    """(edits, info) for the Master Sword's model with the display pose baked in (see SWORD_SCALE above). Every vertex
    of every shape and LOD is turned tip up, scaled and centred (normals and tangents turned too), each mesh's bounding
    boxes and the shapes' spheres come from the new positions, and Skl_Root's rest offset is zeroed."""
    import numpy as np
    d = bytes(src)
    lay = layout(d)
    if set(lay["shapes"]) != SWORD_SHAPES:
        raise ModelError(f"the sword's shapes are {sorted(lay['shapes'])}")
    edits = []

    def put(off, new):
        old = d[off:off + len(new)]
        if old != new:
            edits.append({"offset": off, "expect": old.hex(), "bytes": new.hex()})
    per, allp = {}, []
    for name, s in lay["shapes"].items():
        if s["attrs"] != VERTEX_FORMATS or s["stride"] != 24 or s["skin"] != 1:
            raise ModelError(f"{name}: vertex layout {s['attrs']} (stride {s['stride']}, skin {s['skin']})")
        rec = np.frombuffer(d, np.uint8, s["count"] * 24, s["vbuf"]).reshape(-1, 24).copy()
        p = rec[:, 0:8].copy().view(np.float16).astype(np.float64)[:, :3]
        p2 = np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1) * SWORD_SCALE
        per[name] = (rec, p2)
        allp.append(p2)
    allp = np.vstack(allp)
    c = (allp.min(0) + allp.max(0)) / 2
    lo_all, hi_all = None, None
    for name, (rec, p2) in per.items():
        s = lay["shapes"][name]
        new_p = (p2 - c).astype(np.float16)
        rec[:, 0:6] = new_p.view(np.uint8).reshape(-1, 6)
        for off in (8, 12):
            words = rec[:, off:off + 4].copy().view("<u4").ravel()
            rec[:, off:off + 4] = np.array([_pack_snorm10(_sword_up(_snorm10(int(w))), (int(w) >> 30) & 3)
                                            for w in words], dtype="<u4").view(np.uint8).reshape(-1, 4)
        put(s["vbuf"], rec.tobytes())
        hp = new_p.astype(np.float64)
        boxes = b""
        for m in s["meshes"]:
            used = np.unique(np.frombuffer(d, "<u2", m["count"], m["ibuf"]).astype(np.int64) + m["first"])
            q = hp[used]
            lo, hi = q.min(0), q.max(0)
            boxes += struct.pack("<6f", *((lo + hi) / 2), *((hi - lo) / 2)) * (1 + m["nsub"])
            if m is s["meshes"][0]:
                lo_all = lo if lo_all is None else np.minimum(lo_all, lo)
                hi_all = hi if hi_all is None else np.maximum(hi_all, hi)
        put(s["bounds"], boxes)
        q = hp[np.unique(np.frombuffer(d, "<u2", s["meshes"][0]["count"], s["meshes"][0]["ibuf"]).astype(np.int64)
                         + s["meshes"][0]["first"])]
        sc = (q.min(0) + q.max(0)) / 2
        put(s["sphere"], struct.pack("<4f", *sc, float(np.sqrt(((hp - sc) ** 2).sum(1)).max())))
    b = _bone_at(d, SWORD_BONE)
    put(b + 0x4C, struct.pack("<3f", 0.0, 0.0, 0.0))
    info = {"min": [float(x) for x in lo_all], "max": [float(x) for x in hi_all], "scale": SWORD_SCALE,
            "centre_removed": [float(x) for x in c]}
    return edits, info


def _dict_problems(data, path, fmdb):
    """Checks a built model's name dictionaries. The game's lookup has to find every key, and the model by its FmdbName
    in the file's model dictionary (FRES + 0x30, the name ModelInfo gives; res_dict.py, test_guardroom3)."""
    bad = res_dict.problems(data, path)
    if not res_dict.has(data, fmdb, _q(data, 0x30)):
        bad.append(f"{path}: its model dictionary doesn't find {fmdb} (the game couldn't load the model by name)")
    return bad


def verify_sword(data, donor):
    """Problems with a built Master Sword model: names, Skl_Root's rest offset 0, every vertex the donor's turned,
    scaled and centred, the blade above the grip, bounds holding the vertices."""
    import numpy as np
    path = model_path("Rando_Show_MasterSword")
    bad = []
    try:
        lay, dlay = layout(data), layout(donor)
    except ModelError as e:
        return [f"{path}: {e}"]
    fmdb = DISPLAYS["Rando_Show_MasterSword"][2]
    if lay["name"] != fmdb or lay["file_name"] != f"{SWORD_PROJECT}.{fmdb}":
        bad.append(f"{path}: names {lay['name']} / {lay['file_name']}")
    bad += _dict_problems(data, path, fmdb)
    if struct.unpack_from("<3f", data, _bone_at(data, SWORD_BONE) + 0x4C) != (0.0, 0.0, 0.0):
        bad.append(f"{path}: {SWORD_BONE} keeps a rest offset")
    pos = {}
    for name, s in lay["shapes"].items():
        rec = np.frombuffer(data, np.uint8, s["count"] * 24, s["vbuf"]).reshape(-1, 24)
        pos[name] = rec[:, 0:8].copy().view(np.float16).astype(np.float64)[:, :3]
        drec = np.frombuffer(donor, np.uint8, s["count"] * 24, dlay["shapes"][name]["vbuf"]).reshape(-1, 24)
        dp = drec[:, 0:8].copy().view(np.float16).astype(np.float64)[:, :3]
        want = np.stack([dp[:, 0], dp[:, 2], -dp[:, 1]], 1) * SWORD_SCALE
        if np.abs((pos[name] - pos[name].mean(0)) - (want - want.mean(0))).max() > 4e-3:
            bad.append(f"{path}: {name} isn't the sword turned tip up and scaled {SWORD_SCALE}")
        if (rec[:, 16:24] != drec[:, 16:24]).any():
            bad.append(f"{path}: {name}'s UVs or bone indices changed")
        box = struct.unpack_from(f"<{6 * s['nboxes']}f", data, s["bounds"])
        c, h = np.array(box[:3]), np.array(box[3:6])
        m = s["meshes"][0]
        q = pos[name][np.unique(np.frombuffer(data, "<u2", m["count"], m["ibuf"]).astype(np.int64) + m["first"])]
        if (q < c - h - 1e-3).any() or (q > c + h + 1e-3).any():
            bad.append(f"{path}: {name}'s bounding box doesn't hold its vertices")
    allp = np.vstack(list(pos.values()))
    if np.abs((allp.min(0) + allp.max(0)) / 2).max() > 3e-3:
        bad.append(f"{path}: not centred ({(allp.min(0) + allp.max(0)) / 2})")
    blade, grip = pos["Blade_Mark__Mt_Weapon_Sword_Master_Metal"], pos["Grip__Mt_Weapon_Sword_Master"]
    if blade[:, 1].max() <= grip[:, 1].max() or (allp.max(0) - allp.min(0))[1] < 0.9:
        bad.append(f"{path}: the blade isn't up (size {allp.max(0) - allp.min(0)})")
    return bad


def mask_op(romfs=None):
    """The new mask texture: make_patch new_files op (the same op for every display: add it once)."""
    fs = _fs(romfs or _romfs())
    src = fs.read(MASK_SRC)
    renames = [[MASK_SRC_NAME, MASK]]
    return {"to": MASK_FILE, "from": MASK_SRC, "rename": renames,
            "bytes": mask_edits(src) + res_dict.edits(src, renames),
            "note": "glow mask of the song and Ocarina button models (parity/_show_models.py)"}


def plan(display, romfs=None, controls=None, controller=None):
    """{"new_files": [the model's op, the mask's op], "modelinfo": {FmdbName, ModelProjectName}, "aabb": (min, max),
    "anim_from": ANIM_FROM[, "label"]} for a display this module has a model for, else None. Several displays' mask
    ops are the same op, so keep one (dedupe new_files by "to"). Every model here is centred on bone Root with
    Skl_Root at identity. Show it with ANIM_FROM's animation set (its Pose_* leave Skl_Root at identity or scale it
    0.85), not a pose set of another model (a sword's turns Skl_Root, a rupee's shifts it).
    controls, controller: the seed's remake_ocarina_controls and remake_controller (plan["_show_models"], context()).
    An Ocarina note item's model is the button playing its note, labelled for that controller (defaults:
    REMAKE_DEFAULTS). Other displays don't depend on them."""
    if display not in DISPLAYS:
        return None
    romfs = romfs or _romfs()
    fs = _fs(romfs)
    fmdb = DISPLAYS[display][2]
    label = None
    if DISPLAYS[display][0] == "button":
        label = button_label(display, controls, controller)
        fmdb = button_fmdb(label)
    if DISPLAYS[display][0] == "soul":  # the enemy's own model (parity/_soul_figures.py)
        from parity import _soul_figures
        out = _soul_figures.plan(DISPLAYS[display][1], romfs)
        out["anim_from"] = ANIM_FROM
        return out
    if DISPLAYS[display][0] == "sword":
        src = fs.read(SWORD_DONOR)
        edits, info = sword_build(src)
        renames = [[f"{SWORD_PROJECT}.{SWORD_PROJECT}", f"{SWORD_PROJECT}.{fmdb}"], [SWORD_PROJECT, fmdb]]
        op = {"to": model_path(display), "from": SWORD_DONOR, "rename": renames,
              "bytes": edits + res_dict.edits(src, renames),  # the model dictionary finds the new name
              "note": f"{display}: the Master Sword's model, display pose baked in (parity/_show_models.py)"}
        lo = {"X": info["min"][0], "Y": info["min"][1], "Z": info["min"][2]}
        hi = {"X": info["max"][0], "Y": info["max"][1], "Z": info["max"][2]}
        return {"new_files": [op], "modelinfo": {"FmdbName": fmdb, "ModelProjectName": SWORD_PROJECT},
                "aabb": (lo, hi), "anim_from": ANIM_FROM}
    src = fs.read(DONOR)
    edits, info = build(src, mesh_for(display, label), glow_for(label or display))
    what = f"Ocarina button {label}" if label else f"{DISPLAYS[display][0]} model"
    renames = [[f"{DONOR_PROJECT}.{DONOR_PROJECT}", f"{DONOR_PROJECT}.{fmdb}"], [DONOR_PROJECT, fmdb],
               [DONOR_MASK, MASK]]
    op = {"to": button_model_path(label) if label else model_path(display), "from": DONOR, "rename": renames,
          "bytes": edits + res_dict.edits(src, renames),  # the model dictionary finds the new name
          "note": f"{display}: {what} (parity/_show_models.py)"}
    lo = {"X": info["min"][0], "Y": info["min"][1], "Z": info["min"][2]}
    hi = {"X": info["max"][0], "Y": info["max"][1], "Z": info["max"][2]}
    out = {"new_files": [op, mask_op(romfs)], "modelinfo": {"FmdbName": fmdb, "ModelProjectName": DONOR_PROJECT},
           "aabb": (lo, hi), "anim_from": ANIM_FROM}
    if label:
        out["label"] = label
    return out


def dedupe_new_files(ops):
    """new_files ops with one op per target path (identical duplicates dropped; differing ones refused)."""
    out = {}
    for op in ops:
        if op["to"] in out and out[op["to"]] != op:
            raise ModelError(f"two different new_files ops for {op['to']}")
        out[op["to"]] = op
    return list(out.values())


def verify_model(display, data, label=None):
    """Problems with a built model (decompressed): names, the item's geometry in every LOD of the metal shape, the
    crystal empty, bounds, UVs on the neutral points, the mask slot, the glow. With label it's an Ocarina button's
    model, and display may be None."""
    import numpy as np
    bad = []
    path = button_model_path(label) if label else model_path(display)
    what = f"Ocarina button {label}" if label else DISPLAYS[display][0]
    try:
        lay = layout(data)
        _check_donor(lay, MASK)
    except ModelError as e:
        return [f"{path}: {e}"]
    fmdb = button_fmdb(label) if label else DISPLAYS[display][2]
    if lay["name"] != fmdb or lay["file_name"] != f"{DONOR_PROJECT}.{fmdb}":
        bad.append(f"{path}: names {lay['name']} / {lay['file_name']}")
    bad += _dict_problems(data, path, fmdb)
    if lay["materials"][GLOW_MATERIAL]["textures"].count(MASK) != 1 or DONOR_MASK in sum(
            (m["textures"] for m in lay["materials"].values()), []):
        bad.append(f"{path}: {GLOW_MATERIAL} doesn't read {MASK} (textures {lay['materials'][GLOW_MATERIAL]})")
    mesh = mesh_for(display, label)
    body, empty = lay["shapes"][BODY_SHAPE], lay["shapes"][EMPTY_SHAPE]
    for k, (m, lod) in enumerate(zip(body["meshes"], _lods(mesh, len(body["meshes"])))):
        want = [i for t in lod for i in t]
        got = list(struct.unpack_from(f"<{m['count']}H", data, m["ibuf"]))
        if m["first"] != 0 or got != want or struct.unpack_from("<II", data, m["sub"]) != (0, len(want)):
            bad.append(f"{path}: LOD {k} doesn't draw the {what} ({m['count']} indices from vertex {m['first']})")
    for k, m in enumerate(empty["meshes"]):
        if m["count"] != 3 or any(struct.unpack_from("<3H", data, m["ibuf"])):
            bad.append(f"{path}: the crystal's LOD {k} isn't empty")
    n, s = len(mesh.pos), body["stride"]
    rec = np.frombuffer(data, np.uint8, n * s, body["vbuf"]).reshape(n, s)
    pos = rec[:, 0:8].copy().view(np.float16).astype(np.float64)[:, :3]
    if np.abs(pos - np.array(mesh.pos)).max() > 2e-3:
        bad.append(f"{path}: vertex positions differ from the {what}'s")
    nrm = np.array([_snorm10(int(w)) for w in rec[:, 8:12].copy().view("<u4").ravel()])
    if (np.einsum("ij,ij->i", nrm, np.array(mesh.nrm)) < 0.99).any():
        bad.append(f"{path}: vertex normals differ")
    uv = rec[:, 16:20].copy().view("<u2").reshape(n, 2) / 65535.0
    want_uv = np.array([PART_UV[p] for p in mesh.part])
    if np.abs(uv - want_uv).max() > 1e-4:
        bad.append(f"{path}: UVs off the neutral points")
    tris = np.array([t for lod in _lods(mesh, len(body["meshes"])) for t in lod])
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    if (np.einsum("ij,ij->i", fn, nrm[tris].sum(1)) <= 0).any():
        bad.append(f"{path}: a triangle faces against its normals")
    box = struct.unpack_from(f"<{6 * body['nboxes']}f", data, body["bounds"])
    lo, hi = pos.min(0), pos.max(0)
    for b in range(body["nboxes"]):
        c, h = np.array(box[6 * b:6 * b + 3]), np.array(box[6 * b + 3:6 * b + 6])
        if np.abs(c - (lo + hi) / 2).max() > 1e-3 or np.abs(h - (hi - lo) / 2).max() > 1e-3:
            bad.append(f"{path}: bounding box {b} doesn't fit the item")
            break
    sph = struct.unpack_from("<4f", data, body["sphere"])
    if np.sqrt(((pos - np.array(sph[:3])) ** 2).sum(1)).max() > sph[3] + 1e-3:
        bad.append(f"{path}: bounding sphere {sph} doesn't hold the item")
    at = glow_params(data, GLOW_MATERIAL)
    colour, strength = glow_for(label or display)
    got_c = struct.unpack_from("<4f", data, at["ns_param_color5"])
    got_s = struct.unpack_from("<f", data, at["ns_emission_intensity"])[0]
    if any(abs(a - b) > 1e-4 for a, b in zip(got_c, colour)) or abs(got_s - strength) > 1e-4:
        bad.append(f"{path}: glow {got_c} x {got_s}, want {colour} x {strength}")
    return bad


def verify_mask(data):
    """Problems with the built mask texture: its name, every block's value by side."""
    from parity import _cosmetics_tex as tex
    bad = []
    texs = tex.bntx_textures(data)
    if [t["name"] for t in texs] != [MASK]:
        bad.append(f"{MASK_FILE}: names {[t['name'] for t in texs]}")
    bad += res_dict.problems(data, MASK_FILE)
    if not res_dict.has(data, MASK):
        bad.append(f"{MASK_FILE}: its texture dictionary doesn't find {MASK}")
    for off, (u, _v) in tex.block_positions(data).items():
        val = mask_value(u)
        if data[off:off + 8] != bytes([val, val]) + bytes(6):
            bad.append(f"{MASK_FILE}: block at {off:#x} isn't {val}")
            break
    return bad


def verify(patch, romfs=None):
    """Checks every show model in patch `patch` (and the mask, if any model is there) with verify_model / verify_mask,
    plus the size-table entries for each new file."""
    from romtools import Romfs, Restbl
    romfs = romfs or _romfs()
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    bad, found, files = [], [], []
    for display in DISPLAYS:
        if DISPLAYS[display][0] == "button":
            continue
        if os.path.exists(os.path.join(patch, model_path(display))):
            found.append(display)
            files.append(model_path(display))
            if DISPLAYS[display][0] == "sword":
                bad += verify_sword(fs.read(model_path(display)), van.read(SWORD_DONOR))
            elif DISPLAYS[display][0] == "soul":
                from parity import _soul_figures
                bad += _soul_figures.verify_figure(DISPLAYS[display][1], fs, van, romfs, patch)
            else:
                bad += verify_model(display, fs.read(model_path(display)))
    for label in BUTTON_MODELS:  # the Ocarina buttons: by label (which ones depends on the seed's controls)
        if os.path.exists(os.path.join(patch, button_model_path(label))):
            found.append(f"button:{label}")
            files.append(button_model_path(label))
            bad += verify_model(None, fs.read(button_model_path(label)), label)
    bad += soul_row_problems(fs, van, patch, romfs)
    if found:
        if any(x.startswith("button:") or DISPLAYS[x][0] not in ("sword", "soul") for x in found) \
                and not os.path.exists(os.path.join(patch, MASK_FILE)):
            bad.append(f"{MASK_FILE}: not in the patch (the models' glow mask)")
        elif os.path.exists(os.path.join(patch, MASK_FILE)):
            bad += verify_mask(fs.read(MASK_FILE))
        rstb = Restbl(fs.zs.decompress(fs.raw("System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs")))
        for rel in files + [MASK_FILE]:  # (the mask only if there)
            if os.path.exists(os.path.join(patch, rel)):
                e = rstb.get(rel[:-3])
                if e is None or e < len(fs.read(rel)):
                    bad.append(f"{rel}: size-table entry {e} for {len(fs.read(rel))} bytes")
    return bad, found


def soul_row_problems(fs, van, patch, romfs):
    """Checks every ActorInfo row the patch adds that shows a soul (a Rando_Show_Soul* display, or any row naming a soul
    figure, like a shop shelf type). Its model has to be the enemy's own figure (parity/_soul_figures.py), not a
    one-colour glow figure, and its heaps have to hold what the Hall of Fallen Foes figure's do (the same skeleton and
    materials)."""
    from romtools import byml_load
    table = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
    if not os.path.exists(os.path.join(patch, table)):
        return []
    from parity import _soul_figures
    old = {r["__RowId"] for r in byml_load(van.read(table), allow_big=True)[0]}
    rows = [r for r in byml_load(fs.read(table), allow_big=True)[0] if r["__RowId"] not in old]
    # (a regional soul's display shows its boss's or enemy's figure: the figure's own soul key, DISPLAYS)
    figures = {f: k for k, (_d, f) in SOUL_DISPLAYS.items() if f and not k.startswith("enemy_R_")}
    displays = {d: (DISPLAYS[d][1] if DISPLAYS.get(d, ("",))[0] == "soul" else k) for k, (d, _f) in SOUL_DISPLAYS.items()}
    bad = []
    for r in rows:
        rid, fmdb, proj = r["__RowId"], r.get("FmdbName"), r.get("ModelProjectName")
        key = displays.get(rid) or figures.get(fmdb)
        if fmdb in FLAT_SOUL_FIGURES or (rid in displays and proj == DONOR_PROJECT):
            bad.append(f"{rid}: shows {proj}.{fmdb}, a one-colour glow figure (the fire arrow's metal material, every "
                       f"vertex on one point of its texture), not the enemy's own model and textures")
            continue
        if key is None or SOUL_DISPLAYS[key][1] is None:  # (the bean soul: a game actor's own model, "model_from")
            continue
        mu = _soul_figures.museum(key, romfs)
        if (proj, fmdb) != (mu["project"], SOUL_DISPLAYS[key][1]):
            bad.append(f"{rid}: shows {proj}.{fmdb}, not the {key} figure {mu['project']}.{SOUL_DISPLAYS[key][1]}")
        for h, need in mu["heaps"].items():
            if int(r.get(h) or 0) < need:
                bad.append(f"{rid}: {h} {r.get(h)} is below the Hall of Fallen Foes figure's {need} "
                           f"({mu['actor']}: the same skeleton and materials)")
    return bad


def verify_note(patch, note, romfs):
    """A _gaps_check reader (parity/_gaps_check.READERS: "show_models": ("_show_models", "verify_note")). Every model
    the note's displays need has to be in the patch and read back right (verify). The note is {"displays": [...],
    "controls", "controller"}, and an Ocarina note item's model is the one under those."""
    bad, found = verify(patch, romfs)
    have = set(found)
    want = set()
    for d in note.get("displays", []):
        key = d
        if DISPLAYS.get(d, ("",))[0] == "button":
            key = f"button:{button_label(d, note.get('controls'), note.get('controller'))}"
            want.add(key)
        if key not in have:
            bad.append(f"{model_path(d, note.get('controls'), note.get('controller'))}: not in the patch ({d})")
    for key in sorted(k for k in have if k.startswith("button:") and k not in want):  # no button for other controls
        bad.append(f"{button_model_path(key[7:])}: an Ocarina button the seed's controls ({note.get('controls')}) and "
                   f"controller ({note.get('controller')}) don't show")
    return bad
