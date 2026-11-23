"""The mask button's picker and its owned record.

What the game does (from code and files)
The 8 masks share one equipment button (UI/Pouch/PouchTable EquipmentArray Pa_HeadEquip_02), and it shows the
FIRST mask of its list in the pouch: Mask of Truth, Goron, Zora, Gerudo, Bunny Hood, Spooky, Skull, Keaton
(both ages). Nothing remembers a choice. Wearing puts on the shown mask, and every mask check reads the worn
one (EventQueryPlayerIsEquipArmor, the head slot's equipment actor). Vanilla lends one mask at a time. Once
masks are shuffled (shuffle_child_trade, Archipelago's mask shuffles, or a mask to start with) Link owns
several, and an owned Mask of Truth, Goron, Zora or Gerudo Mask hides the Skull Mask for good. That's an
unbeatable-class problem at Deku Theater.

What this adds
It uses event-flow edits, one Sequence AI edit and borrowed saved flags, the same machinery as the trade
button (tools/trade_slot.py) done for the masks.
- An owned record per mask. That's one borrowed saved flag each (tools/rando/free_flags.py,
  data/rando/songs_trade_masks.json "flags_claimed"), true while the mask is owned but put aside. Owned means
  in the pouch or put aside.
- The picker, anywhere. "Talk to Navi" (her button) when she has nothing to say requests
  NaviHint:NaviHint_Field, a shipped do-nothing scene. The Sequence edit also sets a token flag so only that
  press switches. With two or more owned masks it puts the button's mask aside, so the button shows the next
  owned mask, and past the last one everything comes back and the first is shown again. Link then wears the
  button's mask (PlayerStatus.EquipHeadArmor and IsActiveHeadArmor set, and the head-armor equipment created
  the way vanilla creates the Lens of Truth's). Navi says what happened and how to switch again
  (EventFlowMsg/NaviHint RMS_Switch, 16 languages, SWITCH_TEXT). With one mask or none nothing changes. The
  picker's steps live in ReplaceEquipmentForEraChange, which isn't resident (it only loads with its era-change
  scenes and with the Navi scene), so nothing resident grows.
- Every check of a mask also counts one put aside, without moving anything. That's
  PouchSystemActor.EventQueryIsExistInPouch in any flow and the Happy Mask Shop's
  IsExistInPouchWithNameGameData of Shop_SelectItemName. The expression flags that read a mask's stock do the
  same (HappyMaskShop_HasMask_* of the masks left vanilla, RentalAnyMask, UntilRentMaskOf*).
- Every sale (NpcCommon:SellMask, which takes the worn mask by name) brings back everything put aside right
  after.

Only seeds where Link can own two masks at once get any of this (needs_picker), so masks shuffled or a mask to
start with. make_patch applies the event hooks after every other edit, on each file as patched
(tools/trade_slot.py stage2_next hands each file here once the trade button is done with it), so they land on
the steps the way the other plugins left them. The read-back (verify) re-reads the built files and runs the
picker's steps over pouch states with an interpreter of the patched Navi scene and picker, then walks the
seed's mask uses.
"""
import functools
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(HERE, "data", "rando", "songs_trade_masks.json")
HOST = "ReplaceEquipmentForEraChange"  # the picker's steps (see the module docstring)
NAVI, NAVI_ENTRY = "NaviHint", "NaviHint_Field"
SEQUENCE = "Sequence/NaviHintEvent.module.ainb"
SET_BOOL_FROM = {"file": "Sequence/BeforeMinusMenu.module.ainb", "node": 2}  # a SeqOneShotSetGameDataBool to copy
SELL_TAKE = "Event489"  # NpcCommon:SellMask's take of its ReceiveItem
PREFIX = "RMS_"  # every entry and step this adds
PICK, UNSTASH, RESTORE, ASIDE, EQUIP, NAVI_GRAPH, HOOKS = "RMS_S", "RMS_U", "RMS_R", "RMS_A", "RMS_E", "RMS_N", "RMS_H"
SCRATCH_KEYS = ("picker_scratch", "switched", "token")
TOKEN_STRUCT = "HavePlayedNaviBalloonMessage"  # the borrowed flags' GameData struct (the token is one of them)
EQUIP_HEAD, EQUIP_ACTIVE = "PlayerStatus.EquipHeadArmor", "PlayerStatus.IsActiveHeadArmor"
YES, NO = 0, 1  # query answers (tools/progressive.py)
POUCH, GD, PLAYER, NAVI_ACTOR = "PouchSystemActor", "GameDataActor", "Player_Event", "Npc_Navi"
EXIST, TAKE = "EventQueryIsExistInPouch", "EventTriggerAddOrRemovePouchContent"
NAME_EXIST, SELECT_NAME = "EventQueryIsExistInPouchWithNameGameData", "Shop_SelectItemName"
CREATE = "EventTriggerEquipmentUserRequestCreateStaticEquipment"
TEXT_FILE, SWITCH_LABEL = "EventFlowMsg/NaviHint.msbt", "RMS_Switch"
# Navi's line after a switch, using each language's word for "mask" the way its item names use it (Talk to Navi
# is her button)
SWITCH_TEXT = {
    "USen": "You put on your next mask!\nTalk to me again to switch masks.",
    "EUen": "You put on your next mask!\nTalk to me again to switch masks.",
    "EUde": "Du trägst jetzt deine nächste Maske!\nRede wieder mit mir, um zu wechseln.",
    "EUfr": "Tu portes ton masque suivant !\nParle-moi encore pour en changer.",
    "USfr": "Tu portes ton masque suivant !\nParle-moi encore pour en changer.",
    "EUes": "¡Te has puesto tu siguiente máscara!\nHabla conmigo otra vez para cambiarla.",
    "USes": "¡Te pusiste tu siguiente máscara!\nHabla conmigo otra vez para cambiarla.",
    "EUit": "Hai indossato la maschera successiva!\nParlami di nuovo per cambiarla.",
    "EUnl": "Je draagt nu je volgende masker!\nPraat weer met me om te wisselen.",
    "EUpl": "Założyłeś następną maskę!\nPorozmawiaj ze mną znowu, by ją zmienić.",
    "EUru": "Ты надел следующую маску!\nПоговори со мной снова, чтобы сменить её.",
    "USpt": "Você colocou a próxima máscara!\nFale comigo de novo para trocar.",
    "JPja": "次のお面を かぶったよ！\nまた話しかけてくれたら お面を かえるね",
    "KRko": "다음 가면을 썼어!\n다시 말을 걸면 가면을 바꿔 줄게.",
    "CNzh": "戴上了下一个面具！\n再和我说话，就能换成别的面具。",
    "TWzh": "戴上了下一個面具！\n再跟我說話，就能換成別的面具。",
}


def needs_picker(settings):
    """Whether Link can own two masks at once. That's any mask shuffled (OoTR's shuffle_child_trade, which
    Archipelago's mask shuffles set too), so a found mask next to a rented or found one, since the shop no longer
    takes the old one back (parity/_songs_trade_child.py). Or a mask to start with, next to a rented one.
    Otherwise the shop lends one at a time and the button already shows it."""
    get = (lambda k: settings.get(k)) if isinstance(settings, dict) else (lambda k: getattr(settings, k, None))
    masks = set(data()["items"])
    return bool(masks & set(get("shuffle_child_trade") or [])) or bool(masks & set(get("starting_items") or {}))


@functools.lru_cache(maxsize=None)
def data():
    return json.load(open(DATA_PATH, encoding="utf-8"))


def plan_section(settings=None):
    """What songs_trade writes in the plan's "trade_slot" section as "masks", which is the button's order."""
    return {"order": list(data()["order"])}


def spec(order=None):
    """The plan's "masks" section made whole with this data (the order the plan names, today's flags and steps)."""
    d = data()
    order = list(order or d["order"])
    if sorted(order) != sorted(d["order"]):
        raise ValueError(f"mask_slot: the order {order} isn't the 8 masks {sorted(d['order'])}")
    fl = d["flags_claimed"]
    return {"order": order, "flags": {m: fl[m] for m in order}, "scratch": fl["picker_scratch"],
            "switched": fl["switched"], "token": fl["token"], "navi": d["navi"], "sequence": d["sequence"],
            "equip_state": d["equip"]["DynamicEquipmentState"], "sales": d["sales"], "items": d["items"]}


def plan_spec(section):
    return spec(section.get("order"))


def files(sp):
    """The event files make_patch opens for the masks (every file with a mask check, the sales, host, Navi scene)."""
    return sorted(set(data()["files"]) | {s["file"] for s in data()["sales"]})


def claimed_flags():
    """Every saved flag this holds (tools/rando/free_flags.py hold)."""
    return sorted(data()["flags_claimed"].values())


# Text, AI and save-data plan ops

def text_problems():
    """Checks that each language's switch line fits the message box and that every character is drawable. Width
    and lines use the Archipelago text's measures from the game's fonts, the same checks as tools/trade_slot.py
    text_problems."""
    from parity import _archipelago_text as at
    out = []
    for lang, text in SWITCH_TEXT.items():
        width, lines = at.BOX[lang] if lang in at.BOX else at.BOX["EUen"]
        rows = text.split("\n")
        if len(rows) > lines:
            out.append(f"{lang}: {len(rows)} lines, the box holds {lines}")
        for r in rows:
            if at._width([(c, None) for c in r], lang) > width:
                out.append(f"{lang}: {r!r} is wider than the box")
            if any(not at.drawable(c, lang) for c in r):
                out.append(f"{lang}: {r!r} has a character the font can't draw")
    return out


def text_widths():
    """{language: (widest line in ems, box width, lines, box lines)} for the report."""
    from parity import _archipelago_text as at
    out = {}
    for lang, text in SWITCH_TEXT.items():
        width, lines = at.BOX[lang] if lang in at.BOX else at.BOX["EUen"]
        rows = text.split("\n")
        out[lang] = (max(at._width([(c, None) for c in r], lang) for r in rows), width, len(rows), lines)
    return out


def text_ops():
    """make_patch "text" ops for the switch line in every language (Navi's own message file)."""
    return [{"lang": lang, "file": TEXT_FILE, "label": SWITCH_LABEL, "text": text, "add": True,
             "note": "mask button: Navi's line after a switch (tools/mask_slot.py)"}
            for lang, text in sorted(SWITCH_TEXT.items())]


def ainb_ops(sp):
    """make_patch "ainb" op. When Navi has no area hint (NaviHintEvent node area_sel's False case, which ends the
    module in vanilla), her button now sets the token flag and requests NaviHint_Field. It's built from copies of
    the module's button check, Simultaneous and event request, its struct read, and BeforeMinusMenu's struct-bool
    setter. Other frames end the same as before."""
    S, src = sp["sequence"], {"file": SEQUENCE}
    struct, _, member = sp["token"].partition(".")
    sb = SET_BOOL_FROM["node"]
    return [{"file": SEQUENCE, "edits": [
        {"copy": {"from": src, "nodes": [S["trig_sel"]], "label": "sel", "follow": False}},
        {"copy": {"from": src, "nodes": [S["sim"]], "label": "sim", "follow": False}},
        {"copy": {"from": src, "nodes": [S["request"]], "label": "req", "follow": False,
                  "values": {str(S["request"]): {"EventName": sp["navi"]["entry"]}}}},
        {"copy": {"from": src, "nodes": [S["struct_q"]], "label": "st", "follow": False,
                  "values": {str(S["struct_q"]): {"GameDataFullName": struct}}}},
        {"copy": {"from": {"file": SET_BOOL_FROM["file"]}, "nodes": [sb], "label": "set", "follow": False,
                  "values": {str(sb): {"GameDataName": member, "Value": True}}}},
        {"link": {"from": f"st:{S['struct_q']}", "output": "Value", "to": f"set:{sb}", "input": "ParentStruct"}},
        {"feed": {"from": S["trig"], "output": S["trig_out"], "to": f"sel:{S['trig_sel']}", "input": "Input"}},
        {"add_child": {"parent": f"sim:{S['sim']}", "child": f"set:{sb}"}},
        {"add_child": {"parent": f"sim:{S['sim']}", "child": f"req:{S['request']}"}},
        {"add_child": {"parent": f"sel:{S['trig_sel']}", "child": f"sim:{S['sim']}", "name": "True"}},
        {"add_child": {"parent": f"sel:{S['trig_sel']}", "child": S["end"], "name": "False"}},
        {"set_child": {"parent": S["area_sel"], "which": "False", "child": f"sel:{S['trig_sel']}"}},
    ]}]


def gamedata_ops(sp, skip=()):
    """make_patch "gamedata" op. Every expression flag that reads a mask's stock also counts the mask put aside, so
    StockNum = 0 becomes StockNum = 0 AND NOT aside and StockNum = 1 becomes StockNum = 1 OR aside. `skip` lists
    expressions another edit of this seed redefines (the shuffled masks' shelf conditions,
    parity/_songs_trade_child.py)."""
    d = data()
    by_hash = {int(h): m for m, h in d["stock_hash"].items()}
    exps = {}
    for name, vals in sorted(d["stock_exps"].items()):
        if name in skip:
            continue
        exps[name] = rewrite_exp(vals, by_hash, sp["flags"])
    return [{"boolexp": exps}] if exps else []


def rewrite_exp(vals, by_hash, flags):
    new, k = [], 0
    while k < len(vals):
        v = list(vals[k])
        if v[0] == 15 and v[1] in by_hash and k + 1 < len(vals) and vals[k + 1][0] == 16:
            const = vals[k + 1][1]
            new += [v, list(vals[k + 1]), [0, flags[by_hash[v[1]]]]] + ([[5], [3]] if const == 0 else [[4]])
            k += 2
            continue
        new.append(v)
        k += 1
    return new


# Nodes

def _q_pouch(actor, yes, no):
    return {"actor": POUCH, "query": EXIST, "params": {"Actor": actor, "Num": 1}, "cases": {YES: yes, NO: no}}


def _q_flag(flag, yes, no):
    return {"actor": GD, "query": "EventQueryIsGameDataBool", "params": {"GameDataName": flag, "Index": -1},
            "cases": {YES: yes, NO: no}}


def _set_flag(flag, value, nxt):
    return {"actor": GD, "action": "EventTriggerSetGameDataBool",
            "params": {"GameDataName": flag, "Value": value, "Index": -1}, "next": nxt}


def _pouch(actor, num, nxt):
    return {"actor": POUCH, "action": TAKE, "params": {"Actor": actor, "Num": num, "IsGetEvent": False,
                                                       "IsEquipDIrect": False, "IsSetMessageTargetActorName": False},
            "next": nxt}


def _call(entry, sp, mask, nxt, file=""):
    """A call of the put-back / put-aside entry for one mask (its flag passed along)."""
    return {"call": f"{file}:{entry}", "params": {"Actor": mask, "Flag": sp["flags"][mask]}, "next": nxt}


def store_graphs(sp):
    """{entry: (nodes, start)} for putting back / putting aside one mask ({Actor, Flag} arguments) and for everything
    back. They go in the picker's host and in each file with a sale."""
    order = sp["order"]
    arg_a, arg_f = {"arg": "Actor"}, {"arg": "Flag"}
    out = {RESTORE: ({"q": _q_flag(arg_f, "a", None), "a": _pouch(arg_a, 1, "c"), "c": _set_flag(arg_f, False, None)},
                     "q"),
           ASIDE: ({"q": _q_pouch(arg_a, "f", None), "f": _set_flag(arg_f, True, "r"), "r": _pouch(arg_a, -1, None)},
                   "q"),
           UNSTASH: ({f"r{i}": _call(RESTORE, sp, x, f"r{i + 1}" if i + 1 < len(order) else None)
                      for i, x in enumerate(order)}, "r0")}
    return out


def picker_graphs(sp):
    """{entry: (nodes, start)} added to the host: the store entries, the equip step ({Mask}) and the picker."""
    order = sp["order"]
    n_items = len(order)
    out = store_graphs(sp)
    arg_m = {"arg": "Mask"}
    out[EQUIP] = ({"h": {"actor": GD, "action": "EventTriggerSetGameDataString64",
                         "params": {"GameDataName": EQUIP_HEAD, "Value": arg_m, "Index": -1}, "next": "w"},
                   "w": _set_flag(EQUIP_ACTIVE, True, "c"),
                   "c": {"actor": PLAYER, "action": CREATE,
                         "params": {"EquipmentActorName": arg_m, "IsActive": True,
                                    "DynamicEquipmentState": sp["equip_state"]}, "next": "s"},
                   "s": _set_flag(sp["switched"], True, None)}, "h")

    def nx(label, i, end):
        return f"{label}{i}" if i < n_items else end
    S = sp["scratch"]
    n = {"s1": _set_flag(S, True, "cc0"), "s0": _set_flag(S, False, "cc0"),
         "w": _q_flag(S, "u", "u1"), "u": {"call": f":{UNSTASH}", "next": "v0"},
         "u1": {"call": f":{UNSTASH}", "next": None}}
    for i, x in enumerate(order):
        n[f"f{i}"] = _q_flag(sp["flags"][x], "s1", nx("f", i + 1, "s0"))      # anything put aside?
        n[f"cc{i}"] = _q_pouch(x, f"st{i}", nx("cc", i + 1, "w"))            # the button's mask ...
        n[f"st{i}"] = _call(ASIDE, sp, x, nx("an", i + 1, "w"))              # ... is put aside
        n[f"an{i}"] = _q_pouch(x, "v0", nx("an", i + 1, "w"))                # another after it in the pouch?
        n[f"v{i}"] = _q_pouch(x, f"x{i}", nx("v", i + 1, None))             # the button's new mask:
        n[f"x{i}"] = {"call": f":{EQUIP}", "params": {"Mask": x}, "next": None}  # worn
    out[PICK] = (n, "f0")
    for nodes, _start in out.values():  # identical parameter blocks shared (tools/evfl_build.py "share")
        for node in nodes.values():
            if node.get("params") and "copy" not in node:
                node["share"] = True
    return out


def navi_graph(sp):
    """(nodes, start) of NaviHint_Field's new start. Only the Navi button's request (the token) switches, and Navi
    says the line when a switch happened. Any other request ends at the vanilla do-nothing step."""
    nv = sp["navi"]
    msg = f"{TEXT_FILE.rsplit('.', 1)[0]}:{SWITCH_LABEL}"
    T, W = sp["token"], sp["switched"]
    nodes = {"t": _q_flag(T, "tc", f"@{nv['nothing']}"),
             "tc": _set_flag(T, False, "wc"),
             "wc": _set_flag(W, False, "p"),
             "p": {"call": f"{HOST}:{PICK}", "next": "q"},
             "q": _q_flag(W, "i", None),
             "i": {"copy": nv["talk_call"], "next": "m"},
             "m": {"copy": nv["talk"], "params_over": {"MessageId": msg}, "next": "z"},
             "z": _set_flag(W, False, None)}
    for node in nodes.values():
        if node.get("params") and "copy" not in node:
            node["share"] = True
    return nodes, "t"


# Sites in a (patched) flowchart

def _tr():
    import trade_slot
    return trade_slot


def sites(fc, masks, file_base):
    """[(kind, event, mask)] in one flowchart. The kinds are "query" (IsExistInPouch of a mask, Num 1), "name_query"
    (IsExistInPouchWithNameGameData of Shop_SelectItemName, the shop's "already have it") and "sale" (a call of
    NpcCommon:SellMask with a mask). Steps this added are skipped, and so are the picker's host and the Navi scene."""
    tr = _tr()
    out = []
    if file_base in (HOST, NAVI):
        return out
    for e in fc["events"]:
        if e["name"].startswith(PREFIX):
            continue
        if e["type"] == "subflow" and (e.get("flowchart"), e.get("entry_point")) == ("NpcCommon", "SellMask") and \
                tr._param(e, "ReceiveItem") in masks:
            out.append(("sale", e, tr._param(e, "ReceiveItem")))
            continue
        actor, what = tr._what(fc, e)
        if actor != POUCH or e["type"] != "switch":
            continue
        item = tr._param(e, "Actor")
        if what == EXIST and item in masks and tr._param(e, "Num") == 1:
            out.append(("query", e, item))
        elif what == NAME_EXIST and tr._param(e, "ActorName") == SELECT_NAME and tr._param(e, "Num") == 1:
            out.append(("name_query", e, None))
    return out


def stage2_next(ev, file_base, sp):
    """Event ops for one event file as already patched (an evfl.Evfl), or None when it's done. That's the picker's
    host entries, the Navi scene's new start, or every mask check and sale of the file hooked at once, in one
    graph per flowchart (HOOKS)."""
    tr = _tr()
    masks = set(sp["order"])
    ops = []
    for fc in ev.flowcharts:
        eps = fc["entry_points"]
        if file_base == HOST and fc["name"] == HOST:
            if PICK not in eps:
                ops += [{"flowchart": fc["name"], "add_graph": entry, "nodes": nodes, "start": start}
                        for entry, (nodes, start) in picker_graphs(sp).items()]
            continue
        if file_base == NAVI and fc["name"] == NAVI:
            if NAVI_GRAPH not in eps:
                if sp["navi"]["entry"] not in eps:
                    raise ValueError(f"{file_base}: no entry {sp['navi']['entry']}")
                nodes, start = navi_graph(sp)
                ops += [{"flowchart": fc["name"], "add_graph": NAVI_GRAPH, "nodes": nodes, "start": start},
                        {"flowchart": fc["name"], "entry": sp["navi"]["entry"], "next": f"{NAVI_GRAPH}_{start}"}]
            continue
        if HOOKS in eps:
            continue
        found = sites(fc, masks, file_base)
        if not found:
            continue
        names = {e["name"]: e for e in fc["events"]}
        actors = {a["name"] for a in fc["actors"]}
        if GD not in actors:
            raise ValueError(f"{file_base}: a mask check or sale in a flowchart with no GameDataActor")
        nodes, before, taken = {}, {}, set()
        for kind, e, item in found:
            if kind in ("query", "name_query"):
                before[e["name"]] = f"C{e['name']}"
            else:
                taken.add((e["name"], "next", None))

        def tgt(i):
            nm = tr._name(fc, i)
            return before.get(nm) or tr._at(nm)
        order = sp["order"]
        for kind, e, item in found:
            nm = e["name"]
            _k, yes = tr._case(e, YES)
            _k, no = tr._case(e, NO)
            if kind == "query":
                # owned when put aside too, nothing moves
                nodes[f"C{nm}"] = {"copy": nm, "cases": {YES: tgt(yes), NO: f"Q{nm}"}}
                nodes[f"Q{nm}"] = _q_flag(sp["flags"][item], tgt(yes), tgt(no))
            elif kind == "name_query":
                # the selected shelf item is a mask put aside, so it's owned
                nodes[f"C{nm}"] = {"copy": nm, "cases": {YES: tgt(yes), NO: f"N{nm}_0"}}
                for k, x in enumerate(order):
                    nodes[f"N{nm}_{k}"] = {"actor": GD, "query": "EventQueryIsGameDataString64",
                                           "params": {"GameDataName": SELECT_NAME, "Value": x, "Index": -1},
                                           "cases": {YES: f"F{nm}_{k}",
                                                     NO: f"N{nm}_{k + 1}" if k + 1 < len(order) else tgt(no)}}
                    nodes[f"F{nm}_{k}"] = _q_flag(sp["flags"][x], tgt(yes), tgt(no))
            else:  # a sale took the worn mask by name, so everything put aside comes back
                nodes[f"P{nm}"] = {"call": f":{UNSTASH}", "next": tgt(e["next"])}
                ops.append({"flowchart": fc["name"], "event": nm, "next": f"{HOOKS}_P{nm}"})
        if any(kind == "sale" for kind, _e, _i in found):
            if POUCH not in actors:
                raise ValueError(f"{file_base}: a mask sale in a flowchart with no PouchSystemActor")
            for entry, (gn, start) in store_graphs(sp).items():
                if entry not in eps and entry != ASIDE:  # a sale's file only puts masks back
                    for node in gn.values():
                        node["share"] = True
                    ops.append({"flowchart": fc["name"], "add_graph": entry, "nodes": gn, "start": start})
        for node in nodes.values():
            if node.get("params"):
                node["share"] = True
        ops.insert(0, {"flowchart": fc["name"], "add_graph": HOOKS, "nodes": nodes, "start": next(iter(nodes))})
        for nm, label in before.items():  # everything that led to a hooked check now leads to its hook
            for kind, where, k in tr.predecessors(fc, names[nm]):
                if (where, kind, k) in taken:
                    continue
                op = {"flowchart": fc["name"], "next": f"{HOOKS}_{label}"}
                if kind == "entry":
                    op["entry"] = where
                else:
                    op["event"] = where
                    if kind in ("case", "fork"):
                        op[kind] = k
                ops.append(op)
    return ops or None


# Read-back: the picker run on pouch states

class Machine:
    """Runs patched flowcharts' steps ({file: flowchart}) on a state. The state is the pouch (masks held), aside
    (masks whose flag is set), the scratch / switched / token flags, PlayerStatus.EquipHeadArmor and
    IsActiveHeadArmor, the head-armor equipment created and Navi's lines. Only what this adds is modelled, and any
    other step on the path is an error."""

    def __init__(self, flows, sp):
        self.flows, self.sp = flows, sp
        self.flag_item = {f: x for x, f in sp["flags"].items()}
        self.named = {sp["scratch"]: "scratch", sp["switched"]: "switched", sp["token"]: "token"}

    def run(self, file, entry, state, args=None, limit=5000):
        from evfl_build import is_case_end
        tr = _tr()
        fc = self.flows[file]
        ep = fc["entry_points"].get(entry)
        if ep is None:
            raise ValueError(f"{file} has no entry {entry}")
        i, steps = ep["main"], 0
        while i is not None and i < len(fc["events"]):
            steps += 1
            if steps > limit:
                raise ValueError(f"{file}:{entry}: no end after {limit} steps")
            e = fc["events"][i]
            actor, what = tr._what(fc, e)

            def p(key):
                return tr._param(e, key, args)
            if is_case_end(e):  # a case that ends goes through a do-nothing step (evfl_build.route_end_cases)
                break
            if e["type"] == "subflow":
                callee = (e.get("flowchart") or file, e.get("entry_point"))
                if callee == ("InitTalk", "InitTalk_NaviPlayerSide"):
                    state["init_talk"] = state.get("init_talk", 0) + 1
                elif callee[1].startswith(PREFIX) and callee[0] in self.flows:
                    self.run(callee[0], callee[1], state,
                             {k: p(k) for k in ((e.get("params") or {}).get("items") or {})})
                else:
                    raise ValueError(f"{file} {e['name']}: unexpected call {callee}")
                i = e["next"]
                continue
            if e["type"] == "switch":
                if (actor, what) == (POUCH, EXIST):
                    v = YES if p("Actor") in state["pouch"] else NO
                elif (actor, what) == (GD, "EventQueryIsGameDataBool"):
                    f = p("GameDataName")
                    v = YES if (state[self.named[f]] if f in self.named else
                                self.flag_item[f] in state["aside"]) else NO
                else:
                    raise ValueError(f"{file} {e['name']}: unexpected query {actor}.{what}")
                i = next((c["next"] for c in e["cases"] if c["value"] == v), None)
                continue
            if e["type"] == "action":
                if (actor, what) == (GD, "EventTriggerSetGameDataBool"):
                    f = p("GameDataName")
                    if f == EQUIP_ACTIVE:
                        state["active"] = bool(p("Value"))
                    elif f in self.named:
                        state[self.named[f]] = bool(p("Value"))
                    else:
                        (state["aside"].add if p("Value") else state["aside"].discard)(self.flag_item[f])
                elif (actor, what) == (GD, "EventTriggerSetGameDataString64"):
                    if p("GameDataName") != EQUIP_HEAD:
                        raise ValueError(f"{file} {e['name']}: sets {p('GameDataName')}")
                    state["head"] = p("Value")
                elif (actor, what) == (POUCH, TAKE):
                    x, num = p("Actor"), p("Num")
                    if num < 0 and x not in state["pouch"]:
                        state["errors"].append(f"{e['name']}: takes {x}, which isn't in the pouch")
                    if num > 0 and x in state["pouch"]:
                        state["errors"].append(f"{e['name']}: adds {x}, which is already in the pouch")
                    (state["pouch"].add if num > 0 else state["pouch"].discard)(x)
                    if num < 0 and state.get("equip") and state["equip"][0] == x:
                        state["equip"] = None  # a mask taken from the pouch comes off (like a sale's take does)
                elif (actor, what) == (PLAYER, CREATE):
                    state["equip"] = (p("EquipmentActorName"), bool(p("IsActive")))
                elif (actor, what) == (NAVI_ACTOR, "EventTalk"):
                    state["said"].append(p("MessageId"))
                elif (actor, what) == (NAVI_ACTOR, "EventDoNothing"):
                    state["nothing"] = state.get("nothing", 0) + 1
                else:
                    raise ValueError(f"{file} {e['name']}: unexpected action {actor}.{what}")
                i = e["next"]
                continue
            raise ValueError(f"{file} {e['name']}: unexpected {e['type']} step")
        return state


def new_state(pouch, aside=(), equip=None):
    return {"pouch": set(pouch), "aside": set(aside), "scratch": False, "switched": False, "token": False,
            "head": None, "active": False, "equip": equip, "said": [], "errors": []}


def button(sp, pouch):
    """The mask the button shows, which is the first of its list in the pouch."""
    return next((x for x in sp["order"] if x in pouch), None)


def press_navi(m, state, token=True):
    """Talk to Navi where she has nothing to say. The Sequence edit sets the token and the game plays NaviHint_Field."""
    state["token"] = token
    state["said"] = []
    m.run(NAVI, m.sp["navi"]["entry"], state)


def check_picker(m, sp, cases):
    """Runs the picker on each case (owned masks, masks put aside) twice as many times as there are owned masks, and
    checks that:
    - the owned set never changes
    - the button visits every owned mask in list order
    - each switch wears the button's new mask and has Navi say the line once
    - one owned mask (or none) is left alone
    - a request without the token changes nothing
    Returns (problems, runs)."""
    bad, runs = [], 0
    line = f"{TEXT_FILE.rsplit('.', 1)[0]}:{SWITCH_LABEL}"
    for owned, aside in cases:
        pouch = set(owned) - set(aside)
        where = f"owning {sorted(x.rsplit('_', 1)[1] for x in owned)} (aside " \
                f"{sorted(x.rsplit('_', 1)[1] for x in aside)})"
        state = new_state(pouch, aside)
        press_navi(m, state, token=False)  # a request that isn't the Navi button gets vanilla's do-nothing
        runs += 1
        if state["pouch"] != pouch or state["aside"] != set(aside) or state["said"] or state["equip"] or \
                state.get("nothing") != 1:
            bad.append(f"{where}: NaviHint_Field without the token changed something")
            continue
        seen = []
        for _ in range(2 * len(owned) + 2):
            before = (set(state["pouch"]), set(state["aside"]), state["equip"])
            press_navi(m, state)
            runs += 1
            now = button(sp, state["pouch"])
            if state["pouch"] | state["aside"] != set(owned) or state["pouch"] & state["aside"]:
                bad.append(f"{where}: owned masks changed to pouch {sorted(state['pouch'])} aside "
                           f"{sorted(state['aside'])}")
                break
            if state["token"] or state["switched"]:
                bad.append(f"{where}: the token or the switched flag is left set")
                break
            if len(owned) < 2:
                if (set(state["pouch"]), set(state["aside"]), state["equip"]) != before or state["said"]:
                    bad.append(f"{where}: a single owned mask (or none) was switched, worn or announced")
                break
            if state["said"] != [line] or state.get("init_talk", 0) < 1:
                bad.append(f"{where}: after the switch Navi says {state['said']}, not the switch line")
                break
            if state["equip"] != (now, True) or state["head"] != now or not state["active"]:
                bad.append(f"{where}: the switch wears {state['equip']} (head {state['head']}, active "
                           f"{state['active']}), the button shows {now}")
                break
            seen.append(now)
            if state["errors"]:
                bad += [f"{where}: {x}" for x in state["errors"]]
                break
        if len(owned) >= 2 and set(seen) != set(owned):
            bad.append(f"{where}: switching shows only {sorted(set(seen))}, not every owned mask")
    return bad, runs


def picker_cases(sp, rnd, n_random=300):
    """Pouch states for check_picker: none, every single mask and pair, all 8, random sets with random masks aside."""
    order = sp["order"]
    cases = [(set(), set())]
    for x in order:
        cases.append(({x}, set()))
    for i, x in enumerate(order):
        for y in order[i + 1:]:
            cases.append(({x, y}, set()))
    cases.append((set(order), set()))
    for _ in range(n_random):
        owned = {x for x in order if rnd.random() < 0.45}
        aside = {x for x in owned if rnd.random() < 0.4}
        if owned and not owned - aside:
            aside = set()
        cases.append((owned, aside))
    return cases


# The seed's mask uses, walked

# OoTR locations that need a mask worn, and the vanilla sales (the shop's quest, not an OoTR location)
USES = {"Deku Theater Skull Mask": "Armor_Child_Mask_Skull", "Deku Theater Mask of Truth": "Armor_Child_Mask_Truth"}
CHAIN = ("Armor_Child_Mask_Keaton", "Armor_Child_Mask_Skull", "Armor_Child_Mask_Spooky", "Armor_Child_Mask_Bunny")


def walk_masks(m, sp, spoiler, sale_files):
    """Walks the seed's mask uses in play order with the patched picker. Masks found are added the way their gets add
    them. At each Deku Theater mask check the needed mask gets switched onto the button (running the patched Navi
    scene and picker) and has to be the one worn. With masks left vanilla and complete_mask_quest off, the shop's
    chain is walked last: each rented mask switched on, then sold with the hooked sale, which takes it by name and
    brings everything put aside back. Returns (problems, notes). The walk models the button, not NPC presence
    (logic covers that)."""
    bad, notes, walked = [], [], []
    settings = spoiler.get("settings") or {}
    items = {k: v["pouch"] for k, v in sp["items"].items()}
    locs = {k: (v.get("item") if isinstance(v, dict) else v) for k, v in (spoiler.get("locations") or {}).items()}
    order = [list(sphere) for sphere in (spoiler.get(":playthrough") or {}).values()]
    rest = [k for k in locs if not any(k in s for s in order)]
    state = new_state(())
    shuffled = {items[x] for x in (settings.get("shuffle_child_trade") or []) if x in items}
    for x in (settings.get("starting_items") or {}):
        if x in items:
            state["pouch"].add(items[x])
    most = [len(state["pouch"])]

    def owned():
        return state["pouch"] | state["aside"]

    def switch_to(name, mask):
        if mask not in owned() and mask not in shuffled:
            state["pouch"].add(mask)  # a mask left vanilla: rented at the shop (which no longer takes the others)
        if mask not in owned():
            bad.append(f"{name}: {mask} isn't owned there")
            return False
        if m is None:  # no picker (a patch without the fix), so the button shows the first owned mask for good
            if button(sp, state["pouch"]) != mask:
                bad.append(f"{name}: {mask} is hidden behind {button(sp, state['pouch'])} on the button, owning "
                           f"{', '.join(x.rsplit('_', 1)[1] for x in sp['order'] if x in owned())}")
                return False
            walked.append(f"{name}: {mask.rsplit('_', 1)[1]} on the button with no picker")
            return True
        k, n = 0, len(owned())
        while not (state["equip"] == (mask, True) and button(sp, state["pouch"]) == mask):
            if k > 2 * n + 1:
                bad.append(f"{name}: {mask} never comes onto the button (owning {sorted(owned())})")
                return False
            press_navi(m, state)
            k += 1
        walked.append(f"{name}: {mask.rsplit('_', 1)[1]} worn after {k} switch{'' if k == 1 else 'es'}, owning "
                      f"{', '.join(x.rsplit('_', 1)[1] for x in sp['order'] if x in owned())}")
        return True

    def get(loc):
        x = items.get(locs.get(loc))
        if x and x not in owned():
            state["pouch"].add(x)
        most[0] = max(most[0], len(owned()))

    later = [loc for loc in rest if loc in USES]  # mask checks no sphere needs get visited once their mask is owned
    for names in order:  # a sphere's checks need only what earlier spheres gave
        for loc in names:
            if loc in USES:
                switch_to(loc, USES[loc])
            get(loc)
        for loc in [x for x in later if USES[x] in owned()]:
            later.remove(loc)
            switch_to(f"{loc} (not required)", USES[loc])
            get(loc)
    for loc in rest:  # everything else found, then what is left
        if loc not in USES:
            get(loc)
    for loc in later:
        switch_to(f"{loc} (not required)", USES[loc])
        get(loc)
    if not settings.get("complete_mask_quest"):
        for mask in CHAIN:
            if mask in shuffled:
                continue
            if mask not in owned():
                state["pouch"].add(mask)  # rented (the shop no longer takes the others back)
            if not switch_to(f"vanilla sale of the {mask.rsplit('_', 1)[1]}", mask):
                continue
            sale = sale_files.get(mask)
            if sale is None and m is not None:
                bad.append(f"no hooked sale of {mask}")
                continue
            before = owned() - {mask}
            state["pouch"].discard(mask)  # NpcCommon:SellMask's take, by name
            state["equip"] = None
            if m is not None:
                m.run(sale, UNSTASH, state)
            if state["aside"] or state["pouch"] != before:
                bad.append(f"sale of {mask}: after it the pouch holds {sorted(state['pouch'])}, aside "
                           f"{sorted(state['aside'])}")
    bad += state["errors"]
    notes.append(f"{len(walked)} mask uses walked, up to {most[0]} masks owned at once")
    notes += walked
    return bad, notes


# Read-back of a built patch

def _versions(root, name):
    import re as _re
    d = os.path.join(root, "Event", "EventFlow")
    return sorted(f for f in os.listdir(d) if _re.match(_re.escape(name) + r"(\.\d{3})?\.bfevfl\.zs$", f))


def verify(patch, plan, romfs, seed_dir=None, rnd_seed=0, section=None):
    """Reads the mask button's edits back from a built patch. Returns (problems, notes). With `section`, check these
    mask edits even if the plan has none, as a negative control on a patch built without them."""
    import random
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from romtools import Romfs, byml_load, murmur3_32
    from evfl import Evfl
    import ainb
    from evfl_build import is_case_end
    tr = _tr()
    section = section or (plan.get("trade_slot") or {}).get("masks")
    if not section:
        return [], []
    sp = plan_spec(section)
    d = data()
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad, notes = [], []
    parsed = {}

    def flows(base):
        if base not in parsed:
            parsed[base] = {}
            for f in _versions(romfs, base):
                try:
                    parsed[base][f] = next(x for x in Evfl(fs.read(f"Event/EventFlow/{f}")).flowcharts
                                           if x["name"] == base)
                except (StopIteration, ValueError):
                    pass
        return parsed[base]

    def newest(base):
        x = flows(base)
        return x[sorted(x, key=lambda f: (len(f.split(".")) > 3, f))[-1]] if x else None
    host, navi = newest(HOST), newest(NAVI)
    sale_files = {}
    for s in d["sales"]:
        fc = newest(s["file"])
        if fc is not None and UNSTASH in fc["entry_points"]:
            sale_files[s["mask"]] = s["file"]
    machine = None
    missing = [e for e in (PICK, UNSTASH, RESTORE, ASIDE, EQUIP) if host is None or e not in host["entry_points"]]
    if missing:
        bad.append(f"{HOST}: no {', '.join(missing)}")
    elif navi is None or NAVI_GRAPH not in navi["entry_points"] or \
            tr._name(navi, navi["entry_points"][sp["navi"]["entry"]]["main"]) != f"{NAVI_GRAPH}_t":
        bad.append(f"{NAVI}:{sp['navi']['entry']} doesn't start the mask picker ({NAVI_GRAPH})")
    else:
        # 1. the picker, run on pouch states
        flows_m = {HOST: host, NAVI: navi}
        flows_m.update({f: newest(f) for f in set(sale_files.values())})
        machine = Machine(flows_m, sp)
        cases = picker_cases(sp, random.Random(rnd_seed))
        try:
            problems, runs = check_picker(machine, sp, cases)
        except ValueError as ex:
            problems, runs = [f"the picker can't be run: {ex}"], 0
        bad += problems[:20]
        notes.append(f"picker run {runs} times on {len(cases)} pouch states (Navi scene + {HOST})")
    # 2. every mask check and sale hooked, in every version of every file the data names or the patch holds
    ev_dir = os.path.join(patch, "Event", "EventFlow")
    bases = set(files(sp))
    if os.path.isdir(ev_dir):
        bases |= {f.split(".")[0] for f in os.listdir(ev_dir) if f.endswith(".bfevfl.zs")}
    counts = {"query": 0, "name_query": 0, "sale": 0}
    masks = set(sp["order"])
    for base in sorted(bases):
        for f, fc in flows(base).items():
            by = {e["name"]: e for e in fc["events"]}
            for kind, e, item in sites(fc, masks, base):
                nm = e["name"]
                counts[kind] += 1
                c = by.get(f"{HOOKS}_C{nm}")
                _k, yes = tr._case(e, YES)
                _k, no = tr._case(e, NO)
                preds = [p[1] for p in tr.predecessors(fc, e)]

                def to(i):  # where a case goes: None for the end (directly, or through the do-nothing step)
                    return i if i is not None and i < len(fc["events"]) and not is_case_end(fc["events"][i]) else None
                if kind == "query":
                    q = by.get(f"{HOOKS}_Q{nm}")
                    ok = c is not None and q is not None and not preds and tr._what(fc, c) == (POUCH, EXIST) and \
                        tr._param(c, "Actor") == item and tr._case(c, NO)[1] == q["idx"] and \
                        to(tr._case(c, YES)[1]) == to(yes) and tr._what(fc, q) == (GD, "EventQueryIsGameDataBool") \
                        and tr._param(q, "GameDataName") == sp["flags"][item] and to(tr._case(q, YES)[1]) == to(yes) \
                        and to(tr._case(q, NO)[1]) == to(no)
                    if not ok:
                        bad.append(f"{f} {nm}: the check of {item} doesn't also count it put aside (reached by "
                                   f"{preds})")
                elif kind == "name_query":
                    ok = c is not None and not preds and tr._what(fc, c) == (POUCH, NAME_EXIST) and \
                        to(tr._case(c, YES)[1]) == to(yes)
                    got = set()
                    i = tr._case(c, NO)[1] if c is not None else None
                    while ok and i is not None and i < len(fc["events"]) and fc["events"][i]["name"].startswith(
                            f"{HOOKS}_N{nm}_"):
                        s_ = fc["events"][i]
                        fl = fc["events"][tr._case(s_, YES)[1]]
                        x = tr._param(s_, "Value")
                        ok = ok and tr._param(s_, "GameDataName") == SELECT_NAME and \
                            tr._param(fl, "GameDataName") == sp["flags"].get(x) and \
                            to(tr._case(fl, YES)[1]) == to(yes) and to(tr._case(fl, NO)[1]) == to(no)
                        got.add(x)
                        i = tr._case(s_, NO)[1]
                    if not ok or got != masks or to(i) != to(no):
                        bad.append(f"{f} {nm}: the shop's 'already have it' check doesn't count masks put aside")
                else:
                    p_ = by.get(f"{HOOKS}_P{nm}")
                    u = fc["entry_points"].get(UNSTASH)
                    restored = set()
                    if u is not None:
                        j = u["main"]
                        while j is not None and j < len(fc["events"]):
                            s_ = fc["events"][j]
                            if s_["type"] == "subflow" and s_.get("entry_point") == RESTORE and \
                                    tr._param(s_, "Flag") == sp["flags"].get(tr._param(s_, "Actor")):
                                restored.add(tr._param(s_, "Actor"))
                            j = s_["next"]
                    if p_ is None or e["next"] != p_["idx"] or (p_.get("flowchart") or "", p_.get("entry_point")) != \
                            ("", UNSTASH) or restored != masks or RESTORE not in fc["entry_points"]:
                        bad.append(f"{f} {nm}: the sale of {item} isn't followed by everything put aside coming back")
    notes.append(f"hooked: {counts['query']} mask checks, {counts['name_query']} shop name checks, {counts['sale']} "
                 f"sales (every version of {len(bases)} files)")
    if counts["sale"] < len(d["sales"]) or counts["query"] < d["site_counts"]["query"]:
        bad.append(f"fewer mask checks or sales than vanilla has ({counts} vs {d['site_counts']}, "
                   f"{len(d['sales'])} sales)")
    # 3. the Navi button: NaviHintEvent's no-hint end now sets the token and requests NaviHint_Field
    S = sp["sequence"]
    try:
        a = ainb.Ainb(fs.raw(SEQUENCE))
        n = a.nodes

        def kids(i):
            return {pl["name"]: pl["node"] for pl in n[i]["plugs"][ainb.PLUG_CHILD]}

        def inp(i, name):
            t, e = a._input(i, name)
            return e
        sel = kids(S["area_sel"]).get("False")
        sel_in = inp(sel, "Input")
        sim = kids(sel).get("True")
        sim_kids = [pl["node"] for pl in n[sim]["plugs"][ainb.PLUG_CHILD]]
        req = next(k for k in sim_kids if n[k]["name"] == "SeqOneShotRequestEvent")
        setb = next(k for k in sim_kids if n[k]["name"] == "SeqOneShotSetGameDataBool")
        st = inp(setb, "ParentStruct")["node"]
        struct, _, member = sp["token"].partition(".")
        ok = (n[sel]["type"] == 7 and n[sim]["type"] == 3 and sel_in["node"] == S["trig"] and
              n[S["trig"]]["outputs"]["bool"][sel_in["plug"]]["name"] == S["trig_out"] and
              kids(sel).get("False") == S["end"] and inp(req, "EventName")["value"] == sp["navi"]["entry"] and
              inp(req, "EventName")["node"] == -1 and inp(setb, "GameDataName")["value"] == member and
              inp(setb, "Value")["value"] is True and n[st]["name"] == "SeqQueryGetNonStructGameDataStruct" and
              inp(st, "GameDataFullName")["value"] == struct)
    except (StopIteration, KeyError, ainb.AinbError, IndexError, TypeError) as ex:
        ok = False
        notes.append(f"Navi button read-back: {ex!r}")
    if not ok:
        bad.append(f"{SEQUENCE}: the Navi button with no hint doesn't set the token and request "
                   f"{sp['navi']['entry']}")
    # 4. the Navi scene loads the picker's host (the scene-info list) and the switch line exists
    info = {r["__RowId"]: r for r in byml_load(fs.read("RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs"))[0]}
    subs = set((info.get(sp["navi"]["entry"]) or {}).get("SubFlowList") or [])
    if not {HOST, "InitTalk"} <= subs:
        bad.append(f"scene ID {sp['navi']['entry']}: its called-file list {sorted(subs)} lacks {HOST} or InitTalk")
    for s in d["sales"]:  # a sale scene's file holds its own store entries, so nothing new to load
        if s["mask"] not in sale_files:
            bad.append(f"{s['file']}: no {UNSTASH} for the sale of {s['mask']}")
    bad += [f"the switch line: {x}" for x in text_problems()]
    try:
        import msbt
        missing = []
        for lang in sorted(SWITCH_TEXT):
            arch = msbt.read_archive(fs, lang)
            mm = msbt.Msbt(arch[TEXT_FILE])
            if SWITCH_LABEL not in mm.labels or msbt.plain(mm.messages[mm.labels[SWITCH_LABEL]]) != SWITCH_TEXT[lang]:
                missing.append(lang)
        if missing:
            bad.append(f"{TEXT_FILE} {SWITCH_LABEL}: missing or different in {', '.join(missing)}")
    except (ImportError, KeyError, OSError, SystemExit) as ex:
        bad.append(f"the switch line can't be read back: {ex!r}")
    # 5. the stock expressions count masks put aside
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]["Data"]
    by_hash = {int(h): m for m, h in d["stock_hash"].items()}
    flag_hash = {murmur3_32(f.encode()): f for f in sp["flags"].values()}
    exps = {int(r["Hash"]): [[int(x) for x in v] for v in r.get("Values") or []] for r in gd["BoolExp"]}
    n_ok = 0
    for name, vals in d["stock_exps"].items():
        got = exps.get(murmur3_32(name.encode()))
        want = [[v[0]] + ([murmur3_32(v[1].encode()) if isinstance(v[1], str) else v[1]] if len(v) > 1 else [])
                for v in rewrite_exp(vals, by_hash, sp["flags"])]
        if got == want:
            n_ok += 1
            continue
        # a shuffled mask's shelf condition (parity/_songs_trade_child.py) reads no stock any more, that's fine
        if got is not None and not any(v[0] == 15 and v[1] in by_hash for v in got):
            n_ok += 1
            continue
        bad.append(f"expression {name}: reads a mask's stock without counting it put aside")
    notes.append(f"{n_ok} stock expressions count masks put aside ({len(flag_hash)} flags)")
    # 6. the seed's mask uses walked with the patched picker
    sp_path = os.path.join(seed_dir or os.path.dirname(os.path.abspath(patch)), "spoiler.json")
    if machine is not None and os.path.exists(sp_path):
        try:
            b, nn = walk_masks(machine, sp, json.load(open(sp_path, encoding="utf-8")), sale_files)
        except ValueError as ex:
            b, nn = [f"walk: {ex}"], []
        bad += b
        notes += nn
    elif os.path.exists(sp_path):  # no picker, so walk the game's own button to show what it blocks
        b, nn = walk_masks(None, sp, json.load(open(sp_path, encoding="utf-8")), sale_files)
        bad += [f"walk without a picker: {x}" for x in b] or ["the seed's mask uses can't be walked: no picker"]
        notes += nn
    return bad, notes


def main(argv):
    """python tools/mask_slot.py OUT_DIR [ROMFS] [--section-from PLAN]: the read-back alone. --section-from is the
    negative control, it checks OUT_DIR/patch against the masks section of another seed's plan."""
    import argparse
    import sys
    sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("romfs", nargs="?", default=__import__("romtools").longshot_romfs())
    ap.add_argument("--section-from")
    a = ap.parse_args(argv)
    plan = json.load(open(os.path.join(a.out, "plan.json"), encoding="utf-8"))
    section = None
    if a.section_from:
        section = (json.load(open(a.section_from, encoding="utf-8")).get("trade_slot") or {}).get("masks")
    b, n = verify(os.path.join(a.out, "patch"), plan, a.romfs, a.out, section=section)
    for x in n:
        print(f"  mask button: {x}")
    for x in b:
        print(f"PROBLEM mask button: {x}")
    print(f"{len(b)} problems")
    return 1 if b else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
