# Ported from OotrR (github.com/Mozencaz/OotrR, tests/test_live_memory.py).
# Copyright (c) 2026 Mozencaz. MIT License: see ../LICENSE-OotrR.txt.
"""live_memory over fake memory only: no game runs, and no real process is opened or read.

Ported from OotrR: the pure parts (parse_bools, parse_bool64, valid_slot, module_starts, emulator_layout), snapshots
with the Bool64bitKey offset scan, and the Linux parts over a fake /proc in a temporary folder. Added for the remake:
port_layout (Hookshot's fixed window, Longshot's 1:1 mapping, the MOD0 fallback, junk memory), read_keys / write_keys /
set_bool and their write allowlist, and the mailbox of data/archipelago/MAILBOX.md end to end against a simulated game.

Run from the project root:
  python -m unittest discover -s tools/archipelago/client/tests -t tools/archipelago -p "test_live_memory.py" -v
"""
import bisect
import os
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from client import delivery, live_memory, savefile
from client.live_memory import (BOOL64_PROBE, BOOL64_TYPE, EMULATOR_EXES, GAMEDATA_SLOT, GUEST_CODE, HOOKSHOT_MAIN,
                                HOST_BASE, MAX_BOOLS, MAX_MODULE, MAX_TABLE, MEM_COMMIT, PORT_BASES, PORT_EXES,
                                SEQUENCE_IS_CHILDHOOD, LinuxProcessMemory, LiveGameData, LiveUnavailable,
                                MemfdWindows, bool_slot, denied_message, emulator_layout, exe_link_name,
                                is_guest_memfd, linux_pids, memfd_mappings, module_starts, names_match, parse_bool64,
                                parse_bools, parse_exe_names, parse_maps, plain_name, port_layout, ptrace_scope,
                                readable_regions, valid_slot)

murmur3 = savefile.murmur3

# Guest addresses of gamedata_image(at=AT): pointers there pass valid_slot's range check (>= 0x10000).
AT = 0x90000000
HOLDER, MANAGER, TABLE, ENTRIES, RECORDS = (AT + offset for offset in (0x1000, 0x2000, 0x3000, 0x5000, 0x8000))
SLOT_OFFSET = GAMEDATA_SLOT - HOOKSHOT_MAIN    # the slot's offset in the main module
MAIN_MOD0 = 0x3C4705C                          # main's MOD0, past its first page (Longshot's image.bin)
RTLD_MOD0 = 0x301C


def gamedata_image(bools, size=16, gamedata_slot=GAMEDATA_SLOT, at=0, bool64=None, bool64_at=BOOL64_TYPE):
    """Guest memory as Hookshot lays out GameDataMgr: {guest address: bytes}.

    ``bool64``: {key: value} of Bool64bitKey records, written in the given order at ``bool64_at``."""
    table = bytearray(size * 8)
    entries = bytearray(len(bools) * 24)
    for index, (key, value) in enumerate(bools.items()):
        slot = key % size
        while struct.unpack_from('<I', table, slot * 8)[0]:
            slot = (slot + 1) % size
        struct.pack_into('<II', table, slot * 8, key, index)
        entries[index * 24 + 22] = int(value)
    holder, manager, table_at, entries_at = (at + offset for offset in (0x1000, 0x2000, 0x3000, 0x5000))
    header = bytearray(48 if bool64 is None else 0xD10)
    struct.pack_into('<I', header, 16, len(bools))
    struct.pack_into('<Q', header, 24, entries_at)
    struct.pack_into('<Q', header, 32, table_at)
    struct.pack_into('<I', header, 44, size)
    image = {gamedata_slot: struct.pack('<Q', holder), holder: struct.pack('<Q', manager),
             manager: bytes(header), table_at: bytes(table), entries_at: bytes(entries)}
    if bool64 is not None:
        records_at = at + 0x8000
        records = b''.join(struct.pack('<QIB3x', key, 0, value) for key, value in bool64.items())
        struct.pack_into('<IIQ', header, bool64_at, len(bool64), 0, records_at)
        image[manager], image[records_at] = bytes(header), records
    return image


def value_byte(bools, key, at=AT):
    """Guest address of ``key``'s value byte in gamedata_image(bools, at=at)."""
    return at + 0x5000 + list(bools).index(key) * 24 + 22


class Space:
    """Sparse memory of the fakes: {address: bytearray}; regions never overlap."""

    def __init__(self, regions=None):
        self.regions, self.starts = {}, []
        for start, data in (regions or {}).items():
            self.add(start, data)

    def add(self, start, data):
        end = start + len(data)
        for other in self.starts:
            if other != start and other < end and start < other + len(self.regions[other]):
                raise AssertionError(f'test regions overlap at {start:#x} and {other:#x}')
        self.regions[start] = bytearray(data)
        self.starts = sorted(self.regions)

    def _find(self, address, size):
        index = bisect.bisect_right(self.starts, address) - 1
        if index < 0 or size < 0:
            return None
        start = self.starts[index]
        data = self.regions[start]
        return (start, data) if address + size <= start + len(data) else None

    def get(self, address, size):
        """bytes, or None when part of the range is not mapped (the ``read`` of the pure layout functions)."""
        found = self._find(address, size)
        if found is None:
            return None
        start, data = found
        return bytes(data[address - start:address - start + size])

    def put(self, address, data):
        found = self._find(address, len(data))
        if found is None:
            return False
        start, region = found
        region[address - start:address - start + len(data)] = data
        return True


class FakeMemory:
    """What LiveGameData uses of ProcessMemory: attach, read (LiveUnavailable when unmapped), write, close, and the
    attributes slot, base, image, kind. Guest addresses index ``space``; reads and writes are logged."""

    def __init__(self, regions, slot=GAMEDATA_SLOT, image='', kind='port'):
        self.space = regions if isinstance(regions, Space) else Space(regions)
        self.slot, self.base, self.image, self.kind = slot, HOST_BASE, image, kind
        self.reads, self.writes = [], []
        self.attached = self.closed = 0
        self.on_write = None   # called after each write (the end-to-end test runs a game frame there)

    def attach(self):
        self.attached += 1

    def close(self):
        self.closed += 1

    def read(self, guest, size):
        self.reads.append((guest, size))
        data = self.space.get(guest, size)
        if data is None:
            raise LiveUnavailable(f'cannot read at {guest:#x}')
        return data

    def write(self, guest, data):
        if not self.space.put(guest, bytes(data)):
            raise LiveUnavailable(f'cannot write at {guest:#x}')
        self.writes.append((guest, bytes(data)))
        if self.on_write:
            self.on_write()

    def reads_at(self, guest):
        return sum(1 for address, _ in self.reads if address == guest)


# Ported: snapshots
class LiveGameDataTests(unittest.TestCase):
    def test_reads_bools_through_the_hash_table(self):
        bools = {SEQUENCE_IS_CHILDHOOD: True, 17: False, 33: True}   # 17 and 33 collide (mod 16)
        snapshot = LiveGameData(FakeMemory(gamedata_image(bools))).snapshot()
        self.assertEqual(snapshot['bool'], bools)

    def test_rejects_a_table_without_known_keys(self):
        with self.assertRaises(LiveUnavailable):
            LiveGameData(FakeMemory(gamedata_image({5: True}))).snapshot()

    def test_not_loaded_yet(self):
        regions = gamedata_image({SEQUENCE_IS_CHILDHOOD: True})
        regions[0x1000] = struct.pack('<Q', 0)
        memory = FakeMemory(regions)
        with self.assertRaises(LiveUnavailable):
            LiveGameData(memory).snapshot()
        self.assertEqual(memory.closed, 1)

    def test_unexpected_structure(self):
        for field, value in ((44, 0), (44, MAX_TABLE + 1), (16, 0), (16, MAX_BOOLS + 1)):
            with self.subTest(field=field, value=value):
                regions = gamedata_image({SEQUENCE_IS_CHILDHOOD: True})
                header = bytearray(regions[0x2000])
                struct.pack_into('<I', header, field, value)
                regions[0x2000] = bytes(header)
                with self.assertRaises(LiveUnavailable) as caught:
                    LiveGameData(FakeMemory(regions)).snapshot()
                self.assertIn('unexpected GameData structure', str(caught.exception))

    def test_reads_bool64_flags(self):
        bool64 = {5: 1, BOOL64_PROBE - 1: 0, BOOL64_PROBE: 1, BOOL64_PROBE + 7: 1}
        snapshot = LiveGameData(FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, bool64=bool64))).snapshot()
        self.assertTrue(snapshot['bool64_complete'])
        self.assertEqual(snapshot['bool64'], {5: True, BOOL64_PROBE: True, BOOL64_PROBE + 7: True})

    def test_seed_keys_appended_after_the_sorted_ones(self):
        # A seed's GameData adds Bool64bitKey entries: the game appends them, unsorted.
        bool64 = {5: 0, BOOL64_PROBE: 0, BOOL64_PROBE + 9: 1, 7: 1, 3: 0, 6: 1}
        snapshot = LiveGameData(FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, bool64=bool64))).snapshot()
        self.assertTrue(snapshot['bool64_complete'])
        self.assertEqual(snapshot['bool64'], {BOOL64_PROBE + 9: True, 7: True, 6: True})

    def test_finds_bool64_flags_moved_in_the_manager(self):
        moved = BOOL64_TYPE + 0x30
        regions = gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, bool64={BOOL64_PROBE: 0, BOOL64_PROBE + 1: 1},
                                 bool64_at=moved)
        memory = FakeMemory(regions)
        data = LiveGameData(memory)
        self.assertEqual(data.snapshot()['bool64'], {BOOL64_PROBE + 1: True})
        # the offset found is tried first next time: the usual one isn't read again
        memory.reads.clear()
        self.assertEqual(data.snapshot()['bool64'], {BOOL64_PROBE + 1: True})
        self.assertEqual(memory.reads_at(0x2000 + BOOL64_TYPE), 0)
        self.assertEqual(memory.reads_at(0x2000 + moved), 1)

    def test_bool64_falls_back_to_the_save(self):
        cases = {'unreadable': None, 'no probe key': {1: 1, 2: 1},
                 'probe outside the sorted part': {5: 1, 2: 1, BOOL64_PROBE: 1}}
        for name, bool64 in cases.items():
            with self.subTest(name):
                snapshot = LiveGameData(FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True},
                                                                  bool64=bool64))).snapshot()
                self.assertTrue(snapshot['bool'][SEQUENCE_IS_CHILDHOOD])
                self.assertFalse(snapshot['bool64_complete'])
                self.assertEqual(snapshot['bool64'], {})   # ours keeps an empty dict (OotrR: no key)
                self.assertIn('Bool64bitKey', snapshot['bool64_status'])

    def test_parse_skips_out_of_range_indices(self):
        table = struct.pack('<IIII', 7, 0, 9, 5)
        self.assertEqual(parse_bools(table, bytes(24), 1), {7: False})

    def test_parse_reads_bit_0_only(self):
        entries = bytearray(48)
        entries[22], entries[24 + 22] = 0xFE, 0x81
        self.assertEqual(parse_bools(struct.pack('<IIII', 7, 0, 9, 1), bytes(entries), 2), {7: False, 9: True})

    def test_parse_bool64(self):
        records = lambda pairs: b''.join(struct.pack('<QIB3x', key, 0, value) for key, value in pairs)
        sorted_part = [(5, 1), (BOOL64_PROBE, 0), (BOOL64_PROBE + 3, 1)]
        self.assertEqual(parse_bool64(records(sorted_part), 3), {5: True, BOOL64_PROBE + 3: True})
        # a seed's keys appended after the sorted ones, in any order: still read, the probe still found
        appended = sorted_part + [(BOOL64_PROBE + 9, 1), (2, 1), (8, 0)]
        self.assertEqual(parse_bool64(records(appended), 6), {5: True, BOOL64_PROBE + 3: True,
                                                             BOOL64_PROBE + 9: True, 2: True})
        self.assertIsNone(parse_bool64(records([(1, 1), (2, 1)]), 2))
        self.assertIsNone(parse_bool64(records([(9, 1), (3, 1), (BOOL64_PROBE, 1)]), 3))   # probe only appended
        self.assertIsNone(parse_bool64(b'', 0))

    def test_bool_slot_probes_from_the_hash(self):
        # 3 and 19 share slot 3 (mod 16); 31 wraps to slot 0
        table = bytearray(16 * 8)
        for slot, key, index in ((3, 3, 0), (4, 19, 1), (15, 15, 2), (0, 31, 3)):
            struct.pack_into('<II', table, slot * 8, key, index)
        self.assertEqual(bool_slot(table, 16, 19), 1)
        self.assertEqual(bool_slot(table, 16, 31), 3)
        self.assertIsNone(bool_slot(table, 16, 35))   # slot 3, 4 taken, 5 empty
        full = b''.join(struct.pack('<II', key + 1, 0) for key in range(4))
        self.assertIsNone(bool_slot(full, 4, 99))     # a full table without the key ends

    def test_describe_names_the_attached_game(self):
        memory = FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True}), image='C:\\Games\\Longshot\\longshot.exe')
        self.assertEqual(LiveGameData(memory).describe(), 'longshot.exe (port)')
        memory.image = ''
        self.assertEqual(LiveGameData(memory).describe(), '')


# Ported: layouts
def emulator_process(base, main, bools=None, loaded=True):
    """Host memory of an emulator: guest memory at ``base``, rtld then main (``main``) with their MOD0 headers, and
    decoy regions module_starts has to refuse. Returns (listing, read, guest slot)."""
    slot = main + SLOT_OFFSET
    guest = gamedata_image(bools or {SEQUENCE_IS_CHILDHOOD: True, 17: False}, gamedata_slot=slot, at=AT)
    if not loaded:
        guest[slot] = struct.pack('<Q', 0)
    space = Space({base + address: data for address, data in guest.items()})
    rtld = main - 0x20000
    rtld_head = bytearray(0x4000)
    struct.pack_into('<II', rtld_head, 0, 0, RTLD_MOD0)
    rtld_head[RTLD_MOD0:RTLD_MOD0 + 4] = b'MOD0'
    space.add(base + rtld, rtld_head)
    space.add(base + main, struct.pack('<II', 1, MAIN_MOD0) + bytes(0x1000 - 8))
    space.add(base + main + MAIN_MOD0, b'MOD0')
    listing = [(base + rtld, 0x4000, MEM_COMMIT), (base + main, 0x1000, MEM_COMMIT),
               (base + AT, 0x10000, MEM_COMMIT), (base + (slot & ~0xFFF), 0x1000, MEM_COMMIT)]
    decoys = base + 0xA0000000
    for index, (head, size, state) in enumerate((
            (struct.pack('<II', 0, 0x40), 0x1000, 0x2000),          # reserved, not committed
            (struct.pack('<II', 0, 0x40), 0x800, MEM_COMMIT),       # smaller than a page
            (struct.pack('<II', 0, 0x41), 0x1000, MEM_COMMIT),      # MOD0 offset not aligned
            (struct.pack('<II', 0, 0x40), 0x1000, MEM_COMMIT),      # another magic
            (struct.pack('<II', 0, MAX_MODULE), 0x1000, MEM_COMMIT),   # offset too far
            (struct.pack('<II', 0, 4), 0x1000, MEM_COMMIT))):       # offset inside the header
        address = decoys + index * 0x10000
        page = bytearray(size)
        page[:8] = head
        page[0x40:0x44] = b'MOD1' if index == 3 else b'MOD0'
        page[0x41:0x45] = b'MOD0' if index == 2 else page[0x41:0x45]
        space.add(address, page)
        listing.append((address, size, state))
    listing.append((decoys + 0x100000, 0x1000, MEM_COMMIT))   # listed but unreadable
    return sorted(listing), space.get, slot


class EmulatorLayoutTests(unittest.TestCase):
    """An emulator maps guest memory at a random host base and loads main at a random page."""
    BASE, MAIN = 0x5A3400000000, 0x80347000

    def test_module_starts_keep_committed_mod0_regions_only(self):
        listing, read, _ = emulator_process(self.BASE, self.MAIN)
        self.assertEqual(module_starts(listing, read), [self.BASE + self.MAIN - 0x20000, self.BASE + self.MAIN])

    def test_finds_base_and_slot(self):
        listing, read, slot = emulator_process(self.BASE, self.MAIN)
        self.assertEqual(emulator_layout(listing, read), (self.BASE, slot))

    def test_finds_base_and_slot_at_random_places(self):
        rng = random.Random(0x0075AB)
        for _ in range(4):
            base, main = rng.randrange(0x10, 0x7F00) << 32, rng.choice(GUEST_CODE[0x20:])
            with self.subTest(base=hex(base), main=hex(main)):
                listing, read, slot = emulator_process(base, main)
                self.assertEqual(emulator_layout(listing, read), (base, main + SLOT_OFFSET))

    def test_game_data_not_loaded(self):
        listing, read, _ = emulator_process(self.BASE, self.MAIN, loaded=False)
        self.assertIsNone(emulator_layout(listing, read))

    def test_another_game_s_data_is_not_taken(self):
        listing, read, _ = emulator_process(self.BASE, self.MAIN, bools={5: True, 17: False})
        self.assertIsNone(emulator_layout(listing, read))

    def test_finds_base_and_slot_from_linux_maps(self):
        # Ryuchii on Linux: guest pages are mappings of its memfd inside one reserved window.
        listing, read, slot = emulator_process(self.BASE, self.MAIN)
        lines = [f'{self.BASE:x}-{self.BASE + self.MAIN - 0x20000:x} ---p 00000000 00:00 0']
        lines += [f'{start:x}-{start + size:x} rw-s 00012000 00:01 4321    /memfd:HostMemory (deleted)'
                  for start, size, state in listing if state == MEM_COMMIT]
        self.assertEqual(emulator_layout(readable_regions(parse_maps('\n'.join(lines))), read), (self.BASE, slot))


class ValidSlotTests(unittest.TestCase):
    """valid_slot proves a layout: only a GameData table that knows Sequence_IsChildhood passes."""

    def image(self, bools=None, header=None, **changes):
        regions = gamedata_image(bools or {SEQUENCE_IS_CHILDHOOD: True, 17: False}, at=AT)
        if header:
            data = bytearray(regions[MANAGER])
            for offset, (form, value) in header.items():
                struct.pack_into(form, data, offset, value)
            regions[MANAGER] = bytes(data)
        regions.update(changes.get('regions', {}))
        return Space(regions).get

    def test_a_game_data_table(self):
        self.assertTrue(valid_slot(self.image(), GAMEDATA_SLOT))

    def test_refuses_what_is_not_one(self):
        cases = {
            'slot unmapped': Space().get,
            'holder null': self.image(regions={GAMEDATA_SLOT: struct.pack('<Q', 0)}),
            'holder not aligned': self.image(regions={GAMEDATA_SLOT: struct.pack('<Q', HOLDER + 4)}),
            'holder too low': Space(gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, at=0)).get,
            'holder past 48 bits': self.image(regions={GAMEDATA_SLOT: struct.pack('<Q', 1 << 48)}),
            'manager null': self.image(regions={HOLDER: struct.pack('<Q', 0)}),
            'header unreadable': self.image(regions={MANAGER: bytes(40)}),
            'table size 0': self.image(header={44: ('<I', 0)}),
            'table too big': self.image(header={44: ('<I', MAX_TABLE + 1)}),
            'no Bools': self.image(header={16: ('<I', 0)}),
            'too many Bools': self.image(header={16: ('<I', MAX_BOOLS + 1)}),
            'table null': self.image(header={32: ('<Q', 0)}),
            'entries null': self.image(header={24: ('<Q', 0)}),
            'table unreadable': self.image(header={44: ('<I', 4096)}),
            'key unknown': self.image(bools={5: True, 17: False}),
            'index past the Bools': self.image(bools={17: False, SEQUENCE_IS_CHILDHOOD: True},
                                               header={16: ('<I', 1)}),
        }
        for name, read in cases.items():
            with self.subTest(name):
                self.assertFalse(valid_slot(read, GAMEDATA_SLOT))

    def test_random_garbage_never_passes(self):
        rng = random.Random(0x5107)
        for _ in range(200):
            space, listing = Space(), []
            plant_junk(space, listing, rng, 0, GAMEDATA_SLOT)
            self.assertFalse(valid_slot(space.get, GAMEDATA_SLOT))


def plant_junk(space, listing, rng, base, slot):
    """Host memory where guest ``slot`` (at ``base``) leads to well-formed pointers and a sane-looking header, but
    random bytes for the table (half the time the vanilla key is there, with an index past the Bools)."""
    page = base + (slot & ~0xFFF)
    block = bytearray(rng.randbytes(0x1000))
    data = bytearray(rng.randbytes(0x20000))
    holder, manager = AT + rng.randrange(0, 0x1000, 8), AT + 0x1000 + rng.randrange(0, 0x1000, 8)
    size, count = rng.randrange(1, 0x2000), rng.randrange(1, 0x400)
    struct.pack_into('<Q', block, slot & 0xFFF, holder)
    struct.pack_into('<Q', data, holder - AT, manager)
    struct.pack_into('<I', data, manager - AT + 16, count)
    struct.pack_into('<QQ', data, manager - AT + 24, AT + 0x14000, AT + 0x4000)   # entries, table
    struct.pack_into('<I', data, manager - AT + 44, size)
    if rng.random() < 0.5:
        struct.pack_into('<II', data, 0x4000 + SEQUENCE_IS_CHILDHOOD % size * 8, SEQUENCE_IS_CHILDHOOD,
                         count + rng.randrange(1000))
    space.add(page, block)
    space.add(base + AT, data)
    listing += [(page, 0x1000, MEM_COMMIT), (base + AT, 0x20000, MEM_COMMIT)]


class PortLayoutTests(unittest.TestCase):
    """Longshot/Hookshot: Hookshot's fixed window, then guest memory mapped 1:1 (Longshot's log), then the MOD0 scan."""

    class Regions:
        """The process's regions, listed only when asked (a VirtualQueryEx walk)."""
        def __init__(self, listing=()):
            self.listing, self.calls = list(listing), 0

        def __call__(self):
            self.calls += 1
            return self.listing

    def port_space(self, *bases, bools=None):
        space = Space()
        for base in bases:
            for address, data in gamedata_image(bools or {SEQUENCE_IS_CHILDHOOD: True, 17: False}, at=AT).items():
                space.add(base + address, data)
        return space

    def test_hookshot_window(self):
        regions = self.Regions()
        self.assertEqual(port_layout(self.port_space(HOST_BASE).get, regions), (HOST_BASE, GAMEDATA_SLOT))
        self.assertEqual(regions.calls, 0)

    def test_guest_memory_mapped_one_to_one(self):
        regions = self.Regions()
        self.assertEqual(port_layout(self.port_space(0).get, regions), (0, GAMEDATA_SLOT))
        self.assertEqual(regions.calls, 0)

    def test_order_window_then_one_to_one(self):
        self.assertEqual(PORT_BASES, (HOST_BASE, 0))
        self.assertEqual(port_layout(self.port_space(HOST_BASE, 0).get), (HOST_BASE, GAMEDATA_SLOT))
        # the window holds something else (no vanilla key): the 1:1 mapping is taken
        space = self.port_space(HOST_BASE, bools={5: True, 17: False})
        for address, data in gamedata_image({SEQUENCE_IS_CHILDHOOD: True}, at=AT).items():
            space.add(address, data)
        self.assertEqual(port_layout(space.get), (0, GAMEDATA_SLOT))

    def test_falls_back_to_the_mod0_scan(self):
        base, main = 0x2A7700000000, 0x80551000
        listing, read, slot = emulator_process(base, main)
        regions = self.Regions(listing)
        self.assertEqual(port_layout(read, regions), (base, slot))
        self.assertEqual(regions.calls, 1)
        self.assertEqual(port_layout(read, listing), (base, slot))   # a list works too
        self.assertIsNone(port_layout(read))                          # no regions: no scan

    def test_junk_memory_is_never_taken(self):
        self.assertIsNone(port_layout(Space().get, []))
        self.assertIsNone(port_layout(self.port_space(HOST_BASE, 0, bools={5: True, 17: False}).get, []))
        rng = random.Random(0xBAD5)
        for _ in range(8):
            space, listing = Space(), []
            for base in PORT_BASES:
                plant_junk(space, listing, rng, base, GAMEDATA_SLOT)
            # and a module the scan finds, whose slot leads to junk at one of the guest addresses it tries
            module, main = rng.randrange(0x2000, 0x7000) << 32, rng.choice(GUEST_CODE)
            head = bytearray(rng.randbytes(0x1000))
            struct.pack_into('<II', head, 0, 0, 0x40)
            head[0x40:0x44] = b'MOD0'
            space.add(module, head)
            listing.append((module, 0x1000, MEM_COMMIT))
            plant_junk(space, listing, rng, module - main, main + SLOT_OFFSET)
            regions = self.Regions(sorted(listing))
            self.assertIsNone(port_layout(space.get, regions))
            self.assertEqual(regions.calls, 1)


# Added: mailbox keys
SIGNAL_KEY, IDX0, CODE3, CODE9, COUNT0 = (murmur3(name) for name in (
    delivery.SIGNAL, 'RandoAP_Idx0', 'RandoAP_Code3', 'RandoAP_Code9', 'RandoAP_Count0'))
AT2 = 0xA0000000


class KeyAccessTests(unittest.TestCase):
    """read_keys / write_keys / set_bool: positions resolved once per layout, only bit 0 written, allowlist."""
    BOOLS = {SEQUENCE_IS_CHILDHOOD: True, SIGNAL_KEY: True, IDX0: False, CODE3: True, COUNT0: True}

    def game(self, bools=None, writable=delivery.WRITABLE):
        memory = FakeMemory(gamedata_image(bools or self.BOOLS, size=16, at=AT))
        return memory, LiveGameData(memory, writable=writable)

    def test_keys_are_distinct(self):
        self.assertEqual(len({SEQUENCE_IS_CHILDHOOD, SIGNAL_KEY, IDX0, CODE3, CODE9, COUNT0}), 6)
        self.assertLessEqual({SIGNAL_KEY, IDX0, CODE3, CODE9}, delivery.WRITABLE)
        self.assertNotIn(COUNT0, delivery.WRITABLE)
        self.assertNotIn(SEQUENCE_IS_CHILDHOOD, delivery.WRITABLE)

    def test_read_keys_one_byte_per_key_through_cached_positions(self):
        memory, data = self.game()
        keys = [SIGNAL_KEY, IDX0, CODE3, CODE9]
        self.assertEqual(data.read_keys(keys), {SIGNAL_KEY: True, IDX0: False, CODE3: True, CODE9: None})
        self.assertEqual(memory.reads_at(TABLE), 1)   # resolving reads the table once, not once per key
        memory.reads.clear()
        memory.space.put(value_byte(self.BOOLS, IDX0), b'\x01')   # the game changes a value
        self.assertEqual(data.read_keys(keys), {SIGNAL_KEY: True, IDX0: True, CODE3: True, CODE9: None})
        self.assertEqual(memory.reads_at(TABLE), 0)   # cached: the table isn't read again
        self.assertEqual(sorted(read for read in memory.reads if read[1] == 1),
                         sorted((value_byte(self.BOOLS, key), 1) for key in (SIGNAL_KEY, IDX0, CODE3)))
        self.assertEqual([read for read in memory.reads if read[1] > 8], [])
        self.assertEqual(memory.writes, [])

    def test_read_keys_resolves_a_new_key_once(self):
        memory, data = self.game()
        data.read_keys([SIGNAL_KEY])
        self.assertEqual(data.read_keys([SIGNAL_KEY, COUNT0]), {SIGNAL_KEY: True, COUNT0: True})
        self.assertEqual(memory.reads_at(TABLE), 2)
        data.read_keys([SIGNAL_KEY, COUNT0])
        self.assertEqual(memory.reads_at(TABLE), 2)

    def test_read_keys_resolve_again_when_the_layout_changes(self):
        moved = {IDX0: True, SEQUENCE_IS_CHILDHOOD: True, COUNT0: False, SIGNAL_KEY: False, CODE3: False}
        image = gamedata_image(moved, size=32, at=AT2)
        for case in ('table and entries', 'entries'):
            with self.subTest(case):
                memory, data = self.game()
                self.assertEqual(data.read_keys([SIGNAL_KEY, IDX0]), {SIGNAL_KEY: True, IDX0: False})
                # a save loaded: the game builds its GameData again elsewhere
                header = bytearray(memory.space.get(MANAGER, 48))
                if case == 'table and entries':
                    memory.space.add(AT2 + 0x3000, image[AT2 + 0x3000])
                    memory.space.add(AT2 + 0x5000, image[AT2 + 0x5000])
                    struct.pack_into('<I', header, 16, len(moved))
                    struct.pack_into('<QQ', header, 24, AT2 + 0x5000, AT2 + 0x3000)
                    struct.pack_into('<I', header, 44, 32)
                    expected, table = {SIGNAL_KEY: False, IDX0: True}, AT2 + 0x3000
                else:   # same table, the values moved
                    entries = bytearray(memory.space.get(ENTRIES, len(self.BOOLS) * 24))
                    entries[value_byte(self.BOOLS, SIGNAL_KEY) - ENTRIES] = 0
                    entries[value_byte(self.BOOLS, IDX0) - ENTRIES] = 1
                    memory.space.add(AT2 + 0x5000, entries)
                    struct.pack_into('<Q', header, 24, AT2 + 0x5000)
                    expected, table = {SIGNAL_KEY: False, IDX0: True}, TABLE
                memory.space.put(MANAGER, header)
                before = memory.reads_at(table)
                self.assertEqual(data.read_keys([SIGNAL_KEY, IDX0]), expected)
                self.assertEqual(memory.reads_at(table), before + 1)

    def test_write_keys_changes_bit_0_only(self):
        memory, data = self.game()
        for key, byte in ((SIGNAL_KEY, 0xA4), (IDX0, 0x5B), (CODE3, 0xFE)):
            memory.space.put(value_byte(self.BOOLS, key), bytes([byte]))
        before = memory.space.get(ENTRIES, len(self.BOOLS) * 24)
        data.write_keys([(SIGNAL_KEY, True), (IDX0, False), (CODE3, True), (IDX0, True)])
        position = lambda key: value_byte(self.BOOLS, key)
        self.assertEqual(memory.writes, [(position(SIGNAL_KEY), b'\xa5'), (position(IDX0), b'\x5a'),
                                         (position(CODE3), b'\xff'), (position(IDX0), b'\x5b')])
        expected = bytearray(before)
        expected[position(SIGNAL_KEY) - ENTRIES], expected[position(CODE3) - ENTRIES] = 0xA5, 0xFF
        self.assertEqual(memory.space.get(ENTRIES, len(self.BOOLS) * 24), bytes(expected))
        # the value byte is entries + index * 24 + 22
        self.assertEqual(position(CODE3), ENTRIES + list(self.BOOLS).index(CODE3) * 24 + 22)
        self.assertEqual(data.read_keys([SIGNAL_KEY, IDX0, CODE3]), {SIGNAL_KEY: True, IDX0: True, CODE3: True})

    def test_write_keys_refuses_a_key_outside_the_allowlist_before_any_write(self):
        memory, data = self.game()
        before = {address: bytes(region) for address, region in memory.space.regions.items()}
        with self.assertRaises(PermissionError):
            data.write_keys([(SIGNAL_KEY, False), (IDX0, True), (COUNT0, False)])
        with self.assertRaises(PermissionError):
            data.write_keys([(SEQUENCE_IS_CHILDHOOD, False)])
        self.assertEqual(memory.writes, [])
        self.assertEqual(memory.reads, [])   # refused before the game is even read
        self.assertEqual({address: bytes(region) for address, region in memory.space.regions.items()}, before)

    def test_write_keys_writes_nothing_when_the_game_lacks_a_key(self):
        memory, data = self.game()
        with self.assertRaises(LiveUnavailable):
            data.write_keys([(SIGNAL_KEY, False), (IDX0, True), (CODE9, True)])   # Code9: allowed, not in the game
        self.assertEqual(memory.writes, [])
        self.assertTrue(memory.space.get(value_byte(self.BOOLS, SIGNAL_KEY), 1)[0] & 1)
        self.assertEqual(memory.closed, 1)

    def test_write_keys_with_an_empty_allowlist(self):
        memory, data = self.game(writable=())
        with self.assertRaises(PermissionError):
            data.write_keys([(SIGNAL_KEY, True)])
        self.assertEqual(memory.writes, [])

    def test_set_bool(self):
        memory, data = self.game()
        with self.assertRaises(PermissionError):
            data.set_bool(COUNT0, False)
        self.assertEqual((memory.writes, memory.reads), ([], []))
        memory.space.put(value_byte(self.BOOLS, IDX0), b'\xc0')
        self.assertTrue(data.set_bool(IDX0, True))
        self.assertEqual(memory.writes, [(value_byte(self.BOOLS, IDX0), b'\xc1')])
        self.assertFalse(data.set_bool(CODE9, True))   # allowed, but the game doesn't know it
        self.assertEqual(len(memory.writes), 1)

    def test_event_playing_reads_only(self):
        for shift in (0, 0x327000):   # Longshot's main, and an emulator's main loaded elsewhere
            with self.subTest(shift=hex(shift)):
                manager = AT + 0x2000
                event = live_memory.EVENTMGR_SLOT + shift
                regions = {event: struct.pack('<Q', AT + 0x1000), AT + 0x1000: struct.pack('<Q', manager),
                           manager: bytes(128)}
                memory = FakeMemory(regions, slot=GAMEDATA_SLOT + shift)
                data = LiveGameData(memory)
                self.assertFalse(live_memory.event_playing(data))
                memory.space.put(manager + live_memory.EVENT_PLAYING_OFFSET, struct.pack('<Q', 0x1234))
                self.assertTrue(live_memory.event_playing(data))
                memory.space.put(event, bytes(8))
                with self.assertRaises(LiveUnavailable):
                    live_memory.event_playing(data)
                self.assertEqual(memory.writes, [])


# Added: the mailbox
SEED_KEY = 'Ab3dEf7hK2'
MARKER = f'RandoAP_Seed_{SEED_KEY}'
CODES = {'Progressive Hookshot': 0x155, 'Bow': 0x2AA, 'Zeldas Lullaby': 0x3FF}
OTHER_BITS = 0xA0   # set in every value byte: the client may change bit 0 only


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class SimulatedGame:
    """The game's side of MAILBOX.md section 2, poking the same fake memory directly (never through the client).

    Every frame of play MainUpdate reads Signal. When it's true and no event plays, it clears it and starts the mailbox
    event. That event ends at once if Idx != Count & 15. Otherwise it gives the item whose code is the Code bits and
    adds 1 to Count when the item-get text closes, which is at once, or at end_event() for a long one."""

    def __init__(self, memory, positions):
        self.memory, self.positions = memory, positions
        self.given = []     # codes handed over, in order
        self.stale = 0      # events ended at once (Idx != Count & 15)
        self.event = False  # an item event still playing

    def get(self, name):
        return bool(self.memory.space.get(self.positions[name], 1)[0] & 1)

    def set(self, name, value):
        address = self.positions[name]
        byte = self.memory.space.get(address, 1)[0]
        self.memory.space.put(address, bytes([(byte & ~1) | int(bool(value))]))

    def number(self, names):
        return sum(int(self.get(name)) << bit for bit, name in enumerate(names))

    def set_number(self, value, names):
        for bit, name in enumerate(names):
            self.set(name, (value >> bit) & 1)

    def frame(self, drop=False, long_event=False):
        if self.event or not self.get(delivery.SIGNAL):
            return
        self.set(delivery.SIGNAL, False)
        if drop:
            return          # the request was lost: Signal cleared, nothing given, nothing counted
        if self.number(delivery.IDX) != self.number(delivery.COUNT) & 15:
            self.stale += 1
            return
        self.given.append(self.number(delivery.CODE))
        self.event = True
        if not long_event:
            self.end_event()

    def end_event(self):
        if self.event:
            self.set_number(self.number(delivery.COUNT) + 1, delivery.COUNT)
            self.event = False


class MailboxEndToEndTests(unittest.TestCase):
    """delivery.Delivery over delivery.GameMailbox(LiveGameData(fake memory, writable=delivery.WRITABLE))."""

    def mailbox_game(self, marker=False, codes=CODES):
        names = delivery.COUNT + delivery.CODE + delivery.IDX + [delivery.SIGNAL, MARKER]
        bools = {SEQUENCE_IS_CHILDHOOD: True}
        bools.update((murmur3(name), marker and name == MARKER) for name in names)
        self.assertEqual(len(bools), len(names) + 1)   # no two names share a hash
        memory = FakeMemory(gamedata_image(bools, size=128, at=AT))
        for index in range(len(bools)):
            address = ENTRIES + index * 24 + 22
            memory.space.put(address, bytes([memory.space.get(address, 1)[0] | OTHER_BITS]))
        game = SimulatedGame(memory, {name: value_byte(bools, murmur3(name)) for name in names})
        clock = FakeClock()
        mailbox = delivery.Delivery(delivery.GameMailbox(LiveGameData(memory, writable=delivery.WRITABLE)),
                                    SEED_KEY, codes, clock=clock)
        return memory, game, mailbox, clock

    def expected_writes(self, game, index, code):
        """MAILBOX.md's order: Idx = (n + 1) & 15, then Code, then Idx = n & 15, then Signal last."""
        bits = lambda value, names: [(name, (value >> bit) & 1) for bit, name in enumerate(names)]
        pairs = (bits((index + 1) & 15, delivery.IDX) + bits(code, delivery.CODE) + bits(index & 15, delivery.IDX)
                 + [(delivery.SIGNAL, 1)])
        return [(game.positions[name], bytes([OTHER_BITS | value])) for name, value in pairs]

    def assert_mailbox_writes_only(self, memory, game):
        allowed = {game.positions[name] for name in delivery.CODE + delivery.IDX + [delivery.SIGNAL]}
        self.assertTrue(memory.writes)
        self.assertLessEqual({address for address, _ in memory.writes}, allowed)
        for name, address in game.positions.items():
            self.assertEqual(memory.space.get(address, 1)[0] & ~1, OTHER_BITS, name)
        self.assertLessEqual(memory.reads_at(TABLE), 2)   # a poll reads a few bytes, not the table

    def test_three_items_arrive_in_order(self):
        memory, game, mailbox, clock = self.mailbox_game()
        names = ['Progressive Hookshot', 'Bow', 'Zeldas Lullaby']
        # title screen: the marker is false, nothing is written however long it lasts
        for _ in range(40):
            self.assertIsNone(mailbox.step(names))
            game.frame()
            clock.advance(1.0)
        self.assertEqual(memory.writes, [])
        self.assertIn('no save of this seed', mailbox.status)

        game.set(MARKER, True)   # the seed's save is loaded
        self.assertEqual(mailbox.step(names), 0)
        self.assertEqual(memory.writes, self.expected_writes(game, 0, CODES[names[0]]))
        # a menu is open: Signal stays up and nothing is sent again, however long it takes
        written = len(memory.writes)
        for _ in range(4):
            clock.advance(delivery.RETRY_SECONDS)
            self.assertIsNone(mailbox.step(names))
        self.assertEqual(len(memory.writes), written)
        game.frame()
        self.assertEqual(game.given, [CODES[names[0]]])

        # back to the title screen with items still to come: nothing is written
        game.set(MARKER, False)
        for _ in range(10):
            clock.advance(delivery.RETRY_SECONDS)
            self.assertIsNone(mailbox.step(names))
        self.assertEqual(len(memory.writes), written)
        game.set(MARKER, True)

        self.assertEqual(mailbox.step(names), 1)   # the receipt (Count 1) lets the next item go at once
        self.assertEqual(memory.writes[written:], self.expected_writes(game, 1, CODES[names[1]]))
        game.frame(drop=True)                     # Signal cleared, the request lost: nothing counted
        self.assertEqual(game.number(delivery.COUNT), 1)
        written = len(memory.writes)
        self.assertIsNone(mailbox.step(names))    # sees Signal taken: the receipt timer starts
        clock.advance(delivery.RETRY_SECONDS - 0.25)
        self.assertIsNone(mailbox.step(names))
        self.assertEqual(len(memory.writes), written)
        clock.advance(0.25)
        self.assertEqual(mailbox.step(names), 1)  # no receipt RETRY_SECONDS after: signalled again
        self.assertEqual(memory.writes[written:], self.expected_writes(game, 1, CODES[names[1]]))
        self.assertIn(('retry', 1), mailbox.mailbox.take_notes())
        game.frame()

        self.assertEqual(mailbox.step(names), 2)
        game.frame()
        self.assertIsNone(mailbox.step(names))
        self.assertEqual(mailbox.status, 'every received item is in the game')

        # nothing more is written or given, however long the game keeps running
        written = len(memory.writes)
        for _ in range(20):
            clock.advance(delivery.RETRY_SECONDS)
            self.assertIsNone(mailbox.step(names))
            game.frame()
        self.assertEqual(len(memory.writes), written)
        self.assertEqual(game.given, [CODES[name] for name in names])
        self.assertEqual(game.number(delivery.COUNT), 3)
        self.assertEqual(game.stale, 0)
        self.assert_mailbox_writes_only(memory, game)

    def test_an_item_is_never_given_twice(self):
        # The item-get text stays open past RETRY_SECONDS. Count hasn't moved, so the client signals again. The
        # repeat waits behind the event, then the Idx check ends it without giving anything.
        memory, game, mailbox, clock = self.mailbox_game(marker=True)
        names = ['Progressive Hookshot', 'Bow']
        self.assertEqual(mailbox.step(names), 0)
        game.frame(long_event=True)
        self.assertIsNone(mailbox.step(names))
        clock.advance(delivery.RETRY_SECONDS)
        self.assertEqual(mailbox.step(names), 0)
        game.frame()                               # an event plays: the repeated Signal waits
        self.assertTrue(game.get(delivery.SIGNAL))
        game.end_event()                           # text closed: Count 1
        self.assertIsNone(mailbox.step(names))     # the stale Signal is still up: wait for the game
        game.frame()
        self.assertEqual(game.stale, 1)
        self.assertEqual(mailbox.step(names), 1)
        game.frame()
        self.assertIsNone(mailbox.step(names))
        self.assertEqual(game.given, [CODES['Progressive Hookshot'], CODES['Bow']])
        self.assertEqual(game.number(delivery.COUNT), 2)
        self.assert_mailbox_writes_only(memory, game)

    def test_twenty_items_with_a_frame_between_every_write(self):
        # Signal is written last, so a frame of play between any two writes never sees a half-written item. Idx
        # wraps past 15, and a name without a code goes as code 0 (counted, nothing given).
        codes = {f'Item {i}': (i * 389 + 17) % 1023 + 1 for i in range(19)}
        names = [f'Item {i}' for i in range(19)]
        names.insert(11, 'An item of a newer apworld')
        memory, game, mailbox, clock = self.mailbox_game(marker=True, codes=codes)
        memory.on_write = game.frame
        delivered = []
        for _ in range(len(names)):
            delivered.append(mailbox.step(names))
            clock.advance(0.25)
        self.assertEqual(delivered, list(range(20)))
        self.assertIsNone(mailbox.step(names))
        self.assertEqual(game.given, [codes.get(name, 0) for name in names])
        self.assertEqual(game.number(delivery.COUNT), 20)
        self.assertEqual(game.stale, 0)
        self.assertIn(('no_code', 11), mailbox.mailbox.take_notes())
        self.assert_mailbox_writes_only(memory, game)

    def test_nothing_written_for_another_seed_or_a_game_without_mailbox(self):
        memory, game, _, clock = self.mailbox_game(marker=True)
        other = delivery.Delivery(delivery.GameMailbox(LiveGameData(memory, writable=delivery.WRITABLE)),
                                  'OtherSeed42', CODES, clock=clock)
        self.assertIsNone(other.step(['Bow']))
        self.assertIn('no save of this seed', other.status)
        plain = FakeMemory(gamedata_image({SEQUENCE_IS_CHILDHOOD: True, murmur3(MARKER): True}, at=AT))
        without = delivery.Delivery(delivery.GameMailbox(LiveGameData(plain, writable=delivery.WRITABLE)),
                                    SEED_KEY, CODES, clock=clock)
        self.assertIsNone(without.step(['Bow']))
        self.assertIn('no mailbox', without.status)
        self.assertEqual(memory.writes + plain.writes, [])


# Ported: Linux
class LinuxProcessTests(unittest.TestCase):
    """Linux process access, from fake /proc text and folders."""
    MAPS = (
        '55d0c0a00000-55d0c0a21000 r--p 00000000 08:02 1234                       /usr/bin/ryuchii\n'
        '7f0000000000-7f0000001000 rw-s 00012000 00:01 4321                       /memfd:HostMemory (deleted)\n'
        '7f0000001000-7f0000002000 ---p 00000000 00:00 0 \n'
        '7f0000002000-7f0000003000 rw-s 00000000 00:0e 99                         /dev/dri/renderD128\n'
        '7f0000003000-7f0000004000 rw-s 00000000 00:19 98                         /dev/shm/eden_mem\n'
        '7f0000005000-7f0000006000 rw-p 00000000 00:00 0 \n'
        '7ffd1c3fe000-7ffd1c402000 r--p 00000000 00:00 0                          [vvar]\n'
        '7ffd1c402000-7ffd1c404000 r-xp 00000000 00:00 0                          [vdso]\n'
        'ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0                  [vsyscall]\n')

    def fake_proc(self, processes, scope=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for pid, comm in processes.items():
            (root / str(pid)).mkdir()
            (root / str(pid) / 'comm').write_text(comm + '\n', encoding='utf-8')
            (root / str(pid) / 'maps').write_text(self.MAPS, encoding='utf-8')
        (root / 'self').mkdir()
        if scope is not None:
            (root / 'sys' / 'kernel' / 'yama').mkdir(parents=True)
            (root / 'sys' / 'kernel' / 'yama' / 'ptrace_scope').write_text(f'{scope}\n', encoding='ascii')
        return str(root)

    def test_parses_maps(self):
        rows = parse_maps(self.MAPS + 'not a row\nzz-10 r--p 0 0 0\n')
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[1], (0x7F0000000000, 0x1000, 'rw-s', '/memfd:HostMemory (deleted)'))
        self.assertEqual(rows[2], (0x7F0000001000, 0x1000, '---p', ''))

    def test_keeps_readable_mappings_only(self):
        regions = readable_regions(parse_maps(self.MAPS))
        self.assertEqual([start for start, _, _ in regions],
                         [0x55D0C0A00000, 0x7F0000000000, 0x7F0000003000, 0x7F0000005000, 0x7FFD1C402000])
        self.assertEqual({state for _, _, state in regions}, {MEM_COMMIT})

    def test_names_with_or_without_exe(self):
        self.assertEqual(plain_name('C:\\Emu\\Ryuchii.EXE'), 'ryuchii')
        self.assertEqual(plain_name('"ryuchii"'), 'ryuchii')
        self.assertEqual(exe_link_name('/home/deck/Ryuchii/usr/bin/ryuchii (deleted)'), 'ryuchii')
        self.assertEqual(exe_link_name('/home/deck/Games/Longshot/longshot.exe'), 'longshot')
        self.assertTrue(names_match({'ryuchii'}, {plain_name(name) for name in EMULATOR_EXES}))
        self.assertTrue(names_match({'longshot'}, {plain_name(name) for name in PORT_EXES}))
        # /proc/<pid>/comm keeps 15 characters of a longer name.
        self.assertTrue(names_match({'ryuchii-green-h'}, {'ryuchii-green-hat-boy'}))
        self.assertFalse(names_match({'ryuchii-green'}, {'ryuchii-green-hat-boy'}))
        self.assertFalse(names_match({'bash', ''}, {'ryuchii'}))

    def test_parse_exe_names(self):
        self.assertEqual(parse_exe_names('"C:\\Program Files\\Eden\\Eden.exe"; MyEmu\nother.EXE, ,'),
                         {'eden.exe', 'myemu.exe', 'other.exe'})
        self.assertEqual(parse_exe_names(None), set())
        saved = live_memory._extra_emulators
        self.addCleanup(setattr, live_memory, '_extra_emulators', saved)
        live_memory.set_extra_emulators('MyEmu')
        self.assertIn('myemu.exe', live_memory.emulator_exes())
        self.assertLessEqual(EMULATOR_EXES, live_memory.emulator_exes())

    def test_finds_emulators_by_comm(self):
        proc = self.fake_proc({1001: 'ryuchii', 1003: 'bash', 1005: 'MyEmu', 1007: 'ryuchii'})
        emulators = EMULATOR_EXES | parse_exe_names('MyEmu.exe')
        self.assertEqual(linux_pids(emulators, proc, own=1007), [1001, 1005])
        self.assertEqual(linux_pids(EMULATOR_EXES, proc + '-missing'), [])

    def test_finds_ports_and_emulators_by_exe_link(self):
        # Wine names the comm after the exe; a renamed thread leaves only /proc/<pid>/exe
        proc = self.fake_proc({1001: 'MainThread', 1003: 'bash', 1005: 'longshot.exe', 1007: 'Hookshot.exe'})
        links = {os.path.join(proc, '1001', 'exe'): '/opt/eden/eden (deleted)',
                 os.path.join(proc, '1003', 'exe'): '/usr/bin/bash'}

        def readlink(path):
            if path in links:
                return links[path]
            raise OSError(2, 'No such file or directory', path)

        with mock.patch.object(live_memory.os, 'readlink', readlink):
            self.assertEqual(linux_pids(EMULATOR_EXES | PORT_EXES, proc), [1001, 1005, 1007])
            self.assertEqual(linux_pids(PORT_EXES, proc), [1005, 1007])

    def test_ptrace_scope(self):
        self.assertEqual(ptrace_scope(self.fake_proc({}, scope=1)), 1)
        self.assertIsNone(ptrace_scope(self.fake_proc({})))

    def test_denied_messages_name_the_value_and_the_fix(self):
        for scope in (0, 1, 2, 3):
            self.assertIn(f'ptrace_scope is {scope}', denied_message(scope))
        for scope in (1, 2, 3):
            self.assertIn('Fix:', denied_message(scope))
        self.assertIn('restart', denied_message(3))
        self.assertNotIn('ptrace_scope', denied_message(None))
        self.assertIn('run this client as the user who runs the emulator', denied_message(None))

    def test_refused_memory_reports_ptrace_scope(self):
        class Refused(LinuxProcessMemory):
            def _open(self, pid, flags):
                raise PermissionError(13, 'Permission denied')
        memory = Refused(self.fake_proc({1001: 'ryuchii'}, scope=1))
        with mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES):
            with self.assertRaises(LiveUnavailable) as caught:
                LiveGameData(memory).snapshot()
        self.assertIn('ptrace_scope is 1', str(caught.exception))
        self.assertIn('Fix:', str(caught.exception))
        with self.assertRaises(LiveUnavailable) as again:   # before the next scan: the same reason
            LiveGameData(memory).snapshot()
        self.assertEqual(str(again.exception), str(caught.exception))

    def test_no_emulator_running(self):
        memory = LinuxProcessMemory(self.fake_proc({1003: 'bash'}))
        with mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES):
            with self.assertRaises(LiveUnavailable) as caught:
                memory.attach()
        self.assertEqual(str(caught.exception), 'game not running')

    def wine_port(self):
        """A fake /proc with an emulator that can't be opened and Longshot under Wine, whose /proc/<pid>/mem is
        stood in for by ``space`` (guest memory mapped 1:1, as Longshot's log suggests)."""
        proc = self.fake_proc({1001: 'bash', 1003: 'eden', 1005: 'longshot.exe'})
        bools = {SEQUENCE_IS_CHILDHOOD: True, 17: False}
        space = Space(gamedata_image(bools, at=AT))
        stand_in = Path(proc, 'mem-stand-in')
        stand_in.write_bytes(b'')
        calls = {'open': [], 'memfd': []}

        class Wine(LinuxProcessMemory):
            def _guest_memfds(self, pid):
                calls['memfd'].append(pid)
                return []

            def _open(self, pid, flags):
                calls['open'].append((pid, flags))
                if pid != 1005:
                    raise FileNotFoundError(2, 'No such file or directory')
                return os.open(stand_in, flags)   # a real descriptor the class may close; reads go to ``space``

            def _read(self, fd, host, size):
                return space.get(host, size)

        def pwrite(fd, data, offset):
            return len(data) if space.put(offset, data) else 0

        memory = Wine(proc)
        self.addCleanup(memory.close)
        patches = (mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES),
                   mock.patch.object(live_memory.os, 'pwrite', pwrite, create=True))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return memory, space, calls, value_byte(bools, 17)

    def test_attaches_to_a_port_under_wine(self):
        memory, space, calls, byte_17 = self.wine_port()
        data = LiveGameData(memory, writable={17})
        self.assertTrue(data.snapshot()['bool'][SEQUENCE_IS_CHILDHOOD])
        self.assertEqual((memory.pid, memory.kind, memory.base, memory.slot), (1005, 'port', 0, GAMEDATA_SLOT))
        self.assertEqual(calls['memfd'], [1003])   # the port isn't searched for an emulator's memory file
        self.assertEqual(calls['open'], [(1003, os.O_RDONLY), (1005, os.O_RDONLY)])
        self.assertTrue(data.set_bool(17, True))   # written through /proc/<pid>/mem at base + guest
        self.assertEqual(calls['open'][-1], (1005, os.O_RDWR))
        self.assertEqual(space.get(byte_17, 1), b'\x01')

    # On Linux `image` has to be set too, or the game status reads ": a save of this seed is loaded"
    def test_a_linux_port_is_named(self):
        memory, _, _, _ = self.wine_port()
        data = LiveGameData(memory)
        data.snapshot()
        self.assertIn('longshot', data.describe().lower())
        self.assertTrue(data.describe().endswith('(port)'))

    def test_process_memory_of_this_system(self):
        if os.name == 'nt':
            self.assertIsInstance(live_memory.process_memory(), live_memory.ProcessMemory)
        elif sys.platform.startswith('linux'):
            self.assertIsInstance(live_memory.process_memory(), LinuxProcessMemory)
        self.assertEqual(live_memory.supported(), os.name == 'nt' or sys.platform.startswith('linux'))


class MemfdTests(unittest.TestCase):
    """The guest memory file route, which kernel.yama.ptrace_scope 1 allows."""
    BASE, MAIN, DATA = 0x7EE300000000, 0x80347000, 0x90000000
    # The rows of a Steam Deck's maps look like these: page-sized protection changes, one inode.
    MAPS = (
        '7ee397e00000-7ee397e17000 ---s 21000000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee397e17000-7ee397e18000 rw-s 21017000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee397e18000-7ee397e23000 ---s 21018000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee398000000-7ee398001000 rw-s 00000000 00:01 1369                       /memfd:HostMemory\n'
        '7ee398001000-7ee398002000 rw-s 00004000 00:01 1369                       /memfd:HostMemory (deleted)\n'
        '7ee398002000-7ee398003000 rw-s 00000000 00:01 77                         /memfd:Other\n'
        '7ee398003000-7ee398004000 rw-p 00000000 00:00 0 \n')

    def test_link_names(self):
        self.assertTrue(is_guest_memfd('/memfd:HostMemory (deleted)'))
        self.assertTrue(is_guest_memfd('/memfd:HostMemory'))
        self.assertFalse(is_guest_memfd('/memfd:HostMemoryX'))
        self.assertFalse(is_guest_memfd('/dev/shm/HostMemory'))

    def test_mappings_of_any_protection(self):
        rows = memfd_mappings(self.MAPS)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0], (0x7EE397E00000, 0x17000, 0x21000000, 1369))
        self.assertEqual(rows[4], (0x7EE398001000, 0x1000, 0x4000, 1369))

    def test_windows_join_only_continuous_mappings(self):
        windows = MemfdWindows(memfd_mappings(self.MAPS))
        self.assertEqual(windows.windows, [(0x7EE397E00000, 0x23000, 0x21000000), (0x7EE398000000, 0x1000, 0),
                                           (0x7EE398001000, 0x1000, 0x4000)])
        self.assertEqual(windows.pieces(0x7EE397E16FF8, 16), [(0x21016FF8, 16)])   # across a protection change
        self.assertEqual(windows.pieces(0x7EE398000FFC, 8), [(0xFFC, 4), (0x4000, 4)])
        self.assertIsNone(windows.pieces(0x7EE397E22FFC, 8))   # runs past the mapping
        self.assertIsNone(windows.pieces(0x7EE397DFFFFF, 2))   # starts before it
        self.assertIsNone(windows.pieces(0x7EE398002000, 1))
        self.assertEqual(windows.pieces(0x7EE398000000, 0), [])

    def guest_file(self, folder):
        """A guest memory file and its maps text: main, the GameData slot (a protected page) and the data."""
        slot = self.MAIN + SLOT_OFFSET
        image = gamedata_image({SEQUENCE_IS_CHILDHOOD: True, 17: False}, gamedata_slot=slot, at=self.DATA)
        image[self.MAIN] = struct.pack('<II', 1, 0x40) + bytes(56) + b'MOD0'
        # guest page -> (file offset, size, protection); the file pages are not in guest order
        layout = {self.MAIN: (0x20000, 0x1000, 'rw-s'), slot & ~0xFFF: (0x0, 0x1000, '---s'),
                  self.DATA: (0x1000, 0x10000, 'rw-s')}
        content = bytearray(0x21000)
        for guest, data in image.items():
            page = max(start for start in layout if start <= guest)
            offset = layout[page][0] + guest - page
            content[offset:offset + len(data)] = data
        path = Path(folder, 'HostMemory')
        path.write_bytes(bytes(content))
        inode = os.stat(path).st_ino
        lines = [f'{self.BASE + page:x}-{self.BASE + page + size:x} {protection} {offset:08x} 00:01 {inode}'
                 f'    /memfd:HostMemory (deleted)' for page, (offset, size, protection) in sorted(layout.items())]
        return path, '\n'.join(lines) + '\n', slot

    def test_attaches_and_writes_through_the_file(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path, maps, slot = self.guest_file(folder.name)
        proc = Path(folder.name, 'proc')
        (proc / '1001').mkdir(parents=True)
        (proc / '1001' / 'comm').write_text('ryuchii\n', encoding='utf-8')
        (proc / '1001' / 'maps').write_text(maps, encoding='utf-8')

        def pread(fd, size, offset):   # os.pread is POSIX only; the file is read by path
            with open(path, 'rb') as file:
                file.seek(offset)
                return file.read(size)

        def pwrite(fd, data, offset):
            with open(path, 'r+b') as file:
                file.seek(offset)
                return file.write(data)

        class Memfd(LinuxProcessMemory):
            def _guest_memfds(self, pid):
                return [str(path)]

            def _open(self, pid, flags):
                raise AssertionError('/proc/<pid>/mem opened')

        memory = Memfd(str(proc))
        with mock.patch.object(live_memory, 'emulator_exes', return_value=EMULATOR_EXES), \
                mock.patch.object(live_memory.os, 'pread', pread, create=True), \
                mock.patch.object(live_memory.os, 'pwrite', pwrite, create=True):
            try:
                snapshot = LiveGameData(memory).snapshot()
                self.assertEqual((memory.base, memory.slot, memory.kind), (self.BASE, slot, 'emulator'))
                self.assertTrue(snapshot['bool'][SEQUENCE_IS_CHILDHOOD])
                memory.write(self.DATA + 0x5000 + 24 + 22, b'\x01')   # key 17's value byte
                self.assertTrue(LiveGameData(memory).snapshot()['bool'][17])
                with self.assertRaises(LiveUnavailable):
                    memory.read(self.DATA + 0x20000, 8)   # not mapped, even after reading maps again
            finally:
                memory.close()


if __name__ == '__main__':
    unittest.main()
