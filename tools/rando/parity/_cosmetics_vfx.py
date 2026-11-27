"""Effect colours: find colour values in the game's particle effects and rewrite them in place (same size).

Effect files (Effect/<name>.Nin_Ounce_NVN2.vsetb.byml.zs) are BYMLs whose "PtclBin" value is a NintendoWare Vfx3
blob (magic BFFH), stored as-is inside the decompressed BYML, so an edit to the blob is a same-size edit to the file.
I worked the format out by comparing Navi's normal
and red states and dozens of emitters. TODO: nothing of this has been seen in game yet.
- Pointers are u64 absolute blob offsets; arrays are {u64 ptr, u32 count, u32 stride}; strings point into the
  StringPool section (BFSI records at 0xA8, stride 0x28: +4 offset, +8 size, +0x18 name).
- Root at 0x1000: +0x30 the emitter-set array (stride 0x68): +0 name, +8 the emitter pointer array.
- Emitter: +0 name; +0x08 table P, +0x18 table A, +0x28 table B (pointer arrays of property entries).
- Property entry: u64 hash, u32 d = slot << 8 | size class, u32 t = value << 13 | flags | type. Type 0x0d = an
  explicit vec3 (float r, g, b, pad after the 16-byte entry); type 0x51 = a vec3 curve (extra: u64 kind, u64 keys
  pointer, u32 count, u32 stride 16, float max[3], float min[3], ...; keys are float r, g, b, t). Other types store
  the value packed in t ("compact": white and black splats): no room for a colour, left alone.
- Colour slots: table P slot 0x80 = Color0, 0x88 = Color1, 0x90 = a colour scale (HDR, (4, 2.5, 2) in Navi's red
  state), 0x58 = a point light's colour; table B slot 0x60 / 0x68 = Color0 / Color1 over the particle's life.
  Table A holds scale curves (not colours): never edited.

A colour is replaced keeping its intensity. Each value (r, g, b) becomes target * max(r, g, b), with target in 0..1,
so HDR sparks stay as bright, a grey key of a fade stays as dark, and the target's own darkness is kept.
"""
import re
import struct

VEC3, CURVE = 0x0D, 0x51


class Blob:
    def __init__(self, data):
        self.base = data.find(b"BFFH")
        if self.base < 0:
            raise ValueError("no Vfx3 blob (BFFH) in this file")
        self.d = data
        b = self.base
        nsec = self.u32(0x18)
        self.strings = {}
        for i in range(nsec):
            p = 0xA8 + 0x28 * i
            if data[b + p:b + p + 4] != b"BFSI":
                raise ValueError("Vfx3 section table not where expected")
            off, size = struct.unpack_from("<II", data, b + p + 4)
            name = data[b + p + 0x18:data.index(b"\0", b + p + 0x18)].decode()
            if name == "StringPool":
                self.pool = (off, off + size)

    def u32(self, o):
        return struct.unpack_from("<I", self.d, self.base + o)[0]

    def u64(self, o):
        return struct.unpack_from("<Q", self.d, self.base + o)[0]

    def string(self, o):
        if not self.pool[0] <= o < self.pool[1]:
            raise ValueError("a name pointer outside the string pool")
        start = self.base + o
        return self.d[start:self.d.index(b"\0", start)].decode("utf-8", "replace")

    def ptrs(self, o):
        p, n, stride = self.u64(o), self.u32(o + 8), self.u32(o + 12)
        if n and stride != 8:
            raise ValueError("unexpected pointer array stride")
        return [self.u64(p + 8 * i) for i in range(n)]

    def emitters(self):
        """[(set name, emitter name, emitter offset)] (blob offsets)."""
        root = 0x1000
        p, n, stride = self.u64(root + 0x30), self.u32(root + 0x38), self.u32(root + 0x3C)
        out = []
        for i in range(n):
            es = p + i * stride
            set_name = self.string(self.u64(es))
            for e in self.ptrs(es + 8):
                out.append((set_name, self.string(self.u64(e)), e))
        return out

    def entries(self, emitter, table):
        """{slot: (entry offset, type)} of one property table ("P", "A" or "B")."""
        at = {"P": 0x08, "A": 0x18, "B": 0x28}[table]
        out = {}
        for p in self.ptrs(emitter + at):
            d, t = self.u32(p + 8), self.u32(p + 12)
            out.setdefault(d >> 8, (p, t & 0xFF))
        return out


def _tint(rgb, target):
    m = max(rgb)
    return tuple(target[k] * m for k in range(3))


def recolour(data, groups):
    """(new bytes, counts) with every listed colour entry recoloured. `groups` is [{"sets": [names],
    "emitters": regex, "entries": ["P80", "B60", "P48:white", ...], "colour": "#rrggbb"}]. An entry is the table + slot
    in hex, and ":white" means a neutral tint of the same strength instead of the colour."""
    out = bytearray(data)
    blob = Blob(data)
    base = blob.base
    counts = {"vec3": 0, "curve": 0, "compact": 0}
    done = set()
    emitters = blob.emitters()
    for g in groups:
        target = tuple(int(g["colour"].lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
        rx = re.compile(g["emitters"])
        sets = set(g["sets"])
        hit = False
        for set_name, em_name, e in emitters:
            if set_name not in sets or not rx.fullmatch(em_name):
                continue
            hit = True
            for spec in g["entries"]:
                spec, _, mode = spec.partition(":")  # "white": a neutral tint of the same strength
                table, slot = spec[0], int(spec[1:], 16)
                ent = blob.entries(e, table).get(slot)
                if ent is None:
                    continue
                p, typ = ent
                if p in done:
                    continue
                done.add(p)
                colour = (1.0, 1.0, 1.0) if mode == "white" else target
                if typ == VEC3:
                    o = base + p + 0x10
                    struct.pack_into("<3f", out, o, *_tint(struct.unpack_from("<3f", data, o), colour))
                    counts["vec3"] += 1
                elif typ == CURVE:
                    keys, n, stride = struct.unpack_from("<QII", data, base + p + 0x18)
                    if stride != 16 or not 0 < n <= 64:
                        raise ValueError(f"{set_name}/{em_name}: unexpected colour curve layout")
                    vals = []
                    for i in range(n):
                        o = base + keys + 16 * i
                        v = _tint(struct.unpack_from("<3f", data, o), colour)
                        struct.pack_into("<3f", out, o, *v)
                        vals.append(v)
                    hdr = base + p + 0x28  # update the per-channel max/min to match the new keys
                    struct.pack_into("<3f", out, hdr, *(max(v[k] for v in vals) for k in range(3)))
                    struct.pack_into("<3f", out, hdr + 12, *(min(v[k] for v in vals) for k in range(3)))
                    counts["curve"] += 1
                else:
                    counts["compact"] += 1
        if not hit:
            raise ValueError(f"no emitter {g['emitters']!r} in sets {sorted(sets)}")
    return bytes(out), counts


def colour_values(data, sets, emitters, entries):
    """[(set, emitter, entry, values)] of the listed entries (for checks and the research notes)."""
    blob = Blob(data)
    rx = re.compile(emitters)
    out = []
    for set_name, em_name, e in blob.emitters():
        if set_name not in sets or not rx.fullmatch(em_name):
            continue
        for spec in entries:
            spec = spec.partition(":")[0]
            ent = blob.entries(e, spec[0]).get(int(spec[1:], 16))
            if ent is None:
                continue
            p, typ = ent
            if typ == VEC3:
                vals = [struct.unpack_from("<3f", data, blob.base + p + 0x10)]
            elif typ == CURVE:
                keys, n, _ = struct.unpack_from("<QII", data, blob.base + p + 0x18)
                vals = [struct.unpack_from("<3f", data, blob.base + keys + 16 * i) for i in range(n)]
            else:
                vals = "compact"
            out.append((set_name, em_name, spec, vals))
    return out
