"""The "events" section of the game-logic index, every event flow and the event tables (record shapes in SCHEMA.md).

Files indexed
  Event/EventFlow/*.bfevfl.zs     every version (X.bfevfl.zs, X.110.bfevfl.zs); the game reads the newest one
                                  (summary.newest). Older versions stay in by_file with "superseded_by".
                                  Flowchart files: flowcharts with compact events, entry points with their reach and
                                  classified ops (reads / writes / gives / item_queries). Timeline-only files
                                  (cutscenes): actors, call counts and the few state ops a clip makes (time of day).
  RSDB/EventSetting, GameAnalyzedEventInfo, GameEventBaseSetting, GameEventMetadata, EventPlayEnvSetting
                                  {"kind": "rsdb", "table", "rows": {row id: compact row}}
  Event/EventSetting/**, Event/ResidentEventList/*   {"kind": "setting", "type", "data"}

Conventions (beyond SCHEMA.md)
  An event's "call" is "Actor.Action" / "Actor.Query", or "Flow:Entry" for a sub-flow as the file has it (an empty Flow
  means the same flowchart). An entry's "calls" are normalised to "Flow:Entry". Params are flattened {path: value}. An
  argument the caller passes in is "<arg NAME>", and the caller's sub-flow call carries NAME as a param. A return step
  (type6) has "value", since its next field is the returned value. An event whose actor has a sub name has "sub". An
  action with no op keeps only its non-default params (see _slim), and camera / depth-of-field / developer-comment
  actions keep none.
  An op is {"event", "call", "kind", ...}, with kinds from the RULES table below (summary.classification). "guards" are
  the switch decisions on the shortest path from the entry's main event, as [{"event", "call", "params", "case",
  "cases"?}], where "cases" lists every case value that leads the same way when there are several. An entry's ops only
  cover its own reach, not sub-flows. Flowchart "dead_ops" are ops no entry reaches.
  Settings: an EventSetting row ("scene ID") names a flow file + entry point. Every row has a saved Bool
  HavePlayedEvent.<row id> in GameData. Flows read it and few set it, so the engine sets it when the setting is played
  (EventTransition, a warp's BootEventName, an AISchedule/level request). Those plays are ops of kind "play" with
  "implicit": true. A flow entered as a sub-flow call plays no setting, so a few flows set HavePlayedEvent.X themselves.

The summary only covers the newest version of each flow. Beyond SCHEMA.md it has step_queries {challenge: [ref+op]},
takes {item}, warps {banc or special}, plays {setting}, event_bools, time_sets, timeline_calls, classification
{verb: kinds}, partially_classified, played_flags and counts. An op whose flag/item/setting/destination is a caller's
argument gets indexed at each call site that passes it. There ref is the call site, "via" is the op inside the callee
and the guards are the call site's plus the op's. Step requests, gives and takes inside an entry that other flows call
carry "called_from", the call sites with their guards.

Run: python tools/gamedb/build.py --only events
"""
import os
import re
import sys
from collections import Counter, defaultdict, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402  (puts tools/ on sys.path)
from catalog import GIVE_PATTERNS, matches, walk_params  # noqa: E402
from evfl import Evfl  # noqa: E402

SECTION = "events"
VERSION = 2
PARALLEL = True

FLOWS = "Event/EventFlow"
SETTING_DIRS = ("Event/EventSetting", "Event/ResidentEventList")
RSDB_TABLES = ("EventSetting", "GameAnalyzedEventInfo", "GameEventBaseSetting", "GameEventMetadata",
               "EventPlayEnvSetting")
EVENT_SETTING = "RSDB/EventSetting.Product.111.rstbl.byml.zs"
ANALYZED = "RSDB/GameAnalyzedEventInfo.Product.111.rstbl.byml.zs"
RESIDENT = "Event/ResidentEventList/Default.engine__event__ResidentEventList.bgyml"
CHALLENGES = "RSDB/Challenge.Product.111.rstbl.byml.zs"
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
END = 0xFFFF
BUCKETS = ("reads", "writes", "gives", "item_queries")

_P = {}  # per-process cache for the challenge table and GameData hashes


def _short(path):
    """'Work/Event/EventFlow/SageOfFire.evfc' -> 'SageOfFire'."""
    return path.rsplit("/", 1)[-1].split(".", 1)[0] if isinstance(path, str) and path else path


def challenges(fs):
    """{challenge: [step names in order]} plus the raw rows (participants, ForceProgressGameData)."""
    if "ch" not in _P:
        rows = common.jsonable(common.read_byml(fs, CHALLENGES))
        _P["ch_rows"] = rows
        _P["ch"] = {_short(r["__RowId"]): [s["Name"] for s in r.get("Steps") or []] for r in rows}
    return _P["ch"]


def gamedata_hashes(fs):
    if "gd" not in _P:
        root = common.read_byml(fs, GAMEDATA)
        _P["gd"] = {int(r["Hash"]): t for t, rows in root["Data"].items() for r in rows if "Hash" in r}
    return _P["gd"]


def is_gd(fs, v):
    return isinstance(v, str) and v and not v.startswith("<arg ") and common.murmur3_32(v.encode()) in gamedata_hashes(fs)


# Files

def files(root):
    out = common.list_files(root, FLOWS, r"\.bfevfl\.zs$")
    for t in RSDB_TABLES:
        rel = f"RSDB/{t}.Product.111.rstbl.byml.zs"
        if os.path.isfile(os.path.join(root, rel)):
            out.append(rel)
    for sub in SETTING_DIRS:
        for dp, _, fns in os.walk(os.path.join(root, sub)):
            for f in fns:
                if re.search(r"\.b?g?yml(\.zs)?$", f):
                    out.append(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    return sorted(out)


def index_file(fs, rel):
    if rel.startswith(FLOWS + "/"):
        return index_flow(fs, rel)
    if rel.startswith("RSDB/"):
        return index_rsdb(fs, rel)
    return index_setting(fs, rel)


# Params

def flat(c):
    out = {}
    for path, it in walk_params(c):
        t, v = it["type"], it["value"]
        if t == "argument":
            v = f"<arg {v}>"
        elif t == "float":
            v = round(v, 4) if v == v else None
        elif t == "float_array":
            v = [round(x, 4) if x == x else None for x in v]
        elif t == "actor":
            v = v[0] + (f"[{v[1]}]" if v[1] else "")
        out[path] = v
    return out


# Actions that change nothing the logic reads (no op) drop params that are at their default, so false, "", 0.0, a
# zero vector, and int 0 in talk/balloon calls (choice labels, dialog options). Other ints stay, since MelodyType 0 is
# Zelda's Lullaby. These presentation-only actors keep no params at all (cameras, depth of field, developer comments).
PRESENTATION = {"EventCamera", "PostProcessingActor", "DevelopEventSystemActor"}


def _is_default(v, talk):
    if v is None or v is False or v == "":
        return True
    if type(v) is float:
        return v == 0.0
    if type(v) is int:
        return talk and v == 0
    return isinstance(v, list) and bool(v) and all(type(x) in (int, float) and x == 0 for x in v)


def _slim(call, p):
    actor, verb = call.split(".", 1)
    if actor in PRESENTATION:
        return {}
    talk = "Talk" in verb or "Balloon" in verb
    return {k: v for k, v in p.items() if not _is_default(v, talk)}


def is_arg(v):
    return isinstance(v, str) and v.startswith("<arg ") and v.endswith(">")


# Classification
# classify(event) -> [(bucket, op)], the saved game state an event reads or writes. It works on the compact event
# ({"name", "type", "call", "params"}) so finish() can re-run it for the catalogue.

RULES = {}  # verb (action or query name) -> f(d, actor, params) -> [(bucket, op)]
KINDS = {}  # verb -> kinds it can produce (for the report and the catalogue)


def rule(kinds, *verbs):
    def deco(f):
        for v in verbs:
            RULES[v] = f
            KINDS[v] = kinds
        return f
    return deco


def _op(d, kind, **kw):
    o = {"event": d["name"], "call": d["call"], "kind": kind}
    for k, v in kw.items():
        if v is not None:
            o[k] = v
    return o


_STEP_EXP = re.compile(r"^(?P<ch>.+?)_(?P<op>IsAfter|IsBefore|IsEqual|IsNotEqual)_(?P<step>.+)_Exp$")
_DONE_EXP = re.compile(r"^(?P<ch>.+?)_Is(?P<neg>Not)?Completed_Exp$")
_CMP = {"IsAfter": ">", "IsBefore": "<", "IsEqual": "=", "IsNotEqual": "!="}
_POUCH = re.compile(r"^PouchData\.(?P<item>[^.]+)\.")


def _flag(d, bucket, flag, value=None, index=None, **kw):
    """A GameData flag read or write, kind picked from its name (HavePlayedEvent./IsGet./HaveTalked./PouchData.)."""
    if index == -1:
        index = None
    kind, extra = kw.pop("kind", "bool"), {}
    if isinstance(flag, str):
        if flag.startswith("HavePlayedEvent."):
            kind, extra["setting"] = "played", flag[len("HavePlayedEvent."):]
        elif flag.startswith("IsGet."):
            kind, extra["item"] = "isget", flag[len("IsGet."):]
        elif flag.startswith("HaveTalked."):
            kind = "talked"
        elif _POUCH.match(flag):
            extra["item"] = _POUCH.match(flag).group("item")
    o = _op(d, kind, flag=flag, value=value, index=index, **extra, **kw)
    out = [(bucket, o)]
    if bucket == "reads" and "item" in extra:
        out.append(("item_queries", o))
    return out


def _step_of(ch, step):
    steps = _P.get("ch", {}).get(ch)
    return steps.index(step) if steps and step in steps else None


def _exp(d, name):
    """A BoolExp read. A challenge-step expression (<Challenge>_IsAfter_<Step>_Exp, _IsCompleted_Exp) is a
    step_query instead."""
    ch = _P.get("ch", {})
    if isinstance(name, str):
        m = _STEP_EXP.match(name)
        if m and m.group("ch") in ch and m.group("step") in ch[m.group("ch")]:
            return [("reads", _op(d, "step_query", flag=name, challenge=m.group("ch"), step=m.group("step"),
                                  cmp=_CMP[m.group("op")], step_index=_step_of(m.group("ch"), m.group("step"))))]
        m = _DONE_EXP.match(name)
        if m and m.group("ch") in ch:
            return [("reads", _op(d, "step_query", flag=name, challenge=m.group("ch"), step="Complete",
                                  cmp="!=" if m.group("neg") else "="))]
    return [("reads", _op(d, "exp", flag=name))]


# --- GameDataActor: flags

@rule("bool played isget talked", "EventQueryIsGameDataBool", "EventGameDataBoolWaitChangeValue",
      "EventWaitUntilGameDataTrueWithTimeOut")
def _r_bool(d, a, p):
    return _flag(d, "reads", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"))


@rule("bool played isget talked", "EventTriggerSetGameDataBool")
def _w_bool(d, a, p):
    return _flag(d, "writes", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"))


@rule("bool_array", "EventTriggerSetGameDataBoolArrayAllOnce")
def _w_bool_array(d, a, p):
    return _flag(d, "writes", p.get("GameDataName"), value=p.get("Value"), kind="bool_array")


@rule("exp step_query", "EventQueryIsGameDataBoolExp")
def _r_exp(d, a, p):
    return _exp(d, p.get("GameDataName"))


@rule("int", "EventQueryIsGameDataInt", "EventQueryGameDataIntBranch")
def _r_int(d, a, p):
    return _flag(d, "reads", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"), kind="int")


@rule("int", "EventTriggerSetGameDataInt")
def _w_int(d, a, p):
    return _flag(d, "writes", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"), kind="int", op="=")


@rule("int", "EventTriggerAddOrSubGameDataInt")
def _w_int_add(d, a, p):
    return _flag(d, "writes", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"), kind="int", op="+")


@rule("float", "EventTriggerAddOrSubGameDataFloat")
def _w_float_add(d, a, p):
    return _flag(d, "writes", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"), kind="float",
                 op="+", flag2=p.get("AddGameData") or None)


@rule("int", "EventTriggerSubGameDataInt")
def _w_int_sub(d, a, p):
    return _flag(d, "writes", p.get("GameDataA"), kind="int", op="-", flag2=p.get("GameDataB"))


@rule("copy", "EventTriggerCopyGameDataInt", "EventTriggerCopyGameDataFloat", "EventTriggerCopyGameDataString64")
def _w_copy(d, a, p):
    return [("writes", _op(d, "copy", flag=p.get("DstGameDataName"), flag2=p.get("SrcGameDataName")))]


@rule("enum step_query", "EventQueryIsGameDataEnum")
def _r_enum(d, a, p):
    f = p.get("GameDataName")
    if isinstance(f, str) and f.startswith("Step_") and f[5:] in _P.get("ch", {}):  # the challenge's step enum
        return [("reads", _op(d, "step_query", flag=f, challenge=f[5:], step=p.get("Value"), cmp="=",
                              step_index=_step_of(f[5:], p.get("Value"))))]
    return _flag(d, "reads", f, value=p.get("Value"), index=p.get("Index"), kind="enum")


@rule("enum step", "EventTriggerSetGameDataEnum")
def _w_enum(d, a, p):
    f = p.get("GameDataName")
    if isinstance(f, str) and f.startswith("Step_") and f[5:] in _P.get("ch", {}):
        return [("writes", _op(d, "step", flag=f, challenge=f[5:], step=p.get("Value"), direct=True))]
    return _flag(d, "writes", f, value=p.get("Value"), index=p.get("Index"), kind="enum")


@rule("float", "EventQueryIsGameDataFloat")
def _r_float(d, a, p):
    return _flag(d, "reads", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"), kind="float")


@rule("float", "EventTriggerSetGameDataFloat")
def _w_float(d, a, p):
    return _flag(d, "writes", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"), kind="float")


@rule("string", "EventQueryIsGameDataString64", "EventQueryIsEmptyGameDataString64")
def _r_string(d, a, p):
    v = p.get("Value", "" if d["call"].endswith("IsEmptyGameDataString64") else None)
    return _flag(d, "reads", p.get("GameDataName"), value=v, index=p.get("Index"), kind="string")


@rule("string", "EventTriggerSetGameDataString64")
def _w_string(d, a, p):
    return _flag(d, "writes", p.get("GameDataName"), value=p.get("Value"), index=p.get("Index"), kind="string")


@rule("compare", "EventQueryCompareGameDataInt", "EventQueryCompareGameDataFloat")
def _r_compare(d, a, p):
    return [("reads", _op(d, "compare", flag=p.get("GameDataA"), flag2=p.get("GameDataB"), cmp=p.get("Operator")))]


@rule("elapsed", "EventQueryCheckElapsedTime")
def _r_elapsed(d, a, p):
    return [("reads", _op(d, "elapsed", flag=p.get("GameDataName"),
                          value=f"{p.get('ElapsedHour', 0)}h{p.get('ElapsedMinute', 0)}m"))]


@rule("timestamp", "EventTriggerSetDayTimeStruct")
def _w_timestamp(d, a, p):
    return [("writes", _op(d, "timestamp", flag=p.get("GameDataName")))]


@rule("time", "EventExecuteSetTimeStruct")
def _w_time_struct(d, a, p):
    return [("writes", _op(d, "time", flag=p.get("GameDataName")))]  # world time from a saved time struct


@rule("played", "EventQueryHavePlayedEvent")
def _r_played(d, a, p):
    s = p.get("EventName")
    return [("reads", _op(d, "played", flag=f"HavePlayedEvent.{s}" if not is_arg(s) else s, setting=s))]


@rule("isget", "EventQueryCheckIsGet")
def _r_isget(d, a, p):
    it = p.get("ActorName")
    o = _op(d, "isget", flag=f"IsGet.{it}" if not is_arg(it) else it, item=it)
    return [("reads", o), ("item_queries", o)]


@rule("talked", "EventQueryCheckHaveTalked")
def _r_check_talked(d, a, p):
    it = p.get("ActorName")
    return [("reads", _op(d, "talked", flag=f"HaveTalked.{it}" if not is_arg(it) else it, actor=it))]


@rule("talked", "EventQueryHaveTalked", "EventQueryScrubBusinessIsFirstTalk")
def _r_talked(d, a, p):
    return [("reads", _op(d, "talked", flag=f"HaveTalked.{a}", actor=a))]


@rule("talked", "EventTriggerSetHaveTalked", "EventScrubBusinessWriteGameDataHaveTalked")
def _w_talked(d, a, p):
    return [("writes", _op(d, "talked", flag=f"HaveTalked.{a}", actor=a, value=p.get("value", True)))]


@rule("talk_flag", "EventQueryIsOnRecentTalkFlag", "EventQueryIsOnMaskTalkFlag", "EventQueryIsOnAmiiboMaskTalkFlag")
def _r_talk_flag(d, a, p):
    return [("reads", _op(d, "talk_flag", actor=a, which=d["call"].split(".", 1)[1][len("EventQueryIsOn"):]))]


@rule("talk_flag", "EventTriggerSetRecentTalkFlag", "EventTriggerForceSetRecentTalkFlag", "EventTriggerSetMaskTalkFlag",
      "EventTriggerForceSetMaskTalkFlag", "EventTriggerForceSetAmiiboMaskTalkFlag", "EventDisableRecentTalkFlag",
      "EventAIScheduleNPCForceResetMaskTalkFlag")
def _w_talk_flag(d, a, p):
    verb = d["call"].split(".", 1)[1]
    v = p.get("value", False if ("Disable" in verb or "Reset" in verb) else None)
    return [("writes", _op(d, "talk_flag", actor=a, which=re.sub(r"^Event(Trigger)?(Force)?(Set|Disable|AIScheduleNPCForceReset)", "", verb),
                           value=v))]


@rule("choice", "EventTriggerExcludeNextTalkChoice", "EventTriggerExcludeNextTalkChoiceAndSetActorName",
      "EventTriggerExcludeNextTalkChoiceAndSetActorNameForScrub")
def _r_choice(d, a, p):
    out = []
    for n in range(1, 6):
        f = p.get(f"ChoiceExcludeGameData{n}")
        if f:
            out.append(("reads", _op(d, "choice", flag=f, choice=n, invert=p.get(f"IsInvertGameData{n}") or None)))
    return out


@rule("actor_state", "EventQueryIsGoBackHome")
def _r_go_home(d, a, p):
    return [("reads", _op(d, "actor_state", actor=p.get("ActorName"), instance=p.get("InstanceName") or None))]


@rule("dog", "EventQueryGameDataCheckStrayDogTakenAway")
def _r_dog(d, a, p):
    return [("reads", _op(d, "dog"))]


@rule("dog", "EventStrayDogSetTakenAwayEnable", "EventStrayDogSetTakenAwayDisableAll")
def _w_dog(d, a, p):
    return [("writes", _op(d, "dog", value=d["call"].endswith("Enable")))]


# --- quest steps (challenges)

@rule("step", "EventExecuteProgressChallengeStep", "EventTriggerProgressChallengeStep")
def _w_step(d, a, p):
    ch, st = p.get("ChallengeName"), p.get("StepName")
    return [("writes", _op(d, "step", challenge=ch, step=st, ignore_completed=p.get("IsIgnoreCompletedChallenge"),
                           wait_end=p.get("IsWaitEnd"), ignore_ui=p.get("IsIgnoreChallengeProgressUI") or None,
                           step_index=_step_of(ch, st)))]


@rule("step_rollback", "EventExecuteRollbackChallengeStep")
def _w_step_back(d, a, p):
    ch, st = p.get("ChallengeName"), p.get("ChallengeStep")
    return [("writes", _op(d, "step_rollback", challenge=ch, step=st,
                           ignore_completed=p.get("IsIgnoreCompletedChallenge"), wait_end=p.get("IsWaitEnd"),
                           step_index=_step_of(ch, st)))]


@rule("record", "EventTriggerMiniGameCalcElapsedTime", "EventTriggerSetBestTimeInfoForBossRush")
def _w_record_gd(d, a, p):
    return [("writes", _op(d, "record", flag=v, param=k)) for k, v in p.items()
            if isinstance(v, str) and v and k not in ("LastBossRushBossCount",)]


@rule("record", "EventTriggerRecordBestTimeForDreamWorld", "EventTriggerRequestFlushForFishMiniGameScore")
def _w_record(d, a, p):
    return [("writes", _op(d, "record"))]


@rule("record", "EventQueryHaveRecordedTime", "EventQueryShouldUpdateBestTime")
def _r_record(d, a, p):
    return [("reads", _op(d, "record"))]


# --- items: gives, takes, queries

@rule("give take", "EventTriggerAddOrRemovePouchContent")
def _w_pouch(d, a, p):
    it, n = p.get("Actor"), p.get("Num", 1)
    if isinstance(n, int) and n < 0:
        return [("writes", _op(d, "take", item=it, num=n))]
    return [("gives", _op(d, "give", item=it, num=n if n != 1 else None, param="Actor",
                          get_event=p.get("IsGetEvent"), equip=p.get("IsEquipDIrect") or None))]


@rule("give", "EventTriggerPushToEmptyBottle")
def _w_bottle_fill(d, a, p):
    return [("gives", _op(d, "give", item=p.get("Item"), param="Item", bottle=True))]


@rule("give", "EventTriggerAddOwnToPouch")
def _w_guest(d, a, p):  # the item actor on stage adds itself (which one is decided at run time)
    return [("gives", _op(d, "give", item="<performer>", how="guest_performer"))]


@rule("give", "EventTriggerGetItemAtShop", "EventTriggerShopItemPutInPouch", "EventTriggerGetBottleItemAtShop")
def _w_shop_give(d, a, p):
    return [("gives", _op(d, "give", item="<shop item>", how="shop", get_event=p.get("IsGetEvent")))]


@rule("give", "EventTriggerBorrowMaskAtShop")
def _w_borrow(d, a, p):
    return [("gives", _op(d, "give", item="<mask>", how="borrow"))]


@rule("give", "EventCopyAndRegisterOwnedHorse")
def _w_horse(d, a, p):
    return [("gives", _op(d, "give", item=a, how="horse"))]


@rule("take", "EventTriggerRemoveFromSpecificBottle", "EventTriggerRemoveFromSelectedBottle",
      "EventTriggerConsumeDrinkFromSelectedBottle", "EventTriggerRemoveShopSelectedItemFromBottle")
def _w_bottle_take(d, a, p):
    return [("writes", _op(d, "take", item=p.get("Item", "<bottle>"), bottle=True))]


@rule("take", "EventTriggerRemoveWeaponKeepSheath")
def _w_take_weapon(d, a, p):
    return [("writes", _op(d, "take", item=p.get("Actor"), keep_sheath=True))]


@rule("take", "EventTriggerRemoveSwordBigGoronChallengeActor", "EventTriggerRemoveOwnedMask",
      "EventTriggerRequestDeletePlayerEquipmentFromPouch")
def _w_take_other(d, a, p):
    verb = d["call"].split(".", 1)[1]
    what = {"EventTriggerRemoveSwordBigGoronChallengeActor": "<Biggoron trade item>",
            "EventTriggerRemoveOwnedMask": "<mask>"}.get(verb, "<equipment>")
    return [("writes", _op(d, "take", item=what))]


@rule("pouch", "EventQueryIsExistInPouch")
def _q_pouch(d, a, p):
    return [("item_queries", _op(d, "pouch", item=p.get("Actor"), num=p.get("Num") if p.get("Num", 1) != 1 else None))]


@rule("pouch", "EventQueryIsExistInPouchWithNameGameData")
def _q_pouch_gd(d, a, p):
    o = _op(d, "pouch", flag=p.get("ActorName"), num=p.get("Num") if p.get("Num", 1) != 1 else None)
    return [("item_queries", o), ("reads", o)]


@rule("can_add", "EventQueryCanAddToPorch", "EventQueryCanAddToPorchByGameData")
def _q_can_add(d, a, p):
    if "GameDataForActorName" in p:
        o = _op(d, "can_add", flag=p["GameDataForActorName"])
        return [("item_queries", o), ("reads", o)]
    return [("item_queries", _op(d, "can_add", item=p.get("Actor")))]


@rule("equip", "EventQueryPlayerIsEquipArmor", "EventQueryPlayerIsEquipWeapon")
def _q_equip(d, a, p):
    return [("item_queries", _op(d, "equip", item=p.get("ArmorName"),
                                 slot=p.get("ArmorSlot", p.get("WeaponSlot"))))]


@rule("equip", "EventQueryPlayerIsEquipMask", "EventQueryCheckIsEquippedDynamicEquipment",
      "EventQueryPlayerIsEquipSinkLure", "EventQueryPlayerCheckSelectedItem")
def _q_equip_other(d, a, p):
    verb = d["call"].split(".", 1)[1]
    what = {"EventQueryPlayerIsEquipMask": "<mask>", "EventQueryPlayerIsEquipSinkLure": "<sinking lure>",
            "EventQueryPlayerCheckSelectedItem": "<selected item>"}.get(verb, "<dynamic equipment>")
    return [("item_queries", _op(d, "equip", item=what, slot=p.get("DynamicEquipmentSlot")))]


@rule("bottle", "EventQueryIsExistBottleTypeInPouch", "EventQueryHasAnyBottle", "EventQueryIsAnyBottleEmpty",
      "EventQueryGetBottleContent", "EventQueryIsGhostShopSellByBottleContent")
def _q_bottle(d, a, p):
    return [("item_queries", _op(d, "bottle", value=p.get("BottleItem")))]


@rule("count", "EventQueryTokenGoldNum", "EventQueryHeartPieceNum", "EventQueryIsObtainedSpiritBigPoeCount")
def _q_count(d, a, p):
    verb = d["call"].split(".", 1)[1]
    what = {"EventQueryTokenGoldNum": "Obj_Token_Gold", "EventQueryHeartPieceNum": "Obj_Heart_Piece"}.get(verb, "<Big Poe>")
    return [("item_queries", _op(d, "count", item=what, value=p.get("Value")))]


@rule("item_info", "EventQueryIsHeartPiece", "EventQueryIsSmallKey", "EventQueryIsFairy",
      "EventQueryIsMaxLifeUpPouchContent", "EventQueryIsRecoverHeartOrMpActor", "EventQueryCheckPouchContentCategory",
      "EventQueryCheckPouchContentCategoryFromGameData", "EventQueryPouchContentGetType",
      "EventQueryIsAutoSavePouchContent", "EventQueryCheckUIMessageTargetActorName",
      "EventQueryCheckUIMessageTargetBottleActorName", "EventQueryTreasureBoxCheckActorName",
      "EventQueryTreasureBoxIsDungeonCommonItemInside", "EventQueryCheckTagOnPouchActor")
def _q_item_info(d, a, p):
    """What kind of item a name is (static data), not whether Link has it."""
    flag = p.get("GameData") or p.get("GameDataName") or None
    o = _op(d, "item_info", item=p.get("ActorName") or None, flag=flag)
    return [("item_queries", o)] + ([("reads", o)] if flag else [])


@rule("string", "EventEffectStartGetItem", "EventTriggerSoundStartFanfare", "EventQueryIsOpenActionWindowFromGameData",
      "EventTriggerRecoverByCureItemForShop")
def _r_string_var(d, a, p):
    """Displays and helpers that read the item name from a String64 variable (shops)."""
    f = p.get("GameDataName") or p.get("GameData") or p.get("GameDataForActorName")
    return _flag(d, "reads", f, kind="string") if f else []


@rule("int", "EventQueryIsPlayedCurrentGradeSoundNumForSession", "EventTriggerPreparePlayExampleForSession")
def _r_int_var(d, a, p):
    return _flag(d, "reads", p.get("GameData"), kind="int")


@rule("played_get", "EventQueryGetHavePlayedGetEvent", "EventQueryHavePlayedGetEventAtShop")
def _r_played_get(d, a, p):
    return [("reads", _op(d, "played_get", item="<current item>"))]


@rule("played_get", "EventTriggerSetHavePlayedGetEvent", "EventTriggerSetHavePlayedGetEventAtShopFlag",
      "EventTriggerResetHavePlayedGetEventAtShopFlag")
def _w_played_get(d, a, p):
    return [("writes", _op(d, "played_get", item="<current item>", value="Reset" not in d["call"]))]


# --- money

@rule("rupees", "EventQueryHasRuppe", "EventQueryIsRupeeMax", "EventQueryCheckLoseMoneyIfSell",
      "EventQueryCheckLoseMoneyIfSellSome", "EventQueryCheckPorterSendRupeeLimit")
def _r_rupees(d, a, p):
    return [("reads", _op(d, "rupees", value=p.get("Value", p.get("Price"))))]


@rule("rupees", "EventTriggerIncreaseRupee", "EventPorterSendRupee", "EventTriggerIncreaseRupeeBySell",
      "EventTriggerPayItemPriceAtShop")
def _w_rupees(d, a, p):
    verb = d["call"].split(".", 1)[1]
    how = {"EventPorterSendRupee": "zelda_notes", "EventTriggerIncreaseRupeeBySell": "sell",
           "EventTriggerPayItemPriceAtShop": "shop_price"}.get(verb)
    return [("writes", _op(d, "rupees", value=p.get("Value", p.get("RupeeNum")), how=how))]


@rule("rupees", "EventTriggerAddGameDataIntToRupee")
def _w_rupees_gd(d, a, p):
    o = _op(d, "rupees", flag=p.get("GameDataName"), op="-" if p.get("IsSignInverse") else "+")
    return [("writes", o)]


# --- time, age, horse, misc saved state

@rule("time", "EventTrigger_SetTime")
def _w_time(d, a, p):
    h, m = p.get("TimeHour"), p.get("TimeMin", 0)
    v = f"{h:02d}:{m:02d}" if isinstance(h, int) and isinstance(m, int) else f"{h}:{m}"
    return [("writes", _op(d, "time", value=v))]


@rule("time", "EventTriggerSetIsTimeElapsedToNightByOcarinaSunSong")
def _w_sun_song(d, a, p):
    return [("writes", _op(d, "time", value="sun_song"))]


@rule("time", "EventQueryCheckTime", "EventQueryIsCurrentTimeInSpecifiedTimeRange", "EventQueryTimeDivision",
      "EventQueryGreetingTimeDivision", "EventQueryIsSunSongMakesMiddleTimeFromCurrentBanc")
def _r_time(d, a, p):
    if "Hour" in p:
        v = f"{p.get('CompareOparator')}{p.get('Hour')}:{p.get('Minute', 0)}"
    elif "StartTime" in p:
        v = f"{p.get('StartTime')}-{p.get('EndTme')}"
    else:
        v = None
    return [("reads", _op(d, "time", value=v))]


@rule("age", "EventQueryPlayerIsChild")
def _r_age(d, a, p):
    return [("reads", _op(d, "age"))]


@rule("horse", "EventQueryHasOwnedHorse", "EventQueryIsOwnedHorseInCurrentScene")
def _r_horse(d, a, p):
    return [("reads", _op(d, "horse"))]


@rule("melody", "EventTriggerSetScarecrowMelodyGameData", "EventTriggerSetPierreMelodyGameData")
def _w_melody(d, a, p):
    return [("writes", _op(d, "melody", what="pierre" if "Pierre" in d["call"] else "scarecrow"))]


@rule("gossip", "EventGameDataSetIsBlewOcarinaToGossipStone")
def _w_gossip(d, a, p):
    return [("writes", _op(d, "gossip", actor=a, value=p.get("IsBlewOcarina")))]


@rule("beans", "EventSmallFarmPlantedBeans")
def _w_beans(d, a, p):
    return [("writes", _op(d, "beans", actor=a, sub=d.get("sub")))]


@rule("mask_shop", "EventSetIsNotSelledMask")
def _w_mask_sale(d, a, p):
    return [("writes", _op(d, "mask_shop", actor=a, value=p.get("IsNotSelledMask")))]


@rule("shop", "EventTriggerAddShopItemSoldNum")
def _w_shop_sold(d, a, p):
    return [("writes", _op(d, "shop", what="sold_num"))]


@rule("string", "EventScrubBusinessWriteGameDataBancItemName", "EventScrubBusinessWriteGameDataLeastItemName")
def _w_scrub(d, a, p):
    return [("writes", _op(d, "string", actor=a, what=d["call"].split("WriteGameData", 1)[1]))]


@rule("warp_point", "EventTriggerSetDreamWorldWarpPoint", "EventTriggerFaroreWindSetActorPos")
def _w_warp_point(d, a, p):
    return [("writes", _op(d, "warp_point", what="dream_world" if "Dream" in d["call"] else "farore"))]


@rule("warp_point", "EventQueryIsExistWarpPointForFaroreWind")
def _r_warp_point(d, a, p):
    return [("reads", _op(d, "warp_point", what="farore"))]


# --- where a flow sends the player, and which event it plays next

@rule("warp play", "EventReserveBancChange")
def _w_warp(d, a, p):
    pos = p.get("NextPosition")
    dest = {k: v for k, v in (("banc", p.get("NextBanc")), ("start", p.get("NextStartPos")),
                              ("boot", p.get("BootEventName")), ("starter", p.get("EventStarterName")),
                              ("pos", pos if isinstance(pos, list) and any(pos) else None),
                              ("item_warp", p.get("IsItemWarp") or None)) if v not in (None, "")}
    out = [("writes", _op(d, "warp", dest=dest))]
    if dest.get("boot"):
        out += _play(d, dest["boot"], boot=True)
    return out


@rule("warp play", "EventReserveBancChangeForDreamWorld", "EventReserveBancChangeForFaroreWind",
      "EventReserveBancChangeForRematchBossStage", "EventPlayerWarpToDungeonEntrance")
def _w_warp_special(d, a, p):
    verb = d["call"].split(".", 1)[1]
    special = {"EventReserveBancChangeForDreamWorld": "dream_world", "EventReserveBancChangeForFaroreWind": "farore",
               "EventReserveBancChangeForRematchBossStage": "boss_rematch",
               "EventPlayerWarpToDungeonEntrance": "dungeon_entrance"}[verb]
    dest = {"special": special}
    if p.get("BootEventName"):
        dest["boot"] = p["BootEventName"]
    out = [("writes", _op(d, "warp", dest=dest))]
    if dest.get("boot"):
        out += _play(d, dest["boot"], boot=True)
    return out


def _play(d, setting, **kw):
    """Plays an event setting, which makes the engine set HavePlayedEvent.<setting> (implicit)."""
    flag = f"HavePlayedEvent.{setting}" if isinstance(setting, str) and not is_arg(setting) else setting
    return [("writes", _op(d, "play", setting=setting, flag=flag, implicit=True, **kw))]


@rule("play", "EventTransition")
def _w_transition(d, a, p):
    return _play(d, p.get("EventName"))


@rule("event_bool", "EventTriggerSetEventBool", "EventTriggerSetEventBoolEX1", "EventTriggerSetEventBoolEX2")
def _w_event_bool(d, a, p):
    """The requesting level logic's event bool (EventProxyRequestActor / EventRequestActor), read by its AINB."""
    slot = d["call"].split("SetEventBool", 1)[1] or None
    return [("writes", _op(d, "event_bool", value=p.get("Bool"), slot=slot, actor=a + (f"[{d['sub']}]" if d.get("sub") else "")))]


def classify(d):
    """[(bucket, op)] for a compact event."""
    t, call = d["type"], d.get("call")
    if not call:
        return []
    p = d.get("params") or {}
    if t in ("action", "switch"):
        actor, verb = call.split(".", 1)
        f = RULES.get(verb)
        if f:
            return f(d, actor, p)
        kind = t
    else:
        kind = "subflow"
    out = []
    for path, v in p.items():  # catalog.py's reward patterns (sub-flow hand-overs, Dampé's prize, ...)
        if isinstance(v, str) and matches(GIVE_PATTERNS, kind, call, path):
            out.append(("gives", _op(d, "give", item=v, param=path)))
    return out


# Flows

def _bfs(main, adj):
    if main == END or main >= len(adj):
        return [], {}
    parent, order, q = {main: None}, [main], deque([main])
    while q:
        i = q.popleft()
        for j, case in adj[i]:
            if j not in parent:
                parent[j] = (i, case)
                order.append(j)
                q.append(j)
    return order, parent


def _guards(i, parent, events, adj):
    out, j = [], i
    while parent.get(j) is not None:
        p, case = parent[j]
        if case is not None:
            vals = [c for t, c in adj[p] if t == j]
            # A one-case switch is a guard too, since any other value ends the flow. The quest-step audit caught this
            # at Dm_SY_BancChangeArrive Event165/Event160 on the path to Event158.
            if (len({t for t, _ in adj[p]}) > 1 or len(adj[p]) < len(events[p].get("cases", ()))
                    or len(events[p].get("cases", ())) == 1):
                e = events[p]
                g = {"event": e["name"], "call": e["call"], "case": case}
                if len(vals) > 1:
                    g["cases"] = vals
                if e.get("params"):
                    g["params"] = e["params"]
                out.append(g)
        j = p
    out.reverse()
    return out


def _flowchart(fc):
    names = [e["name"] for e in fc["events"]]
    n = len(names)

    def nm(i):
        return names[i] if i != END and i < n else None

    actors = [a["name"] + (f"[{a['sub_name']}]" if a["sub_name"] else "") for a in fc["actors"]]
    events, adj, ops_at = [], [], {}
    for i, e in enumerate(fc["events"]):
        t = e["type"]
        d = {"i": i, "name": e["name"], "type": t}
        succ = []
        if t in ("action", "switch"):
            a = fc["actors"][e["actor"]]
            verb = a["actions"][e["action"]] if t == "action" else a["queries"][e["query"]]
            d["call"] = f"{a['name']}.{verb}"
            if a["sub_name"]:
                d["sub"] = a["sub_name"]
        elif t in ("subflow", "subflow_switch"):
            d["call"] = f"{e['flowchart'] or ''}:{e['entry_point']}"
        p = flat(e.get("params"))
        if p:
            d["params"] = p
        if t in ("action", "subflow", "join") and nm(e["next"]):
            d["next"] = names[e["next"]]
            succ.append((e["next"], None))
        if t in ("switch", "subflow_switch"):
            d["cases"] = [[c["value"], nm(c["next"])] for c in e["cases"]]
            succ += [(c["next"], c["value"]) for c in e["cases"] if nm(c["next"])]
        if t == "fork":
            d["forks"] = [nm(j) for j in e["forks"]]
            succ += [(j, None) for j in e["forks"] if nm(j)]
            if nm(e["join"]):
                d["join"] = names[e["join"]]
                succ.append((e["join"], None))
        if t == "type6":  # a return step, its field is the value handed back to the caller and not a next step
            d["value"] = e["next"]
        ops = classify(d)
        if ops:
            ops_at[i] = ops
        elif t == "action" and p:
            p = _slim(d["call"], p)
            if p:
                d["params"] = p
            else:
                del d["params"]
        events.append(d)
        adj.append(succ)
    entries, reached = {}, set()
    for ep_name, ep in fc["entry_points"].items():
        order, parent = _bfs(ep["main"], adj)
        reached.update(order)
        ent = {"main": nm(ep["main"])}
        sfe = [nm(j) for j in ep["sub_flow_events"]]
        if sfe:
            ent["sub_flow_events"] = sfe
        if ep["variables"]:
            ent["variables"] = {k: v["type"] for k, v in ep["variables"].items()}
        ent["reach"] = [names[i] for i in order]
        calls, act = [], set()
        for i in order:
            for bucket, op in ops_at.get(i, ()):
                o = dict(op)
                g = _guards(i, parent, events, adj)
                if g:
                    o["guards"] = g
                ent.setdefault(bucket, []).append(o)
            d = events[i]
            if d["type"] in ("subflow", "subflow_switch"):
                f, entry = d["call"].split(":", 1)
                c = f"{f or fc['name']}:{entry}"
                if c not in calls:
                    calls.append(c)
            elif d["type"] in ("action", "switch"):
                act.add(d["call"].split(".", 1)[0])
        if calls:
            ent["calls"] = calls
        if act:
            ent["actors"] = sorted(act)
        entries[ep_name] = ent
    out = {"name": fc["name"], "actors": actors, "events": events, "entries": entries}
    dead = [dict(op, bucket=b) for i, ops in sorted(ops_at.items()) if i not in reached for b, op in ops]
    if dead:
        out["dead_ops"] = dead  # no entry reaches it, so it never runs
    return out


def _timeline(tl):
    calls, ops = Counter(), defaultdict(list)
    for kind in ("clips", "oneshots"):
        for k, x in enumerate(tl[kind]):
            a = tl["actors"][x["actor"]]
            call = f"{a['name']}.{a['actions'][x['action']]}"
            calls[call] += 1
            d = {"name": f"{kind[:-1]}{k}", "type": "action", "call": call, "params": flat(x.get("params"))}
            for bucket, op in classify(d):
                ops[bucket].append(dict(op, at=round(x.get("start", x.get("time", 0.0)), 2)))
    out = {"name": tl["name"], "duration": round(tl["duration"], 2),
           "actors": [a["name"] + (f"[{a['sub_name']}]" if a["sub_name"] else "") for a in tl["actors"]],
           "calls": dict(sorted(calls.items()))}
    if tl["subtimelines"]:
        out["subtimelines"] = tl["subtimelines"]
    out.update(ops)
    return out


def index_flow(fs, rel):
    challenges(fs)
    ev = Evfl(common.read_any(fs, rel))
    base, ver = common.versioned(rel)
    rec = {"base": base, "ver": ver}
    if ev.flowcharts:
        rec["flowcharts"] = [_flowchart(fc) for fc in ev.flowcharts]
    if ev.timelines:
        rec["timelines"] = [_timeline(tl) for tl in ev.timelines]
    return rec


# Tables and settings

def index_rsdb(fs, rel):
    table = os.path.basename(rel).split(".", 1)[0]
    rows = common.jsonable(common.read_byml(fs, rel))
    out = {}
    for r in rows:
        rid = r.pop("__RowId")
        if table == "EventSetting":
            c = {"flow": _short(r.get("FlowchartFileName")), "entry": r.get("EntryPointName"),
                 "timeline": _short(r.get("TimelineFileName")), "movie": r.get("MovieFileName"),
                 "file_type": r.get("EventFileType"), "components": _short(r.get("EventSettingComponentList")),
                 "base_setting": _short(r.get("EventBaseSetting")), "sub_timelines": r.get("SubTimelineNames"),
                 "start_wait": r.get("StartWaitFrame")}
            out[rid] = {k: v for k, v in c.items() if v not in (None, "", [])}
        elif table == "GameAnalyzedEventInfo":
            c = {"sub_flows": r.get("SubFlowList"), "children": r.get("ChildEventList"), "bgm": r.get("BgmNameList"),
                 "movie": r.get("ExistMovie")}
            c = {k: v for k, v in c.items() if v not in (None, "", [], False)}
            if c:
                out[rid] = c
        else:
            out[_short(rid)] = r
    return {"kind": "rsdb", "table": table, "count": len(rows), "rows": out}


def index_setting(fs, rel):
    data = common.jsonable(common.read_byml(fs, rel))
    parts = rel.split("/")
    rec = {"kind": "setting", "type": parts[-2] if parts[1] == "EventSetting" else parts[1], "data": data}
    if rel == RESIDENT:
        rec["events"] = [{"setting": _short(e.get("EventName")), **({"start_flag": e["StartGameData"]}
                                                                     if e.get("StartGameData") else {})}
                         for e in data.get("GlobalResidentEventList") or []]
    return rec


# Summary

ARG = re.compile(r"^<arg (?P<name>[^>]+)>$")
ARG_FIELDS = ("flag", "flag2", "item", "setting", "challenge", "step", "value")


def _args_in(op):
    out = {k for k in ARG_FIELDS if is_arg(op.get(k))}
    if isinstance(op.get("dest"), dict):
        out |= {f"dest.{k}" for k, v in op["dest"].items() if is_arg(v)}
    return out


def _substitute(op, params):
    """The op with its "<arg X>" fields replaced by the caller's params. None means the caller doesn't pass one."""
    new = dict(op)
    if isinstance(op.get("dest"), dict):
        new["dest"] = dict(op["dest"])
    for f in _args_in(op):
        tgt = new["dest"] if f.startswith("dest.") else new
        key = f[5:] if f.startswith("dest.") else f
        name = ARG.match(tgt[key]).group("name")
        if name not in params:
            return None
        tgt[key] = params[name]
    # Rebuild the played or isget flag from the resolved argument.
    if op.get("kind") in ("played", "play") and is_arg(op.get("flag")) and not is_arg(new.get("setting")):
        new["flag"] = f"HavePlayedEvent.{new['setting']}"
    if op.get("kind") == "isget" and is_arg(op.get("flag")) and not is_arg(new.get("item")):
        new["flag"] = f"IsGet.{new['item']}"
    return new


def _hashed_names(fs):
    """Row ids '<murmur challenge>_<murmur step>_<murmur actor>_<suffix>' -> readable names."""
    challenges(fs)
    strings = set()
    for r in _P["ch_rows"]:
        cn = _short(r["__RowId"])
        strings.add(cn)
        for s in r.get("Steps") or []:
            strings.add(s["Name"])
            for p in s.get("Participants") or []:
                strings.add(_short(p.get("ActorName")))
                if p.get("InstanceName"):
                    strings.add(p["InstanceName"])
                sc = _short(p.get("Schedule") or "")
                if sc and sc.startswith(f"{cn}_{s['Name']}_"):
                    strings.add(sc[len(f"{cn}_{s['Name']}_"):])
    d = os.path.join(fs.root, "Pack", "Actor")
    if os.path.isdir(d):
        strings |= {f.split(".", 1)[0] for f in os.listdir(d)}
    return {common.murmur3_32(s.encode()): s for s in strings if s}


def finish(fs, by_file):
    challenges(fs)
    gd = gamedata_hashes(fs)
    flows = [r for r in by_file if r.startswith(FLOWS + "/")]
    newest = common.newest_only(flows)
    newest_by_base = {by_file[r]["base"]: r for r in newest}
    for r in flows:  # older versions stay, flagged
        rec = by_file[r]
        if newest_by_base[rec["base"]] != r:
            rec["superseded_by"] = newest_by_base[rec["base"]]
        else:
            rec.pop("superseded_by", None)

    idx = {k: defaultdict(list) for k in ("setters", "readers", "step_requests", "step_queries", "gives", "takes",
                                          "item_readers", "warps", "plays")}
    event_bools, time_sets = [], []
    counts = {"flow_files": len(newest), "flowcharts": 0, "timeline_files": 0, "entries": 0, "events": 0,
              "ops": Counter(), "op_refs": 0, "dead_ops": 0, "older_versions": len(flows) - len(newest)}
    distinct = set()  # (file, flowchart, event, kind), so an op counts once however many entries reach it
    catalogue, tl_calls = {}, Counter()
    unclassified, partial = {}, {}
    callers = defaultdict(list)  # (callee flowchart, entry) -> [(file, fc, event, [caller entries])]
    pending = []                 # ops with "<arg X>" fields, as (file, fc, entry, op, bucket)
    fc_by_ref = {}

    def add(bucket, ref, op):
        e = dict(ref, **op)
        k = op["kind"]
        if bucket == "gives":
            if not is_arg(op.get("item")):
                idx["gives"][op.get("item")].append(e)
            return
        if bucket == "item_queries":
            if k != "item_info" and op.get("item") and not is_arg(op["item"]) and not op["item"].startswith("<"):
                idx["item_readers"][op["item"]].append(e)
            return
        # an op whose key is an argument is indexed where it is resolved (at its call sites, with "via")
        if k == "take" and op.get("item") and not is_arg(op["item"]):
            idx["takes"][op["item"]].append(e)
        if k in ("step", "step_rollback") and op.get("challenge") and not is_arg(op["challenge"]):
            idx["step_requests"][op["challenge"]].append(e)
        if k == "step_query" and op.get("challenge"):
            idx["step_queries"][op["challenge"]].append(e)
        if k == "warp":
            dest = op.get("dest") or {}
            key = dest.get("banc") or dest.get("special")
            if not is_arg(key):
                idx["warps"][str(key)].append(e)
        if k == "play" and op.get("setting") and not is_arg(op["setting"]):
            idx["plays"][op["setting"]].append(e)
        if k == "event_bool":
            event_bools.append(e)
        if k == "time" and bucket == "writes":
            time_sets.append(e)
        f = op.get("flag")
        if f and not is_arg(f):
            idx["setters" if bucket == "writes" else "readers"][f].append(e)
        f2 = op.get("flag2")
        if f2 and not is_arg(f2):
            idx["readers"][f2].append(e)

    for r in newest:
        rec = by_file[r]
        for tl in rec.get("timelines", ()):
            counts["timeline_files"] += 1
            tl_calls.update(tl.get("calls", {}))
            for bucket in BUCKETS:
                for op in tl.get(bucket, ()):
                    add(bucket, {"file": r, "fc": None, "entry": tl["name"]}, op)
                    counts["op_refs"] += 1
                    distinct.add((r, tl["name"], op["event"], op["kind"]))
        for fc in rec.get("flowcharts", ()):
            counts["flowcharts"] += 1
            counts["entries"] += len(fc["entries"])
            counts["events"] += len(fc["events"])
            counts["dead_ops"] += len(fc.get("dead_ops", ()))
            fc_by_ref[(r, fc["name"])] = fc
            ev2entries = defaultdict(list)
            for ep, ent in fc["entries"].items():
                for name in ent.get("reach", ()):
                    ev2entries[name].append(ep)
                ref = {"file": r, "fc": fc["name"], "entry": ep}
                for bucket in BUCKETS:
                    for op in ent.get(bucket, ()):
                        counts["op_refs"] += 1
                        distinct.add((r, fc["name"], op["event"], op["kind"]))
                        if _args_in(op) and op["kind"] != "item_info":
                            pending.append((r, fc["name"], ep, op, bucket))
                        add(bucket, ref, op)
            for d in fc["events"]:
                call = d.get("call")
                if not call:
                    continue
                if d["type"] in ("subflow", "subflow_switch"):
                    f, entry = call.split(":", 1)
                    callers[(f or fc["name"], entry)].append((r, fc["name"], d, ev2entries.get(d["name"], [])))
                    continue
                ops = classify(d)
                c = catalogue.get(call)
                if c is None:
                    c = catalogue[call] = {"n": 0, "type": "query" if d["type"] == "switch" else "action",
                                           "params": {}, "kinds": set()}
                c["n"] += 1
                c["kinds"].update(op["kind"] for _, op in ops)
                for k, v in (d.get("params") or {}).items():
                    ex = c["params"].setdefault(k, [])
                    if len(ex) < 3 and v not in ex:
                        ex.append(v)
                # a placement's InstanceName that happens to equal a GameData key is not a flag use
                gdp = [(k, v) for k, v in (d.get("params") or {}).items()
                       if is_gd(fs, v) and not k.endswith("InstanceName")]
                if not gdp:
                    continue
                seen = set()
                for _, op in ops:
                    for k, v in op.items():
                        if isinstance(v, str):
                            seen.add(v)
                for k, v in gdp:
                    if v in seen:
                        continue
                    tgt = partial if ops else unclassified
                    u = tgt.setdefault((call, k), {"call": call, "param": k, "type": gd[common.murmur3_32(v.encode())],
                                                   "n": 0, "examples": []})
                    u["n"] += 1
                    if len(u["examples"]) < 3 and v not in u["examples"]:
                        u["examples"].append(v)

    # ops whose flag/item/setting/destination is an argument get resolved at each call site ("via" is the op inside)
    resolved, unresolved = Counter(), Counter()
    guard_cache = {}

    def call_guards(file, fcname, entry, event_name):
        key = (file, fcname, entry)
        if key not in guard_cache:
            fc = fc_by_ref[(file, fcname)]
            names = {d["name"]: i for i, d in enumerate(fc["events"])}
            adj = []
            for d in fc["events"]:
                s = [(names[d["next"]], None)] if d.get("next") else []
                s += [(names[t], v) for v, t in d.get("cases", ()) if t]
                s += [(names[t], None) for t in d.get("forks", ()) if t]
                if d.get("join"):
                    s.append((names[d["join"]], None))
                adj.append(s)
            main = fc["entries"][entry]["main"]
            order, parent = _bfs(names[main] if main else END, adj)
            guard_cache[key] = (names, parent, fc["events"], adj)
        names, parent, events, adj = guard_cache[key]
        return _guards(names[event_name], parent, events, adj)

    work = [(r, fcn, ep, op, b, None, 0) for r, fcn, ep, op, b in pending]
    while work:
        r, fcn, ep, op, bucket, via, depth = work.pop()
        via = via or {"file": r, "fc": fcn, "entry": ep, "event": op["event"]}
        for cfile, cfc, cev, centries in callers.get((fcn, ep), ()):
            new = _substitute(op, cev.get("params") or {})
            if new is None:
                unresolved[op["kind"]] += 1
                continue
            new["event"], new["via"] = cev["name"], via
            if bucket == "gives" and any(b == "gives" for b, _ in classify(cev)):
                continue  # the call site is a hand-over itself (catalog.py pattern) and counts there
            for ce in centries:
                o = dict(new)
                g = call_guards(cfile, cfc, ce, cev["name"]) + list(op.get("guards", ()))
                if g:
                    o["guards"] = g
                else:
                    o.pop("guards", None)
                if _args_in(o):  # passed on from the caller's own caller
                    if depth < 4:
                        work.append((cfile, cfc, ce, o, bucket, via, depth + 1))
                    else:
                        unresolved[o["kind"]] += 1
                    continue
                add(bucket, {"file": cfile, "fc": cfc, "entry": ce}, o)
                resolved[o["kind"]] += 1

    # Step requests, gives and takes also list each sub-flow call site, with the switches that reach that site,
    # because the entry's guards only cover the callee.
    for key in ("step_requests", "gives", "takes"):
        for refs in idx[key].values():
            for e in refs:
                if e.get("via") or e.get("fc") is None:
                    continue
                cf = []
                for cfile, cfc, cev, centries in callers.get((e["fc"], e["entry"]), ()):
                    for ce in centries:
                        c = {"file": cfile, "fc": cfc, "entry": ce, "event": cev["name"]}
                        g = call_guards(cfile, cfc, ce, cev["name"])
                        if g:
                            c["guards"] = g
                        cf.append(c)
                if cf:
                    e["called_from"] = cf[:20]
                    if len(cf) > 20:
                        e["called_from_more"] = len(cf) - 20

    # settings: EventSetting rows -> flow file + entry point
    settings = {}
    es = (by_file.get(EVENT_SETTING) or {}).get("rows", {})
    analyzed = (by_file.get(ANALYZED) or {}).get("rows", {})
    resident = {e["setting"]: e for e in (by_file.get(RESIDENT) or {}).get("events", ())}
    hashed = _hashed_names(fs)
    for rid, row in es.items():
        s = {k: row[k] for k in ("flow", "entry", "timeline", "movie") if k in row}
        flow = row.get("flow")
        if not flow and row.get("timeline") in newest_by_base:
            s["file"] = newest_by_base[row["timeline"]]
        if flow:
            f = newest_by_base.get(flow)
            s["file"] = f
            if not f:
                s["missing"] = "flow"
            elif row.get("entry") and not any(row["entry"] in fc["entries"]
                                              for fc in by_file[f].get("flowcharts", ())):
                s["missing"] = "entry"
        m = re.match(r"^(\d+)_(\d+)_(\d+)_(.+)$", rid)
        if m:
            parts = [hashed.get(int(m.group(k))) for k in (1, 2, 3)]
            s["alias"] = "_".join(p or m.group(k + 1) for k, p in enumerate(parts)) + "_" + m.group(4)
            if parts[0]:
                s["challenge"], s["step"] = parts[0], parts[1]
        if analyzed.get(rid, {}).get("children"):
            s["children"] = analyzed[rid]["children"]
        if rid in resident:
            s["resident"] = True
            if resident[rid].get("start_flag"):
                s["start_flag"] = resident[rid]["start_flag"]
        if not common.murmur3_32(f"HavePlayedEvent.{rid}".encode()) in gd:
            s["no_played_flag"] = True
        settings[rid] = s

    explicit = sorted({f for f, refs in idx["setters"].items() if f.startswith("HavePlayedEvent.")
                       for e in refs if not e.get("implicit")})
    played = {"rule": "every EventSetting row X has a saved GameData Bool HavePlayedEvent.X; flows read it and only "
                      "a few set it, so the engine sets it when X is played as a setting (EventTransition, a warp's "
                      "BootEventName, an AISchedule or level-logic request); entering the same flow entry through a "
                      "sub-flow call plays no setting",
              "rows": len(es), "rows_with_flag": sum(1 for s in settings.values() if not s.get("no_played_flag")),
              "set_by_flows": explicit,
              "set_by_flows_not_a_setting": [f for f in explicit if f[len("HavePlayedEvent."):] not in es],
              "read_not_a_setting": sorted(f for f in idx["readers"] if f.startswith("HavePlayedEvent.")
                                           and f[len("HavePlayedEvent."):] not in es)}

    cat = {}
    for call, c in sorted(catalogue.items()):
        verb = call.split(".", 1)[1]
        cat[call] = {"n": c["n"], "type": c["type"], "params": c["params"]}
        if c["kinds"] or verb in KINDS:
            cat[call]["class"] = sorted(c["kinds"]) or KINDS[verb].split()
    counts["ops"] = dict(sorted(Counter(k for *_, k in distinct).items()))
    counts["resolved_arg_ops"] = dict(sorted(resolved.items()))
    counts["unresolved_arg_ops"] = dict(sorted(unresolved.items()))
    counts["settings"] = len(settings)
    sort = lambda d: {k: d[k] for k in sorted(d, key=str)}  # noqa: E731
    return {"newest": dict(sorted(newest_by_base.items())),
            "setters": sort(idx["setters"]), "readers": sort(idx["readers"]),
            "step_requests": sort(idx["step_requests"]), "step_queries": sort(idx["step_queries"]),
            "gives": sort(idx["gives"]), "takes": sort(idx["takes"]), "item_readers": sort(idx["item_readers"]),
            "warps": sort(idx["warps"]), "plays": sort(idx["plays"]), "event_bools": event_bools,
            "time_sets": time_sets, "calls_catalogue": cat, "timeline_calls": dict(sorted(tl_calls.items())),
            "classification": {v: KINDS[v] for v in sorted(KINDS)},
            "unclassified": sorted(unclassified.values(), key=lambda u: (u["call"], u["param"])),
            "partially_classified": sorted(partial.values(), key=lambda u: (u["call"], u["param"])),
            "settings": settings, "played_flags": played, "counts": counts}
