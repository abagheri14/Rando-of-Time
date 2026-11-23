"""Drop settings, owned by the story plugin.

gold_skulls_ignore_daytime
In OoTR the night-only Gold Skulltulas stay out during the day, and the logic follows: Overworld.json reads
"(at_night or gold_skulls_ignore_daytime)" 32 times, and our logic is OoTR's. In the remake the night-only
Skulltulas are the Enemy_Skulltula_Gold placements with the instance parameter Enemy_Skulltula_Gold_Nocturnal = True
(29 in the overworld levels, child and adult layouts). The Skulltula's utility AI (QueryTimeDivision -> IsDayTime /
IsNightTime) hides those by day, so the parameter goes to False on each of them. The list is
data/rando/gaps_night_gs.json (python tools/rando/parity/_gaps_drops.py build ROMFS).
That alone isn't enough (OotrR PR #7/#54, in game). Each of them (30 AI groups) runs the shared logic module
Gimmick_Nighttime_Skulltula_Gold_Appear_05a9. Its node 0 (ActorLogicEnemySkulltulaGold) has Logic_Delete fed by
node 2 (OperateOR over the day/night nodes, HoldWmGetTimeDiv), so by day the module deletes the Skulltula. With the
setting on, that input becomes unconnected (DAY_DELETE). The AINB input entry gets the source and flags an
unconnected input reads, -1/0 and 0x1800000, which is the same thing story.py's return_to_youth does to the adult
pedestal. Then the module never deletes it.

fix_broken_drops
In OoTR the Spirit Temple child Anubis room pot drops its Deku Shield, which the N64 game never shows, and logic may
count it ("Deku Shield Pot": fix_broken_drops). The Gerudo Training Ground eye statue's magic jar also always
refills. The pot OoTR calls "Spirit Temple Child Anubis Pot 4" is SpiritTemple_Static #17832064472493387916 by the
drop_map pairing, an Obj_Pot_A_05 with no drop of its own. Whenever the pot isn't a shuffled location it drops the
game's Deku Shield pickup (Dynamic.Drop__DropActor = Obj_Shield_Deku, a pickup type the drops plugin already uses).
When it is shuffled, OoTR's vanilla item there is a Deku Shield anyway and the drops plugin places what the fill gave
it. The remake has no magic jar on the eye statue (no Obj_Magic* placement in the Gerudo Training Ground's levels,
and build() records that check), so that half has nothing to fix."""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DATA = os.path.join(HERE, "data", "rando", "gaps_night_gs.json")
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
NOCTURNAL = "Enemy_Skulltula_Gold_Nocturnal"
SHIELD_POT = ("Spirit Temple Child Anubis Pot 4", "Banc/SpiritTemple/SpiritTemple_Static.bcett.byml.zs",
              "17832064472493387916", "Obj_Pot_A_05")
SHIELD = "Obj_Shield_Deku"
# Disconnect node 0's Logic_Delete input in the uncompressed AINB. The source goes from node 2/output 1 to
# node -1/output 0 (0xFFFF), with flags 0x1800000. The binary patch checks both old words first.
DAY_DELETE_FILE = "Logic/Gimmick_Nighttime_Skulltula_Gold_Appear_05a9.logic.module.ainb"
DAY_DELETE = [(0x97C, 0xFFFF, 0x10002), (0x980, 0x1800000, 0)]  # (offset, new, old)


def build(romfs=DEFAULT_ROMFS):
    """Scans every level for night-only Gold Skulltulas and the GTG magic jar, then writes DATA."""
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    night, jars = [], []
    base = os.path.join(romfs, "Banc")
    for d in sorted(os.listdir(base)):
        if not os.path.isdir(os.path.join(base, d)):
            continue
        for f in sorted(os.listdir(os.path.join(base, d))):
            if not f.endswith(".bcett.byml.zs"):
                continue
            rel = f"Banc/{d}/{f}"
            try:
                actors = byml_load(fs.read(rel), allow_big=True)[0].get("Actors") or []
            except Exception:  # noqa: BLE001 - not a placement file
                continue
            for a in actors:
                dyn = a.get("Dynamic") or {}
                if a.get("Gyaml") == "Enemy_Skulltula_Gold" and dyn.get(NOCTURNAL) is True:
                    night.append({"file": rel, "hash": str(a["Hash"]), "pos": [round(x, 2) for x in a["Translate"]]})
                if d == "GerudoTrainingGround" and "Magic" in a.get("Gyaml", ""):
                    jars.append({"file": rel, "hash": str(a["Hash"]), "actor": a["Gyaml"]})
    out = {"_about": "Night-only Gold Skulltulas (Enemy_Skulltula_Gold_Nocturnal True) and magic-jar placements in the "
                     "Gerudo Training Ground, read from the game by tools/rando/parity/_gaps_drops.py build",
           "night_gs": night, "gtg_magic": jars}
    with open(DATA, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    return out


def _data():
    return json.load(open(DATA, encoding="utf-8"))


def world_plan(settings, world):
    ws = getattr(world, "settings", settings)
    placements, gaps, binary = [], {}, []
    if getattr(ws, "gold_skulls_ignore_daytime", False):
        gs = _data()["night_gs"]
        placements += [{"file": g["file"], "hash": g["hash"], "set": {f"Dynamic.{NOCTURNAL}": False}} for g in gs]
        gaps["night_gs"] = [[g["file"], g["hash"]] for g in gs]
        binary += [{"file": DAY_DELETE_FILE, "offset": off, "i32": new, "expect": old,
                    "note": "gold_skulls_ignore_daytime: the night Skulltulas' day delete unconnected"}
                   for off, new, old in DAY_DELETE]
        gaps["day_delete"] = DAY_DELETE_FILE
    if getattr(ws, "fix_broken_drops", False) and getattr(ws, "shuffle_pots", "off") not in ("dungeons", "all"):
        name, f, h, _ = SHIELD_POT
        placements.append({"file": f, "hash": h, "set": {"Dynamic.Drop__DropActor": SHIELD}})
        gaps["shield_pot"] = [f, h]
    out = {}
    if placements:
        out = {"placements": placements, "_gaps": {"drops": gaps}}
    if binary:
        out["binary"] = binary
    return out


def verify(patch, note, romfs):
    from romtools import Romfs, byml_load
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    levels, bad = {}, []

    def actor(f, h):
        if f not in levels:
            levels[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f), allow_big=True)[0].get("Actors") or []}
        return levels[f].get(h)
    for f, h in note.get("night_gs", []):
        a = actor(f, h)
        if a is None or a.get("Gyaml") != "Enemy_Skulltula_Gold" or (a.get("Dynamic") or {}).get(NOCTURNAL) is not False:
            bad.append(f"{f} #{h}: Gold Skulltula still night-only ({a and (a.get('Dynamic') or {}).get(NOCTURNAL)})")
    if "night_gs" in note:
        want = {(g["file"], g["hash"]) for g in _data()["night_gs"]}
        if {tuple(x) for x in note["night_gs"]} != want:
            bad.append("night Skulltulas: the plan doesn't cover every one of data/rando/gaps_night_gs.json")
    if note.get("day_delete"):  # node 0's Logic_Delete unconnected in the patched module
        import struct
        from ainb import Ainb
        data = fs.raw(note["day_delete"])
        n0 = Ainb(data).nodes[0]
        inp = next((i for i in n0["inputs"].get("bool", []) if i["name"] == "Logic_Delete"), None)
        if n0["name"] != "ActorLogicEnemySkulltulaGold" or inp is None or inp["node"] != -1 or \
                [struct.unpack_from("<I", data, off)[0] for off, _n, _o in DAY_DELETE] != [n for _o, n, _x in DAY_DELETE]:
            bad.append(f"{note['day_delete']}: node 0's Logic_Delete is still connected ({inp and inp['node']})")
    if note.get("shield_pot"):
        f, h = note["shield_pot"]
        a = actor(f, h)
        if a is None or a.get("Gyaml") != SHIELD_POT[3] or (a.get("Dynamic") or {}).get("Drop__DropActor") != SHIELD:
            bad.append(f"{f} #{h}: the Anubis room pot doesn't drop {SHIELD}")
    return bad


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        o = build(*(sys.argv[2:3] or [DEFAULT_ROMFS]))
        print(f"{len(o['night_gs'])} night-only Gold Skulltulas, {len(o['gtg_magic'])} GTG magic placements -> {DATA}")
    else:
        sys.exit(__doc__)
