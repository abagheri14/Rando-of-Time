"""Build data/rando/extras_enemy_souls.json: the regular-enemy soul families (extras_souls kind "enemy").

usage: python tools/rando/parity/_enemy_souls_build.py [LEVELS_JSON] [ROMFS]
  LEVELS_JSON: the vanilla game-logic index's levels (tools/gamedb/build.py; default cache/gamedb/vanilla/levels.json)

Facts, not code, taken from OotrR (github.com/Mozencaz/OotrR, MIT; src/oot_rando/patching/soul_adapter.py):
- the families (Gyaml prefixes per soul) and the actors left out (dictionaries, Gold Skulltulas, business scrubs,
  Nabooru's Iron Knuckle, Skull Kid, Poes, Stalchildren, Leevers, Gerudo thieves, Ganon, the crazy floor tiles and
  tricky doors; the boss rush and Ganon's tower folders)
- a soulless enemy is absent. Its placement's Presence reads the soul's flag (read when the map loads), and an
  enemy with a Presence of its own reads "its soul AND its vanilla condition". OotrR found that without the AND
  they appeared with no soul.
- "defeat every enemy" rooms have to stay openable. A room counter's doors (shutters linking to the counter, or
  around its event requester; shutters linked to or from the enemy itself) get Presence on the soul, so without it
  the shutters are absent (an open passage) and with it the room works like in the game (resolve_room_locks).
- an enemy is mechanical when its defeat drives something besides those doors (a chest, a platform, a fuse...:
  remake_world.enemy_mechanics, ALWAYS_MECHANICAL). Entering a dungeon then needs its mechanical families' souls.
What we do: my rule is "do everything", so every one of OotrR's families has a soul. Every placement of a family
takes its soul, like OotrR's. The room locks and the mechanical facts are read from the links like OotrR does, AND
from the room logic modules (the downstream of the enemy's and its counter's outputs: shutters and shutter modules,
chests and the TreasureBoxAppear modules, other actors, flags read anywhere else), which OotrR doesn't read (the
Gerudo Training Ground's lattice doors and air walls, the meadow's gate counter). A door gets Presence "its own AND
every soul of the enemies whose defeat opens it", with no OotrR exception left, so every family of a room is gated.
An overworld enemy's effect has to name its OoTR check (a chest from data/rando/chest_map.json or the chests
plugin's locations, else OVERWORLD_EFFECTS), and that check needs its soul.
Left unbound, with why: an enemy that's part of an NPC (linked to one, like the Lost Woods target practice's scrub
leaf), one a scene not started by its defeat acts on (the Water Temple's water-rise scene pausing its three
Tektites, the Shell Blade a focus scene drops), and an overworld effect with no check named (none today).
The regional mode (OotrR's "regional") uses the same placements with one soul per map folder ("regions"). A
dungeon's boss takes its region's soul.

Each family with a soul has its item ("<Name> Soul"), the OoTR has_soul() tokens it answers (OoTR's logic and our
drops plugin call has_soul(<Token>)), its saved flag (a new Bool of our own, Rando_EnemySoul_<Key>, make_patch
add_bools), its placements (file, hash, the vanilla Presence if any) and its figure. The figure is a Hall of Fallen
Foes figure (Enemy_*_Dictionary, the variant most of its bound placements are), built by parity/_soul_figures.py
like the boss souls' are, and shown by the display Rando_Show_Soul<code> (config/hold_up.json).
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
OUT = os.path.join(HERE, "data", "rando", "extras_enemy_souls.json")
ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()

# key, name, OoTR has_soul tokens, Gyaml prefixes, display code (<= 10 chars, since actor names past 25 crash the
# item get, as OotrR found)
FAMILIES = [
    ("Stalfos", "Stalfos", ("Stalfos",), ("Enemy_Stalfos",), "Stalfos"),
    ("Octorok", "Octorok", ("Octorok",), ("Enemy_Octorok",), "Octorok"),
    ("BigOcto", "Big Octo", ("Big_Octo",), ("Enemy_MiddleBoss_BigOcto",), "BigOcto"),
    ("Wallmaster", "Wallmaster", ("Wallmaster",), ("Enemy_Wallmaster",), "Wallmstr"),
    ("Floormaster", "Floormaster", ("Floormaster",), ("Enemy_Floormaster",), "Floormstr"),
    ("Dodongo", "Dodongo", ("Dodongo",), ("Enemy_Dodongo",), "Dodongos"),  # (King Dodongo has SoulDodongo)
    ("BabyDodongo", "Baby Dodongo", ("Baby_Dodongo",), ("Enemy_BabyDodongo",), "BabyDodo"),
    ("Keese", "Keese", ("Keese",), ("Enemy_Keese",), "Keese"),
    ("Tektite", "Tektite", ("Tektite",), ("Enemy_Tektite",), "Tektite"),
    ("Peahat", "Peahat", ("Peahat",), ("Enemy_Peahat",), "Peahat"),
    ("Lizalfos", "Lizalfos and Dinolfos", ("Lizalfos_and_Dinalfos",),
     ("Enemy_Lizalfos", "Enemy_MiddleBoss_Lizalfos", "Enemy_Dinolfos"), "Lizalfos"),
    ("GohmaLarva", "Gohma Larva", ("Gohma_Larvae",), ("Enemy_Gohma_Larva", "Enemy_Gohma_Egg"), "GohmaLarv"),
    ("Shabom", "Shabom", ("Shabom",), ("Enemy_Shabom",), "Shabom"),
    ("BiriBari", "Biri and Bari", ("Biri_and_Bari",), ("Enemy_Biri", "Enemy_Bari"), "BiriBari"),
    ("Tailpasaran", "Tailpasaran", ("Tailpasaran",), ("Enemy_Tailpasaran",), "Tailpasa"),
    ("TorchSlug", "Torch Slug", ("Torch_Slug",), ("Enemy_TorchSlug",), "TorchSlug"),
    ("Skulltula", "Skulltula", ("Skulltula",), ("Enemy_Skulltula",), "Skulltula"),
    ("Skullwalltula", "Skullwalltula", ("Skullwalltula",), ("Enemy_Skullwalltula",), "Skwalltula"),
    ("Moblin", "Moblin", ("Moblin",), ("Enemy_Moblin",), "Moblin"),
    ("Armos", "Armos", ("Armos",), ("Enemy_Amos",), "Armos"),
    ("Beamos", "Beamos", ("Beamos",), ("Enemy_Beamos",), "Beamos"),
    ("DekuBaba", "Deku Baba", ("Deku_Baba",), ("Enemy_Dekubaba",), "DekuBaba"),
    ("DekuScrub", "Deku Scrub", ("Deku_Scrub",), ("Enemy_Scrub_Deku", "Enemy_Scrub_Mad"), "DekuScrub"),
    ("Bubble", "Bubble", ("Bubble",), ("Enemy_Bubble",), "Bubble"),
    ("ReDead", "ReDead and Gibdo", ("Redead_and_Gibdo",), ("Enemy_ReDead", "Enemy_Gibdo"), "ReDead"),
    ("DeadHand", "Dead Hand", ("Dead_Hand",), ("Enemy_DeadHand",), "DeadHand"),
    ("FlareDancer", "Flare Dancer", ("Flare_Dancer",), ("Enemy_MiddleBoss_FlareDancer",), "FlareDanc"),
    ("ShellBlade", "Shell Blade", ("Shell_Blade",), ("Enemy_ShellBlade",), "ShellBlad"),
    ("LikeLike", "Like Like", ("Like_Like",), ("Enemy_LikeLike",), "LikeLike"),
    ("Spike", "Spike", ("Spike",), ("Enemy_Spike",), "Spike"),
    ("Anubis", "Anubis", ("Anubis",), ("Enemy_Anubis",), "Anubis"),
    ("IronKnuckle", "Iron Knuckle", ("Iron_Knuckle",), ("Enemy_IronKnuckle",), "IronKnuck"),
    ("FlyingPot", "Flying Pot", ("Flying_Pot",), ("Enemy_FlyingPot",), "FlyingPot"),
    ("Freezard", "Freezard", ("Freezard",), ("Enemy_Freezard",), "Freezard"),
    ("Stinger", "Stinger", ("Stinger",), ("Enemy_Stinger",), "Stinger"),
    ("Wolfos", "Wolfos", ("Wolfos",), ("Enemy_Wolfos",), "Wolfos"),
    ("Guay", "Guay", ("Guay",), ("Enemy_Guay", "Enemy_FlockGuayManager"), "Guay"),
    ("JabuTentacle", "Jabu-Jabu Tentacle", ("Jabu_Tentacle",), ("Enemy_Tentacle",), "JabuTent"),
    ("DarkLink", "Dark Link", ("Dark_Link",), ("Enemy_MiddleBoss_DarkLink",), "DarkLink"),
]
EXCLUDED_MARKERS = ("_Dictionary", "Haribote", "ClimaxOnly", "GhostPicturePerformer", "Skulltula_Gold",
                    "Scrub_Business", "Scrub_ForestStage", "IronKnuckle_Nabooru", "SkullKid", "Poe",
                    "Stalchild", "Leever", "GerudoThief", "Ganon", "CrazyFloorTile", "TrickyDoor")
EXCLUDED_FOLDERS = ("DreamWorld", "GanonCastle")
ANCHORS = ("DestinationAnchor",)
# Banc folder -> OoTR dungeon (Region.dungeon). Entering it needs the souls of its mechanical enemies (OotrR's
# exit_requirements: "entering a dungeon requires the souls of every family patched in that dungeon" whose enemies
# drive something).
DUNGEONS = {"InsideTheDekuTree": "Deku Tree", "DodongoCavern": "Dodongos Cavern",
            "InsideJabuJabuBelly": "Jabu Jabus Belly", "ForestTemple": "Forest Temple", "FireTemple": "Fire Temple",
            "WaterTemple": "Water Temple", "ShadowTemple": "Shadow Temple", "SpiritTemple": "Spirit Temple",
            "BottomOfTheWell": "Bottom of the Well", "IceCavern": "Ice Cavern",
            "GerudoTrainingGround": "Gerudo Training Ground", "InsideGanonCastle": "Ganons Castle"}
# OotrR's mechanical facts (remake_world.enemy_mechanics). Links to these drive nothing, these parameters tie an
# enemy to a scripted sequence, and these families' defeat the dungeon always expects
# (soul_adapter.ALWAYS_MECHANICAL).
INERT_LINKS = ("DestinationAnchor", "StartPos", "MapIconOffsetAnchor", "AnchorAction",
               "FieldAndDungeonEntranceEventRequestActor")
MECHANIC_PARAMS = ("IsIntendedForEventAppear", "DefeatedOrder", "ShootOrder", "TalkEventName")
ALWAYS_MECHANICAL = ("BigOcto", "DarkLink", "FlareDancer", "JabuTentacle")
# What an enemy's AI outputs may reach without its defeat doing anything (sensors, anchors, looks, Navi's interest
# spots, the air wall pushing Link off a chest that appears). Ours, from the room modules.
INERT_TARGETS = INERT_LINKS + ("Area", "DungeonRoomArea", "DungeonRoomCenterAnchor", "PushAirWall", "InterestSpotActor",
                               "ForbidAutoPlacementAreaBox", "EftLoc_", "LocationalLight_", "NaviAnchor")
INERT_FLAG_PREFIXES = ("HaveReadHrlField_Note", "HavePlayedNaviBalloonMessage")  # a note read, a Navi hint shown
INERT_FLAG_MARKERS = ("_NaviHelp_",)
CHEST_PREFIX = "Obj_TBox_"
NPC_PREFIXES = ("NPC_", "Npc_")
# Overworld enemies whose defeat drives something that isn't a door or a chest, mapped to the OoTR exit or location
# that needs them by what their defeat sets. Checked against the game files when the data is built, and an unknown
# one stops the build.
OVERWORLD_EFFECTS = {
    # Sacred Forest Meadow, child: the Wolfos at the maze's gate (Gimmick_DefeatEnemy_Open_03, the room counter
    # Obj_EnemyCounter_A_08 and SacredForestMeadow_Gimmick_OpenShutter). The adult's meadow has no such Wolfos.
    "SacredForestMeadow/Obj_EnemyCounter_A_08": {"exit": ["SFM Entryway", "Sacred Forest Meadow"], "age": "child"},
    # Kokiri Forest's grotto (HidingHole_01). The Deku Scrub brothers' order puzzle (Scrub_Deku_Brothers_Manager, their
    # DefeatedOrder / ShootOrder / TalkEventName) makes the grotto's chest appear, KF Storms Grotto Chest
    # (chest_map: KokiriForest/chest/14818888396401495482).
    "KokiriForest/Scrub_Deku_Brothers_Manager": {"location": "KF Storms Grotto Chest"},
    "KokiriForest/param:DefeatedOrder": {"location": "KF Storms Grotto Chest"},
    "KokiriForest/param:ShootOrder": {"location": "KF Storms Grotto Chest"},
    "KokiriForest/param:TalkEventName": {"location": "KF Storms Grotto Chest"},
}


def family_of(gyaml):
    if any(m in gyaml for m in EXCLUDED_MARKERS):
        return None
    best = None
    for key, _n, _t, prefixes, _c in FAMILIES:
        for p in prefixes:
            if (gyaml == p or gyaml.startswith(p + "_")) and (best is None or len(p) > best[1]):
                best = (key, len(p))
    return best[0] if best else None


def _refs(groups, out):
    if isinstance(groups, dict):
        groups = list(groups.values())
    for g in groups or []:
        if isinstance(g, dict):
            out.update(str(h) for h in (g.get("refs") or {}).values())
            _refs(g.get("subs"), out)


def _groups(gs):
    if isinstance(gs, dict):
        gs = list(gs.values())
    for g in gs or []:
        if isinstance(g, dict):
            yield g
            yield from _groups(g.get("subs"))


def _presence(a):
    pr = a["presence"]
    return {"flag": pr["flag"], "neg": bool(pr.get("neg")), "lazy": bool(pr.get("lazy")), "type": pr.get("type") or "Bool"}


class Index:
    """The game-logic index (tools/gamedb) as the scan reads it: levels, logic modules, events, and where each flag is
    read (logic modules, events, placement Presence)."""

    def __init__(self, cache):
        self.levels = json.load(open(os.path.join(cache, "levels.json"), encoding="utf-8"))["by_file"]
        lg = json.load(open(os.path.join(cache, "logic.json"), encoding="utf-8"))
        self.modules = lg["by_file"]
        ev = json.load(open(os.path.join(cache, "events.json"), encoding="utf-8"))
        self.events, self.ev_summary = ev["by_file"], ev["summary"]
        self.flag_modules = collections.defaultdict(set)
        for rel, m in self.modules.items():
            for r in m.get("reads") or []:
                self.flag_modules[r.get("flag")].add(rel)
        self.flag_events = set((self.ev_summary.get("readers") or {}).keys())
        self.flag_presence = set()
        for f in self.levels.values():
            for a in (f.get("actors") or []) if isinstance(f, dict) else []:
                if a.get("presence"):
                    self.flag_presence.add(a["presence"]["flag"])

    def read_elsewhere(self, flag, module):
        return bool(self.flag_modules.get(flag, set()) - {module}) or flag in self.flag_events \
            or flag in self.flag_presence

    def event_entry(self, name):
        """(flowchart, entry) of EventSetting `name`, or (None, None)."""
        s = (self.ev_summary.get("settings") or {}).get(name)
        rel = (self.ev_summary.get("newest") or {}).get((s or {}).get("flow"))
        for fc in (self.events.get(rel) or {}).get("flowcharts", []) if s else []:
            if s.get("entry") in (fc.get("entries") or {}):
                return fc, fc["entries"][s["entry"]]
        return None, None


def _consumers(nodes):
    out = collections.defaultdict(list)
    for n in nodes:
        for k, v in (n.get("in") or {}).items():
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, dict) and "node" in x:
                    out[x["node"]].append((n["i"], k))
    return out


def _downstream(ix, module, starts):
    """What the outputs of nodes `starts` reach in room module `module`: [("actor", instance, input),
    ("module", instance, logic name), ("flag", name)]. Room counters and event requesters are passed through (their
    own outputs are the room's), as are operators and a flag the module writes and reads back itself."""
    mod = ix.modules.get(module)
    if mod is None:
        return [("nomodule", module, "")]
    nodes = {n["i"]: n for n in mod["nodes"]}
    cons = _consumers(mod["nodes"])
    readers = collections.defaultdict(list)
    for n in mod["nodes"]:
        if n["name"].startswith("HoldGameDataGet"):
            for k, v in (n.get("in") or {}).items():
                if k.startswith("GameDataName") and isinstance(v, str):
                    readers[v].append(n["i"])
    seen, todo, out = set(), list(starts), []
    while todo:
        i = todo.pop()
        for c, inp in cons.get(i, []):
            if (c, inp) in seen:
                continue
            seen.add((c, inp))
            n = nodes[c]
            name, inst = n["name"], (n.get("props") or {}).get("InstanceName")
            if name in ("ActorLogicEnemyCounter", "ActorLogicEventRequestActor") and inst:
                out.append(("actor", inst, inp))
                todo.append(c)
                continue
            if name.startswith("ActorLogic") and inst:
                out.append(("actor", inst, inp))
                continue
            if name.endswith(".logic.module") and not name.startswith("Operate"):
                out.append(("module", inst, name))
                continue
            if name.startswith("Trigger") and "GameData" in name:
                flag = next((v for k, v in (n.get("in") or {}).items() if k.startswith("GameDataName")
                             and isinstance(v, str)), None)
                if flag and ix.read_elsewhere(flag, module):
                    out.append(("flag", flag, ""))
                todo.extend(j for j in readers.get(flag, []) if j not in todo)
                continue
            if name.startswith("Trigger"):
                continue
            todo.append(c)
    return out


def _inert(gyaml):
    return gyaml.startswith(INERT_TARGETS) or gyaml.startswith("Enemy_")


def scan(cache):
    """{family: [placement]} of every enemy placement a soul gates, the unbound ones with why, the doors (room locks)
    and the mechanical facts. Each placement has:
    - file, hash, gyaml, folder, presence (vanilla, if any)
    - doors: the room locks its defeat opens (their door placements get the soul's Presence)
    - chests: remake chest ids that appear on its defeat
    - effects: anything else its defeat drives (actors, flags read elsewhere, modules)
    - mechanical (bool)"""
    ix = Index(cache)
    bound, unbound = collections.defaultdict(list), collections.defaultdict(list)
    doors = {}
    for rel, f in sorted(ix.levels.items()):
        if not isinstance(f, dict) or "actors" not in f:
            continue
        folder = rel.split("/")[1] if rel.startswith("Banc/") else None
        if folder is None or folder in EXCLUDED_FOLDERS:
            continue
        acts = f["actors"]
        byh = {str(a["hash"]): a for a in acts}
        incoming = collections.defaultdict(list)
        for a in acts:
            for l in a.get("links") or []:
                incoming[str(l.get("dst"))].append(a)

        def nb(a):
            return [byh[str(l.get("dst"))] for l in a.get("links") or [] if str(l.get("dst")) in byh] + \
                incoming[str(a["hash"])]

        def is_door(a):
            return a.get("gyaml", "").startswith("Obj_") and "Shutter" in a.get("gyaml", "")

        groups = list(_groups(f.get("ai_groups")))
        by_inst = collections.defaultdict(list)  # placement hash -> [(group, instance name)]
        for g in groups:
            for k, v in (g.get("refs") or {}).items():
                by_inst[str(v)].append((g, k))

        def ai_effects(h):
            """Effects of placement h's node(s) in every room module naming it, mapped back to placements."""
            out = []
            for g, k in by_inst.get(h, []):
                mod = ix.modules.get(g.get("logic") or "")
                if mod is None:
                    continue
                starts = [n["i"] for n in mod["nodes"] if (n.get("props") or {}).get("InstanceName") == k]
                refs = g.get("refs") or {}
                subs = {s.get("instance"): key.split("/")[0] for key, s in (g.get("subs") or {}).items()}
                for kind, inst, extra in _downstream(ix, g.get("logic"), starts):
                    if kind == "actor":
                        tgt = str(refs.get(inst))
                        out.append(("actor", tgt, byh.get(tgt, {}).get("gyaml", "?"), extra))
                    elif kind == "module":
                        pre = subs.get(inst)
                        own = [str(v) for kk, v in refs.items() if pre and kk.startswith(pre + "/")]
                        if "TreasureBoxAppear" in extra:  # its chest: the room's own chest(s)
                            own += [str(v) for kk, v in refs.items() if "/" not in kk
                                    and byh.get(str(v), {}).get("gyaml", "").startswith(CHEST_PREFIX)]
                        out.append(("module", extra, own))
                    else:
                        out.append((kind, inst, extra))
            return out

        for a in acts:
            fam = family_of(a.get("gyaml", ""))
            if not fam:
                continue
            h = str(a["hash"])
            p = {"file": rel, "hash": h, "gyaml": a["gyaml"], "folder": folder}
            if a.get("presence"):
                p["presence"] = _presence(a)
            if any(o.get("gyaml", "").startswith(NPC_PREFIXES) for o in nb(a)):
                unbound[fam].append(dict(p, why="part of an NPC (linked to one)"))
                continue
            lock_doors, chests, effects = set(), set(), set()
            # OotrR's room locks. A counter linking it and the shutters linking to that counter or around its event
            # requester, or a shutter linked to or from the enemy itself.
            counters = [c for c in incoming[h] if c.get("gyaml", "").startswith("Obj_EnemyCounter")]
            for c in counters:
                ds = [x for x in incoming[str(c["hash"])] if is_door(x)]
                for ev in incoming[str(c["hash"])]:
                    if ev.get("gyaml") == "EventRequestActor":
                        ds += [x for x in nb(ev) if is_door(x)]
                lock_doors |= {str(d["hash"]) for d in ds}
            lock_doors |= {str(d["hash"]) for d in nb(a) if is_door(d)}
            # OotrR's mechanical facts (links, parameters)
            dyn = a.get("dyn") or {}
            effects |= {"param:" + k for k in MECHANIC_PARAMS if dyn.get(k) not in (None, False, "")}
            if fam in ALWAYS_MECHANICAL:
                effects.add("always:" + fam)
            # A requester only counts if the enemy's defeat or its room counter starts it. The Lake Hylia arrival scene
            # names two Hyrule Field Tektites, but arriving is what starts it, so that link doesn't count.
            starts = {e[1] for src in [h] + [str(c["hash"]) for c in counters] for e in ai_effects(src)
                      if e[0] == "actor"}
            for o in nb(a):
                g2 = o.get("gyaml", "")
                if g2 == "EventRequestActor" and str(o["hash"]) not in starts and not counters:
                    continue
                if g2 == "EventRequestActor" or g2.startswith("Obj_EnemyCounter"):
                    hops = [o] + ([x for x in incoming[str(o["hash"])] if x.get("gyaml") == "EventRequestActor"]
                                  if g2.startswith("Obj_EnemyCounter") else [])
                    for hop in hops:
                        for x in nb(hop):
                            gx = x.get("gyaml", "")
                            if gx.startswith(CHEST_PREFIX):
                                chests.add(str(x["hash"]))
                            elif not (gx.startswith("Enemy_") or "Shutter" in gx or gx.startswith(INERT_TARGETS)
                                      or gx == "EventRequestActor" or gx.startswith("Obj_EnemyCounter")):
                                effects.add(gx)
                elif g2.startswith(CHEST_PREFIX):
                    chests.add(str(o["hash"]))
                elif not (g2.startswith("Enemy_") or "Shutter" in g2 or g2.startswith(INERT_TARGETS)):
                    effects.add(g2)
            # We trace the room module from the enemy and its counters. A counter can block the route by itself even
            # when we found no actor it drives, like the gate counter in Sacred Forest Meadow.
            triggered = set()
            for c in counters:
                cd = {str(x["hash"]) for x in incoming[str(c["hash"])] if is_door(x)}
                for ev in incoming[str(c["hash"])]:
                    if ev.get("gyaml") == "EventRequestActor":
                        cd |= {str(x["hash"]) for x in nb(ev) if is_door(x)}
                ce = [e for e in ai_effects(str(c["hash"])) if e[0] != "actor" or not (
                    e[2] in ("EventRequestActor",) or e[2].startswith("Obj_EnemyCounter") or _inert(e[2]))]
                if not cd and not ce:
                    effects.add(f"counter:{folder}/{c['gyaml']}")
            for src in [h] + [str(c["hash"]) for c in counters]:
                for e in ai_effects(src):
                    if e[0] == "actor":
                        tgt, gy = e[1], e[2]
                        if gy == "EventRequestActor" or gy.startswith("Obj_EnemyCounter"):
                            triggered.add(tgt)
                        elif is_door(byh.get(tgt, {})):
                            lock_doors.add(tgt)
                        elif gy.startswith(CHEST_PREFIX):
                            chests.add(tgt)
                        elif not _inert(gy):
                            effects.add(gy)
                    elif e[0] == "module":
                        own = e[2]
                        ds = [x for x in own if is_door(byh.get(x, {}))]
                        cs = [x for x in own if byh.get(x, {}).get("gyaml", "").startswith(CHEST_PREFIX)]
                        lock_doors |= set(ds)
                        chests |= set(cs)
                        if not ds and not cs:
                            effects.add("module:" + e[1].split("_")[0] + "_" + e[1].split("_")[1])
                    elif e[0] == "flag":
                        if not (e[1].startswith(INERT_FLAG_PREFIXES) or any(m in e[1] for m in INERT_FLAG_MARKERS)):
                            effects.add("flag:" + e[1])
                    else:
                        effects.add(f"{e[0]}:{e[1]}")
            # An enemy stays unbound if a scene it doesn't start still acts on it, or the scene could end up waiting
            # for an actor that's missing.
            acted = None
            for o in nb(a):
                if o.get("gyaml") != "EventRequestActor" or str(o["hash"]) in triggered:
                    continue
                fc, ep = ix.event_entry((o.get("dyn") or {}).get("RequestEventName"))
                if fc is None:
                    continue
                evs = {e["name"]: e for e in fc["events"]}
                if any((evs.get(n) or {}).get("call", "").startswith(a["gyaml"] + ".") for n in ep.get("reach", [])):
                    acted = (o.get("dyn") or {}).get("RequestEventName")
            if acted:
                unbound[fam].append(dict(p, why=f"its scene {acted} (not started by its defeat) acts on it"))
                continue
            for d in lock_doors:
                door = byh[d]
                rec = doors.setdefault((rel, d), {"file": rel, "hash": d, "gyaml": door["gyaml"], "folder": folder,
                                                  "families": set()})
                if door.get("presence"):
                    rec["presence"] = _presence(door)
                rec["families"].add(fam)
            p.update({"doors": sorted(lock_doors), "chests": sorted(chests), "effects": sorted(effects),
                      "mechanical": bool(chests or effects)})
            if counters:
                p["counters"] = sorted(f"{folder}/{c['gyaml']}" for c in counters)
            bound[fam].append(p)
    for rec in doors.values():
        rec["families"] = sorted(rec["families"])
    return bound, unbound, [doors[k] for k in sorted(doors)]


def figures(bound, romfs):
    """{family: (museum actor, model project, FmdbName)} for the families with a soul."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    rows = {}
    for r in byml_load(fs.read("RSDB/ActorInfo.Product.111.rstbl.byml.zs"), allow_big=True)[0]:
        if isinstance(r, dict) and r.get("__RowId"):
            rows[r["__RowId"]] = r
    out = {}
    for fam, places in bound.items():
        prefixes = next(f[3] for f in FAMILIES if f[0] == fam)
        common = collections.Counter(p["gyaml"] for p in places).most_common()
        pick = prefixes[0] + "_Dictionary" if rows.get(prefixes[0] + "_Dictionary", {}).get("FmdbName") else None
        for g, _n in ([] if pick else common):  # the bound variant's own figure, else its base's (Enemy_Tektite_Red_01 -> _Tektite_Red)
            parts = g.split("_")
            for k in range(len(parts), 1, -1):
                cand = "_".join(parts[:k]) + "_Dictionary"
                if cand in rows and rows[cand].get("FmdbName"):
                    pick = cand
                    break
            if pick:
                break
        if pick is None:
            for p in prefixes:
                if p + "_Dictionary" in rows:
                    pick = p + "_Dictionary"
                    break
        if pick is None:  # no museum figure (Jabu-Jabu's tentacles): the enemy's own actor, its own colour anim and
            # rest pose (_soul_figures.museum reads any actor's ActorInfo / GameActorInfo rows)
            for g, _n in sorted(common, key=lambda x: (x[0] != prefixes[0] + "_Red", x[0])):
                if rows.get(g, {}).get("FmdbName"):
                    pick = g
                    break
        if pick is None:
            raise SystemExit(f"{fam}: no Hall of Fallen Foes figure for {[g for g, _ in common]}")
        r = rows[pick]
        out[fam] = (pick, r["ModelProjectName"], r["FmdbName"])
    return out


def figure_name(fmdb, code, taken):
    """The figure's FmdbName, which is the source's with its first word replaced at the same length (Enemy_ -> Rando_,
    Npc_ -> Rnd_). A source two souls share, like the Floormaster's for the Wallmaster, gets the family's code
    letters instead."""
    word = fmdb.split("_")[0]
    cands = [("Rando" if len(word) == 5 else "Rnd" if len(word) == 3 else ("Rnd" + code)[:len(word)]) + fmdb[len(word):],
             ("Rnd" + code)[:len(word)] + fmdb[len(word):]]
    for c in cands:
        if c not in taken and len(c) == len(fmdb):
            return c
    raise SystemExit(f"{fmdb}: no free figure name for {code}")


# Banc folder -> (region soul's name, the message's words, short code). The name uses OotrR's English region names
# with no apostrophes in item names. The short code keeps an actor name within 25 characters, as OotrR found.
REGIONS = {
    "InsideTheDekuTree": ("Deku Tree", "Deku Tree", "DekuTree"),
    "DodongoCavern": ("Dodongos Cavern", "Dodongo's Cavern", "DodongoCv"),
    "InsideJabuJabuBelly": ("Jabu Jabus Belly", "Jabu-Jabu's Belly", "JabuJabu"),
    "ForestTemple": ("Forest Temple", "Forest Temple", "ForestTmp"),
    "FireTemple": ("Fire Temple", "Fire Temple", "FireTmp"),
    "WaterTemple": ("Water Temple", "Water Temple", "WaterTmp"),
    "ShadowTemple": ("Shadow Temple", "Shadow Temple", "ShadowTmp"),
    "SpiritTemple": ("Spirit Temple", "Spirit Temple", "SpiritTmp"),
    "BottomOfTheWell": ("Bottom of the Well", "Bottom of the Well", "Well"),
    "IceCavern": ("Ice Cavern", "Ice Cavern", "IceCavern"),
    "GerudoTrainingGround": ("Gerudo Training Ground", "Gerudo Training Ground", "GTG"),
    "InsideGanonCastle": ("Ganons Castle", "Ganon's Castle", "GanonCast"),
    "KokiriForest": ("Kokiri Forest", "Kokiri Forest", "Kokiri"),
    "LostWood": ("Lost Woods", "Lost Woods", "LostWoods"),
    "SacredForestMeadow": ("Sacred Forest Meadow", "Sacred Forest Meadow", "SFMeadow"),
    "HyruleField": ("Hyrule Field", "Hyrule Field", "HField"),
    "Market": ("Market", "Market", "Market"),
    "HyruleCastle": ("Hyrule Castle", "Hyrule Castle", "HCastle"),
    "KakarikoVillage": ("Kakariko Village", "Kakariko Village", "Kakariko"),
    "Graveyard": ("Graveyard", "Graveyard", "Graveyard"),
    "DeathMountainTrail": ("Death Mountain Trail", "Death Mountain Trail", "DMTrail"),
    "DeathMountainCrater": ("Death Mountain Crater", "Death Mountain Crater", "DMCrater"),
    "GoronCity": ("Goron City", "Goron City", "GoronCity"),
    "ZoraRiver": ("Zoras River", "Zora's River", "ZRiver"),
    "ZoraDomain": ("Zoras Domain", "Zora's Domain", "ZDomain"),
    "ZoraFountain": ("Zoras Fountain", "Zora's Fountain", "ZFountain"),
    "LakeHylia": ("Lake Hylia", "Lake Hylia", "LakeHylia"),
    "LonLonRanch": ("Lon Lon Ranch", "Lon Lon Ranch", "LLRanch"),
    "GerudoValley": ("Gerudo Valley", "Gerudo Valley", "GValley"),
    "GerudoFortress": ("Gerudo Fortress", "Gerudo Fortress", "GFortress"),
    "HountedWasteland": ("Haunted Wasteland", "Haunted Wasteland", "Wasteland"),
    "DesertColossus": ("Desert Colossus", "Desert Colossus", "Colossus"),
}
# a dungeon's region soul shows its boss's figure (extras_souls_data bosses: the boss's dungeon folder)
BOSS_OF = {"InsideTheDekuTree": "gohma", "DodongoCavern": "king_dodongo", "InsideJabuJabuBelly": "barinade",
           "ForestTemple": "phantom_ganon", "FireTemple": "volvagia", "WaterTemple": "morpha",
           "ShadowTemple": "bongo_bongo", "SpiritTemple": "twinrova"}


def overworld(bound, unbound):
    """Each overworld placement whose defeat drives something gets the OoTR check that needs it. That's a chest that
    appears (its OoTR location from data/rando/chest_map.json) or a known effect (OVERWORLD_EFFECTS). One with an
    effect we can't name a check for is left unbound, so it's never a lockout. Returns [{"location" | "exit", "age"?,
    "families", "folders"}]. Dungeon placements need nothing here, since entering the dungeon asks for their souls."""
    cm = json.load(open(os.path.join(HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"]
    chest_loc = collections.defaultdict(list)
    for loc, v in cm.items():
        if isinstance(v, dict) and v.get("remake"):
            chest_loc[v["remake"]].append(loc)
    # the chests plugin's own OoTR locations, the remake-only chests (data/rando/chests_locations.json "new"), with
    # their "also" chests (the same chest in another layout, the other outcome of one puzzle)
    cl = json.load(open(os.path.join(HERE, "data", "rando", "chests_locations.json"), encoding="utf-8"))
    for sec in ("new", "paired"):
        for loc, v in (cl.get(sec) or {}).items():
            if isinstance(v, dict):
                for rid in [v.get("remake")] + list(v.get("also") or []):
                    if isinstance(rid, str) and loc not in chest_loc[rid]:
                        chest_loc[rid].append(loc)
    rules = {}
    for fam in list(bound):
        keep = []
        for p in bound[fam]:
            if p["folder"] in DUNGEONS or not p.get("mechanical"):
                keep.append(p)
                continue
            targets, unknown = [], []
            for c in p["chests"]:
                locs = chest_loc.get(f"{p['folder']}/chest/{c}")
                (targets.extend({"location": l} for l in locs) if locs else unknown.append(f"chest {c}"))
            for e in p["effects"]:
                hit = OVERWORLD_EFFECTS.get(e.split(":", 1)[1] if e.startswith("counter:") else f"{p['folder']}/{e}")
                (targets.append(dict(hit)) if hit else unknown.append(e))
            if unknown:
                unbound[fam].append(dict(p, why=f"overworld effect with no OoTR check named for it: {unknown}"))
                continue
            p["checks"] = [t.get("location") or " -> ".join(t["exit"]) for t in targets]
            for t in targets:
                k = json.dumps(t, sort_keys=True)
                r = rules.setdefault(k, dict(t, families=set(), folders=set()))
                r["families"].add(fam)
                r["folders"].add(p["folder"])
            keep.append(p)
        bound[fam] = keep
    return [dict(r, families=sorted(r["families"]), folders=sorted(r["folders"])) for _, r in sorted(rules.items())]


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "cache", "gamedb", "vanilla")
    if cache.endswith(".json"):
        cache = os.path.dirname(cache)
    romfs = sys.argv[2] if len(sys.argv) > 2 else ROMFS
    bound, unbound, doors = scan(cache)
    rules = overworld(bound, unbound)
    figs = figures(bound, romfs)
    # a family that had a soul keeps its figure's name (the displays and built seeds name it); new ones take the rest
    old = {}
    if os.path.exists(OUT):
        for k, e in json.load(open(OUT, encoding="utf-8")).get("families", {}).items():
            if e.get("figure"):
                old[k] = (e["figure"]["fmdb"], e["figure"]["figure_fmdb"])
    fams, taken = {}, {f for _, f in old.values()}
    for key, name, tokens, prefixes, code in FAMILIES:
        e = {"name": name, "tokens": list(tokens), "prefixes": list(prefixes), "left": len(unbound.get(key, [])),
             "unbound": unbound.get(key, [])}
        if bound.get(key):
            actor, project, fmdb = figs[key]
            fig = old[key][1] if old.get(key, (None,))[0] == fmdb else figure_name(fmdb, code, taken)
            taken.add(fig)
            display = "Rando_Show_Soul" + code
            if len(display) > 25 or len(fig) != len(fmdb):
                raise SystemExit(f"{key}: display {display} or figure {fig} not usable")
            ps = bound[key]
            e.update({"item": f"{name} Soul", "flag": f"Rando_EnemySoul_{key}", "display": display,
                      "figure": {"actor": actor, "project": project, "fmdb": fmdb, "figure_fmdb": fig},
                      "placements": ps,
                      "dungeons": sorted({p["folder"] for p in ps if p["folder"] in DUNGEONS and p["mechanical"]})})
        fams[key] = e
    # the regional mode (OotrR's "regional": one soul per map folder): the same placements, by folder
    by_folder = collections.defaultdict(list)
    for key, e in fams.items():
        for p in e.get("placements", []):
            by_folder[p["folder"]].append(dict(p, family=key))
    regions = {}
    for folder, ps in sorted(by_folder.items()):
        if folder not in REGIONS:
            raise SystemExit(f"{folder}: no region name (REGIONS)")
        name, words, code = REGIONS[folder]
        rep = BOSS_OF.get(folder)
        if rep is None:  # the region's most common enemy that has a figure
            n = collections.Counter(p["family"] for p in ps)
            rep = "enemy_" + min(n, key=lambda k: (-n[k], k))
        display = "Rando_Show_SoulR" + code
        if len(display) > 25:
            raise SystemExit(f"{folder}: display {display} is over 25 characters")
        regions[folder] = {"name": f"{name} Soul", "words": words, "code": code, "item": f"{name} Soul",
                           "flag": f"Rando_EnemySoul_R_{code}", "display": display, "figure_of": rep,
                           "dungeon": DUNGEONS.get(folder), "boss": BOSS_OF.get(folder),
                           "mechanical": folder in DUNGEONS and any(p["mechanical"] for p in ps)}
    data = {"_about": __doc__.strip().splitlines()[0] + " Built by tools/rando/parity/_enemy_souls_build.py.",
            "families": fams, "doors": doors, "overworld": rules, "regions": regions, "dungeons": DUNGEONS}
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    n = sum(len(e.get("placements", [])) for e in fams.values())
    print(f"{sum(1 for e in fams.values() if e.get('item'))} souls ({len(regions)} regions); {n} placements take "
          f"one; {sum(len(v) for v in unbound.values())} left unbound; {len(doors)} doors; {len(rules)} overworld "
          f"checks; written {OUT}")
    for fam, us in sorted(unbound.items()):
        for u in us:
            print(f"  unbound {fam} {u['file'].split('/', 1)[1]} {u['hash']}: {u['why']}")
    for r in rules:
        print(f"  overworld {r.get('location') or r.get('exit')}: {r['families']}")


if __name__ == "__main__":
    main()
