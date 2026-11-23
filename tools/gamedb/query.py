"""Ask the game-logic index a question.

usage: python tools/gamedb/query.py [--tag TAG] [--json] QUESTION ARGS
  setters FLAG          what sets or clears a GameData flag (events, logic modules, actors, new-file default)
  readers FLAG          what reads it (placement presences, logic, events, NPC schedules, expression flags)
  flag NAME             the GameData row (type, default, reset) and, for an expression, its formula expanded
  gates TARGET          what gates a placement: TARGET = placement hash, InstanceName or actor name (gyaml)
  quest CHALLENGE [STEP]  a quest's steps, every request of each step, every reader of its steps
  backwards CHALLENGE   step requests that can move the quest back (with their guards)
  find TEXT             names containing TEXT (flags, flows, modules, actors, instances)
--tag seed1 asks the game as out/seed1/patch makes it (build it: tools/gamedb/build.py --overlay ...).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import GameDB  # noqa: E402


def ref(r):
    if r.get("fc") is not None or r.get("entry"):
        return f"{os.path.basename(r.get('file', ''))} {r.get('fc')}:{r.get('entry')} {r.get('event')}"
    if r.get("node") is not None:
        return f"{os.path.basename(str(r.get('file', '')))} node {r.get('node')}"
    if r.get("hash"):
        return f"{os.path.basename(str(r.get('file', '')))} #{r.get('hash')} {r.get('gyaml', '')}"
    return json.dumps({k: v for k, v in r.items() if k != "via"}, ensure_ascii=False)[:200]


def show_ops(rows):
    for r in rows:
        extra = {k: r[k] for k in ("kind", "value", "step", "ignore_completed", "neg", "exp", "actor", "when", "risk")
                 if k in r and r[k] not in (None, "")}
        print(f"  [{r.get('via')}] {ref(r)}  {json.dumps(extra, ensure_ascii=False) if extra else ''}")
        for g in r.get("guards") or []:
            print(f"        if {g.get('call')} {json.dumps(g.get('params'), ensure_ascii=False)[:160]} == {g.get('case')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="vanilla")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("question")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    db = GameDB(a.tag)
    q, args = a.question, a.args
    if q == "setters":
        res = db.setters(args[0])
    elif q == "readers":
        res = db.readers(args[0])
    elif q == "flag":
        res = {"row": db.key(args[0]), "expanded": db.expand(args[0])}
    elif q == "gates":
        res = db.gates(args[0])
    elif q == "quest":
        res = db.quest(args[0], args[1] if len(args) > 1 else None)
    elif q == "backwards":
        res = db.backwards(args[0])
    elif q == "find":
        res = db.find(args[0])
    else:
        raise SystemExit(f"unknown question {q}")
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        return 0
    if q in ("setters", "readers", "backwards"):
        print(f"{q} of {args[0]}: {len(res)}")
        show_ops(res)
    elif q == "quest":
        print(f"{res['challenge']}: steps {' > '.join(res['steps'])}")
        for step, rows in res["requests"].items():
            print(f" step {step}: {len(rows)} request(s)")
            show_ops([dict(r, via='event') for r in rows])
        print(f" readers: {len(res['readers'])}")
        show_ops(res["readers"])
    elif q == "gates":
        for g in res:
            print(f"#{g['hash']} {g['gyaml']} {g.get('name') or ''} in {g['file']} at {g.get('pos')}")
            if g.get("presence"):
                p = g["presence"]
                print(f"  presence: {'NOT ' if p.get('neg') else ''}{p['flag']}{' (lazy)' if p.get('lazy') else ''}"
                      + (f"  = {g['presence_exp']}" if g.get("presence_exp") else ""))
            for m in g.get("logic") or []:
                print(f"  logic {m['module']} as {m['instance']} ({m.get('class')})")
                for inp, f in (m.get("gates") or {}).items():
                    print(f"     {inp} <- {f}")
            for l in g.get("linked_from") or []:
                print(f"  linked from #{l['src']} {l['gyaml']}: {json.dumps(l['link'], ensure_ascii=False)[:160]}")
            for l in g.get("links") or []:
                print(f"  links to {json.dumps(l, ensure_ascii=False)[:160]}")
            for s in g.get("schedule") or []:
                print(f"  schedule state on {s['cond']}: {', '.join(x or '' for x in s['events'])}")
            for k in ("flag_keys", "event_keys"):
                if g.get(k):
                    print(f"  {k}: {g[k]}")
    else:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
