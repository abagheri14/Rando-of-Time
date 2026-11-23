"""Build data/rando/entrances_remake.json: OoT Randomizer's entrances -> the remake's level transitions.

usage: python tools/rando/parity/_entrances_build.py ROMFS

How the remake moves between levels:
- A level ("banc") change is a FieldAndDungeonEntranceEventRequestActor (FADE for short) placed in a level's
  *_Static file. Its Dynamic settings name the destination for each age (NextBancParamNameChild/Adult), the
  start position there (NextStartPosName, a row of Banc/BancBasedResource/StartPos), the scene played before
  leaving (FirstEventName) and on arrival (NextEventName), first-visit scenes (InitEventFlag/InitEventName,
  AddEventFlag/AddEventName), the "alternative" level variant flag (IsAlternativeGameDataBool) and whether an
  underwater "_Air" start position may be used (IsChangableAirPos). Child and adult levels are separate files,
  each with its own FADE for the same doorway. A FADE is named after the start position next to it, which is
  where the way back arrives.
- Scenes change levels with GameSystemActor.EventReserveBancChange (NextBanc, NextStartPos, BootEventName). That
  covers warp songs (Dm_SY_Ocarina :OcarinaWarp calls), blue warps (Dm_SY_BancChange_EscapeDungeon), the Death
  Mountain owl, Jabu-Jabu swallowing Link and minigames.
- Houses, shops, grottos, graves, the Gerudo hideout, boss rooms and Ganon's tower are inside the same level as
  the area around them. Doors open into rooms modelled in place and grottos move Link inside the level
  (HidingHole_Entry/Exit scenes and linked DestinationAnchors), so there's no transition to retarget for them.

This script reads the game files and the hand-made table below (OoTR entrance -> FADE names). For each OoTR
entrance it writes the FADEs to edit when the entrance is moved (sources) and where it leads in vanilla (target,
per age). Run it again after a game update.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "entrances_remake.json")
FADE = "FieldAndDungeonEntranceEventRequestActor"

# OoTR entrance -> (level base name, [FADE names]) or [(level base, [names]), ...] when the doorway's FADEs live in
# different levels per age. The first name is the one whose destination is used as the vanilla target; the rest
# are other doorways of the same OoTR entrance (moved together).
FADES = {
    # dungeons
    "KF Outside Deku Tree -> Deku Tree Lobby": ("KokiriForest", ["FrontDekuTree"]),
    "Deku Tree Lobby -> KF Outside Deku Tree": ("InsideTheDekuTree", ["Entrance"]),
    "Death Mountain -> Dodongos Cavern Beginning": ("DeathMountainTrail", ["MountainTrail_DodongoCavernSide"]),
    "Dodongos Cavern Beginning -> Death Mountain": ("DodongoCavern", ["DodongoCavern_MountainTrailSide"]),
    "Zoras Fountain -> Jabu Jabus Belly Beginning": ("ZoraFountain", ["ZoraFountain_FromInsideJabuJabuBelly"]),
    "Jabu Jabus Belly Beginning -> Zoras Fountain": ("InsideJabuJabuBelly", ["InsideJabuJabuBelly_FromZoraFountain"]),
    "SFM Forest Temple Entrance Ledge -> Forest Temple Lobby": ("SacredForestMeadow", ["OutsideOfForestTemple"]),
    "Forest Temple Lobby -> SFM Forest Temple Entrance Ledge": ("ForestTemple", ["ForestTemple"]),
    "DMC Fire Temple Entrance -> Fire Temple Lower": ("DeathMountainCrater", ["OutsideOfFireTemple"]),
    "Fire Temple Lower -> DMC Fire Temple Entrance": ("FireTemple", ["FireTemple"]),
    "Lake Hylia -> Water Temple Lobby": ("HyruleField", ["OutsideOfWaterTemple"]),
    "Water Temple Lobby -> Lake Hylia": ("WaterTemple", ["WaterTemple_FromLakeHylia"]),
    "Graveyard Warp Pad Region -> Shadow Temple Entryway": ("Graveyard", ["GraveYard_ShadowTempleSide"]),
    "Shadow Temple Entryway -> Graveyard Warp Pad Region": ("ShadowTemple", ["Entrance"]),
    "Desert Colossus -> Spirit Temple Lobby": ("DesertColossus", ["DesertColossus_FromSpiritTempleEntrance"]),
    "Spirit Temple Lobby -> Desert Colossus From Spirit Lobby": ("SpiritTemple", ["SpiritTemple_Entrance"]),
    "Kakariko Village -> Bottom of the Well": ("KakarikoVillage", ["Kakariko_WellSide"]),
    "Bottom of the Well -> Kakariko Village": ("BottomOfTheWell", ["Well_KakarikoSide"]),
    "ZF Ice Ledge -> Ice Cavern Beginning": ("ZoraFountain", ["ZoraFountain_FromIceCavern",
                                                              "ZoraFountain_FromIceCavern_Backdoor"]),
    "Ice Cavern Beginning -> ZF Ice Ledge": ("IceCavern", ["IceCavern_FromZoraFountain",
                                                           "IceCavern_FromZoraFountain_Backdoor"]),
    "Gerudo Fortress -> Gerudo Training Ground Lobby": ("GerudoFortress", ["GerudoFortress_FromGerudoTrainingGround"]),
    "Gerudo Training Ground Lobby -> Gerudo Fortress": ("GerudoTrainingGround",
                                                        ["GerudoTrainingGround_FromGerudoFortress"]),
    "Ganons Castle Ledge -> Ganons Castle Lobby": ("GanonCastle", ["GanonCastleEntrance_FromInside"]),
    "Ganons Castle Lobby -> Castle Grounds From Ganons Castle": ("InsideGanonCastle", ["Entrance"]),
    # overworld
    "Kokiri Forest -> Lost Woods": ("KokiriForest", ["KokiriForest_FrontOfLostWood"]),
    "LW Forest Exit -> Kokiri Forest": ("LostWood", ["LostWood_Entrance", "*"]),  # "*": the unnamed wrong-way exits
    "Lost Woods -> GC Woods Warp": ("LostWood", ["LostWood_GoronCitySide_before", "LostWood_GoronCitySide_after"]),
    "GC Woods Warp -> Lost Woods": ("GoronCity", ["GoronCity_LostWoodSide_before", "GoronCity_LostWoodSide_after"]),
    "Lost Woods -> Zora River": ("LostWood", ["LostWood_ZoraRiverSide"]),
    "Zora River -> LW Underwater Entrance": ("ZoraRiver", ["ZoraRiver_LostWoodSide"]),
    "LW Beyond Mido -> SFM Entryway": ("LostWood", ["LostWood_FrontOfSacredForestMeadow"]),
    "SFM Entryway -> LW Beyond Mido": ("SacredForestMeadow", ["SacredForestMeadow_FrontOfLostWood"]),
    "LW Bridge -> Hyrule Field": ("KokiriForest", ["LostWoodBridge_FrontOfHyruleField"]),
    "Hyrule Field -> LW Bridge": ("HyruleField", ["HyruleField_FrontOfLostWoodBridge"]),
    "Hyrule Field -> Gerudo Valley": ("HyruleField", ["HyruleField_FrontOfGerudoValley"]),
    "Gerudo Valley -> Hyrule Field": ("GerudoValley", ["GerudoValley_Entrance"]),
    "Hyrule Field -> Market Entrance": ("HyruleField", ["HyruleField_FrontOfMarket"]),
    "Market Entrance -> Hyrule Field": ("Market", ["Market_Entrance"]),
    "Hyrule Field -> Kakariko Village": ("HyruleField", ["HyruleField_FrontOfKakarikoVillage"]),
    "Kakariko Village -> Hyrule Field": ("KakarikoVillage", ["KakarikoVillage_Entrance"]),
    "Hyrule Field -> ZR Front": ("HyruleField", ["HyruleField_FrontOfZoraRiver",
                                                 "HyruleField_FrontOfZoraRiver_UnderWater"]),
    "ZR Front -> Hyrule Field": ("ZoraRiver", ["ZoraRiver_Entrance", "ZoraRiver_Entrance_UnderWater"]),
    "Lake Hylia -> Zoras Domain": ("HyruleField", ["ZoraLakeHylia_FromZoraDomain"]),
    "Zoras Domain -> Lake Hylia": ("ZoraDomain", ["ZoraDomain_FromLakeHylia"]),
    "GV Fortress Side -> Gerudo Fortress": ("GerudoValley", ["GerudoValley_FromGerudoFortress"]),
    "Gerudo Fortress -> GV Fortress Side": ("GerudoFortress", ["GerudoFortress_FromGerudoValley"]),
    "GF Outside Gate -> Wasteland Near Fortress": ("GerudoFortress", ["GerudoFortress_FromHountedWasteland"]),
    "Wasteland Near Fortress -> GF Outside Gate": ("HountedWasteland", ["HountedWasteland_FromGerudoFortress"]),
    "Wasteland Near Colossus -> Desert Colossus": ("HountedWasteland", ["HountedWasteland_FromDesertColossus"]),
    "Desert Colossus -> Wasteland Near Colossus": ("DesertColossus", ["DesertColossus_FromHountedWasteland"]),
    "Market -> Castle Grounds": ("Market", ["Market_FrontOfHyruleCastle", "Market_Entrance_FromCastle"]),
    "Castle Grounds -> Market": [("HyruleCastle", ["HyruleCastle_Entrance"]), ("GanonCastle", ["GanonCastleEntrance"])],
    "Kakariko Village -> Graveyard": ("KakarikoVillage", ["Kakariko_GraveYardSide"]),
    "Graveyard -> Kakariko Village": ("Graveyard", ["GraveYard_KakarikoSide"]),
    "Kak Behind Gate -> Death Mountain": ("KakarikoVillage", ["Kakariko_MountainTrailSide"]),
    "Death Mountain -> Kak Behind Gate": ("DeathMountainTrail", ["MountainTrail_KakarikoSide"]),
    "Death Mountain -> Goron City": ("DeathMountainTrail", ["MountainTrail_GoronCitySide"]),
    "Goron City -> Death Mountain": ("GoronCity", ["GoronCity_MountainTrailSide"]),
    "GC Darunias Chamber -> DMC Lower Local": ("GoronCity", ["GoronCity_CraterSide"]),
    "DMC Lower Nearby -> GC Darunias Chamber": ("DeathMountainCrater", ["Crater_GoronCitySide"]),
    "Death Mountain Summit -> DMC Upper Local": ("DeathMountainTrail", ["MountainTrail_CraterSide"]),
    "DMC Upper Nearby -> Death Mountain Summit": ("DeathMountainCrater", ["Crater_MountainTrailSide"]),
    "ZR Behind Waterfall -> Zoras Domain": ("ZoraRiver", ["ZoraRiver_FromZoraDomain"]),
    "Zoras Domain -> ZR Behind Waterfall": ("ZoraDomain", ["ZoraDomain_FromZoraRiver"]),
    "ZD Behind King Zora -> Zoras Fountain": ("ZoraDomain", ["ZoraDomain_FromZoraFountain"]),
    "Zoras Fountain -> ZD Behind King Zora": ("ZoraFountain", ["ZoraFountain_FromZoraDomain"]),
    "GV Lower Stream -> Lake Hylia": ("GerudoValley", ["GerudoValley_FromLakeHylia"]),
}

# OoTR entrances that are one continuous area in the remake (no transition between the two sides).
SEAMLESS = {
    "Kokiri Forest -> LW Bridge From Forest": "the Lost Woods bridge is part of the Kokiri Forest level",
    "LW Bridge -> Kokiri Forest": "the Lost Woods bridge is part of the Kokiri Forest level",
    "Hyrule Field -> Lake Hylia": "Lake Hylia is part of the Hyrule Field level",
    "Lake Hylia -> Hyrule Field": "Lake Hylia is part of the Hyrule Field level",
    "Hyrule Field -> Lon Lon Ranch": "Lon Lon Ranch is part of the Hyrule Field level",
    "Lon Lon Ranch -> Hyrule Field": "Lon Lon Ranch is part of the Hyrule Field level",
    "Market Entrance -> Market": "the market entrance and the market are one level",
    "Market -> Market Entrance": "the market entrance and the market are one level",
    "Market -> ToT Entrance": "the Temple of Time and its courtyard are part of the Market level",
    "ToT Entrance -> Market": "the Temple of Time and its courtyard are part of the Market level",
}
INSIDE_LEVEL = {  # OoTR entrance types the remake has inside one level (see module docstring)
    "Interior": "houses and shops are modelled in place; the door opens into the room (no level change)",
    "SpecialInterior": "houses and shops are modelled in place; the door opens into the room (no level change)",
    "Hideout": "the Thieves' Hideout is part of the Gerudo Fortress level",
    "Grotto": "grottos are rooms under the same level; HidingHole_Entry/Exit scenes move Link inside the level",
    "Grave": "graves are rooms under the Graveyard level, entered inside the level",
    "ChildBoss": "boss rooms are part of their dungeon's level (no level change at the boss door)",
    "AdultBoss": "boss rooms are part of their dungeon's level (no level change at the boss door)",
    "SpecialBoss": "Ganon's tower is part of the InsideGanonCastle level",
}

# Levels only one age can stand in (the other age's start positions are missing or the level forces the age).
ADULT_ONLY = {"GerudoFortress_Adult", "GanonCastle"}
CHILD_ONLY = {"HyruleCastle"}
SINGLE_AGE_FILES = {"HyruleCastle": "child", "GanonCastle": "adult"}

# One-way arrivals with no FADE destination, as (level base, start position, arrival scene).
ONE_WAY_ARRIVALS = {
    "Minuet of Forest Warp -> Sacred Forest Meadow": ("SacredForestMeadow", "ForestMinuet", "OcarinaWarp_Arrive"),
    "Bolero of Fire Warp -> DMC Central Local": ("DeathMountainCrater", "FireBolero", "OcarinaWarp_Arrive"),
    "Serenade of Water Warp -> Lake Hylia": ("HyruleField", "WaterSerenade", "OcarinaWarp_Arrive"),
    "Requiem of Spirit Warp -> Desert Colossus": ("DesertColossus", "SpiritRequiem", "OcarinaWarp_Arrive"),
    "Nocturne of Shadow Warp -> Graveyard Warp Pad Region": ("Graveyard", "ShadowNocturne", "OcarinaWarp_Arrive"),
    "Prelude of Light Warp -> Temple of Time": ("Market", "LightPrelude", "OcarinaWarp_Arrive"),
    # blue warp landing spots as one-way targets (start positions both ages have, near the remake's landing)
    "Queen Gohma Blue Warp -> KF Outside Deku Tree": ("KokiriForest", "FrontDekuTree", "Dm_SY_BancChangeArrive"),
    "King Dodongo Blue Warp -> Death Mountain": ("DeathMountainTrail", "DodongoCavernFront", "Dm_SY_BancChangeArrive"),
    "Barinade Blue Warp -> Zoras Fountain": ("ZoraFountain", "ZoraFountain_FromZoraDomain", "Dm_SY_BancChangeArrive"),
    # the remake's Forest Temple blue warp lands near the Deku Tree (KokiriForest_Adult/WarpFromForestTemple)
    "Phantom Ganon Blue Warp -> Sacred Forest Meadow": ("KokiriForest", "FrontDekuTree", "Dm_SY_BancChangeArrive"),
    "Volvagia Blue Warp -> DMC Central Local": ("DeathMountainCrater", "FireBolero", "Dm_SY_BancChangeArrive"),
    "Morpha Blue Warp -> Lake Hylia": ("HyruleField", "WaterSerenade", "Dm_SY_BancChangeArrive"),
    "Bongo Bongo Blue Warp -> Graveyard Warp Pad Region": ("Graveyard", "ShadowNocturne", "Dm_SY_BancChangeArrive"),
    "Twinrova Blue Warp -> Desert Colossus": ("DesertColossus", "SpiritRequiem", "Dm_SY_BancChangeArrive"),
    # owl landings. The LH owl lands in Hyrule Field (start position named for arriving from the lake), and the DMT
    # owl lands on Impa's roof, a start position only child Kakariko has
    "LH Owl Flight -> Hyrule Field": ("HyruleField", "HyruleField_FromLakeHylia", "Dm_SY_BancChangeArrive"),
    "DMT Owl Flight -> Kak Impas Rooftop": ("KakarikoVillage", "FromMountainTrail", "Dm_DeathMtTrail_0035"),
    # spawns and the few rooms with a start position inside
    "Child Spawn -> KF Links House": ("KokiriForest", "", "Dm_SY_BancChangeArrive"),
    "Adult Spawn -> Temple of Time": ("Market", "LightPrelude", "Dm_SY_BancChangeArrive"),
    "Kokiri Forest -> KF Links House": ("KokiriForest", "", "Dm_SY_BancChangeArrive"),
    "ToT Entrance -> Temple of Time": ("Market", "LightPrelude", "Dm_SY_BancChangeArrive"),
    # OoTR's "Extra" targets
    "ZD Eyeball Frog Timeout -> Zoras Domain": ("ZoraDomain", "ZoraDomain_FromZoraRiver", "Dm_SY_BancChangeArrive"),
    "ZR Top of Waterfall -> Zora River": ("ZoraRiver", "ZoraRiver_LostWoodSide", "Dm_SY_BancChangeArrive"),
}

# The scene a FADE plays before leaving (FirstEventName), by what it is for:
#   source: belongs to where Link leaves from (diving, Jabu's mouth, Lost Woods fog, race checks...): kept.
#   dest:   a wrapper around the generic exit that prepares the destination (Kakariko cucco reset, Goron City
#           after the Fire Temple, the Zora at Zora's Fountain, the market soldier): follows the destination.
GO_EVENTS = {
    "Dm_SY_BancChangeGo": {"family": "plain", "dest": None},
    "Dm_SY_BancChangeGo_KakarikoVillage": {"family": "plain", "dest": "Kak"},
    "DeathMountainTrail_ToGoronCity": {"family": "plain", "dest": "GC_DMT"},
    "DeathMountainCrater_ToGoronCity": {"family": "plain", "dest": "GC_DMC"},
    "Dm_SY_BancChangeGo_ZoraFountain": {"family": "plain", "dest": "ZF"},
    "Dm_SY_BancChangeGo_RunningRace_01": {"family": "race", "dest": None},
    "Dm_SY_BancChangeGo_RunningRace_03": {"family": "race", "dest": "Kak"},
    "BancChangeGo_Market": {"family": "race", "dest": "Market"},
    # kept as they are (source side)
    "Dm_SY_BancChangeGo_UnderWater": {"family": "source"},
    "Dm_SY_BancChangeGo_RunningRace": {"family": "source"},
    "Dm_SY_BancChangeGo_RunningRace_02": {"family": "source"},
    "Dm_SY_BancChangeGo_ToInsideJabujabu": {"family": "source"},
    "Dm_SY_BancChangeGo_InsideJabujabu": {"family": "source"},
    "Dm_SY_BancChangeGo_LostWood": {"family": "source"},
    "Dm_SY_BancChangeGo_HyruleCastle": {"family": "source"},
    "Dm_SY_BancChangeGo_GanonCastle": {"family": "source"},
    "Dm_SY_BancChangeGo_MarketToCastle": {"family": "source"},
    "GerudoTrainingGround_LeaveGerudoFortress_Confirm": {"family": "source"},
    "UnderTheGrave_DampeReset": {"family": "source"},
    "EscapeFromCrumblingGanonCastle_EscapeComplete": {"family": "source"},
}
GO_BY_FAMILY = {"plain": {None: "Dm_SY_BancChangeGo", "Kak": "Dm_SY_BancChangeGo_KakarikoVillage",
                          "GC_DMT": "DeathMountainTrail_ToGoronCity", "GC_DMC": "DeathMountainCrater_ToGoronCity",
                          "ZF": "Dm_SY_BancChangeGo_ZoraFountain", "Market": "Dm_SY_BancChangeGo"},
                "race": {None: "Dm_SY_BancChangeGo_RunningRace_01", "Kak": "Dm_SY_BancChangeGo_RunningRace_03",
                         "Market": "BancChangeGo_Market", "GC_DMT": "Dm_SY_BancChangeGo_RunningRace_01",
                         "GC_DMC": "Dm_SY_BancChangeGo_RunningRace_01", "ZF": "Dm_SY_BancChangeGo_RunningRace_01"}}

# Destination settings a FADE carries for where it leads (copied from the target's vanilla FADE when retargeted).
DEST_FIELDS = ("NextEventName", "InitEventFlag", "InitEventName", "AddEventFlag", "AddEventName",
               "IsAlternativeGameDataBool")

# Scene-driven transitions edited with "events" ops.
EVENTS = {
    "warp_songs": {
        "Minuet of Forest Warp -> Sacred Forest Meadow": {"file": "Dm_SY_Ocarina", "event": "Event77"},
        "Bolero of Fire Warp -> DMC Central Local": {"file": "Dm_SY_Ocarina", "event": "Event15"},
        "Serenade of Water Warp -> Lake Hylia": {"file": "Dm_SY_Ocarina", "event": "Event16"},
        "Requiem of Spirit Warp -> Desert Colossus": {"file": "Dm_SY_Ocarina", "event": "Event17"},
        "Nocturne of Shadow Warp -> Graveyard Warp Pad Region": {"file": "Dm_SY_Ocarina", "event": "Event18"},
        "Prelude of Light Warp -> Temple of Time": {"file": "Dm_SY_Ocarina", "event": "Event20"},
    },
    # the DMT owl changes level in its talk scene; the LH owl lands inside the Hyrule Field level
    "owls": {
        "DMT Owl Flight -> Kak Impas Rooftop": {"file": "Npc_Kaepora_DeathMountainTrail", "event": "Event45",
                                                "preload": "Event53"},
        "LH Owl Flight -> Hyrule Field": {"file": "Npc_Kaepora_LakeHylia", "after_flight": "Event19",
                                          "landing": "Event22"},
    },
    # Jabu-Jabu swallowing Link (fish) changes level from Get_StoneOfWater; the FADE is used afterwards
    "jabu_first_entry": {"entrance": "Zoras Fountain -> Jabu Jabus Belly Beginning", "file": "Get_StoneOfWater",
                         "event": "Event1", "boot": "Get_StoneOfWater_ArriveJabuJabuBelly"},
    "spawns": {
        "Child Spawn -> KF Links House": {"file": "OpeningEvent", "after": "Event11", "next": "Event12",
                                          "note": "new file: the opening scene ends in Link's house"},
        "Adult Spawn -> Temple of Time": {"file": "Market_Child_Field_ChildToAdult", "event": "Event0",
                                          "note": "time travel lands in the Temple of Time with its story scene"},
    },
}

# Blue warps: where the remake's own blue-warp scenes (Dm_SY_BancChange_EscapeDungeon) land, as OoTR regions.
# The landing scenes complete the dungeon's story stage and are staged in that level, so they stay vanilla.
BLUE_WARPS = {
    "Queen Gohma Blue Warp -> KF Outside Deku Tree": ("KF Outside Deku Tree", "KokiriForest_Child/WarpFromDekuTree"),
    "King Dodongo Blue Warp -> Death Mountain": ("Death Mountain", "DeathMountainTrail_*/DodongoCavernFront"),
    "Barinade Blue Warp -> Zoras Fountain": ("Zoras Fountain", "ZoraFountain_Child/ClearJabuJabu"),
    "Phantom Ganon Blue Warp -> Sacred Forest Meadow": ("KF Outside Deku Tree",
                                                        "SageRoom, then KokiriForest_Adult/WarpFromForestTemple"),
    "Volvagia Blue Warp -> DMC Central Local": ("DMC Central Local", "SageRoom, then DeathMountainCrater_Adult/FireBolero"),
    "Morpha Blue Warp -> Lake Hylia": ("Lake Hylia", "SageRoom, then HyruleField_Adult/WaterSerenade"),
    "Bongo Bongo Blue Warp -> Graveyard Warp Pad Region": ("Graveyard Warp Pad Region",
                                                           "SageRoom, then Graveyard_Adult/ShadowNocturne"),
    "Twinrova Blue Warp -> Desert Colossus": ("Desert Colossus", "SageRoom, then DesertColossus_Adult/SpiritRequiem"),
}


def level_files(levels, base):
    """[(level name, file)] of a level base: KokiriForest -> KokiriForest_Child, _Adult; GanonCastle -> itself."""
    out = []
    for name, rel in levels.items():
        if name == base or re.fullmatch(re.escape(base) + r"_(Child|Adult|Adult_Alternative)", name):
            out.append((name, rel))
    return sorted(out)


def age_of(level):
    if level.endswith("_Child"):
        return "child"
    if level.endswith(("_Adult", "_Adult_Alternative")):
        return "adult"
    return SINGLE_AGE_FILES.get(level, "both")


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    startpos = byml_load(fs.read("Banc/BancBasedResource/StartPos.byml.zs"))[0]
    levels, actors = {}, {}
    for area in sorted(os.listdir(os.path.join(romfs, "Banc"))):
        d = os.path.join(romfs, "Banc", area)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            m = re.match(r"(.+)_Static\.bcett\.byml\.zs$", fn)
            if not m:
                continue
            rel = f"Banc/{area}/{fn}"
            levels[m.group(1)] = rel
            actors[m.group(1)] = [a for a in byml_load(fs.read(rel))[0].get("Actors", []) if a.get("Gyaml") == FADE]
    banc_paths = {}
    for fn in os.listdir(os.path.join(romfs, "Banc", "GameBancParam")):
        name = fn.split(".")[0]
        p = byml_load(fs.raw(f"Banc/GameBancParam/{fn}"))[0]
        banc_paths[name] = (p.get("Banc") or {}).get("Main")

    def has_start(level, sp):
        return level in startpos and sp in startpos[level]

    used = set()
    entrances = {}
    for ent, spec in FADES.items():
        parts = spec if isinstance(spec, list) else [spec]
        sources, by_age = [], {}
        for base, names in parts:
            for level, rel in level_files(levels, base):
                primary_done = False  # the first listed name present in this level is its main doorway
                for nm in names:
                    if nm == "*":  # unnamed FADEs of the level leading where the first one leads
                        first = next(a for a in actors[level] if a.get("Name") == names[0])
                        hits = [a for a in actors[level] if not a.get("Name") and
                                (a.get("Dynamic") or {}).get("NextStartPosName") ==
                                first["Dynamic"]["NextStartPosName"]]
                    else:
                        hits = [a for a in actors[level] if a.get("Name") == nm]
                    for a in hits:
                        d = dict(a.get("Dynamic") or {})
                        used.add(int(a["Hash"]))
                        primary = not primary_done and nm != "*"
                        src = {"file": rel, "hash": str(a["Hash"]), "name": a.get("Name", ""), "level": level,
                               "age": age_of(level), "primary": primary, "vanilla": d}
                        sources.append(src)
                        if primary:
                            primary_done = True
                            if not level.endswith("_Alternative"):
                                for age in ("child", "adult"):
                                    if src["age"] in (age, "both"):
                                        by_age.setdefault(age, src)
        if not sources:
            raise SystemExit(f"{ent}: no FADE found for {spec}")
        target = {}
        for age in ("child", "adult"):
            # a doorway only one age can use (its level is single-age) still names both ages' destinations
            src = by_age.get(age) or next((s for s in sources if s["primary"]), None)
            if src is None:
                target[age] = None
                continue
            d = src["vanilla"]
            lvl = d.get("NextBancParamName" + age.capitalize())
            sp = d.get("NextStartPosName")
            bad = (age == "child" and lvl in ADULT_ONLY) or (age == "adult" and lvl in CHILD_ONLY)
            if not lvl or not has_start(lvl, sp) or bad:
                target[age] = None
                continue
            target[age] = {"level": lvl, "start": sp,
                           "fields": {k: d[k] for k in DEST_FIELDS if k in d},
                           "go_dest": GO_EVENTS.get(d.get("FirstEventName"), {}).get("dest"),
                           "air": has_start(lvl, sp + "_Air")}
        entrances[ent] = {"kind": "fade", "sources": sources, "target": target}
    for ent, why in SEAMLESS.items():
        entrances[ent] = {"kind": "seamless", "why": why, "sources": [], "target": None}
    for ent, (base, sp, arrive) in ONE_WAY_ARRIVALS.items():
        target = {}
        for age in ("child", "adult"):
            cands = [lv for lv, _ in level_files(levels, base) if age_of(lv) in (age, "both")
                     and not lv.endswith("_Alternative")]
            lvl = cands[0] if cands else None
            ok = lvl and has_start(lvl, sp) and not ((age == "child" and lvl in ADULT_ONLY) or
                                                      (age == "adult" and lvl in CHILD_ONLY))
            target[age] = {"level": lvl, "start": sp, "fields": {"NextEventName": arrive}, "go_dest": None,
                           "air": has_start(lvl, sp + "_Air")} if ok else None
        if ent in entrances:
            raise SystemExit(f"{ent} is both a doorway and a one-way arrival")
        entrances[ent] = {"kind": "arrival", "sources": [], "target": target}
    # scene steps the plugin edits. We check they exist and find the Prelude-only branches (by melody number 11).
    from evfl import Evfl
    flows = {}

    def flow(name):
        if name not in flows:
            flows[name] = {e["name"]: e for fc in Evfl(fs.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts
                           for e in fc["events"]}
        return flows[name]
    for spec in list(EVENTS["warp_songs"].values()) + list(EVENTS["owls"].values()) + \
            [EVENTS["jabu_first_entry"]] + list(EVENTS["spawns"].values()):
        for key in ("event", "preload", "after_flight", "landing", "after", "next"):
            if key in spec and spec[key] not in flow(spec["file"]):
                raise SystemExit(f"{spec['file']}: no step {spec[key]} (game update?)")
    oc = flow("Dm_SY_Ocarina")
    names = {e["idx"]: n for n, e in oc.items()}
    EVENTS["prelude"] = {
        "file": "Dm_SY_Ocarina",
        # child Prelude after the Spirit-sage scenes: a Temple-of-Time story scene. Its level change takes the
        # song's destination as arguments; a copy with the Temple of Time written in keeps the scene there.
        "story_warp": "Event296",
        "story_switch": "Event297",
        "story_case": next(i for i, c in enumerate(oc["Event297"]["cases"]) if c["value"] == 11),
        "story_next": names[oc["Event296"]["next"]],
        # on arrival, melody 11 (Prelude) runs Temple-of-Time-only scenes (Light Arrows), which get skipped once Prelude
        # moves
        "arrive_switch": "Event147",
        "arrive_case": next(i for i, c in enumerate(oc["Event147"]["cases"]) if c["value"] == 11),
    }
    for k in ("story_warp", "story_switch", "arrive_switch"):
        if EVENTS["prelude"][k] not in oc:
            raise SystemExit(f"Dm_SY_Ocarina: no step {EVENTS['prelude'][k]} (game update?)")
    unmapped = []
    for level, acts in actors.items():
        for a in acts:
            if int(a["Hash"]) not in used and (a.get("Dynamic") or {}).get("NextStartPosName"):
                unmapped.append({"level": level, "name": a.get("Name", ""), "hash": str(a["Hash"]),
                                 "to": a["Dynamic"].get("NextBancParamNameAdult") + "/" + a["Dynamic"]["NextStartPosName"]})
    out = {
        "_about": "Generated by tools/rando/parity/_entrances_build.py from the game files. "
                  "entrances: OoTR entrance -> remake doorways (FADE actors) to edit "
                  "when it is moved (sources) and where it leads in vanilla per age (target: level, start position, "
                  "destination settings). kind seamless: one continuous area in the remake, nothing to move.",
        "inside_level_types": INSIDE_LEVEL,
        "adult_only_levels": sorted(ADULT_ONLY), "child_only_levels": sorted(CHILD_ONLY),
        "go_events": GO_EVENTS, "go_by_family": {f: {str(k): v for k, v in m.items()} for f, m in GO_BY_FAMILY.items()},
        "dest_fields": list(DEST_FIELDS),
        "events": EVENTS,
        "blue_warps": {k: {"region": r, "remake": w} for k, (r, w) in BLUE_WARPS.items()},
        "level_paths": {k: v for k, v in sorted(banc_paths.items()) if v},
        "entrances": entrances,
        "fades_not_in_ootr": unmapped,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, sort_keys=False)
    n_src = sum(len(e["sources"]) for e in entrances.values())
    print(f"wrote {OUT}: {len(entrances)} entrances ({sum(e['kind'] == 'fade' for e in entrances.values())} with "
          f"doorways, {n_src} doorway actors), {len(unmapped)} doorways OoTR doesn't have")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
