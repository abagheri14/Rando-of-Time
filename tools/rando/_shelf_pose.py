"""A model's vertices as a one-frame skeletal pose leaves them, which is what a shop shelf draws
(tools/rando/shops.py posed_box). This is the BFRES reading and skinning from an earlier parity/_show_models.py.
That module has since been reworked for the soul figures and no longer has a posed-mesh reader, so it's kept here
and the shelf placement doesn't depend on another feature's internals. Read only."""
import math
import struct

SOUL_SOURCE_TRIS = 40000  # the triangle budget the LOD choice spreads over the shapes


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
    """Shapes (name, vertex buffer, attributes, meshes, bounds) and materials of the donor or a copy."""
    if d[:4] != b"FRES" or _u32(d, 8) != 0x000A0400:
        raise ModelError("not a BFRES 10.4 file")
    fm = _q(d, 0x28)
    pool = _q(d, _q(d, 0xB0) + 8)
    shapes = {}
    for i in range(_u16(d, fm + 0x6A)):
        sh = _q(d, fm + 0x28) + 0x60 * i
        vb = _q(d, sh + 0x10)
        attrs = {}
        for k in range(d[vb + 0x4C]):
            a = _q(d, vb + 0x08) + 0x10 * k
            attrs[_str(d, _q(d, a))] = (_u16(d, a + 8), _u16(d, a + 0x0C))
        meshes = []
        for k in range(d[sh + 0x5B]):
            me = _q(d, sh + 0x18) + 0x38 * k
            meshes.append({"at": me, "sub": _q(d, me), "nsub": _u16(d, me + 0x34), "ibuf": pool + _u32(d, me + 0x20),
                           "count": _u32(d, me + 0x2C), "first": _u32(d, me + 0x30), "prim": _u32(d, me + 0x24),
                           "fmt": _u32(d, me + 0x28)})
        nboxes = sum(1 + m["nsub"] for m in meshes)
        shapes[_str(d, _q(d, sh + 8))] = {
            "at": sh, "vbuf": pool + _u32(d, vb + 0x48), "count": _u32(d, vb + 0x50),
            "stride": _u32(d, _q(d, vb + 0x38)), "attrs": attrs, "meshes": meshes, "bounds": _q(d, sh + 0x38),
            "nboxes": nboxes, "sphere": _q(d, sh + 0x40), "skin": d[sh + 0x5A]}
    mats = {}
    for k in range(_u16(d, fm + 0x6C)):
        m = _q(d, fm + 0x38) + 0xB0 * k
        texs = [_str(d, _q(d, _q(d, m + 0x20) + 8 * i)) for i in range(d[m + 0xA3])]
        mats[_str(d, _q(d, m + 8))] = {"at": m, "textures": texs}
    return {"shapes": shapes, "materials": mats, "name": _str(d, _q(d, fm + 8)), "file_name": _str(d, _q(d, 0x20))}


def _euler(r):
    import numpy as np
    x, y, z = r[:3]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return (np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]))


def _skeleton(d):
    """(bones [{name, parent, s, r, t}], matrix-to-bone list, inverse bind matrices of the smooth matrices)."""
    import numpy as np
    sk = _q(d, _q(d, 0x28) + 0x18)
    if d[sk:sk + 4] != b"FSKL":
        raise ModelError("no skeleton")
    ba, nb, ns, nr = _q(d, sk + 0x10), _u16(d, sk + 0x38), _u16(d, sk + 0x3A), _u16(d, sk + 0x3C)
    bones = []
    for i in range(nb):
        b = ba + 0x58 * i
        bones.append({"name": _str(d, _q(d, b)), "parent": struct.unpack_from("<h", d, b + 0x22)[0],
                      "s": struct.unpack_from("<3f", d, b + 0x30), "r": struct.unpack_from("<4f", d, b + 0x3C),
                      "t": struct.unpack_from("<3f", d, b + 0x4C)})
    m2b = [_u16(d, _q(d, sk + 0x18) + 2 * i) for i in range(ns + nr)]
    inv = []
    for i in range(ns):
        m = np.eye(4)
        m[:3] = np.array(struct.unpack_from("<12f", d, _q(d, sk + 0x20) + 48 * i)).reshape(3, 4)
        inv.append(m)
    return bones, m2b, inv


def _pose(anim_data, name):
    """{bone: {"s", "r", "t"}} of one-frame skeletal anim `name` (base values only, curves are refused)."""
    import re
    for m in re.finditer(b"FSKA", anim_data):
        o = m.start()
        try:
            if _str(anim_data, _q(anim_data, o + 8)) != name:
                continue
        except (struct.error, UnicodeDecodeError, IndexError):
            continue
        out = {}
        for i in range(_u16(anim_data, o + 0x4C)):
            b = _q(anim_data, o + 0x28) + 0x38 * i
            flags, ncurve, base = _u32(anim_data, b + 0x28), anim_data[b + 0x2E], _q(anim_data, b + 0x10)
            if ncurve:
                raise ModelError(f"{name}: bone {_str(anim_data, _q(anim_data, b))} has {ncurve} curves")
            e, k = {}, 0
            for bit, key, n in ((0x20, "s", 3), (0x10, "r", 4), (0x08, "t", 3)):
                if flags & bit:
                    e[key] = struct.unpack_from(f"<{n}f", anim_data, base + 4 * k)
                    k += n
            out[_str(anim_data, _q(anim_data, b))] = e
        return out
    raise ModelError(f"no skeletal anim {name}")


def _worlds(bones, pose):
    import numpy as np
    out = []
    for b in bones:
        e = pose.get(b["name"], {})
        m = np.eye(4)
        m[:3, :3] = _euler(e.get("r", b["r"])) @ np.diag(e.get("s", b["s"]))
        m[:3, 3] = e.get("t", b["t"])
        out.append(m if b["parent"] < 0 else out[b["parent"]] @ m)
    return out


_ATTR = {0x0B: (4, 1), 0x02: (1, 1), 0x09: (2, 1), 0x0A: (1, 2), 0x12: (2, 2), 0x15: (4, 2)}  # (count, bytes)


def posed_source(model_path, anim_path, pose_name, fs, skip=()):
    """(positions, triangles) of `model` (Model/<model>.bfres.zs) posed by EnemyDictionary skeletal anim
    `pose_name`, or as bound when that's None. Each shape is at its finest LOD within its share of SOUL_SOURCE_TRIS."""
    import numpy as np
    d = fs.read(model_path)
    lay = layout(d)
    bones, m2b, inv = _skeleton(d)
    pose = _pose(fs.read(anim_path), pose_name) if pose_name else {}
    world = _worlds(bones, pose)
    palette = np.array([world[m2b[i]] @ inv[i] for i in range(len(inv))]) if inv else np.zeros((0, 4, 4))
    shapes = [(n, sh) for n, sh in sorted(lay["shapes"].items()) if not any(x in n for x in skip)]
    low = [sh["meshes"][-1]["count"] // 3 for _, sh in shapes]
    P, T, base = [], [], 0
    for (name, sh), lowc in zip(shapes, low):
        share = max(lowc, SOUL_SOURCE_TRIS * lowc // max(1, sum(low)))
        me = next((m for m in sh["meshes"] if m["count"] // 3 <= share), sh["meshes"][-1])
        if me["prim"] != 3 or me["fmt"] != 1:
            raise ModelError(f"{model} {name}: not a u16 triangle list")
        idx = np.frombuffer(d, "<u2", me["count"], me["ibuf"]).astype(np.int64)
        used = np.unique(idx)
        rec = np.frombuffer(d, np.uint8, sh["count"] * sh["stride"], sh["vbuf"]).reshape(sh["count"], sh["stride"])
        rec = rec[used + me["first"]]
        fmt, off = sh["attrs"]["_p0"]
        if fmt == 0x1805:  # 32-bit floats
            xyz = rec[:, off:off + 12].copy().view("<f4").reshape(-1, 3)
        elif fmt == 0x1505:  # half floats (x, y, z, w)
            xyz = rec[:, off:off + 8].copy().view("<f2").reshape(-1, 4)[:, :3]
        else:
            raise ModelError(f"{model} {name}: positions in format {fmt:#x}")
        pos = np.c_[xyz.astype(np.float64), np.ones(len(used))]
        if sh["skin"] >= 2:
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
            out = np.zeros((len(used), 4))
            for j in range(sh["skin"]):
                out += bw[:, j:j + 1] * np.einsum("nij,nj->ni", palette[bi[:, j]], pos)
        else:  # rigid, so the vertex's own bone (skin 1) or the shape's (skin 0)
            if sh["skin"] == 1:
                f, o = sh["attrs"]["_i0"]
                n, w = _ATTR[f >> 8]
                v = rec[:, o:o + w].copy()
                mats = np.array([world[m2b[i]] for i in (v.view("<u2").ravel() if w == 2 else v.ravel())])
            else:
                mats = np.array([world[_u16(d, sh["at"] + 0x54)]] * len(used))
            out = np.einsum("nij,nj->ni", mats, pos)
        remap = np.full(int(used.max()) + 1, -1, np.int64)
        remap[used] = np.arange(len(used))
        P.append(out[:, :3])
        T.append(remap[idx].reshape(-1, 3) + base)
        base += len(used)
    return np.concatenate(P), np.concatenate(T)
