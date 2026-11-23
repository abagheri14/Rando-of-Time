"""OoT Randomizer-style progressive items, decided when the item is given (like OoTR's resolve_upgrades).

A chest holding a progressive item runs a shared "give the right tier" scene instead of its normal opening:
  1. the chest's opening, as vanilla picks it (Dm_SY_TreasureboxSmall Open). Link opens it from the front
     (DemoOpenTreasureBoxFront) or kicks it open (DemoOpenTreasureBoxWithKick), the lid opens and the pad
     rumbles.
  2. what the player already owns, highest tier first (PouchSystemActor.EventQueryIsExistInPouch)
  3. the tier is given with the game's in-cutscene get routine, the one NPC cutscenes use
     (Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff, e.g. the Lost Woods bullet bag). It creates the item
     from its name, Link holds it up with his "got it" pose and camera, fanfare and glow, the message shows,
     the item is added and the held model is put away.
  4. the chest is marked opened (TreasureBox_EventStarter.EventTriggerTreasureBoxOpened) and the game saves.
The chest's own hidden contents are never woken, so they never show.

Query answers in these scenes are case 0 for "yes" and case 1 for "no". Vanilla does it that way too, Death
Mountain's eye-drop check removes the eye drops on case 0 and the small chest's minigame check plays the
minigame pose on case 0. With them the other way round the chest gave the Longshot first.
"""
import functools
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRESSIVE = json.load(open(os.path.join(HERE, "config", "progressive.json"), encoding="utf-8"))["items"]


def _merged(key):
    """{tier actor: value} from every item's optional `key` table (config/progressive.json)."""
    out = {}
    for v in PROGRESSIVE.values():
        for actor, x in (v.get(key) or {}).items():
            if out.setdefault(actor, x) != x:
                raise ValueError(f"config/progressive.json: {actor} has two different {key!r} entries")
    return out


# What tells us the player owns a tier when it isn't the tier's own name. Swords sit in the pouch as their
# Weapon_* actor (vanilla checks Weapon_Sword_Giant, not Item_Sword_Giant), and a broken Giant's Knife still counts
# as the knife tier. Tiers missing here get checked by their own name (Item_Hookshot works that way, tested).
OWNED = _merged("owned")
# Tiers the usual give step can't hand over by name, e.g. Pouch_Wallet_Small, the Kokiri Wallet's only actor with
# a model, since Item_Wallet_Small has no actor pack. Each is {"call": scene entry that gives it, "add": the pouch
# actor it adds}.
GIVE = _merged("give")

# Items Link can't hold up as they are
# Link's item-get pose ends when the shown item's AS plays Rotate_GetDemo (Dm_SY_GetInEvent Item_Position Event51,
# EventIgnitionShowItem {IsAsPlay: True, IsWaitEnd: True}). An actor without that command never gets let go and the
# game freezes (NX2-ZOOTR saw it in game, and OotrR #15 saw the ocarina crash). config/hold_up.json lists the 26 such
# actors the randomizer can give and how each one still gets held up:
# - "own": the actor gets the hold-up animation (songs, small bags, see hold_up_ops)
# - "show": a display actor of our own with the same model ("displays"/display_ops) is held up while the window,
#   add, fanfare and glow name the item (SHOWN_ENTRY). That's for stones, medallions, ocarinas and the Master Sword.
# - "window": WINDOW_ENTRY, the fanfare and the get window (nothing uses it now)
# tools/rando/no_pose_check.py reads it back and checks that no give reaches a hold-up whose shown actor lacks
# Rotate_GetDemo, isn't an item-get actor (Item_EventObject_Base) or has a name over DISPLAY_NAME_MAX characters.
# The menu displays Pouch_Ocarina_* / *_ImportantMenu aren't item-get actors and crashed in game.
HOLD = json.load(open(os.path.join(HERE, "config", "hold_up.json"), encoding="utf-8"))
HOLD_OWN = {k: v for k, v in HOLD["own"].items() if not k.startswith("_")}
HOLD_SHOW = {k: v for k, v in HOLD["show"].items() if not k.startswith("_")}
HOLD_WINDOW = {k for k in HOLD["window"] if not k.startswith("_")}
HOLD_DISPLAYS = {k: v for k, v in (HOLD.get("displays") or {}).items() if not k.startswith("_")}
# Progressive tiers given through a give entry of their own because their actor can't be held up
# (config/progressive.json "pose": false, the ocarinas). Rando_GiveOcarina holds up the tier's display ("ShowName"),
# then runs its "after" entry.
NO_POSE = {tier for tier, g in GIVE.items() if g.get("pose") is False}
NO_POSE_FILE = HOLD_FILE = "Dm_SY_GetInEvent"
SHOWN_ENTRY = "Rando_GetShown"                 # {ActorName, ShowName}: the hold-up showing ShowName, giving ActorName
WINDOW_ENTRY = "Rando_GetWindow"               # {ActorName}: fanfare, get window + silent add (no hold-up)
NO_POSE_ENTRY = "Rando_GiveOcarina"            # {ActorName, ShowName}: SHOWN_ENTRY, then AFTER_ENTRY
NO_POSE_PAY = "Rando_GiveOcarina_Pay"          # {ActorName, ShowName}: a scrub sale's payment, then NO_POSE_ENTRY
AFTER_ENTRY = "Rando_OcarinaAfter"             # equipment synced with the pouch, then the ocarina's action guide
OCARINA_GUIDE = "ActionGuide:OpenActionGuideSceenForOcarina"
SCRUB_FILE = "Enemy_Scrub_Business_Common"  # the Business Scrubs' sales
SCRUB_SALE_SRC, SCRUB_HANDOVER = "SimpleShopSub_Scrub_Business_OneTime", "Event4"  # its pay-and-hold-up hand-over
POSE_FREE_FILES = ("GetPouchContent",)         # files whose routines never touch Player_Event (no hold-up)
WINDOW_GIVE = "GetPouchContent:GetPouchContentByActorName"
HOLD_ENTRIES = (SHOWN_ENTRY, WINDOW_ENTRY, NO_POSE_ENTRY, NO_POSE_PAY, AFTER_ENTRY)


def no_pose(tier):
    return tier in NO_POSE


def show_of(actor):
    """The actor the hold-up creates for `actor`.

    That's its display stand-in from HOLD_SHOW, or for a tier given by its own entry, the display built for what that
    entry adds (GIVE "add" matched with "for" in config/hold_up.json "displays"). Otherwise it's `actor` itself.
    The Kokiri Wallet needs this. Its Pouch_Wallet_Small is a menu actor with no model bind, so it's shown as
    Rando_Show_WalletSmall, same as its own entry shows it. A big chest holding it would otherwise show the menu actor,
    which is the hold-up crash class, and no_pose_check reads that back."""
    if actor in HOLD_SHOW:
        return HOLD_SHOW[actor]
    add = (GIVE.get(actor) or {}).get("add")
    return next((d for d, v in sorted(HOLD_DISPLAYS.items()) if add and v.get("for") == add), actor)


def give_node(tier, nxt):
    """A node handing over `tier` through its own give entry (GIVE), then going to `nxt`."""
    g = GIVE[tier]
    node = {"call": g["call"], "next": nxt}
    if g.get("params"):
        node["params"] = dict(g["params"])
    return node


def hold_node(actor, nxt, host=None):
    """A node that hands over plain actor `actor` the way the hold-up routines do, for an actor Link can't hold up as it
    is. config/hold_up.json says how: "show" is its display's hold-up and "window" is the get window.
    Returns None when the usual routine can do it (the actor holds up, or "own" gives it the animation). `host` is the
    file the node sits in, and that file's own entries get called as ":Entry"."""
    pre = ":" if host == HOLD_FILE else f"{HOLD_FILE}:"
    if actor in NO_POSE:  # an ocarina uses its own give entry (display hold-up, then equipment sync and guide)
        node = give_node(actor, nxt)
        f, _, e = node["call"].partition(":")
        if f == host:
            node["call"] = f":{e}"
        return node
    if actor in HOLD_SHOW:
        return {"call": f"{pre}{SHOWN_ENTRY}", "params": {"ActorName": actor, "ShowName": HOLD_SHOW[actor]},
                "next": nxt}
    if actor in HOLD_WINDOW:
        return {"call": f"{pre}{WINDOW_ENTRY}", "params": {"ActorName": actor}, "next": nxt}
    return None


def after_nodes(n, tier, label, nxt):
    """Adds the tier's "after" call (for the ocarina that's equipment sync and action guide) as node `label` going to
    `nxt`. Returns the label to go to after a pose-free give of `tier`, which is `nxt` itself when the tier has no
    such call."""
    after = (GIVE.get(tier) or {}).get("after") if tier in NO_POSE else None
    if not after:
        return nxt
    n[label] = {"call": after, "next": nxt}
    return label


def _arg(name):
    return {"arg": name}


def hold_graphs(fc):
    """{file: [(entry, nodes, start)]} for the hold-up entries of config/hold_up.json and the ocarinas' give entries.
    They all go in Dm_SY_GetInEvent. `fc` is its vanilla flowchart model, and the hold-up steps are copies of the ones
    in GetInEvent_NotLookatObjectTurnOff. Scrub sales are handled in scrub_intercept."""
    by_name = {e["name"]: e for e in fc["events"]}
    # GetInEvent_NotLookatObjectTurnOff is Event118, a call to :GetInEvent_DemoNotLookAtTurnOff (Event109 creates the
    # shown item, Event289 locator, Event290 Link's pose, Event112 position, fanfare and glow, Event3 the get window and
    # the add). After that it's Event111 onwards: action guide, put away, glow off, Navi.
    # The locator, pose, fanfare and glow look the item up by name in the pouch tables
    # (EventQueryPouchContentGetType...), so they get the item's name, not its display.
    for name, want in (("Event118", ("subflow", "", "GetInEvent_DemoNotLookAtTurnOff")),
                       ("Event109", ("action", None, None)),
                       ("Event289", ("subflow", "", "GetInEvent_SetLocator")),
                       ("Event290", ("subflow", "", "GetInEvent_Animation")),
                       ("Event112", ("subflow", "", "Item_Position")),
                       ("Event3", ("subflow", "GetPouchContent", "GetPouchContentByActorName")),
                       ("Event111", ("subflow", "ActionGuide", "ActionGuide"))):
        e = by_name.get(name)
        if e is None or e["type"] != want[0] or (want[0] == "subflow" and (
                (e.get("flowchart") or "") != want[1] or e.get("entry_point") != want[2])):
            raise ValueError(f"Dm_SY_GetInEvent {name} is no longer {want}")
    ending, end_start = clone(fc, "Event111", "end_", {})
    shown = {
        "show": {"copy": "Event109", "params_over": {"Actor": _arg("ShowName")}, "next": "loc"},
        "loc": {"copy": "Event289", "next": "anim"},
        "anim": {"copy": "Event290", "next": "pos"},
        "pos": {"copy": "Event112", "next": "add"},
        "add": {"copy": "Event3", "next": end_start},
    }
    shown.update(ending)
    window = {
        "fanfare": {"actor": "SoundSystemActor", "action": "EventTriggerSoundStartFanfare",
                    "params": {"GameDataName": "", "IsEnableIntro": False, "ActorName": _arg("ActorName")},
                    "next": "window"},
        "window": {"call": WINDOW_GIVE, "params": {"ActorName": _arg("ActorName")}, "next": None},
    }
    names = {"ActorName": _arg("ActorName"), "ShowName": _arg("ShowName")}
    ocarina = {"held": {"call": f":{SHOWN_ENTRY}", "params": dict(names), "next": "after"},
               "after": {"call": f":{AFTER_ENTRY}", "next": None}}
    # NX2-ZOOTR shows this in game. An ocarina added by a flow only plays once Link's equipment is synced with the
    # pouch, so these are the steps SubEvent_AllBossBattle uses for that (Event12 one-frame wait, Event11, Event39).
    after = {
        "wait": {"actor": "EventSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 1},
                 "next": "sync"},
        "sync": {"actor": "UISystemActor", "action": "EventTriggerSyncPlayerEquipmentAndPouch", "next": "equip"},
        "equip": {"actor": "Player_Event", "action": "EventWaitCreationFinishedEquipment",
                  "params": {"IsWaitEnd": True}, "next": "guide"},
        "guide": {"call": OCARINA_GUIDE, "next": None},
    }
    pay = {  # same as GetInEvent_NotTurn_2DShop Event193/Event194, pays the price the sale stored in SimpleShop_Price
        "pay": {"actor": "PouchSystemActor", "action": "EventTriggerAddGameDataIntToRupee",
                "params": {"IsSignInverse": True, "GameDataName": "SimpleShop_Price"}, "next": "stable"},
        "stable": {"actor": "UISystemActor", "action": "EventWaitStableNumDisplay", "params": {"IsWaitEnd": True},
                   "next": "give"},
        "give": {"call": f":{NO_POSE_ENTRY}", "params": dict(names), "next": None},
    }
    out = {HOLD_FILE: [(SHOWN_ENTRY, shown, "show"), (WINDOW_ENTRY, window, "fanfare"),
                       (AFTER_ENTRY, after, "wait"), (NO_POSE_ENTRY, ocarina, "held"), (NO_POSE_PAY, pay, "pay")]}
    return out


SHOW_STEPS = ("EventCreateShowItemFromActorFileName", "EventCreateShowItem")  # Player_Event: the item Link holds


def pose_args(load_fc, name, entry, memo=None, depth=0):
    """Arguments X of entry `entry` in event file `name` where a call with X = an actor makes Link hold that actor up.
    That means the entry reaches a Player_Event.EventCreateShowItem* whose Actor is X, either directly or through calls
    that pass X on (every GetInEvent_* routine, NpcCommon hand-overs, scrub sales...).
    load_fc(name) -> evfl flowchart model or None."""
    memo = {} if memo is None else memo
    key = (name, entry)
    if key in memo:
        return memo[key]
    memo[key] = frozenset()  # Break call cycles.
    fc = load_fc(name)
    if fc is None or entry not in fc["entry_points"] or depth > 16:
        return frozenset()
    out, events, seen, todo = set(), fc["events"], set(), [fc["entry_points"][entry]["main"]]
    while todo:
        i = todo.pop()
        if i in seen or i >= len(events):
            continue
        seen.add(i)
        e = events[i]
        todo += [x for x in [e.get("next") if e["type"] != "type6" else None, e.get("join")]
                 + [c["next"] for c in e.get("cases", [])] + list(e.get("forks", [])) if x is not None]
        items = ((e.get("params") or {}).get("items")) or {}
        if e["type"] == "action":
            a = fc["actors"][e["actor"]]
            if a["name"] == "Player_Event" and a["actions"][e["action"]] in SHOW_STEPS:
                v = items.get("Actor")
                if v is not None and v["type"] == "argument":
                    out.add(v["value"])
        elif e["type"] in ("subflow", "subflow_switch"):
            for x in pose_args(load_fc, e.get("flowchart") or name, e["entry_point"], memo, depth + 1):
                v = items.get(x)
                if v is not None and v["type"] == "argument":
                    out.add(v["value"])
    memo[key] = frozenset(out)
    return memo[key]


def step_poses(load_fc, fc, event, param, memo=None):
    """Whether step `event` of flowchart model `fc` makes Link hold up the actor its parameter `param` names."""
    if event["type"] not in ("subflow", "subflow_switch"):
        return False
    return param in pose_args(load_fc, event.get("flowchart") or fc["name"], event["entry_point"], memo)


SCRUB_INTERCEPT = "Rando_HoldHandover"      # per-item hand-over in the scrub's one-time sale, ahead of the vanilla one
SCRUB_SCRATCH = "Scrub_Business_TempItemName_03"  # a String64 the one-time sale never reads (the dungeons' scratch)
ICE_MARKER = "Rando_IceTrap"                # a scrub sale's ActorName for an ice trap (only the hand-over reads it)
DI_MARKER = "Rando_DI_Call_"                # a scrub sale's ActorName for a dungeon item, named after its credit entry
# Dungeon item markers come from tools/rando/shops.py dungeon_marker, see also parity/dungeons.py call_entry.
# Every scrub-sale marker that names a Dm_SY_GetInEvent entry for the intercept to pay and call (tools/rando/shops.py
# call_marker):
# - a dungeon item's credit entry
# - a progressive item's tier entry (RandoST_<Item>_Get) and the Magic Bean Pack's (RandoST_BeanPack, songs/trade
#   plugin)
# - a soul's or the Skeleton Key's give entry (extras_souls)
# - for a trap of any kind but ice, its effect entry (parity/_chests_scenes.py trap_graph), which takes the payment
#   and then does the kind's attacker or rupee loss
CALL_MARKERS = (DI_MARKER, "RandoST_", "Rando_Soul_", "Rando_SkeletonKey", "Rando_GiveHeart", "Rando_GiveFairy",
                "Rando_Trap_")
# Marker entries that read parameters. The heal entries take ActorName (parity/dungeons.py heal_graph), so a Recovery
# Heart or Fairy Drop gets held up, named in its window and heals as itself.
CALL_PARAMS = {"Rando_GiveHeart": {"ActorName": "Obj_Heart"}, "Rando_GiveFairy": {"ActorName": "Obj_Fairy"}}
ICE_PAY = "Dm_SY_GetInEvent:Rando_IceTrap_Pay"  # the chests plugin's pay-and-freeze entry


def scrub_intercept(scrub_fc, actors):
    """(entry, nodes, start, preds) for Enemy_Scrub_Business_Common.

    This goes inside the scrub's one-time sale (SimpleShopSub_Scrub_Business_OneTime), right before its hand-over. The
    hand-over is Event4, Dm_SY_GetInEvent:GetInEvent_NotTurn_2DShop. It pays, holds the item up, shows the window and
    adds the item, and it's the only step that reads the ActorName argument.
    We copy the item named by ActorName into a scratch String64, read it back two frames later (vanilla never reads a
    value it just wrote any sooner) and compare it with each of `actors`. A match pays (2DShop's own Event193/Event194)
    and gives its own hold-up, then carries on with the sale's own next step (ScrubBusiness_IsBuy, BuySuccess, the scrub
    flees). That hold-up is hold_node (a display's hold-up, the window, an ocarina's give entry), the ice trap's
    pay-and-freeze for ICE_MARKER, or for a CALL_MARKERS name that entry, like a dungeon item's credit entry or a
    progressive item's tier entry. No match means the vanilla hand-over.
    The steps run inside the vanilla entry so the scrub actor it binds by argument
    (Enemy_Scrub_Business[SimpleShopSub_Scrub_Business_OneTime(...)]) stays bound. In a copy of the sale under a new
    entry that actor is unbound and it hangs (OotrR saw it in game).
    preds are routing ops (no file/flowchart)."""
    events = scrub_fc["events"]
    by_name = {e["name"]: e for e in events}
    hand = by_name[SCRUB_HANDOVER]
    if hand["type"] != "subflow" or (hand.get("flowchart"), hand.get("entry_point")) != (
            "Dm_SY_GetInEvent", "GetInEvent_NotTurn_2DShop"):
        raise ValueError(f"{SCRUB_FILE} {SCRUB_HANDOVER} is no longer the scrub's 2DShop hand-over")
    after = events[hand["next"]]["name"] if hand.get("next", 0xFFFF) < len(events) else None
    resume = f"@{after}" if after else None
    actors = sorted(set(actors))
    n = {"set": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                 "params": {"GameDataName": SCRUB_SCRATCH, "Index": -1, "Value": {"arg": "ActorName"}}, "next": "wait"},
         "wait": {"actor": "EventSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": 2},
                  "next": "is0" if actors else f"@{SCRUB_HANDOVER}"}}
    for i, actor in enumerate(actors):
        n[f"is{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                       "params": {"GameDataName": SCRUB_SCRATCH, "Index": -1, "Value": actor},
                       "cases": {YES: f"pay{i}" if actor != ICE_MARKER else f"give{i}",
                                 NO: f"is{i + 1}" if i + 1 < len(actors) else f"@{SCRUB_HANDOVER}"}}
        if actor == ICE_MARKER:
            n[f"give{i}"] = {"call": ICE_PAY, "next": resume}
            continue
        n[f"pay{i}"] = {"actor": "PouchSystemActor", "action": "EventTriggerAddGameDataIntToRupee",
                        "params": {"IsSignInverse": True, "GameDataName": "SimpleShop_Price"}, "next": f"stable{i}"}
        n[f"stable{i}"] = {"actor": "UISystemActor", "action": "EventWaitStableNumDisplay",
                           "params": {"IsWaitEnd": True}, "next": f"give{i}"}
        if actor.startswith(CALL_MARKERS):  # paid, then the item's own entry
            # That entry is a dungeon item's credit (hold-up, window, save data), a tier entry or a soul's flag and
            # message.
            n[f"give{i}"] = {"call": f"{HOLD_FILE}:{actor}", "next": resume,
                             **({"params": dict(CALL_PARAMS[actor])} if actor in CALL_PARAMS else {})}
            continue
        held = hold_node(actor, resume, SCRUB_FILE)
        if held is None:
            raise ValueError(f"{actor}: no hold-up of its own to give at a scrub")
        n[f"give{i}"] = held
    preds = []
    for kind, where, k in predecessors(scrub_fc, hand):
        if kind == "entry":
            preds.append({"entry": where})
        else:
            preds.append(dict({"event": where}, **({kind: k} if kind in ("case", "fork") else {})))
    return SCRUB_INTERCEPT, n, "set", preds


ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
GET_DEMO_ASINFO = "Component/ASInfo/Item_GetDemo.engine__component__ASInfo.bgyml"
GET_DEMO_ASINFO_PACK = "Pack/Actor/Item_Boomerang.pack.zs"  # one of the packs holding it (all hold the same bytes)
ITEM_COMMON_AS = "AS/Item_Common.root.asb"
HEAPS = ("InstanceHeapSize", "PreActorRenderInfoHeapSize")


GAME_ACTOR_INFO = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"
MODEL_KEYS = ("ModelProjectName", "FmdbName", "ModelAabbMin", "ModelAabbMax")


DISPLAY_NAME_MAX = 25  # the show-item create keeps 31 characters (m+0x826ca854), and OotrR #3 crashed over 25
DISPLAY_PREFIX = "Rando_Show_"
BASE_ACTOR = "Item_Medal_Light"  # the display pack's base: Item_EventObject_Base, PouchContent event AI, key-item pouch
BASE_PACK = f"Pack/Actor/{BASE_ACTOR}.pack.zs"
BASE_PARAM = f"Actor/{BASE_ACTOR}.engine__actor__ActorParam.bgyml"
BASE_MODELINFO = f"Component/ModelInfo/{BASE_ACTOR}.engine__component__ModelInfo.bgyml"
BASE_ROW = "Item_Sword_Kokiri"  # ActorInfo row we copy, a holdable item with no effect/sound user of its own
BASE_GAME_ROW = BASE_ACTOR  # GameActorInfo row copied (bare)
BASE_DROP = ("ELinkRef", "ActorNameRef")  # the medallion's own effect user and name, not the display's
SHOW_MODELS = "_show_models"  # tools/rando/parity/_show_models.py (the Triforce work): plan(key, romfs) -> model


def _chain_comps(files, actor):
    """Components of the ActorParam chain of `actor` inside its pack's files. The child's value wins."""
    from romtools import byml_load
    comps, name, guard = {}, actor, 0
    while name and guard < 12:
        guard += 1
        path = f"Actor/{name}.engine__actor__ActorParam.bgyml"
        if path not in files:
            break
        p = byml_load(files[path])[0]
        for k, v in (p.get("Components") or {}).items():
            comps.setdefault(k, v)
        par = p.get("$parent")
        name = par.rsplit("/", 1)[-1].split(".")[0] if par else None
    return comps


def show_model(key, romfs=None, ctx=None):
    """The model parity/_show_models.py (from the Triforce work) gives display key `key`, or None.

    The model is {"new_files": [ops], "modelinfo": {FmdbName, ModelProjectName}, "aabb": (min, max)}, and it can
    also have "anim_from": actor.
    None means there's no module or no model for that key yet, and the display keeps its vanilla model.
    ctx is the seed's plan["_show_models"] ({"controls", "controller"}, for an Ocarina note item's button label) and
    goes to its plan(). Each key and ctx is only read once (callers don't change it)."""
    items = tuple(sorted((k, v) for k, v in (ctx or {}).items() if k in ("controls", "controller")))
    return _show_model(key, romfs, items)


@functools.lru_cache(maxsize=None)
def _show_model(key, romfs, ctx_items):
    import sys
    rando = os.path.join(HERE, "tools", "rando")
    if rando not in sys.path:
        sys.path.insert(0, rando)
    try:
        from importlib import import_module
        mod = import_module(f"parity.{SHOW_MODELS}")
    except ImportError:
        return None
    m = mod.plan(key, romfs, **dict(ctx_items)) if romfs else mod.plan(key, **dict(ctx_items))
    if not m:
        return None
    for k in ("modelinfo", "aabb"):
        if k not in m:
            raise ValueError(f"parity/{SHOW_MODELS}.py plan({key!r}) has no {k!r}")
    return m


def display_available(display, romfs=None, ctx=None):
    """Whether `display` (config/hold_up.json "displays") has a model, either its vanilla 'model_from' or one from
    parity/_show_models.py (ctx as in show_model)."""
    spec = HOLD_DISPLAYS.get(display)
    if not spec:
        return False
    return bool(spec.get("model_from")) or show_model(display, romfs, ctx) is not None


def display_bounds(display, read_rows, romfs=None, ctx=None):
    """(ModelAabbMin, ModelAabbMax) for the display's ActorInfo row. It's the provided model's if there is one, else the
    ones in the row of 'model_from'. read_rows(table) -> {row id: row}."""
    m = show_model(display, romfs, ctx)
    if m:
        return tuple(m["aabb"])
    src = read_rows(ACTOR_INFO).get(HOLD_DISPLAYS[display]["model_from"]) or {}
    return src.get("ModelAabbMin"), src.get("ModelAabbMax")


def display_ops(display, read_pack, read_rows, romfs=None, ctx=None):
    """{"new_files", "packs", "byml"} plan ops that make `display` (config/hold_up.json "displays") a new actor type
    that shows an item's model and can be held up.
    - The pack is a copy of BASE_PACK, the medallion's. That's Item_EventObject_Base, the item-get event AI
      PouchContent.event.root that binds a shown item to Link's hands, a key item's pouch parameters and no physics.
      On top of that it gets the hold-up animation set and the model. The animation set is ASInfo Item_GetDemo plus
      the AnimationParam of 'anim_from' (Item_Common_Animation and the model's own), all byte copies. The model is the
      ModelInfo of 'model_from' as a byte copy, or a ModelInfo of its own from parity/_show_models.py.
    - The ActorParam is a copy of the medallion's under a new path, with those references and ASRef
      AS/Item_Common.root.asb (Rotate_GetDemo), minus the medallion's effect user and name.
    - The ActorInfo row (add_row, a copy of BASE_ROW's) gets the model's names and bounds, the AnimationResources of
      'anim_from', ActorName 'for' and the largest heaps of the rows involved. The GameActorInfo row is a copy of
      BASE_GAME_ROW's.
    read_pack(rel) -> {inner path: bytes} (vanilla), read_rows(table) -> {row id: row}. ctx is the seed's
    plan["_show_models"] (see show_model)."""
    from romtools import byml_load
    spec = HOLD_DISPLAYS[display]
    if len(display) > DISPLAY_NAME_MAX or not display.startswith(DISPLAY_PREFIX):
        raise ValueError(f"{display}: a display's name is {DISPLAY_PREFIX}... of at most {DISPLAY_NAME_MAX} characters "
                         f"(the show-item create keeps 31; OotrR crashed over 25)")
    rows = read_rows(ACTOR_INFO)
    if display in rows or display in read_rows(GAME_ACTOR_INFO):
        raise ValueError(f"{display}: the game already has an actor of that name")
    rel = f"Pack/Actor/{display}.pack.zs"
    provided = show_model(display, romfs, ctx)
    anim_from = (provided or {}).get("anim_from") or spec["anim_from"]
    if not provided and not spec.get("model_from"):
        raise ValueError(f"{display}: no model yet (parity/{SHOW_MODELS}.py has none, and no model_from)")
    arel = f"Pack/Actor/{anim_from}.pack.zs"
    afiles = read_pack(arel)
    anim = (_chain_comps(afiles, anim_from).get("AnimationRef") or "").lstrip("?")
    if anim not in afiles:
        raise ValueError(f"{arel}: no AnimationParam {anim!r}")
    names = [r.get("ModelProjectName") for r in (byml_load(afiles[anim])[0].get("AnimationResources") or [])]
    if "Item_Common_Animation" not in names:
        raise ValueError(f"{arel}: {anim} doesn't name Item_Common_Animation (Rotate_GetDemo's animation)")
    base = read_pack(BASE_PACK)
    if BASE_PARAM not in base or BASE_MODELINFO not in base:
        raise ValueError(f"{BASE_PACK}: no {BASE_PARAM} / {BASE_MODELINFO} any more")
    note = f"{display}: the hold-up/look display of {spec.get('for') or display} (config/hold_up.json displays)"
    new_files = [{"to": rel, "from": BASE_PACK, "note": note}]
    packs = [{"pack": rel, "file": GET_DEMO_ASINFO, "from_pack": GET_DEMO_ASINFO_PACK},
             {"pack": rel, "file": anim, "from_pack": arel}]
    if provided:
        new_files += list(provided.get("new_files") or [])
        model = f"Component/ModelInfo/{display}.engine__component__ModelInfo.bgyml"
        mi = provided["modelinfo"]
        packs.append({"pack": rel, "file": model, "new_from": BASE_MODELINFO,
                      "set": {k: mi[k] for k in ("FmdbName", "ModelProjectName")}})
        model_keys = {"ModelProjectName": mi["ModelProjectName"], "FmdbName": mi["FmdbName"]}
    else:
        mrel = f"Pack/Actor/{spec['model_from']}.pack.zs"
        mfiles = read_pack(mrel)
        model = (_chain_comps(mfiles, spec["model_from"]).get("ModelInfoRef") or "").lstrip("?")
        if model not in mfiles:
            raise ValueError(f"{mrel}: no ModelInfo {model!r}")
        if model != BASE_MODELINFO:
            packs.append({"pack": rel, "file": model, "from_pack": mrel})
        mrow = rows[spec["model_from"]]
        model_keys = {k: mrow[k] for k in ("ModelProjectName", "FmdbName") if k in mrow}
    packs.append({"pack": rel, "file": f"Actor/{display}.engine__actor__ActorParam.bgyml", "new_from": BASE_PARAM,
                  "set": {"Components.ModelInfoRef": "?" + model, "Components.ASRef": "?" + ITEM_COMMON_AS,
                          "Components.ASInfoRef": "?" + GET_DEMO_ASINFO, "Components.AnimationRef": "?" + anim},
                  "remove": [f"Components.{c}" for c in BASE_DROP]})
    lo, hi = display_bounds(display, read_rows, romfs, ctx)
    # A provided model can name a "heap_from", the actor whose instance of that model the game sizes. A soul figure's
    # Hall of Fallen Foes actor is one, since its skeleton and materials need those heaps.
    involved = [rows[a] for a in (BASE_ROW, spec.get("model_from"), anim_from, spec.get("for"),
                                  (provided or {}).get("heap_from")) if a in rows]
    sets = dict(model_keys, __RowId=display, ActorName=spec.get("for") or display, ModelAabbMin=lo, ModelAabbMax=hi,
                AnimationResources=[dict(r) for r in (rows[anim_from].get("AnimationResources")
                                                      or [{"ModelProjectName": n} for n in names])])
    for k in HEAPS:
        sets[k] = max(int(r.get(k) or 0) for r in involved)
    byml = [{"file": ACTOR_INFO, "add_row": {"copy_of": BASE_ROW, "set": sets}, "note": note},
            {"file": GAME_ACTOR_INFO, "add_row": {"copy_of": BASE_GAME_ROW, "set": {"__RowId": display}}}]
    return {"new_files": new_files, "packs": packs, "byml": byml}


def own_model_ops(actors, read_pack, read_rows, romfs=None):
    """{"new_files", "packs", "byml"} that give each "own" actor of config/hold_up.json in `actors` its model from
    parity/_show_models.py, when its 'model_key' has one there (the songs' note models).
    That's a ModelInfo of its own in its pack, the ModelInfoRef in its ActorParam, and the model names and bounds in
    its ActorInfo row. It's done on the item actor itself, so chests (which show their content actor), ground looks and
    the hold-up all show it. read_rows is unused (the row is edited by path)."""
    out = {"new_files": [], "packs": [], "byml": []}
    sets = {}
    for actor in sorted(a for a in actors if (HOLD_OWN.get(a) or {}).get("model_key")):
        key = HOLD_OWN[actor]["model_key"]
        m = show_model(key, romfs)
        if not m:
            continue
        rel = f"Pack/Actor/{actor}.pack.zs"
        files = read_pack(rel)
        param = f"Actor/{actor}.engine__actor__ActorParam.bgyml"
        old = (_chain_comps(files, actor).get("ModelInfoRef") or "").lstrip("?")
        if old not in files:
            raise ValueError(f"{rel}: no ModelInfo {old!r} to copy")
        model = f"Component/ModelInfo/{key}.engine__component__ModelInfo.bgyml"
        mi = m["modelinfo"]
        out["new_files"] += list(m.get("new_files") or [])
        out["packs"].append({"pack": rel, "file": model, "new_from": old,
                             "set": {k: mi[k] for k in ("FmdbName", "ModelProjectName")},
                             "note": f"{actor}: model {mi['ModelProjectName']} (parity/{SHOW_MODELS}.py)"})
        out["packs"].append({"pack": rel, "file": param, "set": {"Components.ModelInfoRef": "?" + model}})
        lo, hi = m["aabb"]
        for k, v in (("ModelProjectName", mi["ModelProjectName"]), ("FmdbName", mi["FmdbName"]),
                     ("ModelAabbMin", lo), ("ModelAabbMax", hi)):
            sets[f"[__RowId={actor}].{k}"] = v
    if sets:
        out["byml"].append({"file": ACTOR_INFO, "set": sets, "note": "own-route models (parity/_show_models.py)"})
    return out


def hold_up_ops(actors, read_pack, read_rows, romfs=None):
    """Plan "packs" and "byml" ops that give each "own" actor of config/hold_up.json in `actors` the hold-up animation.
    This is NX2-ZOOTR's song route, in game.
    - Its ActorParam gets ASInfoRef Item_GetDemo (no auto-play), ASRef AS/Item_Common.root.asb (Rotate_GetDemo,
      Pose_GetDemo...) and, as AnimationRef, the AnimationParam of its "anim_from" actor (Item_Common_Animation and the
      model's own). Those two files are byte copies under their own paths, since every pack holding a path holds the
      same bytes.
    - Its ActorInfo row gets the AnimationResources of the "anim_from" row and the heaps of its "heap_from" actor.
    An actor whose 'model_key' has a model in parity/_show_models.py (the songs' notes, own_model_ops) takes that
    model's animation set instead ('anim_from' of the model). Its poses leave the model's Skl_Root as built, and a
    rupee's would shift it.
    read_pack(rel) -> {inner path: bytes} (vanilla), read_rows() -> {row id: ActorInfo row}."""
    from romtools import byml_load
    packs, sets = [], {}
    rows = read_rows()
    for actor in sorted(a for a in actors if a in HOLD_OWN):
        spec = HOLD_OWN[actor]
        rel = f"Pack/Actor/{actor}.pack.zs"
        own = read_pack(rel)
        param = f"Actor/{actor}.engine__actor__ActorParam.bgyml"
        comps = byml_load(own[param])[0].get("Components") or {}
        if comps.get("ASRef") or comps.get("AnimationRef") or comps.get("ASInfoRef"):
            raise ValueError(f"{rel}: {actor} has its own animation components now: re-check config/hold_up.json")
        provided = show_model(spec["model_key"], romfs) if spec.get("model_key") else None
        anim_from = (provided or {}).get("anim_from") or spec["anim_from"]
        src_rel = f"Pack/Actor/{anim_from}.pack.zs"
        src = read_pack(src_rel)
        anim = (_chain_comps(src, anim_from).get("AnimationRef") or "").lstrip("?")
        if anim not in src:
            raise ValueError(f"{src_rel}: no AnimationParam {anim!r} of its own")
        packs.append({"pack": rel, "file": GET_DEMO_ASINFO, "from_pack": GET_DEMO_ASINFO_PACK,
                      "note": f"{actor}: hold-up animation (config/hold_up.json own)"})
        packs.append({"pack": rel, "file": anim, "from_pack": src_rel})
        # The ActorParam in every pack holding it. Item_StickBag_Small's is the parent of the medium and large
        # bags' ones, and those set these three components themselves.
        packs.append({"pack": "*", "file": param, "set": {"Components.ASInfoRef": "?" + GET_DEMO_ASINFO,
                                                         "Components.ASRef": "?" + ITEM_COMMON_AS,
                                                         "Components.AnimationRef": "?" + anim}})
        mine, big = rows[actor], rows[spec["heap_from"]]
        # The ActorInfo row lists the animation banks too. Every holdable vanilla item has Item_Common_Animation
        # there.
        sets[f"[__RowId={actor}].AnimationResources"] = [dict(r) for r in rows[anim_from]["AnimationResources"]]
        for k in HEAPS:
            if int(big.get(k) or 0) > int(mine.get(k) or 0):
                sets[f"[__RowId={actor}].{k}"] = int(big[k])
    byml = [{"file": ACTOR_INFO, "set": sets, "note": "hold-up animation: heaps of a holdable item"}] if sets else []
    return packs, byml


def owned_by(tier):
    """Pouch actors whose presence means `tier` is owned, in query order."""
    return list(OWNED.get(tier) or [tier])

# Scene file (and the scene ID whose settings a reused ID copies) for each chest type.
CHEST_SCENE_FILE = {"small": "Dm_SY_TreasureboxSmall", "big": "Dm_SY_Treasurebox"}
SMALL_CHESTS = ("Obj_TBox_A_01", "Obj_TBox_A_01_NoBake")
BIG_CHESTS = ("Obj_TBox_A_02", "Obj_TBox_A_02_NoBake")


def chest_type(actor):
    return "small" if actor in SMALL_CHESTS else "big" if actor in BIG_CHESTS else None


# Chest types that open like a small or a big chest, so a chest scene built for that size runs on them. The ActorParam
# of Obj_TBox_GlassTruth_A_01 inherits Obj_TBox_A_01's and Obj_TBox_A_03's inherits Obj_TBox_A_02's, so they have
# the same AI, opening and default scene.
# The fill puts progressive items in every chest of these families, Lens and boss-key chests too. chest_type stays the
# narrower list of just the plain small and big chests.
SCENE_FAMILY = {"Obj_TBox_A_01": "small", "Obj_TBox_A_01_NoBake": "small", "Obj_TBox_GlassTruth_A_01": "small",
                "Obj_TBox_A_02": "big", "Obj_TBox_A_02_NoBake": "big", "Obj_TBox_A_03": "big",
                "Obj_TBox_A_03_NoBake": "big"}


def scene_family(actor):
    """"small" or "big", whichever chest scenes run on this chest type, or None."""
    return SCENE_FAMILY.get(actor)
YES, NO = 0, 1  # query answers

GET_ROUTINE = "Dm_SY_GetInEvent:GetInEvent_NotLookatObjectTurnOff"


def entry_name(item, chest):
    return "Rando_" + "".join(w for w in item.title().split() if w.isalnum()) + "_" + chest


def _owned_query(n, j, tier, yes, no):
    """Query nodes for "is tier owned?" (has{j}, then has{j}_{i} for each further actor of owned_by(tier))."""
    actors = owned_by(tier)
    for i, actor in enumerate(actors):
        label = f"has{j}" if i == 0 else f"has{j}_{i}"
        n[label] = {"actor": "PouchSystemActor", "query": "EventQueryIsExistInPouch",
                    "params": {"Actor": actor, "Num": 1},
                    "cases": {YES: yes, NO: f"has{j}_{i + 1}" if i + 1 < len(actors) else no}}


def _tier_checks(n, tiers, give):
    """Branches on what the player owns, highest tier first. Owning tier k (or above) gives tier k+1, and the top tier
    repeats. give(k) is the label that gives tier k."""
    top = len(tiers) - 1
    order = list(range(top, -1, -1))
    for j, k in enumerate(order):
        _owned_query(n, j, tiers[k], give(min(k + 1, top)), f"has{j + 1}" if j + 1 < len(order) else give(0))
    return "has0"


def clone(fc, start, prefix, stop):
    """Nodes copying the vanilla steps reachable from event `start` (by name) in flowchart model `fc`.
    Each one is a "copy" of the original (same actor, action, parameter block) and the routing stays inside the copy.
    Routing to an event named in `stop` goes to stop[name] instead, which is a label or None for the end.
    Returns (nodes, start label)."""
    events = fc["events"]
    by_name = {e["name"]: e for e in events}
    nodes, queue, seen = {}, [], set()

    def lab(i):
        if i >= len(events):
            return None
        name = events[i]["name"]
        if name in stop:
            return stop[name]
        if i not in seen:
            seen.add(i)
            queue.append(i)
        return prefix + name

    first = lab(by_name[start]["idx"])
    while queue:
        e = events[queue.pop(0)]
        node = {"copy": e["name"]}
        if e["type"] in ("action", "subflow", "join"):
            node["next"] = lab(e["next"])
        elif e["type"] == "switch":
            node["cases"] = {c["value"]: lab(c["next"]) for c in e["cases"]}
        elif e["type"] == "fork":
            node["fork"] = [lab(x) for x in e["forks"]]
            node["join"] = lab(e["join"])
        else:
            raise ValueError(f"cannot copy a {e['type']} step ({e['name']})")
        nodes[prefix + e["name"]] = node
    return nodes, first


def show_item_nodes(item, next_label, display=None):
    """The big chest's way of showing its contents, for a named item.
    The item model rotates above Link using Dm_SY_GetInEvent:Item_Position's own steps, minus its fanfare because the
    big chest already plays one. Link's hold-up pose comes from the chest's opening animation, so no second get
    animation plays. `display` is the actor shown (an item Link can't hold up shows its stand-in, config/hold_up.json
    "show"). The glow names the item."""
    return {
        "show": {"actor": "Player_Event", "action": "EventCreateShowItemFromActorFileName",
                 "params": {"IsWaitEnd": True, "Actor": display or item}, "next": "showlod"},
        "showlod": {"actor": "Player_Event", "action": "EventTriggerSetModelLodManual", "params": {"LodLevel": 0},
                    "next": "showfire"},
        "showfire": {"actor": "Player_Event", "action": "EventIgnitionShowItem",
                     "params": {"IsWaitEnd": True, "ItemPos": [0.0, 0.0, 0.0], "IsScale": False, "CreateTime": 0.0,
                                "IsInvalidateShadow": True, "IsAsPlay": True, "ASCommand": "Rotate_GetDemo"},
                     "next": "showglow"},
        "showglow": {"actor": "EventEffectEmitter", "action": "EventEffectStartGetItem",
                     "params": {"GameDataName": "", "ActorName": item, "IsBottleDemo": False}, "next": next_label},
    }


def big_chest_graphs(entry, tiers, model):
    """Graphs for EvflBuilder.add_graph: the big-chest "give the right tier" scene in Dm_SY_Treasurebox.
    It follows the vanilla big chest (Success_) step for step, for the tier decided when the chest opens:
    - the chest's fanfare, with its suspense intro
    - its whole opening cinematic (Success_PlayerPerform: camera, Link's lift and hold-up pose, the lid via
      Process_Treasurebox, the suspense wait, rumbles, Navi)
    - the item shown above Link where the chest would show its own contents (call :Item_Rotation can only show the
      chest's stand-in)
    - the 90-frame wait
    - the item added with its message the way a big chest adds it (GetPouchContentByActorNameForTreasureBox)
    Calling the in-place get routine at the show step doesn't work. It plays a second fanfare and hold-up after the
    chest's own, and it looks like a hiccup."""
    fc = model.flowcharts[0]
    graphs, n = [], {}
    start = _tier_checks(n, tiers, lambda k: f"fanfare{k}")
    for k, item in enumerate(tiers):
        perform = f"{entry}_perform{k}"
        # Process_Treasurebox, then the item shown above Link. An item Link can't hold up shows its display stand-in
        # (config/hold_up.json "show"). One with no holdable model ("window") shows nothing and the branch ends there.
        shown = item not in HOLD_WINDOW
        proc, proc_start = clone(fc, "Event14", f"p{k}_", {"Event9": "show" if shown else None})
        pp, pp_start = clone(fc, "Event37", f"pp{k}_", {"Event28": proc_start, "Event5": proc_start})  # PlayerPerform
        nodes = dict(pp)
        nodes.update(proc)
        if shown:
            nodes.update(show_item_nodes(item, None, show_of(item)))
        graphs.append((perform, nodes, pp_start))
        # Success_ Event29, the big chest's fanfare with its suspense intro, for the tier given
        n[f"fanfare{k}"] = {"actor": "SoundSystemActor", "action": "EventTriggerSoundStartFanfare",
                            "params": {"IsEnableIntro": True, "GameDataName": "", "ActorName": item},
                            "next": f"perform{k}"}
        n[f"perform{k}"] = {"call": f":{perform}", "params": {"ContentName": {"arg": "ContentName"}},
                            "next": f"wait90_{k}"}
        n[f"wait90_{k}"] = {"copy": "Event45", "next": f"add{k}"}  # Success_ Event45
        if item in NO_POSE:  # the ocarinas
            # The get window and the vanilla ocarina's silent add, with IsGetEvent False like Dm_Kokiri_0155 Event68
            # (the chest's own add sets it). Then the "after" call (equipment sync and the action guide), then the
            # display put away.
            n[f"add{k}"] = {"call": WINDOW_GIVE, "params": {"ActorName": GIVE[item].get("add", item)},
                            "next": after_nodes(n, item, f"after{k}", "hide" if shown else "wait1")}
            continue
        n[f"add{k}"] = {"call": "GetPouchContent:GetPouchContentByActorNameForTreasureBox",
                        "params": {"ActorName": (GIVE.get(item) or {}).get("add", item)},
                        "next": "hide" if shown else "wait1"}
    if any(item not in HOLD_WINDOW for item in tiers):
        n["hide"] = {"actor": "Player_Event", "action": "EventDeleteShowItem",
                     "params": {"IsWaitEnd": True, "IsFadeOut": False, "IsScaleOut": False,
                                "ChangeVisibleOffWithRequestDelete": False}, "next": "wait1"}
    # End like Success_Leave. Mark the chest open, release the pause, then save.
    n["wait1"] = {"actor": "GameSystemActor", "action": "EventWait", "params": {"Frames": 1, "IsWaitEnd": True},
                  "next": "markopened"}
    n["markopened"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTreasureBoxOpened", "next": "unpause"}
    n["unpause"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTBoxErasePauseMask", "next": "save"}
    n["save"] = {"actor": "GameSystemActor", "action": "EventTriggerRequestAutoSave", "next": "glowoff"}
    n["glowoff"] = {"actor": "EventEffectEmitter", "action": "EventEffectStopGetItem", "next": None}
    # First the chest's own content display (the first tier it holds) gets deleted, like the Treasure Chest Game does
    # before its chests' scene, so the cinematic shows the tier given.
    n["delc"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTBoxRequestDeleteContentDisplay",
                 "next": start}
    graphs.append((entry, n, "delc"))
    return graphs


def chest_graphs(name, chest, model=None):
    """[(entry point, nodes, start)] to add for a progressive item's chest scene; the last one is the scene."""
    entry, tiers = entry_name(name, chest), PROGRESSIVE[name]["tiers"]
    if chest == "big":
        return big_chest_graphs(entry, tiers, model)
    nodes, start = chest_scene(tiers, chest)
    return [(entry, nodes, start)]


def _open_pose(command):
    return {"actor": "Player_Event", "action": "EventPlayerPlayASForFlowchart", "next": None,
            "params": {"KeepOneTimeAnm": False, "ForceFadeFrame": -1.0, "IsWaitEnd": True, "ASCommand": command,
                       "IsAllSlot": True, "UseAnmDriven": True, "ClothWarpMode": 0}}


def chest_scene(tiers, chest="small"):
    """(nodes, start) for EvflBuilder.add_graph: the small-chest "give the right tier" scene."""
    if chest != "small":
        raise ValueError("only small chests have a progressive scene so far")
    n = {}
    # 1. the chest's own opening (Dm_SY_TreasureboxSmall Open: Event50, Event15/Event52, Event51/Event4)
    n["face"] = {"actor": "TreasureBox_EventStarter", "query": "EventQueryIsFaceToFace",
                 "params": {"ActorName": "Player_Event"}, "cases": {YES: "front", NO: "kick"}}
    for side, pose, rumble in (("front", "DemoOpenTreasureBoxFront", ":FrontVibration"),
                               ("kick", "DemoOpenTreasureBoxWithKick", ":KickVibration")):
        n[side] = {"fork": [f"pose_{side}", f"lid_{side}", f"rumble_{side}"], "join": f"opened_{side}"}
        n[f"pose_{side}"] = _open_pose(pose)
        n[f"lid_{side}"] = {"call": ":TresureboxSmall_Animation", "next": None}
        n[f"rumble_{side}"] = {"call": rumble, "next": None}
        n[f"opened_{side}"] = {"join": True, "next": "has0"}
    # First the chest's own content display (the first tier it holds) gets deleted, like the Treasure Chest Game does
    # before its chests' scene. That way what rises is the tier given, with its hold-up.
    n["delc"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTBoxRequestDeleteContentDisplay",
                 "next": "face"}
    # 2. highest tier owned decides: owning tier k (or above) gives tier k+1; the top tier repeats
    _tier_checks(n, tiers, lambda k: f"give{k}")
    # 3. the game's own in-cutscene get (hold up, message, add to the inventory, put away). A tier with its own give
    #    entry uses that entry, and one Link can't hold up gets its stand-in's hold-up or the window
    #    (config/hold_up.json).
    for k, item in enumerate(tiers):
        n[f"give{k}"] = (give_node(item, "wait1") if item in GIVE else hold_node(item, "wait1") or
                         {"call": GET_ROUTINE, "params": {"ActorName": item}, "next": "wait1"})
    # 4. as Dm_SY_TreasureboxSmall Success_ ends: mark opened, release the pause, save
    n["wait1"] = {"actor": "GameSystemActor", "action": "EventWait", "params": {"Frames": 1, "IsWaitEnd": True},
                  "next": "markopened"}
    n["markopened"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTreasureBoxOpened", "next": "unpause"}
    n["unpause"] = {"actor": "TreasureBox_EventStarter", "action": "EventTriggerTBoxErasePauseMask", "next": "save"}
    n["save"] = {"actor": "GameSystemActor", "action": "EventTriggerRequestAutoSave", "next": None}
    return n, "delc"


# Scene rewards (NPC, song, cutscene)
# A scene gives its item in one step. That's a call to a give routine (Dm_SY_GetInEvent:GetInEvent...,
# GetPouchContent:GetPouchContentByActorName, NpcCommon hand-overs) or a PouchSystemActor add. For a progressive item
# we replace that step the chest way: check what the player owns, highest tier first, then run the same step with the
# right tier.
#  - "inplace": the giver's flowchart has a PouchSystemActor, so the new steps go there. Each tier is a copy of the
#    give step with every parameter kept except the item (camera, NPC and animation arguments stay as they were).
#  - "host": there's no PouchSystemActor there, but the step calls a give routine with nothing but the item. The
#    checks go in a new entry next to that routine (its file has a PouchSystemActor) and the giver calls that entry.
# The steps that led to the give step get pointed at the replacement.
HOSTS = ("GetPouchContent", "Dm_SY_GetInEvent")


def scene_give_mode(fc, event, param):
    """"inplace", "host" or None (no progressive replacement possible) for give step `event` (evfl model)."""
    if any(a["name"] == "PouchSystemActor" and not a["sub_name"] for a in fc["actors"]):
        if event["type"] in ("action", "subflow"):
            return "inplace"
        return None
    items = (event.get("params") or {}).get("items", {})
    if event["type"] == "subflow" and (event.get("flowchart") or "") in HOSTS and set(items) == {param}:
        return "host"
    return None


DISPLAY_ROUTINES = ("GetPouchContent:DisplayGetByActorName", "GetPouchContent:DisplayRutoGetByActorName")


def _owned_checks(n, tiers, give):
    """Branches showing the tier the player owns (highest first), tier 0 if none. It's for a step that only shows the
    item after the scene's add step already gave it."""
    top = len(tiers) - 1
    order = list(range(top, -1, -1))
    for j, k in enumerate(order):
        _owned_query(n, j, tiers[k], give(k), f"has{j + 1}" if j + 1 < len(order) else give(0))
    return "has0"


def reachable(fc, start, goal):
    """Whether step index `goal` can run after step index `start` in flowchart model fc."""
    events, seen, todo = fc["events"], set(), [start]
    while todo:
        i = todo.pop()
        if i in seen or i >= len(events):
            continue
        seen.add(i)
        e = events[i]
        nxt = [e.get("next"), e.get("join")] + [c["next"] for c in e.get("cases", [])] + list(e.get("forks", []))
        for j in nxt:
            if j is not None and j < len(events):
                if j == goal:
                    return True
                todo.append(j)
    return False


def host_entry(item, routine, owned=False):
    return ("Rando_" + "".join(w for w in item.title().split() if w.isalnum()) + "_" + routine
            + ("_Owned" if owned else ""))


def host_graph(tiers, routine, param, owned=False, host=NO_POSE_FILE):
    """Nodes for the host entry: the checks, then the routine (same file, `host`) with the tier.
    A tier with its own give entry calls that entry instead, except in two cases where it's the routine and then the
    tier's "after" call (the ocarina's action guide). One is when the routine only shows the item (display). The other
    is when the tier is only kept from the hold-up (NO_POSE) and the routines in `host` never pose (GetPouchContent)."""
    n = {}
    start = (_owned_checks if owned else _tier_checks)(n, tiers, lambda k: f"give{k}")
    display = routine in {r.split(":")[1] for r in DISPLAY_ROUTINES}
    pose_free = display or host in POSE_FREE_FILES
    for k, t in enumerate(tiers):
        if t in GIVE and not display and not (t in NO_POSE and host in POSE_FREE_FILES):
            node = give_node(t, None)  # a tier the routine can't hand over (by name, or without the hold-up)
            f, _, e = node["call"].partition(":")
            if f == host and t in NO_POSE:
                node["call"] = f":{e}"  # an entry in this same file, called the way vanilla calls its own entries
            n[f"give{k}"] = node
        elif not pose_free and hold_node(t, None, host):  # a tier Link can't hold up (config/hold_up.json)
            n[f"give{k}"] = hold_node(t, None, host)
        else:
            n[f"give{k}"] = {"call": f":{routine}", "params": {param: t},
                             "next": after_nodes(n, t, f"after{k}", None)}
    return n, start


def inplace_graph(tiers, give_event, param, after, owned=False, pose_free=True, last=True):
    """Nodes for the giver's flowchart: the checks, then give step `give_event` copied per tier. `after` is the name of
    the step the give step led to (None means the end).
    For a tier that's never held up (NO_POSE), a step that may pose becomes a call to the tier's give entry. A step may
    pose when pose_free is False, which is any call outside GetPouchContent or any action that isn't a PouchSystemActor
    one. A pose-free step is copied, followed by the tier's "after" call when it's the location's last give step
    (`last`)."""
    n = {}
    start = (_owned_checks if owned else _tier_checks)(n, tiers, lambda k: f"give{k}")
    for k, t in enumerate(tiers):
        nxt = f"@{after}" if after else None
        if t in NO_POSE and not pose_free:
            n[f"give{k}"] = give_node(t, nxt)
            continue
        if not pose_free and hold_node(t, nxt):  # a tier Link can't hold up (config/hold_up.json)
            n[f"give{k}"] = hold_node(t, nxt)
            continue
        if t in GIVE and t not in NO_POSE and not owned:  # the generator keeps such items away from in-place steps
            raise ValueError(f"{t} can't be handed over by a copy of {give_event}: it needs {GIVE[t]['call']}")
        if last:
            nxt = after_nodes(n, t, f"after{k}", nxt)
        n[f"give{k}"] = {"copy": give_event, "params_over": {param: t}, "next": nxt}
    return n, start


def step_pose_free(fc, event):
    """Whether give step `event` (an evfl model step of flowchart model `fc`) can never make Link hold the item up.
    That's a PouchSystemActor action (a silent add) or a call into a file whose routines never pose
    (GetPouchContent)."""
    if event["type"] == "action":
        return fc["actors"][event["actor"]]["name"] == "PouchSystemActor"
    if event["type"] in ("subflow", "subflow_switch"):
        return (event.get("flowchart") or fc["name"]) in POSE_FREE_FILES
    return False


def predecessors(fc, event):
    """Routing edits pointing everything that leads to `event` elsewhere: [(kind, step or entry name, index)]."""
    i, out = event["idx"], []
    for e in fc["events"]:
        if "next" in e and e["next"] == i:
            out.append(("next", e["name"], None))
        for k, c in enumerate(e.get("cases", [])):
            if c["next"] == i:
                out.append(("case", e["name"], k))
        for k, f in enumerate(e.get("forks", [])):
            if f == i:
                out.append(("fork", e["name"], k))
    for name, ep in fc["entry_points"].items():
        if ep["main"] == i:
            out.append(("entry", name, None))
    return out
