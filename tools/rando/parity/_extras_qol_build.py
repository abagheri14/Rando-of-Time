"""Build data/rando/extras_qol_data.json: the game facts the extras_qol plugin (extras_qol.py) relies on, read from the
game files (vanilla view: ./original copies win), so the plugin can write patch plans without the romfs.

usage: python tools/rando/parity/_extras_qol_build.py ROMFS [VANILLA_DIR]

What it records and checks (the build stops when a file differs from what the plugin was written against):
- talon: the castle story steps that set Goto_HyruleCastle to a step before Step04 (each one's flowchart, next step
  and every step or entry leading to it), and the save-data rows the skip sets
- frogs: the frog song game's note timer step (MiniGame_FrogTenors EventTriggerPrepareScoreForFrog)
- replays: Dm_SY_Ocarina's three calls of the "song played" replay (:PlayAuto), and the per-song waits that follow
  each call before the song takes effect (RequestCreateConditionSensor) or its own scene starts
- packs: the wallet capacity rows (IsItemStockMax), the beehive's slingshot damage rate and the player's damage
  rates, and the player's own damage (falls, fire, ice, lava, shocks, poison bog, heat, drowning)
- difficulty: every enemy's MaxLife (Life/LifeParameters/Enemy_* and Keese), every grabbing enemy's grab damage
  (GameParameter/RestraintParam PredationDamageValue) and every attacker's hits (GameBalance/AttackParam
  BaseAttackPower and each attack's DamageMultiplier, is_attacker), and every enemy's lock-on target
  (Attention/ClientParam, type LockOn and action None, named like an enemy: LOCK_ON_ENEMIES), each with the packs
  holding the file
- pickup_text: the "already seen" flags of the small pickups' first get window (HavePlayedGetEvent.<name>, a Bool
  that starts false). GetPouchContent:OpenGetWindow_End sets the flag once the window closes, and every later
  pickup adds its item without a window. The flag goes by the item the pickup gives, its PouchContentParam
  PouchActor (Obj_DekuNut gives Item_DekuNut), or by the pickup itself when it names none (rupees, jars, arrows).
  Where the pickup's own name has a row as well (Obj_DekuSeed), we set that one too. An item whose first get also hands out its small bag (IsAbleToGetBagIfGet, SmallBagActor:
  nuts and sticks) gets that bag's rows too: IsGet, its pouch count, the bag's size (its ExpansionMaxNumActor
  MaxNum, in PouchContentMaxNum.<GameData>) and CurrentExpansionActor_<GameData>.
- blocks: the push blocks' move curves (GrabMoveActorParam MoveSpeed, a Hermite curve of frame -> share of one
  push, points of x, y, slope in, slope out) and every pack holding each file
- dpad: the item-wheel hold counter graph (Sequence/UpdateShortCutOpenHoldFrameCounter.module, which runs every
  frame outside menus and events) and the nodes the D-pad gear edit copies from other sequence graphs, the
  Equipment menu's accessories and boots in its order with the ages that may use each (UI/Pouch/PouchTable), the
  adult's tunics for the D-pad left wheel, and the save rows the cycle reads (IsGet, pouch count, the equipped name)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from romtools import Romfs, byml_load, murmur3_32, sarc_files  # noqa: E402
from evfl import Evfl  # noqa: E402
from parity._story_build import newest, step_info, describe, flat  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "extras_qol_data.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"

TALON_GUARDS = {"Event14": "Step02", "Event51": "Step02_01", "Event46": "Step03", "Event88": "Step03_02"}
TALON_FLAGS = {"Step_Goto_HyruleCastle": "Enum", "Talon_AfterWakeUp": "Bool",
               "HavePlayedEvent.Dm_HrlCastle_0020": "Bool", "Goto_HyruleCastle_IsAfter_Step03_02_Exp": "BoolExp",
               "PlayerStatus.CurrentRupee": "Int"}
# the pouch wallets and the get-demo items that carry the same capacity row (the starting wallet has no Item_ pack)
WALLET_PACKS = [(f"{kind}_Wallet_{size}", f"GameParameter/ExpansionMaxNumActor/Item_Wallet_{size}"
                 f".game__actor__ExpansionMaxNumActor.bgyml")
                for size in ("Small", "Medium", "Large") for kind in ("Item", "Pouch")
                if (kind, size) != ("Item", "Small")]
BEEHIVE = ("Obj_Kokiri_Beehive_A_01", "Life/DamageParameters/Obj_Beehive.game__life__DamageParameters.bgyml")
PLAYER_PACKS = ("Player_Base", "Player_Child", "Player_Adult")
PLAYER_DAMAGE = "Life/DamageParameters/Player.game__life__DamageParameters.bgyml"
# the player's own damage, the hurt that comes from no enemy's attack (in quarter hearts; the per-meter falls in quarter
# hearts a meter): the fields the damage multipliers scale with the attack rates
INTERNAL_DAMAGE = {"BurnContinuousDamage", "IgnitionDamage", "Damage", "ContinuousDamage", "FallDamageMin",
                   "FallDamagePerMeter", "FallDamageHighPerMeter"}
INTERNAL_DAMAGE_PATHS = {f"InternalDamageParameters.{p}" for p in (
    "BurnDamageParameters.BurnContinuousDamage", "BurnDamageParameters.IgnitionDamage",
    "ElectricShockDamageParameters.Damage", "FallDamageParameters.FallDamageHighPerMeter",
    "FallDamageParameters.FallDamageMin", "FallDamageParameters.FallDamagePerMeter",
    "FrozenDamageParameters.ContinuousDamage", "FrozenDamageParameters.Damage",
    "LavaDamageParameters.ContinuousDamage", "LavaDamageParameters.Damage",
    "PoisonBogDamageParameters.ContinuousDamage", "PoisonBogDamageParameters.Damage",
    "UnderwaterDamageParameters.ContinuousDamage", "UnderwaterDamageParameters.Damage",
    "ScorchingEnvDamageParameters.Damage")}
LIFE_DIR = "Life/LifeParameters/"
ATTACK_DIR = "GameBalance/AttackParam/"
# the attackers whose hits hurt Link: enemies, bosses, their shots, and the few named otherwise. Link's reflected beams
# (MirrorShield) are his own.
ATTACKERS_MORE = ("Keese", "BeamosBeam", "ScrubDeku_DekuNut")
ATTENTION_DIR = "Attention/ClientParam/"
LOCK_ON_ENEMIES = ("EnemyCommon_", "Enemy_", "DungeonBoss", "Ganon_")  # the lock-on targets that are enemies
RESTRAINT_DIR = "GameParameter/RestraintParam/"
PICKUP_TEXT = ("Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Rupee_Purple", "Obj_Rupee_Gold", "Obj_Heart",
               "Obj_MagicJar_Small", "Obj_MagicJar_Large", "Obj_ArrowBundle_Small", "Obj_ArrowBundle_Medium",
               "Obj_ArrowBundle_Large", "Obj_DekuSeed", "Obj_DekuNut", "Obj_DekuStick", "Obj_Bomb", "Obj_Bombchu")
BLOCKS = ("Obj_MovableBox_A_01", "Obj_MovableBox_A_04", "Obj_MovableBox_A_05")
# D-pad gear. The graph that times the item-wheel hold every frame outside menus and events, and its nodes the edit
# reads or copies: {key: (index, node name)}
DPAD_FILE = "Sequence/UpdateShortCutOpenHoldFrameCounter.module.ainb"
DPAD_COUNTER = "Sequence_ShortCutOpenHoldCounter"
DPAD_NODES = {"hold": (1, "SeqQueryControllerHoldMaskChecker"), "trig": (13, "SeqQueryControllerTrigMaskChecker"),
              "hook": (32, ""), "reset": (24, "SeqOneShotSetNonStructGameDataFloat"),
              "counter": (19, "SeqQueryGetNonStructGameDataFloat"), "step": (25, "SeqExecuteAddNonStructGameDataFloat"),
              "dummy": (23, "SeqExecuteGenericDummyAction"), "bool_sel": (3, ""), "f32_sel": (20, ""),
              "sim": (10, ""), "set_bool": (16, "SeqOneShotSetNonStructGameDataBool"),
              "get_bool": (30, "SeqQueryGetNonStructGameDataBool"), "hash": (5, "SeqQueryCalcStringHashMurMur3"),
              "set_enum": (9, "SeqOneShotSetNonStructGameDataEnum"), "closing": (33, "")}
# the wheel's own graph (wheel mode): {key: (index, node name)}
WHEEL_FILE = "Sequence/ShortCut.module.ainb"
WHEEL_NODES = {"hold": (3, "SeqQueryControllerHoldMaskChecker"), "end": (5, "SeqOneShotEnd"), "held": (6, ""),
               "force": (16, ""), "set_category": (17, "SeqOneShotSetNonStructGameDataEnum"),
               "close_flag": (32, "SeqOneShotSetNonStructGameDataBool"),
               "get_bool": (51, "SeqQueryGetNonStructGameDataBool"), "hold_r": (59, ""),
               "dummy": (7, "SeqExecuteGenericDummyAction")}
DPAD_OUTPUTS = ("HoldUp", "HoldDown", "TrigUp", "TrigDown", "HoldR", "HoldLeft", "TrigLeft")
# nodes copied from other sequence graphs: {key: (file, index, node name)}
DPAD_SOURCES = {"get_s64": ("Sequence/AfterChangeBanc.module.ainb", 17, "SeqQueryGetNonStructGameDataString64"),
                "str_sel": ("Sequence/AfterChangeBanc.module.ainb", 16, ""),
                "set_s64": ("Sequence/AfterEvent.module.ainb", 12, "SeqOneShotSetNonStructGameDataString64"),
                "get_exp": ("Sequence/Ocarina.module.ainb", 71, "SeqQueryGetNonStructGameDataBoolExp"),
                "sync": ("Sequence/LoadBancImpl.module.ainb", 69, "SeqSyncPlayerEquipmentAndGameData"),
                "index": ("Sequence/AfterLoadSaveData.module.ainb", 0, "SeqOneShotPouchTargetSyncEquipmentIndex"),
                "push": ("Sequence/SetPouchAndStatusForGameStart.module.ainb", 7, "SeqOneShotPushToPouch")}
POUCH_TABLE = "UI/Pouch/PouchTable/PouchTable.game__ui__PouchTable.bgyml"
POUCH_INFO = "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"
# the Equipment menu's accessory and boots buttons, in the menu's order (Pa_HeadEquip_00 is the Stone of Agony)
GEAR_BUTTONS = {"head": ("Pa_HeadEquip_01", "Pa_HeadEquip_02", "Pa_HeadEquip_03"),
                "boots": ("Pa_FootEquip_00", "Pa_FootEquip_01")}
GEAR_SLOT = {"head": "PlayerStatus.EquipHeadArmor", "boots": "PlayerStatus.EquipBoot"}
# the Equipment menu's tunic buttons (Zora, Goron, Kokiri), for the D-pad left wheel: the adult's actors only (a
# child only ever wears the Kokiri tunic, Obj_Armor_Child_Normal)
TUNIC_BUTTONS = ("Pa_Epuipment_06", "Pa_Epuipment_07", "Pa_Epuipment_08")
TUNIC_SLOT = "PlayerStatus.EquipArmor"


def fail(msg):
    raise SystemExit(f"_extras_qol_build: {msg} (the plugin was written against another version of the game)")


def flow(fs, romfs, base):
    rel, versions = newest(romfs, base)
    if len(versions) != 1:
        fail(f"{base}: {versions}: the plugin edits one version only")
    return Evfl(fs.read(rel)).flowcharts[0]


def nexts(fc, e):
    ev = fc["events"]
    if e["type"] in ("action", "subflow", "join", "type6"):
        return [ev[e["next"]]["name"]] if e.get("next") is not None and e["next"] < len(ev) else []
    if "cases" in e:
        return [ev[c["next"]]["name"] for c in e["cases"]]
    if e["type"] == "fork":
        return [ev[x]["name"] for x in e["forks"]] + [ev[e["join"]]["name"]]
    return []


def talon(fs, romfs):
    fc = flow(fs, romfs, "Goto_HyruleCastle")
    by = {e["name"]: e for e in fc["events"]}
    out = {"flowchart": fc["name"], "steps": {}}
    for name, step in TALON_GUARDS.items():
        e = by.get(name)
        info = step_info(fc, e) if e else None
        if info is None or info["kind"] != "action ChallengeSystemActor.EventExecuteProgressChallengeStep" or \
                info["params"].get("ChallengeName") != "Goto_HyruleCastle" or info["params"].get("StepName") != step:
            fail(f"Goto_HyruleCastle {name}: not the Step {step} progress step")
        if not info["preds"]:
            fail(f"Goto_HyruleCastle {name}: nothing leads to it")
        out["steps"][name] = {"next": info["next"], "preds": info["preds"], "step": step}
    return out


def frogs(fs, romfs):
    """Every frog score step (the final song's note list, one per difficulty level and the tutorial's) with the seconds
    the player has for each note (PlayableSeconds) and for the first one (FirstPlayableSeconds)."""
    fc = flow(fs, romfs, "MiniGame_FrogTenors")
    hits = [e for e in fc["events"] if describe(fc, e) == "action GameSystemActor.EventTriggerPrepareScoreForFrog"]
    if len(hits) != 5:
        fail(f"MiniGame_FrogTenors: {len(hits)} frog score steps (5 expected)")
    steps = {}
    for e in hits:
        p = flat(e.get("params"), {})
        if not isinstance(p.get("PlayableSeconds"), float) or not isinstance(p.get("FirstPlayableSeconds"), float):
            fail(f"MiniGame_FrogTenors {e['name']}: no PlayableSeconds / FirstPlayableSeconds")
        steps[e["name"]] = {"PlayableSeconds": p["PlayableSeconds"], "FirstPlayableSeconds": p["FirstPlayableSeconds"],
                            "Num": p.get("Num"), "IsRandom": p.get("IsRandom")}
    return {"flowchart": fc["name"], "steps": steps}


WAITS = ("action EventSystemActor.EventWait", "action GameSystemActor.EventWaitFrameOrSkip")


def replays(fc):
    """The :PlayAuto calls and the per-song waits right after each (the first step every melody case of the dispatch
    queries reaches)."""
    by = {e["name"]: e for e in fc["events"]}
    calls = [e for e in fc["events"] if e["type"] == "subflow" and e.get("entry_point") == "PlayAuto"
             and not e.get("flowchart")]
    if len(calls) != 3:
        fail(f"Dm_SY_Ocarina: {len(calls)} calls of :PlayAuto (3 expected)")
    out = {"flowchart": fc["name"], "calls": {}, "waits": {}}
    for c in calls:
        start = nexts(fc, c)
        if len(start) != 1:
            fail(f"Dm_SY_Ocarina {c['name']}: the replay call has no single next step")
        waits, seen, stack = set(), set(), list(start)
        while stack:  # follow the melody queries to each song's first action
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            e = by[n]
            if e["type"] == "switch":
                stack.extend(nexts(fc, e))
                continue
            if describe(fc, e) in WAITS:
                frames = flat(e.get("params"), {}).get("Frames")
                after = nexts(fc, e)
                # The song takes effect after the replay wait, sometimes after a fork or camera step.
                if isinstance(frames, int) and frames >= 90 and after:
                    waits.add(n)
                    out["waits"][n] = frames
        if not waits:
            fail(f"Dm_SY_Ocarina {c['name']}: no replay wait after the call")
        out["calls"][c["name"]] = {"next": start[0], "waits": sorted(waits, key=lambda x: int(x[5:]))}
    # every wait must lead on to the replay's end (the song's effect sensor, the light reset, the melody fade, or the
    # song's own scene such as Saria's call)
    for w in out["waits"]:
        seen, stack, found = set(), [w], False
        while stack and not found:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            d = describe(fc, by[n])
            if any(k in d for k in ("RequestCreateConditionSensor", "LightOff", "LightPaletteOff_NoCapture",
                                    "FadeOcarinaMelodyHandle", "call Dm_SY_Ocarina_")):
                found = True
            stack.extend(nexts(fc, by[n]))
        if not found:
            fail(f"Dm_SY_Ocarina {w}: the wait does not lead to the replay's end")
    return out


def packs(fs):
    out = {"wallets": [], "beehive": None, "player": []}
    for pack, rel in WALLET_PACKS:
        files = sarc_files(fs.read(f"Pack/Actor/{pack}.pack.zs"))
        if rel not in files:
            fail(f"{pack}: no {rel}")
        d = byml_load(files[rel])[0]
        if d.get("GameData") != "Rupee" or d.get("IsItemStockMax") is not False:
            fail(f"{pack}: {rel} is not a rupee capacity row with IsItemStockMax false")
        out["wallets"].append({"pack": f"Pack/Actor/{pack}.pack.zs", "file": rel, "MaxNum": d.get("MaxNum")})
    pack, rel = BEEHIVE
    files = sarc_files(fs.read(f"Pack/Actor/{pack}.pack.zs"))
    rates = byml_load(files[rel])[0]["ExternalDamageParameters"]["DamageRates"]
    sling = murmur3_32("SlingshotBullet")
    if rates.get(sling) != 0.0 or rates.get(murmur3_32("Arrow")) != 1.0:
        fail(f"{pack}: the beehive's slingshot/arrow damage rates are not 0 / 1")
    out["beehive"] = {"pack": f"Pack/Actor/{pack}.pack.zs", "file": rel, "key": str(sling)}
    for p in PLAYER_PACKS:
        files = sarc_files(fs.read(f"Pack/Actor/{p}.pack.zs"))
        dmg = byml_load(files[PLAYER_DAMAGE])[0]
        rates = dmg["ExternalDamageParameters"]["DamageRates"]
        internal = {f"InternalDamageParameters.{part}.{k}": v
                    for part, fields in sorted(dmg["InternalDamageParameters"].items()) for k, v in sorted(fields.items())
                    if k in INTERNAL_DAMAGE}
        if len(internal) != len(INTERNAL_DAMAGE_PATHS) or set(internal) != INTERNAL_DAMAGE_PATHS:
            fail(f"{p}: the player's own damage (falls, fire, ice, lava...) isn't the fields we scale")
        out["player"].append({"pack": f"Pack/Actor/{p}.pack.zs", "file": PLAYER_DAMAGE,
                              "rates": {str(k): v for k, v in sorted(rates.items())}, "internal": internal})
    return out


def difficulty(fs, romfs):
    """Enemy health (every enemy's MaxLife) and grab damage (every grabbing enemy's PredationDamageValue), with the packs
    holding each file. Grab damage a file doesn't name is the game's own 2 quarter hearts a tick."""
    import packpaths
    idx = packpaths.index(romfs)
    life, grabs, attacks, lock_on = [], [], [], []
    lock, none = murmur3_32("LockOn"), murmur3_32("None")
    for rel in sorted(idx):
        base = os.path.basename(rel).split(".")[0]
        holders = sorted(idx[rel])
        if rel.startswith(ATTENTION_DIR) and base.startswith(LOCK_ON_ENEMIES):
            d = byml_load(sarc_files(fs.read(holders[0]))[rel])[0]
            if d.get("AttentionType") == lock and d.get("ActionType") == none:
                lock_on.append({"file": rel, "packs": holders})
            continue
        if rel.startswith(ATTACK_DIR) and is_attacker(base):
            d = byml_load(sarc_files(fs.read(holders[0]))[rel])[0]
            if not isinstance(d.get("BaseAttackPower"), int):
                fail(f"{rel}: no whole-number BaseAttackPower")
            mults = [a.get("DamageMultiplier") for a in d.get("AttackParams") or []]
            if any(not isinstance(m, float) for m in mults):
                fail(f"{rel}: an attack without a DamageMultiplier")
            attacks.append({"file": rel, "packs": holders, "BaseAttackPower": d["BaseAttackPower"], "multipliers": mults})
            continue
        if rel.startswith(LIFE_DIR) and (base.startswith("Enemy_") or base == "Keese"):
            d = byml_load(sarc_files(fs.read(holders[0]))[rel])[0]
            if not isinstance(d.get("MaxLife"), int):
                fail(f"{rel}: no whole-number MaxLife")
            life.append({"file": rel, "packs": holders, "MaxLife": d["MaxLife"]})
        elif rel.startswith(RESTRAINT_DIR) and base != "Enemy_Common":
            d = byml_load(sarc_files(fs.read(holders[0]))[rel])[0]
            v = d.get("PredationDamageValue")
            if v is not None and not isinstance(v, int):
                fail(f"{rel}: PredationDamageValue isn't a whole number")
            grabs.append({"file": rel, "packs": holders, "value": v})
    if len(life) < 80 or not grabs or len(attacks) < 80:
        fail(f"only {len(life)} enemy life files, {len(grabs)} grab files and {len(attacks)} attackers found")
    if len(lock_on) < 15:
        fail(f"only {len(lock_on)} enemy lock-on targets found")
    return {"life": life, "grabs": grabs, "attacks": attacks, "lock_on": lock_on}


def is_attacker(name):
    """An attack file of something whose hits hurt Link (OOTRR's enemy damage list)."""
    if "MirrorShield" in name:
        return False
    return name.startswith(("Enemy_", "DungeonBoss")) or "_Bullet" in name or name in ATTACKERS_MORE


def gamedata(fs):
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    index = {e["Hash"]: (t, e) for t, rows in gd["Data"].items() if t != "Bool64bitKey" for e in rows}
    out = {}
    for name, kind in TALON_FLAGS.items():
        hit = index.get(murmur3_32(name))
        if hit is None or hit[0] != kind:
            fail(f"save data: {name} is not a {kind}")
        out[name] = {"type": kind}
        if kind == "Enum":
            if "Step04" not in hit[1]["RawValues"]:
                fail(f"save data: {name} has no Step04")
            out[name]["values"] = hit[1]["RawValues"]
    return out


def _ref(ref):
    """Pack path of a component reference ("?Component/...bgyml" or "Work/...gyml")."""
    if not isinstance(ref, str) or not ref:
        return None
    ref = ref.lstrip("?")
    ref = ref[5:] if ref.startswith("Work/") else ref
    return ref[:-5] + ".bgyml" if ref.endswith(".gyml") else ref


def _short(ref):
    return os.path.basename(ref).split(".")[0] if ref else ""


def actor_param(fs, actor, key):
    """The actor's component `key` (PouchContentRef...) merged over its $parent chain inside its pack. A parent the
    pack doesn't hold is the engine's default and adds nothing."""
    files = sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))

    def merged(p):
        chain = []
        while p and p in files:
            d = byml_load(files[p])[0]
            chain.append(d)
            p = _ref(d.get("$parent"))
        out = {}
        for d in reversed(chain):
            for k, v in d.items():
                if k != "$parent":
                    out[k] = {**out.get(k, {}), **v} if k == "Components" and isinstance(v, dict) else v
        return out

    ap = merged(f"Actor/{actor}.engine__actor__ActorParam.bgyml")
    if not ap:
        fail(f"{actor}: no ActorParam in its pack")
    ref = _ref((ap.get("Components") or {}).get(key))
    return merged(ref) if ref else {}


def pickup_text(fs):
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    rows = {e["Hash"]: (t, e) for t, es in gd["Data"].items() if t != "Bool64bitKey" for e in es}

    def row(name, kind, default):
        t, e = rows.get(murmur3_32(name), (None, {}))
        if t != kind or e.get("DefaultValue") != default or type(e.get("DefaultValue")) is not type(default):
            fail(f"save data: {name} is not a {kind} that starts {default!r}")
        return name

    flags, bags, givers = [], [], []
    for actor in PICKUP_TEXT:
        gives = _short(actor_param(fs, actor, "PouchContentRef").get("PouchActor")) or actor
        if gives != actor and murmur3_32(f"HavePlayedGetEvent.{actor}") in rows:  # unused, set anyway
            flags.append(row(f"HavePlayedGetEvent.{actor}", "Bool", False))
        flags.append(row(f"HavePlayedGetEvent.{gives}", "Bool", False))
        if gives not in givers:
            givers.append(gives)
    for item in givers:
        p = actor_param(fs, item, "PouchContentRef")
        if p.get("IsAbleToGetBagIfGet") is not True or not p.get("SmallBagActor"):
            continue
        bag, kind = _short(p["SmallBagActor"]), p.get("MaxNumGameData")
        rel = f"GameParameter/ExpansionMaxNumActor/{bag}.game__actor__ExpansionMaxNumActor.bgyml"
        size = byml_load(sarc_files(fs.read(f"Pack/Actor/{bag}.pack.zs"))[rel])[0]
        if size.get("GameData") != kind or [_short(a) for a in size.get("Actor", [])] != [item] or \
                size.get("IsItemStockMax") is not False or not isinstance(size.get("MaxNum"), int):
            fail(f"{bag}: its size isn't {kind} for {item} alone ({size})")
        bags.append({"item": item, "bag": bag, "kind": kind, "max": size["MaxNum"],
                     "rows": [row(f"IsGet.{bag}", "Bool", False), row(f"PouchData.{bag}.StockNum", "Int", 0),
                              row(f"PouchContentMaxNum.{kind}", "Int", 0),
                              row(f"CurrentExpansionActor_{kind}", "String64", "")]})
    return {"flags": flags, "bags": bags}


def blocks(fs, romfs):
    import packpaths
    out = []
    for name in BLOCKS:
        rel = f"GameParameter/GrabMoveActorParam/{name}.game__object__GrabMoveActorParam.bgyml"
        holders = sorted(packpaths.carriers(rel, romfs))
        if not holders:
            fail(f"{rel}: no pack holds it")
        raw = {sarc_files(fs.read(p))[rel] for p in holders}
        if len(raw) != 1:
            fail(f"{rel}: the packs holding it differ")
        speed = byml_load(raw.pop())[0].get("MoveSpeed") or {}
        data = speed.get("Data") or []
        if speed.get("Type") != "Hermit2DSplit" or not data or len(data) % 4 or data[-4] > speed.get("MaxX", 0) \
                or data[-3] != 1.0:
            fail(f"{rel}: MoveSpeed is not a Hermit2DSplit curve that ends a whole push by MaxX")
        out.append({"file": rel, "packs": holders, "MoveSpeed": speed})
    return out


def dpad(fs):
    """The hold counter graph's layout, the nodes the D-pad edit copies from other graphs, the accessories and boots
    of the Equipment menu (with which ages may use each) and the save rows the cycle reads."""
    import ainb
    a = ainb.Ainb(fs.raw(DPAD_FILE))
    if [(c["name"], c["main"]) for c in a.commands] != [("Root", 14)]:
        fail(f"{DPAD_FILE}: Root no longer starts at node 14")
    for key, (i, name) in DPAD_NODES.items():
        if i >= len(a.nodes) or a.nodes[i]["name"] != name:
            fail(f"{DPAD_FILE}: node {i} ({key}) is not {name or 'a composite'}")
    hold, trig = DPAD_NODES["hold"][0], DPAD_NODES["trig"][0]
    outs = {t: [e["name"] for e in a.nodes[n]["outputs"]["bool"]] for t, n in (("hold", hold), ("trig", trig))}
    for o in DPAD_OUTPUTS:
        if o not in outs["hold" if o.startswith("Hold") else "trig"]:
            fail(f"{DPAD_FILE}: the button checkers have no {o}")
    hook, reset = DPAD_NODES["hook"][0], DPAD_NODES["reset"][0]
    h = a.nodes[hook]
    src = next((e for e in h["inputs"]["bool"] if e["name"] == "Input"), {})
    kids = {pl["name"]: pl["node"] for pl in h["plugs"][ainb.PLUG_CHILD]}
    if h["type"] != 7 or (src.get("node"), src.get("plug")) != (hold, outs["hold"].index("HoldR")) \
            or kids.get("False") != reset:
        fail(f"{DPAD_FILE}: node {hook} is no longer 'R held? else reset the counter'")

    def inp(i, t, name):
        return next(e for e in a.nodes[i]["inputs"][t] if e["name"] == name)
    for key in ("reset", "counter", "step"):
        i = DPAD_NODES[key][0]
        if inp(i, "string", "GameDataFullName")["value"] != DPAD_COUNTER:
            fail(f"{DPAD_FILE}: node {i} no longer works on {DPAD_COUNTER}")
    if inp(reset, "float", "Value")["value"] != 0.0:
        fail(f"{DPAD_FILE}: node {reset} no longer resets the counter to 0")
    step = DPAD_NODES["step"][0]
    v = inp(step, "float", "Value")
    if v["node"] < 0 or a.nodes[v["node"]]["name"] != "SeqQueryGetGameFrameStepRate":
        fail(f"{DPAD_FILE}: node {step} no longer adds the frame step")
    f32 = DPAD_NODES["f32_sel"][0]
    cases, default = a.f32_cases(f32)
    if [(lo, hi) for lo, hi, _ in cases] != [(1.0, 9999.0)] or default != (DPAD_NODES["dummy"][0], a.F32_OTHER):
        fail(f"{DPAD_FILE}: the menu-open switch (node {f32}) no longer opens on 1..9999 only")
    for key, i in (("bool_sel", 3), ("f32_sel", 20), ("sim", 10)):
        want = {"bool_sel": 7, "f32_sel": 4, "sim": 3}[key]
        if a.nodes[i]["type"] != want:
            fail(f"{DPAD_FILE}: node {i} is no longer a {ainb.NODE_TYPES[want]}")
    h, se = DPAD_NODES["hash"][0], DPAD_NODES["set_enum"][0]
    v = next(e for e in a.nodes[se]["inputs"]["ptr"] if e["name"] == "Value")
    if inp(se, "string", "GameDataFullName")["value"] != "UI_CurrentShortCutCategory" or v["node"] != h \
            or inp(h, "string", "String")["value"] != "AssignableItem":
        fail(f"{DPAD_FILE}: node {se} no longer sets the wheel's category from node {h}'s hash")
    c = a.nodes[DPAD_NODES["closing"][0]]
    if ainb.NODE_TYPES.get(c["type"]) != "ModuleIF_Input_Bool" or [e["value"] for e in c["properties"]["string"]]             != ["IsClosingShortCut"] or [e["name"] for e in c["outputs"]["bool"]] != ["Input"]:
        fail(f"{DPAD_FILE}: node {DPAD_NODES['closing'][0]} is no longer the module's IsClosingShortCut input")
    if inp(DPAD_NODES["set_bool"][0], "string", "GameDataFullName")["value"] != "UI_IsNeedOpenShortCut":
        fail(f"{DPAD_FILE}: node {DPAD_NODES['set_bool'][0]} no longer asks the item wheel to open")
    # the wheel's graph: it forces the item category when it opens (StringSelector 16 -> 17) and closes when L and
    # R are both let go (59 False -> End 5; 52/59 True -> 6, the held branch)
    w = ainb.Ainb(fs.raw(WHEEL_FILE))
    for key, (i, name) in WHEEL_NODES.items():
        if i >= len(w.nodes) or w.nodes[i]["name"] != name:
            fail(f"{WHEEL_FILE}: node {i} ({key}) is not {name or 'a composite'}")
    W = {k: v[0] for k, v in WHEEL_NODES.items()}

    def winp(i, t, name):
        return next(e for e in w.nodes[i]["inputs"][t] if e["name"] == name)
    cases, default = w.string_cases(W["force"])
    if w.nodes[W["force"]]["type"] != 5 or cases != [("AssignableItem", W["set_category"])] \
            or default != (W["set_category"], w.F32_OTHER):
        fail(f"{WHEEL_FILE}: node {W['force']} no longer leads only to the category set")
    if winp(W["set_category"], "string", "GameDataFullName")["value"] != "UI_CurrentShortCutCategory":
        fail(f"{WHEEL_FILE}: node {W['set_category']} no longer sets the wheel's category")
    kids = {pl["name"]: pl["node"] for pl in w.nodes[W["hold_r"]]["plugs"][ainb.PLUG_CHILD]}
    src = winp(W["hold_r"], "bool", "Input")
    outs_w = [e["name"] for e in w.nodes[W["hold"]]["outputs"]["bool"]]
    if (src["node"], outs_w[src["plug"]]) != (W["hold"], "HoldR") or kids != {"True": W["held"], "False": W["end"]}:
        fail(f"{WHEEL_FILE}: node {W['hold_r']} is no longer 'R held? else end'")
    if not {"HoldUp", "HoldDown"} <= set(outs_w):
        fail(f"{WHEEL_FILE}: node {W['hold']} has no HoldUp/HoldDown")
    for i, name, val in ((W["close_flag"], "UI_IsNeedOpenShortCut", False), (W["get_bool"], "UI_IsNeedOpenShortCut", None)):
        if winp(i, "string", "GameDataFullName")["value"] != name or (
                val is not None and winp(i, "bool", "Value")["value"] is not val):
            fail(f"{WHEEL_FILE}: node {i} is no longer the {name} node it was")
    sources = {}
    for key, (file, i, name) in DPAD_SOURCES.items():
        b = ainb.Ainb(fs.raw(file))
        n = b.nodes[i] if i < len(b.nodes) else None
        if n is None or n["name"] != name or (key == "str_sel" and n["type"] != 5):
            fail(f"{file}: node {i} is not {name or 'a StringSelector'}")
        for t in ainb.PTYPES:
            for e in n["properties"][t] + n["inputs"][t]:
                if e.get("flags", 0) & ainb.BB_INDEXED:
                    fail(f"{file}: node {i} {e['name']} reads the blackboard")
        sources[key] = {"file": file, "node": i}
    # the gear, from the Equipment menu's table
    table, _ = byml_load(fs.raw(POUCH_TABLE))
    rows = {r.get("BtnName"): r for r in table.get("EquipmentArray") or []}
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    index = {e["Hash"]: t for t, rs in gd["Data"].items() if t != "Bool64bitKey" for e in rs}
    gear = {}
    for slot, buttons in GEAR_BUTTONS.items():
        gear[slot] = []
        for btn in buttons:
            if btn not in rows:
                fail(f"{POUCH_TABLE}: no button {btn}")
            for act in rows[btn].get("Actor") or []:
                name = act["ActorShort"]
                if not name.startswith("Armor_"):
                    fail(f"{POUCH_TABLE}: {btn} lists {name}, not an accessory or boots")
                g = {"actor": name, "button": btn, "child": bool(act.get("IsUsableChild", False)),
                     "adult": bool(act.get("IsUsableAdult", False))}
                for row, kind in ((f"IsGet.{name}", "Bool"), (f"PouchData.{name}.StockNum", "Int")):
                    if index.get(murmur3_32(row)) != kind:
                        fail(f"save data: {row} is not a {kind}")
                if f"Actor/{name}.engine__actor__ActorParam.bgyml" not in sarc_files(
                        fs.read(f"Pack/Actor/{name}.pack.zs")):
                    fail(f"Pack/Actor/{name}.pack.zs: no ActorParam")
                gear[slot].append(g)
    # the adult's tunics. The Kokiri one is pushed into the pouch on a new file (SetPouchAndStatusForGameStart),
    # its row is the DefaultArmor one, so having it says nothing: "default" keeps it out of "you have tunics"
    info = {r["__RowId"]: r for r in byml_load(fs.read(POUCH_INFO), allow_big=True)[0]}
    tunics = []
    for btn in TUNIC_BUTTONS:
        if btn not in rows:
            fail(f"{POUCH_TABLE}: no button {btn}")
        for act in rows[btn].get("Actor") or []:
            name = act["ActorShort"]
            if not act.get("IsUsableAdult"):
                continue
            if not name.startswith("Armor_Adult_") or (info.get(name) or {}).get("PouchCategory") != "Armor":
                fail(f"{POUCH_TABLE}: {btn} lists {name}, not an adult tunic")
            for row, kind in ((f"IsGet.{name}", "Bool"), (f"PouchData.{name}.StockNum", "Int")):
                if index.get(murmur3_32(row)) != kind:
                    fail(f"save data: {row} is not a {kind}")
            tunics.append({"actor": name, "button": btn, "child": False, "adult": True,
                           "default": info[name].get("PouchSpecialDeal") == "DefaultArmor"})
    if sorted(g["actor"] for g in tunics if g["default"]) != ["Armor_Adult_Normal"] or len(tunics) != 3:
        fail(f"{POUCH_TABLE}: the adult's tunics aren't Kokiri (the default), Goron and Zora: {tunics}")
    from parity._extras_wheel import TUNICS_TO_SWITCH  # the code patch's own "you have a tunic to switch to"
    if sorted(TUNICS_TO_SWITCH) != sorted(g["actor"] for g in tunics if not g["default"]):
        fail(f"{POUCH_TABLE}: the wheel patch's tunics to switch to aren't the adult's other tunics")
    # the wheel patch picks its slots from the Equipment menu's buttons by name, and reads the item buttons for the
    # item wheel: its rule must give exactly this gear, and no item button may hold gear
    from parity._extras_wheel import wheel_of
    for slot, number, have in (("head", 1, gear["head"]), ("boots", 2, gear["boots"]), ("tunics", 3, tunics)):
        named = [a["ActorShort"] for r in rows.values() for a in r.get("Actor") or []
                 if wheel_of(a["ActorShort"]) == number]
        if sorted(named) != sorted(g["actor"] for g in have):
            fail(f"{POUCH_TABLE}: the wheel patch's rule picks {sorted(named)} for the {slot} wheel")
    items = [a["ActorShort"] for r in table.get("ItemArray") or [] for a in r.get("Actor") or []]
    if not items or any(a.startswith("Armor_") for a in items):
        fail(f"{POUCH_TABLE}: ItemArray is empty or holds gear")
    for row, kind in ((GEAR_SLOT["head"], "String64"), (GEAR_SLOT["boots"], "String64"), (TUNIC_SLOT, "String64"),
                      ("Sequence_IsChildhood", "Bool"), (DPAD_COUNTER, "Float")):
        if index.get(murmur3_32(row)) != kind:
            fail(f"save data: {row} is not a {kind}")
    return {"file": DPAD_FILE, "counter": DPAD_COUNTER, "nodes": {k: v[0] for k, v in DPAD_NODES.items()},
            "outputs": list(DPAD_OUTPUTS), "sources": sources, "slots": GEAR_SLOT, "gear": gear,
            "wheel": {"file": WHEEL_FILE, "nodes": W}, "kinds": gear_kinds(fs, gear, gd),
            "tunics": tunics, "tunic_slot": TUNIC_SLOT, "tunic_kinds": gear_kinds(fs, {"tunics": tunics}, gd)}


def gear_kind(actor):
    """The wheel's item kind (a value of PlayerStatus.AssignableItem) for a piece of gear, by its name."""
    if actor == "Armor_GlassTruth":
        return "GlassTruth"
    if actor.startswith("Armor_Child_Mask_Amiibo"):  # "Amiibo" is the amiibo item's (Pouch_Amiibo), so a free one
        return "Lure"
    if actor.startswith("Armor_Child_Mask_"):
        return actor[len("Armor_Child_Mask_"):] + "Mask"
    if actor.startswith("Armor_Adult_") and actor.endswith("Boot"):
        return actor[len("Armor_Adult_"):]
    if actor in ("Armor_Adult_Normal", "Armor_Adult_Goron", "Armor_Adult_Zora"):  # no tunic kinds: a free one
        return "SheikahWarp"
    fail(f"{actor}: no item kind rule")


def gear_kinds(fs, gear, gd):
    """{gear actor: its item kind}. A wheel slot draws nothing for a row without a kind (AssignableItem): every item
    row has one, no gear row does. With a kind, the slot's icon is the actor's own (<name>_PouchIcon, 0x80A93480 by
    name), and the kind only picks a few special looks (bottles, arrows, the Bow, the amiibo item) and a pattern frame
    (0x80A96170) that the masks, the Lens, the boots, Lure and SheikahWarp leave alone. So the masks, the Lens and the
    boots take their own kinds, and the amiibo masks (Amiibo is the amiibo item's) and the tunics (none exists) take
    Lure and SheikahWarp, which no row uses. Each kind must be a value of both ages' item-button enum that no row uses
    yet, and each row must be there without a kind of its own."""
    enums = {e["Hash"]: e["RawValues"] for e in gd["Data"]["Enum"]}
    values = [enums.get(murmur3_32(f"PlayerStatus.AssignableItem.{age}")) for age in ("Adult", "Child")]
    if not all(values):
        fail("save data: no PlayerStatus.AssignableItem.Adult/Child")
    rows = {r["__RowId"]: r for r in byml_load(fs.read(POUCH_INFO), allow_big=True)[0]}
    used = {r.get("AssignableItem") for r in rows.values() if r.get("AssignableItem")}
    out = {}
    for g in [g for gs in gear.values() for g in gs]:
        a, kind = g["actor"], gear_kind(g["actor"])
        if a not in rows or "AssignableItem" in rows[a]:
            fail(f"{POUCH_INFO}: {a} is missing or names a kind already")
        if kind is None:
            continue
        if not all(kind in v for v in values) or kind in used:
            fail(f"{a}: {kind} isn't a free item kind of both ages")
        out[a] = kind
    return out


def main(romfs, vanilla=None):
    fs = Romfs(romfs, vanilla or os.path.join(HERE, "original"))
    out = {"_about": "Built by tools/rando/parity/_extras_qol_build.py from the game files; read by extras_qol.py.",
           "talon": talon(fs, romfs), "frogs": frogs(fs, romfs),
           "replays": replays(flow(fs, romfs, "Dm_SY_Ocarina")), "packs": packs(fs), "gamedata": gamedata(fs),
           "pickup_text": pickup_text(fs), "blocks": blocks(fs, romfs), "dpad": dpad(fs),
           "difficulty": difficulty(fs, romfs)}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {OUT}: {len(out['talon']['steps'])} castle guards, {len(out['replays']['waits'])} song waits, "
          f"{len(out['packs']['wallets'])} wallet rows, {len(out['pickup_text']['flags'])} pickup windows, "
          f"{len(out['pickup_text']['bags'])} first-get bags, "
          f"{len(out['blocks'])} block curves, {sum(map(len, out['dpad']['gear'].values()))} D-pad gear")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
