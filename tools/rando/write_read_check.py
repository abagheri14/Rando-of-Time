"""Read-back: no event flow reads a game-data value back before a write to it has landed.

The game applies a game-data write a frame or two after the flow step that asks for it (NX2-ZOOTR found
this too: its shared get wrote the item's name and compared it at once, and
so compared the previous item's). We hit it with the Triforce Piece too. Its credit added one to
Rando_TriforcePieceNum and its count text (GetPouchContent:Rando_TriforceAfter) read the count right away, so the
first piece read the old 0 and showed nothing, and the second read 1 and said "1 of 20".

scan(files) walks every flow from each step that writes a game-data key along every branch, into the sub-flows it
calls (in any of the files), until a step reads that key or a settling step comes first.
  - writes: EventTriggerSetGameData*, ...AddOrSub*, ...Copy* (its destination), EventTriggerSubGameDataInt
    (GameDataA)
  - reads: EventQueryIsGameData*, EventQueryGameData*Branch, or a write that reads it (AddOrSub, Copy's source)
  - settling steps: an EventWait of at least SETTLE_FRAMES frames, or a step that waits on the player (a talk, a
    window, a choice, so IsWaitEnd True on SystemTextNPC / UISystemActor talks and windows)
Vanilla never reads a key it just wrote without one (its five write-then-read sequences all wait).

usage: python tools/rando/write_read_check.py ROMFS [PATCH_DIR]   (all event flows: the patch's over the game's)
verify(patch, romfs) -> (problems, sequences checked)"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))

SETTLE_FRAMES = 2  # NX2-ZOOTR's EventWait fix gives the write two frames, and vanilla waits at least this long
WRITES = {"EventTriggerSetGameDataInt": "GameDataName", "EventTriggerSetGameDataBool": "GameDataName",
          "EventTriggerSetGameDataFloat": "GameDataName", "EventTriggerSetGameDataEnum": "GameDataName",
          "EventTriggerSetGameDataString64": "GameDataName", "EventTriggerSetGameDataString32": "GameDataName",
          "EventTriggerSetGameDataVector3f": "GameDataName", "EventTriggerAddOrSubGameDataInt": "GameDataName",
          "EventTriggerAddOrSubGameDataFloat": "GameDataName", "EventTriggerCopyGameDataInt": "DstGameDataName",
          "EventTriggerCopyGameDataFloat": "DstGameDataName", "EventTriggerCopyGameDataString64": "DstGameDataName",
          "EventTriggerSubGameDataInt": "GameDataA", "EventTriggerSetGameDataBoolArrayAllOnce": "GameDataName"}
READ_ACTIONS = {"EventTriggerAddOrSubGameDataInt": ("GameDataName",), "EventTriggerAddOrSubGameDataFloat":
                ("GameDataName", "AddGameData"), "EventTriggerCopyGameDataInt": ("SrcGameDataName",),
                "EventTriggerCopyGameDataFloat": ("SrcGameDataName",), "EventTriggerCopyGameDataString64":
                ("SrcGameDataName",), "EventTriggerSubGameDataInt": ("GameDataA", "GameDataB")}
WAIT_ON_PLAYER = ("EventTalk", "EventTalkWithoutPlayer", "EventOpenMessage", "EventTriggerRequestOpenGetWindow",
                  "EventTriggerRequestOpenPickUpWindow", "EventCloseMessageDialog")  # (the get window reads the message
# target name right after EventCloseMessageDialog, GetPouchContent Event9 -> Event60)
MAX_STEPS = 400


def settle(nxt):
    """A plan event node that lets a game-data write land before the next step reads it.
    It's the game's own pattern (SharpFlatSpiritTalk_EraseObject Event19/71/73/108 do write, GameSystemActor.EventWait
    2 frames, read). Every flow these plugins write into has GameSystemActor with EventWait (GetPouchContent,
    Dm_SY_Get, Dm_SY_GetInEvent, Dm_SY_Treasurebox, Dm_SY_TreasureboxSmall, Dm_SY_InsertBottle)."""
    return {"actor": "GameSystemActor", "action": "EventWait", "params": {"IsWaitEnd": True, "Frames": SETTLE_FRAMES},
            "next": nxt}


def _prm(e, k):
    return ((e.get("params") or {}).get("items") or {}).get(k, {}).get("value")


class Flows:
    """Every flowchart of the event files given ({rel: bytes}), with entry points and sub-flow calls resolved."""

    def __init__(self, files):
        from evfl import Evfl
        self.fc, self.entries = {}, {}
        for rel, data in files.items():
            try:
                ev = Evfl(data)
            except Exception:  # noqa: BLE001  (a file the reader doesn't know: not ours to judge here)
                continue
            for fc in ev.flowcharts:
                self.fc[fc["name"]] = fc
                eps = fc.get("entry_points") or {}
                items = eps.items() if isinstance(eps, dict) else [(x.get("name"), x) for x in eps]
                for name, ep in items:
                    idx = ep.get("main") if isinstance(ep, dict) else ep
                    if isinstance(idx, int):
                        self.entries[(fc["name"], name)] = idx

    def kind(self, fc, e):
        a = fc["actors"][e["actor"]] if e.get("actor") is not None and e["actor"] < len(fc["actors"]) else {}
        if e["type"] == "action":
            return a.get("name"), (a.get("actions") or [None])[e["action"]] if e.get("action") is not None else None
        if e["type"] == "switch":
            return a.get("name"), (a.get("queries") or [None])[e["query"]] if e.get("query") is not None else None
        return None, None

    def nexts(self, name, i):
        """(flowchart, index) pairs a step goes to. A sub-flow goes into its entry, and then on to its own next."""
        fc = self.fc[name]
        e = fc["events"][i]
        out = []
        if e["type"] == "switch":
            out = [(name, c["next"]) for c in e.get("cases") or []]
        elif e["type"] == "fork":
            out = [(name, x) for x in e.get("forks") or []] + [(name, e.get("join"))]
        elif e["type"] == "join":
            out = [(name, e.get("next"))]
        elif e["type"] == "subflow":
            target = (e.get("flowchart") or name, e.get("entry_point"))
            if target in self.entries:
                out.append((target[0], self.entries[target]))
            out.append((name, e.get("next")))
        else:
            out = [(name, e.get("next"))]
        return [(f, x) for f, x in out if x is not None and x != 0xFFFF and f in self.fc and x < len(self.fc[f]["events"])]


def scan(flows, only=None):
    """[(writer "flowchart:event", key, reader "flowchart:event", [steps between])] for every read of a key with no
    settling step after its write. only: flowchart names to start from (default all)."""
    found = []
    for name, fc in flows.fc.items():
        if only and name not in only:
            continue
        for i, e in enumerate(fc["events"]):
            if e["type"] != "action":
                continue
            _, act = flows.kind(fc, e)
            if act not in WRITES:
                continue
            key = _prm(e, WRITES[act])
            if not isinstance(key, str) or not key:
                continue
            seen, todo = set(), [(f, x, ()) for f, x in flows.nexts(name, i)]
            steps = 0
            while todo and steps < MAX_STEPS:
                f, x, path = todo.pop()
                if (f, x) in seen:
                    continue
                seen.add((f, x))
                steps += 1
                g = flows.fc[f]
                s = g["events"][x]
                actor, what = flows.kind(g, s)
                if s["type"] == "switch" and key in [it.get("value") for it in
                                                     ((s.get("params") or {}).get("items") or {}).values()]:
                    found.append((f"{name}:{e['name']}", key, f"{f}:{s['name']}", list(path)))
                    continue
                if s["type"] == "action" and what == "EventWait":
                    fr = _prm(s, "Frames")
                    if not isinstance(fr, (int, float)) or fr >= SETTLE_FRAMES:  # an argument's frames count as settled
                        continue  # settled
                if s["type"] == "action" and what in WAIT_ON_PLAYER and _prm(s, "IsWaitEnd") is not False:
                    continue  # waits on the player, so many frames
                if s["type"] == "action" and what in WRITES and _prm(s, WRITES[what]) == key:
                    continue  # written again, that write gets checked on its own
                label = f"{actor}.{what}" if what else s["type"]
                if what == "EventWait":
                    label += f"({_prm(s, 'Frames')})"
                todo += [(ff, xx, path + (label,)) for ff, xx in flows.nexts(f, x)]
    return found


def _event_files(romfs, patch=None):
    from romtools import Romfs
    fs = Romfs(romfs, os.environ.get("REMAKE_ORIGINAL") or os.path.join(HERE, "original"), [patch] if patch else [])
    d = os.path.join(romfs, "Event", "EventFlow")
    names = set(os.listdir(d))
    if patch and os.path.isdir(os.path.join(patch, "Event", "EventFlow")):
        names |= set(os.listdir(os.path.join(patch, "Event", "EventFlow")))
    return fs, sorted(n for n in names if n.endswith(".bfevfl.zs"))


def verify(patch, romfs):
    """Write-then-read sequences with no settling step where the write or the read is one of our steps (Rando*, the
    plugins' graphs), in any flowchart. A read of ours after a vanilla write counts too."""
    fs, names = _event_files(romfs, patch)
    files = {n: fs.read(f"Event/EventFlow/{n}") for n in names}
    flows = Flows(files)
    ours = set()
    for n in os.listdir(os.path.join(patch, "Event", "EventFlow")) if os.path.isdir(
            os.path.join(patch, "Event", "EventFlow")) else []:
        from evfl import Evfl
        try:
            ours |= {fc["name"] for fc in Evfl(files[n]).flowcharts}
        except Exception:  # noqa: BLE001
            pass
    hits = [h for h in scan(flows) if ":Rando" in h[0] or ":Rando" in h[2]]
    bad = [f"{w} writes {k} and {r} reads it with no wait between (it reads the old value: wait "
           f"{SETTLE_FRAMES} frames first){' via ' + ' > '.join(p[-4:]) if p else ''}" for w, k, r, p in hits]
    return bad, len(ours)


if __name__ == "__main__":
    romfs = sys.argv[1]
    patch = sys.argv[2] if len(sys.argv) > 2 else None
    fs, names = _event_files(romfs, patch)
    flows = Flows({n: fs.read(f"Event/EventFlow/{n}") for n in names})
    hits = scan(flows)
    for w, k, r, p in hits:
        print(f"{w} writes {k}; {r} reads it; between: {' > '.join(p) or '(nothing)'}")
    print(f"{len(hits)} write-then-read sequences without a settling step in {len(flows.fc)} flowcharts")
