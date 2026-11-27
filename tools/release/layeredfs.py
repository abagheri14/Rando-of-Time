"""Where a patch's files go in a LayeredFS mod (a Switch SD card, an emulator's mod folders).

usage: python tools/release/layeredfs.py PATCH_DIR                 the file list as JSON (source, title, path)
       python tools/release/layeredfs.py PATCH_DIR --sd SD_ROOT     copy into SD_ROOT/atmosphere/contents/<title>/romfs
       python tools/release/layeredfs.py PATCH_DIR --emu GAME_DIR   copy for an emulator: GAME_DIR is the game's mod
                                                                    folder (.../<game title>), DLC files go to the
                                                                    sibling .../<DLC title>, each in "<MOD>/romfs"

Longshot extracts the game and its add-on content (the Master Quest DLC) into one romfs, with the DLC's files under
AoC1/ (the add-on content with index 1). The game mounts that content itself (nn::aoc GetAddOnContentBaseId,
ListAddOnContent and HasAoCMQ in its executable), so on a console or an emulator those files belong to the DLC's
title, not the game's. The add-on content base id is the application id + 0x1000 and index 1 adds 1, which is the
Switch convention: 0400486024DEC000 -> 0400486024DED001.
So a patch's AoC1/<path> goes to that title's romfs as <path>, and every other file goes to the game's. A player
without the DLC never reads them, and the game's copies under the same names in the base romfs get patched the same
way.
TODO: not seen working on hardware or an emulator yet.
"""
import json
import os
import shutil
import sys

APP_ID = "0400486024DEC000"
MOD_NAME = "Rando of Time"
SKIP = {"patch_report.json", "rekarina_fast_text.txt"}


def aoc_id(index, app_id=APP_ID):
    return f"{(int(app_id, 16) & ~0xFFF) + 0x1000 + index:016X}"


def layout(patch_dir):
    """[(source path, title id, path inside that title's romfs)] for every game file of the patch."""
    out = []
    for dp, _, fns in os.walk(patch_dir):
        for fn in sorted(fns):
            if fn in SKIP:
                continue
            src = os.path.join(dp, fn)
            rel = os.path.relpath(src, patch_dir).replace(os.sep, "/")
            parts = rel.split("/", 1)
            if parts[0].startswith("AoC") and parts[0][3:].isdigit() and len(parts) == 2:
                out.append((src, aoc_id(int(parts[0][3:])), parts[1]))
            else:
                out.append((src, APP_ID, rel))
    return sorted(out, key=lambda x: (x[1], x[2]))


def copy(patch_dir, dest_of):
    """Copies every file to dest_of(title) / its path and returns the written paths."""
    written = []
    for src, title, path in layout(patch_dir):
        dst = os.path.join(dest_of(title), *path.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(dst)
    return written


def sd_dest(sd_root):
    return lambda title: os.path.join(sd_root, "atmosphere", "contents", title, "romfs")


def emu_dest(game_dir):
    """game_dir is the emulator's mod folder for the game, named after the game's title id like Ryujinx's
    mods/contents/<title> and the yuzu family's load/<title>. The DLC's folder sits next to it."""
    parent = os.path.dirname(os.path.normpath(game_dir))
    return lambda title: os.path.join(game_dir if title == APP_ID else os.path.join(parent, title), MOD_NAME, "romfs")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        print(json.dumps([{"source": s, "title": t, "path": p} for s, t, p in layout(sys.argv[1])], indent=1))
    elif len(sys.argv) == 4 and sys.argv[2] in ("--sd", "--emu"):
        dest = sd_dest(sys.argv[3]) if sys.argv[2] == "--sd" else emu_dest(sys.argv[3])
        files = copy(sys.argv[1], dest)
        titles = sorted({t for _, t, _ in layout(sys.argv[1])})
        print(f"{len(files)} files written for {', '.join(titles)}")
    else:
        sys.exit(__doc__)
