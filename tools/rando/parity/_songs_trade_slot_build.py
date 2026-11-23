"""Builds data/rando/songs_trade_slot.json, what the trade button's picker and owned record (tools/trade_slot.py) rely
on, read from the game files (vanilla view). The build stops if anything it relies on changed.

usage: python tools/rando/parity/_songs_trade_slot_build.py ROMFS

- flags_claimed: one borrowed saved flag per trade item and the picker's scratch flag. They come from the
  tools/rando/free_flags.py pool as it is without this list, entries FLAG_START.., clear of the drops plugin's
  flags (taken from the pool's front), the fairies' (from its end) and the souls' fixed list (going down from index
  100). free_flags.CLAIM_FILES names this file.
- enum / enum_name: each item's AssignableItem as event steps pass it (EventCreateShowItem, ShowItem's entries,
  EventPlayerSetSelectedItem) and its name in PlayerStatus.AssignableItem.Child/.Adult (the selected item). The
  value is the save list's enum position minus one, since its first value, Empty, has no step value. It's checked
  against every constant the vanilla steps use for a known item.
- child: the items the button shows a child only (PouchTable Pa_ItemIcon_23 IsUsableChild and not IsUsableAdult).
- timed: the items SubEvent_GetSwordBigGoron_TimerCountingStep reads (Biggoron's timers).
- showitem: ShowItem:EntryPoint0's last step (NpcCommon:ShowItem_Close, then the end), where the picker starts.
- claim_check: Biggoron's step after his claim-check reward (Event113, reached only from the give Event123).
- files: every event file with a trade check, hand-in or timed removal (each version), and the two above.
- acceptances: every NPC reaction to a shown trade item whose scene takes it (the trades), from every actor pack's
  GameParameter/ShowItemReplaceEventParam (ShowItemType = murmur3 of the enum name).
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from romtools import Romfs, byml_load, murmur3_32, sarc_files  # noqa: E402
from evfl import Evfl  # noqa: E402
import trade_slot  # noqa: E402

OUT = trade_slot.DATA_PATH
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
POUCH_TABLE = "UI/Pouch/PouchTable/PouchTable.game__ui__PouchTable.bgyml"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
TRADE_BUTTON = "Pa_ItemIcon_23"
FLAG_START = 120
TIMER_EXP = "SubEvent_GetSwordBigGoron_TimerCountingStep"
# vanilla steps passing a known item's AssignableItem (file, event, parameter, item)
KNOWN_ENUMS = [("Goto_HyruleCastle", "Event126", "AssignableItem", "Item_AlarmCucco"),
               ("Goto_HyruleCastle", "Event86", "Item", "Item_AlarmCucco"),
               ("SubEvent_GetSwordBigGoron", "Event44", "Item", "Item_PocketCucco"),
               ("Npc_Kokiri_Fado_Adult", "Event84", "AssignableItem", "Item_OddPowder"),
               ("Npc_Hylia_017_Adult", "Event120", "AssignableItem", "Item_OddMushroom"),
               ("Npc_Goron_Biggoron_Adult", "Event138", "AssignableItem", "Item_ClaimCheck")]
CLAIM = {"file": "Npc_Goron_Biggoron_Adult", "give": "Event123", "before": "Event113", "item": "Item_ClaimCheck",
         "entry": "SubEvent_GetSwordBigGoron_Step11"}


class BuildError(Exception):
    pass


def flowchart(fs, name):
    rel = sorted(f for f in fs_files(fs) if re.match(re.escape(name) + r"(\.\d{3})?\.bfevfl\.zs$", f))[-1]
    return next(f for f in Evfl(fs.read(f"Event/EventFlow/{rel}")).flowcharts if f["name"] == name)


def fs_files(fs):
    return sorted(os.listdir(os.path.join(fs.root, "Event", "EventFlow")))


def event(fc, name):
    e = next((x for x in fc["events"] if x["name"] == name), None)
    if e is None:
        raise BuildError(f"{fc['name']}: no {name}")
    return e


def main(romfs):
    import free_flags
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    fs.root = romfs
    out = {"_about": "Built by tools/rando/parity/_songs_trade_slot_build.py from the game files; used by "
                     "tools/trade_slot.py (the trade button's picker and owned record, D3). Other plugins must not "
                     "use flags_claimed."}
    # Read the trade button's items and find the ones only child Link can use.
    root = byml_load(fs.raw(POUCH_TABLE))[0]
    btn = next(b for b in root["ItemArray"] if b.get("BtnName") == TRADE_BUTTON)
    items = [a["ActorShort"] for a in btn["Actor"]]
    if len(items) != 14:
        raise BuildError(f"{TRADE_BUTTON} lists {len(items)} items, not 14")
    child = sorted(a["ActorShort"] for a in btn["Actor"] if a.get("IsUsableChild") and not a.get("IsUsableAdult"))
    if child != sorted(["Item_WeirdEgg", "Item_AlarmCucco", "Item_ZeldaLetter"]):
        raise BuildError(f"{TRADE_BUTTON}: child-only items are {child}")
    out["child"] = child
    # enums
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    row = next(r for r in gd["Enum"] if int(r["Hash"]) == murmur3_32(trade_slot.SELECTED["child"].encode()))
    adult = next(r for r in gd["Enum"] if int(r["Hash"]) == murmur3_32(trade_slot.SELECTED["adult"].encode()))
    if list(row["RawValues"]) != list(adult["RawValues"]) or row["RawValues"][0] != "Empty":
        raise BuildError("PlayerStatus.AssignableItem.Child/.Adult no longer list the same values, Empty first")
    raw = list(row["RawValues"])
    out["enum_name"] = {x: x.split("_", 1)[1] for x in sorted(items)}
    out["enum"] = {x: raw.index(out["enum_name"][x]) - 1 for x in sorted(items)}
    for file, ev, param, item in KNOWN_ENUMS:
        e = event(flowchart(fs, file), ev)
        v = trade_slot._param(e, param)
        if v != out["enum"][item]:
            raise BuildError(f"{file}:{ev} passes {param}={v} for {item}, the enum says {out['enum'][item]}")
    # Biggoron's timers
    exp = next(r for r in gd["BoolExp"] if int(r["Hash"]) == murmur3_32(TIMER_EXP.encode()))
    words = {int(w) for v in exp.get("Values") or [] for w in (v if isinstance(v, list) else [v])
             if isinstance(w, int)}
    out["timed"] = sorted(x for x in items if murmur3_32(f"PouchData.{x}.StockNum".encode()) in words)
    if out["timed"] != ["Item_EyeDrop", "Item_EyeballFrog", "Item_OddMushroom"]:
        raise BuildError(f"{TIMER_EXP} reads {out['timed']}")
    # the picker's start: ShowItem:EntryPoint0 ends with NpcCommon:ShowItem_Close
    fc = flowchart(fs, trade_slot.SHOWITEM)
    hook = event(fc, "Event47")
    if (hook["type"], hook.get("flowchart"), hook.get("entry_point"), hook["next"] < len(fc["events"])) != \
            ("subflow", "NpcCommon", "ShowItem_Close", False):
        raise BuildError("ShowItem:Event47 is no longer the last step NpcCommon:ShowItem_Close")
    seen, stack = set(), [fc["entry_points"]["EntryPoint0"]["main"]]
    while stack:
        i = stack.pop()
        if i in seen or i >= len(fc["events"]):
            continue
        seen.add(i)
        stack += trade_slot._successors(fc, fc["events"][i])
    if hook["idx"] not in seen or "ShowItemSuccess" not in fc["entry_points"]:
        raise BuildError("ShowItem:EntryPoint0 no longer reaches Event47, or ShowItemSuccess is gone")
    talk = event(fc, "Event4")
    if trade_slot._what(fc, talk) != ("SystemTextNPC", "EventTalk") or trade_slot._param(talk, "MessageId") != "EventFlowMsg/Item_Event:Talk_03":
        raise BuildError("ShowItem:Event4 is no longer EntryPoint0's 'doesn't seem useful' line")
    out["showitem"] = {"file": trade_slot.SHOWITEM, "entry": "EntryPoint0", "hook": "Event47", "talk": "Event4"}
    # the Claim Check: Biggoron's step after his reward
    fc = flowchart(fs, CLAIM["file"])
    give, after = event(fc, CLAIM["give"]), event(fc, CLAIM["before"])
    if give.get("flowchart") != "Dm_SY_GetInEvent" or give["next"] != after["idx"] or \
            trade_slot.predecessors(fc, after) != [("next", CLAIM["give"], None)]:
        raise BuildError(f"{CLAIM['file']}: {CLAIM['before']} is no longer reached only from the give {CLAIM['give']}")
    out["claim_check"] = CLAIM
    # event files with a trade check, hand-in or timed removal
    files = {trade_slot.SHOWITEM, CLAIM["file"]}
    timed_files = set()
    counts = {"query": 0, "take": 0, "timed": 0}
    for f in fs_files(fs):
        if not f.endswith(".bfevfl.zs"):
            continue
        try:
            ev = Evfl(fs.read(f"Event/EventFlow/{f}"))
        except Exception:  # noqa: BLE001 - timeline-only files
            continue
        base = f.split(".")[0]
        for x in ev.flowcharts:
            found = trade_slot.sites(x, set(items), base)
            for kind, _e, _i in found:
                counts[kind] += 1
                if kind == "timed":
                    timed_files.add(base)
            if found:
                files.add(base)
    out["files"] = sorted(files)
    out["timed_files"] = sorted(timed_files)
    out["site_counts"] = counts
    # acceptances: NPC reactions to a shown trade item whose scene takes it
    es = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}
    types = {murmur3_32(out["enum_name"][x].encode()): x for x in items}
    acc = []
    for p in sorted(glob.glob(os.path.join(romfs, "Pack", "Actor", "*.pack.zs"))):
        rel = os.path.relpath(p, romfs).replace(os.sep, "/")
        try:
            files_in = sarc_files(fs.read(rel))
        except Exception:  # noqa: BLE001
            continue
        for k, v in files_in.items():
            if "ShowItemReplaceEventParam" not in k:
                continue
            for e in byml_load(v)[0].get("ShowItemReplaceEventParamList") or []:
                item = types.get(e.get("ShowItemType"))
                if not item:
                    continue
                setting = e["EventName"].split("/")[-1].split(".")[0]
                r = es.get(setting) or {}
                flow = (r.get("FlowchartFileName") or "").split("/")[-1].replace(".evfc", "")
                entry = r.get("EntryPointName")
                try:
                    fcx = flowchart(fs, flow)
                except (IndexError, StopIteration):
                    continue
                ep = fcx["entry_points"].get(entry)
                takes = ep is not None and trade_slot.reaches_take(
                    fcx, ep["main"], item, lambda name: _load(fs, name), flow, hand=lambda scene: _hand(es, scene))
                if takes or (item, flow, entry) == (CLAIM["item"], CLAIM["file"], CLAIM["entry"]):
                    acc.append({"pack": rel, "param": k, "item": item, "setting": setting, "flow": flow,
                                "entry": entry, "conditions": {c: e[c] for c in e
                                                               if c not in ("EventName", "ShowItemType")}})
    out["acceptances"] = acc
    keys = sorted(items) + [trade_slot.SCRATCH]
    out["flags_claimed"] = dict(zip(keys, free_flags.pool(romfs, own="songs_trade")[FLAG_START:FLAG_START + len(keys)]))
    if len(out["flags_claimed"]) != len(keys):
        raise BuildError("not enough free flags")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"{OUT}: {len(acc)} acceptances, sites {counts} in {len(files)} files, flags "
          f"{min(out['flags_claimed'].values())} .. {max(out['flags_claimed'].values())}")


_CACHE = {}


def _hand(es, scene):
    """The (file, entry) for a scene name from RSDB/EventSetting. With no entry it's the file's first."""
    r = es.get(scene)
    if not r:
        return None
    return (r.get("FlowchartFileName") or "").split("/")[-1].replace(".evfc", ""), r.get("EntryPointName") or None


def _load(fs, name):
    if name not in _CACHE:
        try:
            _CACHE[name] = flowchart(fs, name)
        except (IndexError, StopIteration):
            _CACHE[name] = None
    return _CACHE[name]


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else __import__("romtools").longshot_romfs())
