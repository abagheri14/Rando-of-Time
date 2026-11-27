"""D-pad gear (remake_dpad_gear, one of the extras_qol options). Hold D-pad up to switch to the next accessory you
have (the Lens of Truth, the masks, the amiibo masks) and hold D-pad down to swap between the Hover and Iron Boots.
Keep holding to keep switching. A tap still does what the game's own shortcut does: puts the gear on or takes it off.

Where it hooks in: Sequence/UpdateShortCutOpenHoldFrameCounter.module runs every frame outside menus and events
(Main runs it next to its branch picker) and times how long L or R is held for the item wheel, in
Sequence_ShortCutOpenHoldCounter. With neither held it resets the counter (node 32's False case, node 24). The D-pad
goes in right there, before the reset:
- pressing up or down sets the counter to START, way below the wheel's range (1 to 9999, node 20)
- while it's held a float switch adds the frame step (node 25) up to FIRE, then runs the switch and sets AGAIN, so
  the first switch comes about half a second in and the next ones a second apart
- with nothing held the game resets the counter like always
The switch reads the slot's equipped name (PlayerStatus.EquipHeadArmor or EquipBoot) and matches it with a
StringSelector, the way AfterChangeBanc switches on a String64. From there it walks the Equipment menu's list from the
next item on, the list twice over so it wraps round. The first item you have gets written to the slot, and the game
re-applies Link's equipment from the save data (SeqSyncPlayerEquipmentAndGameData) and the pouch's equipped index.
If you have nothing else, nothing happens: the second time round skips the item you're on.

"Have" is the menu's own rule, IsGet plus a pouch count above 0, for the ages the Equipment table allows (both boots
are adult only, every accessory works at both ages in the remake). That means a mask you sold or traded is never
offered. When the seed has the mask picker (tools/mask_slot.py), a mask the picker put aside counts too, and
switching to it puts it back in the pouch and clears its flag first, the same two steps as the picker's own put-back.

I took the hook, the timer and the write-then-sync from OOTRR's gear cycle (they checked theirs in game). The rest
is ours: names get matched with the game's own StringSelector, gear you've sold or traded is never offered, the
picker's put-aside masks count, the ages come from the Equipment table and the amiibo masks are in. The little hop
when you change boots stays.
"""
import os
import random
import struct

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
CHILD = "Sequence_IsChildhood"
START, AGAIN = -1015.0, -1030.0  # counter values on a press and after each switch
FLOOR, FIRE, CEIL = -5000.0, -1000.0, -500.0  # the hold adds the frame step from FLOOR to FIRE, FIRE..CEIL switches
PREP = FIRE - 3.0  # wheel mode: PREP..FIRE sets the wheel's category a few frames before it opens
FRAME_STEP = 1.0  # SeqQueryGetGameFrameStepRate at normal speed, for the read-back's timing
WHEEL = (1.0, 9999.0)  # the counter values that open the item wheel (node 20)
BOOL, AND, OR, NOT, EXP, INT_EQ, INT_CONST, INT_LT, INT_GT = 0, 3, 4, 5, 10, 15, 16, 18, 19  # BoolExp opcodes


def exp_name(actor):
    return f"Rando_Dpad_{actor}_Exp"


def picker_flags(settings):
    """{mask: its put-aside flag} when the seed has the mask picker, else {}."""
    import mask_slot
    if not mask_slot.needs_picker(settings):
        return {}
    return {m: f for m, f in mask_slot.data()["flags_claimed"].items() if m in mask_slot.data()["order"]}


def expressions(d, flags):
    """{expression name: steps}: you have this piece of gear and may use it at your age."""
    out = {}
    for gear in d["gear"].values():
        for g in gear:
            a = g["actor"]
            steps = [[BOOL, f"IsGet.{a}"], [INT_GT, f"PouchData.{a}.StockNum"], [INT_CONST, 0], [AND]]
            if a in flags:
                steps += [[BOOL, flags[a]], [OR]]
            if not g["child"]:
                steps += [[BOOL, CHILD], [NOT], [AND]]
            if not g["adult"]:
                steps += [[BOOL, CHILD], [AND]]
            out[exp_name(a)] = steps
    return out


class _Graph:
    """Writes the "ainb" edits: copies of the game's own nodes, wired up. Refs are "label:index" or a vanilla node."""

    def __init__(self, d):
        self.d, self.edits, self.n = d, [], 0

    def copy(self, key, **inputs):
        d = self.d
        if key in d["nodes"]:
            src, node = {"file": d["file"]}, d["nodes"][key]
        else:
            src, node = {"file": d["sources"][key]["file"]}, d["sources"][key]["node"]
        self.n += 1
        ref = f"dp{self.n}:{node}"
        self.edits.append({"copy": {"from": src, "nodes": [node], "label": f"dp{self.n}", "follow": False}})
        self.edits += [{"set_input": {"node": ref, "name": k, "value": v}} for k, v in inputs.items()]
        return ref

    def bool_sel(self, src, output, yes, no):
        r = self.copy("bool_sel")
        self.edits += [{"feed": {"from": src, "output": output, "to": r, "input": "Input"}},
                       {"add_child": {"parent": r, "child": yes, "name": "True"}},
                       {"add_child": {"parent": r, "child": no, "name": "False"}}]
        return r

    def str_sel(self, src, cases, default):
        r = self.copy("str_sel")
        self.edits += [{"feed": {"from": src, "output": "Value", "to": r, "input": "Input"}},
                       {"add_child": {"parent": r, "child": default, "default": ""}}]
        self.edits += [{"add_child": {"parent": r, "child": c, "string": v}} for v, c in cases]
        return r

    def sim(self, kids):
        r = self.copy("sim")
        self.edits += [{"add_child": {"parent": r, "child": k}} for k in kids]
        return r

    def timer(self, fire, prep=None):
        """The hold's switch on the counter: count up to FIRE, then fire. With prep (wheel mode) the last frames
        before FIRE run prep, which counts on too."""
        n = self.d["nodes"]
        r = self.copy("f32_sel")
        self.edits += [{"feed": {"from": n["counter"], "output": "Value", "to": r, "input": "Input"}},
                       {"add_child": {"parent": r, "child": n["dummy"], "default": ""}}]
        if prep is None:
            self.edits.append({"add_child": {"parent": r, "child": n["step"], "range": [FLOOR, FIRE]}})
        else:
            self.edits += [{"add_child": {"parent": r, "child": n["step"], "range": [FLOOR, PREP]}},
                           {"add_child": {"parent": r, "child": prep, "range": [PREP, FIRE]}}]
        self.edits.append({"add_child": {"parent": r, "child": fire, "range": [FIRE, CEIL]}})
        return r

    def cycle(self, slot, flags, sync, index):
        """The switch for one slot: the StringSelector on the equipped name, into the doubled list."""
        d, dummy = self.d, self.d["nodes"]["dummy"]
        gear, name = d["gear"][slot], d["slots"][slot]
        n = len(gear)
        if n < 2:
            raise ValueError(f"D-pad gear: the {slot} list has {n} item(s), nothing to switch between")
        cur = self.copy("get_s64", GameDataFullName=name)
        have = [self.copy("get_exp", GameDataFullName=exp_name(g["actor"])) for g in gear]
        sets = []
        for g in gear:
            a = g["actor"]
            write = self.copy("set_s64", GameDataFullName=name, Value=a)
            put_on = self.sim([write, sync, index])
            if a in flags:  # put aside by the picker: back into the pouch first
                aside = self.copy("get_bool", GameDataFullName=flags[a])
                push = self.copy("push", ActorName=f"Work/Actor/{a}.engine__actor__ActorParam.gyml")
                clear = self.copy("set_bool", GameDataFullName=flags[a], Value=False)
                put_on = self.bool_sel(aside, "Value", self.sim([push, clear, write, sync, index]), put_on)
            sets.append(put_on)
        steps = [None] * (2 * n - 1)
        for i in range(2 * n - 2, -1, -1):
            j = i % n
            nxt = steps[i + 1] if i + 1 < len(steps) else dummy
            # second time round, the item you're on means nothing else is there: leave it
            target = sets[j] if i < n else self.str_sel(cur, [(gear[j]["actor"], dummy)], sets[j])
            steps[i] = self.bool_sel(have[j], "Value", target, nxt)
        return self.str_sel(cur, [(g["actor"], steps[k + 1]) for k, g in enumerate(gear)], steps[0])


WHEEL_FLAG = "Rando_DpadWheel"  # set before a D-pad wheel opens, cleared once you've let go after it
ITEMS = "AssignableItem"  # the item wheel's category, put back after a D-pad wheel
# UI_CurrentShortCutCategory values. The wheel has no tunic category: the tunic wheel is the boots' one with our
# TUNIC_FLAG set (parity/_extras_wheel.py wheel_cat)
CATEGORY = {"head": "HeadArmor", "boots": "Boot", "tunics": "Boot"}
HAVE_ANY = {"head": "Rando_DpadWheel_Head_Exp", "boots": "Rando_DpadWheel_Boots_Exp",
            "tunics": "Rando_DpadWheel_Tunics_Exp"}
BUTTON = {"head": "Up", "boots": "Down", "tunics": "Left"}


def with_tunics(d):
    """The D-pad data with the adult's tunics as a third slot (D-pad left), for remake_dpad_gear "wheel_tunics"."""
    return dict(d, gear=dict(d["gear"], tunics=d["tunics"]), slots=dict(d["slots"], tunics=d["tunic_slot"]))


def wheel_expressions(d):
    """{name: steps}: you have something for this wheel, at an age that can wear it (both boots and the tunics are
    adult only). The Kokiri tunic (default) doesn't count: you always have it, so the tunic wheel only opens once you
    have the Goron or Zora tunic."""
    out = {}
    for slot, gear in d["gear"].items():
        gear = [g for g in gear if not g.get("default")]
        steps = []
        for k, g in enumerate(gear):
            a = g["actor"]
            steps += [[BOOL, f"IsGet.{a}"], [INT_GT, f"PouchData.{a}.StockNum"], [INT_CONST, 0], [AND]]
            if not g["child"]:
                steps += [[BOOL, CHILD], [NOT], [AND]]
            if not g["adult"]:
                steps += [[BOOL, CHILD], [AND]]
            if k:
                steps.append([OR])
        out[HAVE_ANY[slot]] = steps
    return out


def _set_category(g, value):
    h = g.copy("hash", String=value)
    cat = g.copy("set_enum")
    g.edits.append({"link": {"from": h, "output": "MurMur3Hash", "to": cat, "input": "Value"}})
    return cat


def _prep_wheel(g, slot, tunics=False):
    """Wheel mode, the frames before the wheel opens: with something to show, the wheel's category and our flag (the
    wheel's own graph keeps the category while the flag is set). Save data writes land at the end of the frame, and
    the wheel reads the category as it builds its slots, so it has to be there before the open request. The counter
    counts on either way."""
    n = g.d["nodes"]
    flag = g.copy("set_bool", GameDataFullName=WHEEL_FLAG, Value=True)
    sets = [_set_category(g, CATEGORY[slot]), flag]
    if tunics:  # which wheel the boots' category is: the boots' or the tunics'
        from parity._extras_wheel import TUNIC_FLAG
        sets.append(g.copy("set_bool", GameDataFullName=TUNIC_FLAG, Value=slot == "tunics"))
    have = g.copy("get_exp", GameDataFullName=HAVE_ANY[slot])
    return g.sim([g.bool_sel(have, "Value", g.sim(sets), n["dummy"]), n["step"]])


def _open_wheel(g, slot, again):
    """Wheel mode's fire: with something to show, the game's own open request (its node); the counter either way."""
    n = g.d["nodes"]
    have = g.copy("get_exp", GameDataFullName=HAVE_ANY[slot])
    return g.sim([g.bool_sel(have, "Value", n["set_bool"], n["dummy"]), again])


def _after_wheel(g, chain, tunics=False):
    """Back from a D-pad wheel (the flag set, this module isn't running as part of the wheel's closing, and neither
    D-pad up nor down is held any more): the item wheel's category back, the flag cleared, the counter reset. The pick
    itself is on Link already (the code patch equips it the way the Equipment menu does). Otherwise `chain`."""
    n = g.d["nodes"]
    clear = g.copy("set_bool", GameDataFullName=WHEEL_FLAG, Value=False)
    if tunics:
        from parity._extras_wheel import TUNIC_FLAG
        done = g.sim([_set_category(g, ITEMS), clear, g.copy("set_bool", GameDataFullName=TUNIC_FLAG, Value=False),
                      n["reset"]])
        done = g.bool_sel(n["hold"], "HoldLeft", chain, done)
    else:
        done = g.sim([_set_category(g, ITEMS), clear, n["reset"]])
    let_go = g.bool_sel(n["hold"], "HoldUp", chain, g.bool_sel(n["hold"], "HoldDown", chain, done))
    flag = g.copy("get_bool", GameDataFullName=WHEEL_FLAG)
    return g.bool_sel(n["closing"], "Input", chain, g.bool_sel(flag, "Value", let_go, chain))


def wheel_edits(d, tunics=False):
    """The wheel's own graph (ShortCut.module): it skips forcing the item category when our flag is set, and it
    stays open while D-pad up or down (and left, with the tunic wheel) is held, as it does for L and R."""
    w = d["wheel"]
    W = w["nodes"]
    src = {"file": w["file"]}
    e = []

    def copy(lab, node, **inputs):
        e.append({"copy": {"from": src, "nodes": [node], "label": lab, "follow": False}})
        e.extend({"set_input": {"node": f"{lab}:{node}", "name": k, "value": v}} for k, v in inputs.items())
        return f"{lab}:{node}"

    def sel(lab, src_node, output, yes, no):
        r = copy(lab, W["hold_r"])  # a BoolSelector of this graph
        e.extend([{"feed": {"from": src_node, "output": output, "to": r, "input": "Input"}},
                  {"add_child": {"parent": r, "child": yes, "name": "True"}},
                  {"add_child": {"parent": r, "child": no, "name": "False"}}])
        return r
    q = copy("wq", W["get_bool"], GameDataFullName=WHEEL_FLAG)
    keep = sel("wk", q, "Value", W["dummy"], W["set_category"])
    e += [{"set_child": {"parent": W["force"], "which": 0, "child": keep}},
          {"set_child": {"parent": W["force"], "which": 1, "child": keep}}]
    left = sel("wl", W["hold"], "HoldLeft", W["held"], W["end"]) if tunics else W["end"]
    down = sel("wd", W["hold"], "HoldDown", W["held"], left)
    up = sel("wu", W["hold"], "HoldUp", W["held"], down)
    e.append({"set_child": {"parent": W["hold_r"], "which": "False", "child": up}})
    return [{"file": w["file"], "edits": e}]


def plan(d, settings, wheel=False, tunics=False):
    """(plan sections, read-back notes) for the option. wheel: holding the D-pad opens the game's item wheel on the
    accessories or boots (the code patch in parity/_extras_wheel.py) instead of switching straight away. tunics (with
    wheel): holding D-pad left opens it on the adult's tunics (a tap still plays the ocarina, on release)."""
    if tunics:
        d = with_tunics(d)
    n = d["nodes"]
    g = _Graph(d)
    if wheel:
        flags = {}
        start = g.copy("reset", Value=START)
        again = g.copy("reset", Value=AGAIN)
        head, boots = _open_wheel(g, "head", again), _open_wheel(g, "boots", again)
        fire_head, fire_boots = (lambda: head), (lambda: boots)
        prep = {"head": _prep_wheel(g, "head", tunics), "boots": _prep_wheel(g, "boots", tunics)}
    else:
        flags = picker_flags(settings)
        sync = g.copy("sync", IsOnlyPouchPlayer=False)  # Link himself, not just the menu's model
        index = g.copy("index")
        head = g.cycle("head", flags, sync, index)
        boots = g.cycle("boots", flags, sync, index)
        start = g.copy("reset", Value=START)
        again = g.copy("reset", Value=AGAIN)
        fire_head, fire_boots = (lambda: g.sim([head, again])), (lambda: g.sim([boots, again]))
        prep = {"head": None, "boots": None}
    rest = n["reset"]
    if tunics:  # D-pad left: a tap is the ocarina's (on release, the code patch), a hold opens the tunic wheel
        left_held = g.bool_sel(n["hold"], "HoldLeft",
                               g.timer(_open_wheel(g, "tunics", again), _prep_wheel(g, "tunics", True)), n["reset"])
        rest = g.bool_sel(n["trig"], "TrigLeft", start, left_held)
    down_held = g.bool_sel(n["hold"], "HoldDown", g.timer(fire_boots(), prep["boots"]), rest)
    down = g.bool_sel(n["trig"], "TrigDown", start, down_held)
    up_held = g.bool_sel(n["hold"], "HoldUp", g.timer(fire_head(), prep["head"]), down)
    up = g.bool_sel(n["trig"], "TrigUp", start, up_held)
    if wheel:
        up = _after_wheel(g, up, tunics)
    g.edits.append({"set_child": {"parent": n["hook"], "which": "False", "child": up}})
    if wheel:
        from parity import _extras_wheel as W
        used = {g["actor"]: 0 for gear in d["gear"].values() for g in gear}  # each piece's use-order stamp
        flags_new = {WHEEL_FLAG: False}
        if tunics:
            flags_new[W.TUNIC_FLAG] = False
        sections = {"gamedata": {"add_bools": flags_new, "add_boolexp": wheel_expressions(d),
                                 "add_ints": {W.GEAR_CLOCK: 0},
                                 "add_seeded_ints": {"seed": W.GEAR_SEED, "rows": used}},
                    "ainb": [{"file": d["file"], "edits": g.edits}] + wheel_edits(d, tunics)}
        return sections, {"flags": {}, "exps": wheel_expressions(d), "wheel": True, "tunics": tunics}
    exps = expressions(d, flags)
    sections = {"gamedata": {"add_boolexp": exps}, "ainb": [{"file": d["file"], "edits": g.edits}]}
    return sections, {"flags": flags, "exps": exps}


# Read-back: replays presses and holds through the built graph, for every age, equipped item and a spread of what
# you have, and checks each switch against the menu's list.

class _Run:
    def __init__(self, a, exps, d):
        self.a, self.exps, self.d = a, exps, d

    def _in(self, i, t, name):
        return next(e for e in self.a.nodes[i]["inputs"][t] if e["name"] == name)

    def _out(self, i, t, e):
        return self.a.nodes[e["node"]]["outputs"][t][e["plug"]]["name"]

    def value(self, st, i, t, name):
        e = self._in(i, t, name)
        if e["node"] < 0:
            return e["value"]
        s = self.a.nodes[e["node"]]
        if s["type"] == 104:  # ModuleIF_Input_Bool: the module's IsClosingShortCut
            return st.get("closing", False)
        out = self._out(i, t, e)
        if s["name"] == "SeqQueryControllerTrigMaskChecker":
            return out in st["trig"]
        if s["name"] == "SeqQueryControllerHoldMaskChecker":
            return out in st["hold"]
        if s["name"] == "SeqQueryGetNonStructGameDataBoolExp":
            return self.boolexp(st, self.value(st, e["node"], "string", "GameDataFullName"))
        if s["name"] == "SeqQueryGetNonStructGameDataBool":
            return st["bools"].get(self.value(st, e["node"], "string", "GameDataFullName"), False)
        if s["name"] == "SeqQueryGetNonStructGameDataString64":
            return st["strings"].get(self.value(st, e["node"], "string", "GameDataFullName"), "")
        if s["name"] == "SeqQueryGetNonStructGameDataFloat":
            return st["counter"]
        if s["name"] == "SeqQueryGetGameFrameStepRate":
            return FRAME_STEP
        if s["name"] == "SeqQueryCalcStringHashMurMur3":  # the hashed string itself, which is what it stands for
            return self.value(st, e["node"], "string", "String")
        raise ValueError(f"node {i} reads {s['name']}, which the read-back doesn't know")

    def boolexp(self, st, name):
        from romtools import murmur3_32
        vals = self.exps.get(murmur3_32(name))
        if vals is None:
            raise ValueError(f"no expression {name} in the built save data")
        names = st["names"]
        stack, k = [], 0
        while k < len(vals):
            op = vals[k][0]
            if op == BOOL:
                stack.append(bool(st["bools"].get(names[vals[k][1]], False)))
            elif op in (INT_GT, INT_EQ, INT_LT) and k + 1 < len(vals) and vals[k + 1][0] == INT_CONST:
                v, c = st["ints"].get(names[vals[k][1]], 0), vals[k + 1][1]
                stack.append(v > c if op == INT_GT else v == c if op == INT_EQ else v < c)
                k += 1
            elif op == NOT:
                stack.append(not stack.pop())
            elif op in (AND, OR):
                y, x = stack.pop(), stack.pop()
                stack.append((x and y) if op == AND else (x or y))
            else:
                raise ValueError(f"{name}: step {vals[k]} isn't one the D-pad expressions use")
            k += 1
        if len(stack) != 1:
            raise ValueError(f"{name}: leaves {len(stack)} values")
        return stack[0]

    def run(self, st, i, acts):
        a = self.a
        n = a.nodes[i]
        kids = n["plugs"][2]
        if n["type"] == 7:
            pick = "True" if self.value(st, i, "bool", "Input") else "False"
            return self.run(st, next(pl["node"] for pl in kids if pl["name"] == pick), acts)
        if n["type"] == 5:
            v = self.value(st, i, "string", "Input")
            cases, default = a.string_cases(i)
            return self.run(st, next((c for s, c in cases if s == v), default[0]), acts)
        if n["type"] == 4:
            v = self.value(st, i, "float", "Input")
            cases, default = a.f32_cases(i)
            return self.run(st, next((c for lo, hi, c in cases if lo <= v <= hi), default[0]), acts)
        if n["type"] == 3:
            for pl in kids:
                self.run(st, pl["node"], acts)
            return acts
        name = n["name"]
        if name == "SeqOneShotSetNonStructGameDataFloat":
            acts.append(("counter", self.value(st, i, "float", "Value")))
        elif name == "SeqExecuteAddNonStructGameDataFloat":
            acts.append(("add", self.value(st, i, "float", "Value")))
        elif name == "SeqOneShotSetNonStructGameDataString64":
            acts.append(("write", self.value(st, i, "string", "GameDataFullName"), self.value(st, i, "string", "Value")))
        elif name == "SeqSyncPlayerEquipmentAndGameData":
            acts.append(("sync", self.value(st, i, "bool", "IsOnlyPouchPlayer")))
        elif name == "SeqOneShotPouchTargetSyncEquipmentIndex":
            acts.append(("index",))
        elif name == "SeqOneShotPushToPouch":
            acts.append(("push", self.value(st, i, "string", "ActorName"), self.value(st, i, "int", "Num")))
        elif name == "SeqOneShotSetNonStructGameDataBool":
            acts.append(("bool", self.value(st, i, "string", "GameDataFullName"), self.value(st, i, "bool", "Value")))
        elif name == "SeqOneShotSetNonStructGameDataEnum":
            acts.append(("enum", self.value(st, i, "string", "GameDataFullName"), self.value(st, i, "ptr", "Value")))
        elif name != "SeqExecuteGenericDummyAction":
            raise ValueError(f"node {i} is {name}, which the read-back doesn't know")
        return acts


def _frame(r, st, start):
    """One frame of the 'neither L nor R held' branch: the actions, applied to the state."""
    acts = r.run(st, start, [])
    for act in acts:
        if act[0] == "counter":
            st["counter"] = act[1]
        elif act[0] == "add":
            st["counter"] += act[1]
        elif act[0] == "write":
            st["strings"][act[1]] = act[2]
    return acts


def _expected(gear, have, current):
    """What the menu's list says comes next: (actor, None) or (None, None) when nothing else is there."""
    names = [g["actor"] for g in gear]
    k = names.index(current) if current in names else -1
    order = names[k + 1:] + names[:k] if k >= 0 else names
    return next((x for x in order if x in have), None)


def _verify_wheel(patch, romfs, d, a, gd, tunics=False):
    """Wheel mode: a held D-pad asks for the wheel on the right category when you have something for it at your age
    (and does nothing otherwise), the pick gets applied once the wheel has closed (not while it closes), the wheel's
    graph keeps the category and stays open while the D-pad is held, the flag's save row is there, the use-order clock
    and every piece's stamp are saved Int rows where the code looks for them, and the code patch beside the patch
    folder is the one parity/_extras_wheel.py makes and still fits the player's game."""
    import ainb
    from romtools import murmur3_32
    from parity import _extras_wheel as W
    bad = []
    exps = {int(e["Hash"]): [[int(v) for v in s] for s in e["Values"]] for e in gd["Data"]["BoolExp"]}
    for name in HAVE_ANY.values():
        if murmur3_32(name) not in exps:
            bad.append(f"save data: no expression {name}")
    ints = {int(e["Hash"]): e for e in gd["Data"]["Int"]}
    want = {murmur3_32(W.GEAR_CLOCK): W.GEAR_CLOCK}
    want.update({murmur3_32(g["actor"], W.GEAR_SEED): f"{g['actor']}'s use order" for gear in d["gear"].values()
                 for g in gear})
    for h, what in want.items():
        e = ints.get(h)
        if e is None or int(e.get("SaveFileIndex", -1)) != 0 or int(e.get("DefaultValue", 1)) != 0:
            bad.append(f"save data: {what} isn't a saved Int starting at 0 (hash {h:#x})")
    if bad:
        return bad
    names = {murmur3_32(CHILD): CHILD}
    for gear in d["gear"].values():
        for g in gear:
            for x in (f"IsGet.{g['actor']}", f"PouchData.{g['actor']}.StockNum"):
                names[murmur3_32(x)] = x
    r = _Run(a, exps, d)
    start = next(pl["node"] for pl in a.nodes[d["nodes"]["hook"]]["plugs"][2] if pl["name"] == "False")

    def state(child, have, flag=False, closing=False):
        st = {"trig": set(), "hold": set(), "counter": 0.0, "names": names, "strings": {}, "ints": {},
              "bools": {CHILD: child, WHEEL_FLAG: flag}, "closing": closing}
        for gear in d["gear"].values():
            for g in gear:
                st["bools"][f"IsGet.{g['actor']}"] = g["actor"] in have
                st["ints"][f"PouchData.{g['actor']}.StockNum"] = int(g["actor"] in have)
        return st
    from parity._extras_wheel import TUNIC_FLAG
    for slot in d["gear"]:
        button, gear = BUTTON[slot], d["gear"][slot]
        for child in (True, False):
            for have in (set(), {gear[0]["actor"]}, {gear[-1]["actor"]}, {g["actor"] for g in gear}):
                usable = [g for g in gear if g["actor"] in have and g["child" if child else "adult"]
                          and not g.get("default")]
                st = state(child, have)
                fired, prepped = None, None
                for f in range(40):
                    st["trig"] = {f"Trig{button}"} if f == 0 else set()
                    st["hold"] = {f"Hold{button}"}
                    acts = _frame(r, st, start)
                    if WHEEL[0] <= st["counter"] <= WHEEL[1]:
                        bad.append(f"holding {button} put the counter in the item wheel's range")
                    if any(x[0] in ("sync", "index", "write") for x in acts):
                        bad.append(f"holding {button} re-applies Link's equipment ({acts})")
                    if ("enum", "UI_CurrentShortCutCategory", CATEGORY[slot]) in acts and prepped is None:
                        prepped = (f, acts)
                    if f and acts and acts[-1] == ("counter", AGAIN):
                        fired = (f, acts)
                        break
                want = ([("bool", "UI_IsNeedOpenShortCut", True)] if usable else []) + [("counter", AGAIN)]
                want_prep = [("enum", "UI_CurrentShortCutCategory", CATEGORY[slot]), ("bool", WHEEL_FLAG, True)]
                if tunics:
                    want_prep.append(("bool", TUNIC_FLAG, slot == "tunics"))
                age = "child" if child else "adult"
                if fired is None or fired[1] != want or not 14 <= fired[0] <= 18:
                    bad.append(f"{age} holding D-pad {button.lower()} with {sorted(have)}: {fired}, expected {want}")
                elif usable and (prepped is None or prepped[1][:len(want_prep)] != want_prep
                                 or not 1 <= fired[0] - prepped[0] <= 4):
                    bad.append(f"{age} holding D-pad {button.lower()}: the category isn't set a few frames before "
                               f"the wheel opens ({prepped}, opens at frame {fired[0]})")
                elif not usable and prepped is not None:
                    bad.append(f"{age} holding D-pad {button.lower()} with nothing to show set the category")
    st = state(False, set(), flag=True)
    back = [("enum", "UI_CurrentShortCutCategory", ITEMS), ("bool", WHEEL_FLAG, False)]
    back += [("bool", TUNIC_FLAG, False)] if tunics else []
    if _frame(r, st, start) != back + [("counter", 0.0)]:
        bad.append("back from a D-pad wheel, the item wheel's category isn't put back and the flags cleared")
    for button in [BUTTON[s] for s in d["gear"]]:
        st = state(False, set(), flag=True)
        st["hold"] = {f"Hold{button}"}
        if ("bool", WHEEL_FLAG, False) in _frame(r, st, start):
            bad.append(f"the D-pad wheel's flag gets cleared while D-pad {button.lower()} is still held")
    st = state(False, set(), flag=True, closing=True)
    if any(x[0] in ("sync", "enum") or x == ("bool", WHEEL_FLAG, False) for x in _frame(r, st, start)):
        bad.append("the D-pad wheel gets wound up while the wheel is still closing")
    if not any(int(e["Hash"]) == murmur3_32(WHEEL_FLAG) for e in gd["Data"]["Bool"]):
        bad.append(f"save data: no {WHEEL_FLAG}")
    w, Wn = d["wheel"], d["wheel"]["nodes"]
    path = os.path.join(patch, w["file"])
    if not os.path.exists(path):
        return bad + [f"{w['file']}: not in the patch"]
    s = ainb.Ainb(open(path, "rb").read())

    def kid(i, name):
        return next((pl["node"] for pl in s.nodes[i]["plugs"][2] if pl["name"] == name), None)

    def reads(i):
        e = next(x for x in s.nodes[i]["inputs"]["bool"] if x["name"] == "Input")
        src = s.nodes[e["node"]]
        out = src["outputs"]["bool"][e["plug"]]["name"]
        name = next((x["value"] for x in src["inputs"]["string"] if x["name"] == "GameDataFullName"), None)
        return e["node"], out, name
    kids = [pl["node"] for pl in s.nodes[Wn["force"]]["plugs"][2]]
    keep = kids[0] if len(set(kids)) == 1 else None
    if keep is None or s.nodes[keep]["type"] != 7 or reads(keep)[2] != WHEEL_FLAG             or kid(keep, "False") != Wn["set_category"] or kid(keep, "True") != Wn["dummy"]:
        bad.append(f"{w['file']}: opening doesn't keep the category when {WHEEL_FLAG} is set")
    chain, at = [], kid(Wn["hold_r"], "False")
    for slot in d["gear"]:
        ok = at is not None and s.nodes[at]["type"] == 7 and reads(at)[:2] == (Wn["hold"], f"Hold{BUTTON[slot]}") \
            and kid(at, "True") == Wn["held"]
        chain.append(ok)
        at = kid(at, "False") if at is not None else None
    if not all(chain) or at != Wn["end"]:
        bad.append(f"{w['file']}: the wheel doesn't stay open while D-pad {'/'.join(BUTTON[s].lower() for s in d['gear'])}"
                   f" is held")
    code = os.path.join(os.path.dirname(os.path.abspath(patch)), "exefs", W.PATCH_FILE)
    if not os.path.exists(code):
        bad.append(f"exefs/{W.PATCH_FILE}: not beside the patch")
    elif open(code, encoding="utf-8").read() != W.pchtxt(tunics):
        bad.append(f"exefs/{W.PATCH_FILE}: not the code patch this build makes")
    bad += [f"code patch: {x}" for x in W.check(W.image_path(romfs), tunics)]
    if tunics and not any(int(e["Hash"]) == murmur3_32(TUNIC_FLAG) for e in gd["Data"]["Bool"]):
        bad.append(f"save data: no {TUNIC_FLAG}")
    return bad


def verify(patch, note, romfs, d):
    """Problems with the built D-pad edit: the hook, the timing, and every switch over the states tried."""
    import ainb
    from romtools import Romfs, byml_load, murmur3_32
    bad = []
    path = os.path.join(patch, d["file"])
    if not os.path.exists(path):
        return [f"{d['file']}: not in the patch"]
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    a = ainb.Ainb(open(path, "rb").read())
    base = ainb.Ainb(Romfs(romfs, os.path.join(HERE, "original")).raw(d["file"]))
    n = d["nodes"]
    # the game's own nodes are as they were, but for the hook's False case and the checkers' newly read outputs
    for i, (x, y) in enumerate(zip(base.nodes, a.nodes)):
        kx = [(pl["node"], pl["name"]) for pl in x["plugs"][2]]
        ky = [(pl["node"], pl["name"]) for pl in y["plugs"][2]]
        if i == n["hook"]:
            kx = [k for k in kx if k[1] != "False"]
            ky = [k for k in ky if k[1] != "False"]
        if x["name"] != y["name"] or kx != ky or any(
                [(e["name"], e["node"], e.get("value")) for e in x["inputs"][t]]
                != [(e["name"], e["node"], e.get("value")) for e in y["inputs"][t]] for t in ainb.PTYPES):
            bad.append(f"{d['file']}: the game's node {i} ({x['name']}) changed")
    gd, _ = byml_load(fs.read(GAMEDATA), allow_big=True)
    exps = {int(e["Hash"]): [[int(v) for v in s] for s in e["Values"]] for e in gd["Data"]["BoolExp"]}
    for name, steps in note["exps"].items():
        if murmur3_32(name) not in exps:
            bad.append(f"save data: no expression {name}")
    if bad:
        return bad
    if note.get("wheel"):
        tunics = bool(note.get("tunics"))
        return sorted(set(_verify_wheel(patch, romfs, with_tunics(d) if tunics else d, a, gd, tunics)))
    flags = note["flags"]
    names = {}
    for gear in d["gear"].values():
        for g in gear:
            for x in (f"IsGet.{g['actor']}", f"PouchData.{g['actor']}.StockNum"):
                names[murmur3_32(x)] = x
    for x in list(flags.values()) + [CHILD]:
        names[murmur3_32(x)] = x
    r = _Run(a, exps, d)
    start = next(pl["node"] for pl in a.nodes[n["hook"]]["plugs"][2] if pl["name"] == "False")
    rnd = random.Random(1)

    def state(age_child, have, aside, current, slot):
        st = {"trig": set(), "hold": set(), "counter": 0.0, "names": names, "strings": {d["slots"][slot]: current},
              "bools": {CHILD: age_child}, "ints": {}}
        for gear in d["gear"].values():
            for g in gear:
                a_ = g["actor"]
                owned = a_ in have
                st["bools"][f"IsGet.{a_}"] = owned or a_ in aside
                st["ints"][f"PouchData.{a_}.StockNum"] = 1 if owned and a_ not in aside else 0
                if a_ in flags:
                    st["bools"][flags[a_]] = a_ in aside
        return st

    def hold(st, button, frames):
        """Presses and holds a D-pad button: [(frame, actions)] of the frames that did more than count."""
        out = []
        for f in range(frames):
            st["trig"] = {f"Trig{button}"} if f == 0 else set()
            st["hold"] = {f"Hold{button}"}
            acts = _frame(r, st, start)
            if WHEEL[0] <= st["counter"] <= WHEEL[1]:
                bad.append(f"holding {button} put the counter in the item wheel's range ({st['counter']})")
            if any(x[0] not in ("add", "counter") for x in acts) or f == 0:
                out.append((f, acts))
        return out

    checked = 0
    for slot, button in (("head", "Up"), ("boots", "Down")):
        gear = d["gear"][slot]
        actors = [g["actor"] for g in gear]
        haves = [set()] + [{x} for x in actors] + [set(actors)]
        haves += [set(rnd.sample(actors, rnd.randint(2, len(actors)))) for _ in range(40)]
        for child in (True, False):
            for have in haves:
                for current in actors + [""]:
                    aside = {x for x in have if x in flags and rnd.random() < 0.5}
                    usable = {g["actor"] for g in gear if g["actor"] in have and g["child" if child else "adult"]}
                    want = _expected(gear, usable, current)
                    st = state(child, have, aside, current, slot)
                    frames = hold(st, button, 50)
                    checked += 1
                    first = frames[0][1] if frames and frames[0][0] == 0 else []
                    if first != [("counter", START)]:
                        bad.append(f"{button} press: {first}, not the counter set to {START}")
                    fires = [(f, acts) for f, acts in frames if f > 0]
                    if want is None:
                        if any(x[0] == "write" for _, acts in fires for x in acts):
                            bad.append(f"{slot} {current or 'none'} with {sorted(usable)}: switched with nothing "
                                       f"else to switch to")
                        continue
                    if not fires:
                        bad.append(f"{slot} {current or 'none'}: no switch in 50 frames of holding")
                        continue
                    f, acts = fires[0]
                    if not 14 <= f <= 17:
                        bad.append(f"{slot}: the first switch came {f} frames in")
                    writes = [x for x in acts if x[0] == "write"]
                    if writes != [("write", d["slots"][slot], want)]:
                        bad.append(f"{slot} {current or 'none'} with {sorted(usable)} ({'child' if child else 'adult'}):"
                                   f" wrote {writes}, expected {want}")
                        continue
                    tail = [x for x in acts if x[0] in ("sync", "index")]
                    if tail != [("sync", False), ("index",)] or acts[-1] != ("counter", AGAIN):
                        bad.append(f"{slot} {want}: switch steps {acts}")
                    put_back = [x for x in acts if x[0] in ("push", "bool")]
                    if want in aside:
                        exp_back = [("push", f"Work/Actor/{want}.engine__actor__ActorParam.gyml", 1),
                                    ("bool", flags[want], False)]
                        if put_back != exp_back:
                            bad.append(f"{slot} {want} (put aside): {put_back}, not put back first")
                    elif put_back:
                        bad.append(f"{slot} {want}: {put_back} with nothing put aside")
                    if len(fires) > 1 and fires[1][0] - f not in (30, 31, 32):
                        bad.append(f"{slot}: the next switch came {fires[1][0] - f} frames later")
    # a frame with nothing held resets the counter, as the game does
    st = state(False, set(), set(), "", "head")
    st["counter"] = -1020.0
    if _frame(r, st, start) != [("counter", 0.0)] or st["counter"] != 0.0:
        bad.append("with nothing held the counter isn't reset to 0 any more")
    if not checked:
        bad.append("D-pad read-back tried nothing")
    return sorted(set(bad))
