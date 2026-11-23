"""The soul figures. Each soul shows its enemy the way the Hall of Fallen Foes shows it, with the enemy's own materials
and textures. The one-colour glow figures we started with looked like a solid colour and not like real models at
all, and Ganon's cape came out full of jagged holes.

The museum (Banc/DreamWorld/EnemyMuseum, Enemy_DungeonBoss_*_Dictionary actors) uses the boss's own model and
applies the GameActorInfo row's ModelVariationAnims to it:
  - the pose (.fskb, a skeletal anim, base values only)
  - bone visibility (.fvbb, which group bones show and so which shapes, e.g. Twinrova's hair bun off, Volvagia's
    mask and bone states)
  - material anims (.fmab, shader parameter values, e.g. Barinade's DictionaryEmi emission, Volvagia's body
    emission at frame 73)
A shape shows when its bone (FSHP +0x54, a *_GP group bone or Root) is visible. The full boss model costs 2-57 MB
raw (Barinade 57 MB) and its textures 14-45 MB at 1536 x 1536, and that's where my performance rule comes in.

The figure here is a new model file, a smaller copy of the boss's own model.
  - Everything outside the GPU buffers is the boss's, byte for byte: materials, shader assigns and options, samplers,
    skeleton, shapes, vertex formats and skinning. So the game draws it with the boss's own shaders.
  - The museum's variation anims are baked into it at their listed frame. The pose goes into the bone rest
    transforms, with Root and Skl_Root at identity and the figure scaled to SOUL_SIZE and centred on Skl_Root. That
    way the item animation set Item_Token_Gold, which only binds Root and Skl_Root, spins it and holds it up like
    every other display. Visibility goes into the bones' visible flag (hidden shapes keep one degenerate triangle
    and one vertex) and material anims into the materials' parameter values. The skinned vertex data is the boss's
    (UVs, normals, tangents, colours, weights), and the game skins it into the pose itself.
  - Geometry is one of the boss's LOD meshes per shape, drawn by every LOD slot. It's the finest level that keeps the
    figure within FIGURE_TRIS triangles, then the biggest shapes go one level finer while the budget allows. Only
    the vertex block that LOD uses is kept. A small figure doesn't need LOD switching, FIGURE_TRIS is a handful of
    NPC parts.
  - Every texture larger than TEX_MAX is a new copy of the boss's with its top mips dropped, named TEX_PREFIX + its
    name[2:] (same length). Those are the same bytes as the source's smaller mips, because the block-linear layout
    of a mip chain's tail is the same as a texture starting there (checked against every soul texture's mip table).
    Smaller ones stay the game's own files.
  - The skeleton's scaling mode is Maya, with segment scale compensation on most bones. The bake clears that flag on
    the figure's bones and writes each bone's local as its museum world (computed with Maya's compensation) relative
    to its parent. Then the game's plain hierarchy gives the museum pose at the figure's uniform scale. A
    compensating bone keeps its flag where the hierarchy alone would shear it (build's "ssc" and "ssc_k").
The new file is built from the source by "segments" (make_patch new_files, so copies of source byte ranges, zero
padding and new bytes) plus checked same-size edits. That keeps the plan small and every byte traceable.

The display (config/hold_up.json Rando_Show_Soul*) takes the museum actor's ActorInfo heaps (plan()["heap_from"]),
since an instance of this skeleton and these materials needs what the museum figure needs.
"""
import functools
import math
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
import res_dict  # noqa: E402

SOUL_SIZE = 0.40  # metres, the figure's largest extent (same as the one-colour figures, seen in game)
FIGURE_TRIS = 25000  # the figure's triangles over every shown shape (the boss's LOD meshes, finest that fits)
# FIGURE_TRIS is that high because a figure is held up close at 3840 x 2160, and I asked for more detail than 10,000
# and 256.
MIN_PART_TRIS = 12  # a shown part's LOD has at least this many triangles (or is its finest)
TEX_MAX = 512  # a colour texture's largest side (_Alb, _Emc), bigger ones copy from the first mip this size or less
TEX_MAX_DATA = 256  # the same for the other maps (normal, roughness, ambient occlusion, emission masks...)
COLOUR_MAPS = ("_Alb", "_Emc")
TEX_PREFIX = "Rs"  # a reduced texture's name is TEX_PREFIX + name[2:], same length so it's a pooled-name rename
POOL_ALIGN, BUF_ALIGN = 0x1000, 0x100  # the GPU pool's size and each buffer's start (as every source has them)
ANIM_FILE = "Model/{}.anim.bfres.zs"  # a variation anim's project (the folder before "output" in its Work path)
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
GAME_ACTOR_INFO = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"
HEAPS = ("InstanceHeapSize", "PreActorRenderInfoHeapSize")
SSC = 0x00800000  # bone flag: segment scale compensate (Maya scaling)
HINTS = 0x0F000000  # bone flags: ScaleUniform 0x01, ScaleVolumeOne 0x02, RotateZero 0x04, TranslateZero 0x08 (<< 24)
VISIBLE = 0x1

# soul key (extras_souls / _show_models SOUL_DISPLAYS) -> the museum's figure actor and the figure's FmdbName, which is
# the boss's FmdbName with its first word replaced (same length). Ganon's Soul uses the museum's Ganon, the beast from
# the last fight. It used to be the museum's Ganondorf, so the Ganon soul showed Ganondorf.
FIGURES = {
    "gohma": ("Enemy_DungeonBoss_Gohma_Dictionary", "Enemy_DungeonBoss_Gohma", "Rando_DungeonBoss_Gohma"),
    "king_dodongo": ("Enemy_DungeonBoss_Dodongo_Dictionary", "Enemy_DungeonBoss_Dodongo", "Rando_DungeonBoss_Dodongo"),
    "barinade": ("Enemy_DungeonBoss_Barinade_Dictionary", "Enemy_DungeonBoss_Barinade", "Rando_DungeonBoss_Barinade"),
    "phantom_ganon": ("Enemy_DungeonBoss_PhantomGanon_Dictionary", "Npc_DungeonBoss_PhantomGanon",
                      "Rnd_DungeonBoss_PhantomGanon"),
    "volvagia": ("Enemy_DungeonBoss_Volvagia_Dictionary", "Enemy_DungeonBoss_Volvagia", "Rando_DungeonBoss_Volvagia"),
    "morpha": ("Enemy_DungeonBoss_Morpha_Dictionary", "Enemy_DungeonBoss_Morpha", "Rando_DungeonBoss_Morpha"),
    "bongo_bongo": ("Enemy_DungeonBoss_BongoBongo_Dictionary", "Enemy_DungeonBoss_BongoBongo",
                    "Rando_DungeonBoss_BongoBongo"),
    "twinrova": ("Enemy_DungeonBoss_Twinrova_Dictionary", "Enemy_DungeonBoss_Twinrova", "Rando_DungeonBoss_Twinrova"),
    "ganon": ("Enemy_DungeonBoss_Ganon_Dictionary", "Enemy_DungeonBoss_Ganon", "Rando_DungeonBoss_Ganon"),
}


ENEMY_DATA = os.path.join(HERE, "data", "rando", "extras_enemy_souls.json")  # parity/_enemy_souls_build.py


def _enemy_figures():
    """{"enemy_<Family>": (figure actor, project, figure FmdbName)} for the regular-enemy souls (extras_souls kind
    "enemy"). Their Hall of Fallen Foes figures get built the same way as the bosses'."""
    if not os.path.exists(ENEMY_DATA):
        return {}
    fams = json.load(open(ENEMY_DATA, encoding="utf-8"))["families"]
    return {"enemy_" + k: (e["figure"]["actor"], e["figure"]["project"], e["figure"]["figure_fmdb"])
            for k, e in fams.items() if e.get("figure")}


FIGURES.update(_enemy_figures())


def figure_path(key):
    _actor, project, fig = FIGURES[key]
    return f"Model/{project}.{fig}.bfres.zs"


class FigureError(Exception):
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


def _align(x, a):
    return (x + a - 1) // a * a


def _sm():
    from parity import _show_models
    return _show_models


# The museum's figure
@functools.lru_cache(maxsize=4)
def _rows(romfs, table):
    from romtools import byml_load
    fs = _sm()._fs(romfs)
    return {r["__RowId"]: r for r in byml_load(fs.read(table), allow_big=True)[0]}


@functools.lru_cache(maxsize=None)
def museum(key, romfs):
    """{actor, project, fmdb, model, figure_fmdb, path, heaps, anims: [(ext, file, name, frame)]} for soul `key`'s
    Hall of Fallen Foes figure, from its ActorInfo and GameActorInfo rows."""
    actor, listed, fig = FIGURES[key]
    row = _rows(romfs, ACTOR_INFO).get(actor)
    grow = _rows(romfs, GAME_ACTOR_INFO).get(actor)
    if not row or not grow:
        raise FigureError(f"{actor}: no ActorInfo / GameActorInfo row")
    project, fmdb = row["ModelProjectName"], row["FmdbName"]
    if project != listed:
        raise FigureError(f"{actor}: its model project is {project}, not {listed} (FIGURES)")
    if len(fig) != len(fmdb):
        raise FigureError(f"{fig}: must have {len(fmdb)} characters (a same-length rename of {fmdb})")
    anims = []
    for e in grow.get("ModelVariationAnims") or []:
        parts = e["Fmab"].split("/")
        if "output" not in parts:
            raise FigureError(f"{actor}: variation anim {e['Fmab']} isn't a Work/Model/.../output path")
        name, ext = parts[-1].rsplit(".", 1)
        if ext not in ("fskb", "fvbb", "fmab"):
            raise FigureError(f"{actor}: variation anim kind .{ext} ({e['Fmab']})")
        if e.get("IsPlay") is False:
            continue  # bound but not applied
        anims.append((ext, ANIM_FILE.format(parts[parts.index("output") - 1]), name, float(e.get("Frame") or 0.0)))
    return {"actor": actor, "project": project, "fmdb": fmdb, "model": f"Model/{project}.{fmdb}.bfres.zs",
            "figure_fmdb": fig, "path": f"Model/{project}.{fig}.bfres.zs",
            "heaps": {k: int(row.get(k) or 0) for k in HEAPS}, "anims": anims}


# Animation readers (BFRES 10.4)
def _find(d, magic, name):
    for m in re.finditer(magic, d):
        o = m.start()
        try:
            if _str(d, _q(d, o + 8)) == name:
                return o
        except (struct.error, IndexError):
            continue
    raise FigureError(f"no {magic.decode()} {name}")


def _frames(d, cc):
    ptr, n, ftype = _q(d, cc), _u16(d, cc + 0x12), _u16(d, cc + 0x10) & 3
    if ftype == 0:
        return list(struct.unpack_from(f"<{n}f", d, ptr))
    if ftype == 1:
        return [x / 32.0 for x in struct.unpack_from(f"<{n}h", d, ptr)]
    return list(d[ptr:ptr + n])


def curve_at(d, cc, frame):
    """A curve's value at `frame`, only read where the curve holds a key (at or before its first key's frame, or on a
    key frame). The value a key starts with is the first number of its key, for any curve type. For bool curves it's
    the key's bit. Integer keys are offset (+0x20) + scale (+0x24) x key. Between two keys only a float cubic or
    linear curve is read, with the key's own polynomial (see below). Anything else gets refused, we never interpolate
    by guessing."""
    flags = _u16(d, cc + 0x10)
    ktype, ctype = (flags >> 2) & 3, (flags >> 4) & 7
    frames = _frames(d, cc)
    if ctype in (2, 5, 7):  # baked: one key per frame from the start frame
        k = int(round(frame - struct.unpack_from("<f", d, cc + 0x18)[0]))
        if abs(frame - round(frame)) > 1e-6:
            raise FigureError("a baked curve read between frames")
        k = max(0, min(k, _u16(d, cc + 0x12) - 1))
    elif frame <= frames[0] + 1e-6:
        k = 0
    else:
        hit = [i for i, f in enumerate(frames) if abs(f - frame) < 1e-4]
        if not hit:
            # Between two keys of a float cubic (4 numbers a key) or linear (2) curve we use the key's own polynomial at
            # t = (frame - key) / (next key - key), as the curve stores it. The enemy souls need this, Beamos' museum
            # frame 400 sits between keys 303 and 401. Anything else is still refused.
            seg = [i for i in range(len(frames) - 1) if frames[i] < frame < frames[i + 1]]
            if not seg or ktype != 0 or ctype not in (0, 1):
                raise FigureError(f"curve read at frame {frame}, between its keys {frames}")
            k = seg[0]
            t = (frame - frames[k]) / (frames[k + 1] - frames[k])
            n = 4 if ctype == 0 else 2
            c = struct.unpack_from(f"<{n}f", d, _q(d, cc + 8) + 4 * n * k)
            return sum(c[j] * t ** j for j in range(n))
        k = hit[0]
    keys = _q(d, cc + 8)
    if ctype in (6, 7):
        return bool((d[keys + k // 8] >> (k % 8)) & 1)
    group = {0: 4, 1: 2}.get(ctype, 1)
    i = k * group
    if ktype == 0:
        return struct.unpack_from("<f", d, keys + 4 * i)[0]
    raw = struct.unpack_from("<h", d, keys + 2 * i)[0] if ktype == 1 else struct.unpack_from("<b", d, keys + i)[0]
    off, scale = struct.unpack_from("<ff", d, cc + 0x20)
    return off + scale * raw


def bone_visibility(d, name, frame):
    """{bone: visible} of bone visibility anim `name` at `frame` (base bits, then its curves)."""
    o = _find(d, b"FBVS", name)
    n, nc = struct.unpack_from("<HH", d, o + 0x58)
    names = [_str(d, _q(d, _q(d, o + 0x38) + 8 * i)) for i in range(n)]
    base = _q(d, o + 0x30)
    out = {names[i]: bool((d[base + i // 8] >> (i % 8)) & 1) for i in range(n)}
    for c in range(nc):
        cc = _q(d, o + 0x28) + 0x30 * c
        out[names[_u32(d, cc + 0x14)]] = bool(curve_at(d, cc, frame))
    return out


def material_values(d, name, frame):
    """{material: [(param name hash, byte offset in the param, 4 bytes)]} for material anim `name` at `frame`. That's
    its constants as stored and its curves' values (float curves as f32, integer ones as i32). Texture pattern and
    material visibility anims are refused, none of the museum's use them."""
    o = _find(d, b"FMAA", name)
    out = {}
    for k in range(_u16(d, o + 0x62)):
        e = _q(d, o + 0x28) + 0x40 * k
        mat = _str(d, _q(d, e))
        # e + 0x10 / e + 0x34 is a texture pattern part, a colour or element variant of an enemy figure (Keese,
        # Floormaster, Peahat, Deku Baba, Flying Pot, Guay). We leave it out so the figure keeps its model's own
        # textures, and the anim's other parts still apply.
        vals = []
        for p in range(_u16(d, e + 0x32)):
            pp = _q(d, e + 8) + 0x18 * p
            h = _q(d, pp)
            bc, nf, ni, bk, nk = struct.unpack_from("<HHHHH", d, pp + 8)
            for c in range(bk, bk + nk):
                cs = _q(d, e + 0x20) + 8 * c
                vals.append((h, _u32(d, cs), d[cs + 4:cs + 8]))
            for c in range(bc, bc + nf + ni):
                cc = _q(d, e + 0x18) + 0x30 * c
                v = curve_at(d, cc, frame)
                vals.append((h, _u32(d, cc + 0x14), struct.pack("<f", v) if c < bc + nf else struct.pack("<i", int(v))))
        out.setdefault(mat, []).extend(vals)
    return out


def material_params(d, fmat):
    """{param name hash: (file offset of its value, type)} of material `fmat` (FMAT offset)."""
    sa = _q(d, _q(d, fmat + 0x10))
    arr, data = _q(d, sa + 0x20), _q(d, fmat + 0x58)
    out = {}
    for i in range(_u16(d, sa + 0x4A)):
        off, typ = struct.unpack_from("<HH", d, arr + 24 * i + 16)
        out[_q(d, arr + 24 * i + 8)] = (data + off, typ)
    return out


# The skeleton
def _bone_base(d):
    sk = _q(d, _q(d, 0x28) + 0x18)
    if d[sk:sk + 4] != b"FSKL":
        raise FigureError("no skeleton")
    return _q(d, sk + 0x10)


def bone_flags(d):
    ba = _bone_base(d)
    return [_u32(d, ba + 0x58 * i + 0x2C) for i in range(_u16(d, _q(d, _q(d, 0x28) + 0x18) + 0x38))]


def _trs(s, r, t):
    import numpy as np
    m = np.eye(4)
    m[:3, :3] = _sm()._euler(r) @ np.diag(s)
    m[:3, 3] = t
    return m


def worlds_maya(bones, flags, pose):
    """World matrices of `bones` in `pose` ({bone: {s, r, t}}, else the rest) as the game computes them in Maya scaling
    mode. A bone with segment scale compensation doesn't inherit its parent's scale for its own rotation and scale,
    but its translation does (W = parent W . T(t) . S(parent)^-1 . R . S)."""
    import numpy as np
    out, scales = [], []
    for i, b in enumerate(bones):
        e = pose.get(b["name"], {})
        s, r, t = (np.array(e.get(k, b[k]), dtype=float) for k in ("s", "r", "t"))
        scales.append(s)
        if b["parent"] < 0:
            out.append(_trs(s, r, t))
            continue
        local = _trs(s, r, t)
        if flags[i] & SSC:
            local[:3, :3] = np.diag(1.0 / scales[b["parent"]]) @ local[:3, :3]
        out.append(out[b["parent"]] @ local)
    return out


def _uniform_ratio(written, museum):
    """k if scale `written` is scale `museum` times k on every axis (within float32 rounding), else None."""
    if written is None or any(abs(float(m)) < 1e-9 for m in museum):
        return None
    r = [float(w) / float(m) for w, m in zip(written, museum)]
    k = sum(r) / len(r)
    return k if k > 0 and all(abs(x - k) <= 1e-5 * k for x in r) else None


def worlds_plain(locals_):
    out = []
    for m, p in locals_:
        out.append(m if p < 0 else out[p] @ m)
    return out


def _euler_of(m):
    """Euler XYZ (R = Rz Ry Rx, the skeleton's rotation mode) of a rotation matrix."""
    sy = -m[2, 0]
    sy = max(-1.0, min(1.0, sy))
    y = math.asin(sy)
    if abs(math.cos(y)) > 1e-6:
        x, z = math.atan2(m[2, 1], m[2, 2]), math.atan2(m[1, 0], m[0, 0])
    else:  # gimbal: z = 0
        x, z = math.atan2(-m[1, 2], m[1, 1]), 0.0
    return x, y, z


def decompose(m):
    """(scale, Euler XYZ, translation, shear error) of an affine matrix, with scale > 0 and the nearest rotation."""
    import numpy as np
    a = m[:3, :3]
    s = np.linalg.norm(a, axis=0)
    r = a / s
    u, _, vt = np.linalg.svd(r)
    rot = u @ vt
    if np.linalg.det(rot) < 0:
        raise FigureError("a mirrored bone")
    err = float(np.abs(rot @ np.diag(s) - a).max())
    return s, _euler_of(rot), m[:3, 3].copy(), err


def hint_flags(s, r, t):
    """The transform hint bits of the bone flags for a local (s, r[:3], t), set the way the game's bones have them."""
    f = 0
    if s[0] == s[1] == s[2]:
        f |= 0x01000000
    if s[0] * s[1] * s[2] == 1.0:
        f |= 0x02000000
    if r[0] == r[1] == r[2] == 0.0:
        f |= 0x04000000
    if t[0] == t[1] == t[2] == 0.0:
        f |= 0x08000000
    return f


# Skinning (where the figure's vertices land)
_ATTR = {0x0B: (4, 1), 0x02: (1, 1), 0x09: (2, 1), 0x0A: (1, 2), 0x12: (2, 2), 0x15: (4, 2)}  # (count, bytes)


def vertex_positions(d, sh, rows, world, m2b, inv, shape_bone):
    """Skinned positions of vertex records `rows` (indices into shape `sh`'s buffer) with bone world matrices `world`.
    Smooth skinning uses world . inverse bind, rigid uses the vertex's bone and skin 0 uses the shape's bone."""
    import numpy as np
    rec = np.frombuffer(d, np.uint8, sh["count"] * sh["stride"], sh["vbuf"]).reshape(sh["count"], sh["stride"])[rows]
    fmt, off = sh["attrs"]["_p0"]
    if fmt == 0x1805:
        xyz = rec[:, off:off + 12].copy().view("<f4").reshape(-1, 3)
    elif fmt == 0x1505:
        xyz = rec[:, off:off + 8].copy().view("<f2").reshape(-1, 4)[:, :3]
    else:
        raise FigureError(f"positions in format {fmt:#x}")
    pos = np.c_[xyz.astype(np.float64), np.ones(len(rec))]
    if sh["skin"] >= 2:
        palette = np.array([world[m2b[i]] @ inv[i] for i in range(len(inv))])

        def gather(prefix):
            cols = []
            for j in range(4):
                if f"{prefix}{j}" not in sh["attrs"]:
                    break
                f, o = sh["attrs"][f"{prefix}{j}"]
                n, w = _ATTR[f >> 8]
                v = rec[:, o:o + n * w].copy()
                v = v.view("<u2").reshape(-1, n) if w == 2 else v
                cols.append(v.astype(np.float64) / (65535.0 if prefix == "_w" and w == 2 else
                                                     255.0 if prefix == "_w" else 1.0))
            return np.concatenate(cols, 1)[:, :sh["skin"]]
        bi, bw = gather("_i").astype(np.int64), gather("_w")
        out = np.zeros((len(rec), 4))
        for j in range(sh["skin"]):
            out += bw[:, j:j + 1] * np.einsum("nij,nj->ni", palette[bi[:, j]], pos)
        return out[:, :3]
    if sh["skin"] == 1:
        f, o = sh["attrs"]["_i0"]
        n, w = _ATTR[f >> 8]
        v = rec[:, o:o + w].copy()
        mats = np.array([world[m2b[i]] for i in (v.view("<u2").ravel() if w == 2 else v.ravel())])
    else:
        mats = np.array([world[shape_bone]] * len(rec))
    return np.einsum("nij,nj->ni", mats, pos)[:, :3]


def _lod_rows(d, m):
    """(vertex rows [first, first + max index], the LOD's index array)."""
    import numpy as np
    idx = np.frombuffer(d, "<u2", m["count"], m["ibuf"]).astype(np.int64)
    return np.arange(m["first"], m["first"] + int(idx.max()) + 1), idx


# Textures
def reduced_name(name):
    return TEX_PREFIX + name[2:]


def bntx_info(d):
    """{name, fmt, w, h, mips, block_log, size, start, mips_at, ptrs, brti, brtd} of a one-texture BNTX."""
    from parity import _cosmetics_tex as tex
    if d[:4] != b"BNTX" or _u32(d, 0x24) != 1:
        raise FigureError("not a one-texture BNTX")
    t = tex.bntx_textures(d)[0]
    b = t["brti"]
    mips_at = _q(d, b + 0x70)
    ptrs = [_q(d, mips_at + 8 * i) for i in range(t["mips"])]
    return {"name": t["name"], "fmt": t["fmt"], "w": t["w"], "h": t["h"], "mips": t["mips"],
            "block_log": _u32(d, b + 0x34) & 7, "size": _u32(d, b + 0x50), "start": ptrs[0], "mips_at": mips_at,
            "ptrs": ptrs, "brti": b, "brtd": _q(d, 0x30)}


_ASTC = {0x2D: (4, 4), 0x2E: (5, 4), 0x2F: (5, 5), 0x30: (6, 5), 0x31: (6, 6), 0x32: (8, 5), 0x33: (8, 6),
         0x34: (8, 8), 0x35: (10, 5), 0x36: (10, 6), 0x37: (10, 8), 0x38: (10, 10), 0x39: (12, 10), 0x3A: (12, 12)}


def _block(fmt):
    if fmt in _ASTC:
        return _ASTC[fmt] + (16,)
    if fmt in (0x1A, 0x1D):
        return 4, 4, 8
    if fmt in (0x1B, 0x1C, 0x1E, 0x1F, 0x20):
        return 4, 4, 16
    raise FigureError(f"texture format {fmt:#x}")


def mip_layout(w, h, mips, fmt, block_log):
    """[(size, block height log2)] for each mip of a block-linear texture. Tegra's rule is that a mip's block height
    shrinks while the mip is at most half a block high."""
    bw, bh, bpb = _block(fmt)
    out = []
    for i in range(mips):
        mw, mh = max(1, w >> i), max(1, h >> i)
        nx, ny = -(-mw // bw), -(-mh // bh)
        gw = -(-nx * bpb // 64)
        b = 1 << block_log
        while b > 1 and ny <= 8 * (b // 2):
            b //= 2
        out.append((gw * 512 * b * -(-ny // (8 * b)), b.bit_length() - 1))
    return out


def texture_cap(name):
    """A texture's largest side in a figure. Colour maps (_Alb, _Emc, also numbered like _Alb.0) get TEX_MAX and the
    other maps TEX_MAX_DATA. Lookup tables (LUT in the name) are never reduced, since they're sampled by value, not
    by place."""
    if "LUT" in name.upper().split("_"):
        return 1 << 30
    return TEX_MAX if re.search(r"_(%s)(\.\d+)?$" % "|".join(m[1:] for m in COLOUR_MAPS), name) else TEX_MAX_DATA


def texture_drop(t):
    """How many top mips texture info `t` loses, so its largest side is texture_cap or less, keeping at least one
    mip."""
    n, cap = 0, texture_cap(t["name"])
    while n < t["mips"] - 1 and max(t["w"] >> n, t["h"] >> n) > cap:
        n += 1
    return n


def texture_op(name, fs):
    """The make_patch new_files op for the reduced copy of figure texture `name` (None if it's TEX_MAX or less), and
    {source and new sizes}. The copy is the source's header blocks, its data from mip n on, padding and a new
    relocation table. The edits are the texture's size, mip count, block height, data size, mip pointers, the data
    block's and the file's sizes, and the relocation table's offset."""
    rel = f"Tex/{name}.bntx.zs"
    d = fs.read(rel)
    t = bntx_info(d)
    n = texture_drop(t)
    if n == 0:
        return None, {"name": name, "bytes": len(d), "kept": True}
    lay = mip_layout(t["w"], t["h"], t["mips"], t["fmt"], t["block_log"])
    offs = [sum(s for s, _ in lay[:i]) for i in range(t["mips"])]
    if [p - t["start"] for p in t["ptrs"]] != offs or sum(s for s, _ in lay) != t["size"]:
        raise FigureError(f"{rel}: its mip table isn't the block-linear layout")
    new_mips = t["mips"] - n
    new_lay = mip_layout(t["w"] >> n, t["h"] >> n, new_mips, t["fmt"], lay[n][1])
    if [s for s, _ in new_lay] != [s for s, _ in lay[n:]]:
        raise FigureError(f"{rel}: the tail of its mips isn't a texture of its own")
    tail = d[t["ptrs"][n]:t["start"] + t["size"]]
    new_size = len(tail)
    r = _u32(d, 0x18)
    if d[r:r + 4] != b"_RLT" or _u32(d, r + 8) != 2 or t["start"] + t["size"] > r:
        raise FigureError(f"{rel}: unexpected relocation table")
    rlt_new = _align(t["start"] + new_size, POOL_ALIGN)
    rlt = bytearray(d[r:])
    struct.pack_into("<I", rlt, 4, rlt_new)
    sec1 = 0x10 + 0x18
    if _u32(rlt, sec1 + 8) != t["brtd"]:
        raise FigureError(f"{rel}: its data section isn't the BRTD block")
    struct.pack_into("<I", rlt, sec1 + 12, rlt_new - t["brtd"])
    segs = [{"copy": [0, t["start"]]}, {"copy": [t["ptrs"][n], new_size]},
            {"zero": rlt_new - t["start"] - new_size}, {"hex": bytes(rlt).hex()}]
    edits = []
    b = t["brti"]

    def put(off, new):
        old = d[off:off + len(new)]
        if old != new:
            edits.append({"offset": off, "expect": old.hex(), "bytes": new.hex()})
    put(0x18, struct.pack("<II", rlt_new, rlt_new + len(rlt)))
    put(b + 0x16, struct.pack("<H", new_mips))
    put(b + 0x24, struct.pack("<II", t["w"] >> n, t["h"] >> n))
    put(b + 0x34, struct.pack("<I", (_u32(d, b + 0x34) & ~7) | lay[n][1]))
    put(b + 0x50, struct.pack("<I", new_size))
    ptrs = [t["start"] + offs[i] - offs[n] for i in range(n, t["mips"])]
    ptrs += [ptrs[-1]] * n  # the table keeps its length, every slot a valid pointer
    put(t["mips_at"], struct.pack(f"<{t['mips']}Q", *ptrs))
    put(t["brtd"] + 8, struct.pack("<Q", rlt_new - t["brtd"]))
    new = reduced_name(name)
    renames = [[name, new]]
    op = {"to": f"Tex/{new}.bntx.zs", "from": rel, "segments": segs, "rename": renames,
          "bytes": edits + res_dict.edits(d, renames),
          "note": f"{name} from mip {n} ({t['w'] >> n} x {t['h'] >> n}): a soul figure's texture "
                  f"(parity/_soul_figures.py)"}
    return op, {"name": name, "bytes": len(d), "new_bytes": rlt_new + len(rlt), "drop": n,
                "size": [t["w"] >> n, t["h"] >> n]}


# The figure
def union_sphere(c, r, r2):
    """(x, y, z, radius) of the smallest sphere holding sphere (c, r) and the sphere of radius r2 about the origin."""
    dist = math.sqrt(sum(x * x for x in c))
    if r >= dist + r2:
        return (*c, r)
    if r2 >= dist + r:
        return (0.0, 0.0, 0.0, r2)
    nr = (dist + r + r2) / 2
    k = (nr - r2) / dist
    return (c[0] * k, c[1] * k, c[2] * k, nr * 1.0001)


def pool_string(name):
    b = name.encode()
    return struct.pack("<H", len(b)) + b + b"\0"


def splice(src, segments):
    """make_patch's "segments": the new file's bytes from source copies, zero padding and new bytes."""
    out = bytearray()
    for s in segments:
        if "copy" in s:
            o, n = s["copy"]
            if o < 0 or o + n > len(src):
                raise FigureError(f"segment copy {o:#x}+{n:#x} runs past the source")
            out += src[o:o + n]
        elif "zero" in s:
            out += bytes(s["zero"])
        else:
            out += bytes.fromhex(s["hex"])
    return bytes(out)


def _shape_bone_visible(bones, vis, i):
    while i >= 0:
        if not vis[i]:
            return False
        i = bones[i]["parent"]
    return True


# The built figure, kept on disk
# generate, make_patch and in_game_check each need every figure (31 in an enemy-souls seed, ~12 s per step), and a
# figure is the same for every seed. So build() keeps its result in cache/soul_figures/<key>-<stamp>.pkl, the pickled
# (op, texture ops, info) exactly as the build returned it. The stamp covers everything it comes from: the figure, the
# romfs and the originals folder, the code it runs and Python's and numpy's versions. I traced CACHE_CODE, those are
# the only project files a cold build of all 33 figures runs. The entry also lists every game file the build resolved
# (Romfs.path reads and existence checks, the zstd dictionary and the ActorInfo tables museum() reads) with its
# resolved path, size and time, and any change there rebuilds it.
# REMAKE_NO_CACHE=1 turns the cache off for reads and writes. If we can't write to the folder there's no cache, and
# the figure comes out the same.
CACHE_DIR = os.path.join(HERE, "cache", "soul_figures")
CACHE_CODE = ("tools/rando/parity/_soul_figures.py", "tools/rando/parity/_show_models.py",
              "tools/rando/parity/_appearance_bfres.py", "tools/rando/parity/_cosmetics_tex.py",
              "tools/rando/res_dict.py", "tools/romtools.py", "data/rando/extras_enemy_souls.json")


@functools.lru_cache(maxsize=None)
def _code_stamp():
    import hashlib
    import numpy
    h = hashlib.sha1(f"{sys.version}|{numpy.__version__}".encode())
    for rel in CACHE_CODE:
        p = os.path.join(HERE, rel)
        h.update(f"|{rel}|".encode() + (open(p, "rb").read() if os.path.exists(p) else b"(none)"))
    return h.hexdigest()


def _file_stamp(fs, rel):
    p = fs.path(rel)
    try:
        st = os.stat(p)
        return [rel, p, st.st_size, st.st_mtime_ns]
    except OSError:
        return [rel, p, None, None]


def _cache_file(key, romfs, fs):
    import hashlib
    stamp = hashlib.sha1(json.dumps([key, romfs, fs.vanilla, _code_stamp()]).encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}-{stamp}.pkl")


@functools.lru_cache(maxsize=None)
def build(key, romfs):
    """(model op, texture ops, info) for soul `key`'s figure (_build). It comes from the disk cache when nothing it's
    built from has changed."""
    import pickle
    if os.environ.get("REMAKE_NO_CACHE") == "1":
        return _build(key, romfs)
    from romtools import Romfs
    fs = _sm()._fs(romfs)
    path = _cache_file(key, romfs, fs)
    try:
        with open(path, "rb") as f:
            entry = pickle.load(f)
        if all(_file_stamp(fs, rec[0]) == rec for rec in entry["files"]):
            return entry["result"]
    except (OSError, EOFError, pickle.UnpicklingError, KeyError, TypeError, ValueError, AttributeError,
            IndexError, ImportError):
        pass
    seen, plain = {}, Romfs.path

    def recording(self, rel):  # every game file the build resolves (reads and existence checks)
        p = plain(self, rel)
        seen.setdefault(rel, None)
        return p
    Romfs.path = recording
    try:
        museum.__wrapped__(key, romfs)  # for its reads, in case an earlier call cached it
        fs2 = _sm()._fs(romfs)
        fs2.path(ACTOR_INFO), fs2.path(GAME_ACTOR_INFO)
        result = _build(key, romfs)
    finally:
        Romfs.path = plain
    tmp = f"{path}.{os.getpid()}.tmp"
    try:  # written whole, then moved into place like packpaths.index, and older entries of this figure get removed
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(tmp, "wb") as f:
            pickle.dump({"files": [_file_stamp(fs, rel) for rel in seen], "result": result}, f,
                        protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
        import glob
        for old in glob.glob(os.path.join(CACHE_DIR, glob.escape(key) + "-*.pkl")):
            if os.path.normcase(old) != os.path.normcase(path):
                os.remove(old)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return result


def _build(key, romfs):
    """(model op, texture ops, info) for soul `key`'s figure. The module doc explains how it's built."""
    import numpy as np
    sm = _sm()
    fs = sm._fs(romfs)
    mu = museum(key, romfs)
    d = fs.read(mu["model"])
    lay = sm.layout(d)
    bones, m2b, inv = sm._skeleton(d)
    names = [b["name"] for b in bones]
    flags = bone_flags(d)
    ba = _bone_base(d)
    # the museum's variation anims at their frames
    pose, vis_set, mat_set = {}, {}, {}
    cache = {}
    for ext, rel, name, frame in mu["anims"]:
        data = cache.get(rel) or cache.setdefault(rel, fs.read(rel))
        if ext == "fskb":
            pose.update(sm._pose(data, name))
        elif ext == "fvbb":
            vis_set.update(bone_visibility(data, name, frame))
        else:
            for mat, vals in material_values(data, name, frame).items():
                mat_set.setdefault(mat, []).extend(vals)
    unknown = [n for n in list(vis_set) if n not in names]
    vis = [vis_set.get(n, bool(flags[i] & VISIBLE)) for i, n in enumerate(names)]
    # The shapes shown and the one LOD each keeps. First the game's LOD meshes at one level for every shape (the finest
    # level within FIGURE_TRIS), then the shapes with the most triangles go one level finer while the total allows.
    shapes = sorted(lay["shapes"].items(), key=lambda kv: kv[1]["at"])
    shown = {n: _shape_bone_visible(bones, vis, _u16(d, sh["at"] + 0x54)) for n, sh in shapes}

    def tris(n, k):
        ms = lay["shapes"][n]["meshes"]
        return ms[min(k, len(ms) - 1)]["count"] // 3
    deepest = max(len(sh["meshes"]) for n, sh in shapes)
    lvl = next((k for k in range(deepest) if sum(tris(n, k) for n in shown if shown[n]) <= FIGURE_TRIS), deepest - 1)
    level = {n: min(lvl, len(lay["shapes"][n]["meshes"]) - 1) for n in shown if shown[n]}
    for n in level:  # a shape's coarsest LODs can be a triangle or two, so those small parts take a finer one
        while level[n] > 0 and tris(n, level[n]) < MIN_PART_TRIS:
            level[n] -= 1
    changed = True
    while changed:
        changed = False
        total = sum(tris(n, level[n]) for n in level)
        for n in sorted(level, key=lambda x: -tris(x, level[x])):
            if level[n] > 0 and total - tris(n, level[n]) + tris(n, level[n] - 1) <= FIGURE_TRIS:
                total += tris(n, level[n] - 1) - tris(n, level[n])
                level[n] -= 1
                changed = True
    # the museum pose's worlds (Maya scaling), the figure's centre and scale from LOD 0 of the shown shapes
    world_m = worlds_maya(bones, flags, pose)
    pts = []
    for n, sh in shapes:
        if shown[n]:
            rows, _ = _lod_rows(d, sh["meshes"][level[n]])
            pts.append(vertex_positions(d, sh, rows, world_m, m2b, inv, _u16(d, sh["at"] + 0x54)))
    pts = np.concatenate(pts)
    lo, hi = pts.min(0), pts.max(0)
    s = SOUL_SIZE / float((hi - lo).max())
    centre = (lo + hi) / 2
    C = np.eye(4) * s
    C[3, 3] = 1.0
    C[:3, 3] = -s * centre
    # The figure's bone locals. Root and Skl_Root are identity, and the bones under Skl_Root sit at C . museum world,
    # relative to their parent, with segment scale compensation off.
    skl = names.index("Skl_Root")
    path, i = [], skl  # Root ... Skl_Root stay identity in the figure since the item animations set Root and Skl_Root
    while i >= 0:
        path.append(i)
        i = bones[i]["parent"]
    if bones[0]["name"] != "Root" or path[-1] != 0:
        raise FigureError(f"{mu['model']}: Skl_Root isn't under Root")

    def under(i):
        while i >= 0:
            if i == skl:
                return True
            i = bones[i]["parent"]
        return False
    for n, sh in shapes:
        if shown[n] and sh["skin"] == 0 and not under(_u16(d, sh["at"] + 0x54)):
            raise FigureError(f"{n}: a skin-0 shape on a bone outside Skl_Root")
    edits = []

    def put(off, new):
        old = d[off:off + len(new)]
        if old != new:
            edits.append({"offset": off, "expect": old.hex(), "bytes": new.hex()})
    # Each bone under Skl_Root, parents first. Its world has to come out as C . its museum world, and we use the first
    # of these that holds:
    #   "museum": a bone without segment scale compensation keeps the museum's local (plain parent world . local).
    #   "ssc": a compensating bone keeps the museum's local and its flag when its parent's written scale is the
    #     museum's. The game then compensates like in the museum, whichever way it does that, so it's exact without us
    #     reading it.
    #   "world": otherwise (Skl_Root's children, which carry the figure's scale) the local is the museum world relative
    #     to the parent's, with the flag off (the game's plain hierarchy). "shear" is how far that local is from a
    #     scale-rotate-translate, 0 when the parent's museum scale is uniform.
    #   "ssc_k": where "world" would shear, a compensating bone whose parent's written scale is the parent's museum
    #     scale times one number k keeps its flag and the museum's local, with its scale times k. Maya's W = parent W .
    #     T(t) . S(parent)^-1 . R . S then gives C . its museum world exactly (k cancels), and its written scale is
    #     again its museum scale times k for its own children. Through "world" the Like Like's spine and lips and the
    #     Peahat's blades ended up 56 and 13 mm off the museum pose.
    if any(bones[i]["parent"] >= i for i in range(1, len(bones))):
        raise FigureError(f"{mu['model']}: bones aren't parents-first")
    shear, written, modes = 0.0, {}, {}
    for i in range(len(bones)):
        if not (i in path or under(i)):
            continue
        b = ba + 0x58 * i
        e = pose.get(names[i], {})
        m_s, m_r, m_t = (tuple(float(x) for x in e.get(k, bones[i][k])) for k in ("s", "r", "t"))
        p = bones[i]["parent"]
        f = flags[i]
        if i in path:
            sc, rot, tr, mode = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), "identity"
            f &= ~SSC
        elif p not in path and not (flags[i] & SSC):
            sc, rot, tr, mode = m_s, m_r[:3], m_t, "museum"
        elif p not in path and written[p][0] == tuple(float(x) for x in pose.get(names[p], {}).get("s", bones[p]["s"])):
            sc, rot, tr, mode = m_s, m_r[:3], m_t, "ssc"
        else:
            local = C @ world_m[i] if p in path else np.linalg.inv(world_m[p]) @ world_m[i]
            f &= ~SSC
            if p not in path and np.abs(local - _trs(np.array(m_s), m_r, np.array(m_t))).max() < 1e-5:
                sc, rot, tr, mode = m_s, m_r[:3], m_t, "museum"  # same local, so its museum values exactly
            else:
                sv, rv, tv, err = decompose(local)
                k = (_uniform_ratio(written[p][0], pose.get(names[p], {}).get("s", bones[p]["s"]))
                     if err > 1e-6 and flags[i] & SSC and p not in path else None)
                if k is not None:  # see "ssc_k" above
                    f |= SSC
                    sc, rot, tr, mode = tuple(k * x for x in m_s), m_r[:3], m_t, "ssc_k"
                else:
                    shear = max(shear, err)
                    sc, rot, tr, mode = tuple(float(x) for x in sv), tuple(float(x) for x in rv),                         tuple(float(x) for x in tv), "world"
        sc, rot, tr = (tuple(float(np.float32(x)) for x in v) for v in (sc, rot, tr))
        put(b + 0x30, struct.pack("<3f4f3f", *sc, *rot, 1.0, *tr))
        f = (f & ~HINTS) | hint_flags(sc, rot, tr)
        f = (f & ~VISIBLE) | (VISIBLE if vis[i] else 0)
        put(b + 0x2C, struct.pack("<I", f))
        written[i] = (sc, rot, tr)
        modes[mode] = modes.get(mode, 0) + 1
    target = written
    for i, n in enumerate(names):  # visibility of the bones outside Skl_Root (the *_GP groups)
        if i not in target:
            put(ba + 0x58 * i + 0x2C, struct.pack("<I", (flags[i] & ~VISIBLE) | (VISIBLE if vis[i] else 0)))
    # material anims: parameter values
    mats = {}
    for k in range(_u16(d, _q(d, 0x28) + 0x6C)):
        m = _q(d, _q(d, 0x28) + 0x38) + 0xB0 * k
        mats[_str(d, _q(d, m + 8))] = m
    baked = 0
    for mat, vals in sorted(mat_set.items()):
        if mat not in mats:
            continue  # an anim for a material this model doesn't have
        params = material_params(d, mats[mat])
        for h, off, raw in vals:
            if h not in params:
                continue
            put(params[h][0] + off, raw)
            baked += 1
    # the new GPU pool: index buffers, then vertex buffers
    pool = _q(d, _q(d, 0xB0) + 8)
    old_pool_size = _u32(d, _q(d, 0xB0) + 4)
    old_mempool = pool + old_pool_size
    if _q(d, 0xA8) != old_mempool:
        raise FigureError(f"{mu['model']}: the memory pool isn't right after the buffers")
    segs = [{"copy": [0, pool]}]
    cur = pool
    plan_ib, plan_vb, info_shapes = {}, {}, {}
    zero_ib = None

    def pad_to(a):
        nonlocal cur
        p = _align(cur, a) - cur
        if p:
            segs.append({"zero": p})
            cur += p
    for n, sh in shapes:
        meshes = sh["meshes"]
        if not shown[n]:
            if zero_ib is None:
                pad_to(BUF_ALIGN)
                zero_ib = cur - pool
                segs.append({"hex": "00" * 6})
                cur += 6
            plan_ib[n] = None
            continue
        k0 = level[n]
        offs = {}
        for k in (k0,):
            pad_to(BUF_ALIGN)
            offs[k] = cur - pool
            segs.append({"copy": [meshes[k]["ibuf"], meshes[k]["count"] * 2]})
            cur += meshes[k]["count"] * 2
        plan_ib[n] = offs
    pad_to(BUF_ALIGN)
    sec1 = cur - pool
    for n, sh in shapes:
        meshes, st = sh["meshes"], sh["stride"]
        pad_to(BUF_ALIGN)
        start = cur
        if not shown[n]:
            segs.append({"copy": [sh["vbuf"], st]})
            cur += st
            plan_vb[n] = (start - pool, 1, {})
            continue
        spans = []
        for k in (level[n],):
            rows, _ = _lod_rows(d, meshes[k])
            spans.append([int(rows[0]), int(rows[-1]) + 1])
        spans.sort()
        merged = []
        for a, b in spans:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        where, count = {}, 0
        for a, b in merged:
            segs.append({"copy": [sh["vbuf"] + a * st, (b - a) * st]})
            where[(a, b)] = count
            count += b - a
            cur += (b - a) * st
        first = {}
        for k in (level[n],):
            f = meshes[k]["first"]
            a, b = next(x for x in merged if x[0] <= f < x[1])
            first[k] = where[(a, b)] + f - a
        plan_vb[n] = (start - pool, count, first)
        info_shapes[n] = {"lod": level[n], "tris": meshes[level[n]]["count"] // 3, "vertices": count}
    pool_size = _align(cur - pool, POOL_ALIGN)
    if cur - pool < pool_size:
        segs.append({"zero": pool + pool_size - cur})
        cur = pool + pool_size
    mempool = cur
    segs.append({"copy": [old_mempool, 0x120]})
    cur += 0x120
    # the relocation table: sections moved, entries as they were (their positions are all in the copied part)
    r = _u32(d, 0x18)
    if r != old_mempool + 0x120 or d[r:r + 4] != b"_RLT":
        raise FigureError(f"{mu['model']}: the relocation table isn't right after the memory pool")
    rlt = bytearray(d[r:])
    nsec = _u32(rlt, 8)
    secs = []
    for i in range(nsec):
        o = 0x10 + 0x18 * i
        secs.append([_u32(rlt, o + 8), _u32(rlt, o + 12), _u32(rlt, o + 16), _u32(rlt, o + 20)])
    if nsec != 6 or secs[1][0] != pool or secs[2][0] != pool + secs[1][1] or secs[4][0] != old_mempool:
        raise FigureError(f"{mu['model']}: relocation sections {secs}")
    delta = mempool - old_mempool
    new_secs = [list(x) for x in secs]
    new_secs[1][1] = sec1
    new_secs[2][0], new_secs[2][1] = pool + sec1, pool_size - sec1
    for i in (3, 4, 5):
        new_secs[i][0] += delta
    for i, (pos, size, ei, ec) in enumerate(new_secs):
        struct.pack_into("<II", rlt, 0x10 + 0x18 * i + 8, pos, size)
    struct.pack_into("<I", rlt, 4, cur)
    ent0 = 0x10 + 0x18 * nsec
    mem_ptrs = []  # every pointer to the memory pool (section 4's entries)
    for e in range(secs[4][2], secs[4][2] + secs[4][3]):
        pos, nstruct, noff, npad = struct.unpack_from("<IHBB", rlt, ent0 + 8 * e)
        for si in range(nstruct):
            for oi in range(noff):
                mem_ptrs.append(pos + (si * (noff + npad) + oi) * 8)
    for p in mem_ptrs:
        if _q(d, p) != old_mempool:
            raise FigureError(f"{mu['model']}: pointer at {p:#x} isn't the memory pool's")
        put(p, struct.pack("<Q", mempool))
    segs.append({"hex": bytes(rlt).hex()})
    total = cur + len(rlt)
    put(0x18, struct.pack("<II", cur, total))
    put(_q(d, 0xB0) + 4, struct.pack("<I", pool_size))
    # shapes: buffers, counts, LODs, bounds
    fig_lo, fig_hi = -0.5 * s * (hi - lo), 0.5 * s * (hi - lo)
    for n, sh in shapes:
        vb = _q(d, sh["at"] + 0x10)
        if d[vb + 0x4D] != 1:
            raise FigureError(f"{n}: {d[vb + 0x4D]} vertex buffers")
        voff, count, first = plan_vb[n]
        put(vb + 0x48, struct.pack("<I", voff))
        put(vb + 0x50, struct.pack("<I", count))
        put(_q(d, vb + 0x30), struct.pack("<I", count * sh["stride"]))
        meshes = sh["meshes"]
        for j, m in enumerate(meshes):
            if m["nsub"] != 1 or m["prim"] != 3 or m["fmt"] != 1:
                raise FigureError(f"{n}: mesh {j} isn't a u16 triangle list with one sub-mesh")
            if plan_ib[n] is None:
                ioff, cnt, fst = zero_ib, 3, 0
            else:  # every LOD slot draws the kept LOD
                k = level[n]
                ioff, cnt, fst = plan_ib[n][k], meshes[k]["count"], first[k]
            put(m["at"] + 0x20, struct.pack("<I", ioff))
            put(m["at"] + 0x2C, struct.pack("<II", cnt, fst))
            put(_q(d, m["at"] + 0x18), struct.pack("<I", cnt * 2))
            put(m["sub"], struct.pack("<II", 0, cnt))
        if shown[n]:  # bounds cover the source's and the figure's together (bind space or figure space, either holds)
            boxes = struct.unpack_from(f"<{6 * sh['nboxes']}f", d, sh["bounds"])
            out = []
            for bi in range(sh["nboxes"]):
                c, h = np.array(boxes[6 * bi:6 * bi + 3]), np.array(boxes[6 * bi + 3:6 * bi + 6])
                blo, bhi = np.minimum(c - h, fig_lo), np.maximum(c + h, fig_hi)
                out += list((blo + bhi) / 2) + list((bhi - blo) / 2)
            put(sh["bounds"], struct.pack(f"<{6 * sh['nboxes']}f", *out))
            sx, sy, sz, sr = struct.unpack_from("<4f", d, sh["sphere"])
            put(sh["sphere"], struct.pack("<4f", *union_sphere((sx, sy, sz), sr, float(np.linalg.norm(fig_hi)))))
    # names: the model, and every texture that gets a reduced copy
    tex_ops, tex_info, renames = [], [], [[f"{mu['project']}.{mu['fmdb']}", f"{mu['project']}.{mu['figure_fmdb']}"],
                                          [mu["fmdb"], mu["figure_fmdb"]]]
    from parity import _appearance_bfres as ab
    textures = sorted({t for m in ab.materials(d) for t in m["textures"]})
    seen = {}
    for t in textures:
        if not os.path.exists(fs.path(f"Tex/{t}.bntx.zs")):
            tex_info.append({"name": t, "missing": True})  # same as in the game, the boss's own model names it too
            continue
        op, info = texture_op(t, fs)
        tex_info.append(info)
        if op is None:
            continue
        new = reduced_name(t)
        if new in seen or os.path.exists(fs.path(f"Tex/{new}.bntx.zs")) or new in textures or pool_string(new) in d:
            raise FigureError(f"{t}: its reduced name {new} is taken")
        seen[new] = t
        tex_ops.append(op)
        renames.append([t, new])
    op = {"to": mu["path"], "from": mu["model"], "segments": segs, "rename": renames,
          "bytes": edits + res_dict.edits(d, renames),
          "note": f"soul figure {key}: {mu['actor']}'s model, posed, {SOUL_SIZE} m (parity/_soul_figures.py)"}
    info = {"key": key, "museum": mu["actor"], "source_bytes": len(d), "bytes": total, "pool": pool_size,
            "scale": s, "centre": [float(x) for x in centre], "shapes": info_shapes,
            "hidden": sorted(n for n, _ in shapes if not shown[n]), "draws": sum(1 for v in shown.values() if v),
            "lod0_tris": sum(v["tris"] for v in info_shapes.values()), "material_values": baked,
            "shear": shear, "modes": modes, "unknown_vis": unknown, "textures": tex_info, "heaps": mu["heaps"],
            "aabb": ([float(x) for x in fig_lo], [float(x) for x in fig_hi]), "written": written,
            "level": dict(level), "shown": shown}
    return op, tex_ops, info


def plan(key, romfs):
    """The figure's {"new_files", "modelinfo", "aabb", "heap_from", "info"} (_show_models.plan's shape)."""
    op, tex_ops, info = build(key, romfs)
    mu = museum(key, romfs)
    lo, hi = info["aabb"]
    return {"new_files": [op] + tex_ops,
            "modelinfo": {"FmdbName": mu["figure_fmdb"], "ModelProjectName": mu["project"]},
            "aabb": ({"X": lo[0], "Y": lo[1], "Z": lo[2]}, {"X": hi[0], "Y": hi[1], "Z": hi[2]}),
            "heap_from": mu["actor"], "info": info}


def apply_op(src, op):
    """A new_files op's bytes as make_patch writes them: segments, renames (each old pooled name once), edits."""
    data = splice(src, op["segments"]) if op.get("segments") else bytes(src)
    for old, new in op.get("rename", []):
        o, n = pool_string(old), pool_string(new)
        if len(old) != len(new) or data.count(o) != 1 or data.count(n):
            raise FigureError(f"{op['to']}: rename {old} -> {new} isn't a single same-length pooled name")
        data = data.replace(o, n)
    d = bytearray(data)
    for e in op.get("bytes", []):
        o, old, new = int(e["offset"]), bytes.fromhex(e["expect"]), bytes.fromhex(e["bytes"])
        if d[o:o + len(old)] != old or len(old) != len(new):
            raise FigureError(f"{op['to']}: edit at {o:#x} doesn't find its bytes")
        d[o:o + len(new)] = new
    return bytes(d)


# Read-back (in_game_check / no_pose_check: verify)
def verify_texture(name, data, src):
    """Problems with reduced texture copy `data` of game texture `name` (`src`). Checks its name, dictionary, size,
    mips, block height and data, which has to be the source's mips from the dropped ones on, byte for byte."""
    rel = f"Tex/{reduced_name(name)}.bntx.zs"
    try:
        t, o = bntx_info(data), bntx_info(src)
    except (FigureError, ValueError, struct.error) as e:
        return [f"{rel}: {e}"]
    bad = []
    n = texture_drop(o)
    if t["name"] != reduced_name(name):
        bad.append(f"{rel}: names its texture {t['name']}")
    bad += res_dict.problems(data, rel)
    if not res_dict.has(data, reduced_name(name)):
        bad.append(f"{rel}: its texture dictionary doesn't find {reduced_name(name)}")
    if (t["w"], t["h"], t["mips"], t["fmt"]) != (o["w"] >> n, o["h"] >> n, o["mips"] - n, o["fmt"]) or n == 0:
        bad.append(f"{rel}: {t['w']} x {t['h']}, {t['mips']} mips: not {name} from mip {n}")
        return bad
    if max(t["w"], t["h"]) > texture_cap(name):
        bad.append(f"{rel}: {t['w']} x {t['h']} is over {texture_cap(name)}")
    lay = mip_layout(t["w"], t["h"], t["mips"], t["fmt"], t["block_log"])
    if [p - t["start"] for p in t["ptrs"][:t["mips"]]] != [sum(s for s, _ in lay[:i]) for i in range(t["mips"])] \
            or t["size"] != sum(s for s, _ in lay):
        bad.append(f"{rel}: its mip table isn't its block-linear layout (block height {1 << t['block_log']})")
    if data[t["start"]:t["start"] + t["size"]] != src[o["ptrs"][n]:o["start"] + o["size"]]:
        bad.append(f"{rel}: its texels aren't {name}'s mips {n}+")
    r = _u32(data, 0x18)
    if data[r:r + 4] != b"_RLT" or _u32(data, 0x1C) != len(data) or _u32(data, r + 4) != r \
            or _u32(data, r + 0x10 + 0x18 + 8) + _u32(data, r + 0x10 + 0x18 + 12) != r:
        bad.append(f"{rel}: header / relocation table sizes don't fit the file")
    return bad


def _figure_points(d, sh, m, world, m2b, inv):
    rows, _ = _lod_rows(d, m)
    return vertex_positions(d, sh, rows, world, m2b, inv, _u16(d, sh["at"] + 0x54))


def verify_figure(key, fs, van, romfs, patch):
    """Problems with soul `key`'s figure as the patch has it (fs is the game with the patch, van the plain game). It's
    read from the file itself and checked against the boss's model and the Hall of Fallen Foes anims.
    - The file: its sizes, relocation table, GPU pool and memory-pool pointers fit, plus names and dictionaries.
    - The enemy's own materials (names, shader assigns, parameter layouts) and textures. Each texture is the boss's own
      (in the game) or its reduced copy (in the patch, verify_texture). A shown shape whose material can't load any
      texture gets reported, and so does one whose UVs all sit on one point (one flat colour, like the first pass's
      glow figures). A full-size texture gets reported too, since that's the boss's texture memory.
    - Geometry: each shown shape draws one of the boss's LOD meshes (the source's index bytes and vertex records) in
      every LOD slot, hidden ones one degenerate triangle, and each bone's visible flag is the museum's.
    - Pose: the figure as the game skins it from this skeleton is the museum pose (from the source and the anims, with
      Maya compensation), SOUL_SIZE large and centred, within 2 mm. The baked material values are the anims'."""
    import numpy as np
    sm = _sm()
    mu = museum(key, romfs)
    path = mu["path"]
    try:
        data, src = fs.read(path), van.read(mu["model"])
        lay, slay = sm.layout(data), sm.layout(src)
    except (FigureError, ValueError, struct.error, FileNotFoundError) as e:
        return [f"{path}: {e}"]
    bad = []
    # the file
    r, pool = _u32(data, 0x18), _q(data, _q(data, 0xB0) + 8)
    pool_size = _u32(data, _q(data, 0xB0) + 4)
    secs = [struct.unpack_from("<II", data, r + 0x10 + 0x18 * i + 8) for i in range(_u32(data, r + 8))] \
        if data[r:r + 4] == b"_RLT" else []
    if _u32(data, 0x1C) != len(data) or len(secs) != 6 or _u32(data, r + 4) != r or secs[1][0] != pool \
            or secs[1][1] + secs[2][1] != pool_size or secs[4][0] != pool + pool_size \
            or _q(data, 0xA8) != pool + pool_size:
        return [f"{path}: its header, relocation table and GPU pool don't fit together"]
    if lay["name"] != mu["figure_fmdb"] or lay["file_name"] != f"{mu['project']}.{mu['figure_fmdb']}":
        bad.append(f"{path}: names {lay['name']} / {lay['file_name']}")
    bad += res_dict.problems(data, path)
    if not res_dict.has(data, mu["figure_fmdb"], _q(data, 0x30)):
        bad.append(f"{path}: its model dictionary doesn't find {mu['figure_fmdb']}")
    # materials and textures
    from parity import _appearance_bfres as ab
    mats, smats = ab.materials(data), ab.materials(src)
    if [m["material"] for m in mats] != [m["material"] for m in smats]:
        return bad + [f"{path}: its materials aren't {mu['model']}'s (not the enemy's own look)"]
    loads = {}
    for m, sm_ in zip(mats, smats):
        if len(m["textures"]) != len(sm_["textures"]):
            bad.append(f"{path}: {m['material']} has {len(m['textures'])} textures, the boss's {len(sm_['textures'])}")
            continue
        for got, want in zip(m["textures"], sm_["textures"]):
            if got == want:  # the boss's own, in the game or a slot the boss's model names without a file
                ok = True
            elif got == reduced_name(want):
                ok = os.path.exists(os.path.join(patch, f"Tex/{got}.bntx.zs"))
                if ok and got not in loads:
                    bad += verify_texture(want, fs.read(f"Tex/{got}.bntx.zs"), van.read(f"Tex/{want}.bntx.zs"))
                elif not ok:
                    bad.append(f"{path}: {m['material']} names {got}, which isn't in the patch (it would lose that "
                               f"texture)")
            else:
                bad.append(f"{path}: {m['material']} names texture {got}, not the boss's {want}")
                ok = False
            loads[got] = ok
        sa, sb = _q(data, _q(data, m["fmat"] + 0x10)), _q(src, _q(src, sm_["fmat"] + 0x10))
        if (_str(data, _q(data, sa)), _str(data, _q(data, sa + 8)), _u16(data, sa + 0x4A)) != \
                (_str(src, _q(src, sb)), _str(src, _q(src, sb + 8)), _u16(src, sb + 0x4A)):
            bad.append(f"{path}: {m['material']}'s shader assign isn't the boss's")
    big = sorted(t for t in loads if loads[t] and not t.startswith(TEX_PREFIX)
                 and os.path.exists(van.path(f"Tex/{t}.bntx.zs"))
                 and max(bntx_info(van.read(f"Tex/{t}.bntx.zs"))[k] for k in ("w", "h")) > texture_cap(t))
    if big:
        bad.append(f"{path}: loads full-size textures {big[:3]} ({len(big)}): the boss's texture memory")
    # visibility, geometry, pose
    bones, m2b, inv = sm._skeleton(data)
    sbones, sm2b, sinv = sm._skeleton(src)
    flags, sflags = bone_flags(data), bone_flags(src)
    pose, vis_set, mat_set = {}, {}, {}
    for ext, rel, name, frame in mu["anims"]:
        a = van.read(rel)
        if ext == "fskb":
            pose.update(sm._pose(a, name))
        elif ext == "fvbb":
            vis_set.update(bone_visibility(a, name, frame))
        else:
            for mat, vals in material_values(a, name, frame).items():
                mat_set.setdefault(mat, []).extend(vals)
    want_vis = [vis_set.get(b["name"], bool(sflags[i] & VISIBLE)) for i, b in enumerate(sbones)]
    for i, b in enumerate(bones):
        if bool(flags[i] & VISIBLE) != want_vis[i]:
            bad.append(f"{path}: bone {b['name']}'s visible flag isn't the museum's ({want_vis[i]})")
    vis = [bool(f & VISIBLE) for f in flags]
    world = worlds_maya(bones, flags, {})
    world_m = worlds_maya(sbones, sflags, pose)
    got_pts, want_pts = [], []
    for n, sh in lay["shapes"].items():
        ssh = slay["shapes"][n]
        meshes = sh["meshes"]
        if not _shape_bone_visible(bones, vis, _u16(data, sh["at"] + 0x54)):
            if any(m["count"] != 3 or any(struct.unpack_from("<3H", data, m["ibuf"])) for m in meshes):
                bad.append(f"{path}: hidden shape {n} draws more than one degenerate triangle")
            continue
        m0 = meshes[0]
        idx = data[m0["ibuf"]:m0["ibuf"] + 2 * m0["count"]]
        k = next((k for k, sm0 in enumerate(ssh["meshes"]) if sm0["count"] == m0["count"]
                  and src[sm0["ibuf"]:sm0["ibuf"] + 2 * sm0["count"]] == idx), None)
        if k is None:
            bad.append(f"{path}: shown shape {n} doesn't draw one of the boss's own LOD meshes")
            continue
        rows, _ = _lod_rows(data, m0)
        srows, _ = _lod_rows(src, ssh["meshes"][k])
        st = sh["stride"]
        if data[sh["vbuf"] + rows[0] * st:sh["vbuf"] + (rows[-1] + 1) * st] != \
                src[ssh["vbuf"] + srows[0] * st:ssh["vbuf"] + (srows[-1] + 1) * st]:
            bad.append(f"{path}: shown shape {n}'s vertices aren't the boss's own")
        if any(m["count"] != m0["count"] or m["ibuf"] != m0["ibuf"] or m["first"] != m0["first"] for m in meshes):
            bad.append(f"{path}: shape {n}'s LOD slots don't all draw its kept LOD")
        if "_u0" in sh["attrs"]:
            f, o = sh["attrs"]["_u0"]
            rec = np.frombuffer(data, np.uint8, sh["count"] * st, sh["vbuf"]).reshape(-1, st)[rows]
            uv = rec[:, o:o + 4].copy().view("<u2" if f == 0x1201 else "<f2").astype(np.float64)
            if float(np.nanmax(np.nanmax(uv, 0) - np.nanmin(uv, 0))) < 1e-3 * (65535 if f == 0x1201 else 1):
                bad.append(f"{path}: shape {n}'s vertices all sample one point of its textures (one flat colour)")
        mat = mats[_u16(data, sh["at"] + 0x52)]
        if mat["textures"] and not any(loads.get(t) for t in mat["textures"]):
            bad.append(f"{path}: shape {n}'s material {mat['material']} loads none of its textures")
        got_pts.append(_figure_points(data, sh, m0, world, m2b, inv))
        want_pts.append(_figure_points(src, ssh, ssh["meshes"][k], world_m, sm2b, sinv))
    drawn = sum(sh["meshes"][0]["count"] // 3 for n, sh in lay["shapes"].items()
                if _shape_bone_visible(bones, vis, _u16(data, sh["at"] + 0x54)))
    if drawn > FIGURE_TRIS * 1.05:  # the budget, plus the small parts' MIN_PART_TRIS floor
        bad.append(f"{path}: draws {drawn} triangles, over the figure's {FIGURE_TRIS}")
    if got_pts:
        got, want = np.concatenate(got_pts), np.concatenate(want_pts)
        lo, hi = want.min(0), want.max(0)
        want = (want - (lo + hi) / 2) * (SOUL_SIZE / float((hi - lo).max()))
        dev = float(np.linalg.norm(got - want, axis=1).max())
        if dev > 0.002:
            bad.append(f"{path}: as skinned it is {dev * 1000:.1f} mm from the museum pose at {SOUL_SIZE} m")
    else:
        bad.append(f"{path}: no shape shows")
    # baked material values
    fm = {m["material"]: m["fmat"] for m in mats}
    for mat, vals in mat_set.items():
        if mat not in fm:
            continue
        params = material_params(data, fm[mat])
        for h, off, raw in vals:
            if h in params and data[params[h][0] + off:params[h][0] + off + 4] != raw:
                bad.append(f"{path}: {mat}'s parameter {h:#x} isn't the museum's value")
                break
    return bad
