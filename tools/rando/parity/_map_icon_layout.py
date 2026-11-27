"""New pictures for the map's facility icons (the map tracker's, parity/_map_icons.py): more frames on the icon
layout's Type animation, each showing a texture pair of ours.

The layout is PaMapIconFacility_00.buil in UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.blarc.zs (a SARC
holding every layout four times, byte-identical; all four copies change). A .buil ("BFFH",
Nintendo.Ui.ResModels.LayoutResData) has two sections: "Default" (the data) and "StringPool" (strings ending in
0, pointed at directly). Every reference is an absolute u64 file offset, arrays are {u64 pointer, u32 count, u32
stride}.
- Two texture-name lists of 31 pointers (stride 8): the pictures (MapIconShopMask_00 ... MapIconCarpenter_03) and
  their glows (...Sh_00), in the same order.
- The Type animation (name "Type", u32 frame count 38 at its +0x28 and +0x8C) has two step curves over frames
  1-38, one per list: a curve is {u64 keys block, u64 values block}; the keys block is {f32 first frame, f32 last
  frame, keys array}, the values block {f32 highest value, pad, values array}. Each picture change at frame F is two
  keys at F (the old index, then the new), and the values array holds (index, slope 0) per key. Frame f shows list
  entry "index" (IconType 1 -> 0, 3 -> 1, ... 38 -> 30; unused types keep the picture before).
- The map code sets the frame to the record's IconType (main 0x802232A4) and only treats 35-38 specially (the
  carpenters), so IconType 39 and up just need frames.
add_pictures() appends the new names, the longer lists and the longer curve arrays at the end of the file (inside
the string pool section, which grows to cover them), repoints the lists and curves, and raises the counts, the last
frame (38 + n), the highest value (30 + n) and the frame count. Nothing else moves.
"""
import struct

LAYOUT = "PaMapIconFacility_00.buil"
VANILLA_FRAMES, VANILLA_PICTURES = 38, 31
FIRST_NEW = VANILLA_FRAMES + 1  # IconType of the first new picture


def _q(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _f32(b, o):
    return struct.unpack_from("<f", b, o)[0]


def _str(b, at):
    return bytes(b[at:b.index(b"\0", at)]).decode("ascii", "replace")


def _string_at(b, name):
    """Offset of the string `name` (a whole one: a 0 before and after it), or None."""
    i = bytes(b).find(b"\0" + name.encode() + b"\0")
    return i + 1 if i >= 0 else None


def _lists(b):
    """(picture list header, glow list header): {pointer, count 31, stride 8} whose first entry names a map icon."""
    found = {}
    for o in range(0, len(b) - 16, 8):
        if VANILLA_PICTURES <= _u32(b, o + 8) < 1000 and _u32(b, o + 12) == 8:
            p = _q(b, o)
            if 0 < p < len(b) - 8:
                first = _str(b, _q(b, p))
                if first.startswith("MapIcon"):
                    found["glow" if first.endswith("Sh_00") else "picture"] = o
    if set(found) != {"picture", "glow"}:
        raise ValueError(f"{LAYOUT}: the two texture lists aren't where expected ({found})")
    return found["picture"], found["glow"]


def _type_anim(b):
    """(the animation's frame count field, [the two texture curves]) of the Type animation, vanilla or extended."""
    name = _string_at(b, "Type")
    for o in range(8, len(b) - 0x30, 8):
        frames = _u32(b, o - 8)
        if _q(b, o) != name or not VANILLA_FRAMES <= frames < 1000:
            continue
        arr, n = _q(b, o + 0x18), _u32(b, o + 0x20)
        curves = []
        for i in range(n):
            c = _q(b, arr + 8 * i)
            keys = _q(b, c)
            if (_f32(b, keys), _f32(b, keys + 4)) == (1.0, float(frames)) and                     _u32(b, keys + 16) == 2 * (VANILLA_PICTURES + frames - VANILLA_FRAMES) - 1:
                curves.append(c)
        if len(curves) != 2:
            raise ValueError(f"{LAYOUT}: {len(curves)} texture curves in Type, want 2")
        return o - 8, curves
    raise ValueError(f"{LAYOUT}: no Type animation")


def check(b):
    """[problem] when the layout isn't the one add_pictures was made for."""
    try:
        pic, glow = _lists(b)
        anim, curves = _type_anim(b)
    except ValueError as e:
        return [str(e)]
    bad = []
    for c in curves:
        keys, vals = _q(b, c), _q(b, c + 8)
        k = struct.unpack_from(f"<{2 * VANILLA_PICTURES - 1}f", b, _q(b, keys + 8))
        v = struct.unpack_from(f"<{4 * VANILLA_PICTURES - 2}f", b, _q(b, vals + 8))
        if k[-1] != VANILLA_FRAMES or v[-2] != VANILLA_PICTURES - 1 or _f32(b, vals) != VANILLA_PICTURES - 1:
            bad.append(f"{LAYOUT}: a texture curve doesn't end at frame {VANILLA_FRAMES} on picture 30")
    if _u32(b, anim + 0x64) != VANILLA_FRAMES:
        bad.append(f"{LAYOUT}: the Type animation's second frame count isn't {VANILLA_FRAMES}")
    return bad


def add_pictures(b, pairs):
    """The layout with new pictures: pairs = [(picture texture, glow texture)], shown at IconType FIRST_NEW + i.
    Returns the new bytes."""
    bad = check(b)
    if bad:
        raise ValueError("; ".join(bad))
    n = len(pairs)
    out = bytearray(b)

    def append(blob, align=8):
        out.extend(b"\0" * (-len(out) % align))
        at = len(out)
        out.extend(blob)
        return at

    def string(s):
        at = _string_at(bytes(out), s)
        if at is not None:
            return at
        return append(s.encode() + b"\0", 1)
    pic, glow = _lists(b)
    for hdr, col in ((pic, 0), (glow, 1)):
        old = [_q(b, _q(b, hdr) + 8 * i) for i in range(VANILLA_PICTURES)]
        new = old + [string(p[col]) for p in pairs]
        at = append(b"".join(struct.pack("<Q", x) for x in new))
        struct.pack_into("<QII", out, hdr, at, len(new), 8)
    anim, curves = _type_anim(b)
    for c in curves:
        keys, vals = _q(b, c), _q(b, c + 8)
        k = list(struct.unpack_from(f"<{2 * VANILLA_PICTURES - 1}f", b, _q(b, keys + 8)))
        v = list(struct.unpack_from(f"<{4 * VANILLA_PICTURES - 2}f", b, _q(b, vals + 8)))
        for i in range(n):
            frame, idx = FIRST_NEW + i, VANILLA_PICTURES + i
            k += [frame, frame]
            v += [idx - 1, 0.0, idx, 0.0]
        ka = append(struct.pack(f"<{len(k)}f", *k))
        va = append(struct.pack(f"<{len(v)}f", *v))
        struct.pack_into("<f", out, keys + 4, float(VANILLA_FRAMES + n))
        struct.pack_into("<QII", out, keys + 8, ka, len(k), 4)
        struct.pack_into("<f", out, vals, float(VANILLA_PICTURES - 1 + n))
        struct.pack_into("<QII", out, vals + 8, va, len(v), 4)
    struct.pack_into("<I", out, anim, VANILLA_FRAMES + n)
    struct.pack_into("<I", out, anim + 0x64, VANILLA_FRAMES + n)
    # the string pool section grows to the end, and so does the file
    pool = bytes(out).find(b"BFSI", 0xA8 + 4)
    if bytes(out[pool + 0x18:pool + 0x22]) != b"StringPool":
        raise ValueError(f"{LAYOUT}: no StringPool section header")
    start = _u32(out, pool + 4)
    struct.pack_into("<I", out, pool + 8, len(out) - start)
    struct.pack_into("<I", out, 8, len(out))
    return bytes(out)


def read_pictures(b):
    """{IconType: (picture, glow)} the layout's Type animation shows (frames 1 .. last), for the read-back."""
    pic, glow = _lists(b)
    _, curves = _type_anim(b)
    names = [(_str(b, _q(b, _q(b, pic) + 8 * i)), _str(b, _q(b, _q(b, glow) + 8 * i))) for i in range(_u32(b, pic + 8))]
    out = {}
    for which, c in enumerate(curves):
        keys, vals = _q(b, c), _q(b, c + 8)
        nk = _u32(b, keys + 16)
        k = struct.unpack_from(f"<{nk}f", b, _q(b, keys + 8))
        v = struct.unpack_from(f"<{2 * nk}f", b, _q(b, vals + 8))[0::2]
        cur = 0
        for f in range(1, int(_f32(b, keys + 4)) + 1):
            for kk, vv in zip(k, v):
                if kk <= f:
                    cur = int(vv)
            if which == 0:
                out[f] = names[cur]
            elif out.get(f) != names[cur]:
                raise ValueError(f"{LAYOUT}: the two texture curves differ at frame {f}")
    return out


def sarc_replace(data, name, new):
    """The SARC `data` with every copy of `name` holding `new`, each entry keeping at least its old alignment."""
    if data[:4] != b"SARC":
        raise ValueError("not a SARC archive")
    hsize = struct.unpack_from("<H", data, 4)[0]
    data_off = _u32(data, 0x0C)
    sfat = hsize
    n = struct.unpack_from("<H", data, sfat + 6)[0]
    names_at = sfat + 0x0C + 0x10 * n + 8
    rows = []
    for i in range(n):
        h, attr, s, e = struct.unpack_from("<IIII", data, sfat + 0x0C + 0x10 * i)
        at = names_at + (attr & 0xFFFFFF) * 4
        rows.append((data[at:data.index(b"\0", at)].decode(), s, e))
    head = bytearray(data[:data_off])
    body = bytearray()
    hits = 0
    for i, (nm, s, e) in enumerate(rows):
        align = 1  # the file's alignment in the archive (absolute), kept
        while (data_off + s) % (align * 2) == 0 and align < 0x2000:
            align *= 2
        body.extend(b"\0" * (-(data_off + len(body)) % align))
        start = len(body)
        if nm == name:
            body.extend(new)
            hits += 1
        else:
            body.extend(data[data_off + s:data_off + e])
        struct.pack_into("<II", head, sfat + 0x0C + 0x10 * i + 8, start, len(body))
    if not hits:
        raise ValueError(f"no {name} in the archive")
    struct.pack_into("<I", head, 8, len(head) + len(body))
    return bytes(head + body)
