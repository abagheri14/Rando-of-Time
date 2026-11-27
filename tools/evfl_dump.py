"""Print an event flow as readable steps.

usage: python tools/evfl_dump.py ROMFS_DIR EVENT_FILE [ENTRY_POINT]
  EVENT_FILE: a base name ("Dm_SY_Treasurebox") or path; the newest version (.110) is used.
  Without ENTRY_POINT, lists the entry points.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from romtools import Romfs  # noqa: E402
from evfl import Evfl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fmt_params(c):
    if not c:
        return ""
    if c["type"] == "container":
        return "{" + ", ".join(f"{k}={fmt_params(v)}" for k, v in c["items"].items()) + "}"
    if c["type"] == "argument":
        return f"<arg {c['value']}>"
    return repr(c["value"])


def main(romfs, name, entry=None):
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    if os.path.isfile(name):  # a file on disk (e.g. a patch build), compressed or not
        raw = open(name, "rb").read()
        ev = Evfl(fs.zs.decompress(raw) if name.endswith(".zs") else raw)
    else:
        if not name.startswith("Event/"):
            d = os.path.join(romfs, "Event", "EventFlow")
            pat = re.compile(re.escape(name) + r"(?:\.(\d{3}))?\.bfevfl\.zs$")
            # the game reads the newest version (X.110.bfevfl.zs over X.bfevfl.zs). A plain sort puts the
            # unversioned file last ('b' > '1') and dumps the old one
            cands = sorted((int(m.group(1) or -1), f) for f in os.listdir(d) for m in [pat.match(f)] if m)
            if not cands:
                sys.exit(f"no event file named {name}")
            name = "Event/EventFlow/" + cands[-1][1]
        ev = Evfl(fs.read(name))
    print("#", name)
    for fc in ev.flowcharts:
        print(f"flowchart {fc['name']}: {len(fc['events'])} events, actors: "
              + ", ".join(f"{a['name']}" + (f"[{a['sub_name']}]" if a['sub_name'] else "") for a in fc["actors"]))
        if not entry:
            for ep, e in fc["entry_points"].items():
                print(f"  entry {ep} -> {fc['events'][e['main']]['name'] if e['main'] != 0xFFFF else '-'}")
            continue
        ep = fc["entry_points"].get(entry)
        if not ep:
            print("  no entry point", entry)
            continue
        ev_list = fc["events"]
        def t_ret(e):
            return e["type"] != "type6"
        seen, order, stack = set(), [], [ep["main"]]
        while stack:
            i = stack.pop()
            if i == 0xFFFF or i in seen or i >= len(ev_list):
                continue
            seen.add(i)
            order.append(i)
            e = ev_list[i]
            nxt = []
            if "next" in e and t_ret(e):  # a return step (type 6) ends the flow, its field is a value
                nxt.append(e["next"])
            for c in e.get("cases", []):
                nxt.append(c["next"])
            nxt += e.get("forks", [])
            if "join" in e:
                nxt.append(e["join"])
            stack.extend(reversed(nxt))
        for i in order:
            e = ev_list[i]
            t = e["type"]
            name_of = lambda j: ev_list[j]["name"] if j != 0xFFFF and j < len(ev_list) else "END"
            if t == "action":
                a = fc["actors"][e["actor"]]
                line = f"{a['name']}.{a['actions'][e['action']]} {fmt_params(e.get('params'))} -> {name_of(e['next'])}"
            elif t == "switch":
                a = fc["actors"][e["actor"]]
                cases = ", ".join(f"{c['value']}:{name_of(c['next'])}" for c in e["cases"])
                line = f"? {a['name']}.{a['queries'][e['query']]} {fmt_params(e.get('params'))} [{cases}]"
            elif t == "subflow":
                line = f"call {e['flowchart'] or ''}:{e['entry_point']} {fmt_params(e.get('params'))} -> {name_of(e['next'])}"
            elif t == "subflow_switch":
                cases = ", ".join(f"{c['value']}:{name_of(c['next'])}" for c in e["cases"])
                line = f"? call {e['flowchart'] or ''}:{e['entry_point']} {fmt_params(e.get('params'))} [{cases}]"
            elif t == "fork":
                line = f"fork {[name_of(j) for j in e['forks']]} join {name_of(e['join'])}"
            elif t == "join":
                line = f"join -> {name_of(e['next'])}"
            elif t == "type6":
                line = f"return {e.get('hash')} (value {e.get('next')})"
            else:
                line = f"{t} {e.get('next')} {e.get('hash')}"
            print(f"  {e['name']:9} {line}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
