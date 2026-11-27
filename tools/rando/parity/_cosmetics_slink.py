"""Sound link table (SLink2/slink2.Product.111.bslnk.zs, XLNK v0x22) and sound archives (.bars), read from the files.

How a sound gets played. An actor's SLink user (CRC32 of its name, e.g. "Player",
"Ocarina", or a bgm.byml player's SLinkUserName) has call-table keys ("HeartAlert", "Ocarina_HighD"). Each key's
asset parameters hold `RuntimeAssetName`, the .bars entry that actually plays (a short sound, or a prefetch block
plus Sound/Resource/Stream/<name>.bwav). The runtime name is a u32 `1<<24 | offset into the name table`, so we can
point a key at any other sound whose name is already in the table, in place, without changing the file size.
"@Blank" is a silent asset (the game itself uses it 789 times).
"""
import struct
import zlib

SLINK = "SLink2/slink2.Product.111.bslnk.zs"
BLANK = "@Blank"
_HDR = "<4sIIIII QQ IIIIII Q I I QQ"


class SLink:
    def __init__(self, data):
        self.d = data
        h = struct.unpack_from(_HDR, data, 0)
        if h[0] != b"XLNK" or h[2] != 0x22:
            raise ValueError(f"not a v0x22 XLNK sound link table ({h[0]!r} {h[2]:#x})")
        self.n_user, self.nt = h[15], h[18]
        hashes = struct.unpack_from(f"<{self.n_user}I", data, 0x60)
        offs = struct.unpack_from(f"<{self.n_user}Q", data, 0x60 + 4 * self.n_user)
        self.users = dict(zip(hashes, offs))
        pdt = 0x60 + 12 * self.n_user
        psize, nu, na, _nx, ntg = struct.unpack_from("<5I", data, pdt)
        self.n_user_params = nu
        ents = pdt + 0x18
        cnt = nu + na + ntg
        strs = ents + cnt * 24
        names = []
        for i in range(cnt):
            np_ = struct.unpack_from("<Q", data, ents + i * 24)[0]
            names.append(data[strs + np_:data.index(b"\0", strs + np_)].decode())
        self.asset_params = names[nu:nu + na]
        self.apt = pdt + psize  # asset parameter table (one entry per user asset)
        self._name_offs = None

    # Names
    def name(self, off):
        return self.d[self.nt + off:self.d.index(b"\0", self.nt + off)].decode("utf-8", "replace")

    def name_off(self, s):
        """Offset of string s in the name table, or None (only names already there can be used)."""
        if self._name_offs is None:
            self._name_offs = {}
            p, end = self.nt, len(self.d)
            while p < end:
                q = self.d.find(b"\0", p)
                if q < 0:
                    break
                if q > p:
                    self._name_offs.setdefault(self.d[p:q].decode("utf-8", "replace"), p - self.nt)
                p = q + 1
        return self._name_offs.get(s)

    # Users and keys
    def user(self, name):
        return self.users.get(zlib.crc32(name.encode()))

    def calls(self, user_name):
        """[{key, aid, flag, params}] for a user. params is the absolute offset of the asset's parameters, or None for
        containers."""
        uo = self.user(user_name)
        if uo is None:
            return []
        return self._calls_at(uo)

    def leaves(self):
        """{position of the RuntimeAssetName value: parameter offset} of every user's leaf assets, each parameter entry
        once. Users are walked by table offset since we don't know all their names."""
        if getattr(self, "_leaves", None) is None:
            self._leaves = {}
            for uo in sorted(set(self.users.values())):
                for c in self._calls_at(uo):
                    if c["params"] is not None:
                        pos = self.runtime_pos(c["params"])
                        if pos is not None:
                            self._leaves.setdefault(pos, c["params"])
        return self._leaves

    def _calls_at(self, uo):
        (_setup, n_lp, _nlpe, n_ct, *_rest) = struct.unpack_from("<IHHIIIIIIIIIIQ", self.d, uo)
        p = uo + 0x38 + 8 * n_lp + 4 * self.n_user_params + 2 * n_ct
        p = (p + 3) & ~3
        out = []
        for i in range(n_ct):
            kp, aid, fl, _dur, _par, _h1, _h2, _z, pp, _cp = struct.unpack_from("<QhHiiIIIQQ", self.d, p + i * 0x30)
            leaf = aid >= 0 and not (fl & 1)
            out.append({"key": self.name(kp), "aid": aid, "flag": fl, "params": self.apt + pp if leaf else None})
        return out

    def params(self, off):
        """{param name: value} of an asset (strings resolved; other values as 'type:payload')."""
        mask = struct.unpack_from("<Q", self.d, off)[0]
        out, p = {}, off + 8
        for bit in range(64):
            if mask >> bit & 1:
                v = struct.unpack_from("<I", self.d, p)[0]
                p += 4
                name = self.asset_params[bit] if bit < len(self.asset_params) else f"bit{bit}"
                out[name] = self.name(v & 0xFFFFFF) if v >> 24 == 1 else f"{v >> 24}:{v & 0xFFFFFF}"
        return out

    def runtime_pos(self, off):
        """File offset of the RuntimeAssetName u32 of the asset whose parameters start at off (asset param bit 1)."""
        mask = struct.unpack_from("<Q", self.d, off)[0]
        if not mask & 2:
            return None
        return off + 8 + 4 * (mask & 1)

    def assets(self, user_name):
        """[(key, RuntimeAssetName, params)] of a user's leaf assets."""
        out = []
        for c in self.calls(user_name):
            if c["params"] is not None:
                prm = self.params(c["params"])
                out.append((c["key"], prm.get("RuntimeAssetName"), prm))
        return out


def repoint(data, ops):
    """Apply [{"user", "key", "asset", "was"}] to a decompressed sound link table (bytes) and return the new bytes.
    A key name can hold several layered assets (e.g. a bomb explosion's ground and water sounds), and only the ones
    that play `was` change. Every op has to match at least one asset, and `asset` has to be in the name table already.
    {"remap": {sound: other sound}} re-points every asset of every user that plays a sound (remake_shuffle_all_sfx).
    Each op reads the vanilla table and a later op wins. So a remap's chains (a -> b, b -> c) stay one step, and the
    OoTR settings' picks, listed after the remap, override it on their keys."""
    sl = SLink(data)
    out = bytearray(data)
    by_name = None
    for op in ops:
        if "remap" in op:
            if by_name is None:
                by_name = {}
                for pos in sl.leaves():
                    cur = struct.unpack_from("<I", data, pos)[0]
                    if cur >> 24 == 1:
                        by_name.setdefault(sl.name(cur & 0xFFFFFF), []).append(pos)
            for was, asset in sorted(op["remap"].items()):
                no = sl.name_off(asset)
                if no is None or not by_name.get(was):
                    raise ValueError(f"sound link: remap {was!r} -> {asset!r}: "
                                     f"{'no asset plays it' if no is not None else 'not in the name table'}")
                for pos in by_name[was]:
                    struct.pack_into("<I", out, pos, (1 << 24) | no)
            continue
        no = sl.name_off(op["asset"])
        if no is None:
            raise ValueError(f"sound link: {op['asset']!r} is not in the name table")
        hits = 0
        for c in sl.calls(op["user"]):
            if c["key"] != op["key"] or c["params"] is None:
                continue
            pos = sl.runtime_pos(c["params"])
            if pos is None:
                continue
            cur = struct.unpack_from("<I", data, pos)[0]
            if cur >> 24 != 1 or (op.get("was") is not None and sl.name(cur & 0xFFFFFF) != op["was"]):
                continue
            struct.pack_into("<I", out, pos, (1 << 24) | no)
            hits += 1
        if not hits:
            raise ValueError(f"sound link: no asset {op['user']}/{op['key']} playing {op.get('was')!r} "
                             f"(different game version?)")
    return bytes(out)


# .bars (sound archives)
def bars_entries(data):
    """[{name, prefetch, ch, rate, samples, secs}] of a .bars archive (BARS v0x0102: CRC32 table, AMTA + BWAV)."""
    if data[:4] != b"BARS":
        raise ValueError("not a BARS archive")
    _size, _bom, _ver, cnt = struct.unpack_from("<IHHI", data, 4)
    out = []
    for i in range(cnt):
        ao, bo = struct.unpack_from("<II", data, 0x10 + 4 * cnt + 8 * i)
        so = struct.unpack_from("<I", data, ao + 0x24)[0]
        p = ao + 0x24 + so
        e = {"name": data[p:data.index(b"\0", p)].decode()}
        if bo != 0xFFFFFFFF and data[bo:bo + 4] == b"BWAV":
            e.update(bwav_info(data, bo))
        out.append(e)
    return out


def bwav_info(data, base=0):
    _ver, _crc, pre, nch = struct.unpack_from("<HIHH", data, base + 6)
    # channel 0 info at +0x10 is codec, pan, rate, samples (x2) and DSP coefficients. At +0x30 come two data offsets,
    # a flag, loop end (0xFFFFFFFF means no loop) and loop start, in samples
    _codec, _pan, rate, ns1, ns2 = struct.unpack_from("<HHIII", data, base + 0x10)
    loop_end, loop_start = struct.unpack_from("<II", data, base + 0x10 + 0x3C)
    samples = max(ns1, ns2)
    looping = loop_end != 0xFFFFFFFF
    return {"prefetch": pre, "ch": nch, "rate": rate, "samples": samples,
            "secs": round(samples / rate, 2) if rate else 0.0, "loop": looping,
            "loop_start": round(loop_start / rate, 2) if rate and looping else None}
