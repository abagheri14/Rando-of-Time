"""An ASTC 4x4 (LDR) encoder for the few UI textures we make ourselves, so they're stored the way the game stores
its own icons (the map tracker's icons, parity/_map_icon_art.py).

Every block is one partition with RGBA endpoints (endpoint mode 12) and a 4 x 4 weight grid, in one of two layouts,
whichever decodes closer to the source:
- one weight plane with 8 weight levels, so colour and alpha share their blend, and 192 endpoint levels;
- two weight planes (the second one for alpha) with 4 levels each, and 48 endpoint levels, for blocks where an edge
  fades out while the colour changes.
The endpoints come from the block's principal axis (alpha-weighted, so a transparent texel's colour doesn't pull
them), ordered so endpoint mode 12 never blue-contracts, then each texel takes its nearest weight. The values are
sRGB-encoded bytes, as the game's sRGB ASTC textures interpolate them. The block layout follows the Khronos Data
Format Specification's ASTC chapter, and _astc.py's decoder (built from the same chapter and checked against the
game's own textures) reads every block back in encode_image.
"""
import _astc as A

LAYOUTS = ((0, 8), (1, 4))  # (dual plane, weight levels)
_MODE = {}


def _block_mode(dual, wlev):
    """The 11-bit block mode for a 4 x 4 weight grid."""
    key = (dual, wlev)
    if key not in _MODE:
        for bm in range(2048):
            try:
                if A.block_mode(bm) == (4, 4, dual, wlev):
                    _MODE[key] = bm
                    break
            except A.AstcError:
                continue
        else:
            raise A.AstcError(f"no 4x4 block mode with dual plane {dual}, {wlev} weight levels")
    return _MODE[key]


def _axis(pts, wts):
    """The weighted mean and principal axis of the points (lists of floats)."""
    n = len(pts[0])
    tw = sum(wts) or 1.0
    mean = [sum(p[k] * w for p, w in zip(pts, wts)) / tw for k in range(n)]
    cov = [[sum((p[i] - mean[i]) * (p[j] - mean[j]) * w for p, w in zip(pts, wts)) for j in range(n)] for i in range(n)]
    axis = [1.0] * n
    for _ in range(12):
        v = [sum(cov[i][j] * axis[j] for j in range(n)) for i in range(n)]
        m = max(abs(c) for c in v)
        if m < 1e-9:
            break
        axis = [c / m for c in v]
    return mean, axis


def _ends(pts, wts):
    """Two end points along the principal axis that span the points with weight."""
    mean, axis = _axis(pts, wts)
    norm = sum(a * a for a in axis) or 1.0
    proj = [sum((p[k] - mean[k]) * axis[k] for k in range(len(mean))) / norm for p, w in zip(pts, wts) if w > 0]
    if not proj:
        return mean, mean
    lo, hi = min(proj), max(proj)
    return [mean[k] + axis[k] * lo for k in range(len(mean))], [mean[k] + axis[k] * hi for k in range(len(mean))]


def _lerp(e0, e1, w):
    return (e0 * (64 - w) + e1 * w + 32) >> 6


def _encode(texels, dual, wlev):
    """16 bytes for 16 RGBA texels (row by row) in the given layout."""
    bm = _block_mode(dual, wlev)
    nweights = 16 * (dual + 1)
    wbits = A.ise_bits(nweights, wlev)
    clev = A._colour_levels(8, 128 - 17 - wbits - (2 if dual else 0))
    cw = [(t[3] + 1) / 256 for t in texels]  # a colour only counts as much as it shows
    if dual:
        c0, c1 = _ends([list(t[:3]) for t in texels], cw)
        alphas = [t[3] for t in texels]
        e0, e1 = c0 + [min(alphas)], c1 + [max(alphas)]
    else:
        e0, e1 = _ends([list(t[:3]) + [t[3]] for t in texels], [w + 0.25 for w in cw])
    q0 = [A.quantise_colour(c, clev) for c in e0]
    q1 = [A.quantise_colour(c, clev) for c in e1]
    unq = A.COLOUR_UNQ[clev]
    if sum(unq[v] for v in q1[:3]) < sum(unq[v] for v in q0[:3]):  # mode 12 would blue-contract: swap the ends
        q0, q1 = q1, q0
    u0, u1 = [unq[v] for v in q0], [unq[v] for v in q1]
    wtab = A.WEIGHT_UNQ[wlev]
    weights = []
    for t, k in zip(texels, cw):
        if dual:
            best = min(range(wlev), key=lambda i: k * sum((_lerp(u0[c], u1[c], wtab[i]) - t[c]) ** 2 for c in range(3)))
            best_a = min(range(wlev), key=lambda i: (_lerp(u0[3], u1[3], wtab[i]) - t[3]) ** 2)
            weights += [best, best_a]
        else:
            best = min(range(wlev), key=lambda i: k * sum((_lerp(u0[c], u1[c], wtab[i]) - t[c]) ** 2 for c in range(3))
                       + (_lerp(u0[3], u1[3], wtab[i]) - t[3]) ** 2)
            weights.append(best)
    x = bm | (12 << 13)  # one partition (bits 11-12 zero), endpoint mode 12 (RGBA direct)
    vals = [q0[0], q1[0], q0[1], q1[1], q0[2], q1[2], q0[3], q1[3]]
    cbits, _ = A.ise_encode(vals, clev)
    x |= cbits << 17
    if dual:
        x |= 3 << (128 - wbits - 2)  # the second plane is alpha
    wint, nb = A.ise_encode(weights, wlev)
    for i in range(nb):  # weights fill the block from the top, bit-reversed
        if (wint >> i) & 1:
            x |= 1 << (127 - i)
    return x.to_bytes(16, "little")


def _error(texels, block):
    got = A.decode_block(block, 4, 4)
    return sum((t[3] + 1) / 256 * sum((g[c] - t[c]) ** 2 for c in range(3)) + (g[3] - t[3]) ** 2
               for t, g in zip(texels, got))


def encode_block(texels):
    """The best of the layouts for 16 RGBA texels: (16 bytes, squared error)."""
    if all(t[3] == 0 for t in texels):
        return _encode([(0, 0, 0, 0)] * 16, 0, 8), 0.0
    best = None
    for dual, wlev in LAYOUTS:
        blk = _encode(texels, dual, wlev)
        err = _error(texels, blk)
        if best is None or err < best[1]:
            best = (blk, err)
    return best


def encode_image(w, h, rgba):
    """{(bx, by): 16-byte block} of a w x h RGBA image (bytes, row by row), and the RMS error per channel."""
    out, total = {}, 0.0
    for by in range(-(-h // 4)):
        for bx in range(-(-w // 4)):
            texels = []
            for ty in range(4):
                for tx in range(4):
                    x, y = bx * 4 + tx, by * 4 + ty
                    p = 4 * (y * w + x)
                    texels.append(tuple(rgba[p:p + 4]) if x < w and y < h else (0, 0, 0, 0))
            blk, err = encode_block(texels)
            out[(bx, by)] = blk
            total += err
    rms = (total / (4 * max(1, w * h))) ** 0.5
    return out, rms
