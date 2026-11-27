"""Parity plugin: item options from Ship of Harkinian (SoH) and the 3DS randomizer (OoT3DR) that OoT Randomizer 9.1.40
doesn't have. Every one is a remake setting (settings.remake), off by default, and with all of them off this plugin
changes nothing (no item, rule, random draw or plan section).

- remake_progressive_goron_sword (SoH/OoT3DR "Progressive Goron Sword"): the Giant's Knife and the Biggoron Sword become
  two "Progressive Goron Sword". The first one found is the knife, the second the Biggoron Sword (the tier is decided
  when it's given, tools/progressive.py, and a broken knife still counts as the knife). When OoTR leaves Medigoron
  vanilla, he only sells replacement knives once the player's knife has broken (his "no knife at all" talk goes to his
  "come back when it breaks" line), like OoT3DR and SoH do. Logic: Giants_Knife = 1 copy, Biggoron_Sword = 2.
- remake_progressive_swords (our own chain, needs remake_shuffle_master_sword): Kokiri Sword -> Master Sword -> Giant's
  Knife -> Biggoron Sword as four "Progressive Sword". Logic: Kokiri_Sword = 1, Master_Sword = 2, Giants_Knife = 3,
  Biggoron_Sword = 4 (OoTR's rules are rewritten through rule aliases). It includes everything the Goron sword option
  does, so the two can't both be on.
- remake_gk_durability (OoT3DR "GK Durability"): vanilla (8 hits), random_risky (1-128, low values common, mean about
  15), random_safe (10-50) or a number 1-999. One value per seed, since the remake has no per-knife random. It sets the
  knife's MaxLife (RSDB/GameActorInfo, its actor pack) and the save's PlayerStatus.WeaponSwordGiantLife default.
- remake_remove_double_defense (OoT3DR "Remove Double Defense"): OoTR's Double Defense becomes junk.
- remake_shuffle_deku_stick_bag / remake_shuffle_deku_nut_bag (SoH): the game gives the small stick and nut bags by
  itself on the first stick or nut (PouchActorInfo IsAbleToGetBagIfGet). We turn that off, so with no bag the capacity
  is 0 (like bombs with no bomb bag), and the bag becomes the first of three "Deku Stick Bag" / "Deku Nut Bag" (10/20/30
  sticks, 20/30/40 nuts). Logic: Sticks / Nuts also need one.
- remake_shuffle_child_wallet (SoH): a new file starts with no wallet (the game-start sequence pushes zero Kokiri
  Wallets), so no rupee can be held. OoTR's Progressive Wallet gets a third copy and its first tier is the Kokiri Wallet
  (200), then 500 and 1000. Logic: every purchase and every fee the remake charges needs a wallet.
(OoT3DR's other trap types, remake_trap_weights, live with the ice trap in parity/chests.py and
parity/_chests_scenes.py.)
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
import progressive  # noqa: E402

REMAKE_SETTINGS = {
    "remake_progressive_goron_sword": (False, True),
    "remake_progressive_swords": (False, True),
    "remake_gk_durability": None,                  # checked in check_settings
    "remake_gk_durability_hits": None,             # 1-999, with remake_gk_durability "fixed"
    "remake_remove_double_defense": (False, True),
    "remake_shuffle_deku_stick_bag": (False, True),
    "remake_shuffle_deku_nut_bag": (False, True),
    "remake_shuffle_child_wallet": (False, True),
    "remake_ammo_without_container": ("blue_rupee", "nothing"),  # parity/_ammo.py (read by generate for every give)
}
REMAKE_DEFAULTS = {"remake_progressive_goron_sword": False, "remake_progressive_swords": False,
                   "remake_gk_durability": "vanilla", "remake_gk_durability_hits": 8,
                   "remake_remove_double_defense": False,
                   "remake_shuffle_deku_stick_bag": False, "remake_shuffle_deku_nut_bag": False,
                   "remake_shuffle_child_wallet": False, "remake_ammo_without_container": "blue_rupee"}
GK_MODES = ("vanilla", "random_risky", "random_safe", "fixed")  # "fixed": remake_gk_durability_hits (a number
# given as remake_gk_durability itself, the older form, still means that many hits)

PGS, PS = "Progressive Goron Sword", "Progressive Sword"
STICK_BAG, NUT_BAG = "Deku Stick Bag", "Deku Nut Bag"
WALLET, WALLET_KOKIRI = "Progressive Wallet", "Progressive Kokiri Wallet"
MEDIGORON = "GC Medigoron"

# OoTR item -> the progressive item replacing it, per option
SWORD_ITEMS = {PGS: ("Giants Knife", "Biggoron Sword"),
               PS: ("Kokiri Sword", "Master Sword", "Giants Knife", "Biggoron Sword")}
# OoTR rule names -> tier counts (RuleParser aliases: a rule naming the item counts the progressive copies)
SWORD_RULES = {PGS: {"Giants_Knife": 1, "Biggoron_Sword": 2},
               PS: {"Kokiri_Sword": 1, "Master_Sword": 2, "Giants_Knife": 3, "Biggoron_Sword": 4}}
BAGS = {STICK_BAG: ("remake_shuffle_deku_stick_bag", "Deku Stick Capacity", "Sticks"),
        NUT_BAG: ("remake_shuffle_deku_nut_bag", "Deku Nut Capacity", "Nuts")}
HINTS = {PGS: (["a brittle blade", "a mighty blade"], "a Goron Sword"),
         PS: (["a sharp blade", "a blade"], "a Sword"),
         STICK_BAG: (["a pouch for sticks", "a Deku pouch"], "a Deku Stick Bag"),
         NUT_BAG: (["a pouch for nuts", "a Deku pouch"], "a Deku Nut Bag")}

# The pouch's "get the small bag with the first stick/nut" switch, in the RSDB/PouchActorInfo rows and the actor packs'
# PouchContentParam files that carry it. Data from the files.
BAG_SWITCH = {
    STICK_BAG: {"rows": ["Item_DekuStick", "Obj_DekuStick", "Pouch_DekuStick", "Shop_DekuStick", "Weapon_DekuStick"],
                "file": "Component/PouchContentParam/Obj_DekuStick.game__component__PouchContentParam.bgyml",
                "packs": ["Item_DekuStick", "Obj_DekuStick", "Pouch_DekuStick", "Shop_DekuStick",
                          "Weapon_DekuStick"]},
    NUT_BAG: {"rows": ["Item_DekuNut", "Shootable_ScrubBusinessSees"],
              "file": "Component/PouchContentParam/Item_DekuNut.game__component__PouchContentParam.bgyml",
              "packs": ["Item_DekuNut", "Obj_DekuNut", "Pouch_DekuNut", "Shootable_ScrubBusinessSees"]},
}
POUCH_INFO = "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"
GAME_ACTOR_INFO = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"
GK_LIFE = {"pack": "Pack/Actor/Weapon_Sword_Giant.pack.zs",
           "file": "Life/LifeParameters/Weapon_Sword_Biggoron.game__life__LifeParameters.bgyml"}
GAME_START = "Sequence/SetPouchAndStatusForGameStart.module.ainb"
WALLET_PUSH_NUM = 0x11F8  # node 7 SeqOneShotPushToPouch Item_Wallet_Small, input Num (int32, vanilla 1)
GET_FILE = "Dm_SY_GetInEvent"
WALLET_ENTRY = "Rando_GetWalletSmall"
POUCH_MSG = "ActorMsg/PouchContent.msbt"

# Fees: OoTR locations / events / exits the remake charges rupees for (every scene step
# that checks or takes rupees). With no wallet nothing can be paid.
FEE_LOCATIONS = ("GC Medigoron", "Kak Granny Buy Blue Potion", "Wasteland Bombchu Salesman",
                 "ZR Magic Bean Salesman", "Market Shooting Gallery Reward", "Kak Shooting Gallery Reward",
                 "Market Bombchu Bowling First Prize", "Market Bombchu Bowling Second Prize",
                 "Market Bombchu Bowling Bombchus", "Market Bombchu Bowling Bomb", "LH Child Fishing",
                 "LH Adult Fishing", "LH Loach Fishing", "ZD Diving Minigame", "Graveyard Dampe Gravedigging Tour",
                 "GF HBA 1000 Points", "GF HBA 1500 Points", "LLR Talons Chickens")
FEE_EVENTS = ("Epona", "Links Cow")  # OoTR event locations are named "<event> from <region>"
FEE_PREFIXES = ("Market Treasure Chest Game",)
FEE_MASKS = ("Market Mask Shop Item 5", "Market Mask Shop Item 7", "Market Mask Shop Item 8")
FEE_MASK_EVENTS = ("Mask of Truth Access",)
FEE_EXIT_TARGET = "Gerudo Training Ground Lobby"  # the 30-rupee entry fee (Npc_Gerudo_004)

_state = {}  # id(world) -> {"patchable", "pool", "to_junk", "pool_notes"}
_orig_aliases = {}  # rule name -> OoTR's own alias (or None), kept so each attempt rewrites from the original
_hint_texts = {}  # new item -> (vague, clear) hint texts for every language


def _remake(settings, key):
    return (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS[key])


def _on(settings, key):
    return bool(_remake(settings, key))


def _sword_item(settings):
    """The progressive sword item this seed uses (or None)."""
    if _on(settings, "remake_progressive_swords"):
        return PS
    if _on(settings, "remake_progressive_goron_sword"):
        return PGS
    return None


def _bags(settings):
    return [b for b, (key, _, _) in BAGS.items() if _on(settings, key)]


# Settings
def check_settings(settings):
    out = []
    remake = getattr(settings, "remake", None) or {}
    for k, ok in REMAKE_SETTINGS.items():
        if ok is not None and k in remake and remake[k] not in ok:
            out.append(f"{k} = {remake[k]!r}: extras_items can make {', '.join(map(repr, ok))}")
    gk = remake.get("remake_gk_durability", "vanilla")
    if not (gk in GK_MODES or (isinstance(gk, int) and not isinstance(gk, bool) and 1 <= gk <= 999)):
        out.append(f"remake_gk_durability = {gk!r}: one of {', '.join(map(repr, GK_MODES))} or a number 1-999")
    hits = remake.get("remake_gk_durability_hits", 8)
    if isinstance(hits, bool) or not isinstance(hits, int) or not 1 <= hits <= 999:
        out.append(f"remake_gk_durability_hits = {hits!r}: a number of hits from 1 to 999")
    if _on(settings, "remake_progressive_swords"):
        if _on(settings, "remake_progressive_goron_sword"):
            out.append("remake_progressive_swords already includes the Giant's Knife and Biggoron Sword: turn off "
                       "remake_progressive_goron_sword")
        if not remake.get("remake_shuffle_master_sword"):
            out.append("remake_progressive_swords needs remake_shuffle_master_sword (the pedestal must hold a "
                       "check for the Master Sword tier to be found elsewhere)")
    starting = set(getattr(settings, "starting_items", None) or {})
    clash = {PS: {"Kokiri Sword", "Master Sword", "Giants Knife", "Biggoron Sword"},
             PGS: {"Giants Knife", "Biggoron Sword"}}.get(_sword_item(settings), set()) & starting
    if clash:
        out.append(f"starting with {', '.join(sorted(clash))} while the swords are progressive: not supported")
    for bag in _bags(settings):
        key, cap, _ = BAGS[bag]
        if cap in starting:
            out.append(f"{key} with {cap} as a starting item: not supported")
        if getattr(settings, "start_with_consumables", False):
            out.append(f"{key} with start_with_consumables: the starting sticks/nuts would have no bag to go in")
    if _on(settings, "remake_shuffle_child_wallet"):
        if WALLET in starting:
            out.append("remake_shuffle_child_wallet with a starting Progressive Wallet: not supported")
        if getattr(settings, "start_with_rupees", False):
            out.append("remake_shuffle_child_wallet with start_with_rupees: a new file has no wallet to hold them")
    return out


def untested(settings):
    out = []
    if _sword_item(settings):
        out.append(f"extras_items: {_sword_item(settings)} (sword tiers given by scene, owned-checks on Weapon_* "
                   f"actors, broken knife counts as the knife; Medigoron sells only replacement knives)")
    gk = _remake(settings, "remake_gk_durability")
    if gk != "vanilla":
        out.append(f"extras_items: remake_gk_durability {gk!r} (knife MaxLife in GameActorInfo and its pack)")
    if _on(settings, "remake_remove_double_defense"):
        out.append("extras_items: remake_remove_double_defense (item pool only)")
    for bag in _bags(settings):
        out.append(f"extras_items: {BAGS[bag][0]} (IsAbleToGetBagIfGet off; small bag held up from a check)")
    if _on(settings, "remake_shuffle_child_wallet"):
        out.append("extras_items: remake_shuffle_child_wallet (no wallet pushed at new game; Kokiri Wallet shown as "
                   "Pouch_Wallet_Small and added as Item_Wallet_Small)")
    return out


def any_on(settings):
    return bool(_sword_item(settings) or _remake(settings, "remake_gk_durability") != "vanilla"
                or _on(settings, "remake_remove_double_defense") or _bags(settings)
                or _on(settings, "remake_shuffle_child_wallet"))


# OoTR tables
def _register_item(name):
    """Registers a new OoTR progression item, the same way the story plugin registers the Master Sword. That's ItemList,
    ItemInfo and hint texts in every language. ItemInfo gets a solver id so rules can count it, and 'progressive' = its
    tier count, which OoTR's playthrough reads as the most copies logic can need."""
    import HintList
    import Item
    import ItemList
    import Language
    if name not in ItemList.item_table:
        ItemList.item_table[name] = ("Item", True, None, {"progressive": len(progressive.PROGRESSIVE[name]["tiers"])})
    if name not in Item.ItemInfo.items:
        Item.ItemInfo.items[name] = Item.ItemInfo(name)
    vague, clear = HINTS[name]
    HintList.hintTable.setdefault(name, (vague, clear, "item"))
    _hint_texts[name] = (vague, clear)
    if not getattr(Language.Language.__init__, "remake_extras_items", False):
        original = Language.Language.__init__

        def init(self, lang, _original=original):
            _original(self, lang)
            for n, (v, c) in _hint_texts.items():
                self.hintTable.setdefault(n, {"vague_hint": v, "clear_hint": c, "gender": "no_gender"})
        init.remake_extras_items = True
        Language.Language.__init__ = init


def _set_alias(name, repl):
    """Makes OoTR's rule parser read `name` as `repl` (a helper override, or an item name read as a count)."""
    import RuleParser
    if not RuleParser.rule_aliases:
        RuleParser.load_aliases()
    if name not in _orig_aliases:
        _orig_aliases[name] = RuleParser.rule_aliases.get(name)
    RuleParser.rule_aliases[name] = ([], repl)
    RuleParser.nonaliases.discard(name)


def before_build(settings):
    if not any_on(settings):
        return
    sword = _sword_item(settings)
    if sword:
        _register_item(sword)
        esc = sword.replace(" ", "_")
        for rule_name, count in SWORD_RULES[sword].items():
            _set_alias(rule_name, f"({esc}, {count})")
    for bag in _bags(settings):
        _, cap, helper = BAGS[bag]
        _register_item(bag)
        import Item
        # A capacity item OoTR left vanilla where the patcher can't change it gives that bag in game, so count it.
        Item.ItemInfo.items[cap].advancement = True
        Item.ItemInfo.items[cap].priority = False
        import RuleParser
        if not RuleParser.rule_aliases:
            RuleParser.load_aliases()
        orig = _orig_aliases.get(helper) or RuleParser.rule_aliases[helper]
        _orig_aliases.setdefault(helper, orig)
        _set_alias(helper, f"({orig[1]}) and ({bag.replace(' ', '_')} or {cap.replace(' ', '_')})")
    if any_on(settings):
        _install_pool_hook()


# Item pool (just before OoTR's fill)
def _install_pool_hook():
    """OoTR's pool is only final after every plugin's before_fill (the story plugin adds the shuffled Master Sword
    there), so the swaps run at the start of Main.place_items, for the worlds this plugin set up."""
    import Main
    if getattr(Main.place_items, "remake_extras_items", False):
        return
    original = Main.place_items

    def place_items(worlds, _original=original):
        for w in worlds:
            st = _state.get(id(w))
            if st and st.get("pool"):
                _swap_pool(w, st)
        return _original(worlds)
    place_items.remake_extras_items = True
    Main.place_items = place_items


def _junk_index(pool):
    """The last plain junk item of the pool (rupees, ammo...): never an ice trap, a key or anything logic uses."""
    for i in range(len(pool) - 1, -1, -1):
        it = pool[i]
        if not (it.advancement or it.priority or it.dungeonitem or it.name == "Ice Trap" or it.type != "Item"):
            return i
    raise ValueError("extras_items: the item pool has no junk left to turn into an extra item")


def _swap_pool(world, st):
    from Item import ItemFactory
    pool = world.itempool
    done = []
    for new, olds, total in st["pool"]:
        for i, it in enumerate(pool):
            if it.name in olds:
                pool[i] = ItemFactory(new, world)
        # Locked spots OoTR (or the generator) filled with an item that's being replaced, where the plan writes it.
        for loc in world.get_locations():
            if loc.item is not None and loc.item.name in olds and loc.name in st["patchable"]:
                fresh = ItemFactory(new, world)
                loc.item = fresh
                fresh.location = loc
        n = sum(1 for it in pool if it.name == new) + sum(
            1 for loc in world.get_locations() if loc.item is not None and loc.item.name == new)
        while total is not None and n < total:
            pool[_junk_index(pool)] = ItemFactory(new, world)
            n += 1
        done.append(f"{new}: {n} in the world (from {', '.join(olds) or 'junk'})")
    for name in st.get("to_junk", ()):
        import ItemPool
        for i, it in enumerate(pool):
            if it.name == name:
                pool[i] = ItemFactory(ItemPool.get_junk_item()[0], world)
                done.append(f"{name} -> junk {pool[i].name}")
    st["pool_notes"] = done


def keep_locations(world, settings):
    return set()


def before_fill(world, settings):
    if not any_on(settings):
        return
    import generate
    st = _state.setdefault(id(world), {})
    chest_map = json.load(open(os.path.join(HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"]
    st["patchable"] = set(generate.scene_locations()) | {n for n, v in chest_map.items()
                                                          if v["mode"] in ("full", "group")}
    st["pool"], st["to_junk"] = [], []
    sword = _sword_item(settings)
    if sword:
        st["pool"].append((sword, SWORD_ITEMS[sword], len(SWORD_ITEMS[sword])))
    for bag in _bags(settings):
        st["pool"].append((bag, (BAGS[bag][1],), 3))
    # Special deals can sell these and show the tier they give (shops.py _deal_ops and shelf_look). Regular shelves only
    # take shop items under OoTR's rules. That restriction is in shops.
    if _on(settings, "remake_remove_double_defense"):
        st["to_junk"].append("Double Defense")
    if _on(settings, "remake_shuffle_child_wallet"):
        have = sum(1 for it in world.itempool if it.name == WALLET) + sum(
            1 for loc in world.get_locations() if loc.item is not None and loc.item.name == WALLET)
        st["pool"].append((WALLET, (), have + 1))
        _wallet_rules(world, settings)
        _wallet_placement(world)


def _wallet_rules(world, settings):
    """With no wallet nothing can be bought or paid: every shop and scrub, the merchants, the minigames that charge
    a fee, the Great Fairies' offerings, the Gerudo Training Ground's entry fee and Ingo's riding fee (Epona) need
    one."""
    rule = world.parser.parse_rule("Progressive_Wallet")
    quest = not getattr(settings, "complete_mask_quest", False)
    masks, mask_events = (FEE_MASKS, FEE_MASK_EVENTS) if quest else ((), ())
    for loc in world.get_locations():
        event = loc.name.split(" from ")[0] if loc.type == "Event" else None
        if (loc.type in ("Shop", "Scrub", "GrottoScrub") or loc.name in FEE_LOCATIONS or loc.name in masks
                or loc.name.startswith(FEE_PREFIXES) or event in FEE_EVENTS or event in mask_events):
            loc.add_rule(rule)
    # The Great Fairies take an offering too, and the 300 and 500 ones need the wallet after the Kokiri one (her price
    # when extras_prices set one, else the vanilla offering).
    from parity import extras_prices
    for name, (*_e, vanilla) in sorted(extras_prices.FAIRIES.items()):
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        n = extras_prices.fairy_wallets(vanilla if loc.price is None else loc.price, child_wallet=True)
        if n:
            loc.add_rule(world.parser.parse_rule(f"(Progressive_Wallet, {n})"))
    # The exit through the Training Ground's door. Its name keeps the vanilla target when entrances are shuffled, and
    # the guard who takes the fee stands at that door.
    for region in world.regions:
        for ex in region.exits:
            if ex.name == f"{region.name} -> {FEE_EXIT_TARGET}" and region.name != FEE_EXIT_TARGET:
                ex.add_rule(rule)


def _wallet_placement(world):
    """The Kokiri tier is shown with Pouch_Wallet_Small and added as Item_Wallet_Small by its own scene entry
    (progressive.GIVE), which every tier entry (progressive.host_graph) calls. That covers the chests' tier scenes, the
    songs/trade plugin's give steps (NPCs, the get scene of drop spots and fairies), the core scene locations whose
    steps aren't all routine calls (songs_trade.progressive_spec: the steps call the tier entry), the scrub sales and
    the carpet salesman (shops.call_marker), and the hideout jails. Only the shop shelves (Shop_* actors), the Master
    Sword pedestal (its display step shows the tier before the add) and, without the songs/trade plugin, the core scene
    locations that can't take it still refuse it."""
    import generate
    calls = "parity.songs_trade" in sys.modules
    modes = json.load(open(os.path.join(HERE, "data", "rando", "scene_give_modes.json"), encoding="utf-8"))["locations"]
    allowed = {name for name, rid in generate.scene_locations().items()
               if calls or ((modes.get(rid) or {}).get("steps") and all(m == "host" for m in modes[rid]["steps"].values()))}
    allowed.discard("ToT Master Sword")  # its pedestal display step shows the tier before the add
    scene = set(generate.scene_locations())
    for loc in world.get_locations():
        if loc.type in ("Event", "Drop", "Hint", "HintStone") or loc.name in allowed:
            continue
        if calls and loc.name not in scene and loc.type != "Shop":
            continue
        if not calls and loc.type == "Chest":
            continue
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: item.name != WALLET and prev(location, item))


_seed = {"child_wallet": False}  # the seed being built (generate.py runs one seed per process)


def item_for(item, location, world):
    """In a child-wallet seed, Progressive Wallet becomes the plan's three-tier wallet, Kokiri tier first. At a
    core scene location whose steps can't hand it over by themselves, it's a call to its tier entry
    (songs_trade.progressive_spec)."""
    if item != WALLET or not _seed["child_wallet"]:
        return None
    st = sys.modules.get("parity.songs_trade")
    spec = st.progressive_spec(item, location, WALLET_KOKIRI) if st is not None else None
    return spec or WALLET_KOKIRI


def target_name(name):
    """Which progressive item the plan uses for OoTR's `name`. It's for plugins that build their own give steps, like
    songs_trade (the heart spots go through it too) and the chests plugin for its own chests."""
    return WALLET_KOKIRI if name == WALLET and _seed["child_wallet"] else name


def after_fill(world, settings):
    _seed["child_wallet"] = _on(settings, "remake_shuffle_child_wallet")


# Patch plan
def gk_durability(settings):
    """How many hits the knife takes in this seed (8 is vanilla). It's drawn with a separate generator so OoTR's
    random draws don't change."""
    v = _remake(settings, "remake_gk_durability")
    if v == "vanilla":
        return 8
    if v == "fixed":
        return _remake(settings, "remake_gk_durability_hits")
    if isinstance(v, int):
        return v
    rng = random.Random(f"remake_gk_durability:{getattr(settings, 'seed', '')}")
    if v == "random_safe":
        return rng.randint(10, 50)
    return min(128, 1 + int(rng.expovariate(1 / 14.0)))  # random_risky: 1-128, low values common, mean ~15


def _gk_plan(settings):
    life = gk_durability(settings)
    if life == 8:
        return {}, []
    return ({"byml": [{"file": GAME_ACTOR_INFO, "set": {"[__RowId=Weapon_Sword_Giant].MaxLife": life}}],
             "packs": [dict(GK_LIFE, set={"MaxLife": life})],
             "gamedata": {"defaults": {"PlayerStatus.WeaponSwordGiantLife": life}}},
            [f"Giant's Knife durability: {life} hits (vanilla 8)"])


def _text(label, text):
    return {"lang": "*", "file": POUCH_MSG, "label": label, "text": text, "add": True}


BAG_TEXT = {STICK_BAG: ("Item_StickBag_Small", "You got a Deku-stick bag!",
                        "Now you can carry Deku sticks!\nThis bag fits up to 10 of them!"),
            NUT_BAG: ("Item_NutBag_Small", "You got a Deku-nut bag!",
                      "Now you can carry Deku nuts!\nThis bag fits up to 20 of them!")}


def _bag_plan(settings):
    plan, notes = {"byml": [], "packs": [], "text": []}, []
    for bag in _bags(settings):
        sw = BAG_SWITCH[bag]
        plan["byml"].append({"file": POUCH_INFO, "set": {f"[__RowId={r}].IsAbleToGetBagIfGet": False
                                                         for r in sw["rows"]}})
        for p in sw["packs"]:
            plan["packs"].append({"pack": f"Pack/Actor/{p}.pack.zs", "file": sw["file"],
                                  "set": {"IsAbleToGetBagIfGet": False}})
        actor, msg, cap = BAG_TEXT[bag]
        plan["text"] += [_text(f"{actor}_GetMessage", msg), _text(f"{actor}_GetCaption", cap)]
        notes.append(f"{bag}: the first stick/nut no longer brings the small bag; the bag is the first of three "
                     f"{bag} copies")
    return plan, notes


def wallet_graph():
    """(entry, nodes, start) for Dm_SY_GetInEvent, the Kokiri Wallet's get. It works like
    GetInEvent_DemoNotLookAtTurnOff and GetInEvent_NotLookatObjectTurnOff: show the item, locator, animation, item
    position with fanfare and glow, the get window and pouch add, then put the item away.
    Link holds up a display we made, Rando_Show_WalletSmall (config/hold_up.json "displays"), with the model of
    Pouch_Wallet_Small, the only wallet actor that has a model. The locator, pose and position steps name
    Pouch_Wallet_Small because the pouch tables know it, and the item added is Item_Wallet_Small.
    The hold-up can't create Pouch_Wallet_Small itself. It's a menu actor with no model bind or item-get AI, which is
    the hold-up crash class from test_guardroom that no_pose_check reads back."""
    show = "Pouch_Wallet_Small"
    n = {
        "show": {"actor": "Player_Event", "action": "EventCreateShowItemFromActorFileName",
                 "params": {"IsWaitEnd": True, "Actor": "Rando_Show_WalletSmall"}, "next": "locator"},
        "locator": {"call": ":GetInEvent_SetLocator", "params": {"ActorName": show}, "next": "anim"},
        "anim": {"call": ":GetInEvent_Animation", "params": {"ActorName": show}, "next": "pos"},
        "pos": {"call": ":Item_Position", "params": {"ActorName": show}, "next": "add"},
        "add": {"call": "GetPouchContent:GetPouchContentByActorName", "params": {"ActorName": "Item_Wallet_Small"},
                "next": "away"},
        "away": {"fork": ["hide", "wait"], "join": "done"},
        "hide": {"actor": "Player_Event", "action": "EventDeleteShowItem",
                 "params": {"IsWaitEnd": True, "IsFadeOut": False, "IsScaleOut": False,
                            "ChangeVisibleOffWithRequestDelete": False}, "next": None},
        "wait": {"actor": "EventSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 1},
                 "next": "glowoff"},
        "glowoff": {"actor": "EventEffectEmitter", "action": "EventEffectStopGetItem", "next": None},
        "done": {"join": True, "next": None},
    }
    return WALLET_ENTRY, n, "show"


WALLET_TEXT = [("Item_Wallet_Small_GetMessage", "You got the Kokiri Wallet!"),
               ("Item_Wallet_Small_GetCaption", "Now you can carry rupees!\nIt holds up to 200 of them."),
               ("Pouch_Wallet_Small_Name", "Kokiri Wallet"),
               ("Pouch_Wallet_Small_GetMessage", "You got the Kokiri Wallet!"),
               ("Pouch_Wallet_Small_GetCaption", "Now you can carry rupees!\nIt holds up to 200 of them.")]


def _wallet_plan(settings):
    if not _on(settings, "remake_shuffle_child_wallet"):
        return {}, []
    entry, nodes, start = wallet_graph()
    return ({"binary": [{"file": GAME_START, "offset": WALLET_PUSH_NUM, "i32": 0, "expect": 1}],
             "events": [{"file": GET_FILE, "flowchart": GET_FILE, "add_graph": entry, "nodes": nodes,
                         "start": start}],
             "text": [_text(label, t) for label, t in WALLET_TEXT]},
            ["new file: no Kokiri Wallet (SetPouchAndStatusForGameStart pushes 0); rupees can't be held until a "
             "wallet is found", f"{WALLET}: plan name {WALLET_KOKIRI} (Kokiri 200 -> Adult 500 -> Giant 1000)"])


def _medigoron_plan(world):
    """Medigoron with his vanilla knife. The "no knife at all" branch (Event7 case no) goes to his "if one of my
    knives breaks, come back" line (Event5) instead, so he only replaces a broken knife."""
    try:
        loc = world.get_location(MEDIGORON)
    except KeyError:
        return {}, []
    if loc.item is None or loc.item.name != "Giants Knife":
        return {}, []
    f = "Npc_Goron_Medigoron_Adult"
    return ({"events": [{"file": f, "flowchart": f, "event": "Event7", "case": 1, "next": "Event5"}]},
            [f"{MEDIGORON}: sells only replacement knives (a broken knife must be held)"])


def world_plan(settings, world):
    if not any_on(settings):
        return {}
    plan, notes = {}, []
    import generate
    parts = [_gk_plan(settings), _bag_plan(settings), _wallet_plan(settings)]
    if _sword_item(settings):
        parts.append(_medigoron_plan(world))
    for part, n in parts:
        generate.merge_plan(plan, {k: v for k, v in part.items() if v})
        notes += n
    st = _state.get(id(world)) or {}
    notes += st.get("pool_notes", [])
    if notes:
        plan["_notes_extras_items"] = notes
    return plan
