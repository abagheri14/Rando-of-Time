"""Ammo without its container adds nothing, like in OoTR.

The remake's pouch system gives you the container itself when ammo arrives without one. A "Bombs (5)" chest (its
bundle, Item_BombBundle_Small, adds 5 Item_Bomb) gave a Bomb Bag full of 20 bombs. In OoTR bombs need a Bomb Bag,
arrows a Bow and Deku Seeds a Slingshot, and without it the item adds nothing.

Every give of a non-shop item goes through one of three pouch steps, and each gets a guard in front of it:
  - GetPouchContent Event0 (PouchSystemActor.EventTriggerAddOrRemovePouchContent by the scene's ActorName
    argument), for chests (GetPouchContentByActorNameForTreasureBox) and NPC and scene gifts (GetInEvent and the
    get windows)
  - Dm_SY_Get Event35 (PouchContentGuestPerformer.EventTriggerAddOwnToPouch), for pickups held up
  - Dm_SY_Get_WithoutPlayer Event0 (the same, in the air or water). That file has no GameDataActor, so its step
    calls a Dm_SY_Get entry that guards and adds.
The guard writes the item's name into the UI message target, UI_MessageTargetActorName. That's the game data the
add step sets itself (GameDataActor.EventTriggerSetGameDataString64 from the ActorName argument, or the pickup's
own EventTriggerSetOwnNameToMessage). Then it compares it with each ammo actor
(GameDataActor.EventQueryIsGameDataString64, case 0 = yes, like DisplayShop's tunic checks), and for ammo asks
whether any tier of its container is owned (PouchSystemActor.EventQueryIsExistInPouch, like the progressive
scenes). If it's not owned the add is skipped and the scene goes on, and the item is still shown like in OoTR.
Shop bundles (Shop_*) are left alone, a purchase must never take the rupees and give nothing.

remake_ammo_without_container is a setting because I wanted one ("Make it a setting"): "blue_rupee" (default,
OoTR's rule) or "nothing". OoTR's item_table.c gives Bombs, Arrows and Deku Seeds through bombs_to_rupee /
arrows_to_rupee / seeds_to_rupee, so with no bomb bag, quiver or bullet bag the item becomes a Blue Rupee. Deku
Nuts and Sticks are no_upgrade, and Bombchus are bombchus_to_bag, never a rupee. The container is read when the
item is given:
  - the three guards above. The last "not owned" answer adds a Blue Rupee before the scene goes on (RUPEE_ADD, the
    pouch add the guarded step makes, with TBox_Rupee_Blue, which is what a "Rupees (5)" chest adds).
  - the carrier's quiet give (_songs_trade_lake._quiet_give), the same way
  - our ammo pickups at drop spots, taken with no event. That's their take in AI.Global's DropItem.root (drops.py
    AMMO RUPEE).
"nothing" keeps the guards as they were, so the add is skipped (0/0).
With "blue_rupee" you also see the Blue Rupee and get told about it (my call), keyed on the same container check:
  - the guards' "not owned" end names it first (UI_MessageTargetActorName := TBox_Rupee_Blue, which the get window
    and message read), then adds it
  - the hold-up's show step (every Dm_SY_GetInEvent routine that shows its ActorName argument,
    EventCreateShowItemFromActorFileName) is guarded the same way, so ammo with no container shows TBox_Rupee_Blue
  - a chest's content: drops.py AMMO SWITCH, where queries pick the chest's reads of Drop__DropActor
    (TBox_Rupee_Blue), and chests through switch_ops (their reward's extra keys). A dropper drops the ammo pickup
    (the engine reads its Drop__DropActor, and writing that instance parameter crashes the game) and its take gives
    the Blue Rupee.
  - what a carrier, a heart spot or a silver rupee shows on the ground: drops.item_display(ammo_switch=True), a
    tier look (the Blue Rupee unless an owner is held)

Two more always-on fixes live here (container_ops, every seed). Another remake randomizer, Kaepora
(github.com/Kaepora-HQ/kaepora, MIT), saw both in game:
  - The Bow and the Slingshot bring their small quiver / bullet bag from every source. Their
    RSDB/PouchActorInfo rows list nothing to fill, so a Bow given by anything but a chest held 0 arrows. Only the
    chest's own AI (AI/TreasureBox.module.ainb node 23) adds Item_Quiver_Small and 30 arrows. The pouch add treats
    any row that names a limit and actors to fill as a bag's, so the four weapon rows get the small container's
    four fill fields, with the container added to the fill list. That way IsGet.<container> gets set, and shops
    ask for it before selling ammo. The add does nothing when the limit is already that high, so a chest's Bow, or
    a Bow after a bigger quiver, changes nothing. With Kaepora e33d589 (BringContainers, patcher/mod.cpp) a gift's
    Bow then shot 30 -> 27.
  - Bombs don't need the Goron Bracelet (OotrR found this too). The bomb's
    LiftableParam asks for lift grade Low, so with no strength item neither child nor adult takes a bomb out of
    the bag (Kaepora a872763, seen in game). LiftGrade becomes None (the bombchu's grade) in the 5 packs that hold
    that file. Bomb flowers keep their own LiftableParam (Obj_BombFlower_Fruit) and still need the bracelet, like
    in OoTR. With Kaepora ff561b1 a child at None then took a bomb out and broke a wall.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS
YES, NO = 0, 1
KEY, VALUES, DEFAULT = "remake_ammo_without_container", ("blue_rupee", "nothing"), "blue_rupee"
RUPEE = "TBox_Rupee_Blue"  # item_map.json "Rupees (5)", what a chest's Blue Rupee adds
_mode = {"v": DEFAULT}


def configure(settings):
    """Takes the seed's remake_ammo_without_container, called in generate.build_unfilled before any plugin builds."""
    v = (getattr(settings, "remake", None) or {}).get(KEY, DEFAULT)
    if v not in VALUES:
        raise ValueError(f"{KEY} = {v!r}: one of {', '.join(map(repr, VALUES))}")
    _mode["v"] = v


def mode():
    return _mode["v"]


def group_of(actor):
    """The GROUPS container `actor` needs (or None)."""
    return next((g for g, actors in GROUPS.items() if actor in actors), None)


def owners_of(actor):
    """The actors whose presence in the pouch means `actor`'s container is owned (every tier of the GROUPS container
    holding it), or None for an actor with no container rule."""
    import progressive
    g = next((g for g, actors in GROUPS.items() if actor in actors), None)
    if g is None:
        return None
    return list(dict.fromkeys(o for tier in progressive.PROGRESSIVE[g]["tiers"] for o in progressive.owned_by(tier)))


def rupee_node(nxt):
    """The "not owned" step with remake_ammo_without_container "blue_rupee", which puts a Blue Rupee in the pouch and
    then goes to `nxt`. None with "nothing"."""
    if mode() != "blue_rupee":
        return None
    return {"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
            "params": {"Actor": RUPEE, "Num": 1, "IsEquipDIrect": False, "IsSetMessageTargetActorName": False,
                       "IsGetEvent": False}, "next": nxt}
NAME_SLOT = "UI_MessageTargetActorName"
# container (a config/progressive.json item, for its tiers) -> the ammo actors it's needed for. That's every actor
# whose pouch content bundles Item_Bomb, Item_Arrow_Normal or Item_DekuSeed, plus those three, except the shops'
# Shop_* bundles.
GROUPS = {
    "Bomb Bag": ["Item_BombBundle_Small", "Item_Bomb"],
    "Bow": ["TBox_ArrowBundle_Small", "TBox_ArrowBundle_Medium", "TBox_ArrowBundle_Large", "Obj_ArrowBundle_Small",
            "Obj_ArrowBundle_Medium", "Obj_ArrowBundle_Large", "Item_Arrow_Normal"],
    "Slingshot": ["TBox_DekuSeedBundle", "Obj_DekuSeed", "Item_DekuSeed"],
}
BUNDLED = {"Bomb Bag": "Item_Bomb", "Bow": "Item_Arrow_Normal", "Slingshot": "Item_DekuSeed"}
# (file, step to guard, how the name is written)
TARGETS = (("GetPouchContent", "Event0", "arg"), ("Dm_SY_Get", "Event35", "own"))
WP_FILE, WP_STEP = "Dm_SY_Get_WithoutPlayer", "Event0"
WP_HOST = "Rando_AmmoAddOwn"  # the Dm_SY_Get entry with the guarded pickup add for Dm_SY_Get_WithoutPlayer
# Early container check: GetPouchContent's own entry (every chest, NPC and scene give comes through it) and its arguments
WINDOW_FILE, WINDOW_GRAPH = "GetPouchContent", "Rando_AmmoGuard_Window"
WINDOW_ARGS = ("ActorName", "IsShowNumDisplay", "IsTreasureBox", "IsGetInEvent")

POUCH_INFO = "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"
# weapon row -> the container whose fill fields it borrows (the item's name and the actor name the pouch counts it by)
WEAPON_CONTAINERS = {"Item_Range_Bow": "Item_Quiver_Small", "Weapon_Range_Bow": "Item_Quiver_Small",
                     "Item_Range_SlingShot": "Item_BulletBag_Small", "Weapon_Range_SlingShot": "Item_BulletBag_Small"}
FILL_KEYS = ("MaxNumGameData", "AfterExpansionMaxNum", "IsItemStockMaxIfGet", "ExpansionMaxNumActor")
BOMB_LIFT_FILE = "Component/LiftableParam/Item_Bomb.game__component__LiftableParam.bgyml"
BOMB_LIFT_PACKS = ("Item_Bomb", "Npc_Hylia_ImperialSoldier_Bomb", "Obj_BombFlower_A_01", "Obj_BombFlower_A_04",
                   "Obj_BombFlower_Fruit_For_Break_Obj_DeathMtTrail_BrokenRock_A_01")
LIFT_LOW, LIFT_NONE = 3655598229, 3069107721  # murmur3 of "Low" (the bracelet's grade) and "None" (the bombchu's)


def _work(actor):
    return f"Work/Actor/{actor}.engine__actor__ActorParam.gyml"


def _weapon_fill(rows):
    """{weapon row: {field: value}} the four weapon rows get, from the vanilla PouchActorInfo rows."""
    out = {}
    for weapon, container in WEAPON_CONTAINERS.items():
        w, c = rows.get(weapon), rows.get(container)
        if w is None or c is None:
            raise ValueError(f"{POUCH_INFO}: no row {weapon if w is None else container}")
        if any(k in w for k in FILL_KEYS):
            raise ValueError(f"{POUCH_INFO}: {weapon} already has fill fields (game update?)")
        if any(k not in c for k in FILL_KEYS):
            raise ValueError(f"{POUCH_INFO}: {container} lacks a fill field")
        fill = {k: c[k] for k in FILL_KEYS}
        fill["ExpansionMaxNumActor"] = f"{c['ExpansionMaxNumActor']},{_work(container)}"
        out[weapon] = fill
    return out


def container_ops(romfs=DEFAULT_ROMFS):
    """Plan ops for every seed: the Bow and the Slingshot bring their container, and bombs need no strength item (see
    the module doc). The values are read from the vanilla files and checked, so a game update that changes them stops
    the build."""
    from romtools import Romfs, byml_load, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rows = {r.get("__RowId"): r for r in byml_load(fs.read(POUCH_INFO))[0]}
    sets = {f"[__RowId={w}].{k}": v for w, fill in _weapon_fill(rows).items() for k, v in fill.items()}
    packs = []
    for p in BOMB_LIFT_PACKS:
        rel = f"Pack/Actor/{p}.pack.zs"
        files = dict(sarc_files(fs.read(rel)))
        if BOMB_LIFT_FILE not in files:
            raise ValueError(f"{rel}: no {BOMB_LIFT_FILE}")
        if int(byml_load(files[BOMB_LIFT_FILE])[0].get("LiftGrade")) != LIFT_LOW:
            raise ValueError(f"{rel}: the bomb's LiftGrade is no longer Low")
        packs.append({"pack": rel, "file": BOMB_LIFT_FILE, "set": {"LiftGrade": LIFT_NONE}})
    return {"byml": [{"file": POUCH_INFO, "set": sets}], "packs": packs, "_verify_plugins": ["_ammo"],
            "_notes_ammo": ["the Bow and the Slingshot bring their small quiver / bullet bag from any source "
                            "(PouchActorInfo fill fields, Kaepora); bombs lift at grade None, no bracelet needed "
                            "(5 packs, Kaepora; OotrR U1)"]}


def verify(patch, plan, romfs):
    """Read container_ops' edits back from the built patch (in_game_check, plan "_verify_plugins")."""
    from romtools import Romfs, byml_load, sarc_files
    bad = []
    van = Romfs(romfs, os.path.join(HERE, "original"))
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    want = _weapon_fill({r.get("__RowId"): r for r in byml_load(van.read(POUCH_INFO))[0]})
    rows = {r.get("__RowId"): r for r in byml_load(fs.read(POUCH_INFO))[0]}
    for weapon, fill in want.items():
        got = rows.get(weapon) or {}
        for k, v in fill.items():
            if got.get(k) != v or type(got.get(k)) is not type(v):
                bad.append(f"ammo: {weapon}.{k} is {got.get(k)!r}, not {v!r}")
    for p in BOMB_LIFT_PACKS:
        rel = f"Pack/Actor/{p}.pack.zs"
        files = dict(sarc_files(fs.read(rel)))
        grade = byml_load(files[BOMB_LIFT_FILE])[0].get("LiftGrade") if BOMB_LIFT_FILE in files else None
        if grade is None or int(grade) != LIFT_NONE:
            bad.append(f"ammo: {rel} bomb LiftGrade is {grade}, not None ({LIFT_NONE})")
    bad += verify_no_container(fs, plan.get("_ammo_no_container") or DEFAULT)
    return bad


SHOW_FILE, SHOW_ACTION, SHOW_GRAPH = "Dm_SY_GetInEvent", "EventCreateShowItemFromActorFileName", "Rando_AmmoShow"


def show_steps(fc):
    """The hold-up routines' show steps that show their ActorName argument (17 in Dm_SY_GetInEvent)."""
    out = []
    for e in fc["events"]:
        if e["type"] == "action" and fc["actors"][e["actor"]]["actions"][e["action"]] == SHOW_ACTION:
            a = ((e.get("params") or {}).get("items") or {}).get("Actor")
            if isinstance(a, dict) and a.get("type") == "argument" and a.get("value") == "ActorName":
                out.append(e)
    return out


def _chest_table(chest, romfs):
    """The drop table chest type `chest` reads its instance parameters from (drops.drop_bb_table, its vanilla pack)."""
    import drops as drop_tools
    from romtools import Romfs, sarc_files
    files = sarc_files(Romfs(romfs, os.path.join(HERE, "original")).read(f"Pack/Actor/{chest}.pack.zs"))
    return drop_tools.drop_bb_table(files, chest)


def switch_ops(plan, catalog, romfs=DEFAULT_ROMFS):
    """With "blue_rupee", every mapped chest whose reward is container ammo names it, TBox_Rupee_Blue and its container
    (drops.AMMO_SWITCH_KEYS, the reward's extra keys), and the AMMO SWITCH gets built in the chests' root AIs (plan
    "_ammo_switch"). {} with "nothing"."""
    if mode() != "blue_rupee":
        return {}
    import drops as drop_tools
    ai = {(p if p == "*" else tuple(p), f) for p, f in (plan.get("_ammo_switch") or {}).get("ai") or []}
    tables = set()  # each switched chest type's own drop table (drops.drop_bb_table): the keys must be declared there
    chests = []
    for rid, spec in sorted((plan.get("rewards") or {}).items()):
        r = catalog.get(rid) or {}
        item = spec.get("item")
        if r.get("kind") != "chest" or r.get("source") != "placement" or group_of(item) is None or \
                spec.get("call") or spec.get("progressive"):
            continue
        chest0 = (spec.get("extra") or {}).get("Gyaml") or r["actor"]
        # The Treasure Chest Game's chests keep the game's own AI. The guarded give and hold-up still name and show
        # the Blue Rupee.
        if chest0.startswith("Obj_HrlCity_Shop_TBox"):
            continue
        keys = drop_tools.ammo_switch_sets(item, RUPEE)
        spec["extra"] = dict(spec.get("extra") or {}, **{k.split(".", 1)[1]: v for k, v in keys.items()})
        chest = (spec.get("extra") or {}).get("Gyaml") or r["actor"]
        f = drop_tools.root_ai_of(chest, romfs)
        if f is None:
            raise ValueError(f"{rid}: chest type {chest} runs no root AI for the ammo switch")
        ai.add(("*", f))
        tables.add(_chest_table(chest, romfs))
        chests.append({"id": rid, "files": list(r["files"]), "hash": str(r["hash"]), "item": item})
    if not ai:
        return {}
    out = drop_tools.ammo_switch_ops(ai, romfs, plan.get("_drops_components") or (), tables)
    out["_ammo_switch"] = {"ai": [[p if p == "*" else list(p), f] for p, f in sorted(ai, key=str)], "chests": chests}
    return out


def _ends(fc):
    """The end of each container chain in flowchart `fc`, for our guards (Rando_AmmoGuard_* graphs, WP_HOST) and the
    carrier's quiet gives (RandoST_*_own<j>, in the air too).
    Returns [(file-local name of the chain's last "not owned" step, what its NO answer runs)], where that's
    (actor.action, params) or None. A chain is the EventQueryIsExistInPouch steps on a container's owners, and its
    end is the one whose NO answer isn't another owner query."""
    ev = fc["events"]
    out = []
    owners = {o for g in GROUPS for o in (owners_of(GROUPS[g][-1]) or [])}
    for e in ev:
        name = e["name"]
        if e["type"] != "switch" or not (name.startswith(("Rando_AmmoGuard_", WP_HOST)) or
                                         (name.startswith(("RandoST_LakePickups_", "RandoST_HeartWP_", "RandoST_LakeWP_"))
                                          and "_own" in name)):
            continue
        a = fc["actors"][e["actor"]]
        p = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in ((e.get("params") or {}).get("items") or {}).items()}
        if a["queries"][e["query"]] != "EventQueryIsExistInPouch" or p.get("Actor") not in owners:
            continue
        no = next((c["next"] for c in e.get("cases") or [] if c["value"] == NO), None)
        nx = ev[no] if no is not None and no < len(ev) else None
        if nx is not None and nx["type"] == "switch" and \
                fc["actors"][nx["actor"]]["queries"][nx["query"]] == "EventQueryIsExistInPouch":
            continue  # not the chain's last owner
        what, named = None, False
        if nx is not None and nx["type"] == "subflow":  # Early container check: the entry runs again for the Blue Rupee
            what = (f"call {nx.get('flowchart') or ''}:{nx.get('entry_point')}",
                    {k: (v.get("value") if isinstance(v, dict) else v)
                     for k, v in ((nx.get("params") or {}).get("items") or {}).items()})
            named = True  # the called entry's own window names what it gives
        elif nx is not None and nx["type"] == "action":
            na = fc["actors"][nx["actor"]]
            what = (f"{na['name']}.{na['actions'][nx['action']]}",
                    {k: (v.get("value") if isinstance(v, dict) else v)
                     for k, v in ((nx.get("params") or {}).get("items") or {}).items()})
            if what[0] == "GameDataActor.EventTriggerSetGameDataString64" and what[1].get("Value") == RUPEE and \
                    nx.get("next") not in (None, 0xFFFF):  # the Blue Rupee named, then added
                named, nx = True, ev[nx["next"]]
                na = fc["actors"][nx["actor"]] if nx["type"] == "action" else None
                what = (f"{na['name']}.{na['actions'][nx['action']]}",
                        {k: (v.get("value") if isinstance(v, dict) else v)
                         for k, v in ((nx.get("params") or {}).get("items") or {}).items()}) if na else None
        out.append((name, what, named))
    return out


def verify_no_container(fs, want):
    """Reads remake_ammo_without_container back. In GetPouchContent and both get scenes, every container chain of the
    guards and the carrier's quiet gives has to end in a Blue Rupee add (RUPEE) when nothing is owned with
    "blue_rupee", and in no add of it with "nothing"."""
    from evfl import Evfl
    bad, seen = [], 0
    for f in ("GetPouchContent", "Dm_SY_Get", WP_FILE):
        for fc in Evfl(fs.read(f"Event/EventFlow/{f}.bfevfl.zs")).flowcharts:
            for name, what, named in _ends(fc):
                seen += 1
                rupee = what is not None and (
                    what[0] == "PouchSystemActor.EventTriggerAddOrRemovePouchContent" and what[1].get("Actor") == RUPEE
                    or what[0] == f"call :{WINDOW_FILE}" and what[1].get("ActorName") == RUPEE)
                if (want == "blue_rupee") != rupee:
                    bad.append(f"ammo: {f}:{name}: with no container it " + ("adds a Blue Rupee" if rupee else
                               f"goes on to {what[0] if what else 'the next step'}") + f" ({KEY} {want!r})")
                elif rupee and name.startswith("Rando_Ammo") and not named:  # a guard, its window names the item
                    bad.append(f"ammo: {f}:{name}: adds a Blue Rupee but the window would name the ammo "
                               f"({NAME_SLOT} isn't set to {RUPEE} first)")
    if not seen:
        bad.append("ammo: no container guard found in GetPouchContent or the get scenes")
    if want == "blue_rupee":  # check the container before the get window opens, or Mido's chests
        # show the ammo and 0/0 with the Event0 guard behind the window
        wfc = Evfl(fs.read(f"Event/EventFlow/{WINDOW_FILE}.bfevfl.zs")).flowcharts[0]
        ep = wfc["entry_points"].get(WINDOW_FILE)
        first = wfc["events"][ep["main"] if isinstance(ep, dict) else ep]["name"] if ep is not None else None
        if not (first or "").startswith(WINDOW_GRAPH + "_"):
            bad.append(f"ammo: {WINDOW_FILE}:{WINDOW_FILE} starts with {first}, not the container check: with no "
                       f"container its get window shows the ammo and its 0/0, not the Blue Rupee")
    # the hold-ups' show steps. With "blue_rupee" each one is only reached through its guard, whose "not owned" end
    # shows TBox_Rupee_Blue. With "nothing" none is guarded.
    fc = Evfl(fs.read(f"Event/EventFlow/{SHOW_FILE}.bfevfl.zs")).flowcharts[0]
    ev = fc["events"]
    names = {e["name"]: i for i, e in enumerate(ev)}
    steps = [e for e in show_steps(fc) if not e["name"].startswith("Rando")]  # the game's own (ours show no ammo)
    for e in steps:
        i, graph = names[e["name"]], f"{SHOW_GRAPH}_{e['name']}"
        into = [ev[j]["name"] for j, x in enumerate(ev) if i in [x.get("next")] + [c["next"] for c in x.get("cases") or []]
                + list(x.get("forks") or [])]
        entries = [k for k, v in fc["entry_points"].items() if (v["main"] if isinstance(v, dict) else v) == i]
        guarded = bool(into) and not entries and all(n.startswith(graph + "_") for n in into)
        shows = [x for x in ev if x["name"] == f"{graph}_rshow"]
        rupee = bool(shows) and ((shows[0].get("params") or {}).get("items") or {}).get("Actor", {}).get("value") == RUPEE
        if want == "blue_rupee" and not (guarded and rupee):
            bad.append(f"ammo: {SHOW_FILE}:{e['name']}: the hold-up shows its item with no container check "
                       f"(reached from {entries or into}; Blue Rupee show {'present' if rupee else 'missing'})")
        if want != "blue_rupee" and (shows or not entries and into and all(n.startswith(graph + "_") for n in into)):
            bad.append(f"ammo: {SHOW_FILE}:{e['name']}: guarded with {KEY} {want!r}")
    if not steps:
        bad.append(f"ammo: {SHOW_FILE}: no show step of the ActorName argument (game update?)")
    return bad


def _set_name(how, nxt):
    if how == "arg":
        return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                "params": {"GameDataName": NAME_SLOT, "Index": -1, "Value": {"arg": "ActorName"}}, "next": nxt}
    return {"actor": "PouchContentGuestPerformer", "action": "EventTriggerSetOwnNameToMessage", "next": nxt}


def guard_nodes(how, add, skip, rupee_add=True):
    """(nodes, start) for a guard. It writes the name, then for each ammo actor asks "is it this one?" and then "is its
    container owned?". Not ammo, or owned, goes to `add`. Ammo without its container goes to `skip` (labels or
    "@Event" references), and with "blue_rupee" the Blue Rupee gets named and added first (rupee_add, the show guards
    only switch the shown model)."""
    import progressive
    n = {}
    names = [(g, a) for g, actors in GROUPS.items() for a in actors]
    for k, (g, a) in enumerate(names):
        n[f"is{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                       "params": {"GameDataName": NAME_SLOT, "Index": -1, "Value": a},
                       "cases": {YES: f"own_{g.replace(' ', '')}_0", NO: f"is{k + 1}" if k + 1 < len(names) else add}}
    for g in GROUPS:
        lab = g.replace(" ", "")
        owners = [o for tier in progressive.PROGRESSIVE[g]["tiers"] for o in progressive.owned_by(tier)]
        owners = list(dict.fromkeys(owners))
        rupee = rupee_node(skip) if rupee_add else None  # "blue_rupee": a Blue Rupee instead, named first
        if rupee:
            n[f"rupee_{lab}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                                 "params": {"GameDataName": NAME_SLOT, "Index": -1, "Value": RUPEE},
                                 "next": f"radd_{lab}"}
            n[f"radd_{lab}"] = rupee
        for j, o in enumerate(owners):
            n[f"own_{lab}_{j}"] = {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                                 "params": {"Actor": o, "Num": 1},
                                 "cases": {YES: add, NO: f"own_{lab}_{j + 1}" if j + 1 < len(owners)
                                           else (f"rupee_{lab}" if rupee else skip)}}
    from write_read_check import settle  # the name lands a frame or two later, so compare after that
    n["name"] = _set_name(how, "settle")
    n["settle"] = settle("is0")
    return n, "name"


def guard_ops(romfs=DEFAULT_ROMFS):
    """Plan "events" ops: the three guards (see the module doc)."""
    from romtools import Romfs
    from evfl import Evfl
    import progressive
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    ops = []

    def step(file, name, action):
        fc = Evfl(fs.read(f"Event/EventFlow/{file}.bfevfl.zs")).flowcharts[0]
        ev = next((e for e in fc["events"] if e["name"] == name), None)
        if ev is None or ev["type"] != "action" or fc["actors"][ev["actor"]]["actions"][ev["action"]] != action:
            raise ValueError(f"{file}: {name} is no longer {action}")
        nxt = ev["next"]
        return fc, ev, (None if nxt in (None, 0xFFFF) else fc["events"][nxt]["name"])

    def reroute(file, fc, ev, target):
        for kind, where, k in progressive.predecessors(fc, ev):
            op = {"file": file, "flowchart": file, "next": target}
            if kind == "entry":
                op["entry"] = where
            else:
                op["event"] = where
                if kind in ("case", "fork"):
                    op[kind] = k
            ops.append(op)

    actions = {"GetPouchContent": "EventTriggerAddOrRemovePouchContent", "Dm_SY_Get": "EventTriggerAddOwnToPouch"}
    for file, name, how in TARGETS:
        fc, ev, after = step(file, name, actions[file])
        graph = f"Rando_AmmoGuard_{name}"
        nodes, start = guard_nodes(how, f"@{name}", f"@{after}" if after else None)
        ops.append({"file": file, "flowchart": file, "add_graph": graph, "nodes": nodes, "start": start})
        reroute(file, fc, ev, f"{graph}_{start}")
    if mode() == "blue_rupee":
        # Event7 opens the GetPouchContent window before Event0 adds the item, so we check for the container at the
        # entry too, or Mido's chests show ammo at 0/0. If it's missing, rerun the entry for the Blue Rupee so the
        # window and the pouch agree. Otherwise go on to the original window and add.
        fc = Evfl(fs.read(f"Event/EventFlow/{WINDOW_FILE}.bfevfl.zs")).flowcharts[0]
        first = fc["events"][fc["entry_points"][WINDOW_FILE]["main"]]
        nodes, start = guard_nodes("arg", f"@{first['name']}", "rcall", rupee_add=False)
        nodes["rcall"] = {"call": f":{WINDOW_FILE}", "next": None,
                          "params": dict({a: {"arg": a} for a in WINDOW_ARGS}, ActorName=RUPEE)}
        ops.append({"file": WINDOW_FILE, "flowchart": WINDOW_FILE, "add_graph": WINDOW_GRAPH, "nodes": nodes,
                    "start": start})
        reroute(WINDOW_FILE, fc, first, f"{WINDOW_GRAPH}_{start}")
    # in the air or water the step calls the guarded add in Dm_SY_Get (for its GameDataActor), then goes on
    fc, ev, after = step(WP_FILE, WP_STEP, "EventTriggerAddOwnToPouch")
    nodes, start = guard_nodes("own", "add", None)
    nodes["add"] = {"actor": "PouchContentGuestPerformer", "action": "EventTriggerAddOwnToPouch", "next": None}
    ops.append({"file": "Dm_SY_Get", "flowchart": "Dm_SY_Get", "add_graph": WP_HOST, "nodes": nodes, "start": start})
    graph = "Rando_AmmoGuard_WP"
    ops.append({"file": WP_FILE, "flowchart": WP_FILE, "add_graph": graph, "start": "call",
                "nodes": {"call": {"call": f"Dm_SY_Get:{WP_HOST}", "next": f"@{after}" if after else None}}})
    reroute(WP_FILE, fc, ev, f"{graph}_call")
    if mode() == "blue_rupee":  # the hold-ups show the Blue Rupee too (SHOW_FILE)
        sfc = Evfl(fs.read(f"Event/EventFlow/{SHOW_FILE}.bfevfl.zs")).flowcharts[0]
        for ev in show_steps(sfc):
            after = None if ev["next"] in (None, 0xFFFF) else sfc["events"][ev["next"]]["name"]
            graph = f"{SHOW_GRAPH}_{ev['name']}"
            nodes, start = guard_nodes("arg", f"@{ev['name']}", "rshow", rupee_add=False)
            params = {k: (v.get("value") if isinstance(v, dict) and v.get("type") != "argument" else v)
                      for k, v in ((ev.get("params") or {}).get("items") or {}).items()}
            params = {k: v for k, v in params.items() if not isinstance(v, dict)}
            nodes["rshow"] = {"actor": sfc["actors"][ev["actor"]]["name"], "action": SHOW_ACTION,
                              "params": dict(params, Actor=RUPEE), "next": f"@{after}" if after else None}
            ops.append({"file": SHOW_FILE, "flowchart": SHOW_FILE, "add_graph": graph, "nodes": nodes, "start": start})
            reroute(SHOW_FILE, sfc, ev, f"{graph}_{start}")
    return {"events": ops, "_ammo_no_container": mode(), "_notes_ammo": [
        "ammo without its container (bombs need a Bomb Bag, arrows a Bow, Deku Seeds a Slingshot) "
        + ("gives a Blue Rupee instead (OoTR)" if mode() == "blue_rupee" else "adds nothing")
        + "; guarded at GetPouchContent Event0, Dm_SY_Get Event35 and Dm_SY_Get_WithoutPlayer Event0 "
        "(shop bundles excluded)"]}
