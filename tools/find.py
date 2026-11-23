"""Search the reward catalog and event item checks.

usage: python tools/find.py TEXT [TEXT ...]      (all words must match; case-insensitive)

Examples:
  python tools/find.py Ocarina_Fairy             where the Fairy Ocarina is given, and where events check for it
  python tools/find.py KokiriForest chest        every chest in Kokiri Forest
  python tools/find.py gold_skulltula Graveyard
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(words):
    words = [w.lower() for w in words]
    rewards = json.load(open(os.path.join(HERE, "data", "rewards.json"), encoding="utf-8"))
    checks = json.load(open(os.path.join(HERE, "data", "event_checks.json"), encoding="utf-8"))
    hit = lambda obj: all(w in json.dumps(obj, ensure_ascii=False).lower() for w in words)
    rs = [r for r in rewards if hit(r)]
    print(f"== {len(rs)} rewards")
    for r in rs:
        where = (f"{r['actor']} @ {r['pos']}" if r["source"] == "placement"
                 else f"{r['call']} in {r['event_file']}")
        flags = " ".join(f for f, on in (("[boss rush]", r.get("dreamworld")), ("[shared flow]", r.get("shared"))) if on)
        print(f"  {r['item']!s:32} {r['id']}\n      {where} {flags}")
    cs = [c for c in checks if hit(c)]
    print(f"== {len(cs)} event checks")
    for c in cs[:200]:
        print(f"  {c['item']:32} {c['call']} in {os.path.basename(c['file'])} ({c['event']})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
