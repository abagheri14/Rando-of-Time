"""Parity plugin for quality-of-life and time-saver settings from Ship of Harkinian (SoH) and the 3DS randomizer
(OoT3DR) that OoTR doesn't have. Every one is a remake setting (remake_*) and off by default. With all of them
off the plugin changes nothing, no logic and no patch.

tools/rando/parity/_extras_qol_build.py reads the
game facts (scene steps, save-data rows, pack rows) from the game files into data/rando/extras_qol_data.json.
Rerun it after a game update, it stops when a fact differs. data/rando/logic/extras_qol.json describes the rule
rewrites, and this plugin applies them through OoTR's logic reader only when an option is on.
TODO: nothing here has been seen in-game yet.

Settings (value: default first):
- remake_skip_talon False | True (SoH Shuffle Weird Egg "Skip Waking Talon"): a new file starts with Talon
  already woken and back at Lon Lon Ranch. That's Goto_HyruleCastle at Step04 plus the lasting flags of the wake-up
  scene. Malon's castle egg is skipped and stays OoTR's vanilla Weird Egg, out of logic. Needs the Weird Egg and
  Chicken unshuffled.
- remake_early_grannys_shop False | True (SoH Early Granny's Shop): with shuffle_expensive_merchants and the adult
  trade unshuffled, Granny's item is in logic from the start. The remake's merchant scene already sells it the
  first time you talk to her, but OoTR's rule waited for the Odd Mushroom.
- remake_full_wallets False | True (SoH Full Wallets): every wallet comes full and a new file starts with a full
  wallet. It's IsItemStockMax on the capacity rows, the same flag the quivers and bags already use.
- remake_frog_song_timer 1 | 2 | 3 | 4 (OoT3DR Frog Song Timer): the frogs' final song gives this many times the
  seconds per note.
- remake_skip_song_replays False | True (OoT3DR Skip Song Replays): after you play a song, the wait for its
  replay is cut down to a moment before the song takes effect. The tune itself still plays.
- remake_slingshot_beehives False | True (SoH Slingshot/Bow Break Beehives): the Slingshot breaks beehives (the Bow
  already does in the remake), in logic too.
- remake_damage_multiplier "normal" | "x8" | "x16" (SoH / OoT3DR Damage Multiplier x8 and x16, beyond OoTR's
  values): the player's damage rates, set the way OoTR's damage_multiplier sets them. Logic treats both as
  one-hit KO.
- remake_skip_pickup_text False | True (SoH Skip Pickup Messages, OOTRR's every-pickup follow-up): no "You got a
  Green Rupee!" window the first time you pick up a rupee, a recovery heart, a magic jar, arrows, Deku Seeds, Deku
  Nuts, Deku Sticks, bombs or bombchus. A new file starts with their window already seen
  (HavePlayedGetEvent.<item>, keyed by the item the pickup gives), which is what every later pickup checks. The
  first nut and stick are also what hand out their small bags, so a new file starts with those bags, empty, unless
  the bags are shuffled (extras_items) or the starting items already give one.
- remake_faster_blocks False | True (SoH Faster Block Push): push blocks move twice as fast. Each one's move curve
  (frame -> share of one push) runs in half the frames, so a block still stops on the same spots.
- remake_dpad_gear "off" | "hold" | "wheel" | "wheel_tunics" (OOTRR D-pad gear switching, and the remake's own
  unfinished gear wheels):
  "hold": holding D-pad up switches to the next accessory you have (Lens of Truth, masks, amiibo masks) and D-pad down
  swaps the Hover and Iron Boots, without pausing (parity/_extras_dpad.py); a tap still puts the gear on or takes it
  off. "wheel": holding them opens the game's item wheel on your accessories or boots, with their icons, and letting
  go puts the pick on the way the Equipment menu does; a tap puts the gear on or takes it off when you let go, so a
  hold never toggles it. That one is a code patch too, so the game has to be built again in Longshot
  (parity/_extras_wheel.py), and the gear's pouch rows get their item kinds (the wheel's icons). "wheel_tunics": the
  wheels, plus holding D-pad left opens one on the adult's tunics (once you have the Goron or Zora tunic); D-pad left
  is the ocarina's, so a tap there plays it when you let go. No gear slot greys out in water.
- remake_navi_return "off" | "dungeons" | "everywhere" (OOTRR Return with Navi): D-pad right asks Navi for a trip back,
  the way the N64 game's save and quit did: to a dungeon's entrance, and with "everywhere" also home from the overworld
  (Kokiri Forest as a child, the Temple of Time as an adult). The details are in parity/_extras_navi.py.
- remake_skip_movies False | True (OOTRR skippable cutscenes): the opening movie (Dm_Kokiri_0000) and the first credits
  movie (Dm_StaffCredit_0005) can be skipped like every other cutscene. They're the only two story scenes whose
  scene settings name the game's DisableSkip component (the third is a title screen demo, left alone), so their
  lists lose that one entry.
"""
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))

DATA_PATH = os.path.join(HERE, "data", "rando", "extras_qol_data.json")
LOGIC_PATH = os.path.join(HERE, "data", "rando", "logic", "extras_qol.json")
_data = _logic = None

OWNS = {}
REMAKE_SETTINGS = {
    "remake_skip_talon": (False, True),
    "remake_early_grannys_shop": (False, True),
    "remake_full_wallets": (False, True),
    "remake_frog_song_timer": (1, 2, 3, 4),
    "remake_skip_song_replays": (False, True),
    "remake_slingshot_beehives": (False, True),
    "remake_damage_multiplier": ("normal", "x8", "x16"),
    "remake_skip_pickup_text": (False, True),
    "remake_faster_blocks": (False, True),
    "remake_dpad_gear": ("off", "hold", "wheel", "wheel_tunics"),
    "remake_navi_return": ("off", "dungeons", "everywhere"),
    "remake_skip_movies": (False, True),
}
REMAKE_DEFAULTS = {"remake_skip_talon": False, "remake_early_grannys_shop": False, "remake_full_wallets": False,
                   "remake_frog_song_timer": 1, "remake_skip_song_replays": False,
                   "remake_slingshot_beehives": False, "remake_damage_multiplier": "normal",
                   "remake_skip_pickup_text": False, "remake_faster_blocks": False, "remake_dpad_gear": "off",
                   "remake_navi_return": "off", "remake_skip_movies": False}
DAMAGE = {"x8": 8.0, "x16": 16.0}
REPLAY_FRAMES = 10  # what's left of each song's replay wait: a moment before the song takes effect
TALON_EXP = "Goto_HyruleCastle_IsAfter_Step03_02_Exp"  # Step04 or later: Talon woken
POUCH_INFO = "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"
SKIP_LOCK = "SkipSetting"  # the component naming DisableSkip.engine__event__SkipSetting.bgyml (IsDisableSkip true)
SKIP_LOCK_FILE = "Event/EventSetting/EventSettingComponent/SkipSetting/DisableSkip.engine__event__SkipSetting.bgyml"
LOCKED_MOVIES = tuple(f"Event/EventSetting/EventSettingComponentList/{m}.engine__event__EventSettingComponentList.bgyml"
                      for m in ("Dm_Kokiri_0000", "Dm_StaffCredit_0005"))
GRANNY = "Kak Granny Buy Blue Potion"


def data():
    global _data
    if _data is None:
        _data = json.load(open(DATA_PATH, encoding="utf-8"))
    return _data


def logic():
    global _logic
    if _logic is None:
        _logic = json.load(open(LOGIC_PATH, encoding="utf-8"))["options"]
    return _logic


def value(settings, key):
    return (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS[key])


def active(settings):
    """{setting: value} of the options that are on."""
    return {k: value(settings, k) for k in REMAKE_SETTINGS if value(settings, k) != REMAKE_DEFAULTS[k]}


def claimed_rows(world):
    """Scene IDs (config/scene_rows.json) this seed takes for itself: Navi's return scene. parity/chests.py budgets
    the rows."""
    if value(getattr(world, "settings", None), "remake_navi_return") == "off":
        return []
    from parity import _extras_navi
    return [_extras_navi.ROW]


def _child_trade(settings):
    return set(getattr(settings, "shuffle_child_trade", None) or ())


def _skip_child_zelda(settings):
    starting = getattr(settings, "starting_items", None) or {}
    return "Zeldas Letter" in starting


def talon_on(settings):
    """remake_skip_talon, unless skip child Zelda already wakes Talon (story plugin)."""
    return bool(value(settings, "remake_skip_talon")) and not _skip_child_zelda(settings)


def granny_on(settings):
    """remake_early_grannys_shop, only where it changes anything (Granny's item shuffled, the adult trade not)."""
    return (bool(value(settings, "remake_early_grannys_shop"))
            and bool(getattr(settings, "shuffle_expensive_merchants", False))
            and not getattr(settings, "adult_trade_shuffle", False))


# Settings
def check_settings(settings):
    out = []
    remake = getattr(settings, "remake", None) or {}
    for k, v in remake.items():
        if k in REMAKE_SETTINGS:
            ok = REMAKE_SETTINGS[k]
            if v not in ok or isinstance(v, bool) != isinstance(ok[0], bool):
                out.append(f"{k} = {v!r}: extras_qol can make {', '.join(map(repr, ok))}")
            continue
        near = difflib.get_close_matches(k, list(REMAKE_SETTINGS), n=1, cutoff=0.85)
        if near:
            out.append(f"{k}: unknown remake setting; did you mean {near[0]}?")
    if remake.get("remake_skip_talon") is True and _child_trade(settings) & {"Weird Egg", "Chicken"}:
        out.append("remake_skip_talon with a shuffled Weird Egg or Chicken: Talon starts awake, so Malon's castle egg "
                   "(and its check) is skipped; Ship of Harkinian's Skip Waking Talon is a third Weird Egg value, "
                   "not shuffled")
    if remake.get("remake_damage_multiplier", "normal") != "normal" and \
            getattr(settings, "damage_multiplier", "normal") != "normal":
        out.append(f"remake_damage_multiplier {remake['remake_damage_multiplier']} with OoTR's damage_multiplier "
                   f"{settings.damage_multiplier!r}: use one of the two (both set the player's damage rates)")
    return out


def untested(settings):
    out = []
    for k, v in active(settings).items():
        if k == "remake_skip_talon" and not talon_on(settings):
            out.append("extras_qol: remake_skip_talon has no effect (skip child Zelda already wakes Talon)")
        elif k == "remake_early_grannys_shop" and not granny_on(settings):
            out.append("extras_qol: remake_early_grannys_shop has no effect (it needs shuffle_expensive_merchants on "
                       "and adult_trade_shuffle off, as in Ship of Harkinian)")
        else:
            out.append(f"extras_qol: {k} = {v!r}")
    return out


# Logic (through OoTR's logic reader)
_state = {"talon": False, "granny": False, "sling": False, "ohko": False, "hits": {}}
RX_TALON = re.compile(r"at\('Hyrule Castle Grounds',\s*is_child and \(Weird_Egg or Chicken\)\)")
RX_OHKO = re.compile(r"damage_multiplier\s*!=\s*'ohko'")


def _rewrite_rule(where, name, rule):
    """One region rule string with the options' rewrites (data/rando/logic/extras_qol.json)."""
    hits = _state["hits"]
    if _state["talon"]:
        spec = logic()["remake_skip_talon=true"]
        if name in spec["set"]:
            hits[name] = True
            return spec["set"][name]
        new, n = RX_TALON.subn("True", rule)
        if n:
            hits[name] = True
            rule = new
        if rule.strip() == spec["egg_or_chicken"]:
            hits[name] = True
            rule = "True"
    if _state["granny"] and name == GRANNY and "'Odd Potion Access'" in rule:
        hits[name] = True
        rule = logic()["remake_early_grannys_shop=true"]["set"][GRANNY]
    if _state["ohko"]:
        rule, n = RX_OHKO.subn("False", rule)
        if n:
            hits[name] = True
    return rule


def _rewrite(path, data):
    base = os.path.basename(path)
    if base == "LogicHelpers.json" and isinstance(data, dict):
        data = dict(data)
        if _state["sling"]:
            for k, extra in logic()["remake_slingshot_beehives=true"]["or_helpers"].items():
                if k not in data:
                    raise RuntimeError(f"extras_qol: no helper {k} (OoTR's or the remake's logic changed)")
                data[k] = f"({data[k]}) or {extra}"
                _state["hits"][k] = True
        if _state["ohko"]:
            for k, v in list(data.items()):
                if isinstance(v, str) and RX_OHKO.search(v):
                    data[k] = RX_OHKO.sub("False", v)
                    _state["hits"][k] = True
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict) and "region_name" in data[0]:
        out = []
        for region in data:
            region = dict(region)
            for section in ("locations", "exits", "events"):
                if isinstance(region.get(section), dict):
                    region[section] = {n: (_rewrite_rule(region["region_name"], n, r) if isinstance(r, str) else r)
                                       for n, r in region[section].items()}
            out.append(region)
        return out
    return data


def _install_reader():
    import RuleParser
    import Utils
    import World
    if getattr(Utils.read_logic_file, "remake_extras_qol", False):
        return
    inner = Utils.read_logic_file

    def read(path):
        d = inner(path)
        if any(_state[k] for k in ("talon", "granny", "sling", "ohko")):
            d = _rewrite(path, d)
        return d
    read.remake = True
    read.remake_extras_qol = True
    for module in (Utils, RuleParser, World):
        module.read_logic_file = read


def before_build(settings):
    """Sets up the logic rewrites of the options that are on, applied as OoTR's logic reader reads the files. The
    reader hook is installed once and reads the state of the seed being built. With every option off nothing gets
    installed."""
    _state.update(talon=talon_on(settings), granny=granny_on(settings),
                  sling=bool(value(settings, "remake_slingshot_beehives")),
                  ohko=value(settings, "remake_damage_multiplier") != "normal", hits={})
    if any(_state[k] for k in ("talon", "granny", "sling", "ohko")):
        _install_reader()
        import RuleParser
        RuleParser.rule_aliases.clear()  # helpers reload through the rewrite on the next parse
        RuleParser.nonaliases.clear()


def keep_locations(world, settings):
    """Check that every rewrite found its rule (OoTR's or the remake's logic may have moved it)."""
    hits = _state["hits"]
    need = []
    if _state["talon"]:
        need += logic()["remake_skip_talon=true"]["must_hit"]
    if _state["granny"]:
        need.append(GRANNY)
    if _state["sling"]:
        need += list(logic()["remake_slingshot_beehives=true"]["or_helpers"])
    if _state["ohko"]:
        need.append("can_take_damage")
    missing = [n for n in need if n not in hits]
    if missing:
        raise RuntimeError(f"extras_qol: no rule to rewrite for {', '.join(missing)} (OoTR's or the remake's logic "
                           f"changed)")
    return set()


# Patch plan
def _guard_ops(file, flowchart, event, info):
    """Skip a castle-story step that would set Goto_HyruleCastle back before Step04 while it is at Step04 or later."""
    graph = f"Rando_Qol_{event}"
    after = f"@{info['next']}" if info["next"] else None
    ops = [{"file": file, "flowchart": flowchart, "add_graph": graph, "start": "g", "nodes": {
        "g": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp", "params": {"GameDataName": TALON_EXP},
              "cases": {0: after, 1: f"@{event}"}}}}]
    for kind, where, k in info["preds"]:
        op = {"file": file, "flowchart": flowchart, "next": f"{graph}_g"}
        if kind == "entry":
            op["entry"] = where
        else:
            op["event"] = where
            if kind in ("case", "fork"):
                op[kind] = k
        ops.append(op)
    return ops


BAG_SHUFFLE = {"DekuNut": "remake_shuffle_deku_nut_bag", "DekuStick": "remake_shuffle_deku_stick_bag"}


def pickup_bag_kept(settings, world, bag):
    """Why remake_skip_pickup_text doesn't hand out this small bag at the start, or "". With the first-get window
    already seen, the first nut or stick no longer brings its bag, so a new file gets the bag empty instead. Not
    when the bag is a shuffled item of its own (extras_items), or when the starting items already give a bag of
    that kind."""
    if (getattr(settings, "remake", None) or {}).get(BAG_SHUFFLE.get(bag["kind"])):
        return f"{BAG_SHUFFLE[bag['kind']]}: the bag is an item to find"
    import world_settings
    family = bag["bag"].rsplit("_", 1)[0] + "_"
    started = sorted(a for a in world_settings.starting_actors(settings, world) if a.startswith(family))
    return f"the starting items give {', '.join(started)}" if started else ""


def world_plan(settings, world):
    on = active(settings)
    if not on:
        return {}
    d = data()
    events, packs, defaults, notes = [], [], {}, []
    readback = {"params": [], "graphs": [], "packs": [], "defaults": {}}

    if talon_on(settings):
        t = d["talon"]
        for event, info in sorted(t["steps"].items()):
            events += _guard_ops("Goto_HyruleCastle", t["flowchart"], event, info)
            readback["graphs"].append(["Goto_HyruleCastle", t["flowchart"], f"Rando_Qol_{event}", info["preds"]])
        defaults.update({"Step_Goto_HyruleCastle": "Step04", "Talon_AfterWakeUp": True,
                         "HavePlayedEvent.Dm_HrlCastle_0020": True})
        notes.append("remake_skip_talon: Talon starts awake at the ranch (Goto_HyruleCastle Step04); HC Malon Egg "
                     "is skipped (its vanilla Weird Egg is out of logic)")

    if granny_on(settings):
        notes.append(f"remake_early_grannys_shop: {GRANNY} needs only a wallet (the merchant scene sells it from "
                     f"Granny's first talk)")

    if value(settings, "remake_full_wallets"):
        for w in d["packs"]["wallets"]:
            packs.append({"pack": w["pack"], "file": w["file"], "set": {"IsItemStockMax": True},
                          "note": "remake_full_wallets"})
            readback["packs"].append([w["pack"], w["file"], "IsItemStockMax", True])
        child_wallet = bool((getattr(settings, "remake", None) or {}).get("remake_shuffle_child_wallet", False))
        start = next(w["MaxNum"] for w in d["packs"]["wallets"] if w["pack"].endswith("/Pouch_Wallet_Small.pack.zs"))
        if not child_wallet and not getattr(settings, "start_with_rupees", False):
            defaults["PlayerStatus.CurrentRupee"] = start  # the starting wallet's capacity row (MaxNum)
        notes.append("remake_full_wallets: every wallet's capacity row fills the wallet (IsItemStockMax)"
                     + ("" if child_wallet or getattr(settings, "start_with_rupees", False)
                        else f"; a new file starts with {start} rupees"))

    n = value(settings, "remake_frog_song_timer")
    if n != 1:
        f = d["frogs"]
        for event, p in sorted(f["steps"].items()):
            for k in ("PlayableSeconds", "FirstPlayableSeconds"):
                v = round(p[k] * n, 4)
                events.append({"file": "MiniGame_FrogTenors", "flowchart": f["flowchart"], "event": event,
                               "param": k, "value": v})
                readback["params"].append(["MiniGame_FrogTenors", f["flowchart"], event, k, v])
        notes.append(f"remake_frog_song_timer: the frogs' songs give {n}x the seconds per note")

    if value(settings, "remake_skip_song_replays"):
        r = d["replays"]
        for event in sorted(r["waits"], key=lambda x: int(x[5:])):
            events.append({"file": "Dm_SY_Ocarina", "flowchart": r["flowchart"], "event": event, "param": "Frames",
                           "value": REPLAY_FRAMES})
            readback["params"].append(["Dm_SY_Ocarina", r["flowchart"], event, "Frames", REPLAY_FRAMES])
        notes.append(f"remake_skip_song_replays: {len(r['waits'])} replay waits cut to {REPLAY_FRAMES} frames")

    if value(settings, "remake_slingshot_beehives"):
        b = d["packs"]["beehive"]
        key = f"ExternalDamageParameters.DamageRates.{b['key']}"
        packs.append({"pack": b["pack"], "file": b["file"], "set": {key: 1.0}, "note": "remake_slingshot_beehives"})
        readback["packs"].append([b["pack"], b["file"], key, 1.0])
        notes.append("remake_slingshot_beehives: the Slingshot breaks beehives (SlingshotBullet damage rate 1)")

    m = value(settings, "remake_damage_multiplier")
    if m != "normal":
        for p in d["packs"]["player"]:
            sets = {f"ExternalDamageParameters.DamageRates.{k}": v * DAMAGE[m] for k, v in p["rates"].items()}
            packs.append({"pack": p["pack"], "file": p["file"], "set": sets, "note": "remake_damage_multiplier"})
            readback["packs"] += [[p["pack"], p["file"], k, v] for k, v in sorted(sets.items())]
        notes.append(f"remake_damage_multiplier {m}: the player's damage rates x{DAMAGE[m]:g}")

    if value(settings, "remake_skip_pickup_text"):
        pt = d["pickup_text"]
        for name in pt["flags"]:
            defaults[name] = True
        notes.append(f"remake_skip_pickup_text: {len(pt['flags'])} pickup windows start already seen")
        for bag in pt["bags"]:
            why = pickup_bag_kept(settings, world, bag)
            if why:
                notes.append(f"remake_skip_pickup_text: no empty {bag['bag']} at the start ({why})")
                continue
            got, count, size, current = bag["rows"]
            defaults.update({got: True, count: 1, size: bag["max"], current: bag["bag"]})
            notes.append(f"remake_skip_pickup_text: a new file has an empty {bag['bag']} ({bag['max']}), the bag "
                         f"the first {bag['item']} would have given")

    if value(settings, "remake_faster_blocks"):
        for blk in d["blocks"]:
            speed = faster(blk["MoveSpeed"])
            packs.append({"pack": blk["packs"], "file": blk["file"], "set": {"MoveSpeed": speed},
                          "note": "remake_faster_blocks"})
            readback["packs"] += [[pk, blk["file"], "MoveSpeed", speed] for pk in blk["packs"]]
        notes.append(f"remake_faster_blocks: {len(d['blocks'])} push-block curves run in half the frames")

    gamedata, ainb, exefs, byml, text = {}, [], [], [], []
    if value(settings, "remake_navi_return") != "off":
        from parity import _extras_navi
        import romtools
        romfs = os.environ.get("REMAKE_ROMFS") or romtools.longshot_romfs()
        if os.path.isdir(romfs):  # the read-back checks it again where the patch is built
            bad = _extras_navi.check_sources(romfs)
            if bad:
                raise RuntimeError("remake_navi_return: the game files aren't as expected: " + "; ".join(bad[:3]))
        sections, readback["navi"] = _extras_navi.plan(value(settings, "remake_navi_return"))
        events += sections["events"]
        byml += sections["byml"]
        ainb += sections["ainb"]
        text += sections["text"]
        notes.append(f"remake_navi_return {value(settings, 'remake_navi_return')}: D-pad right asks Navi for a trip "
                     f"back (scene {_extras_navi.FLOW}:{_extras_navi.ENTRY} on scene ID {_extras_navi.ROW}; Navi's area "
                     f"tutorial hints are replaced by it)")
    if value(settings, "remake_dpad_gear") != "off":
        from parity import _extras_dpad
        wheel = value(settings, "remake_dpad_gear") in ("wheel", "wheel_tunics")
        tunics = value(settings, "remake_dpad_gear") == "wheel_tunics"
        if wheel:
            from parity import _extras_wheel
            # the game's code here, when Longshot is on this PC (the read-back checks it again where the patch is
            # built: in_game_check runs on the player's own game)
            bad = _extras_wheel.check_here(tunics)
            if bad:
                raise RuntimeError("D-pad gear wheels: the code patch doesn't fit this game: " + "; ".join(bad[:3]))
            exefs.append({"file": _extras_wheel.PATCH_FILE, "text": _extras_wheel.pchtxt(tunics)})
            # the gear's item kinds, which the wheel draws their icons from (_extras_qol_build.gear_kinds)
            kinds = dict(d["dpad"]["kinds"], **(d["dpad"]["tunic_kinds"] if tunics else {}))
            byml.append({"file": POUCH_INFO, "set": {f"[__RowId={a}].AssignableItem": k for a, k in kinds.items()}})
            readback["kinds"] = kinds
        sections, readback["dpad"] = _extras_dpad.plan(d["dpad"], settings, wheel=wheel, tunics=tunics)
        gamedata.update(sections["gamedata"])
        ainb += sections["ainb"]
        aside = readback["dpad"]["flags"]
        if tunics:
            notes.append("remake_dpad_gear wheel_tunics: holding D-pad left opens the wheel on the adult's tunics; a tap "
                         "plays the ocarina when you let go")
        if wheel:
            notes.append("remake_dpad_gear wheel: holding D-pad up or down opens the item wheel on the accessories or "
                         "boots; the code patch (exefs) needs the game built again in Longshot")
        else:
            notes.append(f"remake_dpad_gear: hold D-pad up for the next of {len(d['dpad']['gear']['head'])} "
                         f"accessories, down for the next of {len(d['dpad']['gear']['boots'])} boots"
                         + (f"; the mask picker's {len(aside)} put-aside masks count too" if aside else ""))

    if value(settings, "remake_skip_movies"):
        byml += [{"file": f, "delete_keys": [f"Components.{SKIP_LOCK}"], "note": "remake_skip_movies"}
                 for f in LOCKED_MOVIES]
        readback["movies"] = list(LOCKED_MOVIES)
        notes.append("remake_skip_movies: the opening movie and the first credits movie can be skipped")

    plan = {}
    if events:
        plan["events"] = events
    if packs:
        plan["packs"] = packs
    if defaults:
        gamedata["defaults"] = defaults
        readback["defaults"] = defaults
    if gamedata:
        plan["gamedata"] = gamedata
    if ainb:
        plan["ainb"] = ainb
    if exefs:
        plan["exefs"] = exefs
    if byml:
        plan["byml"] = byml
    if text:
        plan["text"] = text
    if notes:
        plan["_notes_extras_qol"] = notes
    if events or packs or gamedata or ainb or byml or readback.get("navi"):
        plan["_extras_qol"] = readback
        plan["_verify_plugins"] = ["extras_qol"]
    return plan


def faster(speed):
    """A push block's move curve in half the frames. The points are (frame, share of one push, slope in, slope out),
    so the frames halve and the slopes double, and the shares (where the block is) stay. Halving and doubling are exact
    in the file's 32-bit floats."""
    data = list(speed["Data"])
    for i in range(0, len(data), 4):
        data[i] /= 2
        data[i + 2] *= 2
        data[i + 3] *= 2
    return dict(speed, MaxX=speed["MaxX"] / 2, Data=data)


# Read-back (tools/rando/in_game_check.py)
def verify(patch, plan, romfs):
    """Reads the planned edits back from a built patch and returns [problem, ...]. It checks event parameters, the
    castle guards (each predecessor now leads into its guard, which tests the expression), pack rows and new-file
    defaults."""
    from romtools import Romfs, byml_load, murmur3_32, sarc_files
    from evfl import Evfl
    from parity._story_build import newest, flat
    rb = plan.get("_extras_qol") or {}
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    flows = {}

    def fc_of(file, flowchart):
        if file not in flows:
            rel, _ = newest(romfs, file)
            if not os.path.exists(os.path.join(patch, rel)):
                bad.append(f"{file}: not in the patch")
                flows[file] = None
            else:
                flows[file] = {f["name"]: f for f in Evfl(fs.read(rel)).flowcharts}
        return (flows[file] or {}).get(flowchart)

    for file, flowchart, event, param, want in rb.get("params", []):
        fc = fc_of(file, flowchart)
        e = next((x for x in (fc or {}).get("events", []) if x["name"] == event), None)
        got = flat(e.get("params"), {}).get(param) if e else None
        if got is None or (abs(got - want) > 1e-3 if isinstance(want, float) else got != want):
            bad.append(f"{file} {event} {param} = {got!r}, planned {want!r}")
    for file, flowchart, graph, preds in rb.get("graphs", []):
        fc = fc_of(file, flowchart)
        if fc is None:
            continue
        names = {e["name"]: e for e in fc["events"]}
        start = names.get(f"{graph}_g")
        if start is None or flat(start.get("params"), {}).get("GameDataName") != TALON_EXP:
            bad.append(f"{file}: guard {graph} missing or not testing {TALON_EXP}")
            continue
        for kind, where, _ in preds:
            if kind == "entry":
                ep = fc["entry_points"].get(where)
                target = fc["events"][ep["main"]]["name"] if ep else None
            else:
                e = names.get(where)
                nx = [c["next"] for c in e.get("cases", [])] if e and "cases" in e else [e.get("next")] if e else []
                target = next((fc["events"][i]["name"] for i in nx if i is not None and i < len(fc["events"])
                               and fc["events"][i]["name"] == f"{graph}_g"), None)
            if target != f"{graph}_g":
                bad.append(f"{file}: {where} does not lead into {graph}")
    by_pack = {}
    for pack, file, key, want in rb.get("packs", []):
        if (pack, file) not in by_pack:
            if not os.path.exists(os.path.join(patch, pack)):
                bad.append(f"{pack}: not in the patch")
                by_pack[(pack, file)] = None
            else:
                by_pack[(pack, file)] = byml_load(sarc_files(fs.read(pack))[file])[0]
        cur = by_pack[(pack, file)]
        if cur is None:
            continue
        for part in key.split("."):
            if isinstance(cur, dict):
                cur = cur.get(int(part)) if part.isdigit() and int(part) in cur else cur.get(part)
            else:
                cur = None
        if cur != want:
            bad.append(f"{pack} {file} {key} = {cur!r}, planned {want!r}")
    if rb.get("defaults"):
        gd, _ = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)
        index = {e["Hash"]: (t, e) for t, rows in gd["Data"].items() if t != "Bool64bitKey" for e in rows}
        for name, want in rb["defaults"].items():
            t, e = index.get(murmur3_32(name), (None, {}))
            w = murmur3_32(want) if t == "Enum" else want
            if e.get("DefaultValue") != w:
                bad.append(f"save data {name} default = {e.get('DefaultValue')!r}, planned {want!r}")
    if rb.get("kinds"):
        rows = {r["__RowId"]: r for r in byml_load(fs.read(POUCH_INFO), allow_big=True)[0]}
        for a, k in rb["kinds"].items():
            if (rows.get(a) or {}).get("AssignableItem") != k:
                bad.append(f"{POUCH_INFO}: {a} names {(rows.get(a) or {}).get('AssignableItem')!r}, planned {k}")
        for a, r in rows.items():
            if r.get("AssignableItem") in rb["kinds"].values() and a not in rb["kinds"]:
                bad.append(f"{POUCH_INFO}: {a} names {r['AssignableItem']} too")
    if rb.get("navi"):
        from parity import _extras_navi
        bad += _extras_navi.verify(patch, rb["navi"], romfs)
    if rb.get("dpad"):
        from parity import _extras_dpad
        bad += _extras_dpad.verify(patch, rb["dpad"], romfs, data()["dpad"])
    for f in rb.get("movies", []):
        if not os.path.exists(os.path.join(patch, f)):
            bad.append(f"{f}: not in the patch")
        elif SKIP_LOCK in (byml_load(fs.read(f) if f.endswith(".zs") else fs.raw(f))[0].get("Components") or {}):
            bad.append(f"{f}: still names {SKIP_LOCK}")
    return bad
