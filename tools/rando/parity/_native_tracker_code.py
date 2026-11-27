"""The code patch behind the tracker in the game's own map (rando/native_tracker.py, remake_native_tracker).

How the map's icons work in the game's code (main = 0x80020000 + offset in image.bin, Longshot v3.2.0):
- One screen class draws the pause map and the HUD minimap. Its set-up (0x80F9B1D0) makes the icon panes: it finds
  Pa_Facility_00 in the layout and clones it into a pool of 10 (+0xE0 count, +0xE8 array, made at 0x80F9D08C, the
  fallback at 0x80F9D0E0, the count at 0x80F9D0A0), naming the clones from a table of 9 names (+0x140/+0x148, made at
  0x80F9D130 or 0x80F9D5F0 and filled by hand at 0x80F9D144..0x80F9D208).
- The map's facility records (MapParam Facility, 0xC0 bytes each) go in a list of 10 made by 0x8113EFE0, which fills
  the ten by hand. The parser (0x80B83320) drops records past the list's end.
- Every frame the facility updater (0x80222CF0) takes each record: it hashes its GameDataHashName and looks it up as a
  Bool, then as an expression (BoolExp); on true it goes to 0x80222EB8, takes the record (x8) and reads its IconType
  at 0x80222ECC; on false it hides the icon (0x802230A0). A shown icon's IconType is its picture (the Type
  animation's frame). Then, for the heart badge, it walks every heart and skull sign record of the map
  (0x802232DC: their count, +0x368) looking for the facility's HeartPieceHash0/1.
- An object's own save row (Bool64bitKey) is read by 0x83781680(manager, &byte, hash): a binary search of the rows at
  manager+0xC58 (count, then the 16-byte rows, value at +0xC). A write doesn't change the row right away: the setters
  (0x83781720, and 0x80F27130 for an actor's own no-respawn row) queue {value, row index} at 0x80F271C0, and the
  row only changes once the game applies that queue. Taking a rupee queues its row, so reading the row alone missed
  it.

The patch:
- 0x8113EFE0 is rewritten as a loop making `n` records; the rest of its body holds the two hooks below.
- The pool holds `n` icons and the name table `n` - 1 names, filled by a loop. The rest of that block (nothing else
  jumps into it) holds the object check (OBJECT_CHECK).
- The parser (0x80B83584..0x80B835C8) keeps InstanceID at +0x00 and the heart hashes from +0xB0: HeartPieceHash0
  there, and HeartPieceHash1 next to it at +0xB8 only when Hash0 isn't 0 (with Hash0 0, Hash1 takes +0xB0).
- At 0x80222ECC (a shown record): a record whose +0xB0 is OBJECT_MARK (HeartPieceHash0, only the tracker's) goes to
  the object check, which hides it once the row of its InstanceID is set or a write setting it is queued. x8, w14
  and x15 (where the manager pointer is, 0x80222DE8 / 0x80223098) are untouched.
- At 0x802232DC: a record with no HeartPieceHash0, or the mark there, skips the heart badge walk, the way a map
  without hearts does (s8 = 0 and w22 = 0xC0 are set by then). Every facility the game has with a badge has a real
  HeartPieceHash0; the walk copies each record's name, so with a few hundred icons it would cost the most per frame.
- The map switches: before anything else a shown record whose IconType has a byte set in HIDE_TABLE is hidden. That's
  256 bytes in memory nothing uses: main ends at 0x84EC0000, its .bss at 0x84EBA4C8, and the pages between are zero in
  the image (check() reads them). Our mod's cheats file (cheats(): Longshot's cheat engine, host/cheats.c, runs a mod's
  cheats/<build id>.txt, and each cheat is a switch in the Insert menu's Mods tab, kept in mods.json) fills it: each
  switch, while on, writes 1 at its IconTypes in HIDE_PENDING every frame, and an always-on cheat after them copies
  HIDE_PENDING into HIDE_TABLE and clears it. So a switch turned off shows its icons again a frame later, and the map
  never reads a table half cleared. Without the file (or with every switch off) the table stays zero.

The patch is for one build of the game's code (MAIN_BUILD_ID, the same as the gear wheel's); check() refuses another.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
import a64  # noqa: E402

MAIN_BUILD_ID = "e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348"
IMAGE_BASE, MAIN_BASE = 0x80000000, 0x80020000
PATCH_FILE = "rando_of_time_map_tracker.pchtxt"
OBJECT_MARK = 0xFFFFFFFFFFFFFFFF  # rando/native_tracker.OBJECT_MARK
VANILLA_N = 10
RECORDS = 0x8113EFE0              # the records list's maker (x0 = the list's {count, array}, x1 = the heap)
RECORDS_END = 0x8113F118          # its last word + 4 (two udf words of padding follow)
ALLOC = 0x8005EA70                # (heap, size, alignment, 0) -> memory
POOL = (0x80F9D08C, 0x80F9D0E0)   # mov w1, #0x50: the pool's array (heap, fallback)
POOL_N = 0x80F9D0A0               # mov w8, #0xa
NAMES = (0x80F9D130, 0x80F9D5F0)  # mov w1, #0x2d0: the name table (heap, fallback)
NAMES_FILL, NAMES_STORE = 0x80F9D144, 0x80F9D204  # the hand-made fill, then str w8,[x20,#0x140]; str x0,[x20,#0x148]
SHOWN = 0x80222ECC                # ldr w8, [x8, #0x18]
SHOWN_NEXT = SHOWN + 4
HIDE = 0x802230A0
BADGE = 0x802232DC                # ldr w8, [x19, #0x368]
BADGE_SKIP = 0x802239EC
ROW = 0x83781680
ROW_TABLE = 0xC58                 # the manager's Bool64bitKey table: +0 row count, +8 rows (what ROW searches)
QUEUE_ARRAY, QUEUE_STATE = 0x18, 0x20  # its queue of waiting writes (0x80F271C0 adds them)
OBJECT_CHECK = 0x80F9D178         # the object icons' test, in the name table's block after our loop (_names)
HIDE_TABLE = 0x84EBF000           # the map switches: a byte per IconType, set = hidden (past main's .bss, unused)
HIDE_PENDING = HIDE_TABLE + 0x100  # what the switches write each frame, copied into HIDE_TABLE by the last cheat
HIDE_SIZE = 0x100
CHEATS_FILE = MAIN_BUILD_ID[:16].upper() + ".txt"  # Longshot reads <mod>/cheats/<first 16 of the build id>.txt


def _vanilla_words():
    """{address: word} the patch expects at each site (the game's own instructions)."""
    e = a64.encode
    out = {SHOWN: e("ldr", ["w8", "x8", 0x18]), BADGE: e("ldr", ["w8", "x19", 0x368]),
           POOL_N: e("movz", ["w8", VANILLA_N]), NAMES_STORE: e("str", ["w8", "x20", 0x140]),
           NAMES_STORE + 4: e("str", ["x0", "x20", 0x148]),
           NAMES_FILL - 4: e("cbz", ["x0", NAMES_STORE + 8], NAMES_FILL - 4),
           0x80F9D1EC: e("movz", ["w8", VANILLA_N - 1]), RECORDS: 0xD503237F,
           0x8113F100: e("movz", ["w8", VANILLA_N]), 0x8113EFF8: e("movz", ["w1", VANILLA_N * 0xC0]),
           0x8113F004: e("bl", [ALLOC], 0x8113F004), RECORDS_END - 4: 0xD65F0FFF}
    out.update({a: e("movz", ["w1", VANILLA_N * 8]) for a in POOL})
    out.update({a: e("movz", ["w1", (VANILLA_N - 1) * 0x50]) for a in NAMES})
    return out


def _records(n):
    """The records maker for n records, then the two hooks, from RECORDS. (words, labels)"""
    p = a64.Program(RECORDS)
    p.op("pacibsp")
    p.op("stp", "x29", "x30", "sp", -0x20, "pre")
    p.op("str", "x19", "sp", 0x10)
    p.op("mov", "x29", "sp")
    p.op("mov", "x19", "x0")
    p.op("mov", "x0", "x1")
    p.mov32("w1", n * 0xC0)
    p.op("movz", "w2", 8)
    p.op("mov", "w3", "wzr")
    p.op("bl", ALLOC)
    p.op("cbz", "x0", "r_done")
    p.op("mov", "x8", "x0")
    p.op("movz", "w9", n)
    p.op("movz", "w10", 0x80)
    p.label("r_loop")                       # each record: no IconType, an empty name in its own 0x80-byte buffer
    p.op("str", "wzr", "x8", 0x18)
    p.op("add", "x11", "x8", 0x2C)
    p.op("str", "x11", "x8", 0x20)
    p.op("str", "w10", "x8", 0x28)
    p.op("strb", "wzr", "x8", 0x2C)
    p.op("strb", "wzr", "x8", 0xAB)
    p.op("add", "x8", "x8", 0xC0)
    p.op("subs", "w9", "w9", 1)
    p.op("b.ne", "r_loop")
    p.op("movz", "w8", n)
    p.op("str", "x0", "x19", 8)
    p.op("str", "w8", "x19", 0)
    p.label("r_done")
    p.op("ldr", "x19", "sp", 0x10)
    p.op("ldp", "x29", "x30", "sp", 0x20, "post")
    p.op("retab")
    # a shown record (x8): the tracker's object icons hide once their object's row is set (object_check, in the
    # name table's block)
    p.label("shown")
    p.op("ldr", "w9", "x8", 0x18)              # the map switches: its IconType's byte in HIDE_TABLE set = hidden
    p.op("cmp", "w9", HIDE_SIZE - 1)
    p.op("b.hi", "s_mark")
    p.op("adrp", "x10", HIDE_TABLE)
    p.op("add", "x10", "x10", HIDE_TABLE & 0xFFF)
    p.op("add", "x10", "x10", "x9")
    p.op("ldrb", "w10", "x10", 0)
    p.op("cbz", "w10", "s_mark")
    p.op("b", HIDE)
    p.label("s_mark")
    p.op("ldr", "x9", "x8", 0xB0)
    p.op("cmn", "x9", 1)
    p.op("b.ne", "s_plain")
    p.op("b", OBJECT_CHECK)
    p.label("s_plain")
    p.op("ldr", "w8", "x8", 0x18)
    p.op("b", SHOWN_NEXT)
    # the heart badge: a record without HeartPieceHash0 has none, and neither has one of the tracker's object icons
    p.label("badge")
    p.op("ldr", "w9", "x19", 0x1E0)
    p.op("ldr", "x10", "x19", 0x1E8)
    p.op("cmp", "x24", "x9")
    p.op("csel", "x9", "x24", "xzr", "lo")
    p.op("movz", "w11", 0xC0)
    p.op("madd", "x9", "x9", "x11", "x10")
    p.op("ldr", "x9", "x9", 0xB0)
    p.op("cbz", "x9", "b_skip")
    p.op("cmn", "x9", 1)
    p.op("b.ne", "b_walk")
    p.label("b_skip")
    p.op("b", BADGE_SKIP)
    p.label("b_walk")
    p.op("ldr", "w8", "x19", 0x368)
    p.op("b", BADGE + 4)
    words = p.assemble()
    if words[-1][0] + 4 > RECORDS_END:
        raise a64.AsmError("the map tracker's code doesn't fit the records maker")
    return words, p.labels


def _object_check(plain):
    """The object icons' test, from OBJECT_CHECK (record in x8, x15 &manager pointer): hidden (HIDE) when the row of
    the record's InstanceID is set, or a write of it is still waiting in the row table's queue; else back to `plain`.
    It's the game's own binary search (ROW), keeping the row's index for the queue. Only x0, x2, x9-x13, x16 and x17
    change; the updater sets each again before it reads it."""
    p = a64.Program(OBJECT_CHECK)
    p.op("ldr", "x0", "x15", 0)
    p.op("add", "x17", "x0", ROW_TABLE)
    p.op("ldr", "x2", "x8", 0)                 # the object's hash
    p.op("ldr", "w11", "x17", 0)               # the rows (16 bytes each: hash, ..., value at +0xC), sorted
    p.op("ldr", "x10", "x17", 8)
    p.op("mov", "w12", "wzr")
    p.op("sub", "w11", "w11", 1)
    p.label("o_loop")
    p.op("cmp", "w12", "w11")
    p.op("b.gt", "o_plain")                    # no row
    p.op("add", "w13", "w12", "w11")
    p.op("lsr", "w13", "w13", 1)
    p.op("add", "x16", "x10", "x13", 4)
    p.op("ldr", "x9", "x16", 0)
    p.op("cmp", "x9", "x2")
    p.op("b.eq", "o_found")
    p.op("sub", "w0", "w13", 1)
    p.op("csel", "w11", "w11", "w0", "lo")
    p.op("csinc", "w12", "w12", "w13", "hs")
    p.op("b", "o_loop")
    p.label("o_found")
    p.op("ldrb", "w9", "x16", 0xC)
    p.op("ldr", "w11", "x17", QUEUE_STATE)     # waiting writes: {u8 value, u32 row index}, the count in the low bits
    p.op("and", "w11", "w11", 0xFFFFF)
    p.op("ldr", "x10", "x17", QUEUE_ARRAY)
    p.label("o_scan")
    p.op("cbz", "w11", "o_done")
    p.op("ldr", "w12", "x10", 4)
    p.op("ldrb", "w0", "x10", 0)
    p.op("cmp", "w12", "w13")
    p.op("csel", "w9", "w0", "w9", "eq")       # the newest write of this row wins
    p.op("add", "x10", "x10", 8)
    p.op("sub", "w11", "w11", 1)
    p.op("b", "o_scan")
    p.label("o_done")
    p.op("tbz", "w9", 0, "o_plain")
    p.op("b", HIDE)
    p.label("o_plain")
    p.op("b", plain)
    words = p.assemble()
    if words[-1][0] + 4 > NAMES_STORE:
        raise a64.AsmError("the object check doesn't fit the name table's block")
    return words


def _names(n):
    """The name table's fill as a loop for n - 1 names (each: a pointer to its own 0x40-byte buffer, empty)."""
    p = a64.Program(NAMES_FILL)
    p.op("mov", "x8", "x0")
    p.op("movz", "w9", n - 1)
    p.op("movz", "w10", 0x40)
    p.label("n_loop")
    p.op("add", "x11", "x8", 0xC)
    p.op("str", "x11", "x8", 0)
    p.op("str", "w10", "x8", 8)
    p.op("strb", "wzr", "x8", 0xC)
    p.op("strb", "wzr", "x8", 0x4B)
    p.op("add", "x8", "x8", 0x50)
    p.op("subs", "w9", "w9", 1)
    p.op("b.ne", "n_loop")
    p.op("movz", "w8", n - 1)
    p.op("b", NAMES_STORE)
    return p.assemble()


def writes(n):
    """[(address, new word)] of the whole patch for a map of up to n facility icons."""
    if not VANILLA_N <= n <= 340:
        raise ValueError(f"map tracker: {n} icons on one map, 10 to 340 fit")
    e = a64.encode
    words, labels = _records(n)
    names = _names(n)
    if names[-1][0] + 4 > OBJECT_CHECK:
        raise a64.AsmError("the name table's loop runs into the object check")
    out = list(words) + names + _object_check(labels["s_plain"])
    out += [(a, e("movz", ["w1", n * 8])) for a in POOL] + [(POOL_N, e("movz", ["w8", n]))]
    out += [(a, e("movz", ["w1", (n - 1) * 0x50])) for a in NAMES]
    out += [(SHOWN, e("b", [labels["shown"]], SHOWN)), (BADGE, e("b", [labels["badge"]], BADGE))]
    return sorted(out)


def check(image_path):
    """Problems ([] when the patch fits this game): the game's own word at every site we read, or this patch's
    (a game Longshot built with it before)."""
    if not os.path.exists(image_path):
        return [f"{image_path}: missing (build the game once in Longshot first)"]
    bad = []
    with open(image_path, "rb") as f:
        def word(a):
            f.seek(a - IMAGE_BASE)
            return struct.unpack("<I", f.read(4))[0]
        w = word(SHOWN)
        off = (w & 0x3FFFFFF) - ((1 << 26) if w & (1 << 25) else 0)
        ours = w >> 26 == 0x05 and RECORDS <= SHOWN + 4 * off < RECORDS_END  # a branch into our records maker
        for a, want in sorted(_vanilla_words().items()):
            if word(a) != want and not ours:
                bad.append(f"main+{a - MAIN_BASE:X}: {word(a):08X}, expected {want:08X} (another game build?)")
        f.seek(HIDE_TABLE - IMAGE_BASE)
        if any(f.read(2 * HIDE_SIZE)):
            bad.append(f"main+{HIDE_TABLE - MAIN_BASE:X}: the map switches' memory isn't empty (another game build?)")
    return bad


def pchtxt(n):
    """The IPSwitch text Longshot's Builder reads (offsets into main, offset_shift 0x100 cancels the NSO header)."""
    lines = [f"@nsobid-{MAIN_BUILD_ID}", "@flag offset_shift 0x100", "",
             f"// Rando of Time: the tracker in the game's map, up to {n} icons a map. Made by "
             "tools/rando/parity/_native_tracker_code.py.", "@enabled"]
    run, start = b"", None
    for a, w in writes(n) + [(None, 0)]:
        if run and (a is None or a != start + len(run)):
            lines.append(f"{start - MAIN_BASE:08X} {run.hex().upper()}")
            run, start = b"", None
        if a is not None:
            start = a if start is None else start
            run += struct.pack("<I", w)
    lines += ["@stop", ""]
    return "\n".join(lines)


def cheats():
    """The map switches, as the text of our mod's cheats file (Atmosphere's cheat format, the opcodes Longshot runs):
    a heading, a switch per group of icons (_map_icons.hide_types), and the always-on copy into HIDE_TABLE."""
    from parity import _map_icons
    pend, table = HIDE_PENDING - MAIN_BASE, HIDE_TABLE - MAIN_BASE
    lines = ["[Rando of Time: map tracker switches]", ""]
    for name, types in _map_icons.hide_types():
        lines.append(f"[Map: hide {name}]")
        lines += [f"01000000 {pend + t:08X} 00000001" for t in sorted(set(types)) if 0 <= t < HIDE_SIZE]
        lines.append("")
    # always on, after the switches: HIDE_PENDING -> HIDE_TABLE, 8 bytes at a time through register 1, then
    # HIDE_PENDING cleared. (A store of a value, opcode 0, adds its register R to the address: R is 0 here, and
    # register 0 has to stay 0, so the bytes never go through it.)
    lines.append("{Map tracker: applies the switches}")
    for k in range(0, HIDE_SIZE, 8):
        lines += [f"58010000 {pend + k:08X}", f"A8100400 {table + k:08X}", f"08000000 {pend + k:08X} 00000000 00000000"]
    return "\n".join(lines) + "\n"


def cheats_problems(text):
    """[problem] running the cheats file the way Longshot's cheat engine does (host/cheats.c: the parse, and the
    opcodes it uses: 0 store, 5 load, A store a register), on memory that only holds HIDE_TABLE and HIDE_PENDING: every
    switch is a switch, nothing writes anywhere else, and a few frames with switches on, then off, leave HIDE_TABLE
    holding exactly their IconTypes."""
    from parity import _map_icons
    cheats = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line) >= 2 and line[0] in "[{" and line[-1] in "]}":
            cheats.append((line[1:-1].strip(), line[0] == "{", []))
        elif cheats:
            cheats[-1][2].extend(int(t, 16) for t in line.split() if len(t) == 8)
    base = HIDE_TABLE - MAIN_BASE
    mem = bytearray(2 * HIDE_SIZE)
    bad = []

    def run(words):
        r, i = [0] * 16, 0
        while i < len(words):
            f = words[i]
            t, width, n = f >> 28, (f >> 24) & 0xF, 0
            if t == 0:
                n = 4 if width == 8 else 3
            elif t == 5 or (t == 0xA and (f >> 8) & 0xF == 4):
                n = 2
            region = (f >> 4) & 0xF if t == 0xA else (f >> 20) & 0xF  # 0: main
            if not n or i + n > len(words) or width not in (1, 2, 4, 8) or region:
                return f"opcode {f:08X} isn't one the switches use"
            rel = ((f & 0xFF) << 32) | words[i + 1]
            if t == 5:
                if not 0 <= rel - base <= len(mem) - width:
                    return f"a read outside the switches' memory ({rel:#x})"
                r[(f >> 16) & 0xF] = int.from_bytes(mem[rel - base:rel - base + width], "little")
            else:
                at = rel + r[(f >> 16) & 0xF] if t == 0 else rel
                value = (words[i + 2] << 32 | words[i + 3] if width == 8 else words[i + 2]) if t == 0 else \
                    r[(f >> 20) & 0xF]
                if not 0 <= at - base <= len(mem) - width:
                    return f"a write outside the switches' memory ({at:#x})"
                mem[at - base:at - base + width] = (value & ((1 << 8 * width) - 1)).to_bytes(width, "little")
            i += n
        return None

    def frame(on):
        for name, master, words in cheats:
            if words and (master or name in on):
                why = run(words)
                if why:
                    bad.append(f"cheat {name}: {why}")
    switches = [name for name, master, words in cheats if words and not master]
    groups = {f"Map: hide {name}": set(types) for name, types in _map_icons.hide_types()}
    if sorted(switches) != sorted(groups):
        bad.append("the switches aren't one per group of icons")
    for on in [set(switches)] + [{s} for s in switches] + [set()]:
        frame(on)
        frame(on)
        want = set().union(*(groups.get(s, set()) for s in on))
        if {t for t in range(HIDE_SIZE) if mem[t]} != want or any(mem[HIDE_SIZE:]):
            bad.append(f"with {len(on)} switch(es) on the table doesn't hold just their icons")
            break
    return bad


def verify(patch, plan, romfs):
    """Reads the map tracker back from a built patch: every planned icon in its MapParam list, every flag it names an
    expression of the patch's GameDataList, and the code patch beside it. [problem]"""
    from romtools import Romfs, byml_load, murmur3_32
    rb = plan.get("_native_tracker") or {}
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    mp_rel = "Banc/BancBasedResource/MapParam.byml.zs"
    if not os.path.exists(os.path.join(patch, mp_rel)):
        return [f"map tracker: {mp_rel} not in the patch"]
    mp = byml_load(fs.read(mp_rel), allow_big=True)[0]
    from parity import _map_icons  # our icons (IconType 39 and up), when the plan has them
    n_icons = len(_map_icons.KEYS) if (plan.get("cosmetics") or {}).get("map_icons") else 0
    ICONS_FIRST = _map_icons.FIRST
    names = set()
    for path, want in (rb.get("lists") or {}).items():
        cur = mp
        for part in path.split("."):
            cur = cur[int(part)] if isinstance(cur, list) else (cur or {}).get(part)
        ours = [e for e in cur or [] if str(e.get("GameDataHashName", "")).startswith("RandoMap")]
        names |= {e["GameDataHashName"] for e in ours}
        if len(ours) != want:
            bad.append(f"map tracker: {path} has {len(ours)} icons, planned {want}")
        bad += [f"map tracker: {path}: IconType {e['IconType']}" for e in ours if not (0 < e["IconType"] < 35 or
                ICONS_FIRST <= e["IconType"] < ICONS_FIRST + n_icons)]
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    exps = {e["Hash"] for e in gd["Data"]["BoolExp"]}
    bad += [f"map tracker: no expression {n}" for n in sorted(names) if murmur3_32(n) not in exps]
    exe = os.path.join(os.path.dirname(os.path.abspath(patch)), "exefs", PATCH_FILE)
    if not os.path.exists(exe):
        bad.append(f"exefs/{PATCH_FILE}: not beside the patch")
    elif open(exe, encoding="utf-8").read() != pchtxt(rb.get("pool", VANILLA_N)):
        bad.append(f"exefs/{PATCH_FILE}: not the code patch this build makes")
    sw = os.path.join(os.path.dirname(os.path.abspath(patch)), "cheats", CHEATS_FILE)
    if not os.path.exists(sw):
        bad.append(f"cheats/{CHEATS_FILE}: the map switches aren't beside the patch")
    elif open(sw, encoding="utf-8").read() != cheats():
        bad.append(f"cheats/{CHEATS_FILE}: not the map switches this build makes")
    else:
        bad += [f"cheats/{CHEATS_FILE}: {x}" for x in cheats_problems(open(sw, encoding="utf-8").read())]
    bools = {e["Hash"] for e in gd["Data"]["Bool"]}
    got = plan.get("_native_tracker_got") or {}
    bad += [f"map tracker: got flag {f} ({loc}) has no save row" for loc, f in sorted(got.items())
            if murmur3_32(f) not in bools]
    if n_icons:  # the icons' frames and textures
        bad += ["map tracker: " + x for x in _map_icons.verify(patch, romfs)]
    sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
    import native_tracker  # the got flags' steps in the patched scenes
    bad += ["map tracker: " + x for x in native_tracker.verify_got(patch, plan, romfs)]
    return bad


def image_path(romfs):
    return os.path.join(os.path.dirname(os.path.normpath(romfs)), "image.bin")


def check_here():
    """check() on this PC's Longshot game when there is one, else []."""
    try:
        import romtools
        romfs = romtools.longshot_romfs()
    except Exception:  # noqa: BLE001
        return []
    path = image_path(romfs) if romfs else ""
    return check(path) if path and os.path.exists(path) else []
