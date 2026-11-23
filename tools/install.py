"""Install a built patch into Longshot's romfs, switch patches, or put the original files back.

usage:
  python tools/install.py status  ROMFS_DIR
  python tools/install.py install ROMFS_DIR PATCH_DIR
  python tools/install.py restore ROMFS_DIR
  python tools/install.py mod-install ROMFS_DIR PATCH_DIR   (Longshot 3.1.0 and later: as a mod, see below)
  python tools/install.py mod-remove  ROMFS_DIR
  python tools/install.py mod-status  ROMFS_DIR

As a mod (Longshot 3.1.0, see its docs/user/using-mods.md)
The patch goes to <game folder>/mods/Rando of Time/romfs/, with the app's mod folder name and
randomizer_files.txt list like on its other targets. Longshot lays it over the untouched RomFS at each start.
It merges the mods' size tables with the game's (the larger entry wins) and raises any mod file's entry it
outgrows, so nothing of Longshot's gets edited and no originals are kept. Its PC wording
(data/longshot_pc_text.json, the microphone help line) is applied to the patch's text files there, because a
mod's text file wins over Longshot's rewording. mod-install first takes off a patch installed the old way
(restore), so the RomFS under the mod is the original. The mod folder holds a record of what was written
(rando-of-time.json), and mod-remove only deletes a folder that has one. Longshot finds mods when it starts,
so the game has to be closed.

Originals come from ./original (SHA256SUMS.txt). The installed patch is recorded in
./installed.json. Installing a new patch first puts back the files of the old one. A file only
gets overwritten when it's exactly the original or exactly what we installed, so if a Longshot
rebuild changed the game files we catch it instead of overwriting it.

Longshot serves its own copy of the game's resource size table instead of the one in RomFS. That's
<game folder>/prompts/rsizetable.zs, the game's table with its button-icon files raised. A file bigger than
its entry there fails to load, which is what the grown small-chest scene file did, and no small chest opened.
So every entry the patch raises gets raised in Longshot's copy too. The original copy is kept in
./original/_longshot and put back on restore. Longshot 3.1.0 dropped that copy (its #2092, it serves the
game's table with the font's entry raised), so where prompts/rsizetable.zs is gone, the patch's RomFS table
is the one served and install and restore leave the prompts folder alone.

Longshot also serves its own copy of every language's text (<game folder>/texts/), built from the RomFS text
as it was when Longshot was last built, plus a few PC changes of its own (data/longshot_pc_text.json). So
install writes those copies from the patch's text (restore writes them from the original text) with
Longshot's changes applied. It also makes every text entry in Longshot's size table fit its copy, because
entries too small for the copies crashed the game at boot. Longshot's own copies are kept once in
./original/_longshot/texts.
"""
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romtools import Romfs, Restbl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL = os.environ.get("REMAKE_ORIGINAL") or os.path.join(HERE, "original")  # the app: next to the game
STATE = os.path.join(os.path.dirname(os.path.abspath(ORIGINAL)), "installed.json")
OUT = os.path.join(HERE, "out")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None


def original_sums():
    sums = {}
    for line in open(os.path.join(ORIGINAL, "SHA256SUMS.txt"), encoding="utf-8"):
        if line.strip():
            h, name = line.strip().split(" *", 1)
            sums[os.path.normpath(name)] = h
    return sums


def patch_files(patch_dir):
    out = {}
    for dp, _, fns in os.walk(patch_dir):
        for fn in fns:
            if fn != "patch_report.json":  # every game file the patch contains, compressed or not
                full = os.path.join(dp, fn)
                out[os.path.normpath(os.path.relpath(full, patch_dir))] = full
    return out


def exefs_files(patch_dir):
    """{name: path} of the build's code patches: the exefs folder make_patch writes beside the patch folder."""
    d = os.path.join(os.path.dirname(os.path.abspath(patch_dir)), "exefs")
    if not os.path.isdir(d):
        return {}
    return {fn: os.path.join(d, fn) for fn in sorted(os.listdir(d))
            if fn.startswith("rando_of_time") and fn.endswith(".pchtxt")}


MAIN_IN_IMAGE = 0x20000  # Longshot's image.bin: the game's code from 0x80000000, main at 0x80020000


def code_built(romfs, pchtxt):
    """Is this code patch in the game Longshot built last (image.bin beside the romfs)? None when there's no image.
    A .pchtxt line is "OFFSET BYTES", OFFSET into main (offset_shift cancels the NSO header)."""
    import re
    img = os.path.join(os.path.dirname(os.path.normpath(romfs)), "image.bin")
    if not os.path.exists(img):
        return None
    with open(img, "rb") as f:
        data = f.read()
    for line in open(pchtxt, encoding="utf-8"):
        m = re.fullmatch(r"([0-9A-Fa-f]{8}) ([0-9A-Fa-f]+)", line.strip())
        if m:
            at, want = int(m.group(1), 16) + MAIN_IN_IMAGE, bytes.fromhex(m.group(2))
            if data[at:at + len(want)] != want:
                return False
    return True


def new_files_of(patch_dir, files):
    """The patch's files the game doesn't have. That's make_patch's "new_files", meaning patch_report "new" and
    not inside a pack."""
    report = os.path.join(patch_dir, "patch_report.json")
    made = {os.path.normpath(w["file"]) for w in (json.load(open(report, encoding="utf-8")).get("files", [])
                                                  if os.path.exists(report) else [])
            if w.get("new") and not w.get("inside_pack")}  # new files inside a pack travel with their pack
    return {rel for rel in files if rel in made}


def record_of(romfs, patch_dir, files=None):
    """The install record a patch makes. That's its game files and new files with their installed hashes, plus
    Longshot's size table the way install raises it (None when the patch raises nothing there)."""
    files = files or patch_files(patch_dir)
    made = new_files_of(patch_dir, files)
    state = {"patch": os.path.abspath(patch_dir),
             "files": {rel: sha(src) for rel, src in files.items() if rel not in made},
             "new_files": {rel: sha(src) for rel, src in files.items() if rel in made}}
    table = longshot_table(romfs)
    if RSTB in files and os.path.exists(table) and os.path.exists(LONGSHOT_ORIGINAL):
        new_table, n = raise_longshot_table(romfs, files[RSTB])
        if n:
            fs = Romfs(romfs, ORIGINAL)
            state["longshot_table"] = {"path": table, "sha": hashlib.sha256(new_table).hexdigest(),
                                       "content_sha": hashlib.sha256(fs.zs.decompress(new_table)).hexdigest()}
    return state


def load_state(romfs):
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    # No record, so see whether a built patch (out/<seed>/patch, or an older flat out/<seed>) is fully there in the
    # romfs, installed before we kept records. If it is, we rebuild its record, new files and Longshot's table included.
    if os.path.isdir(OUT):
        for name in sorted(os.listdir(OUT)):
            for cand in (os.path.join(OUT, name, "patch"), os.path.join(OUT, name)):
                files = patch_files(cand) if os.path.isdir(cand) else {}
                files = {r: s for r, s in files.items() if not r.split(os.sep)[0] in ("patch",)}
                if files and all(sha(os.path.join(romfs, rel)) == sha(src) for rel, src in files.items()):
                    state = record_of(romfs, cand, files)
                    lt = state.get("longshot_table")
                    if lt and sha(lt["path"]) != lt["sha"] and table_content_sha(romfs, lt["path"]) != lt["content_sha"]:
                        del state["longshot_table"]  # the live table isn't what this patch makes, so it's not ours
                    return state
    return None


def save_state(state):
    if state is None:
        if os.path.exists(STATE):
            os.remove(STATE)
    else:
        json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)


RSTB = os.path.normpath("System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs")
LONGSHOT_ORIGINAL = os.path.join(ORIGINAL, "_longshot", "prompts", "rsizetable.zs")


def longshot_table(romfs):
    return os.path.join(os.path.dirname(os.path.normpath(romfs)), "prompts", "rsizetable.zs")


def table_content_sha(romfs, path):
    """SHA256 of Longshot's size table, decompressed. A Longshot update can rewrite the file with the same entries
    but different compression, so we go by the content to tell whether it's still what we installed."""
    fs = Romfs(romfs, ORIGINAL)
    return hashlib.sha256(fs.zs.decompress(open(path, "rb").read())).hexdigest()


def raise_longshot_table(romfs, patch_rstb):
    """Longshot's size table with every entry the patch raised (over the game's table) raised to match.
    Returns (bytes to write, number of entries raised)."""
    fs = Romfs(romfs, ORIGINAL)
    if not os.path.exists(LONGSHOT_ORIGINAL):
        os.makedirs(os.path.dirname(LONGSHOT_ORIGINAL), exist_ok=True)
        shutil.copyfile(longshot_table(romfs), LONGSHOT_ORIGINAL)
    raw = open(LONGSHOT_ORIGINAL, "rb").read()
    ls = Restbl(fs.zs.decompress(raw))
    game = Restbl(fs.zs.decompress(open(os.path.join(ORIGINAL, RSTB), "rb").read()))
    ours = Restbl(fs.zs.decompress(open(patch_rstb, "rb").read()))
    n = 0
    for table in ("crc", "names"):
        mine, base, theirs = getattr(ours, table), getattr(game, table), getattr(ls, table)
        for key, size in mine.items():
            if size > base.get(key, 0) and size > theirs.get(key, 0):
                theirs[key] = size
                n += 1
    n += fit_longshot_served(romfs, fs, ls, game)
    return fs.zs.compress(ls.dump(), fs.zs.dict_id(raw)), n


def fit_table_to_texts(romfs):
    """For when there's no patch table to merge. Raises Longshot's live table where its text copies don't fit, and
    the saved base copy the same way (it only gains room), so the next install still recognises the live table as
    the original."""
    table = longshot_table(romfs)
    if not os.path.exists(table):
        return
    fs = Romfs(romfs, ORIGINAL)
    game = Restbl(fs.zs.decompress(open(os.path.join(ORIGINAL, RSTB), "rb").read()))
    same = os.path.exists(LONGSHOT_ORIGINAL) and sha(table) == sha(LONGSHOT_ORIGINAL)
    for path in [table] + ([LONGSHOT_ORIGINAL] if same else []):
        raw = open(path, "rb").read()
        ls = Restbl(fs.zs.decompress(raw))
        if fit_longshot_served(romfs, fs, ls, game):
            open(path, "wb").write(fs.zs.compress(ls.dump(), fs.zs.dict_id(raw)))
            if path == table:
                print(f"  raised    Longshot's text entries in {table}")


def fit_longshot_served(romfs, fs, ls, game):
    """Raises Longshot's entries for the files Longshot serves from its own folders instead of RomFS, so each fits
    its file plus the game's margin for that file. Those files are its texts,
    <game folder>/texts/<lang>.product.110.sarc.zs for Mals/<Lang>.Product.110.sarc. A Longshot update rebuilt its
    texts bigger, so a table rebuilt from an older saved copy had every text entry short and the game crashed at
    boot making its message heap."""
    import glob
    n = 0
    texts = os.path.join(os.path.dirname(os.path.normpath(romfs)), "texts")
    for path in sorted(glob.glob(os.path.join(texts, "*.product.110.sarc.zs"))):
        lang = os.path.basename(path).split(".")[0]
        key = f"Mals/{lang[:2].upper()}{lang[2:]}.Product.110.sarc"
        try:
            vanilla = len(fs.read(key + ".zs"))
        except OSError:
            continue
        margin = max((game.get(key) or vanilla) - vanilla, 0)
        need = (len(fs.zs.decompress(open(path, "rb").read())) + margin + 31) & ~31
        if (ls.get(key) or 0) < need:
            ls.set(key, need)
            n += 1
    return n


PC_TEXT = os.path.join(HERE, "data", "longshot_pc_text.json")
LONGSHOT_TEXTS_ORIGINAL = os.path.join(ORIGINAL, "_longshot", "texts")


def longshot_texts(romfs):
    return os.path.join(os.path.dirname(os.path.normpath(romfs)), "texts")


def derive_pc_text(romfs):
    """Works out Longshot's PC wording on the player's machine, since the release ships no game text and so no
    data/longshot_pc_text.json. It's every message of the on-screen UI text (LayoutMsg/, where Longshot's changes
    are, the microphone help line) that differs between Longshot's copy and the game's text. Longshot's copy is
    the one we first saw, kept in ./original/_longshot/texts. Only LayoutMsg, because a seed never edits it, so
    an old seed's text can't be mistaken for Longshot's."""
    import glob
    import msbt
    from romtools import sarc_files
    fs = Romfs(romfs, ORIGINAL)
    out = {}
    for path in sorted(glob.glob(os.path.join(longshot_texts(romfs), "*.product.110.sarc.zs"))):
        name = os.path.basename(path)
        keep = os.path.join(LONGSHOT_TEXTS_ORIGINAL, name)
        lang = name.split(".")[0]
        lang = f"{lang[:2].upper()}{lang[2:]}"
        try:
            theirs = sarc_files(fs.zs.decompress(open(keep if os.path.exists(keep) else path, "rb").read()))
            ours = sarc_files(fs.read(f"Mals/{lang}.Product.110.sarc.zs"))
        except Exception:  # noqa: BLE001 - a language Longshot has and the game hasn't: nothing to carry over
            continue
        for f, data in theirs.items():
            if not f.startswith("LayoutMsg/") or f not in ours or ours[f] == data:
                continue
            a, b = msbt.Msbt(data), msbt.Msbt(ours[f])
            for label in a.labels:
                if label in b and a.markup(label) != b.markup(label):
                    out.setdefault(lang, {}).setdefault(f, {})[label] = a.markup(label)
    return out


def write_longshot_texts(romfs, files=None):
    """Longshot serves its own copy of every language's text (<game folder>/texts/<lang>.product.110.sarc.zs) instead
    of RomFS Mals/<Lang>.Product.110.sarc.zs. Its copies are the RomFS text as it was when Longshot was last built,
    plus a few PC changes of its own (data/longshot_pc_text.json, the microphone help line). That means they can
    show an older seed's hints. So we write each language's copy here from the patch's text with those changes
    applied.
    `files` is the patch's {rel: path}, and with None or no Mals in it we use the original text.
    Longshot's own copies are kept once in ./original/_longshot/texts. Returns the number of files written."""
    import glob
    import msbt
    from romtools import sarc_files, sarc_write
    fs = Romfs(romfs, ORIGINAL)
    # Longshot's own copies, kept once. A copy that's neither the kept one nor what we last wrote was rewritten by a
    # Longshot update (one rebuilt its texts), so the kept one gets refreshed before anything uses it
    written_path = os.path.join(LONGSHOT_TEXTS_ORIGINAL, "written.json")
    written = json.load(open(written_path, encoding="utf-8")) if os.path.exists(written_path) else {}
    for path in sorted(glob.glob(os.path.join(longshot_texts(romfs), "*.product.110.sarc.zs"))):
        name = os.path.basename(path)
        keep = os.path.join(LONGSHOT_TEXTS_ORIGINAL, name)
        # Only once a write of ours is on record. An install from before the record existed left a seed's text
        # there, and that mustn't be taken for Longshot's own.
        stale = name in written and sha(path) not in (sha(keep), written[name])
        if not os.path.exists(keep) or stale:
            if stale:
                print(f"  note      {path} changed outside the randomizer (a Longshot update?): kept as Longshot's own")
            os.makedirs(LONGSHOT_TEXTS_ORIGINAL, exist_ok=True)
            shutil.copyfile(path, keep)
    pc = json.load(open(PC_TEXT, encoding="utf-8"))["messages"] if os.path.exists(PC_TEXT) else derive_pc_text(romfs)
    n = 0
    for path in sorted(glob.glob(os.path.join(longshot_texts(romfs), "*.product.110.sarc.zs"))):
        name = os.path.basename(path)
        keep = os.path.join(LONGSHOT_TEXTS_ORIGINAL, name)
        lang = name.split(".")[0]
        rel = os.path.normpath(f"Mals/{lang[:2].upper()}{lang[2:]}.Product.110.sarc.zs")
        src = (files or {}).get(rel)
        data = fs.zs.decompress(open(src, "rb").read()) if src else fs.read(rel.replace(os.sep, "/"))
        members = sarc_files(data)
        for msg_file, labels in pc.get(f"{lang[:2].upper()}{lang[2:]}", {}).items():
            m = msbt.Msbt(members[msg_file])
            for label, markup in labels.items():
                m.set_markup(label, markup)
            members[msg_file] = m.dump()
        raw = open(keep, "rb").read()
        new = fs.zs.compress(sarc_write(members), fs.zs.dict_id(raw))
        if not os.path.exists(path) or open(path, "rb").read() != new:
            open(path, "wb").write(new)
            n += 1
        written[name] = hashlib.sha256(new).hexdigest()
    if written:
        json.dump(written, open(written_path, "w", encoding="utf-8"), indent=1, sort_keys=True)
    return n


def restore_problems(romfs, state, sums):
    """Why restoring `state` would leave a mixed game folder. [] means every recorded file is the original or what
    the record installed. An interrupted install leaves some of each, and both are fine."""
    out = []
    for rel, h in (state or {}).get("new_files", {}).items():
        cur = sha(os.path.join(romfs, rel))
        if cur is not None and cur != h:
            out.append(f"{rel} is not what was installed")
    for rel, h in (state or {}).get("files", {}).items():
        cur = sha(os.path.join(romfs, rel))
        if cur != sums.get(rel) and cur != h:
            out.append(f"{rel} is neither the original nor what was installed")
        if cur != sums.get(rel) and not os.path.exists(os.path.join(ORIGINAL, rel)):
            out.append(f"{rel}: no original copy in {ORIGINAL}")
    return out


def longshot_table_state(romfs, state):
    """'original', 'installed' (what `state` raised it to) or 'other' (a Longshot update's own table)."""
    lt = (state or {}).get("longshot_table")
    path = (lt or {}).get("path") or longshot_table(romfs)
    if not os.path.exists(path) or not os.path.exists(LONGSHOT_ORIGINAL) or sha(path) == sha(LONGSHOT_ORIGINAL):
        return "original"
    if lt and (sha(path) == lt["sha"] or (lt.get("content_sha") and lt["content_sha"] == table_content_sha(romfs, path))):
        return "installed"
    return "other"


def adopt_longshot_table(romfs):
    """A Longshot update rewrote its size table, so keep the new one as Longshot's original (the old saved copy
    would take its new entries away). That way install and restore carry on instead of stopping for good."""
    table = longshot_table(romfs)
    shutil.copyfile(table, LONGSHOT_ORIGINAL)
    print(f"  note      {table} changed outside the randomizer (a Longshot update?): kept as Longshot's original")


def restore(romfs, state, sums):
    """Puts back the files `state` installed. Everything gets checked first, so either the whole folder goes back
    or nothing is touched."""
    if not state:
        return
    problems = restore_problems(romfs, state, sums)
    if problems:
        sys.exit("Stopped, nothing changed: " + "; ".join(problems[:5]) + " (was Longshot rebuilt? Reinstall "
                 "Longshot's game files, then delete " + STATE + ")")
    lt = state.get("longshot_table")
    ts = longshot_table_state(romfs, state)
    if ts == "installed":
        shutil.copyfile(LONGSHOT_ORIGINAL, lt["path"])
        print(f"  restored  {lt['path']}")
    elif ts == "other":
        adopt_longshot_table(romfs)
    for rel, h in state.get("new_files", {}).items():  # files the game doesn't have get removed
        dst = os.path.join(romfs, rel)
        if os.path.exists(dst):
            os.remove(dst)
            print(f"  removed   {rel}")
    for rel, h in state["files"].items():
        dst = os.path.join(romfs, rel)
        if sha(dst) == sums.get(rel):
            continue
        shutil.copyfile(os.path.join(ORIGINAL, rel), dst)
        print(f"  restored  {rel}")


MOD_NAME = "Rando of Time"  # the app's ModName, one folder name on every target
MOD_RECORD = "rando-of-time.json"  # the patch and each file's hash (status, the seed the app names)
MOD_LIST = "randomizer_files.txt"  # the app's list of the files it wrote (ReplaceMod / RemoveMod)
# The names from before the rename to Rando of Time. A seed installed under them is still found by mod-status,
# and mod-install / mod-remove take it out, so the old folder never stays behind as a second mod.
OLD_MOD_NAMES = ("OoT Remake Randomizer",)
OLD_MOD_RECORDS = ("remake-rando.json",)


def mod_dir(romfs):
    """<game folder>/mods/Rando of Time (the game folder holds romfs, bin and mods)."""
    return os.path.join(os.path.dirname(os.path.normpath(romfs)), "mods", MOD_NAME)


def mod_dirs(romfs):
    """The mod folder, then the ones under the old names."""
    mods = os.path.dirname(mod_dir(romfs))
    return [mod_dir(romfs)] + [os.path.join(mods, name) for name in OLD_MOD_NAMES]


def record_path(d):
    """The install record in mod folder `d` (under its old name too), or None."""
    for name in (MOD_RECORD,) + OLD_MOD_RECORDS:
        if os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)
    return None


def installed_mod_dir(romfs):
    """The folder holding the installed seed: the mod folder, else one under an old name, else the mod folder."""
    for d in mod_dirs(romfs):
        if record_path(d) or os.path.exists(os.path.join(d, MOD_LIST)):
            return d
    return mod_dir(romfs)


def game_running():
    """True while Longshot's game runs (Windows), since mods are read when it starts and its files may be in use.
    REMAKE_IGNORE_RUNNING=1 is for the app's tests on a scratch copy of a game folder while the real game runs
    (RandoOfTime.exe --ignore-running, --selftest ... --longshot)."""
    if os.name != "nt" or os.environ.get("REMAKE_IGNORE_RUNNING") == "1":
        return False
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq longshot.exe", "/NH"], capture_output=True, text=True)
    return "longshot.exe" in out.stdout.lower()


def pc_worded(fs, rel, raw, pc):
    """A patch text file (Mals/<Lang>.Product.110.sarc.zs, compressed) with Longshot's PC wording applied and
    compressed again with the same dictionary. `pc` is data/longshot_pc_text.json's "messages". You get `raw`
    back unchanged when the language has no PC change."""
    import msbt
    from romtools import sarc_files, sarc_write
    lang = os.path.basename(rel).split(".")[0]
    changes = pc.get(lang) or {}
    if not changes:
        return raw
    members = sarc_files(fs.zs.decompress(raw))
    for msg_file, labels in changes.items():
        if msg_file not in members:
            continue
        m = msbt.Msbt(members[msg_file])
        for label, markup in labels.items():
            if label in m.labels:
                m.set_markup(label, markup)
        members[msg_file] = m.dump()
    return fs.zs.compress(sarc_write(members), fs.zs.dict_id(raw))


def mod_record(romfs):
    path = record_path(installed_mod_dir(romfs))
    return json.load(open(path, encoding="utf-8")) if path else None


def mod_remove(romfs):
    """Deletes the randomizer's mod folder and one left under an old name, but only folders holding our record."""
    removed = False
    for d in mod_dirs(romfs):
        if not os.path.isdir(d):
            continue
        if record_path(d) is None and not os.path.exists(os.path.join(d, MOD_LIST)):
            if d == mod_dir(romfs):
                sys.exit(f"Stopped, nothing changed: {d} has no {MOD_RECORD} or {MOD_LIST}: not a folder the "
                         f"randomizer wrote")
            continue  # a folder with an old name that isn't ours: leave it alone
        shutil.rmtree(d)
        print(f"  removed   {d}")
        removed = True
    return removed


MAX_PATH = 260  # Windows' classic path limit in UTF-16 units, the end of string included


def long_paths(d, files):
    """(how many, the longest) of the mod's files whose full path in `d` would be MAX_PATH units or more, else None."""
    full = [os.path.abspath(os.path.join(d, "romfs", rel)) for rel in files]
    bad = [p for p in full if len(p.encode("utf-16-le")) // 2 >= MAX_PATH]
    return (len(bad), max(bad, key=len)) if bad else None


def mod_install(romfs, patch_dir, sums):
    """Installs `patch_dir` as Longshot's mod (see "As a mod" in the module docstring)."""
    if game_running():
        sys.exit("Stopped, nothing changed: Longshot's game is running (close it first: mods are read at its start)")
    files = patch_files(patch_dir)
    too_long = long_paths(mod_dir(romfs), files)
    if too_long:
        n, longest = too_long
        sys.exit(f"Stopped, nothing changed: {n} of the mod's files would get a path of {MAX_PATH} characters or more "
                 f"(the longest is {len(longest)}: {longest}). Windows and some emulators can't open those, and the "
                 f"game stops when it needs one. Move Longshot's folder closer to the drive root (like E:\\Longshot) "
                 f"and install again.")
    state = load_state(romfs)
    if state:  # a patch installed the old way comes off first, so the RomFS under the mod is the original
        problems = restore_problems(romfs, state, sums)
        if problems:
            sys.exit("Stopped, nothing changed: " + "; ".join(problems[:5]))
        restore(romfs, state, sums)
        save_state(None)
        n_texts = write_longshot_texts(romfs)
        if n_texts:
            print(f"  wrote     {n_texts} of Longshot's text files from the original text")
        fit_table_to_texts(romfs)
        print("  restored  the patch installed in the game files (it is a mod from now on)")
    mod_remove(romfs)
    d = mod_dir(romfs)
    fs = Romfs(romfs, ORIGINAL)
    # Longshot's PC wording. We use the project's copy, or work it out from the player's game since the release
    # ships no game text
    pc = json.load(open(PC_TEXT, encoding="utf-8"))["messages"] if os.path.exists(PC_TEXT) else derive_pc_text(romfs)
    record = {"patch": os.path.abspath(patch_dir), "complete": False, "files": {}}
    os.makedirs(d)
    json.dump(record, open(os.path.join(d, MOD_RECORD), "w", encoding="utf-8"), indent=1)
    for rel, src in sorted(files.items()):
        dst = os.path.join(d, "romfs", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        raw = open(src, "rb").read()
        if os.path.normpath(rel).startswith("Mals" + os.sep) and rel.endswith(".Product.110.sarc.zs"):
            raw = pc_worded(fs, rel, raw, pc)
        open(dst, "wb").write(raw)
        record["files"][rel.replace(os.sep, "/")] = hashlib.sha256(raw).hexdigest()
    code = exefs_files(patch_dir)  # code patches: Longshot's Builder applies them when it builds the game
    if code:
        record["exefs"] = {}
        os.makedirs(os.path.join(d, "exefs"))
        for name, src in code.items():
            raw = open(src, "rb").read()
            open(os.path.join(d, "exefs", name), "wb").write(raw)
            record["exefs"][name] = hashlib.sha256(raw).hexdigest()
    record["complete"] = True
    json.dump(record, open(os.path.join(d, MOD_RECORD), "w", encoding="utf-8"), indent=1)
    with open(os.path.join(d, MOD_LIST), "w", encoding="utf-8") as f:
        f.write("".join(rel + "\n" for rel in sorted(files)))
    print(f"done: {len(files)} files from {patch_dir} as the mod {d}")
    if code:
        print(f"  and {len(code)} code patch(es) in its exefs folder: build the game again in Longshot before "
              f"playing, or they aren't in the game")


def mod_status(romfs):
    rec = mod_record(romfs)
    if rec is None:
        print("installed as a mod: none")
        return
    d = installed_mod_dir(romfs)
    bad = [rel for rel, h in rec["files"].items() if sha(os.path.join(d, "romfs", *rel.split("/"))) != h]
    bad += [f"exefs/{n}" for n, h in (rec.get("exefs") or {}).items() if sha(os.path.join(d, "exefs", n)) != h]
    state = "complete" if rec.get("complete") else "INTERRUPTED"
    changed = f", {len(bad)} CHANGED" if bad else ""
    print(f"installed as a mod: {rec['patch']} ({len(rec['files'])} files, {state}{changed})"
          + (f", code patches: {', '.join(rec['exefs'])}" if rec.get("exefs") else ""))
    if d != mod_dir(romfs):
        print(f"  in {d}, the folder's old name: the next install moves it to {MOD_NAME}")
    for n in rec.get("exefs") or {}:  # a code patch only counts once Longshot has built the game with it
        built = code_built(romfs, os.path.join(d, "exefs", n))
        if built is not None:
            print(f"  {n}: " + ("in the game Longshot built" if built else
                                "NOT in the game Longshot built: build the game again in Longshot before playing"))
    # Check whether the patch was rebuilt after it was installed, otherwise the status says "complete" with 232
    # differences. Mals files are skipped since install applies Longshot's PC wording to them.
    if os.path.isdir(rec["patch"]):
        now = patch_files(rec["patch"])
        names = {rel.replace(os.sep, "/"): src for rel, src in now.items()}
        plain = {rel: h for rel, h in rec["files"].items() if not rel.startswith("Mals/")}
        differ = [rel for rel, h in plain.items() if rel not in names or sha(names[rel]) != h]
        extra = [rel for rel in names if rel not in rec["files"]]
        if differ or extra:
            print(f"  NOTE: {rec['patch']} no longer matches the installed mod ({len(differ)} files differ or are gone, "
                  f"{len(extra)} new): it was rebuilt after the install")
        else:
            print(f"  {rec['patch']} still matches the installed mod ({len(plain)} files compared; text files skipped)")
    else:
        print(f"  NOTE: {rec['patch']} is gone")


def main(cmd, romfs, patch_dir=None):
    if cmd == "mod-status":
        mod_status(romfs)
        return
    if cmd == "mod-remove":
        if game_running():
            sys.exit("Stopped, nothing changed: Longshot's game is running (close it first)")
        print("done" if mod_remove(romfs) else "no mod installed")
        return
    if cmd == "mod-install":
        # the originals only matter for a patch installed the old way, which keeps them. None kept means nothing
        # to undo
        has = os.path.exists(os.path.join(ORIGINAL, "SHA256SUMS.txt"))
        mod_install(romfs, patch_dir, original_sums() if has else {})
        return
    sums = original_sums()
    state = load_state(romfs)
    if cmd == "status":
        print("installed patch:", state["patch"] if state else "none")
        for rel, h in (state or {}).get("files", {}).items():
            cur = sha(os.path.join(romfs, rel))
            print(f"  {'patched ' if cur == h else 'original' if cur == sums.get(rel) else 'CHANGED '} {rel}")
        lt = (state or {}).get("longshot_table")
        if lt and not os.path.exists(lt["path"]):
            print(f"  gone     {lt['path']} (Longshot 3.1.0 and later serve the game's own size table, which the "
                  f"patch raises)")
        elif lt:
            cur = sha(lt["path"])
            print(f"  {'patched ' if cur == lt['sha'] else 'original' if cur == sha(LONGSHOT_ORIGINAL) else 'CHANGED '} "
                  f"{lt['path']} (Longshot's size table)")
        return
    if cmd == "restore":
        restore(romfs, state, sums)
        save_state(None)
        n_texts = write_longshot_texts(romfs)  # the original text, with Longshot's PC changes
        if n_texts:
            print(f"  wrote     {n_texts} of Longshot's text files from the original text")
        fit_table_to_texts(romfs)
        print("done: original files are back")
        return
    files = patch_files(patch_dir)
    made = new_files_of(patch_dir, files)
    missing = [rel for rel in files if rel not in sums and rel not in made]
    if missing:
        sys.exit(f"Stopped: no original copy saved for {missing[:3]} (build patches with tools/make_patch.py).")
    # Check the whole restore before we touch any file. Every file the new patch writes has to be vanilla
    # already, or go back to vanilla when the old patch comes off.
    problems = restore_problems(romfs, state, sums)
    old = (state or {}).get("files", {})
    old_new = (state or {}).get("new_files", {})
    for rel in files:
        cur = sha(os.path.join(romfs, rel))
        if rel in made:  # a file the game doesn't have (make_patch "new_files"), restore removes it again
            if cur is not None and cur != old_new.get(rel):
                problems.append(f"new file {rel} is already in the game folder (left by something else?)")
        elif cur != sums[rel] and cur != old.get(rel):
            problems.append(f"{rel} in the game folder is not the original")
    if problems:
        sys.exit("Stopped, nothing changed: " + "; ".join(problems[:5]) + " (was Longshot rebuilt?)")
    restore(romfs, state, sums)
    save_state(None)
    table = longshot_table(romfs)
    if os.path.exists(LONGSHOT_ORIGINAL) and os.path.exists(table) and sha(table) != sha(LONGSHOT_ORIGINAL):
        adopt_longshot_table(romfs)  # not ours and no record explains it, so it's a Longshot update's table
    new_table, n_raised = None, 0
    if RSTB in files:
        new_table, n_raised = raise_longshot_table(romfs, files[RSTB])
    # We write the record first so restore can undo a half-done install. If the app closes, a file is locked or
    # the disk fills up, every file still has either its original contents or this patch's version.
    state = {"patch": os.path.abspath(patch_dir),
             "files": {rel: sha(src) for rel, src in files.items() if rel not in made},
             "new_files": {rel: sha(src) for rel, src in files.items() if rel in made}}
    if new_table is not None and n_raised:
        fs_ = Romfs(romfs, ORIGINAL)
        state["longshot_table"] = {"path": table, "sha": hashlib.sha256(new_table).hexdigest(),
                                   "content_sha": hashlib.sha256(fs_.zs.decompress(new_table)).hexdigest()}
    save_state(dict(state, complete=False))
    n_texts = write_longshot_texts(romfs, files)  # Longshot shows its own text copies, so they get the patch's text
    if n_texts:
        print(f"  wrote     {n_texts} of Longshot's text files from the patch's text")
    for rel, src in files.items():
        shutil.copyfile(src, os.path.join(romfs, rel))
        print(f"  installed {rel}")
    if new_table is None:
        fit_table_to_texts(romfs)
    elif n_raised:
        open(table, "wb").write(new_table)
        print(f"  raised    {n_raised} entries in {table} (Longshot's size table)")
    save_state(dict(state, complete=True))
    print(f"done: {len(files)} files from {patch_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("status", "install", "restore", "mod-install", "mod-remove",
                                                "mod-status") or \
            (sys.argv[1] in ("install", "mod-install") and len(sys.argv) != 4):
        sys.exit(__doc__)
    main(*sys.argv[1:])
