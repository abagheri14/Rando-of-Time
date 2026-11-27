"""Shop shelves (OoT Randomizer's shopsanity), Business Scrubs (shuffle_scrubs) and the expensive merchants for the
remake. The merchants are shuffle_expensive_merchants. The generator uses this through tools/rando/parity/shops.py.

usage:
  python tools/rando/shops.py build ROMFS                 writes data/rando/shop_map.json, prints a summary
  python tools/rando/shops.py plan ASSIGN.json OUT.json   {OoTR location: [OoTR item, price]} -> plan sections

API (data: data/rando/shop_map.json, made by build):
  sellable(item, kind)            remake actor for a shelf ("shop") or scene ("scrub") sale, or None
  item_allowed(location, item)    use as an OoTR item rule on shop/scrub/merchant locations; why_not() says why
  extra_rule(location)            the rule the remake adds (also in data/rando/logic/shops.json)
  lock_vanilla(world, ItemFactory)  before the fill: lock the shop slots and scrubs kept vanilla with OoTR's pool items
  install_fill_guard()            before the fill: OoTR's last junk pass gives patched slots only items they can sell
  repair_special_deals(world)     after the fill instead: swap unsellable junk out of patched slots
  plan_ops(assignments)           {location: (item, price)} -> {"packs", "placements", "events", "text", "_notes"}

Merchants. The Wasteland carpet salesman sells through SimpleShop:SimpleShopRoot {ActorName, Price}. Only that
sale sets the flag Npc_Hylia_044_Buy, and his flow already branches on it, so the "sold" branch now ends the talk
instead of selling again. Medigoron and Granny are sold by the songs/trade plugin (mode "plugin"). The bean
salesman stays vanilla (MERCHANTS says why).

Shops. What a slot sells and its price come from the shopkeeper's ShopParam GoodsList[i] (Actor, PriceOffset,
StockNum, Release). The shelf placement with ShopItemIndex i only shows it. So a slot is changed in both places:
  - GoodsList[i] in every pack copy of every list the shop uses (child and adult shopkeepers often share a file);
  - the shelf placement's Gyaml in every level file that holds that shelf (child, adult, alternative stages).
Only Shop_* actors can stand on a shelf (no Hookshot, Bow, rupees... exist as one), so a shelf sells only OoTR
items that have one (SHELF): shields, tunics, ammo and bomb bundles, bombchus, recovery hearts, bottle refills.
All of them are harmless to buy twice, and that's the "bought once" guard for shops. The game's sold-out counters
restock daily and count per shopkeeper actor, so they can't be trusted with a one-time item. By default a shelf
only takes a Shop_* type its level already places (a type new to a level broke Kokiri Forest once).
Child and adult remake shops line up with OoTR like this. The KF, GC and ZD shops are one list shared by every
age's shopkeeper (one OoTR shop each). Market Bazaar is the child bazaar and Kak Bazaar the adult bazaar (own
list). The Market and Kak Potion Shops share ONE list file in the remake (the adult keeper's ActorParam inherits
the child's ShopRef), so both stay vanilla unless the remake setting remake_split_potion_shops is on
(split_potion_shops, the parity plugin's). Then the Kakariko keeper gets its own list, a new file in its own pack
(Component/ShopParam/Npc_Hylia_020_Shop_Adult..., made from the shared list, and make_patch "new_from" gives it
a size-table entry), and its ActorParam's ShopRef points at it, as vanilla does for the Kakariko Bazaar keeper
(Npc_Hylia_018_Shop_Adult's own ShopRef and list). Both potion shops then take shopsanity items like the others.
The mask shop isn't part of shopsanity.

Scrubs. The one-time scrubs sell through Enemy_Scrub_Business_Common. The placement's
ScrubBusiness_ShopItemActorName0 is only a key that picks a branch in SimpleShopRoot_Enemy_Scrub_Business_Pouch
(or the HF scrub's Secret flow). The branch calls SimpleShopSub_Scrub_Business_OneTime {ActorName, Price,
SellerMessageId}, which charges SimpleShop_Price and hands the item over. That works for any pouch item, the
boss-rush scrubs sell the Longshot, boots, magic and swords this way. A location is changed by editing those
sale calls in place and routing its branch through a new check of the location's own vanilla "sold" flag (set by
the scene after a sale). That's the "bought once" guard, and it covers every copy of the scrub (child/adult,
KF/LW banc). These four locations keep their vanilla sale calls (one per tier).
Menu scrubs (repeat sales) and the two remake-only scrubs (CONVERTED) are made one-time sellers when
shuffle_scrubs is on. Their placements play the one-time row with a key of their own, and new sale steps are
copies of the heart-piece sale call, one per tier (an evfl_build copy keeps the call's Enemy_Scrub_Business
actor argument). OoTR scrubs the remake doesn't have are mode "absent" (out of logic in
data/rando/logic/shops.json).
"""
import copy
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
# The app sets REMAKE_ROMFS. This module reads the vanilla scene routing for ice-trap sales from it.
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
OUT = os.path.join(HERE, "data", "rando", "shop_map.json")
VANILLA = os.path.join(HERE, "original")
ITEM_MAP = json.load(open(os.path.join(HERE, "config", "item_map.json"), encoding="utf-8"))
PROGRESSIVE = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]

SCRUB_SCENE = "Enemy_Scrub_Business_Common"
SCRUB_ROOT = "SimpleShopRoot_Enemy_Scrub_Business_Pouch"
SCRUB_SALE = "SimpleShopSub_Scrub_Business_OneTime"
# A patched scrub doesn't say what it sells, same as OoTR's scrubs. In every language the game ships, its first line
# is the scrubs' line for an unnamed item (MYSTERY_LINE, "I'll sell ya something special!"), then that language's
# lead-in to the price, taken from its scrub offers (PRICE_LEAD), and then the offer's price and question.
# Where the game's words don't fit after that line we use our own (OWN_WORDS, listed so they can be reviewed).
TEXT_LANGS = ("CNzh", "EUde", "EUen", "EUes", "EUfr", "EUit", "EUnl", "EUpl", "EUru", "JPja", "KRko", "TWzh", "USen",
              "USes", "USfr", "USpt")
MYSTERY_LINE = "Enemy_Scrub_Business_Greeting_06"  # in EventFlowMsg/Enemy_Event.msbt, where the seller lines live
PRICE_LEAD = {
    "USen": "It's", "EUen": "It's",            # Enemy_Scrub_Business_Heart_01
    "EUde": "Kostet nur",                      # Heart_01
    "EUes": "Vale", "USes": "Vale",            # DekuStickPouch_01 / DekuNutsPouch_01
    "EUfr": "Ça coûte", "USfr": "Ça coûte",  # ours, the game's "Il coûte" is about the bag
    "EUit": "Costa",                           # Heart_01
    "EUnl": "Het kost maar",                   # ours, the game's "Hij kost maar" is about the bag
    "EUpl": "Kosztuje tylko",                  # Heart_01
    "EUru": "", "JPja": "",                    # Heart_01, the line starts with the price
    "KRko": "가격은",              # ours ("the price is"), the game's pattern is "<item>은"
    "CNzh": "价格是", "TWzh": "價格是",  # Heart_01 / DekuStickPouch_01
    "USpt": "Custa",                           # Heart_01
}
NO_SPACE = ("CNzh", "TWzh", "JPja")  # no space between the lead-in and the price (Korean has one)
# the offer's question after the price uses the vanilla item's gender, but "algo especial" is masculine
QUESTION_FIX = {lang: (("¿Te la quedas", "¿Te lo quedas"), ("¿La quieres?", "¿Lo quieres?"))
                for lang in ("EUes", "USes")}
OWN_WORDS = {"EUfr": "Ça coûte", "USfr": "Ça coûte", "KRko": "가격은", "EUnl": "Het kost maar",
             "EUes": "¿Te lo quedas / ¿Lo quieres?", "USes": "¿Te lo quedas / ¿Lo quieres?"}
MAX_PRICE = 999

# OoTR item -> the Shop_* actor that sells it on a shelf (bundle sizes read from the packs, see build()).
SHELF = {
    "Buy Deku Shield": "Shop_Weapon_Shield_Deku", "Deku Shield": "Shop_Weapon_Shield_Deku",
    "Buy Hylian Shield": "Shop_Weapon_Shield_Hylian", "Hylian Shield": "Shop_Weapon_Shield_Hylian",
    "Buy Goron Tunic": "Shop_Armor_Goron", "Goron Tunic": "Shop_Armor_Goron",
    "Buy Zora Tunic": "Shop_Armor_Zora", "Zora Tunic": "Shop_Armor_Zora",
    "Buy Heart": "Shop_Heart", "Recovery Heart": "Shop_Heart",
    "Buy Deku Nut (5)": "Shop_DekuNutBundle_01", "Deku Nuts (5)": "Shop_DekuNutBundle_01",
    "Buy Deku Nut (10)": "Shop_DekuNutBundle_02", "Deku Nuts (10)": "Shop_DekuNutBundle_02",
    "Buy Deku Stick (1)": "Shop_DekuStick", "Deku Stick (1)": "Shop_DekuStick",
    "Buy Deku Seeds (30)": "Shop_DekuSeedBundle_01", "Deku Seeds (30)": "Shop_DekuSeedBundle_01",
    "Buy Arrows (10)": "Shop_ArrowBundle_01", "Arrows (10)": "Shop_ArrowBundle_01",
    "Buy Arrows (30)": "Shop_ArrowBundle_02", "Arrows (30)": "Shop_ArrowBundle_02",
    "Buy Arrows (50)": "Shop_ArrowBundle_03",
    "Buy Bombs (5) for 25 Rupees": "Shop_BombBundle_01", "Buy Bombs (5) for 35 Rupees": "Shop_BombBundle_01",
    "Bombs (5)": "Shop_BombBundle_01",
    "Buy Bombs (10)": "Shop_BombBundle_02", "Bombs (10)": "Shop_BombBundle_02",
    "Buy Bombs (20)": "Shop_BombBundle_03", "Bombs (20)": "Shop_BombBundle_03",
    "Buy Bombs (30)": "Shop_BombBundle_04",
    "Buy Bombchu (5)": "Shop_BombchuBundle_05", "Bombchus (5)": "Shop_BombchuBundle_05",
    "Buy Bombchu (10)": "Shop_BombchuBundle_01", "Bombchus (10)": "Shop_BombchuBundle_01",
    "Buy Bombchu (20)": "Shop_BombchuBundle_02", "Bombchus (20)": "Shop_BombchuBundle_02",
    "Buy Green Potion": "Shop_Bottle_GreenPotion", "Buy Blue Fire": "Shop_Bottle_BlueFire",
    "Buy Red Potion for 30 Rupees": "Shop_Bottle_RedPotion", "Buy Red Potion for 40 Rupees": "Shop_Bottle_RedPotion",
    "Buy Red Potion for 50 Rupees": "Shop_Bottle_RedPotion", "Buy Fairy's Spirit": "Shop_Bottle_Fairy",
    "Buy Bottle Bug": "Shop_Bottle_Bug", "Buy Fish": "Shop_Bottle_Fish", "Buy Poe": "Shop_Bottle_Poe",
}
# These have a Shop_* actor but don't go on shelves:
#   - masks, they have their own borrow/sell flow (DisplayShop Root_HappyMaskShop)
#   - bottle refills as OoTR "Bottle with X" items, since a refill isn't a bottle
#   - Arrows (5), there's no 5-arrow bundle
# Masks are only listed here so we can pair the vanilla mask shop's slots in shop_map.json.
PAIR_ONLY = {"Keaton Mask": "Shop_Mask_Keaton", "Skull Mask": "Shop_Mask_Skull", "Spooky Mask": "Shop_Mask_Spooky",
             "Bunny Hood": "Shop_Mask_Bunny", "Goron Mask": "Shop_Mask_Goron", "Zora Mask": "Shop_Mask_Zora",
             "Gerudo Mask": "Shop_Mask_Gerudo", "Mask of Truth": "Shop_Mask_Truth"}

# Items the remake won't sell at one age. DisplayShop NotAvailableTalk has an adult-only answer for the Deku Shield
# (messages Shop_01_Shield_Adult_02_*), read from the files. Tunics for a child aren't verified, so we treat them as
# adult-only. OoTR's rule for "Buy ... Tunic" adds is_adult, and its special-deal tunics rely on a code patch we
# don't have.
AGE_GATE = {"Shop_Weapon_Shield_Deku": "child", "Shop_Armor_Goron": "adult", "Shop_Armor_Zora": "adult"}
# Shelf buys that the shop scene gates on another item (DisplayShop SelectItem_CheckAvailable, read from the files).
# Only junk uses these actors so logic doesn't care, plan_ops just notes them.
SCENE_GATE = {"Shop_DekuSeedBundle_01": "IsGet.Item_BulletBag_Small", "Shop_DekuSeedBundle_02": "IsGet.Item_BulletBag_Small",
              "Shop_ArrowBundle_01": "IsGet.Item_Quiver_Small", "Shop_ArrowBundle_02": "IsGet.Item_Quiver_Small",
              "Shop_ArrowBundle_03": "IsGet.Item_Quiver_Small", "Shop_BombBundle_01": "Get_StoneOfFire_IsCompleted_Exp",
              "Shop_BombBundle_02": "Get_StoneOfFire_IsCompleted_Exp", "Shop_BombBundle_03": "Get_StoneOfFire_IsCompleted_Exp",
              "Shop_BombBundle_04": "Get_StoneOfFire_IsCompleted_Exp"}

# OoTR shop -> remake shopkeeper actors (every age and stage), the ages that reach it, an extra OoTR rule.
SHOPS = {
    "KF Shop": {"npcs": ["Npc_Kokiri_001_Shop_Child", "Npc_Kokiri_001_Shop_Child_ShortStock", "Npc_Kokiri_001_Shop_Adult"],
                "ages": "both"},
    "GC Shop": {"npcs": ["Npc_Goron_011_Shop_Child", "Npc_Goron_011_Shop_Adult"], "ages": "both"},
    "ZD Shop": {"npcs": ["Npc_Zora_011_Shop_Child", "Npc_Zora_011_Shop_Adult"], "ages": "both"},
    "Market Bazaar": {"npcs": ["Npc_Hylia_018_Shop_Child"], "ages": "child"},
    "Kak Bazaar": {"npcs": ["Npc_Hylia_018_Shop_Adult"], "ages": "adult"},
    "Market Bombchu Shop": {"npcs": ["Npc_Hylia_021_Shop_Child"], "ages": "child",
                            "requires": "'Defeat King Dodongo'",
                            "requires_why": "the shopkeeper's placement has Presence Get_StoneOfFire_IsCompleted_Exp "
                                            "(Goron Ruby stage done; world_settings.BOSS_EVENT)"},
    "Market Potion Shop": {"npcs": ["Npc_Hylia_020_Shop_Child"], "ages": "child",
                           "vanilla": "the child and adult potion shopkeepers read the same list file "
                                      "(Component/ShopParam/Npc_Hylia_020_Shop): Market and Kak can't differ"},
    "Kak Potion Shop": {"npcs": ["Npc_Hylia_020_Shop_Adult"], "ages": "adult",
                        "vanilla": "shares its list file with the Market Potion Shop"},
    "Market Mask Shop": {"npcs": ["Npc_Hylia_023_Shop_Child"], "ages": "child",
                         "vanilla": "not part of OoTR's shopsanity (MaskShop locations): the songs_trade plugin "
                                    "gives the shuffled masks' slots (tools/rando/parity/_songs_trade_child.py)",
                         "plugin": "songs_trade"},
}
SPECIAL_DEAL_SLOTS = ("7", "5", "8", "6")  # OoTR World.random_shop_prices takes the first N of these per shop

# OoTR scrub location -> remake one-time scrub. "row" is the EventSetting row its placements' TalkEventName names,
# "key" picks its branch in SCRUB_ROOT (None means it has its own flow, the "Secret" one for HF).
SCRUBS = {
    "LW Deku Scrub Near Bridge": {"row": "Enemy_Scrub_Business_DekuStickPouch_01", "key": "Item_StickBag_Medium"},
    "LW Deku Scrub Grotto Front": {"row": "Enemy_Scrub_Business_DekuNutsPouch_01", "key": "Item_NutBag_Medium"},
    "DMC Deku Scrub": {"row": "Enemy_Scrub_Business_Heart_02", "key": "Obj_Heart_Piece", "setting": "shuffle_scrubs",
                       "note": "OoTR's DMC scrub sells bombs; the remake's sells a heart piece once: only randomized "
                               "when shuffle_scrubs is on, else the remake keeps its heart piece (not in OoTR logic)"},
    "HF Deku Scrub Grotto": {"row": "Enemy_Scrub_Business_Heart_01", "key": None,
                             "requires": "is_child",
                             "requires_why": "Secret flow: an adult Link only gets talk (Event657/Event608 adult "
                                             "branches never reach the sale); OoTR lets both ages buy"},
}


# Menu scrubs (repeat sellers in the remake) that become one-time sellers when shuffle_scrubs is on, plus the two
# remake-only scrubs we add as new OoTR locations (data/rando/logic/shops.json new_locations). Their vanilla is OoTR's
# "Buy Green Potion", the first item on the remake's menu, with default 0x3A so OoTR prices them like its green-potion
# scrubs. Pairing evidence is in data/ootr_match.json "evidence".
#
# Each placement gets TalkEventName Enemy_Scrub_Business_Heart_02 (the one-time pouch root, same as the DMC scrub)
# and a key of its own in ScrubBusiness_ShopItemActorName0, which can be any string no one-time placement uses. The
# root's key chain gets one branch per location that copies the DMC scrub's one-time sale call.
#
# The sold flag is the HavePlayedEvent flag of a scene row that no placement and no event names once every scrub
# using it is converted. They all get converted together whenever shuffle_scrubs is on. None means the only guard is
# the scrub dying after the sale, which is how the game's one-time scrubs work too (the scene's location flags are
# just map icons).
#
# vanilla_stand_in: with shuffle_scrubs off OoTR puts its vanilla "Buy" item there. Where the remake scrub doesn't
# sell it and the item counts in logic (Sticks, Nuts), the plugin swaps in this logic-free item.
CONVERTED = {
    "LW Deku Scrub Grotto Rear": {"hashes": ["2214083465643671502", "14619830301496284497"],
                                  "key": "Item_Bottle_RedPotion", "flag_row": "Enemy_Scrub_Business_Arrow_01"},
    "LW Deku Scrub Near Deku Theater Left": {"hashes": ["2569517939889411425"], "key": "Item_Bottle_Bug",
                                             "flag_row": "Enemy_Scrub_Business_Item_SellBug",
                                             "vanilla_stand_in": "Buy Green Potion"},
    "LW Deku Scrub Near Deku Theater Right": {"hashes": ["15048088372638595204", "11385057993574159532"],
                                              "key": "Item_Bottle_GreenPotion", "flag_row": "Enemy_Scrub_Business_Potion",
                                              "vanilla_stand_in": "Buy Red Potion for 30 Rupees"},
    "LLR Deku Scrub Grotto Left": {"hashes": ["17418042722045679657"], "key": "Shop_DekuNutBundle_01",
                                   "flag_row": "Enemy_Scrub_Business_DekuNuts_01"},
    "LLR Deku Scrub Grotto Center": {"hashes": ["12901354557574090016"], "key": "Shop_DekuSeedBundle_01",
                                     "flag_row": "Enemy_Scrub_Business_DekuSeed_01"},
    "LLR Deku Scrub Grotto Right": {"hashes": ["16672855544778411393"], "key": "Shop_BombBundle_01",
                                    "flag_row": "Enemy_Scrub_Business_Bomb_01"},
    "Dodongos Cavern Deku Scrub Side Room Near Dodongos": {"hashes": ["7388739057158296701"],
                                                           "key": "Shop_Weapon_Shield_Deku",
                                                           "flag_row": "Enemy_Scrub_Business_Item",
                                                           "vanilla_stand_in": "Buy Green Potion"},
    "Jabu Jabus Belly Deku Scrub": {"hashes": ["9496373148524757782"], "key": "Shop_Heart_Bundle", "flag_row": None,
                                    "vanilla_stand_in": "Buy Green Potion"},
    "Bottom of the Well Deku Scrub": {"hashes": ["15945446340598299551"], "key": "Obj_MagicJar_Small",
                                      "flag_row": "Enemy_Scrub_Business_GreenPotion_01", "new": "Buy Green Potion"},
    "Shadow Temple Deku Scrub": {"hashes": ["8721287453021850502"], "key": "Shop_ArrowBundle_01", "flag_row": None,
                                 "new": "Buy Green Potion"},
}
CONVERTED_ROW = "Enemy_Scrub_Business_Heart_02"  # the one-time row every converted placement uses
HEART_KEY = "Obj_Heart_Piece"  # the DMC scrub's key, its row only sets the after-sale flag for this key


# OoTR merchant location -> remake scene, or why it stays vanilla. OoTR gives these locations no price
# (location.price is None), so they sell at the vanilla OoT price and that's what we use here: Medigoron 200,
# carpet 200, Granny 100, beans 60. Those come from OoTR's setting tooltips and its Progressive_Wallet rules.
MERCHANTS = {
    "Wasteland Bombchu Salesman": {"scene": "Npc_Hylia_044_Adult", "sold_flag": "Npc_Hylia_044_Buy", "price": 200,
                                   "setting": "shuffle_expensive_merchants",
                                   "requires": "is_adult", "requires_why": "only Npc_Hylia_044_Adult sells (the child "
                                                                           "file's Npc_Hylia_044_Child has no sale)"},
    # The songs/trade plugin sells these once on a spare save flag (tools/rando/parity/_songs_trade_npcs.py).
    # They have no sold flag. Medigoron checks the pouch for a sword and Granny sells into an empty bottle after a
    # trade step.
    "GC Medigoron": {"price": 200, "plugin": "songs_trade",
                     "why": "no flag records his sale (he checks the pouch for the Giant's Knife or Biggoron's "
                            "Sword): the songs_trade plugin sells his item once on a spare save flag"},
    "Kak Granny Buy Blue Potion": {"price": 100, "plugin": "songs_trade",
                                   "why": "a repeat sale into an empty bottle (GetInEventInBottle_BlueBottleShop), no "
                                          "sold flag, gated by the Biggoron trade steps: the songs_trade plugin "
                                          "sells her item once on a spare save flag, no bottle needed"},
    "ZR Magic Bean Salesman": {"price": 60, "plugin": "songs_trade",
                               "why": "shuffle_beans: the songs_trade plugin makes him sell one item once for 60 "
                                      "rupees (tools/rando/parity/_songs_trade_child.py); OoTR's 'Magic Bean Pack' "
                                      "(10 beans) is given by a scene that adds 10 beans"},
}


class ShopError(Exception):
    pass


# Reading the game
def _plain(v):
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return float(v)
    return str(v)


# The Kokiri Shop has a short stock until Mido moves the forest story on (Meet_DekuTree_IsAfter_Step02_Exp). That's
# a separate short-stock keeper (Npc_Kokiri_001_Shop_Child_ShortStock) with a few shelves and five "sold out" boards,
# standing in front of the full keeper and shelves, each one switched by its placement's Presence.
# With open_forest 'open' Mido might never get to that step, so a shuffled slot could never be bought. So when any KF
# Shop slot is patched we show the full stock from the start. The full stock's Presence is removed and the short
# stock's is made never true in its level (Sequence_IsChildhood negated in child files, plain in adult files).
KF_STOCK_GATE = "Meet_DekuTree_IsAfter_Step02_Exp"


def stock_gate_ops(game, area, flag):
    """Placement ops that show a shop's full stock from the start (see KF_STOCK_GATE)."""
    d = os.path.join(game.romfs, "Banc", area)
    ops = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".bcett.byml.zs"):
            continue
        rel = f"Banc/{area}/{fn}"
        for a in game.byml(rel).get("Actors", []) or []:
            g, pres = str(a.get("Gyaml", "")), a.get("Presence") or {}
            if pres.get("FlagName") != flag or not (g.startswith("Shop_") or g.startswith("Npc_Kokiri_001_Shop")):
                continue
            h = str(int(a["Hash"]))
            if not pres.get("IsNegation"):
                ops.append({"file": rel, "hash": h, "remove": ["Presence"], "note": f"{g}: shown from the start"})
            else:
                ops.append({"file": rel, "hash": h, "note": f"{g}: never shown",
                            "set": {"Presence.FlagName": "Sequence_IsChildhood", "Presence.IsCheckLazy": False,
                                    "Presence.IsNegation": "_Child_" in fn}})
    return ops


class Game:
    def __init__(self, romfs):
        from romtools import Romfs
        self.romfs = romfs
        self.fs = Romfs(romfs, VANILLA)
        self._packs = {}

    def pack(self, actor):
        from romtools import sarc_files
        if actor not in self._packs:
            self._packs[actor] = sarc_files(self.fs.read(f"Pack/Actor/{actor}.pack.zs"))
        return self._packs[actor]

    def byml(self, rel):
        from romtools import byml_load
        return byml_load(self.fs.read(rel))[0]

    def actors(self):
        d = os.path.join(self.romfs, "Pack", "Actor")
        return sorted(f[:-len(".pack.zs")] for f in os.listdir(d) if f.endswith(".pack.zs"))

    def resolve(self, files, path):
        """A BYML file inside a pack, merged over its $parent chain (parents found in the same pack)."""
        from romtools import byml_load
        chain, p = [], path
        while p:
            if p not in files:
                break
            d = byml_load(files[p])[0]
            chain.append(d)
            par = d.get("$parent")
            p = None
            if par:
                p = par.replace("Work/", "", 1).rsplit(".gyml", 1)[0] + ".bgyml"
        out = {}
        for d in reversed(chain):
            for k, v in d.items():
                if k == "Components" and isinstance(v, dict):
                    out.setdefault("Components", {}).update(v)
                elif k != "$parent":
                    out[k] = v
        return out

    def actor_param(self, actor):
        files = self.pack(actor)
        return files, self.resolve(files, f"Actor/{actor}.engine__actor__ActorParam.bgyml")


def _ref(v):
    return (v or "").lstrip("?") or None


def shop_actor_info(game, actor):
    """Price, bundle size and pouch item of a Shop_* actor, read from its pack."""
    files, ap = game.actor_param(actor)
    comp = ap.get("Components", {})
    info = {"price": None, "count": None, "pouch": None, "bundle": None}
    gpt = _ref(comp.get("GameParameterTableRef"))
    if gpt:
        table = game.resolve(files, gpt)
        pp = _ref((table.get("Components") or {}).get("PriceParam"))
        if pp and pp in files:
            info["price"] = int(game.resolve(files, pp).get("BuyingPrice"))
            info["price_param"] = pp
    pc = _ref(comp.get("PouchContentRef"))
    if pc:
        pouch = game.resolve(files, pc)
        if pouch.get("IsBundle"):
            info["bundle"] = (pouch.get("BundleActor") or "").split("/")[-1].split(".")[0]
            info["count"] = int(pouch.get("BundleActorNum") or 1)
        info["pouch"] = (pouch.get("PouchActor") or "").split("/")[-1].split(".")[0] or None
    return info


def _stage(rel):
    return re.sub(r"_(Static|Dynamic)\.bcett\.byml\.zs$", "", os.path.basename(rel))


def banc_files(game):
    banc = os.path.join(game.romfs, "Banc")
    for area in sorted(os.listdir(banc)):
        p = os.path.join(banc, area)
        if not os.path.isdir(p):
            continue
        for fn in sorted(os.listdir(p)):
            if fn.endswith(".bcett.byml.zs"):
                yield f"Banc/{area}/{fn}"


def _event_index(ev):
    fc = ev.flowcharts[0]
    return fc, {e["name"]: e for e in fc["events"]}


def _param(e, name):
    it = ((e.get("params") or {}).get("items") or {}).get(name)
    return None if it is None else it.get("value")


def _reach(fc, start):
    """Events reachable from index `start` inside one flowchart, not following sub-flow calls into entries."""
    seen, order, stack = set(), [], [start]
    while stack:
        i = stack.pop(0)
        if i in seen or i >= len(fc["events"]):
            continue
        seen.add(i)
        e = fc["events"][i]
        order.append(e)
        nxt = [e[k] for k in ("next", "join") if k in e] + [c["next"] for c in e.get("cases", [])] + e.get("forks", [])
        stack += nxt
    return order


def _action(fc, e):
    a = fc["actors"][e["actor"]]
    return a["name"], (a["actions"][e["action"]] if e["type"] == "action" else a["queries"][e["query"]])


def gamedata_names(game, names):
    """Which of these save-data names exist (GameDataList, murmur3 keys)."""
    from romtools import byml_load, murmur3_32
    root = byml_load(game.fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    have = set()
    for table, entries in root["Data"].items():
        if table == "Bool64bitKey":
            continue
        for e in entries:
            have.add(int(e["Hash"]))
    return {n: murmur3_32(n) in have for n in names}


# Build
def build(romfs):
    """Pairs OoTR's shop slots and scrubs with the remake's edit points and writes data/rando/shop_map.json."""
    from evfl import Evfl
    import msbt
    game = Game(romfs)
    match = {x["ootr"]: x for x in json.load(open(os.path.join(HERE, "data", "ootr_match.json"),
                                                  encoding="utf-8"))["ootr_locations"]}
    from_ootr = _ootr_tables()
    out = {"_about": __doc__.strip().splitlines()[0] + " Built by tools/rando/shops.py build; see its docstring.",
           "shop_actors": {}, "stage_shop_types": {}, "shop_lists": {}, "locations": {}}

    # Shop_* actors: price, bundle size
    shop_types = [a for a in game.actors() if a.startswith("Shop_")]
    for a in shop_types:
        if a.startswith(("Shop_Board", "Shop_Item_Base")):
            continue
        out["shop_actors"][a] = shop_actor_info(game, a)

    # shopkeeper lists, which file each shopkeeper reads and every pack that has a copy of it
    npc_packs = [a for a in game.actors() if a.startswith("Npc_") and "Shop" in a]
    copies = defaultdict(list)
    for a in npc_packs:
        for name in game.pack(a):
            if name.startswith("Component/ShopParam/"):
                copies[name].append(a)
    npc_list = {}
    for shop, d in SHOPS.items():
        for npc in d["npcs"]:
            files, ap = game.actor_param(npc)
            ref = _ref(ap.get("Components", {}).get("ShopRef"))
            if not ref or ref not in files:
                raise ShopError(f"{npc}: no ShopRef list in its pack")
            npc_list[npc] = ref
            if ref not in out["shop_lists"]:
                # read it as written, a list with $parent (KF ShortStock, Kak Bazaar) spells out all 8 entries itself
                from romtools import byml_load
                own = byml_load(files[ref])[0]
                goods = own.get("GoodsList")
                if not isinstance(goods, list) or len(goods) != 8:
                    raise ShopError(f"{ref}: GoodsList is not 8 entries")
                out["shop_lists"][ref] = {"parent": (own.get("$parent") or "").split("/")[-1] or None,
                                          "packs": sorted(copies[ref]), "goods": _plain(goods), "used_by": []}
            out["shop_lists"][ref]["used_by"].append(npc)

    # shelves: each shopkeeper placement's ForSale links, per level file
    shelves = defaultdict(lambda: defaultdict(list))  # npc -> slot -> [shelf]
    stage_types = defaultdict(set)
    all_npcs = {n for d in SHOPS.values() for n in d["npcs"]}
    for rel in banc_files(game):
        root = game.byml(rel)
        acts = {int(a["Hash"]): a for a in root.get("Actors", []) or []}
        for a in acts.values():
            g = a.get("Gyaml", "")
            if g.startswith("Shop_"):
                stage_types[_stage(rel)].add(g)
        for a in acts.values():
            if a.get("Gyaml") not in all_npcs:
                continue
            for link in a.get("Links", []) or []:
                if link.get("Name") != "ForSale":
                    continue
                s = acts.get(int(link["Dst"]))
                if s is None:
                    raise ShopError(f"{rel}: {a['Gyaml']} sells {link['Dst']}, not in the same file")
                slot = int((s.get("Dynamic") or {}).get("ShopItemIndex", 0))
                boards = []
                for bl in s.get("Links", []) or []:
                    b = acts.get(int(bl["Dst"]))
                    if b is not None and str(b.get("Gyaml", "")).startswith("Shop_Board"):
                        boards.append({"hash": str(int(b["Hash"])), "gyaml": b["Gyaml"]})
                shelves[a["Gyaml"]][slot].append({"file": rel, "hash": str(int(s["Hash"])), "gyaml": s["Gyaml"],
                                                  "stage": _stage(rel), "npc_hash": str(int(a["Hash"])),
                                                  "presence": _plain(s.get("Presence")), "boards": boards})
    out["stage_shop_types"] = {k: sorted(v) for k, v in sorted(stage_types.items())}

    # every vanilla shelf shows what its list sells in that slot
    for npc, slots in shelves.items():
        goods = out["shop_lists"][npc_list[npc]]["goods"]
        for slot, ss in slots.items():
            want = goods[slot]["Actor"].split("/")[-1].split(".")[0]
            for s in ss:
                if s["gyaml"] != want:
                    raise ShopError(f"{s['file']}: shelf {s['hash']} shows {s['gyaml']}, list slot {slot} sells {want}")

    # shops: OoTR slot -> remake list slot, paired by vanilla item first, the rest in order
    for shop, d in SHOPS.items():
        names = [f"{shop} Item {k}" for k in range(1, 9)]
        lists = sorted({npc_list[n] for n in d["npcs"]})
        main = npc_list[d["npcs"][0]]
        goods = [g["Actor"].split("/")[-1].split(".")[0] for g in out["shop_lists"][main]["goods"]]
        for ref in lists:  # every list of one shop sells the same actor in each slot
            other = [g["Actor"].split("/")[-1].split(".")[0] for g in out["shop_lists"][ref]["goods"]]
            if other != goods:
                raise ShopError(f"{shop}: lists {main} and {ref} differ ({goods} vs {other})")
        pair, free = {}, list(range(8))
        for n in names:
            want = SHELF.get(from_ootr["vanilla"][n]) or PAIR_ONLY.get(from_ootr["vanilla"][n])
            j = next((j for j in free if goods[j] == want), None)
            if j is not None:
                pair[n] = (j, "same vanilla item")
                free.remove(j)
        for n in names:
            if n not in pair:
                pair[n] = (free.pop(0), "slot left over after pairing by item (contents differ)")
        for n in names:
            j, how = pair[n]
            edit = {"shop": shop, "slot": j, "remake_vanilla": goods[j],
                    "lists": [{"pack": f"Pack/Actor/{p}.pack.zs", "file": ref, "index": j,
                               "vanilla": out["shop_lists"][ref]["goods"][j]}
                              for ref in lists for p in out["shop_lists"][ref]["packs"]],
                    "shelves": [s for npc in d["npcs"] for s in shelves[npc].get(j, [])],
                    "ages": d["ages"], "special_deal_slot": n.rsplit(" ", 1)[1] in SPECIAL_DEAL_SLOTS}
            if d.get("requires"):
                edit["requires"] = d["requires"]
                edit["requires_why"] = d["requires_why"]
            entry = {"mode": "plugin" if d.get("plugin") else "vanilla" if d.get("vanilla") else "full",
                     "kind": "shop", "edit": edit,
                     "vanilla": from_ootr["vanilla"][n], "vanilla_price": from_ootr["price"].get(n),
                     "why": d.get("vanilla") or f"{how}; remake slot {j} of {main.split('/')[-1].split('.')[0]}",
                     "ootr_match": match.get(n, {}).get("status")}
            out["locations"][n] = entry

    # scrubs
    raw = game.fs.read(f"Event/EventFlow/{SCRUB_SCENE}.bfevfl.zs")
    ev = Evfl(raw)
    fc, by_name = _event_index(ev)
    rows = {r["__RowId"]: r for r in game.byml("RSDB/EventSetting.Product.111.rstbl.byml.zs")}
    scrub_place = defaultdict(list)
    for rel in banc_files(game):
        if "/DreamWorld/" in rel:
            continue
        for a in game.byml(rel).get("Actors", []) or []:
            if a.get("Gyaml") == "Enemy_Scrub_Business":
                dyn = a.get("Dynamic") or {}
                scrub_place[dyn.get("TalkEventName")].append(
                    {"file": rel, "hash": str(int(a["Hash"])), "key": dyn.get("ScrubBusiness_ShopItemActorName0"),
                     "attacked": dyn.get("AttackedEventName")})
    flags = {}
    for name, d in SCRUBS.items():
        row = rows[d["row"]]
        entry = row["EntryPointName"]
        if not row["FlowchartFileName"].endswith(f"{SCRUB_SCENE}.evfc"):
            raise ShopError(f"{d['row']}: not a {SCRUB_SCENE} scene")
        eps = fc["entry_points"]
        # the location's "sold" flag, which its entry sets after ScrubBusiness_BuySuccess
        flag = None
        for e in _reach(fc, eps[entry]["main"]):
            if e["type"] == "action" and _action(fc, e) == ("GameDataActor", "EventTriggerSetGameDataBool") \
                    and _param(e, "Value") is True and _param(e, "GameDataName") != "ScrubBusiness_BuySuccess":
                flag = _param(e, "GameDataName")
        if not flag:
            raise ShopError(f"{name}: no sold flag in entry {entry}")
        flags[name] = flag
        if d["key"]:
            root_ev = _reach(fc, eps[SCRUB_ROOT]["main"])
            branch = next(e for e in root_ev if e["type"] == "switch"
                          and _action(fc, e) == ("GameDataActor", "EventQueryIsGameDataString64")
                          and _param(e, "GameDataName") == "Scrub_Business_TempItemName_00"
                          and _param(e, "Value") == d["key"])
            # find the key chain's "no key matched" end by following case 1 of the key checks
            e = branch
            while e["type"] == "switch" and _param(e, "GameDataName") == "Scrub_Business_TempItemName_00":
                e = fc["events"][next(c["next"] for c in e["cases"] if c["value"] == 1)]
            no_sale, start = e["name"], fc["events"][next(c["next"] for c in branch["cases"] if c["value"] == 0)]
            route = {"event": branch["name"], "case": 0}
            cont = None
        else:  # HF's Secret flow: check before its first branch, sold goes to the adult's talk-only path
            sec = _reach(fc, eps["Secret"]["main"])
            first = next(e for e in sec if e["type"] == "switch"
                         and _param(e, "GameDataName") == "Enemy_Scrub_Business_Secret_IrregularTalk")
            before = next(e for e in sec if e.get("next") == first["idx"])
            child_q = fc["events"][next(c["next"] for c in first["cases"] if c["value"] == 0)]
            if _action(fc, child_q) != ("Player_Event", "EventQueryPlayerIsChild"):
                raise ShopError("HF Secret flow changed")
            no_sale = fc["events"][next(c["next"] for c in child_q["cases"] if c["value"] == 1)]["name"]
            start, route, cont = sec[0], {"event": before["name"]}, first["name"]
        calls = [e for e in _reach(fc, start["idx"]) if e["type"] == "subflow" and e.get("entry_point") == SCRUB_SALE
                 and not e.get("flowchart")]
        if not calls:
            raise ShopError(f"{name}: no {SCRUB_SALE} call in its branch")
        call_info = [{"event": e["name"], "actor": _param(e, "ActorName"), "price": _param(e, "Price"),
                      "message": _param(e, "SellerMessageId"), "idx": e["idx"]} for e in calls]
        # the location's seller line is the one most of its calls use (the stick scrub's first-visit line, _02, is a
        # long tutorial). Every call we use gets pointed at it, and its text loses the item's name.
        uses = defaultdict(int)
        for c in call_info:
            uses[c["message"]] += 1
        label = max(sorted(uses), key=lambda m: uses[m])
        call_info.sort(key=lambda c: (c["message"] != label, c.pop("idx")))
        texts = {label: {}}
        for lang in TEXT_LANGS:
            arch = msbt.read_archive(game.fs, lang)
            mfile, mlabel = label.split("/", 1)[1].split(":")
            texts[label][lang] = mystery_runs(msbt.Msbt(arch[f"EventFlowMsg/{mfile}.msbt"]), mlabel, lang)
        places = scrub_place[d["row"]]
        if d["key"] and any(p["key"] != d["key"] for p in places):
            raise ShopError(f"{name}: a placement of row {d['row']} has another key")
        edit = {"scene": SCRUB_SCENE, "route": route, "continue": cont, "no_sale": no_sale, "calls": call_info,
                "message": label, "sold_flag": flag, "placements": places, "text": texts,
                "graph": "Rando_" + re.sub(r"\W", "", name.title())}
        for k in ("requires", "requires_why", "setting", "note"):
            if d.get(k):
                edit[k] = d[k]
        out["locations"][name] = {
            "mode": "full", "kind": "scrub", "edit": edit, "vanilla": from_ootr["vanilla"][name],
            "why": f"one-time scrub; row {d['row']}, {len(places)} placement(s), {len(calls)} sale call(s) "
                   f"= at most {len(calls)} tier(s); sold flag {flag}",
            "ootr_match": match.get(name, {}).get("status")}
    missing = [n for n, ok in gamedata_names(game, list(flags.values())).items() if not ok]
    if missing:
        raise ShopError(f"sold flags not in GameDataList: {missing}")

    converted_edits(game, fc, rows, scrub_place, out, match, from_ootr)

    for name, x in match.items():  # every other OoTR scrub is absent from the remake (out of logic) or not driven
        if x["type"] in ("Scrub", "GrottoScrub") and name not in out["locations"]:
            absent = x.get("status") == "absent"
            why = ("absent from the remake: data/rando/logic/shops.json removes it from logic (evidence: "
                   "data/ootr_match.json)" if absent else "no remake scrub" if not x.get("remake") else
                   "a repeat-sale menu scrub in the remake (or none of its own): no one-time sale call to repurpose")
            out["locations"][name] = {"mode": "absent" if absent else "vanilla", "kind": "scrub", "edit": None,
                                      "vanilla": x["vanilla"], "why": why, "ootr_match": x["status"]}

    # merchants
    for name, d in MERCHANTS.items():
        x = match.get(name, {})
        if d.get("plugin"):  # another parity plugin patches it, so no item rule or repair from this module
            out["locations"][name] = {"mode": "plugin", "kind": "merchant", "edit": None, "plugin": d["plugin"],
                                      "vanilla": x.get("vanilla"), "why": d["why"], "ootr_match": x.get("status")}
            continue
        if d.get("vanilla"):
            out["locations"][name] = {"mode": "vanilla", "kind": "merchant", "edit": None, "vanilla": x.get("vanilla"),
                                      "why": d["vanilla"], "ootr_match": x.get("status")}
            continue
        out["locations"][name] = {"mode": "full", "kind": "merchant", "edit": merchant_edit(game, name, d),
                                  "vanilla": x.get("vanilla"), "ootr_match": x.get("status"),
                                  "why": f"{d['scene']}: one sale call; sold flag {d['sold_flag']}"}

    out["stock_gates"] = {"KF Shop": stock_gate_ops(game, "KokiriForest", KF_STOCK_GATE)}

    # remake actor for every OoTR item a scrub could sell, with whether its pack exists
    acts = set(game.actors())
    out["scrub_items"] = {}
    for item in sorted(set(ITEM_MAP["items"]) | set(ITEM_MAP["junk_for"]) | set(PROGRESSIVE) | set(EXTRA_SCRUB_ACTORS)):
        tiers = PROGRESSIVE[item]["tiers"] if item in PROGRESSIVE else [scrub_actor(item)]
        out["scrub_items"][item] = {"tiers": tiers, "exists": all(t in acts for t in tiers)}
    out["ootr_prices"] = from_ootr["item_price"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    _MAP.clear()
    return out


def converted_edits(game, fc, rows, scrub_place, out, match, from_ootr):
    """shop_map entries for CONVERTED, the menu scrubs we make one-time sellers and the remake-only scrubs.
    Each has its placements, key, sold flag and the steps of Enemy_Scrub_Business_Common the plan hooks, all checked
    against the files."""
    import msbt
    eps = fc["entry_points"]
    root_ev = _reach(fc, eps[SCRUB_ROOT]["main"])
    keyq = [e for e in root_ev if e["type"] == "switch"
            and _action(fc, e) == ("GameDataActor", "EventQueryIsGameDataString64")
            and _param(e, "GameDataName") == "Scrub_Business_TempItemName_00"]
    first = next(e for e in keyq if _param(e, "Value") == HEART_KEY)
    e, last = first, None
    while e["type"] == "switch" and _param(e, "GameDataName") == "Scrub_Business_TempItemName_00":
        last, e = e, fc["events"][next(c["next"] for c in e["cases"] if c["value"] == 1)]
    no_sale = e["name"]
    sales = [x for x in _reach(fc, next(c["next"] for c in first["cases"] if c["value"] == 0))
             if x["type"] == "subflow" and x.get("entry_point") == SCRUB_SALE and not x.get("flowchart")]
    if len(sales) != 1 or _param(sales[0], "ActorName") != HEART_KEY:
        raise ShopError("Enemy_Scrub_Business_Common: the heart-piece key no longer leads to one heart-piece sale")
    template, label = sales[0], _param(sales[0], "SellerMessageId")
    # the one-time row's entry sets the DMC scrub's location flag after any sale, so keep that for the DMC key only
    row = rows[CONVERTED_ROW]
    entry = _reach(fc, eps[row["EntryPointName"]]["main"])
    success = next(x for x in entry if x["type"] == "switch"
                   and _param(x, "GameDataName") == "ScrubBusiness_BuySuccess")
    flag_step = fc["events"][next(c["next"] for c in success["cases"] if c["value"] == 0)]
    if _action(fc, flag_step) != ("GameDataActor", "EventTriggerSetGameDataBool") \
            or _param(flag_step, "GameDataName") != "DeathMountain_Enemy_Scrub_Business_HeartPiece_01":
        raise ShopError(f"{CONVERTED_ROW}: its after-sale step no longer sets the DMC scrub's flag")
    texts = {label: {}}
    for lang in TEXT_LANGS:
        arch = msbt.read_archive(game.fs, lang)
        mfile, mlabel = label.split("/", 1)[1].split(":")
        texts[label][lang] = mystery_runs(msbt.Msbt(arch[f"EventFlowMsg/{mfile}.msbt"]), mlabel, lang)
    by_hash = {p["hash"]: dict(p, row=r) for r, ps in scrub_place.items() for p in ps}
    keys = [d["key"] for d in CONVERTED.values()]
    one_time = {HEART_KEY, "Item_StickBag_Medium", "Item_NutBag_Medium"}
    if len(set(keys)) != len(keys) or set(keys) & one_time:
        raise ShopError("converted scrub keys must be unique and unused by the game's one-time scrubs")
    freed = defaultdict(set)
    for name, d in CONVERTED.items():
        for h in d["hashes"]:
            p = by_hash.get(h)
            if p is None:
                raise ShopError(f"{name}: no Enemy_Scrub_Business placement {h}")
            if p["row"] in (CONVERTED_ROW, "Enemy_Scrub_Business_DekuStickPouch_01",
                            "Enemy_Scrub_Business_DekuNutsPouch_01", "Enemy_Scrub_Business_Heart_01"):
                raise ShopError(f"{name}: placement {h} is already a one-time scrub ({p['row']})")
            freed[p["row"]].add(h)
    flag_rows = [d["flag_row"] for d in CONVERTED.values() if d["flag_row"]]
    if len(set(flag_rows)) != len(flag_rows):
        raise ShopError("two converted scrubs share a sold flag")
    for r in flag_rows:  # a flag row must lose every placement that plays it (the scenes name none of them)
        if {p["hash"] for p in scrub_place.get(r, [])} != freed.get(r, set()):
            raise ShopError(f"{r}: placements outside CONVERTED still play it; its HavePlayedEvent flag isn't free")
    flags = {r: f"HavePlayedEvent.{r}" for r in flag_rows}
    missing = [n for n, ok in gamedata_names(game, list(flags.values())).items() if not ok]
    if missing:
        raise ShopError(f"converted scrub flags not in GameDataList: {missing}")
    for name, d in CONVERTED.items():
        places = [{"file": by_hash[h]["file"], "hash": h, "row": by_hash[h]["row"],
                   "attacked": bool(by_hash[h]["attacked"]), "vanilla_key": by_hash[h]["key"]} for h in d["hashes"]]
        edit = {"converted": True, "scene": SCRUB_SCENE, "placements": places, "key": d["key"],
                "sold_flag": flags.get(d["flag_row"]), "template": template["name"], "message": label, "text": texts,
                "chain": {"after": last["name"], "case": 1, "no_sale": no_sale},
                "heart_guard": {"event": success["name"], "case": 0, "flag_step": flag_step["name"], "key": HEART_KEY},
                "row": CONVERTED_ROW, "graph": "Rando_ScrubsConverted", "setting": "shuffle_scrubs"}
        if d.get("vanilla_stand_in"):
            edit["vanilla_stand_in"] = d["vanilla_stand_in"]
        x = match.get(name, {})
        out["locations"][name] = {
            "mode": "full", "kind": "scrub", "edit": edit,
            "vanilla": d.get("new") or from_ootr["vanilla"].get(name) or x.get("vanilla"),
            "new_location": bool(d.get("new")),
            "why": ("remake-only scrub (new OoTR location); " if d.get("new") else "menu scrub made one-time; ")
            + f"{len(places)} placement(s) -> {CONVERTED_ROW}, key {d['key']}, sold flag "
            + (flags.get(d["flag_row"]) or "none (the scrub dies after the sale, as the game's one-time scrubs)"),
            "ootr_match": x.get("status")}


def merchant_edit(game, name, d):
    """The carpet salesman's edit.

    His Talk flow sets SimpleShop_Price, branches on his sold flag (both branches sell) and calls
    SimpleShop:SimpleShopRoot {ActorName, Price, MinusRupeeValue}. Its Sub_SimpleShop_Buy hands the item over
    (NpcCommon_HandOver_NpcToPlayer_NoTurn_NoWaitAS) and sets the flag. We check here that the flag is set only there
    and that he's SimpleShopRoot's only caller, so the flag really means "he sold something"."""
    from evfl import Evfl
    scene = d["scene"]
    fc, by_name = _event_index(Evfl(game.fs.read(f"Event/EventFlow/{scene}.bfevfl.zs")))
    talk = _reach(fc, fc["entry_points"]["Talk"]["main"])
    flag_q = [e for e in talk if e["type"] == "switch" and _param(e, "GameDataName") == d["sold_flag"]]
    calls = [e for e in talk if e["type"] == "subflow" and e.get("flowchart") == "SimpleShop"]
    prices = [e for e in talk if e["type"] == "action" and _param(e, "GameDataName") == "SimpleShop_Price"]
    if len(flag_q) != 1 or len(calls) != 1 or calls[0]["entry_point"] != "SimpleShopRoot" or len(prices) != 1:
        raise ShopError(f"{name}: {scene} Talk flow is not the one this module knows")
    sold = fc["events"][next(c["next"] for c in flag_q[0]["cases"] if c["value"] == 0)]
    if sold.get("next") != calls[0]["idx"]:
        raise ShopError(f"{name}: the sold branch doesn't lead to the sale")
    shop_fc, _ = _event_index(Evfl(game.fs.read("Event/EventFlow/SimpleShop.bfevfl.zs")))
    buy = _reach(shop_fc, shop_fc["entry_points"]["Sub_SimpleShop_Buy"]["main"])
    if not any(_param(e, "GameDataName") == d["sold_flag"] and _param(e, "Value") is True for e in buy):
        raise ShopError(f"{name}: SimpleShop Sub_SimpleShop_Buy doesn't set {d['sold_flag']}")
    callers = set()
    for fn in os.listdir(os.path.join(game.romfs, "Event", "EventFlow")):
        data = game.fs.read(f"Event/EventFlow/{fn}") if fn.endswith(".bfevfl.zs") else b""
        if b"SimpleShopRoot" not in data:
            continue
        for f in Evfl(data).flowcharts:
            for e in f["events"]:
                if e["type"] in ("subflow", "subflow_switch") and e.get("entry_point") == "SimpleShopRoot" \
                        and (e.get("flowchart") == "SimpleShop" or fn.startswith("SimpleShop.")):
                    callers.add(fn)
    if callers != {f"{scene}.bfevfl.zs"}:
        raise ShopError(f"{name}: SimpleShopRoot is also used by {sorted(callers)}")
    exists = gamedata_names(game, [d["sold_flag"]])
    if not all(exists.values()):
        raise ShopError(f"{name}: {d['sold_flag']} not in GameDataList")
    c = calls[0]
    edit = {"scene": scene, "route": {"event": flag_q[0]["name"], "case": 0}, "sold_flag": d["sold_flag"],
            "calls": [{"event": c["name"], "actor": _param(c, "ActorName"), "price": _param(c, "Price"),
                       "minus": _param(c, "MinusRupeeValue")}],
            "price_event": prices[0]["name"], "default_price": d["price"],
            "graph": "Rando_" + re.sub(r"\W", "", name.title()), "setting": d["setting"]}
    for k in ("requires", "requires_why"):
        if d.get(k):
            edit[k] = d[k]
    return edit


def mystery_runs(m, label, lang):
    """The message's text runs, with everything before the price (the item's name and blurb) swapped for the
    language's line for an unnamed item and its lead-in to the price. The price tag and the text after it stay, apart
    from QUESTION_FIX. This is for make_patch "text" ops, and the list form keeps every tag."""
    import msbt
    segs = m.messages[m.labels[label]]
    tags = [s for s in segs if isinstance(s, msbt.Tag)]
    runs = m.runs(label)
    price = next((k for k, t in enumerate(tags) if t.group == 2 and t.type == 12), None)
    if price is None or price < 1:
        raise ShopError(f"{label}: no price tag")
    cut = price - 1 if (tags[price - 1].group, tags[price - 1].type) == (0, 3) else price  # colour tag before it
    if cut < 1:
        raise ShopError(f"{label}: unexpected layout {runs}")
    if MYSTERY_LINE not in m.labels:
        raise ShopError(f"{lang}: no {MYSTERY_LINE} next to {label}")
    line = msbt.plain(m.messages[m.labels[MYSTERY_LINE]]).strip()
    if not line or "\n" in line:
        raise ShopError(f"{lang} {MYSTERY_LINE}: not a one-line message ({line!r})")
    lead = "\n" + PRICE_LEAD[lang] + ("" if not PRICE_LEAD[lang] or lang in NO_SPACE else " ")
    new = list(runs)  # run k is the text before tag k, so run 1 comes after the opening (speaker) tag
    if cut == 1:  # no tag around the item's name (the Chinese bag offers, say), so one run up to the price
        new[1] = line + lead
    else:
        new[1] = line
        for k in range(2, cut):
            new[k] = ""  # the item's name and blurb, their colour/grammar tags stay but with no text
        new[cut] = lead
    for k in range(cut + 1, len(new)):
        for old, repl in QUESTION_FIX.get(lang, ()):
            new[k] = new[k].replace(old, repl)
    return new


def _ootr_tables():
    """OoTR's vanilla item per shop/scrub location and its item prices, read from vendor/ootr as text (no OoTR
    import)."""
    src = open(os.path.join(HERE, "vendor", "ootr", "LocationList.py"), encoding="utf-8").read()
    vanilla, price = {}, {}
    for m in re.finditer(r'\(\s*"([^"]+)",\s*\("(Shop|MaskShop|Scrub|GrottoScrub)",[^\n]*?,\s*(?:\'((?:[^\'\\]|\\.)*)\'|"([^"]*)"),\s*\(', src):
        vanilla[m.group(1)] = (m.group(3) if m.group(3) is not None else m.group(4)).replace("\\'", "'")
    items = open(os.path.join(HERE, "vendor", "ootr", "ItemList.py"), encoding="utf-8").read()
    item_price = {}
    for m in re.finditer(r"^\s*'((?:[^'\\]|\\.)*)':\s*\('Shop',[^\n]*'price':\s*(\d+)", items, re.M):
        item_price[m.group(1).replace("\\'", "'")] = int(m.group(2))
    for n, v in vanilla.items():
        if v in item_price:
            price[n] = item_price[v]
    return {"vanilla": vanilla, "price": price, "item_price": item_price}


# Generator API
_MAP = {}


def shop_map():
    if not _MAP:
        if not os.path.exists(OUT):
            raise ShopError(f"{OUT} missing: run python tools/rando/shops.py build ROMFS")
        _MAP.update(json.load(open(OUT, encoding="utf-8")))
    return _MAP


# Splitting the potion shops (remake_split_potion_shops) gives the Kakariko keeper its own list, a new file in its pack.
POTION_SHOPS = ("Market Potion Shop", "Kak Potion Shop")
POTION_SHARED = "Component/ShopParam/Npc_Hylia_020_Shop.game__component__ShopParam.bgyml"
POTION_KAK = "Component/ShopParam/Npc_Hylia_020_Shop_Adult.game__component__ShopParam.bgyml"
POTION_KAK_PACK = "Pack/Actor/Npc_Hylia_020_Shop_Adult.pack.zs"
POTION_KAK_ACTOR = "Actor/Npc_Hylia_020_Shop_Adult.engine__actor__ActorParam.bgyml"
_SPLIT = {"on": False, "saved": {}}


def split_potion_shops(on):
    """Plays both potion shops (on) or keeps them vanilla (off, the map as built).

    When on, the Kakariko slots write the Kakariko keeper's own list (POTION_KAK, made from the shared list in
    its pack). The Market slots keep writing the shared list in both packs (one path, one content). A shelf gated by a
    save flag (Market slot 6, the bottle-bug tutorial) loses that gate when its item changes (plan_ops)."""
    locs = shop_map()["locations"]
    if on and not _SPLIT["on"]:
        for name, loc in locs.items():
            if loc["kind"] != "shop" or (loc.get("edit") or {}).get("shop") not in POTION_SHOPS:
                continue
            if loc["mode"] != "vanilla":
                continue
            _SPLIT["saved"][name] = copy.deepcopy(loc)
            loc["mode"] = "full"
            loc["why"] = "own list per potion shop (remake_split_potion_shops)"
            if loc["edit"]["shop"] == "Kak Potion Shop":
                first = next(l for l in loc["edit"]["lists"] if l["pack"] == POTION_KAK_PACK)
                loc["edit"]["lists"] = [dict(first, file=POTION_KAK, new_from=POTION_SHARED)]
            loc["edit"]["ungate_shelves"] = True
    elif not on and _SPLIT["on"]:
        locs.update(copy.deepcopy(_SPLIT["saved"]))
        _SPLIT["saved"].clear()
    _SPLIT["on"] = bool(on)


def _split_ops(plan):
    """Once the potion shops are split and any potion list is written, this adds the Kakariko keeper's own list (first,
    from the untouched shared list) and its ShopRef, so a Market change never shows up in Kakariko."""
    touched = any(op.get("file") in (POTION_SHARED, POTION_KAK) and op["pack"].endswith(
        ("Npc_Hylia_020_Shop_Adult.pack.zs", "Npc_Hylia_020_Shop_Child.pack.zs")) for op in plan["packs"])
    if not (_SPLIT["on"] and touched):
        return
    for op in plan["packs"]:
        if op.get("file") in (POTION_SHARED, POTION_KAK):  # only the potion lists' ops, other new files keep theirs
            op.pop("new_from", None)
    plan["packs"][:0] = [
        {"pack": POTION_KAK_PACK, "file": POTION_KAK, "new_from": POTION_SHARED, "set": {},
         "note": "Kak Potion Shop: its own list (a copy of the shared potion list)"},
        {"pack": POTION_KAK_PACK, "file": POTION_KAK_ACTOR, "set": {"Components.ShopRef": f"?{POTION_KAK}"},
         "note": "Kak Potion Shop: the keeper reads its own list"}]


# OoTR items a plugin adds to the pool that config/item_map.json doesn't have, like the story plugin's shuffled
# Master Sword (remake_shuffle_master_sword). songs_trade.ITEM_FIX gives the same actor.
EXTRA_SCRUB_ACTORS = {"Master Sword": "Weapon_Sword_Master"}


def scrub_actor(ootr_item):
    """The actor a scrub's sale call hands over for a non-progressive OoTR item.

    It's the one from config/item_map.json, except for its chest-only TBox_* actors. Rupees become Obj_Rupee_* (vanilla
    scenes hand those over with the Dm_SY_GetInEvent routines), and ammo, shields and hearts become the Shop_* actor a
    shelf sells. The boss-rush scrubs sell Shop_Sword_Giant through this same sale call.
    TODO: check these junk items in game, they're unverified."""
    actor = (ITEM_MAP["items"].get(ootr_item) or ITEM_MAP["junk_for"].get(ootr_item)
             or EXTRA_SCRUB_ACTORS.get(ootr_item))
    if actor and actor.lower().startswith("tbox_"):
        if ootr_item in SHELF:
            return SHELF[ootr_item]
        if actor.startswith("TBox_Rupee_"):
            return "Obj_Rupee_" + actor.rsplit("_", 1)[1]
    return actor


def sellable(ootr_item, kind="shop"):
    """The remake actor that sells this OoTR item, or None.
    kind="shop" gives the Shop_* actor for a shelf (only items that have one). kind="scrub" gives the actor the scrub
    hands over, from config/item_map.json. A progressive item gives its first tier here and plan_ops picks the tier in
    game."""
    if kind == "shop":
        return SHELF.get(ootr_item)
    if kind != "scrub":
        raise ValueError(kind)
    if ootr_item in PROGRESSIVE:
        return PROGRESSIVE[ootr_item]["tiers"][0]
    if ootr_item.startswith("Buy "):
        return None  # OoTR keeps shop items in shop slots
    # Songs, spiritual stones and medallions go through here too. A song holds up with its own animation
    # (config/hold_up.json "own", which make_patch adds when a step names it) through the sale's hand-over, same as at
    # every NPC give step. A stone or medallion can't be held up as it is (hold_up.json "show"), so make_patch's scrub
    # intercept gives it its display's hold-up, like it already does for an ocarina. At the carpet salesman's sale copy
    # hold_rewrite does that.
    return scrub_actor(ootr_item)


def dungeon_marker(ootr_item):
    """A dungeon item's sale marker, or None.

    That's the name of its credit entry (Dm_SY_GetInEvent:Rando_DI_Call_<item>, tools/rando/parity/dungeons.py). A
    scrub's one-time sale gets it as its ActorName (make_patch's scrub intercept pays and calls that entry,
    progressive.DI_MARKER), and the carpet salesman's sale copy calls it (_dungeon_merchant_ops). These items carry no
    dungeon in the game's own items (Item_Dungeon_SmallKey credits whatever dungeon Link is standing in), so a sale
    can't hand them over itself."""
    dg = sys.modules.get("parity.dungeons")
    if dg is None or not hasattr(dg, "call_entry") or dg.dungeon_item(ootr_item) is None:
        return None
    return dg.call_entry(ootr_item)


def call_marker(ootr_item, edit=None, request=False):
    """The Dm_SY_GetInEvent entry a scrub's one-time sale or the carpet salesman's sale copy calls for this item.

    None means the sale hands over the item's own actor, one sale call per tier. The entry's name is the scrub sale's
    ActorName marker (make_patch's intercept pays and calls it, progressive.CALL_MARKERS). It's one of:
      - a dungeon item's credit entry (dungeon_marker)
      - for a progressive item (its plan name) the sale calls can't hand over tier by tier, its tier entry
        RandoST_<Item>_Get, which the songs/trade plugin adds (request=True asks for it at plan time). That's when it
        has more tiers than the location's sale calls `edit["calls"]`, a tier is missing from the game, or a tier has a
        posing give entry of its own (the Kokiri wallet).
      - for an item no sale can hand over as an actor and whose give target is a Dm_SY_GetInEvent call
        (songs_trade._target, so the Magic Bean Pack, a soul or the Skeleton Key), that entry"""
    m = dungeon_marker(ootr_item)
    if m:
        return m
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "heal_call") and dg.heal_call(ootr_item):
        # a Recovery Heart or Fairy Drop gets its own hold-up, window and heal (dungeons.heal_graph). Otherwise the sale
        # would hand over a green rupee for a fairy and the shelf's Shop_Heart for a heart.
        return dg.heal_call(ootr_item).split(":", 1)[1]
    st = sys.modules.get("parity.songs_trade")
    if st is None:
        return None
    if ootr_item in PROGRESSIVE:
        ex = sys.modules.get("parity.extras_items")
        name = ex.target_name(ootr_item) if ex is not None else ootr_item
        import progressive
        tiers = progressive.PROGRESSIVE[name]["tiers"]
        info = shop_map()["scrub_items"].get(name) or {}
        own = info.get("exists") and not any(t in progressive.GIVE and t not in progressive.NO_POSE for t in tiers)
        fits = edit is None or edit.get("converted") or len(tiers) <= len(edit.get("calls") or [])
        if own and fits:
            return None
        from parity import _songs_trade_ops as st_ops
        return st_ops.request_host(name).split(":", 1)[1] if request else st_ops.host_entry(name)
    if scrub_actor(ootr_item) is not None or ootr_item.startswith("Buy ") or ootr_item == ICE:
        return None
    try:
        t = st._target(ootr_item)
    except ValueError:
        return None
    call = (t or {}).get("call") or ""
    import progressive
    if call.startswith("Dm_SY_GetInEvent:") and call.split(":", 1)[1].startswith(progressive.CALL_MARKERS):
        return call.split(":", 1)[1]
    return None


# A Shop_* type that a shelf's level doesn't place gets placed like any other. We used to refuse those because "a
# new object type in a level broke Kokiri Forest once", but that break was Obj_TBox_A_06, a chest with its own
# check-actor AI. The files have no per-level list of the types a level may create (actors load by name from their
# packs), and brand-new types of ours do load in a level (the Triforce probe in
# the Market, test_guardroom). The test build shows one in Kokiri Forest's shop (see its CHECKLIST).
NEW_TYPES = True


def why_not(ootr_name, ootr_item, allow_new_types=NEW_TYPES, deal=False):
    """None if the item can go to this location the way plan_ops would make it, else the reason.
    deal=True means the location is a special deal (OoTR's world.shop_prices), and those sell through the deal path
    (_deal_ops), what a shelf can't sell included."""
    reason = _why_not(ootr_name, ootr_item, allow_new_types)
    if reason and deal and uses_deal(ootr_name, ootr_item, allow_new_types, True):
        return None
    return reason


def _why_not(ootr_name, ootr_item, allow_new_types=NEW_TYPES):
    loc = shop_map()["locations"].get(ootr_name)
    if loc is None:
        return "not a shop, scrub or merchant location"
    if loc["mode"] == "plugin":
        return None  # another parity plugin sells it (MERCHANTS "plugin") and keeps its own item rules
    if loc["mode"] != "full":
        return None if ootr_item == loc["vanilla"] else f"locked vanilla ({loc['why']})"
    if loc["kind"] in ("scrub", "merchant") and call_marker(ootr_item, loc.get("edit")):
        return None  # the hand-over calls its entry (call_marker, a credit, tier or give entry)
    if ootr_item == ICE:
        # At scrubs and the carpet salesman the sale freezes Link (tools/rando/parity/_chests_scenes.py).
        # A shelf shows a disguise its level already places, with no freeze.
        if loc["kind"] in ("scrub", "merchant"):
            return None
        return None if ice_disguise(loc["edit"], "anything") else "no Shop_* look loaded in every shelf's level"
    if _keeps_remake_vanilla(loc, ootr_item):
        return None
    e = loc["edit"]
    if loc["kind"] in ("scrub", "merchant"):  # a scene hands it over, so any pouch item, one sale call per tier
        tiers = (shop_map()["scrub_items"].get(ootr_item) or {}).get("tiers")
        if sellable(ootr_item, "scrub") is None or not tiers:
            return f"no remake actor this {loc['kind']} can hand over"
        if not shop_map()["scrub_items"][ootr_item]["exists"]:
            return f"actor {tiers} missing from the game"
        if e.get("converted"):
            return None  # its sale calls are copies, one per tier
        if len(tiers) > len(e["calls"]):
            return f"{len(tiers)} tiers, this {loc['kind']} has {len(e['calls'])} sale call(s)"
        return None
    actor = sellable(ootr_item, "shop")
    if actor is None:
        return "no Shop_* actor sells it on a shelf"
    if not allow_new_types:
        for s in e["shelves"]:
            if actor not in shop_map()["stage_shop_types"][s["stage"]]:
                return f"{actor} is not loaded in {s['stage']} (a new object type in a level broke Kokiri Forest once)"
    gate = AGE_GATE.get(actor)
    if gate and e["ages"] != gate:
        # OoTR adds is_adult itself to "Buy ... Tunic" in a regular slot, but nothing for special deals or the shield
        if not (gate == "adult" and ootr_item.startswith("Buy ") and e["ages"] == "both"):
            if not (gate == "child" and e["shop"] == "KF Shop"):  # child reaches the KF shop from the start
                return f"the remake sells {actor} to {gate} Link only; this shop is {e['ages']}"
    if ootr_item.startswith("Bombchus"):
        # Bombchus are progression when they're in logic. OoTR's special deal has no rule for them, but the remake's
        # bombchus take their capacity from the bomb bag (world_settings), so without one the purchase might fail.
        # I haven't verified that.
        return "bombchus as a special deal: buying them without a bomb bag is unverified"
    return None


def _keeps_remake_vanilla(loc, ootr_item):
    """A scrub left with OoTR's vanilla menu item keeps the remake's own sale (the DMC scrub's heart piece), nothing to
    change. OoTR places that item ("Buy Bombs (5)...") itself when shuffle_scrubs is off."""
    return loc["kind"] == "scrub" and ootr_item == loc["vanilla"] and ootr_item.startswith("Buy ")


def item_allowed(ootr_name, ootr_item, allow_new_types=NEW_TYPES, deal=False):
    """For an OoTR item rule: can plan_ops sell this item at this location?"""
    return why_not(ootr_name, ootr_item, allow_new_types, deal) is None


def is_deal(location):
    """Whether OoTR location object `location` is a special deal (world.shop_prices from OoTR
    World.random_shop_prices)."""
    world = getattr(location, "world", None)
    return world is not None and location.name in (getattr(world, "shop_prices", None) or {})


# Special deals that sell anything
# A special deal whose item no shelf can sell (no Shop_* actor, a type its level doesn't place, a tunic where a child
# shops, bombchus) gets sold by new DisplayShop steps. It's the Happy Mask Shop's technique
# (parity/_songs_trade_child.py):
#   - The slot shows a placeholder Shop_* type its level already places (deal_look) at the deal's price. Its
#     GoodsList Release keeps it in stock while a new saved Bool of its own is true (default true, deal_flag). That's
#     the game's IsCheckSoldOutGameData, the same way the bombs use Get_StoneOfFire_IsCompleted_Exp and Blue Fire its
#     IsGet flag.
#   - New steps in front of DisplayShop NormalFlow tell the slot apart. NormalFlow is the step every shelf pick
#     reaches once the screen is closed and the out-of-stock checks are done. The steps check the shop's "talking"
#     flag (TALKING, the GameDataName each keeper's flow hands DisplayShop:Root_Buy, true for the visit and false at
#     its end) and Shop_SelectItemIndex, the GoodsList index of the pick. The engine writes that Int when a pick is
#     decided, in the same function that writes Shop_SelectItemPrice and Shop_SelectItemName (in main's code each
#     name's murmur3 hash is built into the set call's argument). The mask shop's flow sets it to 7 for the Mask of
#     Truth, its GoodsList[7] (Npc_Hylia_023_Shop_Child Pay_usagi Event204).
#   - On a match, if it's sold out already we play the shop's sold-out talk (Event118). Otherwise the shop's "The
#     <item>? That'll cost <price> rupees" question (Event16), with Shop_SelectItemName first set to the item's own
#     name actor when the game names it (deal_name). No goes back to the shelves (Event107). Yes checks for enough
#     rupees (EventQueryHasRuppe, else the shop's "not enough rupees" talk, Event329), pays
#     (EventTriggerIncreaseRupee), gives through the shared resolver (songs_trade.plain_give: a tier entry, a call
#     entry, the item's hold-up or the get routine), marks the slot sold, runs the shop camera (Event353's
#     EventCamera) and goes back to the shelves.
DEAL_FILE, DEAL_ENTRY, DEAL_GRAPH = "DisplayShop", "NormalFlow", "Rando_ShopDeal"
DEAL_NEXT, DEAL_SOLD, DEAL_ASK, DEAL_BACK, DEAL_POOR, DEAL_CAMERA = (
    "Event216", "Event118", "Event16", "Event107", "Event329", "Event353")
DEAL_BOARDS, DEAL_END = "Event165", "Event348"  # the board message after a sale, NormalFlow's forced end of the shop


def _trap_give(give):
    """Whether a deal's give node is a trap's (its call ends in the chests plugin's freeze or another trap kind).
    The ice-trap attacker waits until no event plays (drops.ice_sensor_ops), so the shop has to end for it to land.
    While the shop stayed open the Light Arrows trap froze nothing."""
    call = str((give or {}).get("call") or "")
    return "IceTrap" in call or "Trap" in call.split(":")[-1]
TALKING = {"KF Shop": "KokiriForest_Shop_Talking", "GC Shop": "GoronCity_Shop_Talking",
           "ZD Shop": "ZoraDomain_Shop_Talking", "Market Bazaar": "Market_Hylia_018_Shop_Talking",
           "Kak Bazaar": "KakarikoVillage_Hylia_018_Shop_Talking", "Market Bombchu Shop": "Market_Hylia_021_Shop_Talking",
           "Market Potion Shop": "Market_Hylia_020_Shop_Talking",
           "Kak Potion Shop": "KakarikoVillage_Hylia_020_Shop_Talking"}
# Placeholder types whose pick a check before NormalFlow can divert, plus bombchus, masks and count boards. The
# checks are DisplayShop Outofstock_SelectBomb / _SelectArrow / _SelectCloth / _SelectBottle_BlueFire, for bombs
# before the Goron Ruby, arrows and seeds without a quiver, tunics for a child and Blue Fire.
DEAL_AVOID = ("Shop_Armor_", "Shop_BombBundle_", "Shop_ArrowBundle_", "Shop_DekuSeedBundle_", "Shop_BombchuBundle_",
              "Shop_Bottle_BlueFire", "Shop_Mask_", "Shop_Board_")
DEAL_ORDER = ("Shop_Weapon_Shield_", "Shop_Heart", "Shop_DekuNut", "Shop_DekuStick", "Shop_MagicJar", "Shop_Bottle_")


def deal_flag(ootr_name):
    """The saved Bool that keeps a deal slot in stock while it's true (a new row, default true)."""
    return "Rando_Deal_" + re.sub(r"[^A-Za-z0-9]", "", ootr_name.replace(" Item ", "_"))


def deal_look(e, major, seed=""):
    """The placeholder Shop_* type a deal slot shows, or None if there's none.
    It has to be one every shelf of the slot's levels already places and that no check before NormalFlow diverts
    (DEAL_AVOID). A major item gets a shield where the level has one (OoTR's ice-trap appearance split, MAJOR_LOOKS),
    otherwise we take the rest in DEAL_ORDER's order."""
    stages = [s["stage"] for s in e["shelves"]]
    types = shop_map()["stage_shop_types"]
    common = set.intersection(*(set(types[st]) for st in stages)) if stages else set()
    ok = [a for a in sorted(common) if a in shop_map()["shop_actors"] and not a.startswith(DEAL_AVOID)]
    ok.sort(key=lambda a: next((i for i, p in enumerate(DEAL_ORDER) if a.startswith(p)), len(DEAL_ORDER)))
    if not ok:
        return None
    pick = [a for a in ok if (a in MAJOR_LOOKS) == bool(major)] or ok
    if major:
        return pick[0]
    pick = [a for a in pick if not a.startswith("Shop_Bottle_")] or pick  # a bottle asks for an empty bottle
    return pick[sum(map(ord, seed)) % len(pick)]


_deal_cache = {}


def deal_can_give(ootr_item):
    """None if the deal path can hand OoTR item `ootr_item` over, else why not.
    That's any item the shared resolver gives (a progressive item's tier entry, a call entry, an actor). OoTR never
    puts its shop items ("Buy ...") in deals, and an ice trap keeps the shelf disguise (ice_disguise)."""
    if ootr_item in _deal_cache:
        return _deal_cache[ootr_item]
    why = None
    st = sys.modules.get("parity.songs_trade")
    if ootr_item.startswith("Buy ") or ootr_item == ICE:
        why = "a shop item or an ice trap: the shelf's own sale"
    elif ootr_item in PROGRESSIVE:
        why = None
    elif st is None:
        why = "no give router (the songs/trade plugin is off)"
    elif not st.hand_actor(ootr_item):
        try:
            t = st._target(ootr_item)
        except ValueError as ex:
            t, why = {}, str(ex)
        if not why and not (t.get("call") or t.get("actor")):
            why = "nothing to hand over"
    _deal_cache[ootr_item] = why
    return why


def uses_deal(ootr_name, ootr_item, allow_new_types=NEW_TYPES, deal=False):
    """True if this special deal sells `ootr_item` through the deal path. Every shuffled slot does, even an item its
    shelf could sell (a heart, nuts, bombs): OoTR sells each shuffled slot once and then shows it sold out, and only
    the deal path keeps a sold flag (deal_flag), which the trackers read too. A shelf sale could be bought again."""
    loc = shop_map()["locations"].get(ootr_name) or {}
    if not deal or loc.get("kind") != "shop" or loc.get("mode") != "full" or ootr_item == ICE:
        return False
    e = loc["edit"]
    return (e.get("shop") in TALKING and deal_can_give(ootr_item) is None
            and deal_look(e, True) is not None and deal_look(e, False) is not None)


def deal_give(item, location, nxt):
    """The node that hands deal item `item` over through the shared resolver (songs_trade.plain_give), then goes to
    `nxt`."""
    import progressive
    st = sys.modules.get("parity.songs_trade")
    how = st.plain_give(item, location)
    if how is None:
        raise ShopError(f"{location}: no give for {item}")
    if how[0] == "call":
        dg = sys.modules.get("parity.dungeons")  # a heal entry reads ActorName, its window names the item
        params = dg.heal_params(item) if dg is not None and hasattr(dg, "heal_params") else {}
        return {"call": how[1], "next": nxt, **({"params": params} if params else {})}
    actor = how[1]
    if actor.startswith("TBox_Rupee_"):  # a chest's rupee becomes the pickup the scenes hand over (scrub_actor)
        actor = "Obj_Rupee_" + actor.rsplit("_", 1)[1]
    return progressive.hold_node(actor, nxt) or {"call": "Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff",
                                                 "params": {"ActorName": actor}, "next": nxt}


_names = {}


def _pouch_names():
    """The labels of ActorMsg/PouchContent.msbt, like <actor>_Name. We read USen, every language has the same labels."""
    if not _names:
        import msbt
        from romtools import Romfs
        arch = msbt.read_archive(Romfs(DEFAULT_ROMFS, VANILLA), "USen")
        _names["labels"] = set(msbt.Msbt(arch["ActorMsg/PouchContent.msbt"]).labels)
    return _names["labels"]


def deal_name(item):
    """The actor whose name we show for deal item `item`.
    That's PouchContent <actor>_Name, what the shop's question shows for Shop_SelectItemName. Gives one actor per tier
    for a progressive item, [actor] otherwise, and [] if the game has no name for it (then the question names the
    placeholder)."""
    st = sys.modules.get("parity.songs_trade")
    names = _pouch_names()
    if item in PROGRESSIVE:
        import progressive
        ex = sys.modules.get("parity.extras_items")
        tiers = progressive.PROGRESSIVE[ex.target_name(item) if ex is not None else item]["tiers"]
        return list(tiers) if all(f"{a}_Name" in names for a in tiers) else []
    actor = st.hand_actor(item) if st is not None else None
    if not actor and st is not None:
        t = st._target(item)
        if item == "Magic Bean Pack":
            actor = "Item_MagicBean"
        # dungeon items and heals use their model's name (Small Key, Boss Key, Map, Compass, Recovery Heart, Fairy,
        # see dungeons.HEAL)
        elif t.get("dungeon") or t.get("heal"):
            actor = t.get("model")
        elif not t.get("call"):  # a soul's or the Skeleton Key's stand-in model isn't its name
            actor = t.get("actor")
    if actor and actor.startswith("TBox_Rupee_"):
        actor = "Obj_Rupee_" + actor.rsplit("_", 1)[1]
    return [actor] if actor and f"{actor}_Name" in names else []


def _set_name(actor, nxt):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
            "params": {"GameDataName": "Shop_SelectItemName", "Index": -1, "Value": actor}, "next": nxt}


def _route(node, old, new):
    """`node` with every target `old` replaced by `new`."""
    n = dict(node)
    if n.get("next") == old:
        n["next"] = new
    if "cases" in n:
        n["cases"] = {k: (new if v == old else v) for k, v in n["cases"].items()}
    return n


def _deal_ops(plan, notes, name, e, item, price, major, k, looks_like=None, give=None):
    """The deal path for special deal `name` (see the block comment above).
    It makes the item's look on the shelf and in the GoodsList (shelf_look / _shelf_ops). That's a shelf type of ours on
    the placeholder's base, or the placeholder itself when the item has no model to show. Then the DisplayShop nodes
    that tell this slot apart (labels s<k>..., "@next" for the next slot).
    looks_like: an ice trap's disguise, shown and named as that item.
    give: the give node's call to use instead of the item's (an ice trap's freeze)."""
    look = deal_look(e, major, name)
    flag = deal_flag(name)
    shown = looks_like or item
    looks = shelf_look(item, looks_like)
    shelf, shelf_place = (_shelf_ops(plan, notes, name, e, look, shown, looks, flag, k) if looks
                          else (None, []))
    if not looks:
        notes.append(f"{name}: no model to show {shown} with: the placeholder {look} stays")
    _shop_ops(plan, notes, name, e, None, price, actor=shelf or look, base=look if shelf else None,
              release={"IsCheckReleaseGameData": False, "ReleaseGameData": "",
                       "IsCheckSoldOutGameData": True, "SoldOutGameData": flag})
    plan["placements"] += shelf_place
    # A one-time slot shows SOLD OUT once bought, like vanilla's sold-out stock does (KF's short stock, the Bazaar's
    # bombs, Blue Fire). Their shelf links a Shop_Board_SoldOut that the sale's board message shows.
    for s in e["shelves"]:
        if _never_shown(s) or any(b["gyaml"] == SOLD_BOARD for b in s["boards"]):
            continue
        board = _board_ops(plan, s, SOLD_BOARD, f"{name}: SOLD OUT board")
        plan["placements"] += board
        # Every tier shelf of the spot links the board too. The board only shows or hides when its shelf item
        # messages it (Shop_Item_Base.root sends "show" when sold out and "hide" otherwise, on Enter and whenever
        # the sold-out state changes). With no message it stays as created, so shown. If only the tier-0 shelf links
        # it, it stands over the Longshot whenever the Hookshot is owned (KF Shop Item 5), because the tier-0 shelf
        # isn't there to hide it.
        # A twin copies the vanilla shelf's links, which were made before this board.
        for op in shelf_place if board else ():
            if op.get("twin") is not None and op["file"] == s["file"] and str(op["hash"]) == str(s["hash"]):
                op.setdefault("add_links", []).append({"dst": board[0]["twin"]})
    plan.setdefault("_deal_looks", {})[name] = shelf or look
    idx = {l["index"] for l in e["lists"]}
    if len(idx) != 1:
        raise ShopError(f"{name}: its GoodsList index differs between lists ({sorted(idx)})")
    j = idx.pop()
    # EventQueryIsGameDataInt answers 0 for below, 1 for equal and 2 for above Value (see the poe buyer's
    # GhostShop_CouponNum tests, the Dampe race's Event359/360/303). Only "equal" is this
    # slot. If you take 0 as "equal", every pick below the first deal's index buys that deal.
    n = {f"s{k}": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                   "params": {"GameDataName": TALKING[e["shop"]], "Index": -1}, "cases": {0: f"i{k}", 1: "@next"}},
         f"i{k}": {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                   "params": {"GameDataName": "Shop_SelectItemIndex", "Index": -1, "Value": j},
                   "cases": {0: "@next", 1: f"b{k}", 2: "@next"}},
         f"b{k}": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                   "params": {"GameDataName": flag, "Index": -1}, "cases": {0: f"n{k}", 1: "@" + DEAL_SOLD}}}
    tiers = deal_name(shown)
    if len(tiers) > 1:  # the tier it will give: owning tier t names tier t+1 (the top one repeats), none names tier 0
        top = len(tiers) - 1
        for q, t in enumerate(range(top, -1, -1)):
            n[f"n{k}" if q == 0 else f"n{k}_{q}"] = {
                "actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                "params": {"Actor": tiers[t], "Num": 1},
                "cases": {0: f"nm{k}_{min(t + 1, top)}", 1: f"n{k}_{q + 1}" if q < top else f"nm{k}_0"}}
        for t in range(top + 1):
            n[f"nm{k}_{t}"] = _set_name(tiers[t], f"a{k}")
    elif tiers:
        n[f"n{k}"] = _set_name(tiers[0], f"a{k}")
    else:
        n[f"n{k}"] = {"actor": "GameSystemActor", "action": "EventWait", "params": {"Frames": 1, "IsWaitEnd": True},
                      "next": f"a{k}"}
    n[f"a{k}"] = {"copy": DEAL_ASK, "next": f"c{k}"}
    n[f"c{k}"] = {"actor": "GameSystemActor", "query": "EventQueryTalkChoice2", "cases": {0: f"m{k}", 1: "@" + DEAL_BACK}}
    n[f"m{k}"] = {"actor": "PouchSystemActor", "query": "EventQueryHasRuppe", "params": {"Value": price},
                  "cases": {0: f"p{k}", 1: "@" + DEAL_POOR}}
    n[f"p{k}"] = {"actor": "PouchSystemActor", "action": "EventTriggerIncreaseRupee", "params": {"Value": -price},
                  "next": f"g{k}"}
    n[f"g{k}"] = dict(give, next=f"f{k}") if give else deal_give(item, name, f"f{k}")
    n[f"f{k}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                  "params": {"GameDataName": flag, "Index": -1, "Value": False}, "next": f"o{k}"}
    # tell the shop's boards the slot is sold so its SOLD OUT board shows, the same step vanilla runs after a sale
    # (NormalFlow Event224 / Event165, Npc_EventStarter.EventTriggerSendMessageToShopBoard)
    n[f"o{k}"] = {"copy": DEAL_BOARDS, "next": f"r{k}"}
    if give and _trap_give(give):  # a trap ends the shop, like vanilla's KF Deku Shield sale before the Deku Tree does
        n[f"r{k}"] = {"copy": DEAL_END, "next": None}  # Event348 Forced_Buy_End, the freeze waits for no event to play
    else:
        n[f"r{k}"] = {"copy": DEAL_CAMERA, "next": "@" + DEAL_BACK}
    notes.append(f"{name}: {item} for {price}, a special deal sold by its own steps (shelf shows {shelf or look}"
                 + (f" as {looks_like}" if looks_like else "") + f"; GoodsList[{j}], {TALKING[e['shop']]}; sold out: "
                 f"{flag} false)")
    return n



# Shelf looks: the real item on the shelf
# A special deal (or an ice trap's disguise) shows the item itself, the way OoTR's shopsanity draws the item's own
# model and names it in the shop's texts. As I put it: "a random item on the shelf of a shop should look like that
# item". The shelf item is a new actor type of ours per look (shelf_type_ops). It's a copy of the slot's placeholder
# Shop_* pack (deal_look), so it has its shop AI, physics, pouch and price parameters, and the shop's checks before
# NormalFlow treat the pick the same as the placeholder's before the deal steps take over. On top of that it gets:
#   - the model of the item's display and its animation set. That's the look the drops and chests show
#     (drops.item_display), a config/hold_up.json display's model or parity/_show_models.py's, else the item
#     actor's own.
#   - the item's name. The shop screen's name and caption, the price window and Shop_SelectItemName are all read from
#     the shelf actor's ActorName (ActorNameRef's file name). Every vanilla shelf actor works like that:
#     Shop_Weapon_Shield_Deku is named Weapon_Shield_Deku, and its texts are PouchContent Weapon_Shield_Deku_Name /
#     _ShopCaption. So the type is named after the item's pouch actor (Item_Hookshot is "Hookshot"). An item the
#     shelf caption has no text for gets its own <name>_ShopCaption, a copy of the item's caption in every language.
#   - its ActorInfo / GameActorInfo rows. Those are the placeholder's, with the model's names, bounds, animation
#     banks, the larger heaps and the item's pose (ModelVariationAnims).
#   - a size on the shelf within the vanilla shelf items' range (the placement's Scale, SHELF_SIZE).
# A progressive item shows the tier it will give, like OoTR resolves it when drawing the shelf. There's one shelf
# placement per tier (twins of the vanilla shelf), each shown by its own expression flag (add_boolexp, from
# IsGet.<actor> of the tiers before and the tier itself, plus the slot's in-stock flag), checked when the shop loads
# (IsCheckLazy false).
SHELF_PREFIX = "Rando_Shelf_"
SHELF_NAME_MAX = 25  # as with the displays: the show-item create keeps 31 characters, a shelf item is never held up
POUCH_MSG = "ActorMsg/PouchContent.msbt"
SHELF_SIZE = (0.22, 0.62)  # the largest model extent a shelf item is drawn at, in m (the vanilla shelf items' range)
SHELF_FIT = 1.25  # and at most this much larger than the vanilla item of its shelf, since the shelf draws both
#                   (without it the Light Arrows, 0.68 m posed, stood 0.62 m tall where a 0.31 m heart stood)
SHELF_SCALE_STEP = 1.05  # smaller changes aren't made
SHELF_TIER_EXP = "Rando_ShelfT_{:03d}_{}"  # a progressive deal's tier shelf, shown while this expression holds
_shelf_cache = {}


def _fs():
    if "fs" not in _shelf_cache:
        from romtools import Romfs
        _shelf_cache["fs"] = Romfs(DEFAULT_ROMFS, VANILLA)
    return _shelf_cache["fs"]


def _actor_pack(actor):
    key = ("pack", actor)
    if key not in _shelf_cache:
        from romtools import sarc_files
        rel = f"Pack/Actor/{actor}.pack.zs"
        _shelf_cache[key] = sarc_files(_fs().read(rel)) if os.path.exists(os.path.join(DEFAULT_ROMFS, rel)) else None
    return _shelf_cache[key]


def _table(table):
    key = ("rows", table)
    if key not in _shelf_cache:
        from romtools import byml_load
        _shelf_cache[key] = {r["__RowId"]: r for r in byml_load(_fs().read(table), allow_big=True)[0]}
    return _shelf_cache[key]


def _comps(actor):
    import progressive
    files = _actor_pack(actor)
    return progressive._chain_comps(files, actor) if files else {}


def name_actor(actor):
    """The name an actor shows (PouchContent <name>_Name). That's its ActorNameRef's file name, or else its own name."""
    ref = (_comps(actor).get("ActorNameRef") or "").lstrip("?")
    return ref.rsplit("/", 1)[-1].split(".")[0] if ref else actor


def _labels(lang="USen"):
    key = ("labels", lang)
    if key not in _shelf_cache:
        import msbt
        arch = msbt.read_archive(_fs(), lang)
        _shelf_cache[key] = msbt.Msbt(arch[POUCH_MSG])
    return _shelf_cache[key]


def _named(actor):
    """The pouch name actor naming `actor` (name_actor) if PouchContent has its _Name, else None."""
    if not actor:
        return None
    for a in (name_actor(actor), actor):
        if f"{a}_Name" in _labels().labels:
            return a
    return None


def _model_source(actor):
    """How the shelf type shows `actor` (a display or an item actor), or None if it has no model we can copy.
    Returns {"provided": the _show_models model or None, "model_from": the actor whose ModelInfo is copied or None,
    "anim_from": the actor whose AnimationParam is copied}."""
    import progressive
    spec = progressive.HOLD_DISPLAYS.get(actor)
    if spec:
        provided = progressive.show_model(actor, DEFAULT_ROMFS)
        if not provided and not spec.get("model_from"):
            return None
        return {"provided": provided, "model_from": None if provided else spec["model_from"],
                "anim_from": (provided or {}).get("anim_from") or spec["anim_from"]}
    own = progressive.HOLD_OWN.get(actor) or {}
    if own.get("model_key"):
        provided = progressive.show_model(own["model_key"], DEFAULT_ROMFS)
        if provided:
            return {"provided": provided, "model_from": None,
                    "anim_from": provided.get("anim_from") or own["anim_from"]}
    comps = _comps(actor)
    if not comps.get("ModelInfoRef") or "Dummy" in comps["ModelInfoRef"] or actor not in _table(ACTOR_INFO_TABLE):
        return None
    return {"provided": None, "model_from": actor, "anim_from": actor if comps.get("AnimationRef") else None}


ACTOR_INFO_TABLE = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
GAME_ACTOR_INFO_TABLE = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"
# The shop's price window shows the shelf actor's PouchActorInfo row (BuyingPrice) plus the slot's PriceOffset. A
# shelf type with no row shows the offset alone, so the Light Arrows deal at 125 = 40 + 85 showed "85". Every Shop_*
# actor has a row (395 rows), and a shelf type gets a copy of its placeholder's.
POUCH_INFO_TABLE = "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"
# How a shelf item is drawn (read from the files). AS/Item_Common plays the item's "Pose_Shop" where its animation
# bank has one (seeds, sticks, arrow bundles, whose bind poses hang 0.13-0.38 m below the origin), else
# "Pose_Common". In that pose every vanilla shelf item's model stands on its origin (lowest point -0.012..+0.035 m,
# 8 shelf models) and is centred on it.
# A model's ActorInfo bounds come from its bind pose though. By their bound the Light Arrows reach 0.38 m below the
# origin, but only 0.11 m posed, so placing them by the bound floated them 0.27 m above the shelf. And the stick
# bundle's bind-pose centre moved Queen Gohma's figure onto the price tag.
SHELF_POSES = ("Pose_Shop", "Pose_Common")
# The shop's cursor is the lock-on reticle, the four turning triangles. main 0x8022ffc0 (the attention update) places
# it from the target's calculator, and reads the target's ActorPositionCalculatorParam through calc + 0x8a8 (for its
# IsDispLockOnCursorFromBottom, for example).
# Its centre doesn't follow the model. On Queen Gohma's figure, a model centred on its origin, it sat 0.25-0.3 m
# above the placement's origin ("a little too high"). That's the centre of the target body every shelf item has
# (Shop_Item_Base_Tgt_0, a 0.5 m cylinder standing on the origin, in all 46 Shop_* packs). A vanilla shelf item
# stands on its origin with its posed centre 0.14-0.27 m up, so the cursor sits on it. A shelf type of ours stands
# where _shelf_place moved it to rest on the shelf (the figure's origin is 0.155 m up), so its cursor floated about
# a model's height above it.
# The game's own fix for this is the param's CursorYOffset (param + 0x100, ShopCommon sets it, Shop_Sword_Giant has
# 0.3). So each shelf type gets its own calculator param, a copy of its placeholder's, with a CursorYOffset that
# brings the cursor onto the model's posed centre (_cursor_want). The base was measured in game, not read from the
# code (cursor_base).
CURSOR_REF = "Component/ActorPositionCalculatorParam/{}.game__component__ActorPositionCalculatorParam.bgyml"
CURSOR_TOL = 0.05  # m, a shelf type's cursor has to be within this of its model's posed centre (the read-back's)
CURSOR_SPREAD = 0.02  # m, we note a type placed at scales that want CursorYOffsets further apart than this


def _work_path(p):
    """A pack-inner path from a "Work/....gyml" reference (or a "?....bgyml" one)."""
    p = str(p or "").lstrip("?")
    if p.startswith("Work/"):
        p = p[len("Work/"):]
    return p[:-len(".gyml")] + ".bgyml" if p.endswith(".gyml") else p


def cursor_base(files, actor):
    """How high (m) above the origin the centre of `actor`'s target body is, in its pack `files`, or None.
    The target body is the Tgt shape its PhysicsParam's ControllerSet names. That's where the shop's cursor centres
    with no CursorYOffset (see CURSOR_REF), 0.25 m for every shelf item."""
    import progressive
    from romtools import byml_load
    phys = _work_path(progressive._chain_comps(files, actor).get("PhysicsRef"))
    if phys not in files:
        return None
    cset = _work_path(byml_load(files[phys])[0].get("ControllerSetPath"))
    if cset not in files:
        return None
    for e in byml_load(files[cset])[0].get("ShapeNamePathAry") or []:
        shape = _work_path(e.get("FilePath"))
        if str(e.get("Name", "")).startswith("Tgt") and shape in files:
            c = (byml_load(files[shape])[0].get("AutoCalc") or {}).get("Center") or {}
            return float(c.get("Y", 0.0))
    return None


def cursor_offset(files, actor):
    """CursorYOffset of `actor`'s ActorPositionCalculatorParam in its pack `files`, following the param's $parent
    chain (0.0 when none sets it)."""
    import progressive
    from romtools import byml_load
    path, guard = _work_path(progressive._chain_comps(files, actor).get("ActorPositionCalculatorRef")), 0
    while path in files and guard < 8:
        guard += 1
        p = byml_load(files[path])[0]
        if "CursorYOffset" in p:
            return float(p["CursorYOffset"])
        path = _work_path(p.get("$parent"))
    return 0.0


def _cursor_want(built, scale):
    """The CursorYOffset that puts the shop's cursor on the posed centre of shelf type `built` (shelf_type_ops) placed
    at `scale` (a placement's Scale list, None means 1). None if the type's model or target body is unknown.
    TODO: we don't know yet whether the target body scales with the placement, I've only seen unscaled items in game.
    So its height is taken half-way between the two, which is within cursor_base * |1 - scale| / 2 either way
    (3.6 cm at the clamp's 0.71) and exact at scale 1."""
    lo, hi = built.get("aabb") or (None, None)
    k = built.get("cursor_base")
    if not (lo and hi) or k is None:
        return None
    s = float(scale[1]) if scale else 1.0
    return (float(lo["Y"]) + float(hi["Y"])) / 2 * s - k * (1 + s) / 2


def shelf_look(item, looks_like=None):
    """What the shelf shows OoTR item `item` with, as [(display actor, name actor or None)].
    One per tier for a progressive item (tier 0 first), or None when there's no model for it (the placeholder stays).
    `looks_like` is an ice trap's disguise (OoTR's looks_like_item), shown and named as that item."""
    import drops as drop_tools
    shown = looks_like or item
    try:
        d = drop_tools.item_display(shown)
    except Exception:  # a display waiting for its model, or an item drops doesn't know
        d = None
    if d and "tiers" in d:
        import progressive
        ex = sys.modules.get("parity.extras_items")
        tiers = progressive.PROGRESSIVE[ex.target_name(shown) if ex is not None else shown]["tiers"]
        if len(tiers) != len(d["tiers"]):
            return None
        out = [(disp, _named(t) or _named(disp)) for (_owned, disp), t in zip(d["tiers"], tiers)]
    else:
        actor = (d or {}).get("actor")
        st = sys.modules.get("parity.songs_trade")
        hand = None
        if st is not None:
            try:
                hand = st.hand_actor(shown) or (st._target(shown) or {}).get("actor")
            except ValueError:
                hand = None
        hand = hand or (ITEM_MAP["items"].get(shown) or ITEM_MAP["junk_for"].get(shown))
        if hand and hand.startswith("TBox_Rupee_"):
            hand = "Obj_Rupee_" + hand.rsplit("_", 1)[1]
        if not actor and hand and _model_source(hand):
            actor = hand  # no display-only twin (a heart piece), so use the pickup's own model
        actor = actor or SHELF_FALLBACK.get(shown)
        if not actor:
            return None
        spec = __import__("progressive").HOLD_DISPLAYS.get(actor) or {}
        try:
            names = deal_name(shown)
        except ValueError:
            names = []
        name = _named(names[0]) if names else None
        name = name or _named(spec.get("for")) or _named(hand)
        if name is None and not spec and shown not in SHELF_FALLBACK:
            name = _named(actor)
        out = [(actor, name)]  # None: the game has no name text for it, the shelf type gets its own (its OoTR name)
    if any(_model_source(disp) is None for disp, _ in out):
        return None
    return out


# items with no display of their own, and the model a shelf shows them with
SHELF_FALLBACK = {"Skeleton Key": "Item_Dungeon_SmallKey"}


def shelf_type(base, display, name, own=None):
    """The shelf type's name, Rando_Shelf_<short>_<hash>, for a placeholder base, display and name actor. With no
    name actor it's named after OoTR item `own`."""
    import zlib
    short = re.sub(r"^(Rando_Show_|Item_|Obj_|TBox_|Weapon_)", "", display).replace("_", "")
    tag = f"{zlib.crc32(f'{base}|{display}|{name or own}'.encode()) & 0xFFF:03X}"
    room = SHELF_NAME_MAX - len(SHELF_PREFIX) - 1 - len(tag)
    return f"{SHELF_PREFIX}{short[:room]}_{tag}"


def _extent(lo, hi):
    return max(float(hi[k]) - float(lo[k]) for k in ("X", "Y", "Z")) if lo and hi else None


def _banks(rows):
    """The animation banks (Model/<bank>.anim.bfres.zs) an actor's ActorInfo-style rows name, in order, once each."""
    out = []
    for r in rows or ():
        b = (r or {}).get("ModelProjectName")
        if b and b not in out and b != "Item_Common_Animation":
            out.append(b)
    return out


def posed_box(project, fmdb, banks, fallback):
    """(min, max) {X, Y, Z} of model Model/<project>.<fmdb>.bfres.zs the way a shelf draws it, or `fallback` (its
    ActorInfo bounds) when it has none of the poses or can't be posed. The pose is the first of SHELF_POSES one of
    `banks` has, skinned the way parity/_show_models.py does it. Read once per model."""
    key = ("posed", project, fmdb, tuple(banks))
    if key in _shelf_cache:
        return _shelf_cache[key] or fallback
    if "game_models" not in _shelf_cache:
        _shelf_cache["game_models"] = {(r.get("ModelProjectName"), r.get("FmdbName"))
                                       for r in _table(ACTOR_INFO_TABLE).values()}
    if (project, fmdb) not in _shelf_cache["game_models"]:  # our model: its bounds, even if a mod left the file there
        _shelf_cache[key] = None
        return fallback
    box = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import _shelf_pose as sp  # read only, the BFRES skinning in tools/rando/_shelf_pose.py
        fs = _fs()
        for pose in SHELF_POSES:
            bank = None
            for b in banks:
                rel = f"Model/{b}.anim.bfres.zs"
                if not os.path.exists(os.path.join(DEFAULT_ROMFS, rel)):
                    continue
                try:
                    sp._pose(fs.read(rel), pose)
                except sp.ModelError as ex:
                    if str(ex).startswith("no skeletal anim"):
                        continue
                    raise  # it has the pose and is animated, so fall back to its bounds below
                bank = rel
                break
            if bank is None:
                continue
            pos, _tris = sp.posed_source(f"Model/{project}.{fmdb}.bfres.zs", bank, pose, fs)
            lo, hi = pos.min(0), pos.max(0)
            box = ({"X": float(lo[0]), "Y": float(lo[1]), "Z": float(lo[2])},
                   {"X": float(hi[0]), "Y": float(hi[1]), "Z": float(hi[2])})
            break
    except Exception:  # a model or pose the skinning can't read gets its bounds
        box = None
    _shelf_cache[key] = box
    return box or fallback


def actor_shelf_box(actor):
    """posed_box of a game actor's model, from its ActorInfo row (model, bounds, animation banks), or else its
    bounds."""
    row = _table(ACTOR_INFO_TABLE).get(actor) or {}
    fallback = (row.get("ModelAabbMin"), row.get("ModelAabbMax"))
    if not (row.get("ModelProjectName") and row.get("FmdbName")):
        return fallback
    return posed_box(row["ModelProjectName"], row["FmdbName"], _banks(row.get("AnimationResources")), fallback)


def shelf_type_ops(shelf, base, display, name, own=None):
    """Ops for the new shelf actor type `shelf` (see the block comment), as {"new_files", "packs", "byml", "text",
    "scale"}.
    It's a copy of placeholder `base`'s pack that shows `display`'s model and is named `name`, a pouch name actor.
    With name None the type uses its own name, with its own labels made from the display's 'for' item. "scale" is
    the placement scale that brings its largest extent into SHELF_SIZE (1.0 for none)."""
    import progressive
    src = _model_source(display)
    rel = f"Pack/Actor/{shelf}.pack.zs"
    base_rel = f"Pack/Actor/{base}.pack.zs"
    base_files = _actor_pack(base)
    base_param = f"Actor/{base}.engine__actor__ActorParam.bgyml"
    if not base_files or base_param not in base_files:
        raise ShopError(f"{base}: no pack / ActorParam to copy for {shelf}")
    rows, grows = _table(ACTOR_INFO_TABLE), _table(GAME_ACTOR_INFO_TABLE)
    if shelf in rows or shelf in grows:
        raise ShopError(f"{shelf}: the game already has an actor of that name")
    note = f"{shelf}: shelf look of {display} named {name or shelf} (placeholder {base})"
    out = {"new_files": [{"to": rel, "from": base_rel, "note": note}], "packs": [], "byml": [], "text": []}
    involved = [rows[base]]
    if src["provided"]:
        m = src["provided"]
        involved += [rows[h] for h in [m.get("heap_from")] if h in rows]  # a soul figure uses its museum actor's heaps
        out["new_files"] += list(m.get("new_files") or [])
        model = f"Component/ModelInfo/{shelf}.engine__component__ModelInfo.bgyml"
        out["packs"].append({"pack": rel, "file": model, "new_from": progressive.BASE_MODELINFO,
                             "from_pack": progressive.BASE_PACK,
                             "set": {k: m["modelinfo"][k] for k in ("FmdbName", "ModelProjectName")}})
        keys = {k: m["modelinfo"][k] for k in ("ModelProjectName", "FmdbName")}
        lo, hi = m["aabb"]
    else:
        mf = src["model_from"]
        model = (_comps(mf).get("ModelInfoRef") or "").lstrip("?")
        if model not in (_actor_pack(mf) or {}):
            raise ShopError(f"{mf}: no ModelInfo {model!r} in its pack")
        out["packs"].append({"pack": rel, "file": model, "from_pack": f"Pack/Actor/{mf}.pack.zs"})
        keys = {k: rows[mf][k] for k in ("ModelProjectName", "FmdbName") if k in rows[mf]}
        lo, hi = rows[mf].get("ModelAabbMin"), rows[mf].get("ModelAabbMax")
        involved.append(rows[mf])
    sets = {"Components.ModelInfoRef": "?" + model,
            "Components.ActorNameRef": f"?ActorSystem/ActorName/{name or shelf}.engine__actor__ActorName.bgyml"}
    anim_res = None
    af = src["anim_from"]
    if af:
        anim = (_comps(af).get("AnimationRef") or "").lstrip("?")
        if anim not in (_actor_pack(af) or {}):
            raise ShopError(f"{af}: no AnimationParam {anim!r} in its pack")
        out["packs"].append({"pack": rel, "file": anim, "from_pack": f"Pack/Actor/{af}.pack.zs"})
        sets["Components.AnimationRef"] = "?" + anim
        if af in rows:
            involved.append(rows[af])
            anim_res = rows[af].get("AnimationResources")
        if anim_res is None:
            from romtools import byml_load
            anim_res = byml_load(_actor_pack(af)[anim])[0].get("AnimationResources")
    actor_op = {"pack": rel, "file": f"Actor/{shelf}.engine__actor__ActorParam.bgyml", "new_from": base_param,
                "set": sets, **({} if af else {"remove": ["Components.AnimationRef"]})}
    out["packs"].append(actor_op)
    # the shop's cursor (CURSOR_REF). _merge_shelf_types makes the type's own calculator param once every
    # placement's CursorYOffset (_cursor_want) is known, and until then it uses its placeholder's
    calc = _work_path(progressive._chain_comps(base_files, base).get("ActorPositionCalculatorRef"))
    out["cursor"] = {"from": calc if calc in base_files else None, "actor_op": actor_op, "wants": []}
    out["cursor_base"] = cursor_base(base_files, base)
    row = dict(keys, __RowId=shelf, ActorName=name or shelf, ModelAabbMin=lo, ModelAabbMax=hi)
    row["AnimationResources"] = [dict(r) for r in anim_res] if anim_res else [{"ModelProjectName": "Item_Common_Animation"}]
    for k in progressive.HEAPS:
        row[k] = max(int(r.get(k) or 0) for r in involved)
    out["byml"].append({"file": ACTOR_INFO_TABLE, "add_row": {"copy_of": base, "set": row}, "note": note})
    gset = {"__RowId": shelf}
    pose = (grows.get(src["model_from"] or "") or {}).get("ModelVariationAnims")
    if pose:
        gset["ModelVariationAnims"] = [dict(p) for p in pose]
    out["byml"].append({"file": GAME_ACTOR_INFO_TABLE, "add_row": {"copy_of": base, "set": gset}})
    # its pouch row (POUCH_INFO_TABLE) is the placeholder's, so the shop treats the pick like the placeholder's, with
    # the BuyingPrice that _shop_ops offsets the slot's price from
    base_price = (shop_map()["shop_actors"].get(base) or {}).get("price")
    if base not in _table(POUCH_INFO_TABLE) or base_price is None:
        raise ShopError(f"{base}: no PouchActorInfo row / BuyingPrice to copy for {shelf}")
    out["byml"].append({"file": POUCH_INFO_TABLE, "add_row": {"copy_of": base, "set": {
        "__RowId": shelf, "BuyingPrice": int(base_price)}}, "note": f"{shelf}: the price window's BuyingPrice"})
    out["text"] = _shelf_text(shelf, display, name, own)
    if not src["provided"]:  # as the shelf draws it (posed_box), a model of ours is drawn as made (its own bounds)
        lo, hi = posed_box(keys.get("ModelProjectName"), keys.get("FmdbName"), _banks(anim_res), (lo, hi))
    ext = _extent(lo, hi)
    scale = 1.0
    if ext:
        want = min(max(ext, SHELF_SIZE[0]), SHELF_SIZE[1])
        if max(want / ext, ext / want) >= SHELF_SCALE_STEP:
            scale = round(want / ext, 4)
    out["scale"] = scale
    out["aabb"] = (lo, hi)
    return out


def _shelf_text(shelf, display, name, own=None):
    """Text ops for every language.
    Adds the shelf caption <name>_ShopCaption where the game has none, copied from the item's own caption, else its
    get caption, else its name. With no name actor (souls, the Skeleton Key, which the plugins that add them only
    name in English) it adds <shelf>_Name and _ShopCaption with OoTR item `own`'s name."""
    labels = _labels().labels
    src_name = name
    if name is None:
        if not own:
            raise ShopError(f"{shelf}: no name for {display}")
        return [{"lang": "*", "file": POUCH_MSG, "label": f"{shelf}_{s}", "markup": own, "add": True,
                 "note": f"{shelf}: named {own}"} for s in ("Name", "ShopCaption")]
    want = []
    if f"{name}_ShopCaption" not in labels:
        want.append((f"{name}_ShopCaption",
                     tuple(f"{src_name}_{s}" for s in ("ShopCaption", "Caption", "GetCaption", "Name"))))
    ops = []
    for label, sources in want:
        for lang in TEXT_LANGS:
            m = _labels(lang)
            src = next((s for s in sources if s in m.labels), None)
            if src is None:
                raise ShopError(f"{shelf}: {lang} has none of {sources}")
            ops.append({"lang": lang, "file": POUCH_MSG, "label": label, "markup": m.markup(src), "add": True,
                        "note": f"{shelf}: {label} (from {src})"})
    return ops


def _gd_names():
    if "gd" not in _shelf_cache:
        from romtools import byml_load, murmur3_32  # noqa: F401
        root = byml_load(_fs().read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
        _shelf_cache["gd"] = {int(r["Hash"]) for t, rs in root["Data"].items() if isinstance(rs, list)
                              for r in rs if isinstance(r, dict) and "Hash" in r}
    return _shelf_cache["gd"]


def _has_flag(name):
    from romtools import murmur3_32
    return murmur3_32(name) in _gd_names()


def _owned_steps(tier_actors):
    """BoolExp steps (reverse Polish): any IsGet.<actor> of `tier_actors` true."""
    steps = []
    for i, a in enumerate(tier_actors):
        steps.append([0, f"IsGet.{a}"])
        if i:
            steps.append([4])
    return steps


def tier_exps(item, flag, slot_no):
    """{expression name: steps} that show each tier's shelf of progressive deal item `item`, or None if a tier has no
    IsGet flag to read.
    Tier t shows when the tiers below are owned and t isn't. The top tier shows when the one below is owned. Tier 0
    also shows once the slot is sold, so the vanilla shelf stays for the sold-out board."""
    import progressive
    ex = sys.modules.get("parity.extras_items")
    tiers = progressive.PROGRESSIVE[ex.target_name(item) if ex is not None else item]["tiers"]
    # the IsGet flags the game has for each tier's owned actors and their names, like the gauntlets' equipment actors
    # IsGet.Armor_Child_Gauntlet_Goron / Armor_Adult_Gauntlet_Silver / _Gold. The slot's flag is this plan's own
    # (add_bools).
    owned = [[a for a in dict.fromkeys(progressive.owned_by(t) + [name_actor(x) for x in progressive.owned_by(t)])
              if _has_flag(f"IsGet.{a}")] for t in tiers]
    if not all(owned):
        return None
    top = len(tiers) - 1
    out = {}
    for t in range(top + 1):
        if t == 0:
            steps = _owned_steps(owned[0]) + [[5], [0, flag], [5], [4]]
        else:
            steps = _owned_steps(owned[t - 1])
            if t < top:
                steps += _owned_steps(owned[t]) + [[5], [3]]
            steps += [[0, flag], [3]]
        out[SHELF_TIER_EXP.format(slot_no, t)] = steps
    return out


def _level_actors(file):
    key = ("actors", file)
    if key not in _shelf_cache:
        from romtools import byml_load
        root = byml_load(_fs().read(file), allow_big=True)
        root = root[0] if isinstance(root, tuple) else root
        _shelf_cache[key] = {str(a.get("Hash")): a for a in root.get("Actors") or []}
    return _shelf_cache[key]


def _level_hashes(file):
    key = ("level", file)
    if key not in _shelf_cache:
        _shelf_cache[key] = set(_level_actors(file))
    return _shelf_cache[key]


def shelf_turn(rotate):
    """(yaw, tilted) of a placement's Rotate.
    (+-pi, y, +-pi) is a turn of pi - y about the vertical with nothing tilted (Rz(pi) Ry(y) Rx(pi) = Ry(pi - y),
    either order). 62 of the shops' shelf items are placed like that (the Goron, Kakariko potion, Bombchu and Zora
    shops). Any other x or z turn tilts it."""
    import math
    r = [float(v) for v in (rotate or [0.0, 0.0, 0.0])]
    if abs(abs(r[0]) - math.pi) < 1e-3 and abs(abs(r[2]) - math.pi) < 1e-3:
        return math.pi - r[1], False
    return r[1], abs(r[0]) > 1e-3 or abs(r[2]) > 1e-3


def _shelf_place(s, built):
    """Placement sets that put shelf type `built` (shelf_type_ops) where the vanilla item of shelf `s` stood.
    That's the model's size (Scale, a list like the level files hold it), with its centre on the vanilla item's
    centre and its base on the vanilla item's base. Both models are taken as the shelf draws them (posed_box).
    Translate is the offset of the two models' bounding boxes, turned by the placement's yaw:
    world = (x cos + z sin, y, -x sin + z cos). The shops' count boards confirm that convention, each board stands
    at the same spot in front of its item in that frame whatever the shelf's turn."""
    import math
    a = _level_actors(s["file"]).get(str(s["hash"])) or {}
    t, r = a.get("Translate"), a.get("Rotate") or [0.0, 0.0, 0.0]
    s0 = a.get("Scale") or [1.0, 1.0, 1.0]
    vlo, vhi = actor_shelf_box(s["gyaml"])  # the vanilla item as the shelf draws it (posed_box)
    lo, hi = built["aabb"]
    sc = built["scale"]
    ext, vext = _extent(lo, hi), _extent(vlo, vhi)
    if built.get("fit", True) and ext and vext:  # no larger than SHELF_FIT times the shelf's own item
        cap = max(SHELF_SIZE[0], min(SHELF_SIZE[1], vext * max(float(x) for x in s0) * SHELF_FIT))
        want = min(max(ext, SHELF_SIZE[0]), cap)
        sc = round(want / ext, 4) if max(want / ext, ext / want) >= SHELF_SCALE_STEP else 1.0
    sets = {}
    if sc != 1.0:
        sets["Scale"] = [round(sc * float(x), 4) for x in s0]
    if not (t and vlo and vhi and lo and hi):
        return sets
    dx = ((vlo["X"] + vhi["X"]) / 2) * s0[0] - ((lo["X"] + hi["X"]) / 2) * sc
    dy = vlo["Y"] * s0[1] - lo["Y"] * sc
    dz = ((vlo["Z"] + vhi["Z"]) / 2) * s0[2] - ((lo["Z"] + hi["Z"]) / 2) * sc
    # (pi, y, pi) is just yaw. Getting that wrong put Zora's Skull Mask 0.17 m off its shelf.
    yaw, tilted = shelf_turn(r)
    if tilted:  # only align the base when the shelf item really is tilted
        dx = dz = 0.0
    c, sn = math.cos(yaw), math.sin(yaw)
    move = (dx * c + dz * sn, dy, -dx * sn + dz * c)
    if max(abs(m) for m in move) >= 0.002:
        sets["Translate"] = [round(float(t[i]) + move[i], 4) for i in range(3)]
    return sets


def _board_type(board, s):
    """Whether count board type `board` can stand by shelf `s`, so its level places it or (with NEW_TYPES) the game has
    it."""
    if board in shop_map()["stage_shop_types"].get(s["stage"], ()):
        return True
    return NEW_TYPES and os.path.exists(os.path.join(DEFAULT_ROMFS, f"Pack/Actor/{board}.pack.zs"))


def _never_shown(s):
    """Shelf `s` is the KF shop's short stock, which the stock gate never shows once a KF slot changes."""
    pres = s.get("presence") or {}
    return pres.get("FlagName") == KF_STOCK_GATE and bool(pres.get("IsNegation"))


SOLD_BOARD = "Shop_Board_SoldOut"
SOLD_SHIFT = (0.0, 0.009, 0.059)  # (x, y, z) m in the board frame: a SOLD OUT board's origin from a count board's on
#                                  one label (KF slot 2's short stock links both, used where a level has no such pair)


def _rot(v, yaw, back=False):
    """v turned by yaw in the frame the level files use, world = (x cos + z sin, y, -x sin + z cos). back=True undoes
    it."""
    import math
    c, sn = math.cos(yaw), math.sin(yaw)
    x, y, z = (float(t) for t in v)
    return (x * c - z * sn, y, x * sn + z * c) if back else (x * c + z * sn, y, -x * sn + z * c)


def _vanilla_boards(file):
    """[(shelf actor, board actor)] for every vanilla shelf item of level `file` and each board it links (any shop of
    the level, whether its stocks are shown or not)."""
    key = ("boards", file)
    if key not in _shelf_cache:
        acts = _level_actors(file)
        out = []
        for a in acts.values():
            g = str(a.get("Gyaml", ""))
            if not g.startswith("Shop_") or g.startswith("Shop_Board_"):
                continue
            for ln in a.get("Links") or []:
                b = acts.get(str(ln.get("Dst")))
                if b is not None and str(b.get("Gyaml", "")).startswith("Shop_Board_"):
                    out.append((a, b))
        _shelf_cache[key] = out
    return _shelf_cache[key]


def _area_boards(file):
    """_vanilla_boards of every shop level file in `file`'s folder.
    A shop's child, adult and alternative levels place its shelves at the same spots (KF's child and adult stick
    spots are 0.5 mm apart), so one level's boards tell us where the other's go."""
    d = os.path.dirname(file)
    files = sorted({sh["file"] for loc in shop_map()["locations"].values()
                    for sh in ((loc.get("edit") or {}).get("shelves") or []) if os.path.dirname(sh["file"]) == d}
                   | {file})
    return [p for f in files for p in _vanilla_boards(f)]


def _sold_shift(file):
    """A SOLD OUT board's origin minus a count board's on one label, in the boards' frame.
    Taken from a vanilla shelf item of the level's area that links both (KF's short-stock nuts, the Bazaar's bombs),
    else SOLD_SHIFT."""
    by_shelf = {}
    for a, b in _area_boards(file):
        by_shelf.setdefault(str(a["Hash"]), []).append(b)
    for boards in by_shelf.values():
        sold = [b for b in boards if b["Gyaml"] == SOLD_BOARD]
        count = [b for b in boards if b["Gyaml"].startswith("Shop_Board_Bundle_")]
        if sold and count:
            yaw = float((count[0].get("Rotate") or [0, 0, 0])[1])
            return tuple(t - u for t, u in zip(_rot(sold[0]["Translate"], yaw, True),
                                               _rot(count[0]["Translate"], yaw, True)))
    return SOLD_SHIFT


def _board_spot(s, board):
    """(Translate, Rotate, the vanilla board copied) of a new `board` (a count board or SOLD_BOARD) by shelf `s`, or
    None when the level has no board.
    It goes where vanilla puts that board, on the label of the shelf's row (placed any other way, the new "x10" hung
    below the shelf, half behind the counter). The reference is a vanilla board of the level, one linked from a shelf
    item at this very spot (another stock's, like KF's short stock), else from the nearest item on the same row
    (within 0.2 m of height, 1.2 m across). In the board's frame a row's boards share their depth and height (the
    label), and across the row the new board keeps the reference's offset from its own item. A SOLD OUT board stands
    _sold_shift from where a count board would, and the other way round."""
    import math
    a = _level_actors(s["file"]).get(str(s["hash"]))
    pairs = _area_boards(s["file"])
    if a is None or not pairs:
        return None
    t = [float(v) for v in a["Translate"]]

    def rank(p):
        st = [float(v) for v in p[0]["Translate"]]
        same = math.dist(st, t) < 0.02
        row = abs(st[1] - t[1]) < 0.2 and math.hypot(st[0] - t[0], st[2] - t[2]) < 1.2
        return (not same, not row, math.dist(st, t), str(p[1]["Hash"]))
    sh, ref = min(pairs, key=rank)
    yaw = float((ref.get("Rotate") or [0, 0, 0])[1])
    lb, ls, la = (_rot(x, yaw, True) for x in (ref["Translate"], sh["Translate"], t))
    local = [la[0] + (lb[0] - ls[0]), float(ref["Translate"][1]), lb[2]]
    if abs(float(sh["Translate"][1]) - t[1]) >= 0.2:  # another row, its height comes from the reference's offset
        local[1] = t[1] + float(ref["Translate"][1]) - float(sh["Translate"][1])
    shift = _sold_shift(s["file"])
    sign = (board == SOLD_BOARD) - (ref["Gyaml"] == SOLD_BOARD)
    local = [local[q] + sign * shift[q] for q in range(3)]
    pos = [round(v, 4) for v in _rot(local, yaw)]
    rot = [float(v) for v in (ref.get("Rotate") or [0.0, 0.0, 0.0])]
    return pos, rot, ref


def _board_ops(plan, s, board, note):
    """Placement ops that stand a new `board` (a count board, or SOLD_BOARD for a one-time slot) by shelf `s`, or []
    when the level has no board to copy.
    The board is a twin of a vanilla board of the level, where _board_spot puts it, shown when the shelf is. It's
    linked the way vanilla boards are, from the shelf item and from the shopkeeper (Reference, and keeper_ops gives the
    keeper's twins the same links)."""
    spot = _board_spot(s, board)
    if spot is None:
        return []
    pos, rot, ref = spot
    # The reference stands in another level of the area, so the twin copies this level's nearest board, placed and
    # turned the way the reference says.
    if str(ref["Hash"]) not in _level_actors(s["file"]):
        import math
        own = [b for _, b in _vanilla_boards(s["file"])]
        if not own:
            return []
        ref = min(own, key=lambda b: (math.dist([float(v) for v in b["Translate"]], pos), str(b["Hash"])))
    new = _twin_hash(s["file"], str(ref["Hash"]), 1 if board != SOLD_BOARD else 2)
    sets = {"Gyaml": board, "Translate": pos, "Rotate": rot}
    pres = s.get("presence")
    if pres and pres.get("FlagName") != KF_STOCK_GATE:
        sets["Presence"] = dict(pres)  # shown when its shelf is, the KF gate's own shelves show from the start
    op = {"file": s["file"], "hash": str(ref["Hash"]), "twin": new, "join_groups": False, "set": sets,
          "note": f"{note} (new, next to shelf {s['hash']})"}
    if "Presence" not in sets and ref.get("Presence"):
        op["remove"] = ["Presence"]
    ops = [op, {"file": s["file"], "hash": str(s["hash"]), "add_links": [{"dst": new}],
                "note": f"{note}: the shelf item links its board"}]
    keeper = str(s.get("npc_hash") or "")
    if keeper in _level_actors(s["file"]):
        ops.append({"file": s["file"], "hash": keeper, "add_links": [{"dst": new}],
                    "note": f"{note}: the shopkeeper links the board"})
        plan.setdefault("_keeper_boards", {}).setdefault((s["file"], keeper), []).append(new)
    return ops


KEEPER_EXP = "Rando_ShopKeepT_{}_{}"  # a shopkeeper twin's Presence, from the tiers its shelves show (keeper_ops)


def keeper_ops(plan, notes):
    """Placement ops and expressions that give each shopkeeper with tier shelves one keeper per tier combination.

    The shop finds what it sells through the keeper's ForSale links. main 0x28898e0 walks them, reads each linked
    item's ShopItemIndex and keeps the item in that slot's record, and the last link wins. A placement its Presence
    hides still counts, so with the Longshot shelf linked after the Hookshot's, the shown Hookshot can't be picked
    ("like it doesn't exist").

    So a keeper links exactly one shelf per slot, like every vanilla keeper does (16 keepers, 8 ForSale links each,
    no index twice), and the tiers switch keepers instead. That's how the KF shop switches its full and short stock:
    two keepers, each with its own shelves, shown by complementary Presences. The vanilla keeper shows for every
    slot's tier 0, and a twin of it shows for each other combination. The twin's Presence is an expression ANDing each
    slot's tier expression, and its links to each slot's tier-0 shelf are retargeted at that tier's shelf (make_patch
    "relink"). Twins join the keeper's actor groups (only one is ever shown) but not its logic groups (the Bazaar's
    and the Goron shop's, with constant inputs and emotion flags).

    A keeper the game shows by a Presence of its own keeps it, like the Bombchu Shop's after King Dodongo
    (Get_StoneOfFire_IsCompleted_Exp). Each combination's expression ANDs the keeper's own condition (_gate_steps).
    Without that, such a keeper gets no twins and its shop's tier shelves aren't for sale (the Bombchu Shop's
    quivers)."""
    import itertools
    import zlib
    tiers = plan.pop("_keeper_tiers", {})
    plan_boards = plan.pop("_keeper_boards", {})
    exps = plan.get("_shelf_exps") or {}
    ops, new_exps = [], {}
    for (file, keeper), slots in sorted(tiers.items()):
        slots = sorted(slots, key=lambda x: x["slot"])
        k = _level_actors(file).get(str(keeper))
        if k is None:
            notes.append(f"{file}: no shopkeeper {keeper}: its tier shelves show tier 0 only")
            continue
        pres = k.get("Presence") or {}
        gate = []
        if pres and pres.get("FlagName") != KF_STOCK_GATE:  # not the KF gate, stock_gate_ops always shows its stock
            gate = _gate_steps(pres)
            if gate is None:
                notes.append(f"{k['Gyaml']}: shown by {pres.get('FlagName')}, which no expression reads: its tier "
                             f"shelves show tier 0 only")
                continue
        tag = f"{zlib.crc32(f'{file}|{keeper}'.encode()) & 0xFFFF:04X}"
        for n, combo in enumerate(itertools.product(*[range(len(x["tiers"])) for x in slots])):
            steps = []
            for q, (x, t) in enumerate(zip(slots, combo)):
                steps += exps[x["tiers"][t][0]]
                if q:
                    steps.append([3])  # AND
            if gate:
                steps += gate + [[3]]  # AND the keeper's own condition
            exp = KEEPER_EXP.format(tag, "".join(map(str, combo)))
            new_exps[exp] = steps
            shown = {"Presence": {"FlagName": exp, "IsCheckLazy": False, "IsNegation": False}}
            what = ", ".join(f"slot {x['slot']} tier {t}" for x, t in zip(slots, combo))
            if not any(combo):
                ops.append({"file": file, "hash": str(keeper), "set": shown,
                            "note": f"{k['Gyaml']}: shown for {what}"})
                continue
            relink = {str(x["tiers"][0][1]): str(x["tiers"][t][1]) for x, t in zip(slots, combo) if t}
            boards = plan_boards.get((file, str(keeper))) or []
            ops.append({"file": file, "hash": str(keeper), "twin": _twin_hash(file, str(keeper), 1 + n % 15),
                        "set": shown, "relink": relink, **({"add_links": [{"dst": b} for b in boards]} if boards else {}),
                        "note": f"{k['Gyaml']} twin: shown for {what}"})
    if new_exps:
        plan.setdefault("_shelf_exps", {}).update(new_exps)
    return ops


def _gate_steps(pres):
    """BoolExp steps (reverse Polish) that are true when Presence `pres` shows its placement, or None for any other
    kind of flag.
    That's a Bool flag's value, or an expression's steps as the game's GameDataList defines them, negated with
    IsNegation. The steps get copied in because a step names flags, not expressions."""
    from romtools import byml_load, murmur3_32
    if "gate_rows" not in _shelf_cache:
        gd = byml_load(_fs().read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]["Data"]
        _shelf_cache["gate_rows"] = ({int(r["Hash"]) for r in gd.get("Bool") or []},
                                     {int(r["Hash"]): r["Values"] for r in gd.get("BoolExp") or []})
    bools, bool_exps = _shelf_cache["gate_rows"]
    h = murmur3_32(pres["FlagName"])
    if h in bool_exps:
        steps = [[int(v) for v in x] for x in bool_exps[h]]
    elif h in bools:
        steps = [[0, pres["FlagName"]]]
    else:
        return None
    return steps + ([[5]] if pres.get("IsNegation") else [])


def _twin_hash(file, h, t):
    taken = _level_hashes(file)
    for k in range(1, 64):
        c = str(int(h) ^ (t << 20) ^ (k << 8))
        if c not in taken:
            taken.add(c)
            return c
    raise ShopError(f"{file}: no free hash for a twin of {h}")


def _shelf_ops(plan, notes, name, e, base, item, looks, flag=None, slot_no=0):
    """The shelf types that show `looks` ([(display, name actor)] from shelf_look) of OoTR item `item` at slot `name`
    (placeholder `base`), built once per plan (plan["_shelf_types"]).
    Returns (tier 0's type, the placement ops for the slot's shelves), or (None, []) if the look can't be made and
    the placeholder stays. The ops set the scale, and a progressive item's tiers become twins shown by their
    expressions. flag is the slot's in-stock flag. _shop_ops sells and places the type."""
    built = plan.setdefault("_shelf_types", {})
    types = []
    for display, nm in looks:
        shelf = shelf_type(base, display, nm, item)
        if shelf not in built:
            try:
                built[shelf] = shelf_type_ops(shelf, base, display, nm, item)
            except ShopError as ex:
                notes.append(f"{name}: no shelf look ({ex}); the placeholder {base} stays")
                return None, []
        types.append(shelf)
    exps = None
    if len(types) > 1:
        exps = tier_exps(item, flag, slot_no) if flag else None
        if exps is None:
            notes.append(f"{name}: tier shelves need IsGet flags the game lacks: it shows tier 0 only")
            types = types[:1]
    ops = []
    for s in e["shelves"]:
        pres = s.get("presence") or {}
        # The KF shop's stock gate (stock_gate_ops, this slot changes). The short stock's shelf is never shown and the
        # full stock's shows from the start, with its Presence ours (plan_ops leaves the gate's removal of it out).
        if pres.get("FlagName") == KF_STOCK_GATE:
            if pres.get("IsNegation"):
                continue
            s = dict(s, presence=None)
        if s.get("presence") and not e.get("ungate_shelves") and exps:
            notes.append(f"{name}: shelf {s['hash']} is gated by {s['presence'].get('FlagName')}: tier 0 only")
        for t, shelf in enumerate(types):
            sets = {"Gyaml": shelf} if t else {}
            sets.update(_shelf_place(s, built[shelf]))  # its size and its centre on the vanilla item's
            if exps and not (s.get("presence") and not e.get("ungate_shelves")):
                sets["Presence"] = {"FlagName": SHELF_TIER_EXP.format(slot_no, t), "IsCheckLazy": False,
                                    "IsNegation": False}
            elif t:
                break
            built[shelf]["cursor"]["wants"].append(_cursor_want(built[shelf], sets.get("Scale")))  # (CURSOR_REF)
            if t == 0:
                if sets:
                    ops.append({"file": s["file"], "hash": s["hash"], "set": sets,
                                "note": f"{name}: shelf {shelf} sized/shown as tier 0"})
            else:
                twin = _twin_hash(s["file"], s["hash"], t)
                ops.append({"file": s["file"], "hash": s["hash"], "twin": twin,
                            "set": sets, "note": f"{name}: tier {t} shelf {shelf}"})
            if exps and not (s.get("presence") and not e.get("ungate_shelves")) and s.get("npc_hash"):
                # its keeper sells one tier's shelf at a time (keeper_ops)
                kt = plan.setdefault("_keeper_tiers", {}).setdefault((s["file"], str(s["npc_hash"])), [])
                if t == 0:
                    kt.append({"slot": slot_no, "tiers": [(SHELF_TIER_EXP.format(slot_no, 0), str(s["hash"]))]})
                else:
                    kt[-1]["tiers"].append((SHELF_TIER_EXP.format(slot_no, t), twin))
    if exps:
        plan.setdefault("_shelf_exps", {}).update(exps)
    notes.append(f"{name}: shelf shows {', '.join(types)} ("
                 + ", ".join(f"{d} named {n or 'its own'}" for d, n in looks[:len(types)]) + ")")
    return types[0], ops


def extra_rule(ootr_name):
    """An OoTR rule the remake adds to this location (AND it with OoTR's own), or None."""
    loc = shop_map()["locations"].get(ootr_name) or {}
    return (loc.get("edit") or {}).get("requires")


def plan_ops(assignments, allow_new_types=NEW_TYPES, appearance="anything", looks_like=None, deals=(), majors=(),
             ice_calls=None):
    """{OoTR location: (OoTR item, price)} -> plan sections in tools/make_patch.py's format
    ("packs", "placements", "events", "text", plus "_notes"). Raises ShopError on anything it can't make.
    price None means a merchant's vanilla OoT price (OoTR gives merchants none).
    For ice traps, appearance is OoTR's ice_trap_appearance and looks_like is {location: OoTR item an ice trap there
    looks like} (OoTR's looks_like_item).
    deals are the special-deal locations (OoTR world.shop_prices). Their items that a shelf can't sell go through the
    deal path (_deal_ops). majors are the items shown with a major look there."""
    looks_like = looks_like or {}
    _ice_calls.clear()
    _ice_calls.update(ice_calls or {})
    deal_nodes, deal_flags = [], []
    plan = {"packs": [], "placements": [], "events": [], "text": []}
    notes = []
    texts = {}
    converted = []
    for name, (item, price) in sorted(assignments.items()):
        loc = shop_map()["locations"].get(name)
        if loc is None:
            raise ShopError(f"{name}: not a shop, scrub or merchant location in data/rando/shop_map.json")
        reason = why_not(name, item, allow_new_types, name in deals)
        if reason:
            raise ShopError(f"{name}: can't sell {item!r}: {reason}")
        if loc["mode"] != "full" or _keeps_remake_vanilla(loc, item):
            continue  # its vanilla item, nothing to change
        if price is None and loc["kind"] == "merchant":
            price = loc["edit"]["default_price"]
        if price is None:
            raise ShopError(f"{name}: no price")
        price = int(price)
        if not 0 <= price <= MAX_PRICE:
            raise ShopError(f"{name}: price {price} outside 0..{MAX_PRICE}")
        if loc["edit"].get("converted"):
            converted.append((name, loc["edit"], item, price))
        elif loc["kind"] == "merchant" and (call_marker(item, loc["edit"]) or _hold_hand_over(item, loc["edit"])):
            _dungeon_merchant_ops(plan, notes, name, loc["edit"], item, price)
        elif item == ICE and ice_deal(name, loc, ice_look(name, appearance, looks_like), name in deals):
            # an ice trap in a special deal is shown and named as its disguise, and the deal steps freeze Link
            trap = ice_deal(name, loc, ice_look(name, appearance, looks_like), True)
            k = len(deal_nodes)
            deal_nodes.append(_deal_ops(plan, notes, name, loc["edit"], item, price, True, k,
                                        looks_like=ice_look(name, appearance, looks_like), give=trap))
            deal_flags.append(deal_flag(name))
            _deal_record(plan, name, loc, item, price, deal_nodes[-1][f"g{k}"])
        elif item == ICE:
            _ice_ops(plan, notes, name, loc, price, appearance, looks_like.get(name))
        elif uses_deal(name, item, allow_new_types, name in deals):
            deal_nodes.append(_deal_ops(plan, notes, name, loc["edit"], item, price, item in majors, len(deal_nodes)))
            k = len(deal_nodes) - 1
            deal_flags.append(deal_flag(name))
            _deal_record(plan, name, loc, item, price, deal_nodes[-1][f"g{k}"])
        elif loc["kind"] == "shop":
            _shop_ops(plan, notes, name, loc["edit"], item, price)
        elif loc["kind"] == "merchant":
            _merchant_ops(plan, notes, name, loc["edit"], item, price)
        else:
            _scrub_ops(plan, notes, texts, name, loc["edit"], item, price)
    if converted:
        _converted_ops(plan, notes, texts, converted)
    if deal_nodes:
        nodes = {}
        for k, part in enumerate(deal_nodes):
            nxt = f"s{k + 1}" if k + 1 < len(deal_nodes) else "@" + DEAL_NEXT
            nodes.update({lab: _route(n, "@next", nxt) for lab, n in part.items()})
        plan["events"].append({"file": DEAL_FILE, "flowchart": DEAL_FILE, "add_graph": DEAL_GRAPH, "nodes": nodes,
                               "start": "s0", "note": f"{len(deal_nodes)} special deal(s) sold by their own steps"})
        plan["events"].append({"file": DEAL_FILE, "flowchart": DEAL_FILE, "entry": DEAL_ENTRY,
                               "next": f"{DEAL_GRAPH}_s0"})
        plan["gamedata"] = [{"add_bools": {f: True for f in sorted(deal_flags)}}]
    plan["placements"] += keeper_ops(plan, notes)  # before the stock gate and the expressions' merge
    _merge_shelf_types(plan, notes)
    for shop, ops in (shop_map().get("stock_gates") or {}).items():
        if any(n.startswith(shop + " Item ") and shop_map()["locations"][n]["mode"] == "full"
               and not _keeps_remake_vanilla(shop_map()["locations"][n], it)
               and it != shop_map()["locations"][n]["vanilla"] for n, (it, _p) in assignments.items()):
            # keep any Presence the slot already set, tier shelves and hidden boards included.
            # Removing it here brings the old count tags back.
            mine = {(op["file"], str(op["hash"])) for op in plan["placements"] if op.get("twin") is None
                    and any(k == "Presence" or k.startswith("Presence.") for k in (op.get("set") or {}))}
            plan["placements"] += [dict(op) for op in ops if (op["file"], str(op["hash"])) not in mine]
            notes.append(f"{shop}: full stock shown from the start (its short stock waits for {KF_STOCK_GATE})")
    for (lang, label), runs in sorted(texts.items()):
        mfile, mlabel = label.split("/", 1)[1].split(":")
        plan["text"].append({"lang": lang, "file": f"EventFlowMsg/{mfile}.msbt", "label": mlabel, "text": runs})
    _split_ops(plan)
    plan["_notes"] = notes
    plan["_got_flags"] = got_flags(assignments, deal_flags)
    return plan


def got_flags(assignments, deal_flags):
    """{check: tracker flag} for the sales plan_ops built: a special deal is got once its in-stock flag is false
    ("nbool"), a scrub or merchant once the sold flag its sale sets is true. A shelf sale and the Shadow Temple
    scrub (it dies after the sale) have neither."""
    out = {}
    for name, (item, _p) in sorted(assignments.items()):
        loc = shop_map()["locations"].get(name) or {}
        if loc.get("mode") != "full" or _keeps_remake_vanilla(loc, item):
            continue
        if deal_flag(name) in deal_flags:
            out[name] = {"t": "nbool", "n": deal_flag(name)}
        elif loc["kind"] in ("scrub", "merchant") and (loc.get("edit") or {}).get("sold_flag"):
            out[name] = {"t": "bool", "n": loc["edit"]["sold_flag"]}
    return out


def _deal_record(plan, name, loc, item, price, give):
    """The deal's read-back record (parity/_shops_deals.py): what the slot shows and sells, its flags and give."""
    plan.setdefault("_gaps", {}).setdefault("shop_deals", {"deals": {}})["deals"][name] = {
        "item": item, "price": price, "flag": deal_flag(name), "talking": TALKING[loc["edit"]["shop"]],
        "index": loc["edit"]["lists"][0]["index"], "look": plan["_deal_looks"][name],
        "give": {x: v for x, v in give.items() if x in ("call", "params")},
        "lists": sorted({(l["pack"], l["file"]) for l in loc["edit"]["lists"]})}


# an ice trap's disguise in a special deal when OoTR gave it none, picked by its ice_trap_appearance (major or junk
# items)
ICE_MAJOR = ("Boomerang", "Megaton Hammer", "Lens of Truth", "Hover Boots", "Iron Boots", "Mirror Shield",
             "Fire Arrows", "Light Arrows", "Dins Fire", "Farores Wind", "Bottle", "Kokiri Sword")
ICE_JUNK = ("Rupees (20)", "Rupees (50)", "Deku Nuts (5)", "Bombs (5)", "Arrows (10)", "Deku Stick (1)")


def ice_look(name, appearance, looks_like):
    """The item an ice trap in slot `name` looks like, OoTR's looks_like_item or else one of its appearance's kind."""
    if looks_like.get(name):
        return looks_like[name]
    pool = ICE_JUNK if appearance == "junk_only" else ICE_MAJOR if appearance == "major_only" else ICE_MAJOR + ICE_JUNK
    return pool[sum(map(ord, name)) % len(pool)]


def ice_deal(name, loc, looks_like, deal):
    """The freeze an ice trap in special deal `name` gives through the deal steps, as {"call": ...} with the chests
    plugin's trap kind (songs_trade._target).
    None if it's not a deal, OoTR gave no disguise, there's no shelf look for it or no freeze path. Then it gets the
    old shelf disguise (ice_disguise)."""
    if not deal or not looks_like or loc.get("kind") != "shop" or loc.get("mode") != "full":
        return None
    e = loc["edit"]
    if e.get("shop") not in TALKING or deal_look(e, True) is None or not shelf_look(ICE, looks_like):
        return None
    call = _ice_calls.get(name)
    return {"call": call} if call else None


_ice_calls = {}  # this plan's special deals holding an ice trap -> the trap kind's call (parity/shops.py: the chests
#                  plugin's trap_call for the seed's world)


def _merge_shelf_types(plan, notes=None):
    """Puts the shelf types this plan's slots show (_shelf_ops) into its sections, once each, along with their tier
    expressions."""
    built = plan.pop("_shelf_types", {})
    have = {op["to"] for op in plan.get("new_files", [])}
    texts = {(op["lang"], op["label"]) for op in plan["text"]}
    for shelf in sorted(built):
        ops = built[shelf]
        _cursor_ops(shelf, ops, notes if notes is not None else [])
        for op in ops["new_files"]:
            if op["to"] not in have:
                plan.setdefault("new_files", []).append(op)
                have.add(op["to"])
        plan["packs"] += ops["packs"]
        plan.setdefault("byml", []).extend(ops["byml"])
        for op in ops["text"]:
            if (op["lang"], op["label"]) not in texts:
                plan["text"].append(op)
                texts.add((op["lang"], op["label"]))
    exps = plan.pop("_shelf_exps", {})
    if exps:
        gd = plan.get("gamedata") or []
        plan["gamedata"] = ([gd] if isinstance(gd, dict) else list(gd)) + [{"add_boolexp": exps}]
    plan.pop("_deal_looks", None)


def _cursor_ops(shelf, built, notes):
    """Gives shelf type `shelf` (shelf_type_ops, with its placements made) its own calculator param, with a
    CursorYOffset that puts the shop's cursor on its model (CURSOR_REF).
    The param is a copy of its placeholder's, named after the type, and the type's ActorParam names it. There's one
    value per type, the mean of its placements' (_cursor_want), and we note it when they differ by more than
    CURSOR_SPREAD (a type shown at several scales)."""
    cur = built.get("cursor") or {}
    wants = [w for w in cur.get("wants") or () if w is not None]
    if not wants or not cur.get("from"):
        notes.append(f"{shelf}: the shop's cursor keeps its placeholder's height (no model bounds, target body or "
                     f"calculator param to set it from)")
        return
    off = round(sum(wants) / len(wants), 4)
    if max(wants) - min(wants) > CURSOR_SPREAD:
        notes.append(f"{shelf}: placed at scales wanting CursorYOffset {min(wants):+.3f}..{max(wants):+.3f} m; "
                     f"it takes {off:+.3f}")
    rel = cur["actor_op"]["pack"]
    path = CURSOR_REF.format(shelf)
    built["packs"].append({"pack": rel, "file": path, "new_from": cur["from"], "set": {"CursorYOffset": off},
                           "note": f"{shelf}: the shop's cursor on its model (CursorYOffset {off:+.3f} m)"})
    cur["actor_op"]["set"]["Components.ActorPositionCalculatorRef"] = "?" + path


def _shop_ops(plan, notes, name, e, item, price, actor=None, release=None, base=None):
    """Makes the slot sell and show `actor`. For a shelf type of ours, its placeholder `base` gives the price it's
    offset from, and it has no count board."""
    actors = shop_map()["shop_actors"]
    actor = actor or sellable(item, "shop")
    info = actors[base or actor]
    base_price = info["price"]
    if base_price is None:
        raise ShopError(f"{base or actor}: no BuyingPrice found")
    by_pack = defaultdict(dict)
    for l in e["lists"]:
        j = l["index"]
        sets = by_pack[(l["pack"], l["file"])]
        sets[f"GoodsList.{j}.Actor"] = f"Work/Actor/{actor}.engine__actor__ActorParam.gyml"
        sets[f"GoodsList.{j}.PriceOffset"] = price - base_price
        sets[f"GoodsList.{j}.ConditionalPriceOffsetList"] = []  # e.g. the Hylian Shield's -20 after the gate opens
        sets[f"GoodsList.{j}.StockNum"] = -1  # every shelf item is harmless to buy again, so no daily sold-out counter
        sets[f"GoodsList.{j}.Release"] = release or {"IsCheckReleaseGameData": False, "ReleaseGameData": "",
                                                     "IsCheckSoldOutGameData": False, "SoldOutGameData": ""}
    for (pack, file), sets in sorted(by_pack.items()):
        plan["packs"].append({"pack": pack, "file": file, "set": sets, "note": f"{name}: {item} for {price}"})
    # the shelf read-back's record (parity/_shops_deals.py verify_shelves), what the slot shows and at what price
    plan.setdefault("_gaps", {}).setdefault("shop_shelves", {"slots": {}})["slots"][name] = {
        "actor": actor, "price": price, "count": None if base else info.get("count"),
        "deal": bool((release or {}).get("IsCheckSoldOutGameData")),
        "lists": sorted([l["pack"], l["file"], l["index"]] for l in e["lists"])}
    if e.get("ungate_shelves"):  # a shelf shown only after a save flag (Market potion slot 6, the bug tutorial)
        for s in e["shelves"]:
            if s.get("presence"):
                plan["placements"].append({"file": s["file"], "hash": s["hash"], "remove": ["Presence"],
                                           "note": f"{name}: shelf shown from the start (was gated by "
                                                   f"{s['presence'].get('FlagName')})"})
    if actor in SCENE_GATE:
        notes.append(f"{name}: {actor} is sold only once {SCENE_GATE[actor]} is true (shop scene); fine for junk")
    if e.get("requires"):
        notes.append(f"{name}: needs OoTR rule {e['requires']} ({e['requires_why']})")
    count = None if base else info.get("count")
    for s in e["shelves"]:
        if s["gyaml"] != actor:
            sets = {"Gyaml": actor}
            row = _table(ACTOR_INFO_TABLE).get(actor)
            if row and not actor.startswith(SHELF_PREFIX):  # another shop item gets centred on the old one's spot
                # as the shelf draws both (posed_box). A shelf type of ours is placed by _shelf_ops.
                sets.update(_shelf_place(s, {"scale": 1.0, "aabb": actor_shelf_box(actor), "fit": False}))
            plan["placements"].append({"file": s["file"], "hash": s["hash"], "set": sets,
                                       "note": f"{name}: shelf shows {actor}"})
        want = f"Shop_Board_Bundle_{count:02d}" if count else None
        if want and not _board_type(want, s):
            notes.append(f"{name}: no count board for {count} in the game: {actor} shows none")
            want = None
        counted = [b for b in s["boards"] if b["gyaml"] != "Shop_Board_SoldOut"]
        if want and not counted and not _never_shown(s):
            # a bundle on a shelf whose vanilla item had no count board (Arrows (10) where a single Deku Stick stood)
            # gets its own board, placed where the shop's boards stand in front of their items (_board_ops)
            plan["placements"] += _board_ops(plan, s, want, f"{name}: count board for {count}")
        for b in counted:
            if want and want != b["gyaml"]:
                plan["placements"].append({"file": s["file"], "hash": b["hash"], "set": {"Gyaml": want},
                                           "note": f"{name}: count board for {count}"})
            elif want != b["gyaml"]:
                # No count board of the right number in this stage, or the item has no count. Hide the board then, so
                # we don't show the old shelf's number next to another item ("05" by a Goron Tunic, say). The shelf
                # links to it so it can't be deleted, but a Presence on the stage's own age never holds (the same
                # "never shown" switch as hide_shelves). A stage file both ages load just keeps the note.
                fn = s["file"].split("/")[-1]
                old = b["gyaml"].rsplit("_", 1)[1]
                if "_Child_" in fn or "_Adult_" in fn:
                    plan["placements"].append({"file": s["file"], "hash": b["hash"], "note":
                                               f"{name}: count board {old} hidden (no board for {actor})",
                                               "set": {"Presence.FlagName": "Sequence_IsChildhood",
                                                       "Presence.IsCheckLazy": False,
                                                       "Presence.IsNegation": "_Child_" in fn}})
                else:
                    notes.append(f"{name}: {fn} board {b['hash']} still shows {old} next to {actor}")


def _tiers(item, edit=None):
    """The actors a scrub's sale calls hand over for OoTR item `item`, one per tier. For an item given by its own
    entry it's just its marker (call_marker)."""
    marker = call_marker(item, edit, request=True)
    if marker:
        return [marker]
    return [_hand_actor(item)] if item not in PROGRESSIVE else shop_map()["scrub_items"][item]["tiers"]


def _hand_actor(item):
    """The actor a sale hands over for non-progressive OoTR item `item`. That's the songs/trade plugin's when it has
    one (a hatched egg, a mask, from the shared resolver songs_trade.item_for), else shop_map's."""
    st = sys.modules.get("parity.songs_trade")
    if st is not None:
        got = st.hand_actor(item)
        if got:
            return got
    return shop_map()["scrub_items"][item]["tiers"][0]


def _scrub_ops(plan, notes, texts, name, e, item, price):
    tiers = _tiers(item, e)
    calls = e["calls"]
    label = e["message"]
    graph = e["graph"]
    scene = {"file": e["scene"], "flowchart": e["scene"]}
    # call k sells tier k. Owning tier k (or above) sells tier k+1, and the top tier repeats
    nodes = {}
    if e["continue"]:  # HF Secret flow: check, then the vanilla flow (whose only sale call sells tier 0)
        nodes["sold"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                         "params": {"GameDataName": e["sold_flag"], "Index": -1},
                         "cases": {"0": "@" + e["no_sale"], "1": "@" + e["continue"]}}
    else:
        # the highest tier owned decides, same as tools/progressive.py. Owning tier k sells tier k+1, the top one
        # repeats and owning none sells tier 0. The queries answer case 0 = yes, case 1 = no.
        top = len(tiers) - 1
        first = _sale_target(nodes, calls, tiers, 0, price, label)
        if top > 0:
            order = list(range(top, -1, -1))
            for j, k in enumerate(order):
                nodes[f"has{j}"] = {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                                    "params": {"Actor": tiers[k], "Num": 1},
                                    "cases": {"0": _sale_target(nodes, calls, tiers, min(k + 1, top), price, label),
                                              "1": f"has{j + 1}" if j + 1 < len(order)
                                              else _sale_target(nodes, calls, tiers, 0, price, label)}}
            first = "has0"
        nodes = {"sold": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                          "params": {"GameDataName": e["sold_flag"], "Index": -1},
                          "cases": {"0": "@" + e["no_sale"], "1": first}}, **nodes}
    plan["events"].append(dict(scene, add_graph=graph, nodes=nodes, start="sold",
                               note=f"{name}: sold already ({e['sold_flag']}) -> no sale; else sell {item}"))
    plan["events"].append(dict(scene, event=e["route"]["event"], next=f"{graph}_sold",
                               **({"case": e["route"]["case"]} if "case" in e["route"] else {})))
    for k, c in enumerate(calls):
        if k >= len(tiers):
            break
        if c["actor"] != tiers[k]:
            plan["events"].append(dict(scene, event=c["event"], param="ActorName", value=tiers[k]))
        if c["price"] != price:
            plan["events"].append(dict(scene, event=c["event"], param="Price", value=price))
        if c["message"] != label:
            plan["events"].append(dict(scene, event=c["event"], param="SellerMessageId", value=label))
    for lang, runs in e["text"][label].items():
        texts[(lang, label)] = runs
    if e.get("requires"):
        notes.append(f"{name}: needs OoTR rule {e['requires']} ({e['requires_why']})")


def _sale_target(nodes, calls, tiers, k, price, label):
    """The label that sells tier k, which is its sale call.
    A tier Link can't hold up as it is (an ocarina, say) is sold the same way. make_patch's scrub hand-over
    intercept gives it its own hold-up inside the one-time sale (config/hold_up.json)."""
    return "@" + calls[k]["event"]


def _converted_ops(plan, notes, texts, items):
    """The converted scrubs in play.
    Their placements play the one-time row with their own key. One graph in the pouch root's key chain, after the
    vanilla keys' "no match" case, branches on the keys. Each branch checks the sold flag (set means no sale), else
    sells the tier the player is due (highest owned + 1, like tools/progressive.py) through a copy of the heart-piece
    scrub's one-time sale call and sets the sold flag on success. For an ice trap the copy runs the shared freezing
    hand-over (make_patch scrub_intercept_ops, with the ice-trap marker as ActorName). The one-time row's own
    after-sale step (the DMC scrub's location flag) only runs for the DMC key."""
    first = items[0][1]
    scene = {"file": first["scene"], "flowchart": first["scene"]}
    no_sale = "@" + first["chain"]["no_sale"]
    nodes = {}
    for i, (name, e, item, price) in enumerate(items):
        nxt = f"key{i + 1}" if i + 1 < len(items) else no_sale
        nodes[f"key{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                            "params": {"GameDataName": "Scrub_Business_TempItemName_00", "Value": e["key"],
                                       "Index": -1},
                            "cases": {"0": f"sold{i}" if e["sold_flag"] else f"sell{i}", "1": nxt}}
        done = f"done{i}" if e["sold_flag"] else None
        if e["sold_flag"]:
            nodes[f"sold{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                                 "params": {"GameDataName": e["sold_flag"], "Index": -1},
                                 "cases": {"0": no_sale, "1": f"sell{i}"}}
            nodes[f"done{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                                 "params": {"GameDataName": "ScrubBusiness_BuySuccess", "Index": -1},
                                 "cases": {"0": f"set{i}", "1": None}}
            nodes[f"set{i}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                                "params": {"GameDataName": e["sold_flag"], "Value": True, "Index": -1}, "next": None}
        if item == ICE:
            # the vanilla one-time sale with the ice-trap marker, its hand-over pays and freezes. That's make_patch's
            # scrub intercept inside the vanilla entry, because a copied sale left the scrub actor unbound.
            nodes[f"sell{i}"] = {"copy": e["template"], "next": done,
                                 "params_over": {"ActorName": _trap_marker(name), "Price": price,
                                                 "SellerMessageId": e["message"]}}
            notes.append(f"{name}: ice trap for {price} rupees: " + ("Link freezes" if _trap_marker(name) == ICE_MARKER
                         else f"its trap kind ({_trap_marker(name)})"))
        else:
            tiers = _tiers(item, e)
            top = len(tiers) - 1
            for t, actor in enumerate(tiers):
                nodes[f"sale{i}_{t}"] = {"copy": e["template"], "next": done,
                                         "params_over": {"ActorName": actor, "Price": price,
                                                         "SellerMessageId": e["message"]}}
            if top == 0:
                nodes[f"sell{i}"] = nodes.pop(f"sale{i}_0")
            else:  # owning tier k sells tier k+1, the top one repeats, owning none sells tier 0 (case 0 = yes)
                order = list(range(top, -1, -1))
                for j, k in enumerate(order):
                    lab = f"sell{i}" if j == 0 else f"has{i}_{j}"
                    nodes[lab] = {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                                  "params": {"Actor": tiers[k], "Num": 1},
                                  "cases": {"0": f"sale{i}_{min(k + 1, top)}",
                                            "1": f"has{i}_{j + 1}" if j + 1 < len(order) else f"sale{i}_0"}}
            notes.append(f"{name}: sells {item} for {price}, once"
                         + ("" if e["sold_flag"] else " (no sold flag: the scrub dies after the sale)"))
        for p in e["placements"]:
            sets = {"Dynamic.TalkEventName": e["row"], "Dynamic.ScrubBusiness_ShopItemActorName0": e["key"]}
            if p["attacked"]:
                sets["Dynamic.AttackedEventName"] = e["row"]
            plan["placements"].append({"file": p["file"], "hash": p["hash"], "set": sets,
                                       "note": f"{name}: one-time scrub, key {e['key']}"})
        for lang, runs in e["text"][e["message"]].items():
            texts[(lang, e["message"])] = runs
    plan["events"].append(dict(scene, add_graph=first["graph"], nodes=nodes, start="key0",
                               note="converted scrubs: " + ", ".join(n for n, *_ in items)))
    plan["events"].append(dict(scene, event=first["chain"]["after"], case=first["chain"]["case"],
                               next=f"{first['graph']}_key0"))
    g = first["heart_guard"]
    plan["events"].append(dict(scene, add_graph=first["graph"] + "_HeartFlag", start="q", nodes={
        "q": {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
              "params": {"GameDataName": "Scrub_Business_TempItemName_00", "Value": g["key"], "Index": -1},
              "cases": {"0": "@" + g["flag_step"], "1": None}}},
        note="the one-time row's DMC location flag: only after the DMC scrub's own sale"))
    plan["events"].append(dict(scene, event=g["event"], case=g["case"], next=f"{first['graph']}_HeartFlag_q"))


ICE = "Ice Trap"
ICE_MARKER = "Rando_IceTrap"  # tools/progressive.py's ICE_MARKER, a scrub sale's ActorName for an ice trap


def _trap_marker(name):
    """A scrub sale's ActorName for the trap at `name`.
    That's ICE_MARKER, or the effect entry of the trap kind it drew (the chests plugin's trap_call, via
    parity/shops.py). It's in tools/progressive.py CALL_MARKERS, so the intercept pays and calls it."""
    effect = (_ice_calls.get(name) or "").split(":", 1)[-1]
    return effect if effect.startswith("Rando_Trap_") else ICE_MARKER
# OoTR's ice_trap_appearance on a shelf: "major" looks (shields and tunics) or junk looks (the rest)
MAJOR_LOOKS = ("Shop_Weapon_Shield_Deku", "Shop_Weapon_Shield_Hylian", "Shop_Armor_Goron", "Shop_Armor_Zora")


def ice_disguise(e, appearance, looks_like=None, seed=""):
    """The Shop_* actor an ice trap on this shelf slot shows, or None if there's none.
    It's OoTR's looks_like item if a shelf sells it, else one of the appearance's kind. It's always a type every
    shelf of the slot already has in its level, and never one the game refuses at the shop's age."""
    stages = [s["stage"] for s in e["shelves"]]
    types = shop_map()["stage_shop_types"]
    common = set.intersection(*(set(types[st]) for st in stages)) if stages else set()
    ok = sorted(a for a in common if a in shop_map()["shop_actors"] and a in SHELF.values()
                and not a.startswith(("Shop_Bottle_", "Shop_BombchuBundle_"))  # needs an empty bottle / bomb bag
                and (AGE_GATE.get(a) in (None, e["ages"]) or (AGE_GATE.get(a) == "child" and e.get("shop") == "KF Shop")))
    if not ok:
        return None
    want = SHELF.get(looks_like) if looks_like else None
    if want in ok:
        return want
    pick = [a for a in ok if (a in MAJOR_LOOKS) == (appearance == "major_only")] if appearance != "anything" else ok
    pick = pick or ok
    return pick[sum(map(ord, seed)) % len(pick)]


def _ice_ops(plan, notes, name, loc, price, appearance, looks_like):
    """An ice trap at a sale.
      - Scrub: its sale call runs a copy of the scrub's one-time sale whose hand-over pays and freezes
        (_chests_scenes.scrub_graphs).
      - Carpet salesman: his SimpleShop call runs a copy whose hand-over freezes (_chests_scenes.simpleshop_graphs).
      - Shelf: a disguise at the price, which the shopkeeper hands over as that item. No freeze here, since every
        shop shares the shop scene and it can't tell one slot from another."""
    e = loc["edit"]
    if loc["kind"] == "shop":
        actor = ice_disguise(e, appearance, looks_like, name)
        if actor is None:
            raise ShopError(f"{name}: no disguise for an ice trap")
        _shop_ops(plan, notes, name, e, None, price, actor=actor)
        notes.append(f"{name}: ice trap shown as {actor} (a shelf can't freeze Link: it sells {actor})")
        return
    scene = {"file": e["scene"], "flowchart": e["scene"]}
    c = e["calls"][0]
    # the trap kind this location drew (remake_trap_weights, from the chests plugin's trap_call via parity/shops.py).
    # An ice trap gets its marker and sale, any other kind uses its effect entry as the marker and its sale copy.
    effect = _trap_marker(name)
    kind_sfx = "_" + effect[len("Rando_Trap_"):] if effect != ICE_MARKER else ""
    if loc["kind"] == "scrub":
        sale = {"copy": c["event"], "next": None,  # the marker, make_patch's scrub intercept pays and freezes
                "params_over": {"ActorName": effect, "Price": price,
                                "SellerMessageId": e["message"]}}
        if e["continue"]:  # HF Secret flow: the vanilla flow reaches its only sale call, so route that call instead
            plan["events"].append(dict(scene, add_graph=e["graph"] + "_Ice", nodes={"sale": sale}, start="sale"))
            for ev in _call_preds(e, c["event"]):
                plan["events"].append(dict(scene, **ev, next=f"{e['graph']}_Ice_sale"))
            nodes = {"sold": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                              "params": {"GameDataName": e["sold_flag"], "Index": -1},
                              "cases": {"0": "@" + e["no_sale"], "1": "@" + e["continue"]}}}
        else:
            nodes = {"sold": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                              "params": {"GameDataName": e["sold_flag"], "Index": -1},
                              "cases": {"0": "@" + e["no_sale"], "1": "sale"}}, "sale": sale}
        plan["events"].append(dict(scene, add_graph=e["graph"], nodes=nodes, start="sold",
                                   note=f"{name}: sold already -> no sale; else the ice-trap sale"))
        plan["events"].append(dict(scene, event=e["route"]["event"], next=f"{e['graph']}_sold",
                                   **({"case": e["route"]["case"]} if "case" in e["route"] else {})))
        notes.append(f"{name}: ice trap: {price} rupees, then " + (f"its trap kind ({effect})" if kind_sfx else
                     "Link freezes") + f" (once: {e['sold_flag']})")
    else:  # the carpet salesman
        plan["events"].append(dict(scene, add_graph=e["graph"], start="sold", nodes={
            "sold": {"actor": "UISystemActor", "action": "EventCloseRupeeDisplay", "params": {"IsWaitEnd": True},
                     "next": None}}))
        plan["events"].append(dict(scene, event=e["route"]["event"], case=e["route"]["case"],
                                   next=f"{e['graph']}_sold"))
        plan["events"].append(dict(scene, add_graph=e["graph"] + "_Ice", start="sale", nodes={
            "sale": {"copy": c["event"], "call": "SimpleShop:Rando_IceTrap_SimpleShopRoot" + kind_sfx,
                     "params_over": {"Price": price, "MinusRupeeValue": -price}, "next": None}}))
        for ev in _call_preds(e, c["event"]):
            plan["events"].append(dict(scene, **ev, next=f"{e['graph']}_Ice_sale"))
        plan["events"].append(dict(scene, event=e["price_event"], param="Value", value=price))
        notes.append(f"{name}: ice trap for {price} rupees: " + (f"its trap kind ({effect})" if kind_sfx else
                     "Link freezes") + f" (once: {e['sold_flag']})")
    if e.get("requires"):
        notes.append(f"{name}: needs OoTR rule {e['requires']} ({e['requires_why']})")


def _call_preds(e, event):
    """Routing ops (no file/flowchart) pointing every step that leads to the sale call `event` elsewhere."""
    import progressive
    from evfl import Evfl
    from romtools import Romfs
    d = os.path.join(DEFAULT_ROMFS, "Event", "EventFlow")
    files = sorted(f for f in os.listdir(d) if re.match(re.escape(e["scene"]) + r"(\.\d{3})?\.bfevfl\.zs$", f))
    fc = Evfl(Romfs(DEFAULT_ROMFS, os.path.join(HERE, "original")).read("Event/EventFlow/" + files[-1])).flowcharts[0]
    step = next(x for x in fc["events"] if x["name"] == event)
    out = []
    for kind, where, k in progressive.predecessors(fc, step):
        if kind == "entry":
            out.append({"entry": where})
        else:
            out.append(dict({"event": where}, **({kind: k} if kind in ("case", "fork") else {})))
    return out


def lock_vanilla(world, ItemFactory):
    """Locks the shop slots and scrubs this module keeps vanilla, with the item OoTR's own pool holds for them, so the
    pool still matches the empty locations. Returns the names locked.
    Call it after OoTR's Main.build_world_graphs, before the generator locks its other unpatchable locations
    (generate.lock_unpatchable) and fills."""
    return lock_vanilla_scrubs(world, ItemFactory) + lock_vanilla_shops(world, ItemFactory)


def lock_vanilla_scrubs(world, ItemFactory):
    """Locks unsupported scrubs with their pool item instead of their "Buy" name.
    With shuffle_scrubs on, OoTR's pool holds ItemPool.deku_scrubs_items[vanilla item] for each scrub ("Deku Nuts (5)"
    for "Buy Deku Nut (5)", say), not the "Buy" item. Locking an unsupported scrub with its "Buy" name, like
    generate.lock_unpatchable would, takes a shop item out of the shop pool. With shopsanity on that can be the only
    "Buy Deku Shield", and then a child can't leave Kokiri Forest."""
    from ItemPool import deku_scrubs_items
    names = shop_map()["locations"]
    pool, locked = world.itempool, []
    for loc in world.get_locations():
        if loc.type not in ("Scrub", "GrottoScrub") or loc.item is not None or loc.locked:
            continue
        if names.get(loc.name, {}).get("mode") == "full":
            continue
        want = deku_scrubs_items.get(loc.vanilla_item, loc.vanilla_item)
        want = [w[0] for w in want] if isinstance(want, list) else [want]
        item = next((it for it in pool if it.name in want), None)
        if item is not None:
            pool.remove(item)
        else:  # OoTR placed none for it (with shuffle_scrubs off it already holds its vanilla item, skipped above)
            item = ItemFactory(want[0], world)
            junk = next((it for it in pool if it.type != "Shop" and not it.advancement and not it.priority
                         and not it.dungeonitem), None)
            if junk is None:
                raise ShopError("no junk left to balance a locked scrub")
            pool.remove(junk)
        world.push_item(loc, item)
        loc.locked = True
        locked.append(loc.name)
    return locked


def lock_vanilla_shops(world, ItemFactory):
    """Locks the shop slots this module keeps vanilla (both potion shops). Returns the locked location names.
    With shopsanity on, OoTR leaves every shop slot empty and builds its pool for them, a "Buy" item per regular
    slot and a junk item per special deal. Our vanilla slots get their vanilla "Buy" item, lose any special-deal
    price and get locked. Then the pool loses one "Buy" item for each regular slot fewer to fill (same names first,
    then ones logic doesn't use) and junk for the rest, so its count still matches the empty locations."""
    names = shop_map()["locations"]
    locked = []
    for loc in world.get_locations():
        if loc.type != "Shop" or loc.item is not None or names.get(loc.name, {}).get("mode") != "vanilla":
            continue
        world.shop_prices.pop(loc.name, None)
        loc.price = None  # the game keeps its own price here, so no special-deal wallet rule
        world.push_item(loc, ItemFactory(names[loc.name]["vanilla"], world))
        loc.locked = True
        locked.append(loc)
    if not locked:
        return []
    pool = world.itempool
    buy = [it for it in pool if it.type == "Shop"]
    regular = [loc for loc in world.get_locations() if loc.type == "Shop" and loc.item is None and loc.price is None]
    extra = len(buy) - len(regular)
    if extra < 0 or extra > len(locked):
        raise ShopError(f"shop pool: {len(buy)} 'Buy' items for {len(regular)} regular slots after locking "
                        f"{len(locked)} vanilla slots")
    want = [loc.item.name for loc in locked]
    buy.sort(key=lambda it: (it.name not in want, it.advancement, it.name))  # same names, then non-progression
    for it in buy[:extra]:
        pool.remove(it)
    junk = [it for it in pool if it.type != "Shop" and not it.advancement and not it.priority and not it.dungeonitem]
    if len(junk) < len(locked) - extra:
        raise ShopError("shop pool: not enough junk to balance the vanilla shop slots")
    for it in junk[:len(locked) - extra]:
        pool.remove(it)
    return [loc.name for loc in locked]


def _merchant_ops(plan, notes, name, e, item, price):
    """The carpet salesman's sale. His sold-flag branch (vanilla asks "buy more?") closes the rupee display and ends.
    The other branch sells the item at the price (the call's ActorName/Price/MinusRupeeValue and SimpleShop_Price)."""
    actor = _tiers(item, e)[0]
    scene = {"file": e["scene"], "flowchart": e["scene"]}
    c = e["calls"][0]
    plan["events"].append(dict(scene, add_graph=e["graph"], start="sold", nodes={
        "sold": {"actor": "UISystemActor", "action": "EventCloseRupeeDisplay", "params": {"IsWaitEnd": True},
                 "next": None}}, note=f"{name}: sold already ({e['sold_flag']}) -> no sale"))
    plan["events"].append(dict(scene, event=e["route"]["event"], case=e["route"]["case"], next=f"{e['graph']}_sold"))
    for param, value, old in (("ActorName", actor, c["actor"]), ("Price", price, c["price"]),
                              ("MinusRupeeValue", -price, c["minus"])):
        if value != old:
            plan["events"].append(dict(scene, event=c["event"], param=param, value=value))
    plan["events"].append(dict(scene, event=e["price_event"], param="Value", value=price))
    notes.append(f"{name}: sells {item} for {price}; his lines still talk about bombchus")
    if e.get("requires"):
        notes.append(f"{name}: needs OoTR rule {e['requires']} ({e['requires_why']})")


DI_ROOT, DI_BUY = "Rando_DI_SimpleShopRoot", "Rando_DI_SimpleShop_Buy"


def _hold_hand_over(item, edit):
    """For the carpet salesman, the hold-up node (progressive.hold_node, its display's hold-up and the get window) for
    an item Link can't hold up as it is (config/hold_up.json, so a spiritual stone, a medallion, the Master Sword).
    None for any other item.
    His vanilla hand-over would hold it up as it is, and that freezes (no Rotate_GetDemo, see in_game_check's
    no-pose read-back)."""
    if item in PROGRESSIVE or item == ICE or call_marker(item, edit):
        return None
    import progressive
    actor = sellable(item, "scrub")
    return progressive.hold_node(actor, None) if actor else None


def _dungeon_merchant_ops(plan, notes, name, e, item, price):
    """A dungeon item at the carpet salesman.
    Same as his ice trap (_ice_ops), his sale call runs a copy of SimpleShopRoot without the "room in the pouch?"
    check. That calls a copy of Sub_SimpleShop_Buy (the price taken as vanilla) where the item's credit entry
    replaces the NpcCommon hand-over (tools/rando/parity/_chests_scenes.py simpleshop_graphs,
    data/rando/chests_scenes.json "shop", with the freeze swapped for the credit). Any other item given by its own
    entry (call_marker) works the same way, and an item Link can't hold up as it is (_hold_hand_over) gets its own
    hold-up in place of the hand-over."""
    import copy
    from parity import _chests_scenes as cs
    marker = call_marker(item, e, request=True)
    if marker:
        import progressive
        hand = {"call": f"Dm_SY_GetInEvent:{marker}", **({"params": dict(progressive.CALL_PARAMS[marker])}
                                                          if marker in getattr(progressive, "CALL_PARAMS", {}) else {})}
    else:
        held = _hold_hand_over(item, e)
        if held is None:
            raise ShopError(f"{name}: {item} is neither given by an entry of its own nor held up by a display")
        hand = {"call": held["call"], "params": dict(held["params"])}
    for entry, nodes, start in cs.load()["graphs"]["shop"]:
        nodes = copy.deepcopy(nodes)
        if entry == cs.SHOP_BUY:
            entry, swapped = DI_BUY, hand
        elif entry == cs.SHOP_ROOT:
            entry, swapped = DI_ROOT, {"call": f":{DI_BUY}"}
        else:
            raise ShopError(f"data/rando/chests_scenes.json shop graph {entry}: unknown")
        if nodes.get("rando_replaced", {}).get("call") not in (cs.CALL, f":{cs.SHOP_BUY}"):
            raise ShopError(f"data/rando/chests_scenes.json {entry}: its hand-over isn't where it was")
        nodes["rando_replaced"].update(swapped)
        plan["events"].append({"file": cs.SHOP_FILE, "flowchart": cs.SHOP_FILE, "add_graph": entry, "nodes": nodes,
                               "start": start})
    scene = {"file": e["scene"], "flowchart": e["scene"]}
    c = e["calls"][0]
    plan["events"].append(dict(scene, add_graph=e["graph"], start="sold", nodes={
        "sold": {"actor": "UISystemActor", "action": "EventCloseRupeeDisplay", "params": {"IsWaitEnd": True},
                 "next": None}}))
    plan["events"].append(dict(scene, event=e["route"]["event"], case=e["route"]["case"], next=f"{e['graph']}_sold"))
    plan["events"].append(dict(scene, add_graph=e["graph"] + "_DI", start="sale", nodes={
        "sale": {"copy": c["event"], "call": f"{cs.SHOP_FILE}:{DI_ROOT}",
                 "params_over": {"Price": price, "MinusRupeeValue": -price}, "next": None}}))
    for ev in _call_preds(e, c["event"]):
        plan["events"].append(dict(scene, **ev, next=f"{e['graph']}_DI_sale"))
    plan["events"].append(dict(scene, event=e["price_event"], param="Value", value=price))
    notes.append(f"{name}: sells {item} for {price} ({'its own entry' if marker else 'its own hold-up'}, once: "
                 f"{e['sold_flag']})")
    if e.get("requires"):
        notes.append(f"{name}: needs OoTR rule {e['requires']} ({e['requires_why']})")


def install_fill_guard(allow_new_types=NEW_TYPES):
    """OoTR places its last junk with Fill.fast_fill, which ignores item rules, so a shelf could get rupees.
    This wraps it (once per process). Every shop/scrub/merchant slot this module drives first takes a junk item it
    can sell (junk for junk, so logic isn't touched), then OoTR fills the rest as before. It's for the generator's
    before_fill, repair_special_deals does the same thing after the fill instead."""
    import Fill
    if getattr(Fill.fast_fill, "shops_guard", False):
        return
    original = Fill.fast_fill

    def fast_fill(locations, itempool):
        names = shop_map()["locations"]
        for loc in [l for l in locations if names.get(l.name, {}).get("mode") == "full"]:
            k = next((k for k, it in enumerate(itempool) if loc.can_fill_fast(it)
                      and item_allowed(loc.name, it.name, allow_new_types, is_deal(loc))), None)
            if k is None:
                raise Fill.FillError(f"{loc.name}: no junk left that it can sell")
            loc.world.push_item(loc, itempool.pop(k))
            locations.remove(loc)
        return original(locations, itempool)
    fast_fill.shops_guard = True
    Fill.fast_fill = fast_fill


def repair_special_deals(world, allow_new_types=NEW_TYPES):
    """Call after OoTR's Main.place_items, before the spoiler and hints.
    OoTR places its last junk without item rules (Fill.fast_fill), so a shop or scrub slot can end up with junk it
    can't sell (rupees on a shelf, an ice trap). Each of those gets swapped with sellable junk from an ordinary
    location, junk for junk so logic isn't touched. Raises if an advancement item sits where it can't be sold, use
    item_allowed as an item rule for that.
    Returns [(slot, item now there, other location, item now there)]."""
    names = shop_map()["locations"]
    swaps = []
    pool = [loc for loc in world.get_filled_locations() if loc.name not in names and not loc.locked
            and not loc.item.advancement and not loc.item.priority and loc.type not in ("Event", "Drop")]
    for loc in list(world.get_filled_locations()):
        if loc.name not in names or loc.locked or item_allowed(loc.name, loc.item.name, allow_new_types, is_deal(loc)):
            continue
        if loc.item.advancement or loc.item.priority:
            raise ShopError(f"{loc.name}: holds {loc.item.name}, which it can't sell (add item_allowed as an item rule)")
        other = next((o for o in pool if item_allowed(loc.name, o.item.name, allow_new_types, is_deal(loc))
                      and o.item_rule(o, loc.item)), None)
        if other is None:
            raise ShopError(f"{loc.name}: no sellable junk to swap with {loc.item.name}")
        pool.remove(other)
        a, b, other_price = loc.item, other.item, other.price
        world.push_item(loc, b)       # takes the slot's price (OoTR may reroll a refill's special-deal price)
        world.push_item(other, a)     # push_item would carry the slot's price over, so put the location's own back
        other.price = a.price = other_price
        swaps.append((loc.name, b.name, other.name, a.name))
    return swaps


# CLI
def main(argv):
    if len(argv) >= 2 and argv[0] == "build":
        out = build(argv[1])
        modes = defaultdict(lambda: defaultdict(int))
        for v in out["locations"].values():
            modes[v["kind"]][v["mode"]] += 1
        for kind, m in modes.items():
            print(f"{kind}: " + ", ".join(f"{n} {k}" for k, n in sorted(m.items())))
        shop = [a for a in sorted(set(SHELF.values()))]
        print(f"shelf-sellable OoTR items: {len(SHELF)} names -> {len(shop)} Shop_* actors")
        print(f"wrote {OUT}")
        return 0
    if len(argv) == 3 and argv[0] == "plan":
        assign = json.load(open(argv[1], encoding="utf-8"))
        plan = plan_ops({k: tuple(v) for k, v in assign.items() if not k.startswith("_")})
        json.dump(plan, open(argv[2], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        for n in plan["_notes"]:
            print("  note:", n)
        print(f"wrote {argv[2]}: " + ", ".join(f"{len(v)} {k}" for k, v in plan.items() if k != "_notes"))
        return 0
    print(__doc__.split("\n\n")[0])
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ShopError as e:
        sys.exit(f"shop error: {e}")
