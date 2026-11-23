"""The remake's save (slot_NN/progress.sav), read the way the tracker reads it (tracker/app/SaveFile.cs).

GameData format, little-endian: 0x00 u32 magic 0x01020304, 0x08 u32 offset of the value area, then 8-byte entries
(u32 key, u32 value) from 0x20 up to the value area. An entry with key 0 starts a type section and its value is the
type index. Bool 0, BoolArray 1, Int 2, Float 4, Enum 6 and UInt 20 hold their value inline. Arrays hold an offset
into the value area (u32 count, then the elements), and a bool array's elements are bits packed in u32 words, lowest
bit first. Bool64bitKey 32 is one entry whose value is the offset of a 0-ended list of the u64 keys that are TRUE.
Those are placement hashes, like a chest opened, a pot broken, a token taken... Keys of the other types are
murmur3_32 of the GameData name.

Read-only. The game rewrites the file in place, so a read is taken twice and has to match (OotrR's save_reader does
the same) or it's retried. A broken read never turns into an empty (fresh) game.
"""
import os
import struct
import time

MAGIC = 0x01020304
MAX_SAVE = 16 << 20
SAVE_NAME = 'progress.sav'


def murmur3(data, seed=0):
    """MurmurHash3 x86 32-bit: the GameData key of a flag name."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    c1, c2, h, n = 0xCC9E2D51, 0x1B873593, seed & 0xFFFFFFFF, len(data)
    for i in range(0, n - n % 4, 4):
        k = int.from_bytes(data[i:i + 4], 'little')
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[n - n % 4:]
    if tail:
        k = 0
        for j, b in enumerate(tail):
            k |= b << (8 * j)
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


class SaveError(ValueError):
    """Not a save, or caught while the game writes it."""


class SaveFile:
    """One decoded progress.sav. ``bool(name)``, ``int(name)``, ``bit(array, i)``, ``has64(hash)``."""

    def __init__(self, data, path='', written=0.0):
        if len(data) < 0x28 or struct.unpack_from('<I', data, 0)[0] != MAGIC:
            raise SaveError('not a save (or caught mid-write)')
        value_off = struct.unpack_from('<I', data, 8)[0]
        if value_off <= 0x20 or value_off > len(data):
            raise SaveError('bad value-area offset')
        self.data, self.path, self.written = data, path, written
        self.sections = {}
        current = None
        for p in range(0x20, value_off - 7, 8):
            key, value = struct.unpack_from('<II', data, p)
            if key == 0:
                current = self.sections.setdefault(value, {})
            elif current is not None:
                current[key] = value
        self.bool64 = set()
        for offset in (self.sections.get(32) or {}).values():
            p = offset
            while p + 8 <= len(data):
                key = struct.unpack_from('<Q', data, p)[0]
                if key == 0:
                    break
                self.bool64.add(key)
                p += 8

    def _inline(self, kind, name):
        key = name if isinstance(name, int) else murmur3(name)
        return (self.sections.get(kind) or {}).get(key)

    def bool(self, name):
        value = self._inline(0, name)
        return None if value is None else value != 0

    def int(self, name):
        value = self._inline(2, name)
        return None if value is None else struct.unpack('<i', struct.pack('<I', value))[0]

    def uint(self, name):
        return self._inline(20, name)

    def enum(self, name):
        """An Enum's value: the murmur3 of its value name (Step_Defeat_Ganon = murmur3('Complete') once won)."""
        return self._inline(6, name)

    def bit(self, name, index):
        """Element ``index`` of a saved bool array, or None when the array isn't in this save."""
        offset = self._inline(1, name)
        if offset is None or offset + 4 > len(self.data):
            return None
        count = struct.unpack_from('<I', self.data, offset)[0]
        if not 0 <= index < count:
            return None
        word = offset + 4 + 4 * (index // 32)
        if word + 4 > len(self.data):
            return None
        return bool((struct.unpack_from('<I', self.data, word)[0] >> (index % 32)) & 1)

    def has64(self, key):
        return int(key) in self.bool64

    def bools(self):
        """{hash: bool} of every saved Bool (the same shape a live memory snapshot gives)."""
        return {key: value != 0 for key, value in (self.sections.get(0) or {}).items()}


def _read_once(path):
    with open(path, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_SAVE:
            raise SaveError('save too large')
        data = stream.read(MAX_SAVE + 1)
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(data) != after.st_size:
        raise SaveError('save being written')
    return data, after


def load(path, attempts=4):
    """A consistent SaveFile (two equal reads), retrying briefly while the game writes it."""
    last = None
    for attempt in range(attempts):
        try:
            first, stat1 = _read_once(path)
            second, stat2 = _read_once(path)
            if first != second or stat1.st_mtime_ns != stat2.st_mtime_ns:
                raise SaveError('save being written')
            return SaveFile(second, path=str(path), written=stat2.st_mtime)
        except (SaveError, OSError) as error:
            last = error
            if attempt < attempts - 1:
                time.sleep(0.15)
    raise SaveError(f'{path}: unreadable save ({last})')


def find_saves(root, slot=None):
    """Every progress.sav under ``root`` (Longshot: user/save/<account>/slot_NN), newest first.

    ``slot``: only that slot folder (slot_00...). Emulators keep the same slot_NN layout under their own save folder.
    """
    found = []
    if not root or not os.path.isdir(root):
        return found
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if SAVE_NAME in files:
            if slot and os.path.basename(folder).lower() != slot.lower():
                continue
            path = os.path.join(folder, SAVE_NAME)
            try:
                found.append((os.path.getmtime(path), path))
            except OSError:
                continue
    return [path for _, path in sorted(found, reverse=True)]


class SaveWatcher:
    """The newest progress.sav (or a chosen slot's), re-read only when the game wrote it."""

    def __init__(self, root='', slot=None, path=''):
        self.root, self.slot, self.path = root, slot, path
        self.current, self.stamp, self.error = None, None, ''
        self._next_scan, self._found = 0.0, None

    def target(self):
        if self.path:
            return self.path
        now = time.monotonic()
        if self._found is None or now >= self._next_scan:
            saves = find_saves(self.root, self.slot)
            self._found = saves[0] if saves else ''
            self._next_scan = now + 2.0
        return self._found

    def poll(self):
        """(SaveFile, changed): the latest good read; ``changed`` when it is new since the last call."""
        path = self.target()
        if not path:
            self.error = 'no save found' + (f' in {self.root}' if self.root else '')
            return self.current, False
        try:
            stat = os.stat(path)
        except OSError as error:
            self.error = str(error)
            return self.current, False
        stamp = (path, stat.st_size, stat.st_mtime_ns)
        if stamp == self.stamp and self.current is not None:
            return self.current, False
        try:
            save = load(path)
        except SaveError as error:
            self.error = str(error)
            return self.current, False
        self.current, self.stamp, self.error = save, stamp, ''
        return save, True
