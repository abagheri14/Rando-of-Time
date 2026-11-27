"""Gossip Stone text for the remake. Each OoTR stone's hint goes on the label of the remake stone standing where OoTR
put it (data/rando/hints_stones.json, _hints_stones.py), with the remake's place and item names, its box size (3
lines at the stones' small-font width) and OoTR's colours.

A stone shows the GossipStone.msbt message named like its placement, and those names don't follow the stones' areas
(GOSSIP_LOST_WOOD_01 stands in a Zora's River grotto). So we replace generate.py's pairing by area and name order
here. Each stone gets one op per language: "text" (plain, what make_patch.py writes today, keeping the message's
leading tags) and "markup" (colours as the remake's highlight, a new box every 3 lines).
"""
from . import _hints_stones as S
from . import _hints_text as T

GOSSIP_FILE = "EventFlowMsg/GossipStone.msbt"


class PairingError(RuntimeError):
    pass


def base_ops(gossip_stones):
    """One plain op per OoTR stone, on its paired label (generate.gossip_text_ops' shape)."""
    pairing, absent = S.labels(), set(S.absent_names())
    ops, seen = [], {}
    for name in sorted(gossip_stones):
        if name in absent:
            raise PairingError(f"OoTR put a hint on {name}, which the remake doesn't have "
                               f"(data/rando/hints_stones.json 'absent')")
        label = pairing.get(name)
        if label is None:
            raise PairingError(f"no remake Gossip Stone paired with OoTR's {name} (data/rando/hints_stones.json)")
        if label in seen:
            raise PairingError(f"{name} and {seen[label]} both paired with {label}")
        seen[label] = name
        ops.append({"lang": "*", "file": GOSSIP_FILE, "label": label, "text": gossip_stones[name]["text"],
                    "note": name})
    return ops


def gossip_ops(gossip_stones, orig_gossip_text_ops=None):
    """The Gossip Stone ops. orig_gossip_text_ops (generate.py's) isn't used for the pairing any more, it's only kept in
    the signature for callers of the old form."""
    box = T.targets()["box"]
    ops = []
    for op in base_ops(gossip_stones):
        stone = gossip_stones.get(op["note"], {})
        raw = stone.get("text") or ""
        control = T.remake_names(T.mark(raw, stone.get("colors")))
        try:
            langs = T.vanilla(op["file"], op["label"])
        except KeyError:
            ops.append(dict(op, text=T.plain_pages(T.wrap(T.tokens(control), 48, 99))[0]))
            continue
        for lang, markup in sorted(langs.items()):
            pages = T.wrap(T.tokens(control, T.names(lang)["player"]), box["width_small"], box["lines"])
            full, text, _ = T.build(markup, pages, width=box["width_small"])
            ops.append({"lang": lang, "file": op["file"], "label": op["label"], "text": text, "markup": full,
                        "note": op["note"]})
    return ops
