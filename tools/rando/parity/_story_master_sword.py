"""remake_shuffle_master_sword. Without the Master Sword the adult goes back to child at the pedestal, and time travel
never stores or hands Link a Master Sword he doesn't own (story plugin, an OotrR finding).
This only happens with the setting on, the
default output is unchanged. With the sword owned, every step below takes the vanilla path.

What the game does (read from the files):
- The pedestal (Pack/Actor/Obj_TimeTemple_MasterSword_A_01.pack.zs) offers its prompt through three AttentionSender
  clients: PullOut (child, Dm_TimeTemple_0030 played), PullOut_First (child, not played) and PutIn (adult). Their
  CheckLists only hold an age check, the 0030 check, two area fans and a line check, so nothing reads the sword. But
  the PutIn verb doesn't show without the sword (OotrR, in game), so the engine gates the verb itself. The
  pedestal's AI (AI/AttentionActor.root.ainb) answers any of its three DoActionTypes (PullOut, PutIn, PullOut_First)
  with ReceiveDoAction, and then the adult level logic (Market_Adult_Prefab_89da) requests
  Market_Adult_Field_AdultToChild, whatever the verb was.
- The put-in scene (Dm_TimeTemple_0070 "other") copies PlayerStatus.EquipWeapon to
  PlayerWeaponBeforeForceEquipMasterSword (Event3), then force-equips a Master Sword if Link holds none (Event4,
  CreateStaticEquipment). ReplaceEquipmentForEraChange runs right after and stores that copy as the adult's weapon
  (Event7: AnotherEraEquipWeapon <- PlayerWeaponBeforeForceEquipMasterSword), and every later child -> adult trip
  swaps it back into Link's hand (Event0/Event1, a same-frame swap). The first adult arrival with the Silver
  Gauntlets (Dm_TimeTemple_0088 "other", Event28) force-equips the Master Sword too, and nothing gives the old
  weapon back. Every other arrival (Dm_TimeTemple_0085 "other", Event9) makes a pose-only Master Sword
  (CreateDynamicEquipmentNoRelationPouch) when Link holds no two-handed sword, then re-equips from the pouch. Other
  scenes force-equip it as well: the first adult arrival in Kakariko (Dm_SY_BancChangeArrive KakarikoVillage_Arrive
  Event37), the Light Arrow scene (AllSage Event175, both its entries) and Ganondorf (Defeat_Ganon Event33/Event217).

What this module changes (with the setting on):
1. The pedestal pack gets a fourth client, a copy of PullOut (same verb, the adult client's area and line checks).
   Its age check is reversed (adult) and its 0030 check reads IsGet.Weapon_Sword_Master, reversed. So an adult who
   never got the Master Sword sees the PullOut prompt, which starts the same return scene. OotrR's
   pedestal_put_in_without_sword uses the PullOut verb for the adult too (seen in game). The engine sets
   IsGet.<actor> on every pouch add (the IsGet struct has a Weapon_Sword_Master member). An adult
   who got it keeps the vanilla PutIn client, and the new one is off for him.
2. Dm_TimeTemple_0070: without IsGet.Weapon_Sword_Master the put-in scene skips the force-equip (Event3 -> Event15).
3. Dm_TimeTemple_0088: the same for the Silver Gauntlets arrival (Event35 -> Event27).
4. Dm_TimeTemple_0085: the pose-only Master Sword only when Link holds the Master Sword (Event37 -> Event9 only
   then). If he owns it he's always holding it there, since the first-trip guard below equips it on an empty adult
   slot.
5. ReplaceEquipmentForEraChange, going to child: if the weapon to store is the Master Sword and it isn't in the
   pouch, the adult slot gets emptied instead of storing it. That's a set, not the copy, because the game's copies
   in this flow read the values from before the frame's writes. Together with story.py's first-trip guard (Event5,
   the Master Sword only if it's in the pouch) the adult slot never holds an unowned Master Sword, whatever scene
   handed one over.
6. The same force-equip outside time travel, which I found along the way: the Kakariko arrival (Event258 ->
   Event484 without IsGet.Weapon_Sword_Master) and the Light Arrow scene, skipped to Event12 without it. That one
   is a story-plugin pre-hook on AllSage Event175, so it composes with lacs_condition's hooks there. Ganondorf's two
   are left alone. The final battle hands the Master Sword over anyway (Dm_FinalBattle_0010 Event173) and
   Defeat_Ganon reads the held sword right after (Event66).
Read-back: verify() (parity/_gaps_check.py, run by tools/rando/in_game_check.py) reads the patched pack and the six
flows and checks every step above against the vanilla files.
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

PACK = "Pack/Actor/Obj_TimeTemple_MasterSword_A_01.pack.zs"
SENDER = "Component/AttentionSenderParam/Obj_TimeTemple_MasterSword_A_01.game__component__AttentionSenderParam.bgyml"
GAMEPARAM = ("GameParameter/AttentionActor/Obj_TimeTemple_MasterSwordAttention_A_01."
             "game__attention__AttentionActor.bgyml")
PULL_OUT = "TimeTemple_MasterSwordAttention_PullOut"
PULL_OUT_FIRST = "TimeTemple_MasterSwordAttention_PullOut_First"
PUT_IN = "TimeTemple_MasterSwordAttention_PutIn"
RETURN = "TimeTemple_MasterSwordAttention_RandoReturn"  # the new adult client (PullOut verb, sword never got)
VANILLA_CLIENTS = (PULL_OUT, PULL_OUT_FIRST, PUT_IN)
VERBS = {"PullOut": 1302650721, "PutIn": 2411603822}  # ActionType = murmur3 of the verb
CHECK_GAMEDATA = 4204288117  # CheckType murmur3("GameData")
MASTER = "Weapon_Sword_Master"
OWNED = f"IsGet.{MASTER}"
BEFORE = "PlayerWeaponBeforeForceEquipMasterSword"
ADULT_SLOT = "PlayerStatus.AnotherEraEquipWeapon"
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"


def client_file(name):
    return f"Attention/ClientParam/{name}.game__attention__ClientParam.bgyml"


def client_ref(name):
    return f"Work/Attention/ClientParam/{name}.game__attention__ClientParam.gyml"


def _owned_query(yes, no):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
            "params": {"GameDataName": OWNED, "Index": -1}, "cases": {0: yes, 1: no}}  # case 0 = true


# file -> (the step leading to the guarded step, its routing, the new graph, its nodes, its first node, the steps that
# must not run without the sword). The routing is "next" or the case's position, and the steps are
# [(actor, action, params that identify it)].
FLOWS = {
    "Dm_TimeTemple_0070": ("Event3", None, "Rando_MasterSword_PutIn", {"own": _owned_query("@Event13", "@Event15")},
                           "own", [("Player_Event", "EventTriggerEquipmentUserRequestCreateStaticEquipment",
                                    {"EquipmentActorName": MASTER})]),
    "Dm_TimeTemple_0088": ("Event35", None, "Rando_MasterSword_Gauntlets",
                           {"own": _owned_query("@Event29", "@Event27")}, "own",
                           [("Player_Event", "EventTriggerEquipmentUserRequestCreateStaticEquipment",
                             {"EquipmentActorName": MASTER})]),
    # If Link isn't holding the sword the branch just ends. Vanilla Event37 ends the same way when the case is
    # missing, there's no vanilla case with an explicit end target.
    "Dm_TimeTemple_0085": ("Event37", 0, "Rando_MasterSword_Arrive", {
        "held": {"actor": "Player_Event", "query": "EventQueryPlayerIsEquipWeapon",
                 "params": {"ArmorName": MASTER, "WeaponSlot": 0}, "cases": {0: "@Event9"}}}, "held",
        [("Player_Event", "EventTriggerPlayerRequestCreateDynamicEquipmentNoRelationPouch",
          {"EquipmentActorName": MASTER})]),
    "ReplaceEquipmentForEraChange": ("Event6", 1, "Rando_MasterSword_AdultSlot", {
        "held": {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                 "params": {"GameDataName": BEFORE, "Value": MASTER, "Index": -1}, "cases": {0: "own", 1: "@Event7"}},
        "own": {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch", "params": {"Actor": MASTER, "Num": 1},
                "cases": {0: "@Event7", 1: "clear"}},
        "clear": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                  "params": {"GameDataName": ADULT_SLOT, "Value": "", "Index": -1}, "next": "@Event2"}}, "held",
        # the copy of the stored weapon, and the first trip's Master Sword (story.py's guard on Event5)
        [("GameDataActor", "EventTriggerCopyGameDataString64", {"SrcGameDataName": BEFORE}),
         ("GameDataActor", "EventTriggerSetGameDataString64", {"GameDataName": ADULT_SLOT, "Value": MASTER})]),
    # outside time travel: the first adult arrival in Kakariko (entry KakarikoVillage_Arrive)
    "Dm_SY_BancChangeArrive": ("Event258", None, "Rando_MasterSword_Kakariko",
                               {"own": _owned_query("@Event37", "@Event484")}, "own",
                               [("Player_Event", "EventTriggerEquipmentUserRequestCreateStaticEquipment",
                                 {"EquipmentActorName": MASTER})]),
}
# flows many features edit: only the steps named in VANILLA, the guard and the guarded steps are compared
SHARED = ("Dm_SY_BancChangeArrive",)
# a step guarded through the story plugin's Plan (other hooks may sit on the same step): file -> (step, its next)
PLAN_HOOKS = {"AllSage": ("Event175", "Event12")}
PLAN_FORBID = [("Player_Event", "EventTriggerEquipmentUserRequestCreateStaticEquipment",
                {"EquipmentActorName": MASTER})]
# vanilla facts the routing above relies on, checked by verify() against the game files: step -> (kind, next/cases)
VANILLA = {
    "Dm_TimeTemple_0070": {"Event3": ("EventTriggerCopyGameDataString64", "Event13"),
                           "Event13": ("EventQueryPlayerIsEquipWeapon", {0: "Event25", 1: "Event27"}),
                           "Event15": ("EventTriggerEquipmentUserRequestChangeState", None)},
    "Dm_TimeTemple_0088": {"Event35": ("EventTriggerCopyGameDataString64", "Event29"),
                           "Event29": ("EventQueryPlayerIsEquipWeapon", {0: "Event30", 1: "Event32"}),
                           "Event27": ("EventTriggerEquipmentUserRequestChangeState", None)},
    "Dm_TimeTemple_0085": {"Event37": ("EventQueryPlayerIsEquipWeapon", {1: "Event9"}),
                           "Event9": ("EventTriggerPlayerRequestCreateDynamicEquipmentNoRelationPouch", "Event14")},
    "ReplaceEquipmentForEraChange": {"Event6": ("EventQueryIsGameDataBool", {0: "Event1", 1: "Event7"}),
                                     "Event7": ("EventTriggerCopyGameDataString64", "Event2"),
                                     "Event5": ("EventTriggerSetGameDataString64", "Event13")},
    "Dm_SY_BancChangeArrive": {"Event258": (None, "Event37"),  # a call, SubEvent_GetSwordBigGoron's timer
                               "Event37": ("EventTriggerEquipmentUserRequestCreateStaticEquipment", "Event484")},
    "AllSage": {"Event165": ("EventPlayerUnequip", "Event175"),
                "Event175": ("EventTriggerEquipmentUserRequestCreateStaticEquipment", "Event12")},
}


def _on(settings):
    from parity import story  # lazy, story imports this module
    return story.shuffle_master_sword(settings)


def UNTESTED(settings):
    if not _on(settings):
        return []
    return ["remake_shuffle_master_sword: an adult without the Master Sword goes back to child at the pedestal "
            "(PullOut prompt), the put-in / Silver Gauntlets / arrival scenes never equip an unowned Master Sword, "
            "and the adult slot never stores one; nor do the first Kakariko arrival and the Light Arrow scene"]


def hooks(p, settings, world):
    """story.world_plan's hook. Skips the Light Arrow scene's force-equip without the sword (story.Plan)."""
    if _on(settings):
        for f, (step, _) in PLAN_HOOKS.items():
            p.skip_unless(f, step, OWNED, query="EventQueryIsGameDataBool")


def world_plan(settings, world):
    if not _on(settings):
        return {}
    packs = [
        {"pack": PACK, "file": client_file(RETURN), "new_from": client_file(PULL_OUT),
         "set": {"CheckList.0.CheckGameData.IsReverseCondition": True,      # Sequence_IsChildhood false: adult
                 "CheckList.1.CheckGameData.GameDataPath": OWNED,           # was HavePlayedEvent.Dm_TimeTemple_0030
                 "CheckList.1.CheckGameData.IsReverseCondition": True}},    # the Master Sword never got
        {"pack": PACK, "file": SENDER, "set": {"ClientList": [client_ref(c) for c in VANILLA_CLIENTS + (RETURN,)]}},
    ]
    events = []
    for f, (pred, case, graph, nodes, start, _) in FLOWS.items():
        events.append({"file": f, "flowchart": f, "add_graph": graph, "nodes": copy.deepcopy(nodes), "start": start})
        op = {"file": f, "flowchart": f, "event": pred, "next": f"{graph}_{start}"}
        if case is not None:
            op["case"] = case
        events.append(op)
    note = {"pack": PACK, "client": RETURN, "flows": sorted(FLOWS), "plan_hooks": sorted(PLAN_HOOKS)}
    return {"packs": packs, "events": events, "_gaps": {"master_sword_return": note}}


READERS = {"master_sword_return": "verify"}


# Read-back (parity/_gaps_check.py)
def _flat(c, out=None, prefix=""):
    out = {} if out is None else out
    if not c:
        return out
    if c["type"] == "container":
        for k, v in c["items"].items():
            _flat(v, out, k)
    else:
        out[prefix] = c["value"]
    return out


def _name(fc, i):
    return fc["events"][i]["name"] if i is not None and i < len(fc["events"]) else None


def _what(fc, e):
    if e["type"] not in ("action", "switch"):
        return e["type"], None
    a = fc["actors"][e["actor"]]
    return a["name"], (a["actions"][e["action"]] if e["type"] == "action" else a["queries"][e["query"]])


def _route(fc, e):
    """A step's routing by names: its next step, or {case value: step}, or (forks, join)."""
    if e["type"] in ("switch", "subflow_switch"):
        return {c["value"]: _name(fc, c["next"]) for c in e["cases"]}
    if e["type"] == "fork":
        return ([_name(fc, i) for i in e["forks"]], _name(fc, e["join"]))
    return _name(fc, e.get("next"))


def _sig(fc, e):
    return (e["type"], _what(fc, e), _flat(e.get("params")), e.get("flowchart"), e.get("entry_point"))


def _reach(fc, assume):
    """Step names reachable from every entry point. A switch `assume` names (a function of the step returning the
    case value taken, or None for all) follows only that case."""
    todo = [ep["main"] for ep in fc["entry_points"].values()]
    seen = set()
    while todo:
        i = todo.pop()
        if i is None or i >= len(fc["events"]) or i in seen:
            continue
        seen.add(i)
        e = fc["events"][i]
        if e.get("cases"):
            v = assume(fc, e)
            todo += [c["next"] for c in e["cases"] if v is None or c["value"] == v]
        if e.get("next") is not None:
            todo.append(e["next"])
        todo += list(e.get("forks", []))
        if e["type"] == "fork":
            todo.append(e["join"])
    return {fc["events"][i]["name"] for i in seen}


def _ownership(fc, e):
    """True for a switch on owning the Master Sword (ever got it, or in the pouch); case 0 = true."""
    q, p = _what(fc, e)[1], _flat(e.get("params"))
    return (q == "EventQueryIsGameDataBool" and p.get("GameDataName") == OWNED) or \
        (q == "EventQueryIsExistInPouch" and p.get("Actor") == MASTER)


def _unowned(fc, e):
    """The case a switch takes when Link never got the Master Sword, holds none and the weapon to store is one. That's
    the worst case, since the force-equips only run when he holds none and the copy only stores what it's given."""
    q, p = _what(fc, e)[1], _flat(e.get("params"))
    if _ownership(fc, e) or (q == "EventQueryPlayerIsEquipWeapon" and p.get("ArmorName") == MASTER):
        return 1
    if q == "EventQueryIsGameDataString64" and p.get("GameDataName") == BEFORE and p.get("Value") == MASTER:
        return 0
    return None


def _owned(fc, e):
    """Link got the Master Sword and has it; every other switch may go any way."""
    return 0 if _ownership(fc, e) else None


def _forbidden(fc, specs):
    out = set()
    for actor, action, params in specs:
        for e in fc["events"]:
            if e["type"] == "action" and _what(fc, e) == (actor, action) and \
                    all(_flat(e.get("params")).get(k) == v for k, v in params.items()):
                out.add(e["name"])
    return out


def _through_new(fc, start, target, vanilla):
    """Step `start` (a step a plugin added, or the target itself) leads to `target` through added steps only."""
    by = {e["name"]: e for e in fc["events"]}
    todo, seen = [start], set()
    while todo:
        n = todo.pop()
        if n == target:
            return True
        if n is None or n in seen or n in vanilla or n not in by:
            continue
        seen.add(n)
        r = _route(fc, by[n])
        todo += list(r.values()) if isinstance(r, dict) else (r[0] + [r[1]] if isinstance(r, tuple) else [r])
    return False


def _same_route(van, pat, ve, pe, vanilla):
    """A vanilla step routes as in vanilla, or into steps other features added that lead to the vanilla target."""
    vr, pr = _route(van, ve), _route(pat, pe)
    if vr == pr:
        return True
    if isinstance(vr, dict) and isinstance(pr, dict) and set(vr) == set(pr):
        return all(pr[k] == vr[k] or _through_new(pat, pr[k], vr[k], vanilla) for k in vr)
    if isinstance(vr, str) or vr is None:
        return isinstance(pr, str) and _through_new(pat, pr, vr, vanilla)
    return False


def _check_flow(base, van, pat):
    pred, case, graph, nodes, start, forbid = FLOWS[base]
    bad = []
    vby = {e["name"]: e for e in van["events"]}
    pby = {e["name"]: e for e in pat["events"]}
    # the vanilla facts the plan's routing was written for
    for step, (what, route) in VANILLA[base].items():
        e = vby.get(step)
        if e is None or (what is not None and _what(van, e)[1] != what):
            bad.append(f"{base}: vanilla {step} is not {what}: the plan's routing is out of date")
        elif route is not None and _route(van, e) != route:
            bad.append(f"{base}: vanilla {step} routes {_route(van, e)}, the plan expects {route}")
    if len(_forbidden(van, forbid) & _reach(van, _unowned)) != len(forbid):
        bad.append(f"{base}: vanilla doesn't run {[f[1] for f in forbid]} for a swordless Link: nothing to guard")
    # Every vanilla step is unchanged except the one now leading to the guard. Other features' hooks may sit in front
    # of a step, so a route into added steps that lead to the vanilla target counts as the same route. In a shared
    # flow we only check the steps named in VANILLA and the guarded ones.
    keep = set(vby) if base not in SHARED else set(VANILLA[base]) | _forbidden(van, forbid)
    for name, e in ((n, x) for n, x in vby.items() if n in keep):
        p = pby.get(name)
        if p is None or _sig(van, e) != _sig(pat, p):
            bad.append(f"{base}: {name} changed")
        elif name != pred and not _same_route(van, pat, e, p, vby):
            bad.append(f"{base}: {name} routes {_route(pat, p)}, vanilla {_route(van, e)}")
    e = pby.get(pred)
    first = f"{graph}_{start}"
    if e is not None:
        vr, pr = _route(van, vby[pred]), _route(pat, e)
        if case is None:
            ok = pr == first
        else:
            want = {c["value"]: c["next"] for c in vby[pred]["cases"]}
            ok = isinstance(pr, dict) and set(pr) == set(vr) and all(
                pr[v] == (first if k == case else vr[v]) for k, v in enumerate(want))
        if not ok:
            bad.append(f"{base}: {pred} routes {pr}, not to the guard {first}")
    # the guard's own steps as planned
    for lab, n in nodes.items():
        g = pby.get(f"{graph}_{lab}")
        if g is None:
            bad.append(f"{base}: no step {graph}_{lab}")
            continue
        kind = n.get("query") or n.get("action")
        if _what(pat, g) != (n["actor"], kind) or _flat(g.get("params")) != n["params"]:
            bad.append(f"{base}: {graph}_{lab} is {_what(pat, g)} {_flat(g.get('params'))}")
        want = ({v: (t[1:] if isinstance(t, str) and t.startswith("@") else
                     (f"{graph}_{t}" if t is not None else None)) for v, t in n["cases"].items()}
                if "cases" in n else (n["next"][1:] if n["next"] else None))
        if _route(pat, g) != want:
            bad.append(f"{base}: {graph}_{lab} routes {_route(pat, g)}, planned {want}")
    # A swordless Link shouldn't reach the force-equip or the adult-slot copy.
    # Owning the sword should keep the vanilla steps reachable.
    left = _forbidden(pat, forbid) & _reach(pat, _unowned)
    if left:
        bad.append(f"{base}: without the Master Sword, {sorted(left)} still run")
    lost = (_reach(van, _owned) if base not in SHARED else _forbidden(van, forbid)) - _reach(pat, _owned)
    if lost:
        bad.append(f"{base}: with the Master Sword owned, vanilla steps {sorted(lost)} can't be reached")
    return bad


def _check_plan_hook(base, van, pat):
    """Checks a story.Plan pre-hook, a switch on IsGet.Weapon_Sword_Master in front of the step with "false" going to
    its next step. Without the sword the force-equip can't run, with it it can."""
    step, nxt = PLAN_HOOKS[base]
    bad = []
    vby = {e["name"]: e for e in van["events"]}
    for s, (what, route) in VANILLA[base].items():
        e = vby.get(s)
        if e is None or _what(van, e)[1] != what or _route(van, e) != route:
            bad.append(f"{base}: vanilla {s} is not {what} -> {route}: the plan's hook is out of date")
    guards = [e for e in pat["events"] if e["name"].startswith(f"Rando_Story_{step}_") and e["type"] == "switch"
              and _what(pat, e)[1] == "EventQueryIsGameDataBool"
              and _flat(e.get("params")).get("GameDataName") == OWNED]
    if len(guards) != 1:
        bad.append(f"{base}: {len(guards)} ownership guards in front of {step}, not one")
    for g in guards:
        r = _route(pat, g)
        if r.get(1) != nxt or not _through_new(pat, r.get(0), step, vby):
            bad.append(f"{base}: {g['name']} routes {r}, not owned -> {step}, else -> {nxt}")
    forbid = _forbidden(van, PLAN_FORBID)
    if step not in forbid or step not in _reach(van, _unowned):
        bad.append(f"{base}: vanilla {step} is not a reachable force-equip of the Master Sword")
    if _forbidden(pat, PLAN_FORBID) & _reach(pat, _unowned):
        bad.append(f"{base}: without the Master Sword, {sorted(_forbidden(pat, PLAN_FORBID) & _reach(pat, _unowned))} "
                   f"still run")
    if step not in _reach(pat, _owned):
        bad.append(f"{base}: with the Master Sword owned, {step} can't be reached")
    return bad


def _flowcharts(fs, romfs, base):
    import re
    from evfl import Evfl
    rx = re.compile(re.escape(base) + r"(\.\d{3})?\.bfevfl\.zs$")
    names = sorted(f for f in os.listdir(os.path.join(romfs, "Event", "EventFlow")) if rx.match(f))
    return [(n, Evfl(fs.read(f"Event/EventFlow/{n}")).flowcharts[0]) for n in names]


def verify(patch, note, romfs):
    from romtools import Romfs, sarc_files, byml_load, murmur3_32
    van_fs = Romfs(romfs, os.path.join(HERE, "original"))
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []

    def load(b):
        return byml_load(b, allow_big=True)[0]
    # 1. the pedestal pack: the vanilla clients as the plan expects them, the new adult client, the vanilla ones intact
    vf, pf = sarc_files(van_fs.read(PACK)), sarc_files(fs.read(PACK))
    if load(vf[SENDER]).get("ClientList") != [client_ref(c) for c in VANILLA_CLIENTS]:
        bad.append(f"{PACK}: vanilla ClientList is {load(vf[SENDER]).get('ClientList')}, not the three the plan "
                   f"expects")
    got = load(pf[SENDER]).get("ClientList")
    if got != [client_ref(c) for c in VANILLA_CLIENTS + (RETURN,)]:
        bad.append(f"{PACK}: ClientList is {got}, without the adult return client {RETURN}")
    for c in VANILLA_CLIENTS:
        if pf.get(client_file(c)) != vf[client_file(c)]:
            bad.append(f"{PACK}: client {c} changed")
    pull, put = load(vf[client_file(PULL_OUT)]), load(vf[client_file(PUT_IN)])
    if pull.get("ActionType") != VERBS["PullOut"] or put.get("ActionType") != VERBS["PutIn"]:
        bad.append(f"{PACK}: vanilla verbs {pull.get('ActionType')} / {put.get('ActionType')} not PullOut / PutIn")
    pcl = pull.get("CheckList") or []
    gd0 = [(c.get("CheckType"), (c.get("CheckGameData") or {}).get("GameDataPath"),
            (c.get("CheckGameData") or {}).get("IsReverseCondition")) for c in pcl[:2]]
    if gd0 != [(CHECK_GAMEDATA, "Sequence_IsChildhood", False),
               (CHECK_GAMEDATA, "HavePlayedEvent.Dm_TimeTemple_0030", False)] or \
            pcl[2:] != (put.get("CheckList") or [])[1:]:
        bad.append(f"{PACK}: vanilla PullOut client is not PutIn's checks plus the child and 0030 checks: {gd0}")
    if client_file(RETURN) not in pf:
        bad.append(f"{PACK}: no {client_file(RETURN)}")
    else:
        new, want = load(pf[client_file(RETURN)]), copy.deepcopy(pull)
        want["CheckList"][0]["CheckGameData"]["IsReverseCondition"] = True
        want["CheckList"][1]["CheckGameData"].update(GameDataPath=OWNED, IsReverseCondition=True)
        if new != want:
            bad.append(f"{PACK}: {RETURN} is not the PullOut client for an adult who never got the Master Sword")
    acts = load(pf[GAMEPARAM])
    if VERBS["PullOut"] not in (acts.get("DoActionType1"), acts.get("DoActionType2"), acts.get("DoActionType3")):
        bad.append(f"{PACK}: the pedestal's AI doesn't take the PullOut verb ({acts})")
    # 2. IsGet.Weapon_Sword_Master is a member of the IsGet struct (the engine sets members on every pouch add)
    gd = load(fs.read(GAMEDATA))["Data"]
    rows = {int(r["Hash"]): r for t in gd.values() for r in t}
    st = rows.get(murmur3_32("IsGet"))
    mem = {int(m["Hash"]): int(m["Value"]) for m in (st or {}).get("DefaultValue", [])}
    if mem.get(murmur3_32(MASTER)) != murmur3_32(OWNED) or murmur3_32(OWNED) not in rows:
        bad.append(f"{GAMEDATA}: {OWNED} is not a member of the IsGet struct")
    # 3. the six flows (every version make_patch edits)
    for base in sorted(FLOWS) + sorted(PLAN_HOOKS):
        vans = dict(_flowcharts(van_fs, romfs, base))
        for vname, fc in _flowcharts(fs, romfs, base):
            bad += (_check_flow if base in FLOWS else _check_plan_hook)(base, vans[vname], fc)
    return bad


if __name__ == "__main__":  # python _story_master_sword.py PATCH_DIR [ROMFS]: the read-back alone (a negative control)
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
    found = verify(sys.argv[1], {}, sys.argv[2] if len(sys.argv) > 2 else __import__("romtools").longshot_romfs())
    print("\n".join(found) or "ok")
    print(f"{len(found)} problem(s)")
    sys.exit(1 if found else 0)
