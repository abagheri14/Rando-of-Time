"""Player settings fast_bunny_hood, deadly_bonks and auto_equip_masks (owned by the story plugin).
The research is in my notes player_settings.md (copied into my working notes). Every node index below was read from
the vanilla files and gets checked again at plan time (_check_sources). All three AI files are path-keyed and
identical in Player_Base / Player_Child / Player_Adult, so every edit goes to all of them ("pack": "*").

fast_bunny_hood True (experimental)
In OoTR the Bunny Hood makes Link 1.5x faster, like in Majora's Mask.
  The game has no speed parameter for masks. MaskParam only holds UV offsets, and PlayerGameParam has no run speed
  (its GroundSpeedScale is global). Ground movement looks animation-driven, so the walk action plays the player's AS
  faster while the hood is on. It's added to AI/Player.action.walk.module.ainb and
  AI/Player.action.lockonmove.module.ainb as one more child of the module's root Simultaneous (beside
  ExecutePlayerMove / ExecutePlayerLockOnMove):
      BoolSelector( QueryMathEqualS32( QueryPlayerGetSelectedHeadArmor.HeadArmor == 5 ) )
          True:  ExecuteSetASRate {ASSlot 0, ASRate 1.5, IsUndoOnLeave True}
          False: ExecuteGenericSetResultSuccess
  Head-armor values (code 0x4b7b20): 0 none, 1 Lens, 2 Keaton, 3 Skull, 4 Spooky, 5 Bunny, 6 Truth, 7 Goron, 8 Zora,
  9 Gerudo.
  Per frame while walking it's one BoolSelector on a cached bool (both queries are OutputOnlyOnEnter, so they run
  once when the walk starts), plus ExecuteSetASRate's update (one float store) when the hood is on. Nothing runs
  outside the walk / Z-target move actions, and leaving them restores the rate (IsUndoOnLeave).
  In-game check: as child with the Bunny Hood on, run a measured stretch (the Kokiri Forest bridge, say) and time it
  against the same run without the hood. It has to take about 2/3 of the time. It fails if Link only animates
  faster without covering ground faster, if the rate is stuck after a roll/jump (it has to be normal in other
  actions), or if nothing changes at all. In that last case the AS rate isn't what moves Link, and there's no other
  data route.

deadly_bonks 'half'/'normal'/'double'/'quadruple'/'ohko' (experimental)
In OoTR rolling into a wall or object hurts Link by 1/2/4/8 quarter hearts, or kills. Nayru's Love protects, and the
damage ignores damage_multiplier.
  The roll bonk is an AI branch. In AI/Player.action.rolling.module.ainb, SelectorPlayerRolling (node 3) case
  "WallHit" -> ExecutePlayerWallHit (node 4), which only plays the bonk (no life call, code 0x2815a50). The WallHit
  case now starts a Simultaneous holding the vanilla node 4 and the damage branch:
      SelectorMathLessOrEqualF32( PlayerStatus.NayruLoveTime <= 0 )          (Nayru's Love not running)
          if_true:  ohko:  OneShotEventTriggerPlayerRequestNoAnmDie
                    else:  SelectorMathLessOrEqualS32( PlayerStatus.Life - N <= 0 )
                               if_true:  OneShotEventTriggerPlayerRequestNoAnmDie
                               if_false: OneShotSetGameDataInt PlayerStatus.Life = Life - N
          if_false: ExecuteGenericSetResultSuccess
  PlayerStatus.NayruLoveTime is Nayru's Love's remaining time in frames. The code sets it to the param's 34 x 60 at
  the cast and to 0 at the end (0x2e77fb0 / 0x2e780ac). PlayerStatus.Life is the player's life in quarter hearts
  (LifeGameDataSyncParam.LifeGameDataHash). The selectors choose once (SelectChildOnEnterOnly) and every query is
  OutputOnlyOnEnter, so the whole branch runs once per bonk and nothing runs at all outside a bonk.
  No AI node damages the player directly. OneShotLifeSetOwnLife only heals or changes max life (code 0x28e06b0, and
  a negative heal is ignored at 0x49dc64). So:
  - half..quadruple write the save-data life. Whether the live life follows a mid-scene write is unproven.
    In-game check: full hearts, roll into a wall. The HUD has to drop by N quarters (1/2/4/8) at once, and the next
    enemy hit has to start from the lowered life (not snap back to full). With Nayru's Love active a bonk has to do
    nothing. At N quarters or fewer left, a bonk has to kill (same as ohko). It fails if the HUD and the real life
    disagree, or if a later heal/hit restores the old value.
  - ohko (and "would drop to 0") requests a death without the dying animation. That's a player request flag (code
    0x28d74a0) that no vanilla event uses. In-game check: a bonk has to kill Link (game over or fairy). With a
    bottled fairy the fairy has to revive him, because OoTR's logic (can_bonk) counts on it. With Nayru's Love
    active the bonk must not kill. It fails if nothing happens, if Link dies without a game over screen or
    softlocks, or if the fairy doesn't revive.

auto_equip_masks (default OFF in OoTR)
In OoTR masks stay on through scene changes and savewarps.
  The remake already keeps a worn mask through scene changes and saves. The worn state is
  PlayerStatus.IsActiveHeadArmor (Bool, ResetTypeValue 8 = only a new file resets it, saved). The player's
  head-armor updater (code 0x4b7b20) puts the mask on or takes it off to match it on every update, and only time
  travel clears it (ReplaceEquipmentForEraChange Event9), which is what OoTR ON does without equip swap. So True is
  just the remake's own behaviour with no edit, and it's the remake's default (my call: config/rando_settings.json
  and the app's default are True). False (OoTR's default, from an OoTR preset or settings string for example, or
  picked in the app) plays as OoTR's OFF through off_plan() below (experimental).
  The setting is in OoTR's settings string, which salts OoTR's RNG, so resolve_settings() leaves it out of the salt.
  It changes no world, and with True as the new default the default seeds keep their fill.
  In-game check for True: as child put a mask on, walk through a loading zone, enter a house, save and reload. The
  mask has to still be on. Pull the Master Sword and come back, and it has to be off. For False, off_plan() has the
  check."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
GLOBAL = "Pack/AI.Global.Product.111.pack.zs"
WALK = "AI/Player.action.walk.module.ainb"
LOCKON = "AI/Player.action.lockonmove.module.ainb"
ROLL = "AI/Player.action.rolling.module.ainb"
BUNNY_FILES = (WALK, LOCKON)
BUNNY = 5  # QueryPlayerGetSelectedHeadArmor's value for Armor_Child_Mask_Bunny
BUNNY_RATE = 1.5
BONK_QUARTERS = {"half": 1, "normal": 2, "double": 4, "quadruple": 8}  # OoTR's 1/4, 1/2, 1, 2 hearts
BONK_MODES = ("none",) + tuple(BONK_QUARTERS) + ("ohko",)
ROLL_SELECTOR, ROLL_WALLHIT = 3, 4  # SelectorPlayerRolling, ExecutePlayerWallHit (its "WallHit" case)
STRUCT, LIFE, NAYRU = "PlayerStatus", "Life", "NayruLoveTime"

OWNS = {
    "fast_bunny_hood": (False, True),
    "deadly_bonks": BONK_MODES,
    "auto_equip_masks": (False, True),
}


def _src(pack, file):
    return {"pack": pack, "file": file}


# Node templates by label, as (source file, index, node name). Unnamed nodes use their type name. Inputs are constant.
SRC = {
    "head": (_src(GLOBAL, "AI/Player.event.root.ainb"), 644, "QueryPlayerGetSelectedHeadArmor"),
    "eq": (_src(GLOBAL, "AI/SetAutoNearAndFar.module.ainb"), 2, "QueryMathEqualS32"),
    "bsel": (_src("Pack/Actor/Armor_Child_Mask_Bunny.pack.zs", "AI/Armor_Child_Mask_Bunny.root.ainb"), 5,
             "BoolSelector"),
    "rate": (_src("Pack/Actor/Enemy_Bari.pack.zs", "AI/Bari.action.interruptlightshock.module.ainb"), 41,
             "ExecuteSetASRate"),
    "done": (_src("Pack/Actor/Player_Base.pack.zs", "AI/Player.action.root.ainb"), 46,
             "ExecuteGenericSetResultSuccess"),
    "sim": (_src(GLOBAL, "AI/EnemyCommon.PredationEatDamage.module.ainb"), 6, "Simultaneous"),
    "struct": (_src("Pack/Actor/Armor_Adult_GlassTruth.pack.zs", "AI/Armor_Adult_GlassTruth.root.ainb"), 2,
               "QueryGetNonStructGameDataStruct"),
    "geti": (_src("Pack/Actor/Armor_Adult_GlassTruth.pack.zs", "AI/Armor_Adult_GlassTruth.root.ainb"), 4,
             "QueryGetGameDataInt"),
    "getf": (_src(GLOBAL, "AI/Player.event.root.ainb"), 199, "QueryGetGameDataFloat"),
    "sub": (_src("Pack/Actor/Npc_Kokiri_006_Child.pack.zs", "AI/Npc_Kokiri_006_Child.utility.root.ainb"), 14,
            "QueryMathSubS32"),
    "lei": (_src(GLOBAL, "AI/EnemyCommon.PredationEatDamage.module.ainb"), 5, "SelectorMathLessOrEqualS32"),
    "lef": (_src(GLOBAL, "AI/ExecuteStingerWaterLevelChange.module.ainb"), 7, "SelectorMathLessOrEqualF32"),
    "seti": (_src("Pack/Actor/Obj_SpiritTemple_CapstanMirror_A_01.pack.zs",
                  "AI/Obj_SpiritTemple_CapstanMirror_A_01.root.ainb"), 20, "OneShotSetGameDataInt"),
    "die": (_src(GLOBAL, "AI/Player.event.root.ainb"), 708, "OneShotEventTriggerPlayerRequestNoAnmDie"),
}


def _node_name(n):
    import ainb
    return n["name"] or ainb.NODE_TYPES.get(n["type"])


def _check_sources(fs):
    """Reads the vanilla nodes the edits copy and hook from the game, and refuses if a game update moved them."""
    from romtools import sarc_files
    import ainb
    cache = {}

    def load(spec):
        if spec["pack"] not in cache:
            cache[spec["pack"]] = sarc_files(fs.read(spec["pack"]))
        return ainb.Ainb(cache[spec["pack"]][spec["file"]])
    for label, (spec, i, want) in SRC.items():
        a = load(spec)
        if i >= len(a.nodes) or _node_name(a.nodes[i]) != want:
            raise RuntimeError(f"{spec['file']}: node {i} is no longer {want} (game update?)")
        n = a.nodes[i]
        if any(e.get("flags", 0) & ainb.BB_INDEXED for t in ainb.PTYPES for e in n["properties"][t] + n["inputs"][t]):
            raise RuntimeError(f"{spec['file']}: node {i} ({want}) now reads the blackboard")
    base = _src("Pack/Actor/Player_Base.pack.zs", ROLL)
    a = load(base)
    kids = {pl["name"]: pl["node"] for pl in a.nodes[ROLL_SELECTOR]["plugs"][ainb.PLUG_CHILD]}
    if a.nodes[ROLL_SELECTOR]["name"] != "SelectorPlayerRolling" or kids.get("WallHit") != ROLL_WALLHIT or \
            a.nodes[ROLL_WALLHIT]["name"] != "ExecutePlayerWallHit":
        raise RuntimeError(f"{ROLL}: SelectorPlayerRolling's WallHit case is no longer ExecutePlayerWallHit")
    for f in BUNNY_FILES:
        a = load(_src("Pack/Actor/Player_Base.pack.zs", f))
        root = next(c["main"] for c in a.commands if c["name"] == "Root")
        if not a.is_plain_simultaneous(root):
            raise RuntimeError(f"{f}: the Root command no longer starts at a plain Simultaneous")


def _copy(label, tag):
    spec, i, _ = SRC[label]
    return {"copy": {"from": spec, "nodes": [i], "label": tag, "follow": False}}


def _ref(label, tag):
    return f"{tag}:{SRC[label][1]}"


def bunny_edits():
    """ainb edits for the walk / Z-target move modules (fast_bunny_hood)."""
    h, e, s, r, d = (_ref("head", "bh"), _ref("eq", "be"), _ref("bsel", "bs"), _ref("rate", "br"),
                     _ref("done", "bd"))
    return [
        _copy("head", "bh"), _copy("eq", "be"), _copy("bsel", "bs"), _copy("rate", "br"), _copy("done", "bd"),
        {"set_property": {"node": h, "name": "OutputOnlyOnEnter", "value": True}},
        {"set_property": {"node": e, "name": "OutputOnlyOnEnter", "value": True}},
        {"set_input": {"node": e, "name": "S32Base", "value": BUNNY}},
        {"feed": {"from": h, "output": "HeadArmor", "to": e, "input": "S32"}},
        {"feed": {"from": e, "output": "Bool", "to": s, "input": "Input"}},
        {"set_input": {"node": r, "name": "ASSlot", "value": 0}},
        {"set_input": {"node": r, "name": "ASRate", "value": BUNNY_RATE}},
        {"set_property": {"node": r, "name": "IsUndoOnLeave", "value": True}},
        {"add_child": {"parent": s, "child": r, "name": "True"}},
        {"add_child": {"parent": s, "child": d, "name": "False"}},
        {"add_child": {"parent": "@Root", "child": s}},
    ]


def bonk_edits(mode):
    """ainb edits for the roll module (deadly_bonks `mode`)."""
    sim, st, nf, nl, ok, die = (_ref("sim", "ks"), _ref("struct", "kt"), _ref("getf", "kf"), _ref("lef", "kn"),
                                _ref("done", "kd"), _ref("die", "kx"))
    out = [
        _copy("sim", "ks"), _copy("struct", "kt"), _copy("getf", "kf"), _copy("lef", "kn"), _copy("done", "kd"),
        _copy("die", "kx"),
        {"set_property": {"node": st, "name": "OutputOnlyOnEnter", "value": True}},
        {"set_input": {"node": st, "name": "GameDataFullName", "value": STRUCT}},
        {"set_property": {"node": nf, "name": "OutputOnlyOnEnter", "value": True}},
        {"set_input": {"node": nf, "name": "GameDataName", "value": NAYRU}},
        {"link": {"from": st, "output": "Value", "to": nf, "input": "ParentStruct"}},
        {"set_input": {"node": nl, "name": "F32Base", "value": 0.0}},
        {"set_property": {"node": nl, "name": "SelectChildOnEnterOnly", "value": True}},
        {"feed": {"from": nf, "output": "Value", "to": nl, "input": "F32"}},
    ]
    # children in the vanilla order of these selectors: if_true, then if_false
    if mode == "ohko":
        out.append({"add_child": {"parent": nl, "child": die, "name": "if_true"}})
    else:
        lq, sub, sel, setl = _ref("geti", "kl"), _ref("sub", "km"), _ref("lei", "kz"), _ref("seti", "kw")
        out += [
            _copy("geti", "kl"), _copy("sub", "km"), _copy("lei", "kz"), _copy("seti", "kw"),
            {"set_property": {"node": lq, "name": "OutputOnlyOnEnter", "value": True}},
            {"set_input": {"node": lq, "name": "GameDataName", "value": LIFE}},
            {"link": {"from": st, "output": "Value", "to": lq, "input": "ParentStruct"}},
            {"set_property": {"node": sub, "name": "OutputOnlyOnEnter", "value": True}},
            {"set_input": {"node": sub, "name": "InputB", "value": BONK_QUARTERS[mode]}},
            {"feed": {"from": lq, "output": "Value", "to": sub, "input": "InputA"}},
            {"set_input": {"node": sel, "name": "S32Base", "value": 0}},
            {"set_property": {"node": sel, "name": "SelectChildOnEnterOnly", "value": True}},
            {"feed": {"from": sub, "output": "Result", "to": sel, "input": "S32"}},
            {"set_input": {"node": setl, "name": "GameDataName", "value": LIFE}},
            {"feed": {"from": sub, "output": "Result", "to": setl, "input": "Value"}},
            {"link": {"from": st, "output": "Value", "to": setl, "input": "ParentStruct"}},
            {"add_child": {"parent": sel, "child": die, "name": "if_true"}},
            {"add_child": {"parent": sel, "child": setl, "name": "if_false"}},
            {"add_child": {"parent": nl, "child": sel, "name": "if_true"}},
        ]
    out += [
        {"add_child": {"parent": nl, "child": ok, "name": "if_false"}},
        {"add_child": {"parent": sim, "child": ROLL_WALLHIT}},
        {"add_child": {"parent": sim, "child": nl}},
        {"set_child": {"parent": ROLL_SELECTOR, "which": "WallHit", "child": sim}},
    ]
    return out


def resolve_settings(settings):
    """Runs before OoTR's Main.resolve_settings (generate.prepare, through parity/story.py). OoTR seeds its RNG from the
    settings string, and that holds auto_equip_masks (a "shared" setting). The setting changes no world, it's only
    whether a mask stays on, so the salt is computed as if it were False. That way a seed is the same world with either
    value, and the default seeds, made with False before True became the remake's default, keep their fill."""
    import Settings as S
    if getattr(S.Settings.get_numeric_seed, "remake_masks", False):
        return
    original = S.Settings.get_numeric_seed

    def get_numeric_seed(self, _original=original):
        if not getattr(self, "auto_equip_masks", False):
            return _original(self)
        saved = self.settings_string
        self.auto_equip_masks = False
        try:
            self.settings_string = self.get_settings_string()
            return _original(self)
        finally:
            self.auto_equip_masks = True
            self.settings_string = saved
    get_numeric_seed.remake_masks = True
    S.Settings.get_numeric_seed = get_numeric_seed


def world_plan(settings, world):
    """This module's plan sections for the seed's settings ({} when none applies)."""
    ws = getattr(world, "settings", settings)
    bunny = bool(getattr(ws, "fast_bunny_hood", False))
    bonks = getattr(ws, "deadly_bonks", "none")
    masks_off = not getattr(ws, "auto_equip_masks", True)
    out = {}
    if masks_off:  # OoTR's OFF (experimental): masks come off on every area change and reload
        out = off_plan()
        out["_gaps"] = {"player_masks_off": {"row": MASK_ROW, "reset": MASK_RESET, "file": AFTER_LOAD}}
    if not bunny and bonks == "none":
        return out
    from romtools import Romfs
    _check_sources(Romfs(DEFAULT_ROMFS, os.path.join(HERE, "original")))
    ops, gaps = [], {}
    if bunny:
        ops += [{"pack": "*", "file": f, "edits": bunny_edits()} for f in BUNNY_FILES]
        gaps["player_bunny"] = {"files": list(BUNNY_FILES), "head_armor": BUNNY, "rate": BUNNY_RATE}
    if bonks != "none":
        if bonks not in BONK_MODES:
            raise RuntimeError(f"deadly_bonks {bonks!r}")
        ops.append({"pack": "*", "file": ROLL, "edits": bonk_edits(bonks)})
        gaps["player_bonks"] = {"file": ROLL, "mode": bonks, "quarters": BONK_QUARTERS.get(bonks)}
    out["ainb"] = out.get("ainb", []) + ops
    out["_gaps"] = dict(out.get("_gaps") or {}, **gaps)
    return out


def UNTESTED(settings):
    out = []
    if getattr(settings, "fast_bunny_hood", False):
        out.append("fast_bunny_hood = True (experimental: the walk actions play Link's animation 1.5x while the "
                   "Bunny Hood is worn; check he covers ground faster)")
    bonks = getattr(settings, "deadly_bonks", "none")
    if bonks == "ohko":
        out.append("deadly_bonks = 'ohko' (experimental: a roll bonk requests a death without animation; check it "
                   "kills, a fairy revives, Nayru's Love protects)")
    elif bonks != "none":
        out.append(f"deadly_bonks = {bonks!r} (experimental: a roll bonk writes PlayerStatus.Life - "
                   f"{BONK_QUARTERS[bonks]}; check the real life drops, not just the hearts shown)")
    if getattr(settings, "auto_equip_masks", False):
        out.append("auto_equip_masks = True (the remake's own mask persistence, no edit: check a mask stays on "
                   "through a loading zone and a reload)")
    else:
        out.append("auto_equip_masks = False (experimental: IsActiveHeadArmor reset on area change, cleared after a "
                   "load; check a worn mask comes off at the first loading zone and after a reload)")
    return out


# Auto_equip_masks OFF (explicit False)
MASK_ROW, MASK_RESET, AFTER_LOAD = "PlayerStatus.IsActiveHeadArmor", 9, "Sequence/AfterLoadSaveData.module.ainb"


def off_plan():
    """OoTR auto_equip_masks OFF, wired when the setting is False (the remake's default is True). Masks come off on
    every scene change and a reload doesn't keep them. Two edits:
      1. PlayerStatus.IsActiveHeadArmor ResetTypeValue 8 -> 9. With bit 0, ChangeBanc's SeqExecuteResetGameData
         ResetType 0 clears it on every area change, and 288 saved Bools already use 9.
      2. Reloads. OnLoadGameSaveData resets before it reads the save and the next ChangeBanc skips its reset, so the
         after-load sequence sets it False. That's a SeqOneShotSetGameDataBool (PlayerStatus / IsActiveHeadArmor) added
         to the first step of Sequence/AfterLoadSaveData.module.ainb (Simultaneous node 1), copied with its struct
         query from Sequence/BeforeMinusMenu.module.ainb (nodes 1, 2).
    In-game check: a worn mask comes off at the first loading zone and is off after a reload, the pause menu shows it
    unequipped, and time travel is unchanged."""
    src = {"file": "Sequence/BeforeMinusMenu.module.ainb"}
    return {
        "gamedata": [{"reset_type": {"PlayerStatus.IsActiveHeadArmor": 9}}],
        "ainb": [{"file": "Sequence/AfterLoadSaveData.module.ainb", "edits": [
            {"copy": {"from": src, "nodes": [1], "label": "mq", "follow": False}},
            {"copy": {"from": src, "nodes": [2], "label": "ms", "follow": False}},
            {"set_input": {"node": "mq:1", "name": "GameDataFullName", "value": STRUCT}},
            {"set_input": {"node": "ms:2", "name": "GameDataName", "value": "IsActiveHeadArmor"}},
            {"set_input": {"node": "ms:2", "name": "Value", "value": False}},
            {"link": {"from": "mq:1", "output": "Value", "to": "ms:2", "input": "ParentStruct"}},
            {"add_child": {"parent": 1, "child": "ms:2"}},
        ]}],
    }


# Read-back (parity/_gaps_check.py)
def _carriers(file, romfs):
    import packpaths
    return packpaths.carriers(file, romfs)


def _inputs(a, i):
    import ainb
    return {e["name"]: e for t in ainb.PTYPES for e in a.nodes[i]["inputs"][t]}


def _props(a, i):
    import ainb
    return {e["name"]: e.get("value") for t in ainb.PTYPES for e in a.nodes[i]["properties"][t]}


def _src_of(a, i, name):
    e = _inputs(a, i).get(name)
    return -1 if e is None else e["node"]


def _kids(a, i):
    import ainb
    return [(pl["name"], pl["node"]) for pl in a.nodes[i]["plugs"][ainb.PLUG_CHILD]]


def _is(a, i, name):
    return 0 <= i < len(a.nodes) and _node_name(a.nodes[i]) == name


def _struct_ok(a, i):
    return _is(a, i, "QueryGetNonStructGameDataStruct") and \
        _inputs(a, i)["GameDataFullName"]["value"] == STRUCT


def _check_bunny(a, note):
    root = next(c["main"] for c in a.commands if c["name"] == "Root")
    sels = [c for _, c in _kids(a, root) if _is(a, c, "BoolSelector")]
    if len(sels) != 1:
        return [f"the Root Simultaneous has {len(sels)} BoolSelector children, not 1"]
    s = sels[0]
    bad = []
    eq = _src_of(a, s, "Input")
    if not _is(a, eq, "QueryMathEqualS32") or _inputs(a, eq)["S32Base"]["value"] != note["head_armor"]:
        bad.append("the selector's input is not 'head armor == Bunny'")
    elif not _is(a, _src_of(a, eq, "S32"), "QueryPlayerGetSelectedHeadArmor"):
        bad.append("the comparison isn't fed by QueryPlayerGetSelectedHeadArmor")
    kids = dict(_kids(a, s))
    r = kids.get("True", -1)
    if not _is(a, r, "ExecuteSetASRate"):
        bad.append("the True case is not ExecuteSetASRate")
    else:
        ins = _inputs(a, r)
        if abs(ins["ASRate"]["value"] - note["rate"]) > 1e-6 or ins["ASSlot"]["value"] != 0 or \
                not _props(a, r).get("IsUndoOnLeave"):
            bad.append(f"ExecuteSetASRate is {ins['ASRate']['value']} on slot {ins['ASSlot']['value']}, "
                       f"undo {_props(a, r).get('IsUndoOnLeave')}")
    if not _is(a, kids.get("False", -1), "ExecuteGenericSetResultSuccess"):
        bad.append("the False case is not ExecuteGenericSetResultSuccess")
    return bad


def verify_bunny(patch, note, romfs):
    from romtools import Romfs, sarc_files
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    for f in note["files"]:
        packs = _carriers(f, romfs)
        if not packs:
            bad.append(f"{f}: no pack holds it")
        for pack in packs:
            bad += [f"{pack} {f}: {x}" for x in _check_bunny(ainb.Ainb(sarc_files(fs.read(pack))[f]), note)]
    return bad


def _check_bonks(a, note):
    bad = []
    kids = dict(_kids(a, ROLL_SELECTOR))
    sim = kids.get("WallHit", -1)
    if not _is(a, sim, "Simultaneous") or [c for _, c in _kids(a, sim)][:1] != [ROLL_WALLHIT] or \
            len(_kids(a, sim)) != 2:
        return [f"WallHit doesn't start a Simultaneous of ExecutePlayerWallHit and the damage branch ({sim})"]
    if not _is(a, ROLL_WALLHIT, "ExecutePlayerWallHit"):
        bad.append(f"node {ROLL_WALLHIT} is no longer ExecutePlayerWallHit")
    nl = _kids(a, sim)[1][1]
    if not _is(a, nl, "SelectorMathLessOrEqualF32") or _inputs(a, nl)["F32Base"]["value"] != 0.0:
        return bad + ["the damage branch doesn't start with 'NayruLoveTime <= 0'"]
    nf = _src_of(a, nl, "F32")
    if not _is(a, nf, "QueryGetGameDataFloat") or _inputs(a, nf)["GameDataName"]["value"] != NAYRU or \
            not _struct_ok(a, _src_of(a, nf, "ParentStruct")):
        bad.append("the Nayru's Love check doesn't read PlayerStatus.NayruLoveTime")
    nk = dict(_kids(a, nl))
    if not _is(a, nk.get("if_false", -1), "ExecuteGenericSetResultSuccess"):
        bad.append("with Nayru's Love running the branch doesn't do nothing")
    hit = nk.get("if_true", -1)
    if note["mode"] == "ohko":
        if not _is(a, hit, "OneShotEventTriggerPlayerRequestNoAnmDie"):
            bad.append("ohko: the bonk doesn't request the death")
        return bad
    if not _is(a, hit, "SelectorMathLessOrEqualS32") or _inputs(a, hit)["S32Base"]["value"] != 0:
        return bad + ["the bonk doesn't compare 'Life - N <= 0'"]
    sub = _src_of(a, hit, "S32")
    if not _is(a, sub, "QueryMathSubS32") or _inputs(a, sub)["InputB"]["value"] != note["quarters"]:
        bad.append(f"the bonk doesn't subtract {note['quarters']} quarter hearts")
    else:
        lq = _src_of(a, sub, "InputA")
        if not _is(a, lq, "QueryGetGameDataInt") or _inputs(a, lq)["GameDataName"]["value"] != LIFE or \
                not _struct_ok(a, _src_of(a, lq, "ParentStruct")):
            bad.append("the subtraction doesn't start from PlayerStatus.Life")
    hk = dict(_kids(a, hit))
    if not _is(a, hk.get("if_true", -1), "OneShotEventTriggerPlayerRequestNoAnmDie"):
        bad.append("a bonk at N quarters or fewer doesn't request the death")
    w = hk.get("if_false", -1)
    if not _is(a, w, "OneShotSetGameDataInt") or _inputs(a, w)["GameDataName"]["value"] != LIFE or \
            _src_of(a, w, "Value") != sub or not _struct_ok(a, _src_of(a, w, "ParentStruct")):
        bad.append("the bonk doesn't write PlayerStatus.Life = Life - N")
    return bad


def verify_bonks(patch, note, romfs):
    from romtools import Romfs, sarc_files
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    packs = _carriers(note["file"], romfs)
    if not packs:
        bad.append(f"{note['file']}: no pack holds it")
    for pack in packs:
        a = ainb.Ainb(sarc_files(fs.read(pack))[note["file"]])
        bad += [f"{pack} {note['file']}: {x}" for x in _check_bonks(a, note)]
    return bad


READERS = {"player_bunny": "verify_bunny", "player_bonks": "verify_bonks", "player_masks_off": "verify_masks_off"}
PARITY_NOTE = {
    "auto_equip_masks": "the remake's default is True, its own behaviour (config/rando_settings.json, the app); "
                        "False plays as OoTR's Off (experimental)",
    "fast_bunny_hood": "experimental: the run animation at 1.5x",
    "deadly_bonks": "experimental: a life write on the roll's wall hit",
}


def verify_masks_off(patch, note, romfs):
    """Read-back for auto_equip_masks False. The worn-mask row resets on area change (ResetTypeValue 9), and the first
    step of the after-load sequence sets it False (a SeqOneShotSetGameDataBool under node 1 whose ParentStruct is the
    PlayerStatus struct query)."""
    from romtools import Romfs, byml_load, murmur3_32
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    row = next((e for e in gd["Data"]["Bool"] if e["Hash"] == murmur3_32(note["row"])), None)
    if row is None or int(row["ResetTypeValue"]) != note["reset"]:
        bad.append(f"GameDataList: {note['row']} ResetTypeValue is {row and row['ResetTypeValue']}, not {note['reset']}")
    a = ainb.Ainb(open(fs.path(note["file"]), "rb").read())
    hits = []
    for _, c in _kids(a, 1):
        if 0 <= c < len(a.nodes) and _node_name(a.nodes[c]) == "SeqOneShotSetGameDataBool":
            ins = _inputs(a, c)
            q = ins.get("ParentStruct", {}).get("node", -1)  # (sequence files use the Seq-prefixed struct query)
            if ins.get("GameDataName", {}).get("value") == "IsActiveHeadArmor" and \
                    ins.get("Value", {}).get("value") is False and 0 <= q < len(a.nodes) and \
                    _node_name(a.nodes[q]) in ("SeqQueryGetNonStructGameDataStruct", "QueryGetNonStructGameDataStruct") \
                    and _inputs(a, q)["GameDataFullName"]["value"] == STRUCT:
                hits.append(c)
    if len(hits) != 1:
        bad.append(f"{note['file']}: {len(hits)} steps clear IsActiveHeadArmor under node 1 (want 1)")
    return bad
