"""Map metadata for the tracker research: which texture belongs to which level, the capture camera of each map, the
game's own map icon tables (MapParam), and the world -> map-pixel projection.

Sources (all read as vanilla through romtools.Romfs):
  Game/MapMenuInfo/MapMenuInfo.game__ui__MapMenuInfo.bgyml       31 map areas: LocationName, BancName[child, adult],
                                                                 TextureName[child, adult, ""]
  Game/MapCaptureInfo/MapCaptureInfo.game__MapCaptureInfo.bgyml  36 capture cameras; entry i belongs to MapMenuInfo
                                                                 entry i (i < 31): CameraPos {X,Y,Z}, Height, per-floor
                                                                 Near/Far clip planes, IsDungeon
  Banc/BancBasedResource/MapParam.byml.zs                        per level: the map's own icons (TBox, CollectSign,
                                                                 CollectHeart, Door, Facility, EntranceAnchor, ...), and
                                                                 for dungeons Floor[] (TransY) and Room[] (CenterTrans,
                                                                 Floor list, ZoomScale)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)

import romtools  # noqa: E402

ROMFS = os.environ.get("REMAKE_ROMFS") or "E:/LongshotLauncher-data/builds/rc/romfs"  # the app sets REMAKE_ROMFS
_FS = None


def fs():
    global _FS
    if _FS is None:
        _FS = romtools.Romfs(ROMFS, os.path.join(ROOT, "original"))
    return _FS


def _byml(rel):
    d = fs().raw(rel)
    if rel.endswith(".zs"):
        d = fs().zs.decompress(d)
    return romtools.byml_load(d, allow_big=True)[0]


def menu():
    return _byml("Game/MapMenuInfo/MapMenuInfo.game__ui__MapMenuInfo.bgyml")["MapMenuParamArray"]


def capture():
    return _byml("Game/MapCaptureInfo/MapCaptureInfo.game__MapCaptureInfo.bgyml")["MapCaptureParamArray"]


def map_param():
    return _byml("Banc/BancBasedResource/MapParam.byml.zs")


def areas():
    """{LocationName: {"menu": entry, "capture": entry}} pairing the two tables by index."""
    m, c = menu(), capture()
    return {e["LocationName"]: {"menu": e, "capture": c[i], "index": i} for i, e in enumerate(m)}


# Projection
# Field maps (UI/CustomTex/Map/Field/<Area>_<Age>_NN) and dungeon floor maps (UI/CustomTex/Map/Dungeon/<Dungeon>_<F>_*)
# are 2000 x 1440 px. The capture camera looks straight down (-Y) and is orthographic, centred on CameraPos. Despite its
# name, `Height` is the world extent in metres across the 2000 image columns, so scale = 2000 / Height px per metre,
# the same on both axes. I checked it on the Deku Tree B1 floor, where doors land on the room joins and room centres
# in the rooms. With 1440 / Height everything is 28% too small. North (-Z) is up, east (+X) is right.
TEX_W, TEX_H = 2000, 1440


def project(cap, x, z, tex_w=TEX_W, tex_h=TEX_H):
    """World (x, z) -> (px, py) on a 2000x1440 area/floor map, from the capture camera."""
    h = cap["Height"]
    cx, cz = cap.get("CameraPos", {}).get("X", 0.0), cap.get("CameraPos", {}).get("Z", 0.0)
    s = tex_w / h
    return tex_w / 2 + (x - cx) * s, tex_h / 2 + (z - cz) * s


def floor_of(level_param, y):
    """Dungeon floor index of a world height (0 = lowest, as in MapParam Floor[]). It's the highest floor whose TransY
    is at or below y + 1 m, since MapParam stores each floor's base height."""
    floors = level_param.get("Floor") or []
    best = 0
    for i, f in enumerate(floors):
        if f.get("TransY", -1e9) <= y + 1.0:
            best = i
    return best


def floor_name(level_param, idx):
    """'B2', 'B1', '1F', '2F', ... from MinFloor (negative = basements)."""
    n = level_param.get("MinFloor", 0) + idx
    if level_param.get("MinFloor", 0) < 0:
        return f"B{-n}" if n < 0 else f"{n + 1}F"
    return f"{n + 1}F"
