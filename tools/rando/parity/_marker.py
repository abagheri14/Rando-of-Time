"""Unchecked pots and grass show it (appearance plugin, correct_potcrate_appearances).

Pots and grass have no look setting a placement can set. Their materials ignore
GameModelController_GeneralInstanceParam0..2 (what gives the crates and lift rocks their gold), there's one pot type
per level, and the textures are shared. They can change look at run time though,
with ExecuteSetModelExtraColor. That's the node the game uses for its blue "stunned" tint (Gossip Stones, Leever and
NPCs hit by a boomerang or a Deku Nut), with the presets DefaulBlue / DefaultRed, the only colours any vanilla use
passes. So a pot or grass placement holding a shuffled item gets the placement Name MARK_NAME (no vanilla pot or
grass placement has a Name: 564 pots, 292 grass), and the type's root AI tints itself blue while its own Name is
MARK_NAME (QueryGetActorInstanceName + QueryStringIsEqual, like the heart pieces' name checks).
A checked object doesn't come back, because the drops plugin makes its save flag permanent. The few spots that do
come back after their check (no flag, a reset group, an item whose second pickup changes nothing) get no marker, so
the blue shows exactly on unchecked ones (appearance.comes_back_after_check). Under the respawn model
(drops.CHECKED_ARRAY) a checked object is replaced by its unmarked vanilla twin, so every such spot is marked.
The Name checks run once (OutputOnlyOnEnter), so per frame only the selector and the tint are left.
Blue is the only colour on offer (the node's presets, and no vanilla use passes its own colour), so in
textures_content mode pots and grass can't show the category. The ones holding a category the setting colours
turn blue.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

MARK_NAME = "RandoUnchecked"
# object types -> their root AI (each pack's AIInfo RootAIRef). Obj_Pot_A_01.._08 -> Obj_Pot.root, grass A_01 ->
# Plant_Grass.root, and A_03 has its own. The grass and lift-rock packs also carry an unused Obj_Pot.root copy.
# My rule is that everything that has a check and normally looks normal gets marked, walls included. So every other
# item-holding type with a root AI takes the same marker (beehives, flying pots, stone crates, the Gerudo cow skulls
# and hanging signs, icicles, falling icicles, palm fruit, red ice, silver rocks, the bombable rocks, the Goron City
# wall crack, the Hyrule Field bushes).
MARK_AI = {"Obj_Pot_A_": "AI/Obj_Pot.root.ainb", "Obj_Plant_Grass_A_01": "AI/Plant_Grass.root.ainb",
           "Obj_Plant_Grass_A_03": "AI/Obj_Plant_Grass_A_03.root.ainb",
           "Obj_Kokiri_Beehive_A_01": "AI/Obj_Beehive.root.ainb",
           "Enemy_FlyingPot_": "AI/Enemy_FlyingPot.root.ainb",
           "Obj_BrokenBox_A_03": "AI/Obj_BrokenBox_A_03.root.ainb",
           "Obj_Gerudo_CowBoneDecoration_B_": "AI/Obj_Gerudo_CowBoneDecoration_A_01.root.ainb",
           "Obj_Gerudo_HangingSign_B_01": "AI/Obj_Gerudo_HangingSign_A_01.root.ainb",
           "Obj_BrokenIcePillar_A_": "AI/Obj_BrokenIcePillar_A_01.root.ainb",
           "Obj_FallingIcicle_A_": "AI/Obj_FallingIcicle_A_01.root.ainb",
           "Obj_Gerudo_PalmFruit_A_01": "AI/PalmFruit.root.ainb",
           "Obj_RedIce_A_": "AI/Obj_RedIce_A_01.root.ainb",
           "Obj_LiftRock_B_01": "AI/Obj_LiftRock_B_01.root.ainb",
           "Obj_BrokenRock_A_02": "AI/Obj_BrokenRock_A_02.root.ainb",
           "Obj_BrokenRock_A_01": "AI/RandoBoulder.root.ainb",
           "Obj_Goron_BrokenRock_A_01": "AI/RandoGoronRock.root.ainb",
           "Obj_Tree_A_0": "AI/Land_Tree_BeechMiddle_A_01.root.ainb",
           "Obj_Tree_Tutorial_A_01": "AI/Obj_Tree_Tutorial_A_01.root.ainb"}
# Types whose own tint can't be what the player sees. In game there was no blue on the Kokiri Forest tree or the
# Hyrule Field butterfly fairy, and pots are the one kind I've seen blue. The tint colours the actor's own model, and
# these two draw nothing the player sees:
#   - the Hyrule Field bushes have no model at all (ModelInfo ModelProjectName "", no ActorInfo model, a zero box, no
#     pre-actor render heap). The bush on screen isn't drawn by this actor.
#   - the butterfly fairy is a holder (ActorHolderRef: up to 5 Animal_Butterfly) whose utility AI creates the 1-4
#     butterflies on screen (ExecuteCreateAndPlacementButterflies, MinButterflies/MaxButterflies). Each one is a
#     separate Animal_Butterfly actor with no placement Name, so no marker of ours reaches them.
# They aren't marked by Name, and there's no AI edit, so no per-frame cost for a tint nobody sees. They take the
# other cues below instead (cue_for), and verify reports any Name-marked placement of a type that can't show the tint
# (tint_problem).
NO_TINT = {"Land_kokiri_Plant_A_02_DropFixed_03": "has no model of its own (ModelInfo ModelProjectName empty): the "
                                                  "bush on screen isn't this actor's",
           "Animal_ButterflyToFairy": "is a holder: the 1-4 butterflies on screen are Animal_Butterfly actors it "
                                      "creates (ActorHolderRef), not this actor's model"}
STUN_PARAM = "p_stun_ratio"  # every material the game's tint shows on carries it (pots, the Gossip Stone, NPCs)
# Objects that stay standing after their check. Their tint also waits on the check, so it goes the moment they're
# checked (the tint is an Execute node, and leaving it ends the tint, the same way the Gossip Stone's blue flash
# ends). Trees read the flag the drops plugin borrows for the spot, every frame. Its name is in the placement's
# DROP_FLAG_KEY, the tree gate's own read, and it's set when the item is taken. The Gerudo cow skulls read their own
# isDroped, which is set when they're hit and the item drops.
MARK_GATE = {"AI/Land_Tree_BeechMiddle_A_01.root.ainb": "flag", "AI/Obj_Tree_Tutorial_A_01.root.ainb": "flag",
             "AI/Obj_Gerudo_CowBoneDecoration_A_01.root.ainb": "dropped"}
BB_BOOL_SRC = ({"pack": "Pack/AI.Global.Product.111.pack.zs", "file": "AI/NpcCommon.action.Stop.module.ainb"},
               {"QueryBlackboardGetBool": 60})
DROPPED_KEY = "isDroped"
# Bomb boulders, the Goron City wall crack and the Hyrule Field bushes have no vanilla AI. When they hold an item the
# drops plugin copies the bronze boulder's root AI under a new name, so we patch that copy in the packs
# drops.new_ai_packs lists (see drops.NEW_AI_DROPPERS).
TINT_SRC = ({"pack": "Pack/Actor/Obj_GossipStone_A_01.pack.zs", "file": "AI/_LocalModule_f9e82ae9180e.module.ainb"},
            {"ExecuteSetModelExtraColor": 20})  # its blue one (DefaulBlue True)


def tint_problem(actor, files, fs):
    """Why a type's own tint can't be seen, or None. The reasons are NO_TINT, no model of its own (ModelInfo without a
    project or FmdbName, or no such model file), a material without the stun parameters, or a holder that creates the
    actors the player sees (ActorHolderRef with hold settings). `files` is the type's pack."""
    import drops as drop_tools
    from romtools import byml_load
    for prefix, why in NO_TINT.items():
        if actor.startswith(prefix):
            return why
    comps = {}
    for _, c in drop_tools._chain(files, actor):
        for k, v in c.items():
            comps.setdefault(k, v)
    holder = (comps.get("ActorHolderRef") or "").lstrip("?")
    if holder in files and (byml_load(files[holder])[0].get("ActorHoldSettings") or {}):
        held = sorted(byml_load(files[holder])[0]["ActorHoldSettings"])
        return f"is a holder: the actors on screen may be the {', '.join(held)} it creates, not its own model"
    mi = (comps.get("ModelInfoRef") or "").lstrip("?")
    info = byml_load(files[mi])[0] if mi in files else {}
    while info.get("$parent") and not (info.get("ModelProjectName") and info.get("FmdbName")):
        par = info["$parent"].replace("Work/", "").replace(".gyml", ".bgyml")
        info = dict(byml_load(files[par])[0], **{k: v for k, v in info.items() if v}) if par in files else {}
    project, fmdb = info.get("ModelProjectName"), info.get("FmdbName")
    if not project or not fmdb:
        return f"has no model of its own (ModelInfo {project!r} / {fmdb!r})"
    rel = f"Model/{project}.{fmdb}.bfres.zs"
    try:
        d = fs.read(rel)
    except FileNotFoundError:
        return f"names model {rel}, which the game hasn't"
    from parity import _appearance_bfres as ab
    for m in ab.materials(d):
        info = ab.params(fs, d, m["fmat"])
        if STUN_PARAM not in info:
            return f"its material {m['material']} ({rel}) has no {STUN_PARAM}: the tint has nothing to colour"
    return None


def ai_for(actor):
    """The root AI a marked placement of this type reads its Name in, or None (no marker for it)."""
    for prefix, ai in MARK_AI.items():
        if actor.startswith(prefix):
            return ai
    return None


def mark_op(file, hash_, name=MARK_NAME):
    return {"file": file, "hash": str(hash_), "set": {"Name": name}}


def ainb_ops(ai_files, plain=()):
    """Plan "ainb" ops. Each root AI in `ai_files` tints its actor blue while its Name is MARK_NAME. The gated AIs in
    `plain` (a probe build's) also tint ungated while the Name is PLAIN_NAME."""
    import drops as drop_tools
    from romtools import Romfs
    fs = Romfs(drop_tools.DEFAULT_ROMFS, os.path.join(HERE, "original"))
    name_i, eq_i = drop_tools._name_sources(fs)
    src = drop_tools._check_src(fs, *TINT_SRC, "the blue tint")
    tint = TINT_SRC[1]["ExecuteSetModelExtraColor"]
    if [e["value"] for e in src.nodes[tint]["inputs"]["bool"] if e["name"] == "DefaulBlue"] != [True]:
        raise drop_tools.DropPlanError(f"{TINT_SRC[0]['file']}: node {tint} is no longer the blue tint")
    own_src, own = drop_tools.LOOK_SRC["own"]
    bsel, nothing = own["BoolSelector"], own["OneshotDoNothing"]
    ops = []
    for ai in sorted(set(ai_files)):
        e = [
            {"copy": {"from": drop_tools.GS_NAME_SRC, "nodes": [name_i], "label": "mn", "follow": False}},
            {"copy": {"from": drop_tools.GS_EQUAL_SRC, "nodes": [eq_i], "label": "me", "follow": False}},
            {"set_input": {"node": f"me:{eq_i}", "name": "StringB", "value": MARK_NAME}},
            # the Name can't change while the object exists: both queries run once, not every frame
            {"set_property": {"node": f"mn:{name_i}", "name": "OutputOnlyOnEnter", "value": True}},
            {"set_property": {"node": f"me:{eq_i}", "name": "OutputOnlyOnEnter", "value": True}},
            {"feed": {"from": f"mn:{name_i}", "output": "InstanceName", "to": f"me:{eq_i}", "input": "StringA"}},
            {"copy": {"from": own_src, "nodes": [bsel], "label": "ms", "follow": False}},
            {"feed": {"from": f"me:{eq_i}", "output": "IsEqual", "to": f"ms:{bsel}", "input": "Input"}},
            {"copy": {"from": TINT_SRC[0], "nodes": [tint], "label": "mc", "follow": False}},
            {"copy": {"from": own_src, "nodes": [nothing], "label": "mx", "follow": False}},
            {"add_child": {"parent": f"ms:{bsel}", "child": f"mc:{tint}" if ai not in MARK_GATE else f"mg:{bsel}",
                           "name": "True"}},
            {"add_child": {"parent": f"ms:{bsel}", "child": f"mx:{nothing}", "name": "False"}},
            # Obj_Pot.root already starts at such a Simultaneous, the grass AIs start at a SplitTiming. The drops
            # plugin's pickup-save branch may wrap first (verify_pickup_save wants its drop right under Root).
            {"wrap": {"command": "Root", "if_needed": True}},
            {"add_child": {"parent": "@Root", "child": f"ms:{bsel}"}}]
        if ai in MARK_GATE:  # checked: the gate's True case does nothing, so the tint stops
            at = next(k for k, x in enumerate(e) if (x.get("copy") or {}).get("label") == "mx") + 1
            e[at:at] = [{"copy": {"from": own_src, "nodes": [bsel], "label": "mg", "follow": False}},
                     {"copy": {"from": own_src, "nodes": [nothing], "label": "my", "follow": False}},
                     {"add_child": {"parent": f"mg:{bsel}", "child": f"my:{nothing}", "name": "True"}},
                     {"add_child": {"parent": f"mg:{bsel}", "child": f"mc:{tint}", "name": "False"}}]
            if MARK_GATE[ai] == "flag":
                (s1, n1), (s2, n2) = drop_tools.GATE_SRC["getstr"], drop_tools.GATE_SRC["flag"]
                gi, qi = n1["QueryBlackboardGetString"], n2["QueryGetNonStructGameDataBool"]
                e += [{"copy": {"from": s1, "nodes": [gi], "label": "mf", "follow": False}},
                      {"set_property": {"node": f"mf:{gi}", "name": "BlackboardType", "value": 1}},
                      {"set_property": {"node": f"mf:{gi}", "name": "BlackboardKey", "value": drop_tools.DROP_FLAG_KEY}},
                      {"set_property": {"node": f"mf:{gi}", "name": "OutputOnlyOnEnter", "value": True}},
                      {"copy": {"from": s2, "nodes": [qi], "label": "mq", "follow": False}},
                      {"set_property": {"node": f"mq:{qi}", "name": "DispError", "value": False}},
                      {"set_property": {"node": f"mq:{qi}", "name": "OutputOnlyOnEnter", "value": False}},
                      {"feed": {"from": f"mf:{gi}", "output": "String", "to": f"mq:{qi}", "input": "GameDataFullName"}},
                      {"feed": {"from": f"mq:{qi}", "output": "Value", "to": f"mg:{bsel}", "input": "Input"}}]
            else:
                bi = BB_BOOL_SRC[1]["QueryBlackboardGetBool"]
                e += [{"copy": {"from": BB_BOOL_SRC[0], "nodes": [bi], "label": "md", "follow": False}},
                      {"set_property": {"node": f"md:{bi}", "name": "BlackboardType", "value": 0}},
                      {"set_property": {"node": f"md:{bi}", "name": "BlackboardKey", "value": DROPPED_KEY}},
                      {"feed": {"from": f"md:{bi}", "output": "Bool", "to": f"mg:{bsel}", "input": "Input"}}]
        if ai in MARK_GATE and ai in (plain or ()):  # a probe build: the pots' marker, ungated, for PLAIN_NAME
            e += plain_ops(ai)
        packs = "*"
        added = [a for a in drop_tools.NEW_AI_DROPPERS if MARK_AI.get(a) == ai]
        if added:  # an AI the drops plugin adds (not in the game's packs): the packs it puts it in
            packs = sorted({pk for a in added for pk in drop_tools.new_ai_packs(a)})
        ops.append({"pack": packs, "file": ai, "edits": e})
    return ops


def verify(patch, plan, romfs=None):
    """[problem] for every placement the plan names MARK_NAME, plus (n checked). For each one:
    - its type can show the tint (tint_problem: a model of its own, with the stun parameters, not a holder of the
      actors on screen)
    - its type's root AI, in the type's own pack, tints it blue while its Name is MARK_NAME (a QueryStringIsEqual on
      MARK_NAME feeding a BoolSelector whose True case is the blue ExecuteSetModelExtraColor)
    - its AIInfo is in its pack (a drops.NEW_AI_DROPPERS type's too)"""
    import drops as drop_tools
    import ainb
    from romtools import Romfs, sarc_files, byml_load
    romfs = romfs or drop_tools.DEFAULT_ROMFS
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    marked = [op for op in plan.get("placements", []) if (op.get("set") or {}).get("Name") in (MARK_NAME, PLAIN_NAME)]
    names = {}  # type -> the marker Names its placements carry
    types = {}
    levels = {}
    for op in marked:
        if op["file"] not in levels:
            levels[op["file"]] = {str(a.get("Hash")): a.get("Gyaml") for a in byml_load(fs.read(op["file"]))[0]
                                  .get("Actors") or []}
        g = levels[op["file"]].get(str(op["hash"]))
        if g is None:
            return [f"{op['file']} {op['hash']}: the marked placement isn't in the patched level"], 0
        types.setdefault(g, 0)
        types[g] += 1
        names.setdefault(g, set()).add(op["set"]["Name"])
    bad = []
    for actor in sorted(types):
        why = tint_problem(actor, sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs")), fs)
        if why:
            bad.append(f"{actor}: {types[actor]} placements marked, but the tint can't show: it {why}")
            continue
        ai = ai_for(actor)
        if ai is None:
            bad.append(f"{actor}: {types[actor]} placements marked, but the type has no marker AI")
            continue
        pk = f"Pack/Actor/{actor}.pack.zs"
        files = sarc_files(fs.read(pk))
        chain = drop_tools._chain(files, actor)
        ref = next((c["AIInfoRef"] for _, c in chain if c.get("AIInfoRef")), None)
        if not ref and any(c.get("BSARef") for _, c in chain) and ai in files:
            root = ai  # a brain/sense/action actor (the butterfly fairy): its utility root, as the drops plugin edits
        elif not ref or ref.lstrip("?") not in files:
            bad.append(f"{pk}: no AIInfo ({ref})")
            continue
        else:
            root = "AI/" + byml_load(files[ref.lstrip("?")])[0]["RootAIRef"].rsplit("/", 1)[-1] + "b"
        if root != ai or root not in files:
            bad.append(f"{pk}: its root AI is {root}, the marker edits {ai}")
            continue
        a = ainb.Ainb(files[root])

        def ins(i):
            return {e["name"]: e for t in ainb.PTYPES for e in a.nodes[i]["inputs"][t]}
        for name in sorted(names[actor]):
            if not _tints(a, root, name, ins):
                bad.append(f"{pk}: {root} doesn't tint a {name} placement blue")
    more, n_cues = verify_cues(patch, plan, romfs)
    return bad + more, sum(types.values()) + n_cues


def _tints(a, root, name, ins):
    """Whether AI `a` tints its actor blue while its Name is `name` (gated for MARK_NAME in a MARK_GATE AI)."""
    import ainb
    gated = root in MARK_GATE and name == MARK_NAME
    ok = False
    if True:  # (the marker's own check, for one Name)
        for i, n in enumerate(a.nodes):
            if n["name"] != "QueryStringIsEqual" or ins(i).get("StringB", {}).get("value") != name:
                continue
            for m in a.nodes:
                if ainb.NODE_TYPES.get(m["type"]) == "BoolSelector" and m["inputs"]["bool"] and \
                        m["inputs"]["bool"][0]["node"] == i:
                    t = next((pl["node"] for pl in m["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True"), -1)
                    if gated and t >= 0 and ainb.NODE_TYPES.get(a.nodes[t]["type"]) == "BoolSelector":
                        # gated: the check's state feeds the gate, whose False case tints and True case doesn't
                        g = a.nodes[t]
                        src = g["inputs"]["bool"][0]["node"] if g["inputs"]["bool"] else -1
                        kid = {pl["name"]: pl["node"] for pl in g["plugs"][ainb.PLUG_CHILD]}
                        if src < 0 or a.nodes[kid.get("True", 0)]["name"] == "ExecuteSetModelExtraColor":
                            continue
                        if MARK_GATE[root] == "flag":
                            fed = a.nodes[src]["name"] == "QueryGetNonStructGameDataBool" and \
                                a.nodes[ins(src)["GameDataFullName"]["node"]]["name"] == "QueryBlackboardGetString"
                        else:
                            fed = a.nodes[src]["name"] == "QueryBlackboardGetBool"
                        t = kid.get("False", -1) if fed else -1
                    elif gated:
                        continue
                    if t >= 0 and a.nodes[t]["name"] == "ExecuteSetModelExtraColor" and \
                            ins(t).get("DefaulBlue", {}).get("value") is True:
                        ok = True
    return ok


# The other cues
# I want a different cue for the kinds whose own model can't take the tint, so they get another one:
#   - butterfly fairies: a spawner of our own (TINT_TYPES). It's a copy of Animal_ButterflyToFairy whose holder
#     creates BLUE_BUTTERFLY, a copy of Animal_Butterfly whose action AI (its own copy of InsectFireFly.action.root)
#     tints it blue in every movement command. The Gerudo NPCs run the game's tint from an action module the same
#     way. The marked placement is that spawner, and its vanilla twin (the respawn model's) stays the game's.
#   - Hyrule Field bushes (drawn by the foliage system), trees and cows: an effect placed at the object (EFFECT_KINDS,
#     cows through cow_spots). It's a new placement of one of the game's effect-only actors (no AI, no gameplay,
#     CUE_EFFECTS), present while the object is unchecked (read when the area loads) and lifted CUE_LIFT.
# The sparkle candidates I tried first (A-C) didn't attach to the trees at all. They showed up all over the place,
# with haze and a random red effect, because they're the game's room-scale ambient emitters (A: lava erosion, sparks
# and thick smoke; B: a 4 x 1.5 m firefly volume; C: the fairy fountain's well). And the stun tint shows on no tree,
# gated or ungated, even though every tree material carries the stun parameters and the trunk's static options match
# the pot's. The tint just never takes on a tree. An Obj_Tree_* lacks the Chemical, AttentionSender, LocalDepthShadow
# and PerceptionEmitter components every vanilla tint user has, and has an ActiveCameraAlpha controller none of them
# has.
# So there's one cue for every kind the tint can't reach, and it needs nothing from the object's own AI: the game's
# blue point light, EftLoc_Graveyard_DanpeiGraveLight_00. It has one emitter set, Env_Dampe_DryIce_Grave_LGT_00, with
# one emitter "Light", colour (0.25, 0.39, 1.0), and the game places it once, over Dampe's grave. We add a new
# placement of it at the object, present exactly while the object is unchecked (read when the area loads) and lifted
# per kind (CUE_LIFT). It's an effect-only actor, so no AI, no physics and no gameplay.
CUE_EFFECTS = {"L": "EftLoc_Graveyard_DanpeiGraveLight_00"}
CUE_DEFAULT = "L"
CUE_LIFT = {"Land_kokiri_Plant_A_02_DropFixed_03": 0.5, "Obj_Tree_": 1.5, "Animal_Cow": 1.2}  # m above the origin
EFFECT_KINDS = ("Land_kokiri_Plant_A_02_DropFixed_03", "Obj_Tree_A_0", "Obj_Tree_Tutorial_A_01")
TINT_TYPES = {"Animal_ButterflyToFairy": "Rando_BtflySpawn"}
BLUE_BUTTERFLY = "Rando_BtflyBlue"
BLUE_AI = "AI/RandoBtflyBlue.action.root.ainb"
FIREFLY_AI = ({"pack": "Pack/AI.Global.Product.111.pack.zs"}, "AI/InsectFireFly.action.root.ainb")
BLUE_COMMANDS = ("Wait", "Fly", "Land", "Flee", "Appear", "FollowMove")  # the butterfly's movement commands
PROBE = "marker_cues"
PLAIN_NAME = "RandoUncheckedPlain"
PROBES = {}  # (the earlier tree/bush probes, no longer used)
# Cows. Cows we haven't checked should have their own cue, so every cow holding an item gets the same light, present
# while its give flag (data/rando/songs_trade_flags.json) is unset. The Lon Lon Ranch stable pair gives its two items
# in order from either cow, so both show the light until the pair's last flag is set. A cow with a Presence of its
# own (Link's house: MiniGame_HorseRace_IsNewRecord) takes a new expression flag, its own condition AND NOT the give
# flag, so the light never shows before the cow does.
COW_CUE_EXP = "RandoCue_Cow_{}"
# Tree lights. The blue hue does show on the trees, but it's a little too subtle, and it came back after leaving
# Kokiri Forest even with both checks done.
#   - A tree holding junk with its own pickup (the drops plugin's FLAGLESS OWN) records its check in the drops
#     plugin's CHECKED_ARRAY. The pickup sets RandoChecked[its DROP_CHK_KEY bit] when taken, and the tree's
#     DROP_FLAG_KEY names the array for its gate. Its light used that array as its Presence flag, but a Presence reads
#     a Bool or an expression (BoolExp), never an array, so the light never went away. It now reads an expression of
#     ours, CHK_CUE_EXP: "not RandoChecked[bit]" (unchecked_presence). Those rows go in last (appearance.finish_plan)
#     because they read the drops plugin's array, which is added after our plugin's rows.
#   - TODO: a stronger light is parked, my call ("the visual cues can be left for later"). CUE_COPIES lights at each
#     object, at the same spot, would do it. Point lights add, so 2 gives twice the light and the look is unchanged
#     (built and checked with 2, then set back to 1). Raising the light's own colour (its emitter's HDR colour, the
#     one vec3 of the effect file) would also brighten Dampe's grave in the adult Graveyard (the effect's one vanilla
#     placement), so no.
CUE_COPIES = 1
CHK_CUE_EXP = "RandoCue_Chk_{:04d}"


def lift_for(actor):
    return next((v for k, v in CUE_LIFT.items() if (actor or "").startswith(k)), 0.5)


def cow_spots(romfs=None):
    """[(OoTR locations of the group, give flag of its last item, [(file, hash, pos, own presence or None)])] for every
    cow the songs plugin gives items from (data/rando/songs_trade_cows.json: the generic groups, KF, GV, GF)."""
    import json
    import glob
    import drops as drop_tools
    from romtools import Romfs, byml_load
    romfs = romfs or drop_tools.DEFAULT_ROMFS
    data = os.path.join(HERE, "data", "rando")
    cows = json.load(open(os.path.join(data, "songs_trade_cows.json"), encoding="utf-8"))
    flags = json.load(open(os.path.join(data, "songs_trade_flags.json"), encoding="utf-8"))["assigned"]
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    levels = {}

    def actors(f):
        if f not in levels:
            levels[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f), allow_big=True)[0].get("Actors") or []}
        return levels[f]
    out = []
    for g in cows["generic"]:
        spots = []
        for p in g["placements"]:
            a = actors(p["file"]).get(str(p["cow"]))
            if a is not None:
                spots.append((p["file"], str(p["cow"]), [float(v) for v in a["Translate"]], a.get("Presence")))
        out.append((list(g["ootr"]), flags[g["ootr"][-1]], spots))
    for key, gyaml, area in (("kf", "Animal_Cow_LinkHouse", "KokiriForest"),
                             ("gv", "Animal_Cow_GerudoValley", "GerudoValley"),
                             ("gf", "Animal_Cow_GerudoFortress", "GerudoFortress")):  # (the remake-only GF Cow)
        if key not in cows:
            continue
        name, spots = cows[key], []
        for path in sorted(glob.glob(os.path.join(romfs, "Banc", "*", "*.bcett.byml.zs"))):
            rel = os.path.relpath(path, romfs).replace(os.sep, "/")
            if rel.split("/")[1] != area:
                continue
            for h, a in actors(rel).items():
                if a.get("Gyaml") == gyaml:
                    spots.append((rel, h, [float(v) for v in a["Translate"]], a.get("Presence")))
        out.append(([name], flags[name], spots))
    return out


def cow_presence(flag, own, index):
    """(Presence for a cow's light, {new expression flag: steps} or {}). The light shows while it's unchecked (flag
    unset) and the cow is there."""
    if not own:
        return {"FlagName": flag, "IsCheckLazy": False, "IsNegation": True}, {}
    name = COW_CUE_EXP.format(index)
    steps = [[0, own["FlagName"]]] + ([[5]] if own.get("IsNegation") else []) + [[0, flag], [5], [3]]
    return {"FlagName": name, "IsCheckLazy": False, "IsNegation": False}, {name: steps}


def probing():
    try:
        from parity import _test_start as ts
    except ImportError:
        return False
    return ts.probe(PROBE)


def cue_for(actor, key, probe=None):
    """How placement `key` of type `actor` shows that it holds an item. ("name", Name) is the tint on its own model,
    then there's ("effect", effect actor), ("type", our spawner type), or None when this type has no cue."""
    probe = probing() if probe is None else probe
    if probe and key in PROBES:
        v = PROBES[key]
        if v == "gated":
            return ("name", MARK_NAME) if ai_for(actor) else None
        if v == "plain":
            return ("name", PLAIN_NAME) if ai_for(actor) in MARK_GATE else None
        return "effect", CUE_EFFECTS[v]
    if actor in TINT_TYPES:
        return "type", TINT_TYPES[actor]
    if actor.startswith(EFFECT_KINDS):
        return "effect", CUE_EFFECTS[CUE_DEFAULT]
    return ("name", MARK_NAME) if ai_for(actor) else None


def cue_hash(file, hash_, k=0):
    """The hash of the cue's light number `k` at `hash_`. It's never a vanilla hash of the file, since verify reads it
    back. Light 0 keeps the hash the single light always had."""
    h = int(hash_)
    for _ in range(k + 1):
        h = (h * 0x9E3779B97F4A7C15 + 0x52616E646F) % (1 << 63)
    return str(h)


def effect_op(file, hash_, pos, presence, effect, lift=0.5, k=0):
    """Light `k` of the cue. It's a new placement of effect-only actor `effect` at the object, made as a twin of the
    object the way the drops plugin makes its respawn twins. It's lifted `lift` (lift_for), present while `presence`
    holds (the object's unchecked condition), in no group, and takes nothing from the object but its place."""
    return {"file": file, "hash": str(hash_), "twin": cue_hash(file, hash_, k), "join_groups": False,
            "set": {"Gyaml": effect, "Translate": [pos[0], pos[1] + lift, pos[2]], "Rotate": [0.0, 0.0, 0.0],
                    "Presence": dict(presence)},
            "remove": ["Dynamic", "Phive", "Links", "Name", "Scale"]}


def effect_ops(file, hash_, pos, presence, effect, lift=0.5):
    """The cue: CUE_COPIES lights (effect_op) at one spot."""
    return [effect_op(file, hash_, pos, presence, effect, lift, k) for k in range(CUE_COPIES)]


def unchecked_presence(sets):
    """(Presence, {new expression: steps}) of the object's unchecked condition, from the drops plugin's edits of it
    (`sets`), or (None, {}).
    That's its own Presence if it has one (the respawn model's, or a flagless spot's negated check). Otherwise it's
    what its tree gate reads (DROP_FLAG_KEY): either a borrowed flag, shown while unset, or the drops plugin's
    CHECKED_ARRAY (FLAGLESS OWN), shown while the bit its pickup sets (DROP_CHK_KEY) is unset. A Presence can't name an
    array, so an expression of ours, CHK_CUE_EXP, reads the bit."""
    import drops as drop_tools
    if isinstance(sets.get("Presence"), dict):
        return sets["Presence"], {}
    flag = sets.get(f"Dynamic.{drop_tools.DROP_FLAG_KEY}")
    if flag == drop_tools.CHECKED_ARRAY:
        bit = sets.get(f"Dynamic.{drop_tools.DROP_CHK_KEY}")
        if isinstance(bit, bool) or not isinstance(bit, int) or bit < 1:
            return None, {}
        name = CHK_CUE_EXP.format(bit)
        return ({"FlagName": name, "IsCheckLazy": False, "IsNegation": True},
                {name: [[8, drop_tools.CHECKED_ARRAY, bit]]})
    if flag:
        return {"FlagName": flag, "IsCheckLazy": False, "IsNegation": True}, {}
    return None, {}


def butterfly_ops():
    """{"new_files", "packs", "ainb", "byml"}: BLUE_BUTTERFLY and the spawner type (TINT_TYPES)."""
    spawn, src_spawn = TINT_TYPES["Animal_ButterflyToFairy"], "Animal_ButterflyToFairy"
    sp, bp = f"Pack/Actor/{spawn}.pack.zs", f"Pack/Actor/{BLUE_BUTTERFLY}.pack.zs"
    holder = "Component/ActorHolderParam/{}.game__component__ActorHolderParam.bgyml"
    bsa = "Component/BSAParam/{}.game__component__BSAParam.bgyml"
    param = "Actor/{}.engine__actor__ActorParam.bgyml"
    note = "butterfly fairy cue: tinted butterflies (parity/_marker.py)"
    out = {"new_files": [{"to": sp, "from": f"Pack/Actor/{src_spawn}.pack.zs", "note": note},
                         {"to": bp, "from": "Pack/Actor/Animal_Butterfly.pack.zs", "note": note}],
           "packs": [
               {"pack": sp, "file": param.format(spawn), "new_from": param.format(src_spawn),
                "set": {"Components.ActorHolderRef": "?" + holder.format(spawn)}},
               {"pack": sp, "file": holder.format(spawn), "new_from": holder.format(src_spawn),
                "set": {"ActorHoldSettings.Animal_Butterfly.Actor":
                        f"Work/Actor/{BLUE_BUTTERFLY}.engine__actor__ActorParam.gyml"}},
               {"pack": bp, "file": param.format(BLUE_BUTTERFLY), "new_from": param.format("Animal_Butterfly"),
                "set": {"Components.BSARef": "?" + bsa.format(BLUE_BUTTERFLY)}},
               {"pack": bp, "file": bsa.format(BLUE_BUTTERFLY), "new_from": bsa.format("Animal_Butterfly"),
                "set": {"ActionSlotMainAin": "Work/AI/Root/" + BLUE_AI[3:-1]}},
               {"pack": bp, "file": BLUE_AI, "from_pack": FIREFLY_AI[0]["pack"], "new_from": FIREFLY_AI[1]}],
           "byml": [{"file": "RSDB/ActorInfo.Product.111.rstbl.byml.zs",
                     "add_row": {"copy_of": "Animal_Butterfly", "set": {"__RowId": BLUE_BUTTERFLY}}, "note": note},
                    {"file": "RSDB/ActorInfo.Product.111.rstbl.byml.zs",
                     "add_row": {"copy_of": src_spawn, "set": {"__RowId": spawn}}, "note": note},
                    {"file": "RSDB/GameActorInfo.Product.111.rstbl.byml.zs",
                     "add_row": {"copy_of": "Animal_Butterfly", "set": {"__RowId": BLUE_BUTTERFLY}}},
                    {"file": "RSDB/GameActorInfo.Product.111.rstbl.byml.zs",
                     "add_row": {"copy_of": src_spawn, "set": {"__RowId": spawn}}}]}
    tint = TINT_SRC[1]["ExecuteSetModelExtraColor"]
    e = [{"copy": {"from": TINT_SRC[0], "nodes": [tint], "label": "bc", "follow": False}}]
    for c in BLUE_COMMANDS:
        e += [{"wrap": {"command": c, "if_needed": True}}, {"add_child": {"parent": f"@{c}", "child": f"bc:{tint}"}}]
    out["ainb"] = [{"pack": bp, "file": BLUE_AI, "edits": e}]
    return out


def plain_ops(ai):
    """Edits of tree AI `ai` (a probe): a second branch tinting it, ungated, while its Name is PLAIN_NAME."""
    import drops as drop_tools
    from romtools import Romfs
    fs = Romfs(drop_tools.DEFAULT_ROMFS, os.path.join(HERE, "original"))
    name_i, eq_i = drop_tools._name_sources(fs)
    own_src, own = drop_tools.LOOK_SRC["own"]
    bsel, nothing = own["BoolSelector"], own["OneshotDoNothing"]
    tint = TINT_SRC[1]["ExecuteSetModelExtraColor"]
    return [{"copy": {"from": drop_tools.GS_NAME_SRC, "nodes": [name_i], "label": "pn", "follow": False}},
            {"copy": {"from": drop_tools.GS_EQUAL_SRC, "nodes": [eq_i], "label": "pe", "follow": False}},
            {"set_input": {"node": f"pe:{eq_i}", "name": "StringB", "value": PLAIN_NAME}},
            {"set_property": {"node": f"pn:{name_i}", "name": "OutputOnlyOnEnter", "value": True}},
            {"set_property": {"node": f"pe:{eq_i}", "name": "OutputOnlyOnEnter", "value": True}},
            {"feed": {"from": f"pn:{name_i}", "output": "InstanceName", "to": f"pe:{eq_i}", "input": "StringA"}},
            {"copy": {"from": own_src, "nodes": [bsel], "label": "ps", "follow": False}},
            {"feed": {"from": f"pe:{eq_i}", "output": "IsEqual", "to": f"ps:{bsel}", "input": "Input"}},
            {"copy": {"from": TINT_SRC[0], "nodes": [tint], "label": "pc", "follow": False}},
            {"copy": {"from": own_src, "nodes": [nothing], "label": "px", "follow": False}},
            {"add_child": {"parent": f"ps:{bsel}", "child": f"pc:{tint}", "name": "True"}},
            {"add_child": {"parent": f"ps:{bsel}", "child": f"px:{nothing}", "name": "False"}},
            {"add_child": {"parent": "@Root", "child": f"ps:{bsel}"}}]


def in_plan(plan):
    """True if the plan carries any unchecked marker or cue (in_game_check runs verify then)."""
    effects = set(CUE_EFFECTS.values()) | set(TINT_TYPES.values())
    return bool(plan.get("_marker_cows")) or any(
        (op.get("set") or {}).get("Name") in (MARK_NAME, PLAIN_NAME) or (op.get("set") or {}).get("Gyaml") in effects
        for op in plan.get("placements", []))


def _gamedata_index(fs):
    """{name hash: (table, row)} of the GameDataList `fs` serves (every table's rows)."""
    from romtools import byml_load
    raw = fs.read("GameData/GameDataList.Product.110.byml.zs")
    try:
        raw = fs.zs.decompress(raw)
    except Exception:  # noqa: BLE001 - stored uncompressed
        pass
    out = {}
    for t, rows in byml_load(raw, allow_big=True)[0]["Data"].items():
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and "Hash" in r:
                out.setdefault(int(r["Hash"]), (t, r))
    return out


STEP_READS = {0: "Bool", 8: "BoolArray", 10: "BoolExp"}  # an expression step's opcode -> the row kind it reads


def _light_problem(pres, check, own, gd):
    """Why Presence `pres` doesn't show a light exactly while its object is unchecked, or None.
    `check` is the expression step that reads the object's check ([0, flag hash] or [8, RandoChecked hash, bit]).
    `own` is the steps of a condition the light also waits for (a cow's own Presence), or None. `gd` is
    _gamedata_index of the patched game. Shown while unchecked means "not <check>" (negated), or an expression ending
    "AND NOT <check>" (after `own`, if any)."""
    from romtools import murmur3_32
    if not isinstance(pres, dict) or not pres.get("FlagName"):
        return "it has no Presence, so it never goes"
    name = pres["FlagName"]
    t, row = gd.get(murmur3_32(name), (None, None))
    if t not in ("Bool", "BoolExp"):  # a tree's light once named the RandoChecked array itself
        return (f"its Presence names {name}, " + (f"a {t} row" if t else "no row") + " of the GameDataList: a "
                f"Presence reads a Bool or an expression, so the game reads no such flag and the light never goes")
    steps = [[int(x) for x in st] for st in row["Values"]] if t == "BoolExp" else [[0, murmur3_32(name)]]
    for st in steps:
        kind = STEP_READS.get(st[0])
        if kind and gd.get(st[1], (None,))[0] != kind:
            return f"its expression {name} reads {st[1]} as a {kind}, but that row is {gd.get(st[1], (None,))[0]}"
    neg = bool(pres.get("IsNegation"))
    if own is None and neg and steps == [check]:
        return None
    if not neg and len(steps) > 3 and steps[-3:] == [check, [5], [3]] and (own is None or steps[:-3] == own):
        return None
    return (f"its Presence ({'not ' if neg else ''}{name}: {steps}) isn't 'unchecked' (step {check} unset"
            + (f", after {own}" if own else "") + ")")


def verify_cues(patch, plan, romfs=None):
    """[problem] for the other cues (n read back):
    - every light the plan adds (a CUE_EFFECTS placement) is in its patched level as that effect actor, at its object
      (within 1 m across, 0-2.5 m above), with nothing of the object's (parameters, links), and its object holds an
      item
    - its Presence names a Bool or an expression of the patched GameDataList and shows the light exactly while the
      object is unchecked (_light_problem). That's read from what records the check in the patched files, not from
      the planner's own derivation. An object naming a RandoChecked bit (DROP_CHK_KEY, which its pickup sets when
      taken; FLAGLESS OWN, the respawn model) -> that bit. A tree naming a borrowed flag (DROP_FLAG_KEY) or a spot of
      the plan's "_drops_flag_spots" -> that flag. A cow -> its group's give flag (data/rando/songs_trade_flags.json,
      cow_spots), after its own Presence if it has one.
    - each cued object has CUE_COPIES lights, and so does every object of a cue kind holding an item with an
      unchecked condition, and every cow the plan cues
    - every placement of a TINT_TYPES spawner is that type in the level, and the spawner's holder creates
      BLUE_BUTTERFLY, whose action AI tints it blue in every BLUE_COMMANDS command (and the type's rows exist)"""
    import math
    import ainb
    import drops as drop_tools
    from romtools import Romfs, sarc_files, byml_load, murmur3_32
    romfs = romfs or drop_tools.DEFAULT_ROMFS
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad, n = [], 0
    sets = {}
    for op in plan.get("placements", []):
        if "twin" not in op and "set" in op:
            sets.setdefault((op["file"], str(op["hash"])), {}).update(op["set"])
    levels = {}

    def level(f):
        if f not in levels:
            levels[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f), allow_big=True)[0].get("Actors") or []}
        return levels[f]
    effects = set(CUE_EFFECTS.values())
    cow_cues = {tuple(k.split("#")): v for k, v in (plan.get("_marker_cows") or {}).items()}
    lit = [op for op in plan.get("placements", []) if op.get("twin") is not None
           and (op.get("set") or {}).get("Gyaml") in effects]
    gd = _gamedata_index(fs) if lit else {}
    borrowed = {}  # (file, hash) -> its spot's borrowed flag (the carrier's get scene sets it)
    if lit and plan.get("_drops_flag_spots"):
        m = drop_tools._map()
        for name, flag in plan["_drops_flag_spots"].items():
            for p in (drop_tools.lookup(name, m) or {}).get("placements", []):
                borrowed[(p["file"], str(p["hash"]))] = flag
    cows = {}  # (file, hash) -> (its give flag, the steps of its own Presence or None)
    if lit and cow_cues:
        for _, flag, spots in cow_spots(romfs):
            for f, h, _, own in spots:
                cows[(f, str(h))] = (flag, None if not own else [[0, murmur3_32(own["FlagName"])]]
                                     + ([[5]] if own.get("IsNegation") else []))

    def check_of(f, h, o):
        """(the expression step reading object (f, h)'s check, its name) from the patched object, or (None, None)."""
        dyn = o.get("Dynamic") or {}
        bit = dyn.get(drop_tools.DROP_CHK_KEY)
        if isinstance(bit, int) and not isinstance(bit, bool) and bit > 0:
            return [8, murmur3_32(drop_tools.CHECKED_ARRAY), bit], f"{drop_tools.CHECKED_ARRAY}[{bit}]"
        flag = dyn.get(drop_tools.DROP_FLAG_KEY)
        flag = flag if flag and flag != drop_tools.CHECKED_ARRAY else borrowed.get((f, h))
        return ([0, murmur3_32(flag)], flag) if flag else (None, None)
    lights = {}  # (file, object hash) -> its lights' hashes
    for op in lit:
        n += 1
        f, h, src = op["file"], str(op["twin"]), str(op["hash"])
        lights.setdefault((f, src), []).append(h)
        a, o = level(f).get(h), level(f).get(src)
        own = sets.get((f, src), {})
        if a is None or o is None:
            bad.append(f"{f}: cue {h} or its object {src} isn't in the patched level")
            continue
        if a.get("Gyaml") != op["set"]["Gyaml"] or "Dynamic" in a or "Links" in a:
            bad.append(f"{f}: cue {h} is {a.get('Gyaml')} with the object's parameters or links")
        at, ot = a.get("Translate") or [0, 0, 0], o.get("Translate") or [0, 0, 0]
        if math.dist(at[::2], ot[::2]) > 1.0 or not 0.0 <= at[1] - ot[1] <= 2.5:
            bad.append(f"{f}: cue {h} isn't at its object {src}")
        if (f, src) in cow_cues:  # a cow: present while its item is unchecked (and the cow there)
            if (f, src) not in cows:
                bad.append(f"{f}: cow {src} isn't a cow the songs plugin gives items from (cow_spots)")
                continue
            flag, own_steps = cows[(f, src)]
            why = _light_problem(a.get("Presence"), [0, murmur3_32(flag)], own_steps, gd)
            if why:
                bad.append(f"{f}: cow {src}'s light {h} (its give flag {flag}): {why}")
            continue
        if not own.get("Dynamic.Drop__DropActor"):
            bad.append(f"{f}: cue {h}: its object {src} holds no item")
            continue
        check, what = check_of(f, src, o)
        if check is None:
            bad.append(f"{f}: cue {h}: nothing in the patched level records its object {src}'s check (no "
                       f"{drop_tools.DROP_CHK_KEY} bit, no borrowed flag): the light can't know it")
            continue
        why = _light_problem(a.get("Presence"), check, None, gd)
        if why:
            bad.append(f"{f}: light {h} at {o.get('Gyaml')} {src} (checked by {what}): {why}")
    for (f, src), hs in sorted(lights.items()):  # CUE_COPIES lights at each object
        if len(hs) != CUE_COPIES:
            bad.append(f"{f}: {src} has {len(hs)} lights, not {CUE_COPIES}")
    # every object of a cue kind holding an item, with an unchecked condition, has its cue
    for (f, h), s in sorted(sets.items()):
        if not s.get("Dynamic.Drop__DropActor") or unchecked_presence(s)[0] is None:
            continue
        g = level(f).get(h, {}).get("Gyaml", "")
        if g.startswith(EFFECT_KINDS) and (f, h) not in lights:
            bad.append(f"{f}: {h} ({g}) holds an item and shows no cue (its effect)")
    for (f, h) in sorted(cow_cues):  # every cow holding an item has its light
        n += 1
        if (f, h) not in lights:
            bad.append(f"{f}: cow {h} holds an item and shows no cue (its light)")
    looks = ((plan.get("_notes_appearance") or {}).get("potcrate") or {}).get("mode", "off") != "off"
    if looks and plan.get("_songs_cows") and not cow_cues:  # the songs plugin gives items from cows
        bad.append("the cows hold items and no cow shows a cue (appearance cow_plan)")
    for (f, h), s in sets.items():
        if s.get("Gyaml") not in TINT_TYPES.values():
            continue
        n += 1
        if level(f).get(h, {}).get("Gyaml") != s["Gyaml"]:
            bad.append(f"{f}: {h} isn't the {s['Gyaml']} spawner in the patched level")
    if any(s.get("Gyaml") in TINT_TYPES.values() for s in sets.values()):
        spawn = TINT_TYPES["Animal_ButterflyToFairy"]
        try:
            sf = sarc_files(fs.read(f"Pack/Actor/{spawn}.pack.zs"))
            bf = sarc_files(fs.read(f"Pack/Actor/{BLUE_BUTTERFLY}.pack.zs"))
        except FileNotFoundError as e:
            return bad + [f"the butterfly cue's packs: {e}"], n
        hold = byml_load(sf[f"Component/ActorHolderParam/{spawn}.game__component__ActorHolderParam.bgyml"])[0]
        made = [v.get("Actor") for v in (hold.get("ActorHoldSettings") or {}).values()]
        if made != [f"Work/Actor/{BLUE_BUTTERFLY}.engine__actor__ActorParam.gyml"]:
            bad.append(f"{spawn}: its holder creates {made}, not {BLUE_BUTTERFLY}")
        p = byml_load(sf[f"Actor/{spawn}.engine__actor__ActorParam.bgyml"])[0]
        if not str((p.get("Components") or {}).get("ActorHolderRef", "")).endswith(f"{spawn}.game__component__"
                                                                                    f"ActorHolderParam.bgyml"):
            bad.append(f"{spawn}: its ActorParam doesn't use its own holder")
        b = byml_load(bf[f"Component/BSAParam/{BLUE_BUTTERFLY}.game__component__BSAParam.bgyml"])[0]
        bp = byml_load(bf[f"Actor/{BLUE_BUTTERFLY}.engine__actor__ActorParam.bgyml"])[0]
        if b.get("ActionSlotMainAin") != "Work/AI/Root/" + BLUE_AI[3:-1] or \
                not str((bp.get("Components") or {}).get("BSARef", "")).endswith(f"{BLUE_BUTTERFLY}.game__component__"
                                                                                 f"BSAParam.bgyml"):
            bad.append(f"{BLUE_BUTTERFLY}: its action AI isn't {BLUE_AI}")
        a = ainb.Ainb(bf[BLUE_AI])
        for c in BLUE_COMMANDS:
            cmd = next((x for x in a.commands if x["name"] == c), None)
            kids = [pl["node"] for pl in a.nodes[cmd["main"]]["plugs"][ainb.PLUG_CHILD]] if cmd else []
            if not any(a.nodes[k]["name"] == "ExecuteSetModelExtraColor" and any(
                    e["name"] == "DefaulBlue" and e["value"] is True for e in a.nodes[k]["inputs"]["bool"])
                    for k in kids):
                bad.append(f"{BLUE_AI}: command {c} doesn't tint the butterfly blue")
        rows = {r["__RowId"] for r in byml_load(fs.read("RSDB/ActorInfo.Product.111.rstbl.byml.zs"),
                                                allow_big=True)[0]}
        for t in (spawn, BLUE_BUTTERFLY):
            if t not in rows:
                bad.append(f"{t}: no ActorInfo row")
    return bad, n
