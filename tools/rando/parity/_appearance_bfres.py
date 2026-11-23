"""Read-only reader for the remake's model files (BFRES v10.4, Model/<Project>.<Fmdb>.bfres.zs): materials, their
textures and the node-system options that say whether a material reads per-placement colour parameters.

Layout, worked out from the files. Offsets are from the start of the decompressed file and pointers are u64:
  header   +0x28 model array (one FMDL per file in this game)
  FMDL     +0x08 name, +0x38 material array (FMAT, 0xB0 bytes each), +0x6C u16 material count
  FMAT     +0x08 name, +0x10 shader info, +0x20 texture-name array, +0xA3 u8 texture count, +0x58 parameter data
  shader info +0x00 shader assign, +0x30 static option value strings (node-system choices)
  shader assign +0x00 archive name, +0x08 shading model, +0x10 option array (16-byte {u64 hash, u64}),
           +0x20 parameter array (24-byte {u64 0, u64 name hash, u16 offset, u16 type}),
           +0x40 static option dictionary (hashed names), +0x48 u8 option count, +0x4A u16 parameter count
Names are 64-bit hashes. Shader/ExternalBinaryString.bfres.zs lists 454 sorted hashes at 0xF0 and a dictionary of
the 454 names at 0xF20 in the same order.

Node-system materials that build their albedo from an "expression evaluate graph" carry the graph's id among their
static option strings (a long decimal number like 3461558507). The per-placement colour a level sets with
Dynamic.GameModelController_GeneralInstanceParam0..2 reaches the shader through such a graph. Every model the game
tints per placement in vanilla (lift rocks, wooden crates, candle sticks) has one, and pots and chests have none.
"""
import struct

_names = None


def _q(d, off):
    return struct.unpack_from("<Q", d, off)[0]


def _s(d, off):
    n = struct.unpack_from("<H", d, off)[0]
    return d[off + 2:off + 2 + n].decode("ascii", "replace")


def _dic_names(d, off):
    n = struct.unpack_from("<i", d, off + 4)[0]
    return [_s(d, _q(d, off + 8 + 16 * i + 8)) for i in range(1, n + 1)]


def hash_names(fs):
    """{64-bit hash: shader parameter/option name} from Shader/ExternalBinaryString.bfres.zs."""
    global _names
    if _names is None:
        d = fs.read("Shader/ExternalBinaryString.bfres.zs")
        hashes = [_q(d, 0xF0 + 8 * i) for i in range((0xF20 - 0xF0) // 8)]
        _names = dict(zip(hashes, _dic_names(d, 0xF20)))
    return _names


def materials(d):
    """[{model, material, textures, fmat}] of the file's model."""
    if d[:4] != b"FRES":
        raise ValueError("not a BFRES file")
    fm = _q(d, 0x28)
    if d[fm:fm + 4] != b"FMDL":
        raise ValueError("no model in this BFRES file")
    model = _s(d, _q(d, fm + 8))
    arr = _q(d, fm + 0x38)
    count = struct.unpack_from("<H", d, fm + 0x6C)[0]
    out = []
    for k in range(count):
        m = arr + k * 0xB0
        if d[m:m + 4] != b"FMAT":
            raise ValueError(f"no material at {m:#x}")
        texs = [_s(d, _q(d, _q(d, m + 0x20) + 8 * i)) for i in range(d[m + 0xA3])]
        out.append({"model": model, "material": _s(d, _q(d, m + 8)), "textures": texs, "fmat": m})
    return out


def option_strings(d, fmat, limit=64):
    """The material's static option values (strings), in file order."""
    info = _q(d, fmat + 0x10)
    p = _q(d, info + 0x30)
    vals = []
    for i in range(limit):
        q = _q(d, p + 8 * i)
        if q < 0x100 or q >= len(d):
            break
        try:
            vals.append(_s(d, q))
        except (struct.error, IndexError):
            break
    return vals


def graph_ids(d, fmat):
    """Expression-graph ids among the material's static options (long decimal strings)."""
    return [v for v in option_strings(d, fmat) if v.isdigit() and len(v) >= 6]


def params(fs, d, fmat):
    """{parameter name: (offset, type, 16 raw bytes of the material's value)} (type 12 float, 15 float4)."""
    names = hash_names(fs)
    sa = _q(d, _q(d, fmat + 0x10))
    count = struct.unpack_from("<H", d, sa + 0x4A)[0]
    arr, data = _q(d, sa + 0x20), _q(d, fmat + 0x58)
    out = {}
    for i in range(count):
        e = arr + 24 * i
        h = _q(d, e + 8)
        off, typ = struct.unpack_from("<HH", d, e + 16)
        out[names.get(h, f"{h:016x}")] = (off, typ, d[data + off:data + off + 16])
    return out
