"""Bombchu Bowling's prize announcements, changed to name the seed's prizes in every language (shops plugin).

Before a game the keeper announces the prize
(EventFlowMsg/Npc_Hylia_067_Shop_Child.msbt, MiniGame_BombchuBowling AfterWakeUp). Talk_37 is the bombchus (OoTR's
"Market Bombchu Bowling Bombchus"), Talk_06 / Talk_22 the bigger / biggest bomb bag ("First Prize"), Talk_05 the
Piece of Heart ("Second Prize"), and Talk_12 the red rupee after that (no OoTR location). A player who first
declines hears Talk_36 / Talk_31 / Talk_30 ("It's the call of the ... prize, isn't it?").

When a prize location holds another item, its announcement becomes, in each of the 16 languages the game ships:
the vanilla opening of Talk_06 in that language up to its pause tag ("This time, the prize for winning will be...",
"Zu gewinnen gibt es dieses Mal...", "今回の賞品は"..., every language has one), a new line, the item's own name from
that language's ActorMsg/PouchContent.msbt (<actor>_Name, highlighted the way vanilla highlights the prize), and
Talk_06's closing punctuation. The "call of the prize" line becomes that language's Talk_32 ("You wanna play after
all, do ya? I'm sure you can handle it!"), which names no prize. Where no name fits (a progressive item, whose tier
depends on what the player holds when he wins, or an item with no name message), the announcement becomes that
language's Talk_16 ("Keep your eyes on the prize!"). An ice trap is announced as the item it looks like, the way
OoTR shows it. Every language gets text from the game's own messages, nothing is English-only.
"""
import os
import re
import sys

FILE = "EventFlowMsg/Npc_Hylia_067_Shop_Child.msbt"
NAMES = "ActorMsg/PouchContent.msbt"
# OoTR location -> (OoTR's vanilla item there, announcement labels, "call of the prize" label)
PRIZES = {
    "Market Bombchu Bowling Bombchus": ("Bombchus (10)", ("Talk_37",), "Talk_36"),
    "Market Bombchu Bowling First Prize": ("Bomb Bag", ("Talk_06", "Talk_22"), "Talk_31"),
    "Market Bombchu Bowling Second Prize": ("Piece of Heart", ("Talk_05",), "Talk_30"),
}
TEMPLATE, NEUTRAL, NEUTRAL_AGAIN = "Talk_06", "Talk_16", "Talk_32"
PAUSE, ON, OFF = "{tag:5,1}", "{tag:0,3,0000}", "{tag:0,3,ffff}"
_cache = {}


def _texts():
    """{lang: (bowling Msbt, PouchContent Msbt)} for every language the game ships (Mals/<lang>.Product.110)."""
    if _cache:
        return _cache
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    from romtools import Romfs, sarc_files
    from msbt import Msbt
    import shops as shop_tools
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    fs = Romfs(shop_tools.DEFAULT_ROMFS, os.path.join(here, "original"))
    langs = sorted(f.split(".")[0] for f in os.listdir(os.path.join(shop_tools.DEFAULT_ROMFS, "Mals"))
                   if f.endswith(".Product.110.sarc.zs"))
    for lang in langs:
        files = sarc_files(fs.read(f"Mals/{lang}.Product.110.sarc.zs"))
        _cache[lang] = (Msbt(files[FILE]), Msbt(files[NAMES]))
    return _cache


def _actor(item, location, world):
    """The remake actor the seed gives for OoTR item `item` here, or None for a progressive item, since the tier is
    decided when the prize is won."""
    import generate
    if item == "Ice Trap":
        looks = getattr(world.get_location(location).item, "looks_like_item", None)
        item = getattr(looks, "name", None)
        if item is None or item == "Ice Trap":
            return None
    if item in generate.PROGRESSIVE:
        return None
    dg = sys.modules.get("parity.dungeons")
    if dg is not None and dg.dungeon_item(item) is not None:  # given through its credit entry, shown as this model
        return dg.MODEL[dg.dungeon_item(item)[0]]
    try:  # look up the actor in item_map.json here because the plugins' item_for hooks can register scenes
        return generate.remake_item(item)
    except generate.SeedError:
        return None


def _candidates(actor):
    """Name labels to try for an actor, its own first (a bundle's own name gives its count)."""
    import json
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    pouch = json.load(open(os.path.join(here, "data", "rando", "pouch_actors.json"), encoding="utf-8"))["actors"]
    names = [actor, actor.replace("TBox_", "Obj_", 1)]
    p = (pouch.get(actor) or [None])[0]
    if p:
        names.append(p)
    for a in list(names):
        if a.startswith("Item_Mask_"):
            names.append("Armor_Child_Mask_" + a[len("Item_Mask_"):])
        if a in ("Item_HoverBoot", "Item_HeavyBoot"):
            names.append("Armor_Adult_" + a[len("Item_"):])
        if a == "Item_GlassTruth":
            names.append("Armor_GlassTruth")
        if a.startswith("Item_Sword_") or a.startswith("Item_Shield_"):
            names.append("Weapon_" + a[len("Item_"):])
    return [f"{n}_Name" for n in dict.fromkeys(names)]


def _announce(bowling, pouch, labels):
    """The announcement markup for an item named by `labels` (first one the language has), else None."""
    label = next((l for l in labels if l in pouch), None)
    if label is None:
        return None
    name = pouch.markup(label).strip()
    template = bowling.markup(TEMPLATE)
    cut = template.find(PAUSE)
    if not name or cut < 0:
        return None
    punct = re.search(r"(\s?[!！.。]+)$", template)
    return f"{template[:cut + len(PAUSE)]}\n{ON}{name}{OFF}{punct.group(1) if punct else '!'}"


def text_ops(world):
    """make_patch "text" ops for every prize location holding something else, and notes."""
    ops, notes = [], []
    names = {loc.name for loc in world.get_locations()}
    for location, (vanilla, labels, again) in sorted(PRIZES.items()):
        if location not in names or world.get_location(location).item is None:
            continue
        item = world.get_location(location).item.name
        if item == vanilla:
            continue
        actor = _actor(item, location, world)
        cands = _candidates(actor) if actor else []
        named = 0
        for lang, (bowling, pouch) in sorted(_texts().items()):
            new = _announce(bowling, pouch, cands) if cands else None
            named += new is not None
            for label in labels:
                ops.append({"lang": lang, "file": FILE, "label": label,
                            "markup": new if new is not None else bowling.markup(NEUTRAL)})
            ops.append({"lang": lang, "file": FILE, "label": again, "markup": bowling.markup(NEUTRAL_AGAIN)})
        notes.append(f"{location}: {item}: announced by name in {named} of {len(_texts())} languages"
                     + ("" if named == len(_texts()) else " (the others: Talk_16, no prize named)"))
    return ops, notes
