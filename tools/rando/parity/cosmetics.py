"""Parity plugin: OoT Randomizer's cosmetic settings (never touch logic).

What the remake can show using only data the game already has:
- Music: area music shuffled between areas or silenced, fanfares shuffled or silenced (the ocarina song playbacks go
  with them), and normal battle music turned off. These are sound link edits (SLink2, which stream a music key
  plays) plus, for battle music, the enemies' BattlePresentationParam (BYML in Pack/Actor/Enemy_*.pack.zs, a
  standard "packs" edit).
- Sound effects: the keys that play the sounds OoTR lets you change get pointed at another sound in the same actor's
  sound archives, or at the game's silent asset "@Blank". Link's voice can be silenced per age, and the ocarina can
  play with the Skull Kid's flute notes (the only other full note set in the game).
- Kokiri tunic colour: every texture of the tunic (TUNIC_TEXTURES, so the plaid, both vests and the cloth parts, in
  BC1/BC3 and ASTC) recoloured in place. Only its green changes, at its own brightness against the shirt's. Child
  and adult Link share the plaid, and so do Mido's clothes, a Kokiri bed blanket, the Kokiri tunic item models and
  the Fairy Ocarina holder.
- Goron/Zora tunics, both gauntlets and the mirror shield's frame (EQUIPMENT): their textures recoloured in place,
  one part each. Parts are picked by hue, and by texture area for the shield frame (_cosmetics_tex.SELECTIONS /
  ZONES). Models that share a texture but have to keep their look read a vanilla copy (the gold gauntlets' silver
  hand, and the tunic item models when correct_model_colors is off).
- HUD hearts and magic meter (HUD, _cosmetics_hud): their coloured textures in the HUD's texture archive and two
  layout colours. With correct_model_colors the magic jar models change too.
- Sword, boomerang and bombchu trails and Navi's glow (EFFECTS, _cosmetics_vfx): colour values in the particle
  effects, edited in place.
- default_targeting sets the default of the remake's own Targeting Type option (save data). credits_music makes the
  staff credits play shuffled area music.

Sound, texture, effect and HUD edits are binary edits inside compressed files, so they go in the plan's "cosmetics"
section. tools/make_patch.py writes them through _cosmetics_apply.build, and the app runs the same script after it
(with --check to read them back):
    python tools/make_patch.py ROMFS OUT/patch OUT/plan.json
    python tools/rando/parity/_cosmetics_apply.py ROMFS OUT/patch OUT/plan.json
Random choices come from a generator seeded with the seed, so a seed always comes out the same.
"""
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SOUND = os.path.join(HERE, "data", "rando", "cosmetics_sound.json")
TUNIC_TEXTURE = "Tex/Angin_Tile_A_Alb.bntx.zs"
# The whole Kokiri tunic, child and adult. The shirt comes first because the others keep their brightness against it.
# Measured share of tunic green in each: all >= 0.95 except the child's trouser trims (0.55), whose other colours stay
# since tunic_map is selective. Not in here: boots, gloves, belts, feathers, leather (no green). These textures are
# also read by the Kokiri tunic item models, the hat in its scenes and Dark Link, which wear the colour too, and by
# Mido and the Fairy Ocarina holder, which get a vanilla copy (TUNIC_SHARED).
TUNIC_TEXTURES = (TUNIC_TEXTURE, "Tex/Angin_Tile_A_Dark_Alb.bntx.zs", "Tex/Mt_Vest_Player_Child_Alb.bntx.zs",
                  "Tex/Mt_Cloth_Parts_Player_Child_Alb.bntx.zs", "Tex/Mt_PantsParts_Player_Child_Alb.bntx.zs",
                  "Tex/Mt_Vest_Player_Adult_Alb.bntx.zs", "Tex/Mt_Angin_Acs_Player_Adult_Alb.bntx.zs")
# Models outside Link's that read a tunic texture and have to keep their own colours: Mido's clothes and the Fairy
# Ocarina's holder. Without this, recolouring the tunic turns Mido red.
# {texture: (a vanilla copy's name, same length; [their model files])}
# Every other user wears the tunic: the Kokiri Tunic item models, Link's hat in its scenes, Dark Link. Saria's and the
# Kokiri bed's look-alike names are separate textures.
TUNIC_SHARED = {TUNIC_TEXTURE: ("Angin_Tile_K_Alb", ["Npc_Kokiri_MC_Mido.Npc_Kokiri_MC_Mido",
                                                     "Item_OcarinaHolder_Fairy.Item_OcarinaHolder_Fairy"])}
BLANK = "@Blank"


def _tex(name):
    return f"Tex/{name}.bntx.zs"


# Other equipment colours.
# {setting: (OoTR colour table in Colors.py, its default name, the selection in _cosmetics_tex.SELECTIONS, the
# textures, the reference texture, {model reading a texture that must keep its vanilla look: [its textures]})}
# The default name is the remake's own look and gets left alone. The reference texture's selected part averages to
# the chosen colour.
# I listed every model that reads each texture (all of Model/, plus scenes, effects and UI for the names). The tunic
# textures are read by Link's armour model and its item model (Obj_Armor_*, correct_model_colors). The gauntlet metal
# textures are only read by the two gauntlet models, since the item actors use the worn model, and the mirror
# shield's by its one model. The gold gauntlets' model also reads the silver gauntlets' metal (a silver hand of 9,528
# vertices under its gold plates of 6,128), so it gets a vanilla copy and the silver colour stays on the silver
# gauntlets.
GORON = ("Mt_Angin_Armor_Adult_Goron_Alb", "Mt_Vest_Armor_Adult_Goron_Alb", "Mt_Inner_Armor_Adult_Goron_Alb")
ZORA = ("Mt_Angin_Armor_Adult_Zora_Alb", "Mt_Angin_Acs_Armor_Adult_Zora_Alb", "Mt_Vest_Armor_Adult_Zora_Alb",
        "Mt_Parts_Armor_Adult_Zora_Alb")
SILVER = "Mt_Silver_Armor_Adult_Gauntlet_Silver_Alb"
GOLD = "Mt_Gold_Armor_Adult_Gauntlet_Gold_Alb"
MIRROR = "Mt_Weapon_Shield_Mirror_Alb"
EQUIPMENT = {
    "goron_color": ("tunic_colors", "Goron Red", "goron", GORON, GORON[0], {}),
    "zora_color": ("tunic_colors", "Zora Blue", "zora", ZORA, ZORA[0], {}),
    "silver_gauntlets_color": ("gauntlet_colors", "Silver", "not_jewel", (SILVER,), SILVER,
                               {"Armor_Adult_Gauntlet_Gold.Armor_Adult_Gauntlet_Gold": [SILVER]}),
    "golden_gauntlets_color": ("gauntlet_colors", "Gold", "not_jewel", (GOLD,), GOLD, {}),
    "mirror_shield_frame_color": ("shield_frame_colors", "Red", "frame", (MIRROR,), MIRROR, {}),
}
# HUD colours (tools/rando/parity/_cosmetics_hud.py).
# {setting: (OoTR table, default, selection, reference texture, HUD textures recoloured, [(layout, colour entry, its
# vanilla RGB)])}
# That covers the full heart, its glows and sparkles and the low-health outline, and the magic meter's fill, glows,
# use flash, sparkles and glow particles. I searched every layout. The heart textures are only read by the HUD hearts
# and the file-select hearts, the magic ones only by the magic meter. The empty heart, the double-defence frame and
# the meter's frame keep the remake's colours.
HUD = {
    "heart_color": ("heart_colors", "Red", "heart", "HeartW_00_ASTC4x4",
                    ["HeartW_00_ASTC4x4"] + [f"HeartGlowW_0{i}" for i in range(5)]
                    + [f"HeartKiraKira_0{i}" for i in range(6)],
                    [("PaHeartGaugeChildGauge_00", 5, [1.0, 0.2118, 0.0902]),
                     ("PaHeartGaugeChildNoGauge_00", 6, [1.0, 0.2118, 0.0902])]),
    "magic_color": ("magic_colors", "Green", "magic", "MpGaugeCenter_00",
                    ["MpGaugeCenter_00", "MpGaugeFlash_00", "MpGaugeFlash_01", "MpGaugeGlow_00", "MpGaugeGlow_01",
                     "MpKiraKira_00", "MpKiraKira_01", "MpKiraKira_02"],
                    [("PaMpGauge_00", 2, [0.051, 0.5647, 0.2902])]),
}
# correct_model_colors (OoTR also colours the matching item models): the magic jars' green. Those textures are the
# jars' own and only the two jar models read them. The heart container and heart piece models are grey textures
# tinted by their materials, so they don't change. Potions share the one bottle texture
# every bottle uses.
HUD_MODELS = {"magic_color": ["Mt_Obj_MagicJar_Large_Alb", "Mt_Obj_MagicJar_Small_Alb"]}
# With correct_model_colors False (OoTR keeps item models in their vanilla colours), the tunic item models read
# vanilla copies of the recoloured textures they share with Link.
# {colour setting: {item model: [shared textures]}}
# The gauntlets and the mirror shield have no item model of their own (Item_Gauntlet_* and Item_Shield_Mirror show
# the worn model through the same ModelInfo file), so they keep the chosen colour either way.
ITEM_MODELS = {
    "kokiri_color": {"Obj_Armor_Adult_Normal.Obj_Armor_Adult_Normal": ["Angin_Tile_A_Alb", "Mt_Angin_Acs_Player_Adult_Alb",
                                                                       "Mt_Vest_Player_Adult_Alb"],
                     "Obj_Armor_Child_Normal.Obj_Armor_Child_Normal": ["Angin_Tile_A_Alb", "Mt_Cloth_Parts_Player_Child_Alb",
                                                                       "Mt_Vest_Player_Child_Alb"]},
    "goron_color": {"Obj_Armor_Goron.Obj_Armor_Goron": ["Mt_Angin_Armor_Adult_Goron_Alb",
                                                        "Mt_Vest_Armor_Adult_Goron_Alb"]},
    "zora_color": {"Obj_Armor_Zora.Obj_Armor_Zora": ["Mt_Angin_Armor_Adult_Zora_Alb", "Mt_Angin_Acs_Armor_Adult_Zora_Alb",
                                                     "Mt_Vest_Armor_Adult_Zora_Alb", "Mt_Parts_Armor_Adult_Zora_Alb"]},
}


def _fx(name):
    return f"Effect/{name}.Nin_Ounce_NVN2.vsetb.byml.zs"


# Effect colours (particle effects, tools/rando/parity/_cosmetics_vfx.py).
# {setting: [(effect file, emitter sets, emitter name regex, colour entries)]}
# An entry is table + slot: P80/P88 Color0/1, P90 colour scale, P58 a light's colour, B60/B68 colour over life.
# "P48:white" sets the boomerang's warm set-wide tint to white so it doesn't tint the chosen colour. Compact entries
# (white/black splats) have no room for a colour and stay as they are. Navi's normal-state outer halo and the sword
# trail's second colour are like that.
# Every copy of a set is listed. The swords' slash trail is in each of Link's sword files and the Deku Stick's, but
# not in the generic Weapon_Sword file or Dark Link's sword. Navi's states are sets in static, plus her cutscene
# copy.
SWORDS = [_fx(n) for n in ("Weapon_Sword_Kokiri", "Weapon_Sword_Master", "Weapon_Sword_Biggoron",
                           "Weapon_Sword_Giant", "Weapon_Sword_BrokenGiant", "Item_DekuStick")]
STATIC = _fx("static")
NAVI_NORMAL = ["Npc_Navi_Wait_00", "Npc_Navi_Talk_00", "Npc_Navi_Attention_Enemy_00", "Npc_Navi_Attention_Enemy_01",
               "Npc_Navi_Attention_Gimmick_00", "Npc_Navi_Trail_00"]
NAVI_ENEMY = ["Npc_Navi_LockOn_Enemy_00", "Npc_Navi_LockOn_Enemy_01", "Npc_Navi_LockOn_St_Enemy_00",
              "Npc_Navi_LockOn_Ed_Enemy_00", "Npc_Navi_Talk_01", "Npc_Navi_Trail_01"]
NAVI_PROP = ["Npc_Navi_LockOn_Gimmick_00", "Npc_Navi_LockOn_St_Gimmick_00", "Npc_Navi_LockOn_Ed_Gimmick_00"]


def _navi_inner(sets, extra=()):
    return [(STATIC, sets, "PointLight", ["P58"]), (STATIC, sets, "Glow_Inside.*", ["P80", "P88", "P90"]),
            (STATIC, sets, "FairyDust.*|Ptcl.*", ["B60", "B68"])] + list(extra)


EFFECTS = {
    "sword_trail_color_inner": [(f, ["Wpn_Sword_Slash_00"], "SwordBlur", ["B60"]) for f in SWORDS],
    "boomerang_trail_color_inner": [(_fx("Item_Boomerang"), ["Wpn_Boomerang_Tail_00"], "Trail|Circle|RotatingBlur",
                                     ["P80", "B60", "P48:white"])],
    "boomerang_trail_color_outer": [(_fx("Item_Boomerang"), ["Wpn_Boomerang_Tail_00"], "Circle|RotatingBlur",
                                     ["P88", "B68", "P48:white"])],
    "bombchu_trail_color_inner": [(STATIC, ["Wpn_Trail_Bombchu_00"], "Spark_Line|Spark_Trail|SparkSplit", ["B60"])],
    "bombchu_trail_color_outer": [(STATIC, ["Wpn_Trail_Bombchu_00"], "Spark_Line|Spark_Trail", ["B68"])],
    "navi_color_default_inner": _navi_inner(NAVI_NORMAL, [
        (_fx("Dm_Npc_Navi"), ["Npc_Navi_Wait_01"], "PointLight", ["P58"]),
        (_fx("Dm_Npc_Navi"), ["Npc_Navi_Wait_01"], "Glow_Inside.*", ["P80", "P88", "P90"])]),
    "navi_color_enemy_inner": _navi_inner(NAVI_ENEMY),
    "navi_color_enemy_outer": [(STATIC, NAVI_ENEMY, "Glow_Outside.*", ["P80", "P88"])],
    "navi_color_prop_inner": _navi_inner(NAVI_PROP),
    "navi_color_prop_outer": [(STATIC, NAVI_PROP, "Glow_Outside.*", ["P80", "P88"])],
}
# OoTR colour table and default (the remake's own look) per effect setting. An "outer" setting defaults to
# "[Same as Inner]" and follows its inner colour.
EFFECT_COLOURS = {"sword_trail_color": ("sword_trail_colors", "White"),
                  "boomerang_trail_color": ("boomerang_trail_colors", "Yellow"),
                  "bombchu_trail_color": ("bombchu_trail_colors", "Red"),
                  "navi_color_default": ("NaviColors", "White"), "navi_color_enemy": ("NaviColors", "Yellow"),
                  "navi_color_prop": ("NaviColors", "Green")}
SAME = "[Same as Inner]"


def copy_name(name):
    """Texture name for a vanilla copy. It's the same length, since renames are done in place, and never the name of a
    game texture. The plaid's copy keeps the name Mido's copy has always had."""
    if name == "Angin_Tile_A_Alb":
        return TUNIC_SHARED[TUNIC_TEXTURE][0]
    if not name.endswith("_Alb") or name[-5] == "V":
        raise ValueError(f"no copy name for {name}")
    return name[:-5] + "V_Alb"

SFX_CHOICES = ("default", "none", "random-choice", "random-ear-safe", "completely-random")
SFX_SETTINGS = ("sfx_low_hp", "sfx_navi_enemy", "sfx_menu_cursor", "sfx_menu_select", "sfx_hover_boots",
                "sfx_iron_boots", "sfx_boomerang_throw", "sfx_hookshot_chain", "sfx_arrow_shot", "sfx_slingshot_shot",
                "sfx_magic_arrow_shot", "sfx_explosion", "sfx_bombchu_move", "sfx_horse_neigh", "sfx_cucco",
                "sfx_daybreak", "sfx_nightfall", "sfx_silver_rupee", "sfx_get_small_item")

OWNS = {
    # --- applied
    "kokiri_color": None,  # every named colour, "Random Choice", "Completely Random" (checked in check_settings)
    "background_music": ("normal", "off", "random"),
    "fanfares": ("normal", "off", "random"),
    "ocarina_fanfares": (False, True),
    "disable_battle_music": (False, True),
    "sfx_ocarina": ("ocarina", "flute", "random-choice"),
    "sfx_link_adult": ("Default", "Silent"),
    "sfx_link_child": ("Default", "Silent"),
    "randomize_all_cosmetics": (False, True),
    "randomize_all_sfx": (False, True),
    **{s: SFX_CHOICES for s in SFX_SETTINGS},
    **{s: None for s in EQUIPMENT},  # named colours, "Random Choice", "Completely Random" (check_settings)
    **{s: None for s in HUD},  # the same
    **{s: None for s in EFFECTS},  # the same, outer colours also "[Same as Inner]", but not Rainbow (check_settings)
    "correct_model_colors": (True, False),
    "credits_music": (False, True),
    "default_targeting": ("hold", "switch"),
    # --- the remake's own look only (why: see the module docstring)
    "a_button_color": ("N64 Blue",), "b_button_color": ("N64 Green",), "c_button_color": ("Yellow",),
    "start_button_color": ("N64 Red",),
    "navi_color_default_outer": ("[Same as Inner]",),
    "navi_color_npc_inner": ("Light Blue",), "navi_color_npc_outer": ("[Same as Inner]",),
    "sword_trail_color_outer": ("[Same as Inner]",),
    "sword_trail_duration": (4,),
    "sfx_navi_overworld": ("default",),
    "speedup_music_for_last_triforce_piece": (False,), "slowdown_music_when_lowhp": (False,),
    "custom_music_directorypicker": ("",), "display_custom_song_names": ("off",),
    "model_adult": ("Default",), "model_child": ("Default",),
    "display_dpad": ("right",), "dpad_dungeon_menu": (True,),
    "uninvert_y_axis_in_first_person_camera": (False,), "input_viewer": (False,),
}
VERIFIED = ()  # TODO: nothing seen in-game yet
# A remake setting of ours that shuffles every sound effect in the game. OoTR's randomize_all_sfx randomizes its 19
# sound settings, and Ship of Harkinian's audio editor shuffles a hand-picked 57 sound effects. Off by default.
ALL_SFX = "remake_shuffle_all_sfx"
REMAKE_SETTINGS = {ALL_SFX: (False, True)}
REMAKE_DEFAULTS = {ALL_SFX: False}


def _remake(settings, key):
    return (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS[key])
_data = None


def _sound():
    global _data
    if _data is None:
        _data = json.load(open(SOUND, encoding="utf-8"))
    return _data


def _tunic_colors():
    import Colors  # vendor/ootr, on the path while the generator runs
    return Colors.tunic_colors


def _colour_table(name):
    import Colors  # vendor/ootr, on the path while the generator runs
    return Colors.tunic_colors if name == "kokiri_color" else getattr(Colors, {**EQUIPMENT, **HUD}[name][0])


def _effect_table(name):
    import Colors
    base = name.rsplit("_", 1)[0]
    return getattr(Colors, EFFECT_COLOURS[base][0])


def check_settings(settings):
    problems = []
    for name in ("kokiri_color",) + tuple(EQUIPMENT) + tuple(HUD) + tuple(EFFECTS):
        v = getattr(settings, name, None)
        if v is not None and not _accepts(name, v):
            problems.append(f"{name} = {v!r}: cosmetics can make the named colours, 'Random Choice' and "
                            f"'Completely Random' (Rainbow animates in OoTR's own code; custom colours can't pass "
                            f"OoTR's settings check)")
    return problems


def _accepts(name, value):
    if name in EFFECTS:  # Rainbow animates in OoTR's own code
        return (value in _effect_table(name) and value != "Rainbow" or value in ("Random Choice", "Completely Random")
                or name.endswith("_outer") and value == SAME)
    if name == "kokiri_color" or name in EQUIPMENT or name in HUD:
        return value in _colour_table(name) or value in ("Random Choice", "Completely Random")
    ok = OWNS.get(name)
    return ok is None or value in ok


def pick_colour(name, value, rng):
    """('#rrggbb' or None for the remake's own look, the option shown in the log) for an equipment colour."""
    table = _colour_table(name)
    if value == "Random Choice":
        value = rng.choice(sorted(table))
    if value == "Completely Random":
        return "#%02x%02x%02x" % tuple(rng.randint(0, 255) for _ in range(3)), value
    if value == {**EQUIPMENT, **HUD}[name][1]:
        return None, value
    c = table[value]
    return "#%02x%02x%02x" % (c[0], c[1], c[2]), value


def effective(settings, rng):
    """Setting values after OoTR's randomize_all_cosmetics / randomize_all_sfx. Each randomized setting is drawn from
    OoTR's distribution, limited to values the remake can make."""
    from SettingsList import SettingInfos
    vals = {name: getattr(settings, name, None) for name in sorted(OWNS)}
    for key in ("randomize_all_cosmetics", "randomize_all_sfx"):
        if not vals.get(key):
            continue
        for name, info in sorted(SettingInfos.setting_infos.items()):
            if name not in OWNS or info.gui_params.get("randomize_key") != key:
                continue
            pairs = [(c, w) for c, w in info.gui_params.get("distribution", []) if _accepts(name, c)]
            if pairs:
                choices, weights = zip(*pairs)
                vals[name] = rng.choices(choices, weights=weights)[0]
    return vals


def tunic_colour(value, rng):
    """'#rrggbb' for a kokiri_color value, or None for the vanilla look."""
    colors = _tunic_colors()
    if value == "Random Choice":
        value = rng.choice(sorted(colors))
    if value == "Completely Random":
        rgb = [rng.randint(0, 255) for _ in range(3)]
        return "#%02x%02x%02x" % tuple(rgb), "Completely Random"
    if value == "Kokiri Green":
        return None, value
    c = colors[value]
    return "#%02x%02x%02x" % (c[0], c[1], c[2]), value


def _point(rows, asset):
    return [{"user": r["user"], "key": r["key"], "asset": asset, "was": r["was"]} for r in rows if r["was"] != asset]


def _fanfare_rows(d):
    """OoTR's fanfares: the item-get, heart, medal, stone, game over... players, the cutscene jingles and the chest
    suspense. A row's "also" lists more keys for the same sound."""
    return d["fanfares"] + d.get("jingles", [])


def _music_sources(d):
    """Whole looping tracks from the area slots, the extras and the event themes. The shops' one 60 s loop is in the
    extras as BGM_Shop_KokiriForest."""
    return sorted({r["track"] for r in d["bgm_area_slots"]} | {e["track"] for e in d["bgm_extra_tracks"]}
                  | {g["group"] for g in d.get("bgm_event_groups", []) if g["group"] != "BGM_Shop"})


def music_plan(vals, rng, log):
    """Music sound-link edits. A music key pointed at another whole track plays it to the end and loops it on that
    track's own loop points. For that, _cosmetics_apply.build has the music graph (bgm.byml) drop the fixed length and
    start offset of every node that plays such a key (_cosmetics_bgm). log["music_check"] is what the read-back checks:
    area and event slots play looping tracks, jingles play tracks that end."""
    d = _sound()
    ops, packs = [], []
    check = {}
    bgm = vals["background_music"]
    events = d.get("bgm_event_groups", [])
    if bgm == "off":
        ops += _point(d["bgm_area_silence"], BLANK)
        ops += _point([r for g in events for r in g["rows"]], BLANK)  # OoTR's "off": its event themes too
    elif bgm == "random":
        # The battle slot stays out of the shuffle if it can't play.
        slots = [r for r in d["bgm_area_slots"]
                 if not (vals["disable_battle_music"] and r["player"] == "BGM_EnemyBattle")]
        sources = _music_sources(d)
        picks = rng.sample(sources, len(slots))
        chosen = {}
        for slot, track in zip(slots, picks):
            log.setdefault("background_music", {})[slot["player"]] = track
            check.setdefault("area", {})[slot["player"]] = track
            chosen[slot["track"]] = track
            if track != slot["track"]:
                ops.append({"user": slot["user"], "key": slot["key"], "asset": track, "was": slot["track"]})
        # The layered players (Kokiri Forest, Hyrule Field, Market...) each play one whole track from the same pool,
        # starting at their first node. Keys on other paths (parallel fork branches, outros) get silenced, overlays too.
        for lp in d.get("bgm_area_layered", []):
            track = rng.choice(sources)
            log.setdefault("background_music", {})[lp["player"]] = track
            check.setdefault("area", {})[lp["player"]] = track
            ops += _point(lp["play"], track)
            ops += _point(lp["silence"], BLANK)
        for ov in d.get("bgm_overlays", []):
            ops += _point(ov["silence"], BLANK)
        # Event music (the owl, the shops, cutscene loops). OoTR replaces a sequence everywhere it plays, so a group
        # whose track belongs to an area slot follows that slot. The others draw unused tracks from the pool.
        free = [t for t in sources if t not in set(picks)]
        own = [g for g in events if g["group"] not in chosen]
        extra = rng.sample(free, len(own)) if len(free) >= len(own) else [rng.choice(sources) for _ in own]
        picked = dict(zip((g["group"] for g in own), extra))
        for g in events:
            track = chosen.get(g["group"]) or picked[g["group"]]
            log.setdefault("background_music", {})[g["group"]] = track
            check.setdefault("event", {})[g["group"]] = track
            ops += _point(g["rows"], track)
    ff = vals["fanfares"]
    songs = d["ocarina_songs"]
    fan = _fanfare_rows(d)
    if ff == "off":
        ops += _point([dict(r, was=f["track"]) for f in fan for r in [f] + f.get("also", [])], BLANK)
        if vals["ocarina_fanfares"]:
            ops += _point([dict(r, was=r["track"]) for r in songs], BLANK)
    elif ff == "random":
        # One pool, as in OoT Randomizer (Music.py fanfare_sequence_ids, Game Over included) and Ship of Harkinian
        # (AudioCollection SEQ_FANFARE, no default exclusions), so no length groups. The ocarina song playbacks are a
        # pool of their own, like Ship of Harkinian's SEQ_OCARINA. They're Ocarina.bars sounds of the Ocarina user, not
        # BGM_Static streams, so they can't play in a fanfare player. OoTR mixes them in because they're all sequences
        # there.
        pools = [("fanfares", fan)]
        if vals["ocarina_fanfares"]:
            pools.append(("ocarina songs", songs))
        for name, rows in pools:
            tracks = [r["track"] for r in rows]
            shuffled = rng.sample(tracks, len(tracks))
            for r, t in zip(rows, shuffled):
                log.setdefault("fanfares", {})[r.get("player") or r["key"]] = t
                if name == "fanfares":
                    check.setdefault("jingle", {})[r.get("player") or r["key"]] = t
                if t != r["track"]:
                    ops += [{"user": k["user"], "key": k["key"], "asset": t, "was": r["track"]}
                            for k in [r] + r.get("also", [])]
    if vals["disable_battle_music"]:
        # Enemies stop asking for BGM_EnemyBattle and the area music keeps playing (OoTR's disable_battle_music).
        # "pack": "*" edits a shared parameter file in every pack that holds it. EnemyCommon is also in
        # Dm_Enemy_DungeonBoss_Volvagia, which isn't an Enemy_ pack, and the patcher refuses a file whose copies get
        # different edits.
        packs += [{"pack": "*", "file": f, "set": {"BgmName": ""}}
                  for f in sorted({p["file"] for p in d["battle_presentation"]})]
    if check:
        log["music_check"] = check
    return ops, packs


def sfx_plan(vals, rng, log):
    d = _sound()
    ops = []
    for name in SFX_SETTINGS:
        value = vals[name]
        rows = d["sfx"].get(name, [])
        if value == "default" or not rows:
            continue
        if value == "none":
            ops += _point(rows, BLANK)
            log.setdefault("sfx", {})[name] = "none"
            continue
        targets = {r["was"] for r in rows}
        groups = {}
        for r in rows:  # one pick per set of actors sharing the sound (they all hear the same replacement)
            groups.setdefault(tuple(sorted(r["aliases"])), []).append(r)
        picked = []
        for aliases, grows in sorted(groups.items()):
            # The replacement has to be one every actor of the group loads itself (its own .bars files, BarslistPack).
            names = None
            entries = {}
            for u in aliases:
                mine = {e["sound"]: e for b in d["sfx_users"][u] for e in d["sfx_bars"].get(b, [])}
                entries.update(mine)
                names = set(mine) if names is None else names & set(mine)
            # The replacement is the same kind as the target. A loop in a key the game only starts would never stop, and
            # a one-shot in a loop's key (the game stops those) just goes quiet.
            loops = any(r.get("loop") for r in grows)
            pool = [entries[s_] for s_ in sorted(names or ()) if s_ not in targets]
            if value == "random-ear-safe":
                pool = [e for e in pool if e["ear_safe"]]
            elif value == "random-choice":
                pool = [e for e in pool if e["ear_safe"] or e["secs"] <= 4]
            pool = [e for e in pool if bool(e["loop"]) == loops]
            if not pool:
                log.setdefault("sfx_unchanged", []).append(
                    f"{name}: no other {'looping' if loops else 'one-shot'} sound"
                    f"{' that is ear-safe' if value == 'random-ear-safe' else ''} in {', '.join(aliases)}'s own "
                    f"sound files")
                continue
            pick = rng.choice(pool)["sound"]
            picked.append(pick)
            ops += _point(grows, pick)
        log.setdefault("sfx", {})[name] = picked
    oc = vals["sfx_ocarina"]
    if oc == "random-choice":
        oc = rng.choice(["ocarina", "flute"])
    if oc == "flute":
        ops += [{"user": r["user"], "key": r["key"], "asset": r["flute"], "was": r["was"]} for r in d["ocarina_notes"]]
    log["sfx_ocarina"] = oc
    for age in ("adult", "child"):
        if vals[f"sfx_link_{age}"] == "Silent":
            ops += _point(d["link_voice"][age], BLANK)
    return ops


def all_sfx_plan(settings, log):
    """remake_shuffle_all_sfx: every sound effect swaps with another one from the same sound archive and of the same
    kind (voice or not, loop or one-shot and its length band, streamed or not, see _cosmetics_build.all_sound_effects).
    A key only plays what its actor has loaded and an archive loads whole, so nothing new gets loaded and nothing can
    go missing. It has its own generator, so the other sound and music choices stay as they were. It's listed before
    the OoTR settings' picks, which win on their own keys."""
    if not _remake(settings, ALL_SFX):
        return []
    rng = random.Random(f"cosmetics-sfx-all-{settings.seed}")
    remap = {}
    for _arch, kinds in sorted(_sound().get("sfx_all", {}).items()):
        for _kind, names in sorted(kinds.items()):
            for a, b in zip(names, rng.sample(names, len(names))):
                if a != b:
                    remap[a] = b
    log["sfx_all"] = {"sounds": len(remap)}
    return [{"remap": remap, "note": ALL_SFX}] if remap else []


def effect_plan(vals, rng, log):
    """The plan's "effects" edits: [{"file", "sets", "emitters", "entries", "colour", "note"}]."""
    import Colors
    out = []
    for base, (table_name, default) in EFFECT_COLOURS.items():
        table = getattr(Colors, table_name)
        names = sorted(n for n in table if n != "Rainbow")
        opts = {"inner": vals[f"{base}_inner"], "outer": vals.get(f"{base}_outer", SAME)}
        for part in ("inner", "outer"):
            if opts[part] == "Random Choice":
                opts[part] = rng.choice(names)
        if opts["outer"] == SAME:
            opts["outer"] = opts["inner"]
        for index, part in enumerate(("inner", "outer")):
            setting, opt = f"{base}_{part}", opts[part]
            if setting not in EFFECTS or opt == default:
                continue  # the remake's own look (an outer colour the remake can't change stays as it is)
            if opt == "Completely Random":
                c = tuple(rng.randint(0, 255) for _ in range(3))
            else:
                c = table[opt][index] if table_name == "NaviColors" else table[opt]
            colour = "#%02x%02x%02x" % (c[0], c[1], c[2])
            log[setting] = {"option": opt, "color": colour}
            out += [{"file": f, "sets": sets, "emitters": emitters, "entries": entries, "colour": colour,
                     "note": f"{setting} {opt}"} for f, sets, emitters, entries in EFFECTS[setting]]
    return out


# The staff credits' three soundtracks (6-channel cutscene streams, 311 s, 122 s and 49 s), each a cutscene sound
# user's "SoundTrack" key. OoTR's credits_music puts the credits songs in the background music shuffle. Here each
# credits part plays a looping area track instead. The remake's credits streams don't loop, so they don't go into
# areas.
CREDITS = [{"user": f"Event_Dm_StaffCredit_{n}", "key": "SoundTrack", "was": f"Dm_StaffCredit_{n}"}
           for n in ("0000", "0005", "0010")]


def credits_plan(vals, rng, log):
    if not (vals["credits_music"] and vals["background_music"] == "random"):
        return []
    d = _sound()
    pool = _music_sources(d)
    ops = []
    for row in CREDITS:
        track = rng.choice(pool)
        log.setdefault("credits_music", {})[row["user"]] = track
        ops.append(dict(row, asset=track))
    return ops


def _keep_vanilla(model, textures, names, new_files):
    """Makes the model read vanilla copies of these textures (same-length renames, each copy written once)."""
    have = {f["to"] for f in new_files}
    renames = []
    for tex in textures:
        copy = copy_name(tex)
        renames.append([tex, copy])
        if _tex(copy) not in have:
            new_files.append({"to": _tex(copy), "from": _tex(tex), "rename": [[tex, copy]],
                              "note": f"vanilla {tex} for {model.split('.')[0]}"})
            have.add(_tex(copy))
    names.append({"file": f"Model/{model}.bfres.zs", "rename": renames})


def world_plan(settings, world):
    rng = random.Random(f"cosmetics-{settings.seed}")
    vals = effective(settings, rng)
    log = {"settings": {k: vals[k] for k in sorted(vals) if vals[k] != getattr(settings, k, None)}}
    textures = []
    colour, label = tunic_colour(vals["kokiri_color"], rng)
    log["kokiri_color"] = {"option": label, "color": colour or "vanilla"}
    names, new_files = [], []
    if colour:
        textures += [{"file": t, "colour": colour, "ref": TUNIC_TEXTURE, "note": f"kokiri_color {label}"}
                     for t in TUNIC_TEXTURES]
        # Other models using a tunic texture keep their colours by reading a vanilla copy under a new name.
        for tex, (copy, models) in TUNIC_SHARED.items():
            name = tex.split("/")[-1].split(".")[0]
            new_files.append({"to": f"Tex/{copy}.bntx.zs", "from": tex, "rename": [[name, copy]],
                              "note": f"vanilla {name} for {', '.join(m.split('.')[0] for m in models)}"})
            names += [{"file": f"Model/{m}.bfres.zs", "rename": [[name, copy]]} for m in models]
    # The other equipment colours draw from their own generator, so a seed's music and sounds stay as they were.
    rng_c = random.Random(f"cosmetics-colours-{settings.seed}")
    recoloured = {"kokiri_color": bool(colour)}
    for name, (_table, _default, select, texs, ref, keep) in EQUIPMENT.items():
        c, lbl = pick_colour(name, vals[name], rng_c)
        recoloured[name] = bool(c)
        if not c:
            continue
        log[name] = {"option": lbl, "color": c}
        textures += [{"file": _tex(t), "colour": c, "ref": _tex(ref), "select": select, "note": f"{name} {lbl}"}
                     for t in texs]
        for model, shared in sorted(keep.items()):
            _keep_vanilla(model, shared, names, new_files)
    if not vals["correct_model_colors"]:  # the tunic item models keep the remake's own colours
        for name, models in ITEM_MODELS.items():
            if recoloured.get(name):
                for model, shared in sorted(models.items()):
                    _keep_vanilla(model, shared, names, new_files)
        log["correct_model_colors"] = False
    gamedata = []
    if vals["default_targeting"] == "switch":
        # The remake's own Targeting Type option (option.sav, SystemOption_00.msbt "LockOnType"), where Toggle is OoTR's
        # switch. It's the default for a fresh option file and gets reset to it on a new game file (reset type 8, like
        # the option file's other new-game values), since OoTR sets it per new save. The Options menu can still change
        # it.
        gamedata.append({"defaults": {"OptionData.LockOnType": "Switch"},
                         "reset_type": {"OptionData.LockOnType": 4 | 8}})
        log["default_targeting"] = "switch"
    hud = []
    for name, (_table, _default, select, ref, texs, layout_colours) in HUD.items():
        c, lbl = pick_colour(name, vals[name], rng_c)
        if not c:
            continue
        log[name] = {"option": lbl, "color": c}
        hud += [{"kind": "texture", "name": t, "select": select, "ref": ref, "colour": c, "note": f"{name} {lbl}"}
                for t in texs]
        hud += [{"kind": "layout_colour", "layout": lay, "index": i, "was": was, "colour": c,
                 "note": f"{name} {lbl}"} for lay, i, was in layout_colours]
        if vals["correct_model_colors"]:
            textures += [{"file": _tex(t), "colour": c, "ref": _tex(t), "select": select, "note": f"{name} {lbl}"}
                         for t in HUD_MODELS.get(name, [])]
    effects = effect_plan(vals, rng_c, log)
    music_ops, packs = music_plan(vals, rng, log)
    slink = all_sfx_plan(settings, log) + music_ops + sfx_plan(vals, rng, log) + credits_plan(vals, rng_c, log)
    out = {}
    if names or new_files:
        out["names"], out["new_files"] = names, new_files
    if gamedata:
        out["gamedata"] = gamedata
    if slink or textures or effects or hud:
        out["cosmetics"] = {"slink": slink, "textures": textures, "log": log,
                            "apply": "python tools/rando/parity/_cosmetics_apply.py ROMFS OUT/patch OUT/plan.json "
                                     "(after tools/make_patch.py)"}
        if effects:  # only when chosen: a plan without them stays as it was
            out["cosmetics"]["effects"] = effects
        if hud:
            out["cosmetics"]["hud"] = hud
    elif log:
        out["cosmetics"] = {"log": log}
    if packs:
        out["packs"] = packs
    return out
