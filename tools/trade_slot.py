"""The trade button's picker and its owned record.

What the game does
This is in the files, and GyroMK, Clawshot and Goggles saw it in game. The 14 trade items share one menu button
(UI/Pouch/PouchTable Pa_ItemIcon_23) that shows the first owned item of its list for Link's age. An adult skips the
child items but a child sees the adult ones too, and every trade NPC only accepts the shown item
(GameParameter/ShowItemReplaceEventParam). Each item keeps its own pouch count so nothing is lost, but you can't
pick a hidden item. So the Claim Check (never taken), Zelda's Letter with the gate open, or any earlier item whose
NPC isn't there yet blocks everything after it.

What this adds
It's SoH's ShuffleTradeItems and OoT3DR's L/R picker, done with only event-flow edits and borrowed saved flags,
since that's what the remake's files can express.
- An owned record per item. Each one gets a borrowed saved flag (tools/rando/free_flags.py;
  data/rando/songs_trade_slot.json "flags_claimed") that's true while the item is owned but put aside. Owned means
  in the pouch, or put aside.
- The picker. Showing a trade item where it does nothing (ShowItem:EntryPoint0, "This doesn't seem useful
  here...") puts the button's item aside, so the button shows the next owned item of Link's age. Link holds that
  one up and it becomes the selected item. Past the last one, everything put aside comes back and the first is
  shown again. It only kicks in with two or more owned items Link's age can see. With one, nothing changes.
- Every check of a trade item (PouchSystemActor.EventQueryIsExistInPouch, in any flow, the randomizer's included)
  also counts one that's put aside, without moving anything, so talking to an NPC never changes the button. The two
  Biggoron arrival cutscenes (Dm_DeathMtTrail_0006/0007, no GameDataActor) only pick an animation from such a
  check, so we leave them alone (COSMETIC_QUERY_FILES).
- Every hand-in (AddOrRemovePouchContent <trade item> -1) puts that item back first and everything else back
  after, so nothing is lost and the button never stays empty while items are put aside.
- Biggoron's timed removal (PouchSystemActor.EventTriggerRemoveSwordBigGoronChallengeActor, which takes the
  button's first item with no age filter) runs with only the timed items in the pouch, then everything comes back.
- Biggoron takes the Claim Check when he hands over his reward. In vanilla it's never taken and just stays on the
  button.
- After a switch a line says what happened and how to switch again (EventFlowMsg/Item_Event RTS_Switch, 16
  languages, SWITCH_TEXT).

Only seeds where Link can own two trade items of one age at once get the picker (needs_picker, from the settings).
Everywhere else the button already shows the one item Link needs, since songs_trade.TRADE_ORDER puts the child items
first. Those seeds get just one fix. Biggoron's timed removal takes the button's first item with no age filter, and
with TRADE_ORDER's child-first order (the U4 change from the other-randos study) that's Zelda's Letter when an adult
still holds it next to a timed item. Then the gate never opens for the child again, which is the unbeatable class.
So in those seeds each of the 6 removals becomes "remove the held timed item by name" (Odd Mushroom, Eyeball Frog,
Eyedrops), in SubEvent_GetSwordBigGoron and LinkSleepInBed only. Only one of those is ever held on a vanilla chain,
and with none held nothing is removed. Reordering TRADE_ORDER later can't break this, because no removal looks at
the list any more.

The shared steps live in ShowItem (resident) and are kept small. There's one put-back and one put-aside entry that
take the item and its flag as arguments (RTS_R, RTS_A), "everything back" (RTS_U), "timed items first" (RTS_T) and
the picker (RTS_S). make_patch applies the hooks after every other edit, on each event file as already patched, one
site at a time (stage2_next), so they land on the steps the way the other plugins left them. The read-back (verify)
re-reads the built files and runs the picker's own steps over pouch states with an interpreter of the patched
ShowItem flow, then walks the seed's trades with it.
"""
import functools
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(HERE, "data", "rando", "songs_trade_slot.json")
SHOWITEM = "ShowItem"
PREFIX = "RTS_"  # every entry and step this adds
SWITCH, UNSTASH, TIMED_FIRST, RESTORE, ASIDE, HOOKS = "RTS_S", "RTS_U", "RTS_T", "RTS_R", "RTS_A", "RTS_H"
SCRATCH = "picker_scratch"  # flags_claimed key of the picker's own scratch flag (others put aside before it ran)
YES, NO = 0, 1  # query answers (tools/progressive.py)
POUCH, GD, PLAYER = "PouchSystemActor", "GameDataActor", "Player_Event"
EXIST, TAKE, TIMED_TAKE = "EventQueryIsExistInPouch", "EventTriggerAddOrRemovePouchContent", \
    "EventTriggerRemoveSwordBigGoronChallengeActor"
SELECTED = {"child": "PlayerStatus.AssignableItem.Child", "adult": "PlayerStatus.AssignableItem.Adult"}
COSMETIC_QUERY_FILES = ("Dm_DeathMtTrail_0006", "Dm_DeathMtTrail_0007")  # Biggoron's arrival: an animation choice
TEXT_FILE, SWITCH_LABEL = "EventFlowMsg/Item_Event.msbt", "RTS_Switch"
# the line after a switch, in each language's own style for Talk_03 ("This doesn't seem useful here...")
SWITCH_TEXT = {
    "USen": "You switched to your next trade item.\nTo switch again, show it where it's no use.",
    "EUen": "You switched to your next trade item.\nTo switch again, show it where it's no use.",
    "EUde": "Du nimmst den nächsten Tauschgegenstand.\nZeig ihn, wo er nichts nützt, um zu wechseln.",
    "EUfr": "Vous prenez votre objet d'échange suivant.\nMontrez-le là où il est inutile pour changer.",
    "USfr": "Vous prenez votre objet d'échange suivant.\nMontrez-le là où il est inutile pour changer.",
    "EUes": "Sacas tu siguiente objeto de intercambio.\nMuéstralo donde no sirva para cambiar.",
    "USes": "Sacas tu siguiente objeto de intercambio.\nMuéstralo donde no sirva para cambiar.",
    "EUit": "Hai preso il prossimo oggetto di scambio.\nMostralo dove non serve per cambiarlo ancora.",
    "EUnl": "Je pakt je volgende ruilvoorwerp.\nToon het waar het niets doet om te wisselen.",
    "EUpl": "Wyjmujesz kolejny przedmiot do wymiany.\nPokaż go tam, gdzie się nie przyda, by zmienić.",
    "EUru": "Вы взяли следующий предмет для обмена.\nЧтобы сменить, покажите его там,\nгде он не нужен.",
    "USpt": "Você pegou o próximo item de troca.\nMostre-o onde não for útil para trocar de novo.",
    "JPja": "次の交換アイテムに 持ちかえた\nダメな場所で 出すと また持ちかえられる",
    "KRko": "다음 교환 아이템으로 바꿨다\n소용없는 곳에서 꺼내면 다시 바꿀 수 있다",
    "CNzh": "换成了下一个交换道具。\n在没有用的地方拿出来，就能再次更换。",
    "TWzh": "換成了下一個交換道具。\n在沒有作用的地方拿出來，就能再次更換。",
}


def needs_picker(settings):
    """Whether Link can own two trade items of one age at once (OoTR's pools, ItemPool.py).
    That's two adult items with adult_trade_shuffle (the Pocket Cucco drops out when the Pocket Egg is shuffled too),
    or a shuffled Zelda's Letter next to the egg or Chicken. Otherwise each age holds one at a time. That's how the
    vanilla chains work, a shuffled egg or Chicken alone comes before the Letter (which needs Talon awake), and
    skip_child_zelda starts with only the Letter. A child's adult items come after the child ones (TRADE_ORDER), so
    the button already shows what Link needs."""
    get = (lambda k: settings.get(k)) if isinstance(settings, dict) else (lambda k: getattr(settings, k, None))
    adult = set(get("adult_trade_start") or []) if get("adult_trade_shuffle") else set()
    if {"Pocket Egg", "Pocket Cucco"} <= adult:
        adult.discard("Pocket Cucco")
    return len(adult) >= 2 or "Zeldas Letter" in set(get("shuffle_child_trade") or [])


def text_problems():
    """Checks that each language's switch line fits the message box and every character is drawable. Width and lines
    use the Archipelago text's measures, from the game's fonts."""
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


def text_ops():
    """make_patch "text" ops: the switch line, in every language."""
    return [{"lang": lang, "file": TEXT_FILE, "label": SWITCH_LABEL, "text": text, "add": True,
             "note": "trade button: the line after a switch (tools/trade_slot.py)"}
            for lang, text in sorted(SWITCH_TEXT.items())]


@functools.lru_cache(maxsize=None)
def data():
    return json.load(open(DATA_PATH, encoding="utf-8"))


def plan_section(order, picker):
    """What songs_trade writes in the plan: the button's order and whether this seed gets the picker."""
    return {"order": list(order), "picker": bool(picker)}


def spec(order, picker=True):
    """The plan's "trade_slot" section made whole. That's the button's list order (songs_trade.TRADE_ORDER), the mode
    (picker, or just the named timed removals) and this data."""
    d = data()
    order = list(order)
    if sorted(order) != sorted(d["enum"]):
        raise ValueError(f"trade_slot: the order {order} isn't the 14 trade items {sorted(d['enum'])}")
    flags = {k: v for k, v in d["flags_claimed"].items() if k != SCRATCH}
    return {"order": order, "flags": flags, "scratch": d["flags_claimed"][SCRATCH], "enum": d["enum"],
            "enum_name": d["enum_name"], "child": d["child"], "timed": d["timed"],
            "showitem_hook": d["showitem"]["hook"], "showitem_talk": d["showitem"]["talk"], "claim": d["claim_check"],
            "picker": bool(picker)}


def plan_spec(section):
    """spec() from a plan's "trade_slot" section. Plans from before the mode existed had the picker. A "masks" part
    (seeds where Link can own several masks) is the mask button's picker (tools/mask_slot.py), hooked by the same
    stage (stage2_next)."""
    sp = spec(section["order"], section.get("picker", True))
    if section.get("masks"):
        import mask_slot
        sp["masks"] = mask_slot.plan_spec(section["masks"])
    return sp


def files(sp):
    """The event files make_patch opens for this mode (and the mask button's, tools/mask_slot.py)."""
    out = data()["files"] if sp["picker"] else data()["timed_files"]
    if sp.get("masks"):
        import mask_slot
        out = sorted(set(out) | set(mask_slot.files(sp["masks"])))
    return out


def claimed_flags():
    """Every saved flag this holds (tools/rando/free_flags.py hold)."""
    return sorted(data()["flags_claimed"].values())


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


def _is_child(yes, no):
    return {"actor": PLAYER, "query": "EventQueryPlayerIsChild", "cases": {YES: yes, NO: no}}


def _call(entry, sp, item, nxt, file=SHOWITEM):
    """A call of the put-back / put-aside entry for one item (its flag passed along)."""
    return {"call": f"{file}:{entry}", "params": {"Actor": item, "Flag": sp["flags"][item]}, "next": nxt}


def _child_prefix(sp):
    order, child = sp["order"], set(sp["child"])
    a0 = sum(1 for x in order if x in child)
    if set(order[:a0]) != child:
        raise ValueError(f"trade_slot: the child items {sorted(child)} aren't first in the button's order {order} "
                         f"(the picker's adult scan starts after them)")
    return a0


def showitem_graphs(sp):
    """{entry: (nodes, start)} added to ShowItem: put back / put aside one item ({Actor, Flag} arguments), everything
    back, the timed items first, and the picker."""
    order = sp["order"]
    n_items, a0 = len(order), _child_prefix(sp)
    arg_a, arg_f = {"arg": "Actor"}, {"arg": "Flag"}
    out = {RESTORE: ({"q": _q_flag(arg_f, "a", None), "a": _pouch(arg_a, 1, "c"), "c": _set_flag(arg_f, False, None)},
                     "q"),
           ASIDE: ({"q": _q_pouch(arg_a, "f", None), "f": _set_flag(arg_f, True, "r"), "r": _pouch(arg_a, -1, None)},
                   "q")}
    out[UNSTASH] = ({f"r{i}": dict(_call(RESTORE, sp, x, f"r{i + 1}" if i + 1 < n_items else None),
                                   call=f":{RESTORE}") for i, x in enumerate(order)}, "r0")
    others = [x for x in order if x not in sp["timed"]]
    n = {"u": {"call": f":{UNSTASH}", "next": "a0"}}
    for k, x in enumerate(others):
        n[f"a{k}"] = dict(_call(ASIDE, sp, x, f"a{k + 1}" if k + 1 < len(others) else None), call=f":{ASIDE}")
    out[TIMED_FIRST] = (n, "u")

    def nx(label, i, end):
        return f"{label}{i}" if i < n_items else end
    S = sp["scratch"]
    n = {"g": _is_child("f0", f"f{a0}"), "s1": _set_flag(S, True, "go"), "s0": _set_flag(S, False, "go"),
         "go": _is_child("cc0", f"cc{a0}"), "w": _q_flag(S, "u", "u1"), "u": {"call": f":{UNSTASH}", "next": "sh"},
         "u1": {"call": f":{UNSTASH}", "next": None}, "sh": _is_child("v0", f"v{a0}"),
         "m": {"copy": sp["showitem_talk"], "params_over": {"MessageId": f"{TEXT_FILE.rsplit('.', 1)[0]}:{SWITCH_LABEL}"},
               "next": "z"},  # the switch line, said the way EntryPoint0 says its own (Event4, SystemTextNPC.EventTalk)
         "z": {"call": "NpcCommon:ShowItem_Close", "next": None}}
    for i, x in enumerate(order):
        n[f"f{i}"] = _q_flag(sp["flags"][x], "s1", nx("f", i + 1, "s0"))      # anything of the age put aside?
        n[f"cc{i}"] = _q_pouch(x, f"st{i}", nx("cc", i + 1, None))          # the button's item ...
        n[f"st{i}"] = dict(_call(ASIDE, sp, x, nx("an", i + 1, "w")), call=f":{ASIDE}")  # ... is put aside
        n[f"an{i}"] = _q_pouch(x, "sh", nx("an", i + 1, "w"))               # another after it in the pouch?
        n[f"v{i}"] = _q_pouch(x, f"x{i}", nx("v", i + 1, None))             # the button's new item:
        n[f"x{i}"] = {"actor": PLAYER, "action": "EventPlayerSetSelectedItem",
                      "params": {"Item": sp["enum"][x], "IsWaitEnd": True}, "next": f"y{i}"}  # selected
        n[f"y{i}"] = {"call": ":ShowItemSuccess", "params": {"AssignableItem": sp["enum"][x]}, "next": "m"}  # held up
    out[SWITCH] = (n, "g")
    for nodes, _start in out.values():  # identical parameter blocks shared (tools/evfl_build.py "share")
        for node in nodes.values():
            if node.get("params") and "copy" not in node:
                node["share"] = True
    return out


# Sites in a (patched) flowchart

def _param(e, key, args=None):
    v = ((e.get("params") or {}).get("items") or {}).get(key)
    if not isinstance(v, dict):
        return None
    if v.get("type") == "argument":
        return (args or {}).get(v.get("value"))
    return v.get("value") if v.get("type") in ("string", "int", "bool", "float") else None


def _what(fc, e):
    if e["type"] not in ("action", "switch"):
        return None, None
    a = fc["actors"][e["actor"]]
    names = a["actions"] if e["type"] == "action" else a["queries"]
    k = e["action"] if e["type"] == "action" else e["query"]
    return a["name"], (names[k] if k < len(names) else None)


def sites(fc, trade, file_base):
    """[(kind, event, item)] in one flowchart. Steps this added are skipped.
    - "query" is IsExistInPouch of a trade item with Num 1, but not in ShowItem, whose own checks only place the item
      in Link's hand
    - "take" is AddOrRemovePouchContent of a trade item with Num < 0
    - "timed" is Biggoron's removal of the button's first item"""
    out = []
    for e in fc["events"]:
        if e["name"].startswith(PREFIX):
            continue
        actor, what = _what(fc, e)
        if actor != POUCH:
            continue
        item = _param(e, "Actor")
        if what == EXIST and e["type"] == "switch" and item in trade and _param(e, "Num") == 1 and \
                file_base != SHOWITEM:
            out.append(("query", e, item))
        elif what == TAKE and item in trade and isinstance(_param(e, "Num"), int) and _param(e, "Num") < 0:
            out.append(("take", e, item))
        elif what == TIMED_TAKE:
            out.append(("timed", e, None))
    return out


def _name(fc, i):
    return fc["events"][i]["name"] if i is not None and i < len(fc["events"]) else None


def _at(name):
    return f"@{name}" if name else None


def _case(e, value):
    return next(((k, c["next"]) for k, c in enumerate(e.get("cases", [])) if c["value"] == value), (None, None))


def _successors(fc, e):
    out = []
    if "next" in e and e["type"] != "type6":
        out.append(e["next"])
    if "join" in e:
        out.append(e["join"])
    out += [c["next"] for c in e.get("cases", [])] + list(e.get("forks", []))
    return [i for i in out if i < len(fc["events"])]


def reaches_take(fc, start, item, load_fc=None, file_base=None, _memo=None, hand=None):
    """Whether a take of `item` can follow event index `start` in `fc`.
    Same-file sub-flow calls are followed. A call into another file is followed through load_fc(name) -> flowchart, or
    counted as taking when it can't be read. With hand(scene name) -> (file, entry) we follow scene hand-offs
    (EventTransition) too."""
    memo = _memo if _memo is not None else {}
    seen, stack = set(), [start]
    while stack:
        i = stack.pop()
        if i is None or i in seen or i >= len(fc["events"]):
            continue
        seen.add(i)
        e = fc["events"][i]
        actor, what = _what(fc, e)
        if actor == POUCH and (what == TIMED_TAKE or (what == TAKE and _param(e, "Actor") == item and
                                                      (_param(e, "Num") or 0) < 0)):
            return True
        target = None
        if e["type"] in ("subflow", "subflow_switch"):
            target = (e.get("flowchart"), e.get("entry_point"))
        elif hand is not None and what == "EventTransition" and _param(e, "EventName"):
            target = hand(_param(e, "EventName"))
        if target is not None:
            other, entry = target
            if not other or other == fc["name"]:
                ep = fc["entry_points"].get(entry)
                if ep:
                    stack.append(ep["main"])
            elif other != SHOWITEM or not (entry or "").startswith(PREFIX):
                key = (other, entry, item)
                if key not in memo:
                    memo[key] = True  # Treat a recursive call as taking until proven otherwise.
                    ofc = load_fc(other) if load_fc else None
                    eps = (ofc or {}).get("entry_points") or {}
                    ep = eps.get(entry) if entry else next(iter(eps.values()), None)  # a scene row with no entry
                    memo[key] = True if ep is None else reaches_take(ofc, ep["main"], item, load_fc, other, memo,
                                                                     hand)
                if memo[key]:
                    return True
        stack += _successors(fc, e)
    return False


def predecessors(fc, event):
    """[(kind, step or entry name, index)] of everything leading to `event` (tools/progressive.py predecessors)."""
    i, out = event["idx"], []
    for e in fc["events"]:
        if "next" in e and e["type"] != "type6" and e["next"] == i:
            out.append(("next", e["name"], None))
        for k, c in enumerate(e.get("cases", [])):
            if c["next"] == i:
                out.append(("case", e["name"], k))
        for k, f in enumerate(e.get("forks", [])):
            if f == i:
                out.append(("fork", e["name"], k))
    for name, ep in fc["entry_points"].items():
        if ep["main"] == i:
            out.append(("entry", name, None))
    return out


def hook_name(kind, event_name):
    """The name of a hook step this adds in a scene file. "Q" is the check's put-aside test, "B" the put-back (or timed
    items first) before a step, "P" everything back after a hand-in, and "C" + r/t/u the Claim Check's hand-in."""
    return f"{HOOKS}_{kind}{event_name}"


def stage2_next(ev, file_base, sp, load_fc=None):
    """Event ops for one event file as already patched (an evfl.Evfl), or None when it's done.
    First come the trade button's (_trade_next), then once those are in, the mask button's (tools/mask_slot.py
    stage2_next, seeds with a "masks" part). That way the mask hooks land on the file the way the trade hooks left
    it."""
    ops = _trade_next(ev, file_base, sp, load_fc)
    if ops or not sp.get("masks"):
        return ops
    import mask_slot
    try:
        return mask_slot.stage2_next(ev, file_base, sp["masks"])
    except ValueError as e:
        raise ValueError(f"mask button: {e}")


def _trade_next(ev, file_base, sp, load_fc=None):
    """Event ops for one event file as already patched (an evfl.Evfl), or None when it's done.
    That's the ShowItem entries and the picker's hook, or every trade check, hand-in and timed removal of the file
    (and the Claim Check's hand-in) hooked at once, in one graph per flowchart (HOOKS), so the file only gets rebuilt
    once. A hook whose next step is itself hooked goes to that step's hook. A step whose routing a hook takes over (a
    check's "no" branch, a hand-in's next step) doesn't get rerouted again."""
    trade = set(sp["order"])
    ops = []
    if not sp["picker"]:
        return _timed_by_name(ev, sp)
    for fc in ev.flowcharts:
        names = {e["name"]: e for e in fc["events"]}
        eps = fc["entry_points"]
        actors = {a["name"] for a in fc["actors"]}
        if file_base == SHOWITEM and fc["name"] == SHOWITEM:
            if SWITCH in eps:
                continue
            ops += [{"flowchart": fc["name"], "add_graph": entry, "nodes": nodes, "start": start}
                    for entry, (nodes, start) in showitem_graphs(sp).items()]
            hook = names.get(sp["showitem_hook"])
            if hook is None:
                raise ValueError(f"{file_base}: no {sp['showitem_hook']} to hook the picker on")
            ops.append({"flowchart": fc["name"], "event": hook["name"], "next": f"{SWITCH}_g"})
            continue
        if HOOKS in eps:
            continue
        found = [x for x in sites(fc, trade, file_base) if x[0] != "query" or file_base not in COSMETIC_QUERY_FILES]
        cl = sp["claim"]
        claim = names.get(cl["before"]) if file_base == cl["file"] and fc["name"] == cl["file"] else None
        if file_base == cl["file"] and fc["name"] == cl["file"] and (claim is None or POUCH not in actors):
            raise ValueError(f"{file_base}: no {cl['before']} (or no {POUCH}) for the Claim Check's hand-in")
        if not found and claim is None:
            continue
        nodes, before, taken = {}, {}, set()  # before: step name -> label of the hook in front of it
        for kind, e, item in found:
            if kind == "query":
                # Send the caller to a copy of the check that reads the item's saved flag on "no".
                # Some originals have no "no" branch, like carpenter Talk Event179 and Eyedrops Event113.
                if GD not in actors:
                    raise ValueError(f"{file_base} {e['name']}: a check of {item} in a flowchart with no "
                                     f"GameDataActor: it can't also count the item put aside")
                before[e["name"]] = f"C{e['name']}"
            else:
                before[e["name"]] = f"B{e['name']}"
                taken.add((e["name"], "next", None))
        if claim is not None:
            before[claim["name"]] = "Cr"

        def tgt(i):
            nm = _name(fc, i)
            return before.get(nm) or _at(nm)
        for kind, e, item in found:
            nm = e["name"]
            if kind == "query":
                _k, no = _case(e, NO)
                _k, yes = _case(e, YES)
                # Count a set-aside item as owned. The hand-in restores it later if needed.
                nodes[f"C{nm}"] = {"copy": nm, "cases": {YES: tgt(yes), NO: f"Q{nm}"}}
                nodes[f"Q{nm}"] = _q_flag(sp["flags"][item], tgt(yes), tgt(no))
                continue
            if kind == "timed":
                nodes[f"B{nm}"] = {"call": f"{SHOWITEM}:{TIMED_FIRST}", "next": _at(nm)}
            else:
                nodes[f"B{nm}"] = _call(RESTORE, sp, item, _at(nm))
            nodes[f"P{nm}"] = {"call": f"{SHOWITEM}:{UNSTASH}", "next": tgt(e["next"])}
            ops.append({"flowchart": fc["name"], "event": nm, "next": hook_name("P", nm)})
        if claim is not None:
            nodes["Cr"] = _call(RESTORE, sp, cl["item"], "Ct")
            nodes["Ct"] = _pouch(cl["item"], -1, "Cu")
            nodes["Cu"] = {"call": f"{SHOWITEM}:{UNSTASH}", "next": _at(claim["name"])}
        for node in nodes.values():
            if node.get("params"):
                node["share"] = True
        ops.insert(0, {"flowchart": fc["name"], "add_graph": HOOKS, "nodes": nodes, "start": next(iter(nodes))})
        for nm, label in before.items():  # everything that led to a hooked step now leads to its hook
            for kind, where, k in predecessors(fc, names[nm]):
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


def _timed_by_name(ev, sp):
    """For seeds without the picker. Everything that led to a timed removal now removes the held timed item by name and
    goes on where the removal went, so the removal step itself is never reached."""
    ops = []
    for fc in ev.flowcharts:
        if HOOKS in fc["entry_points"]:
            continue
        found = [e for kind, e, _i in sites(fc, set(sp["order"]), fc["name"]) if kind == "timed"]
        if not found:
            continue
        nodes = {}
        for e in found:
            nm, after = e["name"], _at(_name(fc, e["next"]))
            for k, item in enumerate(sp["timed"]):
                nxt = f"N{nm}_{k + 1}" if k + 1 < len(sp["timed"]) else after
                nodes[f"N{nm}_{k}"] = _q_pouch(item, f"N{nm}_{k}r", nxt)
                nodes[f"N{nm}_{k}r"] = _pouch(item, -1, after)
        for node in nodes.values():
            node["share"] = True
        ops.append({"flowchart": fc["name"], "add_graph": HOOKS, "nodes": nodes, "start": next(iter(nodes))})
        for e in found:
            for kind, where, k in predecessors(fc, e):
                op = {"flowchart": fc["name"], "next": f"{HOOKS}_N{e['name']}_0"}
                if kind == "entry":
                    op["entry"] = where
                else:
                    op["event"] = where
                    if kind in ("case", "fork"):
                        op[kind] = k
                ops.append(op)
    return ops or None


def check_timed(fc, sp):
    """Problems, if any. That's a timed removal that's still reached anywhere but right after the picker's timed-first
    step, or a named removal that could take anything but a timed item."""
    out = []
    by = {e["name"]: e for e in fc["events"]}
    for kind, e, _i in sites(fc, set(sp["order"]), fc["name"]):
        if kind != "timed":
            continue
        preds = [p[1] for p in predecessors(fc, e)]
        before = by.get(hook_name("B", e["name"]))
        if preds and not (sp["picker"] and preds == [hook_name("B", e["name"])] and before is not None and
                          (before.get("flowchart"), before.get("entry_point")) == (SHOWITEM, TIMED_FIRST)):
            out.append(f"{e['name']}: Biggoron's removal of the button's first item is still reached from {preds}")
    for e in fc["events"]:
        if e["name"].startswith(f"{HOOKS}_N") and _what(fc, e) == (POUCH, TAKE) and _param(e, "Actor") not in sp["timed"]:
            out.append(f"{e['name']}: the named timed removal takes {_param(e, 'Actor')}")
    return out


# Read-back: the picker run on pouch states

class Machine:
    """Runs the patched ShowItem flowchart's own steps on a state: pouch (set of items held), aside (set of items
    whose flag is set), scratch, age, selected item, shown items. Only what this adds is modelled, and any other step on
    the path is an error."""

    def __init__(self, fc, sp):
        self.fc, self.sp = fc, sp
        self.flag_item = {f: x for x, f in sp["flags"].items()}
        self.enum_item = {v: x for x, v in sp["enum"].items()}

    def run(self, entry, state, args=None, limit=5000):
        from evfl_build import is_case_end
        fc = self.fc
        ep = fc["entry_points"].get(entry)
        if ep is None:
            raise ValueError(f"ShowItem has no entry {entry}")
        i, steps = ep["main"], 0
        while i is not None and i < len(fc["events"]):
            steps += 1
            if steps > limit:
                raise ValueError(f"{entry}: no end after {limit} steps")
            e = fc["events"][i]
            if is_case_end(e):  # a case's end goes through a do-nothing step (evfl_build.route_end_cases)
                break
            actor, what = _what(fc, e)

            def p(key):
                return _param(e, key, args)
            if e["type"] == "subflow":
                callee = (e.get("flowchart") or SHOWITEM, e.get("entry_point"))
                if callee == (SHOWITEM, "ShowItemSuccess"):
                    state["shown"].append(self.enum_item.get(p("AssignableItem")))
                elif callee[0] == SHOWITEM and callee[1].startswith(PREFIX):
                    self.run(callee[1], state, {k: p(k) for k in ((e.get("params") or {}).get("items") or {})})
                elif callee != ("NpcCommon", "ShowItem_Close"):
                    raise ValueError(f"{e['name']}: unexpected call {callee}")
                i = e["next"]
                continue
            if e["type"] == "switch":
                if (actor, what) == (PLAYER, "EventQueryPlayerIsChild"):
                    v = YES if state["age"] == "child" else NO
                elif (actor, what) == (POUCH, EXIST):
                    v = YES if p("Actor") in state["pouch"] else NO
                elif (actor, what) == (GD, "EventQueryIsGameDataBool"):
                    f = p("GameDataName")
                    v = YES if (state["scratch"] if f == self.sp["scratch"] else
                                self.flag_item[f] in state["aside"]) else NO
                else:
                    raise ValueError(f"{e['name']}: unexpected query {actor}.{what}")
                i = next((c["next"] for c in e["cases"] if c["value"] == v), None)
                continue
            if e["type"] == "action":
                if (actor, what) == (GD, "EventTriggerSetGameDataBool"):
                    f = p("GameDataName")
                    if f == self.sp["scratch"]:
                        state["scratch"] = bool(p("Value"))
                    else:
                        (state["aside"].add if p("Value") else state["aside"].discard)(self.flag_item[f])
                elif (actor, what) == (POUCH, TAKE):
                    x, num = p("Actor"), p("Num")
                    if num < 0 and x not in state["pouch"]:
                        state["errors"].append(f"{e['name']}: takes {x}, which isn't in the pouch")
                    (state["pouch"].add if num > 0 else state["pouch"].discard)(x)
                elif (actor, what) == (PLAYER, "EventPlayerSetSelectedItem"):
                    state["selected"] = self.enum_item.get(p("Item"))
                elif (actor, what) == ("SystemTextNPC", "EventTalk"):
                    state.setdefault("said", []).append(p("MessageId"))
                else:
                    raise ValueError(f"{e['name']}: unexpected action {actor}.{what}")
                i = e["next"]
                continue
            raise ValueError(f"{e['name']}: unexpected {e['type']} step")
        return state


def new_state(age, pouch, aside=()):
    return {"age": age, "pouch": set(pouch), "aside": set(aside), "scratch": False, "shown": [], "errors": [],
            "selected": None}


def button(sp, pouch, age):
    """The item the button shows: the first in the pouch, in list order, that the age can see."""
    child = set(sp["child"])
    return next((x for x in sp["order"] if x in pouch and (age == "child" or x not in child)), None)


def visible(sp, age):
    return [x for x in sp["order"] if age == "child" or x not in set(sp["child"])]


def check_picker(fc, sp, cases):
    """Runs the picker on each case (age, owned items, items put aside), twice as many times as the age sees owned
    items. It checks that the owned set never changes, the button visits every owned item of the age in list order, each
    step shows and selects the button's new item, and a single owned item is left alone. Returns (problems, steps
    run)."""
    m, bad, runs = Machine(fc, sp), [], 0
    for age, owned, aside in cases:
        vis = [x for x in visible(sp, age) if x in owned]
        pouch = set(owned) - set(aside)
        if not any(x in pouch for x in visible(sp, age)):
            continue  # nothing on the button: nothing to show
        state = new_state(age, pouch, aside)
        state["selected"] = button(sp, pouch, age)
        seen = [state["selected"]]
        for _ in range(2 * len(vis) + 2):
            before = state["selected"]
            state["shown"] = []
            m.run(SWITCH, state)
            runs += 1
            now = button(sp, state["pouch"], age)
            where = f"{age} owning {sorted(owned)} (aside {sorted(aside)})"
            if state["pouch"] | state["aside"] != set(owned) or state["pouch"] & state["aside"]:
                bad.append(f"{where}: owned items changed to pouch {sorted(state['pouch'])} aside "
                           f"{sorted(state['aside'])}")
                break
            if len(vis) < 2:
                if state["shown"] or now != before or state.get("said"):
                    bad.append(f"{where}: a single owned item was switched or shown again")
                break
            said = state.pop("said", [])
            if said != [f"{TEXT_FILE.rsplit('.', 1)[0]}:{SWITCH_LABEL}"]:
                bad.append(f"{where}: after the switch the game says {said}, not the switch line")
                break
            if state["shown"] != [now] or state["selected"] != now:
                bad.append(f"{where}: the switch showed {state['shown']}, selected {state['selected']}, the button "
                           f"shows {now}")
                break
            seen.append(now)
            if state["errors"]:
                bad += [f"{where}: {x}" for x in state["errors"]]
                break
        if len(vis) >= 2 and set(seen) != set(vis):
            bad.append(f"{age} owning {sorted(owned)} (aside {sorted(aside)}): switching shows only "
                       f"{sorted(set(seen) - {None})}, not every owned item {vis}")
    return bad, runs


def picker_cases(sp, rnd, n_random=300):
    """Pouch states for check_picker: every single item and pair, all 14, and random sets with random items aside."""
    order = sp["order"]
    cases = []
    for age in ("child", "adult"):
        vis = visible(sp, age)
        for x in order:
            cases.append((age, {x}, set()))
        for i, x in enumerate(order):
            for y in order[i + 1:]:
                cases.append((age, {x, y}, set()))
        cases.append((age, set(order), set()))
        for _ in range(n_random):
            owned = {x for x in order if rnd.random() < 0.4}
            aside = {x for x in owned if rnd.random() < 0.4}
            if not any(x in owned - aside for x in vis):
                aside = set()
            cases.append((age, owned, aside))
    return cases


# Read-back of a built patch

# OoTR item -> the actor Link holds. Eggs from anywhere but their own NPC come hatched (songs_trade's targets).
ITEMS = {"Weird Egg": "Item_WeirdEgg", "Chicken": "Item_AlarmCucco", "Zeldas Letter": "Item_ZeldaLetter",
         "Pocket Egg": "Item_PocketEgg", "Pocket Cucco": "Item_PocketCucco", "Cojiro": "Item_CojiroCucco",
         "Odd Mushroom": "Item_OddMushroom", "Odd Potion": "Item_OddPowder", "Poachers Saw": "Item_PoacherSaw",
         "Broken Sword": "Item_BrokenSword", "Prescription": "Item_Prescription", "Eyeball Frog": "Item_EyeballFrog",
         "Eyedrops": "Item_EyeDrop", "Claim Check": "Item_ClaimCheck"}
# OoTR trade location -> (the item its NPC takes, Link's age there)
TRADES = {"Kak Anju Trade Pocket Cucco": ("Item_PocketCucco", "adult"),
          "LW Trade Cojiro": ("Item_CojiroCucco", "adult"),
          "Kak Granny Trade Odd Mushroom": ("Item_OddMushroom", "adult"),
          "LW Trade Odd Potion": ("Item_OddPowder", "adult"),
          "GV Trade Poachers Saw": ("Item_PoacherSaw", "adult"),
          "DMT Trade Broken Sword": ("Item_BrokenSword", "adult"),
          "ZD Trade Prescription": ("Item_Prescription", "adult"),
          "LH Trade Eyeball Frog": ("Item_EyeballFrog", "adult"),
          "DMT Trade Eyedrops": ("Item_EyeDrop", "adult"),
          "DMT Biggoron": ("Item_ClaimCheck", "adult")}
# what each trade gives when its location isn't shuffled (the vanilla chain), and the child gifts
VANILLA = {"Kak Anju Trade Pocket Cucco": "Item_CojiroCucco", "LW Trade Cojiro": "Item_OddMushroom",
           "Kak Granny Trade Odd Mushroom": "Item_OddPowder", "LW Trade Odd Potion": "Item_PoacherSaw",
           "GV Trade Poachers Saw": "Item_BrokenSword", "DMT Trade Broken Sword": "Item_Prescription",
           "ZD Trade Prescription": "Item_EyeballFrog", "LH Trade Eyeball Frog": "Item_EyeDrop",
           "DMT Trade Eyedrops": "Item_ClaimCheck", "HC Malon Egg": "Item_WeirdEgg",
           "HC Zeldas Letter": "Item_ZeldaLetter"}
TALON = ("Talon (castle)", "Item_AlarmCucco", "child")
GATE = ("Kakariko gate guard", "Item_ZeldaLetter", "child")


def _held_actor(item, location, settings):
    if item == "Weird Egg" and location != "HC Malon Egg":
        return "Item_AlarmCucco"
    if item == "Pocket Egg" and (settings or {}).get("adult_trade_shuffle"):
        return "Item_PocketCucco"
    return ITEMS.get(item)


def walk_chains(fc, sp, spoiler):
    """Walks the seed's trades in play order with the patched picker. Each trade's item gets put on the button by
    switching (running the patched ShowItem steps), then handed in the way the hooked hand-in does it (put back,
    taken, everything else back), and then the location's item is added. Returns (problems, notes)."""
    m, bad, notes = Machine(fc, sp), [], []
    settings = spoiler.get("settings") or {}
    locs = {k: (v.get("item") if isinstance(v, dict) else v) for k, v in (spoiler.get("locations") or {}).items()}
    order = [list(sphere) for sphere in (spoiler.get(":playthrough") or {}).values()]
    rest = [k for k in locs if not any(k in s for s in order)] + [k for k in VANILLA if k not in locs]
    state = new_state("child", ())
    done, walked = set(), []
    most = [0]

    def owned():
        return state["pouch"] | state["aside"]

    def hand_in(item):
        m.run(RESTORE, state, {"Actor": item, "Flag": sp["flags"][item]})
        if item not in state["pouch"]:
            bad.append(f"{item}: not back in the pouch for its hand-in")
        state["pouch"].discard(item)
        m.run(UNSTASH, state)

    def trade(name, item, age):
        state["age"] = age
        state["selected"] = button(sp, state["pouch"], age)
        vis = [x for x in visible(sp, age) if x in owned()]
        k = 0
        while button(sp, state["pouch"], age) != item:
            if k > 2 * len(vis) + 1:
                bad.append(f"{name}: {item} never comes onto the button ({age}, owning {sorted(owned())})")
                return False
            state["shown"] = []
            m.run(SWITCH, state)
            k += 1
        hand_in(item)
        walked.append(f"{name}: {item.split('_', 1)[1]} after {k} switch{'' if k == 1 else 'es'}, "
                      f"{len(owned()) + 1} trade items held")
        return True

    def after_get():
        most[0] = max(most[0], len(owned()))
        for who, item, age in (TALON, GATE):
            if who not in done and item in owned() and not (who == GATE[0] and
                                                            settings.get("open_kakariko") == "open"):
                done.add(who)
                trade(who, item, age)
        for egg, chick in (("Item_WeirdEgg", "Item_AlarmCucco"), ("Item_PocketEgg", "Item_PocketCucco")):
            if egg in owned():  # the egg hatches: its hooked hand-in, then the chick
                hand_in(egg)
                state["pouch"].add(chick)

    def step(names):
        progress = True
        while progress:
            progress = False
            for loc in names:
                if loc in done:
                    continue
                if loc in TRADES:
                    item, age = TRADES[loc]
                    if item not in owned():
                        continue
                    done.add(loc)
                    if not trade(loc, item, age):
                        continue
                done.add(loc)
                a = _held_actor(locs[loc], loc, settings) if loc in locs else VANILLA.get(loc)
                if a:
                    state["pouch"].add(a)
                after_get()
                progress = True
    for names in order + [rest]:
        step(names)
    left = [loc for loc in TRADES if loc not in done]
    bad += state["errors"]
    notes.append(f"{len(walked)} trades walked, up to {most[0]} trade items held at once"
                 + (f"; never reached: {', '.join(left)}" if left else ""))
    notes += walked
    return bad, notes


def _restores(e, item):
    """Whether step `e` calls the put-back entry for `item` with its flag."""
    flags = data()["flags_claimed"]
    return e.get("type") == "subflow" and (e.get("flowchart"), e.get("entry_point")) == (SHOWITEM, RESTORE) and \
        _param(e, "Actor") == item and _param(e, "Flag") == flags.get(item)


def _versions(root, name):
    import re as _re
    d = os.path.join(root, "Event", "EventFlow")
    return sorted(f for f in os.listdir(d) if _re.match(_re.escape(name) + r"(\.\d{3})?\.bfevfl\.zs$", f))


def verify(patch, plan, romfs, seed_dir=None, rnd_seed=0):
    """Read the trade button's edits back from a built patch. Returns (problems, notes)."""
    import random
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from evfl_build import is_case_end  # a case's end goes through a do-nothing step (route_end_cases)
    from romtools import Romfs, byml_load, murmur3_32, sarc_files
    from evfl import Evfl
    if not plan.get("trade_slot"):
        return [], []
    sp = plan_spec(plan["trade_slot"])  # same as make_patch, the plan's order and mode with today's data
    d = data()
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad, notes = [], []
    if not sp["picker"]:  # no picker: only the timed removals, by name, in their files
        n = 0
        for base in d["timed_files"]:
            for f in _versions(romfs, base):
                fc = next(x for x in Evfl(fs.read(f"Event/EventFlow/{f}")).flowcharts if x["name"] == base)
                n += sum(1 for kind, _e, _i in sites(fc, set(sp["order"]), base) if kind == "timed")
                bad += [f"{f} {x}" for x in check_timed(fc, sp)]
        notes.append(f"no picker (one trade item per age); {n} timed removals take the timed item by name")
        return bad, notes
    trade = set(sp["order"])
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
    # 1. the picker, run on pouch states
    cases = picker_cases(sp, random.Random(rnd_seed))
    for f, fc in flows(SHOWITEM).items():
        eps = fc["entry_points"]
        missing = [e for e in (SWITCH, UNSTASH, TIMED_FIRST, RESTORE, ASIDE) if e not in eps]
        if missing:
            bad.append(f"{f}: no {', '.join(missing)}")
            continue
        hook = next(e for e in fc["events"] if e["name"] == sp["showitem_hook"])
        if _name(fc, hook["next"]) != f"{SWITCH}_g":
            bad.append(f"{f}: {sp['showitem_hook']} doesn't go on to the picker")
        problems, runs = check_picker(fc, sp, cases)
        bad += [f"{f}: {p}" for p in problems[:20]]
        notes.append(f"{f}: picker run {runs} times on {len(cases)} pouch states")
    show = newest(SHOWITEM)
    # 2. every check, hand-in and timed removal hooked, in every file the data names or the patch holds
    ev_dir = os.path.join(patch, "Event", "EventFlow")
    bases = set(d["files"])
    if os.path.isdir(ev_dir):
        bases |= {f.split(".")[0] for f in os.listdir(ev_dir) if f.endswith(".bfevfl.zs")}
    counts = {"query": 0, "take": 0, "timed": 0}
    for base in sorted(bases):
        for f, fc in flows(base).items():
            by = {e["name"]: e for e in fc["events"]}
            eps = fc["entry_points"]
            bad += [f"{f} {x}" for x in check_timed(fc, sp)]
            for kind, e, item in sites(fc, trade, base):
                nm = e["name"]
                if kind == "query" and base in COSMETIC_QUERY_FILES:
                    continue
                counts[kind] += 1
                if kind == "query":
                    c, q = by.get(hook_name("C", nm)), by.get(hook_name("Q", nm))
                    preds = [p[1] for p in predecessors(fc, e)]
                    _k, yes = _case(e, YES)
                    _k, no = _case(e, NO)
                    if no is not None and no < len(fc["events"]) and is_case_end(fc["events"][no]):
                        no = None  # a case's end goes through a do-nothing step (evfl_build.route_end_cases)
                    ok = c is not None and q is not None and not preds and _what(fc, c) == (POUCH, EXIST) and \
                        _param(c, "Actor") == item and _case(c, NO)[1] == q["idx"] and _case(c, YES)[1] == yes and \
                        _what(fc, q) == (GD, "EventQueryIsGameDataBool") and \
                        _param(q, "GameDataName") == sp["flags"][item] and _case(q, YES)[1] == yes and \
                        (_case(q, NO)[1] if _case(q, NO)[1] is not None and _case(q, NO)[1] < len(fc["events"])
                         and not is_case_end(fc["events"][_case(q, NO)[1]]) else None) == (no if no is not None and no < len(fc["events"]) else None)
                    if not ok:
                        bad.append(f"{f} {nm}: the check of {item} doesn't also count it put aside (reached by "
                                   f"{preds})")
                    continue
                want = hook_name("B", nm)
                preds = predecessors(fc, e)
                if not preds or any(p[1] != want for p in preds):
                    bad.append(f"{f} {nm}: {kind} of {item or 'the button item'} reached by "
                               f"{[p[1] for p in preds]}, not only by {want}")
                    continue
                call = by.get(want)
                if call is None or not (_restores(call, item) if kind != "timed" else
                                        (call.get("flowchart"), call.get("entry_point")) == (SHOWITEM, TIMED_FIRST)):
                    bad.append(f"{f} {want}: doesn't put {item or 'the timed items first'} back")
                if kind != "query":
                    a = by.get(hook_name("P", nm))
                    if a is None or e["next"] != a["idx"] or (a.get("flowchart"), a.get("entry_point")) != \
                            (SHOWITEM, UNSTASH):
                        bad.append(f"{f} {nm}: the {kind} isn't followed by {SHOWITEM}:{UNSTASH}")
            for e in fc["events"]:
                if e["type"] == "subflow" and e.get("flowchart") == SHOWITEM and \
                        (e.get("entry_point") or "").startswith(PREFIX) and \
                        e["entry_point"] not in (show or {}).get("entry_points", {}):
                    bad.append(f"{f} {e['name']}: calls a missing {SHOWITEM}:{e['entry_point']}")
    notes.append(f"hooked: {counts['query']} checks, {counts['take']} hand-ins, {counts['timed']} timed removals "
                 f"(every version of {len(bases)} files)")
    bad += [f"the switch line: {x}" for x in text_problems()]
    # 3. the Claim Check is taken right after Biggoron's reward
    cl = sp["claim"]
    for f, fc in flows(cl["file"]).items():
        anchor = next((e for e in fc["events"] if e["name"] == cl["before"]), None)
        t = next((e for e in fc["events"] if e["name"] == hook_name("C", "t")), None)
        r = next((e for e in fc["events"] if e["name"] == hook_name("C", "r")), None)
        if anchor is None or t is None or r is None or \
                [p[1] for p in predecessors(fc, anchor)] != [hook_name("C", "u")] or not _restores(r, cl["item"]) \
                or _param(t, "Actor") != cl["item"] or _param(t, "Num") != -1:
            bad.append(f"{f}: the Claim Check isn't taken right before {cl['before']}")
    # 4. every trade NPC still reacts to its item, and its scene still hands it in (hooked: 2)
    es = {r["__RowId"]: r for r in byml_load(fs.read("RSDB/EventSetting.Product.111.rstbl.byml.zs"))[0]}

    def hand(scene):
        r = es.get(scene)
        return ((r.get("FlowchartFileName") or "").split("/")[-1].replace(".evfc", ""),
                r.get("EntryPointName") or None) if r else None
    for a in d["acceptances"]:
        files = sarc_files(fs.read(a["pack"]))
        lst = byml_load(files[a["param"]])[0].get("ShowItemReplaceEventParamList") or []
        typ = murmur3_32(sp["enum_name"][a["item"]].encode())
        if not [e for e in lst if e.get("ShowItemType") == typ and a["setting"] in e.get("EventName", "")]:
            bad.append(f"{a['pack']}: no longer reacts to a shown {a['item']} with {a['setting']}")
            continue
        fc = newest(a["flow"])
        ep = (fc or {}).get("entry_points", {}).get(a["entry"])
        if ep is None:
            bad.append(f"{a['flow']}: no entry {a['entry']}")
        elif not reaches_take(fc, ep["main"], a["item"], newest, a["flow"], hand=hand):
            bad.append(f"{a['flow']}:{a['entry']} no longer hands in {a['item']}")
    notes.append(f"{len(d['acceptances'])} trade reactions read back (each reacts to its shown item and hands it in)")
    # 5. the seed's trades walked with the patched picker
    sp_path = os.path.join(seed_dir or os.path.dirname(os.path.abspath(patch)), "spoiler.json")
    if os.path.exists(sp_path) and show is not None:
        b, n = walk_chains(show, sp, json.load(open(sp_path, encoding="utf-8")))
        bad += b
        notes += n
    return bad, notes
