"""Pairs OoT Randomizer's Gold Skulltulas, freestanding items, pots, crates and beehives with the remake's placements.

It also turns item assignments for them into patch-plan sections (tokensanity, shuffle_freestanding_items,
shuffle_pots, shuffle_crates, shuffle_beehives, plus the remake's own grass, rocks and other droppers as "extras").

usage: python tools/rando/drops.py [ROMFS]   (writes data/rando/drop_map.json and prints counts per type and mode)

Pairing (data/rando/drop_map.json, "drops": {OoTR location: entry}) works like tools/rando/chest_map.py:
  full     the pair is certain. It's the only object of its kind there, or landmarks tell them apart (NPCs, houses,
           grottos, bean patches, night-only flag, room), or every OoTR location of the set has the same region
           and rule, so which remake object gets which name can't matter for logic.
  group    same number of objects on both sides of a set, but which is which is unknown and the rules differ. The
           generator has to give every member the rule "every member of the group is reachable" (like chest_map's
           groups).
  vanilla  no reliable counterpart (counts differ, the remake moved or dropped it, wrong age, no save flag...).
           It keeps its vanilla item, and "why" says why.
None of this comes from N64 positions, OoTR has none. Pairs come from the remake's level files (positions, rooms,
files per age, Gold Skulltula flags like Nocturnal / IsMagicBeanSoil, nearby NPCs, houses and grottos), checked
against OoTR's names, regions, rules and vanilla items. Every manual decision is in PAIRS / VANILLA_WHY below.

Second pass (data/rando/drops_regions_*.json): the OoTR region of every other
remake drop object, more pairs, and the OoTR locations proven absent. So the modes also include
  absent     no remake counterpart (evidence in "why"), removed from logic (data/rando/logic/drops.json, null)
  blocked    the remake has it but no data edit can change it (evidence in "why")
  elsewhere  another part of the rando patches it (chests, scenes, dungeons)
and "new" lists every unpaired remake object as a NEW OoTR location named "<region> <kind> <n>". Each one has a type
(OoTR's Pot, Crate, SmallCrate, FlyingPot, Beehive, Freestanding, GS Token, or the remake's RemakeGrass, RemakeRock,
RemakeBoulder, RemakeMisc), setting, region, rule (age + breaking the object + whatever the spot itself needs),
confidence, why, vanilla, placements and blockers. build also writes data/rando/logic/drops.json (new_locations +
region rules).
Some spots have copies, one per age or one before and one after a story step. For those, a region file's "pairs"
entry can give a list of hashes for one OoTR location, and its "merge" ([{"hashes": [first, ...], "why"}]) makes
one new location out of several copies, named after the first.

Entry fields are type (OoTR), area (remake), mode, group, why, vanilla (OoTR item), kind, placements, ages,
extra_rule, blockers (see plan_ops), and for freestanding entries allowed_actors (the pickup types this spot can
become). kind is "drop" when the object drops Drop__DropActor and "freestanding" when the pickup's own type (Gyaml)
is swapped. placements have file, hash, actor, age, current drop/table, save flag and reset group. ages are the ages
the remake object exists for, and extra_rule gets ANDed to the OoTR rule when the remake object exists for fewer ages
than the rule allows.
"extras" lists remake-only droppers (grass, rocks, new pots...) with a save flag, keyed "<area>/<category>/<hash>",
and "location" names the new OoTR location each one is now.

API for the generator:
  build(romfs) -> the map (also written to data/rando/drop_map.json)
  remake_drop(ootr_item) -> remake pickup actor name, or None if the item can't be a world pickup
  plan_ops(assignments, allow=()) -> {"placements": [...], "gamedata": {"reset_type": {...}}} for make_patch
                                      (+ "ainb", "packs", "byml" with allow "checked_on_pickup")
  picks_up_checked(entry), saves_on_pickup(actor), pickup_save_ops(droppers, pickups), verify_pickup_save(...):
                                      checked on pickup
  plan_ops(..., scene=names), get_scene_ops(entries), verify_get_scene(patch_dir, entries): placed heart pieces
                                      and heart containers ("get_scene" entries with tag, Name, pack) that give
                                      any item through the shared get scene
  usable(entry, allow=()) -> True if plan_ops accepts a non-vanilla item for this entry
  spot_respawns(entry) -> True if the object comes back after dropping (only REPEATABLE_* items may go there)
  lookup(name, overrides=None) -> the entry of an OoTR location ("drops"), a new location ("new") or an extras key
  vanilla_drop(entry), empty_in_vanilla(entry), can_be_empty(entry): what an object gives by itself (drop_map
                                      "dropper_tables" has each dropper type's default and named tables, and
                                      whether it lists the empty table "None")
  plan_ops(..., empty=, ice=, overrides=, named=, fallthrough=, disguise_names=): OoTR's "Nothing" made empty, the
                                      disguised ice trap (DISGUISE_ACTOR, its pack's tag query falls through to
                                      the drop_map "disguise" tag), and the settings' entry variants (drop_map
                                      "stage_get_scene" / "stage_actors" for a heart the spot's stage places,
                                      "key_spots" for the BotW and Shadow freestanding keys that their room logic
                                      saves)
  drop_map "scene_gifts" (SCENE_GIFTS, checked by _scene_gift_evidence): GC Pot Freestanding PoH and ZD Storms Grotto
                                      Blue Rupee 1-6 as spots a scene of their own gives (kind "scene", and
                                      "scene_gift" has the scene steps, flags, requesters and placements). The
                                      plugin's steps are in tools/rando/parity/_drops_gifts.py
  plan_scene_gifts(plan), verify_scene_gifts(patch_dir, names): read a plan / a built patch back for them
"""
import csv
import json
import math
import os
import re
import sys
from collections import defaultdict
from functools import lru_cache

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
OUT = os.path.join(HERE, "data", "rando", "drop_map.json")
CATALOGUE = os.path.join(HERE, "data", "rando", "drop_objects.csv")
LOGIC = os.path.join(HERE, "reference", "ootr", "logic.json")
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # REMAKE_ROMFS: the app
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"

# OoTR location types handled here. Vanilla world files only, MQ isn't in the remake's level files.
TYPES = ("GS Token", "Freestanding", "Collectable", "RupeeTower", "BossHeart",
         "Pot", "FlyingPot", "Crate", "SmallCrate", "Beehive", "Wonderitem")
# OoTR hint area -> remake area (as tools/match_ootr.py)
AREA = {
    "KOKIRI_FOREST": "KokiriForest", "LOST_WOODS": "LostWood", "SACRED_FOREST_MEADOW": "SacredForestMeadow",
    "HYRULE_FIELD": "HyruleField", "LON_LON_RANCH": "HyruleField", "LAKE_HYLIA": "HyruleField",
    "MARKET": "Market", "TEMPLE_OF_TIME": "Market", "HYRULE_CASTLE": "HyruleCastle",
    "OUTSIDE_GANONS_CASTLE": "GanonCastle", "KAKARIKO_VILLAGE": "KakarikoVillage", "GRAVEYARD": "Graveyard",
    "DEATH_MOUNTAIN_TRAIL": "DeathMountainTrail", "GORON_CITY": "GoronCity", "DEATH_MOUNTAIN_CRATER": "DeathMountainCrater",
    "ZORA_RIVER": "ZoraRiver", "ZORAS_DOMAIN": "ZoraDomain", "ZORAS_FOUNTAIN": "ZoraFountain",
    "GERUDO_VALLEY": "GerudoValley", "GERUDO_FORTRESS": "GerudoFortress", "THIEVES_HIDEOUT": "GerudoFortress",
    "HAUNTED_WASTELAND": "HountedWasteland", "DESERT_COLOSSUS": "DesertColossus",
    "Deku Tree": "InsideTheDekuTree", "Dodongos Cavern": "DodongoCavern", "Jabu Jabus Belly": "InsideJabuJabuBelly",
    "Forest Temple": "ForestTemple", "Fire Temple": "FireTemple", "Water Temple": "WaterTemple",
    "Shadow Temple": "ShadowTemple", "Spirit Temple": "SpiritTemple", "Bottom of the Well": "BottomOfTheWell",
    "Ice Cavern": "IceCavern", "Gerudo Training Ground": "GerudoTrainingGround", "Ganons Castle": "InsideGanonCastle",
}

# Items
# OoTR item -> remake world pickup. That's an actor deriving from Obj_Item_Base with a pickup event, and only those can
# be dropped or lie in the world. The Item_* actors chests show can't.
# The amounts are the remake's. Blue/Red/Purple/Gold rupees are bundles of 5/20/50/200 greens, arrow bundles hold
# 3/5/10, a seed pickup 3, a bombchu pickup 5, and a nut or stick pickup 1. I didn't find the bomb pickup's count in
# its pack.
DROP_ACTOR = {
    "Rupee (1)": "Obj_Rupee_Green", "Rupees (5)": "Obj_Rupee_Blue", "Rupees (20)": "Obj_Rupee_Red",
    "Rupees (50)": "Obj_Rupee_Purple", "Rupees (200)": "Obj_Rupee_Gold",
    "Rupee (Treasure Chest Game) (1)": "Obj_Rupee_Green", "Rupees (Treasure Chest Game) (5)": "Obj_Rupee_Blue",
    "Rupees (Treasure Chest Game) (20)": "Obj_Rupee_Red", "Rupees (Treasure Chest Game) (50)": "Obj_Rupee_Purple",
    "Recovery Heart": "Obj_Heart", "Fairy Drop": "Obj_Fairy",
    "Piece of Heart": "Obj_Heart_Piece", "Piece of Heart (Treasure Chest Game)": "Obj_Heart_Piece",
    "Piece of Heart (Out of Logic)": "Obj_Heart_Piece", "Heart Container": "Obj_Heart_Container",
    "Gold Skulltula Token": "Obj_Token_Gold",
    "Arrows (5)": "Obj_ArrowBundle_Medium", "Arrows (10)": "Obj_ArrowBundle_Large", "Arrows (30)": "Obj_ArrowBundle_Large",
    "Bombs (5)": "Obj_Bomb", "Bombs (10)": "Obj_Bomb", "Bombs (20)": "Obj_Bomb",
    "Bombchus (5)": "Obj_Bombchu", "Bombchus (10)": "Obj_Bombchu", "Bombchus (20)": "Obj_Bombchu", "Bombchus": "Obj_Bombchu",
    "Deku Nuts (5)": "Obj_DekuNut", "Deku Nuts (10)": "Obj_DekuNut", "Deku Stick (1)": "Obj_DekuStick",
    "Deku Seeds (30)": "Obj_DekuSeed",
    "Deku Shield": "Obj_Shield_Deku", "Hylian Shield": "Obj_Shield_Hylian",
    "Goron Tunic": "Obj_Armor_Goron", "Zora Tunic": "Obj_Armor_Zora", "Fire Arrows": "Obj_Arrow_Fire",
    "Rutos Letter": "Obj_Bottle_Letter",
}
# Junk ammo uses OoTR's counts. The vanilla counts come from RSDB/PouchActorInfo.BundleActorNum: Obj_Bomb gives 1 bomb,
# Obj_DekuNut 1 nut, Obj_ArrowBundle_Large 10 arrows and Obj_DekuSeed 3 seeds.
# So we copy the pickup and give it a pouch bundle with the right count, and ammo_type_ops adds the RSDB rows. Packs
# load by actor name, so the new types don't need registering per level.
# We use copies even for Arrow (5) and Arrow (10) so the container check only sees our own types.
# Obj_DekuStick already gives the right amount, one stick, so it doesn't need a copy.
#
# Each row names the pickup to copy, the item it adds and the count.
AMMO_TYPES = {
    "RandoAmmo_Arrows5": ("Obj_ArrowBundle_Medium", "Item_Arrow_Normal", 5),
    "RandoAmmo_Arrows10": ("Obj_ArrowBundle_Large", "Item_Arrow_Normal", 10),
    "RandoAmmo_Arrows30": ("Obj_ArrowBundle_Large", "Item_Arrow_Normal", 30),
    "RandoAmmo_Bombs5": ("Obj_Bomb", "Item_Bomb", 5),
    "RandoAmmo_Bombs10": ("Obj_Bomb", "Item_Bomb", 10),
    "RandoAmmo_Bombs20": ("Obj_Bomb", "Item_Bomb", 20),
    "RandoAmmo_Nuts5": ("Obj_DekuNut", "Item_DekuNut", 5),
    "RandoAmmo_Nuts10": ("Obj_DekuNut", "Item_DekuNut", 10),
    "RandoAmmo_Seeds30": ("Obj_DekuSeed", "Item_DekuSeed", 30),
}
DROP_ACTOR.update({"Arrows (5)": "RandoAmmo_Arrows5", "Arrows (10)": "RandoAmmo_Arrows10",
                   "Arrows (30)": "RandoAmmo_Arrows30", "Bombs (5)": "RandoAmmo_Bombs5",
                   "Bombs (10)": "RandoAmmo_Bombs10", "Bombs (20)": "RandoAmmo_Bombs20",
                   "Deku Nuts (5)": "RandoAmmo_Nuts5", "Deku Nuts (10)": "RandoAmmo_Nuts10",
                   "Deku Seeds (30)": "RandoAmmo_Seeds30"})
# Dungeon small keys. We assume Obj_Dungeon_SmallKey (pouch KeyItemSmallKey) counts for the dungeon it's picked up in,
# so a key can only go to a location inside its own dungeon.
# TODO: verify that assumption.
KEY_AREA = {
    "Small Key (Forest Temple)": "ForestTemple", "Small Key (Fire Temple)": "FireTemple",
    "Small Key (Water Temple)": "WaterTemple", "Small Key (Shadow Temple)": "ShadowTemple",
    "Small Key (Spirit Temple)": "SpiritTemple", "Small Key (Bottom of the Well)": "BottomOfTheWell",
    "Small Key (Gerudo Training Ground)": "GerudoTrainingGround", "Small Key (Ganons Castle)": "InsideGanonCastle",
}
# How sure we are that the actor works as a drop. "vanilla" means some vanilla placement already drops it
# (Drop__DropActor or a drop table). Everything else is a world pickup nobody's seen dropped (untested).
VANILLA_DROPS = {"Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Rupee_Purple", "Obj_Heart",
                 "Obj_MagicJar_Small", "Obj_Fairy", "Obj_DekuSeed", "Obj_DekuStick", "Obj_Bomb",
                 "Obj_ArrowBundle_Small", "Obj_Heart_Piece", "Obj_Token_Gold", "Obj_Dungeon_SmallKey_GerudoFortress_01"}


# Ice traps from drops. A drop can be a non-pickup actor (in vanilla 45 objects drop
# Animal_Insect), so a pot, crate, rock, grass tuft or Gold Skulltula can release an enemy instead of a pickup.
# The only enemy that freezes Link is the Ice Keese (Keese AttackParam, ice element like the remake's ice-trap chest),
# and it's only placed in Ice Cavern. Other levels get the keese they already place (fire burns, plain bites).
# Anywhere else, and for freestanding pickups (that's a type swap, and no pickup runs a scene), nothing in the files
# can freeze or hurt Link, so the ice trap is a green-rupee stand-in. I read the Keese types per level from every Banc
# file.
ICE_TRAP_ENEMY = {"IceCavern": "Enemy_Keese_Ice"}
ICE_TRAP_ENEMY.update({a: "Enemy_Keese_Fire" for a in ("BottomOfTheWell", "DodongoCavern", "FireTemple",
                                                       "GerudoTrainingGround", "InsideGanonCastle", "ShadowTemple",
                                                       "SpiritTemple")})
ICE_TRAP_ENEMY.update({a: "Enemy_Keese" for a in ("Graveyard", "WaterTemple")})
ICE_TRAP_STAND_IN = ("Obj_Rupee_Green", "Obj_Heart", "Obj_Rupee_Blue")
NO_STAND_IN = set()  # stand-ins this seed can't use (parity/drops.py's no_collectible_hearts takes out Obj_Heart)


def own_pickups(entry):
    """The pickups a drop-map spot gives in the vanilla game. That's its placed pickups, its fixed drops and its vanilla
    item's pickup (an underwater heart counts as a heart)."""
    own = set()
    for p in entry.get("placements", []):
        if entry.get("kind") == "freestanding":
            own.add(p.get("actor"))
        elif p.get("drop"):
            own.add(p["drop"])
    if entry.get("vanilla"):
        own.add(remake_drop(entry["vanilla"]))
    if own & {"Obj_Heart", "Obj_Heart_InWater"}:
        own |= {"Obj_Heart", "Obj_Heart_InWater"}
    own.discard(None)
    return own


def ice_trap_drop(entry):
    """(actor, how) for an ice trap at drop-map entry `entry`. That's an enemy its level places ("freeze", "hurt") or a
    stand-in pickup ("stand-in"), and (None, reason) if nothing fits. A stand-in is never the spot's own pickup, since a
    green rupee standing in for an ice trap on a green-rupee spot plays exactly like the vanilla game."""
    area = entry.get("area")
    if entry.get("kind") == "drop" and area in ICE_TRAP_ENEMY:
        a = ICE_TRAP_ENEMY[area]
        return a, "freeze" if a == "Enemy_Keese_Ice" else "hurt"
    own = own_pickups(entry) | NO_STAND_IN
    if entry.get("kind") == "freestanding":
        fits = [a for a in ICE_TRAP_STAND_IN if a in entry.get("allowed_actors", []) and a not in own]
        return (fits[0], "stand-in") if fits else (None, "no stand-in pickup in this level other than the spot's own")
    fits = [a for a in ICE_TRAP_STAND_IN if a not in own]
    return (fits[0], "stand-in") if fits else (None, "every stand-in pickup is the spot's own")


# Empty objects and disguised ice traps
# When its placement names nothing, an object gives the first table of its DropParam's DropTableResourceList that has
# an empty or missing DropTableName:
# - pots, grass, small rocks, crates: DropTable_ResourceSupply_00, a random heart/magic/ammo by category
# - bomb boulders: DropTable_ResourceSupply_BrokenRock_01
# - cow-skull and sign decorations: their own table
# - flying pots: DropTable_Enemy_Rupee_02, a green rupee every time
# - bug grass and bug rocks: DropTable_Bug_00, bugs
# build() puts this into drop_map "dropper_tables" as {type: {"default": fixed pickup actor or None (random or bugs),
# "empty": the type lists DropTable_None}}.
EMPTY_TABLE = "None"  # DropTable_None ("Items": []), the name vanilla uses for "drops nothing" (42 placements)
# The disguise is one pickup type where every unnamed instance is an ice trap. Obj_GerudoValley_Heart_Piece is a heart
# piece (same model, same get scene Dm_SY_Get, its own copy of the PouchContentUtuwa event AI). It's only placed at the
# Gerudo Valley waterfall (GV Waterfall Freestanding PoH, both GerudoValley stages) and nothing else creates it (no drop
# table, Drop__DropActor, ActorHolder or event flow names it).
# An object can drop it through Drop__DropActor, the same way chests drop types their level never places (Item_Hookshot
# in Kokiri Forest), and it shows a Piece of Heart. Taking it plays the get scene. This pack answers the scene's tag
# query with the DISGUISE tag for any instance without a RandoGetScene name, and the get-scene hook's branch for that
# tag hides it, freezes Link (the chests plugin's shared freeze) and requests its death. The waterfall placement itself
# always gets a name (its own tag, or the vanilla answer 4).
DISGUISE_ACTOR = "Obj_GerudoValley_Heart_Piece"
DISGUISE_PACK = "Pack/Actor/Obj_GerudoValley_Heart_Piece.pack.zs"
GET_SCENE_VANILLA_ANSWER = 4  # the tag query's "anything else" answer (Dm_SY_Get Event115 case 4, CheckHeart)
# Freestanding small keys that their room logic saves. The key is an
# AlwaysRespawn Obj_Dungeon_SmallKey with no Bool64bitKey of its own, but its room's logic module references it
# (ActorLogicSimpleActor). The key's Dead output sets a named Bool, and that Bool deletes the key (BotW) or stops
# creating it (Shadow). So a key taken through the get scene is saved by that Bool, since the hook requests its death
# (DeathReason 10) like the vanilla scene does.
# Obj_Dungeon_SmallKey's pack has its own copy of the event AI (PouchContent_EnableWarp.event.root.ainb), and its
# EventQueryCheckTagOnPouchActor starts at a BoolSelector like the hearts' does. Small keys play Dm_SY_Get (GetType
# Large, and GetDisplayProcess shows the small-key counter).
KEY_PACK = "Pack/Actor/Obj_Dungeon_SmallKey.pack.zs"
KEY_AI = "AI/PouchContent_EnableWarp.event.root.ainb"
KEY_SPOTS = {
    "Bottom of the Well Freestanding Key": {
        "hash": "17649154319341333603", "area": "BottomOfTheWell",
        "logic": "Logic/BottomOfTheWell_Level_Room_03Prefab_25d7.logic.module.ainb",
        "instance": "Obj_Dungeon_SmallKey_db9c", "flag": "BottomOfTheWell_Level_Room_03_Get_SmallKey"},
    "Shadow Temple Freestanding Key": {
        "hash": "12562389953863361839", "area": "ShadowTemple",
        "logic": "Logic/ShadowTemple_Level_Room_B3FB4F_F_Prefab_6cf3.logic.module.ainb",
        "instance": "KeySmall_e812", "flag": "ShadowTemple_Level_Room_13_GetKey"},
}


# Bugs. OoTR's 'Bugs' come from its Drop locations "Bug Shrub", "Bug Rock"
# and "Wandering Bugs" (21 regions). In the remake a bottle catches Animal_Insect (PouchContentParam InBottleBug). The
# Animal_Kokiri_Insect_* actors are just decoration, with no pouch content and no physics.
# Animal_Insect comes from:
# - the bug grass and bug rocks (Obj_Plant_Grass_A_03 / Obj_LiftRock_A_03 with default table DropTable_Bug_00, and
#   grass with Drop__DropActor Animal_Insect). They're all drop-map locations (remake_shuffle_grass / _rocks).
# - BUG_SOURCES, which no setting shuffles
# - the 30 % bug chance of foliage grass (FoliageDropParam DropTable_Foliage_00). That one has no placement and can't
#   be tied to a region, so we never count it (the logic is stricter than the game there).
# The potion shop's Animal_Insect is the bug from its bottle tutorial (Name Item_Bottle_TutorialEvent, run by the
# Market logic module), and that's not counted either. build() writes drop_map "bugs".
# The Hyrule Field bushes (Land_kokiri_Plant_A_02_DropFixed_03, Drop__DropActor Animal_Insect, no save flag) were the
# one permanent source until they became locations (remake_shuffle_bushes). As bug objects, each one counts while it
# isn't shuffled.
BUG_SOURCES = []
BUG_TYPE = "Animal_Insect"


def _stage(rel):
    """A placement file's stage, which is its Banc scene, e.g. Banc/ZoraFountain/ZoraFountain_Adult. GameBancParam
    Banc.Main names one scene per stage, stored as the _Static and _Dynamic halves that load together."""
    return re.sub(r"_(Static|Dynamic)\.bcett\.byml\.zs$", "", rel)


def vanilla_drop(entry, m=None):
    """The one pickup a drop spot's objects give in vanilla when it's fixed, else None (random table, bugs, nothing).
    Fixed means a Drop__DropActor, or a table that drops one actor every time, named on the placement or the type's
    default."""
    tables = (m or _map()).get("dropper_tables", {})
    out = set()
    for p in entry.get("placements", []):
        if p.get("category") == "gold_skulltula":
            return "Obj_Token_Gold"
        if p.get("drop"):
            out.add(p["drop"])
        elif p.get("drop_table") == EMPTY_TABLE:
            out.add(None)
        elif p.get("drop_table"):
            out.add(tables.get(p["actor"], {}).get("named", {}).get(p["drop_table"]))
        else:
            out.add(tables.get(p["actor"], {}).get("default"))
    return out.pop() if len(out) == 1 else None


def empty_in_vanilla(entry):
    """True if every object of the spot drops nothing in vanilla (its placement names the empty table)."""
    rows = entry.get("placements", [])
    return bool(rows) and all(p.get("drop_table") == EMPTY_TABLE and not p.get("drop") for p in rows)


def can_be_empty(entry, m=None):
    """True if every object of the drop spot can be made to drop nothing (its type lists the empty table)."""
    tables = (m or _map()).get("dropper_tables", {})
    rows = entry.get("placements", [])
    return entry.get("kind") == "drop" and bool(rows) and all(tables.get(p["actor"], {}).get("empty") for p in rows)


def remake_drop(ootr_item):
    """The remake world pickup for an OoTR item, or None if it has no pickup form (Hookshot, songs, medallions,
    progressive items, bottles, maps, compasses, boss keys, Ice Trap, Thieves' Hideout keys...). Ruto's Letter and Fire
    Arrows are ordinary pickups, and LAKE_GUARD keeps the Lake Hylia hook to the lake's two placements."""
    if ootr_item in DROP_ACTOR:
        return DROP_ACTOR[ootr_item]
    if ootr_item in KEY_AREA:
        return "Obj_Dungeon_SmallKey"
    return None


# Manual pairing table
# Rows are (area, [OoTR names], [objects], why). An object is a placement hash, and its other-age copy at the same spot
# gets added automatically, or a list of hashes for exactly those copies. Names and objects pair in order. Extra names
# stay vanilla and extra objects become extras.
# The mode is full for one name, or for names that all have the same region and rule. Otherwise it's group.
def _n(prefix, a, b):
    return [f"{prefix}{i}" for i in range(a, b + 1)]


PAIRS = [
    # ---- Gold Skulltulas. The counts match in every area (100 OoTR, 100 remake). We tell them apart by the bean-patch
    # flag (Enemy_Skulltula_Gold_IsMagicBeanSoil), the night flag (Nocturnal), child/adult file, crate links and
    # landmarks.
    ("KokiriForest", ["KF GS Know It All House"], ["17067594426901953848"], "child, night, on the house of the three Know-It-All brothers"),
    ("KokiriForest", ["KF GS Bean Patch"], ["9623998892552467148"], "the bean-patch skulltula (IsMagicBeanSoil)"),
    ("KokiriForest", ["KF GS House of Twins"], ["7116603238806634901"], "adult, night, on the House of Twins (the house with the two pots)"),
    ("LostWood", ["LW GS Bean Patch Near Bridge"], ["9333354743976439033"], "bean patch LostWood02, far from the theater"),
    ("LostWood", ["LW GS Bean Patch Near Theater"], ["17796658857969527112"], "bean patch LostWood01, 5 units from the skulltula above the theater"),
    ("LostWood", ["LW GS Above Theater"], ["4335656213162247230"], "the non-bean skulltula next to the theater bean patch"),
    ("SacredForestMeadow", ["SFM GS"], ["14473218207379268379"], "only one"),
    ("HyruleField", ["LH GS Bean Patch"], ["7014193622407727514"], "bean patch flag Gimmick_MagicBeanSoil_LakeHylia"),
    ("HyruleField", ["LH GS Lab Wall"], ["13944703896577680014"], "child, night, on the lake laboratory (scientist 7 units away)"),
    ("HyruleField", ["LH GS Lab Crate"], ["7388645484070660331"], "adult, inside the lab tank, linked to the crate at the same spot"),
    ("HyruleField", ["LH GS Tree"], ["789492162651991711"], "the only adult night skulltula at the lake"),
    ("HyruleField", ["LLR GS Tree"], ["341792603838029977"], "the tree-style (pop-out) skulltula inside Lon Lon Ranch"),
    # The other six HF / ranch / lake skulltulas, told apart by their Links and grotto rooms (second pass).
    # The two night skulltulas linked to LocationArea_LonLonRanch are two of OoTR's three ranch-building ones. OoTR's
    # boomerang rule (House Window, Back Wall) is the stricter pair, so Rain Shed is the absent one. The child-only one
    # sits on the ranch house (its props within a metre), so it's the House Window; the other is by the ranch tower.
    # The grotto under the HrlField bomb cover at (-156,139,338) has a Gold Skulltula next to a big Skulltula, so that's
    # OoTR's Near Kak Grotto. The cow grotto (cow, 2 pots, webs) has no Gold Skulltula (absent).
    # The non-night lake-shore one (map icon by the crawl hole at -289,131,591) is OoTR's LH Small Island one. OoTR's
    # child + night rule is stricter than the remake's.
    # The HF tree pop-out (70,167,264) and the generic-grotto crate one are new.
    ("HyruleField", ["LLR GS House Window"], ["15889002414176907668"],
     "child night skulltula linked to LocationArea_LonLonRanch, on the ranch house (its Land_LonLon props 1 unit away)"),
    ("HyruleField", ["LLR GS Back Wall"], ["2730878115209290675"],
     "night skulltula linked to LocationArea_LonLonRanch, by the ranch tower (Land_LonLon_Ruins 9 units away)"),
    ("HyruleField", ["HF GS Near Kak Grotto"], ["12007978132755687032"],
     "inside the grotto at (-156,139,338) with a big Skulltula 5 units away (OoT's Near Kak grotto layout)"),
    ("HyruleField", ["LH GS Small Island"], ["8655370827943125875"],
     "the lake-shore skulltula linked to a map icon at (-289,131,591), inside the LakeHylia LocationArea"),
    # The remake moved ZR GS Tree into Zora's River's second bean patch (IsMagicBeanSoil, child). It comes out of
    # planted bugs, so its rule becomes OoTR's bean-patch skulltula rule (RULE_MOVES).
    ("ZoraRiver", ["ZR GS Tree"], ["12370559827741970774"],
     "the second bean-patch skulltula on the river bank past the entrance boulders (child file)"),
    ("GerudoValley", ["GV Waterfall Freestanding PoH"], ["16129198288828948135"],
     "Obj_GerudoValley_Heart_Piece, the valley's only placed heart piece (the crate-ledge one became a chest)"),
    ("Market", ["Market GS Guard House"], ["8942465719711548237"], "only one (in the guard-house crate)"),
    ("HyruleCastle", ["HC GS Tree"], ["2504273934093629549"], "the tree-style (pop-out) one; the other is linked into the storms grotto"),
    ("HyruleCastle", ["HC GS Storms Grotto"], ["9162653017526462607"], "the grotto one"),
    ("GanonCastle", ["OGC GS"], ["5626064870824758772"], "only one"),
    ("KakarikoVillage", ["Kak GS Tree"], ["7677963516305772491"], "the tree-style (pop-out) child skulltula"),
    ("KakarikoVillage", ["Kak GS Watchtower"], ["15118290503807073158"], "on the watchtower (Land_Kakariko_Tower_A_01 about 10 units below)"),
    ("KakarikoVillage", ["Kak GS Above Impas House"], ["3310819903461047792"], "the only adult one"),
    ("KakarikoVillage", ["Kak GS Near Gate Guard", "Kak GS Skulltula House", "Kak GS House Under Construction"],
     ["11629189455828560791", "15314554401574296838", "14107117960174262321"], "the other three child night skulltulas"),
    ("Graveyard", ["Graveyard GS Bean Patch"], ["16798263777516949500"], "bean patch"),
    ("Graveyard", ["Graveyard GS Wall"], ["229475726653285413"], "the night one"),
    ("DeathMountainTrail", ["DMT GS Bean Patch"], ["17425319789138387506"], "bean patch"),
    ("DeathMountainTrail", ["DMT GS Near Kak"], ["351345377871782696"], "the one present for both ages"),
    ("DeathMountainTrail", ["DMT GS Above Dodongos Cavern"], ["17669199296215821346"], "adult, lower of the two adult ones"),
    ("DeathMountainTrail", ["DMT GS Falling Rocks Path"], ["832677387023638406"], "adult, high on the summit path"),
    ("DeathMountainCrater", ["DMC GS Crate"], ["18219295034534354574"], "child, in the crate at the same spot"),
    ("DeathMountainCrater", ["DMC GS Bean Patch"], ["6397182598322965076"], "bean patch"),
    ("GoronCity", ["GC GS Center Platform"], ["18139423190738716302"], "the adult one"),
    ("GoronCity", ["GC GS Boulder Maze"], ["569390966671955163"], "the child one (boulder maze, next to its chest)"),
    ("GerudoValley", ["GV GS Bean Patch"], ["8326970197618554626"], "bean patch"),
    ("GerudoValley", ["GV GS Small Bridge"], ["15265071047503310220"], "the child night one"),
    ("GerudoValley", ["GV GS Behind Tent", "GV GS Pillar"], ["13584527502619061465", "11535915511003753934"], "the two adult night ones"),
    ("GerudoFortress", ["GF GS Archery Range"], ["13037049463363052038"], "inside the horseback-archery fence line"),
    ("GerudoFortress", ["GF GS Top Floor"], ["9362225887419425752"], "the one on the fortress"),
    ("HountedWasteland", ["Wasteland GS"], ["14910672274965350769"], "only one"),
    ("DesertColossus", ["Colossus GS Bean Patch"], ["234735562946824289"], "bean patch"),
    # The two night ones (audit_overworld, guides + files). The one on the bean platform's route (Obj_SmallFarm_A_03
    # links an area by it) is OoT's GS Hill, and the one on the wall by the Spirit Temple is GS Tree (Longshot).
    ("DesertColossus", ["Colossus GS Hill"], ["11160993739666517210"],
     "night skulltula at (-73.9,105.3,-5.7) on the Colossus bean platform's route"),
    ("DesertColossus", ["Colossus GS Tree"], ["15057756765324812936"],
     "night skulltula at (-170.1,101.8,-47.9) on the wall by the Spirit Temple (the audit's rule: Longshot)"),
    ("ZoraRiver", ["ZR GS Ladder"], ["8695975724114049706"], "the child night one"),
    # The two adult night ones: one is 20 units from the raised grotto hole (-16,115,15), the other 24 units from the
    # bridge by the waterfall up to the domain (Land_ZoraRiver_Bridge_A_03) and 29 from the bean platform's end
    # (audit_overworld: bean + Hookshot).
    ("ZoraRiver", ["ZR GS Near Raised Grottos"], ["10917372215719266172"],
     "adult night skulltula 20 units from the raised grotto hole at (-16,115,15)"),
    ("ZoraRiver", ["ZR GS Above Bridge"], ["9450239379321634455"],
     "adult night skulltula 24 units from the bridge by the domain waterfall (Land_ZoraRiver_Bridge_A_03)"),
    ("ZoraDomain", ["ZD GS Frozen Waterfall"], ["9600417828645642589"], "only one"),
    ("ZoraFountain", ["ZF GS Tree"], ["17355397719442343054"], "the tree-style (pop-out) child one"),
    ("ZoraFountain", ["ZF GS Above the Log"], ["7152962033963346563"], "the child-file night one"),
    ("ZoraFountain", ["ZF GS Hidden Cave"], ["9537398183107003742"], "the remaining one (night, both files)"),
    ("InsideTheDekuTree", ["Deku Tree GS Compass Room"], ["13609975487234437568"], "room 3, upper floor (y 121)"),
    ("InsideTheDekuTree", ["Deku Tree GS Basement Back Room"], ["17501688996789643983"], "room 11, the far back room"),
    ("InsideTheDekuTree", ["Deku Tree GS Basement Vines", "Deku Tree GS Basement Gate"], ["16101480770659370603", "18075358844331090388"], "the two in basement room 4"),
    # Dungeon Gold Skulltulas, true pairs from the dungeon audit.
    # Rooms, doors, cracked walls and scarecrow spots tell each one apart.
    ("DodongoCavern", ["Dodongos Cavern GS Vines Above Stairs"], ["8470399761714006011"],
     "room 10, on the web above the bomb-flower staircase top beside Skullwalltula #56429"),
    ("DodongoCavern", ["Dodongos Cavern GS Alcove Above Stairs"], ["4565265801822094851"],
     "room 18, the alcove behind WallCrack #34774 (the audit's can_blast_or_smash)"),
    ("DodongoCavern", ["Dodongos Cavern GS Scarecrow"], ["960362013021648957"],
     "room 2, 5.7 from Pierre's spot #91798 / scarecrow marker #35478"),
    ("DodongoCavern", ["Dodongos Cavern GS Side Room Near Lower Lizalfos"], ["1171854281537584829"],
     "room 3, the side room behind WallCrack #26398 that a Baby Dodongo opens"),
    ("DodongoCavern", ["Dodongos Cavern GS Back Room"], ["13690401647626643497"],
     "room 20, behind the skull's cracked wall #79731, with Armos and Baby Dodongos"),
    ("InsideJabuJabuBelly", ["Jabu Jabus Belly GS Lobby Basement Lower"], ["13852835165271311030"],
     "room 3, the lower of the two (y 88.4)"),
    ("InsideJabuJabuBelly", ["Jabu Jabus Belly GS Lobby Basement Upper"], ["11283202900158580106"],
     "room 3, the upper of the two (y 90.3)"),
    ("InsideJabuJabuBelly", ["Jabu Jabus Belly GS Water Switch Room"], ["11513774157335944149"], "room 14, beside the three switch-room pots (OoTR names that room 14 too)"),
    ("InsideJabuJabuBelly", ["Jabu Jabus Belly GS Near Boss"], ["15983944335296207002"], "the remaining one (room 5)"),
    ("ForestTemple", ["Forest Temple GS First Room"], ["11081821111317815057"], "room 0"),
    ("ForestTemple", ["Forest Temple GS Lobby"], ["17612196129225973969"], "room 2, the central room with the six pots"),
    ("ForestTemple", ["Forest Temple GS Raised Island Courtyard"], ["2014780391754316762"],
     "room 14, the east courtyard with the Map Chest and Pierre's marker #25544 (audit_dungeons: Scarecrow)"),
    ("ForestTemple", ["Forest Temple GS Level Island Courtyard"], ["10970805784153267902"],
     "room 12, the west courtyard with the waterfalls and the step switch"),
    ("ForestTemple", ["Forest Temple GS Basement"], ["3072474196008424241"], "room 27, the remaining one"),
    ("FireTemple", ["Fire Temple GS Song of Time Room"], ["6789992996625105554"],
     "room 19, through door #42688 on top of the Song of Time steps in the big lava room"),
    ("FireTemple", ["Fire Temple GS Boss Key Loop"], ["14706322686481615109"],
     "room 18, the loop behind door #17955 and its hammer pillars (iron rock #94248)"),
    ("FireTemple", ["Fire Temple GS Boulder Maze"], ["12751796212121957464"],
     "room 5, 1.8 behind the boulder-maze cracked wall #92338 among the rolling rocks"),
    ("FireTemple", ["Fire Temple GS Scarecrow Climb"], ["5556173334779815044"],
     "room 7, the shaft above Pierre's spot #51816 (rising floor #55323)"),
    ("FireTemple", ["Fire Temple GS Scarecrow Top"], ["9172014785497046138"],
     "room 8, the top ledge with the three scarecrow chests"),
    ("WaterTemple", ["Water Temple GS Central Pillar"], ["11571778270592589517"],
     "room 1, top of the central pillar by hookshot target #04106"),
    ("WaterTemple", ["Water Temple GS River"], ["15506432733081566465"], "room 21, the river room"),
    ("WaterTemple", ["Water Temple GS Near Boss Key Chest"], ["186694424287048567"],
     "room 24, the boulder stream (rolling rock #93894) past room 14's block puzzle"),
    ("WaterTemple", ["Water Temple GS Behind Gate"], ["16157272130665282352"],
     "room 2, the pillar basement behind gate #52825/#71729 opened by crystal switch #12952"),
    ("WaterTemple", ["Water Temple GS Falling Platform Room"], ["4399424945134189769"],
     "room 25, behind room 17's cracked wall #56465 beside the Map chest (the remake has no GS in room 5; "
     "rule moved to Water Temple Dive, RULE_MOVES)"),
    ("ShadowTemple", ["Shadow Temple GS Invisible Blades Room"], ["16933078188088206331"],
     "room 31, with a visible and an invisible chest on one spot (OoT's invisible blades room)"),
    ("ShadowTemple", ["Shadow Temple GS Falling Spikes Room"], ["15148554628675590606"],
     "room 11, under the falling ceilings (Obj_ShadowTemple_FallingCeiling_A_01) with the push block (audit_dungeons)"),
    ("ShadowTemple", ["Shadow Temple GS Single Giant Pot"], ["15564367841356014861"], "room 14, the remaining one"),
    ("ShadowTemple", ["Shadow Temple GS Near Ship"], ["8823884712433934372"], "room 17, with the boat"),
    ("ShadowTemple", ["Shadow Temple GS Triple Giant Pot"], ["10270336409167849808"], "room 20, with the three skull pots"),
    ("SpiritTemple", ["Spirit Temple GS Lobby"], ["5086449036385341804"],
     "room 7, on the ledge beside Pierre's spot #73433 (the audit's Scarecrow rule)"),
    ("SpiritTemple", ["Spirit Temple GS Hall After Sun Block Room"], ["10127391959410674946"],
     "room 10, the hall behind the sun-block silver-rupee shutter #70549 (the audit's silver-rupee rule)"),
    ("SpiritTemple", ["Spirit Temple GS Metal Fence", "Spirit Temple GS Sun on Floor Room", "Spirit Temple GS Boulder Room"],
     ["10530233152473742636", "12959656942046734931", "8120267919866495114"], "the other three of 5"),
    ("BottomOfTheWell", ["Bottom of the Well GS West Inner Room", "Bottom of the Well GS East Inner Room", "Bottom of the Well GS Like Like Cage"],
     ["3889761319471426870", "7460556442932201772", "12165938013608963606"], "3 and 3, same region and rule"),
    ("IceCavern", ["Ice Cavern GS Spinning Scythe Room"], ["7165255787572043804"], "room 3, with the spinning blade"),
    ("IceCavern", ["Ice Cavern GS Heart Piece Room"], ["1612219105489330028"],
     "room 6, with the Compass Chest and the heart piece in red ice"),
    ("IceCavern", ["Ice Cavern GS Push Block Room"], ["14822647495538506998"],
     "room 8, with the push block and five silver rupees"),

    # ---- Pieces of Heart, Heart Containers
    ("KakarikoVillage", ["Kak Impas House Freestanding PoH"], ["17926402522258180222"], "by the cow behind Impa's house (cow 5 units away)"),
    ("KakarikoVillage", ["Kak Windmill Freestanding PoH"], ["13389209437182306002"], "inside the windmill (windmill house 7 units away)"),
    ("Graveyard", ["Graveyard Freestanding PoH"], ["2157466067026784951"], "the only one, by the bean patch (the remake has no crate around it)"),
    ("DeathMountainTrail", ["DMT Freestanding PoH"], ["715147239509454487"], "only one"),
    ("DeathMountainCrater", ["DMC Wall Freestanding PoH", "DMC Volcano Freestanding PoH"], ["744856631664786545", "10331043360028932045"],
     "two in the crater; the higher one (y 127) is likely the wall one, not sure"),
    ("DesertColossus", ["Colossus Freestanding PoH"], ["10592092054086534681"], "only one"),
    ("HyruleField", ["LLR Freestanding PoH"], ["9814903750835309225"], "child, by the movable boxes at the ranch ruins (tower)"),
    ("HyruleField", ["LH Freestanding PoH"], ["13469300937852836203"], "adult, high above the lake laboratory (y 163)"),
    ("ZoraRiver", ["ZR Near Domain Freestanding PoH"], ["4189391771527808272"], "the upstream one, near the Zora's Domain entrance"),
    ("ZoraRiver", ["ZR Near Open Grotto Freestanding PoH"], ["11455676800795329345"], "the downstream one"),
    ("ZoraFountain", ["ZF Bottom Freestanding PoH"], ["8030885465575590602"], "on the fountain floor (y 71)"),
    ("ZoraFountain", ["ZF Iceberg Freestanding PoH"], ["12406896586250888098"], "the higher one (y 103; the other is on the floor at y 71)"),
    ("InsideTheDekuTree", ["Deku Tree Queen Gohma Heart"], ["17948245526767051747"], "only heart container"),
    ("DodongoCavern", ["Dodongos Cavern King Dodongo Heart"], ["5936534468710061389"], "only heart container"),
    ("InsideJabuJabuBelly", ["Jabu Jabus Belly Barinade Heart"], ["17608884438514432711"], "only heart container"),
    ("ForestTemple", ["Forest Temple Phantom Ganon Heart"], ["18379569660496940670"], "only heart container"),
    ("FireTemple", ["Fire Temple Volvagia Heart"], ["9478330070473364248"], "only heart container"),
    ("WaterTemple", ["Water Temple Morpha Heart"], ["14426685265732353862"], "only heart container"),
    ("ShadowTemple", ["Shadow Temple Bongo Bongo Heart"], ["17599164808183510748"], "only heart container"),
    ("SpiritTemple", ["Spirit Temple Twinrova Heart"], ["4720088048159616469"], "only heart container"),

    # ---- freestanding rupees and hearts
    ("KokiriForest", _n("KF Sarias House Recovery Heart ", 1, 4),
     ["3211747475593407179", "9333984718219537434", "8217415107461137996", "13766700305743331316"], "the four hearts on the floor of Saria's house"),
    ("KokiriForest", _n("KF Top of Sarias Recovery Heart ", 1, 3),
     ["12744945159394614918", "1135865174486388723", "9778104484775444655"], "the three hearts on Saria's roof (y 117.6)"),
    ("KokiriForest", ["KF Boulder Maze Blue Rupee 1", "KF Boulder Maze Blue Rupee 2"],
     ["16647730239269178270", "6618764049130440222"], "the two blue rupees by the Kokiri Sword chest"),
    ("KokiriForest", ["KF Bean Platform Red Rupee"] + _n("KF Bean Platform Green Rupee ", 1, 6),
     [["17212015369679208115"], ["4576019929976975366"], ["12079876816721924835"], ["3669266735444406174"],
      ["4462556192312188043"], ["9667799371071602538"], ["2512122383157745514"]],
     "adult rupee ring above the bean patch: 8 green + 1 purple in the remake (OoTR 6 green + 1 red); purple = red, 2 greens left over"),
    ("DeathMountainCrater", ["DMC Adult Red Rupee"] + _n("DMC Adult Green Rupee ", 1, 6),
     ["12599391464019187002", "11105674007629451672", "4077912846886775366", "6794008535785537922",
      "17524442172396680694", "17170677546946622823", "16794923646428529814"],
     "the ring by Pierre's platform: 6 green + 1 purple (OoTR 6 green + 1 red)"),
    # Don't pair the six adult rupees here as "DMT Cow Grotto". They're in the grotto under the Song of Storms cover
    # (Land_HidingHole_Base_I_03 / Land_Kokiri_HidingHoleCover_A_01), not in the cow's grotto under the bomb rock.
    # They're new DMT Storms Grotto locations (MANUAL_NEW), and OoTR's cow-grotto rupees and hearts are absent.
    ("Graveyard", _n("Graveyard Dampe Race Rupee ", 1, 8),
     ["3236392495739397075", "17177665557365847615", "1718356088455579946", "12976212884789503099",
      "2669035957658688527", "4184471392680640567", "8404733154085657768", "8987278980043647768"],
     "the 8 green rupees along Dampe's tunnel (adult file, near Dampe and the Poe sisters)"),
    ("ZoraFountain", _n("ZF Bottom Green Rupee ", 1, 18),
     ["9058546130605800023", "7369210492575735847", "5767588505352617062", "15066348262714298279", "10518148330968147601",
      "11712600857155855626", "7430539662759067881", "10247339190834717086", "5568633841506517325", "4175716627569108253",
      "11743429110701869711", "4077060633972129211", "6511717208019100686", "2207729956021615024", "16981113694024920682",
      "11672626208313429634"], "16 green rupees under water in the adult file (OoTR has 18)"),
    ("InsideTheDekuTree", _n("Deku Tree Basement Recovery Heart ", 1, 3),
     ["16597323285320397604", "2222711177065858733", "729508615351641392"], "the three hearts in the water of room 9, before the boss (OoTR room 9)"),

    # ---- pots, crates
    ("KokiriForest", ["KF Links House Pot"], [], "no pot in or by Link's house in the remake"),
    ("KokiriForest", ["KF House of Twins Pot 1"], ["15406610986108637956"], "House of Twins pot with a green rupee (OoTR: Rupee (1))"),
    ("KokiriForest", ["KF House of Twins Pot 2"], ["5133775918408786238"], "House of Twins pot with a blue rupee (OoTR: Rupees (5))"),
    ("KokiriForest", ["KF Know it All House Pot 1", "KF Know it All House Pot 2"], ["2108281022000564101", "14828228683041039284"],
     "the two green-rupee pots at the Know-It-All brothers' house"),
    ("HyruleField", ["HF Cow Grotto Pot 1", "HF Cow Grotto Pot 2"], ["8132480728943356272", "1439274781043171114"], "the two pots beside the grotto cow"),
    ("HyruleCastle", _n("HC Storms Grotto Pot ", 1, 4), ["6050451915923533728", "4993011432510724566"],
     "the two pots under ground at the castle's only grotto (OoTR has 4)"),
    ("KakarikoVillage", ["Kak Near Odd Medicine Building Pot 1", "Kak Near Odd Medicine Building Pot 2"],
     ["10165937155993394562", "35339038829944767"], "the two pots by the odd-medicine shop"),
    ("KakarikoVillage", ["Kak Near Potion Shop Pot 1", "Kak Near Potion Shop Pot 2", "Kak Near Guards House Pot 1",
                         "Kak Near Impas House Pot 1", "Kak Near Impas House Pot 2", "Kak Near Impas House Pot 3",
                         "Kak Near Guards House Pot 2", "Kak Near Guards House Pot 3", "Kak Near Potion Shop Pot 3"],
     ["3252450751793784313", "6195808453148783180", "8015913209367877534", "17991454493447452409", "14122332566338914320",
      "18078110404684471865", "3252807497395580785", "700577879275312973"],
     "the other 8 child pots in the village (OoTR has 9, all child-only)"),
    ("DeathMountainCrater", _n("DMC Near GC Pot ", 1, 4), ["1392611204303480056", "8852244876520518028"],
     "the two pots by the Goron City entrance (the first has a heart table, OoTR's pot 1 a heart)"),
    ("GoronCity", ["GC Darunia Pot 1", "GC Darunia Pot 2", "GC Darunia Pot 3"],
     ["10324626920382966851", "5321285816867041493", "15844472277169991248"], "the three pots in Darunia's room (child file only)"),
    ("GoronCity", ["GC Lower Staircase Pot 1"], [["16954699510563627060", "16601055785856579612"]], "lower pots (y 103): child stick pot + adult pot 1.3 units apart"),
    ("GoronCity", ["GC Lower Staircase Pot 2"], ["7233425345132106189"], "lower pots (y 103)"),
    ("GoronCity", _n("GC Upper Staircase Pot ", 1, 3), ["9364468317723295924", "6278492438802004667"], "upper pots (y 111), OoTR has 3"),
    ("GoronCity", ["GC Medigoron Pot"], ["5019133693822726830"], "next to Medigoron"),
    ("GoronCity", ["GC Boulder Maze Crate"], ["8694345348366441423"], "the boulder-maze crate (child file; the skulltula sits in it)"),
    ("HountedWasteland", ["Wasteland Near GS Pot 1"], ["7610536230682784975"], "the four pots by the wasteland structure and its skulltula; heart-table pot"),
    ("HountedWasteland", ["Wasteland Near GS Pot 2", "Wasteland Near GS Pot 3", "Wasteland Near GS Pot 4"],
     ["4476280516446896621", "2769366735314972197", "15199213860662802000"], "the other three pots there"),
    ("ZoraDomain", ["ZD Pot 1"], ["9081708815728257714"], "the stick-table pot (OoTR: Deku Stick)"),
    ("ZoraDomain", ["ZD Pot 2", "ZD Pot 3", "ZD Pot 4", "ZD Pot 5"],
     ["8376134792258235941", "18012220795750713118", "502205486743214712", "3017923073533463600"], "the other four"),
    ("ZoraFountain", _n("ZF Near Jabu Pot ", 1, 4),
     ["10835121848480419248", "11382955502959013110", "697465442349235192", "7692213673625838330"], "the four child pots by Jabu-Jabu"),
    ("InsideJabuJabuBelly", _n("Jabu Jabus Belly Barinade Pot ", 1, 6),
     ["17008314122241535243", "7236701055993128778", "13226303525664955816", "4451366174329825617",
      "8321479553829035058", "5637390904733861408"], "the six heart pots in the boss room (room 15, with the heart container)"),
    ("InsideJabuJabuBelly", _n("Jabu Jabus Belly Above Big Octo Pot ", 1, 3),
     ["6978589088482176618", "3604029748172586256", "6807599735094224635"], "room 6, 3 pots (OoTR room 6, 3 pots)"),
    ("InsideJabuJabuBelly", _n("Jabu Jabus Belly Basement Switch Room Pot ", 1, 3),
     ["9356640604710933239", "13411964117731733665", "5103883096284362521"], "room 14, 3 pots (OoTR room 14, 3 pots)"),
    ("InsideJabuJabuBelly", _n("Jabu Jabus Belly Basement 2 Octoroks Pot ", 1, 5),
     ["11286310503376671564", "15686356656840817485", "437556170115291814", "3104022011556950435"], "room 13, 4 pots (OoTR room 13, 5 pots)"),
    ("InsideJabuJabuBelly", ["Jabu Jabus Belly Small Wooden Crate 1", "Jabu Jabus Belly Small Wooden Crate 2"],
     ["16293430382336788523", "621843243819307036"], "the dungeon's only two (small) crates"),
    # Fire Temple rooms keep OoTR's numbers. Room 2 holds Darunia and 4 pots (3 boss-supply tables + 1 fairy table),
    # where OoTR's room 2 "Near Boss" has 4 pots (2 fairies, 2 bombs). Room 1 has 3 pots like OoTR's room 1.
    ("FireTemple", _n("Fire Temple Big Lava Room Pot ", 1, 3), ["13720304619349543095", "2839526458267949318", "12275059645282086381"],
     "room 1, 3 pots (OoTR room 1, 3 pots)"),
    ("FireTemple", _n("Fire Temple Near Boss Pot ", 1, 4), ["15267562180962122590", "15304985273997957319", "5818975214008540983", "4888253376140319316"],
     "room 2 by Darunia, 4 pots (OoTR room 2, 4 pots; the fairy-table pot first)"),
    ("FireTemple", _n("Fire Temple Moving Fire Room Recovery Heart ", 1, 3), ["10973307894322368710", "876976950103637140"],
     "room 16, 2 hearts (OoTR room 16, 3 hearts)"),
    ("ForestTemple", _n("Forest Temple Center Room Right Pot ", 1, 3) + _n("Forest Temple Center Room Left Pot ", 1, 3),
     ["12190827011300834192", "16258156194217221025", "16714728970292620430", "9600596241209359414", "139743615625578751", "8229370832781285891"],
     "the six pots of room 2, three per side (x > 0 right, x < 0 left)"),
]
# Computed sets. The Market guard house one is the pots room "PodsRoom" (x 7..18, z 52..63).
SELECTIONS = [
    ("Market", _n("Market Guard House Child Pot ", 1, 44), {"category": "pot", "age": "child", "box": (7, 18, 52, 63)},
     "child pots in the guard house"),
    ("Market", _n("Market Guard House Adult Pot ", 1, 11), {"category": "pot", "age": "adult", "box": (7, 18, 52, 63)},
     "adult pots in the guard house"),
    ("Market", _n("Market Guard House Child Crate ", 1, 4), {"category": "crate", "age": "child", "box": (7, 18, 52, 63),
                                                            "exclude": ["14951295602089760727"]},
     "the guard-house crates other than the one holding the skulltula"),
]
# Why the remaining locations stay vanilla (first matching pattern wins).
VANILLA_WHY = [
    (r"^(LLR GS (Rain Shed|House Window|Back Wall)|LH GS Small Island|HF GS (Cow|Near Kak) Grotto)$",
     "one of six Hyrule Field / ranch / lake skulltulas the level files don't tell apart (one child-only, one "
     "adult-only in a grotto crate, four for both ages; none by the grotto cow); a group would mix ages"),
    (r"^ZR GS Tree$", "the remake moved this child skulltula into Zora's River's second bean patch (it appears from "
                      "planted bugs), so OoTR's rule (bonk the tree) does not cover it"),
    (r"Beehive", "the remake's grottos have no beehives (its only beehives are 7 new ones outdoors in Kakariko)"),
    (r"Freestanding Key$|Jail Gerudo Key$", "small keys lie in the world without a save flag (AlwaysRespawn) or are "
                                            "the four Gerudo key actors with their own named flags"),
    (r"^(GV Crate|GV Waterfall) Freestanding PoH$", "one Gerudo Valley heart piece in the remake for OoTR's two; can't tell which"),
    (r"^GC Pot Freestanding PoH$", "the spinning pot's heart piece is created by the pot, not placed; with "
                                   "remake_gc_pot_prize 'any' the pot's heart-piece scene gives any item (drop_map "
                                   "'scene_gifts')"),
    (r"^GC Spinning Pot", "comes from Goron City's spinning pot, a scene, not a placed pickup"),
    (r"Dampe (Race Freestanding PoH|Gravedigging)", "given by Dampe's race / digging scenes, not a placed pickup"),
    (r"^(HF Tektite Grotto|Ice Cavern) Freestanding PoH$|^GF Freestanding PoH$", "no placed heart piece for it in the remake"),
    (r"Grotto (Pot|Recovery|Green|Blue|Red)", "the remake's version of this grotto has different contents"),
    (r"^(LW |LH |ZR Waterfall|GV Octorok|DMC Child|DMT Rock|KF (Behind|End of|Grass Near))",
     "the remake's rupees here don't match OoTR's (count, colour or place; some KF ones are wonder items turned into "
     "rupees); can't tell which is which"),
    (r"^(Deku Tree|Dodongos Cavern|Jabu|Forest Temple|Fire Temple|Water Temple|Shadow Temple|Spirit Temple|Bottom of the Well|"
     r"Ice Cavern|Gerudo Training|Ganons Castle).*(Recovery Heart|Rupee)",
     "the remake's dungeon has no placed heart or rupee for it (its dungeon files hold almost none)"),
    (r"^(Deku Tree|Dodongos Cavern|Jabu|Forest Temple|Fire Temple|Water Temple|Shadow Temple|Spirit Temple|Bottom of the Well|"
     r"Ice Cavern|Gerudo Training|Ganons Castle)",
     "dungeon pots, crates and flying pots: the remake's counts per room differ and its room numbers mostly don't "
     "match OoTR's; not paired (only rooms whose number and count both match are)"),
    (r"(Pot|Crate)", "the remake has a different set of these here (count or place differs); not paired"),
]
DEFAULT_WHY = "no counterpart found in the remake's level files"

# Second pass: every remake object is a location
# data/rando/drops_regions_*.json give the OoTR region (and any extra requirement) of every remake drop object per
# remake area, more OoTR <-> remake pairs, and the OoTR locations proven absent from the remake (with evidence).
# Unpaired remake objects become NEW OoTR locations in their region, and absent OoTR locations leave logic.
# build writes it all into data/rando/logic/drops.json (new_locations + region rules, absent = null).
REGION_FILES = os.path.join(HERE, "data", "rando", "drops_regions_{}.json")
REGION_PARTS = ("d1", "d2", "o1", "o2", "x1", "x2", "x3")  # x1 is trees, respawning pots and grass, silver rocks
# x2 covers icicles and red ice. x3 covers butterflies that turn into fairies.
LOGIC_OUT = os.path.join(HERE, "data", "rando", "logic", "drops.json")
# category -> (location type, setting that shuffles it, rule to break/collect the object, name word)
# OoTR types follow OoTR's settings (shuffle_pots...), and Remake* types are the remake's own settings (remake_*).
# Grass tufts (Obj_Plant_Grass_A_01, _A_03, _A_01_Respawn) also go to a bomb's blast or Din's Fire, since my rule is to
# count every way the game allows. Their chemistry Obj_Grass has RequestDeathIfExploded and RequestDeathIfBurned,
# Plant_Grass's damage table has the exception "Din's Fire only ignites it" (same as the beehives, and I've seen Din's
# Fire break those), and the Default death procedure drops on Exploded and Burned. The Hyrule Field bushes have no
# chemistry and keep can_cut_shrubs.
GRASS_RULE = "can_cut_shrubs or has_explosives or can_use(Dins_Fire)"
CATEGORY = {
    "pot": ("Pot", "shuffle_pots", "True", "Pot"),
    "crate": ("Crate", "shuffle_crates", "can_break_crate", "Crate"),
    "small_crate": ("SmallCrate", "shuffle_crates", "True", "Small Crate"),
    "flying_pot": ("FlyingPot", "shuffle_pots", "True", "Flying Pot"),
    "beehive": ("Beehive", "shuffle_beehives", "can_break_upper_beehive", "Beehive"),
    "freestanding": ("Freestanding", "shuffle_freestanding_items", "True", None),
    "gold_skulltula": ("GS Token", "tokensanity", "True", "GS"),
    "grass": ("RemakeGrass", "remake_shuffle_grass", GRASS_RULE, "Grass"),
    "rock_liftable": ("RemakeRock", "remake_shuffle_rocks", "True", "Rock"),
    "rock_bombable": ("RemakeBoulder", "remake_shuffle_boulders", "can_blast_or_smash", "Boulder"),
    "palm_fruit": ("RemakeMisc", "remake_shuffle_misc", "True", "Palm Fruit"),
    # cow skulls and hanging signs only drop on an Arrow or Hookshot hit (ExternalDamageTypes 6 / 16 in their AIs)
    "gerudo_decoration": ("RemakeMisc", "remake_shuffle_misc", "can_use(Bow) or can_use(Hookshot)", "Decoration"),
    # Ship of Harkinian's object shuffles
    "tree": ("RemakeTree", "remake_shuffle_trees", "can_bonk or can_blast_or_smash", "Tree"),
    "grass_always_respawn": ("RemakeGrass", "remake_shuffle_grass", GRASS_RULE, "Grass"),
    "pot_always_respawn": ("Pot", "shuffle_pots", "True", "Pot"),
    "rock_silver": ("RemakeBoulder", "remake_shuffle_boulders", "Silver_Gauntlets", "Silver Rock"),
    "icicle": ("RemakeIcicle", "remake_shuffle_icicles", "can_jumpslash or has_explosives", "Icicle"),
    "icicle_falling": ("RemakeIcicle", "remake_shuffle_icicles", "True", "Falling Icicle"),
    "red_ice": ("RemakeRedIce", "remake_shuffle_red_ice", "Blue_Fire", "Red Ice"),
    # Ship of Harkinian's Shuffle Bushes, the Hyrule Field bushes. You cut them, you can't roll through them, since
    # their damage table takes no Body or Slingshot damage.
    "bush": ("RemakeBush", "remake_shuffle_bushes", "can_cut_shrubs", "Bush"),
    # Ship of Harkinian's Shuffle Butterfly Fairies (the fairies plugin's setting). The butterfly follows a Deku Stick
    # and turns into a fairy, and the rule is OoTR's Butterfly Fairy rule.
    "butterfly": ("RemakeButterfly", "remake_shuffle_butterfly_fairies", "can_use(Sticks)", "Butterfly Fairy"),
}
# types whose break rule differs from their category's. Bronze boulders only take the hammer. Their ChemicalParam is
# Dummy, and a bomb's blast reaches objects through their chemistry.
ACTOR_BASE_RULE = {"Obj_BrokenRock_A_02": "can_use(Megaton_Hammer)"}
# Permanent adult layout changes (GameDataList BoolExps Sequence_IsAlternative_<Area>Adult).
# Kakariko burns after the Forest, Fire and Water sages. Zora's Domain thaws after the Water sage.
ALT_LAYOUTS = {"KakarikoVillage": "'Defeat Phantom Ganon' and 'Defeat Volvagia' and 'Defeat Morpha'",
               "ZoraDomain": "'Defeat Morpha'"}
# Remake helpers, written into data/rando/logic/drops.json "helpers" with one definition each.
# They're OoTR's definitions, adjusted to what the remake's damage tables and AIs say.
REMAKE_HELPERS = {
    # Deku Sticks are Blunt and both plant damage tables refuse Blunt. Bombs don't cut the field bushes (no chemistry).
    "can_cut_shrubs": "is_adult or Kokiri_Sword or Boomerang or can_use(Megaton_Hammer)",
    "can_mow_the_lawn": "is_adult or (is_child and (Kokiri_Sword or Boomerang or has_explosives))",
    # beehives take arrow damage and have 1 life (the Slingshot does nothing). Din's Fire burns them. The damage table
    # has the exception "Din's Fire only ignites it", the chemistry is Obj_WoodPlate (IsBurn) with RequestDeathIfBurned,
    # and the Default death procedure drops on Burned. Its sphere (ExpandFireField, radius 1 scaled 3 then +4, so 7)
    # reaches every Kakariko grotto hive (2.9-4.4 m above the floor under it, drop_landings.json), and I broke one in
    # game.
    "can_break_lower_beehive": "can_use(Boomerang) or can_use(Hookshot) or can_use(Bow) or can_use(Dins_Fire) or "
                               "Bombs or (logic_beehives_bombchus and has_bombchus)",
    "can_break_upper_beehive": "can_use(Boomerang) or can_use(Hookshot) or can_use(Bow) or can_use(Dins_Fire) or "
                               "(logic_beehives_bombchus and has_bombchus)",
    # Armos take no damage from swords, sticks, thrown objects or the boomerang
    "can_kill_armos": "has_soul(Armos) and ((is_adult and (Bow or Hookshot or Megaton_Hammer)) or has_explosives or "
                      "can_use(Slingshot) or can_use(Dins_Fire))",
    # Biri and Bari take no arrow damage
    "can_kill_biri": "has_soul(Biri_and_Bari) and ((is_child and ((Kokiri_Sword and (can_take_damage or Nuts or "
                     "Magic_Meter)) or Sticks or Boomerang or can_use(Megaton_Hammer))) or (is_adult and "
                     "(can_take_damage or Nuts or Hookshot or Megaton_Hammer or Magic_Meter or can_use(Sticks))) or "
                     "Bombs or (Nuts and has_bombchus) or can_use(Dins_Fire))",
    "can_kill_bari": "has_soul(Biri_and_Bari) and ((is_child and ((Kokiri_Sword and (can_take_damage or Nuts or "
                     "Magic_Meter or Boomerang)) or Sticks or can_use(Megaton_Hammer))) or (is_adult and "
                     "(can_take_damage or Nuts or Hookshot or Megaton_Hammer or Magic_Meter or can_use(Sticks))) or "
                     "Bombs or ((Nuts or can_use(Boomerang)) and has_bombchus) or can_use(Dins_Fire))",
    # the method table says the Flare Dancer's fire only comes off with bombs, the hammer or a shockwave. The dungeon
    # review reads the Hookshot as the only hit on the fire body, so logic asks for both.
    "can_kill_flare_dancer": "has_soul(Flare_Dancer) and (has_explosives or can_use(Megaton_Hammer)) and "
                             "can_use(Hookshot)",
    # the Song of Storms also calls a gossip stone's fairy (GossipStone:BlewOcarinaByPlayer Event12 cases 0, 1, 3, 4, 5)
    "can_summon_gossip_fairy": "can_play(Zeldas_Lullaby) or can_play(Eponas_Song) or can_play(Song_of_Time) or "
                               "can_play(Suns_Song) or can_play(Song_of_Storms)",
    "can_summon_gossip_fairy_without_suns": "can_play(Zeldas_Lullaby) or can_play(Eponas_Song) or "
                                            "can_play(Song_of_Time) or can_play(Song_of_Storms)",
    # a withered Deku Baba has 1 life and takes every hit but arrows and thrusts. Its damage table
    # (Enemy_Dekubaba_Withered) has Arrow and ThrustWeapon at 0 and SmallWeapon, LargeWeapon, SlingshotBullet,
    # Boomerang, Bomb and Fire at 1.0, and its chemistry enemy00 dies to a blast or a burn. There's no Blunt exception,
    # so a Deku Stick works.
    "can_kill_withered_deku_baba": "has_soul(Deku_Baba) and (is_adult or Kokiri_Sword or Sticks or Slingshot or "
                                   "Boomerang or has_explosives or can_use(Dins_Fire))",
}
# Gossip Stone and bean-plant fairies heal Link in a scene and disappear before he can bottle them.
# These are the regions where OoTR gives them a "Fairy" drop.
NO_BOTTLED_FAIRY = {
    "Gossip Stone Fairy": ("Dodongos Cavern Lobby", "Kokiri Forest", "Lost Woods", "Sacred Forest Meadow", "Lake Hylia",
                           "GV Upper Stream", "Desert Colossus", "ToT Entrance", "Hyrule Castle Grounds",
                           "Graveyard Warp Pad Region", "Death Mountain Summit", "Goron City", "DMC Upper Local",
                           "Zora River", "Zoras Domain", "Zoras Fountain", "KF Storms Grotto", "LW Near Shortcuts Grotto",
                           "HF Southeast Grotto", "HF Open Grotto", "HF Cow Grotto", "HF Near Market Grotto",
                           "HC Storms Grotto", "Kak Open Grotto", "DMT Storms Grotto", "DMC Upper Grotto",
                           "ZR Open Grotto"),
    "Bean Plant Fairy": ("Kokiri Forest", "Lost Woods", "Lake Hylia", "GV Upper Stream", "Graveyard", "Death Mountain",
                         "DMC Central Local", "Zora River")}


def _layout_rule(rows):
    """For objects in an area with two adult layouts (ALT_LAYOUTS). Returns a rule restricting the ages and story state
    that can reach one of them, "missable" if no age can count on it, or None (no restriction). A copy only in the
    later layout needs its bosses, and a copy only in the earlier one is gone for good once they're beaten."""
    area = next((r["file"].split("/")[1] for r in rows if r["file"].split("/")[1] in ALT_LAYOUTS), None)
    if area is None:
        return None
    child = any(r["age"] in ("child", "both") for r in rows)
    pre = {str(r["hash"]) for r in rows if r["age"] == "adult"}
    alt = {str(r["hash"]) for r in rows if r["age"] == "adult_alt"}
    if any(r["age"] == "both" for r in rows) or (pre and alt):
        adult = "is_adult"  # in both layouts (one location, one check, since the respawn model's bit is per location)
    elif alt:
        adult = f"is_adult and ({ALT_LAYOUTS[area]})"
    else:
        adult = None  # only before the switch, so an adult can't count on it
    if child and adult == "is_adult":
        return None
    parts = (["is_child"] if child else []) + ([adult] if adult else [])
    if not parts:
        return "missable"
    return " or ".join(f"({x})" for x in parts) if len(parts) > 1 else parts[0]


# Catalogue additions, actor -> category for objects data/rando/drop_objects.csv doesn't list (or lists under a
# category these spots shouldn't take). None means it's not a location.
EXTRA_CATEGORY = {**{f"Obj_BrokenIcePillar_A_0{i}": "icicle" for i in range(1, 5)},
                  "Obj_FallingIcicle_A_01": "icicle_falling", "Obj_FallingIcicle_A_02": "icicle_falling",
                  **{a: "red_ice" for a in ("Obj_RedIce_A_01", "Obj_RedIce_A_02", "Obj_RedIce_A_04", "Obj_RedIce_A_06",
                                            "Obj_RedIce_A_07", "Obj_RedIce_A_08", "Obj_RedIce_A_09")},
                  "Obj_LiftRock_B_01": "rock_silver",
                  # the Goron City end of the Lost Woods shortcut (OoTR's "GC Woods Warp Open"), one per age layout
                  "Obj_Goron_BrokenRock_A_01": "rock_bombable",
                  "Obj_LiftRock_A_02": None, "Obj_LiftRock_C_01": None, "Obj_LiftRock_C_05": None,  # a seat, pillars
                  "Obj_Gerudo_PalmTree_A_01": None,  # never drops (its fruits are the spots)
                  "Animal_ButterflyToFairy": "butterfly"}
NOT_LOCATION_AREAS = ("DreamWorld",)  # the boss rush (from Link's bed), no OoTR region
REMAKE_TYPES = {"RemakeGrass", "RemakeRock", "RemakeBoulder", "RemakeMisc", "RemakeTree", "RemakeIcicle",
                "RemakeRedIce", "RemakeBush", "RemakeButterfly"}
FREESTANDING_WORD = {"Obj_Rupee_Green": "Green Rupee", "Obj_Rupee_Blue": "Blue Rupee", "Obj_Rupee_Red": "Red Rupee",
                     "Obj_Rupee_Purple": "Purple Rupee", "Obj_Rupee_Gold": "Gold Rupee", "Obj_Heart": "Recovery Heart",
                     "Obj_Heart_InWater": "Recovery Heart"}
# vanilla OoTR item of a remake object, from its fixed drop or its pickup. A random table is OoTR's "Nothing" (empty).
VANILLA_OF_ACTOR = {"Obj_Rupee_Green": "Rupee (1)", "Obj_Rupee_Blue": "Rupees (5)", "Obj_Rupee_Red": "Rupees (20)",
                    "Obj_Rupee_Purple": "Rupees (50)", "Obj_Rupee_Gold": "Rupees (200)", "Obj_Heart": "Recovery Heart",
                    "Obj_Heart_InWater": "Recovery Heart", "Obj_Fairy": "Fairy Drop", "Obj_DekuNut": "Deku Nuts (5)",
                    "Obj_DekuStick": "Deku Stick (1)", "Obj_DekuSeed": "Deku Seeds (30)", "Obj_Bomb": "Bombs (5)",
                    "Obj_ArrowBundle_Small": "Arrows (5)", "Obj_ArrowBundle_Medium": "Arrows (5)",
                    "Obj_Token_Gold": "Gold Skulltula Token", "Obj_Heart_Piece": "Piece of Heart"}
VANILLA_OF_TABLE = {"DropTable_Obj_Heart": "Recovery Heart", "DropTable_Obj_DekuNut": "Deku Nuts (5)",
                    "DropTable_Obj_DekuStick": "Deku Stick (1)", "DropTable_Obj_Bomb": "Bombs (5)",
                    "DropTable_Obj_Bomb_01": "Bombs (5)", "DropTable_Obj_Bomb_02": "Bombs (5)",
                    "DropTable_Obj_Fairy": "Fairy Drop", "Drop_Rupee_Red2": "Rupees (20)",
                    "DropTable_Obj_MagicJar_Small": "Recovery Heart"}
# OoTR shuffles beehives with no "empty" check, so a random-table hive counts as its usual blue rupee
EMPTY_AS = {"Beehive": "Rupees (5)"}
# Remake objects the region files don't list, because they were paired before the second pass.
# Rows are (area, hashes, region, rule, why).
MANUAL_NEW = [
    ("DeathMountainTrail", ["991975198297951915", "6307624256587354938", "17286901874670360605", "5008999164523690598",
                            "9972535766636368278", "12472730518306029279"], "DMT Storms Grotto", "True",
     "adult rupee ring at y 58 about 20 units from Land_HidingHole_Base_I_03, the grotto under the Song of Storms "
     "cover (Land_Kokiri_HidingHoleCover_A_01); the cow stands in the other grotto (B_02, bomb rock)"),
    ("HyruleField", ["2177746409373494991"], "Hyrule Field", "can_bonk and (is_adult or can_child_attack)",
     "pop-out Gold Skulltula in the Obj_Tree_A_01 at (70,160,264) east of the ranch (AppearPopOut): roll into the tree"),
    ("HyruleField", ["9047381233010434881"], "HF Open Grotto",
     "can_blast_or_smash and can_break_crate and at('HF Open Grotto', is_child and can_child_attack)",
     "adult Gold Skulltula inside the Obj_BrokenBox_A_01 crate of the south generic grotto (gossip stone, wall "
     "Skulltulas, base 39.9,139.7,342.3); its HrlField cover opens with bombs (drops_regions_o1: HF Open Grotto). "
     "Guides (audit_overworld): a child must first kill a Skulltula there; the files show no link or Presence for "
     "it, so the stricter guide rule is kept"),
]
# extra requirements for new locations that the region files don't carry, hash -> (rule, why)
SPOT_RULES = {
    "14654205574115276454": ("at('HF Open Grotto', is_child and can_child_attack)",
                             "guides (audit_overworld): a child must first kill a Skulltula in this grotto before the "
                             "adult can break the crate"),
}
# Regions an age never stands in, because its layout gives it no way in (OoTR's glitchless logic agrees unless
# overworld entrances are shuffled). That age's copies of objects there aren't locations, whatever the settings, but
# the other age's copies at the same spots are. region -> {age: evidence}.
# The tracker logic server found these (tools/tracker/logic_server.py --validate, never available even with every item).
AGE_NEVER = {
    "GV Fortress Side": {"child": (
        "the child layout (GerudoValley_Child_*) stops a child at the west end of the bridge: Npc_Gerudo_002 there with "
        "the trigger ValleyStopped02_Npc_Gerudo_002_Talk (Npc_Gerudo_002.bfevfl: she talks, then "
        "EventPlayerMoveToAnchor Player_KickOutPos), nine child-only FldObj_AirWall_Player along that side "
        "(x -9..-24), and no entrance to Gerudo Fortress (the adult layout's FieldAndDungeonEntranceEventRequestActor "
        "at (-66.6,114,-7.2)); OoTR: Gerudo Valley -> GV Fortress Side needs is_adult. Each child object here stands "
        "where an adult one does (same position), and those are locations")},
    "GV Storms Grotto": {"child": (
        "entered from GV Fortress Side only (its cover at (-45.3,101,-29) is west of the bridge), which a child can't "
        "reach (see GV Fortress Side); OoTR: is_adult and can_open_storm_grotto. Each child pot stands where an adult "
        "one does, and those are locations")},
}
# OoTR locations proven absent from the remake that the region files don't list, name -> evidence
ABSENT = {
    "LLR GS Rain Shed": "the ranch has two night Gold Skulltulas on buildings (both linked to LocationArea_LonLonRanch) "
                        "for OoTR's three; they take the two boomerang-rule names, so the third is absent",
    "HF GS Cow Grotto": "the cow grotto (Land_HidingHole_Base_D_02: cow, 2 pots, gossip stone, webs, a normal "
                        "Skulltula) holds no Enemy_Skulltula_Gold",
    "Ice Cavern Freestanding PoH": "no Obj_Heart_Piece placement, chest or drop with a heart piece in any IceCavern file; "
                                   "the compass room's red-ice spots hold pots",
    "HF Tektite Grotto Freestanding PoH": "the tektite grotto (Land_HidingHole_Base_H_01: water, tektite, fish) holds three "
                                          "green-rupee crates and no heart piece",
    "GF Freestanding PoH": "no Obj_Heart_Piece in any GerudoFortress file; the fortress's only heart piece is the roof "
                           "chest (GF Chest)",
}
ABSENT.update({n: "OoTR's cow-grotto rupees/hearts: the remake's cow grotto (Land_HidingHole_Base_D_02 on DMT, cow and "
                  "gossip stone) holds no placed rupee or heart; the rupee ring is in the storms grotto (MANUAL_NEW)"
               for n in ["DMT Cow Grotto Red Rupee"] + _n("DMT Cow Grotto Green Rupee ", 1, 6)
               + _n("DMT Cow Grotto Recovery Heart ", 1, 4)})
WONDER_WHY = ("the remake has no invisible wonder-item actor: no WonderItem/HiddenItem-like type exists in any level "
              "file; its own placed rupees where OoT had wonder items are new Freestanding "
              "locations")
# OoTR locations that stay but get a new rule/region, name -> (old region, new region, rule)
RULE_MOVES = {
    "ZR GS Tree": ("ZR Front", "Zora River", "can_plant_bugs and can_child_attack"),
    # the remake's GS is behind room 17's cracked wall by the Map chest, and you reach it from the dive at middle water
    # (true pairs). OoTR's rule is stricter, but it's in a region the remake doesn't have it in.
    "Water Temple GS Falling Platform Room": ("Water Temple Falling Platform Room", "Water Temple Dive",
                                             "can_blast_or_smash and at('Water Temple Middle Water Level', True)"),
}
# OoTR drop-type locations that another part of the rando patches (they aren't drop objects in the remake)
ELSEWHERE = {
    "GV Crate Freestanding PoH": "a chest in the remake (GerudoValley/chest/15856256242099990922): chests plugin",
    "Graveyard Dampe Race Freestanding PoH": "a chest in the remake (Graveyard/chest/5534919361313859554): chests plugin",
    "Graveyard Dampe Gravedigging Tour": "Dampe's digging scene: the scenes plugin",
}
# OoTR locations that can't be patched, with evidence. They're left vanilla and reported as blocked.
# It's empty now. GC Pot Freestanding PoH used to be here, but its once-flag is the save-data Bool
# GoronLargePot_IsGetHeartPiece, which the pot's code reads before it offers the heart piece and sets when the held
# heart piece dies PickedUp. And the pot's heart-piece scene can give any item instead (SCENE_GIFTS).
BLOCKED = {}
# Spots that get a scene of their own to give them when a remake setting asks for it
# The full entries go to drop_map "scene_gifts", and "drops"/"new" keep the old
# entries (the pot heart vanilla, the grotto rupees as their own kind), so nothing changes with the setting at its
# first value. build checks every name below against the game files (_scene_gift_evidence).
GC_POT = "GC Pot Freestanding PoH"
ZD_GROTTO = tuple(f"ZD Storms Grotto Blue Rupee {i}" for i in range(1, 7))
SCENE_GIFTS = {
    # remake_gc_pot_prize "any". The heart-piece drop scene (GoronLargePotParameter HeartPieceDropEventName) hides and
    # kills the dropped heart piece in Dm_Goron_0045 after its last step (DeathReason 10, like Dm_SY_Get Event124). It
    # also sets the pot's once-flag and gives the item (GoronCity_LargePot, after the HeartPieceDrop entry's last step).
    # The pot's code only offers the heart piece while that flag is false, so the scene plays
    # once.
    "gc_pot": {
        "setting": "remake_gc_pot_prize", "locations": [GC_POT], "area": "GoronCity",
        "pot": {"file": "Banc/GoronCity/GoronCity_Child_Static.bcett.byml.zs", "actor": "Obj_GoronCity_LargePot_A_01",
                "pack": "Pack/Actor/Obj_GoronCity_LargePot_A_01.pack.zs", "slot": "Prize_HeartPiece"},
        "drop_scene": {"file": "Dm_Goron_0045", "after": "Event16", "actor": "Obj_Heart_Piece"},
        "give_scene": {"file": "GoronCity_LargePot", "entry": "GoronCity_LargePotRoulette_HeartPieceDrop",
                       "after": "Event17"},
        "flag": "GoronLargePot_IsGetHeartPiece",
        # the scene ID's HavePlayedEvent flag, which the engine sets after a play. A second
        # heart-piece scene could never give again.
        "once": "HavePlayedEvent.GoronCity_LargePotRoulette_HeartPieceDrop",
    },
    # remake_zd_grotto_rupees "gift". OoTR gives all six the rule True inside region ZD Storms Grotto, so we give them
    # the first time you enter the grotto. The grotto's entry requester (one EventRequestActor per Zora's Domain stage,
    # RequestEventName HidingHole_Entry_01) asks for a reused scene ID. Its entry plays the vanilla grotto entry and
    # then the six items, once (the ID's HavePlayedEvent flag). The six Obj_Rupee_Blue placements are deleted.
    "zd_grotto": {
        "setting": "remake_zd_grotto_rupees", "locations": list(ZD_GROTTO), "area": "ZoraDomain",
        # A config/scene_rows.json row no other plugin takes. The chests plugin's ice-trap rows are the last two, and
        # its other trap kinds use DodongoCavern_, ForesetTemple_ and FireTemple_ GetMap/GetCompass. The dungeons plugin
        # has WaterTemple_GetCompass and BottomOfTheWell_GetCompass, plus its silver-rupee scene ShadowTemple_GetCompass
        # (data/rando/silver_rupees.json). Progressive scenes take the front.
        # parity/drops.py check_settings refuses a seed if another plugin names it.
        "row": "ShadowTemple_GetMap",
        "copy_of": "HidingHole_Entry_01",
        "scene": {"file": "GimmickFlow_Common", "entry": "Rando_ZDGrotto_Entry", "vanilla": "HidingHole_Entry_01"},
    },
}


# OoTR drops events whose rule is always False, and then referring to one raises NameError at parse time. So we guard
# these the way the Hideout rules do. gerudo_fortress fast frees the 2-, 3- and 4-torch carpenters up front, and open
# frees all four. story.py (tools/rando/parity/story.py) records the rescues and ends the door fights so the cells
# are open.
MODE_GUARDS = {
    "'Hideout 1 Torch Jail Carpenter'": "(gerudo_fortress == 'open' or 'Hideout 1 Torch Jail Carpenter')",
    "'Hideout 2 Torches Jail Carpenter'": "(gerudo_fortress != 'normal' or 'Hideout 2 Torches Jail Carpenter')",
    "'Hideout 3 Torches Jail Carpenter'": "(gerudo_fortress != 'normal' or 'Hideout 3 Torches Jail Carpenter')",
    "'Hideout 4 Torches Jail Carpenter'": "(gerudo_fortress != 'normal' or 'Hideout 4 Torches Jail Carpenter')",
}


def mode_safe(rule):
    """rule with every settings-dependent OoTR event guarded (MODE_GUARDS); idempotent."""
    if not isinstance(rule, str):
        return rule
    for ev, guarded in MODE_GUARDS.items():
        if ev in rule and guarded not in rule:
            rule = rule.replace(ev, guarded)
    return rule


def _and(*parts):
    parts = [p for p in parts if p and p != "True"]
    if not parts:
        return "True"
    return parts[0] if len(parts) == 1 else " and ".join(f"({p})" for p in parts)


def _or_rules(rules):
    """The rule of a spot held by several copies, where any one will do. True if a copy is unconditional or the copies
    cover both ages, else their OR."""
    rules = sorted({r or "True" for r in rules})
    if "True" in rules or rules == ["is_adult", "is_child"]:
        return "True"
    return rules[0] if len(rules) == 1 else " or ".join(f"({r})" for r in rules)


def _vanilla_item(category, otype, rows):
    p = rows[0]
    if category == "gold_skulltula":
        return "Gold Skulltula Token"
    if category == "freestanding":
        return VANILLA_OF_ACTOR.get(p["actor"], "Rupee (1)")
    if p.get("drop") in VANILLA_OF_ACTOR:
        return VANILLA_OF_ACTOR[p["drop"]]
    if p.get("drop_table") in VANILLA_OF_TABLE:
        return VANILLA_OF_TABLE[p["drop_table"]]
    return EMPTY_AS.get(otype, "Nothing")


def load_region_files():
    out = {}
    for part in REGION_PARTS:
        path = REGION_FILES.format(part)
        if os.path.exists(path):
            for area, v in json.load(open(path, encoding="utf-8")).items():
                if area.startswith("_"):  # notes
                    continue
                if area in out:  # an area in two files (x1/x2 add objects to areas o1/d2 hold), so join them
                    for k, part in v.items():
                        out[area].setdefault(k, type(part)()).update(part) if isinstance(part, dict) else out[area].setdefault(k, []).extend(part)
                    continue
                out[area] = v
    return out


# Loading
def _age(rel):
    b = os.path.basename(rel)
    if "_Child" in b:
        return "child"
    if "_Adult_Alternative" in b:
        return "adult_alt"
    if "_Adult" in b:
        return "adult"
    return "both"


def _rule_age(rule):
    if re.match(r"^is_child(\s+and\b|$)", rule or ""):
        return "child"
    if re.match(r"^is_adult(\s+and\b|$)", rule or ""):
        return "adult"
    return None


def _load_game(romfs):
    """Every placement in the level files, the save flags, and which keys each actor accepts."""
    from romtools import Romfs, byml_load
    from actor_params import ActorParams
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    placements = defaultdict(list)  # hash -> [(area, rel, actor dict)]
    file_types = defaultdict(set)   # rel -> Gyaml set
    banc = os.path.join(romfs, "Banc")
    for area in sorted(os.listdir(banc)):
        p = os.path.join(banc, area)
        if not os.path.isdir(p) or area in ("BancBasedResource", "GameBancParam"):
            continue
        for fn in sorted(os.listdir(p)):
            if not fn.endswith(".bcett.byml.zs"):
                continue
            rel = f"Banc/{area}/{fn}"
            root, _ = byml_load(fs.read(rel))
            for a in (root or {}).get("Actors", []) or []:
                file_types[rel].add(a.get("Gyaml", ""))
                placements[str(a.get("Hash"))].append((area, rel, a))
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    flags = {str(e["Hash"]): int(e["ResetTypeValue"]) for e in gd["Data"]["Bool64bitKey"]}
    return placements, file_types, flags, ActorParams(romfs)


def _catalogue():
    rows = list(csv.DictReader(open(CATALOGUE, encoding="utf-8")))
    return {r["hash"]: r for r in rows}


PICKUP_TYPES = ("Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Rupee_Purple", "Obj_Rupee_Gold",
                "Obj_Heart", "Obj_Heart_InWater", "Obj_Heart_Piece", "Obj_GerudoValley_Heart_Piece",
                "Obj_Heart_Container", "Obj_Arrow_Fire", "Obj_DekuNut", "Obj_DekuSeed", "Obj_DekuStick",
                "Obj_Token_Gold", "Obj_Shield_Deku", "Obj_Shield_Hylian", "Obj_Armor_Goron", "Obj_Armor_Zora",
                "Obj_Bomb", "Obj_Bombchu", "Obj_ArrowBundle_Small", "Obj_ArrowBundle_Medium", "Obj_ArrowBundle_Large",
                "Obj_MagicJar_Small", "Obj_MagicJar_Large")
# Placed pickups with a permanent per-placement flag (NoRespawn, ResetTypeValue 24). A freestanding spot can only
# become one of these, and only one its level file already places, since a type new to a level broke Kokiri Forest.
FREESTANDING_TARGETS = ("Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Rupee_Purple", "Obj_Rupee_Gold",
                        "Obj_Heart", "Obj_Heart_InWater", "Obj_Heart_Piece", "Obj_Heart_Container", "Obj_Arrow_Fire",
                        "Obj_DekuNut", "Obj_DekuSeed", "Obj_DekuStick")
FREESTANDING_CATS = ("freestanding", "freestanding_rupee_heart")
# heart-piece pickup types with their own actor. The spot keeps its type when it gets a Piece of Heart.
HEART_PIECE_VARIANTS = ("Obj_GerudoValley_Heart_Piece",)
# Placed pickups that play the shared get scene Dm_SY_Get when you take them (Dm_SY_Get_WithoutPlayer in the air or
# water). Those are heart pieces and heart containers (PouchContentParam PlayGetEventManyTimes, no DefaultAutoGet).
# Rupees and recovery hearts are DefaultAutoGet and play none.
# Their event AI (AI/PouchContentUtuwa.event.root.ainb, the same bytes in all three packs) answers the scene's
# EventQueryCheckTagOnPouchActor. A spot holding another item gets a placement Name (its instance name, GET_SCENE_NAME
# + tag), and that query answers its tag (>= GET_SCENE_TAG_BASE) for that name, so the scene can give the spot's own
# item (tools/rando/parity/_songs_trade_lake.py, get-scene hook).
GET_SCENE_TYPES = {"Obj_Heart_Piece": "Pack/Actor/Obj_Heart_Piece.pack.zs",
                   "Obj_GerudoValley_Heart_Piece": "Pack/Actor/Obj_GerudoValley_Heart_Piece.pack.zs",
                   "Obj_Heart_Container": "Pack/Actor/Obj_Heart_Container.pack.zs"}
GET_SCENE_AI = "AI/PouchContentUtuwa.event.root.ainb"
GET_SCENE_QUERY = "EventQueryCheckTagOnPouchActor"
GET_SCENE_TAG_BASE = 5  # vanilla answers 0-4 (letter, Fire Arrow, Biggoron Sword, token, anything else)
# Kokiri Forest's freestanding rupees (27 spots) can swap among rupees, but the stage places no heart. So they take the
# heart piece, a pickup type new to the level, through the get scene, marked "new_type" in drop_map. The plugin only
# uses it once the in-game probe has passed, or in a test build that asks for the probe (parity/_test_start.py
# "probes"). A type new to a level "broke Kokiri Forest once", but that was Obj_TBox_A_06, a chest with its own
# check-actor AI.
NEW_TYPE_HEART = {"KokiriForest": "Obj_Heart_Piece"}
GET_SCENE_NAME = "RandoGetScene"


def _allowed_actors(rows, file_types):
    files = sorted({r["file"] for r in rows})
    out = [t for t in FREESTANDING_TARGETS if all(t in file_types[f] for f in files)]
    if any(r["actor"] in HEART_PIECE_VARIANTS for r in rows) and "Obj_Heart_Piece" not in out:
        out.append("Obj_Heart_Piece")  # stands for the spot's own heart-piece type (plan_ops keeps it)
    return out


def _resolved(files, rel):
    """A pack bgyml with its $parent chain merged (the child's keys win), or None."""
    from romtools import byml_load
    out, seen = None, 0
    while rel and rel in files and seen < 12:
        d = byml_load(files[rel])[0]
        out = dict(d) if out is None else {**d, **out}
        par = d.get("$parent")
        rel = par.replace("Work/", "").replace(".gyml", ".bgyml") if par else None
        seen += 1
    return out


def _dropper_tables(fs, types):
    """What a dropper type gives with no table on the placement (the first unnamed table of its DropParam), what it
    gives with a named one, and whether it lists DropTable_None:
    {type: {"default": fixed actor or None, "named": {table name: fixed actor or None}, "empty": bool,
    "default_bugs": true if the default table drops bugs every time}}
    A table is "fixed" when it drops one named actor at 100 %."""
    from romtools import sarc_files, byml_load, murmur3_32
    out = {}
    for t in sorted(types):
        try:
            files = sarc_files(fs.read(f"Pack/Actor/{t}.pack.zs"))
        except Exception:  # noqa: BLE001 - no pack of that name: nothing known
            continue
        comps, rel = {}, f"Actor/{t}.engine__actor__ActorParam.bgyml"
        while rel in files:
            d = byml_load(files[rel])[0]
            for k, v in (d.get("Components") or {}).items():
                comps.setdefault(k, v)
            par = d.get("$parent")
            rel = par.replace("Work/", "").replace(".gyml", ".bgyml") if par else None
        ref = comps.get("DropRef")
        dp = _resolved(files, ref.lstrip("?").replace("Work/", "").replace(".gyml", ".bgyml")) if ref else None
        if not dp:
            continue
        info = {"default": None, "named": {}, "empty": False}
        first = True
        bug_type = murmur3_32(b"Insect")  # the drop category of bugs (Animal_Insect, PouchContentParam InBottleBug)
        for tab in dp.get("DropTableResourceList", []):
            td = byml_load(files[tab.replace("Work/", "").replace(".gyml", ".bgyml")])[0]
            name = td.get("DropTableName", "")
            fixed = None
            subs = [byml_load(files[s.replace("Work/", "").replace(".gyml", ".bgyml")])[0]
                    for s in td.get("SubTableList", [])]
            items = [i for s in subs for i in s.get("Items", [])]
            if len(items) == 1 and items[0].get("DropProbability") == 100 and items[0].get("DropActorName") \
                    and not any(k.startswith("Items_Max") for s in subs for k in s):
                fixed = items[0]["DropActorName"].split("/")[-1].split(".")[0]
            if name == EMPTY_TABLE and not items:
                info["empty"] = True
            if name == "" and first:
                info["default"], first = fixed, False
                if items and all(i.get("Type") == bug_type and i.get("DropProbability") == 100 for i in items):
                    info["default_bugs"] = True
            elif name and fixed:
                info["named"][name] = fixed
        out[t] = info
    return out


def _key_spot_evidence(fs, spot):
    """Reads a freestanding key's room logic module and returns [problem, ...]. Empty means the key's Dead output sets
    spot["flag"] and that Bool gates the key, so a key taken through the get scene stays taken."""
    import ainb
    raw = open(fs.path(spot["logic"]), "rb").read()
    try:
        raw = fs.zs.decompress(raw)
    except Exception:  # noqa: BLE001 - stored uncompressed
        pass
    a = ainb.Ainb(raw)
    names = {}
    for i, n in enumerate(a.nodes):
        for p in n["properties"]["string"]:
            if p.get("name") == "InstanceName":
                names[i] = p.get("value")
    key = [i for i, v in names.items() if v == spot["instance"]]
    problems = [] if len(key) == 1 else [f"{spot['logic']}: no single node for {spot['instance']}"]
    sets = reads = 0
    for i, n in enumerate(a.nodes):
        strs = {e["name"]: e for e in n["inputs"]["string"]}
        if strs.get("GameDataNameBool", {}).get("value") != spot["flag"]:
            continue
        if n["name"] == "TriggerGameDataSetBoolTrue" and key and any(
                e["name"] == "IsDrive" and e["node"] == key[0] and e["plug"] == 0 for e in n["inputs"]["bool"]):
            sets += 1
        if n["name"] == "HoldGameDataGetBoolSimple":
            reads += 1
    if not sets:
        problems.append(f"{spot['logic']}: the key's Dead output doesn't set {spot['flag']}")
    if not reads:
        problems.append(f"{spot['logic']}: nothing reads {spot['flag']} back")
    return problems


SCENE_ROWS = os.path.join(HERE, "config", "scene_rows.json")
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"


def _event_file(fs, name):
    """The newest version of event file `name` (Name.110.bfevfl.zs over Name.bfevfl.zs), parsed."""
    from evfl import Evfl
    d = os.path.join(fs.root, "Event", "EventFlow")
    cands = sorted(f for f in os.listdir(d) if re.match(re.escape(name) + r"(\.\d{3})?\.bfevfl\.zs$", f))
    if not cands:
        return None
    return Evfl(fs.read("Event/EventFlow/" + cands[-1]))


def _reaches(fc, start, target):
    seen, stack = set(), [start]
    while stack:
        i = stack.pop()
        if i == 0xFFFF or i in seen or i >= len(fc["events"]):
            continue
        seen.add(i)
        if i == target:
            return True
        e = fc["events"][i]
        stack += [e[k] for k in ("next", "join") if k in e]
        stack += [c["next"] for c in e.get("cases", [])] + e.get("forks", [])
    return False


def _scene_gift_evidence(fs, group, spec, placements, new):
    """Checks one SCENE_GIFTS group against the game files and returns ([problem, ...], data for its drop_map entries).
    No problems means every file, step, flag and placement the plugin's scene edits name is there as expected."""
    from romtools import byml_load, murmur3_32, sarc_files
    problems, data = [], {"group": group}
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    bools = {int(e["Hash"]) for e in gd["Data"]["Bool"]}
    es = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}

    def bool_flag(name):
        if murmur3_32(name.encode()) not in bools:
            problems.append(f"{group}: no save-data Bool {name}")

    def last_step(file, after, entry=None, actor=None, need=()):
        ev = _event_file(fs, file)
        if ev is None:
            problems.append(f"{group}: no event file {file}")
            return
        fc = ev.flowcharts[0]
        names = {e["name"]: e for e in fc["events"]}
        e = names.get(after)
        if e is None or e["type"] != "action" or e["next"] != 0xFFFF:
            problems.append(f"{group}: {file} {after} is not a last step")
            return
        if entry is not None:
            ep = fc["entry_points"].get(entry)
            if ep is None or not _reaches(fc, ep["main"], e["idx"]):
                problems.append(f"{group}: {file} {after} is not reached from entry {entry}")
        actors = {a["name"] for a in fc["actors"] if not a["sub_name"]}
        for a in ((actor,) if actor else ()) + tuple(need):
            if a not in actors:
                problems.append(f"{group}: {file} has no actor {a}")

    if group == "gc_pot":
        pot = spec["pot"]
        hs = [h for h, xs in placements.items() for _, rel, a in xs if rel == pot["file"] and a.get("Gyaml") == pot["actor"]]
        if len(hs) != 1:
            problems.append(f"gc_pot: {len(hs)} {pot['actor']} placements in {pot['file']}")
        files = sarc_files(fs.read(pot["pack"]))
        holder = next((byml_load(b)[0] for n, b in files.items() if "ActorHolderParam" in n), {}) or {}
        slot = (holder.get("ActorHoldSettings") or {}).get(pot["slot"]) or {}
        if "Obj_Heart_Piece.engine__actor__ActorParam" not in str(slot.get("Actor")):
            problems.append(f"gc_pot: the pot's holder slot {pot['slot']} doesn't hold Obj_Heart_Piece")
        param = next((byml_load(b)[0] for n, b in files.items() if "GoronLargePotParameter" in n), {}) or {}
        if f"/{spec['give_scene']['entry']}.engine__event__EventSettingParam" not in str(param.get("HeartPieceDropEventName")):
            problems.append(f"gc_pot: the pot's HeartPieceDropEventName isn't {spec['give_scene']['entry']}")
        if spec["give_scene"]["entry"] not in es:
            problems.append(f"gc_pot: no scene ID {spec['give_scene']['entry']}")
        bool_flag(spec["flag"])
        bool_flag(spec["once"])
        last_step(spec["drop_scene"]["file"], spec["drop_scene"]["after"], actor=spec["drop_scene"]["actor"])
        last_step(spec["give_scene"]["file"], spec["give_scene"]["after"], entry=spec["give_scene"]["entry"],
                  need=("GameDataActor",))
        data.update({k: spec[k] for k in ("drop_scene", "give_scene", "flag", "once")})
        data["pot"] = {"file": pot["file"], "hash": hs[0] if len(hs) == 1 else None}
        return problems, data

    # zd_grotto
    rows = json.load(open(SCENE_ROWS, encoding="utf-8"))["rows"]
    row = spec["row"]
    if row not in rows:
        problems.append(f"zd_grotto: scene ID {row} is not in config/scene_rows.json")
    for r in (row, spec["copy_of"]):
        if r not in es:
            problems.append(f"zd_grotto: no scene ID {r}")
    bool_flag(f"HavePlayedEvent.{row}")
    rupees, stages = [], set()
    for n in spec["locations"]:
        e = new.get(n)
        if e is None or not e.get("placements") or any(p["actor"] != "Obj_Rupee_Blue" for p in e["placements"]):
            problems.append(f"zd_grotto: {n} isn't a placed blue rupee")
            continue
        for p in e["placements"]:
            rupees.append({"file": p["file"], "hash": p["hash"]})
            stages.add(_stage(p["file"]))
    triggers = []
    for st in sorted(stages):
        found = [{"file": rel, "hash": h} for h, xs in placements.items() for _, rel, a in xs
                 if _stage(rel) == st and a.get("Gyaml") == "EventRequestActor"
                 and (a.get("Dynamic") or {}).get("RequestEventName") == spec["copy_of"]]
        if len(found) != 1:
            problems.append(f"zd_grotto: {len(found)} {spec['copy_of']} requesters in {st}")
        triggers += found
    gone = {(r["file"], r["hash"]) for r in rupees}
    for rel in sorted({r["file"] for r in rupees}):
        root, _ = byml_load(fs.read(rel))
        for a in root.get("Actors", []):
            for link in a.get("Links") or []:
                if any((rel, str(link.get(k))) in gone for k in ("Src", "Dst")) and (rel, str(a.get("Hash"))) not in gone:
                    problems.append(f"zd_grotto: {rel}: {a.get('Gyaml')} links to a grotto rupee")
        for g in root.get("AiGroups") or []:
            if any((rel, str(x.get("Reference"))) in gone for x in g.get("References") or []):
                problems.append(f"zd_grotto: {rel}: logic {g.get('Logic')} names a grotto rupee")
    chests = sorted(({"file": rel, "hash": h} for h, xs in placements.items() for _, rel, a in xs
                     if (a.get("Dynamic") or {}).get("GetEventName") == row), key=lambda x: (x["file"], x["hash"]))
    sc = spec["scene"]
    ev = _event_file(fs, sc["file"])
    if ev is None or sc["vanilla"] not in ev.flowcharts[0]["entry_points"] \
            or "GameDataActor" not in {a["name"] for a in ev.flowcharts[0]["actors"]}:
        problems.append(f"zd_grotto: {sc['file']} lacks entry {sc['vanilla']} or a GameDataActor")
    data.update({"row": row, "copy_of": spec["copy_of"], "scene": sc, "once": f"HavePlayedEvent.{row}",
                 "triggers": triggers, "rupees": rupees, "row_chests": chests,
                 "order": list(spec["locations"])})
    return problems, data


GIFT_GRAPHS = {"gc_pot": ("Rando_GCPot_Remove", "Rando_GCPot_Give")}  # parity/_drops_gifts.py entry names


def plan_scene_gifts(plan, m=None):
    """{location: problem or None} for the scene gifts a patch plan makes (its "_notes_drops_scene_gifts"), read from
    the plan's sections (the gift's scene steps, and for the grotto rupees every placement deleted)."""
    m = m or _map()
    gifts = {}
    for x in plan.get("_notes_drops_scene_gifts", []):
        n = x.split(":")[0]
        e = (m.get("scene_gifts") or {}).get(n)
        gifts[n] = None if e else "not a scene gift in drop_map.json"
    graphs = {op.get("add_graph"): op for op in plan.get("events", []) if op.get("add_graph")}
    deleted = {(p["file"], str(p["hash"])) for p in plan.get("placements", []) if p.get("delete")}
    given = {x.split(":")[0] for x in plan.get("_notes_drops_scene_gifts", [])
             if not x.split(": ", 1)[-1].startswith("Nothing (")}  # OoTR's Nothing in "nothing" mode has no give step
    zd = sum(1 for n in gifts if ((m.get("scene_gifts") or {}).get(n) or {}).get("scene_gift", {}).get("group")
             == "zd_grotto" and n in given)
    for n in gifts:
        e = (m.get("scene_gifts") or {}).get(n)
        if e is None:
            continue
        g = e["scene_gift"]
        if g["group"] == "gc_pot":
            if not all(x in graphs for x in GIFT_GRAPHS["gc_pot"]):
                gifts[n] = "the pot's scene steps are missing from the plan"
        else:
            op = graphs.get(g["scene"]["entry"])
            if op is None or sum(1 for k in op["nodes"] if re.fullmatch(r"g\d+", k)) != zd:
                gifts[n] = "the grotto entry scene is missing from the plan, or gives another number of items"
            left = [p["hash"] for p in e.get("placements", []) if (p["file"], p["hash"]) not in deleted]
            if left:
                gifts[n] = f"its rupee placements stay ({left})"
    return gifts


def verify_scene_gifts(patch_dir, names, romfs=DEFAULT_ROMFS, m=None, nothing=()):
    """Reads a built patch back for scene gifts `names` (drop_map "scene_gifts" locations) and returns [problem, ...].
    `nothing` is the ones holding OoTR's Nothing with remake_empty_object_contents "nothing". Their scene gives nothing
    (no give step), but the pot's flag is still set."""
    from romtools import Romfs, byml_load
    m = m or _map()
    fs = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch_dir])
    problems = []
    by = defaultdict(list)
    for n in names:
        e = (m.get("scene_gifts") or {})[n]
        by[e["scene_gift"]["group"]].append(e)

    def entry_steps(file, entry):
        ev = _event_file(fs, file)
        fc = ev.flowcharts[0] if ev else None
        if fc is None or entry not in fc["entry_points"]:
            problems.append(f"{file}: no entry {entry}")
            return None, {}
        return fc, {e["name"]: e for e in fc["events"]}

    if by.get("gc_pot"):
        g = by["gc_pot"][0]["scene_gift"]
        remove, give = GIFT_GRAPHS["gc_pot"]
        d, s = g["drop_scene"], g["give_scene"]
        fc, ev = entry_steps(d["file"], remove)
        if fc:
            acts = [fc["actors"][x["actor"]]["actions"][x["action"]] for k, x in ev.items()
                    if k.startswith(remove) and x["type"] == "action"]
            if ev[d["after"]]["next"] != ev.get(f"{remove}_hide", {}).get("idx") or \
                    sorted(acts) != ["EventGoOffstageForUser", "EventTriggerRequestDeath"]:
                problems.append(f"{d['file']}: {d['after']} doesn't lead to the heart piece's removal")
        fc, ev = entry_steps(s["file"], give)
        empty = any(e is by["gc_pot"][0] for e in [(m.get("scene_gifts") or {}).get(n) for n in nothing])
        if fc and (ev[s["after"]]["next"] != ev.get(f"{give}_q", {}).get("idx") or (f"{give}_give" in ev) == empty
                   or f"{give}_flag" not in ev):
            problems.append(f"{s['file']}: {s['after']} doesn't lead to the give" + (" (Nothing: no give step "
                                                                                       "expected)" if empty else ""))
    if by.get("zd_grotto"):
        es = sorted(by["zd_grotto"], key=lambda e: e["scene_gift"]["index"])
        g = es[0]["scene_gift"]
        sc = g["scene"]
        fc, ev = entry_steps(sc["file"], sc["entry"])
        if fc:
            gives = [k for k in ev if re.fullmatch(re.escape(sc["entry"]) + r"_g\d+", k)]
            want = len(es) - len([n for n in nothing if (m.get("scene_gifts") or {}).get(n) in es])
            if len(gives) != want or ev.get(f"{sc['entry']}_entry", {}).get("entry_point") != sc["vanilla"]:
                problems.append(f"{sc['file']}: {sc['entry']} has {len(gives)} gives for {want} spots")
        row = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}.get(g["row"], {})
        if not str(row.get("FlowchartFileName", "")).endswith(f"/{sc['file']}.evfc") or row.get("EntryPointName") != sc["entry"]:
            problems.append(f"scene ID {g['row']} doesn't run {sc['file']}:{sc['entry']}")
        files = defaultdict(dict)
        for rel in sorted({t["file"] for t in g["triggers"]} | {p["file"] for e in es for p in e["placements"]}
                          | {c["file"] for c in g["row_chests"]}):
            files[rel] = {str(a.get("Hash")): a for a in byml_load(fs.read(rel))[0].get("Actors", [])}
        for t in g["triggers"]:
            a = files[t["file"]].get(t["hash"]) or {}
            if (a.get("Dynamic") or {}).get("RequestEventName") != g["row"]:
                problems.append(f"{t['file']}: the grotto entry requester {t['hash']} doesn't ask for {g['row']}")
        for e in es:
            for p in e["placements"]:
                if p["hash"] in files[p["file"]]:
                    problems.append(f"{p['file']}: grotto rupee {p['hash']} is still placed")
        for c in g["row_chests"]:
            a = files[c["file"]].get(c["hash"]) or {}
            if (a.get("Dynamic") or {}).get("GetEventName") == g["row"]:
                problems.append(f"{c['file']}: chest {c['hash']} still plays scene ID {g['row']}")
    return problems


def _second_pass(ctx):
    """Region files, absent OoTR locations, manual extras -> (new locations, logic overrides, warnings)."""
    drops, used, ootr, rules, logic = ctx["drops"], ctx["used"], ctx["ootr"], ctx["rules"], ctx["logic"]
    placements, flags, cat, params, file_types = (ctx["placements"], ctx["flags"], ctx["cat"], ctx["params"],
                                                  ctx["file_types"])
    add, placement_rows, category = ctx["add"], ctx["placement_rows"], ctx["category"]
    regions = {r["name"]: r for r in logic["regions"]}
    all_names = set(logic["locations"])
    warnings = []
    regfiles = load_region_files()

    def absent(n, why):
        if n in ootr and (n not in drops or (drops[n].get("mode") == "vanilla" and not drops[n].get("placements"))):
            drops[n] = {"type": ootr[n]["type"], "mode": "absent", "vanilla": ootr[n]["vanilla_item"],
                        "region": rules.get(n, (None,))[0], "why": why}

    # OoTR pairs that ended up vanilla (the remake object only exists for another age...). The object becomes a new
    # location of its own and the OoTR location is absent for the remake.
    freed = {}
    for n, e in list(drops.items()):
        if e.get("mode") == "vanilla" and e.get("placements") and "no_drop_key" not in (e.get("blockers") or []):
            for p in e["placements"]:
                used.discard(p["hash"])
                freed[p["hash"]] = (e.get("region"), e["why"])
            drops[n] = {"type": e["type"], "mode": "absent", "vanilla": e["vanilla"], "region": e.get("region"),
                        "why": f"no remake object can stand in for it ({e['why']}); the object is a new location"}

    # more pairs from the region files
    agent_obj = {}
    for area, v in regfiles.items():
        for h, o in v.get("objects", {}).items():
            agent_obj[h] = dict(o, area=area)
    def _hs(x):  # a pair's object is one hash, or a list of hashes (copies at one spot, e.g. one per age)
        return list(x) if isinstance(x, list) else [x]

    for area, v in sorted(regfiles.items()):
        for pr in v.get("pairs", []):
            names = [n for n in pr["ootr"] if n in ootr and (n not in drops or drops[n].get("mode") in ("vanilla", "absent")
                                                             and not drops[n].get("placements"))]
            hashes = [h for h in pr["hashes"] if all(x not in used and x in placements for x in _hs(h))]
            if len(names) != len(pr["ootr"]) or len(hashes) != len(pr["hashes"]) or len(names) != len(hashes):
                warnings.append(f"{area}: pair {pr['ootr']} skipped (names or objects already taken)")
                continue
            for n in names:
                drops.pop(n, None)
            add(area, names, hashes, pr["why"])
            for n, h in zip(names, hashes):
                extra = _or_rules([agent_obj.get(x, {}).get("rule", "True") for x in _hs(h)])
                if drops[n].get("mode") in ("full", "group") and extra not in ("True", drops[n].get("rule")):
                    drops[n]["extra_rule"] = _and(drops[n].get("extra_rule"), extra)
        for n, why in v.get("absent", {}).items():
            absent(n, why)
    for n, why in ABSENT.items():
        absent(n, why)
    for n, v in ootr.items():
        if v["type"] == "Wonderitem":
            absent(n, WONDER_WHY)
    # Objects. Everything unpaired becomes a new location.
    items = []  # (area, hash, region, rule, also, confidence, why)
    for h, o in agent_obj.items():
        items.append((o["area"], h, o["region"], o.get("rule") or "True", o.get("also") or [], o.get("confidence"),
                      o.get("why", "")))
    for area, hashes, region, rule, why in MANUAL_NEW:
        for h in hashes:
            items.append((area, h, region, rule, [], "high", why))
    for h, (region, why) in freed.items():
        if h not in agent_obj and region:
            items.append((obj_area(placements, h), h, region, "True", [], "medium",
                          f"in {region} (its OoTR pair's region; {why})"))
    # copies that take turns at one spot (one before a story step, the other after it) become one location holding every
    # copy, named by the first hash (the region files' "merge"). The respawn model's checked bit is per location.
    merged = {}
    for area, v in regfiles.items():
        for mg in v.get("merge", []):
            merged[mg["hashes"][0]] = ([x for x in mg["hashes"][1:] if x in placements], mg["why"])
    joined = {x for xs, _ in merged.values() for x in xs}
    new, new_hash = {}, {}
    seen = set()
    for area, h, region, rule, also, conf, why in items:
        if h in used or h in seen or h in joined:
            continue
        if h not in placements:
            warnings.append(f"{area}: object {h} not in the level files")
            continue
        seen.add(h)
        copies = [x for x in merged.get(h, ([], ""))[0] if x not in used]
        if copies:
            why = f"{why}; {merged[h][1]}"
            seen.update(copies)
        a = placements[h][0][2]
        c = category(h, a.get("Gyaml"))
        if c in FREESTANDING_CATS:
            if a.get("Gyaml") not in FREESTANDING_WORD:
                continue  # heart pieces/containers and keys are handled as OoTR locations
            c = "freestanding"
        if c == "crate" and a.get("Gyaml") == "Obj_BrokenBox_A_03":
            c = "small_crate"
        if c not in CATEGORY:
            warnings.append(f"{area}: object {h} ({a.get('Gyaml')}, {c}) has no location category")
            continue
        if region not in regions:
            warnings.append(f"{area}: object {h}: unknown OoTR region {region!r}")
            continue
        otype, setting, base, word = CATEGORY[c]
        rows = placement_rows([h] + copies)
        kind = "freestanding" if c == "freestanding" else "drop"
        blockers = []
        if kind == "drop" and "Drop__DropActor" not in params.allowed(a.get("Gyaml")) and \
                a.get("Gyaml") not in DROP_COMPONENT:  # (the patch gives those a Drop component)
            warnings.append(f"{area}: object {h} ({a.get('Gyaml')}) declares no Drop__DropActor: not a location")
            continue
        if any(r["flag"] is None for r in rows):
            if kind == "freestanding":
                continue
            blockers.append("no_flag")
        if any(r["reset_group"] for r in rows):
            blockers.append("reset_group")
        ages = set()
        for r in rows:
            ages |= {"child", "adult"} if r["age"] == "both" else {"adult" if r["age"] == "adult_alt" else r["age"]}
        age_rule = f"is_{next(iter(ages))}" if len(ages) == 1 else "True"
        never = [AGE_NEVER.get(x, {}).get(next(iter(ages))) for x in [region] + list(also)] if len(ages) == 1 else []
        if never and all(never):  # one age only, in regions that age never reaches, so not a location (AGE_NEVER)
            ctx["age_never_out"][h] = {"region": region, "age": next(iter(ages)), "why": never[0]}
            continue
        if h in SPOT_RULES:
            rule = _and(rule, SPOT_RULES[h][0])
            why = f"{why}; {SPOT_RULES[h][1]}"
        events = [f"Remake Drops Reach {x}" for x in also if x in regions and x != region]
        rule = mode_safe(rule)
        base = ACTOR_BASE_RULE.get(a.get("Gyaml"), base)
        layout = _layout_rule(rows)
        full_rule = _and(age_rule, base, rule, *[f"'{e}'" for e in events])
        if layout and layout != "missable":
            full_rule = _and(full_rule, layout)
            why = f"{why}; only some adult layouts hold it: {layout}"
        word = word or FREESTANDING_WORD[a.get("Gyaml")]
        e = {"type": otype, "category": c, "area": area, "region": region, "rule": full_rule, "spot_rule": rule,
             "also": [x for x in also if x in regions and x != region], "events": events,
             "confidence": conf or "medium", "why": why, "kind": kind, "setting": setting,
             "dungeon": regions[region].get("dungeon"), "vanilla": _vanilla_item(c, otype, rows),
             "placements": rows, "ages": sorted(ages), "blockers": sorted(set(blockers)), "word": word,
             "respawns": bool(blockers) or c == "gold_skulltula"}
        if any(r["age"] == "adult_alt" for r in rows) and all(r["age"] == "adult_alt" for r in rows):
            e["why"] += "; only in the _Adult_Alternative layout"
        if layout == "missable":  # only in an adult layout that goes away, so junk only (the plugin disables it)
            e["missable"] = True
            e["why"] += "; missable: only in an adult layout that is replaced for good (ALT_LAYOUTS)"
        if kind == "freestanding":
            e["allowed_actors"] = _allowed_actors(rows, file_types)
        new_hash[h] = e
    # names are "<region> <word> <n>", numbered north to south, west to east, and never an OoTR name
    by = defaultdict(list)
    for h, e in new_hash.items():
        by[(e["region"], e["word"])].append(h)
    taken = set(all_names)
    # We reuse the names in drop_map.json's "new" section and give new objects unused numbers, so adding a kind of drop
    # to a region doesn't renumber its existing checks.
    prev = {}
    if os.path.exists(OUT):
        for n, e in (json.load(open(OUT, encoding="utf-8")).get("new") or {}).items():
            if e.get("placements"):
                prev[str(e["placements"][0]["hash"])] = n
    for (region, word), hs in sorted(by.items()):
        for h in list(hs):
            n = prev.get(h)
            if n and n not in taken and n.startswith(f"{region} {word} "):
                taken.add(n)
                new[n] = new_hash[h]
                hs.remove(h)
    for (region, word), hs in sorted(by.items()):
        hs.sort(key=lambda h: (round(new_hash[h]["placements"][0]["pos"][2], 1),
                               round(new_hash[h]["placements"][0]["pos"][0], 1), h))
        i = 0
        for h in hs:
            while True:
                i += 1
                name = f"{region} {word} {i}"
                if name not in taken:
                    break
            taken.add(name)
            new[name] = new_hash[h]
    # logic overrides
    reg = defaultdict(lambda: {"locations": {}, "events": {}})
    for n, e in drops.items():
        if e.get("mode") == "absent" and e.get("region") in regions \
                and n in (regions[e["region"]].get("locations") or {}):
            reg[e["region"]]["locations"][n] = None
    for n, (old, region, rule) in RULE_MOVES.items():
        if drops.get(n, {}).get("mode") in ("full", "group"):
            reg[old]["locations"][n] = None
            reg[region]["locations"][n] = rule
            drops[n].update(region=region, rule=rule, why=drops[n]["why"] + f"; OoTR's rule moved to {region}: {rule}")
    newloc = {}
    tags = _region_tags(logic)
    for name, e in new.items():
        reg[e["region"]]["locations"][name] = e["rule"]
        for ev, x in zip(e["events"], e["also"]):
            reg[x]["events"][ev] = "True"
        newloc[name] = {"type": e["type"], "vanilla_item": e["vanilla"],
                        "filter_tags": tags.get(e["region"], []) + [TYPE_TAG.get(e["type"], "Remake Drops")],
                        "scene": None, "default": None}
    for loc, where in NO_BOTTLED_FAIRY.items():  # no bottled fairy from gossip stones or bean plants
        for r in where:
            if r in regions:
                reg[r]["locations"][loc] = "False"
    logic_out = {"_about": "Written by tools/rando/drops.py (do not edit): the remake's drop objects as OoTR locations "
                           "(new_locations, placed by region rule), OoTR drop locations absent from the remake (null) "
                           "and moved rules; the remake's helper definitions (REMAKE_HELPERS) and its unbottled fairies "
                           "(NO_BOTTLED_FAIRY). Evidence per location: data/rando/drop_map.json ('new', 'drops').",
                 "helpers": dict(REMAKE_HELPERS),
                 "regions": {r: {k: v for k, v in s.items() if v} for r, s in sorted(reg.items())},
                 "new_locations": dict(sorted(newloc.items()))}
    ctx["new_of_hash_out"].update({p["hash"]: n for n, e in new.items() for p in e["placements"]})
    return new, logic_out, warnings


TYPE_TAG = {"Pot": "Pots", "Crate": "Crates", "SmallCrate": "Crates", "FlyingPot": "Pots", "Beehive": "Beehives",
            "Freestanding": "Freestandings", "GS Token": "Skulltulas", "RemakeGrass": "Grass", "RemakeRock": "Rocks",
            "RemakeBoulder": "Rocks", "RemakeMisc": "Remake Drops"}


def _region_tags(logic):
    """OoTR filter tags (area names) per region, from the region's own locations."""
    groups = {"Pots", "Crates", "Beehives", "Freestandings", "Skulltulas", "Chests", "NPCs", "Cows", "Shops",
              "Deku Scrubs", "Grottos", "Wonderitems", "Gossip Stones", "Songs", "Rupee Towers", "Silver Rupees",
              "Master Quest", "Vanilla Dungeons", "Dungeon Rewards", "Pieces of Heart", "Heart Containers"}
    by_loc = {n: v.get("categories") or [] for n, v in logic["locations"].items()}
    out = {}
    for r in logic["regions"]:
        for n in (r.get("locations") or {}):
            t = [c for c in by_loc.get(n, []) if c not in groups and "MQ" not in c]
            if t:
                out.setdefault(r["name"], t)
                break
    return out


def obj_area(placements, h):
    return placements[h][0][0] if h in placements else None


# Build
def build(romfs=DEFAULT_ROMFS, write=True):
    placements, file_types, flags, params = _load_game(romfs)
    cat = _catalogue()
    for h, xs in placements.items():  # EXTRA_CATEGORY adds icicles, red ice and silver rocks, takes non-locations out
        g = xs[0][2].get("Gyaml")
        if g in EXTRA_CATEGORY:
            if EXTRA_CATEGORY[g] is None or any(area in NOT_LOCATION_AREAS for area, _, _ in xs) or (
                    g == "Obj_LiftRock_B_01" and all("_Child" in rel for _, rel, _ in xs)) or (  # no child can lift it
                    g == "Animal_ButterflyToFairy" and all(_age(rel) in ("adult", "adult_alt") for _, rel, _ in xs)):
                cat.pop(h, None)  # (and only a child has Deku Sticks to turn a butterfly into a fairy)
            else:
                cat[h] = dict(cat.get(h) or {}, category=EXTRA_CATEGORY[g])
        elif any(area in NOT_LOCATION_AREAS for area, _, _ in xs) and (cat.get(h) or {}).get("category") in (
                "grass_always_respawn", "pot_always_respawn", "tree"):
            cat.pop(h, None)
    logic = json.load(open(LOGIC, encoding="utf-8"))
    rules = {}
    for region in logic["regions"]:
        for name, rule in (region.get("locations") or {}).items():
            rules.setdefault(name, (region["name"], rule))
    ootr = {n: v for n, v in logic["locations"].items() if v["type"] in TYPES and v.get("regions")}

    def category(h, actor):
        if actor == "Enemy_Skulltula_Gold":
            return "gold_skulltula"
        if h in cat:
            return cat[h]["category"]
        if actor in PICKUP_TYPES:
            return "freestanding"
        return None

    def obj(h):
        xs = placements.get(h)
        if not xs:
            raise SystemExit(f"drops: no placement with hash {h} (game files changed?)")
        return xs

    by_kind = defaultdict(list)  # (area, Gyaml) -> [hash]
    for h, xs in placements.items():
        by_kind[(xs[0][0], xs[0][2].get("Gyaml"))].append(h)

    def twins(h):
        """Copies of the same object in the other files of its area (other age / Alternative): same type, same spot."""
        area, rel0, a0 = obj(h)[0]
        files = {rel for _, rel, _ in obj(h)}
        out = []
        for h2 in by_kind[(area, a0.get("Gyaml"))]:
            if h2 == h or any(rel in files for _, rel, _ in placements[h2]):
                continue
            if math.dist(placements[h2][0][2].get("Translate", [0, 0, 0]), a0.get("Translate", [0, 0, 0])) <= 0.35:
                out.append(h2)
        return out

    def placement_rows(hashes):
        rows = []
        for h in hashes:
            for area, rel, a in obj(h):
                dyn = a.get("Dynamic") or {}
                r = cat.get(h) or {}
                rows.append({"file": rel, "hash": h, "actor": a.get("Gyaml"), "age": _age(rel),
                             "category": category(h, a.get("Gyaml")),
                             "drop": dyn.get("Drop__DropActor"), "drop_table": dyn.get("Drop__DropTable"),
                             "dynamic_keys": sorted(dyn), "flag": flags.get(h),
                             "reset_group": r.get("reset_group") or None,
                             "pos": [round(x, 2) for x in a.get("Translate", [0, 0, 0])]})
        return rows

    drops, used = {}, set()

    def make_entry(name, hashes, why, group=None, mode=None):
        loc = ootr[name]
        region, rule = rules.get(name, (None, None))
        rows = placement_rows(hashes)
        kind = "freestanding" if rows[0]["category"] in FREESTANDING_CATS else "drop"
        ages = set()
        for r in rows:
            ages |= {"child", "adult"} if r["age"] == "both" else ({r["age"]} if r["age"] != "adult_alt" else set())
        need = _rule_age(rule)
        entry = {"type": loc["type"], "area": rows[0]["file"].split("/")[1], "mode": mode, "why": why,
                 "vanilla": loc["vanilla_item"], "region": region, "rule": rule, "kind": kind,
                 "placements": rows, "ages": sorted(ages)}
        if group:
            entry["group"] = group
        if need and need not in ages:
            entry.update(mode="vanilla", why=f"the remake object exists only for {', '.join(sorted(ages)) or 'no age'}, "
                                             f"OoTR's location is {need}-only ({why})")
            return entry
        if not need and ages != {"child", "adult"}:
            only = next(iter(ages)) if len(ages) == 1 else None
            if only:
                entry["extra_rule"] = f"is_{only}"
                entry["why"] += f"; the remake object exists only for the {only}: AND is_{only} to the OoTR rule"
        if any(r["age"] == "adult_alt" for r in rows):
            entry["why"] += "; the adult copy is only in the _Adult_Alternative layout (its story state is unverified, so not counted)"
        layout = _layout_rule(rows)
        if layout == "missable":
            entry["missable"] = True
            entry["why"] += "; missable: its adult copy is only in an adult layout replaced for good (ALT_LAYOUTS)"
        elif layout:
            entry["extra_rule"] = _and(entry.get("extra_rule"), layout)
            entry["why"] += f"; only some adult layouts hold it: {layout}"
        blockers = []
        for r in rows:
            if r["flag"] is None:
                blockers.append("no_flag")
            if r["reset_group"]:
                blockers.append("reset_group")
            if kind == "drop" and "Drop__DropActor" not in params.allowed(r["actor"]):
                blockers.append("no_drop_key")
        entry["blockers"] = sorted(set(blockers))
        if "no_drop_key" in entry["blockers"] or (kind == "freestanding" and "no_flag" in entry["blockers"]):
            entry.update(mode="vanilla", why=f"{why}; but {' and '.join(entry['blockers'])}: the object cannot hold "
                                             f"an item, or a swapped pickup would come back on every visit")
        if kind == "freestanding":
            entry["allowed_actors"] = _allowed_actors(rows, file_types)
        return entry

    def add(area, names, objects, why):
        names = [n for n in names if n]
        for n in names:
            if n not in ootr:
                raise SystemExit(f"drops: {n} is not an OoTR location of the handled types")
        pairs = list(zip(names, objects))
        resolved = []
        for n, o in pairs:
            if isinstance(o, list):
                hashes = list(o)
            else:
                hashes = [o] + twins(o)
                need = _rule_age(rules.get(n, (None, None))[1])
                if need:  # keep the other-age copies only if the rule allows that age
                    hashes = [h for h in hashes if h == o or _age(obj(h)[0][1]) in (need, "both")]
            for h in hashes:
                if h in used:
                    raise SystemExit(f"drops: {h} paired twice")
                if obj(h)[0][0] != area:
                    raise SystemExit(f"drops: {h} is in {obj(h)[0][0]}, not {area}")
            used.update(hashes)
            resolved.append((n, hashes))
        same = len({rules.get(n) for n, _ in resolved}) == 1
        mode = "full" if len(resolved) == 1 or same else "group"
        why_full = why + ("; same region and rule for all of them, so any pairing is right" if len(resolved) > 1 and same else "")
        gid = f"{area}:{resolved[0][0]}" if mode == "group" and resolved else None
        for n, hashes in resolved:
            drops[n] = make_entry(n, hashes, why_full if mode == "full" else why + "; which is which unknown", gid, mode)
        if mode == "group" and len({tuple(drops[n].get("ages", ())) for n, _ in resolved}) > 1:
            for n, _ in resolved:  # a group can't mix single-age objects, its rule can't say which is which
                drops[n].update(mode="vanilla", why=drops[n]["why"] + "; but the group mixes objects of different ages")
        for n in names[len(objects):]:
            drops[n] = {"type": ootr[n]["type"], "mode": "vanilla", "vanilla": ootr[n]["vanilla_item"],
                        "why": why if not objects else
                        f"{len(names)} OoTR vs {len(objects)} remake objects ({why}); this one has no counterpart"}

    for area, names, objects, why in PAIRS:
        add(area, names, objects, why)
    for area, names, sel, why in SELECTIONS:
        found = []
        for h, xs in placements.items():
            ar, rel, a = xs[0]
            x, _, z = a.get("Translate", [0, 0, 0])
            x0, x1, z0, z1 = sel["box"]
            if ar == area and category(h, a.get("Gyaml")) == sel["category"] and _age(rel) == sel["age"] \
                    and x0 <= x <= x1 and z0 <= z <= z1 and h not in sel.get("exclude", ()) and h in flags \
                    and h not in used:
                found.append(h)
        found.sort(key=lambda h: (round(obj(h)[0][2]["Translate"][2], 1), round(obj(h)[0][2]["Translate"][0], 1)))
        add(area, names, [[h] for h in found], f"{why}: {len(found)} in the remake, {len(names)} in OoTR")

    new_of_hash_out, age_never_out = {}, {}
    new, logic_out, warnings = _second_pass(locals())
    new_of_hash = new_of_hash_out

    for n, loc in ootr.items():
        if n in drops:
            continue
        why = next((w for rx, w in VANILLA_WHY if re.search(rx, n)), DEFAULT_WHY)
        drops[n] = {"type": loc["type"], "mode": "vanilla", "vanilla": loc["vanilla_item"], "why": why}
        if n in BLOCKED:
            drops[n].update(mode="blocked", why=BLOCKED[n])
        elif n in ELSEWHERE or re.search(r"Freestanding Key$|Jail Gerudo Key$", n):
            drops[n].update(mode="elsewhere", why=ELSEWHERE.get(n, "a small key: the dungeons plugin (tools/rando/"
                                                                   "parity/dungeons.py) handles keys"))

    # remake-only objects that could hold a one-time item, meaning they have a save flag and a drop key (or a pickup to
    # swap)
    extras = {}
    drop_cats = {"pot", "crate", "beehive", "grass", "rock_liftable", "rock_bombable", "flying_pot", "palm_fruit",
                 "gerudo_decoration"}
    for h, xs in sorted(placements.items()):
        if h in used:
            continue
        area, rel, a = xs[0]
        c = category(h, a.get("Gyaml"))
        if c not in drop_cats | {"freestanding_rupee_heart", "freestanding"} or area == "DreamWorld":
            continue
        if h not in flags:
            continue
        rows = placement_rows([h])
        kind = "drop" if c in drop_cats else "freestanding"
        if kind == "drop" and "Drop__DropActor" not in params.allowed(a.get("Gyaml")):
            continue
        if kind == "freestanding" and a.get("Gyaml") not in FREESTANDING_TARGETS:
            continue
        e = {"area": area, "category": c, "kind": kind, "placements": rows,
             "ages": sorted({"child", "adult"} if rows[0]["age"] == "both" else {rows[0]["age"]}),
             "blockers": ["reset_group"] if rows[0]["reset_group"] else []}
        if kind == "freestanding":
            e["allowed_actors"] = [t for t in FREESTANDING_TARGETS if all(t in file_types[r["file"]] for r in rows)]
        if h in new_of_hash:
            e["location"] = new_of_hash[h]  # the new OoTR location this object is (appearance cues read it)
        elif h in age_never_out:
            e["not_a_location"] = age_never_out[h]  # its age never reaches its region (AGE_NEVER)
        extras[f"{area}/{c}/{h}"] = e

    # placed heart pieces and heart containers give any item through the shared get scene (GET_SCENE_* below)
    hearts = sorted(n for n, e in drops.items() if e.get("kind") == "freestanding" and e.get("mode") in ("full", "group")
                    and e["placements"] and all(p["actor"] in GET_SCENE_TYPES for p in e["placements"]))
    for k, n in enumerate(hearts):
        tag = GET_SCENE_TAG_BASE + k
        drops[n]["get_scene"] = {"tag": tag, "name": f"{GET_SCENE_NAME}{tag:02d}",
                                 "pack": GET_SCENE_TYPES[drops[n]["placements"][0]["actor"]]}
    # other placed pickups whose level file also places a heart. An item no type swap can show turns them into that
    # heart ("as"), and it's given through the get scene the same way (the rupees at the Lake Hylia bottom, six Deku
    # Tree spots).
    tag = GET_SCENE_TAG_BASE + len(hearts)
    for sec in (drops, new):
        for n in sorted(sec):
            e = sec[n]
            if e.get("kind") != "freestanding" or "get_scene" in e or not usable(e):
                continue
            heart = next((t for t in ("Obj_Heart_Piece", "Obj_Heart_Container") if t in e.get("allowed_actors", [])),
                         None)
            if heart is None:
                continue
            e["get_scene"] = {"tag": tag, "name": f"{GET_SCENE_NAME}{tag:02d}", "pack": GET_SCENE_TYPES[heart],
                              "as": heart}
            tag += 1
    # remake_touch_pickups "any". A level is a stage, and its _Static and _Dynamic files load
    # together (one Banc scene per GameBancParam).
    # This is for the auto-collected rupees and hearts whose own file places no other pickup type ("only their own kind
    # fits"). "stage_actors" is the pickup types every stage holding the spot places, and "stage_get_scene" is the heart
    # that stage places (the Zora's Fountain and Dampe's-race green rupees, the Deku Tree and Fire Temple hearts). The
    # plugin only uses them with that setting on.
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    stage_types = defaultdict(set)
    for rel, ts in file_types.items():
        stage_types[_stage(rel)] |= ts
    hearts_alike = {"Obj_Heart", "Obj_Heart_InWater"}
    late = []  # spots whose own file places other pickup types too, tagged after the disguise
    for sec in (drops, new):
        for n in sorted(sec):
            e = sec[n]
            if e.get("kind") != "freestanding" or "get_scene" in e or not usable(e):
                continue
            own = {p["actor"] for p in e["placements"]}
            if own & hearts_alike:
                own |= hearts_alike
            if not set(e.get("allowed_actors", [])) <= own:
                # Other pickup types already fit these, so on their own they'd only be type swaps kept to junk (with the
                # plugin pre-placing a fitting pool item). They take the stage's heart and the get scene too whenever
                # the stage places one. Their tags come after every older one (late), so no older spot's tag moves.
                late.append(e)
                continue
            stages = sorted({_stage(p["file"]) for p in e["placements"]})
            st = [t for t in FREESTANDING_TARGETS if all(t in stage_types[s] for s in stages)]
            if st != e.get("allowed_actors"):
                e["stage_actors"] = st
            heart = next((t for t in ("Obj_Heart_Piece", "Obj_Heart_Container") if t in st), None)
            if heart is None:
                continue
            e["stage_get_scene"] = {"tag": tag, "name": f"{GET_SCENE_NAME}{tag:02d}", "pack": GET_SCENE_TYPES[heart],
                                    "as": heart}
            tag += 1
    # remake_freestanding_keys "any", the two freestanding keys that their room logic saves (KEY_SPOTS). The full
    # entries are here, and "drops" keeps them "elsewhere" so nothing changes with the setting off.
    key_spots = {}
    for n, spot in sorted(KEY_SPOTS.items()):
        problems = _key_spot_evidence(fs, spot)
        if problems:
            warnings += problems
            continue
        region, rule = rules.get(n, (None, None))
        rows = placement_rows([spot["hash"]])
        ages = sorted({"child", "adult"} if all(r["age"] == "both" for r in rows) else {r["age"] for r in rows})
        key_spots[n] = {"type": ootr[n]["type"], "area": spot["area"], "mode": "full", "vanilla": ootr[n]["vanilla_item"],
                        "region": region, "rule": rule, "kind": "freestanding", "placements": rows, "ages": ages,
                        "blockers": [], "allowed_actors": ["Obj_Dungeon_SmallKey"],
                        "saved_by": {"logic": spot["logic"], "flag": spot["flag"]},
                        "why": f"{drops[n]['why']}; saved by its room logic ({spot['logic']}: the key's Dead output "
                               f"sets {spot['flag']}, which keeps it from coming back)",
                        "get_scene": {"tag": tag, "name": f"{GET_SCENE_NAME}{tag:02d}", "pack": KEY_PACK,
                                      "ai": KEY_AI}}
        tag += 1
    # remake_gc_pot_prize / remake_zd_grotto_rupees (SCENE_GIFTS). Full entries for the spots a scene of their own
    # gives, while "drops" / "new" keep their old entries so nothing changes with the settings at their first value.
    scene_gifts = {}
    for group, spec in SCENE_GIFTS.items():
        problems, data = _scene_gift_evidence(fs, group, spec, placements, new)
        if problems:
            warnings += problems
            continue
        for i, n in enumerate(spec["locations"]):
            if group == "gc_pot":
                region, rule = rules.get(n, (None, None))
                base = drops[n]
                scene_gifts[n] = {"type": base["type"], "area": spec["area"], "mode": "full", "vanilla": base["vanilla"],
                                  "region": region, "rule": rule, "kind": "scene", "placements": [],
                                  "ages": ["child"], "blockers": [], "confidence": "high",
                                  "why": "the pot's heart-piece scene gives the item: Dm_Goron_0045 removes the "
                                         "dropped heart piece (PickedUp death), GoronCity_LargePot sets "
                                         f"{spec['flag']} (the pot offers the heart piece only while it is false) "
                                         "and gives the item",
                                  "scene_gift": data}
            else:
                scene_gifts[n] = dict(new[n], kind="scene", scene_gift=dict(data, index=i),
                                      why="given on the first entry into the grotto (OoTR: rule True inside the "
                                          "grotto region): the grotto's entry requester asks for scene ID "
                                          f"{data['row']}, which plays the vanilla entry and then, once, the six "
                                          "items; the rupee placements are deleted")
    # the disguised ice trap's carrier, only placed at the GV waterfall spot and dropped by nothing
    gv = [n for n, e in drops.items() if any(p["actor"] == DISGUISE_ACTOR for p in e.get("placements", []))]
    carriers = {h for h, xs in placements.items() if any(a.get("Gyaml") == DISGUISE_ACTOR for _, _, a in xs)}
    named = {h for h, xs in placements.items() for _, _, a in xs
             if DISGUISE_ACTOR in json.dumps(a.get("Dynamic") or {}, default=str)}
    disguise = None
    if len(gv) == 1 and carriers == {p["hash"] for p in drops[gv[0]]["placements"]} and not named:
        disguise = {"actor": DISGUISE_ACTOR, "pack": DISGUISE_PACK, "tag": tag, "spot": gv[0]}
    else:
        warnings.append(f"disguise carrier {DISGUISE_ACTOR}: placed or dropped elsewhere too ({sorted(carriers)}, "
                        f"{sorted(named)}); not used")
    tag += 1  # the disguise's tag, the late stage hearts come after it
    new_type = []
    for e in late:  # freestanding spots that can also swap among rupees, in a stage that places a heart
        stages = sorted({_stage(p["file"]) for p in e["placements"]})
        st = [t for t in FREESTANDING_TARGETS if all(t in stage_types[s] for s in stages)]
        heart = next((t for t in ("Obj_Heart_Piece", "Obj_Heart_Container") if t in st), None)
        if heart is None:
            if e.get("area") in NEW_TYPE_HEART:
                new_type.append((e, st))
            continue
        if st != e.get("allowed_actors"):
            e["stage_actors"] = st
        e["stage_get_scene"] = {"tag": tag, "name": f"{GET_SCENE_NAME}{tag:02d}", "pack": GET_SCENE_TYPES[heart],
                                "as": heart}
        tag += 1
    for e, st in new_type:  # Kokiri Forest has no vanilla heart in this stage.
        heart = NEW_TYPE_HEART[e["area"]]  # it gets a new heart-piece type once the in-game probe passes
        # A test build can request the probe early (parity/_test_start.py).
        e["stage_actors"] = sorted(set(st) | set(e.get("allowed_actors", [])) | {heart})  # (its own file's types too)
        e["stage_get_scene"] = {"tag": tag, "name": f"{GET_SCENE_NAME}{tag:02d}", "pack": GET_SCENE_TYPES[heart],
                                "as": heart, "new_type": True}
        tag += 1
    if tag >= SCENE_DROP_TAG0:
        raise DropPlanError(f"get-scene tags reach {tag}: they would meet the scene-drop tags ({SCENE_DROP_TAG0}+)")
    # (NEW_TYPE_HEART: see its definition)
    dropper_types = {p["actor"] for sec in (drops, new) for e in sec.values() if e.get("kind") == "drop"
                     for p in e.get("placements", [])}
    dropper_types |= {p["actor"] for e in extras.values() if e.get("kind") == "drop" for p in e["placements"]}

    tables = _dropper_tables(fs, dropper_types)
    # bug objects are drop-map locations whose objects give bugs in vanilla (with their region from the region files)
    bug_objects = {}
    for sec in (drops, new):
        for n, e in sorted(sec.items()):
            rows = e.get("placements") or []
            if e.get("kind") == "drop" and rows and e.get("region") and all(
                    p.get("drop") == BUG_TYPE or (not p.get("drop") and not p.get("drop_table")
                                                  and tables.get(p["actor"], {}).get("default_bugs")) for p in rows):
                bug_objects[n] = e["region"]
    bug_permanent = []
    for src in BUG_SOURCES:
        hashes = sorted(h for h, xs in placements.items() if any(
            a.get("Gyaml") == src["type"] and (a.get("Dynamic") or {}).get("Drop__DropActor") == BUG_TYPE
            and h not in flags for _, _, a in xs))
        if not hashes:
            warnings.append(f"bug source {src['type']}: no placement dropping {BUG_TYPE} without a save flag")
            continue
        bug_permanent.append(dict(src, hashes=hashes))
    bugs = {"objects": bug_objects, "permanent": bug_permanent}

    actor_keys = {t: sorted(params.allowed(t)) for t in FREESTANDING_TARGETS}
    counts = summarize(drops, extras, new)
    out = {"_about": __doc__.strip().splitlines()[0], "romfs": romfs, "counts": counts,
           "drops": dict(sorted(drops.items())), "new": dict(sorted(new.items())), "extras": extras,
           "actor_keys": actor_keys, "warnings": warnings,
           "key_spots": key_spots, "scene_gifts": scene_gifts, "disguise": disguise, "dropper_tables": tables,
           "bugs": bugs}
    for secs in logic_out["regions"].values():  # every rule written, also moved and audit-derived ones
        for ch in secs.values():
            for k, v in ch.items():
                ch[k] = mode_safe(v)
    if write:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        json.dump(logic_out, open(LOGIC_OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out


def summarize(drops, extras, new=None):
    by = defaultdict(lambda: defaultdict(int))
    for v in drops.values():
        by[v["type"]][v["mode"]] += 1
        if v["mode"] not in ("vanilla", "absent") and v.get("blockers"):
            by[v["type"]]["of which reset_group"] += "reset_group" in v["blockers"]
    ex = defaultdict(int)
    for v in extras.values():
        ex[v["category"]] += 1
    nw = defaultdict(lambda: defaultdict(int))
    for v in (new or {}).values():
        nw[v["type"]][v["confidence"]] += 1
    return {"ootr": {t: dict(m) for t, m in sorted(by.items())}, "extras": dict(sorted(ex.items())),
            "new": {t: dict(m) for t, m in sorted(nw.items())}}


# Plan
_MAP = None


def _map():
    global _MAP
    if _MAP is None:
        _MAP = json.load(open(OUT, encoding="utf-8"))
    return _MAP


class DropPlanError(ValueError):
    pass


# allow=(...) switches for plan_ops / usable:
#   "reset_group"             objects a SupplyItemResetSystemActor also resets. The plan format can't take them out
#                             of the group (that needs U64 list edits), so the object may come back and drop the
#                             item again.
#   "token_outside_skulltula" a Gold Skulltula Token in a pot/crate/grass... The token normally saves its
#                             skulltula's flag (GoldTokenGmdHash), and with no skulltula behind it that's untested.
#   "checked_on_pickup"       remake_drop_contents "all". Spots picks_up_checked accepts take items with a
#                             save-on-take pickup, and plan_ops adds the AI-graph pipeline (pickup_save_ops).
# What decides "checked" in vanilla: only a Gold Skulltula's own token saves its
# dropper's flag on pickup, because the skulltula's AI hands its hash to the token (GoldTokenGmdHash). Nothing hands
# a pot's, crate's or rock's hash to what it drops (no data file or code writes the heart piece's RespawnGmdHash). So
# everything else is "checked" when the object breaks (its own flag, made permanent) or never (the object respawns),
# unless "checked_on_pickup" adds that hand-over. Without it there are two kinds of spot for an item:
#   once     the object stays broken (flag 24, made so or vanilla). The item drops once, and a dropped item the
#            player leaves behind is gone. Junk, and in remake_drop_contents "all" anything with a pickup.
#   respawn  the object comes back (area reset kept, reset group, no flag, a skulltula dropping something else).
#            It's never lost and may be picked up again. Only items whose second pickup changes nothing
#            (REPEATABLE_*).
# Placed (freestanding) pickups save their own flag when taken, so they're never lost and never repeat.
REPEATABLE_JUNK = {"Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Heart", "Obj_Fairy", "Obj_Shield_Deku",
                   "Obj_Shield_Hylian"}
ONCE_JUNK = {"Obj_Rupee_Purple", "Obj_Rupee_Gold"}  # worth farming: one-time spots only
# progression items with a world pickup whose second pickup changes nothing (owned equipment / magic arrow)
REPEATABLE_ITEMS = {"Goron Tunic", "Zora Tunic", "Fire Arrows"}
# respawn-spot blockers the plan can live with (the item rule keeps once-items out of them)
RESPAWN_BLOCKERS = ("reset_group", "no_flag")


def spot_respawns(entry):
    """True if the object comes back after it drops its item (so only repeatable items may go there)."""
    if entry.get("kind") == "freestanding":
        return False
    rows = entry.get("placements", [])
    if any(r["category"] == "gold_skulltula" for r in rows):
        return True  # it comes back until its token is taken, only the token saves it
    return any(r["flag"] is None or r.get("reset_group") for r in rows)


# Checked on pickup (AI graph edits)
# OoTR counts a pot, crate or skulltula as checked once its item is collected. The remake can do the same with the
# Gold Skulltula's own pipeline, now that we can edit AI graphs (tools/ainb.py):
#  1. The dropper's AI hands its own save-flag hash to what it drops. That's the skulltula's three nodes
#     (QueryGenericMakeOverwriteParam -> QueryBlackboardOverwriteParamAddNoRespawnGmdHash ->
#     OneShotDropSetOverWriteParam) copied into the dropper's root graph, with a second key so either kind of
#     pickup takes it, GoldTokenGmdHash for tokens and RespawnGmdHash for everything else.
#  2. The pickup saves that hash (and hash ^ 2) when it's taken. That's the heart piece's death branch
#     (QueryDeathIsDead -> case 10 -> OneShotHeartPieceTakenDeadAfter + ExecuteDeathSignalDeathProcedure) copied
#     into the pickup's AI, plus case 4 (PickedUp, since rupees, hearts and the like are collected directly and not
#     through the get scene). The u64 blackboard key RespawnGmdHash gets added to its blackboard table. The node
#     skips a missing or 0 key (main 0x28E2DD0), so every other pickup of the type is unaffected.
#  3. The respawn model (CHECKED_ARRAY) replaced this step. Breaks save as in vanilla, the pickup also sets the
#     spot's checked bit, and from the next load the object's vanilla twin stands there. The Gold Skulltula keeps
#     its own way: its break doesn't save its flag (IsSetGmdRespawnFlagToFalse: false) and its token saves it.
# Step 1 changes every placement of the dropper type, step 2 every pickup of the type.
GS_PACK, GS_AI = "Pack/Actor/Enemy_Skulltula_Gold.pack.zs", "AI/Enemy_Skulltula_Gold.utility.root.ainb"
GS_DEATH = (  # its kill (LifeDepleted, Burned, Drowned) doesn't save its row; FallIntoAbyss doesn't even mark it dead
    "System/CombinationDataTableData/Enemy_Skulltula_Gold_game__death__DeathReasonProcedures.pp__CombinationDataTableData"
    ".bgyml")
HP_PACK, HP_AI = "Pack/Actor/Obj_Heart_Piece.pack.zs", "AI/Obj_Heart_Piece.root.ainb"
# game::death::DeathReason: 4 PickedUp (a pickup collected directly), 10 LifeDepleted (what get scenes request)
DEATH_PICKED_UP, DEATH_LIFE_DEPLETED = 4, 10
AI_GLOBAL = "Pack/AI.Global.Product.111.pack.zs"
DEATH_DIR = "System/CombinationDataTableData/"
SCRUB_TABLE = DEATH_DIR + "ScrubBusiness_game__death__DeathReasonProcedures.pp__CombinationDataTableData.bgyml"
SCRUB_REF = "Work/" + SCRUB_TABLE[:-len(".bgyml")] + ".gyml"
BOX03_TABLE = DEATH_DIR + "Obj_BrokenBox_A_03_game__death__DeathReasonProcedures.pp__CombinationDataTableData.bgyml"
# every death reason row of the Default table except AI. Business scrubs share ScrubBusiness and leave by an AI death
# after a sale, which has to keep saving.
# Only rows Default defines. An override cell (no RowKey/ColumnKey) for a row no table of the chain defines crashes the
# game while it loads the table. ChemicalCriticalHitIce did that and every new game crashed in the opening, so
# make_patch refuses such a cell now.
DEATH_ROWS = ("Burned", "ChemicalCriticalHitFire", "Drowned", "Eaten", "Exploded",
              "FallIntoAbyss", "Frozen", "LifeCondition", "LifeDepleted", "PhysicsKinematicCollision", "PickedUp",
              "SideCrushed", "Unequiped", "UpperCrushed", "AutoPlacementMgr")
_DP_EVENT = "Component/DeathParam/Obj_AllowDeathDuringEventIfNotAffiliationAIGroup.game__component__DeathParam.bgyml"
# dropper type -> (its root AI file in its pack, how its break stops saving)
# How it stops saving is "scrub" if it already uses ScrubBusiness, "box03" for its own table, or a DeathParam file in
# its pack that we point at ScrubBusiness (then it dies exactly like a pot).
PICKUP_SAVE_DROPPERS = {
    **{f"Obj_Pot_A_0{i}": ("AI/Obj_Pot.root.ainb", "scrub") for i in range(1, 9)},
    "Obj_BrokenBox_A_03": ("AI/Obj_BrokenBox_A_03.root.ainb", "box03"),
    "Obj_Plant_Grass_A_01": ("AI/Plant_Grass.root.ainb", _DP_EVENT),
    "Obj_Plant_Grass_A_03": ("AI/Obj_Plant_Grass_A_03.root.ainb", _DP_EVENT),
    "Obj_LiftRock_A_01": ("AI/Obj_LiftRock.root.ainb", _DP_EVENT),
    "Obj_LiftRock_A_03": ("AI/Obj_LiftRock.root.ainb", _DP_EVENT),
}
# Ship of Harkinian's Shuffle Icicles / Shuffle Red Ice / Shuffle Boulders' silver rocks
# These types have no Drop
# component, so drop_component_ops gives them the bomb boulder's. Their break (LifeDepleted) already asks for a drop.
# Death mode "icicle" means the icicles' own death table (Obj_FallingIcicle, only they use it) stops saving on break.
# Red ice and silver rocks get a copy of the icicles' DeathParam pointing at it, and red ice's Blue-Fire hit stops
# saving its flag (node 42 OneShotActorChangeIsRespawn).
ICICLE_TABLE = DEATH_DIR + "Obj_FallingIcicle_game__death__DeathReasonProcedures.pp__CombinationDataTableData.bgyml"
ICICLE_DP = "Component/DeathParam/Obj_FallingIcicle.game__component__DeathParam.bgyml"
ICICLE_DP_SRC = "Pack/Actor/Obj_FallingIcicle_A_02.pack.zs"
_RED_ICE = ("Obj_RedIce_A_01", "Obj_RedIce_A_02", "Obj_RedIce_A_04", "Obj_RedIce_A_06", "Obj_RedIce_A_07",
            "Obj_RedIce_A_08", "Obj_RedIce_A_09")
PICKUP_SAVE_DROPPERS.update({
    **{f"Obj_BrokenIcePillar_A_0{i}": ("AI/Obj_BrokenIcePillar_A_01.root.ainb", "icicle") for i in range(1, 5)},
    "Obj_FallingIcicle_A_01": ("AI/Obj_FallingIcicle_A_01.root.ainb", "icicle"),
    "Obj_FallingIcicle_A_02": ("AI/Obj_FallingIcicle_A_01.root.ainb", "icicle"),
    **{a: ("AI/Obj_RedIce_A_01.root.ainb", "icicle") for a in _RED_ICE},
    "Obj_LiftRock_B_01": ("AI/Obj_LiftRock_B_01.root.ainb", "icicle"),
})
DROP_COMPONENT_SRC = "Pack/Actor/Obj_BrokenRock_A_01.pack.zs"
DROP_COMPONENT_FILES = ("Component/DropParam/Default.game__component__DropParam.bgyml",
                        "Component/DropParam/Drop_Default.game__component__DropParam.bgyml",
                        "Drop/DropTable/DropTable_None.game__drop__DropTable.bgyml",
                        "Drop/DropSubTable/DropTable_None.game__drop__DropSubTable.bgyml",
                        "Component/Blackboard/BlackboardParamTable/Drop.engine__component__BlackboardParamTable.bgyml")
DROP_DEFAULT = "Component/DropParam/Drop_Default.game__component__DropParam.bgyml"
# We copy the boulder's Drop_Default along with its parent and tables, and the seed's preload list goes in our copy,
# since 113 enemy packs share the original.
RANDO_DROP_DEFAULT = "Component/DropParam/RandoDrop_Default.game__component__DropParam.bgyml"
DROP_COMPONENT_REF = "?" + RANDO_DROP_DEFAULT
# type -> the ActorParam that names its DropRef (its own, or the parent it inherits it from)
_AP = "Actor/{}.engine__actor__ActorParam.bgyml"
DROP_COMPONENT = {**{f"Obj_BrokenIcePillar_A_0{i}": _AP.format("Obj_BrokenIcePillar_A_01") for i in range(1, 5)},
                  "Obj_FallingIcicle_A_01": _AP.format("Obj_FallingIcicle_A_01"),
                  "Obj_FallingIcicle_A_02": _AP.format("Obj_FallingIcicle_A_02"),
                  **{a: _AP.format("Obj_RedIce_A_01") for a in _RED_ICE},
                  "Obj_LiftRock_B_01": _AP.format("Obj_LiftRock_B_01")}
# Red ice and silver rocks keep their own DeathParam. Taking the icicles' one only made breaking them stop saving, and
# the respawn model keeps vanilla break saving.
DEATH_TO_ICICLE = set()
REDICE_AI, REDICE_RESPAWN_NODE = "AI/Obj_RedIce_A_01.root.ainb", 42
COMPONENT_HEAP_EXTRA = 32 * 1024  # their actor rows' instance heap (the boulder with a Drop component has ~30 KB more)


def drop_component_ops(types, romfs=DEFAULT_ROMFS, tags=False, flag_key=False, save_key=False, at_keys=False):
    """make_patch sections that give dropper types a Drop component.
    - the bomb boulder's five Drop files, copied into every pack holding the ActorParam that names the component (byte
      copies of vanilla paths, so each keeps its size-table entry)
    - Components.DropRef on that ActorParam
    - the icicles' DeathParam for red ice and silver rocks (DEATH_TO_ICICLE)
    - the Drop table's keys registered for those packs, with explicit pack lists since "pack": "*" only finds vanilla
      holders
    - more instance heap"""
    from romtools import Romfs, sarc_files, byml_load
    import packpaths
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = {"packs": [], "ainb": [], "byml": []}
    paths = sorted({DROP_COMPONENT[t] for t in types})
    packs_with_table = set()
    for path in paths:
        holders = packpaths.carriers(path, romfs)
        if not holders:
            raise DropPlanError(f"no pack holds {path}")
        for pk in holders:
            files = sarc_files(fs.read(pk))
            for f in DROP_COMPONENT_FILES:
                if f not in files:
                    out["packs"].append({"pack": pk, "file": f, "from_pack": DROP_COMPONENT_SRC})
            out["packs"].append({"pack": pk, "file": RANDO_DROP_DEFAULT, "new_from": DROP_DEFAULT,
                                 "from_pack": DROP_COMPONENT_SRC})
            packs_with_table.add(pk)
            if path in DEATH_TO_ICICLE and ICICLE_DP not in files:
                out["packs"].append({"pack": pk, "file": ICICLE_DP, "from_pack": ICICLE_DP_SRC})
        sets = {"Components.DropRef": DROP_COMPONENT_REF}
        if path in DEATH_TO_ICICLE:
            sets["Components.DeathRef"] = "?" + ICICLE_DP
        out["packs"].append({"pack": "*", "file": path, "set": sets})
    keys = [{"table": DROP_TABLE, "type": "String", "key": k, "init": "", "instance": True}
            for k in ("Drop__DropActor", "Drop__DropTable")]  # already in the copied table, this registers them
    if flag_key:  # every copy of the Drop table has to end up like the other 195 packs' (the trees' flag name too)
        keys.append({"table": DROP_TABLE, "type": "String", "key": DROP_FLAG_KEY, "init": "", "instance": True})
    if tags:
        keys.append({"table": DROP_TABLE, "type": "F32", "key": DROP_TAG_KEY, "init": 0, "instance": True})
    if save_key:
        keys.append({"table": DROP_TABLE, "type": "Bool", "key": DROP_SAVE_KEY, "init": False, "instance": True})
        keys.append({"table": DROP_TABLE, "type": "S32", "key": DROP_CHK_KEY, "init": 0, "instance": True})
    if at_keys:  # reachable drop positions, for when a placement of the seed makes its drop somewhere else (DROP_AT_*)
        keys.append({"table": DROP_TABLE, "type": "Bool", "key": DROP_AT_KEY, "init": False, "instance": True})
        keys += [{"table": DROP_TABLE, "type": "F32", "key": k, "init": 0, "instance": True} for k in DROP_AT_XYZ]
    out["ainb"].append({"pack": sorted(packs_with_table), "bb_params": keys})
    heap = {r.get("__RowId"): r.get("InstanceHeapSize") for r in byml_load(fs.read(ACTOR_INFO))[0]}
    for t in sorted(types):
        if heap.get(t):
            out["byml"].append({"file": ACTOR_INFO, "set": {
                f"[__RowId={t}].InstanceHeapSize": int(heap[t]) + COMPONENT_HEAP_EXTRA}})
    return out
# These can't do it without a new file. Large crates Obj_BrokenBox_A_01, beehives, palm fruit and flying pots use the
# shared Default death table through ResidentCommon's Default.game__component__DeathParam. There's no DeathParam file in
# their own pack to repoint, and the Default table is every actor's. Bomb boulders (Obj_BrokenRock_A_01) have no AI at
# all. They keep the "safe" rules, junk and repeatable items.
NO_PICKUP_SAVE = {
    "Obj_BrokenBox_A_01": "death table: ResidentCommon's Default DeathParam (no pack file to repoint)",
    "Obj_Kokiri_Beehive_A_01": "death table: ResidentCommon's Default DeathParam (no pack file to repoint)",
    "Obj_Gerudo_PalmFruit_A_01": "death table: ResidentCommon's Default DeathParam (no pack file to repoint)",
    "Enemy_FlyingPot_SpiritTemple": "death table: ResidentCommon's Default DeathParam (no pack file to repoint)",
    "Enemy_FlyingPot_ShadowTemple": "death table: ResidentCommon's Default DeathParam (no pack file to repoint)",
    "Enemy_FlyingPot_IceCavern": "death table: ResidentCommon's Default DeathParam (no pack file to repoint)",
    "Obj_BrokenRock_A_01": "no AI graph (AIInfo) to hand its hash to the drop",
    "Obj_BrokenRock_A_02": "CrackObjectCommon death table, shared with every cracked wall",
}
_BB_DROPITEM = "Component/Blackboard/BlackboardParamTable/DropItem.engine__component__BlackboardParamTable.bgyml"
# Ammo touch pickups
# Through the carrier, ammo gives a pickup prompt and Link stops, while the game's own ammo is picked up automatically
# like every other pickup. So junk ammo at a drop spot whose item is never lost (checked on pickup or the respawn model)
# drops as the game's own pickup, like rupees and recovery hearts do.
# From the files: these types are Obj_Item_Base pickups with the rupees' AI (AI.Global DropItem.root, which raises
# IsEnableAttention), the rupees' blackboard (the DropItem table, every pack) and the rupees' touch client
# (Auto_Item_Catch, same reach for child and adult, and nothing in their packs names an age). Their pouch content has
# DefaultAutoGet and no GetType, so it's taken the moment Link touches it, with no scene and the game's count popup.
# Taking one sets its dropper's checked bit like a rupee does (PICKUP_SAVERS), and the break doesn't record it. Without
# its container the pickup adds nothing (0/0, parity/_ammo.py's rule).
# Obj_DekuStick brings the small stick bag (IsAbleToGetBagIfGet), and our nut types bring the nut bag (ammo_type_ops).
# Not Obj_Bombchu though. Its pouch content inherits Item_Bombchu's GetType (a touch plays a get scene), so bombchus
# stay in the carrier (parity/drops.py _is_ammo).
# Deku Seeds drop as our RandoAmmo_Seeds30, which falls. Obj_DekuSeed's own PhysicsParam (Item_DekuSeed) names a
# controller set with no main rigid body, so it stays where it's created. That's why the type takes Obj_DekuNut's (the
# dropped nut's DropItem controller set, a Dynamic body; AMMO_SEED_BODY), in its own pack only, and placed and
# vanilla-dropped seeds are untouched. The amounts are under Ammo counts.
TOUCH_AMMO = tuple(AMMO_TYPES) + ("Obj_DekuStick",)
# pickup type -> (its AI file, its blackboard table in its pack). An AI file of None means AI.Global's shared
# DropItem.root.ainb.
# Obj_Heart_Piece (RespawnGmdHash) and Obj_Token_Gold (GoldTokenGmdHash) already save their dropper.
PICKUP_SAVERS = {
    **{a: (None, _BB_DROPITEM) for a in ("Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red", "Obj_Rupee_Purple",
                                         "Obj_Rupee_Gold", "Obj_Heart", "Obj_Heart_Container", "Obj_Shield_Deku",
                                         "Obj_Shield_Hylian", "Obj_Armor_Goron", "Obj_Armor_Zora", "Obj_Arrow_Fire",
                                         "Obj_MagicJar_Small", "Obj_MagicJar_Large") + TOUCH_AMMO},
    "Obj_Dungeon_SmallKey": (None, "Component/Blackboard/BlackboardParamTable/"
                                   "Obj_Dungeon_SmallKey.engine__component__BlackboardParamTable.bgyml"),
    "Obj_Bottle_Letter": ("AI/Item_Bottle_Letter.root.ainb", _BB_DROPITEM),
}
SAVES_ALREADY = {"Obj_Heart_Piece", "Obj_Token_Gold", DISGUISE_ACTOR}  # the disguise carrier runs Obj_Heart_Piece.root


def picks_up_checked(entry):
    """True if every object of this drop spot can be made "checked on pickup". That needs a dropper type with the
    pipeline, a save flag that can be permanent, and no reset group that would bring it back after its item is taken."""
    rows = entry.get("placements", [])
    if entry.get("kind") != "drop" or not rows:
        return False
    for r in rows:
        if r["category"] == "gold_skulltula":
            continue
        if r["actor"] not in PICKUP_SAVE_DROPPERS or r["flag"] not in (24, 88, 280) or r.get("reset_group"):
            return False
    return True


# dropper types that can hold flagless drops. Their root AI gets the tag hand-over (pickup_save_ops) and the flag gate.
# Types sharing an AI with a PICKUP_SAVE_DROPPERS type reuse its edit, and others get added when their drop path is
# known.
# Kind "presence": the respawning pots and grass share their base type's root AI (and its tag hand-over), and they leave
# the world once their item is taken. That's a negated placement Presence on the borrowed flag, the same thing vanilla's
# Ruto's-letter bottle does.
# Kind "tree": trees drop through their own AI (Land_Tree_BeechMiddle_A_01.root, node 64 OneShotDropSetOverWriteParam
# before node 60 OneShotDropDrop). The tag joins that chain, and while the borrowed flag is set the tree counts itself
# as already shaken (its own IsDropped), so it stays and drops nothing more.
FLAGLESS_DROPPERS = {"Obj_Pot_A_02_Respawn": ("presence", "Obj_Pot_A_02"),
                     "Obj_Pot_A_05_Respawn": ("presence", "Obj_Pot_A_05"),
                     "Obj_Pot_A_07_Respawn": ("presence", "Obj_Pot_A_07"),
                     "Obj_Pot_A_08_Respawn": ("presence", "Obj_Pot_A_08"),
                     "Obj_Plant_Grass_A_01_Respawn": ("presence", "Obj_Plant_Grass_A_01"),
                     "Obj_Tree_A_01": ("tree", None), "Obj_Tree_A_02": ("tree", None),
                     "Obj_Tree_Tutorial_A_01": ("tree", None),
                     # the Hyrule Field bushes get an AI of their own first (NEW_AI_DROPPERS)
                     "Land_kokiri_Plant_A_02_DropFixed_03": ("presence", "Land_kokiri_Plant_A_02_DropFixed_03"),
                     # the Gerudo hanging signs (no save flag of their own). Their root AI (RESPAWN_DROPPERS) drops once
                     # when an Arrow or the Hookshot hits. An item left behind is there again from the next load, and
                     # once it's taken the sign is a plain one from the next load. Its Presence is only read at loads,
                     # so it doesn't vanish in front of Link.
                     "Obj_Gerudo_HangingSign_B_01": ("presence", "Obj_Gerudo_HangingSign_B_01")}
TREE_AI = {"Obj_Tree_A_01": "AI/Land_Tree_BeechMiddle_A_01.root.ainb",
           "Obj_Tree_A_02": "AI/Land_Tree_BeechMiddle_A_01.root.ainb",
           "Obj_Tree_Tutorial_A_01": "AI/Obj_Tree_Tutorial_A_01.root.ainb"}


def dropper_ai(actor):
    """(pack, AI file) holding a dropper type's drop chain. That's the Gold Skulltula's own AI, a tree's root AI, or the
    type's root AI in PICKUP_SAVE_DROPPERS (for a flagless respawning copy, the root AI of the type it copies)."""
    if actor == "Enemy_Skulltula_Gold":
        return GS_PACK, GS_AI
    kind, base = FLAGLESS_DROPPERS.get(actor, (None, actor))
    if kind == "tree":
        return f"Pack/Actor/{actor}.pack.zs", TREE_AI[actor]
    return f"Pack/Actor/{base}.pack.zs", _dropper_root(base)


# dropper types only the respawn model takes (not picks_up_checked). The fill takes any item there through the scene
# drop (parity/drops.py _checked), since the respawn model never loses it. Their root AI gets the hand-over like the
# others, and with breaks still saving they never needed more than that.
RESPAWN_DROPPERS = {"Animal_ButterflyToFairy": "AI/Animal_ButterflyToFairy.utility.root.ainb",
                    "Obj_BrokenBox_A_01": "AI/Obj_BrokenBox_A_01.root.ainb",
                    "Obj_Kokiri_Beehive_A_01": "AI/Obj_Beehive.root.ainb",
                    "Obj_Gerudo_PalmFruit_A_01": "AI/PalmFruit.root.ainb",
                    "Obj_BrokenRock_A_02": "AI/Obj_BrokenRock_A_02.root.ainb",
                    # Twinless placements (no spot may lose its item). The flying pots are enemies, and their root is
                    # one module call, wrapped like any other dropper's. The Gerudo cow skulls drop once per instance
                    # flag (their own row) when hit, through OneShotDropReserveDropItemCreate, and stay standing.
                    **{f"Enemy_FlyingPot_{d}": "AI/Enemy_FlyingPot.root.ainb"
                       for d in ("SpiritTemple", "ShadowTemple", "IceCavern")},
                    **{f"Obj_Gerudo_CowBoneDecoration_B_0{i}": "AI/Obj_Gerudo_CowBoneDecoration_A_01.root.ainb"
                       for i in (1, 2, 3)},
                    # the Gerudo hanging signs are a cow skull's kind (their ActorParam's parent is the cow skull's)
                    # with their own root AI (isDroped, OneShotDropReserveDropItemCreate, OneShotDropDrop). They have no
                    # save flag, so they take the flagless model (FLAGLESS_DROPPERS "presence"), never the respawn
                    # model.
                    "Obj_Gerudo_HangingSign_B_01": "AI/Obj_Gerudo_HangingSign_A_01.root.ainb",
                    # the bomb boulders, with an AI of their own (NEW_AI_DROPPERS). They're permanent in vanilla, so no
                    # twin.
                    "Obj_BrokenRock_A_01": "AI/RandoBoulder.root.ainb",
                    "Obj_Goron_BrokenRock_A_01": "AI/RandoGoronRock.root.ainb"}
# droppers that stay standing after dropping (not broken). Their original's Presence is only checked at loads, so it
# doesn't vanish in front of the player the moment its item is taken. It's gone from the next load (Twinless
# placements).
STANDING_DROPPERS = {f"Obj_Gerudo_CowBoneDecoration_B_0{i}" for i in (1, 2, 3)}


# dropper types with no AI at all, given one. That's Ship of Harkinian's Shuffle Bushes, the Hyrule Field bushes, whose
# drop comes from their death procedure.
# They get the bronze boulder's root AI (8 nodes: a linked Gold Skulltula's respawn query and dummy actions, nothing
# that moves, hits or draws), copied in under its own name with its own AIInfo, plus Components.AIInfoRef on the type's
# ActorParam (only its own pack holds it) and more instance heap. pickup_save_ops then gives that AI the hand-over every
# dropper gets. Its drop takes the tag and the bit while it's cut through the Default death procedure, like a large
# crate's or a beehive's.
NEW_AI_DROPPERS = {"Land_kokiri_Plant_A_02_DropFixed_03": {"name": "RandoBush",
                                                           "src_pack": "Pack/Actor/Obj_BrokenRock_A_02.pack.zs",
                                                           "src": "Obj_BrokenRock_A_02"},
                   # the bomb boulders get the same AI, so they take the respawn model. My call was "it has to come back
                   # like pots then". They're Twinless placements, permanent in vanilla so there's no twin. An item left
                   # behind comes back with the boulder at a map change or a load (a room inside a map doesn't count),
                   # and once it's taken the boulder stays broken, the vanilla rule.
                   # Obj_BrokenRock_A_01's ActorParam is shared, and Obj_BrokenRock_A_02 (its own AIInfoRef wins) and
                   # the Ganon's Castle crack wall hold the same file. The crack wall inherits the ref, so it carries
                   # the AI too ("with"). That's 8 inert nodes plus the hand-over of tag 0 and bit 0, which nothing
                   # reads.
                   "Obj_BrokenRock_A_01": {"name": "RandoBoulder", "src_pack": "Pack/Actor/Obj_BrokenRock_A_02.pack.zs",
                                           "src": "Obj_BrokenRock_A_02",
                                           "with": ["Obj_CrumblingGanonCastle_CrackWall_A_01"]},
                   "Obj_Goron_BrokenRock_A_01": {"name": "RandoGoronRock",
                                                 "src_pack": "Pack/Actor/Obj_BrokenRock_A_02.pack.zs",
                                                 "src": "Obj_BrokenRock_A_02"}}


def new_ai_packs(actor):
    """The packs a NEW_AI_DROPPERS type's AI and AIInfo go in: its own, and those inheriting its ActorParam ("with")."""
    return [f"Pack/Actor/{x}.pack.zs" for x in [actor] + list(NEW_AI_DROPPERS[actor].get("with", []))]
NEW_AI_HEAP_EXTRA = 32 * 1024  # the boulder with an AI is ~2 KB over the one without, and the hand-over adds ~30 nodes


def new_ai_paths(actor):
    """(root AI, AIInfo, source root AI, source AIInfo) pack paths of a NEW_AI_DROPPERS type."""
    d = NEW_AI_DROPPERS[actor]
    return (f"AI/{d['name']}.root.ainb", f"AI/AIInfo/{d['name']}.engine__actor__AIInfo.bgyml",
            f"AI/{d['src']}.root.ainb", f"AI/AIInfo/{d['src']}.engine__actor__AIInfo.bgyml")


def dropper_ai_bytes(fs, actor):
    """The vanilla bytes a dropper type's root AI starts from: its pack's file, or a NEW_AI_DROPPERS type's source."""
    from romtools import sarc_files
    if actor in NEW_AI_DROPPERS:
        return sarc_files(fs.read(NEW_AI_DROPPERS[actor]["src_pack"]))[new_ai_paths(actor)[2]]
    return sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))[_dropper_root(actor)]


def new_ai_ops(types, romfs=DEFAULT_ROMFS):
    """make_patch sections giving NEW_AI_DROPPERS types their AI: {"packs": [...], "byml": [...]}."""
    from romtools import Romfs, sarc_files, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = {"packs": [], "byml": []}
    heap = {r.get("__RowId"): r.get("InstanceHeapSize") for r in byml_load(fs.read(ACTOR_INFO))[0]}
    for t in sorted(types):
        if t not in NEW_AI_DROPPERS:
            continue
        d = NEW_AI_DROPPERS[t]
        ai, info, src_ai, src_info = new_ai_paths(t)
        pack = f"Pack/Actor/{t}.pack.zs"
        ap = _AP.format(t)
        files = sarc_files(fs.read(pack))
        comps = byml_load(files[ap], allow_big=True)[0].get("Components") or {}
        if "AIInfoRef" in comps or ai in files or info in files:
            raise DropPlanError(f"{t}: already has an AI ({comps.get('AIInfoRef')})")
        import packpaths
        holders = list(packpaths.carriers(ap, romfs))  # every pack holding the ActorParam gets the same edit
        for h in holders:  # other holders have to be listed under "with" or override the inherited AIInfoRef
            if h not in new_ai_packs(t):
                own = f"Actor/{h.split('/')[-1][:-len('.pack.zs')]}.engine__actor__ActorParam.bgyml"
                hf = sarc_files(fs.read(h))
                if own not in hf or "AIInfoRef" not in (byml_load(hf[own], allow_big=True)[0].get("Components") or {}):
                    raise DropPlanError(f"{t}: {h} holds its ActorParam and would inherit the new AI: list it in "
                                        f"NEW_AI_DROPPERS 'with'")
        src = sarc_files(fs.read(d["src_pack"]))
        if src_ai not in src or src_info not in src:
            raise DropPlanError(f"{d['src_pack']}: no {src_ai} / {src_info} to copy")
        if byml_load(src[src_info])[0] != {"RootAIRef": f"Work/AI/Root/{d['src']}.root.ain"}:
            raise DropPlanError(f"{src_info}: no longer only its root AI")
        for pk in new_ai_packs(t):
            out["packs"] += [
                {"pack": pk, "file": ai, "from_pack": d["src_pack"], "new_from": src_ai},  # bytes (not BYML)
                {"pack": pk, "file": info, "from_pack": d["src_pack"], "new_from": src_info,
                 "set": {"RootAIRef": f"Work/AI/Root/{d['name']}.root.ain"}}]
        out["packs"] += [{"pack": h, "file": ap, "set": {"Components.AIInfoRef": "?" + info}}
                         for h in sorted(set(holders) | {pack})]
        for x in [t] + list(d.get("with", [])):
            if heap.get(x):
                out["byml"].append({"file": ACTOR_INFO, "set": {
                    f"[__RowId={x}].InstanceHeapSize": int(heap[x]) + NEW_AI_HEAP_EXTRA}})
    return out


# root AIs whose hand-over has to run before anything else at the root. The butterfly's utility root reserves its drop
# as it starts (OneShotDropReserveDropItemCreate, its first Sequential), so its overwrite param is set first.
HANDOVER_FIRST = {"AI/Animal_ButterflyToFairy.utility.root.ainb"}


def _dropper_root(base):
    """A dropper type's root AI file (PICKUP_SAVE_DROPPERS, RESPAWN_DROPPERS or NEW_AI_DROPPERS)."""
    if base in NEW_AI_DROPPERS:
        return new_ai_paths(base)[0]
    return PICKUP_SAVE_DROPPERS[base][0] if base in PICKUP_SAVE_DROPPERS else RESPAWN_DROPPERS[base]


def respawn_capable(entry):
    """True if every object of this drop spot can take the respawn model. That needs a dropper type whose root AI hands
    the checked bit to its drop (PICKUP_SAVE_DROPPERS) and a save flag of its own (24, 88, 280). A reset group is fine
    (the object comes back with its item until it's taken), and so is a vanilla Presence it can keep (_respawn_ok)."""
    rows = entry.get("placements", [])
    if entry.get("kind") != "drop" or not rows:
        return False
    copies = len(rows) > 1  # COPIES: the twin may stand in where an NPC link or an age-only logic module points
    return all(r["category"] != "gold_skulltula" and (r["actor"] in PICKUP_SAVE_DROPPERS or r["actor"] in
                                                      RESPAWN_DROPPERS) and r["flag"] in (24, 88, 280)
               for r in rows) and all(_respawn_ok(r, copies, twin=False) is None for r in rows)


def respawn_model_spot(p):
    """True if this placement takes the respawn model whenever its spot does (a plan allowing checked_on_pickup). Then
    it never comes back as itself after its check, whatever item it holds (its vanilla twin does). It's decided per spot
    like plan_ops does, so every placement of its drop-map entry has to take it."""
    if p["category"] == "gold_skulltula":
        return False
    if p["flag"] is None:
        return FLAGLESS_DROPPERS.get(p["actor"], (None,))[0] == "presence"
    entry = _entry_of(p["file"], str(p["hash"]))
    if entry is not None:
        return respawn_capable(entry)
    return ((p["actor"] in PICKUP_SAVE_DROPPERS or p["actor"] in RESPAWN_DROPPERS) and p["flag"] in (24, 88, 280)
            and _respawn_ok(p, twin=False) is None)


@lru_cache(maxsize=None)
def _placement_entries():
    m = _map()
    return {(p["file"], str(p["hash"])): e for e in list(m["drops"].values()) + list(m.get("new", {}).values())
            for p in e.get("placements", [])}


def _entry_of(file, h):
    """The drop-map entry holding this placement, or None."""
    return _placement_entries().get((file, h))


def sets_bit_on_pickup(actor):
    """True if this pickup sets its dropper's checked bit when taken (pickup_save_ops). That's the PICKUP_SAVERS types,
    the heart piece and the disguise carrier (Obj_Heart_Piece.root), and the Gold Skulltula token
    (Item_Token_Gold.root), since a token checked on the break would be lost for good if it fell out of reach. For
    anything else (an enemy, a fairy) it's the break."""
    return actor in PICKUP_SAVERS or actor in ("Obj_Heart_Piece", DISGUISE_ACTOR, "Obj_Token_Gold")


@lru_cache(maxsize=None)
def _gd_index():
    """(Bool64bitKey rows {hash: row}, {murmur3 name hash: table}) of the vanilla GameDataList."""
    from romtools import Romfs, byml_load
    fs = Romfs(DEFAULT_ROMFS, os.path.join(HERE, "original"))
    raw = fs.read("GameData/GameDataList.Product.110.byml.zs")
    try:
        raw = fs.zs.decompress(raw)
    except Exception:  # noqa: BLE001 - stored uncompressed
        pass
    g = byml_load(raw, allow_big=True)[0]
    names = {e["Hash"]: t for t, rows in g["Data"].items() if t != "Bool64bitKey" for e in rows}
    return {e["Hash"]: e for e in g["Data"]["Bool64bitKey"]}, names


@lru_cache(maxsize=None)
def _vanilla_level(file):
    """{hash string: actor} of a vanilla level file."""
    from romtools import Romfs, byml_load
    fs = Romfs(DEFAULT_ROMFS, os.path.join(HERE, "original"))
    return {str(a.get("Hash")): a for a in byml_load(fs.read(file))[0].get("Actors", [])}


@lru_cache(maxsize=None)
def _area_byte(file):
    """The ExtraByte (area) of the area-reset rows of this level's objects (the most common), or None."""
    from collections import Counter
    rows, _ = _gd_index()
    c = Counter(int(rows[int(h)]["ExtraByte"]) for h in _vanilla_level(file)
                if int(h) in rows and "ExtraByte" in rows[int(h)] and int(rows[int(h)]["ResetTypeValue"]) == 88)
    return c.most_common(1)[0][0] if c else None


def _presence_steps(pres):
    """A vanilla Presence as BoolExp steps in reverse Polish, or None if its flag is neither. A Bool is [0, name], a
    BoolExp [10, name], with NOT [5] if negated."""
    from romtools import murmur3_32
    _, names = _gd_index()
    t = names.get(murmur3_32(pres.get("FlagName", "")))
    if t not in ("Bool", "BoolExp"):
        return None
    return [[0 if t == "Bool" else 10, pres["FlagName"]]] + ([[5]] if pres.get("IsNegation") else [])


@lru_cache(maxsize=None)
def _inbound_refs(stage_dir):
    """{hash: [what points at it]} over a stage folder's level files. That covers other actors' links, except reset
    actors since their groups take the twin too (group_join_ops), and logic modules' references (AiGroups find actors by
    name, so a twin can't stand in).
    What it finds: room logic modules (Ice Cavern, Bottom of the Well, Ganon's Castle...), palm trees' fruit, red ice
    holding pots, Obj_BrokenBox_A_06's respawn-sync crates, and two NPC/event links."""
    from romtools import Romfs, byml_load
    fs = Romfs(DEFAULT_ROMFS, os.path.join(HERE, "original"))
    out = defaultdict(list)
    for fn in sorted(os.listdir(os.path.join(DEFAULT_ROMFS, stage_dir))):
        if not fn.endswith(".bcett.byml.zs"):
            continue
        doc = byml_load(fs.read(f"{stage_dir}/{fn}"))[0] or {}
        for a in doc.get("Actors", []) or []:
            if a.get("Gyaml") == RESET_ACTOR:
                continue
            for ln in a.get("Links") or []:
                if str(ln.get("Dst")) != str(a.get("Hash")):
                    out[str(ln.get("Dst"))].append(f"{a.get('Gyaml')}'s {ln.get('Name')} link")
        for g in doc.get("AiGroups") or []:
            for r in g.get("References") or []:
                out[str(r.get("Reference"))].append(f"logic {g.get('Logic')}")
    return dict(out)


def _respawn_ok(p, copies=False, twin=True):
    """None if this placement can take the respawn model, else why not.
    `copies` means its location has several copies, and then a twin may stand in where _twin_refs allows (COPIES).
    twin=False is the model without a twin (TWINLESS), which a link or logic module pointing at the placement doesn't
    stop."""
    rows, _ = _gd_index()
    h = int(p["hash"])
    if h not in rows:
        return "no save row of its own"
    refs = _inbound_refs(os.path.dirname(p["file"])).get(str(p["hash"]))
    if twin and refs and not (copies and _twin_refs(p)[0]):
        return f"{refs[0]} points at it (a twin couldn't stand in)"
    van = _vanilla_level(p["file"]).get(str(p["hash"]))
    if van is None:
        return "not in its vanilla level file"
    if van.get("Presence") and _presence_steps(van["Presence"]) is None:
        return f"its Presence flag {van['Presence'].get('FlagName')} is no Bool or BoolExp"
    if twin and p["flag"] != 24 and (h ^ 2) not in rows and str(h ^ 2) in _vanilla_level(p["file"]):
        return "hash ^ 2 is another placement's"
    return None


# COPIES
# A location made of several copies of one object (Spirit Temple Lobby Pot 1/2, one pot per age at each spot, or GC
# Lower Staircase Pot 1, a child and an adult pot) used to give its item once per copy, since each copy kept a save flag
# of its own. OoTR gives a check's item once.
# So a spot like that takes the respawn model, with one checked bit for the location. Every copy leaves once it's set
# and a plain vanilla twin stands in its place, because checked objects look normal. That works even where something
# points at a copy, as long as the twin can honour it:
#  - an NPC's Reference link. The NPC already copes with its target gone, since the pot breaks in vanilla. 74 vanilla
#    NPC Reference links point at objects a Presence can hide, e.g. Talon's at Malon and a Gerudo guard's at the cow.
#  - a logic module that only creates the copy, always or by age (Logic_Create constant True or fed by
#    HoldIsChildhoodOrAdulthood, every other input constant, Logic_Delete False, no node reading its outputs). The
#    twin's Presence takes the same age (Sequence_IsChildhood, like vanilla's age soils). A Presence hides a
#    logic-created actor in vanilla too, the gossip stones' GossipStoneDisappear does it in 710 placements.
# Anything else pointing at a copy still refuses. A copy the game never creates (its patched module's Logic_Create is a
# constant False) gives nothing, and verify_one_give reads both back.
# One module reads its copy for a scene only, and it's named here. GC Lower Staircase Pot 1's child pot
# (GoronCity_Child_Prefab_c44b, Obj_Pot_A_01_4141, Create/Delete constant) drives the one-time Deku Stick scene, where a
# child Goron takes the stick the pot drops (GoronCity_DekuStickStolenEvent_Done), and that Goron's talk
# (GoronCity_DekuStickPot_Broke). Nothing is given or lost there. A stand-in pot broken after the check plays neither.
# The scene plays when the child breaks the pot before its check, as in vanilla, and an adult checking first skips it.
# One item per check is the rule.
COPIES_SCENE_ONLY = {("Logic/GoronCity_Child_Prefab_c44b.logic.module.ainb", "Obj_Pot_A_01_4141")}


@lru_cache(maxsize=None)
def _stage_refs(stage_dir):
    """{hash: {"links": [(source type, link name)], "logic": [(module file, instance name, path)]}} over a stage
    folder's vanilla level files (reset actors' links aside, as _inbound_refs)."""
    from romtools import Romfs, byml_load
    fs = Romfs(DEFAULT_ROMFS, os.path.join(HERE, "original"))
    out = defaultdict(lambda: {"links": [], "logic": []})
    for fn in sorted(os.listdir(os.path.join(DEFAULT_ROMFS, stage_dir))):
        if not fn.endswith(".bcett.byml.zs"):
            continue
        doc = byml_load(fs.read(f"{stage_dir}/{fn}"))[0] or {}
        for a in doc.get("Actors", []) or []:
            if a.get("Gyaml") == RESET_ACTOR:
                continue
            for ln in a.get("Links") or []:
                if str(ln.get("Dst")) != str(a.get("Hash")):
                    out[str(ln.get("Dst"))]["links"].append((str(a.get("Gyaml")), str(ln.get("Name"))))
        for g in doc.get("AiGroups") or []:
            module = "Logic/" + str(g.get("Logic", "")).split("/")[-1] + "b"  # Logic/Module/<P>/<P>_x.ain -> file
            for r in g.get("References") or []:
                out[str(r.get("Reference"))]["logic"].append((module, r.get("Id"), r.get("Path")))
    return dict(out)


@lru_cache(maxsize=None)
def _logic_creates(module, inst):
    """How logic module `module` treats its actor `inst`: "always" or "child"/"adult" if it only creates it (see
    COPIES), else None."""
    from romtools import Romfs
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import ainb
    a = ainb.Ainb(Romfs(DEFAULT_ROMFS, os.path.join(HERE, "original")).raw(module))
    mine = [i for i, n in enumerate(a.nodes)
            if any(x["name"] == "InstanceName" and x["value"] == inst for x in n["properties"]["string"])]
    if len(mine) != 1 or not a.nodes[mine[0]]["name"].startswith("ActorLogic"):
        return None
    i, create = mine[0], None
    for t in ainb.PTYPES:
        for e in a.nodes[i]["inputs"][t]:
            fed = e["node"] >= 0 or e["node"] <= -100 or e["flags"] & ainb.BB_INDEXED
            if t == "bool" and e["name"] == "Logic_Create":
                create = e
            elif fed or (e["name"] == "Logic_Delete" and e["value"] is not False):
                return None
    for j, n in enumerate(a.nodes):  # nothing may read what the node knows of its actor (Dead, Lifted...)
        if j != i and i in a._direct_sources(j) and (module, inst) not in COPIES_SCENE_ONLY:
            return None
    if create is None:
        return None
    if create["node"] == -1:
        return "always" if create["value"] is True else None
    if create["node"] >= 0 and not create["flags"] & ainb.BB_INDEXED:
        src = a.nodes[create["node"]]
        if src["name"] == "HoldIsChildhoodOrAdulthood":
            return {"Childhood": "child", "Adulthood": "adult"}.get(src["outputs"]["bool"][create["plug"]]["name"])
    return None


def _twin_refs(p):
    """(True, the age its twin keeps or None) if a twin can stand in for this copy whatever points at it (COPIES),
    else (False, why)."""
    refs = _stage_refs(os.path.dirname(p["file"])).get(str(p["hash"]), {"links": [], "logic": []})
    for src, name in refs["links"]:
        if not (src.startswith("Npc_") and name == "Reference"):
            return False, f"{src}'s {name} link points at it"
    age = None
    for module, inst, path in refs["logic"]:
        how = _logic_creates(module, inst) if path == inst else None
        if how is None:
            return False, f"logic {module} ({inst}) does more than create it"
        if how != "always":
            if age not in (None, how):
                return False, f"logic modules create it for both ages ({age}, {how})"
            age = how
    return True, age


# BAKED_TYPES. Types whose collision is baked into their area's static body (Phive/StaticCompoundBody), found by
# placement ID. Every placement of these has baked shapes there, and no placement of any other type the drops code can
# twin has any (tools/phive_static.py --check). A twin under a new Phive ID has no entry, so it may have no collision
# (OotrR issue #37: a tree's copy had none). So a twin of these keeps its source's ID (make_patch "keep_phive_id").
# The pair is never present together. The source's Presence is (vanilla's and) not checked, the twin's is (vanilla's
# and) checked.
# Twinned today: 29 crates (Obj_BrokenBox_A_01) and the 26 Hyrule Field bushes. The rest have no twin. Trees stay as
# shaken trees, rocks, red ice and silver rocks are permanent, and a room logic module points at every falling icicle
# (_respawn_ok). Pot, grass and other twins keep their new IDs, and I've seen them work like that in game.
BAKED_TYPES = frozenset({"Obj_BrokenBox_A_01", "Obj_FallingIcicle_A_01", "Obj_FallingIcicle_A_02",
                         "Land_kokiri_Plant_A_02_DropFixed_03", "Obj_BrokenRock_A_02", "Obj_LiftRock_B_01",
                         "Obj_Tree_A_01", "Obj_Tree_A_02", "Obj_Tree_Tutorial_A_01",
                         *(f"Obj_RedIce_A_0{i}" for i in (1, 2, 4, 6, 7, 8, 9))})


def _keeps_phive_id(p):
    """{"keep_phive_id": True} for a twin op of a BAKED_TYPES placement, else {}."""
    return {"keep_phive_id": True} if p["actor"] in BAKED_TYPES else {}


def _respawn_ops(p, bit, actor, exps, with_twin=True):
    """The respawn model for one placement. Returns (sets for its op, its twin op or None, {hash: per-object fields},
    record).
    `exps` ({name: steps}) collects the expression flags. A twin row that doesn't exist yet is marked "new" in its
    fields (plan "add_per_object"). Icicles have that, since with no Drop component in vanilla they have no hash ^ 2
    row."""
    rows, _ = _gd_index()
    h = int(p["hash"])
    exp = CHECKED_EXP.format(bit)
    pres = _vanilla_level(p["file"])[str(p["hash"])].get("Presence")
    # a copy its logic module only creates for one age (COPIES) gets a twin that only stands there for that age
    ok, age = _twin_refs(p) if _inbound_refs(os.path.dirname(p["file"])).get(str(p["hash"])) else (True, None)
    age = age if ok else None
    age_steps = (_presence_steps({"FlagName": "Sequence_IsChildhood", "IsNegation": age == "adult"}) + [[3]]
                 if age else [])
    make_twin = with_twin and p["flag"] != 24  # (permanent in vanilla, or Twinless placements: no twin, no twin expression)
    if pres:  # keep the vanilla condition: (it) and not checked / (it) and checked
        cond, lazy = _presence_steps(pres), bool(pres.get("IsCheckLazy"))
        mine, twin = f"{exp}_{h}_O", f"{exp}_{h}_V"  # per placement, since a spot's placements may differ
        exps[mine] = cond + [[8, CHECKED_ARRAY, bit], [5], [3]]
        if make_twin:
            exps[twin] = cond + [[8, CHECKED_ARRAY, bit], [3]] + age_steps + [[8, VISIT_ARRAY, bit], [5], [3]]
        p_pres = {"FlagName": mine, "IsCheckLazy": lazy and p["actor"] not in STANDING_DROPPERS, "IsNegation": False}
        t_pres = {"FlagName": twin, "IsCheckLazy": False, "IsNegation": False}  # (see TWIN_PRESENCE below)
    else:
        exps[exp] = [[8, CHECKED_ARRAY, bit]]
        p_pres = {"FlagName": exp, "IsCheckLazy": p["actor"] not in STANDING_DROPPERS, "IsNegation": True}
        twin = f"{exp}_V" if not age_steps else f"{exp}_{h}_V"  # (VISIT: checked, and not in this visit)
        if make_twin:
            exps[twin] = [[8, CHECKED_ARRAY, bit]] + age_steps + [[8, VISIT_ARRAY, bit], [5], [3]]
        t_pres = {"FlagName": twin, "IsCheckLazy": False, "IsNegation": False}
    sets = {f"Dynamic.{DROP_CHK_KEY}": bit, "Presence": p_pres}
    if not sets_bit_on_pickup(actor):
        sets[f"Dynamic.{DROP_SAVE_KEY}"] = True
    fields, twin_op = {}, None
    # Unchecked respawn. While unchecked, the original comes back with its item at every map change and load (its row's
    # MAP_RESET bit). Once it's checked its Presence keeps it away, so a reset can't give the item twice (plan_ops
    # refuses a clash).
    if not make_twin:  # A permanent or twinless placement stays gone once its item is taken.
        fields[str(h)] = {"ResetTypeValue": int(rows[h]["ResetTypeValue"]) | MAP_RESET}
    else:  # respawns in vanilla, so its vanilla twin goes under hash ^ 2 and that row resets as its own did in vanilla
        own = rows[h]
        fields[str(h)] = {"ResetTypeValue": int(own["ResetTypeValue"]) | MAP_RESET}
        f = {"ResetTypeValue": int(own["ResetTypeValue"])}
        if "ExtraByte" in own:
            f["ExtraByte"] = int(own["ExtraByte"])
        if (h ^ 2) not in rows:
            f["new"] = True
        fields[str(h ^ 2)] = f
        twin_op = {"file": p["file"], "hash": str(p["hash"]), "twin": str(h ^ 2), "set": {"Presence": t_pres},
                   **_keeps_phive_id(p)}
    rec = {"file": p["file"], "hash": str(p["hash"]), "presence": p_pres, "save_on_break": not sets_bit_on_pickup(actor),
           "twin": twin_op and twin_op["twin"], "twin_presence": twin_op and t_pres, "rows": fields}
    return sets, twin_op, fields, rec


# TWIN_PRESENCE. A Presence with IsCheckLazy true is re-checked while the player is there. Vanilla's Graveyard plants
# (GraveYard_RoyalFamilyTomb_Open) vanish the moment the tomb opens, and the Death Mountain owl and the tektites
# (Get_StoneOfFire_TektiteDelete) the moment their flag is set. With IsCheckLazy false it's checked when the level loads
# (vanilla's Sequence_IsChildhood soils, the scarecrows).
# So a twin is non-lazy, and the vanilla object stands there from the next visit, the way OoTR and Ship of Harkinian
# bring a checked pot back when the room reloads. Lazy twins popped in the moment the item was taken, or with a token
# pot the moment it broke. The checked original stays lazy, so it leaves at once and can't come back holding its item.
# A flagless spot's twin waits for the visit too (VISIT). Its spot has a visit bit of its own (FLAGLESS_VISIT0 and up,
# by location name), which the get scene sets just before the borrowed flag (_songs_trade_lake._heart_branch), and its
# Presence is FLAGLESS_EXP, "the borrowed flag and not this visit's bit".
FLAGLESS_VISIT0 = 2048
FLAGLESS_EXP = "RandoFlv_{:04d}"


def flagless_visits(names):
    """{location: its VISIT_ARRAY bit} of the flagless spots `names`."""
    return {n: FLAGLESS_VISIT0 + i for i, n in enumerate(sorted(names))}


def _flagless_twin(p, flag, visit=None):
    """The twin op of a respawning flagless object. It has no save row, so it respawns on every load like theirs did.
    With its spot's visit bit, its Presence is FLAGLESS_EXP (VISIT)."""
    rows, _ = _gd_index()
    h = int(p["hash"])
    t = next(h ^ k for k in TWIN_SALT if (h ^ k) not in rows and str(h ^ k) not in _vanilla_level(p["file"]))
    name = flag if visit is None else FLAGLESS_EXP.format(visit)
    return {"file": p["file"], "hash": str(p["hash"]), "twin": str(t),
            "set": {"Presence": {"FlagName": name, "IsCheckLazy": False, "IsNegation": False}},  # TWIN_PRESENCE
            **_keeps_phive_id(p)}  # BAKED_TYPES


# Flagless pickups
# Ammo from trees showed up without the count popup when it went through the carrier. So junk with a quiet touch pickup
# of its own (ammo, rupees, recovery hearts) at a flagless spot drops as that pickup, like at checked spots, instead of
# the carrier and the get scene. Flagless spots are trees, bushes, respawning pots and grass and Gerudo hanging signs,
# none of which has a save row of its own.
# The spot gets a CHECKED_ARRAY bit (the respawn model's array and counter) in place of a borrowed flag. Its placements
# name it in DROP_CHK_KEY and every dropper hands it to the drop (the presence kinds through their base type's root AI,
# trees through _tree_edits). The pickup sets VISIT_ARRAY[bit] then CHECKED_ARRAY[bit] when taken (pickup_save_ops), so
# the check is recorded on take, never at the break.
# The object then drops nothing more. A presence kind is gone from the next load, since its Presence is not CHECKED_EXP,
# non-lazy like the borrowed-flag version (a sign doesn't vanish in front of Link), and its vanilla twin stands there
# (CHECKED_EXP and not this visit's VISIT bit). A tree's DROP_FLAG_KEY names CHECKED_ARRAY and its gate reads its own
# bit (_tree_edits), so once the item is taken it counts as already shaken. If you leave the item behind it's back from
# the next load (no row, the object respawns at every load), so nothing is lost and nothing repeats.
# Anything else (major items, bombchus, ice traps, Nothing) keeps the carrier. Plan "_drops_flagless_own";
# verify_flagless_own.
FLAGLESS_OWN_TYPES = frozenset(set(TOUCH_AMMO) | {"Obj_Rupee_Green", "Obj_Rupee_Blue", "Obj_Rupee_Red",
                                                  "Obj_Rupee_Purple", "Obj_Rupee_Gold", "Obj_Heart"})


def flagless_own_actor(entry, item):
    """The pickup OoTR item `item` drops as itself at flagless spot `entry` (Flagless pickups), or None (the
    carrier)."""
    actor = DROP_ACTOR.get(item)
    if actor not in FLAGLESS_OWN_TYPES or actor not in PICKUP_SAVERS or not flagless_capable(entry):
        return None
    return actor


def _flagless_own_exps(bit):
    """(the original's expression name, steps), (the twin's name, steps) for a flagless spot's bit (Flagless
    pickups)."""
    exp = CHECKED_EXP.format(bit)
    return (exp, [[8, CHECKED_ARRAY, bit]]), (f"{exp}_V", [[8, CHECKED_ARRAY, bit], [8, VISIT_ARRAY, bit], [5], [3]])


def _flagless_bit_twin(p, exp_name):
    """The vanilla twin of a respawning flagless object whose spot answers to a bit (Flagless pickups). It has no save
    row, so it respawns on every load like theirs did, and its Presence is `exp_name` (checked and not this visit),
    non-lazy."""
    rows, _ = _gd_index()
    h = int(p["hash"])
    t = next(h ^ k for k in TWIN_SALT if (h ^ k) not in rows and str(h ^ k) not in _vanilla_level(p["file"]))
    return {"file": p["file"], "hash": str(p["hash"]), "twin": str(t),
            "set": {"Presence": {"FlagName": exp_name, "IsCheckLazy": False, "IsNegation": False}},
            **_keeps_phive_id(p)}


def flagless_capable(entry):
    """True if every object of this drop spot has no save flag of its own and a type that can hold a flagless
    drop (FLAGLESS_DROPPERS, or a PICKUP_SAVE_DROPPERS type whose placement has no flag)."""
    rows = entry.get("placements", [])
    return bool(rows) and entry.get("kind") == "drop" and all(
        r["flag"] is None and r["actor"] in FLAGLESS_DROPPERS for r in rows)


def saves_on_pickup(actor):
    return actor in PICKUP_SAVERS or actor in SAVES_ALREADY


# A dropper whose DeathParam is the shared _DP_EVENT file (13 packs, also Dampe's soil, the graveyard rock and the
# respawning pots) gets a copy of it under this path, pointed at ScrubBusiness, and the ActorParam that names its
# DeathParam names the copy instead. The shared file itself stays vanilla.
DP_SCRUB = "Component/DeathParam/RandoPickupSave.game__component__DeathParam.bgyml"


def _chain(files, actor):
    """[(ActorParam path, its Components)] of `actor` from its own pack's files, leaf first."""
    from romtools import byml_load
    out, cur = [], actor
    while cur:
        path = f"Actor/{cur}.engine__actor__ActorParam.bgyml"
        if path not in files or any(p == path for p, _ in out):
            break
        root = byml_load(files[path], allow_big=True)[0]
        out.append((path, root.get("Components") or {}))
        par = root.get("$parent")
        cur = par.split("/")[-1].split(".")[0] if par else None
    return out


def _death_owner(files, actor):
    """(ActorParam path that sets the actor's DeathRef, the value) along its chain, or (None, None)."""
    for path, comps in _chain(files, actor):
        if "DeathRef" in comps:
            return path, comps["DeathRef"]
    return None, None


def _death_ops(fs, droppers, romfs):
    """"packs" ops pointing the DeathParam of these dropper types at DP_SCRUB (see above), with every other type
    sharing the edited ActorParam path kept on its own DeathParam."""
    from romtools import sarc_files
    import packpaths
    owners = {}
    for actor in sorted(droppers):
        path, ref = _death_owner(sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs")), actor)
        if path is None or ref.lstrip("?") != _DP_EVENT:
            raise DropPlanError(f"{actor}: its DeathParam is not {_DP_EVENT} ({ref})")
        owners[path] = ref
    ops, keep = [], {}
    for path, ref in sorted(owners.items()):
        ops.append({"pack": "*", "file": path, "set": {"Components.DeathRef": "?" + DP_SCRUB}})
        for pk in packpaths.carriers(path, romfs):
            files = sarc_files(fs.read(pk))
            if _DP_EVENT not in files:
                raise DropPlanError(f"{pk}: holds {path} but not {_DP_EVENT} to copy")
            ops.append({"pack": pk, "file": DP_SCRUB, "new_from": _DP_EVENT, "set": {"DeathProcedures": SCRUB_REF}})
            actor = pk.rsplit("/", 1)[-1].replace(".pack.zs", "")
            if actor in droppers or not any(p == path for p, _ in _chain(files, actor)):
                continue
            own, _ = _death_owner(files, actor)
            leaf = f"Actor/{actor}.engine__actor__ActorParam.bgyml"
            if own == path and leaf != path:  # actors inheriting the edited ref get their vanilla DeathParam back
                keep[leaf] = ref
                # A direct owner can safely inherit the new break behavior (e.g. grass A_01 with only A_03 in play).
    for leaf, ref in sorted(keep.items()):
        ops.append({"pack": "*", "file": leaf, "set": {"Components.DeathRef": ref}})
    return ops


# Any item from a drop (scene drops)
# A drop spot can give any item the get scene can (remake_drop_contents "all", my rule, same as Ship of Harkinian). Its
# object drops the disguise carrier (DISGUISE_ACTOR, a heart piece), which has to know which spot it came from. A
# dropped actor has no placement Name, but the checked-on-pickup pipeline already hands it values from its dropper
# (QueryBlackboardOverwriteParamAdd*).
# So each such placement gets a number of its own, the F32 instance parameter DROP_TAG_KEY, added to the shared Drop
# table (every dropper reads Drop__DropActor from it). Its type's root AI reads it (QueryBlackboardGetF32,
# BlackboardType 1, the actor's own table keys, like Enemy_BabyDodongo's brain does) and adds it to the drop's overwrite
# param as PICKUP_TAG_KEY (QueryBlackboardOverwriteParamAddF32, like the falling rocks hand FallTime). That's a key the
# carrier's DropActorRespawnData table gets.
# The carrier's event AI answers the get scene's tag query with the spot's tag when its PICKUP_TAG_KEY equals it
# (QueryMathEqualF32, since there's no F32 -> S32 cast), its root AI shows that spot's item, and the get-scene hook
# gives it like at a heart spot.
DROP_TABLE = "Component/Blackboard/BlackboardParamTable/Drop.engine__component__BlackboardParamTable.bgyml"
CARRIER_TABLE = ("Component/Blackboard/BlackboardParamTable/DropActorRespawnData.engine__component__"
                 "BlackboardParamTable.bgyml")
DROP_TAG_KEY = "Drop__RandoTag"   # the dropper placement's number (Drop table, instance parameter)
PICKUP_TAG_KEY = "RandoDropTag"   # what its drop receives
SCENE_DROP_TAG0 = 200  # One tag per scene-drop item, starting at 200.
# Tags 5-68 are heart spots, 69 is the disguise and 70-129 are the rupees with stage hearts.
# The heart pickups' shared root AI grows with every look, and their event AI with every answer. 387 nodes worked, and a
# seed with ~80 scene-drop items takes it near 800. So their actor rows get this much more instance heap as a precaution
# (vanilla is 155-161 KB, and an ice-trap attacker with 0 extra bytes is what failed before).
HEART_ACTORS = ("Obj_Heart_Piece", "Obj_GerudoValley_Heart_Piece", "Obj_Heart_Piece_Digging_Hole",
                "Obj_Heart_Piece_MiniGame")
HEART_HEAP_EXTRA = 256 * 1024


def heart_heap_ops(romfs=DEFAULT_ROMFS):
    """make_patch "byml" ops giving the heart pickups HEART_HEAP_EXTRA more instance heap (RSDB ActorInfo)."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    heap = {r.get("__RowId"): r.get("InstanceHeapSize") for r in byml_load(fs.read(ACTOR_INFO))[0]}
    return [{"file": ACTOR_INFO, "set": {f"[__RowId={a}].InstanceHeapSize": int(heap[a]) + HEART_HEAP_EXTRA}}
            for a in HEART_ACTORS if heap.get(a)]


# Falling pickups
# A tree's item hung in its branches, and in test_guardroom a pot thrown at a wall left its item up there. A drop is
# created where its dropper says. A tree drops at its canopy bone (Land_Tree_BeechMiddle_A_01.root:
# QueryShakingTreeCalcDropPos -> OneShotDropSetForceDropPos), a pot where it breaks, a Gold Skulltula where it dies.
# Only its main rigid body brings it down.
# Every pickup the game drops falls (rupees, hearts, ammo, keys, shields, tunics). They have a Dynamic body,
# Phive/RigidBodyEntityParam/DropItem_0 (MotionType murmur3 "Dynamic", layer SmallObject, hit mask
# HitOnlyGroundAndObject, rotation locked), and a DropBoundParam. The heart pickups, the Fire Arrows pickup and the
# token have a Kinematic body and no DropBoundParam, so they stay where they're created, the way a placed heart piece
# hovers (OotrR found the same for tokens: ootrr_findings G1). So:
#   - the scene-drop carrier (DISGUISE_ACTOR) and the Fire Arrows pickup, when an object drops it, get the dropped
#     pickups' body through fall_ops (new files under FALL_NAME in its own pack only, the shared heart-piece files stay
#     as they are). The carrier is a reserved type, and its one placement, the GV waterfall heart piece, rests 0.40 m
#     above its ledge.
#   - a hovering pickup of any other type (heart piece, heart container, Ruto's Letter) never drops as itself where the
#     carrier can carry it (parity/drops.py _allowed_direct). The item goes through the get scene instead, like tokens
#     already did. A Gold Skulltula's own token keeps the vanilla behaviour and stays where the skulltula died.
# verify_falls reads every dropped pickup type of a built patch back.
FALL_SRC = "Pack/Actor/Obj_Rupee_Green.pack.zs"  # vanilla copies of the dropped pickups' physics come from here
FALL_BODY = "Phive/RigidBodyEntityParam/DropItem_0.phive__RigidBodyEntityParam.bgyml"
FALL_CCOL = "Phive/ContactCollectionEntityParam/HitOnlyGroundAndObject.phive__ContactCollectionEntityParam.bgyml"
FALL_BOUND = "GameParameter/DropBoundParam/Obj_Item_Base.game__drop__DropBoundParam.bgyml"
FALL_GPC = "GameParameter/GamePhysicsControllerParam/Obj_Item_Base.game__physics__GamePhysicsControllerParam.bgyml"
FALL_NAME = "RandoFall_{}"  # the new PhysicsParam, ControllerSet and GameParameterTable of a type given the body
FALL_TYPES = (DISGUISE_ACTOR, "Obj_Arrow_Fire")  # given the body when a plan drops them from an object
# pickups that hover where they're created and don't get the body. Their types are placed or created by events in the
# vanilla game (a freestanding heart piece, Dm_Goron_0045's heart piece, the boss heart containers, the lake's bottle).
# Where the carrier can carry them they go through it (parity/drops.py _allowed_direct).
HOVERING_PICKUPS = ("Obj_Heart_Piece", "Obj_Heart_Container", "Obj_Bottle_Letter", "Obj_Token_Gold")
FLIES = {"Obj_Fairy": "a fairy flies (no rigid body; it moves by its own AI, as the vanilla drop does)"}
GAME_ACTOR_INFO = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"
MOTION_DYNAMIC = 3672686866  # murmur3 "Dynamic" (romtools.murmur3_32); "Kinematic" is 4269567940


def _work(inner):
    """A pack file's path as a reference names it ("Work/...gyml")."""
    return "Work/" + inner[:-len(".bgyml")] + ".gyml"


def _inner(ref):
    """A reference ("?...bgyml" or "Work/...gyml") as the path of the file inside a pack."""
    ref = ref.lstrip("?")
    if ref.startswith("Work/"):
        ref = ref[len("Work/"):]
    return ref[:-len(".gyml")] + ".bgyml" if ref.endswith(".gyml") else ref


def _components(files, actor):
    """`actor`'s merged ActorParam Components (leaf wins), from its own pack's files."""
    out = {}
    for _, comp in reversed(_chain(files, actor)):
        out.update(comp)
    return out


def _main_body(files, ctrl):
    """(index of the main rigid body in RigidBodyEntityNamePathAry, index of its contact collection in
    CColEntityNamePathAry, the controller set) of a ControllerSetParam file; (None, None, set) without one."""
    from romtools import byml_load
    cs = byml_load(files[ctrl], allow_big=True)[0]
    main = next((a for a in cs.get("AliasEntityList", []) if a.get("AliasEntity") == "Main"), None)
    if main is None:
        return None, None, cs
    body = next((i for i, e in enumerate(cs.get("RigidBodyEntityNamePathAry", []))
                 if e.get("Name") == main.get("RigidBodyName")), None)
    ccol = next((i for i, e in enumerate(cs.get("CColEntityNamePathAry", []))
                 if e.get("Name") == main.get("ControllerName")), None)
    return body, ccol, cs


def fall_ops(actors, romfs=DEFAULT_ROMFS):
    """make_patch sections that give each type of `actors` (FALL_TYPES) the dropped pickups' body, so its drop falls to
    the ground. Returns {"packs": [...], "byml": [...]}.
    In its own pack it gets a copy of its ControllerSet whose main rigid body is FALL_BODY and whose contact collection
    is FALL_CCOL (its shapes, sensor and controller stay), and a PhysicsParam naming that set. If its parameter table
    has none, it also gets a copy of the table with FALL_BOUND and FALL_GPC. Its ActorParam names the two, and its
    GameActorInfo row names the body's layer. Vanilla files are copied unchanged (FALL_SRC)."""
    from romtools import Romfs, sarc_files, byml_load
    import packpaths
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    src = sarc_files(fs.read(FALL_SRC))
    for f in (FALL_BODY, FALL_CCOL, FALL_BOUND, FALL_GPC):
        if f not in src:
            raise DropPlanError(f"fall_ops: {FALL_SRC} holds no {f}")
    layer = byml_load(src[FALL_BODY])[0]["LayerEntity"]
    out = {"packs": [], "byml": []}
    for actor in sorted(set(actors)):
        if actor not in FALL_TYPES:
            raise DropPlanError(f"fall_ops: {actor} is not one of FALL_TYPES")
        ap = f"Actor/{actor}.engine__actor__ActorParam.bgyml"
        packs = list(packpaths.carriers(ap, romfs))
        if packs != [f"Pack/Actor/{actor}.pack.zs"]:
            raise DropPlanError(f"fall_ops: {ap} is held by {packs}, not its own pack alone")
        pack = packs[0]
        files = sarc_files(fs.read(pack))
        comp = _components(files, actor)
        phys, table = _inner(comp["PhysicsRef"]), _inner(comp["GameParameterTableRef"])
        ctrl = _inner(byml_load(files[phys])[0]["ControllerSetPath"])
        body, ccol, cs = _main_body(files, ctrl)
        if body is None or ccol is None or "$parent" in cs:
            raise DropPlanError(f"fall_ops: {actor}'s {ctrl} has no main rigid body and contact collection of its own")
        name = FALL_NAME.format(actor)
        new_phys = f"Component/Physics/{name}.engine__component__PhysicsParam.bgyml"
        new_ctrl = f"Phive/ControllerSetParam/{name}.phive__ControllerSetParam.bgyml"
        new_table = f"GameParameter/GameParameterTable/{name}.engine__actor__GameParameterTable.bgyml"
        out["packs"] += [{"pack": pack, "file": f, "from_pack": FALL_SRC} for f in (FALL_BODY, FALL_CCOL)]
        out["packs"].append({"pack": pack, "file": new_ctrl, "new_from": ctrl, "set": {
            f"RigidBodyEntityNamePathAry.{body}.FilePath": _work(FALL_BODY),
            f"CColEntityNamePathAry.{ccol}.FilePath": _work(FALL_CCOL)}})
        out["packs"].append({"pack": pack, "file": new_phys, "new_from": phys,
                             "set": {"ControllerSetPath": _work(new_ctrl)}})
        sets = {"Components.PhysicsRef": "?" + new_phys}
        tc = byml_load(files[table])[0]
        if "$parent" in tc:
            raise DropPlanError(f"fall_ops: {actor}'s {table} has a parent (not handled)")
        add = {k: f for k, f in (("DropBoundParam", FALL_BOUND), ("GamePhysicsControllerParam", FALL_GPC))
               if k not in (tc.get("Components") or {})}
        if add:
            out["packs"] += [{"pack": pack, "file": f, "from_pack": FALL_SRC} for f in add.values()]
            out["packs"].append({"pack": pack, "file": new_table, "new_from": table,
                                 "set": {f"Components.{k}": "?" + f for k, f in add.items()}})
            sets["Components.GameParameterTableRef"] = "?" + new_table
        if actor in TOUCH_TYPES:
            touch, tsets = _touch_ops(fs, pack, files, comp, actor, src)
            out["packs"] += touch
            sets.update(tsets)
        out["packs"].append({"pack": "*", "file": ap, "set": sets})
        out["byml"].append({"file": GAME_ACTOR_INFO, "set": {f"[__RowId={actor}].MainRigidBodyLayer": layer}})
    return out


# Pickup by touch
# Some pickups need a button press and some you just walk into. Item_Catch (AttentionSenderParam PickUpItem, what heart
# pieces and the carrier use) needs the button. Auto_Item_Catch (AutoPickUpItem) is the touch one that rupees, ammo,
# keys, tunics and the moat's Ocarina of Time use. It also reads the actor's IsEnableAttention blackboard key from the
# DropItem table, and heart piece tables don't have that key.
# The attention client only sets the reach though. What actually makes Link grab it on contact is DefaultAutoGet in the
# PouchContentParam, and AutoPickUpItem without it still asks for the button. That's why pot items, bombs, nuts, tokens
# and souls kept showing "Take". In vanilla, Obj_Mask_Amiibo0/1 say DefaultAutoGet false outright, and the moat's
# Ocarina of Time and the Treasure Chest Game key have none.
# What follows the take is up to GetType. With none it's added with no scene (rupees, ammo). A GetType plays the get
# scene (Dm_SY_Get, whose EventTriggerAddOwnToPouch adds it), every time with PlayGetEventManyTimes. The vanilla touch
# items with a get scene are Obj_Token_Gold (DefaultAutoGet, the heart piece's GetType, PlayGetEventManyTimes) and
# Obj_Dungeon_SmallKey.
# So every touch actor here (_touch_ops, touch_attention_ops) also gets a copy of its PouchContentParam
# (RandoTouch_<actor>, _autoget_ops) with DefaultAutoGet and PlayGetEventManyTimes true. The GetType is kept, so the get
# scene, whose hook gives the real item, plays on every touch. IsPlayGetEventPouchMax true too: the game skips a get
# event when the pickup's own pouch is full, and the carrier's own pouch (a heart piece) has nothing to do with the
# item it gives (OotrR set both on their upgrade pickups for that, their PR #140; the game's ammo and hearts have it).
# The carrier also gets the touch attention plus a copy of the DropItem table, listed after its own tables. The copy is
# renamed and has IsEnableAttention true from the start, since nothing in the carrier's AI would raise it. Junk given by
# the carrier (QUIET_JUNK) then skips the hold-up and the window in the hook (parity/_songs_trade_lake.py quiet give).
TOUCH_TYPES = (DISGUISE_ACTOR,)
# The heart pieces placed in levels (vanilla ones, and the freestanding rupees made heart pieces, the "get_scene" spots)
# are taken by touch too, like OoTR's freestanding items. Otherwise ammo at such a spot asks for a button and gets held
# up. Obj_Heart_Piece's ActorParam is in three packs (its own, the carrier's and Dampe's digging hole's), so
# heart_touch_ops gives each of them the touch attention and blackboard (_touch_ops) and sets the ActorParam the same
# everywhere (packpaths rule). A heart piece still plays the get scene on touch (no DefaultAutoGet). A real item is held
# up as before, and junk is given quietly (parity/drops.py "quiet").
HEART_TOUCH_TYPES = ("Obj_Heart_Piece",)
TOUCH_ATTENTION = "Component/AttentionSenderParam/AutoPickUpItem.game__component__AttentionSenderParam.bgyml"
TOUCH_CLIENTS = ("Attention/ClientParam/Auto_Item_Catch.game__attention__ClientParam.bgyml",
                 "Attention/ClientParam/LookOnly_Middle_Small.game__attention__ClientParam.bgyml")
TOUCH_TABLE_SRC = "Component/Blackboard/BlackboardParamTable/DropItem.engine__component__BlackboardParamTable.bgyml"
TOUCH_KEY = "IsEnableAttention"
TOUCH_ROOT_AI = "Work/AI/Root/DropItem.root.ain"  # used by Obj_Rupee_Green and Obj_Dungeon_SmallKey, raises TOUCH_KEY
TOUCH_NAME = "RandoTouch_{}"
# OoTR items a carrier gives by touch with no hold-up and no window, the way their own pickup does. Rupees, recovery
# hearts and ammo are DefaultAutoGet pickups (Ship of Harkinian's "Skip Get Item Animations: Junk Items").
HEAL_UI = ("UISystemActor.EventTriggerReserveRecoverOrAddHeartGauge", "UISystemActor.EventTriggerSetDisplayHeartGauge",
           "UISystemActor.EventStartRecoverOrAddHeartGauge")  # the heart gauge of a heal (Dm_SY_Get CheckHeart)
QUIET_JUNK = frozenset({"Rupee (1)", "Rupees (5)", "Rupees (20)", "Rupees (50)", "Rupees (200)", "Recovery Heart",
                        "Rupee (Treasure Chest Game) (1)", "Rupees (Treasure Chest Game) (5)",
                        "Rupees (Treasure Chest Game) (20)", "Rupees (Treasure Chest Game) (50)",
                        "Arrows (5)", "Arrows (10)", "Arrows (30)", "Bombs (5)", "Bombs (10)", "Bombs (20)",
                        "Bombchus (5)", "Bombchus (10)", "Bombchus (20)", "Bombchus", "Deku Nuts (5)",
                        "Deku Nuts (10)", "Deku Stick (1)", "Deku Seeds (30)"})


def _touch_ops(fs, pack, files, comp, actor, src):
    """Pack ops and ActorParam sets that turn `actor` into a touch pickup."""
    from romtools import byml_load
    for f in (TOUCH_ATTENTION,) + TOUCH_CLIENTS + (TOUCH_TABLE_SRC,):
        if f not in src:
            raise DropPlanError(f"touch: {FALL_SRC} holds no {f}")
    table = byml_load(src[TOUCH_TABLE_SRC])[0]
    rows = table.get("BlackboardParamBoolArray", [])
    idx = next((i for i, r in enumerate(rows) if r.get("BBKey") == TOUCH_KEY), None)
    if idx is None:
        raise DropPlanError(f"touch: {TOUCH_TABLE_SRC} has no {TOUCH_KEY}")
    info = _inner(comp["BlackboardRef"])
    tables = list(byml_load(files[info])[0].get("BlackboardParamTables", []))
    have = {r.get("BBKey") for t in tables if _inner(t) in files
            for arr in byml_load(files[_inner(t)])[0].values() if isinstance(arr, list) for r in arr}
    new = {r.get("BBKey") for arr in table.values() if isinstance(arr, list) for r in arr}
    if have & new:
        raise DropPlanError(f"touch: {actor}'s blackboard already has {sorted(have & new)}")
    name = TOUCH_NAME.format(actor)
    new_table = f"Component/Blackboard/BlackboardParamTable/{name}.engine__component__BlackboardParamTable.bgyml"
    new_info = f"Component/Blackboard/BlackboardInfo/{name}.engine__component__BlackboardInfo.bgyml"
    ops = [{"pack": pack, "file": f, "from_pack": FALL_SRC} for f in (TOUCH_ATTENTION,) + TOUCH_CLIENTS]
    ops.append({"pack": pack, "file": new_table, "from_pack": FALL_SRC, "new_from": TOUCH_TABLE_SRC,
                "set": {f"BlackboardParamBoolArray.{idx}.InitVal": True}})
    ops.append({"pack": pack, "file": new_info, "new_from": info,
                "set": {"BlackboardParamTables": tables + [_work(new_table)]}})
    auto, asets = _autoget_ops(pack, files, comp, actor)
    return ops + auto, {"Components.AttentionSenderRef": "?" + TOUCH_ATTENTION, "Components.BlackboardRef": "?" + new_info,
                        **asets}


TOUCH_POUCH = "Component/PouchContentParam/{}.game__component__PouchContentParam.bgyml"
TOUCH_POUCH_SET = {"DefaultAutoGet": True, "PlayGetEventManyTimes": True, "IsPlayGetEventPouchMax": True}


def _pouch_content(files, ref):
    """A PouchContentParam reference's merged values (leaf wins) from a pack's files; {} if it isn't there."""
    from romtools import byml_load
    out, ref, seen = {}, _inner(ref or ""), set()
    while ref and ref in files and ref not in seen:
        seen.add(ref)
        d = byml_load(files[ref])[0]
        out = {**d, **out}
        ref = _inner(d["$parent"]) if d.get("$parent") else None
    out.pop("$parent", None)
    return out


def _autoget_ops(pack, files, comp, actor):
    """Pack ops and ActorParam sets that make `actor` a touch pickup that keeps its get scene (Pickup by touch). It gets
    a copy of its PouchContentParam, RandoTouch_<actor>, with TOUCH_POUCH_SET. Its GetType stays, so the get scene still
    plays."""
    ref = comp.get("PouchContentRef")
    if not ref or _inner(ref) not in files:
        raise DropPlanError(f"touch: {actor} has no PouchContentParam in {pack}")
    if not _pouch_content(files, ref).get("GetType"):
        raise DropPlanError(f"touch: {actor}'s PouchContentParam has no GetType: a touch would add it with no get "
                            f"scene, and the scene's hook gives the real item")
    new = TOUCH_POUCH.format(TOUCH_NAME.format(actor))
    return ([{"pack": pack, "file": new, "new_from": _inner(ref), "set": dict(TOUCH_POUCH_SET)}],
            {"Components.PouchContentRef": "?" + new})


# Reachable drop positions
# tools/rando/landing_check.py follows every drop placement's fall (data/rando/drop_landings.json). An object high over
# a pit, deep water or a cut-off ledge would drop its item where Link can't follow. For those the check proposes
# "drop_at", the walkable floor nearest under the object that Link reaches from the floors around it.
# The placement then names that point (DROP_AT_KEY and DROP_AT_XYZ, instance parameters of the Drop table) and its
# type's root AI makes the drop there. It runs OneShotDropSetForceDropPos every frame while the placement asks for it.
# That's the trees' own drop step, and what Keese and Guay do when they die in the air, with QueryCalcSafeDropPos. So
# the point the death procedure's drop reads is set when the object dies, like Keese set it at the start of their death.
# Other placements read one Bool once (OutputOnlyOnEnter) and run nothing more.
DROP_AT_KEY = "Drop__RandoDropAt"
DROP_AT_XYZ = ("Drop__RandoDropX", "Drop__RandoDropY", "Drop__RandoDropZ")
DROP_AT_TYPES = {"Enemy_Skulltula_Gold": (GS_PACK, GS_AI)}
DROP_AT_SRC = {"getbool": ({"pack": AI_GLOBAL, "file": "AI/Enemy_Dodongo.brain.landbattale.module.ainb"}, 35),
               "vec": ({"pack": AI_GLOBAL, "file": "AI/Capstan.module.ainb"}, 56),
               "force": ({"pack": "Pack/Actor/Obj_Tree_A_01.pack.zs", "file": "AI/Land_Tree_BeechMiddle_A_01.root.ainb"},
                         59)}
LANDINGS = os.path.join(HERE, "data", "rando", "drop_landings.json")


@lru_cache(maxsize=None)
def drop_landings():
    """{file#hash: landing record} (tools/rando/landing_check.py); empty if the file isn't there."""
    if not os.path.exists(LANDINGS):
        return {}
    with open(LANDINGS, encoding="utf-8") as f:
        return json.load(f).get("spots", {})


def drop_at_of(p):
    """[x, y, z] where placement `p`'s drop is to be made instead of under it, or None."""
    rec = drop_landings().get(f"{p['file']}#{p['hash']}") or {}
    if rec.get("verdict") == "bad" and rec.get("drop_at") and (
            p.get("actor") in DROP_AT_TYPES or p.get("category") == "gold_skulltula"):
        return rec["drop_at"]
    return None


def drop_at_ops(types):
    """make_patch "ainb" ops for the Drop table's DROP_AT_* instance parameters (every pack holding it) and the
    drop-position branch in each type's root AI (Reachable drop positions)."""
    out = [{"pack": "*", "bb_params": [{"table": DROP_TABLE, "type": "Bool", "key": DROP_AT_KEY, "init": False,
                                        "instance": True}] +
            [{"table": DROP_TABLE, "type": "F32", "key": k, "init": 0, "instance": True} for k in DROP_AT_XYZ]}]
    own_src, own = LOOK_SRC["own"]
    bsel, nothing = own["BoolSelector"], own["OneshotDoNothing"]
    (gb_src, gb), (vec_src, vec), (f_src, force) = DROP_AT_SRC["getbool"], DROP_AT_SRC["vec"], DROP_AT_SRC["force"]
    for t in sorted(types):
        pack, ai_file = DROP_AT_TYPES[t]
        at, sel, put, mk, idle = f"dagate:{gb}", f"dasel:{bsel}", f"daput:{force}", f"davec:{vec}", f"daidle:{nothing}"
        edits = [{"copy": {"from": gb_src, "nodes": [gb], "label": "dagate", "follow": False}},
                 {"set_property": {"node": at, "name": "BlackboardType", "value": 1}},
                 {"set_property": {"node": at, "name": "BlackboardKey", "value": DROP_AT_KEY}},
                 {"set_property": {"node": at, "name": "OutputOnlyOnEnter", "value": True}},
                 {"copy": {"from": own_src, "nodes": [bsel], "label": "dasel", "follow": False}},
                 {"feed": {"from": at, "output": "Bool", "to": sel, "input": "Input"}},
                 {"copy": {"from": f_src, "nodes": [force], "label": "daput", "follow": False}},
                 {"set_property": {"node": put, "name": "ExecuteEveryFrame", "value": True}},
                 {"copy": {"from": vec_src, "nodes": [vec], "label": "davec", "follow": False}},
                 {"link": {"from": mk, "output": "Vector3f", "to": put, "input": "Pos"}}]
        for axis, key in zip("XYZ", DROP_AT_XYZ):
            lab = f"da{axis.lower()}"
            ref = f"{lab}:{TAG_SRC['get'][1]['QueryBlackboardGetF32']}"
            edits += [{"copy": {"from": TAG_SRC["get"][0], "nodes": [TAG_SRC["get"][1]["QueryBlackboardGetF32"]],
                                "label": lab, "follow": False}},
                      {"set_property": {"node": ref, "name": "BlackboardType", "value": 1}},
                      {"set_property": {"node": ref, "name": "BlackboardKey", "value": key}},
                      {"set_property": {"node": ref, "name": "OutputOnlyOnEnter", "value": True}},
                      {"feed": {"from": ref, "output": "F32", "to": mk, "input": axis}}]
        edits += [{"add_child": {"parent": sel, "child": put, "name": "True"}},
                  {"copy": {"from": own_src, "nodes": [nothing], "label": "daidle", "follow": False}},
                  {"add_child": {"parent": sel, "child": idle, "name": "False"}},
                  {"wrap": {"command": "Root"}},  # a Simultaneous of its own, so every vanilla node stays as it was
                  {"add_child": {"parent": "@Root", "child": sel}}]
        out.append({"pack": "*", "file": ai_file, "edits": edits})
    return out


def verify_drop_at(patch_dir, plan, romfs=DEFAULT_ROMFS):
    """Reads a built patch back (Reachable drop positions) and returns [problem], n.
    Every placement the plan makes drop somewhere else has to carry DROP_AT_KEY true and the point in the patched level
    file. Its type's pack has to declare the four keys as instance parameters of the Drop table, and its root AI needs a
    OneShotDropSetForceDropPos that runs every frame, fed by QueryMathMakeVector3fFromXYZ of the three point keys, under
    a BoolSelector on DROP_AT_KEY."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    ops = [op for op in plan.get("placements", []) if (op.get("set") or {}).get(f"Dynamic.{DROP_AT_KEY}")]
    if not ops:
        return [], 0
    bad, levels = [], {}
    m = _map()
    cat = {(p["file"], str(p["hash"])): p for sec in ("drops", "new") for e in m[sec].values()
           for p in e.get("placements", [])}
    types = set()
    for op in ops:
        if op["file"] not in levels:
            levels[op["file"]] = {str(a.get("Hash")): a for a in byml_load(new.read(op["file"]))[0]["Actors"]}
        dyn = (levels[op["file"]].get(str(op["hash"])) or {}).get("Dynamic") or {}
        want = [float(op["set"][f"Dynamic.{k}"]) for k in DROP_AT_XYZ]
        if not dyn.get(DROP_AT_KEY) or any(abs(float(dyn.get(k, 0)) - v) > 1e-3 for k, v in zip(DROP_AT_XYZ, want)):
            bad.append(f"{op['file'].split('/')[-1]}#{op['hash']}: the level file doesn't make its drop at {want}")
        p = cat.get((op["file"], str(op["hash"]))) or {}
        types.add("Enemy_Skulltula_Gold" if p.get("category") == "gold_skulltula" else p.get("actor"))
    for t in sorted(types):
        if t not in DROP_AT_TYPES:
            bad.append(f"{t}: a placement makes its drop elsewhere, but the type has no drop-position branch")
            continue
        pack, ai_file = DROP_AT_TYPES[t]
        files = sarc_files(new.read(pack))
        rows = byml_load(files[DROP_TABLE])[0] if DROP_TABLE in files else {}
        declared = {r.get("BBKey") for arr in rows.values() if isinstance(arr, list) for r in arr
                    if r.get("IsInstanceParam")}
        missing = [k for k in (DROP_AT_KEY,) + DROP_AT_XYZ if k not in declared]
        if missing:
            bad.append(f"{pack}: its Drop table doesn't declare {missing}")
        a = ainb.Ainb(files[ai_file])

        def props(i):
            return {e["name"]: e["value"] for ty in ainb.PTYPES for e in a.nodes[i]["properties"][ty]}

        def src(i, name):
            return a._input(i, name)[1]["node"]
        ok = False
        for i, nd in enumerate(a.nodes):
            if nd["name"] != "OneShotDropSetForceDropPos" or not props(i).get("ExecuteEveryFrame"):
                continue
            v = src(i, "Pos")
            if v < 0 or a.nodes[v]["name"] != "QueryMathMakeVector3fFromXYZ":
                continue
            keys = []
            for axis in "XYZ":
                g = src(v, axis)
                keys.append(props(g).get("BlackboardKey") if g >= 0 and props(g).get("BlackboardType") == 1 else None)
            sel = next((j for j, m_ in enumerate(a.nodes) if m_["type"] == 7 and any(
                pl["node"] == i and pl["name"] == "True" for pl in m_["plugs"][ainb.PLUG_CHILD])), None)
            gate = src(sel, "Input") if sel is not None else -1
            if tuple(keys) == DROP_AT_XYZ and gate >= 0 and props(gate).get("BlackboardKey") == DROP_AT_KEY:
                ok = True
        if not ok:
            bad.append(f"{pack} {ai_file}: no drop-position branch reading {DROP_AT_KEY} and {DROP_AT_XYZ}")
    return bad, len(ops)


def _walk_scene(fc, start, flowcharts):
    """Every step reachable from event index `start` of flowchart `fc`, following calls into the same file. Returns
    [(kind, what, params)] with kind "action" ("Actor.Action"), "call" ("File:Entry") or "query"."""
    out, todo, seen = [], [(fc, start)], set()
    while todo:
        f, i = todo.pop()
        if i is None or i == 0xFFFF or (f["name"], i) in seen:
            continue
        seen.add((f["name"], i))
        e = f["events"][i]
        items = {k: v.get("value") for k, v in ((e.get("params") or {}).get("items") or {}).items()
                 if isinstance(v, dict)}
        if e["type"] == "action":
            a = f["actors"][e["actor"]]
            out.append(("action", f"{a['name']}.{a['actions'][e['action']]}", items))
        elif e["type"] == "switch":
            a = f["actors"][e["actor"]]
            out.append(("query", f"{a['name']}.{a['queries'][e['query']]}", items))
            todo += [(f, c["next"]) for c in e.get("cases") or []]
        elif e["type"] == "subflow":
            out.append(("call", f"{e.get('flowchart') or f['name']}:{e.get('entry_point')}", items))
            g = flowcharts.get(e.get("flowchart") or f["name"])
            if g is not None and e.get("entry_point") in g["entry_points"]:
                ep = g["entry_points"][e["entry_point"]]
                todo.append((g, ep if isinstance(ep, int) else ep.get("main", ep.get("event"))))
        elif e["type"] == "fork":
            todo += [(f, j) for j in e.get("forks") or []]
            todo.append((f, e.get("join")))
        todo.append((f, e.get("next")))
    return out


def verify_touch(patch_dir, plan, items, romfs=DEFAULT_ROMFS):
    """Reads a built patch back (Pickup by touch) and returns [problem], {"carrier": bool, "quiet": n tags, "held": n
    tags}.
    - The carrier, if the plan drops it. Its attention has to be a touch client (Auto_Item_Catch) whose blackboard check
      reads a key that one of its blackboard tables sets true from the start. Its pouch content needs DefaultAutoGet
      (taken by itself, no button), a GetType and PlayGetEventManyTimes, so every touch plays the get scene and the hook
      gives the real item. The same goes for the heart spots' heart pieces in every pack holding their ActorParam, and
      for the Lake Hylia Fire Arrows pickup when the patch makes it a touch pickup.
    - Every scene-drop tag whose item is QUIET_JUNK, in both get scenes. Its branch has to hand the item over with
      PouchSystemActor.EventTriggerAddOrRemovePouchContent and no get event, and call no hold-up, window or other scene
      (no call at all, no UISystemActor step)."""
    from romtools import Romfs, sarc_files, byml_load
    import evfl
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad, stats = [], {"carrier": False, "quiet": 0, "held": 0}
    used = any((op.get("set") or {}).get("Dynamic.Drop__DropActor") == DISGUISE_ACTOR for op in plan.get("placements", []))
    import packpaths
    touch_checks = ([(DISGUISE_ACTOR, DISGUISE_PACK)] if used else []) + [
        (a, p) for a in plan.get("_drops_heart_touch") or []
        for p in sorted(packpaths.carriers(f"Actor/{a}.engine__actor__ActorParam.bgyml", romfs))]
    fire = LAKE_LOOK["LH Sun"]["actor"]  # touch_attention_ops: its ActorParam in its own pack only
    fire_pack = f"Pack/Actor/{fire}.pack.zs"
    if os.path.exists(os.path.join(patch_dir, *fire_pack.split("/"))) and _inner(_components(sarc_files(new.read(fire_pack)), fire).get("AttentionSenderRef") or "") == TOUCH_ATTENTION:
        touch_checks.append((fire, fire_pack))
    for actor, pack in touch_checks:
        stats["carrier"] = stats["carrier"] or actor == DISGUISE_ACTOR
        files = sarc_files(new.read(pack))
        comp = _components(files, actor)
        who = f"{actor} ({os.path.basename(pack)})"

        def load(ref):
            k = _inner(ref or "")
            return byml_load(files[k])[0] if k in files else None
        att = load(comp.get("AttentionSenderRef"))
        clients = [load(c) for c in (att or {}).get("ClientList", [])]
        catch = next((c for c in clients if c and c.get("ClientName") == "Catch"), None)
        keys = {}
        for t in (load(comp.get("BlackboardRef")) or {}).get("BlackboardParamTables", []):
            for arr in (load(t) or {}).values():
                if isinstance(arr, list):
                    keys.update({r.get("BBKey"): r.get("InitVal") for r in arr if isinstance(r, dict)})
        if catch is None:
            bad.append(f"{who}: no Catch client in its attention ({comp.get('AttentionSenderRef')})")
        else:
            checks = catch.get("CheckList", [])
            fan = any((c.get("CheckTypeAreaFan") or {}).get("AttentionFanRadius") for c in checks)
            bb = [c["CheckBlackBoard"]["BlackBloardName"] for c in checks
                  if (c.get("CheckBlackBoard") or {}).get("BlackBloardName")]
            if fan and not bb:
                bad.append(f"{who}: its Catch client is the button one (Item_Catch), not a touch")
            # the vanilla touch pickups' own root AI (rupees, small keys, the moat's Ocarina of Time, the Fire Arrows)
            # raises IsEnableAttention once the item settles. Any other AI has to have it true from the start.
            raises = (load(comp.get("AIInfoRef")) or {}).get("RootAIRef") == TOUCH_ROOT_AI
            for k in bb:
                if keys.get(k) is not True and not (raises and k == TOUCH_KEY and k in keys):
                    bad.append(f"{who}: its touch client asks blackboard key {k}, which its tables "
                               f"{'set false' if k in keys else 'lack'}: it could never be taken")
        pc = _pouch_content(files, comp.get("PouchContentRef"))
        if pc.get("DefaultAutoGet") is not True:
            bad.append(f"{who}: its pouch content has no DefaultAutoGet: the touch attention alone still asks for "
                       f"the button (\"Take\")")
        if not pc.get("GetType"):
            bad.append(f"{who}: its pouch content has no GetType: a touch would add it with no get scene")
        if pc.get("PlayGetEventManyTimes") is not True:
            bad.append(f"{who}: no PlayGetEventManyTimes: the get scene (and the hook giving the real item) would "
                       f"play only the first time")
        if pc.get("IsPlayGetEventPouchMax") is not True:
            bad.append(f"{who}: no IsPlayGetEventPouchMax: a full pouch of the carrier's own kind would skip the get "
                       f"scene (and the hook giving the real item)")
    quiet = {t for n, t in (plan.get("_drops_scene_drops") or {}).items() if items.get(n) in QUIET_JUNK}
    spots = {t for n, t in (plan.get("_drops_quiet_spots") or {}).items() if items.get(n) in QUIET_JUNK}
    if set(plan.get("_drops_quiet_spots") or {}) - {n for n in items if items.get(n) in QUIET_JUNK}:
        bad.append("_drops_quiet_spots names a spot whose item isn't junk")
    quiet |= spots
    stats["held"] = len(set((plan.get("_drops_scene_drops") or {}).values()) - quiet)
    if not quiet:
        return bad, stats
    flows = {}
    for scene in HOOK_SCENES:
        for fc in evfl.Evfl(new.read(scene)).flowcharts:
            flows[fc["name"]] = fc
    for scene in HOOK_SCENES:
        name = os.path.basename(scene).split(".")[0]
        fc = flows[name]
        sw = next((e for e in fc["events"] if e["name"] == HOOK_SWITCH), None)
        if sw is None:
            bad.append(f"{name}: no tag switch {HOOK_SWITCH}")
            continue
        cases = {c["value"]: c["next"] for c in sw.get("cases") or []}
        for t in sorted(quiet):
            if t not in cases:
                bad.append(f"{name}: no case for junk tag {t}")
                continue
            steps = _walk_scene(fc, cases[t], flows)
            calls = [w for k, w, _ in steps if k == "call" and not w.startswith("Dm_SY_Get:RandoST_")]
            ui = [w for k, w, _ in steps if k == "action" and w.startswith("UISystemActor.") and w not in HEAL_UI]
            adds = [p for k, w, p in steps if w == "PouchSystemActor.EventTriggerAddOrRemovePouchContent"]
            heals = [p for k, w, p in steps if w == "PouchSystemActor.EventTriggerRecoverByCureItem"]
            if heals and all(p.get("ActorName") == "Obj_Heart" for p in heals):  # The game's heal is a quiet give here.
                adds = [{"IsGetEvent": False}]  # see dungeons.heal_steps
            if calls or ui:
                bad.append(f"{name}: junk tag {t} ({sorted(n for n, x in plan['_drops_scene_drops'].items() if x == t)[:1]}) "
                           f"plays {sorted(set(calls + ui))}: a hold-up or a window")
            if not adds or any(p.get("IsGetEvent") for p in adds):
                bad.append(f"{name}: junk tag {t} has no quiet pouch add")
        stats["quiet"] = len(quiet)
    return bad, stats


# Ammo counts
# Our ammo types (AMMO_TYPES) are only built when a seed drops them. Each is a new actor type, a copy of the game
# pickup's pack (like the shops' Rando_Shelf_* types, shops.shelf_type_ops) with:
#   - its own pouch content, RandoAmmo_<n>. That's a bundle (IsBundle, BundleActor the item, BundleActorNum OoTR's
#     amount, like the arrow bundles and Obj_Bombchu are), DefaultAutoGet, and no GetType kept (taken on touch, no
#     scene).
#   - for nuts, IsAbleToGetBagIfGet true and the single nut's SmallBagActor / MaxNumGameData kept, so the first nuts
#     bring the small nut bag. OoTR gives the nuts with their capacity, and in the game the single nut, Item_DekuNut,
#     brings it. It's false with remake_shuffle_deku_nut_bag, since the bag is an item then (parity/extras_items.py
#     BAG_SWITCH).
#   - for seeds, Obj_DekuNut's PhysicsParam and the four files it needs (AMMO_SEED_BODY), so they get a falling body.
#   - its ActorParam (a copy of the game pickup's, naming the two), and RSDB rows copied from the game pickup's:
#     ActorInfo (model, heaps), GameActorInfo (its body's layer) and PouchActorInfo (BundleActor, BundleActorNum).
# Its ActorName stays the game pickup's, so the count popup names the item.
AMMO_POUCH_INFO = "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"
AMMO_ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
NUT_RULE_FROM = "Item_DekuNut"  # the single nut: its row says what a nut brings (BAG_SWITCH turns it off)
AMMO_SEED_BODY = ("Pack/Actor/Obj_DekuNut.pack.zs",
                  "Component/Physics/Obj_DekuNut.engine__component__PhysicsParam.bgyml",
                  ("Phive/ControllerSetParam/DropItem.phive__ControllerSetParam.bgyml",
                   "Phive/ShapeParam/DropItem_Body_0.phive__ShapeParam.bgyml",
                   "Phive/ShapeParam/DropItem_Tgt_0.phive__ShapeParam.bgyml"))


def _ammo_work(actor):
    return f"Work/Actor/{actor}.engine__actor__ActorParam.gyml"


def ammo_type_ops(types, nut_bag_shuffled, romfs=DEFAULT_ROMFS, looks=False):
    """Plan sections ({"new_files", "packs", "byml"}) that make each of our ammo types in `types` (Ammo counts).
    With `looks` ("Ammo Without Its Bag: Blue Rupee"), each type with a container rule also gets the Drop component that
    its turn into the Blue Rupee drops it with (the ammo turn, turn_drop_ops)."""
    from romtools import Romfs, sarc_files, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = {"new_files": [], "packs": [], "byml": []}
    rows = {r.get("__RowId"): r for r in byml_load(fs.read(AMMO_POUCH_INFO))[0]}
    for t in sorted(types):
        base, item, num = AMMO_TYPES[t]
        rel, base_rel = f"Pack/Actor/{t}.pack.zs", f"Pack/Actor/{base}.pack.zs"
        files = sarc_files(fs.read(base_rel))
        ap = f"Actor/{base}.engine__actor__ActorParam.bgyml"
        ref = _components(files, base).get("PouchContentRef")
        if ap not in files or not ref or _inner(ref) not in files:
            raise DropPlanError(f"{base_rel}: no ActorParam / PouchContentParam to copy for {t}")
        pc = _pouch_content(files, ref)
        if pc.get("DefaultAutoGet") is not True or pc.get("GetType"):
            raise DropPlanError(f"{base}: its pouch content is no longer a touch pickup with no get scene")
        if base not in rows:
            raise DropPlanError(f"{AMMO_POUCH_INFO}: no row {base} to copy for {t}")
        note = f"{t}: {base} giving {num} {item} (OoTR's amount)"
        out["new_files"].append({"to": rel, "from": base_rel, "note": note})
        pouch = TOUCH_POUCH.format(t)
        pset = {"IsBundle": True, "BundleActor": _ammo_work(item), "BundleActorNum": num}
        rset = {"__RowId": t, "BundleActor": _ammo_work(item), "BundleActorNum": num}
        if item == "Item_Bomb":  # like the game's bundles, no stock of the pickup itself, the item's bag counts
            pset.update({"EnableStock": False, "MaxNumGameData": "", "SmallBagActor": ""})
        if item == "Item_DekuNut":
            pset["IsAbleToGetBagIfGet"] = rset["IsAbleToGetBagIfGet"] = not nut_bag_shuffled
        out["packs"].append({"pack": rel, "file": pouch, "new_from": _inner(ref), "set": pset})
        sets = {"Components.PouchContentRef": "?" + pouch}
        if base == "Obj_DekuSeed":
            src, phys, more = AMMO_SEED_BODY
            src_files = sarc_files(fs.read(src))
            for f in (phys,) + more:
                if f not in src_files:
                    raise DropPlanError(f"{src}: no {f} for {t}'s body")
                if f not in files:
                    out["packs"].append({"pack": rel, "file": f, "from_pack": src})
            sets["Components.PhysicsRef"] = "?" + phys
        if looks and ammo_rupee_owners(t):  # Ammo-to-rupee conversion: a Drop component of its own, dropping the Blue Rupee
            if _components(files, base).get("DropRef"):
                raise DropPlanError(f"{base}: already has a Drop component (AMMO TURN gives {t} its own)")
            out["packs"] += turn_drop_ops(rel, fs)
            sets["Components.DropRef"] = "?" + TURN_DROP[0]
        out["packs"].append({"pack": rel, "file": f"Actor/{t}.engine__actor__ActorParam.bgyml", "new_from": ap,
                             "set": sets})
        out["byml"] += [{"file": AMMO_ACTOR_INFO, "add_row": {"copy_of": base, "set": {"__RowId": t}}, "note": note},
                        {"file": GAME_ACTOR_INFO, "add_row": {"copy_of": base, "set": {"__RowId": t}}},
                        {"file": AMMO_POUCH_INFO, "add_row": {"copy_of": base, "set": rset}}]
    return {k: v for k, v in out.items() if v}


# Ammo container check
# With "Ammo Without Its Bag: Blue Rupee" and no container, you see and are told a Blue Rupee, not the ammo. OoTR turns
# Bombs, Arrows and Deku Seeds into a Blue Rupee when they're given with no bomb bag, quiver or bullet bag
# (item_upgrades.c bombs_/arrows_/seeds_to_rupee). The give and its window already do that (parity/_ammo.py guards), and
# this is what a chest shows rising from it.
# A chest holding container ammo also names AMMO_SWITCH_KEYS: the ammo, its Blue Rupee (TBox_Rupee_Blue) and its
# container (a parity/_ammo.py GROUPS name). Its type's root AI creates its content from Drop__DropActor
# (Obj_TBox_A_01.root node 1, where ActorFileName reads it). _ammo_switch_edits feeds every such read from a chain of
# the game's string picks (QuerySelectStringByBool, True -> A, like Obj_TBox_A_06 picks its holder key). If the
# container's name is one of ours and none of its owners is in the pouch (QueryGetPouchContentNumByActorName, like the
# item looks pick a tier), it picks Drop__RandoAmmoNo, else Drop__DropActor. The picks are queries, so they answer when
# the chest creates its content and nothing runs every frame.
# We don't write Drop__DropActor, because that crashes the game on New Game. It's an instance parameter (IsInstanceParam
# in the Drop table, a placement sets it), and ExecuteBlackboardSetString caches no change counter for one (-1), so its
# first write goes to address -1. The game's own AI writes 808 keys through BlackboardType 1 and none of them is an
# instance parameter (tools/rando/ai_shape_check.py refuses such a write).
# Droppers (pots, grass, trees, rocks) get no switch. Their drop reads Drop__DropActor in the engine (no AI step names
# the actor), so the object drops the ammo pickup, and taking it gives the Blue Rupee when there's no container (the
# ammo rupee, DropItem.root). With "nothing" none of this is built.
AMMO_SWITCH_KEYS = ("Drop__RandoAmmo", "Drop__RandoAmmoNo", "Drop__RandoAmmoBag")
AMMO_RUPEE = "Obj_Rupee_Blue"  # a dropped pickup's Blue Rupee (a chest's is parity/_ammo.py RUPEE, TBox_Rupee_Blue)
AMMO_SWITCH_DEFAULT = "blue_rupee"  # parity/_ammo.py DEFAULT (a plan from before the setting is read as the default)


def ammo_rupee_owners(t):
    """The actors whose presence in the pouch means type `t`'s container is owned (parity/_ammo.py GROUPS' owners), or
    None for ammo with no container rule (nuts)."""
    from parity import _ammo
    return _ammo.owners_of(AMMO_TYPES[t][1]) if t in AMMO_TYPES else None


def ammo_type_looks(placements, romfs=DEFAULT_ROMFS):
    """Type looks for our container-ammo types that a plan's placements drop:
    {type: {"tiers": [[its container's owners, LOOK_TURN], [[], LOOK_KEEP]]}}
    With no container owned it turns into the Blue Rupee (the ammo turn), and with one owned it stays as it is."""
    types = {(op.get("set") or {}).get("Dynamic.Drop__DropActor") for op in placements} & set(AMMO_TYPES)
    return {t: {"tiers": [[list(ammo_rupee_owners(t)), LOOK_TURN], [[], LOOK_KEEP]]}
            for t in sorted(types) if ammo_rupee_owners(t)}


def turn_drop_ops(pack, fs):
    """The ammo turn. "packs" ops that give ammo pack `pack` its own Drop component.
    - TURN_DROP's DropParam. It's the butterfly's with its parent dropped, BlackboardTableRef pointing at our copy of
      the Drop table under its own path, and DropTableResourceList at our table.
    - that table (the default one, no name)
    - its sub-table (the butterfly's one item, AMMO_RUPEE at 100 %)"""
    from romtools import sarc_files, byml_load
    src = sarc_files(fs.read(TURN_DROP_SRC[0]))
    item = byml_load(src[TURN_DROP_SRC[4]])[0]["Items"][0]
    if item.get("DropProbability") != 100 or item.get("DropCreateCount") != 1:
        raise DropPlanError(f"{TURN_DROP_SRC[4]}: no longer one item at 100 % (AMMO TURN copies its shape)")
    return [{"pack": pack, "file": TURN_DROP[1], "from_pack": TURN_DROP_SRC[0], "new_from": TURN_DROP_SRC[2]},
            {"pack": pack, "file": TURN_DROP[0], "from_pack": TURN_DROP_SRC[0], "new_from": TURN_DROP_SRC[1],
             "set": {"BlackboardTableRef": _work(TURN_DROP[1]), "DropTableResourceList": [_work(TURN_DROP[2])]},
             "remove": ["$parent"]},
            {"pack": pack, "file": TURN_DROP[2], "from_pack": TURN_DROP_SRC[0], "new_from": TURN_DROP_SRC[3],
             "set": {"SubTableList": [_work(TURN_DROP[3])]}},
            {"pack": pack, "file": TURN_DROP[3], "from_pack": TURN_DROP_SRC[0], "new_from": TURN_DROP_SRC[4],
             "set": {"Items": [dict(item, DropActorName=f"Work/Actor/{AMMO_RUPEE}.engine__actor__ActorParam.gyml")]}}]


def _turn_edits(fs, label):
    """The ammo turn. Returns (edits, ref of the Sequential) for the Sequential that turns a pickup into AMMO_RUPEE (not
    anyone's child yet). It hides the pickup, saves the dropper's rows, hands the rupee the checked bit, drops it and
    deletes the pickup."""
    from romtools import sarc_files
    import ainb
    edits, ref = [], {}
    for k, (src, n) in TURN_SRC.items():
        i = n if isinstance(n, int) else ainb.Ainb(sarc_files(fs.read(src["pack"]))[src["file"]]).node(n)
        edits.append({"copy": {"from": src, "nodes": [i], "label": f"{label}{k}", "follow": False}})
        ref[k] = f"{label}{k}:{i}"
    hsrc, hi = LOOK_SRC["hide"][0], LOOK_SRC["hide"][1]["OneShotSetModelVisible"]
    hide = f"{label}hide:{hi}"
    more, get = _chk_get(f"{label}g", PICKUP_CHK_KEY)
    asrc, ai_ = CHK_SRC["add"]
    add = f"{label}a:{ai_}"
    edits += [{"copy": {"from": hsrc, "nodes": [hi], "label": f"{label}hide", "follow": False}},
              {"set_input": {"node": hide, "name": "Bool", "value": False}}] + more + [
        {"copy": {"from": asrc, "nodes": [ai_], "label": f"{label}a", "follow": False, "values": {ai_: {"S32": 0}}}},
        {"set_property": {"node": add, "name": "Key", "value": PICKUP_CHK_KEY}},
        {"feed": {"from": get, "output": "S32", "to": add, "input": "S32"}},
        {"link": {"from": ref["make"], "output": "OverwriteParam", "to": add, "input": "OverwriteParam"}},
        {"link": {"from": add, "output": "OverwriteParam", "to": ref["hand"], "input": "OverwriteParam"}},
        {"set_property": {"node": ref["delete"], "name": "IsFade", "value": False}}]
    for child in (hide, ref["save"], ref["hand"], ref["drop"], ref["delete"]):
        edits.append({"add_child": {"parent": ref["seq"], "child": child}})
    return edits, ref["seq"]


def ammo_switch_sets(actor, rupee):
    """{"Dynamic.<key>": value} for a placement that gives container ammo `actor` (a pickup type or chest content)."""
    from parity import _ammo
    group = _ammo.group_of(AMMO_TYPES[actor][1] if actor in AMMO_TYPES else actor)
    if group is None:
        raise DropPlanError(f"{actor}: no container rule (parity/_ammo.py GROUPS)")
    return {f"Dynamic.{AMMO_SWITCH_KEYS[0]}": actor, f"Dynamic.{AMMO_SWITCH_KEYS[1]}": rupee,
            f"Dynamic.{AMMO_SWITCH_KEYS[2]}": group.replace(" ", "")}


def root_ai_of(actor, romfs=DEFAULT_ROMFS):
    """The root AI file an actor type runs (its AIInfo's RootAIRef as a file path), or None."""
    from romtools import Romfs, sarc_files, byml_load
    files = sarc_files(Romfs(romfs, os.path.join(HERE, "original")).read(f"Pack/Actor/{actor}.pack.zs"))
    info = _inner(_components(files, actor).get("AIInfoRef") or "")
    if info not in files:
        return None
    ref = byml_load(files[info])[0].get("RootAIRef") or ""
    return "AI/" + ref.split("/")[-1].replace(".ain", ".ainb") if ref else None


def drop_bb_table(files, actor):
    """The blackboard table `actor`'s Drop component reads its instance parameters from (its DropParam chain's first
    BlackboardTableRef, as a pack path), or None.
    Chests differ. Obj_TBox_A_01 (and _NoBake, _memo11), A_02, A_03, GlassTruth and the Treasure Chest Game's read
    Drop_TreasureBox, A_06 reads Drop_TreasureBox_A_06, and only A_04 reads the shared Drop table (DROP_TABLE). A key
    declared only there never reaches the others."""
    from romtools import byml_load
    cur, seen = _inner(_components(files, actor).get("DropRef") or ""), set()
    while cur and cur in files and cur not in seen:
        seen.add(cur)
        d = byml_load(files[cur])[0]
        if d.get("BlackboardTableRef"):
            return _inner(d["BlackboardTableRef"])
        cur = _inner(d["$parent"]) if d.get("$parent") else None
    return None


def ammo_switch_ops(ai_files, romfs=DEFAULT_ROMFS, components=(), tables=()):
    """{"ainb": [...]} with the AMMO_SWITCH_KEYS declared on the Drop table (every pack holding it, droppers and A_04
    chests) and on each other drop table of `tables`, and the switch picks in each chest root AI of `ai_files`.
    `tables` are the switched chests' own tables (drop_bb_table). Mido's A_01 chests read Drop_TreasureBox, so without
    them the keys never reached those chests and they showed and gave the ammo.
    `ai_files` is [(packs, file)], with packs "*" for every pack holding the file, or a list."""
    from romtools import Romfs
    from parity import _ammo
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    groups = {g.replace(" ", ""): _ammo.owners_of(actors[-1]) for g, actors in _ammo.GROUPS.items()}
    keys = [{"table": DROP_TABLE, "type": "String", "key": k, "init": "", "instance": True} for k in AMMO_SWITCH_KEYS]
    out = [{"pack": "*", "bb_params": keys}]
    for t in sorted(set(tables) - {DROP_TABLE, None}):
        out.append({"pack": "*", "bb_params": [dict(k, table=t) for k in keys]})
    import packpaths  # the Drop tables drop_component_ops copies in ("*" finds only the game's own holders)
    comp = sorted({pk for t in components for pk in packpaths.carriers(DROP_COMPONENT[t], romfs)})
    if comp:
        out.append({"pack": comp, "bb_params": keys})
    for pk, f in sorted({(p if p == "*" else tuple(p), f) for p, f in ai_files}, key=str):
        out.append({"pack": pk if pk == "*" else list(pk), "file": f, "edits": _ammo_switch_edits(fs, groups)})
    return {"ainb": out}


SWITCH_PICK_SRC = ({"pack": "Pack/Actor/Obj_TBox_A_06.pack.zs", "file": "AI/Obj_TBox_A_06.root.ainb"},
                   {"QuerySelectStringByBool": 24})  # its A/B read the chest's blackboard, so the copy gets values


def _ammo_switch_edits(fs, groups):
    """Edits that add the ammo switch picks (Ammo container check) to a chest root AI. `groups` is {container name:
    [owner actors]}. Every input that reads Drop__DropActor is fed by the last pick, except a StringSelector's, which
    only keys on special contents."""
    _, eq_i = _name_sources(fs)
    g_src, g = GATE_SRC["getstr"]
    gi = g["QueryBlackboardGetString"]
    pk_src, pk = SWITCH_PICK_SRC
    pi = pk["QuerySelectStringByBool"]
    cnt_src, cnt = LOOK_SRC["count"]
    less_src, less = LOOK_SRC["less"]
    cnt_i, less_i = cnt["QueryGetPouchContentNumByActorName"], less["QueryMathLessS32"]

    def get(label, key):
        ref = f"{label}:{gi}"
        return ref, [{"copy": {"from": g_src, "nodes": [gi], "label": label, "follow": False}},
                     {"set_property": {"node": ref, "name": "BlackboardType", "value": 1}},
                     {"set_property": {"node": ref, "name": "BlackboardKey", "value": key}},
                     {"set_property": {"node": ref, "name": "OutputOnlyOnEnter", "value": True}}]

    def streq(label, feed_from, value):
        ref = f"{label}:{eq_i}"
        return ref, [{"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": label, "follow": False}},
                     {"set_input": {"node": ref, "name": "StringB", "value": value}},
                     {"feed": {"from": feed_from, "output": "String", "to": ref, "input": "StringA"}},
                     {"set_property": {"node": ref, "name": "OutputOnlyOnEnter", "value": True}}]

    def pick(label, cond, output, yes, no):  # cond True -> yes (A), else no (B)
        ref = f"{label}:{pi}"
        return ref, [{"copy": {"from": pk_src, "nodes": [pi], "label": label, "follow": False,
                               "values": {pi: {"A": "", "B": ""}}}},
                     {"feed": {"from": cond, "output": output, "to": ref, "input": "Bool"}},
                     {"feed": {"from": yes, "output": "String", "to": ref, "input": "A"}},
                     {"feed": {"from": no, "output": "String", "to": ref, "input": "B"}}]
    e = []
    bag, x = get("swbag", AMMO_SWITCH_KEYS[2])
    ammo, y = get("swammo", AMMO_SWITCH_KEYS[0])
    no, z = get("swno", AMMO_SWITCH_KEYS[1])
    own, w = get("swown", "Drop__DropActor")
    e += x + y + z + w
    nxt = own  # no container name of ours (every other placement), so the chest's own content
    for k, (label, owners) in enumerate(sorted(groups.items())):
        chain = no
        for j, o in enumerate(reversed(owners)):
            c, lq = f"swcnt{k}_{j}:{cnt_i}", f"swless{k}_{j}:{less_i}"
            e += [{"copy": {"from": cnt_src, "nodes": [cnt_i], "label": f"swcnt{k}_{j}", "follow": False}},
                  {"set_input": {"node": c, "name": "ActorName", "value": o}},
                  {"copy": {"from": less_src, "nodes": [less_i], "label": f"swless{k}_{j}", "follow": False}},
                  {"feed": {"from": c, "output": "Num", "to": lq, "input": "S32Base"}}]
            chain, x = pick(f"swown{k}_{j}", lq, "Bool", ammo, chain)
            e += x
        q, x = streq(f"sweq{k}", bag, label)
        e += x
        nxt, x = pick(f"swsel{k}", q, "IsEqual", chain, nxt)
        e += x
    return e + [{"feed_bb_reads": {"type": "string", "bb": "Drop__DropActor", "from": nxt, "output": "String"}}]


def verify_ammo_touch(patch_dir, plan, items, romfs=DEFAULT_ROMFS, m=None):
    """Reads a built patch back (Ammo touch pickups) and returns [problem], {"own": spots, "flagless": spots, "types":
    [...]}.
    - Every drop spot the plan shuffles that holds junk ammo with a touch pickup of its own (TOUCH_AMMO) has to drop
      that pickup (its placements' Drop__DropActor in the built levels), not the carrier. Through the carrier the get
      scene starts and Link stops. Flagless spots are the exception, since only the carrier can give their item once,
      and they're counted apart.
    - It records the check when taken, not at the break. No placement asks to save on break (DROP_SAVE_KEY), the type is
      one the checked-on-pickup pipeline lists (verify_pickup_save reads its save branch back), and the spot is on the
      respawn model (verify_respawn reads its bit and twin back) or checked on pickup.
    - Each such type in the patch has a Catch client with a blackboard check (touch), the touch pickups' root AI (it
      raises IsEnableAttention), and a pouch content with DefaultAutoGet and no GetType (taken on touch, no scene).
    - Our ammo types (Ammo counts) are a bundle of the item with OoTR's amount, in the pouch content and the RSDB row,
      with ActorInfo and GameActorInfo rows. Nuts bring the nut bag like the single nut does (Item_DekuNut's row, False
      with remake_shuffle_deku_nut_bag).
    - The ammo switch (Ammo container check). With remake_ammo_without_container "blue_rupee" (plan
      "_ammo_no_container"), each placement holding a container ammo type of ours names it, Obj_Rupee_Blue and its
      container (AMMO_SWITCH_KEYS), and each root AI the plan lists (plan "_ammo_switch") runs the switch on exactly
      each container's owners. With "nothing", none of it."""
    from romtools import Romfs, sarc_files, byml_load
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    m = m or _map()
    bad, stats = [], {"own": 0, "flagless": 0, "types": []}
    prow = {r.get("__RowId"): r for r in byml_load(new.read(AMMO_POUCH_INFO))[0]}
    switch_places = {}
    nut_bag = bool((prow.get(NUT_RULE_FROM) or {}).get("IsAbleToGetBagIfGet"))
    tables = {}
    scene = plan.get("_drops_scene_drops") or {}
    flagless = plan.get("_drops_flag_spots") or {}
    model = (plan.get("_drops_respawn") or {}).get("spots") or {}
    cop = plan.get("_checked_on_pickup") or {}
    planned = {(op["file"], str(op["hash"])) for op in plan.get("placements", []) if op.get("twin") is None}
    levels, types = {}, set()

    def level(f):
        if f not in levels:
            levels[f] = {str(a.get("Hash")): a for a in byml_load(new.read(f))[0].get("Actors", [])}
        return levels[f]
    for n, it in sorted(items.items()):
        actor = DROP_ACTOR.get(it)
        e = lookup(n, m) if actor in TOUCH_AMMO else None
        if not e or e.get("kind") != "drop" or not e.get("placements"):
            continue
        if n in flagless:  # Flagless pickups, verify_flagless_own reports a carried one
            continue
        if n in (plan.get("_drops_flagless_own") or {}):
            stats["flagless"] += 1
        if n not in scene and n not in model and not any((p["file"], str(p["hash"])) in planned
                                                         for p in e["placements"]):
            continue  # not shuffled: the object as it is
        types.add(actor)
        if n in scene:
            bad.append(f"{n}: {it} drops the carrier (its get scene starts: Link stops) instead of its own touch "
                       f"pickup {actor}")
            continue
        if ammo_rupee_owners(actor):
            switch_places[n] = [dict(p, actor=actor) for p in e["placements"]]
        for p in e["placements"]:
            dyn = (level(p["file"]).get(str(p["hash"])) or {}).get("Dynamic") or {}
            if dyn.get("Drop__DropActor") != actor:
                bad.append(f"{n} ({p['hash']}): drops {dyn.get('Drop__DropActor')!r}, not {actor}")
            if dyn.get(DROP_SAVE_KEY):
                bad.append(f"{n} ({p['hash']}): saves its check at the break ({DROP_SAVE_KEY}): an ammo pickup left "
                           f"behind would be lost")
        if actor not in (cop.get("pickups") or []):
            bad.append(f"{n}: {actor} is not in the checked-on-pickup pickups: taking it would not record the check")
        if n not in model and not all(p["category"] == "gold_skulltula" or p["actor"] in (cop.get("droppers") or [])
                                      for p in e["placements"]):
            bad.append(f"{n}: neither on the respawn model nor checked on pickup: its {it} could be lost or repeat")
        stats["own"] += 1
    for actor in sorted(types):
        try:
            files = sarc_files(new.read(f"Pack/Actor/{actor}.pack.zs"))
        except (FileNotFoundError, KeyError, OSError):
            bad.append(f"{actor}: no pack Pack/Actor/{actor}.pack.zs in the game or the patch")
            continue
        comp = _components(files, actor)

        def load(ref):
            k = _inner(ref or "")
            return byml_load(files[k])[0] if k in files else None
        clients = [load(c) for c in (load(comp.get("AttentionSenderRef")) or {}).get("ClientList", [])]
        catch = next((c for c in clients if c and c.get("ClientName") == "Catch"), None)
        if catch is None or not any((c.get("CheckBlackBoard") or {}).get("BlackBloardName")
                                    for c in catch.get("CheckList", [])):
            bad.append(f"{actor}: its attention has no touch Catch client")
        if (load(comp.get("AIInfoRef")) or {}).get("RootAIRef") != TOUCH_ROOT_AI:
            bad.append(f"{actor}: its AI is not the touch pickups' root ({TOUCH_ROOT_AI}): nothing raises "
                       f"{TOUCH_KEY}")
        pc = _pouch_content(files, comp.get("PouchContentRef"))
        if pc.get("DefaultAutoGet") is not True:
            bad.append(f"{actor}: no DefaultAutoGet: it would ask for the button")
        if pc.get("GetType"):
            bad.append(f"{actor}: GetType {pc['GetType']}: a touch would start a get scene (Link stops)")
        if actor in AMMO_TYPES:  # Ammo counts: OoTR's amount, a bundle of the item
            base, item, num = AMMO_TYPES[actor]
            if not (pc.get("IsBundle") is True and pc.get("BundleActor") == _ammo_work(item)
                    and pc.get("BundleActorNum") == num):
                bad.append(f"{actor}: its pouch content gives {pc.get('BundleActorNum')} of {pc.get('BundleActor')} "
                           f"(bundle {pc.get('IsBundle')}), not OoTR's {num} {item}")
            if item == "Item_DekuNut" and bool(pc.get("IsAbleToGetBagIfGet")) != nut_bag:
                bad.append(f"{actor}: IsAbleToGetBagIfGet {pc.get('IsAbleToGetBagIfGet')}, the single nut "
                           f"({NUT_RULE_FROM}) {nut_bag}")
            row = prow.get(actor) or {}
            if row.get("BundleActorNum") != num or row.get("BundleActor") != _ammo_work(item) or (item == "Item_DekuNut" and bool(row.get("IsAbleToGetBagIfGet")) != nut_bag):
                bad.append(f"{AMMO_POUCH_INFO}: row {actor} {dict((k, row.get(k)) for k in ('BundleActor', 'BundleActorNum', 'IsAbleToGetBagIfGet'))}"
                           f", not {num} {item}")
            for table in (AMMO_ACTOR_INFO, GAME_ACTOR_INFO):
                if actor not in tables.setdefault(table, {r.get("__RowId") for r in byml_load(new.read(table))[0]}):
                    bad.append(f"{table}: no row {actor} (a new actor type needs one)")
            if "rstb" not in tables:  # the pack's size-table entry (make_patch gives every new pack one)
                sys.path.insert(0, os.path.join(HERE, "tools"))
                import make_patch
                tables["rstb"] = make_patch.Restbl(new.zs.decompress(new.raw(make_patch.RSTB_PATH)))
            if tables["rstb"].get(f"Pack/Actor/{actor}.pack") is None:
                bad.append(f"Pack/Actor/{actor}.pack: no size-table entry (the game can't load a pack it has no size for)")
    stats["types"] = sorted(types)
    # The engine reads Drop__DropActor for breakable objects, and their pickups do the blue-rupee swap when taken. Only
    # chest AIs use the switch keys, so we check each owner list on their switches and that "nothing" mode leaves them
    # out.
    mode = plan.get("_ammo_no_container") or AMMO_SWITCH_DEFAULT
    sw = plan.get("_ammo_switch") or {}
    from parity import _ammo
    groups = {g.replace(" ", ""): sorted(_ammo.owners_of(actors[-1])) for g, actors in _ammo.GROUPS.items()}
    for n, pl in sorted(switch_places.items()):
        for p in pl:
            dyn = (level(p["file"]).get(str(p["hash"])) or {}).get("Dynamic") or {}
            got = [dyn.get(k) for k in AMMO_SWITCH_KEYS]
            if any(got):
                bad.append(f"{n} ({p['hash']}): switch keys {got} on a dropper (its drop is read by the engine)")
    if mode != "blue_rupee" and sw.get("ai"):
        bad.append(f"ammo switch built with {mode!r}")
    if sw.get("ai"):
        import ainb
        for packs, f in sw["ai"]:
            if not f.startswith("AI/Obj_TBox_"):
                bad.append(f"{f}: the ammo switch is for chests' root AIs only")
            for pk in (_carriers_of(f, romfs) if packs == "*" else packs):
                got, why = _ammo_switch_read(ainb.Ainb(sarc_files(new.read(pk))[f]))
                bad += [f"{pk}:{f}: ammo switch: {x}" for x in why]
                if got != groups:
                    bad.append(f"{pk}:{f}: the ammo switch checks {got}, want {groups}")
    rehash = {(op["file"], str(op["hash"])): str(op["set"]["Hash"]) for op in plan.get("placements", [])
              if "Hash" in (op.get("set") or {}) and op.get("twin") is None}  # a chest copy takes its main's hash
    for c in sw.get("chests") or []:  # chests get their content's switch keys (parity/_ammo.py switch_ops)
        want_keys = [c["item"], "TBox_Rupee_Blue", (_ammo.group_of(c["item"]) or "?").replace(" ", "")]
        for f in c["files"]:
            h = rehash.get((f, str(c["hash"])), str(c["hash"]))
            dyn = (level(f).get(h) or {}).get("Dynamic") or {}
            if [dyn.get(k) for k in AMMO_SWITCH_KEYS] != want_keys or dyn.get("Drop__DropActor") != c["item"]:
                bad.append(f"chest {c['id']} ({f}): content {dyn.get('Drop__DropActor')}, switch keys "
                           f"{[dyn.get(k) for k in AMMO_SWITCH_KEYS]}, want {want_keys}")
            # the keys only reach the chest if its own drop table declares them (drop_bb_table)
            gy = (level(f).get(h) or {}).get("Gyaml")
            if gy and gy not in tables.setdefault("switch_tables", {}):
                pf = sarc_files(new.read(f"Pack/Actor/{gy}.pack.zs"))
                tb = drop_bb_table(pf, gy)
                rows = byml_load(pf[tb])[0] if tb in pf else {}
                inst = {e.get("BBKey") for arr_k, arr in rows.items() if arr_k.startswith("BlackboardParam")
                        and isinstance(arr, list) for e in arr if isinstance(e, dict) and e.get("IsInstanceParam")}
                tables["switch_tables"][gy] = (tb, sorted(set(AMMO_SWITCH_KEYS) - inst))
            tb, miss = tables["switch_tables"].get(gy, (None, []))
            if miss:
                bad.append(f"chest {c['id']} ({gy}): its drop table {(tb or '?').split('/')[-1]} doesn't declare "
                           f"{miss}: the switch never gets them, so the chest shows and gives the ammo")
    stats["switch"] = len(sw.get("chests") or [])
    return bad, stats


def _ammo_switch_read(a):
    """What the ammo switch picks of chest root AI `a` check, as ({container name: [owner actors]}, [problem]).
    Per container that's the owners whose "owned" answer picks Drop__RandoAmmo and whose last "not owned" picks
    Drop__RandoAmmoNo. With no container of ours it's Drop__DropActor. The problems also list the inputs still reading
    Drop__DropActor (except a StringSelector's)."""
    import ainb

    def fed(i, kind, name):
        x = next((x for x in a.nodes[i]["inputs"].get(kind, []) if x["name"] == name), None)
        return None if x is None or x.get("node", -1) < 0 else x["node"]

    def prop(i, name):
        return next((x["value"] for arr in (a.nodes[i].get("properties") or {}).values() for x in arr
                     if x.get("name") == name), None)

    def getter(i, key):
        return (i is not None and a.nodes[i]["name"] == "QueryBlackboardGetString" and
                prop(i, "BlackboardType") == 1 and prop(i, "BlackboardKey") == key)

    def is_pick(i):
        return i is not None and i >= 0 and a.nodes[i]["name"] == "QuerySelectStringByBool"
    def ours(i):  # Our picks fall back to the chest's own Drop__DropActor at the end of the B chain.
        seen = set()
        while is_pick(i) and i not in seen:
            seen.add(i)
            i = fed(i, "string", "B")
        return getter(i, "Drop__DropActor")
    reads, fed_by, bad = [], set(), [f"node {i} {a.nodes[i]['name']} input {x} still reads Drop__DropActor"
                                     for i, x in a.bb_readers("string", "Drop__DropActor")]
    for i, n in enumerate(a.nodes):
        if n["type"] == 5 or n["name"] == "QuerySelectStringByBool":
            continue
        for x in n["inputs"].get("string", []):
            if is_pick(x.get("node", -1)) and ours(x["node"]):
                reads.append((i, x["name"]))
                fed_by.add(x["node"])
    if len(fed_by) > 1:
        bad.append(f"the content reads are fed by {len(fed_by)} different pick chains")
    if not any(a.nodes[i]["name"] == "OneShotActorHolderTryRequestCreateActorWithActorFileName" and x == "ActorFileName"
               for i, x in reads):
        bad.append("no create step's ActorFileName is fed by the picks (the chest creates its content as before)")
    out = {}
    s = next(iter(fed_by), None)
    while is_pick(s):
        q = fed(s, "bool", "Bool")
        label = next((x["value"] for x in a.nodes[q]["inputs"]["string"] if x["name"] == "StringB"), None) \
            if q is not None and a.nodes[q]["name"] == "QueryStringIsEqual" and \
            getter(fed(q, "string", "StringA"), AMMO_SWITCH_KEYS[2]) else None
        if not label:
            bad.append(f"pick {s}: not keyed on {AMMO_SWITCH_KEYS[2]}")
            break
        y, owners = fed(s, "string", "A"), []
        while is_pick(y):
            lq = fed(y, "bool", "Bool")
            c = fed(lq, "int", "S32Base") if lq is not None else None
            if c is None or a.nodes[c]["name"] != "QueryGetPouchContentNumByActorName" or \
                    not getter(fed(y, "string", "A"), AMMO_SWITCH_KEYS[0]):
                break
            owners.append(next(x["value"] for x in a.nodes[c]["inputs"]["string"] if x["name"] == "ActorName"))
            y = fed(y, "string", "B")
        if getter(y, AMMO_SWITCH_KEYS[1]):
            out[label] = sorted(owners)
        else:
            bad.append(f"container {label}: its last 'not owned' doesn't pick {AMMO_SWITCH_KEYS[1]}")
        s = fed(s, "string", "B")
    return out, bad


def _body_of(files, actor, rows):
    """What a pickup type's patched files make of its drop: (problem or None, how it moves)."""
    from romtools import byml_load
    comp = _components(files, actor)
    if not comp.get("PhysicsRef"):
        return "no PhysicsRef", None
    phys = _inner(comp["PhysicsRef"])
    if phys not in files:
        return f"its PhysicsRef {phys} is not in its pack", None
    ctrl = _inner(byml_load(files[phys])[0]["ControllerSetPath"])
    if ctrl not in files:
        return f"its controller set {ctrl} is not in its pack", None
    seen, cur, merged = set(), ctrl, {}
    while cur and cur in files and cur not in seen:  # the set's own chain ($parent), leaf wins
        seen.add(cur)
        d = byml_load(files[cur])[0]
        merged = {**d, **merged}
        cur = _inner(d["$parent"]) if d.get("$parent") else None
    main = next((a for a in merged.get("AliasEntityList", []) if a.get("AliasEntity") == "Main"), None)
    ent = next((e for e in merged.get("RigidBodyEntityNamePathAry", [])
                if main and e.get("Name") == main.get("RigidBodyName")), None)
    if ent is None:
        return "no main rigid body: it stays where it is created", "none"
    bf = _inner(ent["FilePath"])
    if bf not in files:
        return f"its main rigid body {bf} is not in its pack", None
    b = byml_load(files[bf])[0]
    if b.get("MotionType") != MOTION_DYNAMIC:
        return (f"its main rigid body {bf.split('/')[-1].split('.')[0]} is not Dynamic (MotionType "
                f"{b.get('MotionType')}): it stays where it is created"), "kinematic"
    if b.get("EnableLayerHitMask") != "HitOnlyGroundAndObject":
        return f"its main rigid body hits {b.get('EnableLayerHitMask')}, not the ground", "dynamic"
    cc = next((e for e in merged.get("CColEntityNamePathAry", []) if e.get("Name") == main.get("ControllerName")),
              None)
    if cc is None or _inner(cc["FilePath"]) not in files:
        return "its body's contact collection is missing from its pack", "dynamic"
    table = _inner(comp.get("GameParameterTableRef") or "")
    tc = {}
    while table in files:  # the table's chain, leaf wins
        d = byml_load(files[table])[0]
        tc = {**(d.get("Components") or {}), **tc}
        table = _inner(d["$parent"]) if d.get("$parent") else ""
    if _inner(tc.get("DropBoundParam") or "") not in files:
        return "no DropBoundParam in its pack (every falling vanilla pickup has one)", "dynamic"
    row = rows.get(actor) or {}
    if row.get("MainRigidBodyLayer") != b.get("LayerEntity"):
        return (f"GameActorInfo names layer {row.get('MainRigidBodyLayer')}, its main body is "
                f"{b.get('LayerEntity')}"), "dynamic"
    return None, "dynamic"


# Drop preloading
# The first 3 or 4 Ice Cavern floor pillars broken right after arriving dropped nothing. Later ones did, and after a
# reload the same ones did. What a dropper may drop is a resource of the dropper. Its DropParam's DropTableResourceList
# names the drop tables, whose items name the actors (DropActorName) or their category. Every vanilla dropper's list
# covers what its placements drop (a pot's Drop_ResourceSupply_00 has hearts, magic, ammo, rupees and fairies by
# category, and the Gold Skulltula's DropTable_Token_Gold names Obj_Token_Gold). But the Drop component we give icicles,
# pillars, red ice and silver rocks (drop_component_ops, the bomb boulder's Drop_Default) only lists DropTable_None, and
# no vanilla table names our own drops (the carrier, the RandoAmmo_* types, a key or a token away from its home). A drop
# like that only loads when it's first asked for, so a drop right after arrival can come to nothing.
# Keep the vanilla pot tables. Listing one table, RandoDrops, in every DropParam the seed drops through (the pots'
# Drop_ResourceSupply_00 too), with one sub-table naming all 20 of the seed's drop actors at DropProbability 0 and
# IsReplace false, made every item-holding pot drop nothing. No vanilla file has that shape. Vanilla has at most 6 items
# per sub-table and 23 tables per list, and no entry names an actor at 0 %. Where a placement drops an actor by
# Drop__DropActor that its tables also name, the entry is 100 %, e.g. Obj_Pot_A_06's Obj_Bomb in DropTable_Obj_Bomb_02.
# So vanilla droppers keep their vanilla lists (their drops already came right after arriving), and only our droppers'
# own RandoDrop_Default lists what icicles, pillars, red ice and silver rocks drop. That's one table per actor, each a
# copy of the vanilla DropTable_Obj_Bomb_02 pair (one item naming the actor, "Type" 126134492, 100 %, count 1), at most
# RESIDENT_MAX of them after DropTable_None. Past that there are none, and it drops like it would with no preloading.
# drop_resource_ops builds them, and verify_drop_resources and verify_drop_resolve read them back.
RANDO_DROPS = ("Drop/DropTable/RandoDrop_{}.game__drop__DropTable.bgyml",
               "Drop/DropSubTable/RandoDrop_{}.game__drop__DropSubTable.bgyml")
RANDO_DROPS_SRC = ("Pack/Actor/Obj_Pot_A_01.pack.zs", "Drop/DropTable/DropTable_Obj_Bomb_02.game__drop__DropTable.bgyml",
                   "Drop/DropSubTable/DropTable_Obj_Bomb_02.game__drop__DropSubTable.bgyml")
# vanilla's largest drop shapes over every Drop file of every Pack/Actor pack. That's tables in one
# DropTableResourceList (Obj_BrokenBox_A_01's Drop_ResourceSupply_00) and items in one sub-table (Land_Tree_Base_M's
# DropTable_ResourceSupply_00).
VANILLA_MAX_TABLES, VANILLA_MAX_ITEMS = 23, 6
RESIDENT_MAX = VANILLA_MAX_TABLES - 1  # RandoDrop_Default: DropTable_None plus one table per actor


def _drop_param_of(actor, romfs):
    """(the DropParam file that holds `actor`'s DropTableResourceList, [packs holding it]) or (None, [])."""
    import packpaths
    from romtools import Romfs, sarc_files, byml_load
    if actor in DROP_COMPONENT:  # our component is the boulder's Drop_Default, in every pack holding its ActorParam
        return _inner(DROP_COMPONENT_REF), sorted(packpaths.carriers(DROP_COMPONENT[actor], romfs))
    try:
        files = sarc_files(Romfs(romfs, os.path.join(HERE, "original")).read(f"Pack/Actor/{actor}.pack.zs"))
    except (FileNotFoundError, OSError):
        return None, []
    cur, seen = _inner(_components(files, actor).get("DropRef") or ""), set()
    while cur and cur in files and cur not in seen:
        seen.add(cur)
        d = byml_load(files[cur])[0]
        if "DropTableResourceList" in d:
            return cur, sorted(packpaths.carriers(cur, romfs))
        cur = _inner(d["$parent"]) if d.get("$parent") else None
    return None, []


def _dropper_drops(placements):
    """{dropper type: {drop actors}} of plan placement ops naming a Drop__DropActor (and the ammo switch's other)."""
    from collections import defaultdict
    out = defaultdict(set)
    for op in placements:
        st = op.get("set") or {}
        a = st.get("Dynamic.Drop__DropActor")
        if not a or op.get("twin") is not None:
            continue
        g = st.get("Gyaml") or (_vanilla_level(op["file"]).get(str(op["hash"])) or {}).get("Gyaml")
        out[g] |= {a} | ({st["Dynamic.Drop__RandoAmmoNo"]} if st.get("Dynamic.Drop__RandoAmmoNo") else set())
    return out


def drop_resource_ops(placements, romfs=DEFAULT_ROMFS):
    """{"packs": [...]} where our droppers' RandoDrop_Default lists one vanilla-shaped table per actor they drop, in
    every pack holding it (Drop preloading). Vanilla droppers' DropParams stay as they are, since touching the pot
    tables made pots drop nothing."""
    from romtools import Romfs, sarc_files, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    by_type = _dropper_drops(placements)
    actors = sorted({a for g, v in by_type.items() if g in DROP_COMPONENT for a in v})
    if not actors:
        return {}
    if len(actors) > RESIDENT_MAX:  # past vanilla's longest list, none (drops like with no preloading)
        return {"_drops_resident": {"actors": [], "skipped": actors}}
    src = sarc_files(fs.read(RANDO_DROPS_SRC[0]))
    item = byml_load(src[RANDO_DROPS_SRC[2]])[0]["Items"][0]
    packs = set()
    for g in sorted(t for t in by_type if t in DROP_COMPONENT):
        dp, holders = _drop_param_of(g, romfs)
        assert dp == RANDO_DROP_DEFAULT, (g, dp)
        packs |= set(holders)
    out = []
    for pk in sorted(packs):
        for a in actors:
            out += [{"pack": pk, "file": RANDO_DROPS[0].format(a), "new_from": RANDO_DROPS_SRC[1],
                     "from_pack": RANDO_DROPS_SRC[0],
                     "set": {"DropTableName": f"RandoDrop_{a}", "SubTableList": [_work(RANDO_DROPS[1].format(a))]}},
                    {"pack": pk, "file": RANDO_DROPS[1].format(a), "new_from": RANDO_DROPS_SRC[2],
                     "from_pack": RANDO_DROPS_SRC[0],
                     "set": {"Items": [dict(item, DropActorName=f"Work/Actor/{a}.engine__actor__ActorParam.gyml",
                                            DropCreateCount=1)]}}]
    old = _vanilla_drop_list(RANDO_DROP_DEFAULT, None, romfs)
    out.append({"pack": sorted(packs), "file": RANDO_DROP_DEFAULT,
                "set": {"DropTableResourceList": old + [_work(RANDO_DROPS[0].format(a)) for a in actors]}})
    return {"packs": out, "_drops_resident": {"actors": actors, "params": [RANDO_DROP_DEFAULT]}}


def _vanilla_drop_list(dp, pack, romfs):
    """The vanilla DropTableResourceList of DropParam file `dp` (a component copy: the boulder's)."""
    from romtools import Romfs, sarc_files, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    if dp == RANDO_DROP_DEFAULT:  # our copy, so the list of the boulder's Drop_Default it was made from
        dp, pack = DROP_DEFAULT, DROP_COMPONENT_SRC
    files = sarc_files(fs.read(pack))
    if dp not in files:
        files = sarc_files(fs.read(DROP_COMPONENT_SRC))
    return list(byml_load(files[dp])[0].get("DropTableResourceList") or [])


def verify_drop_resources(patch_dir, plan, romfs=DEFAULT_ROMFS):
    """Reads Drop preloading back and returns [problem], n placements. For every plan placement naming a
    Drop__DropActor, its type's DropParam resource list in the patch has to name a table whose items name that actor
    (and the ammo switch's other)."""
    from romtools import Romfs, sarc_files, byml_load
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad, cache, n = [], {}, 0
    if not (plan.get("_drops_resident") or {}).get("actors"):
        return bad, n  # no preload (none to make, or past RESIDENT_MAX), drops like with no preloading
    by_type = {g: v for g, v in _dropper_drops(plan.get("placements", [])).items() if g in DROP_COMPONENT}

    def named(g):
        if g in cache:
            return cache[g]
        try:
            files = sarc_files(new.read(f"Pack/Actor/{g}.pack.zs"))
        except (FileNotFoundError, OSError):
            cache[g] = None
            return None
        out, cur, seen, lst = set(), _inner(_components(files, g).get("DropRef") or ""), set(), None
        while cur and cur in files and cur not in seen and lst is None:
            seen.add(cur)
            d = byml_load(files[cur])[0]
            lst = d.get("DropTableResourceList")
            cur = _inner(d["$parent"]) if d.get("$parent") else None
        for t in lst or []:
            tf = _inner(t)
            for st in (byml_load(files[tf])[0].get("SubTableList") or []) if tf in files else []:
                sf = _inner(st)
                d = byml_load(files[sf])[0] if sf in files else {}
                for it in d.get("Items") or []:
                    if it.get("DropActorName"):
                        out.add(it["DropActorName"].split("/")[-1].split(".")[0])
        cache[g] = out
        return out
    for g, actors in sorted(by_type.items(), key=lambda kv: str(kv[0])):
        have = named(g)
        if have is None or (not have and _drop_param_of(g, romfs)[0] is None):
            continue  # no resource list (a chest: its holder's slot)
        n += 1
        missing = sorted(actors - (have or set()))
        if missing:
            bad.append(f"{g}: drops {missing}, which its DropParam's resource tables don't name (loaded only when first "
                       f"asked for: a drop right after arriving can come to nothing)")
    return bad, n


def resolve_drop(files, actor, drop_actor, drop_table=None):
    """What a dropper of type `actor` (its pack's files) drops for a placement's Drop__DropActor / Drop__DropTable, read
    the way the game reads its drop resources. Returns (drop actor or None, chance %, how, [shape problem]).
    It goes through the DropParam's DropTableResourceList, each table's sub-tables and their items. An entry naming the
    drop actor gives its chance (vanilla is 100 % wherever a placement drops an actor its tables name). With no entry
    naming it, it's created as named (100).
    Shapes past vanilla's (VANILLA_MAX_TABLES, VANILLA_MAX_ITEMS, an actor named at 0 %, chances past 100 in one
    sub-table) are problems, because the engine was never shown to take them."""
    from romtools import byml_load
    shape, cur, seen, lst = [], _inner(_components(files, actor).get("DropRef") or ""), set(), None
    while cur and cur in files and cur not in seen and lst is None:
        seen.add(cur)
        d = byml_load(files[cur])[0]
        lst = d.get("DropTableResourceList")
        cur = _inner(d["$parent"]) if d.get("$parent") else None
    if lst is None:
        return drop_actor, 100, "no drop resources (a chest: its holder's slot)", shape
    if len(lst) > VANILLA_MAX_TABLES:
        shape.append(f"{len(lst)} tables in its DropTableResourceList (vanilla at most {VANILLA_MAX_TABLES})")
    names, chances, vanilla = set(), [], []
    for t in lst:
        tf = _inner(t)
        if tf not in files:
            shape.append(f"listed table {tf} missing from its pack")
            continue
        td = byml_load(files[tf])[0]
        names.add(td.get("DropTableName") or "")
        if drop_table and (td.get("DropTableName") or "") != drop_table:
            continue  # a placement naming its table draws from that one only (Guaranteed named drops: fixed_drop_ops)
        for st in td.get("SubTableList") or []:
            sf = _inner(st)
            if sf not in files:
                shape.append(f"sub-table {sf} missing from its pack")
                continue
            items = byml_load(files[sf])[0].get("Items") or []
            if len(items) > VANILLA_MAX_ITEMS:
                shape.append(f"{sf.split('/')[-1].split('.')[0]}: {len(items)} items (vanilla at most "
                             f"{VANILLA_MAX_ITEMS})")
            if sum(int(i.get("DropProbability") or 0) for i in items) > 100:
                shape.append(f"{sf.split('/')[-1].split('.')[0]}: chances add up past 100 %")
            for i in items:
                n = (i.get("DropActorName") or "").split("/")[-1].split(".")[0]
                if n and not i.get("DropProbability"):
                    shape.append(f"{sf.split('/')[-1].split('.')[0]} names {n} at 0 % (no vanilla entry does)")
                if n and n == drop_actor:
                    (chances if (td.get("DropTableName") or "").startswith("RandoDrop") else vanilla).append(
                        int(i.get("DropProbability") or 0))
    if drop_table and drop_table != "None" and drop_table not in names:
        shape.append(f"Drop__DropTable {drop_table} names no listed table")
    if not drop_actor:
        return None, 0, "no Drop__DropActor", shape
    if chances or vanilla:
        k = len(chances + vanilla)
        how = f"named by {k} table entr{'y' if k == 1 else 'ies'}" + ("" if chances else " (vanilla)")
        return drop_actor, min(chances + vanilla), how, shape
    return drop_actor, 100, "created as named (no table names it)", shape


# Guaranteed named drops
# When a named Drop__DropActor has to appear, we give it an empty drop table. Without Drop__DropTable the game uses the
# dropper's default weights, and those weights covered seed rupees at eight spots: two child Kakariko beehives
# (Obj_Kokiri_Beehive_A_01, DropTable_ResourceSupply_01: 30% blue, 70% green) and six Desert Colossus palm fruits
# (Obj_Gerudo_PalmFruit_A_01, DropTable_ResourceSupply_02: 45% green, 15% blue).
# I'm not sure the game rolls the table for a named actor at all. Nine vanilla Kakariko beehives name Obj_Rupee_Blue
# with that same table, which suggests the actor is created directly. So we do what the Gerudo Fortress thieves do: name
# the key with Drop__DropActor and use "None" (DropTable_None). Then the named actor drops with nothing extra from the
# table.
FIXED_TABLE = "None"


def fixed_drop_ops(placements, romfs=DEFAULT_ROMFS):
    """Guaranteed named drops. Sets Drop__DropTable "None" on each plan placement naming a Drop__DropActor (twins aside)
    that its type's drop resources give below 100 %, where the type lists the None table. The resources are read the way
    resolve_drop reads them, with the placement's own Drop__DropTable (the op's or the vanilla one).
    Edits the ops in place and returns {"file#hash": [type, actor, chance before]} for the spots it changed."""
    from romtools import Romfs, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    packs, out = {}, {}
    for op in placements:
        st = op.get("set") or {}
        a = st.get("Dynamic.Drop__DropActor")
        if not a or op.get("twin") is not None:
            continue
        van = _vanilla_level(op["file"]).get(str(op["hash"])) or {}
        g = st.get("Gyaml") or van.get("Gyaml")
        if g not in packs:
            try:
                packs[g] = sarc_files(fs.read(f"Pack/Actor/{g}.pack.zs"))
            except (FileNotFoundError, OSError):
                packs[g] = None
        if packs[g] is None:
            continue
        table = st.get("Dynamic.Drop__DropTable") or (van.get("Dynamic") or {}).get("Drop__DropTable")
        _, chance, _, _ = resolve_drop(packs[g], g, a, table)
        if chance >= 100:
            continue
        _, after, _, shape = resolve_drop(packs[g], g, a, FIXED_TABLE)
        if after < 100 or any("names no listed table" in x for x in shape):
            continue  # no None table to name, the read-back reports it
        st["Dynamic.Drop__DropTable"] = FIXED_TABLE
        out[f"{op['file'].split('/')[-1]}#{op['hash']}"] = [g, a, chance]
    return dict(sorted(out.items()))


def verify_drop_resolve(patch_dir, plan, romfs=DEFAULT_ROMFS, show=()):
    """Reads the drop tables back so no pot drops nothing. Returns [problem], n spots, {"shown": {spot: resolution},
    "notes": [...]}.
    Every placement of the plan naming a Drop__DropActor (twins aside) has to resolve to that actor at 100 % with drop
    resources of vanilla shape, through its type's patched pack and its Drop__DropTable (the plan's, else its vanilla
    one), and the actor's pack has to exist. Below 100 % is a problem, a vanilla table's entry too (Guaranteed named
    drops).
    `show` is (file, hash) pairs whose resolution gets returned."""
    from romtools import Romfs, sarc_files
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad, packs, shapes, n, shown, have, notes = [], {}, {}, 0, {}, {}, []
    show = {(f, str(h)) for f, h in show}
    for op in plan.get("placements", []):
        st = op.get("set") or {}
        a = st.get("Dynamic.Drop__DropActor")
        if not a or op.get("twin") is not None:
            continue
        g = st.get("Gyaml") or (_vanilla_level(op["file"]).get(str(op["hash"])) or {}).get("Gyaml")
        if g not in packs:
            try:
                packs[g] = sarc_files(new.read(f"Pack/Actor/{g}.pack.zs"))
            except (FileNotFoundError, OSError):
                packs[g] = None
        if packs[g] is None:
            bad.append(f"{g}: no pack (drops {a})")
            continue
        n += 1
        table = st.get("Dynamic.Drop__DropTable") or \
            ((_vanilla_level(op["file"]).get(str(op["hash"])) or {}).get("Dynamic") or {}).get("Drop__DropTable")
        got, chance, how, shape = resolve_drop(packs[g], g, a, table)
        for x in shape:
            shapes.setdefault(f"{g}: {x}", 0)
            shapes[f"{g}: {x}"] += 1
        if a not in have:
            try:
                new.read(f"Pack/Actor/{a}.pack.zs")
                have[a] = True
            except (FileNotFoundError, OSError):
                have[a] = False
        where = f"{op['file'].split('/')[-1]}#{op['hash']}"
        if not have[a]:
            bad.append(f"{where} ({g}) drops {a}, which has no actor pack")
        if chance < 100:
            bad.append(f"{where} ({g}) drops {a} only {chance} % of the time ({how}, table {table or 'default'})")
        if (op["file"], str(op["hash"])) in show:
            shown[where] = {"type": g, "drop": got, "chance": chance, "how": how, "shape_ok": not shape}
    bad += [f"{k} ({v} spot{'s' if v > 1 else ''})" for k, v in sorted(shapes.items())]
    return bad, n, {"shown": shown, "notes": notes}


def verify_falls(patch_dir, plan, romfs=DEFAULT_ROMFS, m=None):
    """Reads a built patch back to check that every pickup an object of the plan drops comes down to the ground (Falling
    pickups). Returns ([problem], {type: n}).
    For each Drop__DropActor the plan sets on an object, its patched pack's main rigid body has to be Dynamic, hit the
    ground and have its contact collection and a DropBoundParam, and its GameActorInfo row has to name the body's layer.
    A Gold Skulltula's own token is the exception, it stays where the skulltula died like in the vanilla game, and
    enemies aren't pickups. Every type fall_ops changed has to hold the new files the same way in every pack holding
    them."""
    from romtools import Romfs, sarc_files, byml_load
    m = m or _map()
    out = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch_dir])
    where = {}
    for sec in ("drops", "new"):
        for n, e in (m.get(sec) or {}).items():
            for p in e.get("placements", []):
                where[(p["file"], str(p["hash"]))] = (n, p)
    pickups = set(DROP_ACTOR.values()) | {DISGUISE_ACTOR, "Obj_Dungeon_SmallKey"}
    used = {}
    for op in plan.get("placements", []):
        a = (op.get("set") or {}).get("Dynamic.Drop__DropActor")
        if not a or a not in pickups or op.get("twin") is not None:
            continue
        n, p = where.get((op["file"], str(op["hash"])), (None, None))
        if p is not None and p.get("category") == "gold_skulltula" and a == "Obj_Token_Gold":
            continue
        used.setdefault(a, []).append(n or f"{op['file'].split('/')[-1]}#{op['hash']}")
    rows = {r.get("__RowId"): r for r in byml_load(out.read(GAME_ACTOR_INFO))[0]}
    bad = []
    for a, spots in sorted(used.items()):
        if a in FLIES:
            continue
        why, _ = _body_of(sarc_files(out.read(f"Pack/Actor/{a}.pack.zs")), a, rows)
        if why:
            bad.append(f"{a} dropped by {len(spots)} object(s) (e.g. {sorted(spots)[0]}): {why}")
    return bad, {a: len(s) for a, s in used.items()}


TAG_SRC = {"get": ({"pack": AI_GLOBAL, "file": "AI/Enemy_ReDead.utility.root.ainb"}, {"QueryBlackboardGetF32": 40}),
           "add": ({"pack": AI_GLOBAL, "file": "AI/CancelSleepFallingRock_3.module.ainb"},
                   {"QueryBlackboardOverwriteParamAddF32": 12}),
           "equal": ({"pack": AI_GLOBAL, "file": "AI/AIScheduleThreatReaction.actionseq.root.ainb"},
                     {"QueryMathEqualF32": 34})}


# Flagless drops
# An object with no save flag of its own can still give one item once. That's trees, bushes, respawning grass and pots,
# which have no Bool64bitKey for their placement hash, and the save list can't grow. It gets a borrowed saved Bool
# (tools/rando/free_flags.py) and always drops the carrier with a tag of its own. The get-scene hook gives the item and
# sets that flag (a repeat gives nothing).
# Once the flag is set a respawning pot or grass is gone (a negated placement Presence on it), and a tree counts itself
# as already shaken. The tree's placement names the flag in DROP_FLAG_KEY, a String instance parameter added to the Drop
# table, which the tree's root AI reads (_tree_edits).
DROP_FLAG_KEY = "Drop__RandoFlag"
# a placement of the respawn model whose drop can't record it, so its break sets its checked bit (save_on_break_edits)
DROP_SAVE_KEY = "Drop__RandoSaveOnBreak"
SAVE_ON_BREAK_SRC = {
    "dead": ({"pack": "Pack/Actor/Obj_Heart_Piece.pack.zs", "file": "AI/Obj_Heart_Piece.root.ainb"}, 1),
    "own": ({"pack": "Pack/Actor/Obj_Heart_Piece.pack.zs", "file": "AI/Obj_Heart_Piece.root.ainb"},
            {"BoolSelector": 9, "OneshotDoNothing": 10}),
    "getbool": ({"pack": "Pack/AI.Global.Product.111.pack.zs", "file": "AI/NpcCommon.event.root.ainb"}, 640)}

# The respawn model (OoTR / Ship of Harkinian)
# OoTR counts a pot as checked once its item is taken. The pot itself keeps respawning as in vanilla, and once it's
# checked it drops its vanilla contents and looks like any pot. The remake has one per-object save row the game reads,
# the placement's own Bool64bitKey, which means "broken this visit" and resets when the area changes. So the "checked"
# record is new. It's a bit of a saved bool array (CHECKED_ARRAY, make_patch "add_bool_arrays", one bit per location),
# and bit 0 is what every other drop sets, so it's unused. For each placement:
#  - it names its bit (DROP_CHK_KEY, an S32 instance parameter of the shared Drop table), and its type's root AI hands
#    the bit to what it drops (QueryBlackboardOverwriteParamAddS32 as PICKUP_CHK_KEY, next to RespawnGmdHash). The
#    pickup sets the bit when taken (OneShotSetNonStructGameDataBool on CHECKED_ARRAY, GameDataIndex = the bit), the
#    same way GameDataActor's event AI feeds array indexes. A drop that can't (a token, an enemy, a fairy) gets
#    DROP_SAVE_KEY, and then the break sets the bit (save_on_break_edits). Ammo saves when taken (Ammo touch pickups).
#  - it leaves the world as soon as its bit is set, through a lazy negated Presence (TWIN_PRESENCE) on an expression
#    flag of its own. That's CHECKED_EXP, opcode 8, one bool array element, like vanilla's 7 such BoolExps (make_patch
#    "add_boolexp"; vanilla Presences name BoolExps). A vanilla Presence of its own is kept inside the expression.
#  - it gets a twin, a copy of its vanilla placement under hash ^ 2. That's the second, permanent row every Drop object
#    has, otherwise only written by pickups and read by the CollectSign display. The row gets the placement's own reset
#    type and area, and the twin the positive Presence, so from the next load the vanilla object stands there and
#    breaks, drops and respawns as in vanilla. Only one of the two exists at a time.
# Objects permanent in vanilla (reset type 24: bomb boulders, red ice, silver rocks) get an area reset instead, so they
# come back with their item until it's taken, and no twin. Breaks keep saving (vanilla), so a broken object stays broken
# for the visit. Respawning objects with no flag of their own (FLAGLESS "presence") keep their borrowed flag and get a
# twin under a hash with no row, so it respawns on every load like they do.
CHECKED_ARRAY = "RandoChecked"
CHECKED_EXP = "RandoChk_{:04d}"
# VISIT. The game re-checks a placement's Presence the moment its flag changes, lazy or not. In the guard-room test
# every twin stood there the moment its item was taken, though its Presence is non-lazy (TWIN_PRESENCE). So a twin also
# waits for this visit's bit to clear. Whatever sets CHECKED_ARRAY[bit] (a pickup, the heart piece's and token's death
# branch, a recording break) sets VISIT_ARRAY[bit] just before it, and a twin's Presence is "checked and not visited".
# VISIT_ARRAY is runtime only and reset at every map change (SaveFileIndex -1, ResetTypeValue 1, and ChangeBanc runs
# ResetType 0). Vanilla's per-scene arrays MiniGame_DampeRace_*Checkpoints are made the same way, and vanilla
# expressions do read runtime flags. So the expression can't turn true during the visit the item was taken in. From the
# next load the twin's own row decides (Vanilla respawn).
#
# Vanilla respawn (main = 0x80020000 + offset in work/sa/image/image.bin). A broken pot stays away while its own
# Bool64bitKey row is set. The level loader looks the placement's hash up and marks it dead (0x5AF7D4-0x5AF8A0), and a
# dead placement isn't created. Breaking it marks it dead and sets the row (0xF07040). Its row's reset type decides when
# it comes back (bit n is cleared by SeqExecuteResetGameData ResetType n, 0x32C3360, queued at GameDataMgr+0xCB8):
#  - 88 (8|16|64) with an ExtraByte area (1-30) uses the area counter (the AutoSaveMgr). Changing maps inside an area
#    changes nothing. Leaving an area starts its counter at 43200 (Sequence/AfterChangeBanc's
#    SeqOneShotAutoSaveMgrResetInvalidOldAreaCounter, only when the area changed: 0xBA7980 -> 0xBA7A20), and a counter
#    that's already running isn't restarted. Every frame each running counter goes down by the frame step (0x32762B0).
#    When one reaches 0, a job (0x11A4C70) clears every row whose ExtraByte & 0x7F is that area, if a random roll passes
#    (a game parameter, not traced) and never for the area the player is in. The counter then stops (-1) until the area
#    is left again. Counters (saved FloatArray 0x8F76B998), current and previous area (saved Ints 0x73736CDE,
#    0x37C3F735) and the rows (SaveFileIndex 0) are all in the save, so a save and reload changes nothing.
#  - 88 without an ExtraByte never comes back (the job skips ExtraByte 0), and 24 never either. 280 (enemies, flying
#    pots) is bit 8, every map change (ChangeBanc runs ResetType 0 and 8) and every load. 25 (fairies, scrub leaves) is
#    every map change. No row (the *_Respawn pots, bushes, trees) means back at every load.
#  - A reset group's SupplyItemResetSystemActor (its own row 88, ExtraByte 128 + area) dies and saves its row the first
#    time any linked member is dead (ExecuteSupplyItemResetSystem's update, 0x2866310 -> 0xF07040). I didn't trace what
#    reads GmdReset, but a twin is a full member (links and DstHash, group_join_ops), so the group does to it whatever
#    it does to its source. No code clears a row mid-visit except the area job (never the current area), and revive
#    messages (0x1FB00001) are only sent along RespawnFlagSyncLink (0x2DE6D50).
# A twin's row follows its source's row's rule (_respawn_ops; verify_respawn) and is set when its spot is checked (the
# pickup, or the drop's appearance, see Save on spawn), so the twin comes back exactly when its pot would have. VISIT
# never delays that. The area job never clears the current area, and getting back there is a map change, which clears
# it.
VISIT_ARRAY = "RandoVisit"
# Unchecked respawn. My rule, same as OoTR and Ship of Harkinian: a check can never be lost. A shuffled original whose
# item wasn't taken comes back with it when the player leaves and returns. Its own row keeps its vanilla reset plus bit
# 0, which every map change and every load clears (ChangeBanc runs SeqExecuteResetGameData ResetType 0, loading a save
# 0, 3 and 8). That's the rule of the game's own placed fairies and Business Scrub leaves (Bool64bitKey rows 25 = 24 |
# 1: 113 Obj_FairySpirit, 30 Obj_Fairy, 81 scrub leaves, 24 sold-out boards).
# A drop is a runtime actor, gone with the map, so the original can't come back while its first drop still lies there.
# Once it's checked, the original's lazy "not checked" Presence keeps it away whatever its row says, and its twin (hash
# ^ 2) keeps the vanilla row (Vanilla respawn).
# A room inside a map (the Market guard house's pot room) has no such reset in the game files. The game's own room-level
# comebacks are logic modules (ActorLogicSimpleActor RespawnTrigger fed by an Area sensor, e.g.
# Logic/ForestTemple_Level_Room_00's Wolfos, BottomOfTheWell_Level_Room_10's grass).
MAP_RESET = 1
# Twinless placements
# A placement that a link or logic module points at can't have a twin standing in for it. That's palm fruit on their
# trees, the Ice Cavern and Ganon's Castle icicles and red ice, Kokiri Forest's rocks and grass, crates in a
# RespawnFlagSyncLink pair, and pots frozen in red ice. The flying pots and cow skulls had no hand-over either. They
# take the model without a twin, with the same bit, Presence and map-reset row. So an item left behind is back after any
# map change or load, and once it's taken the object is gone for good (nothing plain stands in). No shuffled spot loses
# an item.
DROP_CHK_KEY = "Drop__RandoChk"   # the placement's checked bit (Drop table, instance parameter; 0 = none)
PICKUP_CHK_KEY = "RandoChk"       # what its drop receives (DropItem / DropActorRespawnData tables)
CHK_SRC = {"get": ({"pack": AI_GLOBAL, "file": "AI/Camera.event.root.ainb"}, 285),  # QueryBlackboardGetS32
           # QueryBlackboardOverwriteParamAddS32. Its S32 reads Bari's blackboard, so the copy gets a value, then a
           # feed.
           "add": ({"pack": "Pack/Actor/Enemy_Bari.pack.zs", "file": "AI/Bari.action.interruptdie.module.ainb"}, 22),
           "set": ({"pack": AI_GLOBAL, "file": "AI/Door.root.ainb"}, 21)}  # OneShotSetNonStructGameDataBool
HP_DEATH_SIM = 6  # Obj_Heart_Piece.root: the death branch's Simultaneous (OneShotHeartPieceTakenDeadAfter + signal)
TOKEN_PACK, TOKEN_AI = "Pack/Actor/Obj_Token_Gold.pack.zs", "AI/Item_Token_Gold.root.ainb"
TOKEN_DEATH_SIM = 8  # Item_Token_Gold.root: the death branch's Simultaneous (OneShotGoldTokenDeadAfter + signal)
TOKEN_TABLE = "Component/Blackboard/BlackboardParamTable/Item_Token_Gold.engine__component__BlackboardParamTable.bgyml"
TWIN_SALT = (1 << 61, 1 << 60, 1 << 59)  # flagless twins get hash ^ one of these, the first with no save row


def _chk_get(label, key):
    """Edits copying a QueryBlackboardGetS32 of the actor's own table key `key` as `label`. Returns (edits, ref)."""
    src, i = CHK_SRC["get"]
    ref = f"{label}:{i}"
    return [{"copy": {"from": src, "nodes": [i], "label": label, "follow": False}},
            {"set_property": {"node": ref, "name": "BlackboardType", "value": 1}},
            {"set_property": {"node": ref, "name": "BlackboardKey", "value": key}},
            {"set_property": {"node": ref, "name": "OutputOnlyOnEnter", "value": False}}], ref


def _chk_hand(label):
    """Edits for the dropper's hand-over node (DROP_CHK_KEY -> the overwrite param's PICKUP_CHK_KEY), unlinked. Returns
    (edits, ref of the add node)."""
    edits, get = _chk_get(f"{label}g", DROP_CHK_KEY)
    src, i = CHK_SRC["add"]
    add = f"{label}a:{i}"
    return edits + [{"copy": {"from": src, "nodes": [i], "label": f"{label}a", "follow": False,
                              "values": {i: {"S32": 0}}}},
                    {"set_property": {"node": add, "name": "Key", "value": PICKUP_CHK_KEY}},
                    {"feed": {"from": get, "output": "S32", "to": add, "input": "S32"}}], add


def _chk_set(label, key, array=CHECKED_ARRAY):
    """Edits for a node that sets `array`[the actor's table key `key`] to true, not anyone's child yet. Returns (edits,
    ref of the set node)."""
    edits, get = _chk_get(f"{label}g", key)
    src, i = CHK_SRC["set"]
    st = f"{label}s:{i}"
    return edits + [{"copy": {"from": src, "nodes": [i], "label": f"{label}s", "follow": False}},
                    {"set_input": {"node": st, "name": "GameDataFullName", "value": array}},
                    {"set_input": {"node": st, "name": "Value", "value": True}},
                    {"feed": {"from": get, "output": "S32", "to": st, "input": "GameDataIndex"}}], st


def _chk_pair(label, key, parent):
    """Edits putting VISIT_ARRAY[key] then CHECKED_ARRAY[key] setters first under Simultaneous `parent` (VISIT)."""
    edits, chk = _chk_set(label, key)
    vedits, vis = _chk_set(f"{label}v", key, VISIT_ARRAY)
    return edits + vedits + [{"add_child": {"parent": parent, "child": chk, "first": True}},
                             {"add_child": {"parent": parent, "child": vis, "first": True}}]


def hp_chk_edits():
    """Obj_Heart_Piece.root (heart pieces, the disguise carrier): its death branch also sets the dropper's bit."""
    return _chk_pair("hpc", PICKUP_CHK_KEY, HP_DEATH_SIM)


def token_chk_edits():
    """Edits for Item_Token_Gold.root (the Gold Skulltula token). Its death branch (OneShotGoldTokenDeadAfter + signal)
    also sets the dropper's bit, first. A Gold Skulltula hands no bit, so its tokens set bit 0, which no spot uses."""
    return _chk_pair("tkc", PICKUP_CHK_KEY, TOKEN_DEATH_SIM)


def save_on_break_edits():
    """Root-AI edits so that with DROP_SAVE_KEY set (BlackboardType 1, no error when absent, read once), dying sets the
    placement's checked bit (DROP_CHK_KEY). That's the respawn model's record when its drop can't make one."""
    dead_src, dead_i = SAVE_ON_BREAK_SRC["dead"]
    own_src, own = SAVE_ON_BREAK_SRC["own"]
    gb_src, gb_i = SAVE_ON_BREAK_SRC["getbool"]
    sel, idle = own["BoolSelector"], own["OneshotDoNothing"]
    setter, st = _chk_set("sbc", DROP_CHK_KEY)
    vsetter, vst = _chk_set("sbv", DROP_CHK_KEY, VISIT_ARRAY)
    both = f"sbsim:{HP_DEATH_SIM}"  # a Simultaneous (the heart piece's death branch's, its children not copied)
    return setter + vsetter + [
        {"copy": {"from": own_src, "nodes": [HP_DEATH_SIM], "label": "sbsim", "follow": False}},
        {"add_child": {"parent": both, "child": vst}},
        {"add_child": {"parent": both, "child": st}},
        {"copy": {"from": dead_src, "nodes": [dead_i], "label": "sbdead", "follow": False}},
        {"copy": {"from": own_src, "nodes": [sel], "label": "sbsel1", "follow": False}},
        {"copy": {"from": own_src, "nodes": [sel], "label": "sbsel2", "follow": False}},
        {"copy": {"from": own_src, "nodes": [idle], "label": "sbidle1", "follow": False}},
        {"copy": {"from": own_src, "nodes": [idle], "label": "sbidle2", "follow": False}},
        {"copy": {"from": gb_src, "nodes": [gb_i], "label": "sbget", "follow": False}},
        {"set_property": {"node": f"sbget:{gb_i}", "name": "BlackboardType", "value": 1}},
        {"set_property": {"node": f"sbget:{gb_i}", "name": "BlackboardKey", "value": DROP_SAVE_KEY}},
        {"set_property": {"node": f"sbget:{gb_i}", "name": "OutputOnlyOnEnter", "value": True}},
        # The placement's save-on-break setting is checked before death is queried, since most objects never need that
        # query.
        {"feed": {"from": f"sbget:{gb_i}", "output": "Bool", "to": f"sbsel1:{sel}", "input": "Input"}},
        {"feed": {"from": f"sbdead:{dead_i}", "output": "IsDead", "to": f"sbsel2:{sel}", "input": "Input"}},
        {"add_child": {"parent": f"sbsel1:{sel}", "child": f"sbsel2:{sel}", "name": "True"}},
        {"add_child": {"parent": f"sbsel1:{sel}", "child": f"sbidle1:{idle}", "name": "False"}},
        {"add_child": {"parent": f"sbsel2:{sel}", "child": both, "name": "True"}},
        {"add_child": {"parent": f"sbsel2:{sel}", "child": f"sbidle2:{idle}", "name": "False"}},
        {"add_child": {"parent": "@Root", "child": f"sbsel1:{sel}"}}]


# Save on spawn
# A checked spot's twin obeys the vanilla rule for a broken pot (Vanilla respawn below). The twin's own row (hash ^ 2,
# given its source's reset type and area) is what keeps it away. The level loader marks a placement dead at every load
# while its row is set (main 0x5AF7D4-0x5AF8A0), and the game's own reset for that row type brings it back.
# A drop that records the check sets that row when it's taken (OneShotHeartPieceTakenDeadAfter sets RespawnGmdHash and
# RespawnGmdHash ^ 2, main 0x28E2DD0). A drop that can't record it (a fairy, or a classic ice trap's keese, where the
# break records it through save_on_break_edits) sets it the moment it appears, so at the break. It does that with the
# same node, run once when its AI starts, on the RespawnGmdHash its dropper hands over (pickup_save_ops step 1, a
# blackboard overwrite at creation). And only for a respawn-model dropper, whose handed bit (PICKUP_CHK_KEY) is not 0
# (QueryMathNotEqualS32 -> BoolSelector). A vanilla pot or a Gold Skulltula hands bit 0, so every other actor running
# the same AI is untouched. A vanilla object's hash ^ 2 row would hide a Gold Skulltula's map icon (CollectSign).
INSECT_TABLE = "Component/Blackboard/BlackboardParamTable/Insect_Base.engine__component__BlackboardParamTable.bgyml"
KEESE_TABLE = "Component/Blackboard/BlackboardParamTable/Enemy_Keese.engine__component__BlackboardParamTable.bgyml"
# drop type -> (its AI file, how the gate runs once, the blackboard table its pack reads the keys from), in every pack
# holding the file ("*"). The gate runs once as "enter", its root SplitTiming's Enter, or "root", a branch of its root
# Simultaneous.
# Not AI.Global's DropItem.root. The rupees run that file too and save when taken, so a gate there would save a rupee's
# spot the moment it appears. Its ammo types save when taken (TOUCH_AMMO, Ammo touch pickups), Obj_Bombchu never drops
# as itself, and spawn_save_ops refuses it.
SPAWN_SAVE = {"Obj_Fairy": ("AI/Obj_Fairy.brain.root.ainb", "enter", INSECT_TABLE),  # its BSAParam BrainAinPath
              **{k: ("AI/Keese.brain.root.ainb", "enter", KEESE_TABLE)
                 for k in ("Enemy_Keese", "Enemy_Keese_Fire", "Enemy_Keese_Ice")}}
SPAWN_SAVE_NODE = "OneShotHeartPieceTakenDeadAfter"
SPAWN_NE_SRC = ({"pack": AI_GLOBAL, "file": "AI/NPCCommon.interruptseq.root.ainb"}, 19)  # QueryMathNotEqualS32
# Its S32 is a constant, so the input gets fed through S32Base.


def spawn_save_type(actor):
    """True if `actor` dropped at a respawn-model spot saves its dropper's rows when it appears (Save on spawn)."""
    return not sets_bit_on_pickup(actor)


def _spawn_save_edits(fs, ai_file, how):
    """Edits that run SPAWN_SAVE_NODE once when `ai_file`'s AI starts, for a respawn-model drop (Save on spawn)."""
    from romtools import sarc_files
    import ainb
    hp = ainb.Ainb(sarc_files(fs.read(HP_PACK))[HP_AI])
    n = hp.node(SPAWN_SAVE_NODE)
    src = {"pack": HP_PACK, "file": HP_AI}
    own_src, own = SAVE_ON_BREAK_SRC["own"]
    sel, idle = own["BoolSelector"], own["OneshotDoNothing"]
    ne_src, ne = SPAWN_NE_SRC
    get_edits, get = _chk_get("spg", PICKUP_CHK_KEY)
    gate = f"spsel:{sel}"
    edits = get_edits + [
        {"copy": {"from": ne_src, "nodes": [ne], "label": "spne", "follow": False, "values": {ne: {"S32": 0}}}},
        {"feed": {"from": get, "output": "S32", "to": f"spne:{ne}", "input": "S32Base"}},
        {"copy": {"from": own_src, "nodes": [sel], "label": "spsel", "follow": False}},
        {"copy": {"from": own_src, "nodes": [idle], "label": "spidle", "follow": False}},
        {"copy": {"from": src, "nodes": [n], "label": "spn", "follow": False}},
        {"feed": {"from": f"spne:{ne}", "output": "Bool", "to": gate, "input": "Input"}},
        {"add_child": {"parent": gate, "child": f"spn:{n}", "name": "True"}},
        {"add_child": {"parent": gate, "child": f"spidle:{idle}", "name": "False"}}]
    if how == "root":
        return [{"wrap": {"command": "Root", "if_needed": True}}] + edits + [
            {"add_child": {"parent": "@Root", "child": gate}}]
    a = ainb.Ainb(sarc_files(fs.read(_carrier(ai_file, DEFAULT_ROMFS)))[ai_file])
    root = next(c["main"] for c in a.commands if c["name"] == "Root")
    if ainb.NODE_TYPES.get(a.nodes[root]["type"]) != "SplitTiming" and a.nodes[root]["name"] != "SplitTiming":
        raise DropPlanError(f"{ai_file}: its Root no longer starts at a SplitTiming")
    (enter,) = [pl["node"] for pl in a.nodes[root]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "Enter"]
    both = f"sps:{HP_DEATH_SIM}"  # a Simultaneous (the heart piece's death branch's, its children not copied)
    return edits + [{"copy": {"from": src, "nodes": [HP_DEATH_SIM], "label": "sps", "follow": False}},
                    {"add_child": {"parent": both, "child": enter}},
                    {"add_child": {"parent": both, "child": gate}},
                    {"set_child": {"parent": root, "which": "Enter", "child": both}}]


def spawn_save_ops(pickups, romfs=DEFAULT_ROMFS):
    """make_patch "ainb" entries that give each drop type in `pickups` that can't record its check (spawn_save_type) the
    Save on spawn gate and the keys it reads (u64 RespawnGmdHash, S32 PICKUP_CHK_KEY). Raises DropPlanError for such a
    type with no known AI."""
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out, done_ai, done_tables = [], set(), set()
    for actor in sorted(a for a in pickups if spawn_save_type(a)):
        if actor not in SPAWN_SAVE:
            raise DropPlanError(f"{actor}: a drop that can't record its check has no SPAWN_SAVE hook (its twin "
                                f"would come back at the next map change, before a vanilla pot)")
        ai_file, how, table = SPAWN_SAVE[actor]
        if table not in done_tables:
            done_tables.add(table)
            out.append({"pack": "*", "bb_params": [
                {"table": table, "type": "U64", "key": "RespawnGmdHash", "init": 0},
                {"table": table, "type": "S32", "key": PICKUP_CHK_KEY, "init": 0}]})
        if ai_file not in done_ai:
            done_ai.add(ai_file)
            out.append({"pack": "*", "file": ai_file, "edits": _spawn_save_edits(fs, ai_file, how)})
    return out


GATE_SRC = {"getstr": ({"pack": AI_GLOBAL, "file": "AI/NpcCommon.action.GetUp.module.ainb"},
                       {"QueryBlackboardGetString": 8}),
            "flag": ({"pack": AI_GLOBAL, "file": "AI/BeforehandLoadEventForEscapeFromRanch.module.ainb"},
                     {"QueryGetNonStructGameDataBool": 5}),
            "setstr": ({"pack": AI_GLOBAL, "file": "AI/Bokoblin.action.interruptsmash.module.ainb"},
                       {"ExecuteBlackboardSetString": 8})}


def _tree_edits(fs, pack, ai_file):
    """Edits for a tree type's root AI. The scene-drop tag joins its own drop chain, between
    OneShotDropSetOverWriteParam and the node feeding it. An always-on branch (Root wrapped in a Simultaneous) sets the
    tree's own IsDropped (a copy of its "IsDropped := true" node) while the placement's DROP_FLAG_KEY names a set flag.
    An unnamed placement (a vanilla tree) is left alone, since the name is compared with "" first.
    For Flagless pickups the drop also receives the placement's DROP_CHK_KEY (before the tag), and a placement whose
    DROP_FLAG_KEY is CHECKED_ARRAY counts itself as shaken while CHECKED_ARRAY[its DROP_CHK_KEY] is set
    (QueryGetNonStructGameDataBool's GameDataIndex)."""
    from romtools import sarc_files
    import ainb
    a = ainb.Ainb(sarc_files(fs.read(pack))[ai_file])
    setp = next(i for i, n in enumerate(a.nodes) if n["name"] == "OneShotDropSetOverWriteParam")
    src = a._input(setp, "OverwriteParam")[1]["node"]
    dropped = next(i for i, n in enumerate(a.nodes) if n["name"] == "ExecuteBlackboardSetBool"
                   and {e["name"]: e["value"] for e in n["properties"]["string"]}.get("BlackboardKey") == "IsDropped"
                   and [e["value"] for e in n["inputs"]["bool"] if e["name"] == "Bool"] == [True])
    tree_src = {"pack": pack, "file": ai_file}
    # Flagless pickups. The placement's checked bit (DROP_CHK_KEY) goes with the drop too, before the tag, the way every
    # other dropper hands it (pickup_save_ops _chk_hand). A pickup dropped as itself sets that bit when taken.
    chk, cadd = _chk_hand("tck")
    edits = chk + [{"link": {"from": src, "output": "OverwriteParam", "to": cadd, "input": "OverwriteParam"}}] + \
        _tag_step(cadd, setp) + [{"wrap": {"command": "Root", "if_needed": True}}]
    _, eq_i = _name_sources(fs)
    (s1, n1), (s2, n2) = GATE_SRC["getstr"], GATE_SRC["flag"]
    gi, qi = n1["QueryBlackboardGetString"], n2["QueryGetNonStructGameDataBool"]
    own_src, own = LOOK_SRC["own"]
    bsel, nothing = own["BoolSelector"], own["OneshotDoNothing"]
    name, empty, gd, setter = f"gname:{gi}", f"gempty:{eq_i}", f"gflag:{qi}", f"gset:{dropped}"
    s0, s1_, i0, i1 = f"gsel0:{bsel}", f"gsel1:{bsel}", f"gidle0:{nothing}", f"gidle1:{nothing}"
    # If DROP_FLAG_KEY names CHECKED_ARRAY, DROP_CHK_KEY goes in as GameDataIndex to read that bit, and once it's set
    # the tree counts as already shaken.
    arr, sb, bq, bset, ib = (f"garr:{eq_i}", f"gsel2:{bsel}", f"gbit:{qi}", f"gset2:{dropped}",
                             f"gidle2:{nothing}")
    sa = f"gsel3:{bsel}"
    bget_edits, bget = _chk_get("gbitg", DROP_CHK_KEY)
    bget_edits[-1] = {"set_property": {"node": bget, "name": "OutputOnlyOnEnter", "value": True}}  # (read once)
    gate_bit = bget_edits + [
        {"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": "garr", "follow": False}},
        {"set_input": {"node": arr, "name": "StringB", "value": CHECKED_ARRAY}},
        {"set_property": {"node": arr, "name": "OutputOnlyOnEnter", "value": True}},
        {"feed": {"from": name, "output": "String", "to": arr, "input": "StringA"}},
        {"copy": {"from": own_src, "nodes": [bsel], "label": "gsel3", "follow": False}},
        {"feed": {"from": arr, "output": "IsEqual", "to": sa, "input": "Input"}},
        {"copy": {"from": s2, "nodes": [qi], "label": "gbit", "follow": False}},
        {"set_property": {"node": bq, "name": "DispError", "value": False}},
        {"set_property": {"node": bq, "name": "OutputOnlyOnEnter", "value": True}},
        {"set_input": {"node": bq, "name": "GameDataFullName", "value": CHECKED_ARRAY}},
        {"feed": {"from": bget, "output": "S32", "to": bq, "input": "GameDataIndex"}},
        {"copy": {"from": own_src, "nodes": [bsel], "label": "gsel2", "follow": False}},
        {"feed": {"from": bq, "output": "Value", "to": sb, "input": "Input"}},
        {"copy": {"from": tree_src, "nodes": [dropped], "label": "gset2", "follow": False}},
        {"add_child": {"parent": sb, "child": bset, "name": "True"}},
        {"copy": {"from": own_src, "nodes": [nothing], "label": "gidle2", "follow": False}},
        {"add_child": {"parent": sb, "child": ib, "name": "False"}},
        {"add_child": {"parent": sa, "child": sb, "name": "True"}}]
    return edits + [
        {"copy": {"from": s1, "nodes": [gi], "label": "gname", "follow": False}},
        {"set_property": {"node": name, "name": "BlackboardType", "value": 1}},
        {"set_property": {"node": name, "name": "BlackboardKey", "value": DROP_FLAG_KEY}}] + gate_bit + [
        {"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": "gempty", "follow": False}},
        {"set_input": {"node": empty, "name": "StringB", "value": ""}},
        {"feed": {"from": name, "output": "String", "to": empty, "input": "StringA"}},
        {"copy": {"from": own_src, "nodes": [bsel], "label": "gsel0", "follow": False}},
        {"feed": {"from": empty, "output": "IsEqual", "to": s0, "input": "Input"}},
        {"copy": {"from": own_src, "nodes": [nothing], "label": "gidle0", "follow": False}},
        {"add_child": {"parent": s0, "child": i0, "name": "True"}},
        {"copy": {"from": s2, "nodes": [qi], "label": "gflag", "follow": False}},
        {"set_property": {"node": gd, "name": "DispError", "value": False}},
        # the name, its emptiness and the flag only matter when the tree is created, so they're read once and not every
        # frame. It drops at most once per creation, and a taken item sets the flag after its own drop.
        {"set_property": {"node": name, "name": "OutputOnlyOnEnter", "value": True}},
        {"set_property": {"node": empty, "name": "OutputOnlyOnEnter", "value": True}},
        {"set_property": {"node": gd, "name": "OutputOnlyOnEnter", "value": True}},
        {"feed": {"from": name, "output": "String", "to": gd, "input": "GameDataFullName"}},
        {"copy": {"from": own_src, "nodes": [bsel], "label": "gsel1", "follow": False}},
        {"feed": {"from": gd, "output": "Value", "to": s1_, "input": "Input"}},
        {"add_child": {"parent": s0, "child": sa, "name": "False"}},  # named: CHECKED_ARRAY (its bit) or a flag
        {"add_child": {"parent": sa, "child": s1_, "name": "False"}},
        {"copy": {"from": tree_src, "nodes": [dropped], "label": "gset", "follow": False}},
        {"add_child": {"parent": s1_, "child": setter, "name": "True"}},
        {"copy": {"from": own_src, "nodes": [nothing], "label": "gidle1", "follow": False}},
        {"add_child": {"parent": s1_, "child": i1, "name": "False"}},
        {"add_child": {"parent": "@Root", "child": s0}}]


def _tag_get(label, key):
    """Edits copying a QueryBlackboardGetF32 of the actor's own table key `key` as `label`; returns (edits, ref)."""
    src, nodes = TAG_SRC["get"]
    i = nodes["QueryBlackboardGetF32"]
    ref = f"{label}:{i}"
    return [{"copy": {"from": src, "nodes": [i], "label": label, "follow": False}},
            {"set_property": {"node": ref, "name": "BlackboardType", "value": 1}},
            {"set_property": {"node": ref, "name": "BlackboardKey", "value": key}}], ref


def _tag_step(frm, to):
    """Edits putting the dropper's tag into its drop's overwrite param between nodes `frm` and `to`."""
    edits, get = _tag_get("tget", DROP_TAG_KEY)
    src, nodes = TAG_SRC["add"]
    i = nodes["QueryBlackboardOverwriteParamAddF32"]
    add = f"tadd:{i}"
    return edits + [{"copy": {"from": src, "nodes": [i], "label": "tadd", "follow": False}},
                    {"set_property": {"node": add, "name": "Key", "value": PICKUP_TAG_KEY}},
                    {"feed": {"from": get, "output": "F32", "to": add, "input": "F32"}},
                    {"link": {"from": frm, "output": "OverwriteParam", "to": add, "input": "OverwriteParam"}},
                    {"link": {"from": add, "output": "OverwriteParam", "to": to, "input": "OverwriteParam"}}]


HOOK_SWITCH = "RandoST_LakePickups_tag"  # the get-scene hook's tag switch (parity/_songs_trade_lake.py)
HOOK_SCENES = ("Event/EventFlow/Dm_SY_Get.bfevfl.zs", "Event/EventFlow/Dm_SY_Get_WithoutPlayer.bfevfl.zs")


def verify_scene_drops(patch_dir, scene_drops, tag_looks=None, romfs=DEFAULT_ROMFS, overrides=None, droppers=None):
    """Reads plan "_drops_scene_drops" ({location: tag}) and "_drops_looks_tags" ({tag: [display actors]}) back and
    returns [problem, ...].
    Each spot's placements have to drop the carrier with their tag. The Drop table (every pack holding it) has to
    declare DROP_TAG_KEY as an F32 instance parameter, and the carrier's table PICKUP_TAG_KEY. Every dropper AI hands
    its DROP_TAG_KEY to its drop right before OneShotDropSetOverWriteParam, the carrier's root AI shows exactly each
    tag's display, and both get scenes' tag switch has a case for every tag."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    import evfl
    import packpaths
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad, levels = [], {}
    for name, tag in sorted(scene_drops.items()):
        e = lookup(name, overrides=overrides)
        for p in e["placements"]:
            if p["file"] not in levels:
                levels[p["file"]] = {str(a.get("Hash")): a for a in byml_load(new.read(p["file"]))[0]["Actors"]}
            dyn = (levels[p["file"]].get(str(p["hash"])) or {}).get("Dynamic") or {}
            if dyn.get("Drop__DropActor") != DISGUISE_ACTOR or dyn.get(DROP_TAG_KEY) != float(tag):
                bad.append(f"{name} ({p['hash']}): drops {dyn.get('Drop__DropActor')} with tag "
                           f"{dyn.get(DROP_TAG_KEY)}, expected {DISGUISE_ACTOR} with {tag}")

    def table_row(pk, table, key):
        files = sarc_files(new.read(pk))
        if table not in files:
            return None
        rows = byml_load(files[table])[0].get("BlackboardParamF32Array") or []
        return next((r for r in rows if r.get("BBKey") == key), None)
    for pk in packpaths.carriers(DROP_TABLE, romfs):
        r = table_row(pk, DROP_TABLE, DROP_TAG_KEY)
        if r is None or not r.get("IsInstanceParam"):
            bad.append(f"{pk}: the Drop table has no instance F32 {DROP_TAG_KEY}")
    for pk in packpaths.carriers(CARRIER_TABLE, romfs):
        if table_row(pk, CARRIER_TABLE, PICKUP_TAG_KEY) is None:
            bad.append(f"{pk}: {CARRIER_TABLE} has no F32 {PICKUP_TAG_KEY}")

    def props(a, i):
        return {e["name"]: e["value"] for t in ainb.PTYPES for e in a.nodes[i]["properties"][t]}

    def gets(a, i, key):
        return (i >= 0 and a.nodes[i]["name"] == "QueryBlackboardGetF32" and props(a, i).get("BlackboardType") == 1
                and props(a, i).get("BlackboardKey") == key)
    kinds = set(droppers) if droppers is not None else set(PICKUP_SAVE_DROPPERS) | {"Enemy_Skulltula_Gold"}
    where = {dropper_ai(a) for a in kinds}
    for pk, ai_file in sorted(where):
        a = ainb.Ainb(sarc_files(new.read(pk))[ai_file])
        drops_ = [i for i, n in enumerate(a.nodes) if n["name"] == "OneShotDropSetOverWriteParam"]
        ok = False
        for d in drops_:
            src = a._input(d, "OverwriteParam")[1]["node"]
            while src >= 0 and a.nodes[src]["name"] == "QueryBlackboardOverwriteParamAddS32":  # the respawn model's
                src = a._input(src, "OverwriteParam")[1]["node"]                               # bit, after the tag
            if src >= 0 and a.nodes[src]["name"] == "QueryBlackboardOverwriteParamAddF32" and \
                    props(a, src).get("Key") == PICKUP_TAG_KEY and gets(a, a._input(src, "F32")[1]["node"], DROP_TAG_KEY):
                ok = True
        if not ok:
            bad.append(f"{pk} {ai_file}: its drop doesn't get the placement's {DROP_TAG_KEY}")
    if tag_looks:
        ai_file = _root_ai(DISGUISE_ACTOR, romfs)
        a = ainb.Ainb(sarc_files(new.read(DISGUISE_PACK))[ai_file])
        got = {}
        for i, n in enumerate(a.nodes):
            if n["name"] != "QueryMathEqualF32":
                continue
            ins = {e["name"]: e for e in n["inputs"]["float"]}
            if not gets(a, ins["F32"]["node"], PICKUP_TAG_KEY) or ins["S32Base"]["value"] == 0:
                continue
            sel = next((j for j, m in enumerate(a.nodes) if m["type"] == 7 and m["inputs"]["bool"]
                        and m["inputs"]["bool"][0]["node"] == i), None)
            if sel is None:
                continue
            true = next(pl["node"] for pl in a.nodes[sel]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True")
            shows, todo, seen = set(), [true], set()
            while todo:
                j = todo.pop()
                if j in seen:
                    continue
                seen.add(j)
                m = a.nodes[j]
                leaf = _look_leaf(a, m)
                if leaf:
                    shows.add(leaf)
                todo += [pl["node"] for pl in m["plugs"][ainb.PLUG_CHILD]]
            got[str(int(ins["S32Base"]["value"]))] = sorted(shows)
        want = {str(t): sorted(v) for t, v in tag_looks.items()}
        if got != want:
            bad.append(f"{ai_file}: tag looks {got}, expected {want}")
    for scene in HOOK_SCENES:
        ev = evfl.Evfl(new.read(scene))
        cases = {c["value"] for fc in ev.flowcharts for e in fc["events"] if e["name"] == HOOK_SWITCH
                 for c in e.get("cases") or []}
        missing = sorted(set(scene_drops.values()) - cases)
        if missing:
            bad.append(f"{scene}: the tag switch has no case for {missing}")
    return bad


def pickup_save_ops(droppers, pickups, romfs=DEFAULT_ROMFS, tags=False, gates=()):
    """make_patch sections for the checked-on-pickup pipeline, {"ainb": [...], "packs": [...], "byml": [...]}, for the
    dropper types `droppers` (PICKUP_SAVE_DROPPERS keys, or "Enemy_Skulltula_Gold") and pickup types `pickups`.
    Every file is edited the same way in every pack holding its path ("pack": "*"; tools/packpaths.py). That's a
    dropper's root AI (Obj_Pot.root is in 21 packs, so every type running it gets the branch), the pickups' blackboard
    tables (the DropItem table is in 34 packs, so elsewhere it's an unused u64 key) and Ruto's letter AI (also the
    letter Link holds).
    `tags` (scene drops): every dropper also hands its DROP_TAG_KEY to its drop (_tag_step), the Drop table (195 packs)
    declares it, and the carrier's and the pickups' tables get PICKUP_TAG_KEY.
    `gates` (dropper types with flagless drops): a tree's root AI also gets _tree_edits and the Drop table declares
    DROP_FLAG_KEY.
    The respawn model: every dropper hands its DROP_CHK_KEY on (_chk_hand) and sets it on break when DROP_SAVE_KEY says
    so, and every pickup (and Obj_Heart_Piece.root) sets the bit it received when taken. Breaks keep saving
    (vanilla)."""
    from romtools import Romfs, sarc_files
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    gs = {"pack": GS_PACK, "file": GS_AI}
    out = {"ainb": [], "packs": [], "byml": []}
    if any(FLAGLESS_DROPPERS.get(g, (None,))[0] == "tree" for g in gates):  # trees read their flag's name
        out["ainb"].append({"pack": "*", "bb_params": [{"table": DROP_TABLE, "type": "String", "key": DROP_FLAG_KEY,
                                                        "init": "", "instance": True}]})
    if tags:
        out["ainb"] += [
            {"pack": "*", "bb_params": [{"table": DROP_TABLE, "type": "F32", "key": DROP_TAG_KEY, "init": 0,
                                         "instance": True}]},
            {"pack": "*", "bb_params": [{"table": CARRIER_TABLE, "type": "F32", "key": PICKUP_TAG_KEY, "init": 0}]}]
    # trees too, their drop chain hands DROP_CHK_KEY on and their bit gate reads it (_tree_edits, Flagless pickups)
    if any(a != "Enemy_Skulltula_Gold" for a in droppers):
        # the respawn model, with the placement's bit and save-on-break switch, and the heart pieces' table and death
        # branch
        out["ainb"].append({"pack": "*", "bb_params": [
            {"table": DROP_TABLE, "type": "Bool", "key": DROP_SAVE_KEY, "init": False, "instance": True},
            {"table": DROP_TABLE, "type": "S32", "key": DROP_CHK_KEY, "init": 0, "instance": True}]})
        out["ainb"].append({"pack": "*", "bb_params": [{"table": CARRIER_TABLE, "type": "S32", "key": PICKUP_CHK_KEY,
                                                        "init": 0}]})
        out["ainb"].append({"pack": "*", "file": HP_AI, "edits": hp_chk_edits()})
        # the token too (it saves its dropper's flag already, through GoldTokenGmdHash)
        out["ainb"].append({"pack": "*", "bb_params": [{"table": TOKEN_TABLE, "type": "S32", "key": PICKUP_CHK_KEY,
                                                        "init": 0}]})
        out["ainb"].append({"pack": "*", "file": TOKEN_AI, "edits": token_chk_edits()})
        out["ainb"] += spawn_save_ops(pickups, romfs)  # drops recording on break save the twin's row as they appear
        out["_sets_checked"] = True  # the setters write CHECKED_ARRAY, plan_ops makes sure it exists
    done_ai = set()
    for actor in sorted(droppers):
        if actor == "Enemy_Skulltula_Gold":  # its own chain gets the second key between the add and the drop node
            out["ainb"].append({"pack": "*", "file": GS_AI, "edits": [
                {"copy": {"from": gs, "nodes": ["QueryBlackboardOverwriteParamAddNoRespawnGmdHash"], "label": "r",
                          "follow": False}},
                {"set_property": {"node": "r:1", "name": "Key", "value": "RespawnGmdHash"}},
                {"link": {"from": "QueryBlackboardOverwriteParamAddNoRespawnGmdHash", "output": "OverwriteParam",
                          "to": "r:1", "input": "OverwriteParam"}}] + (
                _tag_step("r:1", "OneShotDropSetOverWriteParam") if tags else
                [{"link": {"from": "r:1", "output": "OverwriteParam", "to": "OneShotDropSetOverWriteParam",
                           "input": "OverwriteParam"}}])})
            continue
        kind, base = FLAGLESS_DROPPERS.get(actor, (None, actor))
        if kind == "tree":  # its own drop chain and gate
            ai_file = TREE_AI[actor]
            if ai_file not in done_ai:
                done_ai.add(ai_file)
                out["ainb"].append({"pack": "*", "file": ai_file,
                                    "edits": _tree_edits(fs, f"Pack/Actor/{actor}.pack.zs", ai_file)})
            continue
        ai_file = _dropper_root(base)
        pack = f"Pack/Actor/{base}.pack.zs"
        if ai_file not in done_ai:  # one edit per AI file, whichever dropper types share it
            done_ai.add(ai_file)
            a = ainb.Ainb(dropper_ai_bytes(fs, base))
            if base in NEW_AI_DROPPERS:  # an AI of its own first, its pack only ("*" finds vanilla holders)
                for k, v in new_ai_ops([base], romfs).items():
                    out[k] += v
            root = a.nodes[next(c for c in a.commands if c["name"] == "Root")["main"]]
            edits = [] if root["type"] == 3 else [{"wrap": {"command": "Root"}}]
            edits += [
                {"copy": {"from": gs, "nodes": ["OneShotDropSetOverWriteParam"], "label": "d"}},  # Make, Add, Drop
                {"copy": {"from": gs, "nodes": ["QueryBlackboardOverwriteParamAddNoRespawnGmdHash"], "label": "r",
                          "follow": False}},
                {"set_property": {"node": "r:1", "name": "Key", "value": "RespawnGmdHash"}},
                {"link": {"from": "d:1", "output": "OverwriteParam", "to": "r:1", "input": "OverwriteParam"}}]
            chk, cadd = _chk_hand("chd")  # the respawn model, the placement's checked bit goes with the drop
            edits += chk
            edits += _tag_step("r:1", cadd) if tags else [
                {"link": {"from": "r:1", "output": "OverwriteParam", "to": cadd, "input": "OverwriteParam"}}]
            edits += [{"link": {"from": cadd, "output": "OverwriteParam", "to": "d:2", "input": "OverwriteParam"}},
                      {"add_child": dict({"parent": "@Root", "child": "d:2"},
                                         **({"first": True} if ai_file in HANDOVER_FIRST else {}))}]
            edits += save_on_break_edits()  # objects whose drop can't record them, the break sets the bit
            out["ainb"].append({"pack": new_ai_packs(base) if base in NEW_AI_DROPPERS else "*", "file": ai_file,
                                "edits": edits})
        # breaks keep saving as in vanilla (the respawn model), so no death-table edits
    hp = {"pack": HP_PACK, "file": HP_AI}
    # IsDead -> case 10 (LifeDepleted, the get scene's request) or case 4 (PickedUp, collected directly) -> save +
    # signal. The heart piece's own branch only knows 10, since its pickup always goes through the get scene.
    branch = [{"copy": {"from": hp, "nodes": ["BoolSelector"], "label": "t"}},
              {"add_child": {"parent": "t:2", "child": "t:6", "case": DEATH_PICKED_UP}},
              {"add_child": {"parent": "@Root", "child": "t:3"}}]
    done_ai, done_tables = set(), set()
    for actor in sorted(pickups):
        if actor in SAVES_ALREADY or actor not in PICKUP_SAVERS:
            continue
        ai_file, table = PICKUP_SAVERS[actor]
        pack = f"Pack/Actor/{actor}.pack.zs"
        if table not in done_tables:
            done_tables.add(table)
            out["ainb"].append({"pack": "*", "bb_params": [{"table": table, "type": "U64", "key": "RespawnGmdHash",
                                                            "init": 0}] + (
                [{"table": table, "type": "F32", "key": PICKUP_TAG_KEY, "init": 0}] if tags else []) + [
                {"table": table, "type": "S32", "key": PICKUP_CHK_KEY, "init": 0}]})
        where = (pack, ai_file) if ai_file is not None else (AI_GLOBAL, "AI/DropItem.root.ainb")
        if where[1] not in done_ai:  # its own AI, or AI.Global's DropItem.root.ainb that the others share
            done_ai.add(where[1])
            # the respawn model, taking it sets its dropper's visit bit and then its checked bit (VISIT)
            out["ainb"].append({"pack": "*", "file": where[1], "edits": _wrap_if_needed(fs, *where) + branch
                                + _chk_pair("pc", PICKUP_CHK_KEY, "t:6")})
    # every type running an edited pickup AI has the keys it reads, whether or not this seed drops that type
    # (Obj_Dungeon_SmallKey runs AI.Global's DropItem.root with a table of its own)
    for actor, (ai_file, table) in sorted(PICKUP_SAVERS.items()):
        if (ai_file or "AI/DropItem.root.ainb") in done_ai and table not in done_tables:
            done_tables.add(table)
            out["ainb"].append({"pack": "*", "bb_params": [{"table": table, "type": "U64", "key": "RespawnGmdHash",
                                                            "init": 0}] + (
                [{"table": table, "type": "F32", "key": PICKUP_TAG_KEY, "init": 0}] if tags else []) + [
                {"table": table, "type": "S32", "key": PICKUP_CHK_KEY, "init": 0}]})
    return {k: v for k, v in out.items() if v}


# Any item through the get scene (heart spots)
# Node sources for the instance-name check (every one a vanilla node of the same shape):
#  QueryGetActorInstanceName  the stray dogs' event AI (it compares the dog's instance name, its placement Name
#                             'Stray_Brown_01'..., with QueryStringIsEqual: the same check)
#  QueryStringIsEqual         NpcGoron.root's (StringA fed by a node, StringB a constant: flags 0x800000)
#  BoolSelector, ExecuteEventSetQueryValue   the tag query's own first selector and its answer (same file)
GS_NAME_SRC = {"pack": "Pack/Actor/Animal_Dog_Base.pack.zs", "file": "AI/Animal_Dog.event.root.ainb"}
GS_EQUAL_SRC = {"pack": AI_GLOBAL, "file": "AI/NpcGoron.root.ainb"}


def _name_sources(fs):
    """The instance-name check's node sources: the dogs' QueryGetActorInstanceName and NpcGoron.root's
    QueryStringIsEqual with StringA fed and StringB a constant."""
    from romtools import sarc_files
    import ainb
    dog = ainb.Ainb(sarc_files(fs.read(GS_NAME_SRC["pack"]))[GS_NAME_SRC["file"]])
    gor = ainb.Ainb(sarc_files(fs.read(GS_EQUAL_SRC["pack"]))[GS_EQUAL_SRC["file"]])
    eq_i = next(i for i, n in enumerate(gor.nodes) if n["name"] == "QueryStringIsEqual"
                and [(e["name"], e["node"] >= 0, e["flags"]) for e in n["inputs"]["string"]]
                == [("StringA", True, 0), ("StringB", False, 0x800000)])
    return dog.node("QueryGetActorInstanceName"), eq_i


def _get_scene_sources(fs, pack, ai_file=None):
    """(dog name-query index, goron string-compare index, the tag command's node, its vanilla Execute child (a
    BoolSelector), that selector's True answer (an ExecuteEventSetQueryValue)), all read from the vanilla files."""
    from romtools import sarc_files
    import ainb
    name_i, eq_i = _name_sources(fs)
    a = ainb.Ainb(sarc_files(fs.read(pack))[ai_file or GET_SCENE_AI])
    cmd = next(c for c in a.commands if c["name"] == GET_SCENE_QUERY)["main"]
    (sel,) = [pl["node"] for pl in a.nodes[cmd]["plugs"][ainb.PLUG_CHILD]]
    if ainb.NODE_TYPES.get(a.nodes[sel]["type"]) != "BoolSelector":
        raise DropPlanError(f"{pack}: {GET_SCENE_QUERY} no longer starts at a BoolSelector")
    val = next(pl["node"] for pl in a.nodes[sel]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True")
    if a.nodes[val]["name"] != "ExecuteEventSetQueryValue":
        raise DropPlanError(f"{pack}: {GET_SCENE_QUERY}'s first answer is not ExecuteEventSetQueryValue")
    return name_i, eq_i, cmd, sel, val


def _fall_by_ai(fallthrough):
    """{pack: tag} (the disguise carrier's pack) -> {event AI file: [(actor type, tag)]}."""
    out = defaultdict(list)
    for pack, tag in sorted((fallthrough or {}).items()):
        out[GET_SCENE_AI].append((pack.rsplit("/", 1)[-1].replace(".pack.zs", ""), tag))
    return out


def _carrier(inner, romfs):
    """A pack holding `inner` (every one holds the same vanilla bytes): where node sources are read."""
    import packpaths
    found = packpaths.carriers(inner, romfs)
    if not found:
        raise DropPlanError(f"no pack holds {inner}")
    return found[0]


def get_scene_ops(entries, romfs=DEFAULT_ROMFS, actor_keys=None, fallthrough=None, drop_tags=()):
    """make_patch sections that let the get scene tell these heart spots apart (drop_map entries with "get_scene").
    Each placement gets its Name, the instance name. A spot with "as" also becomes that heart type, with the Dynamic
    keys that type doesn't accept removed (actor_keys, drop_map's). The pickups' event AI answers
    EventQueryCheckTagOnPouchActor by first comparing the actor's instance name with every such name of the seed
    (QueryGetActorInstanceName -> QueryStringIsEqual -> BoolSelector, chained through the False cases) and answering the
    spot's tag, or its "value". A spot named only so the fallthrough below skips it answers the vanilla 4.
    `drop_tags` (scene drops) then compare the carrier's PICKUP_TAG_KEY with each tag and answer it (GET_SCENE_AI).
    `fallthrough` ({pack: tag}, the disguised ice trap's carrier) then compares the actor's own type
    (QueryGenericGetOwnActorLink -> QueryGenericGetActorName ActorFileName) and answers that tag for every other actor
    of that type. Anything else reaches the vanilla answer (the old first selector).
    There's one edit per event AI file ("ai" in "get_scene": GET_SCENE_AI, or the small key's KEY_AI), written the same
    into every pack holding it ("pack": "*"). Its path is shared by several pickup types (5 heart packs; 15 key, rupee
    and recovery-heart packs) and can't differ between them (tools/packpaths.py)."""
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    place, by_ai = [], defaultdict(list)
    for e in entries:
        gs = e["get_scene"]
        for p in e["placements"]:
            op = {"file": p["file"], "hash": p["hash"], "set": {"Name": gs["name"]}}
            if gs.get("as") and p["actor"] != gs["as"]:
                op["set"]["Gyaml"] = gs["as"]
                accepts = set((actor_keys or _map()["actor_keys"]).get(gs["as"], []))
                drop = [f"Dynamic.{k}" for k in p.get("dynamic_keys", []) if k not in accepts]
                if drop:
                    op["remove"] = drop
            place.append(op)
        by_ai[gs.get("ai") or GET_SCENE_AI].append(gs)
    fall = _fall_by_ai(fallthrough)
    for ai_file in fall:
        by_ai.setdefault(ai_file, [])
    if drop_tags:
        by_ai.setdefault(GET_SCENE_AI, [])
    out = {"placements": place, "ainb": []}
    for ai_file, spots in sorted(by_ai.items()):
        pack = _carrier(ai_file, romfs)
        name_i, eq_i, cmd, sel, val = _get_scene_sources(fs, pack, ai_file)
        own = {"pack": pack, "file": ai_file}
        edits = [{"copy": {"from": GS_NAME_SRC, "nodes": [name_i], "label": "name", "follow": False}}] if spots else []
        spots = sorted(spots, key=lambda s: s["tag"])
        if len({s["name"] for s in spots}) != len(spots):
            raise DropPlanError(f"{ai_file}: two get-scene spots share a name")
        for s in spots:
            t, q, b, v = s["tag"], f"eq{s['tag']}:{eq_i}", f"sel{s['tag']}:{sel}", f"val{s['tag']}:{val}"
            edits += [
                {"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": f"eq{t}", "follow": False}},
                {"set_input": {"node": q, "name": "StringB", "value": s["name"]}},
                {"feed": {"from": f"name:{name_i}", "output": "InstanceName", "to": q, "input": "StringA"}},
                {"copy": {"from": own, "nodes": [sel], "label": f"sel{t}", "follow": False}},
                {"feed": {"from": q, "output": "IsEqual", "to": b, "input": "Input"}},
                {"copy": {"from": own, "nodes": [val], "label": f"val{t}", "follow": False}},
                {"set_input": {"node": v, "name": "Value", "value": s.get("value", t)}},
                {"set_input": {"node": v, "name": "Label", "value": s["name"]}},
                {"add_child": {"parent": b, "child": v, "name": "True"}}]
        chain = [f"sel{s['tag']}:{sel}" for s in spots]
        if drop_tags and ai_file == GET_SCENE_AI:  # scene drops: the tag the carrier got from its dropper
            more, get = _tag_get("dget", PICKUP_TAG_KEY)
            edits += more
            esrc, enodes = TAG_SRC["equal"]
            qi = enodes["QueryMathEqualF32"]
            for t in sorted(set(drop_tags)):
                q, b, v = f"deq{t}:{qi}", f"dsel{t}:{sel}", f"dval{t}:{val}"
                edits += [
                    {"copy": {"from": esrc, "nodes": [qi], "label": f"deq{t}", "follow": False}},
                    {"set_input": {"node": q, "name": "S32Base", "value": float(t)}},
                    {"feed": {"from": get, "output": "F32", "to": q, "input": "F32"}},
                    {"copy": {"from": own, "nodes": [sel], "label": f"dsel{t}", "follow": False}},
                    {"feed": {"from": q, "output": "Bool", "to": b, "input": "Input"}},
                    {"copy": {"from": own, "nodes": [val], "label": f"dval{t}", "follow": False}},
                    {"set_input": {"node": v, "name": "Value", "value": t}},
                    {"set_input": {"node": v, "name": "Label", "value": f"{GET_SCENE_NAME}Drop{t}"}},
                    {"add_child": {"parent": b, "child": v, "name": "True"}}]
                chain.append(b)
        types = fall.get(ai_file, [])
        if types:  # the disguise carrier, where the actor's own type decides (one QueryGenericGetActorName for all)
            own_i, an_i = _actor_name_sources(fs)
            edits += [{"copy": {"from": GS_NAME_SRC, "nodes": [own_i], "label": "self", "follow": False}},
                      {"copy": {"from": GS_NAME_SRC, "nodes": [an_i], "label": "type", "follow": False}},
                      {"link": {"from": f"self:{own_i}", "output": "Actor", "to": f"type:{an_i}", "input": "Actor"}}]
            for actor, t in types:
                q, b, v = f"teq{t}:{eq_i}", f"tsel{t}:{sel}", f"tval{t}:{val}"
                edits += [
                    {"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": f"teq{t}", "follow": False}},
                    {"set_input": {"node": q, "name": "StringB", "value": actor}},
                    {"feed": {"from": f"type:{an_i}", "output": "ActorFileName", "to": q, "input": "StringA"}},
                    {"copy": {"from": own, "nodes": [sel], "label": f"tsel{t}", "follow": False}},
                    {"feed": {"from": q, "output": "IsEqual", "to": b, "input": "Input"}},
                    {"copy": {"from": own, "nodes": [val], "label": f"tval{t}", "follow": False}},
                    {"set_input": {"node": v, "name": "Value", "value": t}},
                    {"set_input": {"node": v, "name": "Label", "value": f"{GET_SCENE_NAME}Disguise"}},
                    {"add_child": {"parent": b, "child": v, "name": "True"}}]
                chain.append(b)
        for a, nxt in zip(chain, chain[1:] + [None]):
            edits.append({"add_child": {"parent": a, "name": "False", "child": nxt or sel}})
        edits.append({"set_child": {"parent": f"@{GET_SCENE_QUERY}", "which": "Execute",
                                    "child": chain[0] if chain else sel}})
        out["ainb"].append({"pack": "*", "file": ai_file, "edits": edits})
    return out


# The Lake Hylia hook (parity/_songs_trade_lake.py) gives LH Underwater Item's and LH Sun's items when the picked actor
# answers the get scene's tag query with 0 or 1. Vanilla AI/PouchContent.event.root.ainb (AI.Global, the pouch event AI
# of Obj_Item_Base's pickups) answers by actor tag, 0 for every LetterBottle (Obj_Bottle_Letter) and 1 for every
# Obj_Fire_Arrow (Obj_Arrow_Fire). So a Ruto's Letter or Fire Arrows pickup anywhere else got taken for the lake spot,
# hidden, with the lake's item given instead (tools/gamedb item audit, IG-*-pickup-tag).
# LAKE_GUARD keeps those two answers for the lake's own placements only, told apart by instance name, and every other
# letter or arrow answers GET_SCENE_VANILLA_ANSWER (the plain get, like a chest gives them). That also keeps their
# vanilla lake scenes away from other spots. StoneOfWater_GetRutoletter sets Get_StoneOfWater_GetRutoLetter and
# GetFireArrow completes SubEvent_GetFireArrow, and each deletes its lake placement
# (HyruleField_LakeHylia_Child_Prefab_9e98 / _Adult_Prefab_5313), which would lose the lake spot's own item.
# The edit sits inside the two tag branches, so the chains other features put in front of the tag query (extras_npcs'
# fish names) keep working.
LAKE_AI = "AI/PouchContent.event.root.ainb"
LAKE_ACTORS = ("Obj_Bottle_Letter", "Obj_Arrow_Fire")
# (the branch's actor tag, the lake placement's instance name, the placement to name), where None means it's already
# named that. The LH Sun arrow is named "Item" in vanilla (Dm_LakeHrl_0030's flowchart actor finds it by that name), and
# it's the only placement with that name in the game. The letter's placement has no name and gets RandoLakeLetter.
LAKE_GUARD = (("LetterBottle", "RandoLakeLetter",
               {"file": "Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs", "hash": "474136620438465634"}),
              ("Obj_Fire_Arrow", "Item", None))
# Lake pickups
# The letter bottle used to lie at the bottom of Lake Hylia even when the spot gave Arrows (5). So the two lake pickups
# show the item they give, like every other shuffled pickup does (look_ops, by the placement's instance name), and a
# vanilla item keeps the vanilla look. The letter's event AI (LAKE_AI) is the one most pickups run, so its hide step
# only deletes the display for these names (GATED_HIDE), and every other actor goes on to the vanilla step itself. The
# Fire Arrows pickup is taken by touch (touch_attention_ops: AutoPickUpItem, the moat Ocarina of Time's setup, with the
# same DropItem table and root AI). The underwater bottle keeps its own underwater grab (PickUpItem_InWaterBottle).
LAKE_LOOK = {"LH Underwater Item": {"actor": "Obj_Bottle_Letter", "name": "RandoLakeLetter", "set_name": True,
                                    "file": "Banc/HyruleField/HyruleField_Child_Static.bcett.byml.zs",
                                    "hash": "474136620438465634", "pos": [-151.62, 124.97, 461.04]},
             "LH Sun": {"actor": "Obj_Arrow_Fire", "name": "Item", "set_name": False,
                        "file": "Banc/HyruleField/HyruleField_Adult_Static.bcett.byml.zs",
                        "hash": "4598657944866228526", "pos": [-158.13, 131.46, 523.36]}}
LAKE_VANILLA = {"LH Underwater Item": "Rutos Letter", "LH Sun": "Fire Arrows"}
GATED_HIDE = {LAKE_AI}


# Logic-deleted objects
# The Goron City wall crack (Obj_Goron_BrokenRock_A_01, child "Goron City Boulder 20" and adult "Goron City Boulder 21",
# one spot) is run by a logic module, Gimmick_GoronCity_BrokenRock_4403 (the child level's own AiGroup, the adult's
# through GoronCity_Adult_Prefab_44ad). Node 4 sets GoronCity_LostWood_WallCrack_Broke when the rock (node 7) dies, and
# node 7's Logic_Delete reads that flag (node 5), so from the next load the rock is deleted whatever its own row says.
# On the respawn model the rock's row came back at the map change, but the flag deleted it, so an item left behind was
# lost with it. The other age's rock, never broken, got deleted too, and its item was never reachable.
# Here the delete reads an expression instead: broken AND the current age's rock checked (its RandoChecked bit). So a
# rock whose item is still there comes back with it until it's taken, like every respawn-model boulder. The flag itself
# and everything else reading it (the Lost Woods shortcut's entrance sets, the Goron's lines) stay vanilla. Once broken
# the shortcut is open, and the rock standing again over it while its item is untaken can be broken again from either
# side.
# The Hyrule Field open grotto's crate ("HF Open Grotto Crate 1", adult Obj_BrokenBox_A_01 #14654205574115276454).
# HyruleField_Adult_Level_Prefab_c022 node 7 deletes it once a child has killed the grotto's Skullwalltula
# (HaveReadHrlField_Note12_Enemy, set by the child level's HyruleField_Child_Level_Prefab_29fc), and node 1 then creates
# the Gold Skulltula's box (Obj_BrokenBox_A_06 #4392858802949544986, same spot, a RespawnFlagSyncLink to the crate) in
# its place, so a crate item left there was lost. Here the crate only goes once the flag is set and its item is taken,
# and the box only takes its place then ("create_nodes": their Logic_Create reads the same expression), so one crate
# stands there at a time, as in vanilla. Nothing else reads the flag differently.
LOGIC_DELETE = {"Logic/Gimmick_GoronCity_BrokenRock_4403.logic.module.ainb": {
    "flag": "GoronCity_LostWood_WallCrack_Broke", "actor_node": 7, "flag_node": 5, "exp": "RandoGCWallCrack_Gone",
    "spots": {"child": "8438942300162055419", "adult": "8668774813841012997"}},
    "Logic/HyruleField_Adult_Level_Prefab_c022.logic.module.ainb": {
    "flag": "HaveReadHrlField_Note12_Enemy", "actor_node": 7, "flag_node": 6, "exp": "RandoHFGrottoCrate_Gone",
    "spots": {"adult": "14654205574115276454"}, "create_nodes": [1]},
    # Hyrule Field Tree 7 (child Obj_Tree_A_02 #9860797772243961676) is a flagless dropper, so its item's record is a
    # borrowed flag (_drops_flag_spots). HyruleField_Child_Prefab_f06d node 2 sets HrlField_IsGetRupeeFromTree when it's
    # shaken, and from the next load node 4 (OperateAND, UpdateOnce, read once per load) deletes it and creates Tree 5
    # (#11354987278416404894, same spot), so an item shaken out and left was lost. Here node 4 reads the expression
    # ("gate"), flag AND the tree's item taken, still once per load, so the swap keeps vanilla's timing.
    "Logic/HyruleField_Child_Prefab_f06d.logic.module.ainb": {
    "flag": "HrlField_IsGetRupeeFromTree", "actor_node": 0, "flag_node": 3, "exp": "RandoHFTree7_Gone",
    "spots": {"child": "9860797772243961676"}, "gate": [4, "BoolMulti"]}}
LOGIC_DELETE_SRC = ({"file": "Logic/GanonCastle_Level_Field_00_Prefab_14ba.logic.module.ainb"}, 3)  # a vanilla
# HoldGameDataGetBoolExpSimple (GameDataNameBoolExp), the BoolExp reader logic modules use


def logic_delete_ops(respawn_rec, borrowed=None):
    """{"ainb", "boolexp", "record"} for the LOGIC_DELETE modules whose objects are respawn-model spots (their
    RandoChecked bit) or flagless drops holding an item (`borrowed`: {placement hash: its borrowed flag}), or {}."""
    bit_of = {str(pl["hash"]): rec["bit"] for rec in respawn_rec.values() for pl in rec["placements"]}
    borrowed = borrowed or {}
    ainb_ops, exps, record = [], {}, {}
    for module, g in sorted(LOGIC_DELETE.items()):
        bits = {age: bit_of.get(h) for age, h in g["spots"].items()}
        flags = {age: borrowed.get(h) for age, h in g["spots"].items() if bits.get(age) is None}
        if not any(b is not None for b in bits.values()) and not any(flags.values()):
            continue
        # gone = flag AND NOT(OR(child AND NOT checked_child, adult AND NOT checked_adult))
        # An age without a respawn spot keeps the vanilla rule, so it gets no term.
        rpn, terms = [[0, g["flag"]]], 0
        for age, b in sorted(bits.items()):
            if b is None and not flags.get(age):
                continue
            rpn += [[0, "Sequence_IsChildhood"]] + ([] if age == "child" else [[5]])
            rpn += [[8, CHECKED_ARRAY, b] if b is not None else [0, flags[age]], [5], [3]]
            terms += 1
            if terms > 1:
                rpn.append([4])
        rpn += [[5], [3]]
        exps[g["exp"]] = rpn
        src, node = LOGIC_DELETE_SRC
        copy = {"copy": {"from": src, "nodes": [node], "label": "gone", "follow": False,
                         "values": {str(node): {"GameDataNameBoolExp": g["exp"]}}}}
        if g.get("gate"):  # the module's own once-per-load gate reads it (its deletes and creates follow)
            feeds = [{"feed": {"from": f"gone:{node}", "output": "Bool", "to": g["gate"][0], "input": g["gate"][1]}}]
        else:
            feeds = [{"feed": {"from": f"gone:{node}", "output": "Bool", "to": g["actor_node"], "input": "Logic_Delete"}}]
            feeds += [{"feed": {"from": f"gone:{node}", "output": "Bool", "to": c, "input": "Logic_Create"}}
                      for c in g.get("create_nodes", ())]
        ainb_ops.append({"file": module, "edits": [copy] + feeds})
        record[module] = {"exp": g["exp"], "flag": g["flag"], "bits": bits, "actor_node": g["actor_node"],
                          **({"create_nodes": list(g["create_nodes"])} if g.get("create_nodes") else {}),
                          **({"borrowed": {a: f for a, f in flags.items() if f}} if any(flags.values()) else {}),
                          **({"gate": list(g["gate"])} if g.get("gate") else {})}
    return {"ainb": ainb_ops, "boolexp": exps, "record": record} if ainb_ops else {}


def verify_logic_delete(patch_dir, plan, romfs=DEFAULT_ROMFS):
    """Returns [problem]. Every LOGIC_DELETE module of the plan has to delete its object by the plan's expression, which
    is the vanilla flag AND each respawn age's checked bit (the rock comes back while its item is there). What takes its
    place ("create_nodes") has to be created by the same expression, and the expression's steps have to be the
    plan's."""
    import ainb
    from romtools import Romfs
    rec = plan.get("_drops_logic_delete") or {}
    spots = {str(pl["hash"]) for r in ((plan.get("_drops_respawn") or {}).get("spots") or {}).values()
             for pl in r["placements"]}
    spots |= {str(p["hash"]) for n in (plan.get("_drops_flag_spots") or {})  # flagless drops holding an item
              for p in (lookup(n, _map(), None) or {}).get("placements", [])}
    spots |= {str(p["hash"]) for r in (plan.get("_drops_flagless_own") or {}).values()  # (Flagless pickups)
              for p in r["placements"]}
    bad = []
    for module, g in LOGIC_DELETE.items():
        if set(g["spots"].values()) & spots and module not in rec:
            bad.append(f"{module}: its object holds an item (respawn model or a borrowed flag) but its flag still "
                       f"deletes it")
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    from romtools import byml_load, murmur3_32
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]["Data"]
    exp_rows = {int(e["Hash"]) for e in gd.get("BoolExp") or []}
    for module, r in rec.items():
        if murmur3_32(r["exp"]) not in exp_rows:
            bad.append(f"{module}: GameDataList has no BoolExp {r['exp']}")
        a = ainb.Ainb(fs.raw(module))
        reads = [tuple(r["gate"])] if r.get("gate") else \
            [(r["actor_node"], "Logic_Delete")] + [(c, "Logic_Create") for c in r.get("create_nodes", ())]
        for node, inp in reads:
            e = next((x for x in a.nodes[node]["inputs"]["bool"] if x["name"] == inp), None)
            src = a.nodes[e["node"]] if e and e["node"] >= 0 else None
            name = [x["value"] for x in (src or {}).get("inputs", {}).get("string", [])
                    if x["name"] == "GameDataNameBoolExp"]
            if src is None or src["name"] != "HoldGameDataGetBoolExpSimple" or name != [r["exp"]]:
                bad.append(f"{module}: node {node}'s {inp} isn't read from {r['exp']}")
        gds = plan.get("gamedata")
        steps = {}
        for gd_op in (gds if isinstance(gds, list) else [gds or {}]):
            steps.update((gd_op or {}).get("add_boolexp") or {})
        if r["exp"] in steps:  # the expression reads the flag and each age's checked bit (RandoChecked)
            flat = [tuple(s) for s in steps[r["exp"]]]
            if (0, r["flag"]) not in flat or any((8, CHECKED_ARRAY, b) not in flat
                                                  for b in r["bits"].values() if b is not None) or \
                    any((0, f) not in flat for f in (r.get("borrowed") or {}).values()):
                bad.append(f"{module}: {r['exp']} = {steps[r['exp']]} doesn't read {r['flag']} and the checked bits "
                           f"{r['bits']}")
    return bad


def heart_touch_ops(actor, romfs=DEFAULT_ROMFS):
    """make_patch "packs" ops that make `actor` a touch pickup (HEART_TOUCH_TYPES, with its ActorParam in several
    packs). Every pack holding its ActorParam gets the touch attention, its clients and a RandoTouch blackboard
    (_touch_ops), and its ActorParam names them in all of them."""
    import packpaths
    from romtools import Romfs, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    ap = f"Actor/{actor}.engine__actor__ActorParam.bgyml"
    src = sarc_files(fs.read(FALL_SRC))
    ops, sets = [], None
    for pack in sorted(packpaths.carriers(ap, romfs)):
        files = sarc_files(fs.read(pack))
        o, s = _touch_ops(fs, pack, files, _components(files, actor), actor, src)
        if sets not in (None, s):
            raise DropPlanError(f"heart touch: {actor}'s blackboard differs between its packs")
        ops, sets = ops + o, s
    if sets is None:
        raise DropPlanError(f"heart touch: no pack holds {ap}")
    return ops + [{"pack": "*", "file": ap, "set": sets}]


def touch_attention_ops(actor, romfs=DEFAULT_ROMFS):
    """make_patch "packs" ops that make `actor` (its ActorParam only in its own pack) a touch pickup. AutoPickUpItem and
    its two clients are copied unchanged from FALL_SRC, and its blackboard has to hold TOUCH_KEY already (the DropItem
    table, like the moat's Obj_Ocarina_Time, whose setup this is)."""
    import packpaths
    from romtools import Romfs, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    ap = f"Actor/{actor}.engine__actor__ActorParam.bgyml"
    packs = list(packpaths.carriers(ap, romfs))
    if packs != [f"Pack/Actor/{actor}.pack.zs"]:
        raise DropPlanError(f"touch: {ap} is held by {packs}, not its own pack alone")
    files = sarc_files(fs.read(packs[0]))
    if TOUCH_TABLE_SRC not in files:
        raise DropPlanError(f"touch: {actor} has no {TOUCH_TABLE_SRC} (its {TOUCH_KEY})")
    auto, asets = _autoget_ops(packs[0], files, _components(files, actor), actor)
    return ([{"pack": packs[0], "file": f, "from_pack": FALL_SRC} for f in (TOUCH_ATTENTION,) + TOUCH_CLIENTS] + auto
            + [{"pack": "*", "file": ap, "set": {"Components.AttentionSenderRef": "?" + TOUCH_ATTENTION, **asets}}])


def _gated_hide_problems(old, cur, names, ev):
    """[problem] for event AI `ev` (vanilla `old`, patched `cur`). The vanilla hide step and its whole subtree have to
    be as vanilla, each name of `names` runs it with the display delete, and any other actor reaches exactly that
    step."""
    import ainb
    out = []
    vcmd = next(c for c in old.commands if c["name"] == LOOK_HIDE_COMMAND)["main"]
    (vstep,) = [pl["node"] for pl in old.nodes[vcmd]["plugs"][ainb.PLUG_CHILD]]
    todo, seen = [vstep], set()
    while todo:  # the vanilla hide step's whole subtree, node for node
        i = todo.pop()
        if i in seen:
            continue
        seen.add(i)
        if ainb.describe_node(old, i) != ainb.describe_node(cur, i):
            out.append(f"{ev}: vanilla node {i} under {LOOK_HIDE_COMMAND} changed")
        todo += [pl["node"] for pl in old.nodes[i]["plugs"][ainb.PLUG_CHILD]]
    cmd = next(c for c in cur.commands if c["name"] == LOOK_HIDE_COMMAND)["main"]
    (j,) = [pl["node"] for pl in cur.nodes[cmd]["plugs"][ainb.PLUG_CHILD]]
    tested, steps = [], 0
    while j != vstep and steps < 10:  # a chain of name tests whose False goes on, ending at the vanilla step
        steps += 1
        n = cur.nodes[j]
        if ainb.NODE_TYPES.get(n["type"]) != "BoolSelector" or not n["inputs"]["bool"]:
            out.append(f"{ev}: {LOOK_HIDE_COMMAND} reaches node {j} ({n['name']}) before the vanilla step for "
                       f"other pickups")
            break
        q = n["inputs"]["bool"][0]["node"]
        qi = {e["name"]: e for e in cur.nodes[q]["inputs"]["string"]} if q >= 0 else {}
        src = qi.get("StringA", {}).get("node", -1)
        if q < 0 or cur.nodes[q]["name"] != "QueryStringIsEqual" or src < 0 or \
                cur.nodes[src]["name"] != "QueryGetActorInstanceName":
            out.append(f"{ev}: the hide step's selector {j} doesn't test the instance name")
            break
        tested.append(qi["StringB"]["value"])
        kids = {pl["name"]: pl["node"] for pl in n["plugs"][ainb.PLUG_CHILD]}
        sim = kids.get("True", -1)
        under = [pl["node"] for pl in cur.nodes[sim]["plugs"][ainb.PLUG_CHILD]] if sim >= 0 else []
        if vstep not in under or not any(cur.nodes[u]["name"] == "OneShotActorHolderRequestDelete" for u in under):
            out.append(f"{ev}: the name {tested[-1]!r} doesn't run the vanilla step and the display delete")
        j = kids.get("False", -1)
    if j != vstep:
        out.append(f"{ev}: other pickups don't reach the vanilla hide step")
    elif sorted(tested) != sorted(names):
        out.append(f"{ev}: the hide step tests {sorted(tested)}, not the lake looks {sorted(names)}")
    return out


def verify_lake_looks(patch_dir, lake, romfs=DEFAULT_ROMFS):
    """Reads a built patch back (Lake pickups) and returns [problem] for plan "_drops_looks_lake" ({name: {"carrier",
    "shows", "location"}}). Their displays get read back by verify_looks with the plan's other looks.
    The letter's placement carries its name, LH Sun's arrow is taken by touch, and in every GATED_HIDE event AI the
    vanilla hide step and every node under it are as vanilla. An actor whose instance name is none of the spots' reaches
    exactly that vanilla step (the other pickups' path)."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    import packpaths
    bad = []  # the looks themselves are verify_looks, with every other look of the plan (in_game_check)
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    for name, v in lake.items():
        spec = LAKE_LOOK[v["location"]]
        a = next((x for x in byml_load(new.read(spec["file"]))[0]["Actors"] if str(x.get("Hash")) == spec["hash"]), {})
        if a.get("Name") != name:
            bad.append(f"{v['location']}: its placement is named {a.get('Name')!r}, not {name!r}")
        if v["location"] == "LH Sun":
            files = sarc_files(new.read(f"Pack/Actor/{spec['actor']}.pack.zs"))
            if _components(files, spec["actor"]).get("AttentionSenderRef") != "?" + TOUCH_ATTENTION or \
                    TOUCH_ATTENTION not in files:
                bad.append(f"{spec['actor']}: not taken by touch (AttentionSenderRef)")
    names = set(lake)
    for ev in sorted(GATED_HIDE):
        pk = packpaths.carriers(ev, romfs)[0]
        old, cur = ainb.Ainb(sarc_files(van.read(pk))[ev]), ainb.Ainb(sarc_files(new.read(pk))[ev])
        bad += _gated_hide_problems(old, cur, names, ev)
    return bad


def verify_type_looks(patch_dir, types, romfs=DEFAULT_ROMFS):
    """Reads type looks and the ammo turn back and returns [problem]. `types` is plan "_drops_looks_types" ({type:
    {"turn", "owners"}}).
    - Each type's patched pack has its own Drop component (DropRef TURN_DROP's DropParam, its blackboard table under its
      own path) that drops the turn actor at 100 %, vanilla-shaped (resolve_drop).
    - The turn actor's take adds a Blue Rupee (its pouch content is a bundle of 5 Obj_Rupee_Green) and records the spot
      (its DropActorRespawnData table declares PICKUP_CHK_KEY, which DropItem.root's take branch reads).
    - The patched LOOK_TYPE_AI compares the pickup's own type name with it (QueryGenericGetActorName ->
      QueryStringIsEqual -> BoolSelector). Under that selector it asks for each container owner
      (QueryGetPouchContentNumByActorName) and stores LOOK_KEEP (the container owned). With none owned it turns, in this
      order: it hides itself, saves its dropper's rows (OneShotHeartPieceTakenDeadAfter), hands the drop its checked bit
      (OneShotDropSetOverWriteParam fed by QueryBlackboardOverwriteParamAddS32 PICKUP_CHK_KEY, fed by the pickup's own
      PICKUP_CHK_KEY), drops (OneShotDropDrop) and deletes itself with no fade (OneShotGenericDeleteThisActor). A type
      whose no-container branch doesn't turn is reported as a take that adds no rupee."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    import packpaths
    bad = []
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    turns = sorted({v.get("turn") or AMMO_RUPEE for v in types.values()})
    for r in turns:
        try:
            files = sarc_files(new.read(f"Pack/Actor/{r}.pack.zs"))
        except (FileNotFoundError, OSError):
            bad.append(f"{r}: no pack (the turn's drop)")
            continue
        pc = _pouch_content(files, _components(files, r).get("PouchContentRef"))
        if not (pc.get("IsBundle") and (pc.get("BundleActor") or "").endswith("/Obj_Rupee_Green.engine__actor__"
                                                                              "ActorParam.gyml")
                and pc.get("BundleActorNum") == 5 and pc.get("DefaultAutoGet")):
            bad.append(f"{r}: its take doesn't add 5 rupees by touch ({pc.get('BundleActor')} x {pc.get('BundleActorNum')})")
        table = (PICKUP_SAVERS.get(r) or (None, CARRIER_TABLE))[1]  # (a rupee's: its DropItem table)
        tab = byml_load(files[table])[0] if table in files else {}
        keys = [e.get("BBKey") for k, arr in tab.items() if k.startswith("BlackboardParam") and isinstance(arr, list)
                for e in arr if isinstance(e, dict)]
        if PICKUP_CHK_KEY not in keys:
            bad.append(f"{r}: its {table.split('/')[-1]} has no {PICKUP_CHK_KEY}: its take wouldn't record the spot")
    for t, v in sorted(types.items()):
        r = v.get("turn") or AMMO_RUPEE
        try:
            files = sarc_files(new.read(f"Pack/Actor/{t}.pack.zs"))
        except (FileNotFoundError, OSError):
            bad.append(f"{t}: no pack")
            continue
        dp = files.get(TURN_DROP[0])
        if _components(files, t).get("DropRef") != "?" + TURN_DROP[0] or dp is None:
            bad.append(f"{t}: with no container, taking it adds no rupee: no Drop component of its own to turn into {r}")
            continue
        if byml_load(dp)[0].get("BlackboardTableRef") != _work(TURN_DROP[1]) or TURN_DROP[1] not in files:
            bad.append(f"{t}: its DropParam's blackboard table isn't its own ({TURN_DROP[1]})")
        got, chance, how, shape = resolve_drop(files, t, r)
        if chance != 100 or shape or not how.startswith("named by"):
            bad.append(f"{t}: its drop gives {r} at {chance} % ({how}; {shape or 'shape ok'})")
    a = ainb.Ainb(sarc_files(new.read(packpaths.carriers(LOOK_TYPE_AI, romfs)[0]))[LOOK_TYPE_AI])

    def consts(i, kind):
        return {e["name"]: e.get("value") for e in (a.nodes[i].get("inputs") or {}).get(kind, [])
                if e.get("node", -1) < 0}

    def props(i):
        return {e["name"]: e["value"] for t_ in ainb.PTYPES for e in a.nodes[i]["properties"][t_]}

    def kids(i):
        return [pl["node"] for pl in a.nodes[i]["plugs"][ainb.PLUG_CHILD]]

    def feeder(i, kind, name):
        e = next((e for e in a.nodes[i]["inputs"][kind] if e["name"] == name), None)
        return e["node"] if e and e.get("node", -1) >= 0 else -1

    def under(i):
        seen, todo = [], [i]
        while todo:
            j = todo.pop()
            if j < 0 or j in seen:
                continue
            seen.append(j)
            todo += kids(j)
        return seen
    sel_of = {}
    for i, n in enumerate(a.nodes):
        if ainb.NODE_TYPES.get(n["type"]) == "BoolSelector" and n["inputs"]["bool"]:
            sel_of.setdefault(n["inputs"]["bool"][0].get("node", -1), i)
    found = {}
    for i, n in enumerate(a.nodes):
        if n["name"] != "QueryStringIsEqual" or feeder(i, "string", "StringA") < 0 \
                or a.nodes[feeder(i, "string", "StringA")]["name"] != "QueryGenericGetActorName" or i not in sel_of:
            continue
        yes = next((pl["node"] for pl in a.nodes[sel_of[i]]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True"), -1)
        found[consts(i, "string").get("StringB")] = under(yes)
    for t, v in sorted(types.items()):
        sub = found.get(t)
        if sub is None:
            bad.append(f"{LOOK_TYPE_AI}: no check of the pickup's own type for {t}")
            continue
        names = [a.nodes[j]["name"] for j in sub]
        counted = set()  # owned(): count -> QueryMathLessS32 -> the BoolSelector's Input
        for j in sub:
            f = feeder(j, "bool", "Input") if ainb.NODE_TYPES.get(a.nodes[j]["type"]) == "BoolSelector" else -1
            g = feeder(f, "int", "S32Base") if f >= 0 and a.nodes[f]["name"] == "QueryMathLessS32" else -1
            if g >= 0 and a.nodes[g]["name"] == "QueryGetPouchContentNumByActorName":
                counted.add(consts(g, "string").get("ActorName"))
        if set(v["owners"]) - counted:
            bad.append(f"{LOOK_TYPE_AI}: {t}'s check doesn't ask for {sorted(set(v['owners']) - counted)}")
        if not any(a.nodes[j]["name"] == "ExecuteBlackboardSetString" and consts(j, "string").get("String") == LOOK_KEEP
                   for j in sub):
            bad.append(f"{LOOK_TYPE_AI}: {t} with its container never keeps its own look ({LOOK_KEEP})")
        if not any(a.nodes[j]["name"] == "OneShotDropSetDropValid" and consts(j, "bool").get("IsValid") is False
                   for j in sub):
            bad.append(f"{LOOK_TYPE_AI}: {t} with its container doesn't switch its turn's drop off (a burned or "
                       f"exploded pickup would drop {r})")
        seqs = [j for j in sub if ainb.NODE_TYPES.get(a.nodes[j]["type"]) == "Sequential"]
        want = ["OneShotSetModelVisible", "OneShotHeartPieceTakenDeadAfter", "OneShotDropSetOverWriteParam",
                "OneShotDropDrop", "OneShotGenericDeleteThisActor"]
        turn = [j for j in seqs if [a.nodes[c]["name"] for c in kids(j)] == want]
        if not turn:
            bad.append(f"{LOOK_TYPE_AI}: {t} with no container, taking it adds no rupee (no turn into {r}: "
                       f"{'no drop' if 'OneShotDropDrop' not in names else 'its steps are not ' + str(want)})")
            continue
        steps = kids(turn[0])
        if consts(steps[0], "bool").get("Bool") is not False:
            bad.append(f"{LOOK_TYPE_AI}: {t}'s turn doesn't hide the pickup first")
        if props(steps[4]).get("IsFade") is not False:
            bad.append(f"{LOOK_TYPE_AI}: {t}'s turn fades the pickup out instead of removing it at once")
        add = feeder(steps[2], "ptr", "OverwriteParam")
        mk = feeder(add, "ptr", "OverwriteParam") if add >= 0 else -1
        get = feeder(add, "int", "S32") if add >= 0 else -1
        if not (add >= 0 and a.nodes[add]["name"] == "QueryBlackboardOverwriteParamAddS32"
                and props(add).get("Key") == PICKUP_CHK_KEY and mk >= 0
                and a.nodes[mk]["name"] == "QueryGenericMakeOverwriteParam" and get >= 0
                and a.nodes[get]["name"] == "QueryBlackboardGetS32" and props(get).get("BlackboardKey") == PICKUP_CHK_KEY
                and props(get).get("BlackboardType") == 1):
            bad.append(f"{LOOK_TYPE_AI}: {t}'s turn doesn't hand the drop its checked bit ({PICKUP_CHK_KEY})")
    return bad


def lake_branches(a):
    """{actor tag: (its BoolSelector, the selector's True answer)} of a PouchContent event AI's tag query."""
    import ainb
    out = {}
    for i, n in enumerate(a.nodes):
        if ainb.NODE_TYPES.get(n["type"]) != "BoolSelector":
            continue
        src = [e for e in n["inputs"]["bool"] if e["name"] == "Input" and e["node"] >= 0]
        if not src or a.nodes[src[0]["node"]]["name"] != "QueryActorIsTagOn":
            continue
        tag = next((e["value"] for e in a.nodes[src[0]["node"]]["inputs"]["string"] if e["name"] == "TagName"), None)
        val = next((pl["node"] for pl in n["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True"), None)
        if tag is not None and val is not None:
            out[tag] = (i, val)
    return out


def lake_guard_ops(romfs=DEFAULT_ROMFS):
    """make_patch sections for LAKE_GUARD. That's the letter placement's Name, and the two tag branches of LAKE_AI
    asking the picked actor's instance name first (QueryGetActorInstanceName -> QueryStringIsEqual -> BoolSelector).
    True goes to the vanilla answer node, and False to a copy answering GET_SCENE_VANILLA_ANSWER."""
    from romtools import Romfs, sarc_files
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    pack = _carrier(LAKE_AI, romfs)
    a = ainb.Ainb(sarc_files(fs.read(pack))[LAKE_AI])
    branches = lake_branches(a)
    name_i, eq_i = _name_sources(fs)
    own = {"pack": pack, "file": LAKE_AI}
    edits = [{"copy": {"from": GS_NAME_SRC, "nodes": [name_i], "label": "lakename", "follow": False}}]
    place = []
    for k, (tag, name, placement) in enumerate(LAKE_GUARD):
        if tag not in branches:
            raise DropPlanError(f"{pack}:{LAKE_AI}: no {tag} branch in {GET_SCENE_QUERY}")
        sel, val = branches[tag]
        q, b, v = f"lakeeq{k}:{eq_i}", f"lakesel{k}:{sel}", f"lakeval{k}:{val}"
        edits += [
            {"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": f"lakeeq{k}", "follow": False}},
            {"set_input": {"node": q, "name": "StringB", "value": name}},
            {"feed": {"from": f"lakename:{name_i}", "output": "InstanceName", "to": q, "input": "StringA"}},
            {"copy": {"from": own, "nodes": [sel], "label": f"lakesel{k}", "follow": False}},
            {"feed": {"from": q, "output": "IsEqual", "to": b, "input": "Input"}},
            {"copy": {"from": own, "nodes": [val], "label": f"lakeval{k}", "follow": False}},
            {"set_input": {"node": v, "name": "Value", "value": GET_SCENE_VANILLA_ANSWER}},
            {"set_input": {"node": v, "name": "Label", "value": f"RandoLakeOther{tag}"}},
            {"add_child": {"parent": b, "child": val, "name": "True"}},
            {"add_child": {"parent": b, "child": v, "name": "False"}},
            {"set_child": {"parent": sel, "which": "True", "child": b}}]
        if placement:
            place.append(dict(placement, set={"Name": name}))
    return {"placements": place, "ainb": [{"pack": "*", "file": LAKE_AI, "edits": edits}]}


def _lake_check(new, sel, val):
    """(instance name tested, answer if equal, answer otherwise) when `sel`'s True case is LAKE_GUARD's name check
    that ends at `val` on True, else None."""
    import ainb
    kids = {pl["name"]: pl["node"] for pl in new.nodes[sel]["plugs"][ainb.PLUG_CHILD]}
    b = kids.get("True")
    if b is None or b == val or ainb.NODE_TYPES.get(new.nodes[b]["type"]) != "BoolSelector":
        return None
    bk = {pl["name"]: pl["node"] for pl in new.nodes[b]["plugs"][ainb.PLUG_CHILD]}
    src = [e for e in new.nodes[b]["inputs"]["bool"] if e["name"] == "Input" and e["node"] >= 0]
    if bk.get("True") != val or "False" not in bk or not src:
        return None
    q = new.nodes[src[0]["node"]]
    ins = {e["name"]: e for e in q["inputs"]["string"]}
    if q["name"] != "QueryStringIsEqual" or ins.get("StringA", {}).get("node", -1) < 0:
        return None
    if new.nodes[ins["StringA"]["node"]]["name"] != "QueryGetActorInstanceName":
        return None
    answer = {i: next((e["value"] for e in new.nodes[i]["inputs"]["int"] if e["name"] == "Value"), None)
              for i in (val, bk["False"])}
    return ins["StringB"]["value"], answer[val], answer[bk["False"]]


def lake_guard_nodes(old, new):
    """The vanilla LAKE_AI selectors LAKE_GUARD re-points (True case -> its name check), where it did."""
    out = []
    for tag, _name, _p in LAKE_GUARD:
        sel, val = lake_branches(old).get(tag, (None, None))
        if sel is not None and _lake_check(new, sel, val) is not None:
            out.append(sel)
    return out


def verify_lake_guard(patch_dir, romfs=DEFAULT_ROMFS):
    """Reads LAKE_GUARD back from a built patch and returns [problem, ...]. In every pack holding LAKE_AI (one version),
    each lake tag's branch answers its vanilla tag only for the lake placement's instance name and
    GET_SCENE_VANILLA_ANSWER otherwise, and the letter placement carries its name. tools/gamedb item audit checks that
    no other placement has either name."""
    from romtools import Romfs, byml_load, sarc_files
    import ainb
    import packpaths
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch_dir])
    problems = []
    packs = packpaths.carriers(LAKE_AI, romfs)
    copies = {pk: sarc_files(out.read(pk))[LAKE_AI] for pk in packs}
    if len(set(copies.values())) != 1:
        problems.append(f"{LAKE_AI}: not the same in every pack holding it")
    old = ainb.Ainb(sarc_files(fs.read(packs[0]))[LAKE_AI])
    new = ainb.Ainb(copies[packs[0]])
    vanilla = lake_branches(old)
    for tag, name, placement in LAKE_GUARD:
        sel, val = vanilla[tag]
        got = _lake_check(new, sel, val)
        want_v = next(e["value"] for e in old.nodes[val]["inputs"]["int"] if e["name"] == "Value")
        if got != (name, want_v, GET_SCENE_VANILLA_ANSWER):
            problems.append(f"{LAKE_AI}: the {tag} branch is {got}, expected answer {want_v} only for {name!r} and "
                            f"{GET_SCENE_VANILLA_ANSWER} otherwise")
        if placement:
            a = next((x for x in byml_load(out.read(placement["file"]))[0]["Actors"]
                      if str(x.get("Hash")) == placement["hash"]), None)
            if a is None or a.get("Name") != name:
                problems.append(f"{placement['file']} {placement['hash']}: Name {a and a.get('Name')!r}, expected {name}")
    problems += [f"{LAKE_AI}: {p}" for p in new.input_shape_problems()]
    return problems


def lake_guard_needed(plan_part):
    """True if a plan part places a lake-tagged pickup (LAKE_ACTORS) anywhere: a drop, a type swap, a placed actor."""
    import json as _json
    s = _json.dumps({k: plan_part.get(k) for k in ("placements", "byml", "binary") if plan_part.get(k)})
    return any(f'"{a}"' in s for a in LAKE_ACTORS)


# The disguised trap's real ice attack
# A scene can't freeze or hurt Link. No scene action does, negative HealLife does nothing, and Link's conditions reset
# while he's in a scene. The remake's own ice-trap chest (Obj_TBox_A_04) freezes him with an attack: an attack sensor
# "Atk" (rigid body sensor "Body", layer AttackAll, a capsule of radius 1 m around the actor, contact rule
# HitToCharacter), a SensorHit component, and its AttackParam (power 2 = half a heart, ice element; AtSensors =
# murmur3("Body")). ExecuteSensorHitSetupAttack switches it on beside a counter (its AI node 3) once the chest is out of
# its own event (nodes 29/30/28). The disguise carrier gets copies of those (its own physics and parameter table, so the
# heart pieces sharing its files keep theirs).
# The attack runs while the carrier is alive, like the chest's does. No vanilla AI attacks from a death case (all 99 AI
# files with ExecuteSensorHitSetupAttack attack on the not-dead side), and attacking from the PickedUp death case did
# nothing in game. So the get scene's disguise branch doesn't request the death. It hides the carrier, turns its
# attention off (no second pickup), and calls TRAP_SPRING on it. That's a pickup event command no vanilla event uses,
# made to set the carrier's own blackboard key TRAP_KEY, the way the cucco's EventTriggerSetWasAppearInEvent does it
# (ExecuteBlackboardSetBool, actor blackboard). The key lives in a table only the carrier lists (its own
# BlackboardInfo).
# The heart pieces' shared root AI reads it (QueryBlackboardGetBoolNoError, since the other heart pieces don't have it).
# It turns attention off and hides again, waits until the carrier is out of the event, waits, attacks, then requests its
# death itself (DeathReason 10, LifeDepleted: the vanilla death case saves the heart-piece flag of its dropper and runs
# the death procedure). The chest's breath effect (TBox_FreezeBreath) is the chest's alone, and Link's own frozen
# condition shows instead.
TRAP_SRC = {"pack": "Pack/Actor/Obj_TBox_A_04.pack.zs", "file": "AI/Obj_TBox_A_04.root.ainb"}
TRAP_NODES = {"Sequential": 10, "ExecuteGenericCounterByPlug": 25, "Simultaneous": 3,
              "ExecuteGenericBoolForceResult": 29}  # 3: the attack window (counter 4 + ExecuteSensorHitSetupAttack
#   5); 29: success once its own event is over (QueryInvertBool 30 of QueryEventMemberIsEventMemberSomeReason 28)
TRAP_WAIT_FRAMES = 20.0  # after the carrier left the get scene's event, before the attack window
TRAP_FILES = ("Phive/ContactCollectionSensorParam/HitToCharacter.phive__ContactCollectionSensorParam.bgyml",
              "Phive/RigidBodyControllerSensorParam/Obj_TBox_A_04_Atk.phive__RigidBodyControllerSensorParam.bgyml",
              "Phive/RigidBodySensorParam/Obj_TBox_A_04_Atk.phive__RigidBodySensorParam.bgyml",
              "Phive/ShapeParam/Obj_TBox_A_04__Atk.phive__ShapeParam.bgyml",
              "Component/SensorHitParam/Default_IgnoreHookShot.game__component__SensorHitParam.bgyml",
              "GameBalance/AttackParam/Obj_TBox_A_04.game__gamebalance__AttackParam.bgyml")
TRAP_SET_NAME = "RandoIceTrap"
TRAP_KEY = "RandoIceTrapSprung"
# the get scene's step that springs the trap. It's a command of the pickups' event AI (GET_SCENE_AI) that no vanilla
# event calls (checked over all 915 event files), with its Execute child replaced by the key's setter.
TRAP_SPRING = {"actor": "PouchContentGuestPerformer", "action": "EventTriggerSetFootStepRayLength",
               "params": {"RayLength": 0.0}}
TRAP_ATTENTION_OFF = {"actor": "PouchContentGuestPerformer", "action": "EventTriggerAttentionOffClientAll",
                      "params": {}}
TRAP_KEY_SET_SRC = ({"pack": "Pack/Actor/Animal_Cucco.pack.zs", "file": "AI/Animal_Cucco.event.root.ainb"},
                    {"Simultaneous": 61, "ExecuteBlackboardSetBool": 59})  # the EventTriggerSetWasAppearInEvent nodes
TRAP_KEY_GET_SRC = ({"pack": "Pack/Actor/Animal_Frog_Base.pack.zs", "file": "AI/Animal_Frog.event.root.ainb"},
                    {"QueryBlackboardGetBoolNoError": 663})
TRAP_EVENT_NODES = {"OneShotAttentionSenderChangeValid": 12, "OneShotDeathRequestDeath": 177}  # in GET_SCENE_AI
# Wait for Link's main event to end. The carrier is just a guest performer, so its own wait can pass right away.
# With only the carrier's wait, the heart got hidden and the attack never hit Link.
TRAP_MAIN_EVENT_SRC = ({"pack": "Pack/Actor/Animal_Cucco.pack.zs", "file": "AI/_LocalModule_3d9c9aeef30d.module.ainb"},
                       {"QueryIsPlayingMainEvent": 48})
_W = "Work/"


def _check_src(fs, src, nodes, what):
    """Checks the source AI file still has each named node at its index (index: name)."""
    from romtools import sarc_files
    import ainb
    a = ainb.Ainb(sarc_files(fs.read(src["pack"]))[src["file"]])
    for name, i in nodes.items():
        if i >= len(a.nodes) or (a.nodes[i]["name"] != name and ainb.NODE_TYPES.get(a.nodes[i]["type"]) != name):
            raise DropPlanError(f"{src['file']}: node {i} is no longer {name} ({what})")
    return a


def disguise_attack_ops(m, romfs=DEFAULT_ROMFS):
    """Builds the disguise carrier's ice attack (see TRAP_SRC) as {"packs", "ainb"}. `m` is the drop map."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    pack, carrier = DISGUISE_PACK, DISGUISE_ACTOR
    trap_pack = TRAP_SRC["pack"]
    tf = sarc_files(fs.read(trap_pack))
    cf = sarc_files(fs.read(pack))
    chest = _check_src(fs, TRAP_SRC, TRAP_NODES, "the trap chest's attack")
    if [chest.nodes[pl["node"]]["name"] for pl in chest.nodes[3]["plugs"][ainb.PLUG_CHILD]] != \
            ["ExecuteGenericCounterByPlug", "ExecuteSensorHitSetupAttack"]:
        raise DropPlanError(f"{TRAP_SRC['file']}: node 3 is no longer the attack window")
    w = chest.nodes[TRAP_NODES["ExecuteGenericBoolForceResult"]]["inputs"]["bool"][0]["node"]
    if chest.nodes[w]["name"] != "QueryInvertBool" or \
            chest.nodes[chest.nodes[w]["inputs"]["bool"][0]["node"]]["name"] != "QueryEventMemberIsEventMemberSomeReason":
        raise DropPlanError(f"{TRAP_SRC['file']}: node 29 no longer waits for the chest's event to end")
    setter = _check_src(fs, *TRAP_KEY_SET_SRC, "the key's setter")
    getter = _check_src(fs, *TRAP_KEY_GET_SRC, "the key's reader")
    for a, i in ((setter, 59), (getter, 663)):
        if [e["value"] for e in a.nodes[i]["properties"]["int"] if e["name"] == "BlackboardType"] != [1]:
            raise DropPlanError(f"node {i} of a blackboard key source no longer uses the actor blackboard")
    if 59 not in [pl["node"] for pl in setter.nodes[61]["plugs"][ainb.PLUG_CHILD]]:  # Also contains an AS setter.
        raise DropPlanError(f"{TRAP_KEY_SET_SRC[0]['file']}: node 61 no longer holds the key's setter")
    ev = _check_src(fs, {"pack": pack, "file": GET_SCENE_AI}, TRAP_EVENT_NODES, "the pickups' event steps")
    _check_src(fs, *TRAP_MAIN_EVENT_SRC, "the main-event query")
    if not any(c["name"] == TRAP_SPRING["action"] for c in ev.commands):
        raise DropPlanError(f"{GET_SCENE_AI}: no command {TRAP_SPRING['action']}")
    # Copies of the carrier's physics, parameter table and blackboard, with the chest's attack and the key added
    phys_src = "Component/Physics/HeartPiece.engine__component__PhysicsParam.bgyml"
    set_src = "Phive/ControllerSetParam/HeartPiece.phive__ControllerSetParam.bgyml"
    gpt_src = "GameParameter/GameParameterTable/Obj_Heart_Piece.engine__actor__GameParameterTable.bgyml"
    bbi_src = "Component/Blackboard/BlackboardInfo/Obj_Heart_Piece.engine__component__BlackboardInfo.bgyml"
    bbt_src = "Component/Blackboard/BlackboardParamTable/Capture.engine__component__BlackboardParamTable.bgyml"
    for f in (phys_src, set_src, gpt_src, bbi_src, bbt_src):
        if f not in cf:
            raise DropPlanError(f"{pack}: no {f}")
    chest_set = byml_load(tf["Phive/ControllerSetParam/Obj_TBox_A_04.phive__ControllerSetParam.bgyml"])[0]
    own_set = byml_load(cf[set_src])[0]

    def pick(key, name, path_part):
        hit = [e for e in chest_set[key] if e["Name"] == name and path_part in e["FilePath"]]
        if len(hit) != 1:
            raise DropPlanError(f"Obj_TBox_A_04 controller set: no single {key} {name} ({path_part})")
        return dict(hit[0])
    adds = {"CColSensorNamePathAry": pick("CColSensorNamePathAry", "Atk", "HitToCharacter"),
            "ControllerSensorNamePathAry": pick("ControllerSensorNamePathAry", "Atk", "Obj_TBox_A_04_Atk"),
            "RigidBodySensorNamePathAry": pick("RigidBodySensorNamePathAry", "Body", "Obj_TBox_A_04_Atk"),
            "ShapeNamePathAry": pick("ShapeNamePathAry", "Body_Atk", "Obj_TBox_A_04__Atk")}
    set_vals = {}
    for key, entry in adds.items():
        rows = [dict(e) for e in own_set.get(key, [])]
        if any(e["Name"] == entry["Name"] for e in rows):
            raise DropPlanError(f"{set_src}: {key} already has a {entry['Name']}")
        set_vals[key] = rows + [entry]
    new_set = f"Phive/ControllerSetParam/{TRAP_SET_NAME}.phive__ControllerSetParam.bgyml"
    new_phys = f"Component/Physics/{TRAP_SET_NAME}.engine__component__PhysicsParam.bgyml"
    new_gpt = f"GameParameter/GameParameterTable/{TRAP_SET_NAME}.engine__actor__GameParameterTable.bgyml"
    new_bbi = f"Component/Blackboard/BlackboardInfo/{TRAP_SET_NAME}.engine__component__BlackboardInfo.bgyml"
    new_bbt = f"Component/Blackboard/BlackboardParamTable/{TRAP_SET_NAME}.engine__component__BlackboardParamTable.bgyml"
    tables = list(byml_load(cf[bbi_src])[0]["BlackboardParamTables"])
    attack = "?" + TRAP_FILES[5]
    packs = [{"pack": pack, "file": f, "from_pack": trap_pack} for f in TRAP_FILES]
    packs += [
        {"pack": pack, "file": new_set, "new_from": set_src, "set": set_vals},
        {"pack": pack, "file": new_phys, "new_from": phys_src,
         "set": {"ControllerSetPath": _W + new_set.replace(".bgyml", ".gyml")}},
        {"pack": pack, "file": new_gpt, "new_from": gpt_src, "set": {"Components.gamebalance_AttackParam": attack}},
        {"pack": pack, "file": new_bbt, "new_from": bbt_src,
         "set": {"BlackboardParamBoolArray": [{"BBKey": TRAP_KEY, "InitVal": False, "IsInstanceParam": False,
                                                "IsRecord": False, "IsSafeParamForExternalTools": False}]}},
        {"pack": pack, "file": new_bbi, "new_from": bbi_src,
         "set": {"BlackboardParamTables": tables + [_W + new_bbt.replace(".bgyml", ".gyml")]}},
        {"pack": pack, "file": f"Actor/{carrier}.engine__actor__ActorParam.bgyml",
         "set": {"Components.PhysicsRef": "?" + new_phys, "Components.SensorHitRef": "?" + TRAP_FILES[4],
                 "Components.GameParameterTableRef": "?" + new_gpt, "Components.BlackboardRef": "?" + new_bbi}}]
    # In the pickups' event AI the TRAP_SPRING command sets the key. On any other pickup it would find no key.
    kset_src, kset = TRAP_KEY_SET_SRC
    ks, kb = f"ksim:{kset['Simultaneous']}", f"kset:{kset['ExecuteBlackboardSetBool']}"
    spring = [
        {"copy": {"from": kset_src, "nodes": [kset["Simultaneous"]], "label": "ksim", "follow": False}},
        {"copy": {"from": kset_src, "nodes": [kset["ExecuteBlackboardSetBool"]], "label": "kset", "follow": False}},
        {"set_property": {"node": kb, "name": "BlackboardKey", "value": TRAP_KEY}},
        {"set_property": {"node": kb, "name": "IsIgnoreNotExistsError", "value": True}},
        {"add_child": {"parent": ks, "child": kb}},
        {"set_child": {"parent": f"@{TRAP_SPRING['action']}", "which": "Execute", "child": ks}}]
    # The heart pieces share this root AI. It gets one more always-on branch, for a carrier whose key is set.
    own = {"pack": pack, "file": HP_AI}
    evs = {"pack": pack, "file": GET_SCENE_AI}
    hp = ainb.Ainb(cf[HP_AI])
    root = next(c["main"] for c in hp.commands if c["name"] == "Root")
    if ainb.NODE_TYPES.get(hp.nodes[root]["type"]) != "Simultaneous":
        raise DropPlanError(f"{HP_AI}: the Root command no longer starts at a Simultaneous")
    bsel = next(i for i, n in enumerate(hp.nodes) if ainb.NODE_TYPES.get(n["type"]) == "BoolSelector")
    dummy = hp.node("ExecuteGenericDummyAction")
    hide_src, hide_i = LOOK_SRC["hide"][0], LOOK_SRC["hide"][1]["OneShotSetModelVisible"]
    kget_src, kget = TRAP_KEY_GET_SRC
    N, E = TRAP_NODES, TRAP_EVENT_NODES
    win_counter = chest.nodes[N["Simultaneous"]]["plugs"][ainb.PLUG_CHILD][0]["node"]
    win_frames = _bb_init_value(chest, tf, win_counter, "BaseFrameTime")  # the chest's AttackFrame (60)
    q = f"tkey:{kget['QueryBlackboardGetBoolNoError']}"
    e = [
        {"copy": {"from": kget_src, "nodes": [kget["QueryBlackboardGetBoolNoError"]], "label": "tkey",
                  "follow": False}},
        {"set_property": {"node": q, "name": "BlackboardKey", "value": TRAP_KEY}},
        {"copy": {"from": own, "nodes": [bsel], "label": "tsel", "follow": False}},
        {"feed": {"from": q, "output": "Bool", "to": f"tsel:{bsel}", "input": "Input"}},
        {"copy": {"from": own, "nodes": [dummy], "label": "tidle", "follow": False}},
        {"copy": {"from": own, "nodes": [dummy], "label": "thold", "follow": False}},
        {"copy": {"from": TRAP_SRC, "nodes": [N["Sequential"]], "label": "tseq", "follow": False}},
        {"copy": {"from": evs, "nodes": [E["OneShotAttentionSenderChangeValid"]], "label": "toff", "follow": False}},
        {"set_input": {"node": f"toff:{E['OneShotAttentionSenderChangeValid']}", "name": "Bool", "value": False}},
        {"copy": {"from": hide_src, "nodes": [hide_i], "label": "thide", "follow": False}},
        {"set_input": {"node": f"thide:{hide_i}", "name": "Bool", "value": False}},
        # Out of the get scene. This is the chest's wait (ExecuteGenericBoolForceResult on an inverted query), but
        # fed by QueryIsPlayingMainEvent instead of the chest's query (QueryEventMemberIsEventMemberSomeReason on
        # itself). The carrier is the scene's guest performer and nothing releases it, since it doesn't die in the
        # scene. A diagnostic build showed that wait never ends.
        {"copy": {"from": TRAP_SRC, "nodes": [N["ExecuteGenericBoolForceResult"]], "label": "tmw", "follow": False}},
        {"copy": {"from": TRAP_SRC, "nodes": [w], "label": "tmi", "follow": False}},
        {"copy": {"from": TRAP_MAIN_EVENT_SRC[0], "nodes": [TRAP_MAIN_EVENT_SRC[1]["QueryIsPlayingMainEvent"]],
                  "label": "tmq", "follow": False}},
        {"feed": {"from": f"tmq:{TRAP_MAIN_EVENT_SRC[1]['QueryIsPlayingMainEvent']}", "output": "IsPlayingMainEvent",
                  "to": f"tmi:{w}", "input": "Bool"}},
        {"feed": {"from": f"tmi:{w}", "output": "Bool", "to": f"tmw:{N['ExecuteGenericBoolForceResult']}",
                  "input": "Bool"}},
        # Both timers get literal BaseFrameTime values here. The chest's blackboard flags (0x8000000N) point to a board
        # the heart pieces don't have, and that null read crashed the game.
        {"copy": {"from": TRAP_SRC, "nodes": [N["ExecuteGenericCounterByPlug"]], "label": "twait", "follow": False,
                  "values": {str(N["ExecuteGenericCounterByPlug"]): {"BaseFrameTime": TRAP_WAIT_FRAMES}}}},
        {"copy": {"from": TRAP_SRC, "nodes": [N["Simultaneous"]], "label": "twin",  # with its two children
                  "values": {str(win_counter): {"BaseFrameTime": win_frames}}}},
        {"copy": {"from": evs, "nodes": [E["OneShotDeathRequestDeath"]], "label": "tdie", "follow": False}},
        {"set_input": {"node": f"tdie:{E['OneShotDeathRequestDeath']}", "name": "DeathReson", "value": 10}},
        {"add_child": {"parent": f"tsel:{bsel}", "child": f"tseq:{N['Sequential']}", "name": "True"}},
        {"add_child": {"parent": f"tsel:{bsel}", "child": f"tidle:{dummy}", "name": "False"}}]
    seq = [f"toff:{E['OneShotAttentionSenderChangeValid']}", f"thide:{hide_i}",
           f"tmw:{N['ExecuteGenericBoolForceResult']}",
           f"twait:{N['ExecuteGenericCounterByPlug']}",
           f"twin:{N['Simultaneous']}", f"tdie:{E['OneShotDeathRequestDeath']}", f"thold:{dummy}"]
    if os.environ.get("RANDO_TRAP_DIAG"):  # a test build that shows in game how far the trap gets
        seq, more = _trap_diag_edits(seq, chest, hide_src, hide_i, bsel, win_counter, own)
        e += more
    for ch in seq:
        e.append({"add_child": {"parent": f"tseq:{N['Sequential']}", "child": ch}})
    e.append({"add_child": {"parent": root, "child": f"tsel:{bsel}"}})
    return {"packs": packs, "ainb": [{"pack": "*", "file": GET_SCENE_AI, "edits": spring},
                                     {"pack": "*", "file": HP_AI, "edits": e}]}


def _trap_diag_edits(seq, chest, hide_src, hide_i, bsel, win_counter, own):
    """With RANDO_TRAP_DIAG=1 (test builds only) the trap shows three marks you can see in game. The Stone of Agony is
    a display actor in the item-look holder, so it shows on a hidden heart the same way the item looks do.
    1. A Stone of Agony at the heart as soon as the branch runs (the key reached the root AI).
    2. The Stone goes and the heart comes back when the attack window opens (the wait ended).
    3. The Stone shows again while the attack sensor touches something. That's the trap chest's contact check,
       nodes 58/59, on the "Body" of the "Atk" controller. The window lasts 120 frames, then the heart hides again."""
    import ainb
    N = TRAP_NODES
    sim = f"twin:{N['Simultaneous']}"
    q, g = 58, 59
    if chest.nodes[q]["name"] != "QueryRigidBodySensorIsContactHit" or chest.nodes[g]["name"] != "QueryPhysicsGetRigidBodyByControllerAndBodyName":
        raise DropPlanError(f"{TRAP_SRC['file']}: nodes 58/59 are no longer the sensor contact check")
    create_src, create = LOOK_SRC["create"][0], LOOK_SRC["create"][1]["OneShotActorHolderTryRequestCreateActorWithActorFileName"]
    nothing = LOOK_SRC["own"][1]["OneshotDoNothing"]
    del_src, delete = LOOK_SRC["delete"][0], LOOK_SRC["delete"][1]["OneShotActorHolderRequestDelete"]
    more = [
        {"copy": {"from": create_src, "nodes": [create], "label": "dran", "follow": False}},
        {"set_input": {"node": f"dran:{create}", "name": "ActorFileName", "value": "Item_AgonyStone"}},
        {"set_input": {"node": f"dran:{create}", "name": "Key", "value": "ShopHolder"}},
        {"copy": {"from": del_src, "nodes": [delete], "label": "ddel", "follow": False}},
        {"set_input": {"node": f"ddel:{delete}", "name": "Key", "value": "ShopHolder"}},
        {"copy": {"from": hide_src, "nodes": [hide_i], "label": "dshow", "follow": False}},
        {"set_input": {"node": f"dshow:{hide_i}", "name": "Bool", "value": True}},
        {"copy": {"from": hide_src, "nodes": [hide_i], "label": "dhide", "follow": False}},
        {"set_input": {"node": f"dhide:{hide_i}", "name": "Bool", "value": False}},
        {"copy": {"from": TRAP_SRC, "nodes": [q], "label": "dhit"}},  # with its rigid-body getter
        {"set_input": {"node": f"dhit:{g}", "name": "ControllerName", "value": "Atk"}},
        {"set_input": {"node": f"dhit:{g}", "name": "RigidBodyName", "value": "Body"}},
        {"copy": {"from": own, "nodes": [bsel], "label": "dsel", "follow": False}},
        {"feed": {"from": f"dhit:{q}", "output": "IsHit", "to": f"dsel:{bsel}", "input": "Input"}},
        {"copy": {"from": create_src, "nodes": [create], "label": "dmark", "follow": False}},
        {"set_input": {"node": f"dmark:{create}", "name": "ActorFileName", "value": "Item_AgonyStone"}},
        {"set_input": {"node": f"dmark:{create}", "name": "Key", "value": "ShopHolder"}},
        {"copy": {"from": LOOK_SRC["own"][0], "nodes": [nothing], "label": "dnone", "follow": False}},
        {"add_child": {"parent": f"dsel:{bsel}", "child": f"dmark:{create}", "name": "True"}},
        {"add_child": {"parent": f"dsel:{bsel}", "child": f"dnone:{nothing}", "name": "False"}},
        {"add_child": {"parent": sim, "child": f"dsel:{bsel}"}},
        {"set_input": {"node": f"twin:{win_counter}", "name": "BaseFrameTime", "value": 120.0}}]
    i = seq.index(sim)
    seq = seq[:i] + [f"ddel:{delete}", f"dshow:{hide_i}", sim, f"dhide:{hide_i}"] + seq[i + 1:]
    j = seq.index(f"thide:{hide_i}")
    seq = seq[:j + 1] + [f"dran:{create}"] + seq[j + 1:]
    return seq, more


# The ice-trap attacker (every kind of ice trap)
# I tried giving the disguise carrier the trap chest's attack and it never ran. Not from a dead actor, not from an
# offstage one, and not with a blackboard key from the get scene, which never reached its root AI.
# The remake has a cleaner way. A scene can create a condition sensor with
# GameSystemActor.EventTriggerRequestCreateConditionSensor {ActorName}, the way Dm_SY_Ocarina does for the Sun's Song
# and Song of Storms sensors. The game's manager deletes the sensor it made before (0x832b1660) and creates the named
# actor 1 m above Link.
# ConditionSensorActor is the base of both song sensors and vanilla never creates it by name, so it becomes the
# ice-trap attacker. It gets the trap chest's attack (sensor, SensorHit, an AttackParam for half a heart of ice) and
# an AI that waits until no main event plays (Link is out of the scene), waits a bit more, then runs the chest's
# attack window. The shared freeze scene (_chests_scenes.freeze_graph) ends by creating it, so chests, NPCs, shops
# and drops all freeze Link for real.
# ConditionSensorActor's ActorParam is the parent of the song sensors. They keep their own AI and no affiliation
# through overrides of their own (SongOfTheSunSensorActor sets AIInfoRef and AffiliationRef "", Storm sets
# AffiliationRef "").
SENSOR_ACTOR = "ConditionSensorActor"
SENSOR_PACK = f"Pack/Actor/{SENSOR_ACTOR}.pack.zs"
SENSOR_NAME = "RandoIceTrapSensor"
SENSOR_WAIT_FRAMES = 20.0
SENSOR_WINDOW_FRAMES = 90.0
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
SENSOR_HEAP = 65536  # bytes. The Sun's Song sensor has 28536, ours adds AI nodes, sound and affiliation
CHILD_CONDITION = "Component/ConditionParam/Player_Child.game__component__ConditionParam.bgyml"
SENSOR_ELINK = "Component/ELink/Obj_TBox_A_04.engine__component__ELinkParam.bgyml"
SENSOR_SLINK = "Component/SLink/Obj_TBox_A_04.engine__component__SLinkParam.bgyml"
SENSOR_XLINK = "?Component/XLink/ActorBasic.engine__component__XLinkParam.bgyml"  # (a resident file)
# The attacker follows Link, wherever the manager made it. ExecuteActorForceSetPos (as in the cuccos' event AI)
# fed by QueryDungeonGetPlayerPos (as in the trap chest's AI) keeps it standing on him.
FORCE_POS_SRC = ({"pack": "Pack/Actor/Animal_Cucco.pack.zs", "file": "AI/Animal_Cucco.event.root.ainb"},
                 {"ExecuteActorForceSetPos": 37})
SUN = "SongOfTheSunSensorActor"
STORM = "SongOfTheStormSensorActor"
CREATE_SENSOR = {"actor": "GameSystemActor", "action": "EventTriggerRequestCreateConditionSensor",
                 "params": {"ActorName": SENSOR_ACTOR}}
AFFILIATION = "?Component/AffiliationParam/ObjectCommon.game__component__AffiliationParam.bgyml"  # ResidentCommon


def ice_sensor_ops(romfs=DEFAULT_ROMFS):
    """{"packs", "ainb"} sections that turn ConditionSensorActor into the ice-trap attacker (see SENSOR_ACTOR)."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    sf = sarc_files(fs.read(SENSOR_PACK))
    tf = sarc_files(fs.read(TRAP_SRC["pack"]))
    sun_pack = f"Pack/Actor/{SUN}.pack.zs"
    sunf = sarc_files(fs.read(sun_pack))
    chest = _check_src(fs, TRAP_SRC, TRAP_NODES, "the trap chest's attack")
    w = chest.nodes[TRAP_NODES["ExecuteGenericBoolForceResult"]]["inputs"]["bool"][0]["node"]
    if chest.nodes[w]["name"] != "QueryInvertBool":
        raise DropPlanError(f"{TRAP_SRC['file']}: node 29 no longer reads an inverted query")
    _check_src(fs, *TRAP_MAIN_EVENT_SRC, "the main-event query")
    own_ai = f"AI/{SENSOR_ACTOR}.root.ainb"
    base = ainb.Ainb(sf[own_ai])
    if [n["name"] for n in base.nodes] != ["ExecuteSensorHitSetupAttack"]:
        raise DropPlanError(f"{own_ai}: no longer the single attack node")
    ap = f"Actor/{SENSOR_ACTOR}.engine__actor__ActorParam.bgyml"
    comps = byml_load(sf[ap])[0]["Components"]
    for key in ("AIInfoRef", "PhysicsRef", "SensorHitRef"):
        if key not in comps:
            raise DropPlanError(f"{ap}: no {key}")
    if "GameParameterTableRef" in comps or "AffiliationRef" in comps:
        raise DropPlanError(f"{ap}: already has a parameter table or an affiliation")
    for child in (SUN, STORM):  # the song sensors keep what they had
        c = byml_load(sarc_files(fs.read(f"Pack/Actor/{child}.pack.zs"))[
            f"Actor/{child}.engine__actor__ActorParam.bgyml"])[0]["Components"]
        for key in ("GameParameterTableRef", "PhysicsRef", "SensorHitRef"):
            if key not in c:
                raise DropPlanError(f"{child}: no {key} of its own (it would inherit the ice trap's)")
    set_src = f"Phive/ControllerSetParam/{SENSOR_ACTOR}.phive__ControllerSetParam.bgyml"
    phys_src = f"Component/Physics/{SENSOR_ACTOR}.engine__component__PhysicsParam.bgyml"
    info_src = f"AI/AIInfo/{SENSOR_ACTOR}.engine__actor__AIInfo.bgyml"
    gpt_src = f"GameParameter/GameParameterTable/{SUN}.engine__actor__GameParameterTable.bgyml"
    for f, files in ((set_src, sf), (phys_src, sf), (info_src, sf), (gpt_src, sunf)):
        if f not in files:
            raise DropPlanError(f"no {f}")
    chest_set = byml_load(tf["Phive/ControllerSetParam/Obj_TBox_A_04.phive__ControllerSetParam.bgyml"])[0]

    def pick(key, name, path_part):
        hit = [e for e in chest_set[key] if e["Name"] == name and path_part in e["FilePath"]]
        if len(hit) != 1:
            raise DropPlanError(f"Obj_TBox_A_04 controller set: no single {key} {name} ({path_part})")
        return [dict(hit[0])]
    new_set = f"Phive/ControllerSetParam/{SENSOR_NAME}.phive__ControllerSetParam.bgyml"
    new_phys = f"Component/Physics/{SENSOR_NAME}.engine__component__PhysicsParam.bgyml"
    new_info = f"AI/AIInfo/{SENSOR_NAME}.engine__actor__AIInfo.bgyml"
    new_ai = f"AI/{SENSOR_NAME}.root.ainb"
    new_gpt = f"GameParameter/GameParameterTable/{SENSOR_NAME}.engine__actor__GameParameterTable.bgyml"
    packs = [{"pack": SENSOR_PACK, "file": f, "from_pack": TRAP_SRC["pack"]} for f in TRAP_FILES]
    packs += [
        {"pack": SENSOR_PACK, "file": new_set, "new_from": set_src, "set": {
            "CColSensorNamePathAry": pick("CColSensorNamePathAry", "Atk", "HitToCharacter"),
            "ControllerSensorNamePathAry": pick("ControllerSensorNamePathAry", "Atk", "Obj_TBox_A_04_Atk"),
            "RigidBodySensorNamePathAry": pick("RigidBodySensorNamePathAry", "Body", "Obj_TBox_A_04_Atk"),
            "ShapeNamePathAry": pick("ShapeNamePathAry", "Body_Atk", "Obj_TBox_A_04__Atk")}},
        {"pack": SENSOR_PACK, "file": new_phys, "new_from": phys_src,
         "set": {"ControllerSetPath": _W + new_set.replace(".bgyml", ".gyml")}},
        {"pack": SENSOR_PACK, "file": new_info, "new_from": info_src,
         "set": {"RootAIRef": f"Work/AI/Root/{SENSOR_NAME}.root.ain"}},
        {"pack": SENSOR_PACK, "file": new_ai, "from_pack": SENSOR_PACK, "new_from": own_ai},  # bytes (not BYML)
        {"pack": SENSOR_PACK, "file": new_gpt, "from_pack": sun_pack, "new_from": gpt_src,
         "set": {"Components.gamebalance_AttackParam": "?" + TRAP_FILES[5]}},
        # The trap chest's effect and sound users, for its freeze breath (TBox_FreezeBreath)
        {"pack": SENSOR_PACK, "file": SENSOR_ELINK, "from_pack": TRAP_SRC["pack"]},
        {"pack": SENSOR_PACK, "file": SENSOR_SLINK, "from_pack": TRAP_SRC["pack"]}]
    # The parent of every condition sensor gets the ice trap's parts. Its own pack holds the files.
    adds = {"AIInfoRef": "?" + new_info, "PhysicsRef": "?" + new_phys, "SensorHitRef": "?" + TRAP_FILES[4],
            "GameParameterTableRef": "?" + new_gpt, "AffiliationRef": AFFILIATION, "ELinkRef": "?" + SENSOR_ELINK,
            "SLinkRef": "?" + SENSOR_SLINK, "XLinkRef": SENSOR_XLINK}
    packs.append({"pack": "*", "file": ap, "set": {f"Components.{k}": v for k, v in adds.items()}})
    # Child Link has to freeze too, OoTR's ice traps freeze him. The remake turns it off for him (IsEnableFrozen false
    # in Player_Child's ConditionParam, over Player's true), so the attack hurt the child but never froze him. His AI
    # has the same frozen reaction and break-free modules as the adult's (Player.action.reactionfrozen / breakfrozen).
    packs.append({"pack": "*", "file": CHILD_CONDITION, "set": {"IsEnableFrozen": True}})
    # The song sensors keep what they had. Each component they took from this parent keeps its old value, and the
    # parent's new ones are switched off with "" (vanilla does the same with LiftableRef "").
    for child in (SUN, STORM):
        cap = f"Actor/{child}.engine__actor__ActorParam.bgyml"
        own = byml_load(sarc_files(fs.read(f"Pack/Actor/{child}.pack.zs"))[cap])[0]["Components"]
        keep = {f"Components.{k}": comps.get(k, "") for k in adds if k not in own}
        if keep:
            packs.append({"pack": "*", "file": cap, "set": keep})
    N = TRAP_NODES
    win_counter = chest.nodes[N["Simultaneous"]]["plugs"][ainb.PLUG_CHILD][0]["node"]
    hp_src = {"pack": HP_PACK, "file": HP_AI}
    hp = ainb.Ainb(sarc_files(fs.read(HP_PACK))[HP_AI])
    dummy = hp.node("ExecuteGenericDummyAction")
    mq = TRAP_MAIN_EVENT_SRC[1]["QueryIsPlayingMainEvent"]
    _check_src(fs, *FORCE_POS_SRC, "the force-position node")
    breath, ppos = 1, 42
    if chest.nodes[breath]["name"] != "OneShotXLinkSearchAndEmit" or chest.nodes[ppos]["name"] != "QueryDungeonGetPlayerPos":
        raise DropPlanError(f"{TRAP_SRC['file']}: nodes 1/42 are no longer the breath and the player position")
    fpos = FORCE_POS_SRC[1]["ExecuteActorForceSetPos"]
    e = [
        {"copy": {"from": TRAP_SRC, "nodes": [N["Sequential"]], "label": "s", "follow": False}},
        {"copy": {"from": TRAP_SRC, "nodes": [N["ExecuteGenericBoolForceResult"]], "label": "w", "follow": False}},
        {"copy": {"from": TRAP_SRC, "nodes": [w], "label": "i", "follow": False}},
        {"copy": {"from": TRAP_MAIN_EVENT_SRC[0], "nodes": [mq], "label": "m", "follow": False}},
        {"feed": {"from": f"m:{mq}", "output": "IsPlayingMainEvent", "to": f"i:{w}", "input": "Bool"}},
        {"feed": {"from": f"i:{w}", "output": "Bool", "to": f"w:{N['ExecuteGenericBoolForceResult']}",
                  "input": "Bool"}},
        # The chest's timers read its blackboard (flags 0x8000000N), so the copies get plain values.
        {"copy": {"from": TRAP_SRC, "nodes": [N["ExecuteGenericCounterByPlug"]], "label": "c", "follow": False,
                  "values": {str(N["ExecuteGenericCounterByPlug"]): {"BaseFrameTime": SENSOR_WAIT_FRAMES}}}},
        {"copy": {"from": TRAP_SRC, "nodes": [N["Simultaneous"]], "label": "win",
                  "values": {str(win_counter): {"BaseFrameTime": SENSOR_WINDOW_FRAMES}}}},
        {"copy": {"from": hp_src, "nodes": [dummy], "label": "h", "follow": False}},
        # the chest's freeze breath when the attacker appears and again as its attack starts
        {"copy": {"from": TRAP_SRC, "nodes": [breath], "label": "x1", "follow": False}},
        {"copy": {"from": TRAP_SRC, "nodes": [breath], "label": "x2", "follow": False}},
        {"copy": {"from": TRAP_SRC, "nodes": [ppos], "label": "pp", "follow": False}},
        {"copy": {"from": FORCE_POS_SRC[0], "nodes": [fpos], "label": "fp", "follow": False}},
        {"link": {"from": f"pp:{ppos}", "output": "Position", "to": f"fp:{fpos}", "input": "Destination"}},
        # The vanilla always-on attack is switched off with AttackType 0 (the node's update returns at once,
        # 0x808f29c0), and the sequence runs beside it.
        {"set_input": {"node": 0, "name": "AttackType", "value": 0}},
        {"wrap": {"command": "Root"}},
        {"add_child": {"parent": "@Root", "child": f"s:{N['Sequential']}"}},
        {"add_child": {"parent": "@Root", "child": f"fp:{fpos}"}}]
    for ch in (f"x1:{breath}", f"w:{N['ExecuteGenericBoolForceResult']}", f"c:{N['ExecuteGenericCounterByPlug']}",
               f"x2:{breath}", f"win:{N['Simultaneous']}", f"h:{dummy}"):
        e.append({"add_child": {"parent": f"s:{N['Sequential']}", "child": ch}})
    # The actor table. Vanilla never creates the base actor, so its row gives it no instance heap and no effect or
    # sound user. With a heap of 0 the manager's create request fails. The Sun's Song sensor (a sensor, SensorHit, a
    # parameter table, a one-node AI, effects) has 28536 bytes.
    row = f"[__RowId={SENSOR_ACTOR}]"
    byml = [{"file": ACTOR_INFO, "set": {f"{row}.InstanceHeapSize": SENSOR_HEAP,
                                         f"{row}.ELinkUserName": "Obj_TBox_A_04",
                                         f"{row}.SLinkUserName": "Obj_TBox_A_04"}}]
    return {"packs": packs, "ainb": [{"pack": SENSOR_PACK, "file": new_ai, "edits": e}], "byml": byml}


def _bb_init_value(a, files, node, name):
    """The value a blackboard-read parameter of node `node` gets in its own actor. We find the entry it reads (flags
    0x8000000N), then that key's InitVal in the actor's blackboard parameter tables (pack `files`), and fall back to
    the file's default."""
    import ainb
    t, e = a._param(node, "inputs", name)
    f = e["flags"]
    if f >> 24 != 0x80:
        if f & ainb.BB_INDEXED:
            raise DropPlanError(f"node {node} {name}: an indexed form this reader doesn't know ({f:#x})")
        return e["value"]
    entry = a.bb[t][f & 0xFFFF]
    key = {"float": "BlackboardParamF32Array", "int": "BlackboardParamS32Array",
           "bool": "BlackboardParamBoolArray", "string": "BlackboardParamStringArray"}[t]
    from romtools import byml_load
    for path in (b["path"] for b in a.bb_files):
        inner = path.replace("Work/", "", 1).replace(".gyml", ".bgyml")
        if inner in files:
            for row in byml_load(files[inner])[0].get(key, []):
                if row["BBKey"] == entry["name"]:
                    return row["InitVal"]
    return entry["default"]


def _actor_name_sources(fs):
    """The (QueryGenericGetOwnActorLink, QueryGenericGetActorName) nodes in the dogs' event AI, the pair that reads the
    actor's type name."""
    from romtools import sarc_files
    import ainb
    dog = ainb.Ainb(sarc_files(fs.read(GS_NAME_SRC["pack"]))[GS_NAME_SRC["file"]])
    an = dog.node("QueryGenericGetActorName")
    own = dog.nodes[an]["inputs"]["ptr"][0]["node"]
    if dog.nodes[own]["name"] != "QueryGenericGetOwnActorLink":
        raise DropPlanError(f"{GS_NAME_SRC['file']}: QueryGenericGetActorName is no longer fed by its own actor")
    return own, an


def _read_chain(new, cmd, vanilla_first):
    """Walks the chain we added to a tag query. Returns ([(kind, compared string, answer, selector)], end node, problem
    or None), kind being "name" or "type"."""
    import ainb
    out, i, seen = [], new.nodes[cmd]["plugs"][ainb.PLUG_CHILD][0]["node"], set()
    while i != vanilla_first and i not in seen:
        seen.add(i)
        n = new.nodes[i]
        kids = {pl["name"]: pl["node"] for pl in n["plugs"][ainb.PLUG_CHILD]}
        if ainb.NODE_TYPES.get(n["type"]) != "BoolSelector" or set(kids) != {"True", "False"}:
            return out, i, f"node {i} in the chain is not a two-case BoolSelector"
        src = n["inputs"]["bool"][0]["node"]
        q = new.nodes[src]
        if q["name"] == "QueryMathEqualF32":  # a scene drop's tag (get_scene_ops drop_tags)
            fins = {e["name"]: e for e in q["inputs"]["float"]}
            g = new.nodes[fins["F32"]["node"]] if fins["F32"]["node"] >= 0 else None
            props = {e["name"]: e["value"] for t in ainb.PTYPES for e in g["properties"][t]} if g else {}
            if g is None or g["name"] != "QueryBlackboardGetF32" or props.get("BlackboardType") != 1 or \
                    props.get("BlackboardKey") != PICKUP_TAG_KEY or fins["S32Base"]["node"] >= 0:
                return out, i, f"selector {i}: a number check that is not on the carrier's {PICKUP_TAG_KEY}"
            if not any(pl["node"] == src and pl["name"] == "Input" for pl in n["plugs"][0]):
                return out, i, f"selector {i}: an input link has no plug"
            ans = new.nodes[kids["True"]]
            if ans["name"] != "ExecuteEventSetQueryValue":
                return out, i, f"selector {i}: its True case is {ans['name']}"
            out.append(("tag", fins["S32Base"]["value"],
                        next(e["value"] for e in ans["inputs"]["int"] if e["name"] == "Value"), i))
            i = kids["False"]
            continue
        ins = {e["name"]: e for e in q["inputs"]["string"]}
        if q["name"] != "QueryStringIsEqual" or ins["StringA"]["node"] < 0 or ins["StringB"]["node"] >= 0:
            return out, i, f"selector {i} is not fed by a string comparison"
        a = new.nodes[ins["StringA"]["node"]]
        if a["name"] == "QueryGetActorInstanceName":
            kind = "name"
        elif a["name"] == "QueryGenericGetActorName" and \
                a["outputs"]["string"][ins["StringA"]["plug"]]["name"] == "ActorFileName" and \
                new.nodes[a["inputs"]["ptr"][0]["node"]]["name"] == "QueryGenericGetOwnActorLink":
            kind = "type"
        else:
            return out, i, f"selector {i}: compares {a['name']}, not the instance name or the own type"
        if not any(pl["node"] == src and pl["name"] == "Input" for pl in n["plugs"][0]) or \
                not any(pl["node"] == ins["StringA"]["node"] for pl in q["plugs"][4]):
            return out, i, f"selector {i}: an input link has no plug"
        ans = new.nodes[kids["True"]]
        if ans["name"] != "ExecuteEventSetQueryValue":
            return out, i, f"selector {i}: its True case is {ans['name']}"
        out.append((kind, ins["StringB"]["value"],
                    next(e["value"] for e in ans["inputs"]["int"] if e["name"] == "Value"), i))
        i = kids["False"]
    return out, i, None


def verify_get_scene(patch_dir, entries, romfs=DEFAULT_ROMFS, fallthrough=None, drop_tags=()):
    """Reads a built patch back and returns [problem, ...]. Empty means every spot's placements carry its Name, and
    every event AI file is the same in every pack holding it. Its chain walks name checks answering exactly the
    seed's spots, then for `fallthrough` ({pack: tag}) a check of the actor's own type answering that tag, then the
    untouched vanilla answer. Every vanilla node of the edited AI file also reads as before."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    import packpaths
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch_dir])
    problems, by_ai = [], defaultdict(dict)
    levels = {}
    for e in entries:
        gs = e["get_scene"]
        by_ai[gs.get("ai") or GET_SCENE_AI][gs["name"]] = gs.get("value", gs["tag"])
        for p in e["placements"]:
            if p["file"] not in levels:
                levels[p["file"]] = {str(a.get("Hash")): a for a in byml_load(out.read(p["file"]))[0]["Actors"]}
            a = levels[p["file"]].get(p["hash"])
            want = gs.get("as") or p["actor"]
            if a is None or a.get("Name") != gs["name"] or a.get("Gyaml") != want:
                problems.append(f"{p['file']} {p['hash']}: Name {a and a.get('Name')!r}, type "
                                f"{a and a.get('Gyaml')}, expected {gs['name']} on {want}")
    fall = _fall_by_ai(fallthrough)
    for ai_file in fall:
        by_ai.setdefault(ai_file, {})
    if drop_tags:
        by_ai.setdefault(GET_SCENE_AI, {})
    for ai_file, want in sorted(by_ai.items()):
        packs = packpaths.carriers(ai_file, romfs)
        copies = {pk: sarc_files(out.read(pk))[ai_file] for pk in packs}
        if len(set(copies.values())) != 1:
            problems.append(f"{ai_file}: not the same in every pack holding it ({len(set(copies.values()))} "
                            f"versions in {len(packs)} packs)")
        old = ainb.Ainb(sarc_files(fs.read(packs[0]))[ai_file])
        new = ainb.Ainb(copies[packs[0]])
        cmd = next(c for c in new.commands if c["name"] == GET_SCENE_QUERY)["main"]
        vanilla_first = old.nodes[cmd]["plugs"][ainb.PLUG_CHILD][0]["node"]
        looked = {c["main"] for c in new.commands if c["name"] == LOOK_HIDE_COMMAND}  # verify_looks reads it
        sprung = set()
        if False:  # the old spring command for the disguised trap, now off (see ice_sensor_ops)
            sprung = {c["main"] for c in new.commands if c["name"] == TRAP_SPRING["action"]}
            for s in sprung:
                kids = [pl["node"] for pl in new.nodes[s]["plugs"][ainb.PLUG_CHILD]]
                sets = [pl["node"] for k in kids for pl in new.nodes[k]["plugs"][ainb.PLUG_CHILD]]
                ok = (len(kids) == 1 and ainb.NODE_TYPES.get(new.nodes[kids[0]]["type"]) == "Simultaneous"
                      and len(sets) == 1 and new.nodes[sets[0]]["name"] == "ExecuteBlackboardSetBool")
                if ok:
                    n = new.nodes[sets[0]]
                    props = {e["name"]: e["value"] for t in ("int", "bool", "string") for e in n["properties"][t]}
                    ok = (props.get("BlackboardType") == 1 and props.get("BlackboardKey") == TRAP_KEY
                          and n["inputs"]["bool"][0]["value"] is True and n["inputs"]["bool"][0]["node"] < 0)
                if not ok:
                    problems.append(f"{ai_file}: {TRAP_SPRING['action']} doesn't just set {TRAP_KEY}")
        guarded = set(lake_guard_nodes(old, new)) if ai_file == LAKE_AI else set()  # See verify_lake_guard.
        for i in range(len(old.nodes)):
            if i != cmd and i not in looked | sprung | guarded and ainb.describe_node(old, i) != ainb.describe_node(new, i):
                problems.append(f"{ai_file}: vanilla node {i} changed")
        chain, end, why = _read_chain(new, cmd, vanilla_first)
        if why:
            problems.append(f"{ai_file}: {why}")
        elif end != vanilla_first:
            problems.append(f"{ai_file}: the chain doesn't end at the vanilla answer")
        kinds = [k for k, *_ in chain]
        if kinds != sorted(kinds):  # "name" checks first, then the scene drops' "tag", then "type"
            problems.append(f"{ai_file}: the checks are out of order ({kinds})")
        tags = {s: v for k, s, v, _ in chain if k == "tag"}
        want_tags = {float(t): t for t in drop_tags} if ai_file == GET_SCENE_AI else {}
        if tags != want_tags:
            problems.append(f"{ai_file}: answers drop tags {sorted(tags.values())}, expected {sorted(want_tags.values())}")
        got = {s: v for k, s, v, _ in chain if k == "name"}
        types = [(s, v) for k, s, v, _ in chain if k == "type"]
        if got != want:
            problems.append(f"{ai_file}: answers {got}, expected {want}")
        if types != fall.get(ai_file, []):
            problems.append(f"{ai_file}: type checks {types}, expected {fall.get(ai_file, [])}")
    return problems


def verify_pickup_save(patch_dir, droppers, pickups, romfs=DEFAULT_ROMFS):
    """Reads a built patch back and returns [problem, ...]. Empty means every pipeline part is in the written files
    exactly and every vanilla node of every edited AI file reads as before."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    van = Romfs(romfs, os.path.join(HERE, "original"))
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad = []

    def pair(pack, inner, base=None):
        old = dropper_ai_bytes(van, base) if base in NEW_AI_DROPPERS else sarc_files(van.read(pack))[inner]
        return ainb.Ainb(old), ainb.Ainb(sarc_files(new.read(pack))[inner])

    def same_old(a, b, where, root_changes=()):
        for i in range(len(a.nodes)):
            if i not in root_changes and ainb.describe_node(a, i) != ainb.describe_node(b, i):
                bad.append(f"{where}: vanilla node {i} changed")

    def chain_to(b, drop, s32=None):
        keys, j = [], drop
        while True:
            src = b._input(j, "OverwriteParam")[1]["node"] if b.nodes[j]["name"] != "QueryGenericMakeOverwriteParam" else -1
            if src < 0:
                return keys, b.nodes[j]["name"]
            j = src
            if b.nodes[j]["name"] == "QueryBlackboardOverwriteParamAddNoRespawnGmdHash":
                keys.append(b._param(j, "properties", "Key")[1]["value"])
            if b.nodes[j]["name"] == "QueryBlackboardOverwriteParamAddS32" and s32 is not None:
                g = b._input(j, "S32")[1]["node"]
                s32.append((b._param(j, "properties", "Key")[1]["value"],
                            g >= 0 and b.nodes[g]["name"] == "QueryBlackboardGetS32" and
                            b._param(g, "properties", "BlackboardType")[1]["value"] == 1 and
                            b._param(g, "properties", "BlackboardKey")[1]["value"]))

    def setter_ok(b, parent, key, array=None, pos=None):
        """True if a child of node `parent` sets `array`[the actor's table key `key`], with inputs shaped like the
        game's (the fed index flags 0, the constants 0x800000/0x1800000). Without `array` it checks for VISIT_ARRAY then
        CHECKED_ARRAY as the first two children of Simultaneous `parent`, before the death signal (VISIT)."""
        if array is None:
            return setter_ok(b, parent, key, VISIT_ARRAY, 0) and setter_ok(b, parent, key, CHECKED_ARRAY, 1)
        for k, pl in enumerate(b.nodes[parent]["plugs"][ainb.PLUG_CHILD]):
            n = b.nodes[pl["node"]]
            if n["name"] != "OneShotSetNonStructGameDataBool":
                continue
            if pos is not None and k != pos:
                continue
            vals = {e["name"]: e for t in ainb.PTYPES for e in n["inputs"][t]}
            g = vals.get("GameDataIndex", {}).get("node", -1)
            if vals.get("GameDataIndex", {}).get("flags", 1) != 0 or any(
                    not vals.get(c, {}).get("flags", 0) & 0x1800000 for c in ("GameDataFullName", "Value")):
                continue
            if vals.get("GameDataFullName", {}).get("value") == array and \
                    vals.get("Value", {}).get("value") is True and g >= 0 and \
                    b.nodes[g]["name"] == "QueryBlackboardGetS32" and \
                    b._param(g, "properties", "BlackboardType")[1]["value"] == 1 and \
                    b._param(g, "properties", "BlackboardKey")[1]["value"] == key:
                return True
        return False

    for actor in sorted(droppers):
        if actor == "Enemy_Skulltula_Gold":
            a, b = pair(GS_PACK, GS_AI)
            keys, start = chain_to(b, b.node("OneShotDropSetOverWriteParam"))
            if sorted(keys) != ["GoldTokenGmdHash", "RespawnGmdHash"] or start != "QueryGenericMakeOverwriteParam":
                bad.append(f"{actor}: drop chain {keys} from {start}")
            same_old(a, b, actor, {b.node("OneShotDropSetOverWriteParam"), 1})
            continue
        kind, base = FLAGLESS_DROPPERS.get(actor, (None, actor))
        if kind == "tree":  # its own drop chain and flag gate (verify_object_drops)
            continue
        ai_file = _dropper_root(base)
        pack = f"Pack/Actor/{base}.pack.zs"
        a, b = pair(pack, ai_file, base)
        if base in NEW_AI_DROPPERS:  # a new AI of its own, named by its ActorParam through its AIInfo
            files_ = sarc_files(new.read(pack))
            info_ = new_ai_paths(base)[1]
            comps_ = byml_load(files_[_AP.format(base)], allow_big=True)[0].get("Components") or {}
            if comps_.get("AIInfoRef") != "?" + info_ or info_ not in files_ or byml_load(files_[info_])[0] != {
                    "RootAIRef": f"Work/AI/Root/{NEW_AI_DROPPERS[base]['name']}.root.ain"}:
                bad.append(f"{actor}: its new AI isn't named by its ActorParam and AIInfo ({comps_.get('AIInfoRef')})")
        root = b.commands[0]["main"]
        drops_ = [i for i, n in enumerate(b.nodes) if n["name"] == "OneShotDropSetOverWriteParam"]
        if len(drops_) != 1 or not any(pl["node"] == drops_[0] for pl in b.nodes[root]["plugs"][ainb.PLUG_CHILD]):
            bad.append(f"{actor}: the drop-hash node is not an always-on branch of its root")
            continue
        if ai_file in HANDOVER_FIRST and b.nodes[root]["plugs"][ainb.PLUG_CHILD][0]["node"] != drops_[0]:
            bad.append(f"{actor}: the drop-hash node must be its root's first branch (before the drop is reserved)")
        s32 = []
        keys, start = chain_to(b, drops_[0], s32)
        if sorted(keys) != ["GoldTokenGmdHash", "RespawnGmdHash"] or start != "QueryGenericMakeOverwriteParam":
            bad.append(f"{actor}: drop chain {keys} from {start}")
        if s32 != [(PICKUP_CHK_KEY, DROP_CHK_KEY)]:  # the respawn model's bit goes with the drop
            bad.append(f"{actor}: drop chain hands on {s32}, not {PICKUP_CHK_KEY} from the instance key {DROP_CHK_KEY}")
        sb = [i for i, n in enumerate(b.nodes) if n["type"] == 3 and setter_ok(b, i, DROP_CHK_KEY)  # (VISIT)
              and any(m["type"] == 7 and any(pl["node"] == i for pl in m["plugs"][ainb.PLUG_CHILD]) for m in b.nodes)]
        if not sb:
            bad.append(f"{actor}: no save-on-break branch setting {CHECKED_ARRAY}[{DROP_CHK_KEY}]")
        same_old(a, b, actor, {a.commands[0]["main"]})
        if kind is None:  # breaking it saves as in vanilla, DeathParam and death tables untouched
            files, vfiles = sarc_files(new.read(pack)), sarc_files(van.read(pack))
            if _death_owner(files, actor) != _death_owner(vfiles, actor):
                bad.append(f"{actor}: its DeathParam changed ({_death_owner(files, actor)})")
    for table in (SCRUB_TABLE, BOX03_TABLE, ICICLE_TABLE):
        if new.raw(table) != van.raw(table):
            bad.append(f"{table}: edited (the respawn model keeps vanilla break saving)")
    # A Gold Skulltula kill doesn't save, so it comes back on a map change or load until the drop is taken.
    if "Enemy_Skulltula_Gold" in droppers:
        gs = byml_load(new.raw(GS_DEATH))[0]
        txt = json.dumps(gs, default=str)
        if new.raw(GS_DEATH) != van.raw(GS_DEATH) or '"LifeDepleted___Data"' not in txt or \
                '"IsSetGmdRespawnFlagToFalse": false' not in txt.split('"LifeDepleted___Data"', 1)[1][:400]:
            bad.append(f"{GS_DEATH}: a killed Gold Skulltula must not save itself (LifeDepleted IsSetGmdRespawnFlagToFalse"
                       f" false, vanilla): it comes back until its token or item is taken")
    hb = ainb.Ainb(sarc_files(new.read(HP_PACK))[HP_AI])
    if any(a_ != "Enemy_Skulltula_Gold" for a_ in droppers):  # trees too (Flagless pickups, pickup_save_ops)
        if not setter_ok(hb, HP_DEATH_SIM, PICKUP_CHK_KEY):
            bad.append(f"{HP_AI}: its death branch doesn't set {CHECKED_ARRAY}[{PICKUP_CHK_KEY}]")
        bb = byml_load(sarc_files(new.read(HP_PACK))[CARRIER_TABLE])[0]
        if not any(r.get("BBKey") == PICKUP_CHK_KEY for r in bb.get("BlackboardParamS32Array", [])):
            bad.append(f"{HP_PACK}: no S32 {PICKUP_CHK_KEY} in {CARRIER_TABLE}")
        tk = sarc_files(new.read(TOKEN_PACK))  # the Gold Skulltula token sets its dropper's bit when collected
        if not setter_ok(ainb.Ainb(tk[TOKEN_AI]), TOKEN_DEATH_SIM, PICKUP_CHK_KEY):
            bad.append(f"{TOKEN_AI}: its death branch doesn't set {CHECKED_ARRAY}[{PICKUP_CHK_KEY}] first")
        tb = byml_load(tk[TOKEN_TABLE])[0]
        if not any(r.get("BBKey") == PICKUP_CHK_KEY for r in tb.get("BlackboardParamS32Array", [])):
            bad.append(f"{TOKEN_PACK}: no S32 {PICKUP_CHK_KEY} in {TOKEN_TABLE}")
    for actor in sorted(pickups):
        if actor in SAVES_ALREADY or actor not in PICKUP_SAVERS:
            continue
        ai_file, table = PICKUP_SAVERS[actor]
        pack = f"Pack/Actor/{actor}.pack.zs"
        bb = byml_load(sarc_files(new.read(pack))[table])[0]
        row = next((r for r in bb.get("BlackboardParamU64Array", []) if r.get("BBKey") == "RespawnGmdHash"), None)
        if row is None or type(row["InitVal"]).__name__ != "U32" or row["InitVal"] != 0:
            bad.append(f"{actor}: no RespawnGmdHash u64 key (U32 0) in {table}")
        where = (pack, ai_file) if ai_file else (AI_GLOBAL, "AI/DropItem.root.ainb")
        a, b = pair(*where)
        root = b.commands[0]["main"]
        spawn = {pl["node"] for pl in b.nodes[root]["plugs"][ainb.PLUG_CHILD]}  # these run once when the pickup spawns
        spawn |= {pl["node"] for n in b.nodes if any(b.nodes[p["node"]]["name"] == "OneShotGenericDeleteThisActor"
                                                     for p in n["plugs"][ainb.PLUG_CHILD])
                  for pl in n["plugs"][ainb.PLUG_CHILD]}  # these run when the pickup turns into the rupee
        t = [i for i, n in enumerate(b.nodes) if n["name"] == "OneShotHeartPieceTakenDeadAfter" and i not in spawn]
        if len(t) != 1:
            bad.append(f"{actor}: {where[1]} has {len(t)} save-on-take nodes")
            continue
        holders = [j for j, m in enumerate(b.nodes) if t[0] in [q["node"] for q in m["plugs"][2]]]
        cases = {int.from_bytes(pl["extra"][4:8], "little", signed=True) for n in b.nodes if n["type"] == 1
                 for pl in n["plugs"][2][:-1] if pl["node"] in holders}
        if not {DEATH_PICKED_UP, DEATH_LIFE_DEPLETED} <= cases:
            bad.append(f"{actor}: the save-on-take node runs on death cases {sorted(cases)}, not on both "
                       f"{DEATH_PICKED_UP} (picked up) and {DEATH_LIFE_DEPLETED} (get scene)")
        if not any(setter_ok(b, j, PICKUP_CHK_KEY) for j in holders):
            bad.append(f"{actor}: taking it doesn't set {CHECKED_ARRAY}[{PICKUP_CHK_KEY}] (the respawn model)")
        if not any(r.get("BBKey") == PICKUP_CHK_KEY for r in bb.get("BlackboardParamS32Array", [])):
            bad.append(f"{actor}: no S32 {PICKUP_CHK_KEY} in {table}")
        same_old(a, b, f"{actor} ({where[1]})", {a.commands[0]["main"]})
    bad += _verify_spawn_save(pickups, pair, same_old, new, romfs)
    return bad


def _verify_spawn_save(pickups, pair, same_old, new, romfs):
    """Save on spawn read back. Every drop type in `pickups` that records its check on break runs SPAWN_SAVE_NODE once
    when its AI starts (in every pack holding that AI, with only the root node changed), and its own pack's table
    has the u64 RespawnGmdHash key the node reads. Returns [problem, ...]."""
    from romtools import sarc_files, byml_load
    import ainb
    bad = []
    for actor in sorted(a_ for a_ in pickups if spawn_save_type(a_)):
        if actor not in SPAWN_SAVE:
            bad.append(f"{actor}: records its check on break but has no SPAWN_SAVE hook (its twin would come back "
                       f"at the next map change)")
            continue
        ai_file, how, table = SPAWN_SAVE[actor]
        for pack in _carriers_of(ai_file, romfs):
            a, b = pair(pack, ai_file)
            r0 = next(c["main"] for c in a.commands if c["name"] == "Root")
            r1 = next(c["main"] for c in b.commands if c["name"] == "Root")
            if how == "root":
                ok = any(_spawn_gate_ok(b, pl["node"]) for pl in b.nodes[r1]["plugs"][ainb.PLUG_CHILD])
            else:
                v_enter = [pl["node"] for pl in a.nodes[r0]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "Enter"]
                enter = [pl["node"] for pl in b.nodes[r1]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "Enter"]
                kids = [pl["node"] for pl in b.nodes[enter[0]]["plugs"][ainb.PLUG_CHILD]] if len(enter) == 1 else []
                ok = (r1 == r0 and len(enter) == 1 and len(v_enter) == 1 and b.nodes[enter[0]]["type"] == 3
                      and len(kids) == 2 and kids[0] == v_enter[0] and _spawn_gate_ok(b, kids[1]))
            if not ok:
                bad.append(f"{actor}: {pack}:{ai_file} doesn't run {SPAWN_SAVE_NODE} once at its start ({how}) for a "
                           f"drop handed a {PICKUP_CHK_KEY} bit, and only then")
            same_old(a, b, f"{actor} ({pack}:{ai_file})", {r0})
        files = sarc_files(new.read(f"Pack/Actor/{actor}.pack.zs"))
        bb = byml_load(files[table])[0] if table in files else {}
        row = next((r for r in bb.get("BlackboardParamU64Array", []) if r.get("BBKey") == "RespawnGmdHash"), None)
        if row is None or type(row["InitVal"]).__name__ != "U32" or row["InitVal"] != 0:
            bad.append(f"{actor}: no RespawnGmdHash u64 key (U32 0) in its {table}")
        if not any(r.get("BBKey") == PICKUP_CHK_KEY for r in bb.get("BlackboardParamS32Array", [])):
            bad.append(f"{actor}: no S32 {PICKUP_CHK_KEY} in its {table}")
    return bad


def _spawn_gate_ok(b, g):
    """True if node g of AI file b is the Save on spawn gate. That's a BoolSelector on QueryMathNotEqualS32(S32 = 0,
    S32Base = the actor's PICKUP_CHK_KEY), True -> SPAWN_SAVE_NODE, False -> OneshotDoNothing."""
    import ainb
    try:
        if b.nodes[g]["type"] != 7:
            return False
        kids = {pl["name"]: b.nodes[pl["node"]]["name"] or ainb.NODE_TYPES.get(b.nodes[pl["node"]]["type"])
                for pl in b.nodes[g]["plugs"][ainb.PLUG_CHILD]}
        ne = b._input(g, "Input")[1]["node"]
        if kids != {"True": SPAWN_SAVE_NODE, "False": "OneshotDoNothing"} or ne < 0 or b.nodes[ne]["name"] != "QueryMathNotEqualS32":
            return False
        k = b._input(ne, "S32")[1]
        get = b._input(ne, "S32Base")[1]["node"]
        return (k["node"] < 0 and int(k["value"]) == 0 and get >= 0 and b.nodes[get]["name"] == "QueryBlackboardGetS32"
                and b._param(get, "properties", "BlackboardType")[1]["value"] == 1
                and b._param(get, "properties", "BlackboardKey")[1]["value"] == PICKUP_CHK_KEY)
    except (KeyError, IndexError, StopIteration, TypeError):
        return False


def _carriers_of(inner, romfs):
    import packpaths
    return packpaths.carriers(inner, romfs)


# With no_collectible_hearts (parity/_drops_hearts.py) the patch points HpActor in DropGlobalParam at a green
# rupee, so every placement that drops a heart, twins included, drops a green rupee instead. The twin read-backs
# expect that.
DROP_GLOBAL = "GameParameter/DropGlobalParam/Default.game__drop__DropGlobalParam.bgyml"
HEART_DROPS = ("Obj_Heart", "Obj_Heart_InWater")
NO_HEARTS_DROP = "Obj_Rupee_Green"


def no_heart_drops(patch_dir):
    """True if the built patch makes heart drops green rupees (no_collectible_hearts), so HpActor in its
    DropGlobalParam names no heart."""
    from romtools import byml_load
    p = os.path.join(patch_dir, DROP_GLOBAL)
    if not os.path.exists(p):
        return False
    hp = (byml_load(open(p, "rb").read())[0].get("DropLotteryMasterData") or {}).get("HpActor") or ""
    return hp.split("/")[-1].split(".")[0] not in HEART_DROPS


def heartless(actor, on):
    """A vanilla placement the way no_collectible_hearts leaves it when `on` is set: a heart Drop__DropActor becomes a
    green rupee."""
    if on and (actor.get("Dynamic") or {}).get("Drop__DropActor") in HEART_DROPS:
        import copy
        actor = copy.deepcopy(actor)
        actor["Dynamic"]["Drop__DropActor"] = NO_HEARTS_DROP
    return actor


def verify_one_give(patch_dir, plan, items, romfs=DEFAULT_ROMFS, m=None):
    """OoTR gives a check's item once. Returns [problem, ...], the drop-map locations where two copies could each give
    the item. That only matters for an item a second pickup changes (not junk, not REPEATABLE_ITEMS).
    It's a problem when the copies can both exist and don't share the respawn model's bit (plan "_drops_respawn",
    every copy hides once it's set). A copy the game never creates doesn't count (its patched logic module's
    Logic_Create is a constant False). A flagless drop (plan "_drops_flag_spots") is covered by the location's one
    borrowed flag instead. Every copy drops the carrier with the location's tag, and that tag's get-scene branch
    gives nothing once the flag is set (a merged pre/post-fire Kakariko tree). See COPIES."""
    from romtools import Romfs
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import ainb
    m = m or _map()
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    spots = (plan.get("_drops_respawn") or {}).get("spots", {})
    flagged = plan.get("_drops_flag_spots") or {}
    modules = {}

    def never_created(p):
        refs = _stage_refs(os.path.dirname(p["file"])).get(str(p["hash"]), {"logic": []})
        for module, inst, _ in refs["logic"]:
            if module not in modules:
                modules[module] = ainb.Ainb(fs.raw(module))
            for n in modules[module].nodes:
                if any(x["name"] == "InstanceName" and x["value"] == inst for x in n["properties"]["string"]):
                    e = next((x for x in n["inputs"]["bool"] if x["name"] == "Logic_Create"), None)
                    if e is not None and e["node"] == -1 and e["value"] is False:
                        return True
        return False
    bad = []
    for n, it in sorted(items.items()):
        e = lookup(n, m)
        if e is None or e.get("kind") != "drop" or len(e.get("placements") or []) < 2 or it in (None, "Nothing"):
            continue
        if repeatable(it, remake_drop(it)) or n in flagged or n in (plan.get("_drops_flagless_own") or {}):
            continue  # (Flagless pickups: every copy hands the location's one bit)
        # One hash is one save row, so the same placement in two layout files (child/adult) is one copy.
        live = sorted({str(p["hash"]) for p in e["placements"] if not never_created(p)})
        if len(live) < 2:
            continue
        shared = {str(x["hash"]) for x in (spots.get(n) or {}).get("placements", [])}
        if not set(live) <= shared:
            bad.append(f"{n}: {it} can be given once per copy ({', '.join(live)}): the copies share no checked bit")
    return bad


# Missed-item respawn
# A shuffled spot's object that was broken (cut, lifted, melted, killed) while its item was left behind has to come
# back with that item, or the check is lost for good. In a built patch, every placement of a drop-map location that
# holds an item comes back when its row (GameDataList Bool64bitKey, its own hash) has a reset that clears it. That's
# the map change's bit (MAP_RESET, 1), the enemies' (256), or the area counter's (64, with an area in ExtraByte).
# A row left at 24 (or 88 with no area) never clears, so the object stays gone once broken, item taken or not.
# Placements with no row come back at every load. Flagless drops (plan "_drops_flag_spots") answer to their
# borrowed flag (verify_object_drops), and Gold Skulltula kills aren't saved (verify_pickup_save, GS_DEATH).
# With checked_on_pickup (remake_drop_contents "all"), a placement that comes back also has to leave once its item
# is taken. That's the respawn model (plan "_drops_respawn", verify_respawn reads its Presence back).
# NO_RESPAWN_MODEL lists types that can't take the model yet. Their spots hold junk only ("safe" rules) and get
# counted.
NO_RESPAWN_MODEL = {}  # empty now, the bomb boulders took the model with an AI of their own (NEW_AI_DROPPERS)


def _row_comes_back(row):
    """True if a reset ever clears this Bool64bitKey row. None means no row, and the object comes back at every load."""
    if row is None:
        return True
    t = int(row.get("ResetTypeValue", 0))
    return bool(t & (MAP_RESET | 256)) or bool(t & 64 and int(row.get("ExtraByte", 0) or 0))


def verify_flagless_own(patch_dir, plan, items, romfs=DEFAULT_ROMFS, m=None, avoid=False):
    """Reads plan "_drops_flagless_own" back (Flagless pickups). Returns ([problem], {"spots": n, "placements": n}).
    - Every flagless spot holding junk that has a quiet touch pickup of its own drops that pickup, not the carrier.
      The plan's borrowed-flag spots ("_drops_flag_spots") may only hold what can't: major items, bombchus, ice
      traps, Nothing, and with remake_avoid_vanilla_spots (`avoid`) also a pickup the spot gives in the vanilla game.
    - Each such spot has its item's pickup type and a bit of its own (>= 1, below FLAGLESS_VISIT0, used once). Each
      placement drops that type and names the bit in DROP_CHK_KEY, with no tag and no save on break. A presence
      kind's Presence is "not CHECKED_EXP" (non-lazy), and its vanilla twin (its Gyaml and Dynamic) stands there on
      "checked and not this visit". A tree names CHECKED_ARRAY in DROP_FLAG_KEY. The expressions are the plan's
      (_drops_respawn, which verify_respawn reads back from the GameDataList).
    - Every dropper type involved hands DROP_CHK_KEY to its drop (QueryBlackboardOverwriteParamAddS32 Key
      PICKUP_CHK_KEY fed by DROP_CHK_KEY). A tree type's AI also reads CHECKED_ARRAY at that index for its gate, and
      the pickup type is one the checked-on-pickup pipeline saves (verify_pickup_save reads its branch back)."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    m = m or _map()
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    rec = plan.get("_drops_flagless_own") or {}
    flag_spots = plan.get("_drops_flag_spots") or {}
    exps = (plan.get("_drops_respawn") or {}).get("exps") or {}
    cop = plan.get("_checked_on_pickup") or {}
    bad, stats, levels = [], {"spots": 0, "placements": 0}, {}
    hearts_off = no_heart_drops(patch_dir)

    def level(f):
        if f not in levels:
            levels[f] = {str(a.get("Hash")): a for a in byml_load(new.read(f))[0].get("Actors", [])}
        return levels[f]
    for n in sorted(flag_spots):
        e, it = lookup(n, m), items.get(n)
        actor = flagless_own_actor(e, it) if e else None
        if actor and not (avoid and actor in own_pickups(e)):
            bad.append(f"{n}: {it} drops the carrier at a flagless spot (its get scene starts: Link stops, no count "
                       f"popup) instead of its own touch pickup {actor}")
    bits = {}
    for n, r in sorted(rec.items()):
        e, it, actor, bit = lookup(n, m), items.get(n), r.get("actor"), r.get("bit")
        if e is None or flagless_own_actor(e, it) != actor:
            bad.append(f"{n}: {it} at this spot isn't a flagless own pickup ({actor})")
            continue
        if not isinstance(bit, int) or not 1 <= bit < FLAGLESS_VISIT0:
            bad.append(f"{n}: bit {bit!r} out of range")
            continue
        if bit in bits:
            bad.append(f"{n}: bit {bit} also used by {bits[bit]}")
        bits[bit] = n
        if n in flag_spots:
            bad.append(f"{n}: both a borrowed-flag spot and a flagless own pickup")
        (exp, steps), (texp, tsteps) = _flagless_own_exps(bit)
        stats["spots"] += 1
        if actor not in (cop.get("pickups") or []):
            bad.append(f"{n}: {actor} is not in the checked-on-pickup pickups: taking it would not record the check")
        for p in e["placements"]:
            stats["placements"] += 1
            kind = FLAGLESS_DROPPERS.get(p["actor"], (None,))[0]
            a = level(p["file"]).get(str(p["hash"])) or {}
            dyn = a.get("Dynamic") or {}
            who = f"{n} ({p['hash']})"
            if dyn.get("Drop__DropActor") != actor:
                bad.append(f"{who}: drops {dyn.get('Drop__DropActor')!r}, not {actor}")
            if dyn.get(DROP_CHK_KEY) != bit:
                bad.append(f"{who}: {DROP_CHK_KEY} {dyn.get(DROP_CHK_KEY)!r}, not its bit {bit}")
            if dyn.get(DROP_SAVE_KEY) or dyn.get(DROP_TAG_KEY):
                bad.append(f"{who}: saves at the break or carries a scene tag")
            if p["actor"] not in (cop.get("droppers") or []):
                bad.append(f"{who}: {p['actor']} is not among the checked-on-pickup droppers: no hand-over")
            if kind == "presence":
                want = {"FlagName": exp, "IsCheckLazy": False, "IsNegation": True}
                if a.get("Presence") != want:
                    bad.append(f"{who}: Presence {a.get('Presence')}, expected {want}")
                if exps.get(exp) != steps or exps.get(texp) != tsteps:
                    bad.append(f"{who}: expressions {exp}/{texp} are {exps.get(exp)}/{exps.get(texp)}, expected "
                               f"{steps}/{tsteps}")
                tw = _flagless_bit_twin(p, texp)
                t = level(p["file"]).get(tw["twin"]) or {}
                van0 = heartless(_vanilla_level(p["file"]).get(str(p["hash"])) or {}, hearts_off)
                if not t or t.get("Presence") != tw["set"]["Presence"] or t.get("Gyaml") != van0.get("Gyaml") or \
                        (t.get("Dynamic") or {}) != (van0.get("Dynamic") or {}):
                    bad.append(f"{who}: twin {tw['twin']} is {t.get('Gyaml')} with Presence {t.get('Presence')}, "
                               f"expected the vanilla object with {tw['set']['Presence']}")
            elif kind == "tree":
                if dyn.get(DROP_FLAG_KEY) != CHECKED_ARRAY:
                    bad.append(f"{who}: {DROP_FLAG_KEY} {dyn.get(DROP_FLAG_KEY)!r}, expected {CHECKED_ARRAY}")
            else:
                bad.append(f"{who}: {p['actor']} can't hold a flagless drop")
    types = sorted({p["actor"] for n in rec for p in (lookup(n, m) or {}).get("placements", [])})
    seen_ai = set()
    for actor in types:
        pk, ai_file = dropper_ai(actor)
        if (pk, ai_file) in seen_ai:
            continue
        seen_ai.add((pk, ai_file))
        try:
            files = sarc_files(new.read(pk))
            a = ainb.Ainb(files[ai_file])
        except (KeyError, FileNotFoundError, OSError):
            bad.append(f"{actor}: no {ai_file} in {pk}")
            continue

        def prop(i, key):
            return next((e["value"] for t in ainb.PTYPES for e in a.nodes[i]["properties"][t] if e["name"] == key),
                        None)

        def fed_by_chk(i, inp):
            src = next((e["node"] for t in a.nodes[i]["inputs"].values() for e in t if e["name"] == inp), -1)
            return src >= 0 and a.nodes[src]["name"] == "QueryBlackboardGetS32" and \
                prop(src, "BlackboardKey") == DROP_CHK_KEY and prop(src, "BlackboardType") == 1
        hand = any(nd["name"] == "QueryBlackboardOverwriteParamAddS32" and prop(i, "Key") == PICKUP_CHK_KEY
                   and fed_by_chk(i, "S32") for i, nd in enumerate(a.nodes))
        if not hand:
            bad.append(f"{actor} ({ai_file}): no hand-over of {DROP_CHK_KEY} to its drop's {PICKUP_CHK_KEY}")
        if FLAGLESS_DROPPERS.get(actor, (None,))[0] == "tree":
            gate = any(nd["name"] == "QueryGetNonStructGameDataBool" and fed_by_chk(i, "GameDataIndex") and
                       any(e["name"] == "GameDataFullName" and e["node"] < 0 and e["value"] == CHECKED_ARRAY
                           for e in nd["inputs"]["string"]) for i, nd in enumerate(a.nodes))
            if not gate:
                bad.append(f"{actor} ({ai_file}): its gate doesn't read {CHECKED_ARRAY}[{DROP_CHK_KEY}]")
        if DROP_TABLE in files:
            rows = {r.get("BBKey"): r for r in byml_load(files[DROP_TABLE])[0].get("BlackboardParamS32Array") or []}
            if DROP_CHK_KEY not in rows:
                bad.append(f"{pk}: its Drop table doesn't declare {DROP_CHK_KEY}")
    return bad, stats


def verify_no_lost_items(patch_dir, plan, items, romfs=DEFAULT_ROMFS, m=None):
    """Checks Missed-item respawn. Returns ([problem, ...], {type: placements}). A problem is a drop-map location
    holding an item (`items`: {location: item}) whose object's built save row never clears, so an item left behind
    is lost. With checked_on_pickup it's also one whose object comes back but isn't on the respawn model. The second
    value counts the placements of NO_RESPAWN_MODEL types left out (junk-only spots), for the summary line."""
    from romtools import Romfs, byml_load
    m = m or _map()
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    raw = fs.read("GameData/GameDataList.Product.110.byml.zs")
    try:
        raw = fs.zs.decompress(raw)
    except Exception:  # noqa: BLE001 - stored uncompressed
        pass
    rows = {int(e["Hash"]): e for e in byml_load(raw, allow_big=True)[0]["Data"]["Bool64bitKey"]}
    model = {(pl["file"], str(pl["hash"])) for s in ((plan.get("_drops_respawn") or {}).get("spots") or {}).values()
             for pl in s["placements"]}
    flag_spots = plan.get("_drops_flag_spots") or {}
    cop = bool(plan.get("_checked_on_pickup"))
    bad, left = [], {}
    for n, it in sorted(items.items()):
        e = lookup(n, m)
        if e is None or e.get("kind") != "drop" or not e.get("placements") or it in (None, "Nothing") \
                or n in flag_spots:
            continue
        for p in e["placements"]:
            if p["category"] == "gold_skulltula" or p["flag"] is None:
                continue
            row = rows.get(int(p["hash"]))
            on_model = (p["file"], str(p["hash"])) in model
            if p["actor"] in NO_RESPAWN_MODEL and not on_model:
                left[p["actor"]] = left.get(p["actor"], 0) + 1
                continue
            if not _row_comes_back(row):
                bad.append(f"{n} ({p['hash']}, {p['actor']}): {it} is lost if left behind: its row "
                           f"{row and {k: row.get(k) for k in ('ResetTypeValue', 'ExtraByte')}} never clears")
            elif cop and not on_model and not repeatable(it, remake_drop(it)):
                bad.append(f"{n} ({p['hash']}, {p['actor']}): comes back, but not on the respawn model: {it} "
                           f"could be given again")
    return bad, left


def _soul_gated(got, want, rec, souls):
    """With enemy souls (parity/extras_souls.py finalize), a gated enemy's placement and twin read "the Presence it had
    AND its soul", or just the soul flag when it had none. True if Presence `got` is `want` read that way. `souls` is
    the seed's soul expressions (plan "_extras_souls" "enemy_expressions"), None without enemy souls."""
    if not souls or not got or got.get("IsNegation"):
        return False
    if not want:
        return str(got.get("FlagName")).startswith("Rando_EnemySoul_")
    prog = souls.get(got.get("FlagName"))
    if not prog or bool(got.get("IsCheckLazy")) != bool(want.get("IsCheckLazy")):
        return False
    n = want.get("FlagName")
    inner = ([[10, n]] + ([[5]] if want.get("IsNegation") else [])) if n in rec["exps"] else _presence_steps(want)
    return (inner is not None and prog[:-2] == inner and prog[-1] == [3] and prog[-2][0] == 0
            and str(prog[-2][1]).startswith("Rando_EnemySoul_"))


def verify_respawn(patch_dir, rec, romfs=DEFAULT_ROMFS, souls=None):
    """Reads plan "_drops_respawn" back from a built patch and returns [problem, ...].
    In the GameDataList we check the bool array (saved, reset on a new file, big enough), every expression as
    planned (opcode 8 on the array), every per-object row's reset type and area, and that the save layout (MetaData)
    matches what its rows give (make_patch.gamedata_layout). Vanilla rows are otherwise unchanged.
    In the levels, each placement names its bit and Presence (and save-on-break when planned). Each twin is exactly
    its vanilla placement (its links from itself) under its new hash and Phive ID, and a BAKED_TYPES twin keeps its
    source's ID. It has its Presence, or that Presence gated by an enemy soul (_soul_gated, `souls`). No
    respawn-model placement is lost."""
    import copy
    from romtools import Romfs, byml_load, murmur3_32
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import make_patch
    van = Romfs(romfs, os.path.join(HERE, "original"))
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad = []
    hearts_off = no_heart_drops(patch_dir)  # no_collectible_hearts: a heart dropper's twin drops a green rupee

    def gd(fs):
        raw = fs.read("GameData/GameDataList.Product.110.byml.zs")
        try:
            raw = fs.zs.decompress(raw)
        except Exception:  # noqa: BLE001 - stored uncompressed
            pass
        return byml_load(raw, allow_big=True)[0]
    g, g0 = gd(new), gd(van)
    arr = next((r for r in g["Data"]["BoolArray"] if r["Hash"] == murmur3_32(rec["array"])), None)
    if arr is None or arr.get("SaveFileIndex") != 0 or arr.get("ResetTypeValue") != 8 or \
            int(arr.get("TotalSize", 0)) < rec["size"] or arr.get("DefaultValue") is not False:
        bad.append(f"GameDataList: bool array {rec['array']} {arr} (want saved, reset 8, size >= {rec['size']})")
    vis = next((r for r in g["Data"]["BoolArray"] if r["Hash"] == murmur3_32(VISIT_ARRAY)), None)
    if vis is None or vis.get("SaveFileIndex") != -1 or vis.get("ResetTypeValue") != 1 or \
            int(vis.get("TotalSize", 0)) < rec["size"] or vis.get("DefaultValue") is not False:
        bad.append(f"GameDataList: bool array {VISIT_ARRAY} {vis} (want runtime, reset 1, size >= {rec['size']})")
    for name, spot in rec["spots"].items():  # VISIT: a twin can't stand there in the visit its item was taken
        for pl in spot["placements"]:
            tp = pl.get("twin_presence")
            st = rec["exps"].get(tp["FlagName"]) if tp else None
            if tp and (tp.get("IsNegation") or st is None or st[-3:] != [[8, VISIT_ARRAY, spot["bit"]], [5], [3]]):
                bad.append(f"{name} ({pl['hash']}): its twin's Presence {tp} doesn't wait for {VISIT_ARRAY}[{spot['bit']}]")
    exps = {r["Hash"]: r for r in g["Data"]["BoolExp"]}
    for name, steps in rec["exps"].items():
        want = [[st[0]] + [murmur3_32(v) if isinstance(v, str) else v for v in st[1:]] for st in steps]
        got = exps.get(murmur3_32(name))
        if got is None or [[int(x) for x in st] for st in got["Values"]] != want:
            bad.append(f"GameDataList: expression {name} is {got and got['Values']}, want {want}")
    rows = {e["Hash"]: e for e in g["Data"]["Bool64bitKey"]}
    rows0 = {e["Hash"]: e for e in g0["Data"]["Bool64bitKey"]}
    planned = {}
    for spot in rec["spots"].values():
        for pl in spot["placements"]:
            planned.update(pl["rows"])
    for h, fields in planned.items():
        e = rows.get(int(h))
        if e is None or any(int(e.get(f, -1)) != int(v) for f, v in fields.items() if f != "new"):
            bad.append(f"GameDataList: row {h} is {e}, want {fields}")
        if fields.get("new") and int(h) in rows0:
            bad.append(f"GameDataList: row {h} planned as new but vanilla has it")
    for name, spot in sorted(rec["spots"].items()):  # Unchecked objects respawn on map changes.
        for pl in spot["placements"]:  # Presence hides them after the check.
            own = rows.get(int(pl["hash"]))
            pres = pl.get("presence") or {}
            steps = rec["exps"].get(pres.get("FlagName"))
            hides = steps is not None and (
                (pres.get("IsNegation") and steps == [[8, rec["array"], spot["bit"]]])
                or (not pres.get("IsNegation") and steps[-3:] == [[8, rec["array"], spot["bit"]], [5], [3]]))
            if own is None or not int(own.get("ResetTypeValue", 0)) & MAP_RESET or not hides:
                bad.append(f"{name} ({pl['hash']}): row {own} / Presence {pres}: not back at every map change while "
                           f"unchecked, or not kept away once checked")
    for name, spot in sorted(rec["spots"].items()):  # Vanilla respawn: a twin comes back as its pot did in vanilla
        for pl in spot["placements"]:
            if not pl.get("twin"):
                continue
            src, tw = rows0.get(int(pl["hash"])), rows.get(int(pl["twin"]))
            if src is None or tw is None or any(int(tw.get(f, -9)) != int(src.get(f, -9))
                                                for f in ("ResetTypeValue", "ExtraByte", "SaveFileIndex")):
                bad.append(f"{name} ({pl['hash']}): its twin's row {tw} isn't its own vanilla row's rule {src} "
                           f"(reset type, area, saved)")
    hs = [e["Hash"] for e in g["Data"]["Bool64bitKey"]]
    if hs != sorted(hs):
        bad.append("GameDataList: Bool64bitKey rows out of hash order")
    for h, e in rows0.items():
        got = rows.get(h)
        if str(h) in planned or got is None:
            continue
        if {k: v for k, v in got.items() if k != "ResetTypeValue"} != {k: v for k, v in e.items() if k != "ResetTypeValue"}:
            bad.append(f"GameDataList: vanilla row {h} changed beyond its reset type: {e} -> {got}")
    new_rows = {int(h) for h, f in planned.items() if f.get("new")}
    if set(rows) != set(rows0) | new_rows:
        bad.append(f"GameDataList: Bool64bitKey rows {len(rows)}, want vanilla {len(rows0)} + {len(new_rows)} new")
    have = {k: ([int(x) for x in v] if isinstance(v, list) else int(v)) for k, v in g["MetaData"].items()
            if k in ("AllDataSaveOffset", "AllDataSaveSize", "SaveDataOffsetPos", "SaveDataSize")}
    if have != make_patch.gamedata_layout(g):
        bad.append(f"GameDataList: MetaData {have} is not the layout its rows give {make_patch.gamedata_layout(g)}")
    levels = {}

    def level(fs, f):
        key = (id(fs), f)
        if key not in levels:
            levels[key] = {str(a.get("Hash")): a for a in byml_load(fs.read(f))[0]["Actors"]}
        return levels[key]
    for name, spot in sorted(rec["spots"].items()):
        for pl in spot["placements"]:
            a = level(new, pl["file"]).get(pl["hash"]) or {}
            dyn = a.get("Dynamic") or {}
            if dyn.get(DROP_CHK_KEY) != spot["bit"]:
                bad.append(f"{name} ({pl['hash']}): {DROP_CHK_KEY} {dyn.get(DROP_CHK_KEY)}, want {spot['bit']}")
            if a.get("Presence") != pl["presence"] and not _soul_gated(a.get("Presence"), pl["presence"], rec, souls):
                bad.append(f"{name} ({pl['hash']}): Presence {a.get('Presence')}, want {pl['presence']}")
            if bool(dyn.get(DROP_SAVE_KEY)) != pl["save_on_break"]:
                bad.append(f"{name} ({pl['hash']}): {DROP_SAVE_KEY} {dyn.get(DROP_SAVE_KEY)}, want {pl['save_on_break']}")
            if not pl["twin"]:
                continue
            t = level(new, pl["file"]).get(pl["twin"])
            want = heartless(copy.deepcopy(level(van, pl["file"])[pl["hash"]]), hearts_off)
            for ln in want.get("Links") or []:
                if str(ln.get("Src")) == pl["hash"]:
                    ln["Src"] = int(pl["twin"])
            want["Hash"] = int(pl["twin"])
            if isinstance((want.get("Phive") or {}).get("Placement"), dict) and "ID" in want["Phive"]["Placement"] and \
                    want.get("Gyaml") not in BAKED_TYPES:  # a baked type's twin keeps its source's ID (BAKED_TYPES)
                want["Phive"]["Placement"]["ID"] = int(pl["twin"])
            want["Presence"] = pl["twin_presence"]
            if t is not None and _soul_gated(t.get("Presence"), pl["twin_presence"], rec, souls):
                want["Presence"] = t["Presence"]  # (gated by its enemy's soul)
            if t is None:
                bad.append(f"{name} ({pl['hash']}): no twin {pl['twin']} in {pl['file']}")
            elif json.loads(json.dumps(t, default=int)) != json.loads(json.dumps(want, default=int)):
                bad.append(f"{name} ({pl['hash']}): twin {pl['twin']} is not its vanilla placement + Presence")
            key = (id(new), pl["file"], "doc")
            if key not in levels:
                levels[key] = byml_load(new.read(pl["file"]))[0]
            for grp in ("FarDeleteGroups", "SimultaneousGroups"):  # the twin takes its source's place there too
                for members in levels[key].get(grp) or []:
                    ms = {str(x) for x in members}
                    if pl["hash"] in ms and pl["twin"] not in ms:
                        bad.append(f"{name} ({pl['hash']}): twin {pl['twin']} not in its source's {grp} entry")
    for f in sorted({pl["file"] for spot in rec["spots"].values() for pl in spot["placements"]}):
        mine = {pl["hash"] for spot in rec["spots"].values() for pl in spot["placements"] if pl["file"] == f}
        twins_ = {pl["twin"] for spot in rec["spots"].values() for pl in spot["placements"]
                  if pl["file"] == f and pl["twin"]}
        extra = set(level(new, f)) - set(level(van, f)) - twins_
        if extra - {str(x) for x in extra if False}:
            # Other new actors (flagless twins and the like) are other features' business. We only report losses.
            pass
        lost = mine - set(level(new, f))  # (other features delete vanilla placements on purpose)
        if lost:
            bad.append(f"{f}: respawn-model placements lost {sorted(lost)[:5]}")
        if not twins_ <= set(level(new, f)):
            bad.append(f"{f}: twins missing {sorted(twins_ - set(level(new, f)))[:5]}")
    return bad


def _wrap_if_needed(fs, pack, ai_file):
    from romtools import sarc_files
    import ainb
    a = ainb.Ainb(sarc_files(fs.read(pack))[ai_file])
    root = a.nodes[next(c for c in a.commands if c["name"] == "Root")["main"]]
    return [] if root["type"] == 3 else [{"wrap": {"command": "Root"}}]


# Item looks (remake_item_looks "item")
# A get-scene spot shows the item it gives, the way OoTR draws the real model.
# The carrier pickup (heart piece, heart container, small key) gets an ActorHolder
# component. For its own instance name, its root AI hides its model with OneShotSetModelVisible, the node behind the
# command Dm_SY_Get uses on this very actor. Then it creates the item's display actor in the holder slot by name
# with OneShotActorHolderTryRequestCreateActorWithActorFileName, the node every chest uses for its Item_* contents.
# The slot binds the display to the carrier's Root bone (ModelBindSettings, like an NPC's cat, and all the carrier
# models have Root) and is deleted with it ("Parent"). The get scene's hide step (EventGoOffstageForUser) deletes
# it too.
# The carrier has to hide on the same tick that picks its display, or a heart piece shows for a moment when a pot
# breaks. The show branch reads the pick back through QueryBlackboardGetString, the same node that gates the
# picker, and that read can lag by one tick, so the heart piece stays visible until it catches up. That's why each
# picker leaf calls the same OneShotSetModelVisible on the carrier's first AI tick. Sharing a child node like that
# follows the vanilla graph pattern.
# Silver rupee displays
# With remake_silver_rupee_items a silver-rupee token also gives a seed item. parity/_dungeons_silver.py already
# names each token placement RandoSilver<NN>, and the room counts its tokens by its counter's links, not by Name. A
# token holding an item shows it the same way the get-scene spots do (look_ops, carrier SILVER_TOKEN, keyed on that
# Name). It keeps its sparkle (the under-water spots' rule, no ELink key killed), so it still reads as the room's
# silver rupee.
# Its root AI is a SplitTiming whose enter step the silver plugin reads (token_enter), so the look branches go
# under its Update Simultaneous (SILVER_UPDATE) and not a wrap of Root. The token has no event performer, so there's
# no get-scene hide step. Its pickup step (SILVER_PICKUP, the Simultaneous that hides it and starts its flight to
# the counter) deletes the display instead, but only if the token picked one (its look blackboard string), because
# Obj_Rupee_Silver runs the same AI file without the look holder.
SILVER_TOKEN = "Obj_RupeeToken_Silver"
SILVER_AI = "AI/Obj_Rupee_Silver.root.ainb"
SILVER_UPDATE = 29  # Root SplitTiming's "Update" child (a Simultaneous)
SILVER_PICKUP = 11  # the pickup Simultaneous (parity/_dungeons_silver.py DATA token_pickup_node)
LOOK_HOLDER = "Component/ActorHolderParam/RandoItemLook.game__component__ActorHolderParam.bgyml"
LOOK_HOLDER_SRC = ("Pack/Actor/Enemy_Scrub_ForestStage_Elder.pack.zs",
                   "Component/ActorHolderParam/Enemy_Scrub_ForestStage_Elder.game__component__ActorHolderParam.bgyml")
LOOK_SLOT = "ShopHolder"  # the Elder's one wild slot (any type by name), kept under its own name
LOOK_HIDE_COMMAND = "EventGoOffstageForUser"  # the get-scene hook's "hide the pickup" step (Dm_SY_Get Event47)
LOOK_OFFSET = (0.0, 0.0, 0.0)  # display offset from the carrier's Root bone. TODO: tune after the in-game check
# Preloading the chest's way (named holder slots) adds memory and load time to every room with a carrier. With 103
# displays it came to about 18 MB compressed. The display turned out to be asleep, so look_ops wakes it now. The
# open slot should be able to create an unloaded display by itself, so leave preloading off unless that fails.
LOOK_PRELOAD = False
# A display slot declared for preloading, with the chest holder's slot settings (Obj_TBox "Obj_DekuNut")
LOOK_PRELOAD_SLOT = {"DependencyWithHolder": 3707532803, "IsEnableModelAlphaFadeIn": False,
                     "IsEnableSleepDeleteWithHolder": True, "IsEnableWaitCreateAndIgnition": False}
LOOK_HOLDER_SET = {f"ActorHoldSettings.{LOOK_SLOT}.MaxActors": 1,
                   f"ActorHoldSettings.{LOOK_SLOT}.IsModelBind": True,
                   f"ActorHoldSettings.{LOOK_SLOT}.IsEnableSyncModelCtrlParent": False,  # don't hide with the carrier
                   f"ActorHoldSettings.{LOOK_SLOT}.ModelBindSettings": [
                       {"BoneName": "Root", "ModelBindType": 0, "RotOffset": {"X": 0.0, "Y": 0.0, "Z": 0.0},
                        "TransOffset": {"X": LOOK_OFFSET[0], "Y": LOOK_OFFSET[1], "Z": LOOK_OFFSET[2]}}]}
# Node sources. They're vanilla nodes whose parameters are constants, so none of them reads the blackboard.
LOOK_SRC = {
    "own": ({"pack": "Pack/Actor/Obj_Heart_Piece.pack.zs", "file": "AI/Obj_Heart_Piece.root.ainb"},
            {"BoolSelector": 9, "Simultaneous": 6, "OneshotDoNothing": 10}),
    "hide": ({"pack": "Pack/Actor/Obj_Heart_Piece.pack.zs", "file": GET_SCENE_AI}, {"OneShotSetModelVisible": 141}),
    "create": ({"pack": AI_GLOBAL, "file": "AI/Obj_TBox_A_01.root.ainb"},
               {"OneShotActorHolderTryRequestCreateActorWithActorFileName": 9}),
    "valid": ({"file": "AI/MiniGameNpcCommon.event.root.ainb"}, {"QueryActorHolderIsValidActorLink": 6}),
    "count": ({"pack": AI_GLOBAL, "file": "AI/Enemy_Tentacle_Red.utility.root.ainb"},
              {"QueryGetPouchContentNumByActorName": 2}),
    "less": ({"pack": "Pack/Actor/Obj_TBox_A_06.pack.zs", "file": "AI/Obj_TBox_A_06.root.ainb"},
             {"QueryMathLessS32": 30}),
    "delete": ({"pack": "Pack/Actor/Obj_HrlCity_Shop_TBox_A_01.pack.zs", "file": "AI/Obj_HrlCity_Shop_TBox_A_01.root.ainb"},
               {"OneShotActorHolderRequestDelete": 7}),
    # The disguised trap's look uses the engine's weighted random pick (constant properties, children weighted 1.0)
    "random": ({"pack": AI_GLOBAL, "file": "AI/Lizalfos.action.Strafe.module.ainb"}, {"RandomSelector": 35}),
    # a scene drop's look compares its tag (TAG_SRC "equal")
    "equal": ({"pack": AI_GLOBAL, "file": "AI/AIScheduleThreatReaction.actionseq.root.ainb"}, {"QueryMathEqualF32": 34}),
    # A holder creates its actor asleep, so we wake the display with the falling rocks' wake module and the actor's
    # position.
    "wake": ({"pack": AI_GLOBAL, "file": "AI/CancelSleepFallingRock_3.module.ainb"},
             {"OneShotActorHolderTryCancelSleepActor": 0, "QueryActorHolderGetEnableCancelSleepIndex": 3,
              "QueryMathMakeRotFromForward": 1, "QueryGenericMakeOverwriteParam": 5}),
    "pos": ({"pack": AI_GLOBAL, "file": "AI/Enemy_DungeonBoss_Morpha.action.turn_around.module.ainb"},
            {"QueryActorGetPosition": 8}),
    # the display's offset, stored by the create step and read by the bind (file-local blackboard, type 0)
    "setvec": ({"pack": AI_GLOBAL, "file": "AI/ElevatorLiftMove.module.ainb"},
               {"ExecuteBlackboardSetVec3fToBlackBoard": 85}),
    "getvec": ({"pack": AI_GLOBAL, "file": "AI/_LocalModule_8c2f0ee2e805.module.ainb"}, {"QueryBlackboardGetVec3f": 12}),
    # the chosen display's name (constant-input setter, the getter reads by key)
    "setstr": ({"pack": AI_GLOBAL, "file": "AI/Bokoblin.action.interruptsmash.module.ainb"},
               {"ExecuteBlackboardSetString": 8}),
    "getstr": ({"pack": AI_GLOBAL, "file": "AI/NpcCommon.action.GetUp.module.ainb"}, {"QueryBlackboardGetString": 8}),
    # binds the woken display to a bone (all-constant inputs here, Dodongo's copy of the node reads its blackboard)
    "bind": ({"pack": "Pack/Actor/Enemy_MiddleBoss_BigOcto.pack.zs", "file": "AI/Enemy_MiddleBoss_BigOcto.brain.root.ainb"},
             {"OneShotModelBindSetBindActorHolder": 21}),
    # killing the carrier's idle effect by its ELink key (all-constant inputs)
    "fade": ({"pack": AI_GLOBAL, "file": "AI/_LocalModule_77df65f7447e.module.ainb"}, {"OneShotXLinkFadeByKey": 6}),
}
# The carriers' idle glitter is the "Wait" key of ELink2 user Obj_Heart_Piece (asset Obj_HeartPiece_Wait_01). A
# key a carrier doesn't have is ignored.
LOOK_GLITTER_KEY = "Wait"
# Each display spins about its own center. Its offset from the bound bone is stored when the display is picked.
LOOK_OFFSET_KEY = "RandoLookOffset"  # vec3 on the carrier root AI's blackboard (BlackboardType 0)
LOOK_ACTOR_KEY = "RandoLookActor"  # the display the picker chose, same blackboard ("" = none yet, or no look)
# Type-based displays
# My call: ammo without its bag must be a Blue Rupee on the ground, as chests already give one. Our container-ammo
# pickups (RandoAmmo_*, AI.Global's DropItem.root, no placement Name, no get scene) decide by their own type when
# they appear. If the container is owned (any of parity/_ammo.py's owners in the pouch), the pickup stays as it is
# (LOOK_KEEP: the picker stores it, nothing is hidden or created). If none is owned, the pickup turns into the
# game's Obj_Rupee_Blue (LOOK_TURN, Ammo-to-rupee conversion below).
# Ammo-to-rupee conversion
# Changing the look alone wasn't enough. With no Slingshot or Bomb Bag the "Blue Rupee" popped the ammo's 0/0 and
# gave nothing. The take is the pickup's own pouch add (DefaultAutoGet, with its count popup), and the 5-rupee add
# in DropItem.root's take ("AMMO RUPEE") never went live, no build plan holds it.
# A pouch content is per type, so the pickup becomes another actor instead, the way the Kokiri butterfly becomes a
# fairy. Animal_ButterflyToFairy has a DropParam of its own whose one table names the new actor at 100 %, and its AI
# has a drop step. So each such type gets a Drop component of its own (TURN_DROP). That's a DropParam with its
# blackboard table under a path of its own, so the shared Drop table copies stay as they are, and one table naming
# Obj_Rupee_Blue at 100 %. Since it's listed, the rupee loads with the pickup.
# With no container, its AI runs one Sequential that:
# - hides it
# - saves its dropper's rows as its take does (OneShotHeartPieceTakenDeadAfter on the RespawnGmdHash it was handed,
#   since no node reads a u64 to hand that on; Save on spawn does the same)
# - hands the rupee its checked bit (QueryGenericMakeOverwriteParam -> QueryBlackboardOverwriteParamAddS32
#   PICKUP_CHK_KEY -> OneShotDropSetOverWriteParam, the same hand-over the droppers use)
# - drops it (OneShotDropDrop, as trees do)
# - deletes itself (OneShotGenericDeleteThisActor). There's no death, so no take, no pouch add and no popup.
# From there the rupee is the game's own: its look, its take sound, 5 rupees, and its take sets the spot's checked
# and visit bits (DropItem.root's take branch).
LOOK_KEEP = "RandoLookKeep"
LOOK_TURN = "RandoLookTurn"
LOOK_TYPE_AI = "AI/DropItem.root.ainb"
TURN_DROP = ("Component/DropParam/RandoAmmoTurn.game__component__DropParam.bgyml",
             "Component/Blackboard/BlackboardParamTable/RandoAmmoTurn.engine__component__BlackboardParamTable.bgyml",
             "Drop/DropTable/RandoAmmoTurn.game__drop__DropTable.bgyml",
             "Drop/DropSubTable/RandoAmmoTurn.game__drop__DropSubTable.bgyml")
TURN_DROP_SRC = ("Pack/Actor/Animal_ButterflyToFairy.pack.zs",
                 "Component/DropParam/Animal_ButterflyToFairy.game__component__DropParam.bgyml",
                 "Component/Blackboard/BlackboardParamTable/Drop.engine__component__BlackboardParamTable.bgyml",
                 "Drop/DropTable/Animal_ButterflyToFairy.game__drop__DropTable.bgyml",
                 "Drop/DropSubTable/Animal_ButterflyToFairy.game__drop__DropSubTable.bgyml")
TURN_SRC = {  # the turn's nodes as (source, node in it)
    "seq": ({"pack": "Pack/Actor/Animal_ButterflyToFairy.pack.zs", "file": "AI/Animal_ButterflyToFairy.utility.root.ainb"},
            0),  # Sequential
    "save": ({"pack": HP_PACK, "file": HP_AI}, "OneShotHeartPieceTakenDeadAfter"),
    "make": ({"pack": GS_PACK, "file": GS_AI}, "QueryGenericMakeOverwriteParam"),
    "hand": ({"pack": GS_PACK, "file": GS_AI}, "OneShotDropSetOverWriteParam"),
    "drop": ({"pack": "Pack/Actor/Obj_Tree_A_01.pack.zs", "file": "AI/Obj_Tree.root.ainb"}, "OneShotDropDrop"),
    "delete": ({"pack": AI_GLOBAL, "file": "AI/Obj_silverRupeeCounter.root.ainb"}, "OneShotGenericDeleteThisActor"),
}
# With its container the pickup stays as it is, and its new Drop component is switched off (OneShotDropSetDropValid
# with IsValid a constant false, as in TreasureBox.event.root). A pickup's Burned / Exploded / Frozen /
# LifeDepleted death drops (DropItem's DeathReasonProcedures over Default's), and it must drop nothing but its turn.
TURN_KEEP_SRC = ({"pack": AI_GLOBAL, "file": "AI/TreasureBox.event.root.ainb"}, 1)
LOOK_CENTER_Y = 0.206  # the heart piece model's center height above its Root bone (ActorInfo bounding box)
LOOK_FLOOR_CLEAR = 0.02  # a display's lowest point stays this far above the Root bone (the floor)
LOOK_BIND_BONE = "Root"  # the heart piece's only bone, the one its Rotate_Obj animation spins
# Size floor
# A display smaller than LOOK_MIN_SIZE (its largest model extent, ActorInfo ModelAabbMax - Min) is drawn scaled up
# to it, keeping its proportions, at most LOOK_MAX_SCALE times. Small models are hard to see on the ground. OotrR's
# players found the Stone of Agony (0.078 m) and the Goron Bracelet (0.108 m) nearly invisible (their Discord; their
# item_forms.py has WORLD_SIZE 0.35, MIT). The heart piece the display stands in for is 0.44 m wide, the gold token
# 0.39 m, a rupee 0.38 m.
# The scale is an input of the wake step the show branch already runs (OneShotActorHolderTryCancelSleepActor
# "Scale"), so there's no new model, texture or memory. The bind keeps it, since a bound actor's own scale is apart
# from its bind matrix (ModelBindParam IsConsiderParentScaleForBindMtx).
LOOK_MIN_SIZE = 0.35
LOOK_MAX_SCALE = 5.0  # guards against a bad bounding box, the Stone of Agony needs 4.49
LOOK_SCALE_MIN_STEP = 1.05  # smaller enlargements can't be seen: those displays are drawn as they are
LOOK_SCALE_KEY = "RandoLookScale"  # vec3 on the root AI's blackboard, the picked display's scale (1, 1, 1 = none)
# Under water a look is hard to find. In OotrR a Slingshot under Zora's River water "was only found with debug
# flight". So there the carrier keeps its idle glow, which is the game's own marker for a heart piece under water
# (as at the Zora's Fountain bottom). Everywhere else the glow still goes, because a glow around the hidden
# carrier's shape gives the carrier away (OotrR's token aura around every item, from their user report).
# A named spot (a placed pickup) is under water when a fixed water surface of its map lies LOOK_WATER_DEPTH metres
# above it (under_water). Scene drops are left out. A drop lands where it falls, and the water surfaces' boxes are
# coarse rectangles that also cover dry droppers near water (Bottom of the Well grass and boulders, a Hyrule Field
# rock under the Kakariko river's box).
LOOK_FADE_KEY = "RandoLookFade"  # string on the root AI's blackboard, the ELink key killed every frame
LOOK_KEEP_GLOW = "RandoKeepGlow"  # what an under-water spot's picker writes there: a key no ELink user has
LOOK_WATER_DEPTH = (1.0, 35.0)  # under 1 m a display (0.35 m and up) is in plain sight; the deepest look spot is the
#                                 Zora's Fountain bottom (31 m), while the Forest Temple courtyard's pool lies 39.7 m
#                                 above Phantom Ganon's heart, in another room
WATER_SURFACE = "WaterPlane"  # in a map actor's name: a water surface (shallow planes too; EftLoc_ effects excluded)
WATER_MOVING = "Dynamic"  # in a water surface's name: its level moves (the Deku Tree's B1 pool, 24 m over B2's rooms)
# Pickups whose look has a display-only twin (no AI, no pickup). The Treasure Chest Game shows these the same way.
DISPLAY_TWIN = {"Obj_Arrow_Fire": "Item_Arrow_Fire", "Obj_Bottle_Letter": "Item_Bottle_Letter",
                "Obj_MiniGame_SmallKey": "Item_Dungeon_SmallKey", "Obj_Token_Gold": "Item_Token_Gold"}
DISPLAY_EXTRA = ("Item_Ocarina_Fairy", "Item_Ocarina_Time", "Obj_Heart_Piece_MiniGame")  # no AI: display-only too
# The view of its heart piece the Treasure Chest Game prize chest uses (no AI, made to sit bound in a holder). A
# silver rupee holding a Piece of Heart shows this. A get-scene carrier is a heart piece itself and needs none.
HEART_PIECE_VIEW = "Obj_Heart_Piece_MiniGame"
ITEM_LOOKS = ("heart", "item")  # remake_item_looks


def heart_piece_carrier(actor):
    """True if get-scene carrier type `actor` is a heart piece itself (Obj_Heart_Piece, the disguise carrier), so a
    Piece of Heart there keeps the carrier's look. Any other carrier (a boss's Obj_Heart_Container, the Bottom of the
    Well's Obj_Dungeon_SmallKey) shows HEART_PIECE_VIEW for one. Otherwise a Piece of Heart on a boss's heart would
    show a heart container, and on the Bottom of the Well's key a small key."""
    return actor in ("Obj_Heart_Piece", DISGUISE_ACTOR)


def verify_heart_looks(spots, looks):
    """Checks the heart looks with remake_item_looks "item". At a get-scene spot whose carrier isn't a heart piece
    (heart_piece_carrier), a Piece of Heart shows HEART_PIECE_VIEW and an Ice Trap shows some look (its disguise).
    On a heart piece, a trap disguised as a Piece of Heart keeps the carrier's look.
    `spots` is [(location, OoTR item, drop-map entry with the get_scene the plan used)], `looks` is plan
    "_drops_looks". Returns ([problem], n spots checked)."""
    bad, n = [], 0
    for loc, it, e in spots:
        carrier = e["get_scene"].get("as") or e["placements"][0]["actor"]
        if heart_piece_carrier(carrier) or not (it == "Ice Trap" or (it or "").startswith("Piece of Heart")
                                                or it == "Nothing"):  # (Nothing: the heart-piece view, parity _display)
            continue
        n += 1
        shows = (looks.get(e["get_scene"]["name"]) or {}).get("shows") or []
        if it != "Ice Trap" and shows != [HEART_PIECE_VIEW]:
            bad.append(f"{loc}: {it} on {carrier} shows {shows or 'the carrier'}, not {HEART_PIECE_VIEW}")
        elif it == "Ice Trap" and not shows:
            bad.append(f"{loc}: Ice Trap on {carrier} shows the carrier, not its disguise")
    return bad, n


@lru_cache(maxsize=None)
def _actor_chain(actor, romfs=DEFAULT_ROMFS):
    """[(name, Components)] of an actor's ActorParam chain from its pack (empty if it has no pack)."""
    from romtools import Romfs, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rel = f"Pack/Actor/{actor}.pack.zs"
    if not os.path.exists(os.path.join(romfs, rel)):
        return ()
    return tuple((p.split("/")[1].split(".")[0], c) for p, c in _chain(sarc_files(fs.read(rel)), actor))


def display_actor(actor, romfs=DEFAULT_ROMFS):
    """The display-only actor that shows remake actor `actor`, or None if there's none. That's an Item_*/TBox_* event
    object with no pickup, what chests create and the get scene shows.
    An item Link can't hold up as it is shows its hold-up display (config/hold_up.json "show": stones, medallions,
    ocarinas, the Master Sword), so the ground look and the hold-up show the same actor. A pickup with no
    display-only twin in the game (heart container, recovery heart, silver rupee, tunics) shows one of our displays
    ("displays" 'look_for'). A display still waiting for its model (parity/_show_models.py) shows nothing yet."""
    import progressive as prog
    actor = DISPLAY_TWIN.get(actor, actor)
    for d in (prog.HOLD_SHOW.get(actor), _look_displays().get(actor), actor if actor in prog.HOLD_DISPLAYS else None):
        if d:
            return d if prog.display_available(d, romfs) else None
    chain = _actor_chain(actor, romfs)
    if not chain:
        return None
    if any(n == "Item_EventObject_Base" for n, _ in chain):
        return actor
    merged = {}
    for _, c in reversed(chain):  # the leaf's components win (a view whose base names an AI may name none)
        merged.update(c)
    if actor in DISPLAY_EXTRA and not merged.get("AIInfoRef"):
        return actor
    return None


def _look_displays():
    """{pickup actor or OoTR item-name prefix: display} from config/hold_up.json "displays" 'look_for'."""
    import progressive as prog
    return {k: d for d, spec in prog.HOLD_DISPLAYS.items() for k in spec.get("look_for") or ()}


def item_display(item, romfs=DEFAULT_ROMFS, ammo_switch=False):
    """What a get-scene spot holding OoTR item `item` shows. Returns {"actor": display}, or {"tiers": [(owned_by
    actors, display), ...]} for progressive items (OoTR shows the next tier, decided when the carrier appears), or
    None when there's no display model and the carrier keeps its own look.
    `ammo_switch` is remake_ammo_without_container "blue_rupee", for the drops plugin's looks, not the shelves. Then
    container ammo shows the Blue Rupee unless one of its container's owners is held (a tier look, see
    parity/_ammo.py and AMMO SWITCH)."""
    import progressive as prog
    if ammo_switch:
        from parity import _ammo
        own = _ammo.owners_of(_item_map().get(item) or "")
        if own:
            base, rupee = item_display(item, romfs), item_display("Rupees (5)", romfs)
            if base and rupee and "actor" in base and "actor" in rupee:
                return {"tiers": [[own, rupee["actor"]], [[], base["actor"]]]}
    if item == "Triforce Piece":  # Triforce Hunt: the display the patch makes (parity/_gaps_triforce_look.py)
        from parity import _gaps_triforce_look as triforce_look
        return {"actor": triforce_look.ACTOR}
    if item in prog.PROGRESSIVE:
        tiers = prog.PROGRESSIVE[item]["tiers"]
        shows = [display_actor(t, romfs) for t in tiers]
        if any(s is None for s in shows):
            return None
        return {"tiers": [[prog.owned_by(t), s] for t, s in zip(tiers, shows)]}
    by_name = DISPLAY_BY_NAME + tuple((k, d) for k, d in _look_displays().items() if not k.startswith(("Obj_", "Item_")))
    actor = _item_map().get(item) or next((a for p, a in by_name if item.startswith(p)), None)
    show = display_actor(actor, romfs) if actor else None
    return {"actor": show} if show else None


# Items config/item_map.json has no chest actor for, matched by the start of their OoTR name. The dungeons plugin
# gives them through scene calls (our own shuffles). Each gets the model the remake's pickups, chests or weapon show.
# More come from config/hold_up.json "displays" 'look_for' (silver rupees, recovery hearts, the Ocarina buttons).
DISPLAY_BY_NAME = (("Small Key Ring (", "Item_Dungeon_SmallKey"), ("Small Key (", "Item_Dungeon_SmallKey"),
                   ("Boss Key (", "Item_Dungeon_BossKey"), ("Map (", "Item_Dungeon_Map"),
                   ("Compass (", "Item_Dungeon_Compass"), ("Master Sword", "Weapon_Sword_Master"),
                   ("Magic Bean Pack", "Item_MagicBean"))


@lru_cache(maxsize=1)
def _item_map_cached():
    return json.load(open(os.path.join(HERE, "config", "item_map.json"), encoding="utf-8"))["items"]


def _item_map():
    return _item_map_cached()


def _root_ai(actor, romfs=DEFAULT_ROMFS):
    """The root AI file (inner path) an actor type runs: its AIInfo's RootAIRef."""
    from romtools import Romfs, sarc_files, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    files = sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))
    ref = next((c["AIInfoRef"] for _, c in _chain(files, actor) if c.get("AIInfoRef")), None)
    if not ref:
        raise DropPlanError(f"{actor}: no AIInfo")
    info = byml_load(files[ref.lstrip("?")])[0]
    return "AI/" + info["RootAIRef"].rsplit("/", 1)[-1] + "b"


def _holder_owner(actor, romfs=DEFAULT_ROMFS):
    """The ActorParam path to give ActorHolderRef so `actor` has the look holder (its own, its pack's leaf)."""
    return f"Actor/{actor}.engine__actor__ActorParam.bgyml"


def _event_ai(actor, romfs=DEFAULT_ROMFS):
    from romtools import Romfs, sarc_files, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    files = sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))
    ref = next((c["EventPerformerRef"] for _, c in _chain(files, actor) if c.get("EventPerformerRef")), None)
    if ref is None:  # no event performer (the silver-rupee token), so no get-scene hide step to edit
        return None
    p = byml_load(files[ref.lstrip("?")])[0]
    while "EventUniqueAin" not in p and p.get("$parent"):
        p = byml_load(files[p["$parent"].replace("Work/", "").replace(".gyml", ".bgyml")])[0]
    return "AI/" + p["EventUniqueAin"].rsplit("/", 1)[-1] + "b"


def _display_rows(rows, actors, romfs=DEFAULT_ROMFS):
    """Puts into `rows` (vanilla ActorInfo rows by id) the bounds the patch gives our display actors (new rows from
    config/hold_up.json "displays") and the own-route actors with a provided model (the songs,
    parity/_show_models.py)."""
    import progressive as prog
    for a in actors:
        if a in prog.HOLD_DISPLAYS and prog.display_available(a, romfs):
            rows[a] = dict(zip(("ModelAabbMin", "ModelAabbMax"), prog.display_bounds(a, lambda t: rows, romfs)))
        key = (prog.HOLD_OWN.get(a) or {}).get("model_key")
        m = prog.show_model(key, romfs) if key else None
        if m:
            rows[a] = dict(rows.get(a) or {}, ModelAabbMin=m["aabb"][0], ModelAabbMax=m["aabb"][1])


def look_offsets(actors, romfs=DEFAULT_ROMFS, scales=None):
    """{display actor: [x, y, z]}, the bind offset that puts the model's bounding-box center (RSDB ActorInfo
    ModelAabbMin/Max) on the bone's spin axis at the heart's center height, with its lowest point above the floor.
    Displays in `scales` ({actor: s}, from look_scales) are drawn s times as big about their origin, and so is
    their box."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rows = {r.get("__RowId"): r for r in byml_load(fs.read(ACTOR_INFO))[0]}
    out = {}
    from parity import _gaps_triforce_look as triforce_look  # the Triforce piece's display, its row as the patch has it
    if triforce_look.ACTOR in actors:
        rows[triforce_look.ACTOR] = dict(zip(("ModelAabbMin", "ModelAabbMax"), triforce_look.aabb(romfs)))
    _display_rows(rows, actors, romfs)
    for a in actors:
        r = rows.get(a) or {}
        mn, mx = r.get("ModelAabbMin"), r.get("ModelAabbMax")
        if not mn or not mx:
            out[a] = [0.0, 0.0, 0.0]
            continue
        s = (scales or {}).get(a, 1.0)
        cx, cy, cz = ((mn[k] + mx[k]) / 2 * s for k in "XYZ")
        y = max(LOOK_CENTER_Y - cy, LOOK_FLOOR_CLEAR - mn["Y"] * s)
        out[a] = [round(-cx, 4), round(y, 4), round(-cz, 4)]
    return out


def look_scales(actors, romfs=DEFAULT_ROMFS):
    """{display actor: s} for the displays whose largest model extent (ActorInfo box) is under LOOK_MIN_SIZE. s brings
    it up to that size, at most LOOK_MAX_SCALE (rounded to 0.01). Every other display is left out and drawn as is,
    and so is one that would grow by less than LOOK_SCALE_MIN_STEP."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rows = {r.get("__RowId"): r for r in byml_load(fs.read(ACTOR_INFO))[0]}
    from parity import _gaps_triforce_look as triforce_look  # the Triforce piece's display, its row as the patch has it
    if triforce_look.ACTOR in actors:
        rows[triforce_look.ACTOR] = dict(zip(("ModelAabbMin", "ModelAabbMax"), triforce_look.aabb(romfs)))
    _display_rows(rows, actors, romfs)
    out = {}
    for a in actors:
        r = rows.get(a) or {}
        mn, mx = r.get("ModelAabbMin"), r.get("ModelAabbMax")
        size = max(mx[k] - mn[k] for k in "XYZ") if mn and mx else 0.0
        s = round(min(LOOK_MAX_SCALE, LOOK_MIN_SIZE / size), 2) if size > 0 else 1.0
        if s >= LOOK_SCALE_MIN_STEP:
            out[a] = s
    return out


def _euler(rotate):
    """Rotation matrix of a map actor's Rotate (radians, applied X, then Y, then Z)."""
    x, y, z = (list(rotate or ()) + [0.0, 0.0, 0.0])[:3]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx, ry, rz = ((1, 0, 0), (0, cx, -sx), (0, sx, cx)), ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)), \
        ((cz, -sz, 0), (sz, cz, 0), (0, 0, 1))

    def mul(p, q):
        return tuple(tuple(sum(p[i][k] * q[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(rz, mul(ry, rx))


@lru_cache(maxsize=None)
def _water_actor_info(romfs=DEFAULT_ROMFS):
    """{actor: vanilla ActorInfo row}, read once for _water_surfaces, its only reader (a parse takes 0.1 s, 24
    scenes)."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    return {r.get("__RowId"): r for r in byml_load(fs.read(ACTOR_INFO))[0]}


@lru_cache(maxsize=None)
def _water_surfaces(scene_dir, other_age, romfs=DEFAULT_ROMFS):
    """[(translate, rotation, scale, box min, box max)] of the fixed water surfaces in every map file of `scene_dir`
    except the other age's (`other_age` in the file name). Those are map actors named *WaterPlane* but not *Dynamic*,
    with their ActorInfo model box."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rows = _water_actor_info(romfs)
    out = []
    for f in sorted(os.listdir(os.path.join(romfs, scene_dir))):
        if not f.endswith(".bcett.byml.zs") or (other_age and other_age in f):
            continue
        for a in byml_load(fs.read(f"{scene_dir}/{f}"))[0].get("Actors", []):
            name = a.get("Gyaml", "")
            row = rows.get(name) or {}
            if WATER_SURFACE not in name or WATER_MOVING in name or name.startswith("EftLoc_") \
                    or not a.get("Translate") or not row.get("ModelAabbMin") or not row.get("ModelAabbMax"):
                continue
            sc = a.get("Scale")
            sc = (float(sc),) * 3 if isinstance(sc, (int, float)) else tuple(sc[:3]) if sc else (1.0, 1.0, 1.0)
            out.append((tuple(a["Translate"][:3]), _euler(a.get("Rotate")), sc,
                        tuple(row["ModelAabbMin"][k] for k in "XYZ"), tuple(row["ModelAabbMax"][k] for k in "XYZ")))
    return tuple(out)


def under_water(placements, romfs=DEFAULT_ROMFS):
    """Whether a spot lies under water. It does if, for one of its placements ({"file", "pos"}, drop map), a fixed
    water surface of its scene covers it with its top LOOK_WATER_DEPTH above (_water_surfaces, the same age's map
    files and the shared ones). The maps don't mark any pickup as under water, so this is OotrR's test (their
    underwater.py, MIT) with moving water levels left out and tighter depth limits. The named spots it finds on the
    drop map are each checked against the map."""
    low, high = LOOK_WATER_DEPTH
    for p in placements:
        pos = p.get("pos")
        if not pos:
            continue
        base = os.path.basename(p["file"])
        other = "_Child" if "_Adult" in base else "_Adult" if "_Child" in base else None
        for t, rot, sc, mn, mx in _water_surfaces(os.path.dirname(p["file"]), other, romfs):
            d = [pos[i] - t[i] for i in range(3)]
            local = [sum(rot[k][i] * d[k] for k in range(3)) / (sc[i] or 1.0) for i in range(3)]
            if mn[0] <= local[0] <= mx[0] and mn[2] <= local[2] <= mx[2] \
                    and low < (mx[1] - local[1]) * abs(sc[1] or 1.0) <= high:
                return True
    return False


def look_ops(spots, romfs=DEFAULT_ROMFS, wrapped=(), disguise=None, attach=None, pickup_delete=None,
             type_looks=None):
    """make_patch sections that show each get-scene spot's item.
    `spots` is [{"name": placement Name, "carrier": the spot's pickup type, "display": item_display(...)}]. Spots
    without a display keep their carrier's look and are left out. `wrapped` lists root AI files an earlier op of the
    same plan already wrapped in a Simultaneous.
    `disguise` is {"actor": DISGUISE_ACTOR, "displays": [item_display(...)], "skip": [Names], "tags": {tag:
    item_display(...)}}. A carrier whose PICKUP_TAG_KEY is a scene drop's tag shows that spot's item (hidden model,
    display created once, per tag). An untagged one (0) goes on to `skip` and the disguised ice trap's look, OoTR's
    looks_like_item. A dropped carrier has no placement Name to pick a look by. So after the named spots and `skip`
    (names its own placements may carry, which keep their look), the carrier's root AI checks the actor's own type
    (QueryGenericGetOwnActorLink -> QueryGenericGetActorName, as the get scene's fallthrough). For that type it hides
    the model and, when the carrier appears, creates one of `displays` picked by a RandomSelector (weights 1.0).
    Every file is written the same into every pack holding its path ("pack": "*").
    A display smaller than LOOK_MIN_SIZE is woken scaled up (look_scales, its picker leaf stores the scale). A spot
    with "water" true (under_water) keeps the carrier's own idle glow, because its picker leaf names LOOK_KEEP_GLOW
    as the key to kill. Both keys exist only in root AIs that use them.
    `attach` ({root AI: node}) puts that AI's look branches under that node (the silver token's Update Simultaneous)
    instead of a Simultaneous wrapped around Root. With `pickup_delete` ({root AI: node}) that node (the token's
    pickup step) also deletes the display, for a carrier that showed one (Silver rupee displays).
    `type_looks` is {"ai": root AI, "looks": {actor type: item_display spec, a tier may be LOOK_KEEP}}. Pickups of
    those types pick their look by their own type (Type-based displays, their holder comes from ammo_type_ops)."""
    import packpaths
    from romtools import Romfs, sarc_files
    import ainb
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    spots = sorted((s for s in spots if s.get("display")), key=lambda s: s["name"])
    out = {"packs": [], "ainb": []}
    if disguise is not None and not disguise.get("displays") and not disguise.get("tags"):
        disguise = None
    type_looks = type_looks if type_looks and type_looks.get("looks") else None
    if not spots and disguise is None and type_looks is None:
        return out
    if len({s["name"] for s in spots}) != len(spots):
        raise DropPlanError("item looks: two spots share a name")
    src = {k: v[0] for k, v in LOOK_SRC.items()}

    def idx(key, name):
        return LOOK_SRC[key][1][name]

    # The holder. Every carrier type's ActorParam names the look holder, and the holder file (a copy of the Elder's,
    # slot bound to the Root bone) goes in every pack holding that ActorParam.
    carriers = [s["carrier"] for s in spots] + ([disguise["actor"]] if disguise else [])
    owners = sorted({_holder_owner(c, romfs) for c in carriers})
    # With preloading on, each possible display gets a named slot so it loads with the carrier. The wild slot
    # creates loaded actors by name. All carrier packs share this holder file, so we take the union.
    shown = set().union(*(_shows(s["display"]) for s in spots), *(
        _shows(d) for d in ((disguise or {}).get("displays") or [])), *(
        _shows(d) for d in ((disguise or {}).get("tags") or {}).values()), *(
        _shows(d) for d in ((type_looks or {}).get("looks") or {}).values())) - {LOOK_KEEP, LOOK_TURN}
    scales = look_scales(shown, romfs)
    offsets = look_offsets(shown, romfs, scales)
    holder_set = dict(LOOK_HOLDER_SET)
    for actor in sorted(shown) if LOOK_PRELOAD else ():
        holder_set[f"ActorHoldSettings.{actor}"] = dict(
            LOOK_PRELOAD_SLOT, Actor=f"Work/Actor/{actor}.engine__actor__ActorParam.gyml")
    for path in owners:
        out["packs"].append({"pack": "*", "file": path,
                             "set": {"Components.ActorHolderRef": "?" + LOOK_HOLDER}})
        for pk in packpaths.carriers(path, romfs):
            out["packs"].append({"pack": pk, "file": LOOK_HOLDER, "from_pack": LOOK_HOLDER_SRC[0],
                                 "new_from": LOOK_HOLDER_SRC[1], "set": holder_set})
    by_ai = defaultdict(list)
    for s in spots:
        by_ai[_root_ai(s["carrier"], romfs)].append(s)
    dis_ai = _root_ai(disguise["actor"], romfs) if disguise else None
    if dis_ai:
        by_ai.setdefault(dis_ai, [])
    type_ai = type_looks["ai"] if type_looks else None
    if type_ai:
        if type_ai == dis_ai:
            raise DropPlanError(f"item looks: {type_ai} is both the disguise carrier's AI and the type looks'")
        by_ai.setdefault(type_ai, [])
    for ai_file, group in sorted(by_ai.items()):
        a = ainb.Ainb(sarc_files(fs.read(packpaths.carriers(ai_file, romfs)[0]))[ai_file])
        root = a.nodes[next(c for c in a.commands if c["name"] == "Root")["main"]]
        edits = [] if root["type"] == 3 or ai_file in wrapped or ai_file in (attach or {}) else [
            {"wrap": {"command": "Root"}}]
        top = (attach or {}).get(ai_file, "@Root")  # where the picker and the show branch go
        edits += [{"add_bb": {"type": "vec3", "name": LOOK_OFFSET_KEY, "default": [0.0, 0.0, 0.0]}},
                  {"add_bb": {"type": "string", "name": LOOK_ACTOR_KEY, "default": ""}}]
        here = ([d for d in disguise.get("displays") or []] + list((disguise.get("tags") or {}).values())
                if ai_file == dis_ai else [])
        sized = any(x in scales for x in set().union(*(_shows(s["display"]) for s in group), *map(_shows, here)))
        wet = any(s.get("water") for s in group)
        if sized:  # the picked display's scale (look_scales), read by the wake step
            edits.append({"add_bb": {"type": "vec3", "name": LOOK_SCALE_KEY, "default": [1.0, 1.0, 1.0]}})
        if wet:  # the ELink key the show branch kills, the glitter or none at an under-water spot
            edits.append({"add_bb": {"type": "string", "name": LOOK_FADE_KEY, "default": LOOK_GLITTER_KEY}})
        name_i, eq_i = _name_sources(fs)
        edits.append({"copy": {"from": GS_NAME_SRC, "nodes": [name_i], "label": "lname", "follow": False}})
        name_ref = f"lname:{name_i}"
        n = {"k": 0}

        def node(key, name, bb=None):
            n["k"] += 1
            lab = f"lk{n['k']}"
            edits.append({"copy": {"from": src[key], "nodes": [idx(key, name)], "label": lab, "follow": False}})
            ref = f"{lab}:{idx(key, name)}"
            bb = bb or {"getvec": LOOK_OFFSET_KEY, "setvec": LOOK_OFFSET_KEY, "getstr": LOOK_ACTOR_KEY,
                        "setstr": LOOK_ACTOR_KEY}.get(key)
            if bb:  # the AI's own blackboard (type 0)
                edits.extend([{"set_property": {"node": ref, "name": "BlackboardType", "value": 0}},
                              {"set_property": {"node": ref, "name": "BlackboardKey", "value": bb}}])
                if key.startswith("set"):
                    edits.append({"set_property": {"node": ref, "name": "ExecuteOnce", "value": True}})
            return ref

        def streq(value, feed_from, output):
            lab = f"leq{n['k']}"
            n["k"] += 1
            q = f"{lab}:{eq_i}"
            edits.extend([{"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": lab, "follow": False}},
                          {"set_input": {"node": q, "name": "StringB", "value": value}},
                          {"feed": {"from": feed_from, "output": output, "to": q, "input": "StringA"}}])
            return q

        early = {}  # the picker's own hide, one node every leaf shares (First-tick hide)

        def pick(actor, water=False):
            """A picker leaf. It writes the display's name and centering offset into the blackboard (once), its scale if
            it has one, and LOOK_KEEP_GLOW as the key to kill at an under-water spot. It also hides the carrier right
            there (First-tick hide). For LOOK_KEEP (Type-based displays) only that name is stored and the pickup keeps
            its own model. For LOOK_TURN the pickup turns into the Blue Rupee (Ammo-to-rupee conversion,
            _turn_edits)."""
            if actor == LOOK_TURN:
                k = n["k"]
                n["k"] += 1
                more, seq = _turn_edits(fs, f"tt{k}")
                edits.extend(more)
                return seq
            if actor == LOOK_KEEP:  # and its turn's Drop component off (TURN_KEEP_SRC)
                ss, sim = node("setstr", "ExecuteBlackboardSetString"), node("own", "Simultaneous")
                k = n["k"]
                n["k"] += 1
                vsrc, vi = TURN_KEEP_SRC
                off = f"tkv{k}:{vi}"
                edits.extend([{"set_input": {"node": ss, "name": "String", "value": LOOK_KEEP}},
                              {"copy": {"from": vsrc, "nodes": [vi], "label": f"tkv{k}", "follow": False}},
                              {"set_input": {"node": off, "name": "IsValid", "value": False}},
                              {"add_child": {"parent": sim, "child": ss}},
                              {"add_child": {"parent": sim, "child": off}}])
                return sim
            ss, sv, sim = node("setstr", "ExecuteBlackboardSetString"), node("setvec",
                                                                             "ExecuteBlackboardSetVec3fToBlackBoard"), \
                node("own", "Simultaneous")
            if "hide" not in early:
                early["hide"] = node("hide", "OneShotSetModelVisible")
                edits.append({"set_input": {"node": early["hide"], "name": "Bool", "value": False}})
            edits.extend([{"set_input": {"node": ss, "name": "String", "value": actor}},
                          {"set_input": {"node": sv, "name": "Vector", "value": offsets.get(actor, [0.0, 0.0, 0.0])}},
                          {"add_child": {"parent": sim, "child": early["hide"]}},
                          {"add_child": {"parent": sim, "child": ss}},
                          {"add_child": {"parent": sim, "child": sv}}])
            if actor in scales:
                sc = node("setvec", "ExecuteBlackboardSetVec3fToBlackBoard", LOOK_SCALE_KEY)
                edits.extend([{"set_input": {"node": sc, "name": "Vector", "value": [scales[actor]] * 3}},
                              {"add_child": {"parent": sim, "child": sc}}])
            if water:
                fk = node("setstr", "ExecuteBlackboardSetString", LOOK_FADE_KEY)
                edits.extend([{"set_input": {"node": fk, "name": "String", "value": LOOK_KEEP_GLOW}},
                              {"add_child": {"parent": sim, "child": fk}}])
            return sim

        def owned(actor, yes, no):
            cnt = node("count", "QueryGetPouchContentNumByActorName")
            less = node("less", "QueryMathLessS32")
            sel = node("own", "BoolSelector")
            edits.extend([{"set_input": {"node": cnt, "name": "ActorName", "value": actor}},
                          {"feed": {"from": cnt, "output": "Num", "to": less, "input": "S32Base"}},
                          {"feed": {"from": less, "output": "Bool", "to": sel, "input": "Input"}},
                          {"add_child": {"parent": sel, "child": yes, "name": "True"}},
                          {"add_child": {"parent": sel, "child": no, "name": "False"}}])
            return sel

        def pick_tree(disp, water=False):
            if "actor" in disp:
                return pick(disp["actor"], water)
            tiers, top = disp["tiers"], len(disp["tiers"]) - 1
            nxt = pick(tiers[0][1], water)  # nothing owned: the first tier
            for k in range(top + 1):  # built bottom-up: the highest tier is checked first
                for actor in reversed(tiers[k][0]):
                    nxt = owned(actor, pick(tiers[min(k + 1, top)][1], water), nxt)
            return nxt

        # The picker decides which display, if any. Named spots first, then the carrier's tag or own type.
        chain = []
        for s in group:
            sel = node("own", "BoolSelector")
            edits.extend([{"feed": {"from": streq(s["name"], name_ref, "InstanceName"), "output": "IsEqual",
                                    "to": sel, "input": "Input"}},
                          {"add_child": {"parent": sel, "child": pick_tree(s["display"], bool(s.get("water"))),
                                         "name": "True"}}])
            chain.append(sel)
        if ai_file == type_ai:  # Type-based displays: after the named spots, the pickup's own type
            town_i, tan_i = _actor_name_sources(fs)
            edits.extend([
                {"copy": {"from": GS_NAME_SRC, "nodes": [town_i], "label": "tself", "follow": False}},
                {"copy": {"from": GS_NAME_SRC, "nodes": [tan_i], "label": "tactor", "follow": False}},
                {"link": {"from": f"tself:{town_i}", "output": "Actor", "to": f"tactor:{tan_i}", "input": "Actor"}}])
            for t, d in sorted(type_looks["looks"].items()):
                sel = node("own", "BoolSelector")
                edits.extend([{"feed": {"from": streq(t, f"tactor:{tan_i}", "ActorFileName"), "output": "IsEqual",
                                        "to": sel, "input": "Input"}},
                              {"add_child": {"parent": sel, "child": pick_tree(d), "name": "True"}}])
                chain.append(sel)
        closed = set()  # chain selectors whose False case is already set
        sub = []  # untagged carriers: the carrier's own named placements keep their look, then the disguised trap
        if ai_file == dis_ai:
            named = {s["name"] for s in group}
            for nm in (sorted(set(disguise.get("skip", ())) - named) if disguise.get("displays") else []):
                sel, idle = node("own", "BoolSelector"), node("own", "OneshotDoNothing")
                edits.extend([{"feed": {"from": streq(nm, name_ref, "InstanceName"), "output": "IsEqual",
                                        "to": sel, "input": "Input"}},
                              {"add_child": {"parent": sel, "child": idle, "name": "True"}}])
                sub.append(sel)
        if ai_file == dis_ai and disguise.get("displays"):
            own_i, an_i = _actor_name_sources(fs)
            edits.extend([
                {"copy": {"from": GS_NAME_SRC, "nodes": [own_i], "label": "lself", "follow": False}},
                {"copy": {"from": GS_NAME_SRC, "nodes": [an_i], "label": "lactor", "follow": False}},
                {"link": {"from": f"lself:{own_i}", "output": "Actor", "to": f"lactor:{an_i}", "input": "Actor"}}])
            sel, rnd = node("own", "BoolSelector"), node("random", "RandomSelector")
            edits.extend([{"feed": {"from": streq(disguise["actor"], f"lactor:{an_i}", "ActorFileName"),
                                    "output": "IsEqual", "to": sel, "input": "Input"}},
                          {"add_child": {"parent": sel, "child": rnd, "name": "True"}}])
            for d in disguise["displays"]:
                edits.append({"add_child": {"parent": rnd, "child": pick_tree(d), "weight": 1.0}})
            sub.append(sel)
        if ai_file == dis_ai and disguise.get("tags"):
            # tag 0 is untagged (sub), any other tag shows that tag's display
            more, get = _tag_get("ltag", PICKUP_TAG_KEY)
            edits += more

            def equal(value):
                q = node("equal", "QueryMathEqualF32")
                edits.extend([{"set_input": {"node": q, "name": "S32Base", "value": float(value)}},
                              {"feed": {"from": get, "output": "F32", "to": q, "input": "F32"}}])
                return q
            usel, zero = node("own", "BoolSelector"), equal(0)
            tchain = []
            for t, d in sorted(disguise["tags"].items()):
                sel = node("own", "BoolSelector")
                edits.extend([{"feed": {"from": equal(t), "output": "Bool", "to": sel, "input": "Input"}},
                              {"add_child": {"parent": sel, "child": pick_tree(d), "name": "True"}}])
                tchain.append(sel)
            tnone, unone = node("own", "OneshotDoNothing"), node("own", "OneshotDoNothing")
            for c, nxt in zip(tchain, tchain[1:] + [tnone]):
                edits.append({"add_child": {"parent": c, "child": nxt, "name": "False"}})
            for c, nxt in zip(sub, sub[1:] + [unone]):
                edits.append({"add_child": {"parent": c, "child": nxt, "name": "False"}})
            edits.extend([{"feed": {"from": zero, "output": "Bool", "to": usel, "input": "Input"}},
                          {"add_child": {"parent": usel, "child": sub[0] if sub else unone, "name": "True"}},
                          {"add_child": {"parent": usel, "child": tchain[0] if tchain else tnone, "name": "False"}}])
            chain.append(usel)
            closed.add(usel)
        elif ai_file == dis_ai:
            chain += sub
        rest = node("own", "OneshotDoNothing")
        for c, nxt in zip(chain, chain[1:] + [rest]):
            if c not in closed:
                edits.append({"add_child": {"parent": c, "child": nxt, "name": "False"}})
        # The picker runs until a display is chosen. Then the one show branch works from the blackboard.
        got = node("getstr", "QueryBlackboardGetString")
        empty = streq("", got, "String")
        pgate, pidle = node("own", "BoolSelector"), node("own", "OneshotDoNothing")
        gsel, gidle = node("own", "BoolSelector"), node("own", "OneshotDoNothing")
        sim, hide = node("own", "Simultaneous"), node("hide", "OneShotSetModelVisible")
        valid, vsel = node("valid", "QueryActorHolderIsValidActorLink"), node("own", "BoolSelector")
        create = node("create", "OneShotActorHolderTryRequestCreateActorWithActorFileName")
        q = node("wake", "QueryActorHolderGetEnableCancelSleepIndex")
        wsel = node("own", "BoolSelector")
        cs = node("wake", "OneShotActorHolderTryCancelSleepActor")
        pos, rot = node("pos", "QueryActorGetPosition"), node("wake", "QueryMathMakeRotFromForward")
        ow, bind = node("wake", "QueryGenericMakeOverwriteParam"), node("bind", "OneShotModelBindSetBindActorHolder")
        fade = node("fade", "OneShotXLinkFadeByKey")
        shown_case = sim
        if ai_file == type_ai:  # LOOK_KEEP needs no display. Ammo that turned has already been deleted.
            ksel, kidle = node("own", "BoolSelector"), node("own", "OneshotDoNothing")
            edits.extend([{"feed": {"from": streq(LOOK_KEEP, got, "String"), "output": "IsEqual", "to": ksel,
                                    "input": "Input"}},
                          {"add_child": {"parent": ksel, "child": kidle, "name": "True"}},
                          {"add_child": {"parent": ksel, "child": sim, "name": "False"}}])
            shown_case = ksel
        edits.extend([
            {"feed": {"from": empty, "output": "IsEqual", "to": pgate, "input": "Input"}},
            {"add_child": {"parent": pgate, "child": chain[0], "name": "True"}},
            {"add_child": {"parent": pgate, "child": pidle, "name": "False"}},
            {"feed": {"from": empty, "output": "IsEqual", "to": gsel, "input": "Input"}},
            {"add_child": {"parent": gsel, "child": gidle, "name": "True"}},
            {"add_child": {"parent": gsel, "child": shown_case, "name": "False"}},
            # The carrier hides and its idle glitter goes, every frame while the display stands in for it. At an
            # under-water spot the key comes from the blackboard (LOOK_KEEP_GLOW) and the glitter stays.
            {"set_input": {"node": hide, "name": "Bool", "value": False}},
            {"set_input": {"node": fade, "name": "KeyName", "value": LOOK_GLITTER_KEY}},
            {"set_input": {"node": fade, "name": "IsELink", "value": True}},
            {"set_input": {"node": fade, "name": "IsSLink", "value": False}},
            {"set_input": {"node": fade, "name": "IsKill", "value": True}},
            {"set_property": {"node": fade, "name": "ExecuteEveryFrame", "value": True}},
            # no display yet, so create the one the picker named
            {"set_input": {"node": valid, "name": "key", "value": LOOK_SLOT}},
            {"feed": {"from": valid, "output": "Bool", "to": vsel, "input": "Input"}},
            {"set_input": {"node": create, "name": "Key", "value": LOOK_SLOT}},
            {"feed": {"from": got, "output": "String", "to": create, "input": "ActorFileName"}},
            # It's created asleep, so wake it at the carrier, then bind it to the spinning bone with its centering
            # offset.
            {"set_input": {"node": q, "name": "Key", "value": LOOK_SLOT}},
            {"feed": {"from": q, "output": "IsExist", "to": wsel, "input": "Input"}},
            {"set_input": {"node": cs, "name": "Key", "value": LOOK_SLOT}},
            {"feed": {"from": q, "output": "Index", "to": cs, "input": "Index"}},
            {"set_property": {"node": cs, "name": "ExecuteEveryFrame", "value": True}},
            {"link": {"from": pos, "output": "Position", "to": cs, "input": "Pos"}},
            {"set_input": {"node": rot, "name": "Vector", "value": [0.0, 0.0, 1.0]}},
            {"link": {"from": rot, "output": "Mat33F", "to": cs, "input": "Rot"}},
            {"link": {"from": ow, "output": "OverwriteParam", "to": cs, "input": "OverwriteParam"}},
            {"set_input": {"node": bind, "name": "ActorHolderKey", "value": LOOK_SLOT}},
            {"set_input": {"node": bind, "name": "ActorHolderIndex", "value": 0}},
            {"set_input": {"node": bind, "name": "BindBoneName", "value": LOOK_BIND_BONE}},
            {"link": {"from": node("getvec", "QueryBlackboardGetVec3f"), "output": "Vector", "to": bind,
                      "input": "TransOffset"}},
            {"add_child": {"parent": wsel, "child": cs, "name": "True"}},
            {"add_child": {"parent": wsel, "child": bind, "name": "False"}},
            {"add_child": {"parent": vsel, "child": wsel, "name": "True"}},
            {"add_child": {"parent": vsel, "child": create, "name": "False"}},
            {"add_child": {"parent": sim, "child": hide}},
            {"add_child": {"parent": sim, "child": fade}},
            {"add_child": {"parent": sim, "child": vsel}},
            {"add_child": {"parent": top, "child": pgate}},
            {"add_child": {"parent": top, "child": gsel}}])
        if ai_file in (pickup_delete or {}):  # Silver rupee displays: a taken token deletes its display if it had one
            psel, pnone = node("own", "BoolSelector"), node("own", "OneshotDoNothing")
            pdel = node("delete", "OneShotActorHolderRequestDelete")
            edits.extend([{"set_input": {"node": pdel, "name": "Key", "value": LOOK_SLOT}},
                          {"feed": {"from": empty, "output": "IsEqual", "to": psel, "input": "Input"}},
                          {"add_child": {"parent": psel, "child": pnone, "name": "True"}},
                          {"add_child": {"parent": psel, "child": pdel, "name": "False"}},
                          {"add_child": {"parent": pickup_delete[ai_file], "child": psel}}])
        if sized:  # woken at the picked display's scale (1, 1, 1 unless its picker leaf stored one)
            edits.append({"link": {"from": node("getvec", "QueryBlackboardGetVec3f", LOOK_SCALE_KEY), "output": "Vector",
                                   "to": cs, "input": "Scale"}})
        if wet:  # the key killed every frame, the glitter by default or LOOK_KEEP_GLOW (nothing) under water
            edits.append({"feed": {"from": node("getstr", "QueryBlackboardGetString", LOOK_FADE_KEY), "output": "String",
                                   "to": fade, "input": "KeyName"}})
        out["ainb"].append({"pack": "*", "file": ai_file, "edits": edits})
    # The get scene's hide step deletes the display too (EventGoOffstageForUser: ExecuteGoOffstage + a delete).
    for ev in sorted({_event_ai(c, romfs) for c in carriers} - {None}):
        a = ainb.Ainb(sarc_files(fs.read(packpaths.carriers(ev, romfs)[0]))[ev])
        cmd = next(c for c in a.commands if c["name"] == LOOK_HIDE_COMMAND)["main"]
        (old,) = [pl["node"] for pl in a.nodes[cmd]["plugs"][ainb.PLUG_CHILD]]
        edits = [{"copy": {"from": src["own"], "nodes": [idx("own", "Simultaneous")], "label": "gsim", "follow": False}},
                 {"copy": {"from": src["delete"], "nodes": [idx("delete", "OneShotActorHolderRequestDelete")],
                           "label": "gdel", "follow": False}}]
        sim, dele = f"gsim:{idx('own', 'Simultaneous')}", f"gdel:{idx('delete', 'OneShotActorHolderRequestDelete')}"
        edits += [{"set_input": {"node": dele, "name": "Key", "value": LOOK_SLOT}},
                  {"add_child": {"parent": sim, "child": old}},
                  {"add_child": {"parent": sim, "child": dele}}]
        if ev in GATED_HIDE:  # other pickups run this event AI too, so only these names get the delete
            # Every other actor goes on to the vanilla step itself, through a BoolSelector chain on its instance name.
            names = sorted({s["name"] for s in spots if _event_ai(s["carrier"], romfs) == ev})
            name_i, eq_i = _name_sources(fs)
            edits.append({"copy": {"from": GS_NAME_SRC, "nodes": [name_i], "label": "ghname", "follow": False}})
            nxt = old
            for k, nm in reversed(list(enumerate(names))):
                q, b = f"gheq{k}:{eq_i}", f"ghsel{k}:{idx('own', 'BoolSelector')}"
                edits += [{"copy": {"from": GS_EQUAL_SRC, "nodes": [eq_i], "label": f"gheq{k}", "follow": False}},
                          {"set_input": {"node": q, "name": "StringB", "value": nm}},
                          {"feed": {"from": f"ghname:{name_i}", "output": "InstanceName", "to": q, "input": "StringA"}},
                          {"copy": {"from": src["own"], "nodes": [idx("own", "BoolSelector")], "label": f"ghsel{k}",
                                    "follow": False}},
                          {"feed": {"from": q, "output": "IsEqual", "to": b, "input": "Input"}},
                          {"add_child": {"parent": b, "child": sim, "name": "True"}},
                          {"add_child": {"parent": b, "child": nxt, "name": "False"}}]
                nxt = b
            edits.append({"set_child": {"parent": f"@{LOOK_HIDE_COMMAND}", "which": "Execute", "child": nxt}})
        else:
            edits.append({"set_child": {"parent": f"@{LOOK_HIDE_COMMAND}", "which": "Execute", "child": sim}})
        out["ainb"].append({"pack": "*", "file": ev, "edits": edits})
    return out


def verify_silver_items(plan, items):
    """Silver rupee displays cover every item. Every silver rupee spot whose location holds an item must name a look
    for its token in plan "_drops_looks_silver". Silver rupees holding a heart or a Rupees (5) showed nothing, and
    so did an Ice Trap whose drawn look had no model. Returns ([problem], n spots with an item)."""
    from parity import _dungeons_silver as silver
    looks = (plan.get("_drops_looks_silver") or {}).get("looks") or {}
    bad, n = [], 0
    for _puzzle, _k, name, token, _hashes in silver.spots():
        it = items.get(name)
        if not it:
            continue
        n += 1
        if not (looks.get(token) or {}).get("shows"):
            bad.append(f"{name} ({token}) holds {it} but shows nothing inside the silver rupee")
    return bad, n


def verify_silver_looks(patch_dir, silver, romfs=DEFAULT_ROMFS):
    """Reads Silver rupee displays back (plan "_drops_looks_silver"). The pickers themselves are read by verify_looks
    with the plan's other looks. In every pack holding the token AI, Root still starts at its SplitTiming (the
    silver plugin's token_enter), its Update step holds the look's picker gate and show branch, and its pickup step
    deletes the display when the token picked one. The token type's ActorParam names the look holder. Returns
    [problem]."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    import packpaths
    out = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch_dir])
    bad = []
    for pk in packpaths.carriers(silver["ai"], romfs):
        a = ainb.Ainb(sarc_files(out.read(pk))[silver["ai"]])
        rt = next(c for c in a.commands if c["name"] == "Root")["main"]
        if ainb.NODE_TYPES.get(a.nodes[rt]["type"]) != "SplitTiming" or a.nodes[rt]["plugs"][ainb.PLUG_CHILD][1]["node"] \
                != silver["update"]:
            bad.append(f"{pk} {silver['ai']}: Root no longer starts at the token's SplitTiming")
        kids = [pl["node"] for pl in a.nodes[silver["update"]]["plugs"][ainb.PLUG_CHILD]]

        def fed_by_pick(j):
            m = a.nodes[j]
            if ainb.NODE_TYPES.get(m["type"]) != "BoolSelector" or not m["inputs"]["bool"]:
                return False
            q = m["inputs"]["bool"][0]["node"]
            if q < 0 or a.nodes[q]["name"] != "QueryStringIsEqual":
                return False
            src = {e["name"]: e for e in a.nodes[q]["inputs"]["string"]}["StringA"]["node"]
            return src >= 0 and {e["name"]: e["value"] for t in ainb.PTYPES for e in a.nodes[src]["properties"][t]}\
                .get("BlackboardKey") == LOOK_ACTOR_KEY
        if sum(1 for j in kids if fed_by_pick(j)) < 2:
            bad.append(f"{pk} {silver['ai']}: the Update step doesn't run the look's picker and show branch")
        dele = []
        for j in (pl["node"] for pl in a.nodes[silver["pickup"]]["plugs"][ainb.PLUG_CHILD]):
            if fed_by_pick(j):
                f = next((pl["node"] for pl in a.nodes[j]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "False"), -1)
                if f >= 0 and a.nodes[f]["name"] == "OneShotActorHolderRequestDelete" and \
                        {e["name"]: e["value"] for t in ainb.PTYPES for e in a.nodes[f]["inputs"][t]}.get("Key") \
                        == LOOK_SLOT:
                    dele.append(j)
        if len(dele) != 1:
            bad.append(f"{pk} {silver['ai']}: the pickup step deletes the display {len(dele)} times (want 1)")
    path = _holder_owner(SILVER_TOKEN, romfs)
    for pk in packpaths.carriers(path, romfs):
        files = sarc_files(out.read(pk))
        if (byml_load(files[path])[0].get("Components") or {}).get("ActorHolderRef") != "?" + LOOK_HOLDER \
                or LOOK_HOLDER not in files:
            bad.append(f"{pk}: {SILVER_TOKEN} has no look holder")
    return bad


def verify_looks(patch_dir, looks, romfs=DEFAULT_ROMFS, disguise=None, tag_looks=None, water=None):
    """Reads a built patch back for plan["_drops_looks"] ({name: {"carrier", "shows": [display actors]}}) and returns
    [problem, ...]. Empty means every carrier type has the look holder, the holder file is the Elder's slot bound to
    the Root bone in every pack holding the ActorParam, each root AI is the same in every pack and creates exactly
    the planned display actors for each name, and the get scene's hide step deletes the display. `water` is plan
    "_drops_looks_water", for the size floor and under-water glow check (_verify_look_aids)."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    import packpaths
    out = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch_dir])
    bad = _verify_look_aids(out, looks, romfs, disguise, tag_looks, water)
    if disguise:
        bad += _verify_disguise_look(out, disguise, romfs, set(looks))
    # With preloading on, each possible display needs a slot that loads it with the carrier.
    wanted = set().union(*(set(lk["shows"]) for lk in looks.values()), set((disguise or {}).get("shows") or ()),
                         *(set(v) for v in (tag_looks or {}).values()))
    carriers = {lk["carrier"] for lk in looks.values()} | ({disguise["carrier"]} if disguise else set())
    for path in sorted({_holder_owner(c, romfs) for c in carriers}) if LOOK_PRELOAD else ():
        for pk in packpaths.carriers(path, romfs):
            files = sarc_files(out.read(pk))
            slots = byml_load(files[LOOK_HOLDER])[0]["ActorHoldSettings"] if LOOK_HOLDER in files else {}
            missing = sorted(a for a in wanted if (slots.get(a) or {}).get("Actor")
                             != f"Work/Actor/{a}.engine__actor__ActorParam.gyml")
            if missing:
                bad.append(f"{pk}: the look holder doesn't declare {missing[:6]}{'...' if len(missing) > 6 else ''} "
                           f"({len(missing)}), so they wouldn't be loaded")
    # Every "the display exists" case wakes it, since a holder creates asleep. The valid-link selector's True
    # child asks for a sleeping display in the look slot and wakes it every frame at the carrier's position.
    for ai_file in sorted({_root_ai(c, romfs) for c in carriers}):
        a = ainb.Ainb(sarc_files(out.read(packpaths.carriers(ai_file, romfs)[0]))[ai_file])

        def ins(i):
            return {e["name"]: e for t in ainb.PTYPES for e in a.nodes[i]["inputs"][t]}
        for i, n in enumerate(a.nodes):
            if n["name"] != "QueryActorHolderIsValidActorLink" or ins(i)["key"]["value"] != LOOK_SLOT:
                continue
            for j, m in enumerate(a.nodes):
                if ainb.NODE_TYPES.get(m["type"]) != "BoolSelector" or not m["inputs"]["bool"] or m["inputs"]["bool"][0]["node"] != i:
                    continue
                true = next((pl["node"] for pl in m["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True"), -1)
                w = a.nodes[true] if true >= 0 else {}
                q = w["inputs"]["bool"][0]["node"] if w and w.get("inputs", {}).get("bool") else -1
                cs = next((pl["node"] for pl in w.get("plugs", [[]] * 8)[ainb.PLUG_CHILD] if pl["name"] == "True"),
                          -1) if w else -1
                bd = next((pl["node"] for pl in w.get("plugs", [[]] * 8)[ainb.PLUG_CHILD] if pl["name"] == "False"),
                          -1) if w else -1
                tr = ins(bd)["TransOffset"]["node"] if bd >= 0 else -1
                ok = (tr >= 0 and a.nodes[tr]["name"] == "QueryBlackboardGetVec3f"
                      and {e["name"]: e["value"] for t in ainb.PTYPES for e in a.nodes[tr]["properties"][t]}
                      .get("BlackboardKey") == LOOK_OFFSET_KEY
                      and bd >= 0 and a.nodes[bd]["name"] == "OneShotModelBindSetBindActorHolder"
                      and ins(bd)["ActorHolderKey"]["value"] == LOOK_SLOT
                      and ins(bd)["BindBoneName"]["value"] == LOOK_BIND_BONE
                      and q >= 0 and a.nodes[q]["name"] == "QueryActorHolderGetEnableCancelSleepIndex"
                      and ins(q)["Key"]["value"] == LOOK_SLOT and cs >= 0
                      and a.nodes[cs]["name"] == "OneShotActorHolderTryCancelSleepActor"
                      and ins(cs)["Key"]["value"] == LOOK_SLOT and ins(cs)["Index"]["node"] == q
                      and ins(cs)["Pos"]["node"] >= 0
                      and {e["name"]: e["value"] for t in ainb.PTYPES
                           for e in a.nodes[cs]["properties"][t]}.get("ExecuteEveryFrame") is True)
                if not ok:
                    bad.append(f"{ai_file}: the display check at node {j} doesn't wake and bind the display")
        leaves = [i for i, n in enumerate(a.nodes) if n["name"] == "ExecuteBlackboardSetString"
                  and {e["name"]: e["value"] for t in ainb.PTYPES for e in n["properties"][t]}.get("BlackboardKey")
                  == LOOK_ACTOR_KEY and _look_leaf(a, n) != LOOK_KEEP]  # leaves keeping the model store no offset
        creates = [i for i, n in enumerate(a.nodes) if n["name"] == "OneShotActorHolderTryRequestCreateActorWithActorFileName"
                   and ins(i)["Key"]["value"] == LOOK_SLOT]
        fed = [i for i in creates if ins(i)["ActorFileName"]["node"] >= 0
               and a.nodes[ins(i)["ActorFileName"]["node"]]["name"] == "QueryBlackboardGetString"]
        if len(fed) != 1 or len(creates) != 1:
            bad.append(f"{ai_file}: {len(creates)} display creates, {len(fed)} named by the picker (want one shared)")
        sets = [i for i, n in enumerate(a.nodes) if n["name"] == "ExecuteBlackboardSetVec3fToBlackBoard"
                and {e["name"]: e["value"] for t in ainb.PTYPES for e in n["properties"][t]}.get("BlackboardKey")
                == LOOK_OFFSET_KEY]
        if len(sets) != len(leaves) or LOOK_OFFSET_KEY not in [e["name"] for e in a.bb["vec3"]] or LOOK_ACTOR_KEY not in [e["name"] for e in a.bb["string"]]:
            bad.append(f"{ai_file}: {len(leaves)} picked displays but {len(sets)} stored offsets")
        fades = [i for i, n in enumerate(a.nodes) if n["name"] == "OneShotXLinkFadeByKey"
                 and ins(i)["KeyName"]["value"] == LOOK_GLITTER_KEY and ins(i)["IsKill"]["value"] is True]
        turned = {pl["node"] for n in a.nodes if any(a.nodes[p["node"]]["name"] == "OneShotGenericDeleteThisActor"
                                                       for p in n["plugs"][ainb.PLUG_CHILD])
                  for pl in n["plugs"][ainb.PLUG_CHILD]}  # the turn's hide (Ammo-to-rupee conversion) doesn't count
        hides = [i for i, n in enumerate(a.nodes) if n["name"] == "OneShotSetModelVisible" and i not in turned]
        if len(fades) < len(hides) - 1:  # (one hide is the vanilla get scene's own in event AIs, none in root AIs)
            bad.append(f"{ai_file}: {len(hides)} look hides but {len(fades)} glitter kills")
    for name, lk in sorted(looks.items()):
        path = _holder_owner(lk["carrier"], romfs)
        for pk in packpaths.carriers(path, romfs):
            files = sarc_files(out.read(pk))
            ap = byml_load(files[path])[0].get("Components", {})
            if ap.get("ActorHolderRef") != "?" + LOOK_HOLDER or LOOK_HOLDER not in files:
                bad.append(f"{pk}: {path} has no look holder")
                continue
            slot = byml_load(files[LOOK_HOLDER])[0]["ActorHoldSettings"].get(LOOK_SLOT, {})
            if not slot.get("IsWildActor") or not slot.get("IsModelBind") or \
                    [b.get("BoneName") for b in slot.get("ModelBindSettings", [])] != ["Root"]:
                bad.append(f"{pk}: the look holder's slot is not a wild slot bound to Root")
    by_ai = defaultdict(dict)
    for name, lk in looks.items():
        by_ai[_root_ai(lk["carrier"], romfs)][name] = sorted(lk["shows"])
    for ai_file, want in sorted(by_ai.items()):
        copies = {pk: sarc_files(out.read(pk))[ai_file] for pk in packpaths.carriers(ai_file, romfs)}
        if len(set(copies.values())) != 1:
            bad.append(f"{ai_file}: not the same in every pack holding it")
        a = ainb.Ainb(next(iter(copies.values())))
        got = {}
        for i, n in enumerate(a.nodes):
            if n["name"] != "QueryStringIsEqual":
                continue
            ins = {e["name"]: e for e in n["inputs"]["string"]}
            if ins["StringA"]["node"] < 0 or a.nodes[ins["StringA"]["node"]]["name"] != "QueryGetActorInstanceName":
                continue
            sel = next((j for j, m in enumerate(a.nodes) if m["type"] == 7 and m["inputs"]["bool"]
                        and m["inputs"]["bool"][0]["node"] == i), None)
            if sel is None:
                continue
            true = next(pl["node"] for pl in a.nodes[sel]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True")
            shows, todo, seen = set(), [true], set()
            while todo:  # every create node under the spot's True case (not into the next spot's chain)
                j = todo.pop()
                if j in seen:
                    continue
                seen.add(j)
                m = a.nodes[j]
                leaf = _look_leaf(a, m)
                if leaf:
                    shows.add(leaf)
                todo += [pl["node"] for pl in m["plugs"][ainb.PLUG_CHILD]]
            got[ins["StringB"]["value"]] = sorted(shows)
        got = {k: v for k, v in got.items() if k in want or v}
        if got != want:
            bad.append(f"{ai_file}: shows {got}, expected {want}")
    for ev in sorted({_event_ai(lk["carrier"], romfs) for lk in looks.values()} - GATED_HIDE - {None}):
        # a GATED_HIDE event AI's name-gated step is checked by verify_lake_looks / _gated_hide_problems
        a = ainb.Ainb(sarc_files(out.read(packpaths.carriers(ev, romfs)[0]))[ev])
        cmd = next(c for c in a.commands if c["name"] == LOOK_HIDE_COMMAND)["main"]
        kids = [a.nodes[pl["node"]] for pl in a.nodes[cmd]["plugs"][ainb.PLUG_CHILD]]
        sub = [a.nodes[pl["node"]]["name"] for k in kids for pl in k["plugs"][ainb.PLUG_CHILD]]
        if "OneShotActorHolderRequestDelete" not in sub or "ExecuteGoOffstage" not in sub:
            bad.append(f"{ev}: EventGoOffstageForUser doesn't delete the display ({sub})")
    return bad


def _verify_look_aids(out, looks, romfs, disguise=None, tag_looks=None, water=None):
    """Reads the size floor and the under-water glow back (look_ops) in every carrier root AI. Each picker leaf stores
    its display's look_offsets (of the scaled box) and, for a display look_scales enlarges, exactly that scale,
    which the wake step then reads (the blackboard default is (1, 1, 1)). The leaves of the spots in `water` (plan
    "_drops_looks_water": {"spots": [Names]}), and no others, name LOOK_KEEP_GLOW as the ELink key to kill, which
    the show branch's fade then reads (the default is the glitter key)."""
    from romtools import sarc_files
    import ainb
    import packpaths
    wet_spots = set((water or {}).get("spots") or ())
    shown = set().union(*(set(lk["shows"]) for lk in looks.values()), set((disguise or {}).get("shows") or ()),
                        *(set(v) for v in (tag_looks or {}).values()))
    scales = look_scales(shown, romfs)
    offsets = look_offsets(shown, romfs, scales)
    carriers = {lk["carrier"] for lk in looks.values()} | ({DISGUISE_ACTOR} if disguise or tag_looks else set())
    bad, found = [], set()
    for ai_file in sorted({_root_ai(c, romfs) for c in carriers}):
        a = ainb.Ainb(sarc_files(out.read(packpaths.carriers(ai_file, romfs)[0]))[ai_file])

        def ins(i):
            return {e["name"]: e for t in ainb.PTYPES for e in a.nodes[i]["inputs"][t]}

        def props(i):
            return {e["name"]: e["value"] for t in ainb.PTYPES for e in a.nodes[i]["properties"][t]}

        def kids(i):
            return [pl["node"] for pl in a.nodes[i]["plugs"][ainb.PLUG_CHILD]]

        def bb(i, kind, key):  # node i is `kind` on the AI's own blackboard key `key`
            return i >= 0 and a.nodes[i]["name"] == kind and props(i).get("BlackboardType") == 0 \
                and props(i).get("BlackboardKey") == key

        def leaves_under(i):
            got, todo, seen = set(), [i], set()
            while todo:
                j = todo.pop()
                if j < 0 or j in seen:
                    continue
                seen.add(j)
                if j in leaves:
                    got.add(j)
                todo += kids(j)
            return got
        parent = {c: i for i in range(len(a.nodes)) for c in kids(i)}
        leaves = {}  # picker leaf (its Simultaneous) -> whether it keeps the glow
        for i in range(len(a.nodes)):
            if not bb(i, "ExecuteBlackboardSetString", LOOK_ACTOR_KEY) or i not in parent:
                continue
            actor, sim = ins(i)["String"]["value"], parent[i]
            if actor == LOOK_KEEP:  # Type-based displays keep the model: name and drop off, no hide or offset
                if [a.nodes[j]["name"] for j in kids(sim)] != ["ExecuteBlackboardSetString", "OneShotDropSetDropValid"] \
                        or ins(kids(sim)[1])["IsValid"]["value"] is not False:
                    bad.append(f"{ai_file}: the keep-own-model leaf {sim} isn't: store {LOOK_KEEP}, its drop off")
                continue
            vec = {props(j).get("BlackboardKey"): list(ins(j)["Vector"]["value"]) for j in kids(sim)
                   if a.nodes[j]["name"] == "ExecuteBlackboardSetVec3fToBlackBoard"}
            glow = [ins(j)["String"]["value"] for j in kids(sim) if bb(j, "ExecuteBlackboardSetString", LOOK_FADE_KEY)]
            want, got = scales.get(actor), vec.get(LOOK_SCALE_KEY)
            if (want is None) != (got is None) or (want and any(abs(v - want) > 1e-4 for v in got)):
                bad.append(f"{ai_file}: {actor} is drawn at scale {got}, expected {want or 'none'}")
            off = vec.get(LOOK_OFFSET_KEY)
            if off is None or any(abs(x - y) > 1e-3 for x, y in zip(off, offsets.get(actor, [0.0, 0.0, 0.0]))):
                bad.append(f"{ai_file}: {actor} is offset by {off}, expected {offsets.get(actor)}")
            if glow not in ([], [LOOK_KEEP_GLOW]):
                bad.append(f"{ai_file}: {actor}'s picker writes {glow} as the key to kill")
            if not any(a.nodes[j]["name"] == "OneShotSetModelVisible" and ins(j)["Bool"]["value"] is False
                       for j in kids(sim)):  # First-tick hide
                bad.append(f"{ai_file}: {actor}'s picker leaf doesn't hide the carrier when it picks")
            leaves[sim] = bool(glow)
        sized, wet = any(scales.get(ins(i)["String"]["value"]) for i in range(len(a.nodes))
                         if bb(i, "ExecuteBlackboardSetString", LOOK_ACTOR_KEY)), any(leaves.values())
        for i in range(len(a.nodes)):
            if a.nodes[i]["name"] == "OneShotActorHolderTryCancelSleepActor" and ins(i)["Key"]["value"] == LOOK_SLOT \
                    and bb(ins(i)["Scale"]["node"], "QueryBlackboardGetVec3f", LOOK_SCALE_KEY) != sized:
                bad.append(f"{ai_file}: the wake step {'doesn' if sized else 'does'}'t read the display's scale")
            if a.nodes[i]["name"] == "OneShotXLinkFadeByKey" and ins(i)["KeyName"]["value"] == LOOK_GLITTER_KEY \
                    and bb(ins(i)["KeyName"]["node"], "QueryBlackboardGetString", LOOK_FADE_KEY) != wet:
                bad.append(f"{ai_file}: the glitter kill {'doesn' if wet else 'does'}'t read the spot's key")
        defaults = {e["name"]: e.get("default") for t in ("vec3", "string") for e in a.bb[t]}
        if sized and [round(v, 4) for v in defaults.get(LOOK_SCALE_KEY) or []] != [1.0, 1.0, 1.0]:
            bad.append(f"{ai_file}: {LOOK_SCALE_KEY} defaults to {defaults.get(LOOK_SCALE_KEY)}, not (1, 1, 1)")
        if wet and defaults.get(LOOK_FADE_KEY) != LOOK_GLITTER_KEY:
            bad.append(f"{ai_file}: {LOOK_FADE_KEY} defaults to {defaults.get(LOOK_FADE_KEY)!r}, not the glitter")
        keep = set()  # the leaves of under-water spots
        sel_of = {m["inputs"]["bool"][0]["node"]: j for j, m in enumerate(a.nodes)
                  if m["type"] == 7 and m["inputs"]["bool"]}
        for i, nd in enumerate(a.nodes):
            sel = sel_of.get(i)
            if sel is None or nd["name"] != "QueryStringIsEqual":
                continue
            s = {e["name"]: e for e in nd["inputs"]["string"]}
            src, name = s["StringA"]["node"], s["StringB"]["value"]
            if src >= 0 and a.nodes[src]["name"] == "QueryGetActorInstanceName" and name in wet_spots:
                keep |= leaves_under(next((pl["node"] for pl in a.nodes[sel]["plugs"][ainb.PLUG_CHILD]
                                           if pl["name"] == "True"), -1))
                found.add(name)
        for j, glows in sorted(leaves.items()):
            if glows != (j in keep):
                bad.append(f"{ai_file}: picker leaf {j} {'keeps' if glows else 'kills'} the carrier's glow, expected "
                           f"{'keeps' if j in keep else 'kills'}")
    if wet_spots - found:
        bad.append(f"under-water looks not found in any carrier AI: {sorted(wet_spots - found)}")
    return bad


def _look_leaf(a, m):
    """The display a look node stands for: a picker leaf writing LOOK_ACTOR_KEY, or a create by constant name."""
    props = {e["name"]: e["value"] for t in ("string", "int") for e in m["properties"][t]}
    if m["name"] == "ExecuteBlackboardSetString" and props.get("BlackboardKey") == LOOK_ACTOR_KEY:
        return next(e["value"] for e in m["inputs"]["string"] if e["name"] == "String")
    if m["name"] == "OneShotActorHolderTryRequestCreateActorWithActorFileName":
        e = next(e for e in m["inputs"]["string"] if e["name"] == "ActorFileName")
        return e["value"] if e["node"] < 0 else None
    return None


def _verify_disguise_look(out, dis, romfs, shown=()):
    """Reads plan "_drops_looks_disguise" back. The carrier has the look holder, and its root AI (the same in every
    pack) checks the actor's own type against the carrier. For it, the AI picks exactly the planned displays under
    one RandomSelector with every child weighted, and the shared show branch hides the model and creates the pick.
    Each skipped name idles unless it shows its own item (`shown`, the named look spots verify_looks checks)."""
    from romtools import sarc_files, byml_load
    import struct
    import ainb
    import packpaths
    bad = []
    path = _holder_owner(dis["carrier"], romfs)
    for pk in packpaths.carriers(path, romfs):
        files = sarc_files(out.read(pk))
        if byml_load(files[path])[0].get("Components", {}).get("ActorHolderRef") != "?" + LOOK_HOLDER \
                or LOOK_HOLDER not in files:
            bad.append(f"{pk}: {path} has no look holder (disguise)")
    ai_file = _root_ai(dis["carrier"], romfs)
    copies = {pk: sarc_files(out.read(pk))[ai_file] for pk in packpaths.carriers(ai_file, romfs)}
    if len(set(copies.values())) != 1:
        bad.append(f"{ai_file}: not the same in every pack holding it")
    a = ainb.Ainb(next(iter(copies.values())))

    def kind(j):
        return a.nodes[j]["name"] or ainb.NODE_TYPES.get(a.nodes[j]["type"])

    def sel_of(i):
        return next((j for j, m in enumerate(a.nodes) if m["type"] == 7 and m["inputs"]["bool"]
                     and m["inputs"]["bool"][0]["node"] == i), None)
    found, skipped = [], set()
    for i, n in enumerate(a.nodes):
        if n["name"] != "QueryStringIsEqual":
            continue
        ins = {e["name"]: e for e in n["inputs"]["string"]}
        src = ins["StringA"]["node"]
        sel = sel_of(i)
        if src < 0 or sel is None:
            continue
        true = next(pl["node"] for pl in a.nodes[sel]["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True")
        if kind(src) == "QueryGetActorInstanceName" and ins["StringB"]["value"] in dis["skip"]:
            if kind(true) == "OneshotDoNothing":
                skipped.add(ins["StringB"]["value"])
        elif kind(src) == "QueryGenericGetActorName" and ins["StringB"]["value"] == dis["carrier"]:
            found.append(true)
    missing = set(dis["skip"]) - skipped - set(shown)
    if len(found) != 1:
        return bad + [f"{ai_file}: {len(found)} type checks for {dis['carrier']}, expected 1"]
    # The picker's type check leads straight to the random pick, and the one shared show branch hides the carrier.
    hides = [j for j in range(len(a.nodes)) if kind(j) == "OneShotSetModelVisible"
             and [e["value"] for e in a.nodes[j]["inputs"]["bool"] if e["name"] == "Bool"] == [False]]
    if not hides:
        bad.append(f"{ai_file}: the look branch doesn't hide the carrier's model")
    rnds = [found[0]] if a.nodes[found[0]]["type"] == 6 else []
    if len(rnds) != 1:
        return bad + [f"{ai_file}: {len(rnds)} random picks in the disguise branch, expected 1"]
    picks = a.nodes[rnds[0]]["plugs"][ainb.PLUG_CHILD]
    if any(len(pl["extra"]) != 8 or struct.unpack("<If", pl["extra"])[1] <= 0 for pl in picks):
        bad.append(f"{ai_file}: a random pick without a weight")
    shows, todo, seen = set(), [pl["node"] for pl in picks], set()
    while todo:
        j = todo.pop()
        if j in seen:
            continue
        seen.add(j)
        m = a.nodes[j]
        leaf = _look_leaf(a, m)
        if leaf:
            shows.add(leaf)
        todo += [pl["node"] for pl in m["plugs"][ainb.PLUG_CHILD]]
    if sorted(shows) != sorted(dis["shows"]):
        bad.append(f"{ai_file}: the disguise shows {sorted(shows)}, expected {sorted(dis['shows'])}")
    if missing:
        bad.append(f"{ai_file}: the carrier's own names {sorted(missing)} don't keep their look")
    return bad


# Reset groups (remake_reset_group_objects)
# There are 113 SupplyItemResetSystemActor placements over 23 stages, mostly dungeons with one save area each.
# Whenever one fires it brings back the 2-3 pots, grass, crates or rocks it links (its AI is the engine node
# ExecuteSupplyItemResetSystem). So an object in a group comes back after its item was taken, however its own
# flag resets.
# The targets are listed twice, and in vanilla both lists always match (113/113): the actor's Links (Dst) and
# Banc/BancBasedResource/GmdReset (stage -> actor hash -> DstHash). The AoC1 copy holds the same base stages plus
# the MQ ones. Taking an object out means removing it from both, in every file (ungroup_ops). A group left empty
# loses its actor and its GmdReset entry, like a stage without one.
# The object's flag is then made permanent like any other.
GMD_RESET = ("Banc/BancBasedResource/GmdReset.byml.zs", "AoC1/Banc/BancBasedResource/GmdReset.byml.zs")
RESET_ACTOR = "SupplyItemResetSystemActor"


@lru_cache(maxsize=None)
def _gmd_reset(romfs=DEFAULT_ROMFS):
    """{GmdReset file: {reset actor hash: (stage, [target hashes])}} (strings)."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = {}
    for f in GMD_RESET:
        root = byml_load(fs.read(f))[0]
        out[f] = {str(h): (stage, [str(x) for x in g["DstHash"]]) for stage, grp in root.items() for h, g in grp.items()}
    return out


@lru_cache(maxsize=None)
def _reset_actors(stage_dir, romfs=DEFAULT_ROMFS):
    """({reset actor hash: [(level file, [linked hashes])]}, {reset actor hash: [(level file, hash of another actor
    linking to it)]}) for a stage folder's level files. Two vanilla pots link to a reset actor themselves, Bottom of
    the Well 7569958918344529585 and Fire Temple 3049694327750200002. That's a Reference link from the pot, in
    neither list."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out, inbound, acts = defaultdict(list), defaultdict(list), []
    for fn in sorted(os.listdir(os.path.join(romfs, stage_dir))):
        if not fn.endswith(".bcett.byml.zs"):
            continue
        rel = f"{stage_dir}/{fn}"
        for a in (byml_load(fs.read(rel))[0] or {}).get("Actors", []) or []:
            acts.append((rel, a))
            if a.get("Gyaml") == RESET_ACTOR:
                out[str(a.get("Hash"))].append((rel, [str(ln.get("Dst")) for ln in a.get("Links") or []]))
    for rel, a in acts:
        for ln in a.get("Links") or []:
            if str(ln.get("Dst")) in out and a.get("Gyaml") != RESET_ACTOR:
                inbound[str(ln.get("Dst"))].append((rel, str(a.get("Hash"))))
    return dict(out), dict(inbound)


def ungroup_ops(groups, romfs=DEFAULT_ROMFS):
    """make_patch sections that take objects out of their reset groups. `groups` is {reset actor hash: {"targets":
    {hash}, "dirs": {stage folder of the targets' level files}}}. Each reset actor placement loses its links to them
    ("unlink"), or is deleted when none would be left. Each GmdReset copy loses them from the actor's DstHash
    ("remove_values"), or loses the actor's entry ("delete_keys"). Raises DropPlanError where the two lists disagree."""
    resets = _gmd_reset(romfs)
    place, byml = [], []
    for reset, g in sorted(groups.items()):
        targets = set(g["targets"])
        if reset not in resets[GMD_RESET[0]]:
            raise DropPlanError(f"reset group {reset}: not in {GMD_RESET[0]}")
        stage, members = resets[GMD_RESET[0]][reset]
        if targets - set(members):
            raise DropPlanError(f"reset group {reset}: {sorted(targets - set(members))} not among its targets")
        whole = targets == set(members)
        holders = [h for d in sorted(g["dirs"]) for h in _reset_actors(d, romfs)[0].get(reset, [])]
        inbound = [h for d in sorted(g["dirs"]) for h in _reset_actors(d, romfs)[1].get(reset, [])]
        if not holders:
            raise DropPlanError(f"reset group {reset}: no {RESET_ACTOR} placement in {sorted(g['dirs'])}")
        for rel, links in holders:
            if sorted(links) != sorted(members):
                raise DropPlanError(f"{rel}: reset actor {reset} links {links}, GmdReset lists {members}")
            place.append({"file": rel, "hash": reset, "delete": True} if whole else
                         {"file": rel, "hash": reset, "unlink": sorted(targets)})
        if whole:  # nothing may keep a link to a deleted actor
            place += [{"file": rel, "hash": src, "unlink": [reset]} for rel, src in inbound]
        for f in GMD_RESET:
            if reset not in resets[f]:
                continue
            if sorted(resets[f][reset][1]) != sorted(members):
                raise DropPlanError(f"{f}: reset group {reset} differs from {GMD_RESET[0]}")
            byml.append({"file": f, "delete_keys": [f"{stage}.{reset}"]} if whole else
                        {"file": f, "remove_values": {f"{stage}.{reset}.DstHash": [int(t) for t in sorted(targets)]}})
    return {"placements": place, "byml": byml}


def group_join_ops(joins, romfs=DEFAULT_ROMFS):
    """For a reset group's member that takes the respawn model, its twin joins the group beside it. Each reset actor
    links it as it links the member, and every GmdReset copy lists it. So the vanilla pot that stands there once the
    member is checked refills with the room as the member did (only one of the two is ever present).
    `joins` is [(placement, twin hash)]. Returns make_patch sections and {twin: reset actor} (plan
    "_drops_group_twins")."""
    resets = _gmd_reset(romfs)
    adds, vals, rec = defaultdict(list), defaultdict(lambda: defaultdict(list)), {}
    for p, twin in joins:
        reset, h = str(p.get("reset_group") or p.get("ungroup")), str(p["hash"])
        if reset not in resets[GMD_RESET[0]] or h not in resets[GMD_RESET[0]][reset][1]:
            raise DropPlanError(f"{h}: not a target of reset group {reset} in {GMD_RESET[0]}")
        holders = _reset_actors(os.path.dirname(p["file"]), romfs)[0].get(reset, [])
        if not holders:
            raise DropPlanError(f"reset group {reset}: no {RESET_ACTOR} placement beside {p['file']}")
        for rel, links in holders:
            if h not in links:
                raise DropPlanError(f"{rel}: reset actor {reset} doesn't link {h}")
            adds[(rel, reset)].append({"like": h, "dst": str(twin)})
        for f in GMD_RESET:
            if reset in resets[f]:
                vals[f][f"{resets[f][reset][0]}.{reset}.DstHash"].append(int(twin))
        rec[str(twin)] = {"reset": reset, "source": h, "holders": sorted({rel for rel, _ in holders})}
    place = [{"file": rel, "hash": reset, "add_links": a} for (rel, reset), a in sorted(adds.items())]
    byml = [{"file": f, "add_values": {k: sorted(v) for k, v in sorted(paths.items())}} for f, paths in sorted(vals.items())]
    return {"placements": place, "byml": byml, "record": rec}


def verify_group_twins(patch_dir, rec, romfs=DEFAULT_ROMFS):
    """Reads plan "_drops_group_twins" back. Each twin is linked by its group's reset actors as its source is, and
    listed beside it in every GmdReset copy. Returns [problem, ...]."""
    from romtools import Romfs, byml_load
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    bad, levels = [], {}
    for twin, g in sorted(rec.items()):
        for rel in g["holders"]:
            if rel not in levels:
                levels[rel] = {str(a.get("Hash")): a for a in byml_load(new.read(rel))[0].get("Actors", [])}
            a = levels[rel].get(g["reset"]) or {}
            dst = [str(ln.get("Dst")) for ln in a.get("Links") or []]
            if twin not in dst or g["source"] not in dst:
                bad.append(f"{rel}: reset actor {g['reset']} links {g['source']} {g['source'] in dst}, twin {twin} "
                           f"{twin in dst}")
        for f in GMD_RESET:
            root = byml_load(new.read(f))[0]
            for stage, grp in root.items():
                if g["reset"] in {str(k) for k in grp}:
                    lst = [str(x) for x in next(v for k, v in grp.items() if str(k) == g["reset"])["DstHash"]]
                    if twin not in lst or g["source"] not in lst:
                        bad.append(f"{f}: group {g['reset']} lists source {g['source'] in lst}, twin {twin in lst}")
    return bad


def verify_object_drops(patch_dir, scene_drops, flag_spots, droppers, romfs=DEFAULT_ROMFS, overrides=None,
                        components=None):
    """Reads back the object shuffles' own edits (plan "_drops_scene_drops", "_drops_flag_spots" and the
    checked-on-pickup "droppers", "_drops_components"). Returns [problem, ...].
    Flagless drops: every borrowed flag is in the free pool, unclaimed and used once. A respawning pot or grass is
    removed by a negated Presence on it, and a tree's placement names the flag in DROP_FLAG_KEY. Both get scenes ask
    for it and set it. A tree type's AI reads DROP_FLAG_KEY, checks the flag and then sets its own IsDropped, from
    its root. Every pack holding the Drop table declares DROP_FLAG_KEY as a String instance parameter.
    Drop components (icicles, red ice, silver rocks): every pack holding the type's ActorParam has the same five
    Drop files as the bomb boulder, DropRef (and the icicles' DeathParam for red ice and silver rocks), and its Drop
    table declares the tag. Each spot of those types names the empty table, and the type's heap grew. The icicles'
    death table keeps vanilla break saving, and so does red ice's Blue-Fire hit (the respawn model)."""
    from romtools import Romfs, sarc_files, byml_load
    import ainb
    import evfl
    import packpaths
    import free_flags
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    bad, levels = [], {}
    droppers = set(droppers or ())

    def placed(p):
        if p["file"] not in levels:
            levels[p["file"]] = {str(a.get("Hash")): a for a in byml_load(new.read(p["file"]))[0]["Actors"]}
        return levels[p["file"]].get(str(p["hash"])) or {}

    def props(a, i):
        return {e["name"]: e["value"] for t in ainb.PTYPES for e in a.nodes[i]["properties"][t]}

    def drop_rows(pk, array):
        files = sarc_files(new.read(pk))
        if DROP_TABLE not in files:
            return None
        return {r.get("BBKey"): r for r in byml_load(files[DROP_TABLE])[0].get(array) or []}
    # flagless drops
    flags = list((flag_spots or {}).values())
    free, claimed = set(free_flags.pool(romfs)) | set(free_flags.MINTED), free_flags.claimed()
    for f in sorted(set(flags)):
        if f not in free or f in claimed:
            bad.append(f"flag {f}: not a free saved flag (nor one this seed minted)")
        if flags.count(f) > 1:
            bad.append(f"flag {f}: borrowed by {flags.count(f)} spots")
    trees = set()
    for name, flag in sorted((flag_spots or {}).items()):
        for p in lookup(name, overrides=overrides)["placements"]:
            kind = FLAGLESS_DROPPERS.get(p["actor"], (None,))[0]
            a = placed(p)
            if kind == "presence":
                want = {"FlagName": flag, "IsCheckLazy": False, "IsNegation": True}
                if a.get("Presence") != want:
                    bad.append(f"{name} ({p['hash']}): Presence {a.get('Presence')}, expected {want}")
                # its vanilla twin stands there from the next visit, as the vanilla object
                # (non-lazy, TWIN_PRESENCE, VISIT)
                tw = _flagless_twin(p, flag, flagless_visits(flag_spots)[name])
                t = levels[p["file"]].get(tw["twin"]) or {}
                van0 = heartless(_vanilla_level(p["file"]).get(str(p["hash"])) or {}, no_heart_drops(patch_dir))
                if not t:
                    bad.append(f"{name} ({p['hash']}): no vanilla twin {tw['twin']} in {p['file']}")
                elif t.get("Presence") != tw["set"]["Presence"] or t.get("Gyaml") != van0.get("Gyaml") or (t.get("Dynamic") or {}) != (van0.get("Dynamic") or {}):
                    bad.append(f"{name} ({p['hash']}): twin {tw['twin']} is {t.get('Gyaml')} with Presence "
                               f"{t.get('Presence')}, expected the vanilla object with {tw['set']['Presence']}")
                got_id, van_id = (((x.get("Phive") or {}).get("Placement") or {}).get("ID") for x in (t, van0))
                if t and van_id is not None and \
                        int(got_id or 0) != int(van_id if tw.get("keep_phive_id") else tw["twin"]):  # BAKED_TYPES
                    bad.append(f"{name} ({p['hash']}): twin {tw['twin']} has Phive ID {got_id}, expected "
                               f"{'its source' if tw.get('keep_phive_id') else 'its own hash'}'s")
            elif kind == "tree":
                trees.add(p["actor"])
                got = (a.get("Dynamic") or {}).get(DROP_FLAG_KEY)
                if got != flag:
                    bad.append(f"{name} ({p['hash']}): {DROP_FLAG_KEY} {got!r}, expected {flag}")
            else:
                bad.append(f"{name} ({p['hash']}): {p['actor']} can't hold a flagless drop")
    if flags:  # Dm_SY_Get gives (it has the GameDataActor), and the no-player scene calls its RandoST_HeartWP_ entries
        scene = HOOK_SCENES[0]
        ev = evfl.Evfl(new.read(scene))
        asked, setf = {}, {}
        for fc in ev.flowcharts:
            for e in fc["events"]:
                it = (e.get("params") or {}).get("items") or {}
                g = (it.get("GameDataName") or {}).get("value")
                if g is None or not e["name"].startswith("RandoST_"):
                    continue
                path = "no-player" if e["name"].startswith("RandoST_HeartWP_") else "player"
                if e["type"] == "switch":
                    asked.setdefault(g, set()).add(path)
                elif e["type"] == "action" and (it.get("Value") or {}).get("value") is True:
                    setf.setdefault(g, set()).add(path)
        for f in sorted(set(flags)):
            for path in ("player", "no-player"):
                if path not in asked.get(f, ()) or path not in setf.get(f, ()):
                    bad.append(f"{scene}: the {path} give doesn't ask and set flag {f}")
        # VISIT: each flagless spot's visit bit is set just before its flag (its twin can't stand there this visit)
        want = {flag_spots[n]: v for n, v in flagless_visits(flag_spots).items()}
        for fc in ev.flowcharts:
            by = {e["name"]: e for e in fc["events"]}
            for e in fc["events"]:
                it = (e.get("params") or {}).get("items") or {}
                g = (it.get("GameDataName") or {}).get("value")
                if e["type"] != "action" or g not in want or not e["name"].startswith("RandoST_") or \
                        (it.get("Value") or {}).get("value") is not True:
                    continue
                pred = [x for x in fc["events"] if x.get("next") is not None and x["next"] < len(fc["events"])
                        and fc["events"][x["next"]]["name"] == e["name"]]
                vis = [x for x in pred if ((x.get("params") or {}).get("items") or {}).get("GameDataName", {})
                       .get("value") == VISIT_ARRAY and ((x.get("params") or {}).get("items") or {})
                       .get("Index", {}).get("value") == want[g]]
                if len(pred) != 1 or not vis:
                    bad.append(f"{scene}: {e['name']} sets {g} without {VISIT_ARRAY}[{want[g]}] right before it")
    for actor in sorted(trees):
        pk, ai_file = dropper_ai(actor)
        a = ainb.Ainb(sarc_files(new.read(pk))[ai_file])
        ok = False
        for i, n in enumerate(a.nodes):
            if n["name"] != "QueryGetNonStructGameDataBool":
                continue
            src = next((e["node"] for e in n["inputs"]["string"] if e["name"] == "GameDataFullName"), -1)
            if src < 0 or a.nodes[src]["name"] != "QueryBlackboardGetString" or \
                    props(a, src).get("BlackboardKey") != DROP_FLAG_KEY or props(a, src).get("BlackboardType") != 1:
                continue
            for m in a.nodes:
                if ainb.NODE_TYPES.get(m["type"]) != "BoolSelector" or not m["inputs"]["bool"] or \
                        m["inputs"]["bool"][0]["node"] != i:
                    continue
                true = next((pl["node"] for pl in m["plugs"][ainb.PLUG_CHILD] if pl["name"] == "True"), -1)
                t = a.nodes[true] if true >= 0 else {}
                if t.get("name") == "ExecuteBlackboardSetBool" and props(a, true).get("BlackboardKey") == "IsDropped" \
                        and [e["value"] for e in t["inputs"]["bool"] if e["name"] == "Bool"] == [True]:
                    ok = True
        root = a.nodes[next(c for c in a.commands if c["name"] == "Root")["main"]]
        kids = {pl["node"] for pl in root["plugs"][ainb.PLUG_CHILD]}
        gate_top = [j for j in kids if ainb.NODE_TYPES.get(a.nodes[j]["type"]) == "BoolSelector"
                    and a.nodes[j]["inputs"]["bool"]
                    and a.nodes[a.nodes[j]["inputs"]["bool"][0]["node"]]["name"] == "QueryStringIsEqual"]
        if not ok or not gate_top:
            bad.append(f"{pk} {ai_file}: no flag gate setting IsDropped from the root ({actor})")
    # drop components
    comp = sorted(components if components is not None else (t for t in droppers if t in DROP_COMPONENT))
    comp_packs = set()
    src = sarc_files(new.read(DROP_COMPONENT_SRC))  # (its Drop table as edited for every pack)
    for path in sorted({DROP_COMPONENT[t] for t in comp}):
        for pk in packpaths.carriers(path, romfs):
            comp_packs.add(pk)
            files = sarc_files(new.read(pk))
            for f in DROP_COMPONENT_FILES:
                if files.get(f) != src[f]:
                    bad.append(f"{pk}: {f} missing or not the bomb boulder's")
            if RANDO_DROP_DEFAULT not in files:
                bad.append(f"{pk}: no {RANDO_DROP_DEFAULT} (our droppers' own DropParam)")
            ap = byml_load(files[path])[0].get("Components") or {}
            if ap.get("DropRef") != DROP_COMPONENT_REF:
                bad.append(f"{pk}: {path} DropRef {ap.get('DropRef')}")
            if path in DEATH_TO_ICICLE and (ap.get("DeathRef") != "?" + ICICLE_DP or ICICLE_DP not in files):
                bad.append(f"{pk}: {path} DeathRef {ap.get('DeathRef')}, expected the icicles' DeathParam")
    for name in sorted(scene_drops or {}):
        for p in lookup(name, overrides=overrides)["placements"]:
            if p["actor"] in DROP_COMPONENT:
                got = (placed(p).get("Dynamic") or {}).get("Drop__DropTable")
                if got != EMPTY_TABLE:
                    bad.append(f"{name} ({p['hash']}): Drop__DropTable {got!r}, expected {EMPTY_TABLE!r}")
    for pk in sorted(set(packpaths.carriers(DROP_TABLE, romfs)) | comp_packs):
        if scene_drops:
            r = (drop_rows(pk, "BlackboardParamF32Array") or {}).get(DROP_TAG_KEY)
            if r is None or not r.get("IsInstanceParam"):
                bad.append(f"{pk}: the Drop table has no instance F32 {DROP_TAG_KEY}")
        if trees:
            r = (drop_rows(pk, "BlackboardParamStringArray") or {}).get(DROP_FLAG_KEY)
            if r is None or not r.get("IsInstanceParam"):
                bad.append(f"{pk}: the Drop table has no instance String {DROP_FLAG_KEY}")
    if comp:
        old = {r.get("__RowId"): r.get("InstanceHeapSize") for r in byml_load(van.read(ACTOR_INFO))[0]}
        cur = {r.get("__RowId"): r.get("InstanceHeapSize") for r in byml_load(new.read(ACTOR_INFO))[0]}
        for t in comp:
            if old.get(t) and cur.get(t) != old[t] + COMPONENT_HEAP_EXTRA:
                bad.append(f"{t}: instance heap {cur.get(t)}, expected {old[t]} + {COMPONENT_HEAP_EXTRA}")
    if new.raw(ICICLE_TABLE) != van.raw(ICICLE_TABLE):  # the respawn model keeps vanilla break saving
        bad.append(f"{ICICLE_TABLE}: edited")
    if droppers & set(_RED_ICE):  # red ice's Blue-Fire hit saves its flag as in vanilla
        pk = f"Pack/Actor/{sorted(droppers & set(_RED_ICE))[0]}.pack.zs"
        a = ainb.Ainb(sarc_files(new.read(pk))[REDICE_AI])
        v = ainb.Ainb(sarc_files(van.read(pk))[REDICE_AI])
        if ainb.describe_node(a, REDICE_RESPAWN_NODE) != ainb.describe_node(v, REDICE_RESPAWN_NODE):
            bad.append(f"{REDICE_AI}: node {REDICE_RESPAWN_NODE} (the Blue-Fire hit's save) changed")
    return bad


def verify_ungroup(patch_dir, ungrouped, romfs=DEFAULT_ROMFS):
    """Reads plan "_drops_ungrouped" ({reset actor hash: [target hashes]}) back and returns [problem, ...]. Every
    taken-out object is in no reset actor's Links and no GmdReset DstHash (both copies), and its flag is permanent
    (24). Every reset actor left links exactly what GmdReset lists for it, and a deleted actor has no GmdReset entry."""
    from romtools import Romfs, byml_load
    van = Romfs(romfs, os.path.join(HERE, "original"))
    new = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    taken_all = {t for ts in ungrouped.values() for t in ts}

    def state(fs, taken):
        """Returns every way the two lists, the links into reset actors and the taken-out objects disagree, and the
        placed reset actors. Vanilla has some disagreements of its own (MQ-only actors listed only in the AoC1 copy),
        so only new ones count."""
        out, actors, hashes, links_to = set(), {}, set(), []
        for area in sorted(os.listdir(os.path.join(romfs, "Banc"))):
            d = os.path.join(romfs, "Banc", area)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".bcett.byml.zs"):
                    continue
                rel = f"Banc/{area}/{fn}"
                for a in (byml_load(fs.read(rel))[0] or {}).get("Actors", []) or []:
                    hashes.add(str(a.get("Hash")))
                    if a.get("Gyaml") == RESET_ACTOR:
                        actors.setdefault(str(a.get("Hash")), []).append(
                            (rel, sorted(str(ln.get("Dst")) for ln in a.get("Links") or [])))
                    links_to += [(rel, a.get("Gyaml"), str(a.get("Hash")), str(ln.get("Dst")))
                                 for ln in a.get("Links") or []]
        for f in GMD_RESET:
            root = byml_load(fs.read(f))[0]
            listed = {str(h): sorted(str(x) for x in g["DstHash"]) for grp in root.values() for h, g in grp.items()}
            for h, ts in listed.items():
                if set(ts) & taken:
                    out.add(f"{f}: {h} still lists {sorted(set(ts) & taken)}")
                if h not in actors:
                    out.add(f"{f}: {h} has no reset actor in any level file")
            for h, holders in actors.items():
                if h not in listed:
                    out.add(f"reset actor {h} ({holders[0][0]}) has no {f} entry")
                for rel, links in holders:
                    if h in listed and links != listed[h]:
                        out.add(f"{rel}: reset actor {h} links {links}, {f} lists {listed[h]}")
                    if set(links) & taken:
                        out.add(f"{rel}: reset actor {h} still links {sorted(set(links) & taken)}")
        return out, set(actors), hashes, links_to
    before, had, _, _ = state(van, set())  # disagreements vanilla already has don't count
    after, has, hashes, links_to = state(new, taken_all)
    bad = sorted(after - before)
    gone = had - has
    bad += [f"{rel}: {g} {h} links to the deleted reset actor {d}" for rel, g, h, d in links_to if d in gone]
    bad += [f"reset actor {h} was deleted but kept targets" for h in sorted(gone)
            if h not in ungrouped]
    gd, _ = byml_load(new.read(GAMEDATA), allow_big=True)
    flags = {str(e["Hash"]): int(e["ResetTypeValue"]) for e in gd["Data"]["Bool64bitKey"]}
    bad += [f"{t}: save flag resets ({flags.get(t)}), not permanent (24)" for t in sorted(taken_all)
            if flags.get(t) != 24]
    return bad


def repeatable(item_name, actor):
    return item_name in REPEATABLE_ITEMS or actor in REPEATABLE_JUNK or item_name == "Ice Trap"


def usable(entry, allow=()):
    if entry.get("mode") is None and entry.get("type"):  # a new location (drop_map "new")
        return not (set(entry.get("blockers", [])) - set(allow))
    return entry.get("mode") in ("full", "group") and not (set(entry.get("blockers", [])) - set(allow))


def lookup(name, m=None, overrides=None):
    """The drop-map entry of an OoTR location ("drops"), a new location ("new") or an extras key. `overrides` ({name:
    entry}, the plugin's settings-dependent view of stage hearts and key spots) wins."""
    if overrides and name in overrides:
        return overrides[name]
    m = m or _map()
    return m["drops"].get(name) or m.get("new", {}).get(name) or m["extras"].get(name)


def plan_ops(assignments, allow=(), drop_map=None, romfs=None, scene=(), empty="vanilla", ice="classic",
             overrides=None, named=(), fallthrough=None, disguise_names=(), looks=None, disguise_looks=None,
             scene_drops=None, drop_looks=None, flag_spots=None, lake_looks=None, silver_looks=None,
             ammo_rupee=False, flag_own=()):
    """Turns {OoTR location: OoTR item} into make_patch plan sections. A location is a drop_map "drops" or "new" entry
    or an "extras" key. Returns {"placements": [{"file", "hash", "set", "remove"}], "gamedata": {"reset_type":
    {hash: 24}}}. Raises DropPlanError on anything unsupported.
    Drop objects get Dynamic.Drop__DropActor (any named drop table removed). Their save flag is made permanent (88
    area reset / 280 enemy -> 24) unless the item is one of REPEATABLE_ITEMS, so the object keeps coming back and the
    item can never be lost, or the object is in a reset group or has no flag. Gold Skulltulas keep their flag.
    Freestanding pickups change type (Gyaml).
    With allow "checked_on_pickup", every drop spot respawn_capable accepts takes the respawn model instead
    (CHECKED_ARRAY: its bit, Presence, vanilla twin and save rows; plan "_drops_respawn" for verify_respawn and the
    tracker). Also with it, a non-repeatable item with a save-on-take pickup at a spot picks_up_checked accepts adds
    pickup_save_ops ("ainb", "packs", "byml") for the dropper and pickup types involved, and "_checked_on_pickup"
    lists them (a note for the spoiler, make_patch ignores it).
    "Nothing" (remake_empty_object_contents): `empty` "vanilla" leaves the object as it is with its own drop, and
    "nothing" gives it the empty table (Drop__DropTable "None", any Drop__DropActor removed, OoTR's GI_NOTHING).
    Other modes replace OoTR's "Nothing" before the plan.
    An "Ice Trap" at a drop spot (remake_drop_ice_traps): `ice` "classic" is ice_trap_drop's enemy or stand-in, and
    "disguised" is the disguise carrier (DISGUISE_ACTOR, its tag query answers `fallthrough`).
    The other arguments:
    - `scene`: locations among `assignments` whose item the get scene gives (entries with "get_scene"). They keep
      their pickup and get get_scene_ops (a placement Name, the tag query's name check). The scene steps themselves
      belong to the get-scene hook (tools/rando/parity/_songs_trade_lake.py).
    - `overrides`: the plugin's entries for names whose drop-map entry a setting changes (lookup).
    - `named`: extra get-scene spots named only to keep their vanilla answer (entries with "get_scene" carrying
      "value").
    - `fallthrough` ({pack: tag}) goes to get_scene_ops.
    - `disguise_names`: locations whose Ice Trap is the disguised one whatever `ice` says (OoTR's "Nothing" turned
      into an ice trap by remake_empty_object_contents "ice_trap").
    - `looks` ({location: item_display spec or None}, remake_item_looks "item"): the get-scene spots among `scene`
      show their item (look_ops). The plan records them in "_drops_looks" for in_game_check.
    - `disguise_looks` ([item_display spec], with `fallthrough`): what the disguised ice trap may look like (look_ops
      "disguise", plan "_drops_looks_disguise").
    - `scene_drops` ({location: tag}, remake_drop_contents "all"): drop spots whose item the get scene gives. The
      object drops the disguise carrier with its tag (DROP_TAG_KEY on the placement, pickup_save_ops tags), and the
      plan records them in "_drops_scene_drops".
    - `drop_looks` ({tag: item_display spec or None}): what each of those shows ("_drops_looks_tags").
    - `flag_own`: flagless drop spots whose junk drops as its own pickup (Flagless pickups). Each gets a
      CHECKED_ARRAY bit that the pickup records when taken (plan "_drops_flagless_own").
    - `ammo_rupee` ("Ammo Without Its Bag: Blue Rupee"): our container-ammo pickups show the Blue Rupee while no
      container is owned (Type-based displays). Droppers get no AMMO SWITCH, since their drop is the engine's read of
      Drop__DropActor and the pickup's take gives the Blue Rupee.
    - `lake_looks` ({LAKE_LOOK location: item_display spec}): the two lake pickups show the item they give (Lake
      pickups).
    - `silver_looks` ({silver token Name: item_display spec}): the silver-rupee tokens holding an item
      (remake_silver_rupee_items) show it, with their own sparkle (Silver rupee displays)."""
    scene_drops = dict(scene_drops or {})
    flag_spots = dict(flag_spots or {})  # {location: borrowed saved flag}: flagless drops (scene drops with own tags)
    flag_own = set(flag_own or ())  # flagless drops that use their own pickup
    own_rec = {}  # Flagless pickups: {location: {"bit", "actor", "placements"}}
    fl_visits, fl_exps = flagless_visits(flag_spots), {}  # their twins wait for the visit's end (VISIT)
    gates = set()  # dropper types holding flagless drops
    components = set()  # types given a Drop component (DROP_COMPONENT) because one of their objects drops something
    m = drop_map or _map()
    place, reset, touched = [], {}, {}
    twins, chk_bits, chk_exps, chk_rows, respawn_rec = [], {}, {}, {}, {}  # the respawn model
    joins = []  # (reset-group member, its twin): the twin joins the group (group_join_ops)
    groups = {}  # reset actor hash -> {"targets", "dirs"}: objects the plan takes out of their reset group
    cop_spots, dropped = [], []  # checked-on-pickup spots; (entry, actor) of every drop spot
    switch_ai = set()  # Ammo container check: root AI files of droppers holding container ammo
    drop_at_types = set()  # dropper types some placement of which makes its drop elsewhere (DROP_AT_*)
    scene_spots, scene_names = [], []
    for name, item in assignments.items():
        e = lookup(name, m, overrides)
        if e is None:
            raise DropPlanError(f"{name}: not a location in drop_map.json")
        if name in scene:
            if "get_scene" not in e or not usable(e, allow):
                raise DropPlanError(f"{name}: no get-scene pickup here")
            for p in e["placements"]:
                key = (p["file"], p["hash"])
                if key in touched and touched[key] != name:
                    raise DropPlanError(f"{name}: placement {p['hash']} also belongs to {touched[key]}")
                touched[key] = name
            scene_spots.append(e)
            scene_names.append(name)
            continue
        if e.get("mode") in ("vanilla", "absent", "blocked") or ("vanilla" in e and e.get("mode") is None
                                                                   and not e.get("type")):
            if item == e.get("vanilla"):
                continue
            raise DropPlanError(f"{name}: not paired ({e.get('why')}); it can only keep its vanilla {e.get('vanilla')}")
        if item == "Nothing" and name not in scene_drops and name not in flag_spots:
            # A scene drop holding Nothing is handled below. It drops the carrier, whose get scene gives nothing.
            if e.get("vanilla") != "Nothing":  # the object would keep giving its vanilla rupees or token
                raise DropPlanError(f"{name}: Nothing here would leave its vanilla {e.get('vanilla')}")
            if empty == "vanilla":
                continue  # OoTR's empty spot: the object keeps its own (random) drop
            if empty != "nothing" or e.get("kind") != "drop" or not can_be_empty(e, m) or empty_in_vanilla(e):
                raise DropPlanError(f"{name}: Nothing can't be made empty here ({empty})")
            for p in e["placements"]:
                key = (p["file"], p["hash"])
                if key in touched and touched[key] != name:
                    raise DropPlanError(f"{name}: placement {p['hash']} also belongs to {touched[key]}")
                touched[key] = name
                op = {"file": p["file"], "hash": p["hash"], "set": {"Dynamic.Drop__DropTable": EMPTY_TABLE}}
                if p.get("drop"):
                    op["remove"] = ["Dynamic.Drop__DropActor"]
                place.append(op)
            continue
        if item == e.get("vanilla") and e["kind"] == "drop" and e["placements"][0]["category"] == "gold_skulltula":
            continue  # a token in its own skulltula: nothing to do
        missing = set(e.get("blockers", [])) - set(allow)
        if missing:
            raise DropPlanError(f"{name}: blocked by {sorted(missing)} (pass allow=... to accept)")
        actor = remake_drop(item)
        if name in flag_own:  # Flagless pickups: its own pickup, a checked bit the pickup sets when taken
            if name in flag_spots or name in scene_drops or flagless_own_actor(e, item) != actor:
                raise DropPlanError(f"{name}: {item} can't drop as its own pickup at this flagless spot")
            gates |= {p["actor"] for p in e["placements"]}
        elif name in flag_spots:  # no flag of its own, so a borrowed flag, the carrier and the scene
            if name not in scene_drops or e["kind"] != "drop" or not flagless_capable(e):
                raise DropPlanError(f"{name}: no flagless drop here (types: {sorted(FLAGLESS_DROPPERS)})")
            gates |= {p["actor"] for p in e["placements"]}
            actor = DISGUISE_ACTOR
        elif name in scene_drops:  # any item, as the carrier, given by the get scene for its tag
            if e["kind"] != "drop" or not (picks_up_checked(e) or respawn_capable(e)) or \
                    "checked_on_pickup" not in allow:
                raise DropPlanError(f"{name}: no scene drop here (a checked-on-pickup or respawn-model drop spot only)")
            actor = DISGUISE_ACTOR
        elif item == "Ice Trap" and (ice == "disguised" or name in disguise_names):
            if e["kind"] != "drop":
                raise DropPlanError(f"{name}: a disguised ice trap needs a drop spot (placed pickups take ice traps "
                                    f"through the get scene)")
            actor = DISGUISE_ACTOR
        elif item == "Ice Trap":
            actor, how = ice_trap_drop(e)
            if actor is None:
                raise DropPlanError(f"{name}: ice trap: {how}")
        if actor is None:
            raise DropPlanError(f"{name}: {item} has no world-pickup form in the remake (remake_drop)")
        if e["kind"] == "drop":
            dropped.append((e, actor))
        area = e.get("area")
        if item in KEY_AREA and KEY_AREA[item] != area and name not in scene_drops:
            raise DropPlanError(f"{name}: {item} can only go to a location inside its own dungeon ({KEY_AREA[item]})")
        is_gs = all(p["category"] == "gold_skulltula" for p in e["placements"])
        # The respawn model (OoTR / SoH). The object keeps respawning as in vanilla until its item is taken, then its
        # vanilla twin stands there (CHECKED_ARRAY). Any item, repeatable or not.
        respawn = ("checked_on_pickup" in allow and not is_gs and name not in flag_spots and respawn_capable(e))
        # checked on pickup: the dropper comes back until this item is taken (pickup_save_ops)
        checked = respawn or ("checked_on_pickup" in allow and picks_up_checked(e) and saves_on_pickup(actor)
                              and not repeatable(item, actor) and not (is_gs and actor == "Obj_Token_Gold"))
        if checked:
            cop_spots.append(e)
        if actor == "Obj_Token_Gold" and not is_gs and not checked and "token_outside_skulltula" not in allow:
            raise DropPlanError(f"{name}: a token outside a skulltula is untested (allow 'token_outside_skulltula')")
        respawns = spot_respawns(e)
        if respawns and not repeatable(item, actor) and not (is_gs and actor == "Obj_Token_Gold") and not checked \
                and name not in flag_spots and name not in flag_own and "once_items_at_respawn_spots" not in allow:
            raise DropPlanError(f"{name}: the object comes back, so {item} would drop again "
                                f"(allow 'once_items_at_respawn_spots')")
        keep_coming_back = item in REPEATABLE_ITEMS
        if respawn or name in flag_own:  # Flagless pickups use the same array and counter
            bit = len(chk_bits) + 1
            chk_bits[name] = bit
            if bit >= FLAGLESS_VISIT0:  # VISIT_ARRAY holds both: a spot's visit bit is its checked bit
                raise DropPlanError(f"{name}: checked bit {bit} reaches the flagless visit bits ({FLAGLESS_VISIT0})")
        for p in e["placements"]:
            key = (p["file"], p["hash"])
            if key in touched and touched[key] != name:
                raise DropPlanError(f"{name}: placement {p['hash']} also belongs to {touched[key]}")
            touched[key] = name
            if e["kind"] == "freestanding":
                if actor == "Obj_Heart_Piece" and p["actor"] in HEART_PIECE_VARIANTS:
                    continue  # the spot's own heart-piece type
                if actor not in e.get("allowed_actors", []):
                    raise DropPlanError(f"{name}: {actor} is not placed in {p['file']} yet (allowed: "
                                        f"{', '.join(e.get('allowed_actors', []))}); a type new to a level broke it before")
                if actor == p["actor"]:
                    continue
                accepts = set(m["actor_keys"].get(actor, []))
                drop = [f"Dynamic.{k}" for k in p.get("dynamic_keys", []) if k not in accepts]
                op = {"file": p["file"], "hash": p["hash"], "set": {"Gyaml": actor}}
                if drop:
                    op["remove"] = drop
                place.append(op)
            else:
                op = {"file": p["file"], "hash": p["hash"], "set": {}}
                if not (p["drop"] == actor and not p["drop_table"]):
                    op["set"]["Dynamic.Drop__DropActor"] = actor
                    if name in scene_drops:
                        op["set"][f"Dynamic.{DROP_TAG_KEY}"] = float(scene_drops[name])
                    if name in flag_own:  # Flagless pickups: its bit goes with the drop and the object's gate reads it
                        op["set"][f"Dynamic.{DROP_CHK_KEY}"] = bit
                        (exp, steps), (texp, tsteps) = _flagless_own_exps(bit)
                        prec = {"file": p["file"], "hash": str(p["hash"]), "kind": FLAGLESS_DROPPERS[p["actor"]][0]}
                        if prec["kind"] == "presence":  # gone from the next load once taken, its twin from the next
                            op["set"]["Presence"] = {"FlagName": exp, "IsCheckLazy": False, "IsNegation": True}
                            chk_exps[exp], chk_exps[texp] = steps, tsteps
                            tw = _flagless_bit_twin(p, texp)
                            twins.append(tw)
                            prec.update(presence=op["set"]["Presence"], twin=tw["twin"],
                                        twin_presence=tw["set"]["Presence"])
                        else:  # a tree: counts itself as shaken while its bit is set (_tree_edits)
                            op["set"][f"Dynamic.{DROP_FLAG_KEY}"] = CHECKED_ARRAY
                        own_rec.setdefault(name, {"bit": bit, "actor": actor, "placements": []})["placements"].append(
                            prec)
                    elif name in flag_spots:
                        if FLAGLESS_DROPPERS[p["actor"]][0] == "presence":  # hidden once checked
                            op["set"]["Presence"] = {"FlagName": flag_spots[name], "IsCheckLazy": False,
                                                     "IsNegation": True}  # its vanilla twin shows from the next load
                            v = fl_visits[name]
                            fl_exps[FLAGLESS_EXP.format(v)] = [[0, flag_spots[name]], [8, VISIT_ARRAY, v], [5], [3]]
                            twins.append(_flagless_twin(p, flag_spots[name], v))
                        else:
                            op["set"][f"Dynamic.{DROP_FLAG_KEY}"] = flag_spots[name]
                    if p["actor"] in DROP_COMPONENT:
                        components.add(p["actor"])
                        op["set"]["Dynamic.Drop__DropTable"] = EMPTY_TABLE  # actor + "None", as the Gerudo guards have
                    elif p["drop_table"]:
                        op["remove"] = ["Dynamic.Drop__DropTable"]
                at = drop_at_of(p) if not (is_gs and actor == "Obj_Token_Gold") else None
                if at is not None:  # Reachable drop positions: made at the floor nearest under it that Link reaches
                    op["set"][f"Dynamic.{DROP_AT_KEY}"] = True
                    op["set"].update({f"Dynamic.{k}": float(v) for k, v in zip(DROP_AT_XYZ, at)})
                    drop_at_types.add("Enemy_Skulltula_Gold" if p["category"] == "gold_skulltula" else p["actor"])
                if respawn:  # its bit, its Presence, its vanilla twin, its save rows
                    sets, twin, fields, rec = _respawn_ops(p, bit, actor, chk_exps,
                                                           with_twin=_respawn_ok(p, len(e["placements"]) > 1) is None)
                    op["set"].update(sets)
                    if twin:
                        twins.append(twin)
                        if p.get("reset_group") or p.get("ungroup"):  # the twin refills with the room as its source did
                            # A respawn spot is never taken out of its group, "ungroup" only names it.
                            joins.append((p, twin["twin"]))
                    for h_, f_ in fields.items():
                        if h_ in chk_rows and chk_rows[h_] != f_:
                            raise DropPlanError(f"{name}: save row {h_} planned as {chk_rows[h_]} and {f_}")
                    chk_rows.update(fields)
                    respawn_rec.setdefault(name, {"bit": bit, "placements": []})["placements"].append(rec)
                if op["set"] or op.get("remove"):
                    place.append(op)
                if respawn:
                    continue  # no permanent flag, no ungrouping: it respawns as in vanilla until checked
                if is_gs or keep_coming_back or p.get("reset_group") or p["flag"] is None:
                    continue  # the object keeps coming back (the item rule allows repeatable items only)
                if p["flag"] in (88, 280):
                    reset[p["hash"]] = 24
                elif p["flag"] != 24:
                    raise DropPlanError(f"{name}: {p['hash']} has save flag type {p['flag']}, not supported")
                if p.get("ungroup"):  # remake_reset_group_objects "one_time": out of its reset group too
                    g = groups.setdefault(str(p["ungroup"]), {"targets": set(), "dirs": set()})
                    g["targets"].add(str(p["hash"]))
                    g["dirs"].add(os.path.dirname(p["file"]))
    out = {"placements": place + twins}
    if groups:
        ug = ungroup_ops(groups, romfs or DEFAULT_ROMFS)
        out["placements"] += ug["placements"]
        out["byml"] = out.get("byml", []) + ug["byml"]
        out["_drops_ungrouped"] = {h: sorted(g["targets"]) for h, g in sorted(groups.items())}
    if joins:
        j = group_join_ops(joins, romfs or DEFAULT_ROMFS)
        out["placements"] += j["placements"]
        out["byml"] = out.get("byml", []) + j["byml"]
        out["_drops_group_twins"] = j["record"]
    if reset:
        out["gamedata"] = {"reset_type": reset}
    if chk_bits:  # the respawn model's save data: the checked bits, an expression per spot, the rows' resets
        out.setdefault("gamedata", {}).update({
            "add_bool_arrays": {CHECKED_ARRAY: max(chk_bits.values()) + 1},
            "add_runtime_bool_arrays": {VISIT_ARRAY: max(chk_bits.values()) + 1},
            "add_boolexp": dict(sorted(chk_exps.items())),
            "per_object": {h: f for h, f in sorted(chk_rows.items()) if not f.get("new")},
            "add_per_object": {h: {k: v for k, v in f.items() if k != "new"}
                               for h, f in sorted(chk_rows.items()) if f.get("new")}})
        out["_drops_respawn"] = {"array": CHECKED_ARRAY, "visit": VISIT_ARRAY, "size": max(chk_bits.values()) + 1,
                                 "spots": dict(sorted(respawn_rec.items())), "exps": dict(sorted(chk_exps.items()))}
    # objects a story or kill flag deletes (the Goron City wall crack, the HF open grotto crate, HF Tree 7)
    borrowed = {str(p["hash"]): flag for n, flag in flag_spots.items()
                for p in (lookup(n, m, overrides) or {}).get("placements", [])}
    gate = logic_delete_ops({**respawn_rec, **own_rec}, borrowed)  # Flagless pickups: a bit, like the respawn model
    if gate:
        out["ainb"] = out.get("ainb", []) + gate["ainb"]
        out.setdefault("gamedata", {}).setdefault("add_boolexp", {}).update(gate["boolexp"])
        out["_drops_logic_delete"] = gate["record"]
    if own_rec:  # Flagless pickups: read back by verify_flagless_own (its bits share _drops_respawn's array and exps)
        out["_drops_flagless_own"] = dict(sorted(own_rec.items()))
    if fl_exps:  # the flagless twins' expressions and the visit bits the get scene sets (VISIT)
        gd = out.setdefault("gamedata", {})
        gd.setdefault("add_boolexp", {}).update(sorted(fl_exps.items()))
        visits = gd.setdefault("add_runtime_bool_arrays", {})
        visits[VISIT_ARRAY] = max(visits.get(VISIT_ARRAY, 0), max(fl_visits.values()) + 1)
    if twins and any(t["hash"] not in {r["hash"] for v in respawn_rec.values() for r in v["placements"]}
                     for t in twins):
        out["_drops_flagless_twins"] = sorted(f"{t['file']}#{t['hash']}->{t['twin']}" for t in twins
                                              if "Presence" in t["set"] and t["set"]["Presence"]["FlagName"]
                                              in set(flag_spots.values()))
    if cop_spots or gates:
        # The dropper types of those spots stop saving on break everywhere, so every pickup any of their objects
        # drops in this seed saves on take too. A one-time pot holding a purple rupee comes back until it's taken.
        def kind(p):
            return "Enemy_Skulltula_Gold" if p["category"] == "gold_skulltula" else p["actor"]
        types = {kind(p) for e in cop_spots for p in e["placements"]} | gates
        pickups = {a for e, a in dropped if any(kind(p) in types for p in e["placements"])}
        for k, v in pickup_save_ops(types, pickups, romfs or DEFAULT_ROMFS, tags=bool(scene_drops),
                                    gates=gates).items():
            if k == "_sets_checked":  # setters write CHECKED_ARRAY (bit 0 at least: what a dropper without a bit hands)
                arrays = out.setdefault("gamedata", {}).setdefault("add_bool_arrays", {})
                arrays[CHECKED_ARRAY] = max(arrays.get(CHECKED_ARRAY, 0), 1)
                visits = out["gamedata"].setdefault("add_runtime_bool_arrays", {})  # and VISIT_ARRAY
                visits[VISIT_ARRAY] = max(visits.get(VISIT_ARRAY, 0), 1)
                continue
            out[k] = out.get(k, []) + v if isinstance(v, list) else v
        out["_checked_on_pickup"] = {"droppers": sorted(types), "pickups": sorted(pickups)}
    # Ammo container check: the dropper root AIs. generate adds the chests' and builds them with ammo_switch_ops.
    if switch_ai:
        out["_ammo_switch"] = {"ai": [[pk if pk == "*" else list(pk), f] for pk, f in sorted(switch_ai, key=str)]}
    if components:  # icicles, red ice, silver rocks: a Drop component wherever one of them drops something
        # ... and on every type sharing an edited root AI. The two icicle types run one file, so the other one would
        # read keys its pack doesn't have.
        shared = {PICKUP_SAVE_DROPPERS[t][0] for t in components if t in PICKUP_SAVE_DROPPERS}
        components |= {t for t in DROP_COMPONENT if t in PICKUP_SAVE_DROPPERS and PICKUP_SAVE_DROPPERS[t][0] in shared}
        tree = any(FLAGLESS_DROPPERS.get(g, (None,))[0] == "tree" for g in gates)
        saved = any(a != "Enemy_Skulltula_Gold" and FLAGLESS_DROPPERS.get(a, (None,))[0] != "tree"
                    for a in (out.get("_checked_on_pickup") or {}).get("droppers", []))
        for k, v in drop_component_ops(components, romfs or DEFAULT_ROMFS, bool(scene_drops), flag_key=tree,
                                       save_key=saved, at_keys=bool(drop_at_types)).items():
            out[k] = out.get(k, []) + v
        out["_drops_components"] = sorted(components)
    shown = [(e, (looks or {})[n]) for n, e in zip(scene_names, scene_spots) if (looks or {}).get(n)]
    scene_spots += list(named)
    if scene_drops:
        out["_drops_scene_drops"] = dict(sorted(scene_drops.items()))
    if flag_spots:
        out["_drops_flag_spots"] = dict(sorted(flag_spots.items()))
    if scene_spots or fallthrough or scene_drops:  # heart spots, the disguise carrier, scene drops
        gs = get_scene_ops(scene_spots, romfs or DEFAULT_ROMFS, m.get("actor_keys"), fallthrough,
                           drop_tags=sorted(set(scene_drops.values())))
        out["placements"] += gs["placements"]
        out["ainb"] = out.get("ainb", []) + gs["ainb"]
    touch = sorted({(e["get_scene"].get("as") or p["actor"]) for e in scene_spots for p in e["placements"]}
                   & set(HEART_TOUCH_TYPES))
    for actor in touch:  # the heart spots' heart pieces are taken by touch (HEART_TOUCH_TYPES)
        out["packs"] = out.get("packs", []) + heart_touch_ops(actor, romfs or DEFAULT_ROMFS)
    if touch:
        out["_drops_heart_touch"] = touch
    if fallthrough:  # the disguised trap's freeze creates the ice-trap attacker (generate.py adds it once)
        out["_ice_sensor"] = True
    dis = None
    tag_looks = {t: d for t, d in (drop_looks or {}).items() if d and t in set(scene_drops.values())}
    if (fallthrough and disguise_looks) or tag_looks:  # the carrier's own placements keep the look their name gives
        dis = {"actor": DISGUISE_ACTOR, "displays": list(disguise_looks or []) if fallthrough else [],
               "tags": tag_looks,
               "skip": sorted({e["get_scene"]["name"] for e in scene_spots
                               if (e["get_scene"].get("as") or e["placements"][0]["actor"]) == DISGUISE_ACTOR})}
    lake = [(n, d) for n, d in sorted((lake_looks or {}).items()) if d]
    silver = [(n, d) for n, d in sorted((silver_looks or {}).items()) if d]
    tlooks = ammo_type_looks(out["placements"], romfs or DEFAULT_ROMFS) if ammo_rupee else None  # Type-based displays
    if tlooks:
        out["_drops_looks_types"] = {t: {"turn": AMMO_RUPEE, "owners": d["tiers"][0][0]}  # (Ammo-to-rupee conversion)
                                     for t, d in tlooks.items()}
    # After the get-scene edits, since the event AI's hide step is edited on top of the tag query's.
    if shown or dis or lake or silver or tlooks:
        spots = [{"name": e["get_scene"]["name"], "carrier": e["get_scene"].get("as") or e["placements"][0]["actor"],
                  "display": d, "water": under_water(e["placements"], romfs or DEFAULT_ROMFS)} for e, d in shown]
        lake_spots = [{"name": LAKE_LOOK[n]["name"], "carrier": LAKE_LOOK[n]["actor"], "display": d,
                       "water": under_water([LAKE_LOOK[n]], romfs or DEFAULT_ROMFS)} for n, d in lake]
        for n, _ in lake:  # the letter gets its name (as LAKE_GUARD gives it), the arrow is named "Item" in vanilla
            if LAKE_LOOK[n]["set_name"]:
                out["placements"].append({"file": LAKE_LOOK[n]["file"], "hash": LAKE_LOOK[n]["hash"],
                                          "set": {"Name": LAKE_LOOK[n]["name"]}})
        if any(n == "LH Sun" for n, _ in lake):  # the arrow is taken by touch, as the moat's Ocarina of Time
            out["packs"] = out.get("packs", []) + touch_attention_ops(LAKE_LOOK["LH Sun"]["actor"], romfs or DEFAULT_ROMFS)
        spots += lake_spots
        spots += [{"name": n, "carrier": SILVER_TOKEN, "display": d, "water": True} for n, d in silver]
        if any(s["water"] for s in spots):
            out["_drops_looks_water"] = {"spots": sorted(s["name"] for s in spots if s["water"])}
        wrapped = {op["file"] for op in out.get("ainb", []) for ed in op.get("edits", []) if "wrap" in ed}
        sv = {SILVER_AI: SILVER_UPDATE} if silver else None
        lo = look_ops(spots, romfs or DEFAULT_ROMFS, wrapped, dis, attach=sv,
                      pickup_delete={SILVER_AI: SILVER_PICKUP} if silver else None,
                      type_looks={"ai": LOOK_TYPE_AI, "looks": tlooks} if tlooks else None)
        out["packs"] = out.get("packs", []) + lo["packs"]
        out["ainb"] = out.get("ainb", []) + lo["ainb"]
        lake_names = {s["name"] for s in lake_spots} | {n for n, _ in silver}  # (their own plan sections)
        if silver:
            out["_drops_looks_silver"] = {"ai": SILVER_AI, "update": SILVER_UPDATE, "pickup": SILVER_PICKUP,
                                          "looks": {n: {"carrier": SILVER_TOKEN, "shows": sorted(_shows(d))}
                                                    for n, d in silver}}
        if any(s["name"] not in lake_names for s in spots):
            out["_drops_looks"] = {s["name"]: {"carrier": s["carrier"], "shows": sorted(_shows(s["display"]))}
                                   for s in spots if s["name"] not in lake_names}
        if lake_spots:
            out["_drops_looks_lake"] = {s["name"]: {"carrier": s["carrier"], "shows": sorted(_shows(s["display"])),
                                                    "location": n} for (n, _), s in zip(lake, lake_spots)}
        if dis and dis["displays"]:
            out["_drops_looks_disguise"] = {"carrier": dis["actor"], "skip": dis["skip"],
                                            "shows": sorted(set().union(*(_shows(d) for d in dis["displays"])))}
        if dis and dis["tags"]:
            out["_drops_looks_tags"] = {str(t): sorted(_shows(d)) for t, d in sorted(dis["tags"].items())}
    if scene_drops:  # the heart pickups' AIs grow most with scene drops
        out["byml"] = out.get("byml", []) + heart_heap_ops(romfs or DEFAULT_ROMFS)
    if drop_at_types:  # Reachable drop positions
        out["ainb"] = out.get("ainb", []) + drop_at_ops(drop_at_types)
        out["_drops_at"] = sorted(f"{op['file']}#{op['hash']}" for op in place
                                  if (op.get("set") or {}).get(f"Dynamic.{DROP_AT_KEY}"))
    fixed = fixed_drop_ops(out["placements"], romfs or DEFAULT_ROMFS)  # Guaranteed named drops
    if fixed:
        out["_drops_fixed"] = fixed
    res = drop_resource_ops(out["placements"], romfs or DEFAULT_ROMFS)  # Drop preloading
    for k, v in res.items():
        out[k] = out.get(k, []) + v if isinstance(v, list) else v
    falls = sorted({a for _, a in dropped if a in FALL_TYPES})
    if falls:  # Falling pickups: the carrier (and the Fire Arrows pickup) dropped by an object fall to the ground
        fo = fall_ops(falls, romfs or DEFAULT_ROMFS)
        out["packs"] = out.get("packs", []) + fo["packs"]
        out["byml"] = out.get("byml", []) + fo["byml"]
        out["_drops_fall"] = falls
    return out


def _shows(display):
    """Every display actor a look spec can create."""
    return {display["actor"]} if "actor" in display else {t[1] for t in display["tiers"]}


def main(argv):
    romfs = argv[1] if len(argv) > 1 else DEFAULT_ROMFS
    out = build(romfs)
    c = out["counts"]
    print(f"{len(out['drops'])} OoTR locations ({', '.join(TYPES)}):")
    for t, modes in c["ootr"].items():
        print(f"  {t:13s} " + ", ".join(f"{n} {m}" for m, n in sorted(modes.items())))
    print(f"remake objects as new OoTR locations: {len(out['new'])} "
          + ", ".join(f"{t} {sum(v.values())}" for t, v in c["new"].items()))
    if out["warnings"]:
        print(f"{len(out['warnings'])} warnings: " + "; ".join(out["warnings"][:5]))
    print(f"written to {os.path.relpath(OUT, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
