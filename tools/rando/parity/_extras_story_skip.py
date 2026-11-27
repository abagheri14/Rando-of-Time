"""Story cutscene skips (remake_skip_story, OOTRR's story skip, here as an option). Part of extras_story.

What's cut, and what's left behind so the world still knows it happened:
- Each dungeon's ending scenes that only show something (the Deku Tree's last words and death, Link leaving the
  forest, the Gorons celebrating, Ruto at the fountain, the sages waking up, the forest and Kakariko after their
  temples, Lake Hylia refilling). Their transitions in Dm_SY_BancChange_EscapeDungeon become a write of the scene's
  played flag, which is all those scenes leave (a few maps read the flags, like the lake's water and the birds on
  Death Mountain). Back-to-back scenes are cut as one run. The scenes that hand over a reward stay, and so do the
  quest steps and flags around them.
  The Kakariko scene after the Fire Temple is also the only step of the village's boot event that waits for the
  load, so it keeps a load wait and a fade-in. Without them the change to the Chamber of Sages comes too early and
  Link stands frozen at the village entrance.
- Zelda and Impa riding out of the castle as you reach the drawbridge. The Ocarina still waits in the moat and Zelda's
  song still plays when you pick it up.
- The white screen after each medallion in the Chamber of Sages: the wait, the sage's parting lines and the wait
  after them. The medallion is given before, and the flag the Forest and Fire ones write after still is.
- The child Temple of Time: its first-entry scene and the Master Sword discovery start a new file played, with the
  first-time light shaft gone.
- The owls. The ones a story scene plays (the first one in Hyrule Field, the one at Zora's River, the Lost Woods ones)
  are cut the same way, and the ones that stop Link by themselves (Hyrule Field near the castle, toward Gerudo Valley
  and toward Lake Hylia, Zora's River) start a new file played. The flight owls on Death Mountain and at Lake Hylia
  still talk when you go up to them.
The steps and flags come from data/rando/extras_story_data.json (_extras_story_build.py STORY_SKIP).
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GRAPH_START = "w0"


def _flag(scene, nxt):
    return {"actor": "GameDataActor", "action": "EventTriggerSetGameDataBool",
            "params": {"GameDataName": f"HavePlayedEvent.{scene}", "Index": -1, "Value": True}, "next": nxt}


def runs(cut, steps):
    """[(first step, [(step, scene), ...], the step after the run)] for every cut step something outside the cut
    reaches. A run follows the cut steps' own next steps, so back-to-back scenes go together."""
    out = []
    for step in cut:
        if all(kind == "next" and where in cut for kind, where, _ in steps[step]["preds"]):
            continue  # only reached from another cut step, which skips past it
        run, cur = [], step
        while cur in cut:
            run.append((cur, cut[cur]))
            cur = steps[cur]["next"]
        out.append((step, run, cur))
    return out


def plan(h, defaults, d, events):
    """Adds the hooks (extras_story Hooks h), the medallion scenes' routes (to `events`) and the new-file defaults.
    Returns the read-back record."""
    sk = d["story_skip"]
    rb = {"files": {f: dict(c) for f, c in sk["files"].items()}, "runs": [], "owls": [], "medals": {}}
    for base, m in sk["medals"].items():
        events.append({"file": base, "flowchart": m["flowchart"], "event": m["boots"], "next": m["to"]})
        rb["medals"][base] = {"flowchart": m["flowchart"], "boots": m["boots"], "to": m["to"]}
    for file, cut in sk["files"].items():
        steps = d["hooks"][file]["steps"]
        waits = sk["load_wait"].get(file, [])
        for first, run, after in runs(cut, steps):
            nodes = {}
            for i, (step, scene) in enumerate(run):
                nxt = f"w{i + 1}" if i + 1 < len(run) else "end"
                nodes[f"w{i}"] = _flag(scene, nxt)
                if step in waits:  # the boot event's own wait for the load, then the screen back in
                    nodes[f"w{i}"]["next"] = f"load{i}"
                    nodes[f"load{i}"] = {"actor": "UISystemActor", "action": "EventWaitCloseLoadingFade",
                                         "params": {"IsWaitEnd": True}, "next": f"fade{i}"}
                    nodes[f"fade{i}"] = {"copy": sk["fade_in"][file], "next": nxt}
            for n in nodes.values():
                if n.get("next") == "end":
                    n["next"] = f"@{after}" if after else None
            h.pre_hook(file, first, nodes, GRAPH_START)
            rb["runs"].append({"file": file, "first": first, "scenes": [s for _, s in run], "after": after})
    for flag in [f"HavePlayedEvent.{owl}" for owl in sk["owls"]] + list(sk["new_file"]):
        defaults[flag] = True
        rb["owls"].append(flag)
    return rb


def _walk(fc):
    """Indices of every step reachable from the flowchart's entry points (next, cases, forks and their joins)."""
    seen, todo = set(), [ep["main"] for ep in fc["entry_points"].values()]
    while todo:
        i = todo.pop()
        if i is None or i >= len(fc["events"]) or i in seen:
            continue
        seen.add(i)
        e = fc["events"][i]
        for k in ("next", "join"):
            if e.get(k) is not None:
                todo.append(e[k])
        todo += [c["next"] for c in e.get("cases") or []]
        todo += list(e.get("forks") or [])
    return seen


def verify(patch, rb, romfs):
    """Reads the story skip back from a built patch: no reachable step plays a cut scene, a reachable step writes each
    one's played flag, and the owls' flags are on for a new file."""
    import sys
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from romtools import Romfs, byml_load, murmur3_32
    from evfl import Evfl
    from parity._story_build import newest, flat
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    bad = []
    for file, cut in rb["files"].items():
        rel, _ = newest(romfs, file)
        if not os.path.exists(os.path.join(patch, rel)):
            bad.append(f"story skip: {rel} not in the patch")
            continue
        fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == file)
        played, written = set(), set()
        for i in _walk(fc):
            e = fc["events"][i]
            if e.get("actor") is None or "action" not in e:
                continue
            a = fc["actors"][e["actor"]]
            act, p = f"{a['name']}.{a['actions'][e['action']]}", flat(e.get("params"), {})
            if act == "EventSystemActor.EventTransition" and p.get("EventName") in cut.values():
                played.add(p["EventName"])
            if act == "GameDataActor.EventTriggerSetGameDataBool" and p.get("Value") is True:
                written.add(str(p.get("GameDataName")))
        bad += [f"story skip: {file} still plays {s}" for s in sorted(played)]
        bad += [f"story skip: {file}: nothing writes HavePlayedEvent.{s}" for s in sorted(cut.values())
                if f"HavePlayedEvent.{s}" not in written]
    for base, m in (rb.get("medals") or {}).items():
        _, versions = newest(romfs, base)
        for v in versions:
            rel = f"Event/EventFlow/{v}"
            if not os.path.exists(os.path.join(patch, rel)):
                bad.append(f"story skip: {rel} not in the patch")
                continue
            fc = next(f for f in Evfl(fs.read(rel)).flowcharts if f["name"] == m["flowchart"])
            e = next(x for x in fc["events"] if x["name"] == m["boots"])
            nxt = e.get("next")
            got = fc["events"][nxt]["name"] if nxt is not None and nxt < len(fc["events"]) else None
            if got != m["to"]:
                bad.append(f"story skip: {v} {m['boots']} leads to {got}, not {m['to']}")
    if rb.get("owls"):
        gd, _ = byml_load(fs.read("GameData/GameDataList.Product.110.byml.zs"), allow_big=True)
        index = {e["Hash"]: e for t, rows in gd["Data"].items() if t == "Bool" for e in rows}
        bad += [f"story skip: {f} isn't on for a new file" for f in rb["owls"]
                if index.get(murmur3_32(f), {}).get("DefaultValue") is not True]
    return bad
