"""Fairy shuffles (Ship of Harkinian's Shuffle Fountain / Stone / Bean / Song / Butterfly Fairies) for the remake.

usage: python tools/rando/fairies.py [ROMFS]      rebuild data/rando/fairy_map.json and data/rando/logic/fairies.json
                                                  from the game files (every step, flag and placement checked)

The plugin is tools/rando/parity/fairies.py. The give steps go
through the songs_trade plugin's Ops, so Link holds the item up, and progressive tiers, dungeon items' credit entries
and the ice-trap freeze work as at every other scene check. Nothing here moves or replaces a fairy. The vanilla fairy
still comes and heals, and the seed's item is given once with it.

Kinds built:
  stone      (remake_shuffle_stone_fairies) every talkable Gossip Stone, twice, as in SoH: "<stone> Fairy" (Zelda's
             Lullaby, Epona's Song, Sun's Song or the Song of Time) and "<stone> Big Fairy" (the Song of Storms).
             The remake makes one fairy for every song. The stone flow's melody switch (GossipStone Event12) records
             in a scratch flag whether the Song of Storms was played. After the fairy's heal (after Event158) the
             stone asks its own number (EventQueryGossipStoneCheckInstanceName, which its event AI answers 0-39 by
             its placement Name, unused in vanilla) and gives that stone's normal or big item once (a borrowed saved
             flag each, tools/rando/free_flags.py). Sun's Song counts where OoTR's own Gossip Stone Fairy does (its
             _without_suns regions don't).
  fountain   (remake_shuffle_fountain_fairies) the Desert Colossus oasis, where the Song of Storms cutscene (plays
             once ever, DesertColossus_IsStormSongPlayed_02) gives its 7 items after its last step.
             The HF, SFM and ZR fairy fountain grottos. The grotto's entry requester asks for a reused scene ID whose
             entry plays the vanilla grotto entry and then, once (the ID's own HavePlayedEvent flag), the grotto's 8
             items. The drops plugin's ZD storms grotto gift does the same.
             The Graveyard Shield Grave's fountain, the same way, through the grave whose corridor ends at the
             fountain room's WallCrack (GRAVES below).
             Ganon's Castle's fountain room (ROOMS below), which has no event. A copy of its fountain music Area and
             of a castle EventRequestActor run Gerudo Valley's vanilla area-event module as a new logic group, so
             entering the fountain plays a reused scene ID giving the 8 items once.
  butterfly  (remake_shuffle_butterfly_fairies) the 15 butterflies that turn into a fairy at a child's Deku Stick.
             They're drop spots of the drops plugin (tools/rando/drops.py CATEGORY "butterfly"). The butterfly drops
             the seed's item when it turns and keeps coming back until it's taken (the respawn model), then it's a
             vanilla one.
  song       (remake_shuffle_song_fairies) the 9 Fairy Note spots; bean (remake_shuffle_bean_fairies) the 10 bean
             plants, 3 items each. See NOTE_SPOTS / BEAN_SPOTS below.
"""
import json
import math
import os
import re
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # REMAKE_ROMFS: the app
OUT = os.path.join(HERE, "data", "rando", "fairy_map.json")
LOGIC_OUT = os.path.join(HERE, "data", "rando", "logic", "fairies.json")
OOTR_LOGIC = os.path.join(HERE, "reference", "ootr", "logic.json")
STONES = os.path.join(HERE, "data", "rando", "hints_stones.json")
HINTS_LOGIC = os.path.join(HERE, "data", "rando", "logic", "hints.json")
SCENE_ROWS = os.path.join(HERE, "config", "scene_rows.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
LOC_TYPE = "RemakeFairy"

SETTINGS = {"stone": "remake_shuffle_stone_fairies", "fountain": "remake_shuffle_fountain_fairies",
            "bean": "remake_shuffle_bean_fairies", "song": "remake_shuffle_song_fairies",
            "butterfly": "remake_shuffle_butterfly_fairies"}
# Kinds with locations and a patch. The others are refused (parity/fairies.py). The butterflies are drop spots,
# see tools/rando/drops.py CATEGORY "butterfly" (the respawn model, data/rando/drops_regions_x3.json).
BUILT = ("stone", "fountain", "butterfly", "song", "bean")

# Gossip Stones
STONE_FLOW = "GossipStone"
STONE_ACTOR = "Obj_GossipStone_A_01"
STONE_PACK = "Pack/Actor/Obj_GossipStone_A_01.pack.zs"
STONE_EVENT_AI = "AI/GossipStone.event.root.ainb"
STONE_QUERY = "EventQueryGossipStoneCheckInstanceName"
MELODY_SWITCH = "Event12"     # GameSystemActor EventQueryMelodyTypeForNormal: 0 ZL, 1 Epona, 3 Sun, 4 Time, 5 Storms
MELODY_NEXT = "Event21"       # every fairy-making melody's next step
STORMS = 5
STONE_AFTER = "Event158"      # GossipStone_BancChangeCheck set: the fairy came and healed
STONE_RESUME = "Event31"      # Navi's balloon, then the flow's last step
NORMAL_SONGS = ("can_play(Zeldas_Lullaby)", "can_play(Eponas_Song)", "can_play(Song_of_Time)")
SUNS = "can_play(Suns_Song)"
BIG_SONG = "can_play(Song_of_Storms)"

# Fountains
COLOSSUS = {"flow": "SageOfSpirit_FocusOnGimmick", "entry": "DessertColossus_IsStormSongPlayed", "after": "Event114",
            "once": "DesertColossus_IsStormSongPlayed_02", "region": "Desert Colossus",
            "rule": "can_play(Song_of_Storms)", "names": [f"Fairy0{i}" for i in range(1, 8)],
            "area": "DesertColossus", "word": "Colossus Oasis Fairy"}
GROTTO_FLOW, GROTTO_ENTRY = "GimmickFlow_Common", "HidingHole_Entry_01"
FAIRY_TYPE = "Obj_Fairy_HidingHole_FairyFountain"
# config/scene_rows.json rows no other plugin holds statically: the last two map/compass rows nobody names, and the
# rupee-trap big-chest row, which the chests plugin gives up while these grottos hold items (parity/chests.py
# _claimed_rows). Progressive chest scenes skip rows a plan uses (make_patch resolve_progressive).
GROTTOS = {
    "HF Fairy Grotto": {"area": "HyruleField", "row": "WaterTemple_GetMap", "entry": "RandoFairy_HFGrotto"},
    "SFM Fairy Grotto": {"area": "SacredForestMeadow", "row": "SpiritTemple_GetCompass",
                         "entry": "RandoFairy_SFMGrotto"},
    "ZR Fairy Grotto": {"area": "ZoraRiver", "row": "FireTemple_GetMap", "entry": "RandoFairy_ZRGrotto"},
}
GROTTO_FAIRIES = 8
# The fountain prefab's HidingHole_HoleEntrance anchor lands 27.5 m from the centre of its eight fairies. In HF and
# ZR every other grotto lands more than 60 m away, but in Sacred Forest Meadow the Wolfos grotto lands even closer
# to the fountain, at 22.4 m. So we match the 27.5 m offset.
FOUNTAIN_LANDING = 27.5
LANDING_TOLERANCE = 0.6
# The Graveyard's fountain (OoTR's Graveyard Shield Grave "Free Fairies", SoH's 8 Shield Grave fountain fairies).
# It's 8 plain Obj_Fairy per age layout (Graveyard_*_Dynamic) in a back room behind a WallCrack, with no event,
# drop or handle of their own. The remake has three child graves under one tombstone logic group: the Hylian Shield
# chest's, the Heart Piece chest's, and one whose corridor ends at that crack (OoT's shield grave split in two). So
# the grave gives like the grottos, on its first entry.
# We tell the grave by its landing (HidingHole_HoleEntrance) lying on the crack's corridor line (|dx| or |dz| <=
# GRAVE_AXIS) within GRAVE_REACH, the crack being the one nearest the fairies (within WALL_NEAR). Its scene ID is a
# front row nobody names, held by one chest only, the Deku Tree's slingshot chest. That's an item scene, which a
# shuffled chest drops anyway, the progressive chest scenes skip a row a plan uses, and parity/chests.py budgets
# it. Not ForesetTemple_GetBossKey, five boss-key chests share that one.
# The logic rule stays SoH's and OoTR's (break the wall), even though the items come on entry. The seed's logic is
# then SoH's, and never harder than the game.
GRAVES = {
    "Graveyard Shield Grave": {"area": "Graveyard", "row": "InsideTheDekuTree_GetSlingShot",
                               "entry": "RandoFairy_ShieldGrave", "fairy": "Obj_Fairy", "wall": "WallCrack",
                               "rule": "can_blast_or_smash"},
}
GRAVE_AXIS = 0.5
GRAVE_REACH = 25.0
WALL_NEAR = 30.0
# Ganon's Castle's fountain (OoTR's Ganons Castle Deku Scrubs "Free Fairies", SoH's 8 Scrubs Fairies, rule true).
# It's 8 HidingHole fairies in the room under the lobby's fake floor. The castle-wide area of
# InsideGanonCastle_Prefab_47b7 creates them, no event plays in the room and nothing has a handle.
# The room gives like a grotto, on entering the fountain. A copy of the fountain's own music Area (the Area its
# BGM_GreatFairyFountain actor names, the fairies' room) and a copy of a castle EventRequestActor (no links) run
# Gerudo Valley's vanilla area-event module (ROOM_MODULE: Area contact -> EventRequestTrigger, its only nodes) as a
# logic group of their own, with that instance's FarDelete/Simultaneous group shape (exactly the two).
# The requester asks for a scene row nobody names (ForestTemple_GetBow, one chest, read by no Event, Logic or AI
# file), set up like the grottos' rows with the vanilla HidingHole_Entry_01 row's settings (starts with Link busy,
# carrying or sword drawn). Its entry gives the 8 items once (HavePlayedEvent.<row>, set first). The area copy
# carries a lazy negated Presence on that flag, vanilla's shape from KokiriForest_Adult_Level_All_01_233a's areas,
# so it leaves the moment the gift starts and never plays it again.
ROOMS = {
    "Ganons Castle Deku Scrubs": {"area": "InsideGanonCastle", "row": "ForestTemple_GetBow",
                                  "entry": "RandoFairy_GanonsCastle", "word": "Ganons Castle Scrubs Fairy",
                                  "rule": "True", "music": "BGM_GreatFairyFountain_"},
}
ROOM_MODULE = {"file": "Banc/GerudoValley/GerudoValley_Child_Static.bcett.byml.zs",
               "logic": "Logic/Module/GerudoValley_Child_Prefab/GerudoValley_Child_Prefab_c60b.logic.module.ain",
               "area_id": "Area_7125", "event_id": "EventRequestActor_b532"}
MUSIC_AREA_NEAR = 2.0  # the fountain music Area's centre to the fairies' centre (IGC: 1.0)


class FairyError(ValueError):
    pass


def _fs(romfs):
    from romtools import Romfs
    return Romfs(romfs, os.path.join(HERE, "original"))


def _event(fs, name):
    """The game's own copy of an event flow (Name.NNN.bfevfl.zs when the game has numbered copies)."""
    import glob
    import evfl
    root = fs.root if hasattr(fs, "root") else DEFAULT_ROMFS
    cands = sorted(p for p in glob.glob(os.path.join(root, "Event", "EventFlow", f"{name}*.bfevfl.zs"))
                   if os.path.basename(p).split(".")[0] == name)
    if not cands:
        return None
    numbered = [p for p in cands if re.search(r"\.\d{3}\.bfevfl", p)] or cands
    rel = os.path.relpath(numbered[-1], root).replace(os.sep, "/")
    return evfl.Evfl(fs.read(rel))


def _ootr_rules():
    """{location: (region, rule)} from OoTR's logic, and {region: OoTR Gossip Stone Fairy rule}."""
    logic = json.load(open(OOTR_LOGIC, encoding="utf-8"))
    where, fairy = {}, {}
    for r in logic["regions"]:
        for name, rule in (r.get("locations") or {}).items():
            where.setdefault(name, (r["name"], rule))
            if name == "Gossip Stone Fairy":
                fairy[r["name"]] = rule
    return where, fairy


def _normal_rule(fairy_rule):
    """The songs that make the remake's normal stone fairy where OoTR's region rule is `fairy_rule`."""
    songs = list(NORMAL_SONGS)
    if fairy_rule is None or "without_suns" in fairy_rule:
        if fairy_rule and "is_adult and can_play(Suns_Song)" in fairy_rule:  # ToT: Sun's Song only as an adult
            songs.append(f"(is_adult and {SUNS})")
    else:
        songs.append(SUNS)
    return " or ".join(songs)


def _stone_values(fs):
    """{label: value} that the stone's query answers, read from its event AI. That's a StringSelector on the stone's
    instance name whose children set the answer."""
    import ainb
    from romtools import sarc_files
    a = ainb.Ainb(sarc_files(fs.read(STONE_PACK))[STONE_EVENT_AI])
    cmd = next((c for c in a.commands if c["name"] == STONE_QUERY), None)
    if cmd is None:
        raise FairyError(f"{STONE_EVENT_AI}: no command {STONE_QUERY}")
    sel = a.nodes[cmd["main"]]["plugs"][ainb.PLUG_CHILD][0]["node"]
    if ainb.NODE_TYPES.get(a.nodes[sel]["type"]) != "StringSelector":
        raise FairyError(f"{STONE_EVENT_AI}: {STONE_QUERY} no longer selects on a string")
    out = {}
    for pl in a.nodes[sel]["plugs"][ainb.PLUG_CHILD]:
        case = a.pool.get(struct.unpack_from("<I", pl["extra"], 4)[0])
        k = pl["node"]
        ins = {e["name"]: e["value"] for t in ainb.PTYPES for e in a.nodes[k]["inputs"][t]}
        if a.nodes[k]["name"] != "ExecuteEventSetQueryValue":
            raise FairyError(f"{STONE_EVENT_AI}: case {case!r} doesn't answer the query")
        if case.startswith("GOSSIP_"):
            if ins.get("Label") != case:
                raise FairyError(f"{STONE_EVENT_AI}: case {case} answers for {ins.get('Label')}")
            out[case] = int(ins["Value"])
    return out


def _check_stone_flow(fs, problems):
    ev = _event(fs, STONE_FLOW)
    fc = ev.flowcharts[0]
    names = {e["name"]: e for e in fc["events"]}
    acts = fc["actors"]
    sw = names.get(MELODY_SWITCH)
    if sw is None or sw["type"] != "switch" or acts[sw["actor"]]["queries"][sw["query"]] != \
            "EventQueryMelodyTypeForNormal":
        problems.append(f"{STONE_FLOW}: {MELODY_SWITCH} is no longer the melody switch")
        return {}
    nxt = names[MELODY_NEXT]["idx"]
    values = [c["value"] for c in sw["cases"]]
    if sorted(values) != [0, 1, 3, 4, 5] or any(c["next"] != nxt for c in sw["cases"]):
        problems.append(f"{STONE_FLOW}: {MELODY_SWITCH}'s cases changed ({values})")
    after = names.get(STONE_AFTER)
    pv = {k: v.get("value") for k, v in ((after or {}).get("params") or {}).get("items", {}).items()}
    if after is None or after["type"] != "action" or pv.get("GameDataName") != "GossipStone_BancChangeCheck" or \
            after["next"] != names[STONE_RESUME]["idx"]:
        problems.append(f"{STONE_FLOW}: {STONE_AFTER} no longer leads from the fairy's heal to {STONE_RESUME}")
    if STONE_ACTOR not in {a["name"] for a in acts} or "GameDataActor" not in {a["name"] for a in acts}:
        problems.append(f"{STONE_FLOW}: no {STONE_ACTOR} or GameDataActor")
    return {"flow": STONE_FLOW, "switch": MELODY_SWITCH, "melody_next": MELODY_NEXT,
            "storm_cases": [i for i, c in enumerate(sw["cases"]) if c["value"] == STORMS],
            "calm_cases": [i for i, c in enumerate(sw["cases"]) if c["value"] != STORMS],
            "after": STONE_AFTER, "resume": STONE_RESUME, "actor": STONE_ACTOR, "query": STONE_QUERY}


def _stones(fs, problems):
    """Every talkable stone's two fairy spots."""
    pairing = json.load(open(STONES, encoding="utf-8"))
    hints = json.load(open(HINTS_LOGIC, encoding="utf-8"))
    over = {loc: (region, rule) for region, sec in hints.get("regions", {}).items()
            for loc, rule in (sec.get("locations") or {}).items()}
    where, fairy = _ootr_rules()
    values = _stone_values(fs)
    stones = [dict(v, stone=k) for k, v in pairing["stones"].items()] + list(pairing["extra"])
    spots, seen = {}, set()
    for s in sorted(stones, key=lambda x: x["location"]):
        loc, label = s["location"], s["label"]
        if label in seen:
            problems.append(f"stones: label {label} paired twice")
        seen.add(label)
        if label not in values:
            problems.append(f"stones: the stone query has no answer for {label}")
            continue
        region, rule = over.get(loc) or where.get(loc) or (None, None)
        if region is None:
            problems.append(f"stones: no region for {loc}")
            continue
        normal = _normal_rule(fairy.get(region))
        places = [{"file": p["file"], "hash": str(p["hash"]), "pos": p["position"]} for p in s.get("placements", [])]
        for big in (False, True):
            name = f"{loc} {'Big Fairy' if big else 'Fairy'}"
            spots[name] = {"kind": "stone", "setting": SETTINGS["stone"], "region": region,
                           "rule": f"({rule}) and ({BIG_SONG if big else normal})", "label": label,
                           "value": values[label], "big": big, "stone": loc, "places": places,
                           "confidence": "high",
                           "why": f"{label} ({s.get('stone', 'remake-only stone')}); "
                                  f"{'the Song of Storms' if big else 'any other fairy song'}"}
    missing = sorted(set(values) - seen)
    if missing:  # a talkable stone with no OoTR pairing would have no region
        problems.append(f"stones: labels without a pairing: {missing}")
    return spots


def _check_colossus(fs, problems):
    from romtools import byml_load, murmur3_32
    c = COLOSSUS
    ev = _event(fs, c["flow"])
    fc = ev.flowcharts[0]
    names = {e["name"]: e for e in fc["events"]}
    e = names.get(c["after"])
    if c["entry"] not in fc["entry_points"] or e is None or e["type"] != "action" or e["next"] != 0xFFFF:
        problems.append(f"{c['flow']}: {c['after']} is not the last step of {c['entry']}")
    # The cutscene's guard is case 1 (not yet set) of a query on its once-flag, before anything else.
    guard = [x for x in fc["events"] if x["type"] == "switch" and
             (((x.get("params") or {}).get("items") or {}).get("GameDataName") or {}).get("value") == c["once"]]
    if not guard or [k["value"] for k in guard[0]["cases"]] != [1]:
        problems.append(f"{c['flow']}: the cutscene no longer plays only while {c['once']} is unset")
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    if murmur3_32(c["once"].encode()) not in {int(x["Hash"]) for x in gd["Bool"]}:
        problems.append(f"no save-data Bool {c['once']}")
    places = defaultdict(list)  # fairy name -> its placement in each age layout
    for age in ("Child", "Adult"):
        rel = f"Banc/{c['area']}/{c['area']}_{age}_Static.bcett.byml.zs"
        acts = byml_load(fs.read(rel))[0]["Actors"]
        named = {a.get("Name"): a for a in acts if a.get("Gyaml") == "Obj_Fairy"}
        for n in c["names"]:
            if n not in named:
                problems.append(f"{rel}: no Obj_Fairy {n}")
            else:
                places[n].append({"file": rel, "hash": str(named[n]["Hash"]), "pos": named[n]["Translate"]})
    spots = {}
    for i, n in enumerate(c["names"], 1):
        spots[f"{c['word']} {i}"] = {
            "kind": "fountain", "setting": SETTINGS["fountain"], "region": c["region"], "rule": c["rule"],
            "group": "colossus", "index": i - 1, "confidence": "high", "places": places[n],
            "why": f"the oasis cutscene's {n} (Song of Storms at the oasis; plays once ever)"}
    return {"flow": c["flow"], "entry": c["entry"], "after": c["after"], "once": c["once"]}, spots


def _grottos(fs, problems):
    """Each fairy grotto with its entry requesters (one per age layout), their scene ID and its 8 fairies."""
    from romtools import byml_load, murmur3_32
    rows = json.load(open(SCENE_ROWS, encoding="utf-8"))["rows"]
    es = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    bools = {int(x["Hash"]) for x in gd["Bool"]}
    ev = _event(fs, GROTTO_FLOW)
    fc = ev.flowcharts[0]
    if GROTTO_ENTRY not in fc["entry_points"] or "GameDataActor" not in {a["name"] for a in fc["actors"]}:
        problems.append(f"{GROTTO_FLOW}: no entry {GROTTO_ENTRY} or GameDataActor")
    if GROTTO_ENTRY not in es:
        problems.append(f"no scene ID {GROTTO_ENTRY}")
    region_names = {r["name"] for r in json.load(open(OOTR_LOGIC, encoding="utf-8"))["regions"]}
    data, spots = {}, {}
    for region, g in list(GROTTOS.items()) + list(GRAVES.items()):
        grave = region in GRAVES
        place = "grave" if grave else "grotto"
        if g["row"] not in rows:
            problems.append(f"{region}: scene ID {g['row']} is not in config/scene_rows.json")
        if g["row"] not in es:
            problems.append(f"{region}: no scene ID {g['row']}")
        if murmur3_32(f"HavePlayedEvent.{g['row']}".encode()) not in bools:
            problems.append(f"{region}: no save-data Bool HavePlayedEvent.{g['row']}")
        if region not in region_names:
            problems.append(f"{region}: not an OoTR region")
        triggers, fairies = [], []
        for age in ("Child", "Adult"):
            acts = []
            for half in ("Static", "Dynamic"):
                rel = f"Banc/{g['area']}/{g['area']}_{age}_{half}.bcett.byml.zs"
                acts += [(rel, a) for a in byml_load(fs.read(rel))[0]["Actors"]]
            byh = {a["Hash"]: a for _, a in acts}
            ff = [(rel, a) for rel, a in acts if a.get("Gyaml") == g.get("fairy", FAIRY_TYPE)]
            if len(ff) != GROTTO_FAIRIES:
                problems.append(f"{region} ({age}): {len(ff)} fountain fairies, expected {GROTTO_FAIRIES}")
                continue
            centre = [sum(a["Translate"][k] for _, a in ff) / len(ff) for k in range(3)]
            fairies += [{"file": rel, "hash": str(a["Hash"]), "pos": a["Translate"]} for rel, a in ff]
            wall = None
            if grave:
                walls = sorted((a for _, a in acts if a.get("Gyaml") == g["wall"]),
                               key=lambda a: math.dist(a["Translate"], centre))
                if not walls or math.dist(walls[0]["Translate"], centre) > WALL_NEAR:
                    problems.append(f"{region} ({age}): no {g['wall']} within {WALL_NEAR} of the fairies")
                    continue
                wall = walls[0]["Translate"]
            match = []
            for rel, a in acts:
                if a.get("Gyaml") != "EventRequestActor" or \
                        (a.get("Dynamic") or {}).get("RequestEventName") != GROTTO_ENTRY:
                    continue
                hole = next((byh[ln["Dst"]] for ln in a.get("Links", []) if ln["Dst"] in byh
                             and byh[ln["Dst"]].get("Name") == "HidingHole_HoleEntrance"), None)
                if hole is None:
                    continue
                h = hole["Translate"]
                if grave:
                    if min(abs(h[0] - wall[0]), abs(h[2] - wall[2])) <= GRAVE_AXIS and \
                            math.dist((h[0], h[2]), (wall[0], wall[2])) <= GRAVE_REACH:
                        match.append((math.dist(h, wall), rel, a))
                elif abs(math.dist(h, centre) - FOUNTAIN_LANDING) <= LANDING_TOLERANCE:
                    match.append((math.dist(h, centre), rel, a))
            if len(match) != 1:
                where = (f"land on the {g['wall']}'s corridor within {GRAVE_REACH}" if grave
                         else f"land {FOUNTAIN_LANDING} from the fountain")
                problems.append(f"{region} ({age}): {len(match)} {place} entries {where}, expected 1")
                continue
            d, rel, a = match[0]
            t = {"file": rel, "hash": str(a["Hash"])}
            t["landing_to_wall" if grave else "landing_to_fountain"] = round(d, 1)
            triggers.append(t)
        chests = sorted(({"file": rel, "hash": str(a.get("Hash"))} for rel, a in _all_actors(fs)
                         if (a.get("Dynamic") or {}).get("GetEventName") == g["row"]),
                        key=lambda x: (x["file"], x["hash"]))
        data[region] = {"row": g["row"], "copy_of": GROTTO_ENTRY,
                        "scene": {"file": GROTTO_FLOW, "entry": g["entry"], "vanilla": GROTTO_ENTRY},
                        "once": f"HavePlayedEvent.{g['row']}", "triggers": triggers, "row_chests": chests}
        for i in range(GROTTO_FAIRIES):
            spots[f"{region} Fairy {i + 1}"] = {
                "kind": "fountain", "setting": SETTINGS["fountain"], "region": region,
                "rule": g.get("rule", "True"),
                "group": region, "index": i, "confidence": "high",
                "places": fairies[i::GROTTO_FAIRIES],  # the i-th fairy of each age layout
                "why": (f"{region}: given with the grave's first entry (scene ID {g['row']} plays the vanilla entry, "
                        f"then the 8 items once), before the {g['wall']} to the fountain room; the rule stays "
                        f"SoH's (Shield Grave Back: CanBreakMudWalls) and OoTR's Free Fairies' (can_blast_or_smash), "
                        f"never harder than the game" if grave else
                        f"{region}: given with the grotto's first entry (scene ID {g['row']} plays the vanilla entry, "
                        f"then the 8 items once); OoTR's Free Fairies there need only the region")}
    return data, spots


def _new_hash(label, taken):
    """A placement / logic-group hash of our own, derived from `label` and clear of every hash in `taken`."""
    import hashlib
    for salt in range(64):
        h = int.from_bytes(hashlib.sha256(f"{label}#{salt}".encode()).digest()[:8], "little")
        if h not in taken:
            return h
    raise FairyError(f"{label}: no free hash")


def _room_module(fs, problems):
    """ROOM_MODULE read from the game, its module's three nodes and its vanilla instance. The instance is the group's
    two actors, alone in one FarDelete and one Simultaneous group."""
    import ainb
    from romtools import byml_load
    m = ROOM_MODULE
    a = ainb.Ainb(fs.raw("Logic/" + m["logic"].rsplit("/", 1)[-1] + "b"))

    def vals(i, sec):
        return {e["name"]: e for t in ainb.PTYPES for e in a.nodes[i][sec][t]}
    by = {n["name"]: i for i, n in enumerate(a.nodes)}
    want = ("ActorLogicAreaActor", "HoldActorObserverBySensorHitInfo", "ActorLogicEventRequestActor")
    if sorted(n["name"] for n in a.nodes) != sorted(want):
        problems.append(f"{m['logic']}: nodes {[n['name'] for n in a.nodes]}, expected {want}")
        return None
    ar, ob, ev = (by[k] for k in want)
    ok = (vals(ar, "properties")["InstanceName"]["value"] == m["area_id"]
          and vals(ar, "properties")["Layer"]["value"] == "Player"
          and vals(ar, "inputs")["Logic_Create"]["value"] is True and vals(ar, "inputs")["Logic_Create"]["node"] < 0
          and vals(ar, "inputs")["Logic_Delete"]["node"] < 0
          and vals(ob, "inputs")["ActorName"]["value"] == "Player"
          and vals(ev, "properties")["InstanceName"]["value"] == m["event_id"]
          and vals(ev, "inputs")["EventRequestTrigger"]["node"] == ob
          and vals(ev, "inputs")["Logic_Create"]["value"] is True and vals(ev, "inputs")["Logic_Delete"]["node"] < 0)
    if not ok:
        problems.append(f"{m['logic']}: no longer 'player in {m['area_id']} -> request {m['event_id']}'s event'")
    root = byml_load(fs.read(m["file"]))[0]
    byh = {a_["Hash"]: a_ for a_ in root["Actors"]}
    inst = [g for g in root.get("AiGroups") or [] if g["Logic"] == m["logic"]]
    refs = {r["Id"]: byh.get(r["Reference"], {}).get("Gyaml") for r in inst[0]["References"]} if len(inst) == 1 else {}
    if refs != {m["area_id"]: "Area", m["event_id"]: "EventRequestActor"}:
        problems.append(f"{m['file']}: the vanilla {m['logic']} group is not one Area and one EventRequestActor")
        return None
    pair = sorted(r["Reference"] for r in inst[0]["References"])
    for grp in ("FarDeleteGroups", "SimultaneousGroups"):
        if sum(sorted(int(x) for x in mm) == pair for mm in root.get(grp) or []) != 1:
            problems.append(f"{m['file']}: the vanilla {m['logic']} pair is not one {grp} entry of its own")
    return {"logic": m["logic"], "area_id": m["area_id"], "event_id": m["event_id"],
            "vanilla": {"file": m["file"], "group": str(inst[0]["Hash"])}}


def _rooms(fs, problems):
    """Fountain rooms without an event (ROOMS), with the copies, the group and the scene row each one gives through."""
    from romtools import byml_load, murmur3_32
    rows = json.load(open(SCENE_ROWS, encoding="utf-8"))["rows"]
    es = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    bools = {int(x["Hash"]): x for x in gd["Bool"]}
    keys = {int(x["Hash"]) for x in gd.get("Bool64bitKey") or []}
    region_names = {r["name"] for r in json.load(open(OOTR_LOGIC, encoding="utf-8"))["regions"]}
    module = _room_module(fs, problems)
    if module is None:
        return {}, {}
    taken_rows = {g["row"] for g in list(GROTTOS.values()) + list(GRAVES.values())}
    data, spots = {}, {}
    for region, g in ROOMS.items():
        row, once = g["row"], f"HavePlayedEvent.{g['row']}"
        if row not in rows or row not in es or row in taken_rows:
            problems.append(f"{region}: scene ID {row} is not a free row of config/scene_rows.json")
        b = bools.get(murmur3_32(once.encode()))
        if b is None or b.get("ResetTypeValue") != 8:
            problems.append(f"{region}: {once} is not a saved Bool (reset type 8)")
        if GROTTO_ENTRY not in es:
            problems.append(f"no scene ID {GROTTO_ENTRY}")
        if region not in region_names:
            problems.append(f"{region}: not an OoTR region")
        rel = f"Banc/{g['area']}/{g['area']}_Static.bcett.byml.zs"
        root = byml_load(fs.read(rel))[0]
        dyn = byml_load(fs.read(rel.replace("_Static.", "_Dynamic.")))[0]
        acts = root["Actors"]
        byh = {a["Hash"]: a for a in acts}
        ff = [a for a in acts if a.get("Gyaml") == FAIRY_TYPE]
        if len(ff) != GROTTO_FAIRIES:
            problems.append(f"{region}: {len(ff)} fountain fairies in {rel}, expected {GROTTO_FAIRIES}")
            continue
        centre = [sum(a["Translate"][k] for a in ff) / len(ff) for k in range(3)]
        # the fountain's music Area, the one a fairy-fountain BGM actor names that's nearest the fairies
        music = sorted(((math.dist(byh[ln["Dst"]]["Translate"], centre), a, byh[ln["Dst"]]) for a in acts
                        if a.get("Gyaml", "").startswith(g["music"]) for ln in a.get("Links") or []
                        if byh.get(ln["Dst"], {}).get("Gyaml") == "Area"), key=lambda x: x[0])
        if not music or music[0][0] > MUSIC_AREA_NEAR:
            problems.append(f"{region}: no {g['music']}* music Area within {MUSIC_AREA_NEAR} of the fairies")
            continue
        d_area, bgm, area = music[0]
        grouped = {int(x) for grp in ("FarDeleteGroups", "SimultaneousGroups") for mm in root.get(grp) or [] for x in mm}
        refd = {r["Reference"] for gr in root.get("AiGroups") or [] for r in gr["References"]}
        if area["Hash"] in grouped or area["Hash"] in refd or area.get("Presence") or area.get("Links") or \
                set(area.get("Dynamic") or {}) != {"RigidBodyShapeType"}:
            problems.append(f"{region}: the music Area {area['Hash']} is no longer a plain, unbound Area")
        eras = sorted((math.dist(a["Translate"], area["Translate"]), a) for a in acts
                      if a.get("Gyaml") == "EventRequestActor")
        if not eras:
            problems.append(f"{region}: no EventRequestActor in {rel} to copy")
            continue
        d_era, era = eras[0]
        if set(era.get("Dynamic") or {}) != {"RequestEventName"} or \
                any(ln.get("Gyaml") != "Reference" for ln in era.get("Links") or []):
            problems.append(f"{region}: EventRequestActor {era['Hash']} has settings or links of another kind")
        taken = set(byh) | {a["Hash"] for a in dyn.get("Actors") or []} | keys | \
            {gr["Hash"] for gr in root.get("AiGroups") or []}
        area_twin = _new_hash(f"RandoFairyRoom:{region}:Area", taken)
        taken.add(area_twin)
        era_twin = _new_hash(f"RandoFairyRoom:{region}:EventRequestActor", taken)
        taken.add(era_twin)
        group_hash = _new_hash(f"RandoFairyRoom:{region}:AiGroup", taken)
        chests = sorted(({"file": r_, "hash": str(a.get("Hash"))} for r_, a in _all_actors(fs)
                         if (a.get("Dynamic") or {}).get("GetEventName") == row), key=lambda x: (x["file"], x["hash"]))
        readers = sorted({os.path.basename(r_) for r_, a in _all_actors(fs)
                          if (a.get("Presence") or {}).get("FlagName") == once})
        if readers:
            problems.append(f"{region}: placements already show or hide by {once} ({readers})")
        data[region] = {
            "row": row, "copy_of": GROTTO_ENTRY, "scene": {"file": GROTTO_FLOW, "entry": g["entry"]}, "once": once,
            "file": rel,
            "area": {"source": str(area["Hash"]), "twin": str(area_twin), "pos": area["Translate"],
                     "scale": area.get("Scale"), "music": str(bgm["Hash"]), "to_fairies": round(d_area, 1)},
            "requester": {"source": str(era["Hash"]), "twin": str(era_twin), "to_area": round(d_era, 1)},
            "presence": {"FlagName": once, "IsCheckLazy": True, "IsNegation": True},
            "group": dict(module, hash=str(group_hash)), "row_chests": chests}
        places = [{"file": rel, "hash": str(a["Hash"]), "pos": a["Translate"]} for a in ff]
        for i in range(GROTTO_FAIRIES):
            spots[f"{g['word']} {i + 1}"] = {
                "kind": "fountain", "setting": SETTINGS["fountain"], "region": region, "rule": g["rule"],
                "group": region, "index": i, "confidence": "high", "places": [places[i]],
                "why": (f"{region}: given on entering the fountain (a copy of its music Area {area['Hash']} runs "
                        f"{module['logic'].rsplit('/', 1)[-1]} with a copied requester; scene ID {row} gives the 8 "
                        f"items once); SoH's Scrubs Fairies need only the room (OoTR: Lens or logic_lens_castle)")}
    return data, spots


# Fairy Note spots and bean plants
# Neither flow can ask the fairy or the soil which one it is. But each binds it (the note's fairy by
# IsBindNearestActor, the soil as the event's requester), and vanilla flows do ask "is the player close to <flow
# actor> <instance name>?" with GameSystemActor EventQueryIsDistanceBetweenActorsClose and InstanceNameB
# (Dm_SY_BancChangeArrive Event89, Dm_ShadowTemple_0015 Event15). So each spot's placement gets a Name of its own
# (none has one and nothing looks them up by name), and a chain of those questions finds the spot.
DISTANCE_QUERY = ("GameSystemActor", "EventQueryIsDistanceBetweenActorsClose")
NOTE_FLOW = "FairySpirit_AppearPoint"
NOTE_TAILS = (("Event141", "Event39"), ("Event64", "Event26"))  # (wait, the step that removes the fairy): the memo
# (Graffiti) entries' shared tail and the plain PopFairySpirit entry's (a Sun's Song point's replace event)
NOTE_SPOTS = [  # (location word, level file of one placement, room, song, region, extra rule, confidence, why)
    ("Graveyard Royal Familys Tomb", "Graveyard", None, "sun", "Graveyard Royal Familys Tomb",
     "is_adult or Slingshot or Boomerang or Sticks or has_explosives or Kokiri_Sword", "high",
     "by Note 26 in the tomb, 18.8 from its effect volume EftLoc_RoyalFamilyTomb (SoH's Royal Family's Tomb Sun Fairy)."
     " Past the tomb's first room, whose two shutters stay shut until its 4 Keese die "
     "(RoyalFamilyTomb_Common_eea8): OoTR's own weapons for the tomb's song, as Song from Royal Familys Tomb."),
    ("Shadow Temple Falling Spikes", "ShadowTemple", 11, "storms", "Shadow Temple Falling Spikes", "True", "high",
     "room 11 by Note 24, 3.1 from the falling-spikes room's lower pots"),
    ("Bottom of the Well", "BottomOfTheWell", 3, "storms", "Bottom of the Well Main Area", "True", "high",
     "room 3 by Note 23, 6.1 from the main area's pots"),
    ("Ice Cavern", "IceCavern", 6, "sun", "Ice Cavern Behind Ice Walls", "Blue_Fire", "high",
     "room 6, 2.4 from the pots behind the red ice (Blue Fire)"),
    ("LLR Tower", "HyruleField", None, "sun", "LLR Tower", "is_child", "high",
     "the Lon Lon silo by Note 15, 8.5 from the LLR heart piece (child: its boxes, as that heart piece)"),
    ("Colossus", "DesertColossus", None, "storms", "Desert Colossus", "True", "high",
     "by Note 25 at the Spirit Temple entrance, 16.8 from the Colossus GS bean patch"),
    ("Fire Temple", "FireTemple", 13, "sun", "Fire Temple Upper", "True", "medium",
     "room 13 by Note 20 (the rolling-rock room above the hammer stairs; drops_regions_d1 room 13)"),
    ("Forest Temple", "ForestTemple", 19, "sun", "Forest Temple Bow Region", "at('Forest Temple Falling Room', True)",
     "medium", "room 19 by Note 19 at the twisted corridor, between the bow rooms (18) and the falling room (24): "
               "both regions asked"),
    ("Water Temple", "WaterTemple", 5, "sun", "Water Temple Falling Platform Room", "True", "medium",
     "room 5 by Note 22, beside the hookshot float platforms (Obj_WaterTemple_FloatFloorManager_HookShot_A_01)"),
]
SONG_RULE = {"sun": "can_play(Suns_Song)", "storms": "can_play(Song_of_Storms)"}
BEAN_FLOW = "Field_PlantMagicBeanStormMelody"
BEAN_ENTRIES = {"EntryPoint0": "Obj_SmallFarm_A_02", "EntryPoint1": "Obj_SmallFarm_A_01"}
BEAN_TAIL = ("Event19", "Event32")  # the fairy left (IsStart_FairySpiritMove false) -> Navi's balloon, the last step
BEAN_ITEMS = 3  # SoH: three fairies per bean plant
BEAN_SPOTS = [  # (soil hash, location word, OoTR region, extra rule)
    ("6092667454768667954", "KF", "Kokiri Forest", "True"),
    ("5234955674857122897", "LW Bridge", "Lost Woods", "True"),
    ("176409868210268833", "LW Theater", "LW Beyond Mido", "True"),
    ("17092212646454540992", "ZR", "Zora River", "True"),
    ("6833516270248855649", "LH", "Lake Hylia", "True"),
    ("10857724324414230743", "GV", "GV Upper Stream", "True"),
    ("14429198438059673734", "Colossus", "Desert Colossus", "True"),
    ("17500344509500247365", "Graveyard", "Graveyard", "True"),
    ("18350441421271687772", "DMT", "Death Mountain", "has_explosives or Progressive_Strength_Upgrade"),
    ("12044463103654268862", "DMC", "DMC Central Local", "True"),
]
BEAN_RULE = "is_child and can_plant_bean and can_play(Song_of_Storms)"  # OoTR's Bean Plant Fairy, no bottle
NOTE_NAME, SOIL_NAME = "RandoNoteFairy_{}", "RandoBeanSoil_{}"
NEAR = 4.0  # metres. A spot's fairy or soil is within ~1 of Link, and spots of one level are 25+ apart


def _distance(actor, instance, yes, no):
    return {"actor": DISTANCE_QUERY[0], "query": DISTANCE_QUERY[1],
            "params": {"ActorNameA": "Player_Event", "InstanceNameA": "", "IsAnchorActorA": False,
                       "ActorNameB": actor, "InstanceNameB": instance, "IsAnchorActorB": False,
                       "IsTargetPlayingAllEvent": False, "CheckDistance": NEAR},
            "cases": {0: yes, 1: no}}


def _check_tail(fs, flow, tails, problems, delete=None):
    ev = _event(fs, flow)
    fc = ev.flowcharts[0]
    names = {e["name"]: e for e in fc["events"]}
    for a, b in tails:
        if a not in names or b not in names or names[a].get("next") != names[b]["idx"]:
            problems.append(f"{flow}: {a} no longer leads to {b}")
        elif delete and fc["actors"][names[b]["actor"]]["actions"][names[b]["action"]] != delete:
            problems.append(f"{flow}: {b} is no longer {delete}")
    acts = {a["name"]: a for a in fc["actors"]}
    if DISTANCE_QUERY[1] not in (acts.get(DISTANCE_QUERY[0]) or {}).get("queries", []) or "GameDataActor" not in acts:
        problems.append(f"{flow}: no {DISTANCE_QUERY[0]}.{DISTANCE_QUERY[1]} or GameDataActor")
    return fc, acts


def _notes(fs, problems):
    """The 9 Fairy Note spots: one location each (SoH's song fairies)."""
    fc, acts = _check_tail(fs, NOTE_FLOW, NOTE_TAILS, problems, "EventTriggerSetEventBoolEX1")
    if "Obj_FairySpirit" not in acts or not ((acts["Obj_FairySpirit"].get("params") or {}).get("items") or {}).get(
            "IsBindNearestActor", {}).get("value"):
        problems.append(f"{NOTE_FLOW}: its Obj_FairySpirit is no longer bound as the nearest one")
    fairies = [(rel, a) for rel, a in _all_actors(fs) if a.get("Gyaml") == "Obj_FairySpirit"
               and not (a.get("Dynamic") or {}).get("IsGossipStoneAppearance") and a.get("Name") != "MagicBeen"]
    points = [(rel, a) for rel, a in _all_actors(fs) if a.get("Gyaml", "").startswith("FairySpirit_AppearPoint_")]
    spots, data = {}, []
    for k, (word, level, room, song, region, rule, conf, why) in enumerate(NOTE_SPOTS):
        mine = [(rel, a) for rel, a in fairies if rel.split("/")[1] == level and
                (room is None or (a.get("Dynamic") or {}).get("DefaultDungeonRoomIndex") == room)]
        if not mine or len({tuple(round(x, 1) for x in a["Translate"]) for _, a in mine}) != 1 or any(a.get("Name") for _, a in mine):
            problems.append(f"{word}: {len(mine)} unnamed Fairy Note fairies at one spot expected in {level} room {room}")
            continue
        pos = mine[0][1]["Translate"]
        kind = next((a["Gyaml"] for rel, a in points if rel.split("/")[1] == level and math.dist(a["Translate"], pos) < 0.5),
                    None)
        if kind != f"FairySpirit_AppearPoint_{'SunSong' if song == 'sun' else 'StormSong'}":
            problems.append(f"{word}: its appear point is {kind}, not a {song} point")
        name = f"{word} {'Sun' if song == 'sun' else 'Storms'} Fairy"
        places = [{"file": rel, "hash": str(a["Hash"]), "pos": a["Translate"]} for rel, a in mine]
        spots[name] = {"kind": "song", "setting": SETTINGS["song"], "region": region,
                       "rule": f"({rule}) and ({SONG_RULE[song]})" if rule != "True" else SONG_RULE[song],
                       "group": "notes", "index": k, "instance": NOTE_NAME.format(k), "places": places,
                       "confidence": conf, "why": why}
        data.append({"location": name, "instance": NOTE_NAME.format(k), "places": places})
    return {"flow": NOTE_FLOW, "tails": [list(t) for t in NOTE_TAILS], "actor": "Obj_FairySpirit", "spots": data}, spots


def _beans(fs, problems):
    """The 10 bean plants that call a fairy: three locations each, given together (SoH's bean fairies)."""
    fc, acts = _check_tail(fs, BEAN_FLOW, (BEAN_TAIL,), problems)
    entries = {k: fc["events"][v["main"]]["name"] for k, v in fc["entry_points"].items()}
    if sorted(entries) != sorted(BEAN_ENTRIES) or any(a not in acts for a in BEAN_ENTRIES.values()):
        problems.append(f"{BEAN_FLOW}: entries {sorted(entries)} or soil actors changed")
    soils = defaultdict(list)
    for rel, a in _all_actors(fs):
        if a.get("Gyaml") in BEAN_ENTRIES.values():
            soils[str(a["Hash"])].append((rel, a))
    where, _ = _ootr_rules()
    spots, data = {}, []
    for k, (h, word, region, extra) in enumerate(BEAN_SPOTS):
        ps = soils.get(h) or []
        if not ps or any(a.get("Name") for _, a in ps):
            problems.append(f"bean soil {h}: {len(ps)} placements (unnamed expected)")
            continue
        types = {a["Gyaml"] for _, a in ps}
        if len(types) != 1:
            problems.append(f"bean soil {h}: two soil types {types}")
            continue
        near = [a for rel, a in _all_actors(fs) if a.get("Gyaml") == "Obj_FairySpirit" and a.get("Name") == "MagicBeen"
                and rel.split("/")[1] == ps[0][0].split("/")[1] and math.dist(a["Translate"], ps[0][1]["Translate"]) < 2]
        if not near:
            problems.append(f"bean soil {h}: no bean fairy (MagicBeen) beside it")
        places = [{"file": rel, "hash": h, "pos": a["Translate"]} for rel, a in ps]
        rule = BEAN_RULE if extra == "True" else f"({BEAN_RULE}) and ({extra})"
        names = []
        for i in range(BEAN_ITEMS):
            name = f"{word} Bean Plant Fairy {i + 1}"
            names.append(name)
            spots[name] = {"kind": "bean", "setting": SETTINGS["bean"], "region": region, "rule": rule,
                           "group": f"bean:{h}", "index": i, "instance": SOIL_NAME.format(k), "places": places,
                           "confidence": "high",
                           "why": f"the {word} soil: the Song of Storms over "
                                  f"its sprout calls a fairy; OoTR's Bean Plant Fairy rule"}
        data.append({"soil": h, "actor": types.pop(), "instance": SOIL_NAME.format(k), "locations": names,
                     "places": places})
    return {"flow": BEAN_FLOW, "entries": BEAN_ENTRIES, "entry_steps": entries, "tail": list(BEAN_TAIL),
            "spots": data}, spots


_ALL = {}


def _all_actors(fs):
    """[(rel, actor)] of every level file (cached)."""
    from romtools import byml_load
    import glob
    if "a" not in _ALL:
        root = fs.root if hasattr(fs, "root") else DEFAULT_ROMFS
        out = []
        for p in sorted(glob.glob(os.path.join(root, "Banc", "*", "*.bcett.byml.zs"))):
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            try:
                out += [(rel, a) for a in byml_load(fs.read(rel))[0].get("Actors") or []]
            except Exception:  # noqa: BLE001 - a level file the parser can't read holds no chest of ours
                continue
        _ALL["a"] = out
    return _ALL["a"]


def build(romfs=DEFAULT_ROMFS, write=True):
    fs = _fs(romfs)
    fs.root = romfs
    problems = []
    stone_flow = _check_stone_flow(fs, problems)
    spots = _stones(fs, problems)
    colossus, cs = _check_colossus(fs, problems)
    spots.update(cs)
    grottos, gs = _grottos(fs, problems)
    spots.update(gs)
    rooms, rs = _rooms(fs, problems)
    spots.update(rs)
    notes, ns = _notes(fs, problems)
    spots.update(ns)
    beans, bs = _beans(fs, problems)
    spots.update(bs)
    if problems:
        raise FairyError("fairies: the game files don't match:\n  " + "\n  ".join(problems))
    out = {"_about": __doc__.strip().splitlines()[0], "built": list(BUILT), "settings": SETTINGS,
           "spots": dict(sorted(spots.items())), "stones": stone_flow, "colossus": colossus, "grottos": grottos,
           "rooms": rooms, "notes": notes, "beans": beans}
    regions = defaultdict(dict)
    for n, s in sorted(spots.items()):
        regions[s["region"]][n] = s["rule"]
    logic = {"_about": "Fairy shuffle locations (generated by tools/rando/fairies.py; see data/rando/fairy_map.json): "
                       "new OoTR locations in their regions. The plugin locks them with a Recovery Heart when their "
                       "setting is off.",
             "new_locations": {n: {"type": LOC_TYPE, "filter_tags": [], "scene": None, "default": None}
                               for n in sorted(spots)},
             "regions": {r: {"locations": dict(sorted(locs.items()))} for r, locs in sorted(regions.items())}}
    if write:
        json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        json.dump(logic, open(LOGIC_OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out


_MAP = {}


def fairy_map():
    if "m" not in _MAP:
        _MAP["m"] = json.load(open(OUT, encoding="utf-8"))
    return _MAP["m"]


# Read back (tools/rando/in_game_check.py)
def verify(patch_dir, rec, romfs=DEFAULT_ROMFS):
    """Reads a built patch back for the plan's "_fairies" record and returns [problem, ...]. The record is {"stones":
    {location: {"flag", "value", "big", "item"}}, "scratch": flag, "colossus": [...], "grottos": {region: [...]}}."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch_dir])
    fs.root = romfs
    m = fairy_map()
    problems = []

    def steps(file):
        ev = _event(fs, file)
        fc = ev.flowcharts[0]
        return fc, {e["name"]: e for e in fc["events"]}

    def params(e):
        return {k: v.get("value") for k, v in ((e.get("params") or {}).get("items") or {}).items()}

    def query(fc, e):
        return fc["actors"][e["actor"]]["queries"][e["query"]] if e["type"] == "switch" else None

    def gives_from(fc, ev, start, limit=12):
        """Names of what the steps from `start` give (call targets and ActorName params), following next."""
        out, i, seen = [], start, set()
        byidx = {x["idx"]: x for x in ev.values()}
        while i is not None and i != 0xFFFF and i not in seen and len(out) < limit:
            seen.add(i)
            e = byidx[i]
            if e["type"] == "subflow":
                out.append(f"{e.get('flowchart')}:{e.get('entry_point')}" + (
                    f"[{params(e).get('ActorName')}]" if params(e).get("ActorName") else ""))
            i = e.get("next")
        return out

    st = rec.get("stones") or {}
    if st:
        s = m["stones"]
        fc, ev = steps(s["flow"])
        sw = ev[s["switch"]]
        scratch = rec["scratch"]
        for pos in s["storm_cases"] + s["calm_cases"]:
            t = next((x for x in ev.values() if x["idx"] == sw["cases"][pos]["next"]), None)
            want = pos in s["storm_cases"]
            if t is None or params(t).get("GameDataName") != scratch or bool(params(t).get("Value")) != want or \
                    t.get("next") != ev[s["melody_next"]]["idx"]:
                problems.append(f"{s['flow']}: melody case {pos} doesn't set {scratch} to {want} and go on")
        q = next((x for x in ev.values() if x["idx"] == ev[s["after"]]["next"]), None)
        if q is None or query(fc, q) != s["query"]:
            problems.append(f"{s['flow']}: {s['after']} doesn't lead to the stone's own query")
        else:
            cases = {c["value"]: c["next"] for c in q["cases"]}
            byidx = {x["idx"]: x for x in ev.values()}
            for loc, x in st.items():
                t = byidx.get(cases.get(x["value"]))
                if t is None or params(t).get("GameDataName") != scratch:
                    problems.append(f"{loc}: stone {x['value']} doesn't ask which song was played")
                    continue
                branch = byidx.get(next(c["next"] for c in t["cases"] if c["value"] == (0 if x["big"] else 1)))
                if branch is None or params(branch).get("GameDataName") != x["flag"]:
                    problems.append(f"{loc}: its {'big' if x['big'] else 'normal'} branch doesn't check {x['flag']}")
                    continue
                no = byidx.get(next((c["next"] for c in branch["cases"] if c["value"] == 1), None))
                if no is None or params(no).get("GameDataName") != x["flag"] or params(no).get("Value") is not True:
                    problems.append(f"{loc}: {x['flag']} isn't set before the give")
                    continue
                got = gives_from(fc, ev, no.get("next"))
                if not got or not any(x["give"] in g for g in got):
                    problems.append(f"{loc}: gives {got}, expected {x['give']}")
    col = rec.get("colossus") or []
    if col:
        c = m["colossus"]
        fc, ev = steps(c["flow"])
        got = gives_from(fc, ev, ev[c["after"]]["next"], 20)
        want = [x["give"] for x in sorted(col, key=lambda y: y["index"])]
        if len(got) != len(want) or any(w not in g for w, g in zip(want, got)):
            problems.append(f"{c['flow']}: after {c['after']} gives {got}, expected {want}")
    def by_name(fc, ev, start, limit=400):
        """{instance: (flag, [gives])} for the "near <actor> <instance>?" chain from step index `start`."""
        byidx = {x["idx"]: x for x in ev.values()}
        out, seen, todo = {}, set(), [start]
        while todo and len(seen) < limit:
            i = todo.pop()
            if i is None or i == 0xFFFF or i in seen or i not in byidx:
                continue
            seen.add(i)
            e = byidx[i]
            if e["type"] == "switch" and query(fc, e) == DISTANCE_QUERY[1]:
                inst = params(e).get("InstanceNameB")
                yes = byidx.get(next((c["next"] for c in e["cases"] if c["value"] == 0), None))
                no = next((c["next"] for c in e["cases"] if c["value"] == 1), None)
                todo.append(no)
                if yes is None or yes["type"] != "switch":
                    out[inst] = (None, [])
                    continue
                flag = params(yes).get("GameDataName")
                st_ = byidx.get(next((c["next"] for c in yes["cases"] if c["value"] == 1), None))
                ok = st_ is not None and params(st_).get("GameDataName") == flag and params(st_).get("Value") is True
                out[inst] = (flag if ok else None, gives_from(fc, ev, st_.get("next") if ok else None, 20))
            elif e["type"] == "switch":
                todo += [c["next"] for c in e["cases"]]
            else:
                todo.append(e.get("next"))
        return out

    nts = rec.get("notes") or {}
    if nts:
        nt = m["notes"]
        fc, ev = steps(nt["flow"])
        for wait, leave in nt["tails"]:
            found = by_name(fc, ev, ev[wait]["next"])
            for loc, x in nts.items():
                flag, got = found.get(x["instance"], (None, []))
                if flag != x["flag"] or not got or x["give"] not in got[0]:
                    problems.append(f"{loc}: after {wait} the fairy named {x['instance']} gives {got} once by {flag}, "
                                    f"expected {x['give']} by {x['flag']}")
    bns = rec.get("beans") or {}
    if bns:
        bn = m["beans"]
        fc, ev = steps(bn["flow"])
        byidx = {x["idx"]: x for x in ev.values()}
        for ep in bn["entries"]:
            first = byidx.get(fc["entry_points"][ep]["main"]) or {}
            if params(first).get("GameDataName") != rec.get("bean_scratch") or \
                    byidx.get(first.get("next"), {}).get("name") != bn["entry_steps"][ep]:
                problems.append(f"{bn['flow']}: {ep} doesn't record its soil type, then start as vanilla")
        found = by_name(fc, ev, ev[bn["tail"][0]]["next"])
        for soil, x in bns.items():
            flag, got = found.get(x["instance"], (None, []))
            want = [g["give"] for g in sorted(x["gives"], key=lambda g: g["index"])]
            if flag != x["flag"] or len(got) != len(want) or any(w not in g for w, g in zip(want, got)):
                problems.append(f"bean soil {soil} ({x['instance']}): gives {got} once by {flag}, expected {want} by "
                                f"{x['flag']}")
    named = [(pl, x["instance"]) for x in list(nts.values()) + list(bns.values()) for pl in x["places"]]
    for rel in sorted({pl["file"] for pl, _ in named}):
        acts = {str(a.get("Hash")): a for a in byml_load(fs.read(rel))[0].get("Actors", [])}
        for pl, inst in named:
            if pl["file"] == rel and (acts.get(pl["hash"]) or {}).get("Name") != inst:
                problems.append(f"{rel}: {pl['hash']} isn't named {inst}")
    gro = rec.get("grottos") or {}
    if gro:
        rows = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}
        for region, items in sorted(gro.items()):
            g = m["grottos"][region]
            sc = g["scene"]
            fc, ev = steps(sc["file"])
            if sc["entry"] not in fc["entry_points"]:
                problems.append(f"{sc['file']}: no entry {sc['entry']}")
                continue
            start = fc["entry_points"][sc["entry"]]["main"]
            first = next(x for x in ev.values() if x["idx"] == start)
            if first["type"] != "subflow" or first.get("entry_point") != sc["vanilla"]:
                problems.append(f"{sc['entry']}: doesn't start with the vanilla {sc['vanilla']}")
            gq = next((x for x in ev.values() if x["idx"] == first["next"]), None)
            if gq is None or params(gq).get("GameDataName") != g["once"]:
                problems.append(f"{sc['entry']}: no once-check on {g['once']}")
                continue
            no = next((x for x in ev.values() if x["idx"] == next(c["next"] for c in gq["cases"] if c["value"] == 1)), None)
            got = gives_from(fc, ev, (no or {}).get("next"), 20)
            want = [x["give"] for x in sorted(items, key=lambda y: y["index"])]
            if len(got) != len(want) or any(w not in gg for w, gg in zip(want, got)):
                problems.append(f"{region}: the grotto gives {got}, expected {want}")
            row = rows.get(g["row"], {})
            if not str(row.get("FlowchartFileName", "")).endswith(f"/{sc['file']}.evfc") or \
                    row.get("EntryPointName") != sc["entry"]:
                problems.append(f"scene ID {g['row']} doesn't run {sc['file']}:{sc['entry']}")
            for t in g["triggers"]:
                acts = {str(a.get("Hash")): a for a in byml_load(fs.read(t["file"]))[0].get("Actors", [])}
                if ((acts.get(t["hash"]) or {}).get("Dynamic") or {}).get("RequestEventName") != g["row"]:
                    problems.append(f"{t['file']}: {region}'s entry requester doesn't ask for {g['row']}")
            for ch in g["row_chests"]:
                acts = {str(a.get("Hash")): a for a in byml_load(fs.read(ch["file"]))[0].get("Actors", [])}
                if ((acts.get(ch["hash"]) or {}).get("Dynamic") or {}).get("GetEventName") == g["row"]:
                    problems.append(f"{ch['file']}: chest {ch['hash']} still plays scene ID {g['row']}")
    rms = rec.get("rooms") or {}
    if rms:
        problems += _verify_rooms(fs, m, rms, steps, params, gives_from)
    return problems


def _verify_rooms(fs, m, rms, steps, params, gives_from):
    """Checks the fountain rooms of a built patch (ROOMS): the copies, their logic group and spawn groups, the scene
    row and its once-only gives."""
    from romtools import Romfs, byml_load
    van = Romfs(fs.root, os.path.join(HERE, "original"))
    rows = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}
    problems = []
    for region, items in sorted(rms.items()):
        g = m["rooms"][region]
        sc = g["scene"]
        fc, ev = steps(sc["file"])
        byidx = {x["idx"]: x for x in ev.values()}
        if sc["entry"] not in fc["entry_points"]:
            problems.append(f"{sc['file']}: no entry {sc['entry']}")
            continue
        q = byidx.get(fc["entry_points"][sc["entry"]]["main"]) or {}
        if q.get("type") != "switch" or params(q).get("GameDataName") != g["once"]:
            problems.append(f"{sc['entry']}: doesn't start with a once-check on {g['once']}")
            continue
        s_ = byidx.get(next((c["next"] for c in q["cases"] if c["value"] == 1), None)) or {}
        if params(s_).get("GameDataName") != g["once"] or params(s_).get("Value") is not True:
            problems.append(f"{sc['entry']}: {g['once']} isn't set before the gives")
            continue
        got = gives_from(fc, ev, s_.get("next"), 20)
        want = [x["give"] for x in sorted(items, key=lambda y: y["index"])]
        if len(got) != len(want) or any(w not in gg for w, gg in zip(want, got)):
            problems.append(f"{region}: the room gives {got}, expected {want}")
        row = rows.get(g["row"], {})
        if not str(row.get("FlowchartFileName", "")).endswith(f"/{sc['file']}.evfc") or \
                row.get("EntryPointName") != sc["entry"]:
            problems.append(f"scene ID {g['row']} doesn't run {sc['file']}:{sc['entry']}")
        new = byml_load(fs.read(g["file"]))[0]
        old = {str(a["Hash"]): a for a in byml_load(van.read(g["file"]))[0]["Actors"]}
        acts = {str(a["Hash"]): a for a in new["Actors"]}
        ar, rq = g["area"], g["requester"]
        a, src = acts.get(ar["twin"]), old.get(ar["source"])
        if a is None or src is None or a.get("Gyaml") != "Area" or a.get("Presence") != g["presence"] or \
                a.get("Links") or any(a.get(k) != src.get(k) for k in ("Translate", "Scale", "Dynamic", "SRTHash")):
            problems.append(f"{g['file']}: area copy {ar['twin']} isn't {ar['source']} with the lazy Presence "
                            f"{g['presence']}")
        r, src = acts.get(rq["twin"]), old.get(rq["source"])
        if r is None or src is None or r.get("Gyaml") != "EventRequestActor" or r.get("Links") or \
                r.get("Dynamic") != {"RequestEventName": g["row"]} or r.get("Translate") != src.get("Translate"):
            problems.append(f"{g['file']}: requester copy {rq['twin']} doesn't ask for {g['row']} (without links)")
        gr = g["group"]
        mine = [x for x in new.get("AiGroups") or [] if str(x.get("Hash")) == gr["hash"]]
        refs = [(x["Id"], x["Path"], str(x["Reference"])) for x in mine[0]["References"]] if len(mine) == 1 else []
        if len(mine) != 1 or mine[0]["Logic"] != gr["logic"] or \
                refs != [(gr["area_id"], gr["area_id"], ar["twin"]), (gr["event_id"], gr["event_id"], rq["twin"])]:
            problems.append(f"{g['file']}: no logic group {gr['hash']} running {gr['logic']} on the two copies")
        pair = sorted([ar["twin"], rq["twin"]])
        for grp in ("FarDeleteGroups", "SimultaneousGroups"):
            holding = [sorted(map(str, mm)) for mm in new.get(grp) or [] if set(map(str, mm)) & set(pair)]
            if holding != [pair]:
                problems.append(f"{g['file']}: the two copies are not one {grp} entry of their own ({holding})")
        for ch in g["row_chests"]:
            c = {str(x.get("Hash")): x for x in byml_load(fs.read(ch["file"]))[0].get("Actors", [])}
            if ((c.get(ch["hash"]) or {}).get("Dynamic") or {}).get("GetEventName") == g["row"]:
                problems.append(f"{ch['file']}: chest {ch['hash']} still plays scene ID {g['row']}")
    return problems


def main(argv):
    romfs = argv[1] if len(argv) > 1 else DEFAULT_ROMFS
    out = build(romfs)
    by = defaultdict(int)
    for s in out["spots"].values():
        by[s["kind"]] += 1
    print(f"{len(out['spots'])} fairy locations: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
    print(f"written to {os.path.relpath(OUT, HERE)} and {os.path.relpath(LOGIC_OUT, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
