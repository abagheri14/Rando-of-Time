"""Treasure Chest Game with OoTR's shuffle_tcgkeys 'remove' (Keysy).

In OoTR's 'remove' the doors are open, the six keys are gone, the ten room chests and the salesman hold seed items
and the reward needs nothing. How we get that in the remake:
- The per-room shuffle is Logic/MiniGame_SequentialChoiceTreasure_BoxShuffle_84ca.logic.module.ainb. It sets
  IsReplace for a room's two chests to (random F32 < F32_B), with F32_B = 0.5 at file offset 0xc2c. We set that to
  -1.0 so they're never swapped. Every chest keeps its placed (seed) contents and OoTR's Top/Bottom are fixed (the
  keys row at z=9.7 is Top).
- The six chain-locked doors open with MiniGame_SmallKeyNum > 0 (MiniGame_ChainLockedDoor_cce0) and each unlock uses
  a key. The game hands you one key at the start (StartMinigame: Event57 MiniGame_SequentialChoiceTreasure_Start ->
  Event54 PassOnKey -> Event58) and a hit chest gives one more. Here the start sets MiniGame_SmallKeyNum to 6
  instead, so every door opens in every paid game. MiniGame_SequentialChoiceTreasure_End resets the counter to 0, so
  this needs no saved state.
- The salesman's hand-over (PassOnKey -> NpcCommon_HandOver_NpcToPlayer_DisplayGet_NoDisplay, ReceiveItem
  Obj_MiniGame_SmallKey) becomes the seed item, once. SOLD_FLAG, a new saved flag that's false on a new file, marks
  the sale. Vanilla's HaveTalked_Special...Event152 can't do that job because the salesman's talk clears it again
  (every talk calls TalkReset, whose Event210 sets it false), so the sale could repeat.
- The room chests (Obj_HrlCity_Shop_TBox_A_01) run the game's chest AI, unchanged. I bisected this, and with the
  vanilla AI every room chest opens, a right choice goes on and a wrong one ends the game, like vanilla.
  Each placement holds its seed item (Drop__DropActor) and loses IsEnableRepeatOpen, so the first opening saves
  IsTreasureBoxOpen.<hash> (AI/TreasureBox.event.root.ainb, EventTriggerTreasureBoxOpened). From then on the chest
  spawns open, the 'Ready' respawn included (AI/TreasureBox.module.ainb reads the member). So the seed item is given
  once, and a taken chest stands open in later games with nothing given again, no vanilla key or rupee. The tracker
  reads the same member.
  I tried resetting a taken chest every game through this root AI (a 'taken' record, IsRepeatContents, and the
  vanilla contents from two new instance parameters), but then no room chest could be opened. So that's gone, and
  verify_rooms checks the AI is the game's.
  * The scenes are untouched. A Top chest runs Hit/LastHit and a Bottom one runs Miss (the game ends, pay again).
  * The partner's pop-open. MiniGame_SequentialChoiceTreasure_OpenTreasureBox sets
    MiniGame_ChoiceTreasure_OpenedEitherBox before the get scene. A closed chest whose root AI sees it (node 32 ->
    22 -> 27) pops open with no item and nothing saved, and clears it. _End clears it too. A chest that's already
    open doesn't take it (node 32 -> 19). So after a hit in a room whose Bottom chest was taken in an earlier game,
    the flag waits for the next closed chest to see it, which is one of the next room's. That chest stands open for
    that game (its item stays for a later game). That matches what I saw: "a room's right chest couldn't be opened"
    and "both chests of a room showed open".
    The prize chest's root AI (PRIZE_AI) reads the flag too, so after a last hit whose partner was taken the prize
    could pop. Every chest is created whenever Market_Child loads (MiniGame_SequentialChoiceTreasure_cbde
    Logic_Create true), so a stray flag gets taken right away, not when the next room is entered.
    The fix (partner_part) never raises the flag when the room's partner already stands open. The hit and last-hit
    scenes find their room before they open the chest, by comparing the chest's ContentName with each room's Top
    contents (the dungeons' carrier compare). A Top taken earlier can't be the one being opened. If that room's
    Bottom is saved open (IsTreasureBoxOpen.<hash>) they set SKIP_POP. OpenTreasureBox has three ways into its flag
    step (Event70 case 1, joins Event90 and Event97) and all of them go through POP_CHECK, which then goes straight
    to Event203 and clears SKIP_POP. If two hit chests have the same contents and either untaken one's partner is
    open, there's no flag. The worst case is a partner left closed, never a chest of another room popping. No AI or
    chest placement changes.
    On the N64 (decomp En_Changer) opening one chest opens the other with its item shown but not given, so you get
    one choice a room.
The keyed modes (regional, overworld, any_dungeon, keysanity) are the
same game except for the keys. Each Treasure Chest Game key found anywhere adds one to KEY_COUNT, a new saved Int.
The dungeons plugin's credit entries do that: a TCG key is given like a dungeon key, with KEY_COUNT as its count,
and a key ring adds six. Every paid game copies it into MiniGame_SmallKeyNum (a chain of EventQueryIsGameDataInt
branches, capped at six), so the first N doors open with N keys found, the way OoTR's logic has it (room N needs N
keys, the prize 6).
The last of the N comes through the game's shop-key steps, the same ones the salesman's key runs (GETKEY_SHOP:
UI_MiniGameGetSmallKeyOnce, +1, the count-up request, EventTriggerSetDisplaySmallKey, 50 frames). That way the
minigame's key counter (MiniGame_SmallKeyNum, shown in Market_Child while MiniGame_ChoiceTreasure_IsPlaying, main
0x586420, 0xb2c090) comes up with its count-up like after the salesman's key. With none found the start sets 0
silently, and 'remove' sets its six silently. The hit chests'
GetKey call (Top row: OpenHitTreasureBox Event124, OpenLastHitTreasureBox Event135) is skipped, so a room chest only
gives its seed item and never a minigame key. MiniGame_SmallKeyNum itself stays unsaved and ..._End zeroes it like
in vanilla, and the doors lock again with the next game's 'Ready' respawn, also like vanilla.
"""
import struct

FILE = "MiniGame_SequentialChoiceTreasure"
SHUFFLE = "Logic/MiniGame_SequentialChoiceTreasure_BoxShuffle_84ca.logic.module.ainb"
SHUFFLE_OFFSET = 0xC2C
F32_HALF = struct.unpack("<i", struct.pack("<f", 0.5))[0]
F32_NEVER = struct.unpack("<i", struct.pack("<f", -1.0))[0]
SOLD_FLAG = "Rando_TcgSold"  # new saved Bool (false on a new file), set once the salesman's seed item is sold
TAKEN = "Rando_TcgTaken_{}"  # old per-chest record, no longer made (verify_rooms flags one)
ROOT_AI = "AI/Obj_HrlCity_Shop_TBox_A_01.root.ainb"  # the room chests' root AI (both TCG chest packs hold it)
BB_TABLE = "Component/Blackboard/BlackboardParamTable/Obj_HrlCity_Shop_TBox_A_01.engine__component__BlackboardParamTable.bgyml"
VANILLA_DROP, VANILLA_VIEW = "RandoVanillaDrop", "RandoVanillaView"  # the old rework's parameters, for verify_rooms
PRIZE_AI = "AI/Obj_HrlCity_Shop_TBox_A_02.root.ainb"  # the prize chests' root AI
KEYS = "MiniGame_SmallKeyNum"
DOORS = 6
KEY_COUNT = "Rando_TcgKeyNum"  # TCG keys found in the keyed modes (saved Int, 0 on a new file)
AFTER_FILE, AFTER_ENTRY = "GetPouchContent", "Rando_TcgKeyAfter"  # the key's get message (dungeons.TCG_AFTER)
MSBT, MSG = "EventFlowMsg/Dm_SY_Get.msbt", "EventFlowMsg/Dm_SY_Get:{}"
HIT_GETKEY = (("Event124", "Event34"), ("Event135", "Event37"))  # hit chests' GetKey call -> the step after it
GETKEY_SHOP = "MiniGame_SequentialChoiceTreasure_GetKey_Shop"  # the salesman's key (Dm_SY_GetInEvent Event656 calls it)
GETKEY_SHOP_STEPS = (("EventTriggerSetGameDataBool", "GameDataName", "UI_MiniGameGetSmallKeyOnce"),
                     ("EventTriggerAddOrSubGameDataInt", "GameDataName", KEYS),
                     ("EventTriggerSetGameDataBool", "GameDataName", "UI_RequestSmallKeyCountUpDemo"),
                     ("EventWait", "Frames", 1),
                     ("EventTriggerSetDisplaySmallKey", "IsDisplaySmallKey", True),
                     ("EventWait", "Frames", 50))
SALESMAN = "Market Treasure Chest Game Salesman"
# OoTR room chest -> remake chest (Market_Child_Static). Rooms go from the counter inwards (x -74.9 .. -118.9).
# Top is the key row (z 9.7) and Bottom the rupee row (z 15.7).
ROOMS = {
    "Market Treasure Chest Game Room 1 Top": "Market/chest/1775586642693927992",
    "Market Treasure Chest Game Room 1 Bottom": "Market/chest/7390716194495618474",
    "Market Treasure Chest Game Room 2 Top": "Market/chest/5350594583391365806",
    "Market Treasure Chest Game Room 2 Bottom": "Market/chest/12114077686306649660",
    "Market Treasure Chest Game Room 3 Top": "Market/chest/12763522142548402103",
    "Market Treasure Chest Game Room 3 Bottom": "Market/chest/9591654059707200528",
    "Market Treasure Chest Game Room 4 Top": "Market/chest/6478285350658826847",
    "Market Treasure Chest Game Room 4 Bottom": "Market/chest/13633455645485504369",
    "Market Treasure Chest Game Room 5 Top": "Market/chest/18239509117326156183",
    "Market Treasure Chest Game Room 5 Bottom": "Market/chest/15659683110284072977",
}
# item kinds the salesman's hand-over can't give (it adds a plain actor to the pouch)
NOT_SOLD_TYPES = ("Song", "SmallKey", "SmallKeyRing", "BossKey", "GanonBossKey", "Map", "Compass", "HideoutSmallKey",
                  "HideoutSmallKeyRing", "TCGSmallKey", "TCGSmallKeyRing", "SilverRupee", "DungeonReward", "Token",
                  "Event", "Shop")


def room_spec(actor, note, view):
    """Reward spec for a room chest holding `actor`. `view` is the model the chest shows (view_for). The first opening
    is saved (no IsEnableRepeatOpen), so it gives `actor` once."""
    return {"item": actor, "note": note, "extra": {"IsEnableRepeatOpen": None, "DropViewActor": view}}


def _vanilla_room(rid):
    """Vanilla (Drop__DropActor, DropViewActor) of room chest `rid` from data/rewards.json, or None."""
    import json
    import os
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    r = next((x for x in json.load(open(os.path.join(here, "data", "rewards.json"), encoding="utf-8"))
              if x["id"] == rid), None)
    return (r["item"], (r.get("extra") or {}).get("DropViewActor") or "") if r else None


# The chests' views
# Every vanilla Treasure Chest Game chest (ten rooms and the prize) names a view in DropViewActor, the model it shows
# (data/rewards.json): Obj_OrnamentalRupee_Green/Blue/Red_MiniGame, Obj_MiniGame_SmallKey or Obj_Heart_Piece_MiniGame.
# ROOT_AI node 8 loads the actor by name into ContentDisplay before the chest reaches 'Initialized', and the prize
# chest does the same. With an empty name node 12 stays busy (ExecuteGenericSetResultBusy), so view_for always gives
# a name.
# - A room chest shows its vanilla view. That's what my bisect build showed, and it opened.
# - The prize shows a vanilla view when one has the item's model (VIEWS, matched by model and colour, so green, blue
#   and red rupees, any small key, any heart piece). Otherwise it shows the item's display (drops.item_display, an
#   Item_* event object or a display of ours, for a progressive item its first tier's), and failing that its vanilla
#   view. In my test the prize chest showed the Iron Boots that way on the game's AI, and gave them.
# - ITEM_VIEWS (a separate choice, off) treats every chest like the prize. Where the display is a chest-content actor
#   (TBox_*: shields, other rupees, ammo, the magic jar), runs an AI (Item_Dungeon_Map) or is missing, it uses a NEW
#   view type of ours, Rando_TcgView_*. That's a copy of the vanilla ornamental rupee's pack (no AI, no physics, no
#   pouch) with that actor's model, animations and AS (view_type_ops). A room chest's view is created by the same
#   nodes as the prize's (delete, create DropViewActor by name in ContentDisplay, TryAdventActorInTBox) from the same
#   holder, so the Iron Boots test speaks for a display there too. The view types were never seen in game.
# - With remake_item_looks other than "item" (the old look), the chest's vanilla view.
# Views that aren't vanilla are declared in the chest's holder (parity/chests.py TCG_HOLDER) so they load with it.
ITEM_VIEWS = False
ITEM_VIEWS_PROBE = "tcg_item_views"  # a test build's probe (plans "test_start" "probes") that turns ITEM_VIEWS on


def item_views():
    """ITEM_VIEWS, or on in a test build that asks for the probe. OoTR's chests show their item unless
    tcg_requires_lens. TODO: our room views were never seen in game, so the default waits for the probe."""
    from parity import _test_start
    return ITEM_VIEWS or _test_start.probe(ITEM_VIEWS_PROBE)


VIEWS = ("Obj_OrnamentalRupee_Green_MiniGame", "Obj_OrnamentalRupee_Blue_MiniGame", "Obj_OrnamentalRupee_Red_MiniGame",
         "Obj_MiniGame_SmallKey", "Obj_Heart_Piece_MiniGame")
VIEW_BASE = "Obj_OrnamentalRupee_Green_MiniGame"
VIEW_PREFIX = "Rando_TcgView_"
PRIZE = "Market/chest/16881481538337649070"  # the prize chest (Market Treasure Chest Game Reward)
HOLDER = "Component/ActorHolderParam/Obj_HrlCity_Shop_TBox_A_01.game__component__ActorHolderParam.bgyml"
_views = {}


def _tables():
    import shops  # tools/rando/shops.py, reads the game's tables and packs once
    return shops._table(shops.ACTOR_INFO_TABLE), shops._table(shops.GAME_ACTOR_INFO_TABLE)


def _model(actor):
    """(model project, model, colour animations) that `actor` shows, or None."""
    import json
    rows, grows = _tables()
    r = rows.get(actor)
    if not r or not r.get("ModelProjectName"):
        return None
    return (r["ModelProjectName"], r.get("FmdbName"),
            json.dumps((grows.get(actor) or {}).get("ModelVariationAnims") or [], sort_keys=True))


def vanilla_view(actor):
    """The vanilla view showing `actor`'s model (VIEWS), or None."""
    if "match" not in _views:
        _views["match"] = {_model(v): v for v in VIEWS}
    return _views["match"].get(_model(actor)) if actor else None


def _has_ai(actor):
    """Whether `actor` runs an AI in the game (Item_Dungeon_Map's, the pause menu's)."""
    import shops
    return bool(shops._comps(actor).get("AIInfoRef"))


def is_content(actor):
    """A chest-content actor (TBox_*): what a chest gives, never a view."""
    return actor.lower().startswith("tbox_")


def view_for(item, actor, rid, looks="item", stand_in=None, kinds="item"):
    """(DropViewActor, why) for Treasure Chest Game chest `rid` (a room or the prize) holding OoTR item `item` as
    contents `actor`. Never empty. See the block comment above.
    `stand_in` is the hidden contents of an item a scene gives. Its model says nothing about the item.
    `kinds` is "vanilla" (the chest's vanilla view), "display" (a vanilla view or display showing the item, else the
    chest's) or "item" (view types of ours as well, ITEM_VIEWS)."""
    van = (_vanilla_room(rid) or (None, None))[1]
    if not van:
        raise ValueError(f"{rid}: no Treasure Chest Game chest")
    if kinds == "vanilla":
        return van, "the chest's vanilla view"
    import drops as drop_tools  # tools/rando/drops.py
    import progressive
    own = [a for a in (drop_tools._item_map().get(item), actor) if a and a != stand_in]  # the item's remake actors
    for a in own:
        v = vanilla_view(a)
        if v:
            return v, f"{a}'s vanilla view"
    display = None
    if looks == "item":
        try:
            d = drop_tools.item_display(item) or {}
        except Exception:  # noqa: BLE001 - an item the drops plugin has no look for
            d = {}
        display = d.get("actor") or (d.get("tiers") or [[None, None]])[0][1]
        if display is None and item in progressive.PROGRESSIVE:
            display = drop_tools.display_actor(progressive.PROGRESSIVE[item]["tiers"][0])
        display = display or next((d for d in map(drop_tools.display_actor, own) if d), None)
    if display:
        v = vanilla_view(display)
        if v:
            return v, f"{display}'s vanilla view"
        if not is_content(display) and not _has_ai(display):
            return display, "its display"
    src = display or (own[0] if looks == "item" and own else None)  # no display, so its own model
    if kinds == "item" and src and not src.startswith("Pouch_"):  # a pause-menu actor's model shows nothing
        view = view_type(src)
        if view_type_ops(view, src) is not None:
            return view, f"a view of {src}'s model"
    why = f" (no {'view' if kinds == 'item' else 'display'} for {item})" if looks == "item" else ""
    return van, "the chest's vanilla view" + why


def view_type(display):
    """The view type showing actor `display`'s model, Rando_TcgView_<short>. 25 characters at most
    (progressive.DISPLAY_NAME_MAX)."""
    import re
    import zlib
    short = re.sub(r"^(?i:tbox_|item_|obj_)", "", display).replace("Bundle", "").replace("_", "")
    if len(VIEW_PREFIX + short) > 25:
        tag = f"{zlib.crc32(display.encode()) & 0xFFF:03X}"
        short = short[:25 - len(VIEW_PREFIX) - len(tag)] + tag
    return VIEW_PREFIX + short


def view_type_ops(view, display):
    """{"new_files", "packs", "byml"} for the NEW view type `view`. It's a copy of VIEW_BASE's pack (the vanilla view
    class) that shows chest-content actor `display` the way it shows itself (its ModelInfo, AnimationParam, ASInfo and
    AS). None when `display` has no such files."""
    if ("ops", view) in _views:
        return _views[("ops", view)]
    import progressive
    import shops
    rows, grows = _tables()
    files = shops._actor_pack(display) or {}
    comps = shops._comps(display)
    refs = {k: (comps.get(k) or "").lstrip("?") for k in ("ModelInfoRef", "AnimationRef", "ASInfoRef")}
    out = None
    if display in rows and all(refs[k] in files for k in refs) and comps.get("ASRef") and view not in rows:
        rel = f"Pack/Actor/{view}.pack.zs"
        note = f"{view}: the Treasure Chest Game chests' view of {display} (the {VIEW_BASE} class)"
        out = {"new_files": [{"to": rel, "from": f"Pack/Actor/{VIEW_BASE}.pack.zs", "note": note}],
               "packs": [{"pack": rel, "file": f, "from_pack": f"Pack/Actor/{display}.pack.zs"}
                         for f in sorted(set(refs.values()))], "byml": []}
        out["packs"].append({"pack": rel, "file": f"Actor/{view}.engine__actor__ActorParam.bgyml",
                             "new_from": f"Actor/{VIEW_BASE}.engine__actor__ActorParam.bgyml",
                             "set": dict({f"Components.{k}": "?" + v for k, v in refs.items()},
                                         **{"Components.ASRef": comps["ASRef"]})})
        # its rows are the content actor's (model, colour, animations, radii), with the larger heaps of the two
        heaps = {k: max(int(rows[a].get(k) or 0) for a in (VIEW_BASE, display)) for k in progressive.HEAPS}
        out["byml"].append({"file": shops.ACTOR_INFO_TABLE, "add_row": {"copy_of": display, "set": dict(
            heaps, __RowId=view)}, "note": note})
        out["byml"].append({"file": shops.GAME_ACTOR_INFO_TABLE, "add_row": {
            "copy_of": display if display in grows else VIEW_BASE, "set": {"__RowId": view}}})
    _views[("ops", view)] = out
    return out


def verify_views(fs, item_views=False):
    """[problem] for the patched Market. Every Treasure Chest Game chest (ten rooms and the prize) has to name a view
    (DropViewActor) of a valid kind:
    - a vanilla view (VIEWS)
    - a view type of ours (VIEW_PREFIX), meaning the patch's pack, a copy of VIEW_BASE's components with a model of
      its own, and its rows
    - a display, an actor of the patch or the game with no AI that isn't a chest-content actor (TBox_*)
    One that isn't vanilla has to be declared in the chest's holder (HOLDER). Without `item_views` (ITEM_VIEWS, as the
    plan was made) a room chest shows its vanilla view and the prize no view type of ours."""
    from romtools import byml_load, sarc_files
    root = byml_load(fs.read("Banc/Market/Market_Child_Static.bcett.byml.zs"))[0]
    by = {str(x["Hash"]): x for x in root["Actors"]}
    rows = {r["__RowId"] for r in byml_load(fs.read("RSDB/ActorInfo.Product.111.rstbl.byml.zs"), allow_big=True)[0]}
    grows = {r["__RowId"] for r in byml_load(fs.read("RSDB/GameActorInfo.Product.111.rstbl.byml.zs"),
                                                  allow_big=True)[0]}
    packs = {}

    def pack(a):
        if a not in packs:
            try:
                packs[a] = sarc_files(fs.read(f"Pack/Actor/{a}.pack.zs"))
            except Exception:  # noqa: BLE001 - no such pack
                packs[a] = None
        return packs[a]

    def comps(a):
        """{component: ref} of actor `a`'s ActorParam chain in its pack, its own entries first."""
        files, out, name = pack(a) or {}, {}, a
        while name:
            p = files.get(f"Actor/{name}.engine__actor__ActorParam.bgyml")
            if p is None:
                break
            doc = byml_load(p)[0]
            for k, v in (doc.get("Components") or {}).items():
                out.setdefault(k, v)
            par = doc.get("$parent") or ""
            name = par.rsplit("/", 1)[-1].split(".")[0] if par else None
        return out

    base = {k for k, v in comps(VIEW_BASE).items() if v}
    bad = []
    for rid in sorted(set(ROOMS.values()) | {PRIZE}):
        a = by.get(rid.rsplit("/", 1)[1])
        if a is None:
            bad.append(f"{rid}: no Treasure Chest Game chest in Market_Child_Static")
            continue
        dyn = a.get("Dynamic") or {}
        view = dyn.get("DropViewActor") or ""
        if not view:
            bad.append(f"{rid}: no view (DropViewActor empty: the chest's setup waits forever, it can't be opened)")
            continue
        if not item_views and rid != PRIZE and view != (_vanilla_room(rid) or (None, None))[1]:
            bad.append(f"{rid}: view {view}, not its vanilla view (the room chests show theirs: ITEM_VIEWS is off)")
        if not item_views and view.startswith(VIEW_PREFIX):
            bad.append(f"{rid}: view {view}: a view type of ours (only with ITEM_VIEWS)")
        if view in VIEWS:
            continue
        c = comps(view)
        why = None
        if pack(view) is None or view not in rows or view not in grows:
            why = "no pack or ActorInfo / GameActorInfo row"
        elif view.startswith(VIEW_PREFIX):
            model = (c.get("ModelInfoRef") or "").lstrip("?")
            have = {k for k, v in c.items() if v}
            if have - base - {"AnimationRef"} or model not in pack(view) or "Rupee_Green" in model:
                why = f"not the {VIEW_BASE} class with a model of its own ({sorted(have ^ base)}, {model})"
        elif is_content(view):
            why = "a chest-content actor (what a chest gives), not a view"
        elif c.get("AIInfoRef") or view.startswith("Pouch_"):
            why = "an actor with an AI of its own"
        if why:
            bad.append(f"{rid}: view {view}: {why}")
            continue
        files, held, name = pack(a.get("Gyaml") or "") or {}, set(), HOLDER  # the holder and its $parent chain
        while name in files:
            doc = byml_load(files[name])[0]
            held |= {str(x.get("Actor") or "").rsplit("/", 1)[-1].split(".")[0]
                     for x in (doc.get("ActorHoldSettings") or {}).values()}
            name = str(doc.get("$parent") or "").replace("Work/", "", 1).replace(".gyml", ".bgyml")
        if view not in held:
            bad.append(f"{rid}: view {view} isn't declared in its chest's holder ({a.get('Gyaml')}: {HOLDER}), so "
                       f"nothing loads it")
    return bad


def view_types_part(views):
    """Plan sections {"new_files", "packs", "byml"} for the view types among `views` (view_type names)."""
    out = {"new_files": [], "packs": [], "byml": []}
    for view in sorted(set(views)):
        ops = _views.get(("ops", view))
        if view.startswith(VIEW_PREFIX):
            if ops is None:
                raise ValueError(f"{view}: no view type built")
            for k in out:
                out[k] += ops[k]
    return out


def verify_rooms(fs, plan):
    """[problem] if the Treasure Chest Game chests don't run the game's AI. ROOT_AI, PRIZE_AI and BB_TABLE have to hold
    the game's bytes in every pack that has them, and every chest names a valid view (verify_views, with the plan's
    ITEM_VIEWS). Each room chest with a seed item has no IsEnableRepeatOpen, so its first opening is saved and the item
    comes once (chest_flags.verify reads its IsTreasureBoxOpen member). None of the old rework's parameters or records
    are left."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))), "tools"))
    import packpaths
    from romtools import Romfs, byml_load, murmur3_32, sarc_files
    van = Romfs(fs.root, fs.vanilla)
    bad = verify_views(fs, bool(plan.get("_tcg_item_views")))
    for inner in (ROOT_AI, PRIZE_AI, BB_TABLE):
        for pack in sorted(packpaths.carriers(inner, fs.root)):
            if sarc_files(fs.read(pack)).get(inner) != sarc_files(van.read(pack)).get(inner):
                bad.append(f"{pack}:{inner}: not the game's own (the chests' AI stays vanilla: with it edited "
                           f"a room chest wouldn't open)")
    if plan.get("_tcg_partner"):  # the partner's pop-open fix (partner_part)
        bad += verify_partner(fs, plan["_tcg_partner"])
    rooms = sorted(set(ROOMS.values()) & set(plan.get("rewards") or {}))
    if not rooms:
        return bad
    root = byml_load(fs.read("Banc/Market/Market_Child_Static.bcett.byml.zs"))[0]
    by = {str(x["Hash"]): x for x in root["Actors"]}
    bools = {int(e["Hash"]) for e in byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"),
                                               allow_big=True)[0]["Data"]["Bool"]}
    for rid in rooms:
        h = rid.rsplit("/", 1)[1]
        dyn = (by.get(h) or {}).get("Dynamic") or {}
        if dyn.get("IsEnableRepeatOpen"):
            bad.append(f"{rid}: still IsEnableRepeatOpen (its opening saves nothing: the seed item every game)")
        old = [k for k in (VANILLA_DROP, VANILLA_VIEW) if k in dyn]
        if old:
            bad.append(f"{rid}: the old rework's parameters {old}")
        if murmur3_32(TAKEN.format(h)) in bools:
            bad.append(f"{rid}: the old rework's record {TAKEN.format(h)}")
    return bad


def _key_chain(nodes):
    """The keyed modes set MiniGame_SmallKeyNum := min(KEY_COUNT, 6). Int queries answer 0 below, 1 equal, 2 above. The
    last key goes through the game's shop-key steps (GETKEY_SHOP) so the HUD's minigame key counter appears."""
    nodes["keys"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                     "params": {"Index": -1, "GameDataName": KEY_COUNT, "Value": 1},
                     "cases": {0: "set0", 1: "set1", 2: "k2"}}
    for v in range(2, DOORS + 1):
        nodes[f"k{v}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                          "params": {"Index": -1, "GameDataName": KEY_COUNT, "Value": v},
                          "cases": {0: f"set{v - 1}", 1: f"set{v}", 2: f"k{v + 1}" if v < DOORS else f"set{DOORS}"}}
    for v in range(DOORS + 1):
        nodes[f"set{v}"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                            "params": {"Index": -1, "GameDataName": KEYS, "Value": max(v - 1, 0)},
                            "next": "shopkey" if v else "@Event58"}
    nodes["shopkey"] = {"call": f":{GETKEY_SHOP}", "next": "@Event58"}


def after_texts():
    """{label: {language: markup}} with OoTR's text for a shuffled Treasure Chest Game key, by the count after it
    ("You found a Small Key for the Treasure-Chest Shop!" + "It's your first one!" / "You've collected N of them." /
    "You already have enough keys."), in every language (parity/_dungeons_text.py)."""
    from parity import _dungeons_text as dt
    return dt.tcg_count_texts({k: f"Rando_TcgKey{k}" for k in range(1, DOORS + 1)}, "Rando_TcgKeyMore")


def after_graph():
    """(nodes, start) of the key's get message (GetPouchContent, called by the key's credit steps), one per count. The
    credit's add lands a frame or two later (tools/rando/write_read_check.py, same fix as the Triforce count),
    so we read the count after the game's 2-frame wait. Without it the first key read 0 and showed nothing."""
    from parity._chests_scenes import TALK_PARAMS
    from write_read_check import settle
    n = {"settle": settle("q1")}
    for k in range(1, DOORS + 1):
        n[f"q{k}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                      "params": {"GameDataName": KEY_COUNT, "Value": k, "Index": -1},
                      "cases": {0: None, 1: f"t{k}", 2: f"q{k + 1}" if k < DOORS else "more"}}
        n[f"t{k}"] = {"actor": "SystemTextNPC", "action": "EventTalk",
                      "params": dict(TALK_PARAMS, MessageId=MSG.format(f"Rando_TcgKey{k}")), "next": None}
    n["more"] = {"actor": "SystemTextNPC", "action": "EventTalk",
                 "params": dict(TALK_PARAMS, MessageId=MSG.format("Rando_TcgKeyMore")), "next": None}
    return n, "settle"


def plan_part(sale_actor, keyed=False, call=None, node=None):
    """Binary edit (no shuffle) and the start-of-game graph (sale once, then six keys, or the keys found).
    `call` makes the sale's give that scene call instead of Event67's hand-over of `sale_actor`. That's a dungeon
    item's credit entry (parity/dungeons.py call_target), or an ice trap's freeze, a tier entry, the bean pack's or a
    soul's entry (the give router, parity/chests.py _tcg_give).
    `node` is a give node of its own (the get routine or a hold-up)."""
    nodes = {
        "q": {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
              "params": {"Index": -1, "GameDataName": SOLD_FLAG}, "cases": {0: "keys", 1: "give"}},
        "give": {"call": call, "next": "sold"} if call else dict(node, next="sold") if node else
                {"copy": "Event67", "params_over": {"ReceiveItem": sale_actor}, "next": "sold"},
        "sold": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                 "params": {"Index": -1, "GameDataName": SOLD_FLAG, "Value": True}, "next": "keys"},  # (SOLD_FLAG)
        "keys": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataInt",
                 "params": {"Index": -1, "GameDataName": KEYS, "Value": DOORS}, "next": "@Event58"},
    }
    out = {
        "binary": [{"file": SHUFFLE, "offset": SHUFFLE_OFFSET, "i32": F32_NEVER, "expect": F32_HALF}],
        "events": [{"file": FILE, "flowchart": FILE, "add_graph": "Rando_TcgStart", "nodes": nodes, "start": "q"},
                   {"file": FILE, "flowchart": FILE, "event": "Event57", "next": "Rando_TcgStart_q"}],
        "gamedata": {"add_bools": {SOLD_FLAG: False}},
    }
    if keyed:
        _key_chain(nodes)
        a_nodes, a_start = after_graph()
        out["events"].append({"file": AFTER_FILE, "flowchart": AFTER_FILE, "add_graph": AFTER_ENTRY,
                              "nodes": a_nodes, "start": a_start})
        out["text"] = [{"lang": lang, "file": MSBT, "label": k, "markup": m, "add": True, "note": "shuffle_tcgkeys"}
                       for k, v in after_texts().items() for lang, m in sorted(v.items())]
        out["events"] += [{"file": FILE, "flowchart": FILE, "event": ev, "next": nxt} for ev, nxt in HIT_GETKEY]
        out["gamedata"]["add_ints"] = {KEY_COUNT: 0}
        out["_gaps"] = {"tcg_keys": {"count": KEY_COUNT, "skip_getkey": [list(x) for x in HIT_GETKEY]}}
    return out


# The partner's pop-open (see the module doc)
YES, NO = 0, 1  # query answers (case 0 = yes)
SKIP_POP = "Rando_TcgSkipPop"  # new saved Bool (false on a new file), this opening mustn't raise the pop flag
POP_FLAG = "MiniGame_ChoiceTreasure_OpenedEitherBox"
POP_CHECK = "Rando_TcgPopCheck"
OPEN_ENTRY = "MiniGame_SequentialChoiceTreasure_OpenTreasureBox"
POP_SET, POP_AFTER = "Event166", "Event203"  # OpenTreasureBox's flag step and the step after it
POP_EDGES = (("Event70", 1), ("Event90", None), ("Event97", None))  # its ways into POP_SET, as (step, case index)
ROUTES = {  # scene: (first step, case that opens the chest, step it goes to, route graph, rooms)
    "hit": ("Event121", 0, "Event123", "Rando_TcgHitRoute", (1, 2, 3, 4)),
    "last": ("Event132", 0, "Event134", "Rando_TcgLastHitRoute", (5,))}


def room_chests():
    """{room number: (Top rid, Bottom rid)} (ROOMS: Top = the key row, Bottom = the rupee row)."""
    return {n: (ROOMS[f"Market Treasure Chest Game Room {n} Top"], ROOMS[f"Market Treasure Chest Game Room {n} Bottom"])
            for n in range(1, 6)}


def _opened(rid):
    return f"IsTreasureBoxOpen.{rid.rsplit('/', 1)[1]}"  # chest_flags, every chest's saved opening


def _q(flag, yes, no):
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
            "params": {"Index": -1, "GameDataName": flag}, "cases": {YES: yes, NO: no}}


def route_nodes(rooms, contents, go):
    """(nodes, start) of a hit scene's room finder for `rooms` (room numbers), run before its chest opens. `contents` is
    {Top rid: Drop__DropActor} and `go` the vanilla step that opens the chest ("@EventN").
    The chest's ContentName is compared with each Top's contents (the dungeons' carrier compare: the name goes into the
    scrub scratch String64, then the game's 2-frame settle, then EventQueryIsGameDataString64). In the matching room a
    saved-open Bottom (its partner) sets SKIP_POP. If rooms share contents, a Top saved open isn't the one being
    opened, and any other's open Bottom sets SKIP_POP. With one room there's no compare."""
    import progressive
    from write_read_check import settle
    chests = room_chests()
    n = {"skip": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                  "params": {"Index": -1, "GameDataName": SKIP_POP, "Value": True}, "next": "settle"},
         "settle": settle(go)}  # POP_CHECK reads it inside the chest's opening, so let it land first
    groups = {}
    for room in rooms:
        top, bot = chests[room]
        groups.setdefault(contents[top], []).append((top, bot))
    order = sorted(groups)

    def chain(i, members):
        if len(members) == 1:
            n[f"g{i}b0"] = _q(_opened(members[0][1]), "skip", go)
            return f"g{i}b0"
        for j, (top, bot) in enumerate(members):
            nxt = f"g{i}t{j + 1}" if j + 1 < len(members) else go
            n[f"g{i}t{j}"] = _q(_opened(top), nxt, f"g{i}b{j}")
            n[f"g{i}b{j}"] = _q(_opened(bot), "skip", nxt)
        return f"g{i}t0"
    if len(order) == 1:
        return n, chain(0, groups[order[0]])
    n["name"] = {"actor": "GameDataActor", "action": "EventTriggerSetGameDataString64",
                 "params": {"GameDataName": progressive.SCRUB_SCRATCH, "Index": -1, "Value": {"arg": "ContentName"}},
                 "next": "nsettle"}
    n["nsettle"] = settle("c0")
    for i, c in enumerate(order):
        n[f"c{i}"] = {"actor": "GameDataActor", "query": "EventQueryIsGameDataString64",
                      "params": {"GameDataName": progressive.SCRUB_SCRATCH, "Index": -1, "Value": c},
                      "cases": {YES: chain(i, groups[c]), NO: f"c{i + 1}" if i + 1 < len(order) else go}}
    return n, "name"


def partner_part(rewards):
    """Plan sections for the partner's pop-open fix (see the module doc): the hit and last-hit scenes' room finders, the
    pop check in OpenTreasureBox, and SKIP_POP. `rewards` is the plan's rewards. A room chest that isn't in them keeps
    its vanilla contents and IsEnableRepeatOpen, so its Bottom never stands open."""
    contents = {}
    for top, bot in room_chests().values():
        for rid in (top, bot):
            contents[rid] = (rewards.get(rid) or {}).get("item") or (_vanilla_room(rid) or (None,))[0]
    events = []
    for scene, (first, case, opens, graph, rooms) in sorted(ROUTES.items()):
        nodes, start = route_nodes(rooms, contents, f"@{opens}")
        events.append({"file": FILE, "flowchart": FILE, "add_graph": graph, "nodes": nodes, "start": start})
        events.append({"file": FILE, "flowchart": FILE, "event": first, "case": case, "next": f"{graph}_{start}"})
    events.append({"file": FILE, "flowchart": FILE, "add_graph": POP_CHECK, "start": "q", "nodes": {
        "q": _q(SKIP_POP, "reset", f"@{POP_SET}"),
        "reset": {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
                  "params": {"Index": -1, "GameDataName": SKIP_POP, "Value": False}, "next": f"@{POP_AFTER}"}}})
    for ev, case in POP_EDGES:
        events.append(dict({"file": FILE, "flowchart": FILE, "event": ev, "next": f"{POP_CHECK}_q"},
                           **({"case": case} if case is not None else {})))
    note = {"rooms": {str(k): list(v) for k, v in room_chests().items()},
            "contents": {rid: contents[rid] for top, _ in room_chests().values() for rid in [top]}}
    return {"events": events, "gamedata": {"add_bools": {SKIP_POP: False}}, "_tcg_partner": note}


def verify_partner(fs, note):
    """[problem] for the partner fix, read back from the patched flow (see the module doc).
    - For every room, with only its Bottom saved open, the hit (last hit) scene sets SKIP_POP before it opens the
      chest. With its Bottom closed (every other Bottom open) it doesn't, unless a room with the same Top contents is
      untaken with its Bottom open.
    - Every way into OpenTreasureBox's flag step goes through POP_CHECK, which skips the flag on SKIP_POP and clears it.
    - SKIP_POP is a Bool of GameDataList."""
    import progressive
    from evfl import Evfl
    from romtools import byml_load, murmur3_32
    fc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{FILE}.bfevfl.zs")).flowcharts if f["name"] == FILE)
    ev = fc["events"]
    by = {e["name"]: e for e in ev}
    bad = []

    def at(i):
        return ev[i] if i not in (None, 0xFFFF) and i < len(ev) else None

    def prm(e, k):
        return ((e.get("params") or {}).get("items") or {}).get(k, {}).get("value")

    def act(e):
        a = fc["actors"][e["actor"]]
        return a["actions"][e["action"]] if e["type"] == "action" else a["queries"][e["query"]]

    def case(e, v):
        return at(next((c["next"] for c in e["cases"] if c["value"] == v), None))

    def run(e, content, opened, stop):
        """Walk a route from step e. Returns (reached stop, SKIP_POP set) or (None, why)."""
        skip, scratch = False, None
        for _ in range(80):
            if e is None:
                return None, "the route ends"
            if e["name"] == stop:
                return True, skip
            a = act(e) if e["type"] in ("action", "switch") else None
            if a == "EventTriggerSetGameDataString64" and prm(e, "GameDataName") == progressive.SCRUB_SCRATCH:
                scratch = content  # its Value is the ContentName argument
                e = at(e["next"])
            elif a == "EventTriggerSetGameDataBool" and prm(e, "GameDataName") == SKIP_POP:
                skip = bool(prm(e, "Value"))
                e = at(e["next"])
            elif a == "EventWait":
                e = at(e["next"])
            elif a == "EventQueryIsGameDataString64" and prm(e, "GameDataName") == progressive.SCRUB_SCRATCH:
                e = case(e, YES if scratch == prm(e, "Value") else NO)
            elif a == "EventQueryIsGameDataBool" and str(prm(e, "GameDataName")).startswith("IsTreasureBoxOpen."):
                e = case(e, YES if prm(e, "GameDataName") in opened else NO)
            else:
                return None, f"step {e['name']} ({a or e['type']}) isn't a route step"
        return None, "the route doesn't end"
    chests = room_chests()
    contents = note.get("contents") or {}
    for scene, (first, cidx, opens, graph, rooms) in sorted(ROUTES.items()):
        f = by.get(first)
        start = at(f["cases"][cidx]["next"]) if f and len(f.get("cases") or []) > cidx else None
        if start is None or not start["name"].startswith(graph + "_"):
            bad.append(f"{FILE}: {first} doesn't go to {graph} before opening the chest")
            continue
        for room in rooms:
            top, bot = chests[room]
            same = [r for r in rooms if r != room and contents.get(chests[r][0]) == contents.get(top)]
            for open_bottoms, want in (({bot}, True), ({chests[r][1] for r in rooms if r != room}, bool(same))):
                got, skip = run(start, contents.get(top), {_opened(b) for b in open_bottoms}, opens)
                if got is None:
                    bad.append(f"{FILE}:{graph}: room {room}: {skip}")
                elif skip != want:
                    bad.append(f"{FILE}:{graph}: room {room} with {'its' if want and bot in open_bottoms else 'other'} "
                               f"Bottom(s) open {'sets' if skip else 'does not set'} {SKIP_POP}")
    # OpenTreasureBox's ways into the flag step all go through POP_CHECK
    q = by.get(f"{POP_CHECK}_q")
    if q is None or q["type"] != "switch" or act(q) != "EventQueryIsGameDataBool" or \
            prm(q, "GameDataName") != SKIP_POP:
        bad.append(f"{FILE}: no {POP_CHECK} reading {SKIP_POP}")
    else:
        yes, no = case(q, YES), case(q, NO)
        if no is None or no["name"] != POP_SET:
            bad.append(f"{FILE}:{POP_CHECK}: without {SKIP_POP} it doesn't go on to {POP_SET}")
        if yes is None or yes["type"] != "action" or act(yes) != "EventTriggerSetGameDataBool" or \
                prm(yes, "GameDataName") != SKIP_POP or prm(yes, "Value") or \
                (at(yes["next"]) or {}).get("name") != POP_AFTER:
            bad.append(f"{FILE}:{POP_CHECK}: with {SKIP_POP} it doesn't clear it and go on to {POP_AFTER}")
    for name, cidx in POP_EDGES:
        e = by.get(name)
        nxt = at(e["cases"][cidx]["next"]) if e is not None and cidx is not None else at(e.get("next")) if e else None
        if nxt is None or nxt["name"] != f"{POP_CHECK}_q":
            bad.append(f"{FILE}: {name} goes to {nxt and nxt['name']}, not {POP_CHECK}")
    tgt = by[POP_SET]["idx"] if POP_SET in by else None
    into = [e["name"] for e in ev if e["name"] != f"{POP_CHECK}_q" and tgt is not None and
            (e.get("next") == tgt or any(c["next"] == tgt for c in e.get("cases") or []))]
    if tgt is None:
        bad.append(f"{FILE}: no {POP_SET} (the pop flag step) in {OPEN_ENTRY}")
    elif into:
        bad.append(f"{FILE}: {into} still go to {POP_SET} around {POP_CHECK}")
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    if not any(r["Hash"] == murmur3_32(SKIP_POP) for r in gd["Data"]["Bool"]):
        bad.append(f"GameDataList: no Bool {SKIP_POP}")
    return bad


def verify_keyed(patch, note, romfs):
    """Reads the keyed modes back: the saved count, the start chain (every count 0..7 sets the right key number) and the
    skipped GetKey calls."""
    import os
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, os.path.join(here, "tools"))
    from romtools import Romfs, byml_load, murmur3_32
    from evfl import Evfl
    fs = Romfs(romfs, os.path.join(here, "original"), [patch])
    bad = []
    gd = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)[0]
    row = next((e for e in gd["Data"]["Int"] if e["Hash"] == murmur3_32(note["count"])), None)
    if row is None or row["SaveFileIndex"] != 0 or row["DefaultValue"] != 0:
        bad.append(f"GameDataList: {note['count']} is not a saved Int starting at 0 ({row})")
    fc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{FILE}.bfevfl.zs")).flowcharts if f["name"] == FILE)
    ev = fc["events"]
    by = {e["name"]: e for e in ev}

    def name(i):
        return ev[i]["name"] if i not in (None, 0xFFFF) and i < len(ev) else None

    def prm(e, k):
        return ((e.get("params") or {}).get("items") or {}).get(k, {}).get("value")
    for count in range(DOORS + 2):  # walk the chain for each found-key count
        e = by.get("Rando_TcgStart_keys")
        steps = 0
        while e is not None and e["type"] == "switch" and steps < 20:
            v = prm(e, "Value")
            case = 0 if count < v else 1 if count == v else 2
            e = by.get(name(next((c["next"] for c in e["cases"] if c["value"] == case), None)))
            steps += 1
        ok = e is not None and e["type"] == "action" and prm(e, "GameDataName") == KEYS
        want = min(count, DOORS)
        if ok and want:  # all but the last set, then the game's shop key (+1, the HUD's key counter)
            last = ev[e["next"]] if e["next"] not in (None, 0xFFFF) else None
            ok = prm(e, "Value") == want - 1 and last is not None and last["type"] == "subflow" and \
                (last.get("flowchart") or "") in ("", FILE) and last.get("entry_point") == GETKEY_SHOP and \
                name(last["next"]) == "Event58"
        elif ok:
            ok = prm(e, "Value") == 0 and name(e["next"]) == "Event58"
        if not ok:
            bad.append(f"{FILE}: with {count} keys found the game doesn't start with {want} keys (the last one "
                       f"through {GETKEY_SHOP})")
    bad += _shop_key_problems(fc)
    for evn, nxt in note["skip_getkey"]:
        if name(by[evn]["next"]) != nxt:
            bad.append(f"{FILE}: {evn} still calls GetKey (goes to {name(by[evn]['next'])})")
    # The keys' credit. Every step naming the count outside the start chain adds to it (+1 a key, +6 a ring) or calls
    # the shared key entry with it, and the shared entry adds its GameDataName argument by one.
    import re
    for fn in sorted(os.listdir(os.path.join(patch, "Event", "EventFlow"))):
        if ".bfevfl" not in fn or fn.startswith(FILE + "."):
            continue
        raw = fs.read(f"Event/EventFlow/{fn}")
        if KEY_COUNT.encode() not in raw:
            continue
        for f2 in Evfl(raw).flowcharts:
            for e in f2["events"]:
                items = ((e.get("params") or {}).get("items") or {})
                if items.get("GameDataName", {}).get("value") != KEY_COUNT:
                    continue
                if e["type"] == "action":
                    act = f2["actors"][e["actor"]]["actions"][e["action"]]
                    if act != "EventTriggerAddOrSubGameDataInt" or items.get("Value", {}).get("value") not in (1, DOORS):
                        bad.append(f"{fn}: {e['name']} {act} on {KEY_COUNT} is no key credit")
                elif e["type"] == "subflow":
                    if not re.fullmatch(r"Rando_DI_(Key|TcgKey|KeyRing_\w+)(_Big)?", e.get("entry_point") or ""):
                        bad.append(f"{fn}: {e['name']} passes {KEY_COUNT} to {e.get('entry_point')}")
    # the get message, each count 1..7 shows its own text
    pc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{AFTER_FILE}.bfevfl.zs")).flowcharts if f["name"] == AFTER_FILE)
    pev = pc["events"]
    pby = {e["name"]: e for e in pev}
    for count in range(1, DOORS + 2):
        e = pby.get(f"{AFTER_ENTRY}_q1")
        while e is not None and e["type"] == "switch":
            v = prm(e, "Value")
            case = 0 if count < v else 1 if count == v else 2
            nx = next((c["next"] for c in e["cases"] if c["value"] == case), None)
            e = pev[nx] if nx not in (None, 0xFFFF) else None
        want = MSG.format(f"Rando_TcgKey{count}" if count <= DOORS else "Rando_TcgKeyMore")
        if e is None or prm(e, "MessageId") != want:
            bad.append(f"{AFTER_FILE}:{AFTER_ENTRY}: count {count} doesn't show {want}")
    return bad


def _shop_key_problems(fc):
    """Problems if the game's shop-key entry (GETKEY_SHOP) no longer runs GETKEY_SHOP_STEPS (adding one key)."""
    ev = fc["events"]
    ent = fc["entry_points"].get(GETKEY_SHOP)
    if ent is None:
        return [f"{FILE}: no entry {GETKEY_SHOP}"]
    i = ent.get("main", ent.get("event", ent.get("start"))) if isinstance(ent, dict) else ent
    got = []
    while i not in (None, 0xFFFF) and len(got) < 10:
        e = ev[i]
        if e["type"] != "action":
            break
        a = fc["actors"][e["actor"]]["actions"][e["action"]]
        items = (e.get("params") or {}).get("items") or {}
        got.append((a, {k: v.get("value") for k, v in items.items()}))
        i = e.get("next")
    want_ok = len(got) == len(GETKEY_SHOP_STEPS) and all(
        a == wa and p.get(k) == v for (a, p), (wa, k, v) in zip(got, GETKEY_SHOP_STEPS)) and got[1][1].get("Value") == 1
    return [] if want_ok else [f"{FILE}:{GETKEY_SHOP} runs {[a for a, _ in got]}, not {GETKEY_SHOP_STEPS} (+1)"]


def check(romfs, vanilla_dir=None):
    """Problems if the vanilla files differ from what this patch assumes."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from romtools import Romfs
    from evfl import Evfl
    fs = Romfs(romfs, vanilla_dir)
    problems = []
    data = open(fs.path(SHUFFLE), "rb").read()
    if struct.unpack_from("<i", data, SHUFFLE_OFFSET)[0] != F32_HALF:
        problems.append(f"{SHUFFLE}: {SHUFFLE_OFFSET:#x} is not 0.5")
    fc = next(f for f in Evfl(fs.read(f"Event/EventFlow/{FILE}.bfevfl.zs")).flowcharts if f["name"] == FILE)
    by_idx = {e["idx"]: e["name"] for e in fc["events"]}
    by = {e["name"]: e for e in fc["events"]}
    if by_idx.get(by["Event57"].get("next")) != "Event54" or by_idx.get(by["Event54"].get("next")) != "Event58":
        problems.append("StartMinigame no longer runs Event57 -> Event54 (PassOnKey) -> Event58")
    rv = ((by["Event67"].get("params") or {}).get("items") or {}).get("ReceiveItem", {}).get("value")
    if rv != "Obj_MiniGame_SmallKey":
        problems.append(f"Event67 hands {rv!r}, not Obj_MiniGame_SmallKey")
    problems += _shop_key_problems(fc)
    # the partner fix's steps (partner_part): the hit scenes' opening call, the flag step and its three ways in
    for first, cidx, opens, _, _ in ROUTES.values():
        e = by.get(first)
        if e is None or by_idx.get(e["cases"][cidx]["next"]) != opens or by[opens].get("entry_point") != OPEN_ENTRY:
            problems.append(f"{first} case {cidx} no longer goes to {opens} calling {OPEN_ENTRY}")
    s = by.get(POP_SET)
    if s is None or ((s.get("params") or {}).get("items") or {}).get("GameDataName", {}).get("value") != POP_FLAG \
            or by_idx.get(s.get("next")) != POP_AFTER:
        problems.append(f"{POP_SET} no longer sets {POP_FLAG} before {POP_AFTER}")
    for name, cidx in POP_EDGES:
        e = by.get(name)
        nxt = (e["cases"][cidx]["next"] if cidx is not None else e.get("next")) if e else None
        if by_idx.get(nxt) != POP_SET:
            problems.append(f"{name} no longer goes to {POP_SET}")
    return problems
