"""Parity plugin for story and quality-of-life settings (PARITY.md "Story and quality-of-life settings").

The scene steps it hooks are read from the game files into
data/rando/story_data.json (built by tools/rando/parity/_story_build.py). Count conditions are in
_story_conditions.py.
TODO: nothing here is seen in-game yet (untested() lists every applied value for seed.json).

Story gates (every seed): gate_fixes fixes the gates where the remake is
stricter than OoTR. That's returning to child at any time (OoTR's "can always return to youth"), Sheik's Bolero
after the Fire Temple, the Requiem / jail-carpenter order, King Zora's ice kept until thawed, Bombchu Bowling
open, Biggoron's 3-day wait, the Deku Tree exit and late temples not moving the castle story and the Light Arrow
cutscene back, and the first return to child not equipping a Kokiri Sword you never found. Four of them are
32-bit edits of level-logic modules (AINB), the rest are scene steps and placements.
remake_shuffle_master_sword (remake setting, off by default, Ship of Harkinian's Master Sword Shuffle): the
pedestal ("ToT Master Sword") holds any item, given in the first trip where the sword was. The sword is an item
(scene locations only: no chest/pot pickup actor exists). The first trip only equips it for adult if you found
it. Time travel works without it, and logic needs an adult sword for time travel (see keep_locations).

How each setting is made (values the plugin refuses are listed in OWNS with the reason):
- bridge (all, 'random' as OoTR resolves it): the castle-edge level logic requests the bridge cutscene while
  Defeat_Ganon_IsAfter_Ready_Exp holds (and it's not Step01 yet). That expression becomes OoTR's condition (its
  only other user is a fishing-pond chat line). open = always, stones / medallions / dungeons = at least N of the
  IsGet flags of those items (OoTR counts the items too), tokens = Gold Skulltula count, hearts = max life,
  vanilla = after the Light Arrow cutscene with the Light Arrows held. The Light Arrow cutscene's
  "Defeat_Ganon -> Step01" is skipped once the bridge has set Step02, because story steps can go backwards.
- lacs_condition (all): the vanilla trigger (Spirit and Shadow sages awake, then the Temple of Time area) stays,
  but the cutscene first checks the condition at both of its entry points. Reading the altar of the Spiritual
  Stones in the Temple of Time as adult also starts the cutscene once the condition holds, so the condition alone
  is enough. Same item counts as the bridge, as scene queries.
- open_door_of_time: every value but stones_oot_sot (vanilla) decouples the door and the first pull from the
  DoorOfTime steps the moat scene uses (door_of_time()). With sot the door's Song of Time scene doesn't wait for
  the moat cutscene (Step04). oot_sot waits for the Ocarina of Time in the pouch instead, and stones_sot for the
  three stone stages. With stones the door's opened flag is set when the third stone stage completes
  (DoorOfTime_CheckStoneNum, run after the Fire and Water stones, and the Forest stone's exit scene). open is the
  flag's new-file default (world_settings).
- open_forest fast: like closed_deku (Mido still wants the sword and shield shown, which a child can always do
  where OoTR's logic has them). open / closed_deku / closed are done in world_settings.
- zora_fountain adult: King Zora counts as moved for adult (Get_StoneOfWater_IsAfter_Step06_Exp OR adult). With
  open the child's invisible wall is gone, Zora's Domain's first visit is done and Get_StoneOfWater is at Step07
  from a new file (every older step setter is skipped from then on).
- gerudo_fortress open: the four carpenters are saved and SageOfSpirit is at Step02 (the guards turn friendly
  from there). fast: three saved, and the carpenter in the one-torch cell (Npc_Hylia_016) is left. The "fight a
  thief at a saved carpenter's door" entries end at once.
- skip_reward_from_rauru free / free_forced, skip_child_zelda (OoTR gives Zelda's Letter as a starting item),
  gerudo_fortress open with the card unshuffled: OoTR gives those locations' items at the start (skipped
  locations). A new file gets them, Rauru's own give step gives a green rupee instead, and Zelda's story starts
  done (Goto_HyruleCastle Complete, DoorOfTime Step01, older step setters skipped).
- complete_mask_quest: SubEvent_MaskSalesman Complete from a new file (all masks borrowable, no payments).
- chicken_count 0 (and _random): Anju takes one cucco (OoTR's logic is the same for 0-6); big_poe_count_random.
- starting_tod: the opening scene's time (vanilla 6:00).
- no_escape_sequence: Ganondorf's defeat changes level straight to the Ganon arena with its arrival scene, like
  the escape's exit does. no_guard_stealth: the courtyard guards aren't placed (child-only level).
- fast_shadow_boat: the boat's rail speed x3. damage_multiplier (not on yet): the player's damage rates.
- scarecrow_behavior fast: with the scarecrow song set as child and adult, taking out the ocarina at a Pierre
  spot calls him.
- useful_cutscenes, logic_no_night_tokens_without_suns_song: accepted with no game change. The remake plays all
  cutscenes, and the last one is logic only. fast_chests is parity/_gaps_chests.py (big chests open quickly).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
import world_settings  # noqa: E402
from parity import _story_conditions as C  # noqa: E402

REMAKE_KEYS = ("remake_shuffle_master_sword",)  # remake settings this plugin reads (generate.unknown_remake_settings)

DATA = json.load(open(os.path.join(HERE, "data", "rando", "story_data.json"), encoding="utf-8"))

TOD = {"sunrise": (6, 30), "morning": (9, 0), "noon": (12, 0), "afternoon": (15, 0), "sunset": (18, 0),
       "evening": (21, 0), "midnight": (0, 0), "witching-hour": (3, 0)}  # OoTR's Patches.py times
DAMAGE = {"half": 0.5, "normal": 1.0, "double": 2.0, "quadruple": 4.0, "ohko": 100.0}

OWNS = {
    "bridge": ("open", "vanilla", "stones", "medallions", "dungeons", "tokens", "hearts", "random"),
    "bridge_medallions": None, "bridge_stones": None, "bridge_rewards": None, "bridge_tokens": None,
    "bridge_hearts": None,
    "lacs_condition": ("vanilla", "stones", "medallions", "dungeons", "tokens", "hearts"),
    "lacs_medallions": None, "lacs_stones": None, "lacs_rewards": None, "lacs_tokens": None, "lacs_hearts": None,
    "open_forest": ("open", "fast", "closed_deku", "closed"),
    "open_door_of_time": ("open", "sot", "oot_sot", "stones", "stones_sot", "stones_oot_sot"),
    "zora_fountain": ("closed", "fast", "adult", "open"),  # fast: _gaps_story.py
    "gerudo_fortress": ("normal", "fast", "open"),
    "skip_reward_from_rauru": ("not_free", "free", "free_forced"),
    "complete_mask_quest": (False, True),
    "chicken_count": tuple(range(8)), "chicken_count_random": (False, True),
    "big_poe_count_random": (False, True),
    "starting_tod": ("default", "random") + tuple(TOD),
    "no_escape_sequence": (False, True),
    "no_guard_stealth": (False, True),
    "fast_shadow_boat": (False, True),
    "damage_multiplier": tuple(DAMAGE),  # player DamageRates scaled in 3 packs
    "scarecrow_behavior": ("vanilla", "fast", "free"),
    "useful_cutscenes": (False, True),
    "logic_no_night_tokens_without_suns_song": (False, True),
    # OoTR draws the count per world (world.settings.trials), and world_settings.world_plan applies that world's
    # count and skipped trials (barrier flags) the same as for a fixed count
    "trials_random": (False, True),
    # night-only Gold Skulltulas stay at day; the Spirit Temple pot drops its Deku Shield (parity/_gaps_drops.py)
    "gold_skulls_ignore_daytime": (False, True),
    "fix_broken_drops": (False, True),
    # TODO: not possible or not done yet with data edits
    "triforce_hunt": (False,), "triforce_count_per_world": None, "triforce_goal_per_world": None,
    "no_epona_race": (False,),
    "skip_some_minigame_phases": (False,),
    "fast_bunny_hood": (False,),
    "auto_equip_masks": (False,),
    "easier_fire_arrow_entry": (False,), "fae_torch_count": None,
    "ruto_already_f1_jabu": (False,),
    "deadly_bonks": ("none",),
    "blue_fire_arrows": (False,),
}

# The gap settings live in self-contained modules next to this one.
# Each one may define OWNS (merged over the table above), UNTESTED(settings) -> [str], world_plan(settings, world)
# -> plan sections, and READERS {"_gaps" key: function name} for its read-back (parity/_gaps_check.py). Missing
# modules are skipped.
GAPS_MODULES = ("_gaps_story", "_gaps_drops", "_gaps_fire", "_gaps_minigames", "_gaps_player", "_gaps_triforce",
                "_gaps_password", "_gaps_chests",
                # dev test builds only (a plan settings file's "test_start" section). The new file picks a test
                # and starts at its spot with what it needs.
                "_test_start",
                # every seed: game-state traps OotrR's players hit (quests moving back, the clock, Great Fairies...).
                # Its hooks(p, settings, world) adds pre-hooks to this plugin's Plan.
                "_story_traps",
                # remake_shuffle_master_sword: the swordless adult's return at the pedestal, and time travel never
                # stores or hands over a Master Sword you don't own (OotrR finding C3)
                "_story_master_sword")


def gaps_modules():
    import importlib
    out = []
    for name in GAPS_MODULES:
        try:
            out.append(importlib.import_module(f"parity.{name}"))
        except ModuleNotFoundError as e:
            if e.name != f"parity.{name}":
                raise
    return out


PARITY_NOTE = {}  # what a setting's PARITY.md row adds (tools/rando/parity_report.py), from the gaps modules
for _m in gaps_modules():
    OWNS.update(getattr(_m, "OWNS", {}))
    PARITY_NOTE.update(getattr(_m, "PARITY_NOTE", {}))


def resolve_settings(settings):
    """generate.prepare's hook before OoTR resolves the settings. It runs each gaps module's own hook (e.g. in
    _gaps_player the RNG salt leaves auto_equip_masks out)."""
    for m in gaps_modules():
        if hasattr(m, "resolve_settings"):
            m.resolve_settings(settings)

# The damage-rate edit needs integer keys in pack "set" paths.
PACK_INT_KEYS = True  # make_patch supports them through _key

SKIPPED_REPLACEMENT = "TBox_Rupee_Green"  # what Rauru gives when OoTR hands his item out at the start

# Same-size 32-bit edits of level logic modules (uncompressed Logic/*.ainb, and make_patch "binary" checks the old
# value first). Offsets are AINB input/multi-input entries (src node i16, src output i16) and their flags.
# Unconnected inputs read (-1, 0) with flags 0x1800000.
UNCONNECTED, UNCONNECTED_FLAGS = 0xFFFF, 0x1800000
AINB = {
    # OoTR "Can always return to youth". The adult pedestal (Market_Adult_Prefab_89da) deletes its attention while
    # SageOfForest_IsCompleted_Exp is false (vanilla OoT's Forest Medallion rule), so its Logic_Delete becomes
    # unconnected.
    "return_to_youth": [("Logic/Market_Adult_Prefab_89da.logic.module.ainb", 0x4E4, UNCONNECTED, 1),
                        ("Logic/Market_Adult_Prefab_89da.logic.module.ainb", 0x4E8, UNCONNECTED_FLAGS, 0)],
    # The Door of Time (Market_Common_f252, both eras): isOpen = OR(the altar proxy's momentary EventBool,
    # DoorOfTime >= Step06). Its unused Market_Child_TimeTempleDoor_Opened node replaces the EventBool input.
    # A node only computes the outputs flagged "Is Output" (bit 31 of the output entry, OotrR saw an unflagged one
    # read false in game), and a node evaluates the query nodes of its query list. So node 6's Bool output is
    # flagged, and the OR's query list and plug name node 6 instead of 4 (like every vanilla link does).
    "door_flag": [("Logic/Market_Common_f252.logic.module.ainb", 0x1898, 6, 0x10004),
                  ("Logic/Market_Common_f252.logic.module.ainb", 0x1770, 0x8000039D, 0x39D),
                  ("Logic/Market_Common_f252.logic.module.ainb", 0x18FC, 6, 4),
                  ("Logic/Market_Common_f252.logic.module.ainb", 0x938, 6, 4)],
    # The first pull (Market_Child_Prefab_e700 -> Market_Child_DoorOfTime_Draw). DoorOfTime == Step06 becomes
    # DoorOfTime before Step06, since the pedestal is behind the door and after the first trip DoorOfTime is
    # Complete. Node 2's IsBefore output gets flagged "Is Output" (only IsEqual was), and its query list and plug
    # already name node 2.
    "pedestal_first_trip": [("Logic/Market_Child_Prefab_e700.logic.module.ainb", 0x8FC, 0x10002, 0x20002),
                            ("Logic/Market_Child_Prefab_e700.logic.module.ainb", 0x87C, 0x80000195, 0x195)],
    # Sheik in the Crater (DeathMountainCrater_Adult_Prefab_e63c). The Bolero area also needed SageOfFire before
    # EnterTemple, which is gone once the Fire Temple is entered, and its end set EnterTemple, which would move a
    # later stage back. So the area only needs Bolero unplayed, and the step setter is unconnected.
    "bolero_any_time": [("Logic/DeathMountainCrater_Adult_Prefab_e63c.logic.module.ainb", 0xA54, 7, 0x10006),
                        ("Logic/DeathMountainCrater_Adult_Prefab_e63c.logic.module.ainb", 0x958, UNCONNECTED, 0x40000),
                        ("Logic/DeathMountainCrater_Adult_Prefab_e63c.logic.module.ainb", 0x95C, UNCONNECTED_FLAGS, 0)],
    # Sheik at the Colossus (DesertColossus_Common_665d). The end of the Requiem scene set SageOfSpirit Step05 at
    # any step, and the jail carpenters can only be freed at Step01, so finding Requiem early lost you the card. The
    # setter is unconnected, and the scenes set Step05 themselves once the carpenters are free (gate_fixes).
    "requiem_step": [("Logic/DesertColossus_Common_665d.logic.module.ainb", 0x878, UNCONNECTED, 0x40001),
                     ("Logic/DesertColossus_Common_665d.logic.module.ainb", 0x87C, UNCONNECTED_FLAGS, 0)],
}
# Zora's Domain (adult): King Zora's red ice is only placed while SageOfWater isn't complete, so the Blue Fire
# thaw (the Zora Tunic) was lost once the Water Temple was beaten. Now it stays until the thaw scene has played.
KING_ZORA_ICE = (("Banc/ZoraDomain/ZoraDomain_Adult_Static.bcett.byml.zs", "5554999686001029434"),
                 ("Banc/ZoraDomain/ZoraDomain_Adult_Alternative_Static.bcett.byml.zs", "3341274640047764997"))
BIG_GORON_WAIT = ("Event82", "Event71", "Event115", "Event116")  # Claim Check: ElapsedHour 72 -> 0 (OoTR: no wait)
MASTER_SWORD_LOCATIONS = ("event/DoorOfTime/Weapon_Sword_Master", "event/Dm_TimeTemple_0030/Weapon_Sword_Master")
MS_LOCATION = "ToT Master Sword"
MS_ITEM = "Master Sword"
ADULT_SWORDS = ("Master_Sword", "Biggoron_Sword")


def check_settings(settings):
    out = []
    if shuffle_master_sword(settings) and getattr(settings, "starting_age", "child") != "child":
        out.append("remake_shuffle_master_sword with an adult (or random) start: the logic gives time travel only "
                   "with an adult sword, and an adult start would begin without one")
    if settings.open_forest == "fast" and getattr(settings, "shuffle_dungeon_entrances", "off") != "off":
        out.append("open_forest = 'fast' with shuffled dungeon entrances: OoTR then lets adult into the Deku "
                   "Tree once the items are found; the remake's Deku Tree mouth opens only in the child's "
                   "first meeting")
    starting = getattr(settings, "starting_items", None) or {}
    if "Zeldas Letter" in starting and set(getattr(settings, "shuffle_child_trade", None) or ()) & {
            "Weird Egg", "Chicken"}:
        out.append("Zelda's Letter as a starting item (skip child Zelda) with a shuffled Weird Egg or Chicken: "
                   "Malon's egg is given in the castle story the skip completes")
    return out


def untested(settings):
    s = settings
    out = []
    vanilla = {"bridge": "vanilla", "lacs_condition": "vanilla", "open_forest": None, "zora_fountain": "closed",
               "gerudo_fortress": "normal", "skip_reward_from_rauru": "not_free", "complete_mask_quest": False,
               "chicken_count_random": False, "big_poe_count_random": False, "starting_tod": "default",
               "no_escape_sequence": False, "no_guard_stealth": False, "fast_shadow_boat": False,
               "damage_multiplier": "normal"}
    for name, v in vanilla.items():
        if v is not None and getattr(s, name, v) != v:
            out.append(f"{name} = {getattr(s, name)!r}")
    if s.open_forest == "fast":
        out.append("open_forest = 'fast'")
    if s.open_door_of_time in ("sot", "oot_sot", "stones", "stones_sot"):
        out.append(f"open_door_of_time = {s.open_door_of_time!r}")
    if s.scarecrow_behavior == "fast":
        out.append("scarecrow_behavior = 'fast'")
    if s.chicken_count == 0:
        out.append("chicken_count = 0 (Anju takes one)")
    if "Zeldas Letter" in (getattr(s, "starting_items", None) or {}):
        out.append("skip child Zelda (Zelda's Letter at start)")
    if s.open_door_of_time != "stones_oot_sot":
        out.append("Door of Time / first pull decoupled from the moat scene (level-logic edits)")
    if shuffle_master_sword(s):
        out.append("remake_shuffle_master_sword (pedestal item, swordless adult)")
    for name in ("gold_skulls_ignore_daytime", "fix_broken_drops", "trials_random"):  # gap settings
        if getattr(s, name, False):
            out.append(f"{name} = True")
    for m in gaps_modules():
        if hasattr(m, "UNTESTED"):
            out += m.UNTESTED(s)
    out.append("story gate fixes: return to child at any time, Bolero after the Fire Temple, Requiem/carpenter "
               "order, King Zora's ice, Bombchu Bowling, Biggoron's wait, castle and Light Arrow step guards")
    return out


# OoTR hooks
def skipped_locations(world):
    """OoTR locations whose item a new file starts with (Plandomizer.configure_effective_starting_items)."""
    ws = world.settings
    out = []
    if ws.skip_reward_from_rauru in ("free", "free_forced"):
        out.append("ToT Reward from Rauru")
    if world.skip_child_zelda:
        out += ["HC Zeldas Letter", "Song from Impa"]
    if ws.gerudo_fortress == "open" and not ws.shuffle_gerudo_card:
        out.append("Hideout Gerudo Membership Card")
    return out


def _startable(name):
    try:
        return world_settings.starting_actor(name, 1) is not None
    except Exception:  # noqa: BLE001 - an item the remake has no start routine for
        return False


def before_fill(world, settings):
    """Items at skipped locations are given at the start by a pouch add, so only items that have one. No hearts, since
    max life comes from the game-start sequence and isn't a pouch item. The shuffled Master Sword joins the pool."""
    if shuffle_master_sword(settings):
        _master_sword_before_fill(world, settings)
    for name in skipped_locations(world):
        loc = world.get_location(name)
        if loc.item is not None or loc.locked:
            continue
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: prev(location, item) and item.name not in
                         world_settings.HEART_ITEMS and (_startable(item.name) or not (item.advancement or
                                                                                       item.priority)))


def item_for(item, location, world):
    if item == MS_ITEM:
        return "Weapon_Sword_Master"  # the vanilla pouch actor (DoorOfTime:Event115 adds it the same way)
    if location == "ToT Reward from Rauru" and world.settings.skip_reward_from_rauru in ("free", "free_forced"):
        return SKIPPED_REPLACEMENT  # the item itself is given at the start; Rauru's scene still plays
    return None


# Master Sword shuffle (remake setting)
def shuffle_master_sword(settings):
    """remake_shuffle_master_sword (off by default; modelled on Ship of Harkinian's Master Sword Shuffle)."""
    return bool((getattr(settings, "remake", None) or {}).get("remake_shuffle_master_sword", False))


def register_master_sword():
    """Adds the Master Sword as an OoTR item (Master_Sword in rules) and the pedestal as a location without editing
    vendor/ootr. They go into the same tables OoTR builds from ItemList / LocationList / HintList at import."""
    import HintList
    import Item
    import ItemList
    import LocationList
    if MS_ITEM not in ItemList.item_table:
        ItemList.item_table[MS_ITEM] = ("Item", True, None, None)
    if MS_ITEM not in Item.ItemInfo.items:
        Item.ItemInfo.items[MS_ITEM] = Item.ItemInfo(MS_ITEM)
    import Language
    texts = {MS_ITEM: (["a sacred blade", "the blade of evil's bane"], "the Master Sword", "item"),
             MS_LOCATION: ("the #Master Sword's pedestal# holds", None, "exclude")}
    for name, row in texts.items():
        HintList.hintTable.setdefault(name, row)
    if not getattr(Language.Language.__init__, "remake_master_sword", False):
        original = Language.Language.__init__

        def init(self, lang, _original=original):  # every language's hint texts (World makes one per world)
            _original(self, lang)
            for name, (vague, clear, _) in texts.items():
                self.hintTable.setdefault(name, {"vague_hint": vague, "clear_hint": clear, "gender": "no_gender"})
        init.remake_master_sword = True
        Language.Language.__init__ = init
    if MS_LOCATION not in LocationList.location_table:
        tags = ("Temple of Time", "Market", "NPCs")
        LocationList.location_table[MS_LOCATION] = ("NPC", None, None, None, MS_ITEM, tags)
        for group in ("NPC",) + tags:
            if group in LocationList.location_groups:
                LocationList.location_groups[group].append(MS_LOCATION)


def before_build(settings):
    if shuffle_master_sword(settings):
        register_master_sword()


def keep_locations(world, settings):
    """With the Master Sword shuffled, the pedestal ("ToT Master Sword", Beyond Door of Time, rule True) holds any
    item, given in the first trip's scenes where the sword was. Time travel still comes from pulling it (OoTR's
    "Master Sword Pedestal" event). Logic wants an adult sword (Master or Biggoron) for it, so every adult region
    OoTR reaches has the sword its adult rules assume (is_adult stands for "has a sword" in ~340 rules)."""
    if not shuffle_master_sword(settings):
        return set()
    from Location import LocationFactory
    region = world.get_region("Beyond Door of Time")
    if not any(loc.name == MS_LOCATION for loc in region.locations):
        loc = LocationFactory(MS_LOCATION)
        loc.parent_region = region
        loc.world = world
        loc.rule_string = "True"
        world.parser.parse_spot_rule(loc)
        region.locations.append(loc)
        if world._cached_locations:
            world._cached_locations.append(loc)
    pedestal = world.get_location("Master Sword Pedestal")
    pedestal.rule_string = " or ".join(ADULT_SWORDS)
    world.parser.parse_spot_rule(pedestal)
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "CALL_LOCATIONS"):  # a dungeon item on the pedestal has its give steps call the
        dg.CALL_LOCATIONS.add(MS_LOCATION)  # item's credit entry (dungeons.item_for, through master_sword_plan)
    return {MS_LOCATION}


def _master_sword_before_fill(world, settings):
    """The sword joins the item pool, for the one new location (the pedestal). It goes anywhere a give path can hand
    it over, like any other item, and each plugin's own item rule refuses it where its give can't.
    Every path gives the pouch actor Weapon_Sword_Master (item_for, songs_trade.ITEM_FIX, shops.scrub_actor), which
    Link can't hold up as it is. config/hold_up.json "show" gives it its display's hold-up (Rando_Show_MasterSword,
    progressive.hold_node) in chests, get scenes, scrub sales and the carpet salesman's sale copy alike. The pouch
    add sets IsGet.Weapon_Sword_Master, which the shuffle's pedestal and time-travel guards read
    (_story_master_sword)."""
    from Item import ItemFactory
    pool = world.itempool
    if not any(it.name == MS_ITEM for it in pool):
        pool.append(ItemFactory(MS_ITEM, world))


def master_sword_plan(p, world):
    """The pedestal's item replaces the sword in the first trip (Dm_TimeTemple_0030's display, DoorOfTime:Event115's
    pouch add). The first trip only equips the Master Sword for adult if it's in the pouch."""
    import generate
    item = world.get_location(MS_LOCATION).item
    target = generate.plugin_item(generate.plugins(), item.name, MS_LOCATION, world)
    spec = dict(target) if isinstance(target, dict) else {"item": target}
    for rid in MASTER_SWORD_LOCATIONS:
        p.rewards[rid] = dict(spec, note=f"{MS_LOCATION}: {item.name}")
    p.pre_hook("ReplaceEquipmentForEraChange", "Event5", {
        "m": {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
              "params": {"Actor": "Weapon_Sword_Master", "Num": 1}, "cases": {0: "NEXT", 1: "@Event13"}}}, "m")


# Plan building
def _step(file, event):
    """Routing facts of a step the plugin hooks: {"next", "preds", "flowchart"}."""
    h = DATA["hooks"].get(file)
    if h and event in h["steps"]:
        return dict(h["steps"][event], flowchart=h["flowchart"])
    for infos in list(DATA["guards"].values()) + list(DATA.get("requests", {}).values()):
        for g in infos:
            if g["file"] == file and g["event"] == event:
                return g
    raise KeyError(f"{file}:{event} is not in data/rando/story_data.json (run _story_build.py)")


class Plan:
    def __init__(self):
        self.events, self.defaults, self.boolexp = [], {}, {}
        self.placements, self.packs, self.start = [], [], []
        self.binary, self.rewards = [], {}
        self.opening = []  # scene calls the new-file opening makes first (gaps modules' opening(), e.g. the password)
        self.pre = {}  # (file, event) -> [(nodes, start)] run in order before the step

    def pre_hook(self, file, event, nodes, start):
        """New steps in front of `event`, so every step or entry leading to it goes to them first. A target is a
        label, "@Event" (an existing step), None (end) or "NEXT" (the next hook, or the step itself)."""
        self.pre.setdefault((file, event), []).append((nodes, start))

    def guard(self, file, event, exp):
        """Skip `event` (go on to its next step) while the expression `exp` holds."""
        info = _step(file, event)
        after = f"@{info['next']}" if info["next"] else None
        self.pre_hook(file, event, {"g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                                          "params": {"GameDataName": exp}, "cases": {0: after, 1: "NEXT"}}}, "g")

    def skip_unless(self, file, event, exp, query="EventQueryIsGameDataBoolExp"):
        """Skip `event` (go on to its next step) unless `exp` holds (a BoolExp, or a Bool with that query)."""
        info = _step(file, event)
        after = f"@{info['next']}" if info["next"] else None
        params = {"GameDataName": exp} if query.endswith("BoolExp") else {"GameDataName": exp, "Index": -1}
        self.pre_hook(file, event, {"g": {"actor": "GameDataActor", "query": query, "params": params,
                                          "cases": {0: "NEXT", 1: after}}}, "g")

    def assemble(self):
        built, made = {}, []  # (file, flowchart, step) -> its graph's first step, and the graphs made
        for (file, event), frags in self.pre.items():
            info = _step(file, event)
            graph = f"Rando_Story_{event}"
            # where each fragment starts, "NEXT" passed on to the following fragment (or the step itself)
            starts = [None] * (len(frags) + 1)
            starts[len(frags)] = f"@{event}"
            for i in range(len(frags) - 1, -1, -1):
                frag, start = frags[i]
                starts[i] = starts[i + 1] if start == "NEXT" else (f"h{i}_{start}" if start in frag else start)
            nodes = {}
            for i, (frag, _) in enumerate(frags):
                def fix(t, frag=frag, i=i):
                    if t == "NEXT":
                        return starts[i + 1]
                    return f"h{i}_{t}" if t in frag else t
                for lab, n in frag.items():
                    n = dict(n)
                    if "next" in n:
                        n["next"] = fix(n["next"])
                    if "cases" in n:
                        n["cases"] = {k: fix(v) for k, v in n["cases"].items()}
                    nodes[f"h{i}_{lab}"] = n
            first = starts[0]
            if first is None or first.startswith("@") or not nodes:
                continue
            self.events.append({"file": file, "flowchart": info["flowchart"], "add_graph": graph,
                                "nodes": nodes, "start": first})
            built[(file, info["flowchart"], event)] = f"{graph}_{first}"
            made.append((file, info["flowchart"], event, graph, nodes))
            for kind, where, k in info["preds"]:
                op = {"file": file, "flowchart": info["flowchart"], "next": f"{graph}_{first}"}
                if kind == "entry":
                    op["entry"] = where
                else:
                    op["event"] = where
                    if kind in ("case", "fork"):
                        op[kind] = k
                self.events.append(op)
        # A link to another hooked step in the same flowchart must run that step's hooks too. For example,
        # a guard that skips its request can land on the next request, which has its own guard.
        for file, flowchart, event, graph, nodes in made:
            for lab, n in nodes.items():
                links = ([(None, n["next"])] if "next" in n else []) + list(enumerate((n.get("cases") or {}).values()))
                for case, t in links:
                    if isinstance(t, str) and t.startswith("@") and t[1:] != event and \
                            (file, flowchart, t[1:]) in built:
                        op = {"file": file, "flowchart": flowchart, "event": f"{graph}_{lab}",
                              "next": built[(file, flowchart, t[1:])]}
                        if case is not None:
                            op["case"] = case
                        self.events.append(op)

    def to_plan(self):
        self.assemble()
        if self.start or self.opening:  # the new-file opening scene: the opening calls, then the start steps
            frags = [({"o": {"call": c, "next": "NEXT"}}, "o") for c in self.opening]
            if self.start:  # one entry next to the story-step actors
                self.events.append({"file": "DoorOfTime", "flowchart": "DoorOfTime", "add_entry": "Rando_StoryStart",
                                    "steps": self.start})
                frags.append(({"c": {"call": "DoorOfTime:Rando_StoryStart", "next": "NEXT"}}, "c"))
            self.pre = {("OpeningEvent", "Event11"): frags}
            self.assemble()
        plan = {}
        gd = {}
        if self.defaults:
            gd["defaults"] = self.defaults
        if self.boolexp:
            gd["boolexp"] = self.boolexp
        if gd:
            plan["gamedata"] = gd
        if self.events:
            plan["events"] = self.events
        if self.placements:
            plan["placements"] = self.placements
        if self.packs:
            plan["packs"] = self.packs
        if self.binary:
            plan["binary"] = self.binary
        if self.rewards:
            plan["rewards"] = self.rewards
        return plan


def progress(challenge, step):
    return {"actor": "ChallengeSystemActor", "action": "EventExecuteProgressChallengeStep",
            "params": {"ChallengeName": challenge, "StepName": step, "IsWaitEnd": True,
                       "IsIgnoreCompletedChallenge": True, "IsIgnoreChallengeProgressUI": True}}


def set_bool(flag, value=True):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
            "params": {"GameDataName": flag, "Index": -1, "Value": value}}


def guard_challenge(p, challenge):
    exp = world_settings_guard_exp(challenge)
    for g in DATA["guards"].get(challenge, []):
        if g["has_gamedata"]:
            p.guard(g["file"], g["event"], exp)


def world_settings_guard_exp(challenge):
    return {"Goto_HyruleCastle": "Goto_HyruleCastle_IsCompleted_Exp", "DoorOfTime": "DoorOfTime_IsAfter_Step01_Exp",
            "SubEvent_MaskSalesman": "SubEvent_MaskSalesman_IsCompleted_Exp",
            "SageOfSpirit": "SageOfSpirit_IsAfter_Step01_Exp",
            "Get_StoneOfWater": "Get_StoneOfWater_IsAfter_Step06_Exp"}[challenge]


def _end_now(p, file, event):
    """The step's entry/predecessors end at once (a 1-frame wait, then the end)."""
    p.pre_hook(file, event, {"w": {"actor": "EventSystemActor", "action": "EventWait",
                                   "params": {"IsWaitEnd": True, "Frames": 1}, "next": None}}, "w")


def _s32(v):
    """make_patch's binary op reads and writes signed 32-bit numbers (a flagged output word has bit 31 set)."""
    return v - (1 << 32) if v >= 1 << 31 else v


def binary(p, key):
    for file, off, new, old in AINB[key]:
        p.binary.append({"file": file, "offset": off, "i32": _s32(new), "expect": _s32(old), "note": key})


def gate_fixes(p, ws):
    """Story gates that are stricter in the remake than OoTR's logic, fixed for every seed."""
    # time travel back to child at any time (OoTR patches the same rule out of the N64 game)
    binary(p, "return_to_youth")
    # Sheik in the Crater teaches his song to any adult who has not heard it, also after the Fire Temple
    binary(p, "bolero_any_time")
    # the Deku Tree's exit scene sets Goto_HyruleCastle to Step01, and IsIgnoreCompletedChallenge only skips that
    # once it's Complete. After waking Talon (Step04) it would undo the castle story for good, because Zelda needs
    # exactly Step04 and Malon and Talon at the ranch need it past Step03_02.
    p.guard("Dm_SY_BancChange_EscapeDungeon", "Event4", "Goto_HyruleCastle_IsAfter_Ready_Exp")
    # the vanilla Light Arrow cutscene needs AllSage == Step02 (Spirit and Shadow sages), so the Forest Temple's
    # exit (AllSage Step01_00) and the Prelude scene (rollback to Step01_01) can't move it back when they're done late
    p.guard("Dm_SY_BancChange_EscapeDungeon", "Event208", "AllSage_IsAfter_Step01_Exp")
    p.guard("AllSage", "Event34", "AllSage_IsAfter_Step01_01_Exp")
    # Gerudo: the gatekeeper's first talk sets SageOfSpirit Step02, which would undo Step04/Step05 (the Colossus
    # arrival, Requiem). The first Colossus arrival from the wasteland sets Step04, so only after the carpenters,
    # because the jail carpenters can only be freed at Step01.
    p.guard("Npc_Gerudo_006", "Event61", "SageOfSpirit_IsAfter_Step02_Exp")
    p.guard("Dm_SY_BancChangeArrive", "Event76", "SageOfSpirit_IsAfter_Step04_Exp")
    p.skip_unless("Dm_SY_BancChangeArrive", "Event76", "SageOfSpirit_IsAfter_Step01_Exp")
    # Requiem: Step05 once the carpenters are free, at the end of Sheik's scene or, if he taught it first, with
    # the 4th carpenter's card scene (its own Step02)
    binary(p, "requiem_step")
    p.events.append({"file": "AllSage", "flowchart": "AllSage", "add_graph": "Rando_Story_RequiemStep",
                     "nodes": {"p": dict(progress("SageOfSpirit", "Step05"), next=None)}, "start": "p"})
    p.pre_hook("Dm_MelodyGet_Spilit", "Event282", {
        "free": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                 "params": {"GameDataName": "SageOfSpirit_IsAfter_Step01_Exp"}, "cases": {0: "late", 1: "NEXT"}},
        "late": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                 "params": {"GameDataName": "SageOfSpirit_IsAfter_Step04_Exp"}, "cases": {0: "NEXT", 1: "set"}},
        "set": {"call": "AllSage:Rando_Story_RequiemStep", "next": "NEXT"}}, "free")
    p.pre_hook("SageOfSpirit", "Event292", {
        "heard": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                  "params": {"GameDataName": "HavePlayedEvent.Dm_MelodyGet_Spilit", "Index": -1},
                  "cases": {0: "late", 1: "NEXT"}},
        "late": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                 "params": {"GameDataName": "SageOfSpirit_IsAfter_Step04_Exp"}, "cases": {0: "NEXT", 1: "set"}},
        "set": dict(progress("SageOfSpirit", "Step05"), next="NEXT")}, "heard")
    # Bombchu Bowling opens as soon as you talk (OoTR's is_child). The remake waits for King Dodongo.
    info = _step("MiniGame_BombchuBowling", "Event137")
    p.events.append({"file": "MiniGame_BombchuBowling", "flowchart": info["flowchart"], "event": "Event137",
                     "case": 1, "next": "Event297"})
    # Biggoron takes the Claim Check at once (OoTR removes the 3-day wait)
    for ev in BIG_GORON_WAIT:
        p.events.append({"file": "Npc_Goron_Biggoron_Adult", "flowchart": "Npc_Goron_Biggoron_Adult", "event": ev,
                         "param": "ElapsedHour", "value": 0})
    # returning to child for the first time equips the Kokiri Sword even when it was never found
    p.pre_hook("ReplaceEquipmentForEraChange", "Event11", {
        "k": {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
              "params": {"Actor": "Weapon_Sword_Kokiri", "Num": 1}, "cases": {0: "NEXT", 1: "@Event13"}}}, "k")
    # King Zora's ice stays until the thaw scene has played (it vanished with the Water Temple)
    for file, h in KING_ZORA_ICE:
        p.placements.append({"file": file, "hash": h,
                             "set": {"Presence.FlagName": "HavePlayedEvent.SageOfWater_KingZora_IsMelted_Ice"}})


def door_of_time(p, value):
    """Vanilla (stones_oot_sot) keeps the game's chain: stones -> moat scene (Step03/04) -> Song of Time lesson
    (Step05) -> the door's Song of Time scene (Step06) -> the first pull (needs exactly Step06) -> Complete.
    Every other value opens the door out of that order, and the same challenge also drives the moat scene, so the
    door and the first pull stop reading it. The door opens on Market_Child_TimeTempleDoor_Opened, which the door
    scene sets (at the start for 'open', on the third stone stage for 'stones'). The first pull works at any step
    before Step06, and the door scene doesn't set Step06 (the moat scene keeps Step03/Step04/Step05)."""
    if value == "stones_oot_sot":
        return
    binary(p, "door_flag")
    binary(p, "pedestal_first_trip")
    _end_now(p, "DoorOfTime", "Event57")  # the door scene's last step: DoorOfTime -> Step06
    # after the first trip both pedestal requests may fire (the first-pull one, if the moat scene moved DoorOfTime
    # back below Step06, and the usual one), so the second run of the child-to-adult scene does nothing
    p.pre_hook("Market_Child_Field_ChildToAdult", "Event9", {
        "c": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
              "params": {"GameDataName": "Sequence_IsChildhood", "Index": -1}, "cases": {0: "NEXT", 1: None}}}, "c")
    if value in ("sot", "oot_sot", "stones_sot"):
        # DoorOfTime_OpenDoor: after the Song of Time (Event92), Event60 waits for Step04 (the moat cutscene)
        if value == "sot":
            frag, start = {"go": {"actor": "EventSystemActor", "action": "EventWait",
                                  "params": {"IsWaitEnd": True, "Frames": 1}, "next": "@Event69"}}, "go"
        elif value == "oot_sot":
            frag, start = {"oot": {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                                   "params": {"Actor": "Item_Ocarina_Time", "Num": 1},
                                   "cases": {0: "@Event69", 1: None}}}, "oot"
        else:
            frag, start = C.scene_nodes(("flags", list(C.STONE_STAGES), 3), "s", "@Event69", None)
        p.pre_hook("DoorOfTime", "Event60", frag, start)
    elif value == "stones":
        # the door's opened flag once all three stone stages are complete, checked after the Fire and Water
        # stones (DoorOfTime_CheckStoneNum) and the Forest stone
        nodes, start = C.scene_nodes(("flags", list(C.STONE_STAGES), 3), "s", "open", "NEXT")
        nodes["open"] = dict(set_bool("Market_Child_TimeTempleDoor_Opened"), next="NEXT")
        p.pre_hook("DoorOfTime", "Event38", nodes, start)
        p.pre_hook("Dm_SY_BancChange_EscapeDungeon", "Event4", dict(nodes), start)


# OoTR's vanilla bridge is Shadow_Medallion and Spirit_Medallion and Light_Arrows. The remake's comes after the
# Light Arrow cutscene (Defeat_Ganon past Ready), whose vanilla trigger is the Spirit and Shadow sages (the
# medallions follow the boss defeats, world_settings' rewrite). In a randomizer that cutscene gives any item, so we
# check for the Light Arrows in the pouch too (logic: 'Remake Light Arrow Cutscene' and Light_Arrows,
# data/rando/logic/story.json).
VANILLA_BRIDGE = C.enum_after("Step_Defeat_Ganon", "Ready") + [[C.BOOL, "IsGet.Item_Arrow_Light"], [C.AND]]


def bridge(p, ws):
    """The castle-edge level logic requests the bridge cutscene while Defeat_Ganon_IsAfter_Ready_Exp holds and
    Defeat_Ganon isn't after Step01. The expression is OoTR's condition alone. ORing in "after Ready", which the
    Light Arrow cutscene sets, made that cutscene open every bridge."""
    req = C.requirement(ws, "bridge")
    p.boolexp["Defeat_Ganon_IsAfter_Ready_Exp"] = VANILLA_BRIDGE if req is None else C.expression(req)
    # the Light Arrow cutscene sets Defeat_Ganon to Step01, but not once the bridge cutscene has set Step02
    p.pre_hook("AllSage", "Event11", {"g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                                             "params": {"GameDataName": "Defeat_Ganon_IsAfter_Step01_Exp"},
                                             "cases": {0: None, 1: "NEXT"}}}, "g")


def lacs(p, ws):
    req = C.requirement(ws, "lacs")
    if req is None:
        return
    for ev in ("Event40", "Event175"):  # both entry points of the cutscene, only once the condition holds
        nodes, start = C.scene_nodes(req, "c", "NEXT", None)
        p.pre_hook("AllSage", ev, nodes, start)
    # the altar of the Spiritual Stones (Temple of Time), read as adult, starts the cutscene if it's due
    nodes, cstart = C.scene_nodes(req, "c", "go", "NEXT")
    nodes.update({
        "adult": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                  "params": {"GameDataName": "Sequence_IsChildhood", "Index": -1}, "cases": {0: "NEXT", 1: "seen"}},
        "seen": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
                 "params": {"GameDataName": "HavePlayedEvent.Dm_TimeTemple_0130", "Index": -1},
                 "cases": {0: "NEXT", 1: "done"}},
        "done": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                 "params": {"GameDataName": "AllSage_IsCompleted_Exp"}, "cases": {0: "NEXT", 1: cstart}},
        "go": {"copy": "Event22", "params_over": {"EventName": "Market_Adult_Field_GetArrowLight"}, "next": None},
    })
    p.pre_hook("DoorOfTime", "Event172", nodes, "adult")


def dungeon_credit(name):
    """Save-data steps for a small key, boss key, map or compass a new file starts with, else None. The generic pouch
    add credits the dungeon Link stands in, and a new file stands in none, so the key would just be gone. These write
    that dungeon's own rows instead, the way 'remove' starts a file with its keys, and show nothing."""
    from parity import dungeons
    hit = dungeons.dungeon_item(name)
    if hit is None or hit[0] not in ("Small Key", "Boss Key", "Map", "Compass") or hit[1] not in dungeons.DUNGEONS \
            or hit[1] == "Thieves Hideout":
        return None
    kind, dungeon = hit
    area = dungeons.DUNGEONS[dungeon]["area"]
    if kind == "Small Key":
        return dungeons.keys.key_steps(dungeons.keys.key_rows(area), 1)
    return [{"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
             "params": {"Index": -1, "GameDataName": f"DungeonInfo.{area}.{dungeons.FLAG[kind]}", "Value": True}}]


def skipped_gives(world):
    """Pouch adds for the items at OoTR's skipped locations (after the starting items world_settings gives). A dungeon
    item there credits its own dungeon instead (dungeon_credit)."""
    have = {k: getattr(v, "count", v) for k, v in (getattr(world.settings, "starting_items", None) or {}).items()}
    for k, v in (getattr(world, "randomized_starting_items", None) or {}).items():
        have[k] = have.get(k, 0) + v
    steps, given = [], []
    for name in sorted(skipped_locations(world)):
        loc = world.get_location(name)
        item = loc.item
        if item is None or item.world.id != world.id or item.name in world_settings.HEART_ITEMS:
            continue
        if item.name == "Zeldas Letter" and name == "HC Zeldas Letter":
            continue  # OoTR's vanilla letter there: the starting letter is the same one
        credit = dungeon_credit(item.name)
        if credit is not None:
            steps += credit
            given.append(f"{name}: {item.name}")
            continue
        have[item.name] = have.get(item.name, 0) + 1
        try:
            sa = world_settings.starting_actor(item.name, have[item.name])
        except Exception:  # noqa: BLE001
            sa = None
        if sa is None:
            continue  # junk without a pouch item (before_fill keeps progress items out)
        actor, num = sa
        steps.append({"actor": "PouchSystemActor", "action": "EventTriggerAddOrRemovePouchContent",
                      "params": {"Actor": actor, "Num": num, "IsEquipDIrect": False, "IsGetEvent": False,
                                 "IsSetMessageTargetActorName": False}})
        given.append(f"{name}: {item.name}")
    return steps, given


def world_plan(settings, world):
    ws = world.settings  # OoTR's random choices (bridge, counts, time of day) are resolved per world
    p = Plan()

    gate_fixes(p, ws)
    bridge(p, ws)
    lacs(p, ws)
    door_of_time(p, ws.open_door_of_time)
    if shuffle_master_sword(settings):
        master_sword_plan(p, world)

    if ws.open_forest == "fast":  # the forest exit opens as for closed_deku; Mido still checks sword and shield
        p.defaults["KokiriForest_Npc_Kokiri_007_Child_Blocker_00"] = False

    if ws.zora_fountain == "adult":
        p.boolexp["Get_StoneOfWater_IsAfter_Step06_Exp"] = C.enum_after("Step_Get_StoneOfWater", "Step06") + [
            [C.BOOL, "Sequence_IsChildhood"], [C.NOT], [C.OR]]
    elif ws.zora_fountain == "open":
        p.defaults["HavePlayedEvent.Dm_Zora_0010"] = True   # the child's invisible wall behind King Zora
        p.defaults["HavePlayedEvent.Dm_Zora_0000"] = True   # first visit (its arrival scene sets Step03)
        p.start.append(progress("Get_StoneOfWater", "Step07"))
        guard_challenge(p, "Get_StoneOfWater")

    if ws.gerudo_fortress in ("fast", "open"):
        # OoTR's fast leaves the 1-torch jail's carpenter, Npc_Hylia_016_Adult. His cell at y 110 holds the 1-torch
        # room's single crate and pot (drop_map.json), and 013 sits in the 2-torch room at y 102.5.
        saved = ("013", "014", "015") if ws.gerudo_fortress == "fast" else ("013", "014", "015", "016")
        for c in saved:
            p.defaults[f"GerudoFortress_Saved_Npc_Hylia_{c}_Adult"] = True
            p.defaults[f"GerudoFortress_Npc_Hylia_{c}_Adult_IsCallingHelp"] = False
        p.defaults["GerudoFortress_Meet_FourCarpenter_NumOfCarpenterHelped"] = len(saved)
        p.defaults["GerudoFortress_Meet_FourCarpenter_NumOfCarpenterHelped_02"] = 4 - len(saved)
        doors = {"013": "Event119", "014": "Event113", "015": "Event116", "016": "Event204"}
        for c in saved:  # pressing a saved carpenter's cell door would call a thief fight
            _end_now(p, "SageOfSpirit_RescueCarpenter", doors[c])
        if ws.gerudo_fortress == "open":
            p.start.append(progress("SageOfSpirit", "Step02"))
            guard_challenge(p, "SageOfSpirit")

    if world.skip_child_zelda:
        # Zelda met and Impa's send-off done: DoorOfTime Step02 (Saria in the meadow needs it after Step01) and the
        # Kakariko stage it starts. Talon woken and gone, and the courtyard crates moved (OoTR's SaveContext).
        p.start += [progress("Goto_HyruleCastle", "Complete"), progress("DoorOfTime", "Step02")]
        if ws.open_kakariko != "open":  # open: the new file starts at KakarikoVillageLetter, later (_story_traps)
            p.start.append(progress("Get_StoneOfFire", "KakarikoVillageNpc"))
        guard_challenge(p, "Goto_HyruleCastle")
        guard_challenge(p, "DoorOfTime")
        for flag in ("HavePlayedEvent.Dm_HrlCastle_0020", "Talon_AfterWakeUp", "HyruleCastle_IsBoxMoveCorrectPos"):
            p.defaults[flag] = True
        if ws.open_kakariko == "zelda":  # OoTR: the gate opens once the letter is held, which it is from the start
            p.defaults["Npc_Hylia_Soldier_003_GateOpen"] = True

    if ws.complete_mask_quest:
        p.start.append(progress("SubEvent_MaskSalesman", "Complete"))
        guard_challenge(p, "SubEvent_MaskSalesman")

    gives, _ = skipped_gives(world)
    p.start += gives

    if ws.chicken_count_random or ws.chicken_count == 0:  # world_settings used the unresolved/zero count
        n = max(1, ws.chicken_count)
        p.defaults["Npc_Hylia_049_Child_HowManyCuccos"] = n
        for ev in ("Event3", "Event82"):
            p.events.append({"file": "Minigame_CatchCucco", "flowchart": "Minigame_CatchCucco", "event": ev,
                             "param": "Value", "value": n})
    if ws.big_poe_count_random:
        p.events.append({"file": "Dm_SY_InsertBottle", "flowchart": "Dm_SY_InsertBottle", "event": "Event76",
                         "param": "Value", "value": ws.big_poe_count})

    if ws.starting_tod in TOD:
        h, m = TOD[ws.starting_tod]
        p.events += [{"file": "OpeningEvent", "flowchart": "OpeningEvent", "event": "Event9", "param": k,
                      "value": v} for k, v in (("TimeHour", h), ("TimeMin", m))]

    if ws.no_escape_sequence:  # Ganondorf's defeat: the level change the escape's exit makes
        for k, v in (("NextBanc", "FinalBattleField"), ("NextStartPos", "FinalBattleField_Entrance"),
                     ("BootEventName", "InsideGanonCaslte_Dungeon_Escape"),
                     ("EventStarterName", "FinalBattleField_Entrance")):
            p.events.append({"file": "Defeat_Ganon", "flowchart": "Defeat_Ganon", "event": "Event42",
                             "param": k, "value": v})

    if ws.no_guard_stealth:  # the courtyard guards: only present for adult, who never loads the child castle
        for h in ("13791255551109006406", "13542252451411877001", "5205105443331230277", "498294987750346090",
                  "14009796738133600543"):
            p.placements.append({"file": "Banc/HyruleCastle/HyruleCastle_Static.bcett.byml.zs", "hash": h,
                                 "set": {"Presence.FlagName": "Sequence_IsChildhood", "Presence.IsCheckLazy": False,
                                         "Presence.IsNegation": True}})

    if ws.fast_shadow_boat:
        p.placements.append({"file": "Banc/ShadowTemple/ShadowTemple_Static.bcett.byml.zs",
                             "hash": "4994605815279638863", "set": {"Dynamic.Actor_RailLiftMoveSpeed": 10.5}})

    if ws.damage_multiplier != "normal" and PACK_INT_KEYS:
        f = DAMAGE[ws.damage_multiplier]
        for pack in ("Player_Base", "Player_Child", "Player_Adult"):
            p.packs.append({"pack": f"Pack/Actor/{pack}.pack.zs",
                            "file": "Life/DamageParameters/Player.game__life__DamageParameters.bgyml",
                            "set": {f"ExternalDamageParameters.DamageRates.{k}": f for k in DAMAGE_TYPES}})

    if ws.scarecrow_behavior == "fast":
        # taking out the ocarina (Dm_SY_Ocarina EntryPoint0) at a Pierre spot, with the song set as child and
        # played to Pierre as adult, plays Pierre's appear scene for that spot, like playing the song would
        cases = {0: "NEXT"}
        cases.update({v: "call" for v in range(1, 17)})
        p.pre_hook("Dm_SY_Ocarina", "Event19", {
            "song": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp",
                     "params": {"GameDataName": "SubEvent_GetScarecrow_IsCompleted_Exp"},
                     "cases": {0: "spot", 1: "NEXT"}},
            "spot": {"actor": "GameSystemActor", "query": "EventQueryCheckContactAreaCanCallPierre", "cases": cases},
            "call": {"call": ":AppearPierreEventTransition", "next": None}}, "song")

    for m in gaps_modules():  # e.g. the password lock, asked before anything else
        if hasattr(m, "opening"):
            p.opening += m.opening(settings, world)
    for m in gaps_modules():  # modules that hook story steps through this Plan (_story_traps: order guards...)
        if hasattr(m, "hooks"):
            m.hooks(p, settings, world)
    plan = p.to_plan()
    hooked = {_edge(op): op["next"] for op in plan.get("events", []) if _edge(op)}
    hooked_steps = {(op["file"], op["add_graph"][len("Rando_Story_"):]) for op in plan.get("events", [])
                    if str(op.get("add_graph", "")).startswith("Rando_Story_")}
    import generate
    for m in gaps_modules():  # the gap settings (zora_fountain fast, night Skulltulas, ...)
        if hasattr(m, "world_plan"):
            sec = m.world_plan(settings, world)
            _no_hook_clash(m.__name__, sec.get("events", []), hooked, hooked_steps)
            generate.merge_plan(plan, sec)
    return plan


def _edge(op):
    """(file, flowchart, way into a step) a routing op sets ("next" of a step, of one of its cases or forks, or of an
    entry), or None for any other op."""
    if "next" not in op or "add_graph" in op or "add_entry" in op or "param" in op:
        return None
    if "entry" in op:
        return op["file"], op.get("flowchart"), "entry", op["entry"]
    if "event" in op:
        return op["file"], op.get("flowchart"), op["event"], op.get("case"), op.get("fork")
    return None


def _no_hook_clash(module, events, hooked, hooked_steps=()):
    """A gaps module's world_plan merges after the Plan is assembled. So a reroute of an edge the Plan sends into a
    step's hooks would take that edge and orphan every guard on the step. no_epona_race's keep-complete graph did
    that, and _story_traps' order guards on Dm_MelodyGet_Epona Event82 / Npc_Hylia_Malon_Adult Event86 never ran.
    A new step of the module's own that goes straight to a hooked step ("@Event82") also skips the step's guards on
    that way in. Such a module hooks the step through the Plan instead (hooks(p, settings, world): p.guard /
    p.pre_hook), which chains every guard in front of it and sends its own steps' "@" targets through the hooks."""
    for op in events:
        e = _edge(op)
        if e in hooked and op["next"] != hooked[e]:
            raise ValueError(f"{module}: world_plan reroutes {e[0]} {e[2:]} to {op['next']}, an edge the story Plan "
                             f"sends into {hooked[e]}: hook the step through the Plan (hooks(p, settings, world)) "
                             f"so its guards chain")
        for lab, n in (op.get("nodes") or {}).items() if "add_graph" in op else ():
            for t in ([n["next"]] if "next" in n else []) + list((n.get("cases") or {}).values()):
                if isinstance(t, str) and t.startswith("@") and (op["file"], t[1:]) in hooked_steps:
                    raise ValueError(f"{module}: world_plan's {op['add_graph']}_{lab} goes straight to "
                                     f"{op['file']} {t[1:]}, which the story Plan hooks: that way in would skip its "
                                     f"guards (hook through the Plan: hooks(p, settings, world))")


# the 19 damage types in the player's DamageRates (Player_Base / _Child / _Adult, all 1.0 in vanilla)
DAMAGE_TYPES = ("85358548", "388620384", "988705286", "1305706849", "1499870550", "1804308776", "2054188199",
                "2587815097", "2872354806", "3010012571", "3237216321", "3333229237", "3429998625", "3518489183",
                "3520794636", "3531729256", "3797638382", "3810451446", "4190899072")
