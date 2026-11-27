"""Adds new steps (actions, branches, parallel steps, sub-flow calls), entry points, actions and queries
to a BFEVFL event flow.

The layout matches Nintendo's files. New structures (event arrays, entry-point arrays, parameter
containers, name dictionaries) go after the original structures. Then comes the string pool, moved down
with every pointer into it shifted and new strings appended, and then a regenerated relocation table.
The flowchart header gets repointed at the grown arrays.

The structures they replace get cut out of the file: the old event and entry-point arrays, the
entry-point dictionary, an actor's old action/query list, an entry's old sub-flow list and a text
parameter's old item. Every pointer and relocation entry moves with the bytes after them, so a file
only carries one copy of each. The game loads the whole file with its scene, and without the cuts a step
added to Get_Epona's 594 leaves 28 KB behind on every pass. A structure only gets cut when nothing points
into it any more.

The name dictionary (DIC, a Patricia trie) and relocation table (RELT) builders are checked
against every existing one in the game by tools/selftest.py.
"""
import bisect
import struct

from evfl import Evfl, ACTOR_SIZE, EVENT_SIZE, ENTRY_SIZE, T_ARG, T_CONT, T_INT, T_BOOL, T_FLOAT, T_STR, T_FLOATS

# Name dictionary (DIC)


def _bit(key, bit):
    i = bit >> 3
    if i >= len(key):
        return 0
    return (key[len(key) - 1 - i] >> (bit & 7)) & 1


def dic_tree(names):
    """[(bit, left, right)] for the root and each name, in file order (Nintendo ResDic)."""
    nodes = [[-1, 0, 0, b""]]
    for idx, s in enumerate(names, 1):
        key = s.encode("utf-8")
        p, x = 0, nodes[0][1]
        while nodes[p][0] < nodes[x][0]:
            p, x = x, (nodes[x][2] if _bit(key, nodes[x][0]) else nodes[x][1])
        other = nodes[x][3]
        b, top = 0, max(len(key), len(other)) * 8
        while b < top and _bit(key, b) == _bit(other, b):
            b += 1
        p, x = 0, nodes[0][1]
        while nodes[p][0] < nodes[x][0] < b:
            p, x = x, (nodes[x][2] if _bit(key, nodes[x][0]) else nodes[x][1])
        node = [b, x, idx, key] if _bit(key, b) else [b, idx, x, key]
        nodes.append(node)
        if p == 0:
            nodes[0][1] = idx
        elif _bit(key, nodes[p][0]):
            nodes[p][2] = idx
        else:
            nodes[p][1] = idx
    return [(n[0], n[1], n[2]) for n in nodes]


def dic_bytes(names):
    """DIC body with the name pointers left as 0. Returns the bytes and the name for each entry."""
    tree = dic_tree(names)
    out = bytearray(b"DIC " + struct.pack("<I", len(names)))
    for bit, left, right in tree:
        out += struct.pack("<IHHQ", bit & 0xFFFFFFFF, left, right, 0)
    return bytes(out), [""] + list(names)


# Relocation table (RELT)


def relt_entries(slots):
    slots = sorted(slots)
    entries, i = [], 0
    while i < len(slots):
        base, mask, j = slots[i], 0, i
        while j < len(slots) and slots[j] < base + 256 and (slots[j] - base) % 8 == 0:
            mask |= 1 << ((slots[j] - base) // 8)
            j += 1
        entries.append((base, mask))
        i = j
    return entries


def relt_bytes(slots, relt_off, data_end):
    entries = relt_entries(slots)
    out = bytearray(b"RELT" + struct.pack("<III", relt_off, 1, 0))
    out += struct.pack("<QIIII", 0, 0, data_end, 0, len(entries))
    for off, mask in entries:
        out += struct.pack("<II", off, mask)
    return bytes(out)


# Builder


class EvflBuilder:
    STR, BLOCK, ABS = "str", "block", "abs"

    def __init__(self, data):
        self.ev = Evfl(data)
        self.buf = bytearray(data)
        self.relt_slots = self.ev.relt_slots()
        owner = (self.ev.flowcharts or self.ev.timelines)[0]["@"]
        self.pool = owner + struct.unpack_from("<I", data, owner + 4)[0]
        self.n_strings = struct.unpack_from("<I", data, self.pool + 0x10)[0]
        self.strings = {}
        p = self.pool + 0x14
        for _ in range(self.n_strings + 1):
            n = struct.unpack_from("<H", data, p)[0]
            self.strings.setdefault(data[p + 2:p + 2 + n].decode("utf-8"), p)
            p += 2 + n + 1
            p += p & 1
        self.pool_end = p
        self.new_strings = bytearray()
        self.block = bytearray()
        self.fixups = []  # (where: "main"|"block", offset, kind, target)
        self._pending = {}  # flowchart name -> additions written by build()
        self._shared = {}  # parameter blocks of nodes marked "share", one block per distinct parameter set
        self.replaced = []  # (offset, size) of original structures this build replaces, build() cuts them out

    # Strings and pointers
    def _str(self, s):
        if s not in self.strings:
            raw = s.encode("utf-8")
            rec = struct.pack("<H", len(raw)) + raw + b"\0"
            rec += b"\0" * (len(rec) & 1)
            self.strings[s] = ("new", len(self.new_strings))
            self.new_strings += rec
        return self.strings[s]

    def _ptr(self, where, off, kind, target):
        self.fixups.append((where, off, kind, target))

    def _alloc(self, size, align=8):
        while len(self.block) % align:
            self.block.append(0)
        off = len(self.block)
        self.block += bytes(size)
        return off

    # Parameter containers
    def _string_item(self, t, text):
        """A string/argument item laid out like Nintendo's. The text sits right after the item
        (u16 length, bytes, NUL) and the item's pointer points at it."""
        raw = text.encode("utf-8")
        rec = struct.pack("<H", len(raw)) + raw + b"\0"
        it = self._alloc(0x18 + ((len(rec) + 7) & ~7))
        struct.pack_into("<BBH", self.block, it, t, 0, 1)
        self.block[it + 0x18:it + 0x18 + len(rec)] = rec
        self._ptr("block", it + 0x10, self.BLOCK, it + 0x18)
        return it

    def set_string_param(self, item, text, as_string=False):
        """Changes a string/argument parameter of an existing event. It makes a fresh item with the text inline
        and repoints the parent container at it (build() cuts the old item out). as_string turns an argument
        reference into a plain string value."""
        t = T_STR if as_string else {"string": T_STR, "argument": T_ARG}[item["type"]]
        new = self._string_item(t, text)
        self._ptr("main", item["parent_slot"], self.BLOCK, new)
        old, d = item["@"], self.ev.d
        text_at = struct.unpack_from("<Q", d, old + 0x10)[0]
        inline = (2 + struct.unpack_from("<H", d, text_at)[0] + 1 + 7) & ~7 if text_at == old + 0x18 else 0
        self.replaced.append((old, 0x18 + inline))

    def container(self, params, base=None):
        """params is {name: value}, and a value can be a bool, int, float, str, {"arg": name} or [floats].
        With base (an evfl.Evfl container model) the block copies base. Its items that params doesn't name point
        at the original item blocks (any type, e.g. actor references), and params replace or add values."""
        names = list(base["items"]) if base else []
        names += [k for k in params if k not in names]
        n = len(names)
        c = self._alloc(0x10 + 8 * n)
        struct.pack_into("<BBH", self.block, c, T_CONT, 0, n)
        dic, dic_names = dic_bytes(names)
        d = self._alloc(len(dic))
        self.block[d:d + len(dic)] = dic
        self._ptr("block", c + 8, self.BLOCK, d)
        for i, nm in enumerate(dic_names):
            self._ptr("block", d + 8 + 16 * i + 8, self.STR, nm)
        for i, nm in enumerate(names):
            if nm not in params:
                self._ptr("block", c + 0x10 + 8 * i, self.ABS, base["items"][nm]["@"])
                continue
            v = params[nm]
            if isinstance(v, dict) and "arg" in v:
                it = self._string_item(T_ARG, v["arg"])
            elif isinstance(v, bool):
                it = self._alloc(0x18)
                struct.pack_into("<BBHII", self.block, it, T_BOOL, 0, 1, 0, 0)
                struct.pack_into("<I", self.block, it + 0x10, 0x80000001 if v else 0)
            elif isinstance(v, int):
                it = self._alloc(0x18)
                struct.pack_into("<BBH", self.block, it, T_INT, 0, 1)
                struct.pack_into("<i", self.block, it + 0x10, v)
            elif isinstance(v, float):
                it = self._alloc(0x18)
                struct.pack_into("<BBH", self.block, it, T_FLOAT, 0, 1)
                struct.pack_into("<f", self.block, it + 0x10, v)
            elif isinstance(v, str):
                it = self._string_item(T_STR, v)
            elif isinstance(v, list):
                it = self._alloc(0x10 + ((4 * len(v) + 7) & ~7))
                struct.pack_into("<BBH", self.block, it, T_FLOATS, 0, len(v))
                for k, f in enumerate(v):
                    struct.pack_into("<f", self.block, it + 0x10 + 4 * k, float(f))
            else:
                raise TypeError(f"parameter {nm}: unsupported value {v!r}")
            self._ptr("block", c + 0x10 + 8 * i, self.BLOCK, it)
        return c

    # Flowchart edits
    # Additions are collected per flowchart and build() writes them once, so one flowchart can get several entry
    # points, actions and queries. Pointer slots follow Nintendo's relocation rule (checked on ~52,000 vanilla
    # pointers). Array pointers (actor actions/queries, entry sub-flow list and variables, switch cases, fork
    # targets) are listed even when null. Parameter blocks and the entry variable dictionary are only listed
    # when set. Copied structures keep the original listing, nulls included.
    def flowchart(self, name):
        for fc in self.ev.flowcharts:
            if fc["name"] == name:
                return fc
        raise KeyError(name)

    def _pend(self, fc):
        p = self._pending.get(fc["name"])
        if p is None:
            p = self._pending[fc["name"]] = {"fc": fc, "events": [], "entries": [], "actors": {},
                                             "n_actions": {}, "n_queries": {}, "sub_flows": {}, "new_actors": []}
        return p

    def set_sub_flows(self, fc, entry_name, events):
        """Rewrites an existing entry point's sub-flow list, the call steps it reaches (sub_flow_order)."""
        self._pend(fc)["sub_flows"][entry_name] = list(events)

    def _actor_member(self, fc, actor_name, member, kind, sub_name="", new_ok=False):
        for ai, a in enumerate(fc["actors"]):
            if a["name"] == actor_name and (a["sub_name"] or "") == sub_name:
                if member in a[kind]:
                    return ai, a[kind].index(member)
                if not a.get("new"):  # a new actor's lists are written whole in _finalize
                    p = self._pend(fc)
                    p["n_" + kind].setdefault(ai, len(a[kind]))  # how many the file has
                    p["actors"].setdefault(ai, {"actions": [], "queries": []})[kind].append(member)
                a[kind].append(member)
                return ai, len(a[kind]) - 1
        if not new_ok:
            raise KeyError(f"no actor {actor_name}[{sub_name}] in {fc['name']}")
        a = {"@": None, "name": actor_name, "sub_name": sub_name, "argument": "", "actions": [], "queries": [],
             "new": True}
        fc["actors"].append(a)
        self._pend(fc)["new_actors"].append(a)
        a[kind].append(member)
        return len(fc["actors"]) - 1, 0

    def ensure_action(self, fc, actor_name, action, sub_name="", new_ok=False):
        """Returns (actor index, action index) and adds the action to the actor's list if it's missing. new_ok: an
        actor the flowchart lacks is added (_finalize writes it with the member settings of the flowchart's
        GameSystemActor, or its first actor)."""
        return self._actor_member(fc, actor_name, action, "actions", sub_name, new_ok)

    def ensure_query(self, fc, actor_name, query, sub_name="", new_ok=False):
        """Returns (actor index, query index) and adds the query to the actor's list if it's missing (new_ok: as
        ensure_action)."""
        return self._actor_member(fc, actor_name, query, "queries", sub_name, new_ok)

    def add_graph(self, fc, entry_name, nodes, start, entry=True):
        """Adds an entry point that runs a graph of new steps. `nodes` maps a label to one of these:
             {"actor": A, "action": X, "params": {...}, "next": T}               (sub_name optional; "new_actor":
                                                 True adds the actor when the flowchart has none of that name)
             {"call": "File:Entry" or ":Entry", "params": {...}, "next": T}
             {"actor": A, "query": Q, "params": {...}, "cases": {value: T, ...}}   (a branch)
             {"fork": [T, ...], "join": label}                                    (run branches together)
             {"join": True, "next": T}
             "share": True on a node with "params": its parameter block is shared with every other such node
                                                 of this build that has the same parameters (smaller files)
             {"copy": "EventName", ...routing}   an existing step's actor, action/query/call and its exact
                                                 parameter block, with new routing ("next", "cases" or
                                                 "fork"+"join"); a copied call may be retargeted with "call";
                                                 "params_over": {name: value} keeps the block but replaces values
           T is another label, "@EventName" (an existing step), or None (end).
           entry=False: the steps only (named entry_name_<label>), no entry point runs them.
           Returns {label: event index}."""
        p = self._pend(fc)
        if entry and (entry_name in fc["entry_points"] or any(e[0] == entry_name for e in p["entries"])):
            raise ValueError(f"entry point {entry_name} already exists in {fc['name']}")
        base = len(fc["events"]) + len(p["events"])
        labels = list(nodes)
        idx = {lab: base + i for i, lab in enumerate(labels)}
        existing = {e["name"]: e["idx"] for e in fc["events"]}
        by_name = {e["name"]: e for e in fc["events"]}

        def tgt(t):
            if t is None:
                return 0xFFFF
            if isinstance(t, str) and t.startswith("@"):
                return existing[t[1:]]
            return idx[t]

        for lab in labels:
            n = nodes[lab]
            rec = {"name": f"{entry_name}_{lab}", "params": None}
            if n.get("params") and n.get("share"):  # read-only blocks, so steps with the same parameters share one
                key = repr(sorted(n["params"].items(), key=lambda kv: kv[0]))
                if key not in self._shared:
                    self._shared[key] = self.container(n["params"])
                rec["params"] = self._shared[key]
            elif n.get("params"):
                rec["params"] = self.container(n["params"])
            if "params_over" in n:  # a copied step's own parameter block with some values replaced
                if "copy" not in n or not by_name[n["copy"]].get("params"):
                    raise ValueError(f"{lab}: params_over needs a copied step that has parameters")
                rec["params"] = self.container(n["params_over"], base=by_name[n["copy"]]["params"])
            if "copy" in n:
                self._copy_node(rec, n, by_name[n["copy"]], tgt)
            elif "call" in n:
                fcn, _, ep = n["call"].partition(":")
                rec.update(type=4, next=tgt(n.get("next")), fcn=fcn, ep=ep)
            elif "query" in n:
                ai, qi = self.ensure_query(fc, n["actor"], n["query"], n.get("sub_name", ""), n.get("new_actor", False))
                rec.update(type=1, actor=ai, query=qi, cases=[(int(v), tgt(t)) for v, t in n["cases"].items()])
            elif "fork" in n:
                rec.update(type=2, forks=[tgt(t) for t in n["fork"]], join=tgt(n["join"]))
            elif n.get("join") is True:
                rec.update(type=3, next=tgt(n.get("next")))
            else:
                ai, ac = self.ensure_action(fc, n["actor"], n["action"], n.get("sub_name", ""), n.get("new_actor", False))
                rec.update(type=0, next=tgt(n.get("next")), actor=ai, action=ac)
            p["events"].append(rec)
        subs = [idx[lab] for lab in labels if "call" in nodes[lab]
                or ("copy" in nodes[lab] and by_name[nodes[lab]["copy"]]["type"] == "subflow")]
        if entry:
            p["entries"].append((entry_name, idx[start], subs))
        return idx

    def _copy_node(self, rec, n, e, tgt):
        """Fills `rec` from the existing event `e` (an evfl.Evfl model), routed the way node `n` says."""
        if rec["params"] is None:
            rec["params_abs"] = struct.unpack_from("<Q", self.ev.d, e["@"] + 0x10)[0] if e["type"] != "join" else 0
        t = e["type"]
        if t == "action":
            rec.update(type=0, next=tgt(n.get("next")), actor=e["actor"], action=e["action"])
        elif t == "switch":
            rec.update(type=1, actor=e["actor"], query=e["query"],
                       cases=[(int(v), tgt(x)) for v, x in n["cases"].items()])
        elif t == "fork":
            rec.update(type=2, forks=[tgt(x) for x in n["fork"]], join=tgt(n["join"]))
            rec["params_abs"] = 0
        elif t == "join":
            rec.update(type=3, next=tgt(n.get("next")))
        elif t == "subflow":
            fcn, ep = (n["call"].partition(":")[::2]) if "call" in n else (e.get("flowchart") or "", e["entry_point"])
            rec.update(type=4, next=tgt(n.get("next")), fcn=fcn, ep=ep)
        else:
            raise ValueError(f"copying a {t} step ({e['name']}) is not supported")

    def add_chain(self, fc, entry_name, steps):
        """Adds an entry point that runs `steps` in order (each one an action or a {"call": ...} step)."""
        nodes = {}
        for i, st in enumerate(steps):
            nodes[f"s{i}"] = dict(st, next=(f"s{i + 1}" if i + 1 < len(steps) else None))
        return self.add_graph(fc, entry_name, nodes, "s0")["s0"]

    def _copy_listed(self, dst, src, size):
        """Copies `size` bytes of an original structure to block offset dst. Its pointer slots stay listed for
        relocation the way they were in the original, null ones too."""
        self.block[dst:dst + size] = self.ev.d[src:src + size]
        for f in range(0, size, 8):
            if src + f in self.relt_slots:
                v = struct.unpack_from("<Q", self.ev.d, src + f)[0]
                struct.pack_into("<Q", self.block, dst + f, 0)
                self._ptr("block", dst + f, self.ABS, v)

    def _array_ptr(self, off, items, write):
        """Allocates an array of `items` (if there are any) and points block offset `off` at it. The slot is listed
        even when it's empty."""
        if items:
            self._ptr("block", off, self.BLOCK, write(items))
        else:
            self._ptr("block", off, self.ABS, 0)

    def _array_ptr_main(self, off, items):
        """Same as _array_ptr, for a pointer slot in the original structures."""
        if items:
            self._ptr("main", off, self.BLOCK, self._write_u16s(items))
        else:
            self._ptr("main", off, self.ABS, 0)

    def _write_u16s(self, values):
        c = self._alloc(2 * len(values))
        for k, v in enumerate(values):
            struct.pack_into("<H", self.block, c + 2 * k, v)
        return c

    def _write_cases(self, cases):
        c = self._alloc(8 * len(cases))
        for k, (val, nxt) in enumerate(cases):
            struct.pack_into("<IHH", self.block, c + 8 * k, val & 0xFFFFFFFF, nxt, 0)
        return c

    def _finalize(self):
        for p in self._pending.values():
            fc = p["fc"]
            f = fc["@"]
            if p["sub_flows"] and (p["events"] or p["entries"]):
                raise ValueError("set_sub_flows runs in a pass of its own (sync_sub_flows)")
            for name, subs in p["sub_flows"].items():  # in the file's own entry records
                e = fc["entry_points"][name]["@"]
                old, n_old = struct.unpack_from("<Q", self.ev.d, e)[0], struct.unpack_from("<H", self.ev.d, e + 0x18)[0]
                if old and n_old:
                    self.replaced.append((old, 2 * n_old))
                self._array_ptr_main(e, subs)
                struct.pack_into("<H", self.buf, e + 0x18, len(subs))
            # actors: new ones (the flowchart's actor array copied with the new records after it), then grown action /
            # query lists, written into the copy when the array moved
            new = p["new_actors"]
            n_file_actors = struct.unpack_from("<H", self.ev.d, f + 0x10)[0]
            moved = None
            if new:
                old_arr = struct.unpack_from("<Q", self.ev.d, f + 0x28)[0]
                moved = self._alloc(ACTOR_SIZE * (n_file_actors + len(new)))
                if n_file_actors:
                    self._copy_listed(moved, old_arr, ACTOR_SIZE * n_file_actors)
                    self.replaced.append((old_arr, ACTOR_SIZE * n_file_actors))
                base = next((a for a in fc["actors"][:n_file_actors] if a["name"] == "GameSystemActor"),
                            fc["actors"][0] if n_file_actors else None)
                settings = struct.unpack_from("<Q", self.ev.d, base["@"] + 0x28)[0] if base else 0
                for j, a in enumerate(new):
                    r = moved + ACTOR_SIZE * (n_file_actors + j)
                    self._ptr("block", r, self.STR, a["name"])
                    self._ptr("block", r + 8, self.STR, a["sub_name"] or "")
                    self._ptr("block", r + 0x10, self.STR, a["argument"] or "")
                    for kind, ptr_off, cnt_off, hdr_off in (("actions", 0x18, 0x30, 0x12), ("queries", 0x20, 0x32, 0x14)):
                        names = a[kind]
                        if names:
                            arr = self._alloc(8 * len(names))
                            for k, name in enumerate(names):
                                self._ptr("block", arr + 8 * k, self.STR, name)
                            self._ptr("block", r + ptr_off, self.BLOCK, arr)
                        else:
                            self._ptr("block", r + ptr_off, self.ABS, 0)
                        struct.pack_into("<H", self.block, r + cnt_off, len(names))
                        tot = struct.unpack_from("<H", self.buf, f + hdr_off)[0]
                        struct.pack_into("<H", self.buf, f + hdr_off, tot + len(names))
                    if settings:
                        self._ptr("block", r + 0x28, self.ABS, settings)
                    struct.pack_into("<HBB", self.block, r + 0x34, 0xFFFF, 1, 0)  # no entry point, cut 1 (as vanilla)
                self._ptr("main", f + 0x28, self.BLOCK, moved)
                struct.pack_into("<H", self.buf, f + 0x10, n_file_actors + len(new))
            for ai, adds in p["actors"].items():
                a = fc["actors"][ai]
                for kind, ptr_off, cnt_off, hdr_off in (("actions", 0x18, 0x30, 0x12), ("queries", 0x20, 0x32, 0x14)):
                    if not adds[kind]:
                        continue
                    n_file = p["n_" + kind][ai]
                    old = struct.unpack_from("<Q", self.ev.d, a["@"] + ptr_off)[0]
                    arr = self._alloc(8 * (n_file + len(adds[kind])))
                    for k in range(n_file):
                        self._ptr("block", arr + 8 * k, self.ABS, struct.unpack_from("<Q", self.ev.d, old + 8 * k)[0])
                    for k, name in enumerate(adds[kind]):
                        self._ptr("block", arr + 8 * (n_file + k), self.STR, name)
                    if moved is None:
                        self._ptr("main", a["@"] + ptr_off, self.BLOCK, arr)
                        struct.pack_into("<H", self.buf, a["@"] + cnt_off, n_file + len(adds[kind]))
                    else:  # the record's copy: drop the slot _copy_listed listed, then point it at the new list
                        r = moved + ACTOR_SIZE * ai
                        self.fixups = [x for x in self.fixups if not (x[0] == "block" and x[1] == r + ptr_off)]
                        self._ptr("block", r + ptr_off, self.BLOCK, arr)
                        struct.pack_into("<H", self.block, r + cnt_off, n_file + len(adds[kind]))
                    if old and n_file:
                        self.replaced.append((old, 8 * n_file))
                    tot = struct.unpack_from("<H", self.buf, f + hdr_off)[0]
                    struct.pack_into("<H", self.buf, f + hdr_off, tot + len(adds[kind]))
            if not p["events"] and not p["entries"]:
                continue
            # events: original array copied, new steps appended
            n_old, recs = len(fc["events"]), p["events"]
            old_arr = struct.unpack_from("<Q", self.ev.d, f + 0x30)[0]
            arr = self._alloc(EVENT_SIZE * (n_old + len(recs)))
            if n_old:
                self._copy_listed(arr, old_arr, EVENT_SIZE * n_old)
                self.replaced.append((old_arr, EVENT_SIZE * n_old))
            for i, r in enumerate(recs):
                e = arr + EVENT_SIZE * (n_old + i)
                self._ptr("block", e, self.STR, r["name"])
                t = r["type"]
                if t == 0:
                    struct.pack_into("<BBHHH", self.block, e + 8, 0, 0, r["next"], r["actor"], r["action"])
                elif t == 1:
                    struct.pack_into("<BBHHH", self.block, e + 8, 1, 0, len(r["cases"]), r["actor"], r["query"])
                    self._array_ptr(e + 0x18, r["cases"], self._write_cases)
                elif t == 2:
                    struct.pack_into("<BBHH", self.block, e + 8, 2, 0, len(r["forks"]), r["join"])
                    self._array_ptr(e + 0x10, r["forks"], self._write_u16s)
                elif t == 3:
                    struct.pack_into("<BBH", self.block, e + 8, 3, 0, r["next"])
                elif t == 4:
                    struct.pack_into("<BBH", self.block, e + 8, 4, 0, r["next"])
                    self._ptr("block", e + 0x18, self.STR, r["fcn"])
                    self._ptr("block", e + 0x20, self.STR, r["ep"])
                if r["params"] is not None and t != 2:
                    self._ptr("block", e + 0x10, self.BLOCK, r["params"])
                elif r.get("params_abs") and t != 2:  # a copied step keeps its original parameter block
                    self._ptr("block", e + 0x10, self.ABS, r["params_abs"])
            self._ptr("main", f + 0x30, self.BLOCK, arr)
            struct.pack_into("<H", self.buf, f + 0x16, n_old + len(recs))
            if not p["entries"]:
                continue
            # entry points: original array copied, new ones appended, dictionary rebuilt
            names = list(fc["entry_points"])
            n_ep = len(names)
            old_ep = struct.unpack_from("<Q", self.ev.d, f + 0x40)[0]
            eps = self._alloc(ENTRY_SIZE * (n_ep + len(p["entries"])))
            if n_ep:
                self._copy_listed(eps, old_ep, ENTRY_SIZE * n_ep)
                self.replaced.append((old_ep, ENTRY_SIZE * n_ep))
            old_dic = struct.unpack_from("<Q", self.ev.d, f + 0x38)[0]
            if old_dic:
                self.replaced.append((old_dic, 8 + 16 * (n_ep + 1)))
            for k, (name, main, subs) in enumerate(p["entries"]):
                e = eps + ENTRY_SIZE * (n_ep + k)
                self._array_ptr(e, subs, self._write_u16s)        # sub-flow steps: listed even if none
                self._ptr("block", e + 0x10, self.ABS, 0)          # variables: none, listed like vanilla
                struct.pack_into("<HHHH", self.block, e + 0x18, len(subs), 0, main, 0)
                names.append(name)
            dic, dic_names = dic_bytes(names)
            d = self._alloc(len(dic))
            self.block[d:d + len(dic)] = dic
            for i, nm in enumerate(dic_names):
                self._ptr("block", d + 8 + 16 * i + 8, self.STR, nm)
            self._ptr("main", f + 0x38, self.BLOCK, d)
            self._ptr("main", f + 0x40, self.BLOCK, eps)
            struct.pack_into("<H", self.buf, f + 0x18, len(names))
        self._pending = {}

    # Rebuild the file
    def _cuts(self):
        """[(start, end)] of the replaced structures to cut out. These are 8-aligned spans (an old list's padding up
        to the next 8 bytes included) that no remaining pointer, relocation slot or write reaches into. A span
        something still reaches stays as it is, so the file is still right, just bigger."""
        d, pool = self.buf, self.pool
        spans = []
        for off, size in self.replaced:
            end = (off + size + 7) & ~7
            if off % 8 == 0 and 0x48 <= off < end <= pool:
                spans.append([off, end])
        spans.sort()
        merged = []
        for a, b in spans:  # one structure replaced twice, or two side by side, make one span
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        main = {off: (kind, target) for where, off, kind, target in self.fixups if where == "main"}
        fixed = [off for off in main] + [o["@"] for o in self.ev.flowcharts + self.ev.timelines]
        absolute = [target for _, _, kind, target in self.fixups if kind == self.ABS and target]
        while merged:
            starts = [a for a, _ in merged]

            def inside(x):
                i = bisect.bisect_right(starts, x) - 1
                return i if i >= 0 and x < merged[i][1] else None
            hit = {inside(x) for x in fixed}
            for slot in self.relt_slots:  # what the kept pointers point at (as this build leaves them)
                if slot >= pool or inside(slot) is not None:
                    continue
                if slot in main:
                    kind, target = main[slot]
                    v = target if kind == self.ABS else 0
                else:
                    v = struct.unpack_from("<Q", d, slot)[0]
                if v:
                    hit.add(inside(v))
            hit.update(inside(v) for v in absolute)
            hit.discard(None)
            if not hit:
                break
            merged = [m for i, m in enumerate(merged) if i not in hit]
        return [tuple(m) for m in merged]

    def build(self):
        """Lays the file out like Nintendo's: [original structures][new structures][string pool][RELT].
        The structures this build replaced are cut from the original ones (_cuts), so every pointer to what
        follows them moves back. The string pool moves by the size of the new structures minus the cuts."""
        self._finalize()
        for _, _, kind, target in self.fixups:  # every string must exist before the layout is fixed
            if kind == self.STR:
                self._str(target)
        d = self.buf
        pool_start, pool_end = self.pool, self.pool_end
        cuts = self._cuts()
        cut_starts, cut_before = [a for a, _ in cuts], [0]
        for a, b in cuts:
            cut_before.append(cut_before[-1] + b - a)

        def in_cut(v):
            i = bisect.bisect_right(cut_starts, v)
            return bool(i) and v < cuts[i - 1][1]

        def at(v):  # where an offset in the original structures (not in a cut) ends up
            if in_cut(v):
                raise ValueError(f"offset {v:#x} is inside a cut structure")
            return v - cut_before[bisect.bisect_right(cut_starts, v)]
        head_len = at(pool_start)
        block_base = (head_len + 7) & ~7
        new_pool_start = (block_base + len(self.block) + 7) & ~7
        shift = new_pool_start - pool_start
        pool = bytearray(d[pool_start:pool_end]) + self.new_strings
        new_pool_end = new_pool_start + len(pool)
        relt_off = (new_pool_end + 7) & ~7

        def moved(v):  # a pointer value into the original file, at its new place
            if pool_start <= v < pool_end:
                return v + shift
            return at(v) if v < pool_start else v

        def resolve(kind, target):
            if kind == self.STR:
                s = self._str(target)
                return new_pool_start + (pool_end - pool_start) + s[1] if isinstance(s, tuple) else moved(s)
            if kind == self.BLOCK:
                return block_base + target
            return moved(target)

        head = bytearray(d[:pool_start])
        # Use RELT to move the existing pointers. Skip slots inside cuts and leave rewritten slots
        # for the fixups below.
        kept, rewritten = [], {off for where, off, _, _ in self.fixups if where == "main"}
        for slot in self.relt_slots:
            if in_cut(slot):
                continue
            kept.append(slot)
            v = struct.unpack_from("<Q", head, slot)[0]
            if v and slot not in rewritten:
                struct.pack_into("<Q", head, slot, moved(v))
        # relative block-chain offsets and the file-name offset also point into the pool
        for owner in [fc["@"] for fc in self.ev.flowcharts] + [tl["@"] for tl in self.ev.timelines]:
            rel = struct.unpack_from("<I", head, owner + 4)[0]
            if owner + rel == pool_start:
                struct.pack_into("<I", head, owner + 4, new_pool_start - at(owner))
        struct.pack_into("<I", head, 0x10, moved(struct.unpack_from("<I", head, 0x10)[0]))

        block = bytearray(self.block)
        slots = {at(s) for s in kept}
        for where, off, kind, target in self.fixups:
            v = resolve(kind, target)
            if where == "main":
                struct.pack_into("<Q", head, off, v)
                slots.add(at(off))
            else:
                struct.pack_into("<Q", block, off, v)
                slots.add(block_base + off)
        if cuts:  # the original structures without the cut ones
            parts, last = [], 0
            for a, b in cuts:
                parts.append(head[last:a])
                last = b
            parts.append(head[last:])
            head = bytearray(b"".join(parts))
        n_new = sum(1 for _ in _iter_strings(self.new_strings))
        struct.pack_into("<I", pool, 0x10, self.n_strings + n_new)
        out = (head + bytes(block_base - head_len) + block + bytes(new_pool_start - block_base - len(block))
               + pool + bytes(relt_off - new_pool_end))
        out += relt_bytes(slots, relt_off, new_pool_end)
        struct.pack_into("<I", out, 0x18, relt_off)
        struct.pack_into("<I", out, 0x1C, len(out))
        return bytes(out)


def _iter_strings(blob):
    p = 0
    while p < len(blob):
        n = struct.unpack_from("<H", blob, p)[0]
        yield blob[p + 2:p + 2 + n]
        p += 2 + n + 1
        p += p & 1


# Entry points' sub-flow lists
# Each entry point lists the call steps (sub-flow and sub-flow switch) it reaches. That's from its first step
# through next steps, forks, joins and cases, not into the entries it calls, stopping at return steps (type 6).
# The game binds a scene's actors from these lists (the evfl binder at 0x8124c6e0 walks steps without following
# calls), so a call missing from its entry's list runs with its actors unbound. When the get-scene hook's calls
# were missing from Dm_SY_Get's entry, the resident heart scene froze (null handler) or crashed (garbage
# handler) on every disguised ice trap. The rule and the order (depth first, successors in file order) match
# all 5,512 vanilla entry points.
CALL_TYPES = ("subflow", "subflow_switch")


def _successors(ev):
    if ev["type"] == "type6":  # a return step, its field is a value and not a next step
        return []
    if ev["type"] == "fork":
        out = list(ev.get("forks") or []) + [ev.get("join")]
    elif ev.get("cases"):
        out = [c["next"] for c in ev["cases"]]
    else:
        out = [ev.get("next")]
    return [x for x in out if isinstance(x, int)]


def sub_flow_order(fc, start):
    """The call steps entry-point step `start` reaches, in Nintendo's order."""
    evs, seen, out, stack = fc["events"], set(), [], [start]
    while stack:
        i = stack.pop()
        if not isinstance(i, int) or i >= len(evs) or i in seen:
            continue
        seen.add(i)
        if evs[i]["type"] in CALL_TYPES:
            out.append(i)
        stack.extend(reversed(_successors(evs[i])))
    return out


def stale_sub_flows(data):
    """{(flowchart, entry): (listed, reached)} for the entry points whose sub-flow list is wrong."""
    ev = Evfl(data)
    out = {}
    for fc in ev.flowcharts:
        for name, ep in fc["entry_points"].items():
            want = sub_flow_order(fc, ep["main"])
            if list(ep.get("sub_flow_events") or []) != want:
                out[(fc["name"], name)] = (list(ep.get("sub_flow_events") or []), want)
    return out


# Switch cases that end the flow
# None of the game's 27,789 switch cases (914 event files, newest versions) points straight at the flowchart's
# end. A branch that does nothing goes through a step that then ends. A case pointing at the end is a shape the
# engine was never fed (C3's finding), so every case like that a plugin makes (a new graph's case to None, a
# case edit to None) goes through one do-nothing step per flowchart. We use vanilla's, the first one whose
# actor the flowchart has:
# - EventSystemActor / GameSystemActor EventWait of 1 frame (~400 and 99 vanilla steps, both used as a case's
#   last step)
# - Player_Event.EventDoNothing (7 vanilla last steps)
CASE_END = (("EventSystemActor", "EventWait", {"IsWaitEnd": True, "Frames": 1}),
            ("GameSystemActor", "EventWait", {"IsWaitEnd": True, "Frames": 1}),
            ("Player_Event", "EventDoNothing", {"IsWaitEnd": True}))
CASE_END_NAME = "Rando_CaseEnd"


def is_case_end(e):
    """True for route_end_cases' do-nothing step, which a walker reading a case's target treats as the end."""
    return e is not None and e.get("name") == f"{CASE_END_NAME}_w"


def end_cases(data):
    """[(flowchart, step, case index)] of the switch cases pointing at the flowchart's end."""
    out = []
    for fc in Evfl(data).flowcharts:
        n = len(fc["events"])
        for e in fc["events"]:
            out += [(fc["name"], e["name"], k) for k, c in enumerate(e.get("cases") or []) if c["next"] >= n]
    return out


def route_end_cases(data):
    """Returns the event file with every switch case that points at the end sent through a do-nothing step
    (CASE_END) that then ends. A flowchart with none of CASE_END's actors keeps its cases, and end_cases reports
    them."""
    ev = Evfl(data)
    todo = []
    for fc in ev.flowcharts:
        n = len(fc["events"])
        cases = [c for e in fc["events"] for c in (e.get("cases") or []) if c["next"] >= n]
        if cases:
            todo.append((fc["name"], cases))
    if not todo:
        return data
    b = EvflBuilder(data)
    for name, cases in todo:
        fc = b.flowchart(name)
        step = next((e["idx"] for e in fc["events"] if e["name"] == f"{CASE_END_NAME}_w"), None)
        if step is None:
            for actor, action, params in CASE_END:
                if any(a["name"] == actor and not a["sub_name"] for a in fc["actors"]):
                    step = b.add_graph(fc, CASE_END_NAME, {"w": {"actor": actor, "action": action, "params": params,
                                                                  "next": None}}, "w", entry=False)["w"]
                    break
        if step is None:
            continue
        for c in cases:
            struct.pack_into("<H", b.buf, c["@"] + 4, step)
    return b.build()


def sync_sub_flows(data):
    """Returns the event file with every switch case's end routed through a do-nothing step (route_end_cases) and
    every entry point's sub-flow list rewritten to the steps it reaches."""
    data = route_end_cases(data)
    stale = stale_sub_flows(data)
    if not stale:
        return data
    b = EvflBuilder(data)
    for (fcn, name), (_, want) in stale.items():
        b.set_sub_flows(b.flowchart(fcn), name, want)
    out = b.build()
    left = stale_sub_flows(out)
    if left:
        raise ValueError(f"sub-flow lists still wrong after the rewrite: {sorted(left)[:5]}")
    return out
