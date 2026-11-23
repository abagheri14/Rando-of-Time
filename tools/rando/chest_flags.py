"""Chest save flags: how the remake remembers an opened chest, what the tracker reads, and the read-back.

How the game does it:
- Every chest type with the TreasureBox AI (CHEST_TYPES: Obj_TBox_A_01/02/03/06, their NoBake and memo11 copies, the
  Lens chest, and the Treasure Chest Game's Obj_HrlCity_Shop_TBox_A_01/02) saves that it was opened in the Bool
  IsTreasureBoxOpen.<placement Hash, in decimal>. That Bool is a member of the GameData struct IsTreasureBoxOpen,
  which has 206 members, one per chest placement in the game, each with SaveFileIndex 0 and ResetTypeValue 24
  (never reset).
  - The chest's event AI writes it (AI/TreasureBox.event.root.ainb, command EventTriggerTreasureBoxOpened, node 5).
    That node is a OneShotSetGameDataBool with ParentStruct IsTreasureBoxOpen, and the member comes from
    QueryGenericGetInstanceId's InstanceIDString. It isn't written if the placement sets IsEnableRepeatOpen.
    Every chest scene gets to that command on TreasureBox_EventStarter. Dm_SY_TreasureboxSmall and
    Dm_SY_Treasurebox do it directly, the story scenes (Navi chats, sages, the Treasure Chest Game, Dampe's race)
    go through an EventTransition to them, and our own scenes (progressive items, traps, dungeon credits) do it
    with their "markopened" step.
  - AI/TreasureBox.module.ainb reads it (QueryGetGameDataBool on the same struct and name, OR'd with the
    blackboard's IsOpened), and the chest spawns open.
  - It's not the placement's Bool64bitKey. Chests have ActorGameDataSetting AlwaysRespawn, so that per-object row
    is never written (0 of 152 chest hashes in my 6 saves, and OotrR's chest_flags.py found the same). All 6 saves
    hold IsTreasureBoxOpen.4555665598794293658 = true, which is KF Midos Bottom Left Chest, opened in all of them.
- Exceptions:
  - Obj_TBox_A_04, the remake's ice-trap chest, breaks instead. It has ActorGameDataSetting NoRespawn, so its
    Bool64bitKey (ResetTypeValue 24) is written when it dies, and an Ice Trap left in it is tracked by that
    per-object flag.
  - An A_04 spot holding a real item becomes Obj_TBox_A_01 (parity/chests.py). Its hash has no struct member, so
    it would never save being opened. It would close again on the next visit, give its item again, and nothing
    could track it. struct_op() adds the six IsTreasureBoxOpen.<hash> rows and members (make_patch gamedata
    "add_struct_bools"), so the vanilla chest AI saves and reads them like any other chest (no AI or scene change,
    nothing per frame).
  - The Treasure Chest Game reward chest has IsEnableRepeatOpen. Its check is MiniGame_ChoiceTreasure_IsClear,
    which is saved, and its scene sets it right after the reward. The salesman (shuffle_tcgkeys 'remove') uses
    _chests_tcg.SOLD_FLAG.

tracker_flags() gives every chest location its flags (tools/tracker/build_data.py seed), and verify() reads each one
back from a built patch (tools/rando/in_game_check.py).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"

STRUCT = "IsTreasureBoxOpen"
OPENED_ACTION, OPENED_ACTOR = "EventTriggerTreasureBoxOpened", "TreasureBox_EventStarter"
SAVED_RESET = 24  # ResetTypeValue of the struct members (never reset)
TRAP = "Obj_TBox_A_04"
# chest type -> its default GetEventName (the blackboard InitVal, followed through the actor's $parent chain). That's
# the scene a placement runs when it doesn't set its own GetEventName. All of them are AlwaysRespawn, with event AI
# TreasureBox.event.root and a root AI that goes through TreasureBox.module (which reads the flag).
CHEST_TYPES = {
    "Obj_TBox_A_01": "Dm_SY_TreasureboxSmall", "Obj_TBox_A_01_NoBake": "Dm_SY_TreasureboxSmall",
    "Obj_TBox_A_01_memo11": "HrlField_Note_11_Treaurebox_D_T", "Obj_TBox_A_02": "Dm_SY_Treasurebox",
    "Obj_TBox_A_02_NoBake": "Dm_SY_Treasurebox", "Obj_TBox_A_03": "Dm_SY_Treasurebox",
    "Obj_TBox_A_03_NoBake": "Dm_SY_Treasurebox", "Obj_TBox_A_06": "Dm_SY_TreasureboxSmall",
    "Obj_TBox_A_06_NoBake": "Dm_SY_TreasureboxSmall", "Obj_TBox_GlassTruth_A_01": "Dm_SY_TreasureboxSmall",
    "Obj_HrlCity_Shop_TBox_A_01": "Dm_SY_Treasurebox", "Obj_HrlCity_Shop_TBox_A_02": "Dm_SY_Treasurebox"}
TCG_CLEAR = "MiniGame_ChoiceTreasure_IsClear"  # saved; MiniGame_SequentialChoiceTreasure_ClearFlagOn sets it
TCG_FLOW = "MiniGame_SequentialChoiceTreasure"
SET_BOOL = "EventTriggerSetGameDataBool"

_data = {}


def _load(key, *path):
    if key not in _data:
        _data[key] = json.load(open(os.path.join(HERE, *path), encoding="utf-8"))
    return _data[key]


def _catalog():
    """chest reward id ("Area/chest/<hash>") -> data/rewards.json record."""
    if "cat" not in _data:
        _data["cat"] = {r["id"]: r for r in _load("rewards", "data", "rewards.json") if r["kind"] == "chest"}
    return _data["cat"]


def flag_name(h):
    return f"{STRUCT}.{int(h)}"


# The six trap chests are logic-driven. They share one module, Gimmick_TrapTreasureBox_Set, with an instance per spot
# (Ganon's Castle's four as AiGroups of their own, Spirit's and the Training Ground's inside their room prefab), and its
# actor node is ActorLogicTrapTreasureBox.
# A plain chest (Obj_TBox_A_01, ActorLogicNodeRef ActorLogicTreasureBox) reads its lock from that node, through its root
# AI's QueryLogicGetBool "Unlock" (AI/Obj_TBox_A_01.root.ainb node 57, inverted into TreasureBox.module's Locked). The
# trap node has no Unlock, so a converted spot bound to it shows up and stays locked, with no open prompt (Spirit Temple
# First Mirror Left Chest did exactly that).
# Making the module's actor node the plain chest's and cutting the trap's open event (TrapTreasureBoxOpen) is
# all-or-nothing, and a seed can mix the two. With an ice trap kept in one of the six, that edit left the five converted
# ones locked. So trap_module_op keeps the module's trap node and gives it a second actor node, the plain chest's
# ActorLogicTreasureBox. It's a copy of the Fall-appear module's (Unlock true, isSpawnAct the module's own input,
# Logic_Create true) under its own instance name, TRAP_CHEST_INSTANCE.
# Each instance's actor is bound by the AiGroups reference in its level file (Id, and a Path ending in the instance
# name). A converted spot's reference names the chest node (make_patch "groups" "rebind"), and a spot keeping its trap
# still names the trap node. So each instance binds one of the two nodes and leaves the other without an actor. Vanilla
# does the same with 3 of the ActorLogicKakarikoBurnObject nodes of its Kakariko town prefab, in every Kakariko level (9
# unbound nested actor nodes in 3236).
# A converted spot's trap node has no actor, so its open event (node 1, fed by the trap node's isReceiveOpen) never
# fires. A trap spot's trap node, event and autogen flag are vanilla.
TRAP_MODULE = "Logic/Gimmick_TrapTreasureBox_Set_cbc2.logic.module.ainb"
TRAP_INSTANCE = "Obj_TBox_A_04_1d8f"
TRAP_CHEST_INSTANCE = "Obj_TBox_A_01_7b3e"  # the plain chest node a converted spot is bound to
TRAP_HASHES = (876108895472176682, 3253191540272036329, 5732331492537302993, 7881496104962067240,
               11406545451127340703, 17726220643880970879)  # every placement the module drives (read back in verify)
CHEST_NODE_SRC = {"file": "Logic/Gimmick_TreasureBoxAppear_Fall_c6e5.logic.module.ainb"}
CHEST_NODE = 4  # its ActorLogicTreasureBox (Obj_TBox_A_01_NoBake_8fbc)


def trap_module_op(converted):
    """make_patch "ainb" entry that gives the trap-chest module its plain chest node if any spot is converted, else
    None."""
    if not converted:
        return None
    return {"file": TRAP_MODULE, "edits": [
        {"copy": {"from": CHEST_NODE_SRC, "nodes": [CHEST_NODE], "label": "chest", "follow": False,
                  "values": {str(CHEST_NODE): {"Logic_Create": True, "Unlock": True, "isRepeatContents": False,
                                               "SealAttentionSender": False, "isSpawnAct": False}}}},
        {"set_property": {"node": f"chest:{CHEST_NODE}", "name": "InstanceName", "value": TRAP_CHEST_INSTANCE}},
        {"feed": {"from": 3, "output": "isSpawnAct", "to": f"chest:{CHEST_NODE}", "input": "isSpawnAct"}}]}


def trap_rebind_ops(converted):
    """make_patch "groups" entries that bind each converted spot to the module's chest node (trap_module_op). In each of
    the spot's level files, its AiGroups reference names TRAP_CHEST_INSTANCE instead of the trap node."""
    cat = {int(r["hash"]): r for r in _catalog().values() if r.get("actor") == TRAP}
    return [{"file": f, "rebind": {"reference": str(int(h)), "from": TRAP_INSTANCE, "to": TRAP_CHEST_INSTANCE}}
            for h in sorted({int(x) for x in converted}) for f in cat[h]["files"]]


def _trap_refs(fs, hashes):
    """{hash: [(Id, the last part of Path) of each AiGroups reference to it]} in its level files."""
    from romtools import byml_load
    cat = {int(r["hash"]): r for r in _catalog().values() if r.get("actor") == TRAP}
    out = {}
    for h in hashes:
        for f in cat[h]["files"]:
            root = byml_load(fs.read(f))
            root = root[0] if isinstance(root, tuple) else root
            for g in root.get("AiGroups") or []:
                for ref in g.get("References") or []:
                    if int(ref.get("Reference", 0)) == h:
                        out.setdefault(h, []).append((ref.get("Id"), str(ref.get("Path", "")).rsplit("/", 1)[-1]))
    return out


def verify_trap_module(fs, converted):
    """Checks the trap-chest module and returns [problem]. The module has to keep its trap node and event (for the spots
    keeping a trap) and have the plain chest node, unlocked, with isSpawnAct as its own input. Each converted spot has
    to be bound to the chest node and every other spot to the trap node."""
    import ainb
    converted = {int(h) for h in converted}
    if not converted:
        return []
    bad = []
    a = ainb.Ainb(fs.raw(TRAP_MODULE))

    def actor_nodes(inst):
        return [i for i, n in enumerate(a.nodes) if n["name"].startswith("ActorLogic")
                and any(e["name"] == "InstanceName" and e["value"] == inst for e in n["properties"]["string"])]
    trap, chest = actor_nodes(TRAP_INSTANCE), actor_nodes(TRAP_CHEST_INSTANCE)
    if [a.nodes[i]["name"] for i in trap] != ["ActorLogicTrapTreasureBox"]:
        bad.append(f"{TRAP_MODULE}: {TRAP_INSTANCE} is {[a.nodes[i]['name'] for i in trap]}, not the vanilla trap "
                   f"node (a spot keeping its ice trap needs it)")
    else:
        ev = next((e for e in a.nodes[1]["inputs"]["bool"] if e["name"] == "EventRequestTrigger"), None)
        if a.nodes[1]["name"] != "ActorLogicEventRequestActor" or ev is None or ev.get("node") != trap[0]:
            bad.append(f"{TRAP_MODULE}: the trap's open event no longer follows the trap node")
    if [a.nodes[i]["name"] for i in chest] != ["ActorLogicTreasureBox"]:
        bad.append(f"{TRAP_MODULE}: {TRAP_CHEST_INSTANCE} is {[a.nodes[i]['name'] for i in chest]}, not one "
                   f"ActorLogicTreasureBox (a converted spot stays locked)")
    else:
        ins = {e["name"]: e for e in a.nodes[chest[0]]["inputs"]["bool"]}
        if ins.get("Unlock", {}).get("value") is not True or ins["Unlock"].get("node", -1) != -1:
            bad.append(f"{TRAP_MODULE}: the chest's Unlock isn't a constant true")
        if ins.get("isSpawnAct", {}).get("node") != 3:
            bad.append(f"{TRAP_MODULE}: the chest's isSpawnAct isn't the module's input")
        if ins.get("Logic_Create", {}).get("value") is not True or ins["Logic_Create"].get("node", -1) != -1:
            bad.append(f"{TRAP_MODULE}: the chest's Logic_Create isn't a constant true")
    refs = _trap_refs(fs, TRAP_HASHES)
    for h in TRAP_HASHES:
        want = TRAP_CHEST_INSTANCE if h in converted else TRAP_INSTANCE
        got = refs.get(h, [])
        if got != [(want, want)]:
            bad.append(f"{TRAP_MODULE}: trap-chest spot {h} ({'converted' if h in converted else 'keeps its trap'}) "
                       f"is bound to {got}, want [{want}]")
    return bad


def struct_op(hashes):
    """make_patch gamedata op giving these placement hashes a saved IsTreasureBoxOpen member each."""
    return {"add_struct_bools": {STRUCT: [str(int(h)) for h in sorted({int(x) for x in hashes})]}}


def converted_traps(rewards):
    """Hashes of the remake's ice-trap chests (Obj_TBox_A_04) a plan's rewards turn into another chest type."""
    cat = _catalog()
    out = []
    for rid, spec in (rewards or {}).items():
        r = cat.get(rid)
        gy = ((spec or {}).get("extra") or {}).get("Gyaml") if isinstance(spec, dict) else None
        if r and r.get("actor") == TRAP and gy and gy != TRAP:
            out.append(int(r["hash"]))
    return sorted(out)


def location_chests(names):
    """{location: [chest reward id, ...]} for the locations in `names` that are remake chests. They come from:
    - data/rando/chest_map.json, in every mode (a vanilla-mode chest keeps its item but is still a check)
    - the chests the dungeons plugin pairs where chest_map doesn't play its own way (dungeons_world.json kept_chests,
      as parity/dungeons.py _remake_of)
    - chests_locations.json 'new' and 'paired', with their 'also' chests
    - the Treasure Chest Game rooms"""
    from parity import _chests_tcg as tcg
    names = set(names)
    out = {}

    def add(n, ids):
        if n in names:
            for rid in ids:
                if rid and rid not in out.setdefault(n, []):
                    out[n].append(rid)
    chest_map = _load("chest_map", "data", "rando", "chest_map.json")["chests"]
    kept = _load("dungeons_world", "data", "rando", "dungeons_world.json").get("kept_chests") or {}
    for n, e in chest_map.items():
        if n not in kept or e.get("mode") in ("full", "group"):
            add(n, [e.get("remake")])
    for n, rid in kept.items():
        if (chest_map.get(n) or {}).get("mode") not in ("full", "group"):
            add(n, [rid])
    cl = _load("chests_locations", "data", "rando", "chests_locations.json")
    for sec in ("new", "paired"):
        for n, e in (cl.get(sec) or {}).items():
            if isinstance(e, dict):
                add(n, [e.get("remake")] + list(e.get("also") or []))
    for n, rid in tcg.ROOMS.items():
        add(n, [rid])
    return out


def _tcg_reward():
    cl = _load("chests_locations", "data", "rando", "chests_locations.json")
    return {e["remake"] for e in (cl.get("paired") or {}).values() if isinstance(e, dict) and e.get("kind") == "tcg_reward"}


def _renames(plan):
    """{(level file, old hash): new hash} for placements another plugin gives a chest's hash (chests 'share_flag')."""
    return {(op["file"], int(op["hash"])): int(op["set"]["Hash"]) for op in (plan or {}).get("placements", [])
            if "Hash" in (op.get("set") or {})}


def _final_hashes(r, renames):
    """The placement hashes a chest reward record ends up with in its level files."""
    return sorted({renames.get((f, int(r["hash"])), int(r["hash"])) for f in r["files"]} or {int(r["hash"])})


def tracker_flags(names, plan, settings=None):
    """{location: [tracker flag, ...]} for every chest location of a seed, plus the Treasure Chest Game salesman.
    - a chest: {"t": "bool", "n": IsTreasureBoxOpen.<hash>}
    - an Ice Trap left in the remake's trap chest: {"t": "b64", "h": hash}
    - the Treasure Chest Game reward and salesman: the minigame's saved flags"""
    from parity import _chests_tcg as tcg
    cat, renames = _catalog(), _renames(plan)
    converted = set(converted_traps((plan or {}).get("rewards")))
    reward = _tcg_reward()
    out = {}
    for n, rids in location_chests(names).items():
        flags = []
        for rid in rids:
            r = cat.get(rid)
            if r is None:
                continue
            if rid in reward:  # IsEnableRepeatOpen skips the opened flag. The scene saves the minigame clear.
                flags.append({"t": "bool", "n": TCG_CLEAR})
                continue
            for h in _final_hashes(r, renames):
                if r["actor"] == TRAP and int(r["hash"]) not in converted:
                    flags.append({"t": "b64", "h": str(h)})
                elif r["actor"] in CHEST_TYPES or r["actor"] == TRAP:
                    flags.append({"t": "bool", "n": flag_name(h)})
            taken = (((plan or {}).get("_tcg_rooms") or {}).get("taken") or {}).get(rid)
            if taken:  # a room chest, its opened member is cleared at the next game but its record stays (_chests_tcg)
                flags.append({"t": "bool", "n": taken})
        uniq = []
        for f in flags:
            if f not in uniq:
                uniq.append(f)
        if uniq:
            out[n] = uniq
    tcg_mode = (settings or {}).get("shuffle_tcgkeys") if isinstance(settings, dict) else getattr(
        settings, "shuffle_tcgkeys", None)
    if tcg.SALESMAN in set(names) and tcg_mode == "remove":  # the sale is saved once (Rando_TcgStart)
        out[tcg.SALESMAN] = [{"t": "bool", "n": tcg.SOLD_FLAG}]
    return out


# Read-back (tools/rando/in_game_check.py)
def _flows(fs, patch_dir, romfs):
    """name -> the newest event-flow file of that name (rel path), the patch's new files included."""
    pat = re.compile(r"^(.+?)(?:\.(\d{3}))?\.bfevfl\.zs$")
    best = {}
    for d in (os.path.join(romfs, "Event", "EventFlow"), os.path.join(patch_dir, "Event", "EventFlow")):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            m = pat.match(f)
            if m:
                v = int(m.group(2) or -1)
                if m.group(1) not in best or v > best[m.group(1)][0]:
                    best[m.group(1)] = (v, "Event/EventFlow/" + f)
    return {k: v[1] for k, v in best.items()}


class _Scenes:
    """Which actions a scene (an EventSetting row) reaches in the patched files. That's its entry point, its sub-flows
    in the same file and in other files, and the events it hands over to (EventTransition and other steps naming an
    EventName row)."""

    def __init__(self, fs, patch_dir, romfs):
        from romtools import byml_load
        self.fs, self.files, self.parsed = fs, _flows(fs, patch_dir, romfs), {}
        self.rows = {r.get("__RowId"): r for r in byml_load(fs.read(EVENT_SETTING))[0]}

    def flow(self, name):
        if name not in self.parsed:
            from evfl import Evfl
            rel = self.files.get(name)
            self.parsed[name] = Evfl(self.fs.read(rel)) if rel else None
        return self.parsed[name]

    def row_entry(self, row_id):
        r = self.rows.get(row_id) or {}
        f = str(r.get("FlowchartFileName", ""))
        if not f.endswith(".evfc") or "EntryPointName" not in r:
            return None
        return f.rsplit("/", 1)[-1][:-len(".evfc")], r["EntryPointName"]

    def reaches(self, row_id, test):
        """Steps (file:entry:event) of scene `row_id` for which test(actor name, action, params) is true."""
        start = self.row_entry(row_id)
        if start is None:
            return []
        hits, seen, todo = [], set(), [start]
        while todo:
            key = todo.pop()
            if key in seen:
                continue
            seen.add(key)
            fname, entry = key
            ev = self.flow(fname)
            if ev is None:
                continue
            for fc in ev.flowcharts:
                ep = fc["entry_points"].get(entry)
                if not ep:
                    continue
                stack, vis = [ep["main"]], set()
                while stack:
                    i = stack.pop()
                    if i == 0xFFFF or i in vis or i >= len(fc["events"]):
                        continue
                    vis.add(i)
                    e = fc["events"][i]
                    if e["type"] == "action":
                        a = fc["actors"][e["actor"]]
                        params = {k: v.get("value") for k, v in ((e.get("params") or {}).get("items") or {}).items()}
                        if test(a["name"], a["actions"][e["action"]], params):
                            hits.append(f"{fname}:{entry}:{e['name']}")
                        nxt = params.get("EventName")
                        if isinstance(nxt, str) and self.row_entry(nxt):
                            todo.append(self.row_entry(nxt))
                    if e["type"] in ("subflow", "subflow_switch") and e.get("entry_point"):
                        todo.append((e.get("flowchart") or fname, e["entry_point"]))
                    stack += [e[k] for k in ("next", "join") if k in e]
                    stack += [c["next"] for c in e.get("cases", [])] + e.get("forks", [])
        return hits


def verify(patch_dir, plan, out_dir=None, romfs=DEFAULT_ROMFS):
    """Reads every chest location's tracker flag back from a built patch. Returns ([problem], number of flags read
    back).
    - IsTreasureBoxOpen.<h> has to be a saved, never-reset Bool and a member of the struct (in the patched
      GameDataList). Every placement with that hash in its chest's level files has to be a TreasureBox chest type
      without IsEnableRepeatOpen, and its scene (its GetEventName or its type's default, in the patched EventSetting
      and flows) has to reach EventTriggerTreasureBoxOpened on TreasureBox_EventStarter.
    - b64 <h> (an Ice Trap left in the trap chest) needs an Obj_TBox_A_04 placement and its saved, never-reset
      per-object row.
    - The Treasure Chest Game's flags have to be saved, and set by the reward chest's scene or the salesman's sale.
    - out_dir/tracker.json (when it's there): every chest location carries exactly these flags."""
    from romtools import Romfs, byml_load, murmur3_32
    from parity import _chests_tcg as tcg
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    sp = json.load(open(os.path.join(out_dir, "spoiler.json"), encoding="utf-8")) if out_dir else {}
    locs = sp.get("locations", {})
    names = set(locs.get("World 1", locs))
    want = tracker_flags(names, plan, sp.get("settings") or {})
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    bools = {int(e["Hash"]): e for e in gd["Bool"]}
    per_object = {int(e["Hash"]): e for e in gd["Bool64bitKey"]}
    st = next((e for e in gd["Struct"] if int(e["Hash"]) == murmur3_32(STRUCT)), None)
    members = {int(m["Hash"]): int(m["Value"]) for m in (st or {}).get("DefaultValue") or []}
    scenes = _Scenes(fs, patch_dir, romfs)
    cat, renames = _catalog(), _renames(plan)
    levels = {}

    def placements(rids):
        """final hash -> [(file, actor dict)] in the patched level files of these chests."""
        out, seen = {}, set()
        for rid in rids:
            r = cat.get(rid)
            if r is None:
                continue
            for f in r["files"]:
                if f not in levels:
                    levels[f] = byml_load(fs.read(f))[0].get("Actors") or []
                old = int(r["hash"])
                new = renames.get((f, old), old)
                for i, a in enumerate(levels[f]):
                    if int(a.get("Hash", 0)) == new and (f, i) not in seen:
                        seen.add((f, i))
                        out.setdefault(new, []).append((f, a))
        return out

    def saved_bool(name):
        e = bools.get(murmur3_32(name))
        if e is None:
            return f"no saved Bool {name} in the patched GameDataList"
        if int(e.get("SaveFileIndex", -1)) != 0:
            return f"{name} is not saved (SaveFileIndex {e.get('SaveFileIndex')})"
        return None

    def opened(actor, action, params):
        return actor == OPENED_ACTOR and action == OPENED_ACTION

    def sets(flag):
        return lambda actor, action, params: (action == SET_BOOL and params.get("GameDataName") == flag
                                              and params.get("Value") is True)
    problems, n = [], 0
    chest_locs = location_chests(names)
    for loc in sorted(want):
        rids = chest_locs.get(loc, [])
        at = placements(rids)
        for f in want[loc]:
            n += 1
            if f["t"] == "bool" and f["n"].startswith(STRUCT + "."):
                h = int(f["n"].split(".", 1)[1])
                bad = saved_bool(f["n"])
                if bad:
                    problems.append(f"{loc}: {bad}")
                elif int(bools[murmur3_32(f['n'])].get("ResetTypeValue", -1)) != SAVED_RESET:
                    problems.append(f"{loc}: {f['n']} resets (ResetTypeValue "
                                    f"{bools[murmur3_32(f['n'])].get('ResetTypeValue')}): the chest would close again")
                if members.get(murmur3_32(str(h))) != murmur3_32(f["n"]):
                    problems.append(f"{loc}: {STRUCT} has no member {h}: the chest's AI can't save or read it")
                if not at.get(h):
                    problems.append(f"{loc}: no placement with hash {h} in its level files")
                for file, a in at.get(h, []):
                    gy, dyn = a.get("Gyaml"), a.get("Dynamic") or {}
                    if gy not in CHEST_TYPES:
                        problems.append(f"{loc}: {file} {h} is a {gy}, not a chest that saves {STRUCT}")
                        continue
                    if dyn.get("IsEnableRepeatOpen"):
                        problems.append(f"{loc}: {file} {h} has IsEnableRepeatOpen: opening it saves nothing")
                    scene = dyn.get("GetEventName") or CHEST_TYPES[gy]
                    if scenes.row_entry(scene) is None:
                        problems.append(f"{loc}: {file} {h}: its scene {scene} has no EventSetting flow row")
                    elif not scenes.reaches(scene, opened):
                        problems.append(f"{loc}: {file} {h}: its scene {scene} never marks the chest opened "
                                        f"({OPENED_ACTOR}.{OPENED_ACTION})")
            elif f["t"] == "b64":
                h = int(f["h"])
                e = per_object.get(h)
                if e is None or int(e.get("SaveFileIndex", -1)) != 0 or int(e.get("ResetTypeValue", -1)) != SAVED_RESET:
                    problems.append(f"{loc}: trap chest {h} has no saved, never-reset per-object flag ({e})")
                if not any(a.get("Gyaml") == TRAP for _, a in at.get(h, [])):
                    problems.append(f"{loc}: {h} is no {TRAP} (the break that writes its per-object flag)")
            elif f["n"] == TCG_CLEAR:
                bad = saved_bool(TCG_CLEAR)
                if bad:
                    problems.append(f"{loc}: {bad}")
                if not at:
                    problems.append(f"{loc}: no reward chest placement in its level file")
                for h, pl in at.items():
                    for file, a in pl:
                        scene = (a.get("Dynamic") or {}).get("GetEventName") or CHEST_TYPES.get(a.get("Gyaml"), "")
                        if not scenes.reaches(scene, sets(TCG_CLEAR)):
                            problems.append(f"{loc}: {file} {h}: its scene {scene} never sets {TCG_CLEAR}")
            elif f["n"].startswith(tcg.TAKEN.format("")):
                bad = saved_bool(f["n"])
                if bad:
                    problems.append(f"{loc}: {bad}")
            elif f["n"] == tcg.SOLD_FLAG:
                bad = saved_bool(tcg.SOLD_FLAG)
                if bad:
                    problems.append(f"{loc}: {bad}")
                ev = scenes.flow(TCG_FLOW)
                fc = ev.flowcharts[0] if ev else None
                hit = fc and any(
                    e["type"] == "action" and fc["actors"][e["actor"]]["actions"][e["action"]] == SET_BOOL
                    and {k: v.get("value") for k, v in ((e.get("params") or {}).get("items") or {}).items()}
                    .get("GameDataName") == tcg.SOLD_FLAG for e in fc["events"])
                if not hit:
                    problems.append(f"{loc}: {TCG_FLOW} never sets {tcg.SOLD_FLAG} (the sale)")
            else:
                problems.append(f"{loc}: unknown chest flag {f}")
    problems += verify_trap_module(fs, converted_traps((plan or {}).get("rewards")))
    problems += tcg.verify_rooms(fs, plan or {})
    tracker = os.path.join(out_dir, "tracker.json") if out_dir else None
    if tracker and os.path.exists(tracker):
        got = {c["name"]: c.get("flags") or [] for c in json.load(open(tracker, encoding="utf-8")).get("checks", [])}
        for loc in sorted(want):
            if loc in got and sorted(map(json.dumps, got[loc])) != sorted(map(json.dumps, want[loc])):
                problems.append(f"tracker.json: {loc} reads {got[loc]}, the chest saves {want[loc]} "
                                f"(rebuild it: python tools/tracker/build_data.py seed {out_dir})")
    return problems, n
