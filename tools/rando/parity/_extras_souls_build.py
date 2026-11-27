"""Build data/rando/extras_souls_data.json: the game facts the extras_souls plugin (extras_souls.py) relies on, read
from the game files (vanilla view), so the plugin can write patch plans without the romfs.

usage: python tools/rando/parity/_extras_souls_build.py ROMFS [VANILLA_DIR]
       (VANILLA_DIR: the saved originals of patched files; default ./original)

What it records and checks (the build stops when a file differs from what the plugin was written against):
- bosses: for each of the eight dungeon bosses, the scene its arena plays when Link arrives (the boss's
  appearance, RSDB/EventSetting row -> flow file and entry), that entry's first step (its predecessors, kind), and
  where a player who's turned away gets sent. That's the dungeon's own entrance (level, start position, arrival
  scene, air variant), the same place the overworld doorway into the dungeon sends him
  (data/rando/entrances_remake.json, checked against the level file).
- ganondorf: the boss-key door scene into Ganondorf's room (the fight starts from it)
- beans: the ten bean soils (both age files, from the fairies plugin's data/rando/fairy_map.json) with their
  Presence, and each soil's adult leaf platform (Obj_SmallFarm_A_03, the nearest in the adult file) with its
  Presence
- gamedata: the save-data flags the plugin names (type, default)
- flags_claimed: the plugin's own borrowed saved flags, one per soul (tools/rando/free_flags.py pool, downward from
  index FLAG_WINDOW, since the drops plugin takes from the pool's front and the fairies plugin from its end)
- text: the message file the plugin adds its messages to, in every language
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from romtools import Romfs, byml_load, murmur3_32  # noqa: E402
from evfl import Evfl  # noqa: E402
from parity._story_build import newest, step_info  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "extras_souls_data.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
TEXT_FILE = "EventFlowMsg/Item_Event.msbt"

# (OoTR boss name, arena scene row, first step and kind, OoTR entrance, level, boss actor, eject player).
# Entrances come from data/rando/entrances_remake.json. Barinade's row is the door scene, so Link is still
# outside and the door can just stay shut.
BOSSES = {
    "gohma": ("Queen Gohma", "InsideTheDekuTree_BossArea_ShutIn", "Event236",
              "action Player_Event.EventTriggerPlayerEventStartWithDrawn",
              "KF Outside Deku Tree -> Deku Tree Lobby", "InsideTheDekuTree", "Enemy_DungeonBoss_Gohma", True),
    "king_dodongo": ("King Dodongo", "Get_StoneOfFire_AppearBoss", "Event220", "query GameSystemActor.EventQueryIsDreamWorld",
                     "Death Mountain -> Dodongos Cavern Beginning", "DodongoCavern", "Enemy_DungeonBoss_Dodongo", True),
    "barinade": ("Barinade", "Get_StoneOfWater_BossAppear", "Event84", "action Player_Event.EventTriggerParticipateEvent",
                 "Zoras Fountain -> Jabu Jabus Belly Beginning", "InsideJabuJabuBelly", "Enemy_DungeonBoss_Barinade",
                 False),
    "phantom_ganon": ("Phantom Ganon", "ForestTemple_SageOfForest_PhantomGanonAppearance", "Event11",
                      "query GameSystemActor.EventQueryIsDreamWorld",
                      "SFM Forest Temple Entrance Ledge -> Forest Temple Lobby", "ForestTemple",
                      "Enemy_DungeonBoss_PhantomGanon", True),
    "volvagia": ("Volvagia", "SageOfFire_BossAppear", "Event299", "action Player_Event.EventTriggerParticipateEvent",
                 "DMC Fire Temple Entrance -> Fire Temple Lower", "FireTemple", "Enemy_DungeonBoss_Volvagia", True),
    "morpha": ("Morpha", "Demo_SageOfWater_BossAppears", "Event20", "action Player_Event.EventTriggerParticipateEvent",
               "Lake Hylia -> Water Temple Lobby", "WaterTemple", "Enemy_DungeonBoss_Morpha", True),
    "bongo_bongo": ("Bongo Bongo", "ShadowTemple_BossAppear", "Event95", "query GameSystemActor.EventQueryIsDreamWorld",
                    "Graveyard Warp Pad Region -> Shadow Temple Entryway", "ShadowTemple",
                    "Enemy_DungeonBoss_BongoBongo", True),
    "twinrova": ("Twinrova", "SageOfSpirit_BossStart", "Event29", "query GameSystemActor.EventQueryIsDreamWorld",
                 "Desert Colossus -> Spirit Temple Lobby", "SpiritTemple", "Enemy_DungeonBoss_Twinrova", True),
}
GANON = ("Common_Dungeon_OpenShutterMove", "UnlockGanonBossRoomMoveTo0", "Event307", "action Player_Event.EventPlayerMove")
MESSAGE_STEP = ("GetPouchContent", "Event23", "action SystemTextNPC.EventTalk")
ACTORS_NEEDED = ("GameDataActor", "GameSystemActor")
GAMEDATA_FLAGS = ("Sequence_IsChildhood",)
PLATFORM = "Obj_SmallFarm_A_03"
PLATFORM_MAX_DIST = 30.0  # a soil's leaf platform starts beside it (metres in level units)
FLAG_WINDOW = 100  # free_flags.pool() index the flags are taken downward from
FLAGS_NEEDED = 19  # 8 boss souls, Ganon's soul, 10 bean souls


def _rows(fs):
    return {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}


def _flow(romfs, fs, base):
    rel, versions = newest(romfs, base)
    if len(versions) != 1:
        raise SystemExit(f"{base}: {versions}: the plugin edits one version only, check the step names")
    return Evfl(fs.read(rel)).flowcharts[0]


def _hook(romfs, fs, base, entry, step, kind):
    fc = _flow(romfs, fs, base)
    by = {e["name"]: e for e in fc["events"]}
    if entry not in fc["entry_points"]:
        raise SystemExit(f"{base}: no entry {entry}")
    first = fc["events"][fc["entry_points"][entry]["main"]]["name"]
    if first != step:
        raise SystemExit(f"{base}: entry {entry} starts at {first}, expected {step}")
    info = step_info(fc, by[step])
    if not info["kind"].startswith(kind):
        raise SystemExit(f"{base}:{step} is {info['kind']}, expected {kind}")
    actors = [a["name"] for a in fc["actors"]]
    missing = [a for a in ACTORS_NEEDED if a not in actors]
    if missing:
        raise SystemExit(f"{base}: no actor {missing} (the plugin's steps need them)")
    return {"file": base, "flowchart": fc["name"], "entry": entry, "step": step, "info": info}


def _level_actors(fs, level):
    out = []
    for side in ("Static", "Dynamic"):
        rel = f"Banc/{level.split('_')[0]}/{level}_{side}.bcett.byml.zs"
        try:
            out += [(rel, a) for a in byml_load(fs.read(rel))[0].get("Actors") or []]
        except FileNotFoundError:
            continue
    return out


def _bosses(romfs, fs, rows):
    ent = json.load(open(os.path.join(HERE, "data", "rando", "entrances_remake.json"), encoding="utf-8"))["entrances"]
    out = {}
    for key, (name, row, step, kind, entrance, level, boss, eject) in BOSSES.items():
        r = rows.get(row)
        if r is None:
            raise SystemExit(f"{key}: no scene row {row}")
        base = os.path.basename(r["FlowchartFileName"])[:-len(".evfc")]
        entry = r.get("EntryPointName") or "EntryPoint0"
        hook = _hook(romfs, fs, base, entry, step, kind)
        acts = _level_actors(fs, level)
        if not any(a.get("Gyaml") == boss for _, a in acts):
            raise SystemExit(f"{key}: no {boss} in {level}")
        if not any(a.get("Gyaml") == "EventRequestActor" and (a.get("Dynamic") or {}).get("RequestEventName") == row
                   for _, a in acts) and not any((a.get("Dynamic") or {}).get("NomralEvent") == row for _, a in acts):
            raise SystemExit(f"{key}: nothing in {level} starts {row}")
        e = ent.get(entrance)
        if e is None:
            raise SystemExit(f"{key}: no entrance {entrance} in entrances_remake.json")
        t = e["target"]["adult"]
        if t["level"] != level:
            raise SystemExit(f"{key}: {entrance} leads to {t['level']}, not {level}")
        starts = {a.get("Name") for _, a in acts if a.get("Gyaml") == "StartPos"}
        if t["start"] not in starts:
            raise SystemExit(f"{key}: no start position {t['start']} in {level}")
        air = f"{t['start']}_Air" if t.get("air") else ""
        if air and air not in starts:
            raise SystemExit(f"{key}: no air start position {air} in {level}")
        out[key] = {"boss": name, "row": row, "hook": hook, "eject": eject,
                    "entrance": {"level": level, "start": t["start"], "air": air,
                                 "boot": (t.get("fields") or {}).get("NextEventName", "")}}
    return out


def _beans(fs):
    fm = json.load(open(os.path.join(HERE, "data", "rando", "fairy_map.json"), encoding="utf-8"))["beans"]["spots"]
    out = []
    cache = {}

    def level(rel):
        if rel not in cache:
            cache[rel] = byml_load(fs.read(rel))[0].get("Actors") or []
        return cache[rel]
    for i, s in enumerate(fm):
        soils, platforms = [], []
        for p in s["places"]:
            acts = [a for a in level(p["file"]) if str(a.get("Hash")) == p["hash"]]
            if len(acts) != 1 or acts[0].get("Gyaml") not in ("Obj_SmallFarm_A_01", "Obj_SmallFarm_A_02"):
                raise SystemExit(f"bean {i}: {p['file']} has no single soil {p['hash']}")
            pres = acts[0].get("Presence")
            if pres != {"FlagName": "Sequence_IsChildhood", "IsCheckLazy": False, "IsNegation": False}:
                raise SystemExit(f"bean {i}: soil {p['hash']} in {p['file']}: Presence {pres}")
            soils.append({"file": p["file"], "hash": p["hash"], "presence": pres})
            if "_Adult_" in p["file"]:
                pos = acts[0]["Translate"]
                cands = sorted((math.dist(pos, a["Translate"]), str(a["Hash"]), a.get("Presence"))
                               for a in level(p["file"]) if a.get("Gyaml") == PLATFORM)
                if not cands or cands[0][0] > PLATFORM_MAX_DIST:
                    raise SystemExit(f"bean {i}: no {PLATFORM} within {PLATFORM_MAX_DIST} of soil {p['hash']}")
                d, h, pres2 = cands[0]
                if pres2 != {"FlagName": "Sequence_IsChildhood", "IsCheckLazy": False, "IsNegation": True}:
                    raise SystemExit(f"bean {i}: platform {h}: Presence {pres2}")
                platforms.append({"file": p["file"], "hash": h, "presence": pres2, "distance": round(d, 2)})
        if not platforms:
            raise SystemExit(f"bean {i}: no adult file soil")
        out.append({"index": i, "fairy_locations": s["locations"], "soils": soils, "platforms": platforms})
    hashes = [p["hash"] for b in out for p in b["platforms"]]
    if len(hashes) != len(set(hashes)):
        raise SystemExit("two soils share one leaf platform")
    return out


def _flags(fs):
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    index = {}
    for table, entries in gd["Data"].items():
        if table == "Bool64bitKey":
            continue
        for e in entries:
            index.setdefault(e["Hash"], (table, e))
    out = {}
    for name in GAMEDATA_FLAGS:
        hit = index.get(murmur3_32(name))
        if hit is None:
            raise SystemExit(f"no save-data flag {name}")
        out[name] = {"type": hit[0], "default": hit[1].get("DefaultValue")}
    return out


def _claim(romfs):
    import free_flags
    pool = free_flags.pool(romfs, own="extras_souls")  # the pool as it is without this plugin's own claim
    if len(pool) <= FLAG_WINDOW:
        raise SystemExit(f"free_flags pool has {len(pool)} flags, the window starts at {FLAG_WINDOW}")
    return [pool[i] for i in range(FLAG_WINDOW, FLAG_WINDOW - FLAGS_NEEDED, -1)]


def _text(fs, romfs):
    import msbt
    langs = []
    for lang in msbt.archives(romfs):
        if TEXT_FILE not in msbt.read_archive(fs, lang):
            raise SystemExit(f"{lang}: no {TEXT_FILE}")
        langs.append(lang)
    return {"file": TEXT_FILE, "languages": langs}


def main(romfs, vanilla=None):
    fs = Romfs(romfs, vanilla or os.path.join(HERE, "original"))
    rows = _rows(fs)
    out = {"_about": "Built by tools/rando/parity/_extras_souls_build.py from the game files; read by extras_souls.py.",
           "bosses": _bosses(romfs, fs, rows),
           "ganondorf": _hook(romfs, fs, *GANON),
           "beans": _beans(fs), "gamedata": _flags(fs), "text": _text(fs, romfs),
           "flags_claimed": _claim(romfs)}
    fc = _flow(romfs, fs, MESSAGE_STEP[0])
    e = next(x for x in fc["events"] if x["name"] == MESSAGE_STEP[1])
    info = step_info(fc, e)
    if not info["kind"].startswith(MESSAGE_STEP[2]):
        raise SystemExit(f"{MESSAGE_STEP[0]}:{MESSAGE_STEP[1]} is {info['kind']}")
    out["message"] = {"file": MESSAGE_STEP[0], "flowchart": fc["name"], "step": MESSAGE_STEP[1]}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {OUT}: {len(out['bosses'])} bosses, {len(out['beans'])} bean spots "
          f"({sum(len(b['soils']) for b in out['beans'])} soils, {sum(len(b['platforms']) for b in out['beans'])} "
          f"platforms), {len(out['text']['languages'])} languages")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(*sys.argv[1:])
