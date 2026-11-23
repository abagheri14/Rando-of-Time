"""Builds the files the release can't ship from the player's own game, since they hold the game's text or are decoded
from it (tools/release/build_release.py leaves them out). The randomizer app runs this once, before the first seed.

  python tools/release/first_run.py ROMFS [--force]

  data/rando/hints_messages.json     the vanilla text the hints plugin rewrites (parity/_hints_extract.py)
  data/rando/hints_extra.json        the extra hints' vanilla lines (parity/_hints_extra.py)
  data/rando/extras_hints.json       the scrub offer, loach name and lines the extras hints build on
                                     (parity/_extras_hints_build.py)
  tracker/research/checks_proto.json every check's spot on the game's maps (tracker/research/build_checks.py), which
                                     generate.py needs to write each seed's tracker.json
The tracker's map art and icons are built when the tracker first opens (tools/tracker/build_data.py assets).
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILES = {"hints_messages": os.path.join(HERE, "data", "rando", "hints_messages.json"),
         "hints_extra": os.path.join(HERE, "data", "rando", "hints_extra.json"),
         "extras_hints": os.path.join(HERE, "data", "rando", "extras_hints.json"),
         "checks_proto": os.path.join(HERE, "tracker", "research", "checks_proto.json")}


# Rebuild checks_proto.json when one of these input files is newer.
PROTO_INPUTS = [os.path.join(HERE, "tracker", "research", "build_checks.py"),
                os.path.join(HERE, "tracker", "research", "mapinfo.py"),
                os.path.join(HERE, "data", "rando", "drop_map.json")]


def missing():
    return [k for k, p in FILES.items() if not os.path.exists(p)]


def stale():
    """The files that are there but older than what they're made from."""
    p = FILES["checks_proto"]
    if os.path.exists(p) and any(os.path.exists(x) and os.path.getmtime(x) > os.path.getmtime(p) for x in PROTO_INPUTS):
        return ["checks_proto"]
    return []


def main(romfs, force=False):
    os.environ["REMAKE_ROMFS"] = romfs  # the tracker's map readers take the game from there
    for p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando"), os.path.join(HERE, "tracker", "research")):
        sys.path.insert(0, p)
    todo = list(FILES) if force else missing() + [k for k in stale() if k not in missing()]
    if "hints_messages" in todo:
        from parity import _hints_extract
        _hints_extract.main(romfs)
    if "hints_extra" in todo:
        from parity import _hints_extra
        _hints_extra.build(romfs)
    if "extras_hints" in todo:
        from parity import _extras_hints_build
        _extras_hints_build.build(romfs)
    if "checks_proto" in todo:
        import build_checks
        build_checks.main([])
    left = missing()
    if left:
        sys.exit(f"not built: {', '.join(left)}")
    print(f"built {', '.join(todo) or 'nothing (all there)'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], "--force" in sys.argv)
