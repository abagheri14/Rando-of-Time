"""Parity plugin: OoT Randomizer's "appearance matches contents" settings (pots, crates, beehives, chests).

Data: data/rando/appearance_objects.json (built from the
game files by tools/rando/parity/_appearance_build.py) and data/rando/appearance_colours.json (the colours).

What the remake can show without code (Longshot only loads files):
- Wooden crates (Obj_BrokenBox_A_01 and the types sharing its model) and lift rocks (Obj_LiftRock_A_01/_A_03)
  declare three per-placement colour multipliers, Dynamic.GameModelController_GeneralInstanceParam0..2, that their
  material multiplies its albedo by. Vanilla levels already use them (Gerudo Fortress crates 1.75 grey, Death
  Mountain rocks 1.27/0.92/0.65 red-brown...). A crate or rock holding a shuffled item gets a colour:
    correct_potcrate_appearances textures_unchecked: gold on every one holding a shuffled item;
    textures_content: OoTR's category colour (major gold, boss key purple, small key silver-blue, token green,
    heart red), only for the categories in potcrate_textures_specific, and anything else keeps its look.
  A checked crate is broken and a lifted rock is thrown and gone, so the colour shows exactly on unchecked ones.
  Which crates and rocks hold a shuffled item comes from the drops plugin (tools/rando/parity/drops.py), from its
  world_plan result (the placements it gives Drop__DropActor) and the locations it keeps. Remake-only extras
  (grass, rocks, crates) count as soon as that plugin gives them items.
- Chests (options, off by default, that's my call): a chest's look can only change with its type.
  The remake's chest types are small (Obj_TBox_A_01, and the Lens chest Obj_TBox_GlassTruth_A_01 with the same model
  and opening), big (Obj_TBox_A_02) and the ornate boss-key big chest (Obj_TBox_A_03). Each has a _NoBake twin that
  only skips the level's light bake, and there's no small fancy or key chest. correct_chest_appearances (OoTR's
  meanings):
    textures: same size; a big chest holding a boss key becomes the ornate one, any other big chest the plain one;
    both / classic: majors and boss keys in big chests (boss keys ornate), everything else in small ones (classic:
    OoTR's older rule, no chest_textures_specific; small keys would take a small fancy chest, which doesn't exist);
    every mode also colours the stone pedestal under 27 chests (Obj_TBoxPedestal_A_01/_A_02, the colour keys).
  invisible_chests: small chests become the Lens chest where the level already places it (6 levels). Big chests
  have no invisible type and stay visible.
  A chest only takes a type its level already places (a type new to a level broke Kokiri Forest), and it keeps its
  opened flag (Bool64bitKey of its placement hash, not of its type). It only changes size when its scene follows:
  no story/minigame scene of its own, no vanilla item scene that stays, room for a big chest (no object or pedestal
  in the way), and type-bound scenes (progressive items, ice traps, dungeon items) only once shared code follows
  the new type (_aware). chest_actor(world, rid) gives
  other plugins the final type. MimicTexture is declared on chests but nothing reads it (no AI, logic or AS file,
  not the executable).
- Pots (Obj_Pot_A_01..08) and grass (A_01, A_03) have no look setting. There's one pot type per level, so no type
  to swap to, and their materials don't have the colour graph. So they change look at run time instead
  (tools/rando/parity/_marker.py). A placement holding a shuffled item gets the Name RandoUnchecked, and its type's
  root AI tints it with the game's blue "stunned" tint while its Name is that. Blue is the only colour on offer, so
  in textures_content the ones holding a category the setting colours turn blue.
- An object that comes back after its check (no save flag, a reset group, an item whose second pickup changes
  nothing: drops.plan_ops) keeps its own look whatever its type (comes_back_after_check), so a marked object is
  always an unchecked one.
The same run-time marker also covers flying pots, beehives, stone crates, the bombable rocks, the Goron City wall
crack and the Hyrule Field bushes (through the root AI the drops plugin gives them, drops.NEW_AI_DROPPERS), the
Gerudo cow skulls and hanging signs, icicles, falling icicles, palm fruit, red ice and silver rocks, and also the
trees and the butterfly fairies. Trees and cow skulls stand after their check, so their tint also waits on it and
goes the moment they're checked (_marker.MARK_GATE).
TODO: the special chests (ice-trap A_04, check-actor A_06, Treasure Chest Game) still can't be marked, so they keep
their look under every setting.
soa_unlocks_*: a placement's look is fixed level data, so it can't wait for the Stone of Agony.
"""
import json
import os
import random
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OBJECTS = os.path.join(HERE, "data", "rando", "appearance_objects.json")
COLOURS = os.path.join(HERE, "data", "rando", "appearance_colours.json")
DROP_MAP = os.path.join(HERE, "data", "rando", "drop_map.json")
CATEGORIES = ("major", "bosskeys", "keys", "tokens", "hearts")
MINOR = ("bombchus", "shields", "capacity")

OWNS = {
    "correct_potcrate_appearances": ("off", "textures_content", "textures_unchecked"),
    "potcrate_textures_specific": None,  # any subset of CATEGORIES (OoTR checks the names)
    "soa_unlocks_potcrate_texture": (False,),
    "correct_chest_appearances": ("off", "textures", "both", "classic"),
    "chest_textures_specific": None,
    "soa_unlocks_chest_texture": (False,),
    "minor_items_as_major_chest": None,  # any subset of MINOR: decides OoTR's category
    "invisible_chests": (False, True),
}
VERIFIED = ()  # TODO: nothing seen in game yet
# Plugins whose world_plan gives drop objects their item (Dynamic.Drop__DropActor on a drop_map placement)
DROP_PLUGINS = ("drops",)
# remake world pickups a drop gives -> OoTR category, for extras with no OoTR location (tools/rando/drops.py DROP_ACTOR)
ACTOR_CATEGORY = {"Obj_Heart_Piece": "hearts", "Obj_Heart_Container": "hearts", "Obj_Token_Gold": "tokens",
                  "Obj_Dungeon_SmallKey": "keys", "Obj_Armor_Goron": "major", "Obj_Armor_Zora": "major",
                  "Obj_Arrow_Fire": "major", "Obj_Bottle_Letter": "major"}
SMALL_KEYS = ("SmallKey", "HideoutSmallKey", "TCGSmallKey", "SmallKeyRing", "HideoutSmallKeyRing", "TCGSmallKeyRing")
HEARTS = ("Heart Container", "Piece of Heart")
# drop_map placement categories that hide what they hold (OoTR's pots, crates, beehives and the remake's extras)
CONTAINERS = ("pot", "crate", "beehive", "flying_pot", "grass", "rock_liftable", "rock_bombable", "palm_fruit",
              "gerudo_decoration", "icicle", "icicle_falling", "red_ice", "rock_silver", "bush", "tree",
              "butterfly")  # the last seven came with the marker's new types
# Trees and cow skulls stand after their check, so their tint waits on it (_marker.MARK_GATE).
# A chest the patcher leaves alone (no OoTR location) keeps its vanilla item, so its category comes from the remake
# actor. First match wins, small items go as config/chest_rules.json, and the Treasure Chest Game key stays brown
# like OoTR's.
REMAKE_CHEST_ITEM = (("^Item_Dungeon_BossKey$", "bosskeys"), ("^(Item_Dungeon_SmallKey$|Obj_Dungeon_SmallKey)", "keys"),
                     ("^(Obj_Heart_Piece|Obj_Heart_Container)$", "hearts"), ("^(Obj_Token_Gold|Item_Token)", "tokens"),
                     ("^Item_Dungeon_(Map|Compass)$", None))

_cache = {}


def _load(name, path):
    if name not in _cache:
        _cache[name] = json.load(open(path, encoding="utf-8"))
    return _cache[name]


def objects():
    return _load("objects", OBJECTS)


def colours():
    return _load("colours", COLOURS)


def check_settings(settings):
    problems = []
    if getattr(settings, "soa_unlocks_potcrate_texture", False) or getattr(settings, "soa_unlocks_chest_texture",
                                                                           False):
        problems.append("soa_unlocks_potcrate_texture / soa_unlocks_chest_texture: a placement's colour is fixed "
                        "level data, so it can't change when the Stone of Agony is found (no code hooks)")
    for name, allowed in (("potcrate_textures_specific", CATEGORIES), ("chest_textures_specific", CATEGORIES),
                          ("minor_items_as_major_chest", MINOR)):
        bad = [v for v in getattr(settings, name, []) or [] if v not in allowed]
        if bad:
            problems.append(f"{name}: unknown {bad} (OoTR's choices: {', '.join(allowed)})")
    return problems


def untested(settings):
    out = []
    if settings.correct_potcrate_appearances != "off":
        out.append(f"correct_potcrate_appearances {settings.correct_potcrate_appearances}: crates and lift rocks "
                   f"holding a shuffled item coloured per placement (GameModelController_GeneralInstanceParam0..2)")
    mode = settings.correct_chest_appearances
    if mode != "off":
        out.append(f"correct_chest_appearances {mode}: chest types swapped by contents ("
                   + ("boss keys in the ornate big chest, everything else in the plain big chest" if mode == "textures"
                      else "majors and boss keys in big chests, the rest in small ones")
                   + ") where the level already places the type; chest pedestals coloured by contents")
    if settings.invisible_chests:
        out.append("invisible_chests: small chests become the Lens chest (Obj_TBox_GlassTruth_A_01) in the six "
                   "levels that place it; whether the remake lets Link open one without the Lens is unverified")
    return out


# Categories
def category(item, settings):
    """OoTR's chest/pot texture category of an item (Patches.py chest_type: GILDED major, GOLD boss key, SILVER
    small key, SKULL token, HEART heart), or None for the plain brown look. Ice traps look like their
    looks_like_item, as in OoTR."""
    if item is None:
        return None
    look = getattr(item, "looks_like_item", None) or item
    name, typ = look.name, look.type
    minor = getattr(settings, "minor_items_as_major_chest", []) or []
    if typ in ("BossKey", "GanonBossKey"):
        return "bosskeys"
    if typ in SMALL_KEYS:
        # OoTR forces the Treasure Chest Game keys brown while that game's keys stay vanilla
        if typ.startswith("TCG") and getattr(settings, "shuffle_tcgkeys", "vanilla") == "vanilla":
            return None
        return "keys"
    if typ == "Token":
        return "tokens"
    if name in HEARTS or name.startswith("Piece of Heart"):
        return "hearts"
    if name.startswith("Bombchus"):
        return "major" if getattr(settings, "free_bombchu_drops", False) or "bombchus" in minor else None
    if name in ("Deku Shield", "Hylian Shield"):
        return "major" if "shields" in minor else None
    if name in ("Deku Nut Capacity", "Deku Stick Capacity"):
        return "major" if "capacity" in minor else None
    if typ in ("Map", "Compass", "Shop", "Drop", "Event", "Refill", "GSToken"):
        return None
    if name == "Ice Trap":  # no disguise: OoTR's ice-trap item row is a gilded chest
        return "major"
    if look.advancement or look.priority:
        return "major"
    return None


def remake_category(actor):
    """Category of a remake item actor (a chest the patcher leaves with its vanilla item)."""
    for rx, cat in REMAKE_CHEST_ITEM:
        if re.match(rx, actor or ""):
            return cat
    small = _load("chest_rules", os.path.join(HERE, "config", "chest_rules.json"))["chest_size"]["small_items"]
    if re.match(small, actor or ""):
        return None
    return "major" if (actor or "").startswith("Item_") else None


def _location_item(world, name):
    try:
        return world.get_location(name).item
    except (KeyError, AttributeError):
        return None


def tint_op(file, hash_, rgb):
    keys = objects()["tint_keys"]
    return {"file": file, "hash": str(hash_), "set": {f"Dynamic.{k}": float(v) for k, v in zip(keys, rgb)}}


# Pots and crates
def _drop_index():
    if "drop_index" not in _cache:
        m = _load("drop_map", DROP_MAP)
        idx = {}
        for sec in ("drops", "new", "extras"):  # "new": remake objects added as OoTR locations (by location name)
            for name, e in m.get(sec, {}).items():
                for p in e.get("placements", []):
                    idx[(p["file"], str(p["hash"]))] = (sec, name, p)
        _cache["drop_index"] = idx
    return _cache["drop_index"]


def drop_holders(settings, world, log):
    """{(file, hash): (section, name, placement, remake pickup)} for every drop object holding a shuffled item. That's
    the placements a drop plugin's world_plan gives Drop__DropActor, plus the placements of the locations it keeps
    whose item needs no edit (a shuffled item equal to the old fixed drop)."""
    idx = _drop_index()
    out = {}
    for pname in DROP_PLUGINS:
        mod = sys.modules.get(f"parity.{pname}")
        if mod is None:  # the plugin is not part of this seed: nothing it shuffles
            log.setdefault("drop_plugins_missing", []).append(pname)
            continue
        state = random.getstate()  # the generator runs world_plan again, so this preview mustn't use up its draws
        try:
            sub = mod.world_plan(settings, world) or {}
        except Exception as e:  # noqa: BLE001 - its own run reports the error; we only read its result
            log.setdefault("drop_plugin_errors", []).append(f"{pname}: {e}")
            sub = {}
        finally:
            random.setstate(state)
        ov = getattr(mod, "_ov", {}) or {}  # its settings' view of a spot (remake_reset_group_objects frees objects)

        def seen(entry):
            sec, name, p = entry
            for q in (ov.get(name) or {}).get("placements", []):
                if (q["file"], str(q["hash"])) == (p["file"], str(p["hash"])):
                    return sec, name, q
            return entry
        for op in sub.get("placements", []):
            actor = (op.get("set") or {}).get("Dynamic.Drop__DropActor")
            key = (op["file"], str(op["hash"]))
            if "twin" not in op:  # what it sets on the object, its unchecked Presence and its flag (_marker cues)
                _drop_sets.setdefault(id(world), {}).setdefault(key, {}).update(op.get("set") or {})
            if "Name" in (op.get("set") or {}):  # named by that plugin (its get scene): no other Name fits there
                _named.setdefault(id(world), set()).add(key)
            if actor is not None and key in idx:
                out[key] = seen(idx[key]) + (actor,)
        kept = getattr(mod, "_kept", {}).get(id(world), set())
        m = _load("drop_map", DROP_MAP)
        for name in kept:
            e = (mod.drop_tools.lookup(name, m) if hasattr(getattr(mod, "drop_tools", None), "lookup")
                 else m["drops"].get(name) or m.get("new", {}).get(name) or m["extras"].get(name)) or {}
            if e.get("kind") != "drop":
                continue
            for p in e.get("placements", []):
                key = (p["file"], str(p["hash"]))
                out.setdefault(key, seen((("drops" if name in m["drops"] else "extras"), name, p)) + (p.get("drop"),))
    return out


def potcrate_plan(settings, world, log):
    mode = settings.correct_potcrate_appearances
    if mode == "off":
        return []
    acts, pal = objects()["actors"], colours()
    specific = set(getattr(settings, "potcrate_textures_specific", CATEGORIES) or ())
    from parity import _marker
    import drops as drop_tools
    # The respawn model (drops.CHECKED_ARRAY). With remake_drop_contents "all" the drops plugin allows
    # checked_on_pickup, and a checked object gets replaced by its unmarked vanilla twin, so it can always be marked.
    from parity import drops as drops_plugin
    respawn = drops_plugin._remake(settings, "remake_drop_contents") == "all"  # its default is "all"
    ops, marked, plain, cats, back = [], Counter(), Counter(), Counter(), Counter()
    for (file, hash_), (sec, name, p, actor) in sorted(drop_holders(settings, world, log).items()):
        if p["category"] not in CONTAINERS:
            continue  # Gold Skulltulas and freestanding pickups show what they are
        item = _location_item(world, name)  # extras have no OoTR location unless a plugin adds one
        info, ai = acts.get(p["actor"]), _marker.ai_for(p["actor"])
        cue = _marker.cue_for(p["actor"], (file, hash_))  # the tint by Name, an effect, or a type of ours
        if cue is not None and cue[0] != "name":
            ai = None
        if (not info or info["tint"] != "proven") and cue is None:
            plain[f"{p['category']} ({p['actor']})"] += 1
            continue
        # An effect cue is only present while the spot's check flag is unset (_marker.unchecked_presence), so it goes
        # once checked even where the item comes back. A look on the object itself would stay.
        gated = cue is not None and cue[0] == "effect" and \
            _marker.unchecked_presence(_drop_sets.get(id(world), {}).get((file, hash_), {}))[0] is not None
        if comes_back_after_check(p, item, actor) and not (respawn and drop_tools.respawn_model_spot(p)) and not gated:
            back[f"{p['category']} ({p['actor']})"] += 1
            continue
        if ai is not None and (file, hash_) in _named.get(id(world), ()):
            plain[f"{p['category']} ({p['actor']}: named by its drop plugin)"] += 1
            continue
        if mode == "textures_unchecked":
            rgb, cat = pal["unchecked"], "unchecked"
        else:
            cat = category(item, settings) if item is not None else ACTOR_CATEGORY.get(actor)
            if cat not in specific:
                plain[f"{p['category']} ({cat or 'brown'}: original look)"] += 1
                continue
            rgb = pal["categories"][cat]
        if cue is not None and cue[0] == "name":  # the run-time blue marker (tools/rando/parity/_marker.py)
            ops.append(_marker.mark_op(file, hash_, cue[1]))
            _marker_files.setdefault(id(world), set()).add(ai)
            if cue[1] == _marker.PLAIN_NAME:
                _marker_plain.setdefault(id(world), set()).add(ai)
            cat = f"{cat} (blue marker)"
        elif cue is not None and cue[0] == "effect":  # an effect at it while unchecked (_marker cues)
            presence, steps = _marker.unchecked_presence(_drop_sets.get(id(world), {}).get((file, hash_), {}))
            if presence is None or not p.get("pos"):
                plain[f"{p['category']} ({p['actor']}: no unchecked condition for its effect)"] += 1
                continue
            ops += _marker.effect_ops(file, hash_, p["pos"], presence, cue[1], _marker.lift_for(p["actor"]))
            _marker_exps.setdefault(id(world), {}).update(steps)  # a tree's bit, see finish_plan
            cat = f"{cat} (effect {cue[1]})"
        elif cue is not None and cue[0] == "type":  # a type of ours that shows it (_marker cues: butterflies)
            ops.append({"file": file, "hash": str(hash_), "set": {"Gyaml": cue[1]}})
            _marker_types.setdefault(id(world), set()).add(cue[1])
            cat = f"{cat} ({cue[1]})"
        else:
            ops.append(tint_op(file, hash_, rgb))
        marked[p["category"]] += 1
        cats[cat] += 1
    log["potcrate"] = {"mode": mode, "marked": dict(marked), "colours": dict(cats),
                       "come_back_after_their_check_so_left_plain": dict(back),
                       "holding_shuffled_items_but_no_look_setting": dict(plain)}
    return ops


_named = {}  # id(world) -> placements a drop plugin names (drop_holders)
_drop_sets = {}  # id(world) -> {(file, hash): what the drop plugin sets on it} (drop_holders)
_marker_plain = {}  # id(world) -> gated root AIs a probe build's plain marker also edits
_marker_types = {}  # id(world) -> types of ours the placements become (_marker.TINT_TYPES)
_marker_files = {}  # id(world) -> root AI files the pot/grass marker edits (potcrate_plan -> world_plan)
_marker_exps = {}  # id(world) -> {expression: steps} the tree lights read (potcrate_plan -> world_plan -> finish_plan)


def comes_back_after_check(p, item, actor):
    """True if this drop object comes back after it gave its item. That's the drops plugin's rule (drops.plan_ops): no
    save flag, a reset group, or an item whose second pickup changes nothing. A look there would say "unchecked"
    forever, so it keeps its own. Objects holding any other item stay gone once checked (flag made permanent), or only
    come back until the item is taken (checked on pickup)."""
    import drops as drop_tools
    item_name = getattr(item, "name", None) or ""
    if not drop_tools.repeatable(item_name, actor):
        return False
    return p["flag"] is None or bool(p.get("reset_group")) or item_name in drop_tools.REPEATABLE_ITEMS


# Chests
def _chest_locations():
    """({remake chest hash: [OoTR location names]}, {remake chest hash: vanilla remake item}) from
    data/rando/chest_map.json, data/rando/chests_locations.json and data/rewards.json."""
    if "chest_names" not in _cache:
        rewards = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))
                   if r.get("kind") == "chest"}
        names = {}
        cm = json.load(open(os.path.join(HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"]
        cl = json.load(open(os.path.join(HERE, "data", "rando", "chests_locations.json"), encoding="utf-8"))
        # chest_map "vanilla" pairs are unreliable and never patched: those chests keep their remake item
        pairs = [(n, v.get("remake")) for n, v in cm.items() if v.get("mode") in ("full", "group")]
        pairs += [(n, v.get("remake")) for sec in ("new", "paired") for n, v in cl.get(sec, {}).items()]
        for name, rid in pairs:
            if rid in rewards:
                names.setdefault(str(rewards[rid]["hash"]), []).append(name)
        vanilla = {str(r["hash"]): r["item"] for r in rewards.values()}
        _cache["chest_names"] = (names, vanilla)
    return _cache["chest_names"]


def chest_item(world, chest_hash):
    """(OoTR item or None, remake item or None, how) for what the chest on a pedestal holds in this seed. A chest with
    an OoTR location holds that location's item (the patch writes it there), and one without keeps its vanilla item."""
    names, vanilla = _chest_locations()
    for name in names.get(chest_hash, []):
        item = _location_item(world, name)
        if item is not None:
            return item, None, name
    return None, vanilla.get(chest_hash), "vanilla (no OoTR location in this seed)"


def pedestal_plan(settings, world, log):
    """Colours the stone pedestal under a chest by its contents. textures and both use OoTR's categories with
    chest_textures_specific, classic uses boss keys and small keys, the categories classic marks."""
    mode = settings.correct_chest_appearances
    if mode == "off":
        return []
    pal = colours()["categories"]
    if mode == "classic":
        specific = {"bosskeys", "keys"}
    else:
        specific = set(getattr(settings, "chest_textures_specific", CATEGORIES) or ())
    ops, cats, seen = [], Counter(), []
    for ped in objects()["pedestals"]:
        if not ped.get("chest_hash"):
            continue
        item, remake, how = chest_item(world, ped["chest_hash"])
        cat = category(item, settings) if item is not None else remake_category(remake)
        cats[cat or "brown"] += 1
        coloured = cat in specific
        if coloured:
            ops.append(tint_op(ped["file"], ped["hash"], pal[cat]))
        seen.append(f"{ped['file'].rsplit('/', 1)[-1]} pedestal {ped['hash']}: {item.name if item else remake} "
                    f"({how}) -> {cat if coloured else 'plain'}")
    log["pedestals"] = {"coloured": len(ops), "categories": dict(cats), "each": seen}
    return ops


# Chest types
# The chest types a look option swaps between. They all share the treasure-chest AI and logic node. The small ones
# (Obj_TBox_GlassTruth_A_01's ActorParam inherits Obj_TBox_A_01's) play Obj_TBox_A_01's opening and default scene
# Dm_SY_TreasureboxSmall, and the big ones (Obj_TBox_A_03's inherits Obj_TBox_A_02's) play Obj_TBox_A_02's opening
# and Dm_SY_Treasurebox. _NoBake twins only differ by not casting into the level's light bake.
FAMILY = {"Obj_TBox_A_01": "small", "Obj_TBox_A_01_NoBake": "small", "Obj_TBox_GlassTruth_A_01": "small",
          "Obj_TBox_A_02": "big", "Obj_TBox_A_02_NoBake": "big", "Obj_TBox_A_03": "big", "Obj_TBox_A_03_NoBake": "big"}
LOOK = {"Obj_TBox_A_01": "plain", "Obj_TBox_A_01_NoBake": "plain", "Obj_TBox_GlassTruth_A_01": "lens",
        "Obj_TBox_A_02": "plain", "Obj_TBox_A_02_NoBake": "plain", "Obj_TBox_A_03": "ornate",
        "Obj_TBox_A_03_NoBake": "ornate"}
TYPES = {("small", "plain"): ("Obj_TBox_A_01", "Obj_TBox_A_01_NoBake"), ("small", "lens"): ("Obj_TBox_GlassTruth_A_01",),
         ("big", "plain"): ("Obj_TBox_A_02", "Obj_TBox_A_02_NoBake"),
         ("big", "ornate"): ("Obj_TBox_A_03", "Obj_TBox_A_03_NoBake")}
DUNGEON_KINDS = ("Small Key", "Boss Key", "Map", "Compass")
# chests with their own behaviour, never retyped (listed when an option would want another look for them)
SPECIAL_FAMILY = {"Obj_TBox_A_04": "small", "Obj_TBox_A_04_NoBake": "small", "Obj_TBox_A_06": "small",
                  "Obj_TBox_A_06_NoBake": "small", "Obj_TBox_A_01_memo11": "small",
                  "Obj_HrlCity_Shop_TBox_A_01": "big", "Obj_HrlCity_Shop_TBox_A_02": "big"}


def _catalog_chests():
    if "chest_catalog" not in _cache:
        _cache["chest_catalog"] = {r["id"]: r for r in json.load(open(os.path.join(HERE, "data", "rewards.json"),
                                                                       encoding="utf-8")) if r.get("kind") == "chest"}
    return _cache["chest_catalog"]


def chests_in_play(world):
    """{remake chest id: OoTR location name} for every chest this seed's patch writes an item into. That's chest_map's
    full/group pairs (the generator) and the chests the chests and dungeons plugins keep."""
    cm = _load("chest_map", os.path.join(HERE, "data", "rando", "chest_map.json"))["chests"]
    out = {}
    for name, v in sorted(cm.items()):
        if v.get("mode") in ("full", "group") and v.get("remake") and _location_item(world, name) is not None:
            out.setdefault(v["remake"], name)
    ch = sys.modules.get("parity.chests")
    if ch is not None:
        kept = (getattr(ch, "_state", {}).get(id(world)) or {}).get("kept", set())
        for name in sorted(kept):
            rid = ch._mine().get(name)
            if rid:
                out.setdefault(rid, name)
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and hasattr(dg, "_kept"):
        for name in sorted(dg._kept(world)):
            rid = dg.WORLD["kept_chests"].get(name)
            if rid:
                out.setdefault(rid, name)
    return out


def _aware(consumer):
    """Whether shared code / a plugin already follows a chest's swapped type when it picks a type-bound scene
    TODO: until it does, those chests keep their size."""
    if consumer == "make_patch":
        try:
            import make_patch  # tools/, on the path while the generator runs
        except ImportError:
            return False
        return hasattr(make_patch, "planned_chest_actor")
    mod = sys.modules.get(f"parity.{consumer}")
    return mod is None or bool(getattr(mod, "APPEARANCE_CHEST_TYPES", False))


def _big_category(cat, settings):
    """OoTR's big chest types: GILDED (major), GOLD (boss key), and the token / heart chests made big when a win
    condition counts them (Patches.py SKULL_CHEST_BIG, HEART_CHEST_BIG)."""
    if cat in ("major", "bosskeys"):
        return True
    counts = {getattr(settings, "bridge", None), getattr(settings, "lacs_condition", None),
              getattr(settings, "shuffle_ganon_bosskey", None)}
    return (cat == "tokens" and "tokens" in counts) or (cat == "hearts" and "hearts" in counts)


def wanted_look(actor, item, settings, current=None):
    """(family, look) the options ask for: family small/big, look plain/ornate/lens."""
    mode, invisible = settings.correct_chest_appearances, settings.invisible_chests
    fam, look = current or (FAMILY[actor], LOOK[actor])
    if mode != "off":
        cat = category(item, settings)
        if mode in ("textures", "both") and cat not in set(getattr(settings, "chest_textures_specific", CATEGORIES)
                                                            or ()):
            cat = None  # like OoTR, an unchecked category shows up in brown chests
        if mode in ("both", "classic"):
            fam = "big" if _big_category(cat, settings) else "small"
        look = ("ornate" if cat == "bosskeys" else "plain") if fam == "big" else "plain"
    if invisible and fam == "small":
        look = "lens"
    return fam, look


def _dungeon_kind(name):
    return next((k for k in DUNGEON_KINDS if name.startswith(k)), None)


def _blockers(rid, r, name, item, target, settings, world, spots):
    """Why chest `rid` has to keep its type for this swap. Empty means it may take `target`."""
    why = []
    old_fam, new_fam = FAMILY[r["actor"]], FAMILY[target]
    if new_fam != old_fam:  # a different opening and default scene
        ev = (r.get("extra") or {}).get("GetEventName")
        if ev:
            rules = _load("chest_rules", os.path.join(HERE, "config", "chest_rules.json"))["get_events"]["location"]
            loc = None
            try:
                loc = world.get_location(name)
            except KeyError:
                pass
            if any(re.search(rx, ev) for rx in rules):
                why.append(f"keeps its own {old_fam}-chest scene {ev} (story/minigame)")
            elif loc is not None and getattr(loc, "vanilla_item", None) == item.name:
                why.append(f"holds its vanilla item, whose {old_fam}-chest scene {ev} stays")
        prog = _load("progressive", os.path.join(HERE, "config", "progressive.json"))["items"]
        if item.name in prog and not _aware("make_patch"):
            why.append("progressive item: make_patch picks the progressive scene by the catalogued chest type")
        if item.name == "Ice Trap" and not _aware("chests"):
            why.append("ice trap: the chests plugin picks the ice-trap scene by the catalogued chest type")
        kind = _dungeon_kind(item.name)
        dg = sys.modules.get("parity.dungeons")
        if kind and dg is not None and not _aware("dungeons"):
            need = dg.needs_scene(item.name, name)
            if need:
                why.append("dungeon item given through the dungeons plugin's scene, picked by the catalogued type")
            elif kind != "Small Key" and new_fam == "small":
                why.append(f"plain {kind} credits its dungeon only from a big chest's opening")
        if new_fam == "big":
            for s_ in spots:
                if s_["pedestal"]:
                    why.append(f"stands on a pedestal made for a small chest ({s_['level']})")
                elif s_["blocked_by"]:
                    why.append(f"no room for a big chest in {s_['level']}: {s_['blocked_by'][0]} "
                               f"{s_['blocked_by'][1]} m away")
    for s_ in spots:
        if target not in s_["accepted_by"]:
            why.append(f"{target} does not accept the placement's settings {s_['dynamic']}")
    return why


def _twinned():
    """Remake chest ids that come with a copy (another layout's twin, a consolation chest sharing the item). The chests
    plugin writes the item into every copy, so a look option can only change all of them or none."""
    if "twinned" not in _cache:
        cl = json.load(open(os.path.join(HERE, "data", "rando", "chests_locations.json"), encoding="utf-8"))
        ids = set()
        for sec in ("new", "paired"):
            for v in cl.get(sec, {}).values():
                if v.get("also"):
                    ids.add(v.get("remake"))
                    ids.update(v["also"])
        _cache["twinned"] = ids
    return _cache["twinned"]


def chest_retypes(world):
    """{remake chest id: decision} for this seed, computed once. A decision is {"from", "to", "location", "item",
    "want", "why"}, with "to" None when it keeps its type. world_plan uses it, and so do plugins that pick a chest scene
    by type (chest_actor)."""
    st = _cache.setdefault("retypes", {})
    if id(world) in st:
        return st[id(world)]
    settings = world.settings
    out = {}
    if settings.correct_chest_appearances == "off" and not settings.invisible_chests:
        st[id(world)] = out
        return out
    cat = _catalog_chests()
    spots_all = objects()["chest_spots"]
    level_types = objects()["chest_types_per_level"]
    for rid, name in sorted(chests_in_play(world).items()):
        r = cat.get(rid)
        if r is None:
            continue
        item = _location_item(world, name)
        d = {"from": r["actor"], "to": None, "location": name, "item": item.name}
        if r["actor"] not in FAMILY:
            fam0 = SPECIAL_FAMILY.get(r["actor"], "small")
            want = wanted_look(None, item, settings, (fam0, "plain"))
            d["want"] = " ".join(want)
            if want != (fam0, "plain"):
                d["why"] = [f"{r['actor']} is a special chest (ice trap, check-actor, memo, Treasure Chest Game) "
                            f"with its own behaviour: it keeps its type"]
                out[rid] = d
            continue
        spots = [s_ for s_ in spots_all.get(str(r["hash"]), []) if s_["file"] in r["files"]]
        fam, look = wanted_look(r["actor"], item, settings)
        d["want"] = f"{fam} {look}"
        if (fam, look) == (FAMILY[r["actor"]], LOOK[r["actor"]]):
            continue
        if r["actor"] == "Obj_TBox_GlassTruth_A_01":
            d["why"] = ["a vanilla Lens chest stays invisible: the remake has no big invisible chest"]
            out[rid] = d
            continue
        if rid in _twinned():
            d["why"] = ["has a twin copy in another layout or level file (data/rando/chests_locations.json 'also'): "
                        "both copies would have to change together, so it keeps its type"]
            out[rid] = d
            continue
        nobake = r["actor"].endswith("_NoBake")
        options = sorted(TYPES[(fam, look)], key=lambda t: t.endswith("_NoBake") != nobake)
        levels = {s_["level"] for s_ in spots}
        target = next((t for t in options if levels and all(t in level_types.get(lv, ()) for lv in levels)), None)
        if target is None:
            d["why"] = [f"{' / '.join(options)} not placed in {', '.join(sorted(levels)) or 'this level'} (a type new "
                        f"to a level broke Kokiri Forest)"]
        else:
            why = _blockers(rid, r, name, item, target, settings, world, spots)
            if why:
                d["why"] = why
            else:
                d["to"] = target
        out[rid] = d
    st[id(world)] = out
    return out


def chest_actor(world, rid):
    """The chest type this seed's patch gives remake chest `rid`, its catalogued type unless a look option swaps it.
    It's for plugins and shared code that pick a type-bound scene (ice traps, dungeon items, progressive items)."""
    d = chest_retypes(world).get(rid)
    if d and d.get("to"):
        return d["to"]
    r = _catalog_chests().get(rid)
    return r["actor"] if r else None


def retype_plan(settings, world, log):
    decisions = chest_retypes(world)
    if not decisions:
        return []
    cat = _catalog_chests()
    ops, swaps, kept = [], Counter(), []
    for rid, d in sorted(decisions.items()):
        if d.get("to"):
            for f in cat[rid]["files"]:
                ops.append({"file": f, "hash": str(cat[rid]["hash"]), "set": {"Gyaml": d["to"]},
                            "note": f"appearance: {d['location']} ({d['item']}): {d['from']} -> {d['to']}"})
            swaps[f"{d['from']} -> {d['to']}"] += 1
        else:
            kept.append(f"{d['location']} ({d['item']}, {d['from']}, wants {d.get('want', '?')}): "
                        + "; ".join(d.get("why", [])))
    log["chest_types"] = {"mode": settings.correct_chest_appearances, "invisible": settings.invisible_chests,
                          "swapped": dict(swaps), "kept_their_type": kept}
    return ops


def cow_plan(settings, world, log, out):
    """The blue light at every cow holding an item, while its item is unchecked (_marker cows)."""
    if settings.correct_potcrate_appearances == "off" or not getattr(settings, "shuffle_cows", False):
        return []
    from parity import _marker
    effect = _marker.CUE_EFFECTS[_marker.CUE_DEFAULT]
    ops, exps, cues = [], {}, {}
    for names, flag, spots in _marker.cow_spots():
        if not any(_location_item(world, n) is not None for n in names):
            continue
        for file, hash_, pos, own in spots:
            presence, steps = _marker.cow_presence(flag, own, len(exps))
            exps.update(steps)
            ops += _marker.effect_ops(file, hash_, pos, presence, effect, _marker.lift_for("Animal_Cow"))
            cues[f"{file}#{hash_}"] = presence
    if exps:
        out["gamedata"] = out.get("gamedata", []) + [{"add_boolexp": exps}]
    if cues:
        out["_marker_cows"] = cues
    log["cow_cues"] = len(cues)
    return ops


def world_plan(settings, world):
    log = {}
    out = {}
    placements = (potcrate_plan(settings, world, log) + pedestal_plan(settings, world, log)
                  + retype_plan(settings, world, log) + cow_plan(settings, world, log, out))
    if log:
        out["_notes_appearance"] = log
    if placements:
        out["placements"] = placements
    marker_ai = _marker_files.pop(id(world), set())
    from parity import _marker
    if marker_ai:
        out["ainb"] = _marker.ainb_ops(marker_ai, _marker_plain.pop(id(world), set()))
    if _marker_types.pop(id(world), None):  # the butterfly cue's two types
        built = _marker.butterfly_ops()
        for k in ("new_files", "packs", "byml", "ainb"):
            out[k] = out.get(k, []) + built[k]
    exps = _marker_exps.pop(id(world), {})
    if exps:  # added by finish_plan, after every plugin's rows
        out["_marker_chk_exps"] = dict(sorted(exps.items()))
    _drop_sets.pop(id(world), None)
    return out


def finish_plan(settings, plan, cfg):
    """Runs once every plugin's plan is in (generate.main). The tree lights' expressions (_marker.CHK_CUE_EXP, "not
    RandoChecked[bit]") read the drops plugin's array, which its own gamedata op adds. Plugins merge in name order and
    make_patch adds rows op by op, so they go in an op of their own, last."""
    exps = plan.pop("_marker_chk_exps", None)
    if exps:
        gd = plan.get("gamedata")
        plan["gamedata"] = ([] if gd is None else [gd] if isinstance(gd, dict) else list(gd)) + [{"add_boolexp": exps}]
