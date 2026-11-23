"""Read/write helpers for the OoT remake's romfs (TotK-engine formats).

- zstd with the game's dictionaries (Pack/ZsDic.pack.zs)
- SARC (read)
- BYML v7 (read + write, type-preserving)
- RESTBL resource size table (read + write)
"""
import os
import struct
import zlib
from compression import zstd

# Typed values
class U32(int):
    pass

class I64(int):
    pass

class U64(int):
    pass

class F64(float):
    pass

# Vanilla view of romfs
SIDE_DIRS = ("rando-of-time", "remake-rando")  # remake-rando: the folder's name before the rename to Rando of Time


def game_side_dir(root):
    """The originals folder the randomizer app keeps next to a Longshot game folder, or None when there isn't one.
    release/app/Randomizer.cs puts it at <romfs>/../rando-of-time/original, or remake-rando/original from before the
    rename."""
    parent = os.path.dirname(os.path.abspath(root).rstrip("\\/"))
    for name in SIDE_DIRS:
        side = os.path.join(parent, name, "original")
        if os.path.isdir(side):
            return side
    return None


LONGSHOT_HOMES = ("E:/LongshotLauncher-data", os.path.join(os.path.expanduser("~"), "LongshotLauncher-data"))


def longshot_romfs():
    """The game files of Longshot's default build, found the way the randomizer app finds them (builds.json).
    This is the tools' default when REMAKE_ROMFS isn't set. A Longshot update renames its build folder
    (builds/stable/v3.1.0 became v3.1.1 in place), so a version written into the path goes stale. Failing that it's the
    newest build folder with game files, and failing that a path naming what's missing so the error can show it."""
    import glob
    import json
    for home in LONGSHOT_HOMES:
        try:
            with open(os.path.join(home, "builds.json"), encoding="utf-8") as f:
                builds = json.load(f).get("builds") or []
        except (OSError, ValueError, AttributeError):
            builds = []
        for b in sorted((b for b in builds if isinstance(b, dict)), key=lambda b: not b.get("default")):
            folder = str(b.get("folder") or "").replace("\\", "/")
            at = folder.lower().rfind("/builds/")
            # builds.json may still point to the old path after the launcher folder moves.
            for cand in (folder, os.path.join(home, folder[at + 1:]) if at >= 0 else ""):
                if cand and os.path.isdir(os.path.join(cand, "romfs", "Pack")):
                    return os.path.join(cand, "romfs").replace("\\", "/")
        found = sorted(glob.glob(os.path.join(home, "builds", "*", "*", "romfs", "Pack")), key=os.path.getmtime)
        if found:
            return os.path.dirname(found[-1]).replace("\\", "/")
    return LONGSHOT_HOMES[0] + "/builds/(no Longshot build with game files: set REMAKE_ROMFS)/romfs"


class Romfs:
    """Reads game files as vanilla. A saved original (in vanilla_dir) wins over the live romfs file, so files we've
    patched in place still read as their originals.
    A file the install record (installed.json next to vanilla_dir) lists as patched must have its original there.
    Reading the live patched file instead would make a seed depend on which test is installed, so that raises."""

    def __init__(self, root, vanilla_dir=None, overlays=()):
        # The app sets REMAKE_ORIGINAL to the game's backup folder. Keeping the originals and install record next
        # to the game lets a new copy of the randomizer find the same files.
        if vanilla_dir and os.environ.get("REMAKE_ORIGINAL"):
            vanilla_dir = os.environ["REMAKE_ORIGINAL"]
        self.root, self.vanilla, self.overlays = root, vanilla_dir, list(overlays)
        self.patched = set()
        self.checked = set()
        self.game_side = None  # the app's originals next to the game, when it isn't vanilla_dir
        if vanilla_dir:
            import json
            record = os.path.join(os.path.dirname(os.path.abspath(vanilla_dir)), "installed.json")
            if os.path.exists(record):
                files = json.load(open(record, encoding="utf-8")).get("files") or {}
                self.patched = {f.replace("\\", "/") for f in files}
            # Also check the app's install record next to the game. A tool using ./original can otherwise read
            # a live file patched by the app as if it were vanilla.
            side = game_side_dir(root)
            if side and os.path.normcase(side) != os.path.normcase(os.path.abspath(vanilla_dir)):
                rec = os.path.join(os.path.dirname(side), "installed.json")
                if os.path.exists(rec):
                    files = json.load(open(rec, encoding="utf-8")).get("files") or {}
                    self.patched |= {f.replace("\\", "/") for f in files}
                    self.game_side = side
        self.zs = Zs(self.path("Pack/ZsDic.pack.zs"))

    def path(self, rel):
        for o in self.overlays:  # e.g. a built patch, to read the game as it would be with it installed
            v = os.path.join(o, rel)
            if os.path.exists(v):
                return v
        if self.vanilla:
            v = os.path.join(self.vanilla, rel)
            if os.path.exists(v):
                return v
            if self.game_side and os.path.exists(os.path.join(self.game_side, rel)):
                return os.path.join(self.game_side, rel)
            if rel.replace("\\", "/") in self.patched:
                raise FileNotFoundError(f"{rel} is patched in the live game (installed.json) and has no original "
                                        f"copy in {self.vanilla}: refusing to read the patched file as vanilla")
            self._check_vanilla(rel)
        return os.path.join(self.root, rel)

    def _check_vanilla(self, rel):
        """A live file read as vanilla has to be vanilla (data/vanilla_sha256.json lists every file a seed may change).
        One that isn't was changed by something else, like a seed installed without this install record, or it's
        another game version."""
        key = rel.replace("\\", "/")
        if key in self.checked:
            return
        self.checked.add(key)
        want = _vanilla_sums().get(key)
        if want is None:
            return
        import hashlib
        live = os.path.join(self.root, rel)
        if os.path.exists(live) and hashlib.sha256(open(live, "rb").read()).hexdigest() != want:
            raise FileNotFoundError(
                f"{key} in {self.root} is not the game's original file: this game folder already holds another seed or "
                f"mod (put it back first: tools/install.py restore, or Longshot's own repair), or it is another game "
                f"version than the randomizer supports")

    def raw(self, rel):
        return open(self.path(rel), "rb").read()

    def read(self, rel):
        return self.zs.decompress(self.raw(rel))

    def snapshot(self, rel):
        """Keeps a vanilla copy of a file before it gets patched for the first time. It has to be the game's own file.
        If a seed installed by the app changed it, we copy it from that install's originals (next to the game). A live
        file that isn't vanilla (data/vanilla_sha256.json) is refused and never kept as an original. A store for another
        target that got filled while a Longshot seed was installed once held 565 of a seed's files."""
        import hashlib
        import shutil
        dst = os.path.join(self.vanilla, rel)
        if os.path.exists(dst):
            return
        src = os.path.join(self.root, rel)
        if self.game_side and os.path.exists(os.path.join(self.game_side, rel)):
            src = os.path.join(self.game_side, rel)
        elif rel.replace("\\", "/") in self.patched:
            raise FileNotFoundError(f"{rel} is patched in the live game (installed.json) and has no original copy: "
                                    f"refusing to keep the patched file as the original")
        else:
            self._check_vanilla(rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        h = hashlib.sha256(open(dst, "rb").read()).hexdigest()
        with open(os.path.join(self.vanilla, "SHA256SUMS.txt"), "a", encoding="utf-8") as f:
            f.write(f"{h} *./{rel}\n")


# SARC
def sarc_files(data):
    assert data[:4] == b"SARC", data[:4]
    hdr_size, bom = struct.unpack_from("<HH", data, 4)
    e = "<" if bom == 0xFEFF else ">"
    data_off = struct.unpack_from(e + "I", data, 0x0C)[0]
    p = hdr_size
    assert data[p:p + 4] == b"SFAT"
    sfat_hdr, count, _ = struct.unpack_from(e + "HHI", data, p + 4)
    nodes = [struct.unpack_from(e + "IIII", data, p + sfat_hdr + i * 16) for i in range(count)]
    p = p + sfat_hdr + count * 16
    assert data[p:p + 4] == b"SFNT"
    names_off = p + 8
    out = {}
    for _h, attr, s, end in nodes:
        name_off = names_off + (attr & 0xFFFF) * 4
        name = data[name_off:data.index(b"\0", name_off)].decode()
        out[name] = data[data_off + s:data_off + end]
    return out

def sarc_hash(name, key=0x65):
    h = 0
    for c in name.encode("utf-8"):
        h = (h * key + (c if c < 128 else c - 256)) & 0xFFFFFFFF
    return h


def sarc_write(files, align=8):
    """Write a SARC the way the game's actor packs are laid out: entries sorted by name hash,
    names 4-aligned, file data in entry order, each file 8-aligned."""
    names = sorted(files, key=sarc_hash)
    name_blob, name_offs = bytearray(), []
    for n in names:
        name_offs.append(len(name_blob))
        name_blob += n.encode("utf-8") + b"\0"
        while len(name_blob) % 4:
            name_blob.append(0)
    sfat = bytearray(struct.pack("<4sHHI", b"SFAT", 12, len(names), 0x65))
    data = bytearray()
    for n, no in zip(names, name_offs):
        while len(data) % align:
            data.append(0)
        start = len(data)
        data += files[n]
        sfat += struct.pack("<IIII", sarc_hash(n), 0x01000000 | (no // 4), start, len(data))
    sfnt = struct.pack("<4sHH", b"SFNT", 8, 0) + bytes(name_blob)
    head_len = 0x14 + len(sfat) + len(sfnt)
    data_off = (head_len + align - 1) & ~(align - 1)
    total = data_off + len(data)
    header = struct.pack("<4sHHIIHH", b"SARC", 0x14, 0xFEFF, total, data_off, 0x100, 0)
    return header + bytes(sfat) + sfnt + bytes(data_off - head_len) + bytes(data)


# Zstd
class Zs:
    """zstd codec using the game's dictionaries, loaded from a ZsDic.pack.zs."""

    def __init__(self, zsdic_path):
        raw = zstd.decompress(open(zsdic_path, "rb").read())
        self.dicts = {}
        for name, blob in sarc_files(raw).items():
            did = struct.unpack_from("<I", blob, 4)[0]
            self.dicts[did] = (name, zstd.ZstdDict(blob))

    @staticmethod
    def dict_id(raw):
        fhd = raw[4]
        flag = fhd & 3
        if not flag:
            return 0
        single = (fhd >> 5) & 1
        off = 5 + (0 if single else 1)
        size = {1: 1, 2: 2, 3: 4}[flag]
        return int.from_bytes(raw[off:off + size], "little")

    def decompress(self, raw):
        did = self.dict_id(raw)
        if did:
            return zstd.decompress(raw, zstd_dict=self.dicts[did][1])
        return zstd.decompress(raw)

    def compress(self, data, dict_id, level=16):
        if dict_id:
            return zstd.compress(data, level=level, zstd_dict=self.dicts[dict_id][1])
        return zstd.compress(data, level=level)

# BYML read
class HashDict(dict):
    """BYML v7 dictionary keyed by 32- or 64-bit hashes (node types 0x20 / 0x21)."""

    def __init__(self, *args, bits=32, **kw):
        super().__init__(*args, **kw)
        self.bits = bits


class Bin(bytes):
    """BYML binary blob (0xA1), or aligned blob (0xA2) when align is set."""

    def __new__(cls, data, align=None):
        o = super().__new__(cls, data)
        o.align = align
        return o


_BIG = {0xD4: "<q", 0xD5: "<Q", 0xD6: "<d"}
_OFFSET_TYPES = (0xC0, 0xC1, 0x20, 0x21, 0xD4, 0xD5, 0xD6, 0xA1, 0xA2)
_OFFSET_SET = frozenset(_OFFSET_TYPES)
_U32, _F32 = struct.Struct("<I"), struct.Struct("<f")


class BymlReader:
    """Reads BYML into Python values. Dictionaries keep the order their children were laid out in
    the file (Nintendo writes entries sorted by key but children in insertion order), so that
    byml_dump reproduces the file byte for byte."""

    def __init__(self, data):
        self.d = data
        assert data[:2] in (b"YB", b"BY"), "not a BYML file"
        self.big = data[:2] == b"BY"  # big-endian: GameData/GameDataList
        self.e = ">" if self.big else "<"
        self.version, keys_off, strs_off, self.root_off = struct.unpack_from(self.e + "HIII", data, 2)
        self.keys = self._strtab(keys_off) if keys_off else []
        self.strs = self._strtab(strs_off) if strs_off else []

    def _u24(self, off):
        return int.from_bytes(self.d[off:off + 3], "big" if self.big else "little")

    def _u32(self, off):
        return struct.unpack_from(self.e + "I", self.d, off)[0]

    def _strtab(self, off):
        assert self.d[off] == 0xC2
        n = self._u24(off + 1)
        offs = struct.unpack_from(f"{self.e}{n + 1}I", self.d, off + 4)
        return [self.d[off + offs[i]:self.d.index(b"\0", off + offs[i])].decode("utf-8") for i in range(n)]

    def root(self):
        if not self.root_off:
            return None
        return self._node(self.d[self.root_off], self.root_off)

    @staticmethod
    def _layout_order(entries):
        # entries are (slot index, key, type, raw value) in slot order. Children get ordered by where their data
        # sits, inline values first (slot order), then the rest by offset and then slot.
        return ([e for e in entries if e[2] not in _OFFSET_SET] +
                sorted((e for e in entries if e[2] in _OFFSET_SET), key=lambda e: (e[3], e[0])))

    # Containers read each entry table with one struct call and decode the common values in place, since a level file
    # has millions of values. The results are exactly what reading them one by one through _node gives.
    def _node(self, t, v):
        if t == 0xC1:
            return self._dict(v)
        if t == 0xC0:
            return self._list(v)
        if t == 0xA0: return self.strs[v]
        if t == 0xD1: return v - 0x100000000 if v & 0x80000000 else v
        if t == 0xD2: return _F32.unpack(_U32.pack(v))[0]
        if t == 0xD0: return bool(v)
        if t == 0xD3: return U32(v)
        if t == 0xD4: return I64(struct.unpack_from(self.e + "q", self.d, v)[0])
        if t == 0xD5: return U64(struct.unpack_from(self.e + "Q", self.d, v)[0])
        if t == 0xD6: return F64(struct.unpack_from(self.e + "d", self.d, v)[0])
        if t == 0xFF: return None
        if t == 0xA1:
            n = self._u32(v)
            return Bin(self.d[v + 4:v + 4 + n])
        if t == 0xA2:
            n, align = self._u32(v), self._u32(v + 4)
            return Bin(self.d[v + 8:v + 8 + n], align)
        if t in (0x20, 0x21):
            n = self._u24(v + 1)
            esz, hfmt = (8, self.e + "I") if t == 0x20 else (12, self.e + "Q")
            types_off = v + 4 + n * esz
            entries = []
            for i in range(n):
                p = v + 4 + i * esz
                h = struct.unpack_from(hfmt, self.d, p)[0]
                entries.append((i, h, self.d[types_off + i], self._u32(p + esz - 4)))
            return HashDict({h: self._node(tt, raw) for _, h, tt, raw in self._layout_order(entries)},
                            bits=32 if t == 0x20 else 64)
        raise NotImplementedError(f"BYML node type {t:#x} at {v:#x}")

    def _dict(self, v):
        """A dictionary in layout order (_layout_order). Inline values come first, in slot order as they're met, then
        the values held by offset, sorted by offset and then slot."""
        n = self._u24(v + 1)
        w = struct.unpack_from(f"{self.e}{2 * n}I", self.d, v + 4)
        keys, strs, node, out, offs = self.keys, self.strs, self._node, {}, []
        for i in range(n):
            kw, raw = w[2 * i], w[2 * i + 1]
            if self.big:  # each entry is key index (u24) then type byte in the file's byte order, then the value
                k, tt = keys[kw >> 8], kw & 0xFF
            else:
                k, tt = keys[kw & 0xFFFFFF], kw >> 24
            if tt in _OFFSET_SET:
                offs.append((raw, i, k, tt))  # (offset, slot) is unique, so the sort never compares further
            elif tt == 0xA0:
                out[k] = strs[raw]
            elif tt == 0xD2:
                out[k] = _F32.unpack(_U32.pack(raw))[0]
            elif tt == 0xD1:
                out[k] = raw - 0x100000000 if raw & 0x80000000 else raw
            elif tt == 0xD0:
                out[k] = bool(raw)
            else:
                out[k] = node(tt, raw)
        if offs:
            offs.sort()
            for raw, _, k, tt in offs:
                out[k] = self._dict(raw) if tt == 0xC1 else self._list(raw) if tt == 0xC0 else node(tt, raw)
        return out

    def _list(self, v):
        """An array; one whose values are all strings, ints or floats is read in one struct call."""
        n = self._u24(v + 1)
        types = self.d[v + 4:v + 4 + n]
        vo = v + 4 + ((n + 3) & ~3)
        if n and types.count(types[0]) == n:
            t = types[0]
            if t == 0xA0:
                strs = self.strs
                return [strs[x] for x in struct.unpack_from(f"{self.e}{n}I", self.d, vo)]
            if t == 0xD2:  # the 4 value bytes as a float in the file's byte order, same as _node's repacking gives
                return list(struct.unpack_from(f"{self.e}{n}f", self.d, vo))
            if t == 0xD1:
                return list(struct.unpack_from(f"{self.e}{n}i", self.d, vo))
        vals = struct.unpack_from(f"{self.e}{n}I", self.d, vo)
        node, strs = self._node, self.strs
        return [strs[vals[i]] if types[i] == 0xA0 else node(types[i], vals[i]) for i in range(n)]


# The same BYML bytes get parsed again and again within one run, and each caller wants its own tree to change. One
# in_game_check run did 62,265 loads of 1,165 distinct files, and 20 of its 23 s of parsing were repeats.
# So a run keeps the tree of any bytes it has parsed twice, pickled (about the file's size, ~45 MB there), and later
# loads unpickle a fresh copy. That's ~5x faster than parsing and gives the same values, types, attributes, float
# bits and dict order, since pickle rebuilds U32/I64/U64/F64, HashDict's bits and Bin's align.
# Keyed by the bytes' BLAKE2b digest and length, bytes objects only. REMAKE_NO_CACHE=1 turns the memo off.
_BYML_SEEN, _BYML_MEMO = set(), {}
_BYML_MEMO_ON = os.environ.get("REMAKE_NO_CACHE") != "1"


def byml_load(data, allow_big=False):
    """(root, version). Big-endian files load only with allow_big=True, and must be written back with
    byml_dump(..., big=True) (see byml_is_big) so their byte order doesn't silently change."""
    key = None
    if _BYML_MEMO_ON and type(data) is bytes:
        import hashlib
        key = (hashlib.blake2b(data, digest_size=20).digest(), len(data))
        hit = _BYML_MEMO.get(key)
        if hit is not None:
            big, version, blob = hit
            if big and not allow_big:
                raise ValueError("big-endian BYML: load with allow_big=True and write with byml_dump(..., big=True)")
            import pickle
            return pickle.loads(blob), version
    r = BymlReader(data)
    if r.big and not allow_big:
        raise ValueError("big-endian BYML: load with allow_big=True and write with byml_dump(..., big=True)")
    root = r.root()
    if key is not None:
        if key in _BYML_SEEN:
            import pickle
            _BYML_MEMO[key] = (r.big, r.version, pickle.dumps(root, protocol=pickle.HIGHEST_PROTOCOL))
        else:
            _BYML_SEEN.add(key)
    return root, r.version

# BYML write
# The node type for a value of exactly these classes. It's the same answer the isinstance chain below gives, but a
# level file asks that millions of times when it's written. HashDict, Bin and any other subclass go through the chain.
_EXACT_TYPE = {bool: 0xD0, str: 0xA0, type(None): 0xFF, dict: 0xC1, list: 0xC0, U32: 0xD3, I64: 0xD4, U64: 0xD5,
               F64: 0xD6, int: 0xD1, float: 0xD2}
_SIMPLE_LEAF = {str: 0xA0, int: 0xD1, bool: 0xD0, type(None): 0xFF, U32: 0xD3}  # byml_dump's freeze: (type, value)


def _type_of(v):
    t = _EXACT_TYPE.get(type(v))
    if t is not None:
        return t
    if isinstance(v, bool): return 0xD0
    if isinstance(v, str): return 0xA0
    if v is None: return 0xFF
    if isinstance(v, HashDict): return 0x20 if v.bits == 32 else 0x21
    if isinstance(v, dict): return 0xC1
    if isinstance(v, list): return 0xC0
    if isinstance(v, Bin): return 0xA1 if v.align is None else 0xA2
    if isinstance(v, U32): return 0xD3
    if isinstance(v, I64): return 0xD4
    if isinstance(v, U64): return 0xD5
    if isinstance(v, F64): return 0xD6
    if isinstance(v, int): return 0xD1
    if isinstance(v, float): return 0xD2
    raise TypeError(type(v))


_CONTAINERS = (0xC0, 0xC1, 0x20, 0x21)


def _hdr(t, n, e):
    """Container/string-table header: type byte, then a 24-bit count in the file's byte order."""
    return bytes([t]) + n.to_bytes(3, "big" if e == ">" else "little")


def _strtab_bytes(strings, e="<"):
    n = len(strings)
    head = 4 + 4 * (n + 1)
    offs, body = [], bytearray()
    for s in strings:
        offs.append(head + len(body))
        body += s.encode("utf-8") + b"\0"
    offs.append(head + len(body))
    out = bytearray(_hdr(0xC2, n, e))
    for o in offs:
        out += struct.pack(e + "I", o)
    out += body
    while len(out) % 4:
        out += b"\0"
    return bytes(out)


def _bkey(s):
    return s.encode("utf-8")


def byml_is_big(data):
    return data[:2] == b"BY"


def byml_dump(root, version=7, big=False):
    """BYML bytes. big=True writes big-endian ("BY"), the byte order of GameData/GameDataList."""
    e = ">" if big else "<"
    bigf = {t: e + f[1:] for t, f in _BIG.items()}
    keys, strs = set(), set()
    bigs = []  # (type, value) of every 64-bit value and blob, in traversal order (laid out below)
    et = _EXACT_TYPE.get  # `et(type(x)) or _type_of(x)` is _type_of(x) without a call for the exact classes

    def collect(v):
        t = _type_of(v)
        if t == 0xC1:
            keys.update(v)
            children = v.values()
        elif t in (0x20, 0x21):
            children = v.values()
        elif t == 0xC0:
            children = v
        else:
            if t == 0xA0:
                strs.add(v)
            elif t in bigf or t in (0xA1, 0xA2):
                bigs.append((t, v))
            return
        for x in children:  # leaves here, containers by recursion, so it's the same walk in the same order
            tx = et(type(x)) or _type_of(x)
            if tx == 0xA0:
                strs.add(x)
            elif tx in _CONTAINERS:
                collect(x)
            elif tx in bigf or tx in (0xA1, 0xA2):
                bigs.append((tx, x))
    collect(root)

    kb = {k: _bkey(k) for k in keys}  # each key's sort bytes, once
    kbget = kb.__getitem__
    key_list = sorted(keys, key=kbget)
    str_list = sorted(strs, key=_bkey)
    if len(key_list) > 0x1000000:  # a key index is 24 bits (as key_idx[k].to_bytes(3, ...) refused)
        raise OverflowError("int too big to convert")
    key_idx = {k: i for i, k in enumerate(key_list)}
    str_idx = {s: i for i, s in enumerate(str_list)}

    out = bytearray(16)
    keys_off = len(out) if key_list else 0
    if key_list:
        out += _strtab_bytes(key_list, e)
    strs_off = len(out) if str_list else 0
    if str_list:
        out += _strtab_bytes(str_list, e)

    # 64-bit values and binary blobs, deduplicated, in traversal order
    big_off = {}

    def big_key(t, v):
        if t in bigf:
            return (t, struct.pack(bigf[t], v))
        return (t, bytes(v), v.align)

    for t, v in bigs:  # same traversal order as collect, every container's children in insertion order
        k = big_key(t, v)
        if k in big_off:
            continue
        if t in bigf:
            while len(out) % 4:
                out.append(0)
            big_off[k] = len(out)
            out.extend(k[1])
        elif t == 0xA1:
            big_off[k] = len(out)
            out.extend(struct.pack(e + "I", len(v)) + bytes(v))
        else:
            big_off[k] = len(out)
            out.extend(struct.pack(e + "II", len(v), v.align) + bytes(v))
    while len(out) % 4:
        out.append(0)

    frozen = {}
    # Equal containers are written once. A container's identity is a small number for its structure (hash-consing).
    # Two containers get the same number exactly when their whole contents are equal, the way nested tuples would
    # compare. But each container is only looked at once (memo, by object) and hashed shallowly, instead of hashing the
    # whole subtree again at every level, which took ~10 s on a big level file.
    interned, memo = {}, {}
    sget = _SIMPLE_LEAF.get  # leaves whose freeze is just (type, value)

    def freeze(v):
        t = _type_of(v)
        if t in _CONTAINERS:
            hit = memo.get(id(v))
            if hit is not None:
                return hit[1]
            parts = []
            if t == 0xC0:
                for x in v:
                    st = sget(type(x))
                    parts.append((st, x) if st is not None else freeze(x))
            else:
                for k in (sorted(v, key=kbget) if t == 0xC1 else sorted(v)):
                    x = v[k]
                    st = sget(type(x))
                    parts.append((k, (st, x) if st is not None else freeze(x)))
            key = (t, tuple(parts))
            fid = interned.setdefault(key, len(interned))
            memo[id(v)] = (v, fid)  # holds v, so its id stays its own while we write
            return fid
        if t == 0xD2:
            return (t, struct.pack("<f", v))
        if t in bigf or t in (0xA1, 0xA2):
            return big_key(t, v)
        return (t, v)

    def scalar(t, v):
        if t == 0xA0: return str_idx[v]
        if t == 0xD0: return 1 if v else 0
        if t == 0xD1: return struct.unpack("<I", struct.pack("<i", v))[0]
        if t == 0xD2: return struct.unpack("<I", struct.pack("<f", v))[0]
        if t == 0xD3: return int(v)
        if t == 0xFF: return 0
        if t in bigf or t in (0xA1, 0xA2): return big_off[big_key(t, v)]
        raise TypeError(hex(t))

    def value(tx, x):  # an entry's 32-bit value, a string's index (the commonest) or a scalar's
        return str_idx[x] if tx == 0xA0 else scalar(tx, x)

    # Entry tables get reserved, children are written after them, then each table is filled with one struct call.
    # It gives the same bytes as writing entry by entry, and an out-of-range value still raises struct.error.
    def emit(v):
        fz = freeze(v)
        hit = frozen.get(fz)
        if hit is not None:
            return hit
        t = _type_of(v)
        start = len(out)
        frozen[fz] = start
        if t == 0xC0:
            n = len(v)
            types = [et(type(x)) or _type_of(x) for x in v]
            out.extend(_hdr(0xC0, n, e))
            out.extend(bytes(types))
            while len(out) % 4:
                out.append(0)
            slots = len(out)
            out.extend(bytes(4 * n))
            vals = [emit(x) if tx in _CONTAINERS else value(tx, x) for x, tx in zip(v, types)]
            struct.pack_into(f"{e}{n}I", out, slots, *vals)
            return start
        tv = {k: et(type(x)) or _type_of(x) for k, x in v.items()}
        if t == 0xC1:
            order = sorted(v, key=kbget)
            esz = 8
        else:
            order = sorted(v)
            esz = 8 if t == 0x20 else 12
        n = len(order)
        out.extend(_hdr(t, n, e))
        slots = len(out)
        out.extend(bytes(esz * n))
        if t != 0xC1:
            out.extend(bytes(tv[k] for k in order))
            while len(out) % 4:
                out.append(0)
        # children are laid out in insertion order, entries in sorted order
        child = {k: emit(x) for k, x in v.items() if tv[k] in _CONTAINERS}
        words = []
        for k in order:
            tx = tv[k]
            if t == 0xC1:  # key index (24 bits) then the type byte, in the file's byte order
                words.append((key_idx[k] << 8 | tx) if big else (key_idx[k] | tx << 24))
            else:
                words.append(k)
            words.append(child[k] if tx in _CONTAINERS else value(tx, v[k]))
        struct.pack_into(e + ("II" if t != 0x21 else "QI") * n, out, slots, *words)
        return start

    root_off = emit(root) if root is not None else 0
    struct.pack_into(e + "2sHIII", out, 0, b"BY" if big else b"YB", version, keys_off, strs_off, root_off)
    return bytes(out)

# RESTBL
class Restbl:
    NAME_LEN = 0xA0

    def __init__(self, data):
        assert data[:6] == b"RESTBL", data[:6]
        self.version, self.name_len, n_crc, n_name = struct.unpack_from("<IIII", data, 6)
        p = 22
        self.crc = {}
        for _ in range(n_crc):
            h, s = struct.unpack_from("<II", data, p)
            self.crc[h] = s
            p += 8
        self.names = {}
        for _ in range(n_name):
            raw = data[p:p + self.name_len]
            name = raw[:raw.index(b"\0")].decode()
            self.names[name] = struct.unpack_from("<I", data, p + self.name_len)[0]
            p += self.name_len + 4

    def get(self, path):
        if path in self.names:
            return self.names[path]
        return self.crc.get(zlib.crc32(path.encode()))

    def set(self, path, size):
        if path in self.names:
            self.names[path] = size
        else:
            self.crc[zlib.crc32(path.encode())] = size

    def dump(self):
        out = bytearray(b"RESTBL")
        out += struct.pack("<IIII", self.version, self.name_len, len(self.crc), len(self.names))
        for h in sorted(self.crc):
            out += struct.pack("<II", h, self.crc[h])
        for name in sorted(self.names):
            out += name.encode().ljust(self.name_len, b"\0") + struct.pack("<I", self.names[name])
        return bytes(out)


# Hashes
def murmur3_32(data, seed=0):
    """MurmurHash3 x86 32-bit: GameData flag names, enum values and other name hashes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    c1, c2, h, n = 0xCC9E2D51, 0x1B873593, seed & 0xFFFFFFFF, len(data)
    for i in range(0, n - n % 4, 4):
        k = int.from_bytes(data[i:i + 4], "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[n - n % 4:]
    k = 0
    for j, b in enumerate(tail):
        k |= b << (8 * j)
    if tail:
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= n
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


_SUMS = {}


def _vanilla_sums():
    """{rel: sha256} of data/vanilla_sha256.json ({} without it)."""
    if "files" not in _SUMS:
        import json
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vanilla_sha256.json")
        _SUMS["files"] = json.load(open(p, encoding="utf-8")).get("files", {}) if os.path.exists(p) else {}
    return _SUMS["files"]
