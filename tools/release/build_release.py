"""Builds the portable release folder (and its zip): the randomizer app, the tracker, the tools they run and a Python
of their own, with nothing taken from the game.

  python tools/release/build_release.py [OUT_DIR]          default: release/Rando-of-Time

What goes in:
  RandoOfTime.exe, tracker/dist/RandoOfTimeTracker.exe   (built first by release/build.ps1, tracker/build.ps1)
  tools/, data/, config/, vendor/ootr/                         the randomizer (OoTR is MIT licensed: its LICENSE goes too)
  release/data/settings_schema.json                            what the app offers (tools/release/export_schema.py)
  tracker/research/{bntx,build_maps,mapinfo}.py                decode the tracker's map art from the player's own game
  python/                                                      this machine's Python with only the standard library,
                                                               numpy and Pillow (all freely redistributable)
What stays out: the game's files and anything decoded from them (original/, the tracker's maps and icons: the app
builds those from the player's game the first time the tracker opens), seeds (out/), research notes, test plans.
"""
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(HERE, "release", "Rando-of-Time")
PYTHON = sys.base_prefix  # the installed Python (also when this runs in a venv)
# No game text or research leftovers in the release. The player's copy builds whatever text it needs with
# tools/release/first_run.py and install.py's derive_pc_text.
LEAVE_OUT = {"data/rando/hints_messages.json", "data/rando/hints_extra.json", "data/rando/extras_hints.json",
             "data/longshot_pc_text.json",
             # my own dev tools and notes, which stay on my machine (.gitignore "Local only")
             "data/rando/feature_matrix.json", "data/rando/soh_3dr_status.json", "tools/rando/soh_3dr_parity.py",
             "tools/rando/audit_scene_drops.py", "tools/gamedb/audit.py"}
LEAVE_OUT_DIRS = {"data/rando/proposals", "tools/gamedb/audits"}
SITE_PACKAGES = ("numpy", "numpy.libs", "PIL")  # what the tools import beyond the standard library
# tkinter ships because the Archipelago client's window uses it (tools/archipelago/client/app.py). Its Tcl/Tk
# DLLs were already in.
SKIP_DIRS = {"__pycache__", ".git", "site-packages", "test", "tests", "idlelib", "turtledemo", "ensurepip",
             "Doc", "include", "Scripts", "libs", "lib2to3", "pydoc_data"}  # venv stays in, OoTR's Utils imports it

README = """Rando of Time 0.9
=================
A randomizer for the Ocarina of Time remake.

What you need
  - The Ocarina of Time remake, running through Longshot, Rekarina, or a Switch emulator or console.
  - Windows 10 or 11. Nothing to install: everything the randomizer needs is in this folder.

Make a seed
  1. Open RandoOfTime.exe.
  2. Under "Where the seed goes", pick how you play:
     - Longshot (3.1.0 or later): pick Longshot Launcher's folder (the one with builds.json: its default build is
       used) or one game folder (the one with romfs and bin inside). The seed goes in the game's mods folder as a mod,
       which Longshot's Mods tab (F1 in game) lists; Longshot's own game files are never changed.
     - Rekarina: pick Rekarina's game folder (with Rekarina.exe). Under "Game files", pick a dumped romfs folder
       (or leave it empty if you also have Longshot).
     - Switch emulator or console: pick a folder to write the mod to, and a dumped romfs folder under "Game files".
  3. Choose your settings (point at any of them for an explanation), then press "Make the seed".
  4. Start the game and begin a NEW file.

The tracker
  Press "Open the tracker". It shows every check of your seed on the game's own maps, ticks off what you collect while
  you play, and keeps a log. The first time, it builds its maps from your game files (a few minutes).
  Opening the spoiler log marks that seed as spoiled in the tracker.

Your seeds
  Every seed you make is kept in the out folder (its spoiler log, settings and patch).

Back to the original game
  Press "Restore the original game" (under "Where the seed goes"). With Longshot, the seed's mod folder is deleted (a
  seed put into the game files by an older randomizer is undone first); with Rekarina, an SD card or an emulator, the
  seed's files are removed from the mod folder. Other mods stay.
  Close the game first.

If something goes wrong
  The log at the bottom of the window says what happened. Each seed's folder has app.log: attach it to a report.
  Keep this folder somewhere short, such as C:\\Games: from a very deep folder Windows can't load the randomizer's
  Python (the log says so when it starts).
"""


def _copytree(src, dst, keep=None):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(root, src)
        for f in files:
            if f.endswith((".pyc", ".pyo", ".orig")) or (keep and not keep(os.path.join(rel, f))):
                continue
            out = os.path.join(dst, rel, f)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(os.path.join(root, f), out)


def _shipped(rel):
    rel = os.path.normpath(rel).replace(os.sep, "/")
    return rel not in LEAVE_OUT and not any(rel.startswith(x + "/") for x in LEAVE_OUT_DIRS)


def _game_text(path):
    """True if a JSON file holds messages keyed by the game's language codes (its text)."""
    import re
    if not path.endswith(".json"):
        return False
    return bool(re.search(r'"(EUen|USen|JPja|EUde|EUfr|KRko|CNzh)"\s*:\s*[{"]', open(path, encoding="utf-8").read()))


def main(out=OUT):
    exe = os.path.join(HERE, "release", "dist", "RandoOfTime.exe")
    tracker = os.path.join(HERE, "tracker", "dist", "RandoOfTimeTracker.exe")
    for f in (exe, tracker):
        if not os.path.exists(f):
            sys.exit(f"build it first: {f} (release/build.ps1, tracker/build.ps1)")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    shutil.copy2(exe, out)
    shutil.copy2(os.path.join(HERE, "LICENSE"), os.path.join(out, "LICENSE.txt"))  # MIT: the notice travels with it
    os.makedirs(os.path.join(out, "tracker", "dist"))
    shutil.copy2(tracker, os.path.join(out, "tracker", "dist"))
    for d in ("tools", "data", "config"):
        _copytree(os.path.join(HERE, d), os.path.join(out, d), keep=lambda rel, d=d: _shipped(f"{d}/{rel}"))
    _copytree(os.path.join(HERE, "vendor", "ootr"), os.path.join(out, "vendor", "ootr"))
    os.makedirs(os.path.join(out, "release", "data"))
    shutil.copy2(os.path.join(HERE, "release", "data", "settings_schema.json"), os.path.join(out, "release", "data"))
    os.makedirs(os.path.join(out, "tracker", "research"))
    for f in ("bntx.py", "build_maps.py", "mapinfo.py", "build_checks.py"):
        shutil.copy2(os.path.join(HERE, "tracker", "research", f), os.path.join(out, "tracker", "research"))
    # Python: the interpreter, its DLLs and standard library, and the few packages the tools import
    py = os.path.join(out, "python")
    for f in os.listdir(PYTHON):
        if f.endswith((".exe", ".dll")) or f in ("LICENSE.txt",):
            shutil.copy2(os.path.join(PYTHON, f), py if os.path.isdir(py) else (os.makedirs(py) or py))
    _copytree(os.path.join(PYTHON, "DLLs"), os.path.join(py, "DLLs"))
    _copytree(os.path.join(PYTHON, "Lib"), os.path.join(py, "Lib"))
    import importlib.util
    for name in SITE_PACKAGES:
        pkg = name[:-len(".libs")] if name.endswith(".libs") else name
        spec = importlib.util.find_spec(pkg)
        if spec is None:
            sys.exit(f"{pkg} isn't installed in this Python")
        base = os.path.dirname(spec.origin)
        if name.endswith(".libs"):  # numpy's DLLs sit beside the package, wherever it is installed
            base = os.path.join(os.path.dirname(base), name)
        if os.path.isdir(base):
            _copytree(base, os.path.join(py, "Lib", "site-packages", os.path.basename(base)))
    if not os.path.exists(os.path.join(py, "Lib", "os.py")) or not os.path.exists(os.path.join(py, "python.exe")):
        sys.exit(f"the Python copied from {PYTHON} is incomplete")
    # No ._pth file, because it would also drop the script's own folder from sys.path. Instead the app runs this
    # Python with PYTHONNOUSERSITE and without PYTHONPATH/PYTHONHOME, so the player's own Python never mixes in.
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as f:
        f.write(README)
    # leave no game-derived files behind
    for bad in ("original", "out", "installed.json", os.path.join("tracker", "dist", "data"),
                os.path.join("tracker", "research", "checks_proto.json")) + tuple(LEAVE_OUT):
        if os.path.exists(os.path.join(out, bad)):
            sys.exit(f"{bad} must not be in a release")
    for root, _, files in os.walk(out):
        if os.sep + "python" + os.sep in root + os.sep:
            continue
        for f in files:
            if _game_text(os.path.join(root, f)):
                sys.exit(f"{os.path.join(root, f)} holds the game's text: it must not be in a release")
    zpath = out + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(out):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.join(os.path.basename(out), os.path.relpath(full, out)))
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(out) for f in fs)
    print(f"{out}: {size / 1e6:.0f} MB; {zpath}: {os.path.getsize(zpath) / 1e6:.0f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else OUT)
