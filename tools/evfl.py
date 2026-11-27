"""Full reader and in-place editor for BFEVFL v4, the OoT remake's event flows.

The reader walks every structure and records each pointer slot it follows. `check()`
compares that set with the file's relocation table (RELT), which lists every pointer
in the file. If they match, the reader understands the whole file.

Edits happen in place. String pointers get repointed and integer fields (event next/case
targets, int/bool/float params) get overwritten. New strings are appended to the string
pool, which sits right before RELT and has no pointers in it. Structure never moves, so
every other pointer stays valid.
"""
import os
import struct

EVENT_SIZE = 0x30
ACTOR_SIZE = 0x38
ENTRY_SIZE = 0x20
EVENT_TYPES = {0: "action", 1: "switch", 2: "fork", 3: "join", 4: "subflow", 5: "subflow_switch", 6: "type6"}
# container item types
T_ARG, T_CONT, T_INT, T_BOOL, T_FLOAT, T_STR, T_WSTR, T_INTS, T_BOOLS, T_FLOATS, T_STRS, T_WSTRS, T_ACTOR = range(13)
_U16, _U32, _I32, _F32, _U64 = (struct.Struct(f).unpack_from for f in ("<H", "<I", "<i", "<f", "<Q"))
# make_patch and in_game_check often parse the same flows 2,200-3,700 times per run, so from the second parse on
# we cache a flow's parsed state, keyed by its BLAKE2b digest. The bytes stay out of the cache.
# Unpickling gives each EvflBuilder or EvflEditor its own mutable copy, with list and dict order kept.
# ptr_slots can come back in a different order. check() only uses it as a set, so sort it if a caller
# ever needs a fixed order.
# REMAKE_NO_CACHE=1 turns the cache off.
_EVFL_SEEN, _EVFL_MEMO = set(), {}
_EVFL_MEMO_ON = os.environ.get("REMAKE_NO_CACHE") != "1"


class Evfl:
    def __init__(self, data):
        self.d = bytes(data)
        key = None
        if _EVFL_MEMO_ON:
            import hashlib
            key = hashlib.blake2b(self.d, digest_size=20).digest()
            hit = _EVFL_MEMO.get(key)
            if hit is not None:
                import pickle
                self.__dict__.update(pickle.loads(hit))
                return
        self.ptr_slots = set()  # file offsets of every pointer the reader followed
        self.str_slots = {}     # pointer slot -> string it points to
        d = self.d
        assert d[:8] == b"BFEVFL\0\0", d[:8]
        self.version = d[8:12]
        self.reloc_off = self.u32(0x18)
        self.file_size = self.u32(0x1C)
        n_fc, n_tl = self.u16(0x20), self.u16(0x22)
        self.flowcharts, self.timelines = [], []
        fc_arr = self.ptr(0x28)
        self.dict_at(self.ptr(0x30))
        tl_arr = self.ptr(0x38)
        self.dict_at(self.ptr(0x40))
        for i in range(n_fc):
            self.flowcharts.append(self.flowchart(self.ptr(fc_arr + 8 * i)))
        for i in range(n_tl):
            self.timelines.append(self.timeline(self.ptr(tl_arr + 8 * i)))
        if key is not None:
            if key in _EVFL_SEEN:
                import pickle
                _EVFL_MEMO[key] = pickle.dumps({k: v for k, v in self.__dict__.items() if k != "d"},
                                               protocol=pickle.HIGHEST_PROTOCOL)
            else:
                _EVFL_SEEN.add(key)

    # Primitives
    # The formats are precompiled and sptr reads its pointer and string itself, because a file is millions of
    # these reads.
    def u16(self, o): return _U16(self.d, o)[0]
    def u32(self, o): return _U32(self.d, o)[0]
    def i32(self, o): return _I32(self.d, o)[0]
    def f32(self, o): return _F32(self.d, o)[0]

    def ptr(self, slot):
        v = _U64(self.d, slot)[0]
        self.ptr_slots.add(slot)
        return v

    def str_at(self, p):
        n = _U16(self.d, p)[0]
        return self.d[p + 2:p + 2 + n].decode("utf-8")

    def sptr(self, slot):
        d = self.d
        p = _U64(d, slot)[0]
        self.ptr_slots.add(slot)
        if not p:
            return None
        s = d[p + 2:p + 2 + _U16(d, p)[0]].decode("utf-8")
        self.str_slots[slot] = s
        return s

    def dict_at(self, p):
        if not p:
            return []
        assert self.d[p:p + 4] == b"DIC ", hex(p)
        n = self.u32(p + 4)
        sptr = self.sptr  # name pointer of entry i at p + 8 + 16 * i + 8, the root entry (index 0) is read, not kept
        return [sptr(p + 16 + 16 * i) for i in range(n + 1)][1:]

    # Containers
    def container(self, p):
        if not p:
            return None
        t, n = self.d[p], _U16(self.d, p + 2)[0]
        if t == T_CONT:
            names = self.dict_at(self.ptr(p + 8))
            items = {}
            ptr, container = self.ptr, self.container
            for i in range(n):
                child = container(ptr(p + 0x10 + 8 * i))
                if child is not None:
                    child["parent_slot"] = p + 0x10 + 8 * i  # where the container points at this item
                items[names[i]] = child
            return {"@": p, "type": "container", "items": items}
        v = p + 0x10
        if t in (T_ARG, T_STR, T_WSTR):
            return {"@": p, "slot": v, "type": {T_ARG: "argument", T_STR: "string", T_WSTR: "wstring"}[t],
                    "value": self.sptr(v)}
        if t in (T_STRS, T_WSTRS):
            return {"@": p, "slots": [v + 8 * i for i in range(n)], "type": "string_array",
                    "value": [self.sptr(v + 8 * i) for i in range(n)]}
        if t == T_INT:
            return {"@": p, "slot": v, "type": "int", "value": self.i32(v)}
        if t == T_BOOL:
            return {"@": p, "slot": v, "type": "bool", "value": self.u32(v) != 0, "raw": self.u32(v)}
        if t == T_FLOAT:
            return {"@": p, "slot": v, "type": "float", "value": self.f32(v)}
        if t == T_INTS:
            return {"@": p, "type": "int_array", "value": [self.i32(v + 4 * i) for i in range(n)]}
        if t == T_BOOLS:
            return {"@": p, "type": "bool_array", "value": [self.u32(v + 4 * i) != 0 for i in range(n)]}
        if t == T_FLOATS:
            return {"@": p, "slot": v, "type": "float_array", "value": [self.f32(v + 4 * i) for i in range(n)]}
        if t == T_ACTOR:
            return {"@": p, "slots": [v, v + 8], "type": "actor", "value": [self.sptr(v), self.sptr(v + 8)]}
        raise NotImplementedError(f"container item type {t} at {p:#x}")

    # Flowchart
    def flowchart(self, p):
        assert self.d[p:p + 4] == b"EVFL"
        n_actors, n_actions, n_queries, n_events, n_entries = struct.unpack_from("<5H", self.d, p + 0x10)
        fc = {"@": p, "name": self.sptr(p + 0x20), "actors": [], "events": [], "entry_points": {}}
        actors_p, events_p = self.ptr(p + 0x28), self.ptr(p + 0x30)
        ep_names = self.dict_at(self.ptr(p + 0x38))
        entries_p = self.ptr(p + 0x40)
        for i in range(n_actors):
            fc["actors"].append(self._actor(actors_p + ACTOR_SIZE * i))
        for i in range(n_events):
            e = events_p + EVENT_SIZE * i
            t = self.d[e + 8]
            ev = {"@": e, "idx": i, "name": self.sptr(e), "type": EVENT_TYPES[t]}
            if t == 0:
                ev.update(next=self.u16(e + 0x0A), actor=self.u16(e + 0x0C), action=self.u16(e + 0x0E),
                          params=self.container(self.ptr(e + 0x10)))
            elif t == 1:
                ncase = self.u16(e + 0x0A)
                ev.update(actor=self.u16(e + 0x0C), query=self.u16(e + 0x0E),
                          params=self.container(self.ptr(e + 0x10)))
                cp = self.ptr(e + 0x18)
                ev["cases"] = [{"@": cp + 8 * k, "value": self.u32(cp + 8 * k), "next": self.u16(cp + 8 * k + 4)}
                               for k in range(ncase)]
            elif t == 2:
                nf = self.u16(e + 0x0A)
                fp = self.ptr(e + 0x10)
                ev.update(join=self.u16(e + 0x0C), forks=[self.u16(fp + 2 * k) for k in range(nf)])
            elif t == 3:
                ev.update(next=self.u16(e + 0x0A))
            elif t == 4:
                ev.update(next=self.u16(e + 0x0A), params=self.container(self.ptr(e + 0x10)),
                          flowchart=self.sptr(e + 0x18), entry_point=self.sptr(e + 0x20))
            elif t == 5:
                ncase = self.u16(e + 0x0A)
                ev.update(params=self.container(self.ptr(e + 0x10)))
                cp = self.ptr(e + 0x18)
                ev["cases"] = [{"@": cp + 8 * k, "value": self.u32(cp + 8 * k), "next": self.u16(cp + 8 * k + 4)}
                               for k in range(ncase)]
                ev.update(flowchart=self.sptr(e + 0x20), entry_point=self.sptr(e + 0x28))
            elif t == 6:
                ev.update(next=self.u16(e + 0x0A), hash=self.u32(e + 0x0C))
            fc["events"].append(ev)
        for i in range(n_entries):
            e = entries_p + ENTRY_SIZE * i
            nsub, nvar, main = self.u16(e + 0x18), self.u16(e + 0x1A), self.u16(e + 0x1C)
            sp = self.ptr(e)
            var_names = self.dict_at(self.ptr(e + 8))
            vp = self.ptr(e + 0x10)
            variables = {}
            for k in range(nvar):
                variables[var_names[k]] = self._vardef(vp + 0x10 * k)
            fc["entry_points"][ep_names[i]] = {
                "@": e, "main": main, "sub_flow_events": [self.u16(sp + 2 * k) for k in range(nsub)],
                "variables": variables}
        return fc

    def _actor(self, a):
        na, nq = self.u16(a + 0x30), self.u16(a + 0x32)
        act_p, qry_p = self.ptr(a + 0x18), self.ptr(a + 0x20)
        return {
            "@": a,
            "name": self.sptr(a), "sub_name": self.sptr(a + 8), "argument": self.sptr(a + 0x10),
            "actions": [self.sptr(act_p + 8 * k) for k in range(na)],
            "queries": [self.sptr(qry_p + 8 * k) for k in range(nq)],
            "params": self.container(self.ptr(a + 0x28)),
            "entry_point_idx": self.u16(a + 0x34),
            "cut": self.d[a + 0x36],
        }

    def timeline(self, p):
        assert self.d[p:p + 4] == b"TLIN", hex(p)
        duration = self.f32(p + 0x10)
        n_act, n_actions, n_clips, n_oneshots, n_sub, n_cuts = struct.unpack_from("<6H", self.d, p + 0x14)
        tl = {"@": p, "name": self.sptr(p + 0x20), "duration": duration, "actors": [], "clips": [],
              "oneshots": [], "subtimelines": [], "cuts": []}
        actors_p, clips_p, one_p = self.ptr(p + 0x28), self.ptr(p + 0x30), self.ptr(p + 0x38)
        self.ptr(p + 0x40)  # triggers (plain data)
        sub_p, cuts_p = self.ptr(p + 0x48), self.ptr(p + 0x50)
        tl["params"] = self.container(self.ptr(p + 0x58))
        for i in range(n_act):
            tl["actors"].append(self._actor(actors_p + ACTOR_SIZE * i))
        for i in range(n_clips):
            c = clips_p + 0x18 * i
            tl["clips"].append({"@": c, "start": self.f32(c), "duration": self.f32(c + 4),
                                "actor": self.u16(c + 8), "action": self.u16(c + 0x0A),
                                "params": self.container(self.ptr(c + 0x10))})
        for i in range(n_oneshots):
            c = one_p + 0x18 * i
            tl["oneshots"].append({"@": c, "time": self.f32(c), "actor": self.u16(c + 4),
                                   "action": self.u16(c + 6), "params": self.container(self.ptr(c + 0x10))})
        for i in range(n_sub):
            tl["subtimelines"].append(self.sptr(sub_p + 8 * i))
        for i in range(n_cuts):
            c = cuts_p + 0x18 * i
            tl["cuts"].append({"@": c, "start": self.f32(c), "name": self.sptr(c + 8),
                               "params": self.container(self.ptr(c + 0x10))})
        return tl

    def _vardef(self, p):
        # variable definition: value (8 bytes: inline or pointer to array), count u16, type u16, pad
        n, t = self.u16(p + 8), self.u16(p + 0x0A)
        if n > 1 or t in (T_INTS, T_BOOLS, T_FLOATS):
            self.ptr(p)
        return {"@": p, "type": t, "count": n, "raw": self.d[p:p + 8].hex()}

    # Relocation check
    def relt_slots(self):
        r = self.reloc_off
        assert self.d[r:r + 4] == b"RELT"
        n_sec = self.u32(r + 8)
        slots = set()
        sec = r + 0x10
        entries = sec + 0x18 * n_sec
        for s in range(n_sec):
            base = struct.unpack_from("<Q", self.d, sec + 0x18 * s)[0]
            first, count = self.u32(sec + 0x18 * s + 0x10), self.u32(sec + 0x18 * s + 0x14)
            for k in range(first, first + count):
                off, mask = struct.unpack_from("<II", self.d, entries + 8 * k)
                for b in range(32):
                    if mask >> b & 1:
                        slots.add(base + off + 8 * b)
        return slots

    def check(self):
        """Returns (pointers in RELT the reader never followed, non-null pointers the reader followed that RELT lacks).
        Null pointers are relocated for some fields and not for others, so we don't compare them."""
        relt = self.relt_slots()
        unlisted = {s for s in self.ptr_slots - relt if struct.unpack_from("<Q", self.d, s)[0]}
        return relt - self.ptr_slots, unlisted

    # Nintendo's relocation rule, per structure. Some offsets are listed even when null ("always") and some
    # only when set ("if set"). Worked out from ~52,000 vanilla pointers, and tools/selftest.py checks every file.
    RELT_RULES = {
        "flowchart": ((0x20, 0x28, 0x30, 0x38, 0x40), ()),
        "actor": ((0x00, 0x08, 0x10, 0x18, 0x20), (0x28,)),
        "entry": ((0x00, 0x10), (0x08,)),
        "action": ((0x00,), (0x10,)),
        "switch": ((0x00, 0x18), (0x10,)),
        "fork": ((0x00, 0x10), ()),
        "join": ((0x00,), ()),
        "subflow": ((0x00, 0x18, 0x20), (0x10,)),
        "subflow_switch": ((0x00, 0x18, 0x20, 0x28), (0x10,)),
        "type6": ((0x00,), ()),
    }

    def relt_rule_violations(self):
        """[(structure, field offset, file offset, problem)] where the file breaks Nintendo's rule."""
        relt, out = self.relt_slots(), []

        def check(kind, base):
            always, if_set = self.RELT_RULES[kind]
            for o in always:
                if base + o not in relt:
                    out.append((kind, o, base + o, "not listed"))
            for o in if_set:
                listed, null = base + o in relt, struct.unpack_from("<Q", self.d, base + o)[0] == 0
                if listed == null:
                    out.append((kind, o, base + o, "listed but null" if listed else "set but not listed"))
        for fc in self.flowcharts:
            check("flowchart", fc["@"])
            for a in fc["actors"]:
                check("actor", a["@"])
            for e in fc["events"]:
                check(e["type"], e["@"])
            for ep in fc["entry_points"].values():
                check("entry", ep["@"])
        return out

    # Actions/queries helpers
    def calls(self):
        """Yield (flowchart, event, actor_name, action_or_query_name) for action and switch events."""
        for fc in self.flowcharts:
            for ev in fc["events"]:
                if ev["type"] == "action":
                    a = fc["actors"][ev["actor"]]
                    yield fc, ev, a["name"], a["actions"][ev["action"]]
                elif ev["type"] == "switch":
                    a = fc["actors"][ev["actor"]]
                    yield fc, ev, a["name"], a["queries"][ev["query"]]


class EvflEditor:
    """Apply in-place edits to a BFEVFL file. New strings go at the end of the string pool."""

    def __init__(self, data):
        self.ev = Evfl(data)
        self.buf = bytearray(data)
        d = self.buf
        owner = (self.ev.flowcharts or self.ev.timelines)[0]["@"]
        self.pool = owner + struct.unpack_from("<I", d, owner + 4)[0]
        assert d[self.pool:self.pool + 4] == b"STR "
        self.n_strings = struct.unpack_from("<I", d, self.pool + 0x10)[0]
        self.existing = {}
        p = self.pool + 0x14
        for _ in range(self.n_strings + 1):  # the count leaves out the leading empty string
            n = struct.unpack_from("<H", d, p)[0]
            self.existing.setdefault(d[p + 2:p + 2 + n].decode("utf-8"), p)
            p += 2 + n + 1
            p += p & 1
        self.pool_end = p
        assert self.pool_end <= self.ev.reloc_off
        self.new_strings = []  # (string, offset relative to pool_end)
        self.new_len = 0

    def _string_ptr(self, s):
        if s in self.existing:
            return self.existing[s]
        raw = s.encode("utf-8")
        rec = struct.pack("<H", len(raw)) + raw + b"\0"
        if len(rec) & 1:
            rec += b"\0"
        off = self.pool_end + self.new_len
        self.new_strings.append(rec)
        self.new_len += len(rec)
        self.existing[s] = off
        return off

    def set_string(self, slot, s):
        assert slot in self.ev.str_slots, f"{slot:#x} is not a string pointer"
        struct.pack_into("<Q", self.buf, slot, self._string_ptr(s))

    def set_u16(self, off, v):
        struct.pack_into("<H", self.buf, off, v)

    def set_int(self, slot, v):
        struct.pack_into("<i", self.buf, slot, v)

    def set_float(self, slot, v):
        struct.pack_into("<f", self.buf, slot, v)

    def build(self):
        if not self.new_strings:
            return bytes(self.buf)
        d = self.buf
        reloc = self.ev.reloc_off
        added = b"".join(self.new_strings)
        # pad the inserted block so RELT stays 8-aligned
        new_pool_end = self.pool_end + len(added)
        new_reloc = (new_pool_end + 7) & ~7
        out = bytearray(d[:self.pool_end]) + added + bytes(new_reloc - new_pool_end) + d[reloc:]
        struct.pack_into("<I", out, self.pool + 0x10, self.n_strings + len(self.new_strings))
        struct.pack_into("<I", out, 0x18, new_reloc)
        struct.pack_into("<I", out, 0x1C, len(out))
        struct.pack_into("<I", out, new_reloc + 4, new_reloc)
        n_sec = struct.unpack_from("<I", out, new_reloc + 8)[0]
        for s in range(n_sec):
            sec = new_reloc + 0x10 + 0x18 * s
            off, size = struct.unpack_from("<II", out, sec + 8)
            if off + size == self.pool_end:
                # the section ends where the string pool ends, so it grows with the pool
                struct.pack_into("<I", out, sec + 0x0C, size + len(added))
        return bytes(out)
