"""Builds data/rando/songs_trade_child.json, the scene steps and save data for the child trade, mask shop and beans.
That part of the songs/trade plugin is _songs_trade_child.py. Everything is read from the game files (vanilla view)
and every step is checked (call, actor action or query, key parameters, routing), so the build stops if a file
differs from what the plugin expects.

usage: python tools/rando/parity/_songs_trade_child_build.py ROMFS
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romtools import Romfs, byml_load, sarc_files, murmur3_32  # noqa: E402
from _songs_trade_build import BuildError, expect, load_all  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "songs_trade_child.json")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
MASKS = {  # OoTR mask -> remake pouch mask, get actor, mask shop GoodsList index, OoTR mask shop location
    "Keaton Mask": ("Armor_Child_Mask_Keaton", "Item_Mask_Keaton", 1, "Market Mask Shop Item 6"),
    "Skull Mask": ("Armor_Child_Mask_Skull", "Item_Mask_Skull", 3, "Market Mask Shop Item 5"),
    "Spooky Mask": ("Armor_Child_Mask_Spooky", "Item_Mask_Spooky", 0, "Market Mask Shop Item 8"),
    "Bunny Hood": ("Armor_Child_Mask_Bunny", "Item_Mask_Bunny", 2, "Market Mask Shop Item 7"),
    "Goron Mask": ("Armor_Child_Mask_Goron", "Item_Mask_Goron", 5, "Market Mask Shop Item 4"),
    "Zora Mask": ("Armor_Child_Mask_Zora", "Item_Mask_Zora", 4, "Market Mask Shop Item 2"),
    "Gerudo Mask": ("Armor_Child_Mask_Gerudo", "Item_Mask_Gerudo", 6, "Market Mask Shop Item 1"),
    "Mask of Truth": ("Armor_Child_Mask_Truth", "Item_Mask_Truth", 7, "Market Mask Shop Item 3"),
}
SHOP_PACK = "Pack/Actor/Npc_Hylia_023_Shop_Child.pack.zs"
SHOP_LIST = "Component/ShopParam/Npc_Hylia_023_Shop.game__component__ShopParam.bgyml"
GATE = "Npc_Hylia_Soldier_003_GateOpen"  # opens the Kakariko gate and the mask shop
MALON_GIFT_FLAG = "HaveTalked_Special.Goto_HyruleCastle_Goto_HyruleCastle_AfterMalonAppear_Event38"
# Four saved Bools (ResetType 8) for the mask shop count and one for the bean seller's sold state.
# Their names only show up in GameDataList, so as far as I can tell nothing uses these flags.
FLAGS = {"mask_bits": ["HavePlayedEvent.Npc_StepStart_Base", "HavePlayedEvent.Npc_StepStart_NotStarter_Base",
                       "HavePlayedEvent.Dm_MelodyGet_Manegement", "HavePlayedEvent.MiniGame_Fishing_Tutorial_Parent"],
         "beans_sold": "HavePlayedEvent.Parent_Dungeon_DoorMovement"}


def agreed(fs, romfs, name, build):
    results = [(rel, build(fc)) for rel, fc in load_all(fs, romfs, name)]
    for rel, r in results[1:]:
        if r != results[0][1]:
            raise BuildError(f"{rel}: steps differ from {results[0][0]}")
    return results[0][1]


def entry_of(fc, entry):
    i = fc["entry_points"][entry]["main"]
    return fc["events"][i]["name"]


def egg_data(fs, romfs):
    """Malon's Weird Egg (HC Malon Egg), its hatch and Talon's wake-up (Goto_HyruleCastle)."""
    def build(fc):
        give = expect(fc, "Event35", "call", ("Dm_SY_GetInEvent:GetInEvent_NotTurn", {"ActorName": "Item_WeirdEgg"}))
        step3 = expect(fc, "Event46", "action", ("ChallengeSystemActor.EventExecuteProgressChallengeStep",
                                                 {"ChallengeName": "Goto_HyruleCastle", "StepName": "Step03"}))
        gift_flag = expect(fc, "Event76", "action", ("GameDataActor.EventTriggerSetGameDataBool",
                                                     {"GameDataName": MALON_GIFT_FLAG}))
        remove = expect(fc, "Event55", "action", ("PouchSystemActor.EventTriggerAddOrRemovePouchContent",
                                                  {"Actor": "Item_WeirdEgg", "Num": -1}))
        hatch = expect(fc, "Event20", "call", ("GetInEvent_EggHatche:GetInEvent_EggHatche",
                                               {"ActorName": "Item_AlarmCucco"}))
        step_start = expect(fc, "Event25", "query", ("Player_Event.EventQueryPlayerCheckSelectedItem",))
        after_hatch = expect(fc, "Event88", "action", ("ChallengeSystemActor.EventExecuteProgressChallengeStep",
                                                       {"ChallengeName": "Goto_HyruleCastle", "StepName": "Step03_02"}))
        wake = expect(fc, "Event72", "action", ("Npc_Hylia_Talon_Child.EventTriggerParticipateEvent",))
        if remove["next"] != "Event20":
            raise BuildError("Goto_HyruleCastle: the egg gift or the hatch changed shape")
        if entry_of(fc, "Step03_01_Npc_Navi_StepStart") != "Event25" or \
                entry_of(fc, "Goto_HyruleCastle_AfterWakeUpTalon") != "Event72":
            raise BuildError("Goto_HyruleCastle: hatch or wake-up entry moved")
        return {"give": give, "step3": step3, "gift_flag": gift_flag, "remove": remove, "hatch": hatch,
                "hatch_start": step_start, "after_hatch": after_hatch, "wake": wake}
    d = agreed(fs, romfs, "Goto_HyruleCastle", build)
    d.update(file="Goto_HyruleCastle", gift_flag_name=MALON_GIFT_FLAG,
             give_reward_id="event/Goto_HyruleCastle/Goto_HyruleCastle/Event35/ActorName",
             remove_reward_id="event/Goto_HyruleCastle/Goto_HyruleCastle/Event55/Actor")
    return d


def letter_data(fs, romfs):
    """Zelda's Letter. Dm_HrlCastle_0050 Event59 gives it, and the Kakariko guard reacts when you show it until the gate
    is open (ShowItemReplaceEventParam InvalidGameData Npc_Hylia_Soldier_003_GateOpen)."""
    give = agreed(fs, romfs, "Dm_HrlCastle_0050", lambda fc: expect(
        fc, "Event59", "call", ("Dm_SY_GetInEvent:GetInEvent_Zeldaletter", {"ActorName": "Item_ZeldaLetter"})))
    files = sarc_files(fs.read("Pack/Actor/Npc_Hylia_Soldier_003.pack.zs"))
    rel = next(n for n in files if "ShowItemReplaceEventParam" in n)
    lst = byml_load(files[rel])[0]["ShowItemReplaceEventParamList"]
    if len(lst) != 1 or "ShowItem_ZeldaLetter" not in lst[0]["EventName"] or lst[0].get("InvalidGameData") != GATE:
        raise BuildError("Npc_Hylia_Soldier_003: the letter reaction changed")
    return {"file": "Dm_HrlCastle_0050", "give": give, "guard_reaction": lst[0]}


def mask_shop_data(fs, romfs):
    """The Happy Mask Shop: the DisplayShop Root_HappyMaskShop path, Npc_Hylia_023_Shop_Child and the GoodsList Release
    expressions HappyMaskShop_HasMask_*."""
    def build(fc):
        sold_check = expect(fc, "Event134", "query", ("Npc_EventStarter.EventQueryCheckIsSoldOutSelectItem",))
        decide = expect(fc, "Event54", "query", ("Npc_EventStarter.EventQueryIsShopBuyScreenDecideGoods",))
        if [p[1] for p in sold_check["preds"]] != ["Event54"] or entry_of(fc, "Root_HappyMaskShop") != "Event51":
            raise BuildError("DisplayShop: the mask shop's selection step moved")
        close = expect(fc, "Event182", "action", ("Npc_EventStarter.EventCloseShopBuyScreen",))
        end = expect(fc, "Event308", "call", (":Buy_End_ForHappyMaskShop",))
        remove = expect(fc, "Event113", "action", ("Npc_EventStarter.EventTriggerRemoveOwnedMask",))
        borrow = expect(fc, "Event60", "action", ("Npc_EventStarter.EventTriggerBorrowMaskAtShop",))
        if remove["next"] != "Event60" or entry_of(fc, "Rental_Common") != "Event113":
            raise BuildError("DisplayShop: Rental_Common changed")
        name_q = expect(fc, "Event195", "query", ("GameDataActor.EventQueryIsGameDataString64",
                                                  {"GameDataName": "Shop_SelectItemName",
                                                   "Value": "Armor_Child_Mask_Spooky"}))
        return {"sold_check": sold_check, "decide": decide, "close": close, "end": end, "rental_remove": remove,
                "borrow": borrow, "name_query": name_q}
    d = agreed(fs, romfs, "DisplayShop", build)
    truth = agreed(fs, romfs, "Npc_Hylia_023_Shop_Child", lambda fc: expect(
        fc, "Event51", "call", ("Dm_SY_GetInEvent:GetInEvent_Mask", {"ActorName": "Item_Mask_Truth"})))
    if truth["next"] is not None:
        raise BuildError("Npc_Hylia_023_Shop_Child:Event51 no longer ends its branch")
    files = sarc_files(fs.read(SHOP_PACK))
    goods = byml_load(files[SHOP_LIST])[0]["GoodsList"]
    slots = {}
    for ootr, (pouch, get_actor, index, loc) in MASKS.items():
        g = goods[index]
        if g["Actor"] != f"Work/Actor/Shop_{pouch.replace('Armor_Child_', '')}.engine__actor__ActorParam.gyml":
            raise BuildError(f"{SHOP_LIST}: slot {index} sells {g['Actor']}, expected {pouch}")
        rel = g["Release"]["ReleaseGameData"]
        if rel != "HappyMaskShop_HasMask_" + pouch.rsplit("_", 1)[1]:
            raise BuildError(f"{SHOP_LIST}: slot {index} released by {rel}")
        slots[ootr] = {"pouch": pouch, "get_actor": get_actor, "index": index, "location": loc, "release": rel}
    # the expressions and flags must exist in the save-data list
    gd = byml_load(fs.read(GAMEDATA), allow_big=True)[0]["Data"]
    exps = {e["Hash"] for e in gd["BoolExp"]}
    bools = {e["Hash"]: e for e in gd["Bool"]}
    for s in slots.values():
        if murmur3_32(s["release"].encode()) not in exps:
            raise BuildError(f"GameDataList: no expression {s['release']}")
    for f in FLAGS["mask_bits"] + [FLAGS["beans_sold"], GATE, MALON_GIFT_FLAG]:
        e = bools.get(murmur3_32(f.encode()))
        if not e or e["ResetTypeValue"] != 8:
            raise BuildError(f"GameDataList: {f} is not a saved Bool")
    d.update(file="DisplayShop", truth_handover=truth, truth_file="Npc_Hylia_023_Shop_Child", slots=slots,
             gate=GATE, truth_reward_id="event/Npc_Hylia_023_Shop_Child/Npc_Hylia_023_Shop_Child/Event51/ActorName")
    return d


def bean_data(fs, romfs):
    """ZR Magic Bean Salesman (Npc_Hylia_047_Child). The beans bought so far (Get_MagicBeans 0-10) pick the price tier
    in Event0. The 60-rupee tier is Event10 (SellBeans) -> Event11 (SimpleShop:SimpleShopRoot_3Choices), and once ten
    are bought it's Event27 (no more beans). In SimpleShop it goes Event100 rupees -> Event126 "can it go in the pouch"
    -> Event195 Sub_SimpleShop_Buy_MagicBean, whose hand-over is Event182 (Item_MagicBean), then Event40 counts the
    bean."""
    def seller(fc):
        branch = expect(fc, "Event0", "query", ("GameDataActor.EventQueryGameDataIntBranch",
                                                {"GameDataName": "Get_MagicBeans"}))
        tier = expect(fc, "Event10", "call", (":SellBeans", {"Price": 60}))
        root = expect(fc, "Event11", "call", ("SimpleShop:SimpleShopRoot_3Choices",
                                              {"ActorName": "Item_MagicBean", "Price": 60}))
        done = expect(fc, "Event27", "query", ("Npc_EventStarter.EventQueryVolatileGeneralPurposeFlagOn",))
        if tier["next"] != "Event11":
            raise BuildError("Npc_Hylia_047_Child: the 60-rupee tier no longer leads to its sale")
        return {"branch": branch, "tier": tier, "root": root, "sold_out": done}
    d = agreed(fs, romfs, "Npc_Hylia_047_Child", seller)

    def shop(fc):
        rupees = expect(fc, "Event100", "query", ("PouchSystemActor.EventQueryHasRuppe",))
        pouch = expect(fc, "Event126", "query", ("PouchSystemActor.EventQueryCanAddToPorch",))
        buy = expect(fc, "Event195", "call", (":Sub_SimpleShop_Buy_MagicBean",))
        give = expect(fc, "Event182", "call", ("NpcCommon:NpcCommon_HandOver_NpcToPlayer_NoDisplay",
                                               {"ReveiveItem": "Item_MagicBean"}))
        count = expect(fc, "Event40", "action", ("GameDataActor.EventTriggerAddOrSubGameDataInt",
                                                 {"GameDataName": "Get_MagicBeans"}))
        if [p[1] for p in pouch["preds"]] != ["Event100"] or [p[1] for p in count["preds"]] != ["Event195"]:
            raise BuildError("SimpleShop: the bean sale path is shared or moved")
        return {"rupees": rupees, "pouch": pouch, "buy": buy, "give": give, "count": count}
    d["shop"] = agreed(fs, romfs, "SimpleShop", shop)
    # Make sure no other event calls this bean-shop entry.
    callers = set()
    for rel in os.listdir(os.path.join(romfs, "Event", "EventFlow")):
        if not rel.endswith(".bfevfl.zs") or rel.startswith("SimpleShop."):
            continue
        if b"SimpleShopRoot_3Choices" in fs.read(f"Event/EventFlow/{rel}"):
            callers.add(rel.split(".")[0])
    if callers != {"Npc_Hylia_047_Child"}:
        raise BuildError(f"SimpleShopRoot_3Choices is also used by {sorted(callers)}")
    d.update(file="Npc_Hylia_047_Child", give_reward_id="event/SimpleShop/SimpleShop/Event182/ReveiveItem")
    return d


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    data = {"_about": __doc__.strip().splitlines()[0], "flags": FLAGS,
            "egg": egg_data(fs, romfs), "letter": letter_data(fs, romfs), "mask_shop": mask_shop_data(fs, romfs),
            "beans": bean_data(fs, romfs)}
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"{len(data['mask_shop']['slots'])} mask slots, egg/letter/bean steps -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except BuildError as e:
        sys.exit(f"build error: {e}")
