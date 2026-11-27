"""Reads a built patch's text back and checks it against the plan's text ops (hints, text shuffle, any plugin's).

usage: python tools/rando/parity/_hints_check.py ROMFS PATCH_DIR PLAN.json [--show LANG] [--label TEXT]

For every text op, the message in the built archive (PATCH_DIR over the game, tools/romtools.Romfs overlays) has to
read the way the op says. If the op has "markup" that's the whole message, which make_patch.py writes when an op has
it. Otherwise its text runs have to equal the op's runs (a list), or its text has to equal the op's string with the
vanilla message's leading and trailing tags kept. It also checks that the label table finds every op's label
(msbt.misplaced_labels) and that no page has more than 3 lines. A tall page is reported, not an error.
TODO: make_patch.py can't add page breaks yet.
--show LANG prints each changed message of that language (tags as {tag:...}), and --label limits the output to
labels containing TEXT.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))


def check(romfs, patch, plan, show=None, label_part=""):
    """Reads the plan's text ops back from a built patch. Returns (messages checked, [problem], [tall box])."""
    import msbt
    from romtools import Romfs, sarc_files
    langs = msbt.archives(romfs)
    ops = defaultdict(list)
    for op in plan.get("text", []):
        for lang in langs:
            if op.get("lang", "*") in ("*", lang):
                ops[lang].append(op)
    built = Romfs(romfs, os.path.join(HERE, "original"), overlays=[patch])
    vanilla = Romfs(romfs, os.path.join(HERE, "original"))
    bad, tall, checked = [], [], 0
    for lang, lang_ops in sorted(ops.items()):
        rel = langs[lang]
        if not os.path.exists(os.path.join(patch, rel)):
            bad.append(f"{lang}: {rel} not in the patch")
            continue
        new_files, old_files = sarc_files(built.read(rel)), sarc_files(vanilla.read(rel))
        cache = {}
        last = {}
        for op in lang_ops:  # the last op on a label wins (make_patch applies them in order)
            last[(op["file"], op["label"])] = op
        for (f, label), op in sorted(last.items()):
            if f not in cache:
                cache[f] = (msbt.Msbt(new_files[f]), msbt.Msbt(old_files[f]), msbt.misplaced_labels(new_files[f]))
            m, old, misplaced = cache[f]
            checked += 1
            if label in misplaced or label not in m.labels:
                bad.append(f"{lang} {f}:{label}: label not found in the built file")
                continue
            if "copy_from" in op:  # a copy of another message of this language, as built
                src = op["copy_from"]
                ok = src["file"] in new_files and m.get(label) == msbt.Msbt(new_files[src["file"]]).get(src["label"])
            elif "markup" in op and label not in old.labels:  # a new label, compare the whole message
                ok = m.get(label) == msbt.from_markup(op["markup"])
            elif "markup" in op:  # make_patch.py writes the whole message when the op carries it
                old.set_markup(label, op["markup"])
                ok = m.get(label) == old.get(label)
            elif isinstance(op["text"], list):
                ok = m.runs(label) == op["text"]
            else:
                if label not in old.labels:  # add the missing label the same way make_patch.py does for plain text
                    old.add(label)
                old.set_text(label, op["text"])
                ok = m.get(label) == old.get(label)
            if not ok:
                bad.append(f"{lang} {f}:{label}: built text differs from the plan")
            text = m.markup(label)
            pages = text.split("{tag:0,4}")
            worst = max(msbt.plain(msbt.from_markup(p)).count("\n") + 1 for p in pages)
            if worst > 3:
                tall.append(f"{lang} {f}:{label}: {worst} lines in a box")
            if show == lang and label_part in label:
                print(f"== {f}:{label}  ({op.get('note', '')})")
                print("   " + text.replace("\n", "\n   "))
    return checked, bad, tall, len(ops)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("romfs")
    ap.add_argument("patch")
    ap.add_argument("plan")
    ap.add_argument("--show")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    checked, bad, tall, n_langs = check(a.romfs, a.patch, json.load(open(a.plan, encoding="utf-8")), a.show, a.label)
    print(f"{checked} messages checked in {n_langs} languages; {len(bad)} problems; "
          f"{len(tall)} with more than 3 lines in a box")
    for b in bad[:40]:
        print("  BAD", b)
    for t in sorted({x.split(" ", 1)[1] for x in tall})[:40]:
        print("  tall (all languages):", t)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
