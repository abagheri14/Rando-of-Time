"""The code patch behind remake_unequip_gear (OOTRR's unequip gear, which it couldn't do with data): in the Equipment
menu, picking the sword or shield you have on takes it off, and picking it again puts it back on.

How the menu picks gear (main = 0x80020000 + offset in image.bin, Longshot v3.2.0; parity/_extras_wheel.py has the
rest): its handler (PICK, 0x833DA470) reads the picked item's pouch category into [sp+0xC] (the order the game lists
them in: Weapon 0, Bow 1, Arrow 2, Shield 3, Armor 4, Material 5, KeyItem 6, Rupee 7, CureItem 8, HeadArmor 9, Boot
10). Head gear and boots (9, 10) toggle at TOGGLE: the one you have on is worn or taken off (SET_ACTIVE with the
slot's state flipped), anything else is put on. Every other category goes to EQUIP_PATH, which always puts the pick
on, so picking the sword you hold changes nothing.

The patch sends a sword or shield that's already the one you have on (IS_EQUIPPED) to the same toggle, so it comes
off and goes back on the way head gear does. Everything else goes where it went. The new code sits in the last bytes
of the zero padding after main's code (CAVE), which the D-pad wheel patch leaves alone (_extras_wheel.CAVE_END)."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
import a64  # noqa: E402

MAIN_BUILD_ID = "e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348"
IMAGE_BASE, MAIN_BASE = 0x80000000, 0x80020000
PATCH_FILE = "rando_of_time_unequip.pchtxt"
SITE = 0x833DA6C8        # sub w8, w1, #9: the handler's head-gear-or-boots test
TOGGLE = 0x833DA6D4      # head gear and boots: worn or taken off
EQUIP_PATH = 0x833DA740  # everything else: put it on
IS_EQUIPPED = 0x80A91080  # (pouch manager, &name) -> is it the gear chosen for its slot
CAVE, CAVE_END = 0x83C66FC0, 0x83C67000
WEAPON, SHIELD = 0, 3


def _vanilla_words():
    e = a64.encode
    return {SITE: e("sub", ["w8", "w1", 9]), SITE + 4: e("cmp", ["w8", 1]), SITE + 8: e("b.hi", [EQUIP_PATH], SITE + 8),
            TOGGLE: e("ldr", ["x0", "x22", 0])}


def _cave():
    p = a64.Program(CAVE)
    p.op("sub", "w8", "w1", 9)              # head gear and boots: the toggle, as before
    p.op("cmp", "w8", 1)
    p.op("b.hi", "u_other")
    p.op("b", TOGGLE)
    p.label("u_other")
    p.op("cbz", "w1", "u_check")            # a sword or a shield...
    p.op("cmp", "w1", SHIELD)
    p.op("b.eq", "u_check")
    p.op("b", EQUIP_PATH)
    p.label("u_check")
    p.op("ldr", "x0", "x22", 0)             # ...that's the one you have on goes to the toggle too
    p.op("sub", "x1", "x29", 0x10)
    p.op("bl", IS_EQUIPPED)
    p.op("ldr", "w1", "sp", 0xC)            # its category, where the toggle wants it
    p.op("tbnz", "w0", 0, "u_toggle")
    p.op("b", EQUIP_PATH)
    p.label("u_toggle")
    p.op("b", TOGGLE)
    words = p.assemble()
    if words[-1][0] + 4 > CAVE_END:
        raise a64.AsmError("the unequip code doesn't fit its end of the padding")
    return words


def writes():
    """[(address, new word)] of the whole patch."""
    return sorted(_cave() + [(SITE, a64.encode("b", [CAVE], SITE))])


def check(image_path):
    """Problems ([] when the patch fits this game): the handler's words as expected (or our branch, a game Longshot
    built with this patch before) and our end of the padding empty (or ours)."""
    if not os.path.exists(image_path):
        return [f"{image_path}: missing (build the game once in Longshot first)"]
    bad = []
    with open(image_path, "rb") as f:
        def word(a):
            f.seek(a - IMAGE_BASE)
            return struct.unpack("<I", f.read(4))[0]
        ours = word(SITE) == a64.encode("b", [CAVE], SITE)
        for a, want in sorted(_vanilla_words().items()):
            if word(a) != want and not (ours and a == SITE):
                bad.append(f"main+{a - MAIN_BASE:X}: {word(a):08X}, expected {want:08X} (another game build?)")
        f.seek(CAVE - IMAGE_BASE)
        cave = f.read(CAVE_END - CAVE)
        if not ours and cave != bytes(len(cave)):
            bad.append("the end of the padding after main's code isn't empty (another mod's code there?)")
    return bad


def pchtxt():
    """The IPSwitch text Longshot's Builder reads (offsets into main, offset_shift 0x100 cancels the NSO header)."""
    lines = [f"@nsobid-{MAIN_BUILD_ID}", "@flag offset_shift 0x100", "",
             "// Rando of Time: the Equipment menu takes off the sword or shield you pick again. Made by "
             "tools/rando/parity/_unequip_code.py.", "@enabled"]
    run, start = b"", None
    for a, w in writes() + [(None, 0)]:
        if run and (a is None or a != start + len(run)):
            lines.append(f"{start - MAIN_BASE:08X} {run.hex().upper()}")
            run, start = b"", None
        if a is not None:
            start = a if start is None else start
            run += struct.pack("<I", w)
    lines += ["@stop", ""]
    return "\n".join(lines)


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


def verify(patch):
    """[problem]: the code patch is beside the built patch, as this module makes it."""
    exe = os.path.join(os.path.dirname(os.path.abspath(patch)), "exefs", PATCH_FILE)
    if not os.path.exists(exe):
        return [f"exefs/{PATCH_FILE}: not beside the patch"]
    if open(exe, encoding="utf-8").read() != pchtxt():
        return [f"exefs/{PATCH_FILE}: not the code patch this build makes"]
    return []
