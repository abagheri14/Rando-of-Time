"""Offline reach checker on the remake's level collision (tools/phive_shape.py). Tooling only.

    w = World(fs, "DeathMountainTrail", "Child", center=(-40, 122, -26), radius=60)
    w.floor_below((x, y, z))         -> Hit (first surface under the point: .y, .point, .normal, .part) or None
    w.ray(a, b)                      -> first Hit on the segment a->b, or None (w.hits(a, b): every hit)
    w.surfaces(x, z)                 -> every surface on the vertical line at (x, z), top first
    w.line_clear(a, b)               -> True when nothing solid is between a and b
    w.hookshot(eye, target, longshot=False), w.boomerang(eye, target)   range + line of sight
    w.tagged("StickHookshot", center, radius)                           triangles carrying a user shape tag
    climb_ok(fs, height, age), fall_damage(fs, height)                   from the player's own constants
    g = NavGrid(w, x0, z0, x1, z1, age, cell=0.5, include=..., body_radius=False)
    g.reach([g.node_at(p)]) / g.path(seen, node)                         walk / drop / climb / slide graph

What counts as solid is a filter over the labelled parts (phive_shape.Collision.parts). LINK_BODY is the default
and is what stops Link's body: terrain, Physical meshes, solid objects and air walls that hit the player. LINE is
what stops a thrown or shot line, so the same thing without air walls. A filter is a function part -> bool.
Age-specific Presence isn't applied, since each age has its own level files. A part's "presence" says which flag
would remove it.

Player constants, read from the files at run time by player_constants() (values as I found them)
  ledge grab from a jump  StartJumpCliffHoldLimitHeight  adult 2.81, child 2.01   Pack/Actor/Player_Adult|Child
                          (standing grab StartJumpCliffHoldHeight 2.19 / 1.39;      .pack.zs Player/PlayerGameParam/
                          clamber StartClamberHeight child 0.69, adult: code       Player[_Child].game__player__
                          default; step PlayerStepHeight 0.45 / 0.35)               PlayerGameParam.bgyml
  jump height             JumpHeight 0.70 (both ages)                               same
  player height / radius  PlayerHeight 1.68 / 1.17, CctRadius 0.35 / 0.23           same
  hover boots             HoverBootsFloatingTime 84 frames, 42 after a jump         same (adult file)
  fall damage             FallDamageStartHeight 10 m, then FallDamagePerMeter 0.2  Player_*.pack.zs Life/Damage
                          (min 2), FallDamageHighStart 20, no insta-kill height     Parameters/Player.game__life__
                          (FallDamageInstaKillHeight -1); LargeLandHeight 5 m       DamageParameters.bgyml
                          (hard landing) in PlayerGameParam
  hookshot / longshot     Range 10 / 20, ShootLineCheckRadius 0.075                 Pack/Actor/Weapon_Range_Hookshot|
                                                                                    Longshot.pack.zs Component/
                                                                                    HookshotParam/*.bgyml
  boomerang               Range 10, ExtendRange 13, ShortRange 9, MoveSpeed 10      Pack/Actor/Item_Boomerang.pack.zs
                                                                                    GameParameter/Boomerang/
                                                                                    Item_Boomerang.game__player__
                                                                                    Boomerang.bgyml
  Not in the files (code): run speed (so the Hover Boots' distance), the adult's clamber heights.

  python tools/reach.py verify                         the known cases (both ways) as self-checks
  python tools/reach.py floor <Area> <Age> x y z       first surface under a point
  python tools/reach.py ray <Area> <Age> x y z x2 y2 z2
  python tools/reach.py column <Area> <Age> x z        every surface on a vertical line
"""
import functools
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "gamedb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import phive_shape  # noqa: E402

CELL = 4.0          # grid cell (m, XZ)
BIG_CELLS = 64      # triangles spanning more cells than this go in a list tested by every query


# Player constants

def _flat(d, pre=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flat(v, f"{pre}.{k}" if pre else str(k)))
    else:
        out[pre] = d
    return out


@functools.lru_cache(maxsize=4)
def player_constants(fs):
    """{name: (value, source)} for both ages ('adult.X' / 'child.X'), read from the packs."""
    import common
    out = {}

    def get(pack, inner, keys, prefix):
        pk = common.pack(fs, pack)
        d = phive_shape._param(fs, pk, inner) or {}
        f = _flat(d)
        for k in keys:
            if k in f:
                out[f"{prefix}{k.split('.')[-1]}"] = (f[k], f"{pack} {inner}")

    pg = ("StartJumpCliffHoldLimitHeight", "StartJumpCliffHoldHeight", "StartClamberHeight", "StartJumpClamberHeight",
          "PlayerStepHeight", "JumpHeight", "PlayerHeight", "CctRadius", "HoverBootsFloatingTime",
          "HoverBootsFloatingTimeAfterJump", "LargeLandHeight", "CliffHoldHeightMaxInAirFirst",
          "PermitWallAngleMin")
    fd = tuple("InternalDamageParameters.FallDamageParameters." + k for k in
               ("FallDamageStartHeight", "FallDamagePerMeter", "FallDamageMin", "FallDamageHighStart",
                "FallDamageHighPerMeter", "FallDamageInstaKillHeight"))
    get("Pack/Actor/Player_Adult.pack.zs", "Player/PlayerGameParam/Player.game__player__PlayerGameParam.bgyml",
        pg, "adult.")
    get("Pack/Actor/Player_Child.pack.zs", "Player/PlayerGameParam/Player_Child.game__player__PlayerGameParam.bgyml",
        pg, "child.")
    for age, pack in (("adult", "Player_Adult"), ("child", "Player_Child")):
        get(f"Pack/Actor/{pack}.pack.zs", "Life/DamageParameters/Player.game__life__DamageParameters.bgyml", fd,
            age + ".")
    get("Pack/Actor/Weapon_Range_Hookshot.pack.zs",
        "Component/HookshotParam/Weapon_Range_Hookshot.game__component__HookshotParam.bgyml",
        ("Range", "ShootLineCheckRadius"), "hookshot.")
    get("Pack/Actor/Weapon_Range_Longshot.pack.zs",
        "Component/HookshotParam/Weapon_Range_Longshot.game__component__HookshotParam.bgyml",
        ("Range", "ShootLineCheckRadius"), "longshot.")
    get("Pack/Actor/Item_Boomerang.pack.zs", "GameParameter/Boomerang/Item_Boomerang.game__player__Boomerang.bgyml",
        ("Range", "ExtendRange", "ShortRange", "MoveSpeed"), "boomerang.")
    return out


def const(fs, name):
    return player_constants(fs)[name][0]


def climb_ok(fs, height, age):
    """Can Link reach a ledge `height` m above his floor by jumping and grabbing (StartJumpCliffHoldLimitHeight)?"""
    return height <= const(fs, f"{age.lower()}.StartJumpCliffHoldLimitHeight")


def fall_damage(fs, height, age="adult"):
    """Hearts' worth of fall damage the files give for a fall of `height` m (0 below FallDamageStartHeight)."""
    start = const(fs, f"{age.lower()}.FallDamageStartHeight")
    if height < start:
        return 0.0
    return max(const(fs, f"{age.lower()}.FallDamageMin"), (height - start) * const(fs, f"{age.lower()}.FallDamagePerMeter"))


# Filters

PLAYER_AIRWALL_WORDS = ("Player", "_All", "ClimbPlayer")           # FldObj_AirWall_Player*, _All, Land …__Airwall
NOT_PLAYER_AIRWALL_WORDS = ("Enemy", "Animal", "Horse", "Npc", "Cucco", "Lure", "Camera", "CharacterSight",
                            "HitOnlyBomb", "HitBomb", "Hookshot", "DedicatedEnemy")


def is_airwall(p):
    g = p.get("gyaml") or ""
    return (p.get("sublayer") == "AirWall" or "AirWall" in g or "airwall" in (p.get("prim") or "").lower()
            or "Airwall" in (p.get("body") or ""))


def airwall_hits_player(p):
    """Does this air wall stop Link? Yes for the __Airwall meshes in Land models and FldObj_AirWall_Player*/All, no for
    air walls meant for enemies, animals, the camera, bombs or the hookshot."""
    g = p.get("gyaml") or ""
    if any(w in g for w in NOT_PLAYER_AIRWALL_WORDS):
        return False
    if g.startswith("Land_") or g.startswith("Obj_") or any(w in g for w in PLAYER_AIRWALL_WORDS):
        return True
    return p.get("mask") in ("HitOnlyPlayer", None) and not g.startswith("AirWallEnemy")


def _solid_layer(p):
    lay = p.get("layer")
    if p.get("kind") == "terrain":
        return True
    # Link hits both stair shapes: StairStep (GroundHighResRough) and StairSlope (GroundHighResSmooth).
    # PhiveConfig's Player mask (2736127) has bits 6, 7 and 8 set for Physical and the two stairs.
    if lay not in phive_shape.SOLID_LAYERS:
        return False
    return (p.get("mask") or "") not in phive_shape.NOT_PLAYER_MASKS


def LINK_BODY(p):
    """What stops Link's body (walking, falling, standing)."""
    if not _solid_layer(p):
        return False
    return airwall_hits_player(p) if is_airwall(p) else True


def LINE(p):
    """What stops a shot or thrown line (hookshot chain, boomerang): solid geometry, no air walls."""
    return _solid_layer(p) and not is_airwall(p)


def AIRWALLS(p):
    return is_airwall(p)


def EVERYTHING(p):
    """Every part, pickups included (for looking around)."""
    return True


LINK_BODY.solid_only = LINE.solid_only = True
EVERYTHING.solid_only = False


# World

class Hit:
    __slots__ = ("t", "point", "normal", "index", "part", "material", "tags")

    def __init__(self, t, point, normal, index, part, material=None, tags=()):
        self.t, self.point, self.normal, self.index, self.part = t, point, normal, index, part
        self.material, self.tags = material, tags

    @property
    def y(self):
        return float(self.point[1])

    def label(self):
        p = self.part
        bits = [p.get("kind")]
        for k in ("gyaml", "body", "prim", "layer", "sublayer", "hash"):
            if p.get(k):
                bits.append(f"{k}={p[k]}")
        if p.get("presence"):
            bits.append(f"presence={p['presence']}")
        if self.material:
            bits.append(f"material={self.material}")
        if self.tags:
            bits.append("tags=" + "|".join(self.tags))
        return " ".join(str(b) for b in bits)

    def __repr__(self):
        x, y, z = self.point
        return f"<Hit ({x:.2f}, {y:.2f}, {z:.2f}) n=({self.normal[0]:.2f}, {self.normal[1]:.2f}, " \
               f"{self.normal[2]:.2f}) {self.label()}>"


class World:
    """An area's collision around a point (or all of it), with an XZ grid for ray queries."""

    def __init__(self, fs, area, age, center=None, radius=None, variant=None, include=LINK_BODY, col=None):
        self.fs, self.area, self.age = fs, area, age
        self.col = col or phive_shape.area_collision(fs, area, age, variant, center=center, radius=radius)
        self.parts = self.col.parts
        self.tri = self.col.tri.astype(np.float64)
        self.part = self.col.part
        self.mat, self.sub, self.utag = self.col.mat, self.col.sub, self.col.utag
        cfg = phive_shape.phive_config(fs)
        self._mat_names, self._sub_names = cfg["material"], cfg["submaterial"]
        self._tag_bits = sorted((v, k) for k, v in cfg["tagbits"].items() if v and not v & (v - 1))
        v0, v1, v2 = self.tri[:, 0], self.tri[:, 1], self.tri[:, 2]
        n = np.cross(v1 - v0, v2 - v0)
        ln = np.linalg.norm(n, axis=1)
        self.normal = n / np.where(ln > 0, ln, 1)[:, None]
        self.lo, self.hi = self.tri.min(axis=1), self.tri.max(axis=1)
        self.set_filter(include)
        self._grid()

    def set_filter(self, include):
        self.include = include
        keep = np.array([bool(include(p)) for p in self.parts], bool) if self.parts else np.zeros(0, bool)
        self.active = keep[self.part] if len(self.part) else np.zeros(0, bool)
        if getattr(include, "solid_only", True):      # pickups' and characters' own bodies stop nothing here
            names = self._mat_names
            skip = [names.index(n) for n in ("DropItem", "Character", "Ragdoll") if n in names]
            self.active &= ~np.isin(self.mat, skip)

    def _grid(self):
        ix0 = np.floor(self.lo[:, 0] / CELL).astype(np.int64)
        ix1 = np.floor(self.hi[:, 0] / CELL).astype(np.int64)
        iz0 = np.floor(self.lo[:, 2] / CELL).astype(np.int64)
        iz1 = np.floor(self.hi[:, 2] / CELL).astype(np.int64)
        nx, nz = ix1 - ix0 + 1, iz1 - iz0 + 1
        span = nx * nz
        big = span > BIG_CELLS
        self.big = np.nonzero(big)[0]
        idx = np.nonzero(~big)[0]
        keys, tris = [], []
        maxx, maxz = int(nx[idx].max(initial=1)), int(nz[idx].max(initial=1))
        for dx in range(maxx):
            for dz in range(maxz):
                sel = idx[(nx[idx] > dx) & (nz[idx] > dz)]
                keys.append((ix0[sel] + dx) * 1_000_003 + (iz0[sel] + dz))
                tris.append(sel)
        keys = np.concatenate(keys) if keys else np.zeros(0, np.int64)
        tris = np.concatenate(tris) if tris else np.zeros(0, np.int64)
        order = np.argsort(keys, kind="stable")
        self.gkeys, self.gtris = keys[order], tris[order]

    def _cells_tris(self, cells):
        out = [self.big]
        for cx, cz in cells:
            k = cx * 1_000_003 + cz
            a = np.searchsorted(self.gkeys, k, "left")
            b = np.searchsorted(self.gkeys, k, "right")
            if b > a:
                out.append(self.gtris[a:b])
        return np.unique(np.concatenate(out)) if len(out) > 1 else self.big

    def _candidates(self, a, b, pad=0.0):
        x0, x1 = sorted((a[0], b[0]))
        z0, z1 = sorted((a[2], b[2]))
        cx0, cx1 = int(math.floor((x0 - pad) / CELL)), int(math.floor((x1 + pad) / CELL))
        cz0, cz1 = int(math.floor((z0 - pad) / CELL)), int(math.floor((z1 + pad) / CELL))
        if (cx1 - cx0 + 1) * (cz1 - cz0 + 1) <= 400:
            cells = [(cx, cz) for cx in range(cx0, cx1 + 1) for cz in range(cz0, cz1 + 1)]
        else:                                   # long diagonal: walk the line, one cell of margin
            steps = int(max(abs(b[0] - a[0]), abs(b[2] - a[2])) / (CELL / 2)) + 2
            cells = set()
            for s in range(steps + 1):
                x = a[0] + (b[0] - a[0]) * s / steps
                z = a[2] + (b[2] - a[2]) * s / steps
                cx, cz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
                cells.update((cx + i, cz + j) for i in (-1, 0, 1) for j in (-1, 0, 1))
        c = self._cells_tris(cells)
        lo = np.minimum(a, b) - pad - 1e-6
        hi = np.maximum(a, b) + pad + 1e-6
        m = self.active[c] & (self.hi[c] >= lo).all(axis=1) & (self.lo[c] <= hi).all(axis=1)
        return c[m]

    def hits(self, a, b, include=None):
        """Every hit on the segment a->b, nearest first (filter: the world's, or `include`)."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        if include is not None:
            saved = self.active
            self.set_filter(include)
        try:
            c = self._candidates(a, b)
        finally:
            if include is not None:
                self.active = saved
        if not len(c):
            return []
        d = b - a
        v0 = self.tri[c, 0]
        e1 = self.tri[c, 1] - v0
        e2 = self.tri[c, 2] - v0
        p = np.cross(d, e2)
        det = (e1 * p).sum(axis=1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        s = a - v0
        u = (s * p).sum(axis=1) * inv
        q = np.cross(s, e1)
        v = (q * d).sum(axis=1) * inv
        t = (e2 * q).sum(axis=1) * inv
        m = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t >= 0) & (t <= 1)
        out = []
        for i in np.nonzero(m)[0]:
            ti = c[i]
            out.append(Hit(float(t[i]), a + d * t[i], self.normal[ti], int(ti), self.parts[self.part[ti]],
                           self.material_name(ti), self.tag_names(ti)))
        out.sort(key=lambda h: h.t)
        return out

    def material_name(self, i):
        m, s = int(self.mat[i]), int(self.sub[i])
        if m < 0:
            return None
        name = self._mat_names[m] if m < len(self._mat_names) else str(m)
        return name + (f":{self._sub_names[s]}" if 0 < s < len(self._sub_names) else "")

    def tag_names(self, i):
        u = int(self.utag[i])
        return tuple(k for v, k in self._tag_bits if u & v)

    def tagged(self, name, center=None, radius=None):
        """Indices of triangles carrying a user shape tag (e.g. 'StickHookshot', 'Climb', 'Ladder'), optionally
        within `radius` of `center` (3D distance to the triangle's nearest corner/centre)."""
        bit = np.uint64(phive_shape.phive_config(self.fs)["tagbits"][name])
        idx = np.nonzero((self.utag & bit) != 0)[0]
        if center is not None and radius is not None and len(idx):
            c = np.asarray(center, float)
            d = np.linalg.norm(self.tri[idx] - c, axis=2).min(axis=1)
            d = np.minimum(d, np.linalg.norm(self.tri[idx].mean(axis=1) - c, axis=1))
            idx = idx[d <= radius]
        return idx

    def ray(self, a, b, include=None):
        h = self.hits(a, b, include)
        return h[0] if h else None

    def floor_below(self, p, max_drop=500.0, include=None, up_facing=True):
        """First surface under p (facing up unless up_facing=False); None if nothing within max_drop."""
        p = np.asarray(p, float)
        for h in self.hits(p, p - (0, max_drop, 0), include):
            if not up_facing or h.normal[1] > 0.05:
                return h
        return None

    def surfaces(self, x, z, top=1000.0, bottom=-1000.0, include=None):
        """Every surface crossed by the vertical line at (x, z), top first."""
        return self.hits((x, top, z), (x, bottom, z), include)

    def line_clear(self, a, b, include=LINE):
        return self.ray(a, b, include) is None

    def hookshot(self, eye, target, longshot=False):
        """(in range, line clear, distance, first blocking hit) for a hookshot/longshot shot from eye to target."""
        rng = const(self.fs, ("longshot." if longshot else "hookshot.") + "Range")
        dist = float(np.linalg.norm(np.asarray(target, float) - np.asarray(eye, float)))
        h = self._line_block(eye, target)
        return dist <= rng, h is None, dist, h

    def boomerang(self, eye, target, extended=True):
        rng = const(self.fs, "boomerang." + ("ExtendRange" if extended else "Range"))
        dist = float(np.linalg.norm(np.asarray(target, float) - np.asarray(eye, float)))
        h = self._line_block(eye, target)
        return dist <= rng, h is None, dist, h

    def _line_block(self, a, b, end_margin=0.3):
        """The first line-stopping hit between a and b, ignoring the last end_margin m (the target's own body)."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        ln = float(np.linalg.norm(b - a))
        if ln <= end_margin:
            return None
        bb = a + (b - a) * (1 - end_margin / ln)
        return self.ray(a, bb, LINE)


# Walk / drop / climb graph


class NavGrid:
    """A 2.5D walk graph over a box of the world. Nodes are floors (up-facing, walkable, with headroom for the
    age's PlayerHeight) on a square grid of `cell` m, and edges go between 4-neighbours:
      walk  |dy| <= PlayerStepHeight and nothing solid (air walls included) across at knee and chest height;
      drop  down any height: the step off is clear and the fall at the neighbour, from the upper floor down to
            the lower one, hits nothing first (an air wall over the drop stops it);
      climb up to StartJumpCliffHoldLimitHeight (ledge grab from a jump), clear above the ledge, unless the
            ledge's triangles carry NoClamber (then only up to the step height);
      slide off onto a surface too steep to stand on, then down it along its slope to the first walkable floor
            (every step clear of solids and air walls).
    Floors on air walls don't count (Link isn't meant to stand on them), and the slope limit is 50 degrees.
    It's an estimate of the movement model, not the game's controller, so it doesn't see timing or gaps
    thinner than `cell`."""

    MAX_SLOPE_NY = math.cos(math.radians(50))

    def __init__(self, world, x0, z0, x1, z1, age, cell=0.5, ymin=-1e9, ymax=1e9, include=None, body_radius=False):
        self.w, self.age, self.cell = world, age.lower(), cell
        # With body_radius, cast along both sides of Link's capsule (CctRadius) as well as the center.
        # That rules out gaps narrower than Link but costs three rays per move.
        self.radius = const(world.fs, f"{age.lower()}.CctRadius") if body_radius else 0.0
        self.include = include or LINK_BODY      # e.g. without some placements: lambda p: LINK_BODY(p) and ...
        world.set_filter(self.include)           # the grid owns the world's filter while it is used
        fs = world.fs
        self.step = const(fs, f"{self.age}.PlayerStepHeight")
        self.grab = const(fs, f"{self.age}.StartJumpCliffHoldLimitHeight")
        self.height = const(fs, f"{self.age}.PlayerHeight")
        self.xs = np.arange(x0, x1 + 1e-9, cell)
        self.zs = np.arange(z0, z1 + 1e-9, cell)
        self.ymin, self.ymax = ymin, ymax
        self.noclamber = np.uint64(phive_shape.tag_bit(fs, "NoClamber"))
        self.floors = {}            # (i, j) -> [(y, triangle index)]
        for i, x in enumerate(self.xs):
            for j, z in enumerate(self.zs):
                self.floors[(i, j)] = self._column(x, z)
        self.edges = {}

    def _column(self, x, z):
        hits = self.w.hits((x, min(self.ymax + 3, 1e4), z), (x, max(self.ymin - 3, -1e4), z))
        out = []
        for k, h in enumerate(hits):
            if h.normal[1] < self.MAX_SLOPE_NY or is_airwall(h.part):
                continue
            if not (self.ymin <= h.y <= self.ymax):
                continue
            above = [g for g in hits[:k] if g.y > h.y + 0.05]
            if above and above[-1].y - h.y < self.height:
                continue          # no headroom (inside rock or an air wall)
            if out and abs(out[-1][0] - h.y) < 0.05:
                continue
            out.append((h.y, h.index))
        return out

    def _clear(self, a, b):
        if self.w.ray(a, b) is not None:
            return False
        if self.radius:
            a, b = np.asarray(a, float), np.asarray(b, float)
            d = np.array([b[2] - a[2], 0.0, a[0] - b[0]])
            ln = np.linalg.norm(d)
            if ln > 1e-9:
                off = d / ln * self.radius
                return self.w.ray(a + off, b + off) is None and self.w.ray(a - off, b - off) is None
        return True

    def neighbours(self, node):
        (i, j), k = node
        if node in self.edges:
            return self.edges[node]
        y, tri = self.floors[(i, j)][k]
        x, z = self.xs[i], self.zs[j]
        out = []
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if (ni, nj) not in self.floors:
                continue
            nx, nz = self.xs[ni], self.zs[nj]
            for nk, (ny, ntri) in enumerate(self.floors[(ni, nj)]):
                dy = ny - y
                top = max(y, ny)
                if abs(dy) <= self.step:
                    kind = "walk"
                    ok = self._clear((x, top + 0.3, z), (nx, top + 0.3, nz)) and \
                        self._clear((x, top + 1.0, z), (nx, top + 1.0, nz))
                elif dy < 0:
                    kind = "drop"
                    ok = self._clear((x, y + 0.3, z), (nx, y + 0.3, nz)) and \
                        self._clear((x, y + 1.0, z), (nx, y + 1.0, nz))
                    if ok:
                        first = self.w.floor_below((nx, y + 0.3, nz), max_drop=y - ny + 1.0,
                                                   up_facing=False)
                        ok = first is not None and abs(first.y - ny) < 0.06
                elif dy <= self.grab:
                    kind = "climb"
                    lim = self.step if int(self.w.utag[ntri]) & int(self.noclamber) else self.grab
                    ok = dy <= lim and self._clear((x, y + 0.3, z), (x, ny + 1.0, z)) and \
                        self._clear((x, ny + 0.3, z), (nx, ny + 0.3, nz))
                else:
                    continue
                if ok:
                    out.append((((ni, nj), nk), kind))
            land = self._slide(x, y, z, nx, nz)
            if land is not None:
                out.append((land, "slide"))
        self.edges[node] = out
        return out

    def _slide(self, x, y, z, nx, nz, step=0.25, max_steps=120):
        """Step off toward (nx, nz). If the first surface below is too steep to stand on, slide down it (along the
        horizontal part of its normal) until there's a walkable floor. None if the step off or the slide is blocked."""
        if not (self._clear((x, y + 0.3, z), (nx, y + 0.3, nz)) and self._clear((x, y + 1.0, z), (nx, y + 1.0, nz))):
            return None
        h = self.w.floor_below((nx, y + 0.3, nz), max_drop=max(1.0, y - self.ymin + 3), up_facing=False)
        if h is None or h.normal[1] >= self.MAX_SLOPE_NY or h.normal[1] < 0.05:
            return None
        px, py, pz = nx, h.y, nz
        n = h.normal
        for _ in range(max_steps):
            d = np.array([n[0], n[2]])
            ln = np.linalg.norm(d)
            if ln < 1e-6:
                return None
            qx, qz = px + d[0] / ln * step, pz + d[1] / ln * step
            if not self._clear((px, py + 0.4, pz), (qx, py + 0.4, qz)):
                return None
            g = self.w.floor_below((qx, py + 0.5, qz), max_drop=max(1.0, py - self.ymin + 3), up_facing=False)
            if g is None or g.normal[1] < 0.05:
                return None
            px, py, pz, n = qx, g.y, qz, g.normal
            if n[1] >= self.MAX_SLOPE_NY:
                return self.node_at((px, py, pz), tol=0.6)
        return None

    def node_at(self, p, tol=1.0):
        """The floor node under/at point p (nearest grid cell, floor within tol of p's y), or None."""
        i = int(round((p[0] - self.xs[0]) / self.cell))
        j = int(round((p[2] - self.zs[0]) / self.cell))
        best = None
        for k, (y, _) in enumerate(self.floors.get((i, j), [])):
            if abs(y - p[1]) <= tol and (best is None or abs(y - p[1]) < best[0]):
                best = (abs(y - p[1]), ((i, j), k))
        return best[1] if best else None

    def reach(self, starts, kinds=("walk", "drop", "climb", "slide")):
        """{node: (previous node, edge kind)} of every node reachable from the start nodes."""
        seen = {s: None for s in starts if s is not None}
        todo = list(seen)
        while todo:
            n = todo.pop()
            for m, kind in self.neighbours(n):
                if kind in kinds and m not in seen:
                    seen[m] = (n, kind)
                    todo.append(m)
        return seen

    def point(self, node):
        (i, j), k = node
        return (float(self.xs[i]), float(self.floors[(i, j)][k][0]), float(self.zs[j]))

    def path(self, seen, node):
        out = []
        while node is not None and seen.get(node) is not None:
            prev, kind = seen[node]
            out.append((self.point(node), kind))
            node = prev
        if node is not None:
            out.append((self.point(node), "start"))
        return out[::-1]


# Verification


def verify(fs, out=print):
    """Known cases, each both ways where the game proves both. Returns [problem]."""
    bad = []

    def check(name, cond, detail):
        out(f"  {'ok ' if cond else 'BAD'} {name}: {detail}")
        if not cond:
            bad.append(name)

    c = player_constants(fs)
    out("player constants:")
    for k in sorted(c):
        out(f"  {k} = {c[k][0]}   ({c[k][1].split(' ')[0].split('/')[-1]})")
    out("floors under placed items (decode + tile origins + instance transforms together):")
    spots = [("DeathMountainTrail", "Child", "DMT Freestanding PoH", (-39.66, 122.21, -26.0)),
             ("HyruleField", "Adult", "LLR Tower Chest", (-151.87, 162.03, 265.29)),
             ("KakarikoVillage", "Child", "Kak Windmill PoH", (1.48, 108.9, 37.52)),
             ("GoronCity", "Adult", "GC Maze Left Chest", (-47.35, 113.68, -2.35)),
             ("GoronCity", "Adult", "GC Maze Right Chest", (-43.24, 113.68, -8.37)),
             ("ZoraRiver", "Adult", "ZR boulder", (-75.74, 98.08, 4.96))]
    worlds = {}
    for area, age, name, p in spots:
        w = worlds.get((area, age, p)) or World(fs, area, age, center=(p[0], p[2]), radius=8)
        if name.startswith("ZR"):          # the boulder itself: exclude it, find the ground under it
            w.set_filter(lambda q: LINK_BODY(q) and q.get("hash") != "6669732312980766026")
        h = w.floor_below((p[0], p[1] + 0.5, p[2]), max_drop=1.5)
        check(f"{name} rests on a floor", h is not None and abs(h.y - p[1]) < 0.2,
              f"placement y {p[1]}, floor {h.y if h else None:.3f} ({(h.part.get('gyaml') or h.part.get('kind')) if h else ''})"
              if h else f"placement y {p[1]}, no floor")
    out("ledges (StartJumpCliffHoldLimitHeight adult 2.81 / child 2.01), both ways:")
    w = World(fs, "HyruleField", "Child", center=(-147.2, 268.4), radius=8)
    box_top = w.floor_below((-147.16, 153.5, 268.4), max_drop=3)
    floor = w.floor_below((-146.5, 151.5, 266.3), max_drop=3)
    dy = box_top.y - floor.y
    check("LLR box-room box top: both ages climb", climb_ok(fs, dy, "child") and climb_ok(fs, dy, "adult"),
          f"{dy:.2f} m above the box-room floor")
    w = World(fs, "KakarikoVillage", "Adult", center=(1.5, 38.5), radius=8)
    alcove = w.floor_below((1.48, 109.5, 37.0), max_drop=2)
    below = w.floor_below((1.5, 106.0, 40.5), max_drop=3)
    dy = alcove.y - below.y
    check("Kakariko windmill alcove: neither age climbs from the floor",
          not climb_ok(fs, dy, "child") and not climb_ok(fs, dy, "adult"), f"{dy:.2f} m above the windmill floor")
    out("hookshot targets (StickHookshot faces), in range and out of range:")
    w = World(fs, "GoronCity", "Adult", center=(-40.62, 32.55), radius=12)
    tgt = w.tri[w.tagged("StickHookshot", (-40.62, 114.73, 32.55), 3)].mean(axis=1)
    eye = np.array([-36.0, 0.0, 32.55])
    f = w.floor_below((eye[0], 120.0, eye[2]), max_drop=15)
    eye[1] = f.y + 1.4
    inr, clear, dist, _ = w.hookshot(eye, tgt.mean(axis=0))
    check("GC Obj_HookShotTarget_A_01 from the floor 4.6 m east: Hookshot reaches", inr and clear,
          f"{dist:.2f} m, line clear {clear}")
    far = None
    w = World(fs, "GoronCity", "Adult", center=(-40.62, 32.55), radius=18)
    for ang in np.radians(np.arange(0, 360, 10)):
        for r in (11.0, 12.0, 13.0):
            x, z = -40.62 + r * math.cos(ang), 32.55 + r * math.sin(ang)
            f = w.floor_below((x, 125.0, z), max_drop=30)
            if f is None:
                continue
            e = (x, f.y + 1.4, z)
            res = w.hookshot(e, tgt.mean(axis=0))
            if res[1] and (far is None or res[2] < far[2]):
                far = res
    check("GC Obj_HookShotTarget_A_01 from a floor spot 11-13 m away: out of Hookshot range, in Longshot range",
          far is not None and not far[0] and far[2] <= const(fs, "longshot.Range"),
          f"{far[2]:.2f} m, line clear {far[1]}" if far else "no clear spot")
    return bad


def main(argv):
    import common
    fs = common.open_romfs()
    if not argv or argv[0] == "verify":
        bad = verify(fs)
        print("reach: all checks pass" if not bad else f"reach: {len(bad)} checks failed: {bad}")
        return 1 if bad else 0
    cmd, area, age = argv[0], argv[1], argv[2]
    nums = [float(x) for x in argv[3:]]
    if cmd == "floor":
        w = World(fs, area, age, center=(nums[0], nums[2]), radius=30)
        print(w.floor_below(nums[:3]))
    elif cmd == "ray":
        w = World(fs, area, age, center=(nums[0], nums[2]), radius=math.dist(nums[:3], nums[3:6]) + 30)
        for h in w.hits(nums[:3], nums[3:6], include=EVERYTHING)[:20]:
            print(f"  t={h.t:.3f}", h)
    elif cmd == "column":
        w = World(fs, area, age, center=(nums[0], nums[1]), radius=20)
        for h in w.surfaces(nums[0], nums[1], include=EVERYTHING):
            print(" ", h)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
