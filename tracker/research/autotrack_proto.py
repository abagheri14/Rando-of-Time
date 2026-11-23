"""Prototype auto-tracker: what the running game exposes without touching it.

1. The save (tracker/research/savefile.py): every check placement whose Bool64bitKey flag is set (chests opened, pots
   and rocks broken, Gold Skulltula tokens taken, freestanding items picked up), plus IsGet.<actor> item flags.
2. Longshot's log (builds/rc/logs/longshot_log.txt): the current level and age ("map: KokiriForest_Child (child)"),
   and the Discord status line (hearts, Gold Skulltula count, a heart counter), live.

Run:  python tracker/research/autotrack_proto.py [progress.sav] [--watch]
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import savefile  # noqa: E402

LOG = "E:/LongshotLauncher-data/builds/rc/logs/longshot_log.txt"
MAP_RE = re.compile(r"\] map: (\S+) \((child|adult)\)")
STATUS_RE = re.compile(r"discord: the status: (.*?) / \S+ ([\d.]+)/(\d+) · \S+ (\d+) · \S+ (\d+)")
PROBE_RE = re.compile(r"cheats: inventory probe: (.*)")
ITEMS = ["Item_Ocarina_Fairy", "Item_Ocarina_Time", "Weapon_Range_SlingShot", "Weapon_Range_Bow", "Item_Boomerang",
         "Item_Hookshot", "Item_Longshot", "Item_Bomb", "Item_Bombchu", "Item_Hammer", "Item_GlassTruth",
         "Item_DinFire", "Item_FaroreWind", "Item_NayruLove", "Item_Arrow_Fire", "Item_Arrow_Ice", "Item_Arrow_Light",
         "Item_Bottle", "Item_MagicBean", "Item_Sword_Kokiri", "Weapon_Sword_Master", "Item_Sword_Biggoron",
         "Weapon_Shield_Deku", "Weapon_Shield_Hylian", "Item_Shield_Mirror", "Armor_Adult_Goron", "Armor_Adult_Zora",
         "Item_HeavyBoot", "Item_HoverBoot", "Item_Gauntlet_Goron", "Item_Gauntlet_Silver",
         "Armor_Adult_Gauntlet_Gold", "Item_Scale_Silver", "Item_Scale_Gold", "Item_Wallet_Medium",
         "Item_Wallet_Large", "Item_BombBag_Small", "Item_Quiver_Small", "Item_BulletBag_Small", "Item_AgonyStone",
         "Item_Token_Gerudo", "Item_Token_Gold", "Item_Stone_Forest", "Item_Stone_Fire", "Item_Stone_Water",
         "Item_Medal_Forest", "Item_Medal_Fire", "Item_Medal_Water", "Item_Medal_Shadow", "Item_Medal_Spirit",
         "Item_Medal_Light", "Item_Melody_ZeldaLullaby", "Item_Melody_EponaSong", "Item_Melody_SariaSong",
         "Item_Melody_SunSong", "Item_Melody_TimeSong", "Item_Melody_StormSong", "Item_Melody_ForestMinuet",
         "Item_Melody_FireBolero", "Item_Melody_WaterSerenade", "Item_Melody_ShadowNocturne",
         "Item_Melody_SpiritRequiem", "Item_Melody_LightPrelude"]


def log_state(path=LOG, tail_bytes=4_000_000):
    """{level, age, area_label, hearts, max_hearts, gs, heart_counter, probe} from the end of Longshot's log."""
    st = {}
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - tail_bytes))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return st
    for line in text.splitlines():
        m = MAP_RE.search(line)
        if m:
            st["level"], st["age"] = m.group(1), m.group(2)
        m = STATUS_RE.search(line)
        if m:
            st.update(area_label=m.group(1), hearts=float(m.group(2)), max_hearts=int(m.group(3)),
                      gs=int(m.group(4)), heart_counter=int(m.group(5)))
        m = PROBE_RE.search(line)
        if m:
            for kv in m.group(1).split():
                k, _, v = kv.partition("=")
                st.setdefault("probe", {})[k] = int(v) if v.lstrip("-").isdigit() else v
    return st


def save_state(path, checks):
    s = savefile.load(path)
    done = [c for c in checks if s.placement_done(int(c["hash"]))]
    items = {n: s.bool("IsGet." + n) for n in ITEMS}
    return s, done, items


def main(argv):
    checks = json.load(open(os.path.join(HERE, "checks_proto.json"), encoding="utf-8"))
    paths = [a for a in argv if a.endswith(".sav")]
    path = paths[0] if paths else savefile.slots()[0][0]
    while True:
        s, done, items = save_state(path, checks)
        st = log_state()
        print(time.strftime("%H:%M:%S"), path)
        print("  log:", {k: v for k, v in st.items() if k != "probe"})
        print(f"  save: {len(s.bool64)} placement flags set; {len(done)} of {len(checks)} known check placements done")
        by = {}
        for c in done:
            by.setdefault(c["texture"] or c["level"], []).append(f"{c['kind']}: {c['loc']}")
        for k, v in sorted(by.items()):
            print(f"    {k}: {len(v)}  e.g. {v[:3]}")
        print("  IsGet:", sorted(k for k, v in items.items() if v))
        if "--watch" not in argv:
            break
        time.sleep(2)


if __name__ == "__main__":
    main(sys.argv[1:])
