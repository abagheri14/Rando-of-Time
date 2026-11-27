"""The map tracker's icon pictures (parity/_map_icons.py), made from the player's own game files when the patch is
built: nothing of the game ships with the randomizer.

A picture comes from one of three places:
- an item icon (UI/Tex/Icon/<actor>.bntx.zs: rupees, keys, the Gold Skulltula token, bottles, the magic bean...);
- a texture of the UI's own archive (UI/Layout2Archive/Common...bntx.zs: the song symbols OcarinaMelodyIcon_NN, the
  map's heart piece);
- a render of the object's own model (Model/<project>.<fmdb>.bfres.zs, LOD 0 of each shape, its albedo texture
  from Tex/<name>_Alb.bntx.zs): pots, rocks, trees, grass, Gossip Stones, cows... render() draws it with a small
  z-buffered rasteriser at an angle that shows it best, flat light from the top left.
Then it gets the map icons' look (I measured the game's MapIcon* textures): the picture fills about 80 of the 128
pixels, with a thick outline in the map's brown-red (105, 25, 0), and a white glow behind it that's its own
texture, a white silhouette a little bigger with a soft edge (the game's ...Sh_00 textures, BC4, read as alpha).

Stored like the game's own: the picture as ASTC 4x4 sRGB (_astc_encode) and the glow as BC4, both 128 x 128 in the
Switch 2 block-linear layout (_cosmetics_tex.gob_address, GOB height 4), so a new texture can copy the BRTI of the
map's Kokiri shop icon and its glow (_bntx_add).
"""
import math
import os
import re
import struct
import sys

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tracker", "research"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SIZE, CONTENT, LINE, GLOW = 128, 80, 5, 7
OUTLINE = (105, 25, 0)
COMMON_BNTX = "UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs"
TEMPLATE, TEMPLATE_GLOW = "MapIconKokiriShop_00", "MapIconKokiriShopSh_00"  # 128 x 128 ASTC 4x4 sRGB / BC4
SKIP_SHAPES = re.compile(r"(?i)billboard|_lod|lod_|fade|shadow|brack|occlu|collision|impostor")


def _q(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def _u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def _cstr(d, o):
    return d[o + 2:o + 2 + _u16(d, o)].decode("ascii", "replace")


# Pictures
def decode(data, name=None):
    """RGBA picture (PIL) of texture `name` (or the only one) of a BNTX."""
    import bntx
    texs = bntx.textures(data)
    t = next(t for t in texs if name is None or t["name"] == name)
    return Image.fromarray(bntx.decode(t).astype(np.uint8), "RGBA")


def _snorm10(words):
    w = words.astype(np.int64)
    out = []
    for k in range(3):
        v = (w >> (10 * k)) & 0x3FF
        out.append(np.maximum(np.where(v >= 512, v - 1024, v) / 511.0, -1.0))
    return np.stack(out, 1)


def shapes(d):
    """[(shape name, positions, uvs or None, normals or None, triangles, material texture names)] of a BFRES 10.4
    model, LOD 0. Positions are half or single floats, UVs unsigned/signed 16-bit or half floats."""
    if d[:4] != b"FRES":
        raise ValueError("not a BFRES file")
    fm = _q(d, 0x28)
    pool = _q(d, _q(d, 0xB0) + 8)
    mats = []
    for j in range(_u16(d, fm + 0x6C)):
        arr = _q(d, _q(d, fm + 0x38) + 0xB0 * j + 0x20)
        names = []
        for k in range(32):
            p = _q(d, arr + 8 * k)
            if not 0 < p < len(d) - 2:
                break
            s = _cstr(d, p)
            if not s or not s.isprintable():
                break
            names.append(s)
        mats.append(names)
    out = []
    for i in range(_u16(d, fm + 0x6A)):
        sh = _q(d, fm + 0x28) + 0x60 * i
        vb = _q(d, sh + 0x10)
        n = _u32(d, vb + 0x50)
        if not n:
            continue
        base, stride = pool + _u32(d, vb + 0x48), _u32(d, _q(d, vb + 0x38))
        rec = np.frombuffer(d, dtype=np.uint8, count=n * stride, offset=base).reshape(n, stride)
        attrs = {}
        for k in range(d[vb + 0x4C]):
            a = _q(d, vb + 8) + 0x10 * k
            attrs[_cstr(d, _q(d, a))] = (_u16(d, a + 8), _u16(d, a + 0x0C), d[a + 0x0E])

        def read(name):
            if name not in attrs or attrs[name][2] != 0:
                return None
            fmt, off, _ = attrs[name]
            col = np.ascontiguousarray(rec[:, off:off + 16])
            if fmt == 0x1505:
                return col[:, :8].copy().view("<f2").reshape(n, 4)[:, :3].astype(np.float64)
            if fmt == 0x1805:
                return col[:, :12].copy().view("<f4").reshape(n, 3).astype(np.float64)
            if fmt == 0x0E02:
                return _snorm10(col[:, :4].copy().view("<u4").ravel())
            if fmt == 0x1201:
                return col[:, :4].copy().view("<u2").reshape(n, 2).astype(np.float64) / 65535.0
            if fmt == 0x1202:
                return col[:, :4].copy().view("<i2").reshape(n, 2).astype(np.float64) / 32767.0
            if fmt == 0x1205:
                return col[:, :4].copy().view("<f2").reshape(n, 2).astype(np.float64)
            return None
        pos = read("_p0")
        if pos is None:
            continue
        mesh = _q(d, sh + 0x18)
        ifmt, icount, first = _u32(d, mesh + 0x28), _u32(d, mesh + 0x2C), _u32(d, mesh + 0x30)
        dt = np.uint16 if ifmt == 1 else np.uint32
        tris = np.frombuffer(d, dtype=dt, count=icount, offset=pool + _u32(d, mesh + 0x20)).astype(np.int64)
        tris = tris.reshape(-1, 3) + first
        tris = tris[(tris < n).all(1)]
        m = _u16(d, sh + 0x52)
        out.append((_cstr(d, _q(d, sh + 8)), pos, read("_u0"), read("_n0"), tris, mats[m] if m < len(mats) else []))
    return out


def render(fs, project, fmdb, yaw=30.0, pitch=25.0, size=320, keep=None, alpha_test=0.4, light=(-0.4, 0.8, 0.6),
           ambient=0.5):
    """RGBA picture of a model, centred and filling `size` (orthographic, yaw then pitch in degrees)."""
    d = fs.read(f"Model/{project}.{fmdb}.bfres.zs")
    texcache = {}

    def albedo(names):
        alb = next((t for t in names if t.endswith("_Alb")), None)
        if alb is None:
            return None
        if alb not in texcache:
            try:
                texcache[alb] = np.asarray(decode(fs.read(f"Tex/{alb}.bntx.zs")), dtype=np.float64) / 255.0
            except Exception:  # noqa: BLE001 - a shape without its texture is drawn grey
                texcache[alb] = None
        return texcache[alb]
    parts = [(p, uv, nr, t, albedo(tx)) for name, p, uv, nr, t, tx in shapes(d)
             if (keep is None or re.search(keep, name)) and not SKIP_SHAPES.search(name)]
    if not parts:
        raise ValueError(f"{fmdb}: nothing to draw")
    return rasterize(parts, yaw, pitch, size, alpha_test, light, ambient)


def crate_face(alb):
    """A crate's side from the crate's own plank texture (a 512 atlas of planks): planks inside, a frame of darker
    boards round the edge and a brace corner to corner, the way the crate's pieces are built."""
    t = alb[100:356, 0:256].copy()             # a block of upright planks
    board = alb[100:356, 140:176]               # one plank, 256 long
    side = board * 0.78
    flat = board.transpose(1, 0, 2)[:, ::-1] * 0.78
    w = board.shape[1]
    ys, xs = np.mgrid[0:256, 0:256]
    brace = (np.abs(xs - ys) < w * 0.6) & (xs > w) & (xs < 256 - w)
    t[brace] = flat[np.clip((xs[brace] - ys[brace]) + w // 2, 0, w - 1), xs[brace]] * 0.92
    t[:w, :] = flat
    t[-w:, :] = flat
    t[:, :w] = side
    t[:, -w:] = side
    for line in (w, 256 - w):                  # the gaps between frame and planks
        t[max(0, line - 2):line + 2, w:256 - w, :3] *= 0.55
        t[w:256 - w, max(0, line - 2):line + 2, :3] *= 0.55
    t[..., 3] = 1.0
    return t


def sign_face(alb):
    """A Gerudo hanging sign from its own texture (a 1024 atlas: the emblem board above, the red cloth below): the
    board with its emblem over a strip of the cloth."""
    board = alb[90:400, 0:500]
    cloth = alb[640:900, 60:560]
    t = np.concatenate([board, cloth[:int(board.shape[0] * 0.45)]], axis=0).copy()
    t[..., 3] = 1.0
    return t


def render_box(face, yaw=30.0, pitch=25.0, size=320, dims=(1.0, 1.0, 1.0), side=None, **kw):
    """RGBA picture of a box (`dims`: width, height, depth) whose front and back show `face` (H x W x 4, 0-1) and the
    other sides `side` (default `face`), drawn like render() draws a model."""
    corners = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]],
                       dtype=np.float64) * 0.5 * np.array(dims)
    quads = [(0, 1, 2, 3, (0, 0, -1)), (5, 4, 7, 6, (0, 0, 1)), (4, 0, 3, 7, (-1, 0, 0)), (1, 5, 6, 2, (1, 0, 0)),
             (3, 2, 6, 7, (0, 1, 0)), (4, 5, 1, 0, (0, -1, 0))]
    parts = []
    for q0, q1, q2, q3, n in quads:
        pos = corners[[q0, q1, q2, q3]]
        uv = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], dtype=np.float64)
        nrm = np.tile(np.array(n, dtype=np.float64), (4, 1))
        tex = face if n[2] != 0 or side is None else side
        parts.append((pos, uv, nrm, np.array([[0, 1, 2], [0, 2, 3]]), tex))
    return rasterize(parts, yaw, pitch, size, kw.get("alpha_test", 0.4), kw.get("light", (-0.4, 0.8, 0.6)),
                     kw.get("ambient", 0.5))


def rasterize(parts, yaw, pitch, size, alpha_test, light, ambient):
    """Draws [(positions, uvs, normals, triangles, albedo)] orthographically, yaw then pitch, filling `size`."""
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    m = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    allp = np.concatenate([p @ m.T for p, *_ in parts])
    lo, hi = allp.min(0), allp.max(0)
    scale = size * 0.92 / max(hi[0] - lo[0], hi[1] - lo[1])
    cx, cyy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    zbuf = np.full((size, size), -np.inf)
    img = np.zeros((size, size, 4))
    L = np.array(light) / np.linalg.norm(light)
    for pos, uv, nrm, tris, tex in parts:
        p = pos @ m.T
        sx, sy_ = (p[:, 0] - cx) * scale + size / 2, size / 2 - (p[:, 1] - cyy) * scale
        z = p[:, 2]
        nr = nrm @ m.T if nrm is not None else None
        for t in tris:
            x0, x1, x2 = sx[t]
            y0, y1, y2 = sy_[t]
            minx, maxx = max(0, int(math.floor(min(x0, x1, x2)))), min(size - 1, int(math.ceil(max(x0, x1, x2))))
            miny, maxy = max(0, int(math.floor(min(y0, y1, y2)))), min(size - 1, int(math.ceil(max(y0, y1, y2))))
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if minx > maxx or miny > maxy or abs(den) < 1e-9:
                continue
            xs, ys = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
            w0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
            w1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            zz = w0 * z[t[0]] + w1 * z[t[1]] + w2 * z[t[2]]
            sub = zbuf[miny:maxy + 1, minx:maxx + 1]
            ok = inside & (zz > sub)
            if not ok.any():
                continue
            if tex is not None and uv is not None:
                u = w0 * uv[t[0], 0] + w1 * uv[t[1], 0] + w2 * uv[t[2], 0]
                v = w0 * uv[t[0], 1] + w1 * uv[t[1], 1] + w2 * uv[t[2], 1]
                th, tw = tex.shape[:2]
                col = tex[np.mod(np.floor(v * th), th).astype(int), np.mod(np.floor(u * tw), tw).astype(int)]
                ok &= col[..., 3] > alpha_test
            else:
                col = np.broadcast_to(np.array([0.6, 0.6, 0.6, 1.0]), xs.shape + (4,))
            if nr is not None:
                nn = w0[..., None] * nr[t[0]] + w1[..., None] * nr[t[1]] + w2[..., None] * nr[t[2]]
                nn /= np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-9)
                shade = ambient + (1 - ambient) * np.clip(nn @ L, 0, 1)
            else:
                shade = np.ones(xs.shape)
            region = img[miny:maxy + 1, minx:maxx + 1]
            region[ok, :3] = (col[..., :3] * shade[..., None])[ok]
            region[ok, 3] = 1.0
            sub[ok] = zz[ok]
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGBA")


def lift(img, close=0, tint=None):
    """A render brightened to the icons' range (its 97th percentile to 235), colour up a quarter, an optional tint
    (multiplied), and with `close` the gaps of foliage filled (a closing of that size)."""
    if close:
        a = img.getchannel("A").filter(ImageFilter.MaxFilter(close)).filter(ImageFilter.MinFilter(close))
        img = Image.composite(img, img.filter(ImageFilter.MaxFilter(close)), img.getchannel("A"))
        img.putalpha(a)
    rgb = np.asarray(img.convert("RGB"), dtype=np.float64)
    on = np.asarray(img.getchannel("A")) > 0
    if tint is not None:
        rgb *= np.array(tint, dtype=np.float64)
    if on.any():
        rgb = np.clip(rgb * (235.0 / max(np.percentile(rgb[on], 97), 1.0)), 0, 255)
    out = Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return ImageEnhance.Color(out).enhance(1.25)


def _fit(img, box):
    a = np.asarray(img.getchannel("A"))
    ys, xs = np.nonzero(a > 24)
    img = img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    s = box / max(img.size)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def style(img, outline=True, content=CONTENT):
    """(picture, glow) at 128 x 128: the picture centred at `content` pixels with the map's outline, and the glow."""
    pic = _fit(img.convert("RGBA"), content if outline else SIZE - 2 * GLOW - 6)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(pic, ((SIZE - pic.width) // 2, (SIZE - pic.height) // 2))
    solid = canvas.getchannel("A").point(lambda v: 255 if v > 90 else 0)
    if outline:
        ring = solid.filter(ImageFilter.MaxFilter(2 * LINE + 1)).filter(ImageFilter.GaussianBlur(0.8))
        out = Image.new("RGBA", (SIZE, SIZE), OUTLINE + (0,))
        out.putalpha(ring)
        out.alpha_composite(canvas)
        edge = ring
    else:
        out, edge = canvas, solid
    glow_a = edge.point(lambda v: 255 if v > 60 else 0).filter(ImageFilter.MaxFilter(2 * GLOW + 1))
    glow = glow_a.filter(ImageFilter.GaussianBlur(2.5))
    return out, glow


# Stored form
def _bc4_block(vals):
    """8-byte BC4 block of 16 values (0..255), endpoints min and max with 6 levels between."""
    lo, hi = int(vals.min()), int(vals.max())
    if hi == lo:
        return struct.pack("<BB6s", hi, lo, b"\0" * 6)
    pal = np.array([hi, lo] + [((7 - i) * hi + i * lo) / 7 for i in range(1, 7)])
    idx = np.abs(vals[:, None] - pal[None, :]).argmin(1)
    bits = 0
    for k, v in enumerate(idx):
        bits |= int(v) << (3 * k)
    return struct.pack("<BB", hi, lo) + bits.to_bytes(6, "little")


def _swizzle(blocks, nx, ny, bpb, block_height=4):
    """{(bx, by): bytes} -> the surface bytes in the Switch 2 block-linear layout."""
    import _cosmetics_tex as T
    width_in_gobs = -(-nx * bpb // 64)
    size = -(-ny // (8 * block_height)) * 512 * block_height * width_in_gobs
    out = bytearray(size)
    for (x, y), blk in blocks.items():
        a = T.gob_address(x, y, width_in_gobs, bpb, block_height)
        out[a:a + bpb] = blk
    return bytes(out)


def encode_picture(img):
    """The picture as the template stores its own: ASTC 4x4, 128 x 128, block-linear."""
    import _astc_encode as E
    blocks, _rms = E.encode_image(SIZE, SIZE, img.convert("RGBA").tobytes())
    return _swizzle(blocks, SIZE // 4, SIZE // 4, 16)


def encode_glow(alpha):
    """The glow as the template glow stores its own: BC4 (one channel: the game reads it as white with this alpha)."""
    a = np.asarray(alpha.convert("L"), dtype=np.int64)
    blocks = {}
    for by in range(SIZE // 4):
        for bx in range(SIZE // 4):
            blocks[(bx, by)] = _bc4_block(a[4 * by:4 * by + 4, 4 * bx:4 * bx + 4].ravel())
    return _swizzle(blocks, SIZE // 4, SIZE // 4, 8)
