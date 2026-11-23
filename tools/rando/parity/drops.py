"""Parity plugin: Gold Skulltula tokens, freestanding items, heart pieces and containers, pots, crates, flying pots,
beehives, wonder items, and the remake's own grass, rocks, boulders, palm fruit and decorations.

Data: tools/rando/drops.py builds data/rando/drop_map.json and data/rando/logic/drops.json. In the drop map, "drops"
pairs OoTR locations with remake objects or marks them proven absent, and "new" makes every other remake object a
new OoTR location. The logic file has the new locations' regions and rules, with the absent OoTR locations removed.

Settings: OoTR's tokensanity / shuffle_freestanding_items / shuffle_pots / shuffle_crates / shuffle_beehives /
shuffle_empty_* cover OoTR's locations and the remake's objects of the same kind (OoTR decides which it shuffles).
The remake's own objects follow remake settings (off, dungeons, overworld, all; default off):
  remake_shuffle_grass     cuttable grass (Obj_Plant_Grass_A_01/A_03), the first cut drops the item
  remake_shuffle_rocks     small rocks you lift (Obj_LiftRock_A_01/A_03)
  remake_shuffle_boulders  bomb boulders (Obj_BrokenRock_A_01/A_02)
  remake_shuffle_misc      Gerudo palm fruit and cow-skull / sign decorations
  remake_shuffle_bushes    False / True (default False), Ship of Harkinian's Shuffle Bushes. The 13 Hyrule Field
                           bushes (Land_kokiri_Plant_A_02_DropFixed_03, one per spot in each age's layout), cut with
                           anything but a stick, the slingshot or a roll. In vanilla they drop bugs on every cut.
                           They have no AI and no save flag, so the patch gives the type an AI
                           (drops.NEW_AI_DROPPERS) and each spot a borrowed flag. A shuffled bush gives its item once
                           (through the get scene) and is an ordinary bug bush from the next load on.
remake_drop_contents (junk, safe, all = default): what a drop spot can hold. "all" is how OoTR and Ship of Harkinian
behave, a shuffled pot holds anything (my rule). In vanilla only a Gold Skulltula's token saves its dropper on
pickup. Any other object is "checked" when it breaks, so an item left behind would be gone.
  junk  rupees, hearts, fairies, shields, a skulltula's token, and heart pieces/containers on placed-pickup spots.
  safe  junk plus the progression items whose second pickup changes nothing (Goron/Zora Tunic, Fire Arrows). Their
        object keeps its vanilla respawn, so they come back until taken and can never be lost.
  all   safe, plus OoTR's "checked on pickup" (drops.pickup_save_ops). Pots
        (Obj_Pot_A_01..08), small crates (A_03), grass (A_01/A_03), small rocks (A_01/A_03) and Gold Skulltulas hand
        their save flag to what they drop and stop saving when broken, and the pickup saves it when taken. Those
        spots then take every item that has a world pickup: heart pieces and containers, small keys (own dungeon),
        tokens, Ruto's Letter, rupees. Never lost (the object comes back until its item is taken) and never
        repeated. They also take any other item the get scene can give (songs, medallions, stones, equipment,
        bottles, trade items, dungeon items through the dungeons plugin's credit entries, ammo, but no shop items),
        like Ship of Harkinian does. That's a scene drop (_scene_drop_spot, drops.py "scene drops"). The object
        drops the disguise carrier with a tag for that item (its placement's Drop__RandoTag, handed to the drop),
        the carrier shows the item and the get-scene hook gives it. Other spots keep the "safe" rules. It's the
        default because OoTR and Ship of Harkinian put any item in a shuffled pot.
A placed (freestanding) pickup saves its own flag when taken, so those spots take any pickup type their level
already places, heart pieces and containers included. A type that's new to a level broke Kokiri Forest.
  remake_reset_group_objects  one_time | respawn. Objects in a SupplyItemResetSystemActor group (dungeons, Kakariko,
        Market...) come back whenever it fires, so they could only hold repeatable junk. "one_time" (default, OoTR's
        one-time pot checks): every one holding a shuffled item leaves its group (drops.ungroup_ops) and its flag is
        made permanent, so it takes what any other pot takes. "respawn": they stay in their group.
  remake_item_looks  item | heart: what a get-scene spot looks like (heart piece, heart container, freestanding
        key, touch pickup turned into a heart). "item" (default, since OoTR always draws the real model) shows the
        item it gives (drops.item_display / look_ops). The pickup hides its own model and creates the item's
        display model in a holder slot bound to it. Progressive items show the next tier, ice traps their
        looks_like_item, and items without a display model keep the pickup's look. "heart" keeps the pickup's own
        look. The Treasure Chest Game chests follow this setting too (chests plugin, DropViewActor).
Placed heart pieces and heart containers (the 14 freestanding PoH and the 8 boss hearts OoTR always shuffles) take
any item, whatever remake_drop_contents says. Taking one plays the shared get scene, and the get-scene hook
(tools/rando/parity/_songs_trade_lake.py, the songs_trade plugin) branches on the spot's tag. The pickup's event AI
answers that from the placement's instance name (tools/rando/drops.py get_scene_ops). The spot keeps its heart
model. The scene hides it, holds up and gives the seed's item (progressive tiers, dungeon items through the dungeons
plugin's credit entries, ice traps through the chests plugin's freeze) and requests the pickup's death like the
vanilla scene does, which saves the placement's flag.
An item a type swap can show (a rupee where the level places rupees) still swaps the type. An item whose pickup is
the spot's own (Piece of Heart at a heart-piece spot, Heart Container at a boss heart) never goes there, since it
would look vanilla. The 8 other placed pickups whose level file places a heart work the same way (LH Underwater
Green Rupee 1/2 and six remake-only Deku Tree rupees and hearts, drop-map get_scene "as"). An item no type swap
shows turns them into that heart, given through the get scene. Rupees and hearts are the exception and keep the
rupee look. Without the songs_trade plugin there's no hook, so those spots keep the type-swap rules.
Spots that could only ever give their own kind. These are remake
settings. The first value is the old behaviour and the default is the last one:
  remake_empty_object_contents  vanilla | nothing | junk | ice_trap: what OoTR's "Nothing" gives in an object
        (shuffle_empty_pots / shuffle_empty_crates, one per empty object). "vanilla" leaves the object's own drop,
        so it plays like the vanilla game (listed in seed.json). "nothing" is OoTR's GI_NOTHING: the object gets
        the empty drop table ("None", which its type lists). Types without one (bug grass and rocks, cow-skull and
        sign decorations, flying pots) and objects that are already empty in vanilla don't take "Nothing". "junk"
        is a random rupee other than the object's own fixed drop. "ice_trap" (default) is a disguised ice trap. The
        object drops drops.DISGUISE_ACTOR, which shows a random item from OoTR's ice-trap look pool
        (_disguise_looks). Taking it plays the get scene, which freezes Link with the chests plugin's freeze
        through the songs_trade get-scene hook. "junk" and "ice_trap" put the real item in the spoiler.
        OoTR's "Nothing" anywhere else (chests, NPCs, scrubs, shops, the hideout jails) would give
        config/item_map.json's junk_for green rupee. "ice_trap" makes it a real Ice Trap where the spot's rules
        take one, and otherwise (and with "junk") a named junk item. That includes heart spots and scene gifts
        (_nothing_ok, my rule: "OoTR's Nothing goes anywhere"). "nothing" keeps it off every spot except this
        plugin's: an empty-able object gets the empty table, and a heart spot, scene gift, scene drop or flagless
        drop plays its get scene and gives nothing (_scene_target {"nothing"}). "vanilla" leaves it alone.
        With remake_avoid_vanilla_spots on (off by default), items whose pickup is the object's own fixed drop stay
        away from it. Bomb boulders, decorations and flying pots drop a green rupee by themselves (drop_map
        "dropper_tables").
  remake_drop_ice_traps  classic | disguised: an OoTR Ice Trap at a drop spot is the level's keese or a stand-in
        pickup (classic), or the disguised trap that really freezes Link (default). With "disguised", placed
        pickups only take ice traps through the get scene.
  remake_touch_pickups  own_kind | any: with "any" (default) the auto-collected rupees and hearts whose file places
        no other pickup (ZF Bottom, Dampe's race, Deku Tree, Fire Temple) become the heart piece or heart container
        their stage places (drop_map "stage_get_scene"), and they give any item through the get scene.
  remake_freestanding_keys  vanilla | any (default any): the Bottom of the Well and Shadow Temple freestanding keys
        take any item through the key's own get scene, and their room logic saves them (drop_map "key_spots").
Spots that a scene of their own gives (drop_map "scene_gifts"). Both need the
songs_trade plugin because they use its give steps, and without it they fall back to the first value:
  remake_gc_pot_prize  vanilla | any: GC Pot Freestanding PoH. With "any" (default) the pot's heart-piece scene
        removes the dropped heart piece and gives the seed's item, and Link holds it up. The pot's save flag
        GoronLargePot_IsGetHeartPiece gets set in that scene and keeps the pot from ever offering it again. Any
        item.
  remake_zd_grotto_rupees  vanilla | gift: ZD Storms Grotto Blue Rupee 1-6, auto-collected blue rupees that only
        ever gave rupees. With "gift" (default) you get the six items the first time you enter the grotto (the
        first held up, the others in the get window) and the rupees are deleted. OoTR's rule for all six is True
        inside the grotto's region, so that's exactly when the logic counts them. Any item.
Logic: the age rule of single-age objects, OoTR's group rule for pairs whose order is unknown, and the region rules
from data/rando/drops_regions_*.json for new locations. Ammo goes to drop spots like in OoTR. At a checked drop spot,
ammo that has a touch pickup of its own drops as itself and is taken on touch, with the game's count popup and
OoTR's amount (drops AMMO AS ITSELF, AMMO AMOUNTS). Bombchus and flagless spots go through the carrier and the get
scene. Without its container, ammo gives a Blue Rupee or nothing (remake_ammo_without_container, parity/_ammo.py,
drops AMMO RUPEE).
Bugs (every seed): OoTR's bug locations (Bug Shrub, Bug Rock, Wandering Bugs) are replaced by the remake's sources
that provably still give bugs. That's the bug grass tufts and bug rocks left unshuffled, each in its own region, and
the Hyrule Field bushes (drop_map "bugs", _bug_logic). Foliage grass isn't counted because it has no region in the
files.
no_collectible_hearts (OoTR's Hero Mode): every heart a drop would give becomes a green rupee, like OoTR does. That
covers the global drop data, every drop table, placements that drop a heart and their twins, and the Deku Tree
scrubs' scene. Placed hearts and seed items stay. See _drops_hearts.py.
The Deku Tree scrubs (every seed): a scrub whose heart or rupee the seed uses skips its heart-or-rupee scene. That
scene would name pickups the plan renamed and delete one location's item. The scrub just runs away and both stay
(_drops_scrubs.py).
"""
import json
import random
import sys

import drops as drop_tools  # tools/rando/drops.py

LEVELS = ("off", "dungeons", "overworld", "all")
OWNS = {
    "tokensanity": LEVELS,
    "shuffle_freestanding_items": LEVELS,
    "shuffle_pots": LEVELS,
    "shuffle_crates": LEVELS,
    "shuffle_empty_pots": (False, True),
    "shuffle_empty_crates": (False, True),
    "shuffle_beehives": (False, True),
    # The remake has none of OoTR's wonder items (there's no invisible item actor), so this setting changes nothing.
    "shuffle_wonderitems": (False, True),
    # gold_skulls_ignore_daytime and fix_broken_drops belong to the story plugin (parity/_gaps_drops.py)
    # OoTR's Hero Mode: heart drops from enemies and objects become green rupees (_drops_hearts.py)
    "no_collectible_hearts": (False, True),
}
REMAKE_SETTINGS = {
    "remake_shuffle_grass": LEVELS, "remake_shuffle_rocks": LEVELS, "remake_shuffle_boulders": LEVELS,
    "remake_shuffle_misc": LEVELS, "remake_drop_contents": ("junk", "safe", "all"),
    "remake_empty_object_contents": ("vanilla", "nothing", "junk", "ice_trap"),
    "remake_drop_ice_traps": ("classic", "disguised"),
    "remake_touch_pickups": ("own_kind", "any"),
    "remake_freestanding_keys": ("vanilla", "any"),
    "remake_gc_pot_prize": ("vanilla", "any"),
    "remake_zd_grotto_rupees": ("vanilla", "gift"),
    "remake_item_looks": drop_tools.ITEM_LOOKS,
    "remake_reset_group_objects": ("one_time", "respawn"),
    # Ship of Harkinian's Shuffle Trees / Icicles / Red Ice
    "remake_shuffle_trees": LEVELS, "remake_shuffle_icicles": LEVELS, "remake_shuffle_red_ice": LEVELS,
    "remake_shuffle_bushes": (False, True),  # Ship of Harkinian's Shuffle Bushes (On/Off)
}
REMAKE_DEFAULTS = {"remake_drop_contents": "all", "remake_empty_object_contents": "ice_trap",
                   "remake_drop_ice_traps": "disguised", "remake_touch_pickups": "any", "remake_freestanding_keys": "any",
                   "remake_gc_pot_prize": "any", "remake_zd_grotto_rupees": "gift", "remake_item_looks": "item",
                   "remake_reset_group_objects": "one_time", "remake_shuffle_bushes": False}
# scene gifts (drop_map "scene_gifts"): group -> (setting, value that turns it on)
GIFT_SETTINGS = {"gc_pot": ("remake_gc_pot_prize", "any"), "zd_grotto": ("remake_zd_grotto_rupees", "gift")}
JUNK_RUPEES = ("Rupee (1)", "Rupees (5)", "Rupees (20)")  # remake_empty_object_contents "junk"
# "Nothing" at a chest, NPC, scrub or shop gives config/item_map.json's junk_for green rupee in the game. With
# remake_empty_object_contents "junk" (or "ice_trap" where an ice trap can't go) it becomes one of these, as a named
# item.
JUNK_NAMED = ("Rupee (1)", "Rupees (5)", "Rupees (20)", "Recovery Heart", "Deku Nuts (5)", "Deku Stick (1)",
              "Deku Seeds (30)", "Arrows (5)", "Bombs (5)")
NOT_ITEMS = ("Event", "Drop", "Hint", "HintStone")
TOKEN = "Gold Skulltula Token"
HEARTS = ("Obj_Heart_Piece", "Obj_Heart_Container")
# Blockers the plan can take. Respawning objects only get repeatable items (drops.plan_ops checks that again).
ALLOW = drop_tools.RESPAWN_BLOCKERS
_kept = {}
_avoid_vanilla = {"on": False}  # remake_avoid_vanilla_spots (tools/rando/no_vanilla.py), read in keep_locations
# The plugin whose get-scene hook gives the heart spots' items (_songs_trade_lake.py). Without it they only type-swap.
SCENE_PLUGIN = "songs_trade"
_scene = {"on": False}       # set in keep_locations: SCENE_PLUGIN joins this seed
_scene_pickups = {}          # id(world) -> [{"location", "tag", "item", "target"}] (world_plan; read by songs_trade)
_scene_gifts = {}            # id(world) -> [{"location", "item", "target", "gift"}] (world_plan; songs_trade builds them)
# the settings-dependent view (set in keep_locations): effective modes, and drop-map entries a setting replaces
_cfg = {"empty": "vanilla", "ice": "classic", "judge": False}
_ov = {}                     # name -> entry (stage hearts with remake_touch_pickups "any", key spots)
_disguised = {}              # id(world) -> {location}: OoTR "Nothing" turned into a disguised Ice Trap (after_fill)
_nothing_elsewhere = {}      # id(world) -> [(location, item)]: "Nothing" at other spots turned into a named item
_bug_note = {}               # id(world) -> [str]: the bug-logic rewrite (before_fill)
_borrowed = {}               # id(world) -> [flag]: the saved flags this seed's flagless drops borrow (world_plan)


def _map():
    return drop_tools._map()


def _remake(settings, key):
    return (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS.get(key, "off"))


def check_settings(settings):
    problems = []
    for k, v in (getattr(settings, "remake", None) or {}).items():
        if k in REMAKE_SETTINGS and v not in REMAKE_SETTINGS[k]:
            problems.append(f"{k} = {v!r}: drops can make {', '.join(map(repr, REMAKE_SETTINGS[k]))}")
    empties = getattr(settings, "shuffle_empty_pots", False) or getattr(settings, "shuffle_empty_crates", False)
    if empties and _remake(settings, "remake_empty_object_contents") == "ice_trap" and not _disguise_possible():
        problems.append("remake_empty_object_contents = 'ice_trap': the disguised ice trap needs the songs_trade "
                        "plugin's get-scene hook and the chests plugin's freeze (enable both, or choose 'nothing', "
                        "'junk' or 'vanilla')")
    # the grotto gift's scene ID must be one no other plugin rewrites (make_patch refuses a row reused twice)
    row = next((e["scene_gift"]["row"] for e in (_map().get("scene_gifts") or {}).values()
                if e["scene_gift"]["group"] == "zd_grotto"), None)
    taken = set()
    for mod, attr in (("parity.chests", "ICE_ROWS"), ("parity.chests", "TRAP_ROWS"), ("parity.dungeons", "ROWS")):
        taken |= set((getattr(sys.modules.get(mod), attr, None) or {}).values())
    silver = sys.modules.get("parity._dungeons_silver")  # the silver-rupee scene (remake_silver_rupee_items)
    if silver is not None:
        taken.add(silver.DATA.get("scene_row"))
    if row is not None and row in taken and _remake(settings, "remake_zd_grotto_rupees") == "gift":
        problems.append(f"remake_zd_grotto_rupees = 'gift': its scene ID {row} is taken by another plugin; give "
                        f"tools/rando/drops.py SCENE_GIFTS another config/scene_rows.json row")
    return problems


def _disguise_possible():
    """True if the disguised ice trap works in this run, which needs the get-scene hook (songs_trade), the freeze
    (chests) and a carrier."""
    import generate  # tools/rando/generate.py
    on = set(generate.enabled_plugins())
    return SCENE_PLUGIN in on and "chests" in on and bool(_map().get("disguise"))


def _modes(settings):
    """The effective modes of this seed's remake settings. A mode the plugins can't make falls back to the old one, and
    check_settings refuses the case where that would matter."""
    disguise = _disguise_possible()
    empty = _remake(settings, "remake_empty_object_contents")
    if empty == "ice_trap" and not disguise:
        empty = "vanilla"
    ice = _remake(settings, "remake_drop_ice_traps")
    if ice == "disguised" and not disguise:
        ice = "classic"
    touch = _remake(settings, "remake_touch_pickups") == "any" and _scene_enabled()
    keys = _remake(settings, "remake_freestanding_keys") == "any" and _scene_enabled()
    # "judge": spots get judged in-game as soon as any of these settings has a new value. Items that play exactly like
    # the vanilla spot are refused and "Nothing" stays off get-scene spots. With all four old values nothing changes.
    judge = empty != "vanilla" or ice == "disguised" or touch or keys
    # Scene gifts only touch their own spots. Their item rule keeps the vanilla look out, and "judge" stays as it was.
    gifts = tuple(g for g, (k, on) in GIFT_SETTINGS.items() if _remake(settings, k) == on and _scene_enabled())
    ungroup = _remake(settings, "remake_reset_group_objects") == "one_time"
    return {"empty": empty, "ice": ice, "touch": touch, "keys": keys, "judge": judge, "gifts": gifts,
            "ungroup": ungroup}


def _new_type_ok():
    """Whether a stage heart of a type new to its level may be used (drop_map "new_type": Kokiri Forest's 27
    freestanding spots, tools/rando/drops.py NEW_TYPE_HEART). Only a test build that asks for the probe uses it
    (parity/_test_start.py "probes": "kf_heart").
    TODO: not for real seeds until its in-game probe has passed."""
    ts = sys.modules.get("parity._test_start")
    return bool(ts is not None and ts.probe("kf_heart"))


def _overrides(modes):
    """{name: entry} for the drop-map entries these modes replace. That's a stage heart's spot (its "stage_get_scene"
    and "stage_actors" instead of "get_scene" and "allowed_actors") and the freestanding keys ("key_spots")."""
    m = _map()
    out = {}
    if modes["touch"]:
        for sec in ("drops", "new"):
            for n, e in m.get(sec, {}).items():
                if "stage_get_scene" in e and (not e["stage_get_scene"].get("new_type") or _new_type_ok()):
                    out[n] = dict(e, get_scene=e["stage_get_scene"],
                                  allowed_actors=e.get("stage_actors", e.get("allowed_actors", [])))
    if modes["keys"]:
        out.update(m.get("key_spots", {}))
    for n, e in (m.get("scene_gifts") or {}).items():
        if e["scene_gift"]["group"] in modes.get("gifts", ()):
            out[n] = e
    if modes.get("ungroup"):  # remake_reset_group_objects "one_time": the plan takes them out of their group
        for sec in ("drops", "new", "extras"):
            for n, e in m.get(sec, {}).items():
                e = out.get(n, e)
                if any(p.get("reset_group") for p in e.get("placements", [])):
                    out[n] = dict(e, placements=[dict(p, reset_group=None, ungroup=p["reset_group"])
                                                 if p.get("reset_group") else p for p in e["placements"]],
                                  blockers=[b for b in e.get("blockers", []) if b != "reset_group"])
    return out


def _gift(entry):
    """The scene-gift data of a drop-map entry (drop_map "scene_gifts", in play this seed), or None."""
    return (entry or {}).get("scene_gift")


def untested(settings):
    out = []
    if _scene_enabled():
        out.append("drops: heart pieces and heart containers holding another item (the get scene tells the spot by its "
                   "placement Name through the pickup's event AI, gives the item and removes the heart)")
    if _remake(settings, "remake_drop_contents") != "junk":
        out.append("drops: tunics and Fire Arrows dropped by pots/skulltulas (world pickups never seen dropped)")
    if _remake(settings, "remake_drop_contents") == "all":
        out.append("drops: remake_drop_contents 'all' - checked on pickup (AI graph edits: droppers hand their flag "
                   "to the pickup, breaks stop saving) for heart pieces, keys, tokens and Ruto's letter in pots, "
                   "small crates, grass, small rocks and skulltulas")
    for k in ("remake_shuffle_grass", "remake_shuffle_rocks", "remake_shuffle_boulders", "remake_shuffle_misc"):
        if _remake(settings, k) != "off":
            out.append(f"drops: {k} {_remake(settings, k)}")
    md = _modes(settings)
    if md["empty"] == "nothing":
        out.append("drops: remake_empty_object_contents 'nothing' - empty objects get the empty drop table ('None', "
                   "never used on grass, small rocks, palm fruit or small crates in vanilla)")
    if md["empty"] == "ice_trap" or md["ice"] == "disguised":
        out.append("drops: disguised ice traps - objects drop Obj_GerudoValley_Heart_Piece; its get scene freezes "
                   "Link (tag query fallthrough, get-scene hook branch, shared freeze)")
    if md["touch"]:
        out.append("drops: remake_touch_pickups 'any' - auto-collected rupees and hearts turned into their stage's "
                   "heart piece or heart container (a type from the level's other file) and given through the get "
                   "scene")
    if md["keys"]:
        out.append("drops: remake_freestanding_keys 'any' - the Bottom of the Well and Shadow Temple keys give their "
                   "item through the key's get scene (key event AI name check); the room logic's Bool saves them")
    if "gc_pot" in md["gifts"]:
        out.append("drops: remake_gc_pot_prize 'any' - the GC spinning pot's heart-piece scene removes the heart piece "
                   "(PickedUp death), sets GoronLargePot_IsGetHeartPiece and gives the seed's item")
    if "zd_grotto" in md["gifts"]:
        out.append("drops: remake_zd_grotto_rupees 'gift' - the ZD storms grotto's entry gives its six items once (a "
                   "reused scene ID on the entry requester, the vanilla entry as a sub-flow); its blue rupees deleted")
    if getattr(settings, "no_collectible_hearts", False):
        out.append("drops: no_collectible_hearts - heart drops become green rupees (DropGlobalParam HpActor and its "
                   "fairy-to-heart rule, every drop table's heart entry, placements and the Deku Tree scrubs' scene)")
    return out


def _level_on(level, dungeon):
    """True if a remake object setting's value turns on a location. The value is a level (off / dungeons / overworld /
    all) or an On/Off switch, where True means every one, like Ship of Harkinian's Shuffle Bushes."""
    return level is True or level == "all" or (level == "dungeons" and dungeon) or (level == "overworld" and not dungeon)


def _fits(entry, actor):
    """A freestanding spot can only become a pickup type its level already places."""
    return "allowed_actors" not in entry or actor in entry["allowed_actors"]


def _scene_enabled():
    import generate  # tools/rando/generate.py
    return SCENE_PLUGIN in generate.enabled_plugins()


def _scene_spot(entry):
    """A heart spot whose item the get scene can give (this seed has the hook)."""
    return _scene["on"] and "get_scene" in entry


def keep_locations(world, settings):
    """Every paired or new drop location OoTR (or a remake setting) leaves empty. Remake-only kinds that are off get
    their vanilla item and are locked here. The ones that are on add one junk item to the pool, since OoTR doesn't know
    those kinds and adds nothing for them."""
    import no_vanilla  # tools/rando/no_vanilla.py (remake_avoid_vanilla_spots, off by default)
    _avoid_vanilla["on"] = no_vanilla.enabled(settings)
    from Item import ItemFactory
    from ItemPool import get_junk_item
    m = _map()
    out = set()
    _scene["on"] = _scene_enabled()
    modes = _modes(settings)
    _cfg.clear()
    _cfg.update(modes, contents=_remake(settings, "remake_drop_contents"))
    # no_collectible_hearts (OoTR's Hero Mode, _drops_hearts.py): this plugin's own choices never add a heart either
    _cfg["no_hearts"] = bool(getattr(settings, "no_collectible_hearts", False))
    drop_tools.NO_STAND_IN.clear()
    if _cfg["no_hearts"]:
        drop_tools.NO_STAND_IN.add("Obj_Heart")  # an ice trap's stand-in pickup is never a heart
    _ov.clear()
    _ov.update(_overrides(modes))
    dg = sys.modules.get("parity.dungeons")
    if _scene["on"] and dg is not None and hasattr(dg, "CALL_LOCATIONS"):
        # a dungeon item at a heart spot: the get scene calls its credit entry (dungeons.call_target)
        dg.CALL_LOCATIONS.update(n for sec in ("drops", "new") for n, e in m.get(sec, {}).items()
                                 if "get_scene" in _ov.get(n, e))
        dg.CALL_LOCATIONS.update(n for n, e in _ov.items() if "get_scene" in e)
        # a dungeon item at a scene gift: its give step calls the credit entry too
        dg.CALL_LOCATIONS.update(n for n, e in _ov.items() if _gift(e))
        # ... and at a scene-drop spot (remake_drop_contents "all")
        dg.CALL_LOCATIONS.update(n for sec in ("drops", "new") for n, e in m.get(sec, {}).items()
                                 if _scene_drop_spot(_ov.get(n, e)) or _flagless_spot(_ov.get(n, e)))
    for name, e in m["drops"].items():
        e = _ov.get(name, e)
        if not drop_tools.usable(e, ALLOW) or e.get("missable"):
            continue  # stays vanilla if its only adult layout goes away for good (drops.ALT_LAYOUTS)
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.item is None and not loc.locked:
            out.add(name)
    for name, e in m.get("new", {}).items():
        e = _ov.get(name, e)
        try:
            loc = world.get_location(name)
        except KeyError:
            continue
        if loc.item is not None or loc.locked:
            continue
        if e.get("missable"):  # only in an adult layout that goes away for good (drops.ALT_LAYOUTS), so not shuffled
            if e["type"] in drop_tools.REMAKE_TYPES:  # OoTR's pool has nothing for a remake-only kind: lock it here
                world.push_item(loc, ItemFactory(e["vanilla"], world))
                loc.locked = True
            continue  # an OoTR kind: generate.lock_unpatchable takes its vanilla item out of the pool
        if e["type"] in drop_tools.REMAKE_TYPES:
            if not _level_on(_remake(settings, e["setting"]), e.get("dungeon")):
                world.push_item(loc, ItemFactory(e["vanilla"], world))
                loc.locked = True
                continue
            world.itempool.append(ItemFactory(get_junk_item()[0], world))
        if drop_tools.usable(e, ALLOW):
            out.add(name)
        else:
            world.push_item(loc, ItemFactory(e["vanilla"], world))
            loc.locked = True
    _kept[id(world)] = out
    return out


def _scene_target(item, location=None):
    """How the get scene gives OoTR item `item` at a heart spot: {"actor"}, {"progressive"}, {"ice_trap"} or {"call":
    scene entry}, or None if it can't. With `location` (from the plan) we ask the dungeons plugin for a dungeon item's
    credit entry. OoTR's "Nothing" with remake_empty_object_contents "nothing" gives {"nothing": True}, and the scene
    hides the pickup and gives nothing (_songs_trade_lake._resident_give)."""
    if item == "Nothing" and _cfg.get("empty") == "nothing":
        return {"nothing": True} if sys.modules.get(f"parity.{SCENE_PLUGIN}") is not None else None
    if item == "Ice Trap":  # the chests plugin's shared freeze (it adds the entry for any non-chest ice trap), and with
        ch = sys.modules.get("parity.chests")  # the location (the plan), the effect of the kind it drew
        if ch is None:
            return None
        return dict({"ice_trap": True}, **({"call": ch.trap_call_at(location)} if location else {}))
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and dg.dungeon_item(item) is not None:
        if not hasattr(dg, "call_target"):
            return None
        return {"call": dg.call_target(item) if location else "?"}
    st = sys.modules.get(f"parity.{SCENE_PLUGIN}")
    if st is None:
        return None
    try:
        return st._target(item)  # songs_trade's give targets (progressive tiers, trade items, item_map.json)
    except ValueError:
        return None


TRAP_GROUPS = ("Shock Trap", "Fire Trap", "Rupee Trap")  # scene drops of an Ice Trap of another kind (world_plan)


def _gift_name(g):
    """A scene gift's item the way the spoiler names it. An Ice Trap is named by the trap kind its give step calls."""
    call = str((g.get("target") or {}).get("call") or "").split(":")[-1]
    if g["item"] == "Ice Trap" and call.startswith("Rando_Trap_"):
        return f"{call[len('Rando_Trap_'):]} Trap"
    return g["item"]


def _trap_group_target(group):
    """The get-scene target for a scene-drop tag that holds the Ice Traps of one kind (TRAP_GROUPS), which is that
    kind's effect."""
    ch = sys.modules["parity.chests"]
    kind = next(k for k, n in ch.TRAP_NAMES.items() if n == group)
    return {"ice_trap": True, "call": ch.scenes.trap_call(kind)}


def _needs_scene(entry, item, contents):
    """True if the get scene gives the item at this heart spot, meaning it's not the vanilla item and no type swap shows
    it. An ice trap always takes the scene's real freeze rather than a stand-in rupee."""
    if not _scene_spot(entry) or (item.name == entry.get("vanilla") and _vanilla_fits(entry)):
        return False
    if item.name == "Ice Trap" and _scene_target(item.name) is not None:
        return True
    return not _swap_ok(entry, item, contents)


def _vanilla_fits(entry):
    """Whether the spot's vanilla item stays its own pickup, so its type has to be one the spot can show. Not at Kokiri
    Forest's heart spots (drop_map "new_type"). "KF Bean Platform Red Rupee" holds Rupees (20), and the red rupee isn't
    in the forest's files, so even its vanilla item comes through the get scene there."""
    actor = drop_tools.remake_drop(entry.get("vanilla") or "")
    return actor is None or _fits(entry, actor) or not (entry.get("get_scene") or {}).get("new_type")


def _own_pickup(entry, name):
    """True if OoTR item `name` is the spot's own pickup (its placed type, heart-piece variants count as hearts). A
    small key only counts if it's the key of the spot's own dungeon. Every dungeon's single key drops as
    Obj_Dungeon_SmallKey, but another dungeon's key at a freestanding-key spot isn't its vanilla item (my call)."""
    actor = drop_tools.remake_drop(name)
    if actor is not None and name in drop_tools.KEY_AREA:
        return _same_name(entry, name)
    own = {p["actor"] for p in entry.get("placements", [])}
    if own & set(drop_tools.HEART_PIECE_VARIANTS):
        own.add("Obj_Heart_Piece")
    return actor is not None and actor in own


def _swap_ok(entry, item, contents):
    """A placed pickup that turns into the item's own pickup type. It's saved when taken, never lost and never
    repeats."""
    name = item.name
    if name == "Ice Trap":
        return drop_tools.ice_trap_drop(entry)[0] is not None
    actor = drop_tools.remake_drop(name)
    if actor is None or not _fits(entry, actor):
        return False
    if actor in HEARTS or actor in drop_tools.REPEATABLE_JUNK | drop_tools.ONCE_JUNK:
        return True
    return name in drop_tools.REPEATABLE_ITEMS and contents != "junk" and _major_ok(entry)


def _checked(entry):
    """A drop spot whose item is never lost. Either it's checked on pickup (drops.picks_up_checked), or it's an object
    the respawn model takes (drops.respawn_capable). Those come back with their item until the item is taken, and then
    the vanilla twin stands there. Butterflies, large crates, A_02 boulders and beehives work that way too. Remembered
    per spot, since the fill's item rules ask it for every item."""
    key = (entry.get("kind"), tuple((p.get("file"), str(p.get("hash")), p.get("actor"), p.get("flag"),
                                     p.get("reset_group"), p.get("category")) for p in entry.get("placements", [])))
    if key not in _checked_memo:
        _checked_memo[key] = bool(drop_tools.picks_up_checked(entry) or drop_tools.respawn_capable(entry))
    return _checked_memo[key]


_checked_memo = {}


def _scene_drop_spot(entry):
    """A drop spot that gives any item through the get scene (tools/rando/drops.py "scene drops"). That's
    remake_drop_contents "all", my rule, same as Ship of Harkinian. It has to be a checked-on-pickup or respawn-model
    object (_checked), so its dropper hands its tag to its drop and its item is never lost, and the seed needs the
    get-scene hook and the carrier."""
    return (_scene["on"] and _cfg.get("contents") == "all" and entry.get("kind") == "drop"
            and _checked(entry) and bool(_map().get("disguise")))


def _flagless_spot(entry):
    """A drop spot whose objects have no save flag but whose type can hold a flagless drop (drops.flagless_capable).
    Every item it holds is a scene drop with its own tag and its own borrowed flag."""
    return (_scene["on"] and _cfg.get("contents") == "all" and drop_tools.flagless_capable(entry)
            and bool(_map().get("disguise")))


def _flagless_own(entry, name):
    """The pickup OoTR item `name` drops as itself at this flagless spot (drops FLAGLESS OWN), or None for the carrier
    and the get scene. That's junk with a quiet touch pickup of its own: ammo, rupees and recovery hearts, taken on
    touch with the game's count popup and recorded by the spot's checked bit. With remake_avoid_vanilla_spots on, a
    pickup the spot gives in the vanilla game keeps the carrier so its look tells it apart."""
    if not _flagless_spot(entry):
        return None
    actor = drop_tools.flagless_own_actor(entry, name)
    if actor is None or (_avoid_vanilla["on"] and actor in _vanilla_pickups(entry)):
        return None
    return actor


def _scene_drop_ok(entry, item, flagless=False):
    """Can OoTR item `item` go to scene-drop spot `entry` through the get scene? Anything the scene can give, except ice
    traps (those are the disguised trap) and shop items. Progression only where the spot's region rule is certain
    (_major_ok). Ammo too, like OoTR. The carrier shows it, the get scene gives it, and parity/_ammo.py makes ammo
    without its container add nothing. Where ammo can drop as its own touch pickup it does that instead
    (_allowed_direct, drops AMMO AS ITSELF). OoTR's "Nothing" is whatever remake_empty_object_contents makes of it
    (_nothing_ok)."""
    name = item.name
    if name == "Nothing":
        return _nothing_ok(entry, flagless=flagless, scene=True)
    if getattr(item, "type", None) == "Shop" or (name == "Ice Trap" and not flagless):
        return False  # a flagless spot gives its ice trap through the scene too, once, by its flag
    if (getattr(item, "advancement", False) or getattr(item, "priority", False)) and not _major_ok(entry):
        return False
    return _scene_target(name) is not None


def _nothing_ok(entry, flagless=False, scene=False):
    """Can OoTR's "Nothing" go to drop-map entry `entry`? OoTR puts it anywhere (GI_NOTHING). Here it becomes whatever
    remake_empty_object_contents says, and I don't refuse it anywhere the setting gives it a meaning (my call):
      ice_trap  an Ice Trap (after_fill): the disguised trap at any object, the scene's freeze at a heart spot or scene
                gift, and elsewhere (a placed pickup) a named junk item the spot takes (_named_nothing)
      junk      a rupee other than the object's own fixed drop at objects, a named junk item the spot takes elsewhere
      nothing   OoTR's GI_NOTHING: an object gets the empty drop table (if its type lists one and it isn't using it
                already), or a spot whose get scene gives nothing (_scene_target {"nothing"}). That's a heart spot, a
                scene gift, a scene drop or a flagless drop, where the carrier drops and the scene hides it and gives
                nothing.
      vanilla   the object keeps its own drop, so only where that drop is OoTR's Nothing too (a random table)
    `scene` means we're asked about a scene drop (the carrier and the get scene), `flagless` about a flagless drop."""
    mode, kind = _cfg.get("empty"), entry.get("kind")
    if mode == "ice_trap":
        if kind == "drop":
            return True  # the disguised trap drops from any object, after_fill marks it _disguised whatever
            # remake_drop_ice_traps says (plan_ops' disguise_names)
        return _allowed(entry, _item_like("Ice Trap"), _cfg.get("contents")) or _junk_ok(entry)
    if mode == "junk":
        return _junk_ok(entry)
    if mode == "nothing":
        if scene or _gift(entry) or _scene_spot(entry):
            return True  # the get scene gives nothing
        return (kind == "drop" and entry.get("vanilla") == "Nothing" and drop_tools.can_be_empty(entry)
                and not drop_tools.empty_in_vanilla(entry))
    # "vanilla": the object keeps its own drop, so this only works where that drop is OoTR's "Nothing" too (a random
    # table). On a fixed drop or a Skulltula it would give its vanilla rupees or token, and a get scene would give
    # config/item_map.json's junk_for green rupee.
    return not scene and kind == "drop" and entry.get("vanilla") == "Nothing"


def nothing_converted():
    """True if OoTR's "Nothing" outside this plugin's objects becomes a real item after the fill (_named_nothing, with
    remake_empty_object_contents "ice_trap" or "junk"). Then any spot whose rule takes an Ice Trap or a junk item can
    hold it (the fairies plugin, the silver-rupee spots). My rule: OoTR's Nothing goes anywhere."""
    return _cfg.get("empty") in ("ice_trap", "junk")


def _junk_choices(entry):
    """The named junk OoTR's "Nothing" can become at this spot (remake_empty_object_contents "junk", or "ice_trap" where
    no Ice Trap goes). At an object that's a rupee other than its own fixed drop, elsewhere JUNK_NAMED, and only what
    the spot's rule takes."""
    if entry.get("kind") == "drop":
        own = drop_tools.vanilla_drop(entry)
        names = [n for n in JUNK_RUPEES if drop_tools.remake_drop(n) != own]
    else:
        names = [n for n in JUNK_NAMED if not (_cfg.get("no_hearts") and n == "Recovery Heart")]
    return [n for n in names if _allowed(entry, _item_like(n), _cfg.get("contents"))]


def _junk_ok(entry):
    return bool(_junk_choices(entry))


def _needs_scene_drop(entry, item, contents):
    """True if the get scene gives the item at this drop spot (a scene drop). Its own pickup can't drop there, but the
    scene can give it."""
    # Its own pickup is decided without the hidden-vanilla judge, since that asks _gives, which asks this. An item whose
    # pickup would play like the vanilla spot stays out instead of slipping in through the scene.
    if _flagless_spot(entry):
        return _scene_drop_ok(entry, item, flagless=True)
    return (_scene_drop_spot(entry) and not _allowed_direct(entry, item, contents, judge=False)
            and _scene_drop_ok(entry, item))


def _item_like(name):
    """An object with OoTR item `name`'s name, type, advancement and priority (the item rules read nothing else)."""
    from Item import ItemInfo
    from types import SimpleNamespace
    info = ItemInfo.items.get(name)
    if info is None:
        return None
    return SimpleNamespace(name=name, type=info.type, advancement=info.advancement, priority=info.priority)


def _allowed(entry, item, contents):
    """Can OoTR item `item` go to drop-map entry `entry`? Either as its own pickup (or through the heart spot's scene),
    or at a scene-drop spot as anything the get scene can give."""
    if _flagless_spot(entry):  # only through the scene: its pickup alone couldn't be given once
        return _needs_scene_drop(entry, item, contents)
    if _allowed_direct(entry, item, contents):
        return True
    return _needs_scene_drop(entry, item, contents)


def _allowed_direct(entry, item, contents, judge=True):
    """Can OoTR item `item` go to drop-map entry `entry` as a pickup (or through a heart spot's or scene gift's
    scene)?"""
    name = item.name
    if _gift(entry):
        # A scene gift (remake_gc_pot_prize, remake_zd_grotto_rupees) takes anything its scene can give. With
        # remake_avoid_vanilla_spots it refuses what plays as the spot's vanilla item. OoTR's "Nothing" goes as
        # remake_empty_object_contents makes it (_nothing_ok).
        if name == "Nothing":
            return _nothing_ok(entry)
        if _avoid_vanilla["on"] and (_same_name(entry, name) or _hidden_vanilla(entry, name, contents)):
            return False
        if (item.advancement or item.priority) and not _major_ok(entry):
            return False
        return _scene_target(name) is not None
    if _scene_spot(entry):
        # A heart spot takes anything the get scene can give (or a type swap shows). With remake_avoid_vanilla_spots
        # (off by default) it refuses an item whose pickup is the spot's own: Piece of Heart or the Treasure Chest
        # Game's Piece of Heart at a heart-piece spot, Heart Container at a boss heart. That can't be told apart from
        # vanilla, which I read as a bug, and with drop spots that can't hold hearts OoTR's fill put 2-5 of the 22 back
        # per seed. With the setting off, OoTR's fill can put them back, same as OoTR.
        if _avoid_vanilla["on"] and (name == entry.get("vanilla") or _own_pickup(entry, name)):
            return False
        if _cfg.get("judge"):
            if name == "Nothing":  # as remake_empty_object_contents makes it (_nothing_ok)
                return _nothing_ok(entry)
            if _avoid_vanilla["on"] and not _same_name(entry, name) and _hidden_vanilla(entry, name, contents):
                return False
        if _swap_ok(entry, item, contents):
            return True
        if (item.advancement or item.priority) and not _major_ok(entry):
            return False
        # Recovery Heart and Fairy Drop have their own give entries (songs_trade._target -> dungeons.heal_graph),
        # otherwise a green rupee would stand in for them.
        # Rupees and shields of a type the level doesn't place go through the get scene with their display model, like
        # any other item.
        return _scene_target(name) is not None
    if judge and _cfg.get("judge") and _avoid_vanilla["on"] and not _same_name(entry, name) and _hidden_vanilla(entry, name, contents):
        return False  # a different item name, but in-game exactly the vanilla object (e.g. a boulder's green rupee)
    gs = any(p["category"] == "gold_skulltula" for p in entry.get("placements", []))
    if name == TOKEN:
        # Outside a Gold Skulltula, a token drops through the heart-piece carrier when the spot can do a scene drop.
        # Obj_Token_Gold's own AI keeps it standing where it spawns (ExecuteKeepStandingPosture), so a pot thrown at a
        # wall, an icicle's ceiling, a beehive or a lifted rock left it hanging (OotrR #35 in game). The carrier falls
        # thanks to its body (drops.fall_ops). The get scene then gives Item_Token_Gold, with the count and token
        # window, plus the spot's checked bit (ootrr_findings G1). Spots with no scene drop keep the token itself.
        return gs or (contents == "all" and _checked(entry) and _major_ok(entry) and not _scene_drop_spot(entry))
    if name == "Ice Trap":
        if _cfg.get("ice") == "disguised":  # the disguised trap drops from any object, placed pickups use the get scene
            return entry.get("kind") == "drop"
        return drop_tools.ice_trap_drop(entry)[0] is not None  # an enemy the level places, or a stand-in
    if name == "Nothing":  # as remake_empty_object_contents makes it (_nothing_ok)
        return _nothing_ok(entry)
    actor = drop_tools.remake_drop(name)
    if actor is None:
        return False
    if entry.get("kind") == "freestanding":  # a placed pickup: saved when taken, never lost, never repeats
        return _swap_ok(entry, item, contents)
    if actor in drop_tools.HOVERING_PICKUPS and (_scene_drop_spot(entry) or _flagless_spot(entry)):
        # These go through the falling carrier where they can. A heart piece, heart container or Ruto's Letter has a
        # kinematic body and stays up where it spawns, in a tree or against a pot or Skulltula wall for example. The
        # carrier's get scene gives the item, same as for tokens above.
        return False
    respawns = drop_tools.spot_respawns(entry)
    if actor in drop_tools.TOUCH_AMMO:
        # Junk ammo drops as the game's own touch pickup. It's taken the moment Link touches it, with the game's count
        # popup, and gives 0/0 without its container. Only where it's never lost and never repeats: the object comes
        # back with it until it's taken, and taking it records the check. Those are the checked-on-pickup and
        # respawn-model spots.
        if (getattr(item, "advancement", False) or getattr(item, "priority", False)) and not _major_ok(entry):
            return False
        return contents == "all" and _checked(entry)
    if actor in drop_tools.REPEATABLE_JUNK:
        return True
    if contents == "all" and _checked(entry) and drop_tools.saves_on_pickup(actor) \
            and _major_ok(entry) and not _is_ammo(actor) and item.type not in ("Shop",):
        # checked on pickup: the object comes back until this item is taken (keys: own dungeon only)
        return name not in drop_tools.KEY_AREA or drop_tools.KEY_AREA[name] == entry.get("area")
    if actor in drop_tools.ONCE_JUNK:
        return not respawns
    if name in drop_tools.REPEATABLE_ITEMS:
        # Kept respawning (vanilla area reset, enemy flag, reset group, no flag or a skulltula), so it's never lost.
        comes_back = respawns or all(p["flag"] in (88, 280) for p in entry["placements"])
        return contents != "junk" and comes_back and _major_ok(entry)
    return False  # anything else could be lost if left behind (only checked-on-pickup spots take it, above)


def _gives(entry, name, contents="safe", disguised=False):
    """What drop-map spot `entry` gives in the game for OoTR item `name` with this seed's modes. ("scene", name) when
    the get scene gives it, ("actor", pickup or enemy), ("own",) when the object is left as it is, or ("empty",)."""
    if _gift(entry):
        return ("scene", name)  # its own scene gives it (the rupees are deleted, the pot's heart piece removed)
    if _scene_spot(entry) and (name != entry.get("vanilla") or not _vanilla_fits(entry)):
        class _I:  # _needs_scene takes an item
            pass
        it = _I()
        it.name = name
        if _needs_scene(entry, it, contents):
            return ("scene", name)
    if name == "Nothing" and _cfg.get("empty") in ("ice_trap", "junk"):
        if entry.get("kind") == "drop" and _cfg.get("empty") == "ice_trap":
            return ("actor", drop_tools.DISGUISE_ACTOR)  # after_fill: the disguised trap
        return ("converted", name)  # after_fill: an Ice Trap or a named junk item other than the vanilla one
    scene_nothing = name == "Nothing" and _cfg.get("empty") == "nothing"  # the get scene gives nothing
    if entry.get("kind") == "drop" and _flagless_spot(entry) and (name != "Nothing" or scene_nothing):
        own = _flagless_own(entry, name)  # junk with a touch pickup of its own drops as itself (flagless pickup support in drops.py)
        return ("actor", own) if own else ("scene", name)  # else the carrier with its own tag and flag
    if entry.get("kind") == "drop" and (name not in ("Nothing", "Ice Trap") or scene_nothing) and \
            _scene_drop_spot(entry):
        it = _item_like(name)
        if it is not None and _needs_scene_drop(entry, it, contents):
            return ("scene", name)  # a scene drop: the carrier with the spot's tag, the get scene gives it
    if name == "Nothing":
        if entry.get("kind") == "drop" and _cfg.get("empty") == "nothing":
            return ("empty",)
        return ("own",)
    if name == "Ice Trap":
        if entry.get("kind") == "drop" and (_cfg.get("ice") == "disguised" or disguised):
            return ("actor", drop_tools.DISGUISE_ACTOR)
        return ("actor", drop_tools.ice_trap_drop(entry)[0])
    actor = drop_tools.remake_drop(name)
    if entry.get("kind") == "freestanding" and actor == "Obj_Heart_Piece" and any(p["actor"] in drop_tools.HEART_PIECE_VARIANTS for p in entry.get("placements", [])):
        actor = next(p["actor"] for p in entry["placements"] if p["actor"] in drop_tools.HEART_PIECE_VARIANTS)
    return ("actor", actor)


def _vanilla_pickups(entry):
    """The pickups the spot gives in the vanilla game. That's the placed pickups' own types, or the objects' fixed drop
    (Drop__DropActor, or a table that drops the same actor every time, drop_map "dropper_tables")."""
    if entry.get("kind") == "freestanding":
        own = {p["actor"] for p in entry.get("placements", [])}
        if own & {"Obj_Heart", "Obj_Heart_InWater"}:
            own |= {"Obj_Heart", "Obj_Heart_InWater"}
        return own
    vd = drop_tools.vanilla_drop(entry)
    return {vd} if vd else set()


def _same_name(entry, name):
    """True if `name` is the spot's vanilla item as no_vanilla compares names (tools/rando/no_vanilla.py look)."""
    import no_vanilla  # tools/rando/no_vanilla.py
    return entry.get("vanilla") is not None and no_vanilla.look(name) == no_vanilla.look(entry["vanilla"])


def _hidden_vanilla(entry, name, contents="safe", disguised=False):
    """Why OoTR item `name` at this spot plays exactly like the vanilla game even though the name isn't the vanilla
    item, or None. The name check (tools/rando/no_vanilla.py) catches the rest."""
    g = _gives(entry, name, contents, disguised)
    if g[0] == "converted":
        return None  # OoTR's "Nothing" made an Ice Trap or another junk item after the fill
    if g[0] == "scene" and entry.get("kind") == "drop":
        return None  # a scene drop: the carrier and the get scene, never the object's own vanilla pickup
    if g[0] == "scene":
        mine = _scene_target(name)
        # a dungeon item's call is its own, so names compare
        if mine is not None and "call" not in mine and entry.get("vanilla") and mine == _scene_target(entry["vanilla"]):
            return f"the get scene gives {mine}, what the vanilla {entry['vanilla']} gives"
        return None
    if g[0] == "own" and entry.get("kind") == "drop":
        return "the object keeps its own drop (remake_empty_object_contents 'vanilla')"
    if g[0] == "empty" and drop_tools.empty_in_vanilla(entry):
        return "the object already drops nothing in the vanilla game"
    if g[0] == "actor" and g[1] is not None and g[1] in _vanilla_pickups(entry):
        return f"it gives {g[1]}, the spot's own vanilla pickup"
    return None


def _ammo_sw():
    """True if remake_ammo_without_container is "blue_rupee", so container ammo switches looks (drops AMMO SWITCH)."""
    from . import _ammo
    return _ammo.mode() == "blue_rupee"


def _is_ammo(actor):
    """Ammo pickups. The ones with a touch pickup of their own (drops.TOUCH_AMMO: our types with OoTR's amounts, and the
    stick) drop as themselves at checked spots (_allowed_direct, drops AMMO AS ITSELF). Bombchus still come through the
    carrier, since their pickup plays a get scene."""
    return actor in drop_tools.AMMO_TYPES or actor.startswith("Obj_ArrowBundle") or actor in (
        "Obj_DekuSeed", "Obj_Bomb", "Obj_Bombchu", "Obj_DekuNut",
        "Obj_DekuStick")


def _major_ok(entry):
    """Progression only where the rule is certain or stricter than the game (region files: high/medium)."""
    return entry.get("confidence", "high") in ("high", "medium")


def _lookup(name):
    return drop_tools.lookup(name, overrides=_ov)


def before_fill(world, settings):
    from Item import ItemFactory
    kept = _kept.get(id(world), set())
    contents = _remake(settings, "remake_drop_contents")
    groups, prefilled = {}, set()
    for name in sorted(kept):  # placed-pickup spots take few types, so a fitting pool item now (junk or a heart)
        e = _lookup(name)
        if e.get("kind") != "freestanding" or _scene_spot(e):
            continue  # heart spots with the get scene take anything: OoTR's fill places them (item rule below)
        loc = world.get_location(name)
        fits = [it for it in world.itempool if _allowed(e, it, contents) and (not it.advancement or
                drop_tools.remake_drop(it.name) in HEARTS)]
        if fits:
            item = random.choice(fits)
            world.itempool.remove(item)
        else:  # nothing in the pool fits: its vanilla pickup, balanced by dropping a junk item from the pool
            item = ItemFactory(e["vanilla"], world)
            junk = next((it for it in world.itempool if not it.advancement and not it.priority
                         and not it.dungeonitem), None)
            if junk is not None:
                world.itempool.remove(junk)
        world.push_item(loc, item)  # left unlocked: OoTR's fill skips filled spots, its spoiler lists them
        prefilled.add(name)
    for name in sorted(kept):
        e = _lookup(name)
        loc = world.get_location(name)
        if loc.locked:
            continue
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev, e=e: _allowed(e, item, contents) and prev(location, item))
        if name in prefilled:
            continue  # filled above, the rule stays so a later swap (tools/rando/no_vanilla.py) keeps to it
        if e.get("type") and e.get("mode") is None:
            continue  # a new location: its rule comes from data/rando/logic/drops.json
        rule = loc.rule_string or "True"
        if e.get("extra_rule"):
            rule = f"({rule}) and ({e['extra_rule']})"
        if e.get("mode") == "group":
            groups.setdefault(e.get("group"), []).append(name)
        if rule != loc.rule_string:
            loc.rule_string = rule
            world.parser.parse_spot_rule(loc)
    _group_logic(world, groups)
    _bug_logic(world)
    if _cfg.get("empty") == "nothing":
        # OoTR's GI_NOTHING only exists in objects made empty. A chest, NPC, scrub, shop or placed pickup would give
        # config/item_map.json's junk_for green rupee instead, so "Nothing" goes nowhere else.
        for loc in world.get_locations():
            if loc.item is not None or loc.locked or loc.name in kept or loc.type in NOT_ITEMS:
                continue
            prev = loc.item_rule
            loc.item_rule = (lambda location, item, prev=prev: item.name != "Nothing" and prev(location, item))


def _bug_logic(world):
    """OoTR's 'Bugs' (its Drop locations Bug Shrub, Bug Rock, Wandering Bugs), counted only from the remake's provable
    bug sources in this seed, whatever the settings (drop_map "bugs", drops.BUG_SOURCES). Those are every bug object
    that isn't shuffled and the never-shuffled Hyrule Field bushes. An unshuffled bug grass tuft or bug rock sits in its
    own region under its own location rule, and if this world has no OoTR location for it, its region and rule come from
    the drop map. A shuffled bug object gives its item, not bugs.
    One of OoTR's bug locations moves to Root and gets "has_bottle and (at(region, rule) or ...)", the others get
    False, and with no source they're all False. OoTR's own 21 regions aren't used because 14 of them have no remake
    bug source. Foliage grass (30 % bugs) can't be placed in a region and isn't counted, so the logic is never looser
    than the game."""
    bugs = _map().get("bugs") or {}
    objs = bugs.get("objects", {})
    kept = _kept.get(id(world), set())
    shuffled = sorted(n for n in objs if n in kept)
    sources, counted = [], []
    for src in bugs.get("permanent", []):
        sources.append(f"at('{src['region']}', {src['rule']})")
        counted.append(f"{src['region']}: {src['type']} ({len(src['hashes'])} placements)")
    for n, region in sorted(objs.items()):
        if n in kept:
            continue
        try:
            rule = world.get_location(n).rule_string
        except KeyError:  # no OoTR location for it in this world: the drop map's own region rule
            rule = (_lookup(n) or {}).get("rule")
        rule = drop_tools.mode_safe((rule or "True").split("#", 1)[0].strip())
        sources.append(f"at('{region}', {rule})")
        counted.append(f"{region}: {n}")
    rule = "has_bottle and (" + " or ".join(f"({x})" for x in sources) + ")" if sources else "False"
    spots = sorted((loc for loc in world.get_locations() if loc.type == "Drop"
                    and (loc.vanilla_item == "Bugs" or (loc.item is not None and loc.item.name == "Bugs"))),
                   key=lambda loc: loc.name)
    if spots:
        # The counted one sits in Root, like OoTR's item-only events. Its rule only needs items and the sources' subrule
        # events (each at its source's region), not access to one of OoTR's bug regions.
        live = spots[0]
        root = world.get_region("Root")
        if live.parent_region is not root:
            live.parent_region.locations.remove(live)
            live.parent_region = root
            root.locations.append(live)
    for i, loc in enumerate(spots):
        loc.rule_string = rule if i == 0 else "False"
        loc.always = loc.never = False
        world.parser.parse_spot_rule(loc)
    world.parser.create_delayed_rules()
    _bug_note[id(world)] = ([f"bugs: OoTR's {len(spots)} bug locations replaced by the remake's {len(counted)} "
                             f"provable sources ({len(shuffled)} bug objects shuffled: they give their item, not bugs)"
                             + ("" if sources else "; none left: bugs only from the potion shops")]
                            + [f"bug source: {c}" for c in counted])


def _group_logic(world, groups):
    """Every member of a group needs every member reachable (the real pairing is unknown)."""
    from Item import make_event_item
    from Location import Location
    for gid, members in groups.items():
        if len(members) < 2:
            continue
        events = []
        for i, name in enumerate(sorted(members), 1):
            loc = world.get_location(name)
            ev = f"Remake drop group {gid} {i}"
            ev_loc = Location(f"{ev} from {loc.parent_region.name}", location_type="Event", parent=loc.parent_region)
            ev_loc.rule_string = loc.rule_string
            world.parser.parse_spot_rule(ev_loc)
            ev_loc.world = world
            loc.parent_region.locations.append(ev_loc)
            make_event_item(ev, ev_loc)
            events.append(ev)
        rule = " and ".join(f"'{e}'" for e in events)
        for name in members:
            loc = world.get_location(name)
            loc.rule_string = rule
            world.parser.parse_spot_rule(loc)


def after_fill(world, settings):
    """OoTR's junk pass ignores item rules, so junk that can't drop here gets swapped with junk from a chest or scene
    location that can. Both are junk, so logic doesn't change. Then OoTR's "Nothing" in an object becomes what
    remake_empty_object_contents gives ("junk" a rupee, "ice_trap" an Ice Trap), so the spoiler names it."""
    _fix_rules(world, settings)
    mode = _cfg.get("empty")
    _disguised[id(world)] = set()
    _nothing_elsewhere[id(world)] = []
    if mode not in ("junk", "ice_trap"):
        return
    from Item import ItemFactory
    for name in sorted(_kept.get(id(world), set())):
        loc = world.get_location(name)
        e = _lookup(name)
        if loc.item is None or loc.item.name != "Nothing" or e.get("kind") != "drop":
            continue
        if mode == "ice_trap":
            new = "Ice Trap"
            _disguised[id(world)].add(name)
        else:  # never the object's own fixed drop (a boulder's green rupee), and one the spot's rule takes
            new = random.choice(_junk_choices(e))
        item = ItemFactory(new, world)
        loc.item, item.location = item, loc
    _named_nothing(world, mode)


def _named_nothing(world, mode):
    """OoTR's "Nothing" at any other spot (chest, NPC, scrub, shop, placed pickup, heart spot, scene gift...) gives
    config/item_map.json's junk_for green rupee in the game while the spoiler says Nothing. With
    remake_empty_object_contents "ice_trap" it becomes a real Ice Trap where the spot's rules take one (chests and
    scene spots run the freeze). Otherwise, and with "junk", it becomes a named junk item the spot's rules take, never
    its own vanilla item. Logic doesn't change (junk for junk). after_fill already converted this plugin's objects
    (kind "drop")."""
    import no_vanilla  # tools/rando/no_vanilla.py
    from Item import ItemFactory
    kept = _kept.get(id(world), set())
    done = _nothing_elsewhere.setdefault(id(world), [])
    # no_collectible_hearts: OoTR's "Nothing" never becomes a heart OoTR wouldn't have put there
    named = [n for n in JUNK_NAMED if not (_cfg.get("no_hearts") and n == "Recovery Heart")]
    for loc in world.get_locations():
        if loc.item is None or loc.item.name != "Nothing" or loc.locked or loc.type in NOT_ITEMS:
            continue
        if loc.name in kept and _lookup(loc.name).get("kind") == "drop":
            continue  # an object: after_fill's disguised trap or rupee
        cands = (["Ice Trap"] if mode == "ice_trap" else []) + random.sample(named, len(named))
        for name in cands:
            item = ItemFactory(name, world)
            if loc.can_fill_fast(item) and not no_vanilla.is_vanilla(loc, item):
                loc.item, item.location = item, loc
                done.append((loc.name, name))
                break
        else:
            raise ValueError(f"{loc.name}: Nothing, and no named junk item fits here")


def _fix_rules(world, settings):
    kept = _kept.get(id(world), set())
    contents = _remake(settings, "remake_drop_contents")
    bad = [n for n in sorted(kept) if not _allowed(_lookup(n), world.get_location(n).item, contents)]
    if not bad:
        return
    others = [loc for loc in world.get_locations() if loc.item is not None and not loc.locked
              and loc.name not in kept and loc.type not in ("Event", "Drop", "Hint", "HintStone")
              and not loc.item.advancement and not loc.item.priority]
    random.shuffle(others)
    nv = sys.modules.get("no_vanilla")  # tools/rando/no_vanilla.py: prefer swaps that leave neither spot vanilla
    for name in bad:
        loc = world.get_location(name)
        e = _lookup(name)
        if nv is not None and nv.enabled(settings):
            others.sort(key=lambda o: nv.is_vanilla(loc, o.item) or nv.is_vanilla(o, loc.item))
        for other in others:
            if _allowed(e, other.item, contents) and other.item_rule(other, loc.item):
                loc.item, other.item = other.item, loc.item
                loc.item.location, other.item.location = loc, other
                others.remove(other)
                break
        else:
            raise ValueError(f"{name}: no junk that can drop here to swap with {loc.item.name}")


def get_scene_pickups(world):
    """The heart spots this seed gives through the get scene: [{"location", "tag", "item", "target"}], for the
    get-scene hook (songs_trade's _songs_trade_lake.world_plan_ops). Built by world_plan."""
    return list(_scene_pickups.get(id(world), []))


def get_scene_gifts(world):
    """This seed's scene gifts: [{"location", "item", "target", "gift" (drop_map scene_gift data), "placements"}].
    Built by world_plan."""
    return list(_scene_gifts.get(id(world), []))


def scene_gift_ops(o, world):
    """Adds the scene gifts' plan sections to the songs_trade plugin's Ops `o`. Its world_plan calls this after this
    plugin's world_plan, and the gifts' give steps share its progressive, get-window and freeze entries."""
    from . import _drops_gifts
    _drops_gifts.ops(o, get_scene_gifts(world))


def world_plan(settings, world):
    kept = _kept.get(id(world), set())
    assignments = {name: world.get_location(name).item.name for name in kept}
    contents = _remake(settings, "remake_drop_contents")
    allow = ALLOW + (("checked_on_pickup",) if contents == "all" else ())
    scene, pickups = set(), []
    for name in sorted(kept):  # heart spots whose item the get scene gives (runs before dungeons' world_plan)
        e = _lookup(name)
        item = world.get_location(name).item
        if not _needs_scene(e, item, contents):
            continue
        target = _scene_target(item.name, name)
        if target is None:
            raise ValueError(f"{name}: {item.name} can't be given by the get scene (the item rule should have "
                             f"kept it out)")
        scene.add(name)
        # Junk at a heart spot (a freestanding rupee turned into a heart piece, or a vanilla heart piece) is taken
        # quietly, like at a scene drop. Otherwise ammo there gets held up (drops.QUIET_JUNK).
        pickups.append({"location": name, "tag": e["get_scene"]["tag"], "item": item.name, "target": target,
                        "quiet": item.name in drop_tools.QUIET_JUNK})
    # Drop spots whose item the get scene gives. One tag per item (SCENE_DROP_TAG0, +1, ... by item name), so spots
    # holding the same item share its scene branch, its answer and its look, and a progressive item's tier gets
    # checked once.
    # An Ice Trap of another kind (remake_trap_weights) at a scene-drop spot is a scene drop too, with one tag per kind.
    # Its group is named the way the spoiler names it (TRAP_GROUPS). The disguised trap's one fallthrough branch can
    # only freeze. Where the spot can't hand a tag on, it stays the disguised ice trap and its kind is never recorded,
    # so the spoiler names the Ice Trap it plays.
    ch = sys.modules.get("parity.chests")
    scene_drops, tag_of, by_tag = {}, {}, {}
    for name in sorted(n for n in kept if n not in scene):
        item = world.get_location(name).item
        e = _lookup(name)
        trap = (ch.trap_kind(world, name) if ch is not None and item.name == "Ice Trap" and _scene_drop_spot(e)
                and not _flagless_spot(e) else "ice")
        if trap == "ice" and not _needs_scene_drop(e, item, contents):
            continue
        target = _scene_target(item.name, name)  # an Ice Trap's location, so its kind gets recorded for the spoiler
        if target is None:
            raise ValueError(f"{name}: {item.name} can't be given by the get scene (the item rule should have "
                             f"kept it out)")
        group = ch.TRAP_NAMES[trap] if trap != "ice" else item.name
        scene_drops[name] = group
        by_tag.setdefault(group, []).append(name)
    flagless = sorted(n for n in scene_drops if _flagless_spot(_lookup(n)))
    # Junk with a touch pickup of its own drops as itself there (drops FLAGLESS OWN), recorded by the spot's checked
    # bit. No tag, no borrowed flag, no get scene.
    own = sorted(n for n in flagless if _flagless_own(_lookup(n), scene_drops[n]))
    for n in own:
        by_tag[scene_drops[n]].remove(n)
        del scene_drops[n]
    flagless = [n for n in flagless if n not in own]
    for k, it in enumerate(sorted({scene_drops[n] for n in scene_drops if n not in flagless})):
        tag_of[it] = drop_tools.SCENE_DROP_TAG0 + k
        names = [n for n in by_tag[it] if n not in flagless]
        target = (_trap_group_target(it) if it in TRAP_GROUPS else _scene_target(it, names[0]))
        pickups.append({"location": ", ".join(names), "tag": tag_of[it], "item": it, "target": target,
                        "quiet": it in drop_tools.QUIET_JUNK})
    # Flagless drops get a tag and a borrowed saved flag each (tools/rando/free_flags.py), after the per-item tags.
    import free_flags  # tools/rando/free_flags.py
    flags = dict(zip(flagless, free_flags.take(len(flagless)))) if flagless else {}
    _borrowed[id(world)] = sorted(flags.values())  # other plugins borrowing flags skip these (parity/fairies.py)
    next_tag = drop_tools.SCENE_DROP_TAG0 + len(tag_of)
    own_tag = {}
    visits = drop_tools.flagless_visits(flagless)  # the get scene sets the spot's visit bit first (drops VISIT)
    for k, n in enumerate(flagless):
        own_tag[n] = next_tag + k
        it = scene_drops[n]
        pickups.append({"location": n, "tag": own_tag[n], "item": it, "target": _scene_target(it, n),
                        "flag": flags[n], "visit": visits[n], "quiet": it in drop_tools.QUIET_JUNK})
    tag_looks_items = {tag_of[it]: ("Ice Trap", by_tag[it][0]) if it in TRAP_GROUPS else (it, None) for it in tag_of}
    tag_looks_items.update({own_tag[n]: (scene_drops[n], n) for n in flagless})
    scene_drops = {n: own_tag.get(n) or tag_of[it] for n, it in scene_drops.items()}
    gifts = []  # scene gifts (remake_gc_pot_prize, remake_zd_grotto_rupees): songs_trade builds their steps
    for name in sorted(kept):
        e = _lookup(name)
        if not _gift(e):
            continue
        item = world.get_location(name).item
        target = _scene_target(item.name, name)
        if target is None:
            raise ValueError(f"{name}: {item.name} can't be given by its scene (the item rule should have kept it out)")
        gifts.append({"location": name, "item": item.name, "target": target, "gift": e["scene_gift"],
                      "placements": list(e.get("placements", []))})
    _scene_gifts[id(world)] = gifts
    # Disguised ice traps (remake_empty_object_contents "ice_trap", remake_drop_ice_traps "disguised") get one hook
    # branch for the carrier's fallthrough tag. The GV waterfall heart is the carrier's only placement, and it keeps its
    # own answer through a name whenever it stays that type.
    conv = _disguised.get(id(world), set())
    dis = sorted(n for n in kept if assignments[n] == "Ice Trap" and n not in scene and _lookup(n).get("kind") == "drop"
                 and n not in scene_drops and (_cfg.get("ice") == "disguised" or n in conv))
    fall, named = None, []
    if dis:
        d = _map()["disguise"]
        fall = {d["pack"]: d["tag"]}
        pickups.append({"location": f"{len(dis)} drop spots (disguised ice traps)", "tag": d["tag"],
                        "item": "Ice Trap", "target": {"ice_trap": True}, "disguise": True})
        gv, ge = d["spot"], _lookup(d["spot"])
        held = assignments.get(gv) or world.get_location(gv).item.name
        g = _gives(ge, held, contents)
        stays = gv not in kept or (gv not in scene and len(g) > 1 and g[1] == drop_tools.DISGUISE_ACTOR)
        if stays:  # still that type, and unnamed it would be a trap too, so its name keeps the vanilla answer
            named.append(dict(ge, get_scene=dict(ge["get_scene"], value=drop_tools.GET_SCENE_VANILLA_ANSWER)))
    _scene_pickups[id(world)] = pickups
    if _cfg.get("judge"):  # the rules keep hidden vanilla out; anything left is a bug, not a seed
        for name in sorted(kept):
            e, it = _lookup(name), assignments[name]
            why = None if name in scene or _same_name(e, it) else _hidden_vanilla(e, it, contents, name in conv)
            if why and _avoid_vanilla["on"]:
                raise ValueError(f"{name}: {it} plays as the vanilla spot ({why})")
    notes = {}
    if _nothing_elsewhere.get(id(world)):
        notes["_notes_drops_nothing"] = [f"{n}: OoTR's Nothing given as {it} (remake_empty_object_contents "
                                         f"{_cfg.get('empty')!r})" for n, it in _nothing_elsewhere[id(world)]]
    if _bug_note.get(id(world)):
        notes["_notes_drops_bugs"] = list(_bug_note[id(world)])
    if gifts:
        notes["_notes_drops_scene_gifts"] = [f"{g['location']}: {_gift_name(g)} ({g['gift']['group']} scene)" for g in gifts]
        given = {g["location"] for g in gifts}  # their edits are the scene's (_drops_gifts.py), not plan_ops'
        assignments = {n: it for n, it in assignments.items() if n not in given}
    if not assignments:
        return _after_plan_ops(notes, settings, world)
    looks = _looks(settings, world, scene) if _remake(settings, "remake_item_looks") == "item" else None
    dlooks = _disguise_looks(world) if fall and looks is not None else None
    sw = _ammo_sw()  # container ammo shows the Blue Rupee while you have no container (container check in drops.py)
    tag_looks = ({t: (drop_tools.item_display(_trap_look(settings, world, loc) or "") if it == "Ice Trap"
                      else drop_tools.item_display(it, ammo_switch=sw)) for t, (it, loc) in tag_looks_items.items()}
                 if looks is not None else None)
    lake_looks = _lake_looks(settings, world) if looks is not None else None
    silver_looks = _silver_looks(settings, world) if looks is not None else None
    from . import _ammo  # remake_ammo_without_container (generate configured it)
    out = drop_tools.plan_ops(assignments, allow=allow, scene=scene, empty=_cfg.get("empty", "vanilla"),
                              ice=_cfg.get("ice", "classic"), overrides=_ov or None, named=named, fallthrough=fall,
                              disguise_names=conv, looks=looks, disguise_looks=dlooks, scene_drops=scene_drops,
                              drop_looks=tag_looks, flag_spots=flags, lake_looks=lake_looks,
                              silver_looks=silver_looks, ammo_rupee=_ammo.mode() == "blue_rupee", flag_own=own)
    # Only the custom ammo types this seed drops get built, with OoTR's amounts (drops.py AMMO_TYPES). Nuts bring a nut
    # bag unless the bag is shuffled.
    used = {(op.get("set") or {}).get("Dynamic.Drop__DropActor") for op in out.get("placements", [])}
    made = drop_tools.ammo_type_ops(used & set(drop_tools.AMMO_TYPES),
                                    _remake(settings, "remake_shuffle_deku_nut_bag") not in (False, "off", None),
                                    looks=_ammo.mode() == "blue_rupee")  # (Type-based displays: the holder)
    for section, ops in made.items():
        out[section] = out.get(section, []) + ops
    if drop_tools.lake_guard_needed(out):  # a Ruto's Letter or Fire Arrows pickup away from the lake: the lake hook
        guard = drop_tools.lake_guard_ops()  # must answer for the lake's own placements only (drops.LAKE_GUARD)
        out.setdefault("placements", []).extend(guard["placements"])
        out.setdefault("ainb", []).extend(guard["ainb"])
        out["_drops_lake_guard"] = {"ai": drop_tools.LAKE_AI, "guard": [list(g[:2]) for g in drop_tools.LAKE_GUARD]}
    if pickups:
        def look(p):
            if p["tag"] in set(scene_drops.values()):
                d = (tag_looks or {}).get(p["tag"])
                where = f"drops {drop_tools.DISGUISE_ACTOR} with tag {p['tag']}"
                if not d:
                    return f"{where}, which keeps its heart model"
                return f"{where}, which shows " + ("/".join(t[1] for t in d["tiers"]) + " (next tier)"
                                                   if "tiers" in d else d["actor"])
            d = (looks or {}).get(p["location"])
            if looks is None or p["location"] not in scene:
                return "the pickup keeps its heart model"
            if not d:
                return "no display model: the pickup keeps its own look"
            return "shows " + ("/".join(t[1] for t in d["tiers"]) + " (next tier)" if "tiers" in d else d["actor"])
        out["_notes_drops_get_scene"] = [f"{p['location']}: {p['item']} (get scene, tag {p['tag']}; {look(p)})"
                                         for p in pickups]
        quiet = {p["location"]: p["tag"] for p in pickups if p.get("quiet") and "," not in p["location"]
                 and p["location"] in scene}
        if quiet:  # heart spots holding junk: read back by drops.verify_touch with the scene drops' junk tags
            out["_drops_quiet_spots"] = dict(sorted(quiet.items()))
    if dis:
        k = len(out.get("_drops_looks_disguise", {}).get("shows", []))
        look = f"shows one of {k} item models at random (_drops_looks_disguise)" if k else "looks like a Piece of Heart"
        out["_notes_drops_disguise"] = [f"{n}: Ice Trap, drops {drop_tools.DISGUISE_ACTOR} ({look}; its get scene "
                                        f"freezes Link)" for n in dis]
    out.update(notes)
    return _after_plan_ops(out, settings, world)


def _after_plan_ops(part, settings, world):
    """Runs after plan_ops and merges into this plugin's plan part (list sections get appended). It bypasses the Deku
    Tree scrubs' scene for scrubs whose heart or rupee the seed uses (_drops_scrubs.py), and adds no_collectible_hearts
    (OoTR's Hero Mode), the heart-drop edits of _drops_hearts.py. Its twins of heart droppers get the green rupee in
    place."""
    from . import _drops_hearts, _drops_scrubs
    hero = bool(getattr(settings, "no_collectible_hearts", False))
    kept = {n: (_lookup(n), world.get_location(n).item.name) for n in _kept.get(id(world), set())}
    extras = [_drops_scrubs.plan(kept, part.get("placements", []), hero)]
    if hero:
        extras.append(_drops_hearts.plan(kept, part.get("placements", [])))
    for extra in extras:
        for section, value in extra.items():
            part[section] = part.get(section, []) + value if isinstance(value, list) else value
    return part


def _lake_looks(settings, world):
    """remake_item_looks "item": {LH Underwater Item / LH Sun: drops.item_display spec} for the lake pickups that hold
    something other than their vanilla item (drops.py LAKE LOOKS). Like _silver_looks, an Ice Trap shows its disguise
    (_trap_shows) and a Piece of Heart the game's own heart-piece view (_display)."""
    out = {}
    for name, vanilla in drop_tools.LAKE_VANILLA.items():
        try:
            item = world.get_location(name).item
        except (KeyError, AttributeError):
            continue
        if item is None or item.name == vanilla:
            continue
        out[name] = _display(_trap_shows(settings, world, name, item) if item.name == "Ice Trap" else item.name)
    return out


def _silver_looks(settings, world):
    """remake_silver_rupee_items: {silver token Name: drops.item_display spec or None}. Each token shows the item its
    spot gives (SILVER LOOKS), and an Ice Trap shows its disguise (_trap_shows, same as ice traps at the drops'
    get-scene spots). Every item shows something. Without that, a heart, a Rupees (5) or a trap whose drawn look has no
    model (Buy Magic Bean) would show nothing. The spot's own Rupees (5) shows its blue rupee and a Piece of Heart the
    game's own heart-piece view (_display)."""
    from parity import _dungeons_silver as silver
    if not silver.enabled(settings):
        return {}
    out = {}
    for puzzle, n, name, token, hashes in silver.spots():
        try:
            item = world.get_location(name).item
        except (KeyError, AttributeError):
            continue
        if item is None:
            continue
        out[token] = _display(_trap_shows(settings, world, name, item) if item.name == "Ice Trap" else item.name)
    return out


def _display(look):
    """drops.item_display of OoTR item `look` (with the AMMO SWITCH), for a carrier that isn't a heart piece (the silver
    token, the lake pickups, a get-scene spot's heart container or key). A Piece of Heart shows the game's own
    heart-piece view (drops.HEART_PIECE_VIEW). item_display gives it none, since a heart-piece carrier already is one.
    OoTR's "Nothing" (remake_empty_object_contents "nothing", the get scene gives nothing) shows the same heart-piece
    view. That's the look every other get-scene spot holding it has (a heart-piece carrier keeps its own model), and not
    the carrier's vanilla item, otherwise the lake pickups would show the Fire Arrows or Ruto's Letter."""
    spec = drop_tools.item_display(look, ammo_switch=_ammo_sw()) if look else None
    if spec is None and look and (look.startswith("Piece of Heart") or look == "Nothing"):
        spec = {"actor": drop_tools.HEART_PIECE_VIEW}
    return spec


def _looks(settings, world, scene):
    """remake_item_looks "item": {get-scene location: drops.item_display spec or None}, what each spot shows. An Ice
    Trap shows its looks_like_item (OoTR's ice_trap_appearance). One made after the fill (OoTR's "Nothing" turned into a
    trap) draws one the same way, from its own random stream so nothing else in the seed moves (_trap_shows). A Piece of
    Heart keeps a heart-piece carrier's look. On any other carrier (a boss's heart container, the Bottom of the Well's
    key) it shows the game's heart-piece view (_display, drops.heart_piece_carrier)."""
    out = {}
    for name in sorted(scene):
        item = world.get_location(name).item
        look = _trap_shows(settings, world, name, item) if item.name == "Ice Trap" else item.name
        e = _lookup(name)
        if drop_tools.heart_piece_carrier(e["get_scene"].get("as") or e["placements"][0]["actor"]):
            out[name] = drop_tools.item_display(look, ammo_switch=_ammo_sw()) if look else None
        else:
            out[name] = _display(look)
    return out


def important(item):
    """An item an ice trap can look like under ice_trap_appearance "major_only". My rule is "all the important and key
    items, even story items". That's everything OoTR counts as progression (advancement), wherever the seed's settings
    put it. OoTR's own majoritem also drops dungeon-bound keys, boss keys, dungeon rewards on bosses and songs on song
    spots, but here they count. Still left out, like OoTR's majoritem does: shop items, events and drops, maps and
    compasses, Gold Skulltula Tokens unless tokens open something (bridge / Ganon's boss key / LACS), Bombchus without
    bombchu drops, and every non-progression item (refills, rupees)."""
    if not getattr(item, "advancement", False) or getattr(item, "type", None) in ("Shop", "Event", "Drop"):
        return False
    if getattr(item, "map", False) or getattr(item, "compass", False):
        return False
    if item.type == "Token" or item.name.startswith("Bombchus") or item.name == "Heart Container" or item.name.startswith("Piece of Heart"):
        return bool(item.majoritem)
    return True


def _trap_pool(world):
    """The item names an ice trap can look like (ice_trap_appearance), from the items this seed places (vanilla spots
    and story items included). "major_only" (OoTR's default) takes every important item (important), "junk_only" the
    rest, "anything" both. No shop items, events or drops, and only what the remake can show (_shown_as), each by the
    item it shows. OoTR also only draws items that have a model."""
    mode = getattr(world.settings, "ice_trap_appearance", "major_only")
    placed = {(loc.item.name, important(loc.item)) for loc in world.get_locations()
              if loc.item is not None and loc.item.name != "Ice Trap"
              and getattr(loc.item, "type", None) not in ("Shop", "Event", "Drop")}
    if mode == "major_only":
        pool = {n for n, imp in placed if imp}
    elif mode == "junk_only":
        pool = {n for n, imp in placed if not imp}
    else:
        pool = {n for n, _ in placed}
    return sorted({s for s in map(_shown_as, pool) if s})


def _shown_as(name):
    """The item an ice trap disguised as OoTR item `name` shows here, or None if the remake has no model for it. OoTR
    only draws disguises from items with a model (Fill.py: its fallback major_items need an item index, and its pools
    hold no event items). Here the model is drops.item_display's, or the game's own heart-piece view (_display). An item
    without one shows the item OoTR names as its alias (ItemList 'alias'), so Buy Magic Bean, the bean salesman's
    vanilla item, is the Magic Bean. Without that, a silver rupee whose trap drew Buy Magic Bean showed nothing. Deliver
    Letter and Sell Big Poe (no model), the trap itself and Nothing show nothing."""
    from Item import ItemInfo
    info = ItemInfo.items.get(name)
    alias = ((info.special if info is not None else None) or {}).get("alias")
    for n in (name, alias[0] if alias else None):
        if n and n not in ("Ice Trap", "Nothing") and (
                n.startswith("Piece of Heart") or drop_tools.item_display(n) is not None):
            return n
    return None


def _trap_shows(settings, world, name, item):
    """The item OoTR Ice Trap `item` at location `name` shows. That's OoTR's looks_like_item (ice_trap_appearance), by
    the item it shows (_shown_as). If OoTR gave it none, because it was made after the fill (OoTR's "Nothing" turned
    into a trap), or gave it a look the remake can't show (ice_trap_appearance "anything" can pick Nothing), it draws
    one from _trap_pool. That uses its own random stream, so nothing else in the seed moves (_trap_look)."""
    like = getattr(item, "looks_like_item", None)
    return (_shown_as(like.name) if like is not None else None) or _trap_look(settings, world, name)


def _trap_look(settings, world, name):
    pool = _trap_pool(world)
    if not pool:
        return None
    return random.Random(f"{getattr(world.settings, 'seed', '')}:{name}:ice_trap_look").choice(pool)


DISGUISE_LOOKS_MAX = 96  # random picks in the carrier's AI (one create node each); a seed has about 60


def look_actors(name):
    """The display actors item `name` can show: its own, or one per tier for a progressive item, since a disguise can
    show any tier (a Longshot is as tempting as a Hookshot). Tiers without a display model are left out."""
    import progressive as prog
    if name in prog.PROGRESSIVE:
        return {a for a in (drop_tools.display_actor(t) for t in prog.PROGRESSIVE[name]["tiers"]) if a}
    d = drop_tools.item_display(name)
    return set(drop_tools._shows(d)) if d else set()


def _disguise_looks(world):
    """What the disguised ice trap can look like ([drops.item_display spec]). OoTR gives each trap a looks_like_item,
    but a dropped carrier can't tell which spot dropped it, so it picks one of these at random when it appears
    (drops.look_ops "disguise"). That's every display model of _trap_pool's items, each equally likely. Over
    DISGUISE_LOOKS_MAX we take a sample, from its own random stream so nothing else in the seed moves. Empty means the
    carrier keeps its heart look."""
    actors = sorted(set().union(*(look_actors(n) for n in _trap_pool(world))))
    if len(actors) > DISGUISE_LOOKS_MAX:
        rng = random.Random(f"{getattr(world.settings, 'seed', '')}:disguise_looks")
        actors = sorted(rng.sample(actors, DISGUISE_LOOKS_MAX))
    return [{"actor": a} for a in actors]


def in_game(world, loc):
    """For tools/rando/no_vanilla.report: (plays_as_vanilla, how) for location `loc` if it's one of this plugin's spots
    in this seed, else None. Judged from what the patch makes the spot give (drop actor, empty table, own drop, type
    swap, get scene), not from the item's name. OoTR's "Nothing" that leaves a pot's own random drop plays as vanilla, a
    "Nothing" that empties it doesn't, and a green rupee in a bomb boulder (which drops one by itself) does."""
    if loc.name not in _kept.get(id(world), set()) or loc.item is None:
        return None
    e = _lookup(loc.name)
    if e is None:
        return None
    name = loc.item.name
    disguised = loc.name in _disguised.get(id(world), set())
    g = _gives(e, name, _cfg.get("contents", "safe"), disguised)
    if _gift(e):
        how = {"gc_pot": "the spinning pot's heart-piece scene gives", "zd_grotto": "the grotto's entry scene gives"}
        same = _hidden_vanilla(e, name, _cfg.get("contents", "safe"))
        return (True, same) if same else (False, f"{how.get(e['scene_gift']['group'], 'its scene gives')} {name}")
    if g[0] == "scene":
        same = _hidden_vanilla(e, name, _cfg.get("contents", "safe"), disguised)
        return (True, same) if same else (False, f"the get scene gives {name}")
    if g[0] == "own":
        return True, "the object keeps its own drop (remake_empty_object_contents 'vanilla')"
    if g[0] == "empty":
        return (True, "drops nothing, as in the vanilla game") if drop_tools.empty_in_vanilla(e) else (False, "drops nothing (the empty table)")
    own = _vanilla_pickups(e) | ({drop_tools.remake_drop(e["vanilla"])} if e.get("vanilla") else set())
    if g[1] is not None and g[1] in own:
        return True, f"gives {g[1]}, the spot's own vanilla pickup"
    return False, f"gives {g[1]}"


def borrowed_flags(world):
    """The saved flags (tools/rando/free_flags.py) this seed's flagless drops borrow (after world_plan)."""
    return list(_borrowed.get(id(world), []))


def claimed_rows(world):
    """Scene IDs (config/scene_rows.json) this seed's drops take for themselves. That's the ZD storms grotto gift's row
    when that gift is on (known from keep_locations). parity/chests.py budgets the rows."""
    out = []
    for e in (_map().get("scene_gifts") or {}).values():
        g = e["scene_gift"]
        if g["group"] in (_cfg.get("gifts") or ()) and g.get("row") and g["row"] not in out:
            out.append(g["row"])
    return out
