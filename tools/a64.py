"""A small ARM64 assembler for Rando of Time's code patches (exefs .pchtxt files, see tools/rando/parity/_extras_wheel.py).

Only the instructions the patches use, each encoded by hand from the Arm A64 encoding tables. Every word gets checked
against a real disassembler while the patches are built and tested (capstone, outside the repo), so a wrong encoding
shows up before anything reaches the game.

Registers are written "x0".."x30", "w0".."w30", "sp", "xzr", "wzr". Branch targets are absolute addresses or labels.

    p = Program(0x83C661D0)
    p.label("loop"); p.op("ldrb", "w9", "x0", 0); p.op("cbz", "w9", "done"); ...
    words = p.assemble()   # [(address, u32), ...]
"""
import struct

COND = {"eq": 0, "ne": 1, "cs": 2, "hs": 2, "cc": 3, "lo": 3, "mi": 4, "pl": 5, "vs": 6, "vc": 7, "hi": 8, "ls": 9,
        "ge": 10, "lt": 11, "gt": 12, "le": 13, "al": 14}


class AsmError(ValueError):
    pass


def reg(r):
    """(number, is 64-bit) of a register name; sp and the zero register are both 31."""
    r = r.lower()
    if r in ("sp", "xzr"):
        return 31, True
    if r == "wzr" or r == "wsp":
        return 31, False
    if r[0] in "xw" and r[1:].isdigit() and 0 <= int(r[1:]) <= 30:
        return int(r[1:]), r[0] == "x"
    raise AsmError(f"not a register: {r}")


def _imm(v, bits, what, signed=False, scale=1):
    if v % scale:
        raise AsmError(f"{what}: {v} is not a multiple of {scale}")
    v //= scale
    lo, hi = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)
    if not lo <= v <= hi:
        raise AsmError(f"{what}: {v * scale} out of range")
    return v & ((1 << bits) - 1)


def encode(op, args, pc=0):
    """One instruction's u32. Branch args are absolute target addresses (pc is the instruction's own address)."""
    a = list(args)
    if op == "nop":
        return 0xD503201F
    if op == "pacibsp":                 # sign / check the return address with key B and sp, as the game's functions do
        return 0xD503237F
    if op == "retab":
        return 0xD65F0FFF
    if op == "madd":                    # madd xd, xn, xm, xa (xd = xn * xm + xa)
        d, x = reg(a[0])
        return 0x1B000000 | (x << 31) | (reg(a[2])[0] << 16) | (reg(a[3])[0] << 10) | (reg(a[1])[0] << 5) | d
    if op == "cmn":                     # cmn xn, #imm
        z = "xzr" if reg(a[0])[1] else "wzr"
        return encode("adds", [z, a[0], a[1]])
    if op == "ret":
        return 0xD65F03C0 | (reg(a[0])[0] << 5 if a else 30 << 5)
    if op in ("b", "bl"):
        off = _imm(a[0] - pc, 26, op, signed=True, scale=4)
        return (0x94000000 if op == "bl" else 0x14000000) | off
    if op.startswith("b.") and op[2:] in COND:
        return 0x54000000 | (_imm(a[0] - pc, 19, op, signed=True, scale=4) << 5) | COND[op[2:]]
    if op in ("cbz", "cbnz"):
        n, x = reg(a[0])
        return (0x34000000 | (x << 31) | ((op == "cbnz") << 24)
                | (_imm(a[1] - pc, 19, op, signed=True, scale=4) << 5) | n)
    if op in ("tbz", "tbnz"):           # tbz w21, #bit, target
        n, _ = reg(a[0])
        bit = _imm(a[1], 6, op)
        return (0x36000000 | ((bit >> 5) << 31) | ((op == "tbnz") << 24) | ((bit & 31) << 19)
                | (_imm(a[2] - pc, 14, op, signed=True, scale=4) << 5) | n)
    if op in ("movz", "movk"):          # movz w0, #imm16 [, lsl #16*hw]
        n, x = reg(a[0])
        shift = a[2] if len(a) > 2 else 0
        if shift % 16 or shift // 16 > (3 if x else 1):
            raise AsmError(f"{op}: bad shift {shift}")
        base = 0x52800000 if op == "movz" else 0x72800000
        return base | (x << 31) | ((shift // 16) << 21) | (_imm(a[1], 16, op) << 5) | n
    if op == "mov":                     # mov xd, xm (orr xd, xzr, xm) or mov xd, sp / mov sp, xm (add #0)
        d, x = reg(a[0])
        m, x2 = reg(a[1])
        if x != x2:
            raise AsmError("mov: mixed register widths")
        if a[0].lower() == "sp" or a[1].lower() == "sp":
            return encode("add", [a[0], a[1], 0])
        return 0x2A0003E0 | (x << 31) | (m << 16) | d
    if op in ("add", "sub", "adds", "subs"):   # add xd, xn, #imm12 [, lsl #12]  /  add xd, xn, xm [, lsl #s]
        d, x = reg(a[0])
        n, _ = reg(a[1])
        s = op in ("adds", "subs")
        sub = op.startswith("sub")
        if isinstance(a[2], int):
            sh = 1 if (len(a) > 3 and a[3] == 12) else 0
            return (0x11000000 | (x << 31) | (sub << 30) | (s << 29) | (sh << 22)
                    | (_imm(a[2], 12, op) << 10) | (n << 5) | d)
        m, _ = reg(a[2])
        lsl = a[3] if len(a) > 3 else 0
        return (0x0B000000 | (x << 31) | (sub << 30) | (s << 29) | (m << 16) | (_imm(lsl, 6, op) << 10)
                | (n << 5) | d)
    if op == "cmp":                     # cmp wn, #imm / cmp wn, wm
        z = "xzr" if reg(a[0])[1] else "wzr"
        return encode("subs", [z, a[0], a[1]] + a[2:])
    if op in ("ldr", "str", "ldrb", "strb", "ldrsw", "ldrh"):   # ldr xt, [xn, #imm] (unsigned scaled offset)
        t, x = reg(a[0])
        n, _ = reg(a[1])
        off = a[2] if len(a) > 2 else 0
        if op in ("ldrb", "strb"):
            size, opc = 0, (1 if op == "ldrb" else 0)
        elif op == "ldrh":
            size, opc = 1, 1
        elif op == "ldrsw":
            size, opc = 2, 2
        else:
            size, opc = (3 if x else 2), (1 if op == "ldr" else 0)
        return (0x39000000 | (size << 30) | (opc << 22) | (_imm(off, 12, op, scale=1 << size) << 10)
                | (n << 5) | t)
    if op in ("stp", "ldp"):            # stp x1, x2, [sp, #imm] with mode "pre" / "post" / "off"
        t1, x = reg(a[0])
        t2, _ = reg(a[1])
        n, _ = reg(a[2])
        off = a[3]
        mode = a[4] if len(a) > 4 else "off"
        idx = {"post": 0b001, "off": 0b010, "pre": 0b011}[mode]
        opc = 0b10 if x else 0b00
        return ((opc << 30) | (0b101 << 27) | (idx << 23) | ((op == "ldp") << 22)
                | (_imm(off, 7, op, signed=True, scale=8 if x else 4) << 15) | (t2 << 10) | (n << 5) | t1)
    if op == "adrp":
        d, _ = reg(a[0])
        imm = _imm((a[1] >> 12) - (pc >> 12), 21, op, signed=True)
        return 0x90000000 | ((imm & 3) << 29) | ((imm >> 2) << 5) | d
    if op in ("csel", "csinc"):         # csel wd, wn, wm, cond  /  csinc wd, wn, wm, cond (cond ? wn : wm + 1)
        d, x = reg(a[0])
        n, _ = reg(a[1])
        m, _ = reg(a[2])
        return (0x1A800000 | (x << 31) | (m << 16) | (COND[a[3]] << 12) | ((op == "csinc") << 10) | (n << 5)
                | d)
    if op == "lsr":                     # lsr wd, wn, #shift (ubfm)
        d, x = reg(a[0])
        n, _ = reg(a[1])
        top = 63 if x else 31
        return ((0xD3400000 if x else 0x53000000) | (_imm(a[2], 6 if x else 5, op) << 16) | (top << 10)
                | (n << 5) | d)
    if op == "and":                     # and wd, wn, #mask: a mask of the low k bits only (1 <= k < 32)
        d, x = reg(a[0])
        n, _ = reg(a[1])
        k = a[2].bit_length()
        if x or a[2] != (1 << k) - 1 or not 1 <= k < 32:
            raise AsmError(f"and: only a w register and a low-bits mask, not {a[2]:#x}")
        return 0x12000000 | ((k - 1) << 10) | (n << 5) | d
    raise AsmError(f"unknown instruction {op}")


class Program:
    """Instructions laid out from `base`; branch arguments may name labels."""

    def __init__(self, base):
        self.base, self.items, self.labels = base, [], {}

    @property
    def here(self):
        return self.base + 4 * len(self.items)

    def label(self, name):
        if name in self.labels:
            raise AsmError(f"label {name} twice")
        self.labels[name] = self.here

    def op(self, name, *args):
        self.items.append((name, args))

    def mov32(self, r, value):
        """movz + movk for a 32-bit constant."""
        self.op("movz", r, value & 0xFFFF)
        self.op("movk", r, value >> 16, 16)

    def assemble(self):
        out = []
        for k, (name, args) in enumerate(self.items):
            pc = self.base + 4 * k
            args = [self.labels[x] if isinstance(x, str) and x in self.labels else x for x in args]
            if any(isinstance(x, str) and x not in ("pre", "post", "off") and not x[0] in "xwsX" and x not in COND
                   for x in args):
                raise AsmError(f"{name} {args}: unknown label")
            out.append((pc, encode(name, args, pc)))
        return out


def words_bytes(words):
    return b"".join(struct.pack("<I", w) for _, w in words)
