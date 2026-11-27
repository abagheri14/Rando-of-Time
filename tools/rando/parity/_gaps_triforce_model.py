"""Triforce Hunt's piece model, one golden triangle cut from the game's 3D Triforce (parity/_gaps_triforce.py).

Which Triforce (I surveyed every model):
  Model/Obj_TimeTemple_TriforceRelief_A.Obj_TimeTemple_TriforceRelief_A_01.bfres.zs, the Temple of Time's gold
  Triforce relief (its own actor, Obj_TimeTemple_TriforceRelief_A_01). It's one shape (Low4__toki_try_01, material
  toki_try_01: plain brushed-gold triangles in Tex/toki_try_01_Alb, a glow map _Emm, normal and roughness maps),
  48 vertices, 30 faces, 1.28 x 1.07 m and 5 cm thick. Each triangle is a closed solid by itself: its front face,
  three bevel quads (the bevel strips are cut where the triangles touch) and a three-face back.

The piece model is a same-size copy of that file (make_patch "new_files": same-length renames plus byte edits).
  - The index buffer holds the top triangle's 10 faces plus 2 faces closing the corners where it touched the other
    two (the bevels' back corners differ there), so the piece is a closed solid from any side. The rest of the
    buffer is zeroed, and the mesh's index count and its one sub-mesh range say 36.
  - Every vertex position is moved so the piece's bounding box is centred on the origin, and scaled by PIECE_SCALE.
    The scale is uniform so the normals and tangents stay right. That makes it about the Light Medallion's size,
    which is what the get scene held up before (ActorInfo Item_Medal_Light: 0.36 x 0.37 m).
  - The shape's bounding boxes (whole shape, sub-mesh) and bounding sphere follow.
  - The model's names say its own file name: FmdbName FMDB in the same project (Obj_TimeTemple_TriforceRelief_A),
    so the project's material animation file (Obj_TimeTemple_TriforceRelief_A.anim, its Glow) still matches.
  - Its glow. In game a probe with the relief's material came out dark brown and matte. In the relief's shader graph
    (material option 3393472422) the glow is the _Emm map (1.0 on the bevels and edges, 0.5 in the middle of each
    face) times ns_param_color5 times ns_emission_intensity. The fire arrow's metal head (Item_Arrow_Fire
    Mt_Item_Arrow_Metal, the same graph) differs from the relief's material only in those two, its fire orange
    (0.77, 0.18, 0.01) at 3.0 where the relief has white at 1.0. The relief's actor holds that glow at 0 until the
    Temple of Time lights it (its AI reads the logic bool isLit and plays AS Glow or Unlit, and Glow ramps
    ns_emission_intensity 0 -> 1 over 60 frames), so a relief copy is dark. The piece's material glows GLOW_COLOUR,
    the Light Arrow's gold (Item_Arrow_Light Mt_Item_Arrow_Light ns_param_color0), at GLOW_INTENSITY (1.5 on the
    rim, 0.75 mid-face; the fire arrow's peak is 2.3) in any room, and no display of the piece plays the relief's
    Glow animation.
    Offline renders (same room light, though the game's renderer differs) put the white x 1.0 default near white,
    the gold token's paler gold (1.0, 0.64, 0.16) near cream from 1.5 up, and the Heart Container frame's blue-less
    gold (0.9, 0.55, 0) at lemon. The Light Arrow's stays gold and glows from about 1.1.
  - The two corner faces get their own vertices (6 of the 28 unused vertex slots, same positions) with the face's
    own normal, the front face's tangent, and UVs just inside the front face's corner of the texture (gold, glow
    1.0). Borrowed vertices stretched the whole texture across them, grey parts included.
Layout (BFRES 10.4, read off the file; offsets from the start of the decompressed file, pointers u64):
  header +0x28 FMDL; +0xB0 memory-pool info {u32 flags, u32 size, u64 offset}
  FMDL +0x08 name, +0x20 FVTX array, +0x28 FSHP array (0x60 each), +0x38 FMAT array (0xB0 each), +0x6A u16 shape
       count, +0x6C u16 material count
  FMAT +0x10 shader info (+0x00 shader assign: +0x20 parameter array of {u64 0, u64 name hash, u16 offset, u16 type},
       +0x4A u16 parameter count), +0x58 parameter data (type 12 float, 15 float4)
  FVTX +0x08 attribute array (0x10 each: u64 name, u16 format, u16 offset at +0x0C), +0x30 buffer sizes,
       +0x38 strides (0x10 each), +0x48 u32 buffer offset in the pool, +0x4C u8 attribute count, +0x50 u32 vertices
  FSHP +0x08 name, +0x10 FVTX, +0x18 mesh array (0x38 each), +0x38 bounding boxes (6 floats: centre, half size;
       the shape's then each sub-mesh's), +0x40 bounding sphere (centre, radius), +0x5B u8 mesh count
  mesh +0x00 sub-mesh array ({u32 byte offset, u32 count}), +0x20 u32 index offset in the pool, +0x24 primitive
       (3 triangles), +0x28 index format (1 u16), +0x2C u32 index count, +0x30 u32 first vertex, +0x34 u16 sub-meshes
  _p0 (position) format 0x1505: four half floats (x, y, z, 1); _n0 (normal) and _t0 (tangent) 0x0E02: 10-10-10-2
  signed normalised (x, y, z, w); _u0 (UV) 0x1201: two unsigned normalised 16-bit values
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

PROJECT = "Obj_TimeTemple_TriforceRelief_A"
SRC_FMDB = "Obj_TimeTemple_TriforceRelief_A_01"
FMDB = "Obj_TimeTemple_TriforceRelief_A_P1"  # same length as SRC_FMDB (a same-size copy: pooled names keep their place)
SRC = f"Model/{PROJECT}.{SRC_FMDB}.bfres.zs"
MODEL = f"Model/{PROJECT}.{FMDB}.bfres.zs"
RENAME = [[f"{PROJECT}.{SRC_FMDB}", f"{PROJECT}.{FMDB}"], [SRC_FMDB, FMDB]]
PIECE_SCALE = 0.62  # 0.41 x 0.36 x 0.03 m: the medallion's height (a triangle of its width would look smaller)
TOP_SHARE = 0.45  # the top triangle's faces: centroid above this share of the Triforce's height (others <= 0.35)
PIECE_FACES = 12  # its 10 faces and the 2 closing its lower corners
CORNER_FACES = 2  # the last faces of the index buffer: the ones closing the corners (vertices of their own)
GLOW_INTENSITY = 1.5  # ns_emission_intensity (the relief's 1.0; the fire arrow's metal head 3.0)
GLOW_COLOUR = (1.0, 0.45, 0.032, 1.0)  # ns_param_color5: the Light Arrow's gold (the relief's white)
# the material parameters of the glow: name hash (Shader/ExternalBinaryString.bfres) and type (12 float, 15 float4)
GLOW_PARAMS = {"ns_emission_intensity": (0xF686DFDEF5207CB8, 12), "ns_param_color5": (0xF98173481C0CBF24, 15)}
CORNER_UV = ((0.04, 0.04), (0.08, 0.04), (0.04, 0.08))  # barycentric weights for the two farther UVs
# CORNER_UV's base UV is the nearest corner of the front face.
VERTEX_FORMATS = {"_p0": (0x1505, 0), "_n0": (0x0E02, 8), "_t0": (0x0E02, 12), "_u0": (0x1201, 16)}

if len(FMDB) != len(SRC_FMDB):
    raise RuntimeError("the piece model's name must keep the source name's length")


class ModelError(Exception):
    pass


def _q(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def _u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def _str(d, o):
    n = _u16(d, o)
    return d[o + 2:o + 2 + n].decode("ascii", "replace")


def layout(d):
    """The one shape's offsets and values this module reads and writes."""
    if d[:4] != b"FRES" or _u32(d, 8) != 0x000A0400:
        raise ModelError("not a BFRES 10.4 file")
    fm = _q(d, 0x28)
    mp = _q(d, 0xB0)
    pool = _q(d, mp + 8)
    if d[fm:fm + 4] != b"FMDL" or _u16(d, fm + 0x6A) != 1:
        raise ModelError("expected one model with one shape")
    sh = _q(d, fm + 0x28)
    vb = _q(d, sh + 0x10)
    if d[sh:sh + 4] != b"FSHP" or d[vb:vb + 4] != b"FVTX" or d[sh + 0x5B] != 1:
        raise ModelError("expected one shape with one mesh")
    mesh = _q(d, sh + 0x18)
    attrs = {}
    for i in range(d[vb + 0x4C]):
        a = _q(d, vb + 0x08) + 0x10 * i
        attrs[_str(d, _q(d, a))] = (_u16(d, a + 8), _u16(d, a + 0x0C))
    for name, want in VERTEX_FORMATS.items():
        if attrs.get(name) != want:
            raise ModelError(f"vertex attribute {name} is {attrs.get(name)}, want (format, offset) {want}")
    sub = _q(d, mesh)
    n_sub = _u16(d, mesh + 0x34)
    if _u32(d, mesh + 0x24) != 3 or _u32(d, mesh + 0x28) != 1 or n_sub != 1 or _u32(d, mesh + 0x30) != 0:
        raise ModelError("expected one u16 triangle list in one sub-mesh from vertex 0")
    return {"shape": sh, "shape_name": _str(d, _q(d, sh + 8)), "mesh": mesh, "sub": sub,
            "bounds": _q(d, sh + 0x38), "sphere": _q(d, sh + 0x40),
            "count": _u32(d, vb + 0x50), "stride": _u32(d, _q(d, vb + 0x38)),
            "vbuf": pool + _u32(d, vb + 0x48), "ibuf": pool + _u32(d, mesh + 0x20),
            "icount": _u32(d, mesh + 0x2C), "isize": _u32(d, _q(d, mesh + 0x18)),
            "name": _str(d, _q(d, fm + 8))}


def material_params(d):
    """{name: file offset of its value} of GLOW_PARAMS in the model's one material (name hash and type checked)."""
    fm = _q(d, 0x28)
    fmat = _q(d, fm + 0x38)
    if _u16(d, fm + 0x6C) != 1 or d[fmat:fmat + 4] != b"FMAT":
        raise ModelError("expected one material")
    sa = _q(d, _q(d, fmat + 0x10))
    arr, data = _q(d, sa + 0x20), _q(d, fmat + 0x58)
    found = {}
    for i in range(_u16(d, sa + 0x4A)):
        off, typ = struct.unpack_from("<HH", d, arr + 24 * i + 16)
        found[_q(d, arr + 24 * i + 8)] = (data + off, typ)
    out = {}
    for name, (h, typ) in GLOW_PARAMS.items():
        if found.get(h, (0, None))[1] != typ:
            raise ModelError(f"the material has no {name} of type {typ}")
        out[name] = found[h][0]
    return out


def glow(d):
    """(ns_emission_intensity, ns_param_color5) as the model's material holds them."""
    at = material_params(d)
    return (struct.unpack_from("<f", d, at["ns_emission_intensity"])[0],
            struct.unpack_from("<4f", d, at["ns_param_color5"]))


def _snorm10(word):
    """[x, y, z, w] of a 10-10-10-2 signed normalised word."""
    out = []
    for k in range(3):
        v = (word >> (10 * k)) & 0x3FF
        out.append(max((v - 1024 if v >= 512 else v) / 511.0, -1.0))
    w = (word >> 30) & 3
    return out + [w - 4 if w >= 2 else w]


def _pack_snorm10(xyz, w_bits):
    word = w_bits << 30
    for k in range(3):
        word |= (int(round(max(-1.0, min(1.0, float(xyz[k]))) * 511)) & 0x3FF) << (10 * k)
    return word


def vertex_records(d, lay):
    """(normals, tangents, uvs, raw normal words, raw tangent words) of every vertex (numpy arrays)."""
    import numpy as np
    n, s = lay["count"], lay["stride"]
    rec = np.frombuffer(d, dtype=np.uint8, count=n * s, offset=lay["vbuf"]).reshape(n, s)
    nw = rec[:, 8:12].copy().view("<u4").ravel()
    tw = rec[:, 12:16].copy().view("<u4").ravel()
    uv = rec[:, 16:20].copy().view("<u2").reshape(n, 2).astype(np.float64) / 65535.0
    return (np.array([_snorm10(int(x))[:3] for x in nw]), np.array([_snorm10(int(x))[:3] for x in tw]), uv, nw, tw)


def _face_normal(p, t):
    import numpy as np
    c = np.cross(p[t[1]] - p[t[0]], p[t[2]] - p[t[0]])
    return c / np.linalg.norm(c)


def _front_face(p, tris):
    """The face facing +z (the piece's front: one triangle)."""
    fronts = [t for t in tris if _face_normal(p, t)[2] > 0.99]
    if len(fronts) != 1:
        raise ModelError(f"{len(fronts)} faces face +z, want the one front face")
    return list(fronts[0])


def positions(d, lay):
    import numpy as np
    raw = np.frombuffer(d, dtype=np.float16, count=lay["count"] * lay["stride"] // 2, offset=lay["vbuf"])
    return raw.reshape(lay["count"], lay["stride"] // 2)[:, :3].astype(np.float64)


def faces(d, lay, count=None):
    import numpy as np
    n = lay["icount"] if count is None else count
    return np.frombuffer(d, dtype=np.uint16, count=n, offset=lay["ibuf"]).astype(np.int64).reshape(-1, 3)


def _weld(p):
    ids, out = {}, []
    for v in p:
        out.append(ids.setdefault(tuple(round(float(c), 4) for c in v), len(ids)))
    return out


def open_edges(tris, p):
    """Directed edges (welded by position) whose reverse no face has. A closed solid has none."""
    w = _weld(p)
    edges = [(w[a], w[b]) for t in tris for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))]
    have = set(edges)
    return [e for e in edges if (e[1], e[0]) not in have], w


def piece_faces(p, tris):
    """The top triangle's faces, and the faces closing its open corners (each a loop of three open edges, closed
    with the opposite winding so it faces out like its neighbours)."""
    top = [t for t in tris if p[t, 1].mean() > TOP_SHARE * p[:, 1].max()]
    open_, w = open_edges(top, p)
    nxt = {a: b for a, b in open_}
    if len(nxt) != len(open_):
        raise ModelError("the top triangle's open edges don't form simple loops")
    index_of = {}
    for t in top:  # a vertex index per welded position, from the faces that use it
        for i in t:
            index_of.setdefault(w[i], int(i))
    extra, seen = [], set()
    for a in nxt:
        if a in seen:
            continue
        loop = [a]
        while nxt[loop[-1]] != a:
            loop.append(nxt[loop[-1]])
            if len(loop) > 3:
                raise ModelError("an open corner of the top triangle isn't a single missing face")
        seen.update(loop)
        if len(loop) != 3:
            raise ModelError("an open corner of the top triangle isn't a single missing face")
        extra.append([index_of[loop[2]], index_of[loop[1]], index_of[loop[0]]])  # reversed: faces out
    return [list(map(int, t)) for t in top] + extra


def build(src):
    """(edits, info). edits are the byte edits that make the piece model from the decompressed source model `src`, each
    {"offset", "expect", "bytes"} with hex strings of equal length. info is what they make, for the read-back."""
    import numpy as np
    d = bytes(src)
    lay = layout(d)
    p = positions(d, lay)
    tris = faces(d, lay)
    piece = piece_faces(p, tris)
    if len(piece) != PIECE_FACES:
        raise ModelError(f"the top triangle has {len(piece)} faces, not {PIECE_FACES}")
    if open_edges(piece, p)[0]:
        raise ModelError("the piece is not a closed solid")
    used = sorted({i for t in piece for i in t})
    lo, hi = p[used].min(0), p[used].max(0)
    centre = (lo + hi) / 2
    new_p = (p - centre) * PIECE_SCALE
    half = new_p[used].astype(np.float16).astype(np.float64)  # as the file will hold them
    lo, hi = half.min(0), half.max(0)
    box_c, box_h = (lo + hi) / 2, (hi - lo) / 2
    radius = float(np.sqrt(((half - box_c) ** 2).sum(1)).max())
    edits = []

    def put(off, new):
        old = d[off:off + len(new)]
        if old != new:
            edits.append({"offset": off, "expect": old.hex(), "bytes": new.hex()})

    vb = bytearray(d[lay["vbuf"]:lay["vbuf"] + lay["count"] * lay["stride"]])
    for i, v in enumerate(new_p.astype(np.float16)):
        vb[i * lay["stride"]:i * lay["stride"] + 6] = v.tobytes()
    piece, corner_slots = _corner_vertices(d, lay, p, piece, vb)
    put(lay["vbuf"], bytes(vb))
    idx = np.array(piece, dtype=np.uint16).ravel().tobytes()
    put(lay["ibuf"], idx + bytes(lay["icount"] * 2 - len(idx)))
    n = len(piece) * 3
    put(lay["mesh"] + 0x2C, struct.pack("<I", n))
    put(lay["sub"], struct.pack("<II", 0, n))
    box = struct.pack("<6f", *box_c, *box_h)
    put(lay["bounds"], box + box)  # the shape's box, then its one sub-mesh's
    put(lay["sphere"], struct.pack("<4f", *box_c, radius))
    at = material_params(d)
    put(at["ns_emission_intensity"], struct.pack("<f", GLOW_INTENSITY))
    put(at["ns_param_color5"], struct.pack("<4f", *GLOW_COLOUR))
    info = {"faces": piece, "vertices": sorted(set(used) | set(corner_slots)), "index_count": n,
            "min": [float(x) for x in lo], "max": [float(x) for x in hi], "radius": radius, "scale": PIECE_SCALE,
            "source_centre": [float(x) for x in centre], "corner_vertices": corner_slots,
            "glow": [GLOW_INTENSITY, list(GLOW_COLOUR)]}
    return edits, info


def _corner_vertices(d, lay, p, piece, vb):
    """Gives the corner faces (the last CORNER_FACES of `piece`) their own vertices, in unused slots of the vertex
    buffer `vb` (a bytearray with the positions already written). Each slot takes its source vertex's whole record, then
    gets the face's own normal, the front face's tangent, and UVs just inside the nearest corner of the front face's UV
    triangle (CORNER_UV).
    Returns (faces with the corner faces renumbered, the slots used)."""
    import numpy as np
    normals, _, uv, nw, _ = vertex_records(d, lay)
    s = lay["stride"]
    body, corners = [list(t) for t in piece[:-CORNER_FACES]], piece[-CORNER_FACES:]
    taken = {i for t in piece for i in t}
    free = [i for i in range(lay["count"]) if i not in taken]
    if len(free) < 3 * CORNER_FACES:
        raise ModelError("not enough unused vertices for the corner faces")
    front = _front_face(p, body)
    if np.dot(_face_normal(p, front), normals[front].mean(0)) < 0.9:
        raise ModelError("the front face's winding doesn't match its normals")
    slots = []
    for t in corners:
        n = _face_normal(p, t)
        if np.dot(n, normals[list(t)].mean(0)) <= 0:
            raise ModelError("a corner face faces inwards")
        c = min(front, key=lambda i: float(np.linalg.norm(p[i] - p[list(t)].mean(0))))
        o1, o2 = [i for i in front if i != c]
        new = []
        for k, (a, b) in zip(t, CORNER_UV):
            slot = free.pop(0)
            rec = bytearray(vb[k * s:(k + 1) * s])
            struct.pack_into("<I", rec, 8, _pack_snorm10(n, (int(nw[k]) >> 30) & 3))
            rec[12:16] = vb[c * s + 12:c * s + 16]  # the front face's tangent
            u, v = (1 - a - b) * uv[c] + a * uv[o1] + b * uv[o2]
            struct.pack_into("<HH", rec, 16, int(round(u * 65535)), int(round(v * 65535)))
            vb[slot * s:(slot + 1) * s] = rec
            new.append(slot)
        slots += new
        body.append(new)
    return body, slots


def apply(src, edits):
    d = bytearray(src)
    for e in edits:
        o, old, new = e["offset"], bytes.fromhex(e["expect"]), bytes.fromhex(e["bytes"])
        if len(old) != len(new) or d[o:o + len(old)] != old:
            raise ModelError(f"byte edit at {o:#x} doesn't match the source")
        d[o:o + len(new)] = new
    return bytes(d)


def plan(romfs):
    """(new_files op, info) for make_patch."""
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    edits, info = build(fs.read(SRC))
    return {"to": MODEL, "from": SRC, "rename": RENAME, "bytes": edits}, info


def verify(data, info=None):
    """Problems with a built piece model (decompressed). Checks its names, that it's one closed triangle of the expected
    faces centred on the origin, and its index buffer, counts and bounds."""
    import numpy as np
    bad = []
    try:
        lay = layout(data)
    except ModelError as e:
        return [f"{MODEL}: {e}"]
    if lay["name"] != FMDB:
        bad.append(f"{MODEL}: model name {lay['name']}, want {FMDB}")
    if f"{PROJECT}.{FMDB}" != _str(data, _q(data, 0x20)):
        bad.append(f"{MODEL}: file name {_str(data, _q(data, 0x20))}, want {PROJECT}.{FMDB}")
    n = lay["icount"]
    if n != PIECE_FACES * 3 or struct.unpack_from("<II", data, lay["sub"]) != (0, n):
        bad.append(f"{MODEL}: index count {n} / sub-mesh {struct.unpack_from('<II', data, lay['sub'])}, "
                   f"want {PIECE_FACES * 3}")
        return bad
    p = positions(data, lay)
    tris = faces(data, lay)
    if tris.max() >= lay["count"]:
        bad.append(f"{MODEL}: an index past the vertex buffer")
        return bad
    if open_edges(tris, p)[0]:
        bad.append(f"{MODEL}: the piece is not a closed solid")
    used = sorted({int(i) for t in tris for i in t})
    lo, hi = p[used].min(0), p[used].max(0)
    if np.abs((lo + hi) / 2).max() > 2e-3:
        bad.append(f"{MODEL}: not centred on its origin ({(lo + hi) / 2})")
    size = hi - lo
    if not (0.3 < size[0] < 0.5 and 0.25 < size[1] < 0.45 and size[2] < 0.06):
        bad.append(f"{MODEL}: size {size} is not an item's")
    front = [t for t in tris if np.cross(p[t[1]] - p[t[0]], p[t[2]] - p[t[0]])[2] > 0.01]
    if not front or any(p[t, 2].min() < hi[2] - 1e-3 for t in front[:1]):
        bad.append(f"{MODEL}: no front face")
    box = struct.unpack_from("<12f", data, lay["bounds"])
    c, h = np.array(box[:3]), np.array(box[3:6])
    if np.abs(c - (lo + hi) / 2).max() > 1e-3 or np.abs(h - size / 2).max() > 1e-3 or box[:6] != box[6:]:
        bad.append(f"{MODEL}: bounding boxes {box} don't match the vertices")
    sph = struct.unpack_from("<4f", data, lay["sphere"])
    if np.sqrt(((p[used] - np.array(sph[:3])) ** 2).sum(1)).max() > sph[3] + 1e-3:
        bad.append(f"{MODEL}: bounding sphere {sph} doesn't hold the vertices")
    if any(data[lay["ibuf"] + n * 2:lay["ibuf"] + lay["isize"]]):
        bad.append(f"{MODEL}: index buffer past the piece's faces isn't cleared")
    try:
        intensity, colour = glow(data)
    except ModelError as e:
        bad.append(f"{MODEL}: {e}")
    else:
        if abs(intensity - GLOW_INTENSITY) > 1e-6 or any(abs(a - b) > 1e-6 for a, b in zip(colour, GLOW_COLOUR)):
            bad.append(f"{MODEL}: glow {intensity} x {colour}, want {GLOW_INTENSITY} x {GLOW_COLOUR}")
    # the corner faces need their own vertices, with the face's normal and UVs inside the front face's (gold) triangle
    normals, _, uv, _, _ = vertex_records(data, lay)
    body = [[int(i) for i in t] for t in tris[:-CORNER_FACES]]
    corners = [[int(i) for i in t] for t in tris[-CORNER_FACES:]]
    try:
        front = _front_face(p, body)
    except ModelError as e:
        return bad + [f"{MODEL}: {e}"]
    shared = {int(i) for t in body for i in t}
    a, b, c = (uv[i] for i in front)
    m = np.array([b - a, c - a]).T
    for t in corners:
        n_face = _face_normal(p, t)
        if len(set(t)) != 3 or any(int(i) in shared for i in t):
            bad.append(f"{MODEL}: corner face {t} shares vertices with the rest of the piece")
        if any(float(np.dot(normals[i], n_face)) < 0.99 for i in t):
            bad.append(f"{MODEL}: corner face {t} vertex normals aren't the face's own")
        for i in t:
            w1, w2 = np.linalg.solve(m, uv[i] - a)
            if min(w1, w2, 1 - w1 - w2) < 0:
                bad.append(f"{MODEL}: corner face {t} vertex {i} UV {[round(float(x), 4) for x in uv[i]]} is outside "
                           f"the front face's gold")
    if info is not None and [list(map(int, t)) for t in tris] != info["faces"]:
        bad.append(f"{MODEL}: faces differ from the plan's")
    return bad


def aabb(info):
    """The ActorInfo ModelAabbMin/Max of the piece."""
    return ({"X": info["min"][0], "Y": info["min"][1], "Z": info["min"][2]},
            {"X": info["max"][0], "Y": info["max"][1], "Z": info["max"][2]})


if __name__ == "__main__":
    import json
    op, info = plan(sys.argv[1] if len(sys.argv) > 1 else __import__("romtools").longshot_romfs())
    print(json.dumps(info, indent=1))
    print(len(op["bytes"]), "edits,", sum(len(e["bytes"]) // 2 for e in op["bytes"]), "bytes")
