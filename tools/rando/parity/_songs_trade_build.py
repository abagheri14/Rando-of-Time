"""Builds data/rando/songs_trade_data.json, the scene steps the songs/trade/cows plugin (songs_trade.py) edits.
They're read from the game files (vanilla view), so the plugin can write patch plans without the romfs.

usage: python tools/rando/parity/_songs_trade_build.py ROMFS

What it records (every step name and routing is read from the files, and the build stops if a file differs from
what the plugin expects):
- songs: for each OoTR song location, the lesson calls in its scene (Dm_SY_Ocarina:LearningOcarinaPlayExample /
  FollowExample / PlayAuto / PlayAutoForSeek, with their MelodyType, next step and every step leading to them) and
  steps that set the vanilla song's IsGet flag (Sheik in Crater).
- melody: the score book (GameParameter/MelodyScoreBook): each song's notes, and the note value names.
- cows, frogs, gs100, loach: the steps the plugin hooks into (checked to exist with the expected call/params).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
from romtools import Romfs, byml_load  # noqa: E402
from evfl import Evfl  # noqa: E402
import progressive  # noqa: E402

OUT = os.path.join(HERE, "data", "rando", "songs_trade_data.json")

# OoTR song -> (remake pouch actor, MelodyType number used by Dm_SY_Ocarina and the score book order)
SONGS = {
    "Zeldas Lullaby": ("Item_Melody_ZeldaLullaby", 0), "Eponas Song": ("Item_Melody_EponaSong", 1),
    "Sarias Song": ("Item_Melody_SariaSong", 2), "Suns Song": ("Item_Melody_SunSong", 3),
    "Song of Time": ("Item_Melody_TimeSong", 4), "Song of Storms": ("Item_Melody_StormSong", 5),
    "Minuet of Forest": ("Item_Melody_ForestMinuet", 6), "Bolero of Fire": ("Item_Melody_FireBolero", 7),
    "Serenade of Water": ("Item_Melody_WaterSerenade", 8), "Requiem of Spirit": ("Item_Melody_SpiritRequiem", 9),
    "Nocturne of Shadow": ("Item_Melody_ShadowNocturne", 10), "Prelude of Light": ("Item_Melody_LightPrelude", 11),
}
# OoTR song location -> (vanilla song, scene files holding its lesson)
SONG_LOCATIONS = {
    "Song from Impa": ("Zeldas Lullaby", ["Dm_MelodyGet_Zelda"]),
    "Song from Malon": ("Eponas Song", ["Dm_MelodyGet_Epona"]),
    "Song from Saria": ("Sarias Song", ["Dm_MelodyGet_Saria"]),
    "Song from Royal Familys Tomb": ("Suns Song", ["Dm_MelodyGet_Sun"]),
    "Song from Ocarina of Time": ("Song of Time", ["Dm_MelodyGet_Time"]),
    "Song from Windmill": ("Song of Storms", ["Dm_MelodyGet_Storm"]),
    "Sheik in Forest": ("Minuet of Forest", ["Dm_MelodyGet_Forest"]),
    "Sheik in Crater": ("Bolero of Fire", ["Dm_MelodyGet_Fire"]),
    "Sheik in Ice Cavern": ("Serenade of Water", ["Dm_MelodyGet_Water"]),
    "Sheik at Colossus": ("Requiem of Spirit", ["Dm_MelodyGet_Spilit"]),
    "Sheik in Kakariko": ("Nocturne of Shadow", ["Dm_MelodyGet_Shadow"]),
    "Sheik at Temple": ("Prelude of Light", ["Dm_MelodyGet_Shine"]),
}
LESSON = {"LearningOcarinaPlayExample": "example", "LearningOcarinaFollowExample": "follow",
          "LearningOcarinaPlayAuto": "auto", "LearningOcarinaPlayAutoForSeek": "seek"}
SCORE_BOOK = "GameParameter/MelodyScoreBook/Default.game__ocarina__MelodyScoreBook.bgyml"
NOTE_NAMES = ("A", "Down", "Right", "Left", "Up")  # OoTR activation order: A v > < ^


class BuildError(Exception):
    pass


def versions(romfs, name):
    d = os.path.join(romfs, "Event", "EventFlow")
    rx = re.compile(re.escape(name) + r"(\.\d{3})?\.bfevfl\.zs$")
    found = sorted(f"Event/EventFlow/{f}" for f in os.listdir(d) if rx.match(f))
    if not found:
        raise BuildError(f"no event file {name}")
    return found


def step_info(fc, e):
    nxt = e.get("next")
    return {"event": e["name"],
            "next": fc["events"][nxt]["name"] if nxt is not None and nxt < len(fc["events"]) else None,
            "preds": [list(p) for p in progressive.predecessors(fc, e)]}


def params(e):
    out = {}
    for k, v in ((e.get("params") or {}).get("items") or {}).items():
        out[k] = v.get("value") if v["type"] != "container" else None
    return out


def wait_actor(fc):
    """An actor of this flowchart that already has the EventWait action (no new actor in the file)."""
    for a in fc["actors"]:
        if not a["sub_name"] and "EventWait" in a["actions"] and a["name"] in ("EventSystemActor", "GameSystemActor"):
            return a["name"]
    for a in fc["actors"]:
        if not a["sub_name"] and a["name"] in ("EventSystemActor", "GameSystemActor"):
            return a["name"]
    return "EventSystemActor"


def load_all(fs, romfs, name):
    """The flowchart of every version of a scene file. They have to agree on the steps the plugin uses."""
    return [(rel, Evfl(fs.read(rel)).flowcharts[0]) for rel in versions(romfs, name)]


def song_data(fs, romfs):
    out = {}
    for loc, (vanilla, files) in SONG_LOCATIONS.items():
        scenes = {}
        for name in files:
            per_version = []
            for rel, fc in load_all(fs, romfs, name):
                lesson, isget = [], []
                for e in fc["events"]:
                    if e["type"] == "subflow" and e.get("flowchart") == "Dm_SY_Ocarina" and e["entry_point"] in LESSON:
                        rec = step_info(fc, e)
                        rec["kind"] = LESSON[e["entry_point"]]
                        rec["entry"] = e["entry_point"]
                        rec["melody"] = params(e).get("MelodyType")
                        lesson.append(rec)
                    elif e["type"] == "action":
                        a = fc["actors"][e["actor"]]
                        if a["actions"][e["action"]] == "EventTriggerSetGameDataBool" and \
                                params(e).get("GameDataName") == f"IsGet.{SONGS[vanilla][0]}":
                            isget.append(step_info(fc, e))
                per_version.append((rel, {"flowchart": fc["name"], "lesson": lesson, "isget_sets": isget,
                                          "wait_actor": wait_actor(fc)}))
            first = per_version[0][1]
            for rel, d in per_version[1:]:
                if d != first:
                    raise BuildError(f"{rel}: lesson steps differ from {per_version[0][0]}")
            kinds = sorted({x["kind"] for x in first["lesson"]})
            if not first["lesson"] or "example" not in kinds or not ({"auto", "seek"} & set(kinds)):
                raise BuildError(f"{name}: no complete lesson found ({kinds})")
            vt = SONGS[vanilla][1]
            for x in first["lesson"]:
                if x["kind"] in ("example", "follow") and x["melody"] != vt:
                    raise BuildError(f"{name}:{x['event']}: MelodyType {x['melody']}, expected {vt}")
            scenes[name] = first
        out[loc] = {"vanilla": vanilla, "scenes": scenes}
    return out


def melody_data(fs):
    root, _ = byml_load(fs.raw(SCORE_BOOK))
    entries = root["MelodyScores"]
    if len(entries) != 12:
        raise BuildError(f"{SCORE_BOOK}: {len(entries)} songs, expected 12")
    # note values from the vanilla songs (OoTR's vanilla activations, SONG_TABLE order A v > < ^)
    vanilla = {"Zeldas Lullaby": "<^><^>", "Eponas Song": "^<>^<>", "Sarias Song": "v><v><", "Suns Song": ">v^>v^",
               "Song of Time": ">Av>Av", "Song of Storms": "Av^Av^", "Minuet of Forest": "A^<><>",
               "Bolero of Fire": "vAvA>v>v", "Serenade of Water": "Av>><", "Requiem of Spirit": "AvA>vA",
               "Nocturne of Shadow": "<>>A<>v", "Prelude of Light": "^>^><^"}
    sym = {"A": "A", "v": "Down", ">": "Right", "<": "Left", "^": "Up"}
    notes = {}
    for song, (_, t) in SONGS.items():
        score = [int(x) for x in entries[t]["MelodyScore"]]
        act = vanilla[song]
        if len(score) != len(act):
            raise BuildError(f"score book entry {t} ({song}): {len(score)} notes, OoTR's vanilla has {len(act)}")
        for c, v in zip(act, score):
            if notes.setdefault(sym[c], v) != v:
                raise BuildError(f"score book entry {t} ({song}): note {sym[c]} has two values")
    if sorted(notes) != sorted(NOTE_NAMES):
        raise BuildError(f"score book: notes found {sorted(notes)}")
    return {"file": SCORE_BOOK,
            "notes": notes,
            "entries": [{"index": i, "melody_type": int(e["MelodyType"]) if "MelodyType" in e else None,
                         "notes": [int(x) for x in e["MelodyScore"]]} for i, e in enumerate(entries)]}


def expect(fc, name, kind, check):
    e = next((x for x in fc["events"] if x["name"] == name), None)
    if e is None:
        raise BuildError(f"{fc['name']}: no step {name}")
    if kind == "call":
        got = f"{e.get('flowchart') or ''}:{e.get('entry_point')}"
    elif kind == "action":
        a = fc["actors"][e["actor"]]
        got = f"{a['name']}.{a['actions'][e['action']]}"
    else:
        a = fc["actors"][e["actor"]]
        got = f"{a['name']}.{a['queries'][e['query']]}"
    if got != check[0]:
        raise BuildError(f"{fc['name']}:{name} is {got}, expected {check[0]}")
    for k, v in (check[1] if len(check) > 1 else {}).items():
        if params(e).get(k) != v:
            raise BuildError(f"{fc['name']}:{name} {k}={params(e).get(k)!r}, expected {v!r}")
    return step_info(fc, e)


def single(fs, romfs, name):
    vs = load_all(fs, romfs, name)
    if len(vs) != 1:
        raise BuildError(f"{name}: {len(vs)} versions; the plugin edits one")
    return vs[0][1]


def cow_data(fs, romfs):
    fc = single(fs, romfs, "Animal_Cow")
    milk = ("Dm_SY_GetInEvent:GetInEventInBottle", {"ActorName": "Item_Bottle_Milk"})
    return {
        "file": "Animal_Cow",
        # generic Animal_Cow (HF grotto, LLR pair, Kakariko, DMT grotto): scene ID Animal_Cow_PushToBottleMilk
        "generic_start": expect(fc, "Event141", "query", ("PouchSystemActor.EventQueryIsExistBottleTypeInPouch",)),
        # Cow_GiveMilk after Epona's Song (the cow's Roar, Event1): Event3 hands over to the milk scene
        # (EventTransition to its EventName argument). The generic cows' gives go here, where the event's starter is
        # the cow itself, so its linked anchor answers the distance query (songs_trade.py _cow_ops)
        "generic_transition": expect(fc, "Event3", "action", ("EventSystemActor.EventTransition",)),
        "generic_after": expect(fc, "Event64", "action", ("Npc_EventStarter.EventTriggerSetVolatileGeneralPurposeFlag",)),
        "generic_milk": expect(fc, "Event4", "call", milk),
        # KF Link's house cow: its own scene ID Animal_Cow_PushToBottleMilk_LinkHouse
        "kf_start": expect(fc, "Event2", "query", ("PouchSystemActor.EventQueryIsExistBottleTypeInPouch",)),
        "kf_row": "Animal_Cow_PushToBottleMilk_LinkHouse",
        # GV (child) and GF (adult) cows: Cow_GiveMilk_gerudo calls PushToBottleMilk_LinkHouse0 after Epona's song
        "gerudo_give": expect(fc, "Event139", "call", (":PushToBottleMilk_LinkHouse0",)),
    }


def frog_data(fs, romfs):
    fc = single(fs, romfs, "MiniGame_FrogTenors")
    return {"file": "MiniGame_FrogTenors",
            # first time a song is played to the frogs: rupees by how many songs so far (5/10/15/20/30)
            "count_branch": expect(fc, "Event378", "query", ("GameDataActor.EventQueryGameDataIntBranch",
                                                              {"GameDataName": "MiniGame_FrogTenors_GetCount"})),
            "after_reward": expect(fc, "Event379", "action", ("UISystemActor.EventCloseRupeeDisplay",)),
            # the frogs' own give step (heart piece for the bug game), reused for the song items
            "heart_give": expect(fc, "Event384", "call", ("Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc",
                                                          {"ActorName": "Obj_Heart_Piece"}))}


def gs100_data(fs, romfs):
    fc = single(fs, romfs, "GatheringTokenGold")
    give = expect(fc, "Event471", "call", ("Dm_SY_GetInEvent:GetInEvent_NotTurn", {"ActorName": "Obj_Rupee_Gold"}))
    first = expect(fc, "Event141", "action", ("GameDataActor.EventTriggerSetGameDataBool",
                                               {"GameDataName": "HaveTalked_Special.GatheringTokenGold_FinishTalk_SkullDad_Event238"}))
    if first["next"] != "Event238":
        raise BuildError("GatheringTokenGold:Event141 no longer leads to Event238")
    # copy the first-time path after the flag, with our give in place of the gold rupee step
    nodes, start = progressive.clone(fc, "Event238", "first_", {"Event471": "give"})
    return {"file": "GatheringTokenGold", "give": give, "first_flag": first, "clone": nodes, "clone_start": start}


def loach_data(fs, romfs):
    fc = single(fs, romfs, "MiniGame_Fishing")
    purple = ("Dm_SY_GetInEvent:GetInEvent", {"ActorName": "Obj_Rupee_Purple"})
    keep = expect(fc, "Event226", "query", ("GameDataActor.EventQueryIsGameDataBool",
                                            {"GameDataName": "MiniGame_Fishing_KeepLoach"}))
    return {"file": "MiniGame_Fishing", "keep_loach": keep,
            "gives": [expect(fc, "Event374", "call", purple), expect(fc, "Event378", "call", purple)]}


def talon_data(fs, romfs):
    fc = single(fs, romfs, "Minigame_FindOutCucco")
    first = expect(fc, "Event23", "call", ("NpcCommon:NpcCommon_HandOver_NpcToPlayer_NoDisplay",
                                           {"ReveiveItem": "Item_Bottle_Milk"}))
    return {"file": "Minigame_FindOutCucco", "first_win": first,
            "reward_id": "event/Minigame_FindOutCucco/Minigame_FindOutCucco/Event23/ReveiveItem"}


def granny_data(fs, romfs):
    fc = single(fs, romfs, "Npc_Hylia_053_Adult")
    return {"file": "Npc_Hylia_053_Adult",
            "bottle_check": expect(fc, "Event15", "query", ("PouchSystemActor.EventQueryIsAnyBottleEmpty",)),
            "price": expect(fc, "Event179", "action", ("GameDataActor.EventTriggerSetGameDataInt",
                                                        {"GameDataName": "SimpleShop_Price", "Value": 100})),
            "give": expect(fc, "Event12", "call", ("Dm_SY_GetInEvent:GetInEventInBottle_BlueBottleShop",
                                                   {"ActorName": "Item_Bottle_BluePotion"}))}


def agreed(fs, romfs, name, build):
    """build(fc) on every version of a scene file. The versions have to agree, since the plugin edits them all."""
    results = [(rel, build(fc)) for rel, fc in load_all(fs, romfs, name)]
    for rel, r in results[1:]:
        if r != results[0][1]:
            raise BuildError(f"{rel}: steps differ from {results[0][0]}")
    return results[0][1]


def rolling_goron_data(fs, romfs):
    """GC Rolling Goron as Child (Npc_Goron_006_Child). After a stop in the perfect spot (Event7, Talk_03) the
    vanilla flow picks the next bomb bag by the pouch: Medium bag -> Large (Event14 -> Event12 -> Event94 ->
    Event92), Small bag -> Medium (Event13 -> Event21 -> Event54 -> Event58), no bag or the Large bag -> no gift
    (Talk_05). Both gifts then set GoronCity_GetBombBag_fromGoron006 (Event1), checked at Event2 before Event7."""
    fc = single(fs, romfs, "Npc_Goron_006_Child")
    bag = ":NpcCommon_HandOver_NpcToPlayer_NoDisplay_BombBag"
    stop = expect(fc, "Event7", "action", ("Npc_Goron_006_Child.EventTalk",
                                            {"MessageId": "EventFlowMsg/Npc_Goron_006_Child:Talk_03"}))
    if stop["next"] != "Event14":
        raise BuildError("Npc_Goron_006_Child:Event7 no longer leads to the bomb bag checks (Event14)")
    handover = expect(fc, "Event54", "action", ("Npc_Goron_006_Child.EventTalk",
                                                 {"MessageId": "EventFlowMsg/Npc_Goron_006_Child:Talk_29"}))
    if handover["next"] != "Event58":
        raise BuildError("Npc_Goron_006_Child:Event54 no longer leads to the Medium bag gift (Event58)")
    medium = expect(fc, "Event58", "call", (bag, {"ReveiveItem": "Item_BombBag_Medium"}))
    large = expect(fc, "Event92", "call", (bag, {"ReveiveItem": "Item_BombBag_Large"}))
    flag = expect(fc, "Event1", "action", ("GameDataActor.EventTriggerSetGameDataBool",
                                           {"GameDataName": "GoronCity_GetBombBag_fromGoron006"}))
    if medium["next"] != "Event1" or large["next"] != "Event1":
        raise BuildError("Npc_Goron_006_Child: a bomb bag gift no longer sets GetBombBag_fromGoron006 next")
    return {"file": "Npc_Goron_006_Child", "stop": stop, "handover": handover, "flag": flag,
            "reward_ids": ["event/Npc_Goron_006_Child/Npc_Goron_006_Child/Event58/ReveiveItem",
                           "event/Npc_Goron_006_Child/Npc_Goron_006_Child/Event92/ReveiveItem"]}


def dampe_dig_data(fs, romfs):
    """Graveyard Dampe Gravedigging Tour (Npc_Hylia_Dampe_001, two versions). The tough-ground dig (Event291
    DiggingHoleTour_Demo with DropActorName Obj_Heart_Piece) raises a heart piece out of the hole (Event82
    EventMiniGameDiggingHoleAdventActor) and Dampe talks (Event81). Then Event628
    (Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc_Dampe Obj_Heart_Piece) gives it while Event301 deletes the raised
    one. Event357 sets GraveYard_DiggingHoleTour_Drop_HeartPiece, and after that the tough ground gives rupees."""
    def build(fc):
        demo = expect(fc, "Event291", "call", (":DiggingHoleTour_Demo", {"DropActorName": "Obj_Heart_Piece"}))
        raise_hp = expect(fc, "Event82", "action", ("Npc_Hylia_Dampe_001.EventMiniGameDiggingHoleAdventActor",
                                                    {"ActorName": "Obj_Heart_Piece"}))
        give = expect(fc, "Event628", "call", ("Dm_SY_GetInEvent:GetInEvent_NotTurn_NotNpc_Dampe",
                                               {"ActorName": "Obj_Heart_Piece"}))
        flag = expect(fc, "Event357", "action", ("GameDataActor.EventTriggerSetGameDataBool",
                                                 {"GameDataName": "GraveYard_DiggingHoleTour_Drop_HeartPiece"}))
        if demo["next"] != "Event82" or raise_hp["next"] != "Event45":
            raise BuildError("Npc_Hylia_Dampe_001: the heart piece dig no longer runs Event291 -> Event82 -> Event45")
        return {"demo": demo, "raise": raise_hp, "give": give, "flag": flag}
    d = agreed(fs, romfs, "Npc_Hylia_Dampe_001", build)
    d.update(file="Npc_Hylia_Dampe_001",
             reward_id="event/Npc_Hylia_Dampe_001/Npc_Hylia_Dampe_001/Event628/ActorName")
    return d


def medigoron_data(fs, romfs):
    """GC Medigoron (Npc_Goron_Medigoron_Adult, Talk). If you own the Biggoron Sword (Event19) or the Giant's Knife
    (Event6) he only talks. Otherwise every branch sets SimpleShop_Price 200 (Event29) and sells through
    SimpleShop:SimpleShopRoot_Npc_Goron_Medigoron_Adult (Event11, ActorName Shop_Sword_Giant), whose success path
    (SimpleShop Event119, GetInEventItemSwordMedigoron) is his alone. There's no sold flag, so he sells again."""
    fc = single(fs, romfs, "Npc_Goron_Medigoron_Adult")
    first = expect(fc, "Event19", "query", ("PouchSystemActor.EventQueryIsExistInPouch",
                                            {"Actor": "Weapon_Sword_Biggoron"}))
    price = expect(fc, "Event29", "action", ("GameDataActor.EventTriggerSetGameDataInt",
                                             {"GameDataName": "SimpleShop_Price", "Value": 200}))
    sale = expect(fc, "Event11", "call", ("SimpleShop:SimpleShopRoot_Npc_Goron_Medigoron_Adult",
                                          {"ActorName": "Shop_Sword_Giant", "Price": 200}))
    goodbye = expect(fc, "Event4", "action", ("Npc_EventStarter.EventTalk",
                                              {"MessageId": "EventFlowMsg/Npc_Goron_Medigoron_Adult:Talk_03"}))
    shop = single(fs, romfs, "SimpleShop")
    # his root (SimpleShopRoot_Npc_Goron_Medigoron_Adult): choice (Event112) -> rupees (Event113) -> "can it go in
    # the pouch" (Event120, unknown answer for items that aren't swords) -> pay and hand over (Event114 ...
    # Event119) -> his thanks (Event169) -> the broken Giant's Knife is taken (Event25/Event115) -> autosave
    root = expect(shop, "Event112", "query", ("GameSystemActor.EventQueryTalkChoice2",))
    if "SimpleShopRoot_Npc_Goron_Medigoron_Adult" not in [p[1] for p in root["preds"] if p[0] == "entry"]:
        raise BuildError("SimpleShop:Event112 is no longer Medigoron's root")
    rupees = expect(shop, "Event113", "query", ("PouchSystemActor.EventQueryHasRuppe",))
    pouch = expect(shop, "Event120", "query", ("PouchSystemActor.EventQueryCanAddToPorch",))
    pay = expect(shop, "Event114", "action", ("Player_Event.EventTriggerParticipateEvent",))
    paid = expect(shop, "Event119", "call", ("Dm_SY_GetInEvent:GetInEventItemSwordMedigoron",))
    after = expect(shop, "Event169", "action", ("Npc_EventStarter.EventTalk",))
    broken = expect(shop, "Event25", "query", ("PouchSystemActor.EventQueryIsExistInPouch",
                                               {"Actor": "Weapon_Sword_BrokenGiant"}))
    save = expect(shop, "Event62", "action", ("GameSystemActor.EventTriggerRequestAutoSave",))
    if paid["next"] != "Event169" or [p[1] for p in after["preds"]] != ["Event119"] or after["next"] != "Event25":
        raise BuildError("SimpleShop: Medigoron's give (Event119) no longer leads only to Event169 -> Event25")
    if [p[1] for p in rupees["preds"]] != ["Event230"] or [p[1] for p in pouch["preds"]] != ["Event113"]:
        raise BuildError("SimpleShop: Medigoron's rupee/pouch checks are shared with another path")
    return {"file": "Npc_Goron_Medigoron_Adult", "first_check": first, "price": price, "sale": sale,
            "talk_03": goodbye, "shop_rupees": rupees, "shop_pay": pay, "shop_after_give": after,
            "shop_broken_check": broken, "shop_save": save,
            "reward_id": "event/Npc_Goron_Medigoron_Adult/Npc_Goron_Medigoron_Adult/Event11/ActorName"}


def granny_gate_data(fs, romfs):
    """Kak Granny Buy Blue Potion: Talk (Event119 Mask_All) -> Event29 IsAfter_Step03_03 -> Event30
    IsAfter_Step04 -> Event3 IsAfter_Step05_01 -> Event31 Buy_BluePotion: she sells only after the Odd Potion
    was shown to Fado (Step05_01 or later)."""
    fc = single(fs, romfs, "Npc_Hylia_053_Adult")
    gate = expect(fc, "Event29", "query", ("GameDataActor.EventQueryIsGameDataBoolExp",
                                           {"GameDataName": "SubEvent_GetSwordBigGoron_IsAfter_Step03_03_Exp"}))
    buy = expect(fc, "Event31", "call", (":Buy_BluePotion",))
    last = expect(fc, "Event3", "query", ("GameDataActor.EventQueryIsGameDataBoolExp",
                                          {"GameDataName": "SubEvent_GetSwordBigGoron_IsAfter_Step05_01_Exp"}))
    return {"gate": gate, "buy": buy, "last_gate": last}


def lake_data(fs, romfs):
    """LH Sun and LH Underwater Item (world pickups, _songs_trade_lake.py): the shared get scenes and the tag cases
    that tell the Fire Arrows (1: SubEvent_GetFireArrow:GetFireArrow) and Ruto's letter (0:
    Get_StoneOfWater:StoneOfWater_GetRutoletter) apart."""
    get = single(fs, romfs, "Dm_SY_Get")
    e119 = next(x for x in get["events"] if x["name"] == "Event119")
    if e119["type"] != "fork" or [p[1] for p in step_info(get, e119)["preds"]] != ["Event182"]:
        raise BuildError("Dm_SY_Get:Event119 is no longer the fork right after the player's event start (Event182)")
    expect(get, "Event182", "action", ("Player_Event.EventTriggerPlayerFadeVoice",))
    expect(get, "Event158", "action", ("Player_Event.EventTriggerPlayerEventStartWithDrawn",))
    hide = expect(get, "Event47", "action", ("PouchContentGuestPerformer.EventGoOffstageForUser",))
    death = expect(get, "Event124", "action", ("PouchContentGuestPerformer.EventTriggerRequestDeath",))
    for name, ev in (("Dm_SY_Get", "Event43"), ("Dm_SY_Get", "Event115")):
        expect(get, ev, "query", ("PouchContentGuestPerformer.EventQueryCheckTagOnPouchActor",))
    cases = lambda fc, ev: {c["value"]: fc["events"][c["next"]]["name"]
                            for c in next(x for x in fc["events"] if x["name"] == ev)["cases"]}
    if cases(get, "Event43")[0] != "Event41" or cases(get, "Event115")[1] != "Event44":
        raise BuildError("Dm_SY_Get: tag 0 / tag 1 no longer lead to the letter / Fire Arrow steps")
    expect(get, "Event41", "call", ("Get_StoneOfWater:StoneOfWater_GetRutoletter",))
    expect(get, "Event44", "call", ("SubEvent_GetFireArrow:GetFireArrow",))
    wp = single(fs, romfs, "Dm_SY_Get_WithoutPlayer")
    first = expect(wp, "Event15", "action", ("SoundSystemActor.EventTriggerSoundStartFanfare",))
    if ["entry", "Dm_SY_Get_WithoutPlayer", None] not in first["preds"]:
        raise BuildError("Dm_SY_Get_WithoutPlayer no longer starts at Event15")
    wp_hide = expect(wp, "Event6", "action", ("PouchContentGuestPerformer.EventGoOffstageForUser",))
    wc = cases(wp, "Event9")
    if wc[0] != "Event7" or wc[1] != "Event10":
        raise BuildError("Dm_SY_Get_WithoutPlayer: tag 0 / tag 1 no longer lead to the letter / Fire Arrow steps")
    return {"scenes": {"Dm_SY_Get": {"hook": step_info(get, e119), "hide": hide, "death": death},
                       "Dm_SY_Get_WithoutPlayer": {"hook": first, "hide": wp_hide}}}


def main(romfs):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    granny = granny_data(fs, romfs)
    granny.update(granny_gate_data(fs, romfs))
    data = {"_about": __doc__.strip().splitlines()[0],
            "songs": song_data(fs, romfs), "melody": melody_data(fs), "cows": cow_data(fs, romfs),
            "frogs": frog_data(fs, romfs), "gs100": gs100_data(fs, romfs), "loach": loach_data(fs, romfs),
            "talon": talon_data(fs, romfs), "granny": granny,
            "rolling_goron": rolling_goron_data(fs, romfs), "dampe_dig": dampe_dig_data(fs, romfs),
            "medigoron": medigoron_data(fs, romfs), "lake": lake_data(fs, romfs),
            "song_types": {k: v[1] for k, v in SONGS.items()}, "song_actors": {k: v[0] for k, v in SONGS.items()}}
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1)
    n = sum(len(s["lesson"]) for v in data["songs"].values() for s in v["scenes"].values())
    print(f"{len(data['songs'])} song locations ({n} lesson steps), score book {len(data['melody']['entries'])} "
          f"songs -> {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except BuildError as e:
        sys.exit(f"build error: {e}")
