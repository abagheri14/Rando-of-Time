"""List every OoTR trick and glitch the logic refers to, so each can be re-checked on the remake.

usage: python tools/trick_checklist.py      -> data/trick_checklist.csv (+ summary printed)

My rule for the remake port: nothing is on by default, tricks and N64 glitches alike. You turn each
one on by itself, for testing, by listing it in config/tricks.json. Remake-only glitches get added
as new tricks, never ported from OoTR.
"""
import csv
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLITCH_HELPER = re.compile(r"\bcan_(isg|hover|hess|superslide|weirdshot|oi|gdv\w*|dotskip\w*|tsc|mega\w*|equip_swap\w*)\b")


def main():
    logic = json.load(open(os.path.join(HERE, "reference", "ootr", "logic.json"), encoding="utf-8"))
    mq = json.load(open(os.path.join(HERE, "reference", "ootr", "logic_mq.json"), encoding="utf-8"))
    tricks = logic.get("tricks", {})
    helpers = logic.get("helpers", {})
    # which helpers (transitively) mention a trick or a glitch helper
    helper_tricks = {}
    for name, body in helpers.items():
        helper_tricks[name.split("(")[0]] = set(re.findall(r"\b(logic_\w+|glitch_\w+|adv_\w+)\b", body))
    for _ in range(5):
        for name, body in helpers.items():
            key = name.split("(")[0]
            for other, ts in helper_tricks.items():
                if other != key and re.search(r"\b%s\b" % re.escape(other), body):
                    helper_tricks[key] |= ts

    uses = defaultdict(list)  # trick -> [(world, region, what, name)]
    glitch_rules = []
    for world, data in (("vanilla", logic), ("mq", mq)):
        for reg in data["regions"]:
            for what in ("locations", "exits", "events"):
                for name, rule in (reg.get(what) or {}).items():
                    found = set(re.findall(r"\b(logic_\w+|glitch_\w+|adv_\w+)\b", rule))
                    for h, ts in helper_tricks.items():
                        if ts and re.search(r"\b%s\b" % re.escape(h), rule):
                            found |= ts
                    for t in found:
                        uses[t].append((world, reg["name"], what[:-1], name))
                    if GLITCH_HELPER.search(rule):
                        glitch_rules.append((world, reg["name"], name))

    rows = []
    for t in sorted(set(uses) | set(tricks)):
        info = tricks.get(t, {}) if isinstance(tricks, dict) else {}
        u = uses.get(t, [])
        rows.append({
            "trick": t,
            "name": info.get("display_name") or info.get("name") or "",
            "kind": "N64 glitch (off)" if t.startswith(("glitch_", "adv_")) else "glitchless trick (off)",
            "vanilla_rules": sum(1 for x in u if x[0] == "vanilla"),
            "mq_rules": sum(1 for x in u if x[0] == "mq"),
            "examples": "; ".join(f"{x[1]}: {x[3]}" for x in u if x[0] == "vanilla")[:300],
            "tested_in_remake": "",  # notes only: turning a trick on is done in config/tricks.json
        })
    with open(os.path.join(HERE, "data", "trick_checklist.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    g = [r for r in rows if r["kind"].startswith("N64")]
    l = [r for r in rows if not r["kind"].startswith("N64")]
    print(f"glitchless tricks: {len(l)} ({sum(1 for r in l if r['vanilla_rules'])} used by vanilla rules, "
          f"{sum(r['vanilla_rules'] for r in l)} vanilla rules touched)")
    print(f"N64 glitches: {len(g)}; vanilla rules that pass through a helper with a glitch alternative: {sum(r['vanilla_rules'] for r in g)}; "
          f"rules calling glitch helpers directly: {len(glitch_rules)}")
    top = sorted(l, key=lambda r: -r["vanilla_rules"])[:8]
    print("most-used tricks in vanilla logic:", ", ".join(f"{r['trick']} ({r['vanilla_rules']})" for r in top))


if __name__ == "__main__":
    main()
