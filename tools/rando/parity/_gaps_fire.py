"""easier_fire_arrow_entry / fae_torch_count and blue_fire_arrows (story plugin).

The research is in my note torches_bluefire.md, and what's below is a summary of it. The data is
data/rando/gaps_fire.json (python tools/rando/parity/_gaps_fire.py build ROMFS), read from the game and checked
against the vanilla files.

easier_fire_arrow_entry + fae_torch_count
In OoTR the Shadow Temple entrance opens once N of its 24 torches are lit ("this setting does not affect logic").
  - The remake's entrance has 16 candles, not 24 (Obj_CandleStick_GlassTruth_A_02 in ShadowTemple_Static, a ring at
    the warp pad), and they never burn out. Their material wood_fuel_noburnout has IsBurnOut false and
    IsNoExtinguish true, FixedBurningDuration is -1, and the candle AI only puts one out under ForceControl with Burn
    false, which this module never sets. So OoT's time pressure doesn't exist and the count is the whole setting.
  - The door is Logic/ShadowTemple_Level_Room_B1F_A_Prefab_0d1d. Node 0 is an OperateANDFixInputTrue of the 16
    candles' Burning. Node 27 reads it (adult: AND Adulthood) -> 28 (AND not opened), and so does node 32 (child)
    -> 34. Node 37 (OperateORFixInputTrue) latches those into node 33, an EventRequestTrigger for
    Dm_ShadowTemple_0000, which sets the gate flags, and then the gate-open signal lights all 16. Shortening node 0's
    list would make the first N candles enough, not any N.
  - So we build a counter out of the game's nodes. A copy of OperateBoolCount (Gerudo Training Ground Room_08 #15,
    which counts its 9 switches) reads the 16 candles, and a copy of OperateCompareInt (Dodongo's Cavern Room_21 #8,
    A_Bigger) tests count > M - 1. Copies of nodes 27, 28, 32, 34 and 37 read that instead of node 0. Every link in
    this file is a multi-input, so the chain gets copied all the way up to node 33, the first node with a plain
    input, and that one is re-fed. Nodes 0-46 stay, the old chain just doesn't reach the event any more.
  - N (of OoT's 24) -> M (of the remake's 16) = min(15, ceil(2N/3)). That's the same share of the ring and never
    easier than OoTR's share, and N = 23 still asks for fewer than all 16 (OoTR's default 3 -> 2). Din's Fire lights
    all 16.
  - Per frame: 7 logic nodes (one 16-input count, one compare, five 2-3-input AND/OR) in that one room's module.

blue_fire_arrows
In OoTR Ice Arrows act as Blue Fire, so they melt red ice and break Dodongo's Cavern's mud walls. In the logic
Blue_Fire counts Blue_Fire_Arrows, and no world file uses can_break_mud_wall.
  - Red ice (AI/Obj_RedIce_A_01.root, shared by Obj_RedIce_A_01/02/04/06/07/08/09, 17 placements counting King
    Zora's) only melts on the blue-fire message (node 51). It had no Life, so arrow damage never reached its AI.
    What we build: the red ice gets the "hit detector" Life that every hit-reacting object uses
    (Component/LifeParam/SwitchHit, invincible, the Default damage table). The Fire-Arrow ice Obj_Ice_A_01 and the
    eye switches have it. It also gets a melt branch on the AI's root next to the vanilla tree. No vanilla node
    changes, because the drops plugin's red-ice read-back requires that, and both edits combine in either order.
    The branch is Sequential [selector (ice-arrow hit AND not melting yet) -> {melt origin = the ice's position,
    vanilla 43 (IsFireHit for King Zora, no respawn, save flag), vanilla 41}, vanilla 12 (melt delay), vanilla 1
    (melt effect, death)]. That's the vanilla 26 [28, 12, 1] with the hit in place of the blue-fire message.
    Ice-arrow hit = IsOnDamageType(6 = Arrow, as Obj_Ice_A_01 #10) AND LastDamageIsOnDamageElement(1 = Frozen, as
    Enemy_TorchSlug #16, the torch an ice arrow puts out). "Not melting yet" is vanilla node 22 (NOT blackboard
    IsFireHit). Freezard breath (Frozen, but Body damage) and normal, fire and light arrows don't melt it.
    Vanilla shares composite children between parents the same way (127 Sequentials and 617 Simultaneous with
    several parents in the game's AI files).
    Per frame: 9 AI nodes (one Sequential waiting at a selector over 4 queries), 10 with the root's Simultaneous when
    the drops plugin hasn't added it.
  - Dodongo's Cavern's breakables all share Life/DamageParameters/CrackStoneObject (Bomb 100, Hammer 100, Bottle 1,
    every other type 0, MaxLife 6) and have no AI. Blue Fire doesn't break them in the remake either, since the
    blue-fire actors carry no attack and no chemistry.
    What we build, for the 4 dungeon-only actors (Obj_DodongoCave_CrackWall_A_01 x1, _A_02 x2,
    Obj_DodongoCave_CrackFloor_A_01 x1), is a damage table in their packs with CrackStoneObject's rates plus Arrow
    100, and the engine's "only these attacks" rule listing Bomb/Hammer/Bottle and Arrow+Frozen. That's Rule
    1113656608, the same one Obj_InsideGanonCastle_Core_A_01 ("breaks only to Light Arrows") and
    Obj_IronKnuckle_Pillar_A_01 use. make_patch's pack "set" types new values like the ones already in the file, so
    the table is made from a vanilla one that already holds such a rule with typed lists (Enemy_DungeonBoss_Koume's)
    and set to CrackStoneObject's values. The 7 damage types that table doesn't list (CrackStoneObject has them at 0)
    are blocked by the rule anyway.
    Obj_FireTemple_CrackFloor_A_01 inherits the Dodongo floor's ActorParam, so its ActorParam now names the vanilla
    life and it stays vanilla.
    TODO: the 13 generic WallCrack placements in the cavern aren't built. The WallCrack actor is also placed 29 times
    outside it and its files are shared by 23-29 packs, so that one's my decision.
    Per frame: nothing (damage tables only).
  - Item: OoTR's pool holds "Blue Fire Arrows" in place of Ice Arrows, and the remake gives Item_Arrow_Ice for it.
    That needs "Blue Fire Arrows" in config/item_map.json (another work area's file).
    TODO: until it's there, OWNS refuses True, because generation would stop at the first item lookup."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DATA = os.path.join(HERE, "data", "rando", "gaps_fire.json")
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()

# Fire Arrow entry
FAE_LOGIC = "Logic/ShadowTemple_Level_Room_B1F_A_Prefab_0d1d.logic.module.ainb"
COUNT_SRC = ("Logic/GerudoTrainingGround_Level_Room_08_Prefab_0575.logic.module.ainb", 15, "OperateBoolCount")
CMP_SRC = ("Logic/DodongoCavern_Level_Room_21_Prefab_e7c2.logic.module.ainb", 8, "OperateCompareInt")
CANDLE = "ActorLogicCandleStickNeedGlassTruthToSee"
EVENT_NODE, EVENT_INPUT = 33, "EventRequestTrigger"
# the vanilla chain from node 0 to the event, node -> (name, multi-input sources), with node 0 standing for the count
CHAIN = (("adult", 27, "OperateAND", [("cmp", "A_Bigger"), (24, "Adulthood")]),
         ("adult_closed", 28, "OperateAND", [("adult", "True"), (26, "False"), (30, "False")]),
         ("child", 32, "OperateAND", [("cmp", "A_Bigger"), (31, "Childhood")]),
         ("child_closed", 34, "OperateAND", [("child", "True"), (36, "False")]),
         ("latch", 37, "OperateORFixInputTrue", [("adult_closed", "True"), ("child_closed", "True")]))
OOT_TORCHES, REMAKE_CANDLES = 24, 16


def candles_needed(n):
    """OoTR's fae_torch_count (1..23 of 24) -> candles of the remake's 16. Same share, rounded up, always fewer than
    16."""
    return min(REMAKE_CANDLES - 1, math.ceil(n * REMAKE_CANDLES / OOT_TORCHES))


# Blue_fire_arrows: red ice
RED_ICE_PACKS = tuple(f"Pack/Actor/Obj_RedIce_A_0{k}.pack.zs" for k in (1, 2, 4, 6, 7, 8, 9))
RED_AI = "AI/Obj_RedIce_A_01.root.ainb"
RED_AP = "Actor/Obj_RedIce_A_01.engine__actor__ActorParam.bgyml"  # every red ice's parent ActorParam
SWITCH_LIFE = "Component/LifeParam/SwitchHit.game__component__LifeParam.bgyml"
SWITCH_LIFE_FROM = "Pack/Actor/Obj_EyeSwitch_A_01.pack.zs"
RED_SRC = {"pack": RED_ICE_PACKS[0], "file": RED_AI}
ICE_SRC = {"pack": "Pack/Actor/Obj_Ice_A_01.pack.zs", "file": "AI/Obj_Ice_A_01.root.ainb"}
SLUG_SRC = {"pack": "Pack/Actor/Enemy_TorchSlug.pack.zs", "file": "AI/Enemy_TorchSlug.utility.root.ainb"}
BF3_SRC = {"pack": "Pack/Actor/Obj_BlueFire_A_03.pack.zs", "file": "AI/Obj_BlueFire_A_03.root.ainb"}
ARROW_TYPE, FROZEN_ELEMENT = 6, 1  # ExternalDamageTypes 6 (Obj_Ice_A_01 'isArrow'), DamageElement 1 (TorchSlug)
# Vanilla red-ice nodes the branch copies or reuses. build and the read-back both check them.
# The melt Sequential 26 is [28 selector (message) -> 45 -> 31 {27 melt origin, 43 flags and save, 41 LOD}, 12 delay,
# 1 melt and death]. 29 is "nothing yet", and 22 is NOT blackboard IsFireHit (true until a melt starts).
RED_MSG, RED_SEQ, RED_SEL_MSG, RED_MELT, RED_POS, RED_WAIT, RED_NOT_MELTING = 51, 26, 28, 31, 27, 29, 22
RED_SEQ_KIDS, RED_MELT_KIDS = (28, 12, 1), (27, 43, 41)

# Blue_fire_arrows: Dodongo's Cavern walls
WALL_ACTORS = ("Obj_DodongoCave_CrackWall_A_01", "Obj_DodongoCave_CrackWall_A_02", "Obj_DodongoCave_CrackFloor_A_01")
FT_FLOOR = "Obj_FireTemple_CrackFloor_A_01"  # inherits the Dodongo floor's ActorParam, so it's kept vanilla
WALL_PACKS = tuple(f"Pack/Actor/{a}.pack.zs" for a in WALL_ACTORS + (FT_FLOOR,))
CRACK_DP = "Life/DamageParameters/CrackStoneObject.game__life__DamageParameters.bgyml"
CRACK_LP = "Component/LifeParam/WallCrack.game__component__LifeParam.bgyml"
TEMPLATE = ("Pack/Actor/Enemy_DungeonBoss_Koume.pack.zs",
            "Life/DamageParameters/Enemy_DungeonBoss_Koume.game__life__DamageParameters.bgyml")
NEW_DP = "Life/DamageParameters/CrackStoneObject_IceArrow.game__life__DamageParameters.bgyml"
NEW_LP = "Component/LifeParam/WallCrack_IceArrow.game__component__LifeParam.bgyml"
ONLY_RULE = 1113656608  # "only these attacks deal damage" (FeatureExplaination of its vanilla users)
H = {"Arrow": 1499870550, "Frozen": 2817341698, "Bomb": 3237216321, "Hammer": 85358548, "Bottle": 3429998625}
EXCEPTION = {"FeatureExplaination": "Rando blue_fire_arrows: bombs, hammer, bottle and Ice Arrows only",
             "Rule": ONLY_RULE, "Rule_AddDamageAmount": 0, "Rule_DamageRate": 0.5,
             "Elements": [{"DamagePosHeightLimit": 0.0, "Affiliations": [], "DamageAttributes": [],
                           "LastUserAffiliations": [], "DamageElements": [],
                           "DamageTypes": [H["Bomb"], H["Hammer"], H["Bottle"]]},
                          {"DamagePosHeightLimit": 0.0, "Affiliations": [], "DamageAttributes": [],
                           "LastUserAffiliations": [], "DamageElements": [H["Frozen"]], "DamageTypes": [H["Arrow"]]}]}
ARROW_RATE = 100.0  # as Bomb and Hammer: one hit breaks it (MaxLife 6)
VANILLA_LIFE = "?" + CRACK_LP


def _item_mapped():
    """True when config/item_map.json gives a remake item for OoTR's 'Blue Fire Arrows'."""
    try:
        m = json.load(open(os.path.join(HERE, "config", "item_map.json"), encoding="utf-8"))
    except OSError:
        return False
    return "Blue Fire Arrows" in m.get("items", {}) or "Blue Fire Arrows" in m.get("junk_for", {})


OWNS = {"easier_fire_arrow_entry": (False, True), "fae_torch_count": None,
        "blue_fire_arrows": (False, True) if _item_mapped() else (False,)}


# Data (build)
def _leaves(o, path=()):
    """(path, value) for every scalar or plain list in a parsed BYML. Walks the dictionaries and keeps int keys."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _leaves(v, path + (k,))
    else:
        yield path, o


def build(romfs=DEFAULT_ROMFS):
    """Reads and checks everything the plan relies on in the vanilla game, then writes DATA."""
    import ainb
    from romtools import Romfs, byml_load, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))

    def pack_file(pack, inner):
        return sarc_files(fs.read(pack))[inner]
    # Fire Arrow entry
    st = ainb.Ainb(fs.raw(FAE_LOGIC))
    n0 = st.nodes[0]
    if n0["name"] != "OperateANDFixInputTrue" or n0["inputs"]["bool"][0]["node"] != -100:
        raise RuntimeError(f"{FAE_LOGIC}: node 0 is no longer the candles' AND")
    b, cnt = -100 - n0["inputs"]["bool"][0]["node"], n0["inputs"]["bool"][0]["plug"]
    candles = [m[0] for m in st.multi[b:b + cnt]]
    if cnt != REMAKE_CANDLES or any(st.nodes[c]["name"] != CANDLE or st.multi[b + k][1] != 0
                                    for k, c in enumerate(candles)):
        raise RuntimeError(f"{FAE_LOGIC}: node 0 doesn't read the 16 candles' Burning")
    for _, i, name, srcs in CHAIN:
        if st.nodes[i]["name"] != name:
            raise RuntimeError(f"{FAE_LOGIC}: node {i} is no longer {name}")
        e = st.nodes[i]["inputs"]["bool"][0]
        got = [(m[0], m[1]) for m in st.multi[-100 - e["node"]:-100 - e["node"] + e["plug"]]]
        want = []
        for s, out in srcs:
            if isinstance(s, int):
                want.append((s, st._output_index(s, "bool", out)))
            else:  # the vanilla source: node 0 (count) or the chain node this one replaces
                v = {"cmp": 0, **{nm: j for nm, j, _, _ in CHAIN}}[s]
                want.append((v, st._output_index(v, "bool", "True")))
        if got != want:
            raise RuntimeError(f"{FAE_LOGIC}: node {i} reads {got}, not {want}")
    ev = st._input(EVENT_NODE, EVENT_INPUT)[1]
    if ev["node"] != 37 or st.nodes[EVENT_NODE]["name"] != "ActorLogicEventRequestActor":
        raise RuntimeError(f"{FAE_LOGIC}: node {EVENT_NODE} isn't the latch-fed event request")
    for f, i, name in (COUNT_SRC, CMP_SRC):
        if ainb.Ainb(fs.raw(f)).nodes[i]["name"] != name:
            raise RuntimeError(f"{f}: node {i} is no longer {name}")
    # red ice
    red = ainb.Ainb(pack_file(*RED_SRC.values()))
    for i, name in ((RED_MSG, "QueryMessageBlueFireReceiveMessage"), (RED_POS, "OneShotSetRepresentativeBoneWorldPos"),
                    (RED_WAIT, "ExecuteGenericSetResultNone"), (RED_NOT_MELTING, "QueryInvertBool"),
                    (21, "QueryLogicalConjunction")):
        if red.nodes[i]["name"] != name:
            raise RuntimeError(f"{RED_AI}: node {i} is no longer {name}")
    if ([pl["node"] for pl in red.nodes[RED_SEQ]["plugs"][2]] != list(RED_SEQ_KIDS)
            or [pl["node"] for pl in red.nodes[RED_MELT]["plugs"][2]] != list(RED_MELT_KIDS)
            or red._input(RED_SEL_MSG, "Input")[1]["node"] != RED_MSG
            or {pl["name"]: pl["node"] for pl in red.nodes[RED_SEL_MSG]["plugs"][2]}.get("False") != RED_WAIT
            or red._input(RED_NOT_MELTING, "Bool")[1]["flags"] != 0x80000000
            or red.bb["bool"][0]["name"] != "IsFireHit"):
        raise RuntimeError(f"{RED_AI}: the melt tree moved")
    # Dodongo's Cavern walls: the template's leaves set to CrackStoneObject's
    crack = byml_load(pack_file(WALL_PACKS[0], CRACK_DP))[0]
    tmpl = byml_load(pack_file(*TEMPLATE))[0]
    cl, tl = dict(_leaves(crack)), dict(_leaves(tmpl))
    ex_key = ("ExternalDamageParameters", "ExternalDamageExceptionDefines")
    sets, unlisted = {}, []
    for p, v in cl.items():
        if p == ex_key:
            continue
        if p not in tl:
            if p[:2] != ("ExternalDamageParameters", "DamageRates") or v != 0.0:
                raise RuntimeError(f"{TEMPLATE[1]} lacks {p} (CrackStoneObject: {v})")
            unlisted.append(p[2])  # a damage type at 0 that the template doesn't list, the "only" rule blocks it
            continue
        want = ARROW_RATE if p == ("ExternalDamageParameters", "DamageRates", H["Arrow"]) else v
        if type(tl[p]) is not type(v):
            raise RuntimeError(f"{p}: {type(tl[p]).__name__} in the template, {type(v).__name__} in CrackStoneObject")
        if tl[p] != want:
            sets[".".join(map(str, p))] = want
    extra = [p for p in tl if p not in cl]
    if extra:
        raise RuntimeError(f"{TEMPLATE[1]} has keys CrackStoneObject hasn't: {extra}")
    sets[".".join(ex_key)] = [EXCEPTION]
    out = {"_about": "Read from the game by tools/rando/parity/_gaps_fire.py build (checked against the vanilla files)",
           "fae": {"file": FAE_LOGIC, "nodes": len(st.nodes), "candles": candles},
           "walls": {"template": list(TEMPLATE), "sets": sets, "unlisted_rates": unlisted,
                     "crack_rates": {str(k): v for k, v in crack["ExternalDamageParameters"]["DamageRates"].items()}}}
    with open(DATA, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return out


def _data():
    return json.load(open(DATA, encoding="utf-8"))


# Plan
def fae_ops(n_ootr, data):
    """The "ainb" entry for the Shadow Temple door module, so M of the 16 candles open it."""
    m = candles_needed(n_ootr)
    base = data["fae"]["nodes"]
    idx = {"count": base, "cmp": base + 1}
    idx.update({name: base + 2 + k for k, (name, _, _, _) in enumerate(CHAIN)})
    edits = [
        {"copy": {"from": {"file": COUNT_SRC[0]}, "nodes": [COUNT_SRC[1]], "label": "count", "follow": False,
                  "values": {str(COUNT_SRC[1]): {"BoolMulti": [[c, "Burning"] for c in data["fae"]["candles"]]}}}},
        {"copy": {"from": {"file": CMP_SRC[0]}, "nodes": [CMP_SRC[1]], "label": "cmp", "follow": False}},
        {"feed": {"from": f"count:{COUNT_SRC[1]}", "output": "Int", "to": f"cmp:{CMP_SRC[1]}", "input": "Int_A"}},
        {"set_input": {"node": f"cmp:{CMP_SRC[1]}", "name": "Int_B", "value": m - 1}},  # count > M-1
    ]
    for name, i, _, srcs in CHAIN:
        sources = [[s if isinstance(s, int) else idx[s], out] for s, out in srcs]
        edits.append({"copy": {"from": {"file": FAE_LOGIC}, "nodes": [i], "label": name, "follow": False,
                               "values": {str(i): {"BoolMulti": sources}}}})
    edits.append({"feed": {"from": f"latch:{CHAIN[-1][1]}", "output": "True", "to": EVENT_NODE, "input": EVENT_INPUT}})
    note = {"file": FAE_LOGIC, "torches": n_ootr, "candles": m, "nodes": idx, "vanilla_nodes": base}
    return {"file": FAE_LOGIC, "edits": edits}, note


def red_ice_ops():
    """The red ice's melt branch for an ice-arrow hit. It sits at the root next to the vanilla tree, so no vanilla node
    changes (the drops plugin's read-back requires that).

    Sequential [selector (ice-arrow hit AND not yet melting) -> {own position as the melt origin, vanilla 43 (IsFireHit,
    no respawn, save flag), vanilla 41}, vanilla 12 (melt delay), vanilla 1 (melt, death)]

    That's the vanilla 26 [28, 12, 1] with the hit in place of the message. Vanilla shares composite children between
    parents the same way (127 Sequentials, 617 Simultaneous in AI files)."""
    edits = [
        {"wrap": {"command": "Root", "if_needed": True}},  # the drops plugin may have wrapped it already
        {"copy": {"from": ICE_SRC, "nodes": [10], "label": "arrow", "follow": False}},
        {"copy": {"from": SLUG_SRC, "nodes": [16], "label": "frozen", "follow": False}},
        {"copy": {"from": RED_SRC, "nodes": [21], "label": "icearrow", "follow": False}},
        {"copy": {"from": RED_SRC, "nodes": [21], "label": "fresh", "follow": False}},
        {"copy": {"from": RED_SRC, "nodes": [RED_SEQ], "label": "melt", "follow": False}},
        {"copy": {"from": RED_SRC, "nodes": [RED_SEL_MSG], "label": "hit", "follow": False}},
        {"copy": {"from": RED_SRC, "nodes": [RED_MELT], "label": "start", "follow": False}},
        {"copy": {"from": RED_SRC, "nodes": [RED_POS], "label": "pos", "follow": False}},
        {"copy": {"from": BF3_SRC, "nodes": [35], "label": "here", "follow": False}},
        {"feed": {"from": "arrow:10", "output": "Bool", "to": "icearrow:21", "input": "ValueA"}},
        {"feed": {"from": "frozen:16", "output": "Bool", "to": "icearrow:21", "input": "ValueB"}},
        {"feed": {"from": "icearrow:21", "output": "Result", "to": "fresh:21", "input": "ValueA"}},
        {"feed": {"from": RED_NOT_MELTING, "output": "Bool", "to": "fresh:21", "input": "ValueB"}},
        {"feed": {"from": "fresh:21", "output": "Result", "to": f"hit:{RED_SEL_MSG}", "input": "Input"}},
        {"link": {"from": "here:35", "output": "Position", "to": f"pos:{RED_POS}", "input": "WorldPos"}},
        {"add_child": {"parent": f"start:{RED_MELT}", "child": f"pos:{RED_POS}"}},
    ]
    edits += [{"add_child": {"parent": f"start:{RED_MELT}", "child": k}} for k in RED_MELT_KIDS[1:]]
    edits += [{"add_child": {"parent": f"hit:{RED_SEL_MSG}", "child": f"start:{RED_MELT}", "name": "True"}},
              {"add_child": {"parent": f"hit:{RED_SEL_MSG}", "child": RED_WAIT, "name": "False"}},
              {"add_child": {"parent": f"melt:{RED_SEQ}", "child": f"hit:{RED_SEL_MSG}"}}]
    edits += [{"add_child": {"parent": f"melt:{RED_SEQ}", "child": k}} for k in RED_SEQ_KIDS[1:]]
    edits.append({"add_child": {"parent": "@Root", "child": f"melt:{RED_SEQ}"}})
    packs = [{"pack": list(RED_ICE_PACKS), "file": SWITCH_LIFE, "from_pack": SWITCH_LIFE_FROM},
             {"pack": "*", "file": RED_AP, "set": {"Components.LifeRef": "?" + SWITCH_LIFE}}]
    return {"pack": "*", "file": RED_AI, "edits": edits}, packs


def wall_ops(data):
    w = data["walls"]
    packs = [{"pack": list(WALL_PACKS), "file": NEW_DP, "from_pack": w["template"][0], "new_from": w["template"][1],
              "set": w["sets"]},
             {"pack": list(WALL_PACKS), "file": NEW_LP, "new_from": CRACK_LP,
              "set": {"DamageParameters": "Work/" + NEW_DP.replace(".bgyml", ".gyml")}}]
    for a in WALL_ACTORS:  # each actor's own ActorParam (the floor's is also the Fire Temple floor's parent)
        f = f"Actor/{a}.engine__actor__ActorParam.bgyml"
        packs.append({"pack": "*", "file": f, "set": {"Components.LifeRef": "?" + NEW_LP}})
    packs.append({"pack": [f"Pack/Actor/{FT_FLOOR}.pack.zs"], "file": f"Actor/{FT_FLOOR}.engine__actor__ActorParam.bgyml",
                  "set": {"Components.LifeRef": VANILLA_LIFE}})
    return packs


def world_plan(settings, world):
    """This module's plan sections for the seed's settings ({} when none applies)."""
    ws = getattr(world, "settings", settings)
    ainb_ops, packs, gaps = [], [], {}
    if getattr(ws, "easier_fire_arrow_entry", False):
        n = getattr(ws, "fae_torch_count", 3)
        if not isinstance(n, int) or not 1 <= n <= OOT_TORCHES - 1:
            raise ValueError(f"fae_torch_count = {n!r}: OoTR's range is 1..{OOT_TORCHES - 1}")
        op, note = fae_ops(n, _data())
        ainb_ops.append(op)
        gaps["fire_arrow_entry"] = note
    if getattr(ws, "blue_fire_arrows", False):
        op, red_packs = red_ice_ops()
        ainb_ops.append(op)
        packs += red_packs + wall_ops(_data())
        gaps["blue_fire_arrows"] = {"red_ice": {"packs": list(RED_ICE_PACKS), "ai": RED_AI, "actor": RED_AP},
                                    "walls": {"packs": list(WALL_PACKS), "actors": list(WALL_ACTORS),
                                              "kept": FT_FLOOR}}
    out = {}
    if ainb_ops:
        out["ainb"] = ainb_ops
    if packs:
        out["packs"] = packs
    if gaps:
        out["_gaps"] = gaps
    return out


def UNTESTED(settings):
    out = []
    if getattr(settings, "easier_fire_arrow_entry", False):
        n = getattr(settings, "fae_torch_count", 3)
        out.append(f"easier_fire_arrow_entry: {candles_needed(n)} of the Shadow Temple entrance's 16 candles open it "
                   f"(fae_torch_count {n} of OoT's 24; a new 16-input count in its level logic)")
    if getattr(settings, "blue_fire_arrows", False):
        out.append("blue_fire_arrows: Ice Arrows melt every red ice (Life added, 8 AI nodes) and break Dodongo's "
                   "Cavern's 4 dungeon-only breakables (own damage table); its 13 generic cracked walls still need "
                   "bombs or the hammer")
    return out


# Read-back (parity/_gaps_check.py)
READERS = {"fire_arrow_entry": "verify_fae", "blue_fire_arrows": "verify_bfa"}
PARITY_NOTE = {
    "blue_fire_arrows": "red ice and 4 of Dodongo's Cavern's 17 breakables; its other 13 are the generic crack wall "
                        "(29 more outside the dungeon), left alone: logic-neutral (OoTR's mud-wall helper is used by "
                        "no logic file); a cloned actor is the route if an in-game test ever proves re-typing safe",
    "fae_torch_count": "OoTR's N of 24 torches = min(15, ceil(2N/3)) of the remake's 16 candles",
}


def _fs(romfs, patch=None):
    """The game as built (patch given) or vanilla."""
    from romtools import Romfs
    return Romfs(romfs, os.path.join(HERE, "original"), [patch] if patch else [])


def _multi(a, i, name="BoolMulti"):
    e = a._input(i, name)[1]
    if e["node"] > -100:
        return None
    b = -100 - e["node"]
    return [(m[0], a.nodes[m[0]]["outputs"]["bool"][m[1]]["name"]) for m in a.multi[b:b + e["plug"]]]


def verify_fae(patch, note, romfs):
    import ainb
    fs, van = _fs(romfs, patch), _fs(romfs)
    bad = []
    a, v = ainb.Ainb(fs.raw(note["file"])), ainb.Ainb(van.raw(note["file"]))
    idx, base = note["nodes"], note["vanilla_nodes"]
    if len(v.nodes) != base or len(a.nodes) != base + 2 + len(CHAIN):
        return [f"{note['file']}: {len(a.nodes)} nodes (vanilla {len(v.nodes)}, planned {base + 2 + len(CHAIN)})"]
    want_names = {"count": "OperateBoolCount", "cmp": "OperateCompareInt", **{n: nm for n, _, nm, _ in CHAIN}}
    for k, j in idx.items():
        if a.nodes[j]["name"] != want_names[k]:
            bad.append(f"node {j} is {a.nodes[j]['name']}, not {want_names[k]}")
    if bad:
        return bad
    candles = _data()["fae"]["candles"]
    if _multi(a, idx["count"]) != [(c, "Burning") for c in candles]:
        bad.append(f"the count reads {_multi(a, idx['count'])}, not the 16 candles' Burning")
    if any(a.nodes[c]["name"] != CANDLE for c in candles):
        bad.append("a counted node is not a candle")
    cmp_a = a._input(idx["cmp"], "Int_A")[1]
    cmp_b = a._input(idx["cmp"], "Int_B")[1]
    if cmp_a["node"] != idx["count"] or cmp_b["node"] != -1 or cmp_b["value"] != note["candles"] - 1:
        bad.append(f"the compare reads node {cmp_a['node']} > {cmp_b['value']} (planned count > {note['candles'] - 1})")
    if note["candles"] != candles_needed(note["torches"]):
        bad.append(f"{note['candles']} candles for {note['torches']} torches (rule: {candles_needed(note['torches'])})")
    for name, _, _, srcs in CHAIN:
        want = [(s if isinstance(s, int) else idx[s], out) for s, out in srcs]
        if _multi(a, idx[name]) != want:
            bad.append(f"{name} (node {idx[name]}) reads {_multi(a, idx[name])}, not {want}")
    ev = a._input(EVENT_NODE, EVENT_INPUT)[1]
    if ev["node"] != idx["latch"] or a.nodes[idx["latch"]]["outputs"]["bool"][ev["plug"]]["name"] != "True":
        bad.append(f"the event request reads node {ev['node']} output {ev['plug']}, not the new latch's True")
    for i in range(base):  # every vanilla node as it was, but the event's input
        if i != EVENT_NODE and ainb.describe_node(a, i) != ainb.describe_node(v, i):
            bad.append(f"vanilla node {i} changed")
    return bad


def verify_bfa(patch, note, romfs):
    import ainb
    from romtools import byml_load, sarc_files
    fs, van = _fs(romfs, patch), _fs(romfs)
    bad = []
    ais = set()
    for pk in note["red_ice"]["packs"]:
        files = sarc_files(fs.read(pk))
        ap = byml_load(files[note["red_ice"]["actor"]])[0]
        if ap.get("Components", {}).get("LifeRef") != "?" + SWITCH_LIFE:
            bad.append(f"{pk}: red ice LifeRef {ap.get('Components', {}).get('LifeRef')!r}")
        if files.get(SWITCH_LIFE) != sarc_files(van.read(SWITCH_LIFE_FROM))[SWITCH_LIFE]:
            bad.append(f"{pk}: {SWITCH_LIFE} missing or not the vanilla file")
        ais.add(files[note["red_ice"]["ai"]])
    if len(ais) != 1:
        bad.append(f"{note['red_ice']['ai']} differs between the red-ice packs")
    a = ainb.Ainb(next(iter(ais)))

    def src(i, name):
        e = a._input(i, name)[1]
        return (e["node"], a.nodes[e["node"]]["outputs"]["bool"][e["plug"]]["name"]) if e["node"] >= 0 else None

    def kids(i):
        return [pl["node"] for pl in a.nodes[i]["plugs"][2]]
    v = ainb.Ainb(sarc_files(van.read(note["red_ice"]["packs"][0]))[note["red_ice"]["ai"]])
    root = a.commands[0]["main"]
    changed = [i for i in range(len(v.nodes)) if i != v.commands[0]["main"]
               and ainb.describe_node(a, i) != ainb.describe_node(v, i)]
    if changed:
        bad.append(f"red ice: vanilla nodes changed {changed}")
    branch = [k for k in kids(root) if k >= len(v.nodes) and a.nodes[k]["type"] == 2]
    if len(branch) != 1:
        return bad + [f"red ice: {len(branch)} new Sequentials on the root (planned 1)"]
    seq = kids(branch[0])
    if len(seq) != 3 or seq[1:] != list(RED_SEQ_KIDS[1:]) or a.nodes[seq[0]]["type"] != 7:
        return bad + [f"red ice: the branch runs {seq}, not [hit selector, {RED_SEQ_KIDS[1]}, {RED_SEQ_KIDS[2]}]"]
    sel = seq[0]
    cases = {pl["name"]: pl["node"] for pl in a.nodes[sel]["plugs"][2]}
    start = cases.get("True")
    if cases.get("False") != RED_WAIT or start is None or a.nodes[start]["type"] != 3 or kids(start)[1:] != list(RED_MELT_KIDS[1:]):
        bad.append(f"red ice: the hit selector's cases are {cases}")
    else:
        pos = kids(start)[0]
        if a.nodes[pos]["name"] != "OneShotSetRepresentativeBoneWorldPos" or a.nodes[a._input(pos, "WorldPos")[1]["node"]]["name"] != "QueryActorGetPosition":
            bad.append("red ice: the branch's melt origin isn't the ice's own position")
    fresh = src(sel, "Input")
    ice = fresh and a.nodes[fresh[0]]["name"] == "QueryLogicalConjunction" and src(fresh[0], "ValueA")
    if not ice or src(fresh[0], "ValueB") != (RED_NOT_MELTING, "Bool") or a.nodes[ice[0]]["name"] != "QueryLogicalConjunction":
        return bad + ["red ice: the branch doesn't wait for 'ice-arrow hit AND not melting yet'"]
    t, f = src(ice[0], "ValueA"), src(ice[0], "ValueB")
    if a.nodes[t[0]]["name"] != "QueryDamageCalculatorIsOnDamageType" or a._input(t[0], "ExternalDamageTypes")[1]["value"] != ARROW_TYPE:
        bad.append("red ice: the ice-arrow test doesn't ask for arrow damage")
    if a.nodes[f[0]]["name"] != "QueryGetLastDamageIsOnDamageElementFromExternalDamageCalculator" or a._input(f[0], "DamageElement")[1]["value"] != FROZEN_ELEMENT:
        bad.append("red ice: the ice-arrow test doesn't ask for the Frozen element")
    # walls
    for pk in note["walls"]["packs"]:
        files = sarc_files(fs.read(pk))
        lp = byml_load(files.get(NEW_LP, b""))[0] if NEW_LP in files else {}
        if lp.get("DamageParameters") != "Work/" + NEW_DP.replace(".bgyml", ".gyml"):
            bad.append(f"{pk}: {NEW_LP} doesn't point at {NEW_DP}")
        if NEW_DP not in files:
            bad.append(f"{pk}: no {NEW_DP}")
            continue
        bad += [f"{pk}: {x}" for x in _check_table(byml_load(files[NEW_DP])[0],
                                                   byml_load(sarc_files(van.read(pk))[CRACK_DP])[0])]
    for act in note["walls"]["actors"]:
        files = sarc_files(fs.read(f"Pack/Actor/{act}.pack.zs"))
        life = byml_load(files[f"Actor/{act}.engine__actor__ActorParam.bgyml"])[0].get("Components", {}).get("LifeRef")
        if life != "?" + NEW_LP:
            bad.append(f"{act}: LifeRef {life!r}")
    kept = note["walls"]["kept"]
    files = sarc_files(fs.read(f"Pack/Actor/{kept}.pack.zs"))
    life = byml_load(files[f"Actor/{kept}.engine__actor__ActorParam.bgyml"])[0].get("Components", {}).get("LifeRef")
    if life != VANILLA_LIFE:
        bad.append(f"{kept}: LifeRef {life!r} (should stay the vanilla {VANILLA_LIFE})")
    return bad


def _check_table(got, crack):
    """The new damage table should be CrackStoneObject's (with Arrow 100) plus the rule, typed like the game's."""
    from romtools import U32
    bad = []
    gl, cl = dict(_leaves(got)), dict(_leaves(crack))
    ex_key = ("ExternalDamageParameters", "ExternalDamageExceptionDefines")
    for p, v in cl.items():
        if p == ex_key:
            continue
        want = ARROW_RATE if p == ("ExternalDamageParameters", "DamageRates", H["Arrow"]) else v
        if p not in gl:
            if p[:2] == ("ExternalDamageParameters", "DamageRates") and v == 0.0:
                continue  # a type at 0 the table doesn't list, the rule blocks it
            bad.append(f"no {'.'.join(map(str, p))}")
        elif gl[p] != want or type(gl[p]) is not type(v):
            bad.append(f"{'.'.join(map(str, p))} = {gl[p]!r} ({type(gl[p]).__name__}), not {want!r}")
    extra = [p for p in gl if p not in cl]
    if extra:
        bad.append(f"keys CrackStoneObject hasn't: {extra[:3]}")
    ex = gl.get(ex_key) or []
    if len(ex) != 1:
        return bad + [f"{len(ex)} damage exception rules (planned 1)"]
    r = ex[0]
    if not isinstance(r["Rule"], U32) or r["Rule"] != ONLY_RULE or r["Rule_AddDamageAmount"] != 0:
        bad.append(f"rule {r['Rule']!r}, not the 'only these attacks' rule {ONLY_RULE}")
    els = [(sorted(e["DamageTypes"]), sorted(e["DamageElements"]), all(isinstance(x, U32) for x in
                                                                        e["DamageTypes"] + e["DamageElements"]))
           for e in r["Elements"]]
    want = [(sorted([H["Bomb"], H["Hammer"], H["Bottle"]]), [], True), ([H["Arrow"]], [H["Frozen"]], True)]
    if els != want or any(e["Affiliations"] or e["DamageAttributes"] or e["LastUserAffiliations"] for e in r["Elements"]):
        bad.append(f"the rule's attacks are {els}, not bombs/hammer/bottle and Arrow+Frozen (U32)")
    return bad


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        o = build(*(sys.argv[2:3] or [DEFAULT_ROMFS]))
        print(f"{len(o['fae']['candles'])} candles, {o['fae']['nodes']} door nodes; damage table: "
              f"{len(o['walls']['sets'])} sets, {len(o['walls']['unlisted_rates'])} types left to the rule -> {DATA}")
    else:
        sys.exit(__doc__)
