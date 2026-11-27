"""Parity plugin: Archipelago multiworld, the game side (data/archipelago/MAILBOX.md).

usage: python tools/rando/parity/archipelago.py --tables     writes data/archipelago/mailbox.json (item codes,
                                                              GameData names and hashes)
       python tools/rando/parity/archipelago.py --probe OUT   the in-game probe (plans/ap_mailbox_probe.json):
                                                              plan, patch, read-back and CHECKLIST.md in OUT

Only active when the settings hold "remake_archipelago" (tools/archipelago/build_patch.py writes it). Without it
this plugin changes nothing, so single-player seeds stay byte-identical.

- Other players' items: four placeholder OoTR items ("Archipelago Item (Progression)" ...), junk for our own logic.
  At a location that holds one nothing gets added. The chest opens (or the NPC hands over) and a text box says
  "You found <item> for <player>!". The location also sets RandoAP_Found_<AP location id>. No vanilla scene file
  grows, since the mailbox, the found texts and those chests' scenes live in new scene files (renamed copies).
- Received items: the client writes an item code into GameData Bools and raises RandoAP_Signal. One watcher in
  Sequence/MainUpdate.module.ainb requests the event RandoAP_Mailbox, which gives the item the way a single-player
  NPC gift does and counts it in the saved RandoAP_Count bits.

Ported design (not code) from OotrR, https://github.com/Mozencaz/OotrR, MIT License, Copyright (c) 2026 Mozencaz:
patching/ap_mailbox.py (Bool signal written in memory, MainUpdate watcher, item-get event) and archipelago/receive.py
(one signal at a time, retry). The OotrR license text is in data/archipelago/LICENSE-OotrR.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))

MAILBOX_VERSION = 1
SETTING = "remake_archipelago"
REMAKE_INTERNAL = (SETTING,)  # generate.unknown_remake_settings (written by build_patch, not an app setting)
TABLES = os.path.join(HERE, "data", "archipelago", "mailbox.json")

# Placeholders (other players' items)
PLACEHOLDERS = {"progression": "Archipelago Item (Progression)", "useful": "Archipelago Item (Useful)",
                "filler": "Archipelago Item (Filler)", "trap": "Archipelago Item (Trap)"}
PLACEHOLDER_NAMES = frozenset(PLACEHOLDERS.values())

# The mailbox's GameData (all plain saved Bools)
SIGNAL = "RandoAP_Signal"
CODE_BITS, IDX_BITS, COUNT_BITS = 10, 4, 16
CODE = [f"RandoAP_Code{i}" for i in range(CODE_BITS)]
IDX = [f"RandoAP_Idx{i}" for i in range(IDX_BITS)]
COUNT = [f"RandoAP_Count{i}" for i in range(COUNT_BITS)]
SEED_PREFIX = "RandoAP_Seed_"
FOUND_PREFIX = "RandoAP_Found_"
EVENT = "RandoAP_Mailbox"            # the EventSetting row the watcher requests
ENTRY = "RandoAP_Receive"            # its entry (the copied file's own entry already took the file's new name)
# Two new scene files (make_patch "new_files" + NEW_EVENTS), so no vanilla scene grows. The mailbox (about 800 steps)
# would have more than doubled Dm_SY_GetInEvent, which every NPC gift loads, and 167 found texts would have tripled
# GetPouchContent, which every chest loads. Each is a renamed copy of a small vanilla scene file with the actors its
# steps use (same-length rename of the one pooled name), and only the scenes that call it load it.
EVENT_FILE = "RandoAP_Mailbox"           # DmF_SY_FallDown's copy: GameDataActor, PouchSystemActor, UISystemActor,
EVENT_SOURCE = "DmF_SY_FallDown"  # GameSystemActor, EventSystemActor, Player_Event, SoundSystemActor...

# Item types a player can receive (OoTR ItemList). Shop, Event, Drop and Refill entries aren't items you hold.
RECEIVABLE_TYPES = ("Item", "Song", "SmallKey", "SmallKeyRing", "BossKey", "GanonBossKey", "Map", "Compass", "Token",
                    "HideoutSmallKey", "HideoutSmallKeyRing", "TCGSmallKey", "TCGSmallKeyRing", "SilverRupee",
                    "DungeonReward")
NOT_RECEIVABLE = ("Deliver Letter", "Sell Big Poe", "Buy Magic Bean", "Nothing")  # OoTR's internal "Item" rows


def murmur3(name):
    from romtools import murmur3_32
    return murmur3_32(name)


# OoTR hint words for the placeholders. Gossip Stones name what a location holds, and every language falls back to
# these, like the plugins' own items do. They say what the item is to its owner, not who it's for (one text per item
# name).
HINT_WORDS = {"progression": "something important for another world", "useful": "something useful for another world",
              "filler": "something for another world", "trap": "a trap for another world"}


def register_items():
    """Registers the placeholders as OoTR items, plain junk for our own world with no logic, with hint words in every
    language. It's done the extras_items._register_item way, through HintList and each Language's table."""
    import HintList
    import Item
    import ItemList
    import Language
    for cls, name in PLACEHOLDERS.items():
        if name not in ItemList.item_table:
            # Someone else's progression item is marked priority so correct_chest_appearances shows it as a major
            # item, like OoTR multiworld and Archipelago OoT. Our local logic still treats it as junk, like the other
            # placeholders.
            ItemList.item_table[name] = ("Item", False if cls == "progression" else None, None, None)
        if name not in Item.ItemInfo.items:
            Item.ItemInfo.items[name] = Item.ItemInfo(name)
        HintList.hintTable.setdefault(name, (HINT_WORDS[cls], HINT_WORDS[cls], "item"))
    if not getattr(Language.Language.__init__, "remake_archipelago", False):
        original = Language.Language.__init__

        def init(self, lang, _original=original):
            _original(self, lang)
            for c, n in PLACEHOLDERS.items():
                self.hintTable.setdefault(n, {"vague_hint": HINT_WORDS[c], "clear_hint": HINT_WORDS[c],
                                              "gender": "no_gender"})
        init.remake_archipelago = True
        Language.Language.__init__ = init


def _plugin_items():
    """Items our plugins add to OoTR's table (each only under its own settings), in a fixed order."""
    from parity import extras_items, extras_npcs, extras_souls, story
    out = list(extras_items.HINTS) + [extras_npcs.POLE, story.MS_ITEM]
    logic = extras_souls.logic()
    out += [v["item"] for v in logic["bosses"].values()] + [logic["ganon"]["item"]]
    out += [b["item"] for b in logic["beans"]] + [extras_souls.SKELETON]
    from parity import chests  # remake_trap_weights' kinds, as the spoiler (and ids.json) name them
    out += [name for k, name in chests.TRAP_NAMES.items() if k != "ice"]
    return out


def receivable_items():
    """Every item name the game may be sent, OoTR's table order then the plugins' items."""
    from ItemList import item_table
    names = [k for k, v in item_table.items() if v[0] in RECEIVABLE_TYPES and k not in NOT_RECEIVABLE
             and k not in PLACEHOLDER_NAMES]
    return names + [n for n in _plugin_items() if n not in names]


def load_tables():
    if os.path.exists(TABLES):
        return json.load(open(TABLES, encoding="utf-8"))
    return {}


def codes():
    """{item name: code} (data/archipelago/mailbox.json), 1..1023, append-only."""
    return dict(load_tables().get("codes") or {})


def build_tables():
    """mailbox.json: the codes (old ones kept, new items appended) and every GameData name with its hash."""
    old = load_tables()
    table = dict(old.get("codes") or {})
    nxt = max(table.values(), default=0) + 1
    for name in receivable_items():
        if name not in table:
            table[name] = nxt
            nxt += 1
    if nxt - 1 >= 1 << CODE_BITS:
        raise ValueError(f"{nxt - 1} item codes do not fit in {CODE_BITS} bits")
    names = [SIGNAL] + CODE + IDX + COUNT
    return {"_about": "data/archipelago/MAILBOX.md. codes: append-only, 0 = nothing (counted, gives nothing). "
                      "hash = murmur3_32(name), seed 0.",
            "mailbox_version": MAILBOX_VERSION,
            "gamedata": {n: murmur3(n) for n in names},
            "seed_prefix": SEED_PREFIX, "found_prefix": FOUND_PREFIX,
            "event": EVENT,
            "placeholders": PLACEHOLDERS,
            "codes": table}


# Settings
CLASSES = tuple(PLACEHOLDERS)


def _cfg(settings):
    return (getattr(settings, "remake", None) or {}).get(SETTING)


def active(settings):
    return bool(_cfg(settings))


def check_settings(settings):
    """Checks the shape of remake_archipelago (written by tools/archipelago/build_patch.py) before anything is built."""
    cfg = _cfg(settings)
    if cfg is None:
        return []
    import re
    where = SETTING
    if not isinstance(cfg, dict):
        return [f"{where}: a table (data/archipelago/MAILBOX.md section 1)"]
    out = []
    if cfg.get("mailbox_version") != MAILBOX_VERSION:
        out.append(f"{where}.mailbox_version = {cfg.get('mailbox_version')!r}: this patcher builds version "
                   f"{MAILBOX_VERSION}")
    if not isinstance(cfg.get("seed_key"), str) or not re.fullmatch(r"[A-Za-z0-9]{8,16}", cfg["seed_key"]):
        out.append(f"{where}.seed_key = {cfg.get('seed_key')!r}: 8 to 16 letters or digits")
    foreign = cfg.get("foreign", {})
    if not isinstance(foreign, dict):
        return out + [f"{where}.foreign: a table {{location: {{item, player_name, classification, location_id}}}}"]
    ids = set()
    for loc, info in sorted(foreign.items()):
        if not isinstance(info, dict):
            out.append(f"{where}.foreign[{loc!r}]: a table")
            continue
        if not takes_foreign(loc):
            out.append(f"{where}.foreign[{loc!r}]: this location can't hold another player's item "
                       f"(parity.archipelago.takes_foreign)")
        for k in ("item", "player_name"):
            if not isinstance(info.get(k), str) or not info[k].strip():
                out.append(f"{where}.foreign[{loc!r}].{k}: a name")
        if info.get("classification") not in CLASSES:
            out.append(f"{where}.foreign[{loc!r}].classification = {info.get('classification')!r}: "
                       f"one of {', '.join(CLASSES)}")
        lid = info.get("location_id")
        if not isinstance(lid, int) or isinstance(lid, bool) or lid <= 0:
            out.append(f"{where}.foreign[{loc!r}].location_id = {lid!r}: the AP location id (a positive integer)")
        elif lid in ids:
            out.append(f"{where}.foreign[{loc!r}].location_id {lid} is used twice")
        ids.add(lid)
    return out


def before_build(settings):
    if active(settings):  # a single-player seed's OoTR tables stay exactly as they were
        register_items()


# Where another player's item can be shown
_cache = {}


def _json(*path):
    key = "/".join(path)
    if key not in _cache:
        _cache[key] = json.load(open(os.path.join(HERE, *path), encoding="utf-8"))
    return _cache[key]


def _rewards():
    if "rewards" not in _cache:
        _cache["rewards"] = {r["id"]: r for r in _json("data", "rewards.json")}
    return _cache["rewards"]


def _chest_spots():
    """{OoTR location: remake chest id} for data/rando/chest_map.json chests in play (generate.py's own loop)."""
    return {n: v["remake"] for n, v in _json("data", "rando", "chest_map.json")["chests"].items()
            if v["mode"] in ("full", "group") and v.get("remake")}


def _scene_spots():
    """{OoTR location: remake location id}: the core scene locations (generate.scene_locations)."""
    from parity import chests
    return chests._scene_locations()


def _chests_of():
    """{OoTR location: [remake chest ids]} for every chest a plugin puts in play. That's data/rando/chest_map.json's
    (generate.py's own loop), the chests plugin's own (chests_locations.json "new"/"paired", with their "also" copies
    holding the same reward) and the dungeons plugin's kept chests (dungeons_world.json). Not the Treasure Chest Game's
    rooms (a minigame of their own) or the remake's ice-trap chests (A_04, the chests plugin retypes them)."""
    if "chests_of" not in _cache:
        from parity import chests, dungeons
        from parity import _chests_tcg as tcg
        out = {n: [rid] for n, rid in _chest_spots().items()}
        paired = chests._locs()["paired"]
        for n, rid in chests._mine().items():
            if n in tcg.ROOMS or (paired.get(n) or {}).get("kind") == "a04" or n in out:
                continue
            out[n] = [rid] + chests._also(n)[0]
        for n, rid in dungeons.WORLD.get("kept_chests", {}).items():
            out.setdefault(n, [rid])
        _cache["chests_of"] = out
    return _cache["chests_of"]


def takes_foreign(name):
    """Whether OoTR location `name` can hold another player's item (version 1). That's a chest any plugin puts in play
    that can run a scene of its own, so the chests that can hold an ice trap: small and big chests without a
    story/minigame scene, with a location's copies all one size. Or a core scene location (NPC gifts, songs,
    cutscenes, boss rewards, Great Fairies), whose give steps become a call."""
    from parity import chests
    rids = _chests_of().get(name)
    if rids is not None:
        sizes = {chests.ice_size(_rewards()[r]) for r in rids if r in _rewards()}
        return len(sizes) == 1 and None not in sizes and all(r in _rewards() for r in rids)
    return name in _scene_spots()


def foreign_locations():
    """Every OoTR location takes_foreign accepts."""
    return {n for n in list(_chests_of()) + list(_scene_spots()) if takes_foreign(n)}


def before_fill(world, settings):
    """Placeholders only go where they can be shown. An Archipelago seed's placements are forced (build_patch), and the
    rule also keeps OoTR's own fill honest."""
    if not active(settings):
        return
    for loc in world.get_locations():
        if takes_foreign(loc.name):
            continue
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: item.name not in PLACEHOLDER_NAMES and prev(location, item))


# Other players' items
FOUND_FILE = "RandoAP_FoundTexts"        # Dm_SY_LetterBottle's copy: GameDataActor and SystemTextNPC
FOUND_SOURCE = "Dm_SY_LetterBottle"
TEXT_FILE, TEXT_MSBT = "Dm_SY_Get", "EventFlowMsg/Dm_SY_Get.msbt"
CHEST_FILES = {"small": "Dm_SY_TreasureboxSmall", "big": "Dm_SY_Treasurebox"}  # vanilla (their rows are copied)
# The chests holding another player's item play their scene from renamed copies of the chest scene files (same-length
# names), so the vanilla files every other chest loads don't grow (3 steps per chest, plus the shared opening).
CHEST_HOSTS = {"small": "RandoAP_TreasureboxSml", "big": "RandoAP_BigChests"}
ANALYZED_TEMPLATE = "NaviLockOnHint"      # OotrR's scene-info template: no lists, no recorded camera
MAILBOX_ROW_TEMPLATE = "NaviHint_Shield_Hylian"  # PlayerPos, FlowchartEvent, Default sound: requested by a sequence


def _key(info):
    return str(int(info["location_id"]))


def found_entry(info):
    return FOUND_PREFIX + _key(info)


def found_label(info):
    return "RandoAP_" + _key(info)


def chest_entry(info):
    return "RandoAP_C" + _key(info)


def found_call(location, world):
    """The scene call ("File:Entry") that shows `location`'s found text. It's for plugins that build a location's give
    steps themselves, like songs_trade._target."""
    info = ((_cfg(getattr(world, "settings", None)) or {}).get("foreign") or {}).get(location)
    if info is None:
        raise ValueError(f"{location}: another player's item without its remake_archipelago.foreign entry")
    return f"{FOUND_FILE}:{found_entry(info)}"


def _chest_size(rid, world):
    from parity import chests
    r = _rewards()[rid]
    ap = sys.modules.get("parity.appearance")
    if ap is not None and world is not None and r.get("kind") == "chest":
        r = dict(r, actor=ap.chest_actor(world, rid))  # a look option may have changed the chest's type
    return chests.ice_size(r)


def item_for(item, location, world):
    """A placeholder at a chest gets the hidden stand-in and the chest's own scene row. At a scene location its give
    steps call the found text (tools/make_patch.py scene_call_ops)."""
    if item not in PLACEHOLDER_NAMES:
        return None
    from parity import chests
    from parity import _chests_scenes as scenes
    info = ((_cfg(world.settings) or {}).get("foreign") or {}).get(location)
    if info is None:
        raise ValueError(f"{location}: {item} without its remake_archipelago.foreign entry")
    rids = _chests_of().get(location)
    if rids is not None:
        if len({_chest_size(r, world) for r in rids} - {None}) != 1 or any(_chest_size(r, world) is None for r in rids):
            raise ValueError(f"{location}: another player's item in a chest that can't run a scene")
        return {"item": scenes.STAND_IN, "extra": {"GetEventName": chest_entry(info)},
                "note": f"{location}: {info['item']} for {info['player_name']}"}
    rid = _scene_spots().get(location)
    if rid is not None:
        spec = chests.scene_ice_spec(rid)  # its stand-in item, never handed over and different from the vanilla one
        return {"item": spec["item"], "call": f"{FOUND_FILE}:{found_entry(info)}"}
    raise ValueError(f"{location}: another player's item where none can be shown (parity.archipelago.takes_foreign)")


def _found_text_ops(label, info):
    """"You found <item> for <player>!" in the game's 16 languages. _archipelago_text cleans the names for each
    language's font and breaks the lines the way the game's own texts are."""
    from parity import _archipelago_text as T
    return T.found_ops(label, info["item"], info["player_name"])


SAY_ENTRY = "RandoAP_Say"   # FOUND_FILE's one shared step pair: it sets the Bool the argument Flag names, then shows
#                             the text MessageId names. Vanilla passes both as arguments too (268 EventTalk
#                             MessageId and 47 EventTriggerSetGameDataBool GameDataName arguments). A talk step alone
#                             holds 20 parameters, so one shared copy kept FOUND_FILE at a third of its size (220
#                             locations).


def say_graph():
    return _graph(FOUND_FILE, SAY_ENTRY, {
        "found": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                  "params": {"GameDataName": {"arg": "Flag"}, "Index": -1, "Value": True}, "next": "say"},
        "say": dict(_talk({"arg": "MessageId"}), next=None)}, "found")


def _say(flag, label, nxt):
    """A location's step: the shared found step with its flag and text."""
    return {"call": f":{SAY_ENTRY}", "params": {"Flag": flag, "MessageId": f"EventFlowMsg/{TEXT_FILE}:{label}"},
            "next": nxt}


def _talk(label):
    """SystemTextNPC's text box (the FOOL text's settings) for msbt label `label`, or {"arg": name}."""
    from parity import _chests_scenes as scenes
    msg = label if isinstance(label, dict) else f"EventFlowMsg/{TEXT_FILE}:{label}"
    return {"actor": "SystemTextNPC", "action": "EventTalk", "params": dict(scenes.TALK_PARAMS, MessageId=msg)}


def _set_bool(name, value, nxt):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
            "params": {"GameDataName": name, "Index": -1, "Value": bool(value)}, "next": nxt}


def _ask_bool(name, yes, no):
    """A branch on a Bool. Case 0 is set and 1 is not set (README "Event query answers")."""
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
            "params": {"GameDataName": name, "Index": -1}, "cases": {0: yes, 1: no}}


def _graph(file, entry, nodes, start):
    return {"file": file, "flowchart": file, "add_graph": entry, "nodes": nodes, "start": start}


def _chest_shared(size):
    """[(entry, nodes, start)] for chest scene file `size`. First the opening the way the ice-trap chest scene plays it
    (_chests_scenes: front or kick for small chests, the whole suspense opening for big ones) without its freeze,
    returning to the caller (RandoAP_Open_<size>). Then the chest's own ending (RandoAP_End_<size>), which marks it
    opened, releases the pause and saves."""
    from parity import _chests_scenes as scenes
    import copy
    g = scenes.load()["graphs"]
    ending = ("wait1", "markopened", "unpause", "save", "glowoff")
    if size == "small":
        _, n, start = g["small"][1]
        n = copy.deepcopy(n)
        opening = {k: v for k, v in n.items() if k not in ending and k != "freeze"}
        for k in ("opened_front", "opened_kick"):
            opening[k]["next"] = None
        end = {k: v for k, v in n.items() if k in ending}
        return [("RandoAP_Open_small", opening, start), ("RandoAP_End_small", end, "wait1")]
    (_, pn, pstart), (_, n, start) = copy.deepcopy(g["big"][1]), copy.deepcopy(g["big"][2])
    pn["show"] = {"actor": "GameSystemActor", "action": "EventWait", "params": {"Frames": 1, "IsWaitEnd": True},
                  "next": None}  # nothing where the contents would rise, same as the ice trap
    opening = {k: v for k, v in n.items() if k not in ending and k != "wait90_0"}
    opening["perform0"]["call"] = ":RandoAP_Open_big_perform0"
    opening["perform0"]["next"] = None
    end = {k: v for k, v in n.items() if k in ending}
    return [("RandoAP_Open_big_perform0", pn, pstart), ("RandoAP_Open_big", opening, start),
            ("RandoAP_End_big", end, "wait1")]


def foreign_plan(settings, world):
    """Plan parts for every placeholder: its found entry (flag + text), its text in every language, and for chests the
    shared opening/ending and a scene row of its own."""
    cfg = _cfg(settings)
    foreign = cfg.get("foreign") or {}
    placed = {loc.name: loc.item.name for loc in world.get_locations()
              if loc.item is not None and loc.item.name in PLACEHOLDER_NAMES}
    problems = [f"{n}: {placed[n]} has no remake_archipelago.foreign entry" for n in sorted(set(placed) - set(foreign))]
    problems += [f"{n}: remake_archipelago.foreign names it, but it holds "
                 f"{world.get_location(n).item.name if n in {l.name for l in world.get_locations()} else 'nothing'}"
                 for n in sorted(set(foreign) - set(placed))]
    problems += [f"{n}: holds {placed[n]}, but foreign says {foreign[n]['classification']}"
                 for n in sorted(set(placed) & set(foreign)) if PLACEHOLDERS[foreign[n]["classification"]] != placed[n]]
    problems += [f"{n}: another player's item where none can be shown" for n in sorted(placed) if not takes_foreign(n)]
    if problems:
        raise ValueError("Archipelago placements: " + "; ".join(problems))
    events, text, rows, bools, record = [say_graph()], [], [], {}, {}
    sizes = {}
    for loc in sorted(placed):
        info = foreign[loc]
        entry, label = found_entry(info), found_label(info)
        bools[entry] = False
        events.append(_graph(FOUND_FILE, entry, {"go": _say(entry, label, None)}, "go"))
        text += _found_text_ops(label, info)
        rec = {"entry": f"{FOUND_FILE}:{entry}", "flag": entry, "label": label, "item": info["item"],
               "player": info["player_name"], "class": info["classification"]}
        rids = _chests_of().get(loc)
        if rids is not None:
            size = _chest_size(rids[0], world)
            sizes.setdefault(size, []).append(loc)
            f = CHEST_HOSTS[size]
            ce = chest_entry(info)
            open_params = {"ContentName": {"arg": "ContentName"}} if size == "big" else {}
            events.append(_graph(f, ce, {
                "open": {"call": f":RandoAP_Open_{size}", "params": open_params, "next": "found"},
                "found": {"call": f"{FOUND_FILE}:{entry}", "next": "end"},
                "end": {"call": f":RandoAP_End_{size}", "next": None}}, "open"))
            rows.append({"file": EVENT_SETTING_FILE, "add_row": {
                "copy_of": CHEST_FILES[size], "analyzed_copy_of": ANALYZED_TEMPLATE,
                "set": {"__RowId": ce, "FlowchartFileName": f"Work/Event/EventFlow/{f}.evfc", "EntryPointName": ce}},
                "grow": True})
            rec.update(chests=rids, size=size, row=ce, scene=f"{f}:{ce}")
        else:
            rec.update(scene_location=_scene_spots()[loc])
        record[loc] = rec
    for size in sorted(sizes):
        events[:0] = [_graph(CHEST_HOSTS[size], e, n, s) for e, n, s in _chest_shared(size)]
    return {"events": events, "text": text, "byml": rows, "bools": bools, "record": record, "sizes": sorted(sizes),
            "notes": [f"{n}: {foreign[n]['item']} for {foreign[n]['player_name']} ({record[n].get('scene') or 'call '
                      + record[n]['entry']})" for n in sorted(placed)]}


EVENT_SETTING_FILE = "RSDB/EventSetting.Product.111.rstbl.byml.zs"


# The mailbox (received items)
DONE = "@@DONE"                          # a leaf's "finished giving" target (_archipelago_give)
MAIN_UPDATE = "Sequence/MainUpdate.module.ainb"
AFTER_EVENT = "Sequence/AfterEvent.module.ainb"
SEED_MARK_ENTRY = "RandoAP_SeedMark"


def _mods():
    g = sys.modules.get("generate")
    if g is None or not hasattr(g, "plugins"):
        g = sys.modules.get("__main__")
    if g is None or not hasattr(g, "plugins"):
        import generate as g
    return g.plugins()


def _merge(plan, part):
    """generate.merge_plan's rules (lists add up, tables merge, the rest is replaced; gamedata is a list of ops)."""
    for k, v in (part or {}).items():
        if k == "gamedata":
            old = plan.get(k)
            plan[k] = ([] if old is None else [old] if isinstance(old, dict) else list(old)) + (
                [v] if isinstance(v, dict) else list(v))
        elif isinstance(v, list):
            plan[k] = plan.get(k, []) + v
        elif isinstance(v, dict) and isinstance(plan.get(k), dict):
            plan[k] = dict(plan[k], **v)
        else:
            plan[k] = v


def _relabel(code, leaf):
    """A leaf's nodes with labels of their own (L<code>_...) and its DONE ends sent to the counting step."""
    p = f"L{code}_"

    def t(x):
        if x == DONE:
            return "inc0"
        if x is None or (isinstance(x, str) and x.startswith("@")):
            return x
        return p + x
    out = {}
    for lab, node in leaf["nodes"].items():
        n = dict(node)
        if isinstance(n.get("call"), str) and n["call"].startswith(EVENT_FILE + ":"):
            n["call"] = n["call"][len(EVENT_FILE):]  # a call within the mailbox's own file, as vanilla writes them
        if "next" in n:
            n["next"] = t(n["next"])
        if "cases" in n:
            n["cases"] = {k: t(v) for k, v in n["cases"].items()}
        if "fork" in n:
            n["fork"] = [t(x) for x in n["fork"]]
        if "join" in n and n["join"] is not True:
            n["join"] = t(n["join"])
        out[p + lab] = n
    return out, p + leaf["start"]


def mailbox_nodes(starts):
    """The RandoAP_Mailbox graph around the leaves (`starts` is {code: first label}):
    1. Idx (4 bits) has to equal Count's low 4 bits, otherwise the event ends (a stale or repeated request).
    2. Code (10 bits, high bit first) picks the leaf. A code without one goes straight to 3 (counted, nothing given).
    3. Count += 1 (ripple carry over 16 Bools, it wraps past 65535)."""
    n = {}
    for i in range(IDX_BITS):
        nxt = f"chk{i + 1}" if i + 1 < IDX_BITS else "d"
        n[f"chk{i}"] = _ask_bool(COUNT[i], f"chk{i}y", f"chk{i}n")
        n[f"chk{i}y"] = _ask_bool(IDX[i], nxt, None)
        n[f"chk{i}n"] = _ask_bool(IDX[i], None, nxt)

    def build(codes, bit, prefix):
        if bit < 0:
            return starts[codes[0]]
        ones = [c for c in codes if c >> bit & 1]
        zeros = [c for c in codes if not c >> bit & 1]
        label = "d" + prefix
        n[label] = _ask_bool(CODE[bit], build(ones, bit - 1, prefix + "1") if ones else "inc0",
                             build(zeros, bit - 1, prefix + "0") if zeros else "inc0")
        return label
    codes = sorted(c for c in starts if c)
    if codes:
        build(codes, CODE_BITS - 1, "")
    else:
        n["d"] = dict(_set_bool(SIGNAL, False, "inc0"))  # no codes at all, still count
    for i in range(COUNT_BITS):
        n[f"inc{i}"] = _ask_bool(COUNT[i], f"clr{i}", f"set{i}")
        n[f"set{i}"] = _set_bool(COUNT[i], True, None)
        n[f"clr{i}"] = _set_bool(COUNT[i], False, f"inc{i + 1}" if i + 1 < COUNT_BITS else None)
    return n


def _fallback_leaf(item):
    """The plain hold-up of item_map's actor. Only used while _archipelago_give is missing, which never happens in a
    finished build."""
    im = _json("config", "item_map.json")
    actor = im["items"].get(item) or im["junk_for"].get(item)
    if actor is None:
        return None
    return {"nodes": {"give": {"call": "Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc",
                               "params": {"ActorName": actor, "IsNpcEventStarter": False}, "next": DONE}},
            "start": "give", "plan": {}, "kind": "fallback hold-up"}


def _leaves(world, settings, table):
    try:
        from parity import _archipelago_give as G
    except ImportError:
        G = None
    if G is not None:
        return G.leaves(world, settings, _mods(), table), True
    out = {}
    for name, code in table.items():
        leaf = _fallback_leaf(name)
        if leaf is not None:
            out[code] = leaf
    return out, False


def watcher_op():
    """Sequence/MainUpdate.module.ainb (every frame of play) gets one watcher, built from vanilla nodes:
    Signal (SeqQueryGetNonStructGameDataBool, as AfterEvent node 36) -> BoolSelector (MainUpdate node 8's kind):
      True  -> BoolSelector on SeqQueryIsPlayingMainEvent (AfterEvent node 24: prepare and request included):
                 True  -> wait (the shared SeqExecuteGenericDummyAction)
                 False -> Simultaneous (AfterEvent node 38): SeqOneShotRequestEvent(RandoAP_Mailbox) (node 40) and
                          SeqOneShotSetNonStructGameDataBool(Signal = false) (node 35), the same frame
      False -> the dummy.
    Per frame: one Bool read and one selector; the event query only runs while Signal is true."""
    def cp(path, node, label):
        return {"copy": {"from": {"file": path}, "nodes": [node], "label": label, "follow": False}}
    return {"file": MAIN_UPDATE, "edits": [
        cp(MAIN_UPDATE, 8, "sel"), cp(MAIN_UPDATE, 8, "busy"),
        cp(AFTER_EVENT, 36, "sig"), cp(AFTER_EVENT, 24, "ev"), cp(AFTER_EVENT, 38, "both"),
        cp(AFTER_EVENT, 40, "req"), cp(AFTER_EVENT, 35, "clr"),
        {"set_input": {"node": "sig:36", "name": "GameDataFullName", "value": SIGNAL}},
        {"set_input": {"node": "req:40", "name": "EventName", "value": EVENT}},
        {"set_input": {"node": "clr:35", "name": "GameDataFullName", "value": SIGNAL}},
        {"set_input": {"node": "clr:35", "name": "Value", "value": False}},
        {"feed": {"from": "sig:36", "output": "Value", "to": "sel:8", "input": "Input"}},
        {"feed": {"from": "ev:24", "output": "IsPlayingMainEvent", "to": "busy:8", "input": "Input"}},
        {"add_child": {"parent": "sel:8", "child": "busy:8", "name": "True"}},
        {"add_child": {"parent": "sel:8", "child": "SeqExecuteGenericDummyAction", "name": "False"}},
        {"add_child": {"parent": "busy:8", "child": "SeqExecuteGenericDummyAction", "name": "True"}},
        {"add_child": {"parent": "busy:8", "child": "both:38", "name": "False"}},
        {"add_child": {"parent": "both:38", "child": "req:40"}},
        {"add_child": {"parent": "both:38", "child": "clr:35"}},
        {"add_child": {"parent": "@Root", "child": "sel:8"}}]}


def new_file_ops(sizes=()):
    """make_patch "new_files" for our own scene files (EVENT_FILE, FOUND_FILE and the chest hosts in use)."""
    pairs = [(EVENT_FILE, EVENT_SOURCE), (FOUND_FILE, FOUND_SOURCE)] + [(CHEST_HOSTS[s], CHEST_FILES[s]) for s in sizes]
    return [{"to": f"Event/EventFlow/{new}.bfevfl.zs", "from": f"Event/EventFlow/{old}.bfevfl.zs",
             "rename": [[old, new]]} for new, old in pairs]


def seed_mark_ops(seed_key):
    """The new file's opening (OpeningEvent:Opening_Introduction, which runs once per file) sets
    RandoAP_Seed_<seed_key> through an entry in FOUND_FILE, since OpeningEvent has no GameDataActor. It goes
    between Event31 (terrain pin) and Event32 (camera), and world_settings' starting items hook Event8 -> Event31."""
    return [_graph(FOUND_FILE, SEED_MARK_ENTRY, {"mark": _set_bool(SEED_PREFIX + seed_key, True, None)}, "mark"),
            _graph("OpeningEvent", "RandoAP_Seed", {"mark": {"call": f"{FOUND_FILE}:{SEED_MARK_ENTRY}",
                                                             "next": "@Event32"}}, "mark"),
            {"file": "OpeningEvent", "flowchart": "OpeningEvent", "event": "Event31", "next": "RandoAP_Seed_mark"}]


def mailbox_plan(settings, world):
    cfg = _cfg(settings)
    table = codes()
    leaves, complete = _leaves(world, settings, table)
    by_code = {c: n for n, c in table.items()}
    nodes, starts, part = {}, {}, {}
    for code in sorted(leaves):
        ln, start = _relabel(code, leaves[code])
        nodes.update(ln)
        starts[code] = start
        _merge(part, leaves[code].get("plan") or {})
    nodes.update(mailbox_nodes(starts))
    events = [_graph(EVENT_FILE, ENTRY, nodes, "chk0")] + seed_mark_ops(cfg["seed_key"])
    row = {"file": EVENT_SETTING_FILE, "grow": True, "add_row": {
        "copy_of": MAILBOX_ROW_TEMPLATE, "analyzed_copy_of": ANALYZED_TEMPLATE,
        "set": {"__RowId": EVENT, "FlowchartFileName": f"Work/Event/EventFlow/{EVENT_FILE}.evfc",
                "EntryPointName": ENTRY}}}
    bools = {n: False for n in [SIGNAL] + CODE + IDX + COUNT + [SEED_PREFIX + cfg["seed_key"]]}
    missing = sorted(n for n, c in table.items() if c not in leaves)
    record = {"codes": {str(c): {"item": by_code[c], "kind": leaves[c].get("kind", ""), "start": starts[c]}
                        for c in sorted(leaves)},
              "missing": missing, "complete": complete, "seed_key": cfg["seed_key"]}
    return {"events": events, "byml": [row], "ainb": [watcher_op()], "bools": bools, "plan": part,
            "record": record}


def world_plan(settings, world):
    if not active(settings):
        return {}
    register_items()
    fp = foreign_plan(settings, world)
    mb = mailbox_plan(settings, world)
    plan = {"events": fp["events"] + mb["events"], "byml": fp["byml"] + mb["byml"], "ainb": mb["ainb"],
            "gamedata": {"add_bools": dict(mb["bools"], **fp["bools"])}, "new_files": new_file_ops(fp["sizes"])}
    if fp["text"]:
        plan["text"] = fp["text"]
    _merge(plan, mb["plan"])
    plan["_verify_plugins"] = ["archipelago"]
    plan["_archipelago"] = {"mailbox_version": MAILBOX_VERSION, "foreign": fp["record"], "mailbox": mb["record"]}
    notes = fp["notes"] + [f"mailbox: {len(mb['record']['codes'])} item codes; watcher in {MAIN_UPDATE}; event "
                           f"{EVENT_FILE}:{ENTRY} on the new scene row {EVENT}"]
    if mb["record"]["missing"]:
        notes.append(f"mailbox: no give for {len(mb['record']['missing'])} item(s): {mb['record']['missing'][:8]}")
    if not mb["record"]["complete"]:
        notes.append("mailbox: built with fallback gives (parity/_archipelago_give.py missing): NOT for play")
    plan["_notes_archipelago"] = notes
    return plan


# Read-back (tools/rando/in_game_check.py)
def _flow(fs, name):
    from evfl import Evfl
    d = "Event/EventFlow/"
    for rel in (f"{d}{name}.110.bfevfl.zs", f"{d}{name}.bfevfl.zs"):  # the newest version is the one the game reads
        try:
            return Evfl(fs.read(rel)).flowcharts[0]
        except (FileNotFoundError, OSError, KeyError):
            continue
    raise FileNotFoundError(f"{d}{name}")


def _what(fc, e):
    a = fc["actors"][e["actor"]] if "actor" in e else None
    if e["type"] == "switch":
        return f"{a['name']}.{a['queries'][e['query']]}"
    if e["type"] == "action":
        return f"{a['name']}.{a['actions'][e['action']]}"
    if e["type"] == "subflow":
        return f"call {e.get('flowchart') or ''}:{e.get('entry_point')}"
    return e["type"]


def _param(e, name):
    return (((e.get("params") or {}).get("items") or {}).get(name) or {}).get("value")


def simulate(fc, start, state, limit=5000):
    """Runs a graph's RandoAP_* Bool queries and sets on `state` ({name: bool}, changed in place) from event index
    `start`. Returns the first other step reached (its event), or None when the graph ends."""
    i = start
    for _ in range(limit):
        if i is None or i >= len(fc["events"]):
            return None
        e = fc["events"][i]
        w = _what(fc, e)
        name = _param(e, "GameDataName")
        if w == "GameDataActor.EventQueryIsGameDataBool" and str(name).startswith("RandoAP_"):
            want = 0 if state.get(name, False) else 1
            i = next(c["next"] for c in e["cases"] if c["value"] == want)
            continue
        if w == "GameDataActor.EventTriggerSetGameDataBool" and str(name).startswith("RandoAP_"):
            state[name] = bool(_param(e, "Value"))
            i = e.get("next")
            continue
        return e
    raise RuntimeError("the mailbox graph loops")


def _set_number(state, names, value):
    for k, n in enumerate(names):
        state[n] = bool(value >> k & 1)


def _number(state, names):
    return sum(1 << k for k, n in enumerate(names) if state.get(n))


def verify_mailbox(fc, record):
    """Runs the written RandoAP_Mailbox on its own Bools. Every code has to reach its leaf's first step (Count untouched
    until the leaf ends), code 0 and an unknown code count and give nothing, a stale Idx changes nothing, and the
    counter carries (0, 1, 15, 16, 255, 65535 -> +1, wrapping)."""
    bad = []
    by_name = {e["name"]: e["idx"] for e in fc["events"]}
    main = (fc["entry_points"].get(ENTRY) or {}).get("main")
    if main is None:
        return [f"{EVENT_FILE}: no entry {ENTRY}"]
    for code, r in sorted(record["codes"].items(), key=lambda kv: int(kv[0])):
        for count in (0, 37):
            st = {}
            _set_number(st, COUNT, count)
            _set_number(st, IDX, count & 15)
            _set_number(st, CODE, int(code))
            e = simulate(fc, main, st)
            want = f"{ENTRY}_{r['start']}"
            if e is None or e["name"] != want:
                bad.append(f"mailbox code {code} ({r['item']}): reaches {e and e['name']}, not {want}")
            elif _number(st, COUNT) != count:
                bad.append(f"mailbox code {code}: Count changed before the item was given")
    unknown = next(c for c in range(1, 1 << CODE_BITS) if str(c) not in record["codes"])
    for code in (0, unknown):
        for count in (0, 1, 15, 16, 255, 65535):
            st = {}
            _set_number(st, COUNT, count)
            _set_number(st, IDX, count & 15)
            _set_number(st, CODE, code)
            e = simulate(fc, main, st)
            if e is not None or _number(st, COUNT) != (count + 1) & 0xFFFF:
                bad.append(f"mailbox code {code} at Count {count}: reaches {e and e['name']}, Count "
                           f"{_number(st, COUNT)}")
    for count, idx in ((0, 1), (5, 4), (16, 1), (17, 0)):
        st = {}
        _set_number(st, COUNT, count)
        _set_number(st, IDX, idx)
        _set_number(st, CODE, 1)
        before = dict(st)
        e = simulate(fc, main, st)
        if e is not None or st != before:
            bad.append(f"mailbox: a stale request (Count {count}, Idx {idx}) reaches {e and e['name']} or changes Bools")
    if f"{ENTRY}_inc0" not in by_name:
        bad.append("mailbox: no counting step")
    return bad


def verify_generic_hud(fc, record, romfs):
    """Checks the generic Small Key / Boss Key gives (_archipelago_give.hud_nodes). First the credit, then
    Sequence_CurrentBanc compared with every dungeon map (each a Banc of the game). On a dungeon map it's the HUD
    display and 50 frames, then the pick-up window, then the counting step. Off every map it goes straight to the
    window."""
    import glob
    from parity import _archipelago_give as G
    from parity import _dungeons_keys as keys
    bad, ev = [], fc["events"]
    by_name = {e["name"]: i for i, e in enumerate(ev)}
    want_maps = G.dungeon_maps()
    have = {os.path.basename(p)[:-len("_Static.bcett.byml.zs")]
            for p in glob.glob(os.path.join(romfs, "Banc", "*", "*_Static.bcett.byml.zs"))}
    bad += [f"mailbox: dungeon map {m!r} is no Banc of the game" for m in want_maps if m not in have]

    def at(i):
        return ev[i] if isinstance(i, int) and i < len(ev) else None
    for code, r in sorted(record.get("codes", {}).items(), key=lambda kv: int(kv[0])):
        if r["item"] not in G.GENERIC_HUD:
            continue
        action, param = G.GENERIC_HUD[r["item"]]
        p = f"{ENTRY}_L{code}_"
        credit = at(by_name.get(p + "credit"))
        pickup = by_name.get(p + "pickup")
        what = f"mailbox code {code} ({r['item']})"
        if credit is None or _what(fc, credit) != f"GameSystemActor.{G.GENERIC[r['item']][1]}" or pickup is None:
            bad.append(f"{what}: no credit step or pick-up window")
            continue
        if (at(ev[pickup].get("next")) or {}).get("name") != f"{ENTRY}_inc0":
            bad.append(f"{what}: the pick-up window isn't followed by the counting step")
        maps, hud, i = [], set(), credit.get("next")
        while at(i) is not None and _what(fc, ev[i]) == "GameDataActor.EventQueryIsGameDataString64" and len(maps) < 64:
            q = ev[i]
            cases = {c["value"]: c["next"] for c in q.get("cases", [])}
            if _param(q, "GameDataName") != keys.CURRENT or set(cases) != {0, 1}:
                bad.append(f"{what}: {q['name']} doesn't compare {keys.CURRENT}")
                break
            maps.append(_param(q, "Value"))
            hud.add(cases[0])
            i = cases[1]
        if i != pickup:
            bad.append(f"{what}: the map checks end at {(at(i) or {}).get('name')}, not the pick-up window")
        if sorted(maps) != sorted(want_maps):
            bad.append(f"{what}: checks maps {maps}, not every dungeon's {want_maps}")
        if len(hud) != 1:
            bad.append(f"{what}: the map checks lead to {len(hud)} HUD steps")
            continue
        show = at(hud.pop())
        wait = at((show or {}).get("next"))
        if show is None or _what(fc, show) != f"UISystemActor.{action}" or _param(show, param) is not True or \
                wait is None or _what(fc, wait) != "EventSystemActor.EventWait" or _param(wait, "Frames") != 50 or \
                wait.get("next") != pickup:
            bad.append(f"{what}: on a dungeon map it runs {show and _what(fc, show)}, {wait and _what(fc, wait)}, not "
                       f"{action} True, 50 frames, the pick-up window")
    return bad


def verify_watcher(data):
    """Checks Sequence/MainUpdate.module.ainb. Root's Simultaneous holds Signal's BoolSelector, and True -> the
    main-event selector, whose False case requests RandoAP_Mailbox and clears Signal in one Simultaneous."""
    import ainb
    a = ainb.Ainb(data)
    nodes = a.nodes

    def kids(i):
        return {pl["name"]: pl["node"] for pl in nodes[i]["plugs"][ainb.PLUG_CHILD]}

    def src(i):
        return next((e["node"] for e in nodes[i]["inputs"]["bool"] if e["name"] == "Input"), -1)

    def string_in(i, name):
        return next((e["value"] for e in nodes[i]["inputs"]["string"] if e["name"] == name), None)
    root = next(c["main"] for c in a.commands if c["name"] == "Root")
    for sel in [pl["node"] for pl in nodes[root]["plugs"][ainb.PLUG_CHILD]]:
        q = src(sel) if nodes[sel]["type"] == 7 else -1  # BoolSelector: node type 7 (it has no name)
        if q < 0 or nodes[q]["name"] != "SeqQueryGetNonStructGameDataBool" or \
                string_in(q, "GameDataFullName") != SIGNAL:
            continue
        busy = kids(sel).get("True")
        if busy is None or nodes[busy]["type"] != 7 or \
                nodes[src(busy)]["name"] != "SeqQueryIsPlayingMainEvent":
            return ["watcher: Signal's True case isn't the main-event check"]
        both = kids(busy).get("False")
        if both is None:
            return ["watcher: no request while no event plays"]
        got = sorted((nodes[k]["name"], string_in(k, "EventName") or string_in(k, "GameDataFullName"))
                     for k in [pl["node"] for pl in nodes[both]["plugs"][ainb.PLUG_CHILD]])
        if got != [("SeqOneShotRequestEvent", EVENT), ("SeqOneShotSetNonStructGameDataBool", SIGNAL)]:
            return [f"watcher: the request step holds {got}"]
        clr = next(pl["node"] for pl in nodes[both]["plugs"][ainb.PLUG_CHILD]
                   if nodes[pl["node"]]["name"] == "SeqOneShotSetNonStructGameDataBool")
        if next((e["value"] for e in nodes[clr]["inputs"]["bool"] if e["name"] == "Value"), None) is not False:
            return ["watcher: Signal isn't set back to false"]
        for s in (sel, busy):
            other = kids(s).get("False" if s == sel else "True")
            if other is None or nodes[other]["name"] != "SeqExecuteGenericDummyAction":
                return ["watcher: a selector's idle case isn't the dummy action"]
        return []
    return ["watcher: Root has no Signal selector"]


def verify(patch, plan, romfs):
    """Read every Archipelago edit back from the built patch."""
    from romtools import Romfs, byml_load, murmur3_32
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    ap = plan.get("_archipelago") or {}
    bad = []
    # save data: every new Bool, plain, saved, default false
    ops = plan.get("gamedata") if isinstance(plan.get("gamedata"), list) else [plan.get("gamedata") or {}]
    gd = {k: v for op in ops for k, v in (op.get("add_bools") or {}).items() if k.startswith("RandoAP_")}
    root = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    rows = {int(r["Hash"]): r for r in root["Data"]["Bool"]}
    for name in gd:
        r = rows.get(murmur3_32(name))
        if r is None or r["DefaultValue"] is not False or int(r["SaveFileIndex"]) != 0:
            bad.append(f"save data: {name} missing or not a saved Bool defaulting to false")
    # scene rows and their scene-info rows
    es = {r["__RowId"]: r for r in byml_load(fs.read(EVENT_SETTING_FILE))[0]}
    an = {r["__RowId"]: r for r in byml_load(fs.read("RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs"))[0]}
    want_rows = {EVENT: (EVENT_FILE, ENTRY)}
    want_rows.update({r["row"]: (r["scene"].split(":")[0], r["row"]) for r in (ap.get("foreign") or {}).values()
                      if r.get("row")})
    for rid, (f, entry) in sorted(want_rows.items()):
        r = es.get(rid)
        if r is None or not str(r.get("FlowchartFileName", "")).endswith(f"/{f}.evfc") or r.get("EntryPointName") != entry:
            bad.append(f"scene row {rid}: {r and (r.get('FlowchartFileName'), r.get('EntryPointName'))}, "
                       f"not {f}:{entry}")
        if rid not in an:
            bad.append(f"scene row {rid}: no scene-info row")
    # the watcher
    bad += verify_watcher(fs.raw(MAIN_UPDATE))
    # the mailbox
    gfc = _flow(fs, EVENT_FILE)
    bad += verify_mailbox(gfc, ap.get("mailbox") or {"codes": {}})
    if (ap.get("mailbox") or {}).get("complete"):
        bad += verify_generic_hud(gfc, ap["mailbox"], romfs)
    # the seed marker in the opening
    seed = (ap.get("mailbox") or {}).get("seed_key")
    pfc = _flow(fs, FOUND_FILE)
    ofc = _flow(fs, "OpeningEvent")
    ev31 = next((e for e in ofc["events"] if e["name"] == "Event31"), None)
    nxt = ofc["events"][ev31["next"]] if ev31 and ev31.get("next", 0xFFFF) < len(ofc["events"]) else None
    if nxt is None or _what(ofc, nxt) != f"call {FOUND_FILE}:{SEED_MARK_ENTRY}" or \
            ofc["events"][nxt["next"]]["name"] != "Event32":
        bad.append("opening: Event31 doesn't call the seed marker before Event32")
    st = {}
    mark = (pfc["entry_points"].get(SEED_MARK_ENTRY) or {}).get("main")
    if mark is None or simulate(pfc, mark, st) is not None or st != {SEED_PREFIX + str(seed): True}:
        bad.append(f"seed marker: {SEED_MARK_ENTRY} sets {st}")
    # other players' items: the shared found step, each location's call of it, the chests' own entries
    if ap.get("foreign"):
        main = (pfc["entry_points"].get(SAY_ENTRY) or {}).get("main")
        e1 = pfc["events"][main] if main is not None else None
        e2 = pfc["events"][e1["next"]] if e1 and e1.get("next", 0xFFFF) < len(pfc["events"]) else None

        def arg(e, k):
            v = ((e or {}).get("params") or {}).get("items", {}).get(k) or {}
            return (v.get("type"), v.get("value"))
        if _what(pfc, e1 or {"type": "?"}) != "GameDataActor.EventTriggerSetGameDataBool" or \
                arg(e1, "GameDataName") != ("argument", "Flag") or \
                _what(pfc, e2 or {"type": "?"}) != "SystemTextNPC.EventTalk" or \
                arg(e2, "MessageId") != ("argument", "MessageId"):
            bad.append(f"{FOUND_FILE}:{SAY_ENTRY}: not 'set the Bool Flag names, then show MessageId'")
    chest_fc = {}
    renamed = {(op["file"], str(op["hash"])): str(op["set"]["Hash"]) for op in plan.get("placements", [])
               if "Hash" in op.get("set", {})}
    for loc, r in sorted((ap.get("foreign") or {}).items()):
        entry = r["entry"].split(":")[1]
        main = (pfc["entry_points"].get(entry) or {}).get("main")
        e = pfc["events"][main] if main is not None else None
        if e is None or _what(pfc, e) != f"call :{SAY_ENTRY}" or _param(e, "Flag") != r["flag"] or \
                _param(e, "MessageId") != f"EventFlowMsg/{TEXT_FILE}:{r['label']}":
            bad.append(f"{loc}: {r['entry']} doesn't call {SAY_ENTRY} with {r['flag']} and {r['label']}")
        for cid in r.get("chests") or ([r["chest"]] if r.get("chest") else []):  # each chest placement: the hidden
            from parity import _chests_scenes as scenes                          # stand-in and the location's own row
            cr = _rewards()[cid]
            for lf in cr["files"]:
                h = renamed.get((lf, str(cr["hash"])), str(cr["hash"]))  # a copy sharing the main chest's save flag
                a = next((x for x in byml_load(fs.read(lf))[0].get("Actors") or [] if str(x.get("Hash")) == h), None)
                dyn = (a or {}).get("Dynamic") or {}
                if a is None or dyn.get("GetEventName") != r["row"] or \
                        dyn.get(cr["field"].split(".", 1)[1]) != scenes.STAND_IN:
                    bad.append(f"{loc}: {lf} chest {cr['hash']}: GetEventName {dyn.get('GetEventName')!r}, contents "
                               f"{dyn.get(cr['field'].split('.', 1)[1])!r}")
        if r.get("scene_location"):  # an NPC / scene location: one of its give steps' files now calls the text
            files = sorted({f for x in _rewards().values() if x.get("location") == r["scene_location"]
                            or x["id"] == r["scene_location"] for f in x.get("files", [])})
            fl, ent = r["entry"].split(":")
            if not any(e["type"] == "subflow" and e.get("flowchart") == fl and e.get("entry_point") == ent
                       for f in files for fc in [chest_fc.setdefault(f, _flow(fs, f.rsplit("/", 1)[-1].split(".")[0]))]
                       for e in fc["events"]):
                bad.append(f"{loc}: no give step of {r['scene_location']} calls {r['entry']}")
        if r.get("scene"):
            f, ce = r["scene"].split(":")
            fc = chest_fc.setdefault(f, _flow(fs, f))
            i = (fc["entry_points"].get(ce) or {}).get("main")
            calls = []
            while i is not None and i < len(fc["events"]) and len(calls) < 5:
                calls.append(_what(fc, fc["events"][i]))
                i = fc["events"][i].get("next")
            want = [f"call :RandoAP_Open_{r['size']}", f"call {r['entry']}", f"call :RandoAP_End_{r['size']}"]
            if calls != want:
                bad.append(f"{loc}: {r['scene']} runs {calls}, not {want}")
    return bad


def untested(settings):
    if not active(settings):
        return []
    return ["archipelago: the MainUpdate watcher, new EventSetting rows (mailbox and one per chest holding another "
            f"player's item), the mailbox event and the found texts ({PROBE_PLAN} first)"]


# The in-game probe (no client needed)
PROBE_PLAN = "plans/ap_mailbox_probe.json"
PROBE_SEED_KEY = "PROBE0000001"
# (chest, item named in its text, player, class, item the chest then "receives", the Idx it writes). The chest's found
# scene plays the client's part. It writes Code and Idx and raises Signal, so the mailbox runs right after the chest
# scene, from the main sequence, exactly like for an item sent by another world. The third chest repeats Idx 1, a
# stale request that has to give nothing.
PROBE_CHESTS = (("KF Midos Top Left Chest", "Hammer", "Bob", "progression", "Progressive Hookshot", 0),
                ("KF Midos Top Right Chest", "Fire Rod", "Carol", "useful", "Progressive Hookshot", 1),
                ("KF Midos Bottom Left Chest", "Bombs", "Dave", "filler", "Progressive Hookshot", 1),
                ("KF Midos Bottom Right Chest", "Bee Trap", "Eve", "trap", "Piece of Heart", 2))
PROBE_STEPS = """Archipelago mailbox probe (never part of a seed). Build: python tools/rando/parity/archipelago.py --probe out/ap_probe, then install out/ap_probe/patch with tools/install.py. START A NEW FILE (its new save rows and the seed marker are set by the new file's opening).
1. The game boots to the title screen and a new file starts normally (Kokiri Forest, Navi). [new EventSetting rows, MainUpdate edit, new save rows, opening edit]
2. Go into Mido's House (Mido lets you in). Open its four chests IN THIS ORDER (each sends the next item index; another order makes a later chest's item a "stale" one). Open the TOP LEFT chest: the usual small-chest opening, nothing above Link, a text box "You found Hammer for Bob!" (Hammer highlighted), the chest stays open. Then, as soon as the chest scene ends, Link holds up the HOOKSHOT with its text. [new chest row, found text; watcher + mailbox row + progressive give, the first delivery]
3. Open the TOP RIGHT chest: "You found Fire Rod for Carol!", then Link holds up the LONGSHOT. [second delivery: the counter moved to 1, progressive tier 2]
4. Open the BOTTOM LEFT chest: "You found Bombs for Dave!", then NOTHING else (it repeats the previous index on purpose: a stale request must give nothing). Wait 10 seconds: still nothing. [duplicate guard]
5. Open the BOTTOM RIGHT chest: "You found Bee Trap for Eve!", then Link holds up a PIECE OF HEART. [third delivery: the counter moved to 2]
6. Save (System > Save), reload the save: Hookshot became Longshot in the inventory, one heart piece, the four chests stay open, nothing is given again on load.
7. Performance: before installing, note Longshot's log frame stats (render-thread ms per frame, per 600 frames) while standing in Kokiri Forest for a minute; do the same with the probe installed. They should be the same.
PASS: every step as written. Report the first step that differs (crash at boot, no text, no Hookshot, a second gift at step 4...)."""


def probe_plan(world, settings):
    """The probe's make_patch plan (PROBE_STEPS). Mido's House's four chests hold "other players' items" and drive the
    mailbox themselves."""
    from parity import _chests_scenes as scenes
    from parity import chests
    table = codes()
    items = sorted({x[4] for x in PROBE_CHESTS})
    leaves, complete = _leaves(world, settings, {n: table[n] for n in items})
    rewards, events, text, rows, bools, record = {}, [say_graph()], [], [], {}, {}
    for i, (loc, item, player, cls, send, idx) in enumerate(PROBE_CHESTS):
        info = {"item": item, "player_name": player, "classification": cls, "location_id": 600000001 + i}
        entry, label, ce = found_entry(info), found_label(info), chest_entry(info)
        rid = _chest_spots()[loc]
        if _rewards()[rid]["actor"] not in chests.SMALL:  # Mido's chests have a Navi scene of their own, so seeds
            raise ValueError(f"{loc}: the probe expects a small chest")  # leave them out, and the probe replaces it
        n = {"found": _say(entry, label, "c0")}
        steps = [(CODE[k], table[send] >> k & 1) for k in range(CODE_BITS)] + \
                [(IDX[k], idx >> k & 1) for k in range(IDX_BITS)] + [(SIGNAL, True)]
        for k, (name, v) in enumerate(steps):  # the client's part: Code, Idx, then Signal last
            n[f"c{k}"] = _set_bool(name, v, f"c{k + 1}" if k + 1 < len(steps) else None)
        events.append(_graph(FOUND_FILE, entry, n, "found"))
        events.append(_graph(CHEST_HOSTS["small"], ce, {
            "open": {"call": ":RandoAP_Open_small", "next": "found"},
            "found": {"call": f"{FOUND_FILE}:{entry}", "next": "end"},
            "end": {"call": ":RandoAP_End_small", "next": None}}, "open"))
        rows.append({"file": EVENT_SETTING_FILE, "grow": True, "add_row": {
            "copy_of": CHEST_FILES["small"], "analyzed_copy_of": ANALYZED_TEMPLATE,
            "set": {"__RowId": ce, "FlowchartFileName": f"Work/Event/EventFlow/{CHEST_HOSTS['small']}.evfc",
                    "EntryPointName": ce}}})
        rewards[rid] = {"item": scenes.STAND_IN, "extra": {"GetEventName": ce},
                        "note": f"probe: {loc}: {item} for {player}, then the mailbox gets {send} (Idx {idx})"}
        text += _found_text_ops(label, info)
        bools[entry] = False
        record[loc] = {"entry": f"{FOUND_FILE}:{entry}", "flag": entry, "label": label, "item": item, "player": player,
                       "class": cls, "chests": [rid], "size": "small", "row": ce,
                       "scene": f"{CHEST_HOSTS['small']}:{ce}"}
    events[:0] = [_graph(CHEST_HOSTS["small"], e, nn, s) for e, nn, s in _chest_shared("small")]
    nodes, starts, part = {}, {}, {}
    for code in sorted(leaves):
        ln, start = _relabel(code, leaves[code])
        nodes.update(ln)
        starts[code] = start
        _merge(part, leaves[code].get("plan") or {})
    nodes.update(mailbox_nodes(starts))
    events += [_graph(EVENT_FILE, ENTRY, nodes, "chk0")] + seed_mark_ops(PROBE_SEED_KEY)
    rows.append({"file": EVENT_SETTING_FILE, "grow": True, "add_row": {
        "copy_of": MAILBOX_ROW_TEMPLATE, "analyzed_copy_of": ANALYZED_TEMPLATE,
        "set": {"__RowId": EVENT, "FlowchartFileName": f"Work/Event/EventFlow/{EVENT_FILE}.evfc",
                "EntryPointName": ENTRY}}})
    bools.update({nm: False for nm in [SIGNAL] + CODE + IDX + COUNT + [SEED_PREFIX + PROBE_SEED_KEY]})
    by_code = {c: nm for nm, c in table.items()}
    plan = {"description": PROBE_STEPS, "chest_size": "keep", "rewards": rewards, "events": events, "text": text,
            "byml": rows, "ainb": [watcher_op()], "gamedata": [{"add_bools": bools}],
            "new_files": new_file_ops(["small"])}
    _merge(plan, part)
    plan["_verify_plugins"] = ["archipelago"]
    plan["_archipelago"] = {"mailbox_version": MAILBOX_VERSION, "foreign": record, "mailbox": {
        "codes": {str(c): {"item": by_code[c], "kind": leaves[c].get("kind", ""), "start": starts[c]}
                  for c in sorted(leaves)}, "missing": [], "complete": complete, "seed_key": PROBE_SEED_KEY}}
    if not complete and not os.environ.get("AP_PROBE_FALLBACK"):
        raise ValueError("the probe needs tools/rando/parity/_archipelago_give.py")
    return plan


def _probe_world():
    """An unfilled world with the default settings (what the probe's gives read)."""
    import generate
    cfg = dict(sorted(generate.load_settings(os.path.join(HERE, "config", "rando_settings.json")).items()))
    ctx = generate.prepare("60", cfg)
    worlds, world, *_ = generate.build_unfilled(ctx)
    return world, ctx.settings


def build_probe(out_dir):
    import subprocess
    world, settings = _probe_world()
    plan = probe_plan(world, settings)
    with open(os.path.join(HERE, PROBE_PLAN), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "CHECKLIST.md"), "w", encoding="utf-8") as f:
        f.write("# " + PROBE_STEPS.replace("\n", "\n\n") + "\n")
    romfs = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
    patch = os.path.join(out_dir, "patch")
    rc = subprocess.call([sys.executable, os.path.join(HERE, "tools", "make_patch.py"), romfs, patch,
                          os.path.join(out_dir, "plan.json")])
    if rc:
        sys.exit(f"make_patch failed ({rc})")
    bad = verify(patch, plan, romfs)
    from parity import _hints_check
    n_text, bad_text, _, _ = _hints_check.check(romfs, patch, plan)
    bad += [f"text: {x}" for x in bad_text]
    with open(os.path.join(out_dir, "check.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(bad) + f"\n{len(bad)} problems; {n_text} text messages read back\n")
    print(f"probe: {len(bad)} problems; {n_text} text messages read back" + ("".join(f"\n  {b}" for b in bad)))
    return not bad


def main():
    args = sys.argv[1:]
    if "--tables" not in args and "--probe" not in args:
        sys.exit(__doc__)
    sys.path[:0] = [os.path.join(HERE, "vendor", "ootr"), os.path.join(HERE, "tools", "rando")]
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        import Main  # noqa: F401 - OoTR prints hint-table notes on import
    if "--probe" in args:
        out = args[args.index("--probe") + 1]
        sys.exit(0 if build_probe(out) else 1)
    out = build_tables()
    os.makedirs(os.path.dirname(TABLES), exist_ok=True)
    with open(TABLES, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {TABLES}: {len(out['codes'])} item codes")


if __name__ == "__main__":
    main()
