"""Queries over the game-logic index (cache/gamedb, built with tools/gamedb/build.py).

    from gamedb.db import GameDB
    db = GameDB()                       # vanilla; GameDB("seed1") = the game as out/seed1/patch makes it
    db.setters("HyruleField_ArriveEntrance")    # what sets/clears a flag (events, logic modules, new-file default)
    db.readers("WaterTemple_Room07_00")         # what reads it (presences, logic, events, schedules, expressions)
    db.gates("9829790505452123995")             # what gates a placement (or an InstanceName / actor name)
    db.quest("Get_StoneOfFire")                 # the quest's steps, every request of each step, every reader
    db.backwards("Get_StoneOfFire")             # requests that can move the quest back to an earlier step

Every answer is plain data, lists of dicts with refs into the game files, and tools/gamedb/query.py prints them.
"""
import os
import re
import sys
from collections import defaultdict
from functools import cached_property

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

LEAF = re.compile(r"\b(flag|step|int|enum|player|time|node|unknown|const|hit|arg|bb|game):([^,()\s]+)")
STEP_LEAF = re.compile(r"^(?P<ch>[A-Za-z0-9_]+?)(?P<op>>=|<=|>|<|=)(?P<step>[A-Za-z0-9_]+)$")
EXP_STEP = re.compile(r"^(?P<ch>.+?)_(?P<kind>IsAfter|IsBefore|IsEqual|IsAfterOrEqual|IsBeforeOrEqual)_(?P<step>.+)_Exp$")
EXP_DONE = re.compile(r"^(?P<ch>.+?)_IsCompleted_Exp$")


def leaves(formula):
    """[(kind, value)] of a formula string (SCHEMA.md syntax)."""
    return LEAF.findall(formula or "")


def challenge_of(path_or_name):
    """'Work/Challenge/SageOfWater.game__challenge__Challenge.gyml' -> 'SageOfWater'."""
    s = str(path_or_name or "")
    s = s.rsplit("/", 1)[-1]
    return s.split(".", 1)[0]


class GameDB:
    def __init__(self, tag=common.BASE_TAG):
        self.tag = tag
        self._docs = {}

    # Sections
    def doc(self, section):
        if section not in self._docs:
            self._docs[section] = common.load(section, self.tag)
        return self._docs[section]

    def files(self, section):
        try:
            return self.doc(section)["by_file"]
        except FileNotFoundError:
            if section in ("gamedata", "actors"):  # most questions don't need these, so answer without them
                return {}
            raise

    def summary(self, section):
        try:
            return self.doc(section).get("summary") or {}
        except FileNotFoundError:
            if section in ("gamedata", "actors"):
                return {}
            raise

    # Gamedata
    @cached_property
    def gd(self):
        rec = self.files("gamedata").get("GameData/GameDataList.Product.110.byml.zs") or {}
        return rec.get("keys", {})

    @cached_property
    def b64(self):
        rec = self.files("gamedata").get("GameData/GameDataList.Product.110.byml.zs") or {}
        return set(rec.get("b64", []))

    @cached_property
    def challenges(self):
        return self.summary("gamedata").get("challenges", {})

    def key(self, name):
        return self.gd.get(name)

    def step_index(self, challenge, step):
        steps = (self.challenges.get(challenge) or {}).get("steps") or []
        if step in steps:
            return steps.index(step)
        if step == "Complete":
            return len(steps)
        return None

    def expand(self, name, depth=6):
        """A BoolExp's formula with nested expression flags expanded (depth-limited)."""
        k = self.key(name) or {}
        f = k.get("exp")
        if not f or depth <= 0:
            return f
        def sub(m):
            kind, v = m.group(1), m.group(2)
            if kind == "flag" and (self.key(v) or {}).get("exp"):
                return f"[{v}: {self.expand(v, depth - 1)}]"
            return m.group(0)
        return LEAF.sub(sub, f)

    @cached_property
    def exp_users(self):
        """{flag: [expression flags whose formula reads it]} (one level)."""
        out = defaultdict(list)
        for name, k in self.gd.items():
            for kind, v in leaves(k.get("exp")):
                if kind in ("flag", "int", "enum"):
                    out[re.split(r"[<>=!\[]", v)[0]].append(name)
                elif kind == "step":
                    m = STEP_LEAF.match(v)
                    if m:
                        out["@step:" + m.group("ch")].append(name)
        return out

    # Levels
    @cached_property
    def placements(self):
        """{hash: [(level rel, actor record)]} (a hash can sit in several layers or variants)."""
        out = defaultdict(list)
        for rel, rec in self.files("levels").items():
            for a in rec.get("actors") or []:
                out[a["hash"]].append((rel, a))
        return out

    @cached_property
    def by_instance(self):
        """{InstanceName (placement Name or AiGroup Id): [(level rel, hash)]}."""
        out = defaultdict(list)
        for rel, rec in self.files("levels").items():
            for a in rec.get("actors") or []:
                if a.get("name"):
                    out[a["name"]].append((rel, a["hash"]))
            for g in rec.get("ai_groups") or []:
                for iid, h in (g.get("refs") or {}).items():
                    if (rel, h) not in out[iid]:
                        out[iid].append((rel, h))
        return out

    @cached_property
    def by_gyaml(self):
        out = defaultdict(list)
        for rel, rec in self.files("levels").items():
            for a in rec.get("actors") or []:
                out[a["gyaml"]].append((rel, a["hash"]))
        return out

    @cached_property
    def group_refs(self):
        """The logic modules that run on each placement:
        {placement hash: [(level rel, logic rel, InstanceName, group hash)]}."""
        out = defaultdict(list)
        for rel, rec in self.files("levels").items():
            for g in rec.get("ai_groups") or []:
                for iid, h in (g.get("refs") or {}).items():
                    out[h].append((rel, g.get("logic"), iid, g.get("hash")))
        return out

    @cached_property
    def links_to(self):
        """{dst hash: [(level rel, src hash, src gyaml, link)]}."""
        out = defaultdict(list)
        for rel, rec in self.files("levels").items():
            for a in rec.get("actors") or []:
                for ln in a.get("links") or []:
                    d = str(ln.get("dst") or ln.get("Dst") or "")
                    if d:
                        out[d].append((rel, a["hash"], a["gyaml"], ln))
        return out

    @cached_property
    def presence_readers(self):
        out = defaultdict(list)
        for rel, rec in self.files("levels").items():
            for a in rec.get("actors") or []:
                p = a.get("presence")
                if p:
                    out[p["flag"]].append({"file": rel, "hash": a["hash"], "gyaml": a["gyaml"], "neg": p.get("neg"),
                                           "lazy": p.get("lazy")})
        return out

    # Logic
    def module(self, logic_rel):
        return self.files("logic").get(logic_rel)

    def actor_gate(self, logic_rel, instance):
        m = self.module(logic_rel) or {}
        return (m.get("actors") or {}).get(instance)

    @cached_property
    def schedules(self):
        """{actor name: schedule record}."""
        out = {}
        for rel, rec in self.files("logic").items():
            if rec.get("kind") == "schedule":
                out[rec.get("actor") or os.path.basename(rel).split(".")[0]] = dict(rec, file=rel)
        return out

    @cached_property
    def step_schedules(self):
        """{actor: [schedule]} of the quest-step schedules (Pack/AIScheduleParam: <Challenge>_<Step>_<Actor>)."""
        out = defaultdict(list)
        for rel, rec in self.files("logic").items():
            if rec.get("kind") == "schedule_pack":
                for path, s in (rec.get("schedules") or {}).items():
                    out[s.get("actor")].append(dict(s, file=rel, path=path))
        return out

    # Queries
    def setters(self, flag):
        """Everything that writes a flag: [{"via", ...}]."""
        out = []
        for r in (self.summary("events").get("setters") or {}).get(flag, []):
            out.append(dict(r, via="event"))
        for r in (self.summary("logic").get("setters") or {}).get(flag, []):
            out.append(dict(r, via="logic"))
        k = self.key(flag)
        if k is not None and k.get("default") not in (None, False, 0, "", 0.0):
            out.append({"via": "new-file default", "value": k.get("default"), "reset": k.get("reset")})
        for rel, rec in self.files("actors").items():
            for s in rec.get("saves") or []:
                if s.get("flag") == flag or s.get("key") == flag:
                    out.append(dict(s, via="actor", file=rel, actor=rec.get("actor")))
        return out

    def readers(self, flag):
        out = []
        for r in self.presence_readers.get(flag, []):
            out.append(dict(r, via="presence"))
        for r in (self.summary("events").get("readers") or {}).get(flag, []):
            out.append(dict(r, via="event"))
        for r in (self.summary("logic").get("readers") or {}).get(flag, []):
            out.append(dict(r, via="logic"))
        for actor in (self.summary("logic").get("schedule_conditions") or {}).get(flag, []):
            out.append({"via": "schedule", "actor": actor})
        for e in self.exp_users.get(flag, []):
            out.append({"via": "expression", "exp": e, "users": len(self.readers_shallow(e))})
        return out

    def readers_shallow(self, flag):
        return (self.presence_readers.get(flag, []) + (self.summary("events").get("readers") or {}).get(flag, [])
                + (self.summary("logic").get("readers") or {}).get(flag, []))

    def resolve(self, target):
        """A placement hash, an InstanceName, a gyaml or 'Area/kind/hash' -> [(level rel, hash)]."""
        t = str(target)
        if "/" in t and t.rsplit("/", 1)[-1].isdigit():
            t = t.rsplit("/", 1)[-1]
        if t.isdigit():
            return [(rel, t) for rel, _ in self.placements.get(t, [])]
        if t in self.by_instance:
            return list(self.by_instance[t])
        return list(self.by_gyaml.get(t, []))

    def gates(self, target):
        """What decides whether a placement is there / works. Returns [{"hash", "file", "gyaml", "presence",
        "logic": [...], "linked_from": [...], "links": [...], "schedule", "flag_keys"}]."""
        out = []
        for rel, h in self.resolve(target):
            a = next((x for f, x in self.placements.get(h, []) if f == rel), None)
            if a is None:
                continue
            g = {"hash": h, "file": rel, "gyaml": a["gyaml"], "pos": a.get("pos"), "name": a.get("name")}
            if a.get("presence"):
                p = a["presence"]
                g["presence"] = p
                if (self.key(p["flag"]) or {}).get("exp"):
                    g["presence_exp"] = self.expand(p["flag"])
            logic = []
            for lrel, mod, iid, ghash in self.group_refs.get(h, []):
                if lrel != rel and not _same_level(lrel, rel):
                    continue
                gate = self.actor_gate(mod, iid)
                logic.append({"module": mod, "instance": iid, "group": ghash,
                              "class": (gate or {}).get("class"), "gates": (gate or {}).get("gates") or {}})
            if logic:
                g["logic"] = logic
            lf = [{"file": f, "src": s, "gyaml": gy, "link": ln} for f, s, gy, ln in self.links_to.get(h, [])
                  if _same_level(f, rel)]
            if lf:
                g["linked_from"] = lf
            if a.get("links"):
                g["links"] = a["links"]
            sch = self.schedules.get(a["gyaml"])
            if sch:
                g["schedule"] = [{"cond": s.get("cond"), "events": [e.get("setting") for e in s.get("events") or []]}
                                 for s in sch.get("states") or []]
            steps = self.step_schedules.get(a["gyaml"])
            if steps:
                g["step_schedules"] = [f"{s.get('challenge')}:{s.get('step')}" for s in steps]
            for k in ("flag_keys", "event_keys"):
                if a.get(k):
                    g[k] = {x: (a.get("dyn") or {}).get(x) for x in a[k]}
            if a.get("room") is not None:
                g["room"] = a["room"]
            out.append(g)
        return out

    def quest(self, challenge, step=None):
        """{"steps", "requests": {step: [...]}, "readers": [...]} for a Challenge (quest)."""
        steps = (self.challenges.get(challenge) or {}).get("steps") or []
        req = defaultdict(list)
        for r in (self.summary("events").get("step_requests") or {}).get(challenge, []):
            req[r.get("step")].append(r)
        readers = []
        for r in (self.summary("logic").get("step_readers") or {}).get(challenge, []):
            readers.append(dict(r, via="logic"))
        for flag, rs in (self.summary("events").get("readers") or {}).items():
            for r in rs:
                if r.get("kind") in ("step_query", "step") and r.get("challenge") == challenge:
                    readers.append(dict(r, via="event", flag=flag))
        exps = [n for n in self.gd if n.startswith(challenge + "_") and n.endswith("_Exp")]
        exps += self.exp_users.get("@step:" + challenge, [])
        for e in sorted(set(exps)):
            for r in self.readers_shallow(e):
                readers.append(dict(r, exp=e))
        if step:
            req = {step: req.get(step, [])}
            readers = [r for r in readers if step in str(r.get("exp", "")) or r.get("step") == step]
        return {"challenge": challenge, "steps": steps, "requests": dict(req), "readers": readers}

    def backwards(self, challenge):
        """Requests of a quest step that can run while the quest is already past it, which moves the quest back.
        A request is safe when it ignores a completed quest AND a guard on its path checks this quest's step. The rest
        are listed with their guards so a reader can judge. Returns [{"step", "index", "ignore_completed", "guarded",
        "guards", ref...}]"""
        out = []
        qrx = re.compile(rf"^(Step_{re.escape(challenge)}|{re.escape(challenge)}_(IsAfter|IsBefore|IsEqual|"
                         rf"IsAfterOrEqual|IsBeforeOrEqual)_.+_Exp|{re.escape(challenge)}_IsCompleted_Exp)$")

        def quest_guards(guards):
            return [g for g in guards or [] if any(isinstance(v, str) and qrx.match(v)
                                                   for v in (g.get("params") or {}).values())]
        for r in (self.summary("events").get("step_requests") or {}).get(challenge, []):
            idx = self.step_index(challenge, r.get("step"))
            own = quest_guards(r.get("guards"))
            # Every call site must check the quest unless the entry guards its own path.
            callers = r.get("called_from") or []
            via = [quest_guards(c.get("guards")) for c in callers]
            guarded = bool(own) or (bool(callers) and all(via))
            out.append(dict(r, via="event", index=idx, guarded=guarded, quest_guards=own or [g for v in via for g in v],
                            risk=("none" if (r.get("ignore_completed") and guarded) else
                                  "guarded (check the guard's step)" if guarded else
                                  "back from Complete" if not r.get("ignore_completed") else
                                  "back from later steps")))
        for r in (self.summary("logic").get("setters") or {}).get("@step:" + challenge, []):
            out.append(dict(r, via="logic"))
        out.sort(key=lambda r: (r.get("index") if r.get("index") is not None else 99, str(r.get("file"))))
        return out

    def find(self, text, limit=60):
        """Names containing text: GameData keys, events, logic modules, actors, instances."""
        t = text.lower()
        hits = []
        hits += [("gamedata", n) for n in self.gd if t in n.lower()]
        hits += [("event", b) for b in (self.summary("events").get("newest") or {}) if t in b.lower()]
        hits += [("logic", r) for r in self.files("logic") if t in r.lower()]
        hits += [("actor", r) for r in self.files("actors") if t in r.lower()]
        hits += [("instance", n) for n in self.by_instance if t in n.lower()]
        return hits[:limit]


def _same_level(a, b):
    """Two layers of one level (X_Static / X_Dynamic) or the same file."""
    def stem(r):
        return re.sub(r"_(Static|Dynamic)(\.bcett\.byml\.zs)$", "", r)
    return a == b or stem(a) == stem(b)
