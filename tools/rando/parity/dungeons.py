"""Dungeons and keys: OoTR's dungeon-item settings for the remake.

How the remake stores dungeon items (GameData/GameDataList): one block per dungeon area,
DungeonInfo.<area>.{SmallKeyNum (Int), IsGetBossKey, IsGetMap, IsGetCompass (Bool)}, saved with the file. The
generic items Item_Dungeon_SmallKey / BossKey / Map / Compass carry no dungeon. A chest holding one runs
GameSystemActor.EventGetDungeon* (no parameters), which credits the dungeon the player is standing in. So:

- Own dungeon (OoTR 'vanilla', 'dungeon', or any mode when the item lands in its own dungeon): the plain item, like
  vanilla. Small keys go in any chest, boss keys, maps and compasses in big and boss-key chests (plain_ok).
- Anywhere else, and key rings everywhere: the chest holds a stand-in ("carrier", data/rando/dungeons_world.json) and
  runs one shared scene per chest type (a reused scene ID each, for small and big chests, not boss-key or invisible
  chests). The scene plays the chest's normal opening (the big chest's whole cinematic), then copies the stand-in name
  into a temporary save-data string and compares it with each carrier the seed uses
  (GameDataActor.EventQueryIsGameDataString64, the same way the scrub flows compare item names). The matching branch
  calls a new entry in Dm_SY_GetInEvent (Rando_DI_Key / Rando_DI_Flag, given the model and the save-data name as
  arguments, Rando_DI_KeyRing_<area>).
  That entry holds the item up like the game's in-cutscene get routine and shows its get window naming its dungeon in
  OoTR's words, in every language (_dungeons_text.py: GetPouchContent:Rando_DI_Text / Rando_DI_KeyText, with the message
  as an argument). The game's window for the generic items it hands over in their own dungeon says the same
  (Rando_DI_PlainGet). Then it writes the right dungeon's save data (GameDataActor.EventTriggerAddOrSubGameDataInt
  DungeonInfo.<area>.SmallKeyNum, or EventTriggerSetGameDataBool for the boss key, map, compass) instead of adding the
  generic item.
  A small key writes what the game's own key add writes (_dungeons_keys.py): IsGetSmallKeyOnce (it shows the dungeon's
  HUD key counter and map-screen key), SmallKeyTotalNum and SmallKeyNum. Then, when the player is in that dungeon, it
  runs the game's key-counter request (GetPouchContent:Rando_DI_KeyShow, with the dungeon's map as its BancName
  argument). A boss key has its own shared entry (Rando_DI_BossKey). It sets IsGetBossKey and then runs
  GetPouchContent:Rando_DI_BossKeyShow, the game's boss-key display when the player is in that dungeon, like
  Dm_SY_Treasurebox Event82/Event94 do after the game's boss-key add.
- At a scene location (NPC, song, cutscene, config/rando_locations.json) the reward is {"item": model, "call":
  "Dm_SY_GetInEvent:Rando_DI_Call_<item>"}. make_patch (scene_call_ops) replaces the location's give steps with that
  call, a one-step entry that calls the shared entry with the item's arguments.
- Anywhere else a scene step gives the item (OoTR places dungeon items anywhere under keysanity and the *_anywhere
  values): other plugins' locations listed in CALL_LOCATIONS call the same credit entry. That's the drops plugin's heart
  spots, scene drops, flagless drops and scene gifts (the shared get scene, or in the air or water a copy of the credit
  steps, resident_give), the songs/trade plugin's NPCs, merchants, mask shop and lake pickups, the fairies, the extras'
  NPC checks, the Master Sword pedestal, the Business Scrubs (the one-time sale hands the entry's name over, and
  make_patch's scrub intercept pays and calls it), the carpet salesman (a SimpleShop copy) and the Treasure Chest Game's
  salesman.
  The chests plugin's own chests and every chest type that opens as a small or big chest (the Lens chest, the boss-key
  chest, an ice-trap chest given a real item) run the dungeon-item scene. allowed() only keeps OoTR's own restrictions,
  plus the spots where the patch can't give any scene item (see allowed's docstring). The read-back is
  _dungeons_routes.py.
- 'remove' (keys, boss keys), 'startwith' (maps, compasses): new-file save-data defaults. The counter is set to the
  dungeon's keys or locked doors, whichever is more, and the flags get set.

Also, always and whatever the settings: OoTR locations whose vanilla item differs from the remake's (vanilla_items) get
corrected in OoTR's location table, so its pool and 'vanilla' placement match the game. Every dungeon chest that
data/rando/chest_map.json keeps vanilla (KEY_COUNT_DIFFERS, low-confidence or wrong 'absent' reconcile pairs) and that
we paired with certainty, plus the remake-only dungeon chests (new OoTR locations), is taken into play (kept_chests),
with the remake's rules in
data/rando/logic/dungeons.json. Ice traps stay out of these chests because the ice-trap scene belongs to the chests
plugin's chests. A chest chest_map already plays can't be listed (checked on import).

Thieves' Hideout keys: the cells are plain chain locks spending DungeonInfo.GerudoFortress.SmallKeyNum, so a hideout key
found elsewhere is credited like a dungeon key. With keys shuffled, each guard's defeat gives its spot's seed item
(hideout_plan: the shared key drop is skipped, the key placements hidden, and there's a give step after each defeat
entry).
Fire Temple: with small keys vanilla or dungeon, the boss-key loop door starts unlocked on a new file
(IsChainLockDoorOpen.<door>), since OoTR's ROM patch removes that lock and its logic counts a free key.

Silver rupees (remake setting remake_silver_rupee_items, _dungeons_silver.py):
with shuffle_silver_rupees 'vanilla', each of OoTR's 80 silver-rupee spots still counts for its room and also gives a
seed item held at a new location "<puzzle> Silver Rupee Spot <n>" (the token's AI requests a get scene).
OoTR's other values ('remove', 'dungeon', 'regional', 'overworld', 'any_dungeon', 'anywhere') and silver-rupee pouches
are in _dungeons_silver_shuffle.py. Each puzzle's count is a new saved Int, and its counter (the barrier) leaves on a
Presence once the count reaches 5. "Silver Rupee (P)" / "Silver Rupee Pouch (P)" are dungeon items of this plugin
(carriers, chest scenes, call entries), and their credit adds to the count. OoTR's 80 silver-rupee locations are the
tokens, given by the same token scene. A silver rupee is held up as its own display (silver_shuffle.DISPLAY).

Not built: shuffled Bottom of the Well
and Shadow Temple freestanding keys (AlwaysRespawn pickups with no per-placement save flag).
"""
import json
import os
import re
import sys

from . import _dungeons_silver as silver
from . import _dungeons_silver_shuffle as silver_shuffle
from . import _dungeons_ganon as ganon
from . import _gaps_triforce_look as triforce_look
from . import _dungeons_keys as keys
from . import _dungeons_text as dtext

REMAKE_KEYS = (silver.SETTING,)  # remake settings this plugin reads (generate.unknown_remake_settings)

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WORLD = json.load(open(os.path.join(HERE, "data", "rando", "dungeons_world.json"), encoding="utf-8"))
DUNGEONS = WORLD["dungeons"]
CHEST_MAP = json.load(open(os.path.join(HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"]
REWARDS = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))}
CHEST_RULES = json.load(open(os.path.join(HERE, "config", "chest_rules.json"), encoding="utf-8"))
PROGRESSIVE = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]

KEYS_MODES = ("remove", "vanilla", "dungeon", "regional", "overworld", "any_dungeon", "keysanity")
OWNS = {
    "shuffle_smallkeys": KEYS_MODES,
    "shuffle_bosskeys": KEYS_MODES,
    "shuffle_map": ("startwith",) + KEYS_MODES,
    "shuffle_compass": ("startwith",) + KEYS_MODES,
    # on_lacs: OoTR puts the key at the Light Arrow cutscene, a scene location whose give step calls the key's credit
    # entry. With the count conditions (and 'triforce', a Triforce Hunt's), Ganon's boss lock opens while OoTR's
    # condition holds (_dungeons_ganon.py).
    "shuffle_ganon_bosskey": KEYS_MODES + ("on_lacs",) + ganon.CONDITIONS,
    "ganon_bosskey_medallions": None, "ganon_bosskey_stones": None, "ganon_bosskey_rewards": None,
    "ganon_bosskey_tokens": None, "ganon_bosskey_hearts": None,
    "key_rings_choice": None, "key_rings": None, "keyring_give_bk": None,
    # The cells are plain Obj_DoorChainLock_A_01 locks spending DungeonInfo.GerudoFortress.SmallKeyNum, so a hideout key
    # found elsewhere is credited like a dungeon key. The guards' key spots give their seed item when the guard is
    # defeated (SageOfSpirit_RescueCarpenter, hideout_plan). remove is OoTR's value with gerudo_fortress open (no jail).
    "shuffle_hideoutkeys": ("vanilla", "remove", "fortress", "regional", "overworld", "any_dungeon", "keysanity"),
    # 'vanilla': the spots can also give a seed item (remake_silver_rupee_items, _dungeons_silver.py). The other values
    # give a saved count per puzzle that the silver-rupee items credit, and the counter is gone at 5
    # (_dungeons_silver_shuffle.py).
    "shuffle_silver_rupees": silver.SHUFFLE_MODES,  # the values _dungeons_silver.py builds
    "silver_rupee_pouches_choice": None, "silver_rupee_pouches": None,  # a pouch sets its puzzle's count to 5
    "enhance_map_compass": None,
    "key_appearance_match_dungeon": None,  # cosmetic: the remake has one key model either way
    "mq_dungeons_mode": None, "mq_dungeons_specific": None, "mq_dungeons_count": None,
    "empty_dungeons_mode": None, "empty_dungeons_specific": None, "empty_dungeons_rewards": None,
    "empty_dungeons_count": None,
    "dungeon_shortcuts_choice": None, "dungeon_shortcuts": None,
}

KINDS = ("Small Key Ring", "Small Key", "Boss Key", "Map", "Compass")
MODEL = {"Small Key Ring": "Item_Dungeon_SmallKey", "Small Key": "Item_Dungeon_SmallKey",
         "Boss Key": "Item_Dungeon_BossKey", "Map": "Item_Dungeon_Map", "Compass": "Item_Dungeon_Compass"}
MODEL.update({k: silver_shuffle.MODEL for k in silver_shuffle.KINDS})  # (named only: the hold-up shows its display,
#                                                                         silver_shuffle.DISPLAY)
SMALL_CHESTS = ("Obj_TBox_A_01", "Obj_TBox_A_01_NoBake")
BIG_CHESTS = ("Obj_TBox_A_02", "Obj_TBox_A_02_NoBake", "Obj_TBox_A_03", "Obj_TBox_A_03_NoBake")
SCENE_CHESTS = {"small": SMALL_CHESTS, "big": ("Obj_TBox_A_02", "Obj_TBox_A_02_NoBake")}  # TODO: A_03 is untested
GET_FILE = "Dm_SY_GetInEvent"
CHEST_FILE = {"small": "Dm_SY_TreasureboxSmall", "big": "Dm_SY_Treasurebox"}
SCENE_ENTRY = {"small": "Rando_DungeonItem_small", "big": "Rando_DungeonItem_big"}
ROWS = WORLD["scene_rows"]
SCRATCH = WORLD["scratch_string"]
BIG_SCENE = json.load(open(os.path.join(HERE, "data", "rando", "dungeons_scenes.json"), encoding="utf-8"))["big"]
YES, NO = 0, 1  # query answers (README: case 0 = yes)


def dungeon_item(name):
    """(kind, dungeon) for an OoTR dungeon item this plugin handles, else None."""
    if name == TRIFORCE_ITEM:  # Triforce Hunt's pieces (parity/_gaps_triforce.py), credited like the TCG keys
        return TRIFORCE_ITEM, TRIFORCE
    sr = silver_shuffle.dungeon_item(name)  # ("Silver Rupee" / "Silver Rupee Pouch", puzzle), shuffled values only
    if sr is not None:
        return sr
    m = re.fullmatch(r"(.+) \((.+)\)", name or "")
    if m and m.group(2) == TCG and m.group(1) in ("Small Key", "Small Key Ring"):
        return m.group(1), TCG  # the Treasure Chest Game's keys, keyed shuffle_tcgkeys modes (TCG_COUNT)
    if not m or m.group(1) not in KINDS or m.group(2) not in DUNGEONS:
        return None
    if m.group(2) == "Thieves Hideout" and m.group(1) not in ("Small Key", "Small Key Ring"):
        return None
    return m.group(1), m.group(2)


def _all_items():
    out = []
    for d, v in DUNGEONS.items():
        if v["keys"]:
            out += [f"Small Key ({d})", f"Small Key Ring ({d})"]
        if v["boss_key"]:
            out.append(f"Boss Key ({d})")
        if v["map"]:
            out += [f"Map ({d})", f"Compass ({d})"]
    return sorted(out)


CARRIER = dict(zip(_all_items(), WORLD["carriers"]))
if len(CARRIER) != len(_all_items()):
    raise RuntimeError("data/rando/dungeons_world.json: not enough carriers for every dungeon item")
# The Treasure Chest Game's keys (shuffle_tcgkeys regional / overworld / any_dungeon / keysanity). Found anywhere, each
# one adds one to a new saved count (TCG_COUNT, chests plugin: parity/_chests_tcg.py), which the game's start copies
# into the minigame's own key count. A key ring adds all six. They take the carriers after the dungeon items' (appended,
# so no dungeon item changes carrier).
TCG, TCG_COUNT, TCG_KEYS = "Treasure Chest Game", "Rando_TcgKeyNum", 6
TCG_ITEMS = (f"Small Key ({TCG})", f"Small Key Ring ({TCG})")
TCG_ENTRY, TCG_AFTER = "Rando_DI_TcgKey", "GetPouchContent:Rando_TcgKeyAfter"  # (_chests_tcg.after_graph)
CARRIER.update(zip(TCG_ITEMS, WORLD["carriers"][len(CARRIER):]))
if not all(i in CARRIER for i in TCG_ITEMS):
    raise RuntimeError("data/rando/dungeons_world.json: not enough carriers for the Treasure Chest Game's keys")
# Triforce Hunt's pieces (parity/_gaps_triforce.py). Each adds one to a new saved count and shows the count. The get
# scene holds up one golden triangle of the game's own Triforce, without a get window (parity/_gaps_triforce_look.py).
# Its create step makes the piece's display actor, while the steps that look the item up by name still name the Light
# Medallion (TRIFORCE_MODEL), whose hold-up it keeps. It takes the next carrier after the TCG keys'.
TRIFORCE, TRIFORCE_ITEM, TRIFORCE_COUNT = "Triforce", "Triforce Piece", "Rando_TriforcePieceNum"
TRIFORCE_ENTRY, TRIFORCE_MODEL, TRIFORCE_AFTER = "Rando_DI_Triforce", "Item_Medal_Light", "GetPouchContent:Rando_TriforceAfter"
TRIFORCE_SHOW_ENTRY = "Rando_DI_ShowTriforce"  # a big chest's show of the piece (show_graph with its create step)
CARRIER[TRIFORCE_ITEM] = WORLD["carriers"][len(CARRIER)]
MODEL[TRIFORCE_ITEM] = TRIFORCE_MODEL  # (a scene location's call and the big chest's fanfare name the model by kind)
# Silver rupees and pouches (shuffled shuffle_silver_rupees values, _dungeons_silver_shuffle.py) get carriers of their
# own (data/rando/silver_shuffle.json), and none of them is another item's carrier.
if set(silver_shuffle.CARRIERS) & set(CARRIER.values()):
    raise RuntimeError("data/rando/silver_shuffle.json: a silver-rupee carrier is another dungeon item's carrier")
CARRIER.update(zip(silver_shuffle.ITEMS, silver_shuffle.CARRIERS))
# Items given only by an entry of their own: the souls and the Skeleton Key (extras_souls's give entries, with the
# soul's flag and message and the key's counts) and the Magic Bean Pack (BEAN_ENTRY: the bean held up, ten beans added)
# in a small or big chest. They work like a dungeon item there. The chest holds a carrier of the item's own
# (CALL_CARRIERS: item actors no other carrier uses, each named only, never handed over) and plays the dungeon-item
# scene of its type, whose branch for that carrier calls the item's entry. In a big chest the cinematic shows the bean,
# or nothing for a soul, then the entry's _Big variant runs. Without this, chests would refuse these items (songs_trade
# no_call_locations: "a chest gives one actor and has no scene for these items").
BEAN_PACK, BEAN_ENTRY, BEAN_MODEL = "Magic Bean Pack", "Rando_DI_BeanPack", "Item_MagicBean"
CALL_FANFARE = "Obj_Heart_Container"  # a soul's or the Skeleton Key's big-chest fanfare (no model of its own)
CALL_CARRIERS = ("Item_AlarmCucco", "Item_BrokenSword", "Item_ClaimCheck", "Item_CojiroCucco", "Item_EyeDrop",
                 "Item_EyeballFrog", "Item_FairyBless_DefenseDouble", "Item_FishingRod", "Item_OddMushroom",
                 "Item_OddPowder", "Item_PoacherSaw", "Item_PocketCucco", "Item_PocketEgg", "Item_Prescription",
                 "Item_WeirdEgg", "Item_ZeldaLetter", "Obj_Bottle_Letter", "Obj_MiniGame_SmallKey",
                 "Item_Bottle_HalfMilk", "Item_Bottle_Letter",
                 "Item_Dungeon_BossKey", "Item_Dungeon_Compass", "Item_Dungeon_Map", "Item_Dungeon_SmallKey")
# OoTR's Recovery Heart and Fairy Drop, given as themselves. Otherwise every chest and scene step would give a green
# rupee for them (config/item_map.json "junk_for"). Each gets an entry in Dm_SY_GetInEvent (heal_graph) that holds up
# the item's display (config/hold_up.json "displays": Rando_Show_Heart, Rando_Show_Fairy), shows its get window
# (PouchContent Obj_Heart / Obj_Fairy GetMessage: "You got a recovery heart!", "You were graced by a fairy!") and runs
# the game's own heal for it. That's Dm_SY_Get CheckHeart's steps: the heart gauge, then
# PouchSystemActor.EventTriggerRecoverByCureItem of the item, whose CureParam says how much. One heart, or for the fairy
# HitPointRecover 20 = five hearts, like its caption says.
# Every give path calls it: chests (the item scene, like the souls), core scene locations (item_for), and through
# songs_trade._target the NPCs, the get scenes of drop spots and fairies, special deals, silver-rupee spots and the
# hideout jails. A heart taken as its own pickup gets a quiet heal, and in the air or water it's a copy of the steps.
HEAL = {"Recovery Heart": ("Rando_GiveHeart", "Obj_Heart", "Rando_Show_Heart"),
        "Fairy Drop": ("Rando_GiveFairy", "Obj_Fairy", "Rando_Show_Fairy")}


def heal_steps(actor, wait_actor="GameSystemActor"):
    """Dm_SY_Get CheckHeart's heal for cure item `actor` (Event156/146/148, Event103, Event105, Event147): steps
    without "next"."""
    return [{"actor": "UISystemActor", "action": "EventTriggerReserveRecoverOrAddHeartGauge"},
            {"actor": "UISystemActor", "action": "EventTriggerSetDisplayHeartGauge",
             "params": {"IsDisplayHeartGauge": True}},
            {"actor": wait_actor, "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 30}},
            {"actor": "PouchSystemActor", "action": "EventTriggerRecoverByCureItem", "params": {"ActorName": actor}},
            {"actor": wait_actor, "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 3}},
            {"actor": "UISystemActor", "action": "EventStartRecoverOrAddHeartGauge", "params": {"IsWaitEnd": True}}]


def _sale(location):
    """True for a scrub, the carpet salesman or a shop slot (tools/rando/shops.py), whose sale can call a heal entry."""
    sh = sys.modules.get("shops")
    return sh is not None and (sh.shop_map()["locations"].get(location) or {}).get("kind") in ("scrub", "merchant",
                                                                                                 "shop")


def heal_params(item):
    """The parameters a call to `item`'s heal entry passes. heal_graph reads ActorName for its window and hold-up."""
    return {"ActorName": HEAL[item][1]} if item in HEAL else {}


def heal_call(item):
    """'Dm_SY_GetInEvent:<entry>' giving Recovery Heart / Fairy Drop `item` (heal_graph), or None."""
    return f"{GET_FILE}:{HEAL[item][0]}" if item in HEAL else None


def _call_entries():
    """{OoTR item: its Dm_SY_GetInEvent entry} for every item a chest gives by calling an entry of its own. That's the
    names extras_souls gives its souls and the Skeleton Key, whatever this seed's settings, and the bean pack's."""
    from . import extras_souls as so
    lg = so.logic()
    out = {item: v[0] for item, v in HEAL.items()}  # first, so in nearly every seed they take the plainest carriers
    out.update({v["item"]: so._entry("boss", k) for k, v in lg["bosses"].items()})
    out[lg["ganon"]["item"]] = so._entry("ganon", "ganon")
    out.update({b["item"]: so._entry("bean", i) for i, b in enumerate(lg["beans"])})
    out[so.SKELETON] = so._entry("key", "skeleton")
    out[BEAN_PACK] = BEAN_ENTRY
    return out


CALL_ENTRIES = _call_entries()
if set(CALL_CARRIERS) & set(CARRIER.values()) or len(CALL_CARRIERS) < len(CALL_ENTRIES):
    raise RuntimeError("dungeons: CALL_CARRIERS overlaps another carrier or is too short")
CARRIER.update(zip(CALL_ENTRIES, CALL_CARRIERS))


def _enemy_call_entries():
    """{OoTR item: its entry} for the enemy souls (remake_shuffle_enemy_souls). They're given like the boss souls, by an
    entry of their own (extras_souls). A chest shows their enemy's figure rising (_look_carriers), so they take no spare
    actor of CALL_CARRIERS."""
    from . import extras_souls as so
    return {f["item"]: so._entry("enemy", k) for k, f in sorted(so.enemy_data().items()) if f.get("item")}


CALL_ENTRIES.update(_enemy_call_entries())


# What a chest running the item scene shows rising: the item's own look, which the chest's item scene can tell apart
# just like the spare items. Using a spare item of the game's as the stand-in meant that item rose out of the chest
# first (a green rupee before a small key of another dungeon, a medallion before a silver rupee, the Odd Potion before a
# soul's figure), so there's no visible stand-in.
# A heart or fairy shows its display (config/hold_up.json "displays"), a boss's or Ganon's soul its figure
# (extras_souls.display_of). Items that share a look each get their own copy of it under their own name (CARRIER_COPIES,
# built when a chest holds one, carrier_ops). That's every dungeon item and Treasure Chest Game key (its kind's model:
# small key, boss key, map, compass), every silver rupee and pouch (the silver rupee display), the bean souls (their
# figure), the Skeleton Key (the small key's model) and the bean pack (its bean). These are display actors with no
# pickup and no AI of their own, like a chest's vanilla contents (Item_* event objects). The reward names them with
# "force" because they're new types this patch makes. The Triforce piece keeps its carrier since its plugin builds the
# display.
CARRIER_COPIES = {}  # copy name -> (display it copies, or None; vanilla actor whose model it shows, or None)
SKELETON_CARRIER, BEAN_CARRIER = "Rando_Show_SkelKey", "Rando_Show_BeanPack"


def _look_carriers():
    from . import extras_souls as so
    lg = so.logic()
    out = {item: HEAL[item][2] for item in HEAL}
    for i, item in enumerate(list(_all_items()) + list(TCG_ITEMS)):
        copy = f"Rando_Show_DI{i:03d}"
        CARRIER_COPIES[copy] = (None, MODEL[dungeon_item(item)[0]])
        out[item] = copy
    for i, item in enumerate(silver_shuffle.ITEMS):
        copy = f"Rando_Show_SR{i:03d}"
        CARRIER_COPIES[copy] = (silver_shuffle.DISPLAY, None)
        out[item] = copy
    for k, v in lg["bosses"].items():
        out[v["item"]] = so.display_of("boss", k)
    out[lg["ganon"]["item"]] = so.display_of("ganon", "ganon")
    for k, f in so.enemy_data().items():  # an enemy soul: its enemy's figure
        if f.get("item"):
            out[f["item"]] = so.display_of("enemy", k)
    for i, b in enumerate(lg["beans"]):
        copy = f"Rando_Show_SoulBn{i:02d}"
        CARRIER_COPIES[copy] = (so.display_of("bean", i), None)
        out[b["item"]] = copy
    CARRIER_COPIES[SKELETON_CARRIER] = (None, "Item_Dungeon_SmallKey")
    out[so.SKELETON] = SKELETON_CARRIER
    CARRIER_COPIES[BEAN_CARRIER] = (None, BEAN_MODEL)
    out[BEAN_PACK] = BEAN_CARRIER
    import progressive  # a progressive item in a story chest (story_prog) shows its first tier, like the chest scenes
    for i, name in enumerate(sorted(PROGRESSIVE)):  # of tools/progressive.py hold the first tier
        first = PROGRESSIVE[name]["tiers"][0]
        copy = f"Rando_Show_PG{i:02d}"
        shown = progressive.HOLD_SHOW.get(first)
        CARRIER_COPIES[copy] = (shown, None) if shown else (None, first)
        out[name] = copy
    return out


CARRIER.update(_look_carriers())
if len(set(CARRIER.values())) != len(CARRIER):
    raise RuntimeError("dungeons: two items share a chest carrier")
_SOUL_DISPLAYS = {}


def soul_display(item):
    """The figure a soul item is held up as (extras_souls.display_of), or None for any other item and the Skeleton Key.
    That's what a big chest's cinematic shows for it (_show), and then its _Big entry gives it without a second
    hold-up."""
    if not _SOUL_DISPLAYS:
        from . import extras_souls as so
        lg = so.logic()
        _SOUL_DISPLAYS.update({v["item"]: so.display_of("boss", k) for k, v in lg["bosses"].items()})
        _SOUL_DISPLAYS[lg["ganon"]["item"]] = so.display_of("ganon", "ganon")
        _SOUL_DISPLAYS.update({b["item"]: so.display_of("bean", i) for i, b in enumerate(lg["beans"])})
        _SOUL_DISPLAYS.update({f["item"]: so.display_of("enemy", k) for k, f in so.enemy_data().items()
                               if f.get("item")})
    return _SOUL_DISPLAYS.get(item)


def carrier_force(item):
    """True if `item`'s chest carrier is a type this patch makes (a display or a copy), so the reward says "force"."""
    import progressive
    c = CARRIER.get(item)
    return c in CARRIER_COPIES or c in progressive.HOLD_DISPLAYS


def carrier_ops(items, romfs=None):
    """{"new_files", "packs", "byml"} for the carrier copies (CARRIER_COPIES) the chests holding `items` show. Each is
    either a copy of a display or a display of a vanilla model (display_ops' recipe). A copy is progressive.display_ops
    of the display under the copy's name (its pack, ActorParam, ModelInfo and rows), and the model files are the
    display's own."""
    import progressive
    from romtools import Romfs, sarc_files, byml_load
    romfs = romfs or os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    read_pack = lambda rel: sarc_files(fs.read(rel))  # noqa: E731
    read_rows = lambda table: {row["__RowId"]: row for row in byml_load(fs.read(table))[0]}  # noqa: E731
    out = {"new_files": [], "packs": [], "byml": []}
    for copy in sorted({CARRIER[i] for i in items if CARRIER.get(i) in CARRIER_COPIES}):
        display, model_from = CARRIER_COPIES[copy]
        if display is None:  # a display of a vanilla model, built by display_ops' own recipe
            # a bag has no AS of its own
            anim = (progressive.HOLD_OWN.get(model_from) or {}).get("anim_from") or model_from
            progressive.HOLD_DISPLAYS[copy] = {"for": None, "model_from": model_from, "anim_from": anim}
            try:
                built = progressive.display_ops(copy, read_pack, read_rows, romfs)
            finally:
                progressive.HOLD_DISPLAYS.pop(copy, None)
        else:
            built = progressive.display_ops(display, read_pack, read_rows, romfs)
            old_pack, new_pack = f"Pack/Actor/{display}.pack.zs", f"Pack/Actor/{copy}.pack.zs"
            ren = lambda s: (s.replace(f"Actor/{display}.engine__actor__", f"Actor/{copy}.engine__actor__")  # noqa
                             .replace(f"ModelInfo/{display}.engine__component__", f"ModelInfo/{copy}.engine__component__"))
            for op in built["new_files"]:
                if op["to"] == old_pack:
                    op["to"] = new_pack
                    op["note"] = f"{copy}: a chest's look of {display} (dungeons CARRIER_COPIES)"
            for op in built["packs"]:
                op["pack"] = new_pack if op["pack"] == old_pack else op["pack"]
                op["file"] = ren(op["file"])
                op["set"] = {k: (ren(v) if isinstance(v, str) else v) for k, v in (op.get("set") or {}).items()}
            for op in built["byml"]:
                sets = op["add_row"]["set"]
                sets["__RowId"] = copy
                if sets.get("ActorName") == display:
                    sets["ActorName"] = copy
        for k in out:
            out[k] += built[k]
    return out


def chest_call_item(item):
    """True for an item a chest gives through the dungeon-item scene by calling its own entry (CALL_ENTRIES)."""
    return item in CALL_ENTRIES


def chest_scene_call(item, rid, world=None):
    """True if remake chest `rid` gives `item` (chest_call_item) through its item scene, meaning it's a chest of the
    patch whose final type runs one. A Recovery Heart or Fairy Drop in any other chest keeps the green rupee stand-in
    (config/item_map.json "junk_for"). The souls and the bean pack never go there (no_call_locations)."""
    return chest_call_item(item) and rid is not None and scene_chest(rid, world) is not None


# Chests whose own scene stays (a story scene hands the chest over) but still give every item through the item scene.
# The story scene's step that runs the chest's scene runs the item scene instead (rid -> how).
# - "transition": that step is an EventTransition to the big chest's scene row Dm_SY_Treasurebox, and it names the item
#   scene's row (ROWS["big"]).
# - "dispatch": Mido's house's four small chests (Success_MidoHouse: Navi's chat flag, then the small chest's Success_).
#   After the flag, a chest holding an item-scene carrier runs the item scene and any other runs the vanilla step.
# Not here: the Dampe race chest (one transition for its Hookshot and heart-piece states) and Jabu-Jabu's compass chest
# (a cutscene of its own).
STORY_ROUTES = {
    "IceCavern/chest/6859289214373847284": {"chest": "big", "file": "SageOfWater", "event": "Event60"},
    "InsideJabuJabuBelly/chest/5527401621172639818": {"chest": "big", "file": "InsideJabuJabuBelly_FocusGimmick",
                                                      "event": "Event84"},
    "DesertColossus/chest/2490063409521505179": {"chest": "big", "file": "SageOfSpirit", "event": "Event64"},
    "WaterTemple/chest/18059711820131847165": {"chest": "big", "file": "SageOfWater_FocusGimmick", "event": "Event97"},
    # Jabu-Jabu's compass chest. Its scene's transition to InsideJabuJabuBelly_GetCompass names the item scene's row
    # (NaviChat's TreasureBoxDM_NaviChat_JabuJabu_Compass, which only plays the big chest's scene).
    "InsideJabuJabuBelly/chest/3510516276638146208": {"chest": "big", "file": "InsideJabuJabuBelly_FocusGimmick",
                                                      "event": "Event230"},
    # The Dampe race's chests, one per state of Minigame_DampeRace_TreasureBoxState. The scene's state check (Event241
    # AppearHookShot, Event240 AppearHeartPiece) reaches a copy of the shared transition (Event66) that names the item
    # scene's row, then the vanilla steps after it (Event121).
    "Graveyard/chest/16041366920820397198": {"chest": "big", "file": "MiniGame_DampeRace", "branch": "Event241",
                                             "case": 0, "copy": "Event66", "after": "Event121"},
    "Graveyard/chest/5534919361313859554": {"chest": "big", "file": "MiniGame_DampeRace", "branch": "Event240",
                                            "case": 0, "copy": "Event66", "after": "Event121"},
}
# Chests with an AI of their own that still plays the scene their GetEventName names (TreasureBox.module's EventName).
# That's the Fairy Note chests (Obj_TBox_A_01_memo11, shown when a song is played by the note), small.
SCENE_EXTRA = {"Obj_TBox_A_01_memo11": "small"}
MIDO_ROUTE = {"chest": "small", "file": "Dm_SY_TreasureboxSmall", "entry": "Success_MidoHouse", "event": "Event81",
              "vanilla": "Event12"}
for _rid in ("KokiriForest/chest/4555665598794293658", "KokiriForest/chest/9725242744547055868",
             "KokiriForest/chest/12786193094758345086", "KokiriForest/chest/10831981390482426294"):
    STORY_ROUTES[_rid] = MIDO_ROUTE
STORY_GRAPH = "Rando_StoryItem_small"
# The Treasure Chest Game's chests (Obj_HrlCity_Shop_TBox_A_01 rooms, A_02 the prize). Their scenes
# (MiniGame_SequentialChoiceTreasure OpenHit / OpenMiss / OpenLastHit / OpenClear) delete the chest's content display
# and call the chest file's SuccessForMiniGame {ContentName}, which runs Success_ (for small chests Event22 after
# Event16, Navi's flag, for big ones Event86). There a carrier of the item scene runs the item scene instead (the same
# dispatch as Mido's chests), then the minigame's own steps go on (hit count, key, next room). Any other content runs
# the vanilla Success_. The chests' own AI stays the game's (_chests_tcg.verify_rooms).
TCG_ROUTES = {"small": {"chest": "small", "file": "Dm_SY_TreasureboxSmall", "entry": "SuccessForMiniGame",
                        "after": "Event16", "vanilla": "Event22", "graph": "Rando_TcgItem_small"},
              "big": {"chest": "big", "file": "Dm_SY_Treasurebox", "entry": "SuccessForMiniGame",
                      "vanilla": "Event86", "graph": "Rando_TcgItem_big"}}
for _rid, _r in REWARDS.items():
    if _r.get("kind") == "chest" and _r.get("actor") in ("Obj_HrlCity_Shop_TBox_A_01", "Obj_HrlCity_Shop_TBox_A_02") \
            and str((_r.get("extra") or {}).get("GetEventName") or "").startswith("MiniGame_ChoiceTreasure_Open"):
        STORY_ROUTES[_rid] = TCG_ROUTES["big" if _r["actor"].endswith("A_02") else "small"]
# The check-actor chests. Their own AI picks a second content when Link owns a "check" item, but the randomizer's item
# gets given whatever he owns. A chest holding an item-scene item becomes the plain small chest, the same way the chests
# plugin handles an A_04 holding a real item (same model, A_06's ActorParam's parent is A_01's).
A06 = {"Obj_TBox_A_06": "Obj_TBox_A_01", "Obj_TBox_A_06_NoBake": "Obj_TBox_A_01_NoBake"}
_story = {}  # rid -> scene kind: story chests given an item-scene item this seed (story_ops)


def story_ops(used):
    """Plan events that route this seed's story chests (_story) into the item scene. `used` is {kind: items}."""
    events, mido = [], False
    tcg = set()
    for rid, kind in sorted(_story.items()):
        r = STORY_ROUTES[rid]
        if r is MIDO_ROUTE:
            mido = True
            continue
        if r.get("graph"):  # a Treasure Chest Game chest: its file's SuccessForMiniGame dispatches (once per file)
            if r["graph"] not in tcg:
                tcg.add(r["graph"])
                n = {}
                _compare(n, sorted(used.get(r["chest"]) or ()), "", "name", lambda i, item: "ours",
                         "@" + r["vanilla"])
                n["ours"] = {"call": f":{SCENE_ENTRY[r['chest']]}", "params": {"ContentName": {"arg": "ContentName"}},
                             "next": None}
                events.append({"file": r["file"], "flowchart": r["file"], "add_graph": r["graph"], "nodes": n,
                               "start": "name", "note": "the Treasure Chest Game's chests: an item-scene carrier "
                                                        "runs the item scene"})
                route = {"event": r["after"]} if r.get("after") else {"entry": r["entry"]}
                events.append(dict({"file": r["file"], "flowchart": r["file"], "next": f"{r['graph']}_name"}, **route))
            continue
        if r.get("branch"):  # a copy of the shared transition on this chest's own branch
            graph = f"Rando_StoryItem_{r['branch']}"
            events.append({"file": r["file"], "flowchart": r["file"], "add_graph": graph, "start": "t",
                           "nodes": {"t": {"copy": r["copy"], "params_over": {"EventName": ROWS[r["chest"]]},
                                           "next": "@" + r["after"]}},
                           "note": f"{rid}: its state's branch runs the item scene"})
            events.append({"file": r["file"], "flowchart": r["file"], "event": r["branch"], "case": r["case"],
                           "next": f"{graph}_t"})
            continue
        events.append({"file": r["file"], "flowchart": r["file"], "event": r["event"], "param": "EventName",
                       "value": ROWS[r["chest"]], "note": f"{rid}: the story scene runs the item scene"})
    if mido:
        r = MIDO_ROUTE
        n = {}
        _compare(n, sorted(used.get("small") or ()), "", "name", lambda i, item: "ours", "@" + r["vanilla"])
        n["ours"] = {"call": f":{SCENE_ENTRY['small']}", "params": {"ContentName": {"arg": "ContentName"}},
                     "next": None}
        events.append({"file": r["file"], "flowchart": r["file"], "add_graph": STORY_GRAPH, "nodes": n,
                       "start": "name", "note": "Mido's chests: an item-scene carrier runs the item scene"})
        events.append({"file": r["file"], "flowchart": r["file"], "event": r["event"],
                       "next": f"{STORY_GRAPH}_name"})
    _story.clear()
    return events


def chest_calls_ok(location):
    """Whether chest `location` can give those items, meaning the patch plays it and it runs a dungeon-item scene."""
    rid = chest_rid(location)
    return rid is not None and location not in SCENE_LOCS and carrier_ok(rid)


# OoTR's vanilla items, as the remake has them
def _apply_vanilla_items():
    try:
        import LocationList
    except ImportError:  # OoTR not on the path (imported outside the generator)
        return
    for name, v in WORLD["vanilla_items"].items():
        t = LocationList.location_table.get(name)
        if t is None:
            raise RuntimeError(f"data/rando/dungeons_world.json: OoTR has no location {name}")
        if t[4] != v["item"]:
            LocationList.location_table[name] = t[:4] + (v["item"],) + t[5:]


_apply_vanilla_items()




# Settings
def check_settings(settings):
    s, out = settings, list(silver.check_settings(settings))
    if s.shuffle_hideoutkeys == "remove" and s.gerudo_fortress != "open":
        out.append("shuffle_hideoutkeys = 'remove' needs gerudo_fortress 'open': with jailed carpenters the remake's "
                   "cell doors still need their keys")
    if s.enhance_map_compass:
        out.append(f"enhance_map_compass = {s.enhance_map_compass!r}: the remake's map and compass have no "
                   f"per-dungeon text to carry the extra information; must be []")
    mq_off = (s.mq_dungeons_mode == "vanilla" or (s.mq_dungeons_mode == "count" and s.mq_dungeons_count == 0)
              or (s.mq_dungeons_mode == "specific" and not s.mq_dungeons_specific))
    if not mq_off:
        out.append(f"mq_dungeons_mode = {s.mq_dungeons_mode!r}: the remake has one layout per dungeon (no Master "
                   f"Quest dungeon files); must be 'vanilla'")
    if not (s.empty_dungeons_mode == "none" or (s.empty_dungeons_mode == "specific" and not s.empty_dungeons_specific)
            or (s.empty_dungeons_mode == "rewards" and not s.empty_dungeons_rewards)):
        out.append(f"empty_dungeons_mode = {s.empty_dungeons_mode!r}: not supported yet (needs each empty "
                   f"dungeon's story stage completed on a new file); must be 'none'")
    if not (s.dungeon_shortcuts_choice == "off" or (s.dungeon_shortcuts_choice == "choice" and not s.dungeon_shortcuts)):
        out.append(f"dungeon_shortcuts_choice = {s.dungeon_shortcuts_choice!r}: not supported yet; must be 'off'")
    return out


# Where things are
def _remake_of():
    """{OoTR location: remake chest id} for every chest the generator can patch (chest_map full/group + ours)."""
    out = {n: v["remake"] for n, v in CHEST_MAP.items() if v["mode"] in ("full", "group") and v.get("remake")}
    played = {rid: n for n, rid in out.items()}
    for n, rid in WORLD["kept_chests"].items():
        if rid in played and played[rid] != n:  # one remake chest, one OoTR location
            raise RuntimeError(f"data/rando/dungeons_world.json kept_chests: {n} -> {rid}, but chest_map.json "
                               f"already plays that chest as {played[rid]}")
        if rid not in REWARDS or REWARDS[rid]["kind"] != "chest":
            raise RuntimeError(f"data/rando/dungeons_world.json kept_chests: {n} -> {rid} is not a catalogued chest")
        out.setdefault(n, rid)
    return out


REMAKE_OF = _remake_of()


def _scene_locations():
    """{OoTR name: remake location id} for the scene (NPC, song, cutscene) locations the generator plays
    (config/rando_locations.json, same as generate.scene_locations). Their give steps can become a call to a scene entry
    (make_patch scene_call_ops), so they take dungeon items through the same Dm_SY_GetInEvent entries."""
    locs = json.load(open(os.path.join(HERE, "config", "rando_locations.json"), encoding="utf-8"))
    match = {x["ootr"]: x for x in json.load(open(os.path.join(HERE, "data", "ootr_match.json"),
                                                  encoding="utf-8"))["ootr_locations"]}
    out = {}
    for name in locs.get("verified", []) + locs.get("testing", []):
        x = match.get(name)
        if x and x["status"] == "exact" and len(x["remake"]) == 1:
            out[name] = x["remake"][0]
    return out


SCENE_LOCS = _scene_locations()
LOC_SCENE = CHEST_RULES["get_events"]["location"]


def _location_scene(rid):
    ev = (REWARDS[rid].get("extra") or {}).get("GetEventName")
    return bool(ev) and any(re.search(rx, ev) for rx in LOC_SCENE)


APPEARANCE_CHEST_TYPES = True  # scenes and plain items follow the chest type the appearance plugin gives a chest


def _actor(rid, world=None):
    """The chest type the patch gives remake chest rid: its catalogued type, or the one a look option gives it."""
    ch = _chests_plugin()  # (a real item in the remake's own ice-trap chest makes it a plain small chest)
    base = (ch.final_actor(rid) if ch is not None and hasattr(ch, "final_actor") else None) or REWARDS[rid]["actor"]
    ap = sys.modules.get("parity.appearance")
    if ap is not None and world is not None:
        retyped = ap.chest_actor(world, rid)  # (its catalogued type when no look option retypes it)
        if retyped and retyped != REWARDS[rid]["actor"]:
            return retyped
    return base


def scene_chest(rid, world=None):
    """"small" / "big": the dungeon-item scene this chest can run, or None (other chest types, or a chest that keeps a
    story/location scene of its own). With the seed's world, the scene follows the chest's final type.
    The family is progressive.scene_family's. Besides the plain small and big chests, the Lens chest
    Obj_TBox_GlassTruth_A_01 (its ActorParam's parent is Obj_TBox_A_01's, it carries A_01's AIInfo and no AI of its own)
    and the boss-key chest Obj_TBox_A_03 (parent Obj_TBox_A_02's, A_02's own root AI in its pack) open like their parent
    does, so the parent's scene runs on them. Not Obj_TBox_A_06 (its own root AI, AI/Obj_TBox_A_06.root.ainb, the
    check-actor chest), A_04 (the remake's ice-trap chest, which the chests plugin turns into a plain A_01 for a real
    item) or the Treasure Chest Game's Obj_HrlCity_Shop_TBox_* (their own AI)."""
    if _location_scene(rid):
        return (STORY_ROUTES.get(rid) or {}).get("chest")  # (a story chest whose scene can run the item scene)
    import progressive
    actor = _actor(rid) if world is None else _actor(rid, world)  # (a look option may retype it: ornate A_03 -> A_01)
    return (progressive.scene_family(A06.get(actor, actor))  # (a check-actor chest becomes the plain small chest)
            or SCENE_EXTRA.get(actor))


def carrier_ok(rid):
    return scene_chest(rid) is not None


def plain_ok(kind, rid, world=None):
    """Whether the generic item in this chest credits the dungeon it stands in. Small keys work in any chest. Vanilla
    keeps them in small, big and invisible chests, and the small chest's pouch add and the big chest's
    EventGetDungeonSmallKey both credit the current dungeon. Boss keys, maps and compasses only work in big and boss-key
    chests, whose opening (Dm_SY_Treasurebox Success_AddContent) credits them explicitly. A small chest only adds them
    to the pouch, which is unverified for them, so there they go through the scene."""
    return kind == "Small Key" or _actor(rid, world) in BIG_CHESTS


def chest_rid(location):
    """The remake chest an OoTR location is, among the chests the patch plays (the core's from chest_map and
    kept_chests, and the chests plugin's paired and new chests), or None."""
    rid = REMAKE_OF.get(location)
    if rid is None:
        ch = _chests_plugin()
        mine = ch._mine() if ch is not None and hasattr(ch, "_mine") else {}
        rid = mine.get(location)
        if rid is not None and (rid not in REWARDS or REWARDS[rid]["kind"] != "chest"):
            return None
    return rid


def needs_scene(item, location, world=None):
    """True if `item` at `location` needs the dungeon-item scene, False if the plain item does, None if this
    plugin doesn't handle the item."""
    info = dungeon_item(item)
    if info is None:
        return None
    kind, dungeon = info
    rid = chest_rid(location)
    if rid is None or dungeon in (TCG, TRIFORCE) or kind in silver_shuffle.KINDS:  # (no chest's own item credits these
        #                                                                             counts)
        return True
    return (kind == "Small Key Ring" or REWARDS[rid]["area"] != DUNGEONS[dungeon]["area"]
            or not plain_ok(kind, rid, world))


# Other plugins' locations whose item a scene step gives, so that step can call a dungeon item's credit entry the way a
# core scene location's does. Each plugin registers its own in keep_locations. That's the drops plugin's heart spots,
# scene drops and scene gifts (it asks call_target for the step in its world_plan), the songs/trade plugin's NPCs,
# merchants, mask shop and get-scene pickups, the fairies, the extras' NPC checks, the story plugin's Master Sword
# pedestal, and the shops plugin's Business Scrubs and carpet salesman. A plugin whose plan is built after this one's
# needs its items' entries asked for in advance, so after_fill asks for every dungeon item standing at one of these
# locations (_late).
CALL_LOCATIONS = set()
_late = {}  # id(world) -> {dungeon item}: the call entries after_fill asked for (each fill attempt afresh)


def call_target(item):
    """The scene call that gives dungeon item `item` at a CALL_LOCATIONS location,
    "Dm_SY_GetInEvent:Rando_DI_Call_<item>". That's its credit entry, which world_plan builds for every item asked for
    here."""
    if dungeon_item(item) is None:
        raise ValueError(f"{item} is not a dungeon item")
    _used["call"].add(item)
    return f"{GET_FILE}:{call_entry(item)}"


def allowed(location_name, item_name):
    """Whether the patch can give dungeon item `item_name` at `location_name`. OoTR's own restrictions (the
    dungeon/regional/overworld modes) are OoTR's Region.can_fill and stay as they are. Every location kind that gives an
    item through a scene step takes every dungeon item, since OoTR places them anywhere under its keysanity and
    *_anywhere values. Core scene locations, the hideout jails and CALL_LOCATIONS call the item's credit entry, and
    chests run the dungeon-item scene (or hold the plain item in their own dungeon).
    What's left is the chests that can't run any scene (scene_chest None: Obj_TBox_A_06's own AI, a chest whose story or
    minigame scene stays, the Treasure Chest Game's) and the drop spots without a get scene. There the owning plugin
    also refuses every item its pickup can't show (only a small key's own pickup credits the dungeon it's picked up
    in)."""
    need = needs_scene(item_name, location_name)
    if need is None or need is False:
        return True  # not a dungeon item, or the plain item in its own dungeon's chest
    if location_name in SCENE_LOCS or location_name in HIDEOUT or location_name in CALL_LOCATIONS:
        return True  # the give steps call the item's entry (make_patch scene_call_ops; hideout_plan; call_target)
    rid = chest_rid(location_name)
    if rid is not None:
        return carrier_ok(rid)
    info = dungeon_item(item_name)
    if info and info[0] == "Small Key":
        import drops as drop_tools  # tools/rando/drops.py
        e = drop_tools.lookup(location_name)
        if e is not None and e.get("kind") == "drop" and drop_tools.KEY_AREA.get(item_name) == e.get("area"):
            return True  # a dropped Obj_Dungeon_SmallKey counts in the dungeon it is picked up in (in-game check)
    return False  # a drop spot with no get scene (its own plugin refuses every non-pickup item there too)


def _kept(world):
    names = {loc.name for loc in world.get_locations()}
    return {n for n in WORLD["kept_chests"] if n in names
            and CHEST_MAP.get(n, {}).get("mode") not in ("full", "group")}


HIDEOUT = {n: v for n, v in WORLD["hideout_spots"].items() if not n.startswith("_")}
RESCUE = "SageOfSpirit_RescueCarpenter"  # flowchart and file (every version)
HIDEOUT_FILE = "Banc/GerudoFortress/GerudoFortress_Adult_Static.bcett.byml.zs"
GIVE_ROUTINE = f"{GET_FILE}:GetInEvent_NotTurn_NotNpc"  # the diving and frog games' give: Link alone, no NPC turn


def _hideout_spots(world, settings):
    """OoTR's hideout key locations this seed patches, when their keys are shuffled and the jails are in play. With
    gerudo_fortress fast only the 1-torch jail is an OoTR location, and the story plugin frees the other three."""
    if settings.shuffle_hideoutkeys in ("vanilla", "remove") or settings.gerudo_fortress == "open":
        return set()
    names = {loc.name for loc in world.get_locations()}
    out = {n for n in HIDEOUT if n in names}
    if settings.gerudo_fortress == "fast":
        out &= {"Hideout 1 Torch Jail Gerudo Key"}
    return out


def before_build(settings):
    silver.before_build(settings)  # the silver-rupee spot locations, when remake_silver_rupee_items is on
    silver_shuffle.before_build(settings)  # silver-rupee items are dungeon items with a shuffled value


def untested(settings):
    return silver.untested(settings) + silver_shuffle.untested(settings)


def keep_locations(world, settings):
    # the silver-rupee spots: remake_silver_rupee_items' new locations, or OoTR's own with a non-vanilla value
    spots = silver.keep_locations(world, settings) | silver_shuffle.keep_locations(world, settings)
    CALL_LOCATIONS.update(spots)  # their scene step can call a dungeon item's credit entry (call_target)
    return _kept(world) | spots | {n for n in _hideout_spots(world, settings)
                                   if world.get_location(n).item is None and not world.get_location(n).locked}


def before_fill(world, settings):
    """Dungeon items only go where the patcher can give them, and progressive items stay out of our chests that have no
    progressive scene (like generate.guard_progressive does for chest_map's)."""
    for loc in world.get_locations():
        if loc.item is not None or loc.locked or loc.type in ("Event", "Drop", "Hint", "HintStone"):
            continue
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: allowed(location.name, item.name) and prev(location, item))
    calls = "parity.songs_trade" in sys.modules  # a progressive item gets its tier entry (hideout_plan)
    for name in _hideout_spots(world, settings):
        # Without the songs/trade plugin a progressive item would need the tier scene, which this give step doesn't
        # have.
        # An ice trap needs the chests plugin's freeze entry.
        loc = world.get_location(name)
        ch = _chests_plugin()
        ice_ok = ch is not None and hasattr(ch, "scenes")
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev, ice_ok=ice_ok: (calls or item.name not in PROGRESSIVE)
                         and (ice_ok or item.name != ICE) and prev(location, item))
    import progressive
    for name in _kept(world):
        rid = WORLD["kept_chests"][name]
        loc = world.get_location(name)
        # the family includes the Lens and boss-key chests
        if _location_scene(rid) or progressive.scene_family(REWARDS[rid]["actor"]) is None:
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: item.name not in PROGRESSIVE and prev(location, item))
        # An ice trap plays the chests plugin's ice-trap scene (chests.ice_spec, registered in after_fill). A chest that
        # can't run it, or a seed without that plugin, takes other items, and generate.install_rule_fill sticks to that.
        if not _ice_capable(rid):
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: item.name != ICE and prev(location, item))
    silver.before_fill(world, settings)
    silver_shuffle.before_fill(world, settings)


ICE = "Ice Trap"
_ice = {}  # id(world) -> {OoTR location: ice-trap reward spec}, from after_fill


def _chests_plugin():
    import sys as _sys
    return _sys.modules.get("parity.chests")


def _ice_capable(rid):
    """True if the chests plugin can run a trap in chest `rid` (its trap_size). That's every chest type, with story
    chests going through their story scene."""
    ch = _chests_plugin()
    return ch is not None and hasattr(ch, "ice_spec") and getattr(ch, "trap_size", ch.ice_size)(REWARDS[rid]) is not None


def after_fill(world, settings):
    """Ice traps that landed in this plugin's chests get the chests plugin's ice-trap scene. They're registered before
    the plan is built, and its world_plan adds the scene."""
    specs = {}
    for name in sorted(_kept(world)):
        loc = world.get_location(name)
        if loc.item is None or loc.item.name != ICE:
            continue
        ch = _chests_plugin()
        spec = ch.ice_spec(WORLD["kept_chests"][name], world, name) if ch is not None else None
        if spec is None:
            raise RuntimeError(f"{name}: an ice trap in a chest that can't run the ice-trap scene")
        specs[name] = spec
    _ice[id(world)] = specs
    # We ask for the credit entries of the dungeon items at other plugins' scene-given locations now, because some build
    # their give steps after this plugin's world_plan (songs_trade, shops, story, extras_*).
    # Not for a locked spot, where the game gives its vanilla item itself, like a freestanding key's own pickup.
    _late[id(world)] = {loc.item.name for loc in world.get_locations()
                        if loc.name in CALL_LOCATIONS and loc.item is not None and not loc.locked
                        and dungeon_item(loc.item.name)}


_heal_used = set()  # Recovery Heart / Fairy Drop given by a call to their entry this seed (heal_graph)
_used = {"small": set(), "big": set(), "call": set()}  # OoTR items given through each chest type's scene or a
#                                                            scene location's call, this seed


def item_for(item, location, world):
    if item == ICE and location in _ice.get(id(world), {}):
        return _ice[id(world)][location]
    if story_prog(item, location):  # a progressive item in a story chest: the item scene calls its tier entry
        rid = chest_rid(location)
        chest = scene_chest(rid, world)
        _tier_entry(item, request=True)  # (the songs/trade plugin builds the entry; a big chest's window variant)
        if chest == "big":
            from . import _songs_trade_ops as st_ops
            ex = sys.modules.get("parity.extras_items")
            st_ops.request_host(ex.target_name(item) if ex is not None else item, window=True)
        _used[chest].add(item)
        return _scene_spec(item, rid, world, chest)
    if chest_call_item(item) and location not in SCENE_LOCS and location not in CALL_LOCATIONS \
            and chest_scene_call(item, chest_rid(location), world):
        return chest_reward(item, chest_rid(location), world, location)
    if item in HEAL and location in SCENE_LOCS:  # an NPC's, song's or cutscene's give steps call its entry
        _heal_used.add(item)
        from parity import chests
        vanilla = {r["item"] for r in chests._catalog().values() if r.get("location") == SCENE_LOCS[location]
                   or r["id"] == SCENE_LOCS[location]}
        return {"item": "Obj_Rupee_Blue" if "Obj_Rupee_Blue" not in vanilla else "Obj_Rupee_Green",
                "call": heal_call(item),  # ("item": named only, never handed over; it must differ from the vanilla)
                "call_params": heal_params(item)}  # (the entry's window names the item: heal_graph's ActorName)
    need = needs_scene(item, location, world)
    if need is False and dungeon_item(item)[1] == "Thieves Hideout":
        return MODEL[dungeon_item(item)[0]]  # the plain key in a Gerudo Fortress chest (item_map.json has no entry)
    if not need:
        return None  # not ours, or the plain item (config/item_map.json) credits the right dungeon
    if location in SCENE_LOCS or location in CALL_LOCATIONS:  # an NPC, song or cutscene (or another plugin's scene
        _used["call"].add(item)  # location, e.g. the Master Sword pedestal): its give steps call the item's own entry
        return call_spec(item)
    return chest_reward(item, chest_rid(location), world, location)


def call_spec(item):
    """The reward spec that gives dungeon item `item` at a scene location. Every give step becomes a call to its credit
    entry (make_patch scene_call_ops). "item" names its model, and whatever the step showed is never handed over."""
    return {"item": MODEL[dungeon_item(item)[0]], "call": f"{GET_FILE}:{call_entry(item)}"}


def chest_reward(item, rid, world, location=""):
    """The reward spec for dungeon item `item` in remake chest `rid` (the core's chests, this plugin's kept chests, the
    chests plugin's own). None when the plain item credits the right dungeon (config/item_map.json), else its carrier
    and the dungeon-item scene of the chest's final type. Raises if the chest can't run any scene. It also covers the
    items a chest gives by calling their own entry (chest_call_item), with their carrier and the same scene."""
    if chest_call_item(item):
        chest = scene_chest(rid, world) if rid is not None else None
        if chest is None:
            raise RuntimeError(f"{location}: {item} can't be given there (the item scene needs a small or big chest)")
        _used[chest].add(item)
        return _scene_spec(item, rid, world, chest)
    kind, dungeon = dungeon_item(item)
    if rid is None:
        raise RuntimeError(f"{location}: {item} can't be given there (no remake chest or scene give step)")
    if not (kind == "Small Key Ring" or dungeon in (TCG, TRIFORCE) or kind in silver_shuffle.KINDS
            or REWARDS[rid]["area"] != DUNGEONS[dungeon]["area"] or not plain_ok(kind, rid, world)):
        return None
    chest = scene_chest(rid, world)
    if chest is None:
        raise RuntimeError(f"{location}: {item} can't be given there (the dungeon-item scene needs a small or big "
                           f"chest)")
    _used[chest].add(item)
    return _scene_spec(item, rid, world, chest)


def _scene_spec(item, rid, world, chest):
    """The reward spec of a chest that gives `item` through the item scene of kind `chest`, with its carrier and the
    scene row. A story chest keeps its own scene, which gets routed into the item scene (STORY_ROUTES, story_ops). A
    check-actor chest becomes the plain small chest (A06)."""
    spec = {"item": CARRIER[item]}
    if carrier_force(item):
        spec["force"] = True
    if _location_scene(rid):
        _story[rid] = chest
        return spec
    actor = _actor(rid, world)
    spec["extra"] = {"GetEventName": ROWS[chest]}
    if actor in A06:
        spec["extra"]["Gyaml"] = A06[actor]
    return spec


# Scenes
FLAG = {"Boss Key": "IsGetBossKey", "Map": "IsGetMap", "Compass": "IsGetCompass"}


def story_prog(item, location):
    """True for a progressive item at a story chest the item scene is routed into (STORY_ROUTES). The scene calls the
    item's tier entry, the songs/trade plugin's RandoST_<Item>_Get, which holds up the tier Link gets and shows its
    window."""
    if item not in PROGRESSIVE or location in SCENE_LOCS or location in CALL_LOCATIONS:
        return False
    rid = chest_rid(location)
    return rid is not None and _location_scene(rid) and rid in STORY_ROUTES


def _tier_entry(item, request=False):
    from . import _songs_trade_ops as st_ops
    ex = sys.modules.get("parity.extras_items")
    name = ex.target_name(item) if ex is not None else item
    return (st_ops.request_host(name) if request else f"{GET_FILE}:{st_ops.host_entry(name)}").split(":", 1)[1]


def host_call(item):
    """(host entry, call params, ring dungeon or None): how the chest scene gives `item`. Small keys, boss keys, maps
    and compasses share two entries that take the model and the save-data name as arguments. Vanilla entries do that
    too, SageOfSpirit_RescueCarpenter Event55 sets the Bool its GameDataName argument names. A key ring adds a fixed
    number, so it has an entry per dungeon. An item given by an entry of its own (chest_call_item) uses that entry (the
    bean pack's with its model)."""
    if item in PROGRESSIVE:  # (a story chest's progressive item: story_prog)
        return _tier_entry(item), {}, None
    if chest_call_item(item):
        return CALL_ENTRIES[item], ({"ActorName": BEAN_MODEL} if item == BEAN_PACK else
                                    {"ActorName": HEAL[item][1]} if item in HEAL else {}), None
    kind, dungeon = dungeon_item(item)
    if dungeon == TRIFORCE:
        return TRIFORCE_ENTRY, {"ActorName": TRIFORCE_MODEL}, None
    if kind in silver_shuffle.KINDS:  # an entry per item, no model (silver_shuffle.host_graph)
        return silver_shuffle.host_entry(item), {}, None
    params = {"ActorName": MODEL[kind]}
    if dungeon == TCG:  # entries of their own: the key count's own message (_chests_tcg.py), not "Small Key"
        if kind == "Small Key":
            return TCG_ENTRY, params, None
        return "Rando_DI_KeyRing_TreasureChestGame", params, dungeon
    area = DUNGEONS[dungeon]["area"]
    base = f"DungeonInfo.{area}."
    if kind == "Small Key":  # the count, first-key flag and total from _dungeons_keys.KEY_ROWS
        # Msg0..Msg9 from _dungeons_text.key_slots select the window using the total before this key.
        return "Rando_DI_Key", dict(params, **keys.key_rows(area), **dtext.key_slots(area)), None
    if kind == "Small Key Ring":
        return "Rando_DI_KeyRing_" + area, params, dungeon
    msg = dtext.MSG.format(dtext.label({"Boss Key": "boss", "Map": "map", "Compass": "compass"}[kind], area))
    if kind == "Boss Key":  # its flag, then the game's boss-key display in its dungeon (_dungeons_keys.boss_show_step)
        return keys.BOSS_ENTRY, dict(params, GameDataName=base + FLAG[kind], MessageId=msg,
                                     **{keys.BANC_ARG: keys.banc(area)}), None
    return "Rando_DI_Flag", dict(params, GameDataName=base + FLAG[kind], MessageId=msg), None


def _gd_int(name, value):
    return {"actor": "GameDataActor", "action": "EventTriggerAddOrSubGameDataInt",
            "params": {"Index": -1, "GameDataName": name, "Value": value}}


def _gd_true(name):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
            "params": {"Index": -1, "GameDataName": name, "Value": True}}


def host_graph(entry, credit, big=False, window=None):
    """(entry, nodes, start) in Dm_SY_GetInEvent. It's GetInEvent_DemoNotLookAtTurnOff's hold-up (Event109 creates the
    model, Event289 locator, Event290 animation, Event112 position, all taking the ActorName argument), with its add
    step (GetPouchContent:GetPouchContentByActorName) replaced by:
    - the get window `window` (the item's own message naming its dungeon, window_step), by default
      GetPouchContent:DisplayGetByActorName, the model's vanilla window
    - the save-data write `credit` (steps) and the pick-up window
    Then comes GetInEvent_NotLookatObjectTurnOff's ending (Event111 action guide, Event80 put away and glow off,
    Event240/243 Navi). Called with ActorName, plus GameDataName, MessageId or the key's rows and messages for the
    shared entries."""
    n = {
        "show": {"copy": "Event109", "next": "loc"},
        "loc": {"copy": "Event289", "next": "anim"},
        "anim": {"copy": "Event290", "next": "pos"},
        "pos": {"copy": "Event112", "next": "msg"},
        "msg": dict(window or {"call": "GetPouchContent:DisplayGetByActorName",
                               "params": {"ActorName": {"arg": "ActorName"}}}, next="credit0"),
    }
    for i, st in enumerate(credit):
        n[f"credit{i}"] = dict(st, next=f"credit{i + 1}" if i + 1 < len(credit) else "pickup")
    n["pickup"] = {"actor": "UISystemActor", "action": "EventTriggerRequestOpenPickUpWindow",
                   "params": {"ActorName": {"arg": "ActorName"}}, "next": "guide"}
    n["guide"] = {"copy": "Event111", "next": "putaway"}
    n["putaway"] = {"copy": "Event80", "fork": ["delete", "wait"], "join": "joined"}
    n["delete"] = {"copy": "Event105", "next": None}
    n["wait"] = {"copy": "Event700", "next": "glowoff"}
    n["glowoff"] = {"copy": "Event84", "next": None}
    n["joined"] = {"copy": "Event82", "next": "navi"}
    n["navi"] = {"copy": "Event240", "next": "navi2"}
    n["navi2"] = {"copy": "Event243", "next": None}
    if big:  # after a big chest's own cinematic the item is already shown (SHOW_ENTRY), so no second hold-up
        for label in ("show", "loc", "anim", "pos"):
            del n[label]
        return entry + BIG_SUFFIX, n, "msg"
    return entry, n, "show"


BIG_SUFFIX = "_Big"
SHOW_ENTRY = "Rando_DI_Show"


def show_graph(piece=False):
    """(entry, nodes, start) in Dm_SY_GetInEvent: the item model shown above Link the way a big chest shows its
    contents. That's Event109 create, then Item_Position's own steps without its fanfare (Event686 model detail, Event51
    show with the rotating get animation, Event79 glow). Called with ActorName. `piece` makes it TRIFORCE_SHOW_ENTRY,
    whose create step makes the Triforce piece's display (the glow still names ActorName, the Light Medallion)."""
    n = {"show": triforce_look.show_node("lod") if piece else {"copy": "Event109", "next": "lod"},
         "lod": {"copy": "Event686", "next": "fire"},
         "fire": {"copy": "Event51", "next": "glow"},
         "glow": {"copy": "Event79", "next": None}}
    return TRIFORCE_SHOW_ENTRY if piece else SHOW_ENTRY, n, "show"


def call_entry(item):
    """The entry a scene location's give step calls for `item`. It takes no arguments because make_patch's call has
    none, and it calls the shared entry with them."""
    kind, dungeon = dungeon_item(item)
    return "Rando_DI_Call_" + "".join(w for w in f"{kind} {dungeon}".title().split() if w.isalnum())


def call_graphs(items):
    out = []
    for item in sorted(items):
        entry, params, _ = host_call(item)
        out.append((call_entry(item), {"call": {"call": f":{entry}", "params": params, "next": None}}, "call"))
    return out


def _credit(item, world, name=None):
    """The save-data steps that give dungeon item `item`. A small key adds one to its dungeon's key count, a key ring
    the dungeon's full count (and its boss key when the ring carries it), and anything else sets its flag. `name` is the
    save-data name to write. It defaults to the item's own, it's {"arg": "GameDataName"} in the shared entries, and a
    small key writes the game's three key rows, then asks for the dungeon's key counter when the player is in it
    (_dungeons_keys.key_steps)."""
    entry, params, ring = host_call(item)
    if entry == "Rando_DI_Key":
        return keys.key_steps(keys.key_args() if name is not None else params, 1, show=True)
    if entry == "Rando_DI_Flag":
        return [_gd_true(name or params["GameDataName"])]
    if entry == keys.BOSS_ENTRY:  # as the game's own boss-key get: the flag, then (in its dungeon) the display
        return [_gd_true(name or params["GameDataName"]),
                keys.boss_show_step({"arg": keys.BANC_ARG} if name is not None else params[keys.BANC_ARG])]
    if entry == TCG_ENTRY:  # one key, then OoTR's "... for the Treasure-Chest Shop! (first / N / enough)"
        return [_gd_int(TCG_COUNT, 1), {"call": TCG_AFTER}]
    if ring == TCG:  # the ring's six, then OoTR's ring message (_dungeons_text)
        return [_gd_int(TCG_COUNT, TCG_KEYS), dtext.text_window(dtext.MSG.format(dtext.label("ring", dtext.TCG)))]
    if entry == TRIFORCE_ENTRY:  # the count, then its own message (n of goal) and, at the goal, the ending
        return [_gd_int(TRIFORCE_COUNT, 1), {"call": TRIFORCE_AFTER}]
    if silver_shuffle.dungeon_item(item):  # the count, its message and the room's flags at 5 (GetPouchContent)
        return [{"call": silver_shuffle.message_call(item)}]
    d = DUNGEONS[ring]
    base = f"DungeonInfo.{d['area']}."
    credit = keys.key_steps(keys.key_rows(d["area"]), max(d["keys"], d["doors"]), show=True)
    if world is not None and d["boss_key"] and world.keyring_give_bk(ring):
        credit += [_gd_true(base + "IsGetBossKey"), keys.boss_show_step(keys.banc(d["area"]))]
    return credit


def window_step(item, world, shared=False):
    """The get window naming `item`'s dungeon in OoTR's words (_dungeons_text, a GetPouchContent call with no "next"),
    or None for items whose credit has its own message (Treasure Chest Game keys, Triforce pieces, silver rupees). With
    `shared` it's for the shared entries and reads their own arguments (a small key's TotalName and Msg0..Msg9,
    MessageId)."""
    entry, params, ring = host_call(item)
    if entry == "Rando_DI_Key":
        return dtext.key_window({k: {"arg": k} for k in (dtext.TOTAL_ARG,) + dtext.SLOT_ARGS} if shared else params)
    if entry in ("Rando_DI_Flag", keys.BOSS_ENTRY):
        return dtext.text_window({"arg": "MessageId"} if shared else params["MessageId"])
    if ring is not None and ring != TCG:  # (OoTR's "Key Ring ... It includes the Boss Key!" when it carries it)
        d = DUNGEONS[ring]
        bk = world is not None and d["boss_key"] and world.keyring_give_bk(ring)
        return dtext.text_window(dtext.MSG.format(dtext.label("ringbk" if bk else "ring", d["area"])))
    return None


def resident_give(item, world):
    """(model, save-data steps) that give dungeon item `item` inside a resident get scene, which can't call the
    Dm_SY_GetInEvent entries (tools/rando/parity/_songs_trade_lake.py RESIDENT_HOST). The caller shows the item's window
    itself (window_step, a GetPouchContent call, which those scenes are allowed to make) and runs the steps."""
    entry, params, ring = host_call(item)
    if entry == TRIFORCE_ENTRY or ring == TCG or entry == TCG_ENTRY:  # no stand-in window: the credit's own message
        return None, _credit(item, world)
    if silver_shuffle.dungeon_item(item):  # no model at all: the credit's own message (GetPouchContent)
        return None, _credit(item, world)
    return params["ActorName"], _credit(item, world)


def host_graphs(items, world, big_items=()):
    """The Dm_SY_GetInEvent entries the seed's items need, plus their big-chest variants for big_items. A shared entry
    gets its _Big variant when any of its items stands in a big chest, not just the first one sorted."""
    out = {}
    big_entries = {host_call(i)[0] for i in big_items}
    for item in sorted(items):
        entry, _, ring = host_call(item)
        if entry in out:
            continue
        if item in HEAL:  # its display held up, its window, the game's heal
            out[entry] = heal_graph(item)
            if entry in big_entries:
                out[entry + BIG_SUFFIX] = heal_graph(item, big=True)
            continue
        if item == BEAN_PACK:  # the bean held up, its window, ten beans (the game's own add, as RandoST_BeanPack's)
            add = {"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
                   "params": {"Actor": BEAN_MODEL, "Num": 10, "IsEquipDIrect": False,
                              "IsSetMessageTargetActorName": False, "IsGetEvent": False}}
            out[entry] = host_graph(entry, [add])
            if entry in big_entries:
                out[entry + BIG_SUFFIX] = host_graph(entry, [add], big=True)
            continue
        if chest_call_item(item) or item in PROGRESSIVE:  # a soul or the Skeleton Key: extras_souls builds the
            # entry (a progressive item's tier entry: the songs/trade plugin); after a big chest's cinematic its _Big
            if entry in big_entries:  # variant: a soul's give without the hold-up (the cinematic showed its figure,
                # _show), else it just calls the entry (nothing was shown)
                from . import extras_souls as so
                shown = so.shown_give(item, world) if soul_display(item) else None
                out[entry + BIG_SUFFIX] = (entry + BIG_SUFFIX, *shown) if shown else \
                    (entry + BIG_SUFFIX, {"c": {"call": f"{GET_FILE}:{entry}", "next": None}}, "c")
            continue
        if silver_shuffle.dungeon_item(item):  # its display held up, the credit (count, message, flags), put away,
            out[entry] = silver_shuffle.host_graph(item)  # the solved jingle; after a big chest's cinematic (which
            if entry in big_entries:  # showed the display already) the same without the hold-up
                out[entry + BIG_SUFFIX] = silver_shuffle.host_graph(item, big=True)
            continue
        shared = entry in ("Rando_DI_Key", "Rando_DI_Flag", keys.BOSS_ENTRY)
        credit = _credit(item, world, {"arg": "GameDataName"} if shared else None)
        window = window_step(item, world, shared)  # its message naming its dungeon (_dungeons_text)
        out[entry] = host_graph(entry, credit, window=window)
        if entry in big_entries:
            out[entry + BIG_SUFFIX] = host_graph(entry, credit, big=True, window=window)
        if entry in (TRIFORCE_ENTRY, TCG_ENTRY) or ring == TCG:  # no get or pick-up window of the model: its own
            #                                                             message instead
            out[entry] = _without_windows(*out[entry])
            if entry + BIG_SUFFIX in out:
                out[entry + BIG_SUFFIX] = _without_windows(*out[entry + BIG_SUFFIX])
        if entry == TRIFORCE_ENTRY:  # the piece's own display (the big-chest variant shows nothing: TRIFORCE_SHOW_ENTRY)
            e, n, start = out[entry]
            out[entry] = (e, dict(n, show=triforce_look.show_node(n["show"]["next"])), start)
    if big_items:
        out[SHOW_ENTRY] = show_graph()
    if TRIFORCE_ITEM in big_items:
        out[TRIFORCE_SHOW_ENTRY] = show_graph(piece=True)
    if any(silver_shuffle.dungeon_item(i) for i in big_items):
        out[silver_shuffle.SHOW_ENTRY] = silver_shuffle.show_graph()
    return [out[k] for k in sorted(out)]


def _without_windows(entry, n, start):
    """A host graph without its "msg" (the model's get window) and "pickup" (its pick-up window) steps."""
    n = {k: dict(v) for k, v in n.items()}
    last = max(int(k[6:]) for k in n if k.startswith("credit"))
    for k, v in n.items():
        if v.get("next") == "msg":
            v["next"] = "credit0"
    n[f"credit{last}"]["next"] = n["pickup"]["next"]
    del n["msg"], n["pickup"]
    return entry, n, "credit0" if start == "msg" else start


def _open_pose(command):
    return {"actor": "Player_Event", "action": "EventPlayerPlayASForFlowchart", "next": None,
            "params": {"KeepOneTimeAnm": False, "ForceFadeFrame": -1.0, "IsWaitEnd": True, "ASCommand": command,
                       "IsAllSlot": True, "UseAnmDriven": True, "ClothWarpMode": 0}}


def _compare(n, items, prefix, first, give, nomatch):
    """Nodes `first`, which copies the chest's stand-in name into the scratch string, and {prefix}is<i>, which compare
    it with each carrier in order. A match goes to give(i, item), no match to `nomatch`."""
    from write_read_check import settle  # the name lands a frame or two later: compare after it
    n[first] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                "params": {"GameDataName": SCRATCH, "Index": -1, "Value": {"arg": "ContentName"}},
                "next": f"{prefix}settle"}
    n[f"{prefix}settle"] = settle(f"{prefix}is0")
    for i, item in enumerate(items):
        n[f"{prefix}is{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                               "params": {"GameDataName": SCRATCH, "Index": -1, "Value": CARRIER[item]},
                               "cases": {YES: give(i, item), NO: f"{prefix}is{i + 1}" if i + 1 < len(items) else nomatch}}


def _give(n, label, item, nxt, big=False):
    if big and item in PROGRESSIVE:  # shown already (_show): its window and add, then the shown tier put away
        n[label] = {"call": _tier_window(item), "next": f"{label}_hide"}
        n[f"{label}_hide"] = {"actor": "Player_Event", "action": "EventDeleteShowItem",
                              "params": {"IsWaitEnd": True, "IsFadeOut": False, "IsScaleOut": False,
                                         "ChangeVisibleOffWithRequestDelete": False}, "next": nxt}
        return label
    entry, params, _ = host_call(item)
    n[label] = {"call": f"{GET_FILE}:{entry}{BIG_SUFFIX if big else ''}", "params": params, "next": nxt}
    return label


def heal_graph(item, big=False):
    """(entry, nodes, start): host_graph showing the item's display (not the pickup actor, which can't be held up), with
    its own get window, the heal as the credit and no pick-up window. Called with ActorName (Obj_Heart / Obj_Fairy)."""
    entry, actor, display = HEAL[item]
    e, n, start = host_graph(entry, heal_steps(actor), big=big)
    n = {k: dict(v) for k, v in n.items()}
    if "show" in n:
        n["show"] = {"copy": "Event109", "params_over": {"Actor": display}, "next": "loc"}
    last = max(int(k[6:]) for k in n if k.startswith("credit"))
    n[f"credit{last}"]["next"] = n["pickup"]["next"]
    del n["pickup"]
    return e, n, start


def _show(n, label, item):
    if item in HEAL:  # its display, shown the big chest's way
        n[label] = {"call": f"{GET_FILE}:{SHOW_ENTRY}", "params": {"ActorName": HEAL[item][2]}, "next": None}
        return label
    if item in PROGRESSIVE:  # the tier Link gets, shown the big chest's way (progressive.big_chest_graphs' show)
        return _tier_show(n, label, item)
    if soul_display(item):  # a soul: its figure, shown the big chest's way (its _Big entry: no second hold-up)
        n[label] = {"call": f"{GET_FILE}:{SHOW_ENTRY}", "params": {"ActorName": soul_display(item)}, "next": None}
        return label
    if chest_call_item(item) and item != BEAN_PACK:  # the Skeleton Key: no model to show
        n[label] = {"actor": "GameSystemActor", "action": "EventWait", "params": {"Frames": 1, "IsWaitEnd": True},
                    "next": None}
        return label
    if silver_shuffle.dungeon_item(item):  # its own display (silver_shuffle.show_graph)
        n[label] = {"call": f"{GET_FILE}:{silver_shuffle.SHOW_ENTRY}", "next": None}
        return label
    entry, params, _ = host_call(item)
    show = TRIFORCE_SHOW_ENTRY if entry == TRIFORCE_ENTRY else SHOW_ENTRY  # (the piece's own display)
    n[label] = {"call": f"{GET_FILE}:{show}", "params": {"ActorName": params["ActorName"]}, "next": None}
    return label


def _tier_show(n, label, item):
    """Nodes from `label`. First what Link owns, highest tier first (owning tier k or above shows tier k+1, and the top
    tier repeats, in progressive._tier_checks' order with owned_by's actors). Then that tier shown above Link
    (progressive.show_item_nodes, using its display stand-in where it has one). Ends with next None."""
    import progressive
    tiers = PROGRESSIVE[item]["tiers"]
    top = len(tiers) - 1

    def show(k):
        lab = f"{label}_t{k}"
        nodes = progressive.show_item_nodes(tiers[k], None, progressive.show_of(tiers[k]))
        ren = {key: f"{lab}_{key}" for key in nodes}
        for key, node in nodes.items():
            node = dict(node)
            if node.get("next") in ren:
                node["next"] = ren[node["next"]]
            n[ren[key]] = node
        return ren["show"]

    shows = {k: show(k) for k in range(top + 1)}
    order = list(range(top, -1, -1))
    for j, k in enumerate(order):
        actors = progressive.owned_by(tiers[k])
        for i, actor in enumerate(actors):
            here = label if (j, i) == (0, 0) else f"{label}_h{j}_{i}"
            nxt = (f"{label}_h{j}_{i + 1}" if i + 1 < len(actors)
                   else f"{label}_h{j + 1}_0" if j + 1 < len(order) else shows[0])
            n[here] = {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                       "params": {"Actor": actor, "Num": 1}, "cases": {YES: shows[min(k + 1, top)], NO: nxt}}
    return label


def _tier_window(item):
    """The tier entry next to the get window, with no hold-up, for a big chest that already showed the tier. That's the
    songs/trade plugin's GetPouchContent:RandoST_Pouch_<Item> (requested with the reward, story_prog)."""
    ex = sys.modules.get("parity.extras_items")
    name = ex.target_name(item) if ex is not None else item
    return "GetPouchContent:RandoST_Pouch_" + "".join(w for w in name.title().split() if w.isalnum())


def _ending(n, first, last=None):
    """Dm_SY_TreasureboxSmall Success_'s ending: mark opened, release the pause, save (then `last`)."""
    n[first] = {"actor": "GameSystemActor", "action": "EventWait", "params": {"Frames": 1, "IsWaitEnd": True},
                "next": "markopened"}
    n["markopened"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTreasureBoxOpened", "next": "unpause"}
    n["unpause"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTBoxErasePauseMask", "next": "save"}
    n["save"] = {"actor": "GameSystemActor", "action": "EventTriggerRequestAutoSave", "next": last}


def small_chest_graphs(items):
    """[(entry, nodes, start)] for Dm_SY_TreasureboxSmall, with tools/progressive.py chest_scene's opening and ending.
    The chest's stand-in contents tell which dungeon item it is."""
    n = {"face": {"actor": "TreasureBox_EventStarter", "query": "EventQueryIsFaceToFace",
                  "params": {"ActorName": "Player_Event"}, "cases": {YES: "front", NO: "kick"}}}
    for side, pose, rumble in (("front", "DemoOpenTreasureBoxFront", ":FrontVibration"),
                               ("kick", "DemoOpenTreasureBoxWithKick", ":KickVibration")):
        n[side] = {"fork": [f"pose_{side}", f"lid_{side}", f"rumble_{side}"], "join": f"opened_{side}"}
        n[f"pose_{side}"] = _open_pose(pose)
        n[f"lid_{side}"] = {"call": ":TresureboxSmall_Animation", "next": None}
        n[f"rumble_{side}"] = {"call": rumble, "next": None}
        n[f"opened_{side}"] = {"join": True, "next": "name"}
    items = sorted(items)
    _compare(n, items, "", "name", lambda i, item: _give(n, f"give{i}", item, "wait1"), "wait1")
    _ending(n, "wait1")
    return [(SCENE_ENTRY["small"], n, _content_off(n, items, "face"))]


DELETE_CONTENT = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTBoxRequestDeleteContentDisplay"}


def _content_off(n, items, start):
    """A chest holding a progressive item's carrier shows nothing of its own. The chest's content display gets deleted
    first (TreasureBox_EventStarter.EventTriggerTBoxRequestDeleteContentDisplay, like the Treasure Chest Game does
    before its chests' scene), so the item that rises is the tier Link gets (a small chest's hold-up, a big chest's
    show, _show). Returns the scene's new start (`start` when no item is progressive)."""
    prog = sorted(i for i in items if i in PROGRESSIVE)
    if not prog:
        return start
    _compare(n, prog, "d_", "pre", lambda i, item: "delc", start)
    n["delc"] = dict(DELETE_CONTENT, next=start)
    return "pre"


def big_chest_graphs(items):
    """[(entry, nodes, start)] for Dm_SY_Treasurebox, like tools/progressive.py big_chest_graphs. The big chest's
    vanilla cinematic is copied step for step (data/rando/dungeons_scenes.json) into an entry named like the original,
    with its contents display replaced by the dungeon-item branch. Before it comes the fanfare for the item's model,
    after it Success_'s 90-frame wait and the ending."""
    items = sorted(items)
    perform = SCENE_ENTRY["big"] + "_perform"
    pn = json.loads(json.dumps(BIG_SCENE["nodes"]))
    # Where the chest shows its contents we show the item's model the big chest's way (no second hold-up).
    _compare(pn, items, "g_", BIG_SCENE["stop"], lambda i, item: _show(pn, f"g_show{i}", item), None)
    n = {}
    _compare(n, items, "", "name", lambda i, item: f"fanfare{i}", "perform")
    for i, item in enumerate(items):
        n[f"fanfare{i}"] = {"actor": "SoundSystemActor", "action": "EventTriggerSoundStartFanfare",
                            "params": {"IsEnableIntro": True, "GameDataName": "",
                                       "ActorName": silver_shuffle.FANFARE if silver_shuffle.dungeon_item(item)
                                       else PROGRESSIVE[item]["tiers"][0] if item in PROGRESSIVE
                                       else (BEAN_MODEL if item == BEAN_PACK else HEAL[item][1] if item in HEAL
                                             else CALL_FANFARE)
                                       if chest_call_item(item) else MODEL[dungeon_item(item)[0]]},
                            "next": "perform"}
    n["perform"] = {"call": f":{perform}", "params": {"ContentName": {"arg": "ContentName"}}, "next": "wait90"}
    n["wait90"] = {"copy": BIG_SCENE["wait90"], "next": "c_name"}
    # The big chest normally adds its contents after the wait, so this is where we show the window and credit the
    # dungeon.
    _compare(n, items, "c_", "c_name", lambda i, item: _give(n, f"c_give{i}", item, "wait1", big=True), "wait1")
    _ending(n, "wait1", "glowoff")
    n["glowoff"] = {"actor": "EventEffectEmitter", "action": "EventEffectStopGetItem", "next": None}
    return [(perform, pn, BIG_SCENE["start"]), (SCENE_ENTRY["big"], n, _content_off(n, items, "name"))]


def scene_plan(used, world):
    """Plan sections for the dungeon-item scenes, given {chest type: OoTR items given through it}."""
    events, byml = [], []
    for entry, nodes, start in host_graphs(set().union(*used.values()), world, set(used.get("big", ()))) + call_graphs(used.get("call", ())):
        events.append({"file": GET_FILE, "flowchart": GET_FILE, "add_graph": entry, "nodes": nodes, "start": start})
    for chest, graphs in (("small", small_chest_graphs), ("big", big_chest_graphs)):
        if not used.get(chest):
            continue
        for entry, nodes, start in graphs(used[chest]):
            events.append({"file": CHEST_FILE[chest], "flowchart": CHEST_FILE[chest], "add_graph": entry,
                           "nodes": nodes, "start": start})
        byml.append({"file": "RSDB/EventSetting.Product.111.rstbl.byml.zs",
                     "replace_row": {"row": ROWS[chest], "copy_of": CHEST_FILE[chest],
                                     "set": {"EntryPointName": SCENE_ENTRY[chest]}}})
    return {"events": events, "byml": byml}


# Plan
def _defaults(settings):
    s, d = settings, {}
    for dungeon, v in DUNGEONS.items():
        if dungeon == "Thieves Hideout":
            continue
        base = f"DungeonInfo.{v['area']}."
        if s.shuffle_smallkeys == "remove" and v["keys"]:  # the count, its total and the first-key flag
            d.update(keys.key_defaults(v["area"], max(v["keys"], v["doors"])))
        if v["boss_key"]:
            mode = s.shuffle_ganon_bosskey if dungeon == "Ganons Castle" else s.shuffle_bosskeys
            if mode == "remove":
                d[base + "IsGetBossKey"] = True
        if v["map"]:
            if s.shuffle_map == "startwith":
                d[base + "IsGetMap"] = True
            if s.shuffle_compass == "startwith":
                d[base + "IsGetCompass"] = True
    if s.shuffle_smallkeys in ("vanilla", "dungeon"):
        # OoTR (not keysanity) removes the lock on the Fire Temple's boss-key loop door with a ROM patch and counts a
        # free key for it. The remake keeps the lock (door #17955), so it starts unlocked on a new file.
        d[WORLD["fire_loop_door"]["flag"]] = True
    return d


def hideout_plan(settings, world):
    """Plan sections that give each hideout key spot its seed item (keys shuffled). The guard's key no longer appears:
    GerudoThiefDropKey skips the key's steps Event158/Event160, both key placements per cell stay hidden (Presence on
    the key's own taken flag, which nothing sets any more), and the guards drop no key. The guard's defeat entry
    (DestroyGerudoThief0N, one call to GerudoThiefDropKey) goes on to a give step instead: a dungeon item's credit
    entry, the chests plugin's freeze for an ice trap, or the give routine with the item's model. Only those steps and
    placements get edited (the carpenters' rescue itself belongs to the story plugin)."""
    spots = _hideout_spots(world, settings)
    if not spots:
        return {}
    import generate
    events = [{"file": RESCUE, "flowchart": RESCUE, "event": "Event242", "next": "Event377"}]
    placements, notes = [], []
    for name in sorted(HIDEOUT):  # every jail's key is hidden once the shared drop steps are skipped
        spot = HIDEOUT[name]
        for h in spot["keys"]:
            placements.append({"file": HIDEOUT_FILE, "hash": h, "set": {
                "Presence": {"FlagName": spot["flag"], "IsCheckLazy": False, "IsNegation": False}}})
        placements.append({"file": HIDEOUT_FILE, "hash": spot["guard"], "remove": ["Dynamic.Drop__DropActor"]})
    for name in sorted(spots):
        spot = HIDEOUT[name]
        item = world.get_location(name).item.name
        if dungeon_item(item):
            _used["call"].add(item)
            node = {"call": f"{GET_FILE}:{call_entry(item)}", "next": None}
        elif item == ICE:  # (the trap kind this spot drew, remake_trap_weights)
            node = {"call": _chests_plugin().trap_call(world, name), "next": None}
        else:  # the shared resolver (songs_trade.plain_give): a progressive item's tier entry, the bean
            # pack's or a soul's entry or a hatched egg, else the item's own hold-up (config/hold_up.json) or the
            # give routine
            import progressive
            st = sys.modules.get("parity.songs_trade")
            how = st.plain_give(item, name) if st is not None and hasattr(st, "plain_give") else None
            if how is None and item in PROGRESSIVE:
                raise RuntimeError(f"{name}: {item} (progressive) where the give step has no tier scene")
            if how and how[0] == "call":
                node = {"call": how[1], "next": None}
            else:
                actor = how[1] if how else generate.remake_item(item)
                node = progressive.hold_node(actor, None) or {"call": GIVE_ROUTINE, "params": {"ActorName": actor},
                                                              "next": None}
        graph = f"Rando_Hideout_{spot['entry_event']}"
        events.append({"file": RESCUE, "flowchart": RESCUE, "add_graph": graph, "nodes": {"give": node},
                       "start": "give"})
        events.append({"file": RESCUE, "flowchart": RESCUE, "event": spot["entry_event"], "next": f"{graph}_give"})
        notes.append(f"{name}: {item}")
    return {"events": events, "placements": placements, "_notes_dungeons_hideout": notes}


def world_plan(settings, world):
    import generate
    mods = generate.plugins()
    from . import _dungeons_routes as routes  # every placed dungeon item's give path reaches its credit (read-back)
    plan = {"rewards": {}, "_gaps": {"small_keys": keys.NOTE,  # every key credit's read-back (_dungeons_keys)
                                     "dungeon_items": routes.note(world, settings),
                                     "dungeon_text": dtext.NOTE},  # every dungeon item's window names its dungeon
            "events": [keys.show_event(),  # the key counter request every small-key credit ends with
                       keys.boss_show_event()]  # and the boss-key display every boss-key credit ends with
            + dtext.events(),  # the windows (GetPouchContent) and the game's own window for the generic items
            # OoTR's dungeon item messages, one set per language. The Treasure Chest Game's count messages are the
            # chests plugin's labels (_chests_tcg.after_texts).
            "text": dtext.text_ops(only=dtext.plan_labels())}
    sr = silver.world_plan(settings, world)  # first: its dungeon items join this seed's credit entries (_used)
    for k, v in sr.items():
        plan[k] = plan.get(k, []) + v
    ss = silver_shuffle.world_plan(settings, world)  # the same for OoTR's other values (merged below)
    planned = {}  # remake chest id -> what the plan puts there (ours)
    for name in sorted(_kept(world)):
        rid = WORLD["kept_chests"][name]
        item = world.get_location(name).item.name
        target = generate.plugin_item(mods, item, name, world)
        planned[rid] = target
        plan["rewards"][rid] = dict(target, note=f"{name}: {item}") if isinstance(target, dict) else \
            {"item": target, "note": f"{name}: {item}"}
    defaults = _defaults(settings)
    if defaults:
        plan["gamedata"] = {"defaults": defaults}
    for k, v in hideout_plan(settings, world).items():
        plan[k] = plan.get(k, []) + v if isinstance(v, list) else v
    for k, v in ganon.world_plan(settings, world).items():  # Ganon's boss key on a condition
        if k == "gamedata":
            plan["gamedata"] = [x for x in ([plan["gamedata"]] if "gamedata" in plan else [])] + [v]
        elif isinstance(v, list):
            plan[k] = plan.get(k, []) + v
        else:
            plan[k] = dict(plan.get(k, {}), **v)
    for k, v in ss.items():  # silver rupees with a non-vanilla value: save data, placements, AI, scenes, text, _gaps
        if k == "gamedata":
            old = plan.get("gamedata")
            plan["gamedata"] = ([] if old is None else [old] if isinstance(old, dict) else list(old)) + [v]
        elif isinstance(v, list):
            plan[k] = plan.get(k, []) + v
        else:
            plan[k] = dict(plan.get(k, {}), **v)
    _used["call"] |= _late.pop(id(world), set())  # (after_fill: other plugins' scene-given locations)
    # The heal entries for a heart or fairy at a location whose give step calls (other plugins' scene-given locations,
    # the core scene locations, the hideout jails). Built here for every plugin's plan.
    _heal_used.update(loc.item.name for loc in world.get_locations() if loc.item is not None
                      and loc.item.name in HEAL and not loc.locked
                      and (loc.name in CALL_LOCATIONS or loc.name in SCENE_LOCS or loc.name in HIDEOUT
                           or _sale(loc.name)))
    heal_extra = sorted(_heal_used - set().union(*_used.values()))
    for entry, nodes, start in (heal_graph(i) for i in heal_extra):
        plan["events"].append({"file": GET_FILE, "flowchart": GET_FILE, "add_graph": entry, "nodes": nodes,
                               "start": start})
    _heal_used.clear()
    used = {k: set(v) for k, v in _used.items() if v}
    silver_shuffle.note_routes(plan, used, sys.modules[__name__])  # (its read-back: how each silver item is given)
    if used or sr or ss:
        for k, v in (scene_plan(used, world) if used else {}).items():
            plan[k] = plan.get(k, []) + v
        plan["events"] = plan.get("events", []) + story_ops(used)  # story chests routed into the item scene
        for k, v in carrier_ops(set().union(*used.values())).items():  # the carriers' looks of our own
            plan[k] = plan.get(k, []) + v
        # A chest that had a reused scene ID keeps its item but plays the normal opening. If the plan changes its item
        # the patcher drops that (item) scene itself, and a scene the plan gives it stays.
        by_rid = {rid: n for n, rid in REMAKE_OF.items()}
        rows = {ROWS[k] for k in used if k in ROWS} | ({silver.DATA["scene_row"]} if sr or ss else set())
        for r in REWARDS.values():
            if r["kind"] != "chest" or (r.get("extra") or {}).get("GetEventName") not in rows:
                continue
            target = planned.get(r["id"])
            if target is None and r["id"] in by_rid and by_rid[r["id"]] in CHEST_MAP:
                n = by_rid[r["id"]]
                target = generate.plugin_item(mods, world.get_location(n).item.name, n, world)
            if target is None or target == r["item"]:
                plan.setdefault("placements", []).extend(
                    {"file": f, "hash": r["hash"], "remove": ["Dynamic.GetEventName"]} for f in r["files"])
    for v in _used.values():
        v.clear()
    _ice.pop(id(world), None)
    if getattr(getattr(world, "settings", settings), "triforce_hunt", False):  # the pieces' model and display actor,
        for k, v in triforce_look.plan_sections().items():  # which every piece's hold-up and ground look create
            plan[k] = plan.get(k, []) + v if isinstance(v, list) else dict(plan.get(k, {}), **v)
    return plan
