"""Offline reader for the remake's level collision (Havok "Phive" shapes). Tooling only, nothing the game runs uses it.

Worked out from the bytes alone, with no Havok SDK and no outside code. numpy does the bulk vertex math and the caches.

Where the collision is
  Phive/Shape/Dcc/<model>__<Body>.Nin_Ounce_NVN2.bphsh.zs       one shape per file (5877 files, every one an
      hknpMeshShape). <Body> is the rigid body it serves: Physical (GroundHighRes), StairStep (GroundHighResRough),
      StairSlope (GroundHighResSmooth), Airwall (GroundHighRes + sublayer AirWall), and a few one-offs.
  Phive/StaticCompoundBody/<Area>/<Area>_<Age>[_<Variant>]_X<i>_Z<j>.Nin_Ounce_NVN2.bphsc.zs (or <Area>.….bphsc.zs
      for one-tile dungeons): the baked level. Each tile holds the shapes themselves, not references:
        * up to 10 hknpCompoundShape "slots" (one tagfile each), whose instances are the baked placements' shapes
          (copies of the Dcc meshes, plus boxes, convex hulls and capsules from the actors' ShapeParams), each with
          the placement's own rotation, translation and scale;
        * for outdoor areas, an embedded Phive shape file (an hknpMeshShape) = the terrain of that 250 x 250 tile,
          in tile-local coordinates; the 0x30-byte record just before it holds scale (3 floats at +0) and the tile
          origin (3 floats at +0x18), e.g. DeathMountainTrail X1_Z1 -> (-250, 0, -250). Tiles are 250 m, and the
          grid is centred on 0 (4 tiles: -500..500; HyruleField 16 tiles: -2000..2000).
      The tile header (u32s from 0x0c up to the first section, which starts at 0x510) is a list of section offsets
      followed, further on, by their sizes. Section at u32[0x10]: the actor table (tools/phive_static.py): 32-byte
      records {u32 first, u32 last, u64 placement ID, u64, u64}. This reader does not need it: baked instances are
      tied to placements by their transform (every baked instance's translation and rotation equal its placement's,
      checked on 4,262 placements in 4 areas).
  Pack/Actor/<Actor>.pack.zs  Component/Physics/<Actor>…PhysicsParam -> ControllerSetPath -> ControllerSetParam:
      RigidBodyEntityNamePathAry (body -> RigidBodyEntityParam: LayerEntity, SubLayerEntity, EnableLayerHitMask,
      ShapeName) and ShapeNamePathAry (shape -> ShapeParam: PhshMesh (a Dcc path), Box, Polytope, Sphere, Capsule,
      Cylinder, …). Files named "Work/X.gyml" are "X.bgyml" in the pack, else in Pack/ResidentCommon.pack.zs, else
      loose in the romfs; "$parent" merges the parent file under the child's keys.

Phive container (bphsh)
  "Phive\\0" u8 1, u8 0, u16 0xFEFF (byte order mark), u16 0x0400, u32 tagfile offset (0x30), then u32 offsets of
  two trailing sections (materials, collision filter) and the file end, u32 tagfile size, u32 sizes of the trailers.

TAG0 tagfile (Havok 2025, "SDKV20250200")
  A section is u32 BIG-endian: top 2 bits flags (0x40000000 = leaf, 0 = holds sub-sections), low 30 bits = size
  including the 8-byte header; then a 4-char tag. TAG0 holds SDKV (8-char version), DATA (the object bytes, all
  little-endian), TYPE {TPTR, TST1 (type-name strings, NUL-separated), TNA1 (names), FST1 (field-name strings),
  TBDY (bodies), THSH, TPAD} and INDX {ITEM}. No PTCH: every pointer here is self-relative.
  Packed ints (TNA1, TBDY): 0xxxxxxx = 7 bits; 10xxxxxx +1 byte = 14 bits; 110xxxxx +2 bytes; 11100xxx +3 bytes;
  11101xxx +4 bytes (big-endian after the first byte).
  TNA1: count (types + 1; type 0 is "none"), then per type: name index, n params, per param (name index, value);
  a param whose name starts with "t" is a type index, else a number.
  TBDY: per entry: type index (0 = skip), parent type, flags; then, by flag bit: 0x01 format, 0x02 sub-type,
  0x04 version, 0x08 size + alignment, 0x10 extra flags, 0x20 members (count; each: name index, flags, [one more
  packed int when flags & 0x80], offset, type), 0x40 interfaces (count; (type, value) pairs), 0x80 attribute.
  Format: low 4 bits = kind (2 bool, 3 string, 4 int, 5 float, 6 pointer, 7 record, 8 array), 0x20 = fixed-size
  array (count = format >> 8); for ints 0x200 = signed and 0x2000/0x4000/0x8000/0x10000 = 8/16/32/64 bits. A type
  with no format is a typedef of its parent.
  ITEM: 12-byte records {u32 type | flags << 24, u32 offset into DATA, u32 count}; item 0 is empty, item 1 is the
  root object.
  hkRelArrayView<T> = {i32 offset, i32 count}, hkRelArray<T> = {i64 offset, i32 count, i32 capacity}, hkRelPtr<T>
  = {i64 offset}: offsets are relative to the field's own address (0 = null).

hknpMeshShape (size 0xa0; hknpShape base 0x38: type u8 at 0x18 …)
  0x40 vertexConversionUtil {hkVector4 bitScale16 (512, 512, 512), hkVector4 bitScale16Inv (1/512)}
  0x60 shapeTagTable  relview<{u32 meshPrimitiveKey, u16 shapeTag}>   (materials; not needed for geometry)
  0x68 topLevelTree   hkcdSimdTree over the sections
  0x88 geometrySections relview<GeometrySection (0x40 bytes)>:
       0x00 sectionBvh relview<hknpAabb8TreeNode>, 0x08 primitives relview<{u8 a, b, c, d}>,
       0x10 vertexBuffer relview<u8>, 0x18 interiorPrimitiveBitField relview<u8>,
       0x20 sectionOffset i32[3], 0x2c bitScale8Inv float[3], 0x38 bitOffset i16[3]
  Vertices: the vertex buffer is u16[3] per vertex (6 bytes, padded to 4); position = (v + sectionOffset) *
  bitScale16Inv (1/512 m steps). A primitive is a quad (a, b, c, d) = triangles (a, b, c) + (a, c, d), or a
  triangle when c == d. A section whose sectionOffset is 0x7FFFFFFF is a placeholder (one in KakarikoVillage
  Child X7_Z7's terrain) and is skipped.
  Checked: decoded bounding boxes equal the ShapeParam AutoCalc Min/Max (e.g. Land_GreatFairyFountain_Base_A_01
  Physical (-27.475, -2.6, -27.475)..(27.475, 21.518, 27.137)), and closed models decode closed (Obj_BrokenRock_A_01:
  every one of 834 directed edges has its opposite, none repeats: one consistent winding).

Materials (per triangle)
  shapeTagTable = runs {u32 meshPrimitiveKey, u16 shapeTag} sorted by key, a run lasting until the next key;
  key = section << 9 | primitive << 1 | half (half 1 = a quad's second triangle); 0xFFFF = none. A shapeTag indexes
  the Phive file's material section (header u32 0x10..0x14): 16-byte entries {u32 material, u32 sub-material,
  u64 UserShapeTagMask}. Names come from Pack/Bootup.Nin_Ounce_NVN2.pack.zs Phive/Config/PhiveConfig.byml
  (MaterialCollection, SubMaterialCollection, UserShapeTagMaskCollection): e.g. StickHookshot = 1 << 44 (what the
  hookshot sticks to: Obj_HookShotTarget_A_01 boxes, ladder tops), Climb = 1 << 40 (vines), Ladder = 2,
  NoClamber = 1 << 41, Slip = 4. Primitive shapes take theirs from the ShapeParam's MaterialPresets
  (PhiveConfig MaterialPresetCollection). Baked tile copies of a Dcc mesh keep its triangle order, so a matched
  instance takes the Dcc file's materials; the tile's terrain uses its own embedded table.
  Layers: PhiveConfig LayerHitMaskEntityCollection "Player" = 2736127 (bits 0-13 minus 14, 15, 16, 19, 21): Link
  collides with GroundHighRes (Physical), GroundHighResRough (StairStep) and GroundHighResSmooth (StairSlope).

hknpCompoundShape (0xb8): 0x38 instances hkFreeListRelArray<hknpShapeInstance> = hkRelArray {i64 off, i32 n, i32 cap}
  + i32 firstFree + u32 numAllocated. hknpShapeInstance (0x40): quaternion (x, y, z, w) at 0, translation float[3] at
  0x10, leafIdAndFlags at 0x1c, scale float[3] at 0x20, shapeTag u16 at 0x2c, hkRelPtr<hknpShape> at 0x30, userData
  at 0x38. Instance transform: world = translation + rotate(q, scale * v). Nested compounds happen.
hknpConvexShape (0x78): hull at 0x38 = relviews {vertices float[3], planes float[4], faces {u16 firstIndex,
  u8 numIndices, u8 minHalfAngle}, indices u8, faceLinks, vertexEdges}; convexRadius float at 0x68 (the true surface
  is the hull grown by it). hknpBoxShape (0xc0) adds obb (hkTransform at 0x80; column w = shrunk half extents);
  hknpCapsuleShape has a 2-vertex hull (the segment) and its radius as convexRadius.

Placements
  Banc/<Area>/<Level>.bcett.byml.zs Actors: Translate, Rotate (radians), Scale (default 1). Rotation order, found
  by matching baked instance quaternions: q = qZ * qY * qX, i.e. world = T + Rz(rz) Ry(ry) Rx(rx) (S * v) (X turned
  first). All 4,262 placements with turns on all axes in DeathMountainTrail, KakarikoVillage Child, HyruleField
  Adult and GoronCity Adult match it to 1e-5 (but one, a stacked duplicate); no other order comes close.

API
  triangles(fs, shape_rel) -> [(v0, v1, v2)]               a Dcc shape in model space
  Tagfile(buf, offset), tagfiles(buf), shape_mesh(tf, addr), mesh_shape_tags(tf, addr), phive_materials(buf)
                                                           the low-level reader (any TAG0 object, any shape)
  phive_config(fs), tag_bit(fs, name)                       material / user-tag names
  world_triangles(fs, level_rel, hash, solid_only=True) -> [...]  a placed actor's collision in world space
  actor_bodies(fs, gyaml) -> [Body]                           rigid bodies + shapes of an actor type
  placement_matrix(actor) -> 3x4 numpy matrix                 from a level byml actor dict
  static_tile(fs, tile_rel) -> TileParts                      terrain + baked instances of one bphsc tile
  area_collision(fs, area, age, variant=None, center=None, radius=None) -> Collision
      tiles near the point (or all) + the level files' non-baked placements, labelled per part (placement hash,
      actor, body, layer, sublayer, hit mask, Presence) with per-triangle material / sub-material / user tags;
      cached per tile and per level file under cache/gamedb/collision/ (generated; ignored by cache/gamedb/.gitignore)

  python tools/phive_shape.py check                    format self-checks (bbox vs ShapeParam, closed mesh, Euler)
  python tools/phive_shape.py shape <Dcc rel or name>  triangle count and bounding box
  python tools/phive_shape.py area <Area> <Child|Adult> [variant]   build / show an area's cached collision
"""
import functools
import hashlib
import json
import math
import os
import re
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(HERE, "tools")
for _p in (TOOLS, os.path.join(TOOLS, "gamedb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CACHE = os.path.join(HERE, "cache", "gamedb", "collision")
CACHE_VERSION = 4
SHAPE_DIR = "Phive/Shape/Dcc"
TILE_DIR = "Phive/StaticCompoundBody"
SUFFIX = ".Nin_Ounce_NVN2.bphsh.zs"
NO_OFFSET = 0x7FFFFFFF

# Tagfile


def _packed(b, o):
    """(value, next offset) of a packed int (see the docstring)."""
    c = b[o]
    if c < 0x80:
        return c, o + 1
    if c < 0xC0:
        return ((c & 0x3F) << 8) | b[o + 1], o + 2
    if c < 0xE0:
        return ((c & 0x1F) << 16) | (b[o + 1] << 8) | b[o + 2], o + 3
    if c < 0xE8:
        return ((c & 0x07) << 24) | int.from_bytes(b[o + 1:o + 4], "big"), o + 4
    if c < 0xF0:
        return ((c & 0x07) << 32) | int.from_bytes(b[o + 1:o + 5], "big"), o + 5
    raise ValueError(f"packed int prefix {c:#x} at {o:#x}")


def _sections(b, start, end):
    o = start
    while o + 8 <= end:
        hdr = struct.unpack_from(">I", b, o)[0]
        size = hdr & 0x3FFFFFFF
        if size < 8:
            raise ValueError(f"bad tagfile section size {size} at {o:#x}")
        yield b[o + 4:o + 8].decode("latin1"), hdr >> 30, o + 8, o + size
        o += size


class Type:
    __slots__ = ("index", "name", "params", "parent", "flags", "format", "sub", "version", "size", "align",
                 "members")

    def __init__(self, index):
        self.index, self.name, self.params = index, "none", []
        self.parent = self.flags = self.format = self.sub = self.version = self.size = self.align = 0
        self.members = []          # [(name, flags, offset, type index)]

    def __repr__(self):
        return f"<Type {self.index} {self.full_name()}>"

    def full_name(self):
        if not self.params:
            return self.name
        return self.name + "<" + ", ".join(f"{n}={v.full_name() if isinstance(v, Type) else v}"
                                           for n, v in self.params) + ">"


class Tagfile:
    """One TAG0 tagfile inside a buffer. Offsets (items, addresses) are absolute offsets into `buf`."""

    def __init__(self, buf, offset):
        self.buf, self.offset = buf, offset
        size = struct.unpack_from(">I", buf, offset)[0] & 0x3FFFFFFF
        if buf[offset + 4:offset + 8] != b"TAG0":
            raise ValueError(f"no TAG0 at {offset:#x}")
        self.end = offset + size
        tree = {}
        for tag, flags, s, e in _sections(buf, offset + 8, self.end):
            tree[tag] = {t: (s2, e2) for t, _, s2, e2 in _sections(buf, s, e)} if flags == 0 else (s, e)
        self.sdk = buf[tree["SDKV"][0]:tree["SDKV"][1]].decode("latin1")
        self.data = tree["DATA"][0]
        self.types = self._read_types(tree["TYPE"])
        s, e = tree["INDX"]["ITEM"]
        self.items = []
        for o in range(s, e, 12):
            tf, off, cnt = struct.unpack_from("<III", buf, o)
            self.items.append((self.types[tf & 0xFFFFFF], self.data + off, cnt))
        self._item_at = {addr: t for t, addr, _ in self.items[1:]}
        self._names = {}
        for t in self.types:
            self._names.setdefault(t.name, t)

    def _read_types(self, ty):
        b = self.buf
        tstr = [x.decode("latin1") for x in b[ty["TST1"][0]:ty["TST1"][1]].split(b"\0")]
        fstr = [x.decode("latin1") for x in b[ty["FST1"][0]:ty["FST1"][1]].split(b"\0")]
        n, o = _packed(b, ty["TNA1"][0])
        types = [Type(i) for i in range(n)]
        for t in types[1:]:
            v, o = _packed(b, o)
            t.name = tstr[v]
            np_, o = _packed(b, o)
            for _ in range(np_):
                pn, o = _packed(b, o)
                pv, o = _packed(b, o)
                pn = tstr[pn]
                t.params.append((pn, types[pv] if pn.startswith("t") else pv))
        o, e = ty["TBDY"]
        while o < e:
            ti, o = _packed(b, o)
            if ti == 0:
                continue
            t = types[ti]
            t.parent, o = _packed(b, o)
            t.flags, o = _packed(b, o)
            if t.flags & 0x01:
                t.format, o = _packed(b, o)
            if t.flags & 0x02:
                t.sub, o = _packed(b, o)
            if t.flags & 0x04:
                t.version, o = _packed(b, o)
            if t.flags & 0x08:
                t.size, o = _packed(b, o)
                t.align, o = _packed(b, o)
            if t.flags & 0x10:
                _, o = _packed(b, o)
            if t.flags & 0x20:
                cnt, o = _packed(b, o)
                for _ in range(cnt):
                    nm, o = _packed(b, o)
                    fl, o = _packed(b, o)
                    if fl & 0x80:
                        _, o = _packed(b, o)
                    off, o = _packed(b, o)
                    mt, o = _packed(b, o)
                    t.members.append((fstr[nm], fl, off, mt))
            if t.flags & 0x40:
                cnt, o = _packed(b, o)
                for _ in range(cnt):
                    _, o = _packed(b, o)
                    _, o = _packed(b, o)
            if t.flags & 0x80:
                _, o = _packed(b, o)
        return types

    # Type and relative pointer lookups
    @property
    def root(self):
        """(type, address) of the root object (item 1)."""
        t, addr, _ = self.items[1]
        return t, addr

    def type_at(self, addr):
        """The type of the object an item places at addr (None if no item starts there)."""
        return self._item_at.get(addr)

    def type_named(self, name):
        return self._names.get(name)

    def member(self, type_name, field):
        """Offset of a field in a record type, walking up to its parents (raises if absent)."""
        t = self._names[type_name]
        while t and t.index:
            for nm, _, off, _ in t.members:
                if nm == field:
                    return off
            t = self.types[t.parent] if t.parent else None
        raise KeyError(f"{type_name}.{field}")

    def is_a(self, t, name):
        while t and t.index:
            if t.name == name:
                return True
            t = self.types[t.parent] if t.parent else None
        return False

    def relview(self, addr):
        """(absolute address, count) of an hkRelArrayView at addr."""
        off, n = struct.unpack_from("<ii", self.buf, addr)
        return addr + off, n

    def relarray(self, addr):
        """(absolute address, count) of an hkRelArray at addr."""
        off, n = struct.unpack_from("<qi", self.buf, addr)
        return addr + off, n

    def relptr(self, addr):
        off, = struct.unpack_from("<q", self.buf, addr)
        return addr + off if off else None


def tagfiles(buf):
    """Every top-level TAG0 tagfile in a buffer (a bphsc tile holds several), in file order."""
    out, o = [], 0
    while True:
        i = buf.find(b"TAG0", o)
        if i < 0:
            return out
        start = i - 4
        size = struct.unpack_from(">I", buf, start)[0] & 0x3FFFFFFF
        if buf[start] & 0xC0 == 0 and size > 8 and start + size <= len(buf):
            try:
                out.append(Tagfile(buf, start))
                o = start + size
                continue
            except (ValueError, KeyError, IndexError, struct.error):
                pass
        o = i + 4

# Shapes


def _mesh(tf, addr):
    """(vertices float32[n,3], triangles int32[m,3]) of an hknpMeshShape at addr, shape space."""
    b = tf.buf
    conv = addr + tf.member("hknpMeshShape", "vertexConversionUtil")
    inv = np.array(struct.unpack_from("<3f", b, conv + 16), dtype=np.float64)
    sec_addr, nsec = tf.relview(addr + tf.member("hknpMeshShape", "geometrySections"))
    sec_size = tf.type_named("hknpMeshShape::GeometrySection").size or 64
    f_prim = tf.member("hknpMeshShape::GeometrySection", "primitives")
    f_vert = tf.member("hknpMeshShape::GeometrySection", "vertexBuffer")
    f_off = tf.member("hknpMeshShape::GeometrySection", "sectionOffset")
    verts, tris, base = [], [], 0
    for k in range(nsec):
        s = sec_addr + k * sec_size
        ox, oy, oz = struct.unpack_from("<3i", b, s + f_off)
        if NO_OFFSET in (ox, oy, oz):
            continue
        va, vn = tf.relview(s + f_vert)
        pa, pn = tf.relview(s + f_prim)
        nv = vn // 6
        if not nv or not pn:
            continue
        v = np.frombuffer(b, dtype="<u2", count=nv * 3, offset=va).reshape(nv, 3).astype(np.float64)
        v = (v + (ox, oy, oz)) * inv
        p = np.frombuffer(b, dtype=np.uint8, count=pn * 4, offset=pa).reshape(pn, 4).astype(np.int32)
        if p[:, :3].max() >= nv:
            raise ValueError(f"mesh section {k}: index past its {nv} vertices")
        t1 = p[:, [0, 1, 2]]
        quad = p[:, 2] != p[:, 3]
        t2 = p[quad][:, [0, 2, 3]]
        tris.append(np.vstack([t1, t2]) + base)
        verts.append(v)
        base += nv
    if not verts:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32)
    return np.vstack(verts).astype(np.float32), np.vstack(tris).astype(np.int32)


def mesh_shape_tags(tf, addr):
    """Per-triangle shapeTag of an hknpMeshShape (same triangle order as _mesh), 0xFFFF where none.
    shapeTagTable is runs of {u32 meshPrimitiveKey, u16 shapeTag} sorted by key, and a run lasts until the next
    key. Key = section << 9 | primitive << 1 | half (half 1 = the quad's second triangle)."""
    b = tf.buf
    ta, tn = tf.relview(addr + tf.member("hknpMeshShape", "shapeTagTable"))
    sec_addr, nsec = tf.relview(addr + tf.member("hknpMeshShape", "geometrySections"))
    sec_size = tf.type_named("hknpMeshShape::GeometrySection").size or 64
    f_prim = tf.member("hknpMeshShape::GeometrySection", "primitives")
    f_vert = tf.member("hknpMeshShape::GeometrySection", "vertexBuffer")
    f_off = tf.member("hknpMeshShape::GeometrySection", "sectionOffset")
    keys = []
    for k in range(nsec):
        s = sec_addr + k * sec_size
        if NO_OFFSET in struct.unpack_from("<3i", b, s + f_off):
            continue
        _, vn = tf.relview(s + f_vert)
        pa, pn = tf.relview(s + f_prim)
        if not vn // 6 or not pn:
            continue
        p = np.frombuffer(b, dtype=np.uint8, count=pn * 4, offset=pa).reshape(pn, 4)
        idx = np.arange(pn, dtype=np.int64)
        quad = p[:, 2] != p[:, 3]
        keys.append(np.concatenate([(k << 9) | (idx << 1), (k << 9) | (idx[quad] << 1) | 1]))
    if not keys:
        return np.zeros(0, np.uint16)
    keys = np.concatenate(keys)
    if not tn:
        return np.full(len(keys), 0xFFFF, np.uint16)
    tab = np.frombuffer(b, dtype=np.dtype([("key", "<u4"), ("tag", "<u2"), ("pad", "<u2")]), count=tn, offset=ta)
    pos = np.searchsorted(tab["key"].astype(np.int64), keys, side="right") - 1
    out = np.where(pos >= 0, tab["tag"][np.clip(pos, 0, None)], 0xFFFF)
    return out.astype(np.uint16)


def phive_materials(buf, base=0):
    """Material table of a Phive shape file at buf[base]: [(material, sub-material, user shape tag mask)], indexed by
    shapeTag. It's the section at header u32 0x10..0x14, with 16-byte entries {u32 material (PhiveConfig
    MaterialCollection index), u32 sub-material (SubMaterialCollection), u64 UserShapeTagMask bits}."""
    s, e = struct.unpack_from("<II", buf, base + 0x10)
    return [struct.unpack_from("<IIQ", buf, base + o) for o in range(s, e, 16)]


@functools.lru_cache(maxsize=1)
def phive_config(fs):
    """Names from Pack/Bootup…pack.zs Phive/Config/PhiveConfig.byml: materials, sub-materials, user shape tag bits,
    material presets, layers."""
    import common
    pk = common.pack(fs, "Pack/Bootup.Nin_Ounce_NVN2.pack.zs")
    d = common.byml_load(pk["Phive/Config/PhiveConfig.byml"])[0]
    names = lambda k: [x["ComponentName"] if isinstance(x, dict) else x for x in d.get(k) or []]  # noqa: E731
    bits = {x["ComponentName"]: int(x["MaskValue"]) for x in d.get("UserShapeTagMaskCollection") or []}
    presets = {x["ComponentName"]: x for x in d.get("MaterialPresetCollection") or []}
    return {"material": names("MaterialCollection"), "submaterial": names("SubMaterialCollection"),
            "tagbits": bits, "presets": presets, "layer": names("LayerEntityCollection"),
            "sublayer": names("SubLayerEntityCollection")}


def tag_bit(fs, name):
    """The UserShapeTagMask bit of a user shape tag name (e.g. 'StickHookshot' -> 1 << 44)."""
    return phive_config(fs)["tagbits"][name]


def _preset_material(fs, presets):
    """(material, sub-material, tag mask) of a ShapeParam MaterialPresets list."""
    cfg = phive_config(fs)
    mat, sub, mask = 0, 0, 0
    for name in presets or []:
        p = cfg["presets"].get(name)
        if not p:
            continue
        if p.get("Material") in cfg["material"]:
            mat = cfg["material"].index(p["Material"])
        if p.get("SubMaterial") in cfg["submaterial"]:
            sub = cfg["submaterial"].index(p["SubMaterial"])
        for t in p.get("UserShapeTagMask") or []:
            mask |= cfg["tagbits"].get(t, 0)
    return mat, sub, mask


def _hull_faces(tf, addr):
    """(vertices float32[n,3], triangles int32[m,3]) of an hknpConvexShape's hull, grown by its convex radius."""
    b = tf.buf
    h = addr + tf.member("hknpConvexShape", "hull")
    radius = struct.unpack_from("<f", b, addr + tf.member("hknpConvexShape", "convexRadius"))[0]
    va, vn = tf.relview(h + tf.member("hknpConvexHull", "vertices"))
    fa, fn = tf.relview(h + tf.member("hknpConvexHull", "faces"))
    ia, inn = tf.relview(h + tf.member("hknpConvexHull", "indices"))
    v = np.frombuffer(b, dtype="<f4", count=vn * 3, offset=va).reshape(vn, 3).astype(np.float64)
    t = tf.type_at(addr)
    if t is not None and tf.is_a(t, "hknpCapsuleShape") or (fn == 0 and vn == 2):
        return _capsule(v[0], v[1], radius)
    idx = np.frombuffer(b, dtype=np.uint8, count=inn, offset=ia)
    tris = []
    for k in range(fn):
        first, num, _ = struct.unpack_from("<HBB", b, fa + 4 * k)
        f = idx[first:first + num]
        tris += [(f[0], f[j], f[j + 1]) for j in range(1, num - 1)]
    if radius > 0 and vn:
        if t is not None and tf.is_a(t, "hknpBoxShape"):     # box hull = the box shrunk by the radius on each axis
            obb = addr + tf.member("hknpBoxShape", "obb")
            rot = np.array(struct.unpack_from("<12f", b, obb), dtype=np.float64).reshape(3, 4)[:, :3]  # columns
            ctr = np.array(struct.unpack_from("<3f", b, obb + 48), dtype=np.float64)
            local = (v - ctr) @ rot                           # rows of rot^T: coordinates along the box axes
            local += np.sign(local) * radius
            v = local @ rot.T + ctr
        else:                                              # approximate: push each vertex out from the centre
            c = v.mean(axis=0)
            d = v - c
            n = np.linalg.norm(d, axis=1, keepdims=True)
            v = v + d / np.where(n > 0, n, 1) * radius
    return v.astype(np.float32), np.array(tris, dtype=np.int32).reshape(-1, 3)


def _capsule(a, b, r, sides=8):
    """An octagonal prism around segment a-b with radius r, capped flat at a - r and b + r (good enough for reach)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    axis = b - a
    ln = np.linalg.norm(axis)
    u = axis / ln if ln > 1e-9 else np.array([0.0, 1.0, 0.0])
    a, b = a - u * r, b + u * r
    p = np.cross(u, [1.0, 0, 0] if abs(u[0]) < 0.9 else [0, 0, 1.0])
    p /= np.linalg.norm(p)
    q = np.cross(u, p)
    ring = [r * (math.cos(2 * math.pi * k / sides) * p + math.sin(2 * math.pi * k / sides) * q) for k in range(sides)]
    v = np.array([a + x for x in ring] + [b + x for x in ring] + [a, b])
    tris = []
    for k in range(sides):
        k2 = (k + 1) % sides
        tris += [(k, k2, sides + k2), (k, sides + k2, sides + k), (2 * sides, k2, k), (2 * sides + 1, sides + k,
                                                                                     sides + k2)]
    return v.astype(np.float32), np.array(tris, dtype=np.int32)


def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _instances(tf, addr):
    """[(rotation 3x3, translation, scale, shape address, shapeTag)] of an hknpCompoundShape at addr."""
    b = tf.buf
    ia, n = tf.relarray(addr + tf.member("hknpCompoundShape", "instances"))
    size = tf.type_named("hknpShapeInstance").size or 64
    f_sh = tf.member("hknpShapeInstance", "shape")
    out = []
    for i in range(n):
        e = ia + i * size
        q = struct.unpack_from("<4f", b, e)
        t = struct.unpack_from("<3f", b, e + 16)
        s = struct.unpack_from("<3f", b, e + 32)
        tag, = struct.unpack_from("<H", b, e + 44)
        out.append((quat_matrix(q), np.array(t), np.array(s), tf.relptr(e + f_sh), tag))
    return out


def shape_mesh(tf, addr):
    """(vertices, triangles) of any shape at addr (mesh, convex/box/capsule, compound), in that shape's space."""
    t = tf.type_at(addr)
    if t is None:
        raise ValueError(f"no shape object at {addr:#x}")
    if tf.is_a(t, "hknpMeshShape"):
        return _mesh(tf, addr)
    if tf.is_a(t, "hknpConvexShape"):
        return _hull_faces(tf, addr)
    if tf.is_a(t, "hknpCompoundShape"):
        vs, ts, base = [], [], 0
        for rot, tr, sc, sa, _ in _instances(tf, addr):
            v, tri = shape_mesh(tf, sa)
            vs.append((v * sc) @ rot.T + tr)
            ts.append(tri + base)
            base += len(v)
        if not vs:
            return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32)
        return np.vstack(vs).astype(np.float32), np.vstack(ts)
    raise ValueError(f"shape type {t.full_name()} not handled")


def mesh_fingerprint(tf, addr):
    """A content hash of a shape's geometry bytes (same mesh in a Dcc file and in a tile -> same hash)."""
    v, t = shape_mesh(tf, addr)
    return hashlib.sha1(np.round(v, 3).astype(np.float32).tobytes() + t.tobytes()).hexdigest()[:16]

# Dcc shape files


def phive_tagfile(buf, base=0):
    """The tagfile of a Phive shape file (bphsh) starting at buf[base]."""
    if buf[base:base + 6] != b"Phive\0":
        raise ValueError("not a Phive file")
    off, = struct.unpack_from("<I", buf, base + 0x0c)
    return Tagfile(buf, base + off)


def _read(fs, rel):
    import common
    return common.read_any(fs, rel)


def dcc_rel(name):
    """'Land_X__Physical' or 'Work/Phive/Shape/Dcc/Land_X__Physical.phsh' -> romfs rel of the bphsh file."""
    n = name.replace("\\", "/").split("/")[-1]
    for ext in (".phsh", SUFFIX):
        if n.endswith(ext):
            n = n[:-len(ext)]
    return f"{SHAPE_DIR}/{n}{SUFFIX}"


@functools.lru_cache(maxsize=512)
def _dcc_full(fs, rel):
    """(vertices, triangles, materials) of a Dcc shape file; materials = (material, sub, tag mask) per triangle."""
    buf = _read(fs, rel)
    tf = phive_tagfile(buf)
    v, t = shape_mesh(tf, tf.root[1])
    return v, t, _materials_for(mesh_shape_tags(tf, tf.root[1]), phive_materials(buf), len(t))


def _materials_for(tags, table, n):
    """Per-triangle (material int16, sub int16, mask uint64) arrays from shapeTags and a Phive material table."""
    mat = np.full(n, -1, np.int16)
    sub = np.zeros(n, np.int16)
    mask = np.zeros(n, np.uint64)
    if len(tags) == n and table:
        tab = np.array(table + [(0xFFFF, 0, 0)], dtype=np.uint64)
        idx = np.where(tags.astype(np.int64) < len(table), tags.astype(np.int64), len(table))
        mat = np.where(idx < len(table), tab[idx, 0].astype(np.int64), -1).astype(np.int16)
        sub = tab[idx, 1].astype(np.int16)
        mask = tab[idx, 2].astype(np.uint64)
    return mat, sub, mask


def _dcc_mesh(fs, rel):
    v, t, _ = _dcc_full(fs, rel)
    return v, t


def triangles(fs, shape_rel):
    """[(v0, v1, v2)] in model space of one Dcc shape (rel path or bare name)."""
    v, t = _dcc_mesh(fs, dcc_rel(shape_rel) if not shape_rel.startswith(SHAPE_DIR) else shape_rel)
    return [tuple(map(tuple, v[tri].tolist())) for tri in t]


# Actors and placements

SOLID_LAYERS = {"GroundHighRes", "GroundHighResRough", "GroundHighResSmooth", "GroundObject", "Ground", "Object"}
# hit masks that keep a body away from the player (camera-only, small-object-only, ...)
NOT_PLAYER_MASKS = {"NoHit", "HitOnlySmallObject", "HitOnlyCameraBody", "HitOnlyCameraBodyAndSight",
                    "HitOnlyCameraAlphaCtrlCheck", "HitOnlyGround", "HitOnlyGroundAndObject", "FilterCamera",
                    "FilterCameraSight", "HitOnlyObject", "HitOnlyCharacterAndObjectAndSmallObject"}


class Body:
    """One rigid body of an actor type: its layer and its shape primitives (model space)."""

    def __init__(self, name, layer, sublayer, mask, prims):
        self.name, self.layer, self.sublayer, self.mask, self.prims = name, layer, sublayer, mask, prims

    @property
    def blocks_player(self):
        """Solid for Link (ground, objects and air walls that don't skip the player)."""
        return self.layer in SOLID_LAYERS and (self.mask or "") not in NOT_PLAYER_MASKS

    @property
    def is_airwall(self):
        return self.sublayer == "AirWall" or "airwall" in self.name.lower()

    def __repr__(self):
        return f"<Body {self.name} {self.layer}/{self.sublayer}/{self.mask} {[p[0] for p in self.prims]}>"


@functools.lru_cache(maxsize=1)
def _resident(fs):
    import common
    try:
        return common.pack(fs, "Pack/ResidentCommon.pack.zs")
    except FileNotFoundError:
        return {}


def _param(fs, pk, path):
    """A Work/… gyml param merged with its $parent chain, from the actor pack, ResidentCommon or the romfs."""
    import common
    p = path[5:] if path.startswith("Work/") else path
    inner = p[:-5] + ".bgyml" if p.endswith(".gyml") else p
    raw = pk.get(inner) or _resident(fs).get(inner)
    if raw is None:
        for cand in (inner, inner + ".zs"):
            try:
                raw = common.read_any(fs, cand)
                break
            except (FileNotFoundError, OSError):
                continue
    if raw is None:
        return None
    d = common.byml_load(raw)[0]
    if "$parent" in d:
        base = dict(_param(fs, pk, d["$parent"]) or {})
        base.update({k: v for k, v in d.items() if k != "$parent"})
        return base
    return d


def _v3(d, default=0.0):
    return np.array([float((d or {}).get(c, default)) for c in "XYZ"])


def _euler_matrix(r):
    """Rz Ry Rx for angles r = (rx, ry, rz) in radians (the game's order)."""
    rx, ry, rz = r
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mz @ my @ mx


def _box(center, half):
    c, h = np.asarray(center, float), np.asarray(half, float)
    v = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float) * h + c
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = [(a, b, c_) for a, b, c_, d in f] + [(a, c_, d) for a, b, c_, d in f]
    return v, np.array(tris, np.int32)


def _convex_hull(points):
    """Triangles of the convex hull of a small point set (gift-wrap by brute force; Polytopes have few points)."""
    p = np.unique(np.round(np.asarray(points, float), 5), axis=0)
    n = len(p)
    if n < 4:
        return p, np.zeros((0, 3), np.int32)
    c = p.mean(axis=0)
    tris = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                nrm = np.cross(p[j] - p[i], p[k] - p[i])
                ln = np.linalg.norm(nrm)
                if ln < 1e-9:
                    continue
                d = (p - p[i]) @ nrm
                if (d > 1e-6 * ln).any() and (d < -1e-6 * ln).any():
                    continue
                tris.append((i, j, k) if np.dot(nrm, p[i] - c) > 0 else (i, k, j))
    return p, np.array(tris, np.int32).reshape(-1, 3)


def _shape_prims(fs, sp):
    """[(kind, vertices, triangles, materials)] of one ShapeParam dict, in model space (offsets applied). materials
    are what _materials_for gives, from the Dcc file or the primitive's MaterialPresets."""
    out = []
    for m in sp.get("PhshMesh") or []:
        rel = dcc_rel(m.get("PhshMeshPath", ""))
        try:
            v, t, mats = _dcc_full(fs, rel)
        except (FileNotFoundError, OSError):
            continue
        out.append(("mesh:" + rel.split("/")[-1][:-len(SUFFIX)], v, t, mats))
    for kind in ("Box", "Polytope", "Sphere", "Capsule", "Cylinder"):
        for e in sp.get(kind) or []:
            rot = _euler_matrix(_v3(e.get("OffsetRotation")))
            off = _v3(e.get("OffsetTranslation"))
            if kind == "Box":
                v, t = _box(_v3(e.get("Center")), _v3(e.get("HalfExtents")))
            elif kind == "Polytope":
                pts = [_v3(x) for x in (e.get("Vertices") or e.get("VertexArray") or [])]
                if not pts:
                    continue
                v, t = _convex_hull(pts)
            elif kind == "Sphere":
                r = float(e.get("Radius", 0.5))
                v, t = _box(_v3(e.get("Center")), (r, r, r))
            else:
                r = float(e.get("Radius", 0.5))
                a, b = _v3(e.get("CenterA") or e.get("Center")), _v3(e.get("CenterB") or e.get("Center"))
                if kind == "Cylinder" and not e.get("CenterA"):
                    hh = float(e.get("HalfHeight", e.get("Height", 1.0) / 2))
                    a, b = a - (0, hh, 0), a + (0, hh, 0)
                v, t = _capsule(a, b, r)
            m, sb, mk = _preset_material(fs, e.get("MaterialPresets"))
            mats = (np.full(len(t), m, np.int16), np.full(len(t), sb, np.int16), np.full(len(t), mk, np.uint64))
            out.append((kind.lower(), (np.asarray(v) @ rot.T + off).astype(np.float32), t, mats))
    return out


@functools.lru_cache(maxsize=4096)
def _actor_bodies(fs, gyaml):
    import common
    try:
        pk = common.pack(fs, f"Pack/Actor/{gyaml}.pack.zs")
    except (FileNotFoundError, OSError):
        return ()
    phys = [k for k in pk if k.startswith("Component/Physics/")]
    if not phys:
        return ()
    ph = common.byml_load(pk[phys[0]])[0]
    if "$parent" in ph:
        base = dict(_param(fs, pk, ph["$parent"]) or {})
        base.update({k: v for k, v in ph.items() if k != "$parent"})
        ph = base
    cs = _param(fs, pk, ph["ControllerSetPath"]) if ph.get("ControllerSetPath") else None
    if not cs:
        return ()
    shapes = {e["Name"]: e.get("FilePath") for e in cs.get("ShapeNamePathAry") or []}
    bodies = []
    for e in cs.get("RigidBodyEntityNamePathAry") or []:
        rb = _param(fs, pk, e["FilePath"]) if e.get("FilePath") else {}
        rb = rb or {}
        sname = rb.get("ShapeName") or e["Name"]
        sp = _param(fs, pk, shapes[sname]) if shapes.get(sname) else None
        prims = _shape_prims(fs, sp) if sp else []
        bodies.append(Body(e["Name"], rb.get("LayerEntity"), rb.get("SubLayerEntity"),
                           rb.get("EnableLayerHitMask"), prims))
    return tuple(bodies)


def actor_bodies(fs, gyaml):
    """[Body] of an actor type (its rigid bodies with layer and model-space shapes), or [] when it has no physics."""
    return list(_actor_bodies(fs, gyaml))


@functools.lru_cache(maxsize=64)
def _level(fs, level_rel):
    import common
    return common.read_byml(fs, level_rel)


def placement(fs, level_rel, hash_):
    """The level byml's actor dict with this Hash (full precision Translate/Rotate/Scale)."""
    for a in _level(fs, level_rel).get("Actors") or []:
        if int(a.get("Hash", -1)) == int(hash_):
            return a
    raise KeyError(f"no actor {hash_} in {level_rel}")


def placement_matrix(actor):
    """3x4 matrix [M | T] with world = M @ v + T, M = Rz Ry Rx diag(Scale)."""
    s = np.array(actor.get("Scale") or [1.0, 1.0, 1.0], float)
    if s.shape == ():
        s = np.array([float(s)] * 3)
    m = _euler_matrix(actor.get("Rotate") or (0.0, 0.0, 0.0)) * s
    return np.hstack([m, np.array(actor.get("Translate") or (0.0, 0.0, 0.0), float).reshape(3, 1)])


def world_triangles(fs, level_rel, hash_, solid_only=True):
    """[(v0, v1, v2)] in world space for the placed actor's bodies (by default only those solid for Link)."""
    a = placement(fs, level_rel, hash_)
    m = placement_matrix(a)
    out = []
    for body in actor_bodies(fs, a["Gyaml"]):
        if solid_only and not body.blocks_player:
            continue
        for _, v, t, _m in body.prims:
            w = v @ m[:, :3].T + m[:, 3]
            out += [tuple(map(tuple, w[tri].tolist())) for tri in t]
    return out

# Baked tiles

TILE = 250.0


class TileParts:
    """What a bphsc tile holds: `terrain` (vertices, triangles, materials) in world space or None, `instances`
    [(compound index, instance index, rotation 3x3, translation, scale, shape kind, vertices (shape space),
    triangles)]."""

    def __init__(self):
        self.terrain, self.instances, self.origin = None, [], None


def static_tile(fs, tile_rel):
    buf = _read(fs, tile_rel)
    if buf[:6] != b"Phive\0":
        raise ValueError(f"{tile_rel}: not a Phive file")
    parts = TileParts()
    emb = buf.find(b"Phive\0", 8)
    comp = 0
    for tf in tagfiles(buf):
        t, addr = tf.root
        if emb > 0 and tf.offset > emb:          # the embedded terrain shape file
            v, tri = shape_mesh(tf, addr)
            mats = _materials_for(mesh_shape_tags(tf, addr), phive_materials(buf, emb), len(tri))
            hdr_first, = struct.unpack_from("<I", buf, 0x0c)
            offs = struct.unpack_from(f"<{(hdr_first - 0x0c) // 4}I", buf, 0x0c)
            rec = max((o for o in offs if o < emb), default=emb - 0x30)
            scale = np.array(struct.unpack_from("<3f", buf, rec))
            origin = np.array(struct.unpack_from("<3f", buf, rec + 0x18))
            parts.origin = origin
            parts.terrain = ((v * scale + origin).astype(np.float32), tri, mats)
            continue
        if not tf.is_a(t, "hknpCompoundShape"):
            continue
        for i, (rot, tr, sc, sa, _tag) in enumerate(_instances(tf, addr)):
            st = tf.type_at(sa)
            v, tri = shape_mesh(tf, sa)
            kind = ("mesh" if tf.is_a(st, "hknpMeshShape") else "box" if tf.is_a(st, "hknpBoxShape") else
                    "capsule" if tf.is_a(st, "hknpCapsuleShape") else "convex" if tf.is_a(st, "hknpConvexShape")
                    else "compound")
            parts.instances.append((comp, i, rot, tr, sc, kind, v, tri))
        comp += 1
    return parts


_TILE_RX = re.compile(r"^(?P<area>[A-Za-z]+?)(?:_(?P<age>Child|Adult))?(?:_(?P<variant>[A-Za-z]+?))?"
                      r"(?:_X(?P<x>\d+)_Z(?P<z>\d+))?\.Nin_Ounce_NVN2\.bphsc\.zs$")


def area_tiles(fs, area, age, variant=None):
    """[(tile rel, (xmin, zmin, xmax, zmax) or None)] of one area and age (variant e.g. 'Alternative').
    Bounds come from the tile grid, which is 250 m tiles centred on 0, so an area with n tiles a side starts at
    -n * 125. A one-file area (dungeons) has None."""
    d = os.path.join(fs.root, TILE_DIR, area)
    if not os.path.isdir(d):
        return []
    rows = []
    for f in sorted(os.listdir(d)):
        m = _TILE_RX.match(f)
        if not m or m.group("area") != area:
            continue
        if m.group("age") not in (None, age) or (m.group("variant") or None) != variant:
            continue
        rows.append((f"{TILE_DIR}/{area}/{f}", m.group("x"), m.group("z")))
    nx = max((int(x) for _, x, _ in rows if x is not None), default=-1) + 1
    nz = max((int(z) for _, _, z in rows if z is not None), default=-1) + 1
    out = []
    for rel, x, z in rows:
        if x is None:
            out.append((rel, None))
            continue
        x0, z0 = -nx * TILE / 2 + int(x) * TILE, -nz * TILE / 2 + int(z) * TILE
        out.append((rel, (x0, z0, x0 + TILE, z0 + TILE)))
    return out


def area_levels(area, age, variant=None):
    """Level files (Banc rels) of one area and age (+ variant), from the gamedb levels index."""
    import common
    levels = common.load("levels")["by_file"]
    out = []
    for rel, rec in levels.items():
        if rec.get("area") != area or rec.get("kind") == "resource" or not rel.endswith(".bcett.byml.zs"):
            continue
        if (rec.get("age") or "").lower() not in ("", age.lower()):
            continue
        if (rec.get("variant") or None) != variant:
            continue
        out.append(rel)
    return sorted(out)

# Labelled, cached collision


class Collision:
    """Collision as flat arrays: tri (n, 3, 3) float32 in world space and part (n,) int32, an index into parts:
    [{"kind": "terrain" | "baked" | "placed", "hash"?, "gyaml"?, "body"?, "layer"?, "sublayer"?, "mask"?,
      "shape"?, "presence"?, "level"?, "tile"?}]."""

    def __init__(self, tri, part, parts, meta=None, mat=None, sub=None, utag=None):
        self.tri, self.part, self.parts, self.meta = tri, part, parts, meta or {}
        n = len(tri)
        self.mat = mat if mat is not None else np.full(n, -1, np.int16)       # PhiveConfig MaterialCollection
        self.sub = sub if sub is not None else np.zeros(n, np.int16)          # SubMaterialCollection
        self.utag = utag if utag is not None else np.zeros(n, np.uint64)      # UserShapeTagMask bits

    def subset(self, keep):
        return Collision(self.tri[keep], self.part[keep], self.parts, self.meta, self.mat[keep], self.sub[keep],
                         self.utag[keep])

    @staticmethod
    def join(cols):
        tris, prt, parts, mat, sub, utag = [], [], [], [], [], []
        for c in cols:
            tris.append(c.tri)
            prt.append(c.part + len(parts))
            parts += c.parts
            mat.append(c.mat)
            sub.append(c.sub)
            utag.append(c.utag)
        if not tris:
            return Collision(np.zeros((0, 3, 3), np.float32), np.zeros(0, np.int32), [])
        return Collision(np.concatenate(tris), np.concatenate(prt).astype(np.int32), parts, None,
                         np.concatenate(mat), np.concatenate(sub), np.concatenate(utag))


class _Builder:
    def __init__(self):
        self.tris, self.part, self.parts, self.mats = [], [], [], []

    def add(self, v, t, info, mats=None):
        if not len(t):
            return
        self.parts.append(info)
        self.tris.append(np.asarray(v, np.float32)[np.asarray(t)])
        self.part.append(np.full(len(t), len(self.parts) - 1, np.int32))
        if mats is None or len(mats[0]) != len(t):
            mats = (np.full(len(t), -1, np.int16), np.zeros(len(t), np.int16), np.zeros(len(t), np.uint64))
        self.mats.append(mats)

    def done(self, meta):
        if not self.tris:
            return Collision(np.zeros((0, 3, 3), np.float32), np.zeros(0, np.int32), [], meta)
        return Collision(np.concatenate(self.tris), np.concatenate(self.part), self.parts, meta,
                         np.concatenate([m[0] for m in self.mats]), np.concatenate([m[1] for m in self.mats]),
                         np.concatenate([m[2] for m in self.mats]))


def _placements_by_pos(fs, levels):
    """{rounded translation: [(level rel, actor)]} over the given levels."""
    out = {}
    for rel in levels:
        try:
            acts = _level(fs, rel).get("Actors") or []
        except (FileNotFoundError, OSError):
            continue
        for a in acts:
            t = a.get("Translate")
            if t is None:
                continue
            out.setdefault(tuple(round(float(x), 2) for x in t), []).append((rel, a))
    return out


def _match_instance(cands, rot, sc):
    """The (err, level rel, actor) whose transform is this instance's, or None."""
    best = None
    for rel, a in cands:
        s = np.array(a.get("Scale") or [1, 1, 1], float)
        if s.shape == ():
            s = np.array([float(s)] * 3)
        err = float(np.abs(_euler_matrix(a.get("Rotate") or (0, 0, 0)) - rot).max()) + float(np.abs(s - sc).max())
        if best is None or err < best[0]:
            best = (err, rel, a)
    return best if best and best[0] < 2e-3 else None


def _body_for(fs, gyaml, kind, v):
    """The actor's body whose primitive has this instance shape's bounding box (shape space), or None."""
    if not len(v):
        return None  # an instance with no vertices (Market_Adult has one), nothing to match
    lo, hi = v.min(axis=0), v.max(axis=0)
    best = None
    for body in _actor_bodies(fs, gyaml):
        for pname, pv, pt, pm in body.prims:
            if not len(pv):
                continue
            err = max(float(np.abs(pv.min(axis=0) - lo).max()), float(np.abs(pv.max(axis=0) - hi).max()))
            if best is None or err < best[0]:
                best = (err, body, pname, pt, pm)
    return best[1:] if best and best[0] < 0.08 else None


def _presence(a):
    p = a.get("Presence")
    if not p:
        return None
    return {k: v for k, v in p.items()} if isinstance(p, dict) else p


def tile_collision(fs, tile_rel, area, age, variant=None, rebuild=False):
    """One tile's collision, labelled and cached. That's the terrain, and the baked instances with their placement,
    body and layer."""
    key = os.path.basename(tile_rel).split(".")[0]
    npz, js = os.path.join(CACHE, key + ".npz"), os.path.join(CACHE, key + ".json")
    cached = _load_cache(npz, js, rebuild)
    if cached:
        return cached
    bypos = _placements_by_pos(fs, area_levels(area, age, variant))
    tp = static_tile(fs, tile_rel)
    bld = _Builder()
    if tp.terrain is not None:
        bld.add(tp.terrain[0], tp.terrain[1], {"kind": "terrain", "tile": tile_rel, "layer": "GroundHighRes"},
                tp.terrain[2])
    rows = []
    for comp, i, rot, tr, sc, kind, v, t in tp.instances:
        info = {"kind": "baked", "tile": tile_rel, "compound": comp, "shape": kind}
        hit = _match_instance(bypos.get(tuple(round(float(x), 2) for x in tr), []), rot, sc)
        mats = None
        if hit:
            _, lrel, a = hit
            info.update(hash=str(a["Hash"]), gyaml=a["Gyaml"], level=lrel)
            if _presence(a):
                info["presence"] = _presence(a)
            bb = _body_for(fs, a["Gyaml"], kind, v)
            if bb:
                body, pname, pt, pm = bb
                info.update(body=body.name, prim=pname, layer=body.layer, sublayer=body.sublayer, mask=body.mask)
                if len(pt) == len(t):          # the baked copy keeps the shape's triangles in order
                    mats = pm
        rows.append((comp, info, (v * sc) @ rot.T + tr, t, mats))
    # A compound holds one layer, so unmatched instances get its most common known layer.
    votes = {}
    for comp, info, *_ in rows:
        if info.get("layer"):
            votes.setdefault(comp, {}).setdefault((info["layer"], info.get("sublayer")), 0)
            votes[comp][(info["layer"], info.get("sublayer"))] += 1
    for comp, info, w, t, mats in rows:
        if not info.get("layer") and votes.get(comp):
            lay, sub = max(votes[comp].items(), key=lambda kv: kv[1])[0]
            info.update(layer=lay, sublayer=sub, layer_from="compound")
        bld.add(w, t, info, mats)
    col = bld.done({"tile": tile_rel, "version": CACHE_VERSION, "origin": None if tp.origin is None
                    else tp.origin.tolist()})
    _save_cache(col, npz, js)
    return col


@functools.lru_cache(maxsize=64)
def _baked_ids(fs, area, age, variant):
    """Placement IDs that have baked shapes in this area's tiles (the tiles' actor tables)."""
    from phive_static import actor_table, NO_SHAPE
    out = set()
    for rel, _ in area_tiles(fs, area, age, variant):
        for pid, (a, _) in actor_table(_read(fs, rel)).items():
            if a != NO_SHAPE:
                out.add(pid)
    return frozenset(out)


def placed_collision(fs, level_rel, area, age, variant=None, rebuild=False):
    """Collision of one level file's placements that aren't baked into the tiles (dynamic objects, unbaked
    pieces), from their actor packs' shapes and the placement transforms, cached."""
    key = os.path.basename(level_rel).split(".")[0] + "__placed"
    npz, js = os.path.join(CACHE, key + ".npz"), os.path.join(CACHE, key + ".json")
    cached = _load_cache(npz, js, rebuild)
    if cached:
        return cached
    baked = _baked_ids(fs, area, age, variant)
    bld = _Builder()
    for a in _level(fs, level_rel).get("Actors") or []:
        if "Translate" not in a:
            continue
        pid = int(((a.get("Phive") or {}).get("Placement") or {}).get("ID", a.get("Hash", 0)))
        if pid in baked:
            continue
        bodies = _actor_bodies(fs, a["Gyaml"])
        if not bodies:
            continue
        m = placement_matrix(a)
        for body in bodies:
            for pname, v, t, mats in body.prims:
                info = {"kind": "placed", "hash": str(a["Hash"]), "gyaml": a["Gyaml"], "level": level_rel,
                        "body": body.name, "prim": pname, "layer": body.layer, "sublayer": body.sublayer,
                        "mask": body.mask}
                if _presence(a):
                    info["presence"] = _presence(a)
                bld.add(v @ m[:, :3].T + m[:, 3], t, info, mats)
    col = bld.done({"level": level_rel, "version": CACHE_VERSION})
    _save_cache(col, npz, js)
    return col


def _json_safe(o):
    if isinstance(o, dict):
        return {str(k): _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, (bool, str)) or o is None:
        return o
    if isinstance(o, int):
        return int(o)
    if isinstance(o, float):
        return float(o)
    return str(o)


def _ensure_cache_dir():
    os.makedirs(CACHE, exist_ok=True)
    ign = os.path.join(os.path.dirname(CACHE), ".gitignore")
    if not os.path.exists(ign):
        with open(ign, "w", encoding="utf-8") as f:
            f.write("# generated by tools/gamedb/build.py; rebuild with: python tools/gamedb/build.py\n*\n")


def _load_cache(npz, js, rebuild):
    if rebuild or not (os.path.exists(npz) and os.path.exists(js)):
        return None
    with open(js, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("meta", {}).get("version") != CACHE_VERSION:
        return None
    z = np.load(npz)
    return Collision(z["tri"], z["part"], doc["parts"], doc["meta"], z["mat"], z["sub"], z["utag"])


def _save_cache(col, npz, js):
    _ensure_cache_dir()
    np.savez_compressed(npz, tri=col.tri, part=col.part, mat=col.mat, sub=col.sub, utag=col.utag)
    with open(js, "w", encoding="utf-8") as f:
        json.dump({"meta": _json_safe(col.meta), "parts": _json_safe(col.parts)}, f, separators=(",", ":"))


def area_collision(fs, area, age, variant=None, center=None, radius=None, rebuild=False, progress=False):
    """Collision of one area and age as one Collision, cached per tile and per level file. That's the tiles (all of
    them, or those within `radius` of `center` (x, z) or (x, y, z)) plus the level files' non-baked placements."""
    cols = []
    cx = cz = None
    if center is not None and radius is not None:
        cx, cz = float(center[0]), float(center[-1])
    for rel, bounds in area_tiles(fs, area, age, variant):
        if cx is not None and bounds is not None:
            x0, z0, x1, z1 = bounds
            dx = max(x0 - cx, 0, cx - x1)
            dz = max(z0 - cz, 0, cz - z1)
            if math.hypot(dx, dz) > radius + 60:      # baked pieces can reach past their tile's edge
                continue
        if progress:
            print("  tile", rel.split("/")[-1], flush=True)
        cols.append(tile_collision(fs, rel, area, age, variant, rebuild))
    for rel in area_levels(area, age, variant):
        if progress:
            print("  level", rel.split("/")[-1], flush=True)
        cols.append(placed_collision(fs, rel, area, age, variant, rebuild))
    col = Collision.join(cols)
    if cx is not None:
        c = col.tri.mean(axis=1)
        r = np.linalg.norm(col.tri - c[:, None, :], axis=2).max(axis=1)
        keep = np.hypot(c[:, 0] - cx, c[:, 2] - cz) - r <= radius
        col = col.subset(keep)
    col.meta = {"area": area, "age": age, "variant": variant, "center": center, "radius": radius}
    return col

# Self-checks


def check(fs):
    """Format self-checks, returns [problem]."""
    import common
    bad = []
    # 1. bounding boxes = ShapeParam AutoCalc, and a closed model decodes closed
    for actor in ("Land_GreatFairyFountain_Base_A_01", "Obj_BrokenRock_A_01"):
        pk = common.pack(fs, f"Pack/Actor/{actor}.pack.zs")
        for k, raw in pk.items():
            if not k.startswith("Phive/ShapeParam/"):
                continue
            sp = common.byml_load(raw)[0]
            for m in sp.get("PhshMesh") or []:
                v, t = _dcc_mesh(fs, dcc_rel(m["PhshMeshPath"]))
                lo, hi = v.min(axis=0), v.max(axis=0)
                ac = sp["AutoCalc"]
                want_lo, want_hi = _v3(ac["Min"]), _v3(ac["Max"])
                if np.abs(lo - want_lo).max() > 2e-3 or np.abs(hi - want_hi).max() > 2e-3:
                    bad.append(f"{m['PhshMeshPath']}: bbox {lo}..{hi} != AutoCalc {want_lo}..{want_hi}")
    v, t = _dcc_mesh(fs, dcc_rel("Obj_BrokenRock_A_01__Physical"))
    edges = {}
    key = [tuple(x) for x in np.round(v, 4).tolist()]
    for tri in t.tolist():
        for i in range(3):
            e = (key[tri[i]], key[tri[(i + 1) % 3]])
            edges[e] = edges.get(e, 0) + 1
    if any(c > 1 for c in edges.values()) or any((b, a) not in edges for a, b in edges):
        bad.append("Obj_BrokenRock_A_01__Physical is not one closed, consistently wound surface")
    # 2. the rotation order: baked instances of KakarikoVillage Child against their placements
    bypos = _placements_by_pos(fs, area_levels("KakarikoVillage", "Child"))
    n = ok = 0
    tiles = sorted((rel for rel, _ in area_tiles(fs, "KakarikoVillage", "Child")),
                   key=lambda r: -os.path.getsize(fs.path(r)))
    for rel in tiles[:4]:                                  # the four biggest tiles: the village itself
        for comp, i, rot, tr, sc, *_ in static_tile(fs, rel).instances:
            for lrel, a in bypos.get(tuple(round(float(x), 2) for x in tr), []):
                r = a.get("Rotate") or (0, 0, 0)
                if min(abs(r[0]), abs(r[1]), abs(r[2])) < 0.05:
                    continue
                n += 1
                ok += bool(np.abs(_euler_matrix(r) - rot).max() < 1e-3)
                break
    if n == 0 or ok < n * 0.99:
        bad.append(f"rotation order Rz Ry Rx matched {ok} of {n} baked instances")
    else:
        print(f"rotation order Rz Ry Rx: {ok} of {n} three-axis baked instances match")
    # 3. terrain tile origins agree with the tile grid
    for area, age in (("DeathMountainTrail", "Child"), ("HyruleField", "Adult")):
        for rel, bounds in area_tiles(fs, area, age)[:3]:
            tp = static_tile(fs, rel)
            if tp.origin is not None and bounds and (abs(tp.origin[0] - bounds[0]) > 1e-3 or
                                                     abs(tp.origin[2] - bounds[1]) > 1e-3):
                bad.append(f"{rel}: terrain origin {tp.origin} != grid {bounds[:2]}")
    return bad


def main(argv):
    import common
    fs = common.open_romfs()
    if not argv or argv[0] == "check":
        probs = check(fs)
        print("\n".join(probs) or "phive_shape: all checks pass")
        return 1 if probs else 0
    if argv[0] == "shape":
        rel = dcc_rel(argv[1])
        v, t = _dcc_mesh(fs, rel)
        print(rel, len(t), "triangles", "bbox", v.min(axis=0).round(3).tolist(), v.max(axis=0).round(3).tolist())
        return 0
    if argv[0] == "area":
        area, age = argv[1], argv[2]
        variant = argv[3] if len(argv) > 3 and not argv[3].startswith("--") else None
        col = area_collision(fs, area, age, variant, rebuild="--rebuild" in argv, progress=True)
        from collections import Counter
        c = Counter((p["kind"], p.get("layer"), p.get("sublayer")) for p in col.parts)
        print(f"{area} {age} {variant or ''}: {len(col.tri)} triangles, {len(col.parts)} parts")
        for k, v in c.most_common():
            print(f"  {v:6d} parts {k}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
