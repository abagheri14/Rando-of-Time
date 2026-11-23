"""Parity plugin: ice traps, chests beyond data/rando/chest_map.json, the Treasure Chest Game and the chest-look settings.

Data: data/rando/chests_locations.json,
data/rando/logic/chests.json (new OoTR locations), data/rando/chests_scenes.json (tools/rando/parity/_chests_scenes.py).

- Ice traps (junk_ice_traps, custom_ice_trap_count/percent, OoTR's own item pool). A chest holding one runs an
  ice-trap scene (_chests_scenes.py): the chest's own opening, Link's own frozen effect and sound, a flinch, half a
  heart of damage that never takes the last half heart, and the chest marked opened. It's on a reused scene ID
  (config/scene_rows.json, last two rows, one for small chests and one for big ones), like progressive items. The
  remake's own ice-trap chests (Obj_TBox_A_04) are OoTR's vanilla Ice Trap spots, and an Ice Trap there leaves the
  real trap chest as it is. Every chest type runs it (trap_route). A chest whose story or minigame scene stays
  (Mido's house, the Treasure Chest Game, Dampe's race, the Ice Cavern, Jabu-Jabu, Water and Spirit Temple story
  chests) runs it through that scene, like the dungeons plugin's item scene. The Fairy Note chest runs it on the
  small scene ID.
- Ice traps elsewhere: one shared freeze, Dm_SY_GetInEvent:Rando_IceTrap,
  added here whenever a non-chest location holds an ice trap. Core scene locations (NPCs, songs, cutscenes, boss
  rewards, Great Fairies) get it from item_for as a "call" reward spec. songs_trade, shops (scrubs and the carpet
  salesman, which also get Rando_IceTrap_Pay and copies of their sale routines) and drops make their own.
- remake_trap_weights (remake setting, default {"ice": 1}, OoT3DR's trap types): each Ice Trap draws a kind by
  weight (ice, shock, fire, rupee) from its own seed-and-location generator. In _chests_scenes.py trap_graph, shock
  and fire are the ice trap's attacker with their element. Every path plays the kind it drew. Chests use the ice
  trap's scene IDs, told apart by a stand-in of the kind's own (_chests_scenes.with_kinds). Scene and NPC
  locations, scrubs, the carpet salesman, special deals, the hideout jails, silver-rupee spots, fairies, the
  extras' NPC checks, heart spots, scene gifts and drop spots that hand their tag on (one get-scene tag per kind)
  call the kind's effect. Only a disguised drop spot that can't hand a tag on keeps the ice trap, and it draws no
  kind. The spoiler names the kind (Shock Trap, Fire Trap, Rupee Trap).
  Read back by _chests_traps.py.
- ice_trap_appearance: what an ice trap looks like only shows through OoTR's chest-size/texture setting and through
  freestanding and shop models. Chests keep their type here and show nothing before opening, so every value is
  accepted and changes nothing visible in a chest. Freestanding (get-scene) spots show it with remake_item_looks
  "item" (drops plugin), shelves through the shops plugin.
- Obj_TBox_A_04 spots holding a real item become a plain small chest (Obj_TBox_A_01, same model, a type each of
  their levels already places) with that item, and the A_04-only setting SerenityDistance is removed.
- Remake-only chests get added as new OoTR locations with rules at least as strict as the game
  (chests_locations.json 'new'). A location's 'also' chests, the same chest in another layout or the other outcome
  of one puzzle, get the same reward, and with 'share_flag' they take the main chest's instance hash so one opening
  counts for both. OoTR chests the remake doesn't have ('absent', proven from the files) go into OoTR's disabled
  set (before_build). Repeatable payouts and other non-checks are in 'not_checks', and the two chests whose route
  depends on collision the project can't read are in 'blockers'.
- Treasure Chest Game: the remake shuffles which chest of each room holds the key at run time (logic module
  MiniGame_SequentialChoiceTreasure_BoxShuffle: IsReplace = random F32 < 0.5), like OoT, so shuffle_tcgkeys
  vanilla describes it (OoTR itself then disables the room chests and the salesman). The reward chest takes any
  item and keeps its own minigame scene. tcg_requires_lens: OoTR's logic needs the Lens for the rooms either way,
  and the remake can't force a loss without it, which only makes the game easier than logic. 'remove' (Keysy,
  _chests_tcg.py): no per-room shuffle (F32_B -> -1.0), six keys at the start of every game, the room chests open
  once (IsEnableRepeatOpen off) with seed items, and the salesman hands over his seed item once. The keyed modes
  are a known blocker.
- Goron City signboard grotto: its prize and consolation chests hold the same item and the puzzle's guards are
  swapped (GC_PUZZLE), so only one outcome can ever happen.
- Dampe's race: in the remake the heart piece is a chest at the race goal, so OoTR's 'Graveyard Dampe Race
  Freestanding PoH' is paired with it (race scene kept). The race doesn't ask for the Hookshot anymore
  (_chests_dampe.py). The first win shows the first-prize chest until it's opened, and a later win under a minute
  shows the heart piece chest.
- correct_chest_appearances: chests keep their type (my rule), and the remake has one texture per chest model (a
  per-chest MimicTexture setting is declared but no AI or logic file ever reads it), so off only.
  invisible_chests: making chests invisible means changing their type to the Lens chest, so off only.
"""
import json
import os
import sys

from parity import _chests_scenes as scenes
from parity import _chests_dampe as dampe
from parity import _chests_tcg as tcg

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
import progressive  # noqa: E402

OWNS = {
    "junk_ice_traps": ("off", "normal", "on", "mayhem", "onslaught", "custom_count", "custom_percent"),
    "custom_ice_trap_percent": None,
    "custom_ice_trap_count": None,
    "ice_trap_appearance": ("major_only", "junk_only", "anything"),
    # remove (Keysy) and the keyed modes (keys found anywhere, counted by a saved Int): parity/_chests_tcg.py
    "shuffle_tcgkeys": ("vanilla", "remove", "regional", "overworld", "any_dungeon", "keysanity"),
    "tcg_requires_lens": (False, True),
}

ICE = "Ice Trap"
SMALL = ("Obj_TBox_A_01", "Obj_TBox_A_01_NoBake", "Obj_TBox_GlassTruth_A_01", "Obj_TBox_A_06", "Obj_TBox_A_06_NoBake")
BIG = ("Obj_TBox_A_02", "Obj_TBox_A_02_NoBake", "Obj_TBox_A_03", "Obj_TBox_A_03_NoBake")
A04 = "Obj_TBox_A_04"
# Scene IDs for the two ice-trap scenes, the last rows of config/scene_rows.json. Progressive items take rows from
# the front and skip rows a plan already rewrites. Their vanilla chests (Deku Tree compass and map, Navi chat scenes)
# keep their items and play the normal opening.
ICE_ROWS = {"small": "InsideTheDekuTree_GetCompass", "big": "InsideTheDekuTree_GetMap"}
APPEARANCE_CHEST_TYPES = True  # an ice trap's scene follows the chest type the appearance plugin gives the chest
# The Treasure Chest Game chests show a model of their contents. That's DropViewActor, which the chest AI creates by
# name in its ContentDisplay slot. Every room chest and the prize always name one (parity/_chests_tcg.py view_for). A
# room chest names its own vanilla view and the prize a vanilla view or display showing its item (tcg.ITEM_VIEWS,
# item views for all, view types of ours included).

# The chest's ContentDisplay slot is an open (wild) slot, so it only creates by name what's already loaded. The
# chest's own holder (its $parent, Obj_TBox) declares the chest-content displays, and the vanilla views stand in the
# room. Any other view is declared here as a named slot of the Treasure Chest Game chest's holder, so it loads with
# the chest. drops.look_ops does the same for the get-scene looks, and the drop-shaped looks we tried first created
# nothing.
TCG_HOLDER = tcg.HOLDER
TCG_DECLARED = set(tcg.VIEWS) | {"TBox_ArrowBundle_Medium", "Item_BombBundle_Small", "TBox_DekuNutBundle",
                                         "TBox_DekuSeedBundle", "Item_DekuStickBundle_Small", "Tbox_MagicJar_Large",
                                         "TBox_Rupee_Red"}
TCG_SLOT = {"DependencyWithHolder": 3707532803, "IsEnableModelAlphaFadeIn": False, "IsEnableSleepDeleteWithHolder": True,
            "IsEnableWaitCreateAndIgnition": False}

_cache = {}


def _tcg_view(item, actor, rid, settings, notes, name):
    """The Treasure Chest Game chest's DropViewActor for OoTR item `item` as contents `actor`. In tcg.view_for a room
    chest gets its own vanilla view and the prize a vanilla view or display, and tcg.ITEM_VIEWS has item views for
    both."""
    looks = (getattr(settings, "remake", None) or {}).get("remake_item_looks", "item")
    kinds = "item" if tcg.item_views() else "vanilla" if name in tcg.ROOMS else "display"
    view, why = tcg.view_for(item, actor, rid, looks, scenes.STAND_IN, kinds)
    notes.append(f"{name}: shows {view} ({why})")
    return view


_state = {}  # id(world) -> {"kept": set, "capable": set, "surplus": int}


def _load(name, path):
    if name not in _cache:
        _cache[name] = json.load(open(os.path.join(HERE, *path), encoding="utf-8"))
    return _cache[name]


def _locs():
    return _load("locs", ("data", "rando", "chests_locations.json"))


def _chest_map():
    return _load("chest_map", ("data", "rando", "chest_map.json"))["chests"]


def _catalog():
    if "catalog" not in _cache:
        _cache["catalog"] = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"),
                                                                 encoding="utf-8"))}
    return _cache["catalog"]


def _progressive():
    return _load("progressive", ("config", "progressive.json"))["items"]


def _location_scene(r):
    """True if the chest plays a story or minigame scene of its own (config/chest_rules.json 'location')."""
    import re
    ev = (r.get("extra") or {}).get("GetEventName")
    rules = _load("chest_rules", ("config", "chest_rules.json"))["get_events"]["location"]
    return bool(ev) and any(re.search(rx, ev) for rx in rules)


def ice_size(r):
    """'small' or 'big' if this remake chest can run an ice-trap scene on its own scene ID, else None. Other plugins ask
    this too when they need a chest that can take its own scene ID (parity/archipelago.py)."""
    if r.get("kind") != "chest" or _location_scene(r):
        return None
    return "small" if r.get("actor") in SMALL else "big" if r.get("actor") in BIG else None


# Every chest runs its trap. A chest that keeps its own story or minigame scene gets to the trap through that scene,
# the same way the dungeons plugin's item scene does (parity/dungeons.py STORY_ROUTES):
# - a big chest's story scene names the trap's scene ID in its transition (Ice Cavern, Jabu-Jabu, Water Temple, Spirit
#   Temple), or in a copy of it on its state's branch (Dampe's race)
# - Mido's house and the Treasure Chest Game send the trap's stand-in to the trap's scene from their entry
#   (_chests_scenes.story_dispatch)
# The Fairy Note chest takes the small chest's scene ID. Its own AI plays whatever scene its GetEventName names (the
# dungeons plugin's SCENE_EXTRA).
TRAP_EXTRA = {"Obj_TBox_A_01_memo11": "small"}


def _story_route(rid):
    """The dungeons plugin's story route of remake chest `rid` (STORY_ROUTES), or None."""
    dg = sys.modules.get("parity.dungeons")
    return (getattr(dg, "STORY_ROUTES", None) or {}).get(rid) if dg is not None else None


def trap_route(r):
    """(size, how) for a trap in remake chest record `r`, going by its final type. `how` is one of:
    - "row": the chest's own scene ID
    - "transition" / "branch": a step of its story scene names the trap's scene ID
    - "mido" / "tcg": its scene's entry sends the trap's stand-in on to the trap's scene
    (None, None) if it can't run any trap scene."""
    if r.get("kind") != "chest":
        return None, None
    size = ice_size(r)
    if size:
        return size, "row"
    if not _location_scene(r):
        size = TRAP_EXTRA.get(r.get("actor"))
        return (size, "row") if size else (None, None)
    route = _story_route(r["id"])
    if route is None:
        return None, None
    dg = sys.modules["parity.dungeons"]
    how = ("mido" if route is getattr(dg, "MIDO_ROUTE", None) else "tcg" if route.get("graph")
           else "branch" if route.get("branch") else "transition" if route.get("event") else None)
    return (route["chest"], how) if how else (None, None)


def trap_size(r):
    """'small' or 'big' for the trap scene chest record `r` runs (trap_route), or None."""
    return trap_route(r)[0]


def trap_stand_in(kind, how):
    """The item a chest holds for a trap of `kind` reached by `how` (trap_route). An ice trap on the chest's own scene
    ID, or on one its story scene names, keeps STAND_IN. Every other trap gets the stand-in for its kind."""
    return scenes.STAND_IN if kind == "ice" and how in ("row", "transition", "branch") else scenes.TRAP_STAND_INS[kind]


def _plan_name(item):
    """The plan's name for OoTR's progressive `item`. Seeds with the extras_items plugin's child wallet give the wallet
    three tiers under a different name."""
    ex = sys.modules.get("parity.extras_items")
    return ex.target_name(item) if ex is not None else item


def remake_actor(item):
    """OoTR item -> what a chest holds (config/item_map.json, progressive items by name). The songs/trade plugin's
    shared resolver gets the first say (songs_trade.hand_actor), which covers the masks and the Weird and Pocket Eggs
    hatched."""
    if item in _progressive():
        return _plan_name(item)
    st = sys.modules.get("parity.songs_trade")
    if st is not None and hasattr(st, "hand_actor"):
        got = st.hand_actor(item)
        if got:
            return got
    im = _load("item_map", ("config", "item_map.json"))
    if item in im["items"]:
        return im["items"][item]
    if item in im["junk_for"]:
        return im["junk_for"][item]
    raise ValueError(f"no remake item for OoTR's {item!r} (config/item_map.json)")


def _mine():
    """{OoTR name: remake id} for every location this plugin brings into play."""
    d = _locs()
    out = {n: v["remake"] for n, v in d["new"].items()}
    out.update({n: v["remake"] for n, v in d["paired"].items()})
    out.update(tcg.ROOMS)  # kept only when OoTR shuffles them (shuffle_tcgkeys 'remove'), vanilla mode disables them
    return out


# Goron City signboard grotto (HidingHole_Level_Hole_17). The prize chest (clear) and the consolation chest (fail) hold
# the same item, so only one outcome can ever happen. The clear trigger's guard (node 31 = this visit's outcome OR
# node 10) reads the 'clear' flag, and the fail trigger's guard (node 13 = this visit's outcome OR node 11) reads the
# 'faild' flag. We swap them, so a fail blocks every later clear and a clear blocks every later fail. The string-pool
# offsets in that file are 920 = ..._clear and 965 = ..._faild.
GC_GROTTO = "GC Grotto Chest"
GC_PUZZLE = [{"file": "Logic/HidingHole_Level_Hole_17_Prefab_e58a.logic.module.ainb", "offset": 0x4918, "i32": 965,
              "expect": 920},
             {"file": "Logic/HidingHole_Level_Hole_17_Prefab_e58a.logic.module.ainb", "offset": 0x4928, "i32": 920,
              "expect": 965}]


def _also(name):
    """(other remake chests that are this same location, whether they share the main chest's save flag)"""
    v = _locs()["new"].get(name) or _locs()["paired"].get(name) or {}
    return list(v.get("also", [])), bool(v.get("share_flag"))


def final_actor(rid):
    """The chest type this plugin gives remake chest `rid` no matter what it holds, or None. A real item in one of the
    remake's ice-trap chests (Obj_TBox_A_04, paired kind "a04") turns it into a plain Obj_TBox_A_01 (world_plan)."""
    if "a04" not in _cache:
        _cache["a04"] = {v["remake"] for v in _locs()["paired"].values() if v.get("kind") == "a04"}
    return "Obj_TBox_A_01" if rid in _cache["a04"] else None


def absent():
    """{OoTR location: evidence} for OoTR chests the remake doesn't have."""
    return dict(_locs().get("absent", {}))


def check_settings(settings):
    """Checks remake_trap_weights, the remake setting with the weights of the trap kinds every OoTR Ice Trap draws from
    (default {"ice": 1})."""
    w = (getattr(settings, "remake", None) or {}).get("remake_trap_weights", TRAP_DEFAULTS)
    if (not isinstance(w, dict) or set(w) - set(TRAP_KINDS) or not any(w.values()) or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 for v in w.values())):
        return [f"remake_trap_weights = {w!r}: a table of non-negative weights for {', '.join(TRAP_KINDS)}, at least "
                f"one above 0"]
    return []


def untested(settings):
    w = trap_weights(settings)
    out = []
    if set(w) - {"ice"}:
        out.append(f"chests: trap kinds {w} (shock/fire: Link's Condition_ElectricShock / Condition_Lava effects from "
                   f"a scene and one heart of damage; rupee: 10 rupees taken; chest kinds on their own reused scene IDs)")
    if settings.shuffle_tcgkeys not in ("vanilla", "remove"):
        out.append(f"shuffle_tcgkeys = {settings.shuffle_tcgkeys!r} (keys found counted in Rando_TcgKeyNum, copied into "
                   f"each game's key count)")
    if getattr(settings, "shuffle_ganon_bosskey", None) in ("on_lacs", "stones", "medallions", "dungeons", "tokens",
                                                            "hearts", "triforce"):
        out.append(f"shuffle_ganon_bosskey = {settings.shuffle_ganon_bosskey!r} (Ganon's boss lock opens on the "
                   f"condition / the Light Arrow cutscene gives the key)")
    return out


def before_build(settings):
    """OoTR chests we proved the remake doesn't have go into OoTR's disabled set. Logic never needs them and OoTR puts
    junk there. generate.lock_unpatchable locks their vanilla item so the item pool stays balanced."""
    gone = set(absent())
    settings.disabled_locations = sorted(set(settings.disabled_locations or []) | gone)


def keep_locations(world, settings):
    kept = set()
    for name in _mine():
        if name in tcg.ROOMS and settings.shuffle_tcgkeys == "vanilla":
            continue  # vanilla mode: OoTR disables the rooms
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.item is None and not loc.locked:
            kept.add(name)
    try:
        loc = world.get_location(tcg.SALESMAN)
        if loc.item is None and not loc.locked and settings.shuffle_tcgkeys != "vanilla":
            kept.add(tcg.SALESMAN)
    except KeyError:
        pass
    _state[id(world)] = {"kept": kept, "capable": set(), "surplus": 0}
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "CALL_LOCATIONS") and tcg.SALESMAN in kept:  # if he sells a dungeon item, his
        dg.CALL_LOCATIONS.add(tcg.SALESMAN)  # give step calls its credit entry (world_plan)
    return kept


def _dungeon(name):
    """A dungeon item the dungeons plugin gives through its credit entry in this run."""
    dg = sys.modules.get("parity.dungeons")
    return dg is not None and hasattr(dg, "call_target") and dg.dungeon_item(name) is not None


def _tcg_plain(item):
    """True if the salesman's hand-over (a copy of NpcCommon's Event67 with ReceiveItem) can give OoTR item `item`."""
    return (item.name not in _progressive() and item.name != ICE and item.type not in tcg.NOT_SOLD_TYPES
            and _sellable(item.name))


def _tcg_sold(item):
    """The Treasure Chest Game salesman can sell OoTR item `item` (_tcg_give)."""
    if getattr(item, "type", None) == "Shop":
        return False
    if _dungeon(item.name) or _tcg_plain(item):
        return True
    if item.name == ICE:
        return True  # this plugin's freeze (trap_call)
    st = sys.modules.get("parity.songs_trade")
    return st is not None and hasattr(st, "plain_give") and _route(st, item.name) is not None


def _route(st, name):
    """songs_trade.plain_give, but without asking for a tier entry, for the fill's rule. Returns ("call" | "actor", ...)
    or None."""
    if name in _progressive():
        return ("call", None)
    return st.plain_give(name, tcg.SALESMAN)


def _tcg_give(world, sold):
    """How the Treasure Chest Game salesman's sale gives OoTR item `sold`:
    - a dungeon item: its credit entry
    - items his own hand-over can give: that hand-over (a copy of Event67)
    - anything else goes through the songs/trade plugin's give router. That's an Ice Trap's freeze (trap_call), a
      progressive item's tier entry, the bean pack's or a soul's entry (plain_give), or a song, stone, medallion or
      token held up with the get routine (or its own hold-up, config/hold_up.json).
    Returns plan_part's (sale_actor, call, node)."""
    if _dungeon(sold):  # its credit entry, which the dungeons plugin's plan adds (it's built after this one)
        return None, sys.modules["parity.dungeons"].call_target(sold), None
    from Item import ItemInfo
    from types import SimpleNamespace
    info = ItemInfo.items.get(sold)
    if _tcg_plain(SimpleNamespace(name=sold, type=getattr(info, "type", "Item"))):
        return remake_actor(sold), None, None
    if sold == ICE:
        return None, trap_call(world, tcg.SALESMAN), None
    st = sys.modules["parity.songs_trade"]
    how = st.plain_give(sold, tcg.SALESMAN)
    if how[0] == "call":
        return None, how[1], None
    held = progressive.hold_node(how[1], None)  # an item Link can't hold up as it is
    return None, None, held or {"call": "Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff",
                                "params": {"ActorName": how[1]}, "next": None}


def _sellable(name):
    try:
        remake_actor(name)
        return True
    except ValueError:
        return False


def _capable(world, kept):
    """This plugin's OoTR locations (chest_map chests plus its own) where a trap can play. With the dungeons plugin's
    story routes that's every chest the remake has (trap_route)."""
    cat, out = _catalog(), set()
    for name, v in _chest_map().items():
        if v["mode"] in ("full", "group") and v.get("remake") and trap_size(cat[v["remake"]]):
            out.add(name)
    paired = _locs()["paired"]
    for name in kept:
        rid = _mine().get(name)
        if rid is None:
            continue
        if (paired.get(name) or {}).get("kind") == "a04" or all(trap_size(cat[c]) for c in [rid] + _also(name)[0]):
            out.add(name)
    return out


def _scene_locations():
    """{OoTR name: remake location id} for the core scene locations (config/rando_locations.json, same as
    generate.scene_locations). For an ice trap their give steps get replaced by a call to the freeze."""
    if "scene_locs" not in _cache:
        locs = _load("rando_locations", ("config", "rando_locations.json"))
        match = {x["ootr"]: x for x in _load("ootr_match", ("data", "ootr_match.json"))["ootr_locations"]}
        out = {}
        for name in locs.get("verified", []) + locs.get("testing", []):
            x = match.get(name)
            if x and x["status"] == "exact" and len(x["remake"]) == 1:
                out[name] = x["remake"][0]
        _cache["scene_locs"] = out
    return _cache["scene_locs"]


def scene_ice_spec(rid, location=None, world=None):
    """Reward spec for an ice trap at scene location id `rid`. Every give step becomes a call to the freeze
    (tools/make_patch.py scene_call_ops), or to the effect of whatever trap kind OoTR location `location` drew
    (remake_trap_weights, trap_call). The placeholder item is never handed over, but it has to differ from the vanilla
    item or make_patch thinks the reward is unchanged and skips it."""
    parts = [r for r in _catalog().values() if r.get("location") == rid or r["id"] == rid]
    if not parts:
        raise ValueError(f"{rid}: no catalogued give step")
    vanilla = {r["item"] for r in parts}
    call = trap_call(world, location) if world is not None and location else scenes.CALL
    return {"item": "Obj_Rupee_Blue" if "Obj_Rupee_Blue" not in vanilla else "Obj_Rupee_Green", "call": call}


def item_for(item, location, world):
    """Ice traps at the core scene locations (NPCs, songs, cutscenes, boss rewards, Great Fairies)."""
    if item != ICE:
        return None
    rid = _scene_locations().get(location)
    return scene_ice_spec(rid, location, world) if rid else None


# Trap kinds (remake_trap_weights, OoT3DR's traps)
# Every OoTR Ice Trap draws a kind by weight from its own generator, seeded with the seed and the location, so OoTR's
# draws aren't touched. The default {"ice": 1} draws nothing. A path records the kind it plays by asking trap_call (or
# trap_kind for a chest), so the spoiler can name the kind each spot gives (spoiler_names). A path that plays the ice
# trap no matter what was drawn (a disguised drop spot) never asks, and the spoiler just says Ice Trap there.
TRAP_KINDS = ("ice",) + scenes.TRAP_KINDS
TRAP_DEFAULTS = {"ice": 1}
REMAKE_KEYS = ("remake_trap_weights",)  # remake settings this plugin reads (generate.unknown_remake_settings)
TRAP_NAMES = {"ice": ICE, "shock": "Shock Trap", "fire": "Fire Trap", "rupee": "Rupee Trap"}
# Scene IDs the other kinds' chest scenes used to have. Every kind shares ICE_ROWS now, so these rows stay free for
# the progressive scenes. We keep the table so the drops plugin's row check still refuses them for its gifts.
TRAP_ROWS = {("shock", "small"): "DodongoCavern_GetCompass", ("shock", "big"): "DodongoCavern_GetMap",
             ("fire", "small"): "ForesetTemple_GetCompass", ("fire", "big"): "ForesetTemple_GetMap",
             ("rupee", "small"): "FireTemple_GetCompass", ("rupee", "big"): "FireTemple_GetMap"}
_traps = {}  # id(world) -> {"weights", "seed", "kind": {loc: kind}, "calls": {loc: kind}, "chests": {loc: kind},
#                            "hosts": set(kinds whose host graph is in the plan)}


def trap_weights(settings):
    w = (getattr(settings, "remake", None) or {}).get("remake_trap_weights", TRAP_DEFAULTS)
    return {k: float(v) for k, v in w.items() if v} if isinstance(w, dict) else dict(TRAP_DEFAULTS)


def _trap_state(world):
    st = _traps.get(id(world))
    if st is None:
        settings = world.settings
        st = _traps[id(world)] = {"weights": trap_weights(settings), "seed": str(getattr(settings, "seed", "")),
                                  "kind": {}, "calls": {}, "chests": {}, "hosts": set()}
    return st


def trap_kind(world, location):
    """The kind the Ice Trap at OoTR location `location` drew (always ice unless remake_trap_weights adds others)."""
    st = _trap_state(world)
    w = st["weights"]
    if set(w) <= {"ice"}:
        return "ice"
    if location not in st["kind"]:
        import random
        kinds = [k for k in TRAP_KINDS if w.get(k)]
        st["kind"][location] = random.Random(f"remake_trap:{st['seed']}:{location}").choices(
            kinds, weights=[w[k] for k in kinds], k=1)[0]
    return st["kind"][location]


def trap_call(world, location):
    """The scene entry a non-chest location's give steps call for its Ice Trap, for the kind it drew. We record it so
    the spoiler names it."""
    if world is None or not location:
        return scenes.CALL
    kind = trap_kind(world, location)
    if kind != "ice":
        _trap_state(world)["calls"][location] = kind
    return scenes.trap_call(kind)


def trap_host_ops(world, kind):
    """Plan event ops that add the effect of trap kind `kind` to Dm_SY_GetInEvent, the first time a plugin asks (chests
    or the songs/trade plugin). After that it's [], and it's always [] for ice since the chests plugin adds the
    freeze."""
    st = _trap_state(world)
    if kind == "ice" or kind in st["hosts"]:
        return []
    st["hosts"].add(kind)
    return scenes.trap_event_ops(kind, "host")


def trap_names(world):
    """{OoTR location: spoiler item name} for the Ice Traps that give another kind."""
    st = _traps.get(id(world)) or {}
    out = {n: TRAP_NAMES[k] for n, k in st.get("calls", {}).items()}
    out.update({n: TRAP_NAMES[k] for n, k in st.get("chests", {}).items() if k != "ice"})
    return out


def _install_spoiler_names(settings, world):
    """OoTR's spoiler log calls every trap "Ice Trap", so we write the real trap kinds in when the distribution fills
    its location records (every time the generator asks it to)."""
    dist = settings.distribution
    if getattr(dist.update_spoiler, "remake_trap_names", False):
        return
    original = dist.update_spoiler

    def update_spoiler(spoiler, output_spoiler, _original=original):
        _original(spoiler, output_spoiler)
        if not output_spoiler:
            return
        names = trap_names(world)
        records = dist.world_dists[world.id].locations
        for loc, name in names.items():
            rec = records.get(loc)
            if rec is not None and getattr(rec, "item", None) == ICE:
                rec.item = name
    update_spoiler.remake_trap_names = True
    dist.update_spoiler = update_spoiler


def takes_ice_trap(name):
    """Kept for plugins that still ask. Ice traps are only limited by item rules now."""
    return True


def before_fill(world, settings):
    _world["world"] = world
    st = _state.setdefault(id(world), {"kept": set(), "capable": set(), "surplus": 0})
    cat = _catalog()
    prog = _progressive()
    for name in st["kept"]:
        if name == tcg.SALESMAN:  # his sale gives anything the give router can (_tcg_give), only
            loc = world.get_location(name)  # OoTR's own rule stays (no Shop item outside shops)
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: _tcg_sold(item) and prev(location, item))
            continue
        rid = _mine()[name]
        r = cat[rid]
        # Progressive items only go where the patcher has a progressive scene. That's a small or big chest's family, the
        # Lens chest included, without a story or minigame scene. An A_04 spot holding a real item counts as the plain
        # small chest it turns into (final_actor).
        dg = sys.modules.get("parity.dungeons")  # a minigame chest the item scene is routed into gets its
        routed = dg is not None and rid in getattr(dg, "STORY_ROUTES", {})  # tier entry (dungeons.story_prog)
        if (progressive.scene_family(final_actor(rid) or r.get("actor")) is None or _location_scene(r)) and not routed:
            loc = world.get_location(name)
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: item.name not in prog and prev(location, item))
    st["capable"] = _capable(world, st["kept"])
    # Ice traps only go where they can be shown. Chests that can't run the ice-trap scene (they have their own story or
    # minigame scene, or their type has none) take other items, and generate.install_rule_fill sticks to that.
    names = set(st["kept"]) | {n for n, v in _chest_map().items() if v["mode"] in ("full", "group") and v.get("remake")}
    for name in sorted(names - st["capable"]):
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.locked or loc.item is not None:
            continue
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: item.name != ICE and prev(location, item))


def _ice_spec(r, note, world=None, kind="ice"):
    """(reward spec, size) for a trap of `kind` in remake chest record `r`. The spec has the stand-in the chest holds
    (trap_stand_in) and, when the chest has its own scene ID, the ice trap's scene ID for its size. Every kind shares
    that scene ID, since the ice entry sends the other kinds' stand-ins on (_chests_scenes.with_kinds). size is None
    when there's no trap scene."""
    ap = sys.modules.get("parity.appearance")
    if ap is not None and world is not None and r.get("kind") == "chest":
        r = dict(r, actor=ap.chest_actor(world, r["id"]))  # a look option may have changed the chest's type
    size, how = trap_route(r)
    spec = {"item": trap_stand_in(kind, how) if size else scenes.STAND_IN, "note": note}
    if spec["item"] != scenes.STAND_IN:
        spec["force"] = True  # a type of ours (_chests_scenes.stand_in_ops)
    if how == "row":
        spec["extra"] = {"GetEventName": ICE_ROWS[size]}
    return spec, size


def _trap_looks(world, settings, name):
    """The OoTR item a trap at location `name` shows where a chest shows what's inside (the Treasure Chest Game). That's
    the drops plugin's disguise (OoTR's looks_like_item, or one drawn from the seed's items), else ICE."""
    dr = sys.modules.get("parity.drops")
    if dr is None or not hasattr(dr, "_trap_shows"):
        return ICE
    return dr._trap_shows(settings, world, name, world.get_location(name).item) or ICE


def _trap_how(rid, world=None):
    """trap_route's "how" for remake chest `rid` as the seed types it (a look option may retype a chest)."""
    r = _catalog()[rid]
    ap = sys.modules.get("parity.appearance")
    if ap is not None and world is not None and r.get("kind") == "chest":
        r = dict(r, actor=ap.chest_actor(world, rid))
    return trap_route(r)[1]


_external = {}  # id(world) -> {remake chest id: OoTR location} for other plugins' chests holding an ice trap (ice_spec)
_external_specs = {}  # id(world) -> {remake chest id: the spec ice_spec returned (its scene row follows the kind)}


def ice_spec(rid, world, name=None):
    """Reward spec of an ice trap in remake chest `rid`, for another plugin's chest (the dungeons plugin's, say). It has
    the stand-in item and the ice-trap scene row for the chest's final type. None if the chest can't run the scene.
    It also registers the chest, so this plugin's world_plan adds that scene and keeps the row's vanilla chest out of
    the way. Call it after the fill and before the plan is built (after_fill)."""
    spec, size = _ice_spec(_catalog()[rid], f"{name or rid}: Ice Trap", world)
    if not size:
        return None
    _external.setdefault(id(world), {})[rid] = name
    _external_specs.setdefault(id(world), {})[rid] = spec
    return spec


def _scene_rows():
    return _load("scene_rows", ("config", "scene_rows.json"))["rows"]


def _claimed_rows(world):
    """Scene IDs (config/scene_rows.json) that other scenes take this seed, besides the progressive and trap-kind chest
    scenes. That's the ice-trap rows, the dungeons plugin's two chest scenes and its silver-rupee scene, the drops
    plugin's ZD grotto gift and the fairies plugin's fairy grottos. The silver and grotto rows have to be in the budget
    below too, or a seed with lots of progressive chest scenes and trap kinds can run make_patch out of rows."""
    rows = set(ICE_ROWS.values())
    dg = sys.modules.get("parity.dungeons")
    if dg is not None:
        rows |= set(getattr(dg, "ROWS", {}).values())
        sv = sys.modules.get("parity._dungeons_silver")
        if sv is not None and sv.DATA.get("scene_row"):
            rows.add(sv.DATA["scene_row"])
    for mod in ("parity.drops", "parity.fairies"):
        m = sys.modules.get(mod)
        if m is not None and hasattr(m, "claimed_rows"):
            rows |= set(m.claimed_rows(world))
    return rows


def _progressive_pairs(world, kept):
    """{(progressive item, chest scene family)} for the progressive chest scenes tools/make_patch.py needs this seed,
    each on its own scene ID. resolve_progressive makes one per item and chest family, the family being the one of the
    chest type the plan gives the chest."""
    cat, prog = _catalog(), _progressive()
    ap = sys.modules.get("parity.appearance")
    spots = [(n, v["remake"]) for n, v in _chest_map().items() if v["mode"] in ("full", "group") and v.get("remake")]
    spots += [(n, rid) for n in sorted(kept) if n != tcg.SALESMAN for rid in [_mine()[n]] + _also(n)[0]]
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "_kept"):
        spots += [(n, dg.WORLD["kept_chests"][n]) for n in sorted(dg._kept(world)) if n in dg.WORLD["kept_chests"]]
    pairs = set()
    for name, rid in spots:
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        r = cat.get(rid)
        if loc.item is None or loc.item.name not in prog or r is None:
            continue
        actor = final_actor(rid) or (ap.chest_actor(world, rid) if ap is not None else r["actor"])
        family = progressive.scene_family(actor)
        if family:
            pairs.add((_plan_name(loc.item.name), family))
    return pairs


def _chest_trap_kinds(world, entries, kept):
    """{OoTR location: kind} with the kind each chest holding an Ice Trap drew. `entries` is [(location, remake chest
    id)]. Every kind plays on the ice trap's two scene IDs (_chests_scenes.with_kinds), so every chest that runs a trap
    scene plays its own kind. With scene IDs per kind (TRAP_ROWS), a chest whose kind found none left next to the
    progressive scenes played the ice trap under its kind's name.
    A chest with no trap scene at all gives the stand-in, so it draws no kind (trap_route None, which only happens
    without the dungeons plugin's story routes). This is recorded before the spoiler gets written, so the spoiler names
    what each chest gives."""
    st = _trap_state(world)
    cat = _catalog()
    out = {}
    for name, rid in entries:
        size = _ice_spec(cat[rid], "", world)[1]
        out[name] = "ice" if not size or out.get(name) == "ice" else trap_kind(world, name)
    st["chests"].update(out)
    return out


TRAP_MIDO, TRAP_TCG = "Rando_TrapMido", "Rando_TrapTcg_{}"  # the story dispatch entries (_trap_scene_ops)
SCENE_TABLE = "RSDB/EventSetting.Product.111.rstbl.byml.zs"


def _trap_scene_ops(traps, cat, prog_chests, notes):
    """(events, byml, placements) that run every chest trap this seed. `traps` is {remake chest id: (kind, size, how,
    OoTR location)}, with `how` from trap_route.
    - "row", "transition", "branch": the ice trap's scene ID for the chest's size, and its entry. The entry first sends
      the other kinds' stand-ins on to their own chest entries (_chests_scenes.with_kinds). A story scene's transition,
      or its copy on the chest's branch, names that scene ID, the same way the dungeons plugin names its item scene
      (story_ops).
    - "mido" / "tcg": the entries of Mido's house and the Treasure Chest Game send the trap stand-ins to the traps'
      chest entries (_chests_scenes.story_dispatch), and the minigame's small chests to copies with its poses.
    With only ice traps, all on their chests' own scene IDs, this is exactly the plain ice-trap plan."""
    events, byml, placements = [], [], []
    by = {}  # how -> {size: set(kinds)}
    for rid, (kind, size, how, name) in traps.items():
        by.setdefault("row" if how in ("row", "transition", "branch") else how, {}).setdefault(size, set()).add(kind)
    order = lambda ks: sorted(ks, key=lambda k: (("ice",) + TRAP_KINDS).index(k))  # noqa: E731
    made = set()  # (kind, size) chest entries in the plan

    def entries(kind, size):
        if (kind, size) not in made:
            made.add((kind, size))
            return scenes.event_ops(size) if kind == "ice" else scenes.trap_event_ops(kind, size)
        return []
    for size, kinds in sorted(by.get("row", {}).items()):  # big, then small, the order the ice-only plan always had
        others = order(kinds - {"ice"})
        f = scenes.load()["files"][size]
        events += [{"file": f, "flowchart": f, "add_graph": e, "nodes": n, "start": s}
                   for e, n, s in scenes.with_kinds(size, others)]
        made.add(("ice", size))
        row, entry = ICE_ROWS[size], scenes.ENTRY[size]
        notes.append(f"ice-trap scene for {size} chests: {f}:{entry} on reused scene ID {row}" +
                     (f" (also the {', '.join(TRAP_NAMES[k] for k in others)} chests: their stand-ins go on to "
                      f"their own entries)" if others else ""))
        byml.append({"file": SCENE_TABLE, "replace_row": {"row": row, "copy_of": f, "set": {"EntryPointName": entry}}})
        # The vanilla chest that had the reused scene ID plays the normal opening, unless this plan gives it a scene of
        # its own (a trap or a progressive item).
        for r in cat.values():
            if (r["kind"] == "chest" and (r.get("extra") or {}).get("GetEventName") == row
                    and r["id"] not in traps and r["id"] not in prog_chests):
                for f2 in r["files"]:
                    placements.append({"file": f2, "hash": r["hash"], "remove": ["Dynamic.GetEventName"]})
                notes.append(f"{r['id']}: plays the normal opening (its scene ID {row} serves the ice-trap scene)")
        for k in others:
            events += entries(k, size)
    dg = sys.modules.get("parity.dungeons")
    for rid, (kind, size, how, name) in sorted(traps.items()):  # story scenes naming the trap's scene ID
        r = _story_route(rid)
        if how == "transition":
            events.append({"file": r["file"], "flowchart": r["file"], "event": r["event"], "param": "EventName",
                           "value": ICE_ROWS[size], "note": f"{rid}: its story scene runs the trap's chest scene"})
        elif how == "branch":
            graph = f"Rando_StoryTrap_{r['branch']}"
            events.append({"file": r["file"], "flowchart": r["file"], "add_graph": graph, "start": "t",
                           "nodes": {"t": {"copy": r["copy"], "params_over": {"EventName": ICE_ROWS[size]},
                                           "next": "@" + r["after"]}},
                           "note": f"{rid}: its state's branch runs the trap's chest scene"})
            events.append({"file": r["file"], "flowchart": r["file"], "event": r["branch"], "case": r["case"],
                           "next": f"{graph}_t"})
        if how in ("transition", "branch"):
            notes.append(f"{name}: {TRAP_NAMES[kind]} through its story scene ({r['file']})")
    for size, kinds in sorted(by.get("mido", {}).items()):
        r = dg.MIDO_ROUTE
        for k in order(kinds):
            events += entries(k, size)
        op = scenes.story_dispatch(r["file"], TRAP_MIDO, order(kinds), size, r["event"], r["event"])
        events += [op, {"file": r["file"], "flowchart": r["file"], "entry": r["entry"],
                        "next": f"{TRAP_MIDO}_{op['start']}"}]
        notes.append(f"Mido's house: {r['file']}:{r['entry']} sends the trap stand-ins to their chest scenes "
                     f"({', '.join(TRAP_NAMES[k] for k in order(kinds))})")
    for size, kinds in sorted(by.get("tcg", {}).items()):
        r = dg.TCG_ROUTES[size]
        mini = size == "small"
        for k in order(kinds):
            events += entries(k, size)
            if mini:
                e, n, s = scenes.mini(*scenes.small_entry_graph(k))
                events.append({"file": r["file"], "flowchart": r["file"], "add_graph": e, "nodes": n, "start": s})
        first = r.get("after") or r["vanilla"]  # the entry's first step, Navi's flag or the big chest's
        graph = TRAP_TCG.format(size)
        op = scenes.story_dispatch(r["file"], graph, order(kinds), size, r.get("after"), first, minigame=mini)
        events += [op, {"file": r["file"], "flowchart": r["file"], "entry": r["entry"], "next": f"{graph}_{op['start']}"}]
        notes.append(f"Treasure Chest Game ({size} chests): {r['file']}:{r['entry']} sends the trap stand-ins to their "
                     f"chest scenes ({', '.join(TRAP_NAMES[k] for k in order(kinds))})")
    return events, byml, placements


def world_plan(settings, world):
    cat, cm, d = _catalog(), _chest_map(), _locs()
    st = _state.get(id(world), {"kept": set(), "surplus": 0})
    kept = st["kept"]
    prog = _progressive()
    rewards, notes, prog_chests = {}, [], set()
    external = _external.pop(id(world), {})
    ext_specs = _external_specs.pop(id(world), {})
    # trap kinds (remake_trap_weights): every chest holding an Ice Trap draws its kind first
    entries = [(n, rid) for rid, n in sorted(external.items()) if n]
    entries += [(n, v["remake"]) for n, v in sorted(cm.items()) if v["mode"] in ("full", "group") and v.get("remake")
                and world.get_location(n).item.name == ICE]
    entries += [(n, rid) for n in sorted(kept) if n != tcg.SALESMAN and (d["paired"].get(n) or {}).get("kind") != "a04"
                and world.get_location(n).item.name == ICE for rid in [_mine()[n]] + _also(n)[0]]
    chest_kinds = _chest_trap_kinds(world, entries, kept)
    traps = {}  # remake chest id -> (kind, size, how, OoTR location) for every chest holding a trap (_trap_scene_ops)
    for rid in sorted(external):  # we set the trap scene, the reward belongs to the plugin that registered the chest
        kind = chest_kinds.get(external[rid], "ice")
        spec, size = _ice_spec(cat[rid], "", world, kind)
        traps[rid] = (kind, size, _trap_how(rid, world), external[rid])
        if rid in ext_specs:  # the other plugin's spec gets the stand-in for its kind (the scene ID is shared)
            ext_specs[rid].update({k: spec[k] for k in ("item", "force") if k in spec})

    # Chests chest_map already puts in play. An ice trap there gets the scene (generate.py already wrote the stand-in
    # item).
    for name, v in cm.items():
        if v["mode"] not in ("full", "group") or not v.get("remake"):
            continue
        item = world.get_location(name).item.name
        if item in prog:
            prog_chests.add(v["remake"])
        if item == ICE:
            kind = chest_kinds.get(name, "ice")
            spec, size = _ice_spec(cat[v["remake"]], f"{name}: {TRAP_NAMES[kind]}", world, kind)
            rewards[v["remake"]] = spec
            if size:
                traps[v["remake"]] = (kind, size, _trap_how(v["remake"], world), name)
            else:
                notes.append(f"{name}: ice trap in a chest with no trap scene ({cat[v['remake']]['actor']}): "
                             f"a blue rupee")

    tcg_part = None
    for name in sorted(kept):
        if name == tcg.SALESMAN:
            sold = world.get_location(name).item.name
            keyed = settings.shuffle_tcgkeys not in ("vanilla", "remove")
            actor, call, node = _tcg_give(world, sold)  # the give router
            tcg_part = tcg.plan_part(actor, keyed, call=call, node=node)
            notes.append(f"{name}: {sold} (sold once, then " + ("the keys found" if keyed else "six keys") +
                         " every game)")
            continue
        rid = _mine()[name]
        r = cat[rid]
        item = world.get_location(name).item.name
        kind = (d["paired"].get(name) or {}).get("kind", "new")
        note = f"{name}: {item}"
        if kind == "a04":
            trap = trap_kind(world, name) if item == ICE else None
            if trap == "ice":
                notes.append(f"{name}: Ice Trap in the remake's own ice-trap chest (left as it is)")
                continue
            if trap:  # A_04 turned into a plain small chest so it can run the other kind's trap scene
                spec, size = _ice_spec(dict(r, actor="Obj_TBox_A_01"), f"{name}: {TRAP_NAMES[trap]}", None, trap)
                rewards[rid] = dict(spec, extra=dict(spec.get("extra") or {}, Gyaml="Obj_TBox_A_01",
                                                     SerenityDistance=None))
                traps[rid] = (trap, size, "row", name)
                _trap_state(world)["chests"][name] = trap
                continue
            dg = sys.modules.get("parity.dungeons")
            if dg is not None and (dg.dungeon_item(item) is not None or dg.chest_scene_call(item, rid, world)):
                # Once final_actor makes it a plain chest it can use the dungeon-item scene.
                spec = dg.chest_reward(item, rid, world, name) or {"item": remake_actor(item)}
                rewards[rid] = dict(spec, note=note, extra=dict(spec.get("extra") or {}, Gyaml="Obj_TBox_A_01",
                                                                SerenityDistance=None))
                continue
            actor = remake_actor(item)
            if item in prog:  # resolve_progressive reads Gyaml below to pick the small chest scene
                prog_chests.add(rid)
            rewards[rid] = {"item": actor, "note": note,
                            "extra": {"Gyaml": "Obj_TBox_A_01", "SerenityDistance": None}}
            continue
        if item == ICE:
            trap = chest_kinds.get(name, "ice")
            for cid in [rid] + _also(name)[0]:
                spec, size = _ice_spec(cat[cid], f"{name}: {TRAP_NAMES[trap]}" if trap != "ice" else note, world,
                                       trap)
                if size and (name in tcg.ROOMS or kind == "tcg_reward"):  # shows the trap's disguise
                    view = _tcg_view(_trap_looks(world, settings, name), spec["item"], cid, settings, notes, name)
                    spec = (dict(tcg.room_spec(spec["item"], spec["note"], view), force=True) if name in tcg.ROOMS
                            else dict(spec, extra={"DropViewActor": view}))  # disguise shown, once for a room chest
                rewards[cid] = spec
                if size:
                    traps[cid] = (trap, size, _trap_how(cid, world), name)
            continue
        ap = sys.modules.get("parity.archipelago")  # another Archipelago player's item gets the hidden stand-in
        if ap is not None and item in ap.PLACEHOLDER_NAMES:  # and the location's found scene (parity/archipelago.py)
            for cid in [rid] + _also(name)[0]:
                rewards[cid] = ap.item_for(item, name, world)
            continue
        dg = sys.modules.get("parity.dungeons")
        story_prog = dg is not None and hasattr(dg, "story_prog") and dg.story_prog(item, name)
        if dg is not None and (dg.dungeon_item(item) is not None or dg.chest_scene_call(item, rid, world)
                               or story_prog):
            # Carriers and minigame tiers use the item scene. A dungeon's own chest can just hold the plain item.
            for cid in [rid] + _also(name)[0]:  # the dungeons plugin's plan adds the scene, it runs after this one
                spec = dg.item_for(item, name, world) if story_prog else dg.chest_reward(item, cid, world, name)
                if spec is None:
                    kind_, dungeon = dg.dungeon_item(item)
                    spec = {"item": dg.MODEL[kind_] if dungeon == "Thieves Hideout" else remake_actor(item)}
                if name in tcg.ROOMS:  # a Treasure Chest Game room: its contents (given once) and its view
                    view = _tcg_view(item, spec["item"], cid, settings, notes, name)
                    spec = dict(tcg.room_spec(spec["item"], note, view),
                                **({"force": True} if spec.get("force") else {}))
                elif kind == "tcg_reward":
                    spec = dict(spec, extra=dict(spec.get("extra") or {}, DropViewActor=_tcg_view(
                        item, spec["item"], cid, settings, notes, name)))
                rewards[cid] = dict(spec, note=note)
            continue
        actor = remake_actor(item)
        if item in prog:
            if progressive.scene_family(r.get("actor")) is None or _location_scene(r):
                # Only happens if OoTR's fill put it here despite the item rule (before_fill keeps it out).
                actor = prog[item]["tiers"][0]
                notes.append(f"{name}: {item} where no tier can be decided: gives {actor}")
            else:
                prog_chests.add(rid)
        spec = {"item": actor, "note": note}
        if name in tcg.ROOMS:
            spec = tcg.room_spec(actor, note, _tcg_view(item, actor, rid, settings, notes, name))
        if kind == "tcg_reward" and actor != r["item"]:
            spec["extra"] = {"DropViewActor": _tcg_view(item, actor, rid, settings, notes, name)}
        rewards[rid] = spec
        if rid in prog_chests:
            prog_chests.update(_also(name)[0])

    # A location's other chests (another layout's copy, or the other outcome of a puzzle) get the same reward. Copies
    # that share the main chest's save flag take its instance hash. Placement edits run after the reward edits.
    placements = []
    for name in sorted(kept):
        rid = _mine().get(name)
        if rid is None:
            continue
        others, share = _also(name)
        for cid in others:
            if cid not in rewards and rid in rewards:
                rewards[cid] = dict(rewards[rid], note=f"{rewards[rid].get('note', name)} (also {cid})")
            if share:
                for f in cat[cid]["files"]:
                    placements.append({"file": f, "hash": cat[cid]["hash"], "set": {"Hash": cat[rid]["hash"]}})
                notes.append(f"{name}: {cid} shares {rid}'s save flag (instance hash)")
    plan = {"rewards": rewards, "_tcg_item_views": tcg.item_views()}  # the view kinds, for _chests_tcg.verify_rooms
    events, byml, binary = [], [], []
    if any(n in tcg.ROOMS for n in kept) or tcg_part:
        keyed = settings.shuffle_tcgkeys not in ("vanilla", "remove")
        part = tcg_part or tcg.plan_part("Obj_MiniGame_SmallKey", keyed)
        events += part["events"]
        binary += part["binary"]
        for k in ("gamedata", "_gaps", "text"):  # the sale flag, plus key count, message and audit note in keyed modes
            if k in part:
                plan[k] = part[k]
        if any(n in tcg.ROOMS for n in kept):  # room chests keep the game's AI and give their seed item once
            notes.append("Treasure Chest Game rooms: the game's own chest AI; each chest's first opening is saved "
                         "(IsTreasureBoxOpen.<hash>), so it gives its seed item once and stands open in later games")
            pp = tcg.partner_part(rewards)  # a hit whose partner stands open raises no pop flag (_chests_tcg)
            events += pp["events"]
            gd = plan.get("gamedata")
            plan["gamedata"] = ([] if gd is None else [gd] if isinstance(gd, dict) else list(gd)) + [pp["gamedata"]]
            plan["_tcg_partner"] = pp["_tcg_partner"]
            notes.append("Treasure Chest Game rooms: a hit whose partner chest stands open (taken in an earlier game) "
                         "raises no pop flag, so no chest of another room or the prize pops open")
        notes.append(f"Treasure Chest Game ({settings.shuffle_tcgkeys}): no per-room shuffle, the keys found every "
                     f"game, room chests open once" if keyed else
                     "Treasure Chest Game (Keysy): no per-room shuffle, six keys every game, room chests open once")
    if GC_GROTTO in kept:
        binary += GC_PUZZLE
        notes.append(f"{GC_GROTTO}: signboard puzzle outcomes made exclusive (one prize per file)")
    # Dampe's race counts wins without asking for the Hookshot (_chests_dampe.py)
    events += dampe.event_ops(skip_phases=bool(getattr(world.settings, "skip_some_minigame_phases", False)))
    # Every seed. The ClearCount routing can run the first-race path after the Forest Temple, so we stop that path from
    # moving SageOfForest back (Event132 Step03, Event97 Step02). The race timer is always hidden too.
    events += dampe.fix_ops(skip_phases=bool(getattr(world.settings, "skip_some_minigame_phases", False)))
    gaps_fix = {"dampe_fix": {"skip_phases": bool(getattr(world.settings, "skip_some_minigame_phases", False))}}
    notes.append("Dampe's race: first win -> first-prize chest until opened, later wins -> heart piece chest "
                 "(no Hookshot check)")
    ev, by, pl = _trap_scene_ops(traps, cat, prog_chests, notes)
    events += ev
    byml += by
    placements += pl
    # The shared freeze entries other kinds of location call (NPC and scene rewards, scrubs, the carpet salesman, cows,
    # frogs...). Added once here whenever a non-chest location holds an ice trap.
    chest_names = ({n for n, v in cm.items() if v["mode"] in ("full", "group") and v.get("remake")} | set(kept)
                   | {n for n in external.values() if n})
    elsewhere = sorted(loc.name for loc in world.get_locations()
                       if loc.item is not None and loc.item.name == ICE and loc.name not in chest_names)
    if elsewhere:
        events += scenes.event_ops("host")
        notes.append(f"freeze entry {scenes.CALL} for {len(elsewhere)} ice trap(s) outside chests")
        shop_locs = _load("shop_map", ("data", "rando", "shop_map.json"))["locations"]
        kinds = {(shop_locs.get(n) or {}).get("kind") for n in elsewhere if (shop_locs.get(n) or {}).get("mode") == "full"}
        # Scrubs keep the vanilla one-time sale with the ice-trap marker, and make_patch's scrub intercept does the
        # freeze inside the vanilla entry. Copying the sale with scenes.event_ops("scrub") left the scrub actor unbound.
        # The carpet salesman gets a copy of his sale for the trap kind his Ice Trap drew (tools/rando/shops.py _ice_ops
        # calls the kind's root through the shops plugin's trap_call).
        merchant = sorted({trap_kind(world, n) for n in elsewhere if (shop_locs.get(n) or {}).get("mode") == "full"
                           and (shop_locs.get(n) or {}).get("kind") == "merchant"}, key=TRAP_KINDS.index)
        if "ice" in merchant:
            events += scenes.event_ops("shop")
        for kind in (k for k in merchant if k != "ice"):
            f = scenes.load()["files"]["shop"]
            events += [{"file": f, "flowchart": f, "add_graph": e, "nodes": n, "start": s}
                       for e, n, s in scenes.shop_kind_graphs(kind)]
    # Other trap kinds the core scene locations drew (item_for runs before the plugins' plans). The songs/trade plugin
    # adds the ones it needs itself and finish_plan adds any later plugin's (trap_host_ops gives each kind only once).
    for kind in sorted(set(_trap_state(world)["calls"].values()), key=TRAP_KINDS.index):
        events += trap_host_ops(world, kind)
    if set(trap_weights(settings)) - {"ice"}:
        _install_spoiler_names(settings, world)
        notes.append(f"trap kinds {trap_weights(settings)}: chests {sorted(chest_kinds.values())} (every kind on the "
                     f"ice trap's scene IDs, told apart by its stand-in)")
    if any(loc.item is not None and loc.item.name == ICE for loc in world.get_locations()):
        plan["_ice_sensor"] = True  # the freeze creates the ice-trap attacker (generate.py adds its files once)
        notes.append("ice traps: the freeze scene creates ConditionSensorActor, the ice-trap attacker "
                     "(the remake's ice-trap chest's own attack: tools/rando/drops.py ice_sensor_ops)")
    views = sorted({(s.get("extra") or {}).get("DropViewActor") for s in rewards.values() if isinstance(s, dict)}
                   - {None, ""} - TCG_DECLARED)
    if views:  # the Treasure Chest Game's other content models load with the chest (TCG_HOLDER)
        plan["packs"] = [{"pack": "*", "file": TCG_HOLDER, "set": {
            f"ActorHoldSettings.{a}": dict(TCG_SLOT, Actor=f"Work/Actor/{a}.engine__actor__ActorParam.gyml")
            for a in views}}]
        notes.append(f"Treasure Chest Game: the chest's holder declares {', '.join(views)} (loaded with the chest)")
        made = tcg.view_types_part(views)  # the view types we add for it
        if made["new_files"]:
            plan["new_files"] = made["new_files"]
            plan["packs"] += made["packs"]
            byml += made["byml"]
    stands = sorted({(rewards.get(rid) or ext_specs.get(rid) or {}).get("item") for rid in traps}
                    & set(scenes.TRAP_STAND_INS.values()))
    if stands:  # the traps' stand-ins (_chests_scenes.stand_in_ops)
        made = scenes.stand_in_ops(stands)
        plan["new_files"] = plan.get("new_files", []) + made["new_files"]
        plan["packs"] = plan.get("packs", []) + made["packs"]
        byml += made["byml"]
        notes.append(f"trap stand-ins (copies of {scenes.STAND_IN}): {', '.join(stands)}")
    if events:
        plan["events"] = events
    if byml:
        plan["byml"] = byml
    if placements:
        plan["placements"] = placements
    if binary:
        plan["binary"] = binary
    # Trap-chest spots we turn into a plain chest have no IsTreasureBoxOpen member for their hash, so the chest would
    # never save being opened. It'd be closed again on the next visit and give its item again, and it couldn't be
    # tracked. So each one gets a saved member, which the chest's AI then writes and reads (tools/rando/chest_flags.py,
    # read back by in_game_check).
    import chest_flags  # tools/rando/chest_flags.py
    opened = chest_flags.converted_traps(rewards)
    if opened:
        gd = plan.get("gamedata")
        plan["gamedata"] = ([] if gd is None else [gd] if isinstance(gd, dict) else list(gd)) + [
            chest_flags.struct_op(opened)]
        notes.append(f"{len(opened)} trap-chest spot(s) holding an item save being opened "
                     f"({chest_flags.STRUCT} members {', '.join(map(str, opened))})")
        # Their logic module gets a plain, unlocked chest node and each converted spot is bound to it. A spot that keeps
        # its trap keeps the trap node, and any mix works (chest_flags.trap_module_op).
        plan["ainb"] = list(plan.get("ainb") or []) + [chest_flags.trap_module_op(opened)]
        plan["groups"] = list(plan.get("groups") or []) + chest_flags.trap_rebind_ops(opened)
        notes.append(f"trap-chest module {chest_flags.TRAP_MODULE}: {len(opened)} of "
                     f"{len(chest_flags.TRAP_HASHES)} spots bound to its plain chest node "
                     f"{chest_flags.TRAP_CHEST_INSTANCE} (unlocked), the others keep the trap")
    plan["_notes_chests"] = notes
    plan["_gaps"] = dict(plan.get("_gaps") or {}, **gaps_fix)  # the Dampe fix's read-back (parity/_gaps_check.py)
    return plan


def after_fill(world, settings):
    """The progressive chest scenes this fill needs have to fit in the scene IDs that are left. config/scene_rows.json
    can't grow and make_patch gives each (item, chest family) its own row, so a fill that needs more is tried again."""
    from Fill import ShuffleError
    kept = _state.get(id(world), {}).get("kept", set())
    free = [r for r in _scene_rows() if r not in _claimed_rows(world)]
    need = _progressive_pairs(world, kept)
    if len(need) > len(free):
        raise ShuffleError(f"{len(need)} progressive chest scenes need a scene ID, only {len(free)} left")


_world = {}  # "world": the seed's world (before_fill), for give steps built without it (trap_call_at)


def trap_call_at(location):
    """trap_call for OoTR location `location` in this seed's world, for the drops and fairies plugins' scene targets."""
    return trap_call(_world.get("world"), location)


def finish_plan(settings, plan, cfg):
    """Runs once every plugin's plan is in (generate.main). Adds the effect entry of each trap kind a later plugin's
    location drew (trap_host_ops, once each), and the shock and fire traps' attackers (_chests_scenes.kind_sensor_ops).
    Chests, scene locations, drop spots, the resident get scene and received Archipelago traps all create those
    attackers. They end on the "You are a FOOL!" entry, so that gets added too if no ice trap brought it (fool_ops)."""
    world = _world.get("world")
    st = _traps.get(id(world)) if world is not None else None
    asked = set(plan.pop("_trap_sensors", None) or [])
    kinds = set(asked) | set((st or {}).get("calls", {}).values()) | set((st or {}).get("chests", {}).values())
    if st is not None:
        for kind in sorted(set(st["calls"].values()), key=TRAP_KINDS.index):
            plan["events"] = plan.get("events", []) + trap_host_ops(world, kind)
    sensors = sorted(k for k in kinds if k in scenes.SENSORS)
    if not sensors:
        return
    parts = [scenes.kind_sensor_ops(k) for k in sensors]
    if not any(op.get("add_graph") == scenes.FOOL_ENTRY for op in plan.get("events", [])):
        parts.append(scenes.fool_ops())
    for part in parts:
        for section, value in part.items():
            plan[section] = plan.get(section, []) + value
    plan.setdefault("_notes_chests", []).append(
        f"trap attackers: {', '.join(scenes.SENSORS[k] for k in sensors)} (the ice-trap attacker with the "
        f"{', '.join(k for k in sensors)} element; _chests_scenes.kind_sensor_ops)")
