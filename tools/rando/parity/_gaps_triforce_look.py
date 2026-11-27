"""Triforce Hunt's piece look (parity/_gaps_triforce.py). A Triforce Piece shows one golden triangle of the game's 3D
Triforce. The model is parity/_gaps_triforce_model.py.

The display actor
The get scene shows an item by creating a display-only actor by name
(Player_Event.EventCreateShowItemFromActorFileName), so the piece needs an actor whose model is the piece. That's
ACTOR, a new actor type: a new pack plus new rows in RSDB/ActorInfo and GameActorInfo, and both tables grow and get
re-sorted. New actor types work on Longshot (seen in game).
  - The name. The create step copies it into a 32-byte string, so 31 characters at most, and the show item that
    follows reads whatever was created (the Player event AI's OneShotShowItemInvalidateShadow reads actor+0x270 with
    no null check). A longer name creates nothing and the hold-up crashes. The
    first display I tried, the repurposed archery target Obj_Gerudo_HorsebackArcheryTarget_A_02 (38 characters),
    crashed every piece pickup in game that way. ACTOR has 19 (MAX_NAME 25, OotrR's limit).
  - Its pack is a copy of the Light Medallion display's (Item_Medal_Light: Item_EventObject_Base family, its effect
    user, name and pouch component) with the piece's ModelInfo (a copy of the Temple of Time relief's, FmdbName set
    to the piece model's), the hold-up animation files below, and an ActorParam of its own. That ActorParam is a
    child of Item_Medal_Light's with its own ModelInfoRef and the hold-up animation set.
  - The hold-up animation (NX2-ZOOTR found this one). The get scene's Item_Position plays
    Rotate_GetDemo on the shown actor (EventIgnitionShowItem IsAsPlay), and if the actor's AS lacks that command it
    never ends and the game freezes. The medallions' AS (AS/DemoDummy) has none. So the display takes the set every
    holdable item has (Item_Token_Gold, Item_Dungeon_SmallKey and so on): ASRef AS/Item_Common.root.asb
    (Rotate_GetDemo turns the bone Root, the piece model's only bone), ASInfoRef Item_GetDemo, AnimationRef
    ANIM_PARAM (Item_Common_Animation and the gold token's own project, whose Pose_Common is the identity and whose
    Pose_GetDemo is a 0.85 scale), the files byte-copied from Item_Token_Gold's pack, and the ActorInfo row's
    AnimationResources.
  - Its ActorInfo row is a copy of Item_Medal_Light's (radii, effect user) with the piece's model and bounds, the
    animation resources, and the larger heap sizes of the medallion and the token (OotrR: max of template and
    lender). Its GameActorInfo row is a copy of Item_Medal_Light's (empty).

Where the piece shows (dungeons plugin)
The hold-up (Rando_DI_Triforce: chests, scene locations, heart and freestanding spots through the get-scene hook)
creates ACTOR where it created the medallion. The steps that look the item up by name (locator and pose from its
pouch get type "Large", the fanfare, the get-item glow) still name Item_Medal_Light, so the hold-up is the one the
medallion had. A vanilla flow shows a display with no pouch row the same way (MiniGame_Fishing_Sub:
Item_Hat_FishingPondOwner). A big chest shows it with its own show entry (TRIFORCE_SHOW_ENTRY, the shared
Rando_DI_Show with this create step). On the ground (drops plugin, remake_item_looks "item"), heart and freestanding
spots holding a piece show it (drops.item_display / look_offsets). Resident get scenes (in the air or water) still
show no model. Pieces don't go in Treasure Chest Game rooms."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

from parity import _gaps_triforce_model as model  # noqa: E402

ACTOR = "Rando_Show_Triforce"  # a new actor type, in the Rando_Show_* family the hold-up scenes use
MAX_NAME = 25  # longer display names aren't created (the create step keeps 31 characters, and OotrR saw 25+ crash)
SRC_ACTOR = "Item_Medal_Light"  # the display it copies (only the model differs)
PACK = f"Pack/Actor/{ACTOR}.pack.zs"
SRC_PACK = f"Pack/Actor/{SRC_ACTOR}.pack.zs"
RELIEF_PACK = "Pack/Actor/Obj_TimeTemple_TriforceRelief_A_01.pack.zs"
RELIEF_MODELINFO = f"Component/ModelInfo/{model.SRC_FMDB}.engine__component__ModelInfo.bgyml"
MODELINFO = f"Component/ModelInfo/{model.FMDB}.engine__component__ModelInfo.bgyml"
PARAM = f"Actor/{ACTOR}.engine__actor__ActorParam.bgyml"
SRC_PARAM = f"Actor/{SRC_ACTOR}.engine__actor__ActorParam.bgyml"
PARENT = f"Work/Actor/{SRC_ACTOR}.engine__actor__ActorParam.gyml"
# the hold-up animation set, from a holdable item with a flat model and an identity Pose_Common
ANIM_ACTOR = "Item_Token_Gold"
ANIM_PACK = f"Pack/Actor/{ANIM_ACTOR}.pack.zs"
AS_REF = "?AS/Item_Common.root.asb"  # loose file AS/Item_Common.root.asb.zs: has Rotate_GetDemo
ASINFO = "Component/ASInfo/Item_GetDemo.engine__component__ASInfo.bgyml"
ANIM_PARAM = "Component/AnimationParam/Obj_Token_Gold.engine__component__AnimationParam.bgyml"
HOLD_COMMAND = b"Rotate_GetDemo"
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
GAME_ACTOR_INFO = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"
NOTE = "triforce_look"


def _fs(romfs):
    from romtools import Romfs
    return Romfs(romfs, os.path.join(HERE, "original"))


def _romfs():
    import drops as drop_tools  # tools/rando/drops.py: the game folder the plugins read
    return drop_tools.DEFAULT_ROMFS


def plan_sections(romfs=None):
    """make_patch sections for the piece's model and display actor, plus the read-back note."""
    from romtools import sarc_files
    if len(ACTOR) > MAX_NAME:
        raise RuntimeError(f"{ACTOR}: display names over {MAX_NAME} characters aren't created")
    romfs = romfs or _romfs()
    fs = _fs(romfs)
    model_op, info = model.plan(romfs)
    src = sarc_files(fs.read(SRC_PACK))
    if SRC_PARAM not in src:
        raise RuntimeError(f"{SRC_PACK}: no {SRC_PARAM}")
    anim = sarc_files(fs.read(ANIM_PACK))
    if ASINFO not in anim or ANIM_PARAM not in anim or HOLD_COMMAND not in fs.read(AS_REF[1:] + ".zs"):
        raise RuntimeError(f"{ANIM_PACK} / {AS_REF}: the hold-up animation set moved")
    packs = [{"pack": PACK, "file": k, "from_pack": ANIM_PACK} for k in (ASINFO, ANIM_PARAM)]
    packs.append({"pack": PACK, "file": MODELINFO, "from_pack": RELIEF_PACK, "new_from": RELIEF_MODELINFO,
                  "set": {"FmdbName": model.FMDB, "ModelProjectName": model.PROJECT}})
    packs.append({"pack": PACK, "file": PARAM, "new_from": SRC_PARAM, "set": {"$parent": PARENT,
                                                                             "Components": param_components()}})
    lo, hi = model.aabb(info)
    byml = [{"file": ACTOR_INFO, "add_row": {"copy_of": SRC_ACTOR, "set": dict(_row_set(fs, lo, hi), __RowId=ACTOR)}},
            {"file": GAME_ACTOR_INFO, "add_row": {"copy_of": SRC_ACTOR, "set": {"__RowId": ACTOR}}}]
    note = {"model": model.MODEL, "faces": info["faces"], "aabb": [lo, hi], "actor": ACTOR}
    return {"new_files": [model_op, {"to": PACK, "from": SRC_PACK}], "packs": packs, "byml": byml,
            "_gaps": {NOTE: note}}


def param_components():
    """The display's ActorParam components (over its parent Item_Medal_Light's)."""
    return {"ModelInfoRef": "?" + MODELINFO, "ASRef": AS_REF, "ASInfoRef": "?" + ASINFO, "AnimationRef": "?" + ANIM_PARAM}


def _row_set(fs, lo, hi):
    """The ActorInfo fields we set on the display's row, which is a copy of the medallion's. That's the piece's model
    and bounds, the hold-up animation resources (ANIM_ACTOR's) and the larger heap sizes of the two."""
    from romtools import byml_load
    rows = {r["__RowId"]: r for r in byml_load(fs.read(ACTOR_INFO))[0]}
    med, tok = rows[SRC_ACTOR], rows[ANIM_ACTOR]
    return {"ModelProjectName": model.PROJECT, "FmdbName": model.FMDB, "ModelAabbMin": lo, "ModelAabbMax": hi,
            "AnimationResources": [dict(x) for x in tok["AnimationResources"]],
            "InstanceHeapSize": max(int(med["InstanceHeapSize"]), int(tok["InstanceHeapSize"])),
            "PreActorRenderInfoHeapSize": max(int(med["PreActorRenderInfoHeapSize"]),
                                              int(tok["PreActorRenderInfoHeapSize"]))}


def aabb(romfs=None):
    """(min, max) ActorInfo bounds of the piece (drops.look_offsets: where the ground look sits)."""
    romfs = romfs or _romfs()
    _, info = model.plan(romfs)
    return model.aabb(info)


def show_node(nxt):
    """The get scene's create step for the piece (Dm_SY_GetInEvent Event109 with the piece's actor)."""
    return {"actor": "Player_Event", "action": "EventCreateShowItemFromActorFileName",
            "params": {"IsWaitEnd": True, "Actor": ACTOR}, "next": nxt}


def verify(patch, note, romfs):
    """Checks everything the piece look needs:
    - the piece model (a valid one-triangle model, its size-table entry)
    - the display actor's new pack: in the patch and marked new, the Light Medallion display's files and the token's
      animation files byte-equal, ModelInfo naming the model, and the ActorParam a child of the medallion's naming it
    - its new ActorInfo row (model names, bounds, the medallion's values, the larger heap) and GameActorInfo row
      (tables one row longer, still sorted)
    - the name's length
    - every get-scene create step naming it"""
    import json
    from romtools import Romfs, Restbl, sarc_files, byml_load
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    van = _fs(romfs)
    bad = []
    path = os.path.join(patch, model.MODEL)
    if not os.path.exists(path):
        return [f"{model.MODEL}: not in the patch"]
    data = fs.read(model.MODEL)
    bad += model.verify(data, {"faces": note["faces"]})
    rel_rstb = "System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"
    rstb = Restbl(fs.zs.decompress(fs.raw(rel_rstb)))
    entry = rstb.get(model.MODEL[:-3])
    if entry is None or entry < len(data):
        bad.append(f"{model.MODEL}: size-table entry {entry} for {len(data)} bytes")
    if rstb.get(model.SRC[:-3]) != entry:
        bad.append(f"{model.MODEL}: size-table entry {entry} isn't the source model's {rstb.get(model.SRC[:-3])}")
    if note.get("actor") != ACTOR or len(ACTOR) > MAX_NAME:
        bad.append(f"{ACTOR}: the note names {note.get('actor')}; display names over {MAX_NAME} characters aren't "
                   f"created")
    if not os.path.exists(os.path.join(patch, PACK)):
        return bad + [f"{PACK}: not in the patch"]
    report = json.load(open(os.path.join(patch, "patch_report.json"), encoding="utf-8"))
    if not any(w.get("file") == PACK and w.get("new") for w in report.get("files", [])):
        bad.append(f"{PACK}: not marked new in patch_report.json (install.py would not remove it on restore)")
    if (rstb.get(PACK[:-3]) or 0) < len(fs.raw(PACK)):
        bad.append(f"{PACK}: size-table entry {rstb.get(PACK[:-3])} for {len(fs.raw(PACK))} bytes")
    files = sarc_files(fs.read(PACK))
    src = dict(sarc_files(van.read(SRC_PACK)))
    src.update({k: v for k, v in sarc_files(van.read(ANIM_PACK)).items() if k in (ASINFO, ANIM_PARAM)})
    for k, v in src.items():
        if files.get(k) != v:
            bad.append(f"{PACK}: {k} isn't the copy of the vanilla file (medallion display or {ANIM_ACTOR})")
    mi = byml_load(files[MODELINFO])[0] if MODELINFO in files else {}
    if mi.get("FmdbName") != model.FMDB or mi.get("ModelProjectName") != model.PROJECT:
        bad.append(f"{PACK}: {MODELINFO} names {mi}")
    if rstb.get(MODELINFO) is None:
        bad.append(f"{MODELINFO}: no size-table entry")
    p = byml_load(files[PARAM])[0] if PARAM in files else {}
    if p.get("$parent") != PARENT or p.get("Components") != param_components():
        bad.append(f"{PACK}: {PARAM} is {p}")
    # The hold-up (Item_Position's EventIgnitionShowItem plays Rotate_GetDemo on the shown actor) needs the command in
    # its AS and the animation that turns the model's bone. Otherwise it freezes.
    if HOLD_COMMAND not in fs.read(AS_REF[1:] + ".zs"):
        bad.append(f"{AS_REF[1:]}: no {HOLD_COMMAND.decode()} (the hold-up would never end)")
    anim_res = [x.get("ModelProjectName") for x in (byml_load(files[ANIM_PARAM])[0].get("AnimationResources") or [])] \
        if ANIM_PARAM in files else []
    if "Item_Common_Animation" not in anim_res or HOLD_COMMAND not in fs.read(
            "Model/Item_Common_Animation.anim.bfres.zs") or b"\x04\x00Root\x00" not in data:
        bad.append(f"{PACK}: the hold-up animation (Item_Common_Animation's {HOLD_COMMAND.decode()} on bone Root) "
                   f"isn't there for the piece model ({anim_res})")
    # the model loads by the names the actor gives: Model/<ModelProjectName>.<FmdbName>.bfres
    if f"Model/{mi.get('ModelProjectName')}.{mi.get('FmdbName')}.bfres.zs" != model.MODEL:
        bad.append(f"{PACK}: ModelInfo doesn't name {model.MODEL}")
    for t in (ACTOR_INFO, GAME_ACTOR_INFO):  # (other new display rows may be there too)
        ids = [r["__RowId"] for r in byml_load(fs.read(t))[0]]
        vanilla = {r["__RowId"] for r in byml_load(van.read(t))[0]}
        if ids != sorted(ids) or len(ids) != len(set(ids)) or not vanilla <= set(ids) or ACTOR not in ids or ACTOR in vanilla:
            bad.append(f"{t}: {ACTOR} isn't a new row of the sorted table (every vanilla row kept)")
    rows = {r["__RowId"]: r for r in byml_load(fs.read(ACTOR_INFO))[0]}
    want = dict(byml_load(van.read(ACTOR_INFO))[0][[r["__RowId"] for r in byml_load(van.read(ACTOR_INFO))[0]].index(
        SRC_ACTOR)])
    row = rows.get(ACTOR, {})
    special = _row_set(van, note["aabb"][0], note["aabb"][1])
    for k, v in want.items():
        if k in ("__RowId",) or k in special:
            continue
        if row.get(k) != v:
            bad.append(f"{ACTOR_INFO}: {ACTOR}.{k} {row.get(k)!r}, want the medallion's {v!r}")
    for k in ("AnimationResources", "InstanceHeapSize", "PreActorRenderInfoHeapSize"):
        if row.get(k) != special[k]:
            bad.append(f"{ACTOR_INFO}: {ACTOR}.{k} {row.get(k)!r}, want {special[k]!r}")
    want = dict(want, AnimationResources=special["AnimationResources"])
    if row.get("ModelProjectName") != model.PROJECT or row.get("FmdbName") != model.FMDB:
        bad.append(f"{ACTOR_INFO}: {ACTOR} names model {row.get('ModelProjectName')}.{row.get('FmdbName')}")
    lo, hi = note["aabb"]
    for k, box in (("ModelAabbMin", lo), ("ModelAabbMax", hi)):
        if any(abs(float(row.get(k, {}).get(a, 99)) - box[a]) > 1e-4 for a in "XYZ"):
            bad.append(f"{ACTOR_INFO}: {ACTOR}.{k} {row.get(k)}, want {box}")
    extra = set(row) - set(want)
    if extra:
        bad.append(f"{ACTOR_INFO}: {ACTOR} has fields the medallion's row hasn't: {sorted(extra)}")
    g = {r["__RowId"]: r for r in byml_load(fs.read(GAME_ACTOR_INFO))[0]}
    if g.get(ACTOR) != {"__RowId": ACTOR}:
        bad.append(f"{GAME_ACTOR_INFO}: {ACTOR} is {g.get(ACTOR)}")
    # every Triforce entry has to create the piece in place of the medallion
    gi = Evfl(fs.read("Event/EventFlow/Dm_SY_GetInEvent.bfevfl.zs")).flowcharts[0]
    shows = []
    for e in gi["events"]:
        if not e["name"].startswith(("Rando_DI_Triforce", "Rando_DI_ShowTriforce")) or e["type"] != "action":
            continue
        a = gi["actors"][e["actor"]]["actions"][e["action"]]
        if a == "EventCreateShowItemFromActorFileName":
            shows.append(((e.get("params") or {}).get("items") or {}).get("Actor", {}).get("value"))
    if not shows or any(s != ACTOR for s in shows):
        bad.append(f"Dm_SY_GetInEvent: the piece's create steps show {shows}, want {ACTOR}")
    return bad
