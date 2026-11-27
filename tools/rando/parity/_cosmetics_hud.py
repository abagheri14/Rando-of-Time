"""HUD colours for the hearts and the magic meter, rewritten in place (same size) in the HUD's files.

- Textures: UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs, one BNTX with 878 textures (244 MB
  decompressed). The full heart (HeartW_00_ASTC4x4), its glows and sparkles and the magic meter's fill, glows,
  flash and sparkles are coloured ASTC textures (the layout draws them untinted). We recolour them block by block
  like the tunics (_cosmetics_tex, the selected colours go to the target at their brightness against a reference).
- Layout colours: UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.blarc.zs, a SARC of .buil layouts. Each one
  is stored 4 times under the same name, byte-identical. We don't know which copy the game reads, so all 4 get
  edited. Never round-trip it through romtools.sarc_files, which keeps only one. A layout's colour table is float32
  RGBA, 16 bytes an entry. Pointer, count and stride are at .buil+0x2C0 (the UIL block at 0xF8, +0x1C8), with the
  pointer counted from the .buil's start. Panes name their colours by index. We use the low-health heart outline
  and the magic meter's glow particles, and each is the only user of its entry.
Who uses what (I searched every layout of the archive): the heart textures are read by the HUD heart gauges
(PaHeartGaugeChildGauge_00 / NoGauge_00 / Born_00) and the file-select hearts (PaDataFileHeart_00), which is what
OoTR's heart colour covers. The magic textures are read by PaMpGauge_00 only.

ops (the plan's cosmetics "hud" list):
  {"kind": "texture", "name": "HeartW_00_ASTC4x4", "select": "heart", "ref": "HeartW_00_ASTC4x4", "colour": "#.."}
  {"kind": "layout_colour", "layout": "PaMpGauge_00", "index": 2, "was": [r, g, b], "colour": "#.."}
      the entry's RGB becomes colour * max(was) (alpha kept); "was" guards against a changed file
"""
import struct

import _cosmetics_tex as T

BNTX = "UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs"
BLARC = "UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.blarc.zs"
COLOUR_TABLE = 0x2C0  # .buil offset of the colour table's {u64 pointer, u32 count, u32 stride}


def sarc_entries(data):
    """[(name, start, end)] of every SARC entry, duplicates included."""
    if data[:4] != b"SARC":
        raise ValueError("not a SARC archive")
    data_off = struct.unpack_from("<I", data, 0x0C)[0]
    if data[0x14:0x18] != b"SFAT":
        raise ValueError("SARC without SFAT")
    n = struct.unpack_from("<H", data, 0x1A)[0]
    names = 0x20 + 0x10 * n + 8
    out = []
    for i in range(n):
        _h, attr, s, e = struct.unpack_from("<IIII", data, 0x20 + 0x10 * i)
        at = names + (attr & 0xFFFFFF) * 4
        out.append((data[at:data.index(b"\0", at)].decode(), data_off + s, data_off + e))
    return out


def layout_colour_offsets(data, layout, index):
    """Offsets of colour entry `index` in every copy of `layout`."""
    out = []
    for name, start, end in sarc_entries(data):
        if name != layout + ".buil":
            continue
        if data[start:start + 4] != b"BFFH":
            raise ValueError(f"{layout}: not a BFFH layout")
        ptr, count, stride = struct.unpack_from("<QII", data, start + COLOUR_TABLE)
        if stride != 16 or not 0 <= index < count or start + ptr + 16 * count > end:
            raise ValueError(f"{layout}: colour table not as expected")
        out.append(start + ptr + 16 * index)
    if len(out) != 4:
        raise ValueError(f"{layout}: {len(out)} copies in the archive, expected 4")
    return out


def build(fs, ops):
    """{romfs path: new decompressed bytes} for the HUD ops."""
    files = {}
    tex_ops = [op for op in ops if op["kind"] == "texture"]
    if tex_ops:
        data = fs.read(BNTX)
        out = bytearray(data)
        texs = {t["name"]: t for t in T.bntx_textures(data)}
        refs = {}
        for op in tex_ops:
            t = texs.get(op["name"])
            if t is None:
                raise ValueError(f"no HUD texture {op['name']}")
            w = T.selection(op["select"])
            key = (op["ref"], op["select"])
            if key not in refs:
                r = texs[op["ref"]]
                refs[key] = T.mean_selected(data[r["start"]:r["start"] + r["size"]], w,
                                            region=dict(r, start=0))[1]
            if t["fmt"] not in T.ASTC_FORMATS:  # each block is recoloured by itself, so no position needed
                raise ValueError(f"HUD texture {op['name']} isn't ASTC")
            a, b = t["start"], t["start"] + t["size"]
            new, _ = T.recolour_any(bytes(out[a:b]), T.select_map(T.hex_rgb(op["colour"]), refs[key], w),
                                    region=dict(t, start=0))
            out[a:b] = new
        files[BNTX] = bytes(out)
    lay_ops = [op for op in ops if op["kind"] == "layout_colour"]
    if lay_ops:
        data = fs.read(BLARC)
        out = bytearray(data)
        for op in lay_ops:
            target = [v / 255 for v in T.hex_rgb(op["colour"])]
            for o in layout_colour_offsets(data, op["layout"], op["index"]):
                was = struct.unpack_from("<3f", data, o)
                if any(abs(a - b) > 0.002 for a, b in zip(was, op["was"])):
                    raise ValueError(f"{op['layout']} colour #{op['index']} is {was}, expected {op['was']}")
                m = max(was)
                struct.pack_into("<3f", out, o, *(c * m for c in target))
        files[BLARC] = bytes(out)
    return files
