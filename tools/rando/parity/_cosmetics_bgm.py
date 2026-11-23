"""The music graph edits that go with re-pointed music keys, and the music read-back.

A player in Sound/Bgm/bgm.Product.111.byml.zs (big-endian BYML) plays its SLink user's keys through Asset nodes. A
node either lets its stream decide how long it plays (IsDurationAuto, so a looping stream loops on its own loop
points for as long as the player runs), or plays a fixed Duration, maybe from a StartOffset, and then moves on, or
holds (IsDurationInfinity). Hyrule Field, Market, Kakariko, Kokiri Forest, Gerudo Fortress, Lon Lon Ranch, the
Fishing Pond, the Ice Cavern, the Fire Temple, the Deku Tree and others are built from 9 to 35 s segments chained at
random, each one a fixed-Duration node, and the segments don't loop. A re-pointed key keeps its node, so a whole
looping track put in a segment node played its first 12.8 s and then started again on the next segment ("it only
loops the first seconds of the song").

So every Asset node that plays a key re-pointed at a looping track plays it whole, from its start, for as long as
the player runs. A fixed-Duration node becomes IsDurationAuto and its StartOffset becomes 0. In case the game reads
the Duration anyway, that becomes LONG seconds too (vanilla never pairs the two). The track then loops on its own
loop points, the BWAV loop start and end in its BGM_Static entry and stream, which nothing here changes.
Nodes re-pointed at a jingle (fanfares, cutscene jingles, no loop) keep their timing, because the fanfares' Callback
and the chest suspense's wait depend on it. Day and night, battle and the other changes stay as the game has them.
Those are the players' start and stop conditions and conditional transitions, and we don't touch them. Every edit
is in place (a bool or a float in its dictionary entry), so the file keeps its size and layout byte for byte apart
from those values.
"""
import os
import struct

import _cosmetics_slink as S

BGM = "Sound/Bgm/bgm.Product.111.byml.zs"
STATIC = "Sound/Resource/BGM_Static.bars.zs"
# Ten hours in seconds. If the game converts it to samples at 48 kHz, 1.73e9 still fits in a signed int32.
LONG = 36000.0


# Minimal BYML reader that keeps value offsets
class _Byml:
    def __init__(self, data):
        if data[:2] != b"BY":
            raise ValueError("bgm.byml: not a big-endian BYML file")
        self.d = data
        _ver, keys_off, strs_off, self.root = struct.unpack_from(">HIII", data, 2)
        self.keys = self._strtab(keys_off)
        self.strs = self._strtab(strs_off)

    def _u24(self, off):
        return int.from_bytes(self.d[off:off + 3], "big")

    def _strtab(self, off):
        n = self._u24(off + 1)
        offs = struct.unpack_from(f">{n + 1}I", self.d, off + 4)
        return [self.d[off + offs[i]:self.d.index(b"\0", off + offs[i])].decode("utf-8") for i in range(n)]

    def entries(self, off):
        """{key: (type, raw value, offset of the value)} of the dictionary at off."""
        if self.d[off] != 0xC1:
            raise ValueError(f"bgm.byml: no dictionary at {off:#x}")
        out = {}
        for i in range(self._u24(off + 1)):
            p = off + 4 + 8 * i
            kw, raw = struct.unpack_from(">II", self.d, p)
            out[self.keys[kw >> 8]] = (kw & 0xFF, raw, p + 4)
        return out

    def items(self, off):
        """[(type, raw value)] of the array at off."""
        if self.d[off] != 0xC0:
            raise ValueError(f"bgm.byml: no array at {off:#x}")
        n = self._u24(off + 1)
        types = self.d[off + 4:off + 4 + n]
        vals = struct.unpack_from(f">{n}I", self.d, off + 4 + ((n + 3) & ~3))
        return list(zip(types, vals))

    def string(self, entry):
        return self.strs[entry[1]] if entry and entry[0] == 0xA0 else None

    def boolean(self, entry):
        return (entry[2], bool(entry[1])) if entry and entry[0] == 0xD0 else None

    def seconds(self, entry):
        """(offset, value) of a {"Type": "Second", "Value": float} dictionary's value."""
        if not entry or entry[0] != 0xC1:
            return None
        d = self.entries(entry[1])
        if self.string(d.get("Type")) != "Second" or not d.get("Value") or d["Value"][0] != 0xD2:
            return None
        return d["Value"][2], struct.unpack(">f", struct.pack(">I", d["Value"][1]))[0]


def asset_nodes(data):
    """[{player, user, node, key, auto, infinite: (offset, bool), duration, offset: (offset, seconds) or None}] for
    every Asset node."""
    b = _Byml(data)
    root = b.entries(b.root)
    out = []
    for player, (_t, poff, _o) in sorted(b.entries(root["BGM"][1]).items()):
        p = b.entries(poff)
        user = b.string(p.get("SLinkUserName"))
        if "Node" not in p:
            continue
        for _t, noff in b.items(p["Node"][1]):
            n = b.entries(noff)
            if b.string(n.get("Type")) != "Asset" or not b.string(n.get("Key")):
                continue
            out.append({"player": player, "user": user, "node": b.string(n.get("Name")), "key": b.string(n["Key"]),
                        "auto": b.boolean(n.get("IsDurationAuto")), "infinite": b.boolean(n.get("IsDurationInfinity")),
                        "duration": b.seconds(n.get("Duration")), "offset": b.seconds(n.get("StartOffset"))})
    return out


def _positions(sl, cache, user, key):
    """File offsets of the RuntimeAssetName values a user's key plays (several user names can share one table)."""
    if (user, key) not in cache:
        cache[(user, key)] = tuple(sorted(sl.runtime_pos(c["params"]) for c in sl.calls(user)
                                          if c["key"] == key and c["params"] is not None
                                          and sl.runtime_pos(c["params"]) is not None))
    return cache[(user, key)]


def replaced_nodes(bgm_data, slink_old, slink_new):
    """Asset nodes whose key now plays another music track, as [(node row, the track it plays now)]."""
    sl = S.SLink(slink_old)
    new = S.SLink(slink_new)
    cache = {}
    out = []
    for n in asset_nodes(bgm_data):
        if not n["user"]:
            continue
        for pos in _positions(sl, cache, n["user"], n["key"]):
            was, now = struct.unpack_from("<I", slink_old, pos)[0], struct.unpack_from("<I", slink_new, pos)[0]
            if was != now and now >> 24 == 1 and new.name(now & 0xFFFFFF) != S.BLANK:
                out.append((n, new.name(now & 0xFFFFFF)))
                break
    return out


def track_loops(fs):
    """track name -> True / False from its BWAV loop flag (the stream's, else its BGM_Static entry's), or None if
    unknown."""
    static = {e["name"]: e for e in S.bars_entries(fs.read(STATIC))}
    stream_dir = os.path.join(fs.root, "Sound", "Resource", "Stream")
    cache = {}

    def loops(track):
        if track not in cache:
            e = static.get(track)
            if e is None:
                cache[track] = None
            else:
                sp = os.path.join(stream_dir, track + ".bwav")
                info = S.bwav_info(open(sp, "rb").read(0x100)) if os.path.exists(sp) else e
                cache[track] = bool(info.get("loop"))
        return cache[track]
    return loops


def loop_edits(bgm_data, slink_old, slink_new, loops):
    """[(offset, new 4 bytes, note)] so each node playing a re-pointed looping track plays it whole, from its start."""
    edits = []
    for n, track in replaced_nodes(bgm_data, slink_old, slink_new):
        if not loops(track):
            continue  # a jingle keeps its node's timing
        where = f"{n['player']}/{n['key']}"
        fixed = not (n["auto"] and n["auto"][1]) and not (n["infinite"] and n["infinite"][1])
        if fixed:
            if n["auto"] is None or n["duration"] is None:
                raise ValueError(f"bgm.byml: {where} node {n['node']} has no IsDurationAuto or Duration value")
            edits.append((n["auto"][0], struct.pack(">I", 1), f"{where}: whole track ({track})"))
            edits.append((n["duration"][0], struct.pack(">f", LONG), f"{where}: no fixed length"))
        if n["offset"] and n["offset"][1] != 0.0:
            edits.append((n["offset"][0], struct.pack(">f", 0.0), f"{where}: from the start"))
    return edits


def apply(bgm_data, edits):
    out = bytearray(bgm_data)
    for off, new, _note in edits:
        out[off:off + 4] = new
    return bytes(out)


def build(fs, slink_old, slink_new):
    """The patched bgm.byml (decompressed), or None when no node needs a change."""
    bgm = fs.read(BGM)
    edits = loop_edits(bgm, slink_old, slink_new, track_loops(fs))
    return apply(bgm, edits) if edits else None


# Read-back
def _fork_branches(nodes):
    """{fork node name: [set of keys each branch reaches]} for a player's node list (dict form, byml_load)."""
    by = {nd["Name"]: nd for nd in nodes}

    def reach(start):
        keys, todo, seen = set(), [start], set()
        while todo:
            nm = todo.pop()
            if nm in seen or nm not in by:
                continue
            seen.add(nm)
            nd = by[nm]
            if nd.get("Type") == "Asset" and nd.get("Key"):
                keys.add(nd["Key"])
            todo += [t["DestinationNode"] for t in nd.get("Transition") or [] if t.get("DestinationNode")]
        return keys
    return {nd["Name"]: [reach(t["DestinationNode"]) for t in nd.get("Transition") or [] if t.get("DestinationNode")]
            for nd in nodes if nd.get("Type") == "Fork"}


def verify(fs, patch_dir, slink_new, music_log=None):
    """Problems (strings) with a built patch's music.
    - Every node playing a re-pointed looping track plays it whole from its start (bgm.byml in the patch), and
      bgm.byml differs from vanilla in exactly those values.
    - In the plan's log, an area or event slot plays a looping track and a jingle (fanfare, song, cutscene jingle) one
      that ends.
    - No fork plays a new track on two branches at once (the same track twice, out of step)."""
    from romtools import byml_load
    problems = []
    old_sl = fs.read(S.SLINK)
    bgm_old = fs.read(BGM)
    p = os.path.join(patch_dir, BGM)
    bgm_new = fs.zs.decompress(open(p, "rb").read()) if os.path.exists(p) else bgm_old
    if len(bgm_new) != len(bgm_old):
        return ["music: bgm.byml changed size"]
    loops = track_loops(fs)
    replaced = replaced_nodes(bgm_old, old_sl, slink_new)
    nodes_new = {(n["player"], n["node"]): n for n in asset_nodes(bgm_new)}
    for n, track in replaced:
        if not loops(track):
            continue
        m = nodes_new[(n["player"], n["node"])]
        fixed = not (m["auto"] and m["auto"][1]) and not (m["infinite"] and m["infinite"][1])
        if fixed or (m["duration"] and not (m["infinite"] and m["infinite"][1]) and m["duration"][1] < LONG):
            problems.append(f"music: {n['player']} node {n['node'][:8]} ({n['key']}) plays {track} for a fixed "
                            f"{m['duration'][1] if m['duration'] else '?'} s: it would be cut and restarted")
        if m["offset"] and m["offset"][1] != 0.0:
            problems.append(f"music: {n['player']} node {n['node'][:8]} ({n['key']}) starts {track} at "
                            f"{m['offset'][1]:.2f} s")
    if apply(bgm_old, loop_edits(bgm_old, old_sl, slink_new, loops)) != bgm_new:
        problems.append("music: bgm.byml in the patch differs from the edits its sound links call for")
    for kind, slots in sorted((music_log or {}).items()):
        for slot, track in sorted(slots.items()):
            got = loops(track)
            if got is None:
                problems.append(f"music: {kind} {slot} plays {track}, which isn't a BGM_Static track")
            elif kind in ("area", "event") and not got:
                problems.append(f"music: {kind} slot {slot} plays {track}, which doesn't loop")
            elif kind == "jingle" and got:
                problems.append(f"music: jingle {slot} plays {track}, a looping track (it would never end)")
    root = byml_load(bgm_new, allow_big=True)[0]
    by_player = {}
    for n, _track in replaced:
        by_player.setdefault(n["player"], set()).add(n["key"])
    for player, keys in sorted(by_player.items()):
        for fork, branches in _fork_branches(root["BGM"][player].get("Node", [])).items():
            playing = [b & keys for b in branches if b & keys]
            if len(playing) > 1:
                problems.append(f"music: {player} fork {fork[:8]} plays a new track on {len(playing)} branches at "
                                f"once ({sorted(set().union(*playing))})")
    return problems
