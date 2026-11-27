"""Ganon's boss key on a condition (OoTR shuffle_ganon_bosskey 'stones', 'medallions', 'dungeons', 'tokens',
'hearts', and 'triforce', which OoTR forces in a Triforce Hunt).

OoTR places the key at "Gift from Sages" (Root, rule can_receive_ganon_bosskey) and hands it over as soon as the
condition holds, wherever the player is. In the remake all the key does is open one door, Ganon's Tower's boss lock
(`Obj_DoorChainLock_A_02` #13270606936311844433, InsideGanonCastle_Static). Its AI (`AI/BossDoorChainLock.root.ainb`,
shared by every boss lock) lets the player use the lock while `QueryDungeonIsGetBossKey` (the current dungeon's
`DungeonInfo.<area>.IsGetBossKey`) OR the lock's blackboard `isUseAutoData` is false. That's node 8, a
QueryLogicalDisjunction with its ValueA fed by node 0. The unlock scene (`Common_Dungeon_OpenDoorChainLockMove:
MoveToPlusZ_Boss`) plays Link's animation and checks nothing, and the lock saves `IsChainLockDoorOpen.<instance>`
itself.

So the condition goes into the lock. Node 8's ValueA becomes
    QueryDungeonIsGetBossKey OR (own instance Name == "RandoGanonBossKey" AND Rando_GanonBossKey_Exp)
with the name and string compare run once (OutputOnlyOnEnter) and the expression live. Only Ganon's lock gets that
Name, so every other boss lock behaves like before. Rando_GanonBossKey_Exp is a new expression flag (not saved) that
holds OoTR's condition the same way the bridge's does (_story_conditions: IsGet.Item_Stone_* / IsGet.Item_Medal_*
counted the way OoTR counts the items, Gold Skulltula tokens, max life, the Triforce Hunt count). The key item
itself is never shown. OoTR's "Gift from Sages" is locked to it, so the door opens exactly when OoTR's logic says
you have the key.
'on_lacs' needs nothing here. OoTR puts the key at "ToT Light Arrows Cutscene", a scene location whose give step
calls the key's credit entry (dungeons.item_for, like any dungeon item at a scene location)."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

CONDITIONS = ("stones", "medallions", "dungeons", "tokens", "hearts", "triforce")
DOOR_FILE = "Banc/InsideGanonCastle/InsideGanonCastle_Static.bcett.byml.zs"
DOOR_HASH = "13270606936311844433"
DOOR_ACTOR = "Obj_DoorChainLock_A_02"
DOOR_NAME = "RandoGanonBossKey"
EXP = "Rando_GanonBossKey_Exp"
AI = "AI/BossDoorChainLock.root.ainb"
AI_SRC = {"pack": "Pack/Actor/Obj_DoorChainLock_A_02.pack.zs", "file": AI}
KEY_NODE, OR_NODE, AND_NODE = 0, 8, 12  # vanilla: QueryDungeonIsGetBossKey, its disjunction, a conjunction (copied)
EXP_SRC = ({"pack": "Pack/Actor/Animal_Epona_Adult.pack.zs", "file": "AI/GameRomHorse.action.riddenbyplayer.module.ainb"},
           6)  # QueryGetNonStructGameDataBoolExp with a constant GameDataFullName


def condition(settings):
    return getattr(settings, "shuffle_ganon_bosskey", None) in CONDITIONS


def requirement(settings):
    from parity import _story_conditions as C
    return C.requirement(settings, "ganon_bosskey")


def _check_sources(fs):
    """Reads the vanilla nodes this edit relies on from the game, and refuses if a game update moved them."""
    from romtools import sarc_files
    import ainb
    a = ainb.Ainb(sarc_files(fs.read(AI_SRC["pack"]))[AI])
    names = {KEY_NODE: "QueryDungeonIsGetBossKey", OR_NODE: "QueryLogicalDisjunction",
             AND_NODE: "QueryLogicalConjunction"}
    for i, want in names.items():
        if a.nodes[i]["name"] != want:
            raise RuntimeError(f"{AI}: node {i} is {a.nodes[i]['name']}, not {want} (game update?)")
    src = [e for e in a.nodes[OR_NODE]["inputs"]["bool"] if e["name"] == "ValueA"]
    if [e["node"] for e in src] != [KEY_NODE]:
        raise RuntimeError(f"{AI}: node {OR_NODE}'s ValueA is no longer fed by the boss-key query")
    e = ainb.Ainb(sarc_files(fs.read(EXP_SRC[0]["pack"]))[EXP_SRC[0]["file"]])
    n = e.nodes[EXP_SRC[1]]
    if n["name"] != "QueryGetNonStructGameDataBoolExp" or [
            (x["name"], x["node"]) for x in n["inputs"]["string"]] != [("GameDataFullName", -1)]:
        raise RuntimeError(f"{EXP_SRC[0]['file']}: node {EXP_SRC[1]} is no longer a constant BoolExp query")


def ainb_edits(fs):
    import drops as drop_tools  # tools/rando/drops.py, the sources for the instance-name check
    name_i, eq_i = drop_tools._name_sources(fs)
    _check_sources(fs)
    return [
        {"copy": {"from": drop_tools.GS_NAME_SRC, "nodes": [name_i], "label": "gn", "follow": False}},
        {"copy": {"from": drop_tools.GS_EQUAL_SRC, "nodes": [eq_i], "label": "ge", "follow": False}},
        {"set_input": {"node": f"ge:{eq_i}", "name": "StringB", "value": DOOR_NAME}},
        {"set_property": {"node": f"gn:{name_i}", "name": "OutputOnlyOnEnter", "value": True}},
        {"set_property": {"node": f"ge:{eq_i}", "name": "OutputOnlyOnEnter", "value": True}},
        {"feed": {"from": f"gn:{name_i}", "output": "InstanceName", "to": f"ge:{eq_i}", "input": "StringA"}},
        {"copy": {"from": EXP_SRC[0], "nodes": [EXP_SRC[1]], "label": "gx", "follow": False}},
        {"set_input": {"node": f"gx:{EXP_SRC[1]}", "name": "GameDataFullName", "value": EXP}},
        {"copy": {"from": AI_SRC, "nodes": [AND_NODE], "label": "ga", "follow": False}},
        {"feed": {"from": f"ge:{eq_i}", "output": "IsEqual", "to": f"ga:{AND_NODE}", "input": "ValueA"}},
        {"feed": {"from": f"gx:{EXP_SRC[1]}", "output": "Value", "to": f"ga:{AND_NODE}", "input": "ValueB"}},
        {"copy": {"from": AI_SRC, "nodes": [OR_NODE], "label": "go", "follow": False}},
        {"feed": {"from": KEY_NODE, "output": "Bool", "to": f"go:{OR_NODE}", "input": "ValueA"}},
        {"feed": {"from": f"ga:{AND_NODE}", "output": "Result", "to": f"go:{OR_NODE}", "input": "ValueB"}},
        {"feed": {"from": f"go:{OR_NODE}", "output": "Result", "to": OR_NODE, "input": "ValueA"}},
    ]


def world_plan(settings, world):
    """Plan sections for a condition mode, else {}."""
    settings = getattr(world, "settings", settings)  # OoTR forces 'triforce' on the world's copy (Triforce Hunt)
    if not condition(settings):
        return {}
    from romtools import Romfs
    import drops as drop_tools
    from parity import _story_conditions as C
    fs = Romfs(drop_tools.DEFAULT_ROMFS, os.path.join(HERE, "original"))
    req = requirement(settings)
    steps = C.expression(req)
    gamedata = {"add_boolexp": {EXP: steps}}
    if settings.shuffle_ganon_bosskey == "triforce":  # the pieces' saved count (parity/_gaps_triforce.py), added
        gamedata = {"add_ints": {C.TRIFORCE_COUNT: 0}, **gamedata}  # in this op, before the expression naming it
    return {
        "gamedata": gamedata,
        "placements": [{"file": DOOR_FILE, "hash": DOOR_HASH, "set": {"Name": DOOR_NAME},
                        "note": f"Ganon's boss key: {C.describe(req)}"}],
        "ainb": [{"pack": "*", "file": AI, "edits": ainb_edits(fs)}],
        "_gaps": {"ganon_bosskey": {"mode": settings.shuffle_ganon_bosskey, "condition": C.describe(req),
                                    "exp": EXP, "steps": steps, "door": [DOOR_FILE, DOOR_HASH], "name": DOOR_NAME}},
    }


def verify(patch, note, romfs):
    """Reads the built patch back: the lock's AI in every pack that has it, the door's Name and the expression."""
    from romtools import Romfs, sarc_files, byml_load, murmur3_32
    import ainb
    import packpaths
    bad = []
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    packs = packpaths.carriers(AI, romfs)
    for pack in packs:
        a = ainb.Ainb(sarc_files(fs.read(pack))[AI])
        src = [e for e in a.nodes[OR_NODE]["inputs"]["bool"] if e["name"] == "ValueA"]
        o = src[0]["node"] if src else -1
        if o < 0 or a.nodes[o]["name"] != "QueryLogicalDisjunction":
            bad.append(f"{pack} {AI}: node {OR_NODE} ValueA is not fed by the new disjunction")
            continue
        ins = {e["name"]: e["node"] for e in a.nodes[o]["inputs"]["bool"]}
        if ins.get("ValueA") != KEY_NODE:
            bad.append(f"{pack} {AI}: the disjunction lost the boss-key query")
        c = ins.get("ValueB", -1)
        if c < 0 or a.nodes[c]["name"] != "QueryLogicalConjunction":
            bad.append(f"{pack} {AI}: the disjunction's ValueB is not the name-and-condition conjunction")
            continue
        cin = {e["name"]: e["node"] for e in a.nodes[c]["inputs"]["bool"]}
        eq, x = cin.get("ValueA", -1), cin.get("ValueB", -1)
        if eq < 0 or a.nodes[eq]["name"] != "QueryStringIsEqual":
            bad.append(f"{pack} {AI}: no name compare in the conjunction")
        else:
            sb = [e for e in a.nodes[eq]["inputs"]["string"] if e["name"] == "StringB"]
            sa = [e for e in a.nodes[eq]["inputs"]["string"] if e["name"] == "StringA"]
            if not sb or sb[0]["value"] != note["name"] or not sa or sa[0]["node"] < 0 or \
                    a.nodes[sa[0]["node"]]["name"] != "QueryGetActorInstanceName":
                bad.append(f"{pack} {AI}: the name compare doesn't test the own instance Name == {note['name']}")
        if x < 0 or a.nodes[x]["name"] != "QueryGetNonStructGameDataBoolExp":
            bad.append(f"{pack} {AI}: no expression query in the conjunction")
        else:
            gn = [e for e in a.nodes[x]["inputs"]["string"] if e["name"] == "GameDataFullName"]
            if not gn or gn[0]["value"] != note["exp"]:
                bad.append(f"{pack} {AI}: the expression query reads {gn and gn[0]['value']!r}, not {note['exp']}")
    if not packs:
        bad.append(f"{AI}: in no pack")
    f, h = note["door"]
    actors = {str(a.get("Hash")): a for a in byml_load(fs.read(f))[0].get("Actors") or []}
    d = actors.get(h)
    if d is None or d.get("Gyaml") != DOOR_ACTOR or d.get("Name") != note["name"]:
        bad.append(f"{f} #{h}: not Ganon's boss lock named {note['name']} ({d and d.get('Gyaml')}, "
                   f"{d and d.get('Name')})")
    others = [a.get("Hash") for a in actors.values() if a.get("Name") == note["name"] and str(a.get("Hash")) != h]
    if others:
        bad.append(f"{f}: other placements named {note['name']}: {others}")
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    row = next((e for e in gd["Data"]["BoolExp"] if e["Hash"] == murmur3_32(note["exp"])), None)
    if row is None:
        bad.append(f"GameDataList: no expression {note['exp']}")
    else:
        want = [[x if not isinstance(x, str) else murmur3_32(x) for x in st] for st in note["steps"]]
        if [[int(v) for v in st] for st in row["Values"]] != [[int(v) for v in st] for st in want]:
            bad.append(f"GameDataList: {note['exp']} doesn't hold the planned condition")
    return bad
