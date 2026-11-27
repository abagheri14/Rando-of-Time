"""remake_no_low_health_warnings (OOTRR's disable low-health warnings): at low health Link doesn't hunch over or pull
a face, and he doesn't pulse red. The beep is OoTR's own sfx_low_hp ("none"), in the cosmetics.

How (Longshot v3.2.0's game files):
- Pose and face: Link's animation files (AS/Player_Child, Player_Adult and the cutscene ones that hold Link) pick
  their "caution" animations off a bool input, IsCautionLife, which the game sets by name while life is low. Each
  file lists its input names as 32-bit offsets into its string pool. Ours points at "CautionLife" instead, the same
  string two letters in, a name the game never sets, so the input stays false. That's 4 bytes a file, nothing moves.
  Dark Link's file (Enemy_MiddleBoss_DarkLink) stays as it is.
- Red pulse: the player's PlayerGameParam (in every pack holding it, Dark Link's too, since a file in a pack has to
  end alike everywhere) has DamageColor, a red tint, and DamageColorCurve, the Hermit curve it pulses by over
  DamageColorCount (48) frames, rising late and dropping back like the heartbeat. Its values become 0.
- The flashing hearts on the HUD aren't touched: the heart gauge's "Pinch" state is played by the game's code from
  the HUD layout, and changing it there needs more than a value."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

INPUT = "IsCautionLife"
QUIET_NAME = "CautionLife"   # the same pooled string, two bytes in
SKIP_AS = ("Enemy_MiddleBoss_DarkLink.root.asb.zs",)
PARAM = "Player/PlayerGameParam/Player.game__player__PlayerGameParam.bgyml"
CURVE = "DamageColorCurve"
NOTE = "remake_no_low_health_warnings"


def _fs(romfs):
    import romtools
    return romtools.Romfs(romfs, os.path.join(HERE, "original"))


def _pooled(d, pool, off):
    """The pooled string at pool + off, or None when off isn't the start of one."""
    a = pool + off
    if not 0 < a < len(d) or d[a - 1] != 0:
        return None
    try:
        e = d.index(b"\0", a)
    except ValueError:
        return None
    w = d[a:e]
    return w.decode("ascii") if w and all(32 < c < 127 for c in w) else None


def input_slot(d):
    """(offset of the IsCautionLife name slot, its value) in an animation file, or None when the file doesn't list
    it as an input. Raises when it's there but not in the shape expected."""
    if d[:4] != b"ASB ":
        raise RuntimeError("not an animation file")
    at = d.find(b"\0" + INPUT.encode() + b"\0")
    if at < 0:
        return None
    s = at + 1
    if d.count(b"\0" + INPUT.encode() + b"\0") != 1 or d.count(b"\0" + QUIET_NAME.encode() + b"\0"):
        raise RuntimeError(f"{INPUT} isn't in the string pool once, or {QUIET_NAME} is already a name")
    found = []
    for pool in sorted(set(struct.unpack_from("<32I", d, 0)[2:])):
        if not 0 < pool < s:
            continue
        off = s - pool
        for m in re.finditer(re.escape(struct.pack("<I", off)), d):
            o = m.start()
            if o % 4 or o < 4 or o + 8 > len(d):
                continue
            near = [_pooled(d, pool, struct.unpack_from("<I", d, o + k)[0]) for k in (-8, -4, 4, 8)]
            if all(near):
                found.append((o, off))
    if not found:
        return None  # only an animation's name has it (Caution...), no input
    if len(found) != 1:
        raise RuntimeError(f"{INPUT} is listed {len(found)} times")
    return found[0]


def anim_files(romfs):
    """[romfs path] of every animation file (AS/*.asb.zs) but Dark Link's that has the IsCautionLife input."""
    fs = _fs(romfs)
    keep = []
    for f in sorted(os.listdir(os.path.join(romfs, "AS"))):
        if not f.endswith(".asb.zs") or f in SKIP_AS:
            continue
        data = fs.read("AS/" + f)
        if b"\0" + INPUT.encode() + b"\0" in data and input_slot(data) is not None:
            keep.append("AS/" + f)
    return keep


def plan(romfs):
    """(names ops, packs ops, read-back) for remake_no_low_health_warnings."""
    import packpaths
    import romtools
    fs = _fs(romfs)
    names, rows = [], []
    for rel in anim_files(romfs):
        o, off = input_slot(fs.read(rel))
        names.append({"file": rel, "bytes": [{"offset": o, "expect": struct.pack("<I", off).hex(),
                                              "bytes": struct.pack("<I", off + 2).hex()}], "note": NOTE})
        rows.append([rel, o, off + 2])
    if sum(1 for r in rows if r[0] in ("AS/Player_Child.root.asb.zs", "AS/Player_Adult.root.asb.zs")) != 2:
        raise RuntimeError(f"{NOTE}: Link's own animation files don't list {INPUT}")
    packs = sorted(packpaths.index(romfs).get(PARAM) or ())
    if not packs:
        raise RuntimeError(f"{NOTE}: no pack holds {PARAM}")
    y = romtools.byml_load(romtools.sarc_files(fs.read(packs[0]))[PARAM])[0]
    curve = y.get(CURVE) or {}
    data = curve.get("Data") or []
    if curve.get("Type") != "Hermit" or len(data) < 4 or not any(data):
        raise RuntimeError(f"{NOTE}: {PARAM}'s {CURVE} isn't the curve it should be")
    pack_ops = [{"pack": "*", "file": PARAM, "set": {f"{CURVE}.Data.{k}": 0.0 for k in range(len(data))},
                 "note": NOTE}]
    return names, pack_ops, {"anims": rows, "packs": packs, "curve": len(data)}


def verify(patch, rb, romfs):
    """[problem] reading the low-health changes back from a built patch."""
    import romtools
    fs = romtools.Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    for rel, o, want in rb["anims"]:
        if not os.path.exists(os.path.join(patch, rel)):
            bad.append(f"{rel}: not in the patch")
            continue
        d = fs.read(rel)
        if struct.unpack_from("<I", d, o)[0] != want:
            bad.append(f"{rel}: the {INPUT} input still has its name")
    for pk in rb["packs"]:
        y = romtools.byml_load(romtools.sarc_files(fs.read(pk))[PARAM])[0]
        data = (y.get(CURVE) or {}).get("Data") or []
        if len(data) != rb["curve"] or any(data):
            bad.append(f"{pk}: {CURVE} still pulses")
    return bad
