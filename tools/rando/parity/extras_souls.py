"""Parity plugin for Ship of Harkinian's soul items (SoH Shuffle Boss Souls, Shuffle Bean Souls, Ganon's Soul as a
shuffled item). Every option is a remake setting and off by default. With all of them off the plugin changes
nothing, no item, no rule, no patch. I only read SoH's code as a factual reference. The
features of the "impossible" list were re-checked with the same
tools.

Settings (value: default first):
- remake_shuffle_boss_souls False | True (SoH RSK_SHUFFLE_BOSS_SOULS): eight new items, "<Boss> Soul". You can
  only fight a dungeon boss once you've found its soul. In SoH the boss just isn't in its room. The remake's bosses
  appear through their arena's scene, which creates and places the boss, so that scene is where we ask for the
  soul. Without it you get a message and the dungeon's own doorway routine sends Link back to the dungeon's
  entrance (Dm_SY_BancChangeGo:EntryPoint0 with the overworld doorway's level, start position and arrival scene).
  Barinade's scene belongs to his door, so the door just stays shut. The question is the scene's first step and
  nothing of the arena's state changes before it, so the boss shows up as usual when you come back with the soul.
  The boss rush (DreamWorld) is untouched.
- remake_shuffle_ganons_soul False | True (SoH RSK_GANONS_SOUL "Anywhere"): a new item, "Ganon Soul". Without it
  the boss-key door to Ganondorf stays shut (its scene starts the fight). Can't be on with remake_ganons_soul,
  which is extras_story's count variant of the same door.
- remake_shuffle_bean_souls False | True (SoH RSK_SHUFFLE_BEAN_SOULS): ten new items, "<Place> Bean Soul". A soil
  patch and the leaf platform that grows from it are only there once its soul is found. Until then you can't
  plant a magic bean there or drop bugs in for its Gold Skulltula, and with plant_beans the grown plant waits for
  the soul too. It's done with Presence edits on the soil (child) and leaf platform (adult) placements, through
  new expression flags that combine their vanilla age condition and the soul (make_patch add_boolexp).

- remake_shuffle_enemy_souls "off" | "all" | "regional" (OoT3DR ShuffleEnemySouls "All enemies", OoTR Dev-Rob
  shuffle_enemy_spawns "all", OotrR's "all" and "regional").
  "all" is every boss soul (like remake_shuffle_boss_souls) plus one soul per regular enemy family, all 39 of
  OotrR's (data/rando/extras_enemy_souls.json from tools/rando/parity/_enemy_souls_build.py, 872 placements).
  "regional" is one soul per map folder for the same placements (25), and a dungeon's boss is gated by its
  region's soul (no boss souls).
  An enemy without its soul isn't there, like in OotrR (facts from github.com/Mozencaz/OotrR soul_adapter.py,
  remake_world.py). Its placement's Presence reads the soul's flag, a new saved Bool of ours
  (Rando_EnemySoul_<Key>), AND whatever Presence it has (finalize, after every plugin's plan). A room that shuts
  Link in until its enemies are beaten only has its doors when every soul gating them is found ("doors": 116,
  OotrR's room locks, also read from the room logic modules), so without them it's an open passage.
  Logic: with "all", OoTR's has_soul(<Enemy>) asks for the soul (_install_has_soul), and with "regional" it's the
  region's soul. Either way (_enemy_logic) a spot whose item an enemy holds needs that enemy's soul, and the Deku
  Baba stick/nut events need the soul of the Deku Babas there. Entering a dungeon needs the souls of its
  mechanical enemies, the ones whose defeat drives a chest, a platform, a fuse or a story step. Each overworld
  check a defeat opens (the meadow's gate, five grotto chests) needs its enemies' souls. 8 placements are left
  unbound (data "unbound" says why).
  With the enemizer (remake_enemizer), an enemy it swaps takes its NEW family's soul in its Presence, its room
  locks, held items and the logic (seed_view gets enemizer.swaps from the seed, before the fill). A type with no
  soul (a Poe in a Guay's place) is always there, like every Poe (verify: _verify_retyped).
- remake_skeleton_key False | True (SoH RSK_SKELETON_KEY): a new item, "Skeleton Key", added to the pool (the
  small keys stay). It opens every small-key door. Its scene adds each dungeon's full key count to that dungeon's
  saved key counter (DungeonInfo.<area>.SmallKeyNum), with the first-key flag and total set like the game's own
  key add, the same way the dungeons plugin's key rings do it. Thieves' Hideout is included, the Treasure Chest
  Game isn't. It also meets every small-key condition in OoTR's logic, rewritten as OoTR reads its logic files:
  (Small_Key_X, n) -> ((Small_Key_X, n) or Skeleton_Key).

The items are given by a scene of ours in Dm_SY_GetInEvent. It sets the soul's flag, holds up its figure with the
item-get fanfare (held_nodes, and in the air or water only the fanfare), then shows its message. It's called
where the location's give step was. That covers the core scene locations' steps (make_patch scene_call_ops, like
the ice trap and dungeon items) and every other give path that calls an entry (songs_trade._target names it):
the songs/trade NPCs and their reward specs, the get scene of drop spots and fairies (in the air or water a copy
of its steps, resident_steps), the scrub sales and the carpet salesman (shops.call_marker), the silver-rupee
spots, the hideout jails and the Treasure Chest Game salesman. Only chests (one actor, no scene for these items)
and shop shelves refuse them (_forbidden).
Their flags are borrowed saved flags (tools/rando/free_flags.py) from this plugin's fixed list (data
"flags_claimed"). That list comes from the middle of the pool, since the drops plugin takes from its front and
the fairies plugin from its end. In a seed with souls free_flags leaves ours out of the pool they take from, and
verify checks the plan.

The logic is in data/rando/logic/extras_souls.json, applied by this plugin rather than as plain overrides. None of
this has been seen in-game.
"""
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))

DATA_PATH = os.path.join(HERE, "data", "rando", "extras_souls_data.json")
LOGIC_PATH = os.path.join(HERE, "data", "rando", "logic", "extras_souls.json")
_data = _logic = None

BOSS, GANON, BEAN = "remake_shuffle_boss_souls", "remake_shuffle_ganons_soul", "remake_shuffle_bean_souls"
KEY = "remake_skeleton_key"
ENEMY = "remake_shuffle_enemy_souls"
REMAKE_SETTINGS = {BOSS: (False, True), GANON: (False, True), BEAN: (False, True), KEY: (False, True),
                   ENEMY: ("off", "all", "regional")}
REMAKE_DEFAULTS = {BOSS: False, GANON: False, BEAN: False, KEY: False, ENEMY: "off"}
ENEMY_DATA = os.path.join(HERE, "data", "rando", "extras_enemy_souls.json")  # parity/_enemy_souls_build.py
_enemy = None
SKELETON = "Skeleton Key"
KEY_WORDS_SKIP = "Treasure_Chest_Game"  # its keys are the game's own timer keys (SoH's key doesn't open them either)
DUNGEONS_WORLD = os.path.join(HERE, "data", "rando", "dungeons_world.json")
HOST_FILE = "Dm_SY_GetInEvent"          # the give entries (Player_Event, GameSystemActor, GameDataActor)
MSG_FILE = "GetPouchContent"            # the message entries (copies of its system-text talk, Event23)
TEXT_FILE = "EventFlowMsg/Item_Event.msbt"
YES, NO = 0, 1     # query answers (case 0 = yes)
# A soul's give has to hold up its figure, without that there's no hold-up, no fanfare and no model. It uses the
# hold-up steps of the Kokiri Wallet's give (extras_items.wallet_graph, seen in game). Link holds up the soul's
# display (config/hold_up.json "displays" Rando_Show_Soul*, the figure of its enemy from parity/_show_models.py).
# The locator, pose, fanfare and glow read the pouch type of SHOW_TYPE like the wallet's do. That's a key item with
# GetType Large, which gives the big hold-up pose and the item-get fanfare with no action guide. Then come the
# soul's flag and message.
SHOW_TYPE = "Pouch_Wallet_Small"
_state = {}        # id(world) -> {"items": {item: (kind, key)}, "allowed"/"forbidden", "record": world_plan's}
_entries = {}      # OoTR item -> "Dm_SY_GetInEvent:<its give entry>" for this seed (keep_locations; call_target)


def data():
    global _data
    if _data is None:
        _data = json.load(open(DATA_PATH, encoding="utf-8"))
    return _data


def enemy_data():
    """{key: entry} of data/rando/extras_enemy_souls.json. That's every family (only the ones with a soul have "item")
    and the regional mode's souls (key "R_<code>", "region" is its map folder). A regional soul has the same
    placements grouped by folder, the region's name where a family has its name, no OoTR has_soul token, and the
    figure of its boss or its most common enemy ("figure_of")."""
    global _enemy
    if _enemy is None:
        d = json.load(open(ENEMY_DATA, encoding="utf-8"))
        out = dict(d["families"])
        folder_ps = {}
        for k, e in d["families"].items():
            for p in e.get("placements") or []:
                folder_ps.setdefault(p["folder"], []).append(dict(p, family=k))
        for folder, r in sorted((d.get("regions") or {}).items()):
            out["R_" + r["code"]] = {"name": r["words"], "tokens": [], "item": r["item"], "flag": r["flag"],
                                     "display": r["display"], "figure_of": r["figure_of"], "region": folder,
                                     "dungeon": r.get("dungeon"), "boss": r.get("boss"),
                                     "placements": folder_ps.get(folder, []),
                                     "dungeons": [folder] if r.get("mechanical") else []}
        _enemy = out
    return _enemy


def enemy_extra():
    """The room-lock doors, the overworld checks and the dungeon folders of data/rando/extras_enemy_souls.json."""
    d = json.load(open(ENEMY_DATA, encoding="utf-8"))
    return {"doors": d.get("doors") or [], "overworld": d.get("overworld") or [], "dungeons": d.get("dungeons") or {}}


def _family_of(gyaml):
    """The soul family of an enemy type, or None. It follows the data's rule (OotrR's prefixes and left-out kinds)."""
    from parity._enemy_souls_build import family_of
    return family_of(gyaml)


_views = {}


def seed_view(settings):
    """(families, extra, swapped): enemy_data() and enemy_extra() with this seed's enemizer swaps applied. The swaps
    come from remake_enemizer's enemizer.swaps, worked out from the seed alone, so the logic has them before the
    fill. finalize checks the plan's type edits against them. Without swaps it's just enemy_data(), enemy_extra(),
    []."""
    from parity import enemizer
    sw = enemizer.swaps(settings)
    if not sw:
        return enemy_data(), enemy_extra(), []
    key = tuple(sorted((f, h, new) for (f, h), (_s, new) in sw.items()))
    if key not in _views:
        _views[key] = _view_of(json.load(open(ENEMY_DATA, encoding="utf-8")), sw)
    return _views[key]


def _view_of(d, sw):
    """The souls data (as enemy_data / enemy_extra give it) with swaps {(file, hash): (enemizer slot, new type)}.
    A swapped placement takes its NEW family's soul, so it leaves its old family's placements and joins the new
    one's. A place of a type with no soul, like a Poe's, joins when it becomes a Keese or a Guay. The enemizer only
    swaps free slots across families, with nothing linking either way, no logic module and no name, so its absence
    holds nothing up.
    The room locks' families, each family's mechanical dungeons and each overworld check's families are read again
    from the placements, so the doors, the dungeon entries and the checks follow the new family. Regions go by
    folder, so only a soulless swap moves in or out of one.
    These stay ungated, with the reason in swapped[i]["why"]: one of the 8 unbound (a scene acts on it), a place
    outside the soul folders (OotrR's boss rush and Ganon's tower), and a placement that becomes a type with no soul,
    like a Guay that becomes a Poe. OotrR leaves Poes out, so a Poe is always there."""
    from parity._enemy_souls_build import EXCLUDED_FOLDERS
    raw = d["families"]
    at = {(p["file"], str(p["hash"])): k for k, e in raw.items() for p in e.get("placements") or []}
    unbound = {(p["file"], str(p["hash"])): p["why"] for e in raw.values() for p in e.get("unbound") or []}
    ps = {k: list(e.get("placements") or []) for k, e in raw.items()}
    swapped = []
    for (f, h), (slot, new) in sorted(sw.items()):
        old, fam, folder = at.get((f, h)), _family_of(new), f.split("/")[1]
        s = {"file": f, "hash": h, "from": slot["actor"], "to": new, "old_family": old, "family": None}
        swapped.append(s)
        if (f, h) in unbound:
            s["why"] = f"one of the unbound: {unbound[(f, h)]}"
            continue
        if old is None and (folder in EXCLUDED_FOLDERS or not f.startswith("Banc/")):
            s["why"] = f"no souls in {folder} (OotrR leaves the boss rush and Ganon's tower out)"
            continue
        if old is None and _family_of(slot["actor"]) is not None:
            raise RuntimeError(f"extras_souls: {f} {h} ({slot['actor']}) has a soul family but isn't in the souls "
                               f"data (rebuild data/rando/extras_enemy_souls.json)")
        i = None if old is None else next(j for j, p in enumerate(ps[old]) if (p["file"], str(p["hash"])) == (f, h))
        if fam is None or not raw.get(fam, {}).get("item"):
            s["why"] = f"{new} has no soul (OotrR leaves its kind out: it is always there)"
            if i is not None:
                ps[old].pop(i)
            continue
        s["family"] = fam
        if fam == old:
            ps[old][i] = dict(ps[old][i], gyaml=new)
            continue
        if i is not None:
            p = ps[old].pop(i)
        elif slot["watched"] or slot["rails"] or slot["skip"]:
            raise RuntimeError(f"extras_souls: the enemizer made the watched {slot['actor']} {f} {h} a {new}: its "
                               f"soul would need its room's locks and mechanics, which the souls data doesn't have")
        else:
            p = {"file": f, "hash": h, "gyaml": slot["actor"], "folder": folder, "doors": [], "chests": [],
                 "effects": [], "mechanical": False, "joined": slot["actor"]}  # finalize handles its vanilla Presence
        ps[fam].append(dict(p, gyaml=new))
    dungeons = d.get("dungeons") or {}
    fams = {}
    for k, e in raw.items():
        e = dict(e, placements=ps[k])
        if e.get("item"):
            e["dungeons"] = sorted({p["folder"] for p in ps[k] if p["folder"] in dungeons and p.get("mechanical")})
        fams[k] = e
    opens, checks = {}, {}  # (door file, door hash) / check name -> families, folders
    for k, e in fams.items():
        for p in e["placements"]:
            for dr in p.get("doors") or []:
                opens.setdefault((p["file"], str(dr)), set()).add(k)
            for c in p.get("checks") or []:
                checks.setdefault(c, (set(), set()))[0].add(k)
                checks[c][1].add(p["folder"])
    doors = [dict(dr, families=sorted(opens.get((dr["file"], str(dr["hash"])), ()))) for dr in d.get("doors") or []]
    ow = []
    for r in d.get("overworld") or []:
        fs_, folders = checks.get(r.get("location") or " -> ".join(r["exit"]), ((), ()))
        ow.append(dict(r, families=sorted(fs_), folders=sorted(folders)))
    folder_ps = {}  # the regional souls, as enemy_data() makes them, from these placements
    for k, e in fams.items():
        for p in e["placements"]:
            folder_ps.setdefault(p["folder"], []).append(dict(p, family=k))
    for folder, r in sorted((d.get("regions") or {}).items()):
        here = folder_ps.get(folder, [])
        fams["R_" + r["code"]] = {"name": r["words"], "tokens": [], "item": r["item"], "flag": r["flag"],
                                  "display": r["display"], "figure_of": r["figure_of"], "region": folder,
                                  "dungeon": r.get("dungeon"), "boss": r.get("boss"), "placements": here,
                                  "dungeons": [folder] if folder in dungeons and any(p.get("mechanical")
                                                                                     for p in here) else []}
    return fams, {"doors": doors, "overworld": ow, "dungeons": dungeons}, swapped


def _vanilla_presence(ps):
    """The vanilla Presence ({flag, neg, lazy}, same shape as the data's) of placements the souls data doesn't list,
    like a Poe's place that a swap gave a family. Read from the game files once. finalize ANDs the soul with it."""
    todo = [p for p in ps if not p.get("presence_read")]
    if not todo:
        return
    from romtools import Romfs, byml_load
    fs = Romfs(os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(),
               os.path.join(HERE, "original"))
    docs = {}
    for p in todo:
        if p["file"] not in docs:
            docs[p["file"]] = {str(a.get("Hash")): a for a in byml_load(fs.read(p["file"]), allow_big=True)[0]
                               .get("Actors") or []}
        a = docs[p["file"]].get(str(p["hash"]))
        if a is None or a.get("Gyaml") != p["joined"] or a.get("Links") or a.get("Name"):
            raise RuntimeError(f"extras_souls: {p['file']} {p['hash']}: not the free {p['joined']} the enemizer data "
                               f"says")
        pr = a.get("Presence")
        if pr:
            p["presence"] = {"flag": pr["FlagName"], "neg": bool(pr.get("IsNegation")),
                             "lazy": bool(pr.get("IsCheckLazy"))}
        p["presence_read"] = True


def regional(settings):
    return value(settings, ENEMY) == "regional"


def logic():
    global _logic
    if _logic is None:
        _logic = json.load(open(LOGIC_PATH, encoding="utf-8"))["options"]
    return _logic


def _remake(settings):
    return getattr(settings, "remake", None) or {}


def value(settings, key):
    return _remake(settings).get(key, REMAKE_DEFAULTS[key])


def items(settings):
    """{OoTR item name: (kind, key)} of the souls these settings add, kind "boss" / "ganon" / "bean" / "key" /
    "enemy"."""
    out = {}
    enemies = value(settings, ENEMY) == "all"
    regions = value(settings, ENEMY) == "regional"  # OotrR's "regional" mode, one soul per map folder
    # The dungeon's boss is in it too. Its region's soul gates it and it has no boss soul of its own.
    if (value(settings, BOSS) or enemies) and not regions:  # all enemies means the bosses too, like OoT3DR and OotrR
        out.update({v["item"]: ("boss", k) for k, v in logic()["bosses"].items()})
    if regions:
        out.update({e["item"]: ("enemy", k) for k, e in enemy_data().items() if e.get("item") and e.get("region")})
    if value(settings, GANON):
        out[logic()["ganon"]["item"]] = ("ganon", "ganon")
    if value(settings, BEAN):
        out.update({b["item"]: ("bean", i) for i, b in enumerate(logic()["beans"])})
    if value(settings, KEY):
        out[SKELETON] = ("key", "skeleton")
    if enemies:
        out.update({e["item"]: ("enemy", k) for k, e in enemy_data().items() if e.get("item") and not e.get("region")})
    return out


def _token(name):
    from RulesCommon import escape_name
    return escape_name(name)


# Settings
def check_settings(settings):
    out = []
    remake = _remake(settings)
    for k, v in remake.items():
        if k == ENEMY:
            if v not in REMAKE_SETTINGS[k]:
                out.append(f"{k} = {v!r}: extras_souls can make {' or '.join(map(repr, REMAKE_SETTINGS[k]))}")
            continue
        if k in REMAKE_SETTINGS:
            if v not in REMAKE_SETTINGS[k] or not isinstance(v, bool):
                out.append(f"{k} = {v!r}: extras_souls can make true or false")
            continue
        near = difflib.get_close_matches(k, list(REMAKE_SETTINGS), n=1, cutoff=0.85)
        if near:
            out.append(f"{k}: unknown remake setting; did you mean {near[0]}?")
    if remake.get(GANON) is True and remake.get("remake_ganons_soul", "off") != "off":
        out.append(f"{GANON} with remake_ganons_soul {remake['remake_ganons_soul']!r}: both gate the door to "
                   f"Ganondorf; choose one (SoH's Ganon's Soul is either an item or a count)")
    if remake.get(BOSS) is True and remake.get(ENEMY) == "regional":
        out.append(f"{BOSS} with {ENEMY} 'regional': a regional soul already lets you fight its dungeon's boss (OotrR's "
                   f"regional souls); choose one")
    if remake.get(BOSS) is True and getattr(settings, "shuffle_bosses", "off") != "off":
        out.append(f"{BOSS} with shuffle_bosses: the remake's boss rooms are inside their dungeons (no doorway to "
                   f"move), so the remake can't shuffle bosses")
    return out


def untested(settings):
    out = []
    if value(settings, BOSS):
        out.append("extras_souls: remake_shuffle_boss_souls (a boss arena's scene asks for the soul; without it a "
                   "message and the dungeon's doorway routine back to its entrance)")
    if value(settings, GANON):
        out.append("extras_souls: remake_shuffle_ganons_soul (Ganondorf's door scene asks for the soul)")
    if value(settings, BEAN):
        out.append("extras_souls: remake_shuffle_bean_souls (soil and leaf platform Presence: age and soul)")
    if value(settings, KEY):
        out.append("extras_souls: remake_skeleton_key (its scene adds every dungeon's key count to its saved counter)")
    if value(settings, ENEMY) in ("all", "regional"):
        out.append("extras_souls: remake_shuffle_enemy_souls (enemy Presence on the soul's new saved Bool, ANDed with "
                   "the enemy's own; the regular enemies' figures; room-lock doors there only with their souls; "
                   "every family, the 15 new ones' figures, the regional souls)")
    if items(settings):
        out.append("extras_souls: soul get scenes (borrowed flag + message, called from the location's give step)")
    return out


# OoTR tables (before the world is built)
_texts = {}


def _hint_words(name):
    if name == SKELETON:
        return "#a key that opens everything#", "#the Skeleton Key#"
    plain = name.replace(" Soul", "")
    return f"the soul of #{plain}#", f"#{name}#"


_key = {"on": False, "beans": False, "installed": False}
_KEY_RX = re.compile(r"\(\s*(Small_Key_(?!" + KEY_WORDS_SKIP + r")\w+)\s*,\s*(\d+)\s*\)|\b(Small_Key_(?!"
                     + KEY_WORDS_SKIP + r")\w+)\b")


def _key_rule(rule):
    def sub(m):
        if m.group(1):
            return f"(({m.group(1)}, {m.group(2)}) or Skeleton_Key)"
        return f"({m.group(3)} or Skeleton_Key)"
    return _KEY_RX.sub(sub, rule)


def _bean_at_rule(rule):
    """at('<a soil's region>', ...) anywhere, in a helper or another region's rule (e.g. guarantee_trade_path's
    at('DMC Central Local', ... can_plant_bean)). The bean words inside it also need that soil's soul. Rules inside
    the soil's own regions get rewritten on the built world instead (apply_logic)."""
    regions = {r: _token(b["item"]) for b in logic()["beans"] for r in b["regions"]}
    words = re.compile(r"\b(" + "|".join(map(re.escape, logic()["bean_words"])) + r")\b")
    out, i = [], 0
    for m in re.finditer(r"\bat\(\s*'([^']+)'\s*,", rule):
        if m.start() < i or m.group(1) not in regions:
            continue
        depth, j = 1, m.end()
        while j < len(rule) and depth:
            depth += {"(": 1, ")": -1}.get(rule[j], 0)
            j += 1
        tok = regions[m.group(1)]
        out.append(rule[i:m.end()])
        out.append(words.sub(lambda w, t=tok: f"({w.group(1)} and {t})", rule[m.end():j]))
        i = j
    out.append(rule[i:])
    return "".join(out)


def _key_rewrite(d):
    """Rewrites the rule strings (dict values) of a parsed OoTR logic file. With the Skeleton Key it also meets every
    small-key condition, and with bean souls an at() for a soil's region needs its soul."""
    if isinstance(d, dict):
        return {k: _key_rewrite(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_key_rewrite(v) for v in d]
    if isinstance(d, str):
        if _key["on"] and "Small_Key_" in d:
            d = _key_rule(d)
        if _key["beans"] and "at(" in d:
            d = _bean_at_rule(d)
    return d


def _install_key_logic(on, beans=False):
    """Wraps OoTR's logic reader once, like the shops plugin's gate does. It reads the settings of the seed being
    built."""
    _key["on"], _key["beans"] = on, beans
    if _key["installed"] or not (on or beans):
        return
    import RuleParser
    import Utils
    import World
    inner = Utils.read_logic_file

    def read(path):
        data = inner(path)
        return _key_rewrite(data) if _key["on"] or _key["beans"] else data
    read.remake = True
    for module in (Utils, RuleParser, World):
        module.read_logic_file = read
    RuleParser.rule_aliases.clear()  # helpers reload through the rewrite on the next parse
    RuleParser.nonaliases.clear()
    _key["installed"] = True


def before_build(settings):
    _install_key_logic(bool(value(settings, KEY)), bool(value(settings, BEAN)))
    import free_flags  # the souls' flags are only held for this seed, and none when no soul is on
    free_flags.hold("extras_souls", data()["flags_claimed"][:sum(1 for kind, _ in items(settings).values()
                                                                 if kind not in ("key", "enemy"))])
    _install_has_soul()
    new = items(settings)
    if not new:
        return
    import HintList
    import Item
    import ItemList
    import Language
    for name in new:
        if name not in ItemList.item_table:
            ItemList.item_table[name] = ("Item", True, None, None)
        if name not in Item.ItemInfo.items:
            Item.ItemInfo.items[name] = Item.ItemInfo(name)
        vague, clear = _hint_words(name)
        _texts[name] = (vague, clear, "item")
        HintList.hintTable.setdefault(name, _texts[name])
    if not getattr(Language.Language.__init__, "remake_extras_souls", False):
        original = Language.Language.__init__

        def init(self, lang, _original=original):  # every language's hint table (World makes one per world)
            _original(self, lang)
            for n, (vague, clear, _) in _texts.items():
                self.hintTable.setdefault(n, {"vague_hint": vague, "clear_hint": clear, "gender": "no_gender"})
        init.remake_extras_souls = True
        Language.Language.__init__ = init


# Pool, rules, logic
def keep_locations(world, settings):
    """Each soul replaces one junk item of the pool (OoTR's fill needs as many items as locations)."""
    new = items(settings)
    _state[id(world)] = {"items": new}
    _entries.clear()
    _entries.update({n: f"{HOST_FILE}:{_entry(*v)}" for n, v in new.items()})
    if not new:
        return set()
    from Item import ItemFactory
    pool = world.itempool
    for name in sorted(new):
        k = next((i for i in range(len(pool) - 1, -1, -1) if not pool[i].advancement and not pool[i].priority
                  and not pool[i].dungeonitem and pool[i].name not in new), None)
        if k is None:
            raise ValueError(f"extras_souls: no junk item left to make room for {name}")
        pool[k] = ItemFactory(name, world)
    return set()


def _scene_locations():
    from parity import chests
    return chests._scene_locations()


def call_target(item):
    """'Dm_SY_GetInEvent:<entry>' that gives this seed's soul or Skeleton Key `item`, or None. Any give path that
    calls an entry uses it (songs_trade._target)."""
    return _entries.get(item)


def _forbidden(world):
    """Where no give step can call the items' entries. That's the chests (the core's chest_map ones, the chests
    plugin's own, the dungeons plugin's kept ones, any OoTR Chest), because a chest gives one actor and has no scene
    for these items, and the shop shelves (Shop_* actors only). Everywhere else gives them through its call path."""
    from parity import _songs_trade_ops
    return _songs_trade_ops.no_call_locations(world)


def resident_steps(item, world):
    """A copy of the give entry's steps for the get scene in the air or water. A resident scene can only call its own
    files and GetPouchContent (_songs_trade_lake._resident_give). The copy sets the flag (or the Skeleton Key's key
    rows) and then shows the message (GetPouchContent). It comes from this plugin's plan, since our world_plan runs
    before the songs/trade plugin's."""
    rec = ((_state.get(id(world)) or {}).get("record") or {}).get("gives", {}).get(item)
    if rec is None:
        raise RuntimeError(f"extras_souls: no give entry for {item} in this seed's plan")
    steps = list(_key_credit()) if rec.get("flag") is None else [
        {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
         "params": {"GameDataName": rec["flag"], "Index": -1, "Value": True}}]
    if rec.get("display"):  # no hold-up under water or in the air, like every item there: fanfare and window only
        steps.append(_fanfare())
    return steps + [{"call": f"{MSG_FILE}:{rec['message']}"}]


def _fanfare():
    """The item-get fanfare of SHOW_TYPE (Dm_SY_GetInEvent Item_Position Event186's step)."""
    return {"actor": "SoundSystemActor", "action": "EventTriggerSoundStartFanfare",
            "params": {"GameDataName": "", "IsEnableIntro": False, "ActorName": SHOW_TYPE}}


def display_of(kind, key):
    """The hold-up display of a soul (config/hold_up.json "displays" Rando_Show_Soul*), or None (the Skeleton Key)."""
    from parity import _show_models
    if kind == "key":
        return None
    if kind == "enemy":
        return _show_models.SOUL_DISPLAYS["enemy_" + key][0]
    return _show_models.SOUL_DISPLAYS["bean" if kind == "bean" else key][0]


def held_nodes(flag, display, message):
    """A soul's give as (nodes, start). It sets the flag, holds up the figure (the Kokiri Wallet's hold-up steps from
    extras_items.wallet_graph), shows the message and puts the figure away."""
    return {
        "set": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                "params": {"GameDataName": flag, "Index": -1, "Value": True}, "next": "show"},
        "show": {"actor": "Player_Event", "action": "EventCreateShowItemFromActorFileName",
                 "params": {"IsWaitEnd": True, "Actor": display}, "next": "locator"},
        "locator": {"call": ":GetInEvent_SetLocator", "params": {"ActorName": SHOW_TYPE}, "next": "anim"},
        "anim": {"call": ":GetInEvent_Animation", "params": {"ActorName": SHOW_TYPE}, "next": "pos"},
        "pos": {"call": ":Item_Position", "params": {"ActorName": SHOW_TYPE}, "next": "msg"},
        "msg": {"call": message, "next": "away"},
        "away": {"fork": ["hide", "wait"], "join": "done"},
        "hide": {"actor": "Player_Event", "action": "EventDeleteShowItem",
                 "params": {"IsWaitEnd": True, "IsFadeOut": False, "IsScaleOut": False,
                            "ChangeVisibleOffWithRequestDelete": False}, "next": None},
        "wait": {"actor": "EventSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 1},
                 "next": "glowoff"},
        "glowoff": {"actor": "EventEffectEmitter", "action": "EventEffectStopGetItem", "next": None},
        "done": {"join": True, "next": None},
    }, "set"


def _allowed(world):
    """Where the new items can go. That's the core scene locations, whose give step is the generator's and gets
    replaced by a call. Not the ones another plugin gives itself (its keep_locations set, the plugins' "_kept"),
    like the songs/trade plugin's Kak 100 Gold Skulltula Reward and rolling Goron, whose give targets don't know
    these items."""
    claimed = set()
    for name, mod in list(sys.modules.items()):
        if not name.startswith("parity.") or name == __name__:
            continue
        kept = getattr(mod, "_kept", None)
        v = kept.get(id(world)) if isinstance(kept, dict) else None
        if isinstance(v, (set, frozenset, list, tuple, dict)):
            claimed |= set(v)
    st = sys.modules.get("parity.songs_trade")
    if st is not None and getattr(world.settings, "shuffle_100_skulltula_rupee", False):
        claimed.add(st.GS100)  # its first visit is the songs/trade plugin's own give (_gs100_ops), not in its _kept
    return set(_scene_locations()) - claimed


def _set_rule(world, spot, rule):
    spot.rule_string = rule
    world.parser.parse_spot_rule(spot)


def _entrances_into(world, region):
    found = [e for e in world.get_entrances() if getattr(e.connected_region, "name", e.connected_region) == region]
    if not found:
        raise RuntimeError(f"extras_souls: no exit into {region} (OoTR's or the remake's logic changed)")
    return found


def _install_has_soul():
    """Makes OoTR's State.has_soul ask for the enemy's soul when this world has enemy souls. In OoTR it's a stub that's
    always true, called by its glitch rules and our drops plugin's kill rules. world.remake_enemy_souls maps
    {OoTR enemy name: the soul item's solver id}, and the rule parser passes has_soul(Deku_Baba) as "Deku Baba". An
    enemy with no soul in the seed is always there."""
    import State as _S
    if getattr(_S.State.has_soul, "remake_enemy_souls", False):
        return

    def has_soul(self, enemy, **kwargs):
        souls = getattr(self.world, "remake_enemy_souls", None)
        if not souls:
            return True
        sid = souls.get(enemy)
        return True if sid is None else self.solv_items[sid] >= 1
    has_soul.remake_enemy_souls = True
    _S.State.has_soul = has_soul


DEKU_BABA_EVENTS = ("Deku Baba Sticks", "Deku Baba Nuts")


SCENE_FOLDERS = {"Lost Woods": "LostWood", "Death Mountain": "DeathMountainTrail", "Haunted Wasteland": "HountedWasteland",
                 "Castle Grounds": "HyruleCastle", "Market Entrance": "Market", "ZR": "ZoraRiver"}


def _folder_of_region(region):
    """The map folder an OoTR region is in. Its dungeon's if it has one, else its scene's (spaces dropped,
    SCENE_FOLDERS)."""
    dg = getattr(getattr(region, "dungeon", None), "name", None) or getattr(region, "dungeon_name", None)
    if dg:
        return {v: k for k, v in enemy_extra()["dungeons"].items()}.get(dg)
    sc = getattr(region, "scene", None)
    return SCENE_FOLDERS.get(sc, sc.replace(" ", "")) if sc else None


def _enemy_logic(world, new):
    """The enemy souls' rules. It's OotrR's logic, made exact where the game files say more. With "all", has_soul
    answers from the pool, so OoTR's can_kill_* helpers ask for the family's soul. With "regional", has_soul is
    always true and we ask for the region's soul where its enemies matter. Either way:
    - a spot whose item an enemy holds (a drops-plugin spot on a gated placement) needs that enemy's soul
    - the Deku Baba stick and nut events need the soul of the Deku Babas there
    - entering a dungeon needs the souls of its mechanical enemies, the ones whose defeat drives something besides a
      room's door: a chest that appears, a platform, a fuse, a story step. Doors are just absent without their soul.
    - each overworld check a defeat opens (data "overworld", the meadow's gate and the grotto chests that appear)
      needs the soul of the enemies there
    With the enemizer it all comes from the seed's swapped placements (seed_view gives a swapped enemy its new
    family). Returns the changed spots' names."""
    fams, extra, _ = seed_view(world.settings)
    from Item import ItemInfo
    region_mode = any(fams[key].get("region") for kind, key in new.values() if kind == "enemy")
    souls = {}
    for name, (kind, key) in new.items():
        if kind == "enemy" and not fams[key].get("region"):
            for tok in fams[key]["tokens"]:
                souls[tok.replace("_", " ")] = ItemInfo.solver_ids[_token(name)]
    world.remake_enemy_souls = souls
    _install_has_soul()
    # each family's / region's requirement, and each gated placement's
    need = {}      # family key or region folder -> rule text
    gated = {}     # (file, hash) -> rule text
    for name, (kind, key) in new.items():
        if kind != "enemy":
            continue
        e = fams[key]
        req = _token(name) if e.get("region") else f"has_soul({e['tokens'][0]})"
        need[e.get("region") or key] = req
        for p in e["placements"]:
            gated[(p["file"], str(p["hash"]))] = req

    def req_of(family, folder):
        return need.get(folder) if region_mode else need.get(family)

    changed = []

    def add(spot, req):
        if req:
            _set_rule(world, spot, f"({req}) and ({spot.rule_string})")
            changed.append(spot.name)

    import drops as drop_tools
    for loc in world.get_locations():
        if getattr(loc, "rule_string", None) is None:
            continue
        reqs = []
        if loc.name in DEKU_BABA_EVENTS:
            folder = _folder_of_region(loc.parent_region)
            if any(p["folder"] == folder for p in (fams.get("DekuBaba") or {}).get("placements") or []):
                reqs.append(req_of("DekuBaba", folder))
        else:
            e = drop_tools.lookup(loc.name) if gated else None
            for p in (e or {}).get("placements", []):
                r = gated.get((p.get("file"), str(p.get("hash"))))
                if r and r not in reqs:
                    reqs.append(r)
        for r in reqs:
            add(loc, r)
    # Require the mechanical enemies' souls at every entrance from outside the dungeon.
    for folder, dungeon in sorted(extra["dungeons"].items()):
        reqs = sorted({req_of(k, folder) for k, e in fams.items() if not e.get("region") and e.get("item")
                       and folder in (e.get("dungeons") or [])} - {None})
        if not reqs:
            continue
        ways = [x for x in world.get_entrances()
                if getattr(getattr(x.connected_region, "dungeon", None), "name", None) == dungeon
                and getattr(getattr(x.parent_region, "dungeon", None), "name", None) != dungeon]
        if not ways:
            raise RuntimeError(f"extras_souls: no way into {dungeon} (OoTR's logic changed)")
        for x in ways:
            add(x, " and ".join(reqs))
    # the overworld checks a defeat opens
    for r in extra["overworld"]:
        reqs = sorted({req_of(f, d) for f in r["families"] for d in r["folders"]} - {None})
        if not reqs:
            continue
        req = " and ".join(reqs)
        if r.get("age") == "child":
            req = f"is_adult or ({req})"
        if r.get("location"):
            try:
                spot = world.get_location(r["location"])
            except KeyError:
                continue  # (a chests-plugin location this seed doesn't have)
            add(spot, req)
        else:
            a, b = r["exit"]
            hits = [x for x in world.get_region(a).exits if getattr(x.connected_region, "name", None) == b]
            if not hits:
                raise RuntimeError(f"extras_souls: no exit {a} -> {b} (OoTR's logic changed)")
            for x in hits:
                add(x, req)
    return changed


def apply_logic(world, settings):
    """Puts the souls' rules on the built world. Every exit into a guarded boss room needs its soul, and every bean
    word in a soil's regions needs that soil's soul. Returns the changed spots' names."""
    new = items(settings)
    changed = []
    for name, (kind, key) in sorted(new.items()):
        tok = _token(name)
        if kind in ("boss", "ganon"):
            region = logic()["ganon"]["region"] if kind == "ganon" else logic()["bosses"][key]["region"]
            for e in _entrances_into(world, region):
                _set_rule(world, e, f"({e.rule_string}) and {tok}")
                changed.append(e.name)
        elif kind == "bean":
            words = logic()["bean_words"]
            rx = re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b")
            for rname in logic()["beans"][key]["regions"]:
                region = world.get_region(rname)
                spots = list(region.locations) + list(region.exits)
                for s in spots:
                    rule = getattr(s, "rule_string", None)
                    if not rule or not rx.search(rule):
                        continue
                    if " Subrule " in s.name:
                        continue  # here()'s own events: the rewritten rules make new ones (below)
                    _set_rule(world, s, rx.sub(lambda m, t=tok: f"({m.group(1)} and {t})", rule))
                    changed.append(s.name)
    fams = enemy_data()
    region_item = {fams[key]["region"]: name for name, (kind, key) in new.items()
                   if kind == "enemy" and fams[key].get("region")}
    for bkey, b in sorted(logic()["bosses"].items()):  # regional: a boss room needs its dungeon's region soul
        folder = data()["bosses"][bkey]["entrance"]["level"]
        if folder in region_item:
            tok = _token(region_item[folder])
            for e in _entrances_into(world, b["region"]):
                _set_rule(world, e, f"({e.rule_string}) and {tok}")
                changed.append(e.name)
    if any(k == "enemy" for k, _ in new.values()):
        changed += _enemy_logic(world, new)
    if any(k == "bean" for k, _ in new.values()):
        world.parser.create_delayed_rules()  # here(...) with a new inner rule made new subrule events
    world.remake_extras_souls_rules = changed
    return changed


def before_fill(world, settings):
    new = items(settings)
    if not new:
        return
    apply_logic(world, settings)
    forbidden = _forbidden(world)
    _state[id(world)]["forbidden"] = forbidden
    _state[id(world)]["allowed"] = _allowed(world)  # (the core scene locations item_for gives through)
    names = frozenset(new)
    for loc in world.get_locations():
        if loc.name not in forbidden:
            continue
        prev = loc.item_rule
        loc.item_rule = (lambda location, item, prev=prev: item.name not in names and prev(location, item))


def after_fill(world, settings):
    new = items(settings)
    if not new:
        return
    forbidden = (_state.get(id(world)) or {}).get("forbidden") or _forbidden(world)
    bad = [loc.name for loc in world.get_locations() if loc.item is not None and loc.item.name in new
           and loc.name in forbidden]
    if bad:
        raise RuntimeError(f"extras_souls: souls landed where no give step can call their entry: {bad}")


# Give targets
def _entry(kind, key):
    if kind == "key":
        return "Rando_SkeletonKey"
    if kind == "enemy":
        return f"Rando_Soul_Enemy_{key}"
    return f"Rando_Soul_{'Boss_' + key if kind == 'boss' else 'Ganon' if kind == 'ganon' else f'Bean_{key}'}"


def _key_credit():
    """The Skeleton Key's save-data steps. Each dungeon with locked doors gets its full key count (keys or doors,
    whichever is more, like the dungeons plugin's key rings), except the Treasure Chest Game. It's written the way
    the game does its own key add (parity/_dungeons_keys.py): the first-key flag (the HUD key counter and map-screen
    key show), the total, the count, then the key counter request (only shown for the dungeon the player is in)."""
    from ._dungeons_keys import key_rows, key_steps
    world = json.load(open(DUNGEONS_WORLD, encoding="utf-8"))["dungeons"]
    out = []
    for name, d in sorted(world.items()):
        n = max(d["keys"], d["doors"])
        if n:
            out += key_steps(key_rows(d["area"]), n, show=True)
    return out


def item_for(item, location, world):
    st = _state.get(id(world)) or {}
    hit = (st.get("items") or {}).get(item)
    if hit is None:
        return None
    rid = _scene_locations().get(location)
    if rid is None or location in (st.get("forbidden") or ()):
        raise RuntimeError(f"extras_souls: {item} at {location}, which no scene gives (the item rule should forbid it)")
    from parity import chests
    parts = [r for r in chests._catalog().values() if r.get("location") == rid or r["id"] == rid]
    if not parts:
        raise ValueError(f"{rid}: no catalogued give step")
    vanilla = {r["item"] for r in parts}
    # The placeholder is never handed over because the call replaces the give step, but it has to differ from
    # the vanilla item.
    return {"item": "Obj_Rupee_Blue" if "Obj_Rupee_Blue" not in vanilla else "Obj_Rupee_Green",
            "call": f"{HOST_FILE}:{_entry(*hit)}"}


# Patch plan
def _flags(world, n):
    """This plugin's n borrowed saved flags, from our fixed list (data "flags_claimed"). The build script picked them
    from tools/rando/free_flags.py's pool, going down from its index 100. For a seed with souls before_build holds
    them (free_flags.hold), so they're left out of the pool the drops plugin (from its front) and the fairies plugin
    (from its end) take from. verify checks it."""
    mine = data()["flags_claimed"]
    if n > len(mine):
        raise ValueError(f"extras_souls: {n} saved flags needed, {len(mine)} claimed")
    return mine[:n]


def _message(label, text, msgs, events):
    """A system-text message (a new label in Item_Event, every language) shown by a new GetPouchContent entry.
    Returns the call target."""
    # a whole new message ("markup": the text has no tags), as tools/rando/parity/_hints_check.py reads added labels
    msgs.append({"lang": "*", "file": TEXT_FILE, "label": label, "markup": text, "add": True})
    events.append({"file": MSG_FILE, "flowchart": MSG_FILE, "add_graph": label, "start": "t",
                   "nodes": {"t": {"copy": data()["message"]["step"], "next": None,
                                   "params_over": {"MessageId": f"{TEXT_FILE[:-5]}:{label}",
                                                   "IsOverrideStyle": False}}}})
    return f"{MSG_FILE}:{label}"


def _bool(flag, yes, no):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
            "params": {"GameDataName": flag, "Index": -1}, "cases": {YES: yes, NO: no}}


def _pre_hook(hook, nodes, start, events):
    """New steps in front of the hooked step `hook`, so every predecessor goes to them first. "@Event" means an
    existing step."""
    info = hook["info"]
    graph = f"Rando_Souls_{hook['step']}"
    events.append({"file": hook["file"], "flowchart": hook["flowchart"], "add_graph": graph, "nodes": nodes,
                   "start": start})
    for kind, where, k in info["preds"]:
        op = {"file": hook["file"], "flowchart": hook["flowchart"], "next": f"{graph}_{start}"}
        if kind == "entry":
            op["entry"] = where
        else:
            op["event"] = where
            if kind in ("case", "fork"):
                op[kind] = k
        events.append(op)


def _boss_gate(flag, deny_call, eject, hook, events):
    nodes = {"dream": {"actor": "GameSystemActor", "query": "EventQueryIsDreamWorld",
                       "cases": {YES: f"@{hook['step']}", NO: "soul"}},
             "soul": _bool(flag, f"@{hook['step']}", "deny"),
             "deny": {"call": deny_call, "next": "eject" if eject else None}}
    if eject:
        e = eject
        nodes["eject"] = {"call": "Dm_SY_BancChangeGo:EntryPoint0", "next": None,
                          "params": {"NextBanc": e["level"], "NextStartPos": e["start"], "BootEventName": e["boot"],
                                     "IsCheckAir": bool(e["air"]), "NextStartPosAir": e["air"]}}
    _pre_hook(hook, nodes, "dream", events)


def _possessive(name):
    return name + ("'" if name.endswith("s") else "'s")


def _names(new):
    """The seed's soul items in the order world_plan gives them flags and entries."""
    return sorted(new, key=lambda n: (("boss", "ganon", "bean", "key", "enemy").index(new[n][0]), str(new[n][1])))


def give_flags(world):
    """{soul item: its saved flag} the way world_plan sets them. The bosses', Ganon's and the bean souls' flags are
    borrowed ones in _names order, the enemy souls have their own Bools, and the Skeleton Key isn't in it. It's
    known after the fill, so the dungeons plugin, whose plan comes before ours, can give a soul after a big chest's
    cinematic (shown_give)."""
    new = (_state.get(id(world)) or {}).get("items") or {}
    names = _names(new)
    flagged = [n for n in names if new[n][0] not in ("key", "enemy")]
    flags = dict(zip(flagged, _flags(world, len(flagged)))) if flagged else {}
    fams = enemy_data()
    flags.update({n: fams[new[n][1]]["flag"] for n in names if new[n][0] == "enemy"})
    return flags


def shown_give(item, world):
    """(nodes, start) for soul `item`'s give after a big chest's cinematic has already held its figure up (the
    dungeons plugin's _Big entry). Without this the cinematic held up nothing and then our entry held the figure up
    a second time. So it's held_nodes without the hold-up: the flag, the message, the figure put away. None for an
    item with no figure, like the Skeleton Key, whose _Big entry still calls the full entry."""
    new = (_state.get(id(world)) or {}).get("items") or {}
    if item not in new:
        raise RuntimeError(f"extras_souls: {item} isn't one of this seed's soul items")
    kind, key = new[item]
    display = display_of(kind, key)
    if display is None:
        return None
    nodes, _ = held_nodes(give_flags(world)[item], display, f"{MSG_FILE}:{_entry(kind, key)}_Get")
    for label in ("show", "locator", "anim", "pos"):
        del nodes[label]
    nodes["set"] = dict(nodes["set"], next="msg")
    return nodes, "set"


def world_plan(settings, world):
    st = _state.get(id(world)) or {}
    new = st.get("items") or {}
    if not new:
        return {}
    d, lg = data(), logic()
    names = _names(new)
    flags = give_flags(world)
    fams, extra, swapped = seed_view(settings)  # with the enemizer's swaps, a swapped enemy is in its new family
    own = {n: flags[n] for n in names if new[n][0] == "enemy"}  # new saved Bools of our own
    events, msgs, placements, exps = [], [], [], {}
    record = {"flags": flags, "gives": {}, "gates": {}, "beans": {}, "enemies": {}}
    for name in names:
        kind, key = new[name]
        entry = _entry(kind, key)
        if kind == "key":
            call = _message(f"{entry}_Get", "You got the Skeleton Key!\nIt opens every locked door\nin every dungeon.",
                            msgs, events)
            credit = _key_credit()
            nodes = {f"c{i}": dict(st, next=f"c{i + 1}" if i + 1 < len(credit) else "msg")
                     for i, st in enumerate(credit)}
            nodes["msg"] = {"call": call, "next": None}
            events.append({"file": HOST_FILE, "flowchart": HOST_FILE, "add_graph": entry, "start": "c0",
                           "nodes": nodes})
            record["gives"][name] = {"entry": f"{HOST_FILE}:{entry}", "flag": None, "message": f"{entry}_Get",
                                     "credit": [st["params"]["GameDataName"] for st in credit
                                                if "GameDataName" in st["params"]]}  # (not the counter requests)
            continue
        if kind == "boss":
            boss = d["bosses"][key]["boss"]
            text = f"You got {_possessive(boss)} Soul!\n{boss} can now be fought."
        elif kind == "ganon":
            text = "You got Ganon's Soul!\nGanondorf can now be fought."
        elif kind == "enemy":
            fname = fams[key]["name"]
            text = f"You got the {fname} Soul!\n{fname} enemies can now appear."
        else:
            place = name[:-len(" Bean Soul")].replace("Zoras", "Zora's")
            text = f"You got the {place} Bean Soul!\nMagic beans can now grow there."
        call = _message(f"{entry}_Get", text, msgs, events)
        display = display_of(kind, key)
        nodes, start = held_nodes(flags[name], display, call)
        events.append({"file": HOST_FILE, "flowchart": HOST_FILE, "add_graph": entry, "start": start, "nodes": nodes})
        record["gives"][name] = {"entry": f"{HOST_FILE}:{entry}", "flag": flags[name], "message": f"{entry}_Get",
                                 "display": display}
        if kind == "boss":
            b = d["bosses"][key]
            boss = b["boss"]
            deny = _message(f"{entry}_Missing", f"{_possessive(boss)} soul is missing!\nYou can't fight {boss} "
                                                f"without it.", msgs, events)
            _boss_gate(flags[name], deny, b["entrance"] if b["eject"] else None, b["hook"], events)
            record["gates"][name] = {"file": b["hook"]["file"], "step": b["hook"]["step"],
                                     "eject": b["entrance"] if b["eject"] else None}
        elif kind == "enemy":  # their Presence is done in finalize, after every plugin's placements
            record["enemies"][name] = {"key": key, "flag": flags[name],
                                       "placements": [[p["file"], str(p["hash"])] for p in fams[key]["placements"]]}
        elif kind == "ganon":
            deny = _message(f"{entry}_Missing", "Ganon's soul is missing!\nYou can't face Ganondorf without it.",
                            msgs, events)
            _boss_gate(flags[name], deny, None, d["ganondorf"], events)
            record["gates"][name] = {"file": d["ganondorf"]["file"], "step": d["ganondorf"]["step"], "eject": None}
        else:
            b = d["beans"][key]
            if not b["fairy_locations"][0].startswith(lg["beans"][key]["fairy"]):
                raise RuntimeError(f"extras_souls: bean spot {key} is {b['fairy_locations'][0]}, logic says "
                                   f"{lg['beans'][key]['fairy']} (data and logic files out of step)")
            soil_exp, plant_exp = f"RandoBeanSoul_{key}_Soil", f"RandoBeanSoul_{key}_Plant"
            exps[soil_exp] = [[0, "Sequence_IsChildhood"], [0, flags[name]], [3]]
            exps[plant_exp] = [[0, "Sequence_IsChildhood"], [5], [0, flags[name]], [3]]
            for p in b["soils"]:
                placements.append({"file": p["file"], "hash": p["hash"], "note": f"extras_souls: {name}",
                                   "set": {"Presence": {"FlagName": soil_exp, "IsCheckLazy": False,
                                                        "IsNegation": False}}})
            for p in b["platforms"]:
                placements.append({"file": p["file"], "hash": p["hash"], "note": f"extras_souls: {name}",
                                   "set": {"Presence": {"FlagName": plant_exp, "IsCheckLazy": False,
                                                        "IsNegation": False}}})
            record["beans"][name] = {"soil": [[p["file"], p["hash"]] for p in b["soils"]],
                                     "platform": [[p["file"], p["hash"]] for p in b["platforms"]],
                                     "expressions": {soil_exp: exps[soil_exp], plant_exp: exps[plant_exp]}}
    region_of = {fams[key]["region"]: (name, key) for name, (kind, key) in new.items()
                 if kind == "enemy" and fams[key].get("region")}
    if region_of:  # regional: each dungeon boss's arena asks for its dungeon's region soul (no boss soul of its own)
        for bkey, b in sorted(d["bosses"].items()):
            folder = b["entrance"]["level"]
            if folder not in region_of:
                continue
            rname, rkey = region_of[folder]
            boss, words = b["boss"], fams[rkey]["name"]
            deny = _message(f"Rando_Soul_Region_{bkey}_Missing", f"The {words} Soul is missing!\nYou can't fight "
                                                                 f"{boss} without it.", msgs, events)
            _boss_gate(flags[rname], deny, b["entrance"] if b["eject"] else None, b["hook"], events)
            record["gates"][f"{boss} ({rname})"] = {"file": b["hook"]["file"], "step": b["hook"]["step"],
                                                    "eject": b["entrance"] if b["eject"] else None,
                                                    "flag": flags[rname]}
    # The room locks. If a soul in this seed gates some of a door's enemies, the door is only there with all of
    # those souls. These are OotrR's resolve_room_locks door edits with every family of the room gated, so the door's
    # own Presence AND each soul. Without one the room's door is absent (an open passage), and its enemies may be too.
    soul_flag = {}
    for name, (kind, key) in new.items():
        if kind == "enemy":
            soul_flag[fams[key].get("region") or key] = flags[name]
    doors = []
    for dr in extra["doors"]:
        fl = sorted({soul_flag.get(dr["folder"]) if region_of else soul_flag.get(f) for f in dr["families"]} - {None})
        if fl:
            doors.append({"file": dr["file"], "hash": dr["hash"], "gyaml": dr["gyaml"], "flags": fl,
                          "presence": dr.get("presence")})
    record["doors"] = doors
    if swapped and record["enemies"]:  # the enemizer's swaps and the soul each placement reads now
        # That's its new family's or its region's soul, or none and why (_verify_retyped reads it back).
        by = {fams[r["key"]].get("region") or r["key"]: n for n, r in record["enemies"].items()}
        record["enemizer"] = [dict(s, soul=by.get(s["file"].split("/")[1] if region_of else s["family"])
                                   if s["family"] else None) for s in swapped]
    _state.setdefault(id(world), {})["record"] = record  # for resident_steps (the songs/trade plugin's plan is next)
    plan = {"events": events, "text": msgs, "_extras_souls": record, "_verify_plugins": ["extras_souls"],
            "_notes_extras_souls": [f"{n}: given by {record['gives'][n]['entry']}"
                                    + (f", flag {flags[n]}" if n in flags else "") for n in names]}
    if placements:
        plan["placements"] = placements
    gd = {}
    if exps:
        gd["add_boolexp"] = exps
    if own:
        gd["add_bools"] = {f: False for f in sorted(own.values())}
    if gd:
        plan["gamedata"] = gd
    import free_flags  # the flags held for this seed, for the read-back (tools/rando/free_flags.py restore)
    plan.update(free_flags.held_plan("extras_souls"))
    return plan


def _check_retypes(plan, fams, swapped):
    """Checks that the plan's enemy type edits are the ones the souls' logic was built with (seed_view, before the
    fill). Every swap has to be in the plan the way the logic took it, and no other edit may turn a gated placement
    into another family's enemy, since it would read the wrong soul and the logic wouldn't know. Raises otherwise."""
    final = {}
    for op in plan.get("placements", []):
        g = (op.get("set") or {}).get("Gyaml")
        if g is not None and op.get("twin") is None:
            final[(op.get("file"), str(op.get("hash")))] = g
    bad = [f"{s['file']} {s['hash']}: {s['to']} in the logic, {final.get((s['file'], s['hash']), s['from'])} in the "
           f"plan" for s in swapped if final.get((s["file"], s["hash"])) != s["to"]]
    for k, e in fams.items():
        if e.get("region") or not e.get("item"):
            continue
        for p in e.get("placements") or []:
            g = final.get((p["file"], str(p["hash"])))
            if g is not None and g != p["gyaml"] and _family_of(g) != k:
                bad.append(f"{p['file']} {p['hash']}: a {k} soul's placement becomes {g} in the plan")
    if bad:
        raise RuntimeError("extras_souls: the plan's enemy types aren't the ones the souls' logic was built with: "
                           + "; ".join(bad[:10]))


def finalize(plan, settings, world):
    """Runs after every plugin's plan (generate.py). Each gated enemy placement, and every twin another plugin makes of
    one (drops' respawn model), reads "its soul AND the Presence it has by then". That's the vanilla one, or the one
    an op of the plan sets (the drops plugin's checked flag on the source or the twin). A placement with no Presence
    reads the soul flag on its own. Ops it changes are edited in place and the rest comes back as a plan part. {}
    without enemy souls."""
    rec = (plan.get("_extras_souls") or {}).get("enemies") or {}
    door_rec = (plan.get("_extras_souls") or {}).get("doors") or []
    if not rec and not door_rec:
        return {}
    fams, _, swapped = seed_view(settings)  # with the enemizer's swaps, a swapped enemy reads its new family's soul
    _check_retypes(plan, fams, swapped)
    _vanilla_presence([p for r in rec.values() for p in fams[r["key"]]["placements"] if p.get("joined")])
    added = {}
    gds = plan.get("gamedata")
    for op in ([] if gds is None else [gds] if isinstance(gds, dict) else list(gds)):
        added.update({n: "BoolExp" for n in (op.get("add_boolexp") or {})})
        added.update({n: "Bool" for n in (op.get("add_bools") or {})})
    vanilla = {}
    bound = {}
    for name, r in rec.items():
        for p in fams[r["key"]]["placements"]:
            k = (p["file"], str(p["hash"]))
            bound[k] = r["flag"]
            if p.get("presence"):
                v = p["presence"]
                vanilla[k] = {"FlagName": v["flag"], "IsNegation": v["neg"], "IsCheckLazy": v["lazy"]}
    import drops as drop_tools
    exps, made = {}, {}

    def steps(pres):
        n = pres.get("FlagName", "")
        if n in added:
            return [[0 if added[n] == "Bool" else 10, n]] + ([[5]] if pres.get("IsNegation") else [])
        st = drop_tools._presence_steps(pres)
        if st is None:
            raise RuntimeError(f"extras_souls: a gated enemy's Presence {pres} names neither a Bool nor a BoolExp")
        return st

    def gate(pres, flag):
        if not pres:
            return {"FlagName": flag, "IsCheckLazy": False, "IsNegation": False}
        prog = steps(pres) + [[0, flag], [3]]
        key = json.dumps(prog)
        name = made.get(key)
        if name is None:
            name = made[key] = f"RandoEnemySoul_{len(made):03d}"
            exps[name] = prog
        return {"FlagName": name, "IsCheckLazy": bool(pres.get("IsCheckLazy")), "IsNegation": False}

    done = set()
    for op in plan.get("placements", []):
        k = (op.get("file"), str(op.get("hash")))
        if k not in bound:
            continue
        sets = op.setdefault("set", {})
        if "Presence" in sets:
            sets["Presence"] = gate(sets["Presence"], bound[k])
        elif op.get("twin"):  # a copy of the gated placement keeps its vanilla Presence unless the op sets one
            sets["Presence"] = gate(vanilla.get(k), bound[k])
        else:
            continue
        if not op.get("twin"):
            done.add(k)
    part = {"placements": [{"file": f, "hash": h, "note": "extras_souls: enemy soul",
                            "set": {"Presence": gate(vanilla.get((f, h)), flag)}}
                           for (f, h), flag in sorted(bound.items()) if (f, h) not in done]}

    def door_gate(pres, fl):
        """A room lock's Presence is its own (if any) AND each soul. It's read when the room loads, like the
        enemies'."""
        if not pres and len(fl) == 1:
            return {"FlagName": fl[0], "IsCheckLazy": False, "IsNegation": False}
        prog = (steps(pres) if pres else [[0, fl[0]]]) + [x for f in (fl if pres else fl[1:]) for x in ([0, f], [3])]
        key = json.dumps(prog)
        name = made.get(key)
        if name is None:
            name = made[key] = f"RandoEnemySoul_{len(made):03d}"
            exps[name] = prog
        return {"FlagName": name, "IsCheckLazy": bool((pres or {}).get("IsCheckLazy")), "IsNegation": False}

    taken = {(op.get("file"), str(op.get("hash"))) for op in plan.get("placements", []) if "Presence" in
             (op.get("set") or {})}
    for dr in door_rec:
        k = (dr["file"], str(dr["hash"]))
        v = dr.get("presence")
        pres = {"FlagName": v["flag"], "IsNegation": v["neg"], "IsCheckLazy": v["lazy"]} if v else None
        if k in taken:  # another plugin set this door's Presence, so AND the souls with that one
            op = next(o for o in plan["placements"] if (o.get("file"), str(o.get("hash"))) == k
                      and "Presence" in (o.get("set") or {}))
            op["set"]["Presence"] = door_gate(op["set"]["Presence"], dr["flags"])
            continue
        part["placements"].append({"file": dr["file"], "hash": dr["hash"], "set": {"Presence": door_gate(pres, dr["flags"])},
                                   "note": f"extras_souls: room lock, there only with {', '.join(dr['flags'])}"})
    if exps:
        part["gamedata"] = {"add_boolexp": exps}
    plan["_extras_souls"]["enemy_expressions"] = exps
    return part


# Read-back
def verify(patch, plan, romfs):
    """Reads the plan's soul edits back from a built patch. Each give entry has to set its flag and show its message,
    each gate's hooked step has to be reached through the gate, and the messages have to exist. Soils and platforms
    carry their expression Presence and the expressions exist in GameDataList. No borrowed flag is shared with
    another plugin."""
    from romtools import Romfs, byml_load, murmur3_32
    from evfl import Evfl
    rec = plan.get("_extras_souls") or {}
    out = []
    taken = set((plan.get("_drops_flag_spots") or {}).values())
    fa = plan.get("_fairies") or {}
    for sec in ("stones", "notes"):
        taken |= {x.get("flag") for x in (fa.get(sec) or {}).values()}
    taken |= {fa.get("scratch"), fa.get("bean_scratch")} | {x.get("flag") for x in (fa.get("beans") or {}).values()}
    npcs = json.load(open(os.path.join(HERE, "data", "rando", "extras_npcs.json"), encoding="utf-8"))["flags_claimed"]
    taken |= {v for k, v in npcs.items() if not k.startswith("_")}  # the extras_npcs plugin's claims
    mine = list(rec.get("flags", {}).values())
    clash = sorted(set(mine) & taken)
    if clash or len(mine) != len(set(mine)):
        out.append(f"extras_souls: borrowed flags used twice: {clash or mine}")
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])

    def flow(base):
        d = os.path.join(patch, "Event", "EventFlow")
        cands = sorted(f for f in os.listdir(d) if re.match(re.escape(base) + r"(\.\d{3})?\.bfevfl\.zs$", f)) \
            if os.path.isdir(d) else []
        if not cands:
            return None
        return Evfl(fs.zs.decompress(open(os.path.join(d, cands[-1]), "rb").read())).flowcharts[0]

    def steps(fc, name):
        return [e for e in fc["events"] if e["name"].startswith(name)]

    host = flow(HOST_FILE)
    for name, g in sorted((rec.get("gives") or {}).items()):
        entry = g["entry"].split(":", 1)[1]
        if host is None or entry not in host["entry_points"]:
            out.append(f"extras_souls: {name}: no entry {entry} in the patched {HOST_FILE}")
            continue
        first = host["events"][host["entry_points"][entry]["main"]]
        p = json.dumps(first.get("params"), default=str)
        if g["flag"] and g["flag"] not in p:
            out.append(f"extras_souls: {name}: {entry} doesn't set {g['flag']}")
        if g.get("display"):  # the figure held up, the hold-up steps naming SHOW_TYPE, the message
            mine = [e for e in host["events"] if e["name"].startswith(entry + "_")]
            show = [e for e in mine if json.dumps(e.get("params"), default=str).find(f'"{g["display"]}"') >= 0]
            typed = {e.get("entry_point") for e in mine if SHOW_TYPE in json.dumps(e.get("params"), default=str)}
            if not show:
                out.append(f"extras_souls: {name}: {entry} doesn't hold up {g['display']}")
            if not {"GetInEvent_SetLocator", "GetInEvent_Animation", "Item_Position"} <= typed:
                out.append(f"extras_souls: {name}: {entry}'s hold-up steps don't all read {SHOW_TYPE} ({typed})")
            if not any(e.get("entry_point") == g["message"] for e in mine):
                out.append(f"extras_souls: {name}: {entry} doesn't show its message {g['message']}")
            big = entry + "_Big"  # in a big chest (dungeons' _Big entry, shown_give) the cinematic held the figure
            if big in host["entry_points"]:  # up, so this entry sets the flag and shows the message, no second hold-up
                bs = [e for e in host["events"] if e["name"].startswith(big + "_")]
                bp = json.dumps([e.get("params") for e in bs], default=str)
                if g["flag"] not in bp or not any(e.get("entry_point") == g["message"] for e in bs):
                    out.append(f"extras_souls: {name}: {big} doesn't set {g['flag']} and show {g['message']}")
                if f'"{g["display"]}"' in bp or any(e.get("entry_point") == entry for e in bs):
                    out.append(f"extras_souls: {name}: {big} holds {g['display']} up again (the big chest's "
                               f"cinematic already did)")
        if g.get("credit"):
            allp = json.dumps([e.get("params") for e in host["events"] if e["name"].startswith(entry)], default=str)
            miss = [x for x in g["credit"] if x not in allp]
            if miss:
                out.append(f"extras_souls: {name}: {entry} doesn't credit {miss}")
    msgf = flow(MSG_FILE)
    labels = [g["message"] for g in (rec.get("gives") or {}).values()]
    labels += [g["message"].replace("_Get", "_Missing") for n, g in (rec.get("gives") or {}).items()
               if n in (rec.get("gates") or {})]
    for label in labels:
        if msgf is None or label not in msgf["entry_points"]:
            out.append(f"extras_souls: no message entry {label} in the patched {MSG_FILE}")
    # _hints_check.py reads the actual message text back along with the other text ops.
    for name, g in sorted((rec.get("gates") or {}).items()):
        fc = flow(g["file"])
        if fc is None:
            out.append(f"extras_souls: {name}: {g['file']} not in the patch")
            continue
        graph = f"Rando_Souls_{g['step']}"
        mine_steps = steps(fc, graph)
        if not mine_steps:
            out.append(f"extras_souls: {name}: no gate {graph} in {g['file']}")
            continue
        for ep, v in fc["entry_points"].items():
            first = fc["events"][v["main"]]
            if first["name"] == g["step"]:
                out.append(f"extras_souls: {name}: entry {ep} of {g['file']} still starts at {g['step']}")
        want = g.get("flag") or rec["flags"][name]  # (a regional boss gate names its region soul's flag)
        flagged = any(want in json.dumps(e.get("params"), default=str) for e in mine_steps)
        if not flagged:
            out.append(f"extras_souls: {name}: the gate in {g['file']} doesn't ask for {want}")
        if g.get("eject") and not any(g["eject"]["level"] in json.dumps(e.get("params"), default=str)
                                      for e in mine_steps):
            out.append(f"extras_souls: {name}: the gate doesn't send Link to {g['eject']['level']}")
    if rec.get("beans"):
        gd, _ = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)
        exps = {e["Hash"] for e in gd["Data"]["BoolExp"]}
        levels = {}
        for name, b in sorted(rec["beans"].items()):
            for exp in b["expressions"]:
                if murmur3_32(exp) not in exps:
                    out.append(f"extras_souls: {name}: no expression {exp} in the patched GameDataList")
            for side, exp in (("soil", f"_Soil"), ("platform", "_Plant")):
                want = next(x for x in b["expressions"] if x.endswith(exp))
                for f, h in b[side]:
                    if f not in levels:
                        levels[f] = {str(a.get("Hash")): a for a in byml_load(fs.read(f))[0].get("Actors") or []}
                    a = levels[f].get(str(h))
                    got = (a or {}).get("Presence") or {}
                    if got.get("FlagName") != want or got.get("IsNegation"):
                        out.append(f"extras_souls: {name}: {f} {h} Presence {got}, planned {want}")
    if rec.get("enemies"):
        out += _verify_enemies(rec, plan, fs)
    return out


def _verify_enemies(rec, plan, fs):
    """Reads the enemy souls back. Each soul's flag has to be a saved Bool and each expression a BoolExp of the
    patched GameDataList. Every gated placement and every twin of one has to read its soul, either the flag itself
    (not negated) or an expression ending "AND the soul" whose program is the planned one. And nothing in its level
    may refer to a gated placement: no link to it, no logic group naming it, no link of its own except to its
    anchors. That way a missing enemy can't hold anything up."""
    from romtools import byml_load, murmur3_32
    out = []
    gd, _ = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)
    bools = {e["Hash"] for e in gd["Data"]["Bool"]}
    bexps = {e["Hash"]: e for e in gd["Data"]["BoolExp"]}
    exps = rec.get("enemy_expressions") or {}
    for name, r in sorted(rec["enemies"].items()):
        if murmur3_32(r["flag"]) not in bools:
            out.append(f"extras_souls: {name}: its flag {r['flag']} is no saved Bool of the patched GameDataList")
    for exp in exps:
        if murmur3_32(exp) not in bexps:
            out.append(f"extras_souls: enemy soul expression {exp} not in the patched GameDataList")
    want = {}
    for name, r in rec["enemies"].items():
        for f, h in r["placements"]:
            want[(f, str(h))] = (name, r["flag"])
    for op in plan.get("placements", []):  # twins of a gated placement (drops' respawn model)
        k = (op.get("file"), str(op.get("hash")))
        if op.get("twin") and k in want:
            want[(k[0], str(op["twin"]))] = want[k]
    levels = {}

    def doc(f):
        if f not in levels:
            levels[f] = byml_load(fs.read(f), allow_big=True)[0] or {}
        return levels[f]

    def refs(groups, acc):  # AiGroups' References name placements by hash, as drops._inbound_refs reads them
        for g in (groups or []):
            if isinstance(g, dict):
                acc.update(str(r_.get("Reference")) for r_ in g.get("References") or [] if isinstance(r_, dict))

    files = sorted({f for f, _ in want})
    for f in files:
        d = doc(f)
        actors = d.get("Actors") or []
        byh = {str(a.get("Hash")): a for a in actors}
        named = set()
        refs(d.get("AiGroups"), named)
        linked = {str(ln.get("Dst")): a.get("Gyaml") for a in actors for ln in (a.get("Links") or [])}
        for (ff, h), (name, flag) in sorted(want.items()):
            if ff != f:
                continue
            a = byh.get(h)
            if a is None:
                out.append(f"extras_souls: {name}: placement {f} {h} missing from the patch")
                continue
            pr = a.get("Presence") or {}
            fl = pr.get("FlagName")
            if pr.get("IsNegation"):
                out.append(f"extras_souls: {name}: {f} {h} reads its soul negated ({pr})")
            elif fl == flag:
                pass
            elif fl in exps:
                prog = exps[fl]
                if prog[-2:] != [[0, flag], [3]]:
                    out.append(f"extras_souls: {name}: {f} {h} expression {fl} doesn't end in AND {flag}: {prog}")
            else:
                out.append(f"extras_souls: {name}: {f} {h} Presence {pr} doesn't read {flag}")
    # The room locks (OotrR's door edits). Each door has to read every soul gating its enemies, never negated.
    # That's the flag itself, or an expression ANDing each one after the door's own Presence when it had one. And no
    # door of a room whose enemies a soul gates may be left out (the data's doors for this seed's souls).
    for dr in rec.get("doors") or []:
        d = doc(dr["file"])
        a = next((x for x in d.get("Actors") or [] if str(x.get("Hash")) == str(dr["hash"])), None)
        if a is None:
            out.append(f"extras_souls: room lock {dr['file']} {dr['hash']} missing from the patch")
            continue
        pr = a.get("Presence") or {}
        fl = pr.get("FlagName")
        if pr.get("IsNegation"):
            out.append(f"extras_souls: room lock {dr['file']} {dr['hash']} reads its souls negated ({pr})")
        elif fl in exps:
            prog = exps[fl]
            got = {s[1] for s in prog if isinstance(s, list) and len(s) == 2 and s[0] == 0}
            if not set(dr["flags"]) <= got or any(s == [5] for s in prog[-2 * len(dr["flags"]):]):
                out.append(f"extras_souls: room lock {dr['file']} {dr['hash']} expression {fl} doesn't AND "
                           f"{dr['flags']}: {prog}")
        elif not (len(dr["flags"]) == 1 and fl == dr["flags"][0] and not dr.get("presence")):
            out.append(f"extras_souls: room lock {dr['file']} {dr['hash']} Presence {pr} doesn't read {dr['flags']}")
    out += _verify_retyped(rec, plan, doc, exps)
    return out


def _verify_retyped(rec, plan, doc, exps):
    """Every placement a plan op retypes has to read, in the patch, the soul of the type it IS there. Retyped means
    the enemizer's swaps, or any op making it an enemy or changing a soul's placement. The soul is its family's with
    "all" and its region's with "regional", or no soul for a type with none, one of the unbound or a place outside
    the soul folders. So a swapped enemy gated on its old family's soul (a Baby Dodongo on the Dodongo Soul), a Poe
    on a Guay's or a Keese in a Poe's place on none each get reported. _verify_retyped.count is the number of
    placements read."""
    from parity._enemy_souls_build import EXCLUDED_FOLDERS
    fams = enemy_data()
    flag_of = {fams[r["key"]].get("region") or r["key"]: r["flag"] for r in rec["enemies"].values()}
    regional = any(fams[r["key"]].get("region") for r in rec["enemies"].values())
    souls = set(flag_of.values())
    vanilla = {(p["file"], str(p["hash"])) for e in fams.values() if not e.get("region")
               for p in e.get("placements") or []}
    unbound = {(p["file"], str(p["hash"])) for e in fams.values() if not e.get("region")
               for p in e.get("unbound") or []}
    out, seen, byh = [], set(), {}
    for op in plan.get("placements", []):
        k = (op.get("file"), str(op.get("hash")))
        g = (op.get("set") or {}).get("Gyaml")
        if g is None or op.get("twin") is not None or k in seen or not (g.startswith("Enemy_") or k in vanilla):
            continue
        seen.add(k)
        f, h = k
        if f not in byh:
            byh[f] = {str(x.get("Hash")): x for x in doc(f).get("Actors") or []}
        a = byh[f].get(h)
        if a is None:
            out.append(f"extras_souls: retyped placement {f} {h} missing from the patch")
            continue
        g, folder = a.get("Gyaml"), f.split("/")[1]
        fam = _family_of(g)
        want = None
        if k not in unbound and f.startswith("Banc/") and folder not in EXCLUDED_FOLDERS and fam is not None:
            want = flag_of.get(folder if regional else fam)
        pr = a.get("Presence") or {}
        fl = pr.get("FlagName")
        got = ({s[1] for s in exps[fl] if isinstance(s, list) and len(s) == 2 and s[0] == 0} if fl in exps
               else {fl}) & souls
        if got != ({want} if want else set()) or (want and pr.get("IsNegation")):
            out.append(f"extras_souls: {f} {h} is {g} ({fam or 'no soul family'}) in the patch but reads "
                       f"{', '.join(sorted(got)) or 'no soul'}, not {want or 'no soul'}")
    _verify_retyped.count = len(seen)
    return out
