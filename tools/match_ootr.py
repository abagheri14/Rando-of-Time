"""Match OoT Randomizer's vanilla locations to the remake's reward locations.

usage: python tools/match_ootr.py        (reads reference/ootr/logic.json and data/locations.json)

Writes data/ootr_match.json and data/ootr_match.csv. Each OoTR location gets a status:
  exact        one remake location with the same area, check type and vanilla item
  group        several OoTR and remake locations share area/type/item (e.g. the 5 Gold Skulltulas of a
               dungeon, three rupee chests): the set matches, which-is-which still needs pairing by hand
  area_set     same area and check type, but the vanilla item changed in the remake (e.g. junk chests):
               the leftover OoTR and remake checks of that area/type pair up as a set
  area_set_count_differs  as above, with a different number on each side (checks added or removed)
  event_item_differs  the right NPC/event file, but it gives a different item in the remake
  ambiguous_event  several remake events give that item and none is clearly the one (needs a hint entry)
  shared_flow  handled by one event the remake shares between many places (cows)
  no_match     nothing in the remake with that item in that area (moved, changed or removed)
Remake locations no OoTR location points at are listed as remake-only (additions or changes).

Matching uses OoTR's area, check type and vanilla item. N64 flags/addresses are never used.
"""
import csv
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
# remake areas that hold places OoTR files under another area
AREA_ALSO = {"InsideGanonCastle": ["GanonCastle"], "SpiritTemple": ["DesertColossus"], "GerudoFortress": ["GerudoValley"]}

KIND = {"Chest": "chest", "GS Token": "gold_skulltula", "Collectable": "freestanding", "BossHeart": "freestanding",
        "Scrub": "scrub", "GrottoScrub": "scrub", "Shop": "shop", "MaskShop": "shop",
        "NPC": "event", "Song": "event", "Cutscene": "event", "Boss": "event"}

# Shared item vocabulary
OOTR_TOKEN = [
    (r"^Rupee.*\(1\)$", "rupee1"), (r"^Rupees.*\(5\)$", "rupee5"), (r"^Rupees.*\(20\)$", "rupee20"),
    (r"^Rupees.*\(50\)$", "rupee50"), (r"^Rupees.*\(200\)$", "rupee200"), (r"^Recovery Heart$", "heart"),
    (r"^(Buy )?Arrows", "arrows"), (r"^(Buy )?Bombs? \(|^Buy Bombs", "bombs"), (r"^(Buy )?Bombchus?", "bombchus"),
    (r"^(Buy )?Deku Nuts? \(", "nuts"), (r"^Buy Deku Stick", "sticks"), (r"^Buy Deku Seeds", "seeds"),
    (r"^(Buy )?Deku Shield$", "deku_shield"), (r"^(Buy )?Hylian Shield$", "hylian_shield"), (r"^Mirror Shield$", "mirror_shield"),
    (r"^Small Key \(Treasure Chest Game\)$", "tcg_key"), (r"^Small Key", "small_key"), (r"^Boss Key", "boss_key"),
    (r"^Map \(", "map"), (r"^Compass \(", "compass"), (r"^Piece of Heart", "heart_piece"), (r"^Heart Container$", "heart_container"),
    (r"^Gold Skulltula Token$", "token"), (r"^Ice Trap$", "ice_trap"),
    (r"^Kokiri Sword$", "kokiri_sword"), (r"^Slingshot$", "slingshot"), (r"^Bow$", "bow"), (r"^Boomerang$", "boomerang"),
    (r"^Bomb Bag$", "bomb_bag"), (r"^Lens of Truth$", "lens"), (r"^Megaton Hammer$", "hammer"), (r"^Hover Boots$", "hover_boots"),
    (r"^Iron Boots$", "iron_boots"), (r"^Ice Arrows$", "ice_arrows"), (r"^Fire Arrows$", "fire_arrows"), (r"^Light Arrows$", "light_arrows"),
    (r"^Progressive Hookshot$", "hookshot"), (r"^Progressive Strength Upgrade$", "strength"), (r"^Progressive Scale$", "scale"),
    (r"^Progressive Wallet$", "wallet"), (r"^Stone of Agony$", "agony"), (r"^Magic Meter$", "magic"), (r"^Double Defense$", "double_defense"),
    (r"^Dins Fire$", "dins_fire"), (r"^Farores Wind$", "farores_wind"), (r"^Nayrus Love$", "nayrus_love"), (r"^Ocarina$", "ocarina"),
    (r"^Zeldas Lullaby$", "song_lullaby"), (r"^Eponas Song$", "song_epona"), (r"^Sarias Song$", "song_saria"), (r"^Suns Song$", "song_sun"),
    (r"^Song of Time$", "song_time"), (r"^Song of Storms$", "song_storms"), (r"^Minuet of Forest$", "song_minuet"),
    (r"^Bolero of Fire$", "song_bolero"), (r"^Serenade of Water$", "song_serenade"), (r"^Requiem of Spirit$", "song_requiem"),
    (r"^Nocturne of Shadow$", "song_nocturne"), (r"^Prelude of Light$", "song_prelude"),
    (r"^Kokiri Emerald$", "stone_forest"), (r"^Goron Ruby$", "stone_fire"), (r"^Zora Sapphire$", "stone_water"),
    (r"^(\w+) Medallion$", lambda m: "medal_" + m.group(1).lower()),
    (r"^Bottle$", "bottle"), (r"^Bottle with Milk$|^Milk$", "milk"), (r"^Rutos Letter$", "ruto_letter"), (r"^Weird Egg$", "weird_egg"),
    (r"^Zeldas Letter$", "zelda_letter"), (r"^Deku Stick Capacity$", "stick_capacity"), (r"^Deku Nut Capacity$", "nut_capacity"),
    (r"^Gerudo Membership Card$", "gerudo_card"), (r"^Biggoron Sword$", "biggoron_sword"), (r"^Giants Knife$", "giants_knife"),
    (r"^Pocket Egg$", "pocket_egg"), (r"^Cojiro$", "cojiro"), (r"^Odd Mushroom$", "odd_mushroom"), (r"^Odd Potion$", "odd_potion"),
    (r"^Poachers Saw$", "poachers_saw"), (r"^Broken Sword$", "broken_sword"), (r"^Prescription$", "prescription"),
    (r"^Eyeball Frog$", "eyeball_frog"), (r"^Eyedrops$", "eyedrops"), (r"^Claim Check$", "claim_check"),
    (r"^(Buy )?Goron Tunic$", "goron_tunic"), (r"^(Buy )?Zora Tunic$", "zora_tunic"), (r"^Buy Magic Bean$", "magic_bean"),
    (r"^(Keaton|Skull|Spooky|Bunny|Goron|Zora|Gerudo) Mask$|^Bunny Hood$", lambda m: "mask_" + m.group(0).split()[0].lower()),
    (r"^Mask of Truth$", "mask_truth"), (r"^Buy (Red|Green|Blue) Potion", lambda m: m.group(1).lower() + "_potion"),
    (r"^Blue Potion$", "blue_potion"), (r"^Buy Heart$", "heart"), (r"^Buy Fish$", "fish"), (r"^Buy Bottle Bug$", "bug"),
    (r"^Buy Poe$", "poe"), (r"^Buy Blue Fire$", "blue_fire"), (r"^Buy Fairy", "fairy"),
]
REMAKE_TOKEN = [
    (r"Rupee_Green$", "rupee1"), (r"Rupee_Blue$", "rupee5"), (r"Rupee_Red$", "rupee20"), (r"Rupee_Purple$", "rupee50"),
    (r"Rupee_Gold$", "rupee200"), (r"^Obj_Heart$|^Shop_Heart$", "heart"),
    (r"ArrowBundle|^Item_Arrow_Normal$", "arrows"), (r"BombBundle|^Item_Bomb$", "bombs"), (r"Bombchu", "bombchus"),
    (r"DekuNutBundle|^Item_DekuNut$", "nuts"), (r"DekuStick", "sticks"), (r"DekuSeed", "seeds"),
    (r"Shield_Deku", "deku_shield"), (r"Shield_Hylian", "hylian_shield"), (r"Shield_Mirror", "mirror_shield"),
    (r"MiniGame_SmallKey", "tcg_key"), (r"SmallKey", "small_key"), (r"BossKey", "boss_key"),
    (r"Dungeon_Map$", "map"), (r"Dungeon_Compass$", "compass"), (r"Heart_Piece", "heart_piece"), (r"Heart_Container", "heart_container"),
    (r"Token_Gold", "token"),
    (r"Sword_Kokiri$", "kokiri_sword"), (r"SlingShot$|BulletBag", "slingshot"), (r"Range_Bow$|Quiver", "bow"), (r"Boomerang", "boomerang"),
    (r"BombBag", "bomb_bag"), (r"GlassTruth", "lens"), (r"Hammer$", "hammer"), (r"HoverBoot", "hover_boots"),
    (r"HeavyBoot", "iron_boots"), (r"Arrow_Ice$", "ice_arrows"), (r"Arrow_Fire$", "fire_arrows"), (r"Arrow_Light$", "light_arrows"),
    (r"Hookshot$|Longshot$", "hookshot"), (r"Gauntlet", "strength"), (r"Scale_", "scale"), (r"Wallet_", "wallet"),
    (r"AgonyStone", "agony"), (r"FairyBless_MP", "magic"), (r"FairyBless_DefenseDouble", "double_defense"),
    (r"DinFire", "dins_fire"), (r"FaroreWind", "farores_wind"), (r"NayruLove", "nayrus_love"), (r"Item_Ocarina_(Fairy|Time)$", "ocarina"),
    (r"Melody_ZeldaLullaby$", "song_lullaby"), (r"Melody_EponaSong$", "song_epona"), (r"Melody_SariaSong$", "song_saria"),
    (r"Melody_SunSong$", "song_sun"), (r"Melody_TimeSong$", "song_time"), (r"Melody_StormSong$", "song_storms"),
    (r"Melody_ForestMinuet$", "song_minuet"), (r"Melody_FireBolero$", "song_bolero"), (r"Melody_WaterSerenade$", "song_serenade"),
    (r"Melody_SpiritRequiem$", "song_requiem"), (r"Melody_ShadowNocturne$", "song_nocturne"), (r"Melody_LightPrelude$", "song_prelude"),
    (r"Stone_Forest$", "stone_forest"), (r"Stone_Fire$", "stone_fire"), (r"Stone_Water$", "stone_water"),
    (r"Medal_(\w+)$", lambda m: "medal_" + m.group(1).lower()),
    (r"^Item_Bottle$|^Weapon_Bottle$", "bottle"), (r"Bottle_Milk$", "milk"), (r"Bottle_Letter$", "ruto_letter"), (r"WeirdEgg", "weird_egg"),
    (r"ZeldaLetter", "zelda_letter"), (r"StickBag", "stick_capacity"), (r"NutBag", "nut_capacity"), (r"Token_Gerudo", "gerudo_card"),
    (r"Sword_Biggoron$", "biggoron_sword"), (r"Sword_Giant$", "giants_knife"),
    (r"PocketEgg", "pocket_egg"), (r"CojiroCucco", "cojiro"), (r"OddMushroom", "odd_mushroom"), (r"OddPowder", "odd_potion"),
    (r"PoacherSaw", "poachers_saw"), (r"BrokenSword", "broken_sword"), (r"Prescription", "prescription"),
    (r"EyeballFrog", "eyeball_frog"), (r"EyeDrop", "eyedrops"), (r"ClaimCheck", "claim_check"),
    (r"Armor_Goron$", "goron_tunic"), (r"Armor_Zora$", "zora_tunic"), (r"MagicBean", "magic_bean"),
    (r"Mask_(Keaton|Skull|Spooky|Bunny|Goron|Zora|Gerudo)$", lambda m: "mask_" + m.group(1).lower()),
    (r"Mask_Truth$", "mask_truth"), (r"Bottle_(Red|Green|Blue)Potion$", lambda m: m.group(1).lower() + "_potion"),
    (r"Bottle_Fish$", "fish"), (r"Bottle_Bug$", "bug"), (r"Bottle_Poe$", "poe"), (r"Bottle_BlueFire$", "blue_fire"),
    (r"Bottle_Fairy$", "fairy"), (r"MagicJar", "magic_jar"),
]

# where OoTR's NPC/song/cutscene/boss checks live among the remake's event files. The remake swaps two Great
# Fairies, so DMT plays Dm_FairyFountain_Din and HC plays Dm_FairyFountain_Power.
EVENT_HINTS = [
    (r"Lost Dog", r"FindRichard"), (r"Frogs in the Rain|Frogs Ocarina Game|ZR Frogs", r"FrogTenors"),
    (r"LW Ocarina Memory Game", r"Npc_SkullKid_Child_02"), (r"LW Skull Kid", r"Npc_SkullKid_Child$|Npc_SkullKid_Child/"),
    (r"Fishing", r"MiniGame_Fishing"), (r"Bombchu Bowling", r"BombchuBowling"), (r"Gold Skulltula Reward", r"GatheringTokenGold"),
    (r"Dampe", r"Dampe"), (r"Diving Minigame", r"MiniGame_Diving"), (r"Shooting Gallery", r"HitTarget"),
    (r"HBA", r"HorsebackArchery"), (r"HC Great Fairy", r"FairyFountain_Power"), (r"DMT Great Fairy", r"FairyFountain_Din"),
    (r"DMC Great Fairy", r"FairyFountain_Wisdom"), (r"ZF Great Fairy", r"FairyFountain_Frore"),
    (r"Colossus Great Fairy", r"FairyFountain_Nayru"), (r"OGC Great Fairy", r"FairyFountain_Courage"),
    (r"Biggoron", r"Biggoron"), (r"Medigoron", r"Medigoron"), (r"Deku Theater Skull", r"SkullMask"), (r"Deku Theater Mask of Truth", r"TrueMask"),
    (r"Target in Woods", r"Dm_LostWood_0040"), (r"Talons Chickens", r"FindOutCucco"), (r"Anju as Child", r"CatchCucco"),
    (r"Malon Egg", r"Goto_HyruleCastle"), (r"HC Zeldas Letter", r"HrlCastle"),
    (r"Ocarina of Time Item", r"Dm_MelodyGet_Time"), (r"Song from Ocarina of Time", r"Dm_MelodyGet_Time"),
    (r"Gift from Saria", r"Dm_Kokiri_0155"), (r"Light Arrows", r"Dm_TimeTemple"), (r"Rauru", r"SageRoom"),
    (r"Darunias Joy", r"Dm_Goron"), (r"Rolling Goron as Child", r"Npc_Goron_006"), (r"Rolling Goron as Adult", r"SageOfFire"),
    (r"King Zora Thawed", r"SageOfWater"), (r"Gerudo Membership Card", r"Dm_Gerudo"), (r"10 Big Poes", r"BottleShop"),
    (r"Granny Buy Blue Potion", r"Npc_Hylia_053"), (r"Wasteland Bombchu", r"Npc_Hylia_044"),
    (r"Song from Impa", r"Dm_MelodyGet_Zelda"), (r"Song from Malon", r"Dm_MelodyGet_Epona"), (r"Song from Saria", r"Dm_MelodyGet_Saria"),
    (r"Royal Familys Tomb", r"Dm_MelodyGet_Sun"), (r"Windmill", r"Dm_MelodyGet_Storm"), (r"Sheik in Forest", r"Dm_MelodyGet_Forest"),
    (r"Sheik in Crater", r"Dm_MelodyGet_Fire"), (r"Sheik in Ice Cavern", r"Dm_MelodyGet_Water"), (r"Sheik at Colossus", r"Dm_MelodyGet_Spilit"),
    (r"Sheik in Kakariko", r"Dm_MelodyGet_Shadow"), (r"Sheik at Temple", r"Dm_MelodyGet_Shine"),
    (r"Queen Gohma", r"Dm_Kokiri_0130"), (r"King Dodongo", r"Dm_DeathMtTrail_0025"), (r"Barinade", r"Dm_ZoraFountain|Dm_InsideJabu"),
    (r"Phantom Ganon", r"Dm_Awake_Forest"), (r"Volvagia", r"Dm_Awake_Fire"), (r"Morpha", r"Dm_Awake_Water"),
    (r"Bongo Bongo", r"Dm_Awake_Shadow"), (r"Twinrova", r"Dm_Awake_Spirit"),
]


def token(name, table):
    if not name:
        return None
    for rx, t in table:
        m = re.search(rx, name)
        if m:
            return t(m) if callable(t) else t
    return "?" + name


def main():
    ootr = json.load(open(os.path.join(HERE, "reference", "ootr", "logic.json"), encoding="utf-8"))["locations"]
    locs = json.load(open(os.path.join(HERE, "data", "locations.json"), encoding="utf-8"))
    # remake side: one entry per check. A business scrub's 1-3 offers are one check; its first offer names it.
    remake, seen_scrub = [], {}
    for L in locs:
        if L["dreamworld"]:
            continue
        L = dict(L, token=token(L["item"], REMAKE_TOKEN))
        if L["kind"] == "scrub":
            inst = L["location"].rsplit("/", 1)[0]
            if inst in seen_scrub:
                seen_scrub[inst]["offers"].append(L["location"])
                continue
            L.update(location=inst, offers=[L["location"]])
            seen_scrub[inst] = L
        remake.append(L)

    rows = []
    for name, v in ootr.items():
        if v["type"] not in KIND or "MQ" in str(v.get("logic_file")) or v.get("vanilla_item") is None:
            continue
        kind = KIND[v["type"]]
        if v["type"] == "NPC" and "Cows" in (v.get("categories") or []):
            kind = "cow"
        rows.append({"ootr": name, "type": v["type"], "ootr_area": v.get("area"), "region": v.get("region"),
                     "vanilla": v["vanilla_item"], "token": token(v["vanilla_item"], OOTR_TOKEN),
                     "kind": kind, "area": AREA.get(v.get("area")), "remake": [], "status": None})

    used = defaultdict(list)  # remake location -> ootr names

    def take(r, cands, status):
        r["remake"], r["status"] = [c["location"] for c in cands], status
        for c in cands:
            used[c["location"]].append(r["ootr"])

    # Pass 1 matches placements by area, check type, and vanilla item.
    pool = defaultdict(list)
    for L in remake:
        if L["kind"] != "event" and not L["shared"]:
            pool[(L["area"], L["kind"])].append(L)
    o_bucket = defaultdict(list)
    for r in rows:
        if r["kind"] not in ("event", "cow"):
            o_bucket[(r["area"], r["kind"], r["token"])].append(r)
    for (area, kind, tok), rs in o_bucket.items():
        cands = [L for a in [area] + AREA_ALSO.get(area, []) for L in pool[(a, kind)] if L["token"] == tok]
        n, m = len(rs), len(cands)
        if not m:
            continue
        if n == m or (kind == "shop" and m % n == 0 and m // n <= 3):  # shops: child and adult shelves are separate
            status = "exact" if n == 1 and m == 1 else "group"
            for r in rs:
                take(r, cands, status + (" (child+adult shelves)" if kind == "shop" and m > n else ""))
            for c in cands:
                c["_taken"] = True
    # Pass 2 groups leftover placements by area and check type.
    left = defaultdict(list)
    for r in rows:
        if r["kind"] not in ("event", "cow") and r["status"] is None:
            left[(r["area"], r["kind"])].append(r)
    for (area, kind), rs in left.items():
        if kind == "freestanding":
            for r in list(rs):
                in_drop = [L for a in [area] + AREA_ALSO.get(area, []) for L in pool[(a, "drop")]
                           if L["token"] == r["token"] and not L.get("_taken")]
                if len(in_drop) == 1:
                    take(r, in_drop, "exact (inside a pot/crate/rock)")
                    in_drop[0]["_taken"] = True
                    rs.remove(r)
        cands = [L for a in [area] + AREA_ALSO.get(area, []) for L in pool[(a, kind)] if not L.get("_taken")]
        for r in rs:
            if not cands:
                take(r, [], "no_match")
            else:
                take(r, cands, "area_set" if len(rs) == len(cands) else "area_set_count_differs")
        for c in cands:
            c["_taken"] = True

    # Events, matched by item and event-file hint, with shared flows as the fallback.
    events = [L for L in remake if L["kind"] == "event"]
    for r in rows:
        if r["kind"] == "cow":
            take(r, [L for L in events if "Animal_Cow" in L["location"]], "shared_flow")
            continue
        if r["kind"] != "event":
            continue
        hint = next((fx for nx, fx in EVENT_HINTS if re.search(nx, r["ootr"])), None)
        same_item = [L for L in events if L["token"] == r["token"]]
        if hint:
            cands = [L for L in same_item if re.search(hint, L["location"])]
            cands = [L for L in cands if not L["shared"]] or cands
            if not cands:  # the right event file, but it gives something else in the remake
                cands = [L for L in events if re.search(hint, L["location"])]
                if cands:
                    take(r, cands, "event_item_differs")
                    continue
        else:
            cands = [L for L in same_item if not L["shared"]] or same_item
        if not cands:  # some OoTR "NPC" checks are placed items in the remake (Ruto's Letter, Fire Arrows)
            cands = [L for L in remake if L["kind"] == "freestanding" and L["area"] == r["area"] and L["token"] == r["token"]]
        files = {L["location"].split("/")[1] for L in cands if L["kind"] == "event"}
        if not cands:
            status = "no_match"
        elif len(cands) == 1 or (len(files) == 1 and all(L["kind"] == "event" for L in cands)):
            status = "exact"  # one event file; several parts are upgrade tiers (e.g. bullet bag medium/large)
        else:
            status = "ambiguous_event"
        take(r, cands, status)

    remake_only = [L for L in remake if L["location"] not in used and L["kind"] in
                   ("chest", "gold_skulltula", "freestanding", "scrub", "shop", "event")]
    summary = defaultdict(lambda: defaultdict(int))
    for r in rows:
        summary[r["area"] or r["ootr_area"]][r["status"]] += 1
    for L in remake_only:
        summary[L["area"] or "(events)"]["remake_only"] += 1

    out = {"ootr_locations": rows,
           "remake_only": [{k: L.get(k) for k in ("location", "kind", "area", "item", "shared")} for L in remake_only],
           "summary": {str(a): dict(s) for a, s in sorted(summary.items(), key=lambda x: str(x[0]))}}
    json.dump(out, open(os.path.join(HERE, "data", "ootr_match.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.path.join(HERE, "data", "ootr_match.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ootr_location", "ootr_type", "ootr_region", "vanilla_item", "remake_area", "status", "remake_locations"])
        for r in sorted(rows, key=lambda r: (str(r["area"]), r["type"], r["ootr"])):
            w.writerow([r["ootr"], r["type"], r["region"], r["vanilla"], r["area"] or "", r["status"], " | ".join(r["remake"])])
        for L in remake_only:
            w.writerow(["", "", "", L["item"], L["area"] or "", "remake_only", L["location"]])

    tot = defaultdict(int)
    for r in rows:
        tot[r["status"]] += 1
    print(f"{len(rows)} OoTR checks: " + ", ".join(f"{k} {n}" for k, n in sorted(tot.items())))
    ro = defaultdict(int)
    for L in remake_only:
        ro[L["kind"]] += 1
    print(f"{len(remake_only)} remake checks with no OoTR counterpart: " + ", ".join(f"{k} {n}" for k, n in sorted(ro.items())))


if __name__ == "__main__":
    main()
