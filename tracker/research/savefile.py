"""Reads the OoT remake's save files (Longshot: <user>/save/<account>/slot_NN/progress.sav) for auto-tracking.

Format (same GameData engine as TotK, little-endian):
  0x00 u32 magic 0x01020304, 0x04 u32 version (0x002D80EB), 0x08 u32 offset of the value area, 0x0C..0x1F zero
  0x20 entries of 8 bytes (u32 key, u32 value) up to the value area. An entry with key 0 starts a type section; its
       value is the type index:
         0 Bool  1 BoolArray  2 Int  3 IntArray  4 Float  5 FloatArray  6 Enum  7 EnumArray  8 Vector2
         9 Vector2Array  10 Vector3  11 Vector3Array  12 String16  13 String16Array  14 String32  15 String32Array
         16 String64  17 String64Array  18 Binary  19 BinaryArray  20 UInt  21 UIntArray  22 Int64  23 Int64Array
         24 UInt64  25 UInt64Array  26 WString16  27 WString16Array  28 WString32  29 WString32Array  30 WString64
         31 WString64Array  32 Bool64bitKey
       Keys are murmur3_32 of the GameData name (romtools.murmur3_32). Bool/Int/UInt/Float/Enum hold the value
       inline; the others hold an offset into the value area (arrays: u32 count, then the elements).
  Type 32 (Bool64bitKey) has one entry whose value is the offset of a list of u64 keys that are TRUE, ending at a
  0 key. The list's length changes with play, and so does the file size. The keys are placement Hashes from the
  level files (Banc/*.bcett.byml.zs), so the flag of a pot, a rock or a Gold Skulltula is its placement Hash. A
  dropper also sets Hash ^ 2 when its drop is picked up. Chests aren't in it, an opened chest is the Bool
  IsTreasureBoxOpen.<its Hash> (s.bool(...), tools/rando/chest_flags.py).

The game writes it when it saves (autosave on area changes). Longshot writes the file in place, so read the whole
file and retry if the header looks wrong, since that's a read during a write.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))

SAVE_ROOT = "E:/LongshotLauncher-data/user/save"
MAGIC = 0x01020304
INLINE = {0: "Bool", 2: "Int", 4: "Float", 6: "Enum", 20: "UInt"}


class Save:
    def __init__(self, data):
        if len(data) < 0x28 or struct.unpack_from("<I", data, 0)[0] != MAGIC:
            raise ValueError("not a GameData save (or caught mid-write)")
        self.data = data
        self.value_off = struct.unpack_from("<I", data, 8)[0]
        self.sections = {}
        cur = None
        for p in range(0x20, self.value_off, 8):
            k, v = struct.unpack_from("<II", data, p)
            if k == 0:
                cur = v
                self.sections[cur] = {}
            else:
                self.sections[cur][k] = v
        self.bool64 = self._bool64()

    def _bool64(self):
        sec = self.sections.get(32) or {}
        keys = set()
        for _k, off in sec.items():
            p = off
            while p + 8 <= len(self.data):
                key = struct.unpack_from("<Q", self.data, p)[0]
                if key == 0:
                    break
                keys.add(key)
                p += 8
        return keys

    # Lookups by name
    def _key(self, name):
        import romtools
        return romtools.murmur3_32(name)

    def bool(self, name):
        v = self.sections.get(0, {}).get(self._key(name))
        return None if v is None else bool(v)

    def int(self, name):
        v = self.sections.get(2, {}).get(self._key(name))
        return None if v is None else struct.unpack("<i", struct.pack("<I", v))[0]

    def uint(self, name):
        return self.sections.get(20, {}).get(self._key(name))

    def int_array(self, name):
        off = self.sections.get(3, {}).get(self._key(name))
        if off is None:
            return None
        n = struct.unpack_from("<I", self.data, off)[0]
        return list(struct.unpack_from(f"<{n}i", self.data, off + 4))

    def string64(self, name):
        off = self.sections.get(16, {}).get(self._key(name))
        if off is None:
            return None
        raw = self.data[off:off + 64]
        return raw.split(b"\0", 1)[0].decode("utf-8", "replace")

    def vector3(self, name):
        off = self.sections.get(10, {}).get(self._key(name))
        return None if off is None else struct.unpack_from("<3f", self.data, off)

    def enum(self, name):
        """murmur3 of the enum value's name (compare with romtools.murmur3_32("Value"))."""
        return self.sections.get(6, {}).get(self._key(name))

    def pouch(self, actor):
        """Stock count of a pouch item (PouchData.<actor>.StockNum), the numbers Longshot's inventory probe prints."""
        return self.int(f"PouchData.{actor}.StockNum")

    def placement_done(self, placement_hash):
        """True when a placement's Bool64bitKey flag is set (pot broken, token taken...). A chest never sets it, its
        "opened" is self.bool(f"IsTreasureBoxOpen.{hash}")."""
        return int(placement_hash) in self.bool64

    def true_bools(self):
        return {k for k, v in self.sections.get(0, {}).items() if v}


def load(path):
    for _ in range(3):
        try:
            return Save(open(path, "rb").read())
        except (ValueError, struct.error):
            import time
            time.sleep(0.2)
    raise ValueError(f"{path}: unreadable save")


def slots(root=SAVE_ROOT):
    """[(path, mtime)] of every progress.sav, newest first."""
    out = []
    for acc in os.listdir(root):
        d = os.path.join(root, acc)
        if not os.path.isdir(d):
            continue
        for s in os.listdir(d):
            p = os.path.join(d, s, "progress.sav")
            if os.path.exists(p):
                out.append((p, os.path.getmtime(p)))
    return sorted(out, key=lambda x: -x[1])


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else slots()[0][0]
    s = load(path)
    print(path)
    print({k: len(v) for k, v in s.sections.items() if v})
    print("true bools:", len(s.true_bools()), " set Bool64bitKey keys:", len(s.bool64))
    for n in sys.argv[2:]:
        print(n, "bool", s.bool(n), "int", s.int(n), "uint", s.uint(n))
