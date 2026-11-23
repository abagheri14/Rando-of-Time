"""Count conditions (Rainbow Bridge, Light Arrow Cutscene, Door of Time stones) the way the game can check them.

OoTR counts items. has_stones / has_medallions / has_dungeon_rewards count the Spiritual Stones and Medallions held
(State.count_distinct), Gold Skulltula Tokens by number and hearts as Pieces of Heart // 4 + 3. The game can check
the same things. Each stone and medallion has a save flag IsGet.Item_Stone_* / IsGet.Item_Medal_* that's set when it
enters the pouch from any location, tokens are PouchData.Item_Token_Gold.StockNum (the Skulltula House reads it),
and hearts are PlayerStatus.MaxLife in quarter hearts (pieces add 1, containers 4, a new file starts at 12). So
count conditions are checked on the items, the way OoTR's logic counts them. Only the vanilla conditions follow
boss defeats (tools/rando/world_settings.py), because the vanilla story is driven by them.

Two forms:
- an expression (BoolExp, reverse Polish, polled by the bridge's level logic). It's an OR of AND terms, split in
  halves so "at least k of n" stays short (at most ~250 steps for 5 of 9).
- scene steps, a decision graph of save-data queries, for event hooks like the Light Arrow cutscene.
"""
from functools import lru_cache

from romtools import murmur3_32

STONES = ("IsGet.Item_Stone_Forest", "IsGet.Item_Stone_Fire", "IsGet.Item_Stone_Water")
MEDALLIONS = ("IsGet.Item_Medal_Forest", "IsGet.Item_Medal_Fire", "IsGet.Item_Medal_Water",
              "IsGet.Item_Medal_Shadow", "IsGet.Item_Medal_Spirit", "IsGet.Item_Medal_Light")
TOKENS = "PouchData.Item_Token_Gold.StockNum"
MAX_LIFE = "PlayerStatus.MaxLife"
TRIFORCE_COUNT = "Rando_TriforcePieceNum"  # Triforce Hunt's saved count (story plugin, _gaps_triforce.py)
# The Door of Time uses the stages set in each dungeon's exit scene after the boss.
STONE_STAGES = ("Get_StoneOfForest_IsCompleted_Exp", "Get_StoneOfFire_IsCompleted_Exp",
                "Get_StoneOfWater_IsCompleted_Exp")

# BoolExp opcodes
BOOL, ENUM_EQ, ENUM_CONST, AND, OR, NOT, EXP, ENUM_GT, INT_GT, INT_CONST = 0, 1, 2, 3, 4, 5, 10, 12, 19, 16
TRUE = [[BOOL, "Sequence_IsChildhood"], [BOOL, "Sequence_IsChildhood"], [NOT], [OR]]  # x or not x


def requirement(settings, prefix):
    """The requirement for bridge / lacs / ganon_bosskey (OoTR's shuffle_ganon_bosskey count conditions,
    ganon_bosskey_* counts): ('true',) | ('flags', [flag names], k) | ('int', name, minimum) | None (vanilla)."""
    cond = {"bridge": lambda: settings.bridge, "lacs": lambda: settings.lacs_condition,
            "ganon_bosskey": lambda: settings.shuffle_ganon_bosskey}[prefix]()
    if cond == "triforce":  # OoTR pins Ganon's boss key to 'triforce' in a Triforce Hunt: the pieces' goal
        return ("int", TRIFORCE_COUNT, int(settings.triforce_goal_per_world))
    if cond == "vanilla":
        return None
    if cond == "open":
        return ("true",)
    n = lambda key: int(getattr(settings, f"{prefix}_{key}"))  # noqa: E731
    if cond == "stones":
        return ("flags", list(STONES), n("stones"))
    if cond == "medallions":
        return ("flags", list(MEDALLIONS), n("medallions"))
    if cond == "dungeons":
        return ("flags", list(STONES + MEDALLIONS), n("rewards"))
    if cond == "tokens":
        return ("int", TOKENS, n("tokens"))
    if cond == "hearts":
        return ("int", MAX_LIFE, 4 * n("hearts"))
    raise ValueError(f"{prefix} condition {cond!r}")


def describe(req):
    if req is None:
        return "vanilla"
    if req[0] == "true":
        return "always"
    if req[0] == "flags":
        return f"{req[2]} of {', '.join(f.split('.')[-1] for f in req[1])}"
    return f"{req[1]} >= {req[2]}"


# Expressions
@lru_cache(maxsize=None)
def _atleast(flags, k):
    """RPN steps for "at least k of flags" (k >= 1, k <= len(flags))."""
    n = len(flags)
    if k == n:
        out = [[BOOL, flags[0]]]
        for f in flags[1:]:
            out += [[BOOL, f], [AND]]
        return out
    if k == 1:
        out = [[BOOL, flags[0]]]
        for f in flags[1:]:
            out += [[BOOL, f], [OR]]
        return out
    a, b = flags[:n // 2], flags[n // 2:]
    terms = []
    for j in range(max(0, k - len(b)), min(len(a), k) + 1):
        left = _atleast(a, j) if j else None
        right = _atleast(b, k - j) if k - j else None
        if left and right:
            terms.append(left + right + [[AND]])
        else:
            terms.append(left or right)
    out = terms[0]
    for t in terms[1:]:
        out = out + t + [[OR]]
    return out


def expression(req):
    """BoolExp steps (list of [opcode, value]) true when the requirement holds."""
    if req[0] == "true":
        return [list(x) for x in TRUE]
    if req[0] == "flags":
        flags, k = tuple(req[1]), req[2]
        if k <= 0:
            return [list(x) for x in TRUE]
        return [list(x) for x in _atleast(flags, min(k, len(flags)))]
    _, name, minimum = req
    if minimum <= 0:
        return [list(x) for x in TRUE]
    return [[INT_GT, name], [INT_CONST, minimum - 1]]


def enum_after(enum_name, step):
    """BoolExp steps that are true when the challenge enum is strictly after `step`."""
    return [[ENUM_GT, enum_name], [ENUM_CONST, murmur3_32(step)]]


def either(a, b):
    return a + b + [[OR]]


# Scene steps
def _bool_query(flag, yes, no):
    if flag.endswith("_Exp"):
        return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBoolExp", "params": {"GameDataName": flag},
                "cases": {0: yes, 1: no}}
    return {"actor": "GameDataActor", "query": "EventQueryIsGameDataBool",
            "params": {"GameDataName": flag, "Index": -1}, "cases": {0: yes, 1: no}}


def scene_nodes(req, prefix, yes, no):
    """({label: node}, start label) of scene queries that go to `yes` when the requirement holds, else `no`.
    Targets are labels, "@EventName" or None (end). Int queries answer 0 below, 1 equal, 2 above the value."""
    if req[0] == "true":
        return {}, yes
    if req[0] == "int":
        _, name, minimum = req
        node = {"actor": "GameDataActor", "query": "EventQueryIsGameDataInt",
                "params": {"GameDataName": name, "Value": int(minimum), "Index": -1},
                "cases": {0: no, 1: yes, 2: yes}}
        return {f"{prefix}i": node}, f"{prefix}i"
    flags, k = list(req[1]), req[2]
    n = len(flags)
    nodes = {}

    def label(i, c):
        if c >= k:
            return yes
        if c + (n - i) < k:
            return no
        lab = f"{prefix}{i}_{c}"
        if lab not in nodes:
            nodes[lab] = None
            nodes[lab] = _bool_query(flags[i], label(i + 1, c + 1), label(i + 1, c))
        return lab
    start = label(0, 0)
    return nodes, start
