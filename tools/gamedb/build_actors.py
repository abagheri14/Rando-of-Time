"""Actors section of the game-logic index, what each actor pack says about item hold-ups, lifting, breaking and saving.

Files indexed are Pack/Actor/*.pack.zs with one record each, the RSDB tables PouchActorInfo / ActorInfo /
GameActorInfo / Tag / TagDef ({"kind": "rsdb"}), GameParameter/GetDemoParam ({"kind": "getdemo"}), and the menu slot
tables UI/Pouch/PouchTable and BottleTable ({"kind": "pouch_table"}, which pouch actors share one menu slot).

How a pack is read
- An ActorParam names its components as "?Component/X/Name.<type>.bgyml", which is the inner path in the pack. Its
  parent is "Work/Actor/P.engine__actor__ActorParam.gyml", meaning inner "Actor/P.engine__actor__ActorParam.bgyml", and
  every parent sits in the same pack (all 8,373 packs checked). Components merge parent first with the child over it.
  Every component file can have a $parent too, merged the same way. A component the pack names but doesn't hold is an
  engine default ("absent").
- AI comes from AIInfo RootAIRef / PostCalcAIRef / PostSensorAIRef ("Work/AI/Root/X.root.ain" = "AI/X.root.ainb") and
  the EventPerformer's EventUniqueAin, plus the modules those files name. We look for them in the pack, then in
  Pack/AI.Global, then in AI/.
- Enum fields are murmur3_32 hashes of their names. ENUM_NAMES, the RSDB strings and GameDataList's enum values decode
  them, and an unknown one stays an int.

Record (Pack/Actor/<A>.pack.zs), beyond SCHEMA.md's fields:
  "absent": {ref: file name}, "logic_node": ActorLogicNodeRef node, "game_data_setting": ActorGameDataSetting name,
  "notes": [...],
  "holdup": {"event_object_base", "as_getdemo", "animation_param", "getdemo_event", "complete", "proof", "as",
             "getdemo_offset"}  (getdemo_event: the event AI has the item-get commands
             EventTriggerModelBindForItemGetDemo / EventTriggerAddOwnToPouch, as PouchContent.event.root has and
             Common.event.root lacks; complete = as_getdemo + animation_param + getdemo_event; "proof" names the
             inner files),
  "lift": {"grade", "need", "file", "grade_default", "liftableType", "putThrowPossibility", "special_deal"},
  "lifter": [{"grade", "file"}] (the player packs' PlayerLifterParam),
  "pouch": merged PouchContentParam (+ "assignable", "ocarina", "expansion" = ExpansionAbilityActor, "defaults_from"),
  "damage": {"life", "rates" (other than 0/1), "immune" (rate 0), "rate_1", "exceptions", "impulse_damage",
             "invincible", "brittleness", "sensor", "hammer", "fall_break", "cuttable_sign", "death": {"accepted",
             "sets_respawn_flag"}, "chemical", "breakers", "how": {attack: why}, "files"},
  "attacks": [[damage type, [elements], [attributes]]] (what the actor's own AttackParam deals),
  "saves": [{"flag"|"key", "how", "value", "struct", "member", "ai", "node", "gamedata": {"type", "save", "reset"}}]
           (AI GameData writes; "member" <placement hash> / <actor> / <controller placement hash> for struct members,
           <actor> filled in; "placement Bool64bitKey" for OneShotActorChangeIsRespawn and non-AlwaysRespawn
           ActorGameDataSetting; blackboard U64 *GmdHash keys; DefeatedNumGameDataName counters),
  "gamedata_refs": [{"flag"|"key", "field", "file"}] (GameData names the actor's files or blackboards carry),
  "ai": [inner ainb paths], "ai_missing": [...], "push": {...} (push/pull blocks).
Summary: pouch, lift_grades, breakers, breaker_notes, attack_model, holdup_incomplete, holdup_risk, holdup_parts,
shared_pouch_slots (+ _rule), bottle_contents.

Damage model
This is a heuristic read from the files. An attack (ATTACKS, damage type + element + attribute) hurts an actor whose
LifeParam has DamageParameters when its DamageRates entry is > 0. The 19 core types are listed in every file and an
unlisted type counts 1.0. That's after the ExternalDamageExceptionDefines and the SensorHitParam black/white lists.
The rule names (Ignore, OnlyThese, AddDamage, MultiplyRate) are inferred from their Japanese comments. The hit only
kills it if the DeathParam procedures (System/CombinationDataTableData, merged over Default) don't ignore LifeDepleted.
Bombs also kill through the chemical "Exploded" death (ChemicalParam RequestDeathIfExploded) and fire through
"Burned" (RequestDeathIfBurned and a material with IsBurn).
TODO: the AI can still refuse a hit (signboards, switches). That's still open, per actor.
Components left out of "components" because they're cosmetic: COSMETIC.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from common import byml_load, murmur3_32  # noqa: E402

import ainb as AINB  # noqa: E402  (tools/ is on sys.path through common)

SECTION = "actors"
VERSION = 1
# records read these too, so a patch holding one re-indexes every pack (build.py)
REBUILD_ON = (r"^System/CombinationDataTableData/", r"^Pack/AI\.Global", r"^AI/", r"^GameData/GameDataList",
              r"^UI/Pouch/", r"^RSDB/PouchActorInfo")

RSDB_TABLES = ("PouchActorInfo", "ActorInfo", "GameActorInfo", "Tag", "TagDef")
POUCH_TABLES = ("UI/Pouch/PouchTable", "UI/Pouch/BottleTable")
GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
AI_GLOBAL = "Pack/AI.Global.Product.111.pack.zs"
DEATH_DIR = "System/CombinationDataTableData"

COSMETIC = {"ModelInfoRef", "LODRef", "ELinkRef", "SLinkRef", "XLinkRef", "LocalDepthShadowRef", "CaptureRef",
            "NavMeshObjectRef", "PreActorSettingRef", "SystemSetting", "ModelBindRef", "BancPrimitiveModelComponentRef",
            "SoundFootStepRef", "CustomDebugObjectRef", "ClickMenuRef", "Sketch", "ASOptimize",
            "ActorPositionCalculatorRef", "AttentionSenderRef", "VoiceRef", "FoliageInteractRef", "SweepOutRef",
            "ReplaceTextureRef", "AnimeDrivenMoveRef", "LookIKRef", "GameModelControllerRef", "SnapshotRef",
            "ActiveCameraAlphaRef", "DuplicatedModelRef", "FittingModelToSlopeRef", "BgmAnimationSyncInfoRef"}

# Enum names the files store as hashes (murmur3_32 of the name). I found these by hashing the game's strings, and
# the rest get decoded from the RSDB tables and GameDataList enums at run time.
ENUM_NAMES = """
None Low Middle High Default Normal Material KeyItem CureItem Rupee Arrow Bow Weapon Shield Armor HeadArmor Boot
Small Medium Large Heart Item Equipment Ocarina Hookshot Longshot Bomb Bombchu Pot Rock Grass Fish Random Zero
Hammer ThrustWeapon Shockwave Fire Body SlingshotBullet SmallWeapon LargeWeapon Spike Undefined Bottle Boomerang
Impulse Durability Beam Electric Gust Ice Water Miasma Ancient Frozen Light DekuNut DekuStick Blunt PlayerRolling
GuardBreak ReleaseRestraint ComboFinish NoDurabilityDamage Player Enemy Neutral Friendly DomesticAnimal Quadruped
Time Fairy SmallSword LargeSword Spear AlwaysRespawn NoRespawn SupplyObject BancReset BancResetNoItemWarp
""".split()

# ExternalDamageExceptionDefines rule hashes. The names aren't in the game's strings, so these follow the comments in
# the files:
# - 204148089 is "invalid attack" / "ice damage invalid"
# - 1113656608 is "doesn't break except with light arrows"
# - 3355902107 adds Rule_AddDamageAmount, "breaks when the player rolls into it"
# - 3425723885 is "light arrow damage x4"
EXCEPTION_RULES = {204148089: "Ignore", 1113656608: "OnlyThese", 3355902107: "AddDamage", 3425723885: "MultiplyRate"}

# The player's attacks as (name, damage type, element, attribute), taken from these AttackParams:
# - Player/Player_Child (SmallWeapon, LargeWeapon, Hammer, Bottle, Body+PlayerRolling)
# - PlayerShockWave (Shockwave+Hammer)
# - NormalArrow (Arrow, elements Fire/Frozen/Light)
# - Shootable_DekuSeed, Shootable_Hook (Hookshot), Item_Boomerang
# - Item_DekuNut (Body+DekuNut)
# - ExpandFireField (Din's Fire, Fire+Fire)
# - ExplosionBase / BombFruit (Bomb+Bomb)
# WeaponParam WeaponType is SmallSword for the Kokiri and Master Sword, and LargeSword for the Deku Stick, Giant's Knife
# and Biggoron Sword. Grass refuses the attribute Blunt ("can't be cut with a Deku Stick"), so the stick's hits carry
# Blunt.
ATTACKS = [
    ("sword", "SmallWeapon", None, None),
    ("big_sword", "LargeWeapon", None, None),
    ("deku_stick", "LargeWeapon", None, "Blunt"),
    ("hammer", "Hammer", None, None),
    ("hammer_shockwave", "Shockwave", "Hammer", None),
    ("bomb", "Bomb", "Bomb", None),
    ("arrow", "Arrow", None, None),
    ("fire_arrow", "Arrow", "Fire", None),
    ("ice_arrow", "Arrow", "Frozen", None),
    ("light_arrow", "Arrow", "Light", None),
    ("slingshot", "SlingshotBullet", None, None),
    ("hookshot", "Hookshot", "Hookshot", None),
    ("boomerang", "Boomerang", "Boomerang", None),
    ("deku_nut", "Body", "DekuNut", None),
    ("roll", "Body", None, "PlayerRolling"),
    ("thrown_object", "Body", None, None),
    ("dins_fire", "Fire", "Fire", None),
    ("bottle", "Bottle", None, None),
]
FIRE_SOURCES = ("dins_fire", "fire_arrow", "deku_stick_lit")  # set a burnable actor alight (Burned death)
# Attacks the files give a rate for (1.0 in most DamageRates) that probably never connect in play. They stay in
# "how" with "(unsure)" but don't go in "breakers". A bottle swing "hurting" a crack wall is just a default nobody
# tuned.
UNSURE = {"bottle"}

LIFT_NEED = {"None": "nothing", "Low": "Goron Bracelet", "Middle": "Silver Gauntlets", "High": "Golden Gauntlets"}

GETDEMO_COMMANDS = ("EventTriggerModelBindForItemGetDemo", "EventTriggerAddOwnToPouch")
GD_WRITE = re.compile(r"^(OneShot|Execute|EventTrigger)\w*?(Set|Add|Sub|Copy|Multiply)\w*GameData"
                      r"|^OneShotActorChangeIsRespawn$|^OneShotInstanceGameDataSetBool$|RespawnFlag|GmdHash"
                      r"|^OneShotNaviSetNaviFlag$|^OneShotSet(Scarecrow|Pierre)\w*GameData$")
# GameData names a write builds from the actor. The struct member is the placement hash, the actor name, ...
MEMBER_SOURCES = {"QueryGenericGetInstanceId": "<placement hash>", "QueryGenericGetActorName": "<actor>",
                  "QueryDoorChainLockGetControllerInstanceId": "<controller placement hash>"}

_P = {}  # per-process caches


# Files

def files(root):
    out = common.list_files(root, "Pack/Actor", r"\.pack\.zs$")
    rx = r"^(" + "|".join(RSDB_TABLES) + r")\.Product\.\d+\.rstbl\.byml\.zs$"
    out += common.newest_only(common.list_files(root, "RSDB", rx))
    out += common.list_files(root, "GameParameter/GetDemoParam", r"\.bgyml$")
    for d in POUCH_TABLES:
        out += common.list_files(root, d, r"\.bgyml$")
    return out


def index_file(fs, rel):
    if rel.startswith("Pack/Actor/"):
        return index_pack(fs, rel)
    if rel.startswith("RSDB/"):
        return index_rsdb(fs, rel)
    if rel.startswith("UI/Pouch/"):
        return index_pouch_table(fs, rel)
    return {"kind": "getdemo", "data": common.jsonable(common.read_byml(fs, rel))}


# Process caches

def _ctx(fs):
    key = (fs.root, tuple(fs.overlays))
    if _P.get("key") != key:
        _P.clear()
        _P["key"] = key
    return _P


def _gamedata(fs):
    """GameDataList as {hash32: (type, SaveFileIndex, ResetTypeValue)} plus its enum names.
    The Bool64bitKey rows are left out."""
    c = _ctx(fs)
    if "gd" not in c:
        root = common.read_byml(fs, GAMEDATA)
        gd, enums = {}, set()
        for t, rows in (root.get("Data") or {}).items():
            if t == "Bool64bitKey":
                continue
            for r in rows:
                gd[int(r["Hash"])] = (t, int(r.get("SaveFileIndex", -1)), int(r.get("ResetTypeValue", 0)))
                enums.update(str(v) for v in r.get("RawValues") or [])
        c["gd"], c["gd_enums"] = gd, enums
    return c["gd"]


def _names(fs):
    c = _ctx(fs)
    if "names" not in c:
        words = set(ENUM_NAMES)
        _gamedata(fs)
        words |= c["gd_enums"]
        try:
            for r in common.read_byml(fs, "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"):
                words.update(str(v) for v in r.values() if isinstance(v, str) and "/" not in v)
        except FileNotFoundError:
            pass
        c["names"] = {murmur3_32(w.encode()): w for w in words}
    return c["names"]


def _dec(fs, v):
    if isinstance(v, bool) or not isinstance(v, int):
        return v
    return _names(fs).get(int(v), int(v))


def _decode(fs, v):
    """Decodes every hash-valued int in a value where we know the name, keys included."""
    if isinstance(v, dict):
        return {(_names(fs).get(int(k), k) if isinstance(k, str) and k.isdigit() else k): _decode(fs, x)
                for k, x in v.items()}
    if isinstance(v, list):
        return [_decode(fs, x) for x in v]
    if isinstance(v, int) and not isinstance(v, bool) and v > 65535:
        return _names(fs).get(v, v)
    return v


def _ai_global(fs):
    c = _ctx(fs)
    if "aig" not in c:
        try:
            c["aig"] = common.pack(fs, AI_GLOBAL)
        except FileNotFoundError:
            c["aig"] = {}
    return c["aig"]


def _death_table(fs, ref):
    """Merged death procedures {reason: cell} of a DeathProcedures ref (romfs System/CombinationDataTableData)."""
    c = _ctx(fs).setdefault("death", {})
    if ref in c:
        return c[ref]
    rel = _inner(ref)
    cells, seen = {}, set()
    chain = []
    while rel and rel not in seen:
        seen.add(rel)
        try:
            d = common.jsonable(common.read_byml(fs, rel))
        except FileNotFoundError:
            break
        chain.append(d)
        rel = _inner(d["$parent"]) if d.get("$parent") else None
    for d in reversed(chain):
        for k, cell in (d.get("CellList") or {}).items():
            cells.setdefault(k.split("___")[0], {}).update({kk: vv for kk, vv in cell.items() if kk != "$type"})
    c[ref] = cells if chain else None
    return c[ref]


# Helpers

def _inner(ref):
    """Inner pack path of a component reference ("?Component/..bgyml" or "Work/...gyml")."""
    if not isinstance(ref, str) or not ref:
        return None
    ref = ref.lstrip("?")
    if ref.startswith("Work/"):
        ref = ref[5:]
    if ref.endswith(".gyml"):
        ref = ref[:-5] + ".bgyml"
    return ref


def _ai_path(ref):
    """'Work/AI/Root/Event/X.event.root.ain' -> 'AI/X.event.root.ainb'."""
    base = os.path.basename(ref)
    return "AI/" + (base + "b" if base.endswith(".ain") else base)


def _short(path):
    return os.path.basename(path).split(".")[0] if path else path


class _Pack:
    def __init__(self, fs, files):
        self.fs, self.files, self._y = fs, files, {}

    def y(self, inner):
        if inner not in self._y:
            b = self.files.get(inner)
            self._y[inner] = common.jsonable(byml_load(b, allow_big=True)[0]) if b and b[:2] in (b"YB", b"BY") else None
        return self._y[inner]

    def reachable(self, start):
        """The pack files this actor uses, following every reference out from its ActorParam. A pack also holds
        files for the other actors its parents name, and this actor doesn't read those. Each file is read merged
        over its $parent chain, so we don't follow a reference that a child overrides."""
        seen, todo = set(), [start]
        while todo:
            p = todo.pop()
            if p in seen or p not in self.files:
                continue
            seen.add(p)
            if not p.endswith(".bgyml"):
                continue
            d, used, _ = self.merged(p)
            seen.update(used)
            stack = [d]
            while stack:
                v = stack.pop()
                if isinstance(v, dict):
                    stack += list(v.values())
                elif isinstance(v, list):
                    stack += v
                elif isinstance(v, str) and (v.startswith("?") or v.startswith("Work/")):
                    q = _inner(v)
                    if q in self.files and q not in seen:
                        todo.append(q)
        return seen

    def merged(self, inner):
        """A component file merged over its $parent chain, parent first.
        Returns (dict, [files], missing parent or None)."""
        chain, used, missing, seen = [], [], None, set()
        p = inner
        while p and p not in seen:
            seen.add(p)
            d = self.y(p)
            if d is None:
                missing = p
                break
            chain.append(d)
            used.append(p)
            p = _inner(d.get("$parent"))
        out = {}
        for d in reversed(chain):
            for k, v in d.items():
                if k == "$parent":
                    continue
                if isinstance(v, dict) and isinstance(out.get(k), dict) and k == "Components":
                    out[k] = {**out[k], **v}
                else:
                    out[k] = v
        return out, used, missing


# RSDB / pouch tables

def index_rsdb(fs, rel):
    table = os.path.basename(rel).split(".")[0]
    root = common.jsonable(common.read_byml(fs, rel))
    rec = {"kind": "rsdb", "table": table}
    if table == "Tag":
        pl, tl = root["PathList"], root["TagList"]
        bt = bytes.fromhex(root["BitTable"]) if isinstance(root["BitTable"], str) else bytes(root["BitTable"])
        n = len(tl)
        tags = {}
        for i in range(len(pl) // 3):
            have = [tl[j] for j in range(n) if (bt[(i * n + j) >> 3] >> ((i * n + j) & 7)) & 1]
            if have:
                tags[pl[3 * i + 1]] = have
        rec.update(tags=tags, tag_list=tl)
        return rec
    if table == "TagDef":
        rec["rows"] = [[r.get("FullTagId"), r.get("ParentFullTagId"), r.get("DefinitionType")] for r in root]
        return rec
    drop = {"ActorInfo": {"InstanceHeapSize", "PreActorRenderInfoHeapSize", "ModelAabbMax", "ModelAabbMin", "FmdbName",
                          "ModelProjectName", "AnimationResources", "ModelVariationFmabName", "ModelVariationFmabFrame",
                          "ASInfoAutoPlayMaterials", "ASInfoAutoPlaySkeletals", "ASInfoAutoPlayBoneVisibilities",
                          "DebugModelScale", "UsePreActorRenderer", "IsSinglePreActorRender", "ClassName",
                          "DeleteRadiusOffset", "UnloadRadiusOffset", "IsNotTurnToActor", "SLinkUserName",
                          "ELinkUserName", "CoreUsedLevel", "ApplyScaleType", "CalcRadiusDistanceType",
                          "DisplayRadiusDistanceType", "LoadRadiusDistanceType", "IsCalcNodePushBack"},
            "GameActorInfo": {"ModelVariationAnims", "IsBakeCaster", "HasLightRigBone", "UseConcenteredRenderer",
                              "IsWaterFogTypeMisc0", "IsInvalidShapeLod"}}.get(table, set())
    rows = {}
    for r in root:
        row = {k: v for k, v in r.items() if k != "__RowId" and k not in drop}
        if row or table == "PouchActorInfo":
            rows[r["__RowId"]] = row
    rec["rows"] = rows
    if table != "PouchActorInfo":
        rec["dropped_columns"] = sorted(drop)
    return rec


def index_pouch_table(fs, rel):
    root = common.jsonable(common.read_byml(fs, rel))
    rec = {"kind": "pouch_table", "table": os.path.basename(rel).split(".")[0]}
    if "BottleArray" in root:
        rec["bottles"] = [[b.get("ActorNameShort"), _dec(fs, b.get("Content"))] for b in root["BottleArray"]]
        return rec
    slots = []
    for arr, btns in root.items():
        if not isinstance(btns, list):
            continue
        for b in btns:
            if not isinstance(b, dict) or "Actor" not in b:
                continue
            s = {"array": arr, "button": b.get("BtnName"),
                 "actors": [a.get("ActorShort") for a in b["Actor"]],
                 "pouch_actors": [a.get("PouchActorShort") for a in b["Actor"] if a.get("PouchActorShort")]}
            for a in b["Actor"]:
                ages = [x for x, k in (("adult", "IsUsableAdult"), ("child", "IsUsableChild")) if a.get(k)]
                s.setdefault("usable", {})[a.get("ActorShort")] = ages
            for k in ("SpecialDeal", "IsChangeMenuIfInputLeftRight", "IsChangeActorEquipState", "AssignableItemEnum"):
                if k in b:
                    s[k] = _dec(fs, b[k])
            if not s["pouch_actors"]:
                del s["pouch_actors"]
            slots.append(s)
    rec["slots"] = slots
    return rec


# AI

def _ai_find(fs, pk, path):
    if path in pk.files:
        return pk.files[path], "pack"
    g = _ai_global(fs)
    if path in g:
        return g[path], "global"
    try:
        return common.read_any(fs, path), "romfs"
    except FileNotFoundError:
        return None, None


def _ai_info(fs, path, data):
    """{"modules", "commands", "writes", "bb_gd"} of one AINB (cached per process)."""
    c = _ctx(fs).setdefault("ai", {})
    key = (path, len(data))
    if key in c:
        return c[key]
    try:
        a = AINB.Ainb(data)
    except Exception as e:  # noqa: BLE001 - recorded, the build goes on
        c[key] = {"error": f"{type(e).__name__}: {e}"}
        return c[key]
    gd = _gamedata(fs)
    info = {"modules": sorted({"AI/" + m["path"] for m in a.modules if m.get("path")}),
            "commands": [x["name"] for x in a.commands]}
    writes = []
    for i, n in enumerate(a.nodes):
        if GD_WRITE.search(n["name"]):
            w = _ai_write(fs, a, n)
            if w:
                w["node"] = i
                writes.append(w)
    bbgd = []
    for t, es in a.bb.items():
        for e in es:
            d = e.get("default")
            if t == "string" and isinstance(d, str) and d and murmur3_32(d.encode()) in gd:
                bbgd.append({"key": e["name"], "flag": d})
            elif "GmdHash" in e["name"] or "GameData" in e["name"]:
                bbgd.append({"key": e["name"], **({"default": d} if d not in (None, "", 0, False) else {})})
    info["writes"], info["bb_gd"] = writes, bbgd
    c[key] = info
    return info


def _src(a, inp, t):
    """Where an input's value comes from, as ("imm", value) / ("bb", key, default) / ("node", node name, node) ..."""
    if inp["node"] >= 0:
        return ("node", a.nodes[inp["node"]]["name"], inp["node"])
    if inp["node"] <= -100:
        return ("multi",)
    if inp["flags"] & AINB.BB_INDEXED:
        k = inp["flags"] & 0xFFFF
        es = a.bb.get(t) or []
        if k < len(es):
            return ("bb", es[k]["name"], es[k].get("default"))
        return ("bb", f"#{k}", None)
    return ("imm", inp.get("value"))


def _node_string(a, idx, names=("GameDataFullName", "GameDataName", "Name")):
    n = a.nodes[idx]
    for e in n["inputs"].get("string", []) + n["properties"].get("string", []):
        if e["name"] in names:
            s = _src(a, e, "string") if "node" in e else ("imm", e.get("value"))
            return s
    return None


def _ai_write(fs, a, n):
    name = n["name"]
    w = {"how": name}
    ins = {e["name"]: (t, e) for t in AINB.PTYPES for e in n["inputs"].get(t, [])}
    props = {e["name"]: e.get("value") for t in AINB.PTYPES for e in n["properties"].get(t, [])}
    if name == "OneShotActorChangeIsRespawn":
        t, e = ins.get("Bool", (None, None))
        w["key"] = "placement Bool64bitKey"
        if e is not None:
            s = _src(a, e, t)
            w["value"] = s[1] if s[0] == "imm" else f"<{s[0]}:{s[1]}>"
        return w
    if "GmdHash" in name:
        w["key"] = props.get("Key") or "?"
        return w
    for nm in ("GameDataFullName", "GameDataName", "GameDataNameHash", "Name"):
        if nm in ins:
            t, e = ins[nm]
            s = _src(a, e, t)
            if s[0] == "imm":
                w["flag"] = s[1]
            elif s[0] == "bb":
                w["key"] = s[1]
                if s[2]:
                    w["default"] = s[2]
            elif s[0] == "node":
                if s[1] in MEMBER_SOURCES:
                    w["member"] = MEMBER_SOURCES[s[1]]
                else:
                    w["from"] = s[1]
                    sub = [(_src(a, e2, "string"), e2["name"]) for e2 in a.nodes[s[2]]["inputs"].get("string", [])]
                    for (ss, nm2) in sub:  # one step back, a path/name query fed by the blackboard or a constant
                        if ss[0] == "bb":
                            w["key"] = ss[1]
                            if ss[2]:
                                w["default"] = ss[2]
                            break
                        if ss[0] == "imm" and ss[1]:
                            w["flag_via"] = ss[1]
                            break
            break
    if "ParentStruct" in ins:
        t, e = ins["ParentStruct"]
        s = _src(a, e, t)
        if s[0] == "node":
            st = _node_string(a, s[2])
            if st and st[0] == "imm":
                w["struct"] = st[1]
            elif st and st[0] == "bb":
                w["struct_key"] = st[1]
    for nm in ("Value", "Bool", "value", "U64"):
        if nm in ins:
            t, e = ins[nm]
            s = _src(a, e, t)
            if s[0] == "imm" and t != "ptr":
                w["value"] = s[1]
            break
    if "struct" in w and w.get("member"):
        w["flag"] = f"{w['struct']}.{w['member']}"
    if not any(k in w for k in ("flag", "key", "from", "struct", "member")) and n["inputs"]:
        w["key"] = "?"
    return w


def _collect_ai(fs, pk, roots):
    """BFS over the AI files from the roots through their modules. Returns ([paths], [missing], {path: info})."""
    seen, order, missing, infos = set(), [], [], {}
    queue = [r for r in roots if r]
    while queue and len(order) < 120:
        p = queue.pop(0)
        if p in seen:
            continue
        seen.add(p)
        data, _where = _ai_find(fs, pk, p)
        if data is None:
            missing.append(p)
            continue
        order.append(p)
        info = _ai_info(fs, p, data)
        infos[p] = info
        queue += [m for m in info.get("modules", []) if m not in seen]
    return order, missing, infos


# Pack

def index_pack(fs, rel):
    actor = os.path.basename(rel)[:-len(".pack.zs")]
    pk = _Pack(fs, common.pack(fs, rel))
    rec = {"actor": actor}
    ap_path = f"Actor/{actor}.engine__actor__ActorParam.bgyml"
    if ap_path not in pk.files:
        cands = [k for k in pk.files if k.startswith("Actor/")]
        ap_path = cands[0] if len(cands) == 1 else None
    if not ap_path:
        rec["error"] = "no ActorParam"
        return rec
    ap, used, missing = pk.merged(ap_path)
    reach = pk.reachable(ap_path)
    rec["parents"] = [_short(p) for p in used[1:]]
    if missing:
        rec["parent_missing"] = missing
    comps = ap.get("Components") or {}
    refs, absent = {}, {}
    for k, v in sorted(comps.items()):
        if not isinstance(v, str):
            continue
        if not v.startswith("?"):
            if k == "ActorLogicNodeRef":
                rec["logic_node"] = _short(v)
            continue
        inner = _inner(v)
        if inner in pk.files:
            refs[k] = inner
            if k not in COSMETIC:
                rec.setdefault("components", {})[k] = inner
        elif k not in COSMETIC:
            absent[k] = _short(inner)
    if absent:
        rec["absent"] = absent
    if comps.get("ActorGameDataSetting"):
        rec["game_data_setting"] = _short(_inner(comps["ActorGameDataSetting"]))
    gpt = pk.merged(refs["GameParameterTableRef"])[0].get("Components", {}) if "GameParameterTableRef" in refs else {}
    gp = {k: _inner(v) for k, v in gpt.items() if isinstance(v, str)}

    # AI
    roots = []
    if "AIInfoRef" in refs:
        info = pk.merged(refs["AIInfoRef"])[0]
        for k in ("RootAIRef", "PostCalcAIRef", "PostSensorAIRef"):
            if isinstance(info.get(k), str) and info[k]:
                roots.append(_ai_path(info[k]))
    ev_ai = None
    if "EventPerformerRef" in refs:
        ep = pk.merged(refs["EventPerformerRef"])[0]
        if ep.get("EventUniqueAin"):
            ev_ai = _ai_path(ep["EventUniqueAin"])
    elif comps.get("EventPerformerRef"):
        rec.setdefault("notes", []).append("EventPerformerRef file absent: engine default event AI")
    ai_paths, ai_missing, ai_infos = _collect_ai(fs, pk, roots + ([ev_ai] if ev_ai else []))
    if ai_paths:
        rec["ai"] = ai_paths
    if ai_missing:
        rec["ai_missing"] = ai_missing

    rec["holdup"] = _holdup(fs, pk, rec, refs, comps, ev_ai, ai_infos)
    pouch = _pouch(fs, pk, refs, gp)
    if pouch:
        rec["pouch"] = pouch
        if "getdemo_offset" in pouch:
            rec["holdup"]["getdemo_offset"] = pouch.pop("getdemo_offset")
    lift = _lift(fs, pk, refs)
    if lift:
        rec["lift"] = lift
    for k, inner in refs.items():
        if "LifterParam" in inner:
            d, used_l, _ = pk.merged(inner)
            if "LiftGrade" in d:
                rec.setdefault("lifter", []).append({"grade": _dec(fs, d["LiftGrade"]), "file": used_l[0]})
    for inner in sorted(reach):  # the player's PlayerLifterParam is named by its GameParameterTable
        if inner.startswith("Game/PlayerLifterParam/") and not any(x["file"] == inner for x in rec.get("lifter", [])):
            d, _, _ = pk.merged(inner)
            if "LiftGrade" in d:
                rec.setdefault("lifter", []).append({"grade": _dec(fs, d["LiftGrade"]), "file": inner})
    dmg = _damage(fs, pk, refs, gp)
    if dmg:
        rec["damage"] = dmg
    atk = _attacks(fs, pk, gp)
    if atk:
        rec["attacks"] = atk
    push = {}
    for k, field in (("MovableBoxParam", ("MovableBoxType", "PushPullMovability", "PushPerBlock")),
                     ("GrabMoveActorParam", ("GrabMoveActorType",))):
        if gp.get(k) in pk.files:
            d = pk.merged(gp[k])[0]
            push.update({f: _dec(fs, d[f]) for f in field if f in d})
    if push:
        rec["push"] = push

    saves, refs_gd = _saves(fs, pk, rec, ai_infos, dmg, reach)
    if saves:
        rec["saves"] = saves
    if refs_gd:
        rec["gamedata_refs"] = refs_gd
    return rec


def _holdup(fs, pk, rec, refs, comps, ev_ai, ai_infos):
    """What Link's item-get pose needs from the item actor. Item_Hookshot has all of it and the ocarinas have none."""
    h = {"event_object_base": "Item_EventObject_Base" in rec.get("parents", []),
         "as_getdemo": refs.get("ASInfoRef", "").startswith("Component/ASInfo/Item_GetDemo."),
         "animation_param": "AnimationRef" in refs,
         "getdemo_event": bool(ev_ai and any(c in (ai_infos.get(ev_ai) or {}).get("commands", [])
                                             for c in GETDEMO_COMMANDS))}
    h["complete"] = h["as_getdemo"] and h["animation_param"] and h["getdemo_event"]
    if "PouchContentRef" in comps or rec["actor"].startswith(("Item_", "Weapon_", "Armor_")):
        proof = {}
        if h["event_object_base"]:
            proof["event_object_base"] = "Actor/Item_EventObject_Base.engine__actor__ActorParam.bgyml ($parent)"
        if "ASInfoRef" in refs:
            proof["as_info"] = refs["ASInfoRef"]
        elif comps.get("ASInfoRef"):
            proof["as_info"] = "absent: " + _inner(comps["ASInfoRef"])
        if "AnimationRef" in refs:
            proof["animation_param"] = refs["AnimationRef"]
        if ev_ai:
            proof["event_ai"] = ev_ai + (" (has " + ", ".join(c for c in GETDEMO_COMMANDS
                                                              if c in (ai_infos.get(ev_ai) or {}).get("commands", []))
                                         + ")" if h["getdemo_event"] else " (no item-get commands)")
        h["proof"] = proof
        if comps.get("ASRef"):
            h["as"] = _inner(comps["ASRef"])
    return h


def _pouch(fs, pk, refs, gp):
    out = {}
    if "PouchContentRef" in refs:
        d, used, missing = pk.merged(refs["PouchContentRef"])
        for k, v in d.items():
            if k == "GetDemoOffsetPos":
                out["getdemo_offset"] = [round(float(v.get(a, 0)), 3) for a in "XYZ"]
            elif not isinstance(v, (dict, list)):
                out[k] = _dec(fs, v)
            else:
                out[k] = _decode(fs, v)
        out["file"] = used[0]
        if missing:
            out["defaults_from"] = _short(missing) + " (absent: engine defaults)"
    if gp.get("AssignableItemParam") in pk.files:
        d = pk.merged(gp["AssignableItemParam"])[0]
        out["assignable"] = {k: _dec(fs, v) for k, v in d.items()}
    if gp.get("OcarinaParam") in pk.files:
        out["ocarina"] = _decode(fs, pk.merged(gp["OcarinaParam"])[0])
    if gp.get("ExpansionAbilityActor") in pk.files:
        out["expansion"] = _decode(fs, pk.merged(gp["ExpansionAbilityActor"])[0])
    return out


def _lift(fs, pk, refs):
    if "LiftableRef" not in refs:
        return None
    d, used, _ = pk.merged(refs["LiftableRef"])
    g = _dec(fs, d.get("LiftGrade")) if "LiftGrade" in d else "None"
    out = {"grade": g, "need": LIFT_NEED.get(g, "?"), "file": used[0]}
    if "LiftGrade" not in d:
        out["grade_default"] = True
    for k in ("LiftableType", "PutThrowPossibility"):
        if k in d:
            out[k[0].lower() + k[1:]] = _dec(fs, d[k])
    if d.get("SpecialDeal"):
        out["special_deal"] = [_dec(fs, x) for x in d["SpecialDeal"]]
    if d.get("InactiveLift") is not None:
        out["inactive_lift"] = d["InactiveLift"]
    return out


def _attacks(fs, pk, gp):
    out = []
    for k, inner in gp.items():
        if "AttackParam" in k and inner in pk.files:
            for a in pk.merged(inner)[0].get("AttackParams") or []:
                row = [_dec(fs, a.get("DamageType")), [_dec(fs, x) for x in a.get("DamageElements") or []],
                       [_dec(fs, x) for x in a.get("DamageAttributres") or []]]
                if row not in out:
                    out.append(row)
    return out


# Damage

def _match(el, atype, aelem, aattr, aff="Player"):
    types = [x for x in el.get("DamageTypes") or []]
    elems = [x for x in el.get("DamageElements") or []]
    attrs = [x for x in el.get("DamageAttributes") or []]
    affs = [x for x in el.get("Affiliations") or []]
    last = [x for x in el.get("LastUserAffiliations") or []]
    if types and atype not in types:
        return False
    if elems and aelem not in elems:
        return False
    if attrs and aattr not in attrs:
        return False
    if affs and aff not in affs:
        return False
    if last and aff not in last:
        return False
    return True


def _sensor_match(entry, atype, aelem, aattr):
    types = entry.get("ExternalDamageTypes") or []
    elems = entry.get("ExternalDamageElements") or []
    attrs = entry.get("ExternalDamageAttributes") or []
    if not (types or elems or attrs):
        return False  # an AttackIdentifier-only entry (enemy attacks)
    return ((not types or atype in types) and (not elems or aelem in elems) and (not attrs or aattr in attrs))


def _damage(fs, pk, refs, gp):
    out, files = {}, {}
    life = rates = None
    exc, hammer_sw, impulse = [], None, False
    if "LifeRef" in refs:
        lp, used, _ = pk.merged(refs["LifeRef"])
        files["life"] = used[0]
        inv = lp.get("InitInvincibilityType")
        if inv is not None and _dec(fs, inv) != "None":
            out["invincible"] = _dec(fs, inv)
            if lp.get("IsDamagedWhileInvincibile"):
                out["invincible"] = f"{out['invincible']} (IsDamagedWhileInvincibile)"
        lpar = _inner(lp.get("LifeParameters"))
        if lpar in pk.files:
            life = pk.merged(lpar)[0].get("MaxLife")
            files["life_parameters"] = lpar
        dpar = _inner(lp.get("DamageParameters"))
        if dpar in pk.files:
            dp = pk.merged(dpar)[0]
            files["damage_parameters"] = dpar
            ext = dp.get("ExternalDamageParameters") or {}
            rates = {_dec(fs, int(k)) if str(k).isdigit() else k: float(v)
                     for k, v in (ext.get("DamageRates") or {}).items()}
            for e in ext.get("ExternalDamageExceptionDefines") or []:
                els = [{k: [_dec(fs, x) for x in v] for k, v in el.items() if isinstance(v, list) and v}
                       for el in e.get("Elements") or []]
                row = {"rule": EXCEPTION_RULES.get(e.get("Rule"), e.get("Rule")), "elements": els}
                if e.get("Rule_DamageRate") not in (None, 0.5) or row["rule"] == "MultiplyRate":
                    row["rate"] = e.get("Rule_DamageRate")
                if e.get("Rule_AddDamageAmount"):
                    row["add"] = e["Rule_AddDamageAmount"]
                if e.get("FeatureExplaination"):
                    row["note"] = e["FeatureExplaination"]
                exc.append(row)
            hs = ext.get("HammerShockwaveDamageParameters") or {}
            if hs.get("IsEnable"):
                hammer_sw = {"damage": hs.get("Damage"), "insta_kill": bool(hs.get("IsInstaKill"))}
            impulse = bool((ext.get("ImpulseDamageParameters") or {}).get("IsImpulseDamageEnabled"))
            br = _dec(fs, ext.get("Brittleness"))
            if br not in (None, "Normal"):
                out["brittleness"] = br
    if life is not None:
        out["life"] = life
    if rates is not None:
        out["rates"] = {str(k): v for k, v in rates.items() if v not in (0.0, 1.0)}
        out["immune"] = sorted(str(k) for k, v in rates.items() if v == 0.0)
        out["rate_1"] = sorted(str(k) for k, v in rates.items() if v == 1.0)
    if exc:
        out["exceptions"] = exc
    if impulse:
        out["impulse_damage"] = True

    sensor_black, sensor_white = [], []
    if "SensorHitRef" in refs:
        sh = pk.merged(refs["SensorHitRef"])[0]
        files["sensor"] = refs["SensorHitRef"]
        for lst, dst in (("DamageBlackList", sensor_black), ("DamageWhiteList", sensor_white)):
            for e in sh.get(lst) or []:
                dst.append({k: [_dec(fs, x) for x in v] for k, v in e.items() if isinstance(v, list) and v})
        if sensor_black or sensor_white:
            out["sensor"] = {k: v for k, v in (("black", sensor_black), ("white", sensor_white)) if v}

    death = None
    if "DeathRef" in refs:
        dpm = pk.merged(refs["DeathRef"])[0]
        files["death"] = refs["DeathRef"]
        dref = dpm.get("DeathProcedures") or "Work/System/CombinationDataTableData/Default_game__death__DeathReason" \
                                               "Procedures.pp__CombinationDataTableData.gyml"
        death = _death_table(fs, f"{DEATH_DIR}/" + os.path.basename(_inner(dref)))
        files["death_procedures"] = _short(_inner(dref))
    else:
        death = _death_table(fs, f"{DEATH_DIR}/Default_game__death__DeathReasonProcedures.pp__CombinationDataTableData"
                                 f".bgyml")
        files["death_procedures"] = "Default (DeathRef absent)"
    accepted = sorted(k for k, c in (death or {}).items() if not c.get("IsIgnoreThisDeathReason"))
    respawn = sorted(k for k, c in (death or {}).items()
                     if not c.get("IsIgnoreThisDeathReason") and c.get("IsSetRespawnFlagToFalse"))

    chem = {}
    if "ChemicalRef" in refs:
        objs = pk.merged(refs["ChemicalRef"])[0].get("Object") or []
        files["chemical"] = refs["ChemicalRef"]
        for o in objs:
            mat = _inner(o.get("ChemicalMaterial"))
            md = pk.merged(mat)[0] if mat in pk.files else {}
            if o.get("RequestDeathIfExploded"):
                chem["explode"] = True
            if o.get("RequestDeathIfBurned") and md.get("IsBurn"):
                chem["burn"] = True
            if mat:
                chem.setdefault("material", _short(mat) + ("" if mat in pk.files else " (absent)"))

    hammer = {}
    if gp.get("ReactionForHammerAttack") in pk.files:
        rh = pk.merged(gp["ReactionForHammerAttack"])[0]
        hammer.update({k[8:].lower() if k.startswith("IsHammer") else k: v for k, v in rh.items()})
    if hammer_sw:
        hammer["shockwave"] = hammer_sw
    if hammer:
        out["hammer"] = hammer
    if gp.get("SpiderwebParam") in pk.files:
        fb = pk.merged(gp["SpiderwebParam"])[0].get("FallHeight_Break")
        if fb:
            out["fall_break"] = round(float(fb), 2)
    if gp.get("SignboardParam") in pk.files:
        if pk.merged(gp["SignboardParam"])[0].get("IsCuttableSignBoard"):
            out["cuttable_sign"] = True

    # who breaks it
    how = {}
    life_kills = rates is not None and "LifeDepleted" in accepted
    inv = out.get("invincible")
    inv_note = None
    # life never drops. A plain invincible actor only reacts, and one damaged while invincible leaves it to its AI
    if inv:
        inv_note = " (hit registers while invincible: its AI decides)" if "IsDamagedWhileInvincibile" in str(inv) else " (invincible: no life loss)"
    if life_kills:
        for name, atype, aelem, aattr in ATTACKS:
            rate, add, why = rates.get(atype, 1.0), 0, []
            for e in exc:
                hit = any(_match(el, atype, aelem, aattr) for el in e["elements"]) if e["elements"] else True
                r = e["rule"]
                if r == "Ignore" and hit:
                    rate, why = 0.0, why + ["ignored"]
                elif r == "OnlyThese" and not hit:
                    rate, why = 0.0, why + ["not in OnlyThese"]
                elif r == "AddDamage" and hit:
                    add += e.get("add") or 0
                elif r == "MultiplyRate" and hit:
                    rate *= float(e.get("rate") or 1.0)
            if any(_sensor_match(s, atype, aelem, aattr) for s in sensor_black):
                continue
            if sensor_white and not any(_sensor_match(s, atype, aelem, aattr) for s in sensor_white):
                continue
            if rate > 0 or add > 0:
                how[name] = f"{atype}" + (f"+{aelem}" if aelem else "") + (f"+{aattr}" if aattr else "") + \
                    (f" x{rate:g}" if rate != 1.0 else "") + (f" +{add}" if add else "") + \
                    (" (unlisted type)" if atype not in rates else "") + (" (unsure)" if name in UNSURE else "") + (inv_note or "")
        if hammer_sw and "LifeDepleted" in accepted:
            how["hammer_shockwave"] = "HammerShockwaveDamageParameters" + (" insta-kill" if hammer_sw["insta_kill"]
                                                                           else "")
    if chem.get("explode") and "Exploded" in accepted:
        how["bomb"] = (how["bomb"] + "; " if "bomb" in how else "") + "chemical Exploded death"
    if chem.get("burn") and "Burned" in accepted:
        for f in FIRE_SOURCES:
            how[f] = (how[f] + "; " if f in how else "") + "chemical Burned death"
    if out.get("fall_break"):
        how["fall_onto"] = f"SpiderwebParam FallHeight_Break {out['fall_break']}"
    if hammer.get("reflect") and "hammer" in how:
        how["hammer"] += " (ReactionForHammerAttack IsHammerReflect)"
    if gp.get("RedIce") in pk.files:
        how["blue_fire"] = "GameParameter RedIce (melted by its AI when Blue Fire is poured on it: attention " \
                           "BlueFireTarget)"
    if not (how or life is not None or rates is not None):
        return None
    out["death"] = {"accepted": accepted}
    if respawn:
        out["death"]["sets_respawn_flag"] = respawn
    if chem:
        out["chemical"] = chem
    out["breakers"] = sorted(k for k in how if k not in UNSURE and "(invincible: no life loss)" not in how[k])
    out["how"] = how
    out["files"] = files
    return out


# Saves

def _saves(fs, pk, rec, ai_infos, dmg, reach):
    gd = _gamedata(fs)
    saves, refs_gd = [], []

    def saved(name):
        r = gd.get(murmur3_32(name.encode())) if isinstance(name, str) else None
        return None if r is None else {"type": r[0], "save": r[1], "reset": r[2]}

    for p, info in ai_infos.items():
        for w in info.get("writes", []):
            s = dict(w, ai=p)
            if isinstance(s.get("flag"), str) and s.get("member") == "<actor>":
                s["flag"] = s["flag"].replace("<actor>", rec["actor"])  # QueryGenericGetActorName means this actor
            if isinstance(s.get("flag"), str) and "<" not in s["flag"]:
                meta = saved(s["flag"])
                if meta:
                    s["gamedata"] = meta
            elif s.get("struct"):
                meta = saved(s["struct"])
                if meta:
                    s["struct_row"] = meta
            saves.append(s)
        for b in info.get("bb_gd", []):
            refs_gd.append(dict(b, field="AI blackboard", file=p))
    setting = rec.get("game_data_setting")
    if setting and setting != "AlwaysRespawn":
        s = {"key": "placement Bool64bitKey", "how": f"ActorGameDataSetting {setting}: the placement's own flag"}
        if dmg and dmg.get("death", {}).get("sets_respawn_flag"):
            s["deaths"] = dmg["death"]["sets_respawn_flag"]
        saves.append(s)
    # blackboard tables, with GameData names as defaults and U64 *GmdHash keys (a Bool64bitKey the actor writes)
    for inner in sorted(reach):
        b = pk.files[inner]
        if "BlackboardParamTable" not in inner or b[:2] != b"YB":
            continue
        d = pk.y(inner) or {}
        for arr, params in d.items():
            if not isinstance(params, list):
                continue
            for prm in params:
                if not isinstance(prm, dict) or "BBKey" not in prm:
                    continue
                key, v = prm["BBKey"], prm.get("InitValConverted", prm.get("InitVal"))
                if key.endswith("GmdHash"):
                    saves.append({"key": key, "how": f"blackboard {arr[len('BlackboardParam'):-5]} GmdHash: a "
                                                     "Bool64bitKey hash handed to this actor, written when collected",
                                  "file": inner})
                elif isinstance(v, str) and v and murmur3_32(v.encode()) in gd:
                    refs_gd.append({"key": key, "flag": v, "field": "blackboard default", "file": inner,
                                    **({"instance_param": True} if prm.get("IsInstanceParam") else {})})
                elif arr == "BlackboardParamStringArray" and re.search(r"GameData|Gmd|Flag", key):
                    refs_gd.append({"key": key, "field": "blackboard string (a GameData name"
                                    + (", set per placement)" if prm.get("IsInstanceParam") else ")"), "file": inner,
                                    **({"default": v} if v else {})})
    # component files naming GameData (Work/GameData/Entity/X.gmdentity.json?Name)
    for inner in sorted(reach):
        b = pk.files[inner]
        if b"gmdentity.json?" not in b or not inner.endswith(".bgyml"):
            continue
        d = pk.y(inner)
        for field, name in _gmd_fields(d):
            r = {"flag": name, "field": field, "file": inner}
            refs_gd.append(r)
            if "Defeated" in field:
                saves.append({"flag": name, "how": f"{field} (defeat counter, counted when it dies)", "file": inner,
                              **({"gamedata": saved(name)} if saved(name) else {})})
    # dedupe
    out, seen = [], set()
    for s in saves:
        k = repr(sorted((k, v) for k, v in s.items() if k not in ("node",)))
        if k not in seen:
            seen.add(k)
            out.append(s)
    rg, seen = [], set()
    for r in refs_gd:
        k = (r.get("flag"), r.get("key"), r.get("field"), r.get("file"))
        if k not in seen:
            seen.add(k)
            rg.append(r)
    return out, rg


def _gmd_fields(d, path=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _gmd_fields(v, k if not path else f"{path}.{k}")
    elif isinstance(d, list):
        for v in d:
            yield from _gmd_fields(v, path)
    elif isinstance(d, str) and ".gmdentity.json?" in d:
        yield path, d.split("?", 1)[1]


# Finish

ITEM_PREFIXES = ("Item_", "Weapon_", "Armor_", "Obj_")


def finish(fs, by_file):
    packs = {r["actor"]: r for rel, r in by_file.items() if rel.startswith("Pack/Actor/") and r and "actor" in r}
    rs = {r["table"]: r for r in by_file.values() if r and r.get("kind") == "rsdb"}
    pouch_rows = (rs.get("PouchActorInfo") or {}).get("rows") or {}
    tags = (rs.get("Tag") or {}).get("tags") or {}
    summary = {}

    # pouch is the PouchActorInfo row plus what the pack's PouchContentParam says
    pouch = {}
    for a, row in sorted(pouch_rows.items()):
        e = dict(row)
        pc = (packs.get(a) or {}).get("pouch")
        if pc:
            e["content_param"] = {k: v for k, v in pc.items() if k != "file"}
        if a not in packs:
            e["no_pack"] = True
        pouch[a] = e
    summary["pouch"] = pouch

    # lift grades
    grades = {}
    for a, row in pouch_rows.items():
        g = row.get("LiftableGrade")
        if g and g != "None":
            grades.setdefault(g, []).append(a)
    for a, r in packs.items():
        ex = (r.get("pouch") or {}).get("expansion") or {}
        if ex.get("LiftableGrade") not in (None, "None"):
            grades.setdefault(ex["LiftableGrade"], []).append(f"{a} (ExpansionAbilityActor)")
    summary["lift_grades"] = {
        "meaning": {g: LIFT_NEED[g] for g in ("None", "Low", "Middle", "High")},
        "granted_by": {g: sorted(v) for g, v in sorted(grades.items())},
        "player": {a: r["lifter"] for a, r in sorted(packs.items()) if r.get("lifter") and a.startswith("Player")},
        "actors": {a: r["lift"]["grade"] + (" (default)" if r["lift"].get("grade_default") else "")
                   for a, r in sorted(packs.items()) if r.get("lift")},
        "note": "LiftableParam.LiftGrade of the object vs the lifter's grade. The gauntlets' grade is their "
                "PouchActorInfo LiftableGrade / GameParameter ExpansionAbilityActor; the player packs' "
                "PlayerLifterParam (adult High, child Low) look like the age's ceiling, not a base grade (open).",
    }

    # breakers
    breakers, notes = {}, {}
    interesting = {"UnbreakHitPotAttack", "InvalidHitPlayerRolling", "HitPlayerRollingContacting",
                   "ObjectEffectiveHookshot", "IronKnuckleDestructible", "Pot", "LiftGrass", "HammerSlipPillar",
                   "NoDamageToFreezard", "TargetBoomerangChase", "TargetAssistHookshotStick"}
    for a, r in sorted(packs.items()):
        d = r.get("damage")
        if not d:
            continue
        if d.get("breakers"):
            breakers[a] = d["breakers"]
        t = sorted(set(tags.get(a, [])) & interesting)
        n = {}
        if t:
            n["tags"] = t
        if d.get("invincible"):
            n["invincible"] = d["invincible"]
        if r.get("ai") and d.get("breakers") is not None and d.get("invincible"):
            n["ai_decides"] = r["ai"][0]
        if n:
            notes[a] = n
    summary["breakers"] = breakers
    summary["breaker_notes"] = notes
    summary["attack_model"] = {"attacks": {n: [t, e, at] for n, t, e, at in ATTACKS},
                               "fire_sources": list(FIRE_SOURCES), "exception_rules": EXCEPTION_RULES,
                               "player_attack_params": {a: packs[a].get("attacks") for a in
                                                        ("Player_Adult", "Player_Child", "Player_Base", "PlayerShockWave",
                                                         "Item_Bomb", "Item_Bombchu", "Item_Boomerang",
                                                         "Item_DekuNut", "Shootable_Hook", "Shootable_DekuSeed")
                                                        if a in packs and packs[a].get("attacks")}}

    # hold-up, the pouch actors a seed can give that lack hold-up parts
    inc = {}
    for a in sorted(pouch_rows):
        if not a.startswith(ITEM_PREFIXES):
            continue
        r = packs.get(a)
        if not r:
            inc[a] = ["no pack"]
            continue
        h = r.get("holdup") or {}
        miss = [k for k in ("event_object_base", "as_getdemo", "animation_param", "getdemo_event") if not h.get(k)]
        if miss:
            inc[a] = miss
    summary["holdup_incomplete"] = inc
    risk = {"like_ocarina": [], "no_animation_param": [], "no_getdemo_event": [], "worn_equipment": []}
    for a, miss in inc.items():
        if miss == ["no pack"]:
            continue
        if a.startswith("Armor_"):
            risk["worn_equipment"].append(a)  # the worn model, the pouch/get actor is its Item_/Obj_ form
        elif "animation_param" in miss and "getdemo_event" in miss:
            risk["like_ocarina"].append(a)
        elif "animation_param" in miss:
            risk["no_animation_param"].append(a)
        elif "getdemo_event" in miss:
            risk["no_getdemo_event"].append(a)
    risk["no_pack"] = [a for a, m in inc.items() if m == ["no pack"]]
    summary["holdup_risk"] = risk
    summary["holdup_parts"] = {
        "event_object_base": "$parent Item_EventObject_Base (gives EventPerformer PouchContent, Physics Dummy)",
        "as_getdemo": "ASInfoRef = Component/ASInfo/Item_GetDemo.engine__component__ASInfo.bgyml",
        "animation_param": "AnimationRef (Component/AnimationParam/<item>)",
        "getdemo_event": "event AI (EventPerformerParam EventUniqueAin) with " + " / ".join(GETDEMO_COMMANDS),
    }

    # shared pouch slots (UI/Pouch/PouchTable)
    shared = {}
    for r in by_file.values():
        if r and r.get("kind") == "pouch_table":
            for s in r.get("slots") or []:
                if len(s["actors"]) > 1:
                    shared[s["button"]] = {k: v for k, v in s.items() if k != "button"}
            if r.get("bottles"):
                summary["bottle_contents"] = r["bottles"]
    summary["shared_pouch_slots"] = shared
    summary["shared_pouch_slots_rule"] = (
        "UI/Pouch/PouchTable lists the menu's buttons; every actor under one button shows in that one slot, so the "
        "pouch holds one of them at a time (upgrade tiers, the 5 bottle buttons that each take any bottle content, "
        "and the trade-item button Pa_ItemIcon_23 holding all 14 child and adult trade items).")
    return summary
