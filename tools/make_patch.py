"""Build a romfs patch from a plan.

usage:
  python tools/make_patch.py ROMFS_DIR OUT_DIR PLAN.json [PLAN2.json ...]
  python tools/make_patch.py ROMFS_DIR OUT_DIR data/rewards.csv        (rows with new_item filled in)

Always starts from vanilla files (./original copies win over the live romfs), so building a
new patch never stacks on top of an installed one. Writes only files that actually change,
plus the resource size table with their entries updated.

Plan format (all sections optional):
{
  "chest_event_policy": "auto",            # auto | keep | drop: a chest's GetEventName when its item changes
                                           #   auto = drop item scenes, keep location/story scenes (config/chest_rules.json)
  "chest_size": "keep",                    # keep (default: chests keep their type) | match_contents (tested: converted chests lose their animation)
  "rewards": {                             # location ids (data/locations.json, rewards.csv) or single reward ids (rewards.json)
    "KokiriForest/chest/16757992849254467386": "Item_Range_SlingShot",
    "KokiriForest/chest/10831981390482426294": {"item": "Item_Sword_Kokiri",
                                                 "extra": {"GetEventName": "Get_StoneOfForest_GetSword"}},
    "event/Dm_Kokiri_0155/Dm_Kokiri_0155/Event12/ActorName": "Item_Hookshot",
    "event/Dm_Kokiri_0130/Item_Stone_Forest": {"item": "Obj_Rupee_Blue", "call": "Dm_SY_GetInEvent:Rando_IceTrap"}
                                           # a scene location whose give steps call a shared scene entry instead
  },
  "placements": [                          # any field on any placed actor
    {"file": "Banc/X/X_Dynamic.bcett.byml.zs", "hash": "123", "set": {"Dynamic.Foo": 1, "Gyaml": "Obj_X"},
     "remove": ["Dynamic.Bar"]},
    {"file": "Banc/X/X_Dynamic.bcett.byml.zs", "hash": "456", "delete": true},
                                           # take the placed actor out of the file (refused if another op edits
                                           #   it, or anything in the file links to it or an AiGroup names it)
    {"file": "Banc/X/X_Static.bcett.byml.zs", "hash": "789", "unlink": ["123"]},
                                           # take out the actor's one link to each hash (refused if not exactly one)
    {"file": "Banc/X/X_Dynamic.bcett.byml.zs", "hash": "456", "twin": "458", "set": {"Presence": {...}}}
                                           # a NEW actor: a copy of 456 as the vanilla file has it under hash 458
                                           #   (also its Phive placement ID and its links' Src), then "set" / "remove"
                                           #   ("keep_phive_id": true: the copy keeps 456's Phive placement ID, its
                                           #   baked collision's key; only for a pair never present together)
  ],
  "events": [                              # any string/int/float/bool parameter, or event routing
    {"file": "Npc_X", "flowchart": "Npc_X", "event": "Event46", "param": "ActorName", "value": "Item_Y"},
    {"file": "Npc_X", "flowchart": "Npc_X", "event": "Event47", "param": "Name", "value": "X", "as_string": true},
                                           #   ("as_string": an argument reference becomes a plain text value)
    {"file": "Npc_X", "flowchart": "Npc_X", "event": "Event52", "param": "Frames", "value": 40, "with_copies": true},
                                           #   ("with_copies": the plan's copies of the step get the value too)
    {"file": "Npc_X", "flowchart": "Npc_X", "event": "Event10", "next": "Event12"},   # "next": null = the end
    {"file": "Npc_X", "flowchart": "Npc_X", "event": "Event20", "case": 0, "next": "Event12"}
  ],
  "events (new steps)": [                  # add an entry point running steps in order (new scene parts)
    {"file": "Dm_SY_TreasureboxSmall", "flowchart": "Dm_SY_TreasureboxSmall", "add_entry": "RandoX",
     "steps": [{"call": ":Success_MidoHouse", "params": {"ContentName": {"arg": "ContentName"}}},
               {"actor": "EventSystemActor", "action": "EventTransition", "params": {"EventName": "Dm_Kokiri_0063"}}]}
  ],
  "byml": [                                # any value in any BYML file (compressed or not, incl. RSDB tables)
    {"file": "RSDB/EventSetting.Product.111.rstbl.byml.zs",          # the scene table cannot grow: rewrite a free row
     "replace_row": {"row": "Get_StoneOfForest_GetSword", "copy_of": "KokiriForest_TreasureBox_NaviChatOff",
                     "set": {"EntryPointName": "RandoX"}}},
    {"file": "RSDB/EventSetting.Product.111.rstbl.byml.zs",
     "set": {"[__RowId=Dm_Kokiri_0063].EventBaseSetting": "Work/Event/.../PlayerPos.game__event__GameEventBaseSetting.gyml"}},
    {"file": "Banc/BancBasedResource/GmdReset.byml.zs",
     "remove_values": {"BottomOfTheWell.12639752808773309305.DstHash": [13514633590582184597]},  # each there once
     "delete_keys": ["BottomOfTheWell.11741935678639653889"]},                                 # a dictionary key
    {"file": "Banc/BancBasedResource/MapParam.byml.zs",          # entries appended to a list (made if it's missing),
     "add_entries": {"KokiriForest_Child.TBox": {"like": "InsideTheDekuTree.Floor.1.TBox",   # typed like that list's
                                                 "values": [{"InstanceID": 123, "Trans": [0, 0, 0]}]}}}  # first entry
  ],
  "text": [                                # set a message's text in every language ("lang": "*") or one
    {"lang": "*", "file": "EventFlowMsg/GossipStone.msbt", "label": "GOSSIP_KOKIRI_FOREST_01", "text": "..."},
    {"lang": "*", "file": "...", "label": "...", "markup": "...", "add": true}  # whole message with its tags; new label
    {"lang": "*", "file": "...", "label": "...", "add": true,                     # a copy of another message of the
     "copy_from": {"file": "EventFlowMsg/Get_StoneOfForest.msbt", "label": "9998"}},  #   same language, tags and all
  ],
  "copy": [                                # replace a game file with (a copy of) another game file
    {"from": "Event/.../PlayerPos.game__event__GameEventBaseSetting.bgyml", "to": "Event/.../Dm_Kokiri_0063.game__event__GameEventBaseSetting.bgyml"}
  ],
  "names": [                               # same-length renames of pooled names (u16 length, text, zero) in a file
    {"file": "Model/Npc_X.Npc_X.bfres.zs", "rename": [["Angin_Tile_A_Alb", "Angin_Tile_K_Alb"]]},
                                           #   (each old name exactly once in the file; a model's texture names)
    {"file": "AS/Player_Child.root.asb.zs", "bytes": [{"offset": 2048, "expect": "fdb70100", "bytes": "ffb70100"}]}
  ],                                       #   "bytes": same-size edits, like a new file's (checked first)
  "new_files": [                           # a NEW game file: a copy of a vanilla file with its names renamed; its
    {"to": "Tex/Angin_Tile_K_Alb.bntx.zs", "from": "Tex/Angin_Tile_A_Alb.bntx.zs",  # size-table entry is the
     "rename": [["Angin_Tile_A_Alb", "Angin_Tile_K_Alb"]]},                          # source's; tools/install.py
    {"to": "Model/P.New.bfres.zs", "from": "Model/P.Old.bfres.zs", "rename": [...],  # installs it and removes it
     "bytes": [{"offset": 12288, "expect": "00000100", "bytes": "03000400"}]},      # again on restore. "bytes":
    {"to": "Model/P.Small.bfres.zs", "from": "Model/P.Old.bfres.zs",                 #   same-size edits of the copy
     "segments": [{"copy": [0, 4096]}, {"zero": 256}, {"hex": "5f524c54"}], ...}    #   (offset in the decompressed
  ],                                       #   file, hex strings), each checked against the source first. "segments":
                                           #   a file of another size, made of the source's byte ranges, padding and
                                           #   new bytes before the renames and edits; its size-table entry is the
                                           #   source's minus the size difference (parity/_soul_figures.py)
  "gamedata": [                            # new-file save-data defaults (GameData/GameDataList): a new file starts
    {"defaults": {"KokiriForest_Npc_Kokiri_Mido_Child_Blocker": false,   #   from them; existing saves keep theirs.
                  "PlayerStatus.CurrentRupee": 99,                       #   Bool, Int, UInt, Float, String, Enum (by
                  "Step_Meet_DekuTree": "Step03"},                       #   value name). Names are checked.
     "reset_type": {"12345678901234": 24},                               # when a flag resets (name or instance hash)
     "boolexp": {"Get_StoneOfWater_IsAfter_Step06_Exp": [[0, "Sequence_IsChildhood"], [5]]},  # redefine an expression
     "add_bool_arrays": {"RandoChecked": 300},                           # NEW saved bool arrays (new file: all false)
     "add_runtime_bool_arrays": {"RandoVisit": 300},                     # NEW runtime bool arrays, cleared on map change
     "add_boolexp": {"RandoChk_1": [[8, "RandoChecked", 1]]},            # NEW expression flags (not saved)
     "add_ints": {"Rando_TcgKeyNum": 0},                                 # NEW saved Int rows (new file: the default)
     "add_seeded_ints": {"seed": 1927452819, "rows": {"Armor_Child_Mask_Bunny": 0}},  # NEW Int rows keyed
                                          #   murmur3(name, seed), for code that hashes a name with a seed
     "add_bools": {"RandoAP_Signal": false},                             # NEW saved plain Bool rows (new file: default)
     "add_struct_bools": {"IsTreasureBoxOpen": ["876108895472176682"]},  # NEW members (+ Bool rows) of a Bool struct
     "per_object": {"12345678901234": {"ResetTypeValue": 88, "ExtraByte": 6}},  # per-object flag fields
     "add_per_object": {"12345678901236": {"ResetTypeValue": 88, "ExtraByte": 6}}}  # NEW per-object rows
                                           # new rows: the save layout (MetaData) is recomputed, after checking the
                                           #   formula reproduces the vanilla layout exactly (gamedata_layout)
  ],
  "binary": [                              # a 32-bit number at an offset of an uncompressed file, checked first
    {"file": "Sequence/SetPouchAndStatusForGameStart.module.ainb", "offset": 4552, "i32": 20, "expect": 12}
  ],
  "packs": [                               # any value in any BYML file inside an actor pack
    {"pack": "Pack/Actor/Enemy_Skulltula_Gold.pack.zs",
     "file": "Drop/DropSubTable/DropTable_Token_Gold.game__drop__DropSubTable.bgyml",
     "set": {"Items.0.DropActorName": "Work/Actor/Obj_Rupee_Gold.engine__actor__ActorParam.gyml"}},
    {"pack": "...", "file": "Component/ShopParam/New.game__component__ShopParam.bgyml",   # a NEW file in the pack:
     "new_from": "Component/ShopParam/Old.game__component__ShopParam.bgyml", "set": {...}}, # a copy of another,
                                           #   with a size-table entry of its own (the source's, plus its growth)
    {"pack": "Pack/Actor/Obj_Heart_Piece.pack.zs", "file": "Component/ActorHolderParam/X.game__component__...bgyml",
     "from_pack": "Pack/Actor/X.pack.zs"},   # a byte copy of the same path from another pack (the path keeps its
                                           #   size-table entry); "set" may follow; with "new_from" the copy of that
                                           #   file of the other pack goes to the new path "file" (an entry of its own)
    {"pack": "*", "file": "Actor/Obj_Heart_Piece.engine__actor__ActorParam.bgyml", "set": {...}}
  ],                                       # "pack": "*" = every pack of the game holding the file, or a list of packs.
                                           # A file inside a pack must end alike in every pack holding its path
                                           # (tools/packpaths.py); the patch is refused otherwise.
  "exefs": [                               # code patches Longshot's Builder applies to the game's code when it builds
    {"file": "rando_of_time_gear_wheel.pchtxt", "text": "@nsobid-..."}   # the game: written to the "exefs" folder
  ],                                       #   beside the patch folder (a mod's romfs and exefs, side by side)
  "cheats": [                              # a mod's cheats file (Atmosphere format, named by the game's build id):
    {"file": "E0F3CCFAF50065AE.txt", "text": "[...]"}   # written to the "cheats" folder beside the patch folder;
  ],                                       #   each cheat is a switch in Longshot's Insert menu (the Mods tab)
  "ainb": [                               # AI graphs (tools/ainb.py): a loose file, or "pack" + its inner "file"
                                           #   ("pack": "*": every pack holding the file; bb_params tables likewise)
    {"pack": "Pack/Actor/Obj_Pot_A_01.pack.zs", "file": "AI/Obj_Pot.root.ainb", "edits": [
      {"copy": {"from": {"pack": "Pack/Actor/Enemy_Skulltula_Gold.pack.zs",          # nodes from another file, with
                         "file": "AI/Enemy_Skulltula_Gold.utility.root.ainb"},       #   all they link to; refer to
                "nodes": ["OneShotDropSetOverWriteParam"], "label": "drop"}},        #   them as "drop:<source index>"
      {"copy": {"from": {...}, "nodes": [1], "label": "one", "follow": false}},    # just that node, unlinked
      {"copy": {"from": {...}, "nodes": [25], "label": "w", "follow": false,       # a parameter that reads the
                "values": {"25": {"BaseFrameTime": 20.0}}}},                       #   source's blackboard needs
                                                                                   #   its own value (ainb.BB_INDEXED)
      {"wrap": {"command": "Root"}},          # the command starts at a new Simultaneous holding its old start node
                                              #   ("if_needed": true: not when it already starts at one like it)
      {"set_property": {"node": "drop:1", "name": "Key", "value": "RespawnGmdHash"}},
      {"retype": {"node": 0, "from": {...}, "like": 4, "values": {"4": {"Unlock": True}}}},  # node 0 becomes a
                                              #   copy of that node (same index; cut what reads node 0 first)
      {"add_child": {"parent": "@Root", "child": "drop:2"}},     # "@Root": the node command Root starts at
      {"link": {"from": "drop:0", "output": "OverwriteParam", "to": "drop:1", "input": "OverwriteParam"}},
      {"feed": {"from": "q:46", "output": "IsEqual", "to": "sel:116", "input": "Input"}},  # bool/float/string/int
      {"add_child": {"parent": "sel:116", "child": "val:117", "name": "True"}},  # a BoolSelector's True/False case
      {"add_child": {"parent": "rnd:35", "child": "val:117", "weight": 1.0}},    # a RandomSelector's weighted child
      {"add_child": {"parent": "f:20", "child": 23, "default": ""}},            # an F32/StringSelector's default
      {"add_child": {"parent": "f:20", "child": 25, "range": [-5000, -1000]}},  # an F32Selector case (low, high)
      {"add_child": {"parent": "s:16", "child": 22, "string": "Title"}},        # a StringSelector case
      {"set_child": {"parent": "@EventQueryCheckTagOnPouchActor", "which": "Execute", "child": "sel:116"}},
      {"set_input": {"node": "OneShotDeathRequestDeath#1", "name": "DeathReson", "value": 10}},  # "#1": 2nd of name
                                              #   ("const": true: a value set on purpose, never the default's shape)
      {"set_bb": {"name": "TerrorLevel", "value": 2.5}},     # a blackboard default
      {"add_bb": {"type": "string", "name": "X", "like": "DropViewActor"}},  # a new entry (reading Y's table)
      {"read_bb": {"node": "sel:70", "input": "A", "bb": "X"}},  # an input reads a blackboard entry
      {"repoint_source": {"to": 2, "input": "BoolMulti", "old": 3, "from": 1, "output": "Bool"}},  # an OR/AND entry
                                              #   that read node 3 reads node 1's Bool instead
      {"bb_param": {"table": "Component/Blackboard/BlackboardParamTable/Drop.engine__component__BlackboardParamTable.bgyml",
                    # ("instance": true: placements may set it, Dynamic.<key>; make_patch then accepts that)
                    "type": "U64", "key": "RespawnGmdHash", "init": 0}}]},  # a key in an actor blackboard table (packs)
    {"pack": "Pack/Actor/Obj_Heart.pack.zs", "bb_params": [{"table": "...", "type": "U64", "key": "RespawnGmdHash"}]}
  ]                                        # node refs: index, name, "name#n", "label:i", "@Command"; every edit is
}                                          #   read back from the written file
"file" for events may be a base name ("Npc_X"): every version of it (Npc_X.bfevfl.zs, Npc_X.110.bfevfl.zs) is edited.
"""
import csv
import difflib
import json
import os
import re
import struct
import sys
import zlib
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from romtools import (Romfs, Restbl, byml_load, byml_dump, byml_is_big, murmur3_32, sarc_files, sarc_write,  # noqa: E402
                      U32, U64, I64, F64)
from evfl import Evfl, EvflEditor  # noqa: E402
from evfl_build import EvflBuilder, sync_sub_flows, stale_sub_flows  # noqa: E402
from actor_params import ActorParams  # noqa: E402
import progressive  # noqa: E402
import trade_slot  # noqa: E402
import msbt  # noqa: E402
import progress  # noqa: E402  (the app's progress bar: prints only when the app asks)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VANILLA = os.environ.get("REMAKE_ORIGINAL") or os.path.join(HERE, "original")  # the app: next to the game
CATALOG = os.path.join(HERE, "data", "rewards.json")
RSTB_PATH = "System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"
CHEST_ITEM_BOUND = ("Drop__CheckActor", "Drop__DropActor_Substitute")  # refer to the old item
CHEST_RULES = json.load(open(os.path.join(HERE, "config", "chest_rules.json"), encoding="utf-8"))
PROGRESSIVE = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]
SCENE_ROWS = json.load(open(os.path.join(HERE, "config", "scene_rows.json"), encoding="utf-8"))["rows"]


A06_PLAIN = {"Obj_TBox_A_06": "Obj_TBox_A_01", "Obj_TBox_A_06_NoBake": "Obj_TBox_A_01_NoBake"}  # (dungeons.A06)


def planned_chest_actor(retype, r):
    """The chest type the patched level holds. A plan placement edit that sets the chest's Gyaml (the appearance
    plugin's chest looks, tools/rando/parity/appearance.py) wins over the catalogued type."""
    for f in r.get("files", []):
        if (f, str(r.get("hash"))) in retype:
            return retype[(f, str(r.get("hash")))]
    return r["actor"]


def resolve_progressive(rid, spec, r, ctx):
    """OoTR progressive item -> its first tier in the chest (never shown) plus the chest's "give the right
    tier" scene (tools/progressive.py). The scene checks what the player owns when the chest is opened,
    then holds up and gives that tier, like OoTR's resolve_upgrades. One scene per item and chest type,
    each on a reused scene ID (config/scene_rows.json). We tried Obj_TBox_A_06 chests before and they
    broke Kokiri Forest."""
    spec = {"item": spec} if isinstance(spec, str) else dict(spec)
    name = spec["item"]
    if name not in PROGRESSIVE:
        return spec
    tiers = PROGRESSIVE[name]["tiers"]
    if r["source"] == "event":  # a scene's give step, scene_progressive_ops replaces it
        return dict(spec, item=tiers[0], progressive=name)
    if r["kind"] != "chest":
        raise PlanError(f"{rid}: {name} in a {r['kind']} location: progressive items go in chests and scene "
                        f"rewards only")
    # the scene follows the type the plan gives the chest. A look option may make a small chest big or invisible,
    # and an A_04 spot holding a real item becomes Obj_TBox_A_01 through its reward's Gyaml. That covers any small
    # or big chest family, the Lens and boss-key chests too (generate.guard_progressive)
    actor = (spec.get("extra") or {}).get("Gyaml") or planned_chest_actor(ctx["retype"], r)
    plain = A06_PLAIN.get(actor)  # the plain small chest, since check-actor AI can change its contents
    chest = (progressive.scene_family(plain or actor)  # picks the second item if Link owns the check item (shops)
             or {"Obj_TBox_A_01_memo11": "small"}.get(actor))  # the Fairy Note chest's AI plays GetEventName
    if chest is None:
        raise PlanError(f"{rid}: {name} in a {r['actor']}: only small and big chests have a progressive scene")
    key = (name, chest)
    if key not in ctx["rows"]:
        free = [row for row in SCENE_ROWS if row not in ctx["rows"].values() and row not in ctx["plan_rows"]]
        if not free:
            raise PlanError(f"{rid}: no free scene ID left for {name}'s chest scene (config/scene_rows.json)")
        ctx["rows"][key] = free[0]
    ev = r["extra"].get("GetEventName")
    if ev and chest_event_kind(ev) == "location":
        ctx["warnings"].append(f"{rid}: this chest's own scene {ev} is replaced by the progressive scene")
    extra = dict(spec.get("extra") or {})
    extra["GetEventName"] = ctx["rows"][key]
    if plain:
        extra["Gyaml"] = plain
    return dict(spec, item=tiers[0], extra=extra, progressive=name)


def add_progressive_scenes(plan, catalog, expanded, rows, place_ops, warnings, romfs):
    """For each progressive item and chest type in use, adds the scene (a new entry point in the chest's scene file)
    and its scene ID (a reused row pointed at that entry). The vanilla chest that used the row loses its scene."""
    for (name, chest), row in rows.items():
        entry = progressive.entry_name(name, chest)
        scene = progressive.CHEST_SCENE_FILE[chest]
        rels = event_files(romfs, scene)
        newest = [r for r in rels if re.search(r"\.\d{3}\.bfevfl", r)] or rels  # the game reads Name.110.bfevfl.zs
        model = Evfl(Romfs(romfs, VANILLA).read(newest[0]))  # the vanilla scene its copies come from
        for graph, nodes, start in progressive.chest_graphs(name, chest, model):
            plan["events"].append({"file": scene, "flowchart": scene, "add_graph": graph, "nodes": nodes, "start": start})
        plan["byml"].append({"file": EVENT_SETTING, "replace_row": {
            "row": row, "copy_of": scene, "set": {"EntryPointName": entry}}})
        warnings.append(f"{name} ({chest} chests): scene {scene}:{entry} on reused scene ID {row}")
        for r in catalog.values():
            if r["kind"] == "chest" and r["id"] not in expanded and r["extra"].get("GetEventName") == row:
                for f in r["files"]:
                    place_ops[f].append((r["hash"], {}, ["Dynamic.GetEventName"]))
                warnings.append(f"{r['id']}: keeps {r['item']} but plays the normal opening (its scene ID {row} "
                                f"now serves the progressive scene)")


def got_node(flag, nxt):
    """A step that sets saved Bool `flag` (a reward's "got" flag), then goes on to `nxt`."""
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool", "new_actor": True,
            "params": {"GameDataName": flag, "Value": True, "Index": -1}, "next": nxt}


def got_ops(r, flag, romfs):
    """{event file: [ops]} that set `flag` right before scene reward r's give step (its own step, left as it is):
    a new step in front of it that every way into the give goes through. The trackers read the flag
    (rando/native_tracker.py got flags)."""
    vanilla = Romfs(romfs, VANILLA)
    out = defaultdict(list)
    for f in r["files"]:
        fc = next((x for x in Evfl(vanilla.read(f)).flowcharts if x["name"] == r["flowchart"]), None)
        e = next((x for x in (fc or {}).get("events", []) if x["name"] == r["event"]), None)
        if e is None:
            raise PlanError(f"{r['id']}: no step {r['event']} in {f}")
        graph = f"Rando_{r['event']}_Got"
        out[f].append({"flowchart": r["flowchart"], "add_graph": graph, "start": "got",
                       "nodes": {"got": got_node(flag, f"@{r['event']}")}})
        for kind, where, k in progressive.predecessors(fc, e):
            op = {"flowchart": r["flowchart"], "next": f"{graph}_got"}
            if kind == "entry":
                op["entry"] = where
            else:
                op["event"] = where
                if kind in ("case", "fork"):
                    op[kind] = k
            out[f].append(op)
    return out


def scene_call_ops(r, target, romfs, siblings=(), params=None, got=None):
    """{event file: [ops]} that replace scene reward r's give step with a call to scene entry `target`
    ("File:Entry"), e.g. an ice trap's freeze scene or a dungeon item's credit scene. `params` are the call's
    parameters. If a step only shows the item and the same location also has a step that adds it, the show step
    gets skipped instead, so the call runs once. `got` is a flag set just before (got_ops)."""
    vanilla = Romfs(romfs, VANILLA)
    out = defaultdict(list)
    skip = r.get("call") in progressive.DISPLAY_ROUTINES and any(
        s_.get("call") not in progressive.DISPLAY_ROUTINES for s_ in siblings)
    for f in r["files"]:
        model = Evfl(vanilla.read(f))
        fc = next((x for x in model.flowcharts if x["name"] == r["flowchart"]), None)
        e = next((x for x in (fc or {}).get("events", []) if x["name"] == r["event"]), None)
        if e is None:
            raise PlanError(f"{r['id']}: no step {r['event']} in {f}")
        after = fc["events"][e["next"]]["name"] if e.get("next", 0xFFFF) < len(fc["events"]) else None
        if skip:
            new_start = after
            if got:
                graph = f"Rando_{r['event']}_Got"
                out[f].append({"flowchart": r["flowchart"], "add_graph": graph, "start": "got",
                               "nodes": {"got": got_node(got, f"@{after}" if after else None)}})
                new_start = f"{graph}_got"
        else:
            graph = f"Rando_{r['event']}_Call"
            node = {"call": target, "next": f"@{after}" if after else None}
            if params:
                node["params"] = dict(params)
            nodes, start = {"call": node}, "call"
            if got:
                nodes, start = {"got": got_node(got, "call"), "call": node}, "got"
            out[f].append({"flowchart": r["flowchart"], "add_graph": graph, "start": start, "nodes": nodes})
            new_start = f"{graph}_{start}"
        for kind, where, k in progressive.predecessors(fc, e):
            op = {"flowchart": r["flowchart"], "next": new_start}
            if kind == "entry":
                if new_start is None:
                    raise PlanError(f"{r['id']}: entry point {where} starts at the skipped step {r['event']}")
                op["entry"] = where
            else:
                op["event"] = where
                if kind in ("case", "fork"):
                    op[kind] = k
            out[f].append(op)
    return out


def scene_progressive_ops(r, name, romfs, hosts, siblings=(), got=None):
    """{event file: [ops]} that replace scene reward r's give step with "give the right tier" steps
    (tools/progressive.py), either in the giver's flowchart or in a host entry next to the give routine. `got` is a
    flag set just before (got_ops)."""
    tiers = PROGRESSIVE[name]["tiers"]
    vanilla = Romfs(romfs, VANILLA)
    out = defaultdict(list)
    for f in r["files"]:
        model = Evfl(vanilla.read(f))
        fc = next((x for x in model.flowcharts if x["name"] == r["flowchart"]), None)
        e = next((x for x in (fc or {}).get("events", []) if x["name"] == r["event"]), None)
        if e is None:
            raise PlanError(f"{r['id']}: no step {r['event']} in {f}")
        mode = progressive.scene_give_mode(fc, e, r["param"])
        if mode is None:
            raise PlanError(f"{r['id']}: {name} can't be given here: {r['flowchart']} has no PouchSystemActor and "
                            f"its give step isn't a plain give-routine call")
        after = fc["events"][e["next"]]["name"] if e.get("next", 0xFFFF) < len(fc["events"]) else None
        graph = f"Rando_{r['event']}_" + "".join(w for w in name.title().split() if w.isalnum())
        # If this location already gave the item, the display step just shows that same item.
        by_name = {x["name"]: x for x in fc["events"]}
        owned = r.get("call") in progressive.DISPLAY_ROUTINES and any(
            s_["flowchart"] == r["flowchart"] and s_.get("call") not in progressive.DISPLAY_ROUTINES
            and s_["event"] in by_name and progressive.reachable(fc, by_name[s_["event"]]["idx"], e["idx"])
            for s_ in siblings if f in s_["files"])
        if mode == "inplace":
            # For a tier that's never held up (the ocarinas, progressive.NO_POSE), a step that may pose gives
            # through its own entry. A pose-free one gets copied, and the location's last give step then calls
            # the tier's "after".
            last = not any(s_["flowchart"] == r["flowchart"] and s_["event"] in by_name
                           and progressive.reachable(fc, e["idx"], by_name[s_["event"]]["idx"])
                           for s_ in siblings if f in s_["files"])
            nodes, start = progressive.inplace_graph(tiers, r["event"], r["param"], after, owned,
                                                     pose_free=progressive.step_pose_free(fc, e), last=last)
        else:
            host, routine = e["flowchart"], e["entry_point"]
            entry = progressive.host_entry(name, routine, owned)
            if (host, routine, name, owned) not in hosts:
                hosts.add((host, routine, name, owned))
                hn, hs = progressive.host_graph(tiers, routine, r["param"], owned, host=host)
                for hf in event_files(romfs, host):
                    out[hf].append({"flowchart": host, "add_graph": entry, "nodes": hn, "start": hs})
            nodes, start = {"call": {"call": f"{host}:{entry}", "next": f"@{after}" if after else None}}, "call"
        if got:
            nodes, start = dict(nodes, rando_got=got_node(got, start)), "rando_got"
        out[f].append({"flowchart": r["flowchart"], "add_graph": graph, "nodes": nodes, "start": start})
        new_start = f"{graph}_{start}"
        for kind, where, k in progressive.predecessors(fc, e):
            op = {"flowchart": r["flowchart"], "next": new_start}
            if kind == "entry":
                op["entry"] = where
            else:
                op["event"] = where
                if kind in ("case", "fork"):
                    op[kind] = k
            out[f].append(op)
    return out


def chest_event_kind(event_name):
    """'location' for scenes that belong to the chest's spot (story, minigames, Navi), else 'item'."""
    if any(re.search(rx, event_name) for rx in CHEST_RULES["get_events"]["location"]):
        return "location"
    return "item"


def chest_actor_for(actor, item):
    """The chest style vanilla would use for this item, keeping the chest's NoBake variant.
    Chests outside the standard small/big/boss-key set keep their look."""
    rules = CHEST_RULES["chest_size"]
    if actor not in rules["styles"]:
        return actor
    if re.search(rules["boss_key_items"], item):
        style = "boss_key"
    elif re.search(rules["small_items"], item):
        style = "small"
    else:
        style = "big"
    return rules["actor_for"][style] + ("_NoBake" if actor.endswith("_NoBake") else "")


class PlanError(Exception):
    pass


def load_plans(paths):
    plan = {"chest_event_policy": "auto", "chest_size": "keep",
            "rewards": {}, "placements": [], "events": [], "packs": [], "byml": [], "copy": [], "text": [],
            "gamedata": [], "binary": [], "ainb": [],
            "cosmetics": {"slink": [], "textures": [], "effects": [], "hud": [], "map_icons": []},
            "names": [], "new_files": [], "groups": [], "exefs": [], "cheats": []}
    for p in paths:
        if p.lower().endswith(".csv"):
            with open(p, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if (row.get("new_item") or "").strip():
                        plan["rewards"][row["id"]] = row["new_item"].strip()
            continue
        part = json.load(open(p, encoding="utf-8"))
        plan["chest_event_policy"] = part.get("chest_event_policy", plan["chest_event_policy"])
        plan["chest_size"] = part.get("chest_size", plan["chest_size"])
        plan["rewards"].update(part.get("rewards", {}))
        plan["placements"] += part.get("placements", [])
        plan["events"] += part.get("events", [])
        plan["packs"] += part.get("packs", [])
        plan["byml"] += part.get("byml", [])
        plan["copy"] += part.get("copy", [])
        plan["text"] += part.get("text", [])
        gd = part.get("gamedata", [])
        plan["gamedata"] += [gd] if isinstance(gd, dict) else gd
        plan["binary"] += part.get("binary", [])
        plan["ainb"] += part.get("ainb", [])
        plan["names"] += part.get("names", [])
        plan["new_files"] += part.get("new_files", [])
        plan["groups"] += part.get("groups", [])  # new logic groups in level files (ADD_GROUP)
        plan["exefs"] += part.get("exefs", [])  # code patches (write_exefs)
        plan["cheats"] += part.get("cheats", [])  # the mod's cheats file (write_cheats)
        if part.get("trade_slot"):  # the trade button's picker and owned record (tools/trade_slot.py)
            plan["trade_slot"] = part["trade_slot"]
        if part.get("_show_models"):  # the Ocarina buttons' controls and controller (parity/songs_trade.finish_plan)
            plan["_show_models"] = part["_show_models"]
        cos = part.get("cosmetics") or {}  # sound links and texture colours (tools/rando/parity/_cosmetics_apply.py)
        for kind in ("slink", "textures", "effects", "hud"):  # sounds, textures, effect and HUD colours
            plan["cosmetics"][kind] += cos.get(kind, [])
        for key in cos.get("map_icons", []):  # the map tracker's icons (parity/_map_icons.py)
            if key not in plan["cosmetics"]["map_icons"]:
                plan["cosmetics"]["map_icons"].append(key)
    return plan


# Scene name -> its "new_files" op, which writes Event/EventFlow/<name>.bfevfl.zs.
# "events" ops edit these renamed copies like any other scene, and each gets a size-table entry of its own
# from the source and the sizing rule for its edited file. That's how the Archipelago mailbox
# (parity/archipelago.py) stays out of the scenes that load Dm_SY_GetInEvent.
NEW_EVENTS = {}


def event_files(romfs, name):
    if name in NEW_EVENTS:
        return [NEW_EVENTS[name]["to"]]
    if name.startswith("Event/"):
        return [name]
    d = os.path.join(romfs, "Event", "EventFlow")
    rx = re.compile(re.escape(name) + r"(\.\d{3})?\.bfevfl\.zs$")
    found = sorted(f"Event/EventFlow/{f}" for f in os.listdir(d) if rx.match(f))
    if not found:
        raise PlanError(f"no event file named {name}")
    return found


def compile_plan(plan, romfs, catalog):
    """Turns rewards into low-level placement/event operations."""
    place_ops = defaultdict(list)  # file -> [(hash, set{}, remove[])]
    event_ops = defaultdict(list)  # file -> [op]
    report, warnings = [], []
    groups = defaultdict(list)
    for r in catalog.values():
        groups[r["location"]].append(r["id"])
    expanded = {}
    for rid, spec in plan["rewards"].items():
        if rid in catalog:
            expanded[rid] = spec
        elif rid in groups:  # a location id: edit every part of it
            for member in groups[rid]:
                expanded.setdefault(member, spec)
        else:
            raise PlanError(f"unknown reward or location id {rid}")
    plan_rows = {(s_.get("extra") or {}).get("GetEventName") for s_ in plan["rewards"].values() if isinstance(s_, dict)}
    plan_rows |= {op["replace_row"]["row"] for op in plan["byml"] if "replace_row" in op}
    retype = {(op["file"], str(op["hash"])): op["set"]["Gyaml"] for op in plan["placements"]
              if "Gyaml" in op.get("set", {})}
    ctx = {"rows": {}, "plan_rows": plan_rows, "warnings": warnings, "retype": retype}
    expanded = {rid: resolve_progressive(rid, spec, catalog[rid], ctx) for rid, spec in expanded.items()}
    hosts = set()  # (host file, routine, item) entries already added
    add_progressive_scenes(plan, catalog, expanded, ctx["rows"], place_ops, warnings, romfs)
    actors = {f[:-len(".pack.zs")] for f in os.listdir(os.path.join(romfs, "Pack", "Actor")) if f.endswith(".pack.zs")}
    unknown = {}
    for rid, spec in expanded.items():
        s_ = {"item": spec} if isinstance(spec, str) else spec
        if s_["item"] not in actors and not s_.get("force"):
            unknown[s_["item"]] = difflib.get_close_matches(s_["item"], actors, n=3, cutoff=0.6)
        if catalog[rid]["kind"] == "shop" and not str(s_["item"]).startswith("Shop_") and not s_.get("force"):
            raise PlanError(f"{rid}: shop slots take Shop_* actors (got {s_['item']}); add \"force\": true to override")
    if unknown:
        raise PlanError("not actors in this game (add \"force\": true to use anyway): " +
                        "; ".join(f"{k} (did you mean {', '.join(v) or '?'})" for k, v in unknown.items()))
    for rid, spec in expanded.items():
        r = catalog[rid]
        spec = {"item": spec} if isinstance(spec, str) else dict(spec)
        item = spec["item"]
        report.append({"id": rid, "kind": r["kind"], "from": r["item"],
                       "to": f"{spec['progressive']} ({' -> '.join(PROGRESSIVE[spec['progressive']]['tiers'])})"
                       if spec.get("progressive") else item})
        got = spec.get("got")  # a saved Bool set just before the give, for the trackers (got_ops)
        if got and r["source"] != "event":
            raise PlanError(f"{rid}: \"got\" is for scene gives only (a chest or placement keeps its own flag)")
        if item == r["item"] and not spec.get("extra") and not spec.get("call") and not spec.get("progressive") \
                and not got:
            continue  # unchanged: leave the file alone
        if not spec.get("force") and r["source"] == "placement" and (
                (r["kind"] == "scrub" and r["field"].startswith("Dynamic.ScrubBusiness_ShopItemActorName"))
                or (r["kind"] == "shop" and r["field"] == "Gyaml")):
            raise PlanError(f"{rid}: this setting doesn't decide what is sold (a scrub's is a lookup key, a shop "
                            f"shelf's item comes from the shopkeeper's GoodsList). "
                            f"Add \"force\": true to change it anyway")
        if r["source"] == "placement":
            sets, removes = {r["field"]: item}, []
            extra = spec.get("extra") or {}
            if r["kind"] == "chest" and item != r["item"]:
                for k in CHEST_ITEM_BOUND:
                    if k in r["extra"]:
                        removes.append(f"Dynamic.{k}")
                ev = r["extra"].get("GetEventName")
                policy = plan["chest_event_policy"]
                if ev and "GetEventName" not in extra and (
                        policy == "drop" or (policy == "auto" and chest_event_kind(ev) == "item")):
                    removes.append("Dynamic.GetEventName")  # an item scene scripted for the old item at this spot
                if plan["chest_size"] == "match_contents" and "Gyaml" not in extra:
                    new_actor = chest_actor_for(r["actor"], item)
                    if new_actor != r["actor"]:
                        sets["Gyaml"] = new_actor
                        warnings.append(f"{rid}: chest becomes {new_actor} for {item}")
            rewritten = {op["replace_row"]["row"] for op in plan["byml"] if "replace_row" in op}
            rewritten |= {(op["add_row"].get("set") or {}).get("__RowId") for op in plan["byml"] if "add_row" in op}
            # scene files the plan already edits (an EventSetting row "Get_X_Y" lives in event file "Get_X")
            edited = {os.path.basename(op["file"]).split(".")[0] for op in plan["events"]}
            if extra.get("GetEventName") and extra["GetEventName"] not in rewritten \
                    and not any(extra["GetEventName"].startswith(f) for f in edited) \
                    and chest_event_kind(extra["GetEventName"]) == "item":
                warnings.append(f"{rid}: {extra['GetEventName']} is an item scene staged at its vanilla chest; point its "
                                f"chest step at this chest's type and move its cinematic")
            if "Gyaml" in extra:
                sets["Gyaml"] = extra["Gyaml"]
            for k, v in extra.items():
                if k == "Gyaml":
                    continue
                if v is None:
                    removes.append(f"Dynamic.{k}")
                else:
                    sets[f"Dynamic.{k}"] = v
            for f in r["files"]:
                place_ops[f].append((r["hash"], sets, removes))
        elif spec.get("call") and r["source"] == "event":
            siblings = [catalog[x] for x in groups[r["location"]] if x != rid] if r.get("location") else []
            for f, ops in scene_call_ops(r, spec["call"], romfs, siblings, spec.get("call_params"), got).items():
                event_ops[f] += ops
            warnings.append(f"{rid}: give step replaced by a call to {spec['call']}")
        elif spec.get("progressive"):
            siblings = [catalog[x] for x in groups[r["location"]] if x != rid] if r.get("location") else []
            for f, ops in scene_progressive_ops(r, spec["progressive"], romfs, hosts, siblings, got).items():
                event_ops[f] += ops
            warnings.append(f"{rid}: {spec['progressive']} decided when given ({r['event_file']}:{r['event']})")
        elif r["source"] == "event" and progressive.hold_node(item, None) and _hold_step(r, romfs):
            # Link can't hold this item up, so this step uses the stand-in animation or the get window from
            # config/hold_up.json.
            hold = progressive.hold_node(item, None)
            siblings = [catalog[x] for x in groups[r["location"]] if x != rid] if r.get("location") else []
            for f, ops in scene_call_ops(r, hold["call"], romfs, siblings, hold.get("params"), got).items():
                event_ops[f] += ops
            warnings.append(f"{rid}: {item} can't be held up itself: {hold['call']}")
        else:
            for f in r["files"]:
                if item != r["item"]:
                    event_ops[f].append({"flowchart": r["flowchart"], "event": r["event"], "param": r["param"],
                                         "value": item})
            if got:
                for f, ops in got_ops(r, got, romfs).items():
                    event_ops[f] += ops
    for op in saria_hand_ops(expanded, catalog, romfs, warnings):
        for f in event_files(romfs, "Dm_Kokiri_0155"):
            event_ops[f].append(op)
    # A chest plays the wrong scene if replace_row reuses its vanilla GetEventName, so we clear that name
    # unless the reward sets its own (progressive chests, ice traps, moved item scenes).
    # add_progressive_scenes and the chests plugin also clear it on their own rows. Removing it twice
    # is fine.
    reused_rows = {op["replace_row"]["row"] for op in plan["byml"]
                   if "replace_row" in op and op.get("file") == EVENT_SETTING}
    if reused_rows:
        asked = {rid for rid, spec in expanded.items()
                 if isinstance(spec, dict) and "GetEventName" in (spec.get("extra") or {})}
        for r in catalog.values():
            if r["kind"] == "chest" and r["extra"].get("GetEventName") in reused_rows and r["id"] not in asked:
                for f in r["files"]:
                    place_ops[f].append((r["hash"], {}, ["Dynamic.GetEventName"]))
    # Keep the reward's scene even if another plugin clears GetEventName because it reused the vanilla scene ID.
    # The chests plugin once reused the Deku Tree map chest's row for an ice trap. Its removal op wiped the
    # compass scene the dungeons plugin had added to that chest, so the chest gave the stand-in item instead.
    keeps_scene = {(f, str(catalog[rid]["hash"])) for rid, spec in expanded.items()
                   if rid in catalog and isinstance(spec, dict) and (spec.get("extra") or {}).get("GetEventName")
                   for f in catalog[rid]["files"]}
    named = {}  # scenes and AIs look a placement up by its Name (the get scene's RandoGetSceneNN, the pot
    for op in plan["placements"]:  # and grass marker's RandoUnchecked), so two features can't both name one
        n = (op.get("set") or {}).get("Name")
        if n is not None:
            key = (op["file"], str(op.get("twin") or op["hash"]))  # a twin is a new actor with a name of its own
            if named.setdefault(key, n) != n:
                raise PlanError(f"{op['file']}: {op['hash']}: named both {named[key]} and {n}")
    for g in plan.get("groups", []):  # (ADD_GROUP, spec, []) is a new logic group, patch_placement adds it
        place_ops[g["file"]].append((ADD_GROUP, {k: v for k, v in g.items() if k != "file"}, []))
    for op in plan["placements"]:
        if op.get("twin") is not None:  # (new hash, {TWIN_OF: source, ...sets}, removes) is a new actor
            if op.get("delete") or op.get("unlink"):
                raise PlanError(f"{op['file']}: twin {op['twin']} of {op['hash']}: only set / remove apply")
            extra = {NO_GROUPS: True} if op.get("join_groups") is False else {}  # not in its source's groups
            if op.get("keep_phive_id"):
                extra[KEEP_PHIVE_ID] = True
            if op.get("relink"):  # {old end: new end}, copied links to "old end" go to "new end" instead
                extra[RELINK] = dict(op["relink"])
            if op.get("add_links"):  # new plain links, e.g. a keeper twin's to new shop boards. "name" makes it a
                # link of that Gyaml/Name instead of Reference, e.g. a cow proxy's EventProxyRequestLink
                if any(w.get("like") is not None for w in op["add_links"]):
                    raise PlanError(f"{op['file']}: twin {op['twin']}: add_links takes plain links only")
                extra[ADD_LINKS] = list(op["add_links"])
            place_ops[op["file"]].append((str(op["twin"]), {TWIN_OF: str(op["hash"]), **extra, **op.get("set", {})},
                                          list(op.get("remove", []))))
            continue
        if op.get("delete"):  # (hash, None, None), patch_placement takes the actor out of the file
            if op.get("set") or op.get("remove"):
                raise PlanError(f"{op['file']}: {op['hash']}: a deleted placement can't also be edited")
            place_ops[op["file"]].append((str(op["hash"]), None, None))
            continue
        sets = dict(op.get("set", {}))
        if op.get("add_links"):  # [{"like": a hash it links, "dst": the new end}] copies that link, and without
            sets[ADD_LINKS] = op["add_links"]  # "like" it's a new plain Reference link (Gyaml/Name "Reference")
        removes = [k for k in op.get("remove", [])
                   if not (k == "Dynamic.GetEventName" and (op["file"], str(op["hash"])) in keeps_scene)]
        place_ops[op["file"]].append((str(op["hash"]), sets,
                                      removes + [f"{UNLINK}{int(h)}" for h in op.get("unlink", [])]))
    for op in plan["events"]:
        for f in event_files(romfs, op["file"]):
            event_ops[f].append(op)
    add_no_pose_entries(event_ops, romfs, warnings, plan, place_ops)
    return place_ops, event_ops, report, warnings


# LW Gift from Saria
# The cutscene creates the ocarina Link holds as a flowchart actor of its own (Dm_Kokiri_0155 Item_Ocarina_Fairy).
# Event100 joins the event, Event93 binds it to Link's Weapon_L and Event99 sends it offstage. With another item
# there, Link held the Fairy Ocarina while the window named the item (NX2-ZOOTR). So the actor becomes the
# item's actor when that's an item display (ActorParam parent Item_EventObject_Base). NX2-ZOOTR did this and saw
# Link hold the Boomerang in game. A progressive item's tier is only known in game, so the ocarina stays, and an
# ice trap keeps it too since the freeze follows.
SARIA_LOCATION, SARIA_FILE, SARIA_ACTOR = "event/Dm_Kokiri_0155/Item_Ocarina_Fairy", "Dm_Kokiri_0155", "Item_Ocarina_Fairy"


def saria_hand_ops(expanded, catalog, romfs, warnings):
    items = {(spec if isinstance(spec, str) else spec.get("item")) for rid, spec in expanded.items()
             if catalog[rid].get("location") == SARIA_LOCATION
             and not (isinstance(spec, dict) and (spec.get("call") or spec.get("progressive")))}
    items.discard(SARIA_ACTOR)
    if len(items) != 1:
        return []
    item = items.pop()
    rel = f"Pack/Actor/{item}.pack.zs"
    if not os.path.exists(os.path.join(romfs, rel)):
        return []
    files = sarc_files(Romfs(romfs, VANILLA).read(rel))
    param = files.get(f"Actor/{item}.engine__actor__ActorParam.bgyml")
    if param is None or not str(byml_load(param)[0].get("$parent", "")).endswith(
            "/Item_EventObject_Base.engine__actor__ActorParam.gyml"):
        return []
    warnings.append(f"LW Gift from Saria: Link holds {item} in the cutscene (its ocarina actor renamed)")
    return [{"flowchart": SARIA_FILE, "rename_actor": SARIA_ACTOR, "to": item}]


_FC_CACHE = {}


def _vanilla_fc(romfs, name):
    """The vanilla flowchart model the game reads for event file `name` (its newest version), or None."""
    key = (romfs, name)
    if name in NEW_EVENTS:  # a new scene file (NEW_EVENTS), its vanilla state is its source renamed
        op = NEW_EVENTS[name]
        data = Romfs(romfs, VANILLA).read(op["from"])
        return Evfl(rename_strings(data, op.get("rename", []), op["to"])).flowcharts[0]
    if key not in _FC_CACHE:
        try:
            rels = event_files(romfs, name)
        except PlanError:
            _FC_CACHE[key] = None
            return None
        newest = sorted(rels, key=lambda x: int((re.search(r"\.(\d{3})\.bfevfl", x) or [0, -1])[1]))[-1]
        _FC_CACHE[key] = Evfl(Romfs(romfs, VANILLA).read(newest)).flowcharts[0]
    return _FC_CACHE[key]


_POSE_MEMO = {}


def _hold_step(r, romfs):
    """Whether scene reward r's give step holds its item up (it reaches a hold-up with r's parameter)."""
    fc = _vanilla_fc(romfs, r["event_file"])
    e = next((x for x in (fc or {}).get("events", []) if x["name"] == r["event"]), None)
    return e is not None and progressive.step_poses(lambda n: _vanilla_fc(romfs, n), fc, e, r["param"], _POSE_MEMO)


_FILE_FC = {}


def _file_fc(romfs, rel, flowchart):
    """The vanilla flowchart `flowchart` of event file `rel` (that exact file), or None."""
    key = (romfs, rel)
    if key not in _FILE_FC:
        try:
            _FILE_FC[key] = Evfl(Romfs(romfs, VANILLA).read(rel))
        except (FileNotFoundError, OSError):
            _FILE_FC[key] = None
    ev = _FILE_FC[key]
    return next((x for x in (ev.flowcharts if ev else []) if x["name"] == flowchart), None)


def hold_rewrite(event_ops, romfs, warnings):
    """Every new step that would make Link hold up an actor he can't hold up as it is (config/hold_up.json "show" /
    "window") becomes that actor's hold-up instead, whichever plugin wrote it. A new step means a plan's graph
    node, so a call or a copy of a vanilla give step. The hold-up is progressive.hold_node, either its display's
    hold-up or the get window. The read-back (tools/rando/no_pose_check.py) finds any that slip through another
    way."""
    load = lambda n: _vanilla_fc(romfs, n)  # noqa: E731
    for f, ops in event_ops.items():
        base = os.path.basename(f).split(".")[0]
        for op in ops:
            if "add_graph" not in op:
                continue
            fc = _file_fc(romfs, f, op["flowchart"])
            by_name = {e["name"]: e for e in (fc or {}).get("events", [])}
            for lab, node in list(op["nodes"].items()):
                if "next" not in node or "cases" in node or "fork" in node:
                    continue
                values = dict(node.get("params") or {})
                callee = node.get("call")
                if "copy" in node:
                    src = by_name.get(node["copy"])
                    if src is None or src["type"] not in ("subflow", "subflow_switch"):
                        continue
                    if not callee:
                        callee = f"{src.get('flowchart') or ''}:{src['entry_point']}"
                    values = {k: v["value"] for k, v in (((src.get("params") or {}).get("items")) or {}).items()
                              if v.get("type") != "argument"}
                    values.update(node.get("params_over") or {})
                if not callee:
                    continue
                fcn, _, ep = callee.partition(":")
                if ((fcn or base), ep) == (progressive.SCRUB_FILE, progressive.SCRUB_SALE_SRC):
                    continue  # the scrubs' one-time sale gives these itself (scrub_intercept, below)
                for x in progressive.pose_args(load, fcn or base, ep, _POSE_MEMO):
                    v = values.get(x)
                    held = progressive.hold_node(v, node["next"], base) if isinstance(v, str) else None
                    if held:
                        op["nodes"][lab] = held
                        warnings.append(f"{base}: {op['add_graph']}_{lab} would hold up {v} ({callee}): "
                                        f"{held['call']} instead")
                        break


def scrub_intercept_ops(event_ops, romfs, warnings):
    """The Business Scrubs' one-time sale (Enemy_Scrub_Business_Common SimpleShopSub_Scrub_Business_OneTime) when
    it sells an item Link can't hold up as it is, or the ice-trap marker (progressive.ICE_MARKER,
    tools/rando/shops.py). Its hand-over gets the per-item intercept (progressive.scrub_intercept) inside the
    vanilla entry, so the scrub actor that entry binds stays bound."""
    holds = set(progressive.NO_POSE) | set(progressive.HOLD_SHOW) | set(progressive.HOLD_WINDOW)
    holds.add(progressive.ICE_MARKER)
    files = event_files(romfs, progressive.SCRUB_FILE)
    sold = set()
    ours = lambda v: v in holds or str(v).startswith(progressive.CALL_MARKERS)  # noqa: E731 (an entry to call: a
    # dungeon item's credit, a progressive item's tier entry, the bean pack's, a soul's; progressive.CALL_MARKERS)
    for f in files:
        for op in event_ops.get(f, []):
            if op.get("param") == "ActorName" and ours(op.get("value")):
                sold.add(op["value"])
            for node in (op.get("nodes") or {}).values():
                v = (node.get("params_over") or node.get("params") or {}).get("ActorName")
                if ours(v):
                    sold.add(v)
    if not sold:
        return
    for f in files:
        fc = _file_fc(romfs, f, progressive.SCRUB_FILE)
        entry, nodes, start, preds = progressive.scrub_intercept(fc, sold)
        event_ops[f].append({"flowchart": progressive.SCRUB_FILE, "add_graph": entry, "nodes": nodes, "start": start})
        for ev in preds:
            event_ops[f].append(dict(ev, flowchart=progressive.SCRUB_FILE, next=f"{entry}_{start}"))
    warnings.append(f"{progressive.SCRUB_FILE}: the one-time sale's hand-over gives {', '.join(sorted(sold))} "
                    f"itself ({progressive.SCRUB_INTERCEPT})")


def add_no_pose_entries(event_ops, romfs, warnings, plan=None, place_ops=None):
    """Adds the hold-up entries of config/hold_up.json and the ocarinas' give entries (tools/progressive.py
    hold_graphs) to their files, once, when any op calls them. The chest scenes, host and in-place scene gives,
    the plugins' own gives (progressive.host_graph / hold_node) and the scrub sales (tools/rando/shops.py) all
    call them by name.
    With `plan`, the "own" actors of config/hold_up.json that a scene step names get their hold-up animation
    (progressive.hold_up_ops, appended to the plan's "packs" and "byml"). The display actors ("displays") and
    the own actors' provided models that the plan names anywhere get built too (progressive.display_ops /
    own_model_ops, with new packs, rows and files appended to "new_files", "packs" and "byml")."""
    hold_rewrite(event_ops, romfs, warnings)
    scrub_intercept_ops(event_ops, romfs, warnings)
    names = set(progressive.HOLD_ENTRIES)
    called = set()
    for f, ops in event_ops.items():
        base = os.path.basename(f).split(".")[0]
        for op in ops:
            for node in (op.get("nodes") or {}).values():
                fcn, _, ep = str(node.get("call") or "").partition(":")
                if ep in names:
                    called.add((fcn or base, ep))
    if called:
        for file, graphs in progressive.hold_graphs(_vanilla_fc(romfs, progressive.HOLD_FILE)).items():
            for entry, nodes, start in graphs:
                for f in event_files(romfs, file):
                    if any(op.get("add_graph") == entry for op in event_ops[f]):
                        continue  # a plan that brings its own copy
                    event_ops[f].append({"flowchart": file, "add_graph": entry, "nodes": nodes, "start": start})
            warnings.append(f"{file}: hold-up entries {', '.join(e for e, _, _ in graphs)} (items Link can't hold "
                            f"up as they are, config/hold_up.json)")
    if plan is not None:  # only when a scene step of this plan names one, a plan that leaves them alone writes nothing
        text = json.dumps([op for ops in event_ops.values() for op in ops], default=str)
        own = sorted(a for a in progressive.HOLD_OWN if f'"{a}"' in text)
        fs = Romfs(romfs, VANILLA)
        read_pack = lambda rel: sarc_files(fs.read(rel))  # noqa: E731
        read_rows = lambda table: {row["__RowId"]: row for row in byml_load(fs.read(table))[0]}  # noqa: E731
        if own:
            packs, byml = progressive.hold_up_ops(own, read_pack, lambda: read_rows(progressive.ACTOR_INFO), romfs)
            plan["packs"] += packs
            plan["byml"] += byml
            warnings.append(f"hold-up animation added to {', '.join(own)} (config/hold_up.json own)")
        # Build the display actors (config/hold_up.json) and the supplied models for "own" actors
        # (parity/_show_models.py) when the patch can show them. That covers hold-ups, chest contents, ground
        # looks at their create step and Treasure Chest Game previews.
        # Reward references come from event_ops and place_ops, so vanilla rewards still write no files
        # (tools/selftest.py step 3).
        whole = json.dumps({k: v for k, v in plan.items() if not k.startswith("_") and k != "rewards"},
                           default=str) + text + json.dumps(place_ops or {}, default=str)
        named = sorted(a for a in progressive.HOLD_OWN if f'"{a}"' in whole)
        def add(built):  # several displays can share a file (like _show_models.py's glow mask), write it once
            for k in ("packs", "byml"):
                plan[k] += built[k]
            have = {op["to"]: op for op in plan["new_files"]}
            for op in built["new_files"]:
                if op["to"] not in have:
                    plan["new_files"].append(op)
                    have[op["to"]] = op
                elif have[op["to"]] != op:
                    raise PlanError(f"two different new files for {op['to']}")

        built = progressive.own_model_ops(named, read_pack, read_rows, romfs)
        if built["packs"]:
            add(built)
            warnings.append(f"own-route models from parity/{progressive.SHOW_MODELS}.py: "
                            f"{', '.join(sorted({op['pack'].split('/')[-1][:-8] for op in built['packs']}))}")
        shown = sorted(d for d in progressive.HOLD_DISPLAYS if f'"{d}"' in whole)
        ctx = plan.get("_show_models") or {}  # the seed's Ocarina controls and controller (an Ocarina button's label)
        for d in shown:
            if not progressive.display_available(d, romfs, ctx):
                raise PlanError(f"{d}: named by the plan but has no model (config/hold_up.json displays, "
                                f"parity/{progressive.SHOW_MODELS}.py)")
            add(progressive.display_ops(d, read_pack, read_rows, romfs, ctx))
        if shown:
            warnings.append(f"display actors built (config/hold_up.json displays): {', '.join(shown)}")


def set_path(actor, dotted, value):
    keys = dotted.split(".")
    node = actor
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    old = node.get(keys[-1])
    node[keys[-1]] = value
    return old


UNLINK = "Links@Dst="  # a placement "remove" entry taking out the one link to that hash (plan "unlink")
TWIN_OF = "@twin_of"  # in a placement op's sets: the op makes a new actor, a copy of this hash (plan "twin")
ADD_LINKS = "@add_links"  # in a placement op's sets, copies of its links to "like" ending at "dst" (plan "add_links").
#                          With "name", only its link of that Name to "like" where it has several
NO_GROUPS = "@no_groups"  # in a twin op's sets: the twin joins none of its source's actor groups (plan "join_groups")
RELINK = "@relink"  # in a twin op's sets, {old end: new end} for its copied links (plan "relink", a shop keeper's twin)
# in a twin op's sets: the twin keeps its source's Phive placement ID (plan "keep_phive_id"). Every placed actor's ID is
# its hash and keys its entry in the area's Phive/StaticCompoundBody, where a crate's, bush's or icicle's collision is
# baked. A copy under a new ID has no entry (drops.BAKED_TYPES).
KEEP_PHIVE_ID = "@keep_phive_id"
# A plan "groups" entry {"file", "logic", "hash", "references": [{"id", "reference"}], "spawn_group"} adds a logic
# group (AiGroups) that runs that module on those placements of the level file. Each module node finds its actor by
# the Id its InstanceName names. With "spawn_group" it also adds one FarDeleteGroups and one SimultaneousGroups entry
# holding exactly them, which is the shape of a vanilla prefab instance (e.g. Gerudo Valley's Area +
# EventRequestActor group). It gets a plan section of its own and not "placements", whose ops each name an actor
# hash. In place_ops it stands as (ADD_GROUP, spec, []).
# A "groups" entry {"file", "rebind": {"reference": hash, "from": instance, "to": instance}} binds that placement to
# another actor node of the module it already runs instead. Its one AiGroups reference whose Id is "from" gets Id
# "to", and its Path's last part becomes "to" (chest_flags.trap_rebind_ops, for a trap-chest spot made a plain chest).
ADD_GROUP = "@add_group"


def remove_path(actor, dotted):
    if dotted.startswith(UNLINK):
        dst = int(dotted[len(UNLINK):])
        links = actor.get("Links") or []
        keep = [ln for ln in links if int(ln.get("Dst", -1)) != dst]
        if len(keep) != len(links) - 1:
            raise PlanError(f"{actor.get('Gyaml')} {actor.get('Hash')}: {len(links) - len(keep)} links to {dst}, "
                            f"not one")
        if keep:
            actor["Links"] = keep
        else:
            actor.pop("Links", None)  # like vanilla actors without links, no key
        return
    keys = dotted.split(".")
    node = actor
    for k in keys[:-1]:
        node = node.get(k) or {}
    node.pop(keys[-1], None)


ACTOR_PARAMS = None


def patch_placement(data, ops, rel):
    import copy
    root, ver = byml_load(data)
    by_hash = {str(a.get("Hash")): a for a in root.get("Actors", [])}
    touched = []
    new_groups = [sets for h, sets, _ in ops if h == ADD_GROUP]  # added last, once every twin is in the file
    ops = [o for o in ops if o[0] != ADD_GROUP]
    deleted = {h for h, sets, _ in ops if sets is None}
    # twins first, from the actors as this (vanilla) file has them, each a copy without links under its new hash
    twins = [(h, sets, removes) for h, sets, removes in ops if sets is not None and TWIN_OF in sets]
    ops = [o for o in ops if o[1] is None or TWIN_OF not in o[1]]
    made = []
    for h, sets, removes in twins:
        src = by_hash.get(sets[TWIN_OF])
        if src is None:
            raise PlanError(f"{rel}: twin {h}: no actor with hash {sets[TWIN_OF]}")
        if h in by_hash or h in {m_[0] for m_ in made}:
            raise PlanError(f"{rel}: twin {h}: the hash is taken")
        if sets[TWIN_OF] in deleted:
            raise PlanError(f"{rel}: twin {h}: its source {sets[TWIN_OF]} is deleted")
        a = copy.deepcopy(src)
        for ln in a.get("Links") or []:  # its links, from itself
            if str(ln.get("Src")) == sets[TWIN_OF]:
                ln["Src"] = U64(int(h))
        a["Hash"] = U64(int(h))
        if isinstance((a.get("Phive") or {}).get("Placement"), dict) and "ID" in a["Phive"]["Placement"] and \
                not sets.get(KEEP_PHIVE_ID):
            a["Phive"]["Placement"]["ID"] = U64(int(h))
        for old_end, new_end in (sets.get(RELINK) or {}).items():
            hits = [ln for ln in a.get("Links") or [] if str(ln.get("Dst")) == str(old_end)]
            if not hits:
                raise PlanError(f"{rel}: twin {h}: relink {old_end}: its source has no link to it")
            for ln in hits:
                ln["Dst"] = U64(int(new_end))
        for want in sets.get(ADD_LINKS) or []:
            if any(str(ln.get("Dst")) == str(want["dst"]) for ln in a.get("Links") or []):
                raise PlanError(f"{rel}: twin {h}: add_links: already links {want['dst']}")
            kind = want.get("name", "Reference")
            a["Links"] = (a.get("Links") or []) + [{"Gyaml": kind, "Name": kind, "Src": U64(int(h)),
                                                     "Dst": U64(int(want["dst"]))}]
        for k in removes:
            remove_path(a, k)
        for k, v in sets.items():
            if k not in (TWIN_OF, NO_GROUPS, KEEP_PHIVE_ID, RELINK, ADD_LINKS):
                set_path(a, k, v)
        made.append((h, a, None if sets.get(NO_GROUPS) else sets[TWIN_OF]))
    for h, sets, removes in ops:
        a = by_hash.get(h)
        if a is None:
            raise PlanError(f"{rel}: no actor with hash {h}")
        if sets is None:
            continue  # deleted below
        if h in deleted:
            raise PlanError(f"{rel}: actor {h} is both deleted and edited")
        for k in removes:
            remove_path(a, k)
        for k, v in sets.items():
            if k == ADD_LINKS:
                for want in v:
                    links = a.get("Links") or []
                    if want.get("like") is None:  # a plain Reference link like vanilla ones (e.g. a cow's to Malon)
                        if any(str(ln.get("Dst")) == str(want["dst"]) for ln in links):
                            raise PlanError(f"{rel}: {h}: add_links {want}: already links {want['dst']}")
                        a["Links"] = links + [{"Gyaml": "Reference", "Name": "Reference", "Src": U64(int(h)),
                                               "Dst": U64(int(want["dst"]))}]
                        continue
                    like = [ln for ln in links if str(ln.get("Dst")) == str(want["like"])
                            and ("name" not in want or ln.get("Name") == want["name"])]  # ("name" picks the one link
                    # of several to "like", e.g. a shopkeeper's ForSale and Reference links to one shelf item)
                    if len(like) != 1 or any(str(ln.get("Dst")) == str(want["dst"]) and
                                             ("name" not in want or ln.get("Name") == want["name"]) for ln in links):
                        raise PlanError(f"{rel}: {h}: add_links {want}: {len(like)} links to {want['like']}")
                    new_ln = copy.deepcopy(like[0])
                    new_ln["Dst"] = U64(int(want["dst"]))
                    links.append(new_ln)
                continue
            if k == "Hash":
                v = U64(int(v))
            set_path(a, k, v)
        touched.append(a)
    # An actor given a setting it doesn't accept stops the game loading the rest of the level.
    for a in touched:
        bad = set((a.get("Dynamic") or {}).keys()) - ACTOR_PARAMS.allowed(a.get("Gyaml", ""))
        if bad:
            raise PlanError(f"{rel}: {a.get('Gyaml')} (hash {a.get('Hash')}) does not accept {sorted(bad)}; "
                            f"the game would stop loading this level's objects there")
    if deleted:
        # a deleted actor must not be anything else's link or logic reference in this file
        for a in root.get("Actors", []):
            if str(a.get("Hash")) in deleted:
                continue
            for link in a.get("Links") or []:
                for end in ("Src", "Dst"):
                    if str(link.get(end)) in deleted:
                        raise PlanError(f"{rel}: can't delete {link.get(end)}: {a.get('Gyaml')} {a.get('Hash')} "
                                        f"links to it")
        for g in root.get("AiGroups") or []:
            for ref in g.get("References") or []:
                if str(ref.get("Reference")) in deleted:
                    raise PlanError(f"{rel}: can't delete {ref.get('Reference')}: logic {g.get('Logic')} uses it")
        for grp in ("FarDeleteGroups", "SimultaneousGroups"):
            for members in root.get(grp) or []:
                if any(str(x) in deleted for x in members):
                    raise PlanError(f"{rel}: can't delete a member of {grp}")
        root["Actors"] = [a for a in root["Actors"] if str(a.get("Hash")) not in deleted]
    for h, a, s in made:
        bad = set((a.get("Dynamic") or {}).keys()) - ACTOR_PARAMS.allowed(a.get("Gyaml", ""))
        if bad:
            raise PlanError(f"{rel}: twin {h} ({a.get('Gyaml')}) does not accept {sorted(bad)}")
        for link in a.get("Links") or []:  # its links (copied from its source) can't end at a deleted actor
            if str(link.get("Dst")) in deleted:
                raise PlanError(f"{rel}: twin {h} links to {link.get('Dst')}, which this plan deletes")
        # a twin takes its source's place in the level's actor groups (deleted far away, spawned together), since
        # only one of the two is ever there. Unless the op says "join_groups": false, then s is None and it's a new
        # actor on its own
        for grp in ("FarDeleteGroups", "SimultaneousGroups"):
            for members in (root.get(grp) or []) if s is not None else []:
                same = [x for x in members if str(x) == s]
                if same and not any(str(x) == h for x in members):
                    members.append(type(same[0])(int(h)))
        root["Actors"].append(a)
    for g in new_groups:
        if "rebind" in g:
            _rebind_logic_ref(root, g["rebind"], rel)
        else:
            _add_logic_group(root, g, rel, deleted)
    return byml_dump(root, ver)


def _rebind_logic_ref(root, spec, rel):
    """A plan "groups" "rebind" entry (ADD_GROUP above). The placement's one AiGroups reference naming instance
    spec["from"] gets renamed to spec["to"], in its Id and the last part of its Path."""
    hits = [ref for g in root.get("AiGroups") or [] for ref in g.get("References") or []
            if str(ref.get("Reference")) == str(spec["reference"]) and ref.get("Id") == spec["from"]]
    if len(hits) != 1:
        raise PlanError(f"{rel}: rebind {spec}: {len(hits)} logic references, not one")
    ref = hits[0]
    head, _, last = str(ref.get("Path", "")).rpartition("/")
    if last != spec["from"]:
        raise PlanError(f"{rel}: rebind {spec}: its Path {ref.get('Path')} doesn't end in {spec['from']}")
    ref["Id"] = spec["to"]
    ref["Path"] = f"{head}/{spec['to']}" if head else spec["to"]


def _add_logic_group(root, spec, rel, deleted):
    """A plan "groups" entry (ADD_GROUP above). Adds a new AiGroups entry, and with "spawn_group" also one
    FarDeleteGroups and one SimultaneousGroups entry holding exactly its references, like every vanilla prefab
    instance of such a module."""
    h = str(spec.get("hash", ""))
    refs = spec.get("references") or []
    logic = spec.get("logic") or ""
    if not h.isdigit() or not refs or not logic.startswith("Logic/Module/") or not logic.endswith(".logic.module.ain"):
        raise PlanError(f"{rel}: add_group {spec}: needs a hash, references and a Logic/Module/... .ain path")
    have = {str(a.get("Hash")) for a in root.get("Actors", [])}
    if h in have or any(str(g.get("Hash")) == h for g in root.get("AiGroups") or []):
        raise PlanError(f"{rel}: add_group {h}: the hash is taken")
    ids = [r["id"] for r in refs]
    if len(set(ids)) != len(ids):
        raise PlanError(f"{rel}: add_group {h}: an Id twice ({ids})")
    for r in refs:
        if str(r["reference"]) not in have or str(r["reference"]) in deleted:
            raise PlanError(f"{rel}: add_group {h}: {r['id']} -> {r['reference']}, no such actor in the file")
    if AINB_FS is not None:  # the module the group runs is a game file (Logic/<name>.logic.module.ainb)
        try:
            AINB_FS.raw("Logic/" + logic.rsplit("/", 1)[-1] + "b")
        except (OSError, KeyError) as ex:
            raise PlanError(f"{rel}: add_group {h}: no module file for {logic} ({ex})")
    groups = root.setdefault("AiGroups", [])
    groups.append({"Logic": logic, "Hash": U64(int(h)),
                   "References": [{"Id": r["id"], "Path": r.get("path", r["id"]), "Reference": U64(int(r["reference"]))}
                                  for r in refs]})
    if spec.get("spawn_group"):
        for grp in ("FarDeleteGroups", "SimultaneousGroups"):
            members = [U64(int(r["reference"])) for r in refs]
            if any(set(map(str, m)) & set(map(str, members)) for m in root.get(grp) or []):
                raise PlanError(f"{rel}: add_group {h}: a reference is already in a {grp} entry")
            root.setdefault(grp, []).append(members)


def find_param(container, path):
    node = container
    for k in path.split("."):
        if not node or node["type"] != "container" or k not in node["items"]:
            return None
        node = node["items"][k]
    return node


def _event_param(ev_model, op, rel):
    flows = {fc["name"]: fc for fc in ev_model.flowcharts}
    fc = flows.get(op["flowchart"])
    if fc is None:
        raise PlanError(f"{rel}: no flowchart {op['flowchart']}")
    names = {e["name"]: e for e in fc["events"]}
    e = names.get(op["event"])
    if e is None:
        raise PlanError(f"{rel}: no event {op['event']} in {op['flowchart']}")
    c = find_param(e.get("params"), op["param"]) if "param" in op else None
    if "param" in op and c is None:
        raise PlanError(f"{rel}: {op['event']} has no parameter {op['param']}")
    return fc, names, e, c


def _param_owners(ev):
    """{address of a parameter block or value: {(flowchart, event)} whose parameters reach it}. A copied step
    ({"copy": ...} in an add_graph) points at its original's block, and a params_over copy points its unchanged
    values at the original's, so those addresses have two owners."""
    owners = defaultdict(set)

    def walk(node, who):
        if node:
            owners[node["@"]].add(who)
            for child in (node.get("items") or {}).values():
                walk(child, who)
    for fc in ev.flowcharts:
        for e in fc["events"]:
            walk(e.get("params"), (fc["name"], e["name"]))
    return owners


def _own_value(node, rel, where):
    """A copied step's own copy of one parameter (params_over value) from the original's model."""
    t = node["type"]
    if t in ("int", "float", "string", "float_array"):
        return node["value"]
    if t == "bool":
        return bool(node["value"])
    if t == "argument":
        return {"arg": node["value"]}
    raise PlanError(f"{rel}: {where} is a {t} parameter; a copied step can't keep its own copy of it")


def unshare_copies(ops, probe, rel):
    """Copy-on-write for copied steps, so a parameter edit only changes the step it names. An edit on a copied step
    becomes that copy's own value (params_over). An edit on a step the plan copies first gives each copy its own
    copy of the old value. Only parameters an op edits get separated, so a plan with no such edit builds the same
    bytes as before. Returns the ops left to apply, since a copied step's edits are folded into its node."""
    ops = [dict(op, nodes={k: dict(v) for k, v in op["nodes"].items()}) if "add_graph" in op else op for op in ops]
    copies, copies_of, new = {}, defaultdict(list), {}
    for op in ops:
        if "add_graph" in op:
            for lab, n in op["nodes"].items():
                if "copy" in n:
                    copies[(op["flowchart"], f"{op['add_graph']}_{lab}")] = n
                    copies_of[(op["flowchart"], n["copy"])].append(n)
                elif n.get("params"):
                    new[(op["flowchart"], f"{op['add_graph']}_{lab}")] = n
    out = []
    for op in ops:
        if "param" not in op or "add_graph" in op or "add_entry" in op:
            out.append(op)
            continue
        top, _, rest = op["param"].partition(".")
        key = (op["flowchart"], op["event"])
        if key in new and not rest:  # a step this plan adds with its own parameters, its value is set at build
            new[key]["params"] = dict(new[key]["params"], **{top: op["value"]})
            continue
        if key in copies:  # the copy's own value goes into its node and the original keeps its own
            if rest:
                raise PlanError(f"{rel}: {op['event']} is a copied step; its nested parameter {op['param']} "
                                f"can't be given a value of its own")
            n = copies[key]
            n["params_over"] = dict(n.get("params_over") or {}, **{top: op["value"]})
            continue
        if op.get("with_copies"):  # the copies take the new value too, unless they already have one of their own
            if rest:
                raise PlanError(f"{rel}: {op['event']} {op['param']}: with_copies is for a top-level parameter")
            for n in copies_of.get(key, ()):
                if top not in (n.get("params_over") or {}):
                    n["params_over"] = dict(n.get("params_over") or {}, **{top: op["value"]})
            out.append(op)
            continue
        for n in copies_of.get(key, ()):  # the copies keep the value the original had
            if top in (n.get("params_over") or {}):
                continue
            node = find_param(_event_param(probe, dict(op, param=top), rel)[2].get("params"), top)
            if node["type"] in ("string", "argument") and not rest and "params_over" in n:
                continue  # a text edit repoints the original's block, and this copy has a block of its own
            n["params_over"] = dict(n.get("params_over") or {}, **{top: _own_value(node, rel, f"{op['event']} {top}")})
        out.append(op)
    return out


def check_unshared(data, ops, rel):
    """No parameter edit of the plan may land on a value another step also reads. A number is edited in place, so
    its value has to belong to the named step alone. A text edit repoints its block's slot, so the block has to
    belong to it alone as well."""
    ev = Evfl(data)
    owners = _param_owners(ev)
    for op in ops:
        if "param" not in op or "add_graph" in op or "add_entry" in op:
            continue
        fc, names, e, c = _event_param(ev, op, rel)
        parent = e.get("params")
        for k in op["param"].split(".")[:-1]:
            parent = parent["items"][k]
        node = c if c["type"] not in ("string", "argument") else parent
        others = sorted(f"{f}:{n}" for f, n in owners.get(node["@"], ()) if (f, n) != (op["flowchart"], op["event"]))
        if others:
            raise PlanError(f"{rel}: {op['event']} {op['param']} shares its value with {', '.join(others)}: "
                            f"the edit would change them too")


def patch_event(data, ops, rel):
    # Strings sit right after the parameter, so for a text edit the builder writes a new parameter.
    # Numbers, booleans and routes get edited in place.
    probe = Evfl(data)
    ops = unshare_copies(ops, probe, rel)
    chains = [op for op in ops if "add_entry" in op or "add_graph" in op]
    text_edits = [op for op in ops if op not in chains and "param" in op
                  and _event_param(probe, op, rel)[3]["type"] in ("string", "argument")]
    if chains or text_edits:
        b = EvflBuilder(data)
        for op in chains:
            try:
                fc = b.flowchart(op["flowchart"])
            except KeyError:
                raise PlanError(f"{rel}: no flowchart {op['flowchart']}")
            name = op.get("add_entry") or op["add_graph"]
            if name in fc["entry_points"]:
                raise PlanError(f"{rel}: entry point {name} already exists")
            if "add_graph" in op:
                b.add_graph(fc, name, op["nodes"], op["start"])
            else:
                b.add_chain(fc, name, op["steps"])
        for op in text_edits:
            c = _event_param(b.ev, op, rel)[3]
            if c["value"] != op["value"] or (op.get("as_string") and c["type"] == "argument"):
                b.set_string_param(c, op["value"], as_string=bool(op.get("as_string")))
        data = b.build()
        # every built scene file must read back whole and follow Nintendo's relocation rule
        built = Evfl(data)
        unlisted = built.check()[1]
        bad = built.relt_rule_violations()
        if unlisted or bad:
            raise PlanError(f"{rel}: the rebuilt scene file is malformed ({len(unlisted)} unlisted pointers, "
                            f"{len(bad)} relocation-rule breaks, e.g. {bad[:2]}); nothing written")
    ed = EvflEditor(data)
    for op in ops:
        if op in chains or op in text_edits:
            continue
        if "rename_actor" in op:  # a flowchart actor becomes another actor type (its steps and parameters kept)
            fc = next((x for x in ed.ev.flowcharts if x["name"] == op["flowchart"]), None)
            a = next((x for x in (fc or {}).get("actors", []) if x["name"] == op["rename_actor"]
                      and not x["sub_name"]), None)
            if a is None:
                raise PlanError(f"{rel}: no actor {op['rename_actor']} in {op['flowchart']}")
            ed.set_string(a["@"], op["to"])
            continue
        if "entry" in op:  # point an entry point at another step
            fc = next((x for x in ed.ev.flowcharts if x["name"] == op["flowchart"]), None)
            ep = (fc or {}).get("entry_points", {}).get(op["entry"])
            target = next((x for x in (fc or {}).get("events", []) if x["name"] == op["next"]), None)
            if ep is None or target is None:
                raise PlanError(f"{rel}: no entry point {op['entry']} or step {op['next']} in {op['flowchart']}")
            ed.set_u16(ep["@"] + 0x1C, target["idx"])
            continue
        fc, names, e, c = _event_param(ed.ev, op, rel)
        if c is not None:
            v = op["value"]
            if c["type"] == "int":
                ed.set_int(c["slot"], int(v))
            elif c["type"] == "float":
                ed.set_float(c["slot"], float(v))
            elif c["type"] == "bool":
                struct.pack_into("<I", ed.buf, c["slot"], 0x80000001 if v else 0)  # the game stores true as 0x80000001
            elif c["type"] == "float_array":
                if len(v) != len(c["value"]):
                    raise PlanError(f"{rel}: {op['param']} has {len(c['value'])} numbers, got {len(v)}")
                for k, f in enumerate(v):
                    ed.set_float(c["slot"] + 4 * k, float(f))
            else:
                raise PlanError(f"{rel}: parameter {op['param']} is a {c['type']}, not editable here")
        if "next" in op:
            target = {"idx": 0xFFFF} if op["next"] is None else names.get(op["next"])  # None: the end
            if target is None:
                raise PlanError(f"{rel}: no event {op['next']}")
            if "case" in op:
                ed.set_u16(e["cases"][op["case"]]["@"] + 4, target["idx"])
            elif "fork" in op:
                ed.set_u16(ed.ev.ptr(e["@"] + 0x10) + 2 * op["fork"], target["idx"])
            elif "next" in e:
                ed.set_u16(e["@"] + 0x0A, target["idx"])
            else:
                raise PlanError(f"{rel}: {op['event']} ({e['type']}) has no single next; give a case")
    check_unshared(bytes(ed.buf), ops, rel)
    # The game uses each entry point's sub-flow list to bind scene actors, so rebuild it for the new calls.
    # Without sync_sub_flows (tools/evfl_build.py) the heart scene froze and crashed.
    try:
        return sync_sub_flows(ed.build())
    except ValueError as e:
        raise PlanError(f"{rel}: {e}")


def trade_slot_stage(plan, romfs, event_ops, warnings):
    """The event patcher for this plan. That's patch_event, and with a "trade_slot" section (tools/trade_slot.py,
    the trade button's picker and owned record from the songs/trade plugin) also its hooks on each event file as
    patched. Those go one site at a time (trade_slot.stage2_next), so they land on the steps the way every other
    edit left them. Adds the files with trade checks, hand-ins or timed removals (and ShowItem) to `event_ops` so
    they all get patched."""
    if not plan.get("trade_slot"):
        return patch_event
    sp = trade_slot.plan_spec(plan["trade_slot"])  # the plan names order and mode, flags and steps are today's data
    fs = Romfs(romfs, VANILLA)
    cache = {}

    def load_fc(name):  # another file's flowchart, vanilla (deciding whether a check leads to a hand-in)
        if name not in cache:
            try:
                rel = event_files(romfs, name)[-1]
                cache[name] = next((f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == name), None)
            except (PlanError, OSError, ValueError):
                cache[name] = None
        return cache[name]
    for base in trade_slot.files(sp):
        for rel in event_files(romfs, base):
            event_ops.setdefault(rel, [])
    counts = defaultdict(int)

    def patcher(data, ops, rel):
        new = patch_event(data, ops, rel)
        base = os.path.basename(rel).split(".")[0]
        for _ in range(500):
            try:
                batch = trade_slot.stage2_next(Evfl(new), base, sp, load_fc)
            except ValueError as e:
                raise PlanError(f"{rel}: trade button: {e}")
            if not batch:
                return new
            counts[rel] += 1
            new = patch_event(new, batch, rel)
        raise PlanError(f"{rel}: trade button: more than 500 hooks")
    warnings.append("trade button: " + ("picker and owned record hooked" if sp["picker"] else
                                        "Biggoron's timed removals take the timed item by name") + " (tools/trade_slot.py)")
    return patcher


EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
ANALYZED = "RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs"


def entry_links(ev, entry):
    """(scenes handed off to with EventTransition, cross-file calls as (file, entry)) reachable from an entry
    point within one scene file, following same-file sub-flow calls. entry=None means every entry point."""
    fc = ev.flowcharts[0]
    eps = fc["entry_points"]
    starts = [eps[entry]["main"]] if entry in eps else ([] if entry else [ep["main"] for ep in eps.values()])
    hands, calls, seen, stack = set(), set(), set(), list(starts)
    while stack:
        i = stack.pop()
        if i in seen or i >= len(fc["events"]):
            continue  # 0xFFFF = end
        seen.add(i)
        e = fc["events"][i]
        if e["type"] == "action" and fc["actors"][e["actor"]]["actions"][e["action"]] == "EventTransition":
            v = ((e.get("params") or {}).get("items") or {}).get("EventName")
            if v and v.get("value"):
                hands.add(v["value"])
        if e["type"] in ("subflow", "subflow_switch"):
            if e.get("flowchart"):
                calls.add((e["flowchart"], e.get("entry_point")))
            elif e.get("entry_point") in eps:
                stack.append(eps[e["entry_point"]]["main"])
        if e["type"] == "type6":  # a return step, its field is a value and not a next step
            continue
        stack += [e[k] for k in ("next", "join") if k in e]
        stack += [c["next"] for c in e.get("cases", [])] + e.get("forks", [])
    return hands, calls


def scene_links(ev, entry):
    """Hand-offs and called scene files reachable from an entry point within one file (see entry_links)."""
    hands, calls = entry_links(ev, entry)
    return hands, {f for f, _ in calls}


def scene_closure(load, file, entry):
    """(hand-offs, scene files called) reachable from file:entry, following calls into other files.
    Nintendo's precomputed lists match this for 2,161 (files) and 2,284 (hand-offs) of 2,319 scene IDs."""
    hands, files, seen, stack = set(), set(), set(), [(file, entry)]
    while stack:
        f, ep = stack.pop()
        if (f, ep) in seen:
            continue
        seen.add((f, ep))
        ev = load(f)
        if ev is None:
            continue
        h, calls = entry_links(ev, ep)
        hands |= h
        for cf, cep in calls:
            files.add(cf)
            stack.append((cf, cep))
    return hands, files


def sync_scene_info(fs, romfs, patched_events, rewired, warnings):
    """The precomputed scene-info table lists, per scene ID, the scenes it hands off to (ChildEventList) and the
    scene files its steps call (SubFlowList), and the game loads those with the scene. Nintendo's tools keep
    them in step with the scene files, so we keep them in step with our edits:
    - scene IDs whose scene file we edited get what the edit adds or removes
    - scene IDs the plan points at another scene (rewired: {ID: (copy_of, file, entry)}) get the source ID's
      lists plus everything the new entry reaches
    Nothing Nintendo listed gets removed unless our edit removed it. Returns "set" ops for ANALYZED."""
    rows = byml_load(fs.read(EVENT_SETTING))[0]
    info = {r["__RowId"]: r for r in byml_load(fs.read(ANALYZED))[0]}
    vanilla_cache, patched_cache = {}, {}

    def loader(patched):
        cache = patched_cache if patched else vanilla_cache

        def load(name):
            if name not in cache:
                if patched and name in patched_events:
                    cache[name] = Evfl(patched_events[name][1])
                elif name in NEW_EVENTS:  # a new scene file has no vanilla version
                    cache[name] = Evfl(patched_events[name][1]) if name in patched_events else None
                else:
                    try:
                        rels = event_files(romfs, name)
                    except PlanError:
                        rels = []  # a called scene file the game doesn't have, nothing to follow
                    newest = [r for r in rels if re.search(r"\.\d{3}\.bfevfl", r)] or rels
                    cache[name] = Evfl(fs.read(newest[0])) if newest else None
            return cache[name]
        return load

    def put(rid, key, new_list, cur):
        if new_list != cur and (new_list or cur):
            ops.append({"set": {f"[__RowId={rid}].{key}": new_list}})
            warnings.append(f"scene ID {rid}: precomputed {'hand-off' if key == 'ChildEventList' else 'called-file'} "
                            f"list {cur} -> {new_list}")

    ops = []
    for rid, (copy_of, fcn, ep) in rewired.items():
        h, f = scene_closure(loader(True), fcn, ep)
        src = info.get(copy_of) or {}
        put(rid, "ChildEventList", scene_order(set(src.get("ChildEventList") or []) | h),
            list(src.get("ChildEventList") or []))
        put(rid, "SubFlowList", scene_order(set(src.get("SubFlowList") or []) | f), list(src.get("SubFlowList") or []))
    for r in rows:
        rid = r["__RowId"]
        fcn = (r.get("FlowchartFileName") or "").rsplit("/", 1)[-1].replace(".evfc", "")
        if rid in rewired or rid not in info:
            continue
        # Check the scene file and the calls in its vanilla list, because an edited callee can reach a new file.
        # The gamedb audit found this in Malon's race talk and Dm_LostWood_0015, which both reached ShowItem for
        # the hold-up. Missing list entries can crash the game.
        if fcn not in patched_events and not set(info[rid].get("SubFlowList") or []) & set(patched_events):
            continue
        (ha, fa), (hb, fb) = (scene_closure(loader(p), fcn, r.get("EntryPointName")) for p in (False, True))
        for key, old, new in (("ChildEventList", ha, hb), ("SubFlowList", fa, fb)):
            if old == new:
                continue
            cur = list(info[rid].get(key) or [])
            kept = [x for x in cur if x not in old - new]
            put(rid, key, scene_order(set(kept) | (new - old)), cur)
    # Log when a scene kept from boot (Dm_SY_Get, Dm_SY_Get_WithoutPlayer, etc.) calls outside its vanilla list.
    # Stale entry-point sub-flow lists froze the game, and patch_event syncs those now (checked in game).
    # Heart-spot items given through Dm_SY_GetInEvent, outside Dm_SY_Get's vanilla list, worked fine up to
    # the trap.
    bad = []
    for rid, fcn in resident_scenes(fs, rows):
        if fcn not in patched_events:
            continue
        reached = {}
        for patched in (False, True):
            ev = loader(patched)(fcn)
            reached[patched] = set()
            for ep in ((ev.flowcharts[0].get("entry_points") or {}) if ev is not None and ev.flowcharts else {}):
                reached[patched] |= scene_closure(loader(patched), fcn, ep)[1]
        allowed = set((info.get(rid) or {}).get("SubFlowList") or []) | {fcn}
        extra = (reached[True] - reached[False]) - allowed
        if extra:
            bad.append(f"{fcn} (resident scene {rid}) now reaches {sorted(extra)}")
    for b in bad:
        print(f"  note: resident scene calls a file outside its vanilla list: {b}")
    return ops


RESIDENT_LIST = "Event/ResidentEventList/Default.engine__event__ResidentEventList.bgyml"


def resident_scenes(fs, rows):
    """[(scene ID, scene file)] of the resident events (Event/ResidentEventList: loaded at boot and kept)."""
    by_id = {r["__RowId"]: r for r in rows}
    out = []
    for e in byml_load(fs.raw(RESIDENT_LIST))[0].get("GlobalResidentEventList", []):
        rid = e["EventName"].rsplit("/", 1)[-1].split(".")[0]
        fcn = ((by_id.get(rid) or {}).get("FlowchartFileName") or "").rsplit("/", 1)[-1].replace(".evfc", "")
        if fcn:
            out.append((rid, fcn))
    return out


def scene_order(names):
    """A scene-info list in the game's order, which is case-insensitive (every one of the 994 SubFlowLists and 149
    ChildEventLists in the vanilla table). Python's case-sensitive sort disagrees there (Get_StoneOfWater <
    GetPouchContent). With Dm_SY_GetInEvent appended to the end of Dm_SY_Get's list, the game ran the called
    scene's steps with none of its actors bound (three null calls) and every disguised ice trap froze the game."""
    return sorted(set(names), key=lambda s: (s.lower(), s))


def check_scene_order(rows):
    """Names of scene-info rows whose lists aren't in the game's order (refused, see scene_order)."""
    return [f"{r['__RowId']}.{k}" for r in rows for k in ("SubFlowList", "ChildEventList")
            if (r.get(k) or []) != scene_order(r.get(k) or [])]


def _same_value(got, want):
    """Whether an AINB value read back equals the one written. Floats (alone or in a vec3) are compared the way
    the file stores them, 32-bit."""
    if isinstance(got, list):
        return isinstance(want, (list, tuple)) and len(got) == len(want) and all(map(_same_value, got, want))
    if isinstance(got, float):
        return round(got, 5) == round(float(want), 5)
    return got == type(got)(want)


def _typed_like(old, new):
    for t in (U32, U64, I64, F64):
        if isinstance(old, t):
            return t(new)
    if isinstance(old, float) and not isinstance(new, float):
        return float(new)
    if isinstance(old, list) and isinstance(new, list) and old:  # a list of any length, typed like the old one
        return [_typed_like(old[0], v) for v in new]
    if isinstance(old, dict) and isinstance(new, dict):  # a whole entry, each value typed like the old entry's
        return {k: _typed_like(old.get(k), v) for k, v in new.items()}
    return new


def _path_tokens(path):
    # "a.b.0.c" and "[__RowId=X].Field" (select the list element whose field equals X)
    return re.findall(r"\[[^\]]*\]|[^.\[\]]+", path)


def _key(node, tok):
    """A path token as the dictionary's key. Hash-keyed dictionaries (HashDict) use ints."""
    if isinstance(node, dict) and tok not in node and tok.lstrip("-").isdigit() and int(tok) in node:
        return int(tok)
    return tok


def _step(node, tok, rel, path):
    if tok.startswith("["):
        field, _, want = tok[1:-1].partition("=")
        for el in node:
            if isinstance(el, dict) and str(el.get(field)) == want:
                return el
        raise PlanError(f"{rel}: no element with {field}={want} ({path})")
    if isinstance(node, list):
        return node[int(tok)]
    tok = _key(node, tok)
    if tok not in node:
        raise PlanError(f"{rel}: no key {tok} ({path})")
    return node[tok]


def set_byml_paths(root, sets, rel):
    for path, value in sets.items():
        toks = _path_tokens(path)
        node = root
        for t in toks[:-1]:
            node = _step(node, t, rel, path)
        last = toks[-1]
        if isinstance(node, list):
            last = int(last)
            old = node[last]
        else:
            last = _key(node, last)
            old = node.get(last)
            if old is None and isinstance(value, dict):  # a new entry, numbers typed like a sibling entry's
                old = next((v for v in node.values() if isinstance(v, dict)), None)
        node[last] = _typed_like(old, value)


# Tables whose row count the game fixes. Adding a row aborts at startup (tested in-game), so rewrite an unused
# row with "replace_row" instead.
# There's one opt-in exception, an EventSetting "add_row" op with "grow": true. The abort we saw came before we
# knew Longshot serves its own size table, and OotrR adds hundreds of EventSetting rows on Hookshot in game.
# Only the Archipelago plugin asks for it, and its probe plan (archipelago.py --probe) is the in-game check.
# Each new row gets a precomputed scene-info row too.
FIXED_ROW_TABLES = ("RSDB/EventSetting.", "RSDB/Location.")


def patch_byml(data, ops, rel):
    root, ver = byml_load(data, allow_big=True)  # written back in its own byte order
    for op in ops:
        if "replace_row" in op:  # keep a row's ID, take every other field from another row, then apply "set"
            spec = op["replace_row"]
            idx = next((i for i, r in enumerate(root) if r.get("__RowId") == spec["row"]), None)
            src = next((r for r in root if r.get("__RowId") == spec["copy_of"]), None)
            if idx is None or src is None:
                raise PlanError(f"{rel}: no row {spec['row'] if idx is None else spec['copy_of']}")
            row = {k: v for k, v in src.items() if k != "__RowId"}
            row["__RowId"] = root[idx]["__RowId"]
            row = {k: row[k] for k in list(root[idx]) if k in row} | {k: v for k, v in row.items() if k not in root[idx]}
            for k, v in spec.get("set", {}).items():
                row[k] = _typed_like(row.get(k), v)
            root[idx] = row
        if "add_row" in op and rel.startswith(FIXED_ROW_TABLES) and not (
                rel.startswith("RSDB/EventSetting.") and op.get("grow") is True):
            raise PlanError(f"{rel}: this table cannot grow (the game aborts at startup); "
                            f"use replace_row on an unused row instead")
        if "add_row" in op:  # table rows: copy an existing row, change fields, insert in sorted place
            spec = op["add_row"]
            src = next((r for r in root if r.get("__RowId") == spec["copy_of"]), None)
            if src is None:
                raise PlanError(f"{rel}: no row {spec['copy_of']}")
            row = dict(src)
            for k, v in spec.get("set", {}).items():
                row[k] = _typed_like(src.get(k), v)
            if any(r.get("__RowId") == row["__RowId"] for r in root):
                raise PlanError(f"{rel}: row {row['__RowId']} already exists")
            ids = [r.get("__RowId") for r in root]
            keep_sorted = ids == sorted(ids)
            root.append(row)
            if keep_sorted:
                root.sort(key=lambda r: r["__RowId"])
        for path, values in op.get("remove_values", {}).items():  # take these values out of a list
            node = root
            for t in _path_tokens(path):
                node = _step(node, t, rel, path)
            if not isinstance(node, list):
                raise PlanError(f"{rel}: {path} is not a list")
            for v in values:
                hits = [i for i, x in enumerate(node) if x == v]
                if len(hits) != 1:
                    raise PlanError(f"{rel}: {path} holds {v} {len(hits)} times, not once")
                del node[hits[0]]
        for path, values in op.get("add_values", {}).items():  # append these values to a list (each new there)
            node = root
            for t in _path_tokens(path):
                node = _step(node, t, rel, path)
            if not isinstance(node, list):
                raise PlanError(f"{rel}: {path} is not a list")
            for v in values:
                if any(x == v for x in node):
                    raise PlanError(f"{rel}: {path} already holds {v}")
                node.append(_typed_like(node[0], v) if node else v)
        for path, spec in op.get("add_entries", {}).items():  # append entries to a list, made if it's missing,
            like = root                                         #   each typed like the first entry of spec["like"]
            for t in _path_tokens(spec["like"]):
                like = _step(like, t, rel, spec["like"])
            if not isinstance(like, list) or not like or not isinstance(like[0], dict):
                raise PlanError(f"{rel}: {spec['like']} has no entry to type the new ones like")
            toks = _path_tokens(path)
            node = root
            for t in toks[:-1]:
                node = _step(node, t, rel, path)
            if not isinstance(node, dict):
                raise PlanError(f"{rel}: {path} isn't under a dictionary")
            key = _key(node, toks[-1]) if toks[-1] in node else toks[-1]
            if key not in node:
                node[key] = []
            if not isinstance(node[key], list):
                raise PlanError(f"{rel}: {path} is not a list")
            for v in spec["values"]:
                if set(v) - set(like[0]):
                    raise PlanError(f"{rel}: {path}: {sorted(set(v) - set(like[0]))} aren't fields of {spec['like']}")
                node[key].append(_typed_like(like[0], v))
        for path in op.get("delete_keys", []):  # take a dictionary key out
            toks = _path_tokens(path)
            node = root
            for t in toks[:-1]:
                node = _step(node, t, rel, path)
            last = _key(node, toks[-1])
            if not isinstance(node, dict) or last not in node:
                raise PlanError(f"{rel}: no key {path}")
            del node[last]
        set_byml_paths(root, op.get("set", {}), rel)
    if "CombinationDataTableData" in rel and isinstance(root, dict):
        _check_table_cells(root, rel)
    return byml_dump(root, ver, big=byml_is_big(data))


# Size-table entries reserve heap space for the file and for the objects created while parsing it.
# Adding just the new file bytes isn't enough, two allocations failed that way. The death table grew from 3 to
# 16 cells and needed about 3 KB more. The item-look holder added one model bind and needed about 100 bytes more.
# These formulas fit every vanilla file of the given type. The first number is the sample size and the number
# in parentheses after each formula is the largest error.
#   AI (*.ainb, 2142)            size rounded to 32 + 376, + 14 + 1.074 x its expression signature table (4)
#   event flow (*.bfevfl, 914)   size rounded to 32 + 272 (exact)        level (*.bcett.byml, 160) rounded + 264 (exact)
#   DeathParam (130)             size rounded to 32 + 5224 (exact)
#   ActorHolderParam (98)        5141 + size + 224 per ActorHoldSettings slot + 102 per ModelBindSettings entry (16)
#   ActorParam (8374)            5159 + size + 48 per component (17)
#   CombinationDataTableData (112) 5137 + size + 240 per CellList cell (17)
#   BlackboardParamTable (590)   5888 + size + 82..104 per parameter by type (20)
# Other byml types (shop params are about 310 per item for sale) rise by their growth plus ENTRY_PER_BLOCK for
# each dict or array element they gain.
ENTRY_SPARE = 32
ENTRY_PER_BLOCK = 384
_BB_COST = {"Bool": 89, "CustomType": 104, "F32": 89, "Mtx33f": 82, "Mtx34f": 86, "Ptr": 99, "S32": 88,
            "String": 104, "U32": 99, "U64": 96, "U8": 85, "Vec3f": 96}  # per parameter, anything else is 104


def _r32(n):
    return (n + 31) & ~31


def rule_entry(key, data):
    """The size-table entry the game's rule for this file type asks for (with ENTRY_SPARE), or None for a type
    without a fitted rule."""
    size = len(data)

    def root():
        r = byml_load(data, allow_big=True)[0]
        return r if isinstance(r, dict) else {}
    if key.endswith(".ainb"):
        import ainb
        exb = ainb.Ainb(data).exb
        sig = 0
        if exb:
            _, _, _, _, _, _, _, _, sig_off, param_off = struct.unpack_from("<4s9I", exb, 0)
            sig = 18 + int(1.08 * max(0, param_off - sig_off)) + 1
        need = _r32(size) + 376 + sig
    elif key.endswith(".bfevfl"):
        need = _r32(size) + 272
    elif key.endswith(".bcett.byml"):
        need = _r32(size) + 264
    elif "game__component__DeathParam" in key:
        need = _r32(size) + 5224
    elif "ActorHolderParam" in key:
        slots = [s for s in (root().get("ActorHoldSettings") or {}).values() if isinstance(s, dict)]
        need = 5141 + size + 224 * len(slots) + 102 * sum(len(s.get("ModelBindSettings") or []) for s in slots) + 16
    elif "engine__actor__ActorParam" in key:
        need = 5159 + size + 48 * len(root().get("Components") or {}) + 17
    elif "CombinationDataTableData" in key:
        need = 5137 + size + 240 * len(root().get("CellList") or {}) + 17
    elif "BlackboardParamTable" in key:
        r = root()
        need = 5888 + size + 20 + sum(
            _BB_COST.get(k.replace("BlackboardParam", "").replace("Array", ""), 104) * len(v)
            for k, v in r.items() if k.startswith("BlackboardParam") and isinstance(v, list))
    else:
        return None
    return _r32(need + ENTRY_SPARE)


def _blocks(data):
    """The dicts and array elements of a byml file, which is what its parse makes objects of."""
    n, stack = 0, [byml_load(data, allow_big=True)[0]]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            n += 1
            stack.extend(x.values())
        elif isinstance(x, list):
            n += len(x)
            stack.extend(x)
    return n


def entry_for(key, old_entry, old, new):
    """The size-table entry a changed file needs. That's its vanilla entry (`old_entry`, for a new file the entry
    of the file it was made from, None if there's none) raised by its growth over `old`, and at least what its
    type's rule asks (rule_entry). Types without a rule rise by ENTRY_PER_BLOCK for each parsed block they gain.
    Returns None when there's no entry to give."""
    need = []
    rule = rule_entry(key, new)
    if rule is not None:
        need.append(rule)
    if old_entry is not None:
        grow = max(0, len(new) - (len(old) if old is not None else len(new)))
        need.append(old_entry + _r32(grow))
        if rule is None and old is not None and key.endswith((".bgyml", ".byml")):
            try:
                gained = max(0, _blocks(new) - _blocks(old))
            except Exception:  # not a byml after all, bytes only
                gained = 0
            need.append(_r32(old_entry + grow + ENTRY_PER_BLOCK * gained))
    return max(need) if need else None


def _check_table_cells(root, rel):
    """A CombinationDataTableData cell without RowKey/ColumnKey only overrides a row its $parent chain defines. One
    for a row nobody defines crashed the game while loading the table (ChemicalCriticalHitIce in the death
    tables, every new game crashed in the opening), so a plan that writes one is refused."""
    defined, parent, seen = set(), root.get("$parent"), set()
    while parent and parent not in seen and AINB_FS is not None:
        seen.add(parent)
        path = parent.replace("Work/", "", 1).replace(".gyml", ".bgyml")
        try:
            p = byml_load(AINB_FS.raw(path), allow_big=True)[0]
        except (OSError, KeyError):
            break
        defined |= set((p.get("CellList") or {}).keys())
        parent = p.get("$parent")
    bad = [k for k, cell in (root.get("CellList") or {}).items()
           if isinstance(cell, dict) and "RowKey" not in cell and k not in defined]
    if bad and (root.get("$parent") is not None):
        raise PlanError(f"{rel}: cells for rows its $parent chain doesn't define and without RowKey/ColumnKey: {bad}")


def patch_text(data, ops, rel):
    """Sets messages' text in a language's text archive (Mals/<Lang>.Product.110.sarc) and keeps their tags."""
    files = sarc_files(data)
    by_file = defaultdict(list)
    for op in ops:
        by_file[op["file"]].append(op)
    for name, file_ops in by_file.items():
        if name not in files:
            raise PlanError(f"{rel}: no text file {name}")
        m = msbt.Msbt(files[name])
        for op in file_ops:
            if op["label"] not in m.labels:
                if not op.get("add"):
                    raise PlanError(f"{rel}:{name}: no message {op['label']} (\"add\": true makes a new one)")
                m.add(op["label"])
            if "copy_from" in op:  # another message of this language, tags and all (a game line reused)
                src = op["copy_from"]
                if src["file"] not in files:
                    raise PlanError(f"{rel}: no text file {src['file']} to copy {src['label']} from")
                sm = m if src["file"] == name else msbt.Msbt(files[src["file"]])
                if src["label"] not in sm:
                    raise PlanError(f"{rel}:{src['file']}: no message {src['label']} to copy")
                m.set_markup(op["label"], sm.markup(src["label"]))
            elif "markup" in op:  # the whole message, tags written as text (tools/msbt.py set_markup)
                m.set_markup(op["label"], op["markup"])
            else:
                m.set_text(op["label"], op["text"])
        files[name] = m.dump()
    return sarc_write(files)


GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
GAMEDATA_TYPES = {"Bool": bool, "Int": int, "UInt": int, "Float": float, "Enum": str,
                  "String16": str, "String32": str, "String64": str}


def patch_gamedata(data, ops, rel):
    """New-file defaults in the save-data list (big-endian BYML, entries keyed by murmur3 of the flag name)."""
    root, ver = byml_load(data, allow_big=True)
    index = {}
    added = False
    for table, entries in root["Data"].items():
        if table == "Bool64bitKey":  # per-placement flags, keyed by 64-bit instance hashes
            continue
        for e in entries:
            index.setdefault(e["Hash"], (table, e))
    for op in ops:
        for name, value in op.get("defaults", {}).items():
            hit = index.get(murmur3_32(name))
            if hit is None:
                raise PlanError(f"{rel}: no save-data flag named {name}")
            table, e = hit
            want = GAMEDATA_TYPES.get(table)
            if want is None or "DefaultValue" not in e:
                raise PlanError(f"{rel}: {name} is a {table}; only {', '.join(GAMEDATA_TYPES)} defaults can be set")
            if not isinstance(value, want) or (want is int and isinstance(value, bool)) or (
                    want is float and isinstance(value, bool)):
                if not (want is float and isinstance(value, int) and not isinstance(value, bool)):
                    raise PlanError(f"{rel}: {name} is a {table}, not {value!r}")
            if table == "Enum":
                if value not in e["RawValues"]:
                    raise PlanError(f"{rel}: {name} has no value {value!r} ({', '.join(e['RawValues'])})")
                value = murmur3_32(value)
            elif table.startswith("String") and len(value.encode("utf-8")) >= int(table[6:]):
                raise PlanError(f"{rel}: {name} holds at most {int(table[6:]) - 1} bytes")
            elif table == "UInt" and value < 0:
                raise PlanError(f"{rel}: {name} is unsigned")
            e["DefaultValue"] = _typed_like(e["DefaultValue"], value)
        # expression flags (BoolExp) are reverse Polish notation, [[opcode, value], ...]. A string value is a flag
        # or enum value name (stored as its murmur3).
        # They're not saved, so a new definition applies to existing saves too.
        for name, values in op.get("boolexp", {}).items():
            hit = index.get(murmur3_32(name))
            if hit is None or hit[0] != "BoolExp":
                raise PlanError(f"{rel}: no expression flag (BoolExp) named {name}")
            e = hit[1]
            old_vals = e["Values"]
            new_vals = []
            for item in values:
                if not isinstance(item, (list, tuple)) or not 1 <= len(item) <= 3:
                    raise PlanError(f"{rel}: {name}: each step is [opcode], [opcode, value] or "
                                    f"[opcode, array, index], got {item!r}")
                step = [int(item[0])]
                if len(item) >= 2:
                    v = item[1]
                    if isinstance(v, str):
                        if murmur3_32(v) not in index and not str(v).startswith("Step"):
                            raise PlanError(f"{rel}: {name}: no flag named {v}")
                        v = murmur3_32(v)
                    step.append(v)
                if len(item) == 3:
                    step.append(int(item[2]))
                new_vals.append(step)
            template = old_vals[0] if old_vals else [0, 0]
            e["Values"] = [[_typed_like(template[0], v) for v in x] for x in new_vals]
        # when a flag resets, a bitmask of SeqExecuteResetGameData types (8 = new file, 1 = area change...).
        # Keys are flag names, or placement instance hashes for per-object flags (Bool64bitKey)
        per_object = None
        for key, value in op.get("reset_type", {}).items():
            if str(key).isdigit():
                if per_object is None:
                    per_object = {e["Hash"]: e for e in root["Data"]["Bool64bitKey"]}
                e = per_object.get(int(key))
                if e is None:
                    raise PlanError(f"{rel}: no per-object flag for instance {key}")
            else:
                hit = index.get(murmur3_32(key))
                if hit is None:
                    raise PlanError(f"{rel}: no save-data flag named {key}")
                e = hit[1]
            e["ResetTypeValue"] = _typed_like(e["ResetTypeValue"], int(value))
        # per-object flag fields (Bool64bitKey rows), ResetTypeValue and ExtraByte (the area an area reset is for)
        for key, fields in op.get("per_object", {}).items():
            if per_object is None:
                per_object = {e["Hash"]: e for e in root["Data"]["Bool64bitKey"]}
            e = per_object.get(int(key))
            if e is None:
                raise PlanError(f"{rel}: no per-object flag for instance {key}")
            for f, v in fields.items():
                if f not in ("ResetTypeValue", "ExtraByte"):
                    raise PlanError(f"{rel}: per-object flag {key}: {f} can't be set")
                like = e.get(f, next((x[f] for x in root["Data"]["Bool64bitKey"] if f in x), int(v)))
                e[f] = _typed_like(like, int(v))
        added |= _add_gamedata_rows(root, op, index, rel, check=not added)  # an earlier op's rows got checked then
        if op.get("add_per_object"):  # new Bool64bitKey rows, kept in hash order (the game binary-searches them)
            if not added:
                _check_layout(root, rel)
            rows = root["Data"]["Bool64bitKey"]
            have = {e["Hash"] for e in rows}
            tmpl = next(e for e in rows if "ExtraByte" in e)
            for key, fields in op["add_per_object"].items():
                h = int(key)
                if h in have:
                    raise PlanError(f"{rel}: per-object flag {key} exists already")
                row = {}
                for f in ("ExtraByte", "ResetTypeValue", "SaveFileIndex", "Hash"):
                    v = {"SaveFileIndex": 0, "Hash": h}.get(f, fields.get(f))
                    if v is not None:
                        row[f] = _typed_like(tmpl[f], int(v))
                if set(fields) - {"ResetTypeValue", "ExtraByte"} or "ResetTypeValue" not in fields:
                    raise PlanError(f"{rel}: new per-object flag {key}: give ResetTypeValue (and ExtraByte) only")
                rows.append(row)
                have.add(h)
            rows.sort(key=lambda e: int(e["Hash"]))
            per_object = None
            added = True
    if added:
        _set_gamedata_layout(root, rel)
    return byml_dump(root, ver, big=byml_is_big(data))


def gamedata_layout(root):
    """The save layout GameDataList's MetaData declares, computed from its rows. That's TotK's format: a 0x20 header,
    one 8-byte entry per row and per type (34 type markers), then the value area. Bool64bitKey rows only go in the
    value area, as a 0-ended list. Returns {"AllDataSaveOffset", "AllDataSaveSize", "SaveDataOffsetPos",
    "SaveDataSize"}. The "all data" image holds every row except the expressions (BoolExp) and structs, and save
    file i holds the rows with SaveFileIndex i."""
    el = {"Vector2": 8, "Vector3": 12, "String16": 16, "String32": 32, "String64": 64, "WString16": 32,
          "WString32": 64, "WString64": 128, "Int64": 8, "UInt64": 8}

    def size(t, r):
        if t in ("Bool", "Int", "UInt", "Float", "Enum", "BoolExp", "Struct"):
            return 0
        if t == "Bool64bitKey":
            return 8
        if t == "Binary":
            return 4 + int(r["DefaultValue"])
        if t in el:
            return el[t]
        if t.endswith("Array"):
            n = int(r.get("ArraySize") or r.get("Size") or r.get("TotalSize") or r.get("OriginalSize") or 1)
            base = t[:-5]
            if base == "Binary":
                return 4 + n * (4 + int(r["DefaultValue"]))
            if base == "Bool":
                return 4 + ((n + 31) // 32) * 4
            return 4 + n * ({"Int": 4, "UInt": 4, "Float": 4, "Enum": 4}.get(base) or el[base])
        raise PlanError(f"GameDataList: no save size known for type {t}")

    def image(rows):
        entries = sum(1 for t, r in rows if t != "Bool64bitKey")
        data = sum(size(t, r) for t, r in rows)
        b64 = 8 if any(t == "Bool64bitKey" for t, r in rows) else 0
        start = 0x20 + 8 * (entries + 34)
        return start, start + data + b64
    rows = [(t, r) for t, rs in root["Data"].items() for r in rs]
    all_start, all_end = image([(t, r) for t, r in rows if t not in ("BoolExp", "Struct")])
    n = len(root["MetaData"]["SaveDataSize"])
    files = [image([(t, r) for t, r in rows if r.get("SaveFileIndex", -1) == i]) for i in range(n)]
    return {"AllDataSaveOffset": all_start, "AllDataSaveSize": all_end,
            "SaveDataOffsetPos": [f[0] for f in files], "SaveDataSize": [f[1] for f in files]}


def _set_gamedata_layout(root, rel):
    meta = root["MetaData"]
    for k, v in gamedata_layout(root).items():
        if isinstance(v, list):
            meta[k] = [_typed_like(meta[k][i], x) for i, x in enumerate(v)]
        else:
            meta[k] = _typed_like(meta[k], v)


def _check_layout(root, rel):
    """Refuses new rows unless gamedata_layout reproduces this GameDataList's MetaData exactly. Otherwise we don't
    know the layout rule and recomputing it could corrupt saves."""
    have = {k: root["MetaData"][k] for k in ("AllDataSaveOffset", "AllDataSaveSize", "SaveDataOffsetPos",
                                             "SaveDataSize")}
    have = {k: ([int(x) for x in v] if isinstance(v, list) else int(v)) for k, v in have.items()}
    if have != gamedata_layout(root):
        raise PlanError(f"{rel}: the save layout formula doesn't reproduce this GameDataList ({have} vs "
                        f"{gamedata_layout(root)}); new rows refused")


def _add_gamedata_rows(root, op, index, rel, check=True):
    """Adds the new rows of op "add_bool_arrays" {name: size} (saved, new-file reset, all false) and "add_boolexp"
    {name: steps}, appended to their tables. The game indexes rows by hash and vanilla tables aren't sorted. True
    if any got added.
    Refused unless gamedata_layout reproduces the vanilla MetaData exactly, because an unknown layout would corrupt
    saves. check=False means an earlier op of this patch already added rows (after checking the vanilla layout),
    so the MetaData won't match the rows until the layout gets recomputed at the end. Several features may each
    add rows."""
    arrays, exps, ints = op.get("add_bool_arrays", {}), op.get("add_boolexp", {}), op.get("add_ints", {})
    bools = op.get("add_bools", {})
    structs = op.get("add_struct_bools", {})
    runtime = op.get("add_runtime_bool_arrays", {})
    seeded = op.get("add_seeded_ints") or {}
    if not arrays and not exps and not ints and not bools and not structs and not runtime and not seeded:
        return False
    if check:
        _check_layout(root, rel)
    # "add_struct_bools" {struct: [member, ...]} adds NEW members to a struct of saved Bools, each with a Bool row
    # "<struct>.<member>" shaped like the row of the struct's first member (for IsTreasureBoxOpen that's save file 0,
    # never reset, false). The game reads and writes a flag like that through the struct, member murmur3(member) ->
    # row murmur3("<struct>.<member>"), and a name that isn't a member just silently doesn't get saved. We use it for
    # the chest AI's open flag (tools/rando/chest_flags.py), like OotrR adds IsGet members for its new items. Members
    # are appended since vanilla member lists aren't sorted.
    for sname, mems in structs.items():
        hit = index.get(murmur3_32(sname))
        if hit is None or hit[0] != "Struct":
            raise PlanError(f"{rel}: no save-data struct named {sname}")
        members = hit[1]["DefaultValue"]
        rows = [index.get(int(m["Value"])) for m in members]
        if not members or any(r is None or r[0] != "Bool" for r in rows):
            raise PlanError(f"{rel}: {sname} is not a struct of Bools")
        stmpl = rows[0][1]
        have = {int(m["Hash"]) for m in members}
        for mem in mems:
            full = f"{sname}.{mem}"
            mh, fh = murmur3_32(str(mem)), murmur3_32(full)
            if mh in have or fh in index:
                raise PlanError(f"{rel}: save-data flag {full} exists already")
            row = dict(stmpl, DefaultValue=False, Hash=_typed_like(stmpl["Hash"], fh))
            root["Data"]["Bool"].append(row)
            index[fh] = ("Bool", row)
            members.append({"Hash": _typed_like(members[0]["Hash"], mh), "Value": _typed_like(members[0]["Value"], fh)})
            have.add(mh)
    # "add_bools" {name: default} adds NEW saved plain Bool rows (save file 0, reset on a new file, like most vanilla
    # flags, 9,338 of 11,292). Plain Bools are what a client can write in memory (the Archipelago mailbox, OotrR's
    # RandoAP.Recv.*) and what event and sequence nodes read by name.
    btmpl = next(r for r in root["Data"]["Bool"] if r.get("SaveFileIndex") == 0 and r.get("ResetTypeValue") == 8)
    for name, default in bools.items():
        h = murmur3_32(name)
        if h in index:
            raise PlanError(f"{rel}: save-data name {name} is taken (hash {h})")
        if not isinstance(default, bool):
            raise PlanError(f"{rel}: new Bool {name}: default {default!r} is not true or false")
        row = {"DefaultValue": default, "Hash": _typed_like(btmpl["Hash"], h),
               "ResetTypeValue": _typed_like(btmpl["ResetTypeValue"], 8),
               "SaveFileIndex": _typed_like(btmpl["SaveFileIndex"], 0)}
        root["Data"]["Bool"].append(row)
        index[h] = ("Bool", row)
    # "add_ints" {name: default} adds NEW saved Int rows (save file 0, reset on a new file, like most vanilla counters)
    itmpl = next(r for r in root["Data"]["Int"] if r.get("SaveFileIndex") == 0 and r.get("ResetTypeValue") == 8)
    # "add_seeded_ints" {"seed": s, "rows": {name: default}}: the same, keyed murmur3(name, s), for code that finds
    # its row by hashing a name it has (the D-pad gear wheels' use order, parity/_extras_wheel.py)
    rows = [(murmur3_32(name), name, default) for name, default in ints.items()]
    if seeded:
        seed = seeded.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 1 << 32:
            raise PlanError(f"{rel}: add_seeded_ints: seed {seed!r} is not a 32-bit number")
        rows += [(murmur3_32(name, seed), f"{name} (seed {seed:#x})", d) for name, d in seeded.get("rows", {}).items()]
    for h, name, default in rows:
        if h in index:
            raise PlanError(f"{rel}: save-data name {name} is taken (hash {h})")
        if isinstance(default, bool) or not isinstance(default, int):
            raise PlanError(f"{rel}: new Int {name}: default {default!r} is not an integer")
        row = {"DefaultValue": _typed_like(itmpl["DefaultValue"], default), "Hash": _typed_like(itmpl["Hash"], h),
               "ResetTypeValue": _typed_like(itmpl["ResetTypeValue"], 8),
               "SaveFileIndex": _typed_like(itmpl["SaveFileIndex"], 0)}
        root["Data"]["Int"].append(row)
        index[h] = ("Int", row)
    tmpl = next(r for r in root["Data"]["BoolArray"] if r.get("SaveFileIndex") == 0)
    for name, n in arrays.items():
        h = murmur3_32(name)
        if h in index:
            raise PlanError(f"{rel}: save-data name {name} is taken (hash {h})")
        if not 1 <= int(n) <= 4096:
            raise PlanError(f"{rel}: bool array {name}: size {n} out of 1..4096")
        row = {"DefaultValue": False, "Hash": _typed_like(tmpl["Hash"], h),
               "OriginalSize": _typed_like(tmpl["OriginalSize"], int(n)),
               "ResetTypeValue": _typed_like(tmpl["ResetTypeValue"], 8),
               "SaveFileIndex": _typed_like(tmpl["SaveFileIndex"], 0),
               "TotalSize": _typed_like(tmpl["TotalSize"], int(n))}
        root["Data"]["BoolArray"].append(row)
        index[h] = ("BoolArray", row)
    # "add_runtime_bool_arrays" {name: size} adds NEW bool arrays that only live while the game runs and get cleared
    # at every map change (SaveFileIndex -1, ResetTypeValue 1, and ChangeBanc runs ResetType 0). They're shaped like
    # vanilla's MiniGame_DampeRace_PlayerPassedCheckpoints. They aren't in the save file, so the save layout doesn't
    # change
    rtmpl = next(r for r in root["Data"]["BoolArray"] if r.get("SaveFileIndex") == -1 and r.get("ResetTypeValue") == 1)
    for name, n in runtime.items():
        h = murmur3_32(name)
        if h in index:
            raise PlanError(f"{rel}: save-data name {name} is taken (hash {h})")
        if not 1 <= int(n) <= 4096:
            raise PlanError(f"{rel}: bool array {name}: size {n} out of 1..4096")
        row = {"DefaultValue": False, "Hash": _typed_like(rtmpl["Hash"], h),
               "OriginalSize": _typed_like(rtmpl["OriginalSize"], int(n)),
               "ResetTypeValue": _typed_like(rtmpl["ResetTypeValue"], 1),
               "SaveFileIndex": _typed_like(rtmpl["SaveFileIndex"], -1),
               "TotalSize": _typed_like(rtmpl["TotalSize"], int(n))}
        root["Data"]["BoolArray"].append(row)
        index[h] = ("BoolArray", row)
    etmpl = root["Data"]["BoolExp"][0]
    for name, values in exps.items():
        h = murmur3_32(name)
        if h in index:
            raise PlanError(f"{rel}: save-data name {name} is taken (hash {h})")
        steps = []
        for item in values:
            step = [int(item[0])]
            if len(item) >= 2:
                v = item[1]
                if isinstance(v, str):
                    if murmur3_32(v) not in index:
                        raise PlanError(f"{rel}: {name}: no flag named {v}")
                    v = murmur3_32(v)
                step.append(v)
            if len(item) == 3:
                step.append(int(item[2]))
            steps.append(step)
        t0 = etmpl["Values"][0]
        row = {"Hash": _typed_like(etmpl["Hash"], h), "ResetTypeValue": _typed_like(etmpl["ResetTypeValue"], 0),
               "SaveFileIndex": _typed_like(etmpl["SaveFileIndex"], -1),
               "Values": [[_typed_like(t0[0], x) for x in st] for st in steps]}
        root["Data"]["BoolExp"].append(row)
        index[h] = ("BoolExp", row)
    return True


def patch_binary(data, ops, rel):
    out = bytearray(data)
    for op in ops:
        off = int(op["offset"], 0) if isinstance(op["offset"], str) else op["offset"]
        if off < 0 or off + 4 > len(out):
            raise PlanError(f"{rel}: offset {off:#x} is outside the file")
        old = struct.unpack_from("<i", out, off)[0]
        if "expect" in op and old != op["expect"]:
            raise PlanError(f"{rel}: {off:#x} holds {old}, not the expected {op['expect']} (different game version?)")
        struct.pack_into("<i", out, off, op["i32"])
    if rel.endswith(".ainb"):  # a level-logic module edited in place has to stay a well-formed graph
        import ainb
        try:
            bad = ainb.Ainb(bytes(out)).input_shape_problems()
        except ainb.AinbError as ex:
            raise PlanError(f"{rel}: the edited AI file no longer reads: {ex}")
        if bad:  # e.g. an input rewired to an output its node never computes (OotrR's finding)
            raise PlanError(f"{rel}: {bad[0]} ({len(bad)} such)")
    return bytes(out)


def patch_copy(data, ops, rel):
    return ops[-1]["_data"]


def installed_new_files(romfs=None):
    """Files tools/install.py added to the game folder (installed.json "new_files"), which aren't the game's own.
    With the game folder given, also those of a seed the randomizer app installed (its record sits next to the
    game)."""
    records = [os.path.join(os.path.dirname(os.path.abspath(VANILLA)), "installed.json")]
    from romtools import game_side_dir
    side = romfs and game_side_dir(romfs)
    if side:
        records.append(os.path.join(os.path.dirname(side), "installed.json"))
    out = set()
    for record in dict.fromkeys(os.path.normcase(r) for r in records):
        if os.path.exists(record):
            out |= {os.path.normpath(r) for r in (json.load(open(record, encoding="utf-8")).get("new_files") or {})}
    return out


def pool_string(name):
    """A name as the game's binary files keep it in their string pools: u16 length, the text, a zero byte."""
    b = name.encode("ascii")
    return len(b).to_bytes(2, "little") + b + b"\0"


def rename_strings(data, renames, rel):
    """Same-length renames of pooled names ([old, new] pairs). Each old name has to be in the file exactly once, as
    a whole pooled string, so nothing else moves and every pointer stays valid."""
    for old, new in renames:
        if len(old) != len(new):
            raise PlanError(f"{rel}: rename {old} -> {new} changes the length")
        o, n = pool_string(old), pool_string(new)
        if data.count(o) != 1:
            raise PlanError(f"{rel}: {old} is in the file {data.count(o)} times as a name, not once")
        if data.count(n):
            raise PlanError(f"{rel}: already holds the name {new}")
        data = data.replace(o, n)
    return data


def splice_segments(data, segments, rel):
    """A new file's bytes from "segments": {"copy": [offset, size]} of the source, {"zero": n}, {"hex": "..."}."""
    out = bytearray()
    for s in segments:
        if "copy" in s:
            o, n = int(s["copy"][0]), int(s["copy"][1])
            if o < 0 or n < 0 or o + n > len(data):
                raise PlanError(f"{rel}: segment {o:#x}+{n:#x} runs past its source ({len(data):#x} bytes)")
            out += data[o:o + n]
        elif "zero" in s:
            out += bytes(int(s["zero"]))
        elif "hex" in s:
            out += bytes.fromhex(s["hex"])
        else:
            raise PlanError(f"{rel}: unknown segment {sorted(s)}")
    return bytes(out)


def patch_bytes(data, edits, rel):
    """Same-size byte edits ([{"offset", "expect", "bytes"}], hex strings of one length). Each one has to find its
    expected bytes, so nothing moves and an edit made for another version of the file is refused."""
    d = bytearray(data)
    for e in edits:
        o, old, new = int(e["offset"]), bytes.fromhex(e["expect"]), bytes.fromhex(e["bytes"])
        if len(old) != len(new) or o < 0 or d[o:o + len(old)] != old:
            raise PlanError(f"{rel}: byte edit at {o:#x} ({len(new)} bytes) doesn't find the bytes it expects")
        d[o:o + len(new)] = new
    return bytes(d)


def patch_names(data, ops, rel):
    for op in ops:
        data = patch_bytes(rename_strings(data, op.get("rename", []), rel), op.get("bytes", []), rel)
    return data


AINB_FS = None  # the vanilla game files, for "ainb" edits that copy nodes from another file
INNER_GROWTH = {}  # files inside packs that "ainb" edits made larger: path -> growth (their size-table entries rise)
NEW_INNER = {}  # files a "packs" op added to a pack ("new_from"): path -> (source path, source size, final size)
NEW_INNER_SRC = {}  # the same files: path -> the bytes they were copied from (entry_for)
BB_ARRAYS = {"Bool": "BlackboardParamBoolArray", "S32": "BlackboardParamS32Array", "U32": "BlackboardParamU32Array",
             "U64": "BlackboardParamU64Array", "F32": "BlackboardParamF32Array",
             "String": "BlackboardParamStringArray"}


_AINB_SOURCES = {}  # (Romfs, pack, file) -> parsed vanilla AI file, "copy" edits read the same few hundreds of times


def _ainb_source(spec):
    """A vanilla AI file to copy nodes from, read and parsed once (Ainb.copy_nodes only reads its source)."""
    import ainb
    key = (AINB_FS, spec.get("pack") or None, spec["file"])
    if key not in _AINB_SOURCES:
        if spec.get("pack"):
            files = sarc_files(AINB_FS.read(spec["pack"]))
            if spec["file"] not in files:
                raise PlanError(f"{spec['pack']}: no file {spec['file']}")
            _AINB_SOURCES[key] = ainb.Ainb(files[spec["file"]])
        else:
            _AINB_SOURCES[key] = ainb.Ainb(AINB_FS.raw(spec["file"]))
    return _AINB_SOURCES[key]


def _ainb_bb_param(files, spec, rel):
    """Adds a key to an actor blackboard table in the same pack, typed like the game's tables."""
    table = spec["table"]
    if table not in files:
        raise PlanError(f"{rel}: no blackboard table {table}")
    root, ver = byml_load(files[table])
    arr = BB_ARRAYS.get(spec["type"])
    if arr is None:
        raise PlanError(f"{rel}: blackboard type {spec['type']} (one of {', '.join(BB_ARRAYS)})")
    rows = root.setdefault(arr, [])
    if any(r.get("BBKey") == spec["key"] for r in rows):
        return
    init = spec.get("init", 0)
    row = {"BBKey": spec["key"]}
    if spec["type"] == "U64":  # like DropActorRespawnData (heart pieces), EnumClassName then a U32 InitVal
        row["EnumClassName"] = ""
        row["InitVal"] = U32(init)
    elif spec["type"] == "U32":
        row["InitVal"] = U32(init)
    elif spec["type"] == "F32":
        row["InitVal"] = float(init)
    elif spec["type"] == "Bool":
        row["InitVal"] = bool(init)
    elif spec["type"] == "String":  # as the Drop table's Drop__DropActor: InitValConverted, a String128
        row["InitValConverted"] = str(init or "")
        row["StringParamType"] = "String128"
    else:
        row["InitVal"] = int(init)
    row.update({"IsInstanceParam": bool(spec.get("instance")), "IsRecord": False,
                "IsSafeParamForExternalTools": False})  # "instance": a level placement may set it (Dynamic.<key>)
    rows.append(row)
    files[table] = byml_dump(root, ver)


def patch_ainb_one(data, op, rel, files=None):
    """Applies one "ainb" plan entry to an AINB file's bytes. Every edit is read back from the written bytes."""
    import ainb
    try:
        a = ainb.Ainb(data)
        labels, checks = {}, []

        def ref(r):
            if isinstance(r, str) and r.startswith("@"):
                c = next((c for c in a.commands if c["name"] == r[1:]), None)
                if c is None:
                    raise PlanError(f"{rel}: no command {r[1:]}")
                return c["main"]
            if isinstance(r, str) and ":" in r:
                lab, _, i = r.partition(":")
                if (lab, int(i)) not in labels:
                    raise PlanError(f"{rel}: no copied node {r}")
                return labels[(lab, int(i))]
            return a.node(r)

        for e in op.get("edits", []):
            (kind, s), = e.items()
            if kind == "copy":
                src = _ainb_source(s["from"])
                m = a.copy_nodes(src, [src.node(n) for n in s["nodes"]], follow=s.get("follow", True),
                                 values=s.get("values"))
                labels.update({(s.get("label", "copy"), i): j for i, j in m.items()})
                checks += [("name", j, src.nodes[i]["name"]) for i, j in m.items()]
            elif kind == "retype":  # node becomes a copy of another file's node, same index (ainb.Ainb.retype)
                src = _ainb_source(s["from"])
                i = a.retype(ref(s["node"]), src, s["like"], values=s.get("values"))
                checks.append(("name", i, src.nodes[src.node(s["like"])]["name"]))
            elif kind == "set_property":
                i = ref(s["node"])
                a.set_property(i, s["name"], s["value"])
                checks.append(("properties", i, s["name"], s["value"]))
            elif kind == "set_input":
                i = ref(s["node"])
                a.set_input(i, s["name"], s["value"], const=bool(s.get("const")))
                checks.append(("inputs", i, s["name"], s["value"]))
            elif kind == "set_bb":
                a.set_bb_default(s["name"], s["value"])
            elif kind == "add_bb":  # a new entry in the file's blackboard (ainb.Ainb.add_bb, "like" names an entry
                a.add_bb(s["type"], s["name"], s.get("default"), like=s.get("like"))  # whose table it reads too)
            elif kind == "read_bb":  # an input reads a blackboard entry (ainb.Ainb.read_bb)
                i = ref(s["node"])
                a.read_bb(i, s["input"], s["bb"])
                checks.append(("read_bb", i, s["input"], s["bb"]))
            elif kind == "feed_bb_reads":  # every input reading blackboard entry "bb" is fed by a node instead
                f = ref(s["from"])  # (ainb.Ainb.feed_bb_reads, a StringSelector's input is left alone)
                if a.feed_bb_reads(s["type"], s["bb"], f, s["output"]) < s.get("min", 1):
                    raise PlanError(f"{rel}: fewer than {s.get('min', 1)} input(s) read blackboard {s['bb']}")
                checks.append(("fed_bb", s["type"], s["bb"]))
            elif kind == "wrap":
                c = next((c for c in a.commands if c["name"] == s.get("command", "Root")), None)
                if s.get("if_needed") and c is not None and a.is_plain_simultaneous(c["main"]):
                    continue  # already starts at a Simultaneous like the one wrap makes (vanilla, or another op's)
                i = a.wrap_command(s.get("command", "Root"))
                checks.append(("child", i, a.nodes[i]["plugs"][2][0]["node"]))
            elif kind == "add_child":
                p, c = ref(s["parent"]), ref(s["child"])
                if "case" in s:  # an S32Selector case (ainb.Ainb.add_case)
                    a.add_case(p, c, s["case"])
                elif "range" in s:  # an F32Selector case [low, high] (ainb.Ainb.add_range_case)
                    a.add_range_case(p, c, *s["range"])
                    checks.append(("range", p, c, tuple(float(x) for x in s["range"])))
                elif "string" in s:  # a StringSelector case (ainb.Ainb.add_string_case)
                    a.add_string_case(p, c, s["string"])
                    checks.append(("string", p, c, s["string"]))
                elif "default" in s:  # an F32/StringSelector's default child, its label (ainb.Ainb.add_default)
                    a.add_default(p, c, s["default"] or ainb.Ainb.F32_OTHER)
                    checks.append(("default", p, c))
                else:
                    a.add_child(p, c, s.get("name", ""), ainb.random_weight(s["weight"]) if "weight" in s else b"",
                                first=bool(s.get("first")))
                checks.append(("child", p, c))
            elif kind == "link":
                f, t = ref(s["from"]), ref(s["to"])
                a.link(f, s["output"], t, s["input"])
                checks.append(("link", f, t, s["input"]))
            elif kind == "feed":  # bool/float/string/int inputs: the consumer lists its source (ainb.Ainb.feed)
                f, t = ref(s["from"]), ref(s["to"])
                a.feed(f, s["output"], t, s["input"])
                checks.append(("link", f, t, s["input"]))
            elif kind == "add_source":  # one more source in a multi-input (ainb.Ainb.add_multi_source)
                f, t = ref(s["from"]), ref(s["to"])
                a.add_multi_source(t, s["input"], f, s["output"])
                checks.append(("source", f, t, s["input"], s["output"]))
            elif kind == "repoint_source":  # a multi-input entry reads another node (ainb.Ainb.repoint_source)
                o, f, t = ref(s["old"]), ref(s["from"]), ref(s["to"])
                a.repoint_source(t, s["input"], o, f, s["output"])
                checks += [("source", f, t, s["input"], s["output"]), ("no_source", o, t, s["input"])]
            elif kind == "cut":  # an input fed by a node holds its own value instead (ainb.Ainb.cut_input)
                i = ref(s["node"])
                a.cut_input(i, s["input"], s["value"], default=bool(s.get("default")))
                checks.append(("cut", i, s["input"], s["value"]))
            elif kind == "set_child":  # re-point an existing child link (by position or name, e.g. "Execute")
                p, c = ref(s["parent"]), ref(s["child"])
                a.set_child(p, s["which"], c)
                checks.append(("child", p, c))
            elif kind == "bb_param":
                if files is None:
                    raise PlanError(f"{rel}: bb_param is for AINB files inside a pack")
                _ainb_bb_param(files, s, rel)
            else:
                raise PlanError(f"{rel}: unknown ainb edit {kind}")
        new = a.dump()
        b = ainb.Ainb(new)  # read back what was written
        if b.dump() != new or len(b.nodes) != len(a.nodes):
            raise PlanError(f"{rel}: the edited AI file does not read back the same")
        for c in checks:
            if c[0] == "name" and b.nodes[c[1]]["name"] != c[2]:
                raise PlanError(f"{rel}: copied node {c[1]} reads back as {b.nodes[c[1]]['name']}")
            if c[0] in ("properties", "inputs"):
                _, e_ = b._param(c[1], c[0], c[2])
                want = c[3]
                if not _same_value(e_["value"], want):
                    raise PlanError(f"{rel}: node {c[1]} {c[2]} reads back as {e_['value']}, not {want}")
            if c[0] == "child" and not any(pl["node"] == c[2] for pl in b.nodes[c[1]]["plugs"][ainb.PLUG_CHILD]):
                raise PlanError(f"{rel}: node {c[2]} is not a child of node {c[1]} after writing")
            if c[0] == "range":
                lo, hi = c[3]
                if not any(x == c[2] and abs(a_ - lo) < 1e-3 and abs(b_ - hi) < 1e-3
                           for a_, b_, x in b.f32_cases(c[1])[0]):
                    raise PlanError(f"{rel}: F32Selector {c[1]} has no case {lo}..{hi} for node {c[2]} after writing")
            if c[0] == "string" and (c[3], c[2]) not in b.string_cases(c[1])[0]:
                raise PlanError(f"{rel}: StringSelector {c[1]} has no case {c[3]!r} for node {c[2]} after writing")
            if c[0] == "default":
                got = b.string_cases(c[1])[1] if b.nodes[c[1]]["type"] == 5 else b.f32_cases(c[1])[1]
                if (got or (None,))[0] != c[2]:
                    raise PlanError(f"{rel}: selector {c[1]}'s default is not node {c[2]} after writing")
            if c[0] == "link" and b._input(c[2], c[3])[1]["node"] != c[1]:
                raise PlanError(f"{rel}: input {c[3]} of node {c[2]} is not fed by node {c[1]} after writing")
            if c[0] == "read_bb":
                t_, e_ = b._input(c[1], c[2])
                idx = e_["flags"] & 0xFFFF
                if not e_["flags"] & ainb.BB_INDEXED or e_["node"] >= 0 or b.bb[t_][idx]["name"] != c[3]:
                    raise PlanError(f"{rel}: input {c[2]} of node {c[1]} doesn't read blackboard {c[3]} after writing")
            if c[0] == "fed_bb" and b.bb_readers(c[1], c[2]):
                raise PlanError(f"{rel}: {b.bb_readers(c[1], c[2])} still read blackboard {c[2]} after writing")
            if c[0] == "cut":
                _, e_ = b._input(c[1], c[2])
                if e_["node"] != -1 or not _same_value(e_["value"], c[3]):
                    raise PlanError(f"{rel}: input {c[2]} of node {c[1]} isn't its own value {c[3]} after writing")
            if c[0] == "source":
                _, f, t, inp, out = c
                pt, e_ = b._input(t, inp)
                k = b._output_index(f, pt, out)
                base = -100 - e_["node"]
                if e_["node"] > -100 or (f, k) not in [(m[0], m[1]) for m in b.multi[base:base + e_["plug"]]]:
                    raise PlanError(f"{rel}: multi-input {inp} of node {t} doesn't read node {f} {out} after writing")
            if c[0] == "no_source":
                _, o, t, inp = c
                _, e_ = b._input(t, inp)
                base = -100 - e_["node"]
                if any(m[0] == o for m in b.multi[base:base + e_["plug"]]):
                    raise PlanError(f"{rel}: multi-input {inp} of node {t} still reads node {o} after writing")
        bad = ainb_bb_reads_out_of_range(b)
        if bad:
            raise PlanError(f"{rel}: {bad[0]} (the game reads a null value there and crashes; "
                            f"{len(bad)} such parameter(s))")
        bad = b.input_shape_problems()
        if bad:
            raise PlanError(f"{rel}: {bad[0]} (no input in the game's files is shaped so; {len(bad)} such)")
        return new
    except ainb.AinbError as ex:
        raise PlanError(f"{rel}: {ex}")


def ainb_bb_reads_out_of_range(a):
    """Parameters that read a blackboard entry the file doesn't have (flags 0x8000000N, entry N of the parameter's
    type). Vanilla has none, all 12955 such reads in 1793 AI files are in range. The disguised trap crashed on
    one when two timers copied from the trap chest kept its blackboard reads."""
    import ainb
    out = []
    for i, n in enumerate(a.nodes):
        for t in ainb.PTYPES:
            for sec in ("properties", "inputs"):
                for e in n[sec][t]:
                    f = e.get("flags", 0)
                    if f >> 24 == 0x80 and ((f & 0xFFFF) >= len(a.bb[t]) or f & 0x00FF0000):
                        out.append(f"node {i} ({n['name']}) {sec[:-1]} {e['name']} reads blackboard {t} entry "
                                   f"{f & 0xFFFF}, which the file doesn't have ({len(a.bb[t])})")
    return out


def patch_ainb(data, ops, rel):
    for op in ops:
        data = patch_ainb_one(data, op, rel)
    return data


def patch_pack(data, ops, rel):
    files = sarc_files(data)
    original = {k: len(v) for k, v in files.items()}  # growth is measured across all the ops on a file
    for op in ops:
        if "_ainb" in op:  # an "ainb" plan entry for an AI file in this pack (and/or its blackboard tables)
            inner = op["_ainb"].get("file")
            if inner is not None and inner not in files:
                raise PlanError(f"{rel}: no file {inner} in the pack")
            if inner is not None:
                files[inner] = patch_ainb_one(files[inner], op["_ainb"], f"{rel}:{inner}", files)
            for spec in op["_ainb"].get("bb_params", []):
                _ainb_bb_param(files, spec, rel)
            continue
        inner = op["file"]
        if op.get("from_pack"):  # by default, a byte copy from another vanilla pack under the same path
            src = sarc_files(AINB_FS.read(op["from_pack"]))  # "new_from" gives it a new path and size-table entry
            name = op.get("new_from") or inner
            if name not in src:
                raise PlanError(f"{rel}: {op['from_pack']} holds no {name} to copy")
            if inner in files and not op.get("new_from") and files[inner] != src[name]:
                raise PlanError(f"{rel}: already holds a different {inner} than {op['from_pack']}")
            if inner not in files:
                files[inner] = src[name]
                if op.get("new_from"):
                    NEW_INNER[inner] = (name, len(src[name]), None)
                    NEW_INNER_SRC[inner] = src[name]
            if not op.get("set") and not op.get("remove"):
                continue
        if inner not in files and op.get("new_from"):  # a new file, copied from another file of the same pack
            if op["new_from"] not in files:
                raise PlanError(f"{rel}: no file {op['new_from']} in the pack to make {inner} from")
            files[inner] = files[op["new_from"]]
            NEW_INNER[inner] = (op["new_from"], len(files[inner]), None)
            NEW_INNER_SRC[inner] = files[inner]
        if inner not in files:
            raise PlanError(f"{rel}: no file {inner} in the pack")
        root, ver = byml_load(files[inner], allow_big=True)
        set_byml_paths(root, op.get("set", {}), f"{rel}:{inner}")
        for path in op.get("remove", []):  # delete a key ("a.b.c")
            toks = _path_tokens(path)
            node = root
            for t in toks[:-1]:
                node = _step(node, t, f"{rel}:{inner}", path)
            if isinstance(node, dict) and toks[-1] in node:
                del node[toks[-1]]
            else:
                raise PlanError(f"{rel}:{inner}: no key {path} to remove")
        try:
            files[inner] = byml_dump(root, ver, big=byml_is_big(files[inner]))
        except (struct.error, OverflowError) as e:
            raise PlanError(f"{rel}:{inner}: a value doesn't fit its type ({e})")
        if inner in NEW_INNER:
            NEW_INNER[inner] = NEW_INNER[inner][:2] + (len(files[inner]),)
    # files in a pack have size-table entries of their own (checked on AI/*.ainb), so raise each by its whole growth
    # over the pack's original. Going by per-op growth (the largest single "ainb" op) left AI/DropItem.root.ainb
    # 1.7 KB short, since three features edit it, and the game crashed at boot reading it.
    for k, v in files.items():
        if k in original and len(v) > original[k]:
            INNER_GROWTH[k] = max(INNER_GROWTH.get(k, 0), len(v) - original[k])
    return sarc_write(files)


def op_packs(op, romfs, inner=None):
    """The packs a "packs"/"ainb" op is for. That's its "pack", a list of packs, or "*" for every pack of the game
    that holds the op's file (tools/packpaths.py)."""
    p = op.get("pack")
    if isinstance(p, list):
        return list(p)
    if p != "*":
        return [p]
    import packpaths
    inner = inner or op.get("file")
    if not inner:
        raise PlanError(f"\"pack\": \"*\" needs a \"file\" to find the packs holding it: {op}")
    found = list(packpaths.carriers(inner, romfs))
    if not found:
        raise PlanError(f"no pack holds {inner} (\"pack\": \"*\")")
    return found


def expand_ainb_op(op, romfs):
    """[(pack, op)] for an "ainb" op in a pack, one per pack it names. With "*", an AI file goes to every pack
    holding it and each blackboard table of "bb_params" to every pack holding that table."""
    if op.get("pack") != "*":
        return [(pk, dict(op, pack=pk)) for pk in op_packs(op, romfs)]
    out = defaultdict(lambda: dict(op, bb_params=[]))
    if op.get("file"):
        for pk in op_packs(op, romfs):
            out[pk]["pack"] = pk
    for spec in op.get("bb_params", []):
        for pk in op_packs(op, romfs, spec["table"]):
            o = out[pk]
            o["pack"] = pk
            if op.get("file") and pk not in op_packs(op, romfs):
                o.pop("file", None)
                o.pop("edits", None)
            o["bb_params"] = o["bb_params"] + [spec]
    return sorted(out.items())


def planned_instance_keys(plan, romfs):
    """{actor: {key}} of instance parameters this plan adds to blackboard tables ("bb_params" with "instance"), for
    every actor whose pack holds the table. Placements of those actors may then set them (Dynamic.<key>)."""
    import packpaths
    out = defaultdict(set)
    for op in plan["ainb"]:
        for spec in op.get("bb_params", []):
            if not spec.get("instance"):
                continue
            packs = (packpaths.carriers(spec["table"], romfs) if op.get("pack") == "*"
                     else [op["pack"]] if isinstance(op.get("pack"), str) else op.get("pack") or [])
            for pk in packs:
                out[os.path.basename(pk).replace(".pack.zs", "")].add(spec["key"])
    # a NEW actor type whose pack is a copy of another actor's ("new_files", e.g. the shops' shelf types from
    # tools/rando/shops.py shelf_type_ops) holds its source's blackboard tables. So its placements take what the
    # source's take, meaning declared instance parameters and the keys vanilla levels give the source
    ap = None
    for op in plan.get("new_files", []):
        to = re.fullmatch(r"Pack/Actor/(\w+)\.pack\.zs", str(op.get("to", "")))
        src = re.fullmatch(r"Pack/Actor/(\w+)\.pack\.zs", str(op.get("from", "")))
        if to and src:
            ap = ap or ActorParams(romfs)
            out[to.group(1)] |= set(ap.declared(src.group(1))) | set(ap.vanilla().get(src.group(1), ()))
            out[to.group(1)] |= set(out.get(src.group(1), ()))  # plus what this plan adds to the source's tables,
            # the copy holds them too (sync_new_packs), e.g. the butterfly cue's spawner in parity/_marker.py
    return dict(out)


def sync_new_packs(built, new_packs, load):
    """A NEW pack is a copy of a game pack, like the shops' shelf types, the chests' carrier copies and the hold-up
    displays. It holds files whose paths the game's packs hold too: its source's AI, physics and pouch parameters,
    plus ModelInfo and AnimationParam files copied from another actor's pack. The plan's edits to such a file in
    the game's packs reach the copies as well. A copy that still holds the file's vanilla bytes gets the edited
    bytes, as long as every edited game pack agrees on them (check_shared_paths reports the rest). Without this a
    seed with every option stopped on Obj_DekuStick's PouchContentParam, which was edited in the game's packs but
    vanilla in two shelf types.
    `built` is {pack: bytes} and gets updated. Returns the new packs changed here."""
    from collections import defaultdict as _dd
    edited, before = _dd(set), {}
    for rel, data in built.items():
        if rel in new_packs:
            continue
        van = sarc_files(load(rel)[0])
        for k, b in sarc_files(data).items():
            if k in van and van[k] != b:
                edited[k].add(b)
                before[k] = van[k]
    out = []
    for rel in new_packs:
        files = dict(sarc_files(built[rel] if rel in built else load(rel)[0]))
        hit = False
        for k, b in list(files.items()):
            if k in edited and len(edited[k]) == 1 and b == before[k]:
                files[k] = next(iter(edited[k]))
                hit = True
        if hit:
            built[rel] = sarc_write(files)
            out.append(rel)
    return out


def check_shared_paths(final, load, romfs):
    """Every file inside a pack that the patch changes or adds has to end with the same bytes in every pack of the
    game that holds its path (tools/packpaths.py). The vanilla game never differs, and a path-keyed resource
    cache would hand one pack's copy to every actor. `final` is {pack rel: {inner: bytes}} for the patched packs.
    Returns [problem, ...]."""
    import hashlib
    import packpaths
    vanilla = {}

    def van(rel):
        if rel not in vanilla:
            vanilla[rel] = sarc_files(load(rel)[0])
        return vanilla[rel]

    changed = defaultdict(set)
    for rel, files in final.items():
        v = van(rel)
        for k, b in files.items():
            if v.get(k) != b:
                changed[k].add(rel)
    problems = []
    for inner in sorted(changed):
        holders = set(packpaths.carriers(inner, romfs)) | {rel for rel, files in final.items() if inner in files}
        by = defaultdict(list)
        for rel in sorted(holders):
            files = final[rel] if rel in final else van(rel)
            if inner in files:
                by[hashlib.sha1(files[inner]).hexdigest()[:10]].append(rel.rsplit("/", 1)[-1].replace(".pack.zs", ""))
        if len(by) > 1:
            parts = "; ".join(f"{len(v)} pack(s) [{', '.join(v[:4])}{', ...' if len(v) > 4 else ''}]"
                              for v in by.values())
            problems.append(f"{inner}: different bytes in different packs ({parts}); edit it in every pack that "
                            f"holds it (\"pack\": \"*\")")
    return problems


def clear_out_dir(out_dir):
    """A patch folder starts empty. Rebuilding a seed in place kept the old plan's extra files, and install.py (it
    installs every file in the folder) and in_game_check would then take them for this plan's. An earlier patch
    (one with patch_report.json) gets removed, and any other non-empty folder is refused."""
    import shutil
    if not os.path.isdir(out_dir) or not os.listdir(out_dir):
        return
    if not os.path.exists(os.path.join(out_dir, "patch_report.json")):
        raise PlanError(f"{out_dir} is not empty and is no earlier patch: give an empty or new folder")
    shutil.rmtree(out_dir)


EXEFS_NAME = re.compile(r"rando_of_time[A-Za-z0-9_-]*\.pchtxt")


def exefs_dir(out_dir):
    """Where a build's code patches go: an "exefs" folder beside the patch (romfs) folder, the way a Longshot mod
    holds them. install.py copies it into the mod."""
    return os.path.join(os.path.dirname(os.path.abspath(out_dir)), "exefs")


def write_exefs(out_dir, ops):
    """Writes the plan's code patches and removes the ones an earlier build left (ours only, by name). [names]"""
    d = exefs_dir(out_dir)
    if os.path.isdir(d):
        for name in os.listdir(d):
            if EXEFS_NAME.fullmatch(name):
                os.remove(os.path.join(d, name))
    names = []
    for op in ops:
        name, text = op["file"], op["text"]
        if not EXEFS_NAME.fullmatch(name) or "@nsobid-" not in text or "@enabled" not in text:
            raise PlanError(f"exefs: {name} is no Rando of Time .pchtxt code patch")
        if name in names:
            raise PlanError(f"exefs: {name} twice")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "wb") as f:
            f.write(text.encode("utf-8"))
        names.append(name)
    return names


CHEATS_NAME = re.compile(r"[0-9A-F]{16}\.txt")


def cheats_dir(out_dir):
    """Where a build's cheats file goes: a "cheats" folder beside the patch (romfs) folder, as in a Longshot mod."""
    return os.path.join(os.path.dirname(os.path.abspath(out_dir)), "cheats")


def write_cheats(out_dir, ops):
    """Writes the plan's cheats files (one per game build id) and removes the ones an earlier build left. [names]"""
    d = cheats_dir(out_dir)
    if os.path.isdir(d):
        for name in os.listdir(d):
            if CHEATS_NAME.fullmatch(name):
                os.remove(os.path.join(d, name))
    names = []
    for op in ops:
        name, text = op["file"], op["text"]
        if not CHEATS_NAME.fullmatch(name) or "[" not in text:
            raise PlanError(f"cheats: {name} is no cheats file (16 hex digits of the build id, .txt)")
        if name in names:
            raise PlanError(f"cheats: {name} twice")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "wb") as f:
            f.write(text.encode("utf-8"))
        names.append(name)
    return names


def _write(zs, dst, data, dict_id, compress):
    """Writes one patch file, zstd-compressed (the game's dictionary, level 16) when `compress`. main runs these on
    worker threads."""
    with open(dst, "wb") as f:
        f.write(zs.compress(data, dict_id) if compress else data)


def main(romfs, out_dir, *plan_paths):
    global ACTOR_PARAMS, AINB_FS
    for record in (INNER_GROWTH, NEW_INNER, NEW_INNER_SRC, NEW_EVENTS, _AINB_SOURCES):  # one build's records only
        record.clear()
    clear_out_dir(out_dir)
    ACTOR_PARAMS = ActorParams(romfs)
    plan = load_plans(plan_paths)
    for op in plan["new_files"]:  # new scene files "events" ops may edit (NEW_EVENTS)
        m = re.fullmatch(r"Event/EventFlow/([A-Za-z0-9_]+)\.bfevfl\.zs", op["to"])
        if m:
            NEW_EVENTS[m.group(1)] = op
    ACTOR_PARAMS.planned = planned_instance_keys(plan, romfs)
    catalog = {r["id"]: r for r in json.load(open(CATALOG, encoding="utf-8"))}
    fs = Romfs(romfs, VANILLA)
    AINB_FS = fs
    # Compressing the written files (zstd level 16) took a quarter of a build on one core, so it runs on worker
    # threads (zstd releases the GIL and the bytes come out the same). Every write has finished before the report
    # gets written.
    from concurrent.futures import ThreadPoolExecutor
    pool, writes, last = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)), [], {}

    def write(dst, data, did, compress):
        key = os.path.normcase(os.path.normpath(dst))
        if key in last:  # a file written again, the earlier write finishes first so the last one still wins
            last[key].result()
        last[key] = pool.submit(_write, fs.zs, dst, bytes(data), did, compress)
        writes.append(last[key])

    place_ops, event_ops, report, warnings = compile_plan(plan, romfs, catalog)
    patch_events = trade_slot_stage(plan, romfs, event_ops, warnings)

    rstb_raw = fs.raw(RSTB_PATH)
    rstb = Restbl(fs.zs.decompress(rstb_raw))
    written = []
    pack_ops, byml_ops, copy_ops = defaultdict(list), defaultdict(list), defaultdict(list)
    for op in plan["packs"]:  # "pack" can be a list, or "*" for every pack holding the file
        for pk in op_packs(op, romfs):
            pack_ops[pk].append(dict(op, pack=pk))
    ainb_ops = defaultdict(list)
    for op in plan["ainb"]:  # AI files in a pack are edited in the same pass as the pack's other files
        if op.get("pack"):
            for pk, one in expand_ainb_op(op, romfs):
                pack_ops[pk].append({"_ainb": one})
        elif "file" not in op or op["file"].endswith(".zs"):
            raise PlanError(f"{op['file']}: ainb edits are for .ainb files (loose or in a pack)")
        else:
            ainb_ops[op["file"]].append(op)
    reused = defaultdict(list)
    for op in plan["byml"]:
        byml_ops[op["file"]].append(op)
        if "replace_row" in op:
            # Compare the source row and every field the op sets, since two flowcharts can share an entry name
            # and an op can leave the entry unset.
            spec = op["replace_row"]
            reused[(op["file"], spec["row"])].append(
                json.dumps({k: v for k, v in spec.items() if k != "row"}, sort_keys=True))
    clash = {row: eps for (f, row), eps in reused.items() if len(set(map(str, eps))) > 1}
    if clash:  # two features took the same scene ID, the last one would silently win
        raise PlanError("scene IDs reused twice with different scenes: " +
                        "; ".join(f"{row} ({', '.join(map(str, eps))})" for row, eps in clash.items()))
    # Every scene ID with a scene file needs a row in the precomputed scene-info table, or the game aborts
    # at startup. So we mirror each new EventSetting row there, copied from the same source.
    have = {op["replace_row"]["row"] for op in byml_ops.get(ANALYZED, []) if "replace_row" in op}
    for op in byml_ops.get(EVENT_SETTING, []):
        if "replace_row" in op and op["replace_row"]["row"] not in have:
            byml_ops[ANALYZED].append({"replace_row": {"row": op["replace_row"]["row"],
                                                       "copy_of": op["replace_row"]["copy_of"]}})
            warnings.append(f"scene ID {op['replace_row']['row']}: its precomputed scene-info row now copies "
                            f"{op['replace_row']['copy_of']}'s")
    have_new = {(op["add_row"].get("set") or {}).get("__RowId") for op in byml_ops.get(ANALYZED, []) if "add_row" in op}
    for op in byml_ops.get(EVENT_SETTING, []):  # new rows ("grow") get a new scene-info row copied from
        if "add_row" in op:                     # "analyzed_copy_of", or else from the EventSetting row's source
            spec = op["add_row"]
            new_id = (spec.get("set") or {}).get("__RowId")
            if not new_id:
                raise PlanError(f"{EVENT_SETTING}: add_row needs set.__RowId")
            if new_id not in have_new:
                byml_ops[ANALYZED].append({"add_row": {"copy_of": spec.get("analyzed_copy_of") or spec["copy_of"],
                                                       "set": {"__RowId": new_id}}})
                have_new.add(new_id)

    new_event_files = {op["to"]: op for op in NEW_EVENTS.values()}
    # new actor packs (a copy of a vanilla pack that "packs" ops then fill, like OotrR's new actor types and our
    # hold-up displays from progressive.display_ops) are built the same way. They get the source pack's size-table
    # entry plus their growth and are marked new for tools/install.py
    new_event_files.update({op["to"]: op for op in plan["new_files"]
                            if re.fullmatch(r"Pack/Actor/[A-Za-z0-9_]+\.pack\.zs", op["to"])})

    def load(rel):
        if rel in new_event_files:  # a new scene file is its source renamed (the "new_files" op)
            op = new_event_files[rel]
            data, did = load(op["from"])
            return rename_strings(data, op.get("rename", []), rel), did
        raw = fs.raw(rel)
        if rel.endswith(".zs"):
            return fs.zs.decompress(raw), fs.zs.dict_id(raw)
        return raw, None

    for op in plan["copy"]:
        if not os.path.exists(os.path.join(romfs, op["to"])):
            raise PlanError(f"copy target {op['to']} does not exist in the game")
        copy_ops[op["to"]].append(dict(op, _data=load(op["from"])[0]))
    def run(rel, ops, patcher):
        data, did = load(rel)
        new = patcher(data, ops, rel)
        if new == data and rel not in new_event_files:
            return data, new
        key = rel[:-3] if rel.endswith(".zs") else rel
        if rel in new_event_files:  # a new scene file: the checks of "new_files", then the source's entry to start from
            src = new_event_files[rel]["from"]
            if (os.path.exists(os.path.join(romfs, rel)) and os.path.normpath(rel) not in installed_new_files(romfs)) or \
                    rstb.get(key) is not None or zlib.crc32(key.encode()) in rstb.crc:
                raise PlanError(f"new file {rel} already exists in the game, or its size-table hash is taken")
            base = rstb.get(src[:-3] if src.endswith(".zs") else src)
            if base is None:
                raise PlanError(f"new file {rel}: no size-table entry to copy from {src}")
            rstb.set(key, base)
            dst = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            write(dst, new, did, True)
            need = entry_for(key, base, data, new)
            rstb.set(key, max(base, need))
            written.append({"file": rel, "new": True, "from": src, "size": [len(data), len(new)],
                            "size_table": [None, rstb.get(key)]})
            return data, new
        fs.snapshot(rel)  # keep the vanilla file before we ever install a change to it
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        write(dst, new, did, rel.endswith(".zs"))
        old_entry = rstb.get(key)
        if old_entry is not None:  # the game's rule for its type, not just its growth (entry_for)
            need = entry_for(key, old_entry, data, new)
            if need > old_entry:
                rstb.set(key, need)
            if len(new) > old_entry:  # wouldn't load with the game's sizes
                warnings.append(f"{rel}: grows past its size-table entry ({len(new)} > {old_entry}); "
                                f"install with tools/install.py, which raises it in Longshot's own table too")
        written.append({"file": rel, "size": [len(data), len(new)], "size_table": [old_entry, rstb.get(key)]})
        return data, new

    for rel, ops in progress.span(place_ops.items(), 0.06, 0.29):
        run(rel, ops, patch_placement)
    # Scene files first, so the precomputed scene info can follow what they now hand off to.
    patched_events = {}
    for rel, ops in progress.span(sorted(event_ops.items(), key=lambda kv: re.search(r"\.\d{3}\.bfevfl", kv[0]) is None),
                                  0.29, 0.50):
        old, new = run(rel, ops, patch_events)  # newest version (Name.110.bfevfl.zs) first, the game reads that one
        if new != old:
            patched_events.setdefault(os.path.basename(rel).split(".")[0], (old, new))
    rewired = {}  # scene IDs the plan points at another scene: ID -> (row copied, scene file, entry point)
    if byml_ops.get(EVENT_SETTING):
        es = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}
        for op in byml_ops[EVENT_SETTING]:
            if "replace_row" in op:
                spec = op["replace_row"]
                row = dict(es.get(spec["copy_of"], {}), **spec.get("set", {}))
                rewired[spec["row"]] = (spec["copy_of"],
                                        (row.get("FlowchartFileName") or "").rsplit("/", 1)[-1].replace(".evfc", ""),
                                        row.get("EntryPointName"))
            elif "add_row" in op:  # a new row ("grow"), its lists start from the scene-info row it copies
                spec = op["add_row"]
                row = dict(es.get(spec["copy_of"], {}), **spec.get("set", {}))
                rewired[row["__RowId"]] = (spec.get("analyzed_copy_of") or spec["copy_of"],
                                           (row.get("FlowchartFileName") or "").rsplit("/", 1)[-1].replace(".evfc",
                                                                                                           ""),
                                           row.get("EntryPointName"))
    byml_ops[ANALYZED] += sync_scene_info(fs, romfs, patched_events, rewired, warnings)
    if not byml_ops[ANALYZED]:
        del byml_ops[ANALYZED]
    built = {rel: patch_pack(load(rel)[0], ops, rel)  # checked before writing
             for rel, ops in progress.span(pack_ops.items(), 0.58, 0.69)}
    for rel in sync_new_packs(built, sorted(r for r in new_event_files if r.startswith("Pack/Actor/")), load):
        pack_ops.setdefault(rel, [])  # (a copy with no op of its own is written with the synced files)
    shared = check_shared_paths({rel: sarc_files(new) for rel, new in built.items() if new != load(rel)[0]}, load,
                                romfs)
    if shared:  # one path with different bytes in different packs, whichever pack loads first would win
        raise PlanError("files inside packs must be edited alike in every pack that holds them:\n  " +
                        "\n  ".join(shared))
    for rel in pack_ops:
        run(rel, [built[rel]], lambda data, ops, rel: ops[0])
    for key, grow in sorted(INNER_GROWTH.items()):  # AI files and tables grown inside packs by "ainb" edits
        old_entry = rstb.get(key)
        if old_entry is not None:
            rstb.set(key, old_entry + ((grow + 31) & ~31))
            written.append({"file": key, "inside_pack": True, "size_table": [old_entry, rstb.get(key)]})
    for key, (src, src_size, size) in sorted(NEW_INNER.items()):  # files added inside packs get an entry of their own
        base = rstb.get(src)
        if base is None:
            raise PlanError(f"{key}: its source {src} has no size-table entry to start from")
        if rstb.get(key) is None or rstb.get(key) < base:
            rstb.set(key, base + ((max(0, (size or src_size) - src_size) + 31) & ~31))
            written.append({"file": key, "inside_pack": True, "new": True, "size_table": [None, rstb.get(key)]})
    # every file a pack op changed or added gets at least what the game's rule for its type asks (entry_for), and
    # then has to fit it. The game sizes the file's heap by the entry, parsed blocks included
    vanilla = Restbl(fs.zs.decompress(rstb_raw))
    short, ruled = [], set()
    for rel, new in built.items():
        if new == load(rel)[0]:
            continue
        old_files = sarc_files(load(rel)[0])
        for key, data in sarc_files(new).items():
            if old_files.get(key) == data:
                continue
            if key not in ruled:
                ruled.add(key)
                if key in old_files:
                    base, old = vanilla.get(key), old_files[key]
                else:  # an added file, from the one it was copied from
                    base, old = vanilla.get(NEW_INNER.get(key, (key,))[0]), NEW_INNER_SRC.get(key)
                need = entry_for(key, base, old, data)
                if need is not None and (base is not None or key in NEW_INNER) and \
                        (rstb.get(key) is None or rstb.get(key) < need):
                    written.append({"file": key, "inside_pack": True, "rule": True,
                                    "size_table": [rstb.get(key), need]})
                    rstb.set(key, need)
            entry = rstb.get(key)
            if entry is not None and entry < max(len(data), rule_entry(key, data) or 0):
                short.append(f"{rel}:{key} is {len(data)} bytes, its size-table entry {entry} "
                             f"(its type asks {rule_entry(key, data)})")
    if short:
        raise PlanError("size-table entries smaller than their files:\n  " + "\n  ".join(sorted(set(short))))
    for rel, ops in progress.span(byml_ops.items(), 0.73, 0.77):
        _, new = run(rel, ops, patch_byml)
        if rel == ANALYZED:  # the game looks these lists up in its own order (scene_order)
            unordered = check_scene_order(byml_load(new, allow_big=True)[0])
            if unordered:
                raise PlanError("scene-info lists out of the game's order: " + ", ".join(unordered))
    for rel, ops in copy_ops.items():
        run(rel, ops, patch_copy)
    names_ops = defaultdict(list)  # same-length renames of pooled names in any file (a model's texture name)
    for op in plan["names"]:
        names_ops[op["file"]].append(op)
    for rel, ops in names_ops.items():
        run(rel, ops, patch_names)
    ours = installed_new_files(romfs)
    for op in plan["new_files"]:  # a new game file, a same-size copy of a vanilla file with its names renamed
        rel = op["to"]
        if any(w.get("file") == rel for w in written):  # a new scene file "events" ops already built (NEW_EVENTS)
            continue
        if os.path.exists(os.path.join(romfs, rel)) and os.path.normpath(rel) not in ours:
            raise PlanError(f"new file {rel} already exists in the game")
        data, did = load(op["from"])
        src_len = len(data)
        if op.get("segments"):  # a new file of another size, made of the source's byte ranges, padding and new bytes
            data = splice_segments(data, op["segments"], rel)
        new = patch_bytes(rename_strings(data, op.get("rename", []), rel), op.get("bytes", []), rel)
        key, src_key = (r[:-3] if r.endswith(".zs") else r for r in (rel, op["from"]))
        entry = rstb.get(src_key)
        if entry is None or rstb.get(key) is not None:
            raise PlanError(f"new file {rel}: no size-table entry to copy from {src_key}, or {key} already has one")
        if zlib.crc32(key.encode()) in rstb.crc:
            raise PlanError(f"new file {rel}: its size-table hash is another file's")
        entry += len(new) - src_len  # the source's overhead over its size, so a same-size copy gets the source's entry
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        write(dst, new, did, rel.endswith(".zs"))
        rstb.set(key, entry)
        written.append({"file": rel, "new": True, "size_table": [None, entry], "from": op["from"]})
    if any(plan["cosmetics"].values()):  # binary edits, same size (the map icons grow the UI's two archives)
        sys.path.insert(0, os.path.join(HERE, "tools", "rando", "parity"))
        import _cosmetics_apply
        _, cos_files = _cosmetics_apply.build(romfs, plan["cosmetics"])
        for rel, new in sorted(cos_files.items()):
            run(rel, [new], lambda data, ops, rel: ops[-1])
    if plan["gamedata"]:
        run(GAMEDATA, plan["gamedata"], patch_gamedata)
    binary_ops = defaultdict(list)
    for op in plan["binary"]:
        if op["file"].endswith(".zs"):
            raise PlanError(f"{op['file']}: binary edits are for uncompressed files")
        binary_ops[op["file"]].append(op)
    for rel, ops in binary_ops.items():
        run(rel, ops, patch_binary)
    for rel, ops in ainb_ops.items():
        if rel in binary_ops:
            raise PlanError(f"{rel}: both binary and ainb edits (use ainb edits only)")
        run(rel, ops, patch_ainb)
    text_ops = defaultdict(list)  # "lang": "*" means every language
    langs = msbt.archives(romfs)
    for op in plan["text"]:
        for lang, rel in langs.items():
            if op.get("lang", "*") in ("*", lang):
                text_ops[rel].append(op)
    for rel, ops in progress.span(text_ops.items(), 0.92, 0.94):
        run(rel, ops, patch_text)

    if written:
        fs.snapshot(RSTB_PATH)
        dst = os.path.join(out_dir, RSTB_PATH)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        write(dst, rstb.dump(), fs.zs.dict_id(rstb_raw), True)
    for w in progress.span(writes, 0.94, 0.95):  # every file is on disk (a failed write raises here)
        w.result()
    pool.shutdown()
    os.makedirs(out_dir, exist_ok=True)
    for w in warnings:
        print("  note:", w)
    changed = [r for r in report if r["from"] != r["to"]]
    exefs = write_exefs(out_dir, plan["exefs"])
    cheats = write_cheats(out_dir, plan.get("cheats") or [])
    report_json = {"rewards_changed": changed, "notes": warnings, "files": written}
    if exefs:
        report_json["exefs"] = exefs
    if cheats:
        report_json["cheats"] = cheats
    json.dump(report_json, open(os.path.join(out_dir, "patch_report.json"), "w",
              encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(changed)} rewards changed ({len(report)} listed), "
          f"{len(plan['placements'])} raw placement edits, {len(plan['events'])} raw event edits, "
          f"{len(plan['packs'])} pack edits, {len(plan['byml'])} data-file edits, {len(plan['copy'])} file copies, "
          f"{sum(len(op.get('defaults', {})) for op in plan['gamedata'])} save-data defaults, "
          f"{sum(len(op.get('reset_type', {})) for op in plan['gamedata'])} reset types, "
          f"{sum(len(op.get('boolexp', {})) for op in plan['gamedata'])} expressions, "
          f"{len(plan['binary'])} number edits" + (f", {len(plan['ainb'])} AI file edits" if plan["ainb"] else ""))
    print(f"{len(written)} game files written to {out_dir}" + (" + size table" if written else ""))
    if exefs:
        print(f"{len(exefs)} code patch(es) written to {exefs_dir(out_dir)}: the game has to be built again in "
              f"Longshot after installing")
    if cheats:
        print(f"cheats file written to {cheats_dir(out_dir)} (switches in Longshot's Insert menu, the Mods tab)")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    try:
        main(*sys.argv[1:])
    except PlanError as e:
        sys.exit(f"plan error: {e}")
