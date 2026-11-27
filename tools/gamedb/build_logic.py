"""Logic section of the game-logic index, with what the AINB graphs (Logic/, Sequence/, AI/) and the NPC schedules
(Component/AIScheduleParam, Pack/AIScheduleParam.pack.zs, AISchedule/) say about the game's logic.

Each AINB record (SCHEMA.md "logic.json") has the compact node list, the actors each module drives with a formula
for every gate input, and the GameData it reads and writes (a write's "when" is the formula of its trigger input). It
also lists inputs that read an output not flagged "Is Output", which read their default forever, and
observer/query nodes whose outputs feed nothing.

Formulas (prefix form, SCHEMA.md) are built by walking a gate's input back to its leaves. The combinators below
behave the way the graphs show (OperateORFixInputTrueWithReset.module spells its latch out in plain OR/AND nodes):
    OperateAND / OperateOR            True = AND/OR(BoolMulti...), False = NOT(that)
    ...FixInputTrue                   LATCH(x): true from the first time x is true, for the module's life
    ...Pulse                          PULSE(x): true for the one update in which x becomes true
    UpdateOnce = true                 ONCE(x): x as evaluated once, when the module starts
    OperateInvertBool                 NOT(x)
    HoldGeneralDelayBool              DELAY(x): x, Frame frames late
    a feedback loop out = OR(set, AND(hold, out))     LATCH(set, hold) (the WithReset module: hold = NOT(Reset))
    module calls (InvBool.module, prefab modules ...) the callee's ModuleIF_Output formula, its arg:<Name> leaves
                                      replaced by the call node's inputs, its node leaves prefixed by the call node
                                      (node:<call>/<callee node>.<out>)
Leaves: flag:<GameData bool / BoolExp / HavePlayedEvent.<event> / IsVisitLocation.<location>>[index],
int:<a><op><b> (also enums: int:<enum>=<value>), step:<Challenge><op><Step> (> IsAfter, < IsBefore, = IsEqual),
player:child|adult|boots=N|state=N|bag:<item>|stock:<item>|in_room|in_space|equip:<actor>|riding|aims_at_sun,
time:day|night|HH:MM-HH:MM (OperateIsInTimeRange: start A, end C, the tested time B; an unwired B is a constant)|
appearance@HH:MM-HH:MM|prime_fishing, node:<i>.<out> (actor outputs, timers, lotteries...), unknown:<node>#<i>.<out>
(a node that reads data and isn't interpreted yet), const:true|false; and beyond SCHEMA.md:
    hit:<actor>@<area|area>   a sensor observer: that actor (Player, Item_Bomb, ...; tag=/cucco# forms) in the areas
                              (true only while an area exists: see the area actor's own Logic_Delete gate)
    arg:<Name>                a module interface input (ModuleIF_Input_*), in a module's own record
    bb:<Key>                  the module's blackboard bool
    game:<what>               engine state backed by save data without a GameData name (Big Poe fences, autogen data)
    $<Name> inside a leaf     a module's string/number argument (flag:$GameDataNameBool), filled in when inlined
Int operands: a GameData int's name, hour/min, count{a;b;...} (OperateBoolCount), a+b, node:<i>.<out>.
An input linked to an output its node doesn't flag "Is Output" reads false/0 forever (C1, no vanilla file has one).
The formula says const:false there and unflagged_reads names the link.

Schedules are {"kind": "schedule", "actor", "states": [{"cond", "neg"?, "events": [{"type", "setting"}], "actions"}],
"default", "rule": "last true wins"}. The quest-ordered conditions in the data only make sense that way (summary
schedule_rule.evidence). Pack/AIScheduleParam.pack.zs holds 187 more, per quest step (<Challenge>_<Step>_<Actor>, with
$parent inheritance resolved), in one "schedule_pack" record. A record that inlines a called module keeps the callee's
signature in "deps", and finish() re-indexes it when an overlay changed the callee.
"""
import hashlib
import os
import re
import struct
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ainb import Ainb, BB_INDEXED, NODE_TYPES, PTYPES  # noqa: E402
from romtools import byml_load, murmur3_32  # noqa: E402

SECTION = "logic"
VERSION = 1

AINB_DIRS = {"Logic": "logic", "Sequence": "sequence", "AI": "ai"}
SCHED_DIR = "Component/AIScheduleParam"
SCHED_PACK = "Pack/AIScheduleParam.pack.zs"
RULE = "last true wins"
T, F = "const:true", "const:false"
MAX_LEAVES = 400          # a formula larger than this is cut at the node it came from (node:<i>.<out>)
CALL_DEPTH = 6
BBTYPE = {"int": "int", "bool": "bool", "float": "float", "string": "string", "vec3": "vec3", "ptr": "ptr"}
# unread outputs of these node kinds are dead_outputs (an observer or query nobody reads)
OBSERVER = re.compile(r"^(Hold|Operate|Query|SeqQuery|EventQuery|Qiery)")
# an uninterpreted node is unknown: if its name says it reads save data, the player, items or time, else node:
DATALIKE = re.compile(r"GameData|Challenge|Item|Stock|Pouch|DateTime|TimeDiv|Wm[A-Z]|Childhood|Adulthood|Equip|Visit|"
                      r"Save|TalkFlag|HavePlayed|Step|Boots|Rupee|Heart|Poe|Bottle|Sold")
LEAF_RX = re.compile(r"\b(unknown):([^,()\s#]+)#([^,()\s]+)")


# Files

def files(root):
    out = []
    for d in AINB_DIRS:
        out += common.list_files(root, d, r"\.ainb$")
    out += common.list_files(root, SCHED_DIR, r"\.bgyml$")
    base = os.path.join(root, "AISchedule")
    if os.path.isdir(base):
        for sub in sorted(os.listdir(base)):
            out += common.list_files(root, f"AISchedule/{sub}", r"\.bgyml$")
    if os.path.isfile(os.path.join(root, SCHED_PACK)):
        out.append(SCHED_PACK)
    return out


def index_file(fs, rel):
    top = rel.split("/")[0]
    if top in AINB_DIRS:
        return index_ainb(fs, rel)
    if rel.startswith(SCHED_DIR + "/"):
        rec = schedule_record(common.read_byml(fs, rel), os.path.basename(rel).split(".")[0])
        rec["sig"] = _sig(fs.raw(rel))
        return rec
    if rel == SCHED_PACK:
        return index_schedule_pack(fs, rel)
    if top == "AISchedule":
        return {"kind": "aischedule_base", "type": rel.split("/")[1],
                "data": common.jsonable(common.read_byml(fs, rel)), "sig": _sig(fs.raw(rel))}
    raise ValueError(f"not a logic file: {rel}")


def _sig(data):
    return hashlib.sha1(data).hexdigest()[:12]


# Formulas

def _flat(op, xs):
    out = []
    for x in xs:
        if isinstance(x, tuple) and (x[0] == op or x[0] == "ARGS"):
            out += _flat(op, x[1:])
        else:
            out.append(x)
    return out


def AND(*xs):
    xs = _flat("AND", xs)
    if F in xs:
        return F
    xs = list(dict.fromkeys(x for x in xs if x != T))
    return T if not xs else xs[0] if len(xs) == 1 else ("AND", *xs)


def OR(*xs):
    xs = _flat("OR", xs)
    if T in xs:
        return T
    xs = list(dict.fromkeys(x for x in xs if x != F))
    return F if not xs else xs[0] if len(xs) == 1 else ("OR", *xs)


def NOT(x):
    if isinstance(x, tuple) and x[0] == "ARGS":
        x = AND(*x[1:])
    if x == T:
        return F
    if x == F:
        return T
    if isinstance(x, tuple) and x[0] == "NOT":
        return x[1]
    return ("NOT", x)


def WRAP(op, x):
    """LATCH/ONCE/DELAY of a constant is that constant, and PULSE(const:false) never fires."""
    if isinstance(x, tuple) and x[0] == "ARGS":
        x = AND(*x[1:])
    if x in (T, F) and (op != "PULSE" or x == F):
        return x
    return (op, x)


def LATCH2(set_, hold):
    if hold == F:
        return set_
    if hold == T:
        return WRAP("LATCH", set_)
    if set_ == F:
        return F
    return ("LATCH", set_, hold)


def ONCEIF(cond, x):
    if cond == T:
        return WRAP("ONCE", x)
    if cond == F:
        return x
    return ("ONCEIF", cond, x)


def rebuild(f, leaf):
    """f with every leaf mapped through leaf(str) -> formula, simplified again."""
    if isinstance(f, str):
        return leaf(f)
    op, args = f[0], [rebuild(x, leaf) for x in f[1:]]
    if op == "AND":
        return AND(*args)
    if op == "OR":
        return OR(*args)
    if op == "NOT":
        return NOT(args[0])
    if op == "LATCH":
        return LATCH2(args[0], args[1]) if len(args) == 2 else WRAP("LATCH", args[0])
    if op == "ONCEIF":
        return ONCEIF(args[0], args[1])
    if op == "ARGS":
        return ("ARGS", *args) if len(args) > 1 else args[0]
    return WRAP(op, args[0]) if len(args) == 1 else (op, *args)


def size(f):
    return 1 if isinstance(f, str) else sum(size(x) for x in f[1:])


def fstr(f):
    if isinstance(f, str):
        return f
    op = "AND" if f[0] == "ARGS" else f[0]
    return f"{op}(" + ", ".join(fstr(x) for x in f[1:]) + ")"


def contains(f, leaf):
    return f == leaf if isinstance(f, str) else any(contains(x, leaf) for x in f[1:])


def _clean(s):
    return re.sub(r"[,()\s]", "_", str(s))


def challenge_of(path):
    return str(path or "").rsplit("/", 1)[-1].split(".", 1)[0]


def actor_of(path):
    """'Work/Actor/Item_Bomb.engine__actor__ActorParam.gyml' -> 'Item_Bomb'."""
    return str(path or "").rsplit("/", 1)[-1].split(".", 1)[0]


def _num(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


# One AINB as a graph

_CALLEES = {}


class Graph:
    def __init__(self, fs, a, rel, depth=0):
        self.fs, self.a, self.rel, self.depth = fs, a, rel, depth
        self.memo, self.busy = {}, set()
        self.deps = {}           # callee rel -> sig, transitively (an overlay re-indexes this file when one changes)

    # Basics
    def nm(self, i):
        n = self.a.nodes[i]
        return n["name"] or NODE_TYPES.get(n["type"], str(n["type"]))

    def oname(self, i, t, k):
        outs = self.a.nodes[i]["outputs"][t]
        return outs[k]["name"] if 0 <= k < len(outs) else f"#{k}"

    def find_in(self, i, name, types=PTYPES):
        for t in types:
            for e in self.a.nodes[i]["inputs"][t]:
                if e["name"] == name:
                    return t, e
        return None, None

    def prop(self, i, name, default=None):
        for t in PTYPES:
            for e in self.a.nodes[i]["properties"][t]:
                if e["name"] == name:
                    if e.get("flags", 0) & BB_INDEXED:
                        return "bb:" + self.bb_name(t, e["flags"])
                    return e.get("value", e.get("class"))
        return default

    def bb_name(self, t, flags):
        if flags >> 24 == 0x80:
            lst = self.a.bb.get(BBTYPE[t]) or []
            k = flags & 0xFFFF
            return lst[k]["name"] if k < len(lst) else f"#{k}"
        return f"#{flags:#x}"

    def link_out(self, s, t, k, flags=0):
        """(type, output entry or None) that a link to node s, output k reads. A node-fed input with a bit-31 form
        reads another type's output, otherwise it's the input's type. That form is 0xC2000000 | n, one component n of a
        vec3 output, like QueryMathSubF32 reading a position's Y."""
        outs = self.a.nodes[s]["outputs"] if 0 <= s < len(self.a.nodes) else {}
        if not flags & BB_INDEXED and 0 <= k < len(outs.get(t, [])):
            return t, outs[t][k]
        for t2 in ((t,) if not flags & BB_INDEXED else ()) + ("vec3", "float", "int", "bool", "string", "ptr"):
            if 0 <= k < len(outs.get(t2, [])):
                return t2, outs[t2][k]
        return t, None

    def sources(self, t, e):
        """[("n", node, output index) | ("bb", name) | ("c", value)] of an input entry."""
        if e.get("node", -1) >= 0:
            return [("n", e["node"], e["plug"])]
        if e.get("node", -1) <= -100:
            b = -100 - e["node"]
            return [("n", m[0], m[1]) for m in self.a.multi[b:b + e["plug"]]]
        if e.get("flags", 0) & BB_INDEXED:
            return [("bb", self.bb_name(t, e["flags"]))]
        return [("c", e.get("value"))]

    # Bool formulas
    def bools(self, i, name):
        """The formulas feeding bool input `name` of node i (several for a multi-input)."""
        t, e = self.find_in(i, name, ("bool",))
        if e is None:
            return [F]
        out = []
        fl = e.get("flags", 0) if e.get("node", -1) >= 0 else 0
        for kind, *v in self.sources(t, e):
            if kind == "n" and fl & BB_INDEXED:  # a bit-31 form can read another type's output
                t2, oe = self.link_out(v[0], t, v[1], fl)
                if t2 != "bool" or oe is None:
                    out.append(f"node:{v[0]}.{oe['name'] if oe else '#' + str(v[1])}")
                    continue
            if kind == "n":
                t2, oe = self.link_out(v[0], "bool", v[1])
                if oe is not None and not oe["flag"]:  # never computed, so the input reads false forever (C1)
                    out.append(F)
                    continue
                out.append(self.out(v[0], "bool", v[1]))
            elif kind == "bb":
                out.append("bb:" + _clean(v[0]))
            else:
                out.append(T if v[0] else F)
        return out

    def bool_in(self, i, name, how=AND):
        xs = self.bools(i, name)
        return xs[0] if len(xs) == 1 else how(*xs)

    def out(self, i, t, k):
        key = (i, t, k)
        if key in self.memo:
            return self.memo[key]
        if not 0 <= i < len(self.a.nodes):
            return f"node:{i}.#{k}"
        o = self.oname(i, t, k)
        me = f"node:{i}.{o}"
        if o.startswith("#"):
            return me
        if key in self.busy:
            return me
        self.busy.add(key)
        try:
            f = self._out(i, t, o) if t == "bool" else me
        finally:
            self.busy.discard(key)
        if not isinstance(f, str) and contains(f, me):
            f = self._latch(f, me)
        if size(f) > MAX_LEAVES:
            f = me
        self.memo[key] = f
        return f

    @staticmethod
    def _latch(f, me):
        """out = OR(set..., AND(hold..., out)) -> LATCH(set, hold); other loops keep their node leaf."""
        if f[0] == "OR":
            loops = [x for x in f[1:] if isinstance(x, tuple) and x[0] == "AND" and me in x[1:]]
            rest = [x for x in f[1:] if x not in loops]
            if len(loops) == 1 and not any(contains(x, me) for x in rest):
                hold = AND(*[x for x in loops[0][1:] if x != me])
                if not contains(hold, me):
                    return LATCH2(OR(*rest), hold)
        return f

    def _out(self, i, t, o):
        n = self.a.nodes[i]
        name = self.nm(i)
        if n["flags"] & 2:
            return self.call_out(i, o)
        if n["type"] == 104:  # ModuleIF_Input_Bool
            return "arg:" + _clean(self.prop(i, "Name", o))
        if name.startswith("ActorLogic"):
            return f"node:{i}.{o}"
        h = HANDLERS.get(name)
        if h is None:
            for pre, fn in PREFIX_HANDLERS:
                if re.search(pre, name):
                    h = fn
                    break
        if h is not None:
            r = h(self, i, o)
            if r is not None:
                return r
        if DATALIKE.search(name):
            return f"unknown:{_clean(name)}#{i}.{o}"
        return f"node:{i}.{o}"

    # Operands (int/float/string)
    def operand(self, i, name):
        t, e = self.find_in(i, name, ("int", "float", "string", "bool"))
        if e is None:
            return "?"
        srcs = self.sources(t, e)
        if not srcs:
            return "?"
        kind, *v = srcs[0]
        if kind == "c":
            return _clean(_num(v[0]))
        if kind == "bb":
            return "bb:" + _clean(v[0])
        fl = e.get("flags", 0) if e.get("node", -1) >= 0 else 0
        t2, oe = self.link_out(v[0], t, v[1], fl)
        if fl & BB_INDEXED and (t2 != t or oe is None):
            return f"node:{v[0]}.{oe['name'] if oe else '#' + str(v[1])}"
        if oe is not None and not oe["flag"] and t in ("int", "float"):
            return "0"  # an output never computed reads 0 (C1)
        return self.node_operand(v[0], t, v[1])

    def node_operand(self, s, t, k):
        o = self.oname(s, t, k)
        name = self.nm(s)
        n = self.a.nodes[s]
        if n["type"] in (100, 101, 103):  # ModuleIF_Input_S32/F32/String
            return "$" + _clean(self.prop(s, "Name", o))
        if name == "HoldGameDataGetIntSimple":
            return _clean(self.str_in(s, "GameDataNameInt")) + self.index_sfx(s)
        if name in ("HoldWmGetDateTime", "HoldWmGetAppearanceDateTime"):
            return ("appearance_" if "Appearance" in name else "") + o.lower()
        if name == "OperateBoolCount":
            xs = self.bools(s, "BoolMulti")
            if all(isinstance(x, str) for x in xs):
                at = {x.split("@", 1)[1] for x in xs if x.startswith("hit:") and "@" in x}
                if len(at) == 1 and all(x.startswith("hit:") and "@" in x for x in xs):  # one area set: say it once
                    return "count{hit:" + ";".join(x[4:].split("@", 1)[0] for x in xs) + "@" + at.pop() + "}"
                return "count{" + ";".join(xs) + "}"
        if name == "OperateAddInt":
            return f"{self.operand(s, 'Int_A')}+{self.operand(s, 'Int_B')}"
        if re.match(r"(Seq)?Query.*GameData(Int|Float|String64|Enum)", name):
            return self.gd_name(s)
        return f"node:{s}.{o}"

    def str_in(self, i, name):
        t, e = self.find_in(i, name, ("string",))
        if e is None:
            v = self.prop(i, name)
            return v if v is not None else "?"
        kind, *v = (self.sources(t, e) or [("c", "?")])[0]
        if kind == "c":
            return v[0]
        if kind == "bb":
            return "bb:" + v[0]
        return self.node_operand(v[0], t, v[1])

    def index_sfx(self, i):
        for nm_ in ("GameDataArrayIndex", "GameDataIndex"):
            t, e = self.find_in(i, nm_, ("int",))
            if e is not None:
                op = self.operand(i, nm_)
                return "" if op == "-1" else f"[{op}]"
        return ""

    def gd_name(self, i):
        """GameData name of a Seq/AI accessor, either GameDataFullName or Struct.Member through ParentStruct."""
        for key in ("GameDataFullName", "GameDataName"):
            t, e = self.find_in(i, key, ("string",))
            if e is not None:
                base = self.str_in(i, key)
                pt, pe = self.find_in(i, "ParentStruct", ("ptr",))
                if pe is not None and pe["node"] >= 0:
                    base = f"{self.gd_name(pe['node'])}.{base}"
                return _clean(base) + self.index_sfx(i)
        return "?"

    def areas(self, i):
        t, e = self.find_in(i, "SensorHitInfoMulti", ("ptr",))
        names = []
        for kind, *v in (self.sources(t, e) if e is not None else []):
            if kind != "n":
                continue
            s = v[0]
            if self.a.nodes[s]["type"] == 105:
                names.append("$" + str(self.prop(s, "Name", "?")))
            else:
                names.append(str(self.prop(s, "InstanceName", self.nm(s))))
        return _clean("|".join(names) or "?")

    # Module calls
    def callee_rel(self, i):
        name = self.nm(i)
        path = name + ".ainb"
        cat = next((m["category"] for m in self.a.modules if m["path"] == path), None)
        for d in ([cat] if cat else []) + [self.rel.split("/")[0], "Logic", "Sequence", "AI"]:
            try:
                if d in AINB_DIRS and os.path.exists(self.fs.path(f"{d}/{path}")):
                    return f"{d}/{path}"
            except FileNotFoundError:
                pass
        return None

    def call_out(self, i, o):
        me = f"node:{i}.{o}"
        crel = self.callee_rel(i)
        if crel is None or self.depth >= CALL_DEPTH:
            return me
        outs, deps = callee_outputs(self.fs, crel, self.depth + 1)
        self.deps.update(deps)
        f = outs.get(o)
        if f is None:
            return me
        return rebuild(f, lambda s: self._subst(i, s))

    def _subst(self, i, s):
        if s.startswith("arg:"):
            xs = self.bools(i, s[4:])
            return xs[0] if len(xs) == 1 else ("ARGS", *xs)
        s = re.sub(r"\bnode:", f"node:{i}/", s)
        s = re.sub(r"\b(unknown:[^,()\s#]*#)", rf"\g<1>{i}/", s)
        s = re.sub(r"\bbb:", f"bb:{i}/", s)
        return re.sub(r"\$([A-Za-z0-9_]+)", lambda m: self._arg_text(i, m.group(1)), s)

    def _arg_text(self, i, name):
        t, e = self.find_in(i, name, ("string", "int", "float", "ptr"))
        if e is None:
            return "$" + name
        if t == "ptr":
            srcs = [x for x in self.sources(t, e) if x[0] == "n"]
            if srcs:
                s = srcs[0][1]
                if self.a.nodes[s]["type"] == 105:
                    return "$" + str(self.prop(s, "Name", "?"))
                return _clean(self.prop(s, "InstanceName", self.nm(s)))
            return "?"
        return _clean(self.operand(i, name))


def callee_outputs(fs, rel, depth):
    """{output Name: formula over arg:<input> leaves}, {rel: sig} of a module file (cached per worker)."""
    key = (fs.root, tuple(fs.overlays), rel)
    if key in _CALLEES:
        return _CALLEES[key]
    _CALLEES[key] = ({}, {})  # give recursive calls an empty result so they stop here
    raw = common.read_any(fs, rel)
    a = Ainb(raw)
    g = Graph(fs, a, rel, depth)
    outs = {}
    for i, n in enumerate(a.nodes):
        if n["type"] == 204:  # ModuleIF_Output_Bool
            ins = n["inputs"]["bool"]
            if ins:
                outs[str(g.prop(i, "Name", ins[0]["name"]))] = g.bool_in(i, ins[0]["name"])
    deps = dict(g.deps)
    deps[rel] = _sig(raw)
    _CALLEES[key] = (outs, deps)
    return outs, deps


# Leaf handlers

def _neg(cond, f):
    return NOT(f) if cond else f


def h_combinator(g, i, o):
    """OperateAND/OR[FixInputTrue|Pulse] have one value per node (True = it, False = NOT(it)), so a loop
    through either output shows up as a loop on node:<i>.True."""
    key, me = (i, "base"), f"node:{i}.True"
    if key in g.busy:
        return NOT(me) if o == "False" else me
    if key not in g.memo:
        g.busy.add(key)
        try:
            name = g.nm(i)
            how = OR if name.replace("Operate", "")[:2] == "OR" else AND
            xs = g.bools(i, "BoolMulti")
            if "FixInputTrue" in name and how is OR:  # a latch's own output among its inputs adds nothing
                xs = [x for x in xs if x != me]
            base = how(*xs)
            if "FixInputTrue" in name:
                base = WRAP("LATCH", base)
            elif "Pulse" in name:
                base = WRAP("PULSE", base)
            t, e = g.find_in(i, "UpdateOnce", ("bool",))
            if e is not None:
                base = ONCEIF(g.bool_in(i, "UpdateOnce"), base)
        finally:
            g.busy.discard(key)
        if not isinstance(base, str) and contains(base, me):
            base = Graph._latch(base, me)
        g.memo[key] = base
    base = g.memo[key]
    return NOT(base) if o == "False" else base


def h_invert(g, i, o):
    return NOT(g.bool_in(i, "Bool"))


def h_cmp(g, i, o):
    """OperateCompareInt/F32, where A_Bigger is A>B, A_Smaller A<B and Equal A=B. The variable side goes left."""
    name = g.nm(i)
    a_, b_ = ("Int_A", "Int_B") if "Int" in name else ("F32_A", "F32_B")
    return _cmp_leaf(g.operand(i, a_), {"A_Bigger": ">", "A_Smaller": "<", "Equal": "="}.get(o), g.operand(i, b_))


def h_math(g, i, o):
    op = "=" if "Equal" in g.nm(i) else "<="
    return _cmp_leaf(g.operand(i, "Int"), op, g.operand(i, "IntBase"))


def _isnum(s):
    return re.fullmatch(r"-?\d+(\.\d+)?(e-?\d+)?", s) is not None


def _cmp_leaf(a, op, b):
    if op is None:
        return None
    if _isnum(a) and _isnum(b):
        x, y = float(a), float(b)
        return T if {">": x > y, "<": x < y, "=": x == y, "<=": x <= y}[op] else F
    if _isnum(a) and not _isnum(b):
        a, b, op = b, a, {">": "<", "<": ">", "=": "=", "<=": ">="}[op]
    return f"int:{a}{op}{b}"


def h_timerange(g, i, o):
    """OperateIsInTimeRange: B (the time tested, HoldWmGetDateTime) within [A, C) (wrapping midnight)."""
    hb, mb = g.operand(i, "HourB"), g.operand(i, "MinB")
    rng = f"{int(g.operand(i, 'HourA')):02d}:{int(g.operand(i, 'MinA')):02d}-" \
          f"{int(g.operand(i, 'HourC')):02d}:{int(g.operand(i, 'MinC')):02d}" \
        if all(_isnum(g.operand(i, x)) for x in ("HourA", "MinA", "HourC", "MinC")) else "?"
    if _isnum(hb) and _isnum(mb) and rng != "?":  # nothing feeds the tested time, so it's a constant
        a = int(g.operand(i, "HourA")) * 60 + int(g.operand(i, "MinA"))
        c = int(g.operand(i, "HourC")) * 60 + int(g.operand(i, "MinC"))
        b = int(hb) * 60 + int(mb)
        inside = (a <= b < c) if a <= c else (b >= a or b < c)
        return T if inside else F
    pre = "appearance@" if hb.startswith("appearance_") else ""
    return f"time:{pre}{rng}"


def h_gd_bool(g, i, o):
    return "flag:" + _clean(g.str_in(i, "GameDataNameBool")) + g.index_sfx(i)


def h_gd_exp(g, i, o):
    return "flag:" + _clean(g.str_in(i, "GameDataNameBoolExp"))


def h_played(g, i, o):
    return _neg(o == "NoPlay", "flag:HavePlayedEvent." + _clean(g.str_in(i, "EventName")))


def h_step(g, i, o):
    op = {"IsAfter": ">", "IsBefore": "<", "IsEqual": "="}.get(o)
    if op is None:
        return None
    return f"step:{_clean(challenge_of(g.str_in(i, 'ChallengeName')))}{op}{_clean(g.str_in(i, 'ChallengeStepName'))}"


def h_enum(g, i, o):
    leaf = f"int:{_clean(g.str_in(i, 'GameDataNameEnum'))}{g.index_sfx(i)}={_clean(g.str_in(i, 'EnumName'))}"
    return _neg(o == "IsNotEqual", leaf)


def h_visit(g, i, o):
    return _neg(o == "NotVisit", "flag:IsVisitLocation." + _clean(g.str_in(i, "LocationName")))


def h_age(g, i, o):
    return {"Childhood": "player:child", "Adulthood": "player:adult"}.get(o)


def h_boots(g, i, o):
    return _neg(o == "IsNotState", f"player:boots={g.operand(i, 'Boots')}")


def h_pstate(g, i, o):
    return _neg(o == "IsNotState", f"player:state={g.operand(i, 'EventQueryPlayerState')}")


def h_stock(g, i, o):
    item = _clean(actor_of(g.str_in(i, "ActorName")))
    return {"HasBag": f"player:bag:{item}", "NoHasBag": NOT(f"player:bag:{item}"),
            "HasMoreThanZero": f"player:stock:{item}", "NoHas": NOT(f"player:stock:{item}")}.get(o)


def h_room(g, i, o):
    return "player:in_room" if "Room" in g.nm(i) else "player:in_space"


def h_timediv(g, i, o):
    return {"Day": "time:day", "Night": "time:night"}.get(o)


def h_fishing(g, i, o):
    return _neg(o == "Normal", "time:prime_fishing")


def h_sun(g, i, o):
    return "player:aims_at_sun"


def h_observer(g, i, o):
    name = g.nm(i)
    if "Tag" in name:
        who = "tag=" + str(g.str_in(i, "ActorTagName"))
    elif "Cucco" in name:
        who = "cucco#" + str(g.str_in(i, "InstanceName"))
    else:
        who = actor_of(g.str_in(i, "ActorName"))
        if g.find_in(i, "InstanceName", ("string",))[1] is not None:
            who += "#" + str(g.str_in(i, "InstanceName"))
    num = g.operand(i, "ActorNum")
    if _isnum(num) and int(num) > 1:
        who += f"x{num}"
    leaf = f"hit:{_clean(who)}@{g.areas(i)}"
    return {"IsHit": leaf, "IsNotHit": NOT(leaf)}.get(o)


def h_bb(g, i, o):
    key = g.str_in(i, "BlackboardKey")
    if key in (None, "?"):
        key = g.prop(i, "BlackboardKey", "?")
    return "bb:" + _clean(key)


def h_delay(g, i, o):
    return WRAP("DELAY", g.bool_in(i, "Bool"))


def h_autogen(g, i, o):
    return f"game:autogen.{int(g.prop(i, '__GUIDHash', 0)) & 0xFFFFFFFF:08x}"


def h_poe(g, i, o):
    return f"game:PoeBig.{o}.{g.operand(i, 'FenceId')}"


def h_seq_gd_bool(g, i, o):
    return "flag:" + g.gd_name(i)


def h_seq_and(g, i, o):
    return AND(g.bool_in(i, "ValueA"), g.bool_in(i, "ValueB"))


def h_seq_or(g, i, o):
    return OR(g.bool_in(i, "ValueA"), g.bool_in(i, "ValueB"))


def h_identity(g, i, o):
    return g.bool_in(i, "Bool")


def h_runtime(g, i, o):
    return f"node:{i}.{o}"


def h_equip(g, i, o):
    return "player:equip:" + _clean(actor_of(g.str_in(i, "EquipmentActor")))


def h_riding(g, i, o):
    return "player:riding"


HANDLERS = {
    "OperateInvertBool": h_invert, "OperateCompareInt": h_cmp, "OperateCompareF32": h_cmp,
    "OperateMathEqualS32": h_math, "OperateMathLessOrEqualS32": h_math, "OperateIsInTimeRange": h_timerange,
    "OperateGameDataAllocAutogenGameData": h_autogen, "OperateCheckNullptr": h_runtime,
    "HoldGameDataGetBoolSimple": h_gd_bool, "HoldGameDataGetBoolExpSimple": h_gd_exp,
    "HoldGameDataHavePlayedEvent": h_played, "HoldChallengeCurrentStepCheckOrder": h_step,
    "HoldGameDataEnumCheckOrder": h_enum, "HoldGameDataIsVisitLocation": h_visit,
    "HoldIsChildhoodOrAdulthood": h_age, "HoldPlayerCheckBoots": h_boots,
    "HoldPlayerrCheckEventQueryPlayerState": h_pstate, "HoldHasStockItem": h_stock,
    "HoldDungeonRoomQueryIsInCurrentRoom": h_room, "HoldDungeonRoomQueryIsInCurrentSpace": h_room,
    "HoldWmGetTimeDiv": h_timediv, "HoldWmPrimeFishingTime": h_fishing,
    "HoldCheckIsReticleDirectedToTheSun": h_sun, "HoldBlackboardGetBool": h_bb, "HoldGeneralDelayBool": h_delay,
    "HoldPoeBigGetCanAppear": h_poe,
    # runtime state: timers, toggles, lotteries, safety checks, event outputs (a node leaf, not "unknown")
    "HoldGeneralTimerSwitch": h_runtime, "TriggerChangeBool": h_runtime, "HoldMiniGameCuccoLotteryResult": h_runtime,
    "HoldGameSafetyIsProcessing": h_runtime, "HoldHountedWastelandOutArea": h_runtime,
    "HoldPoeBigCalcCreateAndRecreateFlag": h_runtime, "TriggerCheckIsReticleRayCastToTheSun": h_runtime,
    # Sequence / AI queries
    "SeqQueryInvertBool": h_invert, "QueryInvertBool": h_invert, "QueryGetBoolSimple": h_identity,
    "SeqQueryLogicalConjunction": h_seq_and, "QueryLogicalConjunction": h_seq_and,
    "SeqQueryLogicalDisjunction": h_seq_or, "QueryLogicalDisjunction": h_seq_or,
    "QueryBlackboardGetBool": h_bb, "QueryBlackboardGetBoolNoError": h_bb,
    "SeqQueryGetIsEquip": h_equip, "SeqQueryGetIsPlayerRiding": h_riding,
    "QueryAIScheduleIsAIScheduleFlag": h_runtime, "QueryGetVolatileGeneralPurposeFlag": h_runtime,
}
PREFIX_HANDLERS = [
    (r"^Operate(AND|OR)", h_combinator),
    (r"^Hold\w*Observer\w*SensorHitInfo$|^HoldNpcObserverFor", h_observer),
    (r"^(Seq)?Query(Get)?(NonStruct)?GameDataBool(Exp)?$", h_seq_gd_bool),
]


# AINB record

READ_KINDS = {  # node name -> (kind, name input or None)
    "HoldGameDataGetBoolSimple": ("bool", "GameDataNameBool"),
    "HoldGameDataGetBoolExpSimple": ("exp", "GameDataNameBoolExp"),
    "HoldGameDataGetIntSimple": ("int", "GameDataNameInt"),
    "HoldGameDataEnumCheckOrder": ("enum", "GameDataNameEnum"),
    "HoldGameDataIsValidBool": ("valid", "GameDataNameBool"),
    "HoldGameDataHavePlayedEvent": ("played", "EventName"),
    "HoldGameDataIsVisitLocation": ("visit", "LocationName"),
    "HoldChallengeCurrentStepCheckOrder": ("step", None),
    "HoldHasStockItem": ("item", "ActorName"),
    "OperateGameDataAllocAutogenGameData": ("autogen", None),
    "HoldPoeBigGetCanAppear": ("poe", None),
}


def index_ainb(fs, rel):
    raw = common.read_any(fs, rel)
    a = Ainb(raw)
    g = Graph(fs, a, rel)
    kind = AINB_DIRS[rel.split("/")[0]]
    nodes, readers = compact_nodes(g)
    rec = {"kind": kind, "name": a.name, "category": a.category, "nodes": nodes}
    if a.commands:
        rec["commands"] = {c["name"]: c["main"] for c in a.commands}
    bb = {e["name"]: _jv(e["default"]) for t in ("string", "int", "float", "bool") for e in a.bb[t]}
    if bb:
        rec["bb"] = bb
    if a.modules:
        rec["modules"] = [f"{m['category']}/{m['path']}" for m in a.modules]

    # actors: every node with an InstanceName property (actor nodes and module calls)
    actors = {}
    for i, n in enumerate(a.nodes):
        inst = next((e["value"] for e in n["properties"]["string"] if e["name"] == "InstanceName"), None)
        if inst is None or not isinstance(inst, str):
            continue
        gates = {}
        for e in n["inputs"]["bool"]:
            src = g.sources("bool", e)
            if src and src[0][0] == "c":
                v = bool(src[0][1])
                if (e["name"] == "Logic_Create" and not v) or (e["name"] == "Logic_Delete" and v):
                    gates[e["name"]] = T if v else F
                continue
            gates[e["name"]] = fstr(g.bool_in(i, e["name"]))
        rec_a = {"node": i, "class": g.nm(i)}
        if n["flags"] & 2:
            rec_a["module"] = g.callee_rel(i) or g.nm(i) + ".ainb"
        if gates:
            rec_a["gates"] = gates
        if inst in actors:  # the same instance driven twice, keep both
            inst = f"{inst}#{i}"
        actors[inst] = rec_a
    if actors:
        rec["actors"] = actors

    # module interface (in the callee's record)
    ins = [str(g.prop(i, "Name", "")) for i, n in enumerate(a.nodes) if 100 <= n["type"] <= 105]
    if ins:
        rec["inputs"] = ins
    outs = {}
    for i, n in enumerate(a.nodes):
        if n["type"] == 204 and n["inputs"]["bool"]:
            outs[str(g.prop(i, "Name", ""))] = fstr(g.bool_in(i, n["inputs"]["bool"][0]["name"]))
    if outs:
        rec["outputs"] = outs

    reads, writes = reads_writes(g, readers)
    if reads:
        rec["reads"] = reads
    if writes:
        rec["writes"] = writes

    # BoolSelector conditions (Sequence / AI behaviour trees)
    sel = {}
    for i, n in enumerate(a.nodes):
        if n["type"] == 7:
            t, e = g.find_in(i, "Input", ("bool",))
            if e is not None and not (g.sources(t, e)[0][0] == "c"):
                sel[str(i)] = fstr(g.bool_in(i, "Input"))
            elif e is None:
                v = g.prop(i, "InputValue")
                if isinstance(v, str):
                    sel[str(i)] = v
    if sel:
        rec["selectors"] = sel

    uf, odd = unflagged(g)
    if uf:
        rec["unflagged_reads"] = uf
    if odd:
        rec["odd_links"] = odd
    dead = dead_outputs(g, readers)
    if dead:
        rec["dead_outputs"] = dead

    leaves = {(name, where) for f in _all_formulas(rec) for _, name, where in LEAF_RX.findall(f)}
    unk = Counter(name for name, where in leaves if "/" not in where)  # a callee's are counted in its own record
    if unk:
        rec["unknown"] = dict(unk)
    rec["sig"] = _sig(raw)
    if g.deps:
        rec["deps"] = g.deps
    return rec


def _all_formulas(rec):
    for a in (rec.get("actors") or {}).values():
        yield from (a.get("gates") or {}).values()
    yield from (rec.get("outputs") or {}).values()
    yield from (rec.get("selectors") or {}).values()
    for w in rec.get("writes") or []:
        if w.get("when"):
            yield w["when"]


def _jv(v):
    if isinstance(v, float):
        return float(f"{v:.6g}")
    if isinstance(v, list):
        return [_jv(x) for x in v]
    return v


def compact_nodes(g):
    a = g.a
    readers = defaultdict(list)  # (src node, type, out index) -> [(consumer, input)]
    nodes = []
    for i, n in enumerate(a.nodes):
        d = {"i": i, "name": g.nm(i), "type": NODE_TYPES.get(n["type"], n["type"])}
        props = {}
        for t in PTYPES:
            for e in n["properties"][t]:
                if t == "ptr":
                    continue
                props[e["name"]] = {"bb": g.bb_name(t, e["flags"])} if e.get("flags", 0) & BB_INDEXED else _jv(e["value"])
        if props:
            d["props"] = props
        ins = {}
        for t in PTYPES:
            for e in n["inputs"][t]:
                srcs = g.sources(t, e)
                links = []
                for kind, *v in srcs:
                    if kind == "n":
                        s, k = v
                        fl = e.get("flags", 0) if e.get("node", -1) >= 0 else 0
                        t2, oe = g.link_out(s, t, k, fl)
                        readers[(s, t2, k)].append((i, e["name"]))
                        ln = {"node": s, "out": oe["name"] if oe else k, "flagged": bool(oe and oe["flag"])}
                        if fl:
                            ln["form"] = f"{fl:#x}"
                        links.append(ln)
                    elif kind == "bb":
                        links.append({"bb": v[0]})
                if links:
                    ins[e["name"]] = links[0] if len(links) == 1 and e.get("node", -1) > -100 else links
                elif t != "ptr":
                    ins[e["name"]] = _jv(e["value"])
        if ins:
            d["in"] = ins
        outs = {e["name"]: bool(e["flag"]) for t in PTYPES for e in n["outputs"][t]}
        if outs:
            d["out"] = outs
        if n["flags"] & 2:
            d["call"] = True
        kids = []
        for pl in n["plugs"][2]:
            lab = pl["name"]
            if not lab and len(pl["extra"]) == 8 and n["type"] == 1:  # S32Selector case value
                lab = struct.unpack("<Ii", bytes(pl["extra"]))[1]
            kids.append([pl["node"], lab] if lab != "" else pl["node"])
        if kids:
            d["kids"] = kids
        trans = [pl["node"] for pl in n["plugs"][3]]
        if trans:
            d["trans"] = trans
        if n["attachments"]:
            d["att"] = [a.attachments[k]["name"] for k in n["attachments"]]
        nodes.append(d)
    return nodes, readers


def _used_outs(g, readers, i):
    n = g.a.nodes[i]
    return [e["name"] for t in PTYPES for k, e in enumerate(n["outputs"][t]) if readers.get((i, t, k))]


def reads_writes(g, readers):
    a = g.a
    reads, writes = [], []
    for i, n in enumerate(a.nodes):
        name = g.nm(i)
        used = _used_outs(g, readers, i)
        if name in READ_KINDS:
            kind, key = READ_KINDS[name]
            r = {"node": i, "kind": kind}
            if kind == "step":
                ch = challenge_of(g.str_in(i, "ChallengeName"))
                r.update(flag="@step:" + ch, challenge=ch, step=g.str_in(i, "ChallengeStepName"))
            elif kind == "played":
                r["flag"] = "HavePlayedEvent." + str(g.str_in(i, key))
            elif kind == "visit":
                r["flag"] = "IsVisitLocation." + str(g.str_in(i, key))
            elif kind == "item":
                r["flag"] = actor_of(g.str_in(i, key))
            elif kind == "autogen":
                r["flag"] = h_autogen(g, i, "Bool")[5:]
            elif kind == "poe":
                r["flag"] = f"PoeBig.{g.operand(i, 'FenceId')}"
            else:
                r["flag"] = str(g.str_in(i, key))
                if kind == "enum":
                    r["value"] = g.str_in(i, "EnumName")
            idx = g.index_sfx(i)
            if idx:
                r["index"] = idx[1:-1]
            live = [o for o in used if any(e["name"] == o and e["flag"] for t in PTYPES for e in n["outputs"][t])]
            if live:
                r["outs"] = live
            else:
                r["dead"] = True  # nobody reads it, or only through outputs it never computes (C1)
                if used:
                    r["unflagged"] = used
            reads.append(r)
        elif re.match(r"^(Seq)?Query(Get)?(NonStruct)?GameData(Bool|BoolExp|Int|Enum|String\d*|Struct|Float|Vector3)$",
                      name):
            r = {"node": i, "kind": re.search(r"GameData(\w+)$", name).group(1).lower(), "flag": g.gd_name(i)}
            if not used:
                r["dead"] = True
            reads.append(r)
        # writes
        w = None
        if name in ("TriggerGameDataSetBoolTrue", "TriggerGameDataSetBoolFalse"):
            w = {"flag": str(g.str_in(i, "GameDataNameBool")), "kind": "bool", "value": name.endswith("True")}
        elif name == "TriggerGameDataSetIntSum":
            w = {"flag": str(g.str_in(i, "GameDataNameInt")), "kind": "int", "value": g.operand(i, "SetValue")}
        elif name == "TriggerGameDataAddInt":
            w = {"flag": str(g.str_in(i, "GameDataNameInt")), "kind": "int", "value": "+" + g.operand(i, "AddValue")}
        elif name in ("TriggerChallengeSetStep", "TriggerChallengeSetStepNoEventPause"):
            ch = challenge_of(g.str_in(i, "ChallengeName"))
            w = {"flag": "@step:" + ch, "kind": "step", "challenge": ch, "value": g.str_in(i, "StepName"),
                 "step": g.str_in(i, "StepName"), "ignore_completed": bool(g.prop(i, "IgnoreStepComplete", False))}
        elif name in ("TriggerDungeonRoomStepClear", "TriggerDungeonRoomStepForward"):
            w = {"flag": "@room_step", "kind": "room_step",
                 "value": "clear" if name.endswith("Clear") else g.operand(i, "Step")}
        elif name in ("TriggerBlackBoardSetBoolTrue", "TriggerBlackBoardSetBoolFalse"):
            w = {"flag": str(g.str_in(i, "BlackboardKey")), "kind": "bb", "value": name.endswith("True")}
        elif name == "OperateGameDataAllocAutogenGameData":
            w = {"flag": h_autogen(g, i, "Bool")[5:], "kind": "autogen", "value": fstr(g.bool_in(i, "Bool"))}
            w["when"] = fstr(g.bool_in(i, "IsWrite"))
        elif name == "TriggerRequestAutoSave":
            w = {"flag": "@autosave", "kind": "autosave", "value": True}
        elif re.match(r"^(Seq)?OneShot(Set|Add)(NonStruct)?GameData\w+$", name):
            kind = re.search(r"GameData(\w+)$", name).group(1).lower()
            w = {"flag": g.gd_name(i), "kind": kind}
            t, e = g.find_in(i, "Value")
            if e is not None:
                v = fstr(g.bool_in(i, "Value")) if t == "bool" else g.operand(i, "Value")
                w["value"] = {T: True, F: False}.get(v, v)
            if "Add" in name:
                w["value"] = "+" + str(w.get("value", g.operand(i, "AddValue")))
        elif name == "SeqExecuteResetGameData":
            w = {"flag": "@reset", "kind": "reset", "value": g.operand(i, "ResetType")}
        elif name == "OneShotAIScheduleSetAIScheduleFlag":
            v = fstr(g.bool_in(i, "Value"))
            w = {"flag": "@aischedule_flag." + g.operand(i, "FlagType"), "kind": "aischedule_flag",
                 "value": {T: True, F: False}.get(v, v)}
        if w is not None:
            w["node"] = i
            if "when" not in w and g.find_in(i, "IsDrive", ("bool",))[1] is not None:
                w["when"] = fstr(g.bool_in(i, "IsDrive"))
            if w.get("kind") in ("bool", "int") and g.index_sfx(i):
                w["index"] = g.index_sfx(i)[1:-1]
            writes.append(w)
    return reads, writes


def unflagged(g):
    out, odd = [], []
    a = g.a
    for i, n in enumerate(a.nodes):
        for t in PTYPES:
            for e in n["inputs"][t]:
                fl = e.get("flags", 0) if e.get("node", -1) >= 0 else 0
                for kind, *v in g.sources(t, e):
                    if kind != "n":
                        continue
                    s, k = v
                    t2, oe = g.link_out(s, t, k, fl)
                    if oe is None:
                        odd.append({"node": i, "input": e["name"], "src": s, "out": k, "type": t, "form": f"{fl:#x}"})
                    elif not oe["flag"]:
                        out.append({"node": i, "input": e["name"], "src": s, "out": oe["name"]})
    return out, odd


def dead_outputs(g, readers):
    """Observer/query nodes (Hold*, Operate*, Query*) with data outputs nobody reads. Either the whole node is
    unused ("whole": true, like an Item_Bomb observer nobody wired up) or it has flagged outputs computed for
    nothing."""
    out = []
    for i, n in enumerate(g.a.nodes):
        name = g.nm(i)
        if not OBSERVER.match(name) or n["flags"] & 2:
            continue
        data = [(t, k, e) for t in ("bool", "int", "float", "string") for k, e in enumerate(n["outputs"][t])]
        if not data:
            continue
        unread = [(t, k, e) for t, k, e in data if not readers.get((i, t, k))]
        whole = len(unread) == len(data) and not any(readers.get((i, "ptr", k))
                                                       for k in range(len(n["outputs"]["ptr"])))
        if whole:
            d = {"node": i, "name": name, "outs": {e["name"]: bool(e["flag"]) for _, _, e in unread}, "whole": True}
            t, k, _ = data[0]
            f = g.out(i, t, k) if t == "bool" else None
            if isinstance(f, str) and not f.startswith(("node:", "unknown:")):
                d["leaf"] = f  # the unread node observes a leaf like hit:Item_Bomb@... or flag:...
            out.append(d)
        else:
            fl = [e["name"] for _, _, e in unread if e["flag"]]
            if fl:
                out.append({"node": i, "name": name, "outs": {x: True for x in fl}})
    return out


# Schedules

TIME_DIV = {3710534274: "Always", 262656402: "Noon", 2181706133: "Night"}
ACTION_TYPE = {murmur3_32(f"Action{k}".encode()): f"Action{k}" for k in range(1, 21)}
ACTION_TYPE.update({murmur3_32(s.encode()): s for s in ("Wander1", "Wander2", "Sleep1", "Sleep2")})
EVENT_KEYS = {"EventName": "setting", "TalkEventName": "talk", "NearEventName": "near", "ChaseEventName": "chase"}
SETTING_KEEP = ("ArrivalAS", "WaitArrivalAS", "MovingAS", "GatheringAS", "ChaseAS", "IsSleepInBed", "CanAwake",
                "IsChase", "IsForceArrived", "IsFlyMove", "IsGreet")


def _setting_name(path):
    s = str(path or "")
    return s.rsplit("/", 1)[-1].split(".", 1)[0] if s else ""


def _events(entries):
    out = []
    for e in entries or []:
        d = {"type": str(e.get("$type", "")).replace("game__aischedule__", "")}
        for k, short in EVENT_KEYS.items():
            if e.get(k):
                d[short] = _setting_name(e[k])
        if "Distance" in e:
            d["dist"] = round(float(e["Distance"]), 2)
        for k in ("TargetActor", "TargetAction"):
            if e.get(k) not in (None, ""):
                d[k[6:].lower()] = common.jsonable(e[k])
        out.append(d)
    return out


def _actions(lst):
    out = []
    for a in lst or []:
        d = {}
        if "ActionTimeDivision" in a:
            d["time"] = TIME_DIV.get(int(a["ActionTimeDivision"]), int(a["ActionTimeDivision"]))
        if "ActionType" in a:
            d["type"] = ACTION_TYPE.get(int(a["ActionType"]), int(a["ActionType"]))
        if "StartTime" in a or "StartTime_Minutes" in a:
            d["start"] = f"{int(a.get('StartTime', 0)):02d}:{int(a.get('StartTime_Minutes', 0)):02d}"
        if a.get("AnchorInstanceName"):
            d["anchor"] = a["AnchorInstanceName"]
        if a.get("IsWarpToActionPos"):
            d["warp"] = True
        st = {k: common.jsonable(v) for k, v in (a.get("Setting") or {}).items()
              if k in SETTING_KEEP and v not in ("", None, False)}
        if st:
            d["set"] = st
        out.append(d)
    return out


def schedule_record(root, base, parent=None):
    rec = {"kind": "schedule", "actor": base, "states": [], "rule": RULE}
    for s in root.get("ConditionalSchedule") or []:
        st = {"cond": s.get("ConditionFlag")}
        if s.get("IsReverseCondition"):
            st["neg"] = True
        if s.get("IsResetRecentTalkFlagOnChange"):
            st["reset_talk"] = True
        ev = _events(s.get("EventEntry"))
        if ev:
            st["events"] = ev
        ac = _actions(s.get("ActionSchedule"))
        if ac:
            st["actions"] = ac
        rec["states"].append(st)
    d = root.get("DefaultSchedule")
    if d is not None:
        rec["default"] = {k: v for k, v in (("events", _events(d.get("EventEntry"))),
                                            ("actions", _actions(d.get("ActionSchedule")))) if v}
    for k in ("AIScheduleLodDistance", "IsSimplifyActor", "IsInvalidAIScheduleLOD"):
        if k in root:
            rec.setdefault("opts", {})[k] = common.jsonable(root[k])
    if parent:
        rec["parent"] = parent
    return rec


_STEPS = {}


def challenge_steps(fs):
    """{challenge hash 'Step_<name>': [step names]} from GameDataList's step enums (cached per process)."""
    key = fs.root
    if key not in _STEPS:
        root = common.read_byml(fs, "GameData/GameDataList.Product.110.byml.zs")
        _STEPS[key] = {int(e["Hash"]): [str(x) for x in e.get("RawValues") or []]
                       for e in (root.get("Data") or {}).get("Enum") or []}
    return _STEPS[key]


def split_step_schedule(fs, base):
    """'Get_StoneOfFire_DungeonStart_Npc_Goron_Darunia_Child' -> (challenge, step, actor) or (None, None, base)."""
    enums = challenge_steps(fs)
    parts = base.split("_")
    for k in range(1, len(parts)):
        ch = "_".join(parts[:k])
        steps = enums.get(murmur3_32(f"Step_{ch}".encode()))
        if not steps:
            continue
        rest = "_".join(parts[k:])
        for st in sorted(steps, key=len, reverse=True):
            if rest.startswith(st + "_"):
                return ch, st, rest[len(st) + 1:]
    m = re.search(r"_((?:Npc|Animal)_.+)$", base)
    return None, None, m.group(1) if m else base


def index_schedule_pack(fs, rel):
    raw = fs.raw(rel)
    files_ = common.pack(fs, rel)
    roots = {}
    for k, v in files_.items():
        if not k.endswith(".bgyml"):
            continue
        data = fs.zs.decompress(v) if v[:4] == common.ZSTD_MAGIC else v
        roots[os.path.basename(k).split(".")[0]] = (k, byml_load(data, allow_big=True)[0])
    out = {}

    def merged(base, seen=()):
        k, r = roots[base]
        par = r.get("$parent")
        if not par or base in seen:
            return dict(r), []
        pbase = _setting_name(par)
        if pbase not in roots:
            return dict(r), []
        pr, _ = merged(pbase, seen + (base,))
        m = dict(pr)
        inherited = [x for x in pr if x not in r and not x.startswith("$")]
        m.update(r)
        return m, inherited

    for base, (k, r) in sorted(roots.items()):
        root, inherited = merged(base)
        par = _setting_name(r.get("$parent")) if r.get("$parent") else None
        rec = schedule_record(root, base, par)
        ch, st, actor = split_step_schedule(fs, base)
        rec["actor"] = actor
        rec["name"] = base
        if ch:
            rec["challenge"], rec["step"] = ch, st
        if inherited:
            rec["inherited"] = inherited
        out[k] = rec
    return {"kind": "schedule_pack", "schedules": out, "sig": _sig(raw),
            "note": "challenge-step schedules (<Challenge>_<Step>_<Actor>); none duplicates Component/AIScheduleParam"}


# Finish

def _schedules(by_file):
    for rel, rec in by_file.items():
        if rec.get("kind") == "schedule":
            yield rel, rec
        elif rec.get("kind") == "schedule_pack":
            for k, r in (rec.get("schedules") or {}).items():
                yield f"{rel}:{k}", r


EXP = re.compile(r"^(?P<ch>.+?)_(?P<k>IsAfter|IsCompleted)(?:_(?P<st>.+))?_Exp$")


def rule_evidence(fs, by_file):
    """Pairs of states (earlier, later) of one schedule whose conditions are IsAfter/IsCompleted expressions of
    the same quest. 'later_implies_earlier' means the later state is the more advanced one, which is only reachable if
    the last true condition wins. 'earlier_implies_later' is only reachable if the first true one wins."""
    try:
        enums = challenge_steps(fs)
    except Exception:  # noqa: BLE001 - no GameDataList: no evidence
        return None

    def rank(cond):
        m = EXP.match(cond or "")
        if not m:
            return None
        steps = enums.get(murmur3_32(f"Step_{m.group('ch')}".encode()))
        if not steps:
            return None
        if m.group("k") == "IsCompleted":  # true at Complete, and IsAfter_<s> is true from the step after s
            return m.group("ch"), steps.index("Complete") if "Complete" in steps else len(steps)
        st = m.group("st")
        return (m.group("ch"), steps.index(st) + 1) if st in steps else None

    later = earlier = 0
    examples = []
    for ref, rec in _schedules(by_file):
        states = [s for s in rec.get("states") or [] if not s.get("neg")]
        for x in range(len(states)):
            for y in range(x + 1, len(states)):
                a, b = rank(states[x]["cond"]), rank(states[y]["cond"])
                if not a or not b or a[0] != b[0] or a[1] == b[1]:
                    continue
                if b[1] > a[1]:
                    later += 1
                else:
                    earlier += 1
                    if len(examples) < 5:
                        examples.append([ref, states[x]["cond"], states[y]["cond"]])
    return {"later_implies_earlier": later, "earlier_implies_later": earlier, "counter_examples": examples}


def finish(fs, by_file):
    # an overlay can change a called module without re-indexing its callers, so re-index the ones whose deps moved
    sigs = {rel: rec.get("sig") for rel, rec in by_file.items()}
    for rel, rec in list(by_file.items()):
        deps = rec.get("deps") or {}
        if any(sigs.get(d) not in (None, s) for d, s in deps.items()):
            try:
                by_file[rel] = index_file(fs, rel)
            except Exception:  # noqa: BLE001 - keep the old record
                pass

    setters, readers, gates, step_readers, items, pt = (defaultdict(list) for _ in range(6))
    names, unknown, sched_cond = Counter(), Counter(), defaultdict(list)
    totals = Counter()
    # for a module's flag argument ($GameDataNameBool), the flag each caller passes
    callers = defaultdict(list)
    for rel, rec in by_file.items():
        mods = {m.rsplit("/", 1)[-1]: m for m in rec.get("modules") or []}
        for n in rec.get("nodes") or []:
            if n.get("call") and n["name"] + ".ainb" in mods:
                callers[mods[n["name"] + ".ainb"]].append((rel, n))

    def resolved(rel, flag, ref):
        if not str(flag).startswith("$"):
            return [(flag, ref)]
        out = [(v, dict(ref, file=crel, node=n["i"], via={"file": rel, "node": ref["node"]}))
               for crel, n in callers.get(rel, []) for v in [(n.get("in") or {}).get(flag[1:])] if isinstance(v, str)]
        return out or [(flag, ref)]
    for rel, rec in by_file.items():
        kind = rec.get("kind")
        if kind in AINB_DIRS.values():
            totals["modules"] += 1
            totals[f"modules_{kind}"] += 1
            totals["nodes"] += len(rec.get("nodes") or [])
            for n in rec.get("nodes") or []:
                names[n["name"]] += 1
            for inst, a in (rec.get("actors") or {}).items():
                gates[inst.split("#")[0]].append({"file": rel, "node": a["node"], "class": a["class"]})
                totals["actors"] += 1
                totals["actor_gates"] += len(a.get("gates") or {})
            for r in rec.get("reads") or []:
                totals["reads"] += 1
                if r.get("kind") == "step":
                    step_readers[r["challenge"]].append({"file": rel, "node": r["node"], "step": r.get("step"),
                                                         "outs": r.get("outs", []), **({"dead": True} if r.get("dead") else {})})
                elif r.get("kind") == "item":
                    items[r["flag"]].append({"file": rel, "node": r["node"], "outs": r.get("outs", [])})
                elif r.get("kind") != "poe":
                    ref = {"file": rel, "node": r["node"], "kind": r["kind"], **({"dead": True} if r.get("dead") else {})}
                    for flag, ref2 in resolved(rel, r["flag"], ref):
                        readers[flag].append(ref2)
            for w in rec.get("writes") or []:
                totals["writes"] += 1
                if w.get("kind") in ("bb", "autosave", "room_step", "reset"):
                    continue
                ref = {"file": rel, "node": w["node"], "kind": w["kind"], "value": w.get("value")}
                for k in ("when", "step", "ignore_completed", "index"):
                    if k in w:
                        ref[k] = w[k]
                for flag, ref2 in resolved(rel, w["flag"], ref):
                    setters[flag].append(ref2)
            for inst, a in (rec.get("actors") or {}).items():
                for g in (a.get("gates") or {}).values():
                    for leaf in set(re.findall(r"\b(?:player|time):[^,()\s]+", g)):
                        if not pt[leaf] or pt[leaf][-1] != rel:
                            pt[leaf].append(rel)
            for k, v in (rec.get("unknown") or {}).items():
                unknown[k] += v
            totals["unflagged_reads"] += len(rec.get("unflagged_reads") or [])
            totals["dead_outputs"] += len(rec.get("dead_outputs") or [])
    for ref, rec in _schedules(by_file):
        totals["schedules"] += 1
        for s in rec.get("states") or []:
            if s.get("cond"):
                who = rec.get("actor") or ref
                if who not in sched_cond[s["cond"]]:
                    sched_cond[s["cond"]].append(who)
    totals["unknown_leaves"] = sum(unknown.values())
    return {"setters": dict(setters), "readers": dict(readers), "actor_gates": dict(gates),
            "step_readers": dict(step_readers), "item_readers": dict(items), "player_time_gates": dict(pt),
            "node_name_counts": dict(names.most_common()),
            "unknown_leaf_nodes": dict(unknown.most_common()), "schedule_conditions": dict(sched_cond),
            "schedule_rule": dict(rule=RULE, evidence=rule_evidence(fs, by_file)), "totals": dict(totals)}
