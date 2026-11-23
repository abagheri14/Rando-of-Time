"""ASTC (LDR) blocks: read, decode, and recolour in place by rewriting each block's colour endpoints.

Every 16-byte block holds its own end colours, and a texel is a weighted blend of its partition's two end colours.
So a colour map applied to the end colours reaches every texel of the block without decoding the image, without the
Switch's block-linear swizzle (blocks are rewritten one by one, wherever they sit) and without an encoder. The block
keeps its mode, weight grid, weights and partitioning, and only the endpoint section gets re-encoded (in RGB/RGBA
direct or base+scale mode, quantised as finely as the block's free bits allow). I built it from the Khronos Data
Format Specification's ASTC chapter and checked it by decoding the game's own textures.

recolour_block(block, fn) -> (new 16 bytes, how); recolour_region(data, start, size, fn) for a whole texture;
fn maps an (r, g, b) end colour (0..255) to its new colour.
decode_block(block, bw, bh) -> [[r, g, b, a]] * (bw * bh) texels (0..255), for checks.
"""
import math

# Integer sequence encoding (ISE)
# levels -> (bits, trits, quints)
QUANTS = {2: (1, 0, 0), 3: (0, 1, 0), 4: (2, 0, 0), 5: (0, 0, 1), 6: (1, 1, 0), 8: (3, 0, 0), 10: (1, 0, 1),
          12: (2, 1, 0), 16: (4, 0, 0), 20: (2, 0, 1), 24: (3, 1, 0), 32: (5, 0, 0), 40: (3, 0, 1), 48: (4, 1, 0),
          64: (6, 0, 0), 80: (4, 0, 1), 96: (5, 1, 0), 128: (7, 0, 0), 160: (5, 0, 1), 192: (6, 1, 0),
          256: (8, 0, 0)}
COLOUR_LEVELS = (6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128, 160, 192, 256)
WEIGHT_LEVELS = {0: (None, None, 2, 3, 4, 5, 6, 8), 1: (None, None, 10, 12, 16, 20, 24, 32)}


def ise_bits(n, levels):
    m, t, q = QUANTS[levels]
    return n * m + (8 * n + 4) // 5 * t + (7 * n + 2) // 3 * q


def _bit(v, i):
    return (v >> i) & 1


def _trits(T):
    if (T >> 2) & 7 == 7:
        C = (((T >> 5) & 7) << 2) | (T & 3)
        t4 = t3 = 2
    else:
        C = T & 31
        if (T >> 5) & 3 == 3:
            t4, t3 = 2, _bit(T, 7)
        else:
            t4, t3 = _bit(T, 7), (T >> 5) & 3
    if C & 3 == 3:
        t2, t1 = 2, _bit(C, 4)
        t0 = (_bit(C, 3) << 1) | (_bit(C, 2) & (1 - _bit(C, 3)))
    elif (C >> 2) & 3 == 3:
        t2, t1, t0 = 2, 2, C & 3
    else:
        t2, t1 = _bit(C, 4), (C >> 2) & 3
        t0 = (_bit(C, 1) << 1) | (_bit(C, 0) & (1 - _bit(C, 1)))
    return (t0, t1, t2, t3, t4)


def _quints(Q):
    if (Q >> 1) & 3 == 3 and (Q >> 5) & 3 == 0:
        q2 = (_bit(Q, 0) << 2) | ((_bit(Q, 4) & (1 - _bit(Q, 0))) << 1) | (_bit(Q, 3) & (1 - _bit(Q, 0)))
        q1 = q0 = 4
    else:
        if (Q >> 1) & 3 == 3:
            q2 = 4
            C = (((Q >> 3) & 3) << 3) | ((~(Q >> 5) & 3) << 1) | (Q & 1)
        else:
            q2 = (Q >> 5) & 3
            C = Q & 31
        if C & 7 == 5:
            q1, q0 = 4, (C >> 3) & 3
        else:
            q1, q0 = (C >> 3) & 3, C & 7
    return (q0, q1, q2)


_TRIT_DEC = [_trits(T) for T in range(256)]
_QUINT_DEC = [_quints(Q) for Q in range(128)]
# packed-bit positions inside a group (bits of T / Q stored after each value)
_TRIT_SPLIT = ((0, 2), (2, 2), (4, 1), (5, 2), (7, 1))
_QUINT_SPLIT = ((0, 3), (3, 2), (5, 2))


def _enc_table(dec, split, k):
    """(digits of the first k values) -> packed code whose bits past the first k values' share are zero."""
    keep = sum(n for _, n in split[:k])
    table = {}
    for code, digits in enumerate(dec):
        if code >> keep:
            continue
        table.setdefault(digits[:k], code)
    return table


_TRIT_ENC = {k: _enc_table(_TRIT_DEC, _TRIT_SPLIT, k) for k in range(1, 6)}
_QUINT_ENC = {k: _enc_table(_QUINT_DEC, _QUINT_SPLIT, k) for k in range(1, 4)}


def ise_decode(src, start, n, levels):
    """n integers from bit `start` of int `src` (bit 0 first)."""
    m, t, q = QUANTS[levels]
    pos = start

    def read(k):
        nonlocal pos
        v = (src >> pos) & ((1 << k) - 1)
        pos += k
        return v
    out = []
    if not t and not q:
        return [read(m) for _ in range(n)]
    group, split, dec = (5, _TRIT_SPLIT, _TRIT_DEC) if t else (3, _QUINT_SPLIT, _QUINT_DEC)
    end = start + ise_bits(n, levels)
    while len(out) < n:
        k = min(group, n - len(out))
        lows, code = [], 0
        for i in range(group):
            if i < k:
                lows.append(read(m))
            off, nb = split[i]
            if i < k:
                code |= read(nb) << off
        digits = dec[code]
        out.extend((digits[i] << m) | lows[i] for i in range(k))
    if pos > end + 0:  # partial groups never read past the sequence's own length
        raise ValueError("ISE overrun")
    return out


def ise_encode(values, levels):
    """(int, bit count) for the integers `values`."""
    m, t, q = QUANTS[levels]
    out, pos = 0, 0

    def put(v, k):
        nonlocal out, pos
        out |= (v & ((1 << k) - 1)) << pos
        pos += k
    if not t and not q:
        for v in values:
            put(v, m)
        return out, pos
    group, split, enc = (5, _TRIT_SPLIT, _TRIT_ENC) if t else (3, _QUINT_SPLIT, _QUINT_ENC)
    for g in range(0, len(values), group):
        vals = values[g:g + group]
        k = len(vals)
        code = enc[k][tuple(v >> m for v in vals)]
        for i in range(k):
            put(vals[i], m)
            off, nb = split[i]
            put(code >> off, nb)
    assert pos == ise_bits(len(values), levels)
    return out, pos


# Unquantisation
def _pattern(p, bits):
    """9- or 7-bit value from a spec bit pattern like 'b000b0bb0' (letters: bits of `bits`, a = bit 0)."""
    v = 0
    for ch in p:
        v = (v << 1) | (0 if ch == "0" else (bits >> (ord(ch) - ord("a"))) & 1)
    return v


_COLOUR_BC = {6: ("000000000", 204), 10: ("000000000", 113), 12: ("b000b0bb0", 93), 20: ("b0000bb00", 54),
              24: ("cb000cbcb", 44), 40: ("cb0000cbc", 26), 48: ("dcb000dcb", 22), 80: ("dcb0000dc", 13),
              96: ("edcb000ed", 11), 160: ("edcb0000e", 6), 192: ("fedcb000f", 5)}
_WEIGHT_BC = {6: ("0000000", 50), 10: ("0000000", 28), 12: ("b000b0b", 23), 20: ("b0000b0", 13),
              24: ("cb000cb", 11)}


def _replicate(v, n, to):
    out, have = 0, 0
    while have < to:
        out = (out << n) | v
        have += n
    return out >> (have - to)


def _unq_colour(v, levels):
    m, t, q = QUANTS[levels]
    if not t and not q:
        return _replicate(v, m, 8)
    low, D = v & ((1 << m) - 1), v >> m
    A = 0x1FF if low & 1 else 0
    pat, C = _COLOUR_BC[levels]
    T = (D * C + _pattern(pat, low)) ^ A
    return (A & 0x80) | (T >> 2)


def _unq_weight(v, levels):
    m, t, q = QUANTS[levels]
    if not t and not q:
        r = _replicate(v, m, 6)
    elif m == 0:
        r = {3: (0, 32, 63), 5: (0, 16, 32, 47, 63)}[levels][v]
    else:
        low, D = v & ((1 << m) - 1), v >> m
        A = 0x7F if low & 1 else 0
        pat, C = _WEIGHT_BC[levels]
        T = (D * C + _pattern(pat, low)) ^ A
        r = (A & 0x20) | (T >> 2)
    return r + 1 if r > 32 else r


COLOUR_UNQ = {lv: [_unq_colour(i, lv) for i in range(lv)] for lv in COLOUR_LEVELS}
WEIGHT_UNQ = {lv: [_unq_weight(i, lv) for i in range(lv)] for lv in (2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32)}
# weight inversion (w -> 64 - w) within the same quantisation: exact for every range (checked at import)
WEIGHT_INV = {}
for _lv, _tab in WEIGHT_UNQ.items():
    _inv = {v: i for i, v in enumerate(_tab)}
    WEIGHT_INV[_lv] = [_inv[64 - v] for v in _tab]


# quantise_colour's answer for every (levels, c 0..255), found by the same search once at import. A recolour asks
# it for every colour channel of every block, which is 115 million comparisons in a build with every cosmetic on.
COLOUR_Q = {lv: [min(range(lv), key=lambda i: abs(tab[i] - c)) for c in range(256)] for lv, tab in COLOUR_UNQ.items()}


def quantise_colour(c, levels):
    """The encoded integer whose unquantised value is nearest c (0..255)."""
    return COLOUR_Q[levels][max(0, min(255, int(round(c))))]


# Block layout
class AstcError(ValueError):
    pass


def block_mode(bm):
    """(weight grid width, height, dual plane, weight levels) of an 11-bit block mode, or raises AstcError."""
    if bm & 3:
        R = ((bm >> 4) & 1) | ((bm & 3) << 1)
        H, D = (bm >> 9) & 1, (bm >> 10) & 1
        A, B = (bm >> 5) & 3, (bm >> 7) & 3
        sel = (bm >> 2) & 3
        if sel == 0:
            W, Hh = B + 4, A + 2
        elif sel == 1:
            W, Hh = B + 8, A + 2
        elif sel == 2:
            W, Hh = A + 2, B + 8
        elif not (bm >> 8) & 1:
            W, Hh = A + 2, (B & 1) + 6
        else:
            W, Hh = (B & 1) + 2, A + 2
    else:
        if bm & 15 == 0:
            raise AstcError("reserved block mode")
        R = ((bm >> 4) & 1) | (((bm >> 2) & 3) << 1)
        H, D = (bm >> 9) & 1, (bm >> 10) & 1
        A = (bm >> 5) & 3
        sel = (bm >> 7) & 3
        if sel == 0:
            W, Hh = 12, A + 2
        elif sel == 1:
            W, Hh = A + 2, 12
        elif sel == 2:
            W, Hh = A + 6, ((bm >> 9) & 3) + 6
            D = H = 0
        else:
            if A == 0:
                W, Hh = 6, 10
            elif A == 1:
                W, Hh = 10, 6
            else:
                raise AstcError("reserved block mode")
    levels = WEIGHT_LEVELS[H][R]
    if levels is None:
        raise AstcError("reserved weight range")
    return W, Hh, D, levels


def parse(block):
    """A block's fields as a dict, or {"void": rgba16} for a constant-colour block. Raises AstcError on illegal or
    HDR content."""
    x = int.from_bytes(block, "little")
    if x & 0x1FF == 0x1FC:
        if (x >> 9) & 1:
            raise AstcError("HDR void extent")
        return {"void": [(x >> (64 + 16 * i)) & 0xFFFF for i in range(4)], "x": x}
    W, Hh, D, wlev = block_mode(x & 0x7FF)
    P = ((x >> 11) & 3) + 1
    nweights = W * Hh * (D + 1)
    if nweights > 64 or (D and P == 4):
        raise AstcError("too many weights")
    wbits = ise_bits(nweights, wlev)
    if not 24 <= wbits <= 96:
        raise AstcError("weight bits out of range")
    extra = 0
    if P == 1:
        cems = [(x >> 13) & 15]
        start = 17
        part = 0
    else:
        part = (x >> 13) & 0x3FF
        cemf = (x >> 23) & 0x3F
        start = 29
        if cemf & 3 == 0:
            cems = [cemf >> 2] * P
        else:
            extra = 3 * P - 4
            ext = (x >> (128 - wbits - extra)) & ((1 << extra) - 1)
            full = cemf | (ext << 6)
            base = (full & 3) - 1
            cs = [(full >> (2 + i)) & 1 for i in range(P)]
            ms = [(full >> (2 + P + 2 * i)) & 3 for i in range(P)]
            cems = [((base + cs[i]) << 2) | ms[i] for i in range(P)]
    if any(c in (2, 3, 7, 11, 14, 15) for c in cems):
        raise AstcError("HDR endpoint mode")
    nvals = sum(2 * ((c >> 2) + 1) for c in cems)
    if nvals > 18:
        raise AstcError("too many endpoint values")
    avail = 128 - start - wbits - extra - (2 if D else 0)
    clev = _colour_levels(nvals, avail)
    ccs = (x >> (128 - wbits - extra - 2)) & 3 if D else None
    vals = ise_decode(x, start, nvals, clev)
    rev = int(f"{x:0128b}"[::-1], 2)
    weights = ise_decode(rev, 0, nweights, wlev)
    return {"x": x, "W": W, "H": Hh, "D": D, "wlev": wlev, "wbits": wbits, "P": P, "part": part, "cems": cems,
            "clev": clev, "vals": vals, "ccs": ccs, "weights": weights}


def _colour_levels(nvals, avail):
    for lv in reversed(COLOUR_LEVELS):
        if ise_bits(nvals, lv) <= avail:
            return lv
    raise AstcError("too few bits for the endpoints")


# Endpoints
def _clamp(v):
    return max(0, min(255, v))


def _bts(a, b):
    """bit_transfer_signed: (offset a, base b) of a base+offset pair."""
    b = (b >> 1) | (a & 0x80)
    a = (a >> 1) & 0x3F
    if a & 0x20:
        a -= 0x40
    return a, b


def _bc(r, g, b, a):
    return ((r + b) >> 1, (g + b) >> 1, b, a)


def endpoints(cem, v):
    """(e0, e1) RGBA 0..255 of one partition's unquantised values `v`."""
    if cem == 0:
        return (v[0],) * 3 + (255,), (v[1],) * 3 + (255,)
    if cem == 1:
        L0 = (v[0] >> 2) | (v[1] & 0xC0)
        L1 = min(255, L0 + (v[1] & 0x3F))
        return (L0,) * 3 + (255,), (L1,) * 3 + (255,)
    if cem == 4:
        return (v[0],) * 3 + (v[2],), (v[1],) * 3 + (v[3],)
    if cem == 5:
        o1, b0 = _bts(v[1], v[0])
        o3, b2 = _bts(v[3], v[2])
        return (b0,) * 3 + (b2,), (_clamp(b0 + o1),) * 3 + (_clamp(b2 + o3),)
    if cem in (6, 10):
        a0, a1 = (v[4], v[5]) if cem == 10 else (255, 255)
        return (((v[0] * v[3]) >> 8), ((v[1] * v[3]) >> 8), ((v[2] * v[3]) >> 8), a0), (v[0], v[1], v[2], a1)
    if cem in (8, 12):
        a0, a1 = (v[6], v[7]) if cem == 12 else (255, 255)
        if v[1] + v[3] + v[5] >= v[0] + v[2] + v[4]:
            return (v[0], v[2], v[4], a0), (v[1], v[3], v[5], a1)
        return _bc(v[1], v[3], v[5], a1), _bc(v[0], v[2], v[4], a0)
    if cem in (9, 13):
        o1, b0 = _bts(v[1], v[0])
        o3, b2 = _bts(v[3], v[2])
        o5, b4 = _bts(v[5], v[4])
        if cem == 13:
            o7, b6 = _bts(v[7], v[6])
        else:
            o7, b6 = 0, 255
        if o1 + o3 + o5 >= 0:
            return (b0, b2, b4, b6), (_clamp(b0 + o1), _clamp(b2 + o3), _clamp(b4 + o5), _clamp(b6 + o7))
        return (_bc(_clamp(b0 + o1), _clamp(b2 + o3), _clamp(b4 + o5), _clamp(b6 + o7)), _bc(b0, b2, b4, b6))
    raise AstcError(f"endpoint mode {cem}")


def block_endpoints(f):
    """[(e0, e1)] per partition of a parsed block."""
    unq = [COLOUR_UNQ[f["clev"]][v] for v in f["vals"]]
    out, i = [], 0
    for c in f["cems"]:
        n = 2 * ((c >> 2) + 1)
        out.append(endpoints(c, unq[i:i + n]))
        i += n
    return out


# Texel decode (checks)
def _hash52(p):
    M = 0xFFFFFFFF
    p ^= p >> 15
    p = (p - (p << 17)) & M
    p = (p + (p << 7)) & M
    p = (p + (p << 4)) & M
    p ^= p >> 5
    p = (p + (p << 16)) & M
    p ^= p >> 7
    p ^= p >> 3
    p = (p ^ (p << 6)) & M
    p ^= p >> 17
    return p


def partition_of(seed, x, y, z, count, small):
    if count == 1:
        return 0
    if small:
        x, y, z = x << 1, y << 1, z << 1
    seed += (count - 1) * 1024
    r = _hash52(seed)
    s = [(r >> sh) & 0xF for sh in (0, 4, 8, 12, 16, 20, 24, 28, 18, 22, 26)]
    s.append(((r >> 30) | (r << 2)) & 0xF)
    s = [v * v for v in s]
    if seed & 1:
        sh1 = 4 if seed & 2 else 5
        sh2 = 6 if count == 3 else 5
    else:
        sh1 = 6 if count == 3 else 5
        sh2 = 4 if seed & 2 else 5
    sh3 = sh1 if seed & 0x10 else sh2
    shifts = (sh1, sh2, sh1, sh2, sh1, sh2, sh1, sh2, sh3, sh3, sh3, sh3)
    s = [v >> h for v, h in zip(s, shifts)]
    a = (s[0] * x + s[1] * y + s[10] * z + (r >> 14)) & 0x3F
    b = (s[2] * x + s[3] * y + s[11] * z + (r >> 10)) & 0x3F
    c = (s[4] * x + s[5] * y + s[8] * z + (r >> 6)) & 0x3F
    d = (s[6] * x + s[7] * y + s[9] * z + (r >> 2)) & 0x3F
    if count < 4:
        d = 0
    if count < 3:
        c = 0
    if a >= b and a >= c and a >= d:
        return 0
    if b >= c and b >= d:
        return 1
    if c >= d:
        return 2
    return 3


def texel_weights(f, bw, bh):
    """Per texel (plane 0 weight, plane 1 weight) 0..64, infilled from the weight grid."""
    W, H, D = f["W"], f["H"], f["D"]
    unq = [WEIGHT_UNQ[f["wlev"]][w] for w in f["weights"]]
    planes = [unq[p::D + 1] for p in range(D + 1)]
    Ds = (1024 + bw // 2) // (bw - 1)
    Dt = (1024 + bh // 2) // (bh - 1)
    out = []
    for t in range(bh):
        for s in range(bw):
            gs = (Ds * s * (W - 1) + 32) >> 6
            gt = (Dt * t * (H - 1) + 32) >> 6
            js, fs, jt, ft = gs >> 4, gs & 15, gt >> 4, gt & 15
            w11 = (fs * ft + 8) >> 4
            w10, w01 = ft - w11, fs - w11
            w00 = 16 - fs - ft + w11
            res = []
            for pl in planes:
                def g(i, j):
                    return pl[j * W + i] if i < W and j < H else 0
                res.append((g(js, jt) * w00 + g(js + 1, jt) * w01 + g(js, jt + 1) * w10 + g(js + 1, jt + 1) * w11
                            + 8) >> 4)
            out.append(res)
    return out


def decode_block(block, bw, bh):
    """[(r, g, b, a)] texels (0..255) of a block, row by row; magenta for an illegal block."""
    try:
        f = parse(block)
    except AstcError:
        return [(255, 0, 255, 255)] * (bw * bh)
    if "void" in f:
        return [tuple(v >> 8 for v in f["void"])] * (bw * bh)
    eps = block_endpoints(f)
    tw = texel_weights(f, bw, bh)
    small = bw * bh < 31
    out = []
    for t in range(bh):
        for s in range(bw):
            p = partition_of(f["part"], s, t, 0, f["P"], small)
            e0, e1 = eps[p]
            w = tw[t * bw + s]
            px = []
            for ch in range(4):
                wc = w[1] if f["D"] and ch == f["ccs"] else w[0]
                px.append((e0[ch] * (64 - wc) + e1[ch] * wc + 32) >> 6)
            out.append(tuple(px))
    return out


# Recolouring
LUM = (0.299, 0.587, 0.114)


def _lum(c):
    return LUM[0] * c[0] + LUM[1] * c[1] + LUM[2] * c[2]


def _requant_weight(value, levels):
    tab = WEIGHT_UNQ[levels]
    v = max(0, min(64, value))
    return min(range(levels), key=lambda i: abs(tab[i] - v))


def _colinear(e0, e1, tol=3.0):
    """e0 is e1 scaled by s (0..1) within `tol` per channel: (True, s) or (False, None)."""
    l1 = _lum(e1)
    if l1 <= 0:
        return all(c <= tol for c in e0[:3]), 0.0
    s = _lum(e0) / l1
    if s > 1.0 + 1e-6:
        return False, None
    return all(abs(e1[k] * s - e0[k]) <= tol for k in range(3)), s


def _write(f, cem, vals, clev, weights):
    """Block bytes with f's mode, grid and partitioning. Every partition is in endpoint mode `cem` with ISE values
    `vals` at `clev`, `weights` are indices in f's quantisation, and a dual-plane block's second plane goes to alpha
    (CCS 3)."""
    x, P, D, wbits = f["x"], f["P"], f["D"], f["wbits"]
    start = 17 if P == 1 else 29
    region = ((1 << (128 - wbits)) - 1) ^ ((1 << start) - 1)  # endpoints, extra mode bits, CCS
    y = x & ~region
    if P == 1:
        y = (y & ~(15 << 13)) | (cem << 13)
    else:
        y = (y & ~(0x3F << 23)) | ((cem << 2) << 23)  # low bits 00: every partition the same mode
    enc, nb = ise_encode(vals, clev)
    if start + nb > 128 - wbits - (2 if D else 0):
        raise AstcError("endpoints overflow")
    y |= enc << start
    if D:
        y |= 3 << (128 - wbits - 2)
    wenc, wn = ise_encode(weights, f["wlev"])
    if wn != wbits:
        raise AstcError("weights changed size")
    rev = int(f"{wenc:0{wn}b}"[::-1], 2) << (128 - wn)
    y = (y & ((1 << (128 - wbits)) - 1)) | rev
    return y.to_bytes(16, "little")


def recolour_block(block, fn):
    """(new bytes, how) for one block with every end colour c mapped to fn(c) (RGB 0..255, alpha kept).
    how is "same" (nothing changes), "void", "scale", "direct" or "skipped" (left as it was, for an illegal or HDR
    block or when no encoding fits).
    A dual-plane block whose second plane drives a colour channel gets one weight set for all three channels, with
    the two planes blended by that channel's share of the luminance change (exact for a luminance-driven map). Its
    second plane goes to alpha with alpha's old weights."""
    try:
        f = parse(block)
    except AstcError:
        return bytes(block), "skipped"
    if "void" in f:
        v = f["void"]
        old = tuple(ch / 257 for ch in v[:3])
        c = fn(old)
        if all(abs(c[k] - old[k]) < 0.5 for k in range(3)):
            return bytes(block), "same"
        x = f["x"] & ~(((1 << 48) - 1) << 64)
        for i in range(3):
            x |= max(0, min(65535, int(round(c[i] * 257)))) << (64 + 16 * i)
        return x.to_bytes(16, "little"), "void"
    eps = block_endpoints(f)
    new = [(tuple(fn(e0[:3])) + (e0[3],), tuple(fn(e1[:3])) + (e1[3],)) for e0, e1 in eps]
    if all(abs(o[k] - n[k]) < 0.5 for pe, pn in zip(eps, new) for o, n in zip(pe, pn) for k in range(3)):
        return bytes(block), "same"
    alpha = any(e0[3] != 255 or e1[3] != 255 for e0, e1 in eps)
    weights = list(f["weights"])
    P, D = f["P"], f["D"]
    if D and f["ccs"] != 3:  # fold the colour channel's own plane into plane 1, plane 2 becomes alpha's (old p1)
        c = f["ccs"]
        num = den = 0.0
        for e0, e1 in eps:
            d = [e1[k] - e0[k] for k in range(3)]
            tot = sum(LUM[k] * d[k] for k in range(3))
            if abs(tot) > 0.5:
                num += LUM[c] * d[c]
                den += tot
        beta = max(-1.0, min(2.0, num / den)) if den else 0.0
        unq = [WEIGHT_UNQ[f["wlev"]][w] for w in weights]
        out = []
        for a, b in zip(unq[0::2], unq[1::2]):
            out += [_requant_weight((1 - beta) * a + beta * b, f["wlev"]), _requant_weight(a, f["wlev"])]
        weights = out
    start = 17 if P == 1 else 29
    avail = 128 - start - f["wbits"] - (2 if D else 0)

    def levels(n):
        if n > 18:
            return None
        try:
            return _colour_levels(n, avail)
        except AstcError:
            return None
    # every pair one way round (dark end first), or every pair the other way (then the weights flip)
    darker_first = [_lum(n0) <= _lum(n1) + 1e-6 for n0, n1 in new]
    order = "keep" if all(darker_first) else "flip" if not any(darker_first) else "mixed"
    pairs = new if order != "flip" else [(n1, n0) for n0, n1 in new]
    w_final = weights if order != "flip" else [WEIGHT_INV[f["wlev"]][w] for w in weights]
    # base + scale: every pair on one line through black (a luminance-driven recolour's own case)
    if order != "mixed":
        lines = [_colinear(n0, n1) for n0, n1 in pairs]
        if all(ok for ok, _ in lines):
            cem = 10 if alpha else 6
            clev = levels(P * (6 if alpha else 4))
            if clev:
                vals = []
                for (n0, n1), (_, s) in zip(pairs, lines):
                    v = [quantise_colour(n1[k], clev) for k in range(3)] + [quantise_colour(256 * s, clev)]
                    if alpha:
                        v += [quantise_colour(n0[3], clev), quantise_colour(n1[3], clev)]
                    vals += v
                return _write(f, cem, vals, clev, w_final), "scale"
    # direct: a pair that would read back swapped (its light end first) is flattened to its mean
    cem = 12 if alpha else 8
    clev = levels(P * (8 if alpha else 6))
    if not clev:
        return bytes(block), "skipped"
    vals = []
    for n0, n1 in pairs:
        q = [quantise_colour(n0[0], clev), quantise_colour(n1[0], clev), quantise_colour(n0[1], clev),
             quantise_colour(n1[1], clev), quantise_colour(n0[2], clev), quantise_colour(n1[2], clev)]
        u = [COLOUR_UNQ[clev][i] for i in q]
        if u[1] + u[3] + u[5] < u[0] + u[2] + u[4]:
            mid = [(u[0] + u[1]) / 2, (u[2] + u[3]) / 2, (u[4] + u[5]) / 2]
            q = [quantise_colour(mid[k // 2], clev) for k in range(6)]
        if alpha:
            q += [quantise_colour(n0[3], clev), quantise_colour(n1[3], clev)]
        vals += q
    return _write(f, cem, vals, clev, w_final), "direct"


def recolour_region(data, start, size, fn):
    """Recolours every 16-byte block of data[start:start + size], a texture's image data (all mips, any layout).
    Returns (new bytes, {how: count})."""
    out = bytearray(data)
    counts, cache = {}, {}
    for o in range(start, start + size - 15, 16):
        blk = bytes(data[o:o + 16])
        hit = cache.get(blk)
        if hit is None:
            hit = cache[blk] = recolour_block(blk, fn)
        out[o:o + 16] = hit[0]
        counts[hit[1]] = counts.get(hit[1], 0) + 1
    return bytes(out), counts
