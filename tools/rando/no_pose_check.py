"""Read a built patch back: no hold-up shows an actor without a working hold-up animation (the game would freeze), and
every ocarina give syncs Link's equipment and opens the ocarina's action guide.

usage: python tools/rando/no_pose_check.py OUT_DIR [ROMFS]     (tools/rando/in_game_check.py runs it too)

How it reads the game, independent of the code that wrote the patch:
- Holdable: an actor whose ActorParam chain (read from the patched pack, else the vanilla one) has an ASRef whose AS
  file (loose AS/<n>.root.asb.zs, or in Pack/Bootup) holds the command Rotate_GetDemo, the one Link's item-get pose
  waits for (Dm_SY_GetInEvent Item_Position Event51). Without it the hold-up never ends (NX2-ZOOTR in game).
- A hold-up is a step creating the item Link holds: Player_Event.EventCreateShowItemFromActorFileName or
  EventCreateShowItem. Its Actor is a constant or an argument of the entry it sits in. An entry "poses with
  argument X" when it reaches such a step with Actor X, directly or through calls passing X on
  (tools/progressive.py pose_args, over the patched and vanilla files).
- Every step of every patched event file is checked. A problem is a hold-up step whose constant Actor isn't
  holdable, a call passing a constant actor that isn't holdable to an argument its callee poses with, a big chest's
  own item display (Dm_SY_Treasurebox Item_Rotation / DisplayContent) called with an ocarina, or a new step naming
  an ocarina in an action outside the known pose-free ones (the pouch, the fanfare, the get glow, the Zelda Notes
  screenshot).
- Every new step giving an ocarina (a PouchSystemActor add, a GetPouchContent call, a call of the ocarina's give
  entry) must reach the tier's "after" entry later (equipment sync, then the action guide), or sit inside an entry
  that does.
- Chests holding an ocarina (a progressive chest's hidden first tier) must play a scene of their own. The vanilla
  opening shows its contents without waiting, so it's not a freeze, but NX2 saw an invisible ocarina.
- The shown actor must exist when the ignition comes. In game with test_guardroom, the Ocarina, both Triforce
  pieces and the Master Sword crashed. Player_Event.EventIgnitionShowItem runs the Player's event-AI node
  OneShotShowItemInvalidateShadow (fn 0x82963040), which reads the ShowItem slot's actor without a null check
  (0x80994de0 reads actor+0x270, the null read at guest 0x270), and the create step before it reports done
  whether or not it made an actor. So a hold-up's actor is a problem when:
  - its name is over SHOW_NAME_MAX (31) characters: the create copies the name into a 32-byte string (m+0x826ca854)
    and asks for an actor that doesn't exist (Obj_Gerudo_HorsebackArcheryTarget_A_02 / _A_03, 38 characters);
  - it is a menu display (Pouch_Item_Base: the pouch menu's Pouch_Ocarina_*, the quest menu's *_ImportantMenu),
    with no ModelBind and a menu AI of its own (the Ocarina's crashed, the Kokiri Emerald's showed nothing);
  - it has no ModelBind component, or no ActorInfo / GameActorInfo row in the patched tables. Every actor vanilla
    holds up has a ModelBind (Item_EventObject_Base, Shop_Item_Base, Obj_Item_Base, the weapons), it binds the
    shown item to Link's hands;
  - it is new (no vanilla ActorInfo row: our display actors) and its name is over progressive.DISPLAY_NAME_MAX (25).
"""
import functools
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()
SHOW = ("EventCreateShowItemFromActorFileName", "EventCreateShowItem")
# actions that may name an ocarina without showing it held (the vanilla ocarina gives use the pouch ones)
SAFE_ACTIONS = {("PouchSystemActor", None), ("SoundSystemActor", "EventTriggerSoundStartFanfare"),
                ("EventEffectEmitter", "EventEffectStartGetItem"), ("EventEffectEmitter", "EventEffectStopGetItem"),
                ("GameSystemActor", "EventTriggerZeldaNotesRequestSendDailyScreenShot"),
                ("UISystemActor", "EventTriggerRequestOpenPickUpWindow"),
                ("GameDataActor", None)}  # (string compares and sets, e.g. a scrub's Shop_SelectItemName)
BIG_DISPLAY = {("Dm_SY_Treasurebox", "Item_Rotation"), ("Dm_SY_Treasurebox", "DisplayContent"),
               ("Dm_SY_TreasureboxSmall", "ItemDisplay"), ("Dm_SY_TreasureboxSmall", "Pack_ItemDisplay"),
               ("Dm_SY_TreasureboxSmall", "ItemDisplayNoSpace"), ("Dm_SY_TreasureboxSmall", "Pack_ItemDisplayNoSpace")}
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
BOOTUP = "Pack/Bootup.Nin_Ounce_NVN2.pack.zs"
COMMAND = b"Rotate_GetDemo"
COMMON_ANIM = "Item_Common_Animation"  # the animation bank Rotate_GetDemo plays from
BONE = b"Root"  # the bone it turns
BONE_RX = re.compile(rb"[\x01-\x40]\x00Root\x00")  # a bfres name entry: u16 length, the name, a zero
GAME_ACTOR_INFO = "RSDB/GameActorInfo.Product.111.rstbl.byml.zs"
SHOW_NAME_MAX = 31  # the show-item create's name buffer (FixedSafeString<32>, m+0x826ca854)
MENU_BASES = ("Pouch_Item_Base",)  # the pouch and quest menus' 3D items: crash or show nothing when held up
NEW_ACTOR_PREFIXES = ("Rando_",)  # actor types the patch adds (progressive.DISPLAY_PREFIX, the Triforce piece's)


def _items(e):
    return ((e.get("params") or {}).get("items")) or {}


def _successors(e):
    out = [e.get("join")] + [c["next"] for c in e.get("cases", [])] + list(e.get("forks", []))
    if e["type"] != "type6":  # a return step's field is a value
        out.append(e.get("next"))
    return [i for i in out if i is not None and i != 0xFFFF]


def _reach(fc, start):
    E, seen, todo = fc["events"], set(), [start]
    while todo:
        i = todo.pop()
        if i in seen or i >= len(E):
            continue
        seen.add(i)
        todo += _successors(E[i])
    return [E[i] for i in sorted(seen)]


class Game:
    """The game as the patch makes it (patch files over the vanilla ones)."""

    def __init__(self, patch, romfs):
        from romtools import Romfs
        self.fs = Romfs(romfs, os.path.join(HERE, "original"), [patch] if patch else [])
        self.romfs = romfs
        self.dir = os.path.join(romfs, "Event", "EventFlow")
        self.patch = patch
        self._files = sorted(os.listdir(self.dir))
        self._memo = {}

    @functools.lru_cache(maxsize=None)
    def rels(self, name):
        rx = re.compile(re.escape(name) + r"(\.(\d{3}))?\.bfevfl\.zs$")
        return [f"Event/EventFlow/{f}" for f in self._files if rx.match(f)]

    @functools.lru_cache(maxsize=None)
    def flowchart(self, name):
        """The flowchart the game reads for `name` (the newest version: X.110 over X), or None."""
        from evfl import Evfl
        rels = self.rels(name)
        if not rels:
            return None
        newest = sorted(rels, key=lambda r: int((re.search(r"\.(\d{3})\.bfevfl", r) or [0, -1])[1]))[-1]
        return Evfl(self.fs.read(newest)).flowcharts[0]

    def pose_args(self, name, entry):
        import progressive
        return progressive.pose_args(self.flowchart, name, entry, self._memo)

    def patched_files(self):
        d = os.path.join(self.patch, "Event", "EventFlow")
        return sorted(f"Event/EventFlow/{f}" for f in os.listdir(d)) if os.path.isdir(d) else []

    @functools.lru_cache(maxsize=None)
    def _bootup(self):
        from romtools import sarc_files
        return sarc_files(self.fs.read(BOOTUP))

    @functools.lru_cache(maxsize=None)
    def why_not_holdable(self, actor):
        """None if the patched game's `actor` can be held up. That needs its AS to have Rotate_GetDemo, its animation
        list to name Item_Common_Animation (where that command's animation lives) and its model to have the bone it
        turns (Root). Returns "no pack" if it has none, else the reason."""
        from romtools import sarc_files, byml_load
        import progressive
        if len(actor) > SHOW_NAME_MAX:
            return (f"its name has {len(actor)} characters: the show-item create keeps {SHOW_NAME_MAX} "
                    f"('{actor[:SHOW_NAME_MAX]}' isn't an actor), so the ignition finds no actor (null read at +0x270)")
        rel = f"Pack/Actor/{actor}.pack.zs"
        if not os.path.exists(os.path.join(self.romfs, rel)) and not (
                self.patch and os.path.exists(os.path.join(self.patch, rel))):
            return "no pack"
        files = sarc_files(self.fs.read(rel))
        comps, name, guard, chain = {}, actor, 0, []
        while name and guard < 12:
            guard += 1
            path = f"Actor/{name}.engine__actor__ActorParam.bgyml"
            if path not in files:
                break
            chain.append(name)
            p = byml_load(files[path])[0]
            for k, v in (p.get("Components") or {}).items():
                comps.setdefault(k, v)
            parent = p.get("$parent")
            name = parent.rsplit("/", 1)[-1].split(".")[0] if parent else None
        menu = [b for b in chain if b in MENU_BASES]
        if menu:
            return (f"a menu display ({menu[0]}): no ModelBind and a menu AI of its own; held up it crashes or shows "
                    f"nothing (test_guardroom: the Ocarina, the Kokiri Emerald)")
        if not (comps.get("ModelBindRef") or "").lstrip("?"):
            return "no ModelBind component: it can't be bound to Link's hands (every vanilla held item has one)"
        if actor not in self._actor_info():
            return "no ActorInfo row: the create makes nothing"
        if actor not in self._game_actor_info():
            return "no GameActorInfo row: the create makes nothing"
        if actor not in self._vanilla_rows() and len(actor) > progressive.DISPLAY_NAME_MAX:
            return f"a new actor with a {len(actor)}-character name (ours stay within {progressive.DISPLAY_NAME_MAX})"
        asref = (comps.get("ASRef") or "").lstrip("?")
        if not asref:
            return "no AS"
        if os.path.exists(os.path.join(self.romfs, asref + ".zs")) or (
                self.patch and os.path.exists(os.path.join(self.patch, asref + ".zs"))):
            data = self.fs.read(asref + ".zs")
        else:
            data = files.get(asref) or self._bootup().get(asref) or b""
        if COMMAND not in data:
            return f"{asref} has no {COMMAND.decode()}"
        anim = (comps.get("AnimationRef") or "").lstrip("?")
        res = [r.get("ModelProjectName") for r in (byml_load(files[anim])[0].get("AnimationResources") or [])] if anim in files else []
        if COMMON_ANIM not in res:
            return f"its animation list ({anim or 'none'}) has no {COMMON_ANIM}"
        row = self._actor_info().get(actor) or {}
        if COMMON_ANIM not in [r.get("ModelProjectName") for r in (row.get("AnimationResources") or [])]:
            return f"its ActorInfo row's AnimationResources have no {COMMON_ANIM}"
        info = (comps.get("ModelInfoRef") or "").lstrip("?")
        if info not in files:
            return "no ModelInfo"
        m = byml_load(files[info])[0]
        model = f"Model/{m.get('ModelProjectName')}.{m.get('FmdbName')}.bfres.zs"
        try:
            bfres = self.fs.read(model)
        except (FileNotFoundError, OSError):
            return f"no model {model}"
        if not BONE_RX.search(bfres):
            return f"its model {model} has no {BONE.decode()} bone"
        return None

    @functools.lru_cache(maxsize=None)
    def _actor_info(self):
        from romtools import byml_load
        return {r["__RowId"]: r for r in byml_load(self.fs.read(ACTOR_INFO))[0]}

    @functools.lru_cache(maxsize=None)
    def _game_actor_info(self):
        from romtools import byml_load
        return {r["__RowId"] for r in byml_load(self.fs.read(GAME_ACTOR_INFO))[0]}

    @functools.lru_cache(maxsize=None)
    def _vanilla_rows(self):
        from romtools import Romfs, byml_load
        fs = Romfs(self.romfs, os.path.join(HERE, "original"))
        return {r["__RowId"] for r in byml_load(fs.read(ACTOR_INFO))[0]}

    def holdable(self, actor):
        """True / False, or None for a vanilla name with no pack (an argument value that names no actor). A name the
        game doesn't know at all (no pack, no vanilla row: a display of ours the patch failed to build) is False."""
        why = self.why_not_holdable(actor)
        if why == "no pack":
            return None if actor in self._vanilla_rows() or not actor.startswith(NEW_ACTOR_PREFIXES) else False
        return why is None


def _const(v):
    return v["value"] if v is not None and v.get("type") != "argument" else None


def _calls_after(game, fc, name, start_idx, after_calls, seen_entries=None):
    """Whether a call to one of `after_calls` ("File:Entry") runs after step `start_idx` (its successors, and
    inside the entries they call)."""
    seen_entries = seen_entries if seen_entries is not None else set()
    for e in _reach(fc, start_idx):
        if e["type"] in ("subflow", "subflow_switch"):
            callee = e.get("flowchart") or name
            if f"{callee}:{e['entry_point']}" in after_calls:
                return True
            key = (callee, e["entry_point"])
            if key in seen_entries:
                continue
            seen_entries.add(key)
            cfc = game.flowchart(callee)
            if cfc is not None and e["entry_point"] in cfc["entry_points"] and _calls_after(
                    game, cfc, callee, cfc["entry_points"][e["entry_point"]]["main"], after_calls, seen_entries):
                return True
    return False


def _intercepted(game, callee, entry, arg, value):
    """Whether the patched `callee`:`entry` gives `value` (passed as `arg`) itself before its vanilla hand-over. That's
    the scrubs' one-time sale with make_patch's intercept (tools/progressive.py scrub_intercept) comparing it, and
    every step that led to the vanilla hand-over now leading to the intercept."""
    import progressive
    if (callee, entry, arg) != (progressive.SCRUB_FILE, progressive.SCRUB_SALE_SRC, "ActorName"):
        return False
    fc = game.flowchart(callee)
    names = {e["name"]: e for e in fc["events"]}
    start = names.get(f"{progressive.SCRUB_INTERCEPT}_set")
    hand = names.get(progressive.SCRUB_HANDOVER)
    if start is None or hand is None:
        return False
    compares = any(e["name"].startswith(f"{progressive.SCRUB_INTERCEPT}_is") and _const(_items(e).get("Value")) == value
                   for e in fc["events"])
    reach = {e["idx"] for e in _reach(fc, fc["entry_points"][entry]["main"])}
    # the vanilla hand-over is reached only through the intercept's no-match branch
    direct = any(hand["idx"] in _successors(e) for e in fc["events"]
                 if e["idx"] in reach and not e["name"].startswith(progressive.SCRUB_INTERCEPT + "_"))
    return compares and start["idx"] in reach and not direct


def _unbound_actors(fc, rel, van_names, stats):
    """A flowchart actor bound by an argument belongs to one entry (its entry_point_idx), so a new step using it must
    run in that entry, reached from that entry's start. Otherwise the game hangs (OotrR saw it: a copied scrub sale named
    the scrub actor its new entry never bound)."""
    out = []
    eps = list(fc["entry_points"])
    reach = {}
    for ai, a in enumerate(fc["actors"]):
        if not a.get("argument") or a.get("entry_point_idx", 0xFFFF) >= len(eps):
            continue
        ep = eps[a["entry_point_idx"]]
        if ep not in reach:
            reach[ep] = {e["idx"] for e in _reach(fc, fc["entry_points"][ep]["main"])}
        for e in fc["events"]:
            if e["type"] in ("action", "switch") and e["actor"] == ai and e["name"] not in van_names:
                stats["bound"] += 1
                if e["idx"] not in reach[ep]:
                    out.append(f"{rel} {e['name']}: uses {a['name']}[{a['sub_name']}], bound only in entry {ep}, "
                               f"which never reaches it (the actor is unbound there: the game hangs)")
    return out


def verify(patch, romfs=DEFAULT_ROMFS):
    """([problem], {stats}) for a built patch directory."""
    import progressive
    from evfl import Evfl
    from romtools import byml_load
    tiers = sorted(progressive.NO_POSE)
    after_calls = {(progressive.GIVE[t].get("after")) for t in tiers} - {None}
    give_entries = {f"{progressive.HOLD_FILE}:{e}" for e in (progressive.NO_POSE_ENTRY, progressive.NO_POSE_PAY)}
    game = Game(patch, romfs)
    vanilla_game = Game(None, romfs)
    problems, stats = [], {"files": 0, "holds": 0, "gives": 0, "chests": 0, "shown": set(), "intercepted": 0,
                           "bound": 0}

    def check_actor(where, actor, how):
        stats["holds"] += 1
        ok = game.holdable(actor)
        if ok is False:
            problems.append(f"{where}: {how} {actor}: {game.why_not_holdable(actor)} (the hold-up can't end: a "
                            f"freeze, or a crash at the ignition)")
        elif ok:
            stats["shown"].add(actor)

    for rel in game.patched_files():
        stats["files"] += 1
        ev = Evfl(game.fs.read(rel))
        name = os.path.basename(rel).split(".")[0]
        van = vanilla_game.flowchart(name) if game.rels(name) else None
        van_names = {e["name"] for e in (van or {}).get("events", [])}
        for fc in ev.flowcharts:
            problems += _unbound_actors(fc, rel, van_names, stats)
            for e in fc["events"]:
                it = _items(e)
                consts = {k: _const(v) for k, v in it.items() if isinstance(_const(v), str)}
                named = {k: v for k, v in consts.items() if v in tiers}
                new = e["name"] not in van_names
                where = f"{rel} {e['name']}"
                gives = False
                if e["type"] == "action":
                    a = fc["actors"][e["actor"]]
                    act = a["actions"][e["action"]]
                    if a["name"] == "Player_Event" and act in SHOW and consts.get("Actor"):
                        check_actor(where, consts["Actor"], "Link holds up")
                    elif named and new and (a["name"], act) not in SAFE_ACTIONS \
                            and (a["name"], None) not in SAFE_ACTIONS:  # (vanilla steps: as the game has them)
                        problems.append(f"{where}: {a['name']}.{act} names {sorted(named.values())} (not a known "
                                        f"pose-free use)")
                    gives = bool(named) and a["name"] == "PouchSystemActor" and \
                        act == "EventTriggerAddOrRemovePouchContent"
                elif e["type"] in ("subflow", "subflow_switch"):
                    callee = e.get("flowchart") or name
                    for x in game.pose_args(callee, e["entry_point"]):
                        v = consts.get(x)
                        if v and _intercepted(game, callee, e["entry_point"], x, v):
                            stats["intercepted"] += 1  # its own branch's steps are checked where they are
                        elif v == progressive.ICE_MARKER:
                            problems.append(f"{where}: sells the ice-trap marker through {callee}:"
                                            f"{e['entry_point']}, whose hand-over doesn't freeze for it")
                        elif v:
                            check_actor(where, v, f"calls {callee}:{e['entry_point']}, which holds up")
                    if named and (callee, e["entry_point"]) in BIG_DISPLAY:
                        problems.append(f"{where}: shows {sorted(named.values())} with the chest's item display")
                    gives = bool(named) and (callee in progressive.POSE_FREE_FILES
                                             or f"{callee}:{e['entry_point']}" in give_entries)
                if gives and new:
                    stats["gives"] += 1
                    inside = e["name"].startswith(tuple(f"{x}_" for x in progressive.HOLD_ENTRIES))
                    if not inside and after_calls and not _calls_after(game, fc, name, e["idx"], after_calls):
                        problems.append(f"{where}: gives {sorted(named.values())} but no {sorted(after_calls)} "
                                        f"follows")
    # After the ocarina hold-up, the scene must sync equipment and open the action guide.
    fc = game.flowchart(progressive.HOLD_FILE)
    if progressive.NO_POSE_ENTRY in fc["entry_points"] and after_calls and not _calls_after(
            game, fc, progressive.HOLD_FILE, fc["entry_points"][progressive.NO_POSE_ENTRY]["main"], after_calls):
        problems.append(f"{progressive.HOLD_FILE}:{progressive.NO_POSE_ENTRY}: no {sorted(after_calls)}")
    after = progressive.AFTER_ENTRY
    if after in fc["entry_points"]:
        acts = {fc["actors"][e["actor"]]["actions"][e["action"]] for e in _reach(fc, fc["entry_points"][after]["main"])
                if e["type"] == "action"}
        calls = {f"{e.get('flowchart') or ''}:{e['entry_point']}" for e in _reach(fc, fc["entry_points"][after]["main"])
                 if e["type"] == "subflow"}
        for need in ("EventTriggerSyncPlayerEquipmentAndPouch", "EventWaitCreationFinishedEquipment"):
            if need not in acts:
                problems.append(f"{progressive.HOLD_FILE}:{after}: no {need} (the ocarina plays only after a reload)")
        if progressive.OCARINA_GUIDE not in calls:
            problems.append(f"{progressive.HOLD_FILE}:{after}: no {progressive.OCARINA_GUIDE}")
    # chests holding an ocarina: a scene of their own
    setting = {r["__RowId"]: r for r in byml_load(game.fs.read(EVENT_SETTING))[0]}
    for root, _, files in os.walk(os.path.join(patch, "Banc")):
        for fn in files:
            if not fn.endswith(".bcett.byml.zs"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), patch).replace("\\", "/")
            for a in byml_load(game.fs.read(rel))[0].get("Actors") or []:
                dyn = a.get("Dynamic") or {}
                held = [v for k, v in dyn.items() if isinstance(v, str) and v in tiers and k.startswith("Drop__")]
                if not held or not str(a.get("Gyaml", "")).startswith("Obj_TBox"):
                    continue
                stats["chests"] += 1
                row = setting.get(dyn.get("GetEventName") or "")
                if row is None:
                    problems.append(f"{rel} {a.get('Hash')}: {a.get('Gyaml')} holds {held} and plays the vanilla "
                                    f"opening")
                    continue
                fcn = (row.get("FlowchartFileName") or "").rsplit("/", 1)[-1].replace(".evfc", "")
                ep = row.get("EntryPointName")
                cfc = game.flowchart(fcn)
                if cfc is None or ep not in cfc["entry_points"]:
                    problems.append(f"{rel} {a.get('Hash')}: scene {dyn.get('GetEventName')} ({fcn}:{ep}) missing")
                elif any(e["type"] in ("subflow", "subflow_switch")
                         and ((e.get("flowchart") or fcn), e["entry_point"]) in BIG_DISPLAY
                         for e in _reach(cfc, cfc["entry_points"][ep]["main"])):
                    problems.append(f"{rel} {a.get('Hash')}: holds {held}; its scene {fcn}:{ep} shows its contents")
    problems += _show_model_problems(game, patch, romfs, stats)
    stats["shown"] = sorted(stats["shown"])
    return problems, stats


def _show_model_problems(game, patch, romfs, stats):
    """Checks the models parity/_show_models.py makes (song notes, Ocarina buttons, the upright Master Sword). Each one
    a patched ActorInfo row names (a display of ours, a song) is in the patch, and every one there reads back right
    (_show_models.verify: geometry, names, glow mask, size-table entries)."""
    try:
        from parity import _show_models as sm
    except ImportError:
        return []
    bad, found = sm.verify(patch, romfs)
    out = [f"show model: {x}" for x in bad]
    named = {r.get("FmdbName"): rid for rid, r in game._actor_info().items() if r.get("FmdbName")}
    for key, spec in sm.DISPLAYS.items():  # (an Ocarina button display has no fixed model: its label's, below)
        if spec[2] and spec[2] in named and key not in found:
            out.append(f"{named[spec[2]]}: its row names model {spec[2]} ({key}), which the patch doesn't have")
    codes = {sm.button_fmdb(label): label for label in sm.BUTTON_MODELS}
    for fmdb, rid in sorted(named.items()):
        if fmdb in codes and f"button:{codes[fmdb]}" not in found:
            out.append(f"{rid}: its row names model {fmdb} (Ocarina button {codes[fmdb]}), which the patch doesn't have")
    stats["models"] = len(found)
    return out


def main(out_dir, romfs=DEFAULT_ROMFS):
    patch = os.path.join(out_dir, "patch")
    if not os.path.isdir(patch):
        sys.exit(f"no patch in {out_dir}")
    problems, stats = verify(patch, romfs)
    for p in problems:
        print(p)
    print(f"{len(problems)} problems; {stats.get('files', 0)} patched event files read, {stats.get('holds', 0)} "
          f"hold-ups of a named actor checked, {stats.get('gives', 0)} new ocarina gives, {stats.get('chests', 0)} "
          f"ocarina chests, {stats.get('models', 0)} show models")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
