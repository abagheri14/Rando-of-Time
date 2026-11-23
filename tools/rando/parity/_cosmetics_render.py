"""Render a game texture (mip 0) to PNG, for checking recolours by eye: before/after pictures of cosmetics edits.

usage: python tools/rando/parity/_cosmetics_render.py ROMFS Tex/X.bntx.zs OUT.png [--name TEX] [--max 512]
       python tools/rando/parity/_cosmetics_render.py ROMFS PATCH_DIR/Tex/X.bntx.zs OUT.png   (a patched copy)
       python tools/rando/parity/_cosmetics_render.py --plan ROMFS PLAN.json OUT_DIR [--max 512]
           every texture the plan's cosmetics section changes: OUT_DIR/<name>_before.png and _after.png

Reads BNTX files with one texture or many (for the HUD's Common...bntx.zs, pick one with --name). Formats are BC1,
BC3, BC4 and ASTC (any block size, LDR). It undoes the Switch's block-linear layout (64-byte x 8-row GOBs, block
height from the texture's layout field). It's slow (pure Python, cached per distinct block), seconds to a minute
per texture. Only for checking cosmetics by hand, the patcher never imports it.
"""
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _astc  # noqa: E402
import _cosmetics_tex  # noqa: E402

ASTC_BLOCKS = _cosmetics_tex.ASTC_BLOCKS
BC = {0x1A: 8, 0x1C: 16, 0x1D: 8}  # BC1, BC3, BC4: bytes per 4x4 block


textures = _cosmetics_tex.bntx_textures


def _gob_address(x, y, width_in_gobs, bpb, block_height):
    return _cosmetics_tex.gob_address(x, y, width_in_gobs, bpb, block_height)


def _rgb565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def _bc1_colours(block, o, three_ok=True):
    c0, c1 = struct.unpack_from("<HH", block, o)
    a, b = _rgb565(c0), _rgb565(c1)
    if c0 > c1 or not three_ok:
        return [a + (255,), b + (255,), tuple((2 * a[k] + b[k]) // 3 for k in range(3)) + (255,),
                tuple((a[k] + 2 * b[k]) // 3 for k in range(3)) + (255,)]
    return [a + (255,), b + (255,), tuple((a[k] + b[k]) // 2 for k in range(3)) + (255,), (0, 0, 0, 0)]


def _bc4_values(block, o):
    a0, a1 = block[o], block[o + 1]
    if a0 > a1:
        pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        pal = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
    bits = int.from_bytes(block[o + 2:o + 8], "little")
    return [pal[(bits >> (3 * i)) & 7] for i in range(16)]


def decode_block(fmt, block):
    """[(r, g, b, a)] texels of one block, row by row."""
    if fmt in ASTC_BLOCKS:
        bw, bh = ASTC_BLOCKS[fmt]
        return _astc.decode_block(block, bw, bh)
    if fmt == 0x1A:
        pal = _bc1_colours(block, 0)
        idx = struct.unpack_from("<I", block, 4)[0]
        return [pal[(idx >> (2 * i)) & 3] for i in range(16)]
    if fmt == 0x1C:
        alpha = _bc4_values(block, 0)
        pal = _bc1_colours(block, 8, three_ok=False)
        idx = struct.unpack_from("<I", block, 12)[0]
        return [pal[(idx >> (2 * i)) & 3][:3] + (alpha[i],) for i in range(16)]
    if fmt == 0x1D:
        return [(v, v, v, 255) for v in _bc4_values(block, 0)]
    raise ValueError(f"format {fmt:#x} not supported by the renderer")


def decode(data, tex):
    """(width, height, rgba bytes) of a texture's mip 0."""
    fmt = tex["fmt"]
    bw, bh = ASTC_BLOCKS.get(fmt, (4, 4))
    bpb = 16 if fmt in ASTC_BLOCKS else BC[fmt]
    w, h = tex["w"], tex["h"]
    nx, ny = -(-w // bw), -(-h // bh)
    width_in_gobs = -(-nx * bpb // 64)
    block_height = tex["block_height"]
    while block_height > 1 and ny <= 8 * (block_height // 2):  # small surfaces use a smaller block height
        block_height //= 2
    out = bytearray(w * h * 4)
    cache = {}
    for by in range(ny):
        for bx in range(nx):
            o = tex["start"] + _gob_address(bx, by, width_in_gobs, bpb, block_height)
            blk = bytes(data[o:o + bpb])
            texels = cache.get(blk)
            if texels is None:
                texels = cache[blk] = decode_block(fmt, blk)
            for ty in range(bh):
                y = by * bh + ty
                if y >= h:
                    break
                for tx in range(bw):
                    x = bx * bw + tx
                    if x >= w:
                        break
                    p = (y * w + x) * 4
                    out[p:p + 4] = bytes(texels[ty * bw + tx])
    return w, h, bytes(out)


def _png(path, w, h, rgba, max_side=None):
    if max_side and max(w, h) > max_side:  # box-filter down to max_side (keeps the files small)
        f = -(-max(w, h) // max_side)
        nw, nh = w // f, h // f
        small = bytearray(nw * nh * 4)
        for y in range(nh):
            for x in range(nw):
                acc = [0, 0, 0, 0]
                for yy in range(y * f, y * f + f):
                    row = (yy * w + x * f) * 4
                    for xx in range(f):
                        for k in range(4):
                            acc[k] += rgba[row + 4 * xx + k]
                p = (y * nw + x) * 4
                small[p:p + 4] = bytes(v // (f * f) for v in acc)
        w, h, rgba = nw, nh, bytes(small)
    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def render(data, out_png, name=None, max_side=512):
    texs = textures(data)
    tex = texs[0] if name is None else next((t for t in texs if t["name"] == name), None)
    if tex is None:
        raise SystemExit(f"no texture named {name!r}")
    w, h, rgba = decode(data, tex)
    _png(out_png, w, h, rgba, max_side)
    return tex


def _read(romfs, path):
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    if os.path.isfile(path):
        raw = open(path, "rb").read()
        return fs.zs.decompress(raw) if path.endswith(".zs") else raw
    return fs.read(path)


def main(argv):
    max_side = 512
    if "--max" in argv:
        i = argv.index("--max")
        max_side = int(argv[i + 1])
        del argv[i:i + 2]
    if argv and argv[0] == "--plan":
        import _cosmetics_apply
        romfs, plan, out_dir = argv[1:4]
        cos = _cosmetics_apply.load([plan])
        fs, files = _cosmetics_apply.build(romfs, dict(cos, slink=[], effects=[]))
        for rel, new in sorted(files.items()):
            if new[:4] != b"BNTX":  # layouts and effects get no picture (their values are in the plan's log)
                continue
            old = fs.read(rel)
            for t in textures(new):
                o, n = t["start"], t["start"] + t["size"]
                if old[o:n] == new[o:n]:
                    continue
                base = os.path.join(out_dir, t["name"])
                render(old, base + "_before.png", t["name"], max_side)
                render(new, base + "_after.png", t["name"], max_side)
                print(f"  {t['name']}: {base}_before.png / _after.png")
        return
    name = None
    if "--name" in argv:
        i = argv.index("--name")
        name = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) != 3:
        raise SystemExit(__doc__)
    romfs, path, out_png = argv
    tex = render(_read(romfs, path), out_png, name, max_side)
    print(f"{tex['name']}: format {tex['fmt']:#x} {tex['w']}x{tex['h']} -> {out_png}")


if __name__ == "__main__":
    main(sys.argv[1:])
