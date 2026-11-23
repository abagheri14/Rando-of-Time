"""Gossip Stone pairing: every OoT Randomizer stone -> the remake stone standing where OoTR put it.

usage: python tools/rando/parity/_hints_stones.py ROMFS             rebuild data/rando/hints_stones.json and
                                                                     data/rando/logic/hints.json from the game
       python tools/rando/parity/_hints_stones.py ROMFS --check     compare both files with the game
       python tools/rando/parity/_hints_stones.py ROMFS --verify OUT
                                     read back a built seed (OUT/plan.json, OUT/spoiler.json, OUT/patch): every
                                     OoTR stone's hint on its paired label, none for absent stones

How a stone picks its text: GossipStone:Talk -> Event18 Npc_EventStarter.EventTalkWithInstanceNameLabel
{MstxtName='GossipStone'}, so the message is EventFlowMsg/GossipStone.msbt:<placement Name>. Every talkable stone
is an Obj_GossipStone_A_01 placement named GOSSIP_<AREA>_NN (no Dynamic parameter picks another label), and the
area in the name isn't where the stone stands (GOSSIP_LOST_WOOD_01 is in a Zora's River grotto...). So the pairing
goes by placement: level file, position, grotto. A grotto is a room under its own level. The HidingHole_Entry_01
EventRequestActor links to a HidingHole_HoleEntrance DestinationAnchor (the landing point inside), and the cover on
the entrance says how it opens (cover_kind). OoTR's stones and regions come from vendor/ootr/Hints.py
gossipLocations, the LocationList.py HintStone entries and data/World/Overworld.json.

Result: 40 remake stones, and 41 placements because the stone
by the Lost Woods bridge is placed in both the Kokiri Forest and the Lost Woods level with one label. 36 are paired
with OoTR stones, 4 OoTR stones are absent (the remake has no stone there), and 4 remake stones are ones OoTR
doesn't have (extra). The hints plugin (hints.py) takes the absent stones out of OoTR's stone set and adds the
extras to it as new OoTR stones in their real regions (data/rando/logic/hints.json), so OoTR fills 40 stones like it
always does.
"""
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
OUT = os.path.join(HERE, "data", "rando", "hints_stones.json")
LOGIC = os.path.join(HERE, "data", "rando", "logic", "hints.json")
GOSSIP_FILE = "EventFlowMsg/GossipStone.msbt"

# OoTR stone (Hints.gossipLocations name) -> remake label, level folder, why. build() reads the positions and grottos
# from the level files, and the "why" names the landmark that decides between stones of one area.
PAIRS = {
    "DMC (Bombable Wall)": ("GOSSIP_DEATH_MOUNTAIN_CRATER_01", "DeathMountainCrater",
                            "surface stone 0.9 behind a WallCrack (OoTR: has_explosives)"),
    "DMC (Upper Grotto)": ("GOSSIP_DEATH_MOUNTAIN_CRATER_02", "DeathMountainCrater",
                           "in the DMC grotto under the Obj_BrokenRock_A_01 boulder (the other DMC grotto, under a "
                           "hammer rock, holds Dinolfos and a chest, no stone)"),
    "DMT (Biggoron)": ("GOSSIP_DEATH_MOUNTAIN_TRAIL_02", "DeathMountainTrail",
                       "the summit, 20 units from Npc_Goron_Biggoron_Adult; DMT's only surface stone"),
    "Colossus (Spirit Temple)": ("GOSSIP_DESERT_COLOSSUS_01", "DesertColossus", "Colossus' only stone"),
    "Dodongos Cavern (Bombable Wall)": ("GOSSIP_DODONGO_CAVERN_01", "DodongoCavern",
                                        "room 1 (lobby), 1.8 from a WallCrack; the dungeon's only stone"),
    "GV (Waterfall)": ("GOSSIP_GERUDO_VALLEY_01", "GerudoValley",
                       "6.5 from the waterfall's guardrail and ground; GV's only stone"),
    "GC (Maze)": ("GOSSIP_GORON_CITY_02", "GoronCity",
                  "between the rock maze's chests (z -2.4 and -5.2), walled in by brown, iron and silver rocks"),
    "GC (Medigoron)": ("GOSSIP_GORON_CITY_01", "GoronCity", "4.9 from Medigoron, 8.1 from his room's WallCrack"),
    "Graveyard (Shadow Temple)": ("GOSSIP_GRAVEYARD_01", "Graveyard",
                                  "17 from the GraveYard_ShadowTempleSide entrance; the Graveyard's only stone"),
    "HC (Malon)": ("GOSSIP_HYRULE_CASTLE_01", "HyruleCastle", "12.9 from Malon, 15.7 from Talon"),
    "HC (Rock Wall)": ("GOSSIP_HYRULE_CASTLE_02", "HyruleCastle",
                       "HC's other surface stone, past the guards (soldier 012 at 22)"),
    "HC (Storms Grotto)": ("GOSSIP_HYRULE_FIELD_01", "HyruleCastle",
                           "in HC's Song of Storms grotto, 4.8 behind a WallCrack (OoTR: can_blast_or_smash)"),
    "KF (Outside Storms)": ("GOSSIP_KOKIRI_FOREST_01", "KokiriForest",
                            "surface stone 4.7 from KF's Song of Storms grotto entrance"),
    "KF (Deku Tree Left)": ("GOSSIP_KOKIRI_FOREST_04", "KokiriForest",
                            "both Deku Tree stones stand left (north, -z) of the tree's axis (tree at z -29.6, "
                            "facing +x); this one is further left (z -54.4). Same OoTR region and rule as its twin"),
    "KF (Deku Tree Right)": ("GOSSIP_KOKIRI_FOREST_03", "KokiriForest",
                             "the Deku Tree stone nearer the tree's axis (z -41.8)"),
    "LH (Lab)": ("GOSSIP_LAKE_HYLIA_01", "HyruleField",
                 "Lake Hylia is part of the Hyrule Field level; the stone reached by the bridges in the middle of "
                 "the lake (Land_LakeHrl_Bridge_A_02 at 23), not a corner of the shore"),
    "LH (Southeast Corner)": ("GOSSIP_LAKE_HYLIA_03", "HyruleField",
                              "the southern shore stone (z 579), east of the other corner stone"),
    "LH (Southwest Corner)": ("GOSSIP_LAKE_HYLIA_02", "HyruleField", "the western corner stone (x -331)"),
    "LW (Bridge)": ("GOSSIP_LOST_WOOD_02", "LostWood",
                    "the Lost Woods room by the bridge, 9.7 from the stick-upgrade business scrub (OoTR's LW Deku "
                    "Scrub Near Bridge); the same spot is placed in the Kokiri Forest level too (same label, the "
                    "scrub and the ledge chest at the same offsets)"),
    "SFM (Maze Lower)": ("GOSSIP_SACRED_FOREST_MEADOW_02", "SacredForestMeadow",
                         "maze stone nearer the Lost Woods entrance (z 41; entrance z 74). Same region and rule as "
                         "its twin"),
    "SFM (Maze Upper)": ("GOSSIP_SACRED_FOREST_MEADOW_01", "SacredForestMeadow",
                         "maze stone nearer the meadow (z 18.6)"),
    "SFM (Saria)": ("GOSSIP_SACRED_FOREST_MEADOW_03", "SacredForestMeadow",
                    "by the Minuet plaza, 21 from Saria (child layout)"),
    "ToT (Left)": ("GOSSIP_HYRULE_MARKET_01", "Market",
                   "the four Temple of Time stones stand in one row right of the temple's axis (temple at x 81, "
                   "z -34, facing the Market); left to right seen walking to the temple: _01, _02, _03, _04. All "
                   "four share OoTR's region and rule"),
    "ToT (Left-Center)": ("GOSSIP_HYRULE_MARKET_02", "Market", "second of the row"),
    "ToT (Right-Center)": ("GOSSIP_HYRULE_MARKET_03", "Market", "third of the row"),
    "ToT (Right)": ("GOSSIP_HYRULE_MARKET_04", "Market", "fourth of the row"),
    "ZD (Mweep)": ("GOSSIP_ZORA_DOMAIN_01", "ZoraDomain",
                   "ZD's only stone. Adult: a frozen Obj_GossipStone_A_02 (no instance name, so no label) stands "
                   "there until SageOfWater_IsAfter_Step08_Exp (Water sage Complete); the talkable stone's Presence "
                   "is IsAppear_GossipStone_ZoraDomain_Adult (that flag and not destroyed)"),
    "ZF (Fairy)": ("GOSSIP_ZORA_FOUNTAIN_02", "ZoraFountain",
                   "by the Great Fairy fountain's bombable wall (WallCrack 13, silver rocks 8-12)"),
    "ZF (Jabu)": ("GOSSIP_ZORA_FOUNTAIN_01", "ZoraFountain", "32 from Lord Jabu-Jabu"),
    "ZR (Near Grottos)": ("GOSSIP_ZORA_RIVER_01", "ZoraRiver",
                          "surface stone 18 from the fairy grotto boulder, near the open grotto"),
    "ZR (Near Domain)": ("GOSSIP_ZORA_RIVER_03", "ZoraRiver",
                         "surface stone at the upper river (x 118) by the Lost Woods and Zora's Domain exits"),
    "ZR (Open Grotto)": ("GOSSIP_ZORA_RIVER_02", "ZoraRiver",
                         "in ZR's open grotto (no cover) beside its chest, as OoTR's generic grotto"),
    "HF (Cow Grotto)": ("GOSSIP_HYRULE_FIELD_04", "HyruleField",
                        "in the cow grotto by the Gerudo Valley exit (boulder, SoundLocator_HidingHoleCow), behind "
                        "a spider web 3.8 away (OoTR: has_fire_source)"),
    "HF (Near Market Grotto)": ("GOSSIP_HYRULE_FIELD_02", "HyruleField",
                                "one of the field's two remaining stone grottos (stone + loose rupees, no chest), "
                                "under a bomb lid like OoTR's Near Market and Southeast grottos "
                                "(here(can_blast_or_smash)); the eastern one (x 180, between the Zora's River and Lost "
                                "Woods exits), the other being the southern one, east of the road to Lake Hylia"),
    "HF (Southeast Grotto)": ("GOSSIP_HYRULE_FIELD_03", "HyruleField",
                              "the field's southern stone grotto (stone + Gold Skulltula, crates), under a bomb "
                              "lid, east of the road to Lake Hylia as OoT's Southeast grotto"),
    "Kak (Open Grotto)": ("GOSSIP_KAKARIKO_VILLAGE_01", "KakarikoVillage",
                          "Kakariko's open grotto (no cover, in the back alley) with its chest, as OoTR's generic "
                          "grotto"),
}

# OoTR stones with no remake stone, with the place OoTR means and what's there instead
ABSENT = {
    "KF (Storms Grotto)": ("KokiriForest", (-51.9, 121.6, -62.8),
                           "Kokiri Forest's only grotto (Song of Storms lid) holds the Deku Scrub brothers and their "
                           "chest; no stone inside. KF's stones are the three surface stones and the Lost Woods "
                           "bridge stone"),
    "LW (Near Shortcuts Grotto)": ("LostWood", (27.8, 100.0, -28.3),
                                   "the Lost Woods grotto by the Goron City and Zora's River shortcuts (boulder) "
                                   "is an empty room (Land_HidingHole_Base_F_01, no chest, no stone); LW's other "
                                   "grottos are the Deku Theater and the two-scrub grotto"),
    "DMT (Storms Grotto)": ("DeathMountainTrail", (-1.6, 120.2, -26.1),
                            "Death Mountain Trail's Song of Storms grotto (in the ring of rocks) holds Baby "
                            "Dodongos, bomb flowers and loose rupees; no stone"),
    "HF (Open Grotto)": ("HyruleField", None,
                         "OoT's three generic Hyrule Field grottos became two stone grottos, both under bomb lids "
                         "(paired with OoTR's two bomb grottos, Near Market and Southeast); no open grotto in the "
                         "field holds a stone. All eleven field grottos were followed to their interiors"),
}

# Remake stones OoTR doesn't have. hints.py adds them to OoTR's stone set as new HintStone locations.
# The region is OoTR's region for the grotto entrance (the remake doesn't shuffle grotto entrances), and "rule" is the
# stone's own rule inside it. id is the stone id in OoTR's spoiler (gossipLocations key, above OoTR's 0x0401-0x044A).
# twin is the OoTR stone an extra stands in for in hint distributions that name stones (disabled, groups,
# remove_stones, priority_stones). Wherever the twin is listed, the extra is listed too (follow_twins). Every extra is
# a grotto stone behind one ordinary obstacle, so each twin is an OoTR generic-grotto stone of its own area (or the
# area's grotto stone the remake moved), never HC Storms / HF Cow, which OoTR singles out for needing a second item.
EXTRA = {
    "DMT (Cow Grotto)": dict(label="GOSSIP_HYRULE_CASTLE_03", area="DeathMountainTrail", id=0x04F0,
                             location="DMT Cow Grotto Gossip Stone", region="DMT Cow Grotto", rule="True",
                             twin="DMT (Storms Grotto)",
                             why="DMT's grotto under the boulder near the Goron City exit (SoundLocator_HidingHoleCow, "
                                 "a cow 3.6 away): OoTR's DMT Cow Grotto (here(can_blast_or_smash)), which has no "
                                 "stone in OoTR"),
    "ZR (Storms Grotto)": dict(label="GOSSIP_LOST_WOOD_01", area="ZoraRiver", id=0x04F1,
                               location="ZR Storms Grotto Gossip Stone", region="ZR Storms Grotto", rule="True",
                               twin="ZR (Open Grotto)",
                               why="ZR's Song of Storms grotto near the Hyrule Field exit (pots, butterflies, stone; "
                                   "no business scrubs): OoTR's ZR Storms Grotto (can_open_storm_grotto)"),
    "Kak (Redead Grotto)": dict(label="GOSSIP_DEATH_MOUNTAIN_TRAIL_01", area="KakarikoVillage", id=0x04F2,
                                location="Kak Redead Grotto Gossip Stone", region="Kak Redead Grotto", rule="True",
                                twin="Kak (Open Grotto)",
                                why="Kakariko's grotto under a bomb lid by the House of Skulltula (beehives, "
                                    "stone, pond): the entrance OoTR calls Kak Redead Grotto "
                                    "(can_open_bomb_grotto); the drops plugin uses the same region for its "
                                    "beehives (the ReDead room itself is under a Hyrule Field hole)"),
    "SFM (Storms Grotto)": dict(label="GOSSIP_KOKIRI_FOREST_02", area="SacredForestMeadow", id=0x04F3,
                                location="SFM Storms Grotto Gossip Stone", region="Sacred Forest Meadow",
                                rule="can_open_bomb_grotto", twin="KF (Storms Grotto)",
                                why="SFM's grotto by the Minuet plaza (chest behind four Song of Time blocks, stone). "
                                    "By elimination OoTR's SFM Storms Grotto, but its cover is a bomb lid "
                                    "(Land_SacredForest_HidingHoleCover_A_02 -> Land_HidingHoleCover_BrokenBomb_"
                                    "Base), not a Song of Storms lid, so the stone sits in the meadow with the "
                                    "bomb-grotto rule"),
}

TWINS_WHY = (
    "An extra stone follows its twin in the stone lists of a hint distribution (disabled, groups, remove_stones, "
    "priority_stones). OoTR's coop distribution disables all eleven of its grotto stones; the four extras are grotto "
    "stones, and their twins (DMT Storms Grotto: DMT's grotto stone, which the remake moved into the cow grotto; "
    "ZR Open Grotto and Kak Open Grotto: their area's grotto stone; KF Storms Grotto: the forest's grotto stone, the "
    "SFM grotto's label is GOSSIP_KOKIRI_FOREST_02) are all on that list, so coop disables the extras too. league, "
    "scrubs and sgl single out only HC Storms Grotto and HF Cow Grotto (each needs a second item past the entrance: "
    "a bombable wall, a spider web); no extra has a second obstacle and no twin is on those lists, so the extras "
    "stay ordinary stones there, as OoTR's generic grotto stones do.")
DISAPPEAR = (
    "GossipStoneDisappear.<label> (the stones' Presence, negated): Bool, ResetTypeValue 8 (reset only by a new game), "
    "SaveFileIndex 0 (saved). Set by the stone itself: AI/GossipStone.root.ainb state 5 runs _LocalModule_f9e82ae9180e "
    "(Launch_Ignition, Launch_Count, Launch, Launch_Crush; node 33 OneShotSetNonStructGameDataBool 'GossipStoneDisappear.' "
    "+ its own instance name = true, node 9 OneShotDeathRequestDeath). State 5 comes from _LocalModule_c0e755492001 "
    "nodes 1/4/5/12: a hit that is not the player's own attack on the stone's Tgt sensor "
    "(QuerySensorHitIsHitTg IsCheckPlayerAttackOnly) with ExternalDamageTypes 7: most likely an explosion, as OoT's "
    "stones launch when bombed (the type enum is not named in the files). The player's own hits on the stone pick "
    "the Shake, ShakeVertical, Crush or Spin states (the sword's time-of-day event; Din's Fire and magic arrows "
    "spin it), none of which sets the flag. Not permanent: Sequence/LoadBancImpl.module node 54 "
    "SeqOneShotResetGameDataGossipStoneDisappear runs on every level load where Sequence_IsAnotherLoadArea is true "
    "(node 50/51), so a blown-away stone and its hint come back when the player enters from another area, as in "
    "OoT. No reset-type change is needed. Remake quirk: the adult Zora's Domain stone's Presence "
    "(IsAppear_GossipStone_ZoraDomain_Adult = SageOfWater_IsAfter_Step08_Exp and not "
    "GossipStoneDisappear.GOSSIP_KOKIRI_FOREST_01) reads the Kokiri Forest stone's flag, harmless because entering "
    "Zora's Domain is an area load that clears it.")

# Rules of existing OoTR stones that the remake makes stricter. Only ever stricter, because a hint gets placed on a
# stone OoTR can reach without the hinted item.
RULES = {
    "Zoras Domain": {"ZD Gossip Stone": ("is_child or 'Defeat Morpha'",
                                         "adult: the talkable stone appears with SageOfWater Complete (the Water "
                                         "Temple's blue-warp landing scene; world_settings ties story stages to "
                                         "the boss defeat)")},
    "Goron City": {"GC Maze Gossip Stone": ("can_blast_or_smash",
                                            "between the Left and Center maze chests (-48.75,113.68,-3.75): the "
                                            "collision mesh reaches it with bombs or the hammer (either age's bombs), "
                                            "not with the Silver Gauntlets alone (logic entry 6); OoTR's rule also "
                                            "had the Silver Gauntlets")},
}


# Reading the level files
def _layout(area, stem):
    m = re.match(re.escape(area) + r"_(.*)_(Static|Dynamic)$", stem)
    return m.group(1) if m else "all"


def _r(v, n=2):
    return [round(float(x), n) for x in v]


_COVER_CACHE = {}


def cover_kind(fs, gyaml):
    """What opens a grotto cover, from its actor pack: a bomb lid, a Song of Storms lid, or a boulder/rock."""
    fixed = {"Obj_BrokenRock_A_01": "boulder (blast or smash)", "Obj_BrokenRock_A_02": "iron rock (hammer)",
             "Obj_LiftRock_B_01": "silver rock", "Obj_BrokenBox_A_01": "crate"}
    if gyaml in fixed:
        return fixed[gyaml]
    if gyaml not in _COVER_CACHE:
        from romtools import sarc_files
        kind = None
        rel = f"Pack/Actor/{gyaml}.pack.zs"
        if os.path.exists(fs.path(rel)):
            blob = b"".join(sarc_files(fs.read(rel)).values())
            if b"Land_HidingHoleCover_BrokenBomb_Base" in blob:
                kind = "bomb lid (Land_HidingHoleCover_BrokenBomb_Base)"
            elif b"DisappearSrom" in blob or b"HitOcarinaMelodyCheck" in blob:
                kind = "Song of Storms lid (HidingHoleCover_DisappearSrom, HitOcarinaMelodyCheck)"
        _COVER_CACHE[gyaml] = kind
    return _COVER_CACHE[gyaml]


NOTABLE = ("TBox", "Gossip", "Scrub", "Enemy_", "Animal_Cow", "Beehive", "Npc_", "Heart", "Obj_Rupee", "Fairy",
           "Skulltula", "SongOfTime", "CandleStick", "HidingHole_Base", "Pot_", "BrokenBox", "WallCrack", "SpiderWeb")


class Levels:
    def __init__(self, fs):
        from romtools import byml_load
        self.fs = fs
        self.files = {}  # rel -> actors
        banc = os.path.join(fs.root, "Banc")  # list the live romfs (fs.path would pick ./original's partial tree)
        for area in sorted(os.listdir(banc)):
            d = os.path.join(banc, area)
            if not os.path.isdir(d) or area in ("BancBasedResource", "GameBancParam"):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".bcett.byml.zs"):
                    rel = f"Banc/{area}/{fn}"
                    root, _ = byml_load(fs.read(rel), allow_big=True)
                    self.files[rel] = (root or {}).get("Actors", []) or []

    def layout_actors(self, area, layout):
        out = []
        for rel, actors in self.files.items():
            a, fn = rel.split("/")[1:]
            if a == area and _layout(area, fn.split(".")[0]) == layout:
                out += [(rel, x) for x in actors]
        return out

    def stones(self):
        for rel, actors in self.files.items():
            for a in actors:
                if a.get("Gyaml", "").startswith("Obj_GossipStone"):
                    yield rel, a

    def grottos(self, area, layout):
        """[(entry actor, entrance pos, landing pos)] of every grotto in one layout of an area."""
        acts = self.layout_actors(area, layout)
        byh = {a["Hash"]: a for _, a in acts}
        out = []
        for _, a in acts:
            if a.get("Gyaml") != "EventRequestActor" or \
                    "HidingHole_Entry" not in str((a.get("Dynamic") or {}).get("RequestEventName", "")):
                continue
            dst = [byh[link["Dst"]] for link in a.get("Links", []) if link["Dst"] in byh]
            hole = next((d for d in dst if d.get("Name") == "HidingHole_HoleEntrance"), None)
            go = next((d for d in dst if d.get("Name") == "HidingHole_FieldEntranceGo"), None)
            if hole:
                out.append((a, (go or a)["Translate"], hole["Translate"]))
        return out

    def grotto_info(self, area, layout, entry, entrance, landing):
        acts = self.layout_actors(area, layout)
        cover = sorted({a["Gyaml"] for _, a in acts if math.dist(a.get("Translate", [0, 0, 0]), entrance) < 4
                        and cover_kind(self.fs, a["Gyaml"])})
        landings = [g[2] for g in self.grottos(area, layout)]
        inside = Counter()
        for _, a in acts:
            t = a.get("Translate", [0, 0, 0])
            d = math.dist(t, landing)
            # under the entrance, near this landing and nearer to it than to any other grotto's landing
            if d < 26 and t[1] < entrance[1] - 6 and abs(t[1] - landing[1]) < 12 and \
                    all(d <= math.dist(t, other) + 1e-6 for other in landings) and \
                    any(k in a["Gyaml"] for k in NOTABLE):
                inside[a["Gyaml"]] += 1
        return {"entry_hash": entry["Hash"], "entrance": _r(entrance, 1), "landing": _r(landing, 1),
                "cover": {c: cover_kind(self.fs, c) for c in cover} or "none (open)",
                "inside": dict(sorted(inside.items()))}

    def grotto_of(self, area, layout, pos):
        best = None
        for entry, entrance, landing in self.grottos(area, layout):
            d = math.dist(pos, landing)
            if d < 30 and pos[1] < entrance[1] - 6 and (best is None or d < best[0]):
                best = (d, entry, entrance, landing)
        if best is None:
            return None
        info = self.grotto_info(area, layout, *best[1:])
        info["stone_to_landing"] = round(best[0], 1)
        return info


def survey(fs):
    """{label: [placement]} of every talkable stone, and the unnamed (untalkable) stone placements."""
    lv = Levels(fs)
    by_label, unnamed = defaultdict(list), []
    for rel, a in sorted(lv.stones(), key=lambda x: (x[0], x[1].get("Name") or "")):
        area = rel.split("/")[1]
        layout = _layout(area, rel.split("/")[2].split(".")[0])
        p = {"file": rel, "layout": layout, "gyaml": a["Gyaml"], "hash": a["Hash"], "position": _r(a["Translate"]),
             "room": (a.get("Dynamic") or {}).get("DefaultDungeonRoomIndex"), "presence": a.get("Presence")}
        if not a.get("Name"):
            unnamed.append(p)
            continue
        g = lv.grotto_of(area, layout, a["Translate"])
        if g:
            p["grotto"] = g
        by_label[a["Name"]].append(p)
    return lv, by_label, unnamed


# Building the data files
def _entry(label, area, why, by_label):
    places = by_label.get(label, [])
    order = {"Child": 0, "Adult": 1, "all": 2}
    here = sorted((p for p in places if p["file"].split("/")[1] == area), key=lambda p: order.get(p["layout"], 3))
    if not here:
        raise SystemExit(f"{label}: no placement in Banc/{area}")
    main = here[0]  # the child layout's placement when there is one
    out = {"label": label, "file": main["file"], "hash": main["hash"], "position": main["position"],
           "where": "grotto" if "grotto" in main else ("dungeon room %s" % main["room"] if main["room"] is not None
                                                       else "surface"),
           "evidence": why, "placements": places}
    return out


def build(romfs):
    import Hints  # noqa: F401  (vendor/ootr on the path)
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    lv, by_label, unnamed = survey(fs)
    stones = {}
    for name, (label, area, why) in PAIRS.items():
        stones[name] = dict(location=_ootr_location(name), **_entry(label, area, why, by_label))
    absent = []
    for name, (area, entrance, why) in ABSENT.items():
        rec = {"stone": name, "location": _ootr_location(name), "area": area, "evidence": why}
        if entrance:  # the grotto OoTR means: prove there is no stone inside, in every layout
            for layout in sorted({p["layout"] for ps in by_label.values() for p in ps
                                  if p["file"].split("/")[1] == area}):
                for entry, ent, land in lv.grottos(area, layout):
                    if math.dist(ent, entrance) < 1.5:
                        info = lv.grotto_info(area, layout, entry, ent, land)
                        if any("Gossip" in k for k in info["inside"]):
                            raise SystemExit(f"{name}: the grotto at {entrance} has a stone ({layout})")
                        rec.setdefault("grotto", {})[layout] = info
            if "grotto" not in rec:
                raise SystemExit(f"{name}: no grotto at {entrance} in Banc/{area}")
        else:  # no grotto of the kind OoTR means: list the area's grottos that hold a stone
            rec["stone_grottos"] = sorted({(tuple(p["grotto"]["entrance"]), json.dumps(p["grotto"]["cover"]))
                                           for ps in by_label.values() for p in ps
                                           if p["file"].split("/")[1] == area and "grotto" in p})
            rec["stone_grottos"] = [{"entrance": list(e), "cover": json.loads(c)} for e, c in rec["stone_grottos"]]
            if any(g["cover"] == "none (open)" for g in rec["stone_grottos"]):
                raise SystemExit(f"{name}: Banc/{area} has an open grotto with a stone")
        absent.append(rec)
    extra = []
    for name, e in EXTRA.items():
        _ootr_location(e["twin"])  # a real OoTR stone name
        rec = dict(stone=name, id="0x%04X" % e["id"], location=e["location"], region=e["region"], rule=e["rule"],
                   twin=e["twin"], **_entry(e["label"], e["area"], e["why"], by_label))
        extra.append(rec)
    used = {s["label"] for s in stones.values()} | {s["label"] for s in extra}
    missing = sorted(set(by_label) - used)
    if missing:
        raise SystemExit(f"placed stones paired with nothing: {missing}")
    import Hints
    ootr = {s.name for s in Hints.gossipLocations.values() if s.name not in {e for e in EXTRA}}
    unpaired = sorted(ootr - set(stones) - set(ABSENT))
    if unpaired:
        raise SystemExit(f"OoTR stones neither paired nor absent: {unpaired}")
    doc = {
        "_about": "Gossip Stone pairing (generated by tools/rando/parity/_hints_stones.py from the game files; edit "
                  "the tables there, not this file). stones: OoTR stone (vendor/ootr/Hints.py gossipLocations name) "
                  "-> the remake stone at its place: label (EventFlowMsg/GossipStone.msbt, the placement's instance "
                  "Name, which the stone shows), first placement (file, hash, position), every placement (child and "
                  "adult layouts; grotto = the HidingHole entrance it is under, its cover and contents), evidence. "
                  "absent: OoTR stones with no remake stone (no hint is placed there). extra: remake stones OoTR "
                  "lacks, added to OoTR's stone set by the hints plugin (region/rule: data/rando/logic/hints.json).",
        "counts": {"remake_stones": len(by_label), "placements": sum(len(v) for v in by_label.values()),
                   "paired": len(stones), "absent": len(absent), "extra": len(extra)},
        "stones": stones, "absent": absent, "extra": extra,
        "untalkable": [dict(p, note="no instance Name, so no label: the frozen adult Zora's Domain stone") for p in
                       unnamed],
        "rules": {region: {loc: {"rule": r, "why": w} for loc, (r, w) in locs.items()}
                  for region, locs in RULES.items()},
        "twins": TWINS_WHY,
        "disappear": DISAPPEAR,
    }
    logic = logic_file()
    return doc, logic


def _ootr_location(name):
    import Hints
    for s in Hints.gossipLocations.values():
        if s.name == name:
            return s.location
    raise SystemExit(f"{name}: not an OoTR Gossip Stone (vendor/ootr/Hints.py gossipLocations)")


def logic_file():
    regions = defaultdict(lambda: {"locations": {}})
    for e in EXTRA.values():
        regions[e["region"]]["locations"][e["location"]] = e["rule"]
    for region, locs in RULES.items():
        for loc, (rule, _) in locs.items():
            regions[region]["locations"][loc] = rule
    return {
        "_about": "Hints plugin logic (generated by tools/rando/parity/_hints_stones.py; see data/rando/"
                  "hints_stones.json): the remake-only Gossip Stones as OoTR HintStone locations in their real "
                  "regions, and the stricter rules of two existing stones (ZD: adult only after the Water Temple; "
                  "GC maze: the maze chests' rock rule).",
        "new_locations": {e["location"]: {"type": "HintStone", "filter_tags": [], "scene": None, "default": None}
                          for e in EXTRA.values()},
        "regions": {k: dict(v) for k, v in sorted(regions.items())},
    }


def _dump(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")


# Used by the hints plugin
_loaded = {}


def load():
    if "doc" not in _loaded:
        _loaded["doc"] = json.load(open(OUT, encoding="utf-8"))
    return _loaded["doc"]


def labels():
    """{OoTR stone name: remake label} for every stone OoTR may put a hint on (paired and extra)."""
    d = load()
    out = {name: s["label"] for name, s in d["stones"].items()}
    out.update({e["stone"]: e["label"] for e in d["extra"]})
    return out


def absent_names():
    return [a["stone"] for a in load()["absent"]]


def install():
    """Makes OoTR's stone set the remake's. Registers the extra stones in Hints.gossipLocations (their locations come
    from data/rando/logic/hints.json) and keeps the absent ones out of the stones OoTR hands out. Those stay known by
    name, so hint distributions that list them (coop's 'disabled', say) still load. Idempotent."""
    import Hints
    import Plandomizer
    d = load()
    for e in d["extra"]:
        sid = int(e["id"], 16)
        if sid in Hints.gossipLocations and Hints.gossipLocations[sid].name != e["stone"]:
            raise RuntimeError(f"stone id {e['id']} is taken by {Hints.gossipLocations[sid].name}")
        Hints.gossipLocations[sid] = Hints.GossipStone(e["stone"], e["location"])
        Hints.gossipLocations_reversemap[e["stone"]] = sid
    absent = {Hints.gossipLocations_reversemap[n] for n in absent_names()}
    cls = Plandomizer.WorldDistribution
    if getattr(cls.configure_gossip, "remake_absent", None) is None:
        orig = cls.configure_gossip

        def configure_gossip(self, spoiler, stone_ids, _orig=orig):
            # build_world_gossip_hints hands this list on to every later step (disabled, groups, the fill)
            stone_ids[:] = [i for i in stone_ids if i not in configure_gossip.remake_absent]
            # OoTR 9.1.40 leaves out lang when it builds GossipText for plando stones, so we pass the world's
            # language in. Otherwise distributions with gossip_stones fail to load with a TypeError.
            lang = spoiler.worlds[self.id].language
            saved = Plandomizer.GossipText
            Plandomizer.GossipText = lambda *a, **k: saved(*a, **dict(k, lang=k.get("lang", lang)))
            try:
                return _orig(self, spoiler, stone_ids)
            finally:
                Plandomizer.GossipText = saved
        configure_gossip.remake_absent = absent
        cls.configure_gossip = configure_gossip
    else:
        cls.configure_gossip.remake_absent = absent


def follow_twins(world):
    """Each extra stone joins every stone list its twin is on in the world's hint distribution (disabled, groups,
    remove_stones, priority_stones, see TWINS_WHY). Idempotent, since a custom distribution's dict is shared between
    build attempts."""
    dist = getattr(world, "hint_dist_user", None) or {}
    twins = [(e["stone"], e["twin"]) for e in load()["extra"]]

    def follow(lst):
        for extra, twin in twins:
            if twin in lst and extra not in lst:
                lst.insert(lst.index(twin) + 1, extra)
    if isinstance(dist.get("disabled"), list):
        follow(dist["disabled"])
    for group in dist.get("groups") or []:
        if isinstance(group, list):
            follow(group)
    for spec in (dist.get("distribution") or {}).values():
        for key in ("remove_stones", "priority_stones"):
            if isinstance(spec, dict) and isinstance(spec.get(key), list):
                follow(spec[key])


def check_plando(settings):
    """Plando'd gossip texts (a distribution file's gossip_stones) can't name an absent stone."""
    problems = []
    absent = set(absent_names())
    dist = getattr(settings, "distribution", None)
    for wd in getattr(dist, "world_dists", []) or []:
        for name in (getattr(wd, "gossip_stones", None) or {}):
            if name in absent:
                problems.append(f"plando gossip stone {name!r}: the remake has no stone there "
                                f"(data/rando/hints_stones.json 'absent')")
    return problems


# Reading a built seed back
def verify(romfs, out_dir):
    """Checks that every OoTR stone in the spoiler has its hint on its paired label in the built archive, absent stones
    get nothing, and no other plan op writes a gossip label."""
    import msbt
    from romtools import Romfs, sarc_files
    plan = json.load(open(os.path.join(out_dir, "plan.json"), encoding="utf-8"))
    spoiler = json.load(open(os.path.join(out_dir, "spoiler.json"), encoding="utf-8"))
    gs = spoiler.get("gossip_stones") or {}
    gs = gs.get("World 1", gs)
    pairing, absent = labels(), set(absent_names())
    bad = []
    for name in gs:
        if name in absent:
            bad.append(f"{name}: OoTR placed a hint on an absent stone")
        elif name not in pairing:
            bad.append(f"{name}: no remake stone paired")
    ops = [op for op in plan.get("text", []) if op.get("file") == GOSSIP_FILE and op["label"].startswith("GOSSIP_")]
    by_label = defaultdict(list)
    for op in ops:
        by_label[op["label"]].append(op)
        if op.get("note") not in gs:
            bad.append(f"{op['label']}: op for {op.get('note')!r}, not a spoiler stone")
        elif pairing.get(op["note"]) != op["label"]:
            bad.append(f"{op['note']}: written to {op['label']}, paired with {pairing.get(op['note'])}")
    for name in gs:
        if name in pairing and pairing[name] not in by_label:
            bad.append(f"{name}: no text op on {pairing[name]}")
    built = Romfs(romfs, os.path.join(HERE, "original"), overlays=[os.path.join(out_dir, "patch")])
    vanilla = Romfs(romfs, os.path.join(HERE, "original"))
    langs = msbt.archives(romfs)
    shown = {}
    checked = 0
    for lang, rel in sorted(langs.items()):
        new = msbt.Msbt(sarc_files(built.read(rel))[GOSSIP_FILE])
        old = msbt.Msbt(sarc_files(vanilla.read(rel))[GOSSIP_FILE])
        lang_ops = {}
        for op in ops:
            if op.get("lang", "*") in ("*", lang):
                lang_ops[op["label"]] = op  # the last op on a label wins
        for label, op in sorted(lang_ops.items()):
            if "markup" in op:  # make_patch.py writes the whole message when the op carries it
                ok = new.get(label) == msbt.from_markup(op["markup"])
            elif isinstance(op["text"], list):
                ok = new.runs(label) == op["text"]
            else:
                want = msbt.Msbt(sarc_files(vanilla.read(rel))[GOSSIP_FILE])
                want.set_text(label, op["text"])
                ok = new.get(label) == want.get(label)
            checked += 1
            if not ok:
                bad.append(f"{lang} {label}: built text differs from {op['note']}'s op")
            plain = msbt.plain(new.get(label))
            if re.search(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]", plain):
                bad.append(f"{lang} {label}: unprintable character in {plain!r}")
            if lang == "USen":
                shown[op["note"]] = (label, plain.replace("\n", " "))
        for label in new.labels:  # stones with no hint keep their vanilla rumour
            if label.startswith("GOSSIP_") and label not in lang_ops and new.get(label) != old.get(label):
                bad.append(f"{lang} {label}: changed without a hint op")
    return gs, shown, checked, bad


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    try:
        sys.stdout.reconfigure(errors="backslashreplace")  # hint text on a console without its characters
    except AttributeError:
        pass
    sys.path.insert(0, os.path.join(HERE, "vendor", "ootr"))
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        import Hints  # noqa: F401
    romfs = argv[1]
    if len(argv) > 2 and argv[2] == "--verify":
        install()
        gs, shown, checked, bad = verify(romfs, argv[3])
        absent = set(absent_names())
        print(f"{len(gs)} OoTR stones with a hint in the spoiler ({len(set(gs) & absent)} absent), "
              f"{checked} label texts read back in all languages")
        for name in sorted(shown):
            label, text = shown[name]
            print(f"  {name:32s} -> {label:34s} {text[:90]}")
        for b in bad:
            print("  BAD", b)
        print("OK" if not bad else f"{len(bad)} problems")
        sys.exit(1 if bad else 0)
    doc, logic = build(romfs)
    if len(argv) > 2 and argv[2] == "--check":
        old = json.load(open(OUT, encoding="utf-8"))
        old_logic = json.load(open(LOGIC, encoding="utf-8"))
        same = json.loads(json.dumps(doc)) == old and json.loads(json.dumps(logic)) == old_logic
        print("hints_stones.json and logic/hints.json match the game" if same else "OUT OF DATE: rebuild them")
        sys.exit(0 if same else 1)
    _dump(OUT, doc)
    _dump(LOGIC, logic)
    c = doc["counts"]
    print(f"{c['remake_stones']} remake stones ({c['placements']} placements): {c['paired']} paired, "
          f"{c['absent']} OoTR stones absent, {c['extra']} extra -> {OUT}, {LOGIC}")


if __name__ == "__main__":
    main(sys.argv)
