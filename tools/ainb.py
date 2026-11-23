"""AINB (AI node binary, version 0x408) reader and writer.

These are the remake's AI, Logic and Sequence graphs, so romfs AI/, Logic/ and Sequence/, the AI/*.ainb files
inside actor packs and Pack/AI.Global.Product.111.pack.zs.

    a = Ainb(data)              # parse
    a.dump() == data            # every file in the game re-saves byte for byte (tools/selftest.py step 8)
    n = a.node_by_name("OneShotDropSetOverWriteParam")
    a.set_input(n, "Key", "RespawnGmdHash")           # an input's immediate value
    a.set_property(n, "IsSet", True)                    # a property's value
    a.set_bb_default("string", "Name", "x")             # a blackboard default
    a.set_plug(n, 2, 0, node=7)                         # a link (plug) target
    a.add_node(copy_of=n)                               # a new node (a copy), linked with add_plug
    a.add_child(sel, m, "True")                         # a child, or a BoolSelector's True/False case
    a.set_child(cmd_node, "Execute", m)                 # re-point an existing child link
    a.feed(q, "IsEqual", sel, "Input")                  # a bool/float/string/int input, consumer-side plug

Every name and value lives in the model as plain Python data. The writer lays the sections out again in the
game's order and recomputes every offset, count and base index. Strings keep their place in the string pool and
new ones get appended, so the parts we keep as raw bytes (plug extras, expression binary) stay valid.
"""
import struct

# Parameter types in node parameter tables (properties, inputs, outputs) and plug kinds.
PTYPES = ("int", "bool", "float", "string", "vec3", "ptr")
# Blackboard types, in their section order (0x408 adds an unused u32 slot).
BBTYPES = ("string", "int", "u32", "float", "bool", "vec3", "ptr")
BB_VALUE_SIZE = {"string": 4, "int": 4, "u32": 4, "float": 4, "bool": 4, "vec3": 12, "ptr": 0}
PLUG_KINDS = 10  # 0 input/output links, 2 children, 3 transitions, 4/5 selector inputs, the rest unused here
PLUG_INPUT, PLUG_CHILD, PLUG_TRANSITION = 0, 2, 3
# A parameter whose flags have bit 31 set reads its value from somewhere else, and its own value field is only a
# fallback. 0x8000000N means entry N of that type in the file's blackboard, and 0x88/0x8C/0xC2... are other indexed
# forms. Plain values are 0, 0x800000 or 0x1800000 (checked over 1319 vanilla files).
BB_INDEXED = 0x80000000
# Input shapes, counted over AI.Global's 1319 files. An input fed by another node has flags 0 (or a bit-31 form).
# An input holding its own value always has 0x800000 or 0x1800000, never 0. Edits stick to these shapes, and
# input_shape_problems checks a whole file.
CONST_FLAGS = 0x800000
NODE_TYPES = {0: "UserDefined", 1: "S32Selector", 2: "Sequential", 3: "Simultaneous", 4: "F32Selector",
              5: "StringSelector", 6: "RandomSelector", 7: "BoolSelector", 8: "Fork", 9: "Join", 10: "Alert",
              20: "Expression", 100: "ModuleIF_Input_S32", 101: "ModuleIF_Input_F32",
              102: "ModuleIF_Input_Vec3f", 103: "ModuleIF_Input_String", 104: "ModuleIF_Input_Bool",
              105: "ModuleIF_Input_Ptr", 200: "ModuleIF_Output_S32", 201: "ModuleIF_Output_F32",
              202: "ModuleIF_Output_Vec3f", 203: "ModuleIF_Output_String", 204: "ModuleIF_Output_Bool",
              205: "ModuleIF_Output_Ptr", 300: "ModuleIF_Child", 400: "StateEnd", 500: "SplitTiming"}

HEADER = struct.Struct("<4sI27I")
NODE = struct.Struct("<HhHBBIIIIHHHHIHHI16s")
assert HEADER.size == 0x74 and NODE.size == 0x3C


def random_weight(w):
    """Extra bytes for a RandomSelector child, u32 0 and then its f32 weight (vanilla uses 1.0, 3.0 and 50.0)."""
    return struct.pack("<If", 0, float(w))


class AinbError(Exception):
    pass


def _f32(raw):
    return struct.unpack("<f", struct.pack("<I", raw))[0]


def _u32f(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


class _Reader:
    def __init__(self, data):
        self.d = data

    def u32(self, o):
        return struct.unpack_from("<I", self.d, o)[0]

    def i32(self, o):
        return struct.unpack_from("<i", self.d, o)[0]

    def u16(self, o):
        return struct.unpack_from("<H", self.d, o)[0]

    def i16(self, o):
        return struct.unpack_from("<h", self.d, o)[0]


class StringPool:
    """Keeps the pool's vanilla layout. A string is written at its first vanilla offset and new ones go at the end,
    so offsets held in raw bytes (plug extras) stay valid."""

    def __init__(self, raw=b""):
        self.raw = bytearray(raw)
        self.index = {}
        p = 0
        while p < len(raw):
            e = raw.index(b"\0", p)
            self.index.setdefault(raw[p:e].decode("utf-8"), p)
            p = e + 1

    def get(self, off):
        return self.raw[off:self.raw.index(b"\0", off)].decode("utf-8")

    def offset(self, s):
        if s not in self.index:
            self.index[s] = len(self.raw)
            self.raw += s.encode("utf-8") + b"\0"
        return self.index[s]


class Ainb:
    def __init__(self, data):
        self._parse(bytes(data))

    # Parse
    def _parse(self, d):
        r = _Reader(d)
        magic, self.version, *h = HEADER.unpack_from(d, 0)
        if magic != b"AIB ":
            raise AinbError("not an AINB file")
        if self.version != 0x408:
            raise AinbError(f"AINB version {self.version:#x} (only 0x408 is supported)")
        (fname, ncmd, nnode, self.nquery, natt, self.nout, o_bb, o_str, o_enum, o_prop, o_trans, o_io, o_multi,
         o_att, o_attidx, o_exb, o_repl, o_query, o_x50, self.x54, self.x58, o_module, catname, self.cat,
         o_action, o_x6c, o_bbid) = h
        if self.x54 or self.x58:
            raise AinbError("header fields 0x54/0x58 are set (unknown section)")
        if o_x50 != o_trans:
            raise AinbError("header field 0x50 is not the transition offset")
        # the string pool runs to the end of the file
        self.pool = StringPool(d[o_str:])
        s = self.pool.get
        self.name, self.category = s(fname), s(catname)

        self.commands = []
        p = 0x74
        for _ in range(ncmd):
            nm, guid, main, sec = struct.unpack_from("<I16sHH", d, p)
            self.commands.append({"name": s(nm), "guid": guid, "main": main, "secondary": sec})
            p += 0x18

        # Read the global tables first. Nodes and attachments store indices into them.
        props = {}
        offs = struct.unpack_from("<6I", d, o_prop)
        ends = list(offs[1:]) + [o_io]
        for t, a, b in zip(PTYPES, offs, ends):
            size = 20 if t == "vec3" else 12
            if (b - a) % size:
                raise AinbError(f"property table {t}: {b - a} bytes")
            props[t] = [self._read_prop(r, t, a + i * size) for i in range((b - a) // size)]
        inputs, outputs = {}, {}
        io = struct.unpack_from("<12I", d, o_io)
        for i, t in enumerate(PTYPES):
            ia, oa = io[2 * i], io[2 * i + 1]
            ib = oa
            ob = io[2 * i + 2] if i < 5 else o_multi
            isz = {"vec3": 24, "ptr": 20}.get(t, 16)
            osz = 8 if t == "ptr" else 4
            if (ib - ia) % isz or (ob - oa) % osz:
                raise AinbError(f"input/output table {t}: bad size")
            inputs[t] = [self._read_input(r, t, ia + k * isz) for k in range((ib - ia) // isz)]
            outputs[t] = [self._read_output(r, t, oa + k * osz) for k in range((ob - oa) // osz)]
        multi_end = o_trans if o_trans >= o_multi else o_query
        self.multi = [struct.unpack_from("<hhI", d, o_multi + 8 * k) for k in range((multi_end - o_multi) // 8)]

        # nodes
        self.nodes = []
        node_param_offs = []
        for i in range(nnode):
            (ntype, idx, n_att, flags, flags2, nm, nhash, unk10, o_param, exb_n, exb_sz, multi_n, pad1e, att_base,
             q_base, q_n, x28, guid) = NODE.unpack_from(d, p)
            self.nodes.append({"type": ntype, "index": idx, "flags": flags, "flags2": flags2, "name": s(nm),
                               "hash": nhash, "unk10": unk10, "exb_count": exb_n, "exb_size": exb_sz,
                               "multi_count": multi_n, "pad1e": pad1e, "attachments": [], "_n_att": n_att,
                               "_att_base": att_base, "query_base": q_base, "query_count": q_n, "x28": x28,
                               "guid": guid})
            node_param_offs.append(o_param)
            p += 0x3C
        node_end = p

        # blackboard
        self.bb = self._read_blackboard(r, o_bb)

        # node parameter regions, in node order
        region_ends = node_param_offs[1:] + [o_attidx]
        expect = self._bb_end
        for n, a, end in zip(self.nodes, node_param_offs, region_ends):
            if a != expect:
                raise AinbError(f"node {n['index']} parameters at {a:#x}, expected {expect:#x}")
            pr = struct.unpack_from("<12I", d, a)
            n["properties"] = {}
            for k, t in enumerate(PTYPES):
                base, cnt = pr[2 * k], pr[2 * k + 1]
                n["properties"][t] = props[t][base:base + cnt]
                n.setdefault("_prop_ranges", []).append((base, cnt))
            ior = struct.unpack_from("<24I", d, a + 0x30)
            n["inputs"], n["outputs"] = {}, {}
            for k, t in enumerate(PTYPES):
                ib, ic, ob, oc = ior[4 * k:4 * k + 4]
                n["inputs"][t] = inputs[t][ib:ib + ic]
                n["outputs"][t] = outputs[t][ob:ob + oc]
                n.setdefault("_io_ranges", []).append((ib, ic, ob, oc))
            pe = struct.unpack_from("<20B", d, a + 0x90)
            total = sum(pe[0::2])
            ptrs = struct.unpack_from(f"<{total}I", d, a + 0xA4)
            n["_plug_entries"] = [(pe[2 * k], pe[2 * k + 1]) for k in range(PLUG_KINDS)]
            data_start = a + 0xA4 + 4 * total
            if ptrs and ptrs[0] != data_start:
                raise AinbError(f"node {n['index']}: plug data not right after its pointers")
            bounds = list(ptrs[1:]) + [end]
            n["plugs"] = [[] for _ in range(PLUG_KINDS)]
            flat = []
            kinds = [k for k in range(PLUG_KINDS) for _ in range(pe[2 * k])]
            for q, nxt, kind in zip(ptrs, bounds, kinds):
                if nxt < q:
                    raise AinbError(f"node {n['index']}: plug data out of order")
                if kind == PLUG_TRANSITION:  # a transition: node and the transition table index
                    flat.append({"node": r.i32(q), "transition": r.u32(q + 4), "extra": d[q + 8:nxt]})
                else:
                    flat.append({"node": r.i32(q), "name": s(r.u32(q + 4)), "extra": d[q + 8:nxt]})
            k0 = 0
            for k in range(PLUG_KINDS):
                cnt, base = n["_plug_entries"][k]
                if base != k0 and cnt:
                    raise AinbError(f"node {n['index']}: plug kind {k} base {base}, expected {k0}")
                n["plugs"][k] = flat[base:base + cnt]
                k0 += cnt
            n["_plug_bases"] = [b for _, b in n["_plug_entries"]]
            expect = end if not ptrs else end
            if not ptrs:
                expect = data_start
                if data_start != end:
                    raise AinbError(f"node {n['index']}: {end - data_start} unread bytes after its parameters")
        if not self.nodes:
            expect = self._bb_end
        if o_attidx != expect:
            raise AinbError(f"attachment index array at {o_attidx:#x}, expected {expect:#x}")

        # attachments
        self.attachment_index = [r.u32(o_attidx + 4 * k) for k in range((o_att - o_attidx) // 4)]
        self.attachments = []
        q = o_att
        param_offs = []
        for k in range(natt):
            nm, o_par, exb_n, exb_sz, ahash = struct.unpack_from("<IIHHI", d, q)
            self.attachments.append({"name": s(nm), "exb_count": exb_n, "exb_size": exb_sz, "hash": ahash})
            param_offs.append(o_par)
            q += 16
        for k, (a_, o_par) in enumerate(zip(self.attachments, param_offs)):
            if o_par != q + 0x64 * k:
                raise AinbError(f"attachment {k} parameters at {o_par:#x}, expected {q + 0x64 * k:#x}")
            a_["debug"] = r.u32(o_par)
            pr = struct.unpack_from("<12I", d, o_par + 4)
            a_["properties"] = {t: props[t][pr[2 * j]:pr[2 * j] + pr[2 * j + 1]] for j, t in enumerate(PTYPES)}
            a_["_prop_ranges"] = [(pr[2 * j], pr[2 * j + 1]) for j in range(6)]
            tail = struct.unpack_from("<12I", d, o_par + 0x34)
            if any(tail[2 * j] or tail[2 * j + 1] != o_par + 0x64 for j in range(6)):  # six empty (count, at) pairs
                raise AinbError(f"attachment {k}: unknown values after its properties")
        if q + 0x64 * natt != o_prop:
            raise AinbError("attachment parameters don't end at the property table")
        for n in self.nodes:  # node -> attachment links through the attachment index array
            b, c = n.pop("_att_base"), n.pop("_n_att")
            n["attachments"] = list(self.attachment_index[b:b + c])
            n["_att_base"] = b
        self._props, self._inputs, self._outputs = props, inputs, outputs

        # transitions
        self.transitions = []
        if o_trans < o_query:
            first = r.u32(o_trans)
            toffs = [r.u32(o_trans + 4 * k) for k in range((first - o_trans) // 4)]
            q = first
            for to in toffs:
                if to != q:
                    raise AinbError("transition entries out of order")
                flags = r.u32(q)
                if flags & 0xFF == 0:
                    self.transitions.append({"flags": flags, "command": s(r.u32(q + 4))})
                    q += 8
                else:
                    self.transitions.append({"flags": flags})
                    q += 4
            if q != o_query:
                raise AinbError("transition table doesn't end at the query table")
        # queries
        q_end = o_exb or o_module
        if (q_end - o_query) % 4:
            raise AinbError("query table size")
        self.queries = [struct.unpack_from("<HH", d, o_query + 4 * k) for k in range((q_end - o_query) // 4)]
        q = q_end
        if o_exb:
            if o_exb != q:
                raise AinbError("expression binary not right after the query table")
            self.exb = d[o_exb:o_module]
            q = o_module
        else:
            self.exb = None
        if q != o_module:
            raise AinbError(f"module table at {o_module:#x}, expected {q:#x}")
        cnt = r.u32(o_module)
        self.modules = [{"path": s(r.u32(o_module + 4 + 12 * k)), "category": s(r.u32(o_module + 8 + 12 * k)),
                         "count": r.u32(o_module + 12 + 12 * k)} for k in range(cnt)]
        q = o_module + 4 + 12 * cnt
        if q != o_action:
            raise AinbError("action table not right after the module table")
        cnt = r.u32(o_action)
        self.actions = [{"node": r.i32(o_action + 4 + 12 * k), "slot": s(r.u32(o_action + 8 + 12 * k)),
                         "action": s(r.u32(o_action + 12 + 12 * k))} for k in range(cnt)]
        q = o_action + 4 + 12 * cnt
        if q != o_bbid:
            raise AinbError("blackboard id not right after the action table")
        self.bb_id = struct.unpack_from("<II", d, o_bbid)
        if o_repl != o_bbid + 8:
            raise AinbError("replacement table not right after the blackboard id")
        replaced, rpad, rcnt, upd_node, upd_att = struct.unpack_from("<BBHhh", d, o_repl)
        self.replacement = {"replaced": replaced, "pad": rpad, "node": upd_node, "attachment": upd_att,
                            "entries": [struct.unpack_from("<BBhhh", d, o_repl + 8 + 8 * k) for k in range(rcnt)]}
        q = o_repl + 8 + 8 * rcnt
        if o_x6c != q:
            raise AinbError("0x6C section not right after the replacement table")
        self.x6c = r.u32(o_x6c)
        if o_enum != o_x6c + 4:
            raise AinbError("enum table not right after the 0x6C section")
        cnt = r.u32(o_enum)
        self.enums = [struct.unpack_from("<III", d, o_enum + 4 + 12 * k) for k in range(cnt)]
        if o_enum + 4 + 12 * cnt != o_str:
            raise AinbError("string pool not right after the enum table")
        if node_end != (0x74 + 0x18 * ncmd + 0x3C * nnode) or o_bb != node_end:
            raise AinbError("blackboard not right after the nodes")
        self._check_tables_in_order()

    def _check_tables_in_order(self):
        """The writer rebuilds the global tables as each node's slice and then each attachment's slice in turn, so check
        they really were laid out that way. Otherwise we couldn't recompute the bases."""
        for t in PTYPES:
            k = 0
            for owner in self.nodes + self.attachments:
                base, cnt = owner["_prop_ranges"][PTYPES.index(t)]
                if cnt and base != k:
                    raise AinbError(f"property table {t} not in owner order")
                if not cnt and base != k:
                    owner.setdefault("_prop_odd", {})[t] = base
                k += cnt
            if k != len(self._props[t]):
                raise AinbError(f"property table {t}: {len(self._props[t]) - k} entries nobody uses")
            ki = ko = 0
            for n in self.nodes:
                ib, ic, ob, oc = n["_io_ranges"][PTYPES.index(t)]
                if (ic and ib != ki) or (oc and ob != ko):
                    raise AinbError(f"input/output table {t} not in node order")
                if not ic and ib != ki:
                    n.setdefault("_in_odd", {})[t] = ib
                if not oc and ob != ko:
                    n.setdefault("_out_odd", {})[t] = ob
                ki += ic
                ko += oc
            if ki != len(self._inputs[t]) or ko != len(self._outputs[t]):
                raise AinbError(f"input/output table {t}: entries nobody uses")
        k = 0
        for n in self.nodes:
            if n["attachments"] and n["_att_base"] != k:
                raise AinbError("attachment index array not in node order")
            if not n["attachments"] and n["_att_base"] != k:
                n["_att_odd"] = n["_att_base"]
            k += len(n["attachments"])
        if k != len(self.attachment_index):
            raise AinbError("attachment index array: entries nobody uses")
        for n in self.nodes:
            del n["_prop_ranges"], n["_io_ranges"], n["_att_base"]
            k = 0
            for kind, (cnt, base) in enumerate(n.pop("_plug_entries")):
                if base != k:
                    n.setdefault("_plug_odd", {})[kind] = base
                k += cnt
            del n["_plug_bases"]
        for a in self.attachments:
            del a["_prop_ranges"]
        del self._props, self._inputs, self._outputs, self.attachment_index

    def _read_prop(self, r, t, o):
        s = self.pool.get
        name, flags = r.u32(o), r.u32(o + 4)
        if t == "ptr":
            return {"name": s(name), "class": s(flags), "flags": r.u32(o + 8)}
        return {"name": s(name), "flags": flags, "value": self._read_value(r, t, o + 8)}

    def _read_value(self, r, t, o):
        if t == "int":
            return r.i32(o)
        if t == "bool":
            v = r.u32(o)
            return bool(v) if v in (0, 1) else v
        if t == "float":
            return _f32(r.u32(o))
        if t == "string":
            return self.pool.get(r.u32(o))
        if t == "vec3":
            return [_f32(r.u32(o + 4 * i)) for i in range(3)]
        raise AinbError(t)

    def _read_input(self, r, t, o):
        s = self.pool.get
        if t == "ptr":
            return {"name": s(r.u32(o)), "class": s(r.u32(o + 4)), "node": r.i16(o + 8), "plug": r.i16(o + 10),
                    "flags": r.u32(o + 12), "value": r.u32(o + 16)}
        return {"name": s(r.u32(o)), "node": r.i16(o + 4), "plug": r.i16(o + 6), "flags": r.u32(o + 8),
                "value": self._read_value(r, t, o + 12)}

    def _read_output(self, r, t, o):
        w = r.u32(o)
        out = {"name": self.pool.get(w & 0x7FFFFFFF), "flag": w >> 31}
        if t == "ptr":
            out["class"] = self.pool.get(r.u32(o + 4))
        return out

    def _read_blackboard(self, r, o):
        hdr = [struct.unpack_from("<4H", r.d, o + 8 * i) for i in range(7)]
        p = o + 0x38
        bb = {t: [] for t in BBTYPES}
        refs_needed = -1
        for i, t in enumerate(BBTYPES):
            cnt, idx, voff, pad = hdr[i]
            if pad:
                raise AinbError("blackboard header padding is set")
            for _ in range(cnt):
                w, notes = r.u32(p), r.u32(p + 4)
                e = {"name": self.pool.get(w & 0x3FFFFF), "flags": (w >> 22) & 3, "notes": self.pool.get(notes)}
                if w >> 31:
                    e["file"] = (w >> 24) & 0x7F
                    refs_needed = max(refs_needed, e["file"])
                elif (w >> 24) & 0x7F:
                    raise AinbError("blackboard file index without its valid bit")
                bb[t].append(e)
                p += 8
        vbase = p
        for i, t in enumerate(BBTYPES):
            cnt, idx, voff, pad = hdr[i]
            for k, e in enumerate(bb[t]):
                vo = vbase + voff + k * BB_VALUE_SIZE[t]
                e["default"] = None if t == "ptr" else (r.u32(vo) if t == "u32" else self._read_value(r, t, vo))
        vend = vbase + sum(len(bb[t]) * BB_VALUE_SIZE[t] for t in BBTYPES)
        if hdr[-1][2] + 0 != vend - vbase and bb["ptr"] is not None and hdr[-1][2] != vend - vbase:
            raise AinbError("blackboard value layout")
        self.bb_files = []
        q = vend
        for _ in range(refs_needed + 1):
            path, h1, h2, h3 = struct.unpack_from("<4I", r.d, q)
            self.bb_files.append({"path": self.pool.get(path), "hashes": (h1, h2, h3)})
            q += 16
        self._bb_end = q
        return bb

    # Edit
    def node(self, ref):
        """A node index from an int, a node name ("OneShotX", first one) or "OneShotX#2" (third one)."""
        if isinstance(ref, int):
            if not 0 <= ref < len(self.nodes):
                raise AinbError(f"{self.name}: no node {ref}")
            return ref
        name, _, nth = str(ref).partition("#")
        hits = [i for i, n in enumerate(self.nodes) if n["name"] == name or NODE_TYPES.get(n["type"]) == name]
        k = int(nth or 0)
        if k >= len(hits):
            raise AinbError(f"{self.name}: no node {ref} ({len(hits)} named {name})")
        return hits[k]

    def query_index(self, i):
        """Position of query node i in the query numbering (query nodes, in node order)."""
        if not self.nodes[i]["flags"] & 1:
            raise AinbError(f"{self.name}: node {i} is not a query")
        return sum(1 for n in self.nodes[:i] if n["flags"] & 1)

    def _direct_sources(self, i):
        out = []
        for t in PTYPES:
            for e in self.nodes[i]["inputs"][t]:
                if e["node"] >= 0:
                    out.append(e["node"])
                elif e["node"] <= -100:
                    b = -100 - e["node"]
                    out += [m[0] for m in self.multi[b:b + e["plug"]]]
        seen = []
        for j in out:
            if j not in seen:
                seen.append(j)
        return seen

    def refresh_queries(self, i):
        """Points node i's query list at the query nodes that feed its inputs. That's the game's rule, checked on every
        vanilla file. The new list goes at the end of the query table and the old entries stay, since other nodes may
        share them."""
        q = [self.query_index(j) for j in self._direct_sources(i) if self.nodes[j]["flags"] & 1]
        n = self.nodes[i]
        cur = [v for v, _ in self.queries[n["query_base"]:n["query_base"] + n["query_count"]]]
        if cur == q:
            return
        if not q:
            n["query_base"], n["query_count"] = 0, 0
            return
        n["query_base"], n["query_count"] = len(self.queries), len(q)
        self.queries += [(v, 0) for v in q]

    def _new_guid(self, seed):
        import hashlib
        return hashlib.md5(f"{self.name}/{seed}/{len(self.nodes)}".encode()).digest()

    def add_node(self, node):
        """Appends a copy of a node dict (as parsed). Query nodes take the last query number so existing ones keep
        theirs. The caller sets its links, inputs and query list (see copy_nodes, link, add_child)."""
        import copy
        n = copy.deepcopy(node)
        i = len(self.nodes)
        n["index"] = i
        n["guid"] = self._new_guid(n.get("guid", b"").hex())
        n["query_base"], n["query_count"] = 0, 0
        for k in ("_prop_odd", "_in_odd", "_out_odd", "_plug_odd", "_att_odd"):
            n.pop(k, None)
        if n["attachments"] or n["exb_count"] or n["flags"] & 2:
            raise AinbError(f"{n['name']}: nodes with attachments, expressions or module calls can't be added")
        self.nodes.append(n)
        if n["flags"] & 1:
            self.nquery += 1
        return i

    def copy_nodes(self, src, roots, follow=True, values=None):
        """Copies nodes from a parsed file (src, which may be this one) along with every node they reach through links
        and inputs. With follow=False only the listed nodes get copied, and their links and node-fed inputs are
        dropped so you set them with link / add_child. Returns {src index: new index}.

        It refuses anything that can't move between files:
        - blackboard-indexed parameters, unless `values` {src index: {name: value}} gives the copy a value instead.
          Flag bit 31 means the value is read from the file's blackboard (0x80000001 reads entry #1 of that type, and
          0x88/0x8C/0xC2... are other indexed forms). With `values` the copy gets a plain value with flags 0, like
          vanilla's unbound parameters.
        - selectors whose plug data hold string offsets
        - multi-inputs, attachments, expressions and module calls
        Copies within one file keep their blackboard reads.

        A multi-input (a list of sources, e.g. OperateAND's BoolMulti) only gets copied when `values` names it. A plain
        value drops its sources and the input holds that value. A list [[node, output], ...] of THIS file's nodes
        (output is a name or an index) gives the copy a new multi-input, laid out the way the game's are. That's a new
        slice at the end of the multi-input table, flags 0, the node's multi count and a plug to the first source."""
        values = {int(k): v for k, v in (values or {}).items()}
        todo, order = [src.node(r) for r in roots], []
        while todo:
            i = todo.pop(0)
            if i in order:
                continue
            order.append(i)
            n = src.nodes[i]
            if n["type"] in (5, 20):
                raise AinbError(f"{src.name}: node {i} ({NODE_TYPES[n['type']]}) can't be copied")
            for t in PTYPES:
                for e in n["properties"][t] + n["inputs"][t]:
                    if (e.get("flags", 0) & BB_INDEXED and src is not self
                            and e["name"] not in values.get(i, {})):
                        raise AinbError(f"{src.name}: node {i} parameter {e['name']} reads the blackboard "
                                        f"(flags {e['flags']:#x}): give the copy its own value")
                    if e in n["inputs"][t] and e["node"] <= -100 and e["name"] not in values.get(i, {}):
                        raise AinbError(f"{src.name}: node {i} uses a multi-input")
                    if follow and e in n["inputs"][t] and e["node"] >= 0:
                        todo.append(e["node"])
            for kind in range(PLUG_KINDS):
                for pl in n["plugs"][kind]:
                    if kind == PLUG_TRANSITION:
                        raise AinbError(f"{src.name}: node {i} has a transition")
                    if follow:
                        todo.append(pl["node"])
        for i, given in values.items():
            if i not in order:
                raise AinbError(f"{src.name}: values for node {i}, which isn't copied")
            for name in given:
                if not any(e["name"] == name for t in PTYPES
                           for e in src.nodes[i]["properties"][t] + src.nodes[i]["inputs"][t]):
                    raise AinbError(f"{src.name}: node {i} has no parameter {name}")
        src_nodes = [src.nodes[i] for i in order]  # src may be self, so grab them before appending
        remap = {i: self.add_node(n) for i, n in zip(order, src_nodes)}
        for i, j in remap.items():
            n = self.nodes[j]
            multi = []  # (type, input, [[node, output], ...]) per new multi-input, laid out after the links below
            for name, v in values.get(i, {}).items():
                for t in PTYPES:
                    for e in n["properties"][t] + n["inputs"][t]:
                        if e["name"] == name:
                            if t == "ptr":
                                raise AinbError(f"{src.name}: node {i} pointer {name} can't take a value")
                            if e.get("node", 0) <= -100:  # a multi-input (see the docstring)
                                n["multi_count"] -= e["plug"]
                                e["node"], e["plug"], e["flags"] = -1, 0, CONST_FLAGS
                                if isinstance(v, (list, tuple)):
                                    multi.append((t, e, v))
                                    continue
                            e["flags"], e["value"] = CONST_FLAGS, self._coerce(t, v, e["value"])
                            if "node" in e:
                                e["node"], e["plug"] = -1, 0
            for t in PTYPES:
                for e in n["inputs"][t]:
                    if e["node"] >= 0:
                        if e["node"] in remap:
                            e["node"] = remap[e["node"]]
                        else:  # feed dropped, the input holds its own value until something feeds it again
                            e["node"], e["plug"], e["flags"] = -1, 0, CONST_FLAGS
            for kind in range(PLUG_KINDS):
                n["plugs"][kind] = [dict(pl, node=remap[pl["node"]]) for pl in n["plugs"][kind] if pl["node"] in remap]
            for t, e, sources in multi:
                self._new_multi_input(j, t, e, sources)
        for j in remap.values():
            self.refresh_queries(j)
        return remap

    def retype(self, i, src, k, values=None):
        """Turns node i into a copy of node k of parsed file `src` (type, name and parameters) and keeps index i and its
        guid. It works like copy_nodes with follow=False, so node-fed inputs are dropped and `values` works the same
        way. Nothing may read or reach node i (the caller cuts those first) because its outputs become the new type's.
        This is how a logic module's actor node (ActorLogic...) takes another actor type's node, and it's how we made
        the remake's ice-trap chest spot a plain chest (parity/chests.py). Both need the same flags, since logic
        modules' nodes are all queries. Module calls, command starts and action nodes are refused."""
        if any(c["main"] == i or c.get("secondary") == i for c in self.commands) or any(a["node"] == i for a in self.actions):
            raise AinbError(f"{self.name}: node {i} starts a command or holds an action")
        old = self.nodes[i]
        k = src.node(k)
        if old["flags"] != src.nodes[k]["flags"] or old["flags"] & 2:
            raise AinbError(f"{self.name}: node {i} (flags {old['flags']}) can't take a node with flags "
                            f"{src.nodes[k]['flags']} (a query stays a query: logic modules' nodes all are)")
        for j, n in enumerate(self.nodes):
            if j == i:
                continue
            for t in PTYPES:
                for e in n["inputs"][t]:
                    if e["node"] == i:
                        raise AinbError(f"{self.name}: node {j} input {e['name']} reads node {i}: cut it first")
            for kind in range(PLUG_KINDS):
                if any(pl["node"] == i for pl in n["plugs"][kind]):
                    raise AinbError(f"{self.name}: node {j} plugs node {i}")
        if any(m[0] == i for m in self.multi):
            raise AinbError(f"{self.name}: a multi-input reads node {i}")
        m = self.copy_nodes(src, [k], follow=False, values=values)
        j = m[k]
        if j != len(self.nodes) - 1:
            raise AinbError(f"{self.name}: retype copy landed at {j}")
        new = self.nodes.pop()
        if new["flags"] & 1:  # the copy got the last query number, so node i keeps its own
            self.nquery -= 1
        new["index"], new["guid"] = i, old["guid"]
        self.nodes[i] = new
        self.refresh_queries(i)
        return i

    def _new_multi_input(self, j, t, e, sources):
        """Makes input e (type t) of node j read the list `sources` [[node, output name or index], ...] of this file.
        It adds a new slice at the end of the multi-input table (vanilla entries are source node, output index,
        flags 0) and points the input at it (node -100 - slice start, plug = count, flags 0). Then it raises the
        node's multi count and adds a plug to the first source, since vanilla's Operate nodes list one."""
        if not sources:
            raise AinbError(f"{self.name}: node {j} input {e['name']}: an empty multi-input")
        if self.nodes[j]["type"] != 0:
            raise AinbError(f"{self.name}: node {j}: multi-inputs are made for UserDefined (Operate...) nodes only")
        entries = []
        for s, out in sources:
            s = self.node(s)
            k = out if isinstance(out, int) else self._output_index(s, t, out)
            if not 0 <= k < len(self.nodes[s]["outputs"][t]):
                raise AinbError(f"{self.name}: node {s} has no {t} output {out}")
            entries.append((s, k, 0))
            self.flag_output(s, t, k)
        base = len(self.multi)
        self.multi += entries
        e["node"], e["plug"], e["flags"] = -100 - base, len(entries), 0
        self.nodes[j]["multi_count"] += len(entries)
        self.nodes[j]["plugs"][PLUG_INPUT].append({"node": entries[0][0], "name": e["name"], "extra": b""})

    def input_shape_problems(self):
        """Inputs shaped in a way the game's files never are (CONST_FLAGS). That's an input fed by a node with flags
        other than 0 or a bit-31 form, or one holding its own value without 0x800000/0x1800000. Multi-inputs
        (node <= -100) are left aside.
        Also every input or multi-input entry that reads an output not flagged "Is Output" (bit 31 of the output
        entry). A node only computes its flagged outputs, so an input like that reads false/0 forever. OotrR found
        that in-game, and every one of the 2691 vanilla Logic/AI/Sequence/AI.Global files reads flagged outputs
        only (bit-15 output forms such as 0x8000 aside)."""
        out = []
        for i, n in enumerate(self.nodes):
            for t in PTYPES:
                for e in n["inputs"][t]:
                    f, src = e.get("flags", 0), e.get("node", -1)
                    if src >= 0 and f and not f & BB_INDEXED:
                        out.append(f"node {i} ({n['name']}) input {e['name']}: fed by node {src} but flags {f:#x}")
                    elif -100 < src < 0 and not f & BB_INDEXED and not f & 0x1800000:
                        out.append(f"node {i} ({n['name']}) input {e['name']}: its own value but flags {f:#x}")
                    if f & BB_INDEXED:
                        continue
                    reads = [(src, e.get("plug", 0))] if src >= 0 else (
                        [(m[0], m[1]) for m in self.multi[-100 - src:-100 - src + e.get("plug", 0)]]
                        if src <= -100 else [])
                    for s, k in reads:
                        if 0 <= s < len(self.nodes) and 0 <= k < len(self.nodes[s]["outputs"][t]) and \
                                not self.nodes[s]["outputs"][t][k]["flag"]:
                            out.append(f"node {i} ({n['name']}) input {e['name']}: reads node {s}'s {t} output "
                                       f"{self.nodes[s]['outputs'][t][k]['name']}, not flagged Is Output (the node "
                                       f"never computes it)")
            # A node evaluates the query nodes in its query list before it reads them (refresh_queries). Every
            # vanilla file lists each query node that feeds a node.
            listed = {v for v, _ in self.queries[n["query_base"]:n["query_base"] + n["query_count"]]}
            for s in self._direct_sources(i):
                if 0 <= s < len(self.nodes) and self.nodes[s]["flags"] & 1 and self.query_index(s) not in listed:
                    out.append(f"node {i} ({n['name']}) reads query node {s} ({self.nodes[s]['name']}), which its "
                               f"query list doesn't name")
        return out

    def add_multi_source(self, dst, input_name, src, output):
        """Adds one more source at the end of dst's multi-input `input_name` (e.g. an OperateOR's BoolMulti). The entry
        goes in right after the input's slice, since vanilla has one contiguous slice per input, and later slices move
        up one. The node's multi count grows, the read output gets flagged and dst's query list follows. Its plug
        doesn't change (the first source, which is what vanilla lists)."""
        d, s = self.node(dst), self.node(src)
        t, e = self._input(d, input_name)
        if e["node"] > -100:
            raise AinbError(f"{self.name}: node {d} input {input_name} is not a multi-input")
        k = self._output_index(s, t, output)
        base, cnt = -100 - e["node"], e["plug"]
        if any(m[0] == s and m[1] == k for m in self.multi[base:base + cnt]):
            raise AinbError(f"{self.name}: node {d} input {input_name} already reads node {s} output {output}")
        self.multi.insert(base + cnt, (s, k, 0))
        for n in self.nodes:
            for tt in PTYPES:
                for x in n["inputs"][tt]:
                    if x is not e and x.get("node", 0) <= -100 and -100 - x["node"] >= base + cnt:
                        x["node"] -= 1
        e["plug"] = cnt + 1
        self.nodes[d]["multi_count"] += 1
        self.flag_output(s, t, k)
        self.refresh_queries(d)

    def flag_output(self, i, ptype, k):
        """Flag node i's output k (of type ptype) "Is Output", so the node computes it for its readers."""
        self.nodes[i]["outputs"][ptype][k]["flag"] = 1

    def is_plain_simultaneous(self, i):
        """Whether node i is a Simultaneous that runs every child to the end (EndPolicy 0, ResultPolicy 0), like the
        ones wrap_command makes. A branch added beside its children then always runs, same as they do."""
        n = self.nodes[i]
        return n["type"] == 3 and {e["name"]: (e["flags"], e["value"]) for e in n["properties"]["int"]} == {
            "EndPolicy": (0, 0), "ResultPolicy": (0, 0)}

    def wrap_command(self, command="Root"):
        """Makes a command start at a new Simultaneous node whose only child is the old start node, so more always-on
        branches can go beside it (add_child). Returns the new node's index."""
        c = next((c for c in self.commands if c["name"] == command), None)
        if c is None:
            raise AinbError(f"{self.name}: no command {command}")
        old = c["main"]
        n = {"type": 3, "index": 0, "flags": 4, "flags2": 0, "name": "", "hash": 0, "unk10": 0, "exb_count": 0,
             "exb_size": 0, "multi_count": 0, "pad1e": 0, "attachments": [], "query_base": 0, "query_count": 0,
             "x28": 0, "guid": f"wrap/{command}".encode(),
             "properties": {t: [] for t in PTYPES}, "inputs": {t: [] for t in PTYPES},
             "outputs": {t: [] for t in PTYPES}, "plugs": [[] for _ in range(PLUG_KINDS)]}
        n["properties"]["int"] = [{"name": "EndPolicy", "flags": 0, "value": 0},
                                  {"name": "ResultPolicy", "flags": 0, "value": 0}]
        i = self.add_node(n)
        self.nodes[i]["plugs"][PLUG_CHILD].append({"node": old, "name": "", "extra": b""})
        c["main"] = i
        return i

    def add_child(self, parent, child, name="", extra=b"", first=False):
        """Adds a child link (plug kind 2) at the end of a Sequential/Simultaneous/selector node's children. first=True
        makes it a Simultaneous's first child instead, e.g. a save step before the death signal, which is how the
        game orders its branches.
        A BoolSelector takes its two cases this way, named "True" and "False" with no extra bytes, like every vanilla
        BoolSelector. A RandomSelector's child carries its weight (random_weight(w), 8 extra bytes and no name, like
        every vanilla one). Other selectors need case values and are refused."""
        p, c = self.node(parent), self.node(child)
        kind = self.nodes[p]["type"]
        if kind == 7:
            if name not in ("True", "False") or extra:
                raise AinbError(f"{self.name}: a BoolSelector's cases are named True and False")
            if any(pl["name"] == name for pl in self.nodes[p]["plugs"][PLUG_CHILD]):
                raise AinbError(f"{self.name}: BoolSelector {p} already has a {name} case (set_child changes it)")
        elif kind == 6:
            if name or len(extra) != 8 or struct.unpack("<If", bytes(extra))[1] <= 0:
                raise AinbError(f"{self.name}: a RandomSelector's child needs a weight (random_weight) and no name")
        elif kind not in (2, 3, 8, 300) and kind != 0:
            raise AinbError(f"{self.name}: node {p} ({NODE_TYPES.get(kind)}) needs a case for a new child")
        if first and kind != 3:
            raise AinbError(f"{self.name}: only a Simultaneous takes a child first (node {p} is {NODE_TYPES.get(kind)})")
        plug = {"node": c, "name": name, "extra": bytes(extra)}
        if first:
            self.nodes[p]["plugs"][PLUG_CHILD].insert(0, plug)
        else:
            self.nodes[p]["plugs"][PLUG_CHILD].append(plug)

    def add_case(self, parent, child, value):
        """Adds a new case to an S32Selector (node type 1). It's a child plug with extra bytes u32 0 and the i32 case
        value, placed before the selector's default, which every vanilla S32Selector keeps as its last child."""
        p, c = self.node(parent), self.node(child)
        if self.nodes[p]["type"] != 1:
            raise AinbError(f"{self.name}: node {p} is not an S32Selector")
        kids = self.nodes[p]["plugs"][PLUG_CHILD]
        if not kids:
            raise AinbError(f"{self.name}: S32Selector {p} has no default child to keep last")
        if any(len(pl["extra"]) == 8 and struct.unpack("<Ii", bytes(pl["extra"]))[1] == int(value) for pl in kids[:-1]):
            raise AinbError(f"{self.name}: S32Selector {p} already has a case {value}")
        kids.insert(len(kids) - 1, {"node": c, "name": "", "extra": struct.pack("<Ii", 0, int(value))})

    def set_child(self, parent, which, child):
        """Points an existing child link of `parent` at another node. `which` is its position among the children
        (plug kind 2) or its name, "Execute" for an event command's node or "True"/"False" for a BoolSelector."""
        p, c = self.node(parent), self.node(child)
        kids = self.nodes[p]["plugs"][PLUG_CHILD]
        hits = [k for k, pl in enumerate(kids) if (pl["name"] == which if isinstance(which, str) else k == which)]
        if len(hits) != 1:
            raise AinbError(f"{self.name}: node {p} has {len(hits)} children matching {which!r}")
        kids[hits[0]]["node"] = c

    # Consumer-side input links (feed). For each input type, which plug kind lists a node's source, and the extra
    # bytes selectors carry there (a u32 0, then the source's output index). It's the same in every vanilla file,
    # counted over AI.Global: bool/float in kind 0, string in kind 4, int in kind 5. UserDefined nodes carry no
    # extra bytes.
    FEED_KIND = {"bool": 0, "float": 0, "string": 4, "int": 5}
    SELECTORS = (1, 4, 7)  # S32Selector, F32Selector, BoolSelector, not StringSelector (its extra holds a string)

    def feed(self, src, output, dst, input_name):
        """Feeds dst's bool, float, string or int input from src's output, the way the game's files do it for those
        types. The consumer lists its source in its own plugs (FEED_KIND) and the input names the source and output.
        Pointer and vec3 inputs get linked the other way round (link). dst's query list follows."""
        s, d = self.node(src), self.node(dst)
        t, e = self._input(d, input_name)
        if t not in self.FEED_KIND:
            raise AinbError(f"{self.name}: {t} input {input_name} of node {d}: use link")
        dtype = self.nodes[d]["type"]
        if dtype == 5:
            raise AinbError(f"{self.name}: node {d} is a StringSelector (its input link holds a string)")
        k = self._output_index(s, t, output)
        old = e["node"]
        e["node"], e["plug"] = s, k
        e["flags"] = 0  # like every node-fed input in the game's files
        self.flag_output(s, t, k)  # a node computes only its flagged outputs
        kind = self.FEED_KIND[t]
        extra = struct.pack("<II", 0, k) if dtype in self.SELECTORS else b""
        plugs = [pl for pl in self.nodes[d]["plugs"][kind] if not (pl["name"] == input_name and pl["node"] == old)]
        plugs.append({"node": s, "name": input_name, "extra": extra})
        self.nodes[d]["plugs"][kind] = plugs
        self.refresh_queries(d)

    def cut_input(self, node, name, value, default=False):
        """Makes a bool, float, string or int input stop reading the node that feeds it and hold `value` itself, like
        the game's constant inputs do. It gets flags 0x1800000 when `value` is the input's default (default=True),
        e.g. Logic_Create True or Logic_Delete False, which 5,435 and 5,440 actor inputs in the game's logic files
        use. A value set on purpose gets CONST_FLAGS, e.g. Logic_Create False for an actor that's never created
        (InsideJabuJabuBelly room 08's node 10). Its plug goes and its query list follows. The source keeps its
        outputs as they are, and a query node nothing names any more just never gets evaluated."""
        i = self.node(node)
        t, e = self._input(i, name)
        if t not in self.FEED_KIND:
            raise AinbError(f"{self.name}: {t} input {name} of node {i} can't be cut here")
        src = e["node"]
        if src < 0 or e["flags"] & BB_INDEXED:
            raise AinbError(f"{self.name}: input {name} of node {i} is not fed by one node")
        e["node"], e["plug"] = -1, 0
        e["flags"] = 0x1800000 if default else CONST_FLAGS
        e["value"] = self._coerce(t, value, e["value"])
        kind = self.FEED_KIND[t]
        self.nodes[i]["plugs"][kind] = [pl for pl in self.nodes[i]["plugs"][kind]
                                        if not (pl["name"] == name and pl["node"] == src)]
        self.refresh_queries(i)

    def _output_index(self, i, ptype, name):
        outs = self.nodes[i]["outputs"][ptype]
        for k, o in enumerate(outs):
            if o["name"] == name:
                return k
        raise AinbError(f"{self.name}: node {i} has no {ptype} output {name}")

    def _input(self, i, name, ptype=None):
        for t in ([ptype] if ptype else PTYPES):
            for e in self.nodes[i]["inputs"][t]:
                if e["name"] == name:
                    return t, e
        raise AinbError(f"{self.name}: node {i} ({self.nodes[i]['name']}) has no input {name}")

    def link(self, src, output, dst, input_name):
        """Feeds dst's input from src's output the way the game's files do it for pointer results. The source lists
        the consumer in its plug 0 and the input names the source and output. dst's query list follows."""
        s, d = self.node(src), self.node(dst)
        t, e = self._input(d, input_name)
        k = self._output_index(s, t, output)
        old = e["node"]
        e["node"], e["plug"] = s, k
        e["flags"] = 0  # like every node-fed input in the game's files
        self.flag_output(s, t, k)  # a node computes only its flagged outputs
        if old >= 0 and old != s:
            self.nodes[old]["plugs"][PLUG_INPUT] = [pl for pl in self.nodes[old]["plugs"][PLUG_INPUT]
                                                    if pl["node"] != d]
        if not any(pl["node"] == d for pl in self.nodes[s]["plugs"][PLUG_INPUT]):
            self.nodes[s]["plugs"][PLUG_INPUT].append({"node": d, "name": output, "extra": b""})
        self.refresh_queries(d)

    def _param(self, i, kind, name):
        table = self.nodes[i][kind]
        for t in PTYPES:
            for e in table[t]:
                if e["name"] == name:
                    return t, e
        raise AinbError(f"{self.name}: node {i} ({self.nodes[i]['name']}) has no {kind[:-1]} {name}")

    @staticmethod
    def _coerce(t, v, old):
        if t == "int":
            return int(v)
        if t == "bool":
            return bool(v)
        if t == "float":
            return float(v)
        if t == "string":
            return str(v)
        if t == "vec3":
            return [float(x) for x in v]
        raise AinbError(f"a {t} parameter can't be set")

    def set_property(self, node, name, value):
        i = self.node(node)
        t, e = self._param(i, "properties", name)
        if e.get("flags", 0) & BB_INDEXED:
            raise AinbError(f"{self.name}: property {name} of node {i} reads the blackboard")
        e["value"] = self._coerce(t, value, e.get("value"))

    def set_input(self, node, name, value):
        """An input's own value (used when no node or blackboard feeds it)."""
        i = self.node(node)
        t, e = self._input(i, name)
        if e["node"] >= 0 or e["node"] <= -100 or e["flags"] & BB_INDEXED:
            raise AinbError(f"{self.name}: input {name} of node {i} is fed by another node or the blackboard")
        e["value"] = self._coerce(t, value, e["value"])
        if not e["flags"] & 0x1800000:
            e["flags"] = CONST_FLAGS

    def add_bb(self, t, name, default=None, like=None):
        """Adds a new entry to this file's blackboard (BlackboardType 0) at the end of its type's list, so every
        existing entry keeps its index. Parameters read blackboard entries by type and index. Idempotent.
        like: an existing entry of the same type. The new one copies its flags and its file reference, which points
        at an actor blackboard table (an instance parameter's, e.g. the Treasure Chest Game chest's DropViewActor)."""
        if t not in BBTYPES or t == "ptr":
            raise AinbError(f"{self.name}: blackboard type {t} can't be added")
        if any(e["name"] == name for e in self.bb[t]):
            return
        if default is None:
            default = {"string": "", "int": 0, "u32": 0, "float": 0.0, "bool": False, "vec3": [0.0, 0.0, 0.0]}[t]
        e = {"name": name, "flags": 0, "notes": "",
             "default": int(default) if t == "u32" else self._coerce(t, default, default)}
        if like is not None:
            src = next((x for x in self.bb[t] if x["name"] == like), None)
            if src is None:
                raise AinbError(f"{self.name}: no {t} blackboard entry {like}")
            e["flags"] = src["flags"]
            if "file" in src:
                e["file"] = src["file"]
        self.bb[t].append(e)

    def read_bb(self, node, name, bb_name):
        """Makes input `name` of `node` read blackboard entry `bb_name` of its type (the first one with that name),
        like the game's blackboard-read inputs do with flags 0x80000000 | the entry's index. No node feeds it after
        that."""
        i = self.node(node)
        t, e = self._input(i, name)
        idx = next((k for k, x in enumerate(self.bb.get(t) or []) if x["name"] == bb_name), None)
        if idx is None:
            raise AinbError(f"{self.name}: no {t} blackboard entry {bb_name}")
        old = e["node"]
        if old <= -100:
            raise AinbError(f"{self.name}: input {name} of node {i} is a multi-input")
        e["node"], e["plug"], e["flags"] = -1, 0, BB_INDEXED | idx
        if old >= 0 and t in self.FEED_KIND:
            kind = self.FEED_KIND[t]
            self.nodes[i]["plugs"][kind] = [pl for pl in self.nodes[i]["plugs"][kind]
                                            if not (pl["name"] == name and pl["node"] == old)]
        self.refresh_queries(i)

    def bb_readers(self, t, bb_name):
        """[(node, input name)] for the inputs of type `t` that read blackboard entry `bb_name` in the plain 0x8000000N
        form, any entry with that name. StringSelectors are left out because their input link holds a string and
        feed can't do that."""
        names = [x["name"] for x in self.bb.get(t) or []]
        return [(i, e["name"]) for i, nd in enumerate(self.nodes) if nd["type"] != 5
                for e in nd["inputs"].get(t, []) if e.get("flags", 0) & 0xFFFF0000 == BB_INDEXED
                and (e["flags"] & 0xFFFF) < len(names) and names[e["flags"] & 0xFFFF] == bb_name]

    def feed_bb_reads(self, t, bb_name, src, output):
        """Feeds every input bb_readers lists from src's output instead (feed). Returns how many."""
        todo = self.bb_readers(t, bb_name)
        for i, name in todo:
            self.feed(src, output, i, name)
        return len(todo)

    def set_bb_default(self, name, value):
        for t in BBTYPES:
            for e in self.bb[t]:
                if e["name"] == name:
                    if t == "ptr":
                        raise AinbError(f"{self.name}: pointer blackboard entries have no default")
                    e["default"] = int(value) if t == "u32" else self._coerce(t, value, e["default"])
                    return
        raise AinbError(f"{self.name}: no blackboard entry {name}")

    # Write
    def dump(self):
        pool = StringPool(bytes(self.pool.raw))
        S = pool.offset
        out = bytearray(0x74)
        for c in self.commands:
            out += struct.pack("<I16sHH", S(c["name"]), c["guid"], c["main"], c["secondary"])
        node_at = len(out)
        out += bytes(0x3C * len(self.nodes))
        # blackboard
        o_bb = len(out)
        idx = voff = 0
        for t in BBTYPES:
            out += struct.pack("<4H", len(self.bb[t]), idx, voff, 0)
            idx += len(self.bb[t])
            voff += len(self.bb[t]) * BB_VALUE_SIZE[t]
        for t in BBTYPES:
            for e in self.bb[t]:
                w = S(e["name"]) | (e["flags"] << 22)
                if "file" in e:
                    w |= (e["file"] << 24) | 0x80000000
                out += struct.pack("<II", w, S(e["notes"]))
        for t in BBTYPES:
            for e in self.bb[t]:
                if t == "u32":
                    out += struct.pack("<I", e["default"])
                elif t != "ptr":
                    out += self._value_bytes(t, e["default"], S)
        for f in self.bb_files:
            out += struct.pack("<4I", S(f["path"]), *f["hashes"])
        # global tables, filled while laying out the nodes
        props = {t: [] for t in PTYPES}
        inputs = {t: [] for t in PTYPES}
        outputs = {t: [] for t in PTYPES}
        att_index = []
        node_params = []
        for n in self.nodes:
            a = len(out)
            node_params.append(a)
            for t in PTYPES:
                base = n.get("_prop_odd", {}).get(t, len(props[t])) if not n["properties"][t] else len(props[t])
                out += struct.pack("<II", base, len(n["properties"][t]))
                props[t] += n["properties"][t]
            for t in PTYPES:
                ib = n.get("_in_odd", {}).get(t, len(inputs[t])) if not n["inputs"][t] else len(inputs[t])
                ob = n.get("_out_odd", {}).get(t, len(outputs[t])) if not n["outputs"][t] else len(outputs[t])
                out += struct.pack("<4I", ib, len(n["inputs"][t]), ob, len(n["outputs"][t]))
                inputs[t] += n["inputs"][t]
                outputs[t] += n["outputs"][t]
            k = 0
            for kind in range(PLUG_KINDS):
                cnt = len(n["plugs"][kind])
                out += struct.pack("<BB", cnt, n.get("_plug_odd", {}).get(kind, k))
                k += cnt
            flat = [pl for kind in range(PLUG_KINDS) for pl in n["plugs"][kind]]
            q = len(out) + 4 * len(flat)
            for pl in flat:
                out += struct.pack("<I", q)
                q += 8 + len(pl["extra"])
            for pl in flat:
                second = pl["transition"] if "transition" in pl else S(pl["name"])
                out += struct.pack("<iI", pl["node"], second) + pl["extra"]
        att_base = []
        for n in self.nodes:
            att_base.append(n.get("_att_odd", len(att_index)) if not n["attachments"] else len(att_index))
            att_index += n["attachments"]
        o_attidx = len(out)
        for v in att_index:
            out += struct.pack("<I", v)
        o_att = len(out)
        par0 = o_att + 16 * len(self.attachments)
        for k, a_ in enumerate(self.attachments):
            out += struct.pack("<IIHHI", S(a_["name"]), par0 + 0x64 * k, a_["exb_count"], a_["exb_size"], a_["hash"])
        for a_ in self.attachments:
            out += struct.pack("<I", a_["debug"])
            for t in PTYPES:
                out += struct.pack("<II", len(props[t]), len(a_["properties"][t]))
                props[t] += a_["properties"][t]
            end = len(out) + 0x30
            out += struct.pack("<12I", *[0, end] * 6)
        o_prop = len(out)
        out += bytes(24)
        for j, t in enumerate(PTYPES):
            struct.pack_into("<I", out, o_prop + 4 * j, len(out))
            for e in props[t]:
                if t == "ptr":
                    out += struct.pack("<III", S(e["name"]), S(e["class"]), e["flags"])
                else:
                    out += struct.pack("<II", S(e["name"]), e["flags"]) + self._value_bytes(t, e["value"], S)
        o_io = len(out)
        out += bytes(48)
        for j, t in enumerate(PTYPES):
            struct.pack_into("<I", out, o_io + 8 * j, len(out))
            for e in inputs[t]:
                if t == "ptr":
                    out += struct.pack("<IIhhII", S(e["name"]), S(e["class"]), e["node"], e["plug"], e["flags"],
                                       e["value"])
                else:
                    out += struct.pack("<IhhI", S(e["name"]), e["node"], e["plug"], e["flags"])
                    out += self._value_bytes(t, e["value"], S)
            struct.pack_into("<I", out, o_io + 8 * j + 4, len(out))
            for e in outputs[t]:
                out += struct.pack("<I", S(e["name"]) | (e["flag"] << 31))
                if t == "ptr":
                    out += struct.pack("<I", S(e["class"]))
        o_multi = len(out)
        for m in self.multi:
            out += struct.pack("<hhI", *m)
        o_trans = len(out)
        if self.transitions:
            q = o_trans + 4 * len(self.transitions)
            for tr in self.transitions:
                out += struct.pack("<I", q)
                q += 8 if "command" in tr else 4
            for tr in self.transitions:
                out += struct.pack("<I", tr["flags"])
                if "command" in tr:
                    out += struct.pack("<I", S(tr["command"]))
        o_query = len(out)
        for qv in self.queries:
            out += struct.pack("<HH", *qv)
        o_exb = 0
        if self.exb is not None:
            o_exb = len(out)
            out += self.exb
        o_module = len(out)
        out += struct.pack("<I", len(self.modules))
        for m in self.modules:
            out += struct.pack("<III", S(m["path"]), S(m["category"]), m["count"])
        o_action = len(out)
        out += struct.pack("<I", len(self.actions))
        for a_ in self.actions:
            out += struct.pack("<iII", a_["node"], S(a_["slot"]), S(a_["action"]))
        o_bbid = len(out)
        out += struct.pack("<II", *self.bb_id)
        o_repl = len(out)
        rp = self.replacement
        out += struct.pack("<BBHhh", rp["replaced"], rp["pad"], len(rp["entries"]), rp["node"], rp["attachment"])
        for e in rp["entries"]:
            out += struct.pack("<BBhhh", *e)
        o_x6c = len(out)
        out += struct.pack("<I", self.x6c)
        o_enum = len(out)
        out += struct.pack("<I", len(self.enums))
        for e in self.enums:
            out += struct.pack("<III", *e)
        # Write the nodes now that their parameter offsets are known. Resolve names before writing the pool.
        for i, n in enumerate(self.nodes):
            NODE.pack_into(out, node_at + 0x3C * i, n["type"], n["index"], len(n["attachments"]), n["flags"],
                           n["flags2"], S(n["name"]), n["hash"], n["unk10"], node_params[i], n["exb_count"],
                           n["exb_size"], n["multi_count"], n["pad1e"], att_base[i], n["query_base"],
                           n["query_count"], n["x28"], n["guid"])
        fname, catname = S(self.name), S(self.category)
        o_str = len(out)
        out += pool.raw
        HEADER.pack_into(out, 0, b"AIB ", self.version, fname, len(self.commands), len(self.nodes), self.nquery,
                         len(self.attachments), self.nout, o_bb, o_str, o_enum, o_prop, o_trans, o_io, o_multi,
                         o_att, o_attidx, o_exb, o_repl, o_query, o_trans, self.x54, self.x58, o_module, catname,
                         self.cat, o_action, o_x6c, o_bbid)
        return bytes(out)

    @staticmethod
    def _value_bytes(t, v, S):
        if t == "int":
            return struct.pack("<i", v)
        if t == "bool":
            return struct.pack("<I", int(v))
        if t == "float":
            return struct.pack("<I", _u32f(v))
        if t == "string":
            return struct.pack("<I", S(v))
        if t == "vec3":
            return struct.pack("<3I", *map(_u32f, v))
        raise AinbError(t)


def _fmt_value(v):
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, list):
        return "(" + ", ".join(_fmt_value(x) for x in v) + ")"
    return repr(v)


def describe_node(a, i):
    """One node as text: name, parameters (with their sources) and links."""
    n = a.nodes[i]
    kind = NODE_TYPES.get(n["type"], n["type"])
    out = [f"  [{i}] {n['name'] or kind}" + (f" ({kind})" if n["name"] and n["type"] else "")
           + (f" flags={n['flags']}" if n["flags"] else "")]
    for t in PTYPES:
        for e in n["properties"][t]:
            src = f" <- bb#{e['flags'] & 0xFFFF} ({e['flags']:#x})" if e.get("flags", 0) & BB_INDEXED else ""
            out.append(f"      prop {t} {e['name']} = {_fmt_value(e.get('value', e.get('class')))}{src}")
        for e in n["inputs"][t]:
            if e["node"] >= 0:
                src = f" <- node {e['node']} out {e['plug']}"
            elif e["node"] <= -100:
                src = f" <- multi {-100 - e['node']} x{e['plug']}"
            elif e["flags"] & BB_INDEXED:
                src = f" <- bb#{e['flags'] & 0xFFFF} ({e['flags']:#x})"
            else:
                src = ""
            out.append(f"      in {t} {e['name']} = {_fmt_value(e['value'])}{src}")
        for e in n["outputs"][t]:
            out.append(f"      out {t} {e['name']}")
    for kind_, plugs in enumerate(n["plugs"]):
        for pl in plugs:
            label = pl.get("name", f"transition {pl.get('transition')}")
            out.append(f"      plug{kind_} {label} -> node {pl['node']}" + (f" +{pl['extra'].hex()}" if pl["extra"] else ""))
    for k in n["attachments"]:
        out.append(f"      attachment {a.attachments[k]['name']}")
    return "\n".join(out)


def describe(a):
    """A readable listing of a parsed file: blackboard, commands, then every node with its parameters and links."""
    out = [f"{a.name} ({a.category}), {len(a.nodes)} nodes"]
    for t in BBTYPES:
        for e in a.bb[t]:
            src = f" [file {a.bb_files[e['file']]['path']}]" if "file" in e else ""
            out.append(f"  bb {t} {e['name']} = {_fmt_value(e['default'])}{src}")
    for c in a.commands:
        out.append(f"  command {c['name']} -> node {c['main']}")
    out += [describe_node(a, i) for i in range(len(a.nodes))]
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from romtools import Romfs, sarc_files
    if len(sys.argv) < 3:
        sys.exit("usage: python tools/ainb.py ROMFS FILE.ainb | Pack/Actor/X.pack.zs[:AI/inner.ainb]")
    fs = Romfs(sys.argv[1], os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "original"))
    target = sys.argv[2]
    if ".pack.zs" in target:
        pack, _, inner = target.partition(":")
        files = sarc_files(fs.read(pack))
        for name in ([inner] if inner else sorted(f for f in files if f.endswith(".ainb"))):
            print(describe(Ainb(files[name])))
    else:
        print(describe(Ainb(fs.raw(target))))
