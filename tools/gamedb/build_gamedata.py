"""GameData section of the game-logic index. It has every save-data row of GameDataList (named where we can find
the name), the quests (RSDB Challenge, with their steps in order), the per-area pot/grass resets (GmdReset) and when
each reset type fires (the Sequence modules that call SeqExecuteResetGameData).

GameDataList keys its rows by murmur3_32 of the flag name and nothing else, so the names come from a dictionary we
build here:
  1. Every identifier-like string in the game files that name flags (event flows, AI/Logic/Sequence graphs, levels,
     components, RSDB tables, game parameters, the actor packs' AI and parameter files), plus the executable image
     Longshot keeps next to the romfs (image.bin, when it's there), with their '.'/'/' sub-paths.
  2. Struct trees. A Struct row lists (murmur3(member), murmur3("<struct>.<member>")), so a named struct names the
     rows of its members (both hashes must match) and a named member row names its struct.
  3. Generated names, each checked by hash, and struct members by the member hash too. These are placement hashes
     as decimal members (IsTreasureBoxOpen.<hash>, IsGoldSkullDead.IsGoldSkullDead_<hash>), the autogen flags of the
     logic modules (AutogenGameDataLogicNode.<AiGroup hash><node __GUIDHash>), quest names (Step_<quest>,
     <quest>_IsAfter_<step>_Exp ...), the executable's printf formats filled with base names, numbered siblings of
     every name found (X_01 -> X_00..X_99), family crossing (HaveDefeatedEnemy_X + DreamWorldPlate_Y ->
     DreamWorldPlate_X), and SEED_NAMES (names an offline search found, and only the ones whose hash matches get
     used). A generated name only names a row of the kind its pattern came from, and a dotted name only names a
     struct member. Otherwise a single 32-bit match over millions of guesses would let collisions in.

ResetTypeValue is a bitmask where bit n means reset to DefaultValue by SeqExecuteResetGameData(ResetType=n). Summary
"reset_bits" lists which Sequence modules call each n. SaveFileIndex is the index into MetaData.SaveDirectory, and -1
means not saved.

Fields beyond SCHEMA.md. Per key there's "named_by" (how we found a name that wasn't read from a file or a struct
tree, one of quest, family, sibling, format, autogen, seed, guess), "parent"/"member" (for an unnamed struct member,
its struct's key and the member name or #hash), "members" (Struct), "bytes" (Binary*, the DefaultValue byte size),
"orig_size" (arrays) and "exp_problems"/"rpn" (a BoolExp that didn't decode). Formula leaves beyond SCHEMA.md are
enum:<name><op><value> (a non-quest enum compare) and flag:<BoolArray>[i], and int ops are =, <, >. Per record
there's b64_count, b64_reset {reset value other than 24: [hashes]}, b64_extra {hash: ExtraByte}, unnamed_by_type,
rows_by_type, named_by_type, named_how, save_files, metadata and names_build (timings, sources). The names this
builder resolved also go to cache/gamedb/vanilla/gamedata_names.json ({"rows": {hash: name}, "members": {hash: member
name}, "how": ...}).
"""
import bisect
import collections
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SECTION = "gamedata"
VERSION = 1
PARALLEL = False

GAMEDATA = "GameData/GameDataList.Product.110.byml.zs"
CHALLENGE = "RSDB/Challenge.Product.111.rstbl.byml.zs"
GMDRESET = "Banc/BancBasedResource/GmdReset.byml.zs"
STATIC_AREA = "Banc/BancBasedResource/StaticGameDataArea.byml.zs"
FILES = (GAMEDATA, CHALLENGE, GMDRESET, STATIC_AREA)

TOKEN = re.compile(rb"[A-Za-z0-9_.\-/]{3,}")
FMT = re.compile(rb"[A-Za-z0-9_.]*%(?:llu|lld|lu|ld|u|d|s|0\dd|0\du)[A-Za-z0-9_.%]*")
NAME_OK = re.compile(r"^[A-Za-z0-9_\-][A-Za-z0-9_.\-]*$")

# Names an offline NumPy search over word combinations found. They're kept here so nobody has to run that
# search again, and the build still needs the row hash to match.
SEED_NAMES = (
    "DungeonRoomStep",            # struct: DungeonRoomStep.<Area>.DungeonRoom%03d.{ClearRoom, ClearAutoSave, Step}
    "ClearRoom", "ClearAutoSave",
    "NpcFairyColor",              # struct of Enum Color0.. per Kokiri NPC
    "AmiiboData", "TouchLog",
    "IsGoBackHome",               # struct of Bools per NPC placement hash
    "WellAreaEvent", "BancChangeArrive",
    "ActionGuide_IsNew",          # twin of ActionGuide_IsEnd (members: the TutorialType enum values)
    "ChallengeMenu_State",        # struct of Enum None/New/Update per quest
    "MilestoneCount",             # struct of Int64 PlayTime, RupeeTotal ... (the executable's "Milestone.Add.%s")
    "IsGameClear",                # Bool read by the 134 UndefeatedEnemyAfterGameClear_<enemy> expressions
)
# Less certain ones. Each is a single 32-bit match from a search over <known name head>_<word(s)>. That search
# also turned up collisions, which you can spot by the wrong type or a meaningless name, so these are only kept when
# the type matches and there's a family of attested siblings. Rows they name get "named_by": "guess".
SEED_GUESSES = (
    "InsideJabuJabuBelly_TentacleRed",                    # saved, default true, as InsideJabuJabuBelly_TentacleBlue
    "InsideTheDekuTree_Dungeon_EnemyScrubDekuDestroy",    # as ..._001.._003
    "GerudoTrainingGround_Dungeon_Room06_Key",
    "NaviHint_Field_Attention", "NaviHint_Field_Talked", "NaviHint_Dungeon_Talked",
    "NaviHelp_Dungeon_Talked",                            # as NaviHelp_Dungeon_Read
)

# ResetType n (SeqExecuteResetGameData) -> when the game calls it, read from the Sequence modules that call it.
# Summary "reset_types" also lists the callers found in the files, so it shows if a patch moves them.
RESET_CALLS = {
    0: "every area (Banc) change (ChangeBanc), and when a save is loaded (OnLoadGameSaveData)",
    1: "day change (ResetGameDataOnDayChange, run from MainUpdate and Event)",
    2: "options reset to defaults (ConfirmationResetOption)",
    3: "new game (NormalTitle), and before a save is loaded (OnLoadGameSaveData: saved rows then get the save's "
       "values)",
    4: "before the title screen and before a game starts (BeforeInitializeCommon, via BeforeTitle / "
       "BeforeInitializeGameStart)",
    5: "new game only (NormalTitle; not on load: saved rows keep the save's values, unsaved ones keep their value "
       "for the session)",
    6: "not called by a Sequence module: set only on per-object rows of respawning things (pots, grass, rocks, "
       "ice pillars ...: Bool64bitKey ResetTypeValue 88), each with an ExtraByte whose low 7 bits are its area's "
       "index (bit 7 on 158 rows: unknown); likely reset per area by the engine, and the level's "
       "SupplyItemResetSystemActor resets listed subsets (GmdReset: SrcHash actor -> DstHash rows)",
    7: "not called by a Sequence module: only the boss retry counters have it (DungeonInfo.<dungeon>.BossRetryNum, "
       "SpiritTemple_Boss_*RetryCount: 160 = 128+32); likely reset by the boss-retry code",
    8: "every area change except a same-area item warp (ChangeBanc unless Sequence_IsSameBancItemWarp), and when a "
       "save is loaded",
}


def files(root):
    return [f for f in FILES if os.path.isfile(os.path.join(root, f))]


def index_file(fs, rel):
    if rel == GAMEDATA:
        return index_gamedata(fs, rel)
    if rel == CHALLENGE:
        return index_challenges(fs, rel)
    if rel == GMDRESET:
        return index_gmdreset(fs, rel)
    return {"kind": "resource", "data": common.jsonable(common.read_byml(fs, rel))}


# Murmur3 over bytes, a faster loop than the one in romtools
def mm3(data):
    n = len(data)
    nb = n >> 2
    h = 0
    if nb:
        for k in struct.unpack_from("<%dI" % nb, data):
            k = (k * 0xCC9E2D51) & 0xFFFFFFFF
            k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
            k = (k * 0x1B873593) & 0xFFFFFFFF
            h ^= k
            h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
            h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    r = n & 3
    if r:
        k = int.from_bytes(data[n - r:], "little")
        k = (k * 0xCC9E2D51) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * 0x1B873593) & 0xFFFFFFFF
        h ^= k
    h ^= n
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def H(s):
    return mm3(s.encode() if isinstance(s, str) else s)


# The name dictionary
def _walk(fs, sub, rx):
    """Rel paths of the files under sub, in the romfs and any overlay. A patch's new files count too."""
    out = set()
    for top in [fs.root] + list(getattr(fs, "overlays", ()) or ()):
        for dp, dn, fn in os.walk(os.path.join(top, sub)):
            for f in fn:
                if rx.search(f):
                    out.add(os.path.relpath(os.path.join(dp, f), top).replace(os.sep, "/"))
    return sorted(out)


HARVEST = (("Event/EventFlow", r"\.bfevfl(\.zs)?$"), ("Logic", r"\.ainb$"), ("Sequence", r"\.ainb$"),
           ("AI", r"\.ainb$"), ("Banc", r"\.byml(\.zs)?$"), ("AoC1/Banc", r"\.byml(\.zs)?$"),
           ("Component", r"\.bgyml$"), ("RSDB", r"\.byml(\.zs)?$"), ("GameParameter", r""), ("Game", r""),
           ("System", r"\.(byml|bgyml)(\.zs)?$"), ("WorldMgr", r""), ("AISchedule", r""))


class Harvest:
    """What the game files say that can name a GameData row: tokens, placement hashes, autogen keys, format strings."""

    def __init__(self, fs):
        self.fs = fs
        self.tokens = set()
        self.formats = set()
        self.u64 = set()
        self.ai_groups = []            # (AiGroup or reference hash, logic rel)
        self.autogen = {}              # logic rel -> [__GUIDHash of OperateGameDataAllocAutogenGameData nodes]
        self.sources = collections.Counter()
        self.exe = None

    def scan(self, data, tag):
        s = TOKEN.findall(data)
        self.sources[tag] += 1
        self.tokens.update(s)

    def run(self):
        fs = self.fs
        for sub, rx in HARVEST:
            r = re.compile(rx)
            for rel in _walk(fs, sub, r):
                try:
                    d = common.read_any(fs, rel)
                except Exception:  # noqa: BLE001 - an unreadable file names nothing
                    continue
                self.scan(d, sub)
                if rel.endswith(".bcett.byml.zs"):
                    self._level(rel)
                elif rel.startswith("Logic/") and b"OperateGameDataAllocAutogenGameData" in d:
                    self._autogen(rel, d)
        for rel in _walk(fs, "Pack", re.compile(r"\.pack\.zs$")):
            try:
                inner = common.pack(fs, rel)
            except Exception:  # noqa: BLE001
                continue
            for k, d in inner.items():
                if k.endswith((".ainb", ".bgyml", ".byml")):
                    self.scan(d, "Pack")
        exe = os.path.join(os.path.dirname(os.path.abspath(fs.root)), "image.bin")
        if os.path.isfile(exe):
            d = open(exe, "rb").read()
            self.scan(d, "image.bin")
            self.formats.update(FMT.findall(d))
            self.exe = exe
        return self

    def _level(self, rel):
        try:
            root = common.read_byml(self.fs, rel)
        except Exception:  # noqa: BLE001
            return
        stack = [root]
        while stack:
            v = stack.pop()
            if isinstance(v, dict):
                stack.extend(v.values())
            elif isinstance(v, list):
                stack.extend(v)
            elif isinstance(v, int) and not isinstance(v, bool) and v > 0xFFFFFFFF:
                self.u64.add(int(v))
        for g in root.get("AiGroups") or []:
            if g.get("Logic"):
                self.ai_groups.append((int(g["Hash"]), _logic_rel(g["Logic"])))
            for ref in g.get("References") or []:
                if ref.get("Logic") and ref.get("Reference"):
                    self.ai_groups.append((int(ref["Reference"]), _logic_rel(ref["Logic"])))

    def _autogen(self, rel, d):
        try:
            import ainb
            a = ainb.Ainb(d)
        except Exception:  # noqa: BLE001
            return
        out = []
        for n in a.nodes:
            if n["name"] == "OperateGameDataAllocAutogenGameData":
                for e in n["properties"]["int"]:
                    if e["name"] == "__GUIDHash":
                        out.append(int(e["value"]))
        if out:
            self.autogen[rel] = out


def _logic_rel(path):
    """'Logic/Module/X/X_3284.logic.module.ain' (a level's AiGroup) -> 'Logic/X_3284.logic.module.ainb'."""
    b = path.rsplit("/", 1)[-1]
    if b.endswith(".ain"):
        b += "b"
    return "Logic/" + b


class Names:
    """Row hash -> name, member hash -> member name, resolved against one GameDataList."""

    def __init__(self, data):
        self.rows = {}                 # hash -> (type, row)
        for t, rs in data.items():
            if t == "Bool64bitKey":
                continue
            for r in rs:
                self.rows.setdefault(int(r["Hash"]), (t, r))
        self.structs = {int(r["Hash"]): [(int(m["Hash"]), int(m["Value"])) for m in r["DefaultValue"]]
                        for r in data.get("Struct", [])}
        self.parent = {}               # member row hash -> (struct hash, member hash)
        for s, mems in self.structs.items():
            for mh, vh in mems:
                self.parent[vh] = (s, mh)
        self.member_hashes = {mh for mems in self.structs.values() for mh, vh in mems}
        self.name = {}                 # row hash -> name
        self.how = {}                  # row hash -> how it was found
        self.mem = {}                  # member hash -> member name (confirmed by a full row name)
        self.mem_cand = {}             # member hash -> a string with that hash (unconfirmed)
        self.new = 0

    # Offering candidates
    def offer(self, s, how, types=None):
        """Offers a candidate name (bytes or str) and returns True if it named a row. `types` are the row types a
        generated name may name, so a guess from a family of names shouldn't name a row of another kind by a hash
        collision."""
        b = s if isinstance(s, bytes) else s.encode()
        h = mm3(b)
        hit = False
        if h in self.rows and h not in self.name and (types is None or self.rows[h][0] in types):
            hit = self._row(h, b.decode("utf-8", "replace"), how)
        if h in self.member_hashes and h not in self.mem:
            c = self.mem_cand.setdefault(h, [])
            if len(c) < 8:
                c.append(b.decode("utf-8", "replace"))
        return hit

    def offer_member(self, s):
        """A candidate member name only. propagate() verifies it against its struct's name."""
        b = s if isinstance(s, bytes) else s.encode()
        h = mm3(b)
        if h in self.member_hashes and h not in self.mem:
            c = self.mem_cand.setdefault(h, [])
            if len(c) < 8:
                c.append(b.decode("utf-8", "replace"))

    def _row(self, h, name, how):
        if not NAME_OK.match(name):
            return False
        par = self.parent.get(h)
        if par:  # a struct member is "<struct name>.<member>" and both hashes must agree
            s, mh = par
            if "." not in name:
                return False
            pre, m = name.rsplit(".", 1)
            if H(m) != mh:
                return False
            if s in self.name:
                if self.name[s] != pre:
                    return False
            elif H(pre) == s:
                self._set(s, pre, "struct")
            else:
                return False
            self.mem[mh] = m
        elif "." in name and how != "file":
            return False  # a dotted name is a struct path, so a generated one on a plain row is a hash collision
        self._set(h, name, how)
        return True

    def _set(self, h, name, how):
        if h not in self.name:
            self.name[h] = name
            self.how[h] = how
            self.new += 1
            if h in self.parent and "." in name:
                self.mem.setdefault(self.parent[h][1], name.rsplit(".", 1)[1])

    def propagate(self):
        """Walks the struct trees until nothing changes. A named struct names the rows of its known members and
        their sub-structs."""
        while True:
            n = self.new
            for s, mems in self.structs.items():
                sn = self.name.get(s)
                if sn is None:
                    continue
                for mh, vh in mems:
                    if vh in self.name:
                        continue
                    for m in [self.mem.get(mh)] + self.mem_cand.get(mh, []):
                        if m is not None and H(f"{sn}.{m}") == vh:
                            self._set(vh, f"{sn}.{m}", "struct")
                            self.mem[mh] = m
                            break
            if self.new == n:
                return

    # Views
    def key(self, h):
        return self.name.get(h, f"#{h}")


def build_names(fs, root, challenges):
    """Resolves the row names of root["Data"]. Returns (Names, Harvest, stats)."""
    t0 = time.time()
    hv = Harvest(fs).run()
    nm = Names(root["Data"])
    stages = {"harvest": round(time.time() - t0, 1)}
    found = {}

    def stage(label, fn):
        t, n = time.time(), nm.new
        fn()
        nm.propagate()
        stages[label] = round(time.time() - t, 1)
        found[label] = nm.new - n

    # 1. tokens and their '.' / '/' sub-paths; enum values; the seed list
    cands = set()

    def tokens():
        for t in hv.tokens:
            cands.add(t)
            for sep in (b"/", b"."):
                if sep in t:
                    parts = t.split(sep)
                    for i in range(len(parts)):
                        for j in range(i + 1, len(parts) + 1):
                            if j - i < len(parts):
                                cands.add(sep.join(parts[i:j]))
        cands.discard(b"")
        for c in cands:
            nm.offer(c, "file")
        for t in ("Enum", "EnumArray"):
            for r in root["Data"].get(t, []):
                for v in r.get("RawValues") or []:
                    nm.offer(v, "file")
        for x in SEED_NAMES:
            nm.offer(x, "seed")
        for x in SEED_GUESSES:
            nm.offer(x, "guess", ("Bool",))
    stage("tokens", tokens)

    # 2. placement hashes as decimal members, and <prefix><hash> for the executable's "IsGoldSkullDead_%llu"
    u64 = hv.u64 | {int(r["Hash"]) for r in root["Data"].get("Bool64bitKey", [])}
    try:
        gmd = common.read_byml(fs, GMDRESET)
    except Exception:  # noqa: BLE001
        gmd = {}
    for area, d in (gmd or {}).items():
        for src, v in d.items():
            u64.add(int(src))
            u64.update(int(x) for x in v.get("DstHash") or [])
    dec = [str(u) for u in sorted(u64)]

    def placements():
        for x in dec:
            nm.offer_member(x)
        for f in sorted(hv.formats):
            m = re.match(rb"^([A-Z][A-Za-z0-9_]+)%(?:llu|lu)$", f)
            if m:
                pre = m.group(1).decode()
                for x in dec:
                    nm.offer_member(pre + x)
    stage("placements", placements)

    # 3. autogen flags of logic modules: AutogenGameDataLogicNode.<AiGroup hash><__GUIDHash, signed>
    def autogen():
        for gh, rel in hv.ai_groups:
            for g in hv.autogen.get(rel, ()):
                nm.offer(f"AutogenGameDataLogicNode.{gh}{g}", "autogen")
    stage("autogen", autogen)

    # 4. quests: Step_<quest>, <quest>_IsAfter_<step>_Exp ...
    def quests():
        for c, steps in challenges.items():
            for x in _quest_names(c, steps):
                nm.offer(x, "quest")
    stage("quests", quests)

    # 5. base names (actor packs, quests, steps, the last part of every path) as rows and as members, and the
    #    executable's printf formats whose literal part starts a name already found, filled with them
    base = set()
    pack_dir = os.path.join(fs.root, "Pack", "Actor")
    if os.path.isdir(pack_dir):
        base.update(f.split(".")[0] for f in os.listdir(pack_dir))
    for c, st in challenges.items():
        base.add(c)
        base.update(st)
    for t in hv.tokens:
        if b"/" in t:
            x = t.rsplit(b"/", 1)[1].split(b".")[0]
            if len(x) >= 3:
                base.add(x.decode("ascii", "replace"))
    base = sorted(base)

    def formats():
        for x in base:
            nm.offer(x, "base")
        known = sorted(set(nm.name.values()) | set(nm.mem.values()))
        for f in sorted(hv.formats):
            fmt = f.decode("ascii", "replace")
            if fmt.count("%") != 1 or len(fmt) > 64 or not fmt[:1].isupper():
                continue
            m = re.search(r"%(0\d)?(?:s|d|u|ld|lu|lld|llu)", fmt)
            if not m or m.start() < 3:
                continue
            lit = fmt[:m.start()]
            i = bisect.bisect_left(known, lit)
            if i >= len(known) or not known[i].startswith(lit):
                continue
            pre, post = fmt[:m.start()], fmt[m.end():]
            if m.group().endswith("s"):
                fills = base
            else:
                w = m.group(1)
                fills = [f"{k:{w}d}" if w else str(k) for k in range(1000)]
            for x in fills:
                nm.offer(pre + x + post, "format")
    stage("formats", formats)

    # 6. numbered siblings (X_03 -> X_00..X_99) and family crossing (A_x, B_x, B_y -> A_y), until stable
    seen = set()

    def siblings_and_families():
        for _ in range(3):
            n0 = nm.new
            flat_types = {}
            for h, n in nm.name.items():
                if h not in nm.parent:
                    flat_types[n] = nm.rows[h][0]
            for n, t in list(flat_types.items()):
                for v in _siblings(n):
                    if v not in seen:
                        seen.add(v)
                        nm.offer(v, "sibling", (t,))
            for m in list(nm.mem.values()):
                for v in _siblings(m):
                    if v not in seen:
                        seen.add(v)
                        nm.offer_member(v)
            for cand, types in _crossings(flat_types):
                if cand not in seen:
                    seen.add(cand)
                    nm.offer(cand, "family", types)
            for s, mems in nm.structs.items():
                if s not in nm.name or all(vh in nm.name for mh, vh in mems):
                    continue
                fam = {nm.mem[mh]: "m" for mh, vh in mems if mh in nm.mem}
                for cand, _t in _crossings(fam, max_k=4, min_len=3):
                    if ("m", cand) not in seen:
                        seen.add(("m", cand))
                        nm.offer_member(cand)
            nm.propagate()
            if nm.new == n0:
                break
    stage("siblings_families", siblings_and_families)

    stats = {"seconds": round(time.time() - t0, 1), "stage_seconds": stages, "stage_found": found,
             "tokens": len(hv.tokens), "candidates": len(cands), "placement_hashes": len(u64),
             "formats": len(hv.formats), "autogen_modules": len(hv.autogen), "exe_image": hv.exe,
             "sources": dict(hv.sources)}
    return nm, hv, stats


def _crossings(names, max_k=3, min_shared=2, max_family=400, min_len=4):
    """Names that a family of names suggests. Each name is split as <head>_<rest> at its first 1..max_k '_'.
    Two heads that share at least min_shared rests (min_len+ characters, not all digits) lend each other their other
    rests. names is {name: type}. Yields (candidate, (types of the head's family))."""
    fam = collections.defaultdict(set)
    ftypes = collections.defaultdict(set)
    for n, t in names.items():
        seg = n.split("_")
        for k in range(1, min(max_k, len(seg) - 1) + 1):
            head = "_".join(seg[:k])
            fam[head].add("_".join(seg[k:]))
            ftypes[head].add(t)
    inv = collections.defaultdict(list)
    for head, rests in fam.items():
        if len(rests) > max_family:
            continue
        for r in rests:
            if len(r) >= min_len and not r.isdigit():
                inv[r].append(head)
    pairs = collections.Counter()
    for r, heads in inv.items():
        if len(heads) > 60:
            continue
        for i in range(len(heads)):
            for j in range(i + 1, len(heads)):
                pairs[(heads[i], heads[j])] += 1
    for (a, b), n in pairs.items():
        if n < min_shared:
            continue
        for x, y in ((a, b), (b, a)):
            types = tuple(ftypes[x])
            for r in fam[y] - fam[x]:
                yield f"{x}_{r}", types


def _quest_names(c, steps):
    """Names a quest's rows and expressions may have (each is checked by hash)."""
    out = [f"Step_{c}", c, f"{c}_IsCompleted_Exp", f"{c}_IsNotCompleted_Exp", f"{c}_IsCompleted",
           f"{c}_IsReady_Exp", f"{c}_IsNotReady_Exp", f"{c}_IsStarted_Exp", f"{c}_IsPlaying_Exp",
           f"{c}_IsNotStarted_Exp", f"{c}_IsActive_Exp", f"{c}_IsInProgress_Exp"]
    for s in ["NotReady", "Complete"] + list(steps):
        for k in ("IsAfter", "IsBefore", "IsEqual", "IsAfterOrEqual", "IsBeforeOrEqual", "IsNot", "Is",
                  "IsNotEqual", "IsAfterEqual", "IsBeforeEqual", "IsOrAfter", "IsOrBefore"):
            out.append(f"{c}_{k}_{s}_Exp")
        out.append(f"{c}_{s}")
        out.append(f"{c}_{s}_Exp")
    return out


_DIGITS = re.compile(r"\d+")


def _siblings(n):
    """X_03 -> X_00..X_99. Each digit run varies over its width, 0..99 for 1-2 digits, 0..999 for 3 and
    0..9999 for 4."""
    ms = list(_DIGITS.finditer(n))
    if not ms or len(ms) > 4:
        return ()
    out = []
    for m in ms:
        w = len(m.group())
        if w > 4 or len(n) > 80:
            continue
        pre, post = n[:m.start()], n[m.end():]
        if w == 1:
            out.extend(f"{pre}{i}{post}" for i in range(100))
        elif w == 4:  # like Dm_Kokiri_0010, the same thousand
            out.extend(f"{pre}{m.group()[0]}{i:03d}{post}" for i in range(1000))
        else:
            out.extend(f"{pre}{i:0{w}d}{post}" for i in range(10 ** w))
    return out


# BoolExp
ENUM_OPS = {12: ">", 11: "<", 1: "="}
INT_OPS = {15: "=", 18: "<", 19: ">"}


def decode_exp(values, nm, step_enums, enums):
    """The formula (SCHEMA.md syntax) of a BoolExp's reverse-Polish steps, and [unknown opcodes]."""
    stack = []
    bad = []
    i = 0
    vals = [[int(x) for x in v] for v in values]
    while i < len(vals):
        v = vals[i]
        op = v[0]
        if op in (0, 10):
            stack.append(f"flag:{nm.key(v[1])}")
        elif op == 8:
            stack.append(f"flag:{nm.key(v[1])}[{v[2] if len(v) > 2 else '?'}]")
        elif op in ENUM_OPS:
            if i + 1 < len(vals) and vals[i + 1][0] == 2:
                const = vals[i + 1][1]
                i += 1
            else:
                bad.append(op)
                const = None
            e = v[1]
            raw = enums.get(e, {})
            cname = raw.get(const, f"#{const}") if const is not None else "?"
            if e in step_enums:
                stack.append(f"step:{step_enums[e]}{ENUM_OPS[op]}{cname}")
            else:
                stack.append(f"enum:{nm.key(e)}{ENUM_OPS[op]}{cname}")
        elif op in INT_OPS:
            if i + 1 < len(vals) and vals[i + 1][0] == 16:
                const = _s32(vals[i + 1][1])
                i += 1
            else:
                bad.append(op)
                const = "?"
            stack.append(f"int:{nm.key(v[1])}{INT_OPS[op]}{const}")
        elif op in (3, 4):
            if len(stack) < 2:
                bad.append(op)
            else:
                b, a = stack.pop(), stack.pop()
                f = "AND" if op == 3 else "OR"
                stack.append(f"{f}({', '.join(_flat(f, a) + _flat(f, b))})")
        elif op == 5:
            if stack:
                stack.append(f"NOT({stack.pop()})")
            else:
                bad.append(op)
        elif op == 2:
            stack.append(f"enumconst:{v[1]}")
            bad.append(op)
        elif op == 16:
            stack.append(f"const:{v[1]}")
            bad.append(op)
        else:
            bad.append(op)
            stack.append(f"unknown:op{op}")
        i += 1
    if len(stack) != 1:
        bad.append("stack")
        return "AND(" + ", ".join(stack) + ")" if stack else "const:true", bad
    return stack[0], bad


def _s32(x):
    x = int(x) & 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


def _flat(f, s):
    """AND(a, AND(b, c)) -> [a, b, c] (only the outermost level of the same combinator)."""
    if s.startswith(f + "(") and s.endswith(")"):
        inner = s[len(f) + 1:-1]
        parts, depth, cur = [], 0, ""
        for ch in inner:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(cur.strip())
                cur = ""
            else:
                cur += ch
        parts.append(cur.strip())
        return parts
    return [s]


# Files
def read_challenges(fs):
    """{quest: [step names in order]} from RSDB Challenge. A quest's enum is Step_<quest>, NotReady plus these."""
    out = {}
    for r in common.read_byml(fs, CHALLENGE):
        name = os.path.basename(r["__RowId"]).split(".", 1)[0]
        out[name] = [s["Name"] for s in r.get("Steps") or []]
    return out


def index_challenges(fs, rel):
    recs = {}
    for r in common.read_byml(fs, rel):
        name = os.path.basename(r["__RowId"]).split(".", 1)[0]
        rec = {"steps": [s["Name"] for s in r.get("Steps") or []], "category": int(r.get("Category") or 0)}
        if r.get("IsCompleteTarget"):
            rec["complete_target"] = True
        flags = {}
        for s in r.get("Steps") or []:
            f = {k: v for k, v in s.items() if k != "Name" and v not in (False, "", [], None, 0)}
            if f:
                flags[s["Name"]] = common.jsonable(f)
        if flags:
            rec["step_info"] = flags
        recs[name] = rec
    return {"kind": "challenges", "challenges": recs}


def index_gmdreset(fs, rel):
    """{area: {SupplyItemResetSystemActor hash: [per-object row hashes it resets]}} (decimal strings)."""
    root = common.read_byml(fs, rel)
    out = {}
    for area, d in root.items():
        out[area] = {str(int(src)): [str(int(x)) for x in v.get("DstHash") or []] for src, v in d.items()}
    return {"kind": "gmd_reset", "areas": out}


def index_gamedata(fs, rel):
    root = common.read_byml(fs, rel)
    data = root["Data"]
    try:
        challenges = read_challenges(fs)
    except Exception:  # noqa: BLE001
        challenges = {}
    nm, hv, stats = build_names(fs, root, challenges)
    enums = {}                         # enum row hash -> {value hash: raw value}
    for t in ("Enum", "EnumArray"):
        for r in data.get(t, []):
            enums[int(r["Hash"])] = {int(h): v for h, v in zip(r.get("Values") or [], r.get("RawValues") or [])}
    step_enums = {}
    for c in challenges:
        h = H(f"Step_{c}")
        if h in nm.rows:
            step_enums[h] = c
    keys = {}
    unnamed = collections.Counter()
    bad_ops = collections.Counter()
    for t, rs in data.items():
        if t == "Bool64bitKey":
            continue
        for r in rs:
            h = int(r["Hash"])
            k = nm.key(h)
            if k in keys:              # a hash in two tables, keep both
                k = f"{k}@{t}"
            rec = {"type": t}
            if nm.how.get(h) not in (None, "file", "struct"):
                rec["named_by"] = nm.how[h]
            if h not in nm.name:
                unnamed[t] += 1
                par = nm.parent.get(h)
                if par:
                    rec["parent"] = nm.key(par[0])
                    rec["member"] = nm.mem.get(par[1], f"#{par[1]}")
            dv = r.get("DefaultValue")
            if t in ("Enum", "EnumArray"):
                rec["values"] = list(r.get("RawValues") or [])
                rec["default"] = enums[h].get(int(dv), f"#{int(dv)}") if dv is not None else None
            elif t == "Struct":
                rec["members"] = [nm.mem.get(int(m["Hash"]), f"#{int(m['Hash'])}") for m in dv or []]
            elif t in ("Binary", "BinaryArray"):
                rec["bytes"] = int(dv)
            elif t == "BoolExp":
                f, bad = decode_exp(r.get("Values") or [], nm, step_enums, enums)
                rec["exp"] = f
                if bad:
                    rec["exp_problems"] = [str(b) for b in bad]
                    rec["rpn"] = [[int(x) for x in v] for v in r.get("Values") or []]
                    for b in bad:
                        bad_ops[str(b)] += 1
            elif dv is not None:
                rec["default"] = common.jsonable(dv)
            rec["reset"] = int(r.get("ResetTypeValue", 0))
            sv = int(r.get("SaveFileIndex", -1))
            if sv >= 0:
                rec["save"] = sv
            for f, out in (("TotalSize", "size"), ("Size", "size"), ("ArraySize", "size")):
                if f in r and "size" not in rec:
                    rec[out] = int(r[f])
            if "OriginalSize" in r and int(r["OriginalSize"]) != rec.get("size"):
                rec["orig_size"] = int(r["OriginalSize"])
            if t == "Struct" and "Size" in r:
                rec["size"] = int(r["Size"])
            if rec.get("default") in (None, False, 0, 0.0, "") and t not in ("Enum", "EnumArray"):
                rec.pop("default", None)
            keys[k] = rec
    b64 = data.get("Bool64bitKey", [])
    b64_reset = collections.defaultdict(list)
    b64_extra = {}
    for r in b64:
        hs = str(int(r["Hash"]))
        rt = int(r.get("ResetTypeValue", 0))
        if rt != 24:
            b64_reset[str(rt)].append(hs)
        if "ExtraByte" in r:
            b64_extra[hs] = int(r["ExtraByte"])
    total = collections.Counter(t for t, rs in data.items() if t != "Bool64bitKey" for _ in rs)
    named = collections.Counter(nm.rows[h][0] for h in nm.name)
    how = collections.Counter(nm.how.values())
    md = root.get("MetaData") or {}
    rec = {"keys": keys,
           "b64": [str(int(r["Hash"])) for r in b64], "b64_count": len(b64),
           "b64_reset": dict(b64_reset), "b64_extra": b64_extra,
           "unnamed": sum(unnamed.values()), "unnamed_by_type": dict(unnamed),
           "rows_by_type": dict(total), "named_by_type": dict(named), "named_how": dict(how),
           "save_files": {str(i): p for i, p in enumerate(md.get("SaveDirectory") or [])},
           "metadata": common.jsonable(md), "names_build": stats}
    if bad_ops:
        rec["exp_unknown_ops"] = dict(bad_ops)
    if not getattr(fs, "overlays", None):
        _save_names(nm, stats)
    return rec


def _save_names(nm, stats):
    """Writes every 32-bit name this builder resolved to cache/gamedb/vanilla/gamedata_names.json, as
    {"rows": {hash: name}, "members": {hash: member name}, "how": ...}. Other tools can name hashed GameData
    references with it."""
    doc = {"meta": {"section": "gamedata_names", "version": VERSION, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
                    **{k: v for k, v in stats.items() if k != "sources"}},
           "rows": {str(h): n for h, n in sorted(nm.name.items())},
           "members": {str(h): m for h, m in sorted(nm.mem.items())},
           "how": {str(h): w for h, w in sorted(nm.how.items()) if w != "file"}}
    try:
        common.save("gamedata_names", doc)
    except OSError:
        pass


# Summary
def reset_callers(fs):
    """{ResetType n: [Sequence module that calls SeqExecuteResetGameData with it]}."""
    out = collections.defaultdict(list)
    try:
        import ainb
    except Exception:  # noqa: BLE001
        return {}
    d0 = os.path.join(fs.root, "Sequence")
    if not os.path.isdir(d0):
        return {}
    for f in sorted(os.listdir(d0)):
        if not f.endswith(".ainb"):
            continue
        rel = "Sequence/" + f
        try:
            d = common.read_any(fs, rel)
        except Exception:  # noqa: BLE001
            continue
        if b"SeqExecuteResetGameData" not in d:
            continue
        try:
            a = ainb.Ainb(d)
        except Exception:  # noqa: BLE001
            continue
        for i, n in enumerate(a.nodes):
            if n["name"] != "SeqExecuteResetGameData":
                continue
            for sec in ("inputs", "properties"):
                for e in n[sec]["int"]:
                    if e["name"] == "ResetType" and e.get("node", -1) < 0:
                        out[int(e["value"])].append(f"{rel}#{i}")
    return {k: sorted(v) for k, v in sorted(out.items())}


def finish(fs, by_file):
    gd = by_file.get(GAMEDATA) or {}
    keys = gd.get("keys") or {}
    ch = (by_file.get(CHALLENGE) or {}).get("challenges") or {}
    challenges = {}
    for c, rec in ch.items():
        e = keys.get(f"Step_{c}") or {}
        exp = sorted(n for n in keys if n.startswith(c + "_") and n.endswith("_Exp") and
                     re.match(rf"^{re.escape(c)}_(Is[A-Za-z]+)(_.+)?_Exp$", n))
        out = {"steps": rec.get("steps") or []}
        if e:
            out["enum"] = f"Step_{c}"
            out["enum_values"] = e.get("values")
            out["default"] = e.get("default")
            out["reset"] = e.get("reset")
            if "save" in e:
                out["save"] = e["save"]
        out["exp_names"] = exp
        for k in ("category", "complete_target", "step_info"):
            if k in rec:
                out[k] = rec[k]
        challenges[c] = out
    # reset types
    callers = reset_callers(fs)
    values = collections.Counter(k["reset"] for k in keys.values())
    for r in gd.get("b64_reset", {}):
        values[int(r)] += len(gd["b64_reset"][r])
    values[24] += gd.get("b64_count", 0) - sum(len(v) for v in gd.get("b64_reset", {}).values())
    bits = {}
    for n in range(10):
        if any(v & (1 << n) for v in values):
            bits[str(1 << n)] = {"reset_type": n, "when": RESET_CALLS.get(n, "unknown"),
                                 "callers": callers.get(n, []),
                                 "certain": bool(callers.get(n))}
    reset_types = {}
    for v, c in sorted(values.items()):
        parts = [b for b in range(10) if v & (1 << b)]
        reset_types[str(v)] = {"rows": c, "bits": [1 << b for b in parts],
                               "meaning": "no bit: SeqExecuteResetGameData never resets it, not even on a new game "
                                          "(BoolExp and Struct rows hold no value; a saved row keeps what its save "
                                          "file holds: options, captions, account)" if not parts else
                               "; ".join(f"{1 << b}: {RESET_CALLS.get(b, 'unknown')}" for b in parts)}
    # notable defaults
    true_bools = sorted(n for n, k in keys.items() if k["type"] == "Bool" and k.get("default") is True and
                        "save" in k)
    true_unsaved = sorted(n for n, k in keys.items() if k["type"] == "Bool" and k.get("default") is True and
                          "save" not in k)
    ints = {n: {"default": k["default"], "reset": k["reset"], **({"save": k["save"]} if "save" in k else {})}
            for n, k in sorted(keys.items()) if k["type"] in ("Int", "UInt", "Int64", "UInt64") and k.get("default")}
    rows = gd.get("rows_by_type") or {}
    named = gd.get("named_by_type") or {}
    stats = {t: {"rows": n, "named": named.get(t, 0), "pct": round(100.0 * named.get(t, 0) / n, 1) if n else 100.0}
             for t, n in sorted(rows.items())}
    allr = sum(rows.values())
    alln = sum(named.values())
    stats["_all"] = {"rows": allr, "named": alln, "pct": round(100.0 * alln / allr, 1) if allr else 100.0}
    # HavePlayedEvent members that no name in the game spells. Every RSDB EventSetting (the events the game can play,
    # and so mark played) names one, so these are left-over rows nothing writes or reads by name.
    hpe = sum(1 for n, k in keys.items() if n.startswith("#") and k.get("parent") == "HavePlayedEvent")
    if "Bool" in stats:
        b = stats["Bool"]
        stats["Bool_without_unnamed_HavePlayedEvent"] = {
            "rows": b["rows"] - hpe, "named": b["named"],
            "pct": round(100.0 * b["named"] / (b["rows"] - hpe), 1) if b["rows"] > hpe else 100.0}
    # unnamed rows an expression reads, and they matter because the expression's value depends on them
    read_by_exp = collections.defaultdict(list)
    for n, k in keys.items():
        for m in re.finditer(r"(?:flag|int|enum):(#\d+)", k.get("exp") or ""):
            if n not in read_by_exp[m.group(1)]:
                read_by_exp[m.group(1)].append(n)
    return {"challenges": challenges, "reset_types": reset_types, "reset_bits": bits,
            "save_files": gd.get("save_files") or {},
            "resolution": stats, "named_how": gd.get("named_how") or {},
            "unnamed_have_played_event": hpe,
            "unnamed_read_by_exp": {h: sorted(v) for h, v in sorted(read_by_exp.items())},
            "notable_defaults": {"saved_bools_true": true_bools, "unsaved_bools_true": true_unsaved,
                                 "ints_nonzero": ints},
            "exp_unknown_ops": gd.get("exp_unknown_ops") or {}}
