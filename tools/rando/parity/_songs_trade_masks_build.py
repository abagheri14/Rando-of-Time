"""Builds data/rando/songs_trade_masks.json, what the mask button's picker and owned record (tools/mask_slot.py) rely
on, read from the game files (vanilla view). The build stops if anything it relies on changed.

usage: python tools/rando/parity/_songs_trade_masks_build.py ROMFS

- order: the 8 masks the equipment button Pa_HeadEquip_02 lists (UI/Pouch/PouchTable EquipmentArray), in its order.
  The button shows the first one in the pouch, at both ages, since every entry is IsUsableAdult and IsUsableChild.
- items: OoTR item name -> the pouch name (Armor_Child_Mask_*) and the get actor (Item_Mask_*).
- flags_claimed: one borrowed saved flag per mask (true while it's owned but put aside), the picker's scratch flag,
  its "switched" result and the Navi-button token. They come from the tools/rando/free_flags.py pool as it is
  without this list, entries FLAG_START.. after the trade button's list. That keeps them clear of the drops plugin's
  flags at the pool's front, the fairies' at its end and the souls' list going down from index 100.
  free_flags.CLAIM_FILES names this file.
- host: the event file the picker's steps go in, ReplaceEquipmentForEraChange. It isn't resident, it only loads with
  its 3 era-change scenes, and it has GameDataActor, PouchSystemActor and Player_Event.
- navi: NaviHint:NaviHint_Field, a shipped do-nothing entry (Npc_Navi.EventDoNothing) with its own EventSetting row.
  The Navi button (Sequence/NaviHintEvent.module.ainb) requests it when Navi has nothing to say. Also the Navi line
  steps of NaviHint_Shield_Hylian (InitTalk_NaviPlayerSide, Npc_Navi.EventTalk) that the switch line copies.
- sequence: the node indexes of NaviHintEvent.module.ainb the edit relies on (the "no area hint" end, the button
  check, the request), and the GameData struct-bool setter it copies (BeforeMinusMenu.module.ainb).
- equip: the head-armor creation step vanilla runs (SageOfShadow Event63, Armor_GlassTruth, a head armor) whose
  parameters the picker's equip step uses.
- sales: every call of NpcCommon:SellMask with a mask (the four mask sales), and NpcCommon:SellMask's take.
- files / site_counts: every event file with a mask check (IsExistInPouch of a mask, or the shop's
  IsExistInPouchWithNameGameData of Shop_SelectItemName).
- stock_exps: every expression flag (BoolExp) that reads a mask's PouchData StockNum, with its vanilla steps.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from romtools import Romfs, byml_load, murmur3_32  # noqa: E402
from evfl import Evfl  # noqa: E402
import ainb  # noqa: E402
import mask_slot  # noqa: E402
import trade_slot  # noqa: E402

OUT = mask_slot.DATA_PATH
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
POUCH_TABLE = "UI/Pouch/PouchTable/PouchTable.game__ui__PouchTable.bgyml"
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
MASK_BUTTON = "Pa_HeadEquip_02"
FLAG_START = 120
ITEMS = {"Mask of Truth": "Truth", "Goron Mask": "Goron", "Zora Mask": "Zora", "Gerudo Mask": "Gerudo",
         "Bunny Hood": "Bunny", "Spooky Mask": "Spooky", "Skull Mask": "Skull", "Keaton Mask": "Keaton"}
# the BoolExp names that read a mask's stock. They're checked against the game data, so every reader has to be
# named here.
STOCK_EXP_NAMES = ["HappyMaskShop_HasMask_" + m for m in ITEMS.values()] + \
    ["HappyMaskShop_RentalAnyMask"] + ["HappyMaskSaleMan_UntilRentMaskOf" + m
                                       for m in ("Keaton", "Skull", "Spooky", "Bunny")]


class BuildError(Exception):
    pass


def flowchart(fs, name):
    rel = sorted(f for f in os.listdir(os.path.join(fs.root, "Event", "EventFlow"))
                 if re.match(re.escape(name) + r"(\.\d{3})?\.bfevfl\.zs$", f))[-1]
    return next(f for f in Evfl(fs.read(f"Event/EventFlow/{rel}")).flowcharts if f["name"] == name)


def event(fc, name):
    e = next((x for x in fc["events"] if x["name"] == name), None)
    if e is None:
        raise BuildError(f"{fc['name']}: no {name}")
    return e


def params(e):
    return {k: (v or {}).get("value") for k, v in (((e.get("params") or {}).get("items")) or {}).items()}


def main(romfs):
    import free_flags
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    fs.root = romfs
    out = {"_about": "Built by tools/rando/parity/_songs_trade_masks_build.py from the game files; used by "
                     "tools/mask_slot.py (the mask button's picker and owned record). Other plugins must not use "
                     "flags_claimed."}
    # the button's masks, in its order
    root = byml_load(fs.raw(POUCH_TABLE))[0]
    btn = next(b for b in root["EquipmentArray"] if b.get("BtnName") == MASK_BUTTON)
    order = [a["ActorShort"] for a in btn["Actor"]]
    if sorted(order) != sorted(f"Armor_Child_Mask_{m}" for m in ITEMS.values()) or btn.get("SpecialDeal") != "Mask":
        raise BuildError(f"{MASK_BUTTON} lists {order}")
    if not all(a.get("IsUsableAdult") and a.get("IsUsableChild") for a in btn["Actor"]):
        raise BuildError(f"{MASK_BUTTON}: a mask isn't usable at both ages")
    out["order"] = order
    out["items"] = {k: {"pouch": f"Armor_Child_Mask_{v}", "get": f"Item_Mask_{v}"} for k, v in ITEMS.items()}
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    bools = {int(r["Hash"]) for r in gd["Bool"]}
    strings = {int(r["Hash"]) for r in gd["String64"]}
    for name, table in ((mask_slot.EQUIP_HEAD, strings), (mask_slot.EQUIP_ACTIVE, bools)):
        if murmur3_32(name.encode()) not in table:
            raise BuildError(f"GameData: no {name} of the expected type")
    # the picker's host file
    fc = flowchart(fs, mask_slot.HOST)
    actors = {a["name"] for a in fc["actors"]}
    if not {"GameDataActor", "PouchSystemActor", "Player_Event"} <= actors:
        raise BuildError(f"{mask_slot.HOST} lacks one of GameDataActor, PouchSystemActor, Player_Event: {actors}")
    if any(k.startswith(mask_slot.PREFIX) for k in fc["entry_points"]):
        raise BuildError(f"{mask_slot.HOST} already has an {mask_slot.PREFIX} entry")
    es = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING))[0]}
    resident = byml_load(fs.raw("Event/ResidentEventList/Default.engine__event__ResidentEventList.bgyml"))[0]
    res_names = {e["EventName"].rsplit("/", 1)[-1].split(".")[0] for e in resident["GlobalResidentEventList"]}
    users = sorted(k for k, r in es.items() if (r.get("FlowchartFileName") or "").endswith(f"/{mask_slot.HOST}.evfc"))
    out["host"] = {"file": mask_slot.HOST, "scene_rows": users}
    # the Navi button's event: NaviHint:NaviHint_Field does nothing
    nv = flowchart(fs, mask_slot.NAVI)
    row = es.get(mask_slot.NAVI_ENTRY) or {}
    if row.get("FlowchartFileName") != f"Work/Event/EventFlow/{mask_slot.NAVI}.evfc" or \
            row.get("EntryPointName") != mask_slot.NAVI_ENTRY or mask_slot.NAVI_ENTRY in res_names:
        raise BuildError(f"EventSetting {mask_slot.NAVI_ENTRY} isn't the non-resident {mask_slot.NAVI}:"
                         f"{mask_slot.NAVI_ENTRY}")
    ep = nv["entry_points"][mask_slot.NAVI_ENTRY]
    nothing = nv["events"][ep["main"]]
    if trade_slot._what(nv, nothing) != ("Npc_Navi", "EventDoNothing") or nothing["next"] < len(nv["events"]):
        raise BuildError(f"{mask_slot.NAVI}:{mask_slot.NAVI_ENTRY} no longer does nothing ({nothing['name']})")
    call, talk = event(nv, "Event135"), event(nv, "Event136")
    if (call.get("flowchart"), call.get("entry_point")) != ("InitTalk", "InitTalk_NaviPlayerSide") or \
            call["next"] != talk["idx"] or trade_slot._what(nv, talk) != ("Npc_Navi", "EventTalk") or \
            not str(params(talk).get("MessageId", "")).startswith(f"EventFlowMsg/{mask_slot.NAVI}:"):
        raise BuildError(f"{mask_slot.NAVI}: Event135/136 are no longer Navi's InitTalk + line")
    if "GameDataActor" not in {a["name"] for a in nv["actors"]}:
        raise BuildError(f"{mask_slot.NAVI} has no GameDataActor")
    out["navi"] = {"file": mask_slot.NAVI, "entry": mask_slot.NAVI_ENTRY, "nothing": nothing["name"],
                   "talk_call": "Event135", "talk": "Event136"}
    # the Navi button: Sequence/NaviHintEvent.module.ainb
    seq = ainb.Ainb(fs.raw(mask_slot.SEQUENCE))
    n = seq.nodes

    def kids(i):
        return {pl["name"]: pl["node"] for pl in n[i]["plugs"][ainb.PLUG_CHILD]}

    def fed(i, name):
        t, e = seq._input(i, name)
        return e["node"], (n[e["node"]]["outputs"][t][e["plug"]]["name"] if e["node"] >= 0 else None)
    S = {"area_sel": 9, "area_query": 10, "end": 0, "trig": 4, "trig_out": "TrigRight", "trig_sel": 17,
         "request": 19, "sim": 28, "struct_q": 34}
    ok = (n[S["area_sel"]]["type"] == 7 and fed(S["area_sel"], "Input")[0] == S["area_query"] and
          n[S["area_query"]]["name"] == "SeqQueryIsNaviAreaHint" and kids(S["area_sel"]).get("False") == S["end"] and
          n[S["end"]]["name"] == "SeqOneShotEnd" and n[S["trig"]]["name"] == "SeqQueryControllerTrigMaskChecker" and
          fed(S["trig_sel"], "Input") == (S["trig"], S["trig_out"]) and
          n[S["request"]]["name"] == "SeqOneShotRequestEvent" and n[S["sim"]]["type"] == 3 and
          kids(S["trig_sel"]).get("True") == 24 and  # the area hint's own request, fired by the same button
          n[S["struct_q"]]["name"] == "SeqQueryGetNonStructGameDataStruct")
    if not ok:
        raise BuildError(f"{mask_slot.SEQUENCE}: the nodes the Navi-button edit relies on changed")
    src = ainb.Ainb(fs.raw(mask_slot.SET_BOOL_FROM["file"]))
    sb = src.nodes[mask_slot.SET_BOOL_FROM["node"]]
    if sb["name"] != "SeqOneShotSetGameDataBool" or {"GameDataName", "Value", "ParentStruct"} - \
            {e["name"] for t in ainb.PTYPES for e in sb["inputs"][t]}:
        raise BuildError(f"{mask_slot.SET_BOOL_FROM}: not a SeqOneShotSetGameDataBool with a ParentStruct")
    out["sequence"] = S
    # the head-armor creation step vanilla runs (the Lens of Truth, a head armor)
    lens = event(flowchart(fs, "SageOfShadow"), "Event63")
    p = params(lens)
    if p.get("EquipmentActorName") != "Armor_GlassTruth" or set(p) != {"EquipmentActorName", "IsActive",
                                                                     "DynamicEquipmentState"}:
        raise BuildError(f"SageOfShadow Event63 is no longer the head-armor creation ({p})")
    out["equip"] = {"from": "SageOfShadow:Event63", "DynamicEquipmentState": p["DynamicEquipmentState"]}
    # Check that SellMask takes ReceiveItem, then find its mask callers.
    nc = flowchart(fs, "NpcCommon")
    take = event(nc, mask_slot.SELL_TAKE)
    it = ((take.get("params") or {}).get("items") or {})
    if trade_slot._what(nc, take) != ("PouchSystemActor", "EventTriggerAddOrRemovePouchContent") or \
            (it.get("Actor") or {}).get("type") != "argument" or (it.get("Actor") or {}).get("value") != "ReceiveItem" \
            or params(take).get("Num") != -1:
        raise BuildError(f"NpcCommon {mask_slot.SELL_TAKE} is no longer SellMask's take of ReceiveItem")
    sales, files, counts = [], set(), {"query": 0, "name_query": 0}
    for f in sorted(os.listdir(os.path.join(romfs, "Event", "EventFlow"))):
        if not f.endswith(".bfevfl.zs"):
            continue
        try:
            ev = Evfl(fs.read(f"Event/EventFlow/{f}"))
        except Exception:  # noqa: BLE001 - timeline-only files
            continue
        base = f.split(".")[0]
        for x in ev.flowcharts:
            found = mask_slot.sites(x, set(order), base)
            for kind, e, item in found:
                if kind == "sale":
                    sales.append({"file": base, "event": e["name"], "mask": item})
                else:
                    counts[kind] += 1
            if found:
                files.add(base)
    if sorted(s["mask"] for s in sales) != sorted(f"Armor_Child_Mask_{m}" for m in ("Keaton", "Skull", "Spooky",
                                                                                  "Bunny")):
        raise BuildError(f"the mask sales are {sales}")
    out["sales"] = sales
    out["files"] = sorted(files | {mask_slot.HOST, mask_slot.NAVI})
    out["site_counts"] = counts
    # expression flags reading a mask's stock
    stock = {murmur3_32(f"PouchData.{m}.StockNum".encode()): m for m in order}
    names = {murmur3_32(nm.encode()): nm for nm in STOCK_EXP_NAMES}
    exps = {}
    for r in gd["BoolExp"]:
        vals = [[int(x) for x in v] for v in r.get("Values") or []]
        if any(v[0] == 15 and v[1] in stock for v in vals):
            nm = names.get(int(r["Hash"]))
            if nm is None:
                raise BuildError(f"BoolExp {r['Hash']} reads a mask's stock and isn't named in STOCK_EXP_NAMES")
            for k, v in enumerate(vals):
                if v[0] == 15 and v[1] in stock and not (k + 1 < len(vals) and vals[k + 1][0] == 16
                                                         and vals[k + 1][1] in (0, 1)):
                    raise BuildError(f"{nm}: a mask stock compared with something but 0 or 1")
            exps[nm] = vals
    if sorted(exps) != sorted(STOCK_EXP_NAMES):
        raise BuildError(f"stock readers {sorted(exps)} != {sorted(STOCK_EXP_NAMES)}")
    out["stock_exps"] = exps
    out["stock_hash"] = {m: h for h, m in stock.items()}
    keys = sorted(order) + list(mask_slot.SCRATCH_KEYS)
    pool = free_flags.pool(romfs, own="songs_trade_masks")
    out["flags_claimed"] = dict(zip(keys, pool[FLAG_START:FLAG_START + len(keys)]))
    if len(out["flags_claimed"]) != len(keys):
        raise BuildError("not enough free flags")
    # the Sequence edit sets the token the way the module reads ActionGuide_IsEnd.Navi, struct then member by name
    struct, _, member = out["flags_claimed"]["token"].partition(".")
    row = next((r for r in gd["Struct"] if int(r["Hash"]) == murmur3_32(struct.encode())), None)
    pairs = {int(x["Hash"]): int(x["Value"]) for x in (row or {}).get("DefaultValue") or []}
    if struct != mask_slot.TOKEN_STRUCT or pairs.get(murmur3_32(member.encode())) != \
            murmur3_32(out["flags_claimed"]["token"].encode()):
        raise BuildError(f"the token flag isn't the member {member} of the GameData struct {struct}")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"{OUT}: {len(sales)} sales, sites {counts} in {len(files)} files, {len(exps)} stock expressions, flags "
          f"{min(out['flags_claimed'].values())} .. {max(out['flags_claimed'].values())}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else __import__("romtools").longshot_romfs())
