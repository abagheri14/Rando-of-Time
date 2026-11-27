"""Adds textures to a many-texture BNTX (the UI's UI/Layout2Archive/Common...bntx.zs), for the map tracker's icons
(parity/_map_icons.py). Each new texture is a copy of a template texture of the same size and format with its own
name and pixels.

How the file is laid out (read off the UI's BNTX, platform "Ounc"):
  header   +0x10 u32 file name, +0x16 u16 first block (_STR), +0x18 u32 relocation table, +0x1C u32 file size
  NX       +0x24 u32 texture count, +0x28 texture pointer array, +0x30 the BRTD block, +0x38 the name dictionary
  _STR     the strings (u16 length, characters, 0), the name dictionary (_DIC) inside it
  BRTI     one per texture (0x318 bytes for most), chained by the u32 at +4 (offset to the next block; the last one's
           reaches BRTD). +0x60 name, +0x70 the mip offset array (inside the BRTI), whose entries point into BRTD.
  BRTD     the texture data, 0x1000-aligned (the header's alignment), +8 u64 its size with the 0x10-byte header
  _RLT     where every pointer is: two sections (0: pointers into the headers, 1: into BRTD), entries {u32 first
           pointer, u16 structures, u8 pointers per structure, u8 words skipped after each}
Every pointer is an absolute file offset and the relocation table lists them all, so the file can grow anywhere: we
put the new BRTIs, their names, a longer pointer array and a new dictionary after the last BRTI, move BRTD up by
whole pages, add the new pixels at its end, and write the table again.

The dictionary is Nintendo's radix tree (ResDic): node 0 is the root (bit -1, key ""), every other node tests one bit
of the name, counted from the name's last byte, low bit first. build_dic makes the game's own 878-node tree from its
names, byte for byte (check() runs that).
"""
import struct

ALIGN_DATA = 0x1000  # the header's alignment (2^12); BRTD's data starts on it
ALIGN_TEX = 0x200    # each texture's data (the game's starts are multiples of 0x200)


def _q(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def _u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def _up(x, a):
    return -(-x // a) * a


def _name(d, at):
    return d[at + 2:at + 2 + _u16(d, at)]


def pointers(d):
    """[(location, section)] of every pointer the relocation table lists."""
    r = _u32(d, 0x18)
    if d[r:r + 4] != b"_RLT":
        raise ValueError("no relocation table")
    nsec = _u32(d, r + 8)
    ent = r + 0x10 + 0x18 * nsec
    out = []
    for s in range(nsec):
        sec = r + 0x10 + 0x18 * s
        first, count = _u32(d, sec + 0x10), _u32(d, sec + 0x14)
        for e in range(first, first + count):
            o = ent + 8 * e
            at, ns, npt, pad = _u32(d, o), _u16(d, o + 4), d[o + 6], d[o + 7]
            for _ in range(ns):
                out += [(at + 8 * p, s) for p in range(npt)]
                at += 8 * (npt + pad)
    return out


def _bit(name, b):
    i = b >> 3
    return (name[len(name) - 1 - i] >> (b & 7)) & 1 if i < len(name) else 0


def _first_diff(a, b):
    for i in range(8 * max(len(a), len(b))):
        if _bit(a, i) != _bit(b, i):
            return i
    raise ValueError(f"two textures named {a!r}")


def build_dic(names):
    """[(bit, left, right, name index or -1 for the root)] of the dictionary of `names` (bytes) in this order."""
    nodes = [[-1, 0, 0, -1]]
    keys = [b""]
    for k, name in enumerate(names, 1):
        prev, cur = 0, nodes[0][1]
        while nodes[prev][0] < nodes[cur][0]:
            prev, cur = cur, nodes[cur][2] if _bit(name, nodes[cur][0]) else nodes[cur][1]
        bit = _first_diff(keys[cur], name)
        prev, cur = 0, nodes[0][1]
        while nodes[prev][0] < nodes[cur][0] and nodes[cur][0] < bit:
            prev, cur = cur, nodes[cur][2] if _bit(name, nodes[cur][0]) else nodes[cur][1]
        node = [bit, cur, k, k - 1] if _bit(name, bit) else [bit, k, cur, k - 1]
        if prev == 0:
            nodes[0][1] = k
        elif _bit(name, nodes[prev][0]):
            nodes[prev][2] = k
        else:
            nodes[prev][1] = k
        nodes.append(node)
        keys.append(name)
    return [tuple(n) for n in nodes]


def _dic_bytes(nodes, key_at):
    """The _DIC block: header and nodes, key_at(node index) -> string address."""
    out = bytearray(b"_DIC" + struct.pack("<I", len(nodes) - 1))
    for i, (bit, left, right, _) in enumerate(nodes):
        out += struct.pack("<IHHQ", bit & 0xFFFFFFFF, left, right, key_at(i))
    return bytes(out)


def textures(d):
    """[(name bytes, BRTI address)] in the file's order."""
    arr, n = _q(d, 0x28), _u32(d, 0x24)
    out = []
    for i in range(n):
        b = _q(d, arr + 8 * i)
        out.append((_name(d, _q(d, b + 0x60)), b))
    return out


def check(d):
    """[problem] if this file isn't laid out the way add_textures expects (its own dictionary rebuilt, etc.)."""
    bad = []
    if d[:4] != b"BNTX":
        return ["not a BNTX file"]
    tex = textures(d)
    dic = _q(d, 0x38)
    nodes = build_dic([n for n, _ in tex])
    if _u32(d, dic + 4) != len(tex):
        bad.append("dictionary count isn't the texture count")
    for i, (bit, left, right, _) in enumerate(nodes):
        o = dic + 8 + 0x10 * i
        if (_u32(d, o), _u16(d, o + 4), _u16(d, o + 6)) != (bit & 0xFFFFFFFF, left, right):
            bad.append(f"dictionary node {i} isn't the one the game's names make")
            break
    brtd = _q(d, 0x30)
    if d[brtd:brtd + 4] != b"BRTD" or (brtd + 0x10) % ALIGN_DATA:
        bad.append("BRTD not where expected")
    return bad


def add_textures(d, new):
    """d with new textures added. new = [(name, template name, data)]: data is the texture's bytes as stored (the
    template's size, its swizzled layout). Returns the new file's bytes."""
    bad = check(d)
    if bad:
        raise ValueError("; ".join(bad))
    tex = textures(d)
    by_name = {n: b for n, b in tex}
    ptrs = pointers(d)
    ptr_set = {loc for loc, _ in ptrs}
    rlt = _u32(d, 0x18)
    nsec = _u32(d, rlt + 8)
    sec0_end = _u32(d, rlt + 0x10 + 0x0C)
    brtd = _q(d, 0x30)
    brtd_size = _q(d, brtd + 8)
    brtd_end = brtd + brtd_size
    last = max(b for _, b in tex)
    if last + _u32(d, last + 4) != brtd:
        raise ValueError("the last BRTI doesn't chain to BRTD")
    tail = bytearray()
    t0 = _up(sec0_end, 16)
    new_ptrs = []  # (location, value, section)
    clones = []
    for name, template, data in new:
        name = name.encode() if isinstance(name, str) else name
        tb = by_name.get(template.encode() if isinstance(template, str) else template)
        if tb is None:
            raise ValueError(f"no template texture {template}")
        size = _u32(d, tb + 8)
        if len(data) != _u32(d, tb + 0x50):
            raise ValueError(f"{name!r}: {len(data)} bytes, the template holds {_u32(d, tb + 0x50)}")
        at = t0 + len(tail)
        block = bytearray(d[tb:tb + size])
        struct.pack_into("<I", block, 4, size)  # chained to the next new block (the last one is set below)
        mips = _q(d, tb + 0x70)
        if _u16(d, tb + 0x16) != 1 or not tb <= mips < tb + size:
            raise ValueError(f"template {template}: one mip with its offset inside the BRTI expected")
        for loc in range(tb, tb + size, 8):
            if loc not in ptr_set:
                continue
            v = _q(d, loc)
            if loc == mips:  # the data, filled in below
                nv, sec = None, 1
            elif tb <= v < tb + size:
                nv, sec = at + (v - tb), 0
            else:
                nv, sec = v, 0
            new_ptrs.append([at + (loc - tb), nv, sec])
        clones.append((name, at, at + (mips - tb), at + 0x60, data))
        tail += block
    strings = {}
    for name, _, _, _, _ in clones:
        tail += b"\0" * (len(tail) % 2)
        strings[name] = t0 + len(tail)
        tail += struct.pack("<H", len(name)) + name + b"\0"
    tail += b"\0" * (-len(tail) % 8)
    arr_at = t0 + len(tail)
    all_brti = [b for _, b in tex] + [c[1] for c in clones]
    tail += b"\0" * (8 * len(all_brti))
    dic_at = t0 + len(tail)
    names = [n for n, _ in tex] + [c[0] for c in clones]
    nodes = build_dic(names)
    old_dic = _q(d, 0x38)
    old_keys = [_q(d, old_dic + 8 + 0x10 * i + 8) for i in range(len(tex) + 1)]

    def key_at(i):  # the root and the game's names keep their strings, a new node names its new texture
        return old_keys[i] if i < len(old_keys) else strings[names[nodes[i][3]]]
    dic = _dic_bytes(nodes, key_at)
    tail += dic
    s0 = t0 + len(tail)
    new_brtd = _up(s0 + 0x10, ALIGN_DATA) - 0x10
    new_brtd = max(new_brtd, brtd)
    k = new_brtd - brtd
    if k % ALIGN_DATA:
        raise ValueError("BRTD must move by whole pages")
    # the new pixels at the end of BRTD
    data_tail = bytearray()
    data_end = brtd_end + k
    placed = []
    for name, at, mip_loc, _, data in clones:
        pad = _up(data_end + len(data_tail), ALIGN_TEX) - (data_end + len(data_tail))
        data_tail += b"\0" * pad
        placed.append(data_end + len(data_tail))
        data_tail += data
    new_brtd_size = brtd_size + len(data_tail)
    rlt_at = _up(new_brtd + new_brtd_size, ALIGN_DATA)

    def moved(v):
        return v + k if v >= brtd else v
    out = bytearray(d[:t0]) + tail + b"\0" * (new_brtd - s0) + d[brtd:brtd_end] + data_tail
    out += b"\0" * (rlt_at - len(out))
    final = []  # (location, value)
    for loc, _sec in ptrs:
        nloc = moved(loc)
        final.append((nloc, moved(_q(d, loc))))
    for i, (loc, v, sec) in enumerate(new_ptrs):
        final.append((loc, v))
    for (name, at, mip_loc, name_loc, _), dat in zip(clones, placed):
        final = [(l, (dat if l == mip_loc else (strings[name] if l == name_loc else v))) for l, v in final]
    for i, b in enumerate(all_brti):
        final.append((arr_at + 8 * i, moved(b) if b < brtd else b))
    for i in range(len(nodes)):
        final.append((dic_at + 8 + 0x10 * i + 8, key_at(i)))
    final = {l: v for l, v in final}
    final[0x28] = arr_at
    final[0x38] = dic_at
    final[0x30] = new_brtd
    for loc, v in final.items():
        if v is None:
            raise ValueError("a new texture's data pointer wasn't set")
        struct.pack_into("<Q", out, loc, v)
    struct.pack_into("<I", out, 0x24, len(all_brti))
    chain = [last] + [c[1] for c in clones]
    for a, b in zip(chain, chain[1:]):
        struct.pack_into("<I", out, a + 4, b - a)
    struct.pack_into("<I", out, chain[-1] + 4, new_brtd - chain[-1])
    struct.pack_into("<Q", out, new_brtd + 8, new_brtd_size)
    # the relocation table: section by the pointer's target
    locs = sorted(final)
    sections = [[l for l in locs if final[l] < new_brtd], [l for l in locs if final[l] >= new_brtd]]
    entries, sec_rows = [], []
    for s, ls in enumerate(sections):
        first = len(entries)
        i = 0
        while i < len(ls):
            j = i
            while j + 1 < len(ls) and ls[j + 1] == ls[j] + 8 and j + 1 - i < 255:
                j += 1
            entries.append(struct.pack("<IHBB", ls[i], 1, j - i + 1, 0))
            i = j + 1
        sec_rows.append(struct.pack("<QIIII", 0, 0 if s == 0 else new_brtd,
                                    s0 if s == 0 else new_brtd_size, first, len(entries) - first))
    table = b"_RLT" + struct.pack("<III", rlt_at, len(sections), 0) + b"".join(sec_rows) + b"".join(entries)
    out += table
    struct.pack_into("<I", out, 0x18, rlt_at)
    struct.pack_into("<I", out, 0x1C, len(out))
    if nsec != 2:
        raise ValueError("expected a two-section relocation table")
    return bytes(out)
