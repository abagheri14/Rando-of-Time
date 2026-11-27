"""Keeps Rekarina's fast text working with a seed's text.

usage: python tools/release/rekarina_text.py PATCH_DIR REKARINA_GAME_DIR       (run before copying to the mods folder)
       python tools/release/rekarina_text.py --check ROMFS REKARINA_GAME_DIR     (our conversion = Rekarina's files)

Rekarina's fast text is an overlay set, romfs-patches-fasttext. You turn it on with rekarina.ini fast_text = 1 or
REKARINA_FAST_TEXT=1, and it's read at start (runtime/cfg.c FAST_TEXT). The overlay is every message archive
(Mals/<Lang>.Product.*.sarc.zs) with the pause tags left out, meaning tags of group 5, types 0-2, without
parameters (setup/<ver>/tools/make_oot_prompts.py).
A mod's file wins over Rekarina's overlay for the same path (runtime/romfs.c), so a seed's text archives (the hints,
the FOOL text...) put the pauses back. With fast text on, this takes them out of the seed's archives too, so you get
both. The archives are written for the setting at export time, so run it again after switching Rekarina's fast
text. With fast text off it changes nothing.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
PAUSE = re.compile(r"\{tag:5,[012]\}")  # group 5, types 0-2, no parameters (Rekarina's PAUSE_GROUP / PAUSE_TYPES)
MARK = "rekarina_fast_text.txt"


def fast_text_on(game_dir):
    """Rekarina's fast text setting. REKARINA_FAST_TEXT first, then fast_text in rekarina.ini (any section), else
    off."""
    env = os.environ.get("REKARINA_FAST_TEXT")
    if env is not None:
        return env.strip() == "1"
    ini = os.path.join(game_dir, "rekarina.ini")
    if os.path.exists(ini):
        for line in open(ini, encoding="utf-8", errors="replace"):
            m = re.match(r"\s*fast_text\s*=\s*(\S+)", line, re.I)
            if m:
                return m.group(1).lower() in ("1", "true", "on", "yes")
    return False


def without_pauses(sarc_data):
    """A message archive (decompressed SARC) with every message's pause tags left out."""
    import msbt
    from romtools import sarc_files, sarc_write
    files = sarc_files(sarc_data)
    for name, data in list(files.items()):
        if not data.startswith(b"MsgStdBn"):
            continue
        try:
            m = msbt.Msbt(data)
        except Exception:  # noqa: BLE001 - a member our reader can't parse (Rekarina leaves UTF-16 files alone too)
            continue
        changed = False
        for label in m.labels:
            text = m.markup(label)
            new = PAUSE.sub("", text)
            if new != text:
                m.set_markup(label, new)
                changed = True
        if changed:
            files[name] = m.dump()
    return sarc_write(files)


def apply(patch_dir, game_dir):
    """Rewrites the patch's message archives without pauses when Rekarina's fast text is on, and returns how many it
    wrote."""
    from romtools import Romfs
    if not fast_text_on(game_dir):
        return 0
    mark = os.path.join(patch_dir, MARK)
    if os.path.exists(mark):
        return 0  # already converted
    mals = os.path.join(patch_dir, "Mals")
    if not os.path.isdir(mals):
        return 0
    zs = Romfs(os.environ.get("REMAKE_ROMFS") or __import__("romtools").longshot_romfs(), None).zs
    n = 0
    for fn in sorted(os.listdir(mals)):
        if not fn.endswith(".sarc.zs"):
            continue
        p = os.path.join(mals, fn)
        raw = open(p, "rb").read()
        open(p, "wb").write(zs.compress(without_pauses(zs.decompress(raw)), zs.dict_id(raw)))
        n += 1
    open(mark, "w", encoding="utf-8").write("message archives written without pauses for Rekarina's fast text\n")
    return n


def check(romfs, game_dir):
    """Checks our conversion of the game's text against Rekarina's fast-text archives and returns a list of problems."""
    import msbt
    from romtools import Romfs, sarc_files
    fs = Romfs(romfs, os.path.join(HERE, "original"))
    folder = os.path.join(game_dir, "romfs-patches-fasttext", "Mals")
    bad = []
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".Product.110.sarc.zs"):
            continue
        ours = sarc_files(without_pauses(fs.read(f"Mals/{fn}")))
        theirs = sarc_files(fs.zs.decompress(open(os.path.join(folder, fn), "rb").read()))
        for name in sorted(theirs):
            if not theirs[name].startswith(b"MsgStdBn"):
                continue
            a, b = msbt.Msbt(ours[name]), msbt.Msbt(theirs[name])
            diff = [lb for lb in b.labels if a.markup(lb) != b.markup(lb)]
            if diff:
                bad.append(f"{fn} {name}: {len(diff)} messages differ, e.g. {diff[0]}")
    return bad


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--check":
        problems = check(sys.argv[2], sys.argv[3])
        print(f"{len(problems)} archives' messages differ from Rekarina's fast text")
        for x in problems[:20]:
            print("  " + x)
        sys.exit(1 if problems else 0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    n = apply(sys.argv[1], sys.argv[2])
    print(f"Rekarina fast text {'on' if fast_text_on(sys.argv[2]) else 'off'}: {n} message archives written without "
          f"pauses")
