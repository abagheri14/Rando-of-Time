"""Builds the game-logic index (cache/gamedb) from the remake's files.

usage:
  python tools/gamedb/build.py                      every section, vanilla game (./original first)
  python tools/gamedb/build.py --only events,logic  some sections
  python tools/gamedb/build.py --overlay out/seed1/patch --tag seed1
                                                    the game as that patch makes it: the vanilla index with the
                                                    patch's own files re-indexed (cache/gamedb/test29/)
  python tools/gamedb/build.py --check              say which sections are missing or out of date
Options: --romfs DIR (default: REMAKE_ROMFS or Longshot's rc romfs), --jobs N (default: CPU count, max 12).

Sections build in order, with gamedata last because it names GameData hashes from the strings the other sections
found.
"""
import argparse
import importlib
import multiprocessing as mp
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SECTIONS = ["levels", "events", "logic", "actors", "gamedata"]
MODULES = {s: f"build_{s}" for s in SECTIONS}

_W = {}


def _init(mod_name, romfs, overlays):
    _W["mod"] = importlib.import_module(mod_name)
    _W["fs"] = common.open_romfs(romfs, overlays)


def _one(rel):
    try:
        return rel, _W["mod"].index_file(_W["fs"], rel), None
    except Exception as e:  # noqa: BLE001 - reported, the build goes on
        import traceback
        return rel, None, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"


def _all_files(root):
    out = []
    for d, _, fs_ in os.walk(root):
        for f in fs_:
            out.append(os.path.relpath(os.path.join(d, f), root).replace("\\", "/"))
    return out


def build_section(section, romfs, overlays=(), tag=common.BASE_TAG, jobs=8, log=print):
    mod = importlib.import_module(MODULES[section])
    fs = common.open_romfs(romfs, overlays)
    t0 = time.time()
    if overlays:
        base = common.load(section, common.BASE_TAG)
        if base["meta"].get("version") != mod.VERSION:
            raise SystemExit(f"{section}: the vanilla index is version {base['meta'].get('version')}, the builder "
                             f"{mod.VERSION}: rebuild it first (python tools/gamedb/build.py --only {section})")
        by_file = dict(base["by_file"])
        todo = sorted({r for o in overlays for r in mod.files(o)})
        # If a patched path matches REBUILD_ON we rebuild the whole section, since more than one record can depend
        # on a file like an actor death table or GameDataList.
        deps = [re.compile(x) for x in getattr(mod, "REBUILD_ON", ())]
        hit = sorted(r for o in overlays for r in _all_files(o) if any(d.search(r) for d in deps))
        if hit:
            log(f"{section}: the patch holds {hit[0]}{' and more' if len(hit) > 1 else ''}: re-indexing every file")
            todo = sorted(set(mod.files(fs.root)) | set(todo))
    else:
        by_file = {}
        todo = mod.files(fs.root)
    errors = {}
    if jobs > 1 and len(todo) > 40 and getattr(mod, "PARALLEL", True):
        ctx = mp.get_context("spawn")
        with ctx.Pool(jobs, initializer=_init, initargs=(MODULES[section], romfs, list(overlays))) as pool:
            for rel, rec, err in pool.imap_unordered(_one, todo, chunksize=8):
                if err:
                    errors[rel] = err
                else:
                    by_file[rel] = rec
    else:
        _W["mod"], _W["fs"] = mod, fs
        for rel in todo:
            rel, rec, err = _one(rel)
            if err:
                errors[rel] = err
            else:
                by_file[rel] = rec
    by_file = {k: by_file[k] for k in sorted(by_file)}
    summary = mod.finish(fs, by_file) if hasattr(mod, "finish") else None
    doc = {"meta": common.meta(section, mod.VERSION, fs, len(by_file), time.time() - t0, overlays),
           "by_file": by_file, "summary": summary, "errors": errors}
    if overlays:
        doc["meta"]["overlay_files"] = todo
        doc["meta"]["overlay_fingerprint"] = fingerprint(overlays)
    p = common.save(section, doc, tag)
    log(f"{section}: {len(todo)} files indexed, {len(errors)} errors, {time.time() - t0:.1f} s -> "
        f"{os.path.relpath(p, common.HERE)}")
    for rel, err in list(errors.items())[:5]:
        log(f"  ! {rel}: {err.splitlines()[0]}")
    return doc


def fingerprint(overlays):
    """Path, file count and newest change of each patch folder right now. If a seed gets rebuilt into the same folder,
    or another seed folder has the same name, the overlay index is stale."""
    out = []
    for o in overlays:
        n, newest = 0, 0.0
        for d, _, fs_ in os.walk(o):
            for f in fs_:
                n += 1
                newest = max(newest, os.path.getmtime(os.path.join(d, f)))
        out.append([os.path.abspath(o).replace("\\", "/").lower(), n, round(newest, 3)])
    return out


def check(tag=common.BASE_TAG, overlays=()):
    bad = []
    for s in SECTIONS:
        try:
            mod = importlib.import_module(MODULES[s])
        except ModuleNotFoundError:
            bad.append(f"{s}: no builder ({MODULES[s]}.py)")
            continue
        m = common.load_meta(s, tag)
        if m is None:
            bad.append(f"{s}: missing")
            continue
        if m.get("version") != mod.VERSION or m.get("schema") != common.SCHEMA:
            bad.append(f"{s}: built by version {m.get('version')}, builder is {mod.VERSION}")
        elif overlays and m.get("overlay_fingerprint") != fingerprint(overlays):
            bad.append(f"{s}: built from another state of the patch folder (or another folder of this name)")
    return bad


def ensure(sections=None, romfs=None, overlays=(), tag=common.BASE_TAG, jobs=None, log=print):
    """Builds whatever is missing or stale, the vanilla index first and then the overlay's. The audits call this."""
    jobs = jobs or min(12, os.cpu_count() or 4)
    want = sections or SECTIONS
    stale = {b.split(":")[0] for b in check(common.BASE_TAG)}
    for s in SECTIONS:
        if s in want and s in stale:
            build_section(s, romfs, (), common.BASE_TAG, jobs, log)
    if overlays:
        stale_o = {b.split(":")[0] for b in check(tag, overlays)}
        for s in SECTIONS:
            if s in want and (s in stale_o or s in stale):
                build_section(s, romfs, overlays, tag, jobs, log)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated sections: " + ",".join(SECTIONS))
    ap.add_argument("--romfs", default=None)
    ap.add_argument("--overlay", action="append", default=[], help="a built patch folder (romfs-shaped)")
    ap.add_argument("--tag", default=None, help="cache name for an overlay build (default: the patch's seed folder)")
    ap.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 4))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    tag = a.tag or (os.path.basename(os.path.dirname(os.path.abspath(a.overlay[0]))) if a.overlay else common.BASE_TAG)
    if a.check:
        bad = check(tag, a.overlay)
        print("\n".join(bad) if bad else f"{tag}: every section is built and current")
        return 1 if bad else 0
    secs = a.only.split(",") if a.only else SECTIONS
    for s in secs:
        if s not in SECTIONS:
            raise SystemExit(f"unknown section {s}")
    for s in SECTIONS:
        if s in secs:
            build_section(s, a.romfs, a.overlay, tag, a.jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
