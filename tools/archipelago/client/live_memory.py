# Ported from OotrR (github.com/Mozencaz/OotrR, src/oot_rando/tracker/live_memory.py).
# Copyright (c) 2026 Mozencaz. MIT License: see LICENSE-OotrR.txt in this folder.
# Changes for Rando of Time: Longshot's layouts tried first (fixed window, then guest memory mapped 1:1),
# processes found by name through a Toolhelp snapshot (no process is opened unless its name matches), and a write
# allowlist (only the mailbox keys of data/archipelago/MAILBOX.md can ever be written).
"""Real-time GameData Bools of a running game: Longshot or Hookshot (Windows), or a yuzu-family emulator (Windows, or
native Linux).

The layout, as Hookshot v2.1.0's own cheat menu reads it (tools/host/hos_main.c, oot_gamedata_set_bool). Longshot is
a fork of Hookshot and loads the same image (builds/rc/image.bin has rtld MOD0 at +0x301c and main at +0x20000 with
MOD0 at +0x3c4705c), so main sits at guest 0x80020000 like in Hookshot.
- Guest memory is one window at the fixed host address HOST_BASE = 0x100000000000 (in Hookshot host = base + guest).
  Longshot's log says "image 96 MB at 0x80000000" and "heap at 0x1000000000", which reads as guest memory mapped
  1:1 (host = guest). We try both bases and only keep one once the GameData table it leads to is proven, meaning it
  holds murmur3('Sequence_IsChildhood').
- The guest pointer at GAMEDATA_SLOT (0x84c9e180) points to a holder whose first word is the GameDataMgr.
- GameDataMgr+32 is a (hash u32, index u32) open-addressing table with its size u32 at +44. The probe starts at
  hash % size and key 0 is an empty slot.
- GameDataMgr+24 holds the Bool entries, 24 bytes each with the value byte at +22, and their count u32 is at +16.

Emulators (Eden, Lichii, yuzu and forks) run the same game code, so the structures are the same. Only two addresses
differ, and they change at every boot. Guest memory is a window of the emulator process ("fastmem"), and the main
module is loaded at a random page near 0x80000000. ``emulator_layout`` finds the modules by their MOD0 header in the
process, then tries the possible guest addresses of each and keeps the one where the slot leads to a GameData table
holding a known key. The same scan is the last resort for a port whose fixed layouts both fail.

Bool64bitKey flags are keyed by a placed actor's u64 hash (chests, Gold Skulltulas, freestanding items...). What we
know about them comes from the sloperina practice menu's findings. There's a u32 count at GameDataMgr+0xC58, and at
the pointer in +0xC60 there are 16-byte records sorted by key (u64 key, u32 reset type, u8 value at +0xC). A seed's
own keys are appended after the sorted ones.

The only write is ``LiveGameData.set_bool``. It writes one value byte like the cheat menu does, and only for a key
on the allowlist the caller gives (the documented mailbox keys).
"""
import bisect
import ctypes
import os
import struct
import sys
import time
from pathlib import Path, PureWindowsPath

HOST_BASE = 0x100000000000
GAMEDATA_SLOT = 0x84C9E180
HOOKSHOT_MAIN = 0x80020000                 # where Hookshot (and Longshot's image) keeps the main module
SEQUENCE_IS_CHILDHOOD = 0xCEA220D3         # murmur3('Sequence_IsChildhood'), always present
MAX_TABLE, MAX_BOOLS = 1 << 20, 1 << 20
BOOL64_TYPE = 0xC58                        # GameDataMgr offset of the Bool64bitKey entry (v131072)
BOOL64_SCAN = range(0xC08, 0xD08, 8)       # other offsets tried if the game's layout moved
BOOL64_RECORD = 16
BOOL64_PROBE = 0xECDC46B409ED7D38          # the game's first Gold Skulltula: every save knows it
PORT_EXES = {'longshot.exe', 'hookshot.exe'}
EMULATOR_EXES = {'lichii.exe', 'ryuchii.exe', 'eden.exe', 'yuzu.exe', 'suyu.exe', 'citron.exe', 'sudachi.exe'}
# A port's guest memory: Hookshot's fixed window, then guest addresses as host addresses (Longshot's log)
PORT_BASES = (HOST_BASE, 0)
MEM_COMMIT = 0x1000
MAX_MODULE = 0x10000000                              # MOD0 may sit past the first region (main: +0x3c4705c)
GUEST_CODE = range(0x80000000, 0x84000000, 0x1000)   # where emulators load the main module
SCAN_SECONDS = 5.0                                   # a process scan at most this often while no game is found


class LiveUnavailable(Exception):
    pass


def parse_exe_names(text):
    """Executable names from a free list (commas, semicolons or lines): lower case, '.exe' added."""
    names = set()
    for part in str(text or '').replace(';', ',').replace('\n', ',').split(','):
        name = PureWindowsPath(part.strip().strip('"')).name.lower()
        if name:
            names.add(name if name.endswith('.exe') else name + '.exe')
    return names


_extra_emulators = set()


def set_extra_emulators(text):
    """Executables the player listed (the client's settings), used by the next process scan."""
    global _extra_emulators
    _extra_emulators = parse_exe_names(text)


def emulator_exes():
    return EMULATOR_EXES | _extra_emulators


def plain_name(name):
    """Executable name without folder and '.exe', lower case: 'ryuchii.exe' matches the Linux 'ryuchii'."""
    name = PureWindowsPath(str(name).strip().strip('"')).name.lower()
    return name[:-4] if name.endswith('.exe') else name


def supported():
    """True where the running game's memory can be read: Windows, and Linux (native emulators)."""
    return os.name == 'nt' or sys.platform.startswith('linux')


# Pure parts
def parse_bools(table, entries, count):
    """{hash: bool} from the raw hash table and Bool entries (pure: tested without a game)."""
    result = {}
    for slot in range(len(table) // 8):
        key, index = struct.unpack_from('<II', table, slot * 8)
        if key and index < count:
            result[key] = bool(entries[index * 24 + 22] & 1)
    return result


def parse_bool64(records, count):
    """{key: True} of the set Bool64bitKey flags, or None when ``records`` is not the table whose sorted part knows
    :data:`BOOL64_PROBE` (pure). The game's own keys come first, sorted, and a seed's keys are appended after them."""
    keys, flags, sorted_end = [], {}, None
    for index in range(count):
        key, value = struct.unpack_from('<Q4xB', records, index * BOOL64_RECORD)
        if sorted_end is None and keys and key <= keys[-1]:
            sorted_end = index
        keys.append(key)
        if value == 1:
            flags[key] = True
    head = keys[:sorted_end]
    position = bisect.bisect_left(head, BOOL64_PROBE)
    return flags if position < len(head) and head[position] == BOOL64_PROBE else None


def bool_slot(table, size, key):
    """Index of Bool ``key`` in the raw (hash, index) table, or None (pure)."""
    for probe in range(size):
        slot = (key + probe) % size
        found, index = struct.unpack_from('<II', table, slot * 8)
        if not found:
            return None
        if found == key:
            return index
    return None


def valid_slot(read, slot):
    """True when guest ``slot`` leads to a GameData manager whose table knows a vanilla key.

    ``read(guest, size)`` returns bytes or None. Pure: tested without a game.
    """
    def pointer(address):
        raw = read(address, 8)
        value = struct.unpack('<Q', raw)[0] if raw else 0
        return value if 0x10000 <= value < 1 << 48 and not value & 7 else 0

    holder = pointer(slot)
    manager = pointer(holder) if holder else 0
    header = read(manager, 48) if manager else None
    if not header or len(header) < 48:
        return False
    count, size = struct.unpack_from('<I', header, 16)[0], struct.unpack_from('<I', header, 44)[0]
    entries, table = struct.unpack_from('<QQ', header, 24)
    if not (table and entries and 0 < size <= MAX_TABLE and 0 < count <= MAX_BOOLS):
        return False
    raw = read(table, size * 8)
    index = bool_slot(raw, size, SEQUENCE_IS_CHILDHOOD) if raw else None
    return index is not None and index < count


def module_starts(regions, read):
    """Host addresses of the loaded NSO modules (committed regions starting with a MOD0 pointer)."""
    result = []
    for address, size, state in regions:
        if state != MEM_COMMIT or size < 0x1000:
            continue
        head = read(address, 8)
        offset = struct.unpack_from('<I', head, 4)[0] if head else 0
        if 8 <= offset < MAX_MODULE and not offset & 3 and read(address + offset, 4) == b'MOD0':
            result.append(address)
    return result


def emulator_layout(regions, read):
    """(host base of guest memory, guest GameData slot) in an emulator process, or None.

    ``regions``: (address, size, state) of the process, in address order; ``read(host, size)`` returns bytes or None.
    Pure: tested without a game.
    """
    offset = GAMEDATA_SLOT - HOOKSHOT_MAIN
    for module in module_starts(regions, read):
        raw = read(module + offset, 8)
        if not raw or not struct.unpack('<Q', raw)[0]:
            continue   # not main, or the game has not loaded its data yet
        for guest in GUEST_CODE:
            base = module - guest
            if valid_slot(lambda address, length, base=base: read(base + address, length), guest + offset):
                return base, guest + offset
    return None


def port_layout(read, regions=None):
    """(host base, guest slot) of a Longshot/Hookshot process: its fixed layouts, then the MOD0 scan; or None (pure)."""
    for base in PORT_BASES:
        if valid_slot(lambda address, length, base=base: read(base + address, length), GAMEDATA_SLOT):
            return base, GAMEDATA_SLOT
    if regions is not None:
        return emulator_layout(regions() if callable(regions) else regions, read)
    return None


# Windows
class MemoryRegion(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_ulonglong), ('AllocationBase', ctypes.c_ulonglong),
                ('AllocationProtect', ctypes.c_ulong), ('PartitionId', ctypes.c_ushort),
                ('RegionSize', ctypes.c_ulonglong), ('State', ctypes.c_ulong),
                ('Protect', ctypes.c_ulong), ('Type', ctypes.c_ulong)]


class ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong), ('th32ProcessID', ctypes.c_ulong),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', ctypes.c_ulong),
                ('cntThreads', ctypes.c_ulong), ('th32ParentProcessID', ctypes.c_ulong),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong), ('szExeFile', ctypes.c_wchar * 260)]


class ProcessMemory:
    """ReadProcessMemory on the running game: Longshot/Hookshot, else an emulator that has the game loaded.

    ``base``: host address of guest address 0; ``slot``: guest address of the GameData slot.
    """
    def __init__(self):
        from ctypes import wintypes
        self.wt = wintypes
        self.k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k = self.k32
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
        k.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
                                         ctypes.POINTER(ctypes.c_size_t)]
        k.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(MemoryRegion),
                                     ctypes.c_size_t]
        k.VirtualQueryEx.restype = ctypes.c_size_t
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
        self.handle, self.pid, self.next_scan = None, None, 0.0
        self.image = ''   # full path of the attached game's exe
        self.kind = ''    # 'port' or 'emulator'
        self.base, self.slot = HOST_BASE, GAMEDATA_SLOT

    def _processes(self):
        """(pid, lower-case exe name) of every process, from a Toolhelp snapshot (opens no process)."""
        snap = self.k32.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
        if not snap or snap == ctypes.c_void_p(-1).value:
            return []
        result, entry = [], ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        try:
            ok = self.k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                result.append((entry.th32ProcessID, entry.szExeFile.lower()))
                ok = self.k32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            self.k32.CloseHandle(snap)
        return result

    def _exe(self, handle):
        size = self.wt.DWORD(520)
        buffer = ctypes.create_unicode_buffer(size.value)
        if self.k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ''

    def alive(self):
        if not self.handle:
            return False
        code = self.wt.DWORD()
        return bool(self.k32.GetExitCodeProcess(self.handle, ctypes.byref(code)) and code.value == 259)

    def attach(self):
        if self.handle:
            if self.alive():
                return
            self.close()
        now = time.monotonic()
        if now < self.next_scan:
            raise LiveUnavailable('game not running')
        self.next_scan = now + SCAN_SECONDS
        emulators = emulator_exes()
        for pid, name in self._processes():
            port = name in PORT_EXES
            if not port and name not in emulators:
                continue
            handle = self.k32.OpenProcess(0x0010 | 0x0400, False, pid)   # VM_READ | QUERY_INFORMATION
            if not handle:
                continue
            read = lambda host, size, handle=handle: self._read(handle, host, size)
            regions = lambda handle=handle: self._regions(handle)
            layout = port_layout(read, regions) if port else emulator_layout(self._regions(handle), read)
            if layout:
                self.handle, self.pid, self.image = handle, pid, self._exe(handle) or name
                self.kind = 'port' if port else 'emulator'
                self.base, self.slot = layout
                return
            self.k32.CloseHandle(handle)
        raise LiveUnavailable('game not running')

    def _regions(self, handle):
        """(address, size, state) of every region of the process, in address order."""
        result, address, region = [], 0, MemoryRegion()
        while self.k32.VirtualQueryEx(handle, address, ctypes.byref(region), ctypes.sizeof(region)):
            result.append((region.BaseAddress, region.RegionSize, region.State))
            address = region.BaseAddress + region.RegionSize
            if address >= 1 << 48:
                break
        return result

    def _read(self, handle, host, size):
        if host < 0 or size <= 0:
            return None
        buffer, done = ctypes.create_string_buffer(size), ctypes.c_size_t()
        if not self.k32.ReadProcessMemory(handle, ctypes.c_void_p(host), buffer, size, ctypes.byref(done)) \
                or done.value != size:
            return None
        return buffer.raw

    def read(self, guest, size):
        data = self._read(self.handle, self.base + guest, size)
        if data is None:
            raise LiveUnavailable(f'cannot read at {guest:#x}')
        return data

    def write(self, guest, data):
        """WriteProcessMemory through a handle opened for this write only."""
        handle = self.k32.OpenProcess(0x0008 | 0x0020 | 0x0010, False, self.pid)   # VM_OPERATION|VM_WRITE|VM_READ
        if not handle:
            raise LiveUnavailable('cannot open the game for writing')
        try:
            done = ctypes.c_size_t()
            if not self.k32.WriteProcessMemory(handle, ctypes.c_void_p(self.base + guest), data, len(data),
                                               ctypes.byref(done)) or done.value != len(data):
                raise LiveUnavailable(f'cannot write at {guest:#x}')
        finally:
            self.k32.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.k32.CloseHandle(self.handle)
        self.handle, self.pid, self.image, self.kind = None, None, '', ''


# Linux
# /proc/<pid>/maps rows we never read: the kernel pages /proc/<pid>/mem refuses, and device mappings (GPU memory).
# Guest memory is the emulator's memfd ("/memfd:HostMemory") or anonymous.
SKIPPED_MAPPINGS = ('[vvar]', '[vvar_vclock]', '[vsyscall]')
COMM_LENGTH = 15   # /proc/<pid>/comm keeps the first 15 bytes of the name
MEMFD_NAME = '/memfd:HostMemory'   # the yuzu-family emulators' guest memory file (memfd_create)


def parse_maps(text):
    """(start, size, permissions, path) of each /proc/<pid>/maps row (pure)."""
    rows = []
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 5 or '-' not in fields[0]:
            continue
        try:
            start, end = (int(value, 16) for value in fields[0].split('-', 1))
        except ValueError:
            continue
        rows.append((start, end - start, fields[1], fields[5].strip() if len(fields) > 5 else ''))
    return rows


def readable_regions(rows):
    """(address, size, MEM_COMMIT) of the readable mappings, as :func:`emulator_layout` takes them (pure)."""
    return [(start, size, MEM_COMMIT) for start, size, permissions, path in rows
            if permissions.startswith('r') and path not in SKIPPED_MAPPINGS
            and not (path.startswith('/dev/') and not path.startswith('/dev/shm/'))]


def is_guest_memfd(path):
    """True for the link name or maps path of an emulator's guest memory file (pure)."""
    return path in (MEMFD_NAME, MEMFD_NAME + ' (deleted)')


def memfd_mappings(text):
    """(start, size, file offset, inode) of each /proc/<pid>/maps row of a guest memory file (pure)."""
    rows = []
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6 or not is_guest_memfd(fields[5].strip()):
            continue
        try:
            start, end = (int(value, 16) for value in fields[0].split('-', 1))
            rows.append((start, end - start, int(fields[2], 16), int(fields[4])))
        except ValueError:
            continue
    return rows


class MemfdWindows:
    """Host addresses to offsets in the guest memory file, from its mappings (pure). Mappings that continue each
    other in both the address space and the file are joined."""
    def __init__(self, mappings):
        self.windows = []
        for start, size, offset, _ in sorted(mappings):
            last = self.windows[-1] if self.windows else None
            if last and last[0] + last[1] == start and last[2] + last[1] == offset:
                self.windows[-1] = (last[0], last[1] + size, last[2])
            else:
                self.windows.append((start, size, offset))
        self.starts = [window[0] for window in self.windows]

    def pieces(self, host, size):
        """[(file offset, length)] covering host..host+size, or None when part of it is not in the file."""
        result = []
        while size > 0:
            index = bisect.bisect_right(self.starts, host) - 1
            if index < 0:
                return None
            start, length, offset = self.windows[index]
            if host >= start + length:
                return None
            part = min(size, start + length - host)
            result.append((offset + host - start, part))
            host, size = host + part, size - part
        return result


def exe_link_name(target):
    """Name of the /proc/<pid>/exe target; an executable replaced on disk ends in ' (deleted)' (pure)."""
    if target.endswith(' (deleted)'):
        target = target[:-len(' (deleted)')]
    return plain_name(target.replace('\\', '/').rsplit('/', 1)[-1])


def names_match(names, wanted):
    """True when a process name is a wanted one (``wanted`` is plain names). A 15-character name may be a truncated
    /proc/<pid>/comm (pure)."""
    return any(name and (name in wanted or (len(name) == COMM_LENGTH and any(w.startswith(name) for w in wanted)))
               for name in names)


def linux_process_names(proc, pid):
    names = set()
    try:
        names.add(plain_name(Path(proc, str(pid), 'comm').read_text(encoding='utf-8', errors='replace').strip()))
    except OSError:
        pass
    try:
        names.add(exe_link_name(os.readlink(os.path.join(proc, str(pid), 'exe'))))
    except (OSError, NotImplementedError, ValueError):
        pass
    return names


def linux_pids(executables, proc='/proc', own=None):
    """Process ids whose comm or executable name is one of ``executables`` (with or without '.exe')."""
    wanted = {plain_name(name) for name in executables}
    try:
        entries = os.listdir(proc)
    except OSError:
        return []
    pids = sorted(int(entry) for entry in entries if entry.isdigit() and int(entry) != own)
    return [pid for pid in pids if names_match(linux_process_names(proc, pid), wanted)]


def ptrace_scope(proc='/proc'):
    try:
        return int(Path(proc, 'sys', 'kernel', 'yama', 'ptrace_scope').read_text(encoding='ascii').strip())
    except (OSError, ValueError):
        return None


def denied_message(scope):
    """Why Linux refused to open the emulator's memory, and the fix (pure)."""
    if scope == 1:
        return ('Linux refused to read the emulator\'s memory: kernel.yama.ptrace_scope is 1 (only a parent '
                'process may read it). Fix: set kernel.yama.ptrace_scope to 0 (sysctl, as root).')
    if scope == 2:
        return ('Linux refused to read the emulator\'s memory: kernel.yama.ptrace_scope is 2 (administrators '
                'only). Fix: set kernel.yama.ptrace_scope to 0 (sysctl, as root).')
    if scope == 3:
        return ('Linux refused to read the emulator\'s memory: kernel.yama.ptrace_scope is 3 (no process may, '
                'and it stays so until a restart). Fix: set it to 0 in the boot settings (sysctl.d), then restart.')
    return ('Linux refused to read the emulator\'s memory' + (f' (kernel.yama.ptrace_scope is {scope})'
            if scope is not None else '') + ': run this client as the user who runs the emulator.')


class LinuxProcessMemory:
    """Memory of a native Linux emulator that has the game loaded (same interface as :class:`ProcessMemory`).

    First the emulator's guest memory file (``/memfd:HostMemory``), opened again through ``/proc/<pid>/fd`` and read
    at the offsets ``/proc/<pid>/maps`` gives (works with kernel.yama.ptrace_scope 1); else ``/proc/<pid>/mem``.
    A Windows port under Wine/Proton (longshot.exe) is tried through ``/proc/<pid>/mem`` with the port layouts.
    """
    def __init__(self, proc='/proc'):
        self.proc, self.fd, self.pid, self.next_scan = proc, None, None, 0.0
        self.base, self.slot = HOST_BASE, GAMEDATA_SLOT
        self.failure = 'game not running'
        self.windows, self.memfd, self.inode, self.next_maps = None, None, None, 0.0
        self.image, self.kind = '', ''

    def _open(self, pid, flags):
        return os.open(os.path.join(self.proc, str(pid), 'mem'), flags)

    def _maps(self, pid):
        try:
            return Path(self.proc, str(pid), 'maps').read_text(encoding='utf-8', errors='replace')
        except OSError:
            return ''

    def _regions(self, pid):
        return readable_regions(parse_maps(self._maps(pid)))

    def _guest_memfds(self, pid):
        folder = os.path.join(self.proc, str(pid), 'fd')
        try:
            entries = sorted((entry for entry in os.listdir(folder) if entry.isdigit()), key=int)
        except OSError:
            return []
        paths = []
        for entry in entries:
            try:
                if is_guest_memfd(os.readlink(os.path.join(folder, entry))):
                    paths.append(os.path.join(folder, entry))
            except OSError:
                continue
        return paths

    @staticmethod
    def _read(fd, host, size):
        try:
            data = os.pread(fd, size, host)
        except (OSError, OverflowError):
            return None
        return data if len(data) == size else None

    @staticmethod
    def _read_file(fd, windows, host, size):
        pieces = windows.pieces(host, size)
        if pieces is None:
            return None
        data = b''
        for offset, length in pieces:
            try:
                part = os.pread(fd, length, offset)
            except (OSError, OverflowError):
                return None
            if len(part) != length:
                return None
            data += part
        return data

    def _attach_memfd(self, pid):
        text = self._maps(pid)
        for path in self._guest_memfds(pid):
            try:
                fd = os.open(path, os.O_RDONLY)
            except OSError:
                continue
            inode = os.fstat(fd).st_ino
            mappings = [row for row in memfd_mappings(text) if row[3] == inode]
            windows = MemfdWindows(mappings)
            regions = [(start, size, MEM_COMMIT) for start, size, _, _ in mappings]
            layout = emulator_layout(regions, lambda host, size: self._read_file(fd, windows, host, size))
            if layout:
                return fd, path, inode, windows, layout
            os.close(fd)
        return None

    def _read_attached(self, host, size):
        if self.fd is None:
            return None
        if self.windows is None:
            return self._read(self.fd, host, size)
        data = self._read_file(self.fd, self.windows, host, size)
        if data is None and time.monotonic() >= self.next_maps:
            self.next_maps = time.monotonic() + 1
            self.windows = MemfdWindows([row for row in memfd_mappings(self._maps(self.pid)) if row[3] == self.inode])
            data = self._read_file(self.fd, self.windows, host, size)
        return data

    def attach(self):
        if self.fd is not None:
            if Path(self.proc, str(self.pid)).is_dir():
                return
            self.close()
        now = time.monotonic()
        if now < self.next_scan:
            raise LiveUnavailable(self.failure)
        self.next_scan = now + SCAN_SECONDS
        denied = False
        ports = {plain_name(name) for name in PORT_EXES}
        for pid in linux_pids(emulator_exes() | PORT_EXES, self.proc, os.getpid()):
            port = bool(linux_process_names(self.proc, pid) & ports)
            if not port:
                found = self._attach_memfd(pid)
                if found:
                    self.fd, self.memfd, self.inode, self.windows, (self.base, self.slot) = found
                    self.pid, self.kind, self.image = pid, 'emulator', self._image(pid)
                    return
            try:
                fd = self._open(pid, os.O_RDONLY)
            except PermissionError:
                denied = True
                continue
            except OSError:
                continue
            read = lambda host, size, fd=fd: self._read(fd, host, size)
            layout = port_layout(read, lambda pid=pid: self._regions(pid)) if port else \
                emulator_layout(self._regions(pid), read)
            if layout:
                self.fd, self.pid, self.kind = fd, pid, 'port' if port else 'emulator'
                self.image = self._image(pid)
                self.base, self.slot = layout
                return
            os.close(fd)
        self.failure = denied_message(ptrace_scope(self.proc)) if denied else 'game not running'
        raise LiveUnavailable(self.failure)

    def _image(self, pid):
        """The attached process's executable (its /proc exe link, else its comm), for the window's status."""
        try:
            target = os.readlink(os.path.join(self.proc, str(pid), 'exe'))
            if target.endswith(' (deleted)'):
                target = target[:-len(' (deleted)')]
            name = target.replace('\\', '/').rsplit('/', 1)[-1]
            if name and not name.startswith(('wine', 'wine64')):
                return name
        except (OSError, NotImplementedError, ValueError):
            pass
        try:
            return Path(self.proc, str(pid), 'comm').read_text(encoding='utf-8', errors='replace').strip()
        except OSError:
            return ''

    def alive(self):
        return self.fd is not None and Path(self.proc, str(self.pid)).is_dir()

    def read(self, guest, size):
        data = self._read_attached(self.base + guest, size)
        if data is None:
            raise LiveUnavailable(f'cannot read at {guest:#x}')
        return data

    def write(self, guest, data):
        if self.windows is not None:
            self._write_file(guest, data)
            return
        try:
            fd = self._open(self.pid, os.O_RDWR)
        except PermissionError:
            raise LiveUnavailable(denied_message(ptrace_scope(self.proc))) from None
        except OSError:
            raise LiveUnavailable('cannot open the game for writing') from None
        try:
            done = os.pwrite(fd, data, self.base + guest)
        except (OSError, OverflowError):
            done = -1
        finally:
            os.close(fd)
        if done != len(data):
            raise LiveUnavailable(f'cannot write at {guest:#x}')

    def _write_file(self, guest, data):
        pieces = self.windows.pieces(self.base + guest, len(data))
        if pieces is None:
            raise LiveUnavailable(f'cannot write at {guest:#x}')
        try:
            fd = os.open(self.memfd, os.O_RDWR)
        except OSError:
            raise LiveUnavailable('cannot open the game for writing') from None
        done = 0
        try:
            for offset, length in pieces:
                if os.pwrite(fd, data[done:done + length], offset) != length:
                    break
                done += length
        except (OSError, OverflowError):
            pass
        finally:
            os.close(fd)
        if done != len(data):
            raise LiveUnavailable(f'cannot write at {guest:#x}')

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd, self.pid, self.kind, self.image = None, None, '', ''
        self.windows, self.memfd, self.inode = None, None, None


class NoProcessMemory:
    """Systems without a memory reader: always unavailable."""
    image, kind = '', ''

    def attach(self):
        raise LiveUnavailable('live memory needs Windows or Linux')

    def read(self, guest, size):
        raise LiveUnavailable('live memory needs Windows or Linux')

    def write(self, guest, data):
        raise LiveUnavailable('live memory needs Windows or Linux')

    def alive(self):
        return False

    def close(self):
        pass


def process_memory():
    if os.name == 'nt':
        return ProcessMemory()
    if sys.platform.startswith('linux'):
        return LinuxProcessMemory()
    return NoProcessMemory()


# GameData
class LiveGameData:
    """``snapshot()`` -> {'bool': {hash: bool}, 'bool64': {key: True}, 'bool64_complete': bool} or LiveUnavailable.

    ``writable``: the Bool hashes ``set_bool`` may write (the mailbox keys); any other write is refused.
    """
    def __init__(self, memory=None, writable=()):
        self.memory = memory or process_memory()
        self.writable = frozenset(int(k) for k in writable)
        self._layout = None
        self._bool64_offset = None

    def u64(self, guest):
        return struct.unpack('<Q', self.memory.read(guest, 8))[0]

    def u32(self, guest):
        return struct.unpack('<I', self.memory.read(guest, 4))[0]

    def _tables(self):
        self.memory.attach()
        holder = self.u64(getattr(self.memory, 'slot', GAMEDATA_SLOT))
        manager = self.u64(holder) if holder else 0
        if not manager:
            raise LiveUnavailable('game data not loaded yet')
        table, size = self.u64(manager + 32), self.u32(manager + 44)
        entries, count = self.u64(manager + 24), self.u32(manager + 16)
        if not (table and entries and 0 < size <= MAX_TABLE and 0 < count <= MAX_BOOLS):
            raise LiveUnavailable('unexpected GameData structure (game version?)')
        return manager, table, size, entries, count

    def snapshot(self, bool64=True):
        try:
            manager, table, size, entries, count = self._tables()
            raw_table = self.memory.read(table, size * 8)
            raw_entries = self.memory.read(entries, count * 24)
        except LiveUnavailable:
            self.memory.close()
            raise
        except OSError as error:
            self.memory.close()
            raise LiveUnavailable(str(error)) from None
        self._layout = (table, size, entries, count)
        bools = parse_bools(raw_table, raw_entries, count)
        if SEQUENCE_IS_CHILDHOOD not in bools:
            raise LiveUnavailable('GameData table not recognised')
        snapshot = {'bool': bools, 'bool64': {}, 'bool64_complete': False}
        if bool64:
            try:
                snapshot['bool64'] = self._bool64(manager)
                snapshot['bool64_complete'] = True
            except LiveUnavailable as error:
                snapshot['bool64_status'] = str(error)
        return snapshot

    def _bool64(self, manager):
        offsets = [self._bool64_offset] if self._bool64_offset else []
        for offset in offsets + [BOOL64_TYPE] + [o for o in BOOL64_SCAN if o != BOOL64_TYPE]:
            try:
                count, records = self.u32(manager + offset), self.u64(manager + offset + 8)
                if not (0 < count <= MAX_BOOLS and records and not records & 7):
                    continue
                raw = self.memory.read(records, count * BOOL64_RECORD)
            except LiveUnavailable:
                continue
            flags = parse_bool64(raw, count)
            if flags is not None:
                self._bool64_offset = offset
                return flags
        self._bool64_offset = None
        raise LiveUnavailable('Bool64bitKey flags not found (game version?)')

    def set_bool(self, key, value):
        """Writes Bool ``key`` (hash) in the running game, one value byte. False when the game doesn't know it.

        A key outside ``writable`` is refused (PermissionError), so only the documented mailbox keys are ever written.
        """
        key = int(key)
        if key not in self.writable:
            raise PermissionError(f'GameData key {key:#010x} is not a mailbox key: not written')
        try:
            _, table, size, entries, count = self._tables()
            index = bool_slot(self.memory.read(table, size * 8), size, key)
            if index is None or index >= count:
                return False
            position = entries + index * 24 + 22
            current = self.memory.read(position, 1)[0]
            self.memory.write(position, bytes([(current & ~1) | int(bool(value))]))
        except OSError as error:
            self.memory.close()
            raise LiveUnavailable(str(error)) from None
        return True

    def _positions(self, keys):
        """{key: guest address of its value byte, or None when the game doesn't know it}. Resolved once per
        GameData layout, so a poll then reads a few bytes instead of the whole table."""
        _, table, size, entries, count = self._tables()
        layout = (table, size, entries, count)
        if layout != getattr(self, '_pos_layout', None):
            self._pos_layout, self._pos = layout, {}
        missing = [k for k in keys if k not in self._pos]
        if missing:
            raw = self.memory.read(table, size * 8)
            for key in missing:
                index = bool_slot(raw, size, key)
                self._pos[key] = entries + index * 24 + 22 if index is not None and index < count else None
        return {k: self._pos[k] for k in keys}

    def read_keys(self, keys):
        """{key: bool, or None when the game doesn't know the key}: one byte read per key."""
        try:
            positions = self._positions([int(k) for k in keys])
            return {k: (None if p is None else bool(self.memory.read(p, 1)[0] & 1)) for k, p in positions.items()}
        except LiveUnavailable:
            self.memory.close()
            raise
        except OSError as error:
            self.memory.close()
            raise LiveUnavailable(str(error)) from None

    def write_keys(self, pairs):
        """Writes [(key, bool)] in order. Every key must be in ``writable``, else nothing at all is written."""
        pairs = [(int(k), bool(v)) for k, v in pairs]
        refused = [k for k, _ in pairs if k not in self.writable]
        if refused:
            raise PermissionError(f'GameData key {refused[0]:#010x} is not a mailbox key: nothing written')
        try:
            positions = self._positions([k for k, _ in pairs])
            if any(p is None for p in positions.values()):
                raise LiveUnavailable('the running game has no mailbox')
            for key, value in pairs:
                position = positions[key]
                current = self.memory.read(position, 1)[0]
                self.memory.write(position, bytes([(current & ~1) | int(value)]))
        except LiveUnavailable:
            self.memory.close()
            raise
        except OSError as error:
            self.memory.close()
            raise LiveUnavailable(str(error)) from None

    def describe(self):
        """Which game is attached, for the window ("Longshot (port)", "eden.exe (emulator)")."""
        image = getattr(self.memory, 'image', '') or ''
        name = PureWindowsPath(image).name if image else ''
        kind = getattr(self.memory, 'kind', '')
        return f'{name} ({kind})' if name and kind else name


# EventMgr, as Hookshot's teleport cheat reads it (hos_main.c, OOT_EVENTMGR_SLOT). It's a guest pointer to a holder
# whose first word is the manager, and the manager's u64 at +104 is non-zero while an event plays (talks, cutscenes,
# chests).
EVENTMGR_SLOT = 0x84C9E090
EVENT_PLAYING_OFFSET = 104


def event_playing(data):
    """Whether an event plays in the game ``data`` (a LiveGameData) is attached to. Reads 24 bytes, never writes."""
    memory = data.memory
    try:
        memory.attach()
        holder = data.u64(getattr(memory, 'slot', GAMEDATA_SLOT) - GAMEDATA_SLOT + EVENTMGR_SLOT)
        manager = data.u64(holder) if holder else 0
        word = data.u64(manager + EVENT_PLAYING_OFFSET) if manager else 0
    except LiveUnavailable:
        memory.close()
        raise
    if not holder or not manager:
        raise LiveUnavailable('event manager not loaded yet')
    return word != 0


def main():
    """Diagnostic, reads only (game running): ``python -m client.live_memory``."""
    data = LiveGameData()
    try:
        snap = data.snapshot()
    except LiveUnavailable as error:
        print('Cannot read the game:', error)
        return 1
    print(f"{data.describe()}: base {data.memory.base:#x}, slot {data.memory.slot:#x}")
    print(f"{len(snap['bool'])} Bools read; Sequence_IsChildhood = {snap['bool'][SEQUENCE_IS_CHILDHOOD]}")
    print('Bool64bitKey:', f"{len(snap['bool64'])} set" if snap['bool64_complete'] else snap.get('bool64_status'))
    try:
        print('Event playing:', event_playing(data))
    except LiveUnavailable as error:
        print('Event state unreadable:', error)
    return 0


if __name__ == '__main__':
    sys.exit(main())
