"""Parity plugin for songs, ocarina melodies, trade items, cows and other special NPC rewards.

The step data is
data/rando/songs_trade_data.json (built from the game files by tools/rando/parity/_songs_trade_build.py), the cows
are in data/rando/songs_trade_cows.json and the save flags in data/rando/songs_trade_flags.json.

- Songs (shuffle_song_items song / dungeon / any). The 12 song locations are scene locations the core already
  patches (their give step). A song lesson also teaches and *adds* its own song by melody number (Dm_SY_Ocarina's
  PlayAuto adds the song of the lesson's MelodyType), so the lesson has to follow the item. A song there gets its
  own melody number in the lesson steps, with the warp-song or plain playback routine to match. Any other item
  keeps the vanilla example and follow steps and plays the tune back without learning it (Dm_SY_Ocarina:PlayAuto,
  PLAYBACK). Sheik in Crater's "IsGet Bolero" step is skipped unless Bolero is given there. Whenever Song from
  Windmill holds another item, the windmill man asks whether his lesson played instead of whether Storms is owned
  (WINDMILL_*). Songs anywhere else are given like any item (in chests item_map's Item_Melody_*, in scenes their
  give routine).
  'dungeon' needs songs on the boss heart containers, which are freestanding pickups here: refused.
- ocarina_songs frog / warp: OoTR's generated melodies are written into the score book
  (GameParameter/MelodyScoreBook), which the lessons, the player's playing and the frogs read. The patcher can only
  rewrite note values in place (typed list values, "Needs in shared code"), so each random song keeps its slot's
  vanilla note count. Before the fill, any generated song of another length is re-rolled with OoTR's own song
  generator (get_random_song, same no-sub-song rule) until it fits. frogs2 changes nothing, because the remake's
  frog game has no fixed melody (the frogs follow any note).
- Cows (shuffle_cows): 7 of OoTR's 9 cows (plus the MQ Jabu cow) exist in the remake. The LLR tower and MQ Jabu
  cows stay vanilla (milk). The remake's own Gerudo Fortress cow is the remake-only location GF Cow
  (data/rando/logic/songs_trade.json), given in Cow_GiveMilk_gerudo's adult branch. Each cow gives its item once
  (a save flag) and then milk as before. The 5 cows sharing the generic scene are told apart by an anchor that
  each cow's EventProxyRequestActor links. An ocarina replace event finds anchors through its actor's proxy, the
  same way the bean soils and Npc_Pierre do (the earlier attempts just gave milk in game).
  TODO: until that's seen working they take no item logic needs (data/rando/songs_trade_cows.json
  generic_cows_any_item). A test build with the test_start probe "cows" also gets diagnostic branches
  (songs_trade_cows.json "probe").
- LLR Talons Chickens (always shuffled by OoTR): the hand-over after the first win (Minigame_FindOutCucco Event23)
  gives the item, and later wins refill milk like vanilla.
- shuffle_frog_song_rupees: the first time each of the five songs is played to the frogs, the item for that song
  replaces the remake's count-based rupees.
- shuffle_100_skulltula_rupee: the 100-token reward is repeatable, and the item is only given on the first-time
  path.
- shuffle_loach_reward: keeping the Hyrule Loach gives the item once (save flag), then the purple rupee. 'easy'
  is applied as 'vanilla' because OoTR's fishing tweaks need code. The logic is the same.
- shuffle_gerudo_card: the card location is a core scene location. The guards, gatekeeper, Training Ground keeper
  and horseback archery follow SageOfSpirit > Step01 (set by the card scene at the last rescue), not the card. So
  with the card shuffled every OoTR use of the card also needs the carpenters freed. data/rando/logic/songs_trade.json
  redefines Gerudo_Membership_Card as a helper, the item and 'Remake Carpenters Freed'.
- shuffle_gerudo_fortress_heart_piece: the remake has no heart piece above the jail, so the location stays out of
  play for every value.
- Two-step NPC rewards the core leaves vanilla (LW target, both shooting galleries, bombchu bowling bomb bag, HBA
  1500, both Deku theater masks, Skulltula House 10 and 30) and Kak Man on Roof: OoTR always shuffles them, and
  every give step of each one gets the item (the NPC's own once-only flag stays in charge).
- GC Rolling Goron as Child and Graveyard Dampe Gravedigging Tour (always shuffled by OoTR), GC Medigoron and Kak
  Granny Buy Blue Potion (shuffle_expensive_merchants, the shops plugin owns the setting and sells the carpet
  salesman's item): _songs_trade_npcs.py. They're once-only sales on save flags, with the gates OoTR's logic
  doesn't have removed.
- adult_trade_start (any) with adult_trade_shuffle off: the core's Anju-as-adult location gives OoTR's selected
  trade item. Trade NPCs take an item when you show it to them (ShowItemReplaceEventParam), not by quest step.
  'Broken Sword' is Biggoron's broken sword trade item (Item_BrokenSword), not the broken Giant's Knife that
  config/item_map.json lists.
- shuffle_child_trade (any subset), the 8 Market Mask Shop slots (with complete_mask_quest) and shuffle_beans (the
  bean salesman sells one item once, the 10-bean pack): _songs_trade_child.py.
- LH Sun and LH Underwater Item (always shuffled by OoTR, world pickups in the remake): the shared get scenes give
  the location's item once when the Fire Arrows / Ruto's letter pickup is taken (_songs_trade_lake.py). The same
  get-scene hook gives the drops plugin's placed heart pieces and heart containers their seed items
  (drops.get_scene_pickups, tags 5 and up).
- adult_trade_shuffle (any adult_trade_start subset, with trade timers off like OoTR's disable_trade_revert):
  _songs_trade_adult.py.
- shuffle_song_items "dungeon" (OoTR's dungeon-end spots: the 8 boss Heart Containers, Sheik in Ice Cavern, Impa,
  the Bottom of the Well Lens of Truth chest, the Gerudo Training Ground maze's final chest): the boss hearts give
  their song through the get-scene hook above (needs the drops plugin) and the chests through their chest scene.
- Refused (reason in check_settings): shuffle_individual_ocarina_notes, free_bombchu_drops.
"""
import sys

from . import _songs_trade_ops as ops
from . import _songs_trade_npcs as npcs
from . import _songs_trade_child as child
from . import _songs_trade_adult as adult
from . import _songs_trade_lake as lake
from . import _show_models as show_models

DATA = ops.load("songs_trade_data.json")
COWS = ops.load("songs_trade_cows.json")
FLAGS = ops.load("songs_trade_flags.json")["assigned"]
ITEM_MAP = ops.load("../../config/item_map.json")
PROGRESSIVE = ops.progressive.PROGRESSIVE

OWNS = {  # None: checked in check_settings (lists, or values refused with a reason)
    "shuffle_song_items": None,                  # song, dungeon, any
    "ocarina_songs": None,                       # list: frog, warp, frogs2
    "shuffle_individual_ocarina_notes": None,    # False
    "shuffle_child_trade": None,                 # list: any subset (_songs_trade_child.py)
    "adult_trade_shuffle": None,                 # False / True (_songs_trade_adult.py)
    "adult_trade_start": None,                   # list: any subset
    "shuffle_cows": (False, True),
    "shuffle_gerudo_card": (False, True),
    "shuffle_frog_song_rupees": (False, True),
    "shuffle_100_skulltula_rupee": (False, True),
    "shuffle_loach_reward": ("off", "vanilla", "easy"),
    "shuffle_gerudo_fortress_heart_piece": ("remove", "vanilla", "shuffle"),
    "free_bombchu_drops": None,                  # False
}
SUPPORTED = {"shuffle_song_items": ("song", "dungeon", "any"), "shuffle_individual_ocarina_notes": (False,),
             "adult_trade_shuffle": (False, True), "free_bombchu_drops": (False,)}
REASONS = {
    "shuffle_individual_ocarina_notes": "no file-level way found to lock single ocarina buttons (the remake's "
                                        "ocarina input has no per-note setting or save flag: its ocarina manager "
                                        "reads the buttons in code, main+0x3294DF0, with a fixed button mask and "
                                        "note map, main+0x4D419FC and +0x3293E70)",
    "free_bombchu_drops": "remake bombchus take their capacity from the bomb bag (Item_Bombchu MaxNumGameData "
                          "'Bomb'), so OoTR's bombchus without a bomb bag would be useless",
}
# The Ocarina note items' look (parity/_show_models.py). Each one shows the button that plays its note, for the
# seed's Ocarina controls and the player's controller ("auto" is the one Longshot shows when the seed is made).
# It's only written into the plan (finish_plan) when the plan shows such an item, so seeds without one don't
# change.
REMAKE_SETTINGS = dict(show_models.REMAKE_SETTINGS)
REMAKE_DEFAULTS = dict(show_models.REMAKE_DEFAULTS)
SONG_LOCATIONS = list(DATA["songs"])
SONG_TYPES = DATA["song_types"]             # OoTR song -> MelodyType
SONG_ACTORS = DATA["song_actors"]
WARP_TYPES = range(6, 12)
# A song spot holding anything but a song keeps the lesson's example and follow steps (vanilla notes) and ends
# with Dm_SY_Ocarina:PlayAuto in place of the learning call. That plays the fixed tune and the success pose without
# adding a song. Turning all three lesson calls into 1-frame waits froze Sheik in Crater, whose example runs beside
# a Navi wait. That's from another remake randomizer's in-game test (WekarXD).
PLAYBACK = "PlayAuto"
# The windmill man (Npc_Hylia_009_Adult) only starts his lesson while IsGet.Item_Melody_StormSong is false (Event9,
# Event17, Event31, Event69), so Song from Windmill was lost if the Song of Storms came from somewhere else first.
# With another item there he asks whether his lesson has played instead (WekarXD batch 22, in game).
WINDMILL_LOCATION = "Song from Windmill"
WINDMILL_NPC = "Npc_Hylia_009_Adult"
WINDMILL_STORM_QUERIES = ("Event9", "Event17", "Event31", "Event69")
WINDMILL_TAUGHT = "HavePlayedEvent.Dm_MelodyGet_Storm"
# The 14 trade items share one menu button (UI/Pouch/PouchTable ItemArray Pa_ItemIcon_23), which shows the FIRST
# owned item of its Actor list. Almost every hand-in only takes the item on show, and a child sees owned adult
# items too (an adult skips the child ones). Vanilla lists the 11 adult items first (Claim Check ... Pocket Egg),
# then the Letter, the Cucco and the Weird Egg. So a child holding any adult item can never show the Cucco to
# Talon, and OoTR puts the Pocket Egg in the pool on every default seed. That loses Zelda, the Letter, the gate and
# the Door of Time. GyroMK/barajador-de-hyrule, Clawshot and Goggles of Truth all saw this in game, and GyroMK's
# reorder (child items first: egg, Cucco, Letter) was tested in game.
# The adult items follow in trade-chain order, so a later trade never hides the earlier one it needs. The Claim
# Check (no flow ever takes it) and the Pocket Egg go last. With adult_trade_shuffle off only one adult item is
# held at a time.
# TODO: the adult order is untested in game.
# This is on for every seed. The entries are the same, so the file keeps its size.
POUCH_TABLE = "UI/Pouch/PouchTable/PouchTable.game__ui__PouchTable.bgyml"
TRADE_BUTTON = "Pa_ItemIcon_23"
TRADE_ORDER = ("Item_WeirdEgg", "Item_AlarmCucco", "Item_ZeldaLetter", "Item_PocketCucco", "Item_CojiroCucco",
               "Item_OddMushroom", "Item_OddPowder", "Item_PoacherSaw", "Item_BrokenSword", "Item_Prescription",
               "Item_EyeballFrog", "Item_EyeDrop", "Item_ClaimCheck", "Item_PocketEgg")


def trade_order_op(romfs=None):
    """The byml op that reorders the trade button's list (see TRADE_ORDER); checked against the vanilla file."""
    import os
    from romtools import Romfs, byml_load
    fs = Romfs(romfs or os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(),
               os.path.join(ops.HERE, "original"))
    root = byml_load(fs.raw(POUCH_TABLE))[0]
    button = next(b for b in root["ItemArray"] if b.get("BtnName") == TRADE_BUTTON)
    by = {a["ActorShort"]: a for a in button["Actor"]}
    if sorted(by) != sorted(TRADE_ORDER) or len(button["Actor"]) != len(TRADE_ORDER):
        raise ValueError(f"{POUCH_TABLE}: {TRADE_BUTTON} no longer lists the 14 trade items")
    return {"file": POUCH_TABLE, "set": {f"ItemArray.[BtnName={TRADE_BUTTON}].Actor": [by[a] for a in TRADE_ORDER]}}
FROG_SONGS = {"ZR Frogs Zeldas Lullaby": 0, "ZR Frogs Eponas Song": 1, "ZR Frogs Sarias Song": 2,
              "ZR Frogs Suns Song": 3, "ZR Frogs Song of Time": 4}
TALON = "LLR Talons Chickens"
LOACH = "LH Loach Fishing"
GS100 = "Kak 100 Gold Skulltula Reward"
GS100_REMAKE = "event/GatheringTokenGold/Obj_Rupee_Gold"
ITEM_FIX = {"Broken Sword": "Item_BrokenSword"}  # config/item_map.json names the broken Giant's Knife
# config/item_map.json has no shuffled Master Sword entry, and without this mapping the Kak 100 Gold Skulltula
# reward crashed planning. It's the same pouch actor story.item_for uses.
ITEM_FIX["Master Sword"] = "Weapon_Sword_Master"
# NPC rewards the core leaves vanilla because the remake gives them in two steps. The NPC hands over the next
# tier of its vanilla upgrade (medium or large) after a once-only flag check, so both steps get the item.
# Kak 10/30: the matcher paired both wallets with both. The 10-token step is Event398 and the 30-token step
# Event194, each behind its KakarikoVillage_GatheringTokenGold_GetReward flag.
# Kak Man on Roof is Npc_Hylia_001 (flags Npc_Hylia_001_IsOnTheRoof, Npc_Hylia_001_IsGetHeartPiece), which the
# matcher left ambiguous.
TIERED = {
    "LW Target in Woods": ["event/Dm_LostWood_0040/Dm_LostWood_0040/Event17/ActorName",
                           "event/Dm_LostWood_0040/Dm_LostWood_0040/Event30/ActorName"],
    "Market Shooting Gallery Reward": ["event/MiniGame_HitTarget/MiniGame_HitTarget/Event378/ReveiveItem",
                                       "event/MiniGame_HitTarget/MiniGame_HitTarget/Event241/ReveiveItem"],
    "Kak Shooting Gallery Reward": ["event/MiniGame_HitTarget/MiniGame_HitTarget/Event242/ReveiveItem",
                                    "event/MiniGame_HitTarget/MiniGame_HitTarget/Event381/ReveiveItem"],
    "Market Bombchu Bowling First Prize": [
        "event/MiniGame_BombchuBowling/MiniGame_BombchuBowling/Event306/ReveiveItem",
        "event/MiniGame_BombchuBowling/MiniGame_BombchuBowling/Event304/ReveiveItem"],
    "GF HBA 1500 Points": ["event/Minigame_HorsebackArchery/Minigame_HorsebackArchery/Event319/ActorName",
                           "event/Minigame_HorsebackArchery/Minigame_HorsebackArchery/Event320/ActorName"],
    "Deku Theater Skull Mask": [
        "event/LostWood_ScrubForestStageElder_SkullMaskFirst/LostWood_ScrubForestStageElder_SkullMaskFirst/Event32/ActorName",
        "event/LostWood_ScrubForestStageElder_SkullMaskFirst/LostWood_ScrubForestStageElder_SkullMaskFirst/Event29/ActorName"],
    "Deku Theater Mask of Truth": [
        "event/LostWood_ScrubForestStageElder_TrueMaskFirst/LostWood_ScrubForestStageElder_TrueMaskFirst/Event31/ActorName",
        "event/LostWood_ScrubForestStageElder_TrueMaskFirst/LostWood_ScrubForestStageElder_TrueMaskFirst/Event2/ActorName"],
    "Kak 10 Gold Skulltula Reward": ["event/GatheringTokenGold/GatheringTokenGold/Event398/TakenRewardActor"],
    "Kak 30 Gold Skulltula Reward": ["event/GatheringTokenGold/GatheringTokenGold/Event194/TakenRewardActor"],
    "Kak Man on Roof": ["event/Npc_Hylia_001_Adult/Npc_Hylia_001_Adult/Event4/ActorName"],
    # The two frog heart pieces share the location id event/MiniGame_FrogTenors/Obj_Heart_Piece, so as core scene
    # locations a seed only wrote one of their items. They're the Song of Storms prize and the bug game's prize
    # (first try and retry calls of MushiToriGame, which hands its ActorName over).
    "ZR Frogs in the Rain": ["event/MiniGame_FrogTenors/MiniGame_FrogTenors/Event384/ActorName"],
    "ZR Frogs Ocarina Game": ["event/MiniGame_FrogTenors/MiniGame_FrogTenors/Event161/ActorName",
                              "event/MiniGame_FrogTenors/MiniGame_FrogTenors/Event75/ActorName"],
}
GRANNY = "Kak Granny Buy Blue Potion"
# The expensive merchants the shops plugin leaves vanilla, because Medigoron and Granny keep no sold flag
# (data/rando/shop_map.json). We sell them here once each on a save flag (data/rando/songs_trade_flags.json)
# when shuffle_expensive_merchants is on. The shops plugin owns the setting and sells the carpet salesman's item.
GRANNY_ENABLED = True
MERCHANTS = (npcs.MEDIGORON, GRANNY)
# NPC rewards OoTR always shuffles that need more than a changed give step (_songs_trade_npcs.py)
ALWAYS = {npcs.ROLLING: DATA["rolling_goron"]["reward_ids"], npcs.DAMPE_DIG: [DATA["dampe_dig"]["reward_id"]]}
_kept = {}


# Settings
def before_build(settings):
    """A seed where Link can own two trade items of one age at once holds the trade button's owned-record flags
    (tools/rando/free_flags.py, tools/trade_slot.py needs_picker). Other seeds hold none."""
    import free_flags
    import trade_slot
    free_flags.hold("songs_trade", trade_slot.claimed_flags() if trade_slot.needs_picker(settings) else [])
    import mask_slot  # the mask button's owned record (tools/mask_slot.py), where Link can own several masks
    free_flags.hold("songs_trade_masks", mask_slot.claimed_flags() if mask_slot.needs_picker(settings) else [])
    # the remake-only GF Cow's give flag comes from the shared pool (songs_trade_flags.json "flags_claimed"). It's
    # held while cows are shuffled so the drops and fairies plugins never pick it.
    gf = COWS.get("gf")
    free_flags.hold("songs_trade_cows", [FLAGS[gf]] if gf and settings.shuffle_cows else [])
    if gf and settings.shuffle_cows:
        _register_cow_hint(gf, GF_COW_HINT)


# OoTR-style hint text for the remake-only GF Cow, like OoTR's GV Cow ("a #cow in Gerudo Valley# gifts", overworld,
# sometimes). It only goes into OoTR's hint tables while cows are shuffled, so a seed without them doesn't change.
GF_COW_HINT = ("a #cow at the horseback archery range# gifts", "a #cow in Gerudo's Fortress# gifts",
               ["overworld", "sometimes"])


def _register_cow_hint(name, row):
    """Puts `name`'s text into OoTR's hint tables (vendor/ootr HintList.hintTable and every Language's, the way
    extras_npcs registers its locations), so hints can name the location like OoTR names its own cows."""
    import HintList
    import Language
    HintList.hintTable.setdefault(name, tuple(row))
    _register_cow_hint.texts[name] = tuple(row)
    if not getattr(Language.Language.__init__, "remake_songs_trade_cows", False):
        original = Language.Language.__init__

        def init(self, lang, _original=original):  # every language's hint table (World makes one per world)
            _original(self, lang)
            for n, (vague, clear, _) in _register_cow_hint.texts.items():
                self.hintTable.setdefault(n, {"vague_hint": vague, "clear_hint": clear, "gender": "no_gender"})
        init.remake_songs_trade_cows = True
        Language.Language.__init__ = init


_register_cow_hint.texts = {}


def check_settings(settings):
    problems = []
    for name, ok in SUPPORTED.items():
        if getattr(settings, name, None) not in ok:
            problems.append(f"{name} = {getattr(settings, name, None)!r}: not supported ({REASONS[name]}); "
                            f"the patcher can make {', '.join(map(repr, ok))}")
    if getattr(settings, "shuffle_song_items", None) == "dungeon" and not hasattr(sys.modules.get("parity.drops"),
                                                                                "get_scene_pickups"):
        problems.append("shuffle_song_items = 'dungeon': the boss Heart Containers give songs through the drops "
                        "plugin's get-scene hook (enable the drops plugin)")
    bad = set(getattr(settings, "ocarina_songs", []) or []) - {"frog", "warp", "frogs2"}
    if bad:
        problems.append(f"ocarina_songs: unknown {sorted(bad)}")
    problems += child.check_settings(settings)
    problems += adult.check_settings(settings)
    remake = getattr(settings, "remake", None) or {}
    for k, ok in REMAKE_SETTINGS.items():
        if k in remake and remake[k] not in ok:
            problems.append(f"{k} = {remake[k]!r}: takes {', '.join(map(repr, ok))}")
    return problems


def finish_plan(settings, plan, cfg):
    """Runs once the plan is whole (generate.main). If it shows an Ocarina note item (an Ocarina button display), this
    adds the labels' context plan["_show_models"] (show_models.context with the controls and the controller, "auto"
    resolved now), its read-back note (_gaps "show_models", show_models.verify_note) and the resolved controller in
    cfg, so settings_used.json rebuilds the same seed."""
    import json
    text = json.dumps({k: v for k, v in plan.items() if not k.startswith("_")}, default=str)
    displays = sorted(d for d in show_models.NOTE_PITCH if f'"{d}"' in text)
    if not displays:
        return
    ctx = show_models.context(settings)
    plan["_show_models"] = ctx
    plan["_gaps"] = dict(plan.get("_gaps") or {}, show_models=dict(
        {k: v for k, v in ctx.items() if k != "controller_from"}, displays=displays))
    cfg["remake_ocarina_controls"] = ctx["controls"]
    cfg["remake_controller"] = ctx["controller"]


def _cow_names():
    names = [COWS["kf"], COWS["gv"]] + [n for g in COWS["generic"] for n in g["ootr"]]
    if COWS.get("gf"):  # the remake-only Gerudo Fortress cow (data/rando/logic/songs_trade.json new_locations)
        names.append(COWS["gf"])
    return names


def _active(settings):
    """OoTR locations this plugin patches for these settings."""
    out = {TALON} | set(TIERED) | set(ALWAYS) | lake.active(settings)
    if GRANNY_ENABLED and getattr(settings, "shuffle_expensive_merchants", False):
        out |= set(MERCHANTS)
    if settings.shuffle_cows:
        out |= set(_cow_names())
    if settings.shuffle_frog_song_rupees:
        out |= set(FROG_SONGS)
    if settings.shuffle_loach_reward != "off":
        out.add(LOACH)
    out |= child.active(settings)
    out |= adult.active(settings)
    return out


def keep_locations(world, settings):
    _world["w"] = world  # so hand_actor has the seed's settings for plugins whose plan runs before ours
    adult.configure(settings)  # so the Pocket Egg is hatched for every plugin's plan, not only from world_plan on
    out = set()
    for name in sorted(_active(settings)):
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.item is None and not loc.locked:
            out.add(name)
    _kept[id(world)] = out
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "CALL_LOCATIONS"):  # a dungeon item here: its give steps call its credit entry
        dg.CALL_LOCATIONS.update(out)  # _target, and the generic cows' own rule keeps progression items away
    return out


def before_fill(world, settings):
    kept = _kept.get(id(world), set())
    generic = {n for g in COWS["generic"] for n in g["ootr"]}
    for name in sorted(kept):
        loc = world.get_location(name)
        prev = loc.item_rule
        if name in generic and not COWS["generic_cows_any_item"]:
            # TODO: until the in-game test shows each cow is told apart, a missed cow may only lose junk
            loc.item_rule = (lambda location, item, prev=prev: not item.advancement and prev(location, item))
        # No rule for a progressive item at a give step that can't hand it over itself, like the Kak 10/30 Gold
        # Skulltula Reward. The step becomes a call to its tier entry (ops.reward_spec).
    if getattr(settings, "ocarina_songs", None):
        _fit_song_lengths(world, settings)
    child.before_fill(world, settings, kept)
    adult.before_fill(world, settings, kept)


GIVE_MODES = ops.load("scene_give_modes.json")["locations"]


def _step_progressive(reward_id):
    """Whether the patcher can give a progressive item at this give step (data/rando/scene_give_modes.json)."""
    _, file, _fc, event, _p = reward_id.split("/")
    return any(mode is not None for loc in GIVE_MODES.values() for k, mode in loc["steps"].items()
               if k == f"{file}.bfevfl.zs:{event}")


# Items
def item_for(item, location, world):
    """item is the OoTR item name at `location` (a chest or core scene location). A progressive item at a core scene
    location whose give steps can't hand it over by themselves becomes a call to its tier entry (progressive_spec)."""
    return (progressive_spec(item, location) or adult.item_for(item, location, world)
            or child.item_for(item, location, world) or ITEM_FIX.get(item))


def progressive_spec(item, location, plan_name=None):
    """For OoTR progressive `item` at core scene location `location` whose give steps can't hand it over by
    themselves, the reward spec calling its tier entry (ops.call_spec), else None and the core gives it as before.
    Those are the steps with no PouchSystemActor and no plain give-routine call in data/rando/scene_give_modes.json,
    e.g. Kak 20/40/50/100 Gold Skulltula Reward, LW Skull Kid, the memory game, Anju as child, the lost dog, or the
    Kokiri wallet at an in-place copy. `plan_name` is the plan's progressive item (extras_items.target_name)."""
    if item not in PROGRESSIVE:
        return None
    import generate
    rid = generate.scene_locations().get(location)
    if rid is None:
        return None
    if plan_name is None:
        ex = sys.modules.get("parity.extras_items")
        plan_name = ex.target_name(item) if ex is not None else item
    if ops.takes_progressive([rid], plan_name):
        return None
    return ops.call_spec(plan_name)


_cur = {"world": None}  # the world whose plan is being built (trap kinds are drawn per location)
_world = {"w": None}    # the seed's world, from keep_locations on (hand_actor)


def hand_actor(item, location=None):
    """The shared item resolver. It gives the actor any plain hand-over (a chest's contents, a scrub or carpet sale, a
    silver-rupee spot's or a hideout jail's give step) uses for OoTR item `item`, where this plugin knows better than
    config/item_map.json. That's the Weird Egg hatched (the Chicken, HC Malon Egg keeps the egg), the Pocket Egg
    hatched with the adult trade shuffle on, the masks and the Chicken, the Broken Sword and the Master Sword. None
    means config/item_map.json's. This way these items don't have to be kept out of other plugins' locations."""
    w = _world["w"] or _cur["world"]
    got = adult.item_for(item, location, w) if w is not None else None
    got = got or child.item_for(item, location, w) or ITEM_FIX.get(item)
    return got if isinstance(got, str) else None


def plain_give(item, location=None, window=False):
    """How a plain give step hands over OoTR item `item`, leaving ice traps and dungeon items aside. A plain give
    step is one node in another plugin's scene, like a silver-rupee spot, a hideout jail or the Treasure Chest Game
    salesman. Returns ("call", "File:Entry") for an item given by an entry of its own (a progressive item's tier
    entry, requested here, the Magic Bean Pack's, a soul's or the Skeleton Key's). Otherwise ("actor", remake
    actor) from hand_actor, else config/item_map.json. None if neither."""
    if item in PROGRESSIVE:
        ex = sys.modules.get("parity.extras_items")
        return ("call", ops.request_host(ex.target_name(item) if ex is not None else item, window=window))
    actor = hand_actor(item, location)
    if actor:
        return ("actor", actor)
    try:
        t = _target(item, location)
    except ValueError:
        return None
    if t.get("call") and not t.get("ice_trap"):
        return ("call", t["call"])
    return ("actor", t["actor"]) if t.get("actor") else None


def _target(item_name, location=None):
    """OoTR item -> {"progressive": name}, {"ice_trap": True} or {"actor": remake actor}. The ice trap is the shared
    freeze (tools/rando/parity/chests.py), and with the OoTR location it also gets "call", the effect of the trap
    kind it drew."""
    hatched = adult.target(item_name, lambda _n: None)
    if hatched:
        return hatched
    if item_name == "Weird Egg" or child.actor_for(item_name) or item_name == child.BEAN_PACK:
        return child.target(item_name)
    if item_name == "Ice Trap":
        if location and _cur["world"] is not None:
            from parity import chests
            return {"ice_trap": True, "call": chests.trap_call(_cur["world"], location)}
        return {"ice_trap": True}
    ap = sys.modules.get("parity.archipelago")  # another Archipelago player's item: its "found" text (a scene call,
    if ap is not None and item_name in ap.PLACEHOLDER_NAMES:  # as the Magic Bean Pack's), nothing handed over
        return {"call": ap.found_call(location, _cur["world"])}
    so = sys.modules.get("parity.extras_souls")  # a soul or the Skeleton Key gets its give entry (flag and message) on
    if so is not None and hasattr(so, "call_target") and so.call_target(item_name):  # every call path
        return {"call": so.call_target(item_name), "model": "Obj_Rupee_Blue"}  # ("model": named only, never given)
    dg = sys.modules.get("parity.dungeons")  # a dungeon item uses its credit entry (the dungeons plugin builds it for
    if dg is not None and dg.dungeon_item(item_name) is not None:  # every item at a CALL_LOCATIONS spot, after_fill)
        return {"call": f"{dg.GET_FILE}:{dg.call_entry(item_name)}", "dungeon": item_name,
                "model": dg.MODEL[dg.dungeon_item(item_name)[0]]}
    if dg is not None and hasattr(dg, "heal_call") and dg.heal_call(item_name):  # Recovery Heart, Fairy Drop: their
        #   own hold-up and the game's heal (dungeons.heal_graph)
        return {"call": dg.heal_call(item_name), "model": dg.HEAL[item_name][1], "heal": True}
    if item_name in PROGRESSIVE:
        ex = sys.modules.get("parity.extras_items")  # child-wallet seeds: the three-tier wallet's plan name
        return {"progressive": ex.target_name(item_name) if ex is not None else item_name}
    if item_name in ITEM_FIX:
        return {"actor": ITEM_FIX[item_name]}
    if item_name in ITEM_MAP["items"]:
        return {"actor": ITEM_MAP["items"][item_name]}
    if item_name in ITEM_MAP["junk_for"]:
        return {"actor": ITEM_MAP["junk_for"][item_name]}
    raise ValueError(f"no remake item for OoTR's {item_name!r}")


def _ice_spec(rid, location=None):
    """Reward spec replacing every give step of reward `rid` with a call to the shared freeze (or the effect of the
    trap kind OoTR location `location` drew)."""
    from parity import chests
    return chests.scene_ice_spec(rid, location, _cur["world"])


def _item(world, name):
    try:
        loc = world.get_location(name)
    except KeyError:
        return None
    return loc.item.name if loc.item is not None else None


# Songs
def _song_ops(o, world):
    for loc_name in SONG_LOCATIONS:
        rec = DATA["songs"][loc_name]
        item = _item(world, loc_name)
        if item is None or item == rec["vanilla"]:
            continue
        song = item if item in SONG_TYPES else None
        if not hasattr(o, "song_lessons"):
            o.song_lessons = {}
        o.song_lessons[loc_name] = {"item": item, "song": song is not None}  # read back by verify()
        if loc_name == WINDMILL_LOCATION:  # the windmill man teaches only while Storms isn't owned
            for event in WINDMILL_STORM_QUERIES:
                o.param(WINDMILL_NPC, WINDMILL_NPC, event, "GameDataName", WINDMILL_TAUGHT)
        for scene, s in rec["scenes"].items():
            fc = s["flowchart"]
            for step in s["lesson"]:
                graph = f"RandoST_Lesson_{step['event']}"
                if song is None:  # no song, so the vanilla notes are shown and followed, then played back unlearned
                    if step["kind"] not in ("example", "follow"):  # 1-frame waits froze Sheik in Crater
                        o.replace(scene, fc, step, graph,
                                  {"call": {"call": f"Dm_SY_Ocarina:{PLAYBACK}", "next": ops.at(step["next"])}},
                                  "call")
                elif step["kind"] in ("example", "follow"):
                    o.param(scene, fc, step["event"], "MelodyType", SONG_TYPES[song])
                else:  # PlayAuto (frog songs) or PlayAutoForSeek (warp songs) adds the lesson's song
                    want = "LearningOcarinaPlayAutoForSeek" if SONG_TYPES[song] in WARP_TYPES \
                        else "LearningOcarinaPlayAuto"
                    if want != step["entry"]:
                        o.replace(scene, fc, step, graph,
                                  {"call": {"call": f"Dm_SY_Ocarina:{want}", "next": ops.at(step["next"])}}, "call")
            for step in s["isget_sets"]:  # Sheik in Crater marks Bolero as obtained before teaching it
                o.replace(scene, fc, step, f"RandoST_SkipIsGet_{step['event']}",
                          {"wait": ops.wait_node(s["wait_actor"], ops.at(step["next"]))}, "wait")
        o.notes.append(f"{loc_name}: lesson " + (f"teaches {song}" if song else f"played back, not learned (gives {item})"))


def _fit_song_lengths(world, settings):
    """Random songs keep their slot's vanilla note count (the score book is rewritten in place)."""
    import OcarinaSongs
    vanilla = {name: notes for name, (_, kind, notes) in OcarinaSongs.SONG_TABLE.items() if kind != "frogs2"}
    kinds = {name: kind for name, (_, kind, _n) in OcarinaSongs.SONG_TABLE.items()}
    rand = set()
    if "frog" in settings.ocarina_songs:
        rand |= {n for n, k in kinds.items() if k == "frog"}
    if "warp" in settings.ocarina_songs:
        rand |= {n for n, k in kinds.items() if k == "warp"}
    rand -= set(world.distribution.configure_songs())  # plandomized songs are kept as given
    songs = world.song_notes
    for name in sorted(rand, key=lambda n: OcarinaSongs.DIFFICULTY_ORDER.index(n)):
        want = len(vanilla[name])
        if len(songs[name].activation) == want:
            continue
        others = [s for n, s in songs.items() if n != name and n != "ZR Frogs Ocarina Game"]
        for _ in range(5000):
            s = OcarinaSongs.get_random_song()
            if len(s.activation) == want and not any(OcarinaSongs.subsong(s, x) or OcarinaSongs.subsong(x, s)
                                                     for x in others):
                songs[name] = s
                break
        else:
            raise ValueError(f"ocarina_songs: no {want}-note melody found for {name}")


def _melody_ops(o, world, settings):
    if not getattr(settings, "ocarina_songs", None):
        return
    import OcarinaSongs
    book = DATA["melody"]
    sym = {"A": "A", "v": "Down", ">": "Right", "<": "Left", "^": "Up"}
    sets = {}
    for name, song in world.song_notes.items():
        if name not in SONG_TYPES:
            continue  # the frogs' game melody (frogs2): the remake's frog game has none
        notes = str(song)
        entry = book["entries"][SONG_TYPES[name]]
        if len(notes) != len(entry["notes"]):
            raise ValueError(f"{name}: {len(notes)} notes but the score book slot has {len(entry['notes'])}")
        new = [book["notes"][sym[c]] for c in notes]
        for j, (a, b) in enumerate(zip(entry["notes"], new)):
            if a != b:
                sets[f"MelodyScores.{entry['index']}.MelodyScore.{j}"] = b
        if notes != OcarinaSongs.SONG_TABLE[name][2]:
            o.notes.append(f"{name}: melody {notes}")
    if sets:
        o.byml.append({"file": book["file"], "set": sets})


# Cows
PROXY, PROXY_LINK = "EventProxyRequestActor", "EventProxyRequestLink"


def _cow_probing():
    """Whether this test build asks for the cow probes ("probes": "cows" in parity/_test_start.py,
    songs_trade_cows.json "probe"). No other seed gets them."""
    ts = sys.modules.get("parity._test_start")
    return bool(ts is not None and ts.probe("cows"))


def _flag_clear(name, nxt):
    n = ops.flag_set(name, nxt)
    n["params"]["Value"] = False
    return n


def _cow_ops(o, world):
    d = DATA["cows"]
    f, fc = d["file"], d["file"]
    items = {n: _item(world, n) for n in _cow_names()}
    probe = COWS["probe"] if _cow_probing() else None
    if probe is None and not any(v and v != "Milk" for v in items.values()):
        return
    pf, pi = (probe or {}).get("flags", {}), (probe or {}).get("items", {})
    # KF Link's house: its own scene entry
    kf = COWS["kf"]
    n, first = {}, None
    if items.get(kf):
        n = {"q": ops.flag_query(FLAGS[kf], ops.at(d["kf_start"]["event"]), "give"),
             "give": o.give(_target(items[kf], kf), "set"), "set": ops.flag_set(FLAGS[kf], None)}
        first = "q"
    if probe is not None:  # test builds only: Link's house cow (kf), its gate (the flag) skipped
        n.update({"p": ops.flag_query(pf["kf"], "p_give", first or ops.at(d["kf_start"]["event"])),
                  "p_give": o.give(_target(pi["kf"]), "p_clear"), "p_clear": _flag_clear(pf["kf"], None)})
        first = "p"
    if first:
        o.replace(f, fc, d["kf_start"], "RandoST_CowKF", n, first)
    # The GV (child) and GF (adult) cows share Cow_GiveMilk_gerudo and are told apart by age. The GV cow is
    # child-only (GerudoValley_Child_Static) and the GF cow adult-only (GerudoFortress_Adult_Static). GF Cow is the
    # remake-only location (songs_trade_cows.json "gf"), given like GV's: its flag, the item, the flag set.
    gv, gf = COWS["gv"], COWS.get("gf")
    m, m_first = {}, None
    milk_g, after_g = ops.at(d["gerudo_give"]["event"]), ops.at(d["gerudo_give"]["next"])
    if items.get(gv) or (gf and items.get(gf)):
        m = {"age": {"actor": "Player_Event", "query": "EventQueryPlayerIsChild",
                     "cases": {ops.YES: "q" if items.get(gv) else milk_g, ops.NO: milk_g}}}
        m_first = "age"
    if items.get(gv):
        m.update({"q": ops.flag_query(FLAGS[gv], milk_g, "give"),
                  "give": o.give(_target(items[gv], gv), "set"),
                  "set": ops.flag_set(FLAGS[gv], after_g)})
    if gf and items.get(gf):
        m["age"]["cases"][ops.NO] = "gf_q"
        m.update({"gf_q": ops.flag_query(FLAGS[gf], milk_g, "gf_give"),
                  "gf_give": o.give(_target(items[gf], gf), "gf_set"),
                  "gf_set": ops.flag_set(FLAGS[gf], after_g)})
    if probe is not None and gf and items.get(gf):  # the GF probe below is moot once the cow is a location
        m.update({"p": ops.flag_query(pf["gv"], "p_give", "age"),
                  "p_give": o.give(_target(pi["gv"]), "p_clear"), "p_clear": _flag_clear(pf["gv"], after_g)})
        m_first = "p"
    elif probe is not None:
        # test builds only. The GV cow (gv) with its gate (age, flag) skipped. The Gerudo Fortress cow (adult, no OoTR
        # location, no flag at all) gives an item every song, then a second one if any cow's save flag already reads as
        # set.
        if not m:
            m = {"age": {"actor": "Player_Event", "query": "EventQueryPlayerIsChild",
                         "cases": {ops.YES: milk_g, ops.NO: milk_g}}}
        m["age"]["cases"][ops.NO] = "gf"
        cow_flags = [FLAGS[x] for x in _cow_names()]
        m["gf"] = o.give(_target(pi["gf"]), "gf_t0")
        for i, fl in enumerate(cow_flags):
            m[f"gf_t{i}"] = ops.flag_query(fl, "gf_tell", f"gf_t{i + 1}" if i + 1 < len(cow_flags) else after_g)
        m["gf_tell"] = o.give(_target(pi["gf_flag"]), after_g)
        m.update({"p": ops.flag_query(pf["gv"], "p_give", "age"),
                  "p_give": o.give(_target(pi["gv"]), "p_clear"), "p_clear": _flag_clear(pf["gv"], after_g)})
        m_first = "p"
    if m_first:
        o.replace(f, fc, d["gerudo_give"], "RandoST_CowGV", m, m_first)
    # Generic cows (songs_trade_cows.json). Each placement links an anchor of its own, named after its group, and
    # gets an EventProxyRequestActor at the cow that links the cow (EventProxyRequestLink) and that anchor. An actor's
    # ocarina replace event finds instance names through its proxy in every vanilla case (the bean soils' 'Dirt',
    # Npc_Pierre's 'BonooruCamera'), and the actor itself links none. After Epona's Song, Cow_GiveMilk asks for each
    # name in turn, and only the played cow's proxy answers for its own name. The item comes instead of the milk
    # (OoTR), then the scene ends like it does after the milk hand-over (Event64, the cow's volatile flag
    # Animal_Cow_HaveTalked).
    # Using anchors of other actors, or anchors linked from the cow only with no proxy, just gave milk in game.
    g_n, chain = {}, []
    tr = d["generic_transition"]
    milk, after = ops.at(tr["event"]), ops.at(tr["next"])
    for gi, g in enumerate(COWS["generic"]):
        names = [x for x in g["ootr"] if items.get(x)]
        if not names:
            continue
        chain.append((gi, g, names))
    for k, (gi, g, names) in enumerate(chain):
        nxt_site = f"near{chain[k + 1][0]}" if k + 1 < len(chain) else milk
        g_n[f"near{gi}"] = ops.anchor_query(g["anchor"], f"g{gi}_q0", nxt_site)
        for j, name in enumerate(names):
            later = f"g{gi}_q{j + 1}" if j + 1 < len(names) else milk
            g_n[f"g{gi}_q{j}"] = ops.flag_query(FLAGS[name], later, f"g{gi}_give{j}")
            g_n[f"g{gi}_give{j}"] = o.give(_target(items[name], name), f"g{gi}_set{j}")
            g_n[f"g{gi}_set{j}"] = ops.flag_set(FLAGS[name], after)
    g_first = f"near{chain[0][0]}" if chain else None
    if probe is not None:
        # test builds only. Each probe test sets its flag at the start and the branch clears it, so the next song
        # plays like in every seed. Impa's child cow (lookup) tells by the item which of its two probe anchors the event
        # finds, the one linked from the cow only ("own") or the one linked from its proxy only ("proxy").
        own, px = probe["anchors"]["own"][0], probe["anchors"]["proxy"][0]
        g_n.update({"p": ops.flag_query(pf["lookup"], "p_own", g_first or milk),
                    "p_own": ops.anchor_query(own, "p_own_px", "p_noown_px"),
                    "p_own_px": ops.anchor_query(px, "p_both", "p_ownonly"),
                    "p_noown_px": ops.anchor_query(px, "p_pxonly", "p_none"),
                    "p_both": o.give(_target(pi["both"]), "p_clear"),
                    "p_ownonly": o.give(_target(pi["own"]), "p_clear"),
                    "p_pxonly": o.give(_target(pi["proxy"]), "p_clear"),
                    "p_none": o.give(_target(pi["none"]), "p_clear"),
                    "p_clear": _flag_clear(pf["lookup"], after)})
        g_first = "p"
        o.cows_probe = probe  # read back by verify_cows
    if g_first:
        o.replace(f, fc, tr, "RandoST_Cows", g_n, g_first)
    proxies = {}  # (file, cow) -> the proxy's placement op
    for gi, g, _ in chain:
        for p in g["placements"]:
            o.placements.append({"file": p["file"], "hash": p["anchor_source"], "twin": p["anchor"],
                                 "join_groups": False,
                                 "set": {"Name": g["anchor"], "Translate": [float(v) for v in p["pos"]]}})
            o.placements.append({"file": p["file"], "hash": p["cow"], "add_links": [{"dst": p["anchor"]}]})
            proxies[(p["file"], p["cow"])] = _proxy_op(p, [p["anchor"]])
    if chain:
        o.cows = {g["anchor"]: g["placements"] for _, g, _ in chain}  # read back by verify_cows (in_game_check)
    if probe is not None:
        key = (probe["file"], probe["cow"])
        if key not in proxies:  # Impa's cow holding milk in a probe build gets its proxy for the probe alone
            p = next(p for g in COWS["generic"] for p in g["placements"] if (p["file"], p["cow"]) == key)
            proxies[key] = _proxy_op(p, [])
        for name, h in sorted(probe["anchors"].values()):
            o.placements.append({"file": probe["file"], "hash": probe["anchor_source"], "twin": h,
                                 "join_groups": False,
                                 "set": {"Name": name, "Translate": [float(v) for v in probe["pos"]]}})
        o.placements.append({"file": probe["file"], "hash": probe["cow"],
                             "add_links": [{"dst": probe["anchors"]["own"][1]}]})
        proxies[key]["add_links"].insert(-1, {"dst": probe["anchors"]["proxy"][1]})
    o.placements += list(proxies.values())
    o.notes.append("cows: " + ", ".join(f"{k}: {v}" for k, v in sorted(items.items()) if v))


def _proxy_op(p, anchors):
    """A new EventProxyRequestActor at cow placement `p` (songs_trade_cows.json "proxy"). It's a copy of the file's
    DestinationAnchor p["anchor_source"] turned into a proxy, placed the way vanilla proxies are (Gyaml, Translate,
    links, no Name or Rotate). It links a Reference to each of `anchors` and then an EventProxyRequestLink to the
    cow, in the vanilla order."""
    return {"file": p["file"], "hash": p["anchor_source"], "twin": p["proxy"], "join_groups": False,
            "set": {"Gyaml": PROXY, "Translate": [float(v) for v in p["pos"]]}, "remove": ["Name", "Rotate"],
            "add_links": [{"dst": a} for a in anchors] + [{"name": PROXY_LINK, "dst": p["cow"]}]}


# NPC rewards
def _talon_ops(o, world):
    item = _item(world, TALON)
    if item is None or TALON not in _kept_any(world):
        return
    t = _target(item, TALON)
    rid = DATA["talon"]["reward_id"]
    if t.get("ice_trap"):
        o.rewards[rid] = dict(_ice_spec(rid, TALON), note=f"{TALON}: {item}")
        return
    o.rewards[rid] = ops.reward_spec(t, f"{TALON}: {item}", [rid])


def _frog_ops(o, world, settings):
    if not settings.shuffle_frog_song_rupees:
        return
    d = DATA["frogs"]
    n, cases = {}, {}
    for loc_name, t in FROG_SONGS.items():
        item = _item(world, loc_name)
        if item is None:
            continue
        cases[t] = f"give{t}"
        n[f"give{t}"] = o.give(_target(item, loc_name), ops.at(d["after_reward"]["event"]),
                               copy=d["heart_give"]["event"])
    if not cases:
        return
    for t in range(14):  # other melodies keep the count-based rupees (they never reach this step)
        cases.setdefault(t, ops.at(d["count_branch"]["event"]))
    n["song"] = {"actor": "GameSystemActor", "query": "EventQueryMelodyTypeForNormal", "cases": cases}
    o.replace(d["file"], d["file"], d["count_branch"], "RandoST_FrogSongs", n, "song")
    o.notes.append("frog songs: " + ", ".join(f"{k}: {_item(world, k)}" for k in FROG_SONGS))


def _loach_ops(o, world, settings):
    if settings.shuffle_loach_reward == "off":
        return
    item = _item(world, LOACH)
    if item is None:
        return
    d = DATA["loach"]
    for k, step in enumerate(d["gives"]):
        n = {"q": ops.flag_query(FLAGS[LOACH], ops.at(step["event"]), "give"),
             "give": o.give(_target(item, LOACH), "set", copy=step["event"]),
             "set": ops.flag_set(FLAGS[LOACH], ops.at(step["next"]))}
        o.replace(d["file"], d["file"], step, f"RandoST_Loach{k}", n, "q")
    if settings.shuffle_loach_reward == "easy":
        o.notes.append("shuffle_loach_reward easy: applied as vanilla (the fishing tweaks need code)")
    o.notes.append(f"{LOACH}: {item}")


def _gs100_ops(o, world, settings):
    item = _item(world, GS100)
    if not settings.shuffle_100_skulltula_rupee or item is None or item == "Rupees (200)":
        return
    d = DATA["gs100"]
    nodes = dict(d["clone"])
    nodes["give"] = o.give(_target(item, GS100), ops.at(d["give"]["next"]), copy=d["give"]["event"])
    o.events.append({"file": d["file"], "flowchart": d["file"], "add_graph": "RandoST_GS100", "nodes": nodes,
                     "start": d["clone_start"]})
    o.events.append({"file": d["file"], "flowchart": d["file"], "event": d["first_flag"]["event"],
                     "next": f"RandoST_GS100_{d['clone_start']}"})
    # the repeatable reward stays the gold rupee (the core would put the item on every visit)
    o.rewards[GS100_REMAKE] = {"item": "Obj_Rupee_Gold", "note": f"{GS100}: {item} on the first visit only"}
    o.notes.append(f"{GS100}: {item} (first time), then the vanilla 200 rupees")


def _kept_any(world):
    return _kept.get(id(world), set())


def _tiered_ops(o, world):
    for name, rids in TIERED.items():
        item = _item(world, name)
        if item is None or name not in _kept_any(world):
            continue
        t = _target(item, name)
        for rid in rids:
            if t.get("ice_trap"):
                o.rewards[rid] = dict(_ice_spec(rid, name), note=f"{name}: {item}")
            else:
                o.rewards[rid] = ops.reward_spec(t, f"{name}: {item}", rids)


def _granny_ops(o, world, settings):
    if not getattr(settings, "shuffle_expensive_merchants", False) or GRANNY not in _kept_any(world):
        return
    item = _item(world, GRANNY)
    if item is None:
        return
    d = DATA["granny"]
    flag = FLAGS[GRANNY]
    # Granny's purchase checks for 100 rupees (vanilla), then the bottle check. The item needs no empty bottle, is
    # sold once (save flag), and the 100 rupees are taken the way her own sale does it (AddGameDataIntToRupee,
    # inverted).
    n = {"q": ops.flag_query(flag, ops.at(d["bottle_check"]["event"]), "price"),
         "price": {"copy": d["price"]["event"], "next": "pay"},
         "pay": {"actor": "PouchSystemActor", "action": "EventTriggerAddGameDataIntToRupee",
                 "params": {"IsSignInverse": True, "GameDataName": "SimpleShop_Price"}, "next": "give"},
         "give": o.give(_target(item, GRANNY), "set"),
         "set": ops.flag_set(flag, ops.at(d["give"]["next"]))}
    o.replace(d["file"], d["file"], d["bottle_check"], "RandoST_Granny", n, "q")
    o.notes.append(f"{GRANNY}: {item} (once, 100 rupees, no bottle needed), then blue potions as vanilla")


def _npc_ops(o, world, settings):
    kept = _kept_any(world)
    for name, fn in ((npcs.ROLLING, npcs.rolling_goron_ops), (npcs.DAMPE_DIG, npcs.dampe_dig_ops)):
        item = _item(world, name)
        if item is not None and name in kept:
            fn(o, DATA, item, _target(item, name), _ice_spec)
    if not getattr(settings, "shuffle_expensive_merchants", False):
        return
    item = _item(world, npcs.MEDIGORON)
    if item is not None and npcs.MEDIGORON in kept:
        npcs.medigoron_ops(o, DATA, FLAGS[npcs.MEDIGORON], item, _target(item, npcs.MEDIGORON), _ice_spec)
    if GRANNY in kept and _item(world, GRANNY) is not None:
        npcs.granny_gate_ops(o, DATA, FLAGS[GRANNY])


def _lake_ops(o, world):
    kept = _kept_any(world)
    items = {n: _item(world, n) for n in lake.LOCATIONS if n in kept}
    targets = {n: _target(i, n) for n, i in items.items() if i is not None}
    # the drops plugin's heart spots holding another item go through the same hook (its world_plan runs first)
    dr = sys.modules.get("parity.drops")
    pickups = dr.get_scene_pickups(world) if dr is not None and hasattr(dr, "get_scene_pickups") else []
    lake.world_plan_ops(o, items, targets, {n: FLAGS[n] for n in lake.LOCATIONS}, DATA["lake"], pickups)


def _gift_ops(o, world):
    """The drops plugin's scene gifts (GC spinning pot, ZD storms grotto, parity/_drops_gifts.py) give through this
    Ops, so their progressive, get-window and freeze entries are only added once, together with the hook's."""
    dr = sys.modules.get("parity.drops")
    if dr is not None and hasattr(dr, "scene_gift_ops"):
        dr.scene_gift_ops(o, world)
    fa = sys.modules.get("parity.fairies")  # the fairy shuffles (parity/fairies.py; its world_plan runs first)
    if fa is not None and hasattr(fa, "gift_ops"):
        fa.gift_ops(o, world)


def world_plan(settings, world):
    adult.configure(settings)
    _cur["world"] = world
    o = ops.Ops()
    o.world = world
    _song_ops(o, world)
    _melody_ops(o, world, settings)
    if settings.shuffle_cows:
        _cow_ops(o, world)
    _talon_ops(o, world)
    _frog_ops(o, world, settings)
    _loach_ops(o, world, settings)
    _gs100_ops(o, world, settings)
    _tiered_ops(o, world)
    _granny_ops(o, world, settings)
    _npc_ops(o, world, settings)
    child.world_plan_ops(o, world, settings, _kept_any(world))
    _lake_ops(o, world)
    _gift_ops(o, world)
    adult.biggoron_keep_knife_ops(o, world)
    adult.world_plan_ops(o, world, settings, _kept_any(world), _target, _ice_spec)
    # the tier entries other give steps call, each added once (ops.request_host for core scene locations, scrub
    # sales, the carpet salesman, the hideout jails and the Treasure Chest Game salesman)
    for name in ops.requested_hosts():
        o.give({"progressive": name}, None)
    for name in ops.requested_window_hosts():  # in the water, next to the get window (_window_give)
        lake._window_give(o, {"progressive": name}, None)
    # the effects of the trap kinds this plugin's locations drew (each added once per seed, chests.trap_host_ops)
    from parity import chests
    for kind in sorted(set(chests._trap_state(world)["calls"].values()), key=chests.TRAP_KINDS.index):
        o.events += chests.trap_host_ops(world, kind)
    o.byml.append(trade_order_op())  # every seed: child trade items show before adult ones (TRADE_ORDER)
    out = o.plan()
    # the trade button (tools/trade_slot.py, make_patch hooks it on the files as patched). Where Link can own two
    # trade items of one age at once it gets the picker and owned record, with its saved flags held in before_build.
    # In every seed Biggoron's timed removals take the timed item, never a child item listed first by TRADE_ORDER.
    import free_flags
    import trade_slot
    picker = trade_slot.needs_picker(settings)
    out["trade_slot"] = trade_slot.plan_section(TRADE_ORDER, picker)
    if picker:
        out["text"] = out.get("text", []) + trade_slot.text_ops()
        out.update(free_flags.held_plan("songs_trade"))
    if child.plan_gamedata(o):
        out["gamedata"] = child.plan_gamedata(o)
    # the mask button (tools/mask_slot.py, hooked by the same stage). Where Link can own several masks it gets the
    # picker (Navi's button), the owned record and the hooked checks and sales. Its saved flags are held in
    # before_build.
    import mask_slot
    if mask_slot.needs_picker(settings):
        msp = mask_slot.spec()
        out["trade_slot"]["masks"] = mask_slot.plan_section(settings)
        out["text"] = out.get("text", []) + mask_slot.text_ops()
        out["ainb"] = out.get("ainb", []) + mask_slot.ainb_ops(msp)
        redefined = {k for op in (out.get("gamedata") or []) for k in (op.get("boolexp") or {})}
        out["gamedata"] = list(out.get("gamedata") or []) + mask_slot.gamedata_ops(msp, skip=redefined)
        held = free_flags.held_plan("songs_trade_masks").get("_flags_held") or {}
        if held:
            out["_flags_held"] = dict(out.get("_flags_held") or {}, **held)
    held = free_flags.held_plan("songs_trade_cows").get("_flags_held") or {}  # GF Cow's give flag (before_build)
    if held:
        out["_flags_held"] = dict(out.get("_flags_held") or {}, **held)
    out["_songs_lessons"] = getattr(o, "song_lessons", None) or {}  # read back by verify (in_game_check)
    if getattr(o, "cows", None):
        out["_songs_cows"] = o.cows  # the generic cows' anchors and proxies (verify_cows)
    if getattr(o, "cows_probe", None):
        out["_songs_cows_probe"] = o.cows_probe  # a test build's cow probes (verify_cows)
    out["_verify_plugins"] = ["songs_trade"]
    return out


PLAY_REACH = 6.0  # how far from a cow Link can stand and still play to it (its attention range is shorter)


def _plan_cow_items(plan):
    """{OoTR cow location: item} from the plan's songs_trade_notes "cows: ..." line (Milk counts as no item)."""
    line = next((x for x in plan.get("songs_trade_notes") or [] if x.startswith("cows: ")), "")
    out = {}
    for name in _cow_names():
        i = line.find(f"{name}: ")
        if i >= 0:
            rest = line[i + len(name) + 2:]
            nxt = min([rest.find(f", {n}: ") for n in _cow_names() if rest.find(f", {n}: ") >= 0] or [len(rest)])
            if rest[:nxt] != "Milk":
                out[name] = rest[:nxt]
    return out


def cow_lookup(acts, cow):
    """{anchor name: [DestinationAnchor actors]} that an ocarina replace event started by placement `cow` can find by
    instance name. Those are the anchors linked (Reference) from an EventProxyRequestActor that links the cow with
    an EventProxyRequestLink, in the same level file. Every vanilla ocarina replace actor whose event names an
    anchor does it this way (the 18 bean soils' Field_PlantMagicBeanStormMelody 'Dirt', Npc_Pierre's
    BlewOcarinaByPlayer 'BonooruCamera'), and the actor itself links none. Anchors the cow links itself don't count,
    those gave milk in game."""
    found = {}
    for a in acts.values():
        lns = a.get("Links") or []
        if a.get("Gyaml") != PROXY or not any(ln.get("Name") == PROXY_LINK and str(ln.get("Dst")) == cow for ln in lns):
            continue
        for ln in lns:
            d = acts.get(str(ln.get("Dst")))
            if ln.get("Name") == "Reference" and d is not None and d.get("Gyaml") == "DestinationAnchor":
                found.setdefault(d.get("Name"), []).append(d)
    return found


def _cow_walk(fc, start, stop, answer):
    """Follows a cow scene from event index `start` as one song plays. `answer(query, params)` gives a switch's case
    value (None if it can't tell). Returns {"path", "gives" (calls), "sets", "clears" (GameData bools), "end" (an
    event of `stop`, None for the scene's end), "why" (why the walk stopped early)}."""
    ev = fc["events"]
    r = {"path": [], "gives": [], "sets": [], "clears": [], "end": None, "why": None}
    i = start
    for _ in range(500):
        if i is None or i == 0xFFFF:
            return r
        e = ev[i]
        r["path"].append(e["name"])
        if e["name"] in stop:
            r["end"] = e["name"]
            return r
        pr = {k: v.get("value") for k, v in ((e.get("params") or {}).get("items") or {}).items()}
        if e["type"] == "switch":
            q = fc["actors"][e["actor"]]["queries"][e["query"]]
            val = answer(q, pr)
            i = next((c["next"] for c in e["cases"] if c["value"] == val), None)
            if val is None or i is None:
                r["why"] = f"{e['name']}: {q} {pr}: no answer {val}"
                return r
        elif e["type"] == "action":
            if fc["actors"][e["actor"]]["actions"][e["action"]] == "EventTriggerSetGameDataBool":
                (r["sets"] if pr.get("Value") else r["clears"]).append(pr.get("GameDataName"))
            i = e.get("next")
        elif e["type"] == "subflow":
            r["gives"].append(f"{e.get('flowchart') or DATA['cows']['file']}:{e.get('entry_point')}")
            i = e.get("next")
        else:
            r["why"] = f"{e['name']}: a {e['type']} step"
            return r
    r["why"] = "no end in 500 steps"
    return r


def verify_cows(fs, plan):
    """The generic cows, read back the way the game resolves them. Each generic cow placement plays Epona's Song
    through the patched Cow_GiveMilk (from the Roar, Event1). Every anchor query is answered the way that cow's event
    would answer it: an anchor is only found if the cow's EventProxyRequestActor links it (cow_lookup) and it stands
    within the query's CheckDistance of a Link playing beside the cow. Every save-flag query is answered by the flags
    given so far. A cow of a group holding items (the plan's "cows:" note) has to hand one over and set that group's
    next flag, song after song in order, then reach the milk hand-over (Event3). A cow of a group holding none has to
    reach the milk with no hand-over.
    It also checks there's one proxy per item-holding cow, at the cow, that Event3 is still reached and that the
    milk scene's entry is vanilla. A vanilla Cow_GiveMilk with the queries in the milk scene fails this, and so do
    anchors linked from the cows with no proxy.
    A test build's probes (plan "_songs_cows_probe"): each probe branch hands something over and clears its flag.
    The lookup probe's answer under this model is reported in verify_cows.notes."""
    import math
    from romtools import byml_load
    from evfl import Evfl
    verify_cows.notes = []
    items = _plan_cow_items(plan)
    probe = plan.get("_songs_cows_probe") or None
    generic = {n for g in COWS["generic"] for n in g["ootr"]}
    gerudo = [] if probe else _verify_gerudo_cows(fs, items)  # a probe build skips the GV gate on purpose
    if not (set(items) & generic) and not probe:
        return gerudo
    bad, files = list(gerudo), {}

    def actors(f):
        if f not in files:
            files[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f), allow_big=True)[0].get("Actors") or []}
        return files[f]

    def pos(a):
        return [float(v) for v in a.get("Translate") or [0, 0, 0]]
    fc = next(x for x in Evfl(fs.read(f"Event/EventFlow/{DATA['cows']['file']}.bfevfl.zs")).flowcharts
              if x["name"] == DATA["cows"]["file"])
    ev = fc["events"]
    by = {e["name"]: i for i, e in enumerate(ev)}
    tr = DATA["cows"]["generic_transition"]
    milk, after = tr["event"], tr["next"]
    start = ev[by[tr["preds"][0][1]]].get("next")
    probe_flags = set(((probe or {}).get("flags") or {}).values())
    all_flags = {FLAGS[n] for n in _cow_names()}

    def answerer(found, cow_at, flags_set):
        def answer(q, pr):
            if q == "EventQueryIsDistanceBetweenActorsClose" and pr.get("IsAnchorActorB") is True and \
                    pr.get("ActorNameB") == "DestinationAnchor" and pr.get("ActorNameA") == "Player_Event":
                near = any(math.dist(pos(a), cow_at) + PLAY_REACH <= float(pr.get("CheckDistance") or 0)
                           for a in found.get(pr.get("InstanceNameB"), []))
                return ops.YES if near else ops.NO
            if q == "EventQueryIsGameDataBool" and pr.get("GameDataName") in all_flags | probe_flags:
                return ops.YES if pr.get("GameDataName") in flags_set else ops.NO
            return None
        return answer
    reached_milk = False
    for g in COWS["generic"]:
        held = [n for n in g["ootr"] if n in items]
        for p in g["placements"]:
            acts = actors(p["file"])
            cow = acts.get(p["cow"])
            if cow is None:
                bad.append(f"cow {p['cow']} ({g['ootr'][0]}): not in {p['file']}")
                continue
            found = cow_lookup(acts, p["cow"])
            tag = f"cow {p['cow']} ({'/'.join(g['ootr'])}, {p['file'].split('/')[-1]})"
            if held:
                px = [a for a in acts.values() if a.get("Gyaml") == PROXY and any(
                    ln.get("Name") == PROXY_LINK and str(ln.get("Dst")) == p["cow"] for ln in a.get("Links") or [])]
                if len(px) != 1 or math.dist(pos(px[0]), pos(cow)) > 0.5:
                    bad.append(f"{tag}: {len(px)} EventProxyRequestActors link it, want one at the cow")
            for k in range(len(held) + 1):
                flags_set = {FLAGS[n] for n in held[:k]}
                r = _cow_walk(fc, start, {milk, after}, answerer(found, pos(cow), flags_set))
                if r["why"]:
                    bad.append(f"{tag}: song {k + 1}: {r['why']}")
                    continue
                reached_milk |= r["end"] == milk
                if k < len(held):
                    want = FLAGS[held[k]]
                    if not r["gives"] or r["sets"] != [want]:
                        bad.append(f"{tag}: song {k + 1} reaches {r['end'] or 'the end'} giving {r['gives']} setting "
                                   f"{r['sets']}, not {held[k]}'s item and {want} (the event finds anchors "
                                   f"{sorted(found)})")
                elif r["end"] != milk or r["gives"] or r["sets"]:
                    bad.append(f"{tag}: song {k + 1} (every item given) reaches {r['end'] or 'the end'} giving "
                               f"{r['gives']} setting {r['sets']}, not the milk hand-over {milk}")
    if not reached_milk:
        bad.append(f"Cow_GiveMilk: no cow reaches the milk hand-over ({milk})")
    ep = fc["entry_points"].get("PushToBottleMilk")
    if ep is None or ev[ep["main"]]["name"] != DATA["cows"]["generic_start"]["event"]:
        bad.append("PushToBottleMilk: its entry doesn't start at the vanilla bottle query any more")
    if probe:
        bad += _verify_cow_probes(fs, fc, probe, actors, answerer, pos)
    return bad


def _verify_gerudo_cows(fs, items):
    """The two cows of Cow_GiveMilk_gerudo, read back from the patched scene (with the remake-only GF Cow). A child
    (the GV cow) and an adult (the GF cow) each play Epona's Song twice from the step after Event65. A cow holding an
    item (the plan's "cows:" note) hands it over and sets its own flag on the first song and reaches the milk
    hand-over (Event139) on the second. A cow holding none reaches the milk at once. Each age's walk answers the age
    query and only its own flag, so the other cow's flag never decides its path."""
    from evfl import Evfl
    d = DATA["cows"]
    cows = [(n, child) for n, child in ((COWS["gv"], True), (COWS.get("gf"), False)) if n]
    if not any(n in items for n, _ in cows):
        return []
    fc = next(x for x in Evfl(fs.read(f"Event/EventFlow/{d['file']}.bfevfl.zs")).flowcharts if x["name"] == d["file"])
    ev = fc["events"]
    by = {e["name"]: i for i, e in enumerate(ev)}
    g = d["gerudo_give"]
    start = ev[by[g["preds"][0][1]]].get("next")
    others = {FLAGS[n] for n, _ in cows}
    bad = []
    for name, child in cows:
        for k in range(2 if name in items else 1):
            flags_set = {FLAGS[name]} if k else set()

            def answer(q, pr, child=child, flags_set=flags_set):
                if q == "EventQueryPlayerIsChild":
                    return ops.YES if child else ops.NO
                if q == "EventQueryIsGameDataBool" and pr.get("GameDataName") in others:
                    return ops.YES if pr.get("GameDataName") in flags_set else ops.NO
                return None
            r = _cow_walk(fc, start, {g["event"], g["next"]}, answer)
            tag = f"{name} ({'child' if child else 'adult'}), song {k + 1}"
            if r["why"]:
                bad.append(f"Cow_GiveMilk_gerudo: {tag}: {r['why']}")
            elif name in items and not k:
                if not r["gives"] or r["sets"] != [FLAGS[name]] or r["end"] != g["next"]:
                    bad.append(f"Cow_GiveMilk_gerudo: {tag} gives {r['gives']} setting {r['sets']} and reaches "
                               f"{r['end']}, not {name}'s item and {FLAGS[name]}, then {g['next']}")
            elif r["gives"] or r["sets"] or r["end"] != g["event"]:
                bad.append(f"Cow_GiveMilk_gerudo: {tag} gives {r['gives']} setting {r['sets']} and reaches "
                           f"{r['end']}, not the milk hand-over {g['event']}")
    return bad


def _verify_cow_probes(fs, fc, probe, actors, answerer, pos):
    """Each probe branch of a test build (songs_trade_cows.json "probe") with its flag set has to hand something
    over and clear the flag. The lookup probe's answer under cow_lookup's model goes to verify_cows.notes."""
    bad = []
    ev = fc["events"]
    by = {e["name"]: i for i, e in enumerate(ev)}
    d = DATA["cows"]
    acts = actors(probe["file"])
    cow = acts.get(probe["cow"])
    found = cow_lookup(acts, probe["cow"]) if cow is not None else {}
    names = {v[0]: k for k, v in probe["anchors"].items()}
    flag = probe["flags"]["lookup"]
    r = _cow_walk(fc, ev[by[d["generic_transition"]["preds"][0][1]]].get("next"),
                  {d["generic_transition"]["event"], d["generic_transition"]["next"]},
                  answerer(found, pos(cow) if cow else [0, 0, 0], {flag}))
    if r["why"] or not r["gives"] or r["clears"] != [flag] or r["sets"]:
        bad.append(f"cow probe lookup: {r['why'] or ''} gives {r['gives']}, sets {r['sets']}, clears {r['clears']}")
    seen = sorted(names[n] for n in found if n in names)
    verify_cows.notes.append(f"cow probe lookup (Impa's child cow): this model expects "
                             f"{'+'.join(seen) or 'none'} -> {probe['items']['both' if len(seen) == 2 else (seen or ['none'])[0]]}")
    for key, step in (("kf", "kf_start"), ("gv", "gerudo_give")):
        preds = d[step]["preds"]
        if preds[0][0] == "entry":
            i = fc["entry_points"][preds[0][1]]["main"]
        else:
            i = ev[by[preds[0][1]]].get("next")
        f = probe["flags"][key]
        r = _cow_walk(fc, i, {d[step]["event"]}, lambda q, pr: (
            ops.YES if pr.get("GameDataName") == f else None) if q == "EventQueryIsGameDataBool" else None)
        if r["why"] or not r["gives"] or r["clears"] != [f]:
            bad.append(f"cow probe {key}: {r['why'] or ''} gives {r['gives']}, clears {r['clears']}")
    i = ev[by[d["gerudo_give"]["preds"][0][1]]].get("next")  # the Gerudo Fortress cow: adult, no flag set
    r = _cow_walk(fc, i, {d["gerudo_give"]["event"], d["gerudo_give"]["next"]}, lambda q, pr: (
        ops.NO if q in ("EventQueryPlayerIsChild", "EventQueryIsGameDataBool") else None))
    if r["why"] or len(r["gives"]) != 1 or r["end"] != d["gerudo_give"]["next"]:
        bad.append(f"cow probe gf: {r['why'] or ''} gives {r['gives']}, ends at {r['end']}")
    return bad


def verify(patch, plan, romfs):
    """Reads the song-spot edits back from the built patch (in_game_check, plan "_verify_plugins"). At a spot holding
    anything but a song, every way into a learning call (PlayAuto / PlayAutoForSeek) has to call
    Dm_SY_Ocarina:PlayAuto instead and go on where the learning call went, and the example and follow steps still
    have to be reached. With another item at Song from Windmill, the man's four Storms queries have to ask whether
    his lesson played."""
    import os
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(ops.HERE, "original"), [patch])
    bad = []

    def flowchart(name):
        return next(f for f in Evfl(fs.read(f"Event/EventFlow/{name}.bfevfl.zs")).flowcharts if f["name"] == name)
    for loc, rec in sorted((plan.get("_songs_lessons") or {}).items()):
        if not rec.get("song"):
            for scene, s in DATA["songs"][loc]["scenes"].items():
                fc = flowchart(s["flowchart"])
                ev = fc["events"]
                by = {e["name"]: e for e in ev}

                def name(i):
                    return ev[i]["name"] if i not in (None, 0xFFFF) and i < len(ev) else None
                for step in s["lesson"]:
                    if step["kind"] in ("example", "follow"):
                        if step["event"] not in by or not ops.progressive.predecessors(fc, by[step["event"]]):
                            bad.append(f"{scene}: {loc}'s {step['kind']} step {step['event']} is no longer reached")
                        continue
                    if step["event"] in by and ops.progressive.predecessors(fc, by[step["event"]]):
                        bad.append(f"{scene}: {loc} still reaches the learning call {step['event']}")
                    calls = [e for e in ev if e["name"].startswith(f"RandoST_Lesson_{step['event']}_")]
                    c = calls[0] if calls else None
                    if c is None or c["type"] != "subflow" or c.get("flowchart") != "Dm_SY_Ocarina" or \
                            c.get("entry_point") != PLAYBACK or name(c.get("next")) != step["next"] or \
                            not ops.progressive.predecessors(fc, c):
                        bad.append(f"{scene}: {loc}'s {step['event']} isn't replaced by a reached call of "
                                   f"Dm_SY_Ocarina:{PLAYBACK} going on to {step['next']}")
        if loc == WINDMILL_LOCATION:
            by = {e["name"]: e for e in flowchart(WINDMILL_NPC)["events"]}
            for event in WINDMILL_STORM_QUERIES:
                got = ((by.get(event, {}).get("params") or {}).get("items") or {}).get("GameDataName", {}).get("value")
                if got != WINDMILL_TAUGHT:
                    bad.append(f"{WINDMILL_NPC}: {event} asks {got}, not {WINDMILL_TAUGHT}")
    from romtools import byml_load
    van = Romfs(romfs, os.path.join(ops.HERE, "original"))
    old = next(b for b in byml_load(van.raw(POUCH_TABLE))[0]["ItemArray"] if b.get("BtnName") == TRADE_BUTTON)
    new = next((b for b in byml_load(fs.raw(POUCH_TABLE))[0]["ItemArray"] if b.get("BtnName") == TRADE_BUTTON), None)
    if new is None or [a.get("ActorShort") for a in new["Actor"]] != list(TRADE_ORDER) or \
            sorted(map(str, new["Actor"]), key=str) != sorted(map(str, old["Actor"]), key=str) or \
            {k: v for k, v in new.items() if k != "Actor"} != {k: v for k, v in old.items() if k != "Actor"}:
        bad.append(f"{POUCH_TABLE}: {TRADE_BUTTON} isn't the vanilla entries in TRADE_ORDER")
    if len(fs.raw(POUCH_TABLE)) != len(van.raw(POUCH_TABLE)):
        bad.append(f"{POUCH_TABLE}: size changed ({len(van.raw(POUCH_TABLE))} -> {len(fs.raw(POUCH_TABLE))})")
    bad += verify_cows(fs, plan)
    for line in getattr(verify_cows, "notes", None) or []:
        print(f"  cows: {line}")
    import trade_slot  # the trade button's picker, owned record and hooked hand-ins, and the seed's trades walked
    slot_bad, slot_notes = trade_slot.verify(patch, plan, romfs)
    verify.notes = slot_notes
    import mask_slot  # the mask button's picker, owned record, hooked checks and sales, the seed's mask uses walked
    mask_bad, mask_notes = mask_slot.verify(patch, plan, romfs)
    verify.mask_notes = mask_notes
    return bad + slot_bad + [f"mask button: {x}" for x in mask_bad]
