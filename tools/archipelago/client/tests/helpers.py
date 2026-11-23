"""Test helpers: a synthetic progress.sav, a seed folder, and a simulated game behind the mailbox."""
import json
import os
import struct

from client import delivery as D
from client.savefile import murmur3


def make_save(bools=None, ints=None, enums=None, arrays=None, bool64=()):
    """progress.sav bytes in the game's GameData layout (savefile.py's docstring)."""
    sections = {0: {}, 1: {}, 2: {}, 6: {}, 32: {}}
    for name, value in (bools or {}).items():
        sections[0][murmur3(name)] = int(bool(value))
    for name, value in (ints or {}).items():
        sections[2][murmur3(name)] = value & 0xFFFFFFFF
    for name, value in (enums or {}).items():
        sections[6][murmur3(name)] = murmur3(value)
    order = sorted(sections)
    entries = sum(len(v) + 1 for v in sections.values()) + len(arrays or {}) + 1  # Count array entries and the Bool64 entry too.
    value_off = 0x20 + entries * 8
    values = bytearray()
    array_offsets = {}
    for name, flags in (arrays or {}).items():
        array_offsets[name] = value_off + len(values)
        words = [0] * ((len(flags) + 31) // 32)
        for i, flag in enumerate(flags):
            if flag:
                words[i // 32] |= 1 << (i % 32)
        values += struct.pack('<I', len(flags)) + b''.join(struct.pack('<I', w) for w in words)
    for name, offset in array_offsets.items():
        sections[1][murmur3(name)] = offset
    sections[32][0xA3DB7114] = value_off + len(values)
    for key in sorted(bool64):
        values += struct.pack('<Q', key)
    values += struct.pack('<Q', 0)
    out = bytearray(struct.pack('<III', 0x01020304, 0x002D80EB, value_off) + bytes(20))
    for kind in order:
        out += struct.pack('<II', 0, kind)
        for key, value in sections[kind].items():
            out += struct.pack('<II', key, value)
    assert len(out) == value_off
    return bytes(out + values)


def write_seed(folder, locations, checks, seed='12345', seed_key='K3yK3yK3y', slot_name='Alice', foreign=None,
               plan=None, tracker_seed='12345'):
    """A seed folder as build_patch writes it: ap.json, tracker.json (and plan.json)."""
    os.makedirs(folder, exist_ok=True)
    ap = {'format': 1, 'game': 'Rando of Time', 'mailbox_version': 1, 'seed_name': 'fake-seed',
          'seed': seed, 'slot': 1, 'slot_name': slot_name, 'team': 0, 'locations': locations,
          'foreign': foreign or {}, 'start_inventory': {}}
    if seed_key is not None:
        ap['seed_key'] = seed_key
    with open(os.path.join(folder, 'ap.json'), 'w', encoding='utf-8') as stream:
        json.dump(ap, stream)
    with open(os.path.join(folder, 'tracker.json'), 'w', encoding='utf-8') as stream:
        json.dump({'format': 1, 'seed': tracker_seed, 'checks': checks, 'maps': [], 'items': []}, stream)
    if plan is not None:
        with open(os.path.join(folder, 'plan.json'), 'w', encoding='utf-8') as stream:
            json.dump(plan, stream)


class FakeGame:
    """The running game behind the mailbox, as MAILBOX.md section 2 describes it. Every read is one game frame.
    A true Signal gets taken (cleared) unless the game is busy (``paused``). The event then gives the item when Idx
    matches Count's low bits, unless ``drop`` > 0, which is an event the game dropped (nothing given, nothing
    counted)."""

    def __init__(self, seed_key='K3yK3yK3y', marker=True, count=0, snapshot_bools=None, bool64=None):
        self.marker_name = f'RandoAP_Seed_{seed_key}'
        self.bools = {name: False for name in D.COUNT + D.CODE + D.IDX + [D.SIGNAL]}
        self.bools[self.marker_name] = marker
        self.set_count(count)
        self.given = []           # codes handed over, in order
        self.paused = False
        self.drop = 0
        self.writes = []
        self.reachable = True
        self.extra = dict(snapshot_bools or {})
        self.bool64 = dict(bool64 or {})

    def set_count(self, n):
        for name, value in D.bits(n, D.COUNT):
            self.bools[name] = value

    def count(self):
        return D.number(self.bools, D.COUNT)

    def frame(self):
        if not self.bools[D.SIGNAL] or self.paused:
            return
        self.bools[D.SIGNAL] = False
        if self.drop:
            self.drop -= 1
            return
        if D.number(self.bools, D.IDX) != self.count() & 15:
            return
        self.given.append(D.number(self.bools, D.CODE))
        self.set_count(self.count() + 1)

    def _check(self):
        if not self.reachable:
            from client.live_memory import LiveUnavailable
            raise LiveUnavailable('game not running')

    def read_bools(self, names):
        self._check()
        self.frame()
        return {name: self.bools.get(name) for name in names}

    def write_bools(self, pairs):
        self._check()
        for name, value in pairs:
            if name not in D.WRITTEN:
                raise PermissionError(name)
            self.bools[name] = bool(value)
            self.writes.append((name, bool(value)))

    def snapshot(self):
        self._check()
        out = {murmur3(name): value for name, value in self.bools.items()}
        out.update({murmur3(name): value for name, value in self.extra.items()})
        return {'bool': out, 'bool64': dict(self.bool64), 'bool64_complete': True}

    def describe(self):
        return 'fake.exe (port)'
