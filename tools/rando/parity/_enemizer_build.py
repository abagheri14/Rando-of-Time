"""Build data/rando/enemizer.json (the enemy randomizer's slots and swap rules) from the game files.

usage: python tools/rando/parity/_enemizer_build.py ROMFS

Reads every level file (Banc/<Area>/<Level>_{Static,Dynamic}.bcett.byml.zs, vanilla copies in original/ first),
every enemy actor pack (Pack/Actor/Enemy_*.pack.zs) and every level logic module (Logic/*.ainb).
In short:

- A level only gets enemy types it already places, since a type new to a level broke Kokiri Forest. The
  candidates for a slot are the enemy types placed anywhere in the same level (Static + Dynamic file).
- Slots something else in the level watches (enemy counters and shutters linking to them, level logic modules
  creating them by instance) only take a "twin". That's a type whose character controller, AI graphs, damage
  parameters, logic node class (ActorLogicNodeRef), save-data setting (ActorGameDataSetting) and death setting
  (DeathRef: how it dies and respawns) are the same as the original's.
  Twins move, fight, take damage and die the same way and the same logic node drives them, so a room cleared by
  killing them needs the same weapons as before and OoTR's rules stay exact. Logic modules bind their actors by the
  placement's hash, not by the type name in the reference (1,663 vanilla references already name a different type,
  e.g. Obj_Pot_A_06 -> Obj_Pot_A_06_Dream), so a type swap keeps the binding.
- Slots nothing watches ("free": no links, no logic module, no instance name, no rails, no event settings, no item
  drop) are never needed by the logic. They also take any other type of the same habitat placed in the level, but
  a walking enemy only takes a type whose body is no wider (character-controller shape), so it can't block a
  passage the original left open.
- Never touched: bosses and mini-bosses, scrubs, Skull Kid, Poe sisters and Big Poes, Gold Skulltulas (their spots
  are the gs_positions plugin's), Deku Babas (OoTR's logic gets Deku Sticks and Nuts from them), enemies seen only
  with the Lens (*_Truth), decoys (*_Haribote), the Jabu-Jabu tentacles, floor tiles, flying pots, fake doors,
  rolling spikes, Gohma eggs, Dead Hand, Anubis, Wallmasters and Floormasters (they carry Link off), Like Likes (they
  eat his shield) and anything with an item drop (Drop__DropActor) or listed in data/rando/drop_map.json.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load, sarc_files  # noqa: E402
from actor_params import ActorParams  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "enemizer.json")
SKIP_AREAS = ("BancBasedResource", "GameBancParam", "EnemyMuseum", "DreamWorld")
# never swapped from or to (reasons in the module docstring)
EXCLUDE_RX = re.compile(r"Dictionary|DungeonBoss|MiddleBoss|Scrub|SkullKid|GhostPicture|Poe_(Amy|Beth|Joelle|Meg|Big|"
                        r"Hyrule|Flat|Sharp)|Skulltula_Gold|Dekubaba|_Truth|Haribote|Tentacle|CrazyFloorTile|FlyingPot|"
                        r"TrickyDoor|Enemy_Spike|Gohma_Egg|DeadHand|Anubis|Wallmaster|Floormaster|LikeLike|Manager|"
                        r"Peahat_AircraftCarrier|Peahat_Larva|ClimaxOnly")
# habitats for free slots (from the packs: flyers run FlyingPathFindingUser / BubbleBase patrol / Poe wander AI)
HABITAT = {
    "flying": ("Enemy_Keese", "Enemy_Keese_Fire", "Enemy_Keese_Ice", "Enemy_Guay_Fixed", "Enemy_Bubble_Red",
               "Enemy_Bubble_Blue", "Enemy_Bubble_Green", "Enemy_Bubble_White", "Enemy_Poe"),
    "ground": ("Enemy_Stalfos", "Enemy_Stalfos_Weak", "Enemy_Stalfos_ForChild", "Enemy_ReDead", "Enemy_Gibdo",
               "Enemy_Wolfos", "Enemy_Wolfos_White", "Enemy_BabyDodongo", "Enemy_Dodongo", "Enemy_TorchSlug",
               "Enemy_Tektite_Red", "Enemy_Dinolfos", "Enemy_Lizalfos", "Enemy_Moblin", "Enemy_Moblin_Club"),
}
SENSOR_SHAPE = re.compile(r"Atk|Attack|Tgt|Sensor|Perception|Search|Condition|Punch|Chemical|Weak|Hit", re.I)
# placement settings that tie an enemy to an event or an item
EVENT_KEYS = {"TalkEventName", "AttackedEventName", "DamageEventName", "Wallmaster_BootEventName",
              "IsIntendedForEventAppear", "Drop__DropActor", "PoeBig_FenceID", "PoeBig_IsCleared"}
# links into a slot that only watch it die (vanilla links them to mixed enemy types, so they don't care about the
# type)
WATCHERS = re.compile(r"^Obj_EnemyCounter_|SwitchShutter")


def level_of(rel):
    return re.sub(r"_(Static|Dynamic)$", "", rel.split("/")[-1].replace(".bcett.byml.zs", ""))


def resolved_components(fs, actor, files, seen=None):
    """An actor's ActorParam Components with its $parent chain merged (child entries win)."""
    seen = seen or set()
    ap = [f for f in files if f.startswith("Actor/") and f.endswith(".engine__actor__ActorParam.bgyml")
          and f.split("/")[-1].split(".")[0] == actor]
    if not ap:
        return {}
    root, _ = byml_load(files[ap[0]])
    comps = dict(root.get("Components") or {})
    parent = root.get("$parent")
    if parent:
        pname = parent.split("/")[-1].split(".")[0]
        if pname not in seen:
            seen.add(pname)
            pfiles = files
            if not any(f.split("/")[-1].split(".")[0] == pname for f in files if f.startswith("Actor/")):
                path = f"Pack/Actor/{pname}.pack.zs"
                if os.path.exists(fs.path(path)):
                    pfiles = sarc_files(fs.read(path))
            comps = dict(resolved_components(fs, pname, pfiles, seen), **comps)
    return comps


def type_info(fs, actor):
    files = sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))
    comps = resolved_components(fs, actor, files)
    cc = sorted(f.split("/")[-1].split(".")[0] for f in files if "CharacterControllerParam" in f)
    ai = hashlib.md5(b"".join(files[f] for f in sorted(files) if f.startswith("AI/"))).hexdigest()
    dmg = hashlib.md5(b"".join(files[f] for f in sorted(files) if "DamageParameters" in f)).hexdigest()
    # The original enemy's width is its controller shape (*_Cct* / cct_*), and a replacement's is the widest solid
    # shape in its pack. Attack, target and sensor shapes don't count.
    extent = extent_max = None
    for f in sorted(files):
        if "ShapeParam" not in f or SENSOR_SHAPE.search(f.split("/")[-1]):
            continue
        root, _ = byml_load(files[f])
        box = (root or {}).get("AutoCalc") or {}
        if box.get("Max") and box.get("Min"):
            e = round(max(abs(box["Max"]["X"]), abs(box["Max"]["Z"]), abs(box["Min"]["X"]), abs(box["Min"]["Z"])), 3)
            extent_max = max(extent_max or 0.0, e)
            if "cct" in f.lower():
                extent = max(extent or 0.0, e)
    drop_tables = sorted(f.split("/")[-1].split(".")[0] for f in files if f.startswith("Drop/DropTable/"))
    node = (comps.get("ActorLogicNodeRef") or "").split("/")[-1].replace(".aidefn", "")
    gds = (comps.get("ActorGameDataSetting") or "").split("/")[-1].split(".")[0]
    death = (comps.get("DeathRef") or "").split("/")[-1].split(".")[0]  # death/respawn behaviour (DeathParam)
    twin = hashlib.md5(json.dumps([cc, ai, dmg, node, gds, death]).encode()).hexdigest()[:10]
    return {"twin": twin, "node": node, "save": gds, "death": death, "cc": cc, "extent": extent, "extent_max": extent_max,
            "drop_tables": drop_tables}


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    params = ActorParams(romfs)
    drop_hashes = set()
    dm = json.load(open(os.path.join(HERE, "data", "rando", "drop_map.json"), encoding="utf-8"))
    for sec in ("drops", "new", "extras"):
        for e in (dm.get(sec) or {}).values():
            for p in (e.get("placements") or []) if isinstance(e, dict) else []:
                drop_hashes.add(str(p.get("hash")))
    slots, placed = {}, {}
    banc = os.path.join(romfs, "Banc")
    for area in sorted(os.listdir(banc)):
        if area in SKIP_AREAS or not os.path.isdir(os.path.join(banc, area)):
            continue
        for fn in sorted(os.listdir(os.path.join(banc, area))):
            if not fn.endswith(".bcett.byml.zs"):
                continue
            rel = f"Banc/{area}/{fn}"
            root, _ = byml_load(fs.read(rel))
            acts = (root or {}).get("Actors") or []
            lvl = level_of(rel)
            refd = {}
            for g in (root or {}).get("AiGroups") or []:
                for ref in g.get("References") or []:
                    refd.setdefault(ref.get("Reference"), []).append(g["Logic"].split("/")[-1])
            links_in = {}
            for b in acts:
                for link in b.get("Links") or []:
                    links_in.setdefault(link.get("Dst"), []).append(b.get("Gyaml", ""))
            for a in acts:
                g = a.get("Gyaml", "")
                if not g.startswith("Enemy_"):
                    continue
                placed.setdefault(lvl, set()).add(g)
                dyn = a.get("Dynamic") or {}
                why = []
                if EXCLUDE_RX.search(g):
                    why.append("type never swapped")
                if str(a.get("Hash")) in drop_hashes:
                    why.append("a drops-plugin location")
                if set(dyn) & EVENT_KEYS:
                    why.append("event or item setting " + ",".join(sorted(set(dyn) & EVENT_KEYS)))
                if a.get("Name"):
                    why.append("instance name (events may address it)")
                if a.get("Links"):
                    why.append("links to other actors")
                ins = links_in.get(a.get("Hash"), [])
                if any(not WATCHERS.search(x) for x in ins):
                    why.append("linked from " + ",".join(sorted({x for x in ins if not WATCHERS.search(x)})))
                watched = bool(ins) or a.get("Hash") in refd
                slots.setdefault(lvl, []).append({
                    "file": rel, "hash": str(a.get("Hash")), "actor": g, "keys": sorted(dyn),
                    "drop_table": dyn.get("Drop__DropTable"), "room": dyn.get("DefaultDungeonRoomIndex"),
                    "rails": "Rails" in a, "watched": watched, "skip": why})
    types = {}
    for lvl, ts in placed.items():
        for t in ts:
            if t not in types and not EXCLUDE_RX.search(t):
                types[t] = type_info(fs, t)
                types[t]["params"] = sorted(params.allowed(t))
    for h, members in HABITAT.items():
        for t in members:
            if t in types:
                types[t]["habitat"] = h
    out = {"_about": "Generated by tools/rando/parity/_enemizer_build.py from the game files. levels: enemy placements "
                     "per level (Static + Dynamic file) with why a slot is never swapped (skip) and whether something "
                     "in the level watches it (watched: twins only). placed: enemy types each level places. types: "
                     "twin = character controller + AI + damage parameters + logic node + save-data setting "
                     "fingerprint; habitat and body extent for free slots.",
           "romfs": romfs.replace("\\", "/"),
           "placed": {k: sorted(v) for k, v in sorted(placed.items())},
           "types": dict(sorted(types.items())),
           "levels": {k: v for k, v in sorted(slots.items())}}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    n = sum(len(v) for v in slots.values())
    usable = sum(1 for v in slots.values() for s in v if not s["skip"])
    print(f"{n} enemy placements in {len(slots)} levels, {usable} not excluded -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
