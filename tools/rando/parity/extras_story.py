"""Parity plugin for story and time-saver extras from Ship of Harkinian (SoH) and the 3DS randomizer (OoT3DR) that
OoTR doesn't have. Every one is a remake setting (remake_*) and off by default. With all of them off the plugin
changes nothing, no logic and no patch.

tools/rando/parity/_extras_story_build.py reads
the game facts the plugin relies on (scene steps, flags, placements, level-logic words) from the game files into
data/rando/extras_story_data.json. Rerun it after a game update. The logic is data/rando/logic/extras_story.json,
which this plugin applies to the built world when an option is on.
TODO: nothing here has been seen in-game yet.

Settings (value: default first):
- remake_sleeping_waterfall "closed" | "open" (SoH Sleeping Waterfall): the waterfall to Zora's Domain is open
  from the start of a new file. It sets Zorariver_TheWaterfallsplits, the waterfall door's only input, as a
  new-file default.
- remake_skip_four_poes False | True (OoT3DR Four Poes Cutscene): entering the Forest Temple main hall the first
  time gives you the cutscene's lasting effects (elevator flag, SageOfForest Step06, played flag) without the
  cutscene.
- remake_skip_lake_owl False | True (OoT3DR Lake Hylia Owl): the owl's flight scene (Dm_LakeHrl_0010) is skipped.
  Saying yes to the flight goes straight to the landing scene, or to the owl's shuffled destination.
- remake_skip_area_intros False | True (OOTRR Skip Area Intros): the first-visit scenes that only show a place
  (25 of them: villages, fields' neighbours, dungeon doorways) don't play. Where nothing else hangs on them, a new
  file starts with them played, and their places show their name (and count as visited) when you arrive. Where their arrival scene does more after the intro (a quest
  step, Navi), only the intro step changes: it plays the plain arrival and marks the intro played and the place
  visited, and the rest runs as before. Intros that move a quest themselves keep playing. See
  _extras_story_build.py INTRO_NEW_FILE / INTRO_EDITS.
- remake_jabu_mouth "closed" | "open" (SoH/OoT3DR Jabu-Jabu Open): Jabu-Jabu opens his mouth for a child who
  reaches him (a level-logic word patch) and the mouth's doorway plays the first-arrival scene. No fish needed.
- remake_medallion_trials False | True (SoH Medallion-Locked Trials): each trial's barrier room only opens if you
  have its medallion (the doors' own scenes check IsGet.Item_Medal_*).
- remake_ganons_soul "off" | "stones" | "medallions" | "dungeons" | "tokens" | "hearts", remake_ganons_soul_count
  (SoH Ganon's Soul, trigger variants): the door to Ganondorf (whose scene starts the fight) only opens once you
  have the count, counted on the items the same way the story plugin's bridge is.
- remake_king_zora_speed "vanilla" | "fast" (OoT3DR King Zora Speed): King Zora's 1500-frame shuffle (Dm_Zora_0010
  C10) is cut and his robe turns walkable at once, which is how every later visit has it anyway.
- remake_racing False | True (OoT3DR Racing): personal options that change how long scenes take (fanfares, song
  playbacks) are locked to the game's values, so every racer's patch plays the same.
"""
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
from parity import _story_conditions as C  # noqa: E402

DATA_PATH = os.path.join(HERE, "data", "rando", "extras_story_data.json")
LOGIC_PATH = os.path.join(HERE, "data", "rando", "logic", "extras_story.json")
_data = _logic = None

OWNS = {}  # before_build reads the cosmetics plugin's fanfare settings for racing mode.
SOUL_KINDS = ("off", "stones", "medallions", "dungeons", "tokens", "hearts")
SOUL_RANGE = {"stones": (1, 3), "medallions": (1, 6), "dungeons": (1, 9), "tokens": (1, 100), "hearts": (4, 20)}
REMAKE_SETTINGS = {
    "remake_sleeping_waterfall": ("closed", "open"),
    "remake_skip_four_poes": (False, True),
    "remake_skip_lake_owl": (False, True),
    "remake_skip_area_intros": (False, True),
    "remake_jabu_mouth": ("closed", "open"),
    "remake_medallion_trials": (False, True),
    "remake_ganons_soul": SOUL_KINDS,
    "remake_ganons_soul_count": None,  # checked in check_settings (SOUL_RANGE), default / 0 means the kind's maximum
    "remake_king_zora_speed": ("vanilla", "fast"),
    "remake_racing": (False, True),
}
REMAKE_DEFAULTS = {"remake_sleeping_waterfall": "closed", "remake_skip_four_poes": False,
                   "remake_skip_lake_owl": False, "remake_skip_area_intros": False, "remake_jabu_mouth": "closed",
                   "remake_medallion_trials": False,
                   "remake_ganons_soul": "off", "remake_ganons_soul_count": None,
                   "remake_king_zora_speed": "vanilla", "remake_racing": False}
# remake_racing locks these personal (cosmetic, unshared) OoTR settings because their value changes how long a
# scene runs. Item-get and song scenes wait for their fanfare to end, so 'off'
# (silence) and 'random' (other lengths) would make some racers' gets shorter or longer. OoT3DR's Racing overrides
# QuickText, ColoredKeys and ColoredBossKeys the same way (source/settings.cpp racingOverrides). The remake's text
# speed is the game's own option, and key colours are seed settings here.
RACING_LOCKS = {"fanfares": "normal", "ocarina_fanfares": False}

TRIALS = ("Forest", "Fire", "Water", "Shadow", "Spirit", "Light")
# The scene each trial's barrier-room door plays (InsideGanonCastle_CommonGimmick) and its first step. The Light
# trial's door gets the Fire trial's scene, because its own is the default door scene that every door shares, and
# we tell it apart by a named anchor at that door.
TRIAL_DOOR_STEP = {"Forest": "Event138", "Water": "Event141", "Fire": "Event144", "Shadow": "Event164",
                   "Spirit": "Event167"}
LIGHT_HOST = "Fire"
TEXT_FILE = "EventFlowMsg/Item_Event.msbt"
SOUL_WORDS = {"stones": ("Spiritual Stone", "Spiritual Stones"), "medallions": ("Medallion", "Medallions"),
              "dungeons": ("Spiritual Stone or Medallion", "Spiritual Stones and Medallions"),
              "tokens": ("Gold Skulltula Token", "Gold Skulltula Tokens"), "hearts": ("heart", "hearts")}


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
    v = (getattr(settings, "remake", None) or {}).get(key, REMAKE_DEFAULTS[key])
    return None if key == "remake_ganons_soul_count" and v == 0 and not isinstance(v, bool) else v  # 0: all


def soul(settings):
    """(kind, count) of remake_ganons_soul, or None when off."""
    kind = value(settings, "remake_ganons_soul")
    if kind == "off":
        return None
    n = value(settings, "remake_ganons_soul_count")
    return kind, SOUL_RANGE[kind][1] if n is None else n


def active(settings):
    """{setting: value} of the options that are on."""
    return {k: value(settings, k) for k in REMAKE_SETTINGS if value(settings, k) != REMAKE_DEFAULTS[k]}


# Settings
def check_settings(settings):
    out = []
    remake = getattr(settings, "remake", None) or {}
    for k, v in remake.items():
        if k in REMAKE_SETTINGS:
            ok = REMAKE_SETTINGS[k]
            if ok is not None and (v not in ok or isinstance(v, bool) != isinstance(ok[0], bool)):
                out.append(f"{k} = {v!r}: extras_story can make {', '.join(map(repr, ok))}")
            continue
        near = difflib.get_close_matches(k, list(REMAKE_SETTINGS), n=1, cutoff=0.85)
        if near:  # a typo of one of ours would silently leave the option off
            out.append(f"{k}: unknown remake setting; did you mean {near[0]}?")
    kind = remake.get("remake_ganons_soul", "off")
    n = remake.get("remake_ganons_soul_count")
    if n == 0 and not isinstance(n, bool):  # the app's "all of that kind"
        n = None
    if n is not None:
        if kind == "off" or kind not in SOUL_RANGE:
            out.append("remake_ganons_soul_count is set but remake_ganons_soul is 'off'")
        elif isinstance(n, bool) or not isinstance(n, int) or not SOUL_RANGE[kind][0] <= n <= SOUL_RANGE[kind][1]:
            lo, hi = SOUL_RANGE[kind]
            out.append(f"remake_ganons_soul_count = {n!r}: {kind} takes {lo} to {hi}")
    if remake.get("remake_racing") is True and getattr(settings, "randomize_all_sfx", False):
        out.append("remake_racing with randomize_all_sfx: that draws the fanfares at random (OoTR's "
                   "randomize_key), which changes how long item gets take; turn randomize_all_sfx off")
    return out


def untested(settings):
    out = []
    for k, v in active(settings).items():
        if k == "remake_ganons_soul_count":
            continue
        if k == "remake_ganons_soul":
            kind, n = soul(settings)
            out.append(f"extras_story: remake_ganons_soul {kind} {n} (Ganondorf's door scene checks the count)")
        elif k == "remake_racing":
            out.append("extras_story: remake_racing (locked: " + ", ".join(f"{n} = {v!r}" for n, v in
                                                                     RACING_LOCKS.items()) + ")")
        else:
            out.append(f"extras_story: {k} = {v!r}")
    return out


def before_build(settings):
    """For remake_racing, locks the personal settings that change scene lengths. OoT3DR overrides them the same way."""
    if value(settings, "remake_racing"):
        for name, want in RACING_LOCKS.items():
            if getattr(settings, name, want) != want:
                setattr(settings, name, want)


# Logic (built world, before the fill)
def _region_name(r):
    return getattr(r, "name", r)


def _set_rule(world, spot, rule):
    spot.rule_string = rule
    world.parser.parse_spot_rule(spot)


def _entrances_into(world, region):
    """Every exit leading into `region`. These are dungeon rooms, so OoTR's entrance shuffle never moves these exits."""
    found = [e for e in world.get_entrances() if _region_name(e.connected_region) == region]
    if not found:
        raise RuntimeError(f"extras_story: no exit into {region} (OoTR's or the remake's logic changed)")
    return found


def apply_logic(world, settings):
    """The options' rules (data/rando/logic/extras_story.json) on the built world."""
    rules = logic()
    keys = []
    if value(settings, "remake_sleeping_waterfall") == "open":
        keys.append("remake_sleeping_waterfall=open")
    if value(settings, "remake_jabu_mouth") == "open":
        keys.append("remake_jabu_mouth=open")
    if value(settings, "remake_medallion_trials"):
        keys.append("remake_medallion_trials=true")
    changed = []
    for key in keys:
        spec = rules[key]
        for name, rule in spec.get("set", {}).items():
            _set_rule(world, world.get_entrance(name), rule)
            changed.append(name)
        for name, (old, new) in spec.get("replace", {}).items():
            e = world.get_entrance(name)
            rule, n = re.subn(rf"\b{re.escape(old)}\b", new, e.rule_string)
            if not n:
                raise RuntimeError(f"extras_story: {name}: no {old} in its rule {e.rule_string!r}")
            _set_rule(world, e, rule)
            changed.append(name)
        for region, extra in spec.get("and_into", {}).items():
            for e in _entrances_into(world, region):
                _set_rule(world, e, f"({e.rule_string}) and ({extra})")
                changed.append(e.name)
    s = soul(settings)
    if s:
        kind, n = s
        spec = rules["remake_ganons_soul"]
        cond = spec["conditions"][kind].format(n=n)
        for region, extra in spec["and_into"].items():
            for e in _entrances_into(world, region):
                _set_rule(world, e, f"({e.rule_string}) and ({extra.format(condition=cond)})")
                changed.append(e.name)
        # OoTR only counts tokens and hearts as progress up to what its own goals need (World.max_progressions).
        # We raise it so the playthrough and the "required" checks see the soul's count.
        mp = world.max_progressions
        if kind == "tokens":
            mp["Gold Skulltula Token"] = max(mp.get("Gold Skulltula Token", 0), n)
        if kind == "hearts":
            mp["Heart Container"] = max(mp.get("Heart Container", 0), n)
            for name in ("Piece of Heart", "Piece of Heart (Treasure Chest Game)"):
                mp[name] = max(mp.get(name, 0), 4 * n)
    world.remake_extras_story_rules = changed
    return changed


def keep_locations(world, settings):
    apply_logic(world, settings)
    return set()


def before_fill(world, settings):
    """With Ganon's soul on tokens or hearts, those items lead to the goal. OoTR's majoritem (hints, item placement by
    major/minor) only counts them for its own token/heart goals, so this makes it count them for this one too."""
    s = soul(settings)
    if not s or s[0] not in ("tokens", "hearts"):
        return
    import Item
    prop = Item.Item.majoritem
    if getattr(prop.fget, "remake_ganons_soul", None) is not None:
        prop.fget.remake_ganons_soul = s[0]
        return
    original = prop.fget

    def majoritem(self, _original=original):
        kind = majoritem.remake_ganons_soul
        if self.world is not None and self.advancement:
            if kind == "tokens" and self.type == "Token":
                return True
            if kind == "hearts" and (self.name == "Heart Container" or self.name.startswith("Piece of Heart")):
                return True
        return _original(self)
    majoritem.remake_ganons_soul = s[0]
    Item.Item.majoritem = property(majoritem)


# Patch plan
def _step(file, event):
    h = data()["hooks"][file]
    return dict(h["steps"][event], flowchart=h["flowchart"])


class Hooks:
    """New steps in front of existing ones, so every step or entry leading there goes to them first. A node target is
    a label of the same fragment, "@Event" (an existing step), None (end) or "NEXT" (the step itself)."""

    def __init__(self):
        self.pre, self.events = {}, []

    def pre_hook(self, file, event, nodes, start):
        self.pre.setdefault((file, event), []).append((nodes, start))

    def assemble(self):
        out = []
        for (file, event), frags in self.pre.items():
            info = _step(file, event)
            graph = f"Rando_Extras_{event}"
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
            out.append({"file": file, "flowchart": info["flowchart"], "add_graph": graph, "nodes": nodes,
                        "start": first})
            for kind, where, k in info["preds"]:
                op = {"file": file, "flowchart": info["flowchart"], "next": f"{graph}_{first}"}
                if kind == "entry":
                    op["entry"] = where
                else:
                    op["event"] = where
                    if kind in ("case", "fork"):
                        op[kind] = k
                out.append(op)
        return out


def _bool(flag, yes, no):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
            "params": {"GameDataName": flag, "Index": -1}, "cases": {0: yes, 1: no}}


def _message_entry(key, text, msgs, events):
    """A system-text message (a new label in Item_Event, every language) shown by a new GetPouchContent entry.
    Returns the call target."""
    label = f"Rando_Extras_{key}"
    # _hints_check compares new labels by their full markup, so this uses markup even without tags. A text op
    # would look for an existing vanilla message.
    msgs.append({"lang": "*", "file": TEXT_FILE, "label": label, "markup": text, "add": True})
    events.append({"file": "GetPouchContent", "flowchart": data()["hooks"]["GetPouchContent"]["flowchart"],
                   "add_graph": label, "start": "t",
                   "nodes": {"t": {"copy": "Event23", "next": None,
                                   "params_over": {"MessageId": f"{TEXT_FILE[:-5]}:{label}",
                                                   "IsOverrideStyle": False}}}})
    return f"GetPouchContent:{label}"


def _moved(world, name):
    """True when OoTR's entrance shuffle gave this entrance another destination (the entrances plugin moves it)."""
    if not getattr(world, "entrance_shuffle", False):
        return False
    try:
        e = world.get_entrance(name)
    except Exception:  # noqa: BLE001 - not an entrance of this world
        return False
    return e.replaces is not None and e.replaces is not e


def trials_plan(h, msgs, events, placements):
    calls = {t: _message_entry(f"Trial{t}", f"This chamber is sealed.\nOnly the bearer of the {t} Medallion\n"
                                            f"may pass.", msgs, events) for t in TRIALS}
    for t, step in TRIAL_DOOR_STEP.items():
        frag = {"m": _bool(f"IsGet.Item_Medal_{t}", "NEXT", "deny"), "deny": {"call": calls[t], "next": None}}
        start = "m"
        if t == LIGHT_HOST:  # the Light trial's barrier door plays this scene too, we tell it apart by its anchor
            anchor = data()["anchors"]["light_barrier_door"]["name"]
            frag.update({
                "near": {"actor": "GameSystemActor", "query": "EventQueryIsDistanceBetweenActorsClose",
                         "params": {"ActorNameA": "Player_Event", "InstanceNameA": "", "IsAnchorActorA": False,
                                    "ActorNameB": "DestinationAnchor", "InstanceNameB": anchor,
                                    "IsAnchorActorB": True, "IsTargetPlayingAllEvent": False,
                                    "CheckDistance": 4.0},
                         "cases": {0: "light", 1: "m"}},
                "light": _bool("IsGet.Item_Medal_Light", "pass", "deny_light"),
                "pass": {"copy": step, "next": None},  # through the door, as the default door scene does
                "deny_light": {"call": calls["Light"], "next": None},
            })
            start = "near"
        h.pre_hook("InsideGanonCastle_CommonGimmick", step, frag, start)
    door = data()["placements"]["light_barrier_door"]
    placements.append({"file": door["file"], "hash": door["hash"],
                       "set": {"Dynamic.NomralEvent": f"InsideGanonCastle_LookBarrierFromDoor_{LIGHT_HOST}"}})


def soul_plan(settings, h, msgs, events):
    kind, n = soul(settings)
    if kind == "stones":
        req = ("flags", list(C.STONES), n)
    elif kind == "medallions":
        req = ("flags", list(C.MEDALLIONS), n)
    elif kind == "dungeons":
        req = ("flags", list(C.STONES + C.MEDALLIONS), n)
    elif kind == "tokens":
        req = ("int", C.TOKENS, n)
    else:
        req = ("int", C.MAX_LIFE, 4 * n)
    one, many = SOUL_WORDS[kind]
    words = f"{n} {one if n == 1 else many}" if kind != "hearts" else f"{n} hearts"
    text = (f"Ganondorf's power is beyond your reach.\nYou need {words}\nto face him." if kind != "hearts" else
            f"Ganondorf's power is beyond your reach.\nYou need {words} of life\nto face him.")
    call = _message_entry("GanonsSoul", text, msgs, events)
    nodes, start = C.scene_nodes(req, "s", "NEXT", "deny")
    nodes.update({
        # the boss rush (DreamWorld) uses the same door scene, but no soul is needed there
        "dream": {"actor": "GameSystemActor", "query": "EventQueryIsDreamWorld", "cases": {0: "NEXT", 1: start}},
        "deny": {"call": call, "next": None},
    })
    h.pre_hook("Common_Dungeon_OpenShutterMove", "Event307", nodes, "dream")


def intros_plan(intros, defaults, byml):
    """remake_skip_area_intros: new-file flags for the intros nothing else hangs on, with their places showing their
    name (and getting marked visited) on arrival like places without an intro (the Location table), and for the
    others new steps in front of the arrival entry's intro step (intro played, place visited) and that step playing
    the plain arrival instead. Only the intro step and what leads to it change, so the steps after it (quest steps
    other plugins guard) stay as they are."""
    rows = sorted({r for x in intros["new_file"] for r in x["rows"]})
    for x in intros["new_file"]:
        defaults[x["played"]] = True
    byml.append({"file": intros["locations"],
                 "set": {f"[__RowId={r}].IsShowLocationUIFirstTimeInDemo": False for r in rows}})
    file, fc, out = intros["arrive"], intros["flowchart"], []
    for x in intros["edits"]:
        step = x["step"]
        flags = [x["played"]] + x["visit"]
        nodes = {f"f{i}": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                           "params": {"GameDataName": f, "Index": -1, "Value": True},
                           "next": f"f{i + 1}" if i + 1 < len(flags) else f"@{step}"} for i, f in enumerate(flags)}
        graph = f"Rando_Intro_{step}"
        out.append({"file": file, "flowchart": fc, "event": step, "param": "EventName", "value": intros["arrive"]})
        out.append({"file": file, "flowchart": fc, "add_graph": graph, "nodes": nodes, "start": "f0"})
        for kind, where, k in x["preds"]:
            op = {"file": file, "flowchart": fc, "next": f"{graph}_f0"}
            if kind == "entry":
                op["entry"] = where
            else:
                op["event"] = where
                if kind in ("case", "fork"):
                    op[kind] = k
            out.append(op)
    return out


def world_plan(settings, world):
    if not active(settings):
        return {}
    d = data()
    h = Hooks()
    events, msgs, placements, binary, defaults = [], [], [], [], {}

    if value(settings, "remake_sleeping_waterfall") == "open":
        defaults["Zorariver_TheWaterfallsplits"] = True

    if value(settings, "remake_skip_four_poes"):
        fc = d["hooks"]["Dm_ForestTemple_0010"]["flowchart"]
        events.append({"file": "Dm_ForestTemple_0010", "flowchart": fc, "add_graph": "Rando_Extras_SkipPoes",
                       "start": "elevator", "nodes": {
                           "elevator": {"copy": "Event305", "next": "played"},
                           "played": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                                      "params": {"GameDataName": "HavePlayedEvent.Dm_ForestTemple_0010",
                                                 "Index": -1, "Value": True}, "next": "step"},
                           "step": {"copy": "Event2", "next": "ui"},
                           "ui": {"copy": "Event307", "next": None}}})
        h.pre_hook("ForestTemple_OpenDoor_Room01To02", "Event3",
                   {"c": {"call": "Dm_ForestTemple_0010:Rando_Extras_SkipPoes", "next": "@Event11"}}, "c")

    if value(settings, "remake_skip_lake_owl"):
        info = _step("Npc_Kaepora_LakeHylia", "Event19")
        if info["preds"] != [["next", "Event18", None]]:
            raise RuntimeError(f"extras_story: the owl's flight scene has other predecessors: {info['preds']}")
        # with owl_drops the entrances plugin turns the flight's next step into its own level change
        target = "Rando_OwlFlight_warp" if _moved(world, "LH Owl Flight -> Hyrule Field") else "Event22"
        events.append({"file": "Npc_Kaepora_LakeHylia", "flowchart": info["flowchart"], "event": "Event18",
                       "next": target})

    readback, byml = {}, []
    if value(settings, "remake_skip_area_intros"):
        events += intros_plan(d["intros"], defaults, byml)
        readback["intros"] = {"edits": [{k: x[k] for k in ("step", "preds", "played", "visit")}
                                        for x in d["intros"]["edits"]],
                              "defaults": {x["played"]: True for x in d["intros"]["new_file"]},
                              "locations": d["intros"]["locations"],
                              "rows": sorted({r for x in d["intros"]["new_file"] for r in x["rows"]})}

    if value(settings, "remake_jabu_mouth") == "open":
        for w in d["ainb"]["jabu_open_mouth"]:
            binary.append(dict(w, note="remake_jabu_mouth"))
        if not _moved(world, "Zoras Fountain -> Jabu Jabus Belly Beginning"):
            # the first entry through the mouth plays Jabu-Jabu's first-arrival scene, like the fish's swallow does. A
            # moved doorway that leads to Jabu-Jabu gets the same two settings from the entrances plugin.
            m = d["placements"]["jabu_mouth"]
            placements.append({"file": m["file"], "hash": m["hash"], "set": {
                "Dynamic.InitEventFlag": "HavePlayedEvent.Get_StoneOfWater_ArriveJabuJabuBelly",
                "Dynamic.InitEventName": "Get_StoneOfWater_ArriveJabuJabuBelly"}})

    if value(settings, "remake_medallion_trials"):
        trials_plan(h, msgs, events, placements)

    if soul(settings):
        soul_plan(settings, h, msgs, events)

    if value(settings, "remake_king_zora_speed") == "fast":
        h.pre_hook("Dm_Zora_0010", "Event3", {
            "robe": {"copy": "Event55", "next": "zora"},     # his robe walkable (the move's own lasting effect)
            "zora": {"copy": "Event195", "next": "palette"},  # the Zora by the passage to her post
            "palette": {"copy": "Event177", "next": "dof"},
            "dof": {"copy": "Event232", "next": "face"},
            "face": {"copy": "Event175", "next": "whew"},
            "whew": {"copy": "Event92", "next": "@Event184"}}, "robe")

    plan = {}
    events = h.assemble() + events
    if events:
        plan["events"] = events
    if placements:
        plan["placements"] = placements
    if binary:
        plan["binary"] = binary
    if msgs:
        plan["text"] = msgs
    if defaults:
        plan["gamedata"] = {"defaults": defaults}
    if byml:
        plan["byml"] = byml
    if readback:
        plan["_extras_story"] = readback
        plan["_verify_plugins"] = ["extras_story"]
    return plan


def verify(patch, plan, romfs):
    """Reads remake_skip_area_intros back from a built patch: each edited arrival step plays the plain arrival, and
    every step or entry that led to it now goes through its flags (each set true) first; the new-file flags are on.
    Returns [problem, ...]."""
    from romtools import Romfs, byml_load, murmur3_32
    from evfl import Evfl
    from parity._story_build import newest, flat
    rb = (plan.get("_extras_story") or {}).get("intros")
    if not rb:
        return []
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    rel, _ = newest(romfs, "Dm_SY_BancChangeArrive")
    if not os.path.exists(os.path.join(patch, rel)):
        return [f"{rel}: not in the patch"]
    fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == "Dm_SY_BancChangeArrive")
    by = {e["name"]: e for e in fc["events"]}

    def call(e):
        a = fc["actors"][e["actor"]]
        return f"{a['name']}.{a['actions'][e['action']]}" if e["type"] == "action" else None

    for x in rb["edits"]:
        step = by.get(x["step"])
        if step is None or flat(step.get("params"), {}).get("EventName") != "Dm_SY_BancChangeArrive":
            bad.append(f"intros: {x['step']} doesn't play the plain arrival")
            continue
        for kind, where, k in x["preds"]:
            if kind == "entry":
                i = fc["entry_points"][where]["main"]
            else:
                e = by[where]
                i = e["cases"][k]["next"] if kind == "case" else e["forks"][k] if kind == "fork" else e.get("next")
            got = []
            while i is not None and fc["events"][i]["name"] != x["step"] and len(got) < 8:
                e = fc["events"][i]
                p = flat(e.get("params"), {})
                if call(e) != "GameDataActor.EventTriggerSetGameDataBool" or p.get("Value") is not True:
                    break
                got.append(p.get("GameDataName"))
                i = e.get("next")
            if i is None or fc["events"][i]["name"] != x["step"] or got != [x["played"]] + x["visit"]:
                bad.append(f"intros: {where} reaches {x['step']} through {got}, planned {[x['played']] + x['visit']}")
    gd, _ = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)
    bools = {e["Hash"]: e for e in gd["Data"]["Bool"]}
    for name, want in rb["defaults"].items():
        if bools.get(murmur3_32(name), {}).get("DefaultValue") is not want:
            bad.append(f"intros: save data {name} doesn't start {want}")
    locs = {r["__RowId"]: r for r in byml_load(fs.read(rb["locations"]), allow_big=True)[0]}
    for row in rb["rows"]:
        if locs.get(row, {}).get("IsShowLocationUIFirstTimeInDemo") is not False:
            bad.append(f"intros: {row} still leaves its first name to the skipped intro")
    return bad
