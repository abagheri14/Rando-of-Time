"""NPC rewards the core can't take as plain scene locations, for the songs/trade plugin (songs_trade.py).

Each function adds patch-plan ops to an Ops (_songs_trade_ops.py) for one OoTR location. The step data comes from
data/rando/songs_trade_data.json, which _songs_trade_build.py builds from the game files, checking every step named
here.

- GC Rolling Goron as Child (always shuffled by OoTR): the goron picks the next bomb bag by what's in the pouch and
  gives nothing if you have no bag or the Large bag. Now when you stop him in the perfect spot (Talk_03) the flow
  goes straight to the hand-over (Talk_29) and the gift, whatever the pouch holds. Both vanilla gift steps get the
  item (one can't be reached anymore) and the goron's own once-only flag stays in charge.
- Graveyard Dampe Gravedigging Tour (always): Dampe's tough-ground dig gives the item with his own give step
  (Event628). The heart piece he raises out of the hole is skipped unless a heart piece is given there. His flag
  (GraveYard_DiggingHoleTour_Drop_HeartPiece) keeps it once only.
- GC Medigoron (shuffle_expensive_merchants): he sells his item once, whatever sword you hold, with a save flag set
  right after his give step. After that he only says goodbye.
- Kak Granny Buy Blue Potion (shuffle_expensive_merchants): sold once for 100 rupees, no empty bottle needed
  (songs_trade._granny_ops), and offered from the first talk. Her vanilla sale waits until the Odd Potion has been
  shown to Fado, and OoTR's rule doesn't ask for that, so the game can't either.
"""
from . import _songs_trade_ops as ops

ROLLING = "GC Rolling Goron as Child"
DAMPE_DIG = "Graveyard Dampe Gravedigging Tour"
MEDIGORON = "GC Medigoron"


def _reward(o, rid, target, name, item, ice_spec):
    if target.get("ice_trap"):
        o.rewards[rid] = dict(ice_spec(rid, name), note=f"{name}: {item}")
    else:
        o.rewards[rid] = ops.reward_spec(target, f"{name}: {item}", [rid])


def rolling_goron_ops(o, data, item, target, ice_spec):
    d = data["rolling_goron"]
    for rid in d["reward_ids"]:
        _reward(o, rid, target, ROLLING, item, ice_spec)
    # the stop talk (Talk_03) leads to the hand-over talk (Talk_29) and its gift whatever bag the player holds
    o.events.append({"file": d["file"], "flowchart": d["file"], "event": d["stop"]["event"],
                     "next": d["handover"]["event"]})
    o.notes.append(f"{ROLLING}: {item} (given after any stop in the perfect spot, whatever bomb bag is held)")


def dampe_dig_ops(o, data, item, target, ice_spec):
    d = data["dampe_dig"]
    _reward(o, d["reward_id"], target, DAMPE_DIG, item, ice_spec)
    if item != "Piece of Heart":  # no heart piece rises out of the hole for another item
        o.events.append({"file": d["file"], "flowchart": d["file"], "event": d["demo"]["event"],
                         "next": d["raise"]["next"]})
    o.notes.append(f"{DAMPE_DIG}: {item}")


def medigoron_ops(o, data, flag, item, target, ice_spec):
    d = data["medigoron"]
    f = d["file"]
    if target.get("ice_trap"):  # the freeze replaces the sale: given free, once
        n = {"q": ops.flag_query(flag, "sold", "give"),
             "sold": {"copy": d["talk_03"]["event"],
                      "params_over": {"MessageId": "EventFlowMsg/Npc_Goron_Medigoron_Adult:Talk_04"}, "next": None},
             "give": o.give(target, "set"), "set": ops.flag_set(flag, None)}
        o.replace(f, f, d["first_check"], "RandoST_Medigoron", n, "q")
        o.notes.append(f"{MEDIGORON}: {item} (free, once)")
        return
    # If he already sold it he goes to his goodbye (Talk_04). Otherwise it's straight to the sale (price, rupee display,
    # offer, then SimpleShopRoot), which skips the "you already have a sword" talks.
    n = {"q": ops.flag_query(flag, "sold", ops.at(d["price"]["event"])),
         "sold": {"copy": d["talk_03"]["event"],
                  "params_over": {"MessageId": "EventFlowMsg/Npc_Goron_Medigoron_Adult:Talk_04"}, "next": None}}
    o.replace(f, f, d["first_check"], "RandoST_Medigoron", n, "q")
    _reward(o, d["reward_id"], target, MEDIGORON, item, ice_spec)
    # No pouch check on Medigoron's SimpleShop path, since we don't know how it handles a non-sword item. The flag gets
    # set as soon as he hands the item over, and the player's broken Giant's Knife is left alone.
    s = "SimpleShop"
    o.events.append({"file": s, "flowchart": s, "event": d["shop_rupees"]["event"], "case": ops.YES,
                     "next": d["shop_pay"]["event"]})
    after = d["shop_after_give"]
    o.replace(s, s, after, "RandoST_MedigoronSold", {"set": ops.flag_set(flag, ops.at(after["event"]))}, "set")
    o.events.append({"file": s, "flowchart": s, "event": after["event"], "next": d["shop_save"]["event"]})
    o.notes.append(f"{MEDIGORON}: {item} (once, 200 rupees)")


def granny_gate_ops(o, data, flag):
    """Granny offers the shuffled item from the first talk (her vanilla gate waits for Step05_01)."""
    d = data["granny"]
    f = d["file"]
    n = {"q": ops.flag_query(flag, ops.at(d["gate"]["event"]), ops.at(d["buy"]["event"]))}
    o.replace(f, f, d["gate"], "RandoST_GrannyGate", n, "q")
