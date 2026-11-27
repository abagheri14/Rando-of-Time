"""The "levels" section of the game-logic index, what the level files place and how (tools/gamedb/build.py builds it).

Files indexed are every Banc/<Area>/*.bcett.byml.zs (the placements of one layer of one level),
Banc/BancBasedResource/*.byml.zs (per-level tables like GmdReset, StartPos, MapParam, ...) and
Banc/GameBancParam/*.bgyml (each level's parameters), and the same under AoC1/Banc. The DLC only holds
BancBasedResource tables, and those add the Master Quest levels.

A level record (SCHEMA.md, plus the fields marked +):
  {"kind"+: "level", "area", "level", "layer", "age", "variant"?, "file_path"+: the level's Work/ path,
   "actors": [{"hash", "gyaml", "name"?, "pos"?, "rot"+?: radians (3 dp, left out when zero), "scale"+?: (3 dp, left out
               when 1,1,1), "presence"?: {"flag", "neg", "lazy", "type"+?: its GameDataList table, absent when the flag
               is no GameData name}, "links"?: [{"dst", "src", "name", "gyaml"}], "dyn"?: the whole Dynamic dict,
               "room"?, "flag_keys"?, "event_keys"?, "b64"+?: a Bool64bitKey row has its hash (a per-placement saved
               flag), "b64_x2"+?: one has hash ^ 2, "rails"+?: [rail hashes it rides], "phive_id"+?: its Phive placement
               ID when that isn't its hash, "phive_group"+?: its Phive placement group GUID (see plg_gd),
               "constraint"+?: {"refers"?: [[type, owner hash]], "owners"?: [[type, refer hash]]} (Phive constraint
               links: a part fixed to another), "force_active"+?: true}],
   "ai_groups": [{"hash", "logic": "Logic/<file>.ainb", "refs": {key: placement hash}, "logic_missing"+?: true,
                  "paths"+?: {key: Path} (where the prefab path differs from the key), "subs"+?: {key: {"logic",
                  "instance", "logic_missing"?}} (a reference that is a nested module instance, not a placement),
                  "instance"+?, "blackboards"+?, "dyn"+?}],
   "far_delete_groups"?, "simultaneous_groups"?, "rails"+?: count,
   "plg_gd"+?: [{"guid", "flag", "type"}] (Phive placement groups moved by a GameData flag: PlgGdTable),
   "placement_groups"+?: [{"guid", "id", "type", "parent"?}] (PhiveHeader)}
  refs keys are the reference's Id. When one group names an Id twice (nested prefabs), those references are keyed by
  their Path instead, and by Path#2, #3... if even that repeats.
Resource records are {"kind": "resource", "name", "data"} and banc params are {"kind": "banc_param", "name",
"parent"?: the banc param it inherits from ($parent), "data"}. Both can have "gd_refs"?: [{"path", "flag"}], the values
that name a GameData flag, with "#<hash>" for a *GameDataHash value. In "data", 64-bit unsigned values (placement
hashes) are decimal strings and floats are rounded to 3 dp.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from romtools import U64, I64, murmur3_32  # noqa: E402

SECTION = "levels"
VERSION = 1
# All levels get re-indexed when the patch changes the tables behind b64, flag_keys or event_keys.
REBUILD_ON = (r"^GameData/GameDataList", r"^RSDB/EventSetting")

GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
RESOURCE_DIRS = ("BancBasedResource", "GameBancParam")
BANC_ROOTS = ("Banc", "AoC1/Banc")


# Files

def files(root):
    out = []
    for base in BANC_ROOTS:
        d = os.path.join(root, base)
        if not os.path.isdir(d):
            continue
        for area in sorted(os.listdir(d)):
            if not os.path.isdir(os.path.join(d, area)):
                continue
            if area == "BancBasedResource":
                out += common.list_files(root, f"{base}/{area}", r"\.byml\.zs$")
            elif area == "GameBancParam":
                out += common.list_files(root, f"{base}/{area}", r"\.bgyml$")
            else:
                out += common.list_files(root, f"{base}/{area}", r"\.bcett\.byml\.zs$")
    return sorted(out)


# Per-process context (GameData names, events, logic)

_CTX = {}


def _dirs(fs, sub):
    """Every folder a file under sub may come from: the overlays, the vanilla copies, the live romfs."""
    return [os.path.join(d, sub) for d in [*fs.overlays, fs.vanilla, fs.root] if d]


def _names_in(fs, sub, pattern=None):
    rx = re.compile(pattern) if pattern else None
    out = set()
    for d in _dirs(fs, sub):
        if os.path.isdir(d):
            out.update(f for f in os.listdir(d) if rx is None or rx.search(f))
    return out


def ctx(fs):
    key = (fs.root, fs.vanilla, tuple(fs.overlays))
    c = _CTX.get(key)
    if c is not None:
        return c
    gd = common.read_byml(fs, GAMEDATA)["Data"]
    gd_type, b64 = {}, set()
    for table, rows in gd.items():
        if not isinstance(rows, list):
            continue
        if table == "Bool64bitKey":
            b64.update(int(r["Hash"]) for r in rows if "Hash" in r)
            continue
        for r in rows:
            if "Hash" in r:
                gd_type.setdefault(int(r["Hash"]), table)
    flows = {common.versioned(f)[0] for f in _names_in(fs, "Event/EventFlow", r"\.bfevfl\.zs$")}
    es_files = sorted(f for f in _names_in(fs, "RSDB", r"^EventSetting\.Product\.\d+\.rstbl\.byml\.zs$"))
    settings = set()
    if es_files:
        rows = common.read_byml(fs, "RSDB/" + max(es_files, key=lambda f: common.versioned(f)[1]))
        settings = {r.get("__RowId") for r in rows if isinstance(r, dict) and r.get("__RowId")}
    c = {"gd_type": gd_type, "b64": b64, "flows": flows, "settings": settings,
         "logic": _names_in(fs, "Logic", r"\.ainb$"), "named": {}}
    _CTX[key] = c
    return c


def gd_name_type(c, s):
    """The GameDataList table of the flag this string names, or None."""
    t = c["named"].get(s, 0)
    if t == 0:
        t = c["named"][s] = c["gd_type"].get(murmur3_32(s))
    return t


def event_kind(c, s):
    """Returns "setting" for an RSDB EventSetting row (what actors request by name), "flow" for only a
    flowchart's base name or Flowchart.Entry, or None."""
    if s in c["settings"]:
        return "setting"
    if s in c["flows"] or ("." in s and s.split(".", 1)[0] in c["flows"]):
        return "flow"
    return None


def is_event(c, s):
    return event_kind(c, s) is not None


# Value helpers

def _h(v):
    return str(int(v))


def val(v, nd=3):
    """A byml value as JSON data. Floats go to nd places and 64-bit unsigned values (placement hashes)
    become decimal strings."""
    if isinstance(v, dict):
        return {str(k): val(x, nd) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [val(x, nd) for x in v]
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, U64):
        return str(int(v))
    if isinstance(v, I64):
        return int(v) if abs(int(v)) < 2 ** 53 else str(int(v))
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        r = round(float(v), nd)
        return 0.0 if r == 0 else r
    return common.jsonable(v)


def logic_rel(path):
    """Logic/Module/X/X_eb36.logic.module.ain (as levels name it) -> Logic/X_eb36.logic.module.ainb (the romfs file)."""
    base = path.rsplit("/", 1)[-1]
    return "Logic/" + (base if base.endswith(".ainb") else base + "b")


# Index

def index_file(fs, rel):
    parts = rel.split("/")
    if "BancBasedResource" in parts:
        return index_resource(fs, rel)
    if "GameBancParam" in parts:
        return index_banc_param(fs, rel)
    return index_level(fs, rel)


def _level_names(rel, file_path):
    fn = os.path.basename(rel)[:-len(".bcett.byml.zs")]
    level = None
    if isinstance(file_path, str) and file_path.endswith(".bcett.json"):
        level = file_path.rsplit("/", 1)[-1][:-len(".bcett.json")]
    if level and fn.startswith(level + "_"):
        layer = fn[len(level) + 1:]
    else:
        level, _, layer = fn.rpartition("_")
    toks = level.split("_")
    age, variant = None, None
    for i, t in enumerate(toks):
        if t in ("Adult", "Child"):
            age = t.lower()
            variant = "_".join(toks[i + 1:]) or None
            break
    return level, layer, age, variant


def index_level(fs, rel):
    c = ctx(fs)
    root = common.read_byml(fs, rel) or {}
    parts = rel.split("/")
    level, layer, age, variant = _level_names(rel, root.get("FilePath"))
    rec = {"kind": "level", "area": parts[-2], "level": level, "layer": layer, "age": age}
    if variant:
        rec["variant"] = variant
    if parts[0] != "Banc":
        rec["pack"] = parts[0]  # AoC1
    if root.get("FilePath"):
        rec["file_path"] = root["FilePath"]
    rec["actors"] = [actor(c, a) for a in root.get("Actors") or []]
    rec["ai_groups"] = [ai_group(c, g) for g in root.get("AiGroups") or []]
    for key, out in (("FarDeleteGroups", "far_delete_groups"), ("SimultaneousGroups", "simultaneous_groups")):
        if root.get(key):
            rec[out] = [[_h(x) for x in grp] for grp in root[key]]
    if root.get("Rails"):
        rec["rails"] = len(root["Rails"])
    plg = []
    for row in root.get("PlgGdTable") or []:
        path = row.get("GameDataPath") or ""
        plg.append({"guid": _h(row.get("PlgGuid", 0)), "flag": path.rsplit("?", 1)[-1] if "?" in path else path,
                    "type": row.get("GameDataType")})
    if plg:
        rec["plg_gd"] = plg
    pgs = []
    for g in (root.get("PhiveHeader") or {}).get("PlacementGroups") or []:
        e = {"guid": _h(g.get("GroupGUID", 0)), "id": int(g.get("GroupID", -1)), "type": g.get("Type")}
        if int(g.get("ParentGroupGUID", 0) or 0):
            e["parent"] = _h(g["ParentGroupGUID"])
        pgs.append(e)
    if pgs:
        rec["placement_groups"] = pgs
    return rec


def actor(c, a):
    h = int(a.get("Hash", 0))
    out = {"hash": str(h), "gyaml": a.get("Gyaml")}
    if a.get("Name"):
        out["name"] = a["Name"]
    if a.get("Translate") is not None:
        out["pos"] = common.rnd(a["Translate"], 2)
    rot = a.get("Rotate")
    if rot is not None:
        r = [val(x) for x in rot]
        if any(r):
            out["rot"] = r
    sc = a.get("Scale")
    if sc is not None:
        s = [val(x) for x in sc]
        if s != [1.0, 1.0, 1.0]:
            out["scale"] = s
    p = a.get("Presence")
    if p:
        pr = {"flag": p.get("FlagName"), "neg": bool(p.get("IsNegation")), "lazy": bool(p.get("IsCheckLazy"))}
        t = gd_name_type(c, p.get("FlagName") or "")
        if t:
            pr["type"] = t
        out["presence"] = pr
    links = a.get("Links")
    if links:
        out["links"] = [{"dst": _h(ln.get("Dst", 0)), "src": _h(ln.get("Src", 0)), "name": ln.get("Name"),
                         "gyaml": ln.get("Gyaml")} for ln in links]
    dyn = a.get("Dynamic")
    if dyn:
        out["dyn"] = val(dyn)
        if "DefaultDungeonRoomIndex" in dyn:
            out["room"] = int(dyn["DefaultDungeonRoomIndex"])
        fk = [k for k, v in dyn.items() if isinstance(v, str) and v and gd_name_type(c, v)]
        ek = [k for k, v in dyn.items() if isinstance(v, str) and v and is_event(c, v)]
        if fk:
            out["flag_keys"] = fk
        if ek:
            out["event_keys"] = ek
    if h in c["b64"]:
        out["b64"] = True
    if (h ^ 2) in c["b64"]:
        out["b64_x2"] = True
    if a.get("Rails"):
        out["rails"] = [_h(r.get("Dst", 0)) for r in a["Rails"]]
    ph = a.get("Phive") or {}
    pl = ph.get("Placement") or {}
    if "ID" in pl and int(pl["ID"]) != h:
        out["phive_id"] = _h(pl["ID"])
    if pl.get("GroupGUID"):
        out["phive_group"] = _h(pl["GroupGUID"])
    cl = ph.get("ConstraintLink")
    if cl:
        con = {}
        if cl.get("Refers"):
            con["refers"] = [[r.get("Type"), _h(r.get("Owner", 0))] for r in cl["Refers"]]
        if cl.get("Owners"):
            con["owners"] = [[o.get("Type"), _h(o.get("Refer", 0))] for o in cl["Owners"]]
        if con:
            out["constraint"] = con
    if a.get("IsForceActive"):
        out["force_active"] = True
    return out


def ai_group(c, g):
    logic = logic_rel(g.get("Logic") or "")
    out = {"hash": _h(g.get("Hash", 0)), "logic": logic}
    if logic.rsplit("/", 1)[-1] not in c["logic"]:
        out["logic_missing"] = True
    refs_in = g.get("References") or []
    ids = {}
    for r in refs_in:
        ids[r.get("Id")] = ids.get(r.get("Id"), 0) + 1
    refs, paths, subs = {}, {}, {}
    for r in refs_in:
        rid, path = r.get("Id"), r.get("Path") or r.get("Id")
        key = rid if ids[rid] == 1 else path
        n = 2
        base = key
        while key in refs:
            key = f"{base}#{n}"
            n += 1
        refs[key] = _h(r.get("Reference", 0))
        if path != key:
            paths[key] = path
        if r.get("Logic"):
            sl = logic_rel(r["Logic"])
            s = {"logic": sl, "instance": r.get("InstanceName")}
            if sl.rsplit("/", 1)[-1] not in c["logic"]:
                s["logic_missing"] = True
            subs[key] = s
    out["refs"] = refs
    if paths:
        out["paths"] = paths
    if subs:
        out["subs"] = subs
    if g.get("InstanceName"):
        out["instance"] = g["InstanceName"]
    if g.get("Blackboards"):
        out["blackboards"] = list(g["Blackboards"])
    if g.get("Dynamic"):
        out["dyn"] = val(g["Dynamic"])
    return out


def gd_refs(c, v, path="", out=None):
    """The values in v that name a GameData flag, or a *GameDataHash that is one, as [{"path", "flag"}]."""
    out = [] if out is None else out
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, int) and not isinstance(x, bool) and str(k).endswith("GameDataHash") \
                    and int(x) in c["gd_type"]:
                out.append({"path": f"{path}.{k}" if path else str(k), "flag": f"#{int(x)}"})
            else:
                gd_refs(c, x, f"{path}.{k}" if path else str(k), out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            gd_refs(c, x, f"{path}[{i}]", out)
    elif isinstance(v, str) and v and gd_name_type(c, v):
        out.append({"path": path, "flag": v})
    return out


def index_resource(fs, rel):
    c = ctx(fs)
    root = common.read_byml(fs, rel)
    name = os.path.basename(rel).split(".", 1)[0]
    rec = {"kind": "resource", "name": name, "data": val(root) if root is not None else None}
    if rel.split("/")[0] != "Banc":
        rec["pack"] = rel.split("/")[0]
    refs = gd_refs(c, root)
    if refs:
        rec["gd_refs"] = refs
    return rec


def index_banc_param(fs, rel):
    c = ctx(fs)
    root = common.read_byml(fs, rel) or {}
    name = os.path.basename(rel).split(".", 1)[0]
    rec = {"kind": "banc_param", "name": name}
    par = root.get("$parent")
    if isinstance(par, str):
        rec["parent"] = par.rsplit("/", 1)[-1].split(".", 1)[0]
    rec["data"] = val(root)
    refs = gd_refs(c, root)
    if refs:
        rec["gd_refs"] = refs
    return rec


# Summary

def _tname(v):
    return {bool: "bool", int: "int", float: "float", str: "str", list: "list", dict: "dict"}.get(type(v), "other")


def finish(fs, by_file):
    """Cross-file summary. "event_dyn_keys_flow_only" has the keys whose values only matched as a flowchart's
    base name and never as an EventSetting row. Those are mostly coincidences, like a Location or banc name that a
    flowchart also has."""
    c = ctx(fs)
    areas, presence, dyn_keys, flag_keys, event_keys, link_names = {}, {}, {}, {}, {}, {}
    event_setting_keys = set()
    modules, missing = {}, set()
    tot = {"levels": 0, "actors": 0, "presence": 0, "links": 0, "ai_groups": 0, "ai_sub_modules": 0,
           "logic_missing_groups": 0, "b64": 0, "b64_x2": 0, "resources": 0, "banc_params": 0}
    for rel, rec in by_file.items():
        if not isinstance(rec, dict):
            continue
        kind = rec.get("kind")
        if kind == "resource":
            tot["resources"] += 1
            continue
        if kind == "banc_param":
            tot["banc_params"] += 1
            continue
        tot["levels"] += 1
        ar = areas.setdefault(rec["area"], {"files": 0, "actors": 0, "presence": 0, "links": 0, "ai_groups": 0})
        ar["files"] += 1
        acts = rec.get("actors") or []
        ar["actors"] += len(acts)
        tot["actors"] += len(acts)
        for a in acts:
            p = a.get("presence")
            if p:
                ar["presence"] += 1
                tot["presence"] += 1
                presence[p["flag"]] = presence.get(p["flag"], 0) + 1
            for ln in a.get("links") or []:
                ar["links"] += 1
                tot["links"] += 1
                link_names[ln["name"]] = link_names.get(ln["name"], 0) + 1
            tot["b64"] += bool(a.get("b64"))
            tot["b64_x2"] += bool(a.get("b64_x2"))
            for k, v in (a.get("dyn") or {}).items():
                d = dyn_keys.setdefault(k, {"count": 0, "types": {}, "examples": []})
                d["count"] += 1
                t = _tname(v)
                d["types"][t] = d["types"].get(t, 0) + 1
                if len(d["examples"]) < 5 and v not in d["examples"]:
                    d["examples"].append(v)
            for k in a.get("flag_keys") or []:
                flag_keys[k] = flag_keys.get(k, 0) + 1
            for k in a.get("event_keys") or []:
                event_keys[k] = event_keys.get(k, 0) + 1
                if k not in event_setting_keys and event_kind(c, a["dyn"][k]) == "setting":
                    event_setting_keys.add(k)
        for g in rec.get("ai_groups") or []:
            ar["ai_groups"] += 1
            tot["ai_groups"] += 1
            modules.setdefault(g["logic"], []).append({"file": rel, "hash": g["hash"]})
            if g.get("logic_missing"):
                tot["logic_missing_groups"] += 1
                missing.add(g["logic"])
            for key, s in (g.get("subs") or {}).items():
                tot["ai_sub_modules"] += 1
                modules.setdefault(s["logic"], []).append({"file": rel, "hash": g["refs"][key], "parent": g["hash"]})
                if s.get("logic_missing"):
                    missing.add(s["logic"])

    def by_count(d):
        return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))

    return {"totals": tot, "areas": dict(sorted(areas.items())),
            "presence_flags": by_count(presence),
            "dynamic_keys": dict(sorted(dyn_keys.items())),
            "flag_dyn_keys": by_count(flag_keys), "event_dyn_keys": by_count(event_keys),
            "event_dyn_keys_flow_only": by_count({k: n for k, n in event_keys.items() if k not in event_setting_keys}),
            "link_names": by_count(link_names),
            "ai_group_modules": dict(sorted(modules.items())),
            "logic_missing": sorted(missing)}
