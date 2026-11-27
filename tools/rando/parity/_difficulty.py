"""OOTRR's difficulty options that the remake's own data can do (extras_qol settings, all off by default).
Each one reads the player's game when the seed is made (plan stops if something isn't where it should be) and is
read back from the built patch (verify).

- remake_shorter_timers "off" | "three_quarters" | "half": the dungeons' puzzles on a clock give 75% or 50% of their
  time. Those are timed floor switches (Obj_StepSwitch_A_02, CountTime), timed eye switches (Obj_EyeSwitch_A_05,
  LimitTime) and torches that burn out (Obj_CandleStick_TimeExtinguish_A_01, ExtinguishTime; a placement without one
  uses the 15 s of the torch's blackboard table). The time is the placement's own value in its level file, so only
  the placements change. Every puzzle keeps a floor so it stays winnable:
    floor switch  10 s   (the Deku Tree's 20.2 s switch, the Fire Temple's 19 s and 12.95 s ones)
    eye switch     6 s   (Dodongo's Cavern's: the doors they open are about 20 m off, 4 s at a run)
    torches       the time to walk from torch to torch through the whole room at 3 m/s (the shortest of the
                  nearest-torch-next routes), plus 3 s to light them; the "flame weakening" warning time is scaled
                  with the torch so it never outlasts the flame
  Left alone: a timer of 1 s or less (the Water Temple's eye switches) or of 999 s or more (Gerudo Training Ground's
  "no clock" switch), a torch that's alone in its room (no way to tell what its time is for), and everything outside
  the dungeons (Zora's Domain's torches are the ZD Chest puzzle you light with a Deku Stick, Goron City's open its
  shop the same way, and Dampe's race keeps its own clock).
- remake_unbreakable_bowling_grass False | True: the bushes in the Bombchu Bowling lanes (17
  Obj_HrlCity_Shop_MovingObstacle_A_01 in the child Market, one set per difficulty) can't be broken, so the Bombchus
  have to go round them. The obstacle dies two ways, both in its own pack: its AI graph requests its death when an
  attacker hit it from close by (a BoolSelector on QueryGetLastAttackerInfoFromExternalDamageCalculator, then a
  distance check, then OneShotDeathRequestDeath), and its chemistry dies when burned or exploded. The selector's True
  branch now goes to the graph's own do-nothing node, and the obstacle gets its own copy of its chemistry file with
  both deaths off (that file, Obj_ContactOnly, is shared by 37 packs, bomb flowers among them). Its collision and its
  reset between rounds stay.
- remake_enemy_speed 100, or a whole percent from 75 to 200: enemies move and attack faster or slower. Every speed in
  an enemy's movement file (BSA/MovementParam, walk, jog, run, dash, escape...; not turning, not how fast it gets up
  to speed) times the percent, and every wait in its attack timing file (GameBalance/AttackInterval) divided by it.
  Bosses keep their pace (their fights are scripted around it): Gohma, King Dodongo, Barinade, Phantom Ganon and his
  horse, Twinrova, Ganondorf, Ganon. Minibosses change. An enemy that moves by its animations only (Octoroks,
  Skulltulas) and one without its own attack timing keep theirs.
- remake_enemies_respawn False | True: ordinary enemies you beat come back once their part of the map loads again
  (you leave and come back). Each of RESPAWN_TABLES stops remembering every way of dying, the way the game's own
  AlwaysRespawn tables do it. Left as they are: bosses and minibosses, Iron Knuckles, Dead Hand, Poes, the Skull
  Kid, scrubs, Gold Skulltulas, Jabu-Jabu's tentacles (beating one opens a way), Gohma's eggs and larvae, and
  enemies whose table is a shared base one (Beamos, Lizalfos, Anubis). A room that opens once its enemies are beaten
  keeps its own count, so it should stay open; that's for the test to show.
- remake_no_bottles_in_combat False | True: no drinking from a bottle or letting out its contents (a fish, bugs, Blue
  Fire, a fairy) while an enemy is after you or in a boss fight (BOTTLE_FLOWS, the guard below).
- remake_no_dupe_bottles False | True: no second bottle of the same thing: catching (CATCH_FLOW), milking a cow
  (COW_FLOW) and buying (SHOP_FLOW) are refused while a bottle holds that already (the notes at COW_FLOW say which
  contents and why not the hand-overs in scenes).
- remake_limited_ammo False | True: random drops give no ammo, the game's own supplies do (see the notes at
  KEEP_AMMO). Bombchu drops (OoTR's free_bombchu_drops) aren't in these tables and stay: logic counts them.
- remake_lose_heart_on_death False | True: each Try Again after a game over costs a heart container, down to 3 hearts
  (heart_plan, the notes above it).
- remake_enemy_regen False | True: enemies slowly heal while alive (regen_plan, the notes above it).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

# Shorter timers
TIMER_SHARE = {"three_quarters": 0.75, "half": 0.5}
DUNGEONS = ("InsideTheDekuTree", "DodongoCavern", "InsideJabuJabuBelly", "ForestTemple", "FireTemple", "WaterTemple",
            "ShadowTemple", "SpiritTemple", "BottomOfTheWell", "IceCavern", "GerudoTrainingGround", "InsideGanonCastle")
SWITCHES = {"Obj_StepSwitch_A_02": ("CountTime", 10.0), "Obj_EyeSwitch_A_05": ("LimitTime", 6.0)}
TORCH = "Obj_CandleStick_TimeExtinguish_A_01"
TORCH_PACK = f"Pack/Actor/{TORCH}.pack.zs"
TORCH_TABLE = f"Component/Blackboard/BlackboardParamTable/{TORCH}.engine__component__BlackboardParamTable.bgyml"
NO_CLOCK = (1.0, 999.0)  # a timer at or under the first, or at or over the second, isn't a puzzle's clock
WALK = 3.0   # m/s, slower than Link runs: the torches' floor
LIGHT = 3.0  # s, to light the torches on top of walking between them

# Unbreakable Bombchu Bowling grass
BOWLING_PACK = "Pack/Actor/Obj_HrlCity_Shop_MovingObstacle_A_01.pack.zs"
BOWLING_AI = "AI/Obj_HrlCity_Shop_MovingObstacle_A_01.root.ainb"
BOWLING_ACTOR = "Actor/Obj_HrlCity_Shop_MovingObstacle_A_01.engine__actor__ActorParam.bgyml"
BOWLING_CHEM = "Component/ChemicalParam/Obj_ContactOnly.game__component__ChemicalParam.bgyml"
BOWLING_OWN_CHEM = ("Component/ChemicalParam/RandoObj_HrlCity_Shop_MovingObstacle_A_01"
                    ".game__component__ChemicalParam.bgyml")
HIT_QUERY = "QueryGetLastAttackerInfoFromExternalDamageCalculator"
DUMMY = "ExecuteGenericDummyAction"
CHEM_DEATHS = ("RequestDeathIfBurned", "RequestDeathIfExploded")

# Enemy speed
SPEED_RANGE = (75, 200)
MOVEMENT = "BSA/MovementParam/"
ATTACK = "GameBalance/AttackInterval/"
SAME_PACE = ("Enemy_DungeonBoss_", "Enemy_PhantomGanonHorse")  # bosses keep their pace


# Enemies respawn: an enemy's death table (System/CombinationDataTableData/<X>_game__death__DeathReasonProcedures...,
# which inherit through "$parent") says per way of dying whether the game remembers it (IsSetRespawnFlagToFalse, and
# IsSetGmdRespawnFlagToFalse for the save). The game's own "AlwaysRespawn" enemies (a Stalfos, a ReDead, an Armos, a
# Shabom) turn those off. Only ordinary enemies with a table of their own change, never a shared base table.
DEATH_DIR = "System/CombinationDataTableData/"
DEATH_SUFFIX = "_game__death__DeathReasonProcedures.pp__CombinationDataTableData.bgyml"
CELL_TYPE = "game__death__DeathReasonProceduresCell"
REMEMBER = ("IsSetRespawnFlagToFalse", "IsSetGmdRespawnFlagToFalse")
RESPAWN_TABLES = ("Amos", "BabyDodongo", "Bari", "Biri", "Bubble", "Bubble_Green_Big", "Redead", "Dekubaba",
                  "Dekubaba_DekuStickDrop", "DekubabaWithered", "Dodongo", "Enemy_Floormaster", "Floormaster_Little",
                  "Enemy_Freezard", "Guay", "Enemy_Guay_Fixed", "Enemy_Keese", "Leever", "Leever_Fixed",
                  "Enemy_LikeLike", "Enemy_Moblin", "MoblinClub", "Enemy_Octorok", "Enemy_Peahat",
                  "Enemy_Peahat_Larva", "Enemy_Shabom", "ShellBlade", "Skulltula", "Enemy_Skullwalltula", "Stalchild",
                  "Enemy_Stalfos", "Enemy_Stinger", "Enemy_Tektite", "Enemy_TorchSlug", "Enemy_Wallmaster",
                  "Enemy_Wolfos")


def _death_cells(fs, name):
    """{cell: {key: value}} of a death table with everything it inherits (its own values win)."""
    import romtools
    doc = romtools.byml_load(fs.raw(DEATH_DIR + name + DEATH_SUFFIX))[0]
    parent = (doc.get("$parent") or "").rsplit("/", 1)[-1].replace(DEATH_SUFFIX.replace(".bgyml", ".gyml"), "")
    out = _death_cells(fs, parent) if parent else {}
    for cell, vals in (doc.get("CellList") or {}).items():
        out[cell] = dict(out.get(cell, {}), **vals)
    return out


def respawn_plan(romfs):
    """(byml ops, read-back [table, ...]) for remake_enemies_respawn: in each of RESPAWN_TABLES, every way of dying
    its chain remembers gets both remember switches off, in the table's own cell (made when it only inherits it)."""
    import romtools
    fs = _fs(romfs)
    ops, tables = [], []
    for name in RESPAWN_TABLES:
        rel = DEATH_DIR + name + DEATH_SUFFIX
        doc = romtools.byml_load(fs.raw(rel))[0]
        own = doc.get("CellList") or {}
        sets = {}
        for cell, vals in sorted(_death_cells(fs, name).items()):
            if vals.get("IsIgnoreThisDeathReason") or not vals.get("IsSetRespawnFlagToFalse"):
                continue
            if cell in own:
                sets.update({f"CellList.{cell}.{k}": False for k in REMEMBER})
            else:
                sets[f"CellList.{cell}"] = {"$type": CELL_TYPE, **{k: False for k in REMEMBER}}
        if not sets:
            continue
        if "CellList" not in doc:
            raise RuntimeError(f"remake_enemies_respawn: {rel} has no CellList of its own")
        ops.append({"file": rel, "set": sets, "note": "remake_enemies_respawn"})
        tables.append(name)
    if len(tables) < len(RESPAWN_TABLES) // 2:
        raise RuntimeError(f"remake_enemies_respawn: only {len(tables)} of the enemies' death tables remember a death")
    return ops, tables


# No bottles in combat: the three flows that use a bottle (drink it, let its contents out, let a fairy out) each start
# with a guard: a boss fight (save data IsBossBattle) or the battle music playing (SoundSystemActor's
# EventQueryIsPlayingBgmName, BGM_EnemyBattle, which an enemy starts once it's after you; music shuffle changes its
# tracks, never its name) means no. Then Link shakes his head (EvtTalkNo, the "no" the game's flows use 177 times)
# and puts the bottle away the way every bottle flow ends (EventPlayerDrawnShieldAfterUseBottle; ending earlier leaves
# him frozen). A fairy that saves you when you fall isn't one of these flows, so it still does.
BOTTLE_FLOWS = ("Dm_SY_DrinkBottle", "Dm_SY_OutBottle", "Dm_SY_OutBottleFairy")
BATTLE_BGM = "BGM_EnemyBattle"
BOSS_FLAG = "IsBossBattle"
YES, NO = 0, 1  # a yes/no query's cases: 0 is yes
GUARD = "Rando_NoBottleFight"


def _guard_nodes(go_on):
    """The guard's steps: boss fight or battle music -> refuse, else `go_on` (an "@Event" of the flow)."""
    return {
        "boss": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool", "new_actor": True,
                 "params": {"Index": -1, "GameDataName": BOSS_FLAG}, "cases": {YES: "start", NO: "music"}},
        "music": {"actor": "SoundSystemActor", "query": "EventQueryIsPlayingBgmName", "new_actor": True,
                  "params": {"BgmName": BATTLE_BGM}, "cases": {YES: "start", NO: go_on}},
        "start": {"actor": "Player_Event", "action": "EventTriggerPlayerEventStartWithDrawn", "params": {},
                  "next": "shake"},
        "shake": {"actor": "Player_Event", "action": "EventPlayerPlayASForFlowchart",
                  "params": {"IsWaitEnd": True, "UseAnmDriven": False, "IsAllSlot": False, "KeepOneTimeAnm": False,
                             "ForceFadeFrame": -1.0, "ASCommand": "EvtTalkNo", "ClothWarpMode": 0},
                  "next": "away"},
        "away": {"actor": "Player_Event", "action": "EventPlayerDrawnShieldAfterUseBottle",
                 "params": {"IsWaitEnd": True, "IsImmediateDrawn": False}, "next": None},
    }


def bottle_plan(romfs):
    """(event ops, read-back [[file, entry, graph], ...]) for remake_no_bottles_in_combat: a guard in front of every
    entry point of the bottle flows."""
    import romtools
    from evfl import Evfl
    from parity._story_build import newest
    fs = _fs(romfs)
    ops, rows = [], []
    for file in BOTTLE_FLOWS:
        rel, _ = newest(romfs, file)
        fc = next((f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == file), None)
        if fc is None or not fc["entry_points"]:
            raise RuntimeError(f"remake_no_bottles_in_combat: {rel} has no flowchart {file}")
        if not any("EventPlayerDrawnShieldAfterUseBottle" in a.get("actions", []) for a in fc["actors"]
                   if a["name"] == "Player_Event"):
            raise RuntimeError(f"remake_no_bottles_in_combat: {file} doesn't put the bottle away as expected")
        for entry, ep in sorted(fc["entry_points"].items()):
            graph = f"{GUARD}_{entry}"
            first = fc["events"][ep["main"]]["name"]
            ops.append({"file": file, "flowchart": file, "add_graph": graph, "nodes": _guard_nodes(f"@{first}"),
                        "start": "boss", "note": "remake_no_bottles_in_combat"})
            ops.append({"file": file, "flowchart": file, "entry": entry, "next": f"{graph}_boss",
                        "note": "remake_no_bottles_in_combat"})
            rows.append([file, entry, graph])
    return ops, rows


# No duplicate catches: catching something in a bottle (Dm_SY_InsertBottle, whose BottleItem argument is the content's
# number: 9 a fairy, 7 a Poe, 6 a Big Poe...) first asks PouchSystemActor's EventQueryIsExistBottleTypeInPouch, the
# query the game over and fall flows use to find a fairy, with that same number. Holding one already: Link shakes his
# head and puts the bottle away, like the bottle guard above, and lets the item cycle again (the catch stops it).
CATCH_FLOW = "Dm_SY_InsertBottle"
CATCH_ENTRY = "EntryPoint0"  # (its other entry is the Market's bottle tutorial)
NO_DUPE = "Rando_NoDupeCatch"
# Buying and milking too: a cow's milk entries (Animal_Cow) and a shop's bottled items (DisplayShop, the item kind 5
# its EventQueryCheckShopSelectItemName gives them, the name in Shop_SelectItemName) go their own "no empty bottle"
# way when a bottle holds that already. The content numbers are the ones the game's own flows use (9 a fairy in the
# game over flow, 6/7 the Poes in PoeSpiritTalkEvent, 3/4/8 in the Market bottle seller's, 0/10/9 in the business
# scrubs' dream flow); Green Potion and half milk aren't in any, so they aren't checked. Things handed over in a scene
# (Dm_SY_GetInEvent) aren't either: the scene would still show you getting it.
COW_FLOW = "Animal_Cow"
COW_ENTRIES = ("PushToBottleMilk", "PushToBottleMilk_LinkHouse", "PushToBottleMilk_LinkHouse0")
COW_CHECKS = ("EventQueryIsExistBottleTypeInPouch", "EventQueryIsAnyBottleEmpty")
MILK = 10
SHOP_FLOW = "DisplayShop"
SHOP_BOTTLE_KIND = 5
BOTTLED = {"Item_Bottle_RedPotion": 0, "Item_Bottle_BluePotion": 2, "Item_Bottle_BlueFire": 3, "Item_Bottle_Fish": 4,
           "Item_Bottle_BigPoe": 6, "Item_Bottle_Poe": 7, "Item_Bottle_Bug": 8, "Item_Bottle_Fairy": 9,
           "Item_Bottle_Milk": MILK}


def dupe_plan(romfs, cows=True):
    """(event ops, read-back [file, entry, graph], the shop's read-back) for remake_no_dupe_bottles. cows=False (the
    cows hold checks): their milk entries hand out the check, so they're left alone."""
    from evfl import Evfl
    from parity._story_build import newest
    fs = _fs(romfs)
    rel, _ = newest(romfs, CATCH_FLOW)
    fc = next((f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == CATCH_FLOW), None)
    if fc is None or CATCH_ENTRY not in fc["entry_points"]:
        raise RuntimeError(f"remake_no_dupe_bottles: {rel} has no {CATCH_ENTRY}")
    push = [e for e in fc["events"] if e["type"] == "action"
            and fc["actors"][e["actor"]]["actions"][e["action"]] == "EventTriggerPushToEmptyBottle"]
    if not push or any("BottleItem" not in str((e.get("params") or {})) for e in push):
        raise RuntimeError(f"remake_no_dupe_bottles: {CATCH_FLOW} doesn't fill the bottle from its BottleItem")
    first = fc["events"][fc["entry_points"][CATCH_ENTRY]["main"]]["name"]
    nodes = {
        "held": {"actor": "PouchSystemActor", "query": "EventQueryIsExistBottleTypeInPouch",
                 "params": {"BottleItem": {"arg": "BottleItem"}}, "cases": {YES: "start", NO: f"@{first}"}},
        "start": {"actor": "Player_Event", "action": "EventTriggerPlayerEventStartWithDrawn", "params": {},
                  "next": "shake"},
        "shake": {"actor": "Player_Event", "action": "EventPlayerPlayASForFlowchart",
                  "params": {"IsWaitEnd": True, "UseAnmDriven": False, "IsAllSlot": False, "KeepOneTimeAnm": False,
                             "ForceFadeFrame": -1.0, "ASCommand": "EvtTalkNo", "ClothWarpMode": 0},
                  "next": "away"},
        "away": {"actor": "Player_Event", "action": "EventPlayerDrawnShieldAfterUseBottle",
                 "params": {"IsWaitEnd": True, "IsImmediateDrawn": True}, "next": "resume"},
        "resume": {"actor": "Player_Event", "action": "EventTriggerPlayerStartUpdateSelectedItem", "params": {},
                   "next": None},
    }
    graph = f"{NO_DUPE}_{CATCH_ENTRY}"
    ops = [{"file": CATCH_FLOW, "flowchart": CATCH_FLOW, "add_graph": graph, "nodes": nodes, "start": "held",
            "note": "remake_no_dupe_bottles"},
           {"file": CATCH_FLOW, "flowchart": CATCH_FLOW, "entry": CATCH_ENTRY, "next": f"{graph}_held",
            "note": "remake_no_dupe_bottles"}]
    rows = [[CATCH_FLOW, CATCH_ENTRY, graph]]
    # cows: their milk entries start by asking for an empty bottle; holding milk already goes their own "no empty
    # bottle" way
    rel, _ = newest(romfs, COW_FLOW)
    cfc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == COW_FLOW)
    for entry in COW_ENTRIES if cows else ():
        ep = cfc["entry_points"].get(entry)
        if ep is None:
            raise RuntimeError(f"remake_no_dupe_bottles: {COW_FLOW} has no {entry}")
        first = cfc["events"][ep["main"]]
        a = cfc["actors"][first["actor"]]
        if first["type"] != "switch" or a["queries"][first["query"]] not in COW_CHECKS:
            raise RuntimeError(f"remake_no_dupe_bottles: {COW_FLOW} {entry} doesn't start with the empty bottle check")
        no = cfc["events"][first["cases"][NO]["next"]]["name"]
        g = f"{NO_DUPE}_{entry}"
        ops += [{"file": COW_FLOW, "flowchart": COW_FLOW, "add_graph": g, "start": "held",
                 "nodes": {"held": {"actor": "PouchSystemActor", "query": "EventQueryIsExistBottleTypeInPouch",
                                    "params": {"BottleItem": MILK}, "cases": {YES: f"@{no}", NO: f"@{first['name']}"}}},
                 "note": "remake_no_dupe_bottles"},
                {"file": COW_FLOW, "flowchart": COW_FLOW, "entry": entry, "next": f"{g}_held",
                 "note": "remake_no_dupe_bottles"}]
        rows.append([COW_FLOW, entry, g])
    # shops: a bottled item (the shop's item kind 5) asks for an empty bottle first; one a bottle holds already goes
    # the shop's own "no empty bottle" way
    rel, _ = newest(romfs, SHOP_FLOW)
    sfc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == SHOP_FLOW)
    kinds = [e for e in sfc["events"] if e["type"] == "switch"
             and sfc["actors"][e["actor"]]["queries"][e["query"]] == "EventQueryCheckShopSelectItemName"]
    def asks_empty(i):
        t = sfc["events"][i]
        return t["type"] == "switch" and sfc["actors"][t["actor"]]["queries"][t["query"]] == "EventQueryIsAnyBottleEmpty"
    hits = [(e, c) for e in kinds for c in e["cases"] if c.get("value") == SHOP_BOTTLE_KIND and asks_empty(c["next"])]
    if len(hits) != 1:
        raise RuntimeError(f"remake_no_dupe_bottles: {SHOP_FLOW} has {len(hits)} bottled-item checks, not one")
    kind, case = hits[0]
    check = sfc["events"][case["next"]]
    no = sfc["events"][check["cases"][NO]["next"]]["name"]
    nodes = {}
    items = sorted(BOTTLED.items())
    for k, (name, code) in enumerate(items):
        nxt = f"is{k + 1}" if k + 1 < len(items) else f"@{check['name']}"
        nodes[f"is{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64", "new_actor": True,
                           "params": {"GameDataName": "Shop_SelectItemName", "Index": -1, "Value": name},
                           "cases": {YES: f"held{k}", NO: nxt}}
        nodes[f"held{k}"] = {"actor": "PouchSystemActor", "query": "EventQueryIsExistBottleTypeInPouch",
                             "new_actor": True, "params": {"BottleItem": code},
                             "cases": {YES: f"@{no}", NO: f"@{check['name']}"}}
    g = f"{NO_DUPE}_Shop"
    ops += [{"file": SHOP_FLOW, "flowchart": SHOP_FLOW, "add_graph": g, "nodes": nodes, "start": "is0",
             "note": "remake_no_dupe_bottles"},
            {"file": SHOP_FLOW, "flowchart": SHOP_FLOW, "event": kind["name"],
             "case": kind["cases"].index(case), "next": f"{g}_is0", "note": "remake_no_dupe_bottles"}]
    return ops, rows, {"file": SHOP_FLOW, "event": kind["name"], "case": kind["cases"].index(case), "graph": g}


# Limited ammo: random drops (pots, grass, rocks, crates, trees, enemies) give no arrows, Deku Seeds, bombs, Deku Nuts
# or Deku Sticks. A drop sub-table (Drop/DropSubTable/*, in the actor packs) lists entries by kind (Type, a murmur3
# name) or by a named pickup (Type "Actor", DropActorName). Every ammo entry of a table that isn't one of the game's
# own supplies becomes a named green rupee with the same odds and count, like the game's own named entries, so every
# other drop keeps its chance; a "MostDepletedResource" entry (whatever you're lowest on) keeps only magic. Kept as
# they are: the supplies the game puts where a puzzle or a fight needs ammo (KEEP_AMMO: the tables the maps name for
# their supply pots and grass, the rooms before the bosses, Gohma's room and eggs, the Poe sisters, Poe Meg, Bongo
# Bongo, Ganon's fights) and the Deku
# Babas' sticks and nuts, which OoTR's logic counts (its "Deku Stick Drop" / "Deku Nut Drop" events). Shops, scrubs,
# chests and the seed's own ammo items are no drops, so they stay.
AMMO_TYPES = {3237216321: "bombs", 2211636230: "Deku Nuts", 4192551701: "Deku Sticks", 798871343: "arrows",
              1113099761: "ammo for the weapon you hold"}
AMMO_ACTORS = ("Obj_Bomb", "Obj_Bombchu", "Obj_DekuNut", "Obj_DekuStick", "Obj_DekuSeed", "Obj_ArrowBundle_Small",
               "Obj_ArrowBundle_Medium", "Obj_ArrowBundle_Large")
ACTOR_TYPE = 126134492         # an entry that names its pickup (DropActorName)
LOWEST_TYPE = 2121460961       # murmur3 "MostDepletedResource": whatever you're lowest on, from its list
MAGIC_TYPE = 832898412         # "Mp"
GREEN_RUPEE = "Work/Actor/Obj_Rupee_Green.engine__actor__ActorParam.gyml"
DROP_TABLES = "Drop/DropSubTable/"
KEEP_AMMO = ("DropTable_Obj_Bomb", "DropTable_Obj_DekuNut", "DropTable_Obj_DekuStick", "DropTable_RangeWeapon_",
             "DropTable_ResourceSupply_Gohma", "DropTable_ResourceSupply_FinalBattle", "DropTable_Ganon_Remedies_",
             "Enemy_DungeonBoss_", "Drop_ResourceSupply_BeforeBoss", "Enemy_Dekubaba_DekuStickDrop",
             "DropTable_Enemy_RangedWeapon_",  # the Poe sisters', Poe Meg's, Gohma's eggs' and larvae's: their fights'
             #                                   arrows and seeds
             "DropTable_Dekubaba_DekuNut", "Drop_Test_")
DROP_LISTS = ("Items", "Items_Max_FirstCandidate", "Items_Max_SecondCandidate", "Items_Max_ThirdCandidate")


def _is_ammo(e):
    actor = (e.get("DropActorName") or "").rsplit("/", 1)[-1].split(".")[0]
    return e.get("Type") in AMMO_TYPES or (e.get("Type") == ACTOR_TYPE and actor in AMMO_ACTORS)


def _ammo_sets(d):
    """{path: value} turning sub-table `d`'s ammo entries into green rupees (and its lowest-on lists into magic)."""
    sets = {}
    for key in DROP_LISTS:
        c = d.get(key)
        entries = c if isinstance(c, list) else [c] if isinstance(c, dict) else []
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                continue
            at = f"{key}.{i}" if isinstance(c, list) else key
            if _is_ammo(e):
                sets[f"{at}.Type"] = ACTOR_TYPE
                sets[f"{at}.DropActorName"] = GREEN_RUPEE
            elif e.get("Type") == LOWEST_TYPE and any(t in AMMO_TYPES for t in e.get("MostDepletedResource") or []):
                sets[f"{at}.MostDepletedResource"] = [t for t in e["MostDepletedResource"] if t not in AMMO_TYPES] \
                    or [MAGIC_TYPE]
    return sets


def ammo_plan(romfs):
    """(packs ops, read-back [pack, file, key, value]) for remake_limited_ammo."""
    import packpaths
    import romtools
    fs = _fs(romfs)
    ops, rows = [], []
    for inner, packs in sorted(packpaths.index(romfs).items()):
        if not inner.startswith(DROP_TABLES) or not packs:
            continue
        name = inner[len(DROP_TABLES):].split(".")[0]
        if name.startswith(KEEP_AMMO):
            continue
        sets = _ammo_sets(romtools.byml_load(romtools.sarc_files(fs.read(packs[0]))[inner], allow_big=True)[0])
        if sets:
            ops.append({"pack": list(packs), "file": inner, "set": sets, "note": "remake_limited_ammo"})
            rows += [[pk, inner, k, v] for pk in packs for k, v in sorted(sets.items())]
    if not ops:
        raise RuntimeError("remake_limited_ammo: no drop table gives ammo")
    return ops, rows


# Lose a heart on death: Try Again after a game over reloads your last save, so a heart taken at the game over screen
# comes back. What survives the reload is save data that's never saved and never reset, like
# Sequence_ReservedBootEventName (String64, SaveFileIndex -1, ResetTypeValue 0): the scene the game plays once the
# level has loaded again (Sequence/AfterChangeBanc), the way it plays ShieldHylianNaviHintBootEvent after a load. So
# choosing Try Again (DmF_SY_GameOver, the step setting the result "Retry") first reserves our scene, and that scene,
# a new entry of ShieldHylianNaviHintBootEvent's flow on a reused scene ID copied from that boot event's row, takes
# one heart container off PlayerStatus.MaxLife (in quarter hearts) unless you're at 3 hearts or fewer, keeps your
# health within it and saves. Going back to the title and a fairy's revival lose nothing.
GAME_OVER = "DmF_SY_GameOver"
RETRY_RESULT = ("GameSystemActor", "EventSetEventResult", "EventResult", "Retry")
BOOT_FLOW = "ShieldHylianNaviHintBootEvent"
BOOT_ENTRY = "Rando_LoseHeart"
BOOT_ROW = "SubEvent_GetIceArrow_OpenTBox"  # a scene ID of config/scene_rows.json that no other feature names
RESERVED = "Sequence_ReservedBootEventName"
MAX_LIFE = "PlayerStatus.MaxLife"
HEART = 4  # quarter hearts
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"


def heart_plan(romfs):
    """(event ops, byml ops, read-back) for remake_lose_heart_on_death."""
    from evfl import Evfl
    from parity._story_build import newest, flat
    import progressive
    fs = _fs(romfs)
    rel, _ = newest(romfs, GAME_OVER)
    fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == GAME_OVER)
    actor, action, key, value = RETRY_RESULT
    retry = [e for e in fc["events"] if e["type"] == "action" and fc["actors"][e["actor"]]["name"] == actor
             and fc["actors"][e["actor"]]["actions"][e["action"]] == action
             and flat(e.get("params"), {}).get(key) == value]
    if len(retry) != 1:
        raise RuntimeError(f"remake_lose_heart_on_death: {GAME_OVER} has {len(retry)} Try Again results, not one")
    retry = retry[0]
    events = [{"file": GAME_OVER, "flowchart": GAME_OVER, "add_graph": "Rando_LoseHeartReserve",
               "nodes": {"reserve": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                                     "params": {"GameDataName": RESERVED, "Index": -1, "Value": BOOT_ROW},
                                     "next": f"@{retry['name']}"}},
               "start": "reserve", "note": "remake_lose_heart_on_death"}]
    for kind, where, k in progressive.predecessors(fc, retry):
        op = {"file": GAME_OVER, "flowchart": GAME_OVER, "next": "Rando_LoseHeartReserve_reserve",
              "note": "remake_lose_heart_on_death"}
        if kind == "entry":
            op["entry"] = where
        else:
            op["event"] = where
            if kind in ("case", "fork"):
                op[kind] = k
        events.append(op)
    nodes = {}
    for hearts in (3, 2, 1):  # at 3 hearts or fewer: nothing to lose
        nxt = f"at{hearts - 1}" if hearts > 1 else "lose"
        nodes[f"at{hearts}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt", "new_actor": True,
                                "params": {"GameDataName": MAX_LIFE, "Index": -1, "Value": hearts * HEART},
                                "cases": {YES: None, NO: nxt}}
    nodes["lose"] = {"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt", "new_actor": True,
                     "params": {"GameDataName": MAX_LIFE, "Index": -1, "Value": -HEART}, "next": "heal"}
    nodes["heal"] = {"actor": "Player_Event", "action": "EventTriggerHealLifeMax", "new_actor": True, "params": {},
                     "next": "save"}
    nodes["save"] = {"actor": "GameSystemActor", "action": "EventTriggerRequestAutoSave", "new_actor": True,
                     "params": {}, "next": None}
    events.append({"file": BOOT_FLOW, "flowchart": BOOT_FLOW, "add_graph": BOOT_ENTRY, "nodes": nodes,
                   "start": "at3", "note": "remake_lose_heart_on_death"})  # (its entry point: BOOT_ENTRY)
    byml = [{"file": EVENT_SETTING, "replace_row": {"row": BOOT_ROW, "copy_of": BOOT_FLOW,
                                                    "set": {"EntryPointName": BOOT_ENTRY}},
             "note": "remake_lose_heart_on_death"}]
    return events, byml, {"retry": retry["name"], "row": BOOT_ROW, "entry": BOOT_ENTRY}


# Enemy regeneration: nearly every enemy's AI runs one tiny shared graph next to its other branches each frame,
# AI/EnemyCommon.common.reactiondamagecolor.module (its damage colour; the Stalfos packs have their own copy, same
# node). It gets a branch of its own beside that node (Root wrapped in a Simultaneous, the drops plugin's way): a
# looping frame counter (SelectorGenericFrameCounter, as Kotake and Koume's battle manager uses it) that every
# REGEN_FRAMES frames heals 1 (OneShotLifeSetOwnLife, SetType 0 adds, never past the maximum: Link's own heal uses it
# so; Floormaster's graph proves it works on an enemy) unless QueryDeathIsDead says it's dying. Each actor whose AI
# runs the graph gets REGEN_HEAP more instance heap (RSDB ActorInfo), as the drops plugin does for its own AI edits.
# Bosses run it too, so they heal as well.
REGEN_GRAPH = "AI/EnemyCommon.common.reactiondamagecolor.module.ainb"
REGEN_STALFOS = "AI/Stalfos.utility.reactiondamagecolor.module.ainb"
REGEN_FRAMES = 150.0
REGEN_HEAP = 16 * 1024
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
REGEN_SOURCES = {  # node name -> the vanilla graph we copy it from
    "SelectorGenericFrameCounter": "AI/Enemy_KotakeKoumeBattleManager.root.ainb",
    "ExecuteGenericDummyAction": "AI/Enemy_KotakeKoumeBattleManager.root.ainb",
    "QueryDeathIsDead": "AI/DungeonBossCommon.action.interruptchancetime.module.ainb",
    "OneShotLifeSetOwnLife": "AI/Floormaster.action.interruptdown.module.ainb",
}


def _regen_sources(romfs):
    """{node name: (copy source {"pack", "file"}, node index)} and the BoolSelector's (the bowling obstacle's)."""
    import ainb
    import packpaths
    import romtools
    fs = _fs(romfs)
    idx = packpaths.index(romfs)
    out = {}
    for name, path in REGEN_SOURCES.items():
        pack = idx[path][0]
        a = ainb.Ainb(romtools.sarc_files(fs.read(pack))[path])
        hits = [i for i, n in enumerate(a.nodes) if n.get("name") == name]
        if not hits:
            raise RuntimeError(f"remake_enemy_regen: {path} has no {name}")
        out[name] = ({"pack": pack, "file": path}, hits[0])
    sel, _ = bowling_nodes(romfs)
    out["BoolSelector"] = ({"pack": BOWLING_PACK, "file": BOWLING_AI}, sel)
    return out


def regen_users(romfs):
    """The actors (pack names) whose AI runs the regenerating graph: enemy packs naming it in a graph of theirs."""
    import packpaths
    import romtools
    fs = _fs(romfs)
    out = set()
    packs = sorted({p for path, ps in packpaths.index(romfs).items() if path.endswith(".ainb") for p in ps
                    if p.rsplit("/", 1)[-1].startswith(("Enemy_", "Dm_Enemy_"))})
    for p in packs:
        if any(b"reactiondamagecolor" in data for n, data in romtools.sarc_files(fs.read(p)).items()
               if n.endswith(".ainb")):
            out.add(p.rsplit("/", 1)[-1].replace(".pack.zs", ""))
    return sorted(out)


def regen_plan(romfs):
    """(ainb ops, byml ops, read-back) for remake_enemy_regen."""
    import packpaths
    import romtools
    src = _regen_sources(romfs)

    def ref(name, label):
        return f"{label}:{src[name][1]}"
    tick, idle, idle2 = ("SelectorGenericFrameCounter", "rgtick"), ("ExecuteGenericDummyAction", "rgidle"), \
        ("ExecuteGenericDummyAction", "rgidle2")
    dead, sel, heal = ("QueryDeathIsDead", "rgdead"), ("BoolSelector", "rgsel"), ("OneShotLifeSetOwnLife", "rgheal")
    edits = [{"wrap": {"command": "Root", "if_needed": True}}]
    for name, label in (tick, idle, idle2, dead, sel, heal):
        edits.append({"copy": {"from": src[name][0], "nodes": [src[name][1]], "label": label, "follow": False}})
    edits += [
        {"set_property": {"node": ref(*tick), "name": "CountFrames", "value": REGEN_FRAMES}},
        {"set_property": {"node": ref(*tick), "name": "IsLoop", "value": True}},
        {"feed": {"from": ref(*dead), "output": "IsDead", "to": ref(*sel), "input": "Input"}},
        {"set_input": {"node": ref(*heal), "name": "SetType", "value": 0}},
        {"set_input": {"node": ref(*heal), "name": "SetValue", "value": 1}},
        {"add_child": {"parent": ref(*tick), "child": ref(*idle), "name": "NotFinish"}},
        {"add_child": {"parent": ref(*tick), "child": ref(*sel), "name": "Finish"}},
        {"add_child": {"parent": ref(*sel), "child": ref(*idle2), "name": "True"}},
        {"add_child": {"parent": ref(*sel), "child": ref(*heal), "name": "False"}},
        {"add_child": {"parent": "@Root", "child": ref(*tick)}},
    ]
    idx = packpaths.index(romfs)
    ainb_ops = [{"pack": list(idx[g]), "file": g, "edits": edits, "note": "remake_enemy_regen"}
                for g in (REGEN_GRAPH, REGEN_STALFOS)]
    fs = _fs(romfs)
    heap = {r.get("__RowId"): r.get("InstanceHeapSize") for r in romtools.byml_load(fs.read(ACTOR_INFO))[0]}
    users = [a for a in regen_users(romfs) if heap.get(a)]
    byml = [{"file": ACTOR_INFO, "set": {f"[__RowId={a}].InstanceHeapSize": int(heap[a]) + REGEN_HEAP for a in users},
             "note": "remake_enemy_regen"}]
    return ainb_ops, byml, {"graphs": [REGEN_GRAPH, REGEN_STALFOS], "heap": {a: int(heap[a]) + REGEN_HEAP
                                                                            for a in users}}


def _fs(romfs):
    import romtools
    return romtools.Romfs(romfs, os.path.join(HERE, "original"))


def _torch_defaults(fs):
    """{blackboard key: default} of the burning-out torch (ExtinguishTime, FireWeakTime)."""
    import romtools
    table = romtools.byml_load(romtools.sarc_files(fs.read(TORCH_PACK))[TORCH_TABLE])[0]
    return {e["BBKey"]: float(e["InitVal"]) for e in table.get("BlackboardParamF32Array") or []
            if e.get("IsInstanceParam")}


def _tour(points):
    """The shortest of the nearest-next routes through every point, one starting from each (metres)."""
    best = math.inf
    for s in range(len(points)):
        left, at, length = set(range(len(points))) - {s}, s, 0.0
        while left:
            nxt = min(left, key=lambda j: math.dist(points[at], points[j]))
            length += math.dist(points[at], points[nxt])
            left.discard(nxt)
            at = nxt
        best = min(best, length)
    return best


def timer_plan(romfs, which):
    """(placement ops, read-back rows [file, hash, key, value]) for remake_shorter_timers `which`."""
    import romtools
    fs = _fs(romfs)
    share = TIMER_SHARE[which]
    defaults = _torch_defaults(fs)
    if not {"ExtinguishTime", "FireWeakTime"} <= set(defaults):
        raise RuntimeError(f"remake_shorter_timers: {TORCH_TABLE} has no ExtinguishTime / FireWeakTime")
    ops, rows = [], []

    def put(rel, h, sets):
        ops.append({"file": rel, "hash": str(h), "set": {f"Dynamic.{k}": v for k, v in sets.items()},
                    "note": "remake_shorter_timers"})
        rows.extend([rel, str(h), k, v] for k, v in sorted(sets.items()))
    for level in DUNGEONS:
        for part in ("Static", "Dynamic"):
            rel = f"Banc/{level}/{level}_{part}.bcett.byml.zs"
            try:
                actors = romtools.byml_load(fs.read(rel))[0].get("Actors") or []
            except (OSError, KeyError):
                continue
            rooms = {}
            for a in actors:
                dyn = a.get("Dynamic") or {}
                if a.get("Gyaml") in SWITCHES:
                    key, floor = SWITCHES[a["Gyaml"]]
                    old = dyn.get(key)
                    if not isinstance(old, (int, float)) or not NO_CLOCK[0] < old < NO_CLOCK[1]:
                        continue
                    new = round(max(old * share, floor), 2)
                    if new < old:
                        put(rel, a["Hash"], {key: new})
                elif a.get("Gyaml") == TORCH:
                    rooms.setdefault(dyn.get("DefaultDungeonRoomIndex"), []).append(a)
            for room, torches in sorted(rooms.items(), key=lambda kv: str(kv[0])):
                if len(torches) < 2:
                    continue
                floor = _tour([[float(v) for v in t["Translate"]] for t in torches]) / WALK + LIGHT
                for t in torches:
                    dyn = t.get("Dynamic") or {}
                    old = float(dyn.get("ExtinguishTime", defaults["ExtinguishTime"]))
                    if not NO_CLOCK[0] < old < NO_CLOCK[1]:
                        continue
                    new = round(max(old * share, floor), 2)
                    if new < old:
                        weak = float(dyn.get("FireWeakTime", defaults["FireWeakTime"]))
                        put(rel, t["Hash"], {"ExtinguishTime": new, "FireWeakTime": round(weak * new / old, 2)})
    if not ops:
        raise RuntimeError("remake_shorter_timers: no timer found in the dungeons' level files")
    return ops, rows


def bowling_nodes(romfs):
    """(selector, do-nothing node) indices in the obstacle's graph: the BoolSelector fed by the hit query, whose True
    branch leads to its death, and the graph's ExecuteGenericDummyAction. Raises when the graph isn't like that."""
    import ainb
    import romtools
    files = romtools.sarc_files(_fs(romfs).read(BOWLING_PACK))
    a = ainb.Ainb(files[BOWLING_AI])
    names = [n.get("name") for n in a.nodes]
    if names.count(HIT_QUERY) != 1 or names.count(DUMMY) != 1 or "OneShotDeathRequestDeath" not in names:
        raise RuntimeError(f"remake_unbreakable_bowling_grass: {BOWLING_AI} isn't the graph it should be")
    query, dummy = names.index(HIT_QUERY), names.index(DUMMY)
    sel = [i for i, n in enumerate(a.nodes) if n.get("type") == 7
           and any(x.get("node") == query for x in (n.get("inputs") or {}).get("bool") or [])]
    if len(sel) != 1:
        raise RuntimeError(f"remake_unbreakable_bowling_grass: {len(sel)} selectors read the hit query")
    true = [p["node"] for p in a.nodes[sel[0]]["plugs"][2] if p["name"] == "True"]
    if len(true) != 1 or true[0] == dummy:
        raise RuntimeError("remake_unbreakable_bowling_grass: the hit selector's True branch isn't the death")
    chem = romtools.byml_load(files[BOWLING_CHEM])[0]
    if not all((chem.get("Object") or [{}])[0].get(k) is True for k in CHEM_DEATHS):
        raise RuntimeError(f"remake_unbreakable_bowling_grass: {BOWLING_CHEM} doesn't die when burned and exploded")
    return sel[0], dummy


def bowling_plan(romfs):
    """(ainb ops, packs ops, read-back) for remake_unbreakable_bowling_grass."""
    sel, dummy = bowling_nodes(romfs)
    ainb_ops = [{"pack": BOWLING_PACK, "file": BOWLING_AI, "note": "remake_unbreakable_bowling_grass",
                 "edits": [{"set_child": {"parent": sel, "which": "True", "child": dummy}}]}]
    packs = [{"pack": BOWLING_PACK, "file": BOWLING_OWN_CHEM, "new_from": BOWLING_CHEM,
              "set": {f"Object.0.{k}": False for k in CHEM_DEATHS}, "note": "remake_unbreakable_bowling_grass"},
             {"pack": BOWLING_PACK, "file": BOWLING_ACTOR, "set": {"Components.ChemicalRef": "?" + BOWLING_OWN_CHEM},
              "note": "remake_unbreakable_bowling_grass"}]
    return ainb_ops, packs, {"selector": sel, "dummy": dummy}


def _pace_files(romfs):
    """{inner path: packs} of the enemies' movement and attack timing files (bosses left out)."""
    import packpaths
    out = {}
    for path, packs in packpaths.index(romfs).items():
        if not path.startswith((MOVEMENT, ATTACK)):
            continue
        name = path.rsplit("/", 1)[1].split(".")[0]
        if not (name.startswith("Enemy_") or name in ("Keese", "Gohma_Larva")) or name.startswith(SAME_PACE):
            continue
        out[path] = list(packs)
    return out


def speed_plan(romfs, pct):
    """(packs ops, read-back rows [pack, file, key, value]) for remake_enemy_speed `pct`."""
    import romtools
    fs = _fs(romfs)
    factor = pct / 100
    ops, rows = [], []
    for path, packs in sorted(_pace_files(romfs).items()):
        doc = romtools.byml_load(romtools.sarc_files(fs.read(packs[0]))[path])[0]
        if path.startswith(MOVEMENT):
            sets = {k: v * factor for k, v in doc.items() if k.endswith("Speed") and "Rotate" not in k
                    and isinstance(v, float) and v > 0}
        else:
            sets = {k: v / factor for k, v in doc.items() if "Interval" in k and isinstance(v, float) and v > 0}
        if not sets:
            continue
        sets = {k: _f32(v) for k, v in sets.items()}
        ops.append({"pack": packs, "file": path, "set": sets, "note": "remake_enemy_speed"})
        rows += [[pk, path, k, v] for pk in packs for k, v in sorted(sets.items())]
    if not ops:
        raise RuntimeError("remake_enemy_speed: no enemy movement or attack timing file found")
    return ops, rows


def _f32(v):
    import struct
    return struct.unpack("<f", struct.pack("<f", v))[0]


def verify(patch, rb, romfs):
    """[problem] reading the shorter timers, the bowling grass and the respawning enemies back from a built patch."""
    import ainb
    import romtools
    fs = romtools.Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    levels = {}
    for rel, h, key, want in rb.get("timers", []):
        if rel not in levels:
            levels[rel] = {str(a.get("Hash")): a for a in romtools.byml_load(fs.read(rel))[0].get("Actors") or []}
        got = (levels[rel].get(h, {}).get("Dynamic") or {}).get(key)
        if got is None or abs(got - want) > 1e-3:
            bad.append(f"{rel} #{h} {key} = {got!r}, planned {want!r}")
    if rb.get("bowling"):
        files = romtools.sarc_files(fs.read(BOWLING_PACK))
        a = ainb.Ainb(files[BOWLING_AI])
        sel, dummy = rb["bowling"]["selector"], rb["bowling"]["dummy"]
        true = [p["node"] for p in a.nodes[sel]["plugs"][2] if p["name"] == "True"]
        if true != [dummy]:
            bad.append(f"{BOWLING_AI}: the hit selector's True branch goes to {true}, planned node {dummy}")
        actor = romtools.byml_load(files[BOWLING_ACTOR])[0]
        if (actor.get("Components") or {}).get("ChemicalRef") != "?" + BOWLING_OWN_CHEM:
            bad.append(f"{BOWLING_ACTOR}: ChemicalRef isn't the obstacle's own chemistry")
        own = files.get(BOWLING_OWN_CHEM)
        obj = (romtools.byml_load(own)[0].get("Object") or [{}])[0] if own else {}
        if not own or any(obj.get(k) is not False for k in CHEM_DEATHS):
            bad.append(f"{BOWLING_OWN_CHEM}: missing, or it still dies when burned or exploded")
    if rb.get("bottles"):
        from evfl import Evfl
        from parity._story_build import newest, flat
        for file, entry, graph in rb["bottles"]:
            rel, _ = newest(romfs, file)
            if not os.path.exists(os.path.join(patch, rel)):
                bad.append(f"{rel}: not in the patch")
                continue
            fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == file)
            ev = {e["name"]: e for e in fc["events"]}
            ep = fc["entry_points"].get(entry)
            if not ep or fc["events"][ep["main"]]["name"] != f"{graph}_boss":
                bad.append(f"{file} {entry}: doesn't start with the battle check")
                continue
            music = ev.get(f"{graph}_music")
            if not music or flat(music.get("params"), {}).get("BgmName") != BATTLE_BGM:
                bad.append(f"{file} {entry}: its battle-music check isn't asking for {BATTLE_BGM}")
            shake = ev.get(f"{graph}_shake")
            if not shake or flat(shake.get("params"), {}).get("ASCommand") != "EvtTalkNo":
                bad.append(f"{file} {entry}: the refusal doesn't shake Link's head")
    if rb.get("regen"):
        import packpaths
        idx = packpaths.index(romfs)
        for g in rb["regen"]["graphs"]:
            for pk in idx.get(g, ()):
                a = ainb.Ainb(romtools.sarc_files(fs.read(pk))[g])
                names = [n.get("name") for n in a.nodes]
                heal = next((n for n in a.nodes if n.get("name") == "OneShotLifeSetOwnLife"), None)
                vals = {x["name"]: x.get("value") for x in ((heal or {}).get("inputs") or {}).get("int") or []}
                tick = next((n for n in a.nodes if n.get("name") == "SelectorGenericFrameCounter"), None)
                frames = {x["name"]: x.get("value") for x in ((tick or {}).get("properties") or {}).get("float") or []}
                if "QueryDeathIsDead" not in names or vals != {"SetType": 0, "SetValue": 1} or \
                        frames.get("CountFrames") != REGEN_FRAMES:
                    bad.append(f"{pk} {g}: no regeneration branch (a heal of 1 every {REGEN_FRAMES:g} frames)")
        rows = {r.get("__RowId"): r for r in romtools.byml_load(fs.read(ACTOR_INFO))[0]}
        for actor, want in rb["regen"]["heap"].items():
            if (rows.get(actor) or {}).get("InstanceHeapSize") != want:
                bad.append(f"{ACTOR_INFO} {actor}: InstanceHeapSize {rows.get(actor, {}).get('InstanceHeapSize')}, "
                           f"planned {want}")
    if rb.get("heart"):
        from evfl import Evfl
        from parity._story_build import newest, flat
        h = rb["heart"]
        rel, _ = newest(romfs, GAME_OVER)
        fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == GAME_OVER)
        ev = {e["name"]: e for e in fc["events"]}
        res = ev.get("Rando_LoseHeartReserve_reserve")
        if not res or flat(res.get("params"), {}).get("Value") != h["row"]:
            bad.append(f"{GAME_OVER}: Try Again doesn't reserve the heart scene {h['row']}")
        elif fc["events"][res["next"]]["name"] != h["retry"]:
            bad.append(f"{GAME_OVER}: the heart scene's reservation doesn't go on to {h['retry']}")
        into = [e["name"] for e in fc["events"]
                if res and res["idx"] in [e.get("next")] + [c.get("next") for c in e.get("cases") or []]]
        if not into:
            bad.append(f"{GAME_OVER}: nothing leads to the heart scene's reservation")
        rows = {r["__RowId"]: r for r in romtools.byml_load(fs.read(EVENT_SETTING), allow_big=True)[0]}
        row = rows.get(h["row"]) or {}
        if row.get("EntryPointName") != h["entry"] or BOOT_FLOW not in (row.get("FlowchartFileName") or ""):
            bad.append(f"{EVENT_SETTING}: {h['row']} isn't {BOOT_FLOW}:{h['entry']}")
        rel, _ = newest(romfs, BOOT_FLOW)
        bfc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == BOOT_FLOW)
        lose = next((e for e in bfc["events"] if e["name"] == f"{h['entry']}_lose"), None)
        if h["entry"] not in bfc["entry_points"] or not lose or flat(lose.get("params"), {}).get("Value") != -HEART:
            bad.append(f"{BOOT_FLOW}: no {h['entry']} taking off a heart")
    if rb.get("dupe_shop"):
        from evfl import Evfl
        from parity._story_build import newest
        d = rb["dupe_shop"]
        rel, _ = newest(romfs, d["file"])
        fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == d["file"])
        kind = next((e for e in fc["events"] if e["name"] == d["event"]), None)
        nxt = kind["cases"][d["case"]]["next"] if kind else None
        if nxt is None or fc["events"][nxt]["name"] != f"{d['graph']}_is0":
            bad.append(f"{d['file']} {d['event']} case {d['case']}: a bottled item isn't checked against your bottles")
    for file, entry, graph in rb.get("dupes", []):
        from evfl import Evfl
        from parity._story_build import newest, flat
        rel, _ = newest(romfs, file)
        if not os.path.exists(os.path.join(patch, rel)):
            bad.append(f"{rel}: not in the patch")
            continue
        fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == file)
        ep = fc["entry_points"].get(entry)
        if not ep or fc["events"][ep["main"]]["name"] != f"{graph}_held":
            bad.append(f"{file} {entry}: doesn't start by asking whether a bottle holds that already")
        held = next((e for e in fc["events"] if e["name"] == f"{graph}_held"), None)
        if held is not None and "BottleItem" not in str(held.get("params")):
            bad.append(f"{file} {entry}: the duplicate check doesn't ask for the caught content")
    for name in rb.get("respawn", []):
        for cell, vals in sorted(_death_cells(fs, name).items()):
            if not vals.get("IsIgnoreThisDeathReason") and any(vals.get(k) is True for k in REMEMBER):
                bad.append(f"{DEATH_DIR}{name}{DEATH_SUFFIX} {cell}: the game still remembers that death")
    return bad  # (enemy speed's rows are pack rows: extras_qol's own read-back checks them)
