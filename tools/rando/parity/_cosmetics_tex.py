"""Recolour a BC1/BC3 texture (Tex/*.bntx.zs) in place, same size, by rewriting its blocks' colour endpoints.

A BC1 or BC3 block stores two RGB565 end colours and per-pixel 2-bit indices into the colours between them. A
linear colour map applied to both end colours applies exactly to every pixel, so recolouring needs no decoding, no
swizzle and no re-encoding. Every block of every mip level just gets rewritten by itself. The map is "luminance
times target", so each end colour becomes target * (its luminance / the texture's mean luminance). The texture
keeps its light and dark detail and its average becomes the target colour, which is what OoTR's tunic colours are
(the average colour of a flat tunic).

Only BC1 (0x1a) and BC3 (0x1c) textures can be done this way. The remake's other coloured equipment textures are
ASTC (0x2d..0x3a), and their blocks need a real encoder.
"""
import os
import struct

BC1, BC3 = 0x1A, 0x1C


def info(data):
    """{fmt, srgb, width, height, mips, start, size} of a single-texture BNTX (data region = BRTD payload)."""
    if data[:4] != b"BNTX":
        raise ValueError("not a BNTX texture")
    b = data.find(b"BRTI")
    t = data.find(b"BRTD")
    if b < 0 or t < 0:
        raise ValueError("BNTX without BRTI/BRTD")
    mips = struct.unpack_from("<H", data, b + 0x16)[0]
    fmt = struct.unpack_from("<I", data, b + 0x1C)[0]
    w, h = struct.unpack_from("<II", data, b + 0x24)
    size = struct.unpack_from("<I", data, b + 0x50)[0]
    start = t + 0x10
    if start + size > len(data):
        raise ValueError("BNTX image size runs past the file")
    return {"fmt": fmt >> 8, "srgb": (fmt & 0xFF) == 6, "width": w, "height": h, "mips": mips,
            "start": start, "size": size}


def _rgb(c):
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


def _565(r, g, b):
    def q(v, n):
        return max(0, min(n, int(v * n / 255 + 0.5)))
    return (q(r, 31) << 11) | (q(g, 63) << 5) | q(b, 31)


def _lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _blocks(t):
    step = 8 if t["fmt"] == BC1 else 16
    colour_at = 0 if t["fmt"] == BC1 else 8
    return range(t["start"], t["start"] + t["size"] - step + 1, step), colour_at


def mean_colour(data):
    """Mean (r, g, b) and luminance of the texture's end colours (mip 0 dominates the count)."""
    t = info(data)
    if t["fmt"] not in (BC1, BC3):
        raise ValueError(f"format {t['fmt']:#x} is not BC1/BC3")
    rng, ca = _blocks(t)
    s = [0.0, 0.0, 0.0]
    n = 0
    for o in rng:
        c0, c1 = struct.unpack_from("<HH", data, o + ca)
        for c in (c0, c1):
            rgb = _rgb(c)
            s[0] += rgb[0]
            s[1] += rgb[1]
            s[2] += rgb[2]
            n += 1
    m = tuple(v / max(n, 1) for v in s)
    return m, _lum(m)


def recolour(data, target, ref_lum=None):
    """New texture bytes: every end colour c -> target * lum(c) / ref_lum (default: the texture's mean luminance)."""
    t = info(data)
    if t["fmt"] not in (BC1, BC3):
        raise ValueError(f"format {t['fmt']:#x} is not BC1/BC3")
    if ref_lum is None:
        ref_lum = mean_colour(data)[1]
    ref_lum = max(ref_lum, 1.0)
    out = bytearray(data)
    rng, ca = _blocks(t)
    tr, tg, tb = target
    for o in rng:
        c0, c1, idx = struct.unpack_from("<HHI", data, o + ca)
        n = []
        for c in (c0, c1):
            f = _lum(_rgb(c)) / ref_lum
            n.append(_565(min(255, tr * f), min(255, tg * f), min(255, tb * f)))
        n0, n1 = n
        # In BC1, c0 > c1 means four colours, otherwise three plus black/transparent. BC3 colour blocks are always
        # four-colour by the spec, but some decoders follow the BC1 rule anyway, so we keep the vanilla order for both
        # (the game's BC3 tunic texture only has c0 >= c1 blocks).
        four = c0 > c1
        if four and n0 < n1 or not four and n0 > n1:
            n0, n1 = n1, n0
            # swap the end colours: indices 0<->1, and in four-colour mode 2<->3 (the two blends)
            idx = idx ^ 0x55555555 if four else _swap01(idx)
        if four and n0 == n1:  # equal ends would read as three-colour mode, so nudge blue by one step (no carry)
            if n0 & 31 < 31:
                n0 += 1
            else:
                n1 -= 1
        struct.pack_into("<HHI", out, o + ca, n0, n1, idx)
    return bytes(out)


def _swap01(idx):
    """Three-colour BC1 block with its end colours swapped: index 0<->1, 2 (midpoint) and 3 (transparent) stay."""
    out = 0
    for i in range(16):
        v = (idx >> (2 * i)) & 3
        if v < 2:
            v ^= 1
        out |= v << (2 * i)
    return out


def hex_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# Whole-tunic recolour (any format)
# Child and adult Link's Kokiri tunic is several textures: the plaid shirt (Angin_Tile_A_Alb, BC3), the darker plaid
# of the trousers and hat (Angin_Tile_A_Dark_Alb, ASTC 5x4), the vest and its band (Mt_Vest_Player_*_Alb, ASTC
# 10x8) and the cloth parts (Mt_Cloth_Parts_Player_Child_Alb, ASTC 8x5). Recolouring only the shirt left the rest
# green ("half of the tunic is green and the other half is red"). So every one of them maps its green colours to the
# target at their own brightness against the shirt's mean, which keeps the vest darker than the shirt like it's
# designed. Colours far from green (brown leather, metal, skin) keep theirs, with a soft edge between.
ASTC_FORMATS = range(0x2D, 0x3B)


def greenness(rgb):
    """0..1: how much a colour is the tunic's green (hue 65-170 degrees, not grey)."""
    r, g, b = (max(0.0, min(255.0, float(v))) for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx <= 0 or mx - mn < 1e-6:
        return 0.0
    sat = (mx - mn) / mx
    if mx == r:
        hue = 60 * (((g - b) / (mx - mn)) % 6)
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn) + 2)
    else:
        hue = 60 * ((r - g) / (mx - mn) + 4)
    if 65 <= hue <= 170:
        h = 1.0
    elif 45 < hue < 65:
        h = (hue - 45) / 20
    elif 170 < hue < 190:
        h = (190 - hue) / 20
    else:
        h = 0.0
    s = 0.0 if sat <= 0.06 else 1.0 if sat >= 0.15 else (sat - 0.06) / 0.09
    return h * s


def tunic_map(target, ref_lum, selective=True):
    """fn(rgb) -> rgb: green colours to `target` at lum(c) / ref_lum (selective: weighted by greenness)."""
    ref = max(float(ref_lum), 1.0)

    def fn(c):
        f = _lum(c) / ref
        mapped = tuple(min(255.0, t * f) for t in target)
        g = greenness(c) if selective else 1.0
        return tuple(c[k] + (mapped[k] - c[k]) * g for k in range(3))
    fn.key = ("tunic_map", tuple(target), ref, bool(selective))  # (recolour_any's cache)
    return fn


# Selective recolours (other equipment)
# Each selection picks the colours of one part of a texture by hue and saturation (weight 0..1, soft edges), and the
# rest of the texture keeps its colours. Measured on the game's textures (hue histograms and mask renders):
#   goron:     the Goron tunic's reds (cloth 345 deg s.74, vest 345-0 deg s.26-.51, undershirt 330 deg s.28); its
#              gold trims (30 deg), brown leather (15-25 deg) and beads stay
#   zora:      the Zora tunic's blues (195-240 deg); white parts, purple leather, brown straps stay
#   frame:     the mirror shield's red frame (9 deg s.71); its leather back and straps (22 deg s.40) and the
#              lavender mirror face stay
#   not_jewel: everything but a saturated red jewel (the gauntlets' metal; the jewel is 0-345 deg s.76-.90)
#   heart:     the HUD heart's red-orange (heart 13 deg s.79, glow fringes and sparkles orange); white cores stay
#   magic:     the magic meter's greens (fill 142 deg, glows, flash edges, yellow-green sparkles)
SELECTIONS = {  # name: (hue from, hue to, soft edge degrees, saturation with weight 0, with weight 1, invert)
    "goron": (-30, 8, 6, 0.12, 0.20, False),
    "zora": (185, 250, 12, 0.10, 0.18, False),
    "frame": (-20, 12, 6, 0.45, 0.55, False),
    "frame_strip": (-25, 28, 6, 0.10, 0.20, False),
    "not_jewel": (-20, 12, 8, 0.35, 0.50, True),
    "heart": (-35, 45, 10, 0.12, 0.25, False),
    "magic": (70, 175, 10, 0.10, 0.20, False),
}
# Texture areas (u0, v0, u1, v1 of the texture, 0..1, top left = 0, 0) where another selection applies. A part whose
# colours mix with its neighbours' would come out blotchy by colour alone. The mirror shield's frame strips (the
# bottom third of its texture) are red with a mottled red-brown fringe, and by colour alone the fringe changed in
# patches. So inside the strips every red to brown colour changes (the gold rivets stay), and elsewhere only the
# strong red does, since the leather back and the straps share the fringe's browns.
ZONES = {"frame": [(0.0, 0.66, 1.0, 1.0, "frame_strip")]}


def hue_sat(rgb):
    """(hue degrees 0..360, saturation 0..1) of an (r, g, b) colour; hue 0 for greys."""
    r, g, b = (max(0.0, min(255.0, float(v))) for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx <= 0 or mx - mn < 1e-6:
        return 0.0, 0.0
    if mx == r:
        hue = 60 * (((g - b) / (mx - mn)) % 6)
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn) + 2)
    else:
        hue = 60 * ((r - g) / (mx - mn) + 4)
    return hue, (mx - mn) / mx


def selection(name):
    """fn(rgb) -> 0..1: how much a colour belongs to the named part (SELECTIONS)."""
    lo, hi, soft, s0, s1, invert = SELECTIONS[name]

    def weight(c):
        hue, sat = hue_sat(c)
        if hue > hi + soft:  # put the hue on the window's side of the circle (red windows cross 0)
            hue -= 360
        if hue < lo - soft:
            hue += 360
        if lo <= hue <= hi:
            h = 1.0
        elif lo - soft < hue < lo:
            h = (hue - (lo - soft)) / soft
        elif hi < hue < hi + soft:
            h = (hi + soft - hue) / soft
        else:
            h = 0.0
        s = 0.0 if sat <= s0 else 1.0 if sat >= s1 else (sat - s0) / (s1 - s0)
        w = h * s
        return 1.0 - w if invert else w
    weight.key = ("selection", name, (lo, hi, soft, s0, s1, invert))  # (recolour_any's cache)
    return weight


def mean_selected(data, weight, zone_at=None, region=None):
    """(mean (r, g, b), its luminance) of the texture's end colours, each weighted by weight(colour). That's the average
    colour of the selected part, over all mips (mip 0 dominates). BC1/BC3/ASTC. With zone_at ({block offset: zone}),
    weight is {zone: weight fn}. `region` picks one texture of a many-texture BNTX ({fmt, start, size} from
    bntx_textures)."""
    t = info(data) if region is None else region
    s, n = [0.0, 0.0, 0.0], 0.0
    here = [weight if zone_at is None else weight[-1]]

    def add(c):
        nonlocal n
        w = here[0](c)
        if w > 0:
            for k in range(3):
                s[k] += c[k] * w
            n += w
    if t["fmt"] in ASTC_FORMATS:
        import _astc
        seen = {}
        for o in range(t["start"], t["start"] + t["size"] - 15, 16):
            if zone_at is not None:
                here[0] = weight[zone_at.get(o, -1)]
            blk = bytes(data[o:o + 16])
            eps = seen.get(blk)
            if eps is None:
                try:
                    f = _astc.parse(blk)
                    eps = seen[blk] = ([(tuple(v / 257 for v in f["void"][:3]),) * 2] if "void" in f
                                       else _astc.block_endpoints(f))
                except _astc.AstcError:
                    eps = seen[blk] = []
            for e0, e1 in eps:
                add(e0[:3])
                add(e1[:3])
    elif t["fmt"] in (BC1, BC3):
        rng, ca = _blocks(t)
        for o in rng:
            if zone_at is not None:
                here[0] = weight[zone_at.get(o, -1)]
            c0, c1 = struct.unpack_from("<HH", data, o + ca)
            add(_rgb(c0))
            add(_rgb(c1))
    else:
        raise ValueError(f"format {t['fmt']:#x} can't be read")
    if n <= 0:
        raise ValueError("the selection matches no colour of the texture")
    m = tuple(v / n for v in s)
    return m, _lum(m)


def select_map(target, ref_lum, weight):
    """fn(rgb) -> rgb: the selected colours to `target` at lum(c) / ref_lum, blended by their weight."""
    ref = max(float(ref_lum), 1.0)

    def fn(c):
        f = _lum(c) / ref
        mapped = tuple(min(255.0, t * f) for t in target)
        g = weight(c)
        return tuple(c[k] + (mapped[k] - c[k]) * g for k in range(3))
    wkey = getattr(weight, "key", None)
    fn.key = None if wkey is None else ("select_map", tuple(target), ref, wkey)  # (recolour_any's cache)
    return fn


ASTC_BLOCKS = {0x2D: (4, 4), 0x2E: (5, 4), 0x2F: (5, 5), 0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5), 0x33: (8, 6),
               0x34: (8, 8), 0x35: (10, 5), 0x36: (10, 6), 0x37: (10, 8), 0x38: (10, 10), 0x39: (12, 10),
               0x3A: (12, 12)}


def bntx_textures(data):
    """[{name, brti, fmt, srgb, w, h, mips, start, size, block_height}] of a BNTX holding one texture or many
    (the HUD's UI/Layout2Archive/Common...bntx.zs holds 878). Platform tag "Ounc" on the Switch 2."""
    if data[:4] != b"BNTX":
        raise ValueError("not a BNTX file")
    count = struct.unpack_from("<I", data, 0x24)[0]
    arr = struct.unpack_from("<Q", data, 0x28)[0]
    out = []
    for i in range(count):
        b = struct.unpack_from("<Q", data, arr + 8 * i)[0]
        if data[b:b + 4] != b"BRTI":
            raise ValueError("BNTX texture table doesn't point at a BRTI")
        fmt = struct.unpack_from("<I", data, b + 0x1C)[0]
        w, h = struct.unpack_from("<II", data, b + 0x24)
        layout = struct.unpack_from("<I", data, b + 0x34)[0]
        name_at = struct.unpack_from("<Q", data, b + 0x60)[0]
        n = struct.unpack_from("<H", data, name_at)[0]
        mips_at = struct.unpack_from("<Q", data, b + 0x70)[0]
        out.append({"name": data[name_at + 2:name_at + 2 + n].decode(), "brti": b, "fmt": fmt >> 8,
                    "srgb": (fmt & 0xFF) == 6, "w": w, "h": h, "mips": struct.unpack_from("<H", data, b + 0x16)[0],
                    "start": struct.unpack_from("<Q", data, mips_at)[0],
                    "size": struct.unpack_from("<I", data, b + 0x50)[0], "block_height": 1 << (layout & 7)})
    return out


def gob_address(x, y, width_in_gobs, bpb, block_height):
    """Byte offset of block (x, y) in a block-linear surface (bpb bytes per block). Inside a 512-byte GOB the Switch 2
    (NVN2) orders the address bits x0-3, y0, y1, x4, y2, x5. The Switch 1's order (x0-3, y0, x4, y1, y2, x5) scrambles
    these textures. I found this by decoding the HUD's letter and heart textures every way, keeping the smooth one and
    then checking it by eye."""
    xb = x * bpb
    gob = ((y // (8 * block_height)) * 512 * block_height * width_in_gobs + (xb // 64) * 512 * block_height
           + (y % (8 * block_height) // 8) * 512)
    return (gob + (xb & 15) + ((y & 1) << 4) + (((y >> 1) & 1) << 5) + (((xb >> 4) & 1) << 6)
            + (((y >> 2) & 1) << 7) + (((xb >> 5) & 1) << 8))


def block_positions(data):
    """{block offset: (u, v)} for every block of every mip of a single-texture BNTX, where (u, v) is the block's centre
    in the texture (0..1). Mip offsets come from the texture's own table, and each mip's block height shrinks while
    the mip is at most half a block high (the Tegra rule)."""
    b = data.find(b"BRTI")
    t = info(data)
    fmt = t["fmt"]
    bw, bh = ASTC_BLOCKS.get(fmt, (4, 4))
    bpb = 16 if fmt in ASTC_FORMATS or fmt == BC3 else 8
    block_h0 = 1 << (struct.unpack_from("<I", data, b + 0x34)[0] & 7)
    mips_at = struct.unpack_from("<Q", data, b + 0x70)[0]
    out = {}
    for level in range(t["mips"]):
        base = struct.unpack_from("<Q", data, mips_at + 8 * level)[0]
        w, h = max(1, t["width"] >> level), max(1, t["height"] >> level)
        nx, ny = -(-w // bw), -(-h // bh)
        width_in_gobs = -(-nx * bpb // 64)
        block_h = block_h0
        while block_h > 1 and ny <= 8 * (block_h // 2):
            block_h //= 2
        for y in range(ny):
            for x in range(nx):
                out[base + gob_address(x, y, width_in_gobs, bpb, block_h)] = ((x + 0.5) / nx, (y + 0.5) / ny)
    return out


def _zone_of(name, uv):
    for i, (u0, v0, u1, v1, _sel) in enumerate(ZONES.get(name, ())):
        if uv is not None and u0 <= uv[0] < u1 and v0 <= uv[1] < v1:
            return i
    return -1


def _zone_selection(name, zone):
    return selection(name if zone < 0 else ZONES[name][zone][4])


def mean_of_selection(data, name):
    """mean_selected for a named selection, with its zones (ZONES) applied by block position."""
    if name not in ZONES:
        return mean_selected(data, selection(name))
    pos = block_positions(data)
    weights = {z: _zone_selection(name, z) for z in range(-1, len(ZONES[name]))}
    zone_at = {o: _zone_of(name, uv) for o, uv in pos.items()}
    return mean_selected(data, weights, zone_at)


def recolour_selected(data, name, target, ref_lum):
    """(new bytes, counts) with the named selection's colours moved to `target` at lum(c) / ref_lum (select_map). When
    the selection has zones (ZONES), each block uses its zone's selection."""
    if name not in ZONES:
        w = selection(name)
        return recolour_any(data, select_map(target, ref_lum, w))
    pos = block_positions(data)
    fns = {z: select_map(target, ref_lum, _zone_selection(name, z)) for z in range(-1, len(ZONES[name]))}
    zone_at = {o: _zone_of(name, uv) for o, uv in pos.items()}
    return recolour_any(data, fns, zone_at)


# A recolour is pure Python. For an ASTC texture every distinct block gets decoded and re-encoded, and a player's
# tunic, gauntlet and HUD colours take ~15 s. A seed also asks for each one twice, since make_patch writes it and the
# app's cosmetics check (_cosmetics_apply --check) builds it again to compare. So recolour_any keeps each result in
# cache/recolour/<stamp>.pkl (the pickled (bytes, counts)), under a stamp of everything it comes from: this file's
# and _astc.py's code, the texture's bytes, the region, the zones and the colour map's key. tunic_map, select_map and
# selection set .key from their arguments, and a map without one isn't cached. The folder keeps its newest
# RECOLOUR_CACHE_MAX bytes. REMAKE_NO_CACHE=1 turns the cache off. If we can't write to the folder there's no cache,
# same bytes.
RECOLOUR_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))), "cache", "recolour")
RECOLOUR_CACHE_MAX = 256 * 1024 * 1024
_RECOLOUR_CODE = []


def _recolour_stamp(data, fn, zone_at, region):
    import hashlib
    if isinstance(fn, dict):
        keys = tuple((z, getattr(f, "key", None)) for z, f in sorted(fn.items()))
        if any(k is None for _, k in keys):
            return None
    else:
        keys = getattr(fn, "key", None)
        if keys is None:
            return None
    if not _RECOLOUR_CODE:
        here = os.path.dirname(os.path.abspath(__file__))
        _RECOLOUR_CODE.append(hashlib.sha1(b"".join(open(os.path.join(here, f), "rb").read()
                                                    for f in ("_cosmetics_tex.py", "_astc.py"))).digest())
    h = hashlib.sha1(_RECOLOUR_CODE[0])
    h.update(repr((keys, None if region is None else sorted(region.items()),
                   None if zone_at is None else sorted(zone_at.items()), len(data))).encode())
    h.update(hashlib.blake2b(bytes(data)).digest())
    return h.hexdigest()


def recolour_any(data, fn, zone_at=None, region=None):
    """(new bytes, {how: count}) with every block's end colours mapped by fn, for BC1/BC3 (endpoint pairs) or ASTC.
    With zone_at ({block offset: zone}), fn is {zone: map} and each block uses its zone's map (zone -1 elsewhere).
    `region` picks one texture of a many-texture BNTX ({fmt, start, size} from bntx_textures). Comes from the disk
    cache when the same recolour was made before (RECOLOUR_CACHE)."""
    import pickle
    stamp = None if os.environ.get("REMAKE_NO_CACHE") == "1" else _recolour_stamp(data, fn, zone_at, region)
    if stamp is None:
        return _recolour_any(data, fn, zone_at, region)
    path = os.path.join(RECOLOUR_CACHE, stamp + ".pkl")
    try:
        with open(path, "rb") as f:
            out = pickle.load(f)
        try:
            os.utime(path)  # so it counts as newest when the folder is trimmed
        except OSError:
            pass
        return out
    except (OSError, EOFError, pickle.UnpicklingError, ValueError, TypeError):
        pass
    out = _recolour_any(data, fn, zone_at, region)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:  # written whole and then moved into place, then the oldest entries go while the folder is over its size
        os.makedirs(RECOLOUR_CACHE, exist_ok=True)
        with open(tmp, "wb") as f:
            pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
        ents = sorted((e for e in os.scandir(RECOLOUR_CACHE) if e.name.endswith(".pkl")),
                      key=lambda e: e.stat().st_mtime_ns, reverse=True)
        total = 0
        for e in ents:
            total += e.stat().st_size
            if total > RECOLOUR_CACHE_MAX and e.path != path:
                os.remove(e.path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return out


def _recolour_any(data, fn, zone_at=None, region=None):
    t = info(data) if region is None else region
    if t["fmt"] in ASTC_FORMATS:
        import _astc
        if zone_at is None:
            return _astc.recolour_region(data, t["start"], t["size"], fn)
        out = bytearray(data)
        counts, cache = {}, {}
        for o in range(t["start"], t["start"] + t["size"] - 15, 16):
            z = zone_at.get(o, -1)
            key = (bytes(data[o:o + 16]), z)
            hit = cache.get(key)
            if hit is None:
                hit = cache[key] = _astc.recolour_block(key[0], fn[z])
            out[o:o + 16] = hit[0]
            counts[hit[1]] = counts.get(hit[1], 0) + 1
        return bytes(out), counts
    if t["fmt"] not in (BC1, BC3):
        raise ValueError(f"format {t['fmt']:#x} can't be recoloured")
    out = bytearray(data)
    rng, ca = _blocks(t)
    counts = {}
    for o in rng:
        c0, c1, idx = struct.unpack_from("<HHI", data, o + ca)
        f = fn if zone_at is None else fn[zone_at.get(o, -1)]
        n = []
        for c in (c0, c1):
            m = f(_rgb(c))
            n.append(_565(*m))
        n0, n1 = n
        four = c0 > c1
        if four and n0 < n1 or not four and n0 > n1:
            n0, n1 = n1, n0
            idx = idx ^ 0x55555555 if four else _swap01(idx)
        if four and n0 == n1:
            if n0 & 31 < 31:
                n0 += 1
            else:
                n1 -= 1
        struct.pack_into("<HHI", out, o + ca, n0, n1, idx)
        how = "same" if (n0, n1) == (c0, c1) else "mapped"
        counts[how] = counts.get(how, 0) + 1
    return bytes(out), counts
