"""Read-back for the special deals. Every special deal sold by its own steps (tools/rando/shops.py _deal_ops) has to be
sold as planned. The shops plugin's note (plan "_gaps" "shop_deals") lists each deal with its talking flag,
GoodsList index, sold-out flag, placeholder, price and give step. We read the built patch:
- DisplayShop NormalFlow starts the deal steps (Rando_ShopDeal_*).
- For each deal there's a talking-flag query whose "yes" reaches a Shop_SelectItemIndex query for its index, and
  that one's "yes" reaches its sold-out flag. From there (within the deal steps) come the rupee check and the
  payment for its price, its give step (the call, or the hand-over of its actor) and clearing the sold-out flag.
- Every list file of its shop (every pack copy) shows the placeholder at that index, at that price, sold out while
  the flag is false (Release IsCheckSoldOutGameData / SoldOutGameData).
- The save data has the flag, true on a new file.
- For a deal showing one of our shelf types (tools/rando/shops.py shelf_type_ops, Rando_Shelf_*: the item's own
  model and name), its pack is in the patch with its ActorParam, which names a ModelInfo the pack holds and the
  name actor. Its ActorInfo row carries that name, and PouchContent has the name's _Name and _ShopCaption in every
  language.
Prints the problems and exits 1 if there are any (python tools/rando/parity/_shops_deals.py OUT_DIR [ROMFS])."""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if os.path.join(HERE, "tools") not in sys.path:  # romtools, for the default below
    sys.path.append(os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
FILE, ENTRY, GRAPH = "DisplayShop", "NormalFlow", "Rando_ShopDeal"


def _what(fc, e):
    if e["type"] in ("action", "switch") and "actor" in e:
        a = fc["actors"][e["actor"]]
        return a["name"], (a["actions"][e["action"]] if e["type"] == "action" else a["queries"][e.get("query", 0)])
    return None, None


def verify(patch, note, romfs=DEFAULT_ROMFS):
    sys.path[:0] = [p for p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando")) if p not in sys.path]
    from romtools import Romfs, byml_load, sarc_files, murmur3_32
    from parity import _dungeons_routes as R
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    van = Romfs(romfs, os.path.join(HERE, "original"))
    flows = R._Flows(fs, van)
    bad = []
    deals = (note or {}).get("deals") or {}
    if not deals:
        return ["the note lists no deal"]
    fc = next((f for f, _ in flows.get(FILE) if f["name"] == FILE), None)
    if fc is None:
        return [f"{FILE}: unreadable"]
    ev = fc["events"]
    ep = fc["entry_points"].get(ENTRY)
    if ep is None or not ev[ep["main"]]["name"].startswith(GRAPH + "_"):
        return [f"{FILE} {ENTRY} doesn't start the deal steps ({ev[ep['main']]['name'] if ep else 'no entry'})"]
    mine = {i for i, e in enumerate(ev) if e["name"].startswith(GRAPH + "_")}

    def reach(starts):
        """Deal steps reachable from `starts` without leaving the deal steps."""
        seen, todo = set(), list(starts)
        while todo:
            i = todo.pop()
            if i in seen or i not in mine:
                continue
            seen.add(i)
            todo += R._nexts(ev[i])
        return seen

    def yes(i, value=0):
        """The step case `value` of query step i goes to (a Bool query: 0 yes; an Int query: 0 below, 1 equal,
        2 above its Value)."""
        return next((c["next"] for c in ev[i].get("cases", []) if c["value"] == value), None)

    chain = reach([ep["main"]])
    for loc, d in sorted(deals.items()):
        talk = [i for i in chain if _what(fc, ev[i]) == ("GameDataActor", "EventQueryIsGameDataBool")
                and R._params(ev[i]).get("GameDataName") == d["talking"]]
        idx = [yes(i) for i in talk if yes(i) is not None
               and _what(fc, ev[yes(i)]) == ("GameDataActor", "EventQueryIsGameDataInt")
               and R._params(ev[yes(i)]).get("GameDataName") == "Shop_SelectItemIndex"
               and R._params(ev[yes(i)]).get("Value") == d["index"]]
        # Case 1 (equal) leads to the sold-out check, and cases 0 (below) and 2 (above) have to skip this sale.
        # Treating 0 as equal sold the first deal for any pick below its index.
        sold = [yes(i, 1) for i in idx if yes(i, 1) is not None
                and R._params(ev[yes(i, 1)]).get("GameDataName") == d["flag"]]
        if not sold:
            bad.append(f"{loc}: no step reached from {ENTRY} tells its pick apart ({d['talking']}, "
                       f"Shop_SelectItemIndex equal to {d['index']}, then {d['flag']})")
            continue
        for i in idx:
            for v in (0, 2):
                if yes(i, v) is not None and yes(i, v) in reach([sold[0]]):
                    bad.append(f"{loc}: a pick {'below' if v == 0 else 'above'} index {d['index']} enters its "
                               f"steps (Shop_SelectItemIndex case {v})")
        steps = reach([yes(sold[0])])
        found = {"money": False, "pay": False, "give": False, "clear": False, "board message": False}
        for i in steps:
            e = ev[i]
            who, what = _what(fc, e)
            p = R._params(e)
            if what == "EventQueryHasRuppe" and p.get("Value") == d["price"]:
                found["money"] = True
            elif what == "EventTriggerIncreaseRupee" and p.get("Value") == -d["price"]:
                found["pay"] = True
            elif what == "EventTriggerSetGameDataBool" and p.get("GameDataName") == d["flag"] and p.get("Value") is False:
                found["clear"] = True
            if what == "EventTriggerSendMessageToShopBoard":
                found["board message"] = True
            c = R._call(fc, e)
            g = d["give"]
            if c and c == g.get("call") and all(p.get(k) == v for k, v in (g.get("params") or {}).items()):
                found["give"] = True
        # a trap ends the shop (Forced_Buy_End), because the ice-trap attacker waits until no event plays. A Light
        # Arrows trap froze nothing while the shop stayed open. Anything else goes back to the shelves.
        import shops as _shops
        trap = _shops._trap_give(d["give"])
        gives = [i for i in steps if R._call(fc, ev[i]) == d["give"].get("call")]
        after = reach([n_ for i in gives for n_ in R._nexts(ev[i])])  # (the steps after the give)
        ends = {R._call(fc, ev[i]) for i in after} | {ev[n_]["name"] for i in after for n_ in R._nexts(ev[i])
                                                       if n_ is not None and n_ < len(ev)}
        if trap and (not gives or not any(str(x).endswith(":Forced_Buy_End") for x in ends)
                     or _shops.DEAL_BACK in ends):
            bad.append(f"{loc}: a trap's sale doesn't end the shop (Forced_Buy_End): its freeze waits for no event")
        missing = [k for k, v in found.items() if not v]
        if missing:
            bad.append(f"{loc}: its deal steps lack {', '.join(missing)} ({d['item']}, {d['price']} rupees, "
                       f"give {d['give']})")
    # the shelves' lists
    packs = {}
    for loc, d in sorted(deals.items()):
        for pack, file in d["lists"]:
            if pack not in packs:
                try:
                    packs[pack] = sarc_files(fs.read(pack))
                except (FileNotFoundError, OSError, KeyError):
                    packs[pack] = None
            files = packs[pack]
            if files is None or file not in files:
                bad.append(f"{loc}: {pack} {file} unreadable")
                continue
            goods = byml_load(files[file])[0].get("GoodsList") or []
            g = goods[d["index"]] if d["index"] < len(goods) else {}
            rel = g.get("Release") or {}
            if (not str(g.get("Actor", "")).endswith(f"/{d['look']}.engine__actor__ActorParam.gyml")
                    or rel.get("IsCheckSoldOutGameData") is not True or rel.get("SoldOutGameData") != d["flag"]):
                bad.append(f"{loc}: {pack} {file} GoodsList[{d['index']}] is {g.get('Actor')} with {rel}, not "
                           f"{d['look']} sold out while {d['flag']} is false")
    # the shelf types, the item's own model and name (shops)
    shelves = 0
    rows = None
    import msbt
    texts = {}
    for loc, d in sorted(deals.items()):
        look = d["look"]
        if not look.startswith("Rando_Shelf_"):
            continue
        shelves += 1
        rel = f"Pack/Actor/{look}.pack.zs"
        try:
            files = sarc_files(fs.read(rel))
        except (FileNotFoundError, OSError, KeyError):
            bad.append(f"{loc}: shelf type {look}: no pack {rel} in the patch")
            continue
        param = f"Actor/{look}.engine__actor__ActorParam.bgyml"
        if param not in files:
            bad.append(f"{loc}: {rel} has no {param}")
            continue
        comps = byml_load(files[param])[0].get("Components") or {}
        model = str(comps.get("ModelInfoRef", "")).lstrip("?")
        name = str(comps.get("ActorNameRef", "")).lstrip("?").rsplit("/", 1)[-1].split(".")[0]
        if model not in files:
            bad.append(f"{loc}: {look} names ModelInfo {model!r}, which its pack lacks")
        if rows is None:
            rows = {r["__RowId"]: r for r in byml_load(fs.read("RSDB/ActorInfo.Product.111.rstbl.byml.zs"),
                                                       allow_big=True)[0]}
        if (rows.get(look) or {}).get("ActorName") != name:
            bad.append(f"{loc}: ActorInfo row {look} is {(rows.get(look) or {}).get('ActorName')!r}, not {name!r}")
        for lang in ("USen", "EUde", "JPja", "EUfr"):
            if lang not in texts:
                texts[lang] = msbt.Msbt(msbt.read_archive(fs, lang)["ActorMsg/PouchContent.msbt"])
            for s in ("_Name", "_ShopCaption"):
                if name + s not in texts[lang].labels:
                    bad.append(f"{loc}: {lang} PouchContent has no {name}{s} ({look}'s name)")
    # the save data: every flag a new Bool, true on a new file
    try:
        gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
        rows = {int(r["Hash"]): r for r in gd["Data"]["Bool"]}
        for loc, d in sorted(deals.items()):
            r = rows.get(murmur3_32(d["flag"]))
            if r is None or r.get("DefaultValue") is not True:
                bad.append(f"{loc}: save data has no Bool {d['flag']} true on a new file ({r})")
    except (FileNotFoundError, OSError, KeyError) as ex:
        bad.append(f"GameDataList unreadable: {ex}")
    verify.counts = {"deals": len(deals), "shelves": shelves}
    return bad


NEVER = "Sequence_IsChildhood"  # a Presence on the level's own age negated: never shown (shops._shop_ops)
BOTTOM_TOL, CENTRE_TOL = 0.03, 0.05  # m: a shelf item's posed base on the vanilla item's, its centre on the vanilla's


def _hidden(actor, file):
    """The placement is never shown: the "never" Presence of its level's age (shops board hiding, stock gate)."""
    p = actor.get("Presence") or {}
    return p.get("FlagName") == NEVER and bool(p.get("IsNegation")) == ("_Child_" in file.rsplit("/", 1)[-1])


def verify_shelves(patch, note, romfs=DEFAULT_ROMFS):
    """[problem] for every changed shop slot (plan "_gaps" "shop_shelves", shops._shop_ops), read from the patch:
    - its price: the shown actor's PouchActorInfo BuyingPrice plus the slot's PriceOffset, in every list, is the price.
      The price window adds those two, so a shelf type with no pouch row showed the offset alone ("85").
    - every placement of one of our shelf types (a tier shelf too) is for sale, meaning a shopkeeper's ForSale link
      reaches it. The keeper finds its items through those links, and a Longshot shelf with none couldn't be picked.
      Every keeper selling it is shown only when the game shows that shop's keeper (its own Presence, kept in each
      tier twin's expression). The Bombchu Shop's comes after King Dodongo, and a seed once had no twin there.
    - its count board: a shown board next to a shown shelf names the item's count, a bundle has one and a single item
      none ("x10" once showed under Saria's Song, with no "x10" by the Arrows (10)).
    - where it stands: the model, as the shelf draws it (shops.posed_box), has its base within BOTTOM_TOL and its
      centre within CENTRE_TOL of the vanilla item's (the Light Arrows once floated 0.25 m above the shelf, and Queen
      Gohma's figure sat 0.38 m below it on a price tag). And one of our shelf types is no larger than shops.SHELF_FIT
      times the vanilla item."""
    import math
    sys.path[:0] = [p for p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando")) if p not in sys.path]
    from romtools import Romfs, byml_load, sarc_files
    import shops
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    slots = (note or {}).get("slots") or {}
    if not slots:
        return ["the note lists no shelf"]
    bad = []
    pouch = {r["__RowId"]: r for r in byml_load(fs.read(shops.POUCH_INFO_TABLE), allow_big=True)[0]}
    gd = {}

    def keeps_gate(k_, file):
        """None if keeper placement `k_` (patched) is shown only when the game shows its shop's keeper, else why."""
        from romtools import murmur3_32
        van_k = shops._level_actors(file).get(str(k_["Hash"])) or next(
            (v for v in shops._level_actors(file).values() if v.get("Gyaml") == k_.get("Gyaml")
             and (v.get("Presence") or {}).get("FlagName") not in (None, shops.KF_STOCK_GATE)), None) or {}
        vp = van_k.get("Presence") or {}
        if not vp or vp.get("FlagName") == shops.KF_STOCK_GATE:  # (the KF gate: its stock is shown throughout)
            return None
        kp = k_.get("Presence") or {}
        if kp.get("FlagName") == vp["FlagName"] and bool(kp.get("IsNegation")) == bool(vp.get("IsNegation")):
            return None
        want = [[murmur3_32(v) if isinstance(v, str) else int(v) for v in x] for x in shops._gate_steps(vp) or []]
        if not gd:
            data = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]["Data"]
            gd.update({int(r["Hash"]): [[int(v) for v in x] for x in r["Values"]] for r in data.get("BoolExp") or []})
        got = gd.get(murmur3_32(kp.get("FlagName") or "")) if not kp.get("IsNegation") else None
        if want and got and any(got[i:i + len(want)] == want for i in range(len(got) - len(want) + 1)):
            return None
        return f"shown by {kp.get('FlagName')}, without the shop keeper's own {vp['FlagName']}"
    info = {r["__RowId"]: r for r in byml_load(fs.read(shops.ACTOR_INFO_TABLE), allow_big=True)[0]}
    packs, levels = {}, {}
    actor_packs, n_cursors = {}, [0]

    def pack_files(actor):
        """The files of `actor`'s pack as the patch has it, or None."""
        if actor not in actor_packs:
            try:
                actor_packs[actor] = sarc_files(fs.read(f"Pack/Actor/{actor}.pack.zs"))
            except (FileNotFoundError, OSError, KeyError):
                actor_packs[actor] = None
        return actor_packs[actor]

    def level(file):
        if file not in levels:
            root = byml_load(fs.read(file), allow_big=True)
            root = root[0] if isinstance(root, tuple) else root
            levels[file] = {str(a.get("Hash")): a for a in root.get("Actors") or []}
        return levels[file]

    def box(gyaml):
        row = info.get(gyaml) or {}
        fb = (row.get("ModelAabbMin"), row.get("ModelAabbMax"))
        if not (row.get("ModelProjectName") and row.get("FmdbName")):
            return fb
        return shops.posed_box(row["ModelProjectName"], row["FmdbName"], shops._banks(row.get("AnimationResources")),
                               fb)

    def centre(t, lo, hi, scale, yaw):
        mx = (float(lo["X"]) + float(hi["X"])) / 2 * float(scale[0])
        mz = (float(lo["Z"]) + float(hi["Z"])) / 2 * float(scale[2])
        c, sn = math.cos(yaw), math.sin(yaw)
        return float(t[0]) + mx * c + mz * sn, float(t[2]) - mx * sn + mz * c
    n_shelves = 0
    for loc, d in sorted(slots.items()):
        # the price
        for pack, file, j in d["lists"]:
            if pack not in packs:
                try:
                    packs[pack] = sarc_files(fs.read(pack))
                except (FileNotFoundError, OSError, KeyError):
                    packs[pack] = None
            files = packs[pack]
            goods = (byml_load(files[file])[0].get("GoodsList") or []) if files and file in files else []
            g = goods[j] if j < len(goods) else {}
            actor = str(g.get("Actor", "")).rsplit("/", 1)[-1].split(".")[0]
            buy = (pouch.get(actor) or {}).get("BuyingPrice")
            shown = None if buy is None else int(buy) + int(g.get("PriceOffset") or 0)
            if actor != d["actor"] or shown != d["price"]:
                bad.append(f"{loc}: {pack} {file} GoodsList[{j}] shows {actor or None} at {shown} (pouch row "
                           f"BuyingPrice {buy}, offset {g.get('PriceOffset')}), not {d['actor']} at {d['price']}")
        e = (shops.shop_map()["locations"].get(loc) or {}).get("edit") or {}
        for s in e.get("shelves") or []:
            acts = level(s["file"])
            a = acts.get(str(s["hash"]))
            fn = s["file"].rsplit("/", 1)[-1]
            if a is None or _hidden(a, s["file"]):
                continue
            n_shelves += 1
            # the placements standing for this shelf: itself and its twins (a tier shelf), same item index, within
            # 1 m (a shop's other slots have other indices; another shop of the level stands farther)
            idx = (a.get("Dynamic") or {}).get("ShopItemIndex")
            spots = [x for x in acts.values() if str(x.get("Gyaml", "")).startswith(("Shop_", "Rando_Shelf_"))
                     and not str(x.get("Gyaml", "")).startswith("Shop_Board_")
                     and (x.get("Dynamic") or {}).get("ShopItemIndex") == idx
                     and math.dist([float(v) for v in x["Translate"]], [float(v) for v in a["Translate"]]) < 1.0
                     and not _hidden(x, s["file"])]
            sellers = {str(ln.get("Dst")) for k in acts.values() for ln in k.get("Links") or []
                       if ln.get("Name") == "ForSale"}
            # a keeper sells one shelf per slot and the last one linked wins the slot, hidden or not. A Longshot
            # shelf linked after the Hookshot's made the shown Hookshot unpickable.
            for k_ in acts.values():
                ends = [acts.get(str(ln.get("Dst"))) for ln in k_.get("Links") or [] if ln.get("Name") == "ForSale"]
                idx_ = [((x or {}).get("Dynamic") or {}).get("ShopItemIndex") for x in ends if x is not None]
                if idx in idx_ and idx_.count(idx) > 1 and str(a["Hash"]) in {str(ln.get("Dst")) for ln in
                                                                             k_.get("Links") or []}:
                    bad.append(f"{loc}: {fn} {k_['Gyaml']} {k_['Hash']} sells {idx_.count(idx)} shelves in slot "
                               f"{idx}: the last linked takes the slot, shown or not")
            for x in spots:
                if str(x["Hash"]) not in sellers:
                    bad.append(f"{loc}: {fn} {x['Gyaml']} {x['Hash']} is not for sale (no shopkeeper's ForSale "
                               f"link): it can't be picked")
            spot_ids = {str(x["Hash"]) for x in spots}
            for k_ in acts.values():  # every keeper selling it stands only when the shop's keeper does
                if any(ln.get("Name") == "ForSale" and str(ln.get("Dst")) in spot_ids for ln in k_.get("Links") or []):
                    why = keeps_gate(k_, s["file"])
                    if why:
                        bad.append(f"{loc}: {fn} keeper {k_['Gyaml']} {k_['Hash']}: {why}")
            # its count board
            want = d.get("count")
            near = [acts[str(ln.get("Dst"))] for ln in a.get("Links") or [] if str(ln.get("Dst")) in acts]
            names = sorted(b["Gyaml"] for b in near if str(b.get("Gyaml", "")).startswith("Shop_Board_Bundle_")
                           and not _hidden(b, s["file"]))
            board = f"Shop_Board_Bundle_{want:02d}" if want else None
            if names != ([board] if board else []):
                bad.append(f"{loc}: {fn} shelf {s['hash']} ({d['actor']}) shows count board(s) {names or 'none'}, "
                           f"want {board or 'none'}")
            # a new board (a twin of the level's) stands on its row's label like vanilla's boards do
            # (shops._board_spot). Otherwise the new "x10" hangs below the shelf, half behind the counter.
            van_acts = shops._level_actors(s["file"])
            for b in near:
                g_ = str(b.get("Gyaml", ""))
                if str(b["Hash"]) in van_acts or not g_.startswith("Shop_Board_") or _hidden(b, s["file"]):
                    continue
                spot = shops._board_spot(s, g_)
                if spot is None or math.dist([float(v) for v in b["Translate"]], spot[0]) > 0.01 or \
                        abs(float(b["Rotate"][1]) - spot[1][1]) > 1e-3:
                    bad.append(f"{loc}: {fn} new board {g_} {b['Hash']} stands at {b.get('Translate')}, not on its "
                               f"row's label {spot and spot[0]}")
            # a one-time slot (a special deal) shows SOLD OUT once bought: its shelf links a SOLD OUT board
            if d.get("deal") and not any(str(b.get("Gyaml")) == shops.SOLD_BOARD and not _hidden(b, s["file"])
                                         for b in near):
                bad.append(f"{loc}: {fn} shelf {s['hash']} links no SOLD OUT board: bought, it shows a blank board")
            # ... and every tier shelf of the spot links it too. The board only shows or hides on the message of a
            # shelf item linking it, so with the tier-0 shelf gone (its tier owned) it stayed up over the next
            # tier's item, a SOLD OUT board under the unbought Longshot.
            sold = {str(b["Hash"]) for b in near if str(b.get("Gyaml")) == shops.SOLD_BOARD and not _hidden(b, s["file"])}
            for x in spots if d.get("deal") and sold else ():
                if not sold & {str(ln.get("Dst")) for ln in x.get("Links") or []}:
                    bad.append(f"{loc}: {fn} {x['Gyaml']} {x['Hash']} doesn't link its spot's SOLD OUT board "
                               f"{sorted(sold)}: shown, it stands with SOLD OUT shown under it")
            # the shop's cursor (shops.CURSOR_REF) has to sit on the model it picks. It centres the target body's
            # height (cursor_base) above the placement's origin plus the type's CursorYOffset. Whether that height
            # scales with the placement isn't settled, so we check both: each within the model's height (CURSOR_TOL
            # of slack), and for one of our shelf types their middle (what the plan aims at) within CURSOR_TOL of its
            # centre. KF's top shelf once had it 0.25 m above Queen Gohma's figure, over its top.
            for x in spots:
                files = pack_files(str(x["Gyaml"]))
                lo, hi = box(x["Gyaml"])
                k = shops.cursor_base(files, str(x["Gyaml"])) if files else None
                if not (lo and hi) or k is None:
                    continue
                n_cursors[0] += 1
                sc = float((x.get("Scale") or [1.0, 1.0, 1.0])[1])
                y0 = float(x["Translate"][1])
                off = shops.cursor_offset(files, str(x["Gyaml"]))
                bottom, top = y0 + float(lo["Y"]) * sc, y0 + float(hi["Y"]) * sc
                ends = (y0 + k + off, y0 + k * sc + off)
                mid, middle = sum(ends) / 2, (bottom + top) / 2
                ours = str(x["Gyaml"]).startswith(shops.SHELF_PREFIX)
                if max(ends) > top + shops.CURSOR_TOL or min(ends) < bottom - shops.CURSOR_TOL or \
                        (ours and abs(mid - middle) > shops.CURSOR_TOL):
                    bad.append(f"{loc}: {fn} {x['Gyaml']} {x['Hash']}: the shop's cursor centres {mid - middle:+.2f} m "
                               f"from its model's centre ({min(ends) - top:+.2f}..{max(ends) - top:+.2f} m from its "
                               f"top; CursorYOffset {off:+.3f}, model {bottom - y0:+.2f}..{top - y0:+.2f} m on its "
                               f"origin, target body {k:.2f} m)")
            # where it stands
            van = shops._level_actors(s["file"]).get(str(s["hash"])) or {}
            vlo, vhi = box(s["gyaml"])
            if not (vlo and vhi and van.get("Translate")):
                continue
            s0 = van.get("Scale") or [1.0, 1.0, 1.0]
            vy = float(van["Translate"][1]) + float(vlo["Y"]) * float(s0[1])
            vcx, vcz = centre(van["Translate"], vlo, vhi, s0, shops.shelf_turn(van.get("Rotate"))[0])
            for x in spots:
                if x["Gyaml"] == s["gyaml"] and x.get("Translate") == van.get("Translate"):
                    continue  # the vanilla item where it stood
                lo, hi = box(x["Gyaml"])
                if not (lo and hi):
                    continue
                sc = x.get("Scale") or [1.0, 1.0, 1.0]
                cx, cz = centre(x["Translate"], lo, hi, sc, shops.shelf_turn(x.get("Rotate"))[0])
                y = float(x["Translate"][1]) + float(lo["Y"]) * float(sc[1])
                off = math.hypot(cx - vcx, cz - vcz)
                if abs(y - vy) > BOTTOM_TOL or off > CENTRE_TOL:
                    bad.append(f"{loc}: {fn} {x['Gyaml']} {x['Hash']} stands {y - vy:+.2f} m from the shelf "
                               f"({s['gyaml']}'s base) and {off:.2f} m off its centre")
                # a shelf type of ours: no larger than SHELF_FIT times the shelf's own item (within the shelf range)
                size = shops._extent(lo, hi) * float(sc[0])
                cap = max(shops.SHELF_SIZE[0], min(shops.SHELF_SIZE[1], shops._extent(vlo, vhi) * max(
                    float(v) for v in s0) * shops.SHELF_FIT))
                if str(x["Gyaml"]).startswith("Rando_Shelf_") and size > cap * shops.SHELF_SCALE_STEP:
                    bad.append(f"{loc}: {fn} {x['Gyaml']} {x['Hash']} is drawn {size:.2f} m large where "
                               f"{s['gyaml']} ({shops._extent(vlo, vhi):.2f} m) stood (at most {cap:.2f} m)")
    verify_shelves.counts = {"slots": len(slots), "shelves": n_shelves, "cursors": n_cursors[0]}
    return bad


def main(argv):
    out = argv[0]
    romfs = argv[1] if len(argv) > 1 else DEFAULT_ROMFS
    plan = json.load(open(os.path.join(out, "plan.json"), encoding="utf-8"))
    note = ((plan.get("_gaps") or {}).get("shop_deals")) or {}
    bad = verify(os.path.join(out, "patch"), note, romfs)
    for b in bad:
        print(b)
    print(f"{len(bad)} problem(s); {len(note.get('deals') or {})} deal(s) read back")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
