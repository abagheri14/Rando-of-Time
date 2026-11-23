"""OoT Randomizer's text_shuffle for the remake: dialogue lines trade places.

OoTR (Messages.shuffle_messages) permutes its N64 messages within groups of the same shape (plain, choices...) and
keeps hints and important text in place for 'except_hints'. The remake's dialogue is in EventFlowMsg/*.msbt (per
language), and we shuffle it here per language with a seed-fixed permutation:
  - lines:   messages whose text is one run (no tags inside it; the speaker, voice and style tags before and after
             it stay with the message they belong to, Msbt.set_text), not empty
  - choices: choice options (numeric labels such as 0000), among themselves
Never shuffled: messages with variable tags (group 2: prices, counts, names, which only work where they are), text
with tags inside (pauses, colours, page breaks, ruby), and all non-dialogue text (item names and captions, menus,
signs' layouts, staff roll).
TODO: text with tags inside has to stay put because the tags can't follow the text yet.
'except_hints' also keeps these in place: every Gossip Stone message, every message a hint is written to (the hints
plugin's targets), the cucco and poe counts' lines (variables), and shop and price lines (variables).
'complete' shuffles the vanilla lines of the Gossip Stone and hint-target messages too. The hints are then written
over their own labels, so hints stay readable where they are (OoTR's complete mode moves hint text too).
The game's text is read through romtools.Romfs: ./original (vanilla copies), then the romfs named by the
REMAKE_ROMFS environment variable or the project's default (README).
"""
import os
import random
import sys
import re

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if os.path.join(HERE, "tools") not in sys.path:  # romtools, for the default below
    sys.path.append(os.path.join(HERE, "tools"))
DEFAULT_ROMFS = os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs()  # REMAKE_ROMFS: the app
CHOICE = re.compile(r"^\d{4}$")


def romfs():
    for p in (os.environ.get("REMAKE_ROMFS"), DEFAULT_ROMFS):
        if p and os.path.isdir(os.path.join(p, "Mals")):
            return p
    return None


def _eligible(m, label):
    import msbt
    segs = m.messages[m.labels[label]]
    texts = [i for i, s in enumerate(segs) if isinstance(s, str)]
    if not texts:
        return None
    if any(isinstance(s, msbt.Tag) and s.group == 2 for s in segs):
        return None
    if len(texts) != 1:  # tags between text runs
        return None
    text = segs[texts[0]]
    if not text.strip():
        return None
    return text


def shuffle_ops(mode, exempt, seed):
    """Text ops for text_shuffle mode ('except_hints' or 'complete'). exempt is the {(file, label)} set the hints plugin
    writes, kept in place for except_hints."""
    import msbt
    from romtools import Romfs
    root = romfs()
    if root is None:
        raise RuntimeError("text_shuffle needs the game's text: set REMAKE_ROMFS to the romfs folder")
    fs = Romfs(root, os.path.join(HERE, "original"))
    ops = []
    for lang in sorted(msbt.archives(root)):
        files = msbt.read_archive(fs, lang)
        groups = {"line": [], "choice": []}
        for name in sorted(files):
            if not name.startswith("EventFlowMsg/"):
                continue
            if mode == "except_hints" and name == "EventFlowMsg/GossipStone.msbt":
                continue
            m = msbt.Msbt(files[name])
            for label in m.labels:
                if mode == "except_hints" and (name, label) in exempt:
                    continue
                text = _eligible(m, label)
                if text is None:
                    continue
                groups["choice" if CHOICE.match(label) else "line"].append((name, label, text))
        rng = random.Random(f"{seed}:text_shuffle:{lang}")
        for group in groups.values():
            texts = [t for _, _, t in group]
            rng.shuffle(texts)
            for (name, label, old), new in zip(group, texts):
                if new != old:
                    ops.append({"lang": lang, "file": name, "label": label, "text": new})
    return ops
