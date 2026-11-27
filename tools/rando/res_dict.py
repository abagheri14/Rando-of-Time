"""The name dictionaries in the game's BFRES 10 models and BNTX textures (nn::util::ResDic), and how a renamed copy
keeps them working.

A dictionary is a Patricia tree over its keys' bits: u32 magic ("_DIC" in BNTX, 0 in BFRES 10), s32 count, then
count + 1 nodes of 16 bytes (s32 reference bit, u16 left, u16 right, u64 offset of the key: a pooled string, u16
length + bytes). Node 0 is the root (reference -1, empty key). A lookup walks from the root's left child, taking each
node's right child when the key has that node's reference bit set, while the reference bits grow; it finds the key
only if the node it stops on holds it. Bit r of a key is bit (r & 7) of its character (r >> 3) counted from the END
(0 past its length).

So a same-length rename of a key (make_patch "rename") keeps every byte valid but can leave its node's reference
bit pointing the wrong way, and then the game can't find that model by its name. That happened with
test_guardroom3. The song notes' and the upright Master Sword's models were renamed copies whose model dictionary
still had the donor's bits: Item_Arrow_Fire (ends in "e", bit 0 set) became Rando_Song_Zeld (ends in "d", bit 0
clear), and Weapon_Sword_Master became Rando_MasterSwordUp. The lookup by FmdbName missed, the actor got no model
(nothing on the ground) and the hold-up crashed on its empty ShowItem slot. edits() rebuilds the tree for the new
keys and problems() reads it back.
"""
import struct


def key_at(d, ptr):
    n = struct.unpack_from("<H", d, ptr)[0]
    return bytes(d[ptr + 2:ptr + 2 + n])


def bit(key, ref):
    """Bit `ref` of `key` as the lookup reads it (character from the end, LSB first; 0 past the key)."""
    ci = ref >> 3
    if ref < 0 or ci >= len(key):
        return 0
    return (key[len(key) - 1 - ci] >> (ref & 7)) & 1


# Where a dictionary can start (4-aligned). That's the word "_DIC" (BNTX), or a zero word with the root node's
# reference -1 two words on (BFRES 10).
_DIC_WORD = int.from_bytes(b"_DIC", "little")
_NODE = struct.Struct("<iHHQ")  # a node: reference, left, right, key offset


def dictionaries(d):
    """[(offset, [(reference, left, right, key offset) for node 0..count])] of every dictionary in `d`. Those are the
    4-aligned offsets o (o + 12 <= len(d)) holding a dictionary head, read in order, with the scan going on after
    each dictionary's last node. It's the same result as stepping o by 4 from 0, but numpy finds the heads on every
    word at once."""
    import numpy as np
    out, pos = [], 0
    hay = d if isinstance(d, (bytes, bytearray)) else bytes(d)
    n = (len(hay) - 12) // 4 + 1  # the words a head can start at
    if n <= 0:
        return out
    w = np.frombuffer(hay, dtype="<u4", count=n + 2)
    heads = np.flatnonzero((w[:n] == _DIC_WORD) | ((w[:n] == 0) & (w[2:] == 0xFFFFFFFF))) * 4
    for o in heads.tolist():
        if o < pos:
            continue
        count = struct.unpack_from("<i", d, o + 4)[0]
        end = o + 8 + 16 * (count + 1)
        if 0 < count < 65535 and end <= len(d):
            nodes = list(_NODE.iter_unpack(hay[o + 8:end]))
            if nodes[0][0] == -1 and all(n[1] <= count and n[2] <= count and n[3] + 2 <= len(d) for n in nodes):
                out.append((o, nodes))
                pos = end
    return out


def find(d, nodes, key):
    """The node index the game's lookup reaches for `key`, or -1."""
    prev, cur = 0, nodes[0][1]
    for _ in range(len(nodes) + 1):
        if not nodes[prev][0] < nodes[cur][0]:
            break
        prev, cur = cur, (nodes[cur][2] if bit(key, nodes[cur][0]) else nodes[cur][1])
    return cur if cur and key_at(d, nodes[cur][3]) == key else -1


def _first_diff(a, b):
    for r in range(max(len(a), len(b)) * 8):
        if bit(a, r) != bit(b, r):
            return r
    return None


def tree(keys):
    """[(reference, left, right)] for node 0..len(keys): the tree inserting `keys` in order (node i holds keys[i-1])."""
    nodes = [[-1, 0, 0]]
    for i, key in enumerate(keys, 1):
        prev, cur = 0, nodes[0][1]
        while nodes[prev][0] < nodes[cur][0]:
            prev, cur = cur, (nodes[cur][2] if bit(key, nodes[cur][0]) else nodes[cur][1])
        ref = _first_diff(key, keys[cur - 1] if cur else b"")
        if ref is None:
            raise ValueError(f"key {key!r} twice in one dictionary")
        prev, cur = 0, nodes[0][1]
        while nodes[prev][0] < nodes[cur][0] < ref:
            prev, cur = cur, (nodes[cur][2] if bit(key, nodes[cur][0]) else nodes[cur][1])
        nodes.append([ref, cur, i] if bit(key, ref) else [ref, i, cur])
        if prev == 0 or not bit(key, nodes[prev][0]):
            nodes[prev][1] = i
        else:
            nodes[prev][2] = i
    return [tuple(n) for n in nodes]


def edits(src, renames):
    """Byte edits ([{"offset", "expect", "bytes"}], make_patch "bytes") that give every dictionary of `src` whose keys
    the same-length `renames` change ([old, new] names, make_patch "rename") the tree of its new keys. Only the
    nodes' reference bits and links change, the keys' offsets stay."""
    names = {old.encode(): new.encode() for old, new in renames}
    out = []
    for o, nodes in dictionaries(src):
        keys = [key_at(src, n[3]) for n in nodes[1:]]
        new = [names.get(k, k) for k in keys]
        if new == keys:
            continue
        for i, (ref, left, right) in enumerate(tree(new)):
            at = o + 8 + 16 * i
            old, now = bytes(src[at:at + 8]), struct.pack("<iHH", ref, left, right)
            if old != now:
                out.append({"offset": at, "expect": old.hex(), "bytes": now.hex()})
    return out


def problems(d, label=""):
    """Keys their own dictionary can't find (by the game's lookup), as text."""
    bad = []
    for o, nodes in dictionaries(d):
        for i in range(1, len(nodes)):
            k = key_at(d, nodes[i][3])
            if find(d, nodes, k) != i:
                bad.append(f"{label}{': ' if label else ''}the dictionary at {o:#x} can't find "
                           f"{k.decode('latin1')!r} by name (reference bit {nodes[i][0]})")
    return bad


def has(d, key, offset=None):
    """Whether the dictionary at `offset` (default: any) finds `key` (a str)."""
    k = key.encode()
    return any(find(d, nodes, k) > 0 for o, nodes in dictionaries(d) if offset is None or o == offset)
