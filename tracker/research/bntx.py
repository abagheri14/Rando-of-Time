"""BNTX texture reader (Switch / Switch 2 "Ounce") for the tracker research. It parses the header, deswizzles the
block-linear layout, decodes to RGBA (numpy) and saves as PNG.

Formats seen in the map/UI assets:
  0x2d..0x3a ASTC 4x4..12x12 (LDR)   -> tools/rando/parity/_astc.decode_block, memoised per unique block
  0x1a BC1, 0x1b BC2, 0x1c BC3, 0x1d BC4, 0x1e BC5, 0x20 BC7 -> Pillow's built-in "bcn" decoder
  0x02 R8, 0x09 R8G8, 0x0b R8G8B8A8, 0x0c B8G8R8A8 -> numpy
The channel selector (BRTI+0x58, one byte per R,G,B,A: 0 zero, 1 one, 2 R, 3 G, 4 B, 5 A) is applied after decode.

The block-linear layout is NVIDIA GOBs of 64 bytes x 8 rows (512 bytes), with `1 << (layout & 7)` GOBs stacked per
block and the blocks going left to right then down, same as on Switch 1 (the sizes in the BRTI header match that
padding exactly). The order of the 32 sixteen-byte sectors inside a GOB isn't Switch 1's though, see deswizzle().

Usage (as a script):  python tracker/research/bntx.py <romfs-relative .bntx.zs> [out.png] [--list]
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "rando", "parity"))

ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # the app sets REMAKE_ROMFS

ASTC_BLOCKS = {0x2d: (4, 4), 0x2e: (5, 4), 0x2f: (5, 5), 0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5), 0x33: (8, 6),
               0x34: (8, 8), 0x35: (10, 5), 0x36: (10, 6), 0x37: (10, 8), 0x38: (10, 10), 0x39: (12, 10),
               0x3a: (12, 12)}
BCN = {0x1a: (1, 8), 0x1b: (2, 16), 0x1c: (3, 16), 0x1d: (4, 8), 0x1e: (5, 16), 0x1f: (6, 16), 0x20: (7, 16)}
PLAIN = {0x02: 1, 0x09: 2, 0x0b: 4, 0x0c: 4}  # bytes per pixel


def romfs():
    import romtools
    return romtools.Romfs(ROMFS, os.path.join(ROOT, "original"))


def textures(d):
    """[{name, fmt, srgb, width, height, mips, block_height_log2, comp, data}] for every BRTI in a BNTX."""
    if d[:4] != b"BNTX":
        raise ValueError("not BNTX")
    nx = 0x20
    count = struct.unpack_from("<I", d, nx + 4)[0]
    infos = struct.unpack_from("<Q", d, nx + 8)[0]
    out = []
    for i in range(count):
        b = struct.unpack_from("<Q", d, infos + 8 * i)[0]
        assert d[b:b + 4] == b"BRTI"
        mips = struct.unpack_from("<H", d, b + 0x16)[0]
        fmt = struct.unpack_from("<I", d, b + 0x1C)[0]
        w, h, depth, arr, layout = struct.unpack_from("<IIIII", d, b + 0x24)
        size, _align, comp = struct.unpack_from("<III", d, b + 0x50)
        name_off = struct.unpack_from("<Q", d, b + 0x60)[0]
        nl = struct.unpack_from("<H", d, name_off)[0]
        name = d[name_off + 2:name_off + 2 + nl].decode()
        ptrs = struct.unpack_from("<Q", d, b + 0x70)[0]
        mip0 = struct.unpack_from("<Q", d, ptrs)[0]
        out.append({"name": name, "fmt": fmt >> 8, "srgb": (fmt & 0xFF) == 6, "width": w, "height": h,
                    "mips": mips, "block_height_log2": layout & 7, "comp": comp, "array": arr,
                    "data": d[mip0:mip0 + size]})
    return out


def _block_dims(fmt):
    if fmt in ASTC_BLOCKS:
        bw, bh = ASTC_BLOCKS[fmt]
        return bw, bh, 16
    if fmt in BCN:
        return 4, 4, BCN[fmt][1]
    if fmt in PLAIN:
        return 1, 1, PLAIN[fmt]
    raise NotImplementedError(f"format {fmt:#x}")


def deswizzle(tex):
    """Linear bytes (rows of blocks) of mip 0 from the block-linear layout."""
    bw, bh, bpe = _block_dims(tex["fmt"])
    W = (tex["width"] + bw - 1) // bw
    H = (tex["height"] + bh - 1) // bh
    gob_h = 1 << tex["block_height_log2"]
    # shrink the block height for small images the way the hardware does
    while gob_h > 1 and (H + 7) // 8 <= gob_h // 2:
        gob_h //= 2
    width_gobs = (W * bpe + 63) // 64
    src = np.frombuffer(tex["data"], dtype=np.uint8)
    y = np.arange(H, dtype=np.int64)[:, None]
    xb = (np.arange(W, dtype=np.int64) * bpe)[None, :]  # byte x of each element
    gob = ((y // (8 * gob_h)) * 512 * gob_h * width_gobs + (xb // 64) * 512 * gob_h
           + ((y % (8 * gob_h)) // 8) * 512)
    # The zero padding in an ASTC icon gave away the order of the 16-byte sectors: x5, y2, x4, y1, y0.
    # Textures come out clean with that order. The Switch 1 (Maxwell) order, x5, y2, y1, x4, y0,
    # scrambles them.
    addr = (gob + ((xb >> 5) & 1) * 256 + ((y >> 2) & 1) * 128 + ((xb >> 4) & 1) * 64 + ((y >> 1) & 1) * 32
            + (y & 1) * 16 + (xb % 16))
    idx = addr[..., None] + np.arange(bpe, dtype=np.int64)
    need = int(idx.max()) + 1
    if need > len(src):
        src = np.concatenate([src, np.zeros(need - len(src), np.uint8)])
    return src[idx].reshape(H, W, bpe), (bw, bh)


def _apply_comp(rgba, comp):
    sel = [(comp >> (8 * i)) & 0xFF for i in range(4)]
    if sel == [2, 3, 4, 5]:
        return rgba
    out = np.empty_like(rgba)
    for i, s in enumerate(sel):
        if s == 0:
            out[..., i] = 0
        elif s == 1:
            out[..., i] = 255
        else:
            out[..., i] = rgba[..., s - 2]
    return out


_ASTC_CACHE = {}


def decode(tex, progress=False):
    """RGBA uint8 array (height, width, 4) of mip 0."""
    fmt = tex["fmt"]
    blocks, (bw, bh) = deswizzle(tex)
    H, W, bpe = blocks.shape
    w, h = tex["width"], tex["height"]
    if fmt in PLAIN:
        px = blocks.reshape(H, W, bpe)
        rgba = np.zeros((H, W, 4), np.uint8)
        if bpe == 1:
            rgba[..., 0] = px[..., 0]
            rgba[..., 3] = 255
        elif bpe == 2:
            rgba[..., 0] = px[..., 0]
            rgba[..., 1] = px[..., 1]
            rgba[..., 3] = 255
        elif fmt == 0x0c:
            rgba = px[..., [2, 1, 0, 3]].copy()
        else:
            rgba = px.copy()
        return _apply_comp(rgba[:h, :w], tex["comp"])
    if fmt in BCN:
        from PIL import Image
        n = BCN[fmt][0]
        raw = blocks.tobytes()
        mode = "RGBA" if n not in (4, 5) else ("L" if n == 4 else "RGB")
        im = Image.frombytes(mode, (W * 4, H * 4), raw, "bcn", n)
        arr = np.array(im.convert("RGBA"))
        if n == 4:
            arr[..., 1] = arr[..., 2] = 0
        return _apply_comp(arr[:h, :w], tex["comp"])
    # ASTC: decode each unique block once
    import _astc
    flat = blocks.reshape(-1, 16)
    uniq, inverse = np.unique(flat, axis=0, return_inverse=True)
    cache = _ASTC_CACHE.setdefault((bw, bh), {})
    texels = np.empty((len(uniq), bh, bw, 4), np.uint8)
    for i, blk in enumerate(uniq):
        key = blk.tobytes()
        t = cache.get(key)
        if t is None:
            t = np.array(_astc.decode_block(key, bw, bh), np.uint8).reshape(bh, bw, 4)
            cache[key] = t
        texels[i] = t
        if progress and i % 20000 == 0:
            print(f"    {i}/{len(uniq)} unique blocks", flush=True)
    img = texels[inverse.reshape(-1)].reshape(H, W, bh, bw, 4).transpose(0, 2, 1, 3, 4).reshape(H * bh, W * bw, 4)
    return _apply_comp(img[:h, :w], tex["comp"])


def save_png(rgba, path):
    from PIL import Image
    Image.fromarray(rgba, "RGBA").save(path)


def main(argv):
    fs = romfs()
    rel = argv[0]
    d = fs.read(rel)
    texs = textures(d)
    if "--list" in argv:
        for t in texs:
            print(f"{t['name']:50} fmt={t['fmt']:#04x} srgb={t['srgb']} {t['width']}x{t['height']} "
                  f"mips={t['mips']} comp={t['comp']:#010x}")
        return
    out = argv[1] if len(argv) > 1 else os.path.join(HERE, "samples", texs[0]["name"] + ".png")
    import time
    t0 = time.time()
    save_png(decode(texs[0], progress=True), out)
    print(f"{out} ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1:])
