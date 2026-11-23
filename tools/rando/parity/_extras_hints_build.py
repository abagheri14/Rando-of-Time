"""Game text the extras_hints plugin builds on, read from the game files into data/rando/extras_hints.json (./original
copies win). Rerun after a game update:

    python tools/rando/parity/_extras_hints_build.py ROMFS

Per language archive:
  scrub_offer   the Business Scrub offer EventFlowMsg/Enemy_Event:Enemy_Scrub_Business_Heart_01 (the one every
                shuffled scrub sells through): its speaker tag, its price run ({tag:0,3,0000}{tag:2,12,<SimpleShop_Price>}
                rupees{tag:0,3,ffff}, with the plural tag of Polish/Russian) and the text after the price
  loach         the game's own name of the Hyrule loach (the pond owner's catch line MiniGame_Fishing:Talk_150,
                its first highlighted name)
  messages      vanilla markup of every line a hint is added to (TARGETS)
The build stops if a message is missing, a target line is shown as a choice prompt (a page can't follow a choice),
or the scrub offer has no price tag.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
DATA = os.path.join(HERE, "data", "rando", "extras_hints.json")
SCRUB_FILE, SCRUB_LABEL = "EventFlowMsg/Enemy_Event.msbt", "Enemy_Scrub_Business_Heart_01"
FISH_FILE = "EventFlowMsg/MiniGame_Fishing.msbt"
LOACH_LINE = "Talk_150"
# hint -> the vanilla lines a page is added to: (file, label, mode)
TARGETS = {"loach": [(FISH_FILE, "Talk_152", "append")]}
HI, LO = "{tag:0,3,0000}", "{tag:0,3,ffff}"
PRICE_TAG = "{tag:2,12,"


def scrub_parts(markup):
    """(speaker lead, item name, price run, text after the price run) of a scrub offer."""
    lead = re.match(r"(\{tag:3,[^}]*\})*", markup).group(0)
    m = re.search(re.escape(HI) + r"(\{tag:201,[^}]*\})?([^{]*)" + re.escape(LO), markup)
    k = markup.find(PRICE_TAG)
    if not lead or m is None or k < 0:
        raise SystemExit(f"{SCRUB_LABEL}: unexpected layout {markup!r}")
    start = markup.rfind(HI, 0, k)
    end = markup.find(LO, k)
    if start < 0 or end < 0:
        raise SystemExit(f"{SCRUB_LABEL}: no highlighted price run in {markup!r}")
    end += len(LO)
    return lead, m.group(2), markup[start:end], markup[end:]


def loach_name(markup):
    m = re.search(re.escape(HI) + r"([^{]*)" + re.escape(LO), markup)
    if m is None:
        raise SystemExit(f"{LOACH_LINE}: no highlighted name in {markup!r}")
    return " ".join(m.group(1).split())


def build(romfs):
    import msbt
    from evfl import Evfl
    from romtools import Romfs
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    out = {"_about": "Game text the extras_hints plugin builds on (tools/rando/parity/_extras_hints_build.py, from the "
                     "game files, ./original copies winning), per language archive.",
           "scrub_offer": {}, "loach": {}, "messages": {}, "shown_by": {}}
    wanted = sorted({(f, lb) for ts in TARGETS.values() for f, lb, _m in ts})
    for lang in msbt.archives(romfs):
        files = msbt.read_archive(fs, lang)
        scrub = msbt.Msbt(files[SCRUB_FILE])
        lead, name, price, after = scrub_parts(scrub.markup(SCRUB_LABEL))
        out["scrub_offer"][lang] = {"lead": lead, "vanilla_item": name, "price": price, "after": after}
        out["loach"][lang] = loach_name(msbt.Msbt(files[FISH_FILE]).markup(LOACH_LINE))
        for f, lb in wanted:
            m = msbt.Msbt(files[f])
            if lb not in m.labels:
                raise SystemExit(f"{lang}: no message {f}:{lb}")
            out["messages"].setdefault(f"{f}:{lb}", {})[lang] = m.markup(lb)
    # the flow steps that show each line (a choice prompt can't take an appended page)
    shown = {}
    d = os.path.join(romfs, "Event", "EventFlow")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".bfevfl.zs"):
            continue
        ev = Evfl(fs.read("Event/EventFlow/" + fn))
        for fc in ev.flowcharts:
            for e in fc["events"]:
                items = ((e.get("params") or {}).get("items") or {})
                for pname, pv in items.items():
                    mid = (pv or {}).get("value")
                    if not ((pname.startswith("MessageId") or pname == "SellerMessageId") and isinstance(mid, str)
                            and mid.startswith("EventFlowMsg/")):
                        continue
                    n = (items.get("ChoiceNumber") or {}).get("value") or 0 if pname == "MessageId" else 0
                    shown.setdefault(mid, set()).add((fn, e["name"], n))
    for ts in TARGETS.values():
        for f, lb, mode in ts:
            key = f"{f[:-5]}:{lb}"
            uses = shown.get(key, set())
            if not uses:
                raise SystemExit(f"{key}: no flow step shows it")
            if mode == "append" and any(n for _f, _e, n in uses):
                raise SystemExit(f"{key}: shown as a choice prompt ({sorted(uses)}); a page can only go first")
            out["shown_by"][key] = sorted(f"{a}:{b}" for a, b, _n in uses)
    scrub_key = f"{SCRUB_FILE[:-5]}:{SCRUB_LABEL}"
    out["shown_by"][scrub_key] = sorted(f"{a}:{b}" for a, b, _n in shown.get(scrub_key, set()))
    json.dump(out, open(DATA, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(out['scrub_offer'])} languages -> {os.path.relpath(DATA, HERE)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
